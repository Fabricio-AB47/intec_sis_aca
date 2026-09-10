import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.routers import sisacademico_admin


class AcademicCatalogCursor:
    columns = [
        "codigo_materia",
        "Cod_AnioBasica",
        "Nomb_Materia",
        "Semestre",
        "Creditos",
        "estado_mat",
    ]

    def __init__(self) -> None:
        self.description = [(column,) for column in self.columns]
        self.executions: list[tuple[str, list[object]]] = []
        self._is_count = False
        self._is_malla_lookup = False

    def execute(self, statement: str, params: list[object]) -> "AcademicCatalogCursor":
        self.executions.append((statement, list(params)))
        self._is_count = "COUNT_BIG" in statement
        self._is_malla_lookup = "FROM dbo.MALLA_PENSUM" in statement
        if not self._is_count and not self._is_malla_lookup:
            self.description = [(column,) for column in self.columns]
        return self

    def fetchone(self) -> tuple[int]:
        return (53,)

    def fetchall(self) -> list[tuple[object, ...]]:
        if self._is_count:
            return []
        if self._is_malla_lookup:
            return [("2026", "2026 - Malla")]
        return [(501, 71, "Sistemas Operativos", 2, 4, "ACTIVO")]


class AcademicCatalogConnection:
    def __init__(self, cursor: AcademicCatalogCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "AcademicCatalogConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> AcademicCatalogCursor:
        return self._cursor


class AcademicCreateCursor:
    def __init__(self) -> None:
        self.mode = ""
        self.description: list[tuple[str]] = []
        self.created_columns = sisacademico_admin._selectable_columns(
            sisacademico_admin._all_read_columns(sisacademico_admin.SECTIONS["materias"])
        )

    def execute(self, statement: str, _params: object = None) -> "AcademicCreateCursor":
        if "FROM dbo.CARRERAS" in statement:
            self.mode = "career"
        elif "FROM dbo.MALLA_PENSUM" in statement:
            self.mode = "malla"
        elif "INSERT INTO [dbo].[PENSUM]" in statement:
            self.mode = "insert"
        elif "SCOPE_IDENTITY" in statement:
            self.mode = "identity"
        elif "FROM [dbo].[PENSUM]" in statement:
            self.mode = "created_record"
            self.description = [(column,) for column in self.created_columns]
        return self

    def fetchone(self) -> tuple[object] | None:
        if self.mode in {"career", "malla"}:
            return (1,)
        if self.mode == "identity":
            return (901,)
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        if self.mode != "created_record":
            return []
        record = {
            "codigo_materia": 901,
            "Cod_AnioBasica": 14,
            "Nomb_Materia": "Materia de prueba",
            "Semestre": 1,
            "Creditos": 3,
            "NumMalla": 2026,
            "Horas": 72,
            "ValorHora": 0,
            "ValorHoraVirtual": 0,
            "verreporte": 1,
            "SecuenciaMateria": "0",
            "estado_mat": "A",
        }
        return [tuple(record.get(column) for column in self.created_columns)]


class AcademicCreateConnection:
    def __init__(self) -> None:
        self._cursor = AcademicCreateCursor()
        self.committed = False

    def __enter__(self) -> "AcademicCreateConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> AcademicCreateCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


class CareersPensumTests(unittest.TestCase):
    def test_pensum_list_filters_by_career_and_paginates_in_sql(self) -> None:
        cursor = AcademicCatalogCursor()
        section = sisacademico_admin.SECTIONS["materias"]

        with (
            patch.object(
                sisacademico_admin,
                "get_connection",
                return_value=AcademicCatalogConnection(cursor),
            ),
            patch.object(sisacademico_admin, "_lookup_options_for_section", return_value={}),
        ):
            result = sisacademico_admin._list_academic_catalog_records(
                "materias",
                section,
                query="operativos",
                carrera="71",
                page=2,
                page_size=25,
            )

        self.assertEqual(len(cursor.executions), 3)
        count_sql, count_params = cursor.executions[0]
        data_sql, data_params = cursor.executions[1]
        malla_sql, malla_params = cursor.executions[2]
        self.assertIn("[Cod_AnioBasica] = ?", count_sql)
        self.assertIn("OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", data_sql)
        self.assertIn("ORDER BY Semestre ASC", data_sql)
        self.assertIn("Orden ASC, Nomb_Materia ASC, codigo_materia ASC", data_sql)
        self.assertEqual(count_params[0], 71)
        self.assertEqual(data_params[-2:], [25, 25])
        self.assertIn("FROM dbo.MALLA_PENSUM", malla_sql)
        self.assertEqual(malla_params, [71, 71])
        self.assertEqual(result["total"], 53)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["total_pages"], 3)
        self.assertEqual(result["rows"][0]["Nomb_Materia"], "Sistemas Operativos")
        malla_field = next(field for field in result["section"]["create_fields"] if field["name"] == "NumMalla")
        self.assertEqual(malla_field["options"], [{"value": "2026", "label": "2026 - Malla"}])

    def test_invalid_career_filter_is_rejected_before_querying(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._list_academic_catalog_records(
                "materias",
                sisacademico_admin.SECTIONS["materias"],
                query=None,
                carrera="carrera-invalida",
                page=1,
                page_size=25,
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_public_route_uses_scoped_pagination_for_the_related_pensum(self) -> None:
        expected = {"rows": [], "total": 0, "page": 1}
        with patch.object(
            sisacademico_admin,
            "_list_academic_catalog_records",
            return_value=expected,
        ) as paginated_list:
            result = sisacademico_admin.list_records(
                "materias",
                query="seguridad",
                limit=None,
                periodo=None,
                carrera="7",
                paginado=True,
                page=1,
                page_size=25,
                _=Mock(),
            )

        self.assertEqual(result, expected)
        paginated_list.assert_called_once_with(
            "materias",
            sisacademico_admin.SECTIONS["materias"],
            "seguridad",
            "7",
            1,
            25,
        )

    def test_catalog_does_not_load_all_database_options_by_default(self) -> None:
        with patch.object(sisacademico_admin, "_lookup_options_by_section") as lookup:
            result = sisacademico_admin.catalog(include_options=False, _=Mock())

        lookup.assert_not_called()
        self.assertTrue(result["sections"])

    def test_schema_exposes_school_text_and_combination_field(self) -> None:
        career_fields = sisacademico_admin.SECTIONS["carreras"]["editable_fields"]
        subject_fields = sisacademico_admin.SECTIONS["materias"]["editable_fields"]

        school = next(field for field in career_fields if field.name == "tp_escuela")
        self.assertEqual(school.type, "text")
        self.assertTrue(any(field.name == "CombinarMateria" for field in subject_fields))

    def test_subject_relation_rejects_an_unknown_career(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = None

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._ensure_pensum_career_exists(cursor, 999999)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("no existe", str(raised.exception.detail))

    def test_duplicate_career_code_is_reported_as_conflict(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = (1,)

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._ensure_new_career_code_available(cursor, 7)

        self.assertEqual(raised.exception.status_code, 409)

    def test_school_type_respects_database_length(self) -> None:
        field = next(
            item
            for item in sisacademico_admin.SECTIONS["carreras"]["editable_fields"]
            if item.name == "tp_escuela"
        )

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._normalize_value("x" * 51, field)

        self.assertEqual(raised.exception.status_code, 400)

    def test_subject_creation_returns_the_persisted_record_for_immediate_refresh(self) -> None:
        connection = AcademicCreateConnection()
        payload = sisacademico_admin.SavePayload(
            values={
                "Cod_AnioBasica": 14,
                "Nomb_Materia": "Materia de prueba",
                "Semestre": 1,
                "Creditos": 3,
                "NumMalla": 2026,
                "Horas": 72,
            }
        )

        with (
            patch.object(sisacademico_admin, "get_connection", return_value=connection),
            patch.object(sisacademico_admin, "_invalidate_after_section_change"),
        ):
            result = sisacademico_admin.create_record("materias", payload, Mock(login="admin"))

        self.assertTrue(connection.committed)
        self.assertEqual(result["affected_rows"], 1)
        self.assertEqual(result["record"]["codigo_materia"], 901)
        self.assertEqual(result["record"]["Semestre"], 1)
        self.assertEqual(result["record_key"], result["record"]["_record_key"])


if __name__ == "__main__":
    unittest.main()
