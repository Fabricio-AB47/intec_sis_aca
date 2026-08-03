import pytest
from fastapi import HTTPException

from app.routers.academic_enrollment import _normalize_teacher_student_selection


def test_mass_teacher_enrollment_ignores_individual_student_filter() -> None:
    assert _normalize_teacher_student_selection("MASIVA", [10, 20]) is None


def test_individual_teacher_enrollment_normalizes_student_codes() -> None:
    assert _normalize_teacher_student_selection("INDIVIDUAL", [20, 10, 20, 0]) == [10, 20]


def test_individual_teacher_enrollment_requires_students() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_teacher_student_selection("INDIVIDUAL", [])

    assert exc_info.value.status_code == 400
    assert "al menos un estudiante" in str(exc_info.value.detail)
