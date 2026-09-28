"""Shared visual contract in the real app; requests never reach institutional APIs."""

import json

from playwright.sync_api import expect, sync_playwright
from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


STYLE_FILES = sorted((ROOT / "frontend/src").rglob("*.css"))
EXPECTED = {
    "fontFamily": '"Segoe UI", Tahoma, Geneva, Verdana, sans-serif',
    "borderRadius": "6px",
    "minHeight": "40px",
    "letterSpacing": "normal",
}


def style(locator):
    return locator.evaluate("""el => {
        const s = getComputedStyle(el);
        return Object.fromEntries(['fontFamily', 'fontSize', 'fontWeight', 'borderRadius',
            'minHeight', 'backgroundColor', 'color', 'letterSpacing'].map(k => [k, s[k]]));
    }""")


def verify_contract(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ["dashboard"], "dashboard", viewport)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Dashboard Estudiantil", exact=True).wait_for()
    page.evaluate("""() => {
        const section = document.createElement('section');
        section.id = 'style-contract';
        section.innerHTML = `<div class="student-card">
            <h2>Contrato visual de prueba</h2>
            <div class="enrollment-check">
                <button class="primary-action" id="theme-primary">Guardar</button>
                <button class="ghost-button" id="theme-secondary">Cancelar</button>
                <button class="primary-action" id="theme-disabled" disabled>Procesando</button>
                <input id="theme-input" aria-label="Nombre de prueba" value="Dato conservado" />
                <select id="theme-select" aria-label="Estado de prueba"><option>Activo</option></select>
                <input id="theme-checkbox" type="checkbox" aria-label="Seleccionar prueba" />
                <table><thead><tr><th>Nombre</th></tr></thead><tbody><tr><td>Prueba</td></tr></tbody></table>
            </div>
        </div>`;
        document.querySelector('.student-main, .app').append(section);
    }""")
    primary = page.locator("#theme-primary")
    initial = style(primary)
    for field, expected in EXPECTED.items():
        assert initial[field] == expected, (name, field, initial)
    assert initial["backgroundColor"] == "rgb(147, 25, 19)", initial
    assert initial["color"] == "rgb(255, 255, 255)", initial
    assert initial["fontSize"] == "13px", initial
    assert initial["fontWeight"] == "600", initial
    # A lazy module must not override the visual contract, regardless of load order.
    paths = ["/src/" + str(file.relative_to(ROOT / "frontend/src")).replace("\\", "/") for file in STYLE_FILES]
    for batch in (paths, list(reversed(paths))):
        for path in batch:
            awaitable = "async path => { const mod = await import(path + '?raw'); const s = document.createElement('style'); s.textContent = mod.default; document.head.append(s); }"
            page.evaluate(awaitable, path)
        assert style(primary) == initial, (name, "Lazy style priority changed", style(primary), initial)
    for selector in ("#theme-input", "#theme-select"):
        result = style(page.locator(selector))
        assert result["fontFamily"] == initial["fontFamily"], result
        assert result["fontSize"] == "14px" and result["borderRadius"] == "6px", result
        assert result["minHeight"] == "40px", result
    primary.focus()
    assert primary.evaluate("e => getComputedStyle(e).outlineStyle") == "solid"
    expect(page.locator("#theme-input")).to_have_value("Dato conservado")
    expect(page.locator("#theme-disabled")).to_be_disabled()
    assert style(page.locator("#theme-disabled"))["backgroundColor"] == "rgb(233, 237, 240)"
    page.locator("#theme-checkbox").check()
    expect(page.locator("#theme-checkbox")).to_be_checked()
    page.locator("#theme-input").evaluate("e => e.setAttribute('aria-invalid', 'true')")
    assert page.locator("#theme-input").evaluate("e => getComputedStyle(e).borderTopColor") == "rgb(172, 38, 30)"
    page.locator("#style-contract").evaluate("e => e.remove()")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name
    page.screenshot(path=str(ROOT / ".runlogs" / f"unified-dashboard-{name}.png"), full_page=True)
    page.emulate_media(reduced_motion="reduce")
    assert page.locator(".app button").first.evaluate("e => parseFloat(getComputedStyle(e).transitionDuration) < .01")
    # Embedded printable reports keep their own font, dimensions and stylesheet.
    page.evaluate("""() => {
        const frame = document.createElement('iframe');
        frame.id = 'document-test';
        frame.srcdoc = '<style>body{font-family:serif;font-size:12pt;color:navy}h1{font-size:20pt}</style><h1>Documento</h1>';
        document.querySelector('.app').append(frame);
    }""")
    heading = page.frame_locator("#document-test").locator("h1")
    expect(heading).to_have_text("Documento")
    assert heading.evaluate("e => getComputedStyle(e).color") == "rgb(0, 0, 128)"
    assert heading.evaluate("e => getComputedStyle(e).fontFamily") == "serif"
    assert not errors, errors
    context.close()
    print(f"{name}: shared controls, lazy CSS order, keyboard focus, disabled/error states, reduced motion and isolated report passed")


def verify_login(browser):
    context, page, _, _, errors = mock_context(browser, [], "dashboard", {"width": 1366, "height": 900}, anonymous=True)
    page.goto(BASE_URL)
    page.locator("input[type=password]").wait_for()
    assert page.locator(".app--auth").evaluate("e => getComputedStyle(e).backgroundImage").startswith("radial-gradient")
    assert page.locator(".login-panel h2").evaluate("e => getComputedStyle(e).color") == "rgb(255, 255, 255)"
    page.screenshot(path=str(ROOT / ".runlogs/unified-login.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors, errors
    context.close()


def verify_other_modules(browser, name, viewport):
    for module, heading in [("secretaria-general", "Verificaci\u00f3n de expedientes de grado"),
                            ("actualizar-malla-carrera", "Actualizar malla por carrera")]:
        context, page, _, _, errors = mock_context(browser, [module], module, viewport)
        context.route("**/api/secretaria-general/dashboard", lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({
                "candidates": {"total": 0, "proximos": 0, "egresados": 0, "graduados": 0},
                "cases": {"expedientes": 0, "en_validacion": 0, "observados": 0, "aprobados": 0,
                          "documentos_faltantes": 0, "estudiantes_con_faltantes": 0}})))
        context.route("**/api/secretaria-general/candidates?*", lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({"items": [], "total": 0,
                "page": 1, "page_size": 25, "total_pages": 1})))
        page.goto(BASE_URL)
        title = page.get_by_role("heading", name=heading, exact=True)
        title.wait_for()
        assert style(title)["fontSize"] == "28px", style(title)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (module, name)
        page.screenshot(path=str(ROOT / ".runlogs" / f"unified-{module}-{name}.png"), full_page=True)
        assert not errors, errors
        context.close()
    print(f"{name}: secretariat and curriculum modules share headings and responsive layout")




if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1500, "height": 950}), ("mobile", {"width": 390, "height": 844})]:
            verify_contract(browser, name, viewport)
            verify_other_modules(browser, name, viewport)
        verify_login(browser)
        browser.close()
