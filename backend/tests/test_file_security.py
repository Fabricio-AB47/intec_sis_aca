import unittest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException, UploadFile

from app.core.file_security import read_secure_upload


def xlsx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
    return output.getvalue()


class FileSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_valid_xlsx(self) -> None:
        upload = UploadFile(BytesIO(xlsx_bytes()), filename="personas.xlsx")

        filename, content = await read_secure_upload(
            upload,
            maximum=1024 * 1024,
            allowed_extensions={".xlsx"},
        )

        self.assertEqual(filename, "personas.xlsx")
        self.assertTrue(content.startswith(b"PK"))

    async def test_rejects_extension_signature_mismatch(self) -> None:
        upload = UploadFile(BytesIO(b"contenido que no es PDF"), filename="respaldo.pdf")

        with self.assertRaises(HTTPException) as captured:
            await read_secure_upload(upload, maximum=1024, allowed_extensions={".pdf"})

        self.assertEqual(captured.exception.status_code, 400)

    async def test_closes_upload_when_extension_is_rejected(self) -> None:
        upload = UploadFile(BytesIO(b"contenido"), filename="respaldo.exe")

        with self.assertRaises(HTTPException):
            await read_secure_upload(upload, maximum=1024, allowed_extensions={".pdf"})

        self.assertTrue(upload.file.closed)

    async def test_rejects_content_beyond_limit_without_unbounded_read(self) -> None:
        upload = UploadFile(BytesIO(b"%PDF-" + b"x" * 128), filename="respaldo.pdf")

        with self.assertRaises(HTTPException) as captured:
            await read_secure_upload(upload, maximum=64, allowed_extensions={".pdf"})

        self.assertEqual(captured.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
