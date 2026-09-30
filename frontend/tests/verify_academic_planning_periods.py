"""Synthetic-only PEA/syllabus regression for grouped courses with 11 periods."""
import json
import re
from email.parser import BytesParser
from email.policy import default
from urllib.parse import urlparse

from playwright.sync_api import expect
from verify_runtime_optimizations import BASE_URL, mock_context

PERIODS = [1032, 1028, 1025, 1022, 1016, 1060, 1051, 1027, 1024, 1023, 1020]


def verify(browser, name, viewport):
    permission = 'portal-docente-planificacion'
    context, page, _, _, errors = mock_context(browser, [permission], permission, viewport)
    sent = []
    course = dict(codigo_periodos=PERIODS, codigo_materia='TEST', cod_materia='TEST',
                  cod_anio_basica=12, paralelo='VARIOS', cod_jornada=1, nombre_materia='Asignatura de prueba',
                  nombre_carrera='Carrera', detalle_periodos='11 periodos')
    storage_key = 'portal.teacher.planning.' + ','.join(map(str, PERIODS)) + '|12|TEST|VARIOS|1'
    draft = {'unidades': [{'nombre': 'Unidad 1', 'temas': [{'tema': 'Tema de prueba', 'semana': 1,
             'horas_docencia': 3, 'horas_practica': 1, 'horas_autonomo': 2}]}]}
    context.add_init_script(f'localStorage.setItem({json.dumps(storage_key)}, {json.dumps(json.dumps(draft))})')

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        if path.endswith('/courses'):
            assert request.method == 'GET'
            return route.fulfill(content_type='application/json', body=json.dumps({'items': [course]}))
        assert request.method == 'POST'
        if path.endswith('/academic-planning-sign'):
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode() + request.post_data_buffer)
            fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
                      for part in message.iter_parts()}
            payload = json.loads(fields['payload_json'])
        else:
            assert path.endswith('/academic-planning-pdf')
            payload = request.post_data_json
        assert payload['codigo_periodos'] == PERIODS
        sent.append((path, payload['document_type']))
        route.fulfill(content_type='application/pdf', body=b'%PDF-1.4\n%%EOF')

    context.route('**/api/portal/teacher/**', api)
    page.goto(BASE_URL)
    expect(page.get_by_label('Materia asignada')).to_contain_text('11 periodos')
    page.get_by_role('button', name='Guardar borrador', exact=True).click()
    assert json.loads(page.evaluate('(key) => localStorage.getItem(key)', storage_key))['unidades'][0]['temas'][0]['tema'] == 'Tema de prueba'
    for kind, label in [('pea', 'PEA'), ('silabo', 'Sílabo')]:
        page.get_by_role('radio', name=re.compile('^' + label)).click()
        page.get_by_role('button', name=f'Vista previa {label}', exact=True).first.click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_role('button', name='Cerrar', exact=True).click()
        with page.expect_download():
            page.get_by_role('button', name=f'Generar {label} PDF', exact=True).click()
        page.locator('.planning-module-nav button').nth(7).click()
        page.get_by_label('Certificado .p12 o .pfx', exact=True).set_input_files(
            {'name': 'test.p12', 'mimeType': 'application/x-pkcs12', 'buffer': b'test-only'})
        page.get_by_label('Contraseña del certificado', exact=True).fill('test-only')
        with page.expect_download():
            page.get_by_role('button', name=f'Firmar {label}', exact=True).click()
        expect(page.get_by_label('Contraseña del certificado', exact=True)).to_have_value('')
        assert sent[-1] == ('/api/portal/teacher/academic-planning-sign', kind)
    assert len(sent) == 6
    assert not errors, errors
    context.close()
    print(f'{name}: 11 periods preserved in draft, preview, download and synthetic signing for PEA/syllabus')
