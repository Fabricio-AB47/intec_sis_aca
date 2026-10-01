"""Multipart compatibility checks; storage, audit and mail are mocked."""
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import SessionUser
from app.routers import portal_academico as portal


@pytest.fixture
def archive_api():
    app = FastAPI()
    app.add_api_route('/archive', portal.teacher_signed_documents_archive, methods=['POST'])
    app.dependency_overrides[portal._TEACHER_ACCESS] = lambda: SessionUser(
        login='teacher@example.test', rol='DOCENTE', codigo_doc=1, cedula='TEST')

    def store(**kwargs):
        count = 3 + int(kwargs['career_grades_pdf'] is not None) + len(kwargs['invoice_documents'])
        return {'folder_path': 'DOCENTES/test', 'same_folder': True,
                'items': [{'name': f'doc-{i}'} for i in range(count)]}

    with (
        patch.object(portal, '_teacher_contract_identity', return_value={
            'cedula': 'TEST', 'codigo_doc': 1, 'nombre': 'Test', 'correo': 'teacher@example.test'}),
        patch.object(portal, '_assert_pdf_signature_field'),
        patch.object(portal, '_assert_career_grade_pages_signed') as annex_validator,
        patch.object(portal, '_store_signed_teacher_documents_onedrive', side_effect=store) as storage,
        patch.object(portal, 'record_teacher_report_event', return_value=True) as audit,
        patch.object(portal, 'teacher_honoraria_mail_state', return_value='new'),
        patch.object(portal, 'send_teacher_honoraria_mail', return_value='accepted') as send,
        TestClient(app) as client,
    ):
        yield client, storage, send, audit, annex_validator


def uploads(annex=False, invoices=False):
    files = {name: (name + '.pdf', b'%PDF-1.4\nsynthetic', 'application/pdf')
             for name in ('informe', 'notas', 'contrato')}
    if annex:
        files['notas_por_carrera'] = ('anexo.pdf', b'%PDF-1.4\nannex', 'application/pdf')
    if invoices:
        files['factura_xml'] = ('factura.xml', b'<factura/>', 'application/xml')
        files['ride_pdf'] = ('ride.pdf', b'%PDF-1.4\nride', 'application/pdf')
    return files


@pytest.mark.parametrize('annex,invoices,count', [(False, False, 3), (True, False, 4), (False, True, 5), (True, True, 6)])
def test_accepts_both_multipart_versions(archive_api, annex, invoices, count):
    client, storage, send, audit, validator = archive_api
    response = client.post('/archive', files=uploads(annex, invoices))
    assert response.status_code == 200, response.text
    assert response.headers['X-OneDrive-Item-Count'] == str(count)
    assert response.headers['X-Honorarios-Email-Status'] == ('sent' if invoices else 'pending')
    with ZipFile(BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == count
        assert ('reporte-notas-por-carrera-firmado.pdf' in archive.namelist()) == annex
    assert (storage.call_args.kwargs['career_grades_pdf'] is not None) == annex
    assert validator.call_count == int(annex)
    archived = next(call.kwargs for call in audit.call_args_list if call.kwargs['stage'] == 'ARCHIVADO')
    assert archived['metadata']['anexo_por_carrera_incluido'] == annex
    if invoices:
        docs = send.call_args.args[1]
        assert len(docs) == count
        assert all(isinstance(doc['content'], bytes) for doc in docs)
    else:
        send.assert_not_called()


def test_supplied_unsigned_annex_is_not_silently_omitted(archive_api):
    client, storage, send, _, validator = archive_api
    validator.side_effect = HTTPException(400, 'Cada hoja del anexo debe estar firmada')
    response = client.post('/archive', files=uploads(True))
    assert response.status_code == 400
    storage.assert_not_called()
    send.assert_not_called()


def test_empty_annex_is_rejected(archive_api):
    client, storage, send, _, _ = archive_api
    files = uploads(True)
    files['notas_por_carrera'] = ('anexo.pdf', b'', 'application/pdf')
    response = client.post('/archive', files=files)
    assert response.status_code == 400
    storage.assert_not_called()
    send.assert_not_called()


def test_contract_remains_required(archive_api):
    client, storage, send, _, _ = archive_api
    files = uploads()
    del files['contrato']
    assert client.post('/archive', files=files).status_code == 422
    storage.assert_not_called()
    send.assert_not_called()
