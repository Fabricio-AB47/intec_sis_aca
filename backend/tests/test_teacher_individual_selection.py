from contextlib import contextmanager
from copy import deepcopy
import re
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import academic_enrollment as academic
from app.routers import portal_academico as portal
from app.services.teacher_enrollment_scope import save_teacher_selection, teacher_selection_filter


class EnrollmentCursor:
    def __init__(self):
        self.statements = []
        self.rows = []
        self.rowcount = 0
        self.assignments = set()
        self.selections = set()
        self.enrollments = [
            {"student": student, "career": career, "subject": subject, "period": period, "parallel": parallel, "teacher": ""}
            for career, subject, period, parallel, students in (
                (7, 71, 1060, "A", (10, 20, 30, 40)),
                (12, 171, 1060, "A", (50, 60)),
                (7, 71, 1050, "A", (10,)),
                (7, 71, 1060, "B", (10,)),
                (7, 72, 1060, "A", (10,)),
            )
            for student in students
        ]

    def execute(self, statement, *params):
        self.statements.append((statement, params))
        sql = " ".join(statement.split()).upper()
        self.rows = []
        self.rowcount = 0
        if "SP_GETAPPLOCK" in sql:
            return self
        if sql.startswith("SELECT OBJECT_ID"):
            self.rows = [(123,)]
        elif "AS NOMB_MATERIA" in sql and "SELECT DISTINCT" in sql:
            period, parallel = params[:2]
            contexts = {(row["career"], row["subject"]) for row in self.enrollments
                        if row["period"] == period and row["parallel"] == parallel and row["subject"] in (71, 171)}
            self.rows = [SimpleNamespace(cod_anio_basica=career, codigo_materia=subject,
                                         Nomb_Materia="Sistemas operativos", Nombre_Basica=str(career))
                         for career, subject in sorted(contexts)]
        elif "SELECT DISTINCT TRY_CONVERT(INT, CODIGO_ESTUD)" in sql:
            self.rows = [SimpleNamespace(codigo_estud=row["student"]) for row in self.enrollments
                         if (row["career"], row["subject"], row["period"], row["parallel"]) == params]
        elif "SELECT COUNT(DISTINCT COD_PERIODO)" in sql:
            self.rows = [(len(params),)]
        elif "SELECT COUNT(*)" in sql:
            self.rows = [(int(tuple(params) in self.assignments),)]
        elif "INSERT INTO DBO.CARRERAXDOCENTE" in sql:
            self.assignments.add(tuple(params[:6]))
        elif "UPDATE DBO.CARRERAXESTUD" in sql:
            teacher, career, subject, period, parallel = params[:5]
            selected = set(params[5:]) if "CODIGO_ESTUD) IN" in sql else None
            for row in self.enrollments:
                if (row["career"], row["subject"], row["period"], row["parallel"]) == (career, subject, period, parallel):
                    if selected is None or row["student"] in selected:
                        row["teacher"] = teacher
                        self.rowcount += 1
        elif "INSERT INTO DBO.PORTAL_MATRICULA_DOCENTE_SELECCION" in sql:
            self.selections.add(tuple(params[:7]))
        elif "DELETE FROM DBO.PORTAL_MATRICULA_DOCENTE_SELECCION" in sql:
            self.selections = {key for key in self.selections if key[:6] != params}
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


def payload(codes, *, mode="INDIVIDUAL", period=1060):
    return academic.AcademicTeacherUniqueEnrollmentPayload(
        codigo_doc=31, cod_materia="VGA-CG-2023-71", codigo_periodo=period,
        paralelo="A", modo_asignacion=mode, codigos_estudiantes=codes,
    )


@pytest.mark.parametrize("codes", [[10], [10, 20, 30], [30, 10, 30]])
def test_individual_save_only_links_selected_students(codes):
    cursor = EnrollmentCursor()
    result = academic._save_teacher_unique_period_with_cursor(cursor, payload(codes))
    changed = [row for row in cursor.enrollments if row["teacher"]]
    assert {row["student"] for row in changed} == set(codes)
    assert all((row["career"], row["subject"], row["period"], row["parallel"]) == (7, 71, 1060, "A") for row in changed)
    assert result["students_linked"] == result["students_requested"] == len(set(codes))
    assert len(result["assignments"]) == 1
    assert {key[6] for key in cursor.selections} == set(codes)
    updates = [(sql, params) for sql, params in cursor.statements if "UPDATE dbo.CARRERAXESTUD" in sql]
    assert len(updates) == 1
    assert "codigo_estud) IN" in updates[0][0]
    assert set(updates[0][1][5:]) == set(codes)


def test_individual_scope_is_idempotent_and_does_not_expand_on_next_save():
    cursor = EnrollmentCursor()
    academic._save_teacher_unique_period_with_cursor(cursor, payload([10]))
    academic._save_teacher_unique_period_with_cursor(cursor, payload([10]))
    academic._save_teacher_unique_period_with_cursor(cursor, payload([20]))
    assert {row["student"] for row in cursor.enrollments if row["teacher"]} == {10, 20}
    assert {key[6] for key in cursor.selections} == {10, 20}
    assert len(cursor.assignments) == 1


@pytest.mark.parametrize("method,model,selection", [
    (academic.matricula_acad_save_teacher_unique_subject_enrollment, academic.AcademicTeacherUniqueEnrollmentPayload,
     {"cod_materia": "71", "codigo_periodo": 1060, "codigos_estudiantes": [10, 20, 30]}),
    (academic.matricula_acad_save_teacher_multi_period_enrollment, academic.AcademicTeacherMultiEnrollmentPayload,
     {"cod_materia": "71", "periodos": [{"codigo_periodo": 1060, "codigos_estudiantes": [10, 20, 30]}]}),
    (academic.matricula_acad_save_teacher_multi_subject_enrollment, academic.AcademicTeacherMultiSubjectEnrollmentPayload,
     {"materias": [{"cod_materia": "71", "periodos": [{"codigo_periodo": 1060, "codigos_estudiantes": [10, 20, 30]}]}]}),
])
def test_each_enrollment_route_preserves_the_individual_selection(method, model, selection):
    cursor = EnrollmentCursor()
    connection = Mock()
    connection.cursor.return_value = cursor

    @contextmanager
    def database():
        yield connection

    with patch.object(academic, "get_connection", database), \
         patch.object(academic, "_ensure_teacher_entities_exist", return_value={"codigo_doc": "31"}):
        result = method(model(codigo_doc=31, modo_asignacion="INDIVIDUAL", **selection), current_user=None)
    assert result["students_linked"] == 3
    assert {row["student"] for row in cursor.enrollments if row["teacher"]} == {10, 20, 30}
    assert {key[6] for key in cursor.selections} == {10, 20, 30}
    connection.commit.assert_called_once_with()


def test_failed_second_period_rolls_back_first_period_without_partial_enrollment():
    cursor = EnrollmentCursor()
    original_enrollments = deepcopy(cursor.enrollments)
    connection = Mock()
    connection.cursor.return_value = cursor

    def rollback():
        cursor.enrollments = deepcopy(original_enrollments)
        cursor.assignments.clear()
        cursor.selections.clear()

    connection.rollback.side_effect = rollback

    @contextmanager
    def database():
        yield connection

    request = academic.AcademicTeacherMultiEnrollmentPayload(
        codigo_doc=31, cod_materia="71", modo_asignacion="INDIVIDUAL", periodos=[
            {"codigo_periodo": 1060, "codigos_estudiantes": [10]},
            {"codigo_periodo": 1050, "codigos_estudiantes": [999]},
        ],
    )
    with patch.object(academic, "get_connection", database), \
         patch.object(academic, "_ensure_teacher_entities_exist", return_value={"codigo_doc": "31"}):
        with pytest.raises(HTTPException) as error:
            academic.matricula_acad_save_teacher_multi_period_enrollment(request, current_user=None)
    assert error.value.status_code == 400
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    assert cursor.enrollments == original_enrollments
    assert not cursor.assignments and not cursor.selections


def test_individual_selection_is_applied_per_career_and_subject():
    cursor = EnrollmentCursor()
    result = academic._save_teacher_unique_period_with_cursor(cursor, payload([10, 50]))
    assert {row["student"] for row in cursor.enrollments if row["teacher"]} == {10, 50}
    assert len(result["assignments"]) == 2
    assert {key[1:3] + (key[6],) for key in cursor.selections} == {(7, 71, 10), (12, 171, 50)}


@pytest.mark.parametrize("codes", [[], [999], [10, 999], [0], [-1]])
def test_invalid_selection_never_writes_assignments_or_enrollments(codes):
    cursor = EnrollmentCursor()
    with pytest.raises(HTTPException):
        academic._save_teacher_unique_period_with_cursor(cursor, payload(codes))
    assert not cursor.assignments
    assert not cursor.selections
    assert not any(row["teacher"] for row in cursor.enrollments)


@pytest.mark.parametrize("mode", ["MASIVA", "UNKNOWN", ""])
def test_low_level_writer_cannot_silently_discard_a_selection(mode):
    cursor = EnrollmentCursor()
    with pytest.raises(HTTPException):
        academic._link_teacher_to_enrolled_students(
            cursor, codigo_doc=31, cod_anio_basica=7, codigo_materia=71,
            codigo_periodo=1060, paralelo="A", modo_asignacion=mode, student_codes=[10],
        )
    assert not cursor.statements


def test_low_level_individual_writer_rejects_missing_allowlist():
    cursor = EnrollmentCursor()
    with pytest.raises(HTTPException):
        academic._link_teacher_to_enrolled_students(
            cursor, codigo_doc=31, cod_anio_basica=7, codigo_materia=71,
            codigo_periodo=1060, paralelo="A", modo_asignacion="INDIVIDUAL",
        )
    assert not cursor.statements


def test_mass_enrollment_still_requires_explicit_course_wide_intent():
    cursor = EnrollmentCursor()
    academic._save_teacher_unique_period_with_cursor(cursor, payload([10]))
    result = academic._save_teacher_unique_period_with_cursor(cursor, payload([], mode="MASIVA"))
    assert {row["student"] for row in cursor.enrollments if row["teacher"]} == {10, 20, 30, 40, 50, 60}
    assert result["students_linked"] == 6
    assert not cursor.selections
    with pytest.raises(HTTPException):
        academic._save_teacher_unique_period_with_cursor(cursor, payload([10], mode="MASIVA"))


@pytest.mark.parametrize("model,data", [
    (academic.AcademicTeacherUniqueEnrollmentPayload, {"codigo_periodo": 1060, "codigos_estudiantes": [10]}),
    (academic.AcademicTeacherMultiEnrollmentPayload, {"periodos": [{"codigo_periodo": 1060, "codigos_estudiantes": [10]}]}),
    (academic.AcademicTeacherMultiSubjectEnrollmentPayload, {"materias": [{"cod_materia": "71", "periodos": [{"codigo_periodo": 1060, "codigos_estudiantes": [10]}]}]}),
])
def test_omitted_mode_is_rejected_instead_of_defaulting_to_mass(model, data):
    with pytest.raises(ValidationError) as error:
        model(codigo_doc=31, **({"cod_materia": "71"} if model is not academic.AcademicTeacherMultiSubjectEnrollmentPayload else {}), **data)
    assert any(item["loc"] == ("modo_asignacion",) for item in error.value.errors())


def test_legacy_course_wide_route_cannot_ignore_individual_student_fields():
    with pytest.raises(ValidationError) as error:
        academic.AcademicTeacherEnrollmentPayload(
            codigo_doc=31, cod_anio_basica=7, codigo_materia=71, codigo_periodo=1060,
            codigos_estudiantes=[10], modo_asignacion="INDIVIDUAL",
        )
    assert {item["loc"][0] for item in error.value.errors()} == {"codigos_estudiantes", "modo_asignacion"}


def test_misplaced_top_level_student_selection_is_not_silently_ignored():
    with pytest.raises(ValidationError):
        academic.AcademicTeacherMultiSubjectEnrollmentPayload(
            codigo_doc=31, modo_asignacion="MASIVA", codigos_estudiantes=[10],
            materias=[{"cod_materia": "71", "periodos": [{"codigo_periodo": 1060}]}],
        )


def test_persisted_scope_is_independent_of_mutable_grade_actor():
    cursor = EnrollmentCursor()
    sql = teacher_selection_filter(cursor)
    assert "Usuario" not in sql
    for dimension in ("codigo_doc", "cod_anio_basica", "codigo_materia", "codigo_periodo", "paralelo", "cod_jornada", "codigo_estud"):
        assert f"selection.{dimension}" in sql
    assert "NOT EXISTS" in sql and "OR EXISTS" in sql
    assert "selection.codigo_estud = TRY_CONVERT(int, cxe.codigo_estud)" in sql
    cursor.rows = []
    with patch.object(cursor, "fetchone", return_value=(None,)):
        assert teacher_selection_filter(cursor) == "1 = 1"


def test_sql_membership_filter_only_returns_individually_selected_students():
    predicate = teacher_selection_filter(EnrollmentCursor())
    # Fixture values are already typed; strip SQL Server-only conversion calls.
    predicate = re.sub(r"TRY_CONVERT\((?:int|nvarchar\(100\)),\s*([\w.]+)\)", r"\1", predicate)
    with sqlite3.connect(":memory:") as connection:
        connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        connection.execute("""CREATE TABLE dbo.PORTAL_MATRICULA_DOCENTE_SELECCION (
            codigo_doc integer, cod_anio_basica integer, codigo_materia integer,
            codigo_periodo integer, paralelo text, cod_jornada integer, codigo_estud integer
        )""")
        connection.execute("""CREATE TABLE courses (
            codigo_doc integer, cod_Anio_Basica integer, codigo_materia integer,
            codigo_periodo integer, Paralelo text, Cod_Jornada integer
        )""")
        connection.execute("""CREATE TABLE students (
            codigo_estud integer, cod_anio_Basica integer, codigo_materia integer, Usuario text
        )""")
        connection.executemany("INSERT INTO courses VALUES (?, ?, ?, ?, ?, ?)", [
            (31, 7, 71, 1060, " a ", 1), (32, 7, 71, 1060, "A", 1),
            (31, 7, 71, 1050, "A", 1), (31, 7, 71, 1060, "B", 1), (31, 7, 71, 1060, "A", 2),
        ])
        connection.executemany("INSERT INTO students VALUES (?, ?, ?, ?)", [
            (10, 7, 71, "MOODLE"), (20, 7, 71, "95"), (30, 7, 71, "other"), (40, 7, 71, "31"),
        ])
        connection.executemany("INSERT INTO dbo.PORTAL_MATRICULA_DOCENTE_SELECCION VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (31, 7, 71, 1060, "A", 1, code) for code in (10, 20, 30)
        ])
        query = f"SELECT cxe.codigo_estud FROM courses cxd CROSS JOIN students cxe WHERE {predicate} AND cxd.rowid = ? ORDER BY cxe.codigo_estud"
        assert connection.execute(query, (1,)).fetchall() == [(10,), (20,), (30,)]
        connection.execute("DELETE FROM dbo.PORTAL_MATRICULA_DOCENTE_SELECCION WHERE codigo_estud != 10")
        assert connection.execute(query, (1,)).fetchall() == [(10,)]
        # Another teacher, period, parallel or jornada remains independently scoped.
        for course in range(2, 6):
            assert connection.execute(query, (course,)).fetchall() == [(10,), (20,), (30,), (40,)]
        connection.execute("UPDATE students SET Usuario = 'AUTOMATICO'")
        assert connection.execute(query, (1,)).fetchall() == [(10,)]


def test_empty_persisted_selection_cannot_remove_a_restriction():
    cursor = EnrollmentCursor()
    with pytest.raises(ValueError):
        save_teacher_selection(cursor, codigo_doc=31, cod_anio_basica=7,
                               codigo_materia=71, codigo_periodo=1060, paralelo="A",
                               cod_jornada=1, student_codes=[])
    assert not cursor.statements


@contextmanager
def connection_for(cursor):
    connection = Mock()
    connection.cursor.return_value = cursor
    yield connection


def test_enrollment_roster_honors_the_saved_individual_scope():
    cursor = EnrollmentCursor()
    with patch.object(academic, "get_connection", lambda: connection_for(cursor)):
        result = academic.matricula_acad_teacher_students(
            current_user=None, codigo_doc=31, codigo_periodo=[1060],
            cod_anio_basica=[7], codigo_materia="71", paralelo="A",
        )
    assert result["items"] == []
    sql = cursor.statements[-1][0]
    assert "WHERE (" in sql
    assert "selection.codigo_estud = TRY_CONVERT(int, cxe.codigo_estud)" in sql
    assert "ta.codigo_doc" in sql and "ta.Cod_Jornada" in sql


def test_candidate_assignment_label_uses_course_membership_not_the_grade_actor():
    cursor = EnrollmentCursor()
    with patch.object(academic, "get_connection", lambda: connection_for(cursor)):
        academic.matricula_acad_teacher_parallel_students(
            current_user=None, codigo_periodo=[1060], codigo_materia="71",
            paralelo="A", cod_anio_basica=[7], semestre=None,
        )
    sql = cursor.statements[-1][0]
    assert "assigned_teacher.codigo_doc AS codigo_docente_asignado" in sql
    assert "selection.codigo_estud = TRY_CONVERT(int, sr.codigo_estud)" in sql
    assert "FROM dbo.CARRERAXDOCENTE cxd" in sql
    assert "TRY_CONVERT(nvarchar(100), sr.Usuario) AS codigo_docente_asignado" not in sql


def teacher():
    return SimpleNamespace(id_usuario=31, codigo_usuario=31, rol="DOCENTE", login="docente@example.test")


def test_teacher_portal_and_course_counts_use_the_same_individual_scope():
    for method, kwargs in (
        (portal.teacher_courses, {}),
        (portal.teacher_course_students, {"codigo_periodo": [1060], "codigo_materia": "71", "paralelo": "A",
                                         "cod_anio_basica": 7, "cod_jornada": 1, "buscar": None}),
    ):
        cursor = EnrollmentCursor()
        with patch.object(portal, "get_connection", lambda: connection_for(cursor)), patch.object(portal, "_teacher_code", return_value=31):
            method(current_user=teacher(), **kwargs)
        sql = cursor.statements[-1][0]
        assert "selection.codigo_estud = TRY_CONVERT(int, cxe.codigo_estud)" in sql


def test_teacher_cannot_grade_an_unselected_classmate():
    cursor = EnrollmentCursor()
    cursor.rowcount = 0
    # The course assignment exists, but the guarded UPDATE affects no student.
    with patch.object(cursor, "fetchone", return_value=(123,)), \
         patch.object(portal, "get_connection", lambda: connection_for(cursor)), \
         patch.object(portal, "_teacher_code", return_value=31):
        with pytest.raises(HTTPException) as error:
            portal.teacher_save_grades(
                portal.TeacherGradePayload(codigo_estud=40, cod_anio_basica=7,
                                           codigo_materia=71, codigo_periodo=1060,
                                           paralelo="A", p1_tareas=9),
                current_user=teacher(),
            )
    assert error.value.status_code == 409
    sql, params = cursor.statements[-1]
    assert "selection.codigo_estud = TRY_CONVERT(int, cxe.codigo_estud)" in sql
    assert "EXISTS (" in sql and params[-1] == 31
