from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pyodbc
import pytest

from app.core.security import SessionUser
from app.routers import direct_admission as admission
from app.routers import academic_enrollment as academic
from app.routers.document_expedients import _identification, _institutional_expedient
from app.services.graph_documents import build_expedient_folder_path, normalize_identification, _student_root_from_folder_path
from app.services.academic_student_identity import find_academic_student, same_identification


USER = SessionUser(login="operador@intec.edu.ec", rol="ACADEMICO")
PENSUM = {
    11: {"codigo_materia": "11", "nombre_materia": "Materia inicial", "semestre": 1},
    12: {"codigo_materia": "12", "nombre_materia": "Materia inicial 2", "semestre": 1},
    21: {"codigo_materia": "21", "nombre_materia": "Materia de segundo nivel", "semestre": 2},
}


def payload():
    return admission.DirectAdmissionPayload(
        solicitud_id=uuid4(),
        estudiante={"identificacion": "1724036536", "nombres": "Ana Maria", "apellidos": "Perez Lopez",
                    "correo": "ana@example.test", "sexo": 2, "estado_civil": 1, "etnia": 1},
        matricula={"cod_anio_basica": 7, "codigo_periodo": 1060, "nivel": 1,
                   "materia_codes": [11, 12], "paralelo": "A", "cod_jornada": 1},
    )


class Cursor:
    def __init__(self):
        self.statements = []
        self.rows = []
        self.previous = None
        self.conflict_source = None
        self.students = []
        self.audits = []
        self.identity_rows = []

    def execute(self, sql, *params):
        self.statements.append((sql, params))
        normalized = " ".join(sql.split()).upper()
        self.rows = []
        if normalized.startswith("SELECT CODIGO_ESTUD, CEDULA_EST, APELLIDOS_NOMBRE"):
            self.rows = self.identity_rows
        elif normalized.startswith("SELECT CONTENIDO_HASH"):
            self.rows = [self.previous] if self.previous else []
        elif "SELECT COALESCE(MAX(CODIGO)" in normalized:
            self.rows = [(99,)]
        elif normalized.startswith("SELECT TOP (1)") and self.conflict_source and f"FROM DBO.{self.conflict_source}" in normalized:
            self.rows = [(123,)]
        elif normalized.startswith("INSERT INTO DBO.DATOS_ESTUD"):
            self.students.append(params)
        elif normalized.startswith("INSERT INTO DBO.PORTAL_INGRESO_DIRECTO"):
            self.audits.append(params)
            self.previous = SimpleNamespace(contenido_hash=params[1], registrado_por=params[6], resultado_json=params[7])
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self):
        self.db_cursor = Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.snapshot = None

    def __enter__(self):
        self.snapshot = deepcopy((self.db_cursor.students, self.db_cursor.audits, self.db_cursor.previous))
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.db_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.db_cursor.students, self.db_cursor.audits, self.db_cursor.previous = deepcopy(self.snapshot)


@pytest.fixture
def setup():
    connection = Connection()
    writer = Mock(return_value={"ok": True, "inserted": 2, "num_matricula": "1", "subject_results": []})
    with (
        patch.object(admission, "get_connection", return_value=connection),
        patch.object(admission, "_validate_student_catalogs"),
        patch.object(academic, "_fetch_pensum_by_code", return_value=PENSUM),
        patch.object(academic, "_save_enrollment_with_cursor", writer),
    ):
        yield connection, writer


@pytest.mark.parametrize("field,value", [
    ("identificacion", "1724036535"), ("identificacion", "1724-036536"),
    ("identificacion", "99999999999999999999999999"),
    ("correo", "correo sin arroba"), ("correo", "ana@localhost"),
    ("correo", ".ana@example.test"), ("correo", "ana.@example.test"),
    ("correo", "ana..perez@example.test"), ("correo", "ana@-example.test"),
    ("correo_intec", "ana@example.test"), ("sexo", 0), ("etnia", -1),
    ("fecha_nacimiento", date.today().isoformat()),
    ("fecha_nacimiento", (date.today() + timedelta(days=1)).isoformat()),
    ("nombres", "12345"), ("apellidos", "a" * 69),
])
def test_student_rejects_invalid_identity_and_schema_overflow(field, value):
    data = payload().estudiante.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        admission.DirectStudentPayload(**data)


def test_normalizes_names_and_emails_without_losing_accents():
    data = payload().estudiante.model_dump()
    data.update(nombres="  Ana  Mar\u00eda ", correo=" ANA@EXAMPLE.TEST ")
    student = admission.DirectStudentPayload(**data)
    assert student.nombres == "ANA MAR\u00cdA"
    assert student.correo == "ana@example.test"


@pytest.mark.parametrize("field,value", [("nivel", 0), ("materia_codes", []), ("materia_codes", [0]),
                                         ("valor", -1), ("valor", float("nan")), ("paralelo", "ABCDE"),
                                         ("num_grupo", 0), ("cod_jornada", 0)])
def test_enrollment_rejects_invalid_fields(field, value):
    data = payload().matricula.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        admission.DirectEnrollmentPayload(**data)


@pytest.mark.parametrize("field", ["codigo_estud", "remove_unselected", "control_matricula"])
def test_client_cannot_control_student_code_or_remove_other_enrollments(field):
    data = payload().matricula.model_dump()
    data[field] = 1
    with pytest.raises(ValidationError):
        admission.DirectEnrollmentPayload(**data)


def test_creates_related_records_and_enrollment_atomically(setup):
    connection, writer = setup
    request = payload()
    result = admission.save_direct_admission(request, USER)
    assert result["codigo_estud"] == "99" and result["identificacion"] == request.estudiante.identificacion
    assert connection.commits == 1 and connection.rollbacks == 0
    saved_payload = writer.call_args.args[1]
    assert saved_payload.codigo_estud == 99
    assert saved_payload.materia_codes == [11, 12] and not saved_payload.remove_unselected
    assert saved_payload.control_matricula == 1
    sql = " ".join(statement for statement, _ in connection.db_cursor.statements)
    assert all(name in sql for name in ["INSERT INTO dbo.DATOS_ESTUD", "INSERT INTO dbo.CorreosEstudIntec",
                                        "INSERT INTO dbo.DATOSFACTURA", "INSERT INTO dbo.PORTAL_INGRESO_DIRECTO"])
    assert "WITH (UPDLOCK, HOLDLOCK)" in sql and "sp_getapplock" in sql
    assert connection.db_cursor.students[0][0:5] == (99, "1724036536", "PEREZ LOPEZ ANA MARIA", "ana@example.test", "")
    assert "'PENDIENTE'" in sql and "Password" in sql
    assert connection.db_cursor.audits[0][6] == USER.login
    for sql, params in connection.db_cursor.statements:
        assert sql.count("?") == len(params), sql


def test_email_checks_compare_both_fields_on_both_sides(setup):
    connection, _ = setup
    student = payload().estudiante
    student.correo_intec = "ana@intec.edu.ec"
    admission._ensure_new_identity(connection.db_cursor, student)
    sql, params = connection.db_cursor.statements[0]
    assert "LOWER(LTRIM(RTRIM(correo))) IN" in sql
    assert "LOWER(LTRIM(RTRIM(correointec))) IN" in sql
    assert params[-6:-2] == (student.correo, student.correo_intec, student.correo, student.correo_intec)
    sql, params = connection.db_cursor.statements[-1]
    assert "LOWER(LTRIM(RTRIM(CorreoPersonal))) IN" in sql
    assert "LOWER(LTRIM(RTRIM(CorreoIntec))) IN" in sql
    assert params == (student.correo, student.correo_intec, student.correo, student.correo_intec, None, None)


@pytest.mark.parametrize("failure", [HTTPException(409, "Prerrequisito pendiente"), pyodbc.Error("Fallo SQL"), RuntimeError("Fallo inesperado")])
def test_any_failure_rolls_back_student_and_enrollment(setup, failure):
    connection, writer = setup
    writer.side_effect = failure
    with pytest.raises(type(failure)):
        admission.save_direct_admission(payload(), USER)
    assert connection.rollbacks == 1 and connection.commits == 0
    assert connection.db_cursor.students == [] and connection.db_cursor.audits == []


def test_partial_subject_enrollment_is_not_committed(setup):
    connection, writer = setup
    writer.return_value = {"ok": True, "inserted": 1}
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(payload(), USER)
    assert error.value.status_code == 409 and connection.rollbacks == 1
    assert not connection.db_cursor.students


def test_retry_after_lost_response_does_not_repeat_any_insert(setup):
    connection, writer = setup
    request = payload()
    first = admission.save_direct_admission(request, USER)
    second = admission.save_direct_admission(request, USER)
    assert second == {**first, "reused": True}
    assert writer.call_count == 1 and len(connection.db_cursor.students) == 1
    assert len(connection.db_cursor.audits) == 1


def test_reused_request_with_different_content_is_blocked(setup):
    connection, writer = setup
    request = payload()
    admission.save_direct_admission(request, USER)
    request.matricula.paralelo = "B"
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(request, USER)
    assert error.value.status_code == 409 and writer.call_count == 1
    assert len(connection.db_cursor.students) == 1


@pytest.mark.parametrize("source", ["DATOS_ESTUD", "PREINSCRIPCION", "CORREOSESTUDINTEC"])
def test_duplicates_in_either_identity_source_block_registration(setup, source):
    connection, writer = setup
    connection.db_cursor.conflict_source = source
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(payload(), USER)
    assert error.value.status_code == 409
    writer.assert_not_called()
    assert not connection.db_cursor.students


@pytest.mark.parametrize("codes,level", [([21], 1), ([11], 2), ([999], 1)])
def test_subjects_outside_the_career_or_level_are_blocked(setup, codes, level):
    connection, writer = setup
    request = payload()
    request.matricula.materia_codes = codes
    request.matricula.nivel = level
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(request, USER)
    assert error.value.status_code == 400 and not connection.db_cursor.students
    writer.assert_not_called()


def test_later_level_uses_the_existing_prerequisite_exception_logic(setup):
    _, writer = setup
    writer.return_value = {"ok": True, "inserted": 1}
    request = payload()
    request.matricula.nivel = 2
    request.matricula.materia_codes = [21]
    request.matricula.prerequisite_exception_codes = [21]
    request.matricula.prerequisite_exception_reason = "Admisión por homologación documentada"
    admission.save_direct_admission(request, USER)
    assert writer.call_args.args[1].prerequisite_exception_codes == [21]


def test_preview_is_read_only_and_uses_a_virtual_student(setup):
    connection, writer = setup
    with patch.object(academic, "_preview_with_cursor", return_value={"summary": {"insertar": 2}}) as preview:
        result = admission.preview_direct_admission(payload(), USER)
    assert result["summary"]["insertar"] == 2
    assert preview.call_args.args[1].codigo_estud == -1
    assert preview.call_args.kwargs == {"student_pending_creation": True}
    assert not any("INSERT" in sql.upper() or "CREATE TABLE" in sql.upper() for sql, _ in connection.db_cursor.statements)
    assert connection.commits == 0 and connection.rollbacks == 1
    writer.assert_not_called()


def existing_student(**changes):
    return SimpleNamespace(**{"codigo_estud": 123, "Cedula_Est": "1724036536", "Estado": "A",
                              "Apellidos_nombre": "PEREZ LOPEZ ANA MARIA", "correo": "ana@example.test",
                              "correointec": "", **changes})


@pytest.mark.parametrize("inserted,skipped", [(2, 0), (1, 1), (0, 2)])
def test_existing_cedula_reuses_academic_student_and_keeps_existing_enrollments(setup, inserted, skipped):
    connection, writer = setup
    connection.db_cursor.identity_rows = [existing_student()]
    writer.return_value = {"ok": True, "inserted": inserted, "existing_skipped": skipped}
    result = admission.save_direct_admission(payload(), USER)
    assert result["codigo_estud"] == "123" and result["estudiante_existente"]
    assert writer.call_args.args[1].codigo_estud == 123
    assert writer.call_args.kwargs == {"student_already_resolved": True}
    assert not writer.call_args.args[1].remove_unselected
    assert not connection.db_cursor.students and connection.commits == 1
    sql = " ".join(statement for statement, _ in connection.db_cursor.statements)
    assert all(name not in sql for name in ["INSERT INTO dbo.DATOS_ESTUD", "INSERT INTO dbo.CorreosEstudIntec", "INSERT INTO dbo.DATOSFACTURA"])
    assert "UPDATE dbo.DATOS_ESTUD" not in sql
    checks = [params[-2:] for sql, params in connection.db_cursor.statements if "SELECT TOP (1)" in sql]
    assert checks == [(123, 123)] * 3


def test_existing_student_preview_uses_real_code_and_identifies_reuse(setup):
    connection, _ = setup
    connection.db_cursor.identity_rows = [existing_student()]
    with patch.object(academic, "_preview_with_cursor", return_value={"summary": {"existentes": 2}}) as preview:
        result = admission.preview_direct_admission(payload(), USER)
    assert result["estudiante"] == {"accion": "EXISTENTE", "codigo_estud": "123"}
    assert preview.call_args.args[1].codigo_estud == 123
    assert preview.call_args.kwargs == {"student_pending_creation": False}
    assert connection.rollbacks == 1 and not connection.db_cursor.students


def test_resolved_academic_student_is_not_created_again_from_preinscription():
    request = payload().matricula.academic_payload(123)
    with patch.object(academic, "_resolve_or_create_student_from_preinscription") as resolver, \
         patch.object(academic, "_ensure_entity_exists", side_effect=HTTPException(409, "Validación académica")) as ensure:
        with pytest.raises(HTTPException):
            academic._save_enrollment_with_cursor(Mock(), request, USER.login, date.today(), student_already_resolved=True)
    resolver.assert_not_called()
    assert ensure.call_args.args[1].codigo_estud == 123


@pytest.mark.parametrize("change", [{"Estado": "I"}, {"Estado": "G"}, {"Apellidos_nombre": "OTRA PERSONA"},
                                         {"Cedula_Est": "AB123456"}, {"correointec": "other@intec.edu.ec"}])
def test_same_cedula_with_inactive_or_conflicting_data_is_not_duplicated(setup, change):
    connection, writer = setup
    connection.db_cursor.identity_rows = [existing_student(**change)]
    request = payload()
    request.estudiante.correo_intec = "ana@intec.edu.ec"
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(request, USER)
    assert error.value.status_code == 409 and not connection.db_cursor.students
    writer.assert_not_called()


def test_duplicate_academic_cedula_blocks_before_creation_or_enrollment(setup):
    connection, writer = setup
    connection.db_cursor.identity_rows = [existing_student(), existing_student(codigo_estud=124)]
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(payload(), USER)
    assert error.value.status_code == 409 and not connection.db_cursor.students
    writer.assert_not_called()


def test_different_cedula_cannot_reuse_another_students_email(setup):
    connection, writer = setup
    connection.db_cursor.conflict_source = "DATOS_ESTUD"
    request = payload()
    request.estudiante.tipo_documento, request.estudiante.identificacion = 2, "AB123456"
    with pytest.raises(HTTPException) as error:
        admission.save_direct_admission(request, USER)
    assert error.value.status_code == 409 and not connection.db_cursor.students
    writer.assert_not_called()


@pytest.mark.parametrize("left,right,match", [("0805575739", "805575739", True),
                                            ("1724-036536", "1724036536", True),
                                            ("AB123456", "CD123456", False), ("", "1724036536", False)])
def test_academic_identity_comparison_preserves_passports_and_legacy_zeroes(left, right, match):
    assert same_identification(left, right) is match


def test_identity_search_checks_text_and_numeric_fields_before_any_write():
    cursor = Cursor()
    cursor.identity_rows = [existing_student(Cedula_Est="805575739")]
    assert find_academic_student(cursor, "0805575739").codigo_estud == 123
    sql, params = cursor.statements[0]
    assert "TRY_CONVERT(bigint, Cedula_Est)" in sql and "AND Cedula = ?" in sql
    assert params == ("0805575739", 805575739, 805575739, 805575739, 805575739)


def test_readonly_identity_search_does_not_hold_update_locks_during_pdf_generation():
    cursor = Cursor()
    find_academic_student(cursor, "1724036536")
    assert "UPDLOCK" not in cursor.statements[-1][0]
    find_academic_student(cursor, "1724036536", for_update=True)
    assert "UPDLOCK, HOLDLOCK" in cursor.statements[-1][0]


def test_catalog_values_and_territorial_relationships_are_validated():
    request = payload()
    catalogs = {key: [{"value": str(value), "label": key}] for key, value in
                [("Sexo", 2), ("EstadoCivil", 1), ("Etnia", 1), ("tipodocumento", 1)]}
    with patch.object(admission, "_legacy_data_update_catalogs", return_value=catalogs), patch.object(admission, "_validate_territorial_updates") as territorial:
        admission._validate_student_catalogs(Mock(), request.estudiante)
        assert territorial.call_args.args[1] == "estudiantes"
        assert "codprov" in territorial.call_args.args[3]
        request.estudiante.etnia = 999
        with pytest.raises(HTTPException) as error:
            admission._validate_student_catalogs(Mock(), request.estudiante)
        assert error.value.status_code == 400


def test_unspecified_student_data_uses_schema_defaults_and_still_validates_catalogs():
    student = admission.DirectStudentPayload(identificacion="1724036536", nombres="Ana Maria", apellidos="Perez Lopez")
    assert student.correo == student.correo_intec == ""
    assert (student.sexo, student.estado_civil, student.etnia) == (3, 6, 9)
    catalogs = {key: [{"value": str(value), "label": key}] for key, value in
                [("Sexo", 3), ("EstadoCivil", 6), ("Etnia", 9), ("tipodocumento", 1)]}
    with patch.object(admission, "_legacy_data_update_catalogs", return_value=catalogs), \
         patch.object(admission, "_validate_territorial_updates"):
        admission._validate_student_catalogs(Mock(), student)
        catalogs["Sexo"] = [{"value": "1", "label": "Hombre"}]
        with pytest.raises(HTTPException) as error:
            admission._validate_student_catalogs(Mock(), student)
    assert error.value.status_code == 400


def test_empty_personal_email_is_excluded_from_all_duplicate_email_queries():
    student = admission.DirectStudentPayload(identificacion="1724036536", nombres="Ana Maria", apellidos="Perez Lopez")
    cursor = Cursor()
    admission._ensure_new_identity(cursor, student)
    assert len(cursor.statements) == 3
    for sql, _ in cursor.statements:
        assert "IN (NULLIF(?, ''), NULLIF(?, ''))" in sql
        assert "IN (?, NULLIF(?, ''))" not in sql


def test_minimal_excel_identity_can_be_saved_without_inventing_email_or_demographic_values(setup):
    connection, writer = setup
    request = payload()
    request.estudiante = admission.DirectStudentPayload(identificacion="1724036536", nombres="Ana Maria", apellidos="Perez Lopez")
    result = admission.save_direct_admission(request, USER)
    assert result["ok"] and result["nombre_estudiante"] == "PEREZ LOPEZ ANA MARIA"
    inserted = connection.db_cursor.students[0]
    assert inserted[3:5] == ("", "")
    assert inserted[8:11] == (6, 9, 3)
    assert writer.call_args.kwargs["student_already_resolved"]
    assert connection.commits == 1 and connection.rollbacks == 0


def test_http_validation_never_enters_database_for_bad_payload(setup):
    connection, writer = setup
    app = FastAPI()
    app.include_router(admission.router)
    app.dependency_overrides[admission._ACCESS] = lambda: USER
    data = payload().model_dump(mode="json")
    data["estudiante"]["codigo_estud"] = 123
    with TestClient(app) as client:
        response = client.post("/api/students/ingreso-directo/save", json=data)
    assert response.status_code == 422 and not connection.db_cursor.statements
    writer.assert_not_called()


def test_unauthorized_profiles_cannot_access_admission():
    with patch("app.services.screen_access.role_has_screen_access", return_value=False) as access:
        dependency = admission.require_screen_access("matricula-acad/ingreso-directo")
        with pytest.raises(HTTPException) as error:
            dependency(SessionUser(login="student@example.test", rol="ESTUDIANTE"))
    assert error.value.status_code == 403
    access.assert_called_once_with("ESTUDIANTE", "matricula-acad/ingreso-directo")


def test_passport_letters_are_preserved_in_document_identity_and_roots():
    for identity in ["AB123456", "CD123456"]:
        student = payload().estudiante.model_dump()
        student.update(identificacion=identity, tipo_documento=2)
        assert admission.DirectStudentPayload(**student).identificacion == identity
        assert _identification(identity) == normalize_identification(identity) == identity
        path = build_expedient_folder_path(module_code="SECRETARIA", identification=identity,
                                            student_code=99, student_name="ANA", origin_id="EST-99")
        assert f" - {identity}/" in path
        assert _student_root_from_folder_path(path, "123456") == ""


def test_new_student_can_prepare_institutional_archive_without_a_graduation_case():
    archive = _institutional_expedient({"code": 99, "enrollment_type": "R"}, "SECRETARIA")
    assert archive["origin_id"] == "EST-99" and archive["upload_enabled"]
    assert archive["table_origin"] == "DATOS_ESTUD" and archive["institutional_archive"]
