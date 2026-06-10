import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Annotated, Any, cast

import httpx
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.security import SessionUser, require_roles
from app.routers.students import _MATRICULA_BASE_CTE, _validate_tipo
from app.services.db import get_connection
from app.services.graph import graph_get, graph_get_all, graph_patch, graph_post, graph_post_with_meta

router = APIRouter(prefix="/api/teams", tags=["teams"])

_TEAMS_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")
_EXAMPLE_START_HOUR = "6:00 PM"
_EXAMPLE_END_HOUR = "8:00 PM"
_UTC_OFFSET_SUFFIX = "+00:00"
_MEET_JOIN_URL_TOKEN = "teams.microsoft.com/l/meetup-join/"
_CHANNEL_ACTIVITY_ACTIVE_WINDOW_MINUTES = 120
_GRAPH_PARALLEL_WORKERS = 6
_CHANNEL_MESSAGES_LIMIT = 20
_MESSAGE_REPLIES_LIMIT = 30
_TEAM_READY_TIMEOUT_SECONDS = 180
_TEAM_MEMBER_RETRY_TIMEOUT_SECONDS = 180
_TEAM_CREATION_SLOT_TIMEOUT_SECONDS = 240
_GRAPH_TEAM_RETRY_STATUS_CODES = {404, 409, 429, 500, 502, 503, 504}
_TEAM_CREATION_LOCK = Lock()
_TEAM_CREATION_IN_PROGRESS: set[str] = set()
_ECUADOR_TIMEZONE_NAME = "America/Guayaquil"
_ECUADOR_TIMEZONE = timezone(timedelta(hours=-5), name="ECT")
_GRAPH_TIMEZONE_OFFSETS = {
    "UTC": timezone.utc,
    "Etc/UTC": timezone.utc,
    "America/Guayaquil": _ECUADOR_TIMEZONE,
    "SA Pacific Standard Time": _ECUADOR_TIMEZONE,
    "Eastern Standard Time": timezone(timedelta(hours=-5), name="EST"),
    "Central Standard Time": timezone(timedelta(hours=-6), name="CST"),
    "Mountain Standard Time": timezone(timedelta(hours=-7), name="MST"),
    "Pacific Standard Time": timezone(timedelta(hours=-8), name="PST"),
    "E. South America Standard Time": timezone(timedelta(hours=-3), name="BRT"),
    "Pacific SA Standard Time": timezone(timedelta(hours=-4), name="CLT"),
}


class TeamEnrollmentRequest(BaseModel):
    user_id: str
    team_id: str


class TeamManualEmailEnrollmentRequest(BaseModel):
    team_id: str
    emails: list[str] = Field(default_factory=list)


class TeamCreateClassroomRequest(BaseModel):
    display_name: str
    courses: list[str]
    teacher_user_ids: list[str]
    visibility: str = "private"
    description: str = ""


class TeamMassEnrollmentRequest(BaseModel):
    team_id: str
    tipo_matricula: str | None = None
    estado_codigo: str | None = "A"
    anio_periodo: int | None = None
    punto_matricula: str = "PRIMERA"
    codigo_periodo: str | None = None
    limit: int = Field(default=300, ge=1, le=2000)


class TeamEnrollmentGroupSearchRequest(BaseModel):
    codigo_periodo: str | None = None
    codigo_periodos: list[str] = Field(default_factory=list)
    cod_anio_basica: str | None = None
    paralelo: str | None = None
    paralelos: list[str] = Field(default_factory=list)
    materia_query: str | None = None
    materia_base_keys: list[str] = Field(default_factory=list)
    tipo_matricula: str | None = None
    anio_periodo: int | None = None
    limit: int = Field(default=100, ge=1, le=500)


class TeamEnrollmentFilterOptionsRequest(BaseModel):
    codigo_periodos: list[str] = Field(default_factory=list)
    cod_anio_basica: str | None = None
    paralelo: str | None = None
    paralelos: list[str] = Field(default_factory=list)
    anio_periodo: int | None = None


class TeamEnrollmentGroupIdentityItem(BaseModel):
    codigo_periodo: str
    cod_anio_basica: str
    paralelo: str
    materia_base_key: str
    anio_periodo: int | None = None


class TeamCreateAndEnrollRequest(TeamCreateClassroomRequest):
    codigo_periodo: str | None = None
    cod_anio_basica: str | None = None
    paralelo: str | None = None
    materia_base_key: str | None = None
    selected_student_codes: list[str] = Field(default_factory=list)
    anio_periodo: int | None = None
    group_items: list[TeamEnrollmentGroupIdentityItem] = Field(default_factory=list)


class TeamEnrollmentGroupStudentsRequest(BaseModel):
    codigo_periodo: str | None = None
    cod_anio_basica: str | None = None
    paralelo: str | None = None
    materia_base_key: str | None = None
    anio_periodo: int | None = None
    group_items: list[TeamEnrollmentGroupIdentityItem] = Field(default_factory=list)


class TeamEnrollmentSelectionRequest(BaseModel):
    team_id: str
    codigo_periodo: str | None = None
    cod_anio_basica: str | None = None
    paralelo: str | None = None
    materia_base_key: str | None = None
    selected_student_codes: list[str] = Field(default_factory=list)
    anio_periodo: int | None = None
    group_items: list[TeamEnrollmentGroupIdentityItem] = Field(default_factory=list)


class TeamIndividualStudentSearchRequest(BaseModel):
    codigo_periodo: str
    query: str = ""
    materia_query: str | None = None
    paralelo: str | None = None
    anio_periodo: int | None = None
    limit: int = Field(default=25, ge=1, le=100)


class TeamIndividualEnrollmentRequest(BaseModel):
    team_id: str
    codigo_periodo: str
    codigo_estud: str | None = None
    selected_student_codes: list[str] = Field(default_factory=list)
    materia_query: str | None = None
    paralelo: str | None = None
    anio_periodo: int | None = None


_TEAM_ENROLLMENT_BASE_CTE = """
WITH latest_correo_estud AS (
    SELECT
        c.*,
        ROW_NUMBER() OVER (
            PARTITION BY TRY_CONVERT(varchar(50), c.codestud)
            ORDER BY
                COALESCE(
                    TRY_CONVERT(datetime2, c.fecha, 121),
                    TRY_CONVERT(datetime2, c.fecha, 120),
                    TRY_CONVERT(datetime2, c.fecha, 103),
                    TRY_CONVERT(datetime2, c.fecha, 105),
                    TRY_CONVERT(datetime2, c.fecha),
                    CAST('1900-01-01' AS datetime2)
                ) DESC,
                COALESCE(TRY_CONVERT(int, c.NumMigracion), -1) DESC
        ) AS rn_correo
    FROM [dbo].[CorreosEstudIntec] c
),
pensum_catalog AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY TRY_CONVERT(varchar(50), p.Cod_AnioBasica), TRY_CONVERT(varchar(50), p.codigo_materia)
            ORDER BY
                COALESCE(TRY_CONVERT(int, p.Orden), 2147483647) ASC,
                TRY_CONVERT(varchar(50), p.cod_materia) ASC
        ) AS rn_pensum
    FROM [dbo].[PENSUM] p
),
team_enrollment_base AS (
    SELECT
        TRY_CONVERT(varchar(50), cx.codigo_estud) AS codigo_estud,
        TRY_CONVERT(varchar(50), cx.cod_anio_Basica) AS cod_anio_basica,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(255), ca.Nombre_Basica))), ''),
            CONCAT('Carrera ', TRY_CONVERT(varchar(50), cx.cod_anio_Basica))
        ) AS nombre_carrera,
        TRY_CONVERT(varchar(50), cx.codigo_materia) AS codigo_materia,
        COALESCE(
            NULLIF(TRY_CONVERT(varchar(50), ps.cod_materia), ''),
            TRY_CONVERT(varchar(50), cx.codigo_materia)
        ) AS materia_base_key,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(255), ps.Nomb_Materia))), ''),
            CONCAT('Materia ', TRY_CONVERT(varchar(50), cx.codigo_materia))
        ) AS nombre_materia,
        TRY_CONVERT(varchar(50), cx.codigo_periodo) AS codigo_periodo,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.paralelo))), ''),
            NULLIF(NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.NumGrupo))), ''), '0')
        ) AS paralelo,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(255), pl.paralelo))), ''),
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.paralelo))), ''),
            NULLIF(NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.NumGrupo))), ''), '0')
        ) AS paralelo_nombre,
        TRY_CONVERT(varchar(50), cx.NumGrupo) AS num_grupo,
        TRY_CONVERT(int, pr.anio) AS anio_periodo,
        TRY_CONVERT(varchar(255), pr.Detalle_Periodo) AS detalle_periodo,
        TRY_CONVERT(varchar(100), pr.Periodo) AS periodo_nombre,
        TRY_CONVERT(varchar(10), pr.TipoMatricula) AS tipo_matricula,
        TRY_CONVERT(varchar(255), ce.CorreoIntec) AS correo_intec,
        TRY_CONVERT(varchar(255), ce.CorreoPersonal) AS correo_personal,
        TRY_CONVERT(varchar(255), ce.Nombres) AS nombre_estudiante,
        TRY_CONVERT(varchar(50), ce.Estado) AS estado_correo,
        TRY_CONVERT(varchar(255), ce.Descripcion) AS descripcion_correo,
        cx.Fecha_Matricula,
        ROW_NUMBER() OVER (
            PARTITION BY
                TRY_CONVERT(varchar(50), cx.codigo_estud),
                TRY_CONVERT(varchar(50), cx.cod_anio_Basica),
                TRY_CONVERT(varchar(50), cx.codigo_periodo),
                COALESCE(
                    NULLIF(TRY_CONVERT(varchar(50), ps.cod_materia), ''),
                    TRY_CONVERT(varchar(50), cx.codigo_materia)
                ),
                COALESCE(
                    NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.paralelo))), ''),
                    NULLIF(NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.NumGrupo))), ''), '0')
                )
            ORDER BY
                COALESCE(
                    TRY_CONVERT(datetime2, cx.Fecha_Matricula, 121),
                    TRY_CONVERT(datetime2, cx.Fecha_Matricula, 120),
                    TRY_CONVERT(datetime2, cx.Fecha_Matricula, 103),
                    TRY_CONVERT(datetime2, cx.Fecha_Matricula, 105),
                    TRY_CONVERT(datetime2, cx.Fecha_Matricula),
                    CAST('1900-01-01' AS datetime2)
                ) DESC,
                COALESCE(TRY_CONVERT(int, cx.Num_Matricula), -1) DESC,
                COALESCE(TRY_CONVERT(int, cx.Num_Reg_Mat), -1) DESC,
                COALESCE(TRY_CONVERT(int, cx.num), -1) DESC
        ) AS rn_student_group
    FROM [dbo].[CARRERAXESTUD] cx
    INNER JOIN [dbo].[PERIODO] pr
        ON TRY_CONVERT(varchar(50), pr.cod_periodo) = TRY_CONVERT(varchar(50), cx.codigo_periodo)
    LEFT JOIN [dbo].[CARRERAS] ca
        ON TRY_CONVERT(varchar(50), ca.Cod_AnioBasica) = TRY_CONVERT(varchar(50), cx.cod_anio_Basica)
    LEFT JOIN latest_correo_estud ce
        ON TRY_CONVERT(varchar(50), ce.codestud) = TRY_CONVERT(varchar(50), cx.codigo_estud)
       AND ce.rn_correo = 1
    LEFT JOIN pensum_catalog ps
        ON TRY_CONVERT(varchar(50), ps.Cod_AnioBasica) = TRY_CONVERT(varchar(50), cx.cod_anio_Basica)
       AND TRY_CONVERT(varchar(50), ps.codigo_materia) = TRY_CONVERT(varchar(50), cx.codigo_materia)
       AND ps.rn_pensum = 1
    LEFT JOIN [dbo].[PARALELOS] pl
        ON LTRIM(RTRIM(TRY_CONVERT(varchar(50), pl.num))) = LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.paralelo)))
        OR LTRIM(RTRIM(TRY_CONVERT(varchar(255), pl.paralelo))) = LTRIM(RTRIM(TRY_CONVERT(varchar(255), cx.paralelo)))
        OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), pl.num))) = LTRIM(RTRIM(TRY_CONVERT(varchar(50), cx.NumGrupo)))
    WHERE cx.codigo_estud IS NOT NULL
      AND cx.codigo_periodo IS NOT NULL
)
"""


def _resolve_graph_timezone(value: str | None):
    normalized = str(value or "").strip()
    if not normalized or normalized.upper() == "Z":
        return timezone.utc

    return _GRAPH_TIMEZONE_OFFSETS.get(normalized, timezone.utc)


def _parse_graph_datetime(value: Any, time_zone: str | None = None) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", _UTC_OFFSET_SUFFIX))
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=_resolve_graph_timezone(time_zone))
        return parsed
    except ValueError:
        return None


def _as_ecuador_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_ECUADOR_TIMEZONE)


def _ecuador_datetime_iso(value: Any, time_zone: str | None = None) -> str | None:
    parsed = _parse_graph_datetime(value, time_zone)
    if not parsed:
        return None
    return _as_ecuador_time(parsed).isoformat()


def _format_time_label(value: Any, time_zone: str | None = None) -> str | None:
    parsed = _parse_graph_datetime(value, time_zone)
    if not parsed:
        return None
    return _as_ecuador_time(parsed).strftime("%I:%M %p").lstrip("0")


def _format_datetime_label(value: Any, time_zone: str | None = None) -> str | None:
    parsed = _parse_graph_datetime(value, time_zone)
    if not parsed:
        return None
    return _as_ecuador_time(parsed).strftime("%d/%m/%Y %I:%M %p")


def _format_date_label(value: Any, time_zone: str | None = None) -> str | None:
    parsed = _parse_graph_datetime(value, time_zone)
    if not parsed:
        return None
    return _as_ecuador_time(parsed).strftime("%d/%m/%Y")


def _event_datetime_field(
    event: dict[str, Any],
    key: str,
) -> tuple[str | None, str | None, datetime | None]:
    value = event.get(key)
    payload = cast(dict[str, Any], value) if isinstance(value, dict) else {}
    raw_value = payload.get("dateTime")
    time_zone = str(payload.get("timeZone") or "").strip() or None
    raw = str(raw_value) if raw_value else None
    return raw, time_zone, _parse_graph_datetime(raw_value, time_zone)


def _format_duration_label(total_seconds: int | None) -> str | None:
    if total_seconds is None or total_seconds < 0:
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"


def _duration_seconds_from_item(file_item: dict[str, Any]) -> int | None:
    video_info = file_item.get("video")
    audio_info = file_item.get("audio")
    duration_value: Any = None

    if isinstance(video_info, dict):
        duration_value = cast(dict[str, Any], video_info).get("duration")
    if duration_value is None and isinstance(audio_info, dict):
        duration_value = cast(dict[str, Any], audio_info).get("duration")

    if duration_value is None:
        return None

    try:
        duration_number = float(duration_value)
    except (TypeError, ValueError):
        return None

    # Some payloads expose milliseconds; treat very large values as ms.
    if duration_number > 10_000:
        duration_number = duration_number / 1000.0

    duration_int = int(round(duration_number))
    return duration_int if duration_int >= 0 else None


def _recording_item_with_hours(file_item: dict[str, Any]) -> dict[str, Any]:
    start_time = file_item.get("createdDateTime") or file_item.get("lastModifiedDateTime")
    end_time = file_item.get("lastModifiedDateTime")

    duration_seconds = _duration_seconds_from_item(file_item)
    start_dt = _parse_graph_datetime(start_time)
    if duration_seconds is not None and start_dt:
        end_time = (start_dt + timedelta(seconds=duration_seconds)).isoformat()

    return {
        "id": file_item.get("id"),
        "name": file_item.get("name"),
        "webUrl": file_item.get("webUrl"),
        "startTime": start_time,
        "endTime": end_time,
        "startDateLabel": _format_date_label(start_time),
        "endDateLabel": _format_date_label(end_time),
        "startHourLabel": _format_time_label(start_time),
        "endHourLabel": _format_time_label(end_time),
        "durationSeconds": duration_seconds,
        "durationLabel": _format_duration_label(duration_seconds),
        "lastModifiedDateTime": file_item.get("lastModifiedDateTime"),
        "size": file_item.get("size"),
        "timeZone": _ECUADOR_TIMEZONE_NAME,
    }


def _is_recording_drive_item(file_item: dict[str, Any]) -> bool:
    if isinstance(file_item.get("folder"), dict) or isinstance(file_item.get("package"), dict):
        return False

    name = str(file_item.get("name") or "").strip()
    name_lower = name.lower()
    if not name_lower:
        return False

    excluded_extensions = (".vtt", ".srt", ".txt", ".doc", ".docx", ".pdf", ".html", ".url")
    if name_lower.endswith(excluded_extensions):
        return False

    file_info = file_item.get("file")
    mime_type = str(cast(dict[str, Any], file_info).get("mimeType") or "").lower() if isinstance(file_info, dict) else ""
    extension_match = re.search(r"\.([a-z0-9]+)$", name_lower)
    extension = extension_match.group(1) if extension_match else ""
    media_extensions = {"mp4", "m4v", "mov", "webm", "mkv", "m4a", "mp3", "wav"}
    has_media_facet = isinstance(file_item.get("video"), dict) or isinstance(file_item.get("audio"), dict)
    has_media_mime = mime_type.startswith("video/") or mime_type.startswith("audio/")
    has_media_extension = extension in media_extensions

    return has_media_facet or has_media_mime or has_media_extension


def _dedupe_recording_items(file_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recordings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for file_item in file_items:
        if not _is_recording_drive_item(file_item):
            continue

        item = _recording_item_with_hours(file_item)
        name_key = re.sub(r"\.[a-z0-9]+$", "", str(item.get("name") or "").strip().lower())
        key = "|".join(
            [
                name_key,
                str(item.get("startDateLabel") or ""),
                str(item.get("startHourLabel") or ""),
                str(item.get("durationLabel") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        recordings.append(item)

    recordings.sort(key=lambda item: str(item.get("startTime") or item.get("lastModifiedDateTime") or ""), reverse=True)
    return recordings


def _is_access_denied_error(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code != 403:
        return False
    detail = exc.response.text.lower()
    return "erroraccessdenied" in detail or "access is denied" in detail


def _graph_error_payload(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    try:
        payload = exc.response.json()
    except ValueError:
        return {}
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _graph_error_context(exc: httpx.HTTPStatusError) -> tuple[str, str, str]:
    payload = _graph_error_payload(exc)
    error_info = payload.get("error")
    error_payload = cast(dict[str, Any], error_info) if isinstance(error_info, dict) else {}
    inner_info = error_payload.get("innerError")
    inner_payload = cast(dict[str, Any], inner_info) if isinstance(inner_info, dict) else {}
    code = str(error_payload.get("code") or "").strip()
    message = str(error_payload.get("message") or exc.response.text or "").strip()
    request_id = str(
        inner_payload.get("request-id")
        or inner_payload.get("client-request-id")
        or exc.response.headers.get("request-id")
        or ""
    ).strip()
    return code, message, request_id


def _graph_error_detail(exc: httpx.HTTPStatusError) -> str:
    code, message, request_id = _graph_error_context(exc)
    if exc.response.status_code == 401 or code.lower() == "unauthorized":
        suffix = f" Request ID: {request_id}." if request_id else ""
        return (
            "Microsoft Graph no autorizo la consulta. "
            "Actualiza la conexion de Microsoft y revisa que la aplicacion tenga consentimiento "
            "para leer Teams/Canales/Mensajes."
            f"{suffix}"
        )

    if message and message != exc.response.text:
        suffix = f" Codigo Graph: {code}." if code else ""
        return f"{message}{suffix}"
    return exc.response.text


def _raise_graph_http_exception(exc: httpx.HTTPStatusError) -> None:
    status_code = 502 if exc.response.status_code == 401 else exc.response.status_code
    raise HTTPException(status_code=status_code, detail=_graph_error_detail(exc)) from exc


def _is_teamwork_migrate_forbidden(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code != 403:
        return False
    detail = exc.response.text.lower()
    return "teamwork.migrate.all" in detail


def _extract_participant_key(member: dict[str, Any]) -> str:
    mail = str(member.get("mail") or "").strip().lower()
    if mail:
        return mail
    upn = str(member.get("userPrincipalName") or "").strip().lower()
    if upn:
        return upn
    member_id = str(member.get("id") or "").strip().lower()
    return member_id


def _read_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _email_from_attendee(attendee: dict[str, Any]) -> str:
    email_info = attendee.get("emailAddress")
    if not isinstance(email_info, dict):
        return ""
    return _read_text(cast(dict[str, Any], email_info), "address").lower()


def _participants_from_attendees(attendees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    participants: list[dict[str, Any]] = []
    for attendee in attendees:
        email_info = attendee.get("emailAddress")
        status_info = attendee.get("status")
        email_payload = cast(dict[str, Any], email_info) if isinstance(email_info, dict) else {}
        status_payload = cast(dict[str, Any], status_info) if isinstance(status_info, dict) else {}

        participants.append(
            {
                "name": email_payload.get("name"),
                "address": email_payload.get("address"),
                "response": status_payload.get("response"),
                "time": status_payload.get("time"),
            }
        )

    return participants


def _event_window(event: dict[str, Any]) -> tuple[str | None, str | None, datetime | None, datetime | None]:
    start_raw, _, start_dt = _event_datetime_field(event, "start")
    end_raw, _, end_dt = _event_datetime_field(event, "end")
    return start_raw, end_raw, start_dt, end_dt


def _find_active_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    now_utc = datetime.now(timezone.utc)
    for event in events:
        _, _, start_dt, end_dt = _event_window(event)
        if start_dt and end_dt and start_dt <= now_utc <= end_dt:
            return event
    return None


def _calendar_view_url(team_id: str, minutes_range: int = 180) -> str:
    now_utc = datetime.now(timezone.utc)
    start = (now_utc - timedelta(minutes=minutes_range)).isoformat().replace(_UTC_OFFSET_SUFFIX, "Z")
    end = (now_utc + timedelta(minutes=minutes_range)).isoformat().replace(_UTC_OFFSET_SUFFIX, "Z")
    return (
        f"https://graph.microsoft.com/v1.0/groups/{team_id}/calendarView"
        f"?startDateTime={start}&endDateTime={end}"
    )


def _load_team_events(team_id: str) -> tuple[list[dict[str, Any]], str | None]:
    # Preferred source for ongoing meetings in a time window.
    try:
        calendar_payload = graph_get_all(
            _calendar_view_url(team_id)
            + "&$select=id,subject,start,end,attendees,onlineMeeting"
        )
        calendar_events = _graph_value_items(calendar_payload)
        if calendar_events:
            return calendar_events, "Llamada detectada por calendario del equipo."
    except httpx.HTTPStatusError as exc:
        if not _is_access_denied_error(exc):
            raise

    # Fallback source.
    try:
        events_payload = graph_get_all(
            f"https://graph.microsoft.com/v1.0/groups/{team_id}/events"
            "?$select=id,subject,start,end,attendees,onlineMeeting"
        )
        events = _graph_value_items(events_payload)
        if events:
            return events, "Llamada detectada por calendario del equipo."
        return events, None
    except httpx.HTTPStatusError as exc:
        if _is_access_denied_error(exc):
            return [], None
        raise


def _missing_participants_from_attendees(
    participants: list[dict[str, Any]],
    attendee_keys: set[str],
) -> list[dict[str, Any]]:
    missing_participants: list[dict[str, Any]] = []
    for member in participants:
        key = _extract_participant_key(member)
        if key and key not in attendee_keys:
            missing_participants.append(
                {
                    "id": member.get("id"),
                    "displayName": member.get("displayName"),
                    "mail": member.get("mail"),
                    "userPrincipalName": member.get("userPrincipalName"),
                }
            )
    return missing_participants


def _person_identity_key(person: dict[str, Any]) -> str:
    return (
        str(person.get("id") or "").strip()
        or str(person.get("mail") or "").strip().lower()
        or str(person.get("userPrincipalName") or "").strip().lower()
    )


def _load_team_members(team_id: str) -> list[dict[str, Any]]:
    members = _graph_value_items(
        graph_get_all(
            f"https://graph.microsoft.com/v1.0/groups/{team_id}/members"
            "?$select=id,displayName,mail,userPrincipalName"
        )
    )
    try:
        owners = _graph_value_items(
            graph_get_all(
                f"https://graph.microsoft.com/v1.0/groups/{team_id}/owners"
                "?$select=id,displayName,mail,userPrincipalName"
            )
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        owners = []

    people_by_key: dict[str, dict[str, Any]] = {}

    def upsert_person(person: dict[str, Any], role_key: str) -> None:
        person_key = _person_identity_key(person)
        if not person_key:
            return

        item = people_by_key.setdefault(
            person_key,
            {
                "id": person.get("id"),
                "displayName": person.get("displayName"),
                "mail": person.get("mail"),
                "userPrincipalName": person.get("userPrincipalName"),
                "isOwner": False,
                "isMember": False,
            },
        )
        item["displayName"] = item.get("displayName") or person.get("displayName")
        item["mail"] = item.get("mail") or person.get("mail")
        item["userPrincipalName"] = item.get("userPrincipalName") or person.get("userPrincipalName")
        if role_key == "owner":
            item["isOwner"] = True
        if role_key == "member":
            item["isMember"] = True

    for member in members:
        upsert_person(member, "member")
    for owner in owners:
        upsert_person(owner, "owner")

    items = sorted(
        people_by_key.values(),
        key=lambda item: (
            0 if item.get("isOwner") else 1,
            str(item.get("displayName") or item.get("mail") or item.get("userPrincipalName") or "").lower(),
        ),
    )
    for item in items:
        is_owner = bool(item.get("isOwner"))
        is_member = bool(item.get("isMember"))
        item["role"] = "owner_member" if is_owner and is_member else "owner" if is_owner else "member"
        item["roleLabel"] = (
            "Propietario y miembro"
            if is_owner and is_member
            else "Propietario"
            if is_owner
            else "Miembro"
        )

    return items


def _extract_join_url(value: str) -> str | None:
    match = re.search(r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+", value)
    if not match:
        return None
    return match.group(0)


def _is_meeting_signal(message: dict[str, Any]) -> tuple[bool, str | None]:
    body = message.get("body")
    body_content = cast(dict[str, Any], body).get("content") if isinstance(body, dict) else ""
    raw_text = str(body_content or "")
    normalized_text = _strip_html(raw_text).lower()
    join_url = _extract_join_url(raw_text)
    event_detail = str(message.get("eventDetail") or "").lower()

    has_signal = (
        (join_url is not None)
        or (_MEET_JOIN_URL_TOKEN in normalized_text)
        or ("reunirse ahora" in normalized_text)
        or ("join now" in normalized_text)
        or ("started a call" in normalized_text)
        or ("inicio una llamada" in normalized_text)
        or ("meeting" in event_detail)
        or ("call" in event_detail)
        or ("video" in event_detail)
    )
    return has_signal, join_url


def _detect_active_channel_meeting(team_id: str) -> dict[str, Any] | None:
    channels_payload = graph_get(
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels?$select=id,displayName"
    )
    channels = _graph_value_items(channels_payload)
    channels = channels[:8]
    if not channels:
        return None

    latest_created: datetime | None = None
    latest_message: dict[str, Any] | None = None
    latest_join_url: str | None = None
    latest_channel_id = ""
    latest_channel_name = ""

    for channel in channels:
        channel_id = str(channel.get("id") or "").strip()
        channel_name = str(channel.get("displayName") or "").strip()
        if not channel_id:
            continue

        messages_payload = graph_get(
            f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
        )
        messages = _graph_value_items(messages_payload)
        messages = messages[:12]

        for message in messages:
            created_dt = _parse_graph_datetime(message.get("createdDateTime"))
            if not created_dt:
                continue

            has_signal, join_url = _is_meeting_signal(message)
            if not has_signal:
                continue

            if latest_created is None or created_dt > latest_created:
                latest_created = created_dt
                latest_message = message
                latest_join_url = join_url
                latest_channel_id = channel_id
                latest_channel_name = channel_name

    if not latest_created or not latest_message:
        return None

    age_minutes = (datetime.now(timezone.utc) - latest_created).total_seconds() / 60.0
    if age_minutes > _CHANNEL_ACTIVITY_ACTIVE_WINDOW_MINUTES:
        return None

    return {
        "id": latest_message.get("id"),
        "topic": latest_message.get("subject") or "Reunirse ahora",
        "start": latest_message.get("createdDateTime"),
        "startLabel": _format_datetime_label(latest_message.get("createdDateTime")),
        "end": None,
        "endLabel": None,
        "joinWebUrl": latest_join_url,
        "channelId": latest_channel_id,
        "channelName": latest_channel_name or "General",
        "source": "channel-activity",
        "timeZone": _ECUADOR_TIMEZONE_NAME,
    }


def _resolve_team_call_status(team_id: str) -> dict[str, Any]:
    participants = _load_team_members(team_id)

    events, events_note = _load_team_events(team_id)

    active_event = _find_active_event(events)

    attendee_keys: set[str] = set()
    attendee_list = cast(list[dict[str, Any]], active_event.get("attendees")) if active_event and isinstance(active_event.get("attendees"), list) else []
    in_call_participants = _participants_from_attendees(attendee_list)

    for attendee in attendee_list:
        attendee_key = _email_from_attendee(attendee)
        if attendee_key:
            attendee_keys.add(attendee_key)

    active_meeting: dict[str, Any] | None = None
    if active_event:
        start_raw, start_tz, _ = _event_datetime_field(active_event, "start")
        end_raw, end_tz, _ = _event_datetime_field(active_event, "end")
        active_meeting = {
            "id": active_event.get("id"),
            "topic": active_event.get("subject"),
            "start": start_raw,
            "end": end_raw,
            "startLabel": _format_datetime_label(start_raw, start_tz),
            "endLabel": _format_datetime_label(end_raw, end_tz),
            "source": "calendar-event",
            "joinWebUrl": active_event.get("onlineMeeting", {}).get("joinUrl") if isinstance(active_event.get("onlineMeeting"), dict) else None,
            "timeZone": _ECUADOR_TIMEZONE_NAME,
        }

    if not active_meeting:
        active_meeting = _detect_active_channel_meeting(team_id)

    if active_meeting and str(active_meeting.get("source") or "") == "channel-activity":
        missing_participants = [
            {
                "id": member.get("id"),
                "displayName": member.get("displayName"),
                "mail": member.get("mail"),
                "userPrincipalName": member.get("userPrincipalName"),
            }
            for member in participants
        ]
    else:
        missing_participants = _missing_participants_from_attendees(participants, attendee_keys)

    result: dict[str, Any] = {
        "is_in_call": active_meeting is not None,
        "active_meeting": active_meeting,
        "participant_count": len(participants),
        "attendee_count": len(attendee_keys),
        "in_call_participants": in_call_participants,
        "missing_count": len(missing_participants),
        "missing_participants": missing_participants,
        "timeZone": _ECUADOR_TIMEZONE_NAME,
    }
    if active_meeting and str(active_meeting.get("source") or "") == "channel-activity":
        result["note"] = (
            "Llamada detectada por actividad reciente de canal. "
            "Microsoft Graph no expone participantes en vivo para este tipo de llamada; "
            "la invitacion masiva se enviara a todo el equipo para asegurar cobertura."
        )
    elif events_note:
        result["note"] = events_note
    return result


def _extract_invite_context(
    status_info: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    active_meeting = cast(dict[str, Any], status_info.get("active_meeting")) if isinstance(status_info.get("active_meeting"), dict) else None
    active_channel_id = str(active_meeting.get("channelId") or "").strip() if active_meeting else ""
    missing_participants = cast(list[dict[str, Any]], status_info.get("missing_participants") or [])
    return active_meeting, active_channel_id, missing_participants


def _message_sender_name(message: dict[str, Any]) -> str:
    sender_info = message.get("from")
    sender_payload = cast(dict[str, Any], sender_info) if isinstance(sender_info, dict) else {}
    for sender_key in ("user", "application", "device", "conversation"):
        sender_value = sender_payload.get(sender_key)
        if isinstance(sender_value, dict):
            display_name = str(cast(dict[str, Any], sender_value).get("displayName") or "").strip()
            if display_name:
                return display_name
            sender_id = str(cast(dict[str, Any], sender_value).get("id") or "").strip()
            if sender_id:
                return sender_id
    return "Sin remitente"


def _message_attachments_summary(message: dict[str, Any]) -> list[dict[str, Any]]:
    attachments_info = message.get("attachments")
    if not isinstance(attachments_info, list):
        return []

    items: list[dict[str, Any]] = []
    for attachment in cast(list[Any], attachments_info):
        if not isinstance(attachment, dict):
            continue
        attachment_payload = cast(dict[str, Any], attachment)
        items.append(
            {
                "id": attachment_payload.get("id"),
                "name": attachment_payload.get("name"),
                "contentType": attachment_payload.get("contentType"),
                "contentUrl": attachment_payload.get("contentUrl"),
            }
        )
    return items


def _message_reactions_summary(message: dict[str, Any]) -> list[dict[str, Any]]:
    reactions_info = message.get("reactions")
    if not isinstance(reactions_info, list):
        return []

    items: list[dict[str, Any]] = []
    for reaction in cast(list[Any], reactions_info):
        if not isinstance(reaction, dict):
            continue
        reaction_payload = cast(dict[str, Any], reaction)
        user_info = reaction_payload.get("user")
        user_payload = cast(dict[str, Any], user_info) if isinstance(user_info, dict) else {}
        items.append(
            {
                "reactionType": reaction_payload.get("reactionType"),
                "createdDateTime": reaction_payload.get("createdDateTime"),
                "userDisplayName": user_payload.get("displayName"),
                "userId": user_payload.get("id"),
            }
        )
    return items


def _message_event_detail_summary(message: dict[str, Any]) -> dict[str, Any] | None:
    event_detail = message.get("eventDetail")
    if not isinstance(event_detail, dict):
        return None

    payload = cast(dict[str, Any], event_detail)
    event_type = str(payload.get("@odata.type") or payload.get("eventType") or "").split(".")[-1]
    summary_values = [
        str(value or "").strip()
        for key, value in payload.items()
        if not key.startswith("@") and isinstance(value, (str, int, float, bool))
    ]
    return {
        "type": event_type or None,
        "text": " | ".join(value for value in summary_values if value),
        "raw": payload,
    }


def _message_combined_search_text(message: dict[str, Any]) -> str:
    body_info = message.get("body")
    body_content = cast(dict[str, Any], body_info).get("content") if isinstance(body_info, dict) else ""
    attachments = _message_attachments_summary(message)
    attachments_text = " ".join(
        " ".join(str(value or "") for value in attachment.values())
        for attachment in attachments
    )
    event_detail = message.get("eventDetail")
    event_detail_text = str(event_detail or "")
    if isinstance(event_detail, dict):
        event_detail_text = " ".join(str(value or "") for value in cast(dict[str, Any], event_detail).values())

    return _strip_html(
        " ".join(
            [
                str(message.get("subject") or ""),
                str(message.get("summary") or ""),
                str(message.get("messageType") or ""),
                str(message.get("importance") or ""),
                str(body_content or ""),
                attachments_text,
                event_detail_text,
            ]
        )
    )


def _graph_channel_message_item(
    channel_id: str,
    channel_name: str,
    message: dict[str, Any],
    parent_message_id: str | None = None,
    root_subject: str | None = None,
    root_created_datetime: str | None = None,
) -> dict[str, Any]:
    body_info = message.get("body")

    sender_name = _message_sender_name(message)
    body_content = cast(dict[str, Any], body_info).get("content") if isinstance(body_info, dict) else ""
    body_content_type = cast(dict[str, Any], body_info).get("contentType") if isinstance(body_info, dict) else None
    body_text = _strip_html(body_content)
    attachments = _message_attachments_summary(message)
    reactions = _message_reactions_summary(message)
    event_detail = _message_event_detail_summary(message)
    is_recording_related = _is_recording_channel_message(message)
    message_id = str(message.get("id") or "").strip()
    resolved_parent_id = str(parent_message_id or message.get("replyToId") or "").strip()
    is_reply = bool(resolved_parent_id)
    thread_subject = root_subject or str(message.get("subject") or body_text[:80] or "Mensaje de canal")

    return {
        "id": message_id or message.get("id"),
        "etag": message.get("etag"),
        "replyToId": message.get("replyToId"),
        "parentMessageId": resolved_parent_id or None,
        "rootMessageId": resolved_parent_id or message_id or None,
        "isReply": is_reply,
        "threadSubject": thread_subject,
        "threadCreatedDateTime": root_created_datetime or message.get("createdDateTime"),
        "channelId": channel_id,
        "channelName": channel_name,
        "messageType": message.get("messageType"),
        "importance": message.get("importance"),
        "locale": message.get("locale"),
        "webUrl": message.get("webUrl"),
        "createdDateTime": message.get("createdDateTime"),
        "createdDateTimeUtc": message.get("createdDateTime"),
        "createdDateTimeEcuador": _ecuador_datetime_iso(message.get("createdDateTime")),
        "lastModifiedDateTime": message.get("lastModifiedDateTime"),
        "lastModifiedDateTimeEcuador": _ecuador_datetime_iso(message.get("lastModifiedDateTime")),
        "deletedDateTime": message.get("deletedDateTime"),
        "createdDateLabel": _format_date_label(message.get("createdDateTime")),
        "createdHourLabel": _format_time_label(message.get("createdDateTime")),
        "createdDateTimeLabel": _format_datetime_label(message.get("createdDateTime")),
        "subject": message.get("subject"),
        "summary": message.get("summary"),
        "from": sender_name,
        "eventDetail": event_detail,
        "eventDetailType": event_detail.get("type") if event_detail else None,
        "eventDetailText": event_detail.get("text") if event_detail else None,
        "bodyContentType": body_content_type,
        "bodyText": body_text,
        "bodyPreview": body_text,
        "attachmentsCount": len(attachments),
        "attachments": attachments,
        "reactionsCount": len(reactions),
        "reactions": reactions,
        "replyCount": 0,
        "isRecordingRelated": is_recording_related,
        "activityType": "recording" if is_recording_related else "message",
        "activityLabel": "Mensaje de grabacion" if is_recording_related else "Mensaje de canal",
        "timeZone": _ECUADOR_TIMEZONE_NAME,
    }


def _is_recording_channel_message(message: dict[str, Any]) -> bool:
    combined_text = _message_combined_search_text(message).lower()
    if not combined_text:
        return False

    recording_terms = (
        "recording",
        "recorded",
        "record",
        "grabacion",
        "grabación",
        "grabado",
        "grabada",
        "grabar",
        "transcription",
        "transcripcion",
        "transcripción",
        "transcript",
        "meeting recap",
        "recap",
    )
    return any(term in combined_text for term in recording_terms)


def _load_channel_message_replies(team_id: str, channel_id: str, message_id: str) -> list[dict[str, Any]]:
    if not message_id:
        return []

    replies_url = (
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}"
        f"/messages/{message_id}/replies?$top={_MESSAGE_REPLIES_LIMIT}"
    )
    payload = graph_get_all(replies_url, max_items=_MESSAGE_REPLIES_LIMIT)
    return _graph_value_items(payload)


def _load_recent_channel_messages(
    team_id: str,
    channel: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]]]:
    channel_id = str(channel.get("id") or "").strip()
    channel_name = str(channel.get("displayName") or "Sin canal")
    if not channel_id:
        return "", channel_name, []

    messages_url = (
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}"
        f"/messages?$top={_CHANNEL_MESSAGES_LIMIT}"
    )
    payload = graph_get_all(messages_url, max_items=_CHANNEL_MESSAGES_LIMIT)
    return channel_id, channel_name, _graph_value_items(payload)


def _participant_contact(item: dict[str, Any]) -> str:
    return str(item.get("mail") or item.get("userPrincipalName") or "").strip().lower()


def _build_mass_invite_attendees(missing_participants: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    attendees: list[dict[str, Any]] = []
    names: list[str] = []
    seen_contacts: set[str] = set()

    for item in missing_participants:
        contact = _participant_contact(item)
        display_name = str(item.get("displayName") or item.get("mail") or item.get("userPrincipalName") or "").strip()
        if not contact or contact in seen_contacts:
            continue
        seen_contacts.add(contact)
        names.append(display_name or contact)
        attendees.append(
            {
                "emailAddress": {
                    "address": contact,
                    "name": display_name or contact,
                },
                "type": "required",
            }
        )

    return attendees, names


def _meeting_join_url(active_meeting: dict[str, Any] | None) -> str:
    return str((active_meeting or {}).get("joinWebUrl") or "").strip()


def _mass_invite_body_html(active_meeting: dict[str, Any] | None, names: list[str]) -> str:
    join_url = _meeting_join_url(active_meeting)
    names_text = "<br/>".join(f"- {name}" for name in names[:120])
    extra = f"<br/>... y {len(names) - 120} mas" if len(names) > 120 else ""
    source = str((active_meeting or {}).get("source") or "desconocido")

    return (
        "<p><strong>REPORTERIA_MASS_INVITE</strong></p>"
        "<p>Solicitud masiva para unirse a la llamada en curso.</p>"
        f"<p>Fuente detectada: {source}</p>"
        f"<p>{names_text}{extra}</p>"
        f"<p>Enlace de llamada: {join_url or 'No disponible'}</p>"
        "<p>Si ya estas dentro de la llamada, ignora este aviso.</p>"
    )


def _find_existing_mass_invite_event(team_id: str) -> dict[str, Any] | None:
    events_payload = graph_get_all(
        f"https://graph.microsoft.com/v1.0/groups/{team_id}/events"
        "?$select=id,subject,body,attendees,start,end"
    )
    events = _graph_value_items(events_payload)
    latest_event: dict[str, Any] | None = None
    latest_start: datetime | None = None

    for event in events:
        subject = str(event.get("subject") or "")
        body_info = event.get("body")
        body_content = str(cast(dict[str, Any], body_info).get("content") or "") if isinstance(body_info, dict) else ""
        if "REPORTERIA_MASS_INVITE" not in subject and "REPORTERIA_MASS_INVITE" not in body_content:
            continue

        _, _, start_dt = _event_datetime_field(event, "start")
        if start_dt is None:
            continue

        if latest_start is None or start_dt > latest_start:
            latest_start = start_dt
            latest_event = event

    return latest_event


def _resolve_team_owner_user_id(team_id: str) -> str | None:
    owners_payload = graph_get_all(
        f"https://graph.microsoft.com/v1.0/groups/{team_id}/owners"
        "?$select=id,mail,userPrincipalName"
    )
    owners = _graph_value_items(owners_payload)
    if not owners:
        return None
    owner = owners[0]
    return str(owner.get("id") or "").strip() or None


def _resolve_team_display_name(team_id: str) -> str:
    payload = graph_get(f"https://graph.microsoft.com/v1.0/groups/{team_id}?$select=displayName")
    display_name = str(payload.get("displayName") or "").strip()
    return display_name or team_id


def _find_existing_mass_invite_event_for_user(user_id: str) -> dict[str, Any] | None:
    events_payload = graph_get_all(
        f"https://graph.microsoft.com/v1.0/users/{user_id}/events"
        "?$select=id,subject,body,attendees,start,end"
    )
    events = _graph_value_items(events_payload)
    latest_event: dict[str, Any] | None = None
    latest_start: datetime | None = None

    for event in events:
        subject = str(event.get("subject") or "")
        body_info = event.get("body")
        body_content = str(cast(dict[str, Any], body_info).get("content") or "") if isinstance(body_info, dict) else ""
        if "REPORTERIA_MASS_INVITE" not in subject and "REPORTERIA_MASS_INVITE" not in body_content:
            continue

        _, _, start_dt = _event_datetime_field(event, "start")
        if start_dt is None:
            continue

        if latest_start is None or start_dt > latest_start:
            latest_start = start_dt
            latest_event = event

    return latest_event


def _iso_utc_now_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat().replace(_UTC_OFFSET_SUFFIX, "Z")


def _send_channel_join_request_massive(
    team_id: str,
    login: str,
    active_meeting: dict[str, Any] | None,
    active_channel_id: str,
    missing_participants: list[dict[str, Any]],
) -> dict[str, Any]:
    del login, active_channel_id
    attendees, names = _build_mass_invite_attendees(missing_participants)
    if not attendees:
        return {
            "ok": False,
            "message": "No se encontraron contactos validos para invitar en calendario.",
            "invited_count": 0,
        }

    now_start = _iso_utc_now_plus(0)
    now_end = _iso_utc_now_plus(30)
    team_display_name = _resolve_team_display_name(team_id)
    subject = team_display_name
    body_html = _mass_invite_body_html(active_meeting, names)

    update_payload: dict[str, Any] = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "start": {"dateTime": now_start, "timeZone": "UTC"},
        "end": {"dateTime": now_end, "timeZone": "UTC"},
        "attendees": attendees,
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }
    create_payload: dict[str, Any] = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "start": {"dateTime": now_start, "timeZone": "UTC"},
        "end": {"dateTime": now_end, "timeZone": "UTC"},
        "attendees": attendees,
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "location": {"displayName": "Microsoft Teams"},
    }

    try:
        existing_event = _find_existing_mass_invite_event(team_id)
        if existing_event and existing_event.get("id"):
            existing_attendees_raw = existing_event.get("attendees")
            existing_attendees = cast(list[dict[str, Any]], existing_attendees_raw) if isinstance(existing_attendees_raw, list) else []
            existing_addresses = {
                str(cast(dict[str, Any], attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
                for attendee in existing_attendees
            }
            merged_attendees = list(existing_attendees)
            for attendee in attendees:
                address = str(cast(dict[str, Any], attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
                if address and address not in existing_addresses:
                    existing_addresses.add(address)
                    merged_attendees.append(attendee)

            update_payload["attendees"] = merged_attendees
            graph_patch(f"https://graph.microsoft.com/v1.0/groups/{team_id}/events/{existing_event['id']}", update_payload)
            join_web_url = _meeting_join_url(active_meeting)
            return {
                "ok": True,
                "message": "Se actualizo el evento de invitacion masiva existente para la llamada en curso.",
                "invited_count": len(attendees),
                "event_id": existing_event["id"],
                "join_web_url": join_web_url,
                "request_type": "calendar-mass-invite-update",
            }

        created = graph_post(f"https://graph.microsoft.com/v1.0/groups/{team_id}/events", create_payload)
        created_online = created.get("onlineMeeting")
        created_join_web_url = (
            str(cast(dict[str, Any], created_online).get("joinUrl") or "").strip()
            if isinstance(created_online, dict)
            else ""
        )
        return {
            "ok": True,
            "message": "Se creo un evento de calendario para invitar masivamente a usuarios faltantes.",
            "invited_count": len(attendees),
            "event_id": created.get("id"),
            "join_web_url": created_join_web_url or _meeting_join_url(active_meeting),
            "request_type": "calendar-mass-invite-create",
        }
    except httpx.HTTPStatusError as exc:
        if not _is_access_denied_error(exc):
            raise

        owner_user_id = _resolve_team_owner_user_id(team_id)
        if not owner_user_id:
            raise

        owner_existing = _find_existing_mass_invite_event_for_user(owner_user_id)
        if owner_existing and owner_existing.get("id"):
            owner_existing_attendees_raw = owner_existing.get("attendees")
            owner_existing_attendees = cast(list[dict[str, Any]], owner_existing_attendees_raw) if isinstance(owner_existing_attendees_raw, list) else []
            owner_addresses = {
                str(cast(dict[str, Any], attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
                for attendee in owner_existing_attendees
            }
            owner_merged = list(owner_existing_attendees)
            for attendee in attendees:
                address = str(cast(dict[str, Any], attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
                if address and address not in owner_addresses:
                    owner_addresses.add(address)
                    owner_merged.append(attendee)

            update_payload["attendees"] = owner_merged
            graph_patch(f"https://graph.microsoft.com/v1.0/users/{owner_user_id}/events/{owner_existing['id']}", update_payload)
            join_web_url = _meeting_join_url(active_meeting)
            return {
                "ok": True,
                "message": "Se actualizo el evento de invitacion masiva en el calendario del propietario del Team.",
                "invited_count": len(attendees),
                "event_id": owner_existing["id"],
                "join_web_url": join_web_url,
                "request_type": "calendar-mass-invite-update-owner",
            }

        owner_created = graph_post(f"https://graph.microsoft.com/v1.0/users/{owner_user_id}/events", create_payload)
        owner_online = owner_created.get("onlineMeeting")
        owner_created_join_web_url = (
            str(cast(dict[str, Any], owner_online).get("joinUrl") or "").strip()
            if isinstance(owner_online, dict)
            else ""
        )
        return {
            "ok": True,
            "message": "Se creo el evento de invitacion masiva en el calendario del propietario del Team.",
            "invited_count": len(attendees),
            "event_id": owner_created.get("id"),
            "join_web_url": owner_created_join_web_url or _meeting_join_url(active_meeting),
            "request_type": "calendar-mass-invite-create-owner",
        }


def _invite_for_calendar_event(
    team_id: str,
    login: str,
    active_meeting: dict[str, Any],
    active_channel_id: str,
    missing_participants: list[dict[str, Any]],
) -> dict[str, Any]:
    return _send_channel_join_request_massive(team_id, login, active_meeting, active_channel_id, missing_participants)


def _invite_http_error_response(exc: httpx.HTTPStatusError, team_id: str) -> dict[str, Any] | None:
    if _is_access_denied_error(exc):
        del team_id
        return {
            "ok": False,
            "message": "No fue posible crear/editar el evento ni en calendario del grupo ni en calendario del propietario. Revisa Calendars.ReadWrite (Aplicacion), Group.ReadWrite.All y consentimiento de administrador.",
            "invited_count": 0,
        }

    if _is_teamwork_migrate_forbidden(exc):
        return {
            "ok": False,
            "message": (
                "No se pudo publicar en canal, pero ya se intentan invitaciones 1x1 por calendario con el buzón organizador."
            ),
            "invited_count": 0,
        }

    return None


def _strip_html(value: Any) -> str:
    text = str(value or "")
    no_tags = re.sub(r"<[^>]+>", " ", text)
    normalized = re.sub(r"\s+", " ", unescape(no_tags)).strip()
    return normalized


def _graph_value_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("value")
    if not isinstance(raw_items, list):
        return []

    typed_items: list[dict[str, Any]] = []
    for raw_item in cast(list[Any], raw_items):
        if isinstance(raw_item, dict):
            typed_items.append(cast(dict[str, Any], raw_item))
    return typed_items


def _normalize_graph_operation_url(operation_url: str) -> str:
    raw_url = str(operation_url or "").strip()
    if not raw_url:
        raise RuntimeError("Graph no devolvio URL de operacion para rastrear la creacion del Team")

    if raw_url.startswith(("http://", "https://")):
        return raw_url

    if raw_url.startswith(("/v1.0/", "/beta/")):
        return f"https://graph.microsoft.com{raw_url}"

    if raw_url.startswith("/"):
        return f"https://graph.microsoft.com/v1.0{raw_url}"

    if raw_url.startswith(("v1.0/", "beta/")):
        return f"https://graph.microsoft.com/{raw_url}"

    return f"https://graph.microsoft.com/v1.0/{raw_url.lstrip('/')}"


def _wait_for_team_creation(operation_url: str, timeout_seconds: int = 120) -> str:
    normalized_operation_url = _normalize_graph_operation_url(operation_url)
    started = time.time()

    while time.time() - started < timeout_seconds:
        operation = graph_get(normalized_operation_url)
        status = str(operation.get("status", "")).lower()

        if status == "succeeded":
            team_id = operation.get("targetResourceId")
            if not team_id:
                raise RuntimeError("Graph no devolvio targetResourceId para el Team creado")
            return str(team_id)

        if status == "failed":
            raise RuntimeError(f"Graph reporto fallo al crear Team: {operation}")

        time.sleep(2)

    raise RuntimeError("Timeout esperando la creacion del Team en Graph")


def _graph_retry_delay_seconds(attempt: int) -> float:
    return min(12.0, 2.0 + (attempt * 2.0))


def _graph_error_search_text(exc: httpx.HTTPStatusError) -> str:
    code, message, _request_id = _graph_error_context(exc)
    return f"{code} {message} {exc.response.text}".lower()


def _is_retryable_team_graph_error(exc: httpx.HTTPStatusError) -> bool:
    status_code = exc.response.status_code
    if status_code in (_GRAPH_TEAM_RETRY_STATUS_CODES - {404, 409}):
        return True

    if status_code == 404:
        return True

    if status_code in {400, 409}:
        detail = _graph_error_search_text(exc)
        return any(
            token in detail
            for token in (
                "notfound",
                "itemnotfound",
                "could not find resource",
                "not ready",
                "provision",
                "team not found",
                "conversation",
            )
        )

    return False


def _graph_post_with_meta_retry(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    attempt = 0
    last_error = ""

    while time.time() - started < _TEAM_MEMBER_RETRY_TIMEOUT_SECONDS:
        try:
            return graph_post_with_meta(url, payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {429, 500, 502, 503, 504}:
                raise

            last_error = _graph_error_detail(exc)
            attempt += 1
            time.sleep(_graph_retry_delay_seconds(attempt))

    raise RuntimeError(
        "No se pudo iniciar la creacion del Team porque Microsoft Graph no respondio de forma estable."
        + (f" Ultimo error Graph: {last_error}" if last_error else "")
    )


def _is_already_team_member_error(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code not in {400, 409}:
        return False

    detail = _graph_error_search_text(exc)
    return any(
        token in detail
        for token in (
            "already exist",
            "already exists",
            "already a conversation member",
            "one or more added object references already exist",
        )
    )


def _team_id_url_value(team_id: str) -> str:
    normalized = str(team_id or "").strip()
    if not normalized:
        raise RuntimeError("Graph no devolvio un id de Team valido")
    return quote(normalized, safe="")


def _normalize_team_display_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _reserve_team_creation_slot(display_name: str) -> str:
    creation_key = _normalize_team_display_name(display_name).lower()
    started = time.time()

    while time.time() - started < _TEAM_CREATION_SLOT_TIMEOUT_SECONDS:
        with _TEAM_CREATION_LOCK:
            if creation_key not in _TEAM_CREATION_IN_PROGRESS:
                _TEAM_CREATION_IN_PROGRESS.add(creation_key)
                return creation_key

        time.sleep(2)

    raise HTTPException(
        status_code=409,
        detail=(
            "Ya existe una creacion de Team en proceso con el mismo nombre. "
            "Espera a que termine y vuelve a intentar para evitar matricular en un aula incorrecta."
        ),
    )


def _release_team_creation_slot(creation_key: str) -> None:
    with _TEAM_CREATION_LOCK:
        _TEAM_CREATION_IN_PROGRESS.discard(creation_key)


def _team_resource_exists(team_id: str) -> bool:
    try:
        graph_get(f"https://graph.microsoft.com/v1.0/teams/{_team_id_url_value(team_id)}")
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return False
        raise


def _find_existing_teams_by_display_name(display_name: str) -> list[dict[str, Any]]:
    normalized_name = _normalize_team_display_name(display_name)
    escaped_name = normalized_name.replace("'", "''")
    encoded_filter = quote(f"displayName eq '{escaped_name}'", safe="'()")
    url = (
        "https://graph.microsoft.com/v1.0/groups"
        "?$top=25"
        "&$select=id,displayName,description,mail,webUrl,resourceProvisioningOptions"
        f"&$filter={encoded_filter}"
    )
    payload = graph_get_all(url, max_items=25)
    exact_matches: list[dict[str, Any]] = []

    for group in _graph_value_items(payload):
        group_name = _normalize_team_display_name(group.get("displayName"))
        if group_name.lower() != normalized_name.lower():
            continue

        group_id = str(group.get("id") or "").strip()
        if not group_id:
            continue

        raw_options = group.get("resourceProvisioningOptions")
        options = [str(option).lower() for option in raw_options] if isinstance(raw_options, list) else []
        if "team" in options or _team_resource_exists(group_id):
            exact_matches.append(group)

    return exact_matches


def _existing_classroom_team(display_name: str) -> dict[str, Any] | None:
    existing_teams = _find_existing_teams_by_display_name(display_name)
    if not existing_teams:
        return None

    if len(existing_teams) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Existen {len(existing_teams)} Teams con el nombre exacto '{display_name}'. "
                "Usa un nombre unico antes de matricular para evitar enviar estudiantes al Team incorrecto."
            ),
        )

    team = existing_teams[0]
    team_id = str(team.get("id") or "").strip()
    _wait_for_team_ready(team_id)
    return team


def _wait_for_team_ready(team_id: str, timeout_seconds: int = _TEAM_READY_TIMEOUT_SECONDS) -> dict[str, Any]:
    encoded_team_id = _team_id_url_value(team_id)
    started = time.time()
    attempt = 0
    last_error = ""

    while time.time() - started < timeout_seconds:
        try:
            group = graph_get(
                f"https://graph.microsoft.com/v1.0/groups/{encoded_team_id}"
                "?$select=id,displayName,description,mail,webUrl"
            )
            team = graph_get(f"https://graph.microsoft.com/v1.0/teams/{encoded_team_id}")
            graph_get_all(f"https://graph.microsoft.com/v1.0/teams/{encoded_team_id}/members?$top=1", max_items=1)
            return {"group": group, "team": team}
        except httpx.HTTPStatusError as exc:
            if not _is_retryable_team_graph_error(exc):
                raise

            last_error = _graph_error_detail(exc)
            attempt += 1
            time.sleep(_graph_retry_delay_seconds(attempt))

    suffix = f" Ultimo error: {last_error}" if last_error else ""
    raise RuntimeError(
        f"Timeout esperando que el Team '{team_id}' exista y acepte miembros en Microsoft Graph.{suffix}"
    )


@router.get("/catalog", responses={500: {"description": "Error interno del servidor"}})
def teams_catalog(
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    url = (
        "https://graph.microsoft.com/v1.0/groups"
        "?$filter=resourceProvisioningOptions/Any(x:x eq 'Team')"
        "&$select=id,displayName,description,mail,visibility,webUrl"
    )

    try:
        return graph_get_all(url)
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/by-user/{user_id}", responses={500: {"description": "Error interno del servidor"}})
def teams_by_user(
    user_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/joinedTeams"
    try:
        return graph_get(url)
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/participants", responses={500: {"description": "Error interno del servidor"}})
def teams_participants(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user

    try:
        items = _load_team_members(team_id)
        return {
            "value": items,
            "count": len(items),
            "member_count": sum(1 for item in items if item.get("isMember")),
            "owner_count": sum(1 for item in items if item.get("isOwner")),
        }
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/courses", responses={500: {"description": "Error interno del servidor"}})
def teams_courses(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels"

    try:
        payload = graph_get_all(url)
        channels = _graph_value_items(payload)
        items: list[dict[str, Any]] = [
            {
                "id": channel.get("id"),
                "displayName": channel.get("displayName"),
                "description": channel.get("description"),
                "membershipType": channel.get("membershipType"),
                "webUrl": channel.get("webUrl"),
            }
            for channel in channels
        ]
        return {"value": items, "count": len(items)}
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/recordings", responses={500: {"description": "Error interno del servidor"}})
def teams_recordings(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    url = f"https://graph.microsoft.com/v1.0/groups/{team_id}/drive/root/search(q='recording')"

    try:
        payload = graph_get_all(url)
        files = _graph_value_items(payload)
        items = _dedupe_recording_items(files)
        return {
            "value": items,
            "count": len(items),
            "raw_count": len(files),
            "timeZone": _ECUADOR_TIMEZONE_NAME,
            "example": {
                "startHourLabel": _EXAMPLE_START_HOUR,
                "endHourLabel": _EXAMPLE_END_HOUR,
                "text": "Ejemplo en hora de Ecuador: inicio 6:00 PM y fin 8:00 PM",
            },
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            fallback_url = (
                f"https://graph.microsoft.com/v1.0/groups/{team_id}/drive/root/children"
            )
            try:
                fallback_payload = graph_get_all(fallback_url)
                fallback_items = _graph_value_items(fallback_payload)
                recording_candidates = [
                    file_item
                    for file_item in fallback_items
                    if str(file_item.get("name", "")).strip().lower().find("record") >= 0
                    or str(file_item.get("name", "")).strip().lower().find("grab") >= 0
                ]
                recordings = _dedupe_recording_items(recording_candidates)
                return {
                    "value": recordings,
                    "count": len(recordings),
                    "raw_count": len(fallback_items),
                    "timeZone": _ECUADOR_TIMEZONE_NAME,
                    "example": {
                        "startHourLabel": _EXAMPLE_START_HOUR,
                        "endHourLabel": _EXAMPLE_END_HOUR,
                        "text": "Ejemplo en hora de Ecuador: inicio 6:00 PM y fin 8:00 PM",
                    },
                }
            except httpx.HTTPStatusError as fallback_exc:
                _raise_graph_http_exception(fallback_exc)
            except RuntimeError as fallback_exc:
                raise HTTPException(status_code=500, detail=str(fallback_exc)) from fallback_exc

        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/status", responses={500: {"description": "Error interno del servidor"}})
def teams_status(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user

    try:
        return _resolve_team_call_status(team_id)
    except httpx.HTTPStatusError as exc:
        if _is_access_denied_error(exc):
            return {
                "is_in_call": False,
                "active_meeting": None,
                "participant_count": 0,
                "attendee_count": 0,
                "missing_count": 0,
                "missing_participants": [],
                "timeZone": _ECUADOR_TIMEZONE_NAME,
                "note": "Graph devolvio AccessDenied para eventos del Team. Revisa permisos Group.Read.All/Calendars.Read.",
                "example": {
                    "startHourLabel": _EXAMPLE_START_HOUR,
                    "endHourLabel": _EXAMPLE_END_HOUR,
                    "text": "Ejemplo de horario en Ecuador: inicio 6:00 PM y fin 8:00 PM",
                },
            }
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{team_id}/call/invite-missing", responses={500: {"description": "Error interno del servidor"}})
def teams_invite_missing_to_call(
    team_id: str,
    request: Request,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    try:
        del request

        status_info = _resolve_team_call_status(team_id)
        active_meeting, active_channel_id, missing_participants = _extract_invite_context(status_info)

        if not missing_participants:
            return {
                "ok": True,
                "message": "Todos los participantes ya estan en la llamada/evento activo.",
                "invited_count": 0,
            }

        if not active_meeting or not active_meeting.get("id"):
            return {
                "ok": False,
                "message": "El equipo no tiene una llamada/evento activo en este momento.",
                "invited_count": 0,
            }

        return _invite_for_calendar_event(team_id, current_user.login, active_meeting, active_channel_id, missing_participants)
    except httpx.HTTPStatusError as exc:
        error_response = _invite_http_error_response(exc, team_id)
        if error_response is not None:
            return error_response
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/attendance", responses={500: {"description": "Error interno del servidor"}})
def teams_attendance(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    # Graph application permissions usually expose event attendees, not confirmed presence.
    url = (
        f"https://graph.microsoft.com/v1.0/groups/{team_id}/events"
    )

    try:
        payload = graph_get_all(url)
        events = _graph_value_items(payload)
        items: list[dict[str, Any]] = []
        for event in events:
            attendees_info = event.get("attendees")
            start, start_tz, _ = _event_datetime_field(event, "start")
            end, end_tz, _ = _event_datetime_field(event, "end")
            total_attendees = len(cast(list[Any], attendees_info)) if isinstance(attendees_info, list) else 0

            items.append(
                {
                    "id": event.get("id"),
                    "topic": event.get("subject"),
                    "start": start,
                    "end": end,
                    "startLabel": _format_datetime_label(start, start_tz),
                    "endLabel": _format_datetime_label(end, end_tz),
                    "totalAttendees": total_attendees,
                    "timeZone": _ECUADOR_TIMEZONE_NAME,
                }
            )
        return {
            "value": items,
            "count": len(items),
            "timeZone": _ECUADOR_TIMEZONE_NAME,
            "note": "Asistencia estimada por invitados de eventos del Team (no confirma presencia real).",
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return {
                "value": [],
                "count": 0,
                "timeZone": _ECUADOR_TIMEZONE_NAME,
                "note": "No hay permisos de Graph para eventos/asistencias en este tenant. Solicita Group.Read.All/Calendars.Read.",
            }
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{team_id}/messages", responses={500: {"description": "Error interno del servidor"}})
def teams_messages(
    team_id: str,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    channels_url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels"

    try:
        channels_payload = graph_get_all(channels_url)
        channels = _graph_value_items(channels_payload)
        messages: list[dict[str, Any]] = []
        raw_message_count = 0
        root_message_count = 0
        reply_message_count = 0
        channel_errors: list[dict[str, Any]] = []
        reply_errors: list[dict[str, Any]] = []
        root_entries: list[tuple[str, str, dict[str, Any]]] = []

        valid_channels = [channel for channel in channels if str(channel.get("id") or "").strip()]
        if valid_channels:
            workers = min(_GRAPH_PARALLEL_WORKERS, len(valid_channels))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_load_recent_channel_messages, team_id, channel): channel
                    for channel in valid_channels
                }
                for future in as_completed(futures):
                    channel = futures[future]
                    channel_id = str(channel.get("id") or "").strip()
                    channel_name = str(channel.get("displayName") or "Sin canal")
                    try:
                        loaded_channel_id, loaded_channel_name, message_items = future.result()
                    except httpx.HTTPStatusError as channel_exc:
                        channel_errors.append(
                            {
                                "channelId": channel_id,
                                "channelName": channel_name,
                                "status": channel_exc.response.status_code,
                                "detail": _graph_error_detail(channel_exc),
                            }
                        )
                        continue

                    channel_id = loaded_channel_id or channel_id
                    channel_name = loaded_channel_name or channel_name
                    raw_message_count += len(message_items)
                    root_message_count += len(message_items)
                    for message in message_items:
                        root_entries.append(
                            (channel_id, channel_name, _graph_channel_message_item(channel_id, channel_name, message))
                        )

        reply_results: dict[str, list[dict[str, Any]]] = {}
        reply_targets = [
            (channel_id, channel_name, root_item)
            for channel_id, channel_name, root_item in root_entries
            if str(root_item.get("id") or "").strip()
        ]
        if reply_targets:
            workers = min(_GRAPH_PARALLEL_WORKERS, len(reply_targets))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        _load_channel_message_replies,
                        team_id,
                        channel_id,
                        str(root_item.get("id") or "").strip(),
                    ): (channel_id, channel_name, root_item)
                    for channel_id, channel_name, root_item in reply_targets
                }
                for future in as_completed(futures):
                    channel_id, channel_name, root_item = futures[future]
                    message_id = str(root_item.get("id") or "").strip()
                    try:
                        reply_results[message_id] = future.result()
                    except httpx.HTTPStatusError as reply_exc:
                        reply_results[message_id] = []
                        reply_errors.append(
                            {
                                "channelId": channel_id,
                                "channelName": channel_name,
                                "messageId": message_id,
                                "status": reply_exc.response.status_code,
                                "detail": _graph_error_detail(reply_exc),
                            }
                        )

        for channel_id, channel_name, root_item in root_entries:
            message_id = str(root_item.get("id") or "").strip()
            replies = reply_results.get(message_id, [])
            root_item["replyCount"] = len(replies)
            if any(_is_recording_channel_message(reply) for reply in replies):
                root_item["isRecordingRelated"] = True
                root_item["activityType"] = "recording"
                root_item["activityLabel"] = "Hilo con grabacion"
            messages.append(root_item)
            reply_message_count += len(replies)
            raw_message_count += len(replies)

            root_subject = str(root_item.get("threadSubject") or root_item.get("subject") or "")
            root_created_datetime = str(root_item.get("createdDateTime") or "")
            for reply in replies:
                messages.append(
                    _graph_channel_message_item(
                        channel_id,
                        channel_name,
                        reply,
                        parent_message_id=message_id,
                        root_subject=root_subject,
                        root_created_datetime=root_created_datetime,
                    )
                )

        messages.sort(key=lambda item: str(item.get("createdDateTime") or ""), reverse=True)
        recording_message_count = sum(1 for item in messages if item.get("isRecordingRelated"))
        return {
            "value": messages[:200],
            "count": len(messages),
            "raw_count": raw_message_count,
            "root_message_count": root_message_count,
            "reply_message_count": reply_message_count,
            "recording_message_count": recording_message_count,
            "channel_count": len(channels),
            "scanned_channel_count": max(0, len(channels) - len(channel_errors)),
            "channel_errors": channel_errors,
            "reply_errors": reply_errors,
            "filter": "all_channel_messages_with_replies",
            "timeZone": _ECUADOR_TIMEZONE_NAME,
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return {
                "value": [],
                "count": 0,
                "timeZone": _ECUADOR_TIMEZONE_NAME,
                "note": "No hay permisos para mensajes de canal. Solicita ChannelMessage.Read.All y Team.ReadBasic.All.",
            }
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/enroll", responses={500: {"description": "Error interno del servidor"}})
def enroll_user_to_team(
    payload: TeamEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, str | bool]:
    del current_user
    team_id = str(payload.team_id or "").strip()
    user_id = str(payload.user_id or "").strip()
    if not team_id or not user_id:
        raise HTTPException(status_code=400, detail="Debes indicar user_id y team_id para matricular")

    try:
        _wait_for_team_ready(team_id)
        _add_directory_object_to_team(team_id, user_id)
        return {
            "ok": True,
            "message": "Usuario matriculado en Teams correctamente",
            "team_id": team_id,
            "user_id": user_id,
        }
    except httpx.HTTPStatusError as exc:
        if _is_already_team_member_error(exc):
            return {
                "ok": True,
                "message": "El usuario ya pertenece al Team",
                "team_id": team_id,
                "user_id": user_id,
            }
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc


@router.post(
    "/mass-enrollment/preview",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def mass_enrollment_preview(
    payload: TeamMassEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    criteria = _normalize_team_mass_enrollment_payload(payload)
    return _build_mass_enrollment_preview(criteria)


@router.post(
    "/mass-enrollment/execute",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def mass_enrollment_execute(
    payload: TeamMassEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    criteria = _normalize_team_mass_enrollment_payload(payload)
    return _execute_mass_enrollment(criteria)


@router.post(
    "/enrollment/filter-options",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_filter_options(
    payload: TeamEnrollmentFilterOptionsRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    criteria = _normalize_group_filter_options_payload(payload)
    return {
        "criteria": criteria,
        "max_periods": 2,
        "periodos": _load_team_enrollment_period_options(),
        "paralelos": _load_team_enrollment_parallel_options(criteria),
        "materias": _load_team_enrollment_materia_options(criteria),
    }


@router.post(
    "/enrollment/search-groups",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_search_groups(
    payload: TeamEnrollmentGroupSearchRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    criteria = _normalize_group_search_payload(payload)
    items = _search_team_enrollment_groups(criteria)
    return {
        "criteria": criteria,
        "total": len(items),
        "items": items,
    }


@router.post(
    "/enrollment/group-students",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_group_students(
    payload: TeamEnrollmentGroupStudentsRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    group_identities = _normalize_group_identities(payload)
    items = _load_team_enrollment_students_for_groups(group_identities)
    group = _group_context_from_students(items, group_identities)
    return {
        "group": group,
        "suggested_team_name": group.get("suggested_team_name"),
        "selected_group_count": len(group_identities),
        "total": len(items),
        "items": items,
    }


@router.post(
    "/enrollment/selected/preview",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_selected_preview(
    payload: TeamEnrollmentSelectionRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    if not payload.team_id.strip():
        raise HTTPException(status_code=400, detail="Debes indicar el Team ID para validar los estudiantes seleccionados")
    return _build_selected_students_preview(payload)


@router.post(
    "/enrollment/selected/execute",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_selected_execute(
    payload: TeamEnrollmentSelectionRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    if not payload.team_id.strip():
        raise HTTPException(status_code=400, detail="Debes indicar el Team ID para matricular los estudiantes seleccionados")
    return _execute_selected_students(payload)


@router.post(
    "/enrollment/individual/search-students",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_individual_search_students(
    payload: TeamIndividualStudentSearchRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    criteria = _normalize_individual_student_search_payload(payload)
    items = _search_individual_team_enrollment_students(criteria)
    return {
        "criteria": criteria,
        "total": len(items),
        "items": items,
        "message": (
            f"Se encontraron {len(items)} estudiante(s) en el periodo."
            if items
            else "No se encontro el estudiante en el periodo seleccionado."
        ),
    }


@router.post(
    "/enrollment/individual/preview",
    responses={400: {"description": "Solicitud invalida"}, 404: {"description": "No encontrado"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_individual_preview(
    payload: TeamIndividualEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _build_individual_team_enrollment_preview(payload)


@router.post(
    "/enrollment/individual/execute",
    responses={400: {"description": "Solicitud invalida"}, 404: {"description": "No encontrado"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_individual_execute(
    payload: TeamIndividualEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _execute_individual_team_enrollment(payload)


@router.post(
    "/enrollment/manual/preview",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_manual_preview(
    payload: TeamManualEmailEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _build_manual_email_enrollment_preview(payload)


@router.post(
    "/enrollment/manual/execute",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def enrollment_manual_execute(
    payload: TeamManualEmailEnrollmentRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _execute_manual_email_enrollment(payload)


def _normalize_items(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _normalize_team_mass_enrollment_payload(payload: TeamMassEnrollmentRequest) -> dict[str, Any]:
    team_id = payload.team_id.strip()
    if not team_id:
        raise HTTPException(status_code=400, detail="Debes indicar el Team ID para la matriculacion masiva")

    tipo_matricula: str | None = None
    tipo_raw = str(payload.tipo_matricula or "").strip().upper()
    if tipo_raw and tipo_raw != "ALL":
        tipo_matricula = _validate_tipo(tipo_raw)

    estado_codigo = str(payload.estado_codigo or "").strip().upper() or None
    if estado_codigo and estado_codigo not in {"A", "P", "R", "G"}:
        raise HTTPException(status_code=400, detail="estado_codigo debe ser A, P, R o G")

    punto_matricula = str(payload.punto_matricula or "PRIMERA").strip().upper() or "PRIMERA"
    if punto_matricula == "ALL":
        punto_matricula = "BOTH"
    if punto_matricula not in {"PRIMERA", "ULTIMA", "BOTH"}:
        raise HTTPException(status_code=400, detail="punto_matricula debe ser PRIMERA, ULTIMA o BOTH")

    codigo_periodo = str(payload.codigo_periodo or "").strip() or None

    return {
        "team_id": team_id,
        "tipo_matricula": tipo_matricula,
        "estado_codigo": estado_codigo,
        "anio_periodo": payload.anio_periodo,
        "punto_matricula": punto_matricula,
        "codigo_periodo": codigo_periodo,
        "limit": int(payload.limit),
    }


def _mass_enrollment_point_filter_sql(punto_matricula: str) -> str:
    if punto_matricula == "PRIMERA":
        return "AND punto_matricula = 'PRIMERA'"
    if punto_matricula == "ULTIMA":
        return "AND punto_matricula = 'ULTIMA'"
    return ""


def _load_mass_enrollment_candidates(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    query = (
        _MATRICULA_BASE_CTE
        + """
        , movement_rows AS (
            SELECT
                tipo_matricula,
                estado_codigo,
                estado_nombre,
                codigo_estud,
                Cedula_Est,
                Apellidos_nombre,
                nombre_carrera,
                correo_intec_datos,
                correo_personal_datos,
                codigo_periodo,
                Detalle_Periodo,
                anio_periodo,
                'PRIMERA' AS punto_matricula
            FROM base_cruce
            WHERE rn_global = 1
            UNION ALL
            SELECT
                tipo_matricula,
                estado_codigo,
                estado_nombre,
                codigo_estud,
                Cedula_Est,
                Apellidos_nombre,
                nombre_carrera,
                correo_intec_datos,
                correo_personal_datos,
                codigo_periodo,
                Detalle_Periodo,
                anio_periodo,
                'ULTIMA' AS punto_matricula
            FROM base_cruce
            WHERE rn_ultima = 1
        ),
        filtered_rows AS (
            SELECT *
            FROM movement_rows
            WHERE correo_intec_datos IS NOT NULL
              AND LTRIM(RTRIM(CAST(correo_intec_datos AS varchar(255)))) <> ''
              {punto_filter}
              AND (? IS NULL OR tipo_matricula = ?)
              AND (? IS NULL OR estado_codigo = ?)
              AND (? IS NULL OR anio_periodo = ?)
              AND (? IS NULL OR TRY_CONVERT(varchar(50), codigo_periodo) = ?)
        ),
        deduped_rows AS (
            SELECT
                codigo_estud,
                MAX(Cedula_Est) AS Cedula_Est,
                MAX(Apellidos_nombre) AS Apellidos_nombre,
                MAX(nombre_carrera) AS nombre_carrera,
                MAX(correo_intec_datos) AS correo_intec_datos,
                MAX(correo_personal_datos) AS correo_personal_datos,
                CASE
                    WHEN SUM(CASE WHEN punto_matricula = 'PRIMERA' THEN 1 ELSE 0 END) > 0
                     AND SUM(CASE WHEN punto_matricula = 'ULTIMA' THEN 1 ELSE 0 END) > 0 THEN 'BOTH'
                    ELSE MAX(punto_matricula)
                END AS punto_matricula,
                CASE
                    WHEN MIN(tipo_matricula) = MAX(tipo_matricula) THEN MAX(tipo_matricula)
                    ELSE 'MIXTO'
                END AS tipo_matricula,
                CASE
                    WHEN MIN(estado_codigo) = MAX(estado_codigo) THEN MAX(estado_codigo)
                    ELSE 'MIXTO'
                END AS estado_codigo,
                CASE
                    WHEN MIN(estado_nombre) = MAX(estado_nombre) THEN MAX(estado_nombre)
                    ELSE 'Multiples estados'
                END AS estado_nombre,
                MAX(anio_periodo) AS anio_periodo,
                CASE
                    WHEN MIN(COALESCE(TRY_CONVERT(varchar(50), codigo_periodo), '')) = MAX(COALESCE(TRY_CONVERT(varchar(50), codigo_periodo), ''))
                        THEN MAX(COALESCE(TRY_CONVERT(varchar(50), codigo_periodo), ''))
                    ELSE 'MULTIPLE'
                END AS codigo_periodo,
                CASE
                    WHEN MIN(COALESCE(Detalle_Periodo, '')) = MAX(COALESCE(Detalle_Periodo, ''))
                        THEN MAX(COALESCE(Detalle_Periodo, ''))
                    ELSE 'Multiples periodos'
                END AS Detalle_Periodo
            FROM filtered_rows
            GROUP BY codigo_estud
        )
        SELECT TOP (?)
            codigo_estud,
            Cedula_Est,
            Apellidos_nombre,
            nombre_carrera,
            correo_intec_datos,
            correo_personal_datos,
            punto_matricula,
            tipo_matricula,
            estado_codigo,
            estado_nombre,
            anio_periodo,
            codigo_periodo,
            Detalle_Periodo
        FROM deduped_rows
        ORDER BY Apellidos_nombre, codigo_estud
        """.format(punto_filter=_mass_enrollment_point_filter_sql(str(criteria["punto_matricula"])))
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    criteria["tipo_matricula"],
                    criteria["tipo_matricula"],
                    criteria["estado_codigo"],
                    criteria["estado_codigo"],
                    criteria["anio_periodo"],
                    criteria["anio_periodo"],
                    criteria["codigo_periodo"],
                    criteria["codigo_periodo"],
                    criteria["limit"],
                ),
            )
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando candidatos de matriculacion masiva: {exc}") from exc

    return [
        {
            "codigo_estud": str(row.codigo_estud) if row.codigo_estud is not None else "",
            "cedula": row.Cedula_Est,
            "nombre_estudiante": row.Apellidos_nombre,
            "nombre_carrera": row.nombre_carrera,
            "correo_intec": row.correo_intec_datos,
            "correo_personal": row.correo_personal_datos,
            "punto_matricula": row.punto_matricula,
            "tipo_matricula": row.tipo_matricula,
            "estado_codigo": row.estado_codigo,
            "estado_nombre": row.estado_nombre,
            "anio_periodo": int(row.anio_periodo) if row.anio_periodo is not None else None,
            "codigo_periodo": str(row.codigo_periodo) if row.codigo_periodo is not None else "",
            "detalle_periodo": row.Detalle_Periodo,
        }
        for row in rows
    ]


def _normalize_email_address(value: Any) -> str:
    return str(value or "").strip().lower()


def _email_has_valid_shape(value: str) -> bool:
    return "@" in value and "." in value.split("@", 1)[-1]


def _resolve_graph_user_by_email(email: str, cache: dict[str, dict[str, Any] | None]) -> dict[str, Any] | None:
    normalized = _normalize_email_address(email)
    if normalized in cache:
        return cache[normalized]

    escaped = normalized.replace("'", "''")
    filter_expr = f"mail eq '{escaped}' or userPrincipalName eq '{escaped}'"
    encoded_filter = quote(filter_expr, safe="'()")
    url = (
        "https://graph.microsoft.com/v1.0/users"
        "?$top=5"
        "&$select=id,displayName,mail,userPrincipalName"
        f"&$filter={encoded_filter}"
    )
    payload = graph_get(url)
    users = _graph_value_items(payload)
    if not users:
        cache[normalized] = None
        return None

    exact_match = next(
        (
            user
            for user in users
            if _normalize_email_address(user.get("mail")) == normalized
            or _normalize_email_address(user.get("userPrincipalName")) == normalized
        ),
        users[0],
    )
    cache[normalized] = exact_match
    return exact_match


def _looks_like_guid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value))


def _resolve_graph_user_for_teacher(identifier: str, cache: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    raw_value = str(identifier or "").strip()
    normalized = raw_value.lower()
    if not raw_value:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un docente valido")

    if normalized in cache and cache[normalized]:
        return cast(dict[str, Any], cache[normalized])

    if _looks_like_guid(raw_value):
        try:
            user = graph_get(
                "https://graph.microsoft.com/v1.0/users/"
                f"{quote(raw_value, safe='')}"
                "?$select=id,displayName,mail,userPrincipalName"
            )
            cache[normalized] = user
            return user
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    if "@" in raw_value:
        user = _resolve_graph_user_by_email(raw_value, cache)
        if user:
            cache[normalized] = user
            return user

    escaped = raw_value.replace("'", "''")
    filter_expr = f"displayName eq '{escaped}'"
    encoded_filter = quote(filter_expr, safe="'()")
    payload = graph_get(
        "https://graph.microsoft.com/v1.0/users"
        "?$top=5"
        "&$select=id,displayName,mail,userPrincipalName"
        f"&$filter={encoded_filter}"
    )
    users = [
        user
        for user in _graph_value_items(payload)
        if str(user.get("displayName") or "").strip().lower() == normalized
    ]
    if len(users) == 1:
        cache[normalized] = users[0]
        return users[0]
    if len(users) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El docente '{raw_value}' coincide con varios usuarios en Microsoft Graph. "
                "Usa el correo institucional o el UPN para identificarlo."
            ),
        )

    raise HTTPException(
        status_code=400,
        detail=(
            f"No se encontro el docente '{raw_value}' en Microsoft Graph. "
            "Usa correo institucional, UPN o id de usuario."
        ),
    )


def _team_member_indexes(team_id: str) -> tuple[set[str], set[str]]:
    member_ids: set[str] = set()
    member_keys: set[str] = set()

    for member in _load_team_members(team_id):
        member_id = str(member.get("id") or "").strip().lower()
        if member_id:
            member_ids.add(member_id)
            member_keys.add(member_id)

        mail = _normalize_email_address(member.get("mail"))
        if mail:
            member_keys.add(mail)

        upn = _normalize_email_address(member.get("userPrincipalName"))
        if upn:
            member_keys.add(upn)

    return member_ids, member_keys


def _preview_status_label(status: str) -> str:
    labels = {
        "ready": "Listo para matricular",
        "already_in_team": "Ya pertenece al Team",
        "not_found": "No encontrado en Graph",
        "invalid_email": "Correo invalido",
        "error": "Error al validar en Graph",
        "enrolled": "Matriculado correctamente",
    }
    return labels.get(status, status)


def _build_suggested_team_name(group_info: dict[str, Any]) -> str:
    nombre_materia = str(group_info.get("nombre_materia") or "").strip()
    nombre_carrera = str(group_info.get("nombre_carrera") or "").strip()
    cod_anio_basica = str(group_info.get("cod_anio_basica") or "").strip()
    paralelo = str(group_info.get("paralelo_nombre") or group_info.get("paralelo") or "").strip()
    detalle_periodo = str(group_info.get("detalle_periodo") or group_info.get("codigo_periodo") or "").strip()

    parts = [
        part
        for part in [
            nombre_materia,
            nombre_carrera or (f"Carrera {cod_anio_basica}" if cod_anio_basica else ""),
            f"Paralelo {paralelo}" if paralelo else "",
            detalle_periodo,
        ]
        if part
    ]
    return " - ".join(parts)


def _normalize_distinct_text_items(values: list[str], max_items: int | None = None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)

    if max_items is not None and len(normalized) > max_items:
        raise HTTPException(status_code=400, detail=f"Solo puedes seleccionar hasta {max_items} periodos")

    return normalized


def _normalize_selected_periods(
    values: list[str],
    fallback_value: str | None = None,
    required: bool = False,
) -> list[str]:
    combined_values = list(values or [])
    fallback_text = str(fallback_value or "").strip()
    if fallback_text:
        combined_values.append(fallback_text)

    normalized = _normalize_distinct_text_items(combined_values, max_items=2)
    if required and not normalized:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un periodo para iniciar la busqueda")
    return normalized


def _normalize_selected_parallels(values: list[str], fallback_value: str | None = None) -> list[str]:
    combined_values = list(values or [])
    fallback_text = str(fallback_value or "").strip()
    if fallback_text:
        combined_values.append(fallback_text)
    return _normalize_distinct_text_items(combined_values)


def _first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


def _build_sql_in_condition(column_name: str, values: list[str]) -> tuple[str, list[Any]]:
    if not values:
        return "", []

    placeholders = ", ".join("?" for _ in values)
    return f" AND {column_name} IN ({placeholders})", list(values)


def _normalize_group_search_payload(payload: TeamEnrollmentGroupSearchRequest) -> dict[str, Any]:
    tipo_matricula: str | None = None
    tipo_raw = str(payload.tipo_matricula or "").strip().upper()
    if tipo_raw and tipo_raw != "ALL":
        tipo_matricula = _validate_tipo(tipo_raw)

    codigo_periodos = _normalize_selected_periods(
        payload.codigo_periodos,
        fallback_value=payload.codigo_periodo,
        required=True,
    )
    paralelos = _normalize_selected_parallels(payload.paralelos, fallback_value=payload.paralelo)

    return {
        "codigo_periodo": _first_or_none(codigo_periodos),
        "codigo_periodos": codigo_periodos,
        "cod_anio_basica": str(payload.cod_anio_basica or "").strip() or None,
        "paralelo": _first_or_none(paralelos),
        "paralelos": paralelos,
        "materia_query": str(payload.materia_query or "").strip() or None,
        "materia_base_keys": _normalize_distinct_text_items(payload.materia_base_keys),
        "tipo_matricula": tipo_matricula,
        "anio_periodo": payload.anio_periodo,
        "limit": int(payload.limit),
    }


def _normalize_group_filter_options_payload(payload: TeamEnrollmentFilterOptionsRequest) -> dict[str, Any]:
    codigo_periodos = _normalize_selected_periods(payload.codigo_periodos)
    paralelos = _normalize_selected_parallels(payload.paralelos, fallback_value=payload.paralelo)
    return {
        "codigo_periodo": _first_or_none(codigo_periodos),
        "codigo_periodos": codigo_periodos,
        "cod_anio_basica": str(payload.cod_anio_basica or "").strip() or None,
        "paralelo": _first_or_none(paralelos),
        "paralelos": paralelos,
        "anio_periodo": payload.anio_periodo,
    }


def _normalize_group_identity_fields(
    codigo_periodo: Any,
    cod_anio_basica: Any,
    paralelo: Any,
    materia_base_key: Any,
    anio_periodo: int | None = None,
) -> dict[str, Any]:
    codigo_periodo_text = str(codigo_periodo or "").strip()
    cod_anio_basica_text = str(cod_anio_basica or "").strip()
    paralelo_text = str(paralelo or "").strip()
    materia_base_key_text = str(materia_base_key or "").strip()

    if not codigo_periodo_text or not cod_anio_basica_text or not paralelo_text or not materia_base_key_text:
        raise HTTPException(
            status_code=400,
            detail="Debes indicar codigo_periodo, cod_anio_basica, paralelo y materia_base_key",
        )

    return {
        "codigo_periodo": codigo_periodo_text,
        "cod_anio_basica": cod_anio_basica_text,
        "paralelo": paralelo_text,
        "materia_base_key": materia_base_key_text,
        "anio_periodo": anio_periodo,
    }


def _normalize_group_identity(
    payload: TeamEnrollmentGroupIdentityItem | TeamEnrollmentGroupStudentsRequest | TeamEnrollmentSelectionRequest,
) -> dict[str, Any]:
    return _normalize_group_identity_fields(
        payload.codigo_periodo,
        payload.cod_anio_basica,
        payload.paralelo,
        payload.materia_base_key,
        payload.anio_periodo,
    )


def _normalize_group_identities(
    payload: TeamEnrollmentGroupStudentsRequest | TeamEnrollmentSelectionRequest,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, int | None]] = set()

    raw_items = list(payload.group_items or [])
    if raw_items:
        candidates = raw_items
    else:
        candidates = [payload]

    for item in candidates:
        identity = _normalize_group_identity(item)
        key = (
            str(identity["codigo_periodo"]),
            str(identity["cod_anio_basica"]),
            str(identity["paralelo"]),
            str(identity["materia_base_key"]),
            cast(int | None, identity.get("anio_periodo")),
        )
        if key in seen:
            continue
        normalized.append(identity)
        seen.add(key)

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Debes indicar al menos un grupo valido para consultar o matricular estudiantes",
        )

    return normalized


def _search_team_enrollment_groups(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    materia_query = str(criteria.get("materia_query") or "").strip()
    materia_like = f"%{materia_query}%" if materia_query else None
    period_filter_sql, period_filter_params = _build_sql_in_condition(
        "codigo_periodo",
        cast(list[str], criteria["codigo_periodos"]),
    )
    materia_filter_sql, materia_filter_params = _build_sql_in_condition(
        "materia_base_key",
        cast(list[str], criteria["materia_base_keys"]),
    )
    paralelo_filter_sql, paralelo_filter_params = _build_sql_in_condition(
        "paralelo",
        cast(list[str], criteria.get("paralelos") or []),
    )
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + f"""
        SELECT TOP (?)
            cod_anio_basica,
            MAX(nombre_carrera) AS nombre_carrera,
            codigo_periodo,
            anio_periodo,
            detalle_periodo,
            periodo_nombre,
            paralelo,
            MAX(paralelo_nombre) AS paralelo_nombre,
            materia_base_key,
            MIN(codigo_materia) AS codigo_materia_referencia,
            MAX(nombre_materia) AS nombre_materia,
            COUNT(DISTINCT codigo_estud) AS total_estudiantes,
            COUNT(DISTINCT CASE
                WHEN correo_intec IS NOT NULL AND LTRIM(RTRIM(CAST(correo_intec AS varchar(255)))) <> '' THEN codigo_estud
                END
            ) AS con_correo_intec
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          {period_filter_sql}
          AND (? IS NULL OR cod_anio_basica = ?)
          {paralelo_filter_sql}
          AND (? IS NULL OR anio_periodo = ?)
          AND (? IS NULL OR tipo_matricula = ?)
          {materia_filter_sql}
          AND (
                ? IS NULL
                OR nombre_materia LIKE ?
                OR materia_base_key LIKE ?
                OR codigo_materia LIKE ?
          )
        GROUP BY
            cod_anio_basica,
            codigo_periodo,
            anio_periodo,
            detalle_periodo,
            periodo_nombre,
            paralelo,
            materia_base_key
        ORDER BY anio_periodo DESC, codigo_periodo DESC, nombre_materia, paralelo
        """
    )

    params = (
        criteria["limit"],
        *period_filter_params,
        criteria["cod_anio_basica"],
        criteria["cod_anio_basica"],
        *paralelo_filter_params,
        criteria["anio_periodo"],
        criteria["anio_periodo"],
        criteria["tipo_matricula"],
        criteria["tipo_matricula"],
        *materia_filter_params,
        materia_like,
        materia_like,
        materia_like,
        materia_like,
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error buscando grupos para Teams: {exc}") from exc

    items: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "cod_anio_basica": str(row.cod_anio_basica) if row.cod_anio_basica is not None else "",
            "nombre_carrera": row.nombre_carrera,
            "codigo_periodo": str(row.codigo_periodo) if row.codigo_periodo is not None else "",
            "anio_periodo": int(row.anio_periodo) if row.anio_periodo is not None else None,
            "detalle_periodo": row.detalle_periodo,
            "periodo_nombre": row.periodo_nombre,
            "paralelo": str(row.paralelo) if row.paralelo is not None else "",
            "paralelo_nombre": row.paralelo_nombre,
            "materia_base_key": str(row.materia_base_key) if row.materia_base_key is not None else "",
            "codigo_materia_referencia": str(row.codigo_materia_referencia) if row.codigo_materia_referencia is not None else "",
            "nombre_materia": row.nombre_materia,
            "total_estudiantes": int(row.total_estudiantes or 0),
            "con_correo_intec": int(row.con_correo_intec or 0),
        }
        item["sin_correo_intec"] = max(0, int(item["total_estudiantes"]) - int(item["con_correo_intec"]))
        item["suggested_team_name"] = _build_suggested_team_name(item)
        items.append(item)

    return items


def _load_team_enrollment_period_options() -> list[dict[str, Any]]:
    query = """
        SELECT
            TRY_CONVERT(varchar(50), pr.cod_periodo) AS codigo_periodo,
            TRY_CONVERT(int, pr.anio) AS anio_periodo,
            TRY_CONVERT(varchar(255), pr.Detalle_Periodo) AS detalle_periodo,
            TRY_CONVERT(varchar(100), pr.Periodo) AS periodo_nombre
        FROM [dbo].[PERIODO] pr
        WHERE pr.cod_periodo IS NOT NULL
        ORDER BY TRY_CONVERT(int, pr.anio) DESC, TRY_CONVERT(varchar(50), pr.cod_periodo) DESC
    """

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando periodos disponibles para Teams: {exc}") from exc

    return [
        {
            "codigo_periodo": str(row.codigo_periodo) if row.codigo_periodo is not None else "",
            "anio_periodo": int(row.anio_periodo) if row.anio_periodo is not None else None,
            "detalle_periodo": row.detalle_periodo,
            "periodo_nombre": row.periodo_nombre,
        }
        for row in rows
        if row.codigo_periodo is not None
    ]


def _load_team_enrollment_parallel_options(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    codigo_periodos = cast(list[str], criteria.get("codigo_periodos") or [])
    if not codigo_periodos:
        return []

    period_filter_sql, period_filter_params = _build_sql_in_condition("codigo_periodo", codigo_periodos)
    paralelo_filter_sql, paralelo_filter_params = _build_sql_in_condition(
        "paralelo",
        cast(list[str], criteria.get("paralelos") or []),
    )
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + f"""
        SELECT
            paralelo,
            MAX(paralelo_nombre) AS paralelo_nombre
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          {period_filter_sql}
          AND (? IS NULL OR cod_anio_basica = ?)
          AND (? IS NULL OR anio_periodo = ?)
          AND paralelo IS NOT NULL
          AND LTRIM(RTRIM(paralelo)) <> ''
        GROUP BY paralelo
        ORDER BY MAX(paralelo_nombre), paralelo
        """
    )

    params = (
        *period_filter_params,
        criteria["cod_anio_basica"],
        criteria["cod_anio_basica"],
        criteria["anio_periodo"],
        criteria["anio_periodo"],
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando paralelos disponibles para Teams: {exc}") from exc

    return [
        {
            "paralelo": str(row.paralelo) if row.paralelo is not None else "",
            "paralelo_nombre": row.paralelo_nombre,
        }
        for row in rows
        if row.paralelo is not None
    ]


def _load_team_enrollment_materia_options(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    codigo_periodos = cast(list[str], criteria.get("codigo_periodos") or [])
    if not codigo_periodos:
        return []

    period_filter_sql, period_filter_params = _build_sql_in_condition("codigo_periodo", codigo_periodos)
    paralelo_filter_sql, paralelo_filter_params = _build_sql_in_condition(
        "paralelo",
        cast(list[str], criteria.get("paralelos") or []),
    )
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + f"""
        SELECT
            materia_base_key,
            MIN(codigo_materia) AS codigo_materia_referencia,
            MAX(nombre_materia) AS nombre_materia,
            COUNT(DISTINCT CONCAT(cod_anio_basica, '|', codigo_periodo, '|', paralelo, '|', materia_base_key)) AS total_grupos,
            COUNT(DISTINCT codigo_estud) AS total_estudiantes
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          {period_filter_sql}
          AND (? IS NULL OR cod_anio_basica = ?)
          {paralelo_filter_sql}
          AND (? IS NULL OR anio_periodo = ?)
          AND materia_base_key IS NOT NULL
          AND LTRIM(RTRIM(materia_base_key)) <> ''
        GROUP BY materia_base_key
        ORDER BY MAX(nombre_materia), materia_base_key
        """
    )

    params = (
        *period_filter_params,
        criteria["cod_anio_basica"],
        criteria["cod_anio_basica"],
        *paralelo_filter_params,
        criteria["anio_periodo"],
        criteria["anio_periodo"],
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando materias disponibles para Teams: {exc}") from exc

    return [
        {
            "materia_base_key": str(row.materia_base_key) if row.materia_base_key is not None else "",
            "codigo_materia_referencia": str(row.codigo_materia_referencia) if row.codigo_materia_referencia is not None else "",
            "nombre_materia": row.nombre_materia,
            "total_grupos": int(row.total_grupos or 0),
            "total_estudiantes": int(row.total_estudiantes or 0),
        }
        for row in rows
        if row.materia_base_key is not None
    ]


def _load_team_enrollment_students(group_identity: dict[str, Any]) -> list[dict[str, Any]]:
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + """
        SELECT
            codigo_estud,
            nombre_estudiante,
            correo_intec,
            correo_personal,
            estado_correo,
            descripcion_correo,
            tipo_matricula,
            cod_anio_basica,
            nombre_carrera,
            codigo_periodo,
            anio_periodo,
            detalle_periodo,
            periodo_nombre,
            paralelo,
            paralelo_nombre,
            materia_base_key,
            codigo_materia,
            nombre_materia,
            num_grupo
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          AND codigo_periodo = ?
          AND cod_anio_basica = ?
          AND paralelo = ?
          AND materia_base_key = ?
          AND (? IS NULL OR anio_periodo = ?)
        ORDER BY nombre_estudiante, codigo_estud
        """
    )

    params = (
        group_identity["codigo_periodo"],
        group_identity["cod_anio_basica"],
        group_identity["paralelo"],
        group_identity["materia_base_key"],
        group_identity["anio_periodo"],
        group_identity["anio_periodo"],
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estudiantes del grupo Teams: {exc}") from exc

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "codigo_estud": str(row.codigo_estud) if row.codigo_estud is not None else "",
                "nombre_estudiante": row.nombre_estudiante,
                "correo_intec": row.correo_intec,
                "correo_personal": row.correo_personal,
                "estado_correo": row.estado_correo,
                "descripcion_correo": row.descripcion_correo,
                "tipo_matricula": row.tipo_matricula,
                "cod_anio_basica": str(row.cod_anio_basica) if row.cod_anio_basica is not None else "",
                "nombre_carrera": row.nombre_carrera,
                "codigo_periodo": str(row.codigo_periodo) if row.codigo_periodo is not None else "",
                "anio_periodo": int(row.anio_periodo) if row.anio_periodo is not None else None,
                "detalle_periodo": row.detalle_periodo,
                "periodo_nombre": row.periodo_nombre,
                "paralelo": str(row.paralelo) if row.paralelo is not None else "",
                "paralelo_nombre": row.paralelo_nombre,
                "materia_base_key": str(row.materia_base_key) if row.materia_base_key is not None else "",
                "codigo_materia": str(row.codigo_materia) if row.codigo_materia is not None else "",
                "nombre_materia": row.nombre_materia,
                "num_grupo": str(row.num_grupo) if row.num_grupo is not None else "",
            }
        )

    return items


def _team_enrollment_student_summary_from_row(row: Any) -> dict[str, Any]:
    return {
        "codigo_estud": str(row.codigo_estud) if row.codigo_estud is not None else "",
        "nombre_estudiante": row.nombre_estudiante,
        "correo_intec": row.correo_intec,
        "correo_personal": row.correo_personal,
        "estado_correo": row.estado_correo,
        "descripcion_correo": row.descripcion_correo,
        "tipo_matricula": row.tipo_matricula,
        "codigo_periodo": str(row.codigo_periodo) if row.codigo_periodo is not None else "",
        "anio_periodo": int(row.anio_periodo) if row.anio_periodo is not None else None,
        "detalle_periodo": row.detalle_periodo,
        "periodo_nombre": row.periodo_nombre,
        "materia_base_key": str(row.materia_base_key) if getattr(row, "materia_base_key", None) is not None else "",
        "nombre_materia": row.nombre_materia,
        "total_materias": int(getattr(row, "total_materias", 0) or 0),
    }


def _normalize_individual_student_search_payload(payload: TeamIndividualStudentSearchRequest) -> dict[str, Any]:
    codigo_periodo = str(payload.codigo_periodo or "").strip()
    if not codigo_periodo:
        raise HTTPException(status_code=400, detail="Debes seleccionar un periodo")

    query = str(payload.query or "").strip()

    return {
        "codigo_periodo": codigo_periodo,
        "query": query,
        "materia_query": str(payload.materia_query or "").strip() or None,
        "paralelo": str(payload.paralelo or "").strip() or None,
        "anio_periodo": payload.anio_periodo,
        "limit": int(payload.limit),
    }


def _normalize_individual_enrollment_payload(payload: TeamIndividualEnrollmentRequest) -> dict[str, Any]:
    team_id = str(payload.team_id or "").strip()
    codigo_periodo = str(payload.codigo_periodo or "").strip()
    selected_student_codes = _normalize_distinct_text_items(
        [*payload.selected_student_codes, str(payload.codigo_estud or "").strip()]
    )

    if not team_id:
        raise HTTPException(status_code=400, detail="Debes seleccionar un Team")
    if not codigo_periodo:
        raise HTTPException(status_code=400, detail="Debes seleccionar un periodo")
    if not selected_student_codes:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un estudiante")

    return {
        "team_id": team_id,
        "codigo_periodo": codigo_periodo,
        "codigo_estud": selected_student_codes[0],
        "selected_student_codes": selected_student_codes,
        "materia_query": str(payload.materia_query or "").strip() or None,
        "paralelo": str(payload.paralelo or "").strip() or None,
        "anio_periodo": payload.anio_periodo,
    }


def _search_individual_team_enrollment_students(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    query_text = str(criteria.get("query") or "").strip()
    like_pattern = f"%{query_text}%" if query_text else None
    materia_text = str(criteria.get("materia_query") or "").strip()
    materia_like = f"%{materia_text}%" if materia_text else None
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + """
        SELECT TOP (?)
            codigo_estud,
            MAX(nombre_estudiante) AS nombre_estudiante,
            MAX(correo_intec) AS correo_intec,
            MAX(correo_personal) AS correo_personal,
            MAX(estado_correo) AS estado_correo,
            MAX(descripcion_correo) AS descripcion_correo,
            MAX(tipo_matricula) AS tipo_matricula,
            MAX(codigo_periodo) AS codigo_periodo,
            MAX(anio_periodo) AS anio_periodo,
            MAX(detalle_periodo) AS detalle_periodo,
            MAX(periodo_nombre) AS periodo_nombre,
            MAX(materia_base_key) AS materia_base_key,
            MAX(nombre_materia) AS nombre_materia,
            COUNT(DISTINCT materia_base_key) AS total_materias
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          AND codigo_periodo = ?
          AND (? IS NULL OR paralelo = ?)
          AND (? IS NULL OR anio_periodo = ?)
          AND (
                ? IS NULL
             OR nombre_materia LIKE ?
             OR materia_base_key LIKE ?
             OR codigo_materia LIKE ?
          )
          AND (
                ? IS NULL
             OR codigo_estud LIKE ?
             OR nombre_estudiante LIKE ?
             OR correo_intec LIKE ?
             OR correo_personal LIKE ?
          )
        GROUP BY codigo_estud
        ORDER BY MAX(nombre_estudiante), codigo_estud
        """
    )

    params = (
        criteria["limit"],
        criteria["codigo_periodo"],
        criteria["paralelo"],
        criteria["paralelo"],
        criteria["anio_periodo"],
        criteria["anio_periodo"],
        materia_like,
        materia_like,
        materia_like,
        materia_like,
        like_pattern,
        like_pattern,
        like_pattern,
        like_pattern,
        like_pattern,
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error buscando estudiante para Teams: {exc}") from exc

    return [_team_enrollment_student_summary_from_row(row) for row in rows]


def _load_individual_team_enrollment_candidates(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    selected_codes = cast(list[str], criteria.get("selected_student_codes") or [])
    code_filter_sql, code_params = _build_sql_in_condition("codigo_estud", selected_codes)
    materia_text = str(criteria.get("materia_query") or "").strip()
    materia_like = f"%{materia_text}%" if materia_text else None
    query = (
        _TEAM_ENROLLMENT_BASE_CTE
        + f"""
        SELECT
            codigo_estud,
            MAX(nombre_estudiante) AS nombre_estudiante,
            MAX(correo_intec) AS correo_intec,
            MAX(correo_personal) AS correo_personal,
            MAX(estado_correo) AS estado_correo,
            MAX(descripcion_correo) AS descripcion_correo,
            MAX(tipo_matricula) AS tipo_matricula,
            MAX(codigo_periodo) AS codigo_periodo,
            MAX(anio_periodo) AS anio_periodo,
            MAX(detalle_periodo) AS detalle_periodo,
            MAX(periodo_nombre) AS periodo_nombre,
            MAX(materia_base_key) AS materia_base_key,
            MAX(nombre_materia) AS nombre_materia,
            COUNT(DISTINCT materia_base_key) AS total_materias
        FROM team_enrollment_base
        WHERE rn_student_group = 1
          AND codigo_periodo = ?
          AND (? IS NULL OR paralelo = ?)
          AND (? IS NULL OR anio_periodo = ?)
          AND (
                ? IS NULL
             OR nombre_materia LIKE ?
             OR materia_base_key LIKE ?
             OR codigo_materia LIKE ?
          )
          {code_filter_sql}
        GROUP BY codigo_estud
        """
    )

    params = (
        criteria["codigo_periodo"],
        criteria["paralelo"],
        criteria["paralelo"],
        criteria["anio_periodo"],
        criteria["anio_periodo"],
        materia_like,
        materia_like,
        materia_like,
        materia_like,
        *code_params,
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error validando estudiante para Teams: {exc}") from exc

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Los estudiantes seleccionados no existen o no estan matriculados en el periodo seleccionado",
        )

    items_by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _team_enrollment_student_summary_from_row(row)
        item["source"] = "individual_student"
        items_by_code[str(item.get("codigo_estud") or "")] = item

    return [items_by_code[code] for code in selected_codes if code in items_by_code]


def _load_team_enrollment_students_for_groups(group_identities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    students_by_code: dict[str, dict[str, Any]] = {}

    for group_identity in group_identities:
        for student in _load_team_enrollment_students(group_identity):
            codigo_estud = str(student.get("codigo_estud") or "").strip()
            if not codigo_estud:
                continue
            if codigo_estud not in students_by_code:
                students_by_code[codigo_estud] = student

    return sorted(
        students_by_code.values(),
        key=lambda item: (
            str(item.get("nombre_estudiante") or "").lower(),
            str(item.get("codigo_estud") or ""),
        ),
    )


def _group_context_from_students(students: list[dict[str, Any]], group_identities: list[dict[str, Any]]) -> dict[str, Any]:
    if not group_identities:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un grupo valido")

    if len(group_identities) == 1:
        group_identity = group_identities[0]
        if students:
            first = students[0]
            context = {
                "cod_anio_basica": first.get("cod_anio_basica"),
                "nombre_carrera": first.get("nombre_carrera"),
                "codigo_periodo": first.get("codigo_periodo"),
                "anio_periodo": first.get("anio_periodo"),
                "detalle_periodo": first.get("detalle_periodo"),
                "periodo_nombre": first.get("periodo_nombre"),
                "paralelo": first.get("paralelo"),
                "paralelo_nombre": first.get("paralelo_nombre"),
                "materia_base_key": first.get("materia_base_key"),
                "codigo_materia_referencia": first.get("codigo_materia"),
                "nombre_materia": first.get("nombre_materia"),
            }
        else:
            context = {
                "cod_anio_basica": group_identity.get("cod_anio_basica"),
                "nombre_carrera": None,
                "codigo_periodo": group_identity.get("codigo_periodo"),
                "anio_periodo": group_identity.get("anio_periodo"),
                "detalle_periodo": None,
                "periodo_nombre": None,
                "paralelo": group_identity.get("paralelo"),
                "paralelo_nombre": None,
                "materia_base_key": group_identity.get("materia_base_key"),
                "codigo_materia_referencia": None,
                "nombre_materia": None,
            }
    else:
        first_group = group_identities[0]
        materia_names = _normalize_distinct_text_items([str(item.get("nombre_materia") or "") for item in students])
        materia_keys = _normalize_distinct_text_items([str(item.get("materia_base_key") or "") for item in students])
        codigo_materias = _normalize_distinct_text_items([str(item.get("codigo_materia") or "") for item in students])
        period_labels = _normalize_distinct_text_items(
            [str(item.get("detalle_periodo") or item.get("codigo_periodo") or "") for item in students]
        )
        carreras = _normalize_distinct_text_items(
            [str(item.get("cod_anio_basica") or "") for item in students or group_identities]
        )
        carrera_names = _normalize_distinct_text_items(
            [str(item.get("nombre_carrera") or "") for item in students]
        )
        paralelo_values = _normalize_distinct_text_items(
            [str(item.get("paralelo") or "") for item in students or group_identities]
        )
        paralelo_labels = _normalize_distinct_text_items(
            [
                str(item.get("paralelo_nombre") or item.get("paralelo") or "")
                for item in students or group_identities
            ]
        )
        anio_values = [item.get("anio_periodo") for item in students if item.get("anio_periodo") is not None]
        anio_periodo = anio_values[0] if len(set(anio_values)) == 1 and anio_values else first_group.get("anio_periodo")

        context = {
            "cod_anio_basica": carreras[0] if len(carreras) == 1 else "",
            "nombre_carrera": carrera_names[0] if len(carrera_names) == 1 else "",
            "codigo_periodo": first_group.get("codigo_periodo"),
            "anio_periodo": anio_periodo,
            "detalle_periodo": " / ".join(period_labels[:2]) if period_labels else None,
            "periodo_nombre": None,
            "paralelo": paralelo_values[0] if len(paralelo_values) == 1 else "",
            "paralelo_nombre": paralelo_labels[0] if len(paralelo_labels) == 1 else "",
            "materia_base_key": materia_keys[0] if materia_keys else first_group.get("materia_base_key"),
            "codigo_materia_referencia": codigo_materias[0] if codigo_materias else None,
            "nombre_materia": materia_names[0] if materia_names else None,
        }

    context["selected_group_count"] = len(group_identities)
    context["total_estudiantes"] = len(students)
    context["con_correo_intec"] = sum(1 for item in students if str(item.get("correo_intec") or "").strip())
    context["sin_correo_intec"] = max(0, int(context["total_estudiantes"]) - int(context["con_correo_intec"]))
    context["suggested_team_name"] = _build_suggested_team_name(context)
    return context


def _selected_students_from_groups(
    payload: TeamEnrollmentSelectionRequest,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    group_identities = _normalize_group_identities(payload)
    selected_codes = {
        str(code).strip()
        for code in payload.selected_student_codes
        if str(code).strip()
    }
    if not selected_codes:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un estudiante")

    all_students = _load_team_enrollment_students_for_groups(group_identities)
    selected_students = [student for student in all_students if str(student.get("codigo_estud") or "") in selected_codes]
    return group_identities, selected_students, len(selected_codes)


def _mass_enrollment_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total_candidates": len(items),
        "ready_count": 0,
        "already_in_team_count": 0,
        "not_found_count": 0,
        "invalid_email_count": 0,
        "error_count": 0,
        "enrolled_count": 0,
    }

    for item in items:
        status = str(item.get("status") or "")
        if status == "ready":
            summary["ready_count"] += 1
        elif status == "already_in_team":
            summary["already_in_team_count"] += 1
        elif status == "not_found":
            summary["not_found_count"] += 1
        elif status == "invalid_email":
            summary["invalid_email_count"] += 1
        elif status == "error":
            summary["error_count"] += 1
        elif status == "enrolled":
            summary["enrolled_count"] += 1

    return summary


def _build_enrollment_preview_from_candidates(
    team_id: str,
    candidates: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_team_id = str(team_id or "").strip()
    try:
        _wait_for_team_ready(normalized_team_id)
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    team_display_name = _resolve_team_display_name(normalized_team_id)
    member_ids, member_keys = _team_member_indexes(normalized_team_id)
    graph_cache: dict[str, dict[str, Any] | None] = {}
    preview_items: list[dict[str, Any]] = []

    for candidate in candidates:
        email = _normalize_email_address(candidate.get("correo_intec"))
        preview_item = dict(candidate)
        preview_item.update(
            {
                "correo_intec": email,
                "graph_user_id": None,
                "graph_display_name": None,
                "graph_mail": None,
                "graph_user_principal_name": None,
                "status": "ready",
                "status_label": _preview_status_label("ready"),
            }
        )

        if not email or not _email_has_valid_shape(email):
            preview_item["status"] = "invalid_email"
            preview_item["status_label"] = _preview_status_label("invalid_email")
            preview_items.append(preview_item)
            continue

        try:
            graph_user = _resolve_graph_user_by_email(email, graph_cache)
        except httpx.HTTPStatusError as exc:
            preview_item["status"] = "error"
            preview_item["status_label"] = _preview_status_label("error")
            preview_item["error"] = exc.response.text
            preview_items.append(preview_item)
            continue

        if not graph_user:
            preview_item["status"] = "not_found"
            preview_item["status_label"] = _preview_status_label("not_found")
            preview_items.append(preview_item)
            continue

        graph_user_id = str(graph_user.get("id") or "").strip()
        graph_mail = _normalize_email_address(graph_user.get("mail"))
        graph_upn = _normalize_email_address(graph_user.get("userPrincipalName"))
        preview_item["graph_user_id"] = graph_user_id or None
        preview_item["graph_display_name"] = graph_user.get("displayName")
        preview_item["graph_mail"] = graph_mail or None
        preview_item["graph_user_principal_name"] = graph_upn or None

        is_member = (
            (graph_user_id and graph_user_id.lower() in member_ids)
            or (graph_mail and graph_mail in member_keys)
            or (graph_upn and graph_upn in member_keys)
            or email in member_keys
        )
        if is_member:
            preview_item["status"] = "already_in_team"
            preview_item["status_label"] = _preview_status_label("already_in_team")

        preview_items.append(preview_item)

    return {
        "team_id": normalized_team_id,
        "team_display_name": team_display_name,
        **_mass_enrollment_summary(preview_items),
        "items": preview_items,
        **(extra or {}),
    }


def _add_directory_object_to_team_once(team_id: str, directory_object_id: str) -> None:
    graph_post(
        f"https://graph.microsoft.com/v1.0/groups/{team_id}/members/$ref",
        {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{directory_object_id}"},
    )


def _add_directory_object_to_team(team_id: str, directory_object_id: str) -> None:
    started = time.time()
    attempt = 0
    last_error = ""

    while time.time() - started < _TEAM_MEMBER_RETRY_TIMEOUT_SECONDS:
        try:
            _add_directory_object_to_team_once(team_id, directory_object_id)
            return
        except httpx.HTTPStatusError as exc:
            if _is_already_team_member_error(exc):
                raise
            if not _is_retryable_team_graph_error(exc):
                raise

            last_error = _graph_error_detail(exc)
            attempt += 1
            time.sleep(_graph_retry_delay_seconds(attempt))

    raise RuntimeError(
        "No se pudo confirmar que el Team este listo para matricular estudiantes."
        + (f" Ultimo error Graph: {last_error}" if last_error else "")
    )


def _add_owner_to_team(team_id: str, user_id: str) -> None:
    graph_post(
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/members",
        {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["owner"],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
        },
    )


def _load_team_conversation_members(team_id: str) -> list[dict[str, Any]]:
    payload = graph_get_all(f"https://graph.microsoft.com/v1.0/teams/{team_id}/members")
    return _graph_value_items(payload)


def _find_team_conversation_member(team_id: str, user_id: str) -> dict[str, Any] | None:
    target_id = str(user_id or "").strip().lower()
    if not target_id:
        return None

    for member in _load_team_conversation_members(team_id):
        member_user_id = str(member.get("userId") or "").strip().lower()
        if member_user_id == target_id:
            return member

    return None


def _conversation_member_is_owner(member: dict[str, Any]) -> bool:
    roles = member.get("roles")
    if not isinstance(roles, list):
        return False
    return any(str(role).strip().lower() == "owner" for role in roles)


def _promote_team_member_to_owner(team_id: str, membership_id: str) -> None:
    graph_patch(
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/members/{quote(membership_id, safe='')}",
        {"roles": ["owner"]},
    )


def _teacher_display_label(teacher_user: dict[str, Any]) -> str:
    return str(
        teacher_user.get("displayName")
        or teacher_user.get("userPrincipalName")
        or teacher_user.get("mail")
        or teacher_user.get("id")
        or ""
    ).strip()


def _ensure_owner_on_team(team_id: str, teacher_user: dict[str, Any]) -> str:
    teacher_id = str(teacher_user.get("id") or "").strip()
    teacher_label = _teacher_display_label(teacher_user) or teacher_id
    if not teacher_id:
        raise HTTPException(status_code=400, detail=f"No se obtuvo id de Microsoft Graph para '{teacher_label}'")

    started = time.time()
    attempt = 0
    last_error = ""

    while time.time() - started < _TEAM_MEMBER_RETRY_TIMEOUT_SECONDS:
        try:
            member = _find_team_conversation_member(team_id, teacher_id)
            if member:
                if _conversation_member_is_owner(member):
                    return "already_owner"

                membership_id = str(member.get("id") or "").strip()
                if membership_id:
                    _promote_team_member_to_owner(team_id, membership_id)
                    return "promoted_owner"

            _add_owner_to_team(team_id, teacher_id)
            return "added_owner"
        except httpx.HTTPStatusError as exc:
            if _is_already_team_member_error(exc):
                try:
                    member = _find_team_conversation_member(team_id, teacher_id)
                    if member:
                        if _conversation_member_is_owner(member):
                            return "already_owner"

                        membership_id = str(member.get("id") or "").strip()
                        if membership_id:
                            _promote_team_member_to_owner(team_id, membership_id)
                            return "promoted_owner"
                except httpx.HTTPStatusError as verify_exc:
                    if not _is_retryable_team_graph_error(verify_exc):
                        raise HTTPException(
                            status_code=verify_exc.response.status_code,
                            detail=(
                                f"No se pudo validar el docente propietario '{teacher_label}' "
                                f"en el Team: {verify_exc.response.text}"
                            ),
                        ) from verify_exc

                last_error = _graph_error_detail(exc)
                attempt += 1
                time.sleep(_graph_retry_delay_seconds(attempt))
                continue

            if not _is_retryable_team_graph_error(exc):
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=f"No se pudo agregar el docente propietario '{teacher_label}' al Team: {exc.response.text}",
                ) from exc

            last_error = _graph_error_detail(exc)
            attempt += 1
            time.sleep(_graph_retry_delay_seconds(attempt))

    raise HTTPException(
        status_code=504,
        detail=(
            f"No se pudo agregar el docente propietario '{teacher_label}' al Team porque Microsoft Graph "
            "no confirmo que el recurso este listo."
            + (f" Ultimo error Graph: {last_error}" if last_error else "")
        ),
    )


def _ensure_teachers_are_team_owners(team_id: str, resolved_teachers: list[dict[str, Any]]) -> list[dict[str, str]]:
    owner_results: list[dict[str, str]] = []
    for index, teacher_user in enumerate(resolved_teachers):
        teacher_id = str(teacher_user.get("id") or "").strip()
        owner_results.append(
            {
                "teacher_id": teacher_id,
                "teacher_display_name": _teacher_display_label(teacher_user),
                "status": _ensure_owner_on_team(team_id, teacher_user),
            }
        )
        if index < len(resolved_teachers) - 1:
            time.sleep(2)

    return owner_results


def _execute_preview_result(preview: dict[str, Any]) -> dict[str, Any]:
    items = cast(list[dict[str, Any]], preview.get("items") or [])
    team_id = str(preview.get("team_id") or "").strip()
    processed = 0
    failed_count = 0

    try:
        _wait_for_team_ready(team_id)
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    for item in items:
        if str(item.get("status") or "") != "ready":
            continue

        graph_user_id = str(item.get("graph_user_id") or "").strip()
        if not graph_user_id:
            item["status"] = "error"
            item["status_label"] = _preview_status_label("error")
            item["error"] = "No se obtuvo graph_user_id para matricular"
            failed_count += 1
            continue

        processed += 1
        try:
            _add_directory_object_to_team(team_id, graph_user_id)
            item["status"] = "enrolled"
            item["status_label"] = _preview_status_label("enrolled")
        except httpx.HTTPStatusError as exc:
            if _is_already_team_member_error(exc):
                item["status"] = "already_in_team"
                item["status_label"] = _preview_status_label("already_in_team")
            else:
                item["status"] = "error"
                item["status_label"] = _preview_status_label("error")
                item["error"] = exc.response.text
                failed_count += 1
        except RuntimeError as exc:
            item["status"] = "error"
            item["status_label"] = _preview_status_label("error")
            item["error"] = str(exc)
            failed_count += 1

    return {
        "ok": True,
        "message": (
            "Matriculacion masiva ejecutada."
            if processed > 0
            else "No habia candidatos listos para matricular."
        ),
        "processed_count": processed,
        "failed_count": failed_count,
        "team_id": preview.get("team_id"),
        "team_display_name": preview.get("team_display_name"),
        **_mass_enrollment_summary(items),
        "items": items,
        **{
            key: value
            for key, value in preview.items()
            if key not in {
                "items",
                "team_id",
                "team_display_name",
                "total_candidates",
                "ready_count",
                "already_in_team_count",
                "not_found_count",
                "invalid_email_count",
                "error_count",
                "enrolled_count",
            }
        },
    }


def _build_individual_team_enrollment_preview(payload: TeamIndividualEnrollmentRequest) -> dict[str, Any]:
    criteria = _normalize_individual_enrollment_payload(payload)
    candidates = _load_individual_team_enrollment_candidates(criteria)
    selected_codes = cast(list[str], criteria.get("selected_student_codes") or [])
    found_codes = {str(item.get("codigo_estud") or "") for item in candidates}
    missing_codes = [code for code in selected_codes if code not in found_codes]
    preview = _build_enrollment_preview_from_candidates(
        str(criteria["team_id"]),
        candidates,
        {
            "source": "individual_student",
            "criteria": criteria,
            "selected_requested_count": len(selected_codes),
            "selected_found_count": len(candidates),
            "missing_student_codes": missing_codes,
        },
    )
    preview["message"] = (
        "Validacion individual completada."
        if not missing_codes
        else f"Validacion completada. No se encontraron {len(missing_codes)} estudiante(s) dentro de los filtros."
    )
    return preview


def _execute_individual_team_enrollment(payload: TeamIndividualEnrollmentRequest) -> dict[str, Any]:
    result = _execute_preview_result(_build_individual_team_enrollment_preview(payload))
    result["message"] = (
        "Matriculacion individual ejecutada. "
        f"Seleccionados: {int(result.get('selected_requested_count') or 0)} | "
        f"Procesados: {int(result.get('processed_count') or 0)} | "
        f"Matriculados: {int(result.get('enrolled_count') or 0)}."
    )
    return result


def _normalize_manual_email_enrollment_payload(payload: TeamManualEmailEnrollmentRequest) -> tuple[str, list[str]]:
    team_id = str(payload.team_id or "").strip()
    if not team_id:
        raise HTTPException(status_code=400, detail="Debes seleccionar o indicar el Team ID")

    emails: list[str] = []
    seen: set[str] = set()
    for value in payload.emails:
        email = _normalize_email_address(value)
        if not email or email in seen:
            continue
        emails.append(email)
        seen.add(email)

    if not emails:
        raise HTTPException(status_code=400, detail="Debes ingresar al menos un correo para matricular")

    if len(emails) > 500:
        raise HTTPException(status_code=400, detail="Solo puedes matricular hasta 500 correos por operacion")

    return team_id, emails


def _manual_email_candidates(emails: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "codigo_estud": email,
            "nombre_estudiante": email,
            "correo_intec": email,
            "correo_personal": None,
            "source": "manual_email",
        }
        for email in emails
    ]


def _build_manual_email_enrollment_preview(payload: TeamManualEmailEnrollmentRequest) -> dict[str, Any]:
    team_id, emails = _normalize_manual_email_enrollment_payload(payload)
    preview = _build_enrollment_preview_from_candidates(
        team_id,
        _manual_email_candidates(emails),
        {
            "source": "manual_email",
            "manual_email_count": len(emails),
        },
    )
    preview["message"] = f"Validacion manual completada para {len(emails)} correo(s)."
    return preview


def _execute_manual_email_enrollment(payload: TeamManualEmailEnrollmentRequest) -> dict[str, Any]:
    preview = _build_manual_email_enrollment_preview(payload)
    result = _execute_preview_result(preview)
    result["message"] = (
        "Matriculacion manual por correo ejecutada. "
        f"Procesados: {int(result.get('processed_count') or 0)} | "
        f"Matriculados: {int(result.get('enrolled_count') or 0)}."
    )
    return result


def _build_mass_enrollment_preview(criteria: dict[str, Any]) -> dict[str, Any]:
    return _build_enrollment_preview_from_candidates(
        str(criteria["team_id"]),
        _load_mass_enrollment_candidates(criteria),
        {"criteria": criteria},
    )


def _execute_mass_enrollment(criteria: dict[str, Any]) -> dict[str, Any]:
    return _execute_preview_result(_build_mass_enrollment_preview(criteria))


def _build_selected_students_preview(payload: TeamEnrollmentSelectionRequest) -> dict[str, Any]:
    group_identities, selected_students, selected_requested_count = _selected_students_from_groups(payload)
    group_context = _group_context_from_students(selected_students, group_identities)
    return _build_enrollment_preview_from_candidates(
        payload.team_id.strip(),
        selected_students,
        {
            "group": group_context,
            "selected_group_count": len(group_identities),
            "selected_requested_count": selected_requested_count,
            "selected_found_count": len(selected_students),
            "suggested_team_name": group_context.get("suggested_team_name"),
        },
    )


def _execute_selected_students(payload: TeamEnrollmentSelectionRequest) -> dict[str, Any]:
    return _execute_preview_result(_build_selected_students_preview(payload))


def _create_classroom_and_assign_teachers(payload: TeamCreateClassroomRequest) -> dict[str, Any]:
    courses = _normalize_items(payload.courses)
    teacher_inputs = _normalize_items(payload.teacher_user_ids)

    if not payload.display_name.strip():
        raise HTTPException(status_code=400, detail="Debes indicar el nombre del aula")

    if not courses:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un curso")

    if not teacher_inputs:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un docente")

    teacher_cache: dict[str, dict[str, Any] | None] = {}
    resolved_teachers: list[dict[str, Any]] = []
    seen_teacher_ids: set[str] = set()
    for teacher_input in teacher_inputs:
        teacher_user = _resolve_graph_user_for_teacher(teacher_input, teacher_cache)
        teacher_id = str(teacher_user.get("id") or "").strip()
        if not teacher_id:
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo obtener el id de Microsoft Graph para el docente '{teacher_input}'",
            )
        if teacher_id in seen_teacher_ids:
            continue
        resolved_teachers.append(teacher_user)
        seen_teacher_ids.add(teacher_id)

    description_parts: list[str] = []
    if payload.description.strip():
        description_parts.append(payload.description.strip())
    description_parts.append(f"Cursos: {', '.join(courses)}")
    full_description = " | ".join(description_parts)

    create_url = "https://graph.microsoft.com/v1.0/teams"
    primary_teacher = resolved_teachers[0]
    create_body: dict[str, Any] = {
        "template@odata.bind": "https://graph.microsoft.com/v1.0/teamsTemplates('educationClass')",
        "displayName": payload.display_name.strip(),
        "description": full_description,
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{str(primary_teacher.get('id') or '').strip()}')",
            }
        ],
    }

    creation_key = _reserve_team_creation_slot(payload.display_name)
    try:
        existing_team = _existing_classroom_team(payload.display_name.strip())
        team_already_existed = existing_team is not None

        if existing_team:
            team_id = str(existing_team.get("id") or "").strip()
        else:
            creation_result = _graph_post_with_meta_retry(create_url, create_body)
            headers = creation_result.get("headers", {})
            location = ""
            if isinstance(headers, dict):
                header_map: dict[str, Any] = cast(dict[str, Any], headers)
                header_location = header_map.get("location") or header_map.get("Location")
                location = str(header_location) if header_location else ""

            if not location:
                raise RuntimeError("Graph no devolvio encabezado Location para rastrear la creacion del Team")

            team_id = _wait_for_team_creation(location)
            _wait_for_team_ready(team_id)

        owner_results = _ensure_teachers_are_team_owners(team_id, resolved_teachers)

        return {
            "ok": True,
            "message": (
                "Aula existente encontrada, validada y lista para matricular estudiantes."
                if team_already_existed
                else "Aula tipo clase creada con docentes propietarios y lista para matricular estudiantes como miembros"
            ),
            "team_id": team_id,
            "team_already_existed": team_already_existed,
            "teacher_count": len(resolved_teachers),
            "course_count": len(courses),
            "teacher_inputs": teacher_inputs,
            "teacher_display_names": [
                str(teacher.get("displayName") or teacher.get("userPrincipalName") or teacher.get("mail") or "").strip()
                for teacher in resolved_teachers
            ],
            "owner_results": owner_results,
        }
    except httpx.HTTPStatusError as exc:
        _raise_graph_http_exception(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        _release_team_creation_slot(creation_key)


def _create_classroom_and_auto_enroll(payload: TeamCreateAndEnrollRequest) -> dict[str, Any]:
    creation_result = _create_classroom_and_assign_teachers(payload)
    selected_codes = _normalize_distinct_text_items(payload.selected_student_codes)

    if not selected_codes:
        creation_result["message"] = "Aula tipo clase creada correctamente. No habia estudiantes seleccionados para matricular."
        return creation_result

    selection_payload = TeamEnrollmentSelectionRequest(
        team_id=str(creation_result.get("team_id") or ""),
        codigo_periodo=payload.codigo_periodo,
        cod_anio_basica=payload.cod_anio_basica,
        paralelo=payload.paralelo,
        materia_base_key=payload.materia_base_key,
        selected_student_codes=selected_codes,
        anio_periodo=payload.anio_periodo,
        group_items=payload.group_items,
    )
    enrollment_result = _execute_selected_students(selection_payload)
    action_label = (
        "Aula existente validada y matriculacion automatica ejecutada."
        if creation_result.get("team_already_existed")
        else "Aula tipo clase creada y matriculacion automatica ejecutada."
    )

    return {
        **creation_result,
        **enrollment_result,
        "team_id": creation_result.get("team_id"),
        "teacher_count": creation_result.get("teacher_count"),
        "course_count": creation_result.get("course_count"),
        "teacher_inputs": creation_result.get("teacher_inputs"),
        "teacher_display_names": creation_result.get("teacher_display_names"),
        "message": (
            f"{action_label} "
            f"Procesados: {int(enrollment_result.get('processed_count') or 0)} | "
            f"Matriculados: {int(enrollment_result.get('enrolled_count') or 0)}."
        ),
    }


@router.post(
    "/create-classroom",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def create_classroom(
    payload: TeamCreateClassroomRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _create_classroom_and_assign_teachers(payload)


@router.post(
    "/create-and-enroll",
    responses={400: {"description": "Solicitud invalida"}, 500: {"description": "Error interno del servidor"}},
)
def create_and_enroll(
    payload: TeamCreateAndEnrollRequest,
    current_user: Annotated[SessionUser, Depends(_TEAMS_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _create_classroom_and_auto_enroll(payload)
