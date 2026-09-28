"""Login and navigation regression checks, without institutional requests."""
import json
from playwright.sync_api import expect, sync_playwright
from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


CONTRAST = """el => {
    const rgb = s => (s.match(/[\\d.]+/g) || []).slice(0,3).map(Number);
    const light = c => {const a = c.map(v => v/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4); return a[0]*.2126+a[1]*.7152+a[2]*.0722};
    let bg = 'rgb(255,255,255)';
    for(let p=el; p; p=p.parentElement) {const c=getComputedStyle(p).backgroundColor; if(c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') {bg=c; break}}
    const fg=getComputedStyle(el).color, a=light(rgb(fg)), b=light(rgb(bg));
    return {fg,bg,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
}"""


def contrast(locator):
    result = locator.evaluate(CONTRAST)
    assert result['ratio'] >= 4.5, (locator.text_content(), result)


def verify_login(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, [], 'dashboard', viewport, anonymous=True)
    submitted = []
    pending_requests = []
    def reject(route):
        submitted.append(route.request.post_data_json)
        pending_requests.append(route)
    context.route('**/api/auth/login', reject)
    page.goto(BASE_URL)
    page.get_by_label('Usuario o correo', exact=True).fill('prueba@example.test')
    page.locator('input[autocomplete=current-password]').fill('Prueba-no-real')
    page.get_by_role('button', name='Mostrar contraseña', exact=True).click()
    expect(page.locator('input[autocomplete=current-password]')).to_have_attribute('type', 'text')
    expect(page.get_by_role('button', name='Ocultar contraseña', exact=True)).to_have_attribute('aria-pressed', 'true')
    page.get_by_role('button', name='Ocultar contraseña', exact=True).click()
    page.get_by_role('button', name='Iniciar sesión', exact=True).click()
    expect(page.get_by_role('button', name='Validando...', exact=True)).to_be_disabled()
    assert page.locator('.submit-button').evaluate('e => getComputedStyle(e).backgroundImage').startswith('linear-gradient')
    pending_requests[0].fulfill(status=401, content_type='application/json', body=json.dumps({'detail': 'Credenciales incorrectas.'}))
    expect(page.get_by_role('alert')).to_have_text('Credenciales incorrectas.')
    assert submitted == [{'login': 'prueba@example.test', 'password': 'Prueba-no-real'}]
    for selector in ['.login-panel h2', '.login-copy', '.field > span', '.submit-button', '.public-evaluation-button']:
        contrast(page.locator(selector).first)
    assert page.locator('.auth-layout').evaluate('e => getComputedStyle(e).display') == 'grid'
    assert page.locator('.login-panel').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(116, 110, 110)'
    assert page.locator('.showcase-copy h1 span').evaluate('e => getComputedStyle(e).color') == 'rgb(141, 187, 199)'
    assert page.locator('.submit-button').evaluate('e => getComputedStyle(e).backgroundImage').startswith('linear-gradient')
    assert page.locator('.field input').first.evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(232, 240, 254)'
    password = page.locator('input[autocomplete=current-password]').bounding_box()
    toggle = page.get_by_role('button', name='Mostrar contraseña', exact=True).bounding_box()
    assert password and toggle and abs(password['y'] - toggle['y']) < 1 and password['x'] + password['width'] <= toggle['x']
    assert password['height'] == toggle['height'] == 48
    if name == 'reference':
        styles = "el => {const s=getComputedStyle(el); return [s.color,s.backgroundColor,s.backgroundImage,s.fontSize,s.borderRadius]}"
        controls = ['.login-panel', '.submit-button', '.field input', '.showcase-copy h1 span']
        before = [page.locator(selector).first.evaluate(styles) for selector in controls]
        for path in ['/src/App.css', '/src/features/secretaria/SecretariaGeneralView.css', '/src/features/notifications/UnifiedAcademicAlerts.css']:
            page.evaluate("async path => {const css=await import(path+'?raw'); const el=document.createElement('style');el.textContent=css.default;document.head.append(el)}", path)
        assert before == [page.locator(selector).first.evaluate(styles) for selector in controls], 'Lazy styles must not change login'
        showcase = page.locator('.showcase-panel').bounding_box()
        panel = page.locator('.login-panel').bounding_box()
        assert showcase and panel and abs(showcase['width'] / viewport['width'] - .6) < .01
        assert abs(showcase['x'] + showcase['width'] - panel['x']) < 1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(ROOT / '.runlogs' / f'login-restored-{name}.png'), full_page=True)
    assert not errors, errors
    context.close()


def verify_menu(browser, name, viewport, role):
    context, page, _, _, errors = mock_context(browser, ['dashboard', 'moodle/status', 'titulacion-proceso'], 'dashboard', viewport)
    context.route('**/api/auth/me', lambda route: route.fulfill(content_type='application/json', body=json.dumps({
        'login': 'prueba@example.test', 'nombres': 'Usuario de prueba', 'rol': role, 'perfiles': []})))
    context.route('**/api/auth/screen-access*', lambda route: route.fulfill(content_type='application/json', body=json.dumps({
        'current_role': role, 'screens': [], 'roles': [{'value': role, 'pages': ['dashboard', 'moodle/status', 'titulacion-proceso'], 'default_pages': [], 'configured': True, 'protected': False}]})))
    page.goto(BASE_URL)
    sidebar = page.locator('.student-sidebar')
    sidebar.wait_for()
    if viewport['width'] < 768:
        page.get_by_role('button', name='Abrir menú principal', exact=True).click()
    else:
        sidebar.hover()
    selected = page.locator('.student-nav__group-button--active').first
    selected.wait_for()
    for state in ['normal', 'hover', 'focus']:
        if state == 'hover': selected.hover()
        if state == 'focus': selected.focus()
        page.wait_for_timeout(200)
        contrast(selected.locator('strong'))
        contrast(selected.locator('.student-nav__group-meta'))
    items = page.locator('.student-nav__item--active')
    if items.count():
        expect(items.first).to_have_attribute('aria-current', 'page')
        contrast(items.first.locator('strong'))
    for button in page.locator('.student-nav__group-button').all():
        contrast(button.locator('strong'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(ROOT / '.runlogs' / f'menu-readable-{role}-{name}.png'), full_page=True)
    context.close()


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        for name, viewport in [('desktop', {'width': 1500, 'height': 950}), ('mobile', {'width': 390, 'height': 844})]:
            verify_login(browser, name, viewport)
            for role in ['ADMINISTRADOR', 'DOCENTE', 'ESTUDIANTE']:
                verify_menu(browser, name, viewport, role)
            print(f'{name}: login, credentials preserved and three navigation profiles passed')
        for name, viewport in [('reference', {'width': 1859, 'height': 895}), ('small-mobile', {'width': 320, 'height': 740})]:
            verify_login(browser, name, viewport)
            print(f'{name}: reference login, loading/error states and aligned controls passed')
        browser.close()
