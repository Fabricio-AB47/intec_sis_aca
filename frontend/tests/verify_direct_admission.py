"""Direct admission UI checks. SQL, Moodle and Graph writes are all mocked."""

import json
import re
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


PREFIX = "/api/students/ingreso-directo"
SUBJECTS = [
    {"codigo_materia": str(code), "nombre_materia": name, "semestre": level,
     "cod_materia": f"VGA-CG-2026-{code}", "creditos": 4}
    for code, name, level in [(11, "Matem\u00e1tica aplicada", 1), (12, "Pensamiento cr\u00edtico", 1),
                              (21, "Sistemas operativos", 2)]
]
CATALOGS = {
    "Sexo": [{"value": "1", "label": "Hombre"}, {"value": "2", "label": "Mujer"}],
    "EstadoCivil": [{"value": "1", "label": "Soltero"}],
    "Etnia": [{"value": "1", "label": "Mestizo"}],
    "tipodocumento": [{"value": "1", "label": "C\u00e9dula"}, {"value": "2", "label": "Pasaporte"}],
    "paisNacionalidadId": [{"value": "1", "label": "Ecuador"}, {"value": "2", "label": "Otro pa\u00eds"}],
    "paisResidenciaId": [{"value": "1", "label": "Ecuador"}, {"value": "2", "label": "Otro pa\u00eds"}],
    "codprov": [{"value": "17", "label": "Pichincha", "parent_value": "1"},
                {"value": "99", "label": "Provincia extranjera", "parent_value": "2"}],
    "provinciaNacimeintoId": [{"value": "17", "label": "Pichincha", "parent_value": "1"}],
    "Canton": [{"value": "1701", "label": "Quito", "parent_value": "17"}],
    "cantonNacimeintoId": [{"value": "1701", "label": "Quito", "parent_value": "17"}],
}


def verify(browser, name, viewport):
    context, page, _, scripts, errors = mock_context(browser, ["matricula-acad/ingreso-directo"], "matricula-acad", viewport)
    state = {"save_failure": True, "document_failure": True, "uploaded": False, "record": None}
    saves = []
    previews = []
    uploads = []
    prepares = []
    held = []
    state["hold_career"] = False

    def handler(route):
        path = urlparse(route.request.url).path
        query = parse_qs(urlparse(route.request.url).query)
        status = 200
        if path == PREFIX + "/catalog":
            body = {"datos_catalogos": CATALOGS,
                    "carreras": [{"cod_anio_basica": "7", "nombre_basica": "Ciberseguridad"},
                                 {"cod_anio_basica": "8", "nombre_basica": "Otra carrera"}],
                    "periodos": [{"codigo_periodo": "1060", "detalle_periodo": "C1-2026-PB", "tipo_matricula": "R"}],
                    "jornadas": [{"value": "1", "label": "Matutina"}]}
        elif path == PREFIX + "/pensum":
            body = {"items": SUBJECTS if query["cod_anio_basica"] == ["7"] else []}
            if state["hold_career"] and query["cod_anio_basica"] == ["7"]:
                held.append((route, body))
                return
        elif path == PREFIX + "/preview":
            payload = route.request.post_data_json
            previews.append(payload)
            blocked = payload["matricula"]["nivel"] == 2 and not payload["matricula"]["prerequisite_exception_codes"]
            body = {"summary": {"insertar": len(payload["matricula"]["materia_codes"]), "bloqueadas_por_prerrequisito": int(blocked)},
                    "items": [{**subject, "accion": "BLOQUEADA_PRERREQUISITO" if blocked else "INSERTAR"}
                              for subject in SUBJECTS if int(subject["codigo_materia"]) in payload["matricula"]["materia_codes"]]}
        elif path == PREFIX + "/save":
            payload = route.request.post_data_json
            saves.append(payload)
            assert payload["matricula"]["materia_codes"] == [21]
            assert "codigo_estud" not in payload["matricula"] and "remove_unselected" not in payload["matricula"]
            if state["save_failure"]:
                state["save_failure"] = False
                status = 500
                body = {"detail": "Error simulado de respuesta; reintente la misma solicitud."}
            else:
                body = {"solicitud_id": payload["solicitud_id"], "codigo_estud": "99", "identificacion": "1724036536",
                        "nombre_estudiante": "PEREZ LOPEZ ANA MARIA", "nivel": 2, "ok": True,
                        "message": "Estudiante registrado y matriculado correctamente.", "documentos_pendientes": True,
                        "matricula": {"inserted": 1, "num_matricula": "1"}}
                state["record"] = {**body, "carrera": "Ciberseguridad", "periodo": "C1-2026-PB",
                                   "registrado_por": "admin@example.test", "fecha_registro": "2026-09-18T12:00:00"}
        elif path == PREFIX + "/history":
            body = {"items": [state["record"]] if state["record"] else []}
        elif path.startswith(PREFIX) and path.endswith("/credenciales"):
            assert route.request.method == "GET"
            body = {"estado_general": "PENDIENTE", "datos_credenciales": {"nombres": "ANA MARIA", "apellidos": "PEREZ LOPEZ"}}
        elif path == "/api/document-expedients/context":
            assert query["identification"] == ["1724036536"]
            if state["document_failure"]:
                status = 502
                body = {"detail": "Graph no disponible; la matr\u00edcula permanece guardada."}
            else:
                documents = [{"document_graph_id": 101, "document_type_code": "CEDULA", "name": "cedula.pdf",
                              "version": 1, "status": "CARGADO", "size": 25, "uploaded_at": "2026-09-18T12:00:00Z",
                              "uploaded_by": "admin@example.test"}] if state["uploaded"] else []
                body = {"student": {"code": 99, "identification": "1724036536", "name": "PEREZ LOPEZ ANA MARIA",
                                    "email": "ana@example.test", "career": "Ciberseguridad", "period_name": "C1-2026-PB", "enrollment_type": "R"},
                        "total_documents": len(documents), "total_expedients": 1, "max_file_bytes": 1024 * 1024,
                        "expedients": [{"module_code": "SECRETARIA", "module_name": "Secretar\u00eda General",
                                        "origin_id": "EST-99", "expedient_code": "ARCHIVO-SECRETARIA-99", "status": "DISPONIBLE",
                                        "upload_enabled": True, "document_types": [{"code": "CEDULA", "name": "C\u00e9dula"}],
                                        "documents": documents}]}
        elif path == "/api/document-expedients/prepare":
            body = route.request.post_data_json
            prepares.append(body)
            assert body == {"identification": "1724036536", "module_code": "SECRETARIA", "origin_id": "EST-99"}
            body = {"ok": True, "message": "Expediente preparado correctamente."}
        elif path == "/api/document-expedients/upload-session":
            payload = route.request.post_data_json
            uploads.append(payload)
            assert payload["identification"] == "1724036536" and payload["origin_id"] == "EST-99"
            assert payload["module_code"] == "SECRETARIA" and payload["document_type_code"] == "CEDULA"
            body = {"upload_id": str(uuid4()), "upload_url": BASE_URL + "/mock-direct-upload", "chunk_size": 1024 * 1024}
        elif path == "/api/document-expedients/finalize":
            state["uploaded"] = True
            body = {"ok": True, "message": "Documento relacionado correctamente.", "version": 1, "document_graph_id": 101}
        else:
            raise AssertionError("Unexpected API request: " + path)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/ingreso-directo/**", handler)
    context.route("**/api/document-expedients/**", handler)
    context.route("**/mock-direct-upload", lambda route: route.fulfill(status=201, content_type="application/json", body='{"id":"mock-file"}'))
    page.goto(BASE_URL)
    page.get_by_role("heading", name="ingreso_intec", exact=True).wait_for()
    expect(page.get_by_role("button", name="Validar matr\u00edcula", exact=True)).to_be_disabled()
    form = page.locator(".direct-admission form")
    page.get_by_label("Identificaci\u00f3n", exact=False).fill("1724036536")
    page.get_by_label("Nombres", exact=False).fill("Ana Maria")
    page.get_by_label("Apellidos", exact=False).fill("Perez Lopez")
    page.get_by_label("Correo personal", exact=False).fill("ana@example.test")
    for label, value in [("Sexo", "2"), ("Estado civil", "1"), ("Etnia", "1"),
                         ("Carrera", "7"), ("Per\u00edodo", "1060")]:
        form.get_by_label(label, exact=False).select_option(value)
    expect(form.get_by_label("Nivel", exact=False)).to_have_value("1")
    expect(form.get_by_role("checkbox", name=re.compile(r"^Matricular "))).to_have_count(2)
    expect(form.get_by_role("combobox", name="Provincia de residencia", exact=True)).to_be_disabled()
    form.get_by_role("combobox", name="Pa\u00eds de residencia", exact=True).select_option("1")
    form.get_by_role("combobox", name="Provincia de residencia", exact=True).select_option("17")
    form.get_by_role("combobox", name="Cant\u00f3n de residencia", exact=True).select_option("1701")
    form.get_by_role("combobox", name="Pa\u00eds de residencia", exact=True).select_option("2")
    expect(form.get_by_role("combobox", name="Provincia de residencia", exact=True)).to_have_value("")
    expect(form.get_by_role("combobox", name="Cant\u00f3n de residencia", exact=True)).to_have_value("")
    form.get_by_role("combobox", name="Pa\u00eds de residencia", exact=True).select_option("")

    # Changing level must discard the previous level's selected subjects.
    form.get_by_role("button", name="Seleccionar nivel", exact=True).click()
    form.get_by_label("Nivel", exact=False).select_option("2")
    expect(form.get_by_role("button", name="Validar matr\u00edcula", exact=True)).to_be_disabled()
    form.get_by_role("checkbox", name="Matricular Sistemas operativos", exact=True).check()
    form.get_by_role("button", name="Validar matr\u00edcula", exact=True).click()
    dialog = page.get_by_role("dialog", name="Confirmar ingreso y matr\u00edcula", exact=True)
    expect(dialog.get_by_role("button", name="Registrar y matricular", exact=True)).to_be_disabled()
    assert not saves
    dialog.get_by_role("button", name="Volver", exact=True).click()
    form.get_by_role("checkbox", name="Autorizar excepci\u00f3n de prerrequisitos", exact=True).check()
    form.get_by_label("Justificaci\u00f3n", exact=False).fill("Admisión por homologación documentada")
    page.screenshot(path=str(ROOT / ".runlogs" / f"direct-admission-{name}-form.png"), full_page=True)
    form.get_by_role("button", name="Validar matr\u00edcula", exact=True).click()
    expect(dialog.get_by_role("button", name="Registrar y matricular", exact=True)).to_be_enabled()
    assert dialog.evaluate("element => element.open && element.matches(':modal')")
    expect(dialog.locator("li")).to_have_count(1)
    assert "Sistemas operativos" in dialog.inner_text() and "Pensamiento" not in dialog.inner_text()
    box = dialog.locator(".direct-admission-modal").bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 1
    page.screenshot(path=str(ROOT / ".runlogs" / f"direct-admission-{name}-confirm.png"))
    dialog.get_by_role("button", name="Registrar y matricular", exact=True).evaluate("button => { button.click(); button.click(); }")
    dialog.get_by_role("alert").filter(has_text="Error simulado").wait_for()
    assert len(saves) == 1
    dialog.get_by_role("button", name="Registrar y matricular", exact=True).click()
    page.get_by_role("heading", name="Documentaci\u00f3n del estudiante", exact=True).wait_for()
    assert len(saves) == 2 and saves[0] == saves[1]
    page.get_by_role("alert").filter(has_text="Graph no disponible").wait_for()
    expect(page.get_by_role("status").filter(has_text="Código 99")).to_be_visible()

    # A failed document load is resumed from history, without resending enrollment.
    state["document_failure"] = False
    page.get_by_role("button", name="Ingresos registrados", exact=True).click()
    page.get_by_role("button", name="Documentos", exact=True).click()
    module = page.locator(".document-expedient-module")
    module.get_by_role("button", name="Preparar carpeta documental", exact=True).click()
    module.get_by_role("status").filter(has_text="Expediente preparado").wait_for()
    module.get_by_label("Archivo", exact=False).set_input_files({"name": "cedula.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\nmock document"})
    module.get_by_role("button", name="Subir documento", exact=True).click()
    module.get_by_text("cedula.pdf", exact=True).wait_for()
    module.get_by_text("admin@example.test", exact=True).wait_for()
    assert len(uploads) == 1 and len(prepares) == 1 and len(saves) == 2
    page.screenshot(path=str(ROOT / ".runlogs" / f"direct-admission-{name}-documents.png"), full_page=True)
    page.get_by_role("button", name="Nuevo ingreso", exact=True).click()
    expect(form.get_by_label("Identificaci\u00f3n", exact=False)).to_have_value("")
    expect(form.get_by_role("button", name="Validar matr\u00edcula", exact=True)).to_be_disabled()

    # A late reply from an old career cannot repopulate the current pensum.
    state["hold_career"] = True
    form.get_by_label("Carrera", exact=False).select_option("7")
    page.wait_for_timeout(200)
    assert held
    form.get_by_label("Carrera", exact=False).select_option("8")
    expect(form.get_by_label("Nivel", exact=False)).to_be_disabled()
    for route, body in held:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.wait_for_timeout(200)
    expect(form.get_by_role("checkbox", name=re.compile(r"^Matricular "))).to_have_count(0)
    assert not errors, errors
    assert any("IngresoDirectoView.tsx" in script for script in scripts)
    context.close()
    print(f"{name}: level isolation, prerequisites, retry identity, document upload, history and stale-career guards passed")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1600, "height": 1000}),
                               ("mobile", {"width": 390, "height": 844}),
                               ("mobile-small", {"width": 320, "height": 740})]:
            verify(browser, name, viewport)
        browser.close()
