import unittest
from datetime import date
from unittest.mock import Mock, patch

from app.routers.academic_enrollment import (
    AcademicEnrollmentPayload,
    _fetch_existing_codes,
    _next_subject_matricula,
    _save_enrollment_with_cursor,
)


class RecordingCursor:
    def __init__(self, fetchone_result=None) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1
        self.fetchone_result = fetchone_result

    def execute(self, statement: str, *params: object) -> "RecordingCursor":
        self.calls.append((statement, params))
        return self

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self) -> list:
        return []


class AcademicEnrollmentSaveTests(unittest.TestCase):
    def test_duplicate_checks_use_transaction_locks(self) -> None:
        payload = AcademicEnrollmentPayload(
            codigo_estud=100,
            cod_anio_basica=8,
            codigo_periodo=1034,
            materia_codes=[101],
        )
        existing_cursor = RecordingCursor()
        _fetch_existing_codes(existing_cursor, payload, for_update=True)

        attempt_cursor = RecordingCursor((2,))
        attempt = _next_subject_matricula(
            attempt_cursor,
            100,
            8,
            101,
            for_update=True,
        )

        self.assertIn("WITH (UPDLOCK, HOLDLOCK)", existing_cursor.calls[0][0])
        self.assertIn("WITH (UPDLOCK, HOLDLOCK)", attempt_cursor.calls[0][0])
        self.assertIn("COUNT(", attempt_cursor.calls[0][0])
        self.assertIn("DISTINCT", attempt_cursor.calls[0][0])
        self.assertIn("codigo_periodo", attempt_cursor.calls[0][0])
        self.assertNotIn("MAX(TRY_CONVERT(int, Num_Matricula))", attempt_cursor.calls[0][0])
        self.assertEqual(attempt, 2)

    def test_new_regular_or_special_subject_uses_n_in_carreraxestud(self) -> None:
        preview = {
            "summary": {
                "bloqueadas_por_prerrequisito": 0,
                "bloqueadas_por_periodo": 0,
            },
            "items": [
                {
                    "codigo_materia": "101",
                    "nombre_materia": "Matemática aplicada",
                    "accion": "INSERTAR",
                }
            ],
        }
        pensum = {
            101: {
                "codigo_materia": "101",
                "nombre_materia": "Matemática aplicada",
                "creditos": 3,
            }
        }

        expected_types = (("R", "N"), ("E", "N"), ("H", "H"))
        for period_type, expected_cxe_type in expected_types:
            with self.subTest(period_type=period_type, expected_cxe_type=expected_cxe_type):
                cursor = RecordingCursor()
                payload = AcademicEnrollmentPayload(
                    codigo_estud=100,
                    cod_anio_basica=8,
                    codigo_periodo=1034,
                    materia_codes=[101],
                    tipo_matricula=period_type,
                )
                with patch.multiple(
                    "app.routers.academic_enrollment",
                    _validate_payload=Mock(),
                    _resolve_or_create_student_from_preinscription=Mock(return_value=True),
                    _preview_with_cursor=Mock(return_value=preview),
                    _fetch_pensum_by_code=Mock(return_value=pensum),
                    _fetch_jornada_name=Mock(return_value="Nocturno"),
                    _fetch_existing_codes=Mock(return_value={}),
                    _next_number=Mock(return_value=1),
                    _next_subject_matricula=Mock(return_value=1),
                ):
                    result = _save_enrollment_with_cursor(
                        cursor,
                        payload,
                        "ADMIN",
                        date(2026, 8, 27),
                    )

                insert_call = next(
                    call
                    for call in cursor.calls
                    if "INSERT INTO dbo.CARRERAXESTUD" in call[0]
                )
                self.assertEqual(insert_call[1][10], expected_cxe_type)
                self.assertEqual(result["inserted"], 1)

    def test_second_subject_enrollment_is_inserted_with_attempt_two(self) -> None:
        cursor = RecordingCursor()
        payload = AcademicEnrollmentPayload(
            codigo_estud=100,
            cod_anio_basica=8,
            codigo_periodo=1034,
            materia_codes=[101],
            tipo_matricula="R",
        )
        preview = {
            "summary": {"bloqueadas_por_prerrequisito": 0, "bloqueadas_por_periodo": 0},
            "items": [{"codigo_materia": 101, "accion": "INSERTAR"}],
        }
        pensum = {101: {"nombre_materia": "Matemática aplicada", "creditos": 3}}

        with (
            patch("app.routers.academic_enrollment._validate_payload"),
            patch(
                "app.routers.academic_enrollment._resolve_or_create_student_from_preinscription",
                return_value=True,
            ),
            patch("app.routers.academic_enrollment._preview_with_cursor", return_value=preview),
            patch("app.routers.academic_enrollment._fetch_pensum_by_code", return_value=pensum),
            patch("app.routers.academic_enrollment._fetch_jornada_name", return_value="Nocturno"),
            patch("app.routers.academic_enrollment._fetch_existing_codes", return_value={}) as existing,
            patch("app.routers.academic_enrollment._next_number", return_value=1) as next_number,
            patch("app.routers.academic_enrollment._next_subject_matricula", return_value=2) as attempt,
        ):
            result = _save_enrollment_with_cursor(
                cursor,
                payload,
                "ADMIN",
                date(2026, 9, 7),
            )

        insert_call = next(
            call for call in cursor.calls if "INSERT INTO dbo.CARRERAXESTUD" in call[0]
        )
        header_lookup = next(
            call for call in cursor.calls if "SELECT TOP (1) Num_Matricula" in call[0]
        )
        self.assertIn("WITH (UPDLOCK, HOLDLOCK)", header_lookup[0])
        self.assertEqual(insert_call[1][4], 2)
        self.assertEqual(result["subject_results"][0]["num_matricula"], 2)
        existing.assert_called_once_with(cursor, payload, for_update=True)
        next_number.assert_called_once_with(
            cursor,
            "CARRERAXESTUD",
            "Num_Reg_Mat",
            for_update=True,
        )
        attempt.assert_called_once_with(cursor, 100, 8, 101, for_update=True)


if __name__ == "__main__":
    unittest.main()
