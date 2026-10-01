"""Synthetic compliance UI regression; no real API reads or writes."""
import json
from urllib.parse import urlparse

from playwright.sync_api import expect
from verify_runtime_optimizations import BASE_URL, mock_context


def verify(browser, name, viewport, honoraria=False):
    screen = "portal-docente-informe"
    context, page, _, _, errors = mock_context(browser, [screen], screen, viewport)
    course = {
        "codigo_materia": "209", "cod_materia": "VGA-TEST-209",
        "nombre_materia": "Curso de prueba", "cod_anio_basica": "7",
        "nombre_carrera": "Ciberseguridad", "codigo_periodo": "1055",
        "codigo_periodos": ["1055"], "detalle_periodo": "C1-HOMO-2026-PB",
        "paralelo": "A", "tipo_periodo": "H", "es_homologacion": True,
        "total_estudiantes": 1, "tiene_homologacion": True,
    }
    student = {
        **course, "codigo_estud": "1", "nombre_estudiante": "Estudiante prueba",
        "cedula": "TEST", "correo_intec": "prueba@intec.edu.ec", "promedio_final": 9.4,
        "esquema_calificacion": "HOMOLOGACION", "teoria_homo": 8.5, "practica_homo": 10,
    }
    state = {"different": False, "offline": False}
    generated = []
    signed = []
    archived = []

    def handler(route):
        path = urlparse(route.request.url).path
        if honoraria and path.endswith('/contracts/analyze-document'):
            route.fulfill(content_type='application/json', body=json.dumps({
                'codigo_materia': '209', 'numero_contrato': 'TEST',
                'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-09-30', 'warnings': []}))
            return
        if honoraria and path.endswith(('/student-grade-report-sign', '/contracts/sign-uploaded', '/compliance-report-sign')):
            signed.append(path)
            route.fulfill(content_type='application/pdf', body=b'%PDF-1.4\nsynthetic-signed\n%%EOF')
            return
        if honoraria and path.endswith('/signed-documents-archive'):
            payload = route.request.post_data_buffer
            assert b'synthetic-signed' in payload
            assert b'invoice-test' in payload and b'ride-test' in payload
            archived.append(payload)
            if len(archived) == 2:
                assert b'existing_folder_path' in payload and b'DOCENTES/test' in payload
            route.fulfill(content_type='application/zip', body=b'PK-test', headers={
                'X-OneDrive-Saved': 'true', 'X-OneDrive-Same-Folder': 'true',
                'X-OneDrive-Item-Count': '6', 'X-OneDrive-Folder': 'DOCENTES/test',
                'X-Honorarios-Email-Status': 'error' if len(archived) == 1 else 'sent',
                'X-Honorarios-Email-Message': 'Fallo%20simulado' if len(archived) == 1 else ''})
            return
        if path.endswith("/teacher/compliance-report-pdf"):
            assert route.request.method == "POST"
            generated.append(route.request.post_data_buffer.decode("utf-8", errors="replace"))
            route.fulfill(content_type="application/pdf", body=b"%PDF-1.4\n%%EOF")
            return
        assert route.request.method == "GET"
        if path == "/api/auth/me":
            body = {"login": "docente@example.test", "nombres": "Docente prueba", "rol": "DOCENTE", "perfiles": []}
        elif path == "/api/auth/screen-access":
            body = {"current_role": "DOCENTE", "screens": [], "roles": [{
                "value": "DOCENTE", "pages": [screen], "default_pages": [], "configured": True, "protected": False}]}
        elif path.endswith("/teacher/courses"):
            body = {"items": [course], "total": 1}
        elif path.endswith("/teacher/subject-students"):
            body = {"items": [student], "total": 1}
        elif path.endswith("/teacher/compliance-moodle-resources"):
            if state["offline"]:
                route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Moodle temporalmente no disponible"}))
                return
            difference = {**student, "nota_moodle": 8.5, "notas_intec": [], "componentes": [{
                "campo": "teoriaHomo", "componente": "Examen teórico de homologación",
                "actividad": "Cuestionario de Evaluación", "item_id": 1, "nota_moodle": 8.5, "nota_intec": None}]}
            body = {"matched": True, "selected_course_id": 1490, "courses": [], "academic": {},
                    "resources": {"sections": [], "totals": {"sections": 0, "modules": 0, "files": 0}},
                    "student_email_validation": {"mode": "moodle_enrollment", "matched": 1}, "student_email_matches": 1,
                    "grade_validation": {
                        "passing_grade": 7, "failed_threshold_percent": 10, "justification_min_length": 20,
                        "total_records": 1, "graded_records": 1, "missing_academic_count": 0,
                        "failed_count": 0, "failed_percentage": 0, "requires_justification": False,
                        "can_generate": not state["different"], "blockers": ["Diferencia de componente"] if state["different"] else [],
                        "missing_academic_students": [], "failed_students": [], "students_without_email": [],
                        "moodle": {"comparison_source": "evaluation_components", "checked": True,
                                   "course_id": 1490, "course_name": "Prueba", "error": "",
                                   "verified_students": 0 if state["different"] else 1,
                                   "not_enrolled_students": [], "missing_grade_students": [],
                                   "discrepancies": [difference] if state["different"] else []}}}
        else:
            body = {"items": [], "value": [], "total": 0}
        route.fulfill(content_type="application/json", body=json.dumps(body))

    context.route("**/api/**", handler)
    if honoraria:
        context.route(BASE_URL.rstrip('/') + '/', lambda route: route.fulfill(
            path=str(browser.build / 'index.html'), content_type='text/html',
            headers={'Content-Security-Policy': "connect-src 'self'"}))
        context.add_init_script("""window.blobFetches = [];
            const originalFetch = window.fetch;
            window.fetch = function(input, options) {
                if (String(input).startsWith('blob:')) window.blobFetches.push(String(input));
                return originalFetch.call(this, input, options);
            };""")
    page.goto(BASE_URL)
    panel = page.locator(".portal-compliance-grade-validation")
    expect(panel).to_be_visible(timeout=15000)
    expect(panel).to_contain_text("No se utiliza el total del curso de Moodle")
    expect(panel).not_to_contain_text("Diferencias en Evaluación")
    state["different"] = True
    page.get_by_role("button", name="Actualizar recursos", exact=True).click()
    expect(panel).to_contain_text("Examen teórico de homologación")
    expect(panel).to_contain_text("Moodle Evaluación 8.50")
    expect(panel).to_contain_text("INTECBDD Sin nota")
    expect(panel).to_contain_text("Informe habilitado")
    justification = page.get_by_label("Justificación académica (opcional)", exact=False)
    expect(justification).to_be_visible()
    justification.fill("Estudiante prueba pendiente de examen por ausencia justificada.")
    assert page.locator('#portal-justification-title').evaluate(
        "el => !!(el.compareDocumentPosition(document.querySelector('#portal-signature-title')) & Node.DOCUMENT_POSITION_FOLLOWING)")
    download = page.get_by_role("button", name="Descargar PDF sin firma", exact=True)
    expect(download).to_be_enabled()
    with page.expect_download(): download.click()
    assert "ausencia justificada" in generated[-1]
    state["offline"] = True
    page.get_by_role("button", name="Actualizar recursos", exact=True).click()
    expect(page.get_by_text("Moodle temporalmente no disponible", exact=True)).to_be_visible()
    expect(download).to_be_enabled()
    justification.fill("")
    with page.expect_download(): download.click()
    assert len(generated) == 2
    if honoraria:
        def upload(label, filename, content, mime):
            page.get_by_label(label, exact=False).set_input_files({'name': filename, 'mimeType': mime, 'buffer': content})

        upload('Contrato docente PDF', 'test.pdf', b'%PDF-test-contract', 'application/pdf')
        expect(page.get_by_text('Contrato validado. Las fechas de inicio y fin se completaron desde el PDF.', exact=True)).to_be_visible()
        expect(page.locator('.institutional-email-notification-overlay')).to_be_hidden(timeout=6000)
        upload('Factura electrónica XML', 'test.xml', b'<invoice-test/>', 'application/xml')
        upload('RIDE en PDF', 'ride.pdf', b'%PDF-ride-test', 'application/pdf')
        upload('Archivo de certificado', 'synthetic.p12', b'not-a-real-certificate', 'application/x-pkcs12')
        page.get_by_placeholder('Contraseña del archivo .p12').fill('synthetic-password')
        page.get_by_label('Confirmo que soy titular', exact=False).check()
        page.get_by_role('button', name='Firmar, archivar y enviar si hay factura', exact=True).click()
        expect(page.get_by_text('Fallo simulado', exact=True)).to_be_visible(timeout=15000)
        expect(page.locator('.institutional-email-notification-overlay')).to_be_hidden(timeout=6000)
        retry = page.get_by_role('button', name='Completar y enviar honorarios', exact=True)
        expect(retry).to_be_enabled()
        retry.click()
        expect(page.get_by_role('button', name='Correo enviado', exact=True)).to_be_disabled(timeout=15000)
        assert len(signed) == 4 and len(archived) == 2
        assert b'notas_por_carrera' in archived[-1]
        assert page.evaluate('window.blobFetches') == []
        print(f'{name}: retry retained all six files including career annex, reused folder, no re-signing or blob fetch under CSP', flush=True)
    assert not errors, errors
    context.close()
    print(f"{name}: advisory findings, optional justification, download and Moodle outage verified", flush=True)
