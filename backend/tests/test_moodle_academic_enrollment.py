import unittest
from unittest.mock import patch

from app.services.moodle_academic_enrollment import (
    MoodleAcademicEnrollmentService,
    extract_parallel_from_course_name,
)


class MoodleAcademicEnrollmentServiceTests(unittest.TestCase):
    def test_extracts_parallel_from_final_course_name_segment(self) -> None:
        course = {
            "displayname": "A1+ - ELEMENTARY ENGLISH R29 - PBS1",
            "fullname": "A1+ - ELEMENTARY ENGLISH R29 - PBS1",
        }

        self.assertEqual(extract_parallel_from_course_name(course), "PBS1")

    def test_parallel_is_not_inferred_from_period_or_middle_segment(self) -> None:
        without_parallel = {
            "displayname": "A1+ - ELEMENTARY ENGLISH R29",
            "fullname": "A1+ - ELEMENTARY ENGLISH R29",
        }
        too_long = {
            "displayname": "A1+ - ELEMENTARY ENGLISH R29 - PARALELO1",
            "fullname": "A1+ - ELEMENTARY ENGLISH R29 - PARALELO1",
        }

        self.assertEqual(extract_parallel_from_course_name(without_parallel), "")
        self.assertEqual(extract_parallel_from_course_name(too_long), "")

    def test_course_code_resolves_all_career_candidates_for_same_subject_code(self) -> None:
        course = {
            "idnumber": "VGA-ID-2023-115-BECAS PBS1 R29",
            "shortname": "VGA-ID-2023-115-BECAS PBS1 R29",
            "displayname": "A1+ - ELEMENTARY ENGLISH R29 - PBS1",
            "fullname": "A1+ - ELEMENTARY ENGLISH R29 - PBS1",
        }
        subjects = [
            {
                "career_code": 12,
                "subject_id": 332,
                "subject_code": "VGA-ID-2023-115",
                "subject_name": "A1+ - ELEMENTARY",
            },
            {
                "career_code": 20,
                "subject_id": 901,
                "subject_code": "VGA-ID-2023-115",
                "subject_name": "A1+ - ELEMENTARY",
            },
            {
                "career_code": 12,
                "subject_id": 400,
                "subject_code": "VGA-ID-2023-11",
                "subject_name": "Otra materia",
            },
        ]

        code, candidates, error = MoodleAcademicEnrollmentService._resolve_course_subjects(
            course,
            subjects,
        )

        self.assertEqual(error, "")
        self.assertEqual(code, "VGA-ID-2023-115")
        self.assertEqual({item["subject_id"] for item in candidates}, {332, 901})

    def test_ambiguous_subject_requires_one_course_career(self) -> None:
        candidates = [
            {"career_code": 12, "subject_id": 332},
            {"career_code": 20, "subject_id": 901},
        ]

        subject, error = MoodleAcademicEnrollmentService._select_course_subject(
            candidates,
            None,
        )

        self.assertIsNone(subject)
        self.assertIn("Seleccione la carrera", error)

        subject, error = MoodleAcademicEnrollmentService._select_course_subject(
            candidates,
            20,
        )

        self.assertEqual(error, "")
        self.assertIsNotNone(subject)
        self.assertEqual(subject["subject_id"], 901)

    def test_unique_subject_automatically_selects_its_career(self) -> None:
        subject, error = MoodleAcademicEnrollmentService._select_course_subject(
            [{"career_code": 12, "subject_id": 332}],
            None,
        )

        self.assertEqual(error, "")
        self.assertIsNotNone(subject)
        self.assertEqual(subject["career_code"], 12)

    def test_duplicate_institutional_email_is_blocked_without_guessing_by_name(self) -> None:
        user = {
            "email": "estudiante@intec.edu.ec",
            "username": "estudiante@intec.edu.ec",
            "idnumber": "",
            "fullname": "Estudiante de prueba",
        }
        duplicate_records = [
            {"code": 10, "name": "Uno", "state": "A"},
            {"code": 11, "name": "Dos", "state": "ACTIVO"},
        ]

        result = MoodleAcademicEnrollmentService._match_person(
            user,
            {"estudiante@intec.edu.ec": duplicate_records},
            {},
            person_kind="estudiante",
        )

        self.assertEqual(result["status"], "CORREO_AMBIGUO")
        self.assertEqual(result["record"], {})

    def test_active_student_match_ignores_duplicate_inactive_record(self) -> None:
        user = {
            "email": "estudiante@intec.edu.ec",
            "username": "estudiante@intec.edu.ec",
            "idnumber": "",
        }
        records = [
            {"code": 10, "name": "Activo", "state": "A"},
            {"code": 11, "name": "Inactivo", "state": "I"},
        ]

        result = MoodleAcademicEnrollmentService._match_person(
            user,
            {"estudiante@intec.edu.ec": records},
            {},
            person_kind="estudiante",
        )

        self.assertEqual(result["status"], "COINCIDE")
        self.assertEqual(result["record"]["code"], 10)

    def test_student_with_only_inactive_records_is_ignored(self) -> None:
        user = {
            "email": "inactivo@intec.edu.ec",
            "username": "inactivo@intec.edu.ec",
            "idnumber": "1720000000",
        }
        inactive = {"code": 12, "name": "Inactivo", "state": "I"}

        result = MoodleAcademicEnrollmentService._match_person(
            user,
            {"inactivo@intec.edu.ec": [inactive]},
            {"1720000000": [inactive]},
            person_kind="estudiante",
        )

        self.assertEqual(result["status"], "IGNORADO_ACADEMICO")
        self.assertEqual(result["record"], {})

    def test_second_subject_enrollment_is_exposed_for_review(self) -> None:
        item = {
            "student_code": 10,
            "career_code": 12,
            "subject_id": 332,
        }
        academic_preview = {
            "summary": {"bloqueadas_por_prerrequisito": 0},
            "items": [{"codigo_materia": 332, "accion": "INSERTAR"}],
        }

        with (
            patch(
                "app.services.moodle_academic_enrollment.academic._preview_with_cursor",
                return_value=academic_preview,
            ),
            patch(
                "app.services.moodle_academic_enrollment.academic._next_subject_matricula",
                return_value=2,
            ),
        ):
            MoodleAcademicEnrollmentService._validate_academic_enrollment(
                object(),  # type: ignore[arg-type]
                item,
                {"code": 1060, "enrollment_type": "R"},
                {"code": 2},
                "PBS1",
            )

        self.assertEqual(item["status"], "LISTO")
        self.assertEqual(item["enrollment_number"], 2)
        self.assertIn("segunda matrícula", item["message"])

    def test_duplicate_student_subject_in_mass_selection_is_blocked(self) -> None:
        def course(course_id: int, parallel: str) -> dict:
            return {
                "course": {"id": course_id, "name": f"Curso {parallel}"},
                "students": [
                    {
                        "status": "LISTO",
                        "student_code": 10,
                        "career_code": 12,
                        "career_name": "Inglés",
                        "subject_id": 332,
                        "subject_code": "VGA-ID-2023-115",
                        "subject_name": "A1+ - ELEMENTARY",
                        "enrollment_number": 1,
                    }
                ],
                "warnings": [],
                "errors": [],
                "academic_contexts": [],
                "ready": True,
                "summary": {
                    "ready_students": 1,
                    "existing_students": 0,
                    "blocked_students": 0,
                    "first_enrollments": 1,
                    "second_enrollments": 0,
                    "third_enrollments": 0,
                },
            }

        courses = [course(1330, "PBS1"), course(1331, "PBS2")]

        MoodleAcademicEnrollmentService._mark_duplicate_targets(courses)

        for item in courses:
            self.assertFalse(item["ready"])
            self.assertEqual(item["students"][0]["status"], "DUPLICADO_SELECCION")
            self.assertEqual(item["summary"]["ready_students"], 0)
            self.assertEqual(item["summary"]["blocked_students"], 1)
            self.assertEqual(item["summary"]["first_enrollments"], 0)

    def test_mass_apply_keeps_same_teacher_in_multiple_courses_and_all_co_teachers(self) -> None:
        class RecordingCursor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, statement: str, *params: object):
                self.calls.append((" ".join(statement.split()), params))
                return self

            def fetchone(self):
                return (0,)

        class RecordingConnection:
            def __init__(self) -> None:
                self.recording_cursor = RecordingCursor()
                self.committed = False
                self.rolled_back = False
                self.closed = False

            def cursor(self):
                return self.recording_cursor

            def commit(self) -> None:
                self.committed = True

            def rollback(self) -> None:
                self.rolled_back = True

            def close(self) -> None:
                self.closed = True

        connection = RecordingConnection()
        preview = {
            "fingerprint": "b" * 64,
            "can_apply": True,
            "period": {"code": 1060, "name": "Período", "enrollment_type": "R"},
            "jornada": {"code": 2, "name": "Nocturno"},
            "courses": [
                {
                    "course": {"id": 1330, "name": "Curso - PBS1"},
                    "parallel": "PBS1",
                    "teachers": [{"academic_code": 100, "status": "COINCIDE"}],
                    "students": [
                        {
                            "status": "LISTO",
                            "student_code": 1,
                            "career_code": 12,
                            "subject_id": 332,
                            "academic_name": "Estudiante 1",
                            "moodle_name": "Estudiante 1",
                        },
                        {
                            "status": "LISTO",
                            "student_code": 2,
                            "career_code": 12,
                            "subject_id": 332,
                            "academic_name": "Estudiante 2",
                            "moodle_name": "Estudiante 2",
                        },
                    ],
                    "academic_contexts": [{"career_code": 12, "subject_id": 332}],
                    "summary": {"blocked_students": 0},
                },
                {
                    "course": {"id": 1332, "name": "Curso - PBS3"},
                    "parallel": "PBS3",
                    "teachers": [
                        {"academic_code": 100, "status": "COINCIDE"},
                        {"academic_code": 111, "status": "COINCIDE"},
                    ],
                    "students": [
                        {
                            "status": "LISTO",
                            "student_code": 3,
                            "career_code": 12,
                            "subject_id": 333,
                            "academic_name": "Estudiante 3",
                            "moodle_name": "Estudiante 3",
                        }
                    ],
                    "academic_contexts": [{"career_code": 12, "subject_id": 333}],
                    "summary": {"blocked_students": 0},
                },
            ],
        }
        service = MoodleAcademicEnrollmentService(
            None,  # type: ignore[arg-type]
            connection_factory=lambda: connection,  # type: ignore[arg-type]
        )

        with (
            patch.object(service, "_build_preview", return_value=preview),
            patch(
                "app.services.moodle_academic_enrollment.academic._save_enrollment_with_cursor",
                return_value={"inserted": 1, "existing_skipped": 0, "blocked_by_repetition": 0},
            ) as save_enrollment,
            patch(
                "app.services.moodle_academic_enrollment.academic._link_teacher_to_enrolled_students",
                return_value=1,
            ) as link_teacher,
        ):
            result = service._apply_sync(
                [],
                1060,
                2,
                {1330: 12, 1332: 12},
                {1332: 111},
                "b" * 64,
                "administrador",
            )

        teacher_inserts = [
            call
            for call in connection.recording_cursor.calls
            if "INSERT INTO dbo.CARRERAXDOCENTE" in call[0]
        ]
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(save_enrollment.call_count, 3)
        self.assertEqual(len(teacher_inserts), 3)
        self.assertEqual(link_teacher.call_count, 2)
        self.assertEqual(link_teacher.call_args_list[0].kwargs["codigo_doc"], 100)
        self.assertEqual(link_teacher.call_args_list[1].kwargs["codigo_doc"], 111)
        self.assertEqual(result["summary"]["students_inserted"], 3)
        self.assertEqual(result["summary"]["teacher_assignments_inserted"], 3)


if __name__ == "__main__":
    unittest.main()
