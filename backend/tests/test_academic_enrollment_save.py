import unittest
from datetime import date
from unittest.mock import Mock, patch

from app.routers.academic_enrollment import (
    AcademicEnrollmentPayload,
    _save_enrollment_with_cursor,
)


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1

    def execute(self, statement: str, *params: object) -> "RecordingCursor":
        self.calls.append((statement, params))
        return self

    def fetchone(self) -> None:
        return None


class AcademicEnrollmentSaveTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
