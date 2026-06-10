from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.db import get_connection


DEFAULT_CEDULAS = """
0201953049
1710693217
1719387522
1724580483
1725671059
1755332192
0104012448
0105667083
0706780269
0706920378
0707275442
0707392973
0804125128
0804191930
0950688689
0958991754
1317323887
1600862484
1720377934
1722362934
1725925091
1729047173
1753023975
0107762981
0504641309
0804041911
0925089518
1003249768
1720886843
1725611287
1727729467
1720967544
0802830190
0941831901
1105073397
1105193021
1150377461
1250236898
1307799351
1550065534
1600853111
1716542889
1718958620
1720791811
1724702731
1725301111
1726324013
1751050186
1752255503
1803317211
1805247788
0106278062
0245000259
0931158646
1720722279
1722789557
1726494949
2200138556
0105432181
1150566766
1314918648
1450172018
1752280139
1004539829
1351033939
1724148216
1725105850
1750999854
1751622034
1753954229
1803827896
"""


CSV_COLUMNS = [
    "orden",
    "cedula_buscada",
    "estado",
    "codigo_estud",
    "cedula_registrada",
    "estudiante",
    "telefono",
    "movil",
    "correo_personal",
    "correo_datos_estud",
    "correo_personal_correos_intec",
    "correo_intec",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_cedulas(raw_text: str) -> list[str]:
    cedulas: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[\s,;]+", raw_text):
        cedula = re.sub(r"\D+", "", token.strip())
        if not cedula or cedula in seen:
            continue
        seen.add(cedula)
        cedulas.append(cedula)
    return cedulas


def read_cedulas(input_path: Path | None) -> list[str]:
    if input_path:
        return parse_cedulas(input_path.read_text(encoding="utf-8-sig"))
    return parse_cedulas(DEFAULT_CEDULAS)


def output_path(custom_output: Path | None) -> Path:
    if custom_output:
        custom_output.parent.mkdir(parents=True, exist_ok=True)
        return custom_output
    exports_dir = BACKEND_ROOT / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return exports_dir / f"contactos_estudiantes_{timestamp}.csv"


def fetch_contacts(cedulas: list[str]) -> list[dict[str, Any]]:
    if not cedulas:
        return []

    values_sql = ", ".join("(?, ?)" for _ in cedulas)
    params: list[Any] = []
    for index, cedula in enumerate(cedulas, start=1):
        params.extend([cedula, index])

    sql = f"""
        WITH requested(cedula, orden) AS (
            SELECT *
            FROM (VALUES {values_sql}) AS data(cedula, orden)
        )
        SELECT
            r.orden,
            r.cedula AS cedula_buscada,
            CASE WHEN d.Cedula_Est IS NULL THEN 'NO_ENCONTRADO' ELSE 'OK' END AS estado,
            TRY_CONVERT(varchar(50), d.codigo_estud) AS codigo_estud,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.Cedula_Est))) AS cedula_registrada,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.Apellidos_nombre))) AS estudiante,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.telefono))) AS telefono,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.movil))) AS movil,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correo))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), cei.CorreoPersonal))), N'')
            ) AS correo_personal,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correo))) AS correo_datos_estud,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), cei.CorreoPersonal))) AS correo_personal_correos_intec,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correointec))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), cei.CorreoIntec))), N'')
            ) AS correo_intec
        FROM requested r
        LEFT JOIN dbo.DATOS_ESTUD d
          ON LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.Cedula_Est))) = r.cedula
        LEFT JOIN dbo.CorreosEstudIntec cei
          ON TRY_CONVERT(decimal(18, 0), cei.codestud) = TRY_CONVERT(decimal(18, 0), d.codigo_estud)
        ORDER BY r.orden
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append({column: clean_text(getattr(row, column, "")) for column in CSV_COLUMNS})
    return results


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta telefonos y correos personales de estudiantes por cedula.")
    parser.add_argument("--input", type=Path, help="Archivo TXT/CSV con cedulas separadas por saltos, comas o punto y coma.")
    parser.add_argument("--output", type=Path, help="Ruta del CSV de salida. Si no se indica, se crea en backend/exports.")
    args = parser.parse_args()

    cedulas = read_cedulas(args.input)
    if not cedulas:
        raise SystemExit("No hay cedulas para consultar.")

    rows = fetch_contacts(cedulas)
    destination = output_path(args.output)
    write_csv(rows, destination)

    found = sum(1 for row in rows if row["estado"] == "OK")
    missing = sum(1 for row in rows if row["estado"] != "OK")
    print(f"Archivo generado: {destination}")
    print(f"Cedulas consultadas: {len(cedulas)}")
    print(f"Encontrados: {found}")
    print(f"No encontrados: {missing}")


if __name__ == "__main__":
    main()
