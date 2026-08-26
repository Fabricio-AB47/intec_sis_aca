from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from typing import Any, Iterable, Sequence

from app.core.config import Settings, get_settings
from app.services.db import get_connection
from app.services.email_identity import normalize_email_identity
from app.services.grade_calculation import (
    calculate_homologation_grade_with_recovery,
    calculate_regular_grade_with_recovery,
)
from app.services.moodle_read_service import MoodleReadService


GRADE_FIELDS = {
    "P1Tareas",
    "P1Proyectos",
    "P1Examen",
    "P2Tareas",
    "P2Proyectos",
    "P2Examen",
    "P3Tareas",
    "P3Proyectos",
    "P3Examen",
    "teoriaHomo",
    "practicahomo",
}
_APPLICABLE_STATUSES = {"ready", "ready_override"}
_ACTIVE_STATES = {"A", "ACTIVO", "ACTIVA"}
_PRACTICAL_WORDS = ("PRACTICO", "PRACTICA")
_THEORY_WORDS = ("TEORICO", "TEORICA", "TEORIA")
_EVALUATION_MODULES = {"quiz", "assign"}
_PARTIAL_LABELS = {
    1: "Primer parcial",
    2: "Segundo parcial",
    3: "Tercer parcial",
}
_PARTIAL_PATTERNS = {
    1: (
        r"\bP\s*1\b",
        r"\bPRIMER(?:O)?\s+PARCIAL\b",
        r"\bPARCIAL\s*(?:(?:NO|NRO|NUMERO)\.?\s*)?1\b",
    ),
    2: (
        r"\bP\s*2\b",
        r"\bSEGUNDO\s+PARCIAL\b",
        r"\bPARCIAL\s*(?:(?:NO|NRO|NUMERO)\.?\s*)?2\b",
    ),
    3: (
        r"\bP\s*3\b",
        r"\bTERCER(?:O)?\s+PARCIAL\b",
        r"\bPARCIAL\s*(?:(?:NO|NRO|NUMERO)\.?\s*)?3\b",
    ),
}


class MoodleGradeSyncError(RuntimeError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_institutional_email(value: Any) -> str:
    """Normalize an institutional email without introducing fuzzy identity matches."""
    return normalize_email_identity(value)


def institutional_email_candidates(enrollment: dict[str, Any]) -> list[tuple[str, str]]:
    """Return only the canonical Moodle identity stored in CorreosEstudIntec."""
    email = normalize_institutional_email(enrollment.get("registry_email"))
    return [("CorreosEstudIntec", email)] if email else []


def match_course_users_by_institutional_email(
    enrollment: dict[str, Any],
    users_by_email: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str, str]:
    """Match one academic enrollment only against users enrolled in the selected Moodle course."""
    matched: dict[tuple[str, Any], dict[str, Any]] = {}
    match_metadata: dict[tuple[str, Any], tuple[str, str]] = {}
    for source, email in institutional_email_candidates(enrollment):
        for user in users_by_email.get(email, []):
            user_id = int(user.get("id") or 0)
            key = ("id", user_id) if user_id > 0 else (
                "identity",
                normalize_institutional_email(user.get("email"))
                or normalize_institutional_email(user.get("username"))
                or _text(user.get("fullname")),
            )
            matched[key] = user
            match_metadata.setdefault(key, (email, source))

    ordered_keys = list(matched)
    if len(ordered_keys) != 1:
        return [matched[key] for key in ordered_keys], "", ""
    matched_email, source = match_metadata[ordered_keys[0]]
    return [matched[ordered_keys[0]]], matched_email, source


def _normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", _text(value).upper())
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    return " ".join(text.replace("_", " ").replace("-", " ").split())


def _matter_match_score(course: dict[str, Any], matter: Any) -> int:
    """Score an academic subject name inside the selected Moodle course metadata."""
    normalized_matter = _normalized_text(matter)
    matter_tokens = {
        token
        for token in normalized_matter.split()
        if len(token) >= 3 and token not in {"DEL", "LOS", "LAS", "UNA", "UNO"}
    }
    if not normalized_matter or not matter_tokens:
        return 0

    best_score = 0
    for field in ("displayname", "fullname", "shortname", "idnumber"):
        normalized_course = _normalized_text(course.get(field))
        if not normalized_course:
            continue
        if normalized_matter in normalized_course:
            best_score = max(best_score, 1000 + len(normalized_matter))
            continue
        course_tokens = set(normalized_course.split())
        overlap = len(matter_tokens & course_tokens)
        if overlap == len(matter_tokens):
            best_score = max(best_score, 500 + overlap)
        elif len(matter_tokens) >= 3 and overlap / len(matter_tokens) >= 0.8:
            best_score = max(best_score, 100 + overlap)
    return best_score


def canonical_course_code(value: Any) -> str:
    """Normalize only formatting noise; internal code segments remain exact."""
    return re.sub(r"[-_/.\s]+$", "", _text(value).upper())


def _course_code_segments(value: Any) -> tuple[str, ...]:
    """Split a course code into exact segments without confusing 1 with 10 or 12."""
    return tuple(segment for segment in re.split(r"[^A-Z0-9]+", _text(value).upper()) if segment)


def _course_code_match_score(course: dict[str, Any], academic_code: Any) -> int:
    """Match a PENSUM code inside Moodle metadata while allowing only extra suffixes."""
    expected = canonical_course_code(academic_code)
    expected_segments = _course_code_segments(expected)
    if not expected or len(expected_segments) < 2:
        return 0

    best_score = 0
    for field in ("idnumber", "shortname", "displayname", "fullname"):
        candidate = canonical_course_code(course.get(field))
        if not candidate:
            continue
        if candidate == expected:
            best_score = max(best_score, 10_000 + len(expected))
            continue

        candidate_segments = _course_code_segments(candidate)
        expected_size = len(expected_segments)
        for offset in range(0, len(candidate_segments) - expected_size + 1):
            if candidate_segments[offset : offset + expected_size] != expected_segments:
                continue
            suffix_size = len(candidate_segments) - offset - expected_size
            # Moodle suele agregar paralelo, cohorte, beca u otro sufijo al
            # código exacto de PENSUM. Los segmentos académicos no se alteran.
            position_score = 9_000 if offset == 0 else 8_000
            best_score = max(
                best_score,
                position_score + expected_size * 10 - min(suffix_size, 100),
            )
    return best_score


def _partial_number(normalized_item_name: str) -> int | None:
    for partial, patterns in _PARTIAL_PATTERNS.items():
        if any(re.search(pattern, normalized_item_name) for pattern in patterns):
            return partial
    return None


def moodle_exam_targets(
    item_name: Any,
    enrollment_type: str,
    item_module: Any = None,
) -> tuple[str, ...]:
    normalized = _normalized_text(item_name)
    module = _text(item_module).casefold()
    if module == "quiz":
        is_practical = False
        is_theoretical = True
    elif module == "assign":
        is_practical = True
        is_theoretical = False
    else:
        # Compatibilidad con datos históricos sin itemmodule. La migración
        # normal solo admite quiz y assign dentro de la sección Evaluación.
        if "EXAMEN" not in normalized:
            return ()
        is_practical = any(word in normalized for word in _PRACTICAL_WORDS)
        is_theoretical = any(word in normalized for word in _THEORY_WORDS)
        if is_practical == is_theoretical:
            return ()

    if enrollment_type.upper() == "H":
        return ("practicahomo",) if is_practical else ("teoriaHomo",)

    if enrollment_type.upper() != "R":
        return ()

    partial = _partial_number(normalized)
    if partial is None:
        # En regular cada examen pertenece a un parcial específico.
        return ()

    if is_practical:
        return (f"P{partial}Tareas", f"P{partial}Proyectos")
    return (f"P{partial}Examen",)


def _evaluation_module_targets(
    item_module: str,
    enrollment_type: str,
    partial: int | None,
) -> tuple[str, ...]:
    """Map Moodle activity types without depending on their display names."""
    module = _text(item_module).casefold()
    enrollment = _text(enrollment_type).upper()
    if module not in _EVALUATION_MODULES:
        return ()
    if enrollment == "H":
        return ("teoriaHomo",) if module == "quiz" else ("practicahomo",)
    if enrollment != "R" or partial not in {1, 2, 3}:
        return ()
    if module == "quiz":
        return (f"P{partial}Examen",)
    return (f"P{partial}Tareas", f"P{partial}Proyectos")


def practical_exam_targets(item_name: Any, enrollment_type: str) -> tuple[str, ...]:
    """Compatibilidad para consumidores que consultan solo exámenes prácticos."""
    normalized = _normalized_text(item_name)
    if not any(word in normalized for word in _PRACTICAL_WORDS):
        return ()
    return moodle_exam_targets(item_name, enrollment_type)


def _moodle_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    normalized = _text(value).casefold()
    if normalized in {"", "0", "false", "no", "none", "null"}:
        return False
    if normalized in {"1", "true", "yes", "si", "sí"}:
        return True
    try:
        return Decimal(normalized.replace(",", ".")) != 0
    except InvalidOperation:
        return bool(normalized)


def _enabled_grade_item(item: dict[str, Any]) -> bool:
    hidden_fields = ("hidden", "gradeishidden", "gradehiddenbydate", "disabled")
    if any(_moodle_flag(item.get(field)) for field in hidden_fields):
        return False
    for field in ("visible", "uservisible"):
        if field in item and not _moodle_flag(item.get(field)):
            return False
    return True


def _moodle_decimal(value: Any, *, field: str) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    if isinstance(value, bool):
        raise MoodleGradeSyncError(f"Moodle devolvió {field} con un formato no numérico")

    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if text.endswith("%"):
        text = text[:-1]
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        raise MoodleGradeSyncError(f"Moodle devolvió {field} con un formato no numérico")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise MoodleGradeSyncError(f"Moodle devolvió {field} con un formato no numérico") from exc
    if not number.is_finite():
        raise MoodleGradeSyncError(f"Moodle devolvió {field} con un valor no finito")
    return number


class _VisibleGradeTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _visible_moodle_grade_details(value: Any) -> tuple[Decimal | None, bool]:
    """Obtiene la nota visible y distingue si Moodle la presenta como porcentaje."""
    if value in (None, "", "-"):
        return None, False
    if isinstance(value, bool):
        return None, False

    parser = _VisibleGradeTextParser()
    try:
        parser.feed(str(value))
        parser.close()
    except (AssertionError, ValueError):
        return None, False

    visible_text = " ".join(parser.parts).replace("\u00a0", " ").strip()
    match = re.search(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)", visible_text)
    if match is None:
        return None, False
    visible_suffix = visible_text[match.end() :].lstrip()
    return (
        _moodle_decimal(match.group(0), field="la calificación visible"),
        visible_suffix.startswith("%"),
    )


def _decimal_close(
    left: Decimal,
    right: Decimal,
    *,
    tolerance: Decimal = Decimal("0.02"),
) -> bool:
    return abs(left - right) <= tolerance


def _range_scale(value: Any) -> tuple[Decimal, Decimal] | None:
    values = re.findall(r"\d+(?:[.,]\d+)?", _text(value))
    if len(values) < 2:
        return None
    minimum = _moodle_decimal(values[0], field="el mínimo de la escala")
    maximum = _moodle_decimal(values[-1], field="el máximo de la escala")
    if minimum is None or maximum is None or maximum <= minimum:
        return None
    return minimum, maximum


def _ten_point_grade(value: Any) -> float:
    grade = _moodle_decimal(value, field="una calificación normalizada")
    if grade is None or grade < 0 or grade > 10:
        raise MoodleGradeSyncError("La calificación normalizada debe estar entre 0 y 10")
    return float(grade.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _normalize_moodle_grade_details(item: dict[str, Any]) -> dict[str, Any] | None:
    raw_source = "graderaw"
    raw = _moodle_decimal(item.get("graderaw"), field="una calificación")
    visible_grade, visible_grade_is_percentage = _visible_moodle_grade_details(
        item.get("gradeformatted")
    )
    percentage = _moodle_decimal(
        item.get("percentageformatted"),
        field="un porcentaje de calificación",
    )
    if percentage is not None and (percentage < 0 or percentage > 100):
        raise MoodleGradeSyncError("El porcentaje Moodle debe estar entre 0 y 100")

    if raw is None:
        raw_source = "gradeformatted"
        raw = visible_grade
    if raw is None:
        if percentage is None:
            return None
        return {
            "grade": _ten_point_grade(percentage / Decimal("10")),
            "raw_grade": float(percentage),
            "grade_min": 0.0,
            "grade_max": 100.0,
            "raw_source": "percentageformatted",
            "scale_source": "percentage",
        }

    minimum = _moodle_decimal(item.get("grademin"), field="el mínimo de la escala")
    maximum = _moodle_decimal(item.get("grademax"), field="el máximo de la escala")
    scale_source = "declared"
    if minimum is None:
        minimum = Decimal("0")
    if maximum is None:
        range_scale = _range_scale(item.get("rangeformatted"))
        if range_scale is not None:
            minimum, maximum = range_scale
            scale_source = "rangeformatted"
        elif percentage is not None:
            return {
                "grade": _ten_point_grade(percentage / Decimal("10")),
                "raw_grade": float(raw),
                "grade_min": None,
                "grade_max": None,
                "raw_source": raw_source,
                "scale_source": "percentage",
            }
        elif Decimal("0") <= raw <= Decimal("10"):
            minimum, maximum = Decimal("0"), Decimal("10")
            scale_source = "inferred_10"
        elif Decimal("10") < raw <= Decimal("100"):
            minimum, maximum = Decimal("0"), Decimal("100")
            scale_source = "inferred_100"
        else:
            raise MoodleGradeSyncError(
                "No se pudo determinar si la calificación Moodle está sobre 10 o sobre 100"
            )

    if maximum <= minimum:
        raise MoodleGradeSyncError("La escala de la calificación Moodle no es válida")
    if raw < minimum or raw > maximum:
        raise MoodleGradeSyncError("La calificación Moodle está fuera de su escala declarada")

    normalized_from_scale = ((raw - minimum) / (maximum - minimum)) * Decimal("10")
    percentage_grade = percentage / Decimal("10") if percentage is not None else None
    visible_percentage_consistent = (
        percentage is None
        or (
            visible_grade is not None
            and (
                _decimal_close(percentage, visible_grade, tolerance=Decimal("0.05"))
                or _decimal_close(
                    percentage * Decimal("10"),
                    visible_grade,
                    tolerance=Decimal("0.05"),
                )
                or _decimal_close(
                    percentage_grade,
                    visible_grade,
                    tolerance=Decimal("0.05"),
                )
            )
        )
    )

    # Algunos libros de calificaciones institucionales devuelven el valor decimal desplazado
    # junto con el porcentaje que conserva la nota real: 0,70 y 7,00 %, por ejemplo. Esta
    # recuperación se limita a una escala declarada 0-10 y exige que ambas señales coincidan;
    # una nota menor que uno sin esa evidencia se conserva sin multiplicarla.
    institutional_decimal_shift = (
        Decimal("0") < normalized_from_scale < Decimal("1")
        and percentage is not None
        and Decimal("0") < percentage <= Decimal("10")
        and _decimal_close(
            maximum - minimum,
            Decimal("10"),
            tolerance=Decimal("0.01"),
        )
        and _decimal_close(
            percentage,
            normalized_from_scale * Decimal("10"),
            tolerance=Decimal("0.05"),
        )
    )

    # La calificación visible es la misma que consulta el docente en Moodle. Cuando es una
    # nota numérica sobre 10 (no un porcentaje), prevalece sobre una escala técnica mal
    # configurada para impedir que 7,00 o 9,00 se conviertan en 0,70 o 0,90.
    visible_ten_point_scale = (
        visible_grade is not None
        and not visible_grade_is_percentage
        and Decimal("0") <= visible_grade <= Decimal("10")
        and visible_percentage_consistent
    )
    if institutional_decimal_shift:
        normalized = percentage
        scale_source = "institutional_decimal_shift_10"
    elif visible_ten_point_scale:
        normalized = visible_grade
        scale_source = "gradeformatted_direct_10"
    else:
        normalized = normalized_from_scale
        if percentage_grade is not None and not _decimal_close(
            normalized,
            percentage_grade,
            tolerance=Decimal("0.05"),
        ):
            raise MoodleGradeSyncError(
                "La nota, el porcentaje y la escala devueltos por Moodle son contradictorios"
            )

    return {
        "grade": _ten_point_grade(normalized),
        "raw_grade": float(raw),
        "grade_min": float(minimum),
        "grade_max": float(maximum),
        "raw_source": raw_source,
        "scale_source": scale_source,
    }


def normalize_moodle_grade(item: dict[str, Any]) -> float | None:
    details = _normalize_moodle_grade_details(item)
    return None if details is None else float(details["grade"])


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _same_grade(left: Any, right: Any) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    if left_number is None or right_number is None:
        return left_number is right_number
    return abs(left_number - right_number) < 0.005


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    return {column[0]: value for column, value in zip(cursor.description, row)}


def parse_configured_mappings(raw_value: str) -> list[tuple[int, int]]:
    mappings: list[tuple[int, int]] = []
    for item in raw_value.split(","):
        clean_item = item.strip()
        if not clean_item:
            continue
        course_text, separator, period_text = clean_item.partition(":")
        if not separator or not course_text.strip().isdigit() or not period_text.strip().isdigit():
            raise MoodleGradeSyncError(
                "MOODLE_GRADE_SYNC_MAPPINGS debe usar el formato course_id:codigo_periodo"
            )
        pair = (int(course_text), int(period_text))
        if pair not in mappings:
            mappings.append(pair)
    return mappings


def normalize_period_codes(
    period_code: int | None = None,
    period_codes: Sequence[int] | None = None,
) -> list[int]:
    """Return one to three distinct positive academic period codes."""
    values = list(period_codes or ())
    if period_code is not None:
        values.insert(0, period_code)

    normalized: list[int] = []
    for value in values:
        try:
            code = int(value)
        except (TypeError, ValueError) as exc:
            raise MoodleGradeSyncError("Los períodos académicos deben tener códigos numéricos") from exc
        if code <= 0:
            raise MoodleGradeSyncError("Los códigos de período deben ser mayores que cero")
        if code not in normalized:
            normalized.append(code)

    if not normalized:
        raise MoodleGradeSyncError("Seleccione al menos un período académico")
    if len(normalized) > 3:
        raise MoodleGradeSyncError("Puede seleccionar un máximo de tres períodos académicos")
    return normalized


class MoodleGradeSyncService:
    def __init__(
        self,
        moodle: MoodleReadService,
        settings: Settings | None = None,
    ) -> None:
        self._moodle = moodle
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.moodle_enabled
            and self._settings.moodle_reads_enabled
            and self._settings.moodle_grade_sync_enabled
        )

    def configured_mappings(self) -> list[tuple[int, int]]:
        return parse_configured_mappings(
            getattr(self._settings, "moodle_grade_sync_mappings", "")
        )

    async def catalog(self, *, refresh: bool = False) -> dict[str, Any]:
        self._require_enabled()
        courses = await self._moodle.get_all_courses(refresh=refresh)
        academic_options = self._academic_period_options()
        configured_periods = dict(self.configured_mappings())
        options_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for option in academic_options:
            options_by_code[canonical_course_code(option["course_code"])].append(option)

        catalog_by_id: dict[int, dict[str, Any]] = {}
        for course in courses:
            course_id = int(course.get("id") or 0)
            if course_id <= 0:
                continue
            candidates = self._course_codes(course)
            matched_options: list[dict[str, Any]] = []
            matched_code = ""
            for candidate in sorted(candidates):
                options = options_by_code.get(candidate, [])
                if options:
                    if not matched_code:
                        matched_code = candidate
                    matched_options.extend(options)
            unique_options = {
                (
                    int(option["period_code"]),
                    option["course_code"],
                    option["period_type"],
                ): option
                for option in matched_options
            }
            periods = sorted(
                unique_options.values(),
                key=lambda item: (-int(item["period_code"]), item["career"]),
            )
            configured_period = configured_periods.get(course_id)
            recommended_period = (
                configured_period
                if configured_period is not None
                and any(int(item["period_code"]) == configured_period for item in periods)
                else None
            )
            catalog_by_id[course_id] = {
                "id": course_id,
                "name": (
                    course.get("displayname")
                    or course.get("fullname")
                    or course.get("shortname")
                    or f"Curso Moodle {course_id}"
                ),
                "shortname": course.get("shortname") or "",
                "idnumber": course.get("idnumber") or "",
                "matched_course_code": matched_code,
                "has_academic_match": bool(periods),
                "recommended_period_code": recommended_period,
                "periods": periods,
            }

        catalog_courses = sorted(
            catalog_by_id.values(),
            key=lambda item: _normalized_text(item["name"]),
        )
        matched_count = sum(1 for item in catalog_courses if item["has_academic_match"])

        return {
            "enabled": True,
            "apply_enabled": bool(self._settings.moodle_grade_sync_apply_enabled),
            "nightly_enabled": bool(self._settings.moodle_grade_sync_nightly_enabled),
            "change_detection_enabled": bool(
                getattr(self._settings, "moodle_grade_sync_changes_enabled", False)
            ),
            "change_detection_interval_minutes": int(
                getattr(self._settings, "moodle_grade_sync_interval_minutes", 5)
            ),
            "configured_mappings": [
                {"course_id": course_id, "period_code": period_code}
                for course_id, period_code in self.configured_mappings()
            ],
            "totals": {
                "courses": len(catalog_courses),
                "matched": matched_count,
                "unmatched": len(catalog_courses) - matched_count,
            },
            "courses": catalog_courses,
        }

    async def course_context(self, *, course_id: int, refresh: bool = False) -> dict[str, Any]:
        """Resolve one Moodle course against active academic rows by institutional email."""
        self._require_enabled()
        courses = await self._moodle.get_all_courses(refresh=refresh)
        course = next((item for item in courses if int(item.get("id") or 0) == course_id), None)
        if course is None:
            raise MoodleGradeSyncError("No se encontró el curso seleccionado en Moodle")

        moodle_users = await self._moodle.get_course_enrolled_users(course_id, refresh=refresh)
        institutional_emails = self._moodle_course_emails(moodle_users)
        academic_options = self._academic_period_options_for_emails(institutional_emails)
        context = self._resolve_course_context(course, academic_options)

        configured_period = dict(self.configured_mappings()).get(course_id)
        if configured_period is not None and any(
            int(period["period_code"]) == configured_period
            for period in context["periods"]
        ):
            configured_periods = self._recommended_period_codes(
                context["periods"],
                preferred_period_code=configured_period,
            )
            context["recommended_period_code"] = configured_periods[0]
            context["recommended_period_codes"] = configured_periods

        return {
            "id": course_id,
            "name": (
                course.get("displayname")
                or course.get("fullname")
                or course.get("shortname")
                or f"Curso Moodle {course_id}"
            ),
            "shortname": course.get("shortname") or "",
            "idnumber": course.get("idnumber") or "",
            "identity_key": "CorreoIntec",
            "identity_relation": (
                "Moodle.email = CorreosEstudIntec.CorreoIntec; "
                "CorreosEstudIntec.codestud = DATOS_ESTUD.codigo_estud = "
                "CARRERAXESTUD.codigo_estud"
            ),
            "moodle_users": len(moodle_users),
            "moodle_users_with_email": len(institutional_emails),
            **context,
        }

    @staticmethod
    def _moodle_course_emails(moodle_users: Sequence[dict[str, Any]]) -> set[str]:
        institutional_emails: set[str] = set()
        for user in moodle_users:
            email = (
                normalize_institutional_email(user.get("email"))
                or normalize_institutional_email(user.get("username"))
            )
            if email:
                institutional_emails.add(email)
        return institutional_emails

    @staticmethod
    def _recommended_period_codes(
        periods: Sequence[dict[str, Any]],
        *,
        preferred_period_code: int | None = None,
    ) -> list[int]:
        """Select up to three periods supported by the strongest student overlap."""
        eligible_by_code: dict[int, dict[str, Any]] = {}
        for period in periods:
            period_code = int(period.get("period_code") or 0)
            period_type = _text(period.get("period_type")).upper()
            students = int(period.get("students") or 0)
            current = eligible_by_code.get(period_code)
            if (
                period_code > 0
                and period_type in {"R", "H"}
                and students > 0
                and (current is None or students > int(current.get("students") or 0))
            ):
                eligible_by_code[period_code] = period
        eligible_periods = list(eligible_by_code.values())
        if not eligible_periods:
            return []

        preferred_period = next(
            (
                period
                for period in eligible_periods
                if int(period.get("period_code") or 0) == preferred_period_code
            ),
            None,
        )
        periods_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for period in eligible_periods:
            periods_by_type[_text(period.get("period_type")).upper()].append(period)

        def ranked(period_type: str) -> list[dict[str, Any]]:
            return sorted(
                periods_by_type[period_type],
                key=lambda item: (
                    -int(item.get("students") or 0),
                    -int(item.get("period_code") or 0),
                ),
            )

        if preferred_period is not None:
            selected_type = _text(preferred_period.get("period_type")).upper()
        else:
            selected_type = max(
                periods_by_type,
                key=lambda period_type: (
                    sum(
                        int(period.get("students") or 0)
                        for period in ranked(period_type)[:3]
                    ),
                    int(ranked(period_type)[0].get("students") or 0),
                    max(
                        int(period.get("period_code") or 0)
                        for period in periods_by_type[period_type]
                    ),
                ),
            )

        selected_periods = ranked(selected_type)
        if preferred_period is not None:
            selected_periods = [
                preferred_period,
                *[
                    period
                    for period in selected_periods
                    if int(period.get("period_code") or 0) != preferred_period_code
                ],
            ]
        return [int(period["period_code"]) for period in selected_periods[:3]]

    def _resolve_course_context(
        self,
        course: dict[str, Any],
        academic_options: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        scores_by_code: dict[str, int] = {}
        for option in academic_options:
            academic_code = canonical_course_code(option.get("course_code"))
            if not academic_code:
                continue
            scores_by_code[academic_code] = max(
                scores_by_code.get(academic_code, 0),
                _course_code_match_score(course, academic_code),
            )

        best_code_score = max(scores_by_code.values(), default=0)
        best_codes = {
            code
            for code, score in scores_by_code.items()
            if score == best_code_score and score > 0
        }
        matched_codes = set(best_codes) if len(best_codes) == 1 else set()
        match_method = "codigo_pensum_y_correointec" if matched_codes else ""

        if not matched_codes:
            scores_by_matter: dict[str, int] = {}
            for option in academic_options:
                matter_key = _normalized_text(option.get("matter"))
                if not matter_key:
                    continue
                scores_by_matter[matter_key] = max(
                    scores_by_matter.get(matter_key, 0),
                    _matter_match_score(course, option.get("matter")),
                )
            best_score = max(scores_by_matter.values(), default=0)
            best_matters = {
                matter
                for matter, score in scores_by_matter.items()
                if score == best_score and score > 0
            }
            if len(best_matters) == 1:
                matched_matter = next(iter(best_matters))
                matched_codes = {
                    canonical_course_code(option.get("course_code"))
                    for option in academic_options
                    if _normalized_text(option.get("matter")) == matched_matter
                    and canonical_course_code(option.get("course_code"))
                }
                match_method = "asignatura_pensum_y_correointec"

        matched_options = [
            dict(option)
            for option in academic_options
            if canonical_course_code(option.get("course_code")) in matched_codes
        ]
        unique_options = {
            (
                int(option["period_code"]),
                canonical_course_code(option.get("course_code")),
                _text(option.get("period_type")).upper(),
            ): option
            for option in matched_options
        }
        periods = sorted(
            unique_options.values(),
            key=lambda item: (-int(item["period_code"]), _normalized_text(item.get("career"))),
        )
        matched_students = sum(int(option.get("students") or 0) for option in periods)
        recommended_period_codes = self._recommended_period_codes(periods)

        if not academic_options:
            reason = (
                "Ningún correo del curso Moodle coincide exactamente con CorreoIntec y una "
                "matrícula activa enlazada por codestud en CARRERAXESTUD"
            )
        elif not matched_codes:
            reason = (
                "Los estudiantes coinciden por CorreoIntec, pero no se pudo identificar una "
                "asignatura única para registrar sus notas"
            )
        else:
            reason = (
                "Curso validado por código o asignatura de PENSUM; estudiantes enlazados por "
                "CorreoIntec y codestud hasta CARRERAXESTUD"
            )

        return {
            "matched_course_code": sorted(matched_codes)[0] if matched_codes else "",
            "matched_course_codes": sorted(matched_codes),
            "match_method": match_method,
            "has_academic_match": bool(periods),
            "recommended_period_code": (
                recommended_period_codes[0] if recommended_period_codes else None
            ),
            "recommended_period_codes": recommended_period_codes,
            "matched_students": matched_students,
            "resolution_reason": reason,
            "periods": periods,
        }

    async def preview(
        self,
        *,
        course_id: int,
        period_code: int | None = None,
        period_codes: Sequence[int] | None = None,
        refresh: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        self._require_enabled()
        selected_period_codes = normalize_period_codes(period_code, period_codes)
        courses = await self._moodle.get_all_courses(refresh=refresh)
        course = next((item for item in courses if int(item.get("id") or 0) == course_id), None)
        if course is None:
            raise MoodleGradeSyncError("No se encontró el curso seleccionado en Moodle")

        course_codes = self._course_codes(course)
        moodle_users = await self._moodle.get_course_enrolled_users(
            course_id,
            refresh=refresh,
        )
        institutional_emails = self._moodle_course_emails(moodle_users)
        if not institutional_emails:
            raise MoodleGradeSyncError(
                "El curso Moodle no tiene usuarios con un correo institucional válido"
            )

        def load_enrollments(codes: set[str]) -> tuple[dict[int, list[dict[str, Any]]], list[int]]:
            rows_by_period: dict[int, list[dict[str, Any]]] = {}
            missing_periods: list[int] = []
            for selected_period_code in selected_period_codes:
                period_rows = (
                    self._academic_enrollments(
                        selected_period_code,
                        codes,
                        institutional_emails,
                    )
                    if codes
                    else []
                )
                if period_rows:
                    rows_by_period[selected_period_code] = period_rows
                else:
                    missing_periods.append(selected_period_code)
            return rows_by_period, missing_periods

        enrollments_by_period, missing_periods = load_enrollments(course_codes)
        if missing_periods:
            # CorreoIntec is the only student identity shared by Moodle and INTECBDD.
            # Course metadata selects the subject only after that identity match.
            academic_options = self._academic_period_options_for_emails(institutional_emails)
            context = self._resolve_course_context(course, academic_options)
            resolved_codes = {
                canonical_course_code(value)
                for value in context["matched_course_codes"]
                if canonical_course_code(value)
            }
            valid_period_codes = {
                int(period["period_code"])
                for period in context["periods"]
            }
            invalid_periods = [
                value for value in selected_period_codes if value not in valid_period_codes
            ]
            if not resolved_codes or invalid_periods:
                detail = context["resolution_reason"]
                if invalid_periods and resolved_codes:
                    detail = (
                        "Los períodos seleccionados no corresponden a los estudiantes del curso "
                        "Moodle validados por CorreoIntec"
                    )
                raise MoodleGradeSyncError(detail)
            course_codes = resolved_codes
            enrollments_by_period, missing_periods = load_enrollments(course_codes)
            if missing_periods:
                raise MoodleGradeSyncError(
                    "No existen matrículas activas para el curso y los períodos validados por CorreoIntec"
                )

        enrollments = [
            enrollment
            for selected_period_code in selected_period_codes
            for enrollment in enrollments_by_period[selected_period_code]
        ]

        unique_enrollments: dict[int, dict[str, Any]] = {}
        for enrollment in enrollments:
            row_id = int(enrollment.get("row_id") or 0)
            if row_id in unique_enrollments:
                raise MoodleGradeSyncError(
                    "Una matrícula académica aparece repetida entre los períodos seleccionados"
                )
            unique_enrollments[row_id] = enrollment
        enrollments = sorted(
            unique_enrollments.values(),
            key=lambda item: (
                int(item["period_code"]),
                _normalized_text(item["student_name"]),
                int(item["row_id"]),
            ),
        )

        period_types = {str(row["period_type"] or "").upper() for row in enrollments}
        if len(period_types) != 1 or next(iter(period_types)) not in {"R", "H"}:
            raise MoodleGradeSyncError(
                "Los períodos seleccionados deben pertenecer todos a matrícula regular o todos a homologación"
            )
        enrollment_type = next(iter(period_types))

        period_metadata = [
            {
                "code": selected_period_code,
                "name": _text(enrollments_by_period[selected_period_code][0]["period_name"]),
                "type": enrollment_type,
            }
            for selected_period_code in selected_period_codes
        ]

        moodle_grades = await self._moodle.get_course_grade_items(course_id, refresh=refresh)
        users_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for user in moodle_users:
            indexed_emails = {
                normalize_institutional_email(user.get("email")),
                normalize_institutional_email(user.get("username")),
            }
            for email in indexed_emails - {""}:
                if not any(int(existing.get("id") or 0) == int(user.get("id") or 0) for existing in users_by_email[email]):
                    users_by_email[email].append(user)
        grades_by_user = {
            int(group.get("userid") or 0): group
            for group in moodle_grades
            if int(group.get("userid") or 0) > 0
        }
        ledger: dict[tuple[Any, ...], Any] = {}
        for selected_period_code, period_enrollments in enrollments_by_period.items():
            ledger.update(self._grade_ledger(selected_period_code, period_enrollments))

        changes: list[dict[str, Any]] = []
        enrollment_summaries: list[dict[str, Any]] = []
        validation_counts = {
            "selected_periods": len(selected_period_codes),
            "academic_enrollments": len(enrollments),
            "moodle_course_users": len(moodle_users),
            "matched_by_email": 0,
            "matched_by_registry": 0,
            "matched_by_data_fallback": 0,
            "missing_institutional_email": 0,
            "not_enrolled_in_course": 0,
            "ambiguous_users": 0,
        }
        for enrollment in enrollments:
            email_candidates = institutional_email_candidates(enrollment)
            preferred_source, preferred_email = email_candidates[0] if email_candidates else ("Sin registro", "")
            students, matched_email, matched_source = match_course_users_by_institutional_email(
                enrollment,
                users_by_email,
            )
            base_summary = {
                "student_code": int(enrollment["student_code"]),
                "student": _text(enrollment["student_name"]),
                "identity": _text(enrollment["student_identity"]),
                "email": preferred_email,
                "email_source": preferred_source,
                "moodle_email": "",
                "moodle_user_id": 0,
                "course_enrollment_validated": False,
                "career": _text(enrollment["career"]),
                "matter": _text(enrollment["matter_name"]),
                "malla_code": int(enrollment.get("malla_code") or 0),
                "matter_code": int(enrollment.get("matter_code") or 0),
                "parallel": _text(enrollment.get("parallel")),
                "period": _text(enrollment["period_name"]),
                "period_code": int(enrollment["period_code"]),
                "type": enrollment_type,
            }
            if not email_candidates:
                validation_counts["missing_institutional_email"] += 1
                enrollment_summaries.append(
                    {
                        **base_summary,
                        "status": "missing_institutional_email",
                        "reason": (
                            "El estudiante no tiene un CorreoIntec vigente asociado a su "
                            "código único en CorreosEstudIntec"
                        ),
                    }
                )
                continue
            if len(students) != 1:
                status = "not_enrolled" if not students else "ambiguous_user"
                if not students:
                    validation_counts["not_enrolled_in_course"] += 1
                    reason = "El correo institucional no consta entre los usuarios del curso Moodle seleccionado"
                else:
                    validation_counts["ambiguous_users"] += 1
                    reason = "Los correos institucionales del estudiante identifican más de un usuario en el curso Moodle"
                enrollment_summaries.append({**base_summary, "status": status, "reason": reason})
                continue

            moodle_user = students[0]
            moodle_email = (
                normalize_institutional_email(moodle_user.get("email"))
                or normalize_institutional_email(moodle_user.get("username"))
            )
            base_summary.update(
                {
                    "email": matched_email,
                    "email_source": matched_source,
                    "moodle_email": moodle_email,
                    "moodle_user_id": int(moodle_user.get("id") or 0),
                    "course_enrollment_validated": True,
                }
            )
            validation_counts["matched_by_email"] += 1
            if matched_source != "CorreosEstudIntec":
                raise MoodleGradeSyncError(
                    "La identidad de Moodle no fue resuelta desde CorreosEstudIntec"
                )
            validation_counts["matched_by_registry"] += 1
            grade_group = grades_by_user.get(int(moodle_user.get("id") or 0))
            if grade_group is None:
                enrollment_summaries.append(
                    {**base_summary, "status": "without_grades", "reason": "Moodle no devolvió notas para el usuario"}
                )
                continue

            candidates, candidate_errors = self._grade_candidates(
                grade_group.get("gradeitems") or [],
                enrollment_type,
            )
            if candidate_errors:
                enrollment_summaries.append(
                    {**base_summary, "status": "invalid_grade", "reason": "; ".join(candidate_errors)}
                )

            selected, conflicts = self._select_candidates(candidates)
            if conflicts:
                enrollment_summaries.append(
                    {
                        **base_summary,
                        "status": "ambiguous_grade",
                        "reason": "Existen notas Moodle distintas para el mismo componente académico",
                    }
                )
                continue
            if not selected:
                enrollment_summaries.append(
                    {
                        **base_summary,
                        "status": "without_exam_grade",
                        "reason": (
                            "No existen cuestionarios o tareas calificadas para asignar por parcial "
                            "en la sección Evaluación de Moodle"
                            if enrollment_type == "R"
                            else "No existe un cuestionario o una tarea calificada "
                            "en la sección Evaluación de Moodle"
                        ),
                    }
                )
                continue

            for target, candidate in selected.items():
                current_value = enrollment.get(target)
                ledger_key = self._ledger_key(enrollment, target)
                previous_sync = ledger.get(ledger_key)
                status, reason = self._change_status(
                    current=current_value,
                    incoming=candidate["grade"],
                    previous_sync=previous_sync,
                    ungraded=self._is_ungraded(enrollment),
                    allow_override=replace_existing,
                )
                changes.append(
                    {
                        **base_summary,
                        "row_id": int(enrollment["row_id"]),
                        "malla_code": int(enrollment.get("malla_code") or 0),
                        "matter_code": int(enrollment.get("matter_code") or 0),
                        "parallel": _text(enrollment.get("parallel")),
                        "group": int(enrollment["group_number"] or 0),
                        "enrollment_number": int(enrollment["enrollment_number"] or 0),
                        "field": target,
                        "component": self._component_label(target),
                        "current_grade": _number(current_value),
                        "incoming_grade": candidate["grade"],
                        "previous_synced_grade": _number(previous_sync),
                        "moodle_user_id": int(moodle_user.get("id") or 0),
                        "moodle_grade_item_id": int(candidate["item_id"] or 0),
                        "moodle_grade_item": candidate["item_name"],
                        "moodle_grade_item_count": int(candidate["candidate_count"]),
                        "moodle_grade_items": candidate["candidate_item_names"],
                        "moodle_grade_candidates": candidate["candidate_items"],
                        "moodle_grade_selection": candidate["selection_rule"],
                        "moodle_partial_label": candidate["partial_label"],
                        "moodle_partial_segment": candidate["partial_segment"],
                        "moodle_partial_source": candidate["partial_source"],
                        "moodle_raw_grade": candidate["raw_grade"],
                        "moodle_grade_min": candidate["grade_min"],
                        "moodle_grade_max": candidate["grade_max"],
                        "moodle_grade_raw_source": candidate["raw_source"],
                        "moodle_grade_scale_source": candidate["scale_source"],
                        "duplicated_generic_grade": False,
                        "duplicated_component_grade": bool(candidate["duplicated"]),
                        "status": status,
                        "reason": reason,
                    }
                )

        counts: dict[str, int] = defaultdict(int)
        for change in changes:
            counts[change["status"]] += 1
        for summary in enrollment_summaries:
            counts[summary["status"]] += 1

        return {
            "course": {
                "id": course_id,
                "name": course.get("displayname") or course.get("fullname") or course.get("shortname"),
                "code": sorted(course_codes)[0],
            },
            # `period` se conserva para consumidores de una sola selección.
            "period": period_metadata[0],
            "periods": period_metadata,
            "selected_period_codes": selected_period_codes,
            "rule": (
                "R: cada tarea práctica de Evaluación actualiza Tareas 30% y Proyectos 30% "
                "de su parcial; cada cuestionario teórico actualiza Examen 40%. "
                if enrollment_type == "R"
                else "H: el cuestionario actualiza Teoría 40% y la tarea actualiza Práctica 60%. "
            )
            + (
                "Solo se migran actividades del bloque Moodle Evaluación y de sus secciones "
                "Primer, Segundo o Tercer parcial. Simuladores y recuperación quedan excluidos. "
                "El tipo quiz identifica cuestionarios y assign identifica tareas; el nombre es solo una referencia. "
                "El parcial se obtiene del nombre de la sección, de su rótulo o del nombre explícito "
                "de la actividad. Si Moodle usa secciones consecutivas sin rotular, se considera el "
                "orden de esas secciones; las actividades nunca se reparten por su orden. "
                "Si existen varias tareas o varios cuestionarios habilitados para un mismo componente, "
                "se utiliza la mayor nota normalizada sobre 10. Una nota ya sincronizada se vuelve a migrar "
                "únicamente cuando su valor cambia en Moodle."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "replace_existing": replace_existing,
            "counts": dict(counts),
            "course_validation": validation_counts,
            "changes": changes,
            "enrollment_warnings": enrollment_summaries,
            "can_apply": bool(
                self._settings.moodle_grade_sync_apply_enabled
                and any(item["status"] in _APPLICABLE_STATUSES for item in changes)
            ),
        }

    async def apply(
        self,
        *,
        course_id: int,
        period_code: int | None = None,
        period_codes: Sequence[int] | None = None,
        actor: str,
        actor_id: int | None = None,
        refresh: bool = True,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        self._require_enabled()
        selected_period_codes = normalize_period_codes(period_code, period_codes)
        if not self._settings.moodle_grade_sync_apply_enabled:
            raise MoodleGradeSyncError(
                "La escritura está deshabilitada; habilite MOODLE_GRADE_SYNC_APPLY_ENABLED después de validar la vista previa"
            )
        started_at = datetime.now(timezone.utc)
        preview = await self.preview(
            course_id=course_id,
            period_codes=selected_period_codes,
            refresh=refresh,
            replace_existing=replace_existing,
        )
        ready_changes: list[dict[str, Any]] = []
        for original in preview["changes"]:
            if original["status"] not in _APPLICABLE_STATUSES:
                continue
            change = dict(original)
            change["incoming_grade"] = _ten_point_grade(change.get("incoming_grade"))
            ready_changes.append(change)
        if not ready_changes:
            return {**preview, "applied": 0, "message": "No existen cambios aplicables para migrar"}

        applied = 0
        applied_by_period: dict[int, int] = defaultdict(int)
        conflicts: list[dict[str, Any]] = []
        with get_connection() as connection:
            cursor = connection.cursor()
            for selected_period_code in sorted(selected_period_codes):
                self._acquire_lock(cursor, course_id, selected_period_code)
            grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for change in ready_changes:
                grouped[int(change["row_id"])].append(change)

            for row_id, row_changes in grouped.items():
                current_row = self._current_grade_row(cursor, row_id)
                if current_row is None:
                    conflicts.extend({**item, "reason": "La matrícula dejó de existir"} for item in row_changes)
                    continue

                accepted: list[dict[str, Any]] = []
                for change in row_changes:
                    target = change["field"]
                    ledger_value = self._current_ledger_value(cursor, change)
                    status, reason = self._change_status(
                        current=current_row.get(target),
                        incoming=change["incoming_grade"],
                        previous_sync=ledger_value,
                        ungraded=self._is_ungraded(current_row),
                        allow_override=replace_existing,
                    )
                    if status == "ready_override" and not _same_grade(
                        current_row.get(target), change["current_grade"]
                    ):
                        conflicts.append(
                            {
                                **change,
                                "status": "stale_preview",
                                "reason": (
                                    "La nota cambió después de la vista previa; "
                                    "genere una nueva antes de reemplazarla"
                                ),
                            }
                        )
                        continue
                    if status not in _APPLICABLE_STATUSES | {"unchanged"}:
                        conflicts.append({**change, "status": status, "reason": reason})
                        continue
                    if status in _APPLICABLE_STATUSES:
                        accepted.append(change)

                if not accepted:
                    continue

                assignments = ", ".join(f"{item['field']} = ?" for item in accepted)
                parameters = [item["incoming_grade"] for item in accepted]
                cursor.execute(
                    f"UPDATE dbo.CARRERAXESTUD SET {assignments} WHERE TRY_CONVERT(bigint, num) = ?",
                    *parameters,
                    row_id,
                )
                if int(cursor.rowcount or 0) != 1:
                    raise MoodleGradeSyncError("No se pudo aislar la matrícula que debía actualizarse")

                for change in accepted:
                    self._upsert_ledger(cursor, change, course_id, actor)
                    current_row[change["field"]] = change["incoming_grade"]
                    applied += 1
                    applied_by_period[int(change["period_code"])] += 1
                self._recalculate_row(
                    cursor,
                    current_row,
                    actor,
                    enrollment_type=str(accepted[0]["type"]),
                )

            finished_at = datetime.now(timezone.utc)
            for selected_period_code in selected_period_codes:
                period_changes = [
                    change
                    for change in preview["changes"]
                    if int(change["period_code"]) == selected_period_code
                ]
                period_conflicts = [
                    conflict
                    for conflict in conflicts
                    if int(conflict.get("period_code") or 0) == selected_period_code
                ]
                self._insert_log(
                    cursor,
                    started_at=started_at,
                    finished_at=finished_at,
                    period_code=selected_period_code,
                    mode=self._execution_mode(actor, replace_existing=replace_existing),
                    status=(
                        "COMPLETADO"
                        if not period_conflicts
                        else "COMPLETADO_CON_CONFLICTOS"
                    ),
                    processed=len(period_changes),
                    updated=applied_by_period[selected_period_code],
                    errors=len(period_conflicts),
                    actor=actor,
                    statistics={
                        "course_id": course_id,
                        "period_codes": selected_period_codes,
                        "conflicts": len(period_conflicts),
                        "replace_existing": replace_existing,
                        "actor": actor,
                    },
                    actor_id=actor_id,
                )
            connection.commit()

        return {
            **preview,
            "applied": applied,
            "runtime_conflicts": conflicts,
            "message": (
                f"Se aplicaron {applied} componente(s) de calificación desde Moodle "
                f"en {len(selected_period_codes)} período(s)"
            ),
        }

    async def run_configured(self, *, apply: bool, actor: str = "TAREA_MOODLE") -> dict[str, Any]:
        mappings = self.configured_mappings()
        if not mappings:
            raise MoodleGradeSyncError("No existen correspondencias configuradas para la sincronización automática")
        automatic_apply_enabled = bool(
            self._settings.moodle_grade_sync_nightly_enabled
            or getattr(self._settings, "moodle_grade_sync_changes_enabled", False)
        )
        if apply and not automatic_apply_enabled:
            raise MoodleGradeSyncError("La ejecución automática con escritura está deshabilitada")

        results: list[dict[str, Any]] = []
        for course_id, period_code in mappings:
            try:
                result = (
                    await self.apply(
                        course_id=course_id,
                        period_code=period_code,
                        actor=actor,
                        refresh=True,
                    )
                    if apply
                    else await self.preview(
                        course_id=course_id,
                        period_code=period_code,
                        refresh=True,
                    )
                )
                results.append(
                    {
                        "course_id": course_id,
                        "period_code": period_code,
                        "ok": True,
                        "applied": int(result.get("applied") or 0),
                        "counts": result.get("counts", {}),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "course_id": course_id,
                        "period_code": period_code,
                        "ok": False,
                        "error": str(exc)[:500],
                    }
                )
        return {
            "mode": "apply" if apply else "preview",
            "processed": len(results),
            "successful": sum(1 for item in results if item["ok"]),
            "failed": sum(1 for item in results if not item["ok"]),
            "results": results,
        }

    def history(self, *, limit: int = 50) -> dict[str, Any]:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (?)
                    id, fecha_inicio, fecha_fin, duracion_segundos, periodo,
                    modo_ejecucion, estado, notas_procesadas, notas_actualizadas,
                    notas_insertadas, notas_error, mensaje, errores_detalle,
                    estadisticas, usuario_id
                FROM dbo.intec_moodlegradesynclog
                ORDER BY id DESC
                """,
                limit,
            )
            items = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        for item in items:
            for key in ("fecha_inicio", "fecha_fin"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            if item.get("duracion_segundos") is not None:
                item["duracion_segundos"] = float(item["duracion_segundos"])
        return {"items": items, "total": len(items)}

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise MoodleGradeSyncError("La lectura de calificaciones Moodle no está habilitada")

    @staticmethod
    def _execution_mode(actor: str, *, replace_existing: bool) -> str:
        if replace_existing:
            return "MANUAL_REEMPLAZO"
        normalized_actor = _normalized_text(actor)
        if normalized_actor.startswith("TAREA MOODLE CAMBIOS"):
            return "AUTOMATICO_CAMBIOS"
        if normalized_actor.startswith("TAREA MOODLE"):
            return "AUTOMATICO"
        return "MANUAL"

    @staticmethod
    def _course_codes(course: dict[str, Any]) -> set[str]:
        return {
            code
            for code in (
                canonical_course_code(course.get("idnumber")),
                canonical_course_code(course.get("shortname")),
            )
            if code
        }

    @staticmethod
    def _component_label(field: str) -> str:
        return {
            "P1Tareas": "Examen práctico P1 · Tareas 30%",
            "P1Proyectos": "Examen práctico P1 · Proyectos 30%",
            "P1Examen": "Examen teórico P1 · Examen 40%",
            "P2Tareas": "Examen práctico P2 · Tareas 30%",
            "P2Proyectos": "Examen práctico P2 · Proyectos 30%",
            "P2Examen": "Examen teórico P2 · Examen 40%",
            "P3Tareas": "Examen práctico P3 · Tareas 30%",
            "P3Proyectos": "Examen práctico P3 · Proyectos 30%",
            "P3Examen": "Examen teórico P3 · Examen 40%",
            "teoriaHomo": "Examen teórico de homologación",
            "practicahomo": "Examen práctico de homologación",
        }[field]

    @staticmethod
    def _component_percentage(field: str) -> int:
        if field in {"P1Tareas", "P1Proyectos", "P2Tareas", "P2Proyectos", "P3Tareas", "P3Proyectos"}:
            return 30
        if field in {"P1Examen", "P2Examen", "P3Examen", "teoriaHomo"}:
            return 40
        if field == "practicahomo":
            return 60
        raise MoodleGradeSyncError(f"Componente de calificación no permitido: {field}")

    @staticmethod
    def _is_ungraded(row: dict[str, Any]) -> bool:
        approval = _normalized_text(row.get("approval"))
        final = _number(row.get("final_grade"))
        return approval in {"", "P", "PENDIENTE"} and final in {None, 0.0}

    @staticmethod
    def _change_status(
        *,
        current: Any,
        incoming: Any,
        previous_sync: Any,
        ungraded: bool,
        allow_override: bool = False,
    ) -> tuple[str, str]:
        if _same_grade(current, incoming):
            return "unchanged", "La nota académica ya coincide con Moodle"
        if previous_sync is not None and _same_grade(previous_sync, incoming):
            if allow_override:
                return (
                    "ready_override",
                    "Reaplicación manual autorizada para una nota Moodle sin variación",
                )
            return (
                "source_unchanged",
                "La calificación de Evaluación no cambió desde la última sincronización Moodle",
            )
        if current is None or (_same_grade(current, 0) and ungraded and previous_sync is None):
            return "ready", "Componente sin una calificación académica asentada"
        if previous_sync is not None and _same_grade(current, previous_sync):
            return "ready", "La nota actual corresponde a la última sincronización Moodle"
        if allow_override:
            return (
                "ready_override",
                "Reemplazo manual autorizado para una nota académica existente",
            )
        return "manual_conflict", "La nota fue modificada fuera de la última sincronización Moodle"

    @staticmethod
    def _grade_candidates(
        grade_items: Iterable[dict[str, Any]],
        enrollment_type: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        def positive_int(value: Any) -> int | None:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        prepared_items: list[dict[str, Any]] = []
        for source_order, item in enumerate(grade_items, start=1):
            if item.get("evaluation_scope") is not True:
                continue
            if not item.get("course_section_visible") or not item.get("course_module_visible"):
                continue
            if not _enabled_grade_item(item):
                continue
            item_name = _text(item.get("itemname"))
            item_module = _text(item.get("itemmodule")).casefold()
            if item_module not in _EVALUATION_MODULES:
                continue

            section_name = _text(item.get("course_section_name"))
            normalized_section = _normalized_text(section_name)
            metadata_partial = positive_int(item.get("course_section_partial"))
            if metadata_partial not in {1, 2, 3}:
                metadata_partial = None
            named_section_partial = positive_int(
                item.get("course_section_named_partial")
            ) or _partial_number(normalized_section)
            if named_section_partial not in {1, 2, 3}:
                named_section_partial = None
            label_partial = positive_int(item.get("course_label_partial"))
            if label_partial not in {1, 2, 3}:
                label_partial = None
            partial_label = _text(item.get("course_partial_label"))
            partial_segment = _text(item.get("course_partial_segment"))
            explicit_label_partial = (
                label_partial
                if label_partial in {1, 2, 3} and partial_label and partial_segment
                else None
            )
            section_id = positive_int(item.get("course_section_id"))
            section_number = positive_int(item.get("course_section_number"))
            section_key: tuple[Any, ...] | None = None
            if section_id is not None:
                section_key = ("id", section_id)
            elif section_number is not None:
                section_key = ("number", section_number, normalized_section)
            elif normalized_section:
                section_key = ("name", normalized_section)

            prepared_items.append(
                {
                    "item": item,
                    "item_name": item_name,
                    "item_module": item_module,
                    "section_key": section_key,
                    "named_section_partial": named_section_partial,
                    "label_partial": label_partial,
                    "explicit_label_partial": explicit_label_partial,
                    "partial_label": partial_label,
                    "partial_segment": partial_segment,
                    "metadata_partial": metadata_partial,
                    "item_partial": _partial_number(_normalized_text(item_name)),
                    "source_order": source_order,
                }
            )

        def order_value(value: Any, fallback: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return fallback
            return parsed if parsed > 0 else fallback

        prepared_items.sort(
            key=lambda entry: (
                order_value(entry["item"].get("course_section_number"), 1_000_000),
                order_value(entry["item"].get("course_module_order"), entry["source_order"]),
                entry["source_order"],
                order_value(entry["item"].get("id"), 1_000_000),
            )
        )

        ordered_section_keys: list[tuple[Any, ...]] = []
        entries_by_section: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for entry in prepared_items:
            section_key = entry["section_key"]
            if section_key is None:
                continue
            if section_key not in entries_by_section:
                ordered_section_keys.append(section_key)
            entries_by_section[section_key].append(entry)

        inherited_section_partials: dict[tuple[Any, ...], int] = {}
        for section_key, section_entries in entries_by_section.items():
            explicit_context_partials = {
                entry["named_section_partial"]
                or entry["label_partial"]
                or entry["metadata_partial"]
                for entry in section_entries
                if (
                    entry["named_section_partial"]
                    or entry["label_partial"]
                    or entry["metadata_partial"]
                )
                in {1, 2, 3}
            }
            if len(explicit_context_partials) == 1:
                inherited_section_partials[section_key] = next(iter(explicit_context_partials))
                continue

            explicit_item_partials = {
                entry["item_partial"]
                for entry in section_entries
                if entry["item_partial"] in {1, 2, 3}
            }
            if len(explicit_item_partials) == 1:
                # Una actividad rotulada permite ubicar también a sus actividades
                # hermanas dentro de la misma sección de Evaluación.
                inherited_section_partials[section_key] = next(iter(explicit_item_partials))

        entries_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in prepared_items:
            partial_segment = entry["partial_segment"]
            if partial_segment:
                entries_by_segment[partial_segment].append(entry)

        segment_partials: dict[str, int] = {}
        for partial_segment, segment_entries in entries_by_segment.items():
            # Moodle puede incluir "Parcial 2" en el nombre de un segundo intento
            # ubicado todavía bajo la etiqueta Primer parcial. El contexto común
            # del segmento debe prevalecer sobre esos nombres individuales.
            for context_key in (
                "explicit_label_partial",
                "label_partial",
                "named_section_partial",
                "metadata_partial",
            ):
                context_values = {
                    entry[context_key]
                    for entry in segment_entries
                    if entry[context_key] in {1, 2, 3}
                }
                if len(context_values) == 1:
                    segment_partials[partial_segment] = next(iter(context_values))
                    break

        ordered_section_partials: dict[tuple[Any, ...], int] = {}
        if 1 < len(ordered_section_keys) <= 3:
            used_partials = set(inherited_section_partials.values())
            available_partials = [partial for partial in (1, 2, 3) if partial not in used_partials]
            for section_key in ordered_section_keys:
                if section_key in inherited_section_partials or not available_partials:
                    continue
                ordered_section_partials[section_key] = available_partials.pop(0)

        for entry in prepared_items:
            section_key = entry["section_key"]
            # La ubicación estructural en Moodle es autoritativa. Un nombre como
            # "2da oportunidad" describe otro intento, no el segundo parcial.
            # El nombre de la actividad solo se usa cuando Moodle no entrega un
            # rótulo, sección, metadato ni segmento académico utilizable.
            resolution_options = (
                ("segment", segment_partials.get(entry["partial_segment"])),
                ("label", entry["explicit_label_partial"]),
                ("section", entry["named_section_partial"]),
                ("metadata", entry["metadata_partial"]),
                ("label_metadata", entry["label_partial"]),
                ("section_inheritance", inherited_section_partials.get(section_key)),
                ("section_order", ordered_section_partials.get(section_key)),
                ("activity", entry["item_partial"]),
            )
            partial_source, resolved_partial = next(
                (
                    (source, value)
                    for source, value in resolution_options
                    if value in {1, 2, 3}
                ),
                ("", None),
            )
            entry["resolved_partial"] = resolved_partial
            entry["partial_source"] = partial_source

        for entry in prepared_items:
            item = entry["item"]
            item_name = entry["item_name"]
            item_module = entry["item_module"]
            partial = entry["resolved_partial"]
            if _text(enrollment_type).upper() == "R" and partial not in {1, 2, 3}:
                errors.append(
                    f"{item_name or 'Ítem sin nombre'}: no se pudo identificar "
                    "el primer, segundo o tercer parcial dentro de Evaluación"
                )
                continue
            targets = _evaluation_module_targets(item_module, enrollment_type, partial)
            if not targets:
                continue
            try:
                grade_details = _normalize_moodle_grade_details(item)
            except MoodleGradeSyncError as exc:
                errors.append(f"{item_name or 'Ítem sin nombre'}: {exc}")
                continue
            if grade_details is None:
                continue
            grade = float(grade_details["grade"])
            duplicated = len(targets) > 1
            for target in targets:
                candidates.append(
                    {
                        "target": target,
                        "grade": grade,
                        "item_id": int(item.get("id") or 0),
                        "item_name": item_name,
                        "activity_type": item_module,
                        "partial": partial,
                        "partial_label": entry["partial_label"]
                        or _PARTIAL_LABELS.get(partial, ""),
                        "partial_segment": entry["partial_segment"],
                        "partial_source": entry["partial_source"],
                        "course_section_id": int(item.get("course_section_id") or 0),
                        "course_section_name": _text(item.get("course_section_name")),
                        "duplicated": duplicated,
                        "priority": 3,
                        "raw_grade": grade_details["raw_grade"],
                        "grade_min": grade_details["grade_min"],
                        "grade_max": grade_details["grade_max"],
                        "raw_source": grade_details["raw_source"],
                        "scale_source": grade_details["scale_source"],
                    }
                )
        return candidates, errors

    @staticmethod
    def _select_candidates(
        candidates: Iterable[dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], set[str]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate["target"]].append(candidate)
        selected: dict[str, dict[str, Any]] = {}
        conflicts: set[str] = set()
        for target, target_candidates in grouped.items():
            priority = max(item["priority"] for item in target_candidates)
            preferred = [item for item in target_candidates if item["priority"] == priority]
            winner = sorted(
                preferred,
                key=lambda item: (-float(item["grade"]), int(item["item_id"])),
            )[0]
            ordered_candidates = sorted(
                preferred,
                key=lambda item: (-float(item["grade"]), int(item["item_id"])),
            )
            selected[target] = {
                **winner,
                "candidate_count": len(preferred),
                "candidate_item_ids": [int(item["item_id"]) for item in preferred],
                "candidate_item_names": [item["item_name"] for item in preferred],
                "candidate_items": [
                    {
                        "item_id": int(item["item_id"]),
                        "item_name": item["item_name"],
                        "grade": float(item["grade"]),
                        "activity_type": item["activity_type"],
                        "selected": int(item["item_id"]) == int(winner["item_id"]),
                    }
                    for item in ordered_candidates
                ],
                "selection_rule": "highest_grade" if len(preferred) > 1 else "single_grade",
            }
        return selected, conflicts

    @staticmethod
    def _ledger_key(enrollment: dict[str, Any], field: str) -> tuple[Any, ...]:
        return (
            str(enrollment["student_code"]),
            str(enrollment["period_code"]),
            str(enrollment["matter_code"]),
            _text(enrollment["parallel"]).upper(),
            _text(enrollment["period_type"]).upper(),
            field,
        )

    def _academic_period_options(self) -> list[dict[str, Any]]:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(int, ce.codigo_periodo) AS period_code,
                    MAX(TRY_CONVERT(nvarchar(255), per.Detalle_Periodo)) AS period_name,
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))) AS period_type,
                    TRY_CONVERT(nvarchar(100), pen.cod_materia) AS course_code,
                    MAX(TRY_CONVERT(nvarchar(255), pen.Nomb_Materia)) AS matter,
                    MAX(TRY_CONVERT(nvarchar(255), car.Nombre_Basica)) AS career,
                    COUNT(DISTINCT TRY_CONVERT(int, ce.cod_anio_Basica)) AS career_count,
                    COUNT(DISTINCT TRY_CONVERT(int, ce.codigo_estud)) AS students
                FROM dbo.CARRERAXESTUD AS ce
                INNER JOIN dbo.DATOS_ESTUD AS de
                  ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, ce.codigo_estud)
                INNER JOIN dbo.PENSUM AS pen
                  ON TRY_CONVERT(int, pen.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                 AND TRY_CONVERT(int, pen.codigo_materia) = TRY_CONVERT(int, ce.codigo_materia)
                INNER JOIN dbo.PERIODO AS per
                  ON TRY_CONVERT(int, per.cod_periodo) = TRY_CONVERT(int, ce.codigo_periodo)
                LEFT JOIN dbo.CARRERAS AS car
                  ON TRY_CONVERT(int, car.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), de.Estado)))) IN (N'A', N'ACTIVO', N'ACTIVA')
                  AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), pen.cod_materia))), N'') IS NOT NULL
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))) IN (N'R', N'H')
                GROUP BY
                    TRY_CONVERT(int, ce.codigo_periodo),
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))),
                    TRY_CONVERT(nvarchar(100), pen.cod_materia)
                """
            )
            options = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        for option in options:
            career_count = int(option.get("career_count") or 0)
            if career_count > 1:
                option["career"] = f"{career_count} carreras"
        return options

    def _academic_period_options_for_emails(
        self,
        institutional_emails: Iterable[str],
    ) -> list[dict[str, Any]]:
        """Return active academic subjects for Moodle users identified by CorreoIntec."""
        emails = sorted({
            normalized
            for value in institutional_emails
            if (normalized := normalize_institutional_email(value))
        })
        if not emails:
            return []

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE #MoodleInstitutionalEmails (
                    email nvarchar(254) COLLATE Latin1_General_100_CI_AS NOT NULL PRIMARY KEY
                )
                """
            )
            cursor.executemany(
                "INSERT INTO #MoodleInstitutionalEmails (email) VALUES (?)",
                [(email,) for email in emails],
            )
            cursor.execute(
                """
                WITH EmailRegistry AS (
                    SELECT DISTINCT
                        TRY_CONVERT(int, email_row.codestud) AS student_code,
                        LOWER(LTRIM(RTRIM(
                            REPLACE(REPLACE(REPLACE(
                                TRY_CONVERT(nvarchar(254), email_row.CorreoIntec),
                                NCHAR(160), N' '
                            ), NCHAR(8203), N''), NCHAR(65279), N'')
                        ))) COLLATE Latin1_General_100_CI_AS AS institutional_email
                    FROM dbo.CorreosEstudIntec AS email_row
                    WHERE TRY_CONVERT(int, email_row.codestud) IS NOT NULL
                      AND NULLIF(
                            LTRIM(RTRIM(TRY_CONVERT(nvarchar(254), email_row.CorreoIntec))),
                            N''
                          ) IS NOT NULL
                ),
                UniqueMoodleIdentity AS (
                    SELECT
                        MIN(registry.student_code) AS student_code,
                        registry.institutional_email
                    FROM EmailRegistry AS registry
                    INNER JOIN #MoodleInstitutionalEmails AS moodle
                      ON moodle.email = registry.institutional_email
                    GROUP BY registry.institutional_email
                    HAVING COUNT(DISTINCT registry.student_code) = 1
                ),
                AcademicIdentity AS (
                    SELECT
                        TRY_CONVERT(int, ce.codigo_periodo) AS period_code,
                        TRY_CONVERT(nvarchar(255), per.Detalle_Periodo) AS period_name,
                        UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))) AS period_type,
                        TRY_CONVERT(nvarchar(100), pen.cod_materia) AS course_code,
                        TRY_CONVERT(nvarchar(255), pen.Nomb_Materia) AS matter,
                        TRY_CONVERT(int, ce.cod_anio_Basica) AS career_code,
                        TRY_CONVERT(nvarchar(255), car.Nombre_Basica) AS career,
                        identity_row.student_code,
                        identity_row.institutional_email
                    FROM UniqueMoodleIdentity AS identity_row
                    INNER JOIN dbo.DATOS_ESTUD AS de
                      ON TRY_CONVERT(int, de.codigo_estud) = identity_row.student_code
                    INNER JOIN dbo.CARRERAXESTUD AS ce
                      ON TRY_CONVERT(int, ce.codigo_estud) = identity_row.student_code
                    INNER JOIN dbo.PENSUM AS pen
                      ON TRY_CONVERT(int, pen.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                     AND TRY_CONVERT(int, pen.codigo_materia) = TRY_CONVERT(int, ce.codigo_materia)
                    INNER JOIN dbo.PERIODO AS per
                      ON TRY_CONVERT(int, per.cod_periodo) = TRY_CONVERT(int, ce.codigo_periodo)
                    LEFT JOIN dbo.CARRERAS AS car
                      ON TRY_CONVERT(int, car.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                    WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), de.Estado))))
                          IN (N'A', N'ACTIVO', N'ACTIVA')
                      AND NULLIF(
                            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), pen.cod_materia))),
                            N''
                          ) IS NOT NULL
                      AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula))))
                          IN (N'R', N'H')
                )
                SELECT
                    academic.period_code,
                    MAX(academic.period_name) AS period_name,
                    academic.period_type,
                    academic.course_code,
                    MAX(academic.matter) AS matter,
                    MAX(academic.career) AS career,
                    COUNT(DISTINCT academic.career_code) AS career_count,
                    COUNT(DISTINCT academic.student_code) AS students
                FROM AcademicIdentity AS academic
                GROUP BY
                    academic.period_code,
                    academic.period_type,
                    academic.course_code
                ORDER BY academic.period_code DESC, academic.course_code
                """
            )
            options = [_row_to_dict(cursor, row) for row in cursor.fetchall()]

        for option in options:
            career_count = int(option.get("career_count") or 0)
            if career_count > 1:
                option["career"] = f"{career_count} carreras"
        return options

    def _academic_enrollments(
        self,
        period_code: int,
        course_codes: set[str],
        institutional_emails: set[str],
    ) -> list[dict[str, Any]]:
        normalized_emails = sorted(
            {
                normalized
                for email in institutional_emails
                if (normalized := normalize_institutional_email(email))
            }
        )
        if not normalized_emails:
            return []

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE #MoodleInstitutionalEmails (
                    email nvarchar(254) COLLATE Latin1_General_100_CI_AS NOT NULL PRIMARY KEY
                )
                """
            )
            cursor.executemany(
                "INSERT INTO #MoodleInstitutionalEmails (email) VALUES (?)",
                [(email,) for email in normalized_emails],
            )
            cursor.execute(
                """
                WITH EmailRegistry AS (
                    SELECT DISTINCT
                        TRY_CONVERT(int, email_row.codestud) AS student_code,
                        LOWER(LTRIM(RTRIM(
                            REPLACE(REPLACE(REPLACE(
                                TRY_CONVERT(nvarchar(254), email_row.CorreoIntec),
                                NCHAR(160), N' '
                            ), NCHAR(8203), N''), NCHAR(65279), N'')
                        ))) COLLATE Latin1_General_100_CI_AS AS registry_email
                    FROM dbo.CorreosEstudIntec AS email_row
                    WHERE TRY_CONVERT(int, email_row.codestud) IS NOT NULL
                      AND NULLIF(
                            LTRIM(RTRIM(TRY_CONVERT(nvarchar(254), email_row.CorreoIntec))),
                            N''
                          ) IS NOT NULL
                ),
                UniqueMoodleIdentity AS (
                    SELECT
                        MIN(email_registry.student_code) AS student_code,
                        email_registry.registry_email
                    FROM EmailRegistry AS email_registry
                    INNER JOIN #MoodleInstitutionalEmails AS moodle
                      ON moodle.email = email_registry.registry_email
                    GROUP BY email_registry.registry_email
                    HAVING COUNT(DISTINCT email_registry.student_code) = 1
                )
                SELECT
                    TRY_CONVERT(bigint, ce.num) AS row_id,
                    TRY_CONVERT(int, ce.codigo_estud) AS student_code,
                    email_registry.student_code AS registry_student_code,
                    TRY_CONVERT(int, ce.cod_anio_Basica) AS malla_code,
                    TRY_CONVERT(int, ce.codigo_materia) AS matter_code,
                    TRY_CONVERT(int, ce.codigo_periodo) AS period_code,
                    TRY_CONVERT(int, ce.Num_Matricula) AS enrollment_number,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), ce.paralelo))) AS parallel,
                    TRY_CONVERT(int, ce.NumGrupo) AS group_number,
                    TRY_CONVERT(nvarchar(100), pen.cod_materia) AS course_code,
                    TRY_CONVERT(nvarchar(255), pen.Nomb_Materia) AS matter_name,
                    TRY_CONVERT(nvarchar(255), car.Nombre_Basica) AS career,
                    TRY_CONVERT(nvarchar(255), per.Detalle_Periodo) AS period_name,
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))) AS period_type,
                    TRY_CONVERT(nvarchar(50), de.Cedula_Est) AS student_identity,
                    TRY_CONVERT(nvarchar(255), de.Apellidos_nombre) AS student_name,
                    email_registry.registry_email AS institutional_email,
                    email_registry.registry_email AS registry_email,
                    ce.P1Tareas, ce.P1Proyectos, ce.P1Examen,
                    ce.P2Tareas, ce.P2Proyectos, ce.P2Examen,
                    ce.P3Tareas, ce.P3Proyectos, ce.P3Examen,
                    ce.teoriaHomo, ce.practicahomo, ce.Recuperacion,
                    ce.PromedioFinal AS final_grade, ce.caprueba AS approval
                FROM UniqueMoodleIdentity AS email_registry
                INNER JOIN dbo.DATOS_ESTUD AS de
                  ON TRY_CONVERT(int, de.codigo_estud) = email_registry.student_code
                INNER JOIN dbo.CARRERAXESTUD AS ce
                  ON TRY_CONVERT(int, ce.codigo_estud) = email_registry.student_code
                INNER JOIN dbo.PENSUM AS pen
                  ON TRY_CONVERT(int, pen.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                 AND TRY_CONVERT(int, pen.codigo_materia) = TRY_CONVERT(int, ce.codigo_materia)
                INNER JOIN dbo.PERIODO AS per
                  ON TRY_CONVERT(int, per.cod_periodo) = TRY_CONVERT(int, ce.codigo_periodo)
                LEFT JOIN dbo.CARRERAS AS car
                  ON TRY_CONVERT(int, car.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                WHERE TRY_CONVERT(int, ce.codigo_periodo) = ?
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), de.Estado)))) IN (N'A', N'ACTIVO', N'ACTIVA')
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), per.TipoMatricula)))) IN (N'R', N'H')
                """,
                period_code,
            )
            rows = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        filtered = [row for row in rows if canonical_course_code(row["course_code"]) in course_codes]
        unique_rows: dict[int, dict[str, Any]] = {}
        for row in filtered:
            row_id = int(row.get("row_id") or 0)
            student_code = int(row.get("student_code") or 0)
            registry_student_code = int(row.get("registry_student_code") or 0)
            if row_id <= 0:
                raise MoodleGradeSyncError("Una matrícula coincidente no tiene un identificador único")
            if student_code <= 0 or registry_student_code != student_code:
                raise MoodleGradeSyncError(
                    "La identidad institucional no coincide con el código único del estudiante"
                )
            if row_id in unique_rows:
                raise MoodleGradeSyncError("La relación entre matrícula y pensum no es única")
            unique_rows[row_id] = row
        return sorted(unique_rows.values(), key=lambda item: (_normalized_text(item["student_name"]), item["row_id"]))

    def _grade_ledger(
        self,
        period_code: int,
        enrollments: list[dict[str, Any]],
    ) -> dict[tuple[Any, ...], Any]:
        student_codes = {str(item["student_code"]) for item in enrollments}
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT codigo_estudiante, periodo, codigo_materia, paralelo,
                       tipo_matricula, componente_nota, nota_obtenida
                FROM dbo.intec_estudiantenota
                WHERE periodo = ?
                """,
                str(period_code),
            )
            ledger: dict[tuple[Any, ...], Any] = {}
            for row in cursor.fetchall():
                item = _row_to_dict(cursor, row)
                if str(item["codigo_estudiante"]) not in student_codes:
                    continue
                key = (
                    str(item["codigo_estudiante"]),
                    str(item["periodo"]),
                    str(item["codigo_materia"]),
                    _text(item["paralelo"]).upper(),
                    _text(item["tipo_matricula"]).upper(),
                    _text(item["componente_nota"]),
                )
                ledger[key] = item["nota_obtenida"]
            return ledger

    def _acquire_lock(self, cursor: Any, course_id: int, period_code: int) -> None:
        cursor.execute(
            """
            DECLARE @result int;
            EXEC @result = sys.sp_getapplock
                @Resource = ?, @LockMode = N'Exclusive',
                @LockOwner = N'Transaction', @LockTimeout = ?;
            SELECT @result;
            """,
            f"INTEC_MOODLE_GRADES:{course_id}:{period_code}",
            int(self._settings.moodle_grade_sync_lock_timeout_ms),
        )
        result = int(cursor.fetchone()[0])
        if result < 0:
            raise MoodleGradeSyncError("Existe otra sincronización activa para el mismo curso y período")

    @staticmethod
    def _current_grade_row(cursor: Any, row_id: int) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT TRY_CONVERT(bigint, num) AS row_id,
                   P1Tareas, P1Proyectos, P1Examen,
                   P2Tareas, P2Proyectos, P2Examen,
                   P3Tareas, P3Proyectos, P3Examen,
                   teoriaHomo, practicahomo, Recuperacion,
                   PromedioFinal AS final_grade, caprueba AS approval
            FROM dbo.CARRERAXESTUD WITH (UPDLOCK, ROWLOCK)
            WHERE TRY_CONVERT(bigint, num) = ?
            """,
            row_id,
        )
        row = cursor.fetchone()
        return _row_to_dict(cursor, row) if row is not None else None

    def _current_ledger_value(self, cursor: Any, change: dict[str, Any]) -> Any:
        cursor.execute(
            """
            SELECT nota_obtenida
            FROM dbo.intec_estudiantenota WITH (UPDLOCK, HOLDLOCK)
            WHERE codigo_estudiante = ? AND periodo = ? AND codigo_materia = ?
              AND paralelo = ? AND tipo_matricula = ? AND componente_nota = ?
            """,
            str(change["student_code"]),
            str(change["period_code"]),
            str(change["matter_code"]),
            change["parallel"],
            change["type"],
            change["field"],
        )
        row = cursor.fetchone()
        return row[0] if row is not None else None

    @staticmethod
    def _upsert_ledger(cursor: Any, change: dict[str, Any], course_id: int, actor: str) -> None:
        percentage = MoodleGradeSyncService._component_percentage(change["field"])
        cursor.execute(
            """
            MERGE dbo.intec_estudiantenota WITH (HOLDLOCK) AS target
            USING (SELECT ? AS codigo_estudiante, ? AS periodo, ? AS codigo_materia,
                          ? AS paralelo, ? AS tipo_matricula, ? AS componente_nota) AS source
            ON target.codigo_estudiante = source.codigo_estudiante
               AND target.periodo = source.periodo
               AND target.codigo_materia = source.codigo_materia
               AND target.paralelo = source.paralelo
               AND target.tipo_matricula = source.tipo_matricula
               AND target.componente_nota = source.componente_nota
            WHEN MATCHED THEN UPDATE SET
                nota_obtenida = ?, nota_maxima = 10, porcentaje = ?, estado = N'SINCRONIZADA',
                moodle_course_id = ?, moodle_grade_item_id = ?, fecha_calificacion = SYSDATETIME(),
                fecha_sincronizacion = SYSDATETIME(), comentario_profesor = ?, calificado_por = ?
            WHEN NOT MATCHED THEN INSERT
                (codigo_estudiante, periodo, codigo_materia, paralelo, tipo_matricula,
                 componente_nota, nota_obtenida, nota_maxima, porcentaje, estado,
                 moodle_course_id, moodle_grade_item_id, fecha_calificacion,
                 fecha_sincronizacion, fecha_creacion, comentario_profesor, calificado_por)
            VALUES
                (source.codigo_estudiante, source.periodo, source.codigo_materia, source.paralelo,
                 source.tipo_matricula, source.componente_nota, ?, 10, ?, N'SINCRONIZADA',
                 ?, ?, SYSDATETIME(), SYSDATETIME(), SYSDATETIME(), ?, ?);
            """,
            str(change["student_code"]),
            str(change["period_code"]),
            str(change["matter_code"]),
            change["parallel"],
            change["type"],
            change["field"],
            change["incoming_grade"],
            percentage,
            course_id,
            change["moodle_grade_item_id"],
            change["moodle_grade_item"],
            f"MOODLE:{actor}"[:255],
            change["incoming_grade"],
            percentage,
            course_id,
            change["moodle_grade_item_id"],
            change["moodle_grade_item"],
            f"MOODLE:{actor}"[:255],
        )

    @staticmethod
    def _recalculate_row(
        cursor: Any,
        row: dict[str, Any],
        actor: str,
        *,
        enrollment_type: str,
    ) -> None:
        row_id = int(row["row_id"])
        if enrollment_type.upper() == "H":
            calculation = calculate_homologation_grade_with_recovery(
                _number(row.get("teoriaHomo")),
                _number(row.get("practicahomo")),
                _number(row.get("Recuperacion")),
            )
            final = calculation.final
            cursor.execute(
                """
                UPDATE dbo.CARRERAXESTUD
                SET Promedio = ?, PromedioAux = ?, PromedioFinal = ?, caprueba = ?, Usuario = ?
                WHERE TRY_CONVERT(bigint, num) = ?
                """,
                final,
                final,
                final,
                None if final is None else ("A" if final >= 7 else "R"),
                actor[:10],
                row_id,
            )
            return

        calculation = calculate_regular_grade_with_recovery(
            (
                (_number(row.get("P1Tareas")), _number(row.get("P1Proyectos")), _number(row.get("P1Examen"))),
                (_number(row.get("P2Tareas")), _number(row.get("P2Proyectos")), _number(row.get("P2Examen"))),
                (_number(row.get("P3Tareas")), _number(row.get("P3Proyectos")), _number(row.get("P3Examen"))),
            ),
            _number(row.get("Recuperacion")),
        )
        final = calculation.final
        cursor.execute(
            """
            UPDATE dbo.CARRERAXESTUD
            SET promP1 = ?, promP2 = ?, promP3 = ?,
                Promedio = ?, PromedioAux = ?, PromedioFinal = ?, caprueba = ?, Usuario = ?
            WHERE TRY_CONVERT(bigint, num) = ?
            """,
            calculation.partials[0],
            calculation.partials[1],
            calculation.partials[2],
            final,
            final,
            final,
            None if final is None else ("A" if final >= 7 else "R"),
            actor[:10],
            row_id,
        )

    @staticmethod
    def _insert_log(
        cursor: Any,
        *,
        started_at: datetime,
        finished_at: datetime,
        period_code: int,
        mode: str,
        status: str,
        processed: int,
        updated: int,
        errors: int,
        actor: str,
        statistics: dict[str, Any],
        actor_id: int | None = None,
    ) -> None:
        duration = max((finished_at - started_at).total_seconds(), 0)
        actor_key = actor.strip().lower()
        resolved_actor_id: int | None = None
        if actor_key:
            cursor.execute(
                """
                SELECT TOP (1) id
                FROM dbo.auth_user
                WHERE LOWER(LTRIM(RTRIM(COALESCE(username, '')))) = ?
                   OR LOWER(LTRIM(RTRIM(COALESCE(email, '')))) = ?
                ORDER BY
                    CASE
                        WHEN LOWER(LTRIM(RTRIM(COALESCE(username, '')))) = ? THEN 0
                        ELSE 1
                    END,
                    id
                """,
                actor_key,
                actor_key,
                actor_key,
            )
            actor_row = cursor.fetchone()
            if actor_row is not None:
                resolved_actor_id = int(actor_row[0])

        cursor.execute(
            """
            INSERT INTO dbo.intec_moodlegradesynclog
                (fecha_inicio, fecha_fin, duracion_segundos, periodo, modo_ejecucion,
                 estado, notas_procesadas, notas_actualizadas, notas_insertadas,
                 notas_error, mensaje, errores_detalle, estadisticas, usuario_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, ?)
            """,
            started_at.replace(tzinfo=None),
            finished_at.replace(tzinfo=None),
            duration,
            str(period_code),
            mode,
            status,
            processed,
            updated,
            errors,
            f"Sincronización Moodle completada: {updated} componente(s) actualizado(s)",
            json.dumps(statistics, ensure_ascii=False),
            resolved_actor_id,
        )


__all__ = [
    "MoodleGradeSyncError",
    "MoodleGradeSyncService",
    "canonical_course_code",
    "institutional_email_candidates",
    "match_course_users_by_institutional_email",
    "moodle_exam_targets",
    "normalize_institutional_email",
    "normalize_moodle_grade",
    "normalize_period_codes",
    "parse_configured_mappings",
    "practical_exam_targets",
]
