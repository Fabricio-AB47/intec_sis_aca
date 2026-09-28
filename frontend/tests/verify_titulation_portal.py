"""The former secondary portal runs in React. All reads and writes are mocked."""
import json
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright
from verify_runtime_optimizations import BASE_URL, ROOT, mock_context

PREFIX = '/api/titulation-portal/'
GROUP = {'grupoTitulacionId': 4, 'codigoGrupo': 'GRUPO-PRUEBA', 'tema': 'Tema', 'carrera': 'Software',
         'mecanismoCodigo': 'EXAMEN_COMPLEXIVO', 'estadoCodigo': 'PROGRAMADO', 'estudiantes': [
             {'expedienteId': 3, 'numeroIdentificacion': '1700000001', 'estadoCodigo': 'ACTIVO'}],
         'responsables': [{'nombres': 'Responsable', 'rolCodigo': 'EVALUADOR', 'orden': 1}]}


def setup(browser, viewport, configured=True, roles=None):
    context, page, _, _, errors = mock_context(browser, ['titulacion-proceso'], 'titulacion-proceso', viewport)
    writes = []
    def handle(route):
        path = urlparse(route.request.url).path.removeprefix(PREFIX)
        if route.request.method != 'GET':
            writes.append((path, route.request))
            return route.fulfill(content_type='application/json', body=json.dumps({'resultado': 'Guardado'}))
        body = []
        if path == 'status': body = {'configured': configured, 'roles': roles or ['ADMIN_TITULACION', 'COORDINADOR_ACADEMICO', 'EVALUADOR_TITULACION']}
        elif path == 'dashboard/resumen': body = {'estudiantesAptos': 5, 'actasGeneradas': 2}
        elif path == 'estudiantes-aptos': body = {'items': [{'cedula': '1700000001', 'nombres': 'Estudiante Prueba', 'carrera': 'Software', 'periodo': '2026', 'puedeHabilitar': True}], 'total': 1, 'pageSize': 25}
        elif path == 'habilitaciones': body = [{'habilitacionId': 2, 'expedienteId': 3, 'numeroIdentificacion': '1700000001', 'estadoCodigo': 'ACTIVO'}]
        elif path == 'grupos': body = [GROUP]
        elif path == 'grupos/4': body = GROUP
        elif path == 'responsables': body = [{'responsableTitulacionId': n, 'nombres': f'Responsable {n}', 'rolCodigo': 'EVALUADOR', 'activo': True} for n in range(1, 5)]
        elif path == 'expedientes/3/documentos': body = [{'documentoId': 2, 'tipoDocumentoCodigo': 'APTITUD_LEGAL', 'nombreArchivo': 'Documento.pdf', 'usuarioCarga': 'secretaria@example.test', 'version': 1, 'estadoCodigo': 'CARGADO'}]
        elif path == 'documentos/2/historial': body = [{'accion': 'CARGA', 'usuarioAccion': 'secretaria@example.test', 'version': 1}]
        elif path == 'expedientes/3/calificaciones': body = [{'notaExamenComplexivo': 9, 'evaluadorNumero': 1}]
        elif path == 'expedientes/3/calificaciones/consolidado': body = {'notaFinalGrado': 9}
        elif path == 'actas': body = [{'actaGradoId': 8, 'expedienteId': 3, 'numeroActa': 'ACTA-PRUEBA', 'nombresEstudiante': 'Estudiante Prueba', 'estadoCodigo': 'GENERADA'}]
        elif path == 'actas/8/pdf': return route.fulfill(content_type='application/pdf', body=b'%PDF-test')
        elif path == 'titulos': body = [{'expedienteId': 3, 'nombresEstudiante': 'Estudiante Prueba', 'tipoDocumentoCodigo': 'TITULO_INTEC', 'estadoCodigo': 'CARGADO'}]
        route.fulfill(content_type='application/json', body=json.dumps(body))
    context.route('**/api/titulation-portal/**', handle)
    page.goto(BASE_URL)
    page.get_by_role('tab', name='Gestión integral', exact=True).click()
    page.get_by_role('heading', name='Gestión integral de titulación', exact=True).wait_for()
    return context, page, writes, errors


def verify(browser, name, viewport):
    context, page, writes, errors = setup(browser, viewport)
    tabs = page.get_by_role('tablist', name='Secciones de titulación')
    expect(tabs.get_by_role('tab')).to_have_count(12)
    for tab in ['Estudiantes aptos', 'Habilitaciones', 'Grupos', 'Complexivo', 'Defensa', 'Responsables', 'Calificaciones', 'Títulos', 'Actas', 'Resumen']:
        tabs.get_by_role('tab', name=tab, exact=True).click()
        page.wait_for_timeout(120)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), tab
    tabs.get_by_role('tab', name='Estudiantes aptos', exact=True).click()
    page.get_by_role('button', name='Habilitar', exact=True).click()
    dialog = page.get_by_role('dialog')
    expect(dialog.get_by_role('heading')).to_have_text('Habilitar Estudiante Prueba')
    dialog.get_by_role('button', name='Guardar', exact=True).click()
    expect(dialog).not_to_be_visible()
    assert writes[-1][0] == 'habilitaciones'
    assert writes[-1][1].post_data_json['cedula'] == '1700000001'
    tabs.get_by_role('tab', name='Complexivo', exact=True).click()
    page.get_by_role('button', name='Crear con Teams').click()
    dialog.get_by_label('Código del grupo', exact=True).fill('R30')
    dialog.get_by_label('Tema', exact=True).fill('Tema de prueba')
    dialog.get_by_label('Responsable', exact=True).select_option('1')
    for n in range(1, 4): dialog.get_by_label(f'Evaluador {n}', exact=True).select_option('2')
    before = len(writes)
    dialog.get_by_role('button', name='Guardar', exact=True).click()
    expect(dialog.get_by_role('alert')).to_have_text('No se pueden repetir responsables o evaluadores.')
    assert len(writes) == before
    dialog.get_by_role('button', name='Cancelar', exact=True).click()
    page.get_by_role('button', name='Ver integrantes', exact=True).click()
    expect(page.get_by_role('heading', name='GRUPO-PRUEBA · Integrantes')).to_be_visible()
    page.get_by_role('button', name='Ver notas', exact=True).click()
    expect(page.get_by_text('9', exact=True)).to_be_visible()
    tabs.get_by_role('tab', name='Documentos', exact=True).click()
    page.get_by_label('Número de expediente', exact=True).fill('3')
    page.get_by_role('button', name='Buscar', exact=True).click()
    expect(page.get_by_text('Documento.pdf', exact=True)).to_be_visible()
    page.get_by_role('button', name='Historial', exact=True).click()
    expect(page.get_by_text('CARGA', exact=True)).to_be_visible()
    page.get_by_role('button', name='Cargar documento', exact=True).click()
    dialog.get_by_label('Archivo', exact=True).set_input_files({'name': 'prueba.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-mock'})
    dialog.get_by_role('button', name='Guardar', exact=True).click()
    expect(dialog).not_to_be_visible()
    assert writes[-1][0] == 'documentos/upload'
    assert 'multipart/form-data' in writes[-1][1].headers['content-type']
    assert b'name="expedienteId"\r\n\r\n3' in writes[-1][1].post_data_buffer
    tabs.get_by_role('tab', name='Títulos', exact=True).click()
    page.get_by_role('button', name='Título SENESCYT', exact=True).click()
    expect(dialog.get_by_label('Código de registro')).to_have_attribute('required', '')
    expect(dialog.get_by_label('Fecha de registro')).to_have_attribute('required', '')
    dialog.get_by_role('button', name='Cancelar', exact=True).click()
    tabs.get_by_role('tab', name='Actas', exact=True).click()
    with page.expect_download() as result:
        page.get_by_role('button', name='PDF', exact=True).click()
    assert result.value.suggested_filename == 'acta-8.pdf'
    tabs.get_by_role('tab', name='Reportes', exact=True).click()
    with page.expect_download() as result:
        page.get_by_role('button', name='Exportar aptos CSV', exact=True).click()
    assert 'Estudiante Prueba' in open(result.value.path(), encoding='utf-8-sig').read()
    tabs.get_by_role('tab', name='Grupos', exact=True).click()
    page.get_by_role('button', name='Nuevo grupo').click()
    page.screenshot(path=str(ROOT / '.runlogs' / f'titulation-unified-{name}.png'), full_page=True)
    assert not errors, errors
    context.close()
    print(f'{name}: 12 sections, habilitation, groups, validation, uploads, titles, PDF and real report rows passed')


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        for name, viewport in [('desktop', {'width': 1500, 'height': 950}), ('mobile', {'width': 390, 'height': 844})]: verify(browser, name, viewport)
        context, page, writes, errors = setup(browser, {'width': 1400, 'height': 900}, configured=False)
        expect(page.get_by_text('El servicio de titulación necesita configurar su conexión en el servidor. Los expedientes individuales continúan disponibles.')).to_be_visible()
        assert not writes
        context.close()
        context, page, writes, errors = setup(browser, {'width': 1400, 'height': 900}, roles=['SECRETARIA_TITULACION'])
        page.get_by_role('tab', name='Grupos', exact=True).click()
        expect(page.get_by_role('button', name='Nuevo grupo')).to_have_count(0)
        page.get_by_role('tab', name='Títulos', exact=True).click()
        expect(page.get_by_role('button', name='Título SENESCYT', exact=True)).to_be_visible()
        context.close()
        browser.close()
