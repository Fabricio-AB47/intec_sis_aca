import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader

from app.routers.preinscription import (
    ScholarshipContractGeneratePayload,
    ScholarshipContractPreviewPayload,
    ScholarshipContractTemplatePayload,
    _build_program_scholarship_contract_pdf,
    _build_selected_scholarship_contract_pdf,
    _build_scholarship_contract_pdf,
    _canonical_scholarship_contract_format,
    _combined_scholarship_seeds,
    _exclude_english_scholarship_items,
    _is_english_career,
    _scholarship_relation_key,
    _scholarship_contract_base_number,
    _scholarship_contract_clauses,
    _scholarship_contract_generation_selection,
    _scholarship_contract_initial,
    _scholarship_contract_preview_item,
    _scholarship_contract_scope,
    get_scholarship_contract_template,
    list_scholarship_contract_candidates,
    preview_scholarship_contract,
)
from app.core.security import SessionUser
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
    def test_scholarship_sources_are_related_by_normalized_name(self) -> None:
        seeds = _combined_scholarship_seeds(
            [("Beca Intec", 10.0, 100.0), ("Suzuki", 100.0, 100.0)],
            [
                ("Beca Intec", 25.0, 25.0),
                ("Susuki", 100.0, 100.0),
                ("Beca deportiva", 75.0, 75.0),
                ("Ninguno", 0.0, 0.0),
            ],
        )

        self.assertEqual(
            seeds,
            [
                ("Beca Intec", 10.0, 100.0),
                ("Suzuki", 100.0, 100.0),
                ("Beca deportiva", 75.0, 75.0),
            ],
        )
        self.assertEqual(_scholarship_relation_key("Beca Susuki"), "SUZUKI")

    @patch(
        "app.routers.preinscription._scholarship_configurations",
        return_value=[{"nombre": "Beca Intec"}, {"nombre": "Beca Mintel"}],
    )
    @patch(
        "app.routers.preinscription._scholarship_contract_candidates",
        return_value=[{"tipo_beca": "Beca Intec", "codigo_periodo": "1060"}],
    )
    def test_contract_filters_include_configured_types_without_candidates(
        self,
        _candidates_mock: object,
        _configurations_mock: object,
    ) -> None:
        response = list_scholarship_contract_candidates(
            SessionUser(login="admin", rol="ADMINISTRADOR"),
        )

        self.assertEqual(response["tipos_beca"], ["Beca Intec", "Beca Mintel"])

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
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 595.28, delta=0.1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.height), 841.89, delta=0.1)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("CONTRATO DE BECA - No.", text)
        self.assertIn("ESTUDIANTE DE PRUEBA", text)
        self.assertIn(contract_number, text)
        self.assertIn("BECA INTEC", text)
        self.assertIn("C1-2026-PC", text)
        self.assertIn("Resolución No. 002-CR-INTEC-2024", text)
        self.assertIn("CLÁUSULA SEGUNDA.- OBJETIVO ESPECÍFICO", text)
        self.assertIn("DATOS BECA", text)
        self.assertIn("CLÁUSULA TERCERA.- MONTO Y RUBROS DE LA BECA", text)
        self.assertIn("CLÁUSULA TERCERA.- DURACIÓN", text)
        self.assertIn("CLÁUSULA DÉCIMA SEGUNDA.- ACEPTACIÓN Y RATIFICACIÓN", text)
        self.assertIn("Correo INTEC para notificaciones", text)
        self.assertEqual(text.count("Ingeniero JAIME RODER ORTEGA PEREIRA, MGT."), 1)
        self.assertIn("Ing. JAIME RODER ORTEGA PEREIRA, MGT.", text)
        self.assertIn("BECARIO/A – C.C.: 0706442670", text)
        self.assertEqual(text.count("CLÁUSULA TERCERA"), 2)
        self.assertIn("La renovación de la beca estará", text)
        self.assertIn("no requerirá la suscripción de uno nuevo", text)

    def test_scholarship_number_starts_with_the_first_significant_letter(self) -> None:
        self.assertEqual(_scholarship_contract_initial("Beca INTEC"), "I")
        self.assertEqual(_scholarship_contract_initial("Beca MINTEL"), "M")
        self.assertEqual(_scholarship_contract_initial("Futuro Femenino"), "F")

        number = _scholarship_contract_base_number(
            scholarship_item(tipo_beca="Beca INTEC", beca_id=25, codigo_periodo="1060"),
            date(2026, 8, 27),
        )
        self.assertEqual(number, "I002510602026")

    def test_contract_identifies_the_period_and_renewal_conditions(self) -> None:
        content = _build_scholarship_contract_pdf(
            scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
            "I002510602026",
            date(2026, 8, 27),
        )

        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        self.assertIn("MAYO-SEPTIEMBRE 2026", text)
        self.assertIn("La renovación de la beca estará", text)
        self.assertIn("Dirección de Bienestar del INTEC", text)

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

    def test_contract_generation_accepts_an_editable_tax_incentive_template(self) -> None:
        payload = ScholarshipContractGeneratePayload(
            beca_ids=[25],
            codigo_periodo="1060",
            formato_contrato="INCENTIVOS_TRIBUTARIOS",
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

        self.assertEqual(payload.formato_contrato, "INCENTIVOS_TRIBUTARIOS")
        self.assertEqual(payload.plantilla.programa, "Programa institucional de permanencia académica")
        self.assertEqual(len(payload.plantilla.proyeccion), 1)

    def test_contract_preview_uses_sample_data_without_registering_a_contract(self) -> None:
        payload = ScholarshipContractPreviewPayload(
            codigo_periodo="1060",
            tipo_beca="Beca INTEC",
            periodo="C1-2026-PC",
            plantilla={
                "titulo_contrato": "CONTRATO PARA VISTA PREVIA",
                "introduccion_institucional": "Documento de {ESTUDIANTE} para {PERIODO}.",
                "clausulas_institucionales": [],
            },
        )

        item = _scholarship_contract_preview_item(payload)
        response = preview_scholarship_contract(
            payload,
            SessionUser(login="admin", rol="ADMINISTRADOR"),
        )

        self.assertEqual(item["estudiante"], "ESTUDIANTE DE VISTA PREVIA")
        self.assertEqual(item["codigo_periodo"], "1060")
        self.assertEqual(response.media_type, "application/pdf")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("inline", response.headers["content-disposition"])

    def test_contract_template_returns_independent_defaults_for_both_formats(self) -> None:
        user = SessionUser(login="admin", rol="ADMINISTRADOR")

        scholarship = get_scholarship_contract_template(user, "BECA")
        tax_incentive = get_scholarship_contract_template(user, "INCENTIVOS_TRIBUTARIOS")

        self.assertEqual(scholarship["titulo_contrato"], "CONTRATO DE BECA")
        self.assertEqual(scholarship["proyeccion"], [])
        self.assertIn("[[TABLA_DATOS]]", scholarship["texto_completo"])
        self.assertIn("[[FIRMAS]]", scholarship["texto_completo"])
        self.assertNotIn("[[TABLA_PROYECCION]]", scholarship["texto_completo"])
        self.assertEqual(
            tax_incentive["titulo_contrato"],
            "CONTRATO DE BECA",
        )
        self.assertIn("[[TABLA_DATOS]]", tax_incentive["texto_completo"])
        self.assertIn("[[TABLA_PROYECCION]]", tax_incentive["texto_completo"])
        self.assertIn("[[FIRMAS]]", tax_incentive["texto_completo"])
        self.assertEqual(
            [row["rubro"] for row in tax_incentive["proyeccion"]],
            ["Matrícula y arancel", "Ayuda económica"],
        )

    def test_legacy_contract_formats_are_mapped_to_the_current_two_types(self) -> None:
        self.assertEqual(_canonical_scholarship_contract_format("INSTITUCIONAL"), "BECA")
        self.assertEqual(_canonical_scholarship_contract_format("PROGRAMA"), "INCENTIVOS_TRIBUTARIOS")
        self.assertEqual(_canonical_scholarship_contract_format("BECA"), "BECA")
        legacy_payload = ScholarshipContractGeneratePayload(
            beca_ids=[25],
            codigo_periodo="1060",
            formato_contrato="PROGRAMA",
        )
        self.assertEqual(legacy_payload.formato_contrato, "INCENTIVOS_TRIBUTARIOS")
        schema = ScholarshipContractGeneratePayload.model_json_schema()
        self.assertEqual(
            schema["properties"]["formato_contrato"]["enum"],
            ["BECA", "INCENTIVOS_TRIBUTARIOS"],
        )

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
                    "rubro": "Ayuda económica",
                    "periodicidad": "$ 187,50 durante el período adjudicado",
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
            rotulos_tabla={
                "nombres": "Persona beneficiaria",
                "rubro": "Concepto financiado",
                "periodicidad_rubro": "Cobertura",
            },
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
        self.assertIn("CONTRATO DE BECA No.", text)
        self.assertNotIn("CONTRATO DE BECA DE PROGRAMA", text)
        self.assertIn("INFORMACIÓN PERSONALIZADA", text)
        self.assertIn("DETALLE PERSONALIZADO", text)
        self.assertIn("Persona beneficiaria", text)
        self.assertIn("Concepto financiado", text)
        self.assertIn("Cobertura", text)
        self.assertIn("Programa institucional de permanencia académica", text)
        self.assertIn("Arancel académico", text)
        self.assertIn("Ayuda económica", text)
        self.assertIn("Ambato", text)
        self.assertIn("Ing. JAIME RODER ORTEGA PEREIRA, MGT.", text)
        self.assertIn("INTRODUCCIÓN EDITADA PARA ESTUDIANTE DE PRUEBA EN Ambato", text)
        self.assertIn("CLÁUSULA PERSONALIZADA", text)
        self.assertIn("BECA INTEC se aplica durante MAYO-SEPTIEMBRE 2026", " ".join(text.split()))
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
            rotulos_tabla={
                "becario": "Persona beneficiaria:",
                "beneficio": "Beneficio concedido:",
                "numero_contrato": "Contrato No.",
                "identificacion_firma": "Identificación:",
            },
        )
        content = _build_scholarship_contract_pdf(
            scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
            "I002510602026",
            date(2026, 8, 28),
            template,
        )

        reader = PdfReader(BytesIO(content))
        self.assertEqual(len(reader.pages), 1)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        normalized_text = " ".join(text.split())
        self.assertIn("CONTRATO DE BECA", normalized_text)
        self.assertNotIn("ACUERDO INSTITUCIONAL EDITADO", normalized_text)
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
        self.assertIn("Persona beneficiaria:", normalized_text)
        self.assertIn("Beneficio concedido:", normalized_text)
        self.assertIn("Identificación:", normalized_text)

    def test_both_contract_formats_use_the_complete_editable_text_and_keep_the_title_fixed(self) -> None:
        cases = [
            (
                "BECA",
                "[[TABLA_DATOS]]",
                "CUERPO INSTITUCIONAL TOTALMENTE EDITADO",
            ),
            (
                "INCENTIVOS_TRIBUTARIOS",
                "[[TABLA_DATOS]]\n\n[[TABLA_PROYECCION]]",
                "CUERPO DE INCENTIVOS TOTALMENTE EDITADO",
            ),
        ]
        for contract_format, table_markers, custom_body in cases:
            with self.subTest(contract_format=contract_format):
                template = ScholarshipContractTemplatePayload(
                    titulo_contrato="TÍTULO QUE NO DEBE APLICARSE",
                    texto_completo=(
                        f"{custom_body} PARA {{ESTUDIANTE}}.\n\n"
                        "CLÁUSULA ÚNICA EDITADA.-\n"
                        "Este es todo el texto contractual del período {PERIODO}.\n\n"
                        f"{table_markers}\n\n"
                        "CIERRE PERSONALIZADO PARA {CONTRATO}.\n\n"
                        "[[FIRMAS]]"
                    ),
                )
                content = _build_selected_scholarship_contract_pdf(
                    scholarship_item(periodo="C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026"),
                    "I002510602026",
                    date(2026, 8, 28),
                    contract_format,
                    template,
                )

                text = " ".join(
                    "\n".join(
                        page.extract_text() or ""
                        for page in PdfReader(BytesIO(content)).pages
                    ).split()
                )
                self.assertIn("CONTRATO DE BECA", text)
                self.assertNotIn("TÍTULO QUE NO DEBE APLICARSE", text)
                self.assertIn(custom_body, text)
                self.assertIn("ESTUDIANTE DE PRUEBA", text)
                self.assertIn("CLÁUSULA ÚNICA EDITADA", text)
                self.assertIn("CIERRE PERSONALIZADO PARA I002510602026", text)
                self.assertIn("DATOS BECA", text)
                self.assertIn("Ing. JAIME RODER ORTEGA PEREIRA, MGT.", text)
                if contract_format == "INCENTIVOS_TRIBUTARIOS":
                    self.assertIn("PROYECCIÓN DE LA BECA", text)

    def test_complete_text_restores_required_structures_when_their_markers_are_removed(self) -> None:
        content = _build_scholarship_contract_pdf(
            scholarship_item(),
            "I002510602026",
            date(2026, 8, 28),
            ScholarshipContractTemplatePayload(
                texto_completo="TEXTO CONTRACTUAL SIN MARCADORES ESTRUCTURALES.",
            ),
        )

        text = " ".join(
            "\n".join(
                page.extract_text() or ""
                for page in PdfReader(BytesIO(content)).pages
            ).split()
        )
        self.assertIn("TEXTO CONTRACTUAL SIN MARCADORES ESTRUCTURALES", text)
        self.assertIn("DATOS BECA", text)
        self.assertIn("BECARIO/A", text)
        self.assertNotIn("[[TABLA_DATOS]]", text)
        self.assertNotIn("[[FIRMAS]]", text)

    def test_selected_contract_builder_dispatches_both_formats(self) -> None:
        template = ScholarshipContractTemplatePayload()
        institutional = _build_selected_scholarship_contract_pdf(
            scholarship_item(),
            "I002510602026",
            date(2026, 8, 28),
            "BECA",
            template,
        )
        program = _build_selected_scholarship_contract_pdf(
            scholarship_item(),
            "I002510602026",
            date(2026, 8, 28),
            "INCENTIVOS_TRIBUTARIOS",
            template,
        )

        institutional_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(institutional)).pages
        )
        program_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(program)).pages
        )
        institutional_reader = PdfReader(BytesIO(institutional))
        program_reader = PdfReader(BytesIO(program))
        self.assertEqual(len(institutional_reader.pages), 1)
        self.assertEqual(len(program_reader.pages), 1)
        self.assertAlmostEqual(float(institutional_reader.pages[0].mediabox.width), 595.28, delta=0.1)
        self.assertAlmostEqual(float(institutional_reader.pages[0].mediabox.height), 841.89, delta=0.1)
        self.assertAlmostEqual(float(program_reader.pages[0].mediabox.width), 612.0, delta=0.1)
        self.assertAlmostEqual(float(program_reader.pages[0].mediabox.height), 792.0, delta=0.1)
        self.assertIn("CLÁUSULA DÉCIMA SEGUNDA", institutional_text)
        self.assertIn("PROYECCIÓN DE LA BECA", program_text)
        self.assertIn("Matrícula y arancel", program_text)
        self.assertIn("Ayuda económica", program_text)
        self.assertIn("CLÁUSULA TERCERA.- PLAZO DEL CONTRATO", program_text)
        self.assertIn("CLÁUSULA CUARTA.- ENTREGA DE RECURSOS Y FORMA DE PAGO", program_text)
        self.assertIn("5.1. OBLIGACIONES DEL INTEC", program_text)
        self.assertIn("5.2. OBLIGACIONES DEL/LA BECARIO/A", program_text)
        self.assertIn("CLÁUSULA SÉPTIMA.- ACEPTACIÓN Y RATIFICACIÓN", program_text)
        self.assertNotEqual(institutional, program)


if __name__ == "__main__":
    unittest.main()
