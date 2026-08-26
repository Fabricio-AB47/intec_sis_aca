from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import re
from threading import Lock
from typing import Any, Iterable

import pyodbc

from app.core.audit_context import get_audit_context
from app.services.db import get_integration_control_connection


logger = logging.getLogger(__name__)


class IntegrationHistoryUnavailableError(RuntimeError):
    """Raised when the central integration history cannot be consulted."""


_bootstrap_lock = Lock()
_schema_bootstrapped = False
_SENSITIVE_KEYS = {
    "authorization",
    "clave",
    "contrasena",
    "contraseña",
    "cookie",
    "password",
    "secret",
    "token",
}
_SENSITIVE_JSON_VALUE = re.compile(
    r'(?i)("(?:password|contrasena|contraseña|token|secret|authorization|cookie|clave)"\s*:\s*)"[^"]*"'
)


def _normalized_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "").replace("-", "")


def redact_sensitive_data(value: Any) -> Any:
    """Redacts credentials recursively before audit information leaves the API."""
    if isinstance(value, dict):
        return {
            key: "[PROTEGIDO]"
            if any(part in _normalized_key(key) for part in _SENSITIVE_KEYS)
            else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_data(item) for item in value]
    return value


def _safe_json_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return redact_sensitive_data(value)
    try:
        return redact_sensitive_data(json.loads(value))
    except (TypeError, ValueError):
        return _SENSITIVE_JSON_VALUE.sub(r'\1"[PROTEGIDO]"', value)


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(redact_sensitive_data(value), ensure_ascii=False, default=str)


def _rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description or ()]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _row(cursor: pyodbc.Cursor) -> dict[str, Any] | None:
    columns = [column[0] for column in cursor.description or ()]
    item = cursor.fetchone()
    return dict(zip(columns, item, strict=False)) if item else None


def _as_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"0x{bytes(value).hex()}"
    return value


def _serialize_record(record: dict[str, Any], *, include_json: bool = False) -> dict[str, Any]:
    result = {key: _as_iso(value) for key, value in record.items()}
    if include_json:
        for key in ("ColumnasAfectadas", "ClavesAfectadas", "DatosAntes", "DatosDespues", "PeriodosJson", "MetadatosJson"):
            if key in result:
                result[key] = _safe_json_value(result[key])
    return result


def ensure_integration_history_schema() -> None:
    global _schema_bootstrapped
    if _schema_bootstrapped:
        return
    with _bootstrap_lock:
        if _schema_bootstrapped:
            return
        try:
            with get_integration_control_connection() as connection:
                cursor = connection.cursor()
                cursor.execute("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud') EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo')")
                cursor.execute("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo')")
                cursor.execute(
                    """
                    IF OBJECT_ID(N'aud.EventoInformeDocente', N'U') IS NULL
                    BEGIN
                        CREATE TABLE aud.EventoInformeDocente
                        (
                            EventoInformeId BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                            FechaEventoUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
                            Etapa VARCHAR(20) NOT NULL,
                            Estado VARCHAR(20) NOT NULL,
                            TipoDocumento VARCHAR(80) NOT NULL,
                            CodigoDocente NVARCHAR(50) NULL,
                            CedulaDocente NVARCHAR(30) NULL,
                            NombreDocente NVARCHAR(300) NULL,
                            CodigoMateria NVARCHAR(100) NULL,
                            NombreMateria NVARCHAR(300) NULL,
                            PeriodosJson NVARCHAR(MAX) NULL,
                            Paralelo NVARCHAR(30) NULL,
                            Jornada NVARCHAR(100) NULL,
                            NombreArchivo NVARCHAR(500) NULL,
                            RutaDocumento NVARCHAR(1500) NULL,
                            UrlDocumento NVARCHAR(2000) NULL,
                            CantidadEstudiantes INT NULL,
                            UsuarioAplicacion NVARCHAR(256) NOT NULL,
                            RolAplicacion NVARCHAR(100) NULL,
                            UsuarioIdAplicacion NVARCHAR(100) NULL,
                            OrigenAplicacion NVARCHAR(100) NULL,
                            IdSolicitud NVARCHAR(128) NULL,
                            MetodoHttp VARCHAR(10) NULL,
                            RutaHttp NVARCHAR(1000) NULL,
                            Detalle NVARCHAR(2000) NULL,
                            MetadatosJson NVARCHAR(MAX) NULL,
                            HashEvento VARBINARY(32) NULL
                        )
                    END
                    """
                )
                cursor.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE object_id = OBJECT_ID(N'aud.EventoInformeDocente')
                          AND name = N'IX_AudEventoInforme_Fecha'
                    )
                    CREATE INDEX IX_AudEventoInforme_Fecha
                      ON aud.EventoInformeDocente(FechaEventoUtc DESC, EventoInformeId DESC)
                    """
                )
                cursor.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE object_id = OBJECT_ID(N'aud.EventoInformeDocente')
                          AND name = N'IX_AudEventoInforme_DocenteFecha'
                    )
                    CREATE INDEX IX_AudEventoInforme_DocenteFecha
                      ON aud.EventoInformeDocente(CodigoDocente, FechaEventoUtc DESC)
                      INCLUDE(Etapa, Estado, CodigoMateria, NombreArchivo, UsuarioAplicacion)
                    """
                )
                connection.commit()
            _schema_bootstrapped = True
        except (RuntimeError, pyodbc.Error) as exc:
            raise IntegrationHistoryUnavailableError(
                "No se pudo preparar el histórico central de integraciones."
            ) from exc


def _page_result(items: list[dict[str, Any]], total: int, page: int, page_size: int) -> dict[str, Any]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
    }


def list_database_events(
    *,
    page: int = 1,
    page_size: int = 25,
    operation: str = "",
    database: str = "",
    search: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    filters = ["Operacion IN ('INSERT', 'UPDATE', 'DELETE')"]
    parameters: list[Any] = []
    if operation:
        filters.append("Operacion = ?")
        parameters.append(operation)
    if database:
        filters.append("BaseDatos = ?")
        parameters.append(database)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            "(Objeto LIKE ? OR Esquema LIKE ? OR UsuarioAplicacion LIKE ? OR IdSolicitud LIKE ? OR RutaHttp LIKE ?)"
        )
        parameters.extend([pattern] * 5)
    if date_from:
        filters.append("FechaEventoUtc >= ?")
        parameters.append(date_from)
    if date_to:
        filters.append("FechaEventoUtc <= ?")
        parameters.append(date_to)
    where = " AND ".join(filters)
    offset = (page - 1) * page_size

    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT_BIG(1) FROM aud.EventoCambio WHERE " + where, *parameters)
            total = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT
                    EventoCambioId AS id,
                    FechaEventoUtc AS fecha_utc,
                    DATEADD(MINUTE, -300, FechaEventoUtc) AS fecha_ecuador,
                    BaseDatos AS base_datos,
                    Esquema AS esquema,
                    Objeto AS objeto,
                    Operacion AS operacion,
                    CantidadFilas AS cantidad_filas,
                    MuestraLimitada AS muestra_limitada,
                    UsuarioAplicacion AS usuario,
                    RolAplicacion AS rol,
                    OrigenAplicacion AS origen,
                    IdSolicitud AS solicitud,
                    MetodoHttp AS metodo,
                    RutaHttp AS ruta
                FROM aud.EventoCambio
                WHERE """ + where + """
                ORDER BY FechaEventoUtc DESC, EventoCambioId DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                *parameters,
                offset,
                page_size,
            )
            items = [_serialize_record(item) for item in _rows(cursor)]
            return _page_result(items, total, page, page_size)
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudo consultar aud.EventoCambio. Ejecute el instalador de auditoría total."
        ) from exc


def list_teacher_report_events(
    *,
    page: int = 1,
    page_size: int = 25,
    stage: str = "",
    status: str = "",
    search: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    ensure_integration_history_schema()
    filters = ["1 = 1"]
    parameters: list[Any] = []
    if stage:
        filters.append("Etapa = ?")
        parameters.append(stage)
    if status:
        filters.append("Estado = ?")
        parameters.append(status)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            "(NombreDocente LIKE ? OR CedulaDocente LIKE ? OR CodigoDocente LIKE ? OR CodigoMateria LIKE ? OR NombreMateria LIKE ? OR NombreArchivo LIKE ?)"
        )
        parameters.extend([pattern] * 6)
    if date_from:
        filters.append("FechaEventoUtc >= ?")
        parameters.append(date_from)
    if date_to:
        filters.append("FechaEventoUtc <= ?")
        parameters.append(date_to)
    where = " AND ".join(filters)
    offset = (page - 1) * page_size
    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT_BIG(1) FROM aud.EventoInformeDocente WHERE " + where, *parameters)
            total = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT
                    EventoInformeId AS id,
                    FechaEventoUtc AS fecha_utc,
                    DATEADD(MINUTE, -300, FechaEventoUtc) AS fecha_ecuador,
                    Etapa AS etapa,
                    Estado AS estado,
                    TipoDocumento AS tipo_documento,
                    CodigoDocente AS codigo_docente,
                    CedulaDocente AS cedula_docente,
                    NombreDocente AS nombre_docente,
                    CodigoMateria AS codigo_materia,
                    NombreMateria AS nombre_materia,
                    Paralelo AS paralelo,
                    NombreArchivo AS nombre_archivo,
                    RutaDocumento AS ruta_documento,
                    CantidadEstudiantes AS cantidad_estudiantes,
                    UsuarioAplicacion AS usuario,
                    RolAplicacion AS rol,
                    IdSolicitud AS solicitud,
                    Detalle AS detalle
                FROM aud.EventoInformeDocente
                WHERE """ + where + """
                ORDER BY FechaEventoUtc DESC, EventoInformeId DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                *parameters,
                offset,
                page_size,
            )
            items = [_serialize_record(item) for item in _rows(cursor)]
            return _page_result(items, total, page, page_size)
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudo consultar el histórico de informes docentes."
        ) from exc


def _compliance_document_type(filename: Any) -> str:
    normalized = str(filename or "").strip().casefold()
    if normalized.endswith(".xml") and "factura" in normalized:
        return "FACTURA_XML"
    if normalized.endswith(".pdf") and "ride" in normalized:
        return "RIDE"
    if "cumplimiento" in normalized or "informe" in normalized:
        return "INFORME"
    if "nota" in normalized:
        return "NOTAS"
    if "contrato" in normalized:
        return "CONTRATO"
    if normalized.endswith(".zip") or "paquete" in normalized:
        return "PAQUETE"
    return "OTRO"


def _json_list(value: Any) -> list[Any]:
    parsed = _safe_json_value(value)
    return parsed if isinstance(parsed, list) else []


def _flatten_teacher_compliance_events(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for event in events:
        event_id = int(event.get("event_id") or 0)
        periods = [str(item) for item in _json_list(event.get("periods_json")) if item not in (None, "")]
        metadata = _safe_json_value(event.get("metadata_json"))
        files = metadata.get("archivos") if isinstance(metadata, dict) else None
        base = {
            "event_id": event_id,
            "fecha_utc": _as_iso(event.get("fecha_utc")),
            "fecha_ecuador": _as_iso(event.get("fecha_ecuador")),
            "codigo_docente": event.get("codigo_docente"),
            "cedula_docente": event.get("cedula_docente"),
            "nombre_docente": event.get("nombre_docente"),
            "codigo_materia": event.get("codigo_materia"),
            "nombre_materia": event.get("nombre_materia"),
            "periodos": periods,
            "paralelo": event.get("paralelo"),
            "jornada": event.get("jornada"),
            "ruta_carpeta": event.get("folder_path"),
            "url_carpeta": event.get("folder_url"),
            "detalle": event.get("detalle"),
        }
        valid_files = [item for item in files or [] if isinstance(item, dict)]
        if valid_files:
            for index, item in enumerate(valid_files, start=1):
                filename = str(item.get("nombre") or "Documento firmado").strip()
                explicit_type = str(item.get("tipo_documento") or "").strip().upper()
                document_type = (
                    explicit_type
                    if explicit_type
                    in {
                        "INFORME",
                        "NOTAS",
                        "CONTRATO",
                        "PAQUETE",
                        "FACTURA_XML",
                        "RIDE",
                        "OTRO",
                    }
                    else _compliance_document_type(filename)
                )
                documents.append(
                    {
                        **base,
                        "id": f"{event_id}:{index}",
                        "documento_id": item.get("id"),
                        "nombre_documento": filename,
                        "tipo_documento": document_type,
                        "url_documento": item.get("url"),
                    }
                )
            continue

        # Los registros anteriores pueden conservar únicamente el enlace de la carpeta.
        folder_url = event.get("folder_url")
        if folder_url:
            documents.append(
                {
                    **base,
                    "id": f"{event_id}:folder",
                    "documento_id": None,
                    "nombre_documento": event.get("filename") or "Carpeta de documentos firmados",
                    "tipo_documento": "CARPETA",
                    "url_documento": folder_url,
                }
            )
    return documents


def list_teacher_compliance_documents(
    *,
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    document_type: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    ensure_integration_history_schema()
    filters = ["Etapa = 'ARCHIVADO'", "Estado = 'EXITOSO'"]
    parameters: list[Any] = []
    if date_from:
        filters.append("FechaEventoUtc >= ?")
        parameters.append(date_from)
    if date_to:
        filters.append("FechaEventoUtc <= ?")
        parameters.append(date_to)
    where = " AND ".join(filters)

    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    EventoInformeId AS event_id,
                    FechaEventoUtc AS fecha_utc,
                    DATEADD(MINUTE, -300, FechaEventoUtc) AS fecha_ecuador,
                    CodigoDocente AS codigo_docente,
                    CedulaDocente AS cedula_docente,
                    NombreDocente AS nombre_docente,
                    CodigoMateria AS codigo_materia,
                    NombreMateria AS nombre_materia,
                    PeriodosJson AS periods_json,
                    Paralelo AS paralelo,
                    Jornada AS jornada,
                    NombreArchivo AS filename,
                    RutaDocumento AS folder_path,
                    UrlDocumento AS folder_url,
                    Detalle AS detalle,
                    MetadatosJson AS metadata_json
                FROM aud.EventoInformeDocente
                WHERE """ + where + """
                ORDER BY FechaEventoUtc DESC, EventoInformeId DESC
                """,
                *parameters,
            )
            documents = _flatten_teacher_compliance_events(_rows(cursor))
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudieron consultar los documentos de cumplimiento docente."
        ) from exc

    normalized_search = search.strip().casefold()
    normalized_type = document_type.strip().upper()
    filtered: list[dict[str, Any]] = []
    for document in documents:
        if normalized_type and document.get("tipo_documento") != normalized_type:
            continue
        if normalized_search:
            searchable = " ".join(
                str(value or "")
                for value in (
                    document.get("nombre_docente"),
                    document.get("cedula_docente"),
                    document.get("codigo_docente"),
                    document.get("nombre_materia"),
                    document.get("codigo_materia"),
                    " ".join(document.get("periodos") or []),
                    document.get("nombre_documento"),
                    document.get("ruta_carpeta"),
                )
            ).casefold()
            if normalized_search not in searchable:
                continue
        filtered.append(document)

    total = len(filtered)
    offset = (page - 1) * page_size
    result = _page_result(filtered[offset : offset + page_size], total, page, page_size)
    result["summary"] = {
        "documents": total,
        "packages": len({item["event_id"] for item in filtered}),
        "teachers": len(
            {
                item.get("codigo_docente") or item.get("cedula_docente") or item.get("nombre_docente")
                for item in filtered
                if item.get("codigo_docente") or item.get("cedula_docente") or item.get("nombre_docente")
            }
        ),
    }
    return result


def _metadata_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_teacher_compliance_archive(event_id: int) -> dict[str, Any] | None:
    """Returns the archived package that owns a compliance-document folder."""
    ensure_integration_history_schema()
    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    EventoInformeId AS event_id,
                    CodigoDocente AS codigo_docente,
                    CedulaDocente AS cedula_docente,
                    NombreDocente AS nombre_docente,
                    CodigoMateria AS codigo_materia,
                    NombreMateria AS nombre_materia,
                    PeriodosJson AS periods_json,
                    RutaDocumento AS folder_path,
                    UrlDocumento AS folder_url,
                    MetadatosJson AS metadata_json
                FROM aud.EventoInformeDocente
                WHERE EventoInformeId = ?
                  AND Etapa = 'ARCHIVADO'
                  AND Estado = 'EXITOSO'
                """,
                event_id,
            )
            archive = _row(cursor)
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudo consultar el expediente del informe de cumplimiento."
        ) from exc

    if not archive:
        return None
    archive["periodos"] = [
        str(item)
        for item in _json_list(archive.pop("periods_json", None))
        if item not in (None, "")
    ]
    archive["metadatos"] = _metadata_object(archive.pop("metadata_json", None))
    return archive


def append_teacher_compliance_documents(
    *,
    event_id: int,
    documents: Iterable[dict[str, Any]],
    backup_id: str,
    uploaded_by: str,
) -> dict[str, Any] | None:
    """Atomically appends an XML/RIDE pair to an archived teacher package."""
    ensure_integration_history_schema()
    normalized_documents = [redact_sensitive_data(dict(item)) for item in documents]
    if len(normalized_documents) != 2:
        raise ValueError("El respaldo de factura debe contener exactamente un XML y un RIDE.")

    uploaded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT RutaDocumento, UrlDocumento, MetadatosJson
                FROM aud.EventoInformeDocente WITH (UPDLOCK, ROWLOCK)
                WHERE EventoInformeId = ?
                  AND Etapa = 'ARCHIVADO'
                  AND Estado = 'EXITOSO'
                """,
                event_id,
            )
            current = cursor.fetchone()
            if not current:
                return None

            metadata = _metadata_object(current.MetadatosJson)
            existing_files = metadata.get("archivos")
            files = [dict(item) for item in existing_files or [] if isinstance(item, dict)]
            files.extend(normalized_documents)
            metadata["archivos"] = files

            existing_backups = metadata.get("respaldos_factura")
            backups = [dict(item) for item in existing_backups or [] if isinstance(item, dict)]
            backups.append(
                {
                    "id": backup_id,
                    "fecha_carga_utc": uploaded_at,
                    "cargado_por": uploaded_by,
                    "documentos": [item.get("id") for item in normalized_documents],
                }
            )
            metadata["respaldos_factura"] = backups

            cursor.execute(
                """
                UPDATE aud.EventoInformeDocente
                   SET MetadatosJson = ?
                 WHERE EventoInformeId = ?
                """,
                _json_text(metadata),
                event_id,
            )
            connection.commit()
            return {
                "event_id": event_id,
                "folder_path": str(current.RutaDocumento or "").strip(),
                "folder_url": str(current.UrlDocumento or "").strip() or None,
                "backup_id": backup_id,
                "uploaded_at": uploaded_at,
                "documents": normalized_documents,
            }
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudo registrar el respaldo de factura en el expediente."
        ) from exc


def get_history_detail(kind: str, event_id: int) -> dict[str, Any] | None:
    table = "aud.EventoCambio" if kind == "database" else "aud.EventoInformeDocente"
    key = "EventoCambioId" if kind == "database" else "EventoInformeId"
    if kind == "teacher-report":
        ensure_integration_history_schema()
    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {table} WHERE {key} = ?", event_id)
            item = _row(cursor)
            return _serialize_record(item, include_json=True) if item else None
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError("No se pudo consultar el detalle histórico.") from exc


def integration_history_summary() -> dict[str, Any]:
    ensure_integration_history_schema()
    try:
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN Operacion = 'INSERT' THEN 1 ELSE 0 END) AS inserts,
                    SUM(CASE WHEN Operacion = 'UPDATE' THEN 1 ELSE 0 END) AS updates,
                    SUM(CASE WHEN Operacion = 'DELETE' THEN 1 ELSE 0 END) AS deletes,
                    COUNT_BIG(1) AS total
                FROM aud.EventoCambio
                WHERE Operacion IN ('INSERT', 'UPDATE', 'DELETE')
                  AND FechaEventoUtc >= DATEADD(DAY, -1, SYSUTCDATETIME())
                """
            )
            changes = _row(cursor) or {}
            cursor.execute(
                """
                SELECT
                    COUNT_BIG(1) AS total,
                    SUM(CASE WHEN Etapa = 'GENERADO' AND Estado = 'EXITOSO' THEN 1 ELSE 0 END) AS generated,
                    SUM(CASE WHEN Etapa = 'FIRMADO' AND Estado = 'EXITOSO' THEN 1 ELSE 0 END) AS signed,
                    SUM(CASE WHEN Etapa = 'ARCHIVADO' AND Estado = 'EXITOSO' THEN 1 ELSE 0 END) AS archived,
                    SUM(CASE WHEN Estado = 'ERROR' THEN 1 ELSE 0 END) AS errors
                FROM aud.EventoInformeDocente
                WHERE FechaEventoUtc >= DATEADD(DAY, -30, SYSUTCDATETIME())
                """
            )
            reports = _row(cursor) or {}
            cursor.execute(
                """
                SELECT DISTINCT BaseDatos
                FROM aud.EventoCambio
                WHERE Operacion IN ('INSERT', 'UPDATE', 'DELETE')
                ORDER BY BaseDatos
                """
            )
            databases = [str(row[0]) for row in cursor.fetchall()]
            cursor.execute(
                """
                IF OBJECT_ID(N'aud.CoberturaObjeto', N'U') IS NULL
                    SELECT
                        CAST(0 AS BIGINT) AS installed,
                        CAST(0 AS BIGINT) AS pending,
                        CAST(0 AS BIGINT) AS total;
                ELSE
                    SELECT
                        SUM(CASE WHEN Instalado = 1 THEN 1 ELSE 0 END) AS installed,
                        SUM(CASE WHEN Instalado = 0 THEN 1 ELSE 0 END) AS pending,
                        COUNT_BIG(1) AS total
                    FROM aud.CoberturaObjeto
                    WHERE TipoCaptura = 'DML';
                """
            )
            coverage = _row(cursor) or {}
            return {
                "changes_last_24_hours": {key: int(value or 0) for key, value in changes.items()},
                "teacher_reports_last_30_days": {key: int(value or 0) for key, value in reports.items()},
                "coverage": {key: int(value or 0) for key, value in coverage.items()},
                "databases": databases,
            }
    except (RuntimeError, pyodbc.Error) as exc:
        raise IntegrationHistoryUnavailableError(
            "No se pudo obtener el resumen del histórico de integraciones."
        ) from exc


def record_teacher_report_event(
    *,
    stage: str,
    status: str = "EXITOSO",
    document_type: str = "INFORME_CUMPLIMIENTO",
    teacher_code: Any = None,
    teacher_id: Any = None,
    teacher_name: Any = None,
    subject_code: Any = None,
    subject_name: Any = None,
    period_codes: Iterable[Any] | None = None,
    parallel: Any = None,
    schedule: Any = None,
    filename: Any = None,
    document_path: Any = None,
    document_url: Any = None,
    student_count: int | None = None,
    detail: Any = None,
    metadata: Any = None,
) -> bool:
    """Writes a document event without ever interrupting the business flow."""
    try:
        ensure_integration_history_schema()
        context = get_audit_context()
        periods_json = _json_text(list(period_codes or []))
        metadata_json = _json_text(metadata)
        digest_source = "|".join(
            str(value or "")
            for value in (
                stage,
                status,
                document_type,
                teacher_code,
                subject_code,
                periods_json,
                filename,
                context.user,
                context.request_id,
                datetime.utcnow().isoformat(),
            )
        )
        with get_integration_control_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO aud.EventoInformeDocente
                (
                    Etapa, Estado, TipoDocumento, CodigoDocente, CedulaDocente,
                    NombreDocente, CodigoMateria, NombreMateria, PeriodosJson,
                    Paralelo, Jornada, NombreArchivo, RutaDocumento, UrlDocumento,
                    CantidadEstudiantes, UsuarioAplicacion, RolAplicacion,
                    UsuarioIdAplicacion, OrigenAplicacion, IdSolicitud, MetodoHttp,
                    RutaHttp, Detalle, MetadatosJson, HashEvento
                )
                VALUES
                (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                str(stage or "ERROR").upper()[:20],
                str(status or "ERROR").upper()[:20],
                str(document_type or "INFORME_CUMPLIMIENTO")[:80],
                str(teacher_code or "")[:50] or None,
                str(teacher_id or "")[:30] or None,
                str(teacher_name or "")[:300] or None,
                str(subject_code or "")[:100] or None,
                str(subject_name or "")[:300] or None,
                periods_json,
                str(parallel or "")[:30] or None,
                str(schedule or "")[:100] or None,
                str(filename or "")[:500] or None,
                str(document_path or "")[:1500] or None,
                str(document_url or "")[:2000] or None,
                student_count,
                str(context.user or "SISTEMA")[:256],
                str(context.role or "SISTEMA")[:100],
                str(context.user_id or "")[:100] or None,
                str(context.origin or "API")[:100],
                str(context.request_id or "")[:128] or None,
                str(context.method or "")[:10] or None,
                str(context.path or "")[:1000] or None,
                str(detail or "")[:2000] or None,
                metadata_json,
                sha256(digest_source.encode("utf-8")).digest(),
            )
            connection.commit()
        return True
    except Exception:
        logger.exception("No se pudo registrar el evento histórico del informe docente.")
        return False
