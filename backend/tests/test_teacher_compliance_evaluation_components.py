from copy import deepcopy

from app.routers.portal_academico import _teacher_compliance_grade_validation
from app.services.moodle_grade_sync import MoodleGradeSyncService


def activity(module, grade, item_id=1, **extra):
    return {
        "id": item_id, "itemtype": "mod", "itemmodule": module,
        "itemname": f"Evaluación {module}", "graderaw": grade,
        "grademin": 0, "grademax": 10,
        "evaluation_scope": True, "course_section_visible": True,
        "course_module_visible": True, **extra,
    }


def student(code=1, theory=8.5, practice=10, final=9.4, **extra):
    return {
        "codigo_estud": code, "correo_intec_registro": f"s{code}@intec.edu.ec",
        "nombre_estudiante": f"Estudiante {code}", "codigo_periodo": 1055,
        "detalle_periodo": "C1-HOMO-2026-PB", "tipo_matricula": "H",
        "teoria_homo": theory, "practica_homo": practice,
        "promedio_final": final, **extra,
    }


def validate(records, groups):
    selected = {r["codigo_estud"]: r for r in records}
    return _teacher_compliance_grade_validation(
        records, list(selected.values()), {"id": 1490},
        moodle_users=[{"id": code, "email": r["correo_intec_registro"]} for code, r in selected.items()],
        moodle_user_grades=[{"userid": code, "gradeitems": items} for code, items in groups.items()],
    )


def test_report_ignores_course_totals_and_reproduces_reported_case():
    records = [student(), student(2, 8, 7, 7.4), student(3, None, 8, None)]
    groups = {
        1: [activity("quiz", 8.5), activity("assign", 10, 2), {"itemtype": "course", "graderaw": 9.17}],
        2: [activity("quiz", 8), activity("assign", 7, 2), {"itemtype": "course", "graderaw": 5}],
        3: [activity("quiz", None), activity("assign", 8, 2)],
    }
    result = validate(records, groups)
    assert result["moodle"]["discrepancies"] == []
    assert result["moodle"]["verified_students"] == 2
    assert result["missing_academic_count"] == 1
    assert result["moodle"]["missing_grade_students"][0]["codigo_estud"] == 3
    assert result["can_generate"]
    assert result["blockers"]  # Findings are retained but no longer gate the report.
    assert validate(records[:2], groups)["can_generate"]


def test_component_difference_is_not_hidden_by_matching_final():
    result = validate([student(theory=10, practice=9)], {1: [activity("quiz", 8.5), activity("assign", 10, 2)]})
    difference = result["moodle"]["discrepancies"][0]
    assert len(difference["componentes"]) == 2
    assert difference["componentes"][0]["nota_intec"] == 10
    assert difference["componentes"][0]["nota_moodle"] == 8.5
    assert result["can_generate"]


def test_missing_local_component_is_not_zero_or_verified():
    result = validate([student(theory=None)], {1: [activity("quiz", 0), activity("assign", 10, 2)]})
    assert result["moodle"]["discrepancies"][0]["componentes"][0]["nota_intec"] is None
    assert result["moodle"]["verified_students"] == 0


def test_zero_is_valid_and_course_total_is_not_required():
    result = validate([student(theory=0, practice=0, final=0)], {1: [activity("quiz", 0), activity("assign", 0, 2)]})
    assert result["can_generate"]
    assert result["moodle"]["verified_students"] == 1


def test_course_total_cannot_fill_missing_evaluation():
    result = validate([student()], {1: [{"itemtype": "course", "graderaw": 9.4, "grademax": 10}]})
    assert result["can_generate"]
    assert result["moodle"]["missing_grade_students"]
    assert result["moodle"]["verified_students"] == 0


def test_same_scale_and_best_attempt_as_migration_ignores_hidden_and_other_sections():
    items = [activity("quiz", 60, grademax=100), activity("quiz", 85, 3, grademax=100),
             activity("assign", 100, 2, grademax=100),
             activity("quiz", 10, 4, evaluation_scope=False),
             activity("quiz", 10, 5, course_module_visible=False)]
    before = deepcopy(items)
    selected, errors, conflicts = MoodleGradeSyncService.evaluation_components(items, "H")
    assert not errors and not conflicts
    assert selected["teoriaHomo"]["item_id"] == 3
    assert validate([student()], {1: items})["can_generate"]
    assert items == before


def test_every_enrollment_is_checked_instead_of_matching_any_period():
    result = validate([student(), student(theory=7, codigo_periodo=1056, detalle_periodo="HOMO 1056")],
                      {1: [activity("quiz", 8.5), activity("assign", 10, 2)]})
    assert result["can_generate"]
    assert result["moodle"]["discrepancies"][0]["detalle_periodo"] == "HOMO 1056"
    assert result["moodle"]["verified_students"] == 0


def test_regular_partials_and_recovery_do_not_compare_course_total():
    record = student(tipo_matricula="R", detalle_periodo="Regular", recuperacion=10, final=8.27)
    items = []
    for partial in (1, 2, 3):
        items.extend([activity("quiz", 8, partial * 10, course_section_partial=partial),
                      activity("assign", 8, partial * 10 + 1, course_section_partial=partial)])
        record.update({f"p{partial}_{c}": 8 for c in ("tareas", "proyectos", "examen")})
    assert validate([record], {1: items})["can_generate"]
    record["p2_examen"] = 7
    result = validate([record], {1: items})
    assert result["moodle"]["discrepancies"][0]["componentes"][0]["campo"] == "P2Examen"


def test_invalid_scale_blocks_instead_of_using_course_total():
    items = [activity("quiz", 500), activity("assign", 10, 2), {"itemtype": "course", "graderaw": 9.4}]
    result = validate([student()], {1: items})
    assert result["can_generate"]
    assert result["moodle"]["verified_students"] == 0


def test_explicit_homologation_type_does_not_require_homo_in_period_name():
    assert validate([student(detalle_periodo="C1-2026")],
                    {1: [activity("quiz", 8.5), activity("assign", 10, 2)]})["can_generate"]
