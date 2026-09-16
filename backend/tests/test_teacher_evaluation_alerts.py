import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers import teacher_evaluation


class _FakeCursor:
    def __init__(self, result_sets: list[list[dict]]) -> None:
        self._result_sets = iter(result_sets)
        self._current: list[dict] = []

    def execute(self, _statement: str, *_params: object) -> None:
        self._current = next(self._result_sets)

    def fetchall(self) -> list[dict]:
        return self._current


class _FakeConnection:
    def __init__(self, result_sets: list[list[dict]]) -> None:
        self._cursor = _FakeCursor(result_sets)

    def cursor(self) -> _FakeCursor:
        return self._cursor


def _connection(result_sets: list[list[dict]]):
    @contextmanager
    def open_connection():
        yield _FakeConnection(result_sets)

    return open_connection


def _identity(value: dict) -> dict:
    return value


def _row_identity(_cursor: _FakeCursor, value: dict) -> dict:
    return value


def _deduplicate_identity(value: list[dict], **_kwargs: object) -> list[dict]:
    return value


class TeacherEvaluationPendingAlertTests(unittest.TestCase):
    def test_student_alert_counts_each_pending_flow(self) -> None:
        rows = [
            [{"evaluado": False}, {"evaluado": True}],
            [{"evaluado": False}],
        ]
        user = SessionUser(
            login="estudiante@intec.edu.ec",
            rol="ESTUDIANTE",
            cedula="1712345678",
            codigo_estud=91,
        )

        with (
            patch.object(teacher_evaluation, "get_connection", _connection(rows)),
            patch.object(
                teacher_evaluation,
                "_fetch_student",
                return_value={"codigo_estud": 91},
            ),
            patch.object(teacher_evaluation, "_row_dict", side_effect=_row_identity),
            patch.object(teacher_evaluation, "_course_from_row", side_effect=_identity),
            patch.object(
                teacher_evaluation,
                "_deduplicate_subject_courses",
                side_effect=_deduplicate_identity,
            ),
            patch.object(
                teacher_evaluation,
                "_apply_evaluation_status_groups",
                side_effect=lambda _actor, groups: groups,
            ),
        ):
            result = teacher_evaluation.get_teacher_evaluation_pending_alerts(user)

        self.assertEqual(result["role"], "ESTUDIANTE")
        self.assertEqual(result["total_evaluable"], 3)
        self.assertEqual(result["total_completed"], 1)
        self.assertEqual(result["total_pending"], 2)
        self.assertEqual(
            {item["flow"]: item["pending"] for item in result["items"]},
            {"student": 1, "auto_estudiante": 1},
        )
        self.assertEqual(
            {item["flow"]: len(item["pending_courses"]) for item in result["items"]},
            {"student": 1, "auto_estudiante": 1},
        )

    def test_teacher_alert_counts_self_and_peer_evaluations(self) -> None:
        rows = [
            [{"evaluado": False}],
            [{"evaluado": True}, {"evaluado": False}, {"evaluado": False}],
        ]
        user = SessionUser(
            login="docente@intec.edu.ec",
            rol="DOCENTE",
            cedula="0912345678",
            codigo_doc=42,
        )

        with (
            patch.object(teacher_evaluation, "get_connection", _connection(rows)),
            patch.object(
                teacher_evaluation,
                "_fetch_teacher",
                return_value={"codigo_doc": 42},
            ),
            patch.object(teacher_evaluation, "_row_dict", side_effect=_row_identity),
            patch.object(teacher_evaluation, "_course_from_row", side_effect=_identity),
            patch.object(
                teacher_evaluation,
                "_deduplicate_subject_courses",
                side_effect=_deduplicate_identity,
            ),
            patch.object(
                teacher_evaluation,
                "_apply_evaluation_status_groups",
                side_effect=lambda _actor, groups: groups,
            ),
        ):
            result = teacher_evaluation.get_teacher_evaluation_pending_alerts(user)

        self.assertEqual(result["role"], "DOCENTE")
        self.assertEqual(result["total_evaluable"], 4)
        self.assertEqual(result["total_completed"], 1)
        self.assertEqual(result["total_pending"], 3)
        self.assertEqual(
            {item["flow"]: item["pending"] for item in result["items"]},
            {"auto_docente": 1, "par_docente": 2},
        )
        self.assertEqual(
            {item["flow"]: len(item["pending_courses"]) for item in result["items"]},
            {"auto_docente": 1, "par_docente": 2},
        )

    def test_alert_rejects_session_without_valid_identity(self) -> None:
        user = SessionUser(login="docente@intec.edu.ec", rol="DOCENTE")

        with self.assertRaises(HTTPException) as raised:
            teacher_evaluation.get_teacher_evaluation_pending_alerts(user)

        self.assertEqual(raised.exception.status_code, 422)
