from collections import deque
from collections.abc import Callable
from typing import Any

from app.core.security import SessionProfile, SessionUser, verify_password
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
    "SECRETARIA",
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
    "10": "SECRETARIA",
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
    "SECRETARIA": "SECRETARIA",
    "SECRETARIA ACADEMICA": "SECRETARIA",
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


def _normalize_status(value: Any) -> str:
    normalized = _clean(value).upper()
    return (
        normalized.replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
    )


def _student_access_allowed(correo_status: Any, academic_status: Any) -> bool:
    allowed_mail_statuses = {
        "A",
        "ACTIVO",
        "R",
        "RETIRADO",
        "I",
        "INACTIVO",
        "G",
        "GRADUADO",
    }
    excluded_academic_statuses = {
        "D",
        "E CONTINUA",
        "EDUCACION CONTINUA",
        "EDUCACION_CONTINUA",
    }
    return (
        _normalize_status(correo_status) in allowed_mail_statuses
        and _normalize_status(academic_status) not in excluded_academic_statuses
    )


def _authenticate_administrative_user(login_or_email: str, password: str | None) -> SessionUser | None:
    query = """
    SELECT TOP (50)
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
        [tp_us],
        TRY_CONVERT(nvarchar(100), [cedula]) AS cedula,
        TRY_CONVERT(nvarchar(100), tu.detalle_tipo_us) AS detalle_tipo_us
    FROM [dbo].[USUARIO_SIS]
    LEFT JOIN [dbo].[TIPO_USUARIO] tu
      ON TRY_CONVERT(int, tu.Codigo_tipo_us) = TRY_CONVERT(int, [tp_us])
    WHERE LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [login])))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [email])))) = LOWER(?)
       OR LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), [cedula]), N''))) = ?
    ORDER BY
        CASE
            WHEN LOWER(LTRIM(RTRIM(TRY_CONVERT(varchar(255), [login])))) = LOWER(?) THEN 0
            ELSE 1
        END
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (login_or_email, login_or_email, login_or_email, login_or_email))
        rows = cursor.fetchall()

    if not rows:
        return None

    authenticated_rows = [
        row for row in rows if password is None or verify_password(password, row.password)
    ]
    if not authenticated_rows:
        return None

    active_rows = [row for row in authenticated_rows if _is_active(row.estado)]
    if not active_rows:
        raise PermissionError('El usuario no está activo')

    typed_rows = [candidate for candidate in active_rows if _clean(candidate.tp_us)]
    if not typed_rows:
        raise PermissionError("Usuario administrativo sin tipo de usuario asignado")

    row = next(
        (candidate for candidate in typed_rows if _normalize_role(candidate.tp_us)),
        None,
    )
    if row is None:
        raise PermissionError('Tipo de usuario administrativo no válido')

    role = _normalize_role(row.tp_us)
    if not role:
        raise PermissionError('Tipo de usuario administrativo no válido')

    if role not in _ALLOWED_ROLES:
        raise PermissionError("Usuario sin acceso a este portal")

    return SessionUser(
        login=_clean(row.login),
        nombres=_clean(row.nombres) or None,
        email=_clean(row.email) or None,
        id_usuario=_int_or_none(row.id_usuarios),
        rol=role,
        cedula=_clean(row.cedula) or None,
        origen="USUARIO_SIS",
    )


def _authenticate_student(login_or_email: str, password: str | None) -> SessionUser | None:
    query = """
    SELECT TOP (100)
        TRY_CONVERT(int, de.codigo_estud) AS codigo_estud,
        TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS Cedula_Est,
        TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS Apellidos_nombre,
        TRY_CONVERT(nvarchar(255), de.correo) AS correo,
        TRY_CONVERT(nvarchar(255), de.correointec) AS correointec,
        TRY_CONVERT(nvarchar(100), de.Estado) AS Estado,
        TRY_CONVERT(nvarchar(255), ce.CorreoIntec) AS CorreoIntec,
        TRY_CONVERT(nvarchar(255), ce.CorreoPersonal) AS CorreoPersonal,
        TRY_CONVERT(nvarchar(255), ce.[Password]) AS CorreoPassword,
        TRY_CONVERT(nvarchar(100), ce.Estado) AS CorreoEstado
    FROM dbo.DATOS_ESTUD de
    INNER JOIN dbo.CorreosEstudIntec ce
      ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, de.codigo_estud)
    WHERE LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N'')))) = LOWER(?)
       OR LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoPersonal), N'')))) = LOWER(?)
       OR LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), de.Cedula_Est), N''))) = ?
    ORDER BY
        CASE
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N'')))) = LOWER(?) THEN 0
            WHEN LOWER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(255), ce.CorreoPersonal), N'')))) = LOWER(?) THEN 1
            ELSE 2
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
            ),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    authenticated_rows = [
        row for row in rows if password is None or verify_password(password, row.CorreoPassword)
    ]
    if not authenticated_rows:
        return None

    active_rows = [
        row
        for row in authenticated_rows
        if _student_access_allowed(row.CorreoEstado, row.Estado)
    ]
    if not active_rows:
        raise PermissionError(
            'El acceso estudiantil no está habilitado para educación continua, estado D o estados sin clasificar'
        )
    row = active_rows[0]

    return SessionUser(
        login=_clean(row.CorreoIntec) or login_or_email,
        nombres=_clean(row.Apellidos_nombre) or None,
        email=_clean(row.CorreoIntec) or _clean(row.correointec) or _clean(row.correo) or None,
        id_usuario=None,
        rol="ESTUDIANTE",
        codigo_estud=_int_or_none(row.codigo_estud),
        cedula=_clean(row.Cedula_Est) or None,
        origen="CorreosEstudIntec",
    )


def _authenticate_teacher(login_or_email: str, password: str | None) -> SessionUser | None:
    query = """
    SELECT TOP (50)
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
        rows = cursor.fetchall()

    if not rows:
        return None

    authenticated_rows = [
        row for row in rows if password is None or verify_password(password, row.password)
    ]
    if not authenticated_rows:
        return None

    active_rows = [row for row in authenticated_rows if _is_active(row.Estado)]
    if not active_rows:
        raise PermissionError('El usuario docente no está activo')
    row = active_rows[0]

    return SessionUser(
        login=_clean(row.login) or login_or_email,
        nombres=_clean(row.apellidos_nombre) or None,
        email=_clean(row.correo) or _clean(row.correop) or None,
        id_usuario=_int_or_none(row.Codigo_Usuario),
        rol="DOCENTE",
        codigo_doc=_int_or_none(row.codigo_doc),
        cedula=_clean(row.cedula_doc) or _clean(row.cedula_usuario) or None,
        origen="USUARIOS",
    )


def authenticate_user(login: str, password: str) -> dict[str, Any]:
    login_or_email = str(login or "").strip()
    if not login_or_email:
        raise ValueError('Credenciales inválidas')

    profiles: list[SessionProfile] = []
    permission_errors: list[PermissionError] = []
    resolvers: tuple[tuple[str, Callable[[str, str | None], SessionUser | None]], ...] = (
        ("USUARIO_SIS", _authenticate_administrative_user),
        ("ESTUDIANTE", _authenticate_student),
        ("DOCENTE", _authenticate_teacher),
    )
    resolved_sources: set[str] = set()
    resolver_cache: dict[tuple[str, str], SessionUser | None | PermissionError] = {}

    def resolve(
        source: str,
        resolver: Callable[[str, str | None], SessionUser | None],
        identifier: str,
    ) -> SessionUser | None:
        key = (source, identifier.casefold())
        cached = resolver_cache.get(key)
        if isinstance(cached, PermissionError):
            raise cached
        if key in resolver_cache:
            return cached
        try:
            user = resolver(identifier, password)
        except PermissionError as exc:
            resolver_cache[key] = exc
            raise
        resolver_cache[key] = user
        return user

    # Primero se valida la credencial contra los tres origenes oficiales.
    for source, resolver in resolvers:
        try:
            user = resolve(source, resolver, login_or_email)
        except PermissionError as exc:
            permission_errors.append(exc)
            continue
        if user is not None:
            resolved_sources.add(source)
            profile = SessionProfile.model_validate(user.model_dump())
            if not any(existing.rol == profile.rol for existing in profiles):
                profiles.append(profile)

    if profiles:
        # Una vez comprobada la identidad, se resuelven sus otros perfiles por
        # correo/login institucional o cedula. El rol sigue dependiendo de que
        # exista un registro activo en su tabla de origen.
        pending_identifiers: deque[str] = deque([login_or_email])
        for profile in profiles:
            pending_identifiers.extend(filter(None, (profile.login, profile.email, profile.cedula)))
        checked_identifiers: set[str] = set()

        while pending_identifiers and len(resolved_sources) < len(resolvers):
            identifier = pending_identifiers.popleft().strip()
            identifier_key = identifier.casefold()
            if not identifier or identifier_key in checked_identifiers:
                continue
            checked_identifiers.add(identifier_key)

            for source, resolver in resolvers:
                if source in resolved_sources:
                    continue
                try:
                    user = resolve(source, resolver, identifier)
                except PermissionError as exc:
                    permission_errors.append(exc)
                    continue
                if user is None:
                    continue
                resolved_sources.add(source)
                profile = SessionProfile.model_validate(user.model_dump())
                if any(existing.rol == profile.rol for existing in profiles):
                    continue
                profiles.append(profile)
                for value in (profile.login, profile.email, profile.cedula):
                    normalized = _clean(value)
                    if normalized and normalized.casefold() not in checked_identifiers:
                        pending_identifiers.append(normalized)

    if profiles:
        primary = profiles[0]
        return SessionUser(**primary.model_dump(), perfiles=profiles).model_dump()

    if permission_errors:
        raise permission_errors[0]

    raise ValueError('Credenciales inválidas')
