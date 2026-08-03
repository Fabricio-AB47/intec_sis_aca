import unittest

from fastapi import HTTPException

from app.routers.academic_enrollment import (
    AcademicEnrollmentPayload,
    _validate_payload,
    _would_create_prerequisite_cycle,
)


def payload(**overrides: object) -> AcademicEnrollmentPayload:
    values: dict[str, object] = {
        "codigo_estud": 100,
        "cod_anio_basica": 8,
        "codigo_periodo": 1034,
        "materia_codes": [101, 102],
    }
    values.update(overrides)
    return AcademicEnrollmentPayload(**values)


class AcademicEnrollmentPrerequisiteTests(unittest.TestCase):
    def test_rejects_direct_prerequisite_cycle(self) -> None:
        self.assertTrue(_would_create_prerequisite_cycle([(101, 102)], 102, 101))

    def test_rejects_indirect_prerequisite_cycle(self) -> None:
        edges = [(101, 102), (102, 103)]

        self.assertTrue(_would_create_prerequisite_cycle(edges, 103, 101))

    def test_accepts_non_cyclic_prerequisite_chain(self) -> None:
        edges = [(101, 102), (102, 103)]

        self.assertFalse(_would_create_prerequisite_cycle(edges, 103, 104))

    def test_exception_subject_must_be_selected(self) -> None:
        enrollment = payload(
            prerequisite_exception_codes=[999],
            prerequisite_exception_reason="Autorizacion academica documentada",
        )

        with self.assertRaises(HTTPException) as context:
            _validate_payload(enrollment)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("materias seleccionadas", str(context.exception.detail))

    def test_exception_requires_a_meaningful_reason(self) -> None:
        enrollment = payload(
            prerequisite_exception_codes=[101],
            prerequisite_exception_reason="Corto",
        )

        with self.assertRaises(HTTPException) as context:
            _validate_payload(enrollment)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("al menos 10 caracteres", str(context.exception.detail))

    def test_valid_exception_is_normalized(self) -> None:
        enrollment = payload(
            materia_codes=[102, 101, 101],
            prerequisite_exception_codes=[102, 102],
            prerequisite_exception_reason="  Autorizado por coordinacion academica  ",
        )

        _validate_payload(enrollment)

        self.assertEqual(enrollment.materia_codes, [101, 102])
        self.assertEqual(enrollment.prerequisite_exception_codes, [102])
        self.assertEqual(
            enrollment.prerequisite_exception_reason,
            "Autorizado por coordinacion academica",
        )


if __name__ == "__main__":
    unittest.main()
