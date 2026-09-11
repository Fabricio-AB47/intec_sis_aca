from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.integrations.moodle.client import (
    COURSE_CATEGORIES_FUNCTION,
    COURSES_FUNCTION,
    CREATE_CATEGORIES_FUNCTION,
    DUPLICATE_COURSE_FUNCTION,
    UPDATE_COURSES_FUNCTION,
    MoodleClient,
)
from app.integrations.moodle.exceptions import (
    MoodleConfigurationError,
    MoodleCourseCloningError,
    MoodleError,
)
from app.services.db import get_integration_control_connection

logger = logging.getLogger(__name__)

CourseOfferType = Literal["REGULAR", "HOMOLOGACION"]

CLONING_REQUIRED_FUNCTIONS = (
    COURSES_FUNCTION,
    COURSE_CATEGORIES_FUNCTION,
    CREATE_CATEGORIES_FUNCTION,
    DUPLICATE_COURSE_FUNCTION,
    UPDATE_COURSES_FUNCTION,
)

_TEMPLATE_ROOT = "CURSOS_BASE_PLANTILLAS"
_OFFER_ROOT = "OFERTA_ACADEMICA"
_LOCAL_TIMEZONE = ZoneInfo("America/Guayaquil")
_OFFER_TYPES: dict[str, CourseOfferType] = {
    "REGULAR": "REGULAR",
    "HOMOLOGACION": "HOMOLOGACION",
}
_PLAN_MARKERS: dict[CourseOfferType, tuple[str, ...]] = {
    "REGULAR": ("RPLAN",),
    "HOMOLOGACION": ("HPLAN", "RPLAN"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _identity(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value).upper())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", plain).strip("_")


def _slug(value: Any) -> str:
    return _identity(value).replace("_", "-")


def _bounded_code(value: str, maximum: int) -> str:
    clean = _slug(value)
    if len(clean) <= maximum:
        return clean
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:10].upper()
    prefix = clean[: maximum - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}"


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_LOCAL_TIMEZONE)
    return value.astimezone(_LOCAL_TIMEZONE)


def _replace_plan_marker(
    value: str,
    *,
    offer_type: CourseOfferType,
    period_code: str,
    field_name: str,
    maximum: int,
) -> str:
    source = _text(value)
    markers = _PLAN_MARKERS[offer_type]
    pattern = "|".join(re.escape(marker) for marker in markers)
    matches = list(re.finditer(pattern, source, flags=re.IGNORECASE))
    if len(matches) != 1:
        expected = " o ".join(markers)
        raise MoodleCourseCloningError(
            f"El {field_name} de la plantilla debe contener una sola vez {expected}"
        )
    match = matches[0]
    result = f"{source[:match.start()]}{period_code}{source[match.end():]}"
    if len(result) > maximum:
        raise MoodleCourseCloningError(
            f"El {field_name} resultante supera {maximum} caracteres"
        )
    return result


class MoodleCourseCloningService:
    """Build and execute deterministic Moodle course cloning plans."""

    def __init__(
        self,
        settings: Settings,
        client: MoodleClient | None = None,
        auditor: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or MoodleClient(settings)
        self._auditor = auditor or self._record_audit
        self._write_lock = asyncio.Lock()

    async def catalog(self) -> dict[str, Any]:
        context = await self._load_context()
        capability = self._capability(context["functions"])
        template_root = self._find_root(context["categories"], _TEMPLATE_ROOT)
        offer_root = self._find_root(context["categories"], _OFFER_ROOT)
        templates, ignored_courses = self._templates(
            context["categories"], context["courses"], template_root
        )

        catalog_ready = template_root is not None and bool(templates)
        if template_root is None:
            catalog_reason = (
                "No se encontró la categoría principal CURSOS_BASE_PLANTILLAS en Moodle."
            )
        elif not templates:
            catalog_reason = (
                "No se encontraron cursos dentro de ramas REGULAR u HOMOLOGACION "
                "de las plantillas."
            )
        else:
            catalog_reason = "El catálogo de plantillas está disponible."

        return {
            "current_year": datetime.now(_LOCAL_TIMEZONE).year,
            "capability": capability,
            "catalog_ready": catalog_ready,
            "catalog_reason": catalog_reason,
            "template_root": self._category_summary(template_root),
            "offer_root": self._category_summary(offer_root),
            "templates": templates,
            "summary": {
                "templates": len(templates),
                "regular": sum(item["offer_type"] == "REGULAR" for item in templates),
                "homologation": sum(
                    item["offer_type"] == "HOMOLOGACION" for item in templates
                ),
                "ignored_courses": ignored_courses,
            },
        }

    async def preview(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._build_plan(request, await self._load_context())

    async def apply(
        self,
        request: dict[str, Any],
        *,
        actor: str,
        actor_id: int | None,
    ) -> dict[str, Any]:
        async with self._write_lock:
            context = await self._load_context()
            plan = self._build_plan(request, context)
            if not plan["capability"]["enabled"]:
                raise MoodleCourseCloningError(plan["capability"]["reason"])
            if not plan["ready"]:
                raise MoodleCourseCloningError(
                    "La previsualización contiene conflictos que impiden clonar los cursos"
                )

            categories = list(context["categories"])
            courses = list(context["courses"])
            created_categories: list[dict[str, Any]] = []
            results: list[dict[str, Any]] = []
            values = self._request_values(request)

            for planned_course in plan["courses"]:
                if planned_course["status"] == "EXISTENTE":
                    results.append(
                        {
                            **planned_course,
                            "status": "OMITIDO",
                            "message": "El curso ya existe y no fue duplicado.",
                            "audit_recorded": False,
                        }
                    )
                    continue

                try:
                    destination, new_categories = await self._ensure_destination(
                        categories,
                        category_route=planned_course["category_route"],
                        year=values["year"],
                        offer_type=values["offer_type"],
                        period_name=values["period_name"],
                    )
                    created_categories.extend(new_categories)
                    duplicate = await self._client.duplicate_course(
                        course_id=planned_course["template_course_id"],
                        fullname=planned_course["fullname"],
                        shortname=planned_course["shortname"],
                        category_id=destination["id"],
                        visible=False,
                    )
                    new_course_id = _integer(duplicate.get("id"))
                    warnings: list[str] = []
                    try:
                        await self._client.update_course(
                            new_course_id,
                            idnumber=planned_course["idnumber"],
                            startdate=values["startdate"],
                            enddate=values["enddate"],
                            visible=False,
                        )
                    except MoodleError as exc:
                        warnings.append(
                            "No se completaron el código o las fechas del curso: "
                            + _text(exc)[:400]
                        )

                    created_course = {
                        "id": new_course_id,
                        "fullname": planned_course["fullname"],
                        "shortname": planned_course["shortname"],
                        "idnumber": planned_course["idnumber"],
                        "categoryid": destination["id"],
                    }
                    courses.append(created_course)
                    audit_recorded = await asyncio.to_thread(
                        self._auditor,
                        {
                            "template_course_id": planned_course["template_course_id"],
                            "template_name": planned_course["subject_name"],
                            "source_path": planned_course["source_path"],
                        },
                        {
                            **created_course,
                            "destination_path": destination["path"],
                            "offer_type": values["offer_type"],
                            "period_name": values["period_name"],
                            "year": values["year"],
                            "actor": actor,
                            "actor_id": actor_id,
                            "warnings": warnings,
                        },
                    )
                    if not audit_recorded:
                        warnings.append(
                            "El curso se creó, pero no se registró la auditoría local."
                        )
                    has_warnings = bool(warnings)
                    results.append(
                        {
                            **planned_course,
                            "course_id": new_course_id,
                            "destination_category_id": destination["id"],
                            "destination_path": destination["path"],
                            "status": (
                                "CREADO_CON_ADVERTENCIA" if has_warnings else "CREADO"
                            ),
                            "message": (
                                "El curso se clonó y quedó oculto para revisión. "
                                + " ".join(warnings)
                                if has_warnings
                                else "El curso se clonó y quedó oculto para revisión."
                            ),
                            "audit_recorded": audit_recorded,
                        }
                    )
                except MoodleError as exc:
                    results.append(
                        {
                            **planned_course,
                            "status": "ERROR",
                            "message": _text(exc)[:500] or "No fue posible clonar el curso.",
                            "audit_recorded": False,
                        }
                    )

            created_count = sum(
                item["status"] in {"CREADO", "CREADO_CON_ADVERTENCIA"}
                for item in results
            )
            skipped_count = sum(item["status"] == "OMITIDO" for item in results)
            error_count = sum(item["status"] == "ERROR" for item in results)
            warning_count = sum(
                item["status"] == "CREADO_CON_ADVERTENCIA" for item in results
            )
            return {
                "ok": error_count == 0 and warning_count == 0,
                "message": (
                    f"Se clonaron {created_count} curso(s), se omitieron {skipped_count} "
                    f"y se registraron {error_count + warning_count} novedad(es)."
                ),
                "created_count": created_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "warning_count": warning_count,
                "created_categories": self._unique_categories(created_categories),
                "courses": results,
            }

    async def _load_context(self) -> dict[str, Any]:
        site_info = await self._client.get_site_info()
        functions = self._function_names(site_info.get("functions"))
        if COURSE_CATEGORIES_FUNCTION not in functions:
            raise MoodleConfigurationError(
                "El servicio web de Moodle no publica core_course_get_categories"
            )
        categories, courses = await asyncio.gather(
            self._client.get_course_categories(), self._client.get_all_courses()
        )
        return {
            "functions": functions,
            "categories": self._normalize_categories(categories),
            "courses": [dict(item) for item in courses],
        }

    def _capability(self, functions: set[str]) -> dict[str, Any]:
        missing = [name for name in CLONING_REQUIRED_FUNCTIONS if name not in functions]
        configured = bool(
            self._settings.moodle_enabled
            and self._settings.moodle_writes_enabled
            and getattr(self._settings, "moodle_course_cloning_enabled", False)
        )
        enabled = configured and not missing
        if not self._settings.moodle_enabled:
            reason = "La integración con Moodle está deshabilitada."
        elif not self._settings.moodle_writes_enabled:
            reason = "Las escrituras en Moodle están deshabilitadas."
        elif not getattr(self._settings, "moodle_course_cloning_enabled", False):
            reason = "La clonación de cursos Moodle está deshabilitada."
        elif missing:
            reason = "El servicio Moodle no publica: " + ", ".join(missing)
        else:
            reason = "La creación de categorías y clonación de cursos está habilitada."
        return {
            "enabled": enabled,
            "reason": reason,
            "required_functions": list(CLONING_REQUIRED_FUNCTIONS),
            "missing_functions": missing,
        }

    def _build_plan(
        self,
        request: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        values = self._request_values(request)
        capability = self._capability(context["functions"])
        template_root = self._find_root(context["categories"], _TEMPLATE_ROOT)
        templates, _ignored = self._templates(
            context["categories"], context["courses"], template_root
        )
        templates_by_id = {item["course_id"]: item for item in templates}
        selected: list[dict[str, Any]] = []
        for course_id in values["template_course_ids"]:
            template = templates_by_id.get(course_id)
            if template is None:
                raise MoodleCourseCloningError(
                    f"El curso plantilla Moodle {course_id} no está disponible"
                )
            if template["offer_type"] != values["offer_type"]:
                raise MoodleCourseCloningError(
                    f"{template['subject_name']} pertenece a {template['offer_type']} y no "
                    f"puede clonarse en {values['offer_type']}"
                )
            selected.append(template)

        category_plans: list[dict[str, Any]] = []
        course_plans: list[dict[str, Any]] = []
        existing_by_shortname = {
            _text(item.get("shortname")).casefold(): item
            for item in context["courses"]
            if _text(item.get("shortname"))
        }
        existing_by_idnumber = {
            _text(item.get("idnumber")).casefold(): item
            for item in context["courses"]
            if _text(item.get("idnumber"))
        }

        for template in selected:
            route_categories, destination_category = self._plan_destination(
                context["categories"],
                category_route=template["category_route"],
                year=values["year"],
                offer_type=values["offer_type"],
                period_name=values["period_name"],
            )
            category_plans.extend(route_categories)
            fullname, shortname, idnumber = self._course_identity(template, values)
            existing = existing_by_shortname.get(shortname.casefold())
            if existing is None:
                existing = existing_by_idnumber.get(idnumber.casefold())

            if existing is None:
                course_status = "POR_CLONAR"
                conflict = ""
                existing_course_id = 0
            else:
                existing_course_id = _integer(existing.get("id"))
                same_identity = (
                    _text(existing.get("shortname")).casefold() == shortname.casefold()
                    and _text(existing.get("idnumber")).casefold() == idnumber.casefold()
                )
                course_status = "EXISTENTE" if same_identity else "CONFLICTO"
                conflict = (
                    ""
                    if same_identity
                    else "El nombre corto o código ya pertenece a otro curso Moodle."
                )

            course_plans.append(
                {
                    "template_course_id": template["course_id"],
                    "subject_name": template["subject_name"],
                    "template_shortname": template["shortname"],
                    "source_path": template["source_path"],
                    "area": template["area"],
                    "career": template["career"],
                    "category_route": template["category_route"],
                    "offer_type": template["offer_type"],
                    "fullname": fullname,
                    "shortname": shortname,
                    "idnumber": idnumber,
                    "destination_path": destination_category["path"],
                    "destination_category_id": destination_category.get("id", 0),
                    "existing_course_id": existing_course_id,
                    "status": course_status,
                    "conflict": conflict,
                }
            )

        generated_identities: dict[str, list[dict[str, Any]]] = {}
        for item in course_plans:
            for key in (
                f"shortname:{item['shortname'].casefold()}",
                f"idnumber:{item['idnumber'].casefold()}",
            ):
                generated_identities.setdefault(key, []).append(item)
        for duplicates in generated_identities.values():
            if len(duplicates) < 2:
                continue
            for item in duplicates:
                item["status"] = "CONFLICTO"
                item["conflict"] = (
                    "Dos plantillas seleccionadas generan el mismo nombre corto o código."
                )

        category_plans = self._unique_category_plans(category_plans)
        category_conflicts = sum(item["status"] == "CONFLICTO" for item in category_plans)
        course_conflicts = sum(item["status"] == "CONFLICTO" for item in course_plans)
        return {
            "ready": bool(selected) and category_conflicts == 0 and course_conflicts == 0,
            "capability": capability,
            "year": values["year"],
            "offer_type": values["offer_type"],
            "period_name": values["period_name"],
            "opening_at": values["opening_at"].isoformat(),
            "closing_at": (
                values["closing_at"].isoformat() if values["closing_at"] else None
            ),
            "categories": category_plans,
            "courses": course_plans,
            "summary": {
                "selected": len(selected),
                "to_clone": sum(item["status"] == "POR_CLONAR" for item in course_plans),
                "existing": sum(item["status"] == "EXISTENTE" for item in course_plans),
                "course_conflicts": course_conflicts,
                "categories_to_create": sum(
                    item["status"] == "POR_CREAR" for item in category_plans
                ),
                "categories_existing": sum(
                    item["status"] == "EXISTENTE" for item in category_plans
                ),
                "category_conflicts": category_conflicts,
            },
        }

    def _request_values(self, request: dict[str, Any]) -> dict[str, Any]:
        template_course_ids = list(
            dict.fromkeys(_integer(value) for value in request.get("template_course_ids", []))
        )
        if not template_course_ids or any(value <= 0 for value in template_course_ids):
            raise MoodleCourseCloningError("Seleccione al menos un curso plantilla válido")
        if len(template_course_ids) > 50:
            raise MoodleCourseCloningError("Puede clonar un máximo de 50 cursos por proceso")

        offer_type = _identity(request.get("offer_type"))
        if offer_type not in _OFFER_TYPES:
            raise MoodleCourseCloningError("Seleccione Regular u Homologación")
        opening_at = request.get("opening_at")
        closing_at = request.get("closing_at")
        if not isinstance(opening_at, datetime):
            raise MoodleCourseCloningError("La fecha inicial no es válida")
        opening_at = _local_datetime(opening_at)
        closing_at = _local_datetime(closing_at) if isinstance(closing_at, datetime) else None
        if closing_at and closing_at <= opening_at:
            raise MoodleCourseCloningError(
                "La fecha final debe ser posterior a la fecha inicial"
            )

        year = opening_at.year
        raw_period = " ".join(_text(request.get("period_name")).upper().split())
        expected_prefix = "R" if offer_type == "REGULAR" else "H"
        period_identity = _identity(raw_period).replace("_", " ")
        if not re.fullmatch(rf"{expected_prefix}\d+[ A-Z0-9.-]*", period_identity):
            raise MoodleCourseCloningError(
                f"El período de {offer_type.title()} debe iniciar con "
                f"{expected_prefix} y un número"
            )
        explicit_years = [
            int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", raw_period)
        ]
        if explicit_years and any(value != year for value in explicit_years):
            raise MoodleCourseCloningError(
                "El año escrito en el período no coincide con la fecha inicial"
            )
        period_name = (
            f"{raw_period} {year}"
            if offer_type == "HOMOLOGACION" and not explicit_years
            else raw_period
        )
        return {
            "template_course_ids": template_course_ids,
            "offer_type": _OFFER_TYPES[offer_type],
            "opening_at": opening_at,
            "closing_at": closing_at,
            "startdate": int(opening_at.timestamp()),
            "enddate": int(closing_at.timestamp()) if closing_at else None,
            "year": year,
            "period_name": period_name,
            "parallel": _slug(request.get("parallel"))[:20],
        }

    def _templates(
        self,
        categories: list[dict[str, Any]],
        courses: list[dict[str, Any]],
        root: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], int]:
        if root is None:
            return [], len(courses)
        by_id = {item["id"]: item for item in categories}
        templates: list[dict[str, Any]] = []
        ignored = 0
        for course in courses:
            path = self._category_path(_integer(course.get("categoryid")), by_id)
            path_ids = [item["id"] for item in path]
            if root["id"] not in path_ids:
                continue
            relative = path[path_ids.index(root["id"]) + 1 :]
            type_indexes = [
                index
                for index, item in enumerate(relative)
                if _identity(item["name"]) in _OFFER_TYPES
            ]
            if len(type_indexes) != 1 or type_indexes[0] < 1:
                ignored += 1
                continue
            type_index = type_indexes[0]
            category_route = [
                item["name"]
                for index, item in enumerate(relative)
                if index != type_index
            ]
            if not category_route:
                ignored += 1
                continue
            area = category_route[0]
            career = category_route[-1] if len(category_route) > 1 else ""
            offer_type = _OFFER_TYPES[_identity(relative[type_index]["name"])]
            subject_name = self._subject_name(course)
            templates.append(
                {
                    "course_id": _integer(course.get("id")),
                    "subject_name": subject_name,
                    "fullname": _text(course.get("fullname")) or subject_name,
                    "shortname": _text(course.get("shortname")),
                    "idnumber": _text(course.get("idnumber")),
                    "category_id": _integer(course.get("categoryid")),
                    "source_path": "/".join(item["name"] for item in path),
                    "area": area,
                    "career": career,
                    "category_route": category_route,
                    "offer_type": offer_type,
                    "visible": bool(_integer(course.get("visible"))),
                }
            )
        templates.sort(
            key=lambda item: (
                _identity(item["offer_type"]),
                _identity(item["area"]),
                _identity(item["career"]),
                _identity(item["subject_name"]),
                item["course_id"],
            )
        )
        return templates, ignored

    @staticmethod
    def _subject_name(course: dict[str, Any]) -> str:
        name = _text(course.get("fullname")) or _text(course.get("displayname"))
        clean = re.sub(
            r"^\s*(?:PLANTILLA|CURSO\s+BASE)(?:\s+(?:REGULAR|HOMOLOGACI[OÓ]N))?"
            r"\s*[-:|]\s*",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        clean = re.sub(
            r"\s+(?:PLANTILLA|RPLAN|HPLAN)\s*$",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        return clean or name or f"Curso plantilla {_integer(course.get('id'))}"

    def _course_identity(
        self,
        template: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[str, str, str]:
        fullname = f"{values['period_name']} - {template['subject_name']}"
        if values["parallel"]:
            fullname += f" - {values['parallel']}"
        fullname = fullname[:254].strip()
        period_code = _identity(values["period_name"]).replace("_", "")
        shortname = _replace_plan_marker(
            template["shortname"],
            offer_type=values["offer_type"],
            period_code=period_code,
            field_name="nombre corto",
            maximum=255,
        )
        idnumber = _replace_plan_marker(
            template["idnumber"],
            offer_type=values["offer_type"],
            period_code=period_code,
            field_name="número ID del curso",
            maximum=100,
        )
        return fullname, shortname, idnumber

    def _plan_destination(
        self,
        categories: list[dict[str, Any]],
        *,
        category_route: list[str],
        year: int,
        offer_type: CourseOfferType,
        period_name: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        parent_id: int | None = 0
        parent_path = ""
        code = "OFA"
        root, root_plan = self._planned_category(
            categories,
            name=_OFFER_ROOT,
            code=code,
            parent_id=parent_id,
            parent_path=parent_path,
        )
        plans.append(root_plan)
        parent_id = root.get("id") or None
        parent_path = root_plan["path"]

        for name in category_route:
            segment = _slug(name)
            code = _bounded_code(f"{code}-{segment}", 100)
            category, category_plan = self._planned_category(
                categories,
                name=name,
                code=code,
                parent_id=parent_id,
                parent_path=parent_path,
            )
            plans.append(category_plan)
            parent_id = category.get("id") or None
            parent_path = category_plan["path"]

        year_code = _bounded_code(f"{code}-Y{year}", 100)
        year_category, year_plan = self._planned_category(
            categories,
            name=str(year),
            code=year_code,
            parent_id=parent_id,
            parent_path=parent_path,
        )
        plans.append(year_plan)
        year_parent_id = year_category.get("id") or None
        year_path = year_plan["path"]

        type_categories: dict[str, dict[str, Any]] = {}
        for type_name, type_suffix in (("REGULAR", "REG"), ("HOMOLOGACION", "HOM")):
            category, category_plan = self._planned_category(
                categories,
                name=type_name,
                code=_bounded_code(f"{year_code}-{type_suffix}", 100),
                parent_id=year_parent_id,
                parent_path=year_path,
            )
            plans.append(category_plan)
            type_categories[type_name] = category

        selected_suffix = "REG" if offer_type == "REGULAR" else "HOM"
        selected_type = type_categories[offer_type]
        selected_type_path = f"{year_path}/{offer_type}"
        period, period_plan = self._planned_category(
            categories,
            name=period_name,
            code=_bounded_code(
                f"{year_code}-{selected_suffix}-{_slug(period_name)}",
                100,
            ),
            parent_id=selected_type.get("id") or None,
            parent_path=selected_type_path,
        )
        plans.append(period_plan)
        return plans, {"id": period.get("id", 0), "path": period_plan["path"]}

    def _planned_category(
        self,
        categories: list[dict[str, Any]],
        *,
        name: str,
        code: str,
        parent_id: int | None,
        parent_path: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        path = f"{parent_path}/{name}" if parent_path else name
        code_matches = [
            item
            for item in categories
            if item["idnumber"] and _identity(item["idnumber"]) == _identity(code)
        ]
        if len(code_matches) > 1:
            return {}, self._category_plan(
                name,
                code,
                path,
                "CONFLICTO",
                "El código identifica más de una categoría Moodle.",
            )
        if code_matches:
            category = code_matches[0]
            if parent_id is not None and category["parent"] != parent_id:
                return category, self._category_plan(
                    name,
                    code,
                    path,
                    "CONFLICTO",
                    "El código existe bajo una categoría padre diferente.",
                    category["id"],
                )
            if _identity(category["name"]) != _identity(name):
                return category, self._category_plan(
                    name,
                    code,
                    path,
                    "CONFLICTO",
                    "El código ya pertenece a una categoría con otro nombre.",
                    category["id"],
                )
            return category, self._category_plan(
                category["name"],
                category["idnumber"] or code,
                path,
                "EXISTENTE",
                category_id=category["id"],
            )

        if parent_id is not None:
            name_matches = [
                item
                for item in categories
                if item["parent"] == parent_id
                and _identity(item["name"]) == _identity(name)
            ]
            if len(name_matches) > 1:
                return {}, self._category_plan(
                    name,
                    code,
                    path,
                    "CONFLICTO",
                    "Existe más de una categoría con el mismo nombre en esta ruta.",
                )
            if name_matches:
                category = name_matches[0]
                return category, self._category_plan(
                    category["name"],
                    category["idnumber"] or code,
                    path,
                    "EXISTENTE",
                    category_id=category["id"],
                )
        return {}, self._category_plan(name, code, path, "POR_CREAR")

    @staticmethod
    def _category_plan(
        name: str,
        code: str,
        path: str,
        status: str,
        conflict: str = "",
        category_id: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": category_id,
            "name": name,
            "idnumber": code,
            "path": path,
            "status": status,
            "conflict": conflict,
        }

    async def _ensure_destination(
        self,
        categories: list[dict[str, Any]],
        *,
        category_route: list[str],
        year: int,
        offer_type: CourseOfferType,
        period_name: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        created: list[dict[str, Any]] = []
        parent = await self._ensure_category(
            categories,
            created,
            name=_OFFER_ROOT,
            code="OFA",
            parent_id=0,
            parent_path="",
        )
        code = "OFA"
        for name in category_route:
            code = _bounded_code(f"{code}-{_slug(name)}", 100)
            parent = await self._ensure_category(
                categories,
                created,
                name=name,
                code=code,
                parent_id=parent["id"],
                parent_path=parent["path"],
            )

        year_code = _bounded_code(f"{code}-Y{year}", 100)
        year_category = await self._ensure_category(
            categories,
            created,
            name=str(year),
            code=year_code,
            parent_id=parent["id"],
            parent_path=parent["path"],
        )
        type_categories: dict[str, dict[str, Any]] = {}
        for type_name, suffix in (("REGULAR", "REG"), ("HOMOLOGACION", "HOM")):
            type_categories[type_name] = await self._ensure_category(
                categories,
                created,
                name=type_name,
                code=_bounded_code(f"{year_code}-{suffix}", 100),
                parent_id=year_category["id"],
                parent_path=year_category["path"],
            )
        suffix = "REG" if offer_type == "REGULAR" else "HOM"
        destination = await self._ensure_category(
            categories,
            created,
            name=period_name,
            code=_bounded_code(
                f"{year_code}-{suffix}-{_slug(period_name)}",
                100,
            ),
            parent_id=type_categories[offer_type]["id"],
            parent_path=type_categories[offer_type]["path"],
        )
        return destination, created

    async def _ensure_category(
        self,
        categories: list[dict[str, Any]],
        created: list[dict[str, Any]],
        *,
        name: str,
        code: str,
        parent_id: int,
        parent_path: str,
    ) -> dict[str, Any]:
        candidate, plan = self._planned_category(
            categories,
            name=name,
            code=code,
            parent_id=parent_id,
            parent_path=parent_path,
        )
        if plan["status"] == "CONFLICTO":
            raise MoodleCourseCloningError(f"{plan['path']}: {plan['conflict']}")
        if plan["status"] == "EXISTENTE":
            return {**candidate, "path": plan["path"]}

        payload = await self._client.create_course_category(
            name=name, parent=parent_id, idnumber=code
        )
        category = {
            "id": _integer(payload.get("id")),
            "name": _text(payload.get("name")) or name,
            "idnumber": code,
            "parent": parent_id,
            "visible": True,
            "path": plan["path"],
        }
        if category["id"] <= 0:
            raise MoodleCourseCloningError(
                f"Moodle no devolvió el identificador de la categoría {plan['path']}"
            )
        categories.append(category)
        created.append(category)
        return category

    @staticmethod
    def _normalize_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": _integer(item.get("id")),
                "name": _text(item.get("name")),
                "idnumber": _text(item.get("idnumber")),
                "parent": _integer(item.get("parent")),
                "visible": bool(_integer(item.get("visible", 1))),
            }
            for item in categories
            if _integer(item.get("id")) > 0 and _text(item.get("name"))
        ]

    @staticmethod
    def _category_path(
        category_id: int,
        by_id: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        path: list[dict[str, Any]] = []
        visited: set[int] = set()
        current_id = category_id
        while current_id > 0 and current_id not in visited:
            visited.add(current_id)
            category = by_id.get(current_id)
            if category is None:
                break
            path.append(category)
            current_id = category["parent"]
        path.reverse()
        return path

    @staticmethod
    def _find_root(
        categories: list[dict[str, Any]],
        expected_name: str,
    ) -> dict[str, Any] | None:
        expected = _identity(expected_name)
        matches = [
            item
            for item in categories
            if _identity(item["name"]) == expected
            or _identity(item["idnumber"]) == expected
        ]
        if not matches:
            return None
        top_level = [item for item in matches if item["parent"] == 0]
        return sorted(top_level or matches, key=lambda item: item["id"])[0]

    @staticmethod
    def _category_summary(category: dict[str, Any] | None) -> dict[str, Any] | None:
        if category is None:
            return None
        return {
            "id": category["id"],
            "name": category["name"],
            "idnumber": category["idnumber"],
        }

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
    def _unique_category_plans(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for item in items:
            key = _identity(item["idnumber"])
            current = unique.get(key)
            if current is None or current["status"] != "CONFLICTO":
                unique[key] = item
        return list(unique.values())

    @staticmethod
    def _unique_categories(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[int, dict[str, Any]] = {}
        for item in items:
            unique[_integer(item.get("id"))] = item
        return [item for key, item in unique.items() if key > 0]

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
                    "core",
                    "course",
                    "INSERT",
                    1,
                    "fullname,shortname,idnumber,category,startdate,visible",
                    json.dumps(
                        {
                            "template_course_id": before.get("template_course_id"),
                            "course_id": after.get("id"),
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
            logger.exception("No se pudo registrar la auditoría de clonación Moodle")
            return False


__all__ = ["CLONING_REQUIRED_FUNCTIONS", "MoodleCourseCloningService"]
