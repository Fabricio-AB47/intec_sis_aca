"""Student state catalog regression. All API calls are synthetic and read-only."""
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from verify_runtime_optimizations import BASE_URL, mock_context


STATES = [("A", "Activo"), ("C", "Cambio Periodo"), ("D", "E Continua"),
          ("E", "Reingreso"), ("G", "Graduado"), ("P", "Inactivo"), ("R", "Retirado")]


def section(with_options):
    fields = [{"name": key, "label": label, "type": "text", "options": []}
              for key, label in [("codigo_estud", "Codigo"), ("Apellidos_nombre", "Nombre"),
                                  ("correo", "Correo personal"), ("codigo_periodo", "Periodo"),
                                  ("Estado", "Estado")]]
    state = {"name": "Estado", "label": "Estado estudiante", "type": "text", "required": True,
             "options": [{"value": code, "label": f"{code} - {name}"} for code, name in STATES] if with_options else []}
    return {"key": "actualizacion_estudiantes", "title": "Actualización de estados de estudiantes",
            "category": "Personas", "description": "Catalogo de estados", "table": "dbo.DATOS_ESTUD + dbo.ESTADO",
            "key_fields": ["Cedula_Est"], "list_fields": fields, "detail_fields": fields,
            "editable_fields": [state, {"name": "Informacion", "label": "Descripcion", "type": "textarea"}],
            "create_fields": [], "defaults": {}}


def verify(browser, name, viewport):
    permission = "gestion-sisacademico/actualizacion_estudiantes"
    context, page, _, _, errors = mock_context(browser, [permission], permission, viewport)
    list_calls = []

    def api(route):
        assert route.request.method == "GET", "This regression must not change student states"
        parsed = urlparse(route.request.url)
        if parsed.path.endswith("/catalog"):
            body = {"sections": [section(False)]}
        else:
            assert parsed.path.endswith("/actualizacion_estudiantes"), parsed.path
            params = parse_qs(parsed.query)
            current_page = int(params.get("page", ["1"])[0])
            list_calls.append(params)
            body = {"section": section(True), "rows": [
                {"_record_key": "student-a", "codigo_estud": "1", "Apellidos_nombre": "PRUEBA ACTIVO",
                 "correo": "a@example.test", "codigo_periodo": "1060", "Estado": "A"},
                {"_record_key": "student-d", "codigo_estud": "2", "Apellidos_nombre": "PRUEBA CONTINUA",
                 "correo": "d@example.test", "codigo_periodo": "1060", "Estado": "D"}],
                "total": 26, "page": current_page, "page_size": 25, "total_pages": 2}
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/sisacademico/**", api)
    page.goto(BASE_URL)
    selects = page.locator("select.gestion-sis-inline-select")
    expect(selects).to_have_count(2)

    def assert_all_options():
        for index in range(2):
            expect(selects.nth(index).locator("option")).to_have_count(8)
            for code, label in STATES:
                expect(selects.nth(index).locator(f'option[value="{code}"]')).to_have_text(f"{code} - {label}")

    assert_all_options()
    expect(selects.nth(0)).to_have_value("A")
    expect(selects.nth(1)).to_have_value("D")
    for code, _ in STATES:
        selects.nth(0).select_option(code)
        expect(selects.nth(0)).to_have_value(code)
        expect(selects.nth(1)).to_have_value("D")
    with page.expect_response(lambda response: urlparse(response.url).path.endswith("/actualizacion_estudiantes")):
        page.get_by_role("button", name="Siguiente", exact=True).click()
    expect(selects.nth(0)).to_have_value("A")
    assert_all_options()
    with page.expect_response(lambda response: urlparse(response.url).path.endswith("/actualizacion_estudiantes")):
        page.get_by_role("button", name="Filtrar", exact=True).click()
    assert_all_options()
    assert len(list_calls) >= 3, list_calls
    assert not errors, errors
    context.close()
    print(f"{name}: all 7 states, independent selection, pagination and refresh passed")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            verify(browser, "desktop", {"width": 1500, "height": 940})
            verify(browser, "mobile", {"width": 390, "height": 844})
        finally:
            browser.close()
