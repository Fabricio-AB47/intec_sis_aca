import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from app.routers import sisacademico_admin as admin


class StudentStateOptionalDocumentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.conn.__exit__.return_value = False
        self.cursor = self.conn.cursor.return_value
        self.cursor.rowcount = 1
        self.cursor.fetchone.side_effect = [
            SimpleNamespace(codigo_estud="100", estado_anterior="A", estudiante="Prueba"),
            SimpleNamespace(codigo="P", nombre="Inactivo"),
        ]
        self.user = SimpleNamespace(nombres="Prueba", login="test")
        for target, value in (("get_connection", MagicMock(return_value=self.conn)),
                              ("_STUDENT_STATE_DOCUMENT_ROOT", self.root)):
            p = patch.object(admin, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(admin, "read_secure_upload", new=AsyncMock(return_value=("respaldo.pdf", b"%PDF-test")))
        self.secure = p.start()
        self.addCleanup(p.stop)

    def upload(self):
        return UploadFile(BytesIO(b"%PDF-test"), filename="respaldo.pdf")

    async def call(self, **overrides):
        values = dict(record_key=admin._encode_key(["0000000000"]), estado="P",
                      detalle="Cambio autorizado", documento=None, solo_documento=False, current_user=self.user)
        values.update(overrides)
        return await admin.update_student_state_with_document(**values)

    def writes(self, fragment):
        return [call.args for call in self.cursor.execute.call_args_list if fragment in call.args[0]]

    async def test_changes_state_without_file_and_keeps_description_audited(self):
        result = await self.call()
        self.assertTrue(result["ok"])
        self.assertEqual(result["document_url"], "")
        self.assertEqual(len(self.writes("UPDATE dbo.DATOS_ESTUD")), 1)
        audit = self.writes("INSERT INTO dbo.REGISTRODOCESTUD")[0]
        self.assertEqual(audit[2], "")
        self.assertIn("Cambio autorizado", audit[3])
        self.assertIn("A -> P", audit[3])
        self.secure.assert_not_awaited()
        self.conn.commit.assert_called_once()
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_change_can_include_a_document(self):
        result = await self.call(documento=self.upload())
        self.assertTrue(result["document_url"])
        self.assertEqual(len(list(self.root.rglob("*.pdf"))), 1)
        self.secure.assert_awaited_once()
        self.assertEqual(self.secure.call_args.kwargs["maximum"], 15 * 1024 * 1024)

    async def test_later_document_does_not_update_student_state(self):
        result = await self.call(estado="A", detalle="", documento=self.upload(), solo_documento=True)
        self.assertEqual(result["affected_rows"], 0)
        self.assertEqual(self.writes("UPDATE dbo.DATOS_ESTUD"), [])
        self.assertIn("Respaldo posterior", self.writes("INSERT INTO dbo.REGISTRODOCESTUD")[0][3])
        self.conn.commit.assert_called_once()

    async def test_later_document_rejects_stale_state(self):
        with self.assertRaises(HTTPException) as error:
            await self.call(documento=self.upload(), solo_documento=True)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.writes("UPDATE dbo.DATOS_ESTUD"), [])
        self.conn.commit.assert_not_called()

    async def test_description_is_still_required_for_state_changes(self):
        for detail in ("", "   ", "corto"[:4]):
            with self.subTest(detail=detail), self.assertRaises(HTTPException) as error:
                await self.call(detalle=detail)
            self.assertEqual(error.exception.status_code, 400)
        self.conn.cursor.assert_not_called()

    async def test_state_is_required(self):
        with self.assertRaises(HTTPException) as error:
            await self.call(estado="")
        self.assertEqual(error.exception.status_code, 400)
        self.conn.commit.assert_not_called()

    async def test_same_state_is_not_a_state_change(self):
        with self.assertRaises(HTTPException) as error:
            await self.call(estado="A")
        self.assertEqual(error.exception.status_code, 400)
        self.conn.commit.assert_not_called()

    async def test_attachment_only_requires_a_file(self):
        with self.assertRaises(HTTPException) as error:
            await self.call(solo_documento=True)
        self.assertEqual(error.exception.status_code, 400)

    async def test_security_rejection_prevents_state_change(self):
        self.secure.side_effect = HTTPException(413, "Too large")
        with self.assertRaises(HTTPException) as error:
            await self.call(documento=self.upload())
        self.assertEqual(error.exception.status_code, 413)
        self.conn.commit.assert_not_called()

    async def test_long_description_fails_without_losing_data(self):
        with self.assertRaises(HTTPException) as error:
            await self.call(detalle="x" * 250, documento=self.upload())
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.writes("UPDATE dbo.DATOS_ESTUD"), [])
        self.assertEqual(list(self.root.rglob("*.pdf")), [])

    async def test_commit_failure_removes_uploaded_file(self):
        self.conn.commit.side_effect = RuntimeError("DB unavailable")
        with self.assertRaises(HTTPException) as error:
            await self.call(documento=self.upload())
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(list(self.root.rglob("*.pdf")), [])

    def test_http_form_accepts_absent_file(self):
        app = FastAPI()
        app.include_router(admin.router)
        app.dependency_overrides[admin.AllowedEditor.dependency] = lambda: self.user
        with TestClient(app) as client:
            response = client.post(
                f"/api/students/sisacademico/actualizacion_estudiantes/{admin._encode_key(['0000000000'])}/cambio-estado-documentado",
                data={"estado": "P", "detalle": "Cambio autorizado"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["document_url"], "")

    def test_http_form_accepts_later_document_without_new_description(self):
        app = FastAPI()
        app.include_router(admin.router)
        app.dependency_overrides[admin.AllowedEditor.dependency] = lambda: self.user
        with TestClient(app) as client:
            response = client.post(
                f"/api/students/sisacademico/actualizacion_estudiantes/{admin._encode_key(['0000000000'])}/cambio-estado-documentado",
                data={"estado": "A", "detalle": "", "solo_documento": "true"},
                files={"documento": ("respaldo.pdf", b"%PDF-test", "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.writes("UPDATE dbo.DATOS_ESTUD"), [])
