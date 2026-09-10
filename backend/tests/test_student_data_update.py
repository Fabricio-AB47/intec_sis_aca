from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException

from app.routers import students
from app.core.security import SessionUser


class StudentDataUpdateSchemaTests(unittest.TestCase):
    def test_data_update_uses_only_columns_declared_for_each_source_table(self) -> None:
        self.assertIn("paisResidenciaId", students._LEGACY_STUDENT_DATA_FIELDS)
        self.assertIn("codprov", students._LEGACY_STUDENT_DATA_FIELDS)
        self.assertIn("Canton", students._LEGACY_STUDENT_DATA_FIELDS)
        self.assertIn("paisNacionalidadId", students._LEGACY_TEACHER_DATA_FIELDS)
        self.assertIn("provinciaSufragio", students._LEGACY_TEACHER_DATA_FIELDS)
        self.assertEqual(
            students._LEGACY_DATA_READONLY_FIELDS,
            {
                "estudiantes": {"Cedula_Est", "correointec"},
                "docentes": {"cedula_doc"},
            },
        )

    def test_field_metadata_preserves_database_type_length_and_nullability(self) -> None:
        cursor = Mock()
        cursor.fetchall.return_value = [
            SimpleNamespace(
                COLUMN_NAME="Cedula_Est",
                DATA_TYPE="varchar",
                CHARACTER_MAXIMUM_LENGTH=50,
                IS_NULLABLE="NO",
            ),
            SimpleNamespace(
                COLUMN_NAME="codprov",
                DATA_TYPE="decimal",
                CHARACTER_MAXIMUM_LENGTH=None,
                IS_NULLABLE="YES",
            ),
        ]

        metadata = students._actualizacion_datos_field_metadata(
            cursor,
            "estudiantes",
            ["Cedula_Est", "codprov"],
        )

        self.assertTrue(metadata["Cedula_Est"]["readonly"])
        self.assertEqual(metadata["Cedula_Est"]["max_length"], 50)
        self.assertFalse(metadata["Cedula_Est"]["nullable"])
        self.assertEqual(metadata["codprov"]["data_type"], "decimal")
        self.assertTrue(metadata["codprov"]["nullable"])

    def test_territorial_catalogs_include_their_parent_codes(self) -> None:
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [SimpleNamespace(option_value="56", option_label="Ecuador")],
            [SimpleNamespace(option_value="01", option_label="Azuay", parent_value="56")],
            [SimpleNamespace(option_value="0101", option_label="Cuenca", parent_value="01")],
        ]

        catalogs = students._territorial_catalogs(
            cursor,
            ["paisResidenciaId", "codprov", "Canton"],
            "estudiantes",
        )

        self.assertEqual(catalogs["paisResidenciaId"][0]["value"], "56")
        self.assertEqual(catalogs["codprov"][0], {
            "value": "1",
            "label": "Azuay",
            "parent_value": "56",
        })
        self.assertEqual(catalogs["Canton"][0]["parent_value"], "01")

    @patch.object(students, "_table_columns")
    def test_pueblo_nacionalidad_uses_its_unique_identifier(self, table_columns: Mock) -> None:
        table_columns.return_value = {
            "codigo_pueblo_nacionalidad",
            "codigo_etnia_aplica",
            "nombre_pueblo_nacionalidad",
            "activo",
        }
        cursor = Mock()
        cursor.fetchall.return_value = [SimpleNamespace(option_value="6", option_label="Achuar")]

        options = students._catalog_options_from_table(cursor, "PuebloNacionalidad")

        self.assertEqual(options, [{"value": "6", "label": "Achuar"}])
        statement = cursor.execute.call_args.args[0]
        self.assertIn("[codigo_pueblo_nacionalidad]", statement)
        self.assertNotIn("TRY_CONVERT(nvarchar(100), [codigo_etnia_aplica])", statement)

    def test_canton_must_belong_to_the_selected_province(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = SimpleNamespace(parent_code="17")

        with self.assertRaises(HTTPException) as raised:
            students._validate_territorial_updates(
                cursor,
                "estudiantes",
                {
                    "provinciaNacimeintoId": "08",
                    "cantonNacimeintoId": "1701",
                },
                {"cantonNacimeintoId"},
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("no pertenece", str(raised.exception.detail))

    def test_schema_values_are_coerced_without_turning_empty_numbers_into_zero(self) -> None:
        nullable_decimal = {"data_type": "decimal", "max_length": None, "nullable": True}
        required_integer = {"data_type": "int", "max_length": None, "nullable": False}
        limited_text = {"data_type": "nchar", "max_length": 2, "nullable": True}
        date_field = {"data_type": "date", "max_length": None, "nullable": True}

        self.assertIsNone(students._coerce_data_update_value("codprov", "", nullable_decimal))
        self.assertEqual(
            students._coerce_data_update_value("codprov", "01", nullable_decimal),
            Decimal("1"),
        )
        self.assertEqual(
            students._coerce_data_update_value("Fecha_Nac", "2026-09-09", date_field),
            date(2026, 9, 9),
        )
        with self.assertRaises(HTTPException):
            students._coerce_data_update_value("Sexo", "", required_integer)
        with self.assertRaises(HTTPException):
            students._coerce_data_update_value("carnet_conadis", "123", limited_text)

    def test_invalid_email_is_rejected_instead_of_being_erased(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            students._validate_data_update_inputs("estudiantes", {"correo": "correo-invalido"})

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("no es válido", str(raised.exception.detail))

    @patch.object(students, "sync_person_complements", return_value={})
    @patch.object(students, "_load_legacy_data_update_record")
    @patch.object(students, "_actualizacion_datos_field_metadata")
    @patch.object(students, "_actualizacion_datos_columns")
    @patch.object(students, "get_connection")
    def test_update_targets_only_the_resolved_record_and_keeps_audit_user(
        self,
        get_connection: Mock,
        data_columns: Mock,
        field_metadata: Mock,
        load_record: Mock,
        sync_complements: Mock,
    ) -> None:
        connection = MagicMock()
        cursor = Mock()
        get_connection.return_value = connection
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = SimpleNamespace(
            record_id="42",
            record_document="1700000000",
            cedula_doc="1700000000",
            correo="anterior@intec.edu.ec",
        )
        cursor.rowcount = 1
        data_columns.return_value = ["cedula_doc", "correo"]
        field_metadata.return_value = {
            "cedula_doc": {"data_type": "nchar", "max_length": 15, "nullable": False, "readonly": True},
            "correo": {"data_type": "nchar", "max_length": 50, "nullable": True, "readonly": False},
        }
        load_record.return_value = {
            "person": {"codigo": "42", "cedula": "1700000000", "nombre": "Docente", "correo": "nuevo@intec.edu.ec"},
            "fields": {"correo": "nuevo@intec.edu.ec"},
        }

        response = students.update_legacy_data_update_record(
            "docentes",
            "1700000000",
            students.DataUpdatePayload(fields={"correo": "nuevo@intec.edu.ec"}),
            SessionUser(login="admin", rol="ADMINISTRADOR"),
        )

        update_call = cursor.execute.call_args_list[-1]
        self.assertNotIn(" OR ", update_call.args[0].upper())
        self.assertEqual(update_call.args[-1], "42")
        self.assertEqual(response["affected_rows"], 1)
        sync_complements.assert_called_once()
        self.assertEqual(sync_complements.call_args.args[0]["usuario"], "admin")


if __name__ == "__main__":
    unittest.main()
