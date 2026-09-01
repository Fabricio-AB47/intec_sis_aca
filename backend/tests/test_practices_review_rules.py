import unittest

from app.routers.practicas_institucionales import (
    _required_document_codes,
    _required_hours,
    _review_validation_errors,
)
from app.routers.titulacion import _matching_operational_completion


def document(code: str, *, loaded: bool = True) -> dict[str, object]:
    return {
        "Codigo": code,
        "Nombre": code.replace("_", " ").title(),
        "Cargado": loaded,
    }


class PracticesReviewRulesTests(unittest.TestCase):
    def test_requirements_are_process_specific(self) -> None:
        self.assertEqual(_required_hours("PPF"), 240)
        self.assertEqual(_required_hours("VIN"), 60)
        self.assertIn("CARTA_COMPROMISO", _required_document_codes("PPF"))
        self.assertIn("VIDEO_VINCULACION", _required_document_codes("VIN"))

    def test_approval_reports_every_missing_requirement(self) -> None:
        errors = _review_validation_errors(
            "APROBAR",
            120,
            240,
            [document("CARTA_COMPROMISO"), document("REGISTRO_ASISTENCIA", loaded=False)],
            False,
            None,
        )

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("REGISTRO ASISTENCIA" in error.upper() for error in errors))
        self.assertTrue(any("240" in error for error in errors))
        self.assertTrue(any("corroborar" in error.lower() for error in errors))

    def test_approval_is_allowed_only_when_requirements_are_complete(self) -> None:
        errors = _review_validation_errors(
            "APROBAR",
            240,
            240,
            [document(code) for code in _required_document_codes("PPF")],
            True,
            "Información revisada contra matrícula y evidencias.",
        )

        self.assertEqual(errors, [])

    def test_observation_and_rejection_require_a_reason(self) -> None:
        self.assertTrue(
            _review_validation_errors("OBSERVAR", 0, 240, [], False, None)
        )
        self.assertTrue(
            _review_validation_errors("RECHAZAR", 0, 240, [], False, " ")
        )
        self.assertEqual(
            _review_validation_errors(
                "OBSERVAR",
                0,
                240,
                [],
                False,
                "Debe corregir el registro de asistencia.",
            ),
            [],
        )

    def test_titulation_fallback_prefers_exact_career(self) -> None:
        completion_map = {
            ("1724036536", "4", "PPF"): {"ExpedienteId": 10, "Cumple": True},
            ("1724036536", "8", "PPF"): {"ExpedienteId": 11, "Cumple": False},
        }

        result = _matching_operational_completion(
            completion_map,
            "172-403-6536",
            "4",
            "PPF",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["ExpedienteId"], 10)  # type: ignore[index]

    def test_titulation_fallback_rejects_an_ambiguous_career(self) -> None:
        completion_map = {
            ("1724036536", "4", "VIN"): {"ExpedienteId": 20, "Cumple": True},
            ("1724036536", "8", "VIN"): {"ExpedienteId": 21, "Cumple": True},
        }

        result = _matching_operational_completion(
            completion_map,
            "1724036536",
            "",
            "VIN",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
