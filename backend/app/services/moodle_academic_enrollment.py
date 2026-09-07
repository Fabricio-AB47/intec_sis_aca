from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date
import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
import pyodbc

from app.integrations.moodle.exceptions import MoodleAcademicEnrollmentError
from app.routers import academic_enrollment as academic
from app.services.db import get_connection
from app.services.moodle_grade_sync import (
    _course_code_match_score,
    moodle_user_institutional_identity,
    normalize_institutional_email,
)
from app.services.moodle_read_service import MoodleReadService


_STUDENT_ROLE_SHORTNAMES = frozenset({"student"})
_TEACHER_ROLE_SHORTNAMES = frozenset({"editingteacher", "teacher"})
_PARALLEL_AT_END = re.compile(r"\s+-\s+([A-Z0-9]{1,4})\s*$", re.IGNORECASE)
_VALID_PERIOD_TYPES = frozenset({"R", "H", "E"})
_ACTIVE_STUDENT_STATES = frozenset({"A", "ACTIVO", "ACTIVA"})


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _identity_number(value: Any) -> str:
    return "".join(character for character in _clean(value) if character.isdigit())


def _role_shortnames(user: dict[str, Any]) -> set[str]:
    roles = {
        _clean(role).casefold()
        for role in (user.get("role_shortnames") or [])
        if _clean(role)
    }
    for role in user.get("roles") or []:
        if not isinstance(role, dict):
            continue
        shortname = _clean(role.get("shortname")).casefold()
        if shortname:
            roles.add(shortname)
        role_id = _integer(role.get("roleid") or role.get("id"))
        if role_id == 5:
            roles.add("student")
    return roles


def _is_moodle_student(user: dict[str, Any]) -> bool:
    return bool(_role_shortnames(user) & _STUDENT_ROLE_SHORTNAMES)


def _is_moodle_teacher(user: dict[str, Any]) -> bool:
    return bool(_role_shortnames(user) & _TEACHER_ROLE_SHORTNAMES)


def extract_parallel_from_course_name(course: dict[str, Any]) -> str:
    """Read a 1-4 character parallel from the final dash-delimited name segment."""
    for field in ("displayname", "fullname"):
        match = _PARALLEL_AT_END.search(_clean(course.get(field)).upper())
        if match:
            return match.group(1).upper()
    return ""


def _period_type(value: Any) -> str:
    normalized = _clean(value).upper()
    if normalized.startswith("H"):
        return "H"
    if normalized.startswith("E"):
        return "E"
    if normalized.startswith("R"):
        return "R"
    return ""


def _fetch_dicts(cursor: pyodbc.Cursor, statement: str, *params: Any) -> list[dict[str, Any]]:
    cursor.execute(statement, *params)
    columns = [str(column[0]).casefold() for column in (cursor.description or [])]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _serialize_date(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else _clean(value)


class MoodleAcademicEnrollmentService:
    def __init__(
        self,
        moodle: MoodleReadService,
        connection_factory: Callable[[], pyodbc.Connection] = get_connection,
    ) -> None:
        self._moodle = moodle
        self._connection_factory = connection_factory

    async def catalog(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._catalog_sync)

    async def preview(
        self,
        *,
        course_ids: Sequence[int],
        period_code: int,
        jornada_code: int,
        career_by_course: dict[int, int],
        refresh: bool = False,
    ) -> dict[str, Any]:
        snapshot = await self._moodle_snapshot(course_ids, refresh=refresh)
        return await asyncio.to_thread(
            self._preview_sync,
            snapshot,
            period_code,
            jornada_code,
            career_by_course,
        )

    async def apply(
        self,
        *,
        course_ids: Sequence[int],
        period_code: int,
        jornada_code: int,
        career_by_course: dict[int, int],
        principal_teacher_by_course: dict[int, int],
        preview_fingerprint: str,
        actor: str,
    ) -> dict[str, Any]:
        snapshot = await self._moodle_snapshot(course_ids, refresh=True)
        return await asyncio.to_thread(
            self._apply_sync,
            snapshot,
            period_code,
            jornada_code,
            career_by_course,
            principal_teacher_by_course,
            preview_fingerprint,
            actor,
        )

    def _catalog_sync(self) -> dict[str, Any]:
        with self._connection_factory() as connection:
            cursor = connection.cursor()
            periods = _fetch_dicts(
                cursor,
                """
                SELECT TOP (120)
                    TRY_CONVERT(int, cod_periodo) AS code,
                    TRY_CONVERT(nvarchar(255), Detalle_Periodo) AS name,
                    TRY_CONVERT(nvarchar(10), Estado) AS state,
                    TRY_CONVERT(nvarchar(50), TipoMatricula) AS enrollment_type,
                    fechain AS starts_at,
                    fechafin AS ends_at,
                    TRY_CONVERT(int, anio) AS year
                FROM dbo.PERIODO
                WHERE TRY_CONVERT(int, cod_periodo) IS NOT NULL
                ORDER BY
                    CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(Estado, N'')))) = N'A' THEN 0 ELSE 1 END,
                    COALESCE(fechain, CAST('19000101' AS date)) DESC,
                    TRY_CONVERT(int, cod_periodo) DESC
                """,
            )
            jornadas = _fetch_dicts(
                cursor,
                """
                SELECT
                    TRY_CONVERT(int, NumJ) AS code,
                    TRY_CONVERT(nvarchar(100), DetalleJ) AS name
                FROM dbo.JORNADA
                WHERE TRY_CONVERT(int, NumJ) IS NOT NULL
                ORDER BY TRY_CONVERT(nvarchar(100), DetalleJ)
                """,
            )
        return {
            "periods": [
                {
                    "code": int(item["code"]),
                    "name": _clean(item.get("name")),
                    "state": _clean(item.get("state")).upper(),
                    "enrollment_type": _period_type(item.get("enrollment_type")),
                    "starts_at": _serialize_date(item.get("starts_at")),
                    "ends_at": _serialize_date(item.get("ends_at")),
                    "year": _integer(item.get("year")),
                }
                for item in periods
                if _period_type(item.get("enrollment_type")) in _VALID_PERIOD_TYPES
            ],
            "jornadas": [
                {"code": int(item["code"]), "name": _clean(item.get("name"))}
                for item in jornadas
            ],
            "rules": {
                "max_courses": 25,
                "parallel_source": "Último segmento del nombre completo, después de ' - '",
                "student_roles": sorted(_STUDENT_ROLE_SHORTNAMES),
                "teacher_roles": sorted(_TEACHER_ROLE_SHORTNAMES),
            },
        }

    async def _moodle_snapshot(
        self,
        course_ids: Sequence[int],
        *,
        refresh: bool,
    ) -> list[dict[str, Any]]:
        normalized_ids = list(dict.fromkeys(int(course_id) for course_id in course_ids))
        courses = await self._moodle.get_all_courses(refresh=refresh)
        courses_by_id = {int(course.get("id") or 0): course for course in courses}
        missing = [course_id for course_id in normalized_ids if course_id not in courses_by_id]
        if missing:
            raise MoodleAcademicEnrollmentError(
                "No se encontraron los cursos Moodle: " + ", ".join(map(str, missing))
            )

        semaphore = asyncio.Semaphore(6)

        async def load_users(course_id: int) -> list[dict[str, Any]]:
            async with semaphore:
                return await self._moodle.get_course_enrolled_users(
                    course_id,
                    refresh=refresh,
                )

        enrolled_users = await asyncio.gather(*(load_users(course_id) for course_id in normalized_ids))
        return [
            {
                "course": dict(courses_by_id[course_id]),
                "users": users,
            }
            for course_id, users in zip(normalized_ids, enrolled_users, strict=True)
        ]

    def _preview_sync(
        self,
        snapshot: list[dict[str, Any]],
        period_code: int,
        jornada_code: int,
        career_by_course: dict[int, int],
    ) -> dict[str, Any]:
        with self._connection_factory() as connection:
            return self._build_preview(
                connection.cursor(),
                snapshot,
                period_code,
                jornada_code,
                career_by_course,
            )

    def _build_preview(
        self,
        cursor: pyodbc.Cursor,
        snapshot: list[dict[str, Any]],
        period_code: int,
        jornada_code: int,
        career_by_course: dict[int, int],
    ) -> dict[str, Any]:
        period = self._load_period(cursor, period_code)
        jornada = self._load_jornada(cursor, jornada_code)
        valid_parallels = self._load_parallels(cursor)
        subjects = self._load_subjects(cursor)
        students_by_email, students_by_identity = self._load_student_registry(cursor)
        teachers_by_email, teachers_by_identity = self._load_teacher_registry(cursor)

        preliminary_matches: dict[tuple[int, int], dict[str, Any]] = {}
        for entry in snapshot:
            course_id = int(entry["course"].get("id") or 0)
            for user in entry["users"]:
                if not _is_moodle_student(user):
                    continue
                matched = self._match_person(
                    user,
                    students_by_email,
                    students_by_identity,
                    person_kind="estudiante",
                )
                preliminary_matches[(course_id, int(user.get("id") or 0))] = matched

        course_previews = [
            self._build_course_preview(
                cursor,
                entry,
                period,
                jornada,
                valid_parallels,
                subjects,
                preliminary_matches,
                teachers_by_email,
                teachers_by_identity,
                _integer(career_by_course.get(int(entry["course"].get("id") or 0))),
            )
            for entry in snapshot
        ]
        self._mark_duplicate_targets(course_previews)
        summary = {
            "selected_courses": len(course_previews),
            "ready_courses": sum(1 for item in course_previews if item["ready"]),
            "blocked_courses": sum(1 for item in course_previews if not item["ready"]),
            "moodle_students": sum(item["summary"]["moodle_students"] for item in course_previews),
            "ready_students": sum(item["summary"]["ready_students"] for item in course_previews),
            "existing_students": sum(item["summary"]["existing_students"] for item in course_previews),
            "blocked_students": sum(item["summary"]["blocked_students"] for item in course_previews),
            "ignored_users": sum(item["summary"]["ignored_users"] for item in course_previews),
            "matched_teachers": sum(item["summary"]["matched_teachers"] for item in course_previews),
            "first_enrollments": sum(item["summary"]["first_enrollments"] for item in course_previews),
            "second_enrollments": sum(item["summary"]["second_enrollments"] for item in course_previews),
            "third_enrollments": sum(item["summary"]["third_enrollments"] for item in course_previews),
        }
        response = {
            "period": period,
            "jornada": jornada,
            "courses": course_previews,
            "summary": summary,
            "can_apply": bool(course_previews) and summary["blocked_courses"] == 0,
        }
        response["fingerprint"] = self._preview_fingerprint(response)
        return response

    @staticmethod
    def _load_period(cursor: pyodbc.Cursor, period_code: int) -> dict[str, Any]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT TOP (1)
                TRY_CONVERT(int, cod_periodo) AS code,
                TRY_CONVERT(nvarchar(255), Detalle_Periodo) AS name,
                TRY_CONVERT(nvarchar(10), Estado) AS state,
                TRY_CONVERT(nvarchar(50), TipoMatricula) AS enrollment_type,
                fechain AS starts_at,
                fechafin AS ends_at
            FROM dbo.PERIODO
            WHERE TRY_CONVERT(int, cod_periodo) = ?
            """,
            period_code,
        )
        if not rows:
            raise MoodleAcademicEnrollmentError("El período académico seleccionado no existe")
        row = rows[0]
        enrollment_type = _period_type(row.get("enrollment_type"))
        if enrollment_type not in _VALID_PERIOD_TYPES:
            raise MoodleAcademicEnrollmentError("El período no tiene un tipo de matrícula válido")
        return {
            "code": int(row["code"]),
            "name": _clean(row.get("name")),
            "state": _clean(row.get("state")).upper(),
            "enrollment_type": enrollment_type,
            "starts_at": _serialize_date(row.get("starts_at")),
            "ends_at": _serialize_date(row.get("ends_at")),
        }

    @staticmethod
    def _load_jornada(cursor: pyodbc.Cursor, jornada_code: int) -> dict[str, Any]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT TOP (1) TRY_CONVERT(int, NumJ) AS code, TRY_CONVERT(nvarchar(100), DetalleJ) AS name
            FROM dbo.JORNADA
            WHERE TRY_CONVERT(int, NumJ) = ?
            """,
            jornada_code,
        )
        if not rows:
            raise MoodleAcademicEnrollmentError("La jornada seleccionada no existe")
        return {"code": int(rows[0]["code"]), "name": _clean(rows[0].get("name"))}

    @staticmethod
    def _load_parallels(cursor: pyodbc.Cursor) -> set[str]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT DISTINCT UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), paralelo)))) AS code
            FROM dbo.PARALELOS
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), paralelo))), N'') IS NOT NULL
            """,
        )
        return {_clean(item.get("code")).upper() for item in rows if _clean(item.get("code"))}

    @staticmethod
    def _load_subjects(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT
                TRY_CONVERT(int, p.Cod_AnioBasica) AS career_code,
                TRY_CONVERT(int, p.codigo_materia) AS subject_id,
                TRY_CONVERT(nvarchar(100), p.cod_materia) AS subject_code,
                TRY_CONVERT(nvarchar(255), p.Nomb_Materia) AS subject_name,
                TRY_CONVERT(int, p.Semestre) AS level,
                TRY_CONVERT(decimal(18, 2), p.Creditos) AS credits,
                TRY_CONVERT(nvarchar(255), c.Nombre_Basica) AS career_name
            FROM dbo.PENSUM p
            INNER JOIN dbo.CARRERAS c
              ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, p.Cod_AnioBasica)
            WHERE TRY_CONVERT(int, p.Cod_AnioBasica) IS NOT NULL
              AND TRY_CONVERT(int, p.codigo_materia) IS NOT NULL
              AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N'') IS NOT NULL
            """,
        )
        return [
            {
                "career_code": int(item["career_code"]),
                "career_name": _clean(item.get("career_name")),
                "subject_id": int(item["subject_id"]),
                "subject_code": _clean(item.get("subject_code")).upper(),
                "subject_name": _clean(item.get("subject_name")),
                "level": _integer(item.get("level")),
                "credits": float(item.get("credits") or 0),
            }
            for item in rows
        ]

    @staticmethod
    def _load_student_registry(
        cursor: pyodbc.Cursor,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT
                TRY_CONVERT(int, d.codigo_estud) AS code,
                TRY_CONVERT(nvarchar(255), d.Apellidos_nombre) AS name,
                TRY_CONVERT(nvarchar(50), d.Cedula_Est) AS identity_number,
                TRY_CONVERT(nvarchar(20), d.Estado) AS state,
                TRY_CONVERT(nvarchar(254), ce.CorreoIntec) AS registry_email,
                TRY_CONVERT(nvarchar(254), d.correointec) AS student_email
            FROM dbo.DATOS_ESTUD d
            LEFT JOIN dbo.CorreosEstudIntec ce
              ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, d.codigo_estud)
            WHERE TRY_CONVERT(int, d.codigo_estud) IS NOT NULL
            """,
        )
        return MoodleAcademicEnrollmentService._index_registry(
            rows,
            email_fields=("registry_email", "student_email"),
        )

    @staticmethod
    def _load_teacher_registry(
        cursor: pyodbc.Cursor,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        rows = _fetch_dicts(
            cursor,
            """
            SELECT
                TRY_CONVERT(int, d.codigo_doc) AS code,
                TRY_CONVERT(nvarchar(255), d.apellidos_nombre) AS name,
                TRY_CONVERT(nvarchar(50), d.cedula_doc) AS identity_number,
                TRY_CONVERT(nvarchar(254), d.correo) AS institutional_email,
                TRY_CONVERT(nvarchar(254), d.correop) AS personal_email,
                TRY_CONVERT(nvarchar(254), u.login) AS user_email,
                TRY_CONVERT(nvarchar(20), u.Estado) AS state,
                TRY_CONVERT(nvarchar(254), u.login) AS login
            FROM dbo.DATOSDOCENTE d
            LEFT JOIN dbo.USUARIOS u
              ON TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
            WHERE TRY_CONVERT(int, d.codigo_doc) IS NOT NULL
            """,
        )
        return MoodleAcademicEnrollmentService._index_registry(
            rows,
            email_fields=("institutional_email", "personal_email", "user_email"),
        )

    @staticmethod
    def _index_registry(
        rows: list[dict[str, Any]],
        *,
        email_fields: Sequence[str],
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        by_email: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
        by_identity: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
        for row in rows:
            code = _integer(row.get("code"))
            if code is None:
                continue
            record = dict(row)
            record["code"] = code
            for field in email_fields:
                email = normalize_institutional_email(record.get(field))
                if email:
                    by_email[email][code] = record
            identity = _identity_number(record.get("identity_number"))
            if identity:
                by_identity[identity][code] = record
        return (
            {key: list(values.values()) for key, values in by_email.items()},
            {key: list(values.values()) for key, values in by_identity.items()},
        )

    @staticmethod
    def _match_person(
        user: dict[str, Any],
        by_email: dict[str, list[dict[str, Any]]],
        by_identity: dict[str, list[dict[str, Any]]],
        *,
        person_kind: str,
    ) -> dict[str, Any]:
        email, email_source, email_status = moodle_user_institutional_identity(user)
        if email_status == "conflicting_email_username":
            return {
                "status": "IDENTIDAD_CONFLICTIVA",
                "message": "El correo y el usuario institucional de Moodle no coinciden",
                "record": {},
                "source": "",
            }
        email_matches = by_email.get(email, []) if email else []
        inactive_student_match = False
        if person_kind == "estudiante":
            inactive_student_match = bool(email_matches)
            email_matches = [
                record
                for record in email_matches
                if _clean(record.get("state")).upper() in _ACTIVE_STUDENT_STATES
            ]
        if len(email_matches) > 1:
            return {
                "status": "CORREO_AMBIGUO",
                "message": f"El correo institucional pertenece a más de un {person_kind}",
                "record": {},
                "source": email_source,
            }
        if len(email_matches) == 1:
            return {
                "status": "COINCIDE",
                "message": "Coincidencia exacta por correo institucional",
                "record": email_matches[0],
                "source": email_source,
            }

        identity = _identity_number(user.get("idnumber"))
        identity_matches = by_identity.get(identity, []) if identity else []
        if person_kind == "estudiante":
            inactive_student_match = inactive_student_match or bool(identity_matches)
            identity_matches = [
                record
                for record in identity_matches
                if _clean(record.get("state")).upper() in _ACTIVE_STUDENT_STATES
            ]
        if len(identity_matches) > 1:
            return {
                "status": "CEDULA_AMBIGUA",
                "message": f"La identificación pertenece a más de un {person_kind}",
                "record": {},
                "source": "Moodle.idnumber",
            }
        if len(identity_matches) == 1:
            return {
                "status": "COINCIDE",
                "message": "Coincidencia exacta por identificación",
                "record": identity_matches[0],
                "source": "Moodle.idnumber",
            }
        if person_kind == "estudiante" and inactive_student_match:
            return {
                "status": "IGNORADO_ACADEMICO",
                "message": "El estudiante no tiene un registro activo en INTECBDD",
                "record": {},
                "source": email_source or "Moodle.idnumber",
            }
        return {
            "status": "NO_ENCONTRADO",
            "message": f"No se encontró el {person_kind} por correo institucional ni identificación",
            "record": {},
            "source": email_source,
        }

    @staticmethod
    def _resolve_course_subjects(
        course: dict[str, Any],
        subjects: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], str]:
        scored = [
            (_course_code_match_score(course, subject["subject_code"]), subject)
            for subject in subjects
        ]
        best_score = max((score for score, _subject in scored), default=0)
        if best_score <= 0:
            return "", [], "El código Moodle no contiene un código de materia válido de PENSUM"
        best_rows = [subject for score, subject in scored if score == best_score]
        best_codes = {subject["subject_code"] for subject in best_rows}
        if len(best_codes) != 1:
            return "", [], "El código Moodle coincide con más de un código de materia"
        subject_code = next(iter(best_codes))
        candidates = sorted(
            (subject for subject in subjects if subject["subject_code"] == subject_code),
            key=lambda item: (
                _clean(item.get("career_name")).casefold(),
                int(item["career_code"]),
                int(item["subject_id"]),
            ),
        )
        return subject_code, candidates, ""

    @staticmethod
    def _select_course_subject(
        candidates: list[dict[str, Any]],
        requested_career_code: int | None,
    ) -> tuple[dict[str, Any] | None, str]:
        unique_candidates = {
            (int(item["career_code"]), int(item["subject_id"])): item
            for item in candidates
        }
        normalized_candidates = list(unique_candidates.values())
        if not normalized_candidates:
            return None, "No existe una materia compatible en PENSUM"

        if requested_career_code is not None:
            selected = [
                item
                for item in normalized_candidates
                if int(item["career_code"]) == requested_career_code
            ]
            if len(selected) == 1:
                return selected[0], ""
            if not selected:
                return None, "La carrera seleccionada no contiene el código único de esta materia"
            return None, "La carrera seleccionada contiene más de una materia para el mismo código único"

        careers = {int(item["career_code"]) for item in normalized_candidates}
        if len(careers) > 1:
            return None, "Seleccione la carrera académica correspondiente al curso Moodle"
        if len(normalized_candidates) > 1:
            return None, "El código único corresponde a más de una materia dentro de la misma carrera"
        return normalized_candidates[0], ""

    def _build_course_preview(
        self,
        cursor: pyodbc.Cursor,
        entry: dict[str, Any],
        period: dict[str, Any],
        jornada: dict[str, Any],
        valid_parallels: set[str],
        subjects: list[dict[str, Any]],
        preliminary_matches: dict[tuple[int, int], dict[str, Any]],
        teachers_by_email: dict[str, list[dict[str, Any]]],
        teachers_by_identity: dict[str, list[dict[str, Any]]],
        requested_career_code: int | None,
    ) -> dict[str, Any]:
        course = entry["course"]
        course_id = int(course.get("id") or 0)
        course_name = _clean(course.get("displayname") or course.get("fullname"))
        parallel = extract_parallel_from_course_name(course)
        course_code, subject_candidates, subject_error = self._resolve_course_subjects(course, subjects)
        selected_subject: dict[str, Any] | None = None
        selection_error = ""
        if subject_candidates:
            selected_subject, selection_error = self._select_course_subject(
                subject_candidates,
                requested_career_code,
            )
        errors: list[str] = []
        warnings: list[str] = []
        if not parallel:
            errors.append("No se pudo extraer el paralelo del final del nombre del curso")
        elif parallel not in valid_parallels:
            errors.append(f"El paralelo {parallel} no existe en el catálogo académico")
        if subject_error:
            errors.append(subject_error)
        if selection_error:
            errors.append(selection_error)

        teacher_items: list[dict[str, Any]] = []
        for user in entry["users"]:
            if not _is_moodle_teacher(user):
                continue
            item = self._person_preview_item(
                user,
                self._match_person(
                    user,
                    teachers_by_email,
                    teachers_by_identity,
                    person_kind="docente",
                ),
            )
            record = item.pop("_record")
            if bool(user.get("suspended")) or not bool(user.get("confirmed", True)):
                item["status"] = "INACTIVO_MOODLE"
                item["message"] = "La cuenta docente está inactiva o no confirmada en Moodle"
            elif record:
                state = _clean(record.get("state")).upper()
                login = _clean(record.get("login"))
                if state != "A" or not login:
                    item["status"] = "INACTIVO_ACADEMICO"
                    item["message"] = "El docente no tiene un usuario académico activo"
            teacher_items.append(item)

        if not teacher_items:
            errors.append("El curso no tiene docentes con rol teacher o editingteacher")
        invalid_teachers = [item for item in teacher_items if item["status"] != "COINCIDE"]
        if invalid_teachers:
            errors.append("Existen docentes sin una identidad académica única y activa")

        student_items: list[dict[str, Any]] = []
        ignored_users = 0
        for user in entry["users"]:
            if not _is_moodle_student(user):
                continue
            if bool(user.get("suspended")) or not bool(user.get("confirmed", True)):
                ignored_users += 1
                item = self._person_preview_item(
                    user,
                    preliminary_matches.get((course_id, int(user.get("id") or 0)), {}),
                )
                item.pop("_record")
                item["status"] = "IGNORADO_MOODLE"
                item["message"] = "La cuenta está inactiva o no confirmada en Moodle"
                student_items.append(item)
                continue

            match = preliminary_matches.get((course_id, int(user.get("id") or 0)), {})
            item = self._person_preview_item(user, match)
            record = item.pop("_record")
            if item["status"] == "IGNORADO_ACADEMICO":
                ignored_users += 1
                student_items.append(item)
                continue
            if item["status"] != "COINCIDE" or not record:
                student_items.append(item)
                continue
            if _clean(record.get("state")).upper() not in _ACTIVE_STUDENT_STATES:
                ignored_users += 1
                item["status"] = "IGNORADO_ACADEMICO"
                item["message"] = "El estudiante no tiene un registro activo en INTECBDD"
                student_items.append(item)
                continue
            if not subject_candidates:
                item["status"] = "MATERIA_NO_ENCONTRADA"
                item["message"] = subject_error
                student_items.append(item)
                continue

            student_code = int(record["code"])
            if selected_subject is None:
                item["status"] = (
                    "CARRERA_REQUERIDA"
                    if requested_career_code is None
                    and len({int(candidate["career_code"]) for candidate in subject_candidates}) > 1
                    else "MATERIA_AMBIGUA"
                )
                item["message"] = selection_error
                student_items.append(item)
                continue
            item.update(
                {
                    "student_code": student_code,
                    "academic_name": _clean(record.get("name")),
                    "career_code": int(selected_subject["career_code"]),
                    "career_name": selected_subject["career_name"],
                    "subject_id": int(selected_subject["subject_id"]),
                    "subject_code": selected_subject["subject_code"],
                    "subject_name": selected_subject["subject_name"],
                }
            )
            if parallel and parallel in valid_parallels:
                self._validate_academic_enrollment(
                    cursor,
                    item,
                    period,
                    jornada,
                    parallel,
                )
            else:
                item["status"] = "PARALELO_INVALIDO"
                item["message"] = "El paralelo del curso debe existir en el catálogo académico"
            student_items.append(item)

        ignored_statuses = {"IGNORADO_MOODLE", "IGNORADO_ACADEMICO"}
        active_students = [item for item in student_items if item["status"] not in ignored_statuses]
        blocked_students = [
            item for item in active_students if item["status"] not in {"LISTO", "EXISTENTE"}
        ]
        if not active_students:
            errors.append("El curso no tiene estudiantes activos con rol student")
        if blocked_students:
            warnings.append(
                f"{len(blocked_students)} estudiante(s) no superan la validación y serán omitidos"
            )

        contexts: dict[tuple[int, int], dict[str, Any]] = {}
        for item in student_items:
            if item["status"] not in {"LISTO", "EXISTENTE"}:
                continue
            key = (int(item["career_code"]), int(item["subject_id"]))
            context = contexts.setdefault(
                key,
                {
                    "career_code": key[0],
                    "career_name": item["career_name"],
                    "subject_id": key[1],
                    "subject_code": item["subject_code"],
                    "subject_name": item["subject_name"],
                    "students": 0,
                },
            )
            context["students"] += 1

        matched_teachers = [item for item in teacher_items if item["status"] == "COINCIDE"]
        ready = not errors and bool(contexts)
        return {
            "course": {
                "id": course_id,
                "name": course_name,
                "shortname": _clean(course.get("shortname")),
                "idnumber": _clean(course.get("idnumber")),
                "category": _clean(course.get("categoryname")),
                "timemodified": int(course.get("timemodified") or 0),
            },
            "parallel": parallel,
            "course_code": course_code,
            "subject_candidates": subject_candidates,
            "selected_career_code": (
                int(selected_subject["career_code"])
                if selected_subject is not None
                else None
            ),
            "selected_career_name": (
                _clean(selected_subject.get("career_name"))
                if selected_subject is not None
                else ""
            ),
            "selected_subject_id": (
                int(selected_subject["subject_id"])
                if selected_subject is not None
                else None
            ),
            "academic_contexts": sorted(
                contexts.values(),
                key=lambda item: (item["career_name"], item["subject_name"]),
            ),
            "teachers": teacher_items,
            "students": student_items,
            "suggested_principal_teacher_code": (
                int(matched_teachers[0]["academic_code"])
                if len(matched_teachers) == 1
                else None
            ),
            "requires_principal_teacher": len(matched_teachers) > 1,
            "errors": list(dict.fromkeys(errors)),
            "warnings": warnings,
            "ready": ready,
            "summary": {
                "moodle_students": len(student_items),
                "ready_students": sum(1 for item in student_items if item["status"] == "LISTO"),
                "existing_students": sum(1 for item in student_items if item["status"] == "EXISTENTE"),
                "blocked_students": len(blocked_students),
                "ignored_users": ignored_users,
                "moodle_teachers": len(teacher_items),
                "matched_teachers": len(matched_teachers),
                "first_enrollments": sum(
                    1
                    for item in student_items
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 1
                ),
                "second_enrollments": sum(
                    1
                    for item in student_items
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 2
                ),
                "third_enrollments": sum(
                    1
                    for item in student_items
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 3
                ),
            },
        }

    @staticmethod
    def _mark_duplicate_targets(course_previews: list[dict[str, Any]]) -> None:
        targets: dict[tuple[int, int, int], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for course in course_previews:
            for student in course["students"]:
                if student["status"] not in {"LISTO", "EXISTENTE"}:
                    continue
                key = (
                    int(student["student_code"]),
                    int(student["career_code"]),
                    int(student["subject_id"]),
                )
                targets[key].append((course, student))

        affected_courses: dict[int, dict[str, Any]] = {}
        for matches in targets.values():
            if len(matches) < 2:
                continue
            course_names = sorted({course["course"]["name"] for course, _student in matches})
            message = (
                "El estudiante aparece más de una vez para la misma carrera, materia y período "
                f"en la selección: {', '.join(course_names)}"
            )
            for course, student in matches:
                student["status"] = "DUPLICADO_SELECCION"
                student["message"] = message
                affected_courses[int(course["course"]["id"])] = course

        for course in affected_courses.values():
            MoodleAcademicEnrollmentService._refresh_course_student_state(course)

    @staticmethod
    def _refresh_course_student_state(course: dict[str, Any]) -> None:
        students = course["students"]
        ignored_statuses = {"IGNORADO_MOODLE", "IGNORADO_ACADEMICO"}
        active_students = [item for item in students if item["status"] not in ignored_statuses]
        blocked_students = [
            item for item in active_students if item["status"] not in {"LISTO", "EXISTENTE"}
        ]
        warnings = [
            warning
            for warning in course["warnings"]
            if "no superan la validación" not in warning
        ]
        if blocked_students:
            warnings.append(
                f"{len(blocked_students)} estudiante(s) no superan la validación y serán omitidos"
            )
        course["warnings"] = warnings

        contexts: dict[tuple[int, int], dict[str, Any]] = {}
        for item in students:
            if item["status"] not in {"LISTO", "EXISTENTE"}:
                continue
            key = (int(item["career_code"]), int(item["subject_id"]))
            context = contexts.setdefault(
                key,
                {
                    "career_code": key[0],
                    "career_name": item["career_name"],
                    "subject_id": key[1],
                    "subject_code": item["subject_code"],
                    "subject_name": item["subject_name"],
                    "students": 0,
                },
            )
            context["students"] += 1
        course["academic_contexts"] = sorted(
            contexts.values(),
            key=lambda item: (item["career_name"], item["subject_name"]),
        )
        course["summary"].update(
            {
                "ready_students": sum(1 for item in students if item["status"] == "LISTO"),
                "existing_students": sum(1 for item in students if item["status"] == "EXISTENTE"),
                "blocked_students": len(blocked_students),
                "first_enrollments": sum(
                    1
                    for item in students
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 1
                ),
                "second_enrollments": sum(
                    1
                    for item in students
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 2
                ),
                "third_enrollments": sum(
                    1
                    for item in students
                    if item["status"] == "LISTO" and item.get("enrollment_number") == 3
                ),
            }
        )
        course["ready"] = not course["errors"] and bool(contexts)

    @staticmethod
    def _person_preview_item(user: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
        record = match.get("record") if isinstance(match.get("record"), dict) else {}
        return {
            "moodle_user_id": int(user.get("id") or 0),
            "moodle_name": _clean(user.get("fullname") or f"{user.get('firstname', '')} {user.get('lastname', '')}"),
            "moodle_email": _clean(user.get("email")),
            "moodle_idnumber": _clean(user.get("idnumber")),
            "roles": sorted(_role_shortnames(user)),
            "academic_code": _integer(record.get("code")),
            "academic_name": _clean(record.get("name")),
            "match_source": _clean(match.get("source")),
            "status": _clean(match.get("status")) or "NO_ENCONTRADO",
            "message": _clean(match.get("message")) or "No se pudo validar la identidad",
            "_record": record,
        }

    @staticmethod
    def _validate_academic_enrollment(
        cursor: pyodbc.Cursor,
        item: dict[str, Any],
        period: dict[str, Any],
        jornada: dict[str, Any],
        parallel: str,
    ) -> None:
        payload = academic.AcademicEnrollmentPayload(
            codigo_estud=int(item["student_code"]),
            cod_anio_basica=int(item["career_code"]),
            codigo_periodo=int(period["code"]),
            materia_codes=[int(item["subject_id"])],
            paralelo=parallel,
            num_grupo=1,
            tipo_matricula=str(period["enrollment_type"]),
            control_matricula=1,
            cod_jornada=int(jornada["code"]),
        )
        try:
            academic_preview = academic._preview_with_cursor(cursor, payload)
        except HTTPException as exc:
            item["status"] = "BLOQUEADO_ACADEMICO"
            item["message"] = _clean(exc.detail)
            return
        summary = academic_preview.get("summary", {})
        if int(summary.get("bloqueadas_por_prerrequisito", 0) or 0) > 0:
            item["status"] = "PRERREQUISITO_PENDIENTE"
            item["message"] = "La materia está bloqueada por prerrequisitos pendientes"
            return
        action = next(
            (
                row.get("accion")
                for row in academic_preview.get("items", [])
                if int(row.get("codigo_materia") or 0) == int(item["subject_id"])
            ),
            "",
        )
        if action == "EXISTENTE":
            existing_parallels = _fetch_dicts(
                cursor,
                """
                SELECT
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), paralelo)))) AS code,
                    MAX(COALESCE(TRY_CONVERT(int, Num_Matricula), 1)) AS enrollment_number
                FROM dbo.CARRERAXESTUD
                WHERE TRY_CONVERT(int, codigo_estud) = ?
                  AND TRY_CONVERT(int, cod_anio_Basica) = ?
                  AND TRY_CONVERT(int, codigo_materia) = ?
                  AND TRY_CONVERT(int, codigo_periodo) = ?
                GROUP BY UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), paralelo))))
                """,
                int(item["student_code"]),
                int(item["career_code"]),
                int(item["subject_id"]),
                int(period["code"]),
            )
            registered_parallels = {
                _clean(row.get("code")).upper() for row in existing_parallels
            }
            item["enrollment_number"] = max(
                (_integer(row.get("enrollment_number")) or 1 for row in existing_parallels),
                default=1,
            )
            if parallel not in registered_parallels:
                item["status"] = "PARALELO_CONFLICTIVO"
                item["message"] = (
                    "La materia ya está matriculada en otro paralelo: "
                    + ", ".join(sorted(registered_parallels))
                )
                return
            item["status"] = "EXISTENTE"
            item["message"] = "El estudiante ya está matriculado en esta materia y período"
            return
        next_enrollment = academic._next_subject_matricula(
            cursor,
            int(item["student_code"]),
            int(item["career_code"]),
            int(item["subject_id"]),
        )
        item["enrollment_number"] = next_enrollment
        if next_enrollment > 3:
            item["status"] = "LIMITE_MATRICULA"
            item["message"] = "La materia supera el tercer número de matrícula permitido"
            return
        if action not in {"INSERTAR", "EXCEPCION_PRERREQUISITO"}:
            item["status"] = "BLOQUEADO_ACADEMICO"
            item["message"] = "La matrícula no tiene una acción académica válida"
            return
        item["status"] = "LISTO"
        enrollment_label = {
            1: "primera matrícula",
            2: "segunda matrícula",
            3: "tercera matrícula",
        }.get(next_enrollment, f"matrícula {next_enrollment}")
        item["message"] = f"Listo para {enrollment_label} académica"

    @staticmethod
    def _preview_fingerprint(preview: dict[str, Any]) -> str:
        signature = {
            "period": preview["period"]["code"],
            "jornada": preview["jornada"]["code"],
            "courses": [
                {
                    "id": course["course"]["id"],
                    "modified": course["course"]["timemodified"],
                    "parallel": course["parallel"],
                    "code": course["course_code"],
                    "career": course["selected_career_code"],
                    "subject": course["selected_subject_id"],
                    "teachers": sorted(
                        (
                            item["moodle_user_id"],
                            item.get("academic_code"),
                            item["status"],
                        )
                        for item in course["teachers"]
                    ),
                    "students": sorted(
                        (
                            item["moodle_user_id"],
                            item.get("student_code"),
                            item.get("career_code"),
                            item.get("subject_id"),
                            item.get("enrollment_number"),
                            item["status"],
                        )
                        for item in course["students"]
                    ),
                }
                for course in preview["courses"]
            ],
        }
        encoded = json.dumps(signature, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _apply_sync(
        self,
        snapshot: list[dict[str, Any]],
        period_code: int,
        jornada_code: int,
        career_by_course: dict[int, int],
        principal_teacher_by_course: dict[int, int],
        preview_fingerprint: str,
        actor: str,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            preview = self._build_preview(
                cursor,
                snapshot,
                period_code,
                jornada_code,
                career_by_course,
            )
            if preview["fingerprint"] != preview_fingerprint:
                raise MoodleAcademicEnrollmentError(
                    "La información de Moodle o del sistema académico cambió; genere una nueva vista previa"
                )
            if not preview["can_apply"]:
                raise MoodleAcademicEnrollmentError(
                    "La matrícula masiva tiene cursos, docentes o estudiantes pendientes de corrección"
                )

            resolved_principals: dict[int, int] = {}
            for course in preview["courses"]:
                course_id = int(course["course"]["id"])
                teacher_codes = {
                    int(item["academic_code"])
                    for item in course["teachers"]
                    if item["status"] == "COINCIDE" and item.get("academic_code") is not None
                }
                requested_principal = _integer(principal_teacher_by_course.get(course_id))
                if len(teacher_codes) == 1:
                    resolved_principals[course_id] = next(iter(teacher_codes))
                elif requested_principal in teacher_codes:
                    resolved_principals[course_id] = int(requested_principal)
                else:
                    raise MoodleAcademicEnrollmentError(
                        f"Seleccione un docente principal válido para {course['course']['name']}"
                    )

            user_code = (_clean(actor) or "APP")[:10]
            result_courses: list[dict[str, Any]] = []
            total_inserted = 0
            total_existing = 0
            total_skipped = 0
            total_teacher_inserted = 0
            total_teacher_existing = 0
            total_linked = 0
            total_first_enrollments = 0
            total_second_enrollments = 0
            total_third_enrollments = 0

            for course in preview["courses"]:
                course_id = int(course["course"]["id"])
                successful_by_context: dict[tuple[int, int], set[int]] = defaultdict(set)
                student_results: list[dict[str, Any]] = []
                total_skipped += int(course["summary"]["blocked_students"])
                for student in course["students"]:
                    if student["status"] not in {"LISTO", "EXISTENTE"}:
                        continue
                    payload = academic.AcademicEnrollmentPayload(
                        codigo_estud=int(student["student_code"]),
                        cod_anio_basica=int(student["career_code"]),
                        codigo_periodo=int(preview["period"]["code"]),
                        materia_codes=[int(student["subject_id"])],
                        paralelo=course["parallel"],
                        num_grupo=1,
                        tipo_matricula=preview["period"]["enrollment_type"],
                        control_matricula=1,
                        cod_jornada=int(preview["jornada"]["code"]),
                    )
                    try:
                        saved = academic._save_enrollment_with_cursor(
                            cursor,
                            payload,
                            user_code,
                            date.today(),
                        )
                    except HTTPException as exc:
                        raise MoodleAcademicEnrollmentError(
                            f"No se pudo matricular a {student['moodle_name']}: {_clean(exc.detail)}"
                        ) from exc
                    inserted = int(saved.get("inserted", 0) or 0)
                    existing = int(saved.get("existing_skipped", 0) or 0)
                    if int(saved.get("blocked_by_repetition", 0) or 0) > 0:
                        raise MoodleAcademicEnrollmentError(
                            f"La matrícula de {student['moodle_name']} excede el límite permitido"
                        )
                    if inserted == 0 and existing == 0:
                        raise MoodleAcademicEnrollmentError(
                            f"No se confirmó la matrícula de {student['moodle_name']}"
                        )
                    subject_result = next(
                        (
                            item
                            for item in saved.get("subject_results", [])
                            if _integer(item.get("codigo_materia")) == int(student["subject_id"])
                        ),
                        {},
                    )
                    enrollment_number = (
                        _integer(subject_result.get("num_matricula"))
                        or _integer(student.get("enrollment_number"))
                        or 1
                    )
                    total_inserted += inserted
                    total_existing += existing
                    if inserted and enrollment_number == 1:
                        total_first_enrollments += 1
                    elif inserted and enrollment_number == 2:
                        total_second_enrollments += 1
                    elif inserted and enrollment_number == 3:
                        total_third_enrollments += 1
                    context_key = (int(student["career_code"]), int(student["subject_id"]))
                    successful_by_context[context_key].add(int(student["student_code"]))
                    student_results.append(
                        {
                            "student_code": int(student["student_code"]),
                            "name": student["academic_name"] or student["moodle_name"],
                            "status": "MATRICULADO" if inserted else "EXISTENTE",
                            "enrollment_number": enrollment_number,
                        }
                    )

                teacher_codes = sorted(
                    {
                        int(item["academic_code"])
                        for item in course["teachers"]
                        if item["status"] == "COINCIDE" and item.get("academic_code") is not None
                    }
                )
                for context in course["academic_contexts"]:
                    key = (int(context["career_code"]), int(context["subject_id"]))
                    student_codes = sorted(successful_by_context.get(key, set()))
                    for teacher_code in teacher_codes:
                        cursor.execute(
                            """
                            SELECT COUNT(*)
                            FROM dbo.CARRERAXDOCENTE
                            WHERE TRY_CONVERT(int, codigo_doc) = ?
                              AND TRY_CONVERT(int, cod_Anio_Basica) = ?
                              AND TRY_CONVERT(int, codigo_materia) = ?
                              AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), Paralelo)))) = ?
                              AND TRY_CONVERT(int, codigo_periodo) = ?
                              AND TRY_CONVERT(int, Cod_Jornada) = ?
                            """,
                            teacher_code,
                            key[0],
                            key[1],
                            course["parallel"],
                            int(preview["period"]["code"]),
                            int(preview["jornada"]["code"]),
                        )
                        if int(cursor.fetchone()[0] or 0) > 0:
                            total_teacher_existing += 1
                        else:
                            cursor.execute(
                                """
                                INSERT INTO dbo.CARRERAXDOCENTE (
                                    codigo_doc, cod_Anio_Basica, codigo_materia, Paralelo,
                                    codigo_periodo, Cod_Jornada, estadoMoodleDoc
                                )
                                VALUES (?, ?, ?, ?, ?, ?, 1)
                                """,
                                teacher_code,
                                key[0],
                                key[1],
                                course["parallel"],
                                int(preview["period"]["code"]),
                                int(preview["jornada"]["code"]),
                            )
                            total_teacher_inserted += 1
                    total_linked += academic._link_teacher_to_enrolled_students(
                        cursor,
                        codigo_doc=resolved_principals[course_id],
                        cod_anio_basica=key[0],
                        codigo_materia=key[1],
                        codigo_periodo=int(preview["period"]["code"]),
                        paralelo=course["parallel"],
                        student_codes=student_codes,
                    )

                result_courses.append(
                    {
                        "course_id": course_id,
                        "course_name": course["course"]["name"],
                        "parallel": course["parallel"],
                        "principal_teacher_code": resolved_principals[course_id],
                        "teachers": len(teacher_codes),
                        "students": student_results,
                        "inserted": sum(1 for item in student_results if item["status"] == "MATRICULADO"),
                        "existing": sum(1 for item in student_results if item["status"] == "EXISTENTE"),
                    }
                )

            connection.commit()
            return {
                "ok": True,
                "message": "Matrícula masiva desde Moodle completada correctamente",
                "period": preview["period"],
                "jornada": preview["jornada"],
                "courses": result_courses,
                "summary": {
                    "courses": len(result_courses),
                    "students_inserted": total_inserted,
                    "students_existing": total_existing,
                    "students_skipped": total_skipped,
                    "first_enrollments": total_first_enrollments,
                    "second_enrollments": total_second_enrollments,
                    "third_enrollments": total_third_enrollments,
                    "teacher_assignments_inserted": total_teacher_inserted,
                    "teacher_assignments_existing": total_teacher_existing,
                    "student_teacher_links": total_linked,
                },
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["MoodleAcademicEnrollmentService", "extract_parallel_from_course_name"]
