"""Synthetic browser regression: optional student-state supporting documents.

All state updates and uploads are intercepted; never writes to the real API.
"""
import json
import re
from email.parser import BytesParser
from email.policy import default
from urllib.parse import urlparse

from playwright.sync_api import expect
from verify_runtime_optimizations import BASE_URL, mock_context
from verify_student_state_options import section


def verify(browser, name, viewport):
    permission = "gestion-sisacademico/actualizacion_estudiantes"
    context, page, calls, _, errors = mock_context(browser, [permission, 'dashboard'], permission, viewport)
    student = {"_record_key": "student-a", "codigo_estud": "1", "Apellidos_nombre": "PRUEBA ACTIVO",
               "correo": "a@example.test", "codigo_periodo": "1060", "Estado": "A",
               "Informacion": "Motivo anterior que no debe reutilizarse"}
    writes = []

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        if request.method == "POST":
            assert path.endswith("/student-a/cambio-estado-documentado"), path
            message = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
                + request.post_data_buffer)
            parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
            values = {key: part.get_payload(decode=True).decode() for key, part in parts.items()}
            writes.append(values)
            if values["solo_documento"] == "false":
                student["Estado"] = values["estado"]
                student["DescripcionEstado"] = values["detalle"]
                response_message = "Estado actualizado sin documento"
            else:
                assert values["estado"] == student["Estado"]
                assert parts["documento"].get_filename() == "respaldo.pdf"
                student["DocumentoEstado"] = "/uploads/estados_estudiantes/1/respaldo.pdf"
                response_message = "Documento de respaldo adjuntado sin modificar el estado"
            body = {"ok": True, "message": response_message}
        else:
            assert request.method == "GET"
            if path.endswith("/catalog"):
                body = {"sections": [section(True)]}
            else:
                assert path.endswith("/actualizacion_estudiantes"), path
                body = {"section": section(True), "rows": [student], "total": 1,
                        "page": 1, "page_size": 25, "total_pages": 1}
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/students/sisacademico/**", api)
    page.goto(BASE_URL)
    if viewport['width'] < 900:
        page.get_by_role('button', name='Abrir menú principal', exact=True).click()
    page.get_by_role('button', name=re.compile('^Actualizaci')).click()
    page.get_by_role('button', name='Estado estudiante', exact=True).click()
    dashboard_reads_before_save = calls['/api/students/dashboard-matricula']
    select = page.locator("select.gestion-sis-inline-select")
    detail = page.locator("input.gestion-sis-inline-input")
    save = page.get_by_role("button", name="Guardar", exact=True)
    upload = page.get_by_role("button", name="Subir respaldo sin cambiar estado", exact=True)
    expect(select).to_have_value("A")
    expect(detail).to_have_value("")
    saved_description = page.locator('.gestion-sis-state-description')
    expect(saved_description).to_contain_text('Motivo anterior que no debe reutilizarse')
    expect(upload).to_be_disabled()

    # A save requires a different state and a fresh reason, but no document.
    save.click()
    expect(page.get_by_text("Seleccione un estado diferente al estado actual.", exact=True)).to_be_visible()
    select.select_option("P")
    save.click()
    expect(page.get_by_text("Describe el motivo del cambio de estado.", exact=True)).to_be_visible()
    assert not writes
    detail.fill("Cambio autorizado de prueba")
    save.click()
    expect(page.get_by_text("Estado actualizado sin documento", exact=True)).to_be_visible()
    expect(select).to_have_value("P")
    expect(detail).to_have_value("")
    expect(saved_description).to_contain_text('Cambio autorizado de prueba')
    assert calls['/api/students/dashboard-matricula'] == dashboard_reads_before_save + 1, 'Saving must immediately reload dashboard'
    assert len(writes) == 1 and "documento" not in writes[0]
    assert writes[0]["solo_documento"] == "false"

    # Upload later: an unsaved dropdown selection must NOT change the state.
    select.select_option("G")
    page.locator('input[type="file"]').set_input_files(
        {"name": "respaldo.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-synthetic"})
    upload.click()
    expect(page.get_by_text("Documento de respaldo adjuntado sin modificar el estado", exact=True)).to_be_visible()
    expect(select).to_have_value("P")
    expect(saved_description).to_contain_text('Cambio autorizado de prueba')
    assert calls['/api/students/dashboard-matricula'] == dashboard_reads_before_save + 1, 'Attachment-only must not invalidate counters'
    expect(page.get_by_role("link", name="Ver último respaldo", exact=True)).to_be_visible()
    assert len(writes) == 2
    assert writes[1]["solo_documento"] == "true"
    assert writes[1]["estado"] == "P" and writes[1]["detalle"] == ""
    assert not errors, errors
    context.close()
    print(f"{name}: required state/reason, optional file and later upload passed (synthetic only)")
