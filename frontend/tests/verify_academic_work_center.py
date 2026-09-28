"""Academic work center checks. All API requests are mocked; no institutional writes."""

from collections import Counter
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


PERMISSIONS = ['sistema-academico', 'secretaria-general', 'solicitudes-cambio-carrera',
               'solicitudes-cambio-modalidad', 'gestion-sisacademico/periodos',
               'preinscripcion/registro', 'reporteria-integral/carrera']


def setup(browser, viewport, permissions=PERMISSIONS):
    context, page, _, _, errors = mock_context(browser, permissions, 'sistema-academico', viewport)
    seen = Counter()
    flags = {'modality_error': True, 'health_error': True, 'summary_error': False}

    def handler(route):
        parsed = urlparse(route.request.url)
        path, query = parsed.path, parse_qs(parsed.query)
        seen[path] += 1
        assert route.request.method == 'GET', 'No write allowed: ' + path
        status = 200
        if path == '/api/students/dashboard-matricula':
            status = 503 if flags['summary_error'] else 200
            body = {'total_estudiantes': 80, 'active_regular_students': 60,
                    'active_homologation_students': 10, 'states': [{'estado_codigo': 'G', 'total_estudiantes': 3}]}
        elif path == '/api/secretaria-general/candidates':
            assert query['only_missing_documents'] == ['true']
            body = {'total': 1, 'page': 1, 'page_size': 10, 'total_pages': 1, 'items': [{
                'codigo_estud': 21, 'apellidos_nombres': 'ESTUDIANTE DOCUMENTAL', 'numero_identificacion': '001',
                'nombre_carrera': 'Desarrollo de Software', 'nombre_periodo': 'C1-2026', 'secretaria': {'missing': 3}}]}
        elif path in ('/api/requests/career-change/pending', '/api/requests/modality-change/pending'):
            is_modality = 'modality-change' in path
            if is_modality and flags['modality_error']:
                status, body = 503, {'detail': 'Fuente temporalmente no disponible.'}
            else:
                number = int(query.get('page', ['1'])[0])
                total = 0 if query.get('query') == ['Nadie'] or is_modality else 221
                items = [{'id': i, 'student_code': i, 'student': f'ESTUDIANTE {i}', 'identification': f'00{i}',
                          'career': 'Desarrollo de Software', 'period': 'C1-2026',
                          'state': 'APROBADA' if i % 2 else 'PENDIENTE', 'created_at': '2026-09-22T00:00:00Z'}
                         for i in range((number - 1) * 10 + 1, min(number * 10, total) + 1)]
                body = {'total': total, 'page': number, 'page_size': 10, 'total_pages': max(1, (total + 9) // 10),
                        'items': items, 'checked_at': '2026-09-22T00:00:00Z'}
        elif path == '/api/academic-system/integration-status':
            if flags['health_error']:
                status, body = 503, {'detail': 'Verificacion no disponible'}
            else:
                body = {'summary': {'available': 1, 'total': 2}, 'generated_at': '2026-09-22T12:00:00Z',
                        'databases': [{'key': 'academic', 'name': 'INTECBDD', 'status': 'ONLINE', 'available': True,
                                       'configured': True, 'role': 'Registros academicos', 'relation': 'Principal'}]}
        else:
            route.fallback()
            return
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

    context.route('**/api/**', handler)
    return context, page, seen, flags, errors


def verify(browser, name, viewport):
    context, page, seen, flags, errors = setup(browser, viewport)
    page.goto(BASE_URL)
    view = page.locator('.academic-work-center')
    summary = page.get_by_role('region', name='Resumen acad\u00e9mico')
    expect(summary).to_contain_text('80')
    assert seen['/api/students/dashboard-matricula'] == 1, 'Summary must load after direct navigation'
    banner = page.locator('.unified-alert-indicator')
    expect(banner).to_contain_text('222 pendientes')
    expect(view.locator('.academic-pending')).to_have_count(0)
    assert seen['/api/academic-system/integration-status'] == 0, 'Health checks must be on demand'
    assert not page.locator('.academic-process-map, .academic-system-controls').count()
    expect(view.get_by_role('button', name='Abrir Asignaci\u00f3n docente')).to_be_disabled()
    expect(view.get_by_role('button', name='Abrir Admisi\u00f3n e inscripci\u00f3n')).to_be_enabled()
    expect(view.get_by_role('button', name='Abrir Reportes institucionales')).to_be_enabled()
    view.get_by_role('button', name='Formaci\u00f3n', exact=True).click()
    expect(view.locator('.academic-lifecycle__row')).to_have_count(2)
    view.get_by_role('button', name='Todos', exact=True).click()
    expect(view.locator('.academic-lifecycle__row')).to_have_count(8)
    banner.click()
    dialog = page.get_by_role('dialog', name='Pendientes acad\u00e9micos')
    rows = dialog.locator('.unified-alert-source')
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text('1')
    expect(rows.nth(1)).to_contain_text('221')
    expect(rows.nth(2)).to_contain_text('No disponible')
    dialog.get_by_role('button', name='Cambio de carrera', exact=True).click()
    expect(dialog).to_contain_text('221 solicitudes')
    expect(dialog.locator('tbody tr')).to_have_count(10)
    expect(dialog).to_contain_text('Aprobada; falta aplicar')
    dialog.get_by_role('button', name='P\u00e1gina siguiente').click()
    expect(dialog).to_contain_text('P\u00e1gina 2 de 23')
    expect(dialog).to_contain_text('ESTUDIANTE 11')
    search_input = dialog.get_by_label('Buscar estudiante').bounding_box()
    search_button = dialog.get_by_role('button', name='Buscar', exact=True).bounding_box()
    assert search_input and search_button and search_input['x'] + search_input['width'] <= search_button['x'], (search_input, search_button)
    page.screenshot(path=str(ROOT / '.runlogs' / f'academic-pending-{name}.png'))
    bounds = dialog.bounding_box()
    assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= viewport['width']
    dialog.get_by_label('Buscar estudiante').fill('Nadie')
    dialog.get_by_role('button', name='Buscar', exact=True).click()
    expect(dialog).to_contain_text('0 solicitudes')
    expect(dialog).to_contain_text('No hay pendientes con estos criterios.')
    expect(dialog.get_by_role('button', name='P\u00e1gina siguiente')).to_be_disabled()
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    banner.click()
    dialog.get_by_role('button', name='Documentaci\u00f3n de Secretar\u00eda', exact=True).click()
    documents = dialog
    expect(documents).to_contain_text('3 documentos faltantes')
    flags['modality_error'] = False
    dialog.get_by_role('button', name='Actualizar', exact=True).click()
    expect(rows.nth(2)).not_to_contain_text('No disponible')
    expect(rows.nth(2)).to_be_enabled()
    dialog.get_by_role('button', name='Cerrar pendientes').click()
    details = view.locator('details')
    details.locator('summary').click()
    expect(details.get_by_role('alert')).to_contain_text('No se pudo verificar')
    assert '0 fuentes' not in details.inner_text()
    flags['health_error'] = False
    details.get_by_role('button', name='Verificar conexiones').click()
    expect(details).to_contain_text('1 de 2 fuentes disponibles')
    page.screenshot(path=str(ROOT / '.runlogs' / f'academic-center-{name}.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), name
    assert not errors, errors
    context.close()
    print(f'{name}: source isolation, exact totals, pagination, modal, search, permissions and health retries passed')


def restricted(browser):
    context, page, seen, flags, errors = setup(browser, {'width': 1440, 'height': 900}, ['sistema-academico'])
    flags['summary_error'] = True
    page.goto(BASE_URL)
    expect(page.locator('.unified-alert-indicator')).to_have_count(0)
    expect(page.get_by_role('region', name='Resumen acad\u00e9mico')).to_contain_text('No disponible')
    assert not any('/pending' in key or '/candidates' in key for key in seen), seen
    expect(page.get_by_role('button', name='Configuraci\u00f3n acad\u00e9mica')).to_be_disabled()
    assert not errors, errors
    context.close()
    print('Restricted access: no unauthorized source queries; failed metrics do not become zero')


if __name__ == '__main__':
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        for name, viewport in [('desktop', {'width': 1500, 'height': 950}), ('mobile', {'width': 390, 'height': 844})]:
            verify(browser, name, viewport)
        restricted(browser)
        browser.close()
