from typing import Annotated
from datetime import datetime, timedelta, timezone
import hashlib
from threading import Lock
from uuid import uuid4

import jwt
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import RateLimitExceeded, RateLimitUnavailable, rate_limiter
from app.core.security import (
    SessionProfile,
    SessionUser,
    clear_auth_cookie,
    create_session_token,
    get_current_user,
    revoke_session,
    set_auth_cookie,
)
from app.services.auth import authenticate_user
from app.services.graph import (
    build_delegate_auth_url,
    delegated_token_cookie_payload,
    delegated_token_available,
    exchange_delegate_code,
    hydrate_delegated_token_from_cookie,
    store_delegated_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_MS_STATE_LOCK = Lock()
_USED_MS_STATE_IDS: dict[str, float] = {}


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    login: str
    nombres: str | None = None
    email: str | None = None
    id_usuario: int | None = None
    rol: str
    codigo_estud: int | None = None
    codigo_doc: int | None = None
    cedula: str | None = None
    origen: str | None = None
    perfiles: list[SessionProfile] = Field(default_factory=list)


class ProfileSelectionRequest(BaseModel):
    rol: str = Field(min_length=1, max_length=64)


def _build_ms_state(user: SessionUser, team_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "login": user.login,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "typ": "microsoft_oauth_state",
        "jti": str(uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=10),
        "team_id": team_id,
    }
    return str(jwt.encode(payload, settings.signing_secret, algorithm="HS256"))


def _decode_ms_state(state: str) -> tuple[str, str | None]:
    settings = get_settings()
    decoded = jwt.decode(
        state,
        settings.signing_secret,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["iss", "aud", "jti", "iat", "nbf", "exp"]},
    )
    if decoded.get("typ") != "microsoft_oauth_state":
        raise ValueError('Estado Microsoft inválido')
    state_id = str(decoded.get("jti") or "").strip()
    expires_at = float(decoded.get("exp") or 0)
    now = datetime.now(timezone.utc).timestamp()
    with _MS_STATE_LOCK:
        expired = [key for key, expiry in _USED_MS_STATE_IDS.items() if expiry <= now]
        for key in expired:
            _USED_MS_STATE_IDS.pop(key, None)
        if not state_id or state_id in _USED_MS_STATE_IDS:
            raise ValueError('Estado Microsoft inválido o reutilizado')
        _USED_MS_STATE_IDS[state_id] = expires_at
    login = str(decoded.get("login") or "").strip()
    if not login:
        raise ValueError('Estado Microsoft inválido')
    team_id_raw = str(decoded.get("team_id") or "").strip()
    team_id = team_id_raw if team_id_raw else None
    return login, team_id


def _login_rate_keys(request: Request, login_value: str) -> tuple[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    normalized_login = login_value.strip().casefold()
    login_digest = hashlib.sha256(normalized_login.encode("utf-8")).hexdigest()
    return f"login-ip:{client_ip}", f"login-account:{login_digest}"


def _rate_limit_unavailable(exc: RateLimitUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="El control de acceso está temporalmente no disponible.",
    )


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    settings = get_settings()
    ip_key, account_key = _login_rate_keys(request, payload.login)
    try:
        rate_limiter.check(
            ip_key,
            limit=max(settings.login_rate_limit_attempts * 10, 25),
            window_seconds=settings.login_rate_limit_window_seconds,
        )
        rate_limiter.check(
            account_key,
            limit=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='Demasiados intentos de acceso. Intente nuevamente más tarde.',
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except RateLimitUnavailable as exc:
        raise _rate_limit_unavailable(exc) from exc

    try:
        user = SessionUser.model_validate(authenticate_user(payload.login, payload.password))
        rate_limiter.reset(account_key)
        token = create_session_token(user)
        set_auth_cookie(response, token)
        return LoginResponse(**user.model_dump())
    except (ValueError, PermissionError) as exc:
        try:
            rate_limiter.record_failure(
                ip_key,
                limit=max(settings.login_rate_limit_attempts * 10, 25),
                window_seconds=settings.login_rate_limit_window_seconds,
                lockout_seconds=settings.login_rate_limit_lockout_seconds,
            )
            rate_limiter.record_failure(
                account_key,
                limit=settings.login_rate_limit_attempts,
                window_seconds=settings.login_rate_limit_window_seconds,
                lockout_seconds=settings.login_rate_limit_lockout_seconds,
            )
        except RateLimitUnavailable as rate_exc:
            raise _rate_limit_unavailable(rate_exc) from rate_exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Usuario o contraseña inválidos.',
        ) from exc
    except RateLimitUnavailable as exc:
        raise _rate_limit_unavailable(exc) from exc
    except pyodbc.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No se pudo conectar a SQL Server para validar el usuario. "
                "Revisa que la base INTECBDD este activa y que DB_HOST/DB_DRIVER sean correctos."
            ),
        ) from exc


@router.get("/me")
def current_session(
    current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> LoginResponse:
    return LoginResponse(**current_user.model_dump())


@router.post("/select-profile")
def select_profile(
    payload: ProfileSelectionRequest,
    response: Response,
    current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> LoginResponse:
    requested_role = payload.rol.strip().upper()
    profiles = current_user.perfiles or [SessionProfile.model_validate(current_user.model_dump())]
    selected = next((profile for profile in profiles if profile.rol.upper() == requested_role), None)
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El perfil seleccionado no está disponible para esta cuenta.",
        )

    user = SessionUser(**selected.model_dump(), perfiles=profiles)
    revoke_session(current_user)
    set_auth_cookie(response, create_session_token(user))
    return LoginResponse(**user.model_dump())


@router.get("/microsoft/connect")
def microsoft_connect(
    current_user: Annotated[SessionUser, Depends(get_current_user)],
    team_id: str | None = None,
) -> RedirectResponse:
    state = _build_ms_state(current_user, team_id)
    auth_url = build_delegate_auth_url(state)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/microsoft/callback")
def microsoft_callback(code: str, state: str) -> RedirectResponse:
    settings = get_settings()
    try:
        login, team_id = _decode_ms_state(state)
        token_result = exchange_delegate_code(code)
        store_delegated_token(login, token_result)
        cookie_token, cookie_exp = delegated_token_cookie_payload(token_result)
        redirect_url = f"{settings.frontend_base_url}/?ms_connected=1&open_page=teams"
        if team_id:
            redirect_url += f"&auto_invite_team_id={team_id}"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="ms_delegate_access_token",
            value=cookie_token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key="ms_delegate_exp",
            value=str(cookie_exp),
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        return response
    except (ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Estado Microsoft inválido o expirado.') from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='No se pudo completar la conexión con Microsoft.',
        ) from exc


@router.get("/microsoft/status")
def microsoft_status(
    request: Request,
    current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> dict[str, bool | str]:
    hydrate_delegated_token_from_cookie(
        current_user.login,
        request.cookies.get("ms_delegate_access_token"),
        request.cookies.get("ms_delegate_exp"),
    )
    connected = delegated_token_available(current_user.login)
    return {"connected": connected, "login": current_user.login}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
) -> Response:
    settings = get_settings()
    current_user = getattr(request.state, "session_user", None)
    if isinstance(current_user, SessionUser):
        revoke_session(current_user)
    clear_auth_cookie(response)
    response.delete_cookie(
        "ms_delegate_access_token",
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        "ms_delegate_exp",
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
