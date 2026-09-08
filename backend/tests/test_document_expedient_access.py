import unittest
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.document_expedients import (
    _ACCESS,
    _REVIEW_ACCESS,
    _context_payload,
    _ensure_document_upload_actor,
    _ensure_document_upload_window,
    _ensure_teacher_practice_access,
    _institutional_expedient,
    _invoice_expedient,
    _validate_upload_filename,
)


class DocumentExpedientAccessTests(unittest.TestCase):
    def test_student_is_accepted_for_own_expedient(self) -> None:
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")

        self.assertIs(_ACCESS(student), student)

    def test_authorized_profiles_are_accepted(self) -> None:
        for role in ("DOCENTE", "ACADEMICO", "BIENESTAR", "SECRETARIA", "FINANCIERO", "ADMINISTRADOR"):
            with self.subTest(role=role):
                user = SessionUser(login="usuario@intec.edu.ec", rol=role)
                self.assertIs(_ACCESS(user), user)

    def test_teacher_cannot_use_the_global_student_search(self) -> None:
        teacher = SessionUser(login="docente@intec.edu.ec", rol="DOCENTE")

        with self.assertRaises(HTTPException) as context:
            _REVIEW_ACCESS(teacher)

        self.assertEqual(context.exception.status_code, 403)

    def test_teacher_access_requires_an_active_practice_assignment(self) -> None:
        teacher = SessionUser(
            login="docente@intec.edu.ec",
            email="docente@intec.edu.ec",
            codigo_doc=25,
            rol="DOCENTE",
        )
        expedient = {"module_code": "PRACTICAS", "origin_id": "42", "status": "EN PROCESO"}

        with (
            patch("app.routers.document_expedients.get_practices_connection") as get_connection,
            patch("app.routers.document_expedients._use_legacy_practices_schema", return_value=True),
            patch("app.routers.document_expedients._responsible_assignment") as assignment,
        ):
            cursor = get_connection.return_value.__enter__.return_value.cursor.return_value
            _ensure_teacher_practice_access(teacher, expedient, for_write=True)

        assignment.assert_called_once_with(cursor, 42, teacher, require_approval=False)

    def test_teacher_cannot_manage_other_document_modules(self) -> None:
        teacher = SessionUser(login="docente@intec.edu.ec", rol="DOCENTE")

        with self.assertRaises(HTTPException) as context:
            _ensure_teacher_practice_access(
                teacher,
                {"module_code": "TITULACION", "origin_id": "42"},
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_only_assigned_teacher_can_upload_practice_documents(self) -> None:
        expedient = {"module_code": "PRACTICAS", "origin_id": "42", "status": "EN PROCESO"}

        for role in ("ESTUDIANTE", "ACADEMICO", "ADMINISTRADOR"):
            with self.subTest(role=role), self.assertRaises(HTTPException) as context:
                _ensure_document_upload_actor(
                    SessionUser(login=f"{role.lower()}@intec.edu.ec", rol=role),
                    expedient,
                )
            self.assertEqual(context.exception.status_code, 403)

        teacher = SessionUser(login="docente@intec.edu.ec", rol="DOCENTE", codigo_doc=25)
        with patch("app.routers.document_expedients._ensure_teacher_practice_access") as access:
            _ensure_document_upload_actor(teacher, expedient)
        access.assert_called_once_with(teacher, expedient, for_write=True)

    def test_student_cannot_upload_official_documents_from_general_archive(self) -> None:
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")

        with self.assertRaises(HTTPException) as context:
            _ensure_document_upload_actor(
                student,
                {
                    "module_code": "FACTURACION",
                    "origin_id": "123",
                    "status": "DISPONIBLE",
                    "base_origin": "INTECBDD",
                    "table_origin": "DATOS_ESTUD",
                },
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_reviewer_can_upload_to_institutional_practice_archive(self) -> None:
        reviewer = SessionUser(login="secretaria@intec.edu.ec", rol="SECRETARIA")
        expedient = _institutional_expedient({"code": 123}, "PRACTICAS")

        _ensure_document_upload_actor(reviewer, expedient)

    def test_reviewer_context_enables_every_institutional_archive(self) -> None:
        reviewer = SessionUser(login="secretaria@intec.edu.ec", rol="SECRETARIA")
        profile = {
            "code": 100,
            "identification": "0102030405",
            "name": "ESTUDIANTE PRUEBA",
            "email": "estudiante@intec.edu.ec",
        }
        with patch(
            "app.routers.document_expedients.get_titulation_connection",
            side_effect=RuntimeError,
        ):
            expedients = [
                _institutional_expedient(profile, module)
                for module in (
                    "INGLES",
                    "TITULACION",
                    "PRACTICAS",
                    "VINCULACION",
                    "BECAS",
                    "SOLICITUDES",
                    "FACTURACION",
                    "SECRETARIA",
                )
            ]

        with (
            patch("app.routers.document_expedients._domain_expedients", return_value=expedients),
            patch("app.routers.document_expedients.list_documents", return_value=[]),
        ):
            context = _context_payload(profile, reviewer)

        self.assertEqual(len(context["expedients"]), 8)
        self.assertTrue(all(item["upload_enabled"] for item in context["expedients"]))
        self.assertTrue(all(item["document_types"] for item in context["expedients"]))

    def test_student_practice_context_is_read_only(self) -> None:
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")
        practice = {
            "module_code": "PRACTICAS",
            "module_name": "Prácticas preprofesionales",
            "origin_id": "42",
            "domain_expedient_id": 42,
            "expedient_code": "PPF-42",
            "status": "EN PROCESO",
            "document_types": [{"code": "CARTA_COMPROMISO", "name": "Carta compromiso"}],
            "upload_enabled": True,
        }
        profile = {
            "code": 100,
            "identification": "0102030405",
            "name": "ESTUDIANTE PRUEBA",
            "email": "estudiante@intec.edu.ec",
        }

        with (
            patch("app.routers.document_expedients._domain_expedients", return_value=[practice]),
            patch("app.routers.document_expedients.list_documents", return_value=[]),
        ):
            context = _context_payload(profile, student)

        expedient = next(item for item in context["expedients"] if item["module_code"] == "PRACTICAS")
        self.assertFalse(expedient["upload_enabled"])
        self.assertIn("docente responsable", expedient["upload_message"].lower())

    def test_teacher_respects_the_practice_upload_window(self) -> None:
        expedient = {
            "module_code": "PRACTICAS",
            "upload_start": "2026-09-01",
            "upload_end": "2026-09-30",
        }

        _ensure_document_upload_window(expedient, True, date(2026, 9, 15))
        with self.assertRaises(HTTPException) as context:
            _ensure_document_upload_window(expedient, True, date(2026, 10, 1))

        self.assertEqual(context.exception.status_code, 409)

    def test_no_debt_expedient_reuses_student_identity(self) -> None:
        expedient = _invoice_expedient(
            {
                "code": 123,
                "identification": "0102030405",
                "name": "ESTUDIANTE PRUEBA",
            }
        )

        self.assertEqual(expedient["module_code"], "FACTURACION")
        self.assertEqual(expedient["origin_id"], "123")
        self.assertEqual(expedient["expedient_code"], "NO-ADEUDA-123")
        self.assertEqual(
            [item["code"] for item in expedient["document_types"]],
            ["CERTIFICADO_NO_ADEUDAMIENTO"],
        )

    def test_no_debt_certificate_requires_pdf(self) -> None:
        expedient = _invoice_expedient({"code": 123})

        self.assertEqual(
            _validate_upload_filename(
                expedient,
                "CERTIFICADO_NO_ADEUDAMIENTO",
                "certificado-no-adeudamiento.pdf",
            ),
            "certificado-no-adeudamiento.pdf",
        )
        with self.assertRaises(HTTPException) as context:
            _validate_upload_filename(
                expedient,
                "CERTIFICADO_NO_ADEUDAMIENTO",
                "certificado-no-adeudamiento.xml",
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_secretary_archive_contains_the_regular_graduation_documents(self) -> None:
        expedient = _institutional_expedient({"code": 123}, "SECRETARIA")

        self.assertEqual(expedient["module_name"], "Secretaría General")
        self.assertEqual(
            [item["code"] for item in expedient["document_types"]],
            [
                "CEDULA",
                "TITULO_BACHILLER",
                "CERTIFICADO_NO_ADEUDAMIENTO",
                "RECORD_ACADEMICO_FIRMADO",
                "CERTIFICADO_PRACTICAS",
                "CERTIFICADO_VINCULACION",
                "DOCUMENTO_INGLES",
            ],
        )
        with self.assertRaises(HTTPException):
            _validate_upload_filename(expedient, "RECORD_ACADEMICO_FIRMADO", "record.docx")

    def test_homologation_archive_keeps_the_complete_graduation_checklist(self) -> None:
        expedient = _institutional_expedient(
            {"code": 123, "enrollment_type": "H"},
            "SECRETARIA",
        )

        codes = {item["code"] for item in expedient["document_types"]}
        self.assertEqual(len(codes), 13)
        self.assertIn("CERTIFICADO_PRACTICAS", codes)
        self.assertIn("CERTIFICADO_VINCULACION", codes)
        self.assertIn("DOCUMENTO_INGLES", codes)
        self.assertIn("DOCUMENTO_CERTIFICACIONES", codes)
        self.assertIn("DOCUMENTOS_UNIVERSIDAD_ORIGEN", codes)
        self.assertIn("DOCUMENTO_HOMOLOGACION", codes)
        self.assertIn("HOMOLOGACION_ARTICULO_81", codes)
        self.assertIn("HOMOLOGACION_ARTICULO_82", codes)
        self.assertIn("HOMOLOGACION_ARTICULO_83", codes)


if __name__ == "__main__":
    unittest.main()
