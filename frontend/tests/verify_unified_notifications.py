"""Unified notification banner/cards. All APIs are simulated; no data writes."""

from collections import Counter
import json
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from verify_academic_work_center import setup, PERMISSIONS
from verify_runtime_optimizations import BASE_URL, ROOT


def evaluation_data():
    return {'periodo': '1050', 'periodo_detalle': 'C1-2026', 'flow': 'all',
            'summary': [{'pending': 1222}], 'teacher_progress': [], 'total': 1222,
            'items': [{'flow': 'student', 'flow_label': 'Evaluaci\u00f3n al docente', 'evaluator_code': 1,
                       'evaluator_name': 'RESPONSABLE DE PRUEBA', 'evaluator_cedula': '001',
                       'periodo': '1050', 'periodo_detalle': 'C1-2026', 'course': {
                           'key': '1', 'codigo_materia': 1, 'codigo_materia_interno': 'TEST-01',
                           'materia': 'PROGRAMACION', 'carrera': 'Software', 'paralelo': 'A1', 'docente': 'DOCENTE DE PRUEBA'}}]}


def verify(browser, name, viewport):
    permissions = [*PERMISSIONS, 'moodle/alerts', 'evaluacion-docente-avance']
    context, page, seen, flags, errors = setup(browser, viewport, permissions)
    academic_calls = Counter()
    flags['evaluation_error'] = False

    def api(route):
        path = urlparse(route.request.url).path
        if path not in ['/api/evaluacion-docente/admin/periodos', '/api/evaluacion-docente/admin/pendientes', '/api/moodle/grades/alerts']:
            route.fallback()
            return
        assert route.request.method == 'GET'
        academic_calls[path] += 1
        status = 200
        if path.endswith('/periodos'):
            body = {'items': [{'codigo_periodo': '1050', 'detalle_periodo': 'C1-2026'}], 'total': 1}
        elif path.endswith('/pendientes'):
            status = 503 if flags['evaluation_error'] else 200
            body = {'detail': 'Fuente no disponible'} if flags['evaluation_error'] else evaluation_data()
        else:
            body = {'summary': {'total': 708}, 'items': [{
                'id': '1', 'kind': 'SIN_CALIFICAR', 'student': 'ESTUDIANTE MOODLE', 'identity': '002',
                'matter': 'MATEMATICAS', 'period': 'C1-2026', 'period_code': 1050, 'course': 'MAT-01',
                'missing_components': ['P1Examen'], 'missing_sources': [], 'message': '', 'status': 'PENDIENTE',
            }]}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

    context.route('**/api/**', api)
    page.clock.install()
    page.goto(BASE_URL)
    banner = page.locator('.unified-alert-indicator')
    expect(banner).to_contain_text('2.152 pendientes')
    expect(banner).to_have_count(1)
    assert seen['/api/requests/career-change/pending'] == 1, ('No second queue may load duplicate data', dict(seen), dict(academic_calls))
    assert not page.locator('.academic-pending, .academic-pending-dialog').count()
    banner.screenshot(path=str(ROOT / '.runlogs' / f'unified-banner-{name}.png'))
    banner.click()
    dialog = page.get_by_role('dialog', name='Pendientes acad\u00e9micos')
    expect(dialog).to_be_visible()
    cards = dialog.locator('.unified-alert-source')
    expect(cards).to_have_count(5)
    assert page.locator('dialog[open]').count() == 1
    expect(cards.nth(4)).to_contain_text('No disponible')
    geometry = cards.evaluate_all("els => els.map(el => { const r=el.getBoundingClientRect(); return {width:r.width,height:r.height,overflow:el.scrollHeight>el.clientHeight+1}; })")
    assert max(item['width'] for item in geometry) - min(item['width'] for item in geometry) < 1, geometry
    assert all(item['height'] == 176 and not item['overflow'] for item in geometry), geometry
    content = cards.evaluate_all("""els => els.map(el => {
        const card=el.getBoundingClientRect();
        const rows=Array.from(el.children, child=>child.getBoundingClientRect());
        return { separated: rows.every((row,i)=>!i || rows[i-1].bottom<=row.top),
                 contained: rows.every(row=>row.left>=card.left && row.right<=card.right && row.bottom<=card.bottom) };
    })""")
    assert all(item['separated'] and item['contained'] for item in content), content
    page.screenshot(path=str(ROOT / '.runlogs' / f'unified-sources-{name}.png'))
    expect(dialog).to_contain_text('RESPONSABLE DE PRUEBA')
    dialog.get_by_role('button', name='Moodle y calificaciones', exact=True).click()
    expect(dialog).to_contain_text('ESTUDIANTE MOODLE')
    expect(dialog).not_to_contain_text('RESPONSABLE DE PRUEBA')
    dialog.get_by_role('button', name='Cambio de carrera', exact=True).click()
    expect(dialog).to_contain_text('221 solicitudes')
    dialog.get_by_role('button', name='P\u00e1gina siguiente').click()
    expect(dialog).to_contain_text('P\u00e1gina 2 de 23')
    flags['modality_error'] = False
    flags['evaluation_error'] = True
    dialog.get_by_role('button', name='Actualizar', exact=True).click()
    expect(cards.nth(0)).to_contain_text('No disponible')
    expect(cards.nth(4)).not_to_contain_text('No disponible')
    expect(dialog).to_contain_text('P\u00e1gina 2 de 23')
    expect(dialog.get_by_role('button', name='Cambio de carrera', exact=True)).to_have_attribute('aria-pressed', 'true')
    expect(banner).to_contain_text('930 pendientes')
    dialog.get_by_role('button', name='Documentaci\u00f3n de Secretar\u00eda', exact=True).click()
    expect(dialog).to_contain_text('ESTUDIANTE DOCUMENTAL')
    expect(dialog).to_contain_text('3 documentos faltantes')
    expect(page.get_by_role('dialog')).to_have_count(1)
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    assert page.evaluate('document.body.style.overflow') != 'hidden'
    expect(banner).to_be_focused()
    def notification_calls():
        return ({path: count for path, count in seen.items() if path.endswith(('/pending', '/candidates'))}, dict(academic_calls))

    before = notification_calls()
    page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true,value:'hidden'})")
    page.clock.run_for(300_000)
    page.wait_for_timeout(50)
    assert before == notification_calls(), ('Hidden notifications must not poll', before, notification_calls())
    page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true,value:'visible'}); document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(300)
    assert seen['/api/requests/career-change/pending'] == before[0]['/api/requests/career-change/pending'] + 1
    assert not errors, errors
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    context.close()
    print(f'{name}: one banner, five equal cards, source details, retry, preserved page, focus and hidden polling passed')


def daily_reminder(browser, role):
    context, page, seen, flags, errors = setup(browser, {'width': 1200, 'height': 900}, ['sistema-academico'])
    def api(route):
        assert route.request.method == 'GET'
        route.fulfill(content_type='application/json', body=json.dumps({'total_pending': 1, 'total_completed': 0,
            'items': [{'flow': 'auto_docente' if role == 'DOCENTE' else 'student', 'label': 'Evaluacion',
                       'pending_courses': [{'key': '1', 'materia': 'PRUEBA', 'codigo_periodo': 1050, 'codigo_materia': 1}]}]}))
    context.route('**/api/evaluacion-docente/alertas/pendientes', api)
    page.goto(BASE_URL)
    page.locator('.academic-work-center').wait_for()
    page.evaluate("""async role => {
        const loaded = file => performance.getEntriesByType('resource').find(e => new URL(e.name).pathname === '/node_modules/.vite/deps/' + file).name;
        const {default:React}=await import(loaded('react.js'));
        const {default:{createRoot}}=await import(loaded('react-dom_client.js'));
        const {UnifiedAcademicAlertsIndicator}=await import('/src/features/notifications/UnifiedAcademicAlertsIndicator.tsx');
        const el=document.createElement('div'); el.className='app'; document.body.append(el);
        const root=createRoot(el); window.reminderRoot=root;
        const props={role,cedula:'test-reminder',canViewMoodle:false,canViewTeacherEvaluation:true,permissions:[],
            onOpenMoodle(){},onOpenTeacherEvaluation(){},onOpenSecretaria(){},onOpenCareerRequests(){},onOpenModalityRequests(){}};
        window.renderReminder=key=>root.render(React.createElement(UnifiedAcademicAlertsIndicator,{...props,key}));
        window.renderReminder('first');
    }""", role)
    dialog = page.get_by_role('dialog', name='Pendientes acad\u00e9micos')
    expect(dialog).to_be_visible()
    expect(dialog.locator('.unified-alert-source')).to_have_count(1)
    page.keyboard.press('Escape')
    page.evaluate("window.renderReminder('same-day')")
    page.wait_for_timeout(250)
    expect(dialog).not_to_be_visible()
    page.locator('.unified-alert-indicator').click()
    expect(dialog).to_be_visible()
    page.keyboard.press('Escape')
    page.evaluate("role => { localStorage.removeItem('intec:recordatorio-pendientes:' + role + ':test-reminder'); window.renderReminder('next-day'); }", role)
    expect(dialog).to_be_visible()
    page.evaluate('window.reminderRoot.unmount()')
    assert not errors, errors
    context.close()
    print(f'{role}: personal daily reminder preserved; no administrative sources exposed')


def cleared_pending(browser):
    context, page, seen, flags, errors = setup(browser, {'width': 1200, 'height': 900})
    pending = {'total': 1}

    def api(route):
        path = urlparse(route.request.url).path
        if not path.endswith(('/pending', '/candidates')):
            route.fallback()
            return
        assert route.request.method == 'GET'
        route.fulfill(content_type='application/json', body=json.dumps({
            'total': pending['total'] if path.endswith('/candidates') else 0,
            'page': 1, 'page_size': 10, 'total_pages': 1, 'items': []}))

    context.route('**/api/**', api)
    page.goto(BASE_URL)
    banner = page.locator('.unified-alert-indicator')
    expect(banner).to_contain_text('1 pendiente')
    banner.click()
    dialog = page.get_by_role('dialog', name='Pendientes acad\u00e9micos')
    pending['total'] = 0
    dialog.get_by_role('button', name='Actualizar', exact=True).click()
    expect(banner).to_contain_text('Sin pendientes acad\u00e9micos')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text('No hay pendientes con estos criterios.')
    page.keyboard.press('Escape')
    expect(dialog).to_have_count(0)
    expect(banner).to_have_count(0)
    assert page.evaluate('document.body.style.overflow') != 'hidden'
    assert not errors, errors
    context.close()
    print('Resolved pending: refreshed zero remains reviewable; closing hides the cleared banner')


if __name__ == '__main__':
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        for name, viewport in [('desktop', {'width': 1500, 'height': 950}), ('mobile', {'width': 390, 'height': 844}), ('narrow-grid', {'width': 381, 'height': 844}), ('small-mobile', {'width': 320, 'height': 740})]:
            verify(browser, name, viewport)
        for role in ['DOCENTE', 'ESTUDIANTE']:
            daily_reminder(browser, role)
        cleared_pending(browser)
        browser.close()
