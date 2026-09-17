"""Read/load regression checks against Vite; every API request is mocked.

Run from the repository root with a running frontend:
    .venv/Scripts/python.exe frontend/tests/verify_runtime_optimizations.py
"""

from collections import Counter
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("FRONTEND_TEST_URL", "http://127.0.0.1:5174")
SECTIONS = ["status", "courses", "course-cloning", "manual-enrollment", "resources",
            "evaluation-dates", "grades", "academic-enrollment", "alerts", "users"]
EMPTY_COURSES = {
    "items": [],
    "pagination": {"page": 1, "page_size": 50, "total_items": 0, "total_pages": 0,
                   "has_previous": False, "has_next": False},
    "source": {"cached": False, "fetched_at": "2026-09-17T12:00:00Z", "moodle_function": "mock"},
}
EMPTY_ALERTS = {
    "scope": "INSTITUCIONAL", "role": "ADMINISTRADOR", "generated_at": "2026-09-17T12:00:00Z",
    "cached": False, "summary": {}, "validation": {}, "items": [], "errors": [],
}


def mock_context(browser, permissions, active_page, viewport, anonymous=False):
    context = browser.new_context(viewport=viewport)
    calls = Counter()
    scripts = set()
    errors = []

    def handler(route):
        path = urlparse(route.request.url).path
        calls[path] += 1
        status = 200
        if path == "/api/auth/me":
            status = 401 if anonymous else 200
            body = {"login": "admin@example.test", "nombres": "Administrador", "id_usuario": 95,
                    "rol": "ADMINISTRADOR", "perfiles": []}
        elif path == "/api/auth/screen-access":
            body = {"current_role": "ADMINISTRADOR", "screens": [], "roles": [
                {"value": "ADMINISTRADOR", "pages": permissions, "default_pages": [],
                 "configured": True, "protected": False}]}
        elif path == "/api/students/dashboard-matricula":
            body = {"dashboard_type": "matricula", "trend": [], "states": [], "active_by_type": [],
                    "total_estudiantes": 0, "consultado_en": "2026-09-17T12:00:00Z"}
        elif path == "/api/moodle/status":
            body = {"enabled": True, "configured": True, "reachable": True, "site_name": "Moodle",
                    "required_functions": [], "missing_required_functions": [], "functions_count": 0}
        elif path in ("/api/moodle/courses", "/api/moodle/users"):
            body = EMPTY_COURSES
        elif path == "/api/moodle/course-cloning/catalog":
            body = {"current_year": 2026, "capability": {"enabled": True, "reason": "",
                    "required_functions": [], "missing_functions": []}, "catalog_ready": True,
                    "catalog_reason": "", "template_root": None, "offer_root": None, "templates": [],
                    "summary": {"templates": 0, "regular": 0, "homologation": 0, "ignored_courses": 0}}
        elif path == "/api/moodle/manual-enrollment/catalog":
            body = {"capability": {"enabled": True, "reason": ""}, "roles": [], "courses": [],
                    "limits": {"names": 100, "candidates_per_name": 10}}
        elif path == "/api/moodle/academic-enrollment/catalog":
            body = {"periods": [], "jornadas": [], "rules": {"max_courses": 25,
                    "parallel_source": "name", "student_roles": [], "teacher_roles": []}}
        elif path == "/api/moodle/grades/catalog":
            body = {"enabled": True, "courses": [], "periods": []}
        elif path == "/api/moodle/grades/alerts":
            body = EMPTY_ALERTS
        elif path.endswith("/historial") or path == "/api/moodle/grades/history":
            body = {"items": [], "total": 0}
        elif path == "/api/evaluacion-docente/admin/periodos":
            body = {"items": [], "total": 0}
        else:
            body = {}
        assert route.request.method == "GET", "UI checks must not write: " + path
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    context.route("**/api/**", handler)
    context.add_init_script(f"localStorage.setItem('reporteria.active-page', {json.dumps(active_page)})")
    page = context.new_page()
    page.on("request", lambda request: scripts.add(urlparse(request.url).path)
            if request.resource_type == "script" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, calls, scripts, errors


def verify_dashboard(browser, name, viewport):
    context, page, calls, scripts, errors = mock_context(browser, ["dashboard"], "dashboard", viewport)
    page.clock.install()
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Dashboard Estudiantil", exact=True).wait_for()
    page.wait_for_timeout(1200)
    path = "/api/students/dashboard-matricula"
    assert calls[path] == 1, (name, "Dashboard reload loop", calls[path])
    assert not any("TeacherEvaluationView.tsx" in script or "MoodleView.tsx" in script for script in scripts)
    page.clock.run_for(30_000)
    page.wait_for_timeout(150)
    assert calls[path] == 2, (name, "30-second refresh", calls[path])
    page.evaluate("Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })")
    page.clock.run_for(30_000)
    page.wait_for_timeout(150)
    assert calls[path] == 2, (name, "Hidden polling", calls[path])
    page.evaluate("""() => {
        Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
        document.dispatchEvent(new Event('visibilitychange'));
        for (let i = 0; i < 5; i++) window.dispatchEvent(new Event('focus'));
    }""")
    page.wait_for_timeout(350)
    assert calls[path] == 3, (name, "Overlapping focus/visibility requests", calls[path])
    assert not errors, errors
    print(f"{name}: one dashboard load, 30-second refresh, hidden pause and concurrent focus guard passed")
    context.close()


def verify_moodle(browser, name, viewport):
    permissions = [f"moodle/{section}" for section in SECTIONS]
    context, page, calls, scripts, errors = mock_context(browser, permissions, "moodle", viewport)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Estado de la integraci\u00f3n", exact=True).wait_for()
    page.get_by_role("heading", name="Moodle", exact=True).hover()
    panels = ["MoodleCourseCloningPanel", "MoodleManualEnrollmentPanel", "MoodleResourcesPanel",
              "MoodleEvaluationDatesPanel", "MoodleGradeSyncPanel", "MoodleAcademicEnrollmentPanel",
              "MoodleGradeAlertsPanel"]
    assert not any(any(panel in script for panel in panels) for script in scripts), scripts
    tabs = page.get_by_role("navigation", name="Secciones de Moodle", exact=True)
    tabs.get_by_role("button", name="Cursos", exact=True).click()
    page.get_by_role("heading", name="Cursos de Moodle", exact=True).wait_for()
    course_filter = page.get_by_placeholder("Curso, nombre corto, c\u00f3digo o categor\u00eda", exact=True)
    course_filter.fill("R30")
    sections = [
        ("Copiar cursos", "Copiar cursos desde plantillas base", panels[0]),
        ("Matricular usuarios", "Asignaci\u00f3n masiva por nombres", panels[1]),
        ("Recursos por curso", "Recursos por curso", panels[2]),
        ("Fechas de evaluaciones", "Fechas comunes de Simuladores y Evaluaciones", panels[3]),
        ("Migraci\u00f3n de notas", "Notas desde Moodle", panels[4]),
        ("Moodle - Sistema Acad\u00e9mico", "Matr\u00edcula acad\u00e9mica masiva", panels[5]),
        ("Alertas de calificaci\u00f3n", "Alertas de calificaci\u00f3n", panels[6]),
    ]
    opened = set()
    for label, heading, panel in sections:
        tabs.get_by_role("button", name=label, exact=True).click()
        page.get_by_role("heading", name=heading, exact=True).wait_for()
        page.wait_for_timeout(250)
        opened.add(panel)
        loaded = {item for item in panels if any(item in script for script in scripts)}
        assert loaded == opened, (name, panel, loaded, opened)
    tabs.get_by_role("button", name="Cursos", exact=True).click()
    expect(course_filter).to_have_value("R30")
    page.screenshot(path=str(ROOT / ".runlogs" / f"optimization-moodle-{name}.png"), full_page=True)
    assert not errors, errors
    print(f"{name}: all seven Moodle panels load on demand; shell, navigation and course filters preserved")
    context.close()


def verify_historical_progress(browser, name, viewport):
    context, page, _, _, errors = mock_context(browser, ["evaluacion-docente-historicas"], "evaluacion-docente-historicas", viewport)
    offsets = []
    api_path = "/api/evaluacion-docente/admin/autoevaluaciones-historicas"
    teacher = {"codigo_doc": 12, "docente": "DOCENTE DE PRUEBA", "cedula_doc": "0805755739", "periods": [101]}
    period = {"codigo_periodo": 101, "detalle_periodo": "C1-2023-PB", "year": 2023}
    questions = [{"id_pregunta": code, "detalle_preg": f"Pregunta {code}", "puntaje_min": 1, "puntaje_max": 5}
                 for code in (1, 2)]
    course = {"codigo_periodo": 101, "detalle_periodo": "C1-2023-PB", "codigo_materia": 31,
              "codigo_docente_eval": 12, "docente": teacher["docente"], "cedula_docente": teacher["cedula_doc"],
              "materia": "Materia de prueba", "carrera": "Carrera de prueba", "paralelo": "PB1"}
    items = [{"course": {**course, "key": str(index)}, "status": "PENDIENTE" if index < 200 else "EXISTENTE",
              "score_10": 9, "answers": [{"id_pregunta": 1, "puntaje": 4}, {"id_pregunta": 2, "puntaje": 5}]}
             for index in range(201)]

    def handler(route):
        path = urlparse(route.request.url).path
        status = 200
        if path == api_path + "/catalogo":
            body = {"periods": [period], "teachers": [teacher], "max_applications": None, "max_teachers": None}
        elif path == api_path + "/vista-previa":
            assert route.request.post_data_json == {"periods": [101], "teachers": [12]}
            body = {"preview_token": "preview-0", "pending": 200, "existing": 1, "expires_in_minutes": 30,
                    "instrument": {"Id_Instrumento": 7, "Nombre": "Autoevaluacion"}, "questions": questions, "items": items}
        elif path == api_path + "/generar":
            payload = route.request.post_data_json
            offset = payload["offset"]
            assert payload["confirmed"] is True and payload["reason"] == "Prueba administrativa simulada"
            assert payload["preview_token"] == f"preview-{offset}"
            offsets.append(offset)
            if offsets == [0, 100]:
                status = 500
                body = {"detail": "Fallo simulado; reintente el bloque pendiente."}
            else:
                end = min(offset + 100, 201)
                body = {"batch_id": "mock-optimization-batch", "created": end - offset if offset < 200 else 0,
                        "skipped": 1 if offset == 200 else 0, "processed": end, "total": 201,
                        "next_offset": end if end < 201 else None,
                        "preview_token": f"preview-{end}" if end < 201 else None, "message": "Mock only"}
        elif path == api_path + "/historial":
            body = {"items": [], "total": 0}
        else:
            raise AssertionError("Unexpected historical endpoint: " + path)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    context.route("**/api/evaluacion-docente/admin/autoevaluaciones-historicas/**", handler)
    page.goto(BASE_URL)
    page.get_by_role("heading", name="Autoevaluaciones hist\u00f3ricas", exact=True).wait_for()
    selectors = page.locator(".teacher-evaluation-history__selector")
    selectors.nth(0).locator("input[type=checkbox]").first.check()
    selectors.nth(1).locator("input[type=checkbox]").first.check()
    page.get_by_role("button", name="Generar vista previa", exact=True).click()
    page.get_by_label("Motivo administrativo", exact=True).fill("Prueba administrativa simulada")
    page.locator(".teacher-evaluation-history__acknowledgment input").check()
    page.get_by_role("button", name="Confirmar y guardar", exact=True).click()
    dialog = page.get_by_role("dialog", name="Avance de generaci\u00f3n", exact=True)
    dialog.get_by_role("alert").filter(has_text="Fallo simulado").wait_for()
    assert "Procesadas 100 / 201" in dialog.inner_text() and offsets == [0, 100]
    dialog.get_by_role("button", name="Cerrar", exact=True).click()
    page.get_by_role("button", name="Ver avance", exact=True).click()
    assert "Procesadas 100 / 201" in dialog.inner_text() and offsets == [0, 100]
    dialog.get_by_role("button", name="Reintentar pendientes", exact=True).click()
    summary = dialog.locator(".teacher-evaluation-history__success-summary")
    expect(summary).to_contain_text("200 autoevaluaciones generadas correctamente.")
    assert "Formularios procesados: 201 de 201." in summary.inner_text()
    assert "1 autoevaluaci\u00f3n existente conservada sin modificaciones." in summary.inner_text()
    assert offsets == [0, 100, 100, 200], offsets
    summary_text = summary.inner_text()
    assert summary.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    page.screenshot(path=str(ROOT / ".runlogs" / f"optimization-progress-{name}.png"), full_page=True)
    dialog.get_by_role("button", name="Cerrar", exact=True).click()
    page.get_by_role("button", name="Ver avance", exact=True).click()
    assert summary.inner_text() == summary_text and offsets == [0, 100, 100, 200]
    dialog.get_by_role("button", name="Ver historial", exact=True).click()
    expect(page.get_by_role("tab", name="Historial", exact=True)).to_have_attribute("aria-selected", "true")
    assert not errors, errors
    print(f"{name}: 201 forms, preserved checkpoint, renewed tokens, no duplicated completed blocks and persistent progress dialog passed")
    context.close()


API_CHECKS = r"""async () => {
    const api = await import('/src/lib/api.ts');
    const originalFetch = window.fetch;
    const calls = [];
    const held = [];
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const response = (value, status = 200) => new Response(JSON.stringify(value), {
        status, headers: { 'Content-Type': 'application/json' }
    });
    const finish = (value = {}, status = 200) => {
        const resolve = held.shift();
        check(Boolean(resolve), 'No pending mocked transport');
        resolve(response(value, status));
    };
    window.fetch = (url, options) => {
        calls.push({ url: String(url), options });
        if (String(url).includes('/api/auth/')) return Promise.resolve(response({ rol: 'ADMINISTRADOR' }));
        return new Promise((resolve) => held.push(resolve));
    };
    try {
        api.invalidateTeacherEvaluationAlerts();
        const reads = [
            () => api.fetchHistoricalSelfEvaluationCatalog(),
            () => api.fetchHistoricalSelfEvaluationHistory(),
            () => api.fetchTeacherEvaluationAdminPeriods(),
            () => api.fetchTeacherEvaluationAdminPending('101'),
            () => api.fetchTeacherEvaluationPendingAlerts(),
        ];
        for (const read of reads) {
            const before = calls.length;
            const pair = [read(), read()];
            check(calls.length === before + 1, 'Concurrent identical GETs not shared');
            const options = calls.at(-1).options;
            check(options.credentials === 'include' && options.cache === 'no-store', 'Read/auth policy changed');
            finish({ items: [], marker: 'fresh' });
            await Promise.all(pair);
            const fresh = read();
            check(calls.length === before + 2, 'Settled data incorrectly cached');
            finish({ items: [], marker: 'next' });
            await fresh;
        }
        let before = calls.length;
        const periods = [api.fetchTeacherEvaluationAdminPending('101'), api.fetchTeacherEvaluationAdminPending('102')];
        check(calls.length === before + 2, 'Different periods incorrectly combined');
        finish(); finish(); await Promise.all(periods);

        before = calls.length;
        const failures = [api.fetchHistoricalSelfEvaluationCatalog(), api.fetchHistoricalSelfEvaluationCatalog()];
        const outcomes = Promise.allSettled(failures);
        finish({ detail: 'Simulated failure' }, 500);
        check((await outcomes).every((item) => item.status === 'rejected' && item.reason.status === 500), 'API errors changed');
        const retry = api.fetchHistoricalSelfEvaluationCatalog();
        check(calls.length === before + 2, 'Failed reads not released');
        finish(); await retry;

        for (const clear of [() => api.invalidateTeacherEvaluationAlerts(), () => api.selectProfileRequest('ADMINISTRADOR'),
                             () => api.loginRequest('admin@example.test', 'mock'), () => api.logoutRequest()]) {
            const old = api.fetchHistoricalSelfEvaluationCatalog();
            await clear();
            const current = api.fetchHistoricalSelfEvaluationCatalog();
            finish({ marker: 'old' });
            check((await old).marker === 'old', 'Existing caller changed');
            const join = api.fetchHistoricalSelfEvaluationCatalog();
            check(current === join, 'Old completion released a newer session request');
            finish({ marker: 'new' });
            check((await current).marker === 'new' && (await join).marker === 'new', 'Auth/invalidation isolation failed');
        }

        before = calls.length;
        const writes = [api.generateHistoricalSelfEvaluations('mock', 'Simulated reason', 0),
                        api.generateHistoricalSelfEvaluations('mock', 'Simulated reason', 0)];
        check(calls.length === before + 2 && calls.slice(before).every((call) => call.options.method === 'POST'),
              'Writes were incorrectly shared or changed');
        finish({ created: 1 }); finish({ created: 1 }); await Promise.all(writes);
        return { reads: reads.length, checks: 'sharing, fresh data, errors, query isolation, auth isolation and unchanged writes' };
    } finally {
        window.fetch = originalFetch;
        api.invalidateTeacherEvaluationAlerts();
    }
}"""


DASHBOARD_SESSION_CHECKS = r"""async () => {
    const loadedModule = (file) => {
        const entry = performance.getEntriesByType('resource').find((item) => {
            const url = new URL(item.name);
            return url.pathname === '/node_modules/.vite/deps/' + file && url.searchParams.has('v');
        });
        if (!entry) throw new Error('Missing loaded Vite module: ' + file);
        return entry.name;
    };
    const { default: React } = await import(loadedModule('react.js'));
    const { default: { createRoot } } = await import(loadedModule('react-dom_client.js'));
    const { useReporteriaApp } = await import('/src/hooks/useReporteriaApp.ts');
    const api = await import('/src/lib/api.ts');
    const originalFetch = window.fetch;
    const held = [];
    let current;
    let role = 'ADMINISTRADOR';
    let dashboardReads = 0;
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const response = (value) => new Response(JSON.stringify(value), {
        status: 200, headers: { 'Content-Type': 'application/json' }
    });
    const session = () => ({ login: 'admin@example.test', id_usuario: 95, nombres: 'Administrador', rol: role, perfiles: [] });
    window.fetch = (url, options) => {
        const path = new URL(String(url), window.location.href).pathname;
        if (path === '/api/auth/select-profile') role = JSON.parse(options.body).rol;
        if (path === '/api/auth/me' || path === '/api/auth/select-profile') return Promise.resolve(response(session()));
        if (path === '/api/auth/screen-access') return Promise.resolve(response({ roles: [
            { value: role, pages: ['dashboard'], default_pages: [], configured: true, protected: false }
        ] }));
        if (path === '/api/students/dashboard-matricula') {
            dashboardReads++;
            return new Promise((resolve) => held.push(resolve));
        }
        return Promise.resolve(response({}));
    };
    const waitUntil = async (condition) => {
        for (let attempt = 0; attempt < 150; attempt++) {
            if (condition()) return;
            await new Promise((resolve) => setTimeout(resolve, 20));
        }
        throw new Error('Hook/session transition timed out: ' + JSON.stringify({
            held: held.length, dashboardReads, role: current?.session?.rol,
            page: current?.activePage, error: current?.error
        }));
    };
    const element = document.createElement('div');
    document.body.append(element);
    const root = createRoot(element);
    function Capture() {
        const app = useReporteriaApp();
        React.useEffect(() => { current = app; });
        return null;
    }
    try {
        await api.selectProfileRequest('ADMINISTRADOR');
        root.render(React.createElement(Capture));
        await waitUntil(() => held.length === 1 && current?.session?.rol === 'ADMINISTRADOR');
        const first = current.loadDashboardMatricula();
        const join = current.loadDashboardMatricula();
        check(first === join && dashboardReads === 1, 'Concurrent dashboard callers must await the same load');
        await current.selectAccessProfile('ADMISIONES');
        await waitUntil(() => held.length === 2 && current?.session?.rol === 'ADMISIONES');
        held[0](response({ marker: 'old', dashboard_type: 'matricula', total_estudiantes: 111 }));
        await first;
        check(current.dashboardMatricula?.marker !== 'old', 'Old-profile response populated current dashboard');
        check(current.dashboardMatriculaLoading, 'Old completion cleared a new profile loading state');
        held[1](response({ marker: 'new', dashboard_type: 'admisiones', total_estudiantes: 222 }));
        await waitUntil(() => current.dashboardMatricula?.marker === 'new' && !current.dashboardMatriculaLoading);
        check(dashboardReads === 2, 'Dashboard loop or skipped fresh profile load');
        return 'awaitable shared load and stale-profile response/loading isolation';
    } finally {
        root.unmount();
        element.remove();
        await api.logoutRequest();
        window.fetch = originalFetch;
    }
}"""


def verify_api_and_public_form(browser):
    context, page, _, scripts, errors = mock_context(browser, [], "dashboard", {"width": 1280, "height": 900}, anonymous=True)
    page.goto(BASE_URL + "/?public=evaluacion-docente")
    page.get_by_role("heading", name="Evaluaci\u00f3n docente", exact=True).wait_for()
    assert any("TeacherEvaluationView.tsx" in script for script in scripts)
    print("Public evaluation form: lazy module and anonymous access passed")
    print("API:", page.evaluate(API_CHECKS))
    try:
        print("Dashboard session:", page.evaluate(DASHBOARD_SESSION_CHECKS))
    except Exception as error:
        raise AssertionError(f"{error}; browser errors: {errors}") from error
    assert not errors, errors
    context.close()


if __name__ == "__main__":
    (ROOT / ".runlogs").mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, viewport in [("desktop", {"width": 1600, "height": 1000}),
                               ("mobile", {"width": 390, "height": 844}),
                               ("mobile-small", {"width": 320, "height": 740})]:
            verify_dashboard(browser, name, viewport)
            verify_moodle(browser, name, viewport)
            verify_historical_progress(browser, name, viewport)
        verify_api_and_public_form(browser)
        browser.close()
