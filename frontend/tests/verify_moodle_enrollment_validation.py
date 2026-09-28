"""Read-only enrollment audit UI checks. All API traffic uses synthetic fixtures."""
import json
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


CATALOG = {
    "periods": [{"code": 10, "name": "PERIODO R30", "enrollment_type": "R"},
                {"code": 11, "name": "PERIODO H1", "enrollment_type": "H"}],
    "parallels": ["PB1", "PB2"], "max_courses": 100,
    "careers": [{"code": 1, "name": "Ciberseguridad", "period_codes": [10]},
                {"code": 2, "name": "Big Data", "period_codes": [11]}],
    "courses": [{"id": 20, "fullname": "INTELIGENCIA ARTIFICIAL R30 - PB1", "shortname": "VGA-ES-2023-95-R30",
                 "category": "Big Data", "parallel": "PB1"},
                {"id": 21, "fullname": "SISTEMAS OPERATIVOS R30", "shortname": "VGA-CG-2023-71-R30",
                 "category": "TICS", "parallel": ""}],
}
ROW = {
    "status": "CAMBIO_CARRERA", "status_label": "Revisar cambio de carrera", "student_code": "1",
    "student": "ESTUDIANTE DE PRUEBA", "document": "0010000001", "email": "prueba@example.test",
    "moodle_email": "prueba@example.test", "moodle_user_id": "100", "course_id": "20",
    "course": CATALOG["courses"][0]["fullname"], "moodle_code": "VGA-ES-2023-95-R30",
    "subject_code": "VGA-ES-2023-95", "subject": "Inteligencia Artificial", "academic_career": "",
    "moodle_idnumber": "VGA-ES-2023-95-R30", "code_match": "Similitud controlada",
    "code_match_detail": "Prefijo parecido con el mismo ano y numero de materia.", "code_candidates": "VGA-ES-2023-95",
    "period": "PERIODO R30", "period_code": "10", "academic_parallel": "", "moodle_parallel": "*",
    "period_careers": "Ciberseguridad", "previous_careers": "Big Data",
    "career_changes": "Big Data a Ciberseguridad (2026-09-21)",
    "reason": "No existe la materia en el periodo seleccionado. Hay un cambio de carrera aplicado.",
}
REPORT = {
    "report_id": "snapshot-test", "generated_at": "2026-09-21T18:00:00Z", "actor": "admin@example.test",
    "period": {"code": 10, "name": "PERIODO R30"}, "warnings": [],
    "scope": [{"id": c["id"], "name": c["fullname"], "parallel": "*", "subject_code": "VGA-ES-2023-95", "error": ""} for c in CATALOG["courses"]],
    "summary": {"rows": 2, "matches": 1, "inactive": 0, "findings": 1, "career_history": 1},
    "rows": [ROW, {**ROW, "student": "OTRO ESTUDIANTE", "student_code": "2", "status": "COINCIDE",
                   "status_label": "Coincide", "previous_careers": "", "career_changes": "", "reason": "Matricula coincidente"}],
}
ACADEMIC_ROW = {**ROW, "academic_career": "Ciberseguridad", "status": "COINCIDE",
                "status_label": "Materia matriculada en el periodo", "subject_careers": "Ciberseguridad, Big Data",
                "enrollment_periods": "PERIODO R30 (10) - Ciberseguridad", "period_relation": "Periodo Moodle no confirmado",
                "reason": "Materia matriculada en la carrera y periodo seleccionados."}
ACADEMIC_REPORT = {**REPORT, "report_id": "academic-snapshot", "mode": "academic", "course_selection": True, "career": {"code": 1, "name": "Ciberseguridad"},
                   "summary": {"rows": 1, "matches": 1, "inactive": 0, "findings": 0, "career_history": 1},
                   "rows": [ACADEMIC_ROW], "students": [{
                       "student_code": "1", "student": ROW["student"], "document": ROW["document"], "email": ROW["email"],
                       "academic_career": "Ciberseguridad", "career_code": "1", "period": "PERIODO R30", "period_code": "10",
                       "findings": 0, "evaluated_subjects": 1, "query_error": "", "rows": [ACADEMIC_ROW], "moodle_courses": [ACADEMIC_ROW],
                       "academic_subjects": [{"subject_id": 101, "subject_code": "VGA-ES-2023-95", "subject": "Inteligencia Artificial",
                                              "semester": 2, "parallel": "PB1", "linked": True}],
                   }]}


def verify(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ["dashboard", "moodle/enrollment-validation"], "dashboard", viewport)
    calls = []
    fail = [False]
    selected_courses = [[]]

    def handler(route):
        path = urlparse(route.request.url).path
        calls.append((route.request.method, path, route.request.post_data_json if route.request.method == "POST" else None))
        if path.endswith("/catalog"):
            body = CATALOG
        elif path.endswith("/academic"):
            payload = route.request.post_data_json
            assert payload["period_code"] == 10 and payload["career_code"] == 1 and payload["courses"]
            selected_courses[0] = payload["courses"]
            if fail[0]:
                route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": "Curso no disponible"}))
                return
            body = {"job_id": "career-job", "status": "running", "unit": "courses", "processed": 0, "total": len(payload["courses"]), "error": "", "report": None}
        elif path.endswith("/academic/career-job"):
            report = {**ACADEMIC_REPORT, "scope": [item for item in REPORT["scope"] if item["id"] in {c["id"] for c in selected_courses[0]}]}
            if len(selected_courses[0]) > 1:
                report["rows"] = REPORT["rows"]
                report["summary"] = REPORT["summary"]
            body = {"job_id": "career-job", "status": "completed", "unit": "courses", "processed": len(selected_courses[0]), "total": len(selected_courses[0]), "error": "", "report": report}
        else:
            assert path in ("/api/moodle/enrollment-validation/reports/snapshot-test/pdf",
                            "/api/moodle/enrollment-validation/reports/snapshot-test/xlsx",
                            "/api/moodle/enrollment-validation/reports/academic-snapshot/pdf",
                            "/api/moodle/enrollment-validation/reports/academic-snapshot/xlsx")
            route.fulfill(body=b"synthetic-download", content_type="application/octet-stream")
            return
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/moodle/enrollment-validation/**", handler)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Dashboard Estudiantil", exact=True).wait_for()
    if viewport["width"] < 700:
        page.get_by_role("button", name="Abrir men\u00fa principal", exact=True).click()
    else:
        page.get_by_role("complementary", name="Men\u00fa lateral", exact=True).hover()
    group = page.locator(".student-nav__group-button").filter(has_text="Integraciones")
    if group.get_attribute("aria-expanded") != "true":
        group.click()
    page.locator('.student-nav__item').filter(has_text="Validaci\u00f3n de matr\u00edculas Moodle").click()
    section = page.get_by_role("region", name="Validaci\u00f3n de matr\u00edculas", exact=True)
    expect(section.get_by_role("heading", name="Validaci\u00f3n de matr\u00edculas", exact=True)).to_be_visible()
    period = section.get_by_role("combobox", name="Per\u00edodo acad\u00e9mico", exact=True)
    run = section.get_by_role("button", name="Validar matr\u00edculas", exact=True)
    career = section.get_by_role("combobox", name="Carrera matriculada", exact=True)
    expect(career).to_be_disabled()
    period.select_option("10")
    expect(run).to_be_disabled()
    expect(career.locator("option")).to_have_count(2)
    career.select_option("1")
    expect(run).to_be_disabled()
    expect(section.get_by_role("tablist", name="Origen de validaci\u00f3n")).to_have_count(0)
    section.get_by_role("searchbox", name="Buscar curso", exact=True).click()
    first_course = section.get_by_role("checkbox", name=f"Seleccionar {CATALOG['courses'][0]['fullname']}", exact=True)
    first_course.check()
    expect(section.get_by_role("combobox", name=f"Paralelo de {CATALOG['courses'][0]['fullname']}")).to_have_value("*")
    run.click()
    expect(section.get_by_role("progressbar", name="Avance de validaci\u00f3n")).to_be_visible()
    expect(career).to_be_disabled()
    expect(first_course).to_be_disabled()
    result = section.get_by_role("region", name="Resultado de validaci\u00f3n", exact=True)
    expect(result).to_be_visible()
    expect(result.get_by_role("table", name="Matr\u00edculas por estudiante").locator("tbody tr")).to_have_count(1)
    result.get_by_role("button", name=f"Ver matr\u00edcula y aulas de {ROW['student']}", exact=True).click()
    student_dialog = page.get_by_role("dialog", name=ROW["student"], exact=True)
    expect(student_dialog).to_be_visible()
    expect(student_dialog.get_by_text("Ciberseguridad \u00b7 1", exact=True)).to_be_visible()
    expect(student_dialog.get_by_role("table", name="Materias acad\u00e9micas del estudiante").locator("tbody tr")).to_have_count(1)
    expect(student_dialog.get_by_role("table", name="Cursos Moodle del estudiante").locator("tbody tr")).to_have_count(1)
    expect(student_dialog.get_by_role("cell").filter(has_text=ACADEMIC_ROW["enrollment_periods"])).to_be_visible()
    assert student_dialog.evaluate("element => element.scrollWidth <= element.clientWidth"), "Student dialog overflow"
    page.screenshot(path=str(ROOT / ".runlogs" / f"enrollment-academic-detail-{name}.png"))
    page.keyboard.press("Escape")
    for label in ("Excel completo", "PDF completo"):
        with page.expect_download():
            result.get_by_role("button", name=label, exact=True).click()
    result.get_by_role("tab", name="Detalle por materia", exact=True).click()
    expect(result.get_by_role("table").locator("tbody tr")).to_have_count(1)
    result.get_by_role("tab", name="Estudiantes", exact=True).click()
    page.screenshot(path=str(ROOT / ".runlogs" / f"enrollment-academic-{name}.png"), full_page=True)
    period.select_option("11")
    expect(result).not_to_be_visible()
    expect(career).to_have_value("")
    expect(career.locator("option")).to_have_count(2)
    expect(run).to_be_disabled()
    expect(first_course).not_to_be_checked()
    period.select_option("10")
    career.select_option("1")
    parallels = [section.get_by_role("combobox", name=f"Paralelo de {course['fullname']}", exact=True)
                 for course in CATALOG["courses"]]
    for parallel in parallels:
        expect(parallel).to_have_value("*")
    section.get_by_role("searchbox", name="Buscar curso", exact=True).click()
    first_course = section.get_by_role("checkbox", name=f"Seleccionar {CATALOG['courses'][0]['fullname']}", exact=True)
    first_course.check()
    expect(parallels[0]).to_have_value("*")
    expect(run).to_be_enabled()
    parallels[0].select_option("PB1")
    search = section.get_by_role("searchbox", name="Buscar curso", exact=True)
    search.fill("SISTEMAS")
    section.get_by_role("button", name="Seleccionar visibles", exact=True).click()
    search.fill("")
    expect(parallels[0]).to_have_value("PB1")
    expect(parallels[1]).to_have_value("*")
    section.get_by_role("button", name="Limpiar selecci\u00f3n", exact=True).click()
    section.get_by_role("button", name="Seleccionar visibles", exact=True).click()
    for parallel in parallels:
        expect(parallel).to_have_value("*")
    expect(period).to_have_value("10")
    expect(run).to_be_enabled()
    run.click()
    result = section.get_by_role("region", name="Resultado de validaci\u00f3n", exact=True)
    expect(result).to_be_visible()
    assert [data for method, path, data in calls if method == "POST" and path.endswith("/academic")][-1] == {
        "period_code": 10, "career_code": 1, "courses": [{"id": 20, "parallel": "*"}, {"id": 21, "parallel": "*"}],
    }
    result.get_by_role("tab", name="Detalle por materia", exact=True).click()
    expect(result.locator("tbody tr")).to_have_count(2)
    result.get_by_role("combobox", name="Resultado", exact=True).select_option("findings")
    expect(result.locator("tbody tr")).to_have_count(1)
    result.get_by_role("button", name="Ver detalle de ESTUDIANTE DE PRUEBA", exact=True).click()
    dialog = page.get_by_role("dialog", name="ESTUDIANTE DE PRUEBA", exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_text("Big Data a Ciberseguridad (2026-09-21)", exact=True)).to_be_visible()
    expect(dialog.get_by_text("Similitud controlada", exact=True)).to_be_visible()
    expect(dialog.get_by_text(ROW["code_match_detail"], exact=True)).to_be_visible()
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"]
    assert box["y"] >= 0 and box["y"] + box["height"] <= viewport["height"]
    page.screenshot(path=str(ROOT / ".runlogs" / f"enrollment-validation-detail-{name}.png"))
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    for label, extension in [("Excel completo", "xlsx"), ("PDF completo", "pdf")]:
        with page.expect_download() as download:
            result.get_by_role("button", name=label, exact=True).click()
        assert download.value.suggested_filename.endswith("." + extension)
    assert len([c for c in calls if c[0] == "POST" and c[1].endswith("/academic")]) == 2, "Export must use the existing snapshot"
    assert not any(c[1].endswith("/preview") for c in calls), "Only one unified validation flow is allowed"
    page.screenshot(path=str(ROOT / ".runlogs" / f"enrollment-validation-{name}.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Page overflow"
    parallels[0].select_option("PB1")
    expect(result).not_to_be_visible()
    fail[0] = True
    run.click()
    expect(section.get_by_role("alert")).to_have_text("Curso no disponible")
    expect(result).not_to_be_visible()
    expect(section.get_by_role("checkbox", name="Seleccionar INTELIGENCIA ARTIFICIAL R30 - PB1", exact=True)).to_be_checked()
    fail[0] = False
    run.click()
    expect(result).to_be_visible()
    section.get_by_role("button", name="Limpiar selecci\u00f3n", exact=True).click()
    expect(result).not_to_be_visible()
    expect(run).to_be_disabled()
    assert not errors, errors
    context.close()
    print(f"{name}: unified career/period/course selection, exact payload, default parallels, context reset, filtering, progress, detail, exports and retry passed")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1500, "height": 940}), ("mobile", {"width": 390, "height": 844})]:
            verify(browser, name, viewport)
        browser.close()
