import unittest
from types import SimpleNamespace

from app.routers.titulacion import _bulk_academic_summaries


class BulkSummaryCursor:
    columns = [
        "CodigoEstud",
        "CodAnioBasica",
        "MateriasPensum",
        "MateriasCursadas",
        "MateriasAprobadas",
        "PromedioAprobadas",
        "PromedioGeneral",
    ]

    def __init__(self) -> None:
        self.description = [(column,) for column in self.columns]
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, *params: object) -> "BulkSummaryCursor":
        self.executions.append((statement, params))
        return self

    def fetchall(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                CodigoEstud=10,
                CodAnioBasica=7,
                MateriasPensum=24,
                MateriasCursadas=24,
                MateriasAprobadas=24,
                PromedioAprobadas=8.2350000001,
                PromedioGeneral=8.1,
            ),
            SimpleNamespace(
                CodigoEstud=20,
                CodAnioBasica=7,
                MateriasPensum=24,
                MateriasCursadas=3,
                MateriasAprobadas=0,
                PromedioAprobadas=None,
                PromedioGeneral=5.5,
            ),
        ]


class TitulacionBulkLoadingTests(unittest.TestCase):
    def test_academic_summaries_are_calculated_in_one_set_based_query(self) -> None:
        cursor = BulkSummaryCursor()
        rows = [
            {"CodigoEstud": 10, "CodAnioBasica": "7"},
            {"CodigoEstud": 20, "CodAnioBasica": "7"},
            {"CodigoEstud": 10, "CodAnioBasica": "7"},
        ]

        summaries = _bulk_academic_summaries(cursor, rows)  # type: ignore[arg-type]

        self.assertEqual(len(cursor.executions), 1)
        statement, params = cursor.executions[0]
        self.assertIn("FROM (VALUES (?, ?),(?, ?))", statement)
        self.assertIn("INNER JOIN dbo.CARRERAXESTUD", statement)
        self.assertIn("cxe.codigo_estud = candidates.CodigoEstud", statement)
        self.assertIn("cxe.cod_anio_Basica = candidates.CodAnioBasica", statement)
        self.assertEqual(params, (10, 7, 20, 7, 7.0))
        self.assertEqual(summaries[(10, 7)]["materias_aprobadas"], 24)
        self.assertEqual(summaries[(10, 7)]["promedio_asignaturas"], 8.24)
        self.assertTrue(summaries[(10, 7)]["malla_finalizada"])
        self.assertEqual(summaries[(20, 7)]["materias_cursadas"], 3)
        self.assertEqual(summaries[(20, 7)]["promedio_asignaturas"], 5.5)
        self.assertFalse(summaries[(20, 7)]["malla_finalizada"])

    def test_empty_candidate_list_does_not_query_database(self) -> None:
        cursor = BulkSummaryCursor()

        summaries = _bulk_academic_summaries(cursor, [])  # type: ignore[arg-type]

        self.assertEqual(summaries, {})
        self.assertEqual(cursor.executions, [])

    def test_large_candidate_sets_are_split_below_the_sql_parameter_limit(self) -> None:
        cursor = BulkSummaryCursor()
        rows = [
            {"CodigoEstud": student, "CodAnioBasica": 7}
            for student in range(1, 502)
        ]

        _bulk_academic_summaries(cursor, rows)  # type: ignore[arg-type]

        self.assertEqual(len(cursor.executions), 2)
        self.assertEqual(len(cursor.executions[0][1]), 1001)
        self.assertEqual(len(cursor.executions[1][1]), 3)


if __name__ == "__main__":
    unittest.main()
