import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.routers import sisacademico_admin


class RecordingCursor:
    def __init__(self, total: int = 63) -> None:
        self.total = total
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, statement: str, params: list[object]) -> "RecordingCursor":
        self.calls.append((statement, list(params)))
        return self

    def fetchval(self) -> int:
        return self.total

    def fetchall(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                codigo_estud="42",
                Cedula_Est="1724036536",
                Apellidos_nombre="ESTUDIANTE DE PRUEBA",
                codigo_periodo="1060",
                Estado="A",
                estado_nombre="Activo",
                Informacion="",
                DocumentoEstado="",
                correo="estudiante@example.com",
                ultimo_periodo=1060,
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


class StudentStatePaginationTests(unittest.TestCase):
    def test_list_paginates_before_enriching_student_rows(self) -> None:
        statement = sisacademico_admin._actualizacion_estudiante_list_select(
            page_size=25,
            offset=50,
        )

        self.assertIn("WITH selected_students AS", statement)
        self.assertIn("OFFSET 50 ROWS FETCH NEXT 25 ROWS ONLY", statement)
        self.assertLess(statement.index("OFFSET 50 ROWS"), statement.index("FROM selected_students d"))

    def test_list_returns_total_and_clamps_page_to_available_results(self) -> None:
        cursor = RecordingCursor(total=63)
        section = sisacademico_admin.SECTIONS["actualizacion_estudiantes"]

        with patch.object(
            sisacademico_admin,
            "get_connection",
            return_value=RecordingConnection(cursor),
        ):
            result = sisacademico_admin._list_actualizacion_estudiantes_records(
                section,
                query="prueba",
                page=99,
                page_size=25,
            )

        self.assertEqual(result["total"], 63)
        self.assertEqual(result["page"], 3)
        self.assertEqual(result["page_size"], 25)
        self.assertEqual(result["total_pages"], 3)
        self.assertTrue(result["has_previous"])
        self.assertFalse(result["has_next"])
        self.assertEqual(len(cursor.calls), 2)
        self.assertIn("COUNT_BIG(*)", cursor.calls[0][0])
        self.assertIn("OFFSET 50 ROWS FETCH NEXT 25 ROWS ONLY", cursor.calls[1][0])
        self.assertEqual(cursor.calls[0][1], cursor.calls[1][1])

    def test_public_route_forwards_page_configuration(self) -> None:
        expected = {"rows": [], "total": 0, "page": 2, "page_size": 50}
        with patch.object(
            sisacademico_admin,
            "_list_actualizacion_estudiantes_records",
            return_value=expected,
        ) as specialized_list:
            result = sisacademico_admin.list_records(
                "actualizacion_estudiantes",
                query="ana",
                limit=None,
                periodo="1060",
                page=2,
                page_size=50,
                _=Mock(),
            )

        self.assertEqual(result, expected)
        specialized_list.assert_called_once_with(
            sisacademico_admin.SECTIONS["actualizacion_estudiantes"],
            "ana",
            "1060",
            2,
            50,
        )


if __name__ == "__main__":
    unittest.main()
