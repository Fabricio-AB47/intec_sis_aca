import pyodbc

from app.core.config import get_settings


def _build_connection_string(
    *,
    database: str,
    user: str,
    password: str,
    host: str,
    port: int,
    driver: str,
    encrypt: str,
    trust_cert: str,
) -> str:
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
    )


def _connect_with_fallback(
    *,
    database: str,
    user: str,
    password: str,
    host: str,
    port: int,
    driver: str,
    encrypt: str,
    trust_cert: str,
) -> pyodbc.Connection:
    connection_string = _build_connection_string(
        database=database,
        user=user,
        password=password,
        host=host,
        port=port,
        driver=driver,
        encrypt=encrypt,
        trust_cert=trust_cert,
    )

    try:
        return pyodbc.connect(connection_string, timeout=10)
    except pyodbc.Error as exc:
        message = str(exc).lower()
        fallback_drivers = ("ODBC Driver 17 for SQL Server", "SQL Server")
        should_retry_driver_17 = (
            "encryption not supported" in message
            or "ssl provider" in message
            or "security package" in message
            or "data source name not found" in message
            or "no se encuentra el nombre del origen de datos" in message
            or "can't open lib" in message
            or "driver" in message and "not found" in message
        )

        if should_retry_driver_17:
            for fallback_driver in fallback_drivers:
                if driver != fallback_driver and fallback_driver in pyodbc.drivers():
                    try:
                        return pyodbc.connect(
                            _build_connection_string(
                                database=database,
                                user=user,
                                password=password,
                                host=host,
                                port=port,
                                driver=fallback_driver,
                                encrypt=encrypt,
                                trust_cert=trust_cert,
                            ),
                            timeout=10,
                        )
                    except pyodbc.Error:
                        continue

        raise


def get_connection() -> pyodbc.Connection:
    settings = get_settings()
    return _connect_with_fallback(
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        driver=settings.db_driver,
        encrypt=settings.db_encrypt,
        trust_cert=settings.db_trust_cert,
    )


def get_evaluation_connection() -> pyodbc.Connection:
    settings = get_settings()
    missing = [
        name
        for name, value in {
            "B_NAME1/DB_NAME1": settings.eval_db_name,
            "DB_USER1": settings.eval_db_user,
            "DB_PASSWORD1": settings.eval_db_password,
            "DB_HOST1": settings.eval_db_host,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno para evaluacion 360: {', '.join(missing)}")

    return _connect_with_fallback(
        database=settings.eval_db_name or "",
        user=settings.eval_db_user or "",
        password=settings.eval_db_password or "",
        host=settings.eval_db_host or "",
        port=settings.eval_db_port,
        driver=settings.eval_db_driver or settings.db_driver,
        encrypt=settings.eval_db_encrypt or settings.db_encrypt,
        trust_cert=settings.eval_db_trust_cert or settings.db_trust_cert,
    )
