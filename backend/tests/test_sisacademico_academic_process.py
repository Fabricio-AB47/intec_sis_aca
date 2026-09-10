import unittest
from datetime import date, datetime, time
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.routers import sisacademico_admin


class AcademicProcessSchemaTests(unittest.TestCase):
    def test_sections_use_the_primary_keys_from_the_database_schema(self) -> None:
        self.assertEqual(
            sisacademico_admin.SECTIONS["materia_homo_textof"]["key_fields"],
            ["cod_materia", "cod_periodo"],
        )
        self.assertEqual(
            sisacademico_admin.SECTIONS["asistencia_estudiantes"]["key_fields"],
            [
                "codigo_estud",
                "cod_anio_Basica",
                "codigo_materia",
                "codigo_periodo",
                "paralelo",
                "Fecha",
            ],
        )

    def test_period_exposes_all_editable_configuration_columns(self) -> None:
        section = sisacademico_admin.SECTIONS["periodos"]
        editable = {field.name for field in section["editable_fields"]}
        detail = {field.name for field in section["detail_fields"]}

        for name in ("Detalle_Reg", "VersionCalificacion", "NotaPromedioMax"):
            self.assertIn(name, editable)
            self.assertIn(name, detail)

    def test_curriculum_dependencies_and_schedules_are_available(self) -> None:
        dependencies = sisacademico_admin.SECTIONS["materias_consecutivas"]
        schedules = sisacademico_admin.SECTIONS["horarios_academicos"]

        self.assertEqual(dependencies["table"], "[dbo].[MATERIAS_CONSECUTIVAS]")
        self.assertEqual(schedules["table"], "[dbo].[HORARIOS]")
        self.assertEqual(schedules["key_fields"], ["id"])
        self.assertEqual(
            {field.name for field in schedules["create_fields"]},
            {
                "cod_materia",
                "cod_periodo",
                "cod_carrera",
                "cod_jornada",
                "paralelo",
                "dia_semana",
                "hora_inicio",
                "hora_fin",
                "codigo_docente",
                "fecha_inicio",
                "fecha_finalizacion",
            },
        )

    def test_date_datetime_and_time_values_are_normalized(self) -> None:
        date_field = sisacademico_admin.field("fecha", "Fecha", "date")
        datetime_field = sisacademico_admin.field("fecha_hora", "Fecha y hora", "datetime")
        time_field = sisacademico_admin.field("hora", "Hora", "time")

        self.assertEqual(sisacademico_admin._normalize_value("2026-09-09", date_field), date(2026, 9, 9))
        self.assertEqual(
            sisacademico_admin._normalize_value("2026-09-09T18:30", datetime_field),
            datetime(2026, 9, 9, 18, 30),
        )
        self.assertEqual(sisacademico_admin._normalize_value("18:30", time_field), time(18, 30))

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._normalize_value("09/09/2026", date_field)
        self.assertEqual(raised.exception.status_code, 400)

    def test_subject_rejects_a_malla_from_another_career(self) -> None:
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), None, None, (1,)]

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._validate_academic_process_values(
                cursor,
                "materias",
                {
                    "Cod_AnioBasica": 7,
                    "NumMalla": 2026,
                    "Semestre": 1,
                    "Creditos": 3,
                    "Horas": 72,
                    "ValorHora": 0,
                    "ValorHoraVirtual": 0,
                },
                creating=True,
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("no pertenece", str(raised.exception.detail))

    def test_first_subject_creates_initial_malla_relation_for_new_career(self) -> None:
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), None, None, None]

        sisacademico_admin._validate_academic_process_values(
            cursor,
            "materias",
            {
                "Cod_AnioBasica": 91,
                "NumMalla": 2027,
                "Semestre": 1,
                "Creditos": 3,
                "Horas": 72,
                "ValorHora": 0,
                "ValorHoraVirtual": 0,
            },
            creating=True,
        )

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("INSERT INTO dbo.MALLA_PENSUM" in statement for statement in statements))

    def test_consecutive_subject_relation_cannot_be_duplicated(self) -> None:
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (1,), (1,)]

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._validate_academic_process_values(
                cursor,
                "materias_consecutivas",
                {
                    "cod_carrera": "7",
                    "cod_materia": "100",
                    "cod_materia_consecutiva": "101",
                    "bloqueada_por_reprobacion": True,
                },
                creating=True,
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_schedule_rejects_an_invalid_time_range(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = (1,)

        with self.assertRaises(HTTPException) as raised:
            sisacademico_admin._validate_academic_process_values(
                cursor,
                "horarios_academicos",
                {
                    "cod_materia": "VGA-TEST",
                    "cod_periodo": "1060",
                    "cod_carrera": "7",
                    "cod_jornada": "2",
                    "paralelo": "1",
                    "dia_semana": "1",
                    "hora_inicio": time(20, 0),
                    "hora_fin": time(19, 0),
                    "codigo_docente": "10",
                    "fecha_inicio": date(2026, 9, 1),
                    "fecha_finalizacion": date(2026, 12, 1),
                },
                creating=True,
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("hora de fin", str(raised.exception.detail))

    def test_any_standard_section_can_use_server_pagination(self) -> None:
        expected = {"rows": [], "total": 14, "page": 1}
        with patch.object(
            sisacademico_admin,
            "_list_academic_catalog_records",
            return_value=expected,
        ) as paginated_list:
            result = sisacademico_admin.list_records(
                "mallas",
                query="2026",
                limit=None,
                periodo=None,
                carrera=None,
                paginado=True,
                page=1,
                page_size=25,
                _=Mock(),
            )

        self.assertEqual(result, expected)
        paginated_list.assert_called_once_with(
            "mallas",
            sisacademico_admin.SECTIONS["mallas"],
            "2026",
            None,
            1,
            25,
        )

    def test_database_duplicate_is_reported_as_conflict(self) -> None:
        error = sisacademico_admin._write_error(Exception("SQL Server 2627 duplicate key"), "Error")
        self.assertEqual(error.status_code, 409)


if __name__ == "__main__":
    unittest.main()
