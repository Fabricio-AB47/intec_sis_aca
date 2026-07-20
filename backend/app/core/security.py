from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

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
ADMIN_PORTAL_ROLES = (
    "ADMINISTRADOR",
    "FINANCIERO",
    "BIENESTAR",
    "ACADEMICO",
    "ADMISIONES",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "INVITADO_SOP",
)
_HASHER = PasswordHasher() if PasswordHasher is not None else None
_JWT_ALGORITHM = "HS256"


class SessionUser(BaseModel):
    login: str
    nombres: str | None = None
    email: str | None = None
    id_usuario: int | None = None
    rol: str
    codigo_estud: int | None = None
    codigo_doc: int | None = None
    cedula: str | None = None


def verify_password(candidate: str, stored_value: str | None) -> bool:
    if stored_value is None:
        return False

    normalized = str(stored_value).strip()
    if not normalized:
        return False

    settings = get_settings()

    if _HASHER is None:
        return settings.auth_legacy_plaintext_enabled and candidate == normalized

    try:
        return _HASHER.verify(normalized, candidate)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        return settings.auth_legacy_plaintext_enabled and candidate == normalized


def hash_password(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("La contrasena no puede estar vacia")
    if _HASHER is None:
        return normalized
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
        "iat": issued_at,
        "exp": expires_at,
    }

    return jwt.encode(payload, settings.signing_secret, algorithm=_JWT_ALGORITHM)


def decode_session_token(token: str) -> SessionUser:
    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.signing_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion invalida o expirada",
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
    response.delete_cookie(settings.session_cookie_name, path="/")


def get_current_user(request: Request) -> SessionUser:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No hay una sesion activa",
        )

    user = decode_session_token(token)
    if user.rol not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol sin acceso a este portal",
        )

    return user


def require_roles(*roles: str) -> Callable[[SessionUser], SessionUser]:
    requested_roles = {role.upper() for role in roles}
    if {"ADMINISTRADOR", "ACADEMICO", "RECTOR"}.issubset(requested_roles):
        requested_roles.update(ADMIN_PORTAL_ROLES)
    allowed_roles = tuple(requested_roles)

    def dependency(
        current_user: SessionUser = Depends(get_current_user),
    ) -> SessionUser:
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta operacion",
            )
        return current_user

    return dependency
