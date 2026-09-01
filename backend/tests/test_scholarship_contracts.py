import unittest
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from app.routers.preinscription import (
    ScholarshipContractGeneratePayload,
    ScholarshipContractTemplatePayload,
    _build_program_scholarship_contract_pdf,
    _build_selected_scholarship_contract_pdf,
    _build_scholarship_contract_pdf,
    _exclude_english_scholarship_items,
    _is_english_career,
    _scholarship_contract_base_number,
    _scholarship_contract_clauses,
    _scholarship_contract_generation_selection,
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
        "telefono": "0999999999",
        "nivel_formacion": "TERCER NIVEL - TECNÓLOGO SUPERIOR",
        "discapacidad": "2",
        "porcentaje_discapacidad": "0",
        "tipo_discapacidad": "7",
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
        self.assertIn("BECA INTEC", text)
        self.assertIn("C1-2026-PC", text)
        self.assertIn("Resolución No. 002-CR-INTEC-2024", text)
        self.assertIn("CLÁUSULA SEGUNDA.- OBJETIVO ESPECÍFICO", text)
        self.assertIn("DATOS BECA", text)
        self.assertIn("CLÁUSULA TERCERA.- MONTO, RUBROS Y DURACIÓN", text)
        self.assertIn("CLÁUSULA DÉCIMA SEGUNDA.- ACEPTACIÓN Y RATIFICACIÓN", text)
        self.assertIn("Correo INTEC para notificaciones", text)
        self.assertEqual(text.count("Ingeniero JAIME RODER ORTEGA PEREIRA, MGT."), 1)
        self.assertIn("Ing. JAIME RODER ORTEGA PEREIRA, MGT.", text)
        self.assertIn("BECARIO/A – C.C.: 0706442670", text)
        self.assertEqual(text.count("CLÁUSULA TERCERA"), 1)
        self.assertIn("La beca rige exclusivamente", text)
        self.assertIn("adjudicación C1-2026-PC", text)

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
        self.assertIn("MAYO-SEPTIEMBRE 2026", text)
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

    def test_contract_generation_accepts_the_complete_selection_without_a_batch_cap(self) -> None:
        payload = ScholarshipContractGeneratePayload(
            beca_ids=[*range(1, 501), 1, 250],
            codigo_periodo=" 1060 ",
        )

        scholarship_ids, academic_period = _scholarship_contract_generation_selection(payload)

        self.assertEqual(len(scholarship_ids), 500)
        self.assertEqual(scholarship_ids[0], 1)
        self.assertEqual(scholarship_ids[-1], 500)
        self.assertEqual(academic_period, "1060")

    def test_contract_generation_accepts_an_editable_program_template(self) -> None:
        payload = ScholarshipContractGeneratePayload(
            beca_ids=[25],
            codigo_periodo="1060",
            formato_contrato="PROGRAMA",
            plantilla={
                "titulo_contrato": "Contrato de beca especial",
                "programa": "Programa institucional de permanencia académica",
                "rector_tratamiento": "Ingeniero",
                "rector_nombre": "JAIME RODER ORTEGA PEREIRA",
                "rector_titulo": "MGT.",
                "proyeccion": [
                    {
                        "rubro": "Arancel académico",
                        "periodicidad": "25 % durante el período adjudicado",
                    },
                ],
            },
        )

        self.assertEqual(payload.formato_contrato, "PROGRAMA")
        self.assertEqual(payload.plantilla.programa, "Programa institucional de permanencia académica")
        self.assertEqual(len(payload.plantilla.proyeccion), 1)

    def test_contract_template_preserves_an_extended_clause_order(self) -> None:
        clauses = [
            {
                "titulo": f"CLÁUSULA {index:02d}.-",
                "contenido": f"Contenido personalizado {index}.",
            }
            for index in range(1, 26)
        ]

        template = ScholarshipContractTemplatePayload(clausulas_institucionales=clauses)

        self.assertEqual(len(template.clausulas_institucionales or []), 25)
        self.assertEqual(
            [clause.titulo for clause in template.clausulas_institucionales or []],
            [clause["titulo"] for clause in clauses],
        )

    def test_contract_template_allows_removing_all_clauses(self) -> None:
        clauses = _scholarship_contract_clauses(
            {"clausulas_institucionales": []},
            "clausulas_institucionales",
            [
                {
                    "titulo": "CLÁUSULA PREDETERMINADA.-",
                    "contenido": "Este texto no debe restaurarse.",
                },
            ],
        )

        self.assertEqual(clauses, [])

    def test_program_contract_pdf_uses_the_colored_table_format_and_custom_values(self) -> None:
        template = ScholarshipContractTemplatePayload(
            titulo_contrato="CONTRATO DE BECA DE PROGRAMA",
            ciudad="Ambato",
            programa="Programa institucional de permanencia académica",
            rector_tratamiento="Ingeniero",
            rector_nombre="JAIME RODER ORTEGA PEREIRA",
            rector_titulo="MGT.",
            proyeccion=[
                {
                    "rubro": "Arancel académico",
                    "periodicidad": "25 % durante el período adjudicado",
                },
                {
                    "rubro": "Matrícula",
                    "periodicidad": "No cubierta por la Beca INTEC",
                },
            ],
            introduccion_programa="INTRODUCCIÓN EDITADA PARA {ESTUDIANTE} EN {CIUDAD}.",
            clausulas_programa=[
                {
                    "titulo": "CLÁUSULA PERSONALIZADA.-",
                    "contenido": "La beca {BECA} se aplica durante {PERIODO}.",
                },
            ],
            titulo_tabla_datos="INFORMACIÓN PERSONALIZADA",
            titulo_tabla_proyeccion="DETALLE PERSONALIZADO",
            firma_rector_tratamiento="Ing.",
            firma_rector_nombre="JAIME RODER ORTEGA PEREIRA",
            firma_rector_titulo="MGT.",
            firma_rector_etiqueta="REPRESENTANTE INSTITUCIONAL",
            firma_becario_tratamiento="Estudiante:",
            firma_becario_etiqueta="PERSONA BECARIA",
            color_cabecera_tabla="#123456",
            color_celda_etiqueta="#ABCDEF",
            color_cabecera_interior="#234567",
            color_celda_valor="#345678",
            color_borde_tabla="#456789",
        )
        content = _build_program_scholarship_contract_pdf(
            scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
            "I002510602026",
            date(2026, 8, 28),
            template,
        )

        self.assertTrue(content.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(content))
        self.assertEqual(len(reader.pages), 1)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("CONTRATO DE BECA DE PROGRAMA", text)
        self.assertIn("INFORMACIÓN PERSONALIZADA", text)
        self.assertIn("DETALLE PERSONALIZADO", text)
        self.assertIn("Programa institucional de permanencia académica", text)
        self.assertIn("Arancel académico", text)
        self.assertIn("No cubierta por la Beca INTEC", text)
        self.assertIn("Ambato", text)
        self.assertIn("Ing. JAIME RODER ORTEGA PEREIRA, MGT.", text)
        self.assertIn("INTRODUCCIÓN EDITADA PARA ESTUDIANTE DE PRUEBA EN Ambato", text)
        self.assertIn("CLÁUSULA PERSONALIZADA", text)
        self.assertIn("BECA INTEC se aplica durante MAYO-SEPTIEMBRE 2026", text)
        self.assertIn("REPRESENTANTE INSTITUCIONAL", text)
        self.assertIn("Estudiante:", text)
        self.assertIn("PERSONA BECARIA", text)

        content_stream = b"\n".join(
            page.get_contents().get_data()
            for page in reader.pages
            if page.get_contents() is not None
        )
        self.assertIn(b".070588 .203922 .337255 rg", content_stream)
        self.assertIn(b".670588 .803922 .937255 rg", content_stream)
        self.assertIn(b".137255 .270588 .403922 rg", content_stream)
        self.assertIn(b".203922 .337255 .470588 rg", content_stream)
        self.assertIn(b".270588 .403922 .537255 RG", content_stream)

    def test_institutional_contract_allows_editing_its_complete_text(self) -> None:
        template = ScholarshipContractTemplatePayload(
            titulo_contrato="ACUERDO INSTITUCIONAL EDITADO",
            introduccion_institucional=(
                "Documento celebrado en {CIUDAD} entre {RECTOR} y {ESTUDIANTE}, "
                "con cédula {CEDULA}."
            ),
            clausulas_institucionales=[
                {
                    "titulo": "PRIMERA CLÁUSULA EDITADA.-",
                    "contenido": "Corresponde a {BECA} para la carrera {CARRERA}.",
                },
                {
                    "titulo": "SEGUNDA CLÁUSULA EDITADA.-",
                    "contenido": "Su vigencia corresponde al período {PERIODO}.",
                },
                {
                    "titulo": "CIERRE EDITADO.-",
                    "contenido": "Las partes aceptan el contrato {CONTRATO}.",
                },
            ],
            titulo_tabla_datos="DATOS PERSONALIZADOS",
            firma_rector_tratamiento="Ing.",
            firma_rector_nombre="RECTORA DE PRUEBA",
            firma_rector_titulo="MGT.",
            firma_rector_etiqueta="AUTORIDAD",
            firma_becario_tratamiento="Beneficiario:",
            firma_becario_etiqueta="ESTUDIANTE BECADO",
        )
        content = _build_scholarship_contract_pdf(
            scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
            "I002510602026",
            date(2026, 8, 28),
            template,
        )

        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        normalized_text = " ".join(text.split())
        self.assertIn("ACUERDO INSTITUCIONAL EDITADO", normalized_text)
        self.assertIn("Documento celebrado en Quito, D.M.", normalized_text)
        self.assertIn("PRIMERA CLÁUSULA EDITADA", normalized_text)
        self.assertIn("SEGUNDA CLÁUSULA EDITADA", normalized_text)
        self.assertIn("CIERRE EDITADO", normalized_text)
        self.assertIn("DATOS PERSONALIZADOS", normalized_text)
        self.assertIn("Ingeniero JAIME RODER ORTEGA PEREIRA, MGT.", normalized_text)
        self.assertIn("Ing. RECTORA DE PRUEBA, MGT.", normalized_text)
        self.assertIn("AUTORIDAD", normalized_text)
        self.assertIn("Beneficiario:", normalized_text)
        self.assertIn("ESTUDIANTE BECADO", normalized_text)

    def test_selected_contract_builder_dispatches_both_formats(self) -> None:
        template = ScholarshipContractTemplatePayload()
        institutional = _build_selected_scholarship_contract_pdf(
            scholarship_item(),
            "I002510602026",
            date(2026, 8, 28),
            "INSTITUCIONAL",
            template,
        )
        program = _build_selected_scholarship_contract_pdf(
            scholarship_item(),
            "I002510602026",
            date(2026, 8, 28),
            "PROGRAMA",
            template,
        )

        institutional_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(institutional)).pages
        )
        program_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(program)).pages
        )
        self.assertIn("CLÁUSULA DÉCIMA SEGUNDA", institutional_text)
        self.assertIn("PROYECCIÓN DE LA BECA", program_text)
        self.assertNotEqual(institutional, program)


if __name__ == "__main__":
    unittest.main()
