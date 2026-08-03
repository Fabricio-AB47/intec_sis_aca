import unittest

from fastapi import HTTPException

from app.routers.english_exams import _safe_filename, _safe_video_content_type


class EnglishVideoUploadTests(unittest.TestCase):
    def test_accepts_supported_video_extensions(self) -> None:
        for filename in ("parcial.mp4", "parcial.MOV", "parcial.mkv", "parcial.webm"):
            with self.subTest(filename=filename):
                self.assertEqual(_safe_filename(filename), filename)

    def test_rejects_non_video_extensions(self) -> None:
        for filename in ("evidencia.pdf", "audio.mp3", "archivo.zip", "documento.docx"):
            with self.subTest(filename=filename):
                with self.assertRaises(HTTPException) as context:
                    _safe_filename(filename)
                self.assertEqual(context.exception.status_code, 400)

    def test_accepts_video_and_binary_content_types(self) -> None:
        self.assertEqual(_safe_video_content_type("video/mp4"), "video/mp4")
        self.assertEqual(_safe_video_content_type("video/webm; codecs=vp9"), "video/webm")
        self.assertEqual(_safe_video_content_type("application/octet-stream"), "application/octet-stream")

    def test_rejects_non_video_content_type(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _safe_video_content_type("application/pdf")
        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
