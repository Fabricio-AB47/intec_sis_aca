import unittest

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.document_expedients import (
    _ACCESS,
    _invoice_expedient,
    _validate_upload_filename,
)


class DocumentExpedientAccessTests(unittest.TestCase):
    def test_student_is_rejected(self) -> None:
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")

        with self.assertRaises(HTTPException) as context:
            _ACCESS(student)

        self.assertEqual(context.exception.status_code, 403)

    def test_authorized_profiles_are_accepted(self) -> None:
        for role in ("ACADEMICO", "SECRETARIA", "FINANCIERO", "ADMINISTRADOR"):
            with self.subTest(role=role):
                user = SessionUser(login="usuario@intec.edu.ec", rol=role)
                self.assertIs(_ACCESS(user), user)

    def test_invoice_expedient_reuses_student_identity(self) -> None:
        expedient = _invoice_expedient(
            {
                "code": 123,
                "identification": "0102030405",
                "name": "ESTUDIANTE PRUEBA",
            }
        )

        self.assertEqual(expedient["module_code"], "FACTURACION")
        self.assertEqual(expedient["origin_id"], "123")
        self.assertEqual(expedient["expedient_code"], "FACT-123")
        self.assertEqual(
            [item["code"] for item in expedient["document_types"]],
            ["FACTURA_XML", "RIDE_FACTURA"],
        )

    def test_invoice_upload_formats_are_strict(self) -> None:
        expedient = _invoice_expedient({"code": 123})

        self.assertEqual(
            _validate_upload_filename(expedient, "FACTURA_XML", "factura-001.xml"),
            "factura-001.xml",
        )
        self.assertEqual(
            _validate_upload_filename(expedient, "RIDE_FACTURA", "ride-001.pdf"),
            "ride-001.pdf",
        )
        with self.assertRaises(HTTPException) as xml_context:
            _validate_upload_filename(expedient, "FACTURA_XML", "factura-001.pdf")
        with self.assertRaises(HTTPException) as ride_context:
            _validate_upload_filename(expedient, "RIDE_FACTURA", "ride-001.xml")

        self.assertEqual(xml_context.exception.status_code, 400)
        self.assertEqual(ride_context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
