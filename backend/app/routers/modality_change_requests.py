from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from typing import Annotated, Any
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
import httpx
from pydantic import BaseModel, Field
import pyodbc

from app.core.security import SessionUser, require_screen_access
from app.core.file_security import read_secure_upload
from app.services.academic_movement_audit import (
    build_snapshot_row,
    cursor_row_dict,
    ensure_academic_movement_audit_schema,
    record_academic_movement,
    snapshot_digest,
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


router = APIRouter(prefix="/api/requests/modality-change", tags=["modality-change-requests"])

_SCREEN_ACCESS = require_screen_access("solicitudes-cambio-modalidad")
_REVIEW_ROLES = {"ADMINISTRADOR", "ACADEMICO"}
_VALID_STATES = {"PENDIENTE", "APROBADA", "RECHAZADA", "APLICADA"}
_VALID_PERIOD_TYPES = {"R", "H"}
_ENROLLMENT_TYPE_BY_PERIOD = {"R": "N", "H": "H"}
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_MAX_SUPPORTING_FILES = 10
_MAX_TOTAL_DOCUMENT_BYTES = 100 * 1024 * 1024
_PASSING_GRADE = 7.0
_HOMOLOGATION_THEORY_WEIGHT = 0.40
_HOMOLOGATION_PRACTICE_WEIGHT = 0.60
_STUDENT_MODALITY_BY_ENROLLMENT = {1: "5", 3: "1"}
_ENROLLMENT_MODALITY_BY_STUDENT = {5: 1, 1: 3}
_GRADE_FIELDS = (
    "P1Tareas",
    "P1Proyectos",
    "P1Examen",
    "promP1",
    "P2Tareas",
    "P2Proyectos",
    "P2Examen",
    "promP2",
    "P3Tareas",
    "P3Proyectos",
    "P3Examen",
    "promP3",
    "Promedio",
    "Asistencia",
    "Recuperacion",
    "PromedioFinal",
    "PromedioAux",
    "teoriaHomo",
    "practicahomo",
)
_MODALITY_SNAPSHOT_KEYS = {
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
_schema_lock = Lock()
_schema_ready = False


class ModalityChangePreviewPayload(BaseModel):
    codigo_estud: int = Field(gt=0)
    carrera_destino: int = Field(gt=0)
    codigo_periodo_homologacion: int = Field(gt=0)


class ModalityChangeDecisionPayload(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    observacion: str = Field(default="", max_length=1000)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float:
    try:
        return round(float(value), 2) if value is not None and str(value).strip() else 0.0
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    try:
        return round(float(value), 3) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _normalize_common_code(value: Any) -> str:
    return re.sub(r"\s+", "", _clean(value).upper())


def _user_label(user: SessionUser) -> str:
    return (_clean(user.email) or _clean(user.login) or "USUARIO")[:256]


def _legacy_user_code(user: SessionUser) -> str:
    internal_id = _clean(user.id_usuario)
    return (internal_id or _clean(user.login) or "SISTEMA")[:10]


def _validate_pdf_content(filename: str, content_type: str | None, content: bytes) -> None:
    suffix = Path(filename or "").suffix.lower()
    valid_content_types = {"application/pdf", "application/octet-stream"}
    if suffix != ".pdf" or (content_type and content_type.lower() not in valid_content_types):
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


async def _read_supporting_pdfs(uploads: list[UploadFile]) -> list[dict[str, Any]]:
    if not uploads:
        raise HTTPException(status_code=422, detail="Adjunte al menos un documento PDF de respaldo.")
    if len(uploads) > _MAX_SUPPORTING_FILES:
        for upload in uploads:
            await upload.close()
        raise HTTPException(
            status_code=422,
            detail=f"Puede adjuntar hasta {_MAX_SUPPORTING_FILES} documentos PDF por solicitud.",
        )

    documents: list[dict[str, Any]] = []
    hashes: set[str] = set()
    total_size = 0
    try:
        for order, upload in enumerate(uploads, start=1):
            original_filename, content = await read_secure_upload(
                upload,
                maximum=_MAX_DOCUMENT_BYTES,
                label="archivo PDF",
                allowed_extensions={".pdf"},
                allowed_content_types={"application/pdf", "application/octet-stream"},
            )
            content_type = "application/pdf"
            _validate_pdf_content(original_filename, content_type, content)
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                raise HTTPException(
                    status_code=422,
                    detail=f"El archivo {original_filename} está repetido en la selección.",
                )
            hashes.add(digest)
            total_size += len(content)
            if total_size > _MAX_TOTAL_DOCUMENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="La carga completa de documentos supera el límite de 100 MB.",
                )
            documents.append(
                {
                    "orden": order,
                    "nombre_original": original_filename[:260],
                    "sha256": digest,
                    "tamano": len(content),
                    "contenido": content,
                }
            )
    finally:
        for upload in uploads:
            await upload.close()
    return documents


def _require_reviewer(user: SessionUser) -> None:
    if user.rol.upper() not in _REVIEW_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Solo Académico o Administrador puede aprobar y aplicar la solicitud.",
        )


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

                IF OBJECT_ID(N'sol.SolicitudCambioModalidad', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.SolicitudCambioModalidad
                    (
                        IdSolicitud BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_SolicitudCambioModalidad PRIMARY KEY,
                        CodigoEstud INT NOT NULL,
                        Cedula NVARCHAR(32) NOT NULL,
                        Estudiante NVARCHAR(250) NOT NULL,
                        CarreraOrigen INT NOT NULL,
                        CarreraOrigenNombre NVARCHAR(250) NOT NULL,
                        CarreraDestino INT NOT NULL,
                        CarreraDestinoNombre NVARCHAR(250) NOT NULL,
                        ModalidadOrigen INT NULL,
                        ModalidadOrigenNombre NVARCHAR(150) NULL,
                        CodigoPeriodoOrigen INT NOT NULL,
                        PeriodoOrigenNombre NVARCHAR(250) NOT NULL,
                        TipoPeriodoOrigen NCHAR(1) NOT NULL,
                        ModalidadDestino INT NOT NULL,
                        ModalidadDestinoNombre NVARCHAR(150) NOT NULL,
                        CodigoPeriodoHomologacion INT NOT NULL,
                        PeriodoHomologacionNombre NVARCHAR(250) NOT NULL,
                        TipoPeriodoDestino NCHAR(1) NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_TipoPeriodo DEFAULT N'H',
                        Estado NVARCHAR(20) NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Estado DEFAULT N'PENDIENTE',
                        Motivo NVARCHAR(1000) NOT NULL,
                        ArchivoNombre NVARCHAR(260) NOT NULL,
                        ArchivoRuta NVARCHAR(600) NOT NULL,
                        ArchivoSha256 CHAR(64) NOT NULL,
                        ArchivoTamano BIGINT NOT NULL,
                        GraphDocumentoId BIGINT NULL,
                        GraphWebUrl NVARCHAR(1200) NULL,
                        EstadoExpediente NVARCHAR(30) NULL,
                        TotalMateriasPensum INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Total DEFAULT 0,
                        MateriasMatriculadas INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Matriculadas DEFAULT 0,
                        MateriasExistentes INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Existentes DEFAULT 0,
                        MateriasMigradas INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Migradas DEFAULT 0,
                        MateriasOrigenRetiradas INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_MateriasRetiradas DEFAULT 0,
                        CabecerasOrigenRetiradas INT NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_CabecerasRetiradas DEFAULT 0,
                        CabeceraCreada BIT NULL,
                        CreadoPor NVARCHAR(256) NOT NULL,
                        FechaCreacion DATETIME2 NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidad_Fecha DEFAULT SYSUTCDATETIME(),
                        RevisadoPor NVARCHAR(256) NULL,
                        FechaRevision DATETIME2 NULL,
                        ObservacionRevision NVARCHAR(1000) NULL,
                        AplicadoPor NVARCHAR(256) NULL,
                        FechaAplicacion DATETIME2 NULL,
                        CONSTRAINT CK_SolicitudCambioModalidad_Estado
                            CHECK (Estado IN (N'PENDIENTE', N'APROBADA', N'RECHAZADA', N'APLICADA')),
                        CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodo
                            CHECK (TipoPeriodoDestino IN (N'R', N'H')),
                        CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodoOrigen
                            CHECK (TipoPeriodoOrigen IN (N'R', N'H'))
                    );
                    CREATE INDEX IX_SolicitudCambioModalidad_Estudiante
                        ON sol.SolicitudCambioModalidad(CodigoEstud, FechaCreacion DESC);
                    CREATE INDEX IX_SolicitudCambioModalidad_Estado
                        ON sol.SolicitudCambioModalidad(Estado, FechaCreacion DESC);
                END;

                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'TipoPeriodoDestino') IS NULL
                BEGIN
                    ALTER TABLE sol.SolicitudCambioModalidad
                    ADD TipoPeriodoDestino NCHAR(1) NOT NULL
                        CONSTRAINT DF_SolicitudCambioModalidad_TipoPeriodo DEFAULT N'H' WITH VALUES;
                END;

                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'CodigoPeriodoOrigen') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD CodigoPeriodoOrigen INT NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'PeriodoOrigenNombre') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD PeriodoOrigenNombre NVARCHAR(250) NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'TipoPeriodoOrigen') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD TipoPeriodoOrigen NCHAR(1) NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'MateriasMigradas') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD MateriasMigradas INT NOT NULL
                        CONSTRAINT DF_SolicitudCambioModalidad_Migradas DEFAULT 0 WITH VALUES;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'MateriasOrigenRetiradas') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD MateriasOrigenRetiradas INT NOT NULL
                        CONSTRAINT DF_SolicitudCambioModalidad_MateriasRetiradas DEFAULT 0 WITH VALUES;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'CabecerasOrigenRetiradas') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidad ADD CabecerasOrigenRetiradas INT NOT NULL
                        CONSTRAINT DF_SolicitudCambioModalidad_CabecerasRetiradas DEFAULT 0 WITH VALUES;

                IF NOT EXISTS
                (
                    SELECT 1
                    FROM sys.check_constraints
                    WHERE parent_object_id = OBJECT_ID(N'sol.SolicitudCambioModalidad')
                      AND name = N'CK_SolicitudCambioModalidad_TipoPeriodo'
                )
                BEGIN
                    EXEC
                    (
                        N'ALTER TABLE sol.SolicitudCambioModalidad '
                        + N'ADD CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodo '
                        + N'CHECK (TipoPeriodoDestino IN (N''R'', N''H''));'
                    );
                END;

                IF OBJECT_ID(N'sol.SolicitudCambioModalidadMateria', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.SolicitudCambioModalidadMateria
                    (
                        IdDetalle BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_SolicitudCambioModalidadMateria PRIMARY KEY,
                        IdSolicitud BIGINT NOT NULL,
                        CodigoMateria INT NOT NULL,
                        CodigoComun NVARCHAR(100) NULL,
                        NombreMateria NVARCHAR(300) NOT NULL,
                        Nivel INT NULL,
                        Creditos DECIMAL(8,2) NULL,
                        MateriaOrigen INT NULL,
                        CodigoComunOrigen NVARCHAR(100) NULL,
                        NotaOrigen DECIMAL(18,3) NULL,
                        Estado NVARCHAR(20) NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidadMateria_Estado DEFAULT N'PENDIENTE',
                        NumMatricula INT NULL,
                        Observacion NVARCHAR(500) NULL,
                        CONSTRAINT FK_SolicitudCambioModalidadMateria_Solicitud
                            FOREIGN KEY (IdSolicitud)
                            REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
                        CONSTRAINT UQ_SolicitudCambioModalidadMateria
                            UNIQUE (IdSolicitud, CodigoMateria),
                        CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado
                            CHECK (Estado IN (N'PENDIENTE', N'EXISTENTE', N'MATRICULADA', N'MIGRADA'))
                    );
                END;

                IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'MateriaOrigen') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD MateriaOrigen INT NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'CodigoComunOrigen') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD CodigoComunOrigen NVARCHAR(100) NULL;
                IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'NotaOrigen') IS NULL
                    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD NotaOrigen DECIMAL(18,3) NULL;

                IF EXISTS
                (
                    SELECT 1
                    FROM sys.check_constraints
                    WHERE parent_object_id = OBJECT_ID(N'sol.SolicitudCambioModalidadMateria')
                      AND name = N'CK_SolicitudCambioModalidadMateria_Estado'
                      AND definition NOT LIKE N'%MIGRADA%'
                )
                BEGIN
                    ALTER TABLE sol.SolicitudCambioModalidadMateria
                        DROP CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado;
                    ALTER TABLE sol.SolicitudCambioModalidadMateria
                        ADD CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado
                        CHECK (Estado IN (N'PENDIENTE', N'EXISTENTE', N'MATRICULADA', N'MIGRADA'));
                END;

                IF OBJECT_ID(N'sol.SolicitudCambioModalidadArchivo', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.SolicitudCambioModalidadArchivo
                    (
                        IdArchivo BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_SolicitudCambioModalidadArchivo PRIMARY KEY,
                        IdSolicitud BIGINT NOT NULL,
                        Orden INT NOT NULL,
                        ArchivoNombreOriginal NVARCHAR(260) NOT NULL,
                        ArchivoNombreNube NVARCHAR(260) NULL,
                        ArchivoRuta NVARCHAR(600) NULL,
                        ArchivoSha256 CHAR(64) NOT NULL,
                        ArchivoTamano BIGINT NOT NULL,
                        GraphDocumentoId BIGINT NULL,
                        GraphWebUrl NVARCHAR(1200) NULL,
                        EstadoExpediente NVARCHAR(30) NOT NULL
                            CONSTRAINT DF_SolicitudCambioModalidadArchivo_Estado DEFAULT N'PENDIENTE',
                        FechaCarga DATETIME2(3) NULL,
                        CONSTRAINT FK_SolicitudCambioModalidadArchivo_Solicitud
                            FOREIGN KEY (IdSolicitud)
                            REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
                        CONSTRAINT UQ_SolicitudCambioModalidadArchivo_Orden
                            UNIQUE (IdSolicitud, Orden),
                        CONSTRAINT CK_SolicitudCambioModalidadArchivo_Estado
                            CHECK (EstadoExpediente IN (N'PENDIENTE', N'CARGADO', N'ERROR')),
                        CONSTRAINT CK_SolicitudCambioModalidadArchivo_Tamano
                            CHECK (ArchivoTamano > 0)
                    );
                    CREATE INDEX IX_SolicitudCambioModalidadArchivo_Solicitud
                        ON sol.SolicitudCambioModalidadArchivo(IdSolicitud, Orden);
                END;

                IF OBJECT_ID(N'sol.RespaldoCambioModalidad', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.RespaldoCambioModalidad
                    (
                        IdRespaldo BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_RespaldoCambioModalidad PRIMARY KEY,
                        IdSolicitud BIGINT NOT NULL,
                        CodigoEstud INT NOT NULL,
                        CarreraOrigen INT NOT NULL,
                        CarreraDestino INT NOT NULL,
                        PeriodoOrigen INT NOT NULL,
                        PeriodoDestino INT NOT NULL,
                        ModalidadOrigen INT NULL,
                        ModalidadDestino INT NOT NULL,
                        TotalCabeceras INT NOT NULL,
                        TotalMaterias INT NOT NULL,
                        HashContenido CHAR(64) NOT NULL,
                        FechaRespaldo DATETIME2(3) NOT NULL
                            CONSTRAINT DF_RespaldoCambioModalidad_Fecha DEFAULT SYSUTCDATETIME(),
                        RespaldadoPor NVARCHAR(256) NOT NULL,
                        CONSTRAINT FK_RespaldoCambioModalidad_Solicitud
                            FOREIGN KEY (IdSolicitud)
                            REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
                        CONSTRAINT UQ_RespaldoCambioModalidad_Solicitud UNIQUE (IdSolicitud)
                    );
                END;

                IF OBJECT_ID(N'sol.RespaldoCambioModalidadFila', N'U') IS NULL
                BEGIN
                    CREATE TABLE sol.RespaldoCambioModalidadFila
                    (
                        IdFila BIGINT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_RespaldoCambioModalidadFila PRIMARY KEY,
                        IdRespaldo BIGINT NOT NULL,
                        TipoRegistro NVARCHAR(20) NOT NULL,
                        ClaveNatural NVARCHAR(600) NOT NULL,
                        DatosJson NVARCHAR(MAX) NOT NULL,
                        Sha256 CHAR(64) NOT NULL,
                        CONSTRAINT FK_RespaldoCambioModalidadFila_Respaldo
                            FOREIGN KEY (IdRespaldo)
                            REFERENCES sol.RespaldoCambioModalidad(IdRespaldo),
                        CONSTRAINT UQ_RespaldoCambioModalidadFila_Registro
                            UNIQUE (IdRespaldo, TipoRegistro, ClaveNatural),
                        CONSTRAINT CK_RespaldoCambioModalidadFila_Tipo
                            CHECK (TipoRegistro IN (N'CABECERA', N'MATERIA'))
                    );
                    CREATE INDEX IX_RespaldoCambioModalidadFila_Respaldo
                        ON sol.RespaldoCambioModalidadFila(IdRespaldo, TipoRegistro);
                END;
                """
            )
            ensure_academic_movement_audit_schema(cursor)
            conn.commit()
        _schema_ready = True


def _fetch_student_context(cursor: pyodbc.Cursor, codigo_estud: int) -> dict[str, Any]:
    cursor.execute(
        """
        WITH ultima_cabecera AS
        (
            SELECT
                cab.codigo_estud,
                TRY_CONVERT(int, cab.cod_anio_Basica) AS carrera,
                TRY_CONVERT(int, cab.codigo_periodo) AS periodo,
                NULLIF(TRY_CONVERT(int, cab.codmodalidad), 0) AS modalidad,
                NULLIF(TRY_CONVERT(int, cab.codjornada), 0) AS jornada_codigo,
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), cab.Jornada))), N'') AS jornada_nombre,
                ROW_NUMBER() OVER
                (
                    PARTITION BY cab.codigo_estud
                    ORDER BY
                        TRY_CONVERT(int, cab.codigo_periodo) DESC,
                        TRY_CONVERT(bigint, cab.numcodigo) DESC
                ) AS fila
            FROM dbo.CABECERA_MATRICULA cab
            WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
        ),
        ultima_materia AS
        (
            SELECT
                cxe.codigo_estud,
                TRY_CONVERT(int, cxe.cod_anio_Basica) AS carrera,
                TRY_CONVERT(int, cxe.codigo_periodo) AS periodo,
                ROW_NUMBER() OVER
                (
                    PARTITION BY cxe.codigo_estud
                    ORDER BY
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
            COALESCE(uc.carrera, um.carrera) AS carrera,
            TRY_CONVERT(nvarchar(250), c.Nombre_Basica) AS carrera_nombre,
            COALESCE(uc.periodo, um.periodo) AS periodo,
            TRY_CONVERT(nvarchar(250), periodo.Detalle_Periodo) AS periodo_nombre,
            UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula)))) AS tipo_periodo,
            uc.modalidad AS modalidad_cabecera,
            uc.jornada_codigo,
            uc.jornada_nombre,
            TRY_CONVERT(int, d.ModalidadEstudio) AS modalidad_estudiante
        FROM dbo.DATOS_ESTUD d
        LEFT JOIN ultima_cabecera uc ON uc.codigo_estud = d.codigo_estud AND uc.fila = 1
        LEFT JOIN ultima_materia um ON um.codigo_estud = d.codigo_estud AND um.fila = 1
        LEFT JOIN dbo.CARRERAS c
          ON TRY_CONVERT(int, c.Cod_AnioBasica) = COALESCE(uc.carrera, um.carrera)
        LEFT JOIN dbo.PERIODO periodo
          ON TRY_CONVERT(int, periodo.cod_periodo) = COALESCE(uc.periodo, um.periodo)
        WHERE TRY_CONVERT(int, d.codigo_estud) = ?
        """,
        codigo_estud,
        codigo_estud,
        codigo_estud,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el estudiante seleccionado.")
    career_code = _int_value(row.carrera)
    if career_code is None:
        raise HTTPException(status_code=409, detail="El estudiante no tiene una carrera registrada.")
    modality_code = _int_value(row.modalidad_cabecera)
    if modality_code is None:
        modality_code = _ENROLLMENT_MODALITY_BY_STUDENT.get(
            _int_value(row.modalidad_estudiante) or 0
        )
    modality_name = ""
    if modality_code is not None:
        cursor.execute(
            """
            SELECT TOP (1) TRY_CONVERT(nvarchar(150), DetalleM)
            FROM dbo.ModalidadMatricula
            WHERE TRY_CONVERT(int, NumM) = ?
            """,
            modality_code,
        )
        modality_row = cursor.fetchone()
        modality_name = _clean(modality_row[0]) if modality_row else ""
    return {
        "codigo_estud": int(row.codigo_estud),
        "cedula": _clean(row.cedula),
        "estudiante": _clean(row.estudiante),
        "estado": _clean(row.estado),
        "correo": _clean(row.correo),
        "carrera": career_code,
        "carrera_nombre": _clean(row.carrera_nombre),
        "periodo": _int_value(row.periodo),
        "periodo_nombre": _clean(row.periodo_nombre),
        "tipo_periodo": _clean(row.tipo_periodo).upper(),
        "modalidad": modality_code,
        "modalidad_nombre": modality_name,
        "jornada_codigo": _int_value(row.jornada_codigo),
        "jornada_nombre": _clean(row.jornada_nombre),
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
        raise HTTPException(status_code=404, detail="No se encontró la carrera seleccionada.")
    if _clean(row.estado).upper() not in {"", "A"}:
        raise HTTPException(status_code=409, detail="La carrera seleccionada no está activa.")
    return {"codigo": int(row.codigo), "nombre": _clean(row.nombre)}


def _fetch_modality(cursor: pyodbc.Cursor, modality_code: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, modalidad.NumM) AS codigo,
            TRY_CONVERT(nvarchar(150), modalidad.DetalleM) AS nombre,
            TRY_CONVERT(int, jornada.NumJ) AS jornada_codigo,
            TRY_CONVERT(nvarchar(100), jornada.DetalleJ) AS jornada_nombre
        FROM dbo.ModalidadMatricula modalidad
        OUTER APPLY
        (
            SELECT TOP (1) NumJ, DetalleJ
            FROM dbo.JORNADA
            WHERE TRY_CONVERT(int, codmodalidad) = TRY_CONVERT(int, modalidad.NumM)
            ORDER BY TRY_CONVERT(int, NumJ)
        ) jornada
        WHERE TRY_CONVERT(int, modalidad.NumM) = ?
        """,
        modality_code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró la modalidad seleccionada.")
    return {
        "codigo": int(row.codigo),
        "nombre": _clean(row.nombre),
        "jornada_codigo": _int_value(row.jornada_codigo) or 0,
        "jornada_nombre": _clean(row.jornada_nombre),
    }


def _inherited_modality(
    cursor: pyodbc.Cursor,
    student: dict[str, Any],
) -> dict[str, Any]:
    modality_code = _int_value(student.get("modalidad"))
    if modality_code is None:
        raise HTTPException(
            status_code=409,
            detail="La matrícula del período anterior no tiene una modalidad registrada.",
        )
    inherited = _fetch_modality(cursor, modality_code)
    source_journey_code = _int_value(student.get("jornada_codigo"))
    source_journey_name = _clean(student.get("jornada_nombre"))
    if source_journey_code is not None:
        inherited["jornada_codigo"] = source_journey_code
    if source_journey_name:
        inherited["jornada_nombre"] = source_journey_name
    return inherited


def _fetch_enrollment_period(cursor: pyodbc.Cursor, period_code: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, cod_periodo) AS codigo,
            TRY_CONVERT(nvarchar(250), Detalle_Periodo) AS nombre,
            TRY_CONVERT(nvarchar(10), TipoMatricula) AS tipo,
            TRY_CONVERT(nvarchar(10), Estado) AS estado,
            fechain,
            fechafin
        FROM dbo.PERIODO
        WHERE TRY_CONVERT(int, cod_periodo) = ?
        """,
        period_code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el período seleccionado.")
    period_type = _clean(row.tipo).upper()
    if period_type not in _VALID_PERIOD_TYPES:
        raise HTTPException(
            status_code=409,
            detail="El período seleccionado debe ser regular o de homologación.",
        )
    return {
        "codigo": int(row.codigo),
        "nombre": _clean(row.nombre),
        "tipo": period_type,
        "estado": _clean(row.estado),
        "fecha_inicio": row.fechain.isoformat() if row.fechain else None,
        "fecha_fin": row.fechafin.isoformat() if row.fechafin else None,
    }


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
          AND ISNULL(LTRIM(RTRIM(estado_mat)), '') IN ('', 'A')
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
            "creditos": _float_value(row.creditos),
        }
        for row in cursor.fetchall()
    ]


def _effective_grade(data: dict[str, Any], period_type: str) -> float | None:
    for field in ("PromedioFinal", "Promedio", "PromedioAux"):
        value = _optional_float(data.get(field))
        if value is not None:
            return value

    theory = _optional_float(data.get("teoriaHomo"))
    practice = _optional_float(data.get("practicahomo"))
    if period_type == "H" and (theory is not None or practice is not None):
        return round(
            (theory or 0.0) * _HOMOLOGATION_THEORY_WEIGHT
            + (practice or 0.0) * _HOMOLOGATION_PRACTICE_WEIGHT,
            3,
        )

    partials = [
        _optional_float(data.get("promP1")),
        _optional_float(data.get("promP2")),
        _optional_float(data.get("promP3")),
    ]
    available_partials = [value for value in partials if value is not None]
    if available_partials:
        return round(sum(available_partials) / len(available_partials), 3)

    recovery = _optional_float(data.get("Recuperacion"))
    if recovery is not None:
        return recovery
    return None


def _project_final_grade_to_homologation(final_grade: float) -> tuple[float, float, float]:
    """Use the final grade as both base scores so their 40/60 result is unchanged."""
    component_grade = round(float(final_grade), 3)
    projected_final = round(
        component_grade * _HOMOLOGATION_THEORY_WEIGHT
        + component_grade * _HOMOLOGATION_PRACTICE_WEIGHT,
        3,
    )
    return component_grade, component_grade, projected_final


def _has_grades(data: dict[str, Any]) -> bool:
    return any(_optional_float(data.get(field)) is not None for field in _GRADE_FIELDS)


def _is_approved_grade(value: Any) -> bool:
    grade = _optional_float(value)
    return grade is not None and grade >= _PASSING_GRADE


def _is_failed_grade(value: Any) -> bool:
    grade = _optional_float(value)
    return grade is not None and grade < _PASSING_GRADE


def _fetch_source_enrollments(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    career_code: int,
    period_code: int,
    period_type: str,
) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            cxe.*,
            TRY_CONVERT(nvarchar(100), pensum.cod_materia) AS __codigo_comun,
            TRY_CONVERT(nvarchar(300), pensum.Nomb_Materia) AS __nombre_materia
        FROM dbo.CARRERAXESTUD cxe WITH (HOLDLOCK)
        LEFT JOIN dbo.PENSUM pensum
          ON TRY_CONVERT(int, pensum.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
         AND TRY_CONVERT(int, pensum.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
          AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
          AND TRY_CONVERT(int, cxe.codigo_periodo) = ?
        ORDER BY TRY_CONVERT(int, cxe.codigo_materia), TRY_CONVERT(bigint, cxe.num)
        """,
        codigo_estud,
        career_code,
        period_code,
    )
    result: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        data = cursor_row_dict(cursor, row)
        common_code = _clean(data.pop("__codigo_comun", ""))
        subject_name = _clean(data.pop("__nombre_materia", ""))
        result.append(
            {
                "data": data,
                "codigo_materia": _int_value(data.get("codigo_materia")),
                "codigo_comun": common_code,
                "codigo_normalizado": _normalize_common_code(common_code),
                "nombre": subject_name,
                "nota_final": _effective_grade(data, period_type),
                "tiene_notas": _has_grades(data),
                "num": _int_value(data.get("num")) or 0,
            }
        )
    return result


def _best_sources_by_common_code(
    source_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for source in source_rows:
        code = _clean(source.get("codigo_normalizado"))
        if not code:
            continue
        current = best.get(code)
        source_data = source["data"]
        rank = (
            source.get("nota_final") is not None,
            source.get("nota_final") if source.get("nota_final") is not None else -1.0,
            sum(_optional_float(source_data.get(field)) is not None for field in _GRADE_FIELDS),
            int(source.get("num") or 0),
        )
        if current is None:
            best[code] = source
            continue
        current_data = current["data"]
        current_rank = (
            current.get("nota_final") is not None,
            current.get("nota_final") if current.get("nota_final") is not None else -1.0,
            sum(_optional_float(current_data.get(field)) is not None for field in _GRADE_FIELDS),
            int(current.get("num") or 0),
        )
        if rank > current_rank:
            best[code] = source
    return best


def _build_subject_migration_plan(
    *,
    target_subjects: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    existing: dict[int, int],
    target_period_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources_by_code = _best_sources_by_common_code(source_rows)
    matched_source_numbers: set[int] = set()
    planned: list[dict[str, Any]] = []
    for subject in target_subjects:
        common_code = _normalize_common_code(subject.get("codigo_comun"))
        matching_source = sources_by_code.get(common_code) if common_code else None
        source = matching_source if matching_source and _is_approved_grade(
            matching_source.get("nota_final")
        ) else None
        subject_code = int(subject["codigo_materia"])
        already_exists = subject_code in existing
        if target_period_type == "R" and matching_source is None and not already_exists:
            continue
        if matching_source is not None:
            matched_source_numbers.add(int(matching_source.get("num") or 0))
        if source is not None:
            planned_state = "MIGRAR"
        elif already_exists:
            planned_state = "EXISTENTE"
        elif matching_source is not None and _is_failed_grade(
            matching_source.get("nota_final")
        ):
            planned_state = "REPETIR"
        else:
            planned_state = "MATRICULAR"
        planned.append(
            {
                **subject,
                "estado": planned_state,
                "num_matricula": existing.get(subject_code),
                "materia_origen": source.get("codigo_materia") if source else None,
                "codigo_comun_origen": (
                    matching_source.get("codigo_comun", "") if matching_source else ""
                ),
                "nota_origen": (
                    matching_source.get("nota_final") if matching_source else None
                ),
                "tiene_notas_origen": bool(
                    matching_source and matching_source.get("tiene_notas")
                ),
                "requiere_repeticion": planned_state == "REPETIR",
            }
        )
    unmatched = [
        source
        for source in source_rows
        if int(source.get("num") or 0) not in matched_source_numbers
    ]
    return planned, unmatched


def _existing_target_subjects(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    career_code: int,
    period_code: int,
) -> dict[int, int]:
    cursor.execute(
        """
        SELECT
            TRY_CONVERT(int, codigo_materia) AS codigo_materia,
            MAX(TRY_CONVERT(int, Num_Matricula)) AS num_matricula
        FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        GROUP BY TRY_CONVERT(int, codigo_materia)
        """,
        codigo_estud,
        career_code,
        period_code,
    )
    return {
        int(row.codigo_materia): int(row.num_matricula or 1)
        for row in cursor.fetchall()
        if _int_value(row.codigo_materia) is not None
    }


def _preview_with_cursor(
    cursor: pyodbc.Cursor,
    payload: ModalityChangePreviewPayload,
) -> dict[str, Any]:
    student = _fetch_student_context(cursor, payload.codigo_estud)
    target_career = _fetch_career(cursor, payload.carrera_destino)
    target_modality = _inherited_modality(cursor, student)
    target_period = _fetch_enrollment_period(cursor, payload.codigo_periodo_homologacion)
    source_period_code = _int_value(student.get("periodo"))
    if source_period_code is None:
        raise HTTPException(
            status_code=409,
            detail="El estudiante no tiene un período de matrícula de origen.",
        )
    if source_period_code == target_period["codigo"]:
        raise HTTPException(
            status_code=409,
            detail="El período de destino debe ser diferente del período de matrícula actual.",
        )
    source_period = _fetch_enrollment_period(cursor, source_period_code)
    source_rows = _fetch_source_enrollments(
        cursor,
        student["codigo_estud"],
        student["carrera"],
        source_period["codigo"],
        source_period["tipo"],
    )
    if not source_rows:
        raise HTTPException(
            status_code=409,
            detail="No existen materias en el período de origen para realizar la migración.",
        )
    target_subjects = _fetch_target_subjects(cursor, target_career["codigo"])
    if not target_subjects:
        raise HTTPException(status_code=409, detail="La carrera seleccionada no tiene un pénsum activo.")
    existing = _existing_target_subjects(
        cursor,
        student["codigo_estud"],
        target_career["codigo"],
        target_period["codigo"],
    )
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM dbo.CABECERA_MATRICULA
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        """,
        student["codigo_estud"],
        target_career["codigo"],
        target_period["codigo"],
    )
    header_exists = int(cursor.fetchone()[0] or 0) > 0
    planned_subjects, unmatched_sources = _build_subject_migration_plan(
        target_subjects=target_subjects,
        source_rows=source_rows,
        existing=existing,
        target_period_type=target_period["tipo"],
    )
    if not planned_subjects:
        raise HTTPException(
            status_code=409,
            detail=(
                "No existen materias con el mismo código único entre el período de origen "
                "y el pénsum de destino."
            ),
        )
    return {
        "student": student,
        "target_career": target_career,
        "target_modality": target_modality,
        "source_period": source_period,
        "homologation_period": target_period,
        "subjects": planned_subjects,
        "unmatched_source_subjects": [
            {
                "codigo_materia": source["codigo_materia"],
                "codigo_comun": source["codigo_comun"],
                "nombre": source["nombre"],
                "nota_final": source["nota_final"],
                "tiene_notas": source["tiene_notas"],
            }
            for source in unmatched_sources
        ],
        "summary": {
            "materias_pensum": len(planned_subjects),
            "materias_origen": len(source_rows),
            "materias_a_migrar": sum(
                1 for item in planned_subjects if item["estado"] == "MIGRAR"
            ),
            "materias_por_matricular": sum(1 for item in planned_subjects if item["estado"] == "MATRICULAR"),
            "materias_por_repetir": sum(
                1 for item in planned_subjects if item["estado"] == "REPETIR"
            ),
            "materias_existentes": sum(1 for item in planned_subjects if item["estado"] == "EXISTENTE"),
            "materias_origen_sin_coincidencia": len(unmatched_sources),
            "cabecera_existente": header_exists,
            "cabeceras_a_crear": 0 if header_exists else 1,
        },
    }


def _archive_supporting_document(
    *,
    request_id: int,
    file_order: int,
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
            table_origin="SolicitudCambioModalidad",
            origin_id=request_id,
            expedient_code=f"CAMBIO-MODALIDAD-{request_id}",
            audit_user=audit_user,
        )
        upload_folder = f"{graph_expedient['folder_path']}/CAMBIO DE MODALIDAD"
        ensure_folder(upload_folder)
        cloud_filename = (
            f"RESPALDO-CAMBIO-MODALIDAD-{request_id}-{file_order:02d}-"
            f"{_safe_filename(original_filename)}"
        )
        graph_path = f"{upload_folder}/{cloud_filename}"
        register_upload_session(
            session_id=session_id,
            expedient_graph_id=int(graph_expedient["expedient_graph_id"]),
            document_type_code="RESPALDO_CAMBIO_MODALIDAD",
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
            append_document=True,
        )
        document_id = int(graph_document["document_graph_id"])
        set_document_origin(document_id, request_id)
        return {
            "document_id": document_id,
            "web_url": _clean(graph_document.get("graph_web_url")),
            "graph_path": graph_path,
            "cloud_filename": cloud_filename,
            "graph_item_id": _clean(graph_document.get("graph_item_id"))
            or _clean(graph_item.get("id")),
        }
    except Exception:
        if session_registered:
            try:
                mark_upload_error(
                    session_id,
                    "No se pudo archivar el respaldo de cambio de modalidad.",
                    audit_user,
                )
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
            "DELETE FROM sol.SolicitudCambioModalidadArchivo WHERE IdSolicitud = ?",
            request_id,
        )
        cursor.execute(
            "DELETE FROM sol.SolicitudCambioModalidadMateria WHERE IdSolicitud = ?",
            request_id,
        )
        cursor.execute(
            "DELETE FROM sol.SolicitudCambioModalidad WHERE IdSolicitud = ?",
            request_id,
        )
        conn.commit()


def _delete_unarchived_request_safely(request_id: int) -> None:
    try:
        _delete_unarchived_request(request_id)
    except (RuntimeError, pyodbc.Error):
        pass


def _delete_archived_documents_safely(documents: list[dict[str, Any]]) -> None:
    for document in reversed(documents):
        graph_item_id = _clean(document.get("graph_item_id"))
        if not graph_item_id:
            continue
        try:
            delete_item(graph_item_id)
        except (httpx.HTTPError, RuntimeError):
            pass


def _request_documents(row: Any, legacy_url: str) -> list[dict[str, Any]]:
    try:
        raw_documents = json.loads(_clean(getattr(row, "ArchivosJson", "")) or "[]")
    except (TypeError, json.JSONDecodeError):
        raw_documents = []

    documents: list[dict[str, Any]] = []
    for item in raw_documents if isinstance(raw_documents, list) else []:
        if not isinstance(item, dict):
            continue
        stored_path = _clean(item.get("ruta")).replace(chr(92), "/")
        is_legacy_path = (
            bool(stored_path)
            and stored_path != "PENDIENTE_EXPEDIENTE"
            and not stored_path.startswith("EXPEDIENTES ESTUDIANTILES/")
        )
        graph_url = _clean(item.get("url"))
        documents.append(
            {
                "id": _int_value(item.get("id")),
                "orden": _int_value(item.get("orden")) or len(documents) + 1,
                "nombre_original": _clean(item.get("nombre_original")),
                "nombre": _clean(item.get("nombre")) or _clean(item.get("nombre_original")),
                "archivo_url": graph_url
                or (f"/uploads/{stored_path}" if is_legacy_path else ""),
                "expediente_documento_id": _int_value(item.get("documento_id")),
                "estado": _clean(item.get("estado")),
                "tamano": _int_value(item.get("tamano")) or 0,
                "sha256": _clean(item.get("sha256")),
                "fecha_carga": _clean(item.get("fecha_carga")) or None,
            }
        )

    legacy_name = _clean(getattr(row, "ArchivoNombre", ""))
    if not documents and legacy_name:
        documents.append(
            {
                "id": None,
                "orden": 1,
                "nombre_original": legacy_name,
                "nombre": legacy_name,
                "archivo_url": legacy_url,
                "expediente_documento_id": _int_value(
                    getattr(row, "GraphDocumentoId", None)
                ),
                "estado": _clean(getattr(row, "EstadoExpediente", "")),
                "tamano": _int_value(getattr(row, "ArchivoTamano", None)) or 0,
                "sha256": _clean(getattr(row, "ArchivoSha256", "")),
                "fecha_carga": None,
            }
        )
    return documents


def _row_to_request(row: Any) -> dict[str, Any]:
    graph_url = _clean(getattr(row, "GraphWebUrl", ""))
    stored_path = _clean(row.ArchivoRuta).replace(chr(92), "/")
    is_legacy_path = (
        bool(stored_path)
        and stored_path != "PENDIENTE_EXPEDIENTE"
        and not stored_path.startswith("EXPEDIENTES ESTUDIANTILES/")
    )
    legacy_url = graph_url or (f"/uploads/{stored_path}" if is_legacy_path else "")
    documents = _request_documents(row, legacy_url)
    return {
        "id": int(row.IdSolicitud),
        "codigo_estud": int(row.CodigoEstud),
        "cedula": _clean(row.Cedula),
        "estudiante": _clean(row.Estudiante),
        "carrera_origen": int(row.CarreraOrigen),
        "carrera_origen_nombre": _clean(row.CarreraOrigenNombre),
        "carrera_destino": int(row.CarreraDestino),
        "carrera_destino_nombre": _clean(row.CarreraDestinoNombre),
        "modalidad_origen": _int_value(row.ModalidadOrigen),
        "modalidad_origen_nombre": _clean(row.ModalidadOrigenNombre),
        "codigo_periodo_origen": _int_value(getattr(row, "CodigoPeriodoOrigen", None)),
        "periodo_origen_nombre": _clean(getattr(row, "PeriodoOrigenNombre", "")),
        "tipo_periodo_origen": _clean(getattr(row, "TipoPeriodoOrigen", "")).upper(),
        "modalidad_destino": int(row.ModalidadDestino),
        "modalidad_destino_nombre": _clean(row.ModalidadDestinoNombre),
        "codigo_periodo_homologacion": int(row.CodigoPeriodoHomologacion),
        "periodo_homologacion_nombre": _clean(row.PeriodoHomologacionNombre),
        "tipo_periodo_destino": _clean(row.TipoPeriodoDestino).upper(),
        "estado": _clean(row.Estado),
        "motivo": _clean(row.Motivo),
        "archivo_nombre": _clean(row.ArchivoNombre),
        "archivo_url": legacy_url,
        "expediente_documento_id": _int_value(getattr(row, "GraphDocumentoId", None)),
        "archivo_en_expediente": _int_value(getattr(row, "GraphDocumentoId", None)) is not None,
        "estado_expediente": _clean(getattr(row, "EstadoExpediente", "")),
        "archivos": documents,
        "total_archivos": len(documents),
        "total_materias_pensum": int(row.TotalMateriasPensum or 0),
        "materias_matriculadas": int(row.MateriasMatriculadas or 0),
        "materias_existentes": int(row.MateriasExistentes or 0),
        "materias_migradas": int(getattr(row, "MateriasMigradas", 0) or 0),
        "materias_origen_retiradas": int(
            getattr(row, "MateriasOrigenRetiradas", 0) or 0
        ),
        "cabeceras_origen_retiradas": int(
            getattr(row, "CabecerasOrigenRetiradas", 0) or 0
        ),
        "cabecera_creada": bool(row.CabeceraCreada) if row.CabeceraCreada is not None else None,
        "respaldo_id": _int_value(getattr(row, "RespaldoId", None)),
        "respaldo_cabeceras": int(getattr(row, "RespaldoCabeceras", 0) or 0),
        "respaldo_materias": int(getattr(row, "RespaldoMaterias", 0) or 0),
        "respaldo_hash": _clean(getattr(row, "RespaldoHash", "")),
        "fecha_respaldo": (
            row.FechaRespaldo.isoformat() if getattr(row, "FechaRespaldo", None) else None
        ),
        "auditoria_id": _int_value(getattr(row, "AuditoriaId", None)),
        "auditoria_hash": _clean(getattr(row, "AuditoriaHash", "")),
        "creado_por": _clean(row.CreadoPor),
        "fecha_creacion": row.FechaCreacion.isoformat() if row.FechaCreacion else None,
        "revisado_por": _clean(row.RevisadoPor),
        "fecha_revision": row.FechaRevision.isoformat() if row.FechaRevision else None,
        "observacion_revision": _clean(row.ObservacionRevision),
        "aplicado_por": _clean(row.AplicadoPor),
        "fecha_aplicacion": row.FechaAplicacion.isoformat() if row.FechaAplicacion else None,
    }


def _request_select() -> str:
    return """
        SELECT
            s.*,
            respaldo.IdRespaldo AS RespaldoId,
            respaldo.TotalCabeceras AS RespaldoCabeceras,
            respaldo.TotalMaterias AS RespaldoMaterias,
            respaldo.HashContenido AS RespaldoHash,
            respaldo.FechaRespaldo,
            auditoria.IdMovimiento AS AuditoriaId,
            auditoria.HashMovimiento AS AuditoriaHash,
            (
                SELECT
                    archivo.IdArchivo AS id,
                    archivo.Orden AS orden,
                    archivo.ArchivoNombreOriginal AS nombre_original,
                    archivo.ArchivoNombreNube AS nombre,
                    archivo.ArchivoRuta AS ruta,
                    archivo.ArchivoSha256 AS sha256,
                    archivo.ArchivoTamano AS tamano,
                    archivo.GraphDocumentoId AS documento_id,
                    archivo.GraphWebUrl AS url,
                    archivo.EstadoExpediente AS estado,
                    archivo.FechaCarga AS fecha_carga
                FROM sol.SolicitudCambioModalidadArchivo archivo
                WHERE archivo.IdSolicitud = s.IdSolicitud
                ORDER BY archivo.Orden
                FOR JSON PATH
            ) AS ArchivosJson
        FROM sol.SolicitudCambioModalidad s
        LEFT JOIN sol.RespaldoCambioModalidad respaldo
          ON respaldo.IdSolicitud = s.IdSolicitud
        LEFT JOIN aud.MovimientoAcademico auditoria
          ON auditoria.TipoSolicitud = 'MODALIDAD'
         AND auditoria.IdSolicitud = s.IdSolicitud
         AND auditoria.Accion = 'APLICAR'
    """


def _ensure_single_header(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    target_modality: dict[str, Any],
    period_type: str,
) -> tuple[bool, int]:
    control_enrollment = 1 if period_type == "R" else 0
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, Num_Matricula) AS Num_Matricula
        FROM dbo.CABECERA_MATRICULA WITH (UPDLOCK, HOLDLOCK)
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_homologacion"],
    )
    row = cursor.fetchone()
    if row:
        num_matricula = int(row.Num_Matricula or 1)
        cursor.execute(
            """
            UPDATE dbo.CABECERA_MATRICULA
            SET codmodalidad = ?, codjornada = ?, Jornada = ?, ControlMatricula = ?
            WHERE TRY_CONVERT(int, codigo_estud) = ?
              AND TRY_CONVERT(int, cod_anio_Basica) = ?
              AND TRY_CONVERT(int, codigo_periodo) = ?
            """,
            target_modality["codigo"],
            target_modality["jornada_codigo"],
            target_modality["jornada_nombre"] or None,
            control_enrollment,
            request_item["codigo_estud"],
            request_item["carrera_destino"],
            request_item["codigo_periodo_homologacion"],
        )
        return False, num_matricula

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
        VALUES (?, ?, ?, 1, ?, 0, 0, 0, 0, 0, 0, 0, ?, 0, ?, 0, 0, ?, 0, ?, 1, 0, 0, 0)
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_homologacion"],
        date.today().isoformat(),
        target_modality["jornada_nombre"] or None,
        control_enrollment,
        target_modality["codigo"],
        target_modality["jornada_codigo"],
    )
    return True, 1


def _next_subject_attempt(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    career_code: int,
    subject_code: int,
) -> int:
    cursor.execute(
        """
        SELECT COALESCE(MAX(TRY_CONVERT(int, Num_Matricula)), 0) + 1
        FROM dbo.CARRERAXESTUD WITH (UPDLOCK, HOLDLOCK)
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_materia) = ?
        """,
        codigo_estud,
        career_code,
        subject_code,
    )
    return int(cursor.fetchone()[0] or 1)


def _enroll_all_subjects(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    subjects: list[dict[str, Any]],
    user_code: str,
    period_type: str,
) -> list[dict[str, Any]]:
    if period_type not in _VALID_PERIOD_TYPES:
        raise ValueError("Tipo de período destino inválido.")
    enrollment_type = _ENROLLMENT_TYPE_BY_PERIOD[period_type]
    control_enrollment = 1 if period_type == "R" else 0
    period_label = "regular" if period_type == "R" else "de homologación"
    existing = _existing_target_subjects(
        cursor,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_homologacion"],
    )
    results: list[dict[str, Any]] = []
    for subject in subjects:
        subject_code = int(subject["codigo_materia"])
        if subject_code in existing:
            cursor.execute(
                """
                UPDATE dbo.CARRERAXESTUD
                SET TipoMatricula = ?, ControlMatricula = ?
                WHERE TRY_CONVERT(int, codigo_estud) = ?
                  AND TRY_CONVERT(int, cod_anio_Basica) = ?
                  AND TRY_CONVERT(int, codigo_periodo) = ?
                  AND TRY_CONVERT(int, codigo_materia) = ?
                """,
                enrollment_type,
                control_enrollment,
                request_item["codigo_estud"],
                request_item["carrera_destino"],
                request_item["codigo_periodo_homologacion"],
                subject_code,
            )
            results.append(
                {
                    "codigo_materia": subject_code,
                    "estado": "EXISTENTE",
                    "num_matricula": existing[subject_code],
                    "observacion": f"La materia ya estaba registrada en el período {period_label}.",
                }
            )
            continue
        attempt = _next_subject_attempt(
            cursor,
            request_item["codigo_estud"],
            request_item["carrera_destino"],
            subject_code,
        )
        cursor.execute(
            """
            INSERT INTO dbo.CARRERAXESTUD
            (
                codigo_estud, cod_anio_Basica, codigo_materia, codigo_periodo,
                Num_Matricula, paralelo, NumGrupo, Num_Creditos, Fecha_Matricula,
                TipoMatricula, ControlMatricula, CodUsuaMat
            )
            VALUES (?, ?, ?, ?, ?, N'A', 0, ?, ?, ?, ?, ?)
            """,
            request_item["codigo_estud"],
            request_item["carrera_destino"],
            subject_code,
            request_item["codigo_periodo_homologacion"],
            attempt,
            int(round(_float_value(subject.get("creditos")))),
            date.today().isoformat(),
            enrollment_type,
            control_enrollment,
            user_code,
        )
        results.append(
            {
                "codigo_materia": subject_code,
                "estado": "MATRICULADA",
                "num_matricula": attempt,
                "observacion": f"Materia incorporada en la matrícula única del período {period_label}.",
            }
        )
    return results


def _capture_modality_snapshot(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    parameters = (
        request_item["codigo_estud"],
        request_item["carrera_origen"],
        request_item["codigo_periodo_origen"],
    )
    cursor.execute(
        """
        SELECT cab.*
        FROM dbo.CABECERA_MATRICULA cab WITH (HOLDLOCK)
        WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
          AND TRY_CONVERT(int, cab.cod_anio_Basica) = ?
          AND TRY_CONVERT(int, cab.codigo_periodo) = ?
        ORDER BY TRY_CONVERT(int, cab.Num_Matricula), TRY_CONVERT(bigint, cab.numcodigo)
        """,
        *parameters,
    )
    for row in cursor.fetchall():
        rows.append(
            build_snapshot_row(
                "CABECERA",
                cursor_row_dict(cursor, row),
                _MODALITY_SNAPSHOT_KEYS["CABECERA"],
            )
        )

    cursor.execute(
        """
        SELECT cxe.*
        FROM dbo.CARRERAXESTUD cxe WITH (HOLDLOCK)
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
          AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
          AND TRY_CONVERT(int, cxe.codigo_periodo) = ?
        ORDER BY TRY_CONVERT(int, cxe.codigo_materia), TRY_CONVERT(bigint, cxe.num)
        """,
        *parameters,
    )
    for row in cursor.fetchall():
        rows.append(
            build_snapshot_row(
                "MATERIA",
                cursor_row_dict(cursor, row),
                _MODALITY_SNAPSHOT_KEYS["MATERIA"],
            )
        )

    total_headers = sum(row["tipo_registro"] == "CABECERA" for row in rows)
    total_subjects = sum(row["tipo_registro"] == "MATERIA" for row in rows)
    if total_subjects == 0:
        raise HTTPException(
            status_code=409,
            detail="No existen materias del período de origen para generar el respaldo.",
        )
    return {
        "rows": rows,
        "total_cabeceras": total_headers,
        "total_materias": total_subjects,
        "hash_contenido": snapshot_digest(rows),
    }


def _period_record_counts(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
) -> tuple[int, int]:
    parameters = (
        request_item["codigo_estud"],
        request_item["carrera_origen"],
        request_item["codigo_periodo_origen"],
    )
    cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM dbo.CABECERA_MATRICULA cab WITH (HOLDLOCK)
                WHERE TRY_CONVERT(int, cab.codigo_estud) = ?
                  AND TRY_CONVERT(int, cab.cod_anio_Basica) = ?
                  AND TRY_CONVERT(int, cab.codigo_periodo) = ?
            ),
            (
                SELECT COUNT(*)
                FROM dbo.CARRERAXESTUD cxe WITH (HOLDLOCK)
                WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
                  AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
                  AND TRY_CONVERT(int, cxe.codigo_periodo) = ?
            )
        """,
        *parameters,
        *parameters,
    )
    row = cursor.fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _backup_metadata(row: Any) -> dict[str, Any]:
    return {
        "id_respaldo": int(row.IdRespaldo),
        "id_solicitud": int(row.IdSolicitud),
        "codigo_estud": int(row.CodigoEstud),
        "carrera_origen": int(row.CarreraOrigen),
        "carrera_destino": int(row.CarreraDestino),
        "periodo_origen": int(row.PeriodoOrigen),
        "periodo_destino": int(row.PeriodoDestino),
        "modalidad_origen": _int_value(row.ModalidadOrigen),
        "modalidad_destino": int(row.ModalidadDestino),
        "total_cabeceras": int(row.TotalCabeceras or 0),
        "total_materias": int(row.TotalMaterias or 0),
        "hash_contenido": _clean(row.HashContenido).lower(),
        "fecha_respaldo": row.FechaRespaldo.isoformat() if row.FechaRespaldo else None,
    }


def _find_modality_backup(cursor: pyodbc.Cursor, request_id: int) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT * FROM sol.RespaldoCambioModalidad WHERE IdSolicitud = ?",
        request_id,
    )
    row = cursor.fetchone()
    return _backup_metadata(row) if row else None


def _persist_modality_snapshot(
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
            "SELECT * FROM sol.RespaldoCambioModalidad WITH (UPDLOCK, HOLDLOCK) WHERE IdSolicitud = ?",
            request_id,
        )
        existing = cursor.fetchone()
        if existing:
            backup = _backup_metadata(existing)
            expected = (
                request_item["codigo_estud"],
                request_item["carrera_origen"],
                request_item["carrera_destino"],
                request_item["codigo_periodo_origen"],
                request_item["codigo_periodo_homologacion"],
                request_item["modalidad_origen"],
                request_item["modalidad_destino"],
            )
            actual = (
                backup["codigo_estud"],
                backup["carrera_origen"],
                backup["carrera_destino"],
                backup["periodo_origen"],
                backup["periodo_destino"],
                backup["modalidad_origen"],
                backup["modalidad_destino"],
            )
            if actual != expected:
                raise HTTPException(
                    status_code=409,
                    detail="El respaldo existente no corresponde a esta solicitud de modalidad.",
                )
            return backup

        cursor.execute(
            """
            INSERT INTO sol.RespaldoCambioModalidad
            (
                IdSolicitud, CodigoEstud, CarreraOrigen, CarreraDestino,
                PeriodoOrigen, PeriodoDestino, ModalidadOrigen, ModalidadDestino,
                TotalCabeceras, TotalMaterias, HashContenido, RespaldadoPor
            )
            OUTPUT INSERTED.IdRespaldo
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            request_id,
            request_item["codigo_estud"],
            request_item["carrera_origen"],
            request_item["carrera_destino"],
            request_item["codigo_periodo_origen"],
            request_item["codigo_periodo_homologacion"],
            request_item["modalidad_origen"],
            request_item["modalidad_destino"],
            snapshot["total_cabeceras"],
            snapshot["total_materias"],
            snapshot["hash_contenido"],
            audit_user,
        )
        backup_id = int(cursor.fetchone()[0])
        for row in snapshot["rows"]:
            cursor.execute(
                """
                INSERT INTO sol.RespaldoCambioModalidadFila
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
        cursor.execute(
            "SELECT * FROM sol.RespaldoCambioModalidad WHERE IdRespaldo = ?",
            backup_id,
        )
        return _backup_metadata(cursor.fetchone())


def _verify_modality_backup(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    backup: dict[str, Any],
) -> bool:
    header_count, subject_count = _period_record_counts(cursor, request_item)
    if header_count == 0 and subject_count == 0:
        return False
    if header_count != backup["total_cabeceras"] or subject_count != backup["total_materias"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "La matrícula de origen cambió después de generar el respaldo. "
                "No se eliminó ningún registro."
            ),
        )
    current_snapshot = _capture_modality_snapshot(cursor, request_item)
    if current_snapshot["hash_contenido"] != backup["hash_contenido"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Las calificaciones de origen ya no coinciden con el respaldo. "
                "No se eliminó ningún registro."
            ),
        )
    return True


def _archive_source_period(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
) -> dict[str, int]:
    if request_item["codigo_periodo_origen"] == request_item["codigo_periodo_homologacion"]:
        raise HTTPException(status_code=409, detail="Los períodos de origen y destino no pueden coincidir.")
    parameters = (
        request_item["codigo_estud"],
        request_item["carrera_origen"],
        request_item["codigo_periodo_origen"],
    )
    cursor.execute(
        """
        DELETE FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        """,
        *parameters,
    )
    subjects = max(int(cursor.rowcount or 0), 0)
    cursor.execute(
        """
        DELETE FROM dbo.CABECERA_MATRICULA
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
        """,
        *parameters,
    )
    headers = max(int(cursor.rowcount or 0), 0)
    remaining_headers, remaining_subjects = _period_record_counts(cursor, request_item)
    if remaining_headers or remaining_subjects:
        raise HTTPException(
            status_code=409,
            detail="No se pudo retirar completamente la matrícula de origen; se canceló la operación.",
        )
    return {
        "source_headers_archived": headers,
        "source_subjects_archived": subjects,
    }


def _transformed_grade_values(
    source_data: dict[str, Any],
    source_period_type: str,
    target_period_type: str,
) -> dict[str, Any]:
    values = {field: source_data.get(field) for field in _GRADE_FIELDS}
    final_grade = _effective_grade(source_data, source_period_type)
    if final_grade is None or source_period_type == target_period_type:
        return values
    if target_period_type == "H":
        theory_grade, practice_grade, final_grade = _project_final_grade_to_homologation(
            final_grade
        )
        values["teoriaHomo"] = theory_grade
        values["practicahomo"] = practice_grade
    else:
        for field in (
            "P1Tareas",
            "P1Proyectos",
            "P1Examen",
            "promP1",
            "P2Tareas",
            "P2Proyectos",
            "P2Examen",
            "promP2",
            "P3Tareas",
            "P3Proyectos",
            "P3Examen",
            "promP3",
        ):
            values[field] = final_grade
    values["Promedio"] = final_grade
    values["PromedioFinal"] = final_grade
    values["PromedioAux"] = final_grade
    return values


def _find_target_subject(
    cursor: pyodbc.Cursor,
    request_item: dict[str, Any],
    subject_code: int,
) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT TOP (1) *
        FROM dbo.CARRERAXESTUD WITH (UPDLOCK, HOLDLOCK)
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
          AND TRY_CONVERT(int, codigo_materia) = ?
        ORDER BY
            COALESCE(
                TRY_CONVERT(decimal(18,3), PromedioFinal),
                TRY_CONVERT(decimal(18,3), Promedio),
                TRY_CONVERT(decimal(18,3), PromedioAux),
                -1
            ) DESC,
            TRY_CONVERT(bigint, num) DESC
        """,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        request_item["codigo_periodo_homologacion"],
        subject_code,
    )
    row = cursor.fetchone()
    return cursor_row_dict(cursor, row) if row else None


def _write_target_subject(
    cursor: pyodbc.Cursor,
    *,
    request_item: dict[str, Any],
    subject: dict[str, Any],
    source: dict[str, Any] | None,
    user_code: str,
    source_period_type: str,
    target_period_type: str,
) -> dict[str, Any]:
    subject_code = int(subject["codigo_materia"])
    enrollment_type = _ENROLLMENT_TYPE_BY_PERIOD[target_period_type]
    control_enrollment = 1 if target_period_type == "R" else 0
    existing = _find_target_subject(cursor, request_item, subject_code)
    source_candidate = source
    source_candidate_data = source_candidate["data"] if source_candidate else {}
    recorded_source_grade = _optional_float(subject.get("nota_origen"))
    current_source_grade = (
        _effective_grade(source_candidate_data, source_period_type)
        if source_candidate
        else recorded_source_grade
    )
    requires_repetition = bool(
        subject.get("requiere_repeticion")
        or _is_failed_grade(recorded_source_grade)
        or _is_failed_grade(current_source_grade)
    )
    reported_source_grade = (
        recorded_source_grade
        if _is_failed_grade(recorded_source_grade)
        else current_source_grade
    )
    if source_candidate and (
        requires_repetition or not _is_approved_grade(current_source_grade)
    ):
        source = None
    source_data = source["data"] if source else {}
    grade_values = _transformed_grade_values(
        source_data,
        source_period_type,
        target_period_type,
    )
    source_grade = _effective_grade(grade_values, target_period_type) if source else None
    existing_grade = _effective_grade(existing, target_period_type) if existing else None
    copy_source_grade = bool(
        source
        and (existing_grade is None or source_grade is None or source_grade >= existing_grade)
    )

    if existing:
        assignments = ["TipoMatricula = ?", "ControlMatricula = ?", "CodUsuaMat = ?"]
        parameters: list[Any] = [enrollment_type, control_enrollment, user_code]
        if copy_source_grade:
            assignments.extend(f"[{field}] = ?" for field in _GRADE_FIELDS)
            parameters.extend(grade_values[field] for field in _GRADE_FIELDS)
            assignments.extend(
                [
                    "caprueba = ?",
                    "ControlAprueba = ?",
                    "ObservacionP1 = ?",
                    "ObservacionP2 = ?",
                    "MateriaConvalidada = ?",
                    "Usuario = ?",
                    "estadoMoodle = 0",
                    "NumMatricuMod = COALESCE(NumMatricuMod, 0) + 1",
                ]
            )
            parameters.extend(
                [
                    source_data.get("caprueba"),
                    source_data.get("ControlAprueba"),
                    source_data.get("ObservacionP1"),
                    source_data.get("ObservacionP2"),
                    source_data.get("MateriaConvalidada"),
                    user_code,
                ]
            )
        parameters.append(existing["num"])
        cursor.execute(
            f"UPDATE dbo.CARRERAXESTUD SET {', '.join(assignments)} WHERE num = ?",
            *parameters,
        )
        if source:
            observation = (
                "Registro migrado por código único; se conservó la nota superior que ya existía en destino."
                if not copy_source_grade
                else "Registro y calificaciones migrados por código único al período destino."
            )
            state = "MIGRADA"
        elif requires_repetition:
            observation = (
                "La materia reprobada ya estaba matriculada en el período destino; "
                "no se copiaron calificaciones del período anterior."
            )
            state = "EXISTENTE"
        else:
            observation = "La materia ya existía en el período destino y se conservó sin duplicarla."
            state = "EXISTENTE"
        return {
            "codigo_materia": subject_code,
            "estado": state,
            "num_matricula": _int_value(existing.get("Num_Matricula")) or 1,
            "observacion": observation,
            "origen_mapeado": source is not None,
            "materia_origen": (
                _int_value(source_candidate.get("codigo_materia"))
                if source is not None and source_candidate
                else None
            ),
            "nota_origen": reported_source_grade,
            "requiere_repeticion": requires_repetition,
            "created": False,
        }

    attempt = _next_subject_attempt(
        cursor,
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        subject_code,
    )
    if requires_repetition and source_candidate:
        source_attempt = _int_value(
            source_candidate_data.get("Num_Matricula")
        ) or 0
        attempt = max(attempt, source_attempt + 1)
    columns = [
        "codigo_estud",
        "cod_anio_Basica",
        "codigo_materia",
        "codigo_periodo",
        "Num_Matricula",
        "paralelo",
        "NumGrupo",
        *_GRADE_FIELDS,
        "caprueba",
        "Usuario",
        "Num_Creditos",
        "Fecha_Matricula",
        "ObservacionP1",
        "ObservacionP2",
        "MateriaConvalidada",
        "TipoMatricula",
        "ControlAprueba",
        "ControlMatricula",
        "CodUsuaMat",
        "estadoMoodle",
    ]
    values = [
        request_item["codigo_estud"],
        request_item["carrera_destino"],
        subject_code,
        request_item["codigo_periodo_homologacion"],
        attempt,
        _clean(source_data.get("paralelo")) or "A",
        _int_value(source_data.get("NumGrupo")) or 0,
        *(grade_values[field] for field in _GRADE_FIELDS),
        source_data.get("caprueba"),
        user_code,
        int(round(_float_value(subject.get("creditos")))),
        date.today().isoformat(),
        source_data.get("ObservacionP1"),
        source_data.get("ObservacionP2"),
        source_data.get("MateriaConvalidada"),
        enrollment_type,
        source_data.get("ControlAprueba"),
        control_enrollment,
        user_code,
        0,
    ]
    cursor.execute(
        f"INSERT INTO dbo.CARRERAXESTUD ({', '.join(f'[{column}]' for column in columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        *values,
    )
    return {
        "codigo_materia": subject_code,
        "estado": "MIGRADA" if source else "MATRICULADA",
        "num_matricula": attempt,
        "observacion": (
            "Registro y calificaciones migrados por código único al período destino."
            if source
            else (
                "Materia reprobada matriculada nuevamente sin copiar calificaciones."
                if requires_repetition
                else "Materia incorporada sin calificaciones en la matrícula del período destino."
            )
        ),
        "origen_mapeado": source is not None,
        "materia_origen": (
            _int_value(source_candidate.get("codigo_materia"))
            if source is not None and source_candidate
            else None
        ),
        "nota_origen": reported_source_grade,
        "requiere_repeticion": requires_repetition,
        "created": True,
    }


def _migrate_subjects(
    cursor: pyodbc.Cursor,
    *,
    request_item: dict[str, Any],
    subjects: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    user_code: str,
) -> list[dict[str, Any]]:
    sources_by_code = _best_sources_by_common_code(source_rows)
    results: list[dict[str, Any]] = []
    for subject in subjects:
        source_code = _normalize_common_code(
            subject.get("codigo_comun_origen") or subject.get("codigo_comun")
        )
        requires_repetition = _is_failed_grade(subject.get("nota_origen"))
        source = (
            sources_by_code.get(source_code)
            if subject.get("materia_origen") or requires_repetition
            else None
        )
        if subject.get("materia_origen") and (
            source is None
            or int(source.get("codigo_materia") or 0) != int(subject["materia_origen"])
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"La materia de origen vinculada a {subject['nombre']} cambió. "
                    "No se aplicó la solicitud."
                ),
            )
        if requires_repetition and source is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"La materia reprobada vinculada a {subject['nombre']} ya no está "
                    "disponible en el período de origen. No se aplicó la solicitud."
                ),
            )
        results.append(
            _write_target_subject(
                cursor,
                request_item=request_item,
                subject=subject,
                source=source,
                user_code=user_code,
                source_period_type=request_item["tipo_periodo_origen"],
                target_period_type=request_item["tipo_periodo_destino"],
            )
        )
    return results


@router.get("/catalog")
def modality_change_catalog(
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
            careers = [
                {"codigo": int(row.codigo), "nombre": _clean(row.nombre)}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(int, modalidad.NumM) AS codigo,
                    TRY_CONVERT(nvarchar(150), modalidad.DetalleM) AS nombre,
                    TRY_CONVERT(int, jornada.NumJ) AS jornada_codigo,
                    TRY_CONVERT(nvarchar(100), jornada.DetalleJ) AS jornada_nombre
                FROM dbo.ModalidadMatricula modalidad
                OUTER APPLY
                (
                    SELECT TOP (1) NumJ, DetalleJ
                    FROM dbo.JORNADA
                    WHERE TRY_CONVERT(int, codmodalidad) = TRY_CONVERT(int, modalidad.NumM)
                    ORDER BY TRY_CONVERT(int, NumJ)
                ) jornada
                ORDER BY modalidad.DetalleM
                """
            )
            modalities = [
                {
                    "codigo": int(row.codigo),
                    "nombre": _clean(row.nombre),
                    "jornada_codigo": _int_value(row.jornada_codigo) or 0,
                    "jornada_nombre": _clean(row.jornada_nombre),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT TOP (50)
                    TRY_CONVERT(int, cod_periodo) AS codigo,
                    TRY_CONVERT(nvarchar(250), Detalle_Periodo) AS nombre,
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), TipoMatricula)))) AS tipo,
                    TRY_CONVERT(nvarchar(10), Estado) AS estado,
                    fechain,
                    fechafin
                FROM dbo.PERIODO
                WHERE UPPER(LTRIM(RTRIM(ISNULL(TipoMatricula, '')))) IN ('R', 'H')
                  AND (fechafin IS NULL OR fechafin >= CAST(GETDATE() AS date))
                ORDER BY COALESCE(fechain, CAST('19000101' AS date)) DESC, cod_periodo DESC
                """
            )
            periods = [
                {
                    "codigo": int(row.codigo),
                    "nombre": _clean(row.nombre),
                    "estado": _clean(row.estado),
                    "tipo": _clean(row.tipo).upper(),
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
                    WITH ultima_cabecera AS
                    (
                        SELECT
                            cab.codigo_estud,
                            TRY_CONVERT(int, cab.cod_anio_Basica) AS carrera,
                            TRY_CONVERT(int, cab.codigo_periodo) AS periodo,
                            NULLIF(TRY_CONVERT(int, cab.codmodalidad), 0) AS modalidad,
                            NULLIF(TRY_CONVERT(int, cab.codjornada), 0) AS jornada_codigo,
                            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), cab.Jornada))), N'') AS jornada_nombre,
                            ROW_NUMBER() OVER
                            (
                                PARTITION BY cab.codigo_estud
                                ORDER BY TRY_CONVERT(int, cab.codigo_periodo) DESC,
                                         TRY_CONVERT(bigint, cab.numcodigo) DESC
                            ) AS fila
                        FROM dbo.CABECERA_MATRICULA cab
                    ),
                    ultima_materia AS
                    (
                        SELECT
                            cxe.codigo_estud,
                            TRY_CONVERT(int, cxe.cod_anio_Basica) AS carrera,
                            TRY_CONVERT(int, cxe.codigo_periodo) AS periodo,
                            ROW_NUMBER() OVER
                            (
                                PARTITION BY cxe.codigo_estud
                                ORDER BY TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                                         TRY_CONVERT(bigint, cxe.num) DESC
                            ) AS fila
                        FROM dbo.CARRERAXESTUD cxe
                    )
                    SELECT TOP ({limit})
                        TRY_CONVERT(int, d.codigo_estud) AS codigo_estud,
                        TRY_CONVERT(nvarchar(32), d.Cedula_Est) AS cedula,
                        TRY_CONVERT(nvarchar(250), d.Apellidos_nombre) AS estudiante,
                        TRY_CONVERT(nvarchar(10), d.Estado) AS estado,
                        COALESCE(uc.carrera, um.carrera) AS carrera,
                        TRY_CONVERT(nvarchar(250), carrera.Nombre_Basica) AS carrera_nombre,
                        COALESCE(uc.periodo, um.periodo) AS periodo,
                        TRY_CONVERT(nvarchar(250), periodo.Detalle_Periodo) AS periodo_nombre,
                        UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula)))) AS tipo_periodo,
                        COALESCE(
                            uc.modalidad,
                            CASE TRY_CONVERT(int, d.ModalidadEstudio)
                                WHEN 5 THEN 1
                                WHEN 1 THEN 3
                                ELSE NULL
                            END
                        ) AS modalidad,
                        TRY_CONVERT(nvarchar(150), modalidad.DetalleM) AS modalidad_nombre,
                        uc.jornada_codigo,
                        uc.jornada_nombre
                    FROM dbo.DATOS_ESTUD d
                    LEFT JOIN ultima_cabecera uc ON uc.codigo_estud = d.codigo_estud AND uc.fila = 1
                    LEFT JOIN ultima_materia um ON um.codigo_estud = d.codigo_estud AND um.fila = 1
                    LEFT JOIN dbo.CARRERAS carrera
                      ON TRY_CONVERT(int, carrera.Cod_AnioBasica) = COALESCE(uc.carrera, um.carrera)
                    LEFT JOIN dbo.PERIODO periodo
                      ON TRY_CONVERT(int, periodo.cod_periodo) = COALESCE(uc.periodo, um.periodo)
                    LEFT JOIN dbo.ModalidadMatricula modalidad
                      ON TRY_CONVERT(int, modalidad.NumM) = COALESCE(
                          uc.modalidad,
                          CASE TRY_CONVERT(int, d.ModalidadEstudio)
                              WHEN 5 THEN 1
                              WHEN 1 THEN 3
                              ELSE NULL
                          END
                      )
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
                        "periodo": _int_value(row.periodo),
                        "periodo_nombre": _clean(row.periodo_nombre),
                        "tipo_periodo": _clean(row.tipo_periodo).upper(),
                        "modalidad": _int_value(row.modalidad),
                        "modalidad_nombre": _clean(row.modalidad_nombre),
                        "jornada_codigo": _int_value(row.jornada_codigo),
                        "jornada_nombre": _clean(row.jornada_nombre),
                    }
                    for row in cursor.fetchall()
                ]
        return {
            "students": students,
            "careers": careers,
            "modalities": modalities,
            "periods": periods,
            "states": sorted(_VALID_STATES),
        }
    except pyodbc.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo consultar el catálogo de cambio de modalidad: {exc}",
        ) from exc


@router.post("/preview")
def preview_modality_change(
    payload: ModalityChangePreviewPayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            return _preview_with_cursor(conn.cursor(), payload)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo preparar la matrícula: {exc}") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_modality_change_request(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    codigo_estud: Annotated[int, Form(gt=0)],
    carrera_destino: Annotated[int, Form(gt=0)],
    codigo_periodo_homologacion: Annotated[int, Form(gt=0)],
    motivo: Annotated[str, Form(min_length=10, max_length=1000)],
    archivos: Annotated[list[UploadFile] | None, File()] = None,
    archivo: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    uploads = list(archivos or [])
    if archivo is not None:
        uploads.append(archivo)
    documents = await _read_supporting_pdfs(uploads)
    first_document = documents[0]
    payload = ModalityChangePreviewPayload(
        codigo_estud=codigo_estud,
        carrera_destino=carrera_destino,
        codigo_periodo_homologacion=codigo_periodo_homologacion,
    )
    try:
        with get_connection() as conn:
            preview = _preview_with_cursor(conn.cursor(), payload)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo validar la solicitud: {exc}") from exc

    _ensure_schema()
    request_id: int | None = None
    archived_documents: list[dict[str, Any]] = []
    student = preview["student"]
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM sol.SolicitudCambioModalidad WITH (UPDLOCK, HOLDLOCK)
                WHERE CodigoEstud = ? AND Estado IN (N'PENDIENTE', N'APROBADA')
                """,
                codigo_estud,
            )
            if int(cursor.fetchone()[0] or 0) > 0:
                raise HTTPException(
                    status_code=409,
                    detail="El estudiante ya tiene una solicitud de cambio de modalidad pendiente o aprobada.",
                )
            cursor.execute(
                """
                INSERT INTO sol.SolicitudCambioModalidad
                (
                    CodigoEstud, Cedula, Estudiante,
                    CarreraOrigen, CarreraOrigenNombre, CarreraDestino, CarreraDestinoNombre,
                    ModalidadOrigen, ModalidadOrigenNombre,
                    CodigoPeriodoOrigen, PeriodoOrigenNombre, TipoPeriodoOrigen,
                    ModalidadDestino, ModalidadDestinoNombre,
                    CodigoPeriodoHomologacion, PeriodoHomologacionNombre, TipoPeriodoDestino,
                    Estado, Motivo, ArchivoNombre, ArchivoRuta, ArchivoSha256, ArchivoTamano,
                    EstadoExpediente, TotalMateriasPensum, CreadoPor
                )
                OUTPUT INSERTED.IdSolicitud
                VALUES
                (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                student["codigo_estud"],
                student["cedula"],
                student["estudiante"],
                student["carrera"],
                student["carrera_nombre"],
                preview["target_career"]["codigo"],
                preview["target_career"]["nombre"],
                student["modalidad"],
                student["modalidad_nombre"],
                preview["source_period"]["codigo"],
                preview["source_period"]["nombre"],
                preview["source_period"]["tipo"],
                preview["target_modality"]["codigo"],
                preview["target_modality"]["nombre"],
                preview["homologation_period"]["codigo"],
                preview["homologation_period"]["nombre"],
                preview["homologation_period"]["tipo"],
                "PENDIENTE",
                motivo.strip(),
                first_document["nombre_original"],
                "PENDIENTE_EXPEDIENTE",
                first_document["sha256"],
                first_document["tamano"],
                "PENDIENTE",
                preview["summary"]["materias_pensum"],
                _user_label(current_user),
            )
            request_id = int(cursor.fetchone()[0])
            for document in documents:
                cursor.execute(
                    """
                    INSERT INTO sol.SolicitudCambioModalidadArchivo
                    (
                        IdSolicitud, Orden, ArchivoNombreOriginal, ArchivoSha256,
                        ArchivoTamano, EstadoExpediente
                    )
                    VALUES (?, ?, ?, ?, ?, N'PENDIENTE')
                    """,
                    request_id,
                    document["orden"],
                    document["nombre_original"],
                    document["sha256"],
                    document["tamano"],
                )
            for subject in preview["subjects"]:
                cursor.execute(
                    """
                    INSERT INTO sol.SolicitudCambioModalidadMateria
                    (
                        IdSolicitud, CodigoMateria, CodigoComun, NombreMateria,
                        Nivel, Creditos, MateriaOrigen, CodigoComunOrigen, NotaOrigen,
                        Estado, NumMatricula, Observacion
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    request_id,
                    subject["codigo_materia"],
                    subject["codigo_comun"],
                    subject["nombre"],
                    subject["nivel"],
                    subject["creditos"],
                    subject.get("materia_origen"),
                    subject.get("codigo_comun_origen"),
                    subject.get("nota_origen"),
                    "EXISTENTE" if subject["estado"] == "EXISTENTE" else "PENDIENTE",
                    subject["num_matricula"],
                    (
                        "La materia ya existe en el período seleccionado."
                        if subject["estado"] == "EXISTENTE"
                        else (
                            "Pendiente de migrar por código único."
                            if subject["estado"] == "MIGRAR"
                            else (
                                "Materia reprobada: se matriculará nuevamente sin copiar calificaciones."
                                if subject["estado"] == "REPETIR"
                                else "Pendiente de aprobación y matrícula."
                            )
                        )
                    ),
                )
            conn.commit()

        for document in documents:
            archived = _archive_supporting_document(
                request_id=request_id,
                file_order=document["orden"],
                student=student,
                original_filename=document["nombre_original"],
                content=document["contenido"],
                audit_user=_user_label(current_user),
            )
            archived_documents.append({**document, **archived})

        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            for document in archived_documents:
                cursor.execute(
                    """
                    UPDATE sol.SolicitudCambioModalidadArchivo
                    SET ArchivoNombreNube = ?, ArchivoRuta = ?, GraphDocumentoId = ?,
                        GraphWebUrl = ?, EstadoExpediente = N'CARGADO',
                        FechaCarga = SYSUTCDATETIME()
                    WHERE IdSolicitud = ? AND Orden = ?
                    """,
                    document["cloud_filename"],
                    document["graph_path"],
                    document["document_id"],
                    document["web_url"],
                    request_id,
                    document["orden"],
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"No se pudo vincular el respaldo {document['orden']} con la solicitud."
                    )

            first_archived = archived_documents[0]
            cursor.execute(
                """
                UPDATE sol.SolicitudCambioModalidad
                SET ArchivoNombre = ?, ArchivoRuta = ?, GraphDocumentoId = ?,
                    GraphWebUrl = ?, EstadoExpediente = N'CARGADO'
                WHERE IdSolicitud = ?
                """,
                first_archived["cloud_filename"],
                first_archived["graph_path"],
                first_archived["document_id"],
                first_archived["web_url"],
                request_id,
            )
            conn.commit()
        return {
            "ok": True,
            "message": (
                "La solicitud se registró y el documento quedó en el expediente estudiantil."
                if len(archived_documents) == 1
                else (
                    f"La solicitud se registró y {len(archived_documents)} documentos "
                    "quedaron en el expediente estudiantil."
                )
            ),
            "id": request_id,
            "estado": "PENDIENTE",
            "archivos_cargados": len(archived_documents),
            "materias_pensum": preview["summary"]["materias_pensum"],
            "cabeceras_a_crear": preview["summary"]["cabeceras_a_crear"],
        }
    except HTTPException:
        if request_id is not None:
            _delete_archived_documents_safely(archived_documents)
            _delete_unarchived_request_safely(request_id)
        raise
    except httpx.HTTPError as exc:
        if request_id is not None:
            _delete_archived_documents_safely(archived_documents)
            _delete_unarchived_request_safely(request_id)
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft OneDrive no pudo guardar el respaldo: {exc}",
        ) from exc
    except (pyodbc.Error, RuntimeError, ValueError) as exc:
        if request_id is not None:
            _delete_archived_documents_safely(archived_documents)
            _delete_unarchived_request_safely(request_id)
        raise HTTPException(status_code=503, detail=f"No se pudo registrar la solicitud: {exc}") from exc


@router.get("")
def list_modality_change_requests(
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
                    ? = N'%%' OR s.Estudiante LIKE ? OR s.Cedula LIKE ?
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
def modality_change_request_detail(
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
                FROM sol.SolicitudCambioModalidadMateria
                WHERE IdSolicitud = ?
                ORDER BY Nivel, NombreMateria
                """,
                request_id,
            )
            subjects = [
                {
                    "id": int(item.IdDetalle),
                    "codigo_materia": int(item.CodigoMateria),
                    "codigo_comun": _clean(item.CodigoComun),
                    "nombre": _clean(item.NombreMateria),
                    "nivel": _int_value(item.Nivel),
                    "creditos": _float_value(item.Creditos),
                    "materia_origen": _int_value(getattr(item, "MateriaOrigen", None)),
                    "codigo_comun_origen": _clean(
                        getattr(item, "CodigoComunOrigen", "")
                    ),
                    "nota_origen": _optional_float(getattr(item, "NotaOrigen", None)),
                    "requiere_repeticion": bool(
                        _is_failed_grade(getattr(item, "NotaOrigen", None))
                        and _int_value(getattr(item, "MateriaOrigen", None)) is None
                    ),
                    "estado": _clean(item.Estado),
                    "num_matricula": _int_value(item.NumMatricula),
                    "observacion": _clean(item.Observacion),
                }
                for item in cursor.fetchall()
            ]
        return {**request_item, "subjects": subjects}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar la solicitud: {exc}") from exc


@router.post("/{request_id}/decision")
def decide_modality_change_request(
    request_id: int,
    payload: ModalityChangeDecisionPayload,
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
                UPDATE sol.SolicitudCambioModalidad
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
            result = apply_modality_change_request(request_id, current_user)
            return {**result, "message": f"La solicitud fue aprobada. {result['message']}"}
        return {"ok": True, "message": "La solicitud quedó rechazada.", "estado": decision}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo registrar la decisión: {exc}") from exc


@router.post("/{request_id}/apply")
def apply_modality_change_request(
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    _require_reviewer(current_user)
    _ensure_schema()
    primary_conn: pyodbc.Connection | None = None
    try:
        with get_integration_control_connection() as integration_conn:
            integration_cursor = integration_conn.cursor()
            integration_cursor.execute(f"{_request_select()} WHERE s.IdSolicitud = ?", request_id)
            row = integration_cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontró la solicitud.")
            request_item = _row_to_request(row)
            if request_item["estado"] == "APLICADA":
                return {
                    "ok": True,
                    "message": "La solicitud ya estaba aplicada; no se generaron matrículas adicionales.",
                    "estado": "APLICADA",
                    "cabeceras_creadas": 0,
                    "materias_matriculadas": 0,
                    "materias_existentes": request_item["materias_existentes"],
                    "materias_migradas": request_item["materias_migradas"],
                    "materias_origen_retiradas": request_item["materias_origen_retiradas"],
                    "cabeceras_origen_retiradas": request_item["cabeceras_origen_retiradas"],
                    "respaldo_id": request_item["respaldo_id"],
                    "auditoria_id": request_item["auditoria_id"],
                }
            if request_item["estado"] != "APROBADA":
                raise HTTPException(
                    status_code=409,
                    detail="La solicitud debe estar aprobada antes de aplicarla.",
                )
            if (
                request_item["codigo_periodo_origen"] is None
                or request_item["tipo_periodo_origen"] not in _VALID_PERIOD_TYPES
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "La solicitud no contiene el período de origen requerido para una migración segura. "
                        "Registre una nueva solicitud."
                    ),
                )
            backup = _find_modality_backup(integration_cursor, request_id)
            integration_cursor.execute(
                """
                SELECT
                    CodigoMateria, CodigoComun, NombreMateria, Nivel, Creditos,
                    MateriaOrigen, CodigoComunOrigen, NotaOrigen, Estado, NumMatricula,
                    Observacion
                FROM sol.SolicitudCambioModalidadMateria
                WHERE IdSolicitud = ?
                ORDER BY Nivel, NombreMateria
                """,
                request_id,
            )
            subjects = [
                {
                    "codigo_materia": int(item.CodigoMateria),
                    "codigo_comun": _clean(item.CodigoComun),
                    "nombre": _clean(item.NombreMateria),
                    "nivel": _int_value(item.Nivel),
                    "creditos": _float_value(item.Creditos),
                    "materia_origen": _int_value(item.MateriaOrigen),
                    "codigo_comun_origen": _clean(item.CodigoComunOrigen),
                    "nota_origen": _optional_float(item.NotaOrigen),
                    "estado": _clean(item.Estado),
                    "num_matricula": _int_value(item.NumMatricula),
                    "observacion": _clean(item.Observacion),
                }
                for item in integration_cursor.fetchall()
            ]
            if not subjects:
                raise HTTPException(
                    status_code=409,
                    detail="La solicitud no contiene materias aprobadas para migrar.",
                )

        with get_connection() as primary_conn:
            cursor = primary_conn.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            student = _fetch_student_context(cursor, request_item["codigo_estud"])
            if student["carrera"] not in {
                request_item["carrera_origen"],
                request_item["carrera_destino"],
            }:
                raise HTTPException(
                    status_code=409,
                    detail="La carrera actual cambió después de registrar la solicitud.",
                )
            current_modality = student["modalidad"]
            if current_modality is not None and current_modality not in {
                request_item["modalidad_origen"],
                request_item["modalidad_destino"],
            }:
                raise HTTPException(
                    status_code=409,
                    detail="La modalidad actual cambió después de registrar la solicitud.",
                )
            _fetch_career(cursor, request_item["carrera_destino"])
            target_modality = _inherited_modality(cursor, student)
            if target_modality["codigo"] not in {
                request_item["modalidad_origen"],
                request_item["modalidad_destino"],
            } or request_item["modalidad_origen"] != request_item["modalidad_destino"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "La solicitud no coincide con la modalidad heredada de la matrícula anterior. "
                        "Registre una nueva solicitud."
                    ),
                )
            source_period = _fetch_enrollment_period(
                cursor,
                request_item["codigo_periodo_origen"],
            )
            if source_period["tipo"] != request_item["tipo_periodo_origen"]:
                raise HTTPException(
                    status_code=409,
                    detail="El tipo del período de origen cambió desde que se registró la solicitud.",
                )
            target_period = _fetch_enrollment_period(
                cursor,
                request_item["codigo_periodo_homologacion"],
            )
            if target_period["tipo"] != request_item["tipo_periodo_destino"]:
                raise HTTPException(
                    status_code=409,
                    detail="El tipo del período cambió desde que se registró la solicitud.",
                )
            current_subjects = _fetch_target_subjects(cursor, request_item["carrera_destino"])
            current_subject_codes = {item["codigo_materia"] for item in current_subjects}
            approved_subject_codes = {item["codigo_materia"] for item in subjects}
            pensum_changed = not approved_subject_codes.issubset(current_subject_codes)
            if target_period["tipo"] == "H":
                pensum_changed = pensum_changed or current_subject_codes != approved_subject_codes
            if pensum_changed:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "El pénsum de la carrera cambió desde que se registró la solicitud. "
                        "Registre una nueva solicitud para revisar todas las materias."
                    ),
                )

            if not backup:
                snapshot = _capture_modality_snapshot(cursor, request_item)
                backup = _persist_modality_snapshot(
                    request_id=request_id,
                    request_item=request_item,
                    snapshot=snapshot,
                    audit_user=_user_label(current_user),
                )
            source_present = _verify_modality_backup(cursor, request_item, backup)
            header_created, _header_number = _ensure_single_header(
                cursor,
                request_item,
                target_modality,
                target_period["tipo"],
            )
            if source_present:
                source_rows = _fetch_source_enrollments(
                    cursor,
                    request_item["codigo_estud"],
                    request_item["carrera_origen"],
                    request_item["codigo_periodo_origen"],
                    request_item["tipo_periodo_origen"],
                )
                results = _migrate_subjects(
                    cursor,
                    request_item=request_item,
                    subjects=subjects,
                    source_rows=source_rows,
                    user_code=_legacy_user_code(current_user),
                )
                archived = _archive_source_period(cursor, request_item)
            else:
                results = []
                for subject in subjects:
                    existing = _find_target_subject(
                        cursor,
                        request_item,
                        int(subject["codigo_materia"]),
                    )
                    if not existing:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "El origen ya no está activo, pero la matrícula destino está incompleta. "
                                "Revise el respaldo antes de reintentar."
                            ),
                        )
                    mapped = subject.get("materia_origen") is not None
                    recorded_grade = _optional_float(subject.get("nota_origen"))
                    requires_repetition = bool(
                        not mapped and _is_failed_grade(recorded_grade)
                    )
                    results.append(
                        {
                            "codigo_materia": int(subject["codigo_materia"]),
                            "estado": "MIGRADA" if mapped else "EXISTENTE",
                            "num_matricula": _int_value(existing.get("Num_Matricula")) or 1,
                            "observacion": (
                                "Migración verificada en el período destino durante el reintento."
                                if mapped
                                else "Materia destino verificada sin duplicarla durante el reintento."
                            ),
                            "origen_mapeado": mapped,
                            "materia_origen": subject.get("materia_origen"),
                            "nota_origen": recorded_grade,
                            "requiere_repeticion": requires_repetition,
                            "created": False,
                        }
                    )
                archived = {
                    "source_headers_archived": backup["total_cabeceras"],
                    "source_subjects_archived": backup["total_materias"],
                }
            student_modality = _STUDENT_MODALITY_BY_ENROLLMENT.get(
                target_modality["codigo"],
                str(target_modality["codigo"]),
            )
            cursor.execute(
                """
                UPDATE dbo.DATOS_ESTUD
                SET ModalidadEstudio = ?
                WHERE TRY_CONVERT(int, codigo_estud) = ?
                """,
                student_modality,
                request_item["codigo_estud"],
            )
            primary_conn.commit()

        inserted = sum(1 for item in results if item["created"])
        existing = sum(1 for item in results if not item["created"])
        migrated = sum(1 for item in results if item["origen_mapeado"])
        with get_integration_control_connection() as integration_conn:
            cursor = integration_conn.cursor()
            for item in results:
                cursor.execute(
                    """
                    UPDATE sol.SolicitudCambioModalidadMateria
                    SET Estado = ?, NumMatricula = ?, Observacion = ?,
                        MateriaOrigen = ?, NotaOrigen = ?
                    WHERE IdSolicitud = ? AND CodigoMateria = ?
                    """,
                    item["estado"],
                    item["num_matricula"],
                    item["observacion"],
                    item.get("materia_origen"),
                    item.get("nota_origen"),
                    request_id,
                    item["codigo_materia"],
                )
            audit = record_academic_movement(
                cursor,
                request_type="MODALIDAD",
                request_id=request_id,
                action="APLICAR",
                student_code=request_item["codigo_estud"],
                source_career=request_item["carrera_origen"],
                target_career=request_item["carrera_destino"],
                source_period=request_item["codigo_periodo_origen"],
                target_period=request_item["codigo_periodo_homologacion"],
                source_modality=request_item["modalidad_origen"],
                target_modality=request_item["modalidad_destino"],
                backup_headers=backup["total_cabeceras"],
                backup_subjects=backup["total_materias"],
                migrated_subjects=migrated,
                deleted_records=(
                    archived["source_headers_archived"]
                    + archived["source_subjects_archived"]
                ),
                backup_hash=backup["hash_contenido"],
                before={
                    "carrera": request_item["carrera_origen"],
                    "modalidad": request_item["modalidad_origen"],
                    "periodo": request_item["codigo_periodo_origen"],
                    "tipo_periodo": request_item["tipo_periodo_origen"],
                    "cabeceras": backup["total_cabeceras"],
                    "materias": backup["total_materias"],
                },
                after={
                    "carrera": request_item["carrera_destino"],
                    "modalidad": request_item["modalidad_destino"],
                    "periodo": request_item["codigo_periodo_homologacion"],
                    "tipo_periodo": request_item["tipo_periodo_destino"],
                    "materias_migradas": migrated,
                    "materias_repetidas": sum(
                        1 for item in results if item.get("requiere_repeticion")
                    ),
                    "materias_creadas": inserted,
                    "materias_existentes": existing,
                },
                audit_user=_user_label(current_user),
            )
            cursor.execute(
                """
                UPDATE sol.SolicitudCambioModalidad
                SET Estado = N'APLICADA', AplicadoPor = ?, FechaAplicacion = SYSUTCDATETIME(),
                    MateriasMatriculadas = ?, MateriasExistentes = ?, MateriasMigradas = ?,
                    MateriasOrigenRetiradas = ?, CabecerasOrigenRetiradas = ?, CabeceraCreada = ?
                WHERE IdSolicitud = ? AND Estado = N'APROBADA'
                """,
                _user_label(current_user),
                inserted,
                existing,
                migrated,
                archived["source_subjects_archived"],
                archived["source_headers_archived"],
                1 if header_created else 0,
                request_id,
            )
            integration_conn.commit()
        return {
            "ok": True,
            "message": (
                "El cambio de modalidad se aplicó: solo se migraron notas aprobadas por código único; "
                "las materias reprobadas quedaron matriculadas para repetición sin calificaciones y "
                "la matrícula anterior se respaldó en auditoría."
            ),
            "estado": "APLICADA",
            "cabeceras_creadas": 1 if header_created else 0,
            "materias_matriculadas": inserted,
            "materias_existentes": existing,
            "materias_migradas": migrated,
            "materias_repetidas": sum(
                1 for item in results if item.get("requiere_repeticion")
            ),
            "materias_origen_retiradas": archived["source_subjects_archived"],
            "cabeceras_origen_retiradas": archived["source_headers_archived"],
            "respaldo_id": backup["id_respaldo"],
            "auditoria_id": audit["id_movimiento"],
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            if primary_conn is not None:
                primary_conn.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"No se pudo aplicar el cambio de modalidad: {exc}") from exc
    except (RuntimeError, ValueError) as exc:
        try:
            if primary_conn is not None:
                primary_conn.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=409, detail=f"No se pudo validar la migración: {exc}") from exc
