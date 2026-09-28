"""Offline regression for dashboard invalidation and out-of-order responses."""
import json

from playwright.sync_api import expect
from verify_runtime_optimizations import BASE_URL, mock_context


def verify(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ['dashboard'], 'dashboard', viewport)
    pending = []
    reads = []

    def payload(active):
        return {'dashboard_type': 'matricula', 'trend': [], 'active_by_type': [],
                'states': [{'estado_codigo': 'A', 'estado_nombre': 'Activo', 'total_estudiantes': active},
                           {'estado_codigo': 'R', 'estado_nombre': 'Retirado', 'total_estudiantes': 9 - active}],
                'total_estudiantes': 9, 'consultado_en': str(len(reads))}

    def dashboard(route):
        assert route.request.method == 'GET'
        reads.append(route.request.url)
        if len(reads) == 2:
            pending.append(route)
        else:
            route.fulfill(content_type='application/json', body=json.dumps(payload(8 if len(reads) == 1 else 3)))

    context.route('**/api/students/dashboard-matricula', dashboard)
    page.clock.install()
    page.goto(BASE_URL)
    # Match the exact metric label, not the Regular + Homologation card.
    active_value = page.locator('.dashboard-metric-tile').filter(has=page.get_by_text('Activos', exact=True)).locator('strong')
    expect(active_value).to_have_text('8')
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.wait_for_timeout(200)
    assert len(pending) == 1
    page.evaluate("window.dispatchEvent(new Event('student-state:changed'))")
    expect(active_value).to_have_text('3')
    pending[0].fulfill(content_type='application/json', body=json.dumps(payload(8)))
    page.wait_for_timeout(150)
    expect(active_value).to_have_text('3')
    assert len(reads) == 3
    with page.expect_response(lambda response: response.url.endswith('/api/students/dashboard-matricula')):
        page.evaluate("window.dispatchEvent(new StorageEvent('storage', {key:'student-state:changed', newValue:'123'}))")
    expect(active_value).to_have_text('3')
    assert len(reads) == 4
    assert not errors, errors
    context.close()
    print(f'{name}: dashboard refresh, stale response protection and cross-tab notification passed')
