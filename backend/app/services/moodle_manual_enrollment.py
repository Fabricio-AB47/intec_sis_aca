from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from typing import Any, Literal

from app.core.config import Settings
from app.integrations.moodle.client import (
    COURSES_FUNCTION,
    ENROLLED_USERS_FUNCTION,
    MANUAL_ENROL_USERS_FUNCTION,
    SITE_INFO_FUNCTION,
    USERS_BY_FIELD_FUNCTION,
    USERS_FUNCTION,
    MoodleClient,
)
from app.integrations.moodle.exceptions import MoodleManualEnrollmentError
from app.services.db import get_integration_control_connection
from app.services.moodle_read_service import MoodleReadService

logger = logging.getLogger(__name__)

ManualEnrollmentRole = Literal["student", "teacher"]

MANUAL_ENROLLMENT_REQUIRED_FUNCTIONS = (
    SITE_INFO_FUNCTION,
    USERS_FUNCTION,
    USERS_BY_FIELD_FUNCTION,
    COURSES_FUNCTION,
    ENROLLED_USERS_FUNCTION,
    MANUAL_ENROL_USERS_FUNCTION,
)

_ROLE_LABELS: dict[ManualEnrollmentRole, str] = {
    "student": "Estudiante",
    "teacher": "Docente",
}
_ROLE_SHORTNAMES: dict[ManualEnrollmentRole, frozenset[str]] = {
    "student": frozenset({"student", "estudiante"}),
    "teacher": frozenset({"editingteacher", "docente", "profesor"}),
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _identity(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value).casefold())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _tokens(value: Any) -> tuple[str, ...]:
    return tuple(part for part in _identity(value).split() if part)


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class MoodleManualEnrollmentService:
    """Busca identidades y asigna roles Moodle con vista previa verificable."""

    def __init__(
        self,
        settings: Settings,
        read_service: MoodleReadService,
        client: MoodleClient | None = None,
        auditor: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._moodle = read_service
        self._client = client or MoodleClient(settings)
        self._auditor = auditor or self._record_audit
        self._write_lock = asyncio.Lock()

    async def catalog(self) -> dict[str, Any]:
        site_info, courses = await asyncio.gather(
            self._client.get_site_info(),
            self._moodle.get_all_courses(),
        )
        capability = self._capability(site_info)
        return {
            "capability": capability,
            "roles": [
                {
                    "key": role,
                    "label": _ROLE_LABELS[role],
                    "role_id": self._role_id(role),
                }
                for role in ("student", "teacher")
            ],
            "courses": [
                self._course_item(course)
                for course in courses
                if _integer(course.get("id")) > 1
            ],
            "limits": {"names": 100, "candidates_per_name": 20},
        }

    async def search(
        self,
        *,
        course_id: int,
        role: ManualEnrollmentRole,
        names: list[str],
        refresh: bool = False,
    ) -> dict[str, Any]:
        clean_names = self._clean_names(names)
        users, courses, enrolled_users, site_info = await asyncio.gather(
            self._moodle.get_all_users(refresh=refresh),
            self._moodle.get_all_courses(refresh=refresh),
            self._moodle.get_course_enrolled_users(course_id, refresh=refresh),
            self._client.get_site_info(),
        )
        course = self._require_course(courses, course_id)
        capability = self._capability(site_info)
        enrolled_by_id = {
            _integer(user.get("id")): user
            for user in enrolled_users
            if _integer(user.get("id")) > 0
        }
        search_index = self._search_index(users)

        queries: list[dict[str, Any]] = []
        for index, query in enumerate(clean_names, start=1):
            matches = self._find_candidates(query, search_index)
            candidates = [
                self._candidate_item(
                    user,
                    enrolled_by_id.get(_integer(user.get("id"))),
                    role,
                    match_type,
                    score,
                )
                for user, match_type, score in matches
            ]
            selectable = [item for item in candidates if item["selectable"]]
            if not candidates:
                status = "NO_ENCONTRADO"
                selected_user_id = None
            elif len(candidates) == 1:
                status = "UNICO"
                selected_user_id = candidates[0]["id"] if selectable else None
            else:
                status = "AMBIGUO"
                selected_user_id = None
            queries.append(
                {
                    "index": index,
                    "query": query,
                    "status": status,
                    "selected_user_id": selected_user_id,
                    "candidates": candidates,
                }
            )

        selected_ids = {
            _integer(item.get("selected_user_id"))
            for item in queries
            if _integer(item.get("selected_user_id")) > 0
        }
        return {
            "course": self._course_item(course),
            "role": role,
            "role_label": _ROLE_LABELS[role],
            "role_id": self._role_id(role),
            "capability": capability,
            "queries": queries,
            "summary": {
                "queries": len(queries),
                "unique": sum(item["status"] == "UNICO" for item in queries),
                "ambiguous": sum(item["status"] == "AMBIGUO" for item in queries),
                "not_found": sum(item["status"] == "NO_ENCONTRADO" for item in queries),
                "selected_users": len(selected_ids),
            },
        }

    async def preview(
        self,
        *,
        course_id: int,
        role: ManualEnrollmentRole,
        user_ids: list[int],
        refresh: bool = False,
    ) -> dict[str, Any]:
        selected_ids = self._clean_user_ids(user_ids)
        users_task = self._moodle.get_users_by_ids(selected_ids)
        courses_task = self._moodle.get_all_courses(refresh=refresh)
        enrolled_task = self._moodle.get_course_enrolled_users(course_id, refresh=refresh)
        site_task = self._client.get_site_info()
        users, courses, enrolled_users, site_info = await asyncio.gather(
            users_task,
            courses_task,
            enrolled_task,
            site_task,
        )
        course = self._require_course(courses, course_id)
        capability = self._capability(site_info)
        users_by_id = {
            _integer(user.get("id")): user
            for user in users
            if _integer(user.get("id")) > 0
        }
        enrolled_by_id = {
            _integer(user.get("id")): user
            for user in enrolled_users
            if _integer(user.get("id")) > 0
        }

        items = [
            self._preview_item(
                user_id,
                users_by_id.get(user_id),
                enrolled_by_id.get(user_id),
                role,
            )
            for user_id in selected_ids
        ]
        summary = {
            "selected": len(items),
            "ready": sum(item["status"] == "LISTO" for item in items),
            "existing": sum(item["status"] == "EXISTENTE" for item in items),
            "blocked": sum(item["status"] == "BLOQUEADO" for item in items),
            "new_enrollments": sum(item.get("action") == "MATRICULAR" for item in items),
            "role_additions": sum(item.get("action") == "ASIGNAR_ROL" for item in items),
        }
        fingerprint = self._fingerprint(course_id, role, items)
        can_apply = bool(
            capability["enabled"]
            and summary["ready"] > 0
            and summary["blocked"] == 0
        )
        return {
            "course": self._course_item(course),
            "role": role,
            "role_label": _ROLE_LABELS[role],
            "role_id": self._role_id(role),
            "capability": capability,
            "items": items,
            "summary": summary,
            "preview_fingerprint": fingerprint,
            "can_apply": can_apply,
        }

    async def apply(
        self,
        *,
        course_id: int,
        role: ManualEnrollmentRole,
        user_ids: list[int],
        preview_fingerprint: str,
        actor: str,
        actor_id: int | None = None,
    ) -> dict[str, Any]:
        async with self._write_lock:
            current = await self.preview(
                course_id=course_id,
                role=role,
                user_ids=user_ids,
                refresh=True,
            )
            if current["preview_fingerprint"] != preview_fingerprint:
                raise MoodleManualEnrollmentError(
                    "La matrícula del curso cambió. Genere una nueva vista previa "
                    "antes de continuar."
                )
            if current["summary"]["blocked"]:
                raise MoodleManualEnrollmentError(
                    "La selección contiene usuarios bloqueados y no puede aplicarse."
                )

            ready = [item for item in current["items"] if item["status"] == "LISTO"]
            if not ready:
                raise MoodleManualEnrollmentError(
                    "No existen usuarios nuevos por matricular o asignar al curso."
                )

            role_id = self._role_id(role)
            await self._client.manual_enrol_users(
                [
                    {
                        "roleid": role_id,
                        "userid": item["id"],
                        "courseid": course_id,
                    }
                    for item in ready
                ]
            )

            enrolled_after = await self._moodle.get_course_enrolled_users(
                course_id,
                refresh=True,
            )
            after_by_id = {
                _integer(user.get("id")): user
                for user in enrolled_after
                if _integer(user.get("id")) > 0
            }
            failed_ids = [
                item["id"]
                for item in ready
                if not self._has_target_role(after_by_id.get(item["id"]), role)
            ]
            if failed_ids:
                raise MoodleManualEnrollmentError(
                    "Moodle recibió la operación, pero no fue posible verificar "
                    "todos los roles asignados."
                )

            audit_before = {
                "course_id": course_id,
                "role": role,
                "role_id": role_id,
                "user_ids": [item["id"] for item in ready],
            }
            audit_after = {
                **audit_before,
                "actor": actor,
                "actor_id": actor_id,
                "verified": True,
            }
            audit_recorded = await asyncio.to_thread(
                self._auditor,
                audit_before,
                audit_after,
            )
            results = [
                {
                    **item,
                    "status": "MATRICULADO" if item["status"] == "LISTO" else item["status"],
                    "message": (
                        "Rol asignado y verificado en Moodle."
                        if item["status"] == "LISTO"
                        else item["message"]
                    ),
                }
                for item in current["items"]
            ]
            return {
                "ok": True,
                "course": current["course"],
                "role": role,
                "role_label": _ROLE_LABELS[role],
                "items": results,
                "summary": {
                    "processed": len(current["items"]),
                    "enrolled": len(ready),
                    "existing": current["summary"]["existing"],
                    "failed": 0,
                },
                "audit_recorded": audit_recorded,
                "warning": (
                    "La matrícula se completó, pero no se pudo registrar la auditoría local."
                    if not audit_recorded
                    else ""
                ),
            }

    def _capability(self, site_info: dict[str, Any]) -> dict[str, Any]:
        available = self._function_names(site_info.get("functions"))
        missing = [
            function
            for function in MANUAL_ENROLLMENT_REQUIRED_FUNCTIONS
            if function not in available
        ]
        configured = bool(
            self._settings.moodle_enabled
            and self._settings.moodle_reads_enabled
            and self._settings.moodle_writes_enabled
            and self._settings.moodle_manual_enrollment_enabled
            and self._settings.moodle_full_user_scan_enabled
        )
        enabled = configured and not missing
        if not self._settings.moodle_enabled:
            reason = "La integración con Moodle está deshabilitada."
        elif not self._settings.moodle_reads_enabled:
            reason = "Las consultas de Moodle están deshabilitadas."
        elif not self._settings.moodle_writes_enabled:
            reason = "Las escrituras de Moodle están deshabilitadas."
        elif not self._settings.moodle_manual_enrollment_enabled:
            reason = "La matrícula manual Moodle está deshabilitada."
        elif not self._settings.moodle_full_user_scan_enabled:
            reason = "La búsqueda controlada en el directorio Moodle está deshabilitada."
        elif missing:
            reason = "El servicio Moodle no publica: " + ", ".join(missing)
        else:
            reason = "La matrícula manual de estudiantes y docentes está habilitada."
        return {
            "enabled": enabled,
            "configured": configured,
            "reason": reason,
            "missing_functions": missing,
        }

    def _role_id(self, role: ManualEnrollmentRole) -> int:
        return int(
            self._settings.moodle_student_role_id
            if role == "student"
            else self._settings.moodle_teacher_role_id
        )

    @staticmethod
    def _clean_names(names: list[str]) -> list[str]:
        clean = list(dict.fromkeys(_text(name) for name in names if _text(name)))
        if not clean:
            raise MoodleManualEnrollmentError("Ingrese al menos un nombre para buscar.")
        if len(clean) > 100:
            raise MoodleManualEnrollmentError("Puede buscar un máximo de 100 nombres.")
        return clean

    @staticmethod
    def _clean_user_ids(user_ids: list[int]) -> list[int]:
        clean = list(dict.fromkeys(_integer(user_id) for user_id in user_ids))
        if not clean or any(user_id <= 0 for user_id in clean):
            raise MoodleManualEnrollmentError("Seleccione al menos un usuario Moodle válido.")
        if len(clean) > 100:
            raise MoodleManualEnrollmentError("Puede matricular un máximo de 100 usuarios.")
        return clean

    @staticmethod
    def _require_course(courses: list[dict[str, Any]], course_id: int) -> dict[str, Any]:
        if course_id <= 1:
            raise MoodleManualEnrollmentError("Seleccione un curso académico de Moodle.")
        course = next(
            (item for item in courses if _integer(item.get("id")) == course_id),
            None,
        )
        if course is None:
            raise MoodleManualEnrollmentError("El curso seleccionado ya no existe en Moodle.")
        return course

    @staticmethod
    def _course_item(course: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _integer(course.get("id")),
            "fullname": _text(course.get("fullname") or course.get("displayname")),
            "shortname": _text(course.get("shortname")),
            "idnumber": _text(course.get("idnumber")),
            "category": _text(course.get("categoryname")),
            "visible": bool(course.get("visible")),
        }

    @staticmethod
    def _search_index(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
        index: list[dict[str, Any]] = []
        for user in users:
            if _integer(user.get("id")) <= 0:
                continue
            full_variants = {
                _identity(user.get("fullname")),
                _identity(f"{_text(user.get('firstname'))} {_text(user.get('lastname'))}"),
                _identity(f"{_text(user.get('lastname'))} {_text(user.get('firstname'))}"),
            }
            full_variants.discard("")
            index.append(
                {
                    "user": user,
                    "exact": {
                        _text(user.get("email")).casefold(),
                        _text(user.get("username")).casefold(),
                        _text(user.get("idnumber")).casefold(),
                    }
                    - {""},
                    "full_variants": full_variants,
                    "name_tokens": set(
                        _tokens(
                            f"{_text(user.get('fullname'))} "
                            f"{_text(user.get('firstname'))} "
                            f"{_text(user.get('lastname'))}"
                        )
                    ),
                }
            )
        return index

    @staticmethod
    def _find_candidates(
        query: str,
        search_index: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], str, int]]:
        query_raw = _text(query).casefold()
        query_identity = _identity(query)
        query_tokens = _tokens(query)
        query_compact = query_identity.replace(" ", "")
        ranked: list[tuple[dict[str, Any], str, int]] = []
        for entry in search_index:
            user = entry["user"]
            full_variants = entry["full_variants"]
            name_tokens = entry["name_tokens"]
            if query_raw in entry["exact"]:
                match_type, score = "IDENTIDAD_EXACTA", 100
            elif query_identity in full_variants:
                match_type, score = "NOMBRE_EXACTO", 95
            elif query_tokens and set(query_tokens) == name_tokens:
                match_type, score = "NOMBRE_COMPLETO", 92
            elif query_tokens and all(token in name_tokens for token in query_tokens):
                match_type = "TODOS_LOS_NOMBRES"
                score = 80 + min(9, len(query_tokens))
            elif len(query_compact) >= 5 and any(
                query_identity in variant for variant in full_variants
            ):
                match_type, score = "NOMBRE_CONTENIDO", 70
            elif len(query_tokens) >= 2 and all(
                len(token) >= 2
                and any(name_token.startswith(token) for name_token in name_tokens)
                for token in query_tokens
            ):
                match_type, score = "PREFIJOS_DE_NOMBRE", 60
            else:
                continue
            ranked.append((user, match_type, score))

        ranked.sort(
            key=lambda item: (
                -item[2],
                _identity(item[0].get("fullname")),
                _integer(item[0].get("id")),
            )
        )
        if not ranked:
            return []
        best_score = ranked[0][2]
        # Exact matches must not be mixed with broader token matches.
        if best_score >= 90:
            ranked = [item for item in ranked if item[2] == best_score]
        return ranked[:20]

    def _candidate_item(
        self,
        user: dict[str, Any],
        enrolled: dict[str, Any] | None,
        role: ManualEnrollmentRole,
        match_type: str,
        score: int,
    ) -> dict[str, Any]:
        suspended = bool(user.get("suspended"))
        confirmed = bool(user.get("confirmed", True))
        already_target = self._has_target_role(enrolled, role)
        enrollment_suspended = bool(enrolled and enrolled.get("suspended"))
        if suspended:
            account_status = "SUSPENDIDO"
        elif not confirmed:
            account_status = "NO_CONFIRMADO"
        else:
            account_status = "ACTIVO"
        return {
            "id": _integer(user.get("id")),
            "fullname": _text(user.get("fullname")),
            "firstname": _text(user.get("firstname")),
            "lastname": _text(user.get("lastname")),
            "email": _text(user.get("email")),
            "username": _text(user.get("username")),
            "idnumber": _text(user.get("idnumber")),
            "account_status": account_status,
            "enrollment_status": (
                "SUSPENDIDA"
                if enrollment_suspended
                else "EXISTENTE"
                if already_target
                else ("OTRO_ROL" if enrolled is not None else "NO_MATRICULADO")
            ),
            "current_roles": self._role_items(enrolled),
            "already_target_role": already_target,
            "selectable": account_status == "ACTIVO" and not enrollment_suspended,
            "match_type": match_type,
            "match_score": score,
        }

    def _preview_item(
        self,
        user_id: int,
        user: dict[str, Any] | None,
        enrolled: dict[str, Any] | None,
        role: ManualEnrollmentRole,
    ) -> dict[str, Any]:
        if user is None:
            return {
                "id": user_id,
                "fullname": f"Usuario Moodle {user_id}",
                "email": "",
                "username": "",
                "status": "BLOQUEADO",
                "action": "NINGUNA",
                "message": "El usuario ya no existe o no está disponible en Moodle.",
                "current_roles": [],
            }
        base = {
            "id": user_id,
            "fullname": _text(user.get("fullname")),
            "email": _text(user.get("email")),
            "username": _text(user.get("username")),
            "current_roles": self._role_items(enrolled),
        }
        if bool(user.get("suspended")):
            return {
                **base,
                "status": "BLOQUEADO",
                "action": "NINGUNA",
                "message": "La cuenta Moodle está suspendida.",
            }
        if not bool(user.get("confirmed", True)):
            return {
                **base,
                "status": "BLOQUEADO",
                "action": "NINGUNA",
                "message": "La cuenta Moodle no está confirmada.",
            }
        if enrolled is not None and bool(enrolled.get("suspended")):
            return {
                **base,
                "status": "BLOQUEADO",
                "action": "NINGUNA",
                "message": "La matrícula actual del usuario en este curso está suspendida.",
            }
        if self._has_target_role(enrolled, role):
            return {
                **base,
                "status": "EXISTENTE",
                "action": "NINGUNA",
                "message": f"Ya tiene el rol {_ROLE_LABELS[role].lower()} en este curso.",
            }
        action = "ASIGNAR_ROL" if enrolled is not None else "MATRICULAR"
        return {
            **base,
            "status": "LISTO",
            "action": action,
            "message": (
                f"Se agregará el rol {_ROLE_LABELS[role].lower()} al usuario matriculado."
                if enrolled is not None
                else f"Se matriculará con rol {_ROLE_LABELS[role].lower()}."
            ),
        }

    def _has_target_role(
        self,
        enrolled: dict[str, Any] | None,
        role: ManualEnrollmentRole,
    ) -> bool:
        if not enrolled:
            return False
        role_id = self._role_id(role)
        shortnames = _ROLE_SHORTNAMES[role]
        return any(
            _integer(item.get("roleid") or item.get("id")) == role_id
            or _text(item.get("shortname")).casefold() in shortnames
            for item in self._raw_roles(enrolled)
        )

    @staticmethod
    def _raw_roles(enrolled: dict[str, Any] | None) -> list[dict[str, Any]]:
        roles = enrolled.get("roles") if isinstance(enrolled, dict) else None
        return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []

    @classmethod
    def _role_items(cls, enrolled: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [
            {
                "id": _integer(item.get("roleid") or item.get("id")),
                "name": _text(item.get("name")),
                "shortname": _text(item.get("shortname")),
            }
            for item in cls._raw_roles(enrolled)
        ]

    def _fingerprint(
        self,
        course_id: int,
        role: ManualEnrollmentRole,
        items: list[dict[str, Any]],
    ) -> str:
        payload = {
            "course_id": course_id,
            "role": role,
            "role_id": self._role_id(role),
            "items": [
                {
                    "id": item["id"],
                    "status": item["status"],
                    "action": item["action"],
                    "roles": sorted(
                        (
                            _integer(role_item.get("id")),
                            _text(role_item.get("shortname")).casefold(),
                        )
                        for role_item in item.get("current_roles", [])
                    ),
                }
                for item in sorted(items, key=lambda row: row["id"])
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _function_names(value: Any) -> set[str]:
        if not isinstance(value, list):
            return set()
        return {
            _text(item.get("name") if isinstance(item, dict) else item)
            for item in value
            if _text(item.get("name") if isinstance(item, dict) else item)
        }

    @staticmethod
    def _record_audit(before: dict[str, Any], after: dict[str, Any]) -> bool:
        try:
            with get_integration_control_connection() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    EXEC aud.sp_RegistrarCambio
                        @BaseDatos=?, @Esquema=?, @Objeto=?, @Operacion=?,
                        @CantidadFilas=?, @ColumnasAfectadas=?, @ClavesAfectadas=?,
                        @DatosAntes=?, @DatosDespues=?, @MuestraLimitada=?;
                    """,
                    "MOODLE",
                    "enrol",
                    "user_enrolments",
                    "INSERT",
                    len(after.get("user_ids") or []),
                    "courseid,userid,roleid",
                    json.dumps(
                        {
                            "course_id": after.get("course_id"),
                            "role_id": after.get("role_id"),
                            "user_ids": after.get("user_ids"),
                            "actor": after.get("actor"),
                            "actor_id": after.get("actor_id"),
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
            logger.exception("No se pudo registrar la auditoría de matrícula Moodle")
            return False


__all__ = [
    "MANUAL_ENROLLMENT_REQUIRED_FUNCTIONS",
    "ManualEnrollmentRole",
    "MoodleManualEnrollmentService",
]
