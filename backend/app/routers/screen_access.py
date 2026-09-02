from typing import Annotated

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import SessionUser, get_current_user, require_roles
from app.services.screen_access import get_screen_access, normalize_role, save_screen_access


router = APIRouter(prefix="/api/auth/screen-access", tags=["screen-access"])
_ADMIN_ACCESS = require_roles("ADMINISTRADOR")


class ScreenAccessUpdateRequest(BaseModel):
    pages: list[str] = Field(default_factory=list)


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail='No se pudo sincronizar la asignación de pantallas con INTEC_INTEGRACION_CONTROL.',
    )


@router.get("")
def list_screen_access(
    current_user: Annotated[SessionUser, Depends(get_current_user)],
    include_all: bool = Query(default=False),
    refresh: Annotated[bool, Query()] = False,
) -> dict:
    if include_all and normalize_role(current_user.rol) != "ADMINISTRADOR":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador puede consultar la matriz completa de accesos.",
        )
    try:
        return get_screen_access(
            current_user.rol,
            include_all=include_all,
            force_refresh=refresh,
        )
    except (ValueError, RuntimeError, pyodbc.Error) as exc:
        raise _service_error(exc) from exc


@router.put("/{role_code}")
def update_screen_access(
    role_code: str,
    payload: ScreenAccessUpdateRequest,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict:
    try:
        return save_screen_access(role_code, payload.pages, updated_by=current_user.login)
    except (ValueError, RuntimeError, pyodbc.Error) as exc:
        raise _service_error(exc) from exc
