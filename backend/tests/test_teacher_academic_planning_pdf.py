import unittest
from io import BytesIO

from pypdf import PdfReader

from app.routers.portal_academico import AcademicPlanningPayload, _teacher_academic_planning_pdf


class TeacherAcademicPlanningPdfTests(unittest.TestCase):
    def make_payload(self, document_type: str, **overrides: object) -> AcademicPlanningPayload:
        return AcademicPlanningPayload.model_validate({
            "document_type": document_type,
            "codigo_periodos": [1060],
            "codigo_materia": "VGA-ID-2023-119",
            "paralelo": "A",
            "unidades": [{
                "nombre": "Unidad 1",
                "temas": [{
                    "tema": "Presentación",
                    "semana": 1,
                    "horas_docencia": 3,
                    "horas_practica": 1,
                    "horas_autonomo": 2,
                }],
            }],
            **overrides,
        })

    def render(self, payload: AcademicPlanningPayload) -> PdfReader:
        return PdfReader(BytesIO(_teacher_academic_planning_pdf(
            payload,
            {"docente": "Docente de prueba"},
            {
                "nombre_materia": "Inglés",
                "nombre_carrera": "Administración",
                "cod_materia": "VGA-ID-2023-119",
                "detalle_periodo": "C1-2026-PC",
                "semestre": 6,
            },
        )))

    def test_cover_and_overview_start_on_separate_pages_for_both_documents(self) -> None:
        for document_type in ("pea", "silabo"):
            with self.subTest(document_type=document_type):
                pdf = self.render(self.make_payload(
                    document_type,
                    horas_docencia=32,
                    horas_autonomo=76,
                    horas_practica=48,
                ))
                cover = pdf.pages[0].extract_text()
                overview = pdf.pages[1].extract_text()
                self.assertIn("CONTROL DE CAMBIOS", cover)
                self.assertNotIn("PROGRAMA DE ESTUDIOS DE ASIGNATURA", cover)
                self.assertIn("PROGRAMA DE ESTUDIOS DE ASIGNATURA", overview)
                self.assertIn("Docencia:", overview)
                self.assertIn("32", overview)
                self.assertIn("76", overview)
                self.assertIn("48", overview)

    def test_older_payloads_keep_topic_totals(self) -> None:
        overview = self.render(self.make_payload("pea")).pages[1].extract_text()
        for value in ("Docencia:", "3", "Trabajo Autónomo", "2", "Prácticas Aprendizaje", "1"):
            self.assertIn(value, overview)


if __name__ == "__main__":
    unittest.main()
