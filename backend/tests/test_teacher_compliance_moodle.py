import json
import unittest
from io import BytesIO

from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader

from app.routers.portal_academico import (
    _assert_teacher_compliance_generation_allowed,
    _moodle_planning_document_types,
    _moodle_grade_to_ten,
    _moodle_subject_code_similarity,
    _parse_teacher_moodle_resources,
    _safe_moodle_module_payload,
    _teacher_compliance_grade_validation,
    _teacher_compliance_model_pdf,
    _teacher_compliance_report_docx,
    _teacher_moodle_course_match,
    _teacher_moodle_email_match,
    _teacher_planning_moodle_document_rows,
)


class TeacherComplianceMoodleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = {
            "cod_materia": "VGA-ES-2023-90",
            "codigo_materia": "401",
            "nombre_materia": "Inteligencia Artificial 1",
            "nombre_carrera": "Desarrollo de Software",
            "detalle_periodo": "C1-2026-PC MAYO 2026 - SEPTIEMBRE 2026",
            "paralelo": "A",
            "jornada": "Nocturna",
            "semestre": 4,
            "horas": 144,
        }

    def test_course_match_requires_the_assigned_subject(self) -> None:
        course = {
            "id": 52,
            "fullname": (
                "VGA-ES-2023-90 - Inteligencia Artificial 1 - "
                "C1-2026-PC - Desarrollo de Software - Paralelo A"
            ),
            "shortname": "IA1-1034-A",
            "idnumber": "1034",
            "categoryname": "Desarrollo de Software",
        }

        matched = _teacher_moodle_course_match(course, self.meta, [1034])

        self.assertIsNotNone(matched)
        score, reasons = matched or (0, [])
        self.assertGreaterEqual(score, 100)
        self.assertIn("Código de asignatura", reasons)
        self.assertIn("Período académico", reasons)

        unrelated = dict(course, fullname="Contabilidad General - 1034", shortname="CONT-1034")
        self.assertIsNone(_teacher_moodle_course_match(unrelated, self.meta, [1034]))

    def test_course_match_accepts_controlled_subject_code_similarity(self) -> None:
        course = {
            "id": 53,
            "fullname": (
                "VGA-ES-2023-9O - Inteligencia Artificial 1 - "
                "C1-2026-PC - Desarrollo de Software"
            ),
            "shortname": "IA1-1034-A",
            "idnumber": "1034",
            "categoryname": "Desarrollo de Software",
        }

        matched = _teacher_moodle_course_match(course, self.meta, [1034])

        self.assertIsNotNone(matched)
        _, reasons = matched or (0, [])
        self.assertTrue(any(reason.startswith("Código de asignatura similar") for reason in reasons))

    def test_subject_code_similarity_accepts_a_compact_moodle_code(self) -> None:
        similarity, conflict = _moodle_subject_code_similarity(
            {"fullname": "VGAES20239O - Inteligencia Artificial 1"},
            self.meta["cod_materia"],
        )

        self.assertGreaterEqual(similarity, 0.90)
        self.assertFalse(conflict)

    def test_subject_code_similarity_rejects_a_compact_different_suffix(self) -> None:
        similarity, conflict = _moodle_subject_code_similarity(
            {"fullname": "VGAES202391 - Inteligencia Artificial 1"},
            self.meta["cod_materia"],
        )

        self.assertLess(similarity, 0.82)
        self.assertTrue(conflict)

    def test_course_match_rejects_a_different_numeric_subject_suffix(self) -> None:
        course = {
            "id": 54,
            "fullname": (
                "VGA-ES-2023-91 - Inteligencia Artificial 1 - "
                "C1-2026-PC - Desarrollo de Software"
            ),
            "shortname": "IA1-1034-A",
            "idnumber": "1034",
            "categoryname": "Desarrollo de Software",
        }

        self.assertIsNone(_teacher_moodle_course_match(course, self.meta, [1034]))

    def test_email_match_is_case_insensitive_and_reports_coverage(self) -> None:
        matches, coverage = _teacher_moodle_email_match(
            {"Estudiante.Uno@intec.edu.ec", "estudiante.dos@intec.edu.ec"},
            {"estudiante.uno@INTEC.EDU.EC", "externo@example.com"},
        )

        self.assertEqual(matches, 1)
        self.assertEqual(coverage, 50.0)

    def test_moodle_grade_is_normalized_to_ten(self) -> None:
        grade = _moodle_grade_to_ten(
            {
                "gradeitems": [
                    {
                        "itemtype": "course",
                        "graderaw": 80,
                        "grademin": 0,
                        "grademax": 100,
                    }
                ]
            }
        )

        self.assertEqual(grade, 8.0)

    def test_moodle_activity_grade_does_not_replace_missing_course_total(self) -> None:
        grade = _moodle_grade_to_ten(
            {
                "gradeitems": [
                    {
                        "itemtype": "mod",
                        "itemname": "Tarea parcial",
                        "graderaw": 10,
                        "grademin": 0,
                        "grademax": 10,
                    }
                ]
            }
        )

        self.assertIsNone(grade)

    def test_exact_ten_percent_failed_requires_justification(self) -> None:
        academic_records = []
        moodle_users = []
        moodle_grades = []
        for index in range(10):
            final_grade = 6.5 if index == 0 else 8.0
            academic_records.append(
                {
                    "codigo_estud": index + 1,
                    "cedula": f"11000000{index:02d}",
                    "nombre_estudiante": f"ESTUDIANTE {index + 1}",
                    "correo_intec_registro": f"estudiante{index + 1}@intec.edu.ec",
                    "nombre_carrera": "Desarrollo de Software",
                    "detalle_periodo": "C1-2026-PC",
                    "promedio_final": final_grade,
                }
            )
            moodle_users.append(
                {"id": index + 101, "email": f"estudiante{index + 1}@intec.edu.ec"}
            )
            moodle_grades.append(
                {
                    "userid": index + 101,
                    "gradeitems": [
                        {
                            "itemtype": "course",
                            "graderaw": final_grade,
                            "grademin": 0,
                            "grademax": 10,
                        }
                    ],
                }
            )

        validation = _teacher_compliance_grade_validation(
            academic_records,
            academic_records,
            {"id": 52, "fullname": "Curso de prueba"},
            moodle_users=moodle_users,
            moodle_user_grades=moodle_grades,
        )

        self.assertTrue(validation["can_generate"])
        self.assertEqual(validation["failed_count"], 1)
        self.assertEqual(validation["failed_percentage"], 10.0)
        self.assertTrue(validation["requires_justification"])
        with self.assertRaises(HTTPException) as context:
            _assert_teacher_compliance_generation_allowed(validation, "Muy corta")
        self.assertEqual(context.exception.status_code, 409)
        _assert_teacher_compliance_generation_allowed(
            validation,
            "El estudiante mantiene un plan académico de recuperación documentado.",
        )

    def test_zero_is_a_registered_failed_grade(self) -> None:
        student = {
            "codigo_estud": 1,
            "cedula": "1100000001",
            "nombre_estudiante": "ESTUDIANTE CERO",
            "correo_intec_registro": "cero@intec.edu.ec",
            "promedio_final": 0,
        }
        validation = _teacher_compliance_grade_validation(
            [student],
            [student],
            {"id": 52, "fullname": "Curso de prueba"},
            moodle_users=[{"id": 101, "email": "cero@intec.edu.ec"}],
            moodle_user_grades=[
                {
                    "userid": 101,
                    "gradeitems": [
                        {
                            "itemtype": "course",
                            "graderaw": 0,
                            "grademin": 0,
                            "grademax": 10,
                        }
                    ],
                }
            ],
        )

        self.assertEqual(validation["graded_records"], 1)
        self.assertEqual(validation["missing_academic_count"], 0)
        self.assertEqual(validation["failed_count"], 1)
        self.assertEqual(validation["moodle"]["verified_students"], 1)

    def test_missing_and_different_grades_block_generation(self) -> None:
        missing = {
            "codigo_estud": 1,
            "cedula": "1100000001",
            "nombre_estudiante": "SIN NOTA",
            "correo_intec_registro": "sin.nota@intec.edu.ec",
            "promedio_final": None,
        }
        different = {
            "codigo_estud": 2,
            "cedula": "1100000002",
            "nombre_estudiante": "NOTA DIFERENTE",
            "correo_intec_registro": "diferente@intec.edu.ec",
            "promedio_final": 8,
        }
        validation = _teacher_compliance_grade_validation(
            [missing, different],
            [missing, different],
            {"id": 52, "fullname": "Curso de prueba"},
            moodle_users=[
                {"id": 101, "email": "sin.nota@intec.edu.ec"},
                {"id": 102, "email": "diferente@intec.edu.ec"},
            ],
            moodle_user_grades=[
                {"userid": 101, "gradeitems": []},
                {
                    "userid": 102,
                    "gradeitems": [
                        {
                            "itemtype": "course",
                            "graderaw": 9,
                            "grademin": 0,
                            "grademax": 10,
                        }
                    ],
                },
            ],
        )

        self.assertFalse(validation["can_generate"])
        self.assertEqual(validation["missing_academic_count"], 1)
        self.assertEqual(len(validation["moodle"]["missing_grade_students"]), 1)
        self.assertEqual(len(validation["moodle"]["discrepancies"]), 1)
        with self.assertRaises(HTTPException):
            _assert_teacher_compliance_generation_allowed(validation, "")

    def test_selected_resource_payload_accepts_only_https_links(self) -> None:
        payload = [{
            "course_id": 52,
            "course_name": "Inteligencia Artificial 1",
            "section_id": 8,
            "section_name": "Unidad 1",
            "module_id": 71,
            "name": "Guía de aprendizaje",
            "module_type": "Archivo",
            "visible": True,
            "file_count": 1,
            "file_names": ["guia.pdf"],
            "web_url": "http://moodle.example.edu/mod/resource/view.php?id=71",
            "source": "Moodle",
        }]

        resources = _parse_teacher_moodle_resources(json.dumps(payload))

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["module_id"], 71)
        self.assertEqual(resources[0]["web_url"], "")

    def test_safe_resource_is_built_from_canonical_moodle_data(self) -> None:
        resource = _safe_moodle_module_payload(
            {"id": 52, "displayname": "Inteligencia Artificial 1"},
            {"id": 8, "name": "Unidad 1"},
            {
                "id": 71,
                "name": "Guía de aprendizaje",
                "modplural": "Archivos",
                "visible": 1,
                "uservisible": 1,
                "url": "https://moodle.example.edu/mod/resource/view.php?id=71",
                "contents": [
                    {"filename": "guia.pdf", "fileurl": "https://moodle.example.edu/token-privado"}
                ],
            },
        )

        self.assertEqual(resource["course_id"], 52)
        self.assertEqual(resource["file_names"], ["guia.pdf"])
        self.assertNotIn("fileurl", resource)
        self.assertTrue(resource["visible"])

    def test_planning_documents_are_detected_without_false_positives(self) -> None:
        document_types = _moodle_planning_document_types(
            "Planificación académica",
            "Documentos firmados",
            "PEA Inteligencia Artificial.pdf",
            "Sílabo Inteligencia Artificial.pdf",
        )

        self.assertEqual(set(document_types), {"pea", "silabo"})
        self.assertEqual(
            _moodle_planning_document_types("Unidad 1", "Presentación de la clase", "diapositivas.pdf"),
            [],
        )

    def test_planning_resources_expand_into_verifiable_documents(self) -> None:
        rows = _teacher_planning_moodle_document_rows([{
            "course_name": "Inteligencia Artificial 1",
            "section_name": "Planificación académica",
            "name": "PEA y sílabo firmados",
            "visible": True,
            "file_names": ["PEA firmado.pdf", "Silabo firmado.pdf"],
            "planning_document_types": ["pea", "silabo"],
            "web_url": "https://moodle.example.edu/mod/resource/view.php?id=71",
        }])

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["type_label"] for row in rows}, {"PEA", "Sílabo"})
        self.assertTrue(all(row["publication_status"] == "Publicado" for row in rows))
        self.assertTrue(all(row["signature_status"] == "Firmado" for row in rows))
        self.assertTrue(all(row["web_url"].startswith("https://") for row in rows))

    def test_compliance_pdf_lists_each_selected_moodle_resource(self) -> None:
        pdf = _teacher_compliance_model_pdf(
            {
                "docente": "DOCENTE PRUEBA",
                "cedula": "1106128381",
                "correo": "docente@intec.edu.ec",
            },
            self.meta,
            [],
            {},
            {
                "fecha_inicio": "2026-05-01",
                "fecha_fin": "2026-09-30",
                "telefono": "0999999999",
                "actualizaciones": "Sin cambios.",
                "observaciones": "",
                "moodle_resources": [{
                    "course_id": 52,
                    "course_name": "Inteligencia Artificial 1",
                    "section_id": 8,
                    "section_name": "Unidad 1",
                    "module_id": 71,
                    "name": "PEA y sílabo firmados",
                    "module_type": "Archivo",
                    "visible": True,
                    "file_count": 2,
                    "file_names": ["PEA firmado.pdf", "Silabo firmado.pdf"],
                    "planning_document_types": ["pea", "silabo"],
                    "web_url": "https://moodle.example.edu/mod/resource/view.php?id=71",
                    "source": "Moodle",
                }],
                "teams_recordings": [],
            },
            evidence_images=[],
        )

        reader = PdfReader(BytesIO(pdf))
        report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Documentos PEA/sílabo identificados automáticamente en Moodle", report_text)
        self.assertIn("2 documento(s) verificable(s)", report_text)
        self.assertIn("Recursos del aula virtual verificados en Moodle", report_text)
        self.assertIn("PEA y sílabo firmados", report_text)
        self.assertIn("Unidad 1", report_text)
        self.assertIn("PEA firmado.pdf", report_text)
        self.assertIn("Silabo firmado.pdf", report_text)
        self.assertIn("Publicado", report_text)
        self.assertIn("Firmado", report_text)

    def test_compliance_docx_lists_planning_documents_with_template_without_grid_style(self) -> None:
        docx = _teacher_compliance_report_docx(
            {
                "docente": "DOCENTE PRUEBA",
                "cedula": "1106128381",
                "correo": "docente@intec.edu.ec",
            },
            self.meta,
            [],
            {},
            {
                "fecha_inicio": "2026-05-01",
                "fecha_fin": "2026-09-30",
                "telefono": "0999999999",
                "actualizaciones": "Sin cambios.",
                "moodle_resources": [{
                    "course_name": "Inteligencia Artificial 1",
                    "section_name": "Planificación académica",
                    "name": "PEA y sílabo firmados",
                    "visible": True,
                    "file_names": ["PEA firmado.pdf", "Silabo firmado.pdf"],
                    "planning_document_types": ["pea", "silabo"],
                    "web_url": "https://moodle.example.edu/mod/resource/view.php?id=71",
                }],
            },
            evidence_images=[],
        )

        document = Document(BytesIO(docx))
        table_text = "\n".join(
            " | ".join(cell.text for cell in row.cells)
            for table in document.tables
            for row in table.rows
        )
        self.assertIn("PEA firmado.pdf", table_text)
        self.assertIn("Silabo firmado.pdf", table_text)
        self.assertIn("Publicado", table_text)
        self.assertIn("Firmado", table_text)


if __name__ == "__main__":
    unittest.main()
