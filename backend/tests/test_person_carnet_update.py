from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import SessionUser
from app.routers import students


@pytest.mark.parametrize("field, sanitizer", [
    ("No_Carnet", students._sanitize_student_data_field),
    ("carnet_conadis", students._sanitize_teacher_data_field),
])
@pytest.mark.parametrize("value, expected", [
    ("NA", "NA"), (" na ", "NA"), ("Na", "NA"), ("01", "01"), (0, "0"), (None, ""),
])
def test_carnet_preserves_na_and_numeric_identifiers(field, sanitizer, value, expected):
    assert sanitizer(field, value) == expected
    assert sanitizer("movil", "NA") == ""


@pytest.mark.parametrize("target, table, key, field, max_length", [
    ("estudiantes", "DATOS_ESTUD", "codigo_estud", "No_Carnet", 20),
    ("docentes", "DATOSDOCENTE", "codigo_doc", "carnet_conadis", 2),
])
@pytest.mark.parametrize("edit_carnet", [True, False])
def test_save_keeps_na_in_the_correct_table_even_when_only_another_field_changes(
    target, table, key, field, max_length, edit_carnet,
):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = SimpleNamespace(
        record_id="42", record_document="1700000000",
        **{field: "0" if edit_carnet else "NA", "correo": "anterior@example.test"},
    )
    cursor.rowcount = 1
    email = "anterior@example.test" if edit_carnet else "nuevo@example.test"
    refreshed = {"person": {"codigo": "42", "cedula": "1700000000", "correo": email},
                 "fields": {field: "NA", "correo": email}}
    updates = {field: " na "} if edit_carnet else {"correo": email}
    with patch.object(students, "get_connection", return_value=conn), patch.object(
        students, "_actualizacion_datos_columns", return_value=[field, "correo"],
    ), patch.object(students, "_actualizacion_datos_field_metadata", return_value={
        field: {"data_type": "nchar", "max_length": max_length, "nullable": True, "readonly": False},
        "correo": {"data_type": "nchar", "max_length": 100, "nullable": True, "readonly": False},
    }), patch.object(students, "_fetch_student_beca_fields", return_value={}), patch.object(
        students, "_fetch_single_value", return_value="",
    ), patch.object(students, "_latest_student_cabecera", return_value=None), patch.object(
        students, "_load_legacy_data_update_record", return_value=refreshed,
    ), patch.object(students, "sync_person_complements", return_value={}):
        response = students.update_legacy_data_update_record(
            target, "42", students.DataUpdatePayload(fields=updates),
            SessionUser(login="admin@example.test", rol="ADMINISTRADOR"),
        )
    assert response["fields"][field] == "NA"
    assert response["updated_fields"] == ([field] if edit_carnet else ["correo"])
    sql, *params = cursor.execute.call_args.args
    assert f"UPDATE dbo.[{table}]" in sql
    assert f"WHERE TRY_CONVERT(varchar(50), [{key}]) = ?" in sql
    assert params == ["NA" if edit_carnet else email, "42"]
    conn.commit.assert_called_once()
