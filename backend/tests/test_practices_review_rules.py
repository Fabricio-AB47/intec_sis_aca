import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.practicas_institucionales import (
    AsignacionResponsablePracticasPayload,
    MatriculaPracticaEstudiantePayload,
    MatriculaPracticasPayload,
    _REVIEW_EXPEDIENT_STATE_BY_DECISION,
    _document_compliance_summary,
    _ensure_assigned_teacher_document_upload,
    _required_document_codes,
    _required_hours,
    _ensure_practice_upload_window,
    _review_validation_errors,
    _validate_upload_window,
    router,
)
from app.routers.titulacion import _matching_operational_completion


def document(code: str, *, loaded: bool = True) -> dict[str, object]:
    return {
        "Codigo": code,
        "Nombre": code.replace("_", " ").title(),
        "Cargado": loaded,
    }


class PracticesReviewRulesTests(unittest.TestCase):
    def test_document_progress_uses_required_documents_loaded_once(self) -> None:
        progress = _document_compliance_summary([
            {"Codigo": "A", "Cargado": True, "Validado": True},
            {"Codigo": "B", "Cargado": True, "Validado": False},
            {"Codigo": "C", "Cargado": False, "Validado": False},
            {"Codigo": "D", "Cargado": False, "Validado": False},
            {"Codigo": "E", "Cargado": False, "Validado": False},
        ])

        self.assertEqual(progress["required"], 5)
        self.assertEqual(progress["loaded"], 2)
        self.assertEqual(progress["pending_upload"], 3)
        self.assertEqual(progress["upload_percentage"], 40)
        self.assertEqual(progress["validation_percentage"], 20)

    def test_document_upload_requires_the_assigned_teacher(self) -> None:
        cursor = object()
        student = SessionUser(login="estudiante@intec.edu.ec", rol="ESTUDIANTE")
        with self.assertRaises(HTTPException) as context:
            _ensure_assigned_teacher_document_upload(cursor, 42, student)  # type: ignore[arg-type]
        self.assertEqual(context.exception.status_code, 403)

        teacher = SessionUser(login="docente@intec.edu.ec", rol="DOCENTE", codigo_doc=25)
        with patch("app.routers.practicas_institucionales._responsible_assignment") as assignment:
            assignment.return_value = {"ResponsableProcesoId": 9}
            result = _ensure_assigned_teacher_document_upload(cursor, 42, teacher)  # type: ignore[arg-type]

        self.assertEqual(result["ResponsableProcesoId"], 9)
        assignment.assert_called_once_with(cursor, 42, teacher, require_approval=False)

    def test_document_approval_waits_for_the_final_grade(self) -> None:
        self.assertEqual(_REVIEW_EXPEDIENT_STATE_BY_DECISION["APROBAR"], "EN_REVISION")
        self.assertNotEqual(_REVIEW_EXPEDIENT_STATE_BY_DECISION["APROBAR"], "APROBADO")

    def test_enrollment_and_responsible_assignment_are_separate_operations(self) -> None:
        enrollment = MatriculaPracticasPayload(
            tipo_proceso_codigo="PPF",
            codigo_periodo="1060",
            fecha_inicio_carga=date(2026, 9, 1),
            fecha_fin_carga=date(2026, 9, 30),
            estudiantes=[
                MatriculaPracticaEstudiantePayload(
                    codigo_estud=100,
                    codigo_carrera="4",
                    codigo_periodo_origen="1050",
                )
            ],
        )
        assignment = AsignacionResponsablePracticasPayload(
            tipo_proceso_codigo="PPF",
            codigo_periodo="1060",
            nombre_responsable="Docente responsable",
            codigo_docente="25",
            expediente_ids=[501],
        )

        self.assertEqual(enrollment.estudiantes[0].codigo_estud, 100)
        self.assertEqual(assignment.expediente_ids, [501])
        self.assertNotIn("codigo_docente", enrollment.model_dump())
        self.assertNotIn("estudiantes", assignment.model_dump())

        post_paths = {
            route.path
            for route in router.routes
            if "POST" in getattr(route, "methods", set())
        }
        self.assertIn("/api/practicas/admin/matriculas", post_paths)
        self.assertIn("/api/practicas/admin/matriculas/responsable", post_paths)
        self.assertIn("/api/practicas/admin/inscripciones-cumplimiento", post_paths)
        self.assertIn("/api/practicas/admin/inscripciones-cumplimiento/responsable", post_paths)

        get_paths = {
            route.path
            for route in router.routes
            if "GET" in getattr(route, "methods", set())
        }
        self.assertIn("/api/practicas/admin/docentes-activos", get_paths)

    def test_document_upload_window_rejects_invalid_ranges(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _validate_upload_window(date(2026, 9, 30), date(2026, 9, 1))

        self.assertEqual(context.exception.status_code, 400)

    def test_document_upload_window_is_inclusive_and_required(self) -> None:
        expediente = SimpleNamespace(
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 9, 30),
        )

        _ensure_practice_upload_window(expediente, date(2026, 9, 1))
        _ensure_practice_upload_window(expediente, date(2026, 9, 30))

        for current_date in (date(2026, 8, 31), date(2026, 10, 1)):
            with self.assertRaises(HTTPException) as context:
                _ensure_practice_upload_window(expediente, current_date)
            self.assertEqual(context.exception.status_code, 409)

        with self.assertRaises(HTTPException) as context:
            _ensure_practice_upload_window(
                SimpleNamespace(fecha_inicio=None, fecha_fin=None),
                date(2026, 9, 15),
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_requirements_are_process_specific(self) -> None:
        self.assertEqual(_required_hours("PPF"), 240)
        self.assertEqual(_required_hours("VIN"), 60)
        self.assertIn("CARTA_COMPROMISO", _required_document_codes("PPF"))
        self.assertIn("VIDEO_VINCULACION", _required_document_codes("VIN"))

    def test_approval_reports_every_missing_requirement(self) -> None:
        errors = _review_validation_errors(
            "APROBAR",
            120,
            240,
            [document("CARTA_COMPROMISO"), document("REGISTRO_ASISTENCIA", loaded=False)],
            False,
            None,
        )

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("REGISTRO ASISTENCIA" in error.upper() for error in errors))
        self.assertTrue(any("240" in error for error in errors))
        self.assertTrue(any("corroborar" in error.lower() for error in errors))

    def test_approval_is_allowed_only_when_requirements_are_complete(self) -> None:
        errors = _review_validation_errors(
            "APROBAR",
            240,
            240,
            [document(code) for code in _required_document_codes("PPF")],
            True,
            "Información revisada contra matrícula y evidencias.",
        )

        self.assertEqual(errors, [])

    def test_observation_and_rejection_require_a_reason(self) -> None:
        self.assertTrue(
            _review_validation_errors("OBSERVAR", 0, 240, [], False, None)
        )
        self.assertTrue(
            _review_validation_errors("RECHAZAR", 0, 240, [], False, " ")
        )
        self.assertEqual(
            _review_validation_errors(
                "OBSERVAR",
                0,
                240,
                [],
                False,
                "Debe corregir el registro de asistencia.",
            ),
            [],
        )

    def test_titulation_fallback_prefers_exact_career(self) -> None:
        completion_map = {
            ("1724036536", "4", "PPF"): {"ExpedienteId": 10, "Cumple": True},
            ("1724036536", "8", "PPF"): {"ExpedienteId": 11, "Cumple": False},
        }

        result = _matching_operational_completion(
            completion_map,
            "172-403-6536",
            "4",
            "PPF",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["ExpedienteId"], 10)  # type: ignore[index]

    def test_titulation_fallback_rejects_an_ambiguous_career(self) -> None:
        completion_map = {
            ("1724036536", "4", "VIN"): {"ExpedienteId": 20, "Cumple": True},
            ("1724036536", "8", "VIN"): {"ExpedienteId": 21, "Cumple": True},
        }

        result = _matching_operational_completion(
            completion_map,
            "1724036536",
            "",
            "VIN",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
