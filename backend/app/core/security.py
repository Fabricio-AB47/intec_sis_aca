from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
except ModuleNotFoundError:
    PasswordHasher = None  # type: ignore[assignment]

    class InvalidHashError(Exception):
        pass

    class VerifyMismatchError(Exception):
        pass

ALLOWED_ROLES = (
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
)
_HASHER = PasswordHasher() if PasswordHasher is not None else None
_JWT_ALGORITHM = "HS256"


class SessionProfile(BaseModel):
    login: str
    nombres: str | None = None
    email: str | None = None
    id_usuario: int | None = None
    rol: str
    codigo_estud: int | None = None
    codigo_doc: int | None = None
    cedula: str | None = None
    origen: str | None = None


class SessionUser(SessionProfile):
    perfiles: list[SessionProfile] = Field(default_factory=list)


def verify_password(candidate: str, stored_value: str | None) -> bool:
    if stored_value is None:
        return False

    normalized = str(stored_value).strip()
    if not normalized:
        return False

    settings = get_settings()

    if _HASHER is None:
        return False

    try:
        return _HASHER.verify(normalized, candidate)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        return settings.auth_legacy_plaintext_enabled and candidate == normalized


def hash_password(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError('La contraseña no puede estar vacía')
    if _HASHER is None:
        raise RuntimeError('Argon2 no está disponible para proteger la contraseña')
    return _HASHER.hash(normalized)


def create_session_token(user: SessionUser) -> str:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.session_expire_minutes)

    payload = {
        "sub": user.login,
        "login": user.login,
        "nombres": user.nombres,
        "email": user.email,
        "id_usuario": user.id_usuario,
        "rol": user.rol,
        "codigo_estud": user.codigo_estud,
        "codigo_doc": user.codigo_doc,
        "cedula": user.cedula,
        "origen": user.origen,
        "perfiles": [profile.model_dump() for profile in user.perfiles],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid4()),
        "nbf": issued_at,
        "typ": "session",
        "iat": issued_at,
        "exp": expires_at,
    }

    return jwt.encode(payload, settings.signing_secret, algorithm=_JWT_ALGORITHM)


def decode_session_token(token: str) -> SessionUser:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.signing_secret,
            algorithms=[_JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["sub", "iss", "aud", "jti", "iat", "nbf", "exp"],
            },
        )
        if payload.get("typ") != "session":
            raise jwt.InvalidTokenError("Tipo de token inválido")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Sesión inválida o expirada',
        ) from exc

    return SessionUser.model_validate(payload)


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    max_age = settings.session_expire_minutes * 60
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=max_age,
        expires=max_age,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def get_current_user(request: Request) -> SessionUser:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='No hay una sesión activa',
        )

    cached_user = getattr(request.state, "session_user", None)
    user = cached_user if isinstance(cached_user, SessionUser) else decode_session_token(token)
    if user.rol not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol sin acceso a este portal",
        )

    return user


def require_roles(*roles: str) -> Callable[[SessionUser], SessionUser]:
    requested_roles = {role.upper() for role in roles}
    allowed_roles = tuple(requested_roles)

    def dependency(
        current_user: SessionUser = Depends(get_current_user),
    ) -> SessionUser:
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='No tiene permisos para esta operación',
            )
        return current_user

    return dependency


def require_screen_access(page: str) -> Callable[[SessionUser], SessionUser]:
    from app.services.screen_access import (
        KNOWN_PAGES,
        ScreenAccessUnavailableError,
        role_has_screen_access,
    )

    page_code = str(page or "").strip()
    if page_code not in KNOWN_PAGES:
        raise ValueError(f"Pantalla no reconocida: {page_code or '(vacia)'}")

    def dependency(
        current_user: SessionUser = Depends(get_current_user),
    ) -> SessionUser:
        try:
            allowed = role_has_screen_access(current_user.rol, page_code)
        except ScreenAccessUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='No se pudo validar la asignación institucional de pantallas',
            ) from exc

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='No tiene asignada la pantalla requerida para esta operación',
            )
        return current_user

    return dependency
