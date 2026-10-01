import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.integrations.moodle.exceptions import MoodleError
from app.routers import portal_academico as portal


def _record(student, period, start, email, **extra):
    return {
        "codigo_estud": str(student),
        "nombre_estudiante": f"ESTUDIANTE {student}",
        "codigo_periodo": str(period),
        "detalle_periodo": f"PERIODO {period}",
        "fecha_inicio_periodo": start,
        "anio_periodo": int(start[:4]) if start else None,
        "correo_intec_registro": email,
        **extra,
    }


def test_latest_enrollment_uses_period_start_and_year():
    rows = [
        _record(1, 100, "2024-03-01", "uno@intec.edu.ec"),
        _record(1, 200, "2025-09-07", "uno@intec.edu.ec"),
        _record(2, 300, "2025-09-07", "dos@intec.edu.ec"),
    ]
    selected, review = portal._latest_subject_enrollments(rows)
    assert {(row["codigo_estud"], row["codigo_periodo"]) for row in selected} == {("1", "200"), ("2", "300")}
    assert review == []


def test_ambiguous_duplicate_period_dates_require_review():
    rows = [
        _record(1, 100, "", "uno@intec.edu.ec"),
        _record(1, 200, "2025-09-07", "uno@intec.edu.ec"),
    ]
    selected, review = portal._latest_subject_enrollments(rows)
    assert selected == []
    assert review[0]["codigo_estud"] == "1"


def test_selected_moodle_course_scopes_students_and_periods():
    rows = [
        _record(1, 100, "2024-03-01", "uno@intec.edu.ec"),
        _record(1, 200, "2025-09-07", "uno@intec.edu.ec"),
        _record(2, 300, "2025-09-07", "dos@intec.edu.ec"),
    ]
    users = [
        {"email": "uno@intec.edu.ec", "role_shortnames": ["student"], "confirmed": True},
        {"email": "dos@intec.edu.ec", "role_shortnames": ["student"], "suspended": True},
        {"email": "externo@intec.edu.ec", "role_shortnames": ["student"], "confirmed": True},
    ]
    service = AsyncMock()
    service.get_course_enrolled_users.return_value = users
    with (
        patch.object(portal, "_teacher_subject_moodle_courses", AsyncMock(return_value=[{"id": 10, "fullname": "Materia"}])),
        patch.object(portal, "_teacher_subject_academic_records", return_value=({"cod_materia": "TEST"}, rows)),
        patch.object(portal, "teacher_profile", return_value={"teacher": {"correo": "docente@intec.edu.ec"}}),
    ):
        scope = asyncio.run(portal._teacher_selected_moodle_scope(None, "TEST", 10, service=service))
    assert [(row["codigo_estud"], row["codigo_periodo"]) for row in scope["students"]] == [("1", "200")]
    assert [period["code"] for period in scope["periods"]] == ["200"]
    assert scope["unmatched_moodle_count"] == 1


def test_explicit_course_fails_closed_when_moodle_is_unavailable():
    with patch.object(portal, "_teacher_compliance_moodle_context", AsyncMock(side_effect=HTTPException(503))):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(portal._prepare_teacher_compliance_generation(
                None, [200], "TEST", "*", None, [], [1], "", moodle_course_id=10,
            ))
    assert caught.value.status_code == 503


def test_resources_cannot_switch_explicit_course():
    with pytest.raises(HTTPException) as caught:
        asyncio.run(portal._prepare_teacher_compliance_generation(
            None, [200], "TEST", "*", None, [{"course_id": 11}], [1], "", moodle_course_id=10,
        ))
    assert caught.value.status_code == 400


def test_grade_rows_require_complete_moodle_roster_and_periods():
    scope = {
        "periods": [{"code": "100"}, {"code": "200"}],
        "students": [
            {"codigo_estud": "1", "codigo_periodo": "100"},
            {"codigo_estud": "2", "codigo_periodo": "200"},
        ],
    }
    with patch.object(portal, "_teacher_selected_moodle_scope", AsyncMock(return_value=scope)):
        with pytest.raises(HTTPException) as periods_error:
            asyncio.run(portal._selected_moodle_grade_rows(None, "TEST", 10, [100], [1, 2]))
        with pytest.raises(HTTPException) as students_error:
            asyncio.run(portal._selected_moodle_grade_rows(None, "TEST", 10, [100, 200], [1]))
        rows = asyncio.run(portal._selected_moodle_grade_rows(None, "TEST", 10, [100, 200], [1, 2]))
    assert periods_error.value.status_code == 403
    assert students_error.value.status_code == 403
    assert len(rows) == 2


def test_subject_courses_prioritize_unique_code_and_teacher_enrollment():
    subject = {
        "cod_materia": "VGA-ES-2023-74", "codigo_materia": "401",
        "nombre_materia": "Fundamentos de Seguridad Informática y Ciberseguridad",
        "codigo_periodos": [1034],
    }
    courses = [
        {"id": 10, "fullname": "VGA-ES-2023-74 - Fundamentos de Seguridad Informática"},
        {"id": 11, "fullname": "Fundamentos de Seguridad Informática y Ciberseguridad"},
        {"id": 12, "fullname": "VGA-ES-2023-74 - Fundamentos de Seguridad Informática - Otro docente"},
        {"id": 13, "fullname": "VGA-ES-2023-740 - Fundamentos de Seguridad Informática"},
    ]
    teacher = {"id": 5, "email": "docente@intec.edu.ec", "idnumber": "1724036536", "confirmed": True}
    service = AsyncMock()
    service.get_all_users.return_value = [teacher]
    service.get_user_courses.return_value = courses
    service.get_course_enrolled_users.side_effect = lambda course_id, **_: [
        {**teacher, "role_shortnames": ["editingteacher"] if course_id != 12 else ["student"]}
    ]
    with (
        patch.object(portal, "_teacher_subject_assignment", return_value=subject),
        patch.object(portal, "teacher_profile", return_value={"teacher": {"correo": teacher["email"], "cedula": teacher["idnumber"]}}),
    ):
        matches = asyncio.run(portal._teacher_subject_moodle_courses(None, "VGA-ES-2023-74", service=service))
    assert [item["id"] for item in matches] == [10]
    assert matches[0]["subject_code_similarity"] == 100


def test_course_catalog_fallback_still_checks_teacher_identity():
    subject = {"cod_materia": "VGA-ES-2023-74", "codigo_materia": "401", "nombre_materia": "Seguridad"}
    teacher = {"id": 5, "email": "otro@intec.edu.ec", "idnumber": "1724036536", "confirmed": True}
    service = AsyncMock()
    service.get_all_users.return_value = [teacher]
    service.get_user_courses.side_effect = MoodleError("Función no habilitada")
    service.get_all_courses.return_value = [
        {"id": 10, "fullname": "VGA-ES-2023-74 - Seguridad"},
        {"id": 11, "fullname": "VGA-ES-2023-74 - Seguridad - Otro docente"},
    ]
    service.get_course_enrolled_users.side_effect = lambda course_id, **_: [
        {"idnumber": "1724036536" if course_id == 10 else "9999999999", "role_shortnames": ["docente"]}
    ]
    with (
        patch.object(portal, "_teacher_subject_assignment", return_value=subject),
        patch.object(portal, "teacher_profile", return_value={"teacher": {"cedula": "1724036536"}}),
    ):
        matches = asyncio.run(portal._teacher_subject_moodle_courses(None, "VGA-ES-2023-74", service=service))
    assert [item["id"] for item in matches] == [10]


def test_unique_code_does_not_match_longer_numeric_suffix():
    similarity, conflict = portal._moodle_subject_code_similarity(
        {"fullname": "VGA-ES-2023-740 - Seguridad"}, "VGA-ES-2023-74",
    )
    assert similarity < 0.82
    assert conflict


def test_name_match_cannot_replace_missing_unique_code_match():
    subject = {"cod_materia": "VGA-ES-2023-74", "codigo_materia": "401", "nombre_materia": "Seguridad"}
    teacher = {"id": 5, "email": "docente@intec.edu.ec", "confirmed": True}
    service = AsyncMock()
    service.get_all_users.return_value = [teacher]
    service.get_user_courses.return_value = [
        {"id": 10, "fullname": "VGA-ES-2023-74 - Seguridad"},
        {"id": 11, "fullname": "Seguridad - Aula del docente"},
    ]
    service.get_course_enrolled_users.side_effect = lambda course_id, **_: [
        {**teacher, "role_shortnames": ["student" if course_id == 10 else "editingteacher"]}
    ]
    with (
        patch.object(portal, "_teacher_subject_assignment", return_value=subject),
        patch.object(portal, "teacher_profile", return_value={"teacher": {"correo": teacher["email"]}}),
    ):
        matches = asyncio.run(portal._teacher_subject_moodle_courses(None, "VGA-ES-2023-74", service=service))
    assert matches == []


def test_name_match_remains_available_without_unique_subject_code():
    subject = {"cod_materia": "", "codigo_materia": "401", "nombre_materia": "Seguridad"}
    teacher = {"id": 5, "email": "docente@intec.edu.ec", "confirmed": True}
    service = AsyncMock()
    service.get_all_users.return_value = [teacher]
    service.get_user_courses.return_value = [{"id": 11, "fullname": "Seguridad - Aula del docente"}]
    service.get_course_enrolled_users.return_value = [{**teacher, "role_shortnames": ["editingteacher"]}]
    with (
        patch.object(portal, "_teacher_subject_assignment", return_value=subject),
        patch.object(portal, "teacher_profile", return_value={"teacher": {"correo": teacher["email"]}}),
    ):
        matches = asyncio.run(portal._teacher_subject_moodle_courses(None, "401", service=service))
    assert [item["id"] for item in matches] == [11]
