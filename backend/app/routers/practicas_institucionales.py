from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import pyodbc
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection, get_practices_connection, get_titulation_connection
from app.services.practices_operations import (
    effective_process_configuration,
    ensure_operations_schema,
    is_approved_practice_outcome,
    record_evaluation_history,
    save_titulation_reconciliation,
    update_compliance_enrollment_status,
    upsert_compliance_enrollment,
    write_operations_audit,
)

router = APIRouter(prefix="/api/practicas", tags=["practicas-institucionales"])

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _BACKEND_ROOT / "uploads" / "practicas"
_MAX_UPLOAD_SIZE = 12 * 1024 * 1024

_ADMIN_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE", "SECRETARIA")
_STUDENT_ACCESS = require_roles("ESTUDIANTE", "ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE")
_DOCENTE_ACCESS = require_roles("DOCENTE")
_RESPONSIBLE_ACCESS = require_roles(
    "DOCENTE",
    "ADMINISTRADOR",
    "ACADEMICO",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "SECRETARIA",
)
_ALL_ACCESS = require_roles(
    "ADMINISTRADOR",
    "ACADEMICO",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "SECRETARIA",
    "ESTUDIANTE",
    "DOCENTE",
)

PROCESS_LABELS = {
    "PPF": "Prácticas laborales/preprofesionales",
    "VIN": "Vinculación con la sociedad",
}

_PROCESS_REQUIREMENTS = {
    "PPF": {
        "hours": 240.0,
        "documents": (
            "CARTA_COMPROMISO",
            "REGISTRO_ASISTENCIA",
            "REGISTRO_ACTIVIDADES",
            "EVALUACION_CUALITATIVA",
            "CEDULA_ESTUDIANTE",
        ),
    },
    "VIN": {
        "hours": 60.0,
        "documents": (
            "ANEXO_1_GUION",
            "ANEXO_2_CESION_DERECHOS",
            "VIDEO_VINCULACION",
            "EVIDENCIA_VINCULACION",
        ),
    },
}

_COMPLETION_STATES = {"APROBADO", "VALIDADO", "FINALIZADO", "CERRADO"}
_ADMIN_ROLES = {"ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE", "SECRETARIA"}
_REVIEW_EXPEDIENT_STATE_BY_DECISION = {
    "APROBAR": "EN_REVISION",
    "OBSERVAR": "OBSERVADO",
    "RECHAZAR": "REPROBADO",
}


class CreateExpedientePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_estud: int | None = None
    codigo_carrera: str | None = None
    codigo_periodo: str | None = None
    observacion: str | None = None


class ResponsablePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    expediente_id: int | None = None
    nombre_responsable: str = Field(min_length=3, max_length=250)
    rol_responsable: str = Field(default="RESPONSABLE", max_length=50)
    codigo_docente: str | None = Field(default=None, max_length=50)
    cedula_responsable: str | None = Field(default=None, max_length=20)
    correo_responsable: str | None = Field(default=None, max_length=250)


class PeriodoResponsablePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_periodo: str = Field(min_length=1, max_length=50)
    codigo_periodo_origen: str | None = Field(default=None, max_length=50)
    nombre_responsable: str = Field(min_length=3, max_length=250)
    rol_responsable: str = Field(default="RESPONSABLE", max_length=50)
    codigo_docente: str = Field(min_length=1, max_length=50)
    cedula_responsable: str | None = Field(default=None, max_length=20)
    correo_responsable: str | None = Field(default=None, max_length=250)
    estudiantes: list[int] = Field(default_factory=list)


class InscripcionPracticaEstudiantePayload(BaseModel):
    codigo_estud: int = Field(gt=0)
    codigo_carrera: str = Field(min_length=1, max_length=50)
    codigo_periodo_origen: str = Field(min_length=1, max_length=50)


class InscripcionCumplimientoPayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_periodo: str = Field(min_length=1, max_length=50)
    fecha_inicio_carga: date
    fecha_fin_carga: date
    estudiantes: list[InscripcionPracticaEstudiantePayload] = Field(default_factory=list)
    observacion: str | None = Field(default=None, max_length=500)


# Alias temporales para clientes internos que aún importan los nombres anteriores.
MatriculaPracticaEstudiantePayload = InscripcionPracticaEstudiantePayload
MatriculaPracticasPayload = InscripcionCumplimientoPayload


class AsignacionResponsablePracticasPayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_periodo: str = Field(min_length=1, max_length=50)
    nombre_responsable: str = Field(min_length=3, max_length=250)
    rol_responsable: str = Field(default="RESPONSABLE", max_length=50)
    codigo_docente: str = Field(min_length=1, max_length=50)
    cedula_responsable: str | None = Field(default=None, max_length=20)
    correo_responsable: str | None = Field(default=None, max_length=250)
    expediente_ids: list[int] = Field(default_factory=list)


class AssignResponsablePayload(BaseModel):
    responsable_proceso_id: int


class AutorizacionPracticaPayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_estud: int
    codigo_periodo: str = Field(min_length=1, max_length=50)


class ExpedienteReviewPayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    decision: str = Field(pattern="^(APROBAR|OBSERVAR|RECHAZAR)$")
    horas_verificadas: float = Field(ge=0, le=10000)
    documentos_corroborados: bool = False
    observacion: str | None = Field(default=None, max_length=1000)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _active_teacher_by_code(teacher_code: str) -> dict[str, str] | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1
                TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
                TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula,
                COALESCE(
                    NULLIF(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre), N''),
                    NULLIF(TRY_CONVERT(nvarchar(4000), active_user.Descripcion), N''),
                    NULLIF(TRY_CONVERT(nvarchar(255), active_user.login), N'')
                ) AS nombre,
                COALESCE(
                    NULLIF(TRY_CONVERT(nvarchar(255), d.correo), N''),
                    NULLIF(TRY_CONVERT(nvarchar(255), d.correop), N''),
                    NULLIF(TRY_CONVERT(nvarchar(255), active_user.login), N'')
                ) AS correo
            FROM dbo.DATOSDOCENTE d
            CROSS APPLY (
                SELECT TOP 1 u.login, u.Descripcion, u.Estado
                FROM dbo.USUARIOS u
                WHERE TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
                  AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(20), u.Estado), N'')))) = N'A'
                ORDER BY TRY_CONVERT(nvarchar(255), u.login)
            ) active_user
            WHERE TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, ?)
            """,
            teacher_code,
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "codigo_doc": _clean(row.codigo_doc),
            "cedula": _clean(row.cedula),
            "nombre": _clean(row.nombre),
            "correo": _clean(row.correo),
        }


def _row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [column[0] for column in cursor.description or []]
    return {column: getattr(row, column) for column in columns}


def _fetch_all(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


def _has_object(cursor: pyodbc.Cursor, name: str) -> bool:
    cursor.execute("SELECT CASE WHEN OBJECT_ID(?) IS NULL THEN 0 ELSE 1 END", name)
    row = cursor.fetchone()
    return bool(row and row[0])


def _has_column(cursor: pyodbc.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute("SELECT CASE WHEN COL_LENGTH(?, ?) IS NULL THEN 0 ELSE 1 END", table_name, column_name)
    row = cursor.fetchone()
    return bool(row and row[0])


def _use_legacy_schema(cursor: pyodbc.Cursor) -> bool:
    legacy_ready = all(
        _has_object(cursor, object_name)
        for object_name in (
            "cat.tipo_proceso",
            "cat.tipo_documento_practica",
            "pp.expediente_practica",
            "pp.responsable_proceso",
        )
    )
    modern_ready = all(
        _has_object(cursor, object_name)
        for object_name in (
            "cat.TipoProceso",
            "cat.TipoDocumento",
            "exp.Expediente",
            "resp.ResponsableProceso",
        )
    )

    # Algunas instalaciones contienen los catálogos V4 y el módulo operativo
    # completo V6 simultáneamente. La selección depende de la estructura entera,
    # no solo de la capitalización del catálogo.
    if legacy_ready and not modern_ready:
        return True
    if modern_ready:
        return False
    if legacy_ready:
        return True
    raise RuntimeError(
        "La base de prácticas no contiene una estructura operativa completa "
        "(pp.* ni exp./resp.*)."
    )


def _ensure_period_designation_table(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID('pp.designacion_periodo_responsable', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.designacion_periodo_responsable (
                designacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo_proceso_id tinyint NOT NULL,
                codigo_periodo numeric(18,0) NOT NULL,
                codigo_periodo_origen numeric(18,0) NULL,
                codigo_docente decimal(18,0) NOT NULL,
                cedula_responsable varchar(50) NULL,
                nombre_responsable nvarchar(220) NOT NULL,
                correo_responsable nvarchar(180) NULL,
                rol_responsable nvarchar(180) NULL,
                cumple_requisitos bit NOT NULL CONSTRAINT DF_designacion_periodo_cumple DEFAULT (0),
                activo bit NOT NULL CONSTRAINT DF_designacion_periodo_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                periodo_origen_snapshot nvarchar(220) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_designacion_periodo_fecha DEFAULT (sysdatetime()),
                usuario_modifica varchar(100) NULL,
                fecha_modifica datetime2(3) NULL
            );
        END
        IF OBJECT_ID('pp.designacion_periodo_estudiante', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.designacion_periodo_estudiante (
                designacion_estudiante_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                designacion_id bigint NOT NULL,
                expediente_id bigint NULL,
                codigo_estud decimal(18,0) NOT NULL,
                cedula_est varchar(50) NULL,
                codigo_periodo_origen numeric(18,0) NULL,
                estudiante_snapshot nvarchar(220) NULL,
                cod_anio_basica decimal(18,0) NULL,
                carrera_snapshot nvarchar(250) NULL,
                cumple_requisitos bit NOT NULL CONSTRAINT DF_designacion_est_cumple DEFAULT (1),
                activo bit NOT NULL CONSTRAINT DF_designacion_est_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                periodo_origen_snapshot nvarchar(220) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_designacion_est_fecha DEFAULT (sysdatetime())
            );
        END
        IF OBJECT_ID('pp.autorizacion_practica_estudiante', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.autorizacion_practica_estudiante (
                autorizacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo_proceso_id tinyint NOT NULL,
                codigo_estud decimal(18,0) NOT NULL,
                codigo_periodo numeric(18,0) NOT NULL,
                nombre_archivo nvarchar(260) NOT NULL,
                ruta_archivo nvarchar(500) NOT NULL,
                extension varchar(20) NULL,
                mime_type nvarchar(120) NULL,
                hash_archivo varchar(64) NULL,
                tamanio_bytes bigint NULL,
                activo bit NOT NULL CONSTRAINT DF_autorizacion_practica_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_autorizacion_practica_fecha DEFAULT (sysdatetime())
            );
        END
        """
    )
    for table_name, column_name, definition in [
        ("pp.designacion_periodo_responsable", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.designacion_periodo_responsable", "periodo_origen_snapshot", "nvarchar(220) NULL"),
        ("pp.designacion_periodo_estudiante", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.designacion_periodo_estudiante", "periodo_origen_snapshot", "nvarchar(220) NULL"),
        ("pp.expediente_practica", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.expediente_practica", "periodo_origen_snapshot", "nvarchar(220) NULL"),
    ]:
        if _has_object(cursor, table_name) and not _has_column(cursor, table_name, column_name):
            cursor.execute(f"ALTER TABLE {table_name} ADD {column_name} {definition}")


def _tipo_proceso_id(cursor: pyodbc.Cursor, process_code: str) -> int:
    cursor.execute("SELECT tipo_proceso_id FROM cat.tipo_proceso WHERE codigo = ? AND activo = 1", process_code)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tipo de proceso no encontrado.")
    return int(row.tipo_proceso_id)


def _db_error(exc: Exception, action: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{action}. Revisa que INTEC_PRACTICAS_PREPROFESIONALES exista y que B_NAME2/DB_HOST2 sean correctos. Detalle: {exc}",
    )


def _process_code(value: str) -> str:
    code = _clean(value).upper()
    if code not in PROCESS_LABELS:
        raise HTTPException(status_code=400, detail="Tipo de proceso no válido. Usa PPF o VIN.")
    return code


def _process_requirements(process_code: str) -> dict[str, Any]:
    process = _process_code(process_code)
    return _PROCESS_REQUIREMENTS[process]


def _required_hours(process_code: str) -> float:
    return float(_process_requirements(process_code)["hours"])


def _required_document_codes(process_code: str) -> tuple[str, ...]:
    return tuple(_process_requirements(process_code)["documents"])


def _catalog_state_id(cursor: pyodbc.Cursor, table_name: str, id_column: str, code: str) -> int:
    if table_name not in {"cat.estado_expediente", "cat.estado_documento"}:
        raise RuntimeError("Catálogo de estado no permitido.")
    if id_column not in {"estado_expediente_id", "estado_documento_id"}:
        raise RuntimeError("Identificador de estado no permitido.")
    cursor.execute(
        f"SELECT {id_column} FROM {table_name} WHERE codigo = ?",
        code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail=f"No existe el estado requerido {code}.")
    return int(row[0])


def _required_documents_status(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    process_code: str,
) -> list[dict[str, Any]]:
    required_codes = _required_document_codes(process_code)
    placeholders = ",".join("?" for _ in required_codes)
    cursor.execute(
        f"""
        SELECT
            td.tipo_documento_id AS TipoDocumentoId,
            td.codigo AS Codigo,
            td.nombre AS Nombre,
            latest.documento_id AS DocumentoId,
            latest.nombre_archivo AS NombreArchivo,
            latest.ruta_archivo AS RutaArchivo,
            latest.url_archivo AS UrlArchivo,
            latest.validado AS Validado,
            latest.fecha_validacion AS FechaValidacion,
            latest.estado_codigo AS EstadoCodigo,
            latest.estado_nombre AS EstadoNombre
        FROM cat.tipo_documento_practica td
        OUTER APPLY (
            SELECT TOP (1)
                dp.documento_id,
                dp.nombre_archivo,
                dp.ruta_archivo,
                dp.url_archivo,
                dp.validado,
                dp.fecha_validacion,
                ed.codigo AS estado_codigo,
                ed.nombre AS estado_nombre
            FROM pp.documento_practica dp
            INNER JOIN cat.estado_documento ed
                ON ed.estado_documento_id = dp.estado_documento_id
            WHERE dp.expediente_id = ?
              AND dp.tipo_documento_id = td.tipo_documento_id
              AND ed.codigo <> 'ANULADO'
            ORDER BY dp.fecha_registro DESC, dp.documento_id DESC
        ) latest
        WHERE td.codigo IN ({placeholders})
          AND td.activo = 1
        ORDER BY td.orden, td.tipo_documento_id
        """,
        expediente_id,
        *required_codes,
    )
    documents = _fetch_all(cursor)
    by_code = {_clean(item.get("Codigo")).upper(): item for item in documents}
    # Mantiene el orden funcional aunque un catálogo obligatorio haya sido desactivado por error.
    result: list[dict[str, Any]] = []
    for code in required_codes:
        item = by_code.get(code, {"Codigo": code, "Nombre": code.replace("_", " ").title()})
        state = _clean(item.get("EstadoCodigo")).upper()
        item["Cargado"] = bool(item.get("DocumentoId")) and state not in {"RECHAZADO", "ANULADO"}
        item["Validado"] = bool(item.get("Validado")) and state == "VALIDADO"
        result.append(item)
    return result


def _document_compliance_summary(documents: list[dict[str, Any]]) -> dict[str, int | float]:
    required = len(documents)
    loaded = sum(1 for document in documents if document.get("Cargado"))
    validated = sum(1 for document in documents if document.get("Validado"))
    divisor = max(required, 1)
    return {
        "required": required,
        "loaded": loaded,
        "validated": validated,
        "pending_upload": max(required - loaded, 0),
        "pending_validation": max(required - validated, 0),
        "upload_percentage": round((loaded / divisor) * 100, 2),
        "validation_percentage": round((validated / divisor) * 100, 2),
    }


def _responsible_assignment(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    current_user: SessionUser,
    *,
    require_approval: bool,
) -> dict[str, Any]:
    params: list[Any] = [expediente_id]
    identity_filters: list[str] = []
    if current_user.rol not in _ADMIN_ROLES:
        if current_user.cedula:
            identity_filters.append("LTRIM(RTRIM(rp.cedula_ruc)) = ?")
            params.append(_clean(current_user.cedula))
        for email in {_clean(current_user.email).lower(), _clean(current_user.login).lower()} - {""}:
            identity_filters.append("LOWER(LTRIM(RTRIM(rp.correo))) = ?")
            params.append(email)
        if current_user.codigo_doc is not None:
            identity_filters.append("TRY_CONVERT(bigint, rp.codigo_referencia) = ?")
            params.append(int(current_user.codigo_doc))
        if not identity_filters:
            raise HTTPException(status_code=403, detail="La sesión docente no tiene una identidad verificable.")

    permission_filter = "rp.puede_aprobar = 1" if require_approval else "rp.puede_validar_documentos = 1"
    identity_sql = "" if current_user.rol in _ADMIN_ROLES else f"AND ({' OR '.join(identity_filters)})"
    cursor.execute(
        f"""
        SELECT TOP (1)
            rp.responsable_proceso_id AS ResponsableProcesoId,
            rp.nombres AS NombreResponsable,
            rp.correo AS CorreoResponsable,
            rp.puede_validar_documentos AS PuedeValidarDocumentos,
            rp.puede_aprobar AS PuedeAprobar
        FROM pp.responsable_proceso rp
        WHERE rp.expediente_id = ?
          AND rp.activo = 1
          AND {permission_filter}
          {identity_sql}
        ORDER BY rp.principal DESC, rp.responsable_proceso_id DESC
        """,
        *params,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=403,
            detail="El expediente no está asignado a este docente o no tiene permiso para revisarlo.",
        )
    return _row_dict(cursor, row)


def _ensure_assigned_teacher_document_upload(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    current_user: SessionUser,
) -> dict[str, Any]:
    if _clean(current_user.rol).upper() != "DOCENTE":
        raise HTTPException(
            status_code=403,
            detail="Solo el docente responsable activo puede cargar documentos de prácticas o vinculación.",
        )
    return _responsible_assignment(cursor, expediente_id, current_user, require_approval=False)


def _student_code(current_user: SessionUser, requested_code: int | None = None) -> int:
    if current_user.rol == "ESTUDIANTE":
        if current_user.codigo_estud is None:
            raise HTTPException(status_code=403, detail="La sesión no tiene estudiante vinculado.")
        return int(current_user.codigo_estud)
    if requested_code is None:
        raise HTTPException(status_code=400, detail="Indica el código de estudiante.")
    return requested_code


def _safe_filename(value: str, fallback: str = "documento.pdf") -> str:
    text = Path(value or fallback).name
    cleaned = "".join(char if char.isalnum() or char in "._- " else "_" for char in text).strip(" .")
    return cleaned[:160] or fallback


def _latest_carta_select(prefix: str = "e") -> str:
    return f"""
        OUTER APPLY (
            SELECT TOP 1
                dp.documento_id,
                ed.codigo AS estado_codigo,
                ed.nombre AS estado_nombre,
                dp.nombre_archivo,
                dp.ruta_archivo,
                dp.fecha_registro,
                dp.firmado,
                dp.validado
            FROM pp.documento_practica dp
            INNER JOIN cat.tipo_documento_practica td ON td.tipo_documento_id = dp.tipo_documento_id
            INNER JOIN cat.estado_documento ed ON ed.estado_documento_id = dp.estado_documento_id
            WHERE dp.expediente_id = {prefix}.expediente_id
              AND td.codigo = 'CARTA_COMPROMISO'
            ORDER BY dp.fecha_registro DESC, dp.documento_id DESC
        ) carta
    """


def _latest_certificado_select(prefix: str = "e") -> str:
    return f"""
        OUTER APPLY (
            SELECT TOP 1
                dp.documento_id,
                ed.codigo AS estado_codigo,
                ed.nombre AS estado_nombre,
                dp.nombre_archivo,
                dp.ruta_archivo,
                dp.fecha_registro,
                dp.firmado,
                dp.validado
            FROM pp.documento_practica dp
            INNER JOIN cat.tipo_documento_practica td ON td.tipo_documento_id = dp.tipo_documento_id
            INNER JOIN cat.estado_documento ed ON ed.estado_documento_id = dp.estado_documento_id
            WHERE dp.expediente_id = {prefix}.expediente_id
              AND td.codigo = 'OTRO'
              AND dp.observacion LIKE 'CERTIFICADO_PREPROFESIONALES%'
            ORDER BY dp.fecha_registro DESC, dp.documento_id DESC
        ) certificado
    """


def _fetch_legacy_expediente(cursor: pyodbc.Cursor, expediente_id: int) -> Any:
    cursor.execute(
        """
        SELECT TOP 1
            e.expediente_id,
            e.codigo_expediente,
            e.codigo_estud,
            e.cedula_est,
            e.estudiante_snapshot,
            e.cod_anio_basica,
            e.carrera_snapshot,
            e.codigo_periodo,
            e.periodo_snapshot,
            e.semestre,
            e.semestre_numero,
            e.horas_requeridas,
            e.horas_reconocidas,
            e.horas_asistencia_validadas,
            e.fecha_inicio,
            e.fecha_fin,
            e.estado_expediente_id,
            ee.codigo AS estado_expediente_codigo,
            ee.nombre AS estado_expediente,
            tp.codigo AS tipo_proceso_codigo,
            tp.nombre AS tipo_proceso
        FROM pp.expediente_practica e
        INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
        INNER JOIN cat.estado_expediente ee ON ee.estado_expediente_id = e.estado_expediente_id
        WHERE e.expediente_id = ?
        """,
        expediente_id,
    )
    return cursor.fetchone()


def _normalized_document(value: Any) -> str:
    return "".join(char for char in _clean(value).upper() if char.isalnum())


def _review_validation_errors(
    decision: str,
    hours: float,
    required_hours: float,
    documents: list[dict[str, Any]],
    documents_corroborated: bool,
    observation: str | None,
) -> list[str]:
    normalized_decision = _clean(decision).upper()
    errors: list[str] = []
    if normalized_decision in {"OBSERVAR", "RECHAZAR"} and not _clean(observation):
        errors.append("Debe registrar el motivo de la decisión.")
    if normalized_decision != "APROBAR":
        return errors

    missing = [_clean(item.get("Nombre") or item.get("Codigo")) for item in documents if not item.get("Cargado")]
    if missing:
        errors.append(f"Faltan documentos obligatorios: {', '.join(missing)}.")
    if hours < required_hours:
        errors.append(f"Las horas verificadas deben ser al menos {required_hours:g}.")
    if not documents_corroborated:
        errors.append("Debe corroborar expresamente los documentos antes de aprobar.")
    return errors


def _legacy_review_detail(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    current_user: SessionUser,
) -> dict[str, Any]:
    row = _fetch_legacy_expediente(cursor, expediente_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe el expediente solicitado.")
    expediente = _row_dict(cursor, row)
    process_code = _process_code(expediente.get("tipo_proceso_codigo"))
    assignment = _responsible_assignment(cursor, expediente_id, current_user, require_approval=False)
    documents = _required_documents_status(cursor, expediente_id, process_code)
    configuration = effective_process_configuration(
        cursor,
        process_code=process_code,
        career_code=expediente.get("cod_anio_basica"),
        level=expediente.get("semestre_numero") or expediente.get("semestre"),
        period_code=expediente.get("codigo_periodo"),
    )
    required_hours = float(configuration["horas_requeridas"])
    recognized_hours = float(expediente.get("horas_reconocidas") or 0)

    cursor.execute(
        """
        SELECT TOP (1)
            revision_id AS RevisionId,
            fecha_revision AS FechaRevision,
            revisor_usuario AS RevisorUsuario,
            resultado AS Resultado,
            observacion AS Observacion,
            accion_requerida AS AccionRequerida
        FROM pp.revision_documental_practica
        WHERE expediente_id = ?
          AND documento_id IS NULL
        ORDER BY fecha_revision DESC, revision_id DESC
        """,
        expediente_id,
    )
    latest_review_row = cursor.fetchone()
    latest_review = _row_dict(cursor, latest_review_row) if latest_review_row else None
    missing = [item["Codigo"] for item in documents if not item.get("Cargado")]
    all_loaded = not missing
    can_approve = bool(assignment.get("PuedeAprobar"))
    return {
        "ExpedienteId": int(expediente["expediente_id"]),
        "CodigoExpediente": expediente.get("codigo_expediente"),
        "CodigoEstud": expediente.get("codigo_estud"),
        "Cedula_Est": expediente.get("cedula_est"),
        "Apellidos_nombre": expediente.get("estudiante_snapshot"),
        "CodigoCarrera": expediente.get("cod_anio_basica"),
        "Carrera": expediente.get("carrera_snapshot"),
        "CodigoPeriodo": expediente.get("codigo_periodo"),
        "Periodo": expediente.get("periodo_snapshot"),
        "FechaInicioCarga": expediente.get("fecha_inicio"),
        "FechaFinCarga": expediente.get("fecha_fin"),
        "TipoProcesoCodigo": process_code,
        "TipoProceso": expediente.get("tipo_proceso"),
        "EstadoCodigo": expediente.get("estado_expediente_codigo"),
        "EstadoExpediente": expediente.get("estado_expediente"),
        "HorasRequeridas": required_hours,
        "HorasReconocidas": recognized_hours,
        "HorasAsistenciaValidadas": float(expediente.get("horas_asistencia_validadas") or 0),
        "ConfiguracionProceso": configuration,
        "DocumentosDetalle": documents,
        "DocumentosFaltantes": missing,
        "DocumentosCompletos": all_loaded,
        "ListoParaAprobar": all_loaded and recognized_hours >= required_hours,
        "PuedeAprobar": can_approve,
        "Responsable": assignment,
        "UltimaRevision": latest_review,
    }


def _sync_titulacion_completion(expediente_id: int, process_code: str, usuario: str) -> dict[str, Any]:
    """Refleja una aprobación ya confirmada sin crear expedientes de titulación ambiguos."""
    with get_practices_connection() as practices_conn:
        practices_cursor = practices_conn.cursor()
        ensure_operations_schema(practices_cursor)
        row = _fetch_legacy_expediente(practices_cursor, expediente_id)
        if not row:
            return {"sincronizado": False, "motivo": "Expediente de prácticas no encontrado."}
        source = _row_dict(practices_cursor, row)
        documents = _required_documents_status(practices_cursor, expediente_id, process_code)
        practices_cursor.execute(
            """
            SELECT evaluacion.estado, evaluacion.resultado, evaluacion.calificacion, cierre.fecha_cierre
            FROM ops.evaluacion_practica evaluacion
            LEFT JOIN ops.cierre_proceso cierre ON cierre.expediente_id = evaluacion.expediente_id
            WHERE evaluacion.expediente_id = ?
            """,
            expediente_id,
        )
        evaluation_row = practices_cursor.fetchone()

    state = _clean(source.get("estado_expediente_codigo")).upper()
    required_hours = _required_hours(process_code)
    recognized_hours = float(source.get("horas_reconocidas") or 0)
    documents_complete = all(item.get("Validado") for item in documents)
    formal_evaluation_complete = bool(evaluation_row) and is_approved_practice_outcome(
        evaluation_state=evaluation_row[0] if evaluation_row else None,
        result=evaluation_row[1] if evaluation_row else None,
        grade=evaluation_row[2] if evaluation_row else None,
        closed_at=evaluation_row[3] if evaluation_row else None,
    )
    completed = (
        state in _COMPLETION_STATES
        and recognized_hours >= required_hours
        and documents_complete
        and formal_evaluation_complete
    )
    if not completed:
        return {
            "sincronizado": False,
            "motivo": "El expediente requiere calificación aprobada y cierre confirmado antes de habilitar Titulación.",
        }

    document = _normalized_document(source.get("cedula_est"))
    career = _clean(source.get("cod_anio_basica"))
    if not document:
        return {"sincronizado": False, "motivo": "El expediente no tiene identificación estudiantil válida."}

    with get_titulation_connection() as titulation_conn:
        cursor = titulation_conn.cursor()
        cursor.execute(
            """
            SELECT
                E.ExpedienteId,
                CONVERT(nvarchar(50), E.CodAnioBasica) AS CodAnioBasica
            FROM tit.ExpedienteTitulacion E
            INNER JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
            WHERE UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), ER.NumeroIdentificacion))), '-', ''), ' ', ''), '.', '')) = ?
            ORDER BY E.ExpedienteId DESC
            """,
            document,
        )
        candidates = _fetch_all(cursor)
        exact = [item for item in candidates if _clean(item.get("CodAnioBasica")) == career]
        targets = exact or (candidates if len(candidates) == 1 else [])
        if not targets:
            return {
                "sincronizado": False,
                "pendiente": True,
                "motivo": "La aprobación quedó registrada; se enlazará cuando exista un expediente de titulación inequívoco.",
            }

        for target in targets:
            titulation_id = int(target["ExpedienteId"])
            cursor.execute(
                """
                UPDATE vinc.EnlaceExpedientePracticas
                SET Activo = 0,
                    FechaSincronizacion = SYSDATETIME()
                WHERE ExpedienteId = ?
                  AND TipoProcesoCodigo = ?
                """,
                titulation_id,
                process_code,
            )
            cursor.execute(
                """
                SELECT TOP (1) EnlaceId
                FROM vinc.EnlaceExpedientePracticas
                WHERE ExpedienteId = ?
                  AND TipoProcesoCodigo = ?
                  AND ExpedientePracticasId = ?
                ORDER BY EnlaceId DESC
                """,
                titulation_id,
                process_code,
                expediente_id,
            )
            link = cursor.fetchone()
            link_values = (
                source.get("codigo_expediente"),
                source.get("codigo_estud"),
                career or None,
                _clean(source.get("codigo_periodo")) or None,
                state,
                recognized_hours,
                required_hours,
                source.get("fecha_inicio"),
                source.get("fecha_fin"),
                usuario,
                f"Aprobación docente del expediente {source.get('codigo_expediente') or expediente_id}.",
            )
            if link:
                cursor.execute(
                    """
                    UPDATE vinc.EnlaceExpedientePracticas
                    SET CodigoExpedientePracticas = ?, CodigoEstud = ?, CodigoCarrera = ?, CodigoPeriodo = ?,
                        EstadoPracticasCodigo = ?, TotalHorasReconocidas = ?, HorasMinimasRequeridas = ?,
                        CumpleHoras = 1, DocumentosCompletos = 1, ExpedienteCerrado = 1, Reconocido = 1,
                        FechaInicioProceso = ?, FechaFinProceso = ?, Fuente = 'INTEC_PRACTICAS_PREPROFESIONALES',
                        FechaReconocimiento = SYSDATETIME(), UsuarioReconocimiento = ?, Observacion = ?,
                        Activo = 1, FechaSincronizacion = SYSDATETIME()
                    WHERE EnlaceId = ?
                    """,
                    *link_values,
                    int(link.EnlaceId),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO vinc.EnlaceExpedientePracticas (
                        ExpedienteId, TipoProcesoCodigo, ExpedientePracticasId, CodigoExpedientePracticas,
                        CodigoEstud, CodigoCarrera, CodigoPeriodo, EstadoPracticasCodigo,
                        TotalHorasReconocidas, HorasMinimasRequeridas, CumpleHoras, DocumentosCompletos,
                        ExpedienteCerrado, Reconocido, FechaInicioProceso, FechaFinProceso, Fuente,
                        FechaReconocimiento, UsuarioReconocimiento, Observacion, Activo, FechaSincronizacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1, ?, ?,
                              'INTEC_PRACTICAS_PREPROFESIONALES', SYSDATETIME(), ?, ?, 1, SYSDATETIME())
                    """,
                    titulation_id,
                    process_code,
                    expediente_id,
                    *link_values,
                )

            cursor.execute(
                "SELECT CumplimientoId FROM vinc.CumplimientoPracticasVinculacion WHERE ExpedienteId = ?",
                titulation_id,
            )
            fulfillment = cursor.fetchone()
            if fulfillment:
                if process_code == "PPF":
                    cursor.execute(
                        """
                        UPDATE vinc.CumplimientoPracticasVinculacion
                        SET TotalHorasPracticasPreprofesionales = ?, TienePracticasPreprofesionales = 1,
                            CumplePracticasPreprofesionales = 1, UltimaFechaPracticas = COALESCE(?, CONVERT(date, SYSDATETIME())),
                            FuenteSincronizacion = 'APROBACION_DOCENTE', Observacion = ?, FechaSincronizacion = SYSDATETIME()
                        WHERE ExpedienteId = ?
                        """,
                        recognized_hours,
                        source.get("fecha_fin"),
                        link_values[-1],
                        titulation_id,
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE vinc.CumplimientoPracticasVinculacion
                        SET TotalHorasVinculacion = ?, TieneVinculacion = 1, CumpleVinculacion = 1,
                            UltimaFechaVinculacion = COALESCE(?, CONVERT(date, SYSDATETIME())),
                            FuenteSincronizacion = 'APROBACION_DOCENTE', Observacion = ?, FechaSincronizacion = SYSDATETIME()
                        WHERE ExpedienteId = ?
                        """,
                        recognized_hours,
                        source.get("fecha_fin"),
                        link_values[-1],
                        titulation_id,
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO vinc.CumplimientoPracticasVinculacion (
                        ExpedienteId, TotalHorasPracticasPreprofesionales, TotalHorasVinculacion,
                        TienePracticasPreprofesionales, TieneVinculacion,
                        CumplePracticasPreprofesionales, CumpleVinculacion,
                        UltimaFechaPracticas, UltimaFechaVinculacion,
                        FuenteSincronizacion, Observacion, FechaSincronizacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'APROBACION_DOCENTE', ?, SYSDATETIME())
                    """,
                    titulation_id,
                    recognized_hours if process_code == "PPF" else 0,
                    recognized_hours if process_code == "VIN" else 0,
                    1 if process_code == "PPF" else 0,
                    1 if process_code == "VIN" else 0,
                    1 if process_code == "PPF" else 0,
                    1 if process_code == "VIN" else 0,
                    source.get("fecha_fin") if process_code == "PPF" else None,
                    source.get("fecha_fin") if process_code == "VIN" else None,
                    link_values[-1],
                )
            flag = "PracticasPreprofesionalesCumple" if process_code == "PPF" else "VinculacionCumple"
            cursor.execute(
                f"""
                UPDATE tit.ExpedienteTitulacion
                SET {flag} = 1, FechaActualizacion = SYSDATETIME(), UsuarioActualizacion = ?
                WHERE ExpedienteId = ?
                """,
                usuario,
                titulation_id,
            )
        titulation_conn.commit()
    return {"sincronizado": True, "expedientes_titulacion": len(targets)}


def _register_responsable_for_expediente(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    codigo_docente: Any,
    nombre_responsable: str,
    cedula_responsable: str | None,
    correo_responsable: str | None,
    rol_responsable: str | None,
    usuario: str,
    observacion: str,
) -> int | None:
    cursor.execute(
        """
        EXEC pp.sp_registrar_responsable_proceso
            @expediente_id = ?,
            @tipo_responsable_codigo = ?,
            @tipo_referencia = ?,
            @codigo_referencia = ?,
            @cedula_ruc = ?,
            @nombres = ?,
            @correo = ?,
            @telefono = ?,
            @cargo = ?,
            @institucion = ?,
            @direccion = ?,
            @fecha_inicio = NULL,
            @fecha_fin = NULL,
            @principal = 1,
            @puede_validar_documentos = 1,
            @puede_aprobar = 1,
            @observacion = ?,
            @usuario_registro = ?
        """,
        expediente_id,
        "RESPONSABLE_ACADEMICO",
        "DOCENTE",
        int(codigo_docente) if codigo_docente is not None and str(codigo_docente).isdigit() else None,
        cedula_responsable,
        nombre_responsable,
        correo_responsable,
        None,
        rol_responsable or "RESPONSABLE",
        None,
        None,
        observacion,
        usuario,
    )
    row = cursor.fetchone()
    cursor.execute(
        """
        UPDATE pp.expediente_practica
        SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
            docente_tutor_snapshot = ?,
            usuario_modifica = ?,
            fecha_modifica = SYSDATETIME()
        WHERE expediente_id = ?
        """,
        codigo_docente,
        nombre_responsable,
        usuario,
        expediente_id,
    )
    return int(row.responsable_proceso_id) if row and getattr(row, "responsable_proceso_id", None) is not None else None


def _apply_period_designation_to_expediente(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    tipo_proceso_id: int,
    codigo_periodo: Any,
    usuario: str,
) -> bool:
    _ensure_period_designation_table(cursor)
    cursor.execute(
        """
        SELECT TOP 1 *
        FROM pp.designacion_periodo_responsable
        WHERE tipo_proceso_id = ?
          AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
          AND activo = 1
        ORDER BY fecha_registro DESC, designacion_id DESC
        """,
        tipo_proceso_id,
        codigo_periodo,
    )
    designation = cursor.fetchone()
    if not designation:
        return False
    _register_responsable_for_expediente(
        cursor,
        expediente_id,
        designation.codigo_docente,
        _clean(designation.nombre_responsable),
        _clean(designation.cedula_responsable) or None,
        _clean(designation.correo_responsable) or None,
        _clean(designation.rol_responsable) or "RESPONSABLE",
        usuario,
        f"Designación automática del período {codigo_periodo}.",
    )
    return True


def _ensure_expediente_for_source(
    cursor: pyodbc.Cursor,
    source: Any,
    process_code: str,
    tipo_proceso_id: int,
    usuario: str,
    observacion: str | None = None,
    target_codigo_periodo: Any | None = None,
    target_periodo_nombre: str | None = None,
    fecha_inicio_carga: date | None = None,
    fecha_fin_carga: date | None = None,
) -> int:
    target_period = target_codigo_periodo if target_codigo_periodo not in (None, "") else source.codigo_periodo
    target_period_name = _clean(target_periodo_nombre) or _clean(source.periodo)
    configuration = effective_process_configuration(
        cursor,
        process_code=process_code,
        career_code=source.cod_anio_basica,
        level=source.semestre_numero,
        period_code=target_period,
    )
    required_hours = float(configuration["horas_requeridas"])
    cursor.execute(
        """
        SELECT TOP 1 expediente_id
        FROM pp.expediente_practica
        WHERE tipo_proceso_id = ?
          AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
          AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
          AND cod_anio_basica = TRY_CONVERT(decimal(18,0), ?)
        ORDER BY expediente_id DESC
        """,
        tipo_proceso_id,
        target_period,
        source.codigo_estud,
        source.cod_anio_basica,
    )
    existing = cursor.fetchone()
    if existing:
        expediente_id = int(existing.expediente_id)
        cursor.execute(
            """
            UPDATE pp.expediente_practica
            SET fecha_inicio = COALESCE(?, fecha_inicio),
                fecha_fin = COALESCE(?, fecha_fin),
                horas_requeridas = ?,
                observacion = COALESCE(NULLIF(?, ''), observacion)
            WHERE expediente_id = ?
            """,
            fecha_inicio_carga,
            fecha_fin_carga,
            required_hours,
            _clean(observacion),
            expediente_id,
        )
        upsert_compliance_enrollment(
            cursor,
            expediente_id=expediente_id,
            process_code=process_code,
            student_code=int(source.codigo_estud),
            career_code=int(source.cod_anio_basica),
            academic_period_code=int(source.codigo_periodo),
            institutional_period_code=int(target_period),
            user=usuario,
        )
        return expediente_id

    cursor.execute("SELECT estado_expediente_id FROM cat.estado_expediente WHERE codigo = 'BORRADOR'")
    estado_row = cursor.fetchone()
    if not estado_row:
        raise HTTPException(status_code=500, detail="Falta el estado BORRADOR para crear expediente.")
    cursor.execute("SELECT ISNULL(MAX(expediente_id), 0) + 1 FROM pp.expediente_practica WITH (UPDLOCK, HOLDLOCK)")
    next_id = int(cursor.fetchone()[0])
    code = f"{process_code}-{next_id:08d}"
    cursor.execute(
        """
        SET NOCOUNT ON;
        DECLARE @ExpedienteCreado TABLE (ExpedienteId bigint NOT NULL);
        INSERT INTO pp.expediente_practica (
            codigo_expediente, codigo_estud, cedula_est, cod_anio_basica, codigo_periodo,
            codigo_periodo_origen, estudiante_snapshot, carrera_snapshot, periodo_snapshot,
            periodo_origen_snapshot, estado_expediente_id,
            tipo_proceso_id, semestre, semestre_numero, horas_requeridas,
            fecha_inicio, fecha_fin, observacion, usuario_registro
        )
        OUTPUT INSERTED.expediente_id INTO @ExpedienteCreado (ExpedienteId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        SELECT TOP (1) ExpedienteId FROM @ExpedienteCreado;
        """,
        code,
        int(source.codigo_estud),
        str(source.cedula_est),
        int(source.cod_anio_basica),
        int(target_period),
        int(source.codigo_periodo),
        _clean(source.estudiante),
        _clean(source.carrera),
        target_period_name,
        _clean(source.periodo),
        int(estado_row.estado_expediente_id),
        tipo_proceso_id,
        str(source.semestre_numero or ""),
        int(source.semestre_numero or 3),
        required_hours,
        fecha_inicio_carga,
        fecha_fin_carga,
        observacion,
        usuario,
    )
    row = cursor.fetchone()
    expediente_id = int(row.ExpedienteId)
    upsert_compliance_enrollment(
        cursor,
        expediente_id=expediente_id,
        process_code=process_code,
        student_code=int(source.codigo_estud),
        career_code=int(source.cod_anio_basica),
        academic_period_code=int(source.codigo_periodo),
        institutional_period_code=int(target_period),
        user=usuario,
    )
    return expediente_id


def _ensure_student_owns_expediente(current_user: SessionUser, expediente: Any) -> None:
    if current_user.rol == "ESTUDIANTE" and int(expediente.codigo_estud) != int(current_user.codigo_estud or 0):
        raise HTTPException(status_code=403, detail="No puedes gestionar un expediente de otro estudiante.")


def _practice_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    raw = _clean(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _validate_upload_window(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(
            status_code=400,
            detail="La fecha de cierre documental no puede ser anterior a la fecha de inicio.",
        )


def _ensure_practice_upload_window(expediente: Any, today: date | None = None) -> None:
    start = _practice_date(getattr(expediente, "fecha_inicio", None))
    end = _practice_date(getattr(expediente, "fecha_fin", None))
    if not start or not end:
        raise HTTPException(
            status_code=409,
            detail=(
                "Administración debe definir el plazo de carga documental antes de que "
                "el docente responsable suba archivos."
            ),
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


def _build_carta_compromiso_pdf(expediente: Any) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CartaTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0c1f42"),
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=1,
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "CartaBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        alignment=4,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "CartaSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4b5563"),
    )
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.7 * cm,
        title="Carta compromiso prácticas institucionales",
    )
    story: list[Any] = [
        Paragraph("INSTITUTO SUPERIOR TECNOLÓGICO INTEC", title_style),
        Paragraph("CARTA COMPROMISO DE PRÁCTICAS PREPROFESIONALES", title_style),
        Spacer(1, 0.2 * cm),
    ]
    table_data = [
        ["Expediente", _clean(expediente.codigo_expediente) or str(expediente.expediente_id)],
        ["Estudiante", _clean(expediente.estudiante_snapshot)],
        ["Cédula", _clean(expediente.cedula_est)],
        ["Carrera", _clean(expediente.carrera_snapshot)],
        ["Período", _clean(expediente.periodo_snapshot) or _clean(expediente.codigo_periodo)],
        ["Proceso", _clean(expediente.tipo_proceso)],
    ]
    table = Table(table_data, colWidths=[4.2 * cm, 11.0 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef8fb")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0c1f42")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#b8dce6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 0.55 * cm)])
    story.append(Paragraph(
        "Yo, estudiante identificado en el presente documento, declaro conocer y aceptar las responsabilidades "
        "académicas, administrativas y éticas asociadas al desarrollo de mis prácticas institucionales.",
        body_style,
    ))
    story.append(Paragraph(
        "Me comprometo a cumplir las actividades asignadas por la institución, empresa o proyecto receptor; "
        "mantener comunicación con el responsable designado; presentar evidencias y documentos requeridos; "
        "respetar la confidencialidad de la información a la que tenga acceso; y observar las normas internas "
        "del Instituto Superior Tecnológico INTEC.",
        body_style,
    ))
    story.append(Paragraph(
        "El incumplimiento de estas obligaciones podrá generar observaciones, suspensión del proceso o las "
        "acciones académicas que correspondan conforme a la normativa institucional vigente.",
        body_style,
    ))
    story.extend([Spacer(1, 1.3 * cm), Paragraph("Firma del estudiante: ________________________________", body_style)])
    story.append(Paragraph(f"Fecha de generación: {date.today().isoformat()}", small_style))
    doc.build(story)
    output.seek(0)
    return output.getvalue()


@router.get("/catalog")
def catalog(_: Annotated[SessionUser, Depends(_ALL_ACCESS)]) -> dict[str, Any]:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                _ensure_period_designation_table(cursor)
                ensure_operations_schema(cursor)
                cursor.execute(
                    """
                    SELECT
                        tipo_proceso_id AS TipoProcesoId,
                        codigo AS Codigo,
                        nombre AS Nombre,
                        descripcion AS Descripcion,
                        activo AS Activo
                    FROM cat.tipo_proceso
                    WHERE activo = 1
                    ORDER BY codigo
                    """
                )
                processes = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        td.tipo_documento_id AS TipoDocumentoId,
                        tp.codigo AS TipoProcesoCodigo,
                        td.codigo AS Codigo,
                        td.nombre AS Nombre,
                        CASE WHEN tp.codigo = 'VIN' THEN td.obligatorio_vinculacion ELSE td.obligatorio_practicas END AS EsObligatorio,
                        td.orden AS Orden
                    FROM cat.tipo_documento_practica td
                    CROSS JOIN cat.tipo_proceso tp
                    WHERE td.activo = 1
                      AND tp.activo = 1
                      AND (
                            (tp.codigo = 'PPF' AND td.aplica_practicas = 1)
                         OR (tp.codigo = 'VIN' AND td.aplica_vinculacion = 1)
                      )
                    ORDER BY tp.codigo, td.orden, td.nombre
                    """
                )
                documents = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT TOP 300
                        rp.responsable_proceso_id AS ResponsableProcesoId,
                        tp.codigo AS TipoProcesoCodigo,
                        rp.nombres AS NombreResponsable,
                        rp.cedula_ruc AS CedulaResponsable,
                        rp.correo AS CorreoResponsable,
                        trp.nombre AS RolResponsable,
                        CONVERT(varchar(50), rp.codigo_referencia) AS CodigoDocente,
                        rp.fecha_inicio AS FechaInicio,
                        rp.fecha_fin AS FechaFin,
                        rp.activo AS Activo
                    FROM pp.responsable_proceso rp
                    INNER JOIN pp.expediente_practica e ON e.expediente_id = rp.expediente_id
                    INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
                    LEFT JOIN cat.tipo_responsable_proceso trp ON trp.tipo_responsable_id = rp.tipo_responsable_id
                    WHERE rp.activo = 1
                    ORDER BY tp.codigo, rp.fecha_registro DESC
                    """
                )
                responsibles = _fetch_all(cursor)
            else:
                cursor.execute(
                    """
                    SELECT TipoProcesoId, Codigo, Nombre, Descripcion, Activo
                    FROM cat.TipoProceso
                    WHERE Activo = 1
                    ORDER BY Codigo
                    """
                )
                processes = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        td.TipoDocumentoId,
                        tp.Codigo AS TipoProcesoCodigo,
                        td.Codigo,
                        td.Nombre,
                        td.EsObligatorio,
                        td.Orden
                    FROM cat.TipoDocumento td
                    INNER JOIN cat.TipoProceso tp ON tp.TipoProcesoId = td.TipoProcesoId
                    WHERE td.Activo = 1
                    ORDER BY tp.Codigo, td.Orden, td.Nombre
                    """
                )
                documents = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        ResponsableProcesoId,
                        tp.Codigo AS TipoProcesoCodigo,
                        NombreResponsable,
                        CedulaResponsable,
                        CorreoResponsable,
                        RolResponsable,
                        CodigoDocente,
                        FechaInicio,
                        FechaFin,
                        Activo
                    FROM resp.ResponsableProceso rp
                    INNER JOIN cat.TipoProceso tp ON tp.TipoProcesoId = rp.TipoProcesoId
                    WHERE rp.Activo = 1
                    ORDER BY tp.Codigo, rp.NombreResponsable
                    """
                )
                responsibles = _fetch_all(cursor)

        return {
            "processes": processes,
            "documents": documents,
            "responsibles": responsibles,
            "defaults": [
                {"codigo": "PPF", "nombre": PROCESS_LABELS["PPF"]},
                {"codigo": "VIN", "nombre": PROCESS_LABELS["VIN"]},
            ],
        }
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo cargar el catálogo de prácticas institucionales") from exc


@router.get("/student/me")
def student_practices(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    codigo_estud: int | None = Query(default=None),
) -> dict[str, Any]:
    student_code = _student_code(current_user, codigo_estud)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            use_legacy = _use_legacy_schema(cursor)
            if use_legacy:
                cursor.execute(
                    """
                    SELECT TOP 100
                        codigo_estud,
                        cedula_est AS Cedula_Est,
                        estudiante AS Apellidos_nombre,
                        cod_anio_basica AS CodigoCarrera,
                        carrera AS Carrera,
                        codigo_periodo AS CodigoPeriodo,
                        periodo AS NombrePeriodo,
                        tipo_proceso_codigo AS TipoProcesoCodigo,
                        tipo_proceso AS TipoProceso,
                        semestre_numero AS SemestreMaximo,
                        elegible AS EsElegible
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE codigo_estud = ?
                    ORDER BY codigo_periodo DESC, cod_anio_basica, tipo_proceso_codigo
                    """,
                    student_code,
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP 100 *
                    FROM integ.vw_estudiantes_elegibles
                    WHERE codigo_estud = ?
                    ORDER BY CodigoPeriodo DESC, CodigoCarrera, TipoProcesoCodigo
                    """,
                    student_code,
                )
            eligibility = _fetch_all(cursor)

            if use_legacy:
                cursor.execute(
                    f"""
                    SELECT TOP 100
                        v.expediente_id AS ExpedienteId,
                        v.codigo_expediente AS CodigoExpediente,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.codigo_estud AS CodigoEstud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante_snapshot AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera_snapshot AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        TRY_CONVERT(varchar(50), v.cod_docente_tutor) AS CodigoDocenteTutor,
                        v.docente_tutor_snapshot AS DocenteTutor,
                        v.estado_codigo AS EstadoCodigo,
                        v.estado_expediente AS EstadoExpediente,
                        v.responsable_proceso_id AS ResponsableProcesoId,
                        v.responsable_principal AS NombreResponsable,
                        v.responsable_correo AS CorreoResponsable,
                        e.fecha_inicio AS FechaInicioCarga,
                        e.fecha_fin AS FechaFinCarga,
                        v.fecha_registro AS FechaCreacion,
                        carta.documento_id AS CartaCompromisoDocumentoId,
                        carta.estado_codigo AS CartaCompromisoEstadoCodigo,
                        carta.estado_nombre AS CartaCompromisoEstado,
                        carta.nombre_archivo AS CartaCompromisoArchivo,
                        carta.ruta_archivo AS CartaCompromisoUrl,
                        carta.fecha_registro AS CartaCompromisoFecha,
                        carta.firmado AS CartaCompromisoFirmado,
                        carta.validado AS CartaCompromisoValidado,
                        certificado.documento_id AS CertificadoDocumentoId,
                        certificado.estado_codigo AS CertificadoEstadoCodigo,
                        certificado.estado_nombre AS CertificadoEstado,
                        certificado.nombre_archivo AS CertificadoArchivo,
                        certificado.ruta_archivo AS CertificadoUrl,
                        certificado.fecha_registro AS CertificadoFecha,
                        certificado.firmado AS CertificadoFirmado,
                        certificado.validado AS CertificadoValidado
                    FROM pp.vw_admin_expedientes_control v
                    INNER JOIN pp.expediente_practica e ON e.expediente_id = v.expediente_id
                    {_latest_carta_select("v")}
                    {_latest_certificado_select("v")}
                    WHERE v.codigo_estud = ?
                    ORDER BY v.fecha_registro DESC
                    """,
                    student_code,
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP 100 *
                    FROM exp.vw_expediente_resumen
                    WHERE CodigoEstud = ?
                    ORDER BY FechaCreacion DESC
                    """,
                    student_code,
                )
            expedientes = _fetch_all(cursor)
            for expediente in expedientes:
                process = _process_code(expediente.get("TipoProcesoCodigo"))
                if use_legacy:
                    documents = _required_documents_status(cursor, int(expediente["ExpedienteId"]), process)
                    compliance = _document_compliance_summary(documents)
                    expediente["DocumentosDetalle"] = documents
                else:
                    required = len(_required_document_codes(process))
                    loaded = min(int(expediente.get("DocumentosCargados") or 0), required)
                    validated = min(int(expediente.get("DocumentosValidados") or 0), required)
                    compliance = _document_compliance_summary(
                        [
                            {"Cargado": index < loaded, "Validado": index < validated}
                            for index in range(required)
                        ]
                    )
                expediente["DocumentosRequeridos"] = compliance["required"]
                expediente["DocumentosCargados"] = compliance["loaded"]
                expediente["DocumentosValidados"] = compliance["validated"]
                expediente["DocumentosPendientes"] = compliance["pending_upload"]
                expediente["AvanceDocumental"] = compliance["upload_percentage"]
                expediente["AvanceValidacionDocumental"] = compliance["validation_percentage"]

        return {"codigo_estud": student_code, "eligibility": eligibility, "expedientes": expedientes}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar prácticas institucionales del estudiante") from exc


@router.post("/student/expedientes")
def create_student_expediente(
    payload: CreateExpedientePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process_code = _process_code(payload.tipo_proceso_codigo)
    student_code = _student_code(current_user, payload.codigo_estud)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                _ensure_period_designation_table(cursor)
                ensure_operations_schema(cursor)
                cursor.execute(
                    """
                    SELECT TOP 1 *
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE codigo_estud = ?
                      AND tipo_proceso_codigo = ?
                      AND (? IS NULL OR CONVERT(varchar(50), cod_anio_basica) = ?)
                      AND (? IS NULL OR CONVERT(varchar(50), codigo_periodo) = ?)
                    ORDER BY codigo_periodo DESC
                    """,
                    student_code,
                    process_code,
                    payload.codigo_carrera,
                    payload.codigo_carrera,
                    payload.codigo_periodo,
                    payload.codigo_periodo,
                )
                source = cursor.fetchone()
                if not source:
                    raise HTTPException(status_code=404, detail="No se encontró una referencia académica elegible para crear la inscripción institucional.")
                if not bool(source.elegible):
                    raise HTTPException(status_code=400, detail=f"El estudiante no es elegible: {source.motivo_elegibilidad}")
                tipo_proceso_id = _tipo_proceso_id(cursor, process_code)
                configuration = effective_process_configuration(
                    cursor,
                    process_code=process_code,
                    career_code=source.cod_anio_basica,
                    level=source.semestre_numero,
                    period_code=source.codigo_periodo,
                )
                cursor.execute("SELECT estado_expediente_id FROM cat.estado_expediente WHERE codigo = 'BORRADOR'")
                estado_row = cursor.fetchone()
                if not estado_row:
                    raise HTTPException(status_code=500, detail="Faltan catálogos base de prácticas.")
                cursor.execute("SELECT ISNULL(MAX(expediente_id), 0) + 1 FROM pp.expediente_practica WITH (UPDLOCK, HOLDLOCK)")
                next_id = int(cursor.fetchone()[0])
                code = f"{process_code}-{next_id:08d}"
                cursor.execute(
                    """
                    SET NOCOUNT ON;
                    DECLARE @ExpedienteCreado TABLE (
                        ExpedienteId bigint NOT NULL,
                        CodigoExpediente varchar(80) NOT NULL
                    );
                    INSERT INTO pp.expediente_practica (
                        codigo_expediente, codigo_estud, cedula_est, cod_anio_basica, codigo_periodo,
                        estudiante_snapshot, carrera_snapshot, periodo_snapshot, estado_expediente_id,
                        tipo_proceso_id, semestre, semestre_numero, horas_requeridas,
                        observacion, usuario_registro
                    )
                    OUTPUT INSERTED.expediente_id, INSERTED.codigo_expediente
                    INTO @ExpedienteCreado (ExpedienteId, CodigoExpediente)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    SELECT TOP (1) ExpedienteId, CodigoExpediente FROM @ExpedienteCreado;
                    """,
                    code,
                    int(source.codigo_estud),
                    str(source.cedula_est),
                    int(source.cod_anio_basica),
                    int(source.codigo_periodo),
                    _clean(source.estudiante),
                    _clean(source.carrera),
                    _clean(source.periodo),
                    int(estado_row.estado_expediente_id),
                    tipo_proceso_id,
                    str(source.semestre_numero or ""),
                    int(source.semestre_numero or 3),
                    float(configuration["horas_requeridas"]),
                    payload.observacion,
                    current_user.login,
                )
                row = cursor.fetchone()
                response_payload = _row_dict(cursor, row) if row else {"ok": True, "message": "Expediente creado"}
                if row:
                    upsert_compliance_enrollment(
                        cursor,
                        expediente_id=int(row.ExpedienteId),
                        process_code=process_code,
                        student_code=int(source.codigo_estud),
                        career_code=int(source.cod_anio_basica),
                        academic_period_code=int(source.codigo_periodo),
                        institutional_period_code=int(source.codigo_periodo),
                        user=current_user.login,
                    )
                    response_payload.update({
                        "alcance": "INSTITUCIONAL_CUMPLIMIENTO",
                        "modifica_matricula_academica": False,
                    })
            else:
                cursor.execute(
                    """
                    EXEC exp.sp_crear_expediente
                        @TipoProcesoCodigo = ?,
                        @CodigoEstud = ?,
                        @CodigoCarrera = ?,
                        @CodigoPeriodo = ?,
                        @UsuarioCreacion = ?,
                        @ObservacionGeneral = ?
                    """,
                    process_code,
                    student_code,
                    payload.codigo_carrera,
                    payload.codigo_periodo,
                    current_user.login,
                    payload.observacion,
                )
                row = cursor.fetchone()
                response_payload = _row_dict(cursor, row) if row else {"ok": True, "message": "Expediente creado"}
            conn.commit()
        return response_payload
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo crear el expediente") from exc


@router.get("/student/expedientes/{expediente_id}/carta-compromiso.pdf")
def download_carta_compromiso(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> StreamingResponse:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La generación de carta está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_student_owns_expediente(current_user, expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="La carta compromiso aplica solo para prácticas preprofesionales.")
            content = _build_carta_compromiso_pdf(expediente)
        filename = _safe_filename(f"carta_compromiso_{expediente.codigo_expediente or expediente_id}.pdf")
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo generar la carta compromiso") from exc


@router.post("/student/expedientes/{expediente_id}/carta-compromiso", include_in_schema=False)
@router.post("/responsable/expedientes/{expediente_id}/carta-compromiso")
async def upload_carta_compromiso(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_DOCENTE_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    original_name = _safe_filename(file.filename or "carta_compromiso.pdf")
    extension = Path(original_name).suffix.lower()
    if extension != ".pdf":
        raise HTTPException(status_code=400, detail="Sube la carta compromiso firmada en formato PDF.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La carga de carta está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_assigned_teacher_document_upload(cursor, expediente_id, current_user)
            _ensure_practice_upload_window(expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="La carta compromiso aplica solo para prácticas preprofesionales.")

            safe_code = _safe_filename(str(expediente.codigo_expediente or expediente_id), str(expediente_id))
            target_dir = _UPLOAD_ROOT / safe_code / "carta-compromiso"
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"carta_compromiso_firmada_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/{safe_code}/carta-compromiso/{target_name}"

            cursor.execute(
                """
                EXEC pp.sp_registrar_documento
                    @expediente_id = ?,
                    @tipo_documento_codigo = ?,
                    @nombre_archivo = ?,
                    @ruta_archivo = ?,
                    @extension = ?,
                    @mime_type = ?,
                    @hash_archivo = ?,
                    @tamanio_bytes = ?,
                    @numero_paginas = NULL,
                    @fecha_documento = NULL,
                    @firmado = 1,
                    @validado = 0,
                    @observacion = ?,
                    @usuario_registro = ?
                """,
                expediente_id,
                "CARTA_COMPROMISO",
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or "application/pdf",
                digest,
                len(content),
                "Carta compromiso firmada cargada por el docente responsable asignado.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Carta compromiso subida correctamente.",
            "documento_id": getattr(row, "documento_id", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir la carta compromiso") from exc


@router.post("/student/expedientes/{expediente_id}/certificado", include_in_schema=False)
@router.post("/responsable/expedientes/{expediente_id}/certificado")
async def upload_certificado_preprofesional(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_DOCENTE_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    original_name = _safe_filename(file.filename or "certificado_practicas.pdf")
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Sube el certificado en PDF, JPG o PNG.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La carga de certificado está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_assigned_teacher_document_upload(cursor, expediente_id, current_user)
            _ensure_practice_upload_window(expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="El certificado aplica solo para prácticas preprofesionales.")

            safe_code = _safe_filename(str(expediente.codigo_expediente or expediente_id), str(expediente_id))
            target_dir = _UPLOAD_ROOT / safe_code / "certificados"
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"certificado_preprofesional_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/{safe_code}/certificados/{target_name}"

            cursor.execute(
                """
                EXEC pp.sp_registrar_documento
                    @expediente_id = ?,
                    @tipo_documento_codigo = ?,
                    @nombre_archivo = ?,
                    @ruta_archivo = ?,
                    @extension = ?,
                    @mime_type = ?,
                    @hash_archivo = ?,
                    @tamanio_bytes = ?,
                    @numero_paginas = NULL,
                    @fecha_documento = NULL,
                    @firmado = 0,
                    @validado = 0,
                    @observacion = ?,
                    @usuario_registro = ?
                """,
                expediente_id,
                "OTRO",
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or ("application/pdf" if extension == ".pdf" else "image/jpeg"),
                digest,
                len(content),
                "CERTIFICADO_PREPROFESIONALES: Certificado cargado por el docente responsable asignado.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Certificado subido correctamente.",
            "documento_id": getattr(row, "documento_id", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir el certificado") from exc


@router.get("/admin/expedientes")
def admin_expedientes(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="", max_length=10),
    search: str = Query(default="", max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    params: list[Any] = []
    where = ["1 = 1"]
    process = _clean(tipo_proceso).upper()
    if process:
        _process_code(process)
        where.append("TipoProcesoCodigo = ?")
        params.append(process)
    term = f"%{_clean(search)}%"
    if search.strip():
        where.append(
            "(CodigoExpediente LIKE ? OR Cedula_Est LIKE ? OR Apellidos_nombre LIKE ? OR CodigoCarrera LIKE ? OR CodigoPeriodo LIKE ?)"
        )
        params.extend([term, term, term, term, term])

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                legacy_where = [clause
                    .replace("TipoProcesoCodigo", "v.tipo_proceso_codigo")
                    .replace("CodigoExpediente", "v.codigo_expediente")
                    .replace("Cedula_Est", "v.cedula_est")
                    .replace("Apellidos_nombre", "v.estudiante_snapshot")
                    .replace("CodigoCarrera", "CONVERT(varchar(50), v.cod_anio_basica)")
                    .replace("CodigoPeriodo", "CONVERT(varchar(50), v.codigo_periodo)")
                    for clause in where
                ]
                cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        v.expediente_id AS ExpedienteId,
                        v.codigo_expediente AS CodigoExpediente,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.codigo_estud AS CodigoEstud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante_snapshot AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera_snapshot AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        TRY_CONVERT(varchar(50), v.cod_docente_tutor) AS CodigoDocenteTutor,
                        v.docente_tutor_snapshot AS DocenteTutor,
                        v.estado_codigo AS EstadoCodigo,
                        v.estado_expediente AS EstadoExpediente,
                        v.responsable_proceso_id AS ResponsableProcesoId,
                        v.responsable_principal AS NombreResponsable,
                        v.responsable_correo AS CorreoResponsable,
                        e.fecha_inicio AS FechaInicioCarga,
                        e.fecha_fin AS FechaFinCarga,
                        v.fecha_registro AS FechaCreacion,
                        carta.documento_id AS CartaCompromisoDocumentoId,
                        carta.estado_codigo AS CartaCompromisoEstadoCodigo,
                        carta.estado_nombre AS CartaCompromisoEstado,
                        carta.nombre_archivo AS CartaCompromisoArchivo,
                        carta.ruta_archivo AS CartaCompromisoUrl,
                        carta.fecha_registro AS CartaCompromisoFecha,
                        carta.firmado AS CartaCompromisoFirmado,
                        carta.validado AS CartaCompromisoValidado,
                        certificado.documento_id AS CertificadoDocumentoId,
                        certificado.estado_codigo AS CertificadoEstadoCodigo,
                        certificado.estado_nombre AS CertificadoEstado,
                        certificado.nombre_archivo AS CertificadoArchivo,
                        certificado.ruta_archivo AS CertificadoUrl,
                        certificado.fecha_registro AS CertificadoFecha,
                        certificado.firmado AS CertificadoFirmado,
                        certificado.validado AS CertificadoValidado
                    FROM pp.vw_admin_expedientes_control v
                    INNER JOIN pp.expediente_practica e ON e.expediente_id = v.expediente_id
                    {_latest_carta_select("v")}
                    {_latest_certificado_select("v")}
                    WHERE {' AND '.join(legacy_where)}
                    ORDER BY v.fecha_registro DESC
                    """,
                    *params,
                )
            else:
                cursor.execute(
                    f"""
                    SELECT TOP ({limit}) *
                    FROM exp.vw_expediente_resumen
                    WHERE {' AND '.join(where)}
                    ORDER BY FechaCreacion DESC
                    """,
                    *params,
                )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar expedientes") from exc


@router.get("/admin/elegibles")
def admin_eligible_students(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
    search: str = Query(default="", max_length=100),
    codigo_periodo: str = Query(default="", max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    term = f"%{_clean(search)}%"
    period = _clean(codigo_periodo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                _ensure_period_designation_table(cursor)
                cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        v.codigo_estud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        v.periodo AS NombrePeriodo,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.semestre_numero AS SemestreMaximo,
                        v.elegible AS EsElegible,
                        v.motivo_elegibilidad AS MotivoElegibilidad,
                        CASE WHEN auth.autorizacion_id IS NULL THEN 0 ELSE 1 END AS TieneAutorizacion,
                        auth.autorizacion_id AS AutorizacionId,
                        auth.nombre_archivo AS AutorizacionArchivo,
                        auth.ruta_archivo AS AutorizacionUrl,
                        auth.fecha_registro AS AutorizacionFecha,
                        CASE WHEN v.elegible = 1 OR auth.autorizacion_id IS NOT NULL THEN 1 ELSE 0 END AS PuedeInscribirse,
                        CASE WHEN v.elegible = 1 OR auth.autorizacion_id IS NOT NULL THEN 1 ELSE 0 END AS PuedeMatricular
                    FROM pp.vw_estudiantes_elegibles_proceso v
                    INNER JOIN cat.tipo_proceso tp ON tp.codigo = v.tipo_proceso_codigo
                    OUTER APPLY (
                        SELECT TOP 1 a.*
                        FROM pp.autorizacion_practica_estudiante a
                        WHERE a.tipo_proceso_id = tp.tipo_proceso_id
                          AND a.codigo_estud = TRY_CONVERT(decimal(18,0), v.codigo_estud)
                          AND a.codigo_periodo = TRY_CONVERT(numeric(18,0), v.codigo_periodo)
                          AND a.activo = 1
                        ORDER BY a.fecha_registro DESC, a.autorizacion_id DESC
                    ) auth
                    WHERE v.tipo_proceso_codigo = ?
                      AND (? = '' OR CONVERT(varchar(50), v.codigo_periodo) = ?)
                      AND (
                            ? = '%%'
                         OR v.estudiante LIKE ?
                         OR v.cedula_est LIKE ?
                         OR v.carrera LIKE ?
                         OR v.periodo LIKE ?
                         OR CONVERT(varchar(50), v.codigo_estud) LIKE ?
                      )
                    ORDER BY v.elegible DESC, v.periodo DESC, v.estudiante
                    """,
                    process,
                    period,
                    period,
                    term,
                    term,
                    term,
                    term,
                    term,
                    term,
                )
            else:
                cursor.execute(
                    f"""
                    SELECT TOP ({limit}) *
                    FROM integ.vw_estudiantes_elegibles
                    WHERE TipoProcesoCodigo = ?
                      AND EsElegible = 1
                      AND (? = '' OR CONVERT(varchar(50), CodigoPeriodo) = ?)
                      AND (
                            ? = '%%'
                         OR Apellidos_nombre LIKE ?
                         OR Cedula_Est LIKE ?
                         OR Carrera LIKE ?
                         OR NombrePeriodo LIKE ?
                         OR CONVERT(varchar(50), codigo_estud) LIKE ?
                      )
                    ORDER BY NombrePeriodo DESC, Apellidos_nombre
                    """,
                    process,
                    period,
                    period,
                    term,
                    term,
                    term,
                    term,
                    term,
                    term,
                )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar estudiantes elegibles") from exc


@router.get("/admin/periodos")
def admin_periods(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    try:
        counts: dict[str, int] = {}
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _has_object(cursor, "pp.vw_estudiantes_elegibles_proceso"):
                cursor.execute(
                    """
                    SELECT
                        CONVERT(varchar(50), codigo_periodo) AS CodigoPeriodo,
                        COUNT(DISTINCT codigo_estud) AS TotalEstudiantes
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE tipo_proceso_codigo = ?
                    GROUP BY codigo_periodo
                    """,
                    process,
                )
                counts = {
                    _clean(row.CodigoPeriodo): int(row.TotalEstudiantes or 0)
                    for row in cursor.fetchall()
                }
            elif _has_object(cursor, "integ.vw_estudiantes_elegibles"):
                cursor.execute(
                    f"""
                    SELECT
                        CodigoPeriodo,
                        COUNT(DISTINCT codigo_estud) AS TotalEstudiantes
                    FROM integ.vw_estudiantes_elegibles
                    WHERE TipoProcesoCodigo = ?
                    GROUP BY CodigoPeriodo
                    """,
                    process,
                )
                counts = {
                    _clean(row.CodigoPeriodo): int(row.TotalEstudiantes or 0)
                    for row in cursor.fetchall()
                }

        try:
            with get_connection() as academic_conn:
                academic_cursor = academic_conn.cursor()
                academic_cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        CONVERT(varchar(50), cod_periodo) AS CodigoPeriodo,
                        LTRIM(RTRIM(CONVERT(nvarchar(150), Detalle_Periodo))) AS NombrePeriodo,
                        LTRIM(RTRIM(CONVERT(nvarchar(80), Detalle_Reg))) AS DetalleRegistro,
                        LTRIM(RTRIM(CONVERT(nvarchar(50), Periodo))) AS PeriodoCorto,
                        LTRIM(RTRIM(CONVERT(varchar(10), Estado))) AS EstadoPeriodo,
                        Orden AS OrdenPeriodo,
                        NotaAprobar,
                        LTRIM(RTRIM(CONVERT(nvarchar(80), TipoMatricula))) AS TipoMatricula,
                        fechain AS FechaInicio,
                        fechafin AS FechaFin,
                        anio AS Anio,
                        LTRIM(RTRIM(CONVERT(nvarchar(150), estado_ed))) AS EstadoEducativo
                    FROM dbo.PERIODO
                    ORDER BY ISNULL(Orden, cod_periodo) DESC, cod_periodo DESC
                    """
                )
                items = _fetch_all(academic_cursor)
            for item in items:
                item["TotalEstudiantes"] = counts.get(_clean(item.get("CodigoPeriodo")), 0)
            return {"items": items, "total": len(items)}
        except (pyodbc.Error, RuntimeError):
            items = [
                {
                    "CodigoPeriodo": code,
                    "NombrePeriodo": code,
                    "DetalleRegistro": None,
                    "PeriodoCorto": None,
                    "TotalEstudiantes": total,
                    "EstadoPeriodo": None,
                    "OrdenPeriodo": code,
                    "NotaAprobar": None,
                    "TipoMatricula": None,
                    "FechaInicio": None,
                    "FechaFin": None,
                    "Anio": None,
                    "EstadoEducativo": None,
                }
                for code, total in sorted(counts.items(), key=lambda pair: int(pair[0]) if pair[0].isdigit() else 0, reverse=True)
            ]
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, 'No se pudo consultar períodos de prácticas') from exc


@router.get("/admin/designaciones-periodo")
def admin_period_designations(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                return {"items": [], "total": 0}
            _ensure_period_designation_table(cursor)
            cursor.execute(
                """
                SELECT
                    d.designacion_id AS DesignacionId,
                    tp.codigo AS TipoProcesoCodigo,
                    d.codigo_periodo AS CodigoPeriodo,
                    d.codigo_periodo_origen AS CodigoPeriodoOrigen,
                    d.codigo_docente AS CodigoDocente,
                    d.cedula_responsable AS CedulaResponsable,
                    d.nombre_responsable AS NombreResponsable,
                    d.correo_responsable AS CorreoResponsable,
                    d.rol_responsable AS RolResponsable,
                    d.cumple_requisitos AS CumpleRequisitos,
                    d.activo AS Activo,
                    d.observacion AS Observacion,
                    d.periodo_origen_snapshot AS PeriodoOrigen,
                    d.fecha_registro AS FechaRegistro
                FROM pp.designacion_periodo_responsable d
                INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = d.tipo_proceso_id
                WHERE tp.codigo = ?
                  AND d.activo = 1
                ORDER BY d.codigo_periodo DESC, d.fecha_registro DESC
                """,
                process,
            )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, 'No se pudo consultar designaciones por período') from exc


@router.get("/admin/docentes-activos")
def admin_active_teachers(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    query: str = Query(default="", max_length=250),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    search_text = _clean(query)
    search = f"%{search_text}%"
    digits = "".join(character for character in search_text if character.isdigit())
    document = f"%{digits}%" if digits else search
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(255), active_user.login), N''),
                        NULLIF(TRY_CONVERT(nvarchar(255), d.correo), N''),
                        TRY_CONVERT(nvarchar(255), d.correop)
                    ) AS login,
                    N'DOCENTE' AS tipo_usuario,
                    N'A' AS estado,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre), N''),
                        TRY_CONVERT(nvarchar(4000), active_user.Descripcion)
                    ) AS descripcion,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correop) AS correo_personal,
                    CAST(1 AS bit) AS usuario_validado
                FROM dbo.DATOSDOCENTE d
                CROSS APPLY (
                    SELECT TOP 1 u.login, u.Descripcion, u.Estado
                    FROM dbo.USUARIOS u
                    WHERE TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
                      AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(20), u.Estado), N'')))) = N'A'
                    ORDER BY TRY_CONVERT(nvarchar(255), u.login)
                ) active_user
                WHERE (
                       ? = N''
                    OR TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correo) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correop) LIKE ?
                    OR TRY_CONVERT(nvarchar(4000), active_user.Descripcion) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), d.cedula_doc) LIKE ?
                    OR TRY_CONVERT(varchar(50), d.codigo_doc) = ?
                )
                ORDER BY
                    TRY_CONVERT(nvarchar(4000), d.apellidos_nombre),
                    TRY_CONVERT(nvarchar(255), d.correo)
                """,
                search_text,
                search,
                search,
                search,
                search,
                document,
                search_text,
            )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except pyodbc.Error as exc:
        raise _db_error(exc, "No se pudieron consultar los docentes activos") from exc


@router.post("/admin/autorizaciones")
async def upload_admin_authorization(
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso_codigo: str = Form(...),
    codigo_estud: int = Form(...),
    codigo_periodo: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso_codigo)
    original_name = _safe_filename(file.filename or "autorizacion_practicas.pdf")
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Sube la autorización en PDF, JPG o PNG.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La autorización está disponible para la estructura actual de prácticas.")
            _ensure_period_designation_table(cursor)
            tipo_id = _tipo_proceso_id(cursor, process)
            cursor.execute(
                """
                SELECT TOP 1 codigo_estud
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
                """,
                process,
                codigo_periodo,
                codigo_estud,
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='No se encontró el estudiante en el período seleccionado.')

            safe_period = _safe_filename(str(codigo_periodo), "periodo")
            safe_student = _safe_filename(str(codigo_estud), "estudiante")
            target_dir = _UPLOAD_ROOT / "autorizaciones" / process / safe_period / safe_student
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"autorizacion_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/autorizaciones/{process}/{safe_period}/{safe_student}/{target_name}"

            cursor.execute(
                """
                UPDATE pp.autorizacion_practica_estudiante
                SET activo = 0
                WHERE tipo_proceso_id = ?
                  AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND activo = 1
                """,
                tipo_id,
                codigo_estud,
                codigo_periodo,
            )
            cursor.execute(
                """
                INSERT INTO pp.autorizacion_practica_estudiante (
                    tipo_proceso_id, codigo_estud, codigo_periodo, nombre_archivo,
                    ruta_archivo, extension, mime_type, hash_archivo, tamanio_bytes,
                    activo, observacion, usuario_registro
                )
                OUTPUT INSERTED.autorizacion_id AS AutorizacionId
                VALUES (?, ?, TRY_CONVERT(numeric(18,0), ?), ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                tipo_id,
                codigo_estud,
                codigo_periodo,
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or ("application/pdf" if extension == ".pdf" else "image/jpeg"),
                digest,
                len(content),
                "Autorización administrativa para habilitar prácticas antes de tercer semestre.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Autorización cargada. El estudiante queda habilitado para la inscripción institucional.",
            "autorizacion_id": getattr(row, "AutorizacionId", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir la autorización") from exc


@router.post("/admin/designaciones-periodo")
def save_period_designation(
    payload: PeriodoResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process = _process_code(payload.tipo_proceso_codigo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail='La designación por período está disponible para la estructura actual de prácticas.')
            _ensure_period_designation_table(cursor)
            ensure_operations_schema(cursor)
            tipo_id = _tipo_proceso_id(cursor, process)
            source_period = payload.codigo_periodo_origen or payload.codigo_periodo
            selected_students = sorted({int(item) for item in payload.estudiantes if int(item) > 0})
            if not selected_students:
                raise HTTPException(status_code=400, detail='Seleccione al menos un estudiante para la designación.')
            cursor.execute(
                """
                SELECT TOP 1 periodo
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                """,
                process,
                payload.codigo_periodo,
            )
            target_period_row = cursor.fetchone()
            target_period_name = _clean(target_period_row.periodo) if target_period_row else payload.codigo_periodo
            cursor.execute(
                """
                SELECT TOP 1 periodo
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                """,
                process,
                source_period,
            )
            source_period_row = cursor.fetchone()
            source_period_name = _clean(source_period_row.periodo) if source_period_row else source_period
            cursor.execute(
                """
                UPDATE pp.designacion_periodo_responsable
                SET activo = 0,
                    usuario_modifica = ?,
                    fecha_modifica = SYSDATETIME()
                WHERE tipo_proceso_id = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND codigo_docente = TRY_CONVERT(decimal(18,0), ?)
                  AND activo = 1
                """,
                current_user.login,
                tipo_id,
                payload.codigo_periodo,
                payload.codigo_docente,
            )
            cursor.execute(
                """
                INSERT INTO pp.designacion_periodo_responsable (
                    tipo_proceso_id, codigo_periodo, codigo_periodo_origen, codigo_docente, cedula_responsable,
                    nombre_responsable, correo_responsable, rol_responsable,
                    cumple_requisitos, activo, observacion, periodo_origen_snapshot, usuario_registro
                )
                OUTPUT INSERTED.designacion_id AS DesignacionId
                VALUES (?, TRY_CONVERT(numeric(18,0), ?), TRY_CONVERT(numeric(18,0), ?), TRY_CONVERT(decimal(18,0), ?), ?, ?, ?, ?, 1, 1, ?, ?, ?)
                """,
                tipo_id,
                payload.codigo_periodo,
                source_period,
                payload.codigo_docente,
                payload.cedula_responsable,
                payload.nombre_responsable,
                payload.correo_responsable,
                "RESPONSABLE",
                f"Docente responsable de {process}. Origen {source_period}; destino {payload.codigo_periodo}",
                source_period_name,
                current_user.login,
            )
            row = cursor.fetchone()
            student_placeholders = ",".join("?" for _ in selected_students)
            cursor.execute(
                f"""
                SELECT v.*
                FROM pp.vw_estudiantes_elegibles_proceso v
                INNER JOIN cat.tipo_proceso tp ON tp.codigo = v.tipo_proceso_codigo
                OUTER APPLY (
                    SELECT TOP 1 a.autorizacion_id
                    FROM pp.autorizacion_practica_estudiante a
                    WHERE a.tipo_proceso_id = tp.tipo_proceso_id
                      AND a.codigo_estud = TRY_CONVERT(decimal(18,0), v.codigo_estud)
                      AND a.codigo_periodo = TRY_CONVERT(numeric(18,0), v.codigo_periodo)
                      AND a.activo = 1
                    ORDER BY a.fecha_registro DESC, a.autorizacion_id DESC
                ) auth
                WHERE v.tipo_proceso_codigo = ?
                  AND v.codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND v.codigo_estud IN ({student_placeholders})
                  AND (v.elegible = 1 OR auth.autorizacion_id IS NOT NULL)
                """,
                process,
                source_period,
                *selected_students,
            )
            sources = cursor.fetchall()
            found_students = {int(item.codigo_estud) for item in sources}
            missing_students = [item for item in selected_students if item not in found_students]
            if missing_students:
                raise HTTPException(
                    status_code=400,
                    detail=f"Estudiantes no encontrados, no están en tercer semestre o no tienen autorización cargada: {', '.join(map(str, missing_students))}",
                )
            expediente_ids: list[int] = []
            for source in sources:
                expediente_id = _ensure_expediente_for_source(
                    cursor,
                    source,
                    process,
                    tipo_id,
                    current_user.login,
                    f"Expediente creado desde el período académico de referencia {source_period} para la inscripción institucional del período {payload.codigo_periodo}.",
                    payload.codigo_periodo,
                    target_period_name,
                )
                _register_responsable_for_expediente(
                    cursor,
                    expediente_id,
                    payload.codigo_docente,
                    payload.nombre_responsable,
                    payload.cedula_responsable,
                    payload.correo_responsable,
                    "RESPONSABLE",
                    current_user.login,
                    f"Designación por período {payload.codigo_periodo}.",
                )
                expediente_ids.append(expediente_id)
                cursor.execute(
                    """
                    INSERT INTO pp.designacion_periodo_estudiante (
                        designacion_id, expediente_id, codigo_estud, cedula_est, estudiante_snapshot,
                        codigo_periodo_origen, cod_anio_basica, carrera_snapshot, cumple_requisitos, activo,
                        observacion, periodo_origen_snapshot, usuario_registro
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)
                    """,
                    getattr(row, "DesignacionId", None),
                    expediente_id,
                    int(source.codigo_estud),
                    str(source.cedula_est),
                    _clean(source.estudiante),
                    int(source.codigo_periodo),
                    int(source.cod_anio_basica),
                    _clean(source.carrera),
                    f"Asignado a docente {payload.codigo_docente}. Origen {source_period}; destino {payload.codigo_periodo}",
                    source_period_name,
                    current_user.login,
                )
            conn.commit()
        return {
            "ok": True,
            "message": 'Inscripción institucional por período registrada correctamente.',
            "alcance": "INSTITUCIONAL_CUMPLIMIENTO",
            "modifica_matricula_academica": False,
            "designacion_id": getattr(row, "DesignacionId", None) if row else None,
            "expedientes_actualizados": len(expediente_ids),
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, 'No se pudo guardar la designación por período') from exc


@router.post("/admin/matriculas", include_in_schema=False)
@router.post("/admin/inscripciones-cumplimiento")
def enroll_practices_students(
    payload: InscripcionCumplimientoPayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process = _process_code(payload.tipo_proceso_codigo)
    target_period = _clean(payload.codigo_periodo)
    if not target_period.isdigit():
        raise HTTPException(status_code=400, detail="El período institucional del proceso debe tener un código numérico válido.")
    _validate_upload_window(payload.fecha_inicio_carga, payload.fecha_fin_carga)

    selected: dict[tuple[int, int, int], InscripcionPracticaEstudiantePayload] = {}
    for item in payload.estudiantes:
        career = _clean(item.codigo_carrera)
        source_period = _clean(item.codigo_periodo_origen)
        if not career.isdigit() or not source_period.isdigit():
            raise HTTPException(
                status_code=400,
                detail="La carrera y el período de origen deben tener códigos numéricos válidos.",
            )
        key = (int(item.codigo_estud), int(career), int(source_period))
        selected[key] = item
    if not selected:
        raise HTTPException(status_code=400, detail="Seleccione al menos un estudiante para inscribir en el proceso institucional.")
    if len(selected) > 500:
        raise HTTPException(status_code=400, detail="Puede registrar hasta 500 inscripciones institucionales por operación.")

    source_conditions = " OR ".join(
        "(v.codigo_estud = ? AND v.cod_anio_basica = ? AND v.codigo_periodo = ?)" for _ in selected
    )
    source_params: list[Any] = [process]
    for student_code, career_code, source_period_code in selected:
        source_params.extend([student_code, career_code, source_period_code])

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(
                    status_code=400,
                    detail="La inscripción de cumplimiento está disponible para la estructura operativa actual de prácticas.",
                )
            _ensure_period_designation_table(cursor)
            ensure_operations_schema(cursor)
            process_id = _tipo_proceso_id(cursor, process)
            cursor.execute(
                """
                SELECT TOP 1 periodo
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                """,
                process,
                target_period,
            )
            target_period_row = cursor.fetchone()
            target_period_name = _clean(target_period_row.periodo) if target_period_row else target_period

            cursor.execute(
                f"""
                SELECT v.*
                FROM pp.vw_estudiantes_elegibles_proceso v
                INNER JOIN cat.tipo_proceso tp ON tp.codigo = v.tipo_proceso_codigo
                OUTER APPLY (
                    SELECT TOP 1 a.autorizacion_id
                    FROM pp.autorizacion_practica_estudiante a
                    WHERE a.tipo_proceso_id = tp.tipo_proceso_id
                      AND a.codigo_estud = TRY_CONVERT(decimal(18,0), v.codigo_estud)
                      AND a.codigo_periodo = TRY_CONVERT(numeric(18,0), v.codigo_periodo)
                      AND a.activo = 1
                    ORDER BY a.fecha_registro DESC, a.autorizacion_id DESC
                ) auth
                WHERE v.tipo_proceso_codigo = ?
                  AND ({source_conditions})
                  AND (v.elegible = 1 OR auth.autorizacion_id IS NOT NULL)
                """,
                *source_params,
            )
            source_by_key: dict[tuple[int, int, int], Any] = {}
            for source in cursor.fetchall():
                key = (int(source.codigo_estud), int(source.cod_anio_basica), int(source.codigo_periodo))
                source_by_key.setdefault(key, source)
            missing = [key for key in selected if key not in source_by_key]
            if missing:
                missing_text = ", ".join(str(student_code) for student_code, _, _ in missing[:20])
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No se pudo inscribir a los siguientes estudiantes porque no cumplen los requisitos "
                        f"o no tienen una autorización vigente: {missing_text}."
                    ),
                )

            expediente_ids: list[int] = []
            for key in selected:
                source = source_by_key[key]
                expediente_ids.append(
                    _ensure_expediente_for_source(
                        cursor,
                        source,
                        process,
                        process_id,
                        current_user.login,
                        payload.observacion
                        or f"Inscripción institucional en {PROCESS_LABELS[process]} para el período {target_period_name}.",
                        target_period,
                        target_period_name,
                        payload.fecha_inicio_carga,
                        payload.fecha_fin_carga,
                    )
                )
            conn.commit()
        return {
            "ok": True,
            "message": f"Se registraron {len(expediente_ids)} inscripción(es) institucional(es) correctamente.",
            "alcance": "INSTITUCIONAL_CUMPLIMIENTO",
            "modifica_matricula_academica": False,
            "inscripciones_registradas": len(expediente_ids),
            "expedientes_matriculados": len(expediente_ids),
            "expediente_ids": expediente_ids,
            "fecha_inicio_carga": payload.fecha_inicio_carga.isoformat(),
            "fecha_fin_carga": payload.fecha_fin_carga.isoformat(),
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo registrar la inscripción institucional de prácticas") from exc


@router.post("/admin/matriculas/responsable", include_in_schema=False)
@router.post("/admin/inscripciones-cumplimiento/responsable")
def assign_practices_responsible(
    payload: AsignacionResponsablePracticasPayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process = _process_code(payload.tipo_proceso_codigo)
    target_period = _clean(payload.codigo_periodo)
    teacher_code = _clean(payload.codigo_docente)
    if not target_period.isdigit() or not teacher_code.isdigit():
        raise HTTPException(
            status_code=400,
            detail="El período y el código del responsable deben tener valores numéricos válidos.",
        )
    expediente_ids = sorted({int(item) for item in payload.expediente_ids if int(item) > 0})
    if not expediente_ids:
        raise HTTPException(status_code=400, detail="Seleccione al menos una inscripción institucional para asignar al responsable.")
    if len(expediente_ids) > 500:
        raise HTTPException(status_code=400, detail="Puede asignar hasta 500 inscripciones institucionales por operación.")

    placeholders = ",".join("?" for _ in expediente_ids)
    try:
        active_teacher = _active_teacher_by_code(teacher_code)
        if not active_teacher:
            raise HTTPException(
                status_code=400,
                detail=(
                    "El docente seleccionado no tiene un usuario activo (A) en USUARIOS. "
                    "Actualice su estado antes de asignarlo como responsable."
                ),
            )
        teacher_name = active_teacher["nombre"]
        teacher_document = active_teacher["cedula"] or None
        teacher_email = active_teacher["correo"] or None
        if not teacher_name:
            raise HTTPException(status_code=400, detail="El docente activo no tiene un nombre válido registrado.")

        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(
                    status_code=400,
                    detail="La asignación institucional está disponible para la estructura operativa actual de prácticas.",
                )
            _ensure_period_designation_table(cursor)
            ensure_operations_schema(cursor)
            process_id = _tipo_proceso_id(cursor, process)
            cursor.execute(
                f"""
                SELECT
                    e.expediente_id,
                    e.codigo_estud,
                    e.cedula_est,
                    e.estudiante_snapshot,
                    e.cod_anio_basica,
                    e.carrera_snapshot,
                    e.codigo_periodo_origen,
                    e.periodo_origen_snapshot
                FROM pp.expediente_practica e
                INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
                WHERE tp.codigo = ?
                  AND e.codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND e.expediente_id IN ({placeholders})
                """,
                process,
                target_period,
                *expediente_ids,
            )
            enrollments = cursor.fetchall()
            found_ids = {int(item.expediente_id) for item in enrollments}
            missing_ids = [item for item in expediente_ids if item not in found_ids]
            if missing_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Solo se puede asignar un responsable a estudiantes previamente inscritos en el proceso. "
                        f"No se encontraron las inscripciones: {', '.join(map(str, missing_ids[:20]))}."
                    ),
                )

            source_codes = {
                int(item.codigo_periodo_origen)
                for item in enrollments
                if item.codigo_periodo_origen is not None
            }
            source_names = {
                _clean(item.periodo_origen_snapshot)
                for item in enrollments
                if _clean(item.periodo_origen_snapshot)
            }
            common_source_code = next(iter(source_codes)) if len(source_codes) == 1 else None
            common_source_name = next(iter(source_names)) if len(source_names) == 1 else "Varios períodos de origen"

            cursor.execute(
                f"""
                UPDATE de
                SET de.activo = 0
                FROM pp.designacion_periodo_estudiante de
                WHERE de.expediente_id IN ({placeholders})
                  AND de.activo = 1
                """,
                *expediente_ids,
            )
            cursor.execute(
                """
                INSERT INTO pp.designacion_periodo_responsable (
                    tipo_proceso_id, codigo_periodo, codigo_periodo_origen, codigo_docente,
                    cedula_responsable, nombre_responsable, correo_responsable, rol_responsable,
                    cumple_requisitos, activo, observacion, periodo_origen_snapshot, usuario_registro
                )
                OUTPUT INSERTED.designacion_id AS DesignacionId
                VALUES (?, TRY_CONVERT(numeric(18,0), ?), ?, TRY_CONVERT(decimal(18,0), ?),
                        ?, ?, ?, ?, 1, 1, ?, ?, ?)
                """,
                process_id,
                target_period,
                common_source_code,
                teacher_code,
                teacher_document,
                teacher_name,
                teacher_email,
                payload.rol_responsable,
                f"Responsable asignado después de la inscripción institucional de {len(enrollments)} estudiante(s).",
                common_source_name,
                current_user.login,
            )
            designation = cursor.fetchone()
            designation_id = int(designation.DesignacionId)

            for enrollment in enrollments:
                _register_responsable_for_expediente(
                    cursor,
                    int(enrollment.expediente_id),
                    teacher_code,
                    teacher_name,
                    teacher_document,
                    teacher_email,
                    payload.rol_responsable,
                    current_user.login,
                    f"Responsable asignado para el período {target_period} después de la inscripción institucional.",
                )
                update_compliance_enrollment_status(
                    cursor,
                    expediente_id=int(enrollment.expediente_id),
                    state="EN_PROCESO",
                    user=current_user.login,
                )
                cursor.execute(
                    """
                    INSERT INTO pp.designacion_periodo_estudiante (
                        designacion_id, expediente_id, codigo_estud, cedula_est, estudiante_snapshot,
                        codigo_periodo_origen, cod_anio_basica, carrera_snapshot, cumple_requisitos,
                        activo, observacion, periodo_origen_snapshot, usuario_registro
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)
                    """,
                    designation_id,
                    int(enrollment.expediente_id),
                    int(enrollment.codigo_estud),
                    _clean(enrollment.cedula_est),
                    _clean(enrollment.estudiante_snapshot),
                    enrollment.codigo_periodo_origen,
                    enrollment.cod_anio_basica,
                    _clean(enrollment.carrera_snapshot),
                    f"Asignado al responsable {teacher_code} después de confirmar la inscripción institucional.",
                    _clean(enrollment.periodo_origen_snapshot),
                    current_user.login,
                )
            conn.commit()
        return {
            "ok": True,
            "message": f"Se asignó el responsable a {len(enrollments)} inscripción(es) institucional(es) correctamente.",
            "alcance": "INSTITUCIONAL_CUMPLIMIENTO",
            "modifica_matricula_academica": False,
            "designacion_id": designation_id,
            "expedientes_asignados": len(enrollments),
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo asignar el responsable de prácticas") from exc


@router.get("/responsable/avance")
def responsable_progress(
    current_user: Annotated[SessionUser, Depends(_RESPONSIBLE_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    is_admin = current_user.rol in _ADMIN_ROLES
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                return {"summary": {}, "items": []}

            required_count = len(_required_document_codes(process))

            params: list[Any] = [process]
            user_filters: list[str] = []
            if not is_admin:
                if current_user.cedula:
                    user_filters.append("LTRIM(RTRIM(rp.cedula_ruc)) = ?")
                    params.append(_clean(current_user.cedula))
                for email in {_clean(current_user.email).lower(), _clean(current_user.login).lower()} - {""}:
                    user_filters.append("LOWER(LTRIM(RTRIM(rp.correo))) = ?")
                    params.append(email)
                if current_user.codigo_doc is not None:
                    user_filters.append("TRY_CONVERT(varchar(50), rp.codigo_referencia) = ?")
                    params.append(str(current_user.codigo_doc))
                if not user_filters:
                    return {
                        "summary": {
                            "tipo_proceso": process,
                            "expedientes": 0,
                            "avance": 0,
                            "avance_documental": 0,
                            "documentos_requeridos": required_count,
                            "documentos_cargados": 0,
                            "documentos_validados": 0,
                            "documentos_pendientes": 0,
                        },
                        "items": [],
                    }

            where_user = "" if is_admin else f"AND ({' OR '.join(user_filters)})"
            cursor.execute(
                f"""
                SELECT
                    v.expediente_id AS ExpedienteId,
                    v.codigo_expediente AS CodigoExpediente,
                    v.cedula_est AS Cedula_Est,
                    v.estudiante_snapshot AS Apellidos_nombre,
                    v.carrera_snapshot AS Carrera,
                    v.codigo_periodo AS CodigoPeriodo,
                    v.periodo_snapshot AS Periodo,
                    e.fecha_inicio AS FechaInicioCarga,
                    e.fecha_fin AS FechaFinCarga,
                    v.estado_expediente AS EstadoExpediente,
                    ee.codigo AS EstadoCodigo,
                    v.responsable_principal AS NombreResponsable,
                    ISNULL(v.documentos_firmados, 0) AS DocumentosFirmados,
                    e.horas_requeridas AS HorasRequeridas,
                    e.horas_reconocidas AS HorasReconocidas,
                    e.horas_asistencia_validadas AS HorasAsistenciaValidadas,
                    rp.puede_validar_documentos AS PuedeValidarDocumentos,
                    rp.puede_aprobar AS PuedeAprobar,
                    carta.estado_nombre AS CartaCompromisoEstado,
                    certificado.estado_nombre AS CertificadoEstado
                FROM pp.vw_admin_expedientes_control v
                INNER JOIN pp.expediente_practica e ON e.expediente_id = v.expediente_id
                INNER JOIN cat.estado_expediente ee ON ee.estado_expediente_id = e.estado_expediente_id
                INNER JOIN pp.responsable_proceso rp ON rp.responsable_proceso_id = v.responsable_proceso_id
                {_latest_carta_select("v")}
                {_latest_certificado_select("v")}
                WHERE v.tipo_proceso_codigo = ?
                  AND rp.activo = 1
                  {where_user}
                ORDER BY v.periodo_snapshot DESC, v.estudiante_snapshot
                """,
                *params,
            )
            items = _fetch_all(cursor)
            for item in items:
                documents = _required_documents_status(cursor, int(item["ExpedienteId"]), process)
                compliance = _document_compliance_summary(documents)
                loaded = int(compliance["loaded"])
                validated = int(compliance["validated"])
                recognized_hours = float(item.get("HorasReconocidas") or 0)
                required_hours = _required_hours(process)
                item["TotalDocumentos"] = loaded
                item["DocumentosValidados"] = validated
                item["DocumentosPendientes"] = compliance["pending_upload"]
                item["DocumentosRequeridos"] = compliance["required"]
                item["DocumentosDetalle"] = documents
                item["ListoParaAprobar"] = loaded == required_count and recognized_hours >= required_hours
                item["AvanceDocumental"] = compliance["upload_percentage"]
                item["AvanceValidacionDocumental"] = compliance["validation_percentage"]
                item["Avance"] = compliance["validation_percentage"]

        total_required = required_count * len(items)
        total_validated = sum(int(item.get("DocumentosValidados") or 0) for item in items)
        total_loaded = sum(int(item.get("TotalDocumentos") or 0) for item in items)
        total_pending = max(total_required - total_validated, 0)
        summary = {
            "tipo_proceso": process,
            "expedientes": len(items),
            "avance": round((total_validated / max(total_required, 1)) * 100, 2),
            "avance_documental": round((total_loaded / max(total_required, 1)) * 100, 2),
            "documentos_requeridos": total_required,
            "documentos_cargados": total_loaded,
            "documentos_validados": total_validated,
            "documentos_pendientes": total_pending,
        }
        return {"summary": summary, "items": items}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar el avance del responsable") from exc


@router.get("/responsable/expedientes/{expediente_id}")
def responsable_expediente_detail(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_RESPONSIBLE_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(
                    status_code=400,
                    detail="La revisión docente está disponible para la estructura vigente de prácticas.",
                )
            ensure_operations_schema(cursor)
            return _legacy_review_detail(cursor, expediente_id, current_user)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar el expediente para revisión") from exc


@router.post("/responsable/expedientes/{expediente_id}/revision")
def review_responsable_expediente(
    expediente_id: int,
    payload: ExpedienteReviewPayload,
    current_user: Annotated[SessionUser, Depends(_RESPONSIBLE_ACCESS)],
) -> dict[str, Any]:
    process = _process_code(payload.tipo_proceso_codigo)
    decision = _clean(payload.decision).upper()
    observation = _clean(payload.observacion)
    review_result = {
        "APROBAR": "VALIDADO",
        "OBSERVAR": "OBSERVADO",
        "RECHAZAR": "RECHAZADO",
    }

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(
                    status_code=400,
                    detail="La revisión docente está disponible para la estructura vigente de prácticas.",
                )
            ensure_operations_schema(cursor)

            expediente_row = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente_row:
                raise HTTPException(status_code=404, detail="No existe el expediente solicitado.")
            expediente = _row_dict(cursor, expediente_row)
            expediente_process = _process_code(expediente.get("tipo_proceso_codigo"))
            if expediente_process != process:
                raise HTTPException(status_code=400, detail="El proceso indicado no corresponde al expediente.")

            current_state = _clean(expediente.get("estado_expediente_codigo")).upper()
            if current_state in {"ANULADO", "CERRADO"}:
                raise HTTPException(
                    status_code=400,
                    detail=f"No se puede revisar un expediente con estado {current_state.lower()}.",
                )

            assignment = _responsible_assignment(
                cursor,
                expediente_id,
                current_user,
                require_approval=decision in {"APROBAR", "RECHAZAR"},
            )
            documents = _required_documents_status(cursor, expediente_id, process)
            configuration = effective_process_configuration(
                cursor,
                process_code=process,
                career_code=expediente.get("cod_anio_basica"),
                level=expediente.get("semestre_numero") or expediente.get("semestre"),
                period_code=expediente.get("codigo_periodo"),
            )
            required_hours = float(configuration["horas_requeridas"])
            minimum_grade = float(configuration["nota_minima_aprobacion"])
            validation_errors = _review_validation_errors(
                decision,
                float(payload.horas_verificadas),
                required_hours,
                documents,
                payload.documentos_corroborados,
                observation,
            )
            if validation_errors:
                raise HTTPException(status_code=400, detail=" ".join(validation_errors))

            new_state_code = _REVIEW_EXPEDIENT_STATE_BY_DECISION[decision]
            new_state_id = _catalog_state_id(
                cursor,
                "cat.estado_expediente",
                "estado_expediente_id",
                new_state_code,
            )

            if decision == "APROBAR":
                validated_document_state_id = _catalog_state_id(
                    cursor,
                    "cat.estado_documento",
                    "estado_documento_id",
                    "VALIDADO",
                )
                for document in documents:
                    document_id = document.get("DocumentoId")
                    if not document_id:
                        continue
                    cursor.execute(
                        """
                        UPDATE pp.documento_practica
                        SET estado_documento_id = ?,
                            validado = 1,
                            fecha_validacion = SYSDATETIME(),
                            usuario_valida = ?,
                            observacion = COALESCE(NULLIF(?, ''), observacion)
                        WHERE documento_id = ?
                        """,
                        validated_document_state_id,
                        current_user.login,
                        observation,
                        int(document_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO pp.revision_documental_practica (
                            expediente_id, documento_id, revisor_usuario, resultado,
                            observacion, accion_requerida
                        ) VALUES (?, ?, ?, 'VALIDADO', ?, NULL)
                        """,
                        expediente_id,
                        int(document_id),
                        current_user.login,
                        observation or "Documento obligatorio corroborado para la aprobación del proceso.",
                    )

            cursor.execute(
                """
                INSERT INTO pp.revision_documental_practica (
                    expediente_id, documento_id, revisor_usuario, resultado,
                    observacion, accion_requerida
                ) VALUES (?, NULL, ?, ?, ?, ?)
                """,
                expediente_id,
                current_user.login,
                review_result[decision],
                observation or (
                    "El responsable corroboró horas y documentos obligatorios."
                    if decision == "APROBAR"
                    else None
                ),
                observation if decision in {"OBSERVAR", "RECHAZAR"} else None,
            )
            cursor.execute(
                """
                UPDATE pp.expediente_practica
                SET horas_requeridas = ?,
                    horas_reconocidas = ?,
                    horas_asistencia_validadas = ?,
                    estado_expediente_id = ?,
                    observacion = COALESCE(NULLIF(?, ''), observacion),
                    usuario_modifica = ?,
                    fecha_modifica = SYSDATETIME()
                WHERE expediente_id = ?
                """,
                required_hours,
                float(payload.horas_verificadas),
                float(payload.horas_verificadas),
                new_state_id,
                observation,
                current_user.login,
                expediente_id,
            )
            if int(expediente.get("estado_expediente_id") or 0) != new_state_id:
                cursor.execute(
                    """
                    INSERT INTO pp.historial_estado_expediente (
                        expediente_id, estado_anterior_id, estado_nuevo_id,
                        motivo, usuario_registro
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    expediente_id,
                    expediente.get("estado_expediente_id"),
                    new_state_id,
                    observation or f"Decisión docente: {decision.lower()}.",
                    current_user.login,
                )
            update_compliance_enrollment_status(
                cursor,
                expediente_id=expediente_id,
                state={
                    "APROBAR": "EN_REVISION",
                    "OBSERVAR": "EN_REVISION",
                    "RECHAZAR": "NO_CUMPLIDO",
                }[decision],
                user=current_user.login,
            )
            if decision == "APROBAR":
                cursor.execute(
                    "SELECT evaluacion_id FROM ops.evaluacion_practica WHERE expediente_id = ?",
                    expediente_id,
                )
                evaluation_row = cursor.fetchone()
                if evaluation_row:
                    evaluation_id = int(evaluation_row[0])
                    cursor.execute(
                        """
                        UPDATE ops.evaluacion_practica
                        SET estado = N'PENDIENTE_CALIFICACION', calificacion = NULL,
                            resultado = N'PENDIENTE', nota_minima_aprobacion = ?,
                            origen_calificacion = NULL, detalle_calculo = NULL,
                            observacion_revision = ?, observacion_calificacion = NULL,
                            revisado_por = ?, fecha_revision = SYSDATETIME(),
                            calificado_por = NULL, fecha_calificacion = NULL,
                            usuario_modifica = ?, fecha_modifica = SYSDATETIME()
                        WHERE evaluacion_id = ?
                        """,
                        minimum_grade,
                        observation or "Documentos y horas corroborados por el responsable.",
                        current_user.login,
                        current_user.login,
                        evaluation_id,
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO ops.evaluacion_practica (
                            expediente_id, estado, resultado, nota_minima_aprobacion, observacion_revision,
                            revisado_por, fecha_revision, usuario_registro
                        ) OUTPUT INSERTED.evaluacion_id
                        VALUES (?, N'PENDIENTE_CALIFICACION', N'PENDIENTE', ?, ?, ?, SYSDATETIME(), ?)
                        """,
                        expediente_id,
                        minimum_grade,
                        observation or "Documentos y horas corroborados por el responsable.",
                        current_user.login,
                        current_user.login,
                    )
                    evaluation_id = int(cursor.fetchone()[0])
                record_evaluation_history(
                    cursor,
                    evaluation_id=evaluation_id,
                    action="HABILITAR_CALIFICACION",
                    user=current_user.login,
                    observation=observation or "Revisión documental finalizada.",
                )
                write_operations_audit(
                    cursor,
                    entity="EVALUACION_PRACTICA",
                    entity_id=evaluation_id,
                    action="HABILITAR_CALIFICACION",
                    user=current_user.login,
                    detail=observation or "Revisión documental finalizada.",
                )
            conn.commit()

        if decision == "APROBAR":
            titulation_sync = {
                "sincronizado": False,
                "pendiente": True,
                "motivo": "La revisión terminó; el expediente está a la espera de la calificación final.",
            }
        else:
            titulation_sync = {
                "sincronizado": False,
                "motivo": "La decisión no habilita el requisito de Titulación.",
            }
        return {
            "ok": True,
            "message": {
                "APROBAR": "Revisión finalizada; expediente habilitado para calificación.",
                "OBSERVAR": "Expediente observado; el estudiante debe corregir la documentación indicada.",
                "RECHAZAR": "Expediente rechazado con la justificación registrada.",
            }[decision],
            "decision": decision,
            "estado": new_state_code,
            "responsable": assignment,
            "titulacion": titulation_sync,
        }
    except HTTPException:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo registrar la revisión docente") from exc


@router.post("/admin/responsables")
def create_responsable(
    payload: ResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process_code = _process_code(payload.tipo_proceso_codigo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                if not payload.expediente_id:
                    raise HTTPException(status_code=400, detail='Seleccione un expediente para designar el responsable.')
                cursor.execute(
                    """
                    EXEC pp.sp_registrar_responsable_proceso
                        @expediente_id = ?,
                        @tipo_responsable_codigo = ?,
                        @tipo_referencia = ?,
                        @codigo_referencia = ?,
                        @cedula_ruc = ?,
                        @nombres = ?,
                        @correo = ?,
                        @telefono = ?,
                        @cargo = ?,
                        @institucion = ?,
                        @direccion = ?,
                        @fecha_inicio = NULL,
                        @fecha_fin = NULL,
                        @principal = 1,
                        @puede_validar_documentos = 1,
                        @puede_aprobar = 1,
                        @observacion = ?,
                        @usuario_registro = ?
                    """,
                    payload.expediente_id,
                    "RESPONSABLE_ACADEMICO",
                    "DOCENTE" if payload.codigo_docente else "USUARIO",
                    int(payload.codigo_docente) if payload.codigo_docente and payload.codigo_docente.isdigit() else None,
                    payload.cedula_responsable,
                    payload.nombre_responsable,
                    payload.correo_responsable,
                    None,
                    payload.rol_responsable,
                    None,
                    None,
                    f"Designación {process_code}",
                    current_user.login,
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    UPDATE pp.expediente_practica
                    SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
                        docente_tutor_snapshot = ?,
                        usuario_modifica = ?,
                        fecha_modifica = SYSDATETIME()
                    WHERE expediente_id = ?
                    """,
                    payload.codigo_docente,
                    payload.nombre_responsable,
                    current_user.login,
                    payload.expediente_id,
                )
                conn.commit()
                return _row_dict(cursor, row) if row else {"message": "Responsable designado correctamente."}

            cursor.execute("SELECT TipoProcesoId FROM cat.TipoProceso WHERE Codigo = ? AND Activo = 1", process_code)
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Tipo de proceso no encontrado")
            tipo_proceso_id = int(row.TipoProcesoId)
            cursor.execute(
                """
                INSERT INTO resp.ResponsableProceso
                    (TipoProcesoId, CodigoDocente, CedulaResponsable, NombreResponsable, CorreoResponsable, RolResponsable)
                OUTPUT INSERTED.ResponsableProcesoId
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                tipo_proceso_id,
                payload.codigo_docente,
                payload.cedula_responsable,
                payload.nombre_responsable,
                payload.correo_responsable,
                payload.rol_responsable,
            )
            responsable_id = int(cursor.fetchone().ResponsableProcesoId)
            conn.commit()
        return {
            "responsable_proceso_id": responsable_id,
            "message": f"Responsable registrado por {current_user.login}.",
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el responsable") from exc


@router.post("/admin/expedientes/{expediente_id}/responsable")
def assign_responsable(
    expediente_id: int,
    payload: AssignResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                cursor.execute(
                    """
                    SELECT TOP 1
                        COALESCE(trp.codigo, 'RESPONSABLE_ACADEMICO') AS tipo_responsable_codigo,
                        rp.tipo_referencia,
                        rp.codigo_referencia,
                        rp.cedula_ruc,
                        rp.nombres,
                        rp.correo,
                        rp.telefono,
                        rp.cargo,
                        rp.institucion,
                        rp.direccion
                    FROM pp.responsable_proceso rp
                    LEFT JOIN cat.tipo_responsable_proceso trp ON trp.tipo_responsable_id = rp.tipo_responsable_id
                    WHERE rp.responsable_proceso_id = ?
                      AND rp.activo = 1
                    """,
                    payload.responsable_proceso_id,
                )
                responsable = cursor.fetchone()
                if not responsable:
                    raise HTTPException(status_code=404, detail="Responsable no encontrado o inactivo.")

                cursor.execute(
                    """
                    EXEC pp.sp_registrar_responsable_proceso
                        @expediente_id = ?,
                        @tipo_responsable_codigo = ?,
                        @tipo_referencia = ?,
                        @codigo_referencia = ?,
                        @cedula_ruc = ?,
                        @nombres = ?,
                        @correo = ?,
                        @telefono = ?,
                        @cargo = ?,
                        @institucion = ?,
                        @direccion = ?,
                        @fecha_inicio = NULL,
                        @fecha_fin = NULL,
                        @principal = 1,
                        @puede_validar_documentos = 1,
                        @puede_aprobar = 1,
                        @observacion = ?,
                        @usuario_registro = ?
                    """,
                    expediente_id,
                    responsable.tipo_responsable_codigo,
                    responsable.tipo_referencia,
                    responsable.codigo_referencia,
                    responsable.cedula_ruc,
                    responsable.nombres,
                    responsable.correo,
                    responsable.telefono,
                    responsable.cargo,
                    responsable.institucion,
                    responsable.direccion,
                    "Asignación de responsable existente",
                    current_user.login,
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    UPDATE pp.expediente_practica
                    SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
                        docente_tutor_snapshot = ?,
                        usuario_modifica = ?,
                        fecha_modifica = SYSDATETIME()
                    WHERE expediente_id = ?
                    """,
                    responsable.codigo_referencia,
                    responsable.nombres,
                    current_user.login,
                    expediente_id,
                )
                conn.commit()
                return _row_dict(cursor, row) if row else {"message": "Responsable asignado correctamente."}

            cursor.execute(
                """
                EXEC exp.sp_asignar_responsable_proceso
                    @ExpedienteId = ?,
                    @ResponsableProcesoId = ?,
                    @UsuarioActualizacion = ?
                """,
                expediente_id,
                payload.responsable_proceso_id,
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return _row_dict(cursor, row) if row else {"message": "Responsable asignado correctamente."}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo asignar el responsable") from exc
