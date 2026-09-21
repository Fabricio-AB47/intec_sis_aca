"""Person directory and editor regression checks. All API traffic is mocked."""

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


def person(identifier, target):
    return {
        "id": str(identifier), "codigo": str(identifier), "cedula": f"01000000{identifier:02}",
        "nombre": f"PEREZ LOPEZ ANA {'MARIA' if identifier == 1 else 'ISABEL'}",
        "tipo": "estudiante" if target == "estudiantes" else "docente",
        "carrera": "Desarrollo de Software" if target == "estudiantes" else "Escuela de Tecnologias",
        "correo": f"persona{identifier}@example.test", "campos_llenos": 4, "campos_pendientes": 2,
        "campos_totales": 6, "porcentaje_lleno": 66.67, "campos_faltantes": ["movil", "correo"],
    }


def detail(identifier, target):
    current = person(identifier, target)
    fields = {"correo": current["correo"], "movil": "", "paisNacionalidadId": "56"}
    if target == "estudiantes":
        fields.update({"tipodocumento": "1", "Cedula_Est": current["cedula"], "Apellidos_nombre": current["nombre"],
                       "paisResidenciaId": "56", "codprov": "17", "Canton": "1701", "No_Carnet": "0"})
    else:
        fields.update({"tipoDocumentoId": 2, "cedula_doc": current["cedula"], "apellidos_nombre": current["nombre"],
                       "correop": "personal@example.test", "Direccion": "Quito", "carnet_conadis": "0"})
    return {
        "ok": True, "person": current, "fields": fields, "columns": list(fields),
        "field_metadata": {key: {"data_type": "varchar", "nullable": True, "max_length": 100,
                                "readonly": key in ("Cedula_Est", "cedula_doc")} for key in fields},
        "catalogs": {
            "tipoDocumentoId": [{"value": "1", "label": "C\u00e9dula"}, {"value": "2", "label": "Pasaporte"}],
            "paisResidenciaId": [{"value": "56", "label": "Ecuador"}],
            "paisNacionalidadId": [{"value": "56", "label": "Ecuador"}],
            "codprov": [{"value": "17", "label": "Pichincha", "parent_value": "56"},
                        {"value": "1", "label": "Azuay", "parent_value": "56"}],
            "Canton": [{"value": "1701", "label": "Quito", "parent_value": "17"},
                       {"value": "0101", "label": "Cuenca", "parent_value": "1"}],
        },
    }


def verify(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ["actualizar-datos-personas"], "actualizar-datos-personas", viewport)
    searches, reads, writes = [], [], []
    saved = {}
    reject_save = [False]
    hold_save = [False]
    pending_saves = []
    pending_search = []
    native_dialogs = []

    def unexpected_dialog(dialog):
        native_dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", unexpected_dialog)

    def handler(route):
        parsed = urlparse(route.request.url)
        parts = parsed.path.split("/")
        target = parts[4]
        params = parse_qs(parsed.query)
        if parts[5] == "buscar":
            query = params["q"][0]
            offset = int(params.get("offset", [0])[0])
            searches.append((target, query, offset))
            if query == "lento":
                pending_search.append(route)
                return
            body = {"rows": [] if query == "nadie" else [person(1 if offset == 0 else 3, target), person(2, target)],
                    "has_more": offset == 0, "offset": offset, "limit": 20}
        else:
            identifier = int(parts[6])
            key = (target, identifier)
            if route.request.method == "PUT":
                writes.append((target, identifier, route.request.post_data_json))
                if reject_save[0]:
                    route.fulfill(status=400, content_type="application/json", body=json.dumps({"detail": "Correo no valido"}))
                    return
                saved.setdefault(key, {}).update(route.request.post_data_json["fields"])
            else:
                assert route.request.method == "GET"
                reads.append(key)
            body = detail(identifier, target)
            body["fields"].update(saved.get(key, {}))
            body["person"]["campos_pendientes"] = 1 if saved.get(key) else 2
            body["person"]["correo"] = body["fields"]["correo"]
            if route.request.method == "PUT":
                body["message"] = "Datos actualizados correctamente"
                body["updated_fields"] = list(route.request.post_data_json["fields"])
                if hold_save[0]:
                    pending_saves.append((route, body))
                    return
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/actualizacion-datos/**", handler)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Datos de estudiantes y docentes", exact=True).wait_for()
    expect(page.get_by_role("tab", name="Estudiantes", exact=True)).to_have_attribute("aria-selected", "true")
    search = page.get_by_label("Nombre, apellido, c\u00e9dula o c\u00f3digo", exact=True)
    search.fill("Ana Perez")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page.locator(".data-update-directory tbody tr")).to_have_count(2)
    assert not reads and not writes, "Search must not auto-open or save the first match"
    page.screenshot(path=str(ROOT / ".runlogs" / f"person-directory-{name}.png"), full_page=True)
    page.get_by_role("button", name="P\u00e1gina siguiente", exact=True).click()
    expect(page.get_by_text("P\u00e1gina 2", exact=True)).to_be_visible()
    assert searches[-1] == ("estudiantes", "Ana Perez", 20)
    page.get_by_role("button", name="P\u00e1gina anterior", exact=True).click()
    expect(page.get_by_text("P\u00e1gina 1", exact=True)).to_be_visible()
    page.get_by_role("button", name="Editar datos de PEREZ LOPEZ ANA ISABEL", exact=True).click()
    modal = page.get_by_role("dialog")
    expect(modal).to_be_visible()
    expect(modal.get_by_role("heading", name="PEREZ LOPEZ ANA ISABEL")).to_be_visible()
    cell = modal.get_by_label("Celular", exact=True)
    expect(cell).to_be_visible()
    assert reads[-1] == ("estudiantes", 2)
    expect(modal.get_by_role("button", name="Guardar cambios", exact=True)).to_be_disabled()
    assert page.evaluate("document.activeElement.closest('dialog') !== null")
    document_type = modal.get_by_role("combobox", name="Tipo de documento", exact=True)
    expect(document_type).to_have_value("1")
    expect(document_type.locator('option[value="1"]')).to_have_text("C\u00e9dula")
    expect(document_type.locator('option[value="2"]')).to_have_text("Pasaporte")
    document_type.select_option(label="Pasaporte")
    carnet = modal.get_by_role("textbox", name="N\u00famero de carn\u00e9", exact=True)
    expect(carnet).to_have_value("0")
    assert carnet.get_attribute("inputmode") != "numeric"
    carnet.fill("NA")
    cell.fill("0991112233")
    reject_save[0] = True
    modal.get_by_role("button", name="Guardar cambios", exact=True).click()
    expect(modal.get_by_role("alert")).to_have_text("Correo no valido")
    expect(cell).to_have_value("0991112233")
    expect(document_type).to_have_value("2")
    expect(carnet).to_have_value("NA")
    reject_save[0] = False
    modal.get_by_role("button", name="Guardar cambios", exact=True).click()
    expect(modal.get_by_role("status")).to_contain_text("Datos actualizados correctamente")
    assert writes[-1] == ("estudiantes", 2, {"fields": {"tipodocumento": "2", "movil": "0991112233", "No_Carnet": "NA"}})
    expect(modal.get_by_role("button", name="Guardar cambios", exact=True)).to_be_disabled()
    page.screenshot(path=str(ROOT / ".runlogs" / f"person-editor-{name}.png"), full_page=True)
    box = modal.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= viewport["width"]
    assert 0 <= box["y"] and box["y"] + box["height"] <= viewport["height"]
    cell.fill("0994445566")
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    notice = page.get_by_role("alertdialog", name="Cambios sin guardar", exact=True)
    expect(notice).to_be_visible()
    expect(notice.get_by_role("list", name="Campos modificados")).to_have_text("Celular")
    expect(notice.get_by_text("Estudiante \u00b7 C\u00f3digo 2", exact=True)).to_be_visible()
    assert notice.evaluate("element => element.contains(document.activeElement)")
    notice_box = notice.bounding_box()
    assert notice_box["x"] >= 0 and notice_box["x"] + notice_box["width"] <= viewport["width"]
    assert notice_box["y"] >= 0 and notice_box["y"] + notice_box["height"] <= viewport["height"]
    page.screenshot(path=str(ROOT / ".runlogs" / f"person-close-notice-{name}.png"))
    notice.get_by_role("button", name="Continuar editando", exact=True).click()
    expect(notice).not_to_be_visible()
    expect(modal).to_be_visible()
    expect(cell).to_have_value("0994445566")
    page.keyboard.press("Escape")
    expect(notice).to_be_visible()
    page.keyboard.press("Escape")
    expect(notice).not_to_be_visible()
    expect(cell).to_have_value("0994445566")
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    before_discard = len(writes)
    notice.get_by_role("button", name="Descartar cambios", exact=True).click()
    expect(modal).not_to_be_visible()
    expect(notice).not_to_be_visible()
    expect(page.locator(".data-update-notice[role=status]")).to_contain_text("Se descartaron los cambios pendientes")
    assert len(writes) == before_discard
    student_row = page.locator(".data-update-directory tbody tr").filter(has_text="PEREZ LOPEZ ANA ISABEL")
    expect(student_row.locator('td[data-label="Campos pendientes"]')).to_have_text("1")
    student_row.get_by_role("button", name="Editar datos de PEREZ LOPEZ ANA ISABEL", exact=True).click()
    expect(cell).to_have_value("0991112233")
    expect(document_type).to_have_value("2")
    expect(carnet).to_have_value("NA")
    cell.fill("0995556677")
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    reject_save[0] = True
    notice.get_by_role("button", name="Guardar y cerrar", exact=True).click()
    expect(notice.get_by_role("alert")).to_have_text("Correo no valido")
    expect(cell).to_have_value("0995556677")
    expect(modal).to_be_visible()
    reject_save[0] = False
    hold_save[0] = True
    before_save = len(writes)
    notice.get_by_role("button", name="Guardar y cerrar", exact=True).click()
    expect(notice.get_by_role("status")).to_have_text("Guardando datos...")
    for button in notice.get_by_role("button").all():
        expect(button).to_be_disabled()
    page.keyboard.press("Escape")
    expect(notice).to_be_visible()
    page.wait_for_timeout(100)
    assert len(writes) == before_save + 1
    route, body = pending_saves.pop()
    hold_save[0] = False
    route.fulfill(content_type="application/json", body=json.dumps(body))
    expect(notice).not_to_be_visible()
    expect(modal).not_to_be_visible()
    expect(page.locator(".data-update-notice[role=status]")).to_contain_text("Datos actualizados correctamente")
    assert writes[-1] == ("estudiantes", 2, {"fields": {"movil": "0995556677"}})
    student_row.get_by_role("button", name="Editar datos de PEREZ LOPEZ ANA ISABEL", exact=True).click()
    expect(cell).to_have_value("0995556677")
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    expect(notice).not_to_be_visible()
    page.get_by_role("tab", name="Docentes", exact=True).click()
    expect(page.locator(".data-update-directory tbody tr")).to_have_count(0)
    page.get_by_role("button", name="Buscar", exact=True).click()
    page.get_by_role("button", name="Editar datos de PEREZ LOPEZ ANA MARIA", exact=True).click()
    expect(modal.get_by_label("Correo personal", exact=True)).to_be_visible()
    expect(document_type).to_have_value("2")
    expect(document_type.locator('option[value="1"]')).to_have_text("C\u00e9dula")
    expect(document_type.locator('option[value="2"]')).to_have_text("Pasaporte")
    document_type.select_option(label="C\u00e9dula")
    carnet = modal.get_by_role("textbox", name="Carn\u00e9 CONADIS", exact=True)
    expect(carnet).to_have_value("0")
    assert carnet.get_attribute("inputmode") != "numeric"
    carnet.fill("NA")
    modal.get_by_label("Correo personal", exact=True).fill("actualizado@example.test")
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    expect(notice.get_by_text("Docente \u00b7 C\u00f3digo 1", exact=True)).to_be_visible()
    notice.get_by_role("button", name="Guardar y cerrar", exact=True).click()
    expect(page.locator(".data-update-notice[role=status]")).to_contain_text("Datos actualizados correctamente")
    assert writes[-1] == ("docentes", 1, {"fields": {"tipoDocumentoId": "1", "correop": "actualizado@example.test", "carnet_conadis": "NA"}})
    expect(modal).not_to_be_visible()
    expect(notice).not_to_be_visible()
    teacher_row = page.locator(".data-update-directory tbody tr").filter(has_text="PEREZ LOPEZ ANA MARIA")
    expect(teacher_row.locator('td[data-label="Campos pendientes"]')).to_have_text("1")
    teacher_row.get_by_role("button", name="Editar datos de PEREZ LOPEZ ANA MARIA", exact=True).click()
    expect(document_type).to_have_value("1")
    expect(carnet).to_have_value("NA")
    expect(modal.get_by_role("button", name="Guardar cambios", exact=True)).to_be_disabled()
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    search.fill("nadie")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page.get_by_text("No se encontraron docentes para \u00abnadie\u00bb.", exact=True)).to_be_visible()
    search.fill("lento")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page.get_by_text("Buscando coincidencias...", exact=True)).to_be_visible()
    page.wait_for_timeout(150)
    assert pending_search
    page.get_by_role("tab", name="Estudiantes", exact=True).click()
    pending_search[0].fulfill(content_type="application/json", body=json.dumps({"rows": [person(1, "docentes")]}))
    page.wait_for_timeout(200)
    expect(page.locator(".data-update-directory tbody tr")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Page overflow"
    assert not errors, errors
    assert not native_dialogs, native_dialogs
    context.close()
    print(f"{name}: search, selection, document type codes, NA carnet values, custom close notice, discard, save/close, retry, refreshed rows and no browser prompts passed")


def verify_existing_document_lookup_and_menu(browser, name, viewport):
    context, page, _, _, errors = mock_context(
        browser, ["actualizar-datos-estudiante", "actualizar-datos-personas"], "actualizar-datos-estudiante", viewport,
    )

    def handler(route):
        assert route.request.method == "GET"
        parts = urlparse(route.request.url).path.split("/")
        if parts[5] == "buscar":
            body = {"rows": [person(2, "estudiantes")] if parts[4] == "estudiantes" else []}
        else:
            assert parts[4] == "estudiantes" and parts[6] == "2"
            body = detail(2, "estudiantes")
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/actualizacion-datos/**", handler)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Actualizaci\u00f3n de datos", exact=True).wait_for()
    page.get_by_label("N\u00famero de c\u00e9dula o pasaporte", exact=True).fill("0100000002")
    page.get_by_role("button", name="Buscar por c\u00e9dula o pasaporte", exact=True).click()
    modal = page.get_by_role("dialog")
    expect(modal.get_by_role("heading", name="PEREZ LOPEZ ANA ISABEL", exact=True)).to_be_visible()
    expect(modal.get_by_label("Celular", exact=True)).to_be_visible()
    modal.get_by_role("button", name="Cerrar ficha", exact=True).click()
    if viewport["width"] < 700:
        page.get_by_role("button", name="Abrir men\u00fa principal", exact=True).click()
    else:
        page.get_by_role("complementary", name="Men\u00fa lateral", exact=True).hover()
    group = page.locator(".student-nav__group-button").filter(has_text="Actualizaci\u00f3n")
    if group.get_attribute("aria-expanded") != "true":
        group.click()
    entry = page.locator('[data-screen-page="actualizar-datos-personas"]')
    expect(entry).to_be_visible()
    entry.click()
    expect(page.get_by_role("heading", name="Datos de estudiantes y docentes", exact=True)).to_be_visible()
    assert not errors, errors
    context.close()
    print(f"{name}: existing document lookup and navigation to the new directory passed")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1500, "height": 940}), ("mobile", {"width": 390, "height": 844})]:
            verify(browser, name, viewport)
            verify_existing_document_lookup_and_menu(browser, name, viewport)
        browser.close()
