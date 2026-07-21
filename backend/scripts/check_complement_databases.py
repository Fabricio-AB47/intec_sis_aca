import argparse
from collections.abc import Callable
from pathlib import Path
import sys

import pyodbc

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.db import (
    get_connection,
    get_evaluation_connection,
    get_expedient_connection,
    get_finance_connection,
    get_graph_database_connection,
    get_integration_control_connection,
)


ConnectionFactory = Callable[[], pyodbc.Connection]

EXPECTED_OBJECTS: dict[str, tuple[ConnectionFactory, tuple[tuple[str, str], ...]]] = {
    "expediente": (
        get_expedient_connection,
        (
            ("exp.ExpedienteEstudiantil", "U"),
            ("doc.DocumentoExpediente", "U"),
            ("cron.CronogramaAcademico", "U"),
            ("integ.EjecucionSincronizacion", "U"),
            ("integ.ErrorSincronizacion", "U"),
            ("rpt.vw_EstadoDocumentalIntegracion", "V"),
            ("rpt.vw_ExpedienteIdentidadIntegracion", "V"),
            ("etl.sp_SincronizarModuloCompleto", "P"),
        ),
    ),
    "finanzas": (
        get_finance_connection,
        (
            ("fin.CuentaEstudiante", "U"),
            ("fin.ObligacionEstudiante", "U"),
            ("pag.PagoEstudiante", "U"),
            ("fac.Factura", "U"),
            ("integ.EjecucionSincronizacion", "U"),
            ("integ.ErrorSincronizacion", "U"),
            ("rpt.vw_EstadoFinancieroIntegracion", "V"),
            ("fin.sp_SincronizarProcesoFinancieroCompleto", "P"),
        ),
    ),
    "graph": (
        get_graph_database_connection,
        (
            ("graph.OperacionGraph", "U"),
            ("identity.UsuarioOffice365", "U"),
            ("teams.EquipoClase", "U"),
            ("mail.CorreoSalida", "U"),
            ("rpt.vw_EstadoGraphIntegracion", "V"),
            ("graph.sp_RenovarLeaseOperacion", "P"),
            ("graph.sp_RecuperarOperacionesVencidas", "P"),
        ),
    ),
    "control": (
        get_integration_control_connection,
        (
            ("sync.Ejecucion", "U"),
            ("snap.EstadoAcademico", "U"),
            ("snap.EstadoDocumental", "U"),
            ("snap.EstadoFinanciero", "U"),
            ("snap.EstadoPracticas", "U"),
            ("snap.EstadoIdioma", "U"),
            ("rpt.vw_EstadoIntegralEstudiante", "V"),
            ("sync.sp_EjecutarSincronizacionCompleta", "P"),
        ),
    ),
}


SOURCE_TABLES = ("DATOS_ESTUD", "CARRERAXESTUD", "CARRERAS", "PERIODO")


def _source_counts(factory: ConnectionFactory, database_prefix: str = "") -> dict[str, int]:
    with factory() as connection:
        cursor = connection.cursor()
        return {
            table: int(cursor.execute(f"SELECT COUNT_BIG(1) FROM {database_prefix}dbo.{table}").fetchval())
            for table in SOURCE_TABLES
        }


def _documents(factory: ConnectionFactory, query: str) -> set[str]:
    with factory() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        return {str(row[0]).strip() for row in cursor.fetchall() if str(row[0] or "").strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica las bases complementarias de INTECBDD.")
    parser.add_argument(
        "--strict-source-parity",
        action="store_true",
        help="Falla si INTECBDD principal y la copia del servidor complementario difieren.",
    )
    args = parser.parse_args()
    failed = False
    for label, (factory, expected) in EXPECTED_OBJECTS.items():
        try:
            with factory() as connection:
                cursor = connection.cursor()
                database = cursor.execute("SELECT DB_NAME()").fetchval()
                missing = [
                    f"{name}:{object_type}"
                    for name, object_type in expected
                    if not cursor.execute("SELECT OBJECT_ID(?, ?)", name, object_type).fetchval()
                ]
                status = "OK" if not missing else "INCOMPLETA"
                print(f"{label}: {status} ({database})")
                for item in missing:
                    print(f"  falta {item}")
                failed = failed or bool(missing)
        except Exception as exc:
            failed = True
            print(f"{label}: ERROR {type(exc).__name__}: {exc}")

    primary_counts = _source_counts(get_connection)
    print(f"fuente_academica_principal: OK (INTECBDD, {primary_counts['DATOS_ESTUD']} estudiantes)")
    primary_documents = _documents(
        get_connection,
        "SELECT DISTINCT REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), Cedula_Est))), '-', ''), ' ', '') FROM dbo.DATOS_ESTUD WHERE NULLIF(REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), Cedula_Est))), '-', ''), ' ', ''), '') IS NOT NULL",
    )
    reference_sources = {
        "expediente": (
            get_expedient_connection,
            "SELECT DISTINCT NumeroIdentificacion FROM core.Persona",
        ),
        "finanzas": (
            get_finance_connection,
            "SELECT DISTINCT NumeroIdentificacion FROM core.Estudiante",
        ),
        "graph": (
            get_graph_database_connection,
            "SELECT DISTINCT NumeroIdentificacion FROM core.PersonaGraphRef WHERE TipoPersonaCodigo = 'ESTUDIANTE'",
        ),
    }
    for label, (factory, query) in reference_sources.items():
        target_documents = _documents(factory, query)
        missing = primary_documents - target_documents
        status = "OK" if not missing else "INCOMPLETA"
        print(f"referencias_{label}: {status} ({len(primary_documents) - len(missing)}/{len(primary_documents)})")
        failed = failed or bool(missing)

    complement_counts = _source_counts(get_evaluation_connection, "INTECBDD.")
    mismatches = {
        table: (primary_counts[table], complement_counts[table])
        for table in SOURCE_TABLES
        if primary_counts[table] != complement_counts[table]
    }
    if mismatches:
        print("replica_academica_legacy: OMITIDA (la integracion usa INTECBDD principal)")
        if args.strict_source_parity:
            for table, (primary, complement) in mismatches.items():
                print(f"  {table}: principal={primary}, replica={complement}")
        failed = failed or args.strict_source_parity
    else:
        print("replica_academica_legacy: OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
