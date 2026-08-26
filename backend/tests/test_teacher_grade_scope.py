import unittest
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from pypdf import PdfReader
from pydantic import ValidationError
from fastapi import HTTPException

from app.routers.legacy_reports import (
    _ACTIVE_GRADE_STUDENTS_SQL,
    QUERY_BUILDERS,
    REPORTS,
    ReportGradeUpdatePayload,
    _grade_condition,
    _notas_carrera_materia_query,
    _weighted_grade_partial,
    _weighted_homologation_grade,
    update_student_grade,
)
from app.core.security import SessionUser
from app.routers.portal_academico import (
    AdminGradeCourseBatchPayload,
    AdminGradeCourseSelectionPayload,
    TeacherGradePayload,
    _admin_grade_completion,
    _build_teacher_student_grade_report_pdf,
    _courses_with_enrolled_students,
    _grade_result,
    _group_teacher_courses,
    _pdf_pages_as_compliance_evidence,
    _parse_teacher_contract_text,
    _pdf_signature_target_above_text,
    _signature_stamp_layout,
    _resolve_admin_grade_course_selections,
    _signed_teacher_documents_archive,
    _store_signed_teacher_documents_onedrive,
    _student_grade_report_pdf,
    _teacher_compliance_model_pdf,
    _teacher_course_students_for_report,
    _teacher_signed_documents_folder,
    _weighted_regular_partial,
    teacher_course_students,
    teacher_courses,
    teacher_profile,
    teacher_subject_students,
    teacher_save_grades,
)
from app.services.grade_calculation import (
    calculate_homologation_grade_with_recovery,
    calculate_regular_grade_with_recovery,
    regular_final_with_recovery,
)


def _course(career: str, period: str, students: int = 1) -> dict:
    return {
        "cod_anio_basica": career,
        "nombre_carrera": f"Carrera {career}",
        "codigo_periodo": period,
        "detalle_periodo": f"Periodo {period}",
        "periodo_orden": int(period),
        "codigo_materia": "101",
        "cod_materia": "VGA-CG-2023-06",
        "nombre_materia": "Materia comun",
        "paralelo": "A",
        "cod_jornada": "2",
        "es_homologacion": False,
        "total_estudiantes": students,
    }


def _selection(course: dict) -> AdminGradeCourseSelectionPayload:
    return AdminGradeCourseSelectionPayload(
        codigo_periodo=int(course["codigo_periodo"]),
        cod_anio_basica=int(course["cod_anio_basica"]),
        codigo_materia=course["cod_materia"],
        paralelo=course["paralelo"],
        cod_jornada=int(course["cod_jornada"]),
    )


class SignedTeacherDocumentsArchiveTests(unittest.TestCase):
    @patch("app.routers.portal_academico._assert_pdf_signature_field")
    def test_archive_contains_the_three_signed_documents(self, assert_signature: MagicMock):
        report = b"%PDF-1.4\ninforme"
        grades = b"%PDF-1.4\nnotas"
        contract = b"%PDF-1.4\ncontrato"

        archive_bytes = _signed_teacher_documents_archive(report, grades, contract)

        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    "informe-cumplimiento-firmado.pdf",
                    "reporte-notas-secretaria-firmado.pdf",
                    "contrato-docente-firmado.pdf",
                ],
            )
            self.assertEqual(archive.read("contrato-docente-firmado.pdf"), contract)
        self.assertEqual(
            assert_signature.call_args_list,
            [
                unittest.mock.call(report, "FirmaDocente"),
                unittest.mock.call(grades, "FirmaDocenteReporteNotas"),
                unittest.mock.call(contract, "FirmaDocenteContratoInforme"),
            ],
        )

    @patch("app.routers.portal_academico._assert_pdf_signature_field")
    def test_archive_rejects_a_non_pdf_document(self, _assert_signature: MagicMock):
        with self.assertRaisesRegex(HTTPException, "contrato docente"):
            _signed_teacher_documents_archive(
                b"%PDF-1.4\ninforme",
                b"%PDF-1.4\nnotas",
                b"contenido invalido",
            )

    @patch("app.routers.portal_academico._assert_pdf_signature_field")
    def test_archive_includes_invoice_xml_and_ride(self, _assert_signature: MagicMock):
        xml_content = b'<?xml version="1.0" encoding="UTF-8"?><factura />'
        ride_content = b"%PDF-1.4\nride"

        archive_bytes = _signed_teacher_documents_archive(
            b"%PDF-1.4\ninforme",
            b"%PDF-1.4\nnotas",
            b"%PDF-1.4\ncontrato",
            [
                {
                    "filename": "factura-electronica.xml",
                    "original_name": "factura-001.xml",
                    "content": xml_content,
                    "content_type": "application/xml",
                    "document_type": "FACTURA_XML",
                },
                {
                    "filename": "ride-factura.pdf",
                    "original_name": "ride-001.pdf",
                    "content": ride_content,
                    "content_type": "application/pdf",
                    "document_type": "RIDE",
                },
            ],
        )

        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(archive.read("factura-electronica.xml"), xml_content)
            self.assertEqual(archive.read("ride-factura.pdf"), ride_content)
            self.assertEqual(len(archive.namelist()), 5)

    def test_onedrive_folder_is_scoped_under_docentes(self):
        path = _teacher_signed_documents_folder(
            {
                "codigo_doc": "31",
                "cedula": "1724-036-536",
                "nombre": "BORJA HERNÁNDEZ FABRICIO ALEXANDER",
            },
            subject_code="VGA-ES-2023-90",
            subject_name="Inteligencia Artificial",
            period_codes=["C1-2026-PC", "C1-2026-PC", "C2-2026-PB"],
            signed_at=datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc),
        )

        self.assertTrue(
            path.startswith(
                "DOCENTES/BORJA HERNÁNDEZ FABRICIO ALEXANDER - 1724036536/"
            )
        )
        self.assertIn(
            "/DOCUMENTOS FIRMADOS/Inteligencia Artificial - VGA-ES-2023-90/",
            path,
        )
        self.assertIn("/C1-2026-PC - C2-2026-PB/", path)
        self.assertTrue(path.endswith("FIRMA 20260817-123000-000000 UTC"))

    @patch("app.routers.portal_academico.delete_graph_document_item")
    @patch("app.routers.portal_academico.upload_graph_document_bytes")
    @patch("app.routers.portal_academico.ensure_graph_document_folder")
    def test_onedrive_storage_uploads_three_signed_documents(
        self,
        ensure_folder: MagicMock,
        upload: MagicMock,
        delete_item: MagicMock,
    ) -> None:
        ensure_folder.return_value = {"id": "folder-1"}
        upload.side_effect = [{"id": f"item-{index}"} for index in range(1, 4)]

        stored = _store_signed_teacher_documents_onedrive(
            identity={"codigo_doc": "31", "cedula": "1724036536", "nombre": "DOCENTE"},
            compliance_pdf=b"informe",
            grades_pdf=b"notas",
            contract_pdf=b"contrato",
            subject_code="VGA-90",
            subject_name="Materia",
            period_codes=["1060"],
        )

        self.assertEqual(len(stored["items"]), 3)
        self.assertEqual(upload.call_count, 3)
        self.assertTrue(upload.call_args_list[0].args[0].endswith("/informe-cumplimiento-firmado.pdf"))
        self.assertTrue(upload.call_args_list[2].args[0].endswith("/contrato-docente-firmado.pdf"))
        delete_item.assert_not_called()

    @patch("app.routers.portal_academico.delete_graph_document_item")
    @patch("app.routers.portal_academico.upload_graph_document_bytes")
    @patch("app.routers.portal_academico.ensure_graph_document_folder")
    def test_onedrive_storage_rolls_back_partial_uploads(
        self,
        ensure_folder: MagicMock,
        upload: MagicMock,
        delete_item: MagicMock,
    ) -> None:
        ensure_folder.return_value = {"id": "folder-1"}
        upload.side_effect = [{"id": "item-1"}, RuntimeError("Graph unavailable")]

        with self.assertRaisesRegex(RuntimeError, "Graph unavailable"):
            _store_signed_teacher_documents_onedrive(
                identity={"codigo_doc": "31", "cedula": "1724036536", "nombre": "DOCENTE"},
                compliance_pdf=b"informe",
                grades_pdf=b"notas",
                contract_pdf=b"contrato",
            )

        self.assertEqual(
            delete_item.call_args_list,
            [unittest.mock.call("item-1"), unittest.mock.call("folder-1")],
        )

    @patch("app.routers.portal_academico.delete_graph_document_item")
    @patch("app.routers.portal_academico.upload_graph_document_bytes")
    @patch("app.routers.portal_academico.ensure_graph_document_folder")
    def test_onedrive_storage_uploads_invoice_backups_with_signed_documents(
        self,
        ensure_folder: MagicMock,
        upload: MagicMock,
        delete_item: MagicMock,
    ) -> None:
        ensure_folder.return_value = {"id": "folder-1"}
        upload.side_effect = [{"id": f"item-{index}"} for index in range(1, 6)]

        stored = _store_signed_teacher_documents_onedrive(
            identity={"codigo_doc": "31", "cedula": "1724036536", "nombre": "DOCENTE"},
            compliance_pdf=b"informe",
            grades_pdf=b"notas",
            contract_pdf=b"contrato",
            invoice_documents=[
                {
                    "filename": "factura-electronica.xml",
                    "original_name": "factura-001.xml",
                    "content": b"<factura />",
                    "content_type": "application/xml",
                    "document_type": "FACTURA_XML",
                },
                {
                    "filename": "ride-factura.pdf",
                    "original_name": "ride-001.pdf",
                    "content": b"%PDF-1.4\nride",
                    "content_type": "application/pdf",
                    "document_type": "RIDE",
                },
            ],
        )

        self.assertEqual(len(stored["items"]), 5)
        self.assertEqual(upload.call_count, 5)
        self.assertTrue(upload.call_args_list[3].args[0].endswith("/factura-electronica.xml"))
        self.assertTrue(upload.call_args_list[4].args[0].endswith("/ride-factura.pdf"))
        self.assertEqual(stored["items"][3]["tipo_documento"], "FACTURA_XML")
        self.assertEqual(stored["items"][4]["tipo_documento"], "RIDE")
        self.assertTrue(stored["same_folder"])
        uploaded_folders = {
            str(call.args[0]).rsplit("/", 1)[0]
            for call in upload.call_args_list
        }
        self.assertEqual(uploaded_folders, {stored["folder_path"]})
        self.assertTrue(
            all(item["folder_path"] == stored["folder_path"] for item in stored["items"])
        )
        delete_item.assert_not_called()

    @patch("app.routers.portal_academico.ensure_graph_document_folder")
    def test_onedrive_storage_rejects_incomplete_invoice_backups_before_creating_folder(
        self,
        ensure_folder: MagicMock,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "exactamente una factura XML y un RIDE PDF"):
            _store_signed_teacher_documents_onedrive(
                identity={"codigo_doc": "31", "cedula": "1724036536", "nombre": "DOCENTE"},
                compliance_pdf=b"informe",
                grades_pdf=b"notas",
                contract_pdf=b"contrato",
                invoice_documents=[
                    {
                        "filename": "factura-electronica.xml",
                        "content": b"<factura />",
                        "content_type": "application/xml",
                        "document_type": "FACTURA_XML",
                    }
                ],
            )

        ensure_folder.assert_not_called()


class TeacherContractAnalysisTests(unittest.TestCase):
    def test_regular_contract_extracts_number_subject_dates_and_value(self):
        analysis = _parse_teacher_contract_text(
            """
            CONTRATO: No. 0202. SEM.MAY2025-JUL2025.VGA-ES-2023-83. A
            cédula de ciudadanía Nº 1724036536
            asignatura de VGA-ES-2023-83
            para el período que inicia el 12/MAY/2025 y termina el 06/JUL/2025
            valor total del contrato (US$ 80,00)
            """
        )

        self.assertEqual(analysis["numero_contrato"], "0202. SEM.MAY2025-JUL2025.VGA-ES-2023-83. A")
        self.assertEqual(analysis["cedula"], "1724036536")
        self.assertEqual(analysis["codigo_materia"], "VGA-ES-2023-83")
        self.assertEqual(analysis["modalidad_academica"], "REGULAR")
        self.assertEqual(analysis["fecha_inicio"], "2025-05-12")
        self.assertEqual(analysis["fecha_fin"], "2025-07-06")
        self.assertEqual(analysis["valor_total"], 80.0)

    def test_homologation_contract_extracts_spanish_dates(self):
        analysis = _parse_teacher_contract_text(
            """
            CONTRATO: No. 512 JUN 2026 - JUL2026/VGA-CG-2023-71. HOMO.05 2025
            ciudadanía Nº1724036536
            asignatura de VGA-CG-2023-71 SISTEMAS OPERATIVOS
            para el período que inicia el 15/JUN/2026 y termina el 05/JUL/2026
            valor total de (US$ 40)
            """
        )

        self.assertEqual(analysis["numero_contrato"], "512 JUN 2026 - JUL2026/VGA-CG-2023-71. HOMO.05 2025")
        self.assertEqual(analysis["codigo_materia"], "VGA-CG-2023-71")
        self.assertEqual(analysis["modalidad_academica"], "HOMOLOGACION")
        self.assertEqual(analysis["fecha_inicio"], "2026-06-15")
        self.assertEqual(analysis["fecha_fin"], "2026-07-05")
        self.assertEqual(analysis["valor_total"], 40.0)

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_profile_exposes_system_phone(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchone.return_value = SimpleNamespace(
            codigo_doc="31",
            cedula="1724036536",
            docente="Docente prueba",
            correo="docente@intec.edu.ec",
            correo_personal="docente@example.com",
            telefono="022345678",
            movil="0991234567",
            tipo_docente="T",
            perfil="DOCENTE",
        )
        get_connection.return_value = connection

        result = teacher_profile(
            SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            )
        )

        self.assertEqual(result["teacher"]["telefono"], "022345678")
        self.assertEqual(result["teacher"]["movil"], "0991234567")
        sql = cursor.execute.call_args.args[0]
        self.assertIn("d.telefono", sql)
        self.assertIn("d.movil", sql)


class TeacherGradeScopeTests(unittest.TestCase):
    def test_admin_can_select_up_to_three_periods_of_the_same_type(self):
        available = [
            _course("10", "1028", 8),
            _course("10", "1029", 9),
            _course("10", "1030", 10),
        ]

        selected = _resolve_admin_grade_course_selections(
            available,
            [_selection(course) for course in available],
        )

        self.assertEqual([course["codigo_periodo"] for course in selected], ["1028", "1029", "1030"])

    def test_admin_period_selection_includes_all_careers_in_that_period(self):
        administration = _course("10", "1030", 12)
        finance = _course("20", "1030", 18)

        selected = _resolve_admin_grade_course_selections(
            [administration, finance],
            [_selection(administration)],
        )

        self.assertEqual({course["cod_anio_basica"] for course in selected}, {"10", "20"})
        self.assertEqual(sum(course["total_estudiantes"] for course in selected), 30)

    def test_admin_cannot_select_the_same_period_for_multiple_careers(self):
        administration = _course("10", "1030", 12)
        finance = _course("20", "1030", 18)

        with self.assertRaises(HTTPException) as context:
            _resolve_admin_grade_course_selections(
                [administration, finance],
                [_selection(administration), _selection(finance)],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("período diferente", context.exception.detail)

    def test_admin_cannot_mix_regular_and_homologation_periods(self):
        regular = _course("10", "1029", 9)
        homologation = _course("10", "1030", 10)
        homologation["es_homologacion"] = True
        homologation["tipo_periodo"] = "H"

        with self.assertRaises(HTTPException) as context:
            _resolve_admin_grade_course_selections(
                [regular, homologation],
                [_selection(regular), _selection(homologation)],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("No se pueden mezclar", context.exception.detail)

    def test_admin_period_payload_rejects_a_fourth_period(self):
        courses = [_selection(_course("10", str(1028 + index), 8)) for index in range(4)]

        with self.assertRaises(ValidationError):
            AdminGradeCourseBatchPayload(courses=courses)

    def test_admin_courses_ignore_assignments_without_students(self):
        courses = _courses_with_enrolled_students([
            _course("10", "1030", 0),
            _course("10", "1031", 12),
        ])

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["codigo_periodo"], "1031")

    def test_teacher_courses_merge_careers_by_common_subject_code(self):
        grouped = _group_teacher_courses([
            _course("10", "1030", 12),
            _course("20", "1030", 18),
        ])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(set(grouped[0]["cod_anio_basicas"]), {"10", "20"})
        self.assertEqual(grouped[0]["cod_materia"], "VGA-CG-2023-06")
        self.assertEqual(grouped[0]["total_estudiantes"], 30)
        self.assertEqual(len(grouped[0]["asignaciones"]), 2)
        self.assertEqual(len(grouped[0]["alcances_periodo"]), 2)

    def test_regular_periods_only_group_inside_same_career(self):
        grouped = _group_teacher_courses([
            _course("10", "1029", 8),
            _course("10", "1030", 9),
        ])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["codigo_periodos"], ["1030", "1029"])
        self.assertEqual(grouped[0]["total_estudiantes"], 17)
        self.assertEqual(len(grouped[0]["asignaciones"]), 1)
        self.assertEqual(grouped[0]["asignaciones"][0]["codigo_periodos"], ["1030", "1029"])
        self.assertEqual(
            {scope["codigo_periodo"] for scope in grouped[0]["alcances_periodo"]},
            {"1029", "1030"},
        )

    def test_teacher_courses_keep_different_common_subject_codes_separate(self):
        first = _course("10", "1030", 12)
        second = _course("20", "1030", 18)
        second["cod_materia"] = "VGA-CG-2023-07"

        grouped = _group_teacher_courses([first, second])

        self.assertEqual(len(grouped), 2)
        self.assertEqual(
            {item["cod_materia"] for item in grouped},
            {"VGA-CG-2023-06", "VGA-CG-2023-07"},
        )

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_course_catalog_counts_only_active_students(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchall.return_value = []
        get_connection.return_value = connection

        teacher_courses(
            SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            )
        )

        sql = cursor.execute.call_args.args[0]
        self.assertIn("INNER JOIN dbo.DATOS_ESTUD de_active", sql)
        self.assertIn("de_active.Estado", sql)
        self.assertIn("N'A', N'ACTIVO', N'ACTIVA'", sql)

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_grade_roster_only_loads_active_students(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchall.return_value = []
        get_connection.return_value = connection

        teacher_course_students(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            codigo_periodo=[1030],
            codigo_materia="VGA-CG-2023-06",
            paralelo="A",
            cod_anio_basica=10,
            cod_jornada=2,
        )

        sql = cursor.execute.call_args.args[0]
        self.assertIn("de.Estado", sql)
        self.assertIn("N'A', N'ACTIVO', N'ACTIVA'", sql)

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_grade_roster_filters_student_inside_assigned_course(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchall.return_value = []
        get_connection.return_value = connection

        teacher_course_students(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            codigo_periodo=[1030],
            codigo_materia="VGA-CG-2023-06",
            paralelo="A",
            cod_anio_basica=10,
            cod_jornada=2,
            buscar="María 0102",
        )

        args = cursor.execute.call_args.args
        sql = args[0]
        parameters = args[1:]
        self.assertIn("de.Apellidos_nombre", sql)
        self.assertIn("de.Cedula_Est", sql)
        self.assertIn("de.codigo_estud", sql)
        self.assertIn("Latin1_General_100_CI_AI LIKE", sql)
        self.assertIn("María 0102", parameters)
        self.assertGreaterEqual(parameters.count("%María 0102%"), 3)

    @patch("app.routers.portal_academico.teacher_course_students")
    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_subject_students_queries_every_career_scope(
        self,
        teacher_courses_mock: MagicMock,
        course_students_mock: MagicMock,
    ):
        grouped = _group_teacher_courses([
            _course("10", "1030", 12),
            _course("20", "1030", 18),
        ])
        teacher_courses_mock.return_value = {"total": 1, "items": grouped}

        def student_response(**kwargs):
            career = kwargs["cod_anio_basica"]
            return {
                "items": [{
                    "codigo_estud": career,
                    "codigo_periodo": 1030,
                    "cod_anio_basica": career,
                    "codigo_materia": 101,
                    "paralelo": "A",
                    "num_matricula": 1,
                    "num_grupo": 1,
                    "nombre_carrera": f"Carrera {career}",
                    "nombre_estudiante": f"Estudiante {career}",
                }]
            }

        course_students_mock.side_effect = student_response
        result = teacher_subject_students(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            codigo_materia="VGA-CG-2023-06",
            tipo_periodo="R",
            codigo_periodo=[1030],
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["asignaciones_consultadas"], 2)
        self.assertEqual(
            {call.kwargs["cod_anio_basica"] for call in course_students_mock.call_args_list},
            {10, 20},
        )
        self.assertTrue(
            all(call.kwargs["codigo_materia"] == "VGA-CG-2023-06" for call in course_students_mock.call_args_list)
        )
        self.assertTrue(all(call.kwargs["codigo_periodo"] == [1030] for call in course_students_mock.call_args_list))

    @patch("app.routers.portal_academico.teacher_subject_students")
    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_report_aggregates_one_subject_across_attached_careers(
        self,
        teacher_courses_mock: MagicMock,
        subject_students_mock: MagicMock,
    ):
        grouped = _group_teacher_courses([
            _course("10", "1029", 8),
            _course("20", "1029", 7),
            _course("10", "1030", 9),
            _course("20", "1030", 6),
        ])
        teacher_courses_mock.return_value = {"total": 1, "items": grouped}
        subject_students_mock.return_value = {
            "items": [
                {
                    "codigo_estud": "101",
                    "codigo_periodo": "1030",
                    "cod_anio_basica": "10",
                    "codigo_materia": "101",
                    "paralelo": "A",
                    "num_matricula": "1",
                    "num_grupo": 1,
                }
            ]
        }

        result = _teacher_course_students_for_report(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            period_codes=[1029, 1030],
            subject_filter="VGA-CG-2023-06",
            parallel="*",
        )

        self.assertEqual(len(result), 1)
        subject_students_mock.assert_called_once()
        self.assertEqual(subject_students_mock.call_args.kwargs["tipo_periodo"], "R")
        self.assertEqual(set(subject_students_mock.call_args.kwargs["codigo_periodo"]), {1029, 1030})

    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_regular_subject_accepts_at_most_two_periods(self, teacher_courses_mock: MagicMock):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        with self.assertRaises(HTTPException) as context:
            teacher_subject_students(
                current_user=user,
                codigo_materia="VGA-CG-2023-06",
                tipo_periodo="R",
                codigo_periodo=[1028, 1029, 1030],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("dos periodos regulares", context.exception.detail)
        teacher_courses_mock.assert_not_called()

    @patch("app.routers.portal_academico.teacher_course_students")
    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_regular_subject_combines_two_selected_periods_by_unique_code(
        self,
        teacher_courses_mock: MagicMock,
        course_students_mock: MagicMock,
    ):
        grouped = _group_teacher_courses([
            _course("10", "1029", 8),
            _course("10", "1030", 9),
            _course("20", "1029", 7),
            _course("20", "1030", 6),
        ])
        teacher_courses_mock.return_value = {"total": 1, "items": grouped}
        course_students_mock.return_value = {"items": []}

        result = teacher_subject_students(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            codigo_materia="VGA-CG-2023-06",
            tipo_periodo="R",
            codigo_periodo=[1029, 1030],
        )

        self.assertEqual(result["codigo_periodos"], [1029, 1030])
        self.assertEqual(result["asignaciones_consultadas"], 2)
        self.assertEqual(course_students_mock.call_count, 2)
        self.assertTrue(
            all(set(call.kwargs["codigo_periodo"]) == {1029, 1030} for call in course_students_mock.call_args_list)
        )

    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_homologation_subject_requires_one_independent_period(self, teacher_courses_mock: MagicMock):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        with self.assertRaises(HTTPException) as context:
            teacher_subject_students(
                current_user=user,
                codigo_materia="VGA-CG-2023-06",
                tipo_periodo="H",
                codigo_periodo=[1029, 1030],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("un único período", context.exception.detail)
        teacher_courses_mock.assert_not_called()

    @patch("app.routers.portal_academico.teacher_course_students")
    @patch("app.routers.portal_academico.teacher_courses")
    def test_teacher_homologation_subject_only_queries_selected_period(
        self,
        teacher_courses_mock: MagicMock,
        course_students_mock: MagicMock,
    ):
        first = _course("10", "1029", 8)
        second = _course("10", "1030", 9)
        for course in (first, second):
            course["es_homologacion"] = True
            course["tipo_periodo"] = "H"
        grouped = _group_teacher_courses([first, second])
        teacher_courses_mock.return_value = {"total": 1, "items": grouped}
        course_students_mock.return_value = {"items": []}

        result = teacher_subject_students(
            current_user=SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
            codigo_materia="VGA-CG-2023-06",
            tipo_periodo="H",
            codigo_periodo=[1030],
        )

        self.assertEqual(result["codigo_periodos"], [1030])
        self.assertEqual(result["asignaciones_consultadas"], 1)
        course_students_mock.assert_called_once()
        self.assertEqual(course_students_mock.call_args.kwargs["codigo_periodo"], [1030])

    def test_admin_grade_query_uses_exact_course_and_teacher(self):
        sql, params = _notas_carrera_materia_query(
            100,
            {
                "periodo": "1030",
                "carrera": "10",
                "buscar": "%estudiante%",
                "estado": None,
                "anio": None,
                "genero": None,
            },
        )

        self.assertIn("ce.cod_anio_Basica = pe.Cod_AnioBasica", sql)
        self.assertIn("dbo.CARRERAXDOCENTE", sql)
        self.assertIn("docente_responsable", sql)
        self.assertIn("ce.Num_Matricula", sql)
        self.assertIn("ce.NumGrupo", sql)
        self.assertIn("WHEN calculo.promedio_final >= 7 THEN 'APROBADO'", sql)
        self.assertNotIn("LTRIM(RTRIM(ce.caprueba)) AS condicion", sql)
        self.assertNotIn("pe.TipoMatricula", sql)
        self.assertIn("de.Estado", sql)
        self.assertIn("N'A', N'ACTIVO', N'ACTIVA'", sql)
        self.assertIn("de.Apellidos_nombre LIKE ?", sql)
        self.assertIn("ce.codigo_estud) = ?", sql)
        self.assertNotIn("de.Cedula_Est LIKE ?", sql)
        self.assertNotIn("pe.Nomb_Materia)) LIKE ?", sql)
        self.assertEqual(params, ["%estudiante%", "%estudiante%", None, None, None, None, None, None])

    def test_active_grade_roster_uses_dashboard_source_and_keeps_each_active_enrollment(self):
        self.assertIn("FROM dbo.TOTALESTUDMATRICCNE reporte", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("FROM matricula_cne_catalogada cne", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("WHERE cne.estado_codigo = 'A'", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("grade_summary", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("carrera_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("active.tipo_matricula", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("AS registro_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("COUNT(*) AS matriculas_activas", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("UPPER(LTRIM(RTRIM(active.carrera)))", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("MAX(active.carrera) AS carrera", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("GROUP BY active.registro_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("ORDER BY MAX(active.estudiante)", _ACTIVE_GRADE_STUDENTS_SQL)

    def test_grade_catalog_only_requests_student_name(self):
        self.assertEqual(REPORTS["notas_carrera_materia"]["filters"], ["buscar"])

    def test_grade_status_uses_global_seven_point_threshold(self):
        self.assertEqual(_grade_result(None), "PENDIENTE")
        self.assertEqual(_grade_result(6.99), "REPROBADO")
        self.assertEqual(_grade_result(7), "APROBADO")
        self.assertEqual(_grade_result(10), "APROBADO")

    def test_regular_partial_uses_legacy_30_30_40_weights(self):
        self.assertEqual(_weighted_regular_partial(9.5, 8, 6.5), 7.85)

    def test_recovery_replaces_only_one_tied_lowest_component(self):
        calculation = calculate_regular_grade_with_recovery(
            ((10, 10, 10), (7, 7, 10), (10, 10, 10)),
            9,
        )

        self.assertEqual(calculation.replacement, (1, 0))
        self.assertEqual(calculation.partials, (10, 8.8, 10))
        self.assertEqual(calculation.final, 9.6)

    def test_recovery_uses_component_grade_instead_of_lowest_partial_average(self):
        partials = ((6, 10, 10), (7, 7, 7), (10, 10, 10))
        calculation = calculate_regular_grade_with_recovery(partials, 10)

        self.assertEqual(calculation.replacement, (0, 0))
        self.assertEqual(calculation.partials, (10, 7, 10))
        self.assertEqual(regular_final_with_recovery(partials, 10), 9)

    def test_recovery_does_not_lower_a_component_or_complete_missing_grades(self):
        complete = ((6, 10, 10), (7, 7, 7), (10, 10, 10))
        unchanged = calculate_regular_grade_with_recovery(complete, 5)
        incomplete = calculate_regular_grade_with_recovery(
            ((10, 10, 10), (7, None, 7), (8, 8, 8)),
            9,
        )

        self.assertIsNone(unchanged.replacement)
        self.assertEqual(unchanged.final, 8.6)
        self.assertIsNone(incomplete.replacement)
        self.assertEqual(incomplete.partials, (10, None, 8))
        self.assertIsNone(incomplete.final)

    def test_homologation_recovery_replaces_only_one_lowest_component(self):
        calculation = calculate_homologation_grade_with_recovery(7, 7, 9)

        self.assertEqual(calculation.replacement, 0)
        self.assertEqual(calculation.components, (9, 7))
        self.assertEqual(calculation.final, 7.8)

    def test_homologation_recovery_does_not_lower_or_complete_grades(self):
        unchanged = calculate_homologation_grade_with_recovery(8, 9, 7)
        incomplete = calculate_homologation_grade_with_recovery(8, None, 10)

        self.assertIsNone(unchanged.replacement)
        self.assertEqual(unchanged.final, 8.6)
        self.assertIsNone(incomplete.replacement)
        self.assertIsNone(incomplete.final)

    def test_grade_payloads_reject_values_outside_zero_to_ten(self):
        base = {
            "codigo_estud": 800,
            "cod_anio_basica": 10,
            "codigo_periodo": 1030,
            "codigo_materia": 101,
            "paralelo": "A",
            "num_matricula": 2,
            "num_grupo": 3,
        }
        with self.assertRaises(ValidationError):
            ReportGradeUpdatePayload(**base, p1_tareas=10.01)
        with self.assertRaises(ValidationError):
            TeacherGradePayload(**base, recuperacion=-0.01)

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_update_recalculates_loaded_grades_from_one_lowest_component(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchone.return_value = (1,)
        cursor.rowcount = 1
        get_connection.return_value = connection

        result = teacher_save_grades(
            TeacherGradePayload(
                codigo_estud=800,
                cod_anio_basica=10,
                codigo_periodo=1030,
                codigo_materia=101,
                paralelo="A",
                num_matricula=2,
                num_grupo=3,
                p1_tareas=10,
                p1_proyectos=9,
                p1_examen=9,
                p2_tareas=7,
                p2_proyectos=7,
                p2_examen=10,
                p3_tareas=10,
                p3_proyectos=10,
                p3_examen=10,
                recuperacion=9.23,
            ),
            SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
        )

        update_call = cursor.execute.call_args_list[1]
        update_sql = update_call.args[0]
        update_params = update_call.args[1:]
        self.assertIn("promP1 = ?", update_sql)
        self.assertIn("promP2 = ?", update_sql)
        self.assertIn("promP3 = ?", update_sql)
        self.assertIn("Recuperacion = ?", update_sql)
        self.assertIn("INNER JOIN dbo.DATOS_ESTUD AS de_active", update_sql)
        self.assertIn("de_active.Estado", update_sql)
        assignment_sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("cxd.cod_Anio_Basica", assignment_sql)
        self.assertNotIn("cxd.cod_AnioBasica", assignment_sql)
        self.assertEqual(update_params[3], 9.3)
        self.assertEqual(update_params[7], 8.87)
        self.assertEqual(update_params[11], 10)
        self.assertEqual(update_params[12], 9.39)
        self.assertEqual(update_params[13], 9.23)
        self.assertEqual(update_params[14], 9.39)
        self.assertEqual(result["affected_rows"], 1)
        connection.commit.assert_called_once_with()

    def test_administrative_grade_calculation_matches_teacher_rules(self):
        self.assertEqual(_weighted_grade_partial(10, 8, 7), 8.2)
        self.assertEqual(_weighted_homologation_grade(8, 9), 8.6)
        self.assertEqual(_grade_condition(None), (None, "PENDIENTE"))
        self.assertEqual(_grade_condition(6.99), ("R", "REPROBADO"))
        self.assertEqual(_grade_condition(7), ("A", "APROBADO"))

    @patch("app.routers.legacy_reports.get_connection")
    def test_administrative_update_uses_complete_enrollment_key(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchone.return_value = (1,)
        cursor.rowcount = 1
        get_connection.return_value = connection

        result = update_student_grade(
            ReportGradeUpdatePayload(
                codigo_estud=800,
                cod_anio_basica=10,
                codigo_periodo=1030,
                codigo_materia=101,
                paralelo="A",
                num_matricula=2,
                num_grupo=3,
                p1_tareas=10,
                p1_proyectos=8,
                p1_examen=7,
                p2_tareas=8,
                p2_proyectos=8,
                p2_examen=8,
                p3_tareas=9,
                p3_proyectos=9,
                p3_examen=9,
                recuperacion=10,
            ),
            SessionUser(login="academico", nombres="Prueba", rol="ACADEMICO"),
        )

        update_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("codigo_estud", update_sql)
        self.assertIn("cod_anio_Basica", update_sql)
        self.assertIn("codigo_periodo", update_sql)
        self.assertIn("codigo_materia", update_sql)
        self.assertIn("Num_Matricula", update_sql)
        self.assertIn("NumGrupo", update_sql)
        self.assertIn("INNER JOIN dbo.DATOS_ESTUD AS de_active", update_sql)
        self.assertIn("de_active.Estado", update_sql)
        self.assertEqual(result["affected_rows"], 1)
        self.assertEqual(result["promedio_final"], 8.8)
        self.assertEqual(result["condicion"], "APROBADO")
        connection.commit.assert_called_once_with()

    def test_admin_grade_completion_distinguishes_missing_partial_and_complete(self):
        self.assertEqual(_admin_grade_completion({"es_homologacion": False}), "SIN_CALIFICAR")
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": False, "p1_examen": 8}),
            "EN_PROCESO",
        )
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": True, "teoria_homo": 9}),
            "EN_PROCESO",
        )
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": False, "promedio_final": 7}),
            "COMPLETA",
        )

    def test_secretary_report_does_not_expand_student_academic_history(self):
        source = [{
            "codigo_estud": "800",
            "codigo_periodo": "1030",
            "cod_anio_basica": "10",
            "nombre_estudiante": "ESTUDIANTE PRUEBA",
            "cedula": "1106128380",
            "nombre_carrera": "Carrera 10",
            "nombre_materia": "Materia asignada",
            "promedio_final": 9.7,
            "creditos": 4,
        }, {
            "codigo_estud": "801",
            "codigo_periodo": "1030",
            "cod_anio_basica": "10",
            "nombre_estudiante": "SEGUNDO ESTUDIANTE",
            "cedula": "1106128381",
            "nombre_carrera": "Carrera 10",
            "nombre_materia": "Materia asignada",
            "promedio_final": 6.5,
            "creditos": 4,
        }]

        with patch(
            "app.routers.portal_academico._student_grade_report_rows",
            side_effect=AssertionError("El reporte no debe ampliar el historial academico"),
        ):
            pdf = _student_grade_report_pdf(
                {"docente": "DOCENTE PRUEBA", "cedula": "1106128380"},
                {
                    "nombre_materia": "Materia asignada",
                    "detalle_periodo": "Periodo 1030",
                    "paralelo": "A",
                    "cod_jornada": "2",
                    "semestre": 3,
                    "horas": 144,
                },
                source,
            )

        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(pdf))
        report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Reporte de notas", report_text)
        self.assertIn("NOTA", report_text)
        self.assertIn("Promedio", report_text)
        self.assertIn("Firma del docente", report_text)
        self.assertIn("ESTUDIANTE PRUEBA", report_text)
        self.assertIn("SEGUNDO ESTUDIANTE", report_text)
        self.assertNotIn("APROBADO", report_text)
        self.assertNotIn("REPROBADO", report_text)
        self.assertEqual(reader.pages[0].mediabox.width, 612)
        self.assertEqual(reader.pages[0].mediabox.height, 792)

        signature_page, signature_box = _pdf_signature_target_above_text(pdf, "Firma del docente")
        self.assertEqual(signature_page, len(reader.pages) - 1)
        self.assertGreater(signature_box[1], 18)
        self.assertGreater(signature_box[2], signature_box[0])
        self.assertGreater(signature_box[3], signature_box[1])
        self.assertLessEqual(signature_box[3], 792 - 18)
        self.assertAlmostEqual(signature_box[2] - signature_box[0], 126)
        self.assertAlmostEqual(signature_box[3] - signature_box[1], 48)

        qr_size, font_size, separation = _signature_stamp_layout(signature_box)
        self.assertLessEqual(qr_size, 36)
        self.assertLessEqual(font_size, 5.5)
        self.assertGreaterEqual(separation, 1)

    def test_signature_stamp_scales_to_each_document_area(self):
        notes = _signature_stamp_layout((243, 90, 369, 138))
        compliance = _signature_stamp_layout((72, 458, 262, 516))
        contract = _signature_stamp_layout((335, 42, 565, 112))

        self.assertLess(notes[0], compliance[0])
        self.assertLess(notes[1], compliance[1])
        self.assertLessEqual(compliance[0], contract[0])
        self.assertLessEqual(compliance[1], contract[1])

    def test_secretary_report_builder_keeps_only_selected_students(self):
        students = [
            {
                "codigo_estud": "800",
                "codigo_periodo": "1030",
                "nombre_estudiante": "ESTUDIANTE SELECCIONADO",
                "nombre_carrera": "Desarrollo de Software",
                "detalle_periodo": "Periodo 1030",
                "codigo_materia": "101",
                "cod_materia": "VGA-CG-2023-06",
                "nombre_materia": "Materia asignada",
                "paralelo": "A",
            },
            {
                "codigo_estud": "801",
                "codigo_periodo": "1030",
                "nombre_estudiante": "ESTUDIANTE NO SELECCIONADO",
                "nombre_carrera": "Desarrollo de Software",
                "detalle_periodo": "Periodo 1030",
                "codigo_materia": "101",
                "cod_materia": "VGA-CG-2023-06",
                "nombre_materia": "Materia asignada",
                "paralelo": "A",
            },
        ]

        with (
            patch("app.routers.portal_academico._teacher_code", return_value=31),
            patch(
                "app.routers.portal_academico.teacher_profile",
                return_value={"teacher": {"docente": "DOCENTE PRUEBA", "cedula": "1106128380"}},
            ),
            patch("app.routers.portal_academico._teacher_course_students_for_report", return_value=students),
            patch("app.routers.portal_academico._teacher_course_report_meta", return_value={}),
            patch("app.routers.portal_academico._student_grade_report_pdf", return_value=b"%PDF-test") as pdf_mock,
        ):
            pdf, filename = _build_teacher_student_grade_report_pdf(
                current_user=MagicMock(),
                codigo_periodo=[1030],
                codigo_materia="VGA-CG-2023-06",
                paralelo="A",
                codigo_estud=[800],
            )

        report_students = pdf_mock.call_args.args[2]
        self.assertEqual(pdf, b"%PDF-test")
        self.assertEqual([item["codigo_estud"] for item in report_students], ["800"])
        self.assertIn("reporte-notas-secretaria", filename)

    def test_compliance_report_uses_selected_students_and_graph_recordings(self):
        students = [{
            "codigo_estud": "800",
            "codigo_periodo": "1030",
            "nombre_estudiante": "ESTUDIANTE SELECCIONADO",
            "cedula": "1106128380",
            "nombre_carrera": "Desarrollo de Software",
            "detalle_periodo": "Periodo 1030",
            "promedio_final": 8.75,
        }]

        pdf = _teacher_compliance_model_pdf(
            {
                "docente": "DOCENTE PRUEBA",
                "cedula": "1106128381",
                "correo": "docente@intec.edu.ec",
            },
            {
                "nombre_materia": "Materia asignada",
                "detalle_periodo": "Periodo 1030",
                "paralelo": "A",
                "jornada": "Nocturna",
                "semestre": 3,
                "horas": 144,
            },
            students,
            {},
            {
                "fecha_inicio": "2026-05-01",
                "fecha_fin": "2026-09-30",
                "telefono": "0999999999",
                "actualizaciones": "Sin cambios.",
                "observaciones": "",
                "teams_recordings": [{
                    "team_id": "team-1",
                    "team_name": "Equipo de prueba",
                    "recording_id": "recording-1",
                    "name": "Clase grabada 01.mp4",
                    "date": "21/07/2026",
                    "start_hour": "19:00",
                    "end_hour": "20:02",
                    "call_duration": "01:02:00",
                    "recording_duration": "01:01:32",
                    "modified_by": "DOCENTE PRUEBA",
                    "web_url": "https://example.sharepoint.com/recording",
                    "source": "Microsoft Graph",
                }],
            },
            evidence_images=[],
        )

        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(pdf))
        report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertNotIn("Asistencias", report_text)
        self.assertIn("ESTUDIANTE SELECCIONADO", report_text)
        self.assertIn("8.75", report_text)
        self.assertIn("Clases grabadas en TEAMS", report_text)
        self.assertIn("21/07/2026", report_text)
        self.assertIn("Clase grabada 01.mp4", report_text)
        self.assertIn("01:01:32", report_text)
        self.assertIn("formato Secretaría", report_text)
        self.assertIn("documento independiente", report_text)
        self.assertNotIn("captura de pantalla del reporte de notas", report_text)

    def test_signed_grade_report_is_embedded_as_images_in_compliance_pdf(self):
        teacher = {
            "docente": "DOCENTE PRUEBA",
            "cedula": "1106128381",
            "correo": "docente@intec.edu.ec",
        }
        meta = {
            "nombre_materia": "Materia asignada",
            "detalle_periodo": "Periodo 1030",
            "paralelo": "A",
            "jornada": "Nocturna",
            "semestre": 3,
            "horas": 144,
        }
        students = [{
            "codigo_estud": "800",
            "codigo_periodo": "1030",
            "nombre_estudiante": "ESTUDIANTE SELECCIONADO",
            "cedula": "1106128380",
            "nombre_carrera": "Desarrollo de Software",
            "detalle_periodo": "Periodo 1030",
            "promedio_final": 8.75,
        }]
        signed_grade_pdf = _student_grade_report_pdf(teacher, meta, students)
        grade_images = _pdf_pages_as_compliance_evidence(signed_grade_pdf)

        self.assertGreaterEqual(len(grade_images), 1)
        self.assertTrue(grade_images[0]["content"].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("reporte de notas firmado", grade_images[0]["label"].lower())

        compliance_pdf = _teacher_compliance_model_pdf(
            teacher,
            meta,
            students,
            {},
            {
                "fecha_inicio": "2026-05-01",
                "fecha_fin": "2026-09-30",
                "telefono": "0999999999",
                "actualizaciones": "Sin cambios.",
                "observaciones": "",
                "teams_recordings": [],
            },
            evidence_images=grade_images,
        )

        reader = PdfReader(BytesIO(compliance_pdf))
        report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertEqual(len(reader.pages), 4 + len(grade_images))
        self.assertIn("Reporte de notas firmado - página 1", report_text)
        self.assertIn("Imagen generada automáticamente", report_text)
        self.assertIn("Reporte de notas firmado electrónicamente", report_text)

    @patch("pypdfium2.PdfDocument")
    def test_signed_grade_report_renders_signature_forms_and_annotations(self, pdf_document: MagicMock):
        document = MagicMock()
        document.__len__.return_value = 1
        page = MagicMock()
        bitmap = MagicMock()
        image = MagicMock()
        bitmap.to_pil.return_value.convert.return_value = image
        image.save.side_effect = lambda stream, **_kwargs: stream.write(b"\x89PNG\r\n\x1a\n")
        page.render.return_value = bitmap
        document.__getitem__.return_value = page
        pdf_document.return_value = document

        images = _pdf_pages_as_compliance_evidence(b"%PDF-1.7\nfirmado")

        document.init_forms.assert_called_once_with()
        page.render.assert_called_once_with(
            scale=1.5,
            may_draw_forms=True,
            draw_annots=True,
        )
        self.assertTrue(images[0]["content"].startswith(b"\x89PNG"))

    def test_admin_grade_report_remains_registered(self):
        self.assertIn("notas_carrera_materia", REPORTS)
        self.assertIs(QUERY_BUILDERS["notas_carrera_materia"], _notas_carrera_materia_query)
        self.assertEqual(set(REPORTS), set(QUERY_BUILDERS))


if __name__ == "__main__":
    unittest.main()
