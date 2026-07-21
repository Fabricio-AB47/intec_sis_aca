from typing import Annotated
from datetime import datetime, timedelta, timezone

import jwt
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import (
    SessionProfile,
    SessionUser,
    clear_auth_cookie,
    create_session_token,
    get_current_user,
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


class LoginRequest(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    login: str
    nombres: str | None = None
    email: str | None = None
    id_usuario: int | None = None
    rol: str
    codigo_estud: int | None = None
    codigo_doc: int | None = None
    cedula: str | None = None
    perfiles: list[SessionProfile] = Field(default_factory=list)


class ProfileSelectionRequest(BaseModel):
    rol: str = Field(min_length=1)


def _build_ms_state(user: SessionUser, team_id: str | None = None) -> str:
    settings = get_settings()
    payload = {
        "login": user.login,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "team_id": team_id,
    }
    return str(jwt.encode(payload, settings.signing_secret, algorithm="HS256"))


def _decode_ms_state(state: str) -> tuple[str, str | None]:
    settings = get_settings()
    decoded = jwt.decode(state, settings.signing_secret, algorithms=["HS256"])
    login = str(decoded.get("login") or "").strip()
    if not login:
        raise ValueError("Estado Microsoft invalido")
    team_id_raw = str(decoded.get("team_id") or "").strip()
    team_id = team_id_raw if team_id_raw else None
    return login, team_id


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    try:
        user = SessionUser.model_validate(authenticate_user(payload.login, payload.password))
        token = create_session_token(user)
        set_auth_cookie(response, token)
        return LoginResponse(**user.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


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
def logout(response: Response) -> Response:
    clear_auth_cookie(response)
    response.delete_cookie("ms_delegate_access_token", path="/")
    response.delete_cookie("ms_delegate_exp", path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
