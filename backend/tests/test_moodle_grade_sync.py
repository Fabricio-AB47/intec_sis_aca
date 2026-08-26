import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.moodle_grade_sync import (
    MoodleGradeSyncError,
    MoodleGradeSyncService,
    canonical_course_code,
    institutional_email_candidates,
    match_course_users_by_institutional_email,
    moodle_exam_targets,
    normalize_moodle_grade,
    normalize_period_codes,
    parse_configured_mappings,
    practical_exam_targets,
)


class MoodleGradeRuleTests(unittest.TestCase):
    class _RecordingCursor:
        def __init__(self, *, auth_user_id: int | None = 7) -> None:
            self.statements: list[str] = []
            self.parameters: list[tuple[object, ...]] = []
            self.description: list[object] = []
            self.auth_user_id = auth_user_id

        def execute(self, statement: str, *_params: object):
            self.statements.append(statement)
            self.parameters.append(_params)
            return self

        def executemany(self, _statement: str, _params: object):
            return self

        def fetchall(self) -> list[object]:
            return []

        def fetchone(self) -> tuple[int] | None:
            if self.auth_user_id is None:
                return None
            return (self.auth_user_id,)

    class _RecordingConnection:
        def __init__(self, cursor: "MoodleGradeRuleTests._RecordingCursor") -> None:
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> "MoodleGradeRuleTests._RecordingCursor":
            return self._cursor

    def test_execution_mode_identifies_periodic_change_detection(self) -> None:
        self.assertEqual(
            MoodleGradeSyncService._execution_mode(
                "TAREA_MOODLE_CAMBIOS",
                replace_existing=False,
            ),
            "AUTOMATICO_CAMBIOS",
        )

    def test_sync_log_resolves_django_user_by_login(self) -> None:
        cursor = self._RecordingCursor()
        now = datetime.now(timezone.utc)

        MoodleGradeSyncService._insert_log(
            cursor,
            started_at=now,
            finished_at=now,
            period_code=1034,
            mode="MANUAL_REEMPLAZO",
            status="COMPLETADO",
            processed=119,
            updated=119,
            errors=0,
            actor="usuario@intec.edu.ec",
            statistics={"actor": "usuario@intec.edu.ec"},
            actor_id=42,
        )

        self.assertIn("FROM dbo.auth_user", cursor.statements[0])
        self.assertEqual(
            cursor.parameters[0],
            (
                "usuario@intec.edu.ec",
                "usuario@intec.edu.ec",
                "usuario@intec.edu.ec",
            ),
        )
        self.assertEqual(cursor.parameters[-1][-1], 7)
        self.assertEqual(
            MoodleGradeSyncService._execution_mode("administrador", replace_existing=False),
            "MANUAL",
        )

    def test_sync_log_uses_null_when_login_has_no_django_user(self) -> None:
        cursor = self._RecordingCursor(auth_user_id=None)
        now = datetime.now(timezone.utc)

        MoodleGradeSyncService._insert_log(
            cursor,
            started_at=now,
            finished_at=now,
            period_code=1034,
            mode="MANUAL",
            status="COMPLETADO",
            processed=1,
            updated=1,
            errors=0,
            actor="usuario-legacy@intec.edu.ec",
            statistics={"actor": "usuario-legacy@intec.edu.ec"},
            actor_id=42,
        )

        self.assertIsNone(cursor.parameters[-1][-1])

    def test_period_selection_accepts_one_to_three_distinct_codes(self) -> None:
        self.assertEqual(normalize_period_codes(period_code=1050), [1050])
        self.assertEqual(
            normalize_period_codes(period_codes=[1050, 1048, 1050, 1046]),
            [1050, 1048, 1046],
        )

    def test_period_selection_rejects_empty_or_more_than_three_codes(self) -> None:
        with self.assertRaises(MoodleGradeSyncError):
            normalize_period_codes()
        with self.assertRaises(MoodleGradeSyncError):
            normalize_period_codes(period_codes=[1050, 1048, 1046, 1044])

    def test_preview_consolidates_students_from_three_periods_with_one_moodle_read(self) -> None:
        class FakeMoodle:
            def __init__(self) -> None:
                self.user_reads = 0
                self.grade_reads = 0

            async def get_all_courses(self, *, refresh: bool = False):
                return [{"id": 47, "displayname": "Curso", "idnumber": "VGA-CG-2023-05"}]

            async def get_course_enrolled_users(self, course_id: int, *, refresh: bool = False):
                self.user_reads += 1
                return [
                    {"id": index, "email": f"student{index}@intec.edu.ec"}
                    for index in range(1, 4)
                ]

            async def get_course_grade_items(self, course_id: int, *, refresh: bool = False):
                self.grade_reads += 1
                return []

        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
            moodle_grade_sync_apply_enabled=False,
        )
        moodle = FakeMoodle()
        service = MoodleGradeSyncService(moodle, settings)

        def enrollment(
            period_code: int,
            _course_codes: set[str],
            _institutional_emails: set[str],
        ):
            index = {1050: 1, 1048: 2, 1046: 3}[period_code]
            return [{
                "row_id": index,
                "period_type": "R",
                "period_name": f"Período {period_code}",
                "period_code": period_code,
                "student_code": index,
                "student_name": f"Estudiante {index}",
                "student_identity": f"000000000{index}",
                "registry_email": f"student{index}@intec.edu.ec",
                "data_email": "",
                "career": "Administración",
                "matter_name": "Administración General",
            }]

        service._academic_enrollments = enrollment
        service._grade_ledger = lambda *_args, **_kwargs: {}

        result = asyncio.run(
            service.preview(course_id=47, period_codes=[1050, 1048, 1046])
        )

        self.assertEqual(result["selected_period_codes"], [1050, 1048, 1046])
        self.assertEqual(len(result["periods"]), 3)
        self.assertEqual(result["course_validation"]["academic_enrollments"], 3)
        self.assertEqual(result["course_validation"]["matched_by_email"], 3)
        self.assertEqual(moodle.user_reads, 1)
        self.assertEqual(moodle.grade_reads, 1)

    def test_preview_rejects_mixed_regular_and_homologation_periods(self) -> None:
        class FakeMoodle:
            async def get_all_courses(self, *, refresh: bool = False):
                return [{"id": 47, "displayname": "Curso", "idnumber": "VGA-CG-2023-05"}]

            async def get_course_enrolled_users(self, course_id: int, *, refresh: bool = False):
                return [{"id": 1, "email": "student@intec.edu.ec"}]

        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
            moodle_grade_sync_apply_enabled=False,
        )
        service = MoodleGradeSyncService(FakeMoodle(), settings)

        def enrollment(
            period_code: int,
            _course_codes: set[str],
            _institutional_emails: set[str],
        ):
            return [{
                "row_id": period_code,
                "period_type": "R" if period_code == 1050 else "H",
                "period_name": f"Período {period_code}",
                "period_code": period_code,
                "student_name": f"Estudiante {period_code}",
            }]

        service._academic_enrollments = enrollment

        with self.assertRaisesRegex(MoodleGradeSyncError, "regular o todos a homologación"):
            asyncio.run(service.preview(course_id=47, period_codes=[1050, 1048]))

    def test_institutional_email_registry_is_the_primary_identity_source(self) -> None:
        enrollment = {
            "registry_email": " Student@intec.edu.ec ",
            "data_email": "anterior@intec.edu.ec",
        }

        self.assertEqual(
            institutional_email_candidates(enrollment),
            [("CorreosEstudIntec", "student@intec.edu.ec")],
        )

    def test_data_email_is_not_an_identity_without_registry_relation(self) -> None:
        enrollment = {
            "registry_email": "",
            "data_email": "student@intec.edu.ec",
            "institutional_email": "student@intec.edu.ec",
        }

        self.assertEqual(institutional_email_candidates(enrollment), [])

    def test_academic_queries_resolve_moodle_email_through_unique_student_code(self) -> None:
        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
        )
        service = MoodleGradeSyncService(object(), settings)

        period_cursor = self._RecordingCursor()
        with patch(
            "app.services.moodle_grade_sync.get_connection",
            return_value=self._RecordingConnection(period_cursor),
        ):
            service._academic_period_options_for_emails({"student@intec.edu.ec"})

        period_query = period_cursor.statements[-1]
        self.assertLess(
            period_query.index("INNER JOIN #MoodleInstitutionalEmails AS moodle"),
            period_query.index("INNER JOIN dbo.DATOS_ESTUD AS de"),
        )
        self.assertIn(
            "TRY_CONVERT(int, de.codigo_estud) = identity_row.student_code",
            period_query,
        )
        self.assertNotIn("de.correointec", period_query.casefold())

        enrollment_cursor = self._RecordingCursor()
        with patch(
            "app.services.moodle_grade_sync.get_connection",
            return_value=self._RecordingConnection(enrollment_cursor),
        ):
            service._academic_enrollments(
                1060,
                {"VGA-ES-2023-90"},
                {"student@intec.edu.ec"},
            )

        enrollment_query = enrollment_cursor.statements[-1]
        self.assertLess(
            enrollment_query.index("INNER JOIN #MoodleInstitutionalEmails AS moodle"),
            enrollment_query.index("INNER JOIN dbo.DATOS_ESTUD AS de"),
        )
        self.assertIn("WITH EmailRegistry AS", enrollment_query)
        self.assertIn("FROM UniqueMoodleIdentity AS email_registry", enrollment_query)
        self.assertNotIn("registry_rank = 1", enrollment_query)
        self.assertIn(
            "TRY_CONVERT(int, de.codigo_estud) = email_registry.student_code",
            enrollment_query,
        )
        self.assertIn(
            "TRY_CONVERT(int, ce.codigo_estud) = email_registry.student_code",
            enrollment_query,
        )
        self.assertNotIn("de.correointec", enrollment_query.casefold())

    def test_student_is_matched_only_with_users_from_the_selected_course(self) -> None:
        enrollment = {
            "registry_email": "student@intec.edu.ec",
            "data_email": "",
        }
        selected_course_users = {
            "student@intec.edu.ec": [
                {"id": 42, "email": "STUDENT@INTEC.EDU.EC", "fullname": "Estudiante Uno"}
            ]
        }

        users, email, source = match_course_users_by_institutional_email(
            enrollment,
            selected_course_users,
        )

        self.assertEqual([user["id"] for user in users], [42])
        self.assertEqual(email, "student@intec.edu.ec")
        self.assertEqual(source, "CorreosEstudIntec")

    def test_registry_email_prevents_matching_a_historical_data_email(self) -> None:
        enrollment = {
            "registry_email": "actual@intec.edu.ec",
            "data_email": "anterior@intec.edu.ec",
        }
        selected_course_users = {
            "actual@intec.edu.ec": [{"id": 10, "email": "actual@intec.edu.ec"}],
            "anterior@intec.edu.ec": [{"id": 11, "email": "anterior@intec.edu.ec"}],
        }

        users, email, source = match_course_users_by_institutional_email(
            enrollment,
            selected_course_users,
        )

        self.assertEqual([user["id"] for user in users], [10])
        self.assertEqual(email, "actual@intec.edu.ec")
        self.assertEqual(source, "CorreosEstudIntec")

    def test_course_context_resolves_subject_and_periods_by_correointec(self) -> None:
        class FakeMoodle:
            async def get_all_courses(self, *, refresh: bool = False):
                return [{
                    "id": 81,
                    "displayname": "Estadística Aplicada R28 - A 2026",
                    "shortname": "ESTADISTICA-R28",
                    "idnumber": "CODIGO-MOODLE-DIFERENTE",
                }]

            async def get_course_enrolled_users(self, course_id: int, *, refresh: bool = False):
                return [
                    {"id": 10, "email": "student@intec.edu.ec"},
                    {"id": 11, "username": "second@intec.edu.ec"},
                ]

        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
            moodle_grade_sync_mappings="",
        )
        service = MoodleGradeSyncService(FakeMoodle(), settings)
        captured_emails: set[str] = set()

        def academic_options(emails: set[str]):
            captured_emails.update(emails)
            return [
                {
                    "period_code": 1060,
                    "period_name": "C1-2026-PCFF",
                    "period_type": "R",
                    "course_code": "VGA-ES-2023-90",
                    "matter": "Estadística Aplicada",
                    "career": "Administración",
                    "students": 1,
                },
                {
                    "period_code": 1058,
                    "period_name": "C2-2025-PB",
                    "period_type": "R",
                    "course_code": "VGA-ES-2023-90",
                    "matter": "Estadística Aplicada",
                    "career": "Administración",
                    "students": 2,
                },
            ]

        service._academic_period_options_for_emails = academic_options

        result = asyncio.run(service.course_context(course_id=81))

        self.assertEqual(
            captured_emails,
            {"student@intec.edu.ec", "second@intec.edu.ec"},
        )
        self.assertEqual(result["identity_key"], "CorreoIntec")
        self.assertIn("CorreosEstudIntec.codestud", result["identity_relation"])
        self.assertIn("CARRERAXESTUD.codigo_estud", result["identity_relation"])
        self.assertEqual(result["match_method"], "asignatura_pensum_y_correointec")
        self.assertEqual(result["matched_course_code"], "VGA-ES-2023-90")
        self.assertEqual([period["period_code"] for period in result["periods"]], [1060, 1058])
        self.assertEqual(result["recommended_period_code"], 1058)
        self.assertEqual(result["recommended_period_codes"], [1058, 1060])
        self.assertTrue(result["has_academic_match"])

    def test_period_recommendation_uses_student_coverage_and_one_period_type(self) -> None:
        periods = [
            {"period_code": 1060, "period_type": "R", "students": 2},
            {"period_code": 1058, "period_type": "R", "students": 7},
            {"period_code": 1056, "period_type": "R", "students": 4},
            {"period_code": 1054, "period_type": "R", "students": 1},
            {"period_code": 1057, "period_type": "H", "students": 5},
        ]

        selected = MoodleGradeSyncService._recommended_period_codes(periods)

        self.assertEqual(selected, [1058, 1056, 1060])

    def test_configured_period_is_first_but_only_compatible_periods_are_selected(self) -> None:
        periods = [
            {"period_code": 1060, "period_type": "R", "students": 2},
            {"period_code": 1058, "period_type": "R", "students": 7},
            {"period_code": 1057, "period_type": "H", "students": 20},
        ]

        selected = MoodleGradeSyncService._recommended_period_codes(
            periods,
            preferred_period_code=1060,
        )

        self.assertEqual(selected, [1060, 1058])

    def test_catalog_includes_matched_and_unmatched_moodle_courses(self) -> None:
        class FakeMoodle:
            async def get_all_courses(self, *, refresh: bool = False):
                self.refresh = refresh
                return [
                    {
                        "id": 47,
                        "displayname": "Administración General",
                        "shortname": "ADM-GENERAL",
                        "idnumber": "VGA-CG-2023-05",
                    },
                    {
                        "id": 81,
                        "displayname": "Curso de inducción",
                        "shortname": "INDUCCION-2026",
                        "idnumber": "",
                    },
                ]

        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
            moodle_grade_sync_apply_enabled=False,
            moodle_grade_sync_nightly_enabled=False,
            moodle_grade_sync_mappings="",
        )
        service = MoodleGradeSyncService(FakeMoodle(), settings)
        service._academic_period_options = lambda: [
            {
                "period_code": 1050,
                "period_name": "C1-2026-PC",
                "period_type": "R",
                "course_code": "VGA-CG-2023-05",
                "matter": "Administración General",
                "career": "Administración",
                "students": 20,
            }
        ]

        result = asyncio.run(service.catalog(refresh=True))

        self.assertEqual(result["totals"], {"courses": 2, "matched": 1, "unmatched": 1})
        self.assertEqual([course["id"] for course in result["courses"]], [47, 81])
        self.assertTrue(result["courses"][0]["has_academic_match"])
        self.assertEqual(result["courses"][0]["periods"][0]["period_code"], 1050)
        self.assertFalse(result["courses"][1]["has_academic_match"])
        self.assertEqual(result["courses"][1]["periods"], [])

    def test_generic_regular_exam_is_ignored_without_partial(self) -> None:
        self.assertEqual(
            practical_exam_targets("Examen práctico", "R"),
            (),
        )
        self.assertEqual(moodle_exam_targets("Examen teórico", "R"), ())

    def test_explicit_regular_practical_exam_duplicates_into_task_and_exam(self) -> None:
        self.assertEqual(
            practical_exam_targets("Examen práctico P1", "R"),
            ("P1Tareas", "P1Examen"),
        )
        self.assertEqual(
            practical_exam_targets("Examen práctico parcial 2", "R"),
            ("P2Tareas", "P2Examen"),
        )
        self.assertEqual(
            practical_exam_targets("Examen práctico tercer parcial", "R"),
            ("P3Tareas", "P3Examen"),
        )

    def test_homologation_practical_exam_is_applied_once(self) -> None:
        self.assertEqual(
            practical_exam_targets("Examen práctico P1", "H"),
            ("practicahomo",),
        )

    def test_regular_theoretical_exam_updates_project_of_same_partial(self) -> None:
        self.assertEqual(
            moodle_exam_targets("Examen teórico P1", "R"),
            ("P1Proyectos",),
        )
        self.assertEqual(
            moodle_exam_targets("Examen teórico tercer parcial", "R"),
            ("P3Proyectos",),
        )

    def test_homologation_theoretical_exam_is_applied_once(self) -> None:
        self.assertEqual(moodle_exam_targets("Examen teórico", "H"), ("teoriaHomo",))

    def test_unrelated_grade_item_is_ignored(self) -> None:
        self.assertEqual(practical_exam_targets("Proyecto práctico P1", "R"), ())
        self.assertEqual(moodle_exam_targets("Examen P1", "R"), ())
        self.assertEqual(moodle_exam_targets("Examen teórico práctico P1", "R"), ())

    def test_enabled_quiz_without_theoretical_label_is_theoretical(self) -> None:
        self.assertEqual(
            moodle_exam_targets("Cuestionario P2", "R", "quiz"),
            ("P2Proyectos",),
        )

    def test_assignment_without_practical_label_uses_task_and_exam_components(self) -> None:
        self.assertEqual(
            moodle_exam_targets("Entrega con un nombre libre P2", "R", "assign"),
            ("P2Tareas", "P2Examen"),
        )

    def test_moodle_scale_is_normalized_to_ten(self) -> None:
        self.assertEqual(
            normalize_moodle_grade({"graderaw": 80, "grademin": 0, "grademax": 100}),
            8.0,
        )

    def test_visible_ten_point_grade_corrects_misconfigured_hundred_scale(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": 7,
                    "grademin": 0,
                    "grademax": 100,
                    "gradeformatted": "7,00",
                    "percentageformatted": "7,00 %",
                }
            ),
            7.0,
        )

    def test_visible_html_grade_corrects_misconfigured_hundred_scale(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": 9,
                    "grademin": 0,
                    "grademax": 100,
                    "gradeformatted": '<i class="icon fa fa-exclamation"></i>9,00',
                    "percentageformatted": "9,00 %",
                }
            ),
            9.0,
        )

    def test_real_hundred_point_grade_keeps_declared_scale(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": 80,
                    "grademin": 0,
                    "grademax": 100,
                    "gradeformatted": "80,00",
                    "percentageformatted": "80,00 %",
                }
            ),
            8.0,
        )

    def test_decimal_shift_on_ten_point_scale_is_recovered_from_percentage(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": "0,70",
                    "grademin": 0,
                    "grademax": 10,
                    "gradeformatted": "0,70",
                    "percentageformatted": "7,00 %",
                }
            ),
            7.0,
        )

    def test_decimal_shift_recovery_covers_eight_and_nine(self) -> None:
        for raw, percentage, expected in (
            ("0,80", "8,00 %", 8.0),
            ("0,90", "9,00 %", 9.0),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(
                    normalize_moodle_grade(
                        {
                            "graderaw": raw,
                            "grademin": 0,
                            "grademax": 10,
                            "gradeformatted": raw,
                            "percentageformatted": percentage,
                        }
                    ),
                    expected,
                )

    def test_sub_one_grade_without_decimal_shift_evidence_is_preserved(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": "0,70",
                    "grademin": 0,
                    "grademax": 10,
                    "gradeformatted": "0,70",
                }
            ),
            0.7,
        )

    def test_visible_seven_overrides_decimal_raw_grade(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": "0,70",
                    "grademin": 0,
                    "grademax": 10,
                    "gradeformatted": "7,00",
                    "percentageformatted": "7,00 %",
                }
            ),
            7.0,
        )

    def test_visible_nine_overrides_inconsistent_hundred_scale_metadata(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": "0,90",
                    "grademin": 0,
                    "grademax": 100,
                    "gradeformatted": "9,00",
                    "percentageformatted": "0,90 %",
                }
            ),
            9.0,
        )

    def test_visible_percentage_recovers_confirmed_decimal_shift(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": "0,70",
                    "grademin": 0,
                    "grademax": 10,
                    "gradeformatted": "7,00 %",
                    "percentageformatted": "7,00 %",
                }
            ),
            7.0,
        )

    def test_visible_grade_with_percentage_context_keeps_visible_ten_point_value(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": 7,
                    "grademin": 0,
                    "grademax": 100,
                    "gradeformatted": "7,00 (70,00 %)",
                    "percentageformatted": "70,00 %",
                }
            ),
            7.0,
        )

    def test_contradictory_moodle_grade_signals_are_rejected(self) -> None:
        with self.assertRaisesRegex(MoodleGradeSyncError, "contradictorios"):
            normalize_moodle_grade(
                {
                    "graderaw": 7,
                    "grademin": 0,
                    "grademax": 10,
                    "gradeformatted": "7,00",
                    "percentageformatted": "90,00 %",
                }
            )

    def test_moodle_grade_already_on_ten_keeps_its_value(self) -> None:
        self.assertEqual(
            normalize_moodle_grade({"graderaw": "8,75", "grademin": 0, "grademax": 10}),
            8.75,
        )

    def test_moodle_grade_uses_any_declared_numeric_scale(self) -> None:
        self.assertEqual(
            normalize_moodle_grade({"graderaw": 160, "grademin": 0, "grademax": 200}),
            8.0,
        )

    def test_missing_scale_uses_moodle_percentage_before_inference(self) -> None:
        self.assertEqual(
            normalize_moodle_grade(
                {
                    "graderaw": 42.5,
                    "percentageformatted": "85,00 %",
                }
            ),
            8.5,
        )

    def test_missing_scale_infers_hundred_only_for_raw_grade_above_ten(self) -> None:
        self.assertEqual(normalize_moodle_grade({"graderaw": 85}), 8.5)
        self.assertEqual(normalize_moodle_grade({"graderaw": 8.5}), 8.5)

    def test_formatted_percentage_is_used_when_raw_grade_is_missing(self) -> None:
        self.assertEqual(
            normalize_moodle_grade({"percentageformatted": "92.50%"}),
            9.25,
        )

    def test_moodle_grade_outside_declared_scale_is_rejected(self) -> None:
        with self.assertRaisesRegex(MoodleGradeSyncError, "fuera de su escala"):
            normalize_moodle_grade({"graderaw": 12, "grademin": 0, "grademax": 10})

    def test_theoretical_and_practical_grades_stay_in_their_partial(self) -> None:
        items = [
            {
                "id": 10,
                "itemname": "Examen teórico P2",
                "itemmodule": "quiz",
                "graderaw": 8,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 11,
                "itemname": "Examen práctico P2",
                "itemmodule": "assign",
                "graderaw": 9,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]
        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(selected["P2Tareas"]["grade"], 9.0)
        self.assertEqual(selected["P2Proyectos"]["grade"], 8.0)
        self.assertEqual(selected["P2Examen"]["grade"], 9.0)
        self.assertNotIn("P1Examen", selected)
        self.assertNotIn("P3Examen", selected)

    def test_highest_enabled_quiz_grade_is_selected(self) -> None:
        items = [
            {
                "id": 20,
                "itemname": "Cuestionario P1 - intento 1",
                "itemmodule": "quiz",
                "graderaw": 7,
                "grademax": 10,
                "gradeishidden": 0,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 21,
                "itemname": "Cuestionario P1 - intento 2",
                "itemmodule": "quiz",
                "graderaw": 9,
                "grademax": 10,
                "gradeishidden": 0,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(selected["P1Proyectos"]["grade"], 9.0)
        self.assertEqual(selected["P1Proyectos"]["candidate_count"], 2)
        self.assertEqual(selected["P1Proyectos"]["selection_rule"], "highest_grade")

    def test_highest_enabled_assignment_grade_is_selected(self) -> None:
        items = [
            {
                "id": 22,
                "itemname": "Tarea práctica P2 - primera entrega",
                "itemmodule": "assign",
                "graderaw": 85,
                "grademax": 100,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 23,
                "itemname": "Tarea práctica P2 - entrega final",
                "itemmodule": "assign",
                "graderaw": 9.25,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(set(selected), {"P2Tareas", "P2Examen"})
        self.assertEqual(selected["P2Tareas"]["grade"], 9.25)
        self.assertEqual(selected["P2Examen"]["grade"], 9.25)
        self.assertEqual(selected["P2Examen"]["candidate_count"], 2)
        self.assertEqual(
            selected["P2Examen"]["candidate_item_names"],
            ["Tarea práctica P2 - primera entrega", "Tarea práctica P2 - entrega final"],
        )

    def test_hidden_quiz_is_not_considered_for_maximum_grade(self) -> None:
        items = [
            {
                "id": 30,
                "itemname": "Cuestionario P3 visible",
                "itemmodule": "quiz",
                "graderaw": 8,
                "grademax": 10,
                "gradeishidden": 0,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 31,
                "itemname": "Cuestionario P3 oculto",
                "itemmodule": "quiz",
                "graderaw": 10,
                "grademax": 10,
                "gradeishidden": 1,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(selected["P3Proyectos"]["grade"], 8.0)

    def test_grade_item_outside_evaluation_section_is_ignored(self) -> None:
        items = [
            {
                "id": 40,
                "itemname": "Cuestionario P1",
                "itemmodule": "quiz",
                "graderaw": 10,
                "grademax": 10,
                "gradeishidden": 0,
                "evaluation_scope": False,
                "course_section_visible": True,
                "course_module_visible": True,
            }
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")

        self.assertEqual(errors, [])
        self.assertEqual(candidates, [])

    def test_generic_quizzes_and_assignments_are_ordered_by_module_type(self) -> None:
        items = [
            {
                "id": 50,
                "itemname": "Actividad de inicio",
                "itemmodule": "assign",
                "graderaw": 7,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 1,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 51,
                "itemname": "Comprobación de conocimientos",
                "itemmodule": "quiz",
                "graderaw": 8,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 2,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 52,
                "itemname": "Producto aplicado",
                "itemmodule": "assign",
                "graderaw": 8.5,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 3,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 53,
                "itemname": "Control intermedio",
                "itemmodule": "quiz",
                "graderaw": 9,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 4,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 54,
                "itemname": "Demostración final",
                "itemmodule": "assign",
                "graderaw": 9.5,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 5,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 55,
                "itemname": "Validación de salida",
                "itemmodule": "quiz",
                "graderaw": 10,
                "grademax": 10,
                "course_section_number": 4,
                "course_module_order": 6,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(selected["P1Examen"]["grade"], 7.0)
        self.assertEqual(selected["P2Examen"]["grade"], 8.5)
        self.assertEqual(selected["P3Examen"]["grade"], 9.5)
        self.assertEqual(selected["P1Tareas"]["grade"], 7.0)
        self.assertEqual(selected["P2Tareas"]["grade"], 8.5)
        self.assertEqual(selected["P3Tareas"]["grade"], 9.5)
        self.assertEqual(selected["P1Proyectos"]["grade"], 8.0)
        self.assertEqual(selected["P2Proyectos"]["grade"], 9.0)
        self.assertEqual(selected["P3Proyectos"]["grade"], 10.0)

    def test_section_partial_is_preferred_over_activity_name(self) -> None:
        items = [
            {
                "id": 60,
                "itemname": "Nombre libre de la entrega",
                "itemmodule": "assign",
                "graderaw": 9,
                "grademax": 10,
                "course_section_name": "Evaluación - Segundo parcial",
                "course_section_number": 5,
                "course_module_order": 1,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            }
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, _ = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(set(selected), {"P2Tareas", "P2Examen"})

    def test_only_quiz_and_assign_are_migrated_from_evaluation(self) -> None:
        items = [
            {
                "id": 70,
                "itemname": "Examen teórico P1",
                "itemmodule": "forum",
                "graderaw": 10,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 71,
                "itemname": "Cuestionario con título diferente",
                "itemmodule": "quiz",
                "graderaw": 8,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "R")
        selected, _ = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(set(selected), {"P1Proyectos"})

    def test_homologation_uses_module_type_without_activity_name(self) -> None:
        items = [
            {
                "id": 80,
                "itemname": "Actividad uno",
                "itemmodule": "quiz",
                "graderaw": 8,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 81,
                "itemname": "Evidencia final",
                "itemmodule": "assign",
                "graderaw": 9,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "H")
        selected, _ = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(selected["teoriaHomo"]["grade"], 8.0)
        self.assertEqual(selected["practicahomo"]["grade"], 9.0)

    def test_homologation_selects_highest_quiz_and_assignment_grades(self) -> None:
        items = [
            {
                "id": 82,
                "itemname": "Cuestionario inicial",
                "itemmodule": "quiz",
                "graderaw": 80,
                "grademax": 100,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 83,
                "itemname": "Cuestionario final",
                "itemmodule": "quiz",
                "graderaw": 9,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 84,
                "itemname": "Tarea inicial",
                "itemmodule": "assign",
                "graderaw": 7,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
            {
                "id": 85,
                "itemname": "Tarea final",
                "itemmodule": "assign",
                "graderaw": 8.5,
                "grademax": 10,
                "evaluation_scope": True,
                "course_section_visible": True,
                "course_module_visible": True,
            },
        ]

        candidates, errors = MoodleGradeSyncService._grade_candidates(items, "H")
        selected, conflicts = MoodleGradeSyncService._select_candidates(candidates)

        self.assertEqual(errors, [])
        self.assertEqual(conflicts, set())
        self.assertEqual(selected["teoriaHomo"]["grade"], 9.0)
        self.assertEqual(selected["practicahomo"]["grade"], 8.5)
        self.assertEqual(selected["teoriaHomo"]["candidate_count"], 2)
        self.assertEqual(selected["practicahomo"]["candidate_count"], 2)

    def test_component_percentages_match_academic_structure(self) -> None:
        self.assertEqual(MoodleGradeSyncService._component_percentage("P1Tareas"), 30)
        self.assertEqual(MoodleGradeSyncService._component_percentage("P1Proyectos"), 30)
        self.assertEqual(MoodleGradeSyncService._component_percentage("P1Examen"), 40)
        self.assertEqual(MoodleGradeSyncService._component_percentage("teoriaHomo"), 40)
        self.assertEqual(MoodleGradeSyncService._component_percentage("practicahomo"), 60)

    def test_nightly_mappings_are_deduplicated_and_validated(self) -> None:
        self.assertEqual(parse_configured_mappings("12:1050, 12:1050, 18:1051"), [(12, 1050), (18, 1051)])
        with self.assertRaises(MoodleGradeSyncError):
            parse_configured_mappings("curso:periodo")

    def test_course_code_only_trims_formatting_suffix(self) -> None:
        self.assertEqual(canonical_course_code("VGA-CG-2023-75-"), "VGA-CG-2023-75")

    def test_course_context_accepts_moodle_suffix_after_exact_pensum_code(self) -> None:
        settings = SimpleNamespace(
            moodle_enabled=True,
            moodle_reads_enabled=True,
            moodle_grade_sync_enabled=True,
        )
        service = MoodleGradeSyncService(object(), settings)
        context = service._resolve_course_context(
            {
                "shortname": "VGA-CG-2023-12-BECAS543",
                "idnumber": "VGA-CG-202423123-12-BECAS",
                "displayname": "Curso sin nombre académico",
            },
            [
                {
                    "period_code": 1034,
                    "period_name": "C1-2026-PC-BS",
                    "period_type": "R",
                    "course_code": "VGA-CG-2023-12-",
                    "matter": "Ética Profesional",
                    "career": "Administración",
                    "students": 52,
                }
            ],
        )

        self.assertTrue(context["has_academic_match"])
        self.assertEqual(context["matched_course_code"], "VGA-CG-2023-12")
        self.assertEqual(context["match_method"], "codigo_pensum_y_correointec")

    def test_existing_grade_is_protected_by_default(self) -> None:
        status, reason = MoodleGradeSyncService._change_status(
            current=7,
            incoming=9,
            previous_sync=None,
            ungraded=False,
        )

        self.assertEqual(status, "manual_conflict")
        self.assertIn("fuera de la última sincronización", reason)

    def test_existing_grade_can_be_replaced_only_when_explicitly_authorized(self) -> None:
        status, reason = MoodleGradeSyncService._change_status(
            current=7,
            incoming=9,
            previous_sync=None,
            ungraded=False,
            allow_override=True,
        )

        self.assertEqual(status, "ready_override")
        self.assertIn("Reemplazo manual autorizado", reason)

    def test_equal_grade_remains_unchanged_when_replacement_is_authorized(self) -> None:
        status, _reason = MoodleGradeSyncService._change_status(
            current=9,
            incoming=9,
            previous_sync=None,
            ungraded=False,
            allow_override=True,
        )

        self.assertEqual(status, "unchanged")

    def test_empty_grade_remains_directly_applicable(self) -> None:
        status, _reason = MoodleGradeSyncService._change_status(
            current=None,
            incoming=8.5,
            previous_sync=None,
            ungraded=True,
        )

        self.assertEqual(status, "ready")

    def test_unchanged_moodle_grade_is_not_reapplied(self) -> None:
        status, reason = MoodleGradeSyncService._change_status(
            current=None,
            incoming=8.5,
            previous_sync=8.5,
            ungraded=True,
        )

        self.assertEqual(status, "source_unchanged")
        self.assertIn("no cambió", reason)

    def test_changed_moodle_grade_replaces_its_previous_synced_value(self) -> None:
        status, reason = MoodleGradeSyncService._change_status(
            current=8.5,
            incoming=9.25,
            previous_sync=8.5,
            ungraded=False,
        )

        self.assertEqual(status, "ready")
        self.assertIn("última sincronización", reason)


if __name__ == "__main__":
    unittest.main()
