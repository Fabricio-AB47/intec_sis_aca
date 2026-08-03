from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.routers.document_expedients import _context_payload
from app.services.db import (
    get_connection,
    get_graph_database_connection,
    get_practices_connection,
)


EXPECTED_OBJECTS = (
    "doc.ExpedienteGraph",
    "doc.DocumentoGraph",
    "doc.DocumentoGraphVersion",
    "doc.SesionCargaGraph",
    "rpt.vw_ExpedientesDocumentalesGraph",
)


def _verify_graph_schema() -> None:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        missing = [
            name
            for name in EXPECTED_OBJECTS
            if cursor.execute("SELECT OBJECT_ID(?)", name).fetchone()[0] is None
        ]
        active_types = int(
            cursor.execute(
                "SELECT COUNT(*) FROM cat.TipoExpedienteGraph WHERE Activo = 1"
            ).fetchone()[0]
        )
    if missing:
        raise RuntimeError(f"Faltan objetos Graph: {', '.join(missing)}")
    if active_types != 4:
        raise RuntimeError(f"Se esperaban 4 tipos de expediente activos y existen {active_types}.")
    print(f"Graph documental: {len(EXPECTED_OBJECTS)} objetos y {active_types} tipos activos.")


def _sample_student_code() -> int:
    with get_practices_connection() as conn:
        row = conn.cursor().execute(
            """
            SELECT TOP (1) TRY_CONVERT(BIGINT, CodigoEstud)
            FROM exp.Expediente
            WHERE Activo = 1 AND TRY_CONVERT(BIGINT, CodigoEstud) IS NOT NULL
            ORDER BY ExpedienteId DESC
            """
        ).fetchone()
    if row:
        return int(row[0])
    with get_connection() as conn:
        row = conn.cursor().execute(
            """
            SELECT TOP (1) TRY_CONVERT(BIGINT, codigo_estud)
            FROM dbo.DATOS_ESTUD
            WHERE TRY_CONVERT(BIGINT, codigo_estud) IS NOT NULL
              AND UPPER(LTRIM(RTRIM(CONVERT(VARCHAR(10), Estado)))) = 'A'
            ORDER BY TRY_CONVERT(BIGINT, codigo_estud)
            """
        ).fetchone()
    if not row:
        raise RuntimeError("No existe un estudiante activo para la prueba de lectura.")
    return int(row[0])


def _student_profile(student_code: int) -> dict[str, object]:
    with get_connection() as conn:
        row = conn.cursor().execute(
            """
            SELECT TOP (1)
                TRY_CONVERT(BIGINT, codigo_estud),
                REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(VARCHAR(30), Cedula_Est))), '-', ''), ' ', ''),
                LTRIM(RTRIM(CONVERT(NVARCHAR(500), Apellidos_nombre))),
                COALESCE(correointec, correo), Estado
            FROM dbo.DATOS_ESTUD
            WHERE TRY_CONVERT(BIGINT, codigo_estud) = ?
            """,
            student_code,
        ).fetchone()
    if not row:
        raise RuntimeError(f"El estudiante {student_code} no existe en INTECBDD.")
    return {
        "code": int(row[0]),
        "identification": str(row[1] or "").strip(),
        "name": str(row[2] or "").strip(),
        "email": str(row[3] or "").strip(),
        "career_code": "",
        "career": "",
        "period_code": "",
        "status": str(row[4] or "").strip(),
    }


def main() -> None:
    _verify_graph_schema()
    profile = _student_profile(_sample_student_code())
    context = _context_payload(profile, "ADMINISTRADOR")
    modules = [
        (
            item["module_code"],
            bool(item["origin_id"]),
            len(item["document_types"]),
            item["upload_enabled"],
        )
        for item in context["expedients"]
    ]
    print(f"Estudiante de prueba: {profile['code']} / {profile['identification']}")
    print(f"Resolucion de modulos: {modules}")
    print(
        "Contexto documental valido: "
        f"{context['total_expedients']} expediente(s), "
        f"{context['total_documents']} documento(s)."
    )


if __name__ == "__main__":
    main()
