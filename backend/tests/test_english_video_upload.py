import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.security import SessionUser
from app.routers.english_exams import (
    ActivitySettingsPayload,
    PublishGradePayload,
    PrepareSubmissionPayload,
    ReopenSubmissionPayload,
    RubricDraftPayload,
    UploadSessionPayload,
    _MAX_FILE_BYTES,
    _MIN_FILE_BYTES,
    _activity_state,
    _component_payload,
    _rubric_grade,
    _safe_filename,
    _safe_video_content_type,
    _validated_activity_window,
    _validated_reopen_deadline,
    grade_submission,
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

        self.assertEqual(minimum.size, 40 * 1024 * 1024)
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

    def test_activity_window_converts_guayaquil_time_to_utc(self) -> None:
        start, deadline = _validated_activity_window(
            datetime(2026, 8, 4, 9, 0, 0),
            datetime(2026, 8, 4, 11, 30, 0),
        )

        self.assertEqual(start, datetime(2026, 8, 4, 14, 0, 0))
        self.assertEqual(deadline, datetime(2026, 8, 4, 16, 30, 0))

    def test_activity_window_rejects_invalid_order(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _validated_activity_window(
                datetime(2026, 8, 4, 11, 0, 0),
                datetime(2026, 8, 4, 10, 59, 0),
            )

        self.assertEqual(context.exception.status_code, 422)

    def test_reopening_requires_a_future_deadline(self) -> None:
        now = datetime(2026, 8, 4, 14, 0, 0)
        future = datetime(2026, 8, 4, 15, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(_validated_reopen_deadline(future, now=now), datetime(2026, 8, 4, 15, 0, 0))
        with self.assertRaises(HTTPException) as context:
            _validated_reopen_deadline(datetime(2026, 8, 4, 8, 0, 0), now=now)
        self.assertEqual(context.exception.status_code, 422)

    def test_activity_and_reopening_reject_blank_explanations(self) -> None:
        with self.assertRaises(ValidationError):
            ActivitySettingsPayload(
                component_code="P1",
                period_code="1060",
                instructions="   ",
                activity_start=datetime(2026, 8, 4, 9, 0, 0),
                activity_deadline=datetime(2026, 8, 4, 10, 0, 0),
            )
        with self.assertRaises(ValidationError):
            ReopenSubmissionPayload(
                component_code="P1",
                period_code="1060",
                reason="          ",
                new_deadline=datetime(2026, 8, 5, 10, 0, 0),
            )

    def test_prepare_submission_requires_exact_positive_enrollment(self) -> None:
        payload = PrepareSubmissionPayload(
            enrollment_id=5001,
            period_code="1060",
            subject_code="901",
        )

        self.assertEqual(payload.enrollment_id, 5001)
        with self.assertRaises(ValidationError):
            PrepareSubmissionPayload(
                enrollment_id=0,
                period_code="1060",
                subject_code="901",
            )

    def test_legacy_direct_grade_endpoint_is_retired(self) -> None:
        reviewer = SessionUser(login="academico", nombres="Academico", rol="ACADEMICO")

        with self.assertRaises(HTTPException) as context:
            grade_submission(1, {}, reviewer)

        self.assertEqual(context.exception.status_code, 410)

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

    def test_component_payload_exposes_graph_video_url_for_reviewer_subscreen(self) -> None:
        upload_id = uuid4()
        row = SimpleNamespace(
            componente_id=10,
            codigo="P1",
            numero_parcial=1,
            nombre="Parcial 1",
            tipo_evaluacion="EXAMEN_VIDEO",
            nota=None,
            estado="PENDIENTE",
            observacion=None,
            nombre_evaluador=None,
            fecha_calificacion=None,
            upload_id=upload_id,
            nombre_archivo="p1.mp4",
            content_type="video/mp4",
            tamano_bytes=_MIN_FILE_BYTES,
            numero_version=1,
            fecha_carga=datetime(2026, 8, 4, 15, 0, 0),
            fecha_limite_edicion=datetime(2026, 8, 4, 15, 15, 0),
            fecha_confirmacion=datetime(2026, 8, 4, 15, 5, 0),
            integridad_validada=True,
            hash_integridad="sha256:test",
            estado_carga="CONFIRMADO",
            graph_web_url="https://tenant.sharepoint.com/sites/idiomas/p1.mp4",
        )

        payload = _component_payload(row)

        self.assertEqual(payload["file"]["upload_id"], str(upload_id))
        self.assertEqual(
            payload["file"]["web_url"],
            "https://tenant.sharepoint.com/sites/idiomas/p1.mp4",
        )


if __name__ == "__main__":
    unittest.main()
