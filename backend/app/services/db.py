import pyodbc

from app.core.config import get_settings


def _build_connection_string(driver: str | None = None) -> str:
    settings = get_settings()
    resolved_driver = driver or settings.db_driver
    return (
        f"DRIVER={{{resolved_driver}}};"
        f"SERVER={settings.db_host},{settings.db_port};"
        f"DATABASE={settings.db_name};"
        f"UID={settings.db_user};"
        f"PWD={settings.db_password};"
        f"Encrypt={settings.db_encrypt};"
        f"TrustServerCertificate={settings.db_trust_cert};"
    )


def get_connection() -> pyodbc.Connection:
    settings = get_settings()
    connection_string = _build_connection_string()

    try:
        return pyodbc.connect(connection_string, timeout=10)
    except pyodbc.Error as exc:
        message = str(exc).lower()
        fallback_drivers = ("ODBC Driver 17 for SQL Server", "SQL Server")
        should_retry_driver_17 = (
            "encryption not supported" in message
            or "ssl provider" in message
            or "security package" in message
        )

        if should_retry_driver_17:
            for fallback_driver in fallback_drivers:
                if settings.db_driver != fallback_driver and fallback_driver in pyodbc.drivers():
                    try:
                        return pyodbc.connect(_build_connection_string(fallback_driver), timeout=10)
                    except pyodbc.Error:
                        continue

        raise
