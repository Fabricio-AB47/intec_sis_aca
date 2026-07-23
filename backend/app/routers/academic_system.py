from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Annotated, Any, Callable

import pyodbc
from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.security import SessionUser, require_roles
from app.services.db import (
    get_connection,
    get_evaluation_connection,
    get_expedient_connection,
    get_finance_connection,
    get_graph_database_connection,
    get_integration_control_connection,
    get_practices_connection,
    get_teams_connection,
    get_titulation_connection,
)

router = APIRouter(prefix="/api/academic-system", tags=["academic-system"])
_ACCESS = require_roles(
    "ADMINISTRADOR",
    "FINANCIERO",
    "BIENESTAR",
    "ACADEMICO",
    "ADMISIONES",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "SECRETARIA",
)


def _check_database(
    *,
    key: str,
    configured_name: str | None,
    role: str,
    domains: list[str],
    relation: str,
    connection_factory: Callable[[], pyodbc.Connection],
    primary: bool = False,
) -> dict[str, Any]:
    base = {
        "key": key,
        "name": configured_name or "No configurada",
        "role": role,
        "domains": domains,
        "relation": relation,
        "primary": primary,
        "kind": "database",
        "configured": bool(configured_name),
        "available": False,
        "status": "NOT_CONFIGURED" if not configured_name else "OFFLINE",
    }
    if not configured_name:
        return base

    connection: pyodbc.Connection | None = None
    try:
        connection = connection_factory()
        row = connection.cursor().execute(
            "SELECT DB_NAME() AS DatabaseName, DATABASEPROPERTYEX(DB_NAME(), 'Status') AS DatabaseStatus"
        ).fetchone()
        database_status = str(row.DatabaseStatus or "").upper() if row else ""
        base["name"] = str(row.DatabaseName or configured_name) if row else configured_name
        base["available"] = database_status == "ONLINE"
        base["status"] = "ONLINE" if base["available"] else "OFFLINE"
    except (pyodbc.Error, RuntimeError, AttributeError, ValueError):
        base["status"] = "OFFLINE"
    finally:
        if connection is not None:
            connection.close()
    return base


def _check_read_contract() -> dict[str, Any]:
    checks = [
        (get_connection, "dbo.vw_EstadoAcademicoIntegracion"),
        (get_expedient_connection, "rpt.vw_ExpedienteIdentidadIntegracion"),
        (get_practices_connection, "integ.vw_EstadoPracticasIntegracion"),
    ]
    available_objects = 0
    for connection_factory, object_name in checks:
        connection: pyodbc.Connection | None = None
        try:
            connection = connection_factory()
            row = connection.cursor().execute(
                "SELECT OBJECT_ID(?, 'V') AS ObjectId", object_name
            ).fetchone()
            if row and row.ObjectId is not None:
                available_objects += 1
        except (pyodbc.Error, RuntimeError, AttributeError, ValueError):
            pass
        finally:
            if connection is not None:
                connection.close()

    if available_objects == len(checks):
        status = "ONLINE"
    elif available_objects > 0:
        status = "PARTIAL"
    else:
        status = "OFFLINE"
    return {
        "key": "contracts",
        "name": "Contratos de lectura V3",
        "role": "Vistas estables para integración académica",
        "domains": ["records", "practices", "graduation", "analytics"],
        "relation": f"{available_objects} de {len(checks)} vistas instaladas",
        "primary": False,
        "kind": "contract",
        "configured": True,
        "available": status == "ONLINE",
        "status": status,
    }


@router.get("/integration-status")
def integration_status(
    _: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    settings = get_settings()
    definitions = [
        {
            "key": "academic",
            "configured_name": settings.db_name,
            "role": "Fuente académica maestra",
            "domains": ["admission", "enrollment", "records", "faculty", "analytics"],
            "relation": "Cédula y CodigoEstud",
            "connection_factory": get_connection,
            "primary": True,
        },
        {
            "key": "expedient",
            "configured_name": settings.expedient_db_name,
            "role": "Expediente, documentos y trazabilidad",
            "domains": ["admission", "records", "graduation"],
            "relation": "Cédula y CodigoEstud",
            "connection_factory": get_expedient_connection,
        },
        {
            "key": "finance",
            "configured_name": settings.finance_db_name,
            "role": "Becas, obligaciones, pagos y cartera",
            "domains": ["admission", "finance", "enrollment", "analytics"],
            "relation": "Cédula, CodigoEstud y matrícula",
            "connection_factory": get_finance_connection,
        },
        {
            "key": "graph",
            "configured_name": settings.graph_db_name,
            "role": "Microsoft 365, Teams y auditoría Graph",
            "domains": ["faculty", "records", "analytics"],
            "relation": "Correo institucional y objeto Graph",
            "connection_factory": get_graph_database_connection,
        },
        {
            "key": "evaluation",
            "configured_name": settings.eval_db_name,
            "role": "Evaluación institucional y docente 360",
            "domains": ["faculty", "analytics"],
            "relation": "Cédula, CodigoDoc y periodo",
            "connection_factory": get_evaluation_connection,
        },
        {
            "key": "teams",
            "configured_name": settings.teams_db_name,
            "role": "Aulas virtuales y operación educativa continua",
            "domains": ["records", "faculty", "analytics"],
            "relation": "Correo institucional, curso y periodo",
            "connection_factory": get_teams_connection,
        },
        {
            "key": "control",
            "configured_name": settings.integration_control_db_name,
            "role": "Lotes, conciliación, errores y reintentos",
            "domains": ["admission", "finance", "enrollment", "records", "faculty", "practices", "graduation", "analytics"],
            "relation": "Proceso, lote y clave de origen",
            "connection_factory": get_integration_control_connection,
        },
        {
            "key": "practices",
            "configured_name": settings.practices_db_name,
            "role": "Prácticas preprofesionales y vinculación",
            "domains": ["practices", "graduation"],
            "relation": "Cédula, CodigoEstud y expediente",
            "connection_factory": get_practices_connection,
        },
        {
            "key": "titulation",
            "configured_name": settings.titulation_db_name,
            "role": "Egreso, modalidad, actas y títulos",
            "domains": ["graduation", "analytics"],
            "relation": "Cédula, CodigoEstud y expediente",
            "connection_factory": get_titulation_connection,
        },
    ]

    databases: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(definitions)) as executor:
        futures = {executor.submit(_check_database, **definition): definition["key"] for definition in definitions}
        completed = {}
        for future in as_completed(futures):
            result = future.result()
            completed[result["key"]] = result
    databases = [completed[definition["key"]] for definition in definitions]
    databases.append(_check_read_contract())

    domain_keys = ["admission", "finance", "enrollment", "records", "faculty", "practices", "graduation", "analytics"]
    domains = []
    for domain_key in domain_keys:
        sources = [database for database in databases if domain_key in database["domains"]]
        available = sum(1 for source in sources if source["available"])
        if sources and available == len(sources):
            status = "READY"
        elif available > 0:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"
        domains.append(
            {
                "key": domain_key,
                "status": status,
                "source_keys": [source["key"] for source in sources],
                "available_sources": available,
                "total_sources": len(sources),
            }
        )

    available_count = sum(1 for database in databases if database["available"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_database": settings.db_name,
        "databases": databases,
        "domains": domains,
        "summary": {
            "total": len(databases),
            "configured": sum(1 for database in databases if database["configured"]),
            "available": available_count,
            "degraded": len(databases) - available_count,
        },
    }
