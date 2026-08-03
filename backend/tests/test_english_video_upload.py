import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.english_exams import (
    PublishGradePayload,
    RubricDraftPayload,
    UploadSessionPayload,
    _MAX_FILE_BYTES,
    _MIN_FILE_BYTES,
    _activity_state,
    _rubric_grade,
    _safe_filename,
    _safe_video_content_type,
)


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

    def test_upload_contract_accepts_only_files_between_50_mb_and_2_gb(self) -> None:
        minimum = UploadSessionPayload(filename="p1.mp4", size=_MIN_FILE_BYTES, content_type="video/mp4")
        maximum = UploadSessionPayload(filename="p1.mp4", size=_MAX_FILE_BYTES, content_type="video/mp4")

        self.assertEqual(minimum.size, 50 * 1024 * 1024)
        self.assertEqual(maximum.size, 2 * 1024 * 1024 * 1024)
        with self.assertRaises(ValidationError):
            UploadSessionPayload(filename="p1.mp4", size=_MIN_FILE_BYTES - 1, content_type="video/mp4")
        with self.assertRaises(ValidationError):
            UploadSessionPayload(filename="p1.mp4", size=_MAX_FILE_BYTES + 1, content_type="video/mp4")

    def test_activity_state_enforces_start_and_deadline(self) -> None:
        now = datetime(2026, 8, 3, 12, 0, 0)

        self.assertEqual(_activity_state(now + timedelta(minutes=1), None, now=now), (False, "AUN_NO_INICIA"))
        self.assertEqual(_activity_state(None, now - timedelta(seconds=1), now=now), (False, "PLAZO_FINALIZADO"))
        self.assertEqual(
            _activity_state(now - timedelta(days=1), now + timedelta(days=1), now=now),
            (True, "ABIERTA"),
        )

    def test_rubric_calculates_weighted_grade_over_ten(self) -> None:
        payload = RubricDraftPayload(
            language_mastery=Decimal("8"),
            fluency_pronunciation=Decimal("9"),
            content_coherence=Decimal("7"),
            instruction_compliance=Decimal("10"),
            observation="Retroalimentación",
            component_code="P1",
            period_code="1060",
        )

        self.assertEqual(_rubric_grade(payload), Decimal("8.35"))
        self.assertEqual(PublishGradePayload(component_code="P1", period_code="1060").component_code, "P1")

    def test_rubric_rejects_values_above_ten(self) -> None:
        with self.assertRaises(ValidationError):
            RubricDraftPayload(
                language_mastery=Decimal("10.01"),
                fluency_pronunciation=Decimal("9"),
                content_coherence=Decimal("7"),
                instruction_compliance=Decimal("10"),
                component_code="P1",
                period_code="1060",
            )


if __name__ == "__main__":
    unittest.main()
