"""Read-only operational queue over existing academic movement requests."""

from contextlib import closing
from datetime import datetime, timezone
import logging
from typing import Any, Literal

import pyodbc
from fastapi import HTTPException

from app.services.db import get_integration_control_connection

logger = logging.getLogger(__name__)

_SOURCES = {
    "career": ("sol.SolicitudCambioCarrera", "PeriodoDestinoNombre"),
    "modality": ("sol.SolicitudCambioModalidad", "PeriodoHomologacionNombre"),
}


def read_pending_requests(
    source: Literal["career", "modality"], *, query: str = "", page: int = 1,
    page_size: int = 10, state: Literal["TODOS", "PENDIENTE", "APROBADA"] = "TODOS",
) -> dict[str, Any]:
    if source not in _SOURCES or state not in {"TODOS", "PENDIENTE", "APROBADA"}:
        raise HTTPException(422, "Filtro de pendientes no permitido.")
    if page < 1 or not 1 <= page_size <= 100 or len(query) > 120:
        raise HTTPException(422, "Paginaci\u00f3n o b\u00fasqueda no v\u00e1lida.")
    table, period_column = _SOURCES[source]
    # Identifiers come only from the allowlist; user text is a literal LIKE parameter.
    search = query.strip().replace("^", "^^").replace("%", "^%")
    search = search.replace("_", "^_").replace("[", "^[")
    search = f"%{search}%"
    where = f"""
        Estado IN (N'PENDIENTE', N'APROBADA')
        AND (? = N'TODOS' OR Estado = ?)
        AND (Estudiante LIKE ? ESCAPE '^' OR Cedula LIKE ? ESCAPE '^'
            OR CONVERT(nvarchar(30), IdSolicitud) LIKE ? ESCAPE '^'
            OR CarreraDestinoNombre LIKE ? ESCAPE '^'
            OR {period_column} LIKE ? ESCAPE '^')
    """
    params = (state, state, search, search, search, search, search)
    try:
        with closing(get_integration_control_connection()) as connection:
            connection.timeout = 15
            cursor = connection.cursor()
            cursor.execute(f"SELECT COUNT_BIG(*) FROM {table} WHERE {where}", *params)
            total = int(cursor.fetchone()[0])
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            cursor.execute(
                f"""
                SELECT IdSolicitud AS id, CodigoEstud AS student_code,
                    Cedula AS identification, Estudiante AS student,
                    CarreraDestinoNombre AS career, {period_column} AS period,
                    Estado AS state, FechaCreacion AS created_at
                FROM {table} WHERE {where}
                ORDER BY FechaCreacion ASC, IdSolicitud ASC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                *params, (page - 1) * page_size, page_size,
            )
            columns = [column[0] for column in cursor.description]
            items = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for item in items:
            created = item["created_at"]
            if isinstance(created, datetime):
                # The existing request tables persist SYSUTCDATETIME().
                item["created_at"] = created.replace(tzinfo=timezone.utc).isoformat()
            for field in ("student", "identification", "career", "period", "state"):
                item[field] = str(item[field] or "").strip()
        return {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages, "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except (pyodbc.Error, RuntimeError) as exc:
        logger.warning("Academic pending source unavailable: %s", source, exc_info=True)
        raise HTTPException(
            503, "No fue posible consultar los pendientes. Verifique la base de solicitudes y sus permisos.",
        ) from exc
