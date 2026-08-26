import unittest

from app.core.security import SessionUser
from app.services.moodle_grade_alerts import MoodleGradeAlertService


class _FakeGradeSync:
    def __init__(self, preview: dict, *, preview_error: Exception | None = None) -> None:
        self._preview = preview
        self._preview_error = preview_error

    async def catalog(self, *, refresh: bool = False) -> dict:
        return {
            "courses": [
                {
                    "id": 7,
                    "matched_course_code": "VGA-CG-2023-06",
                    "periods": [
                        {"period_code": 1034, "period_type": "R", "students": 1},
                    ],
                }
            ]
        }

    async def preview(self, **_kwargs) -> dict:
        if self._preview_error is not None:
            raise self._preview_error
        return self._preview


def _assignment(*, parallel: str = "A") -> dict:
    return {
        "teacher_code": 12,
        "teacher": "DOCENTE UNO",
        "malla_code": 8,
        "matter_code": 249,
        "period_code": 1034,
        "parallel": parallel,
        "course_code": "VGA-CG-2023-06",
        "matter": "Pensamiento crítico",
        "career": "Desarrollo de Software",
        "period_name": "C1-2026-PC-BS MAYO 2026 - SEPTIEMBRE 2026",
        "period_type": "R",
    }


def _change(*, field: str = "P1Tareas", parallel: str = "A") -> dict:
    return {
        "student_code": 31,
        "student": "ESTUDIANTE UNO",
        "identity": "1712345678",
        "moodle_email": "estudiante@intec.edu.ec",
        "period_code": 1034,
        "period": "C1-2026-PC-BS MAYO 2026 - SEPTIEMBRE 2026",
        "malla_code": 8,
        "matter_code": 249,
        "parallel": parallel,
        "matter": "Pensamiento crítico",
        "career": "Desarrollo de Software",
        "type": "R",
        "field": field,
        "incoming_grade": 0,
        "current_grade": 8,
        "previous_synced_grade": 7,
        "moodle_grade_item_id": 501,
        "moodle_grade_item": "Cuestionario P1",
        "moodle_grade_item_count": 2,
        "moodle_grade_items": ["Intento 1", "Intento 2"],
        "moodle_grade_selection": "highest_grade",
        "moodle_raw_grade": 80,
        "moodle_grade_min": 0,
        "moodle_grade_max": 100,
        "moodle_grade_raw_source": "graderaw",
        "moodle_grade_scale_source": "grademax",
        "status": "ready",
    }


def _enrollment(
    *,
    parallel: str = "A",
    email: str = "estudiante@intec.edu.ec",
    grades: dict | None = None,
) -> dict:
    row = {
        "row_id": 99,
        "student_code": 31,
        "student": "ESTUDIANTE UNO",
        "identity": "1712345678",
        "email": email,
        "period_code": 1034,
        "period": "C1-2026-PC-BS MAYO 2026 - SEPTIEMBRE 2026",
        "malla_code": 8,
        "matter_code": 249,
        "parallel": parallel,
        "course_code": "VGA-CG-2023-06",
        "matter": "Pensamiento crítico",
        "career": "Desarrollo de Software",
        "type": "R",
    }
    row.update({field: 8 for field in (
        "P1Tareas",
        "P1Proyectos",
        "P1Examen",
        "P2Tareas",
        "P2Proyectos",
        "P2Examen",
        "P3Tareas",
        "P3Proyectos",
        "P3Examen",
    )})
    row.update(grades or {})
    return row


def _preview(
    *,
    changes: list[dict] | None = None,
    warnings: list[dict] | None = None,
    course_validation: dict | None = None,
) -> dict:
    return {
        "course": {
            "id": 7,
            "name": "Pensamiento crítico - R29",
            "code": "VGA-CG-2023-06",
        },
        "selected_period_codes": [1034],
        "changes": changes or [],
        "enrollment_warnings": warnings or [],
        "course_validation": course_validation
        or {
            "selected_periods": 1,
            "academic_enrollments": 1,
            "moodle_course_users": 1,
            "matched_by_email": 1,
            "matched_by_registry": 0,
            "matched_by_data_fallback": 0,
            "missing_institutional_email": 0,
            "not_enrolled_in_course": 0,
            "ambiguous_users": 0,
        },
    }


class MoodleGradeAlertServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(
        preview: dict,
        assignments: list[dict],
        enrollments: list[dict] | None = None,
        preview_error: Exception | None = None,
    ) -> MoodleGradeAlertService:
        service = MoodleGradeAlertService(
            _FakeGradeSync(preview, preview_error=preview_error),
            cache_ttl_seconds=30,
            concurrency=1,
        )
        service._teacher_assignments = lambda _teacher_code: assignments  # type: ignore[method-assign]
        service._active_enrollments = (  # type: ignore[method-assign]
            lambda _academic_pairs: enrollments if enrollments is not None else [_enrollment()]
        )
        return service

    async def test_teacher_only_receives_exact_assignment_and_missing_components(self) -> None:
        service = self._service(_preview(changes=[_change()]), [_assignment()])

        result = await service.list_alerts(
            SessionUser(login="docente", rol="DOCENTE", codigo_doc=12)
        )

        self.assertEqual(result["scope"], "DOCENTE")
        self.assertEqual(result["summary"]["ungraded"], 1)
        self.assertEqual(result["items"][0]["teacher_codes"], [12])
        self.assertEqual(result["items"][0]["missing_sources"], ["MOODLE"])
        self.assertNotIn("P1Tareas", result["items"][0]["missing_components"])
        self.assertEqual(len(result["items"][0]["missing_components"]), 8)

    async def test_component_detail_preserves_zero_and_moodle_scale_traceability(self) -> None:
        service = self._service(_preview(changes=[_change()]), [_assignment()])

        result = await service.list_alerts(
            SessionUser(login="admin", rol="ADMINISTRADOR")
        )

        alert = result["items"][0]
        detail = next(
            item for item in alert["component_details"] if item["field"] == "P1Tareas"
        )
        self.assertTrue(detail["academic_registered"])
        self.assertEqual(detail["academic_grade"], 8.0)
        self.assertTrue(detail["moodle_registered"])
        self.assertEqual(detail["moodle_grade"], 0.0)
        self.assertEqual(detail["previous_synced_grade"], 7.0)
        self.assertEqual(detail["moodle_raw_grade"], 80.0)
        self.assertEqual(detail["moodle_grade_min"], 0.0)
        self.assertEqual(detail["moodle_grade_max"], 100.0)
        self.assertEqual(detail["moodle_grade_item_count"], 2)
        self.assertEqual(detail["moodle_grade_items"], ["Intento 1", "Intento 2"])
        self.assertEqual(detail["moodle_grade_selection"], "highest_grade")
        self.assertEqual(detail["component"], "P1 examen práctico · Tareas 30 %")

    async def test_response_includes_course_validation_and_source_totals(self) -> None:
        validation = {
            "selected_periods": 2,
            "academic_enrollments": 35,
            "moodle_course_users": 38,
            "matched_by_email": 31,
            "matched_by_registry": 2,
            "matched_by_data_fallback": 1,
            "missing_institutional_email": 1,
            "not_enrolled_in_course": 3,
            "ambiguous_users": 1,
        }
        service = self._service(
            _preview(changes=[_change()], course_validation=validation),
            [_assignment()],
        )

        result = await service.list_alerts(
            SessionUser(login="admin", rol="ADMINISTRADOR")
        )

        self.assertEqual(result["validation"], validation)
        self.assertEqual(result["summary"]["missing_moodle"], 1)
        self.assertEqual(result["summary"]["missing_intecbdd"], 0)
        self.assertEqual(result["summary"]["regular"], 1)
        self.assertEqual(result["summary"]["homologation"], 0)

    async def test_zero_grade_is_present_and_not_reported_as_missing(self) -> None:
        changes = [_change(field=field) for field in (
            "P1Tareas",
            "P1Proyectos",
            "P1Examen",
            "P2Tareas",
            "P2Proyectos",
            "P2Examen",
            "P3Tareas",
            "P3Proyectos",
            "P3Examen",
        )]
        service = self._service(_preview(changes=changes), [_assignment()])

        result = await service.list_alerts(
            SessionUser(login="docente", rol="DOCENTE", codigo_doc=12)
        )

        self.assertEqual(result["summary"]["total"], 0)

    async def test_teacher_cannot_receive_another_parallel(self) -> None:
        service = self._service(_preview(changes=[_change(parallel="A")]), [_assignment(parallel="B")])

        result = await service.list_alerts(
            SessionUser(login="docente", rol="DOCENTE", codigo_doc=12)
        )

        self.assertEqual(result["summary"]["total"], 0)

    async def test_academic_receives_identity_warning_but_teacher_does_not(self) -> None:
        warning = {
            **_change(),
            "status": "missing_institutional_email",
            "reason": "El estudiante no tiene CorreoIntec registrado",
        }
        service = self._service(_preview(warnings=[warning]), [_assignment()])

        academic = await service.list_alerts(
            SessionUser(login="academico", rol="ACADEMICO")
        )
        teacher = await service.list_alerts(
            SessionUser(login="docente", rol="DOCENTE", codigo_doc=12),
            refresh=True,
        )

        self.assertEqual(academic["summary"]["data_issues"], 1)
        self.assertTrue(any(item["kind"] == "DATOS" for item in academic["items"]))
        self.assertEqual(teacher["summary"]["data_issues"], 0)

    async def test_admin_sees_active_student_missing_in_both_sources(self) -> None:
        empty_grades = {field: None for field in (
            "P1Tareas",
            "P1Proyectos",
            "P1Examen",
            "P2Tareas",
            "P2Proyectos",
            "P2Examen",
            "P3Tareas",
            "P3Proyectos",
            "P3Examen",
        )}
        service = self._service(
            _preview(),
            [_assignment()],
            [_enrollment(grades=empty_grades)],
        )

        result = await service.list_alerts(
            SessionUser(login="admin", rol="ADMINISTRADOR")
        )

        alert = next(item for item in result["items"] if item["kind"] == "SIN_CALIFICAR")
        self.assertEqual(alert["missing_sources"], ["INTECBDD", "MOODLE"])
        self.assertEqual(len(alert["academic_missing_components"]), 9)
        self.assertEqual(len(alert["moodle_missing_components"]), 9)

    async def test_zero_is_valid_in_intecbdd_and_moodle(self) -> None:
        fields = (
            "P1Tareas",
            "P1Proyectos",
            "P1Examen",
            "P2Tareas",
            "P2Proyectos",
            "P2Examen",
            "P3Tareas",
            "P3Proyectos",
            "P3Examen",
        )
        service = self._service(
            _preview(changes=[_change(field=field) for field in fields]),
            [_assignment()],
            [_enrollment(grades={field: 0 for field in fields})],
        )

        result = await service.list_alerts(
            SessionUser(login="admin", rol="ADMINISTRADOR")
        )

        self.assertEqual(result["summary"]["ungraded"], 0)

    async def test_admin_keeps_academic_alert_when_moodle_preview_fails(self) -> None:
        empty_grades = {field: None for field in (
            "P1Tareas",
            "P1Proyectos",
            "P1Examen",
            "P2Tareas",
            "P2Proyectos",
            "P2Examen",
            "P3Tareas",
            "P3Proyectos",
            "P3Examen",
        )}
        service = self._service(
            _preview(),
            [_assignment(parallel="B")],
            [_enrollment(grades=empty_grades)],
            preview_error=RuntimeError("Moodle temporalmente no disponible"),
        )

        result = await service.list_alerts(
            SessionUser(login="admin", rol="ADMINISTRADOR")
        )

        self.assertEqual(result["summary"]["ungraded"], 1)
        self.assertEqual(result["summary"]["errors"], 1)
        self.assertEqual(result["items"][0]["missing_sources"], ["INTECBDD"])
        self.assertEqual(result["items"][0]["teacher"], "Sin docente asignado")

    async def test_teacher_does_not_receive_unassigned_academic_alert(self) -> None:
        service = self._service(
            _preview(),
            [_assignment(parallel="B")],
            [_enrollment(grades={"P1Tareas": None})],
            preview_error=RuntimeError("Moodle temporalmente no disponible"),
        )

        result = await service.list_alerts(
            SessionUser(login="docente", rol="DOCENTE", codigo_doc=12)
        )

        self.assertEqual(result["summary"]["total"], 0)

    def test_teacher_preview_jobs_only_include_periods_with_exact_assignment(self) -> None:
        courses = [
            {
                "id": 7,
                "matched_course_code": "VGA-CG-2023-06",
                "periods": [
                    {"period_code": 1034, "period_type": "R", "students": 1},
                    {"period_code": 1033, "period_type": "R", "students": 20},
                    {"period_code": 1025, "period_type": "H", "students": 3},
                ],
            }
        ]

        jobs = MoodleGradeAlertService._preview_jobs(
            courses,
            assignments=[_assignment()],
            role="DOCENTE",
        )

        self.assertEqual(jobs, [(7, [1034])])

    def test_institutional_preview_jobs_include_all_active_catalog_periods(self) -> None:
        courses = [
            {
                "id": 7,
                "matched_course_code": "VGA-CG-2023-06",
                "periods": [
                    {"period_code": 1034, "period_type": "R", "students": 1},
                    {"period_code": 1033, "period_type": "R", "students": 20},
                    {"period_code": 1025, "period_type": "H", "students": 3},
                    {"period_code": 1024, "period_type": "R", "students": 0},
                ],
            }
        ]

        jobs = MoodleGradeAlertService._preview_jobs(
            courses,
            assignments=[_assignment()],
            role="ACADÉMICO",
        )

        self.assertEqual(jobs, [(7, [1025]), (7, [1034, 1033])])

    async def test_accented_academic_role_is_supported(self) -> None:
        service = self._service(_preview(changes=[_change()]), [_assignment()])

        result = await service.list_alerts(
            SessionUser(login="academico", rol="ACADÉMICO")
        )

        self.assertEqual(result["role"], "ACADEMICO")
        self.assertEqual(result["scope"], "INSTITUCIONAL")

    async def test_cache_can_be_invalidated_after_grade_migration(self) -> None:
        service = self._service(_preview(changes=[_change()]), [_assignment()])
        await service.list_alerts(SessionUser(login="admin", rol="ADMINISTRADOR"))
        self.assertTrue(service._cache)

        service.invalidate_cache()

        self.assertFalse(service._cache)

    def test_errors_are_consolidated_by_course_and_message(self) -> None:
        errors = MoodleGradeAlertService._consolidate_errors(
            [
                {"course_id": 7, "period_codes": [1034], "message": "Sin correspondencia"},
                {"course_id": 7, "period_codes": [1033], "message": "Sin correspondencia"},
                {"course_id": 8, "period_codes": [1034], "message": "No disponible"},
            ]
        )

        self.assertEqual(
            errors,
            [
                {
                    "course_id": 7,
                    "period_codes": [1034, 1033],
                    "message": "Sin correspondencia",
                },
                {
                    "course_id": 8,
                    "period_codes": [1034],
                    "message": "No disponible",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
