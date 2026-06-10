from typing import Any

from app.core.security import SessionUser, verify_password
from app.services.db import get_connection

_ALLOWED_ROLES = {
    "ADMINISTRADOR",
    "FINANCIERO",
    "BIENESTAR",
    "ACADEMICO",
    "ADMISIONES",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "INVITADO_SOP",
    "DOCENTE",
    "ESTUDIANTE",
}
_TP_US_CATALOG = {
    "1": "ADMINISTRADOR",
    "2": "FINANCIERO",
    "3": "BIENESTAR",
    "4": "ACADEMICO",
    "5": "ADMISIONES",
    "6": "RECTOR",
    "7": "VICERRECTOR",
    "8": "SOPORTE",
    "9": "INVITADO_SOP",
}

_ROLE_ALIASES = {
    **_TP_US_CATALOG,
    "ADM": "ADMINISTRADOR",
    "ACA": "ACADEMICO",
    "REC": "RECTOR",
    "ACADEMICO": "ACADEMICO",
    "ACADEMICA": "ACADEMICO",
    "ADMIN": "ADMINISTRADOR",
    "ADMINISTRADOR": "ADMINISTRADOR",
    "ADMISION": "ADMISIONES",
    "ADMISIONES": "ADMISIONES",
    "BIENESTAR": "BIENESTAR",
    "FIN": "FINANCIERO",
    "FINANCIERO": "FINANCIERO",
    "INVITADO": "INVITADO_SOP",
    "INVITADO SOP": "INVITADO_SOP",
    "INVITADO_SOP": "INVITADO_SOP",
    "RECTOR": "RECTOR",
    "SOPORTE": "SOPORTE",
    "TECNOLOGIA": "SOPORTE",
    "TI": "SOPORTE",
    "VICERRECTOR": "VICERRECTOR",
}


def _normalize_role(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().upper().replace("Á", "A").replace("É", "E")
    normalized = normalized.replace("Í", "I").replace("Ó", "O").replace("Ú", "U")

    if normalized in _ROLE_ALIASES:
        return _ROLE_ALIASES[normalized]
    if normalized in _ALLOWED_ROLES:
        return normalized
    return None


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_active(value: Any) -> bool:
    return _clean(value).upper() in {"1", "ACTIVO", "A", "TRUE", "SI"}


def _password_matches(candidate: str, *stored_values: Any) -> bool:
    return any(verify_password(candidate, _clean(value)) for value in stored_values if _clean(value))


def _authenticate_administrative_user(login_or_email: str, password: str) -> SessionUser | None:
    query = """
    SELECT TOP (1)
        [login],
        [password],
        [nombres],
        [fecha_ingreso],
        [id_usuarios],
        [estado],
        [email],
        [coordcarrera],
        [codprovincia],
        [tipousuario],
        [tp_us]
    FROM [dbo].[USUARIO_SIS]
    WHERE LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [login])))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [email])))) = LOWER(?)
    ORDER BY
        CASE
            WHEN LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [login])))) = LOWER(?) THEN 0
            ELSE 1
        END
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (login_or_email, login_or_email, login_or_email))
        row = cursor.fetchone()

    if not row:
        return None

    if not verify_password(password, row.password):
        return None

    if not _is_active(row.estado):
        raise PermissionError("El usuario no esta activo")

    role = _normalize_role(row.tp_us) or _normalize_role(row.tipousuario)
    if not role:
        raise PermissionError("Usuario sin rol valido")

    if role not in _ALLOWED_ROLES:
        raise PermissionError("Usuario sin acceso a este portal")

    return SessionUser(
        login=_clean(row.login),
        nombres=_clean(row.nombres) or None,
        email=_clean(row.email) or None,
        id_usuario=_int_or_none(row.id_usuarios),
        rol=role,
    )


def _authenticate_student(login_or_email: str, password: str) -> SessionUser | None:
    query = """
    SELECT TOP (1)
        TRY_CONVERT(int, de.codigo_estud) AS codigo_estud,
        TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS Cedula_Est,
        TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS Apellidos_nombre,
        TRY_CONVERT(nvarchar(255), de.correo) AS correo,
        TRY_CONVERT(nvarchar(255), de.correointec) AS correointec,
        TRY_CONVERT(nvarchar(255), de.clave) AS clave,
        TRY_CONVERT(nvarchar(100), de.Estado) AS Estado,
        TRY_CONVERT(nvarchar(255), ce.CorreoIntec) AS CorreoIntec,
        TRY_CONVERT(nvarchar(255), ce.CorreoPersonal) AS CorreoPersonal,
        TRY_CONVERT(nvarchar(255), ce.[Password]) AS CorreoPassword,
        TRY_CONVERT(int, u.Codigo_Usuario) AS Codigo_Usuario,
        TRY_CONVERT(nvarchar(255), u.login) AS usuario_login,
        TRY_CONVERT(nvarchar(255), u.[password]) AS usuario_password
    FROM dbo.DATOS_ESTUD de
    LEFT JOIN dbo.CorreosEstudIntec ce
      ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, de.codigo_estud)
    LEFT JOIN dbo.USUARIOS u
      ON TRY_CONVERT(nvarchar(100), u.cedula) COLLATE SQL_Latin1_General_CP1_CI_AS =
         TRY_CONVERT(nvarchar(100), de.Cedula_Est) COLLATE SQL_Latin1_General_CP1_CI_AS
     AND TRY_CONVERT(int, u.tipo_usuario) = 1
    WHERE LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N'')))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), de.correointec), N'')))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), de.correo), N'')))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), u.login), N'')))) = LOWER(?)
       OR LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), de.Cedula_Est), N''))) = ?
    ORDER BY
        CASE
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N'')))) = LOWER(?) THEN 0
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), de.correointec), N'')))) = LOWER(?) THEN 1
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), u.login), N'')))) = LOWER(?) THEN 2
            ELSE 3
        END
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
            ),
        )
        row = cursor.fetchone()

    if not row:
        return None

    if not _password_matches(password, row.CorreoPassword, row.clave, row.usuario_password):
        return None

    return SessionUser(
        login=_clean(row.CorreoIntec) or _clean(row.correointec) or _clean(row.usuario_login) or login_or_email,
        nombres=_clean(row.Apellidos_nombre) or None,
        email=_clean(row.CorreoIntec) or _clean(row.correointec) or _clean(row.correo) or None,
        id_usuario=_int_or_none(row.Codigo_Usuario),
        rol="ESTUDIANTE",
        codigo_estud=_int_or_none(row.codigo_estud),
        cedula=_clean(row.Cedula_Est) or None,
    )


def _authenticate_teacher(login_or_email: str, password: str) -> SessionUser | None:
    query = """
    SELECT TOP (1)
        TRY_CONVERT(int, d.codigo_doc) AS codigo_doc,
        TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula_doc,
        TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) AS apellidos_nombre,
        TRY_CONVERT(nvarchar(255), d.correo) AS correo,
        TRY_CONVERT(nvarchar(255), d.correop) AS correop,
        TRY_CONVERT(int, u.Codigo_Usuario) AS Codigo_Usuario,
        TRY_CONVERT(nvarchar(100), u.cedula) AS cedula_usuario,
        TRY_CONVERT(nvarchar(255), u.login) AS login,
        TRY_CONVERT(nvarchar(255), u.[password]) AS [password],
        TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
        TRY_CONVERT(nvarchar(100), u.tipo_usuario) AS tipo_usuario
    FROM dbo.USUARIOS u
    INNER JOIN dbo.DATOSDOCENTE d
      ON TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, u.Codigo_Usuario)
      OR TRY_CONVERT(nvarchar(100), d.cedula_doc) COLLATE SQL_Latin1_General_CP1_CI_AS =
         TRY_CONVERT(nvarchar(100), u.cedula) COLLATE SQL_Latin1_General_CP1_CI_AS
    WHERE (
            LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), u.login), N'')))) = LOWER(?)
         OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), d.correo), N'')))) = LOWER(?)
         OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), d.correop), N'')))) = LOWER(?)
         OR LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), u.cedula), N''))) = ?
         OR LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), d.cedula_doc), N''))) = ?
          )
      AND COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1
    ORDER BY
        CASE
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), u.login), N'')))) = LOWER(?) THEN 0
            ELSE 1
        END
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
                login_or_email,
            ),
        )
        row = cursor.fetchone()

    if not row:
        return None

    if not verify_password(password, row.password):
        return None

    if not _is_active(row.Estado):
        raise PermissionError("El usuario docente no esta activo")

    return SessionUser(
        login=_clean(row.login) or login_or_email,
        nombres=_clean(row.apellidos_nombre) or None,
        email=_clean(row.correo) or _clean(row.correop) or None,
        id_usuario=_int_or_none(row.Codigo_Usuario),
        rol="DOCENTE",
        codigo_doc=_int_or_none(row.codigo_doc),
        cedula=_clean(row.cedula_doc) or _clean(row.cedula_usuario) or None,
    )


def authenticate_user(login: str, password: str) -> dict[str, Any]:
    login_or_email = str(login or "").strip()
    if not login_or_email:
        raise ValueError("Credenciales invalidas")

    for resolver in (
        _authenticate_administrative_user,
        _authenticate_student,
        _authenticate_teacher,
    ):
        user = resolver(login_or_email, password)
        if user is not None:
            return user.model_dump()

    raise ValueError("Credenciales invalidas")
