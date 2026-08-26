import unittest

from app.core.config import Settings


class SettingsSecurityTests(unittest.TestCase):
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
        )

        for field_name in sensitive_fields:
            with self.subTest(field_name=field_name):
                self.assertFalse(Settings.model_fields[field_name].repr)


if __name__ == "__main__":
    unittest.main()
