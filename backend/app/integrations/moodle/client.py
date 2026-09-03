from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.core.audit_context import get_audit_context
from app.core.config import Settings
from app.integrations.moodle.exceptions import (
    MoodleApiError,
    MoodleConfigurationError,
    MoodleConnectionError,
    MoodleDisabledError,
    MoodleFullScanDisabledError,
    MoodleFunctionNotAllowedError,
    MoodleInvalidResponseError,
    MoodleResultLimitExceededError,
    MoodleTimeoutError,
    MoodleWriteDisabledError,
)

logger = logging.getLogger(__name__)

SITE_INFO_FUNCTION = "core_webservice_get_site_info"
USERS_FUNCTION = "core_user_get_users"
USERS_BY_FIELD_FUNCTION = "core_user_get_users_by_field"
COURSES_FUNCTION = "core_course_get_courses_by_field"
COURSE_CONTENTS_FUNCTION = "core_course_get_contents"
ENROLLED_USERS_FUNCTION = "core_enrol_get_enrolled_users"
GRADE_ITEMS_FUNCTION = "gradereport_user_get_grade_items"
URLS_FUNCTION = "mod_url_get_urls_by_courses"
UPDATE_USERS_FUNCTION = "core_user_update_users"
CREATE_USERS_FUNCTION = "core_user_create_users"
EDIT_SECTION_FUNCTION = "core_course_edit_section"
UPDATE_INPLACE_EDITABLE_FUNCTION = "core_update_inplace_editable"
READ_FUNCTIONS = frozenset(
    {
        SITE_INFO_FUNCTION,
        USERS_FUNCTION,
        USERS_BY_FIELD_FUNCTION,
        COURSES_FUNCTION,
        COURSE_CONTENTS_FUNCTION,
        ENROLLED_USERS_FUNCTION,
        GRADE_ITEMS_FUNCTION,
        URLS_FUNCTION,
    }
)
WRITE_FUNCTIONS = frozenset(
    {
        CREATE_USERS_FUNCTION,
        UPDATE_USERS_FUNCTION,
        EDIT_SECTION_FUNCTION,
        UPDATE_INPLACE_EDITABLE_FUNCTION,
    }
)
_FUNCTION_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(slots=True)
class MoodleFileStream:
    response: httpx.Response
    owned_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        await self.response.aclose()
        if self.owned_client is not None:
            await self.owned_client.aclose()


class MoodleClient:
    """Cliente REST con consultas y cambio controlado del estado de usuarios."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    @property
    def endpoint(self) -> str:
        base_url = str(self._settings.moodle_base_url or "").strip().rstrip("/")
        if not base_url:
            raise MoodleConfigurationError("La URL de Moodle no está configurada")
        return f"{base_url}/webservice/rest/server.php"

    def _token_value(self) -> str:
        token = self._settings.moodle_token
        value = token.get_secret_value().strip() if token else ""
        if not value:
            raise MoodleConfigurationError("El token de Moodle no está configurado")
        return value

    def _safe_remote_message(self, value: Any) -> str:
        message = str(value or "Error de Moodle").strip()
        token = self._token_value()
        if token:
            message = message.replace(token, "[credencial protegida]")
        return message[:500]

    def _validate_read_access(self) -> None:
        if not self._settings.moodle_enabled:
            raise MoodleDisabledError("La integración con Moodle está deshabilitada")
        if not self._settings.moodle_reads_enabled:
            raise MoodleDisabledError("Las consultas de Moodle están deshabilitadas")

    def _validate_write_access(self, function: str) -> None:
        if not self._settings.moodle_enabled:
            raise MoodleDisabledError("La integración con Moodle está deshabilitada")
        if not self._settings.moodle_writes_enabled:
            raise MoodleWriteDisabledError("Las escrituras de Moodle están deshabilitadas")
        if (
            function == UPDATE_USERS_FUNCTION
            and not self._settings.moodle_user_status_update_enabled
        ):
            raise MoodleWriteDisabledError(
                "La activación e inactivación de usuarios Moodle está deshabilitada"
            )
        if (
            function in {EDIT_SECTION_FUNCTION, UPDATE_INPLACE_EDITABLE_FUNCTION}
            and not self._settings.moodle_section_updates_enabled
        ):
            raise MoodleWriteDisabledError(
                "La actualización de secciones Moodle está deshabilitada"
            )
        evaluation_function = str(
            self._settings.moodle_evaluation_dates_function or ""
        ).strip()
        if (
            function == evaluation_function
            and not self._settings.moodle_evaluation_dates_update_enabled
        ):
            raise MoodleWriteDisabledError(
                "La actualización de fechas de evaluaciones Moodle está deshabilitada"
            )

    def _evaluation_dates_function(self) -> str:
        function = str(self._settings.moodle_evaluation_dates_function or "").strip()
        if not _FUNCTION_NAME_PATTERN.fullmatch(function):
            raise MoodleConfigurationError(
                "La función externa para actualizar fechas de evaluaciones no es válida"
            )
        return function

    async def _post(
        self,
        function: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        write: bool = False,
    ) -> Any:
        if write:
            self._validate_write_access(function)
            allowed_functions = set(WRITE_FUNCTIONS)
            configured_function = str(
                self._settings.moodle_evaluation_dates_function or ""
            ).strip()
            if _FUNCTION_NAME_PATTERN.fullmatch(configured_function):
                allowed_functions.add(configured_function)
        else:
            self._validate_read_access()
            allowed_functions = READ_FUNCTIONS
        if function not in allowed_functions:
            raise MoodleFunctionNotAllowedError("La función de Moodle no está autorizada")

        form_data: dict[str, Any] = {
            "wstoken": self._token_value(),
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        if parameters:
            form_data.update(parameters)

        request_id = get_audit_context().request_id or "sin-request-id"
        operation = "escritura" if write else "consulta"
        logger.info(
            "Operación Moodle iniciada type=%s function=%s request_id=%s",
            operation,
            function,
            request_id,
        )

        try:
            if self._http_client is not None:
                response = await self._http_client.post(self.endpoint, data=form_data)
            else:
                timeout = httpx.Timeout(float(self._settings.moodle_timeout_seconds))
                async with httpx.AsyncClient(
                    timeout=timeout,
                    verify=bool(self._settings.moodle_verify_tls),
                ) as client:
                    response = await client.post(self.endpoint, data=form_data)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("Timeout Moodle function=%s request_id=%s", function, request_id)
            raise MoodleTimeoutError("Moodle no respondió dentro del tiempo permitido") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Error HTTP Moodle function=%s status=%s request_id=%s",
                function,
                exc.response.status_code,
                request_id,
            )
            raise MoodleConnectionError("Moodle respondió con un error HTTP") from exc
        except httpx.RequestError as exc:
            logger.warning("Error de conexión Moodle function=%s request_id=%s", function, request_id)
            raise MoodleConnectionError("No fue posible conectar con Moodle") from exc

        if write and not response.content.strip():
            payload = None
        else:
            try:
                payload = response.json()
            except ValueError as exc:
                raise MoodleInvalidResponseError("Moodle devolvió una respuesta no válida") from exc

        if isinstance(payload, dict) and payload.get("exception"):
            error_code = str(payload.get("errorcode") or "unknown").strip()
            message = self._safe_remote_message(payload.get("message"))
            logger.warning(
                "Error de API Moodle function=%s errorcode=%s request_id=%s",
                function,
                error_code,
                request_id,
            )
            raise MoodleApiError(f"Moodle rechazó la operación ({error_code}): {message}")

        logger.info(
            "Operación Moodle completada type=%s function=%s request_id=%s",
            operation,
            function,
            request_id,
        )
        return payload

    async def get_site_info(self) -> dict[str, Any]:
        payload = await self._post(SITE_INFO_FUNCTION)
        if not isinstance(payload, dict):
            raise MoodleInvalidResponseError("La información del sitio Moodle no tiene el formato esperado")
        return payload

    async def get_all_users(self) -> list[dict[str, Any]]:
        if not self._settings.moodle_full_user_scan_enabled:
            raise MoodleFullScanDisabledError("La consulta global de usuarios Moodle está deshabilitada")

        # core_user_get_users exige al menos un criterio. El comodín de correo
        # permite cargar el directorio completo sin ampliar la búsqueda a otros campos.
        payload = await self._post(
            USERS_FUNCTION,
            {
                "criteria[0][key]": "email",
                "criteria[0][value]": "%",
            },
        )
        users = payload.get("users") if isinstance(payload, dict) else None
        if not isinstance(users, list):
            raise MoodleInvalidResponseError("La lista de usuarios Moodle no tiene el formato esperado")
        if len(users) > int(self._settings.moodle_max_user_scan_items):
            raise MoodleResultLimitExceededError("La consulta de usuarios Moodle superó el límite configurado")
        return [item for item in users if isinstance(item, dict)]

    async def get_users_by_field(self, field: str, values: list[str]) -> list[dict[str, Any]]:
        normalized_field = str(field or "").strip().casefold()
        if normalized_field not in {"email", "idnumber", "username"}:
            raise MoodleConfigurationError("El campo de búsqueda de usuarios Moodle no es válido")

        normalized_values = list(
            dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip())
        )
        if not normalized_values:
            return []
        if len(normalized_values) > 100:
            raise MoodleConfigurationError("La búsqueda Moodle admite hasta 100 valores")

        parameters: dict[str, Any] = {"field": normalized_field}
        for index, value in enumerate(normalized_values):
            parameters[f"values[{index}]"] = value
        payload = await self._post(USERS_BY_FIELD_FUNCTION, parameters)
        if not isinstance(payload, list):
            raise MoodleInvalidResponseError(
                "La búsqueda de usuarios Moodle no tiene el formato esperado"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def create_users(self, users: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not users:
            return []
        if len(users) > 100:
            raise MoodleConfigurationError("La creación Moodle admite hasta 100 usuarios por solicitud")

        required_fields = ("username", "password", "firstname", "lastname", "email")
        allowed_fields = (*required_fields, "auth", "idnumber", "lang")
        parameters: dict[str, Any] = {}
        for index, user in enumerate(users):
            missing = [field for field in required_fields if not str(user.get(field) or "").strip()]
            if missing:
                raise MoodleConfigurationError(
                    f"Faltan campos obligatorios para crear el usuario Moodle: {', '.join(missing)}"
                )
            for field in allowed_fields:
                value = user.get(field)
                if value is not None and str(value).strip():
                    parameters[f"users[{index}][{field}]"] = str(value).strip()
            preferences = user.get("preferences")
            if preferences is not None and not isinstance(preferences, list):
                raise MoodleConfigurationError("Las preferencias del usuario Moodle no son válidas")
            for preference_index, preference in enumerate(preferences or []):
                if not isinstance(preference, Mapping):
                    raise MoodleConfigurationError("Las preferencias del usuario Moodle no son válidas")
                preference_type = str(preference.get("type") or "").strip()
                preference_value = str(preference.get("value") or "").strip()
                if not preference_type:
                    raise MoodleConfigurationError("La preferencia Moodle no tiene tipo")
                parameters[
                    f"users[{index}][preferences][{preference_index}][type]"
                ] = preference_type
                parameters[
                    f"users[{index}][preferences][{preference_index}][value]"
                ] = preference_value

        payload = await self._post(CREATE_USERS_FUNCTION, parameters, write=True)
        if not isinstance(payload, list):
            raise MoodleInvalidResponseError(
                "La creación de usuarios Moodle no tiene el formato esperado"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_all_courses(self) -> list[dict[str, Any]]:
        payload = await self._post(COURSES_FUNCTION, {"field": "", "value": ""})
        courses = payload.get("courses") if isinstance(payload, dict) else None
        if not isinstance(courses, list):
            raise MoodleInvalidResponseError("La lista de cursos Moodle no tiene el formato esperado")
        return [item for item in courses if isinstance(item, dict)]

    async def get_course_contents(self, course_id: int) -> list[dict[str, Any]]:
        payload = await self._post(COURSE_CONTENTS_FUNCTION, {"courseid": int(course_id)})
        if not isinstance(payload, list):
            raise MoodleInvalidResponseError(
                "El contenido del curso Moodle no tiene el formato esperado"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_course_external_urls(self, course_id: int) -> list[dict[str, Any]]:
        payload = await self._post(URLS_FUNCTION, {"courseids[0]": int(course_id)})
        urls = payload.get("urls") if isinstance(payload, dict) else None
        if not isinstance(urls, list):
            raise MoodleInvalidResponseError(
                "La lista de enlaces externos Moodle no tiene el formato esperado"
            )
        return [item for item in urls if isinstance(item, dict)]

    async def get_course_enrolled_users(self, course_id: int) -> list[dict[str, Any]]:
        payload = await self._post(ENROLLED_USERS_FUNCTION, {"courseid": int(course_id)})
        if not isinstance(payload, list):
            raise MoodleInvalidResponseError(
                "La matrícula del curso Moodle no tiene el formato esperado"
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_course_grade_items(
        self,
        course_id: int,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        parameters: dict[str, Any] = {"courseid": int(course_id)}
        if user_id is not None:
            parameters["userid"] = int(user_id)
        payload = await self._post(GRADE_ITEMS_FUNCTION, parameters)
        user_grades = payload.get("usergrades") if isinstance(payload, dict) else None
        if not isinstance(user_grades, list):
            raise MoodleInvalidResponseError(
                "Las calificaciones del curso Moodle no tienen el formato esperado"
            )
        return [item for item in user_grades if isinstance(item, dict)]

    async def update_user_suspension(self, user_id: int, *, suspended: bool) -> None:
        payload = await self._post(
            UPDATE_USERS_FUNCTION,
            {
                "users[0][id]": int(user_id),
                "users[0][suspended]": 1 if suspended else 0,
            },
            write=True,
        )
        if payload is not None and not isinstance(payload, (dict, list)):
            raise MoodleInvalidResponseError(
                "La respuesta del cambio de estado Moodle no tiene el formato esperado"
            )

    async def edit_section_visibility(
        self,
        section_id: int,
        *,
        section_number: int,
        visible: bool,
    ) -> None:
        payload = await self._post(
            EDIT_SECTION_FUNCTION,
            {
                "action": "show" if visible else "hide",
                "id": int(section_id),
                "sectionreturn": int(section_number),
            },
            write=True,
        )
        if payload is not None and not isinstance(payload, (dict, list)):
            raise MoodleInvalidResponseError(
                "La respuesta del cambio de sección Moodle no tiene el formato esperado"
            )

    async def edit_section_name(
        self,
        section_id: int,
        *,
        course_format: str,
        name: str,
    ) -> None:
        clean_format = str(course_format or "").strip().casefold()
        clean_name = str(name or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", clean_format):
            raise MoodleConfigurationError("El formato del curso Moodle no es válido")
        if not clean_name or len(clean_name) > 1333:
            raise MoodleConfigurationError(
                "El nombre de la sección debe tener entre 1 y 1333 caracteres"
            )

        payload = await self._post(
            UPDATE_INPLACE_EDITABLE_FUNCTION,
            {
                "component": f"format_{clean_format}",
                "itemtype": "sectionname",
                "itemid": int(section_id),
                "value": clean_name,
            },
            write=True,
        )
        if not isinstance(payload, dict):
            raise MoodleInvalidResponseError(
                "La respuesta del cambio de nombre Moodle no tiene el formato esperado"
            )

    async def update_evaluation_dates(
        self,
        course_id: int,
        updates: list[dict[str, Any]],
    ) -> Any:
        parameters: dict[str, Any] = {"courseid": int(course_id)}
        for index, update in enumerate(updates):
            for key, value in update.items():
                parameters[f"updates[{index}][{key}]"] = value

        payload = await self._post(
            self._evaluation_dates_function(),
            parameters,
            write=True,
        )
        if payload is not None and not isinstance(payload, (dict, list)):
            raise MoodleInvalidResponseError(
                "La respuesta de la actualización de fechas Moodle no tiene el formato esperado"
            )
        return payload

    def _authenticated_file_url(self, file_url: str) -> str:
        self._validate_read_access()
        base = urlsplit(str(self._settings.moodle_base_url or "").strip().rstrip("/"))
        try:
            candidate = urlsplit(str(file_url or "").strip())
        except ValueError as exc:
            raise MoodleConfigurationError("La dirección del archivo Moodle no es válida") from exc

        if (
            candidate.scheme.casefold() not in {"http", "https"}
            or candidate.scheme.casefold() != base.scheme.casefold()
            or candidate.netloc.casefold() != base.netloc.casefold()
            or candidate.username
            or candidate.password
        ):
            raise MoodleConfigurationError("El archivo no pertenece al sitio Moodle configurado")

        path = candidate.path
        if "/webservice/pluginfile.php/" not in path:
            marker = "/pluginfile.php/"
            if marker not in path:
                raise MoodleConfigurationError("La dirección no corresponde a un archivo Moodle")
            path = path.replace(marker, "/webservice/pluginfile.php/", 1)

        query = [
            (key, value)
            for key, value in parse_qsl(candidate.query, keep_blank_values=True)
            if key.casefold() not in {"token", "wstoken"}
        ]
        query.append(("token", self._token_value()))
        return urlunsplit(
            (candidate.scheme, candidate.netloc, path, urlencode(query, doseq=True), "")
        )

    async def open_file(self, file_url: str) -> MoodleFileStream:
        authenticated_url = self._authenticated_file_url(file_url)
        owned_client: httpx.AsyncClient | None = None
        client = self._http_client
        if client is None:
            owned_client = httpx.AsyncClient(
                timeout=httpx.Timeout(float(self._settings.moodle_timeout_seconds)),
                verify=bool(self._settings.moodle_verify_tls),
                follow_redirects=False,
            )
            client = owned_client

        response: httpx.Response | None = None
        try:
            current_url = authenticated_url
            base = urlsplit(str(self._settings.moodle_base_url or "").strip().rstrip("/"))
            for _redirect in range(4):
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True, follow_redirects=False)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break

                location = str(response.headers.get("location") or "").strip()
                if not location:
                    break
                redirected_url = urlsplit(urljoin(str(response.url), location))
                await response.aclose()
                response = None
                if (
                    redirected_url.scheme.casefold() != base.scheme.casefold()
                    or redirected_url.netloc.casefold() != base.netloc.casefold()
                    or redirected_url.username
                    or redirected_url.password
                ):
                    raise MoodleConnectionError(
                        "Moodle intentó redirigir el archivo fuera del sitio configurado"
                    )
                current_url = urlunsplit(redirected_url)
            else:
                raise MoodleConnectionError("Moodle excedió el límite de redirecciones del archivo")

            if response is None:
                raise MoodleConnectionError("Moodle no devolvió el archivo solicitado")
            response.raise_for_status()
            return MoodleFileStream(response=response, owned_client=owned_client)
        except httpx.TimeoutException as exc:
            if response is not None:
                await response.aclose()
            if owned_client is not None:
                await owned_client.aclose()
            raise MoodleTimeoutError("Moodle no respondió dentro del tiempo permitido") from exc
        except httpx.HTTPStatusError as exc:
            if response is not None:
                await response.aclose()
            if owned_client is not None:
                await owned_client.aclose()
            if exc.response.status_code == 404:
                raise MoodleConnectionError("El archivo ya no está disponible en Moodle") from exc
            raise MoodleConnectionError("Moodle respondió con un error al obtener el archivo") from exc
        except httpx.RequestError as exc:
            if response is not None:
                await response.aclose()
            if owned_client is not None:
                await owned_client.aclose()
            raise MoodleConnectionError("No fue posible obtener el archivo desde Moodle") from exc
