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
    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
    )
    if driver.strip().lower() != "sql server":
        connection_string += (
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust_cert};"
        )
    return connection_string


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
        return pyodbc.connect(connection_string, timeout=30)
    except pyodbc.Error as exc:
        message = str(exc).lower()
        is_login_timeout = (
            "login timeout" in message
            or "timeout error" in message
            or "unable to complete login process" in message
        )
        fallback_drivers = (
            ("SQL Server", "ODBC Driver 17 for SQL Server")
            if is_login_timeout
            else ("ODBC Driver 17 for SQL Server", "SQL Server")
        )
        should_retry_driver_17 = (
            is_login_timeout
            or "encryption not supported" in message
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
                            timeout=30,
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


def get_practices_connection() -> pyodbc.Connection:
    settings = get_settings()
    missing = [
        name
        for name, value in {
            "B_NAME2/DB_NAME2": settings.practices_db_name,
            "DB_USER2": settings.practices_db_user,
            "DB_PASSWORD2": settings.practices_db_password,
            "DB_HOST2": settings.practices_db_host,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno para Prácticas laborales y Servicio Comunitario: {', '.join(missing)}")

    return _connect_with_fallback(
        database=settings.practices_db_name or "",
        user=settings.practices_db_user or "",
        password=settings.practices_db_password or "",
        host=settings.practices_db_host or "",
        port=settings.practices_db_port,
        driver=settings.practices_db_driver or settings.db_driver,
        encrypt=settings.practices_db_encrypt or settings.db_encrypt,
        trust_cert=settings.practices_db_trust_cert or settings.db_trust_cert,
    )


def get_titulation_connection() -> pyodbc.Connection:
    settings = get_settings()
    missing = [
        name
        for name, value in {
            "B_NAME3/DB_NAME3": settings.titulation_db_name,
            "DB_USER3": settings.titulation_db_user,
            "DB_PASSWORD3": settings.titulation_db_password,
            "DB_HOST3": settings.titulation_db_host,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno para titulacion: {', '.join(missing)}")

    return _connect_with_fallback(
        database=settings.titulation_db_name or "",
        user=settings.titulation_db_user or "",
        password=settings.titulation_db_password or "",
        host=settings.titulation_db_host or "",
        port=settings.titulation_db_port,
        driver=settings.titulation_db_driver or settings.db_driver,
        encrypt=settings.titulation_db_encrypt or settings.db_encrypt,
        trust_cert=settings.titulation_db_trust_cert or settings.db_trust_cert,
    )


def get_teams_connection() -> pyodbc.Connection:
    settings = get_settings()
    user = settings.teams_db_user or settings.eval_db_user or settings.db_user
    password = settings.teams_db_password or settings.eval_db_password or settings.db_password
    host = settings.teams_db_host or settings.eval_db_host or settings.db_host
    port = settings.teams_db_port or settings.eval_db_port or settings.db_port
    driver = settings.teams_db_driver or settings.eval_db_driver or settings.db_driver
    encrypt = settings.teams_db_encrypt or settings.eval_db_encrypt or settings.db_encrypt
    trust_cert = settings.teams_db_trust_cert or settings.eval_db_trust_cert or settings.db_trust_cert
    missing = [
        name
        for name, value in {
            "B_NAME4/DB_NAME4/TEAMS_DB_NAME": settings.teams_db_name,
            "DB_USER4/TEAMS_DB_USER": user,
            "DB_PASSWORD4/TEAMS_DB_PASSWORD": password,
            "DB_HOST4/TEAMS_DB_HOST": host,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno para Teams: {', '.join(missing)}")

    return _connect_with_fallback(
        database=settings.teams_db_name,
        user=user or "",
        password=password or "",
        host=host or "",
        port=port,
        driver=driver,
        encrypt=encrypt,
        trust_cert=trust_cert,
    )
