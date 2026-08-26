import secrets
import unittest
from unittest.mock import MagicMock, patch

from app.core.audit_context import (
    AuditContext,
    get_audit_context,
    reset_audit_context,
    set_audit_context,
)
from app.services.db import _apply_audit_context, _build_connection_string
from scripts.install_total_audit import (
    ColumnInfo,
    TableInfo,
    _build_dml_trigger,
    _snapshot_expression,
)


TEST_DATABASE_PASSWORD = secrets.token_urlsafe(12)


class AuditContextTests(unittest.TestCase):
    def test_context_is_isolated_and_restored(self) -> None:
        original = get_audit_context()
        token = set_audit_context(
            AuditContext(
                user="usuario@intec.edu.ec",
                role="ACADEMICO",
                request_id="solicitud-1",
            )
        )
        try:
            current = get_audit_context()
            self.assertEqual(current.user, "usuario@intec.edu.ec")
            self.assertEqual(current.role, "ACADEMICO")
            self.assertEqual(current.request_id, "solicitud-1")
        finally:
            reset_audit_context(token)

        self.assertEqual(get_audit_context(), original)

    def test_connection_receives_application_identity(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value
        token = set_audit_context(
            AuditContext(
                user="auditor@intec.edu.ec",
                role="ADMINISTRADOR",
                user_id="42",
                origin="USUARIO_SIS",
                request_id="req-42",
                method="PATCH",
                path="/api/estudiantes/42",
                client_ip="127.0.0.1",
            )
        )
        try:
            self.assertIs(_apply_audit_context(connection), connection)
        finally:
            reset_audit_context(token)

        cursor.execute.assert_called_once()
        params = cursor.execute.call_args.args[1:]
        self.assertEqual(
            params,
            (
                "auditor@intec.edu.ec",
                "ADMINISTRADOR",
                "42",
                "USUARIO_SIS",
                "req-42",
                "PATCH",
                "/api/estudiantes/42",
                "127.0.0.1",
            ),
        )
        cursor.close.assert_called_once()

    def test_connection_string_identifies_the_api(self) -> None:
        value = _build_connection_string(
            database="INTECBDD",
            user="usuario",
            password=TEST_DATABASE_PASSWORD,
            host="127.0.0.1",
            port=1433,
            driver="ODBC Driver 17 for SQL Server",
            encrypt="no",
            trust_cert="yes",
        )
        self.assertIn("APP=INTEC_SIS_ACA_API;", value)


class AuditTriggerGenerationTests(unittest.TestCase):
    def test_sensitive_values_are_redacted(self) -> None:
        expression = _snapshot_expression(
            ColumnInfo("PasswordHash", "nvarchar", False, False)
        )
        self.assertIn("[PROTEGIDO]", expression)
        self.assertNotIn("TRY_CONVERT", expression)

    def test_legacy_lob_is_not_read_from_inserted_or_deleted(self) -> None:
        expression = _snapshot_expression(ColumnInfo("Contenido", "text", False, False))
        self.assertIn("[TIPO LEGACY NO CAPTURADO]", expression)
        self.assertNotIn("src.[Contenido]", expression)

    def test_computed_column_is_excluded_from_update_detection(self) -> None:
        _, sql = _build_dml_trigger(
            database="INTECBDD",
            table=TableInfo(1, "dbo", "Prueba"),
            columns=[
                ColumnInfo("Id", "int", False, False),
                ColumnInfo("Nombre", "nvarchar", False, False),
                ColumnInfo("NombreNormalizado", "nvarchar", False, True),
            ],
            primary_keys=["Id"],
            capture_data=True,
            max_rows=100,
        )
        self.assertIn("UPDATE([Nombre])", sql)
        self.assertNotIn("UPDATE([NombreNormalizado])", sql)
        self.assertIn("CREATE OR ALTER TRIGGER [dbo].[trg_AUD_DML_", sql)
        self.assertIn("[INTEC_INTEGRACION_CONTROL].[aud].[sp_RegistrarCambio]", sql)


if __name__ == "__main__":
    unittest.main()
