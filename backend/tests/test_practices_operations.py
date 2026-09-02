import unittest
from datetime import date, time

from pydantic import ValidationError

from app.routers.practicas_operativas import (
    ActivityPayload,
    AgreementPayload,
    ProcessConfigurationPayload,
    FinalEvaluationPayload,
    PlanPayload,
    _grade_result,
    _process_requirements,
    router,
)
from app.services.practices_operations import (
    OPERATIONS_SCHEMA_SQL,
    calculate_actor_grade,
    is_approved_practice_outcome,
    update_compliance_enrollment_status,
)


class PracticesOperationsTests(unittest.TestCase):
    def test_operational_routes_cover_the_complete_flow(self) -> None:
        paths = {route.path for route in router.routes}

        self.assertIn("/api/practicas/operaciones/dashboard", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/plan", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/actividades", paths)
        self.assertIn("/api/practicas/operaciones/actividades/{actividad_id}/revision", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/evaluacion", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/evaluaciones-actores/{rol_evaluador}", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/indicadores", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/resultado-vinculacion", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/productos-vinculacion", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/reapertura", paths)
        self.assertIn("/api/practicas/operaciones/configuraciones", paths)
        self.assertIn("/api/practicas/operaciones/expedientes/{expediente_id}/cierre", paths)
        self.assertIn("/api/practicas/operaciones/reportes/seguimiento.xlsx", paths)
        self.assertIn("/api/practicas/operaciones/reportes/seguimiento.pdf", paths)
        self.assertIn("/api/practicas/operaciones/conciliaciones/{reconciliation_id}/reintentar", paths)
        self.assertIn("/api/practicas/operaciones/auditoria", paths)

    def test_schema_contains_every_operational_entity(self) -> None:
        for table in (
            "ops.inscripcion_cumplimiento",
            "ops.configuracion_proceso",
            "ops.evaluacion_practica",
            "ops.evaluacion_actor",
            "ops.historial_calificacion",
            "ops.resultado_vinculacion",
            "ops.producto_vinculacion",
            "ops.reapertura_expediente",
            "ops.entidad_receptora",
            "ops.convenio_institucional",
            "ops.proyecto_vinculacion",
            "ops.plan_proceso",
            "ops.registro_actividad",
            "ops.meta_indicador",
            "ops.cierre_proceso",
            "ops.notificacion_proceso",
            "ops.conciliacion_titulacion",
            "ops.auditoria_operativa",
        ):
            self.assertIn(table, OPERATIONS_SCHEMA_SQL)

    def test_plan_and_agreement_reject_invalid_dates(self) -> None:
        with self.assertRaises(ValidationError):
            AgreementPayload(
                entidad_id=1,
                tipo_proceso_codigo="PPF",
                codigo_convenio="CONV-1",
                fecha_inicio=date(2026, 10, 1),
                fecha_fin=date(2026, 9, 1),
            )

        with self.assertRaises(ValidationError):
            PlanPayload(
                fecha_inicio=date(2026, 10, 1),
                fecha_fin=date(2026, 9, 1),
                horas_planificadas=240,
            )

    def test_activity_rejects_more_than_twenty_four_hours(self) -> None:
        with self.assertRaises(ValidationError):
            ActivityPayload(
                fecha_actividad=date(2026, 9, 1),
                descripcion="Actividad de prueba",
                horas=24.5,
            )

    def test_activity_calculates_hours_from_schedule_and_break(self) -> None:
        payload = ActivityPayload(
            fecha_actividad=date(2026, 9, 1),
            descripcion="Jornada de práctica",
            hora_inicio=time(8, 0),
            hora_fin=time(17, 0),
            descanso_minutos=90,
        )

        self.assertEqual(payload.horas, 7.5)

        with self.assertRaises(ValidationError):
            ActivityPayload(
                fecha_actividad=date(2026, 9, 1),
                descripcion="Jornada incompleta",
                hora_inicio=time(8, 0),
            )

    def test_student_path_reports_every_stage(self) -> None:
        documents = [
            {"Codigo": f"DOC_{index}", "Cargado": True, "Validado": True}
            for index in range(5)
        ]
        requirements = _process_requirements(
            process="PPF",
            responsible={"NombreResponsable": "Docente"},
            plan={"estado": "FINALIZADO"},
            documents=documents,
            summary={"horas_registradas": 240, "horas_validadas": 240, "pendientes": 0},
            closure={"fecha_cierre": date(2026, 9, 1)},
            reconciliation={"Estado": "COMPLETADO"},
            evaluation={"estado": "CALIFICADA", "calificacion": 9, "resultado": "APROBADO"},
        )

        self.assertEqual([item["codigo"] for item in requirements], [
            "INSCRIPCION",
            "RESPONSABLE",
            "PLAN",
            "DOCUMENTOS",
            "BITACORA",
            "EVALUACION",
            "CIERRE",
            "TITULACION",
        ])
        self.assertTrue(all(item["completo"] for item in requirements))

    def test_incomplete_path_distinguishes_pending_and_review(self) -> None:
        requirements = _process_requirements(
            process="PPF",
            responsible=None,
            plan={"estado": "BORRADOR"},
            documents=[{"Codigo": "DOC", "Cargado": True, "Validado": False}],
            summary={"horas_registradas": 10, "horas_validadas": 0, "pendientes": 1},
            closure=None,
            reconciliation=None,
        )
        status_by_code = {item["codigo"]: item["estado"] for item in requirements}

        self.assertEqual(status_by_code["RESPONSABLE"], "PENDIENTE")
        self.assertEqual(status_by_code["PLAN"], "EN_REVISION")
        self.assertEqual(status_by_code["DOCUMENTOS"], "EN_REVISION")
        self.assertEqual(status_by_code["BITACORA"], "EN_REVISION")
        self.assertEqual(status_by_code["EVALUACION"], "PENDIENTE")
        self.assertEqual(status_by_code["CIERRE"], "PENDIENTE")

    def test_vinculacion_path_requires_indicators_with_results(self) -> None:
        requirements = _process_requirements(
            process="VIN",
            responsible={"NombreResponsable": "Docente"},
            plan={"estado": "EN_EJECUCION"},
            documents=[{"Codigo": "ANEXO", "Cargado": True, "Validado": True}],
            summary={"horas_registradas": 60, "horas_validadas": 60, "pendientes": 0},
            closure=None,
            reconciliation=None,
            indicators=[{"nombre": "Beneficiarios", "meta": 20, "resultado": None}],
        )
        status_by_code = {item["codigo"]: item["estado"] for item in requirements}

        self.assertIn("INDICADORES", status_by_code)
        self.assertEqual(status_by_code["INDICADORES"], "EN_REVISION")

        complete_requirements = _process_requirements(
            process="VIN",
            responsible={"NombreResponsable": "Docente"},
            plan={"estado": "FINALIZADO"},
            documents=[{"Codigo": "ANEXO", "Cargado": True, "Validado": True}],
            summary={"horas_registradas": 60, "horas_validadas": 60, "pendientes": 0},
            closure={"fecha_cierre": date(2026, 9, 1)},
            reconciliation={"Estado": "COMPLETADO"},
            evaluation={"estado": "CALIFICADA", "calificacion": 8.5, "resultado": "APROBADO"},
            indicators=[{"nombre": "Beneficiarios", "meta": 20, "resultado": 24}],
        )
        completed_by_code = {item["codigo"]: item["estado"] for item in complete_requirements}
        self.assertEqual(completed_by_code["INDICADORES"], "COMPLETO")

    def test_final_evaluation_validates_transitions_and_grade(self) -> None:
        with self.assertRaises(ValidationError):
            FinalEvaluationPayload(accion="DEVOLVER")

        calculated_by_server = FinalEvaluationPayload(accion="CALIFICAR")
        approved = FinalEvaluationPayload(accion="CALIFICAR", calificacion=7)
        failed = FinalEvaluationPayload(
            accion="CALIFICAR",
            calificacion=6.99,
            observacion="No alcanzó la nota mínima.",
        )

        self.assertIsNone(calculated_by_server.calificacion)
        self.assertEqual(approved.calificacion, 7)
        self.assertEqual(failed.calificacion, 6.99)

    def test_process_configuration_requires_a_complete_weight_distribution(self) -> None:
        with self.assertRaises(ValidationError):
            ProcessConfigurationPayload(
                tipo_proceso_codigo="VIN",
                horas_requeridas=60,
                documentos_requeridos=5,
                nota_minima_aprobacion=7,
                requiere_evaluacion_docente=True,
                peso_docente=100,
            )

        with self.assertRaises(ValidationError):
            ProcessConfigurationPayload(
                tipo_proceso_codigo="PPF",
                horas_requeridas=240,
                documentos_requeridos=5,
                nota_minima_aprobacion=7,
                requiere_evaluacion_docente=True,
                requiere_evaluacion_tutor=True,
                peso_docente=60,
                peso_tutor=30,
            )

        valid = ProcessConfigurationPayload(
            tipo_proceso_codigo="PPF",
            horas_requeridas=240,
            documentos_requeridos=5,
            nota_minima_aprobacion=7,
            requiere_evaluacion_docente=True,
            requiere_evaluacion_tutor=True,
            peso_docente=60,
            peso_tutor=40,
        )
        self.assertEqual(valid.peso_docente + valid.peso_tutor, 100)

    def test_actor_grade_is_weighted_and_reports_missing_roles(self) -> None:
        configuration = {
            "requiere_evaluacion_docente": True,
            "requiere_evaluacion_tutor": True,
            "requiere_autoevaluacion": False,
            "peso_docente": 60,
            "peso_tutor": 40,
            "peso_autoevaluacion": 0,
        }
        grade, missing, components = calculate_actor_grade(
            configuration,
            [{"rol_evaluador": "DOCENTE_ACADEMICO", "calificacion": 8}],
        )
        self.assertIsNone(grade)
        self.assertEqual(missing, ["TUTOR_EMPRESARIAL"])
        self.assertEqual(len(components), 1)

        grade, missing, _ = calculate_actor_grade(
            configuration,
            [
                {"rol_evaluador": "DOCENTE_ACADEMICO", "calificacion": 8},
                {"rol_evaluador": "TUTOR_EMPRESARIAL", "calificacion": 10},
            ],
        )
        self.assertEqual(grade, 8.8)
        self.assertEqual(missing, [])

    def test_final_grade_derives_approval_without_ambiguity(self) -> None:
        self.assertEqual(_grade_result(10), "APROBADO")
        self.assertEqual(_grade_result(7), "APROBADO")
        self.assertEqual(_grade_result(6.99), "REPROBADO")
        self.assertEqual(_grade_result(0), "REPROBADO")

    def test_titulation_requires_approved_grade_and_confirmed_closure(self) -> None:
        approved = {
            "evaluation_state": "CALIFICADA",
            "result": "APROBADO",
            "grade": 7,
            "closed_at": date(2026, 9, 1),
        }

        self.assertTrue(is_approved_practice_outcome(**approved))
        self.assertFalse(is_approved_practice_outcome(**{**approved, "result": "REPROBADO"}))
        self.assertFalse(is_approved_practice_outcome(**{**approved, "grade": None}))
        self.assertFalse(is_approved_practice_outcome(**{**approved, "closed_at": None}))
        self.assertFalse(is_approved_practice_outcome(**{**approved, "evaluation_state": "PENDIENTE_CALIFICACION"}))

    def test_failed_evaluation_completes_titulation_as_not_applicable(self) -> None:
        requirements = _process_requirements(
            process="PPF",
            responsible={"NombreResponsable": "Docente"},
            plan={"estado": "FINALIZADO"},
            documents=[{"Codigo": "DOC", "Cargado": True, "Validado": True}],
            summary={"horas_registradas": 240, "horas_validadas": 240, "pendientes": 0},
            closure={"fecha_cierre": date(2026, 9, 1)},
            reconciliation=None,
            evaluation={"estado": "CALIFICADA", "calificacion": 5, "resultado": "REPROBADO"},
        )
        status_by_code = {item["codigo"]: item["estado"] for item in requirements}

        self.assertEqual(status_by_code["EVALUACION"], "COMPLETO")
        self.assertEqual(status_by_code["TITULACION"], "COMPLETO")

    def test_compliance_enrollment_is_isolated_from_academic_enrollment(self) -> None:
        normalized_sql = " ".join(OPERATIONS_SCHEMA_SQL.upper().split())

        self.assertIn("CK_OPS_INSCRIPCION_NO_ACADEMICA", normalized_sql)
        self.assertIn("CK_OPS_EVALUACION_CONSISTENCIA", normalized_sql)
        self.assertIn("CARRERAXESTUD_SOLO_LECTURA", normalized_sql)
        self.assertNotIn("INSERT INTO CARRERAXESTUD", normalized_sql)
        self.assertNotIn("UPDATE CARRERAXESTUD", normalized_sql)
        self.assertNotIn("DELETE FROM CARRERAXESTUD", normalized_sql)

    def test_compliance_enrollment_rejects_academic_states(self) -> None:
        with self.assertRaises(ValueError):
            update_compliance_enrollment_status(
                None,  # type: ignore[arg-type]
                expediente_id=1,
                state="MATRICULADO",
                user="test",
            )


if __name__ == "__main__":
    unittest.main()
