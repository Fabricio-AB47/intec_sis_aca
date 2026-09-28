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

    def fetchone(self) -> SimpleNamespace:
        return self.fetchall()[0]

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
    def test_description_supports_old_and_current_audit_formats(self):
        for detail in (
            '[CAMBIO DE ESTADO] A -> R. Motivo: Retiro solicitado. Usuario: Prueba. Fecha: 2026-09-28 10:00:00.',
            '[CAMBIO DE ESTADO] A -> R. Usuario: Prueba. Fecha: 2026-09-28 10:00:00. Motivo: Retiro solicitado.',
        ):
            with self.subTest(detail=detail):
                row = sisacademico_admin._actualizacion_estudiante_row(SimpleNamespace(Informacion=detail))
                self.assertEqual(row['DescripcionEstado'], 'Retiro solicitado')
                self.assertEqual(row['Informacion'], detail)
        self.assertEqual(sisacademico_admin._student_state_description(None), '')
        self.assertEqual(sisacademico_admin._student_state_description('Descripción antigua'), 'Descripción antigua')

    def test_later_upload_cannot_replace_change_description_and_blank_url_cannot_hide_file(self):
        for query in (sisacademico_admin._actualizacion_estudiante_select(1),
                      sisacademico_admin._actualizacion_estudiante_list_select(25, 0)):
            with self.subTest(query=query):
                self.assertIn('state_change.DETALLE', query)
                self.assertIn("NOT LIKE N'[[]CAMBIO DE ESTADO] Respaldo posterior%'", query)
                self.assertIn('state_document.LINKURL', query)
                self.assertIn("rd.LINKURL))), '') IS NOT NULL", query)

    def setUp(self) -> None:
        self.state_options = [
            {"value": code, "label": f"{code} - {name}"}
            for code, name in (
                ("A", "Activo"), ("C", "Cambio Periodo"), ("D", "E Continua"),
                ("E", "Reingreso"), ("G", "Graduado"), ("P", "Inactivo"), ("R", "Retirado"),
            )
        ]
        lookup_patch = patch.object(
            sisacademico_admin, "_lookup_options_for_section",
            return_value={"Estado": self.state_options},
        )
        self.lookup = lookup_patch.start()
        self.addCleanup(lookup_patch.stop)

    def assert_complete_state_catalog(self, result: dict) -> None:
        for group in ("list_fields", "detail_fields", "editable_fields"):
            state = next(field for field in result["section"][group] if field["name"] == "Estado")
            self.assertEqual(state["options"], self.state_options)

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
        self.assert_complete_state_catalog(result)
        self.assertEqual(result["rows"][0]["Estado"], "A")
        self.lookup.assert_called_once_with("actualizacion_estudiantes")

    def test_empty_search_still_returns_all_state_options(self) -> None:
        cursor = RecordingCursor(total=0)
        cursor.fetchall = Mock(return_value=[])
        with patch.object(sisacademico_admin, "get_connection", return_value=RecordingConnection(cursor)):
            result = sisacademico_admin._list_actualizacion_estudiantes_records(
                sisacademico_admin.SECTIONS["actualizacion_estudiantes"], "sin resultados",
            )
        self.assertEqual(result["rows"], [])
        self.assert_complete_state_catalog(result)

    def test_record_detail_preserves_all_state_options(self) -> None:
        cursor = RecordingCursor()
        with patch.object(sisacademico_admin, "get_connection", return_value=RecordingConnection(cursor)):
            result = sisacademico_admin._get_actualizacion_estudiantes_record(
                sisacademico_admin.SECTIONS["actualizacion_estudiantes"],
                sisacademico_admin._encode_key(["1724036536"]),
            )
        self.assert_complete_state_catalog(result)
        self.assertEqual(result["record"]["Estado"], "A")

    def test_student_catalog_is_not_limited_to_first_states_or_teacher_states(self) -> None:
        query = sisacademico_admin.LOOKUP_QUERIES["actualizacion_estudiantes"]["Estado"][0]
        self.assertNotRegex(query, r"(?i)\bTOP\s*\(")
        self.assertNotIn("IN (N'A', N'P')", query)
        self.assertIn("FROM dbo.ESTADO", query)
        teacher_query = sisacademico_admin.LOOKUP_QUERIES["actualizacion_est"]["Estado"][0]
        self.assertIn("IN (N'A', N'P')", teacher_query)

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
