from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import Settings
from app.integrations.moodle.client import (
    COURSE_CONTENTS_FUNCTION,
    COURSES_FUNCTION,
    EDIT_SECTION_FUNCTION,
    ENROLLED_USERS_FUNCTION,
    GRADE_ITEMS_FUNCTION,
    SITE_INFO_FUNCTION,
    UPDATE_INPLACE_EDITABLE_FUNCTION,
    UPDATE_USERS_FUNCTION,
    USERS_FUNCTION,
    MoodleClient,
    MoodleFileStream,
)
from app.integrations.moodle.exceptions import (
    MoodleCourseNotFoundError,
    MoodleError,
    MoodleInstitutionalEmailNotFoundError,
    MoodleInstitutionalEmailValidationError,
    MoodleResourceNotFoundError,
    MoodleResultLimitExceededError,
    MoodleSectionNotFoundError,
    MoodleSectionUpdateError,
    MoodleUserNotConfirmedError,
    MoodleUserNotFoundError,
)
from app.services.db import get_connection, get_integration_control_connection
from app.services.email_identity import normalize_email_identity

logger = logging.getLogger(__name__)

UserState = Literal["all", "active", "suspended", "unconfirmed"]
CourseVisibility = Literal["all", "visible", "hidden"]


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())


class _ResourceLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._anchors: list[dict[str, Any]] = []
        self._links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return

        attributes = {key.casefold(): value or "" for key, value in attrs}
        fallback_label = attributes.get("title") or attributes.get("aria-label") or ""
        if normalized_tag == "a" and attributes.get("href"):
            self._anchors.append(
                {
                    "url": attributes["href"],
                    "fallback_label": fallback_label,
                    "parts": [],
                }
            )
            return

        source_attribute = {
            "iframe": "src",
            "embed": "src",
            "object": "data",
        }.get(normalized_tag)
        if source_attribute and attributes.get(source_attribute):
            self._links.append((fallback_label, attributes[source_attribute]))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth or normalized_tag != "a" or not self._anchors:
            return
        anchor = self._anchors.pop()
        label = " ".join(" ".join(anchor["parts"]).split()) or anchor["fallback_label"]
        self._links.append((label, anchor["url"]))

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._anchors:
            self._anchors[-1]["parts"].append(data)

    def links(self) -> list[tuple[str, str]]:
        while self._anchors:
            anchor = self._anchors.pop()
            label = " ".join(" ".join(anchor["parts"]).split()) or anchor["fallback_label"]
            self._links.append((label, anchor["url"]))
        return list(self._links)


@dataclass(slots=True)
class _CacheEntry:
    items: list[dict[str, Any]]
    fetched_at: datetime
    expires_at: float


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _as_text(value).casefold() in {"1", "true", "yes", "si", "sí", "on"}


def _search_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _as_text(value).casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _summary_as_plain_text(value: Any) -> str:
    raw = _as_text(value)
    if not raw:
        return ""
    parser = _PlainTextParser()
    try:
        parser.feed(raw)
        parser.close()
        return parser.text()
    except (ValueError, AssertionError):
        return " ".join(re.sub(r"<[^>]*>", " ", raw).split())


_BARE_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)


class MoodleReadService:
    """Consultas Moodle y cambio controlado del estado de cuentas."""

    def __init__(
        self,
        settings: Settings,
        client: MoodleClient | None = None,
        institutional_email_validator: Callable[[str], dict[str, Any]] | None = None,
        status_auditor: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], bool]
        | None = None,
        section_auditor: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], bool]
        | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or MoodleClient(settings)
        self._institutional_email_validator = (
            institutional_email_validator or self._validate_institutional_email
        )
        self._status_auditor = status_auditor or self._record_status_audit
        self._section_auditor = section_auditor or self._record_section_audit
        self._users_cache: _CacheEntry | None = None
        self._courses_cache: _CacheEntry | None = None
        self._course_contents_cache: dict[int, _CacheEntry] = {}
        self._course_enrolled_users_cache: dict[int, _CacheEntry] = {}
        self._course_grade_items_cache: dict[int, _CacheEntry] = {}
        self._users_lock = asyncio.Lock()
        self._courses_lock = asyncio.Lock()
        self._course_contents_lock = asyncio.Lock()
        self._course_enrolled_users_locks: dict[int, asyncio.Lock] = {}
        self._course_grade_items_locks: dict[int, asyncio.Lock] = {}

    async def get_status(self) -> dict[str, Any]:
        payload = await self._client.get_site_info()
        available_functions = self._function_names(payload.get("functions"))
        required_functions = [
            SITE_INFO_FUNCTION,
            USERS_FUNCTION,
            COURSES_FUNCTION,
            COURSE_CONTENTS_FUNCTION,
            ENROLLED_USERS_FUNCTION,
            GRADE_ITEMS_FUNCTION,
            UPDATE_USERS_FUNCTION,
            EDIT_SECTION_FUNCTION,
            UPDATE_INPLACE_EDITABLE_FUNCTION,
        ]

        token = self._settings.moodle_token
        configured = bool(
            _as_text(self._settings.moodle_base_url)
            and token
            and token.get_secret_value().strip()
        )
        return {
            "enabled": bool(self._settings.moodle_enabled),
            "configured": configured,
            "reachable": True,
            "site_name": _as_text(payload.get("sitename")),
            "site_url": _as_text(payload.get("siteurl")),
            "moodle_username": _as_text(payload.get("username")),
            "moodle_user_id": _as_int(payload.get("userid")),
            "moodle_release": _as_text(payload.get("release")),
            "moodle_version": _as_text(payload.get("version")),
            "user_is_site_admin": _as_bool(payload.get("userissiteadmin")),
            "user_status_updates_enabled": bool(
                self._settings.moodle_enabled
                and self._settings.moodle_writes_enabled
                and self._settings.moodle_user_status_update_enabled
            ),
            "section_updates_enabled": bool(
                self._settings.moodle_enabled
                and self._settings.moodle_writes_enabled
                and self._settings.moodle_section_updates_enabled
            ),
            "functions_count": len(available_functions),
            "required_functions": required_functions,
            "missing_required_functions": [
                name for name in required_functions if name not in available_functions
            ],
        }

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 50,
        email: str | None = None,
        state: UserState = "all",
        refresh: bool = False,
    ) -> dict[str, Any]:
        entry, cached = await self._users(refresh=refresh)
        items = entry.items

        query = _search_text(email)
        if query:
            items = [
                item
                for item in items
                if query in _search_text(item.get("email"))
            ]

        status_by_filter = {
            "active": "ACTIVO",
            "suspended": "SUSPENDIDO",
            "unconfirmed": "NO_CONFIRMADO",
        }
        if state != "all":
            expected_status = status_by_filter[state]
            items = [item for item in items if item["status"] == expected_status]

        items = sorted(items, key=lambda item: (_search_text(item["fullname"]), item["id"]))
        return self._page(
            items,
            page=page,
            page_size=page_size,
            cached=cached,
            fetched_at=entry.fetched_at,
            moodle_function=USERS_FUNCTION,
        )

    async def list_courses(
        self,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        visibility: CourseVisibility = "all",
        category_id: int | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        entry, cached = await self._courses(refresh=refresh)
        items = entry.items

        query = _search_text(search)
        if query:
            fields = ("fullname", "displayname", "shortname", "idnumber", "categoryname")
            items = [
                item
                for item in items
                if any(query in _search_text(item.get(field)) for field in fields)
            ]

        if visibility == "visible":
            items = [item for item in items if item["visible"]]
        elif visibility == "hidden":
            items = [item for item in items if not item["visible"]]

        if category_id is not None:
            items = [item for item in items if item["categoryid"] == category_id]

        items = sorted(
            items,
            key=lambda item: (
                _search_text(item["categoryname"]),
                _search_text(item["fullname"]),
                item["id"],
            ),
        )
        return self._page(
            items,
            page=page,
            page_size=page_size,
            cached=cached,
            fetched_at=entry.fetched_at,
            moodle_function=COURSES_FUNCTION,
        )

    async def get_course_resources(
        self,
        course_id: int,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        courses_entry, _courses_cached = await self._courses(refresh=refresh)
        course = next((item for item in courses_entry.items if item["id"] == course_id), None)
        if course is None and not refresh:
            courses_entry, _courses_cached = await self._courses(refresh=True)
            course = next((item for item in courses_entry.items if item["id"] == course_id), None)
        if course is None:
            raise MoodleCourseNotFoundError("No se encontró el curso solicitado en Moodle")

        contents_entry, cached = await self._course_contents(
            course_id,
            refresh=refresh,
        )
        modules = [
            module
            for section in contents_entry.items
            for module in section.get("modules", [])
        ]
        files = [
            content
            for module in modules
            for content in module.get("contents", [])
            if content.get("filename")
        ]
        links = [
            link
            for module in modules
            for link in module.get("links", [])
            if link.get("url")
        ]
        section_updates_enabled = bool(
            self._settings.moodle_enabled
            and self._settings.moodle_writes_enabled
            and self._settings.moodle_section_updates_enabled
        )
        sections = [
            {
                **section,
                "edit_url": self._section_edit_url(section),
                "can_update_visibility": bool(
                    section_updates_enabled and _as_int(section.get("section")) > 0
                ),
                "can_update_name": bool(
                    section_updates_enabled
                ),
            }
            for section in contents_entry.items
        ]
        return {
            "course": dict(course),
            "sections": sections,
            "totals": {
                "sections": len(contents_entry.items),
                "modules": len(modules),
                "files": len(files),
                "links": len(links),
                "visible_modules": sum(
                    1
                    for module in modules
                    if module.get("visible") and module.get("uservisible")
                ),
            },
            "source": {
                "cached": cached,
                "fetched_at": contents_entry.fetched_at.isoformat(),
                "moodle_function": COURSE_CONTENTS_FUNCTION,
            },
            "section_management": {
                "name_updates_enabled": section_updates_enabled,
                "visibility_updates_enabled": section_updates_enabled,
                "full_edit_in_moodle": False,
            },
        }

    async def get_all_courses(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return the normalized Moodle catalog for exact academic matching."""
        entry, _cached = await self._courses(refresh=refresh)
        return [dict(item) for item in entry.items]

    async def get_course_enrolled_emails(
        self,
        course_id: int,
        *,
        refresh: bool = False,
    ) -> set[str]:
        entry, _cached = await self._course_enrolled_users(
            course_id,
            refresh=refresh,
        )
        return {
            normalized_email
            for item in entry.items
            if (normalized_email := normalize_email_identity(item.get("email")))
        }

    async def get_course_enrolled_users(
        self,
        course_id: int,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        entry, _cached = await self._course_enrolled_users(
            course_id,
            refresh=refresh,
        )
        return [dict(item) for item in entry.items]

    async def get_course_grade_items(
        self,
        course_id: int,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        grade_result, contents_result = await asyncio.gather(
            self._course_grade_items(course_id, refresh=refresh),
            self._course_contents(course_id, refresh=refresh),
        )
        return self._grade_items_with_course_sections(
            grade_result[0].items,
            contents_result[0].items,
        )

    async def open_course_resource_file(
        self,
        course_id: int,
        module_id: int,
        file_index: int,
    ) -> tuple[dict[str, Any], MoodleFileStream]:
        resources = await self.get_course_resources(course_id)
        module = next(
            (
                item
                for section in resources["sections"]
                for item in section.get("modules", [])
                if _as_int(item.get("id")) == module_id
            ),
            None,
        )
        if module is None:
            raise MoodleResourceNotFoundError(
                "No se encontró la actividad solicitada dentro del curso"
            )

        files = [
            item
            for item in module.get("contents", [])
            if _as_text(item.get("filename")) and _as_text(item.get("fileurl"))
        ]
        if file_index < 0 or file_index >= len(files):
            raise MoodleResourceNotFoundError(
                "No se encontró el archivo solicitado dentro de la actividad"
            )

        content = dict(files[file_index])
        file_url = _as_text(content.pop("fileurl", ""))
        stream = await self._client.open_file(file_url)
        return {
            "course_id": course_id,
            "module_id": module_id,
            "module_name": _as_text(module.get("name")),
            "content": content,
        }, stream

    async def set_section_visibility(
        self,
        course_id: int,
        section_id: int,
        *,
        visible: bool,
    ) -> dict[str, Any]:
        resources = await self.get_course_resources(course_id)
        section = next(
            (
                item
                for item in resources["sections"]
                if _as_int(item.get("id")) == section_id
            ),
            None,
        )
        if section is None:
            resources = await self.get_course_resources(course_id, refresh=True)
            section = next(
                (
                    item
                    for item in resources["sections"]
                    if _as_int(item.get("id")) == section_id
                ),
                None,
            )
        if section is None:
            raise MoodleSectionNotFoundError(
                "No se encontró la sección solicitada dentro del curso"
            )
        if _as_int(section.get("section")) <= 0:
            raise MoodleSectionUpdateError(
                "La sección general del curso debe administrarse directamente en Moodle"
            )

        current_visible = _as_bool(section.get("visible"))
        if current_visible == visible:
            return {
                "ok": True,
                "changed": False,
                "message": (
                    "La sección ya se encuentra visible."
                    if visible
                    else "La sección ya se encuentra oculta."
                ),
                "section": dict(section),
                "audit_recorded": False,
            }

        before = {
            "id": section_id,
            "section": _as_int(section.get("section")),
            "name": _as_text(section.get("name")),
            "visible": current_visible,
        }
        await self._client.edit_section_visibility(
            section_id,
            section_number=before["section"],
            visible=visible,
        )

        refreshed = await self.get_course_resources(course_id, refresh=True)
        updated = next(
            (
                item
                for item in refreshed["sections"]
                if _as_int(item.get("id")) == section_id
            ),
            {**section, "visible": visible},
        )
        after = {
            "id": section_id,
            "section": _as_int(updated.get("section")),
            "name": _as_text(updated.get("name")),
            "visible": _as_bool(updated.get("visible")),
        }
        audit_recorded = await asyncio.to_thread(
            self._section_auditor,
            before,
            after,
            {
                "course_id": course_id,
                "course_name": _as_text(resources["course"].get("fullname")),
            },
        )
        logger.info(
            "Sección Moodle actualizada course_id=%s section_id=%s visible=%s",
            course_id,
            section_id,
            visible,
        )
        return {
            "ok": True,
            "changed": True,
            "message": (
                "La sección se mostró correctamente."
                if visible
                else "La sección se ocultó correctamente."
            ),
            "section": dict(updated),
            "audit_recorded": audit_recorded,
        }

    async def set_section_name(
        self,
        course_id: int,
        section_id: int,
        *,
        name: str,
    ) -> dict[str, Any]:
        clean_name = _as_text(name)
        if not clean_name or len(clean_name) > 1333:
            raise MoodleSectionUpdateError(
                "El nombre de la sección debe tener entre 1 y 1333 caracteres"
            )

        resources = await self.get_course_resources(course_id)
        section = next(
            (
                item
                for item in resources["sections"]
                if _as_int(item.get("id")) == section_id
            ),
            None,
        )
        if section is None:
            resources = await self.get_course_resources(course_id, refresh=True)
            section = next(
                (
                    item
                    for item in resources["sections"]
                    if _as_int(item.get("id")) == section_id
                ),
                None,
            )
        if section is None:
            raise MoodleSectionNotFoundError(
                "No se encontró la sección solicitada dentro del curso"
            )
        current_name = _as_text(section.get("name"))
        if current_name == clean_name:
            return {
                "ok": True,
                "changed": False,
                "message": "La sección ya tiene ese nombre.",
                "section": dict(section),
                "audit_recorded": False,
            }

        before = {
            "id": section_id,
            "section": _as_int(section.get("section")),
            "name": current_name,
            "visible": _as_bool(section.get("visible")),
        }
        course_format = _as_text(resources["course"].get("format")) or "topics"
        await self._client.edit_section_name(
            section_id,
            course_format=course_format,
            name=clean_name,
        )

        refreshed = await self.get_course_resources(course_id, refresh=True)
        updated = next(
            (
                item
                for item in refreshed["sections"]
                if _as_int(item.get("id")) == section_id
            ),
            {**section, "name": clean_name},
        )
        after = {
            "id": section_id,
            "section": _as_int(updated.get("section")),
            "name": _as_text(updated.get("name")) or clean_name,
            "visible": _as_bool(updated.get("visible")),
        }
        audit_recorded = await asyncio.to_thread(
            self._section_auditor,
            before,
            after,
            {
                "course_id": course_id,
                "course_name": _as_text(resources["course"].get("fullname")),
            },
        )
        logger.info(
            "Nombre de sección Moodle actualizado course_id=%s section_id=%s",
            course_id,
            section_id,
        )
        return {
            "ok": True,
            "changed": True,
            "message": "El nombre de la sección se actualizó correctamente.",
            "section": dict(updated),
            "audit_recorded": audit_recorded,
        }

    async def set_user_active(self, user_id: int, *, active: bool) -> dict[str, Any]:
        entry, _cached = await self._users(refresh=False)
        target = next((item for item in entry.items if item["id"] == user_id), None)
        if target is None:
            entry, _cached = await self._users(refresh=True)
            target = next((item for item in entry.items if item["id"] == user_id), None)
        if target is None:
            raise MoodleUserNotFoundError("No se encontró el usuario solicitado en Moodle")

        if not target["confirmed"]:
            raise MoodleUserNotConfirmedError(
                "La cuenta Moodle todavía no está confirmada y no puede cambiarse desde esta opción"
            )

        institutional_validation = await asyncio.to_thread(
            self._institutional_email_validator,
            target["email"],
        )
        desired_suspended = not active
        if target["suspended"] == desired_suspended:
            action = "activa" if active else "inactiva"
            return {
                "ok": True,
                "changed": False,
                "message": f"La cuenta ya se encuentra {action}.",
                "user": dict(target),
                "institutional_validation": institutional_validation,
                "audit_recorded": False,
            }

        before = dict(target)
        await self._client.update_user_suspension(user_id, suspended=desired_suspended)
        target["suspended"] = desired_suspended
        target["status"] = "SUSPENDIDO" if desired_suspended else "ACTIVO"
        after = dict(target)

        audit_recorded = await asyncio.to_thread(
            self._status_auditor,
            before,
            after,
            institutional_validation,
        )
        action = "activó" if active else "inactivó"
        logger.info(
            "Cuenta Moodle actualizada action=%s moodle_user_id=%s student_code=%s",
            action,
            user_id,
            institutional_validation.get("codigo_estud"),
        )
        return {
            "ok": True,
            "changed": True,
            "message": f"La cuenta se {action} correctamente.",
            "user": after,
            "institutional_validation": institutional_validation,
            "audit_recorded": audit_recorded,
        }

    async def _users(self, *, refresh: bool) -> tuple[_CacheEntry, bool]:
        current = None if refresh else self._valid_cache(self._users_cache)
        if current is not None:
            return current, True

        async with self._users_lock:
            if refresh:
                self._users_cache = None
            current = self._valid_cache(self._users_cache)
            if current is not None:
                return current, True
            raw_users = await self._client.get_all_users()
            if len(raw_users) > int(self._settings.moodle_max_user_scan_items):
                raise MoodleResultLimitExceededError(
                    "La consulta de usuarios Moodle superó el límite configurado"
                )
            entry = self._cache_entry([self._normalize_user(item) for item in raw_users])
            self._users_cache = entry
            return entry, False

    async def _courses(self, *, refresh: bool) -> tuple[_CacheEntry, bool]:
        current = None if refresh else self._valid_cache(self._courses_cache)
        if current is not None:
            return current, True

        async with self._courses_lock:
            if refresh:
                self._courses_cache = None
            current = self._valid_cache(self._courses_cache)
            if current is not None:
                return current, True
            raw_courses = await self._client.get_all_courses()
            entry = self._cache_entry([self._normalize_course(item) for item in raw_courses])
            self._courses_cache = entry
            return entry, False

    async def _course_contents(
        self,
        course_id: int,
        *,
        refresh: bool,
    ) -> tuple[_CacheEntry, bool]:
        current = None if refresh else self._valid_cache(
            self._course_contents_cache.get(course_id)
        )
        if current is not None:
            return current, True

        async with self._course_contents_lock:
            if refresh:
                self._course_contents_cache.pop(course_id, None)
            current = self._valid_cache(self._course_contents_cache.get(course_id))
            if current is not None:
                return current, True
            raw_sections = await self._client.get_course_contents(course_id)
            if self._contains_url_modules(raw_sections):
                get_external_urls = getattr(self._client, "get_course_external_urls", None)
                if callable(get_external_urls):
                    try:
                        external_urls = await get_external_urls(course_id)
                    except MoodleError as exc:
                        logger.info(
                            "Moodle no permitió ampliar los enlaces externos del curso %s (%s)",
                            course_id,
                            type(exc).__name__,
                        )
                    else:
                        self._attach_external_urls(raw_sections, external_urls)
            entry = self._cache_entry(
                [self._normalize_course_section(item) for item in raw_sections]
            )
            self._course_contents_cache[course_id] = entry
            return entry, False

    async def _course_enrolled_users(
        self,
        course_id: int,
        *,
        refresh: bool,
    ) -> tuple[_CacheEntry, bool]:
        current = None if refresh else self._valid_cache(
            self._course_enrolled_users_cache.get(course_id)
        )
        if current is not None:
            return current, True

        lock = self._course_enrolled_users_locks.setdefault(course_id, asyncio.Lock())
        async with lock:
            if refresh:
                self._course_enrolled_users_cache.pop(course_id, None)
            current = self._valid_cache(self._course_enrolled_users_cache.get(course_id))
            if current is not None:
                return current, True
            raw_users = await self._client.get_course_enrolled_users(course_id)
            entry = self._cache_entry([self._normalize_user(item) for item in raw_users])
            self._course_enrolled_users_cache[course_id] = entry
            return entry, False

    async def _course_grade_items(
        self,
        course_id: int,
        *,
        refresh: bool,
    ) -> tuple[_CacheEntry, bool]:
        current = None if refresh else self._valid_cache(
            self._course_grade_items_cache.get(course_id)
        )
        if current is not None:
            return current, True

        lock = self._course_grade_items_locks.setdefault(course_id, asyncio.Lock())
        async with lock:
            if refresh:
                self._course_grade_items_cache.pop(course_id, None)
            current = self._valid_cache(self._course_grade_items_cache.get(course_id))
            if current is not None:
                return current, True
            raw_grades = await self._client.get_course_grade_items(course_id)
            entry = self._cache_entry([dict(item) for item in raw_grades])
            self._course_grade_items_cache[course_id] = entry
            return entry, False

    def _cache_entry(self, items: list[dict[str, Any]]) -> _CacheEntry:
        now = datetime.now(timezone.utc)
        return _CacheEntry(
            items=items,
            fetched_at=now,
            expires_at=time.monotonic() + int(self._settings.moodle_cache_ttl_seconds),
        )

    @staticmethod
    def _valid_cache(entry: _CacheEntry | None) -> _CacheEntry | None:
        if entry and entry.expires_at > time.monotonic():
            return entry
        return None

    @staticmethod
    def _validate_institutional_email(email: str) -> dict[str, Any]:
        normalized_email = normalize_email_identity(email)
        if not normalized_email:
            raise MoodleInstitutionalEmailNotFoundError(
                "El usuario Moodle no tiene un correo institucional válido"
            )

        try:
            with get_connection() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT TOP (2)
                        TRY_CONVERT(int, de.codigo_estud) AS codigo_estud,
                        MAX(LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), de.Apellidos_nombre)))) AS estudiante,
                        MIN(LTRIM(RTRIM(TRY_CONVERT(nvarchar(254), ce.CorreoIntec)))) AS correo_intec
                    FROM dbo.CorreosEstudIntec AS ce
                    INNER JOIN dbo.DATOS_ESTUD AS de
                        ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, ce.codestud)
                    WHERE LOWER(LTRIM(RTRIM(
                        REPLACE(REPLACE(REPLACE(
                            TRY_CONVERT(nvarchar(254), ce.CorreoIntec),
                            NCHAR(160), N' '
                        ), NCHAR(8203), N''), NCHAR(65279), N'')
                    ))) COLLATE Latin1_General_100_CI_AS = ? COLLATE Latin1_General_100_CI_AS
                    GROUP BY TRY_CONVERT(int, de.codigo_estud)
                    ORDER BY TRY_CONVERT(int, de.codigo_estud);
                    """,
                    normalized_email,
                )
                rows = cursor.fetchall()
                cursor.close()
        except MoodleInstitutionalEmailNotFoundError:
            raise
        except Exception as exc:
            logger.exception("No se pudo validar el correo institucional en INTECBDD")
            raise MoodleInstitutionalEmailValidationError(
                "No fue posible validar el correo institucional en INTECBDD"
            ) from exc

        if not rows:
            raise MoodleInstitutionalEmailNotFoundError(
                "El correo del usuario Moodle no existe en INTECBDD.dbo.CorreosEstudIntec"
            )
        if len(rows) > 1:
            raise MoodleInstitutionalEmailValidationError(
                "El correo institucional está asociado a más de un estudiante en INTECBDD"
            )
        row = rows[0]
        return {
            "validated": True,
            "codigo_estud": _as_int(row[0]),
            "estudiante": _as_text(row[1]),
            "correo_intec": normalize_email_identity(row[2]),
        }

    @staticmethod
    def _record_status_audit(
        before: dict[str, Any],
        after: dict[str, Any],
        institutional_validation: dict[str, Any],
    ) -> bool:
        try:
            with get_integration_control_connection() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    EXEC aud.sp_RegistrarCambio
                        @BaseDatos=?,
                        @Esquema=?,
                        @Objeto=?,
                        @Operacion=?,
                        @CantidadFilas=?,
                        @ColumnasAfectadas=?,
                        @ClavesAfectadas=?,
                        @DatosAntes=?,
                        @DatosDespues=?,
                        @MuestraLimitada=?;
                    """,
                    "MOODLE",
                    "core",
                    "user",
                    "UPDATE",
                    1,
                    "suspended",
                    json.dumps(
                        {
                            "moodle_user_id": before.get("id"),
                            "codigo_estud": institutional_validation.get("codigo_estud"),
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {"status": before.get("status")},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {"status": after.get("status")},
                        ensure_ascii=False,
                    ),
                    0,
                )
                connection.commit()
                cursor.close()
            return True
        except Exception:
            logger.exception("No se pudo registrar la auditoría del estado Moodle")
            return False

    @staticmethod
    def _record_section_audit(
        before: dict[str, Any],
        after: dict[str, Any],
        course: dict[str, Any],
    ) -> bool:
        try:
            with get_integration_control_connection() as connection:
                cursor = connection.cursor()
                changed_columns = ",".join(
                    field
                    for field in ("name", "visible")
                    if before.get(field) != after.get(field)
                ) or "section"
                cursor.execute(
                    """
                    EXEC aud.sp_RegistrarCambio
                        @BaseDatos=?,
                        @Esquema=?,
                        @Objeto=?,
                        @Operacion=?,
                        @CantidadFilas=?,
                        @ColumnasAfectadas=?,
                        @ClavesAfectadas=?,
                        @DatosAntes=?,
                        @DatosDespues=?,
                        @MuestraLimitada=?;
                    """,
                    "MOODLE",
                    "core",
                    "course_section",
                    "UPDATE",
                    1,
                    changed_columns,
                    json.dumps(
                        {
                            "course_id": course.get("course_id"),
                            "section_id": before.get("id"),
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False),
                    0,
                )
                connection.commit()
                cursor.close()
            return True
        except Exception:
            logger.exception("No se pudo registrar la auditoría de la sección Moodle")
            return False

    @staticmethod
    def _function_names(value: Any) -> set[str]:
        if not isinstance(value, list):
            return set()
        names: set[str] = set()
        for item in value:
            name = item.get("name") if isinstance(item, dict) else item
            if _as_text(name):
                names.add(_as_text(name))
        return names

    @staticmethod
    def _normalize_user(item: dict[str, Any]) -> dict[str, Any]:
        firstname = _as_text(item.get("firstname"))
        lastname = _as_text(item.get("lastname"))
        fullname = _as_text(item.get("fullname")) or f"{firstname} {lastname}".strip()
        suspended = _as_bool(item.get("suspended"))
        confirmed = _as_bool(item.get("confirmed"))
        status = "SUSPENDIDO" if suspended else ("ACTIVO" if confirmed else "NO_CONFIRMADO")
        return {
            "id": _as_int(item.get("id")),
            "username": _as_text(item.get("username")),
            "firstname": firstname,
            "lastname": lastname,
            "fullname": fullname,
            "email": _as_text(item.get("email")),
            "idnumber": _as_text(item.get("idnumber")),
            "institution": _as_text(item.get("institution")),
            "department": _as_text(item.get("department")),
            "auth": _as_text(item.get("auth")),
            "suspended": suspended,
            "confirmed": confirmed,
            "firstaccess": _as_int(item.get("firstaccess")),
            "lastaccess": _as_int(item.get("lastaccess")),
            "profileimageurlsmall": _as_text(item.get("profileimageurlsmall")),
            "status": status,
        }

    @staticmethod
    def _normalize_course(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _as_int(item.get("id")),
            "fullname": _as_text(item.get("fullname")),
            "displayname": _as_text(item.get("displayname")),
            "shortname": _as_text(item.get("shortname")),
            "idnumber": _as_text(item.get("idnumber")),
            "categoryid": _as_int(item.get("categoryid")),
            "categoryname": _as_text(item.get("categoryname")),
            "summary": _summary_as_plain_text(item.get("summary")),
            "format": _as_text(item.get("format")),
            "visible": _as_bool(item.get("visible")),
            "startdate": _as_int(item.get("startdate")),
            "enddate": _as_int(item.get("enddate")),
            "enablecompletion": _as_bool(item.get("enablecompletion")),
            "timecreated": _as_int(item.get("timecreated")),
            "timemodified": _as_int(item.get("timemodified")),
        }

    @staticmethod
    def _safe_url(value: Any) -> str:
        raw = _as_text(value)
        if not raw:
            return ""
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return ""
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
            return ""
        if parsed.username or parsed.password:
            return ""
        safe_query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.casefold() not in {"token", "wstoken"}
            ],
            doseq=True,
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment))

    @staticmethod
    def _contains_url_modules(sections: list[dict[str, Any]]) -> bool:
        return any(
            _as_text(module.get("modname")).casefold() == "url"
            for section in sections
            for module in (
                section.get("modules")
                if isinstance(section.get("modules"), list)
                else []
            )
            if isinstance(module, dict)
        )

    @staticmethod
    def _attach_external_urls(
        sections: list[dict[str, Any]],
        external_urls: list[dict[str, Any]],
    ) -> None:
        by_instance = {
            _as_int(item.get("id")): item
            for item in external_urls
            if _as_int(item.get("id")) > 0
        }
        by_course_module = {
            _as_int(item.get("coursemodule")): item
            for item in external_urls
            if _as_int(item.get("coursemodule")) > 0
        }
        for section in sections:
            modules = (
                section.get("modules")
                if isinstance(section.get("modules"), list)
                else []
            )
            for module in modules:
                if (
                    not isinstance(module, dict)
                    or _as_text(module.get("modname")).casefold() != "url"
                ):
                    continue
                external = by_instance.get(_as_int(module.get("instance")))
                if external is None:
                    external = by_course_module.get(_as_int(module.get("id")))
                if external is None:
                    continue
                module["externalurl"] = external.get("externalurl")
                module["externalintro"] = external.get("intro")

    @staticmethod
    def _external_link_provider(url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path.casefold()

        def belongs_to(domain: str) -> bool:
            return hostname == domain or hostname.endswith(f".{domain}")

        if belongs_to("drive.google.com"):
            provider = "Google Drive"
        elif belongs_to("docs.google.com"):
            if path.startswith("/spreadsheets"):
                provider = "Google Sheets"
            elif path.startswith("/presentation"):
                provider = "Google Slides"
            elif path.startswith("/forms"):
                provider = "Google Forms"
            else:
                provider = "Google Docs"
        elif belongs_to("forms.gle"):
            provider = "Google Forms"
        elif belongs_to("canva.com"):
            provider = "Canva"
        elif belongs_to("1drv.ms") or belongs_to("onedrive.live.com"):
            provider = "Microsoft OneDrive"
        elif belongs_to("sharepoint.com"):
            provider = "Microsoft SharePoint"
        elif belongs_to("youtube.com") or belongs_to("youtu.be"):
            provider = "YouTube"
        elif belongs_to("vimeo.com"):
            provider = "Vimeo"
        elif belongs_to("dropbox.com"):
            provider = "Dropbox"
        else:
            provider = "Enlace web"
        return provider, hostname

    @classmethod
    def _normalize_external_link(cls, label: Any, value: Any) -> dict[str, str] | None:
        url = cls._safe_url(value)
        if not url:
            return None
        provider, domain = cls._external_link_provider(url)
        normalized_label = _summary_as_plain_text(label)
        if not normalized_label or normalized_label.casefold().startswith(("http://", "https://")):
            normalized_label = provider
        return {
            "name": normalized_label[:180],
            "url": url,
            "provider": provider,
            "domain": domain,
        }

    @classmethod
    def _extract_resource_links(cls, item: dict[str, Any]) -> list[dict[str, str]]:
        candidates: list[tuple[str, str]] = []
        explicit_url = _as_text(item.get("externalurl"))
        if explicit_url:
            candidates.append((_as_text(item.get("name")), explicit_url))

        source_values = [
            item.get("description"),
            item.get("availabilityinfo"),
            item.get("content"),
            item.get("summary"),
            item.get("intro"),
            item.get("externalintro"),
        ]
        contents = item.get("contents") if isinstance(item.get("contents"), list) else []
        for content in contents:
            if not isinstance(content, dict):
                continue
            source_values.extend(
                [
                    content.get("content"),
                    content.get("description"),
                    content.get("summary"),
                ]
            )

        for source_value in source_values:
            raw = _as_text(source_value)
            if not raw:
                continue
            parser = _ResourceLinkParser()
            try:
                parser.feed(raw)
                parser.close()
                candidates.extend(parser.links())
            except (ValueError, AssertionError):
                pass
            plain_text = _summary_as_plain_text(raw)
            candidates.extend(
                ("", match.group(0).rstrip(".,;:!?)]}"))
                for match in _BARE_URL_PATTERN.finditer(plain_text)
            )

        links: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for label, raw_url in candidates:
            link = cls._normalize_external_link(label, raw_url)
            if link is None or link["url"] in seen_urls:
                continue
            seen_urls.add(link["url"])
            links.append(link)
        return links

    def _section_edit_url(self, section: dict[str, Any]) -> str:
        base_url = _as_text(self._settings.moodle_base_url).rstrip("/")
        if not base_url or _as_int(section.get("id")) <= 0:
            return ""
        return f"{base_url}/course/editsection.php?{urlencode({'id': _as_int(section.get('id')), 'sr': _as_int(section.get('section'))})}"

    @classmethod
    def _grade_items_with_course_sections(
        cls,
        grade_groups: list[dict[str, Any]],
        sections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        module_index: dict[tuple[str, int], dict[str, Any] | None] = {}
        for section in sections:
            section_name = _as_text(section.get("name"))
            section_visible = _as_bool(section.get("visible")) and _as_bool(
                section.get("uservisible", section.get("visible"))
            )
            evaluation_section = cls._is_evaluation_section_name(section_name)
            modules = section.get("modules") if isinstance(section.get("modules"), list) else []
            for module_order, module in enumerate(modules, start=1):
                if not isinstance(module, dict):
                    continue
                key = (
                    _as_text(module.get("modname")).casefold(),
                    _as_int(module.get("instance")),
                )
                if not key[0] or key[1] <= 0:
                    continue
                metadata = {
                    "course_section_id": _as_int(section.get("id")),
                    "course_section_number": _as_int(section.get("section")),
                    "course_section_name": section_name,
                    "course_section_visible": section_visible,
                    "course_module_id": _as_int(module.get("id")),
                    "course_module_order": module_order,
                    "course_module_name": _as_text(module.get("name")),
                    "course_module_visible": _as_bool(module.get("visible"))
                    and _as_bool(module.get("uservisible", module.get("visible"))),
                    "evaluation_scope": evaluation_section,
                }
                # Una coincidencia duplicada no es suficientemente segura para migrar notas.
                module_index[key] = metadata if key not in module_index else None

        enriched_groups: list[dict[str, Any]] = []
        for group in grade_groups:
            enriched_group = dict(group)
            raw_items = group.get("gradeitems") if isinstance(group.get("gradeitems"), list) else []
            enriched_items: list[dict[str, Any]] = []
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                item = dict(raw_item)
                key = (
                    _as_text(item.get("itemmodule")).casefold(),
                    _as_int(item.get("iteminstance")),
                )
                metadata = module_index.get(key)
                if metadata:
                    item.update(metadata)
                else:
                    item.update(
                        {
                            "course_section_id": 0,
                            "course_section_number": 0,
                            "course_section_name": "",
                            "course_section_visible": False,
                            "course_module_id": 0,
                            "course_module_order": 0,
                            "course_module_name": "",
                            "course_module_visible": False,
                            "evaluation_scope": False,
                        }
                    )
                enriched_items.append(item)
            enriched_group["gradeitems"] = enriched_items
            enriched_groups.append(enriched_group)
        return enriched_groups

    @staticmethod
    def _is_evaluation_section_name(value: Any) -> bool:
        tokens = re.findall(r"[a-z0-9]+", _search_text(value))
        return any(token in {"evaluacion", "evaluaciones"} for token in tokens)

    @classmethod
    def _normalize_course_section(cls, item: dict[str, Any]) -> dict[str, Any]:
        section_number = _as_int(item.get("section"))
        modules = item.get("modules") if isinstance(item.get("modules"), list) else []
        return {
            "id": _as_int(item.get("id")),
            "section": section_number,
            "name": _as_text(item.get("name")) or f"Sección {section_number}",
            "summary": _summary_as_plain_text(item.get("summary")),
            "visible": _as_bool(item.get("visible")),
            "uservisible": _as_bool(item.get("uservisible", item.get("visible"))),
            "modules": [
                cls._normalize_course_module(module)
                for module in modules
                if isinstance(module, dict)
            ],
        }

    @classmethod
    def _normalize_course_module(cls, item: dict[str, Any]) -> dict[str, Any]:
        contents = item.get("contents") if isinstance(item.get("contents"), list) else []
        dates = item.get("dates") if isinstance(item.get("dates"), list) else []
        links = cls._extract_resource_links(item)
        completion_data = (
            item.get("completiondata")
            if isinstance(item.get("completiondata"), dict)
            else {}
        )
        return {
            "id": _as_int(item.get("id")),
            "url": cls._safe_url(item.get("url")),
            "name": _as_text(item.get("name")) or "Recurso sin nombre",
            "instance": _as_int(item.get("instance")),
            "contextid": _as_int(item.get("contextid")),
            "visible": _as_bool(item.get("visible")),
            "uservisible": _as_bool(item.get("uservisible", item.get("visible"))),
            "visibleoncoursepage": _as_bool(item.get("visibleoncoursepage", True)),
            "availabilityinfo": _summary_as_plain_text(item.get("availabilityinfo")),
            "description": _summary_as_plain_text(item.get("description")),
            "modicon": cls._safe_url(item.get("modicon")),
            "modname": _as_text(item.get("modname")),
            "modplural": _as_text(item.get("modplural")),
            "indent": _as_int(item.get("indent")),
            "noviewlink": _as_bool(item.get("noviewlink")),
            "completion": _as_int(item.get("completion")),
            "completiondata": {
                "state": _as_int(completion_data.get("state")),
                "timecompleted": _as_int(completion_data.get("timecompleted")),
                "overrideby": _as_int(completion_data.get("overrideby")),
                "valueused": _as_bool(completion_data.get("valueused")),
                "hascompletion": _as_bool(completion_data.get("hascompletion")),
                "uservisible": _as_bool(completion_data.get("uservisible", True)),
            },
            "dates": [
                {
                    "label": _as_text(date.get("label")),
                    "timestamp": _as_int(date.get("timestamp")),
                    "dataid": _as_text(date.get("dataid")),
                }
                for date in dates
                if isinstance(date, dict)
            ],
            "links": links,
            "contents": [
                cls._normalize_course_content(content)
                for content in contents
                if isinstance(content, dict)
            ],
        }

    @classmethod
    def _normalize_course_content(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": _as_text(item.get("type")),
            "filename": _as_text(item.get("filename")),
            "filepath": _as_text(item.get("filepath")),
            "filesize": max(0, _as_int(item.get("filesize"))),
            "fileurl": cls._safe_url(item.get("fileurl")),
            "timecreated": _as_int(item.get("timecreated")),
            "timemodified": _as_int(item.get("timemodified")),
            "sortorder": _as_int(item.get("sortorder")),
            "userid": _as_int(item.get("userid")),
            "author": _as_text(item.get("author")),
            "license": _as_text(item.get("license")),
            "mimetype": _as_text(item.get("mimetype")),
            "isexternalfile": _as_bool(item.get("isexternalfile")),
            "repositorytype": _as_text(item.get("repositorytype")),
        }

    @staticmethod
    def _page(
        items: list[dict[str, Any]],
        *,
        page: int,
        page_size: int,
        cached: bool,
        fetched_at: datetime,
        moodle_function: str,
    ) -> dict[str, Any]:
        total_items = len(items)
        total_pages = math.ceil(total_items / page_size) if total_items else 0
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": items[start:end],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
            "source": {
                "cached": cached,
                "fetched_at": fetched_at.isoformat(),
                "moodle_function": moodle_function,
            },
        }


__all__ = [
    "CourseVisibility",
    "MoodleReadService",
    "UserState",
]
