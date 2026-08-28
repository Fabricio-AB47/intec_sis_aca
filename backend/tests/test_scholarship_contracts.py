import unittest
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from app.routers.preinscription import (
    _build_scholarship_contract_pdf,
    _exclude_english_scholarship_items,
    _is_english_career,
    _scholarship_contract_base_number,
    _scholarship_contract_initial,
    _scholarship_contract_scope,
)
from app.services.screen_access import DEFAULT_ACCESS, SCREEN_CATALOG


def scholarship_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "beca_id": 25,
        "codigo_estud": "1051",
        "cedula": "0706442670",
        "estudiante": "ESTUDIANTE DE PRUEBA",
        "codigo_carrera": "8",
        "carrera": "Administración",
        "codigo_periodo": "1060",
        "periodo": "C1-2026-PC",
        "tipo_beca": "Beca INTEC",
        "porcentaje_beca": 25,
        "valor_beca": 187.50,
    }
    item.update(overrides)
    return item


class ScholarshipContractTests(unittest.TestCase):
    def test_english_career_is_excluded_from_scholarships(self) -> None:
        self.assertTrue(_is_english_career("12", "Inglés"))
        self.assertTrue(_is_english_career("", "Escuela de Idiomas"))
        self.assertFalse(_is_english_career("8", "Administración"))

    def test_scholarship_lists_remove_english_career(self) -> None:
        items = [
            {"codigo_carrera": "12", "carrera": "Inglés"},
            {"codigo_carrera": "8", "carrera": "Administración"},
        ]

        self.assertEqual(_exclude_english_scholarship_items(items), [items[1]])

    def test_intec_scholarship_excludes_enrollment_and_administrative_fees(self) -> None:
        scope = _scholarship_contract_scope(scholarship_item())

        self.assertIn("25% del arancel académico", scope)
        self.assertIn("no se aplica al valor de matrícula", scope)
        self.assertIn("otros rubros administrativos", scope)

    def test_mintel_scholarship_preserves_its_fixed_institutional_scope(self) -> None:
        scope = _scholarship_contract_scope(
            scholarship_item(tipo_beca="Beca MINTEL", porcentaje_beca=100),
        )

        self.assertIn("porcentaje institucional fijo", scope)
        self.assertIn("cuenta estudiantil aprobada", scope)

    def test_contract_pdf_contains_student_and_traceability_information(self) -> None:
        contract_number = _scholarship_contract_base_number(
            scholarship_item(),
            date(2026, 8, 27),
        )
        content = _build_scholarship_contract_pdf(
            scholarship_item(),
            contract_number,
            date(2026, 8, 27),
        )

        self.assertTrue(content.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(content))
        self.assertEqual(len(reader.pages), 1)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("CONTRATO DE BECA - No.", text)
        self.assertIn("ESTUDIANTE DE PRUEBA", text)
        self.assertIn(contract_number, text)
        self.assertIn("Beca INTEC", text)
        self.assertIn("C1-2026-PC", text)
        self.assertIn("rige exclusivamente durante el período", text)

    def test_scholarship_number_starts_with_the_first_significant_letter(self) -> None:
        self.assertEqual(_scholarship_contract_initial("Beca INTEC"), "I")
        self.assertEqual(_scholarship_contract_initial("Beca MINTEL"), "M")
        self.assertEqual(_scholarship_contract_initial("Futuro Femenino"), "F")

        number = _scholarship_contract_base_number(
            scholarship_item(tipo_beca="Beca INTEC", beca_id=25, codigo_periodo="1060"),
            date(2026, 8, 27),
        )
        self.assertEqual(number, "I002510602026")

    def test_contract_explicitly_limits_the_scholarship_to_one_period(self) -> None:
        content = _build_scholarship_contract_pdf(
            scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
            "I002510602026",
            date(2026, 8, 27),
        )

        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        self.assertIn("C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026", text)
        self.assertIn("No se renovará automáticamente", text)

    def test_contract_screen_is_assignable_to_authorized_profiles(self) -> None:
        screen = next(
            item for item in SCREEN_CATALOG
            if item["page"] == "preinscripcion/contratos-becas"
        )

        self.assertEqual(screen["label"], "Contratos de beca")
        self.assertIn("preinscripcion/contratos-becas", DEFAULT_ACCESS["ADMINISTRADOR"])
        self.assertIn("preinscripcion/contratos-becas", DEFAULT_ACCESS["BIENESTAR"])
        self.assertNotIn("preinscripcion/contratos-becas", DEFAULT_ACCESS["ESTUDIANTE"])


if __name__ == "__main__":
    unittest.main()
