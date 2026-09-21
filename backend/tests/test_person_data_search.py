import os
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.security import SessionUser
from app.routers import students


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(students.router)
    app.dependency_overrides[students._STUDENT_ACCESS] = lambda: SessionUser(login="admin", rol="ADMINISTRADOR")
    with TestClient(app) as value:
        yield value


@pytest.mark.parametrize("target", ["estudiantes", "docentes"])
def test_name_search_matches_all_tokens_and_keeps_values_parameterized(target):
    sql, params = students._data_update_search_filter(target, "ANA PEREZ")
    assert params[-2:] == ["%ANA%", "%PEREZ%"]
    assert " AND " in sql
    assert "COLLATE Latin1_General_CI_AI LIKE ? ESCAPE '~'" in sql
    assert "ANA" not in sql and "PEREZ" not in sql
    malicious = "O'NEIL %_~["
    sql, params = students._data_update_search_filter(target, malicious)
    assert malicious not in sql
    assert params[-1] == "%~%~_~~~[%"
    assert students._data_update_search_filter(target, "") == ("1 = 1", [])


@pytest.mark.parametrize("target, table, id_column, summary", [
    ("estudiantes", "DATOS_ESTUD", "codigo_estud", "_student_data_summary"),
    ("docentes", "DATOSDOCENTE", "codigo_doc", "_teacher_data_summary"),
])
def test_search_returns_only_requested_page_and_reports_more_without_writes(client, target, table, id_column, summary):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = ["person-21", "person-22", "person-23"]
    with patch.object(students, "get_connection", return_value=conn), patch.object(
        students, "_actualizacion_datos_columns", return_value=["movil"],
    ), patch.object(students, summary, side_effect=lambda row, _: {"id": row}):
        response = client.get(f"/api/students/actualizacion-datos/{target}/buscar", params={"q": "  Ana  Perez ", "limit": 2, "offset": 20})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rows": [{"id": "person-21"}, {"id": "person-22"}], "total": 2, "limit": 2,
        "offset": 20, "has_more": True, "query": "Ana Perez", "target": target,
    }
    sql, *params = cursor.execute.call_args.args
    assert f"dbo.{table}" in sql
    assert f", d.{id_column}\n" in sql
    assert "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" in sql
    assert params[-2:] == [20, 3]
    conn.commit.assert_not_called()


@pytest.mark.parametrize("params", [{"offset": -1}, {"limit": 0}, {"limit": 201}, {"q": "a" * 121}])
def test_invalid_search_parameters_are_rejected_before_database_access(client, params):
    with patch.object(students, "get_connection") as connection:
        response = client.get("/api/students/actualizacion-datos/estudiantes/buscar", params=params)
    assert response.status_code == 422
    connection.assert_not_called()


def test_unknown_target_is_rejected_before_database_access(client):
    with patch.object(students, "get_connection") as connection:
        response = client.get("/api/students/actualizacion-datos/usuarios/buscar?q=Ana")
    assert response.status_code == 404
    connection.assert_not_called()


@pytest.mark.skipif(os.environ.get("PERSON_DATA_SQL_READONLY_TESTS") != "1", reason="SQL Server SELECT-only test")
@pytest.mark.parametrize("target", ["estudiantes", "docentes"])
def test_search_sql_matches_accents_unordered_names_and_literal_wildcards(target):
    from app.services.db import get_connection

    fixture = """WITH people AS (
        SELECT * FROM (VALUES
            (1, N'PEREZ LOPEZ ANA MARIA', '0100000001', 'ana@example.test'),
            (2, N'GARCIA ANA', '0100000002', 'otra@example.test'),
            (3, N'P\u00c9REZ JOS\u00c9', '0100000003', 'jose@example.test'),
            (4, N'LITERAL %_[', '0100000004', 'literal@example.test')
        ) v(id, nombre, cedula, email)
    ), d AS (
        SELECT id AS codigo_estud, id AS codigo_doc, nombre AS Apellidos_nombre,
            cedula AS Cedula_Est, cedula AS cedula_doc, email AS correo, email AS correop
        FROM people
    ) SELECT codigo_estud FROM d WHERE """
    with get_connection() as connection:
        cursor = connection.cursor()
        for query, expected in [("Ana Perez", [1]), ("Perez Ana", [1]), ("Jose Perez", [3]), ("ana", [1, 2]),
                                ("%_[", [4]), ("0100000002", [2]), ("nadie", [])]:
            sql, params = students._data_update_search_filter(target, query)
            cursor.execute(fixture + sql + " ORDER BY codigo_estud", *params)
            assert [row[0] for row in cursor.fetchall()] == expected
