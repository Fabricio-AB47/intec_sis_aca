from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import SessionUser
from app.routers import students


@pytest.mark.parametrize("target, table, key_column, document_column", [
    ("estudiantes", "DATOS_ESTUD", "codigo_estud", "Cedula_Est"),
    ("docentes", "DATOSDOCENTE", "codigo_doc", "cedula_doc"),
])
@pytest.mark.parametrize("changed", [True, False])
def test_save_returns_refreshed_person_from_resolved_id_and_correct_table(target, table, key_column, document_column, changed):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = SimpleNamespace(
        record_id="42", record_document="1700000000",
        **{document_column: "1700000000", "correo": "anterior@example.test"},
    )
    cursor.rowcount = 1
    new_email = "nuevo@example.test" if changed else "anterior@example.test"
    refreshed = {
        "source_table": table, "person": {"id": "42", "codigo": "42", "cedula": "1700000000",
                                           "correo": new_email, "campos_pendientes": 0},
        "fields": {document_column: "1700000000", "correo": new_email},
    }
    with patch.object(students, "get_connection", return_value=conn), patch.object(
        students, "_actualizacion_datos_columns", return_value=[document_column, "correo"],
    ), patch.object(students, "_actualizacion_datos_field_metadata", return_value={
        document_column: {"data_type": "varchar", "max_length": 50, "nullable": False, "readonly": True},
        "correo": {"data_type": "varchar", "max_length": 100, "nullable": True, "readonly": False},
    }), patch.object(students, "_apply_student_legacy_rules", side_effect=lambda cursor, fields, **kwargs: fields), patch.object(
        students, "_apply_teacher_legacy_rules", side_effect=lambda fields, **kwargs: fields,
    ), patch.object(students, "_load_legacy_data_update_record", return_value=refreshed.copy()) as reload_record, patch.object(
        students, "sync_person_complements", return_value={},
    ) as sync:
        response = students.update_legacy_data_update_record(
            target, "1700000000", students.DataUpdatePayload(fields={"correo": new_email}),
            SessionUser(login="admin@example.test", rol="ADMINISTRADOR"),
        )
    reload_record.assert_called_once_with(cursor, target, "42")
    assert response["source_table"] == table
    assert response["fields"]["correo"] == new_email
    assert response["person"]["campos_pendientes"] == 0
    assert response["affected_rows"] == int(changed)
    assert response["updated_fields"] == (["correo"] if changed else [])
    updates = [call.args for call in cursor.execute.call_args_list if "UPDATE " in call.args[0]]
    if changed:
        assert len(updates) == 1
        sql, *params = updates[0]
        assert f"UPDATE dbo.[{table}]" in sql
        assert f"WHERE TRY_CONVERT(varchar(50), [{key_column}]) = ?" in sql
        assert " OR " not in sql
        assert params == [new_email, "42"]
        conn.commit.assert_called_once()
        sync.assert_called_once()
        assert sync.call_args.args[0]["correo"] == new_email
        assert sync.call_args.args[0]["usuario"] == "admin@example.test"
    else:
        assert updates == []
        conn.commit.assert_not_called()
        sync.assert_not_called()
