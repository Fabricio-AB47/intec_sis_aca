import unittest

from pydantic import ValidationError

from app.core.config import Settings


class SettingsSecurityTests(unittest.TestCase):
    @staticmethod
    def base_settings(**overrides):
        values = {
            "B_NAME": "INTECBDD_TEST",
            "db_user": "test_user",
            "db_password": "test_password",
            "db_host": "localhost",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def test_sensitive_fields_are_excluded_from_settings_repr(self) -> None:
        sensitive_fields = (
            "db_password",
            "eval_db_password",
            "practices_db_password",
            "titulation_db_password",
            "teams_db_password",
            "expedient_db_password",
            "finance_db_password",
            "graph_db_password",
            "integration_control_db_password",
            "client_secret",
            "smtp_password",
            "session_secret",
            "rate_limit_redis_url",
        )

        for field_name in sensitive_fields:
            with self.subTest(field_name=field_name):
                self.assertFalse(Settings.model_fields[field_name].repr)

    def test_development_defaults_remain_compatible(self) -> None:
        settings = self.base_settings()

        self.assertFalse(settings.is_production)
        self.assertEqual(settings.session_cookie_samesite, "lax")

    def test_production_rejects_insecure_defaults(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Configuración de producción insegura"):
            self.base_settings(APP_ENVIRONMENT="production")

    def test_production_accepts_explicit_secure_configuration(self) -> None:
        settings = self.base_settings(
            APP_ENVIRONMENT="production",
            api_docs_enabled=False,
            expose_internal_errors=False,
            security_headers_enabled=True,
            security_hsts_enabled=True,
            csrf_protection_enabled=True,
            csrf_require_origin=True,
            trusted_hosts="api.example.edu.ec",
            session_secret="x" * 48,
            session_cookie_secure=True,
            auth_legacy_plaintext_enabled=False,
            db_encrypt="yes",
            db_trust_cert="no",
            cors_origins="https://app.example.edu.ec",
            frontend_base_url="https://app.example.edu.ec",
            graph_delegate_redirect_uri="https://api.example.edu.ec/api/auth/microsoft/callback",
            rate_limit_backend="redis",
            rate_limit_redis_url="redis://localhost:6379/0",
            upload_antimalware_enabled=True,
        )

        self.assertTrue(settings.is_production)

    def test_production_rejects_insecure_complementary_database(self) -> None:
        with self.assertRaisesRegex(ValidationError, "EXPEDIENT_DB_ENCRYPT"):
            self.base_settings(
                APP_ENVIRONMENT="production",
                api_docs_enabled=False,
                security_hsts_enabled=True,
                csrf_require_origin=True,
                trusted_hosts="api.example.edu.ec",
                session_secret="x" * 48,
                session_cookie_secure=True,
                auth_legacy_plaintext_enabled=False,
                db_encrypt="yes",
                db_trust_cert="no",
                EXPEDIENT_DB_ENCRYPT="no",
                cors_origins="https://app.example.edu.ec",
                frontend_base_url="https://app.example.edu.ec",
                graph_delegate_redirect_uri="https://api.example.edu.ec/api/auth/microsoft/callback",
            )


if __name__ == "__main__":
    unittest.main()
