from io import BytesIO
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from pypdf import PdfReader

from app.routers import teacher_evaluation as evaluation


class TeacherEvaluationDocumentHeaderTests(unittest.TestCase):
    def test_documents_omit_redundant_institution_line_and_keep_report_information(self):
        report = {
            "periodo": "101",
            "periodo_detalle": "C1-2023",
            "weights": [],
            "teachers": [{
                "teacher": {"codigo_doc": "12", "docente": "Docente de prueba", "cedula_doc": "1712345678"},
                "rows": [{"Cod_Materia": "31", "materia": "Matemática", "carrera": "Software", "Paralelo": "PB1",
                          "Promedio_Autoevaluacion": 95, "Puntaje_Final_360": 95}],
            }],
        }
        for flow in ("all", "student", "auto_docente", "par_docente", "academico_docente"):
            for document_type in ("certificado", "consolidado", "resumen", "detalle"):
                with self.subTest(flow=flow, document_type=document_type), patch.object(evaluation, "_template_page_image", return_value=None):
                    document = {**report, "flow": flow, "document_type": document_type}
                    pdf = evaluation._build_teacher_grade_pdf(document)
                    reader = PdfReader(BytesIO(pdf))
                    self.assertEqual(len(reader.pages), 1)
                    text = " ".join(" ".join(page.extract_text() for page in reader.pages).split())
                    self.assertNotIn("INSTITUTO TECNOLÓGICO SUPERIOR INTEC", text)
                    self.assertIn(evaluation._report_document_title(document), text)
                    self.assertIn("QUITO - ECUADOR", text)
                    self.assertIn("Documento #", text)
                    self.assertIn("Docente de prueba", text)
                    self.assertIn("1712345678", text)
                    self.assertIn("C1-2023", text)
                    self.assertIn("Matemática", text)
                    self.assertIn("Software", text)
                    self.assertIn("Coordinación Académica", text)


def detailed_report(subject_count=1, question_count=40, teacher_count=1):
    rows = [{
        "Cod_Materia": str(31 + subject), "materia": f"Materia completa {subject + 1}",
        "carrera": "Desarrollo de Software", "Paralelo": "PB1",
        "Promedio_Autoevaluacion": 95, "Puntaje_Final_360": 95,
        "items_calificacion": [{
            "NoPregunta": str(question + 1),
            "Detalle_Preg": f"Indicador {subject + 1}-{question + 1}: Planifica y desarrolla las actividades de aprendizaje de manera adecuada.",
            "Dimension_Global": f"Dimensión {question // 10 + 1}",
            "Total_Evaluaciones": 1, "Total_Respuestas": 1, "Promedio_Item": 95,
        } for question in range(question_count)],
        "dimensiones": [{"Tipo_Evaluacion": "Autoevaluación", "Dimension_Global": "Dimensión completa",
                          "Total_Evaluaciones": 1, "Total_Respuestas": question_count, "Promedio_Dimension": 95}],
    } for subject in range(subject_count)]
    return {
        "periodo": "101", "periodo_detalle": "C1-2023", "flow": "auto_docente", "document_type": "detalle", "weights": [],
        "teachers": [{"teacher": {"codigo_doc": str(12 + index), "docente": f"Docente completo {index + 1}", "cedula_doc": f"171234567{index}"},
                      "rows": rows} for index in range(teacher_count)],
    }


class TeacherEvaluationSinglePageTests(unittest.TestCase):
    def test_empty_report_keeps_one_page_and_its_empty_state(self):
        with patch.object(evaluation, "_template_page_image", return_value=None):
            pdf = PdfReader(BytesIO(evaluation._build_teacher_grade_pdf({"periodo": "101", "teachers": []})))
        self.assertEqual(len(pdf.pages), 1)
        self.assertIn("No existen calificaciones registradas", pdf.pages[0].extract_text())

    def test_all_questions_and_report_sections_fit_one_a4_page_without_truncation(self):
        for subjects, questions in ((1, 40), (1, 80), (2, 40)):
            with self.subTest(subjects=subjects, questions=questions), patch.object(evaluation, "_template_page_image", return_value=None):
                report = detailed_report(subjects, questions)
                pdf = PdfReader(BytesIO(evaluation._build_teacher_grade_pdf(report)))
            self.assertEqual(len(pdf.pages), 1)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), evaluation.A4[0], places=3)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), evaluation.A4[1], places=3)
            text = " ".join(pdf.pages[0].extract_text().split())
            for header in ("Materia", "Dimensión", "Ítem de calificación", "Evaluaciones", "Respuestas", "Promedio"):
                self.assertIn(header, text)
            for subject in range(subjects):
                self.assertIn(f"Materia completa {subject + 1}", text)
                for question in range(questions):
                    self.assertIn(f"Indicador {subject + 1}-{question + 1}:", text)
            for section in ("Documento #", "DATOS DOCENTE", "MATRIZ DE COMPONENTES", "PUNTAJE FINAL",
                            "DETALLE POR ÍTEM DE CALIFICACIÓN", "DETALLE POR DIMENSIÓN", "Nota:", "Coordinación Académica"):
                self.assertIn(section, text)

    def test_multiple_teachers_keep_one_complete_page_each(self):
        with patch.object(evaluation, "_template_page_image", return_value=None):
            report = detailed_report(teacher_count=2)
            pdf = PdfReader(BytesIO(evaluation._build_teacher_grade_pdf(report)))
        self.assertEqual(len(pdf.pages), 2)
        for index, page in enumerate(pdf.pages):
            text = " ".join(page.extract_text().split())
            self.assertIn(f"Docente completo {index + 1}", text)
            self.assertIn("Indicador 1-40:", text)
            self.assertIn("Coordinación Académica", text)

    def test_massive_zip_contains_complete_single_page_documents(self):
        with patch.object(evaluation, "_template_page_image", return_value=None):
            archive_bytes = evaluation._build_teacher_grade_zip(detailed_report(teacher_count=2))
        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            for filename in archive.namelist():
                pdf = PdfReader(BytesIO(archive.read(filename)))
                self.assertEqual(len(pdf.pages), 1)
                self.assertIn("Indicador 1-40:", pdf.pages[0].extract_text())
