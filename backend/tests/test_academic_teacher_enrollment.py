from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.academic_enrollment import (
    AcademicTeacherMultiEnrollmentPayload,
    AcademicTeacherMultiSubjectEnrollmentPayload,
    AcademicTeacherPeriodEnrollmentPayload,
    AcademicTeacherSubjectEnrollmentPayload,
    _normalize_teacher_period_codes,
    _normalize_teacher_period_enrollments,
    _normalize_teacher_subject_enrollments,
    _normalize_teacher_student_selection,
    matricula_acad_docentes,
    matricula_acad_teacher_enrollments,
)


class TeacherEnrollmentQueryCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str, *params: object) -> "TeacherEnrollmentQueryCursor":
        del params
        self.statements.append(statement)
        return self

    def fetchall(self) -> list[object]:
        return []


def test_mass_teacher_enrollment_ignores_individual_student_filter() -> None:
    assert _normalize_teacher_student_selection("MASIVA", [10, 20]) is None


def test_individual_teacher_enrollment_normalizes_student_codes() -> None:
    assert _normalize_teacher_student_selection("INDIVIDUAL", [20, 10, 20, 0]) == [10, 20]


def test_individual_teacher_enrollment_requires_students() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_student_selection("INDIVIDUAL", [])

    assert exc_info.value.status_code == 400
    assert "al menos un estudiante" in str(exc_info.value.detail)


def test_teacher_enrollment_accepts_up_to_three_distinct_periods() -> None:
    assert _normalize_teacher_period_codes([1060, 1058, 1057]) == [1060, 1058, 1057]


def test_teacher_enrollment_rejects_duplicate_periods() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_period_codes([1060, 1060])

    assert exc_info.value.status_code == 400
    assert "mismo período" in str(exc_info.value.detail)


def test_teacher_enrollment_rejects_more_than_three_periods() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_period_codes([1060, 1058, 1057, 1056])

    assert exc_info.value.status_code == 400
    assert "máximo tres" in str(exc_info.value.detail)


def test_teacher_enrollment_accepts_up_to_three_distinct_subjects() -> None:
    payload = AcademicTeacherMultiSubjectEnrollmentPayload(
        codigo_doc=31,
        materias=[
            AcademicTeacherSubjectEnrollmentPayload(
                cod_materia=f"VGA-CG-2023-{code}",
                periodos=[AcademicTeacherPeriodEnrollmentPayload(codigo_periodo=1060, paralelo="a")],
                semestre=3,
            )
            for code in (17, 18, 19)
        ],
        modo_asignacion="MASIVA",
    )

    normalized = _normalize_teacher_subject_enrollments(payload)

    assert [subject for subject, _, _ in normalized] == [
        "VGA-CG-2023-17",
        "VGA-CG-2023-18",
        "VGA-CG-2023-19",
    ]
    assert all(periods[0].paralelo == "A" for _, _, periods in normalized)


def test_teacher_enrollment_rejects_more_than_three_subjects() -> None:
    with pytest.raises(ValidationError):
        AcademicTeacherMultiSubjectEnrollmentPayload(
            codigo_doc=31,
            materias=[
                AcademicTeacherSubjectEnrollmentPayload(
                    cod_materia=f"VGA-CG-2023-{code}",
                    periodos=[AcademicTeacherPeriodEnrollmentPayload(codigo_periodo=1060)],
                )
                for code in (17, 18, 19, 20)
            ],
        )


def test_teacher_enrollment_rejects_duplicate_subjects() -> None:
    payload = AcademicTeacherMultiSubjectEnrollmentPayload(
        codigo_doc=31,
        materias=[
            AcademicTeacherSubjectEnrollmentPayload(
                cod_materia="vga-cg-2023-17",
                periodos=[AcademicTeacherPeriodEnrollmentPayload(codigo_periodo=1060)],
            ),
            AcademicTeacherSubjectEnrollmentPayload(
                cod_materia="VGA-CG-2023-17",
                periodos=[AcademicTeacherPeriodEnrollmentPayload(codigo_periodo=1058)],
            ),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_subject_enrollments(payload)

    assert exc_info.value.status_code == 400
    assert "misma materia" in str(exc_info.value.detail)


def test_individual_teacher_enrollment_requires_students_in_each_period() -> None:
    payload = AcademicTeacherMultiEnrollmentPayload(
        codigo_doc=31,
        cod_materia="VGA-CG-2023-17",
        periodos=[
            AcademicTeacherPeriodEnrollmentPayload(
                codigo_periodo=1060,
                paralelo="a",
                codigos_estudiantes=[20, 10, 20],
            ),
            AcademicTeacherPeriodEnrollmentPayload(
                codigo_periodo=1058,
                paralelo="a",
                codigos_estudiantes=[],
            ),
        ],
        modo_asignacion="INDIVIDUAL",
    )

    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_period_enrollments(payload)

    assert exc_info.value.status_code == 400
    assert "al menos un estudiante" in str(exc_info.value.detail)


def test_teacher_enrollment_list_only_queries_active_teachers() -> None:
    cursor = TeacherEnrollmentQueryCursor()
    connection = Mock()
    connection.cursor.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    with patch("app.routers.academic_enrollment.get_connection", fake_connection):
        result = matricula_acad_teacher_enrollments(
            current_user=None,  # type: ignore[arg-type]
            codigo_periodo=1060,
            cod_anio_basica=None,
            codigo_materia=None,
            paralelo=None,
            semestre=None,
        )

    assert result == {"total": 0, "items": []}
    assert len(cursor.statements) == 1
    normalized_query = " ".join(cursor.statements[0].split()).upper()
    assert "U.ESTADO" in normalized_query
    assert "= N'A'" in normalized_query


def test_teacher_catalog_uses_exact_active_user_link() -> None:
    cursor = TeacherEnrollmentQueryCursor()
    connection = Mock()
    connection.cursor.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    with patch("app.routers.academic_enrollment.get_connection", fake_connection):
        result = matricula_acad_docentes(
            current_user=None,  # type: ignore[arg-type]
            query="darwin",
            limit=200,
            validar_usuario=True,
        )

    assert result == {"total": 0, "items": []}
    assert len(cursor.statements) == 1
    normalized_query = " ".join(cursor.statements[0].split()).upper()
    assert "INNER JOIN DBO.USUARIOS U" in normalized_query
    assert "U.CODIGO_USUARIO) = TRY_CONVERT(INT, D.CODIGO_DOC" in normalized_query
    assert "U.ESTADO" in normalized_query
    assert "= N'A'" in normalized_query
    assert "OUTER APPLY ( SELECT TOP (1) U.*" not in normalized_query
