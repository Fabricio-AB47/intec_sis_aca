from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import jwt
from pydantic import SecretStr
import pytest

from app.core.security import SessionUser
from app.routers import titulation_portal as portal


KEY = 'test-only-strong-signing-key-1234567890'
USER = SessionUser(login='secretaria@example.test', rol='SECRETARIA')


def settings(**kwargs):
    return SimpleNamespace(titulation_portal_url=kwargs.get('url', 'http://127.0.0.1:8007'),
                           titulation_portal_signing_key=SecretStr(kwargs.get('key', KEY)),
                           titulation_portal_issuer='test', titulation_portal_audience='test-web')


def client():
    app = FastAPI()
    app.include_router(portal.router)
    app.dependency_overrides[portal._ACCESS] = lambda: USER
    return TestClient(app)


@pytest.mark.parametrize('url', ['http://remote.test', 'file:///etc/passwd', 'https://name:pass@host', 'https://host/api', 'https://host?q=1', ''])
def test_rejects_unsafe_service_url(url):
    with patch.object(portal, 'get_settings', return_value=settings(url=url)), pytest.raises(HTTPException) as error:
        portal.portal_config()
    assert error.value.status_code == 503


@pytest.mark.parametrize('key', ['short', 'INTEC_TITULACION_DEV_SIGNING_KEY_CHANGE_ME_2026'])
def test_requires_explicit_strong_key(key):
    with patch.object(portal, 'get_settings', return_value=settings(key=key)), pytest.raises(HTTPException):
        portal.portal_config()


def test_token_preserves_actor_and_does_not_elevate_secretary():
    token = portal.portal_token(USER, settings(), KEY)
    payload = jwt.decode(token, KEY, algorithms=['HS256'], audience='test-web', issuer='test')
    assert payload['sub'] == USER.login
    assert payload['role'] == ['SECRETARIA_TITULACION']
    assert payload['exp'] - payload['iat'] == 120


def test_anonymous_and_student_cannot_access_bridge():
    app = FastAPI()
    app.include_router(portal.router)
    with patch('app.core.security.get_settings'):
        assert TestClient(app).get('/api/titulation-portal/status').status_code == 401
    with pytest.raises(HTTPException) as error:
        portal.portal_roles(SessionUser(login='student', rol='ESTUDIANTE'))
    assert error.value.status_code == 403


@pytest.mark.parametrize('path', ['auth/login', 'documentos/1/download', 'http://evil.test', 'grupos/1/../../users'])
def test_only_allowlisted_endpoints(path):
    assert client().post(f'/api/titulation-portal/{path}', json={}).status_code == 404


def test_disconnected_status_is_explicit_and_does_not_reveal_secrets():
    with patch.object(portal, 'get_settings', return_value=settings(url='')):
        response = client().get('/api/titulation-portal/status')
    assert response.json() == {'configured': False, 'roles': ['SECRETARIA_TITULACION']}
    assert KEY not in response.text


@pytest.mark.parametrize('method,path,content_type,body,response_type', [
    ('GET', 'actas/5/pdf', '', b'', 'application/pdf'),
    ('POST', 'habilitaciones', 'application/json', b'{"cedula":"123"}', 'application/json'),
    ('POST', 'documentos/upload', 'multipart/form-data; boundary=sample', b'--sample\r\ncontent\r\n--sample--', 'application/json'),
    ('PUT', 'documentos/1/observar', 'application/json', b'"Pendiente"', 'application/json'),
])
def test_forwarding_retains_body_identity_and_download(method, path, content_type, body, response_type):
    seen = []
    def handle(request):
        seen.append(request)
        assert request.headers.get('cookie') is None
        claims = jwt.decode(request.headers['authorization'][7:], KEY, algorithms=['HS256'], audience='test-web')
        assert claims['sub'] == USER.login
        return httpx.Response(200, content=b'%PDF-test' if response_type == 'application/pdf' else b'{"ok":true}', headers={'content-type': response_type})
    factory = httpx.AsyncClient
    with patch.object(portal, 'get_settings', return_value=settings()), patch.object(portal.httpx, 'AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handle), **kw)):
        result = client().request(method, f'/api/titulation-portal/{path}?grupoId=3', content=body, headers={'content-type': content_type, 'authorization': 'Bearer browser-fake'})
    assert result.status_code == 200
    assert seen[0].content == body
    assert seen[0].url.params['grupoId'] == '3'
    assert result.headers['content-type'] == response_type
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('upstream,status', [(403, 403), (400, 400), (401, 502), (500, 502), (302, 502)])
def test_errors_preserve_permission_and_mask_server_internals(upstream, status):
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(upstream, json={'detail': 'test-validation'}))
    with patch.object(portal, 'get_settings', return_value=settings()), patch.object(portal.httpx, 'AsyncClient', side_effect=lambda **kw: factory(transport=transport, **kw)):
        result = client().get('/api/titulation-portal/habilitaciones')
    assert result.status_code == status
    if status == 502:
        assert 'test-validation' not in result.text


def test_mutation_timeout_is_not_retried():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout('private server info')
    factory = httpx.AsyncClient
    with patch.object(portal, 'get_settings', return_value=settings()), patch.object(portal.httpx, 'AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handle), **kw)):
        response = client().post('/api/titulation-portal/habilitaciones', json={})
    assert response.status_code == 504 and len(calls) == 1
    assert 'private server info' not in response.text
