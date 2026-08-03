import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.core.security import SessionUser
from app.routers.english_exams import (
    _TEACHER_ACTIVE_ENGLISH_SCOPE_SQL,
    _TEACHER_ENROLLMENT_SCOPE_SQL,
    _aggregate_component_grade,
    _component_specs,
    _require_teacher_exam_scope,
    _reviewer_enrollments,
    _reviewer_periods,
    _reviewer_subjects,
    _reviewer_scope_filter,
    _select_reviewer_period,
    _select_reviewer_subject,
    _virtual_exam_payload,
)


class EnglishTeacherScopeTests(unittest.TestCase):
    def test_teacher_scope_requires_assignment_and_real_student_enrollment(self):
        sql = " ".join(_TEACHER_ENROLLMENT_SCOPE_SQL.split())

        self.assertIn("INTECBDD.dbo.CARRERAXDOCENTE", sql)
        self.assertIn("INTECBDD.dbo.CARRERAXESTUD", sql)
        self.assertIn("cxe.codigo_estud", sql)
        self.assertIn("e.CodigoCarrera", sql)
        self.assertIn("e.CodigoMateria", sql)
        self.assertIn("e.CodigoPeriodo", sql)
        self.assertIn("e.CarreraXEstudNum", sql)
        self.assertIn("e.Paralelo", sql)
        self.assertIn("carrera_docente.tp_escuela", sql)
        self.assertIn("cxd.codigo_materia) = TRY_CONVERT(INT, e.CodigoMateria)", sql)

    def test_active_english_scope_uses_teacher_career_period_and_parallel(self):
        sql = " ".join(_TEACHER_ACTIVE_ENGLISH_SCOPE_SQL.split())

        self.assertIn("cxd.cod_Anio_Basica", sql)
        self.assertIn("cx.cod_anio_Basica", sql)
        self.assertIn("cxd.codigo_periodo", sql)
        self.assertIn("cx.codigo_periodo", sql)
        self.assertIn("cxd.codigo_materia", sql)
        self.assertIn("cx.codigo_materia", sql)
        self.assertIn("cxd.Paralelo", sql)
        self.assertIn("cx.Paralelo", sql)
        self.assertIn("carrera_docente.tp_escuela", sql)

    def test_all_enrollment_types_require_three_partials(self):
        self.assertEqual([item["code"] for item in _component_specs("R")], ["P1", "P2", "P3"])
        self.assertEqual([item["code"] for item in _component_specs("H")], ["P1", "P2", "P3"])

    def test_final_grade_requires_all_three_partials(self):
        self.assertIsNone(_aggregate_component_grade("R", {"P1": 8, "P2": 9}))
        self.assertEqual(
            _aggregate_component_grade("H", {"P1": 8, "P2": 9, "P3": 10}),
            Decimal("9.00"),
        )

    def test_teacher_list_filter_uses_authenticated_teacher_code(self):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        sql, params = _reviewer_scope_filter(user)

        self.assertEqual(sql, _TEACHER_ENROLLMENT_SCOPE_SQL)
        self.assertEqual(params, [31])

    def test_teacher_without_code_receives_empty_list_filter(self):
        user = SessionUser(login="docente@intec.edu.ec", nombres="Docente prueba", rol="DOCENTE")

        sql, params = _reviewer_scope_filter(user)

        self.assertEqual(sql, "1 = 0")
        self.assertEqual(params, [])

    def test_academic_reviewer_is_not_restricted_to_teacher_assignments(self):
        user = SessionUser(login="academico@intec.edu.ec", nombres="Académico", rol="ACADEMICO")

        sql, params = _reviewer_scope_filter(user)

        self.assertIsNone(sql)
        self.assertEqual(params, [])

    def test_direct_teacher_access_is_rejected_outside_assigned_career(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        with self.assertRaises(HTTPException) as context:
            _require_teacher_exam_scope(cursor, 99, user)

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("carrera y período", context.exception.detail)
        params = cursor.execute.call_args.args[1:]
        self.assertEqual(params, (99, 31))

    def test_direct_teacher_access_is_allowed_inside_assigned_career(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        _require_teacher_exam_scope(cursor, 99, user)

        cursor.execute.assert_called_once()

    def test_latest_available_period_is_selected_initially(self):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )
        periods = [
            {"code": "1032", "label": "Periodo 1032"},
            {"code": "1031", "label": "Periodo 1031"},
        ]

        self.assertEqual(_select_reviewer_period(periods, "", user), "1032")
        self.assertEqual(_select_reviewer_period(periods, "1031", user), "1031")

    def test_teacher_cannot_select_period_outside_assignments(self):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=31,
        )

        with self.assertRaises(HTTPException) as context:
            _select_reviewer_period([{"code": "1032"}], "1010", user)

        self.assertEqual(context.exception.status_code, 403)

    def test_period_catalog_prefers_real_active_enrollment_count(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            SimpleNamespace(
                codigo_periodo="1060",
                detalle_periodo="C1-2026-PCFF ABRIL 2026 - AGOSTO 2026",
                periodo_orden=1060,
                total_estudiantes=95,
            ),
        ]
        user = SessionUser(login="admin", nombres="Administrador", rol="ADMINISTRADOR")

        periods = _reviewer_periods(cursor, user)

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["code"], "1060")
        self.assertEqual(periods[0]["student_count"], 95)
        self.assertEqual(cursor.execute.call_count, 1)
        query = " ".join(cursor.execute.call_args.args[0].split())
        self.assertIn("INTECBDD.dbo.CARRERAXESTUD", query)
        self.assertNotIn("ing.ExamenIngles", query)
        self.assertNotIn("A2+ - INTERMEDIATE", cursor.execute.call_args.args)

    def test_subject_catalog_uses_current_enrollment_and_exact_teacher_subject(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            SimpleNamespace(
                codigo_materia="333",
                nombre_materia="A2 - PRE-INTERMEDIATE",
                total_estudiantes=95,
            ),
        ]
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=100,
        )

        subjects = _reviewer_subjects(cursor, "1060", user)

        self.assertEqual(subjects[0]["code"], "333")
        self.assertEqual(subjects[0]["student_count"], 95)
        query = " ".join(cursor.execute.call_args.args[0].split())
        self.assertIn("cxd.codigo_materia", query)
        self.assertIn("cx.codigo_materia", query)
        self.assertEqual(cursor.execute.call_args.args[1:], ("1060", 100))

    def test_subject_selection_rejects_subject_outside_teacher_assignment(self):
        user = SessionUser(
            login="docente@intec.edu.ec",
            nombres="Docente prueba",
            rol="DOCENTE",
            codigo_doc=100,
        )

        with self.assertRaises(HTTPException) as context:
            _select_reviewer_subject([{"code": "333"}], "334", user)

        self.assertEqual(context.exception.status_code, 403)

    def test_reviewer_roster_returns_students_without_exam_deliveries(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            SimpleNamespace(
                codigo_estud=800,
                cedula="1106128380",
                estudiante="ABAD MAZA NATHALY NICOLE",
                correo="estudiante@intec.edu.ec",
                carrera_x_estud_num=5001,
                codigo_carrera=22,
                carrera_ingles="INGLES",
                codigo_materia=901,
                nivel_ingles="A2+ - INTERMEDIATE",
                codigo_periodo=1060,
                detalle_periodo="C1-2026-PCFF ABRIL 2026 - AGOSTO 2026",
                paralelo="A",
                tipo_matricula="R",
                codigo_carrera_principal=4,
                carrera="CONTABILIDAD",
            )
        ]
        user = SessionUser(login="academico", nombres="Académico", rol="ACADEMICO")

        profiles = _reviewer_enrollments(cursor, "1060", "901", user)

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["carrera_x_estud_num"], 5001)
        self.assertEqual(profiles[0]["carrera"], "CONTABILIDAD")
        query = " ".join(cursor.execute.call_args.args[0].split())
        self.assertIn("ROW_NUMBER() OVER", query)
        self.assertIn("INTECBDD.dbo.CARRERAXESTUD", query)
        self.assertNotIn("CargaExamenIngles", query)
        self.assertEqual(cursor.execute.call_args.args[1:3], ("1060", "901"))

    def test_virtual_exam_payload_marks_enrolled_student_without_delivery(self):
        profile = {
            "codigo_estud": 800,
            "cedula": "1106128380",
            "estudiante": "ABAD MAZA NATHALY NICOLE",
            "carrera_x_estud_num": 5001,
            "codigo_carrera": 22,
            "carrera_ingles": "INGLES",
            "codigo_materia": 901,
            "nivel": "A2+ - INTERMEDIATE",
            "carrera": "CONTABILIDAD",
            "codigo_carrera_principal": 4,
            "codigo_periodo": 1060,
            "detalle_periodo": "C1-2026-PCFF ABRIL 2026 - AGOSTO 2026",
            "paralelo": "A",
            "tipo_matricula": "R",
        }

        payload = _virtual_exam_payload(profile)

        self.assertIsNone(payload["exam_id"])
        self.assertEqual(payload["status"], "SIN_ENTREGA")
        self.assertEqual(payload["required_components"], 3)
        self.assertEqual(payload["submitted_components"], 0)
        self.assertEqual(payload["student"]["name"], profile["estudiante"])


if __name__ == "__main__":
    unittest.main()
