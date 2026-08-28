import unittest
from unittest.mock import Mock, patch

from app.routers import sisacademico_admin


class RecordingCursor:
    columns = [
        "codigo_doc",
        "cod_Anio_Basica",
        "codigo_materia",
        "codigo_periodo",
        "Paralelo",
        "Cod_Jornada",
        "estadoMoodleDoc",
        "docente_nombre",
        "docente_cedula",
        "carrera_nombre",
        "materia_nombre",
        "materia_codigo_institucional",
        "periodo_nombre",
        "jornada_nombre",
    ]

    def __init__(self) -> None:
        self.description = [(column,) for column in self.columns]
        self.statement = ""
        self.params: list[object] = []

    def execute(self, statement: str, params: list[object]) -> "RecordingCursor":
        self.statement = statement
        self.params = params
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return [
            (
                40,
                4,
                124,
                1060,
                "PB2",
                2,
                1,
                "BORJA HERNANDEZ FABRICIO ALEXANDER",
                "1724036536",
                "Desarrollo de Software",
                "Inteligencia Artificial",
                "VGA-ES-2023-90",
                "C1-2026-PCFF ABRIL 2026 - AGOSTO 2026",
                "Nocturno",
            )
        ]


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> RecordingCursor:
        return self._cursor


class TeacherAssignmentListTests(unittest.TestCase):
    def test_list_uses_descriptive_relations_and_preserves_record_key(self) -> None:
        cursor = RecordingCursor()
        section = sisacademico_admin.SECTIONS["docente_materias"]

        with patch.object(
            sisacademico_admin,
            "get_connection",
            return_value=RecordingConnection(cursor),
        ):
            result = sisacademico_admin._list_docente_materias_records(section, "borja")

        self.assertIn("LEFT JOIN dbo.DATOSDOCENTE", cursor.statement)
        self.assertIn("OUTER APPLY", cursor.statement)
        self.assertIn("d.apellidos_nombre", cursor.statement)
        self.assertTrue(cursor.params)
        self.assertTrue(all(param == "%borja%" for param in cursor.params))
        self.assertEqual(result["total"], 1)
        row = result["rows"][0]
        self.assertEqual(row["docente_nombre"], "BORJA HERNANDEZ FABRICIO ALEXANDER")
        self.assertEqual(row["materia_nombre"], "Inteligencia Artificial")
        self.assertEqual(row["periodo_nombre"], "C1-2026-PCFF ABRIL 2026 - AGOSTO 2026")
        self.assertEqual(row["codigo_doc"], 40)
        self.assertTrue(row["_record_key"])

    def test_public_list_route_dispatches_to_enriched_teacher_assignments(self) -> None:
        expected = {"rows": [{"docente_nombre": "DOCENTE"}], "total": 1}
        with patch.object(
            sisacademico_admin,
            "_list_docente_materias_records",
            return_value=expected,
        ) as specialized_list:
            result = sisacademico_admin.list_records(
                "docente_materias",
                query="docente",
                limit=None,
                periodo=None,
                _=Mock(),
            )

        self.assertEqual(result, expected)
        specialized_list.assert_called_once_with(
            sisacademico_admin.SECTIONS["docente_materias"],
            "docente",
        )


if __name__ == "__main__":
    unittest.main()
