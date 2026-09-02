from __future__ import annotations

import base64
from datetime import date, datetime, time
from decimal import Decimal
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from typing import Annotated, Any
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
import pyodbc
import httpx

from app.core.security import SessionUser, require_screen_access
from app.services.academic_movement_audit import (
    ensure_academic_movement_audit_schema,
    record_academic_movement,
)
from app.services.db import get_connection, get_integration_control_connection
from app.services.graph_documents import (
    complete_upload_session,
    delete_item,
    ensure_folder,
    mark_upload_error,
    prepare_expedient,
    register_upload_session,
    set_document_origin,
    upload_bytes,
)


router = APIRouter(prefix="/api/requests/career-change", tags=["career-change-requests"])

_SCREEN_ACCESS = require_screen_access("solicitudes-cambio-carrera")
_REVIEW_ROLES = {"ADMINISTRADOR", "ACADEMICO"}
_VALID_STATES = {"PENDIENTE", "APROBADA", "RECHAZADA", "APLICADA"}
_PASSING_GRADE = 7.0
_SIMILARITY_THRESHOLD = 0.84
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_schema_lock = Lock()
_schema_ready = False


class CareerChangePreviewPayload(BaseModel):
    codigo_estud: int = Field(gt=0)
    carrera_destino: int = Field(gt=0)


class CareerChangeDecisionPayload(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    observacion: str = Field(default="", max_length=1000)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        return round(float(value), 2) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _normalize_subject_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value).upper())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    ignored = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "E", "EN"}
    return " ".join(token for token in text.split() if token not in ignored)


def _subject_similarity(source_name: Any, target_name: Any) -> float:
    source = _normalize_subject_name(source_name)
    target = _normalize_subject_name(target_name)
    if not source or not target:
        return 0.0
    return round(SequenceMatcher(None, source, target).ratio(), 4)


def _subject_payload(subject: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo_materia": int(subject["codigo_materia"]),
        "codigo_comun": _clean(subject.get("codigo_comun")),
        "nombre": _clean(subject.get("nombre")),
        "nivel": _int_value(subject.get("nivel")),
        "creditos": _float_value(subject.get("creditos")) or 0,
    }


def _match_payload(
    source: dict[str, Any],
    target: dict[str, Any],
    match_type: str,
    similarity: float,
) -> dict[str, Any]:
    return {
        "source": {
            **_subject_payload(source),
            "carrera": _int_value(source.get("carrera")),
            "periodo": _int_value(source.get("periodo")),
            "periodo_nombre": _clean(source.get("periodo_nombre")),
            "nota_final": _float_value(source.get("nota_final")),
        },
        "target": _subject_payload(target),
        "tipo_coincidencia": match_type,
        "similitud": round(similarity, 4),
        "seleccion_recomendada": match_type in {"CODIGO_EXACTO", "NOMBRE_EXACTO"},
    }


def _build_equivalence_preview(
    source_subjects: list[dict[str, Any]],
    target_subjects: list[dict[str, Any]],
) -> dict[str, Any]:
    approved_sources = [
        subject
        for subject in source_subjects
        if (_float_value(subject.get("nota_final")) or 0) >= _PASSING_GRADE
    ]
    used_sources: set[int] = set()
    used_targets: set[int] = set()
    matches: list[dict[str, Any]] = []

    def append_match(
        source: dict[str, Any],
        target: dict[str, Any],
        match_type: str,
        similarity: float,
    ) -> None:
        source_code = int(source["codigo_materia"])
        target_code = int(target["codigo_materia"])
        used_sources.add(source_code)
        used_targets.add(target_code)
        matches.append(_match_payload(source, target, match_type, similarity))

    source_by_common: dict[str, list[dict[str, Any]]] = {}
    for source in approved_sources:
        common_code = _clean(source.get("codigo_comun")).upper()
        if common_code:
            source_by_common.setdefault(common_code, []).append(source)

    for target in target_subjects:
        target_code = int(target["codigo_materia"])
        common_code = _clean(target.get("codigo_comun")).upper()
        candidates = [
            source
            for source in source_by_common.get(common_code, [])
            if int(source["codigo_materia"]) not in used_sources
        ]
        if common_code and candidates:
            source = max(candidates, key=lambda item: _float_value(item.get("nota_final")) or 0)
            append_match(source, target, "CODIGO_EXACTO", 1.0)
            used_targets.add(target_code)

    source_by_name: dict[str, list[dict[str, Any]]] = {}
    for source in approved_sources:
        if int(source["codigo_materia"]) in used_sources:
            continue
        normalized = _normalize_subject_name(source.get("nombre"))
        if normalized:
            source_by_name.setdefault(normalized, []).append(source)

    for target in target_subjects:
        target_code = int(target["codigo_materia"])
        if target_code in used_targets:
            continue
        normalized = _normalize_subject_name(target.get("nombre"))
        candidates = [
            source
            for source in source_by_name.get(normalized, [])
            if int(source["codigo_materia"]) not in used_sources
        ]
        if normalized and candidates:
            source = max(candidates, key=lambda item: _float_value(item.get("nota_final")) or 0)
            append_match(source, target, "NOMBRE_EXACTO", 1.0)

    fuzzy_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for source in approved_sources:
        if int(source["codigo_materia"]) in used_sources:
            continue
        for target in target_subjects:
            if int(target["codigo_materia"]) in used_targets:
                continue
            similarity = _subject_similarity(source.get("nombre"), target.get("nombre"))
            if similarity >= _SIMILARITY_THRESHOLD:
                fuzzy_candidates.append((similarity, source, target))

    for similarity, source, target in sorted(
        fuzzy_candidates,
        key=lambda item: (item[0], _float_value(item[1].get("nota_final")) or 0),
        reverse=True,
    ):
        if int(source["codigo_materia"]) in used_sources:
            continue
        if int(target["codigo_materia"]) in used_targets:
            continue
        append_match(source, target, "NOMBRE_SIMILAR", similarity)

    unmatched_targets = [
        _subject_payload(target)
        for target in target_subjects
        if int(target["codigo_materia"]) not in used_targets
    ]
    unused_approved = [
        {
            **_subject_payload(source),
            "nota_final": _float_value(source.get("nota_final")),
            "periodo": _int_value(source.get("periodo")),
            "periodo_nombre": _clean(source.get("periodo_nombre")),
        }
        for source in approved_sources
        if int(source["codigo_materia"]) not in used_sources
    ]
    return {
        "matches": matches,
        "unmatched_targets": unmatched_targets,
        "unused_approved_sources": unused_approved,
        "summary": {
            "aprobadas_origen": len(approved_sources),
            "equivalencias_exactas": sum(
                1 for item in matches if item["tipo_coincidencia"] != "NOMBRE_SIMILAR"
            ),
            "equivalencias_similares": sum(
                1 for item in matches if item["tipo_coincidencia"] == "NOMBRE_SIMILAR"
            ),
            "materias_destino_sin_equivalencia": len(unmatched_targets),
        },
    }


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'sol')
                    EXEC(N'CREATE SCHEMA sol AUTHORIZATION dbo');

                IF OBJECT_ID(N'sol.SolicitudCambioCarrera', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.SolicitudCambioCarrera
                    (
                        IdSolicitud BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_SolicitudCambioCarrera PRIMARY KEY,
                        CodigoEstud INT NOT NULL,
                        Cedula NVARCHAR(32) NOT NULL,
                        Estudiante NVARCHAR(250) NOT NULL,
                        CarreraOrigen INT NOT NULL,
                        CarreraOrigenNombre NVARCHAR(250) NOT NULL,
                        CarreraDestino INT NOT NULL,
                        CarreraDestinoNombre NVARCHAR(250) NOT NULL,
                        CodigoPeriodoDestino INT NOT NULL,
                        PeriodoDestinoNombre NVARCHAR(250) NOT NULL,
                        Estado NVARCHAR(20) NOT NULL
                            CONSTRAINT DF_SolicitudCambioCarrera_Estado DEFAULT N'PENDIENTE',
                        Motivo NVARCHAR(1000) NOT NULL,
                        ArchivoNombre NVARCHAR(260) NOT NULL,
                        ArchivoRuta NVARCHAR(600) NOT NULL,
                        ArchivoSha256 CHAR(64) NOT NULL,
                        ArchivoTamano BIGINT NOT NULL,
                        GraphDocumentoId BIGINT NULL,
                        GraphWebUrl NVARCHAR(1200) NULL,
                        EstadoExpediente NVARCHAR(30) NULL,
                        CreadoPor NVARCHAR(256) NOT NULL,
                        FechaCreacion DATETIME2 NOT NULL
                            CONSTRAINT DF_SolicitudCambioCarrera_Fecha DEFAULT SYSUTCDATETIME(),
                        RevisadoPor NVARCHAR(256) NULL,
                        FechaRevision DATETIME2 NULL,
                        ObservacionRevision NVARCHAR(1000) NULL,
                        AplicadoPor NVARCHAR(256) NULL,
                        FechaAplicacion DATETIME2 NULL,
                        CONSTRAINT CK_SolicitudCambioCarrera_Estado
                            CHECK (Estado IN (N'PENDIENTE', N'APROBADA', N'RECHAZADA', N'APLICADA'))
                    );
                    CREATE INDEX IX_SolicitudCambioCarrera_Estudiante
                        ON sol.SolicitudCambioCarrera(CodigoEstud, FechaCreacion DESC);
                    CREATE INDEX IX_SolicitudCambioCarrera_Estado
                        ON sol.SolicitudCambioCarrera(Estado, FechaCreacion DESC);
                END;

                IF COL_LENGTH(N'sol.SolicitudCambioCarrera', N'GraphDocumentoId') IS NULL
                    ALTER TABLE sol.SolicitudCambioCarrera ADD GraphDocumentoId BIGINT NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioCarrera', N'GraphWebUrl') IS NULL
                    ALTER TABLE sol.SolicitudCambioCarrera ADD GraphWebUrl NVARCHAR(1200) NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioCarrera', N'EstadoExpediente') IS NULL
                    ALTER TABLE sol.SolicitudCambioCarrera ADD EstadoExpediente NVARCHAR(30) NULL;

                IF OBJECT_ID(N'sol.SolicitudCambioCarreraEquivalencia', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.SolicitudCambioCarreraEquivalencia
                    (
                        IdEquivalencia BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_SolicitudCambioCarreraEquivalencia PRIMARY KEY,
                        IdSolicitud BIGINT NOT NULL,
                        MateriaOrigen INT NOT NULL,
                        CodigoComunOrigen NVARCHAR(100) NULL,
                        NombreMateriaOrigen NVARCHAR(300) NOT NULL,
                        CarreraOrigen INT NOT NULL,
                        PeriodoOrigen INT NULL,
                        PeriodoOrigenNombre NVARCHAR(250) NULL,
                        NotaFinal DECIMAL(5,2) NOT NULL,
                        MateriaDestino INT NOT NULL,
                        CodigoComunDestino NVARCHAR(100) NULL,
                        NombreMateriaDestino NVARCHAR(300) NOT NULL,
                        NivelDestino INT NULL,
                        CreditosDestino DECIMAL(8,2) NULL,
                        TipoCoincidencia NVARCHAR(30) NOT NULL,
                        Similitud DECIMAL(6,4) NOT NULL,
                        Seleccionada BIT NOT NULL,
                        CONSTRAINT FK_SolicitudCambioCarreraEquivalencia_Solicitud
                            FOREIGN KEY (IdSolicitud)
                            REFERENCES sol.SolicitudCambioCarrera(IdSolicitud),
                        CONSTRAINT UQ_SolicitudCambioCarreraEquivalencia_Destino
                            UNIQUE (IdSolicitud, MateriaDestino)
                    );
                END;

                IF OBJECT_ID(N'sol.RespaldoCambioCarrera', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.RespaldoCambioCarrera
                    (
                        IdRespaldo BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_RespaldoCambioCarrera PRIMARY KEY,
                        IdSolicitud BIGINT NOT NULL,
                        CodigoEstud INT NOT NULL,
                        CarreraOrigen INT NOT NULL,
                        CarreraDestino INT NOT NULL,
                        Estado NVARCHAR(20) NOT NULL
                            CONSTRAINT DF_RespaldoCambioCarrera_Estado DEFAULT N'DISPONIBLE',
                        TotalCabeceras INT NOT NULL,
                        TotalMaterias INT NOT NULL,
                        HashContenido CHAR(64) NOT NULL,
                        FechaRespaldo DATETIME2 NOT NULL
                            CONSTRAINT DF_RespaldoCambioCarrera_Fecha DEFAULT SYSUTCDATETIME(),
                        RespaldadoPor NVARCHAR(256) NOT NULL,
                        FechaUltimaRestauracion DATETIME2 NULL,
                        RestauradoPor NVARCHAR(256) NULL,
                        Restauraciones INT NOT NULL
                            CONSTRAINT DF_RespaldoCambioCarrera_Restauraciones DEFAULT 0,
                        ResultadoUltimaRestauracion NVARCHAR(1000) NULL,
                        CONSTRAINT FK_RespaldoCambioCarrera_Solicitud
                            FOREIGN KEY (IdSolicitud)
                            REFERENCES sol.SolicitudCambioCarrera(IdSolicitud),
                        CONSTRAINT UQ_RespaldoCambioCarrera_Solicitud UNIQUE (IdSolicitud),
                        CONSTRAINT CK_RespaldoCambioCarrera_Estado
                            CHECK (Estado IN (N'DISPONIBLE', N'RESTAURADO'))
                    );
                END;

                IF OBJECT_ID(N'sol.RespaldoCambioCarreraFila', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.RespaldoCambioCarreraFila
                    (
                        IdFila BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_RespaldoCambioCarreraFila PRIMARY KEY,
                        IdRespaldo BIGINT NOT NULL,
                        TipoRegistro NVARCHAR(20) NOT NULL,
                        ClaveNatural NVARCHAR(600) NOT NULL,
                        DatosJson NVARCHAR(MAX) NOT NULL,
                        Sha256 CHAR(64) NOT NULL,
                        CONSTRAINT FK_RespaldoCambioCarreraFila_Respaldo
                            FOREIGN KEY (IdRespaldo)
                            REFERENCES sol.RespaldoCambioCarrera(IdRespaldo),
                        CONSTRAINT UQ_RespaldoCambioCarreraFila_Registro
                            UNIQUE (IdRespaldo, TipoRegistro, ClaveNatural),
                        CONSTRAINT CK_RespaldoCambioCarreraFila_Tipo
                            CHECK (TipoRegistro IN (N'CABECERA', N'MATERIA'))
                    );
                    CREATE INDEX IX_RespaldoCambioCarreraFila_Respaldo
                        ON sol.RespaldoCambioCarreraFila(IdRespaldo, TipoRegistro);
                END;
                """
            )
            ensure_academic_movement_audit_schema(cursor)
            conn.commit()
        _schema_ready = True


def _validate_pdf_content(filename: str, content_type: str | None, content: bytes) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix != ".pdf" or (content_type and content_type.lower() not in {"application/pdf", "application/octet-stream"}):
        raise HTTPException(status_code=422, detail="El respaldo debe ser un archivo PDF.")
    if not content:
        raise HTTPException(status_code=422, detail="El archivo PDF está vacío.")
    if len(content) > _MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="El archivo PDF supera el límite de 20 MB.")
    if not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="El contenido cargado no corresponde a un PDF válido.")


def _safe_filename(filename: str) -> str:
    stem = unicodedata.normalize("NFKD", Path(filename or "respaldo.pdf").stem)
    stem = "".join(character for character in stem if not unicodedata.combining(character))
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "respaldo"
    return f"{stem[:90]}.pdf"


def _user_label(user: SessionUser) -> str:
    return (_clean(user.email) or _clean(user.login) or "USUARIO")[:256]


def _legacy_user_code(user: SessionUser) -> str:
    internal_id = _clean(user.id_usuario)
    return (internal_id or _clean(user.login) or "SISTEMA")[:10]


def _require_reviewer(user: SessionUser) -> None:
    if user.rol.upper() not in _REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="Solo Académico o Administrador puede aprobar y aplicar la solicitud.")


def _fetch_student_context(cursor: pyodbc.Cursor, codigo_estud: int) -> dict[str, Any]:
    cursor.execute(
        """
        WITH ultima_cabecera AS
        (
            SELECT
                cab.codigo_estud,
                TRY_CONVERT(int, cab.cod_anio_Basica) AS cod_anio_Basica,
                TRY_CONVERT(int, cab.codigo_periodo) AS codigo_periodo,
                ROW_NUMBER() OVER
                (
                    PARTITION BY cab.codigo_estud
                    ORDER BY
                        TRY_CONVERT(int, cab.codigo_periodo) DESC,
                        COALESCE(TRY_CONVERT(datetime2, cab.fecha_pago), CAST('19000101' AS datetime2)) DESC,
                        TRY_CONVERT(bigint, cab.numcodigo) DESC,
                        TRY_CONVERT(int, cab.Num_Matricula) DESC
                ) AS fila
            FROM dbo.CABECERA_MATRICULA cab
            WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
        ),
        ultima_materia AS
        (
            SELECT
                cxe.codigo_estud,
                TRY_CONVERT(int, cxe.cod_anio_Basica) AS cod_anio_Basica,
                TRY_CONVERT(int, cxe.codigo_periodo) AS codigo_periodo,
                ROW_NUMBER() OVER
                (
                    PARTITION BY cxe.codigo_estud
                    ORDER BY
                        COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC,
                        TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                        TRY_CONVERT(bigint, cxe.num) DESC
                ) AS fila
            FROM dbo.CARRERAXESTUD cxe
            WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
        )
        SELECT TOP (1)
            TRY_CONVERT(int, d.codigo_estud) AS codigo_estud,
            TRY_CONVERT(nvarchar(32), d.Cedula_Est) AS cedula,
            TRY_CONVERT(nvarchar(250), d.Apellidos_nombre) AS estudiante,
            TRY_CONVERT(nvarchar(10), d.Estado) AS estado,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(300), d.correointec))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(300), d.correo))), N'')
            ) AS correo,
            COALESCE(uc.cod_anio_Basica, um.cod_anio_Basica) AS carrera_origen,
            TRY_CONVERT(nvarchar(250), c.Nombre_Basica) AS carrera_origen_nombre,
            COALESCE(uc.codigo_periodo, um.codigo_periodo) AS periodo_origen
        FROM dbo.DATOS_ESTUD d
        LEFT JOIN ultima_cabecera uc ON uc.codigo_estud = d.codigo_estud AND uc.fila = 1
        LEFT JOIN ultima_materia um ON um.codigo_estud = d.codigo_estud AND um.fila = 1
        LEFT JOIN dbo.CARRERAS c
          ON TRY_CONVERT(int, c.Cod_AnioBasica) = COALESCE(uc.cod_anio_Basica, um.cod_anio_Basica)
        WHERE TRY_CONVERT(int, d.codigo_estud) = ?
        """,
        codigo_estud,
        codigo_estud,
        codigo_estud,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el estudiante seleccionado.")
    if _int_value(row.carrera_origen) is None:
        raise HTTPException(status_code=409, detail="El estudiante no tiene una carrera de origen registrada.")
    return {
        "codigo_estud": int(row.codigo_estud),
        "cedula": _clean(row.cedula),
        "estudiante": _clean(row.estudiante),
        "estado": _clean(row.estado),
        "correo": _clean(row.correo),
        "carrera_origen": int(row.carrera_origen),
        "carrera_origen_nombre": _clean(row.carrera_origen_nombre),
        "periodo_origen": _int_value(row.periodo_origen),
    }


def _fetch_career(cursor: pyodbc.Cursor, career_code: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, Cod_AnioBasica) AS codigo,
            TRY_CONVERT(nvarchar(250), Nombre_Basica) AS nombre,
            TRY_CONVERT(nvarchar(10), Estado) AS estado
        FROM dbo.CARRERAS
        WHERE TRY_CONVERT(int, Cod_AnioBasica) = ?
        """,
        career_code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró la carrera de destino.")
    if _clean(row.estado).upper() not in {"", "A"}:
        raise HTTPException(status_code=409, detail="La carrera de destino no está activa.")
    return {"codigo": int(row.codigo), "nombre": _clean(row.nombre)}


def _fetch_period(cursor: pyodbc.Cursor, period_code: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, cod_periodo) AS codigo,
            TRY_CONVERT(nvarchar(250), Detalle_Periodo) AS nombre,
            fechain,
            fechafin
        FROM dbo.PERIODO
        WHERE TRY_CONVERT(int, cod_periodo) = ?
        """,
        period_code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el período de destino.")
    return {
        "codigo": int(row.codigo),
        "nombre": _clean(row.nombre),
        "fecha_inicio": row.fechain.isoformat() if row.fechain else None,
        "fecha_fin": row.fechafin.isoformat() if row.fechafin else None,
    }


def _fetch_source_subjects(cursor: pyodbc.Cursor, codigo_estud: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        WITH historial AS
        (
            SELECT
                TRY_CONVERT(int, cxe.codigo_materia) AS codigo_materia,
                TRY_CONVERT(int, cxe.cod_anio_Basica) AS carrera,
                TRY_CONVERT(int, cxe.codigo_periodo) AS periodo,
                TRY_CONVERT(nvarchar(100), p.cod_materia) AS codigo_comun,
                TRY_CONVERT(nvarchar(300), p.Nomb_Materia) AS nombre,
                TRY_CONVERT(int, p.Semestre) AS nivel,
                TRY_CONVERT(decimal(8,2), COALESCE(p.Creditos, cxe.Num_Creditos, 0)) AS creditos,
                TRY_CONVERT(nvarchar(250), pe.Detalle_Periodo) AS periodo_nombre,
                COALESCE(
                    TRY_CONVERT(decimal(5,2), cxe.PromedioFinal),
                    TRY_CONVERT(decimal(5,2), cxe.Promedio),
                    TRY_CONVERT(decimal(5,2), cxe.PromedioAux),
                    TRY_CONVERT(decimal(5,2), cxe.Recuperacion)
                ) AS nota_final,
                ROW_NUMBER() OVER
                (
                    PARTITION BY TRY_CONVERT(int, cxe.codigo_materia)
                    ORDER BY
                        COALESCE(
                            TRY_CONVERT(decimal(5,2), cxe.PromedioFinal),
                            TRY_CONVERT(decimal(5,2), cxe.Promedio),
                            TRY_CONVERT(decimal(5,2), cxe.PromedioAux),
                            TRY_CONVERT(decimal(5,2), cxe.Recuperacion),
                            -1
                        ) DESC,
                        TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                        TRY_CONVERT(bigint, cxe.num) DESC
                ) AS fila
            FROM dbo.CARRERAXESTUD cxe
            LEFT JOIN dbo.PENSUM p
              ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
             AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
            LEFT JOIN dbo.PERIODO pe
              ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
            WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
        )
        SELECT * FROM historial WHERE fila = 1 AND codigo_materia IS NOT NULL
        """,
        codigo_estud,
    )
    return [
        {
            "codigo_materia": int(row.codigo_materia),
            "carrera": _int_value(row.carrera),
            "periodo": _int_value(row.periodo),
            "codigo_comun": _clean(row.codigo_comun),
            "nombre": _clean(row.nombre) or f"Materia {row.codigo_materia}",
            "nivel": _int_value(row.nivel),
            "creditos": _float_value(row.creditos) or 0,
            "periodo_nombre": _clean(row.periodo_nombre),
            "nota_final": _float_value(row.nota_final),
        }
        for row in cursor.fetchall()
    ]


def _fetch_target_subjects(cursor: pyodbc.Cursor, career_code: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            TRY_CONVERT(int, codigo_materia) AS codigo_materia,
            TRY_CONVERT(nvarchar(100), cod_materia) AS codigo_comun,
            TRY_CONVERT(nvarchar(300), Nomb_Materia) AS nombre,
            TRY_CONVERT(int, Semestre) AS nivel,
            TRY_CONVERT(decimal(8,2), COALESCE(Creditos, 0)) AS creditos
        FROM dbo.PENSUM
        WHERE TRY_CONVERT(int, Cod_AnioBasica) = ?
          AND TRY_CONVERT(int, codigo_materia) IS NOT NULL
        ORDER BY TRY_CONVERT(int, Semestre), TRY_CONVERT(int, Orden), Nomb_Materia
        """,
        career_code,
    )
    return [
        {
            "codigo_materia": int(row.codigo_materia),
            "codigo_comun": _clean(row.codigo_comun),
            "nombre": _clean(row.nombre),
            "nivel": _int_value(row.nivel),
            "creditos": _float_value(row.creditos) or 0,
        }
        for row in cursor.fetchall()
    ]


def _preview_with_cursor(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    carrera_destino: int,
) -> dict[str, Any]:
    student = _fetch_student_context(cursor, codigo_estud)
    target_career = _fetch_career(cursor, carrera_destino)
    if student["carrera_origen"] == target_career["codigo"]:
        raise HTTPException(status_code=409, detail="La carrera de destino debe ser diferente de la carrera actual.")
    source_subjects = _fetch_source_subjects(cursor, codigo_estud)
    target_subjects = _fetch_target_subjects(cursor, carrera_destino)
    if not target_subjects:
        raise HTTPException(status_code=409, detail="La carrera de destino no tiene un pénsum configurado.")
    equivalences = _build_equivalence_preview(source_subjects, target_subjects)
    return {
        "student": student,
        "target_career": target_career,
        **equivalences,
    }


def _selected_pairs(raw_json: str) -> set[tuple[int, int]]:
    try:
        raw_items = json.loads(raw_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="La selección de equivalencias no es válida.") from exc
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=422, detail="La selección de equivalencias debe ser una lista.")
    pairs: set[tuple[int, int]] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="Existe una equivalencia con formato inválido.")
        source = _int_value(item.get("source_codigo_materia"))
        target = _int_value(item.get("target_codigo_materia"))
        if source is None or target is None:
            raise HTTPException(status_code=422, detail="Existe una equivalencia incompleta.")
        pairs.add((source, target))
    return pairs


_SNAPSHOT_KEYS: dict[str, tuple[str, ...]] = {
    "CABECERA": ("codigo_estud", "cod_anio_Basica", "codigo_periodo"),
    "MATERIA": (
        "codigo_estud",
        "cod_anio_Basica",
        "codigo_materia",
        "Num_Matricula",
        "paralelo",
        "NumGrupo",
    ),
}

_SNAPSHOT_TABLES = {
    "CABECERA": "CABECERA_MATRICULA",
    "MATERIA": "CARRERAXESTUD",
}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__type__": "time", "value": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "__type__": "bytes",
            "value": base64.b64encode(bytes(value)).decode("ascii"),
        }
    return {"__type__": "string", "value": str(value)}


def _json_restore_value(value: Any) -> Any:
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    value_type = value.get("__type__")
    raw_value = value.get("value")
    if value_type == "decimal":
        return Decimal(str(raw_value))
    if value_type == "datetime":
        return datetime.fromisoformat(str(raw_value))
    if value_type == "date":
        return date.fromisoformat(str(raw_value))
    if value_type == "time":
        return time.fromisoformat(str(raw_value))
    if value_type == "bytes":
        return base64.b64decode(str(raw_value), validate=True)
    return _clean(raw_value)


def _snapshot_row(record_type: str, data: dict[str, Any]) -> dict[str, str]:
    key_columns = _SNAPSHOT_KEYS.get(record_type)
    if not key_columns:
        raise ValueError("Tipo de registro de respaldo no permitido.")
    missing = [column for column in key_columns if column not in data]
    if missing:
        raise ValueError(f"El respaldo no contiene su clave natural: {', '.join(missing)}.")
    safe_data = {column: _json_safe_value(value) for column, value in data.items()}
    data_json = json.dumps(
        safe_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    natural_key = json.dumps(
        [_json_safe_value(data[column]) for column in key_columns],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {
        "tipo_registro": record_type,
        "clave_natural": natural_key,
        "datos_json": data_json,
        "sha256": hashlib.sha256(data_json.encode("utf-8")).hexdigest(),
    }


def _cursor_row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [str(description[0]) for description in cursor.description or ()]
    return dict(zip(columns, row, strict=True))


def _capture_career_snapshot(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    carrera_origen: int,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    cursor.execute(
        """
        SELECT cab.*
        FROM dbo.CABECERA_MATRICULA cab WITH (HOLDLOCK)
        WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
          AND TRY_CONVERT(int, cab.cod_anio_Basica) = ?
        ORDER BY TRY_CONVERT(int, cab.codigo_periodo), TRY_CONVERT(int, cab.Num_Matricula)
        """,
        codigo_estud,
        carrera_origen,
    )
    for row in cursor.fetchall():
        rows.append(_snapshot_row("CABECERA", _cursor_row_dict(cursor, row)))

    cursor.execute(
        """
        SELECT cxe.*
        FROM dbo.CARRERAXESTUD cxe WITH (HOLDLOCK)
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
          AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
        ORDER BY
            TRY_CONVERT(int, cxe.codigo_periodo),
            TRY_CONVERT(int, cxe.codigo_materia),
            TRY_CONVERT(bigint, cxe.num)
        """,
        codigo_estud,
        carrera_origen,
    )
    for row in cursor.fetchall():
        rows.append(_snapshot_row("MATERIA", _cursor_row_dict(cursor, row)))

    header_count = sum(1 for row in rows if row["tipo_registro"] == "CABECERA")
    subject_count = sum(1 for row in rows if row["tipo_registro"] == "MATERIA")
    if subject_count == 0:
        raise HTTPException(
            status_code=409,
            detail="No existen materias de la carrera de origen para generar el respaldo.",
        )
    digest_source = "\n".join(
        f"{row['tipo_registro']}|{row['clave_natural']}|{row['sha256']}"
        for row in sorted(rows, key=lambda item: (item["tipo_registro"], item["clave_natural"]))
    )
    return {
        "rows": rows,
        "total_cabeceras": header_count,
        "total_materias": subject_count,
        "hash_contenido": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
    }


def _career_record_counts(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    career_code: int,
) -> tuple[int, int]:
    cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM dbo.CABECERA_MATRICULA cab WITH (HOLDLOCK)
                WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
                  AND TRY_CONVERT(int, cab.cod_anio_Basica) = ?
            ) AS total_cabeceras,
            (
                SELECT COUNT(*)
                FROM dbo.CARRERAXESTUD cxe WITH (HOLDLOCK)
                WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
                  AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
            ) AS total_materias
        """,
        codigo_estud,
        career_code,
        codigo_estud,
        career_code,
    )
    row = cursor.fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _verify_source_career_backup(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    backup: dict[str, Any],
) -> bool:
    header_count, subject_count = _career_record_counts(
        cursor,
        request_item["codigo_estud"],
        request_item["carrera_origen"],
    )
    if header_count == 0 and subject_count == 0:
        return False
    if (
        header_count != backup["total_cabeceras"]
        or subject_count != backup["total_materias"]
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La trayectoria de origen cambió después de generar el respaldo. "
                "No se retiró ningún registro; genere una nueva revisión académica."
            ),
        )
    current_snapshot = _capture_career_snapshot(
        cursor,
        request_item["codigo_estud"],
        request_item["carrera_origen"],
    )
    if current_snapshot["hash_contenido"] != backup["hash_contenido"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "La trayectoria de origen no coincide con el respaldo íntegro. "
                "No se retiró ningún registro; revise las calificaciones antes de continuar."
            ),
        )
    return True


def _archive_source_career(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
) -> dict[str, int]:
    if request_item["carrera_origen"] == request_item["carrera_destino"]:
        raise HTTPException(status_code=409, detail="La carrera de origen y destino no pueden coincidir.")
    parameters = (request_item["codigo_estud"], request_item["carrera_origen"])
    cursor.execute(
        """
        DELETE FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
        """,
        *parameters,
    )
    archived_subjects = max(int(cursor.rowcount or 0), 0)
    cursor.execute(
        """
        DELETE FROM dbo.CABECERA_MATRICULA
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
        """,
        *parameters,
    )
    archived_headers = max(int(cursor.rowcount or 0), 0)
    remaining_headers, remaining_subjects = _career_record_counts(cursor, *parameters)
    if remaining_headers or remaining_subjects:
        raise HTTPException(
            status_code=409,
            detail="No se pudo retirar completamente la carrera de origen; la operación fue cancelada.",
        )
    return {
        "source_headers_archived": archived_headers,
        "source_subjects_archived": archived_subjects,
    }


def _backup_metadata(row: Any) -> dict[str, Any]:
    return {
        "id_respaldo": int(row.IdRespaldo),
        "id_solicitud": int(row.IdSolicitud),
        "codigo_estud": int(row.CodigoEstud),
        "carrera_origen": int(row.CarreraOrigen),
        "carrera_destino": int(row.CarreraDestino),
        "estado": _clean(row.Estado),
        "total_cabeceras": int(row.TotalCabeceras or 0),
        "total_materias": int(row.TotalMaterias or 0),
        "hash_contenido": _clean(row.HashContenido),
        "fecha_respaldo": row.FechaRespaldo.isoformat() if row.FechaRespaldo else None,
        "restauraciones": int(row.Restauraciones or 0),
        "fecha_ultima_restauracion": (
            row.FechaUltimaRestauracion.isoformat() if row.FechaUltimaRestauracion else None
        ),
    }


def _find_backup(cursor: pyodbc.Cursor, request_id: int) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT * FROM sol.RespaldoCambioCarrera WHERE IdSolicitud = ?",
        request_id,
    )
    row = cursor.fetchone()
    return _backup_metadata(row) if row else None


def _persist_career_snapshot(
    *,
    request_id: int,
    request_item: dict[str, Any],
    snapshot: dict[str, Any],
    audit_user: str,
) -> dict[str, Any]:
    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cursor.execute(
            "SELECT * FROM sol.RespaldoCambioCarrera WITH (UPDLOCK, HOLDLOCK) WHERE IdSolicitud = ?",
            request_id,
        )
        existing = cursor.fetchone()
        if existing:
            backup = _backup_metadata(existing)
            if (
                backup["codigo_estud"] != request_item["codigo_estud"]
                or backup["carrera_origen"] != request_item["carrera_origen"]
                or backup["carrera_destino"] != request_item["carrera_destino"]
            ):
                raise HTTPException(
                    status_code=409,
                    detail="El respaldo existente no corresponde a la trayectoria de esta solicitud.",
                )
            return backup

        cursor.execute(
            """
            INSERT INTO sol.RespaldoCambioCarrera
            (
                IdSolicitud, CodigoEstud, CarreraOrigen, CarreraDestino,
                Estado, TotalCabeceras, TotalMaterias, HashContenido, RespaldadoPor
            )
            OUTPUT INSERTED.IdRespaldo
            VALUES (?, ?, ?, ?, N'DISPONIBLE', ?, ?, ?, ?)
            """,
            request_id,
            request_item["codigo_estud"],
            request_item["carrera_origen"],
            request_item["carrera_destino"],
            snapshot["total_cabeceras"],
            snapshot["total_materias"],
            snapshot["hash_contenido"],
            audit_user,
        )
        backup_id = int(cursor.fetchone()[0])
        for row in snapshot["rows"]:
            cursor.execute(
                """
                INSERT INTO sol.RespaldoCambioCarreraFila
                    (IdRespaldo, TipoRegistro, ClaveNatural, DatosJson, Sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                backup_id,
                row["tipo_registro"],
                row["clave_natural"],
                row["datos_json"],
                row["sha256"],
            )
        conn.commit()
        cursor.execute("SELECT * FROM sol.RespaldoCambioCarrera WHERE IdRespaldo = ?", backup_id)
        return _backup_metadata(cursor.fetchone())


def _quote_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _table_insertable_columns(cursor: pyodbc.Cursor, table_name: str) -> list[str]:
    if table_name not in set(_SNAPSHOT_TABLES.values()):
        raise ValueError("Tabla de restauración no permitida.")
    cursor.execute(
        """
        SELECT col.name
        FROM sys.columns col
        INNER JOIN sys.tables tab ON tab.object_id = col.object_id
        INNER JOIN sys.schemas sch ON sch.schema_id = tab.schema_id
        WHERE sch.name = N'dbo'
          AND tab.name = ?
          AND col.is_identity = 0
          AND col.is_computed = 0
          AND col.generated_always_type = 0
          AND col.system_type_id <> 189
        ORDER BY col.column_id
        """,
        table_name,
    )
    return [_clean(row[0]) for row in cursor.fetchall()]


def _decode_snapshot_data(data_json: str, expected_hash: str) -> dict[str, Any]:
    actual_hash = hashlib.sha256(data_json.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        raise HTTPException(status_code=409, detail="El respaldo académico no superó la validación de integridad.")
    try:
        raw_data = json.loads(data_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="El respaldo académico tiene un formato inválido.") from exc
    if not isinstance(raw_data, dict):
        raise HTTPException(status_code=409, detail="El respaldo académico tiene un formato inválido.")
    try:
        return {column: _json_restore_value(value) for column, value in raw_data.items()}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="El respaldo académico contiene valores inválidos.") from exc


def _restore_snapshot_rows(
    cursor: pyodbc.Cursor,
    snapshot_rows: list[dict[str, str]],
    *,
    expected_student: int,
    expected_career: int,
) -> dict[str, int]:
    available_columns: dict[str, list[str]] = {}
    inserted_headers = 0
    inserted_subjects = 0
    skipped = 0
    ordered_rows = sorted(
        snapshot_rows,
        key=lambda item: (0 if item["tipo_registro"] == "CABECERA" else 1, item["clave_natural"]),
    )
    for snapshot_row in ordered_rows:
        record_type = snapshot_row["tipo_registro"]
        table_name = _SNAPSHOT_TABLES.get(record_type)
        key_columns = _SNAPSHOT_KEYS.get(record_type)
        if not table_name or not key_columns:
            raise HTTPException(status_code=409, detail="El respaldo contiene un tipo de registro no permitido.")
        data = _decode_snapshot_data(snapshot_row["datos_json"], snapshot_row["sha256"])
        if any(column not in data for column in key_columns):
            raise HTTPException(status_code=409, detail="Una fila del respaldo no contiene su clave académica.")
        canonical_row = _snapshot_row(record_type, data)
        if canonical_row["clave_natural"] != snapshot_row["clave_natural"]:
            raise HTTPException(
                status_code=409,
                detail="Una fila del respaldo no coincide con su clave académica registrada.",
            )
        if (
            _int_value(data.get("codigo_estud")) != expected_student
            or _int_value(data.get("cod_anio_Basica")) != expected_career
        ):
            raise HTTPException(
                status_code=409,
                detail="El respaldo no corresponde al estudiante y carrera de origen de la solicitud.",
            )

        predicates: list[str] = []
        key_parameters: list[Any] = []
        for column in key_columns:
            quoted = _quote_identifier(column)
            predicates.append(f"({quoted} = ? OR ({quoted} IS NULL AND ? IS NULL))")
            key_parameters.extend((data[column], data[column]))
        cursor.execute(
            f"SELECT COUNT(*) FROM dbo.{_quote_identifier(table_name)} WHERE {' AND '.join(predicates)}",
            *key_parameters,
        )
        if int(cursor.fetchone()[0] or 0) > 0:
            skipped += 1
            continue

        if table_name not in available_columns:
            available_columns[table_name] = _table_insertable_columns(cursor, table_name)
        snapshot_lookup = {column.lower(): column for column in data}
        insert_columns = [
            column for column in available_columns[table_name] if column.lower() in snapshot_lookup
        ]
        if not insert_columns:
            raise HTTPException(status_code=409, detail="No existen columnas compatibles para restaurar el respaldo.")
        values = [data[snapshot_lookup[column.lower()]] for column in insert_columns]
        quoted_columns = ", ".join(_quote_identifier(column) for column in insert_columns)
        placeholders = ", ".join("?" for _ in insert_columns)
        cursor.execute(
            f"INSERT INTO dbo.{_quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})",
            *values,
        )
        if record_type == "CABECERA":
            inserted_headers += 1
        else:
            inserted_subjects += 1
    return {
        "cabeceras_restauradas": inserted_headers,
        "materias_restauradas": inserted_subjects,
        "existentes_omitidos": skipped,
    }


def _row_to_request(row: Any) -> dict[str, Any]:
    graph_url = _clean(getattr(row, "GraphWebUrl", ""))
    stored_path = _clean(row.ArchivoRuta).replace(chr(92), "/")
    is_legacy_path = (
        bool(stored_path)
        and stored_path != "PENDIENTE_EXPEDIENTE"
        and not stored_path.startswith("EXPEDIENTES ESTUDIANTILES/")
    )
    legacy_url = f"/uploads/{stored_path}" if is_legacy_path else ""
    graph_document_id = _int_value(getattr(row, "GraphDocumentoId", None))
    return {
        "id": int(row.IdSolicitud),
        "codigo_estud": int(row.CodigoEstud),
        "cedula": _clean(row.Cedula),
        "estudiante": _clean(row.Estudiante),
        "carrera_origen": int(row.CarreraOrigen),
        "carrera_origen_nombre": _clean(row.CarreraOrigenNombre),
        "carrera_destino": int(row.CarreraDestino),
        "carrera_destino_nombre": _clean(row.CarreraDestinoNombre),
        "codigo_periodo_destino": int(row.CodigoPeriodoDestino),
        "periodo_destino_nombre": _clean(row.PeriodoDestinoNombre),
        "estado": _clean(row.Estado),
        "motivo": _clean(row.Motivo),
        "archivo_nombre": _clean(row.ArchivoNombre),
        "archivo_url": graph_url or legacy_url,
        "expediente_documento_id": graph_document_id,
        "archivo_en_expediente": graph_document_id is not None,
        "estado_expediente": _clean(getattr(row, "EstadoExpediente", "")),
        "creado_por": _clean(row.CreadoPor),
        "fecha_creacion": row.FechaCreacion.isoformat() if row.FechaCreacion else None,
        "revisado_por": _clean(row.RevisadoPor),
        "fecha_revision": row.FechaRevision.isoformat() if row.FechaRevision else None,
        "observacion_revision": _clean(row.ObservacionRevision),
        "aplicado_por": _clean(row.AplicadoPor),
        "fecha_aplicacion": row.FechaAplicacion.isoformat() if row.FechaAplicacion else None,
        "equivalencias": int(getattr(row, "TotalEquivalencias", 0) or 0),
        "respaldo_estado": _clean(getattr(row, "RespaldoEstado", "")),
        "respaldo_cabeceras": int(getattr(row, "RespaldoCabeceras", 0) or 0),
        "respaldo_materias": int(getattr(row, "RespaldoMaterias", 0) or 0),
        "fecha_respaldo": (
            row.FechaRespaldo.isoformat() if getattr(row, "FechaRespaldo", None) else None
        ),
        "restauraciones": int(getattr(row, "Restauraciones", 0) or 0),
        "fecha_ultima_restauracion": (
            row.FechaUltimaRestauracion.isoformat()
            if getattr(row, "FechaUltimaRestauracion", None)
            else None
        ),
        "auditoria_id": _int_value(getattr(row, "AuditoriaId", None)),
        "auditoria_hash": _clean(getattr(row, "AuditoriaHash", "")),
    }


def _archive_supporting_document(
    *,
    request_id: int,
    student: dict[str, Any],
    original_filename: str,
    content: bytes,
    audit_user: str,
) -> dict[str, Any]:
    session_id = uuid4()
    graph_item: dict[str, Any] | None = None
    session_registered = False
    try:
        graph_expedient = prepare_expedient(
            module_code="SOLICITUDES",
            identification=student["cedula"],
            student_code=int(student["codigo_estud"]),
            student_name=student["estudiante"],
            student_email=student.get("correo", ""),
            base_origin="INTEC_INTEGRACION_CONTROL",
            schema_origin="sol",
            table_origin="SolicitudCambioCarrera",
            origin_id=request_id,
            expedient_code=f"CAMBIO-CARRERA-{request_id}",
            audit_user=audit_user,
        )
        upload_folder = f"{graph_expedient['folder_path']}/CAMBIO DE CARRERA"
        ensure_folder(upload_folder)
        cloud_filename = (
            f"RESPALDO-CAMBIO-CARRERA-{request_id}-"
            f"{_safe_filename(original_filename)}"
        )
        graph_path = f"{upload_folder}/{cloud_filename}"
        register_upload_session(
            session_id=session_id,
            expedient_graph_id=int(graph_expedient["expedient_graph_id"]),
            document_type_code="RESPALDO_CAMBIO_CARRERA",
            original_filename=original_filename,
            cloud_filename=cloud_filename,
            graph_path=graph_path,
            content_type="application/pdf",
            expected_size=len(content),
            upload_url="",
            expires_at=None,
            audit_user=audit_user,
            max_expected_size=_MAX_DOCUMENT_BYTES,
        )
        session_registered = True
        graph_item = upload_bytes(graph_path, content, "application/pdf")
        graph_document = complete_upload_session(
            session_id=session_id,
            graph_item=graph_item,
            edit_deadline=None,
            audit_user=audit_user,
            append_document=False,
        )
        document_id = int(graph_document["document_graph_id"])
        set_document_origin(document_id, request_id)
        return {
            "document_id": document_id,
            "web_url": _clean(graph_document.get("graph_web_url")),
            "graph_path": graph_path,
            "cloud_filename": cloud_filename,
        }
    except Exception:
        if session_registered:
            try:
                mark_upload_error(session_id, "No se pudo archivar el respaldo de cambio de carrera.", audit_user)
            except (RuntimeError, pyodbc.Error):
                pass
        if graph_item and _clean(graph_item.get("id")):
            try:
                delete_item(_clean(graph_item.get("id")))
            except httpx.HTTPError:
                pass
        raise


def _delete_unarchived_request(request_id: int) -> None:
    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sol.SolicitudCambioCarreraEquivalencia WHERE IdSolicitud = ?",
            request_id,
        )
        cursor.execute(
            "DELETE FROM sol.SolicitudCambioCarrera WHERE IdSolicitud = ?",
            request_id,
        )
        conn.commit()


def _delete_unarchived_request_safely(request_id: int) -> None:
    try:
        _delete_unarchived_request(request_id)
    except (RuntimeError, pyodbc.Error):
        # Preserve the original upload error; a pending row is safer than
        # masking the failure or deleting a document that reached OneDrive.
        pass


def _request_select() -> str:
    return """
        SELECT
            s.*,
            (SELECT COUNT(*) FROM sol.SolicitudCambioCarreraEquivalencia e
             WHERE e.IdSolicitud = s.IdSolicitud AND e.Seleccionada = 1) AS TotalEquivalencias,
            respaldo.Estado AS RespaldoEstado,
            respaldo.TotalCabeceras AS RespaldoCabeceras,
            respaldo.TotalMaterias AS RespaldoMaterias,
            respaldo.FechaRespaldo,
            respaldo.Restauraciones,
            respaldo.FechaUltimaRestauracion,
            auditoria.IdMovimiento AS AuditoriaId,
            auditoria.HashMovimiento AS AuditoriaHash
        FROM sol.SolicitudCambioCarrera s
        LEFT JOIN sol.RespaldoCambioCarrera respaldo
          ON respaldo.IdSolicitud = s.IdSolicitud
        LEFT JOIN aud.MovimientoAcademico auditoria
          ON auditoria.TipoSolicitud = 'CARRERA'
         AND auditoria.IdSolicitud = s.IdSolicitud
         AND auditoria.Accion = 'APLICAR'
    """


@router.get("/catalog")
def career_change_catalog(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    query: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    del current_user
    normalized_query = query.strip()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(int, Cod_AnioBasica) AS codigo,
                    TRY_CONVERT(nvarchar(250), Nombre_Basica) AS nombre
                FROM dbo.CARRERAS
                WHERE ISNULL(Estado, 'A') = 'A'
                ORDER BY Nombre_Basica
                """
            )
            careers = [{"codigo": int(row.codigo), "nombre": _clean(row.nombre)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT TOP (120)
                    TRY_CONVERT(int, cod_periodo) AS codigo,
                    TRY_CONVERT(nvarchar(250), Detalle_Periodo) AS nombre,
                    fechain,
                    fechafin
                FROM dbo.PERIODO
                ORDER BY COALESCE(fechain, CAST('19000101' AS date)) DESC, cod_periodo DESC
                """
            )
            periods = [
                {
                    "codigo": int(row.codigo),
                    "nombre": _clean(row.nombre),
                    "fecha_inicio": row.fechain.isoformat() if row.fechain else None,
                    "fecha_fin": row.fechafin.isoformat() if row.fechafin else None,
                }
                for row in cursor.fetchall()
            ]
            students: list[dict[str, Any]] = []
            if len(normalized_query) >= 2:
                text_search = f"%{normalized_query}%"
                digits = re.sub(r"\D+", "", normalized_query)
                document_search = f"%{digits}%" if digits else text_search
                cursor.execute(
                    f"""
                    WITH latest AS
                    (
                        SELECT
                            cxe.codigo_estud,
                            TRY_CONVERT(int, cxe.cod_anio_Basica) AS carrera,
                            ROW_NUMBER() OVER
                            (
                                PARTITION BY cxe.codigo_estud
                                ORDER BY
                                    COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC,
                                    TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                                    TRY_CONVERT(bigint, cxe.num) DESC
                            ) AS fila
                        FROM dbo.CARRERAXESTUD cxe
                    )
                    SELECT TOP ({limit})
                        TRY_CONVERT(int, d.codigo_estud) AS codigo_estud,
                        TRY_CONVERT(nvarchar(32), d.Cedula_Est) AS cedula,
                        TRY_CONVERT(nvarchar(250), d.Apellidos_nombre) AS estudiante,
                        TRY_CONVERT(nvarchar(10), d.Estado) AS estado,
                        latest.carrera,
                        TRY_CONVERT(nvarchar(250), c.Nombre_Basica) AS carrera_nombre
                    FROM dbo.DATOS_ESTUD d
                    LEFT JOIN latest ON latest.codigo_estud = d.codigo_estud AND latest.fila = 1
                    LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = latest.carrera
                    WHERE d.Apellidos_nombre LIKE ?
                       OR d.Cedula_Est LIKE ?
                       OR TRY_CONVERT(varchar(50), d.codigo_estud) = ?
                    ORDER BY d.Apellidos_nombre
                    """,
                    text_search,
                    document_search,
                    normalized_query,
                )
                students = [
                    {
                        "codigo_estud": int(row.codigo_estud),
                        "cedula": _clean(row.cedula),
                        "estudiante": _clean(row.estudiante),
                        "estado": _clean(row.estado),
                        "carrera": _int_value(row.carrera),
                        "carrera_nombre": _clean(row.carrera_nombre),
                    }
                    for row in cursor.fetchall()
                ]
        return {
            "students": students,
            "careers": careers,
            "periods": periods,
            "states": sorted(_VALID_STATES),
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar el catálogo de cambio de carrera: {exc}") from exc


@router.post("/preview")
def preview_career_change(
    payload: CareerChangePreviewPayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            return _preview_with_cursor(conn.cursor(), payload.codigo_estud, payload.carrera_destino)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo comparar el historial con el pénsum destino: {exc}") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_career_change_request(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    codigo_estud: Annotated[int, Form(gt=0)],
    carrera_destino: Annotated[int, Form(gt=0)],
    codigo_periodo_destino: Annotated[int, Form(gt=0)],
    motivo: Annotated[str, Form(min_length=10, max_length=1000)],
    equivalencias_json: Annotated[str, Form()] = "[]",
    archivo: UploadFile = File(...),
) -> dict[str, Any]:
    selected = _selected_pairs(equivalencias_json)
    original_filename = archivo.filename or "respaldo.pdf"
    content_type = archivo.content_type
    try:
        content = await archivo.read(_MAX_DOCUMENT_BYTES + 1)
    finally:
        await archivo.close()
    _validate_pdf_content(original_filename, content_type, content)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            preview = _preview_with_cursor(cursor, codigo_estud, carrera_destino)
            period = _fetch_period(cursor, codigo_periodo_destino)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo validar la solicitud: {exc}") from exc

    available_matches = {
        (
            int(item["source"]["codigo_materia"]),
            int(item["target"]["codigo_materia"]),
        ): item
        for item in preview["matches"]
    }
    invalid_pairs = selected.difference(available_matches)
    if invalid_pairs:
        raise HTTPException(
            status_code=409,
            detail="Una o más equivalencias ya no coinciden con el historial o el pénsum vigente.",
        )

    _ensure_schema()
    student = preview["student"]
    target_career = preview["target_career"]
    request_id: int | None = None
    archived: dict[str, Any] | None = None

    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM sol.SolicitudCambioCarrera
                WHERE CodigoEstud = ? AND Estado IN (N'PENDIENTE', N'APROBADA')
                """,
                codigo_estud,
            )
            if int(cursor.fetchone()[0] or 0) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="El estudiante ya tiene una solicitud de cambio de carrera pendiente o aprobada.",
                )
            cursor.execute(
                """
                INSERT INTO sol.SolicitudCambioCarrera
                (
                    CodigoEstud, Cedula, Estudiante,
                    CarreraOrigen, CarreraOrigenNombre,
                    CarreraDestino, CarreraDestinoNombre,
                    CodigoPeriodoDestino, PeriodoDestinoNombre,
                    Estado, Motivo, ArchivoNombre, ArchivoRuta,
                    ArchivoSha256, ArchivoTamano, CreadoPor
                )
                OUTPUT INSERTED.IdSolicitud
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, N'PENDIENTE', ?, ?, ?, ?, ?, ?)
                """,
                codigo_estud,
                student["cedula"],
                student["estudiante"],
                student["carrera_origen"],
                student["carrera_origen_nombre"],
                carrera_destino,
                target_career["nombre"],
                codigo_periodo_destino,
                period["nombre"],
                motivo.strip(),
                original_filename,
                "PENDIENTE_EXPEDIENTE",
                hashlib.sha256(content).hexdigest(),
                len(content),
                _user_label(current_user),
            )
            request_id = int(cursor.fetchone()[0])
            for pair, item in available_matches.items():
                source = item["source"]
                target = item["target"]
                cursor.execute(
                    """
                    INSERT INTO sol.SolicitudCambioCarreraEquivalencia
                    (
                        IdSolicitud, MateriaOrigen, CodigoComunOrigen, NombreMateriaOrigen,
                        CarreraOrigen, PeriodoOrigen, PeriodoOrigenNombre, NotaFinal,
                        MateriaDestino, CodigoComunDestino, NombreMateriaDestino,
                        NivelDestino, CreditosDestino, TipoCoincidencia, Similitud, Seleccionada
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    request_id,
                    int(source["codigo_materia"]),
                    source["codigo_comun"],
                    source["nombre"],
                    int(source["carrera"]),
                    source["periodo"],
                    source["periodo_nombre"],
                    source["nota_final"],
                    int(target["codigo_materia"]),
                    target["codigo_comun"],
                    target["nombre"],
                    target["nivel"],
                    target["creditos"],
                    item["tipo_coincidencia"],
                    item["similitud"],
                    1 if pair in selected else 0,
                )
            conn.commit()

        archived = _archive_supporting_document(
            request_id=request_id,
            student=student,
            original_filename=original_filename,
            content=content,
            audit_user=_user_label(current_user),
        )
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sol.SolicitudCambioCarrera
                   SET ArchivoNombre = ?, ArchivoRuta = ?, GraphDocumentoId = ?,
                       GraphWebUrl = ?, EstadoExpediente = N'CARGADO'
                 WHERE IdSolicitud = ?
                """,
                archived["cloud_filename"],
                archived["graph_path"],
                archived["document_id"],
                archived["web_url"],
                request_id,
            )
            conn.commit()
        return {
            "ok": True,
            "message": "La solicitud se registró y su respaldo se guardó en el expediente del estudiante.",
            "id": request_id,
            "estado": "PENDIENTE",
            "equivalencias_seleccionadas": len(selected),
            "expediente_documento_id": archived["document_id"],
            "expediente_url": archived["web_url"],
        }
    except HTTPException:
        if request_id is not None and archived is None:
            _delete_unarchived_request_safely(request_id)
        raise
    except httpx.HTTPError as exc:
        if request_id is not None and archived is None:
            _delete_unarchived_request_safely(request_id)
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft OneDrive no pudo guardar el respaldo en el expediente: {exc}",
        ) from exc
    except (pyodbc.Error, RuntimeError, ValueError) as exc:
        if request_id is not None and archived is None:
            _delete_unarchived_request_safely(request_id)
        raise HTTPException(status_code=503, detail=f"No se pudo registrar la solicitud: {exc}") from exc


@router.get("")
def list_career_change_requests(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    query: Annotated[str, Query(max_length=120)] = "",
    state: Annotated[str, Query(max_length=20)] = "TODOS",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    del current_user
    _ensure_schema()
    normalized_state = state.strip().upper()
    if normalized_state != "TODOS" and normalized_state not in _VALID_STATES:
        raise HTTPException(status_code=422, detail="El estado solicitado no es válido.")
    search = f"%{query.strip()}%"
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                {_request_select()}
                WHERE (? = N'TODOS' OR s.Estado = ?)
                  AND (
                    ? = N'%%'
                    OR s.Estudiante LIKE ?
                    OR s.Cedula LIKE ?
                    OR TRY_CONVERT(nvarchar(30), s.IdSolicitud) LIKE ?
                  )
                ORDER BY s.FechaCreacion DESC
                OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY
                """,
                normalized_state,
                normalized_state,
                search,
                search,
                search,
                search,
            )
            items = [_row_to_request(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudieron consultar las solicitudes: {exc}") from exc


@router.get("/{request_id}")
def career_change_request_detail(
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    _ensure_schema()
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"{_request_select()} WHERE s.IdSolicitud = ?", request_id)
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
            request_item = _row_to_request(row)
            cursor.execute(
                """
                SELECT *
                FROM sol.SolicitudCambioCarreraEquivalencia
                WHERE IdSolicitud = ?
                ORDER BY Seleccionada DESC, NivelDestino, NombreMateriaDestino
                """,
                request_id,
            )
            equivalences = [
                {
                    "id": int(item.IdEquivalencia),
                    "materia_origen": int(item.MateriaOrigen),
                    "codigo_comun_origen": _clean(item.CodigoComunOrigen),
                    "nombre_materia_origen": _clean(item.NombreMateriaOrigen),
                    "periodo_origen": _int_value(item.PeriodoOrigen),
                    "periodo_origen_nombre": _clean(item.PeriodoOrigenNombre),
                    "nota_final": _float_value(item.NotaFinal),
                    "materia_destino": int(item.MateriaDestino),
                    "codigo_comun_destino": _clean(item.CodigoComunDestino),
                    "nombre_materia_destino": _clean(item.NombreMateriaDestino),
                    "nivel_destino": _int_value(item.NivelDestino),
                    "creditos_destino": _float_value(item.CreditosDestino),
                    "tipo_coincidencia": _clean(item.TipoCoincidencia),
                    "similitud": float(item.Similitud),
                    "seleccionada": bool(item.Seleccionada),
                }
                for item in cursor.fetchall()
            ]
        return {**request_item, "equivalences": equivalences}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar la solicitud: {exc}") from exc


@router.post("/{request_id}/decision")
def decide_career_change_request(
    request_id: int,
    payload: CareerChangeDecisionPayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    _require_reviewer(current_user)
    _ensure_schema()
    decision = payload.decision.strip().upper()
    if decision not in {"APROBADA", "RECHAZADA"}:
        raise HTTPException(status_code=422, detail="La decisión debe ser APROBADA o RECHAZADA.")
    if decision == "RECHAZADA" and len(payload.observacion.strip()) < 5:
        raise HTTPException(status_code=422, detail="Registre el motivo del rechazo.")
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sol.SolicitudCambioCarrera
                SET Estado = ?, RevisadoPor = ?, FechaRevision = SYSUTCDATETIME(),
                    ObservacionRevision = ?
                WHERE IdSolicitud = ? AND Estado = N'PENDIENTE'
                """,
                decision,
                _user_label(current_user),
                payload.observacion.strip(),
                request_id,
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=409, detail="La solicitud ya fue revisada o no existe.")
            conn.commit()
        if decision == "APROBADA":
            result = apply_career_change_request(request_id, current_user)
            return {
                **result,
                "message": f"La solicitud fue aprobada. {result['message']}",
            }
        return {"ok": True, "message": "La solicitud quedó rechazada.", "estado": decision}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo registrar la decisión: {exc}") from exc


def _next_registration_number(cursor: pyodbc.Cursor) -> int:
    cursor.execute(
        "SELECT COALESCE(MAX(TRY_CONVERT(int, Num_Reg_Mat)), 0) + 1 FROM dbo.CARRERAXESTUD WITH (UPDLOCK, HOLDLOCK)"
    )
    return int(cursor.fetchone()[0] or 1)


def _ensure_target_header(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
) -> int:
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, Num_Matricula) AS Num_Matricula
        FROM dbo.CABECERA_MATRICULA
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        ORDER BY TRY_CONVERT(int, Num_Matricula) DESC
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_destino"],
    )
    existing = cursor.fetchone()
    if existing:
        return int(existing.Num_Matricula or 1)

    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(nvarchar(100), Jornada) AS Jornada,
            TRY_CONVERT(int, codjornada) AS codjornada
        FROM dbo.CABECERA_MATRICULA
        WHERE TRY_CONVERT(int, codigo_estud) = ?
        ORDER BY TRY_CONVERT(int, codigo_periodo) DESC, TRY_CONVERT(int, Num_Matricula) DESC
        """,
        request_item["codigo_estud"],
    )
    source_header = cursor.fetchone()
    jornada = _clean(source_header.Jornada) if source_header else ""
    cod_jornada = _int_value(source_header.codjornada) if source_header else None
    cursor.execute(
        """
        INSERT INTO dbo.CABECERA_MATRICULA
        (
            codigo_estud, cod_anio_Basica, codigo_periodo, Num_Matricula, fecha_pago,
            valor, InscripValor, MatriValor, Cuota1, RecargoMatricula, Beca, Descuento,
            Jornada, AyudaEcono, ControlMatricula, ValorNivelacion, codhorario, codmodalidad,
            coddias, codjornada, codestadoMat, reingreso,
            Descuentoprontopago, Descuentoreferidos
        )
        VALUES (?, ?, ?, 1, ?, 0, 0, 0, 0, 0, 0, 0, ?, 0, 1, 0, 0, 0, 0, ?, 0, 0, 0, 0)
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_destino"],
        date.today().isoformat(),
        jornada,
        cod_jornada or 1,
    )
    return 1


def _apply_equivalence(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    equivalence: dict[str, Any],
    registration_number: int,
    legacy_user_code: str,
) -> bool:
    stored_user_code = (_clean(legacy_user_code) or "SISTEMA")[:10]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
          AND TRY_CONVERT(int, codigo_materia) = ?
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_destino"],
        equivalence["materia_destino"],
    )
    if int(cursor.fetchone()[0] or 0) > 0:
        return False

    cursor.execute(
        """
        SELECT TOP (1) *
        FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_materia) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        ORDER BY
            COALESCE(
                TRY_CONVERT(decimal(5,2), PromedioFinal),
                TRY_CONVERT(decimal(5,2), Promedio),
                TRY_CONVERT(decimal(5,2), PromedioAux),
                TRY_CONVERT(decimal(5,2), Recuperacion),
                -1
            ) DESC,
            TRY_CONVERT(bigint, num) DESC
        """,
        request_item["codigo_estud"],
        equivalence["carrera_origen"],
        equivalence["materia_origen"],
        equivalence["periodo_origen"],
    )
    source = cursor.fetchone()
    if not source:
        raise HTTPException(status_code=409, detail="Ya no existe la calificación de origen de una equivalencia aprobada.")

    approved_grade = (
        _float_value(equivalence.get("nota_final"))
        or _float_value(source.PromedioFinal)
        or _float_value(source.Promedio)
        or _float_value(source.PromedioAux)
        or _float_value(source.Recuperacion)
    )
    if approved_grade is None or approved_grade < _PASSING_GRADE:
        raise HTTPException(
            status_code=409,
            detail="La calificación de origen ya no cumple la nota mínima para convalidación.",
        )

    cursor.execute(
        """
        INSERT INTO dbo.CARRERAXESTUD
        (
            codigo_estud, cod_anio_Basica, codigo_materia, codigo_periodo,
            Num_Matricula, paralelo, NumGrupo,
            P1Tareas, P1Proyectos, P1Examen, promP1,
            P2Tareas, P2Proyectos, P2Examen, promP2,
            P3Tareas, P3Proyectos, P3Examen, promP3,
            Promedio, Asistencia, Recuperacion, PromedioFinal, caprueba,
            Usuario, Num_Creditos, Fecha_Matricula, Num_Reg_Mat,
            ObservacionP1, ObservacionP2, MateriaConvalidada,
            TipoMatricula, PromedioAux, ControlAprueba, ControlMatricula,
            teoriaHomo, practicahomo, CodUsuaMat, TipoCursoMigra
        )
        VALUES
        (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
            'N', ?, ?, ?, ?, ?, ?, ?
        )
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        equivalence["materia_destino"],
        request_item["codigo_periodo_destino"],
        1,
        _clean(source.paralelo) or "A",
        _int_value(source.NumGrupo) or 1,
        source.P1Tareas,
        source.P1Proyectos,
        source.P1Examen,
        source.promP1,
        source.P2Tareas,
        source.P2Proyectos,
        source.P2Examen,
        source.promP2,
        source.P3Tareas,
        source.P3Proyectos,
        source.P3Examen,
        source.promP3,
        source.Promedio if source.Promedio is not None else approved_grade,
        source.Asistencia,
        source.Recuperacion,
        source.PromedioFinal if source.PromedioFinal is not None else approved_grade,
        "A",
        stored_user_code,
        equivalence["creditos_destino"] or source.Num_Creditos,
        date.today().isoformat(),
        registration_number,
        source.ObservacionP1,
        source.ObservacionP2,
        source.PromedioAux if source.PromedioAux is not None else approved_grade,
        source.ControlAprueba if source.ControlAprueba is not None else "A",
        source.ControlMatricula,
        source.teoriaHomo,
        source.practicahomo,
        stored_user_code,
        _clean(source.TipoCursoMigra),
    )
    return True


@router.post("/{request_id}/apply")
def apply_career_change_request(
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    _require_reviewer(current_user)
    _ensure_schema()
    try:
        with get_integration_control_connection() as integration_conn:
            integration_cursor = integration_conn.cursor()
            integration_cursor.execute(f"{_request_select()} WHERE s.IdSolicitud = ?", request_id)
            row = integration_cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
            request_item = _row_to_request(row)
            backup = _find_backup(integration_cursor, request_id)
            already_applied = request_item["estado"] == "APLICADA"
            if already_applied and backup and backup["estado"] == "RESTAURADO":
                return {
                    "ok": True,
                    "message": "La carrera anterior ya fue recuperada desde el respaldo.",
                    "estado": "APLICADA",
                    "inserted": 0,
                    "existing_skipped": 0,
                    "respaldo_cabeceras": backup["total_cabeceras"],
                    "respaldo_materias": backup["total_materias"],
                    "source_headers_archived": 0,
                    "source_subjects_archived": 0,
                }
            if request_item["estado"] not in {"APROBADA", "APLICADA"}:
                raise HTTPException(status_code=409, detail="La solicitud debe estar aprobada antes de aplicarla.")
            integration_cursor.execute(
                """
                SELECT *
                FROM sol.SolicitudCambioCarreraEquivalencia
                WHERE IdSolicitud = ? AND Seleccionada = 1
                ORDER BY IdEquivalencia
                """,
                request_id,
            )
            equivalences = [
                {
                    "materia_origen": int(item.MateriaOrigen),
                    "carrera_origen": int(item.CarreraOrigen),
                    "periodo_origen": int(item.PeriodoOrigen) if item.PeriodoOrigen is not None else None,
                    "materia_destino": int(item.MateriaDestino),
                    "creditos_destino": _float_value(item.CreditosDestino),
                    "nota_final": _float_value(item.NotaFinal),
                }
                for item in integration_cursor.fetchall()
            ]

        with get_connection() as primary_conn:
            cursor = primary_conn.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            student_context = _fetch_student_context(cursor, request_item["codigo_estud"])
            if student_context["carrera_origen"] not in {
                request_item["carrera_origen"],
                request_item["carrera_destino"],
            }:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "La carrera actual del estudiante ya no coincide con el origen ni con el destino "
                        "de esta solicitud. Revise su historial antes de continuar."
                    ),
                )
            _fetch_career(cursor, request_item["carrera_origen"])
            _fetch_career(cursor, request_item["carrera_destino"])
            _fetch_period(cursor, request_item["codigo_periodo_destino"])

            if not backup:
                snapshot = _capture_career_snapshot(
                    cursor,
                    request_item["codigo_estud"],
                    request_item["carrera_origen"],
                )
                backup = _persist_career_snapshot(
                    request_id=request_id,
                    request_item=request_item,
                    snapshot=snapshot,
                    audit_user=_user_label(current_user),
                )
            source_career_present = _verify_source_career_backup(cursor, request_item, backup)

            inserted = 0
            skipped = 0
            legacy_user_code = _legacy_user_code(current_user)
            _ensure_target_header(cursor, request_item)
            next_registration = _next_registration_number(cursor)
            for equivalence in equivalences:
                was_inserted = _apply_equivalence(
                    cursor,
                    request_item,
                    equivalence,
                    next_registration,
                    legacy_user_code,
                )
                if was_inserted:
                    inserted += 1
                    next_registration += 1
                else:
                    skipped += 1
            archived = {
                "source_headers_archived": 0,
                "source_subjects_archived": 0,
            }
            if source_career_present:
                archived = _archive_source_career(cursor, request_item)
            primary_conn.commit()

        with get_integration_control_connection() as integration_conn:
            cursor = integration_conn.cursor()
            audit = record_academic_movement(
                cursor,
                request_type="CARRERA",
                request_id=request_id,
                action="APLICAR",
                student_code=request_item["codigo_estud"],
                source_career=request_item["carrera_origen"],
                target_career=request_item["carrera_destino"],
                source_period=None,
                target_period=request_item["codigo_periodo_destino"],
                source_modality=None,
                target_modality=None,
                backup_headers=backup["total_cabeceras"],
                backup_subjects=backup["total_materias"],
                migrated_subjects=len(equivalences),
                deleted_records=backup["total_cabeceras"] + backup["total_materias"],
                backup_hash=backup["hash_contenido"],
                before={
                    "carrera": request_item["carrera_origen"],
                    "cabeceras": backup["total_cabeceras"],
                    "materias": backup["total_materias"],
                },
                after={
                    "carrera": request_item["carrera_destino"],
                    "periodo": request_item["codigo_periodo_destino"],
                    "equivalencias_migradas": len(equivalences),
                },
                audit_user=_user_label(current_user),
            )
            if not already_applied:
                cursor.execute(
                    """
                    UPDATE sol.SolicitudCambioCarrera
                    SET Estado = N'APLICADA', AplicadoPor = ?, FechaAplicacion = SYSUTCDATETIME()
                    WHERE IdSolicitud = ? AND Estado = N'APROBADA'
                    """,
                    _user_label(current_user),
                    request_id,
                )
            integration_conn.commit()
        return {
            "ok": True,
            "message": (
                "Se completó el reemplazo: la carrera anterior quedó únicamente en el respaldo."
                if already_applied and sum(archived.values()) > 0
                else (
                    "La solicitud ya estaba aplicada y la trayectoria anterior permanece respaldada."
                    if already_applied
                    else "El cambio de carrera se aplicó; la trayectoria anterior quedó respaldada y fuera de la matrícula activa."
                )
            ),
            "estado": "APLICADA",
            "inserted": inserted,
            "existing_skipped": skipped,
            "respaldo_cabeceras": backup["total_cabeceras"] if backup else 0,
            "respaldo_materias": backup["total_materias"] if backup else 0,
            "auditoria_id": audit["id_movimiento"],
            **archived,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"No se pudo validar la auditoría: {exc}") from exc
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo aplicar el cambio de carrera: {exc}") from exc


@router.post("/{request_id}/restore")
def restore_previous_career(
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    _require_reviewer(current_user)
    _ensure_schema()
    try:
        with get_integration_control_connection() as integration_conn:
            integration_cursor = integration_conn.cursor()
            integration_cursor.execute(f"{_request_select()} WHERE s.IdSolicitud = ?", request_id)
            request_row = integration_cursor.fetchone()
            if not request_row:
                raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
            request_item = _row_to_request(request_row)
            if request_item["estado"] != "APLICADA":
                raise HTTPException(
                    status_code=409,
                    detail="La carrera anterior solo puede recuperarse después de aplicar el cambio.",
                )
            backup = _find_backup(integration_cursor, request_id)
            if not backup:
                raise HTTPException(
                    status_code=409,
                    detail="Esta solicitud no tiene un respaldo académico disponible.",
                )
            integration_cursor.execute(
                """
                SELECT TipoRegistro, ClaveNatural, DatosJson, Sha256
                FROM sol.RespaldoCambioCarreraFila
                WHERE IdRespaldo = ?
                ORDER BY CASE WHEN TipoRegistro = N'CABECERA' THEN 0 ELSE 1 END, ClaveNatural
                """,
                backup["id_respaldo"],
            )
            snapshot_rows = [
                {
                    "tipo_registro": _clean(row.TipoRegistro),
                    "clave_natural": _clean(row.ClaveNatural),
                    "datos_json": str(row.DatosJson),
                    "sha256": _clean(row.Sha256),
                }
                for row in integration_cursor.fetchall()
            ]

        expected_rows = backup["total_cabeceras"] + backup["total_materias"]
        if len(snapshot_rows) != expected_rows:
            raise HTTPException(
                status_code=409,
                detail="El respaldo académico está incompleto y no puede restaurarse.",
            )
        digest_source = "\n".join(
            f"{row['tipo_registro']}|{row['clave_natural']}|{row['sha256']}"
            for row in sorted(
                snapshot_rows,
                key=lambda item: (item["tipo_registro"], item["clave_natural"]),
            )
        )
        if hashlib.sha256(digest_source.encode("utf-8")).hexdigest() != backup["hash_contenido"]:
            raise HTTPException(
                status_code=409,
                detail="El respaldo académico no superó la validación integral.",
            )

        with get_connection() as primary_conn:
            primary_cursor = primary_conn.cursor()
            primary_cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _fetch_student_context(primary_cursor, request_item["codigo_estud"])
            _fetch_career(primary_cursor, request_item["carrera_origen"])
            restored = _restore_snapshot_rows(
                primary_cursor,
                snapshot_rows,
                expected_student=request_item["codigo_estud"],
                expected_career=request_item["carrera_origen"],
            )
            primary_conn.commit()

        result_text = (
            f"Cabeceras recuperadas: {restored['cabeceras_restauradas']}; "
            f"materias recuperadas: {restored['materias_restauradas']}; "
            f"registros ya existentes: {restored['existentes_omitidos']}."
        )
        with get_integration_control_connection() as integration_conn:
            integration_cursor = integration_conn.cursor()
            integration_cursor.execute(
                """
                UPDATE sol.RespaldoCambioCarrera
                SET Estado = N'RESTAURADO',
                    FechaUltimaRestauracion = SYSUTCDATETIME(),
                    RestauradoPor = ?,
                    Restauraciones = Restauraciones + 1,
                    ResultadoUltimaRestauracion = ?
                WHERE IdRespaldo = ?
                """,
                _user_label(current_user),
                result_text,
                backup["id_respaldo"],
            )
            integration_conn.commit()

        return {
            "ok": True,
            "message": (
                "La trayectoria de la carrera anterior está disponible para una nueva matrícula. "
                "Las notas y registros que ya existían se conservaron sin cambios."
            ),
            "estado": "RESTAURADO",
            **restored,
        }
    except HTTPException:
        raise
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail=f"El respaldo académico no es válido: {exc}") from exc
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo recuperar la carrera anterior: {exc}") from exc
