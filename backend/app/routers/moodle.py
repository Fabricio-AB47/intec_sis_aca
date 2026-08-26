from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.core.audit_context import get_audit_context
from app.core.config import get_settings
from app.core.security import SessionUser, require_screen_access
from app.integrations.moodle.exceptions import (
    MoodleApiError,
    MoodleConfigurationError,
    MoodleConnectionError,
    MoodleCourseNotFoundError,
    MoodleDisabledError,
    MoodleFullScanDisabledError,
    MoodleFunctionNotAllowedError,
    MoodleInvalidResponseError,
    MoodleInstitutionalEmailNotFoundError,
    MoodleInstitutionalEmailValidationError,
    MoodleResultLimitExceededError,
    MoodleResourceNotFoundError,
    MoodleSectionNotFoundError,
    MoodleSectionUpdateError,
    MoodleTimeoutError,
    MoodleUserNotConfirmedError,
    MoodleUserNotFoundError,
    MoodleWriteDisabledError,
)
from app.services.moodle_read_service import MoodleReadService
from app.services.moodle_grade_alerts import MoodleGradeAlertService
from app.services.moodle_grade_sync import MoodleGradeSyncError, MoodleGradeSyncService

router = APIRouter(prefix="/api/moodle", tags=["moodle"])
_MOODLE_STATUS_ACCESS = require_screen_access("moodle/status")
_MOODLE_USERS_ACCESS = require_screen_access("moodle/users")
_MOODLE_COURSES_ACCESS = require_screen_access("moodle/courses")
_MOODLE_RESOURCES_ACCESS = require_screen_access("moodle/resources")
_MOODLE_GRADES_ACCESS = require_screen_access("moodle/grades")
_MOODLE_ALERTS_ACCESS = require_screen_access("moodle/alerts")


class MoodleUserStatusPayload(BaseModel):
    active: bool

    model_config = ConfigDict(extra="forbid")


class MoodleSectionVisibilityPayload(BaseModel):
    visible: bool

    model_config = ConfigDict(extra="forbid")


class MoodleSectionNamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=1333)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("El nombre de la sección es obligatorio")
        return clean_value


class MoodleGradeSelectionPayload(BaseModel):
    course_id: int = Field(ge=1)
    period_code: int | None = Field(default=None, ge=1)
    period_codes: list[int] = Field(default_factory=list, max_length=3)
    replace_existing: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_periods(self) -> "MoodleGradeSelectionPayload":
        values = ([self.period_code] if self.period_code is not None else []) + self.period_codes
        unique_codes = list(dict.fromkeys(values))
        if not unique_codes:
            raise ValueError("Seleccione al menos un período académico")
        if len(unique_codes) > 3:
            raise ValueError("Puede seleccionar un máximo de tres períodos académicos")
        self.period_codes = unique_codes
        return self


@lru_cache(maxsize=1)
def get_moodle_read_service() -> MoodleReadService:
    return MoodleReadService(get_settings())


@lru_cache(maxsize=1)
def get_moodle_grade_sync_service() -> MoodleGradeSyncService:
    return MoodleGradeSyncService(get_moodle_read_service(), get_settings())


@lru_cache(maxsize=1)
def get_moodle_grade_alert_service() -> MoodleGradeAlertService:
    return MoodleGradeAlertService(get_moodle_grade_sync_service())


def _raise_http_error(exc: Exception) -> None:
    request_id = get_audit_context().request_id
    headers = {"X-Request-ID": request_id} if request_id else None

    if isinstance(
        exc,
        (
            MoodleUserNotFoundError,
            MoodleCourseNotFoundError,
            MoodleResourceNotFoundError,
            MoodleSectionNotFoundError,
        ),
    ):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (MoodleSectionUpdateError, MoodleGradeSyncError)):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(
        exc,
        (MoodleInstitutionalEmailNotFoundError, MoodleUserNotConfirmedError),
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(
        exc,
        (
            MoodleConfigurationError,
            MoodleDisabledError,
            MoodleWriteDisabledError,
            MoodleInstitutionalEmailValidationError,
            MoodleFullScanDisabledError,
            MoodleResultLimitExceededError,
        ),
    ):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, MoodleTimeoutError):
        status_code = status.HTTP_504_GATEWAY_TIMEOUT
    elif isinstance(
        exc,
        (
            MoodleConnectionError,
            MoodleApiError,
            MoodleInvalidResponseError,
            MoodleFunctionNotAllowedError,
        ),
    ):
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        raise exc

    detail = str(exc).strip()[:500] or "La consulta de Moodle no pudo completarse"
    token = get_settings().moodle_token
    token_value = token.get_secret_value().strip() if token else ""
    if token_value:
        detail = detail.replace(token_value, "[credencial protegida]")

    raise HTTPException(status_code=status_code, detail=detail, headers=headers) from exc


@router.get("/status")
async def moodle_status(
    _request: Request,
    _user: SessionUser = Depends(_MOODLE_STATUS_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.get_status()
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/users")
async def moodle_users(
    _request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    email: Annotated[str | None, Query(max_length=254)] = None,
    state_filter: Annotated[
        Literal["all", "active", "suspended", "unconfirmed"],
        Query(alias="state"),
    ] = "all",
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_USERS_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.list_users(
            page=page,
            page_size=page_size,
            email=email,
            state=state_filter,
            refresh=refresh,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.patch("/users/{user_id}/status")
async def update_moodle_user_status(
    user_id: Annotated[int, Path(ge=1)],
    payload: MoodleUserStatusPayload,
    _request: Request,
    _user: SessionUser = Depends(_MOODLE_USERS_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.set_user_active(user_id, active=payload.active)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/courses")
async def moodle_courses(
    _request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[str | None, Query(max_length=200)] = None,
    visibility: Literal["all", "visible", "hidden"] = "all",
    category_id: Annotated[int | None, Query(ge=0)] = None,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_COURSES_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.list_courses(
            page=page,
            page_size=page_size,
            search=search,
            visibility=visibility,
            category_id=category_id,
            refresh=refresh,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/courses/{course_id}/resources")
async def moodle_course_resources(
    course_id: Annotated[int, Path(ge=1)],
    _request: Request,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_RESOURCES_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.get_course_resources(course_id, refresh=refresh)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/grades/catalog")
async def moodle_grade_catalog(
    _request: Request,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_GRADES_ACCESS),
    service: MoodleGradeSyncService = Depends(get_moodle_grade_sync_service),
):
    try:
        return await service.catalog(refresh=refresh)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/grades/alerts")
async def moodle_grade_alerts(
    _request: Request,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_ALERTS_ACCESS),
    service: MoodleGradeAlertService = Depends(get_moodle_grade_alert_service),
):
    try:
        return await service.list_alerts(_user, refresh=refresh)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/grades/courses/{course_id}/context")
async def moodle_grade_course_context(
    course_id: Annotated[int, Path(ge=1)],
    _request: Request,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_GRADES_ACCESS),
    service: MoodleGradeSyncService = Depends(get_moodle_grade_sync_service),
):
    try:
        return await service.course_context(course_id=course_id, refresh=refresh)
    except Exception as exc:
        _raise_http_error(exc)


@router.post("/grades/preview")
async def preview_moodle_grades(
    payload: MoodleGradeSelectionPayload,
    _request: Request,
    refresh: bool = False,
    _user: SessionUser = Depends(_MOODLE_GRADES_ACCESS),
    service: MoodleGradeSyncService = Depends(get_moodle_grade_sync_service),
):
    try:
        return await service.preview(
            course_id=payload.course_id,
            period_codes=payload.period_codes,
            refresh=refresh,
            replace_existing=payload.replace_existing,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.post("/grades/apply")
async def apply_moodle_grades(
    payload: MoodleGradeSelectionPayload,
    _request: Request,
    _user: SessionUser = Depends(_MOODLE_GRADES_ACCESS),
    service: MoodleGradeSyncService = Depends(get_moodle_grade_sync_service),
    alert_service: MoodleGradeAlertService = Depends(get_moodle_grade_alert_service),
):
    try:
        result = await service.apply(
            course_id=payload.course_id,
            period_codes=payload.period_codes,
            actor=_user.login,
            actor_id=_user.id_usuario,
            replace_existing=payload.replace_existing,
        )
        alert_service.invalidate_cache()
        return result
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/grades/history")
def moodle_grade_history(
    _request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _user: SessionUser = Depends(_MOODLE_GRADES_ACCESS),
    service: MoodleGradeSyncService = Depends(get_moodle_grade_sync_service),
):
    try:
        return service.history(limit=limit)
    except Exception as exc:
        _raise_http_error(exc)


@router.patch("/courses/{course_id}/sections/{section_id}/visibility")
async def update_moodle_section_visibility(
    course_id: Annotated[int, Path(ge=1)],
    section_id: Annotated[int, Path(ge=1)],
    payload: MoodleSectionVisibilityPayload,
    _request: Request,
    _user: SessionUser = Depends(_MOODLE_RESOURCES_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.set_section_visibility(
            course_id,
            section_id,
            visible=payload.visible,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.patch("/courses/{course_id}/sections/{section_id}/name")
async def update_moodle_section_name(
    course_id: Annotated[int, Path(ge=1)],
    section_id: Annotated[int, Path(ge=1)],
    payload: MoodleSectionNamePayload,
    _request: Request,
    _user: SessionUser = Depends(_MOODLE_RESOURCES_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    try:
        return await service.set_section_name(
            course_id,
            section_id,
            name=payload.name,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/courses/{course_id}/modules/{module_id}/files/{file_index}")
async def moodle_course_resource_file(
    course_id: Annotated[int, Path(ge=1)],
    module_id: Annotated[int, Path(ge=1)],
    file_index: Annotated[int, Path(ge=0)],
    _request: Request,
    disposition: Literal["inline", "attachment"] = "inline",
    _user: SessionUser = Depends(_MOODLE_RESOURCES_ACCESS),
    service: MoodleReadService = Depends(get_moodle_read_service),
):
    stream = None
    try:
        metadata, stream = await service.open_course_resource_file(
            course_id,
            module_id,
            file_index,
        )
        content = metadata["content"]
        filename = str(content.get("filename") or "recurso-moodle")
        media_type = str(
            content.get("mimetype")
            or stream.response.headers.get("content-type")
            or "application/octet-stream"
        ).split(";", 1)[0]
        headers = {
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}"
            ),
            "X-Content-Type-Options": "nosniff",
        }
        content_length = stream.response.headers.get("content-length", "").strip()
        if content_length.isdigit():
            headers["Content-Length"] = content_length
        return StreamingResponse(
            stream.response.aiter_bytes(),
            media_type=media_type,
            headers=headers,
            background=BackgroundTask(stream.close),
        )
    except Exception as exc:
        if stream is not None:
            await stream.close()
        _raise_http_error(exc)


__all__ = [
    "_MOODLE_ALERTS_ACCESS",
    "_MOODLE_COURSES_ACCESS",
    "_MOODLE_GRADES_ACCESS",
    "_MOODLE_RESOURCES_ACCESS",
    "_MOODLE_STATUS_ACCESS",
    "_MOODLE_USERS_ACCESS",
    "MoodleSectionNamePayload",
    "MoodleSectionVisibilityPayload",
    "MoodleGradeSelectionPayload",
    "get_moodle_grade_alert_service",
    "get_moodle_grade_sync_service",
    "get_moodle_read_service",
    "router",
]
