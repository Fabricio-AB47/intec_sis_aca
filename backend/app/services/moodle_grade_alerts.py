from __future__ import annotations

import asyncio
import copy
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Iterable, Sequence
from unicodedata import combining, normalize

from app.core.security import SessionUser
from app.services.db import get_connection
from app.services.email_identity import normalize_email_identity
from app.services.moodle_grade_sync import (
    MoodleGradeSyncError,
    MoodleGradeSyncService,
    canonical_course_code,
)


_REGULAR_COMPONENTS = (
    "P1Tareas",
    "P1Proyectos",
    "P1Examen",
    "P2Tareas",
    "P2Proyectos",
    "P2Examen",
    "P3Tareas",
    "P3Proyectos",
    "P3Examen",
)
_HOMOLOGATION_COMPONENTS = ("teoriaHomo", "practicahomo")
_IDENTITY_WARNING_STATES = {
    "missing_institutional_email",
    "not_enrolled",
    "ambiguous_user",
}
_GRADE_WARNING_STATES = {"without_grades", "without_exam_grade"}
_REVIEW_WARNING_STATES = {"invalid_grade", "ambiguous_grade"}
_COMPONENT_LABELS = {
    "P1Tareas": "P1 examen práctico · Tareas 30 %",
    "P1Proyectos": "P1 examen teórico · Proyectos 30 %",
    "P1Examen": "P1 examen práctico · Examen 40 %",
    "P2Tareas": "P2 examen práctico · Tareas 30 %",
    "P2Proyectos": "P2 examen teórico · Proyectos 30 %",
    "P2Examen": "P2 examen práctico · Examen 40 %",
    "P3Tareas": "P3 examen práctico · Tareas 30 %",
    "P3Proyectos": "P3 examen teórico · Proyectos 30 %",
    "P3Examen": "P3 examen práctico · Examen 40 %",
    "teoriaHomo": "Teoría de homologación 40%",
    "practicahomo": "Práctica de homologación 60%",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalized_role(value: Any) -> str:
    return "".join(
        character
        for character in normalize("NFKD", _text(value).upper())
        if not combining(character)
    )


def _normalized_parallel(value: Any) -> str:
    return _text(value).upper()


def _grade_is_present(value: Any) -> bool:
    """Distingue una nota cero válida de un componente sin registrar."""

    return value is not None and _text(value).upper() not in {"", "-", "NULL", "N/A"}


def _grade_number(value: Any) -> float | int | None:
    """Serializa valores numéricos de SQL sin convertir una nota cero en ausencia."""

    if not _grade_is_present(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else round(number, 4)


def _components_for_type(enrollment_type: Any) -> tuple[str, ...]:
    return (
        _REGULAR_COMPONENTS
        if _text(enrollment_type).upper() == "R"
        else _HOMOLOGATION_COMPONENTS
    )


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row, strict=False))


def _chunks(values: Sequence[int], size: int = 3) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])


class MoodleGradeAlertService:
    """Detecta calificaciones Moodle pendientes con alcance académico exacto."""

    def __init__(
        self,
        grade_sync: MoodleGradeSyncService,
        *,
        cache_ttl_seconds: int = 300,
        concurrency: int = 6,
    ) -> None:
        self._grade_sync = grade_sync
        self._cache_ttl_seconds = max(cache_ttl_seconds, 30)
        self._concurrency = max(concurrency, 1)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_generation = 0
        self._locks: dict[str, asyncio.Lock] = {}

    def invalidate_cache(self) -> None:
        """Fuerza una nueva revisión después de modificar calificaciones."""

        self._cache_generation += 1
        self._cache.clear()

    async def list_alerts(
        self,
        user: SessionUser,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        role = _normalized_role(user.rol)
        if role not in {"ADMINISTRADOR", "ACADEMICO", "DOCENTE"}:
            raise MoodleGradeSyncError(
                "Las alertas de calificación están disponibles para Docente, Académico y Administrador"
            )
        if role == "DOCENTE" and not user.codigo_doc:
            raise MoodleGradeSyncError(
                "El perfil docente no tiene un código vinculado para consultar sus asignaciones"
            )

        cache_key = f"{role}:{int(user.codigo_doc or 0)}"
        cached = self._cached(cache_key)
        if cached is not None and not refresh:
            cached["cached"] = True
            return cached

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._cached(cache_key)
            if cached is not None and not refresh:
                cached["cached"] = True
                return cached
            generation = self._cache_generation
            result = await self._scan(user=user, role=role, refresh=refresh)
            if generation != self._cache_generation:
                generation = self._cache_generation
                result = await self._scan(user=user, role=role, refresh=True)
            if generation == self._cache_generation:
                self._cache[cache_key] = (monotonic(), copy.deepcopy(result))
            return result

    def _cached(self, cache_key: str) -> dict[str, Any] | None:
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        stored_at, payload = cached
        if monotonic() - stored_at > self._cache_ttl_seconds:
            self._cache.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)

    async def _scan(
        self,
        *,
        user: SessionUser,
        role: str,
        refresh: bool,
    ) -> dict[str, Any]:
        assignments = await asyncio.to_thread(
            self._teacher_assignments,
            int(user.codigo_doc) if role == "DOCENTE" and user.codigo_doc else None,
        )
        if role == "DOCENTE" and not assignments:
            return self._response(role=role, items=[], errors=[], assignments=assignments)

        catalog = await self._grade_sync.catalog(refresh=refresh)
        jobs = self._preview_jobs(
            catalog.get("courses") or [],
            assignments=assignments,
            role=role,
        )
        academic_pairs = self._academic_pairs(catalog.get("courses") or [], jobs)
        academic_enrollments = await asyncio.to_thread(
            self._active_enrollments,
            academic_pairs,
        )
        enrollments_by_course_period: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for enrollment in academic_enrollments:
            enrollments_by_course_period[
                (
                    canonical_course_code(enrollment.get("course_code")),
                    int(enrollment.get("period_code") or 0),
                )
            ].append(enrollment)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def load_preview(course_id: int, period_codes: list[int]) -> dict[str, Any]:
            async with semaphore:
                try:
                    preview = await self._grade_sync.preview(
                        course_id=course_id,
                        period_codes=period_codes,
                        refresh=False,
                        replace_existing=False,
                    )
                    return {
                        "preview": preview,
                        "error": None,
                        "period_codes": period_codes,
                    }
                except Exception as exc:  # La bandeja conserva el resto de cursos si uno falla.
                    return {
                        "preview": None,
                        "period_codes": period_codes,
                        "error": {
                            "course_id": course_id,
                            "period_codes": period_codes,
                            "message": _text(exc)[:500] or "No se pudo revisar el curso Moodle",
                        },
                    }

        results = await asyncio.gather(
            *(load_preview(course_id, period_codes) for course_id, period_codes in jobs)
        )
        courses_by_id = {
            int(course.get("id") or 0): course
            for course in catalog.get("courses") or []
            if int(course.get("id") or 0) > 0
        }
        assignment_index = self._assignment_index(assignments)
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        validation_totals: dict[str, int] = defaultdict(int)
        for result in results:
            if result["error"]:
                error = result["error"]
                errors.append(error)
                course = courses_by_id.get(int(error.get("course_id") or 0), {})
                course_code = canonical_course_code(course.get("matched_course_code"))
                scoped_enrollments = [
                    enrollment
                    for period_code in result.get("period_codes") or []
                    for enrollment in enrollments_by_course_period.get(
                        (course_code, int(period_code or 0)),
                        [],
                    )
                ]
                items.extend(
                    self._academic_alerts_when_moodle_fails(
                        course=course,
                        role=role,
                        error_message=_text(error.get("message")),
                        assignments=assignment_index,
                        academic_enrollments=scoped_enrollments,
                    )
                )
                continue
            preview = result["preview"] or {}
            for key, value in (preview.get("course_validation") or {}).items():
                try:
                    validation_totals[key] += int(value or 0)
                except (TypeError, ValueError):
                    continue
            preview_course_code = canonical_course_code((preview.get("course") or {}).get("code"))
            selected_period_codes = preview.get("selected_period_codes") or [
                period.get("code") or period.get("period_code")
                for period in preview.get("periods") or []
            ] or result.get("period_codes") or []
            scoped_enrollments = [
                enrollment
                for period_code in selected_period_codes
                for enrollment in enrollments_by_course_period.get(
                    (preview_course_code, int(period_code or 0)),
                    [],
                )
            ]
            items.extend(
                self._alerts_from_preview(
                    preview,
                    role=role,
                    assignments=assignment_index,
                    academic_enrollments=scoped_enrollments,
                )
            )

        unique_items = self._merge_alert_items(items)
        return self._response(
            role=role,
            items=sorted(
                unique_items.values(),
                key=lambda item: (
                    0 if item["severity"] == "alert" else 1,
                    _text(item.get("teacher")),
                    _text(item.get("student")),
                    int(item.get("period_code") or 0),
                ),
            ),
            errors=self._consolidate_errors(errors),
            assignments=assignments,
            validation=dict(validation_totals),
        )

    @staticmethod
    def _teacher_assignments(teacher_code: int | None) -> list[dict[str, Any]]:
        with get_connection() as connection:
            cursor = connection.cursor()
            sql = """
                SELECT DISTINCT
                    TRY_CONVERT(int, cxd.codigo_doc) AS teacher_code,
                    TRY_CONVERT(nvarchar(255), docente.apellidos_nombre) AS teacher,
                    TRY_CONVERT(int, cxd.cod_Anio_Basica) AS malla_code,
                    TRY_CONVERT(int, cxd.codigo_materia) AS matter_code,
                    TRY_CONVERT(int, cxd.codigo_periodo) AS period_code,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo))) AS parallel,
                    TRY_CONVERT(nvarchar(100), pensum.cod_materia) AS course_code,
                    TRY_CONVERT(nvarchar(255), pensum.Nomb_Materia) AS matter,
                    TRY_CONVERT(nvarchar(255), carrera.Nombre_Basica) AS career,
                    TRY_CONVERT(nvarchar(255), periodo.Detalle_Periodo) AS period_name,
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula)))) AS period_type
                FROM dbo.CARRERAXDOCENTE AS cxd
                INNER JOIN dbo.DATOSDOCENTE AS docente
                  ON TRY_CONVERT(int, docente.codigo_doc) = TRY_CONVERT(int, cxd.codigo_doc)
                INNER JOIN dbo.PENSUM AS pensum
                  ON TRY_CONVERT(int, pensum.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                 AND TRY_CONVERT(int, pensum.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                INNER JOIN dbo.PERIODO AS periodo
                  ON TRY_CONVERT(int, periodo.cod_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                LEFT JOIN dbo.CARRERAS AS carrera
                  ON TRY_CONVERT(int, carrera.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula)))) IN (N'R', N'H')
            """
            parameters: list[Any] = []
            if teacher_code is not None:
                sql += " AND TRY_CONVERT(int, cxd.codigo_doc) = ?"
                parameters.append(teacher_code)
            cursor.execute(sql, *parameters)
            return [_row_to_dict(cursor, row) for row in cursor.fetchall()]

    @staticmethod
    def _academic_pairs(
        courses: Sequence[dict[str, Any]],
        jobs: Sequence[tuple[int, list[int]]],
    ) -> set[tuple[str, int]]:
        codes_by_course_id = {
            int(course.get("id") or 0): canonical_course_code(course.get("matched_course_code"))
            for course in courses
        }
        return {
            (codes_by_course_id.get(course_id, ""), int(period_code))
            for course_id, period_codes in jobs
            for period_code in period_codes
            if codes_by_course_id.get(course_id, "") and int(period_code or 0) > 0
        }

    @staticmethod
    def _active_enrollments(
        academic_pairs: set[tuple[str, int]],
    ) -> list[dict[str, Any]]:
        """Carga todas las matrículas activas del alcance, incluso sin usuario Moodle."""

        period_codes = sorted({period_code for _, period_code in academic_pairs})
        if not period_codes:
            return []

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE #MoodleAlertPeriods (
                    period_code int NOT NULL PRIMARY KEY
                )
                """
            )
            cursor.executemany(
                "INSERT INTO #MoodleAlertPeriods (period_code) VALUES (?)",
                [(period_code,) for period_code in period_codes],
            )
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(bigint, ce.num) AS row_id,
                    TRY_CONVERT(int, ce.codigo_estud) AS student_code,
                    TRY_CONVERT(int, ce.cod_anio_Basica) AS malla_code,
                    TRY_CONVERT(int, ce.codigo_materia) AS matter_code,
                    TRY_CONVERT(int, ce.codigo_periodo) AS period_code,
                    TRY_CONVERT(int, ce.Num_Matricula) AS enrollment_number,
                    TRY_CONVERT(int, ce.NumGrupo) AS group_number,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), ce.paralelo))) AS parallel,
                    TRY_CONVERT(nvarchar(100), pensum.cod_materia) AS course_code,
                    TRY_CONVERT(nvarchar(255), pensum.Nomb_Materia) AS matter,
                    TRY_CONVERT(nvarchar(255), carrera.Nombre_Basica) AS [career],
                    TRY_CONVERT(nvarchar(255), periodo.Detalle_Periodo) AS [period],
                    UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula)))) AS [type],
                    TRY_CONVERT(nvarchar(50), estudiante.Cedula_Est) AS [identity],
                    TRY_CONVERT(nvarchar(255), estudiante.Apellidos_nombre) AS [student],
                    correo.institutional_email AS [email],
                    ce.P1Tareas, ce.P1Proyectos, ce.P1Examen,
                    ce.P2Tareas, ce.P2Proyectos, ce.P2Examen,
                    ce.P3Tareas, ce.P3Proyectos, ce.P3Examen,
                    ce.teoriaHomo, ce.practicahomo,
                    ce.Recuperacion AS recovery_grade,
                    ce.PromedioFinal AS final_grade,
                    TRY_CONVERT(nvarchar(50), ce.caprueba) AS approval
                FROM dbo.CARRERAXESTUD AS ce
                INNER JOIN #MoodleAlertPeriods AS alcance
                  ON alcance.period_code = TRY_CONVERT(int, ce.codigo_periodo)
                INNER JOIN dbo.DATOS_ESTUD AS estudiante
                  ON TRY_CONVERT(int, estudiante.codigo_estud) = TRY_CONVERT(int, ce.codigo_estud)
                INNER JOIN dbo.PENSUM AS pensum
                  ON TRY_CONVERT(int, pensum.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                 AND TRY_CONVERT(int, pensum.codigo_materia) = TRY_CONVERT(int, ce.codigo_materia)
                INNER JOIN dbo.PERIODO AS periodo
                  ON TRY_CONVERT(int, periodo.cod_periodo) = TRY_CONVERT(int, ce.codigo_periodo)
                LEFT JOIN dbo.CARRERAS AS carrera
                  ON TRY_CONVERT(int, carrera.Cod_AnioBasica) = TRY_CONVERT(int, ce.cod_anio_Basica)
                OUTER APPLY (
                    SELECT TOP (1)
                        LOWER(LTRIM(RTRIM(
                            REPLACE(REPLACE(REPLACE(
                                TRY_CONVERT(nvarchar(254), registro.CorreoIntec),
                                NCHAR(160), N' '
                            ), NCHAR(8203), N''), NCHAR(65279), N'')
                        ))) COLLATE Latin1_General_100_CI_AS AS institutional_email
                    FROM dbo.CorreosEstudIntec AS registro
                    WHERE TRY_CONVERT(int, registro.codestud) = TRY_CONVERT(int, ce.codigo_estud)
                      AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(254), registro.CorreoIntec))), N'')
                          IS NOT NULL
                    ORDER BY LOWER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(254), registro.CorreoIntec))))
                ) AS correo
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), estudiante.Estado))))
                        IN (N'A', N'ACTIVO', N'ACTIVA')
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(10), periodo.TipoMatricula))))
                        IN (N'R', N'H')
                """
            )
            rows = [_row_to_dict(cursor, row) for row in cursor.fetchall()]

        unique_rows: dict[int, dict[str, Any]] = {}
        for row in rows:
            row["email"] = normalize_email_identity(row.get("email"))
            pair = (
                canonical_course_code(row.get("course_code")),
                int(row.get("period_code") or 0),
            )
            row_id = int(row.get("row_id") or 0)
            if pair in academic_pairs and row_id > 0:
                unique_rows[row_id] = row
        return list(unique_rows.values())

    @staticmethod
    def _preview_jobs(
        courses: Sequence[dict[str, Any]],
        *,
        assignments: Sequence[dict[str, Any]],
        role: str = "ADMINISTRADOR",
    ) -> list[tuple[int, list[int]]]:
        assignment_periods: dict[str, set[int]] = defaultdict(set)
        for assignment in assignments:
            code = canonical_course_code(assignment.get("course_code"))
            period_code = int(assignment.get("period_code") or 0)
            if code and period_code > 0:
                assignment_periods[code].add(period_code)

        jobs: list[tuple[int, list[int]]] = []
        for course in courses:
            course_id = int(course.get("id") or 0)
            code = canonical_course_code(course.get("matched_course_code"))
            if course_id <= 0 or not code:
                continue
            periods_by_type: dict[str, set[int]] = defaultdict(set)
            for period in course.get("periods") or []:
                period_code = int(period.get("period_code") or 0)
                period_type = _text(period.get("period_type")).upper()
                students = int(period.get("students") or 0)
                if period_code <= 0 or period_type not in {"R", "H"} or students <= 0:
                    continue
                # El docente conserva exclusivamente su asignación exacta. Los perfiles
                # institucionales revisan toda matrícula activa del catálogo para poder
                # detectar también cursos que todavía no tienen docente correctamente
                # relacionado en CARRERAXDOCENTE.
                if (
                    _normalized_role(role) == "DOCENTE"
                    and period_code not in assignment_periods.get(code, set())
                ):
                    continue
                periods_by_type[period_type].add(period_code)
            for period_type in sorted(periods_by_type):
                period_codes = sorted(periods_by_type[period_type], reverse=True)
                jobs.extend((course_id, group) for group in _chunks(period_codes))
        return jobs

    @staticmethod
    def _consolidate_errors(errors: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[int, str], set[int]] = defaultdict(set)
        for item in errors:
            course_id = int(item.get("course_id") or 0)
            message = _text(item.get("message")) or "No se pudo revisar el curso Moodle"
            grouped[(course_id, message)].update(
                int(period_code)
                for period_code in item.get("period_codes") or []
                if int(period_code or 0) > 0
            )
        return [
            {
                "course_id": course_id,
                "period_codes": sorted(period_codes, reverse=True),
                "message": message,
            }
            for (course_id, message), period_codes in sorted(
                grouped.items(),
                key=lambda item: (item[0][0], item[0][1]),
            )
        ]

    @staticmethod
    def _assignment_index(
        assignments: Sequence[dict[str, Any]],
    ) -> dict[tuple[str, int, int, int, str], list[dict[str, Any]]]:
        index: dict[tuple[str, int, int, int, str], list[dict[str, Any]]] = defaultdict(list)
        for assignment in assignments:
            key = (
                canonical_course_code(assignment.get("course_code")),
                int(assignment.get("period_code") or 0),
                int(assignment.get("malla_code") or 0),
                int(assignment.get("matter_code") or 0),
                _normalized_parallel(assignment.get("parallel")),
            )
            index[key].append(assignment)
        return index

    def _alerts_from_preview(
        self,
        preview: dict[str, Any],
        *,
        role: str,
        assignments: dict[tuple[str, int, int, int, str], list[dict[str, Any]]],
        academic_enrollments: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        course = preview.get("course") or {}
        course_code = canonical_course_code(course.get("code"))
        course_id = int(course.get("id") or 0)
        course_name = _text(course.get("name"))
        grouped_changes: dict[tuple[int, int, int, int, str], list[dict[str, Any]]] = defaultdict(list)
        for change in preview.get("changes") or []:
            grouped_changes[self._student_key(change)].append(change)
        grouped_warnings: dict[tuple[int, int, int, int, str], list[dict[str, Any]]] = defaultdict(list)
        for warning in preview.get("enrollment_warnings") or []:
            grouped_warnings[self._student_key(warning)].append(warning)
        academic_by_student = {
            self._student_key(enrollment): enrollment
            for enrollment in academic_enrollments
        }

        alerts: list[dict[str, Any]] = []
        for enrollment in academic_enrollments:
            key = self._student_key(enrollment)
            changes = grouped_changes.get(key, [])
            warnings = grouped_warnings.get(key, [])
            preview_summary = changes[0] if changes else (warnings[0] if warnings else {})
            summary = {**enrollment, **preview_summary}
            scoped_assignments = self._matching_assignments(
                course_code,
                summary,
                assignments,
            )
            if role == "DOCENTE" and not scoped_assignments:
                continue
            expected = _components_for_type(summary.get("type"))
            academic_missing = [
                field for field in expected if not _grade_is_present(enrollment.get(field))
            ]
            received = {_text(change.get("field")) for change in changes}
            moodle_missing = [field for field in expected if field not in received]
            missing = [
                field
                for field in expected
                if field in academic_missing or field in moodle_missing
            ]
            component_details = self._component_details(
                expected,
                enrollment=summary,
                changes=changes,
                moodle_checked=True,
            )
            missing_sources: list[str] = []
            message_parts: list[str] = []
            if academic_missing:
                missing_sources.append("INTECBDD")
                message_parts.append(
                    f"INTECBDD tiene {len(academic_missing)} componente(s) sin nota"
                )
            if moodle_missing:
                missing_sources.append("MOODLE")
                message_parts.append(
                    f"Moodle tiene {len(moodle_missing)} componente(s) sin calificar en Evaluación"
                )
            if missing_sources:
                summary["status"] = (
                    "missing_both"
                    if len(missing_sources) == 2
                    else f"missing_{missing_sources[0].lower()}"
                )
                alerts.append(
                    self._alert_item(
                        kind="SIN_CALIFICAR",
                        severity="alert",
                        summary=summary,
                        course_id=course_id,
                        course_name=course_name,
                        course_code=course_code,
                        assignments=scoped_assignments,
                        missing_components=missing,
                        academic_missing_components=academic_missing,
                        moodle_missing_components=moodle_missing,
                        missing_sources=missing_sources,
                        message=". ".join(message_parts) + ".",
                        component_details=component_details,
                    )
                )

            if not preview_summary and role != "DOCENTE":
                identity_status = (
                    "missing_institutional_email"
                    if not _text(enrollment.get("email"))
                    else "not_enrolled"
                )
                identity_message = (
                    "El estudiante no tiene un CorreoIntec vigente asociado a su código único"
                    if identity_status == "missing_institutional_email"
                    else "El CorreoIntec del estudiante no consta en el curso Moodle"
                )
                alerts.append(
                    self._alert_item(
                        kind="DATOS",
                        severity="warning",
                        summary={**summary, "status": identity_status},
                        course_id=course_id,
                        course_name=course_name,
                        course_code=course_code,
                        assignments=scoped_assignments,
                        missing_components=[],
                        academic_missing_components=[],
                        moodle_missing_components=[],
                        missing_sources=[],
                        message=identity_message,
                        component_details=component_details,
                    )
                )

        for warning in preview.get("enrollment_warnings") or []:
            status = _text(warning.get("status"))
            summary = {
                **(academic_by_student.get(self._student_key(warning)) or {}),
                **warning,
            }
            scoped_assignments = self._matching_assignments(
                course_code,
                summary,
                assignments,
            )
            if role == "DOCENTE" and not scoped_assignments:
                continue
            if status in _IDENTITY_WARNING_STATES:
                if role == "DOCENTE":
                    continue
                kind, severity = "DATOS", "warning"
            elif status in _GRADE_WARNING_STATES:
                # La ausencia de notas ya se representa con el estado comparado
                # de la matrícula activa para evitar duplicar al estudiante.
                continue
            elif status in _REVIEW_WARNING_STATES:
                kind, severity = "REVISAR", "warning"
            else:
                continue
            alerts.append(
                self._alert_item(
                    kind=kind,
                    severity=severity,
                    summary=summary,
                    course_id=course_id,
                    course_name=course_name,
                    course_code=course_code,
                    assignments=scoped_assignments,
                    missing_components=[],
                    academic_missing_components=[],
                    moodle_missing_components=[],
                    missing_sources=[],
                    message=_text(warning.get("reason")),
                    component_details=self._component_details(
                        _components_for_type(summary.get("type")),
                        enrollment=summary,
                        changes=grouped_changes.get(self._student_key(warning), []),
                        moodle_checked=True,
                    ),
                )
            )
        return alerts

    def _academic_alerts_when_moodle_fails(
        self,
        *,
        course: dict[str, Any],
        role: str,
        error_message: str,
        assignments: dict[tuple[str, int, int, int, str], list[dict[str, Any]]],
        academic_enrollments: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """No oculta las notas académicas pendientes si Moodle no puede verificarse."""

        course_id = int(course.get("id") or 0)
        course_name = _text(course.get("fullname") or course.get("name"))
        course_code = canonical_course_code(course.get("matched_course_code"))
        alerts: list[dict[str, Any]] = []
        for enrollment in academic_enrollments:
            scoped_assignments = self._matching_assignments(
                course_code,
                enrollment,
                assignments,
            )
            if role == "DOCENTE" and not scoped_assignments:
                continue
            expected = _components_for_type(enrollment.get("type"))
            academic_missing = [
                field for field in expected if not _grade_is_present(enrollment.get(field))
            ]
            if not academic_missing:
                continue
            alerts.append(
                self._alert_item(
                    kind="SIN_CALIFICAR",
                    severity="alert",
                    summary={**enrollment, "status": "missing_intecbdd_moodle_unavailable"},
                    course_id=course_id,
                    course_name=course_name,
                    course_code=course_code,
                    assignments=scoped_assignments,
                    missing_components=academic_missing,
                    academic_missing_components=academic_missing,
                    moodle_missing_components=[],
                    missing_sources=["INTECBDD"],
                    message=(
                        f"INTECBDD tiene {len(academic_missing)} componente(s) sin nota. "
                        f"Moodle no pudo verificarse: {error_message or 'consulta no disponible'}."
                    ),
                    component_details=self._component_details(
                        expected,
                        enrollment=enrollment,
                        changes=[],
                        moodle_checked=False,
                    ),
                    moodle_checked=False,
                    moodle_error=error_message,
                )
            )
        return alerts

    @staticmethod
    def _component_details(
        expected: Sequence[str],
        *,
        enrollment: dict[str, Any],
        changes: Sequence[dict[str, Any]],
        moodle_checked: bool,
    ) -> list[dict[str, Any]]:
        """Conserva la trazabilidad completa ya obtenida durante la vista previa."""

        changes_by_field: dict[str, dict[str, Any]] = {}
        for change in changes:
            field = _text(change.get("field"))
            if field and field not in changes_by_field:
                changes_by_field[field] = change

        details: list[dict[str, Any]] = []
        for field in expected:
            change = changes_by_field.get(field, {})
            academic_grade = _grade_number(enrollment.get(field))
            moodle_grade = _grade_number(change.get("incoming_grade"))
            details.append(
                {
                    "field": field,
                    "component": _text(change.get("component"))
                    or _COMPONENT_LABELS.get(field, field),
                    "academic_grade": academic_grade,
                    "academic_registered": _grade_is_present(enrollment.get(field)),
                    "moodle_grade": moodle_grade,
                    "moodle_registered": _grade_is_present(change.get("incoming_grade")),
                    "previous_synced_grade": _grade_number(
                        change.get("previous_synced_grade")
                    ),
                    "moodle_grade_item_id": int(change.get("moodle_grade_item_id") or 0),
                    "moodle_grade_item": _text(change.get("moodle_grade_item")),
                    "moodle_grade_item_count": int(
                        change.get("moodle_grade_item_count") or 0
                    ),
                    "moodle_grade_items": [
                        _text(item)
                        for item in change.get("moodle_grade_items") or []
                        if _text(item)
                    ],
                    "moodle_grade_selection": _text(
                        change.get("moodle_grade_selection")
                    ),
                    "moodle_raw_grade": _grade_number(change.get("moodle_raw_grade")),
                    "moodle_grade_min": _grade_number(change.get("moodle_grade_min")),
                    "moodle_grade_max": _grade_number(change.get("moodle_grade_max")),
                    "moodle_grade_raw_source": _text(
                        change.get("moodle_grade_raw_source")
                    ),
                    "moodle_grade_scale_source": _text(
                        change.get("moodle_grade_scale_source")
                    ),
                    "status": _text(change.get("status"))
                    or ("missing" if moodle_checked else "not_checked"),
                    "reason": _text(change.get("reason")),
                }
            )
        return details

    @staticmethod
    def _student_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
        return (
            int(item.get("student_code") or 0),
            int(item.get("period_code") or 0),
            int(item.get("malla_code") or 0),
            int(item.get("matter_code") or 0),
            _normalized_parallel(item.get("parallel")),
        )

    @staticmethod
    def _matching_assignments(
        course_code: str,
        summary: dict[str, Any],
        assignments: dict[tuple[str, int, int, int, str], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        key = (
            course_code,
            int(summary.get("period_code") or 0),
            int(summary.get("malla_code") or 0),
            int(summary.get("matter_code") or 0),
            _normalized_parallel(summary.get("parallel")),
        )
        return assignments.get(key, [])

    @staticmethod
    def _merge_alert_items(
        items: Sequence[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Consolida copias Moodle del mismo registro académico sin perder fuentes."""

        merged: dict[str, dict[str, Any]] = {}
        ordered_fields = (*_REGULAR_COMPONENTS, *_HOMOLOGATION_COMPONENTS)

        def ordered_union(*values: Sequence[Any]) -> list[Any]:
            unique = {item for group in values for item in group}
            known = [item for item in ordered_fields if item in unique]
            return known + sorted(unique - set(known), key=str)

        def merge_component_details(
            first: Sequence[dict[str, Any]],
            second: Sequence[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            by_field: dict[str, dict[str, Any]] = {}
            for detail in (*first, *second):
                field = _text(detail.get("field"))
                if not field:
                    continue
                current_detail = by_field.get(field)
                if current_detail is None:
                    by_field[field] = copy.deepcopy(detail)
                    continue
                preferred = (
                    detail
                    if detail.get("moodle_registered")
                    and not current_detail.get("moodle_registered")
                    else current_detail
                )
                combined_detail = copy.deepcopy(preferred)
                combined_detail["moodle_grade_items"] = list(
                    dict.fromkeys(
                        [
                            *(
                                current_detail.get("moodle_grade_items")
                                or []
                            ),
                            *(detail.get("moodle_grade_items") or []),
                        ]
                    )
                )
                combined_detail["moodle_grade_item_count"] = max(
                    int(current_detail.get("moodle_grade_item_count") or 0),
                    int(detail.get("moodle_grade_item_count") or 0),
                )
                by_field[field] = combined_detail
            return [
                by_field[field]
                for field in ordered_fields
                if field in by_field
            ]

        for item in items:
            item_id = _text(item.get("id"))
            current = merged.get(item_id)
            if current is None:
                merged[item_id] = copy.deepcopy(item)
                continue

            richer = item if len(item.get("missing_sources") or []) > len(
                current.get("missing_sources") or []
            ) else current
            combined = copy.deepcopy(richer)
            combined["missing_components"] = ordered_union(
                current.get("missing_components") or [],
                item.get("missing_components") or [],
            )
            combined["academic_missing_components"] = ordered_union(
                current.get("academic_missing_components") or [],
                item.get("academic_missing_components") or [],
            )
            combined["moodle_missing_components"] = ordered_union(
                current.get("moodle_missing_components") or [],
                item.get("moodle_missing_components") or [],
            )
            combined["missing_sources"] = [
                source
                for source in ("INTECBDD", "MOODLE")
                if source in {
                    *(current.get("missing_sources") or []),
                    *(item.get("missing_sources") or []),
                }
            ]
            combined["teacher_codes"] = sorted(
                {
                    *(current.get("teacher_codes") or []),
                    *(item.get("teacher_codes") or []),
                }
            )
            combined["component_details"] = merge_component_details(
                current.get("component_details") or [],
                item.get("component_details") or [],
            )
            combined["moodle_courses"] = list(
                {
                    (
                        int(course.get("course_id") or 0),
                        _text(course.get("course")),
                        _text(course.get("course_code")),
                    ): course
                    for course in [
                        *(current.get("moodle_courses") or []),
                        *(item.get("moodle_courses") or []),
                    ]
                }.values()
            )
            combined["teacher_assignments"] = list(
                {
                    (
                        int(teacher.get("teacher_code") or 0),
                        _text(teacher.get("teacher")),
                    ): teacher
                    for teacher in [
                        *(current.get("teacher_assignments") or []),
                        *(item.get("teacher_assignments") or []),
                    ]
                }.values()
            )
            teacher_names = sorted(
                {
                    _text(teacher.get("teacher"))
                    for teacher in combined["teacher_assignments"]
                    if _text(teacher.get("teacher"))
                }
            )
            combined["teacher"] = (
                ", ".join(teacher_names) if teacher_names else "Sin docente asignado"
            )
            combined["moodle_checked"] = bool(
                current.get("moodle_checked") or item.get("moodle_checked")
            )
            combined["moodle_error"] = " ".join(
                dict.fromkeys(
                    value
                    for value in (
                        _text(current.get("moodle_error")),
                        _text(item.get("moodle_error")),
                    )
                    if value
                )
            )
            messages = list(
                dict.fromkeys(
                    message
                    for message in (
                        _text(current.get("message")),
                        _text(item.get("message")),
                    )
                    if message
                )
            )
            combined["message"] = " ".join(messages)
            merged[item_id] = combined
        return merged

    @staticmethod
    def _alert_item(
        *,
        kind: str,
        severity: str,
        summary: dict[str, Any],
        course_id: int,
        course_name: str,
        course_code: str,
        assignments: Sequence[dict[str, Any]],
        missing_components: list[str],
        academic_missing_components: list[str],
        moodle_missing_components: list[str],
        missing_sources: list[str],
        message: str,
        component_details: list[dict[str, Any]] | None = None,
        moodle_checked: bool = True,
        moodle_error: str = "",
    ) -> dict[str, Any]:
        teacher_codes = sorted(
            {int(item.get("teacher_code") or 0) for item in assignments if item.get("teacher_code")}
        )
        teachers = sorted({_text(item.get("teacher")) for item in assignments if _text(item.get("teacher"))})
        teacher_assignments = [
            {
                "teacher_code": int(item.get("teacher_code") or 0),
                "teacher": _text(item.get("teacher")),
            }
            for item in assignments
            if int(item.get("teacher_code") or 0) > 0 or _text(item.get("teacher"))
        ]
        student_code = int(summary.get("student_code") or 0)
        period_code = int(summary.get("period_code") or 0)
        malla_code = int(summary.get("malla_code") or 0)
        matter_code = int(summary.get("matter_code") or 0)
        parallel = _normalized_parallel(summary.get("parallel"))
        academic_course_key = course_code or f"MOODLE-{course_id}"
        return {
            "id": (
                f"{kind}:{academic_course_key}:{student_code}:{period_code}:"
                f"{malla_code}:{matter_code}:{parallel}"
            ),
            "kind": kind,
            "severity": severity,
            "status": _text(summary.get("status")) or "incomplete",
            "student_code": student_code,
            "student": _text(summary.get("student")),
            "identity": _text(summary.get("identity")),
            "email": _text(summary.get("email")),
            "email_source": _text(summary.get("email_source"))
            or ("CorreosEstudIntec" if _text(summary.get("email")) else ""),
            "moodle_email": _text(summary.get("moodle_email")),
            "moodle_user_id": int(summary.get("moodle_user_id") or 0),
            "course_enrollment_validated": bool(
                summary.get("course_enrollment_validated")
            ),
            "teacher_codes": teacher_codes,
            "teacher": ", ".join(teachers) if teachers else "Sin docente asignado",
            "teacher_assignments": teacher_assignments,
            "course_id": course_id,
            "course": course_name,
            "course_code": course_code,
            "malla_code": malla_code,
            "matter_code": matter_code,
            "matter": _text(summary.get("matter")),
            "career": _text(summary.get("career")),
            "period_code": period_code,
            "period": _text(summary.get("period")),
            "type": _text(summary.get("type")).upper(),
            "parallel": parallel,
            "record_id": int(summary.get("row_id") or 0),
            "enrollment_number": int(summary.get("enrollment_number") or 0),
            "group_number": int(
                summary.get("group_number") or summary.get("group") or 0
            ),
            "recovery_grade": _grade_number(summary.get("recovery_grade")),
            "final_grade": _grade_number(summary.get("final_grade")),
            "approval": _text(summary.get("approval")),
            "missing_components": missing_components,
            "academic_missing_components": academic_missing_components,
            "moodle_missing_components": moodle_missing_components,
            "missing_sources": missing_sources,
            "message": message,
            "component_details": component_details or [],
            "moodle_checked": moodle_checked,
            "moodle_error": _text(moodle_error),
            "moodle_courses": [
                {
                    "course_id": course_id,
                    "course": course_name,
                    "course_code": course_code,
                }
            ] if course_id > 0 else [],
        }

    @staticmethod
    def _response(
        *,
        role: str,
        items: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        assignments: Sequence[dict[str, Any]],
        validation: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        pending = [item for item in items if item["kind"] == "SIN_CALIFICAR"]
        review = [item for item in items if item["kind"] == "REVISAR"]
        data_issues = [item for item in items if item["kind"] == "DATOS"]
        validation = validation or {}
        missing_intecbdd = sum(
            1 for item in pending if "INTECBDD" in item.get("missing_sources", [])
        )
        missing_moodle = sum(
            1 for item in pending if "MOODLE" in item.get("missing_sources", [])
        )
        return {
            "scope": "DOCENTE" if role == "DOCENTE" else "INSTITUCIONAL",
            "role": role,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cached": False,
            "summary": {
                "total": len(items),
                "ungraded": len(pending),
                "review": len(review),
                "data_issues": len(data_issues),
                "courses": len({int(item["course_id"]) for item in items}),
                "students": len({int(item["student_code"]) for item in items}),
                "teachers": len(
                    {
                        teacher_code
                        for item in items
                        for teacher_code in item.get("teacher_codes") or []
                    }
                ),
                "assignments": len(assignments),
                "errors": len(errors),
                "missing_intecbdd": missing_intecbdd,
                "missing_moodle": missing_moodle,
                "missing_both": sum(
                    1
                    for item in pending
                    if {"INTECBDD", "MOODLE"}.issubset(
                        set(item.get("missing_sources", []))
                    )
                ),
                "regular": sum(1 for item in items if item.get("type") == "R"),
                "homologation": sum(1 for item in items if item.get("type") == "H"),
            },
            "validation": {
                "selected_periods": int(validation.get("selected_periods", 0)),
                "academic_enrollments": int(validation.get("academic_enrollments", 0)),
                "moodle_course_users": int(validation.get("moodle_course_users", 0)),
                "matched_by_email": int(validation.get("matched_by_email", 0)),
                "matched_by_registry": int(validation.get("matched_by_registry", 0)),
                "matched_by_data_fallback": int(
                    validation.get("matched_by_data_fallback", 0)
                ),
                "missing_institutional_email": int(
                    validation.get("missing_institutional_email", 0)
                ),
                "not_enrolled_in_course": int(
                    validation.get("not_enrolled_in_course", 0)
                ),
                "ambiguous_users": int(validation.get("ambiguous_users", 0)),
            },
            "items": items,
            "errors": errors,
        }


__all__ = ["MoodleGradeAlertService"]
