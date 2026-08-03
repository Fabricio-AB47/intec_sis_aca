from __future__ import annotations

from pathlib import Path
import re
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.db import get_graph_database_connection


MIGRATION = BACKEND_ROOT / "sql" / "2026_07_30_graph_expedientes_documentales.sql"
EXPECTED_OBJECTS = (
    ("doc.ExpedienteGraph", "U"),
    ("doc.DocumentoGraph", "U"),
    ("doc.DocumentoGraphVersion", "U"),
    ("doc.SesionCargaGraph", "U"),
    ("rpt.vw_ExpedientesDocumentalesGraph", "V"),
)


def main() -> int:
    sql = MIGRATION.read_text(encoding="utf-8-sig")
    batches = [batch.strip() for batch in re.split(r"(?im)^\s*GO\s*;?\s*$", sql) if batch.strip()]

    with get_graph_database_connection() as connection:
        cursor = connection.cursor()
        database = str(cursor.execute("SELECT DB_NAME()").fetchval())
        if database.upper() != "INTEC_GRAPH_INTEGRACION":
            raise RuntimeError(f"Conexion Graph inesperada: {database}")

        try:
            for index, batch in enumerate(batches, start=1):
                cursor.execute(batch)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise RuntimeError(f"Fallo el lote {index} de {len(batches)}: {exc}") from exc

        missing = [
            name
            for name, object_type in EXPECTED_OBJECTS
            if not cursor.execute("SELECT OBJECT_ID(?, ?)", name, object_type).fetchval()
        ]
        if missing:
            raise RuntimeError(f"La migracion termino sin crear: {', '.join(missing)}")

        catalog_count = int(
            cursor.execute(
                "SELECT COUNT_BIG(1) FROM cat.TipoExpedienteGraph WHERE Activo = 1"
            ).fetchval()
        )

    print(
        f"Migracion documental Graph aplicada en {database}: "
        f"{len(EXPECTED_OBJECTS)} objetos y {catalog_count} tipos de expediente activos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
