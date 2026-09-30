import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from app.services.teacher_honoraria_mail import (
    HONORARIA_RECIPIENTS,
    TeacherMailDeliveryUncertain,
    send_teacher_honoraria_mail,
    teacher_copy_address,
)
from app.services.integration_history import teacher_honoraria_mail_state
from app.routers.portal_academico import _store_signed_teacher_documents_onedrive


def documents(large: bool = False):
    return [
        {"filename": name, "content": b"x" * (3 * 1024 * 1024 if large and kind == "RIDE" else 2), "content_type": mime, "document_type": kind}
        for kind, name, mime in (
            ("INFORME", "informe.pdf", "application/pdf"),
            ("NOTAS", "notas.pdf", "application/pdf"),
            ("CONTRATO", "contrato.pdf", "application/pdf"),
            ("FACTURA_XML", "factura.xml", "application/xml"),
            ("RIDE", "ride.pdf", "application/pdf"),
        )
    ]


class TeacherHonorariaMailTests(unittest.TestCase):
    def test_reuses_teacher_folder_without_deleting_it_on_upload_failure(self):
        parent = "DOCENTES/Docente - 123/DOCUMENTOS FIRMADOS/Materia/1"
        old_folder = f"{parent}/FIRMA old"
        identity = {"cedula": "123", "nombre": "Docente"}
        with (
            patch("app.routers.portal_academico._teacher_signed_documents_folder", return_value=f"{parent}/FIRMA new"),
            patch("app.routers.portal_academico.ensure_graph_document_folder", return_value={"id": "folder"}),
            patch("app.routers.portal_academico.upload_graph_document_bytes", side_effect=RuntimeError("upload failed")),
            patch("app.routers.portal_academico.delete_graph_document_item") as delete_item,
        ):
            with self.assertRaises(RuntimeError):
                _store_signed_teacher_documents_onedrive(
                    identity=identity, compliance_pdf=b"pdf", grades_pdf=b"pdf", contract_pdf=b"pdf",
                    subject_code="1", period_codes=["1"], existing_folder_path=old_folder,
                )
            delete_item.assert_not_called()

    def test_audit_state_prevents_duplicate_or_uncertain_retry(self):
        class Cursor:
            def __init__(self, row):
                self.row = row

            def execute(self, query, folder, teacher):
                self.folder = folder
                self.teacher = teacher
                return self

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self, row):
                self.row = row

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self):
                return Cursor(self.row)

        cases = ((None, "new"), (SimpleNamespace(Etapa="ENVIADO", Estado="EXITOSO"), "sent"),
                 (SimpleNamespace(Etapa="ENVIADO", Estado="ERROR"), "retry"),
                 (SimpleNamespace(Etapa="ENVIANDO", Estado="EXITOSO"), "uncertain"))
        with patch("app.services.integration_history.ensure_integration_history_schema"):
            for row, expected in cases:
                with patch("app.services.integration_history.get_integration_control_connection", return_value=Connection(row)):
                    self.assertEqual(teacher_honoraria_mail_state("DOCENTES/caso", "123"), expected)

    def test_requires_teacher_copy_and_all_five_documents(self):
        self.assertEqual(teacher_copy_address({"correo": "invalid", "correo_personal": "docente@intec.edu.ec"}), "docente@intec.edu.ec")
        with self.assertRaises(ValueError):
            teacher_copy_address({"correo": "invalid"})
        with patch("app.services.teacher_honoraria_mail.get_settings", return_value=SimpleNamespace(graph_mail_sender="envios@intec.edu.ec")):
            with self.assertRaises(ValueError):
                send_teacher_honoraria_mail({"correo": "docente@intec.edu.ec"}, documents()[:-1])

    def test_sends_from_service_mailbox_with_teacher_copy(self):
        calls = []

        def handle(request):
            calls.append(request)
            if request.url.path.endswith("/messages"):
                return httpx.Response(201, json={"id": "draft-1"})
            if request.url.path.endswith("/send"):
                return httpx.Response(202)
            return httpx.Response(201, json={"id": "attachment"})

        real_client = httpx.Client
        with (
            patch("app.services.teacher_honoraria_mail.get_settings", return_value=SimpleNamespace(graph_mail_sender="envios@intec.edu.ec")),
            patch("app.services.teacher_honoraria_mail.get_graph_token", return_value="token"),
            patch("app.services.teacher_honoraria_mail.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)),
        ):
            result = send_teacher_honoraria_mail({"nombre": "Docente", "cedula": "123", "correo": "docente@intec.edu.ec"}, documents())

        self.assertEqual(result, "draft-1")
        draft = json.loads(calls[0].content)
        self.assertEqual(draft["subject"], "Honorarios docentes")
        self.assertEqual(HONORARIA_RECIPIENTS, ("roberto.castro@intec.edu.ec", "veronica.cevallos@intec.edu.ec"))
        self.assertEqual([item["emailAddress"]["address"] for item in draft["toRecipients"]], list(HONORARIA_RECIPIENTS))
        self.assertEqual(draft["ccRecipients"][0]["emailAddress"]["address"], "docente@intec.edu.ec")
        self.assertEqual(len([item for item in calls if item.url.path.endswith("/attachments")]), 5)
        self.assertTrue(calls[-1].url.path.endswith("/send"))

    def test_large_attachment_uses_upload_session(self):
        calls = []

        def handle(request):
            calls.append(request)
            if request.url.path.endswith("/messages"):
                return httpx.Response(201, json={"id": "draft-2"})
            if request.url.path.endswith("/createUploadSession"):
                return httpx.Response(201, json={"uploadUrl": "https://upload.test/session"})
            if request.method == "PUT":
                return httpx.Response(201)
            if request.url.path.endswith("/send"):
                return httpx.Response(202)
            return httpx.Response(201, json={"id": "attachment"})

        real_client = httpx.Client
        with (
            patch("app.services.teacher_honoraria_mail.get_settings", return_value=SimpleNamespace(graph_mail_sender="envios@intec.edu.ec")),
            patch("app.services.teacher_honoraria_mail.get_graph_token", return_value="token"),
            patch("app.services.teacher_honoraria_mail.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)),
        ):
            send_teacher_honoraria_mail({"correo": "docente@intec.edu.ec"}, documents(large=True))

        self.assertEqual(len([item for item in calls if item.url.path.endswith("/createUploadSession")]), 1)
        self.assertEqual(len([item for item in calls if item.method == "PUT"]), 1)
        self.assertEqual(calls[-2].headers["Content-Range"], f"bytes 0-{3 * 1024 * 1024 - 1}/{3 * 1024 * 1024}")

    def test_uncertain_graph_response_is_not_treated_as_retriable(self):
        def handle(request):
            if request.url.path.endswith("/messages"):
                return httpx.Response(201, json={"id": "draft-3"})
            if request.url.path.endswith("/send"):
                raise httpx.ReadError("connection lost")
            return httpx.Response(201, json={"id": "attachment"})

        real_client = httpx.Client
        with (
            patch("app.services.teacher_honoraria_mail.get_settings", return_value=SimpleNamespace(graph_mail_sender="envios@intec.edu.ec")),
            patch("app.services.teacher_honoraria_mail.get_graph_token", return_value="token"),
            patch("app.services.teacher_honoraria_mail.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)),
        ):
            with self.assertRaises(TeacherMailDeliveryUncertain):
                send_teacher_honoraria_mail({"correo": "docente@intec.edu.ec"}, documents())

    def test_failed_attachment_cleans_up_unsent_draft(self):
        calls = []

        def handle(request):
            calls.append(request)
            if request.url.path.endswith("/messages"):
                return httpx.Response(201, json={"id": "draft-4"})
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(403)

        real_client = httpx.Client
        with (
            patch("app.services.teacher_honoraria_mail.get_settings", return_value=SimpleNamespace(graph_mail_sender="envios@intec.edu.ec")),
            patch("app.services.teacher_honoraria_mail.get_graph_token", return_value="token"),
            patch("app.services.teacher_honoraria_mail.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)),
        ):
            with self.assertRaises(httpx.HTTPStatusError):
                send_teacher_honoraria_mail({"correo": "docente@intec.edu.ec"}, documents())

        self.assertEqual(calls[-1].method, "DELETE")
        self.assertFalse(any(item.url.path.endswith("/send") for item in calls))
