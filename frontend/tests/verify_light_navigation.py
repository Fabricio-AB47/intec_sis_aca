"""Neutral navigation, real permission catalog and mocked institutional APIs."""
import ast
import json

from playwright.sync_api import expect, sync_playwright

from verify_login_navigation import contrast
from verify_runtime_optimizations import BASE_URL, ROOT, mock_context


def catalog_permissions():
    tree = ast.parse((ROOT / 'backend/app/services/screen_access.py').read_text(encoding='utf-8-sig'))
    roots, flows = set(), []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        args = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
        if node.func.id == '_screen' and args:
            roots.add(args[0])
        if node.func.id == '_flow' and len(args) >= 2:
            flows.append((args[0], args[1]))
    return sorted(roots - {parent for parent, _ in flows} | {f'{parent}/{child}' for parent, child in flows})


def visual(locator):
    return locator.evaluate("""el => {
        const s=getComputedStyle(el);
        return [s.backgroundColor,s.color,s.borderTopColor,s.borderRadius,s.boxShadow];
    }""")


def verify(browser, name, viewport):
    context, page, calls, scripts, errors = mock_context(browser, catalog_permissions(), 'dashboard', viewport)
    for pattern in ['**/api/secretaria-general/candidates?*', '**/api/requests/*/pending?*']:
        context.route(pattern, lambda route: route.fulfill(content_type='application/json', body=json.dumps({
            'items': [], 'total': 0, 'page': 1, 'page_size': 10, 'total_pages': 1})))
    page.goto(BASE_URL)
    sidebar = page.get_by_role('complementary', name='Men\u00fa lateral')
    sidebar.wait_for()
    groups = sidebar.locator('.student-nav__group-button')
    assert groups.count() >= 20, groups.count()
    is_mobile = viewport['width'] <= 1180
    if not is_mobile:
        page.mouse.move(viewport['width'] - 1, 10)
        page.wait_for_timeout(250)
        assert visual(sidebar)[0] == 'rgb(255, 255, 255)'
        sizes = groups.evaluate_all("els=>els.map(el=>{const r=el.getBoundingClientRect();return [r.width,r.height]})")
        assert all(width >= 44 and height >= 44 for width, height in sizes), sizes
        assert len(set(tuple(size) for size in sizes)) == 1, sizes
        icon_styles = sidebar.locator('.student-nav__group-icon').evaluate_all("els=>els.map(el=>{const s=getComputedStyle(el);return [s.borderTopWidth,s.backgroundColor]})")
        assert all(style == ['0px', 'rgba(0, 0, 0, 0)'] for style in icon_styles), icon_styles
        for group in groups.all():
            assert group.get_attribute('title') == group.get_attribute('aria-label')
            expect(group.locator('.lucide')).to_have_count(2)
        page.screenshot(path=str(ROOT / '.runlogs' / f'light-menu-collapsed-{name}.png'))
        sidebar.hover()
    else:
        page.get_by_role('button', name='Abrir men\u00fa principal', exact=True).click()
    page.wait_for_timeout(250)
    assert visual(sidebar)[0] == 'rgb(255, 255, 255)'
    assert sidebar.locator('.student-nav__group-copy small, .student-nav__item span').count() == 0
    active = sidebar.locator('.student-nav__group-button--active').first
    contrast(active.locator('strong'))
    for group in groups.all():
        contrast(group.locator('strong'))
    assert visual(active)[:2] == ['rgb(252, 237, 235)', 'rgb(147, 25, 19)']
    active.focus()
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    expect(active).to_be_focused()
    assert active.evaluate('el=>getComputedStyle(el).outlineStyle') == 'solid'
    page.keyboard.press('Enter')
    expect(active).to_have_attribute('aria-expanded', 'true')
    submenu = page.locator('#' + active.get_attribute('aria-controls'))
    expect(submenu).to_be_visible()
    current = submenu.locator('[aria-current=page]').first
    expect(current).to_be_visible()
    contrast(current.locator('strong'))
    before = visual(sidebar), visual(active), visual(current)
    for path in ['/src/App.css', '/src/features/secretaria/SecretariaGeneralView.css', '/src/features/matricula/IngresoDirectoView.css']:
        page.evaluate("async path=>{const css=await import(path+'?raw'); const el=document.createElement('style');el.textContent=css.default;document.head.append(el)}", path)
    assert before == (visual(sidebar), visual(active), visual(current)), 'Lazy modules must not change navigation'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    for label in sidebar.locator('.student-nav__group-copy strong, .student-nav__item strong').all():
        assert label.evaluate('el=>el.scrollWidth<=el.clientWidth+1'), label.inner_text()
    nav = sidebar.get_by_role('navigation', name='Men\u00fa principal')
    nav.evaluate('el=>el.scrollTop=el.scrollHeight')
    expect(groups.last).to_be_in_viewport()
    nav.evaluate('el=>el.scrollTop=0')
    page.screenshot(path=str(ROOT / '.runlogs' / f'light-menu-expanded-{name}.png'))
    current.click()
    page.get_by_role('heading', name='Dashboard Estudiantil', exact=True).wait_for()
    if is_mobile:
        assert not sidebar.evaluate("el=>el.classList.contains('student-sidebar--open')")
        page.get_by_role('button', name='Abrir men\u00fa principal', exact=True).click()
        page.keyboard.press('Escape')
        assert not sidebar.evaluate("el=>el.classList.contains('student-sidebar--open')")
        assert page.evaluate('document.body.style.overflow') != 'hidden'
    else:
        page.locator('.student-main').click(position={'x': viewport['width'] - 400, 'y': 10})
    assert not errors, errors
    context.close()
    print(f'{name}: full menu, neutral colors, equal icon targets, contrast, tooltips, scrolling, keyboard and stable lazy styles passed')


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        for name, viewport in [('desktop', {'width': 1500, 'height': 950}),
                               ('tablet', {'width': 1024, 'height': 768}),
                               ('mobile', {'width': 390, 'height': 844}),
                               ('small-mobile', {'width': 320, 'height': 740})]:
            verify(browser, name, viewport)
        browser.close()
