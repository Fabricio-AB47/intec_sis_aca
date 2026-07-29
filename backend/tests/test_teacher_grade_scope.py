import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from pypdf import PdfReader
from pydantic import ValidationError
from fastapi import HTTPException

from app.routers.legacy_reports import (
    _ACTIVE_GRADE_STUDENTS_SQL,
    QUERY_BUILDERS,
    REPORTS,
    ReportGradeUpdatePayload,
    _grade_condition,
    _notas_carrera_materia_query,
    _weighted_grade_partial,
    _weighted_homologation_grade,
    update_student_grade,
)
from app.core.security import SessionUser
from app.routers.portal_academico import (
    AdminGradeCourseBatchPayload,
    AdminGradeCourseSelectionPayload,
    TeacherGradePayload,
    _admin_grade_completion,
    _courses_with_enrolled_students,
    _grade_result,
    _group_teacher_courses,
    _resolve_admin_grade_course_selections,
    _student_grade_report_pdf,
    _weighted_regular_partial,
    teacher_save_grades,
)
from app.services.grade_calculation import calculate_regular_grade_with_recovery, regular_final_with_recovery


def _course(career: str, period: str, students: int = 1) -> dict:
    return {
        "cod_anio_basica": career,
        "nombre_carrera": f"Carrera {career}",
        "codigo_periodo": period,
        "detalle_periodo": f"Periodo {period}",
        "periodo_orden": int(period),
        "codigo_materia": "101",
        "cod_materia": "VGA-CG-2023-06",
        "nombre_materia": "Materia comun",
        "paralelo": "A",
        "cod_jornada": "2",
        "es_homologacion": False,
        "total_estudiantes": students,
    }


def _selection(course: dict) -> AdminGradeCourseSelectionPayload:
    return AdminGradeCourseSelectionPayload(
        codigo_periodo=int(course["codigo_periodo"]),
        cod_anio_basica=int(course["cod_anio_basica"]),
        codigo_materia=course["cod_materia"],
        paralelo=course["paralelo"],
        cod_jornada=int(course["cod_jornada"]),
    )


class TeacherGradeScopeTests(unittest.TestCase):
    def test_admin_can_select_up_to_three_periods_of_the_same_type(self):
        available = [
            _course("10", "1028", 8),
            _course("10", "1029", 9),
            _course("10", "1030", 10),
        ]

        selected = _resolve_admin_grade_course_selections(
            available,
            [_selection(course) for course in available],
        )

        self.assertEqual([course["codigo_periodo"] for course in selected], ["1028", "1029", "1030"])

    def test_admin_period_selection_includes_all_careers_in_that_period(self):
        administration = _course("10", "1030", 12)
        finance = _course("20", "1030", 18)

        selected = _resolve_admin_grade_course_selections(
            [administration, finance],
            [_selection(administration)],
        )

        self.assertEqual({course["cod_anio_basica"] for course in selected}, {"10", "20"})
        self.assertEqual(sum(course["total_estudiantes"] for course in selected), 30)

    def test_admin_cannot_select_the_same_period_for_multiple_careers(self):
        administration = _course("10", "1030", 12)
        finance = _course("20", "1030", 18)

        with self.assertRaises(HTTPException) as context:
            _resolve_admin_grade_course_selections(
                [administration, finance],
                [_selection(administration), _selection(finance)],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("periodo diferente", context.exception.detail)

    def test_admin_cannot_mix_regular_and_homologation_periods(self):
        regular = _course("10", "1029", 9)
        homologation = _course("10", "1030", 10)
        homologation["es_homologacion"] = True
        homologation["tipo_periodo"] = "H"

        with self.assertRaises(HTTPException) as context:
            _resolve_admin_grade_course_selections(
                [regular, homologation],
                [_selection(regular), _selection(homologation)],
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("No se pueden mezclar", context.exception.detail)

    def test_admin_period_payload_rejects_a_fourth_period(self):
        courses = [_selection(_course("10", str(1028 + index), 8)) for index in range(4)]

        with self.assertRaises(ValidationError):
            AdminGradeCourseBatchPayload(courses=courses)

    def test_admin_courses_ignore_assignments_without_students(self):
        courses = _courses_with_enrolled_students([
            _course("10", "1030", 0),
            _course("10", "1031", 12),
        ])

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["codigo_periodo"], "1031")

    def test_teacher_courses_do_not_merge_different_careers(self):
        grouped = _group_teacher_courses([
            _course("10", "1030", 12),
            _course("20", "1030", 18),
        ])

        self.assertEqual(len(grouped), 2)
        self.assertEqual({item["cod_anio_basica"] for item in grouped}, {"10", "20"})
        self.assertEqual(sorted(item["total_estudiantes"] for item in grouped), [12, 18])

    def test_regular_periods_only_group_inside_same_career(self):
        grouped = _group_teacher_courses([
            _course("10", "1029", 8),
            _course("10", "1030", 9),
        ])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["codigo_periodos"], ["1030", "1029"])
        self.assertEqual(grouped[0]["total_estudiantes"], 17)

    def test_admin_grade_query_uses_exact_course_and_teacher(self):
        sql, params = _notas_carrera_materia_query(
            100,
            {
                "periodo": "1030",
                "carrera": "10",
                "buscar": "%estudiante%",
                "estado": None,
                "anio": None,
                "genero": None,
            },
        )

        self.assertIn("ce.cod_anio_Basica = pe.Cod_AnioBasica", sql)
        self.assertIn("dbo.CARRERAXDOCENTE", sql)
        self.assertIn("docente_responsable", sql)
        self.assertIn("ce.Num_Matricula", sql)
        self.assertIn("ce.NumGrupo", sql)
        self.assertIn("WHEN calculo.promedio_final >= 7 THEN 'APROBADO'", sql)
        self.assertNotIn("LTRIM(RTRIM(ce.caprueba)) AS condicion", sql)
        self.assertNotIn("pe.TipoMatricula", sql)
        self.assertIn("de.Estado", sql)
        self.assertIn("N'A', N'ACTIVO', N'ACTIVA'", sql)
        self.assertIn("de.Apellidos_nombre LIKE ?", sql)
        self.assertIn("ce.codigo_estud) = ?", sql)
        self.assertNotIn("de.Cedula_Est LIKE ?", sql)
        self.assertNotIn("pe.Nomb_Materia)) LIKE ?", sql)
        self.assertEqual(params, ["%estudiante%", "%estudiante%", None, None, None, None, None, None])

    def test_active_grade_roster_uses_dashboard_source_and_keeps_each_active_enrollment(self):
        self.assertIn("FROM dbo.TOTALESTUDMATRICCNE reporte", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("FROM matricula_cne_catalogada cne", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("WHERE cne.estado_codigo = 'A'", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("grade_summary", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("carrera_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("active.tipo_matricula", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("AS registro_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("COUNT(*) AS matriculas_activas", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("UPPER(LTRIM(RTRIM(active.carrera)))", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("MAX(active.carrera) AS carrera", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("GROUP BY active.registro_clave", _ACTIVE_GRADE_STUDENTS_SQL)
        self.assertIn("ORDER BY MAX(active.estudiante)", _ACTIVE_GRADE_STUDENTS_SQL)

    def test_grade_catalog_only_requests_student_name(self):
        self.assertEqual(REPORTS["notas_carrera_materia"]["filters"], ["buscar"])

    def test_grade_status_uses_global_seven_point_threshold(self):
        self.assertEqual(_grade_result(None), "PENDIENTE")
        self.assertEqual(_grade_result(6.99), "REPROBADO")
        self.assertEqual(_grade_result(7), "APROBADO")
        self.assertEqual(_grade_result(10), "APROBADO")

    def test_regular_partial_uses_legacy_30_30_40_weights(self):
        self.assertEqual(_weighted_regular_partial(9.5, 8, 6.5), 7.85)

    def test_recovery_replaces_only_one_tied_lowest_component(self):
        calculation = calculate_regular_grade_with_recovery(
            ((10, 10, 10), (7, 7, 10), (10, 10, 10)),
            9,
        )

        self.assertEqual(calculation.replacement, (1, 0))
        self.assertEqual(calculation.partials, (10, 8.8, 10))
        self.assertEqual(calculation.final, 9.6)

    def test_recovery_uses_component_grade_instead_of_lowest_partial_average(self):
        partials = ((6, 10, 10), (7, 7, 7), (10, 10, 10))
        calculation = calculate_regular_grade_with_recovery(partials, 10)

        self.assertEqual(calculation.replacement, (0, 0))
        self.assertEqual(calculation.partials, (10, 7, 10))
        self.assertEqual(regular_final_with_recovery(partials, 10), 9)

    def test_recovery_does_not_lower_a_component_or_complete_missing_grades(self):
        complete = ((6, 10, 10), (7, 7, 7), (10, 10, 10))
        unchanged = calculate_regular_grade_with_recovery(complete, 5)
        incomplete = calculate_regular_grade_with_recovery(
            ((10, 10, 10), (7, None, 7), (8, 8, 8)),
            9,
        )

        self.assertIsNone(unchanged.replacement)
        self.assertEqual(unchanged.final, 8.6)
        self.assertIsNone(incomplete.replacement)
        self.assertEqual(incomplete.partials, (10, None, 8))
        self.assertIsNone(incomplete.final)

    def test_grade_payloads_reject_values_outside_zero_to_ten(self):
        base = {
            "codigo_estud": 800,
            "cod_anio_basica": 10,
            "codigo_periodo": 1030,
            "codigo_materia": 101,
            "paralelo": "A",
            "num_matricula": 2,
            "num_grupo": 3,
        }
        with self.assertRaises(ValidationError):
            ReportGradeUpdatePayload(**base, p1_tareas=10.01)
        with self.assertRaises(ValidationError):
            TeacherGradePayload(**base, recuperacion=-0.01)

    @patch("app.routers.portal_academico.get_connection")
    def test_teacher_update_recalculates_loaded_grades_from_one_lowest_component(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchone.return_value = (1,)
        cursor.rowcount = 1
        get_connection.return_value = connection

        result = teacher_save_grades(
            TeacherGradePayload(
                codigo_estud=800,
                cod_anio_basica=10,
                codigo_periodo=1030,
                codigo_materia=101,
                paralelo="A",
                num_matricula=2,
                num_grupo=3,
                p1_tareas=10,
                p1_proyectos=9,
                p1_examen=9,
                p2_tareas=7,
                p2_proyectos=7,
                p2_examen=10,
                p3_tareas=10,
                p3_proyectos=10,
                p3_examen=10,
                recuperacion=9.23,
            ),
            SessionUser(
                login="docente@intec.edu.ec",
                nombres="Docente prueba",
                rol="DOCENTE",
                codigo_doc=31,
            ),
        )

        update_call = cursor.execute.call_args_list[1]
        update_sql = update_call.args[0]
        update_params = update_call.args[1:]
        self.assertIn("promP1 = ?", update_sql)
        self.assertIn("promP2 = ?", update_sql)
        self.assertIn("promP3 = ?", update_sql)
        self.assertIn("Recuperacion = ?", update_sql)
        self.assertEqual(update_params[3], 9.3)
        self.assertEqual(update_params[7], 8.87)
        self.assertEqual(update_params[11], 10)
        self.assertEqual(update_params[12], 9.39)
        self.assertEqual(update_params[13], 9.23)
        self.assertEqual(update_params[14], 9.39)
        self.assertEqual(result["affected_rows"], 1)
        connection.commit.assert_called_once_with()

    def test_administrative_grade_calculation_matches_teacher_rules(self):
        self.assertEqual(_weighted_grade_partial(10, 8, 7), 8.2)
        self.assertEqual(_weighted_homologation_grade(8, 9), 8.6)
        self.assertEqual(_grade_condition(None), (None, "PENDIENTE"))
        self.assertEqual(_grade_condition(6.99), ("R", "REPROBADO"))
        self.assertEqual(_grade_condition(7), ("A", "APROBADO"))

    @patch("app.routers.legacy_reports.get_connection")
    def test_administrative_update_uses_complete_enrollment_key(self, get_connection: MagicMock):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        cursor.fetchone.return_value = (1,)
        cursor.rowcount = 1
        get_connection.return_value = connection

        result = update_student_grade(
            ReportGradeUpdatePayload(
                codigo_estud=800,
                cod_anio_basica=10,
                codigo_periodo=1030,
                codigo_materia=101,
                paralelo="A",
                num_matricula=2,
                num_grupo=3,
                p1_tareas=10,
                p1_proyectos=8,
                p1_examen=7,
                p2_tareas=8,
                p2_proyectos=8,
                p2_examen=8,
                p3_tareas=9,
                p3_proyectos=9,
                p3_examen=9,
                recuperacion=10,
            ),
            SessionUser(login="academico", nombres="Prueba", rol="ACADEMICO"),
        )

        update_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("codigo_estud", update_sql)
        self.assertIn("cod_anio_Basica", update_sql)
        self.assertIn("codigo_periodo", update_sql)
        self.assertIn("codigo_materia", update_sql)
        self.assertIn("Num_Matricula", update_sql)
        self.assertIn("NumGrupo", update_sql)
        self.assertEqual(result["affected_rows"], 1)
        self.assertEqual(result["promedio_final"], 8.8)
        self.assertEqual(result["condicion"], "APROBADO")
        connection.commit.assert_called_once_with()

    def test_admin_grade_completion_distinguishes_missing_partial_and_complete(self):
        self.assertEqual(_admin_grade_completion({"es_homologacion": False}), "SIN_CALIFICAR")
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": False, "p1_examen": 8}),
            "EN_PROCESO",
        )
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": True, "teoria_homo": 9}),
            "EN_PROCESO",
        )
        self.assertEqual(
            _admin_grade_completion({"es_homologacion": False, "promedio_final": 7}),
            "COMPLETA",
        )

    def test_secretary_report_does_not_expand_student_academic_history(self):
        source = [{
            "codigo_estud": "800",
            "codigo_periodo": "1030",
            "cod_anio_basica": "10",
            "nombre_estudiante": "ESTUDIANTE PRUEBA",
            "cedula": "1106128380",
            "nombre_carrera": "Carrera 10",
            "nombre_materia": "Materia asignada",
            "promedio_final": 9.7,
            "creditos": 4,
        }, {
            "codigo_estud": "801",
            "codigo_periodo": "1030",
            "cod_anio_basica": "10",
            "nombre_estudiante": "SEGUNDO ESTUDIANTE",
            "cedula": "1106128381",
            "nombre_carrera": "Carrera 10",
            "nombre_materia": "Materia asignada",
            "promedio_final": 6.5,
            "creditos": 4,
        }]

        with patch(
            "app.routers.portal_academico._student_grade_report_rows",
            side_effect=AssertionError("El reporte no debe ampliar el historial academico"),
        ):
            pdf = _student_grade_report_pdf(
                {"docente": "DOCENTE PRUEBA", "cedula": "1106128380"},
                {
                    "nombre_materia": "Materia asignada",
                    "detalle_periodo": "Periodo 1030",
                    "paralelo": "A",
                    "cod_jornada": "2",
                    "semestre": 3,
                    "horas": 144,
                },
                source,
            )

        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(pdf))
        report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Reporte de notas", report_text)
        self.assertIn("NOTA", report_text)
        self.assertIn("Promedio", report_text)
        self.assertIn("Firma del docente", report_text)
        self.assertIn("ESTUDIANTE PRUEBA", report_text)
        self.assertIn("SEGUNDO ESTUDIANTE", report_text)
        self.assertNotIn("APROBADO", report_text)
        self.assertNotIn("REPROBADO", report_text)
        self.assertEqual(reader.pages[0].mediabox.width, 612)
        self.assertEqual(reader.pages[0].mediabox.height, 792)

    def test_admin_grade_report_remains_registered(self):
        self.assertIn("notas_carrera_materia", REPORTS)
        self.assertIs(QUERY_BUILDERS["notas_carrera_materia"], _notas_carrera_materia_query)
        self.assertEqual(set(REPORTS), set(QUERY_BUILDERS))


if __name__ == "__main__":
    unittest.main()
