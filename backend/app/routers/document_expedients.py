from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.security import SessionUser, require_roles
from app.routers.practicas_institucionales import _responsible_assignment
from app.services.db import (
    get_connection,
    get_expedient_connection,
    get_finance_connection,
    get_integration_control_connection,
    get_practices_connection,
    get_titulation_connection,
)
from app.services.graph_documents import (
    MAX_DOCUMENT_BYTES,
    complete_upload_session,
    create_upload_session,
    document_record,
    ensure_folder,
    item_by_id,
    item_by_path,
    list_documents,
    mark_upload_error,
    prepare_expedient,
    register_upload_session,
    safe_filename,
    safe_folder_part,
    set_document_origin,
    upload_session,
)


router = APIRouter(prefix="/api/document-expedients", tags=["document-expedients"])

_ACCESS = require_roles("ESTUDIANTE", "DOCENTE", "ACADEMICO", "BIENESTAR", "SECRETARIA", "FINANCIERO", "ADMINISTRADOR")
_REVIEW_ACCESS = require_roles("ACADEMICO", "BIENESTAR", "SECRETARIA", "FINANCIERO", "ADMINISTRADOR")
_ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
    ".zip", ".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4a", ".mp4",
    ".mov", ".mkv", ".webm", ".xml",
}
_MODULE_NAMES = {
    "INGLES": "Inglés",
    "TITULACION": "Titulación",
    "PRACTICAS": "Prácticas preprofesionales",
    "VINCULACION": "Vinculación con la sociedad",
    "BECAS": "Becas",
    "SOLICITUDES": "Solicitudes",
    "FACTURACION": "Facturas",
}
_SCHOLARSHIP_DOCUMENT_TYPES = [
    {"code": "CONTRATO_BECA_FIRMADO", "name": "Contrato de beca firmado"},
]
_INVOICE_DOCUMENT_TYPES = [
    {"code": "FACTURA_XML", "name": "Factura electrónica (XML)"},
    {"code": "RIDE_FACTURA", "name": "RIDE de la factura (PDF)"},
]
_CAREER_CHANGE_DOCUMENT_TYPES = [
    {"code": "RESPALDO_CAMBIO_CARRERA", "name": "Respaldo de cambio de carrera"},
]
_INVOICE_FILE_EXTENSIONS = {
    "FACTURA_XML": ".xml",
    "RIDE_FACTURA": ".pdf",
}


class DocumentUploadPayload(BaseModel):
    identification: str = Field(default="", max_length=30)
    module_code: str = Field(min_length=1, max_length=40)
    origin_id: str = Field(min_length=1, max_length=100)
    document_type_code: str = Field(min_length=1, max_length=80)
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=MAX_DOCUMENT_BYTES)
    content_type: str = Field(default="application/octet-stream", max_length=300)


class DocumentFinalizePayload(BaseModel):
    upload_id: UUID


class DocumentPreparePayload(BaseModel):
    identification: str = Field(default="", max_length=30)
    module_code: str = Field(min_length=1, max_length=40)
    origin_id: str = Field(min_length=1, max_length=100)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _role(value: str) -> str:
    return value.strip().upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")


def _identification(value: Any) -> str:
    return re.sub(r"\D+", "", _clean(value))


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _clean(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _iso_date(value: Any) -> str | None:
    parsed = _date_value(value)
    return parsed.isoformat() if parsed else None


def _ensure_document_upload_window(
    expedient: dict[str, Any],
    enforce_window: bool,
    today: date | None = None,
) -> None:
    if not enforce_window or expedient.get("module_code") not in {"PRACTICAS", "VINCULACION"}:
        return
    start = _date_value(expedient.get("upload_start"))
    end = _date_value(expedient.get("upload_end"))
    if not start or not end:
        raise HTTPException(
            status_code=409,
            detail="Administración debe definir el plazo de carga documental de esta matrícula.",
        )
    current = today or date.today()
    if current < start:
        raise HTTPException(
            status_code=409,
            detail=f"La carga documental se habilitará el {start.isoformat()}.",
        )
    if current > end:
        raise HTTPException(
            status_code=409,
            detail=f"El plazo de carga documental finalizó el {end.isoformat()}.",
        )


def _ensure_teacher_practice_access(
    current_user: SessionUser,
    expedient: dict[str, Any],
    *,
    for_write: bool = False,
) -> None:
    if _role(current_user.rol) != "DOCENTE":
        return
    module = _clean(expedient.get("module_code")).upper()
    if module not in {"PRACTICAS", "VINCULACION"}:
        raise HTTPException(
            status_code=403,
            detail="El docente solo puede gestionar documentos de prácticas o vinculación asignadas.",
        )
    try:
        expediente_id = int(_clean(expedient.get("origin_id")))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="El expediente de prácticas no es válido.") from exc
    if expediente_id <= 0:
        raise HTTPException(status_code=403, detail="El expediente de prácticas no es válido.")

    with get_practices_connection() as conn:
        cursor = conn.cursor()
        if not _use_legacy_practices_schema(cursor):
            raise HTTPException(
                status_code=409,
                detail="La carga docente requiere una asignación individual vigente en el expediente.",
            )
        _responsible_assignment(
            cursor,
            expediente_id,
            current_user,
            require_approval=False,
        )

    if for_write and _clean(expedient.get("status")).upper() in {
        "CERRADO",
        "FINALIZADO",
        "ANULADO",
        "APROBADO",
        "REPROBADO",
    }:
        raise HTTPException(status_code=409, detail="El expediente está cerrado y no admite nuevas cargas.")


def _ensure_document_upload_actor(
    current_user: SessionUser,
    expedient: dict[str, Any],
) -> None:
    normalized_role = _role(current_user.rol)
    module = _clean(expedient.get("module_code")).upper()
    if normalized_role == "DOCENTE":
        _ensure_teacher_practice_access(current_user, expedient, for_write=True)
        return
    if module in {"PRACTICAS", "VINCULACION"}:
        raise HTTPException(
            status_code=403,
            detail="Solo el docente responsable activo puede cargar documentos de prácticas o vinculación.",
        )


def _has_practice_object(cursor: pyodbc.Cursor, name: str) -> bool:
    cursor.execute("SELECT CASE WHEN OBJECT_ID(?) IS NULL THEN 0 ELSE 1 END", name)
    row = cursor.fetchone()
    return bool(row and row[0])


def _use_legacy_practices_schema(cursor: pyodbc.Cursor) -> bool:
    legacy_ready = all(
        _has_practice_object(cursor, object_name)
        for object_name in (
            "cat.tipo_proceso",
            "cat.tipo_documento_practica",
            "pp.expediente_practica",
            "pp.responsable_proceso",
        )
    )
    modern_ready = all(
        _has_practice_object(cursor, object_name)
        for object_name in (
            "cat.TipoProceso",
            "cat.TipoDocumento",
            "exp.Expediente",
            "resp.ResponsableProceso",
        )
    )
    if modern_ready:
        return False
    if legacy_ready:
        return True
    raise RuntimeError(
        "La base de prácticas no contiene una estructura operativa completa "
        "(pp.* ni exp./resp.*)."
    )


def _student_profile(current_user: SessionUser, requested_identification: str = "") -> dict[str, Any]:
    is_student = _role(current_user.rol) == "ESTUDIANTE"
    document = _identification(current_user.cedula if is_student else requested_identification)
    code = current_user.codigo_estud if is_student else None
    if not document and not code:
        raise HTTPException(status_code=400, detail='Indique la cédula del estudiante.')

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (1)
                TRY_CONVERT(BIGINT, D.codigo_estud) AS CodigoEstud,
                REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), D.Cedula_Est))), '-', ''), ' ', '') AS Cedula,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), D.Apellidos_nombre))) AS Estudiante,
                COALESCE(NULLIF(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), D.correointec))), N''),
                         NULLIF(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), D.correo))), N'')) AS Correo,
                TRY_CONVERT(NVARCHAR(100), Ultimo.cod_anio_Basica) AS CodigoCarrera,
                TRY_CONVERT(NVARCHAR(500), C.Nombre_Basica) AS Carrera,
                TRY_CONVERT(NVARCHAR(100), Ultimo.codigo_periodo) AS CodigoPeriodo,
                TRY_CONVERT(VARCHAR(10), D.Estado) AS Estado
            FROM dbo.DATOS_ESTUD D
            OUTER APPLY
            (
                SELECT TOP (1) CX.cod_anio_Basica, CX.codigo_periodo
                FROM dbo.CARRERAXESTUD CX
                WHERE TRY_CONVERT(BIGINT, CX.codigo_estud) = TRY_CONVERT(BIGINT, D.codigo_estud)
                ORDER BY TRY_CONVERT(INT, CX.codigo_periodo) DESC
            ) Ultimo
            LEFT JOIN dbo.CARRERAS C
              ON TRY_CONVERT(INT, C.Cod_AnioBasica) = TRY_CONVERT(INT, Ultimo.cod_anio_Basica)
            WHERE (? IS NOT NULL AND TRY_CONVERT(BIGINT, D.codigo_estud) = ?)
               OR (? <> '' AND REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), D.Cedula_Est))), '-', ''), ' ', '') = ?)
            ORDER BY CASE WHEN ? IS NOT NULL AND TRY_CONVERT(BIGINT, D.codigo_estud) = ? THEN 0 ELSE 1 END
            """,
            code,
            code,
            document,
            document,
            code,
            code,
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='No se encontró al estudiante en INTECBDD.')
    return {
        "code": int(row.CodigoEstud),
        "identification": _clean(row.Cedula),
        "name": _clean(row.Estudiante),
        "email": _clean(row.Correo),
        "career_code": _clean(row.CodigoCarrera),
        "career": _clean(row.Carrera),
        "period_code": _clean(row.CodigoPeriodo),
        "status": _clean(row.Estado),
    }


def _titulation_document_types() -> list[dict[str, str]]:
    fallback = [
        {"code": "DOCUMENTO_HABILITANTE", "name": "Documento habilitante"},
        {"code": "ACTA_GRADO", "name": "Acta de grado"},
        {"code": "ACTA_GRADO_FIRMADA", "name": "Acta de grado firmada"},
        {"code": "TITULO_REGISTRO_SENESCYT", "name": "Registro SENESCYT"},
        {"code": "TITULO_INTEC", "name": "Título"},
    ]
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            if not cursor.execute("SELECT OBJECT_ID(N'cat.TipoDocumentoTitulacion', N'U')").fetchval():
                return fallback
            cursor.execute(
                """
                SELECT COALESCE(NULLIF(Codigo, ''), TipoDocumentoCodigo), Nombre
                FROM cat.TipoDocumentoTitulacion
                WHERE Activo = 1 AND COALESCE(NULLIF(Codigo, ''), TipoDocumentoCodigo) IS NOT NULL
                ORDER BY Orden, Nombre
                """
            )
            rows = [{"code": _clean(row[0]), "name": _clean(row[1])} for row in cursor.fetchall()]
            return rows or fallback
    except (RuntimeError, pyodbc.Error):
        return fallback


def _practice_document_types(process_code: str) -> list[dict[str, str]]:
    with get_practices_connection() as conn:
        cursor = conn.cursor()
        if _use_legacy_practices_schema(cursor):
            cursor.execute(
                """
                SELECT TD.codigo, TD.nombre
                FROM cat.tipo_documento_practica TD
                WHERE TD.activo = 1
                  AND ((? = 'PPF' AND ISNULL(TD.aplica_practicas, 0) = 1)
                    OR (? = 'VIN' AND ISNULL(TD.aplica_vinculacion, 0) = 1))
                ORDER BY TD.orden, TD.nombre
                """,
                process_code,
                process_code,
            )
        else:
            cursor.execute(
                """
                SELECT TD.Codigo, TD.Nombre
                FROM cat.TipoDocumento TD
                INNER JOIN cat.TipoProceso TP ON TP.TipoProcesoId = TD.TipoProcesoId
                WHERE TP.Codigo = ? AND TD.Activo = 1
                ORDER BY TD.Orden, TD.Nombre
                """,
                process_code,
            )
        return [{"code": _clean(row[0]), "name": _clean(row[1])} for row in cursor.fetchall()]


def _invoice_expedient(profile: dict[str, Any]) -> dict[str, Any]:
    student_code = int(profile["code"])
    return {
        "module_code": "FACTURACION",
        "module_name": _MODULE_NAMES["FACTURACION"],
        "origin_id": str(student_code),
        "domain_expedient_id": student_code,
        "expedient_code": f"FACT-{student_code}",
        "status": "ABIERTO",
        "base_origin": "INTECBDD",
        "schema_origin": "dbo",
        "table_origin": "DATOS_ESTUD",
        "document_types": [dict(item) for item in _INVOICE_DOCUMENT_TYPES],
        "upload_enabled": True,
        "upload_message": "",
    }


def _scholarship_expedients(profile: dict[str, Any]) -> list[dict[str, Any]]:
    student_code = _clean(profile.get("code"))
    if not student_code:
        return []

    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            if not cursor.execute("SELECT OBJECT_ID(N'bec.ContratoBeca', N'U')").fetchval():
                return []
            cursor.execute(
                """
                WITH Contratos AS
                (
                    SELECT
                        ContratoBecaId, CodigoPeriodo, Periodo, NumeroContrato,
                        EstadoCodigo, EstadoExpedienteCodigo, FechaGeneracion,
                        ROW_NUMBER() OVER
                        (
                            PARTITION BY CodigoPeriodo
                            ORDER BY ContratoBecaId DESC
                        ) AS Fila
                    FROM bec.ContratoBeca
                    WHERE TRY_CONVERT(nvarchar(50), CodigoEstud) = ?
                )
                SELECT
                    ContratoBecaId, CodigoPeriodo, Periodo, NumeroContrato,
                    EstadoCodigo, EstadoExpedienteCodigo
                FROM Contratos
                WHERE Fila = 1
                ORDER BY FechaGeneracion DESC, ContratoBecaId DESC
                """,
                student_code,
            )
            rows = cursor.fetchall()
    except (RuntimeError, pyodbc.Error):
        return []

    return [
        {
            "module_code": "BECAS",
            "module_name": _MODULE_NAMES["BECAS"],
            "origin_id": f"{student_code}-{_clean(row.CodigoPeriodo)}",
            "domain_expedient_id": int(row.ContratoBecaId),
            "expedient_code": f"BECA-{_clean(row.CodigoPeriodo)}",
            "status": _clean(row.EstadoExpedienteCodigo) or _clean(row.EstadoCodigo),
            "base_origin": "INTEC_FINANZAS_INSTITUCIONAL",
            "schema_origin": "bec",
            "table_origin": "ContratoBeca",
            "period_code": _clean(row.CodigoPeriodo),
            "period_name": _clean(row.Periodo) or _clean(row.CodigoPeriodo),
            "reference": _clean(row.NumeroContrato),
            "document_types": [dict(item) for item in _SCHOLARSHIP_DOCUMENT_TYPES],
            "upload_enabled": False,
            "upload_message": "Cargue el contrato firmado desde Becas > Contratos de beca.",
        }
        for row in rows
        if _clean(row.CodigoPeriodo)
    ]


def _career_change_expedients(profile: dict[str, Any]) -> list[dict[str, Any]]:
    student_code = int(profile["code"])
    document = _identification(profile.get("identification"))
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            if not cursor.execute(
                "SELECT OBJECT_ID(N'sol.SolicitudCambioCarrera', N'U')"
            ).fetchval():
                return []
            cursor.execute(
                """
                SELECT
                    IdSolicitud, Estado, CarreraDestinoNombre,
                    CodigoPeriodoDestino, PeriodoDestinoNombre
                FROM sol.SolicitudCambioCarrera
                WHERE CodigoEstud = ?
                   OR REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Cedula)), '-', ''), ' ', ''), '.', '') = ?
                ORDER BY FechaCreacion DESC, IdSolicitud DESC
                """,
                student_code,
                document,
            )
            rows = cursor.fetchall()
    except (RuntimeError, pyodbc.Error):
        return []

    return [
        {
            "module_code": "SOLICITUDES",
            "module_name": _MODULE_NAMES["SOLICITUDES"],
            "origin_id": str(row.IdSolicitud),
            "domain_expedient_id": int(row.IdSolicitud),
            "expedient_code": f"CAMBIO-CARRERA-{row.IdSolicitud}",
            "status": _clean(row.Estado),
            "base_origin": "INTEC_INTEGRACION_CONTROL",
            "schema_origin": "sol",
            "table_origin": "SolicitudCambioCarrera",
            "period_code": _clean(row.CodigoPeriodoDestino),
            "period_name": _clean(row.PeriodoDestinoNombre),
            "reference": _clean(row.CarreraDestinoNombre),
            "document_types": [dict(item) for item in _CAREER_CHANGE_DOCUMENT_TYPES],
            "upload_enabled": False,
            "upload_message": "El respaldo se carga desde Solicitudes > Cambio de carrera.",
        }
        for row in rows
    ]


def _domain_expedients(profile: dict[str, Any]) -> list[dict[str, Any]]:
    expedients: list[dict[str, Any]] = []
    document = profile["identification"]

    try:
        with get_expedient_connection() as conn:
            cursor = conn.cursor()
            if cursor.execute("SELECT OBJECT_ID(N'ing.ExamenIngles', N'U')").fetchval():
                cursor.execute(
                    """
                    SELECT TOP (1) E.ExamenInglesId, E.ExpedienteEstudiantilId, E.Estado,
                           X.CodigoExpediente
                    FROM ing.ExamenIngles E
                    INNER JOIN exp.ExpedienteEstudiantil X
                      ON X.ExpedienteEstudiantilId = E.ExpedienteEstudiantilId
                    WHERE E.NumeroIdentificacion = ? AND E.Activo = 1
                    ORDER BY E.ExamenInglesId DESC
                    """,
                    document,
                )
                row = cursor.fetchone()
                if row:
                    expedients.append(
                        {
                            "module_code": "INGLES",
                            "module_name": _MODULE_NAMES["INGLES"],
                            "origin_id": str(row.ExamenInglesId),
                            "domain_expedient_id": int(row.ExpedienteEstudiantilId),
                            "expedient_code": _clean(row.CodigoExpediente),
                            "status": _clean(row.Estado),
                            "base_origin": "INTEC_EXPEDIENTE_ESTUDIANTIL",
                            "schema_origin": "ing",
                            "table_origin": "ExamenIngles",
                            "document_types": [],
                            "upload_enabled": False,
                            "upload_message": "La evidencia de Inglés se carga desde Evaluación de Inglés para aplicar el plazo de 15 minutos.",
                        }
                    )
    except (RuntimeError, pyodbc.Error):
        pass

    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT E.ExpedienteId, E.EstadoExpediente, E.NumeroActaGrado
                FROM tit.ExpedienteTitulacion E
                INNER JOIN core.EstudianteRef R ON R.EstudianteRefId = E.EstudianteRefId
                WHERE REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(VARCHAR(30), R.NumeroIdentificacion))), '-', ''), ' ', '') = ?
                ORDER BY E.ExpedienteId DESC
                """,
                document,
            )
            types = _titulation_document_types()
            for row in cursor.fetchall():
                expedients.append(
                    {
                        "module_code": "TITULACION",
                        "module_name": _MODULE_NAMES["TITULACION"],
                        "origin_id": str(row.ExpedienteId),
                        "domain_expedient_id": int(row.ExpedienteId),
                        "expedient_code": _clean(row.NumeroActaGrado) or f"TIT-{row.ExpedienteId}",
                        "status": _clean(row.EstadoExpediente),
                        "base_origin": "TITULACION_INTEC",
                        "schema_origin": "tit",
                        "table_origin": "ExpedienteTitulacion",
                        "document_types": types,
                        "upload_enabled": True,
                        "upload_message": "",
                    }
                )
    except (RuntimeError, pyodbc.Error):
        pass

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            legacy_schema = _use_legacy_practices_schema(cursor)
            if legacy_schema:
                cursor.execute(
                    """
                    SELECT
                        V.expediente_id AS ExpedienteId,
                        V.codigo_expediente AS CodigoExpediente,
                        V.tipo_proceso_codigo AS TipoProceso,
                        V.estado_codigo AS EstadoCodigo,
                        V.estado_expediente AS EstadoNombre,
                        E.fecha_inicio AS FechaInicioCarga,
                        E.fecha_fin AS FechaFinCarga
                    FROM pp.vw_admin_expedientes_control V
                    INNER JOIN pp.expediente_practica E ON E.expediente_id = V.expediente_id
                    WHERE TRY_CONVERT(BIGINT, V.codigo_estud) = ?
                      AND V.tipo_proceso_codigo IN ('PPF', 'VIN')
                    ORDER BY V.expediente_id DESC
                    """,
                    profile["code"],
                )
            else:
                cursor.execute(
                    """
                    SELECT E.ExpedienteId, E.CodigoExpediente, TP.Codigo AS TipoProceso,
                           EE.Codigo AS EstadoCodigo, EE.Nombre AS EstadoNombre,
                           NULL AS FechaInicioCarga, NULL AS FechaFinCarga
                    FROM exp.Expediente E
                    INNER JOIN cat.TipoProceso TP ON TP.TipoProcesoId = E.TipoProcesoId
                    INNER JOIN cat.EstadoExpediente EE ON EE.EstadoExpedienteId = E.EstadoExpedienteId
                    WHERE TRY_CONVERT(BIGINT, E.CodigoEstud) = ? AND E.Activo = 1
                      AND TP.Codigo IN ('PPF', 'VIN')
                    ORDER BY E.ExpedienteId DESC
                    """,
                    profile["code"],
                )
            practice_rows = cursor.fetchall()
            type_cache = {
                "PPF": _practice_document_types("PPF"),
                "VIN": _practice_document_types("VIN"),
            }
            for row in practice_rows:
                is_practice = _clean(row.TipoProceso).upper() == "PPF"
                module = "PRACTICAS" if is_practice else "VINCULACION"
                expedients.append(
                    {
                        "module_code": module,
                        "module_name": _MODULE_NAMES[module],
                        "origin_id": str(row.ExpedienteId),
                        "domain_expedient_id": int(row.ExpedienteId),
                        "expedient_code": _clean(row.CodigoExpediente) or f"{row.TipoProceso}-{row.ExpedienteId}",
                        "status": _clean(row.EstadoNombre) or _clean(row.EstadoCodigo),
                        "base_origin": "INTEC_PRACTICAS_PREPROFESIONALES",
                        "schema_origin": "pp" if legacy_schema else "exp",
                        "table_origin": "expediente_practica" if legacy_schema else "Expediente",
                        "document_types": type_cache[_clean(row.TipoProceso).upper()],
                        "upload_enabled": True,
                        "upload_message": "",
                        "upload_start": _iso_date(row.FechaInicioCarga),
                        "upload_end": _iso_date(row.FechaFinCarga),
                    }
                )
    except (RuntimeError, pyodbc.Error):
        pass

    expedients.extend(_scholarship_expedients(profile))
    expedients.extend(_career_change_expedients(profile))
    expedients.append(_invoice_expedient(profile))
    return expedients


def _context_payload(profile: dict[str, Any], current_user: SessionUser) -> dict[str, Any]:
    expedients = _domain_expedients(profile)
    normalized_role = _role(current_user.rol)
    if normalized_role == "DOCENTE":
        assigned_expedients: list[dict[str, Any]] = []
        for expedient in expedients:
            try:
                _ensure_teacher_practice_access(current_user, expedient)
            except HTTPException:
                continue
            assigned_expedients.append(expedient)
        if not assigned_expedients:
            raise HTTPException(
                status_code=403,
                detail="El estudiante no tiene un expediente de prácticas asignado a este docente.",
            )
        expedients = assigned_expedients

    for expedient in expedients:
        if expedient["module_code"] in {"PRACTICAS", "VINCULACION"}:
            if normalized_role != "DOCENTE":
                expedient["upload_enabled"] = False
                expedient["upload_message"] = (
                    "Solo el docente responsable asignado puede cargar la documentación; el estudiante conserva acceso de consulta."
                )
            else:
                try:
                    _ensure_document_upload_window(expedient, True)
                except HTTPException as exc:
                    expedient["upload_enabled"] = False
                    expedient["upload_message"] = str(exc.detail)
        elif normalized_role == "ESTUDIANTE" and expedient["module_code"] == "TITULACION":
            expedient["upload_enabled"] = False
            expedient["upload_message"] = (
                "Los documentos oficiales de titulación son cargados por Secretaría o el área Académica."
            )
    graph_rows = list_documents(profile["identification"])
    documents_by_origin: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in graph_rows:
        if row.get("DocumentoGraphId") is None:
            continue
        key = (_clean(row.get("TipoExpedienteGraphCodigo")), _clean(row.get("OrigenId")))
        documents_by_origin.setdefault(key, []).append(
            {
                "document_graph_id": int(row["DocumentoGraphId"]),
                "document_type_code": _clean(row.get("TipoDocumentoCodigo")),
                "domain_document_id": _clean(row.get("DocumentoOrigenId")),
                "name": _clean(row.get("NombreArchivo")),
                "content_type": _clean(row.get("ContentType")),
                "size": int(row.get("TamanoBytes") or 0),
                "version": int(row.get("VersionActual") or 1),
                "status": _clean(row.get("EstadoDocumentoGraphCodigo")),
                "uploaded_at": _iso(row.get("FechaCarga")),
                "uploaded_by": _clean(row.get("UsuarioCarga")),
            }
        )
    for expedient in expedients:
        expedient["documents"] = documents_by_origin.get(
            (expedient["module_code"], expedient["origin_id"]),
            [],
        )

    existing_modules = {item["module_code"] for item in expedients}
    for module, name in _MODULE_NAMES.items():
        if module not in existing_modules:
            expedients.append(
                {
                    "module_code": module,
                    "module_name": name,
                    "origin_id": "",
                    "domain_expedient_id": None,
                    "expedient_code": "",
                    "status": "SIN_EXPEDIENTE",
                    "document_types": [],
                    "documents": [],
                    "upload_enabled": False,
                    "upload_message": "Primero debe abrirse el expediente en el módulo correspondiente.",
                }
            )
    expedients.sort(key=lambda item: list(_MODULE_NAMES).index(item["module_code"]))
    return {
        "student": profile,
        "expedients": expedients,
        "total_expedients": sum(1 for item in expedients if item["origin_id"]),
        "total_documents": sum(len(item["documents"]) for item in expedients),
        "max_file_bytes": MAX_DOCUMENT_BYTES,
    }


def _validate_origin(profile: dict[str, Any], module_code: str, origin_id: str) -> dict[str, Any]:
    module = _clean(module_code).upper()
    for item in _domain_expedients(profile):
        if item["module_code"] == module and item["origin_id"] == _clean(origin_id):
            return item
    raise HTTPException(status_code=404, detail="El expediente indicado no pertenece al estudiante.")


def _validate_document_type(expedient: dict[str, Any], document_type_code: str) -> str:
    code = _clean(document_type_code).upper()
    valid_codes = {item["code"].upper() for item in expedient.get("document_types", [])}
    if not expedient.get("upload_enabled"):
        raise HTTPException(status_code=409, detail=expedient.get("upload_message") or "La carga no está habilitada.")
    if code not in valid_codes:
        raise HTTPException(status_code=400, detail='Seleccione un tipo documental válido para el expediente.')
    return code


def _validate_upload_filename(
    expedient: dict[str, Any],
    document_type_code: str,
    filename: str,
) -> str:
    try:
        normalized = safe_filename(filename, _ALLOWED_EXTENSIONS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if expedient.get("module_code") != "FACTURACION":
        return normalized
    expected_extension = _INVOICE_FILE_EXTENSIONS.get(document_type_code)
    if expected_extension and not normalized.lower().endswith(expected_extension):
        document_name = next(
            (
                item["name"]
                for item in _INVOICE_DOCUMENT_TYPES
                if item["code"] == document_type_code
            ),
            document_type_code,
        )
        raise HTTPException(
            status_code=400,
            detail=f"{document_name} debe cargarse en formato {expected_extension.upper()}.",
        )
    return normalized


def _register_domain_document(
    session: dict[str, Any],
    graph_document: dict[str, Any],
    graph_item: dict[str, Any],
    audit_user: str,
) -> int:
    module = _clean(session["TipoExpedienteGraphCodigo"])
    origin_id = int(session["OrigenId"])
    type_code = _clean(session["TipoDocumentoCodigo"])
    name = _clean(session["NombreArchivoOriginal"])
    web_url = _clean(graph_document.get("graph_web_url"))
    content_type = _clean(graph_document.get("content_type"))
    size = int(graph_document.get("size") or 0)

    if module == "FACTURACION":
        return int(graph_document["document_graph_id"])

    if module == "TITULACION":
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1) DocumentoId, VersionDocumento
                FROM doc.DocumentoExpediente
                WHERE ExpedienteId = ? AND TipoDocumentoCodigo = ? AND Activo = 1
                ORDER BY DocumentoId DESC
                """,
                origin_id,
                type_code,
            )
            current = cursor.fetchone()
            if current:
                document_id = int(current.DocumentoId)
                cursor.execute(
                    """
                    UPDATE doc.DocumentoExpediente
                       SET NombreArchivo = ?, RutaNube = ?, EstadoDocumento = 'CARGADO',
                           VersionDocumento = ISNULL(VersionDocumento, 0) + 1,
                           UsuarioCarga = ?, FechaCarga = SYSUTCDATETIME(),
                           Observacion = N'Archivo almacenado y trazado mediante INTEC_GRAPH_INTEGRACION.'
                     WHERE DocumentoId = ?
                    """,
                    name,
                    web_url,
                    audit_user,
                    document_id,
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO doc.DocumentoExpediente
                        (ExpedienteId, TipoDocumentoCodigo, NombreArchivo, RutaNube,
                         EsFirmadoElectronico, EstadoDocumento, VersionDocumento,
                         UsuarioCarga, Observacion, Activo)
                    OUTPUT INSERTED.DocumentoId
                    VALUES (?, ?, ?, ?, 0, 'CARGADO', 1, ?,
                            N'Archivo almacenado y trazado mediante INTEC_GRAPH_INTEGRACION.', 1)
                    """,
                    origin_id,
                    type_code,
                    name,
                    web_url,
                    audit_user,
                )
                document_id = int(cursor.fetchone()[0])
            conn.commit()
            return document_id

    if module in {"PRACTICAS", "VINCULACION"}:
        process = "PPF" if module == "PRACTICAS" else "VIN"
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_practices_schema(cursor):
                extension = Path(name).suffix.lower().lstrip(".")
                cursor.execute(
                    """
                    EXEC pp.sp_registrar_documento
                        @expediente_id = ?,
                        @tipo_documento_codigo = ?,
                        @nombre_archivo = ?,
                        @ruta_archivo = ?,
                        @extension = ?,
                        @mime_type = ?,
                        @hash_archivo = NULL,
                        @tamanio_bytes = ?,
                        @numero_paginas = NULL,
                        @fecha_documento = NULL,
                        @firmado = 0,
                        @validado = 0,
                        @observacion = ?,
                        @usuario_registro = ?
                    """,
                    origin_id,
                    type_code,
                    name,
                    web_url,
                    extension,
                    content_type or "application/octet-stream",
                    size,
                    "Archivo almacenado y trazado mediante INTEC_GRAPH_INTEGRACION.",
                    audit_user,
                )
                row = cursor.fetchone()
                document_id = int(getattr(row, "documento_id", 0) or 0) if row else 0
                if not document_id:
                    cursor.execute(
                        """
                        SELECT TOP (1) DP.documento_id
                        FROM pp.documento_practica DP
                        INNER JOIN cat.tipo_documento_practica TD
                          ON TD.tipo_documento_id = DP.tipo_documento_id
                        WHERE DP.expediente_id = ? AND TD.codigo = ?
                        ORDER BY DP.fecha_registro DESC, DP.documento_id DESC
                        """,
                        origin_id,
                        type_code,
                    )
                    stored = cursor.fetchone()
                    document_id = int(stored[0]) if stored else 0
                if not document_id:
                    raise RuntimeError("La base de prácticas no confirmó el documento registrado.")
                conn.commit()
                return document_id

            cursor.execute(
                """
                SELECT TD.TipoDocumentoId
                FROM cat.TipoDocumento TD
                INNER JOIN cat.TipoProceso TP ON TP.TipoProcesoId = TD.TipoProcesoId
                WHERE TD.Codigo = ? AND TP.Codigo = ? AND TD.Activo = 1
                """,
                type_code,
                process,
            )
            type_row = cursor.fetchone()
            cursor.execute("SELECT EstadoDocumentoId FROM cat.EstadoDocumento WHERE Codigo = 'CARGADO' AND Activo = 1")
            state_row = cursor.fetchone()
            if not type_row or not state_row:
                raise RuntimeError('Faltan catálogos documentales de Prácticas/Vinculación.')
            cursor.execute(
                """
                SELECT TOP (1) DocumentoId, VersionActual
                FROM doc.DocumentoExpediente
                WHERE ExpedienteId = ? AND TipoDocumentoId = ? AND Activo = 1
                ORDER BY DocumentoId DESC
                """,
                origin_id,
                int(type_row[0]),
            )
            current = cursor.fetchone()
            if current:
                document_id = int(current.DocumentoId)
                cursor.execute(
                    """
                    UPDATE doc.DocumentoExpediente
                       SET EstadoDocumentoId = ?, NombreArchivo = ?, RutaArchivo = ?,
                           VersionActual = ISNULL(VersionActual, 0) + 1,
                           ObservacionActual = N'Archivo almacenado y trazado mediante INTEC_GRAPH_INTEGRACION.',
                           FechaCarga = SYSUTCDATETIME(), UsuarioCarga = ?
                     WHERE DocumentoId = ?
                    """,
                    int(state_row[0]),
                    name,
                    web_url,
                    audit_user,
                    document_id,
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO doc.DocumentoExpediente
                        (ExpedienteId, TipoDocumentoId, EstadoDocumentoId, NombreArchivo,
                         RutaArchivo, VersionActual, ObservacionActual, FechaCarga,
                         UsuarioCarga, Activo)
                    OUTPUT INSERTED.DocumentoId
                    VALUES (?, ?, ?, ?, ?, 1,
                            N'Archivo almacenado y trazado mediante INTEC_GRAPH_INTEGRACION.',
                            SYSUTCDATETIME(), ?, 1)
                    """,
                    origin_id,
                    int(type_row[0]),
                    int(state_row[0]),
                    name,
                    web_url,
                    audit_user,
                )
                document_id = int(cursor.fetchone()[0])
            conn.commit()
            return document_id

    raise RuntimeError('El módulo no admite carga desde el expediente documental general.')


def _can_access_document(current_user: SessionUser, record: dict[str, Any]) -> bool:
    role = _role(current_user.rol)
    if role == "DOCENTE":
        try:
            _ensure_teacher_practice_access(
                current_user,
                {
                    "module_code": record.get("TipoExpedienteGraphCodigo"),
                    "origin_id": record.get("OrigenId"),
                },
            )
        except (HTTPException, RuntimeError, pyodbc.Error):
            return False
        return True
    if role != "ESTUDIANTE":
        return True
    return _identification(current_user.cedula) == _identification(record.get("NumeroIdentificacion"))


@router.get("/students")
def search_students(
    current_user: Annotated[SessionUser, Depends(_REVIEW_ACCESS)],
    search: Annotated[str, Query(min_length=2, max_length=120)],
) -> dict[str, Any]:
    del current_user
    term = _clean(search)
    pattern = f"%{term}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (30)
                TRY_CONVERT(BIGINT, D.codigo_estud) AS CodigoEstud,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), D.Apellidos_nombre))) AS Estudiante,
                REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), D.Cedula_Est))), '-', ''), ' ', '') AS Cedula,
                TRY_CONVERT(VARCHAR(10), D.Estado) AS Estado
            FROM dbo.DATOS_ESTUD D
            WHERE TRY_CONVERT(NVARCHAR(500), D.Apellidos_nombre) LIKE ?
               OR TRY_CONVERT(VARCHAR(30), D.Cedula_Est) LIKE ?
               OR TRY_CONVERT(VARCHAR(30), D.codigo_estud) LIKE ?
            ORDER BY D.Apellidos_nombre
            """,
            pattern,
            pattern,
            pattern,
        )
        items = [
            {
                "code": int(row.CodigoEstud),
                "name": _clean(row.Estudiante),
                "identification": _clean(row.Cedula),
                "status": _clean(row.Estado),
            }
            for row in cursor.fetchall()
            if row.CodigoEstud is not None
        ]
    return {"items": items, "total": len(items)}


@router.get("/context")
def expedient_context(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    identification: Annotated[str, Query(max_length=30)] = "",
) -> dict[str, Any]:
    if _role(current_user.rol) == "ESTUDIANTE" and identification and _identification(identification) != _identification(current_user.cedula):
        raise HTTPException(status_code=403, detail="El estudiante solo puede consultar su propio expediente.")
    return _context_payload(_student_profile(current_user, identification), current_user)


@router.post("/prepare")
def prepare_document_expedient(
    payload: DocumentPreparePayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    is_student = _role(current_user.rol) == "ESTUDIANTE"
    if is_student and payload.identification and _identification(payload.identification) != _identification(current_user.cedula):
        raise HTTPException(status_code=403, detail="El estudiante solo puede preparar su propio expediente.")
    module_code = _clean(payload.module_code).upper()
    if module_code not in {"PRACTICAS", "VINCULACION"}:
        raise HTTPException(status_code=400, detail="Este proceso solo prepara expedientes de prácticas o vinculación.")

    profile = _student_profile(current_user, payload.identification)
    expedient = _validate_origin(profile, module_code, payload.origin_id)
    _ensure_document_upload_actor(current_user, expedient)
    _ensure_document_upload_window(expedient, True)
    try:
        graph_expedient = prepare_expedient(
            module_code=expedient["module_code"],
            identification=profile["identification"],
            student_code=profile["code"],
            student_name=profile["name"],
            student_email=profile["email"],
            base_origin=expedient["base_origin"],
            schema_origin=expedient["schema_origin"],
            table_origin=expedient["table_origin"],
            origin_id=expedient["origin_id"],
            expedient_code=expedient["expedient_code"],
            audit_user=current_user.login,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Microsoft Graph no pudo preparar el expediente: {exc}") from exc
    except (RuntimeError, ValueError, pyodbc.Error) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo preparar el expediente documental: {exc}") from exc

    return {
        "ok": True,
        "expedient_graph_id": int(graph_expedient["expedient_graph_id"]),
        "folder_path": _clean(graph_expedient.get("folder_path")),
        "folder_item_id": _clean(graph_expedient.get("folder_item_id")),
        "web_url": _clean(graph_expedient.get("web_url")),
        "student_folder_reused": bool(graph_expedient.get("student_folder_reused")),
        "message": (
            "Expediente vinculado con la carpeta existente del estudiante en Microsoft 365."
            if graph_expedient.get("student_folder_reused")
            else "Expediente creado correctamente en Microsoft 365."
        ),
    }


@router.post("/upload-session")
def start_document_upload(
    payload: DocumentUploadPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    is_student = _role(current_user.rol) == "ESTUDIANTE"
    is_teacher = _role(current_user.rol) == "DOCENTE"
    if is_student and payload.identification and _identification(payload.identification) != _identification(current_user.cedula):
        raise HTTPException(status_code=403, detail="El estudiante solo puede cargar en su propio expediente.")
    profile = _student_profile(current_user, payload.identification)
    expedient = _validate_origin(profile, payload.module_code, payload.origin_id)
    _ensure_document_upload_actor(current_user, expedient)
    _ensure_document_upload_window(expedient, is_student or is_teacher)
    if is_student and expedient["module_code"] == "TITULACION":
        raise HTTPException(
            status_code=403,
            detail='Los documentos oficiales de titulación son cargados por Secretaría o el área Académica.',
        )
    type_code = _validate_document_type(expedient, payload.document_type_code)
    filename = _validate_upload_filename(expedient, type_code, payload.filename)

    session_id = uuid4()
    try:
        graph_expedient = prepare_expedient(
            module_code=expedient["module_code"],
            identification=profile["identification"],
            student_code=profile["code"],
            student_name=profile["name"],
            student_email=profile["email"],
            base_origin=expedient["base_origin"],
            schema_origin=expedient["schema_origin"],
            table_origin=expedient["table_origin"],
            origin_id=expedient["origin_id"],
            expedient_code=expedient["expedient_code"],
            audit_user=current_user.login,
        )
        cloud_name = f"{type_code}-{str(session_id)[:8]}-{filename}"
        type_name = next(
            (
                _clean(item.get("name"))
                for item in expedient.get("document_types", [])
                if _clean(item.get("code")).upper() == type_code
            ),
            type_code,
        )
        document_folder = safe_folder_part(
            f"{type_code} - {type_name}",
            type_code,
            max_length=80,
        )
        upload_folder = f"{graph_expedient['folder_path']}/{document_folder}"
        ensure_folder(upload_folder)
        graph_path = f"{upload_folder}/{cloud_name}"
        graph_session = create_upload_session(graph_path)
        upload_url = _clean(graph_session.get("uploadUrl"))
        if not upload_url:
            raise RuntimeError("Microsoft Graph no devolvió una URL de carga.")
        register_upload_session(
            session_id=session_id,
            expedient_graph_id=int(graph_expedient["expedient_graph_id"]),
            document_type_code=type_code,
            original_filename=filename,
            cloud_filename=cloud_name,
            graph_path=graph_path,
            content_type=payload.content_type,
            expected_size=payload.size,
            upload_url=upload_url,
            expires_at=graph_session.get("expirationDateTime"),
            audit_user=current_user.login,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Microsoft Graph no pudo preparar la carga: {exc}") from exc
    except (RuntimeError, ValueError, pyodbc.Error) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo preparar el expediente documental: {exc}") from exc

    return {
        "upload_id": str(session_id),
        "upload_url": upload_url,
        "expires_at": graph_session.get("expirationDateTime"),
        "chunk_size": 10 * 1024 * 1024,
        "max_file_bytes": MAX_DOCUMENT_BYTES,
    }


@router.post("/finalize")
def finalize_document_upload(
    payload: DocumentFinalizePayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    session = upload_session(payload.upload_id)
    if not session:
        raise HTTPException(status_code=404, detail='No existe la sesión de carga indicada.')
    session_module = _clean(session.get("TipoExpedienteGraphCodigo")).upper()
    if session_module in {"PRACTICAS", "VINCULACION"} and _role(current_user.rol) != "DOCENTE":
        raise HTTPException(
            status_code=403,
            detail="Solo el docente responsable activo puede finalizar cargas de prácticas o vinculación.",
        )
    if _role(current_user.rol) == "ESTUDIANTE" and _identification(current_user.cedula) != _identification(session["NumeroIdentificacion"]):
        raise HTTPException(status_code=403, detail='La sesión no pertenece al estudiante autenticado.')
    if _role(current_user.rol) == "DOCENTE":
        if _clean(session.get("UsuarioCarga")).casefold() != _clean(current_user.login).casefold():
            raise HTTPException(status_code=403, detail="La sesión de carga no pertenece al docente autenticado.")
        profile = _student_profile(current_user, _clean(session.get("NumeroIdentificacion")))
        expedient = _validate_origin(
            profile,
            _clean(session.get("TipoExpedienteGraphCodigo")),
            _clean(session.get("OrigenId")),
        )
        _ensure_document_upload_actor(current_user, expedient)
        _ensure_document_upload_window(expedient, True)
    if _clean(session["EstadoDocumentoGraphCodigo"]) == "CARGADO":
        raise HTTPException(status_code=409, detail="La carga ya fue finalizada.")
    try:
        graph_item = item_by_path(_clean(session["RutaGraph"]))
        if not graph_item:
            raise HTTPException(status_code=409, detail="Microsoft Graph aun no confirma el archivo completo.")
        graph_document = complete_upload_session(
            session_id=payload.upload_id,
            graph_item=graph_item,
            edit_deadline=None,
            audit_user=current_user.login,
            append_document=_clean(session["TipoExpedienteGraphCodigo"]) == "FACTURACION",
        )
        domain_document_id = _register_domain_document(session, graph_document, graph_item, current_user.login)
        set_document_origin(int(graph_document["document_graph_id"]), domain_document_id)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo verificar el archivo en Microsoft Graph: {exc}") from exc
    except (RuntimeError, ValueError, pyodbc.Error) as exc:
        try:
            mark_upload_error(payload.upload_id, str(exc), current_user.login)
        except (RuntimeError, pyodbc.Error):
            pass
        raise HTTPException(status_code=500, detail=f"No se pudo relacionar el documento con su expediente: {exc}") from exc
    return {
        "ok": True,
        "document_graph_id": int(graph_document["document_graph_id"]),
        "domain_document_id": domain_document_id,
        "version": int(graph_document["version"]),
        "message": "Documento cargado y relacionado correctamente.",
    }


@router.get("/files/{document_graph_id}/open")
def open_document(
    document_graph_id: int,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> RedirectResponse:
    record = document_record(document_graph_id)
    if not record or not _can_access_document(current_user, record):
        raise HTTPException(status_code=404, detail="No existe el documento solicitado.")
    item = item_by_id(_clean(record.get("GraphItemId")))
    url = _clean((item or {}).get("webUrl")) or _clean(record.get("GraphWebUrl"))
    if not url:
        raise HTTPException(status_code=404, detail='El archivo no está disponible en Microsoft 365.')
    return RedirectResponse(url=url, status_code=307)


@router.get("/files/{document_graph_id}/download")
def download_document(
    document_graph_id: int,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> RedirectResponse:
    record = document_record(document_graph_id)
    if not record or not _can_access_document(current_user, record):
        raise HTTPException(status_code=404, detail="No existe el documento solicitado.")
    item = item_by_id(_clean(record.get("GraphItemId")))
    download_url = _clean((item or {}).get("@microsoft.graph.downloadUrl"))
    if not download_url:
        raise HTTPException(status_code=404, detail="Microsoft Graph no entrego una URL temporal de descarga.")
    return RedirectResponse(url=download_url, status_code=307)
