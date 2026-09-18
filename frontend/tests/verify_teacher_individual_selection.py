"""Selected-only enrollment regression checks. All API writes are intercepted.

Run with Vite listening on FRONTEND_TEST_URL (default http://127.0.0.1:5174):
    .venv/Scripts/python.exe frontend/tests/verify_teacher_individual_selection.py
"""

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


PREFIX = "/api/students/matricula-acad"
SUBJECTS = [
    {"cod_materia": f"VGA-CG-2023-{code}", "nombre_materia": name, "semestre": "1",
     "niveles": ["1"], "total_estudiantes": 5,
     "carreras": [{"cod_anio_basica": "7", "nombre_carrera": "Ciberseguridad"}]}
    for code, name in [(71, "Sistemas Operativos"), (72, "Redes")]
]


def students_for(query):
    subject = query["codigo_materia"][0]
    parallel = query["paralelo"][0]
    return [
        {"codigo_estud": str(code), "nombre_estudiante": f"Estudiante {code} P{period}",
         "cedula": f"170000{code:04d}", "correo_intec": f"estudiante{code}@example.test",
         "cod_anio_basica": "7", "nombre_carrera": "Ciberseguridad",
         "codigo_periodo": period, "detalle_periodo": f"Periodo {period}",
         "codigo_materia": subject[-2:], "nombre_materia": subject, "paralelo": parallel,
         "num_matricula": "1", "promedio_final": None}
        for period in query["codigo_periodo"]
        for code in ([70] if parallel == "B" else [10, 20, 30, 40, 50] if period == "1060" else [10, 200])
    ]


def verify_selection(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ["matricula-docente"], "matricula-docente", viewport)
    writes = []
    delayed = []
    state = {"hold_a": False}

    def handler(route):
        request = route.request
        url = urlparse(request.url)
        path = url.path
        query = parse_qs(url.query)
        if request.method == "POST":
            assert path == PREFIX + "/docentes/matricula/materias/multiple", path
            payload = request.post_data_json
            writes.append(payload)
            links = sum(len(period["codigos_estudiantes"]) for subject in payload["materias"] for period in subject["periodos"])
            body = {"ok": True, "students_linked": links, "inserted_count": 1, "existing_count": 0}
        else:
            assert request.method == "GET", path
            if path.endswith("/catalog"):
                body = {"periodos": [{"codigo_periodo": str(period), "detalle_periodo": f"Periodo {period}",
                                       "anio": 2026, "total_matriculados": 5} for period in (1060, 1050)],
                        "jornadas": [{"value": "1", "label": "Matutina"}],
                        "paralelos": [], "niveles_materia": [1]}
            elif path.endswith("/docentes"):
                body = {"items": [{"codigo_doc": "31", "descripcion": "Docente de prueba", "estado": "A",
                                   "cedula": "1700000031", "login": "docente@example.test", "usuario_validado": True}]}
            elif path.endswith("/materias-unicas"):
                body = {"items": SUBJECTS}
            elif path.endswith("/paralelos"):
                body = {"items": [{"paralelo": "A", "total_estudiantes": 5}, {"paralelo": "B", "total_estudiantes": 1}]}
            elif path.endswith("/estudiantes-paralelo"):
                body = {"items": students_for(query)}
                if state["hold_a"] and query["paralelo"] == ["A"]:
                    delayed.append((route, body))
                    return
            else:
                body = {"items": [], "total": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/matricula-acad/**", handler)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Matr\u00edcula docente", exact=True).wait_for()
    page.get_by_role("button", name="Matr\u00edcula individual", exact=False).click()
    page.get_by_role("button", name="Seleccionar docente", exact=True).click()
    selector = page.get_by_role("dialog", name="Seleccionar docente", exact=True)
    selector.get_by_role("checkbox").check()
    selector.get_by_role("button", name="Seleccionar docente", exact=True).click()
    for period in (1060, 1050):
        page.get_by_label("Per\u00edodos (m\u00e1ximo 3)", exact=False).select_option(str(period))
        page.get_by_role("button", name="Agregar per\u00edodo", exact=True).click()
        page.get_by_role("button", name="Sistemas Operativos", exact=False).wait_for()
    for subject in SUBJECTS:
        page.get_by_role("button", name=subject["nombre_materia"], exact=False).click()
    student_panel = page.locator("article").filter(has=page.get_by_role("heading", name="Seleccionar estudiantes para el docente", exact=True))
    expect(student_panel.get_by_role("checkbox", name="Seleccionar Estudiante", exact=False)).to_have_count(7)
    assign = student_panel.get_by_role("button", name="Asignar seleccionados", exact=True)
    expect(assign).to_be_disabled()
    for code in (10, 20, 30):
        student_panel.get_by_role("checkbox", name=f"Seleccionar Estudiante {code} P1060", exact=True).check()
    student_panel.get_by_role("checkbox", name="Solo seleccionados", exact=True).check()
    expect(student_panel.locator("tbody tr")).to_have_count(3)
    expect(student_panel.get_by_role("button", name="Limpiar selecci\u00f3n", exact=True)).to_be_visible()
    assert "Estudiante 40" not in student_panel.locator("tbody").inner_text()
    assign.evaluate("button => { button.click(); button.click(); }")
    dialog = page.get_by_role("dialog", name="Asignar estudiantes", exact=True)
    expect(dialog.locator("li")).to_have_count(3)
    assert "Estudiante 40" not in dialog.inner_text() and "P1050" not in dialog.locator("ul").inner_text()
    box = dialog.locator(".matricula-confirm-modal").bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 1
    page.screenshot(path=str(ROOT / ".runlogs" / f"teacher-selection-{name}-confirm.png"))
    dialog.get_by_role("button", name="Aceptar", exact=True).click()
    expect(assign).to_be_enabled()
    assert len(writes) == 1
    validate_individual(writes[-1], [10, 20, 30])
    expect(student_panel.locator("tbody tr")).to_have_count(3)
    student_panel.scroll_into_view_if_needed()
    page.screenshot(path=str(ROOT / ".runlogs" / f"teacher-selection-{name}-selected.png"))

    # A subsequent one-student request cannot inherit the two deselected students.
    for code in (20, 30):
        student_panel.get_by_role("checkbox", name=f"Seleccionar Estudiante {code} P1060", exact=True).click()
    assign.click()
    dialog = page.get_by_role("dialog", name="Asignar estudiantes", exact=True)
    expect(dialog.locator("li")).to_have_count(1)
    dialog.get_by_role("button", name="Aceptar", exact=True).click()
    expect(assign).to_be_enabled()
    assert len(writes) == 2
    validate_individual(writes[-1], [10])
    student_panel.get_by_role("checkbox", name="Seleccionar Estudiante 10 P1060", exact=True).click()
    expect(assign).to_be_disabled()
    assert len(writes) == 2

    # Candidate search and selecting all remain distinct from course-wide mode.
    student_panel.get_by_role("checkbox", name="Solo seleccionados", exact=True).uncheck()
    student_panel.get_by_role("button", name="Seleccionar visibles", exact=True).click()
    student_panel.get_by_role("checkbox", name="Solo seleccionados", exact=True).check()
    expect(student_panel.locator("tbody tr")).to_have_count(7)
    student_panel.get_by_role("button", name="Limpiar selecci\u00f3n", exact=True).click()
    expect(assign).to_be_disabled()

    # A context change while the confirmation is open invalidates its snapshot.
    student_panel.get_by_role("checkbox", name="Solo seleccionados", exact=True).uncheck()
    student_panel.get_by_role("checkbox", name="Seleccionar Estudiante 10 P1060", exact=True).check()
    assign.click()
    page.get_by_label("Paralelo", exact=False).select_option("B", force=True)
    dialog.get_by_role("button", name="Aceptar", exact=True).click()
    expect(page.get_by_text("Los datos o la selecci\u00f3n cambiaron durante la confirmaci\u00f3n.", exact=False)).to_be_visible()
    assert len(writes) == 2

    # An older response cannot replace the new parallel's candidate list.
    page.get_by_label("Paralelo", exact=False).select_option("A")
    expect(student_panel.get_by_role("checkbox", name="Seleccionar Estudiante", exact=False)).to_have_count(7)
    state["hold_a"] = True
    student_panel.get_by_role("button", name="Actualizar estudiantes", exact=True).click()
    page.wait_for_timeout(150)
    assert delayed
    page.get_by_label("Paralelo", exact=False).select_option("B")
    expect(student_panel.get_by_role("checkbox", name="Seleccionar Estudiante", exact=False)).to_have_count(2)
    for route, body in delayed:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.wait_for_timeout(150)
    expect(student_panel.get_by_role("checkbox", name="Seleccionar Estudiante", exact=False)).to_have_count(2)
    assert "Estudiante 10" not in student_panel.locator("tbody").inner_text()
    expect(assign).to_be_disabled()
    assert len(writes) == 2
    page.get_by_role("button", name="Matr\u00edcula masiva", exact=False).click()
    page.get_by_role("button", name="Matricular curso completo", exact=True).click()
    mass_dialog = page.get_by_role("dialog", name="Matr\u00edcula docente masiva", exact=True)
    mass_dialog.get_by_role("button", name="Aceptar", exact=True).click()
    expect(page.get_by_role("button", name="Matricular curso completo", exact=True)).to_be_enabled()
    assert len(writes) == 3 and writes[-1]["modo_asignacion"] == "MASIVA"
    assert all(not period["codigos_estudiantes"] for subject in writes[-1]["materias"] for period in subject["periodos"])
    assert not errors, errors
    print(f"{name}: exact selection of 3/1, selected-only table, multi-subject/period scope, empty selection, double click, stale requests and explicit mass mode passed")
    context.close()


def validate_individual(payload, expected):
    assert payload["modo_asignacion"] == "INDIVIDUAL"
    assert payload["codigo_doc"] == 31
    assert len(payload["materias"]) == 2
    for subject in payload["materias"]:
        assert len(subject["periodos"]) == 1
        period = subject["periodos"][0]
        assert period["codigo_periodo"] == 1060 and period["paralelo"] == "A"
        assert sorted(period["codigos_estudiantes"]) == expected


if __name__ == "__main__":
    (ROOT / ".runlogs").mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1600, "height": 1000}),
                               ("mobile", {"width": 390, "height": 844}),
                               ("mobile-small", {"width": 320, "height": 740})]:
            verify_selection(browser, name, viewport)
        browser.close()
