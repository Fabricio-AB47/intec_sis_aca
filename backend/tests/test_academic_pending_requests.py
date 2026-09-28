from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pyodbc
import pytest

from app.core.security import SessionUser, get_current_user
from app.routers import academic_system, career_change_requests, modality_change_requests
from app.services import academic_pending_requests as service


def connection(total=221):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (total,)
    cursor.description = [(name,) for name in (
        'id', 'student_code', 'identification', 'student', 'career', 'period', 'state', 'created_at',
    )]
    cursor.fetchall.return_value = [(31, 10, '001 ', 'Student ', 'Career', 'Period', 'APROBADA', datetime(2026, 9, 22))] if total else []
    return conn, cursor


@pytest.mark.parametrize('source,table,period', [
    ('career', 'sol.SolicitudCambioCarrera', 'PeriodoDestinoNombre'),
    ('modality', 'sol.SolicitudCambioModalidad', 'PeriodoHomologacionNombre'),
])
def test_exact_count_paging_and_read_only(source, table, period):
    conn, cursor = connection()
    with patch.object(service, 'get_integration_control_connection', return_value=conn):
        result = service.read_pending_requests(source, page=2)
    assert result['total'] == 221 and result['total_pages'] == 23 and result['page'] == 2
    assert len(result['items']) == 1
    assert result['items'][0]['identification'] == '001'
    assert result['items'][0]['created_at'].endswith('+00:00')
    queries = cursor.execute.call_args_list
    assert len(queries) == 2
    assert 'COUNT_BIG(*)' in queries[0].args[0]
    assert table in queries[1].args[0] and period in queries[1].args[0]
    assert 'ORDER BY FechaCreacion ASC, IdSolicitud ASC' in queries[1].args[0]
    assert queries[1].args[-2:] == (10, 10)
    for query in queries:
        assert query.args[0].lstrip().startswith('SELECT')
        assert "Estado IN (N'PENDIENTE', N'APROBADA')" in query.args[0]
        assert all(word not in query.args[0] for word in ('CREATE ', 'ALTER ', 'INSERT ', 'DELETE ', 'UPDATE '))
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
    assert conn.timeout == 15


@pytest.mark.parametrize('total,requested,expected', [(0, 9, 1), (221, 999, 23)])
def test_empty_and_disappearing_pages(total, requested, expected):
    conn, _ = connection(total)
    with patch.object(service, 'get_integration_control_connection', return_value=conn):
        result = service.read_pending_requests('career', page=requested)
    assert result['total'] == total and result['page'] == expected
    if not total:
        assert result['items'] == []


def test_search_is_bound_and_wildcards_are_literal():
    conn, cursor = connection()
    term = "a%_[' OR 1=1 --^"
    with patch.object(service, 'get_integration_control_connection', return_value=conn):
        service.read_pending_requests('career', query=term)
    sql, *params = cursor.execute.call_args.args
    assert term not in sql
    assert "%a^%^_^[' OR 1=1 --^^%" in params


@pytest.mark.parametrize('options', [
    {'source': 'invalid'}, {'source': 'career', 'page': 0}, {'source': 'career', 'page_size': 101},
    {'source': 'career', 'state': 'APLICADA'}, {'source': 'career', 'query': 'a' * 121},
])
def test_invalid_filters_never_open_connection(options):
    with patch.object(service, 'get_integration_control_connection') as connect, pytest.raises(HTTPException) as error:
        service.read_pending_requests(**options)
    assert error.value.status_code == 422
    connect.assert_not_called()


def test_failure_does_not_become_zero_or_expose_sql():
    conn, cursor = connection()
    cursor.execute.side_effect = pyodbc.Error('private hostname; credentials; invalid object')
    with patch.object(service, 'get_integration_control_connection', return_value=conn), pytest.raises(HTTPException) as error:
        service.read_pending_requests('career')
    assert error.value.status_code == 503
    assert 'private hostname' not in error.value.detail
    conn.close.assert_called_once()


@pytest.mark.parametrize('module,path,permission', [
    (career_change_requests, '/api/requests/career-change/pending', 'solicitudes-cambio-carrera'),
    (modality_change_requests, '/api/requests/modality-change/pending', 'solicitudes-cambio-modalidad'),
    (academic_system, '/api/academic-system/integration-status', 'sistema-academico'),
])
def test_real_screen_permissions_are_enforced_before_any_read(module, path, permission):
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    with patch('app.core.security.get_settings'):
        assert client.get(path).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SessionUser(login='test@example.test', rol='ACADEMICO')
    access_connection = MagicMock()
    access_cursor = access_connection.__enter__.return_value.cursor.return_value
    access_cursor.fetchone.return_value = None
    with patch('app.services.screen_access.get_integration_control_connection', return_value=access_connection):
        assert client.get(path).status_code == 403
        assert access_cursor.execute.call_args.args[1:] == ('ACADEMICO', permission, f'{permission}/%')


@pytest.mark.parametrize('module,source', [(career_change_requests, 'career'), (modality_change_requests, 'modality')])
def test_pending_route_not_shadowed_and_never_initializes_schema(module, source):
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: SessionUser(login='test', rol='ACADEMICO')
    access_connection = MagicMock()
    access_connection.__enter__.return_value.cursor.return_value.fetchone.return_value = (1,)
    with patch('app.services.screen_access.get_integration_control_connection', return_value=access_connection), \
            patch.object(module, '_ensure_schema') as schema, patch.object(module, 'read_pending_requests', return_value={'total': 0, 'items': []}) as read:
        result = TestClient(app).get(f'/api/requests/{source}-change/pending?page=2&page_size=10&query=student')
    assert result.status_code == 200
    read.assert_called_once_with(source, query='student', page=2, page_size=10)
    schema.assert_not_called()
