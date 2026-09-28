import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from app.routers import academic_enrollment as enrollment


def bulk_payload(**overrides: object) -> enrollment.AcademicBulkEnrollmentPayload:
    values = {
        "cod_anio_basica": 12,
        "source_codigo_periodo": 1033,
        "target_codigo_periodo": 1034,
        "materia_codes": [332],
    }
    values.update(overrides)
    return enrollment.AcademicBulkEnrollmentPayload(**values)


def english_pensum() -> dict[int, dict[str, object]]:
    return {
        code: {
            "codigo_materia": str(code),
            "nombre_materia": f"Ingles {level}",
            "semestre": level,
            "creditos": 3,
        }
        for level, code in enumerate((331, 332, 333, 334), start=1)
    }


SOURCE_STUDENT = {
    "codigo_estud": 100,
    "nombre_estudiante": "Estudiante de prueba",
    "cedula": "0000000000",
    "paralelo": "A",
    "num_grupo": 1,
}


class MemoryCursor:
    """Records SQL in memory; never creates a database connection."""

    def __init__(self, grade=None, source_level=1) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1
        self.source_rows = [
            SimpleNamespace(
                codigo_materia=330 + source_level,
                Semestre=source_level,
                PromedioFinal=grade,
                Promedio=10,
                PromedioAux=10,
            )
        ]

    def execute(self, statement: str, *params: object) -> "MemoryCursor":
        self.calls.append((" ".join(statement.split()), params))
        return self

    def fetchall(self) -> list:
        statement = self.calls[-1][0]
        if "FROM dbo.CARRERAXESTUD cxe" in statement:
            return self.source_rows
        if "SELECT codigo_materia, PromedioFinal, Promedio, PromedioAux" in statement:
            return self.source_rows
        raise AssertionError(f"Unexpected fetchall: {statement}")

    def fetchone(self):
        statement = self.calls[-1][0]
        if "SELECT COUNT(*) FROM dbo.CABECERA_MATRICULA" in statement:
            return (0,)
        if "SELECT TOP (1) Num_Matricula" in statement:
            return None
        raise AssertionError(f"Unexpected fetchone: {statement}")

    def subject_inserts(self) -> list[tuple[str, tuple[object, ...]]]:
        return [call for call in self.calls if "INSERT INTO dbo.CARRERAXESTUD" in call[0]]


@contextmanager
def database_scenario(*, grade=None, already_enrolled=False, next_attempt=1):
    """Replace database boundaries, retaining real preview/save business logic."""
    cursor = MemoryCursor(grade=grade)
    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    database_mocks = {
        "get_connection": Mock(return_value=connection),
        "_ensure_bulk_entities_exist": Mock(),
        "_ensure_entity_exists": Mock(),
        "_fetch_pensum_by_code": Mock(return_value=english_pensum()),
        "_fetch_bulk_source_students": Mock(return_value=[SOURCE_STUDENT]),
        "_fetch_career_name": Mock(return_value="Ingles"),
        "_fetch_consecutive_rules": Mock(return_value={}),
        "_fetch_audited_successful_subjects": Mock(return_value=set()),
        "_fetch_target_enrollment_status": Mock(
            return_value={
                "existe": already_enrolled,
                "cabeceras": int(already_enrolled),
                "materias": int(already_enrolled),
            }
        ),
        "_fetch_target_period_subjects": Mock(return_value={}),
        "_fetch_existing_codes": Mock(return_value={}),
        "_fetch_individual_prerequisite_rules": Mock(return_value={}),
        "_resolve_or_create_student_from_preinscription": Mock(return_value=True),
        "_fetch_jornada_name": Mock(return_value="Nocturno"),
        "_next_number": Mock(return_value=1),
        "_next_subject_matricula": Mock(return_value=next_attempt),
        "_create_academic_audit_header": Mock(return_value=99),
        "_insert_academic_audit_detail": Mock(),
        "_update_academic_audit_header": Mock(),
    }
    with patch.multiple(enrollment, **database_mocks):
        yield cursor, connection, database_mocks


class EnglishBulkAllowedSubjectsTests(unittest.TestCase):
    def test_english_allows_next_level_without_passing_final_grade(self) -> None:
        for grade in (None, 0, 6.99):
            with self.subTest(grade=grade):
                allowed, blocked = enrollment._bulk_allowed_subjects(
                    MemoryCursor(grade), bulk_payload(), SOURCE_STUDENT, {}, english_pensum()
                )

                self.assertEqual(allowed, [332])
                self.assertEqual(blocked, [])

    def test_other_careers_still_require_passing_final_grade(self) -> None:
        for career_code in (8, 13):
            for grade in (None, 0, 6.99):
                with self.subTest(career_code=career_code, grade=grade):
                    allowed, blocked = enrollment._bulk_allowed_subjects(
                        MemoryCursor(grade),
                        bulk_payload(cod_anio_basica=career_code),
                        SOURCE_STUDENT,
                        {},
                        english_pensum(),
                    )

                    self.assertEqual(allowed, [])
                    self.assertIn("PromedioFinal mayor o igual a 7", blocked[0]["motivo"])

    def test_other_careers_still_allow_a_passing_final_grade(self) -> None:
        allowed, blocked = enrollment._bulk_allowed_subjects(
            MemoryCursor(7),
            bulk_payload(cod_anio_basica=8),
            SOURCE_STUDENT,
            {},
            english_pensum(),
        )

        self.assertEqual(allowed, [332])
        self.assertEqual(blocked, [])

    def test_english_still_requires_exactly_the_next_level(self) -> None:
        for target_code in (331, 333):
            with self.subTest(target_code=target_code):
                allowed, blocked = enrollment._bulk_allowed_subjects(
                    MemoryCursor(),
                    bulk_payload(materia_codes=[target_code]),
                    SOURCE_STUDENT,
                    {},
                    english_pensum(),
                )

                self.assertEqual(allowed, [])
                self.assertIn("exactamente el siguiente nivel", blocked[0]["motivo"])

    def test_english_still_requires_all_target_level_subjects(self) -> None:
        pensum = english_pensum()
        pensum[335] = {"codigo_materia": "335", "semestre": 2}

        allowed, blocked = enrollment._bulk_allowed_subjects(
            MemoryCursor(), bulk_payload(), SOURCE_STUDENT, {}, pensum
        )

        self.assertEqual(allowed, [])
        self.assertIn("todas las materias del nivel de destino", blocked[0]["motivo"])

    def test_english_still_rejects_mixed_target_levels(self) -> None:
        allowed, blocked = enrollment._bulk_allowed_subjects(
            MemoryCursor(),
            bulk_payload(materia_codes=[332, 333]),
            SOURCE_STUDENT,
            {},
            english_pensum(),
        )

        self.assertEqual(allowed, [])
        self.assertIn("mismo nivel", blocked[0]["motivo"])

    def test_english_still_requires_an_identifiable_current_level(self) -> None:
        cursor = MemoryCursor()
        cursor.source_rows = []

        allowed, blocked = enrollment._bulk_allowed_subjects(
            cursor, bulk_payload(), SOURCE_STUDENT, {}, english_pensum()
        )

        self.assertEqual(allowed, [])
        self.assertIn("determinar el nivel actual", blocked[0]["motivo"])

    def test_english_still_honors_explicit_prerequisites(self) -> None:
        allowed, blocked = enrollment._bulk_allowed_subjects(
            MemoryCursor(), bulk_payload(), SOURCE_STUDENT, {332: [331]}, english_pensum()
        )

        self.assertEqual(allowed, [])
        self.assertEqual(blocked[0]["materias_previas"], ["331"])
        self.assertIn("Materia previa sin PromedioFinal aprobatorio", blocked[0]["motivo"])

    def test_english_allows_a_passed_explicit_prerequisite(self) -> None:
        allowed, blocked = enrollment._bulk_allowed_subjects(
            MemoryCursor(7), bulk_payload(), SOURCE_STUDENT, {332: [331]}, english_pensum()
        )

        self.assertEqual(allowed, [332])
        self.assertEqual(blocked, [])


class EnglishBulkOrchestrationTests(unittest.TestCase):
    def test_preview_marks_english_without_grades_ready(self) -> None:
        with database_scenario() as (cursor, _, database_mocks):
            result = enrollment._bulk_preview_with_cursor(cursor, bulk_payload())

        self.assertEqual(result["summary"]["insertar"], 1)
        self.assertEqual(result["summary"]["bloqueadas_por_prerrequisito"], 0)
        self.assertEqual(result["items"][0]["estado"], "LISTO")
        self.assertEqual(result["items"][0]["materias_insertar"][0]["codigo_materia"], "332")
        database_mocks["get_connection"].assert_not_called()
        self.assertEqual(cursor.subject_inserts(), [])

    def test_save_inserts_english_next_level_without_grades(self) -> None:
        with database_scenario() as (cursor, connection, database_mocks):
            result = enrollment.matricula_acad_bulk_save(
                bulk_payload(), SimpleNamespace(login="ADMIN")
            )

        self.assertEqual(result["summary"]["inserted"], 1)
        self.assertEqual(result["summary"]["estudiantes_procesados"], 1)
        self.assertEqual(result["preview"]["items"][0]["estado"], "LISTO")
        self.assertEqual(len(cursor.subject_inserts()), 1)
        self.assertEqual(cursor.subject_inserts()[0][1][:5], (100, 12, 332, 1034, 1))
        database_mocks["_next_subject_matricula"].assert_any_call(
            cursor, 100, 12, 332, for_update=True
        )
        connection.commit.assert_called_once_with()

    def test_preview_and_save_still_skip_existing_target_enrollment(self) -> None:
        with database_scenario(already_enrolled=True) as (cursor, connection, database_mocks):
            preview = enrollment._bulk_preview_with_cursor(cursor, bulk_payload())
            result = enrollment.matricula_acad_bulk_save(
                bulk_payload(), SimpleNamespace(login="ADMIN")
            )

        self.assertEqual(preview["summary"]["insertar"], 0)
        self.assertEqual(preview["items"][0]["estado"], "YA_MATRICULADO")
        self.assertEqual(result["summary"]["inserted"], 0)
        self.assertEqual(result["summary"]["already_enrolled_students"], 1)
        self.assertEqual(result["summary"]["existing_skipped"], 1)
        self.assertEqual(cursor.subject_inserts(), [])
        database_mocks["_next_subject_matricula"].assert_not_called()
        connection.commit.assert_called_once_with()

    def test_preview_and_save_still_block_fourth_attempt(self) -> None:
        with database_scenario(next_attempt=4) as (cursor, connection, _):
            preview = enrollment._bulk_preview_with_cursor(cursor, bulk_payload())
            result = enrollment.matricula_acad_bulk_save(
                bulk_payload(), SimpleNamespace(login="ADMIN")
            )

        self.assertEqual(preview["summary"]["insertar"], 0)
        self.assertEqual(preview["summary"]["bloqueadas_por_num_matricula"], 1)
        self.assertEqual(preview["items"][0]["estado"], "BLOQUEADO")
        self.assertEqual(result["summary"]["inserted"], 0)
        self.assertEqual(result["summary"]["blocked_by_repetition"], 1)
        self.assertEqual(cursor.subject_inserts(), [])
        connection.commit.assert_called_once_with()

    def test_preview_and_save_keep_other_careers_blocked_without_grades(self) -> None:
        with database_scenario() as (cursor, connection, _):
            payload = bulk_payload(cod_anio_basica=8)
            preview = enrollment._bulk_preview_with_cursor(cursor, payload)
            result = enrollment.matricula_acad_bulk_save(
                payload, SimpleNamespace(login="ADMIN")
            )

        self.assertEqual(preview["summary"]["insertar"], 0)
        self.assertEqual(preview["summary"]["bloqueadas_por_prerrequisito"], 1)
        self.assertEqual(preview["items"][0]["estado"], "BLOQUEADO")
        self.assertEqual(result["summary"]["inserted"], 0)
        self.assertEqual(result["summary"]["blocked_by_prerequisite"], 1)
        self.assertEqual(cursor.subject_inserts(), [])
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
