from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException
import pyodbc

from app.integrations.moodle.exceptions import MoodleError
from app.services.db import get_connection, get_integration_control_connection
from app.services.moodle_academic_enrollment import (
    MoodleAcademicEnrollmentService, _clean, _fetch_dicts, _is_moodle_student,
    extract_parallel_from_course_name,
)
from app.services.moodle_grade_sync import moodle_user_institutional_identity, normalize_institutional_email
from app.services.moodle_enrollment_subjects import EnrollmentSubjectResolver
from app.services.moodle_read_service import MoodleReadService


ACTIVE_STATES = {"A", "ACTIVO", "ACTIVA"}
STATUS_LABELS = {
    "COINCIDE": "Coincide",
    "FALTA_MOODLE": "Falta en Moodle",
    "SIN_MATRICULA_PERIODO": "Sin materia en el período",
    "OTRA_CARRERA": "Materia de otra carrera",
    "CAMBIO_CARRERA": "Revisar cambio de carrera",
    "OTRO_PARALELO": "Paralelo diferente",
    "IDENTIDAD_AMBIGUA": "Identidad conflictiva o duplicada",
    "NO_IDENTIFICADO": "Estudiante no identificado",
    "INACTIVO": "Estudiante inactivo",
    "SUSPENDIDO_MOODLE": "Cuenta Moodle suspendida",
    "DUPLICADO_MOODLE": "Varias cuentas Moodle",
    "MATRICULA_DUPLICADA": "Matrícula académica duplicada",
    "SIN_CABECERA": "Matrícula sin cabecera relacionada",
    "SIN_PENSUM": "Código de materia no verificable",
    "ERROR_MOODLE": "Curso no consultado",
    "NO_VERIFICABLE": "Pendiente de verificación",
}


def _document(value: Any) -> str:
    # Keep passport letters and leading zeroes. Never identify a student by name.
    return "".join(c for c in _clean(value).upper() if c.isalnum())


def _identity_indexes(registry: list[dict]) -> tuple[dict, dict, dict]:
    people: dict[int, dict] = {}
    emails, documents = defaultdict(set), defaultdict(set)
    for record in registry:
        code = int(record["student_code"])
        person = people.setdefault(code, {**record, "states": set(), "documents": set(), "emails": set()})
        person["states"].add(_clean(record.get("state")).upper())
        doc = _document(record.get("document"))
        if doc:
            person["documents"].add(doc)
            documents[doc].add(code)
        for field in ("email", "registry_email"):
            email = normalize_institutional_email(record.get(field))
            if email:
                emails[email].add(code)
                person["emails"].add(email)
    return people, emails, documents


def _match_identity(user: dict, people: dict, emails: dict, documents: dict) -> tuple[int | None, str, set[int]]:
    email, _, status = moodle_user_institutional_identity(user)
    email_codes = set(emails.get(email, set()))
    doc = _document(user.get("idnumber"))
    doc_codes = set(documents.get(doc, set()))
    possible = email_codes | doc_codes
    if status == "conflicting_email_username":
        possible |= set(emails.get(normalize_institutional_email(user.get("email")), set()))
        possible |= set(emails.get(normalize_institutional_email(user.get("username")), set()))
        return None, "IDENTIDAD_AMBIGUA", possible
    if len(email_codes) > 1 or len(doc_codes) > 1 or (email_codes and doc_codes and email_codes != doc_codes):
        return None, "IDENTIDAD_AMBIGUA", possible
    if len(possible) != 1:
        return None, "NO_IDENTIFICADO", possible
    code = next(iter(possible))
    person = people[code]
    if len(person["documents"]) > 1 or (doc and person["documents"] and doc not in person["documents"]):
        return None, "IDENTIDAD_AMBIGUA", possible
    active = bool(person["states"] & ACTIVE_STATES)
    if active and person["states"] - ACTIVE_STATES:
        return None, "IDENTIDAD_AMBIGUA", possible
    return code, "COINCIDE" if active else "INACTIVO", possible


def _enrollment_key(row: dict) -> tuple:
    return (row["student_code"], row["career_code"], row["subject_id"], _clean(row.get("parallel")).upper())


def compare_enrollments(*, period: dict, registry: list[dict], subjects: list[dict],
                        enrollments: list[dict], history: list[dict], career_changes: list[dict],
                        snapshots: list[dict], actor: str, warnings: list[str],
                        student_codes: set[int] | None = None, career_code: int | None = None) -> dict:
    people, emails, documents = _identity_indexes(registry)
    subject_resolver = EnrollmentSubjectResolver(subjects)
    by_student, past, changes = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in enrollments:
        by_student[row["student_code"]].append(row)
    for row in history:
        past[row["student_code"]].append(row)
    for row in career_changes:
        changes[row["student_code"]].append(row)
    rows, scopes = [], []
    covered, uncertain = set(), set()

    def add(status: str, scope: dict, code: int | None = None, user: dict | None = None,
            enrollment: dict | None = None, reason: str = "") -> None:
        person = people.get(code, {})
        current_careers = sorted({_clean(r.get("career")) for r in by_student[code]} - {""})
        previous = sorted({_clean(r.get("career")) for r in past[code]} - set(current_careers) - {""})
        transitions = [f"{r['origin']} → {r['destination']} ({_clean(r.get('applied_at'))})" for r in changes[code]]
        enrollment_subjects = [r for r in scope["candidates"] if enrollment
                               and (r["career_code"], r["subject_id"]) == (enrollment["career_code"], enrollment["subject_id"])]
        row = {
            "status": status, "status_label": STATUS_LABELS[status],
            "student_code": str(code or ""), "student": _clean(person.get("student")) or _clean((user or {}).get("fullname")),
            "document": _clean(person.get("document")) or _clean((user or {}).get("idnumber")),
            "email": ", ".join(sorted(person.get("emails", []))),
            "moodle_email": _clean((user or {}).get("email")), "moodle_user_id": str((user or {}).get("id") or ""),
            "course_id": str(scope["course"]["id"]), "course": _clean(scope["course"].get("fullname")),
            "moodle_code": _clean(scope["course"].get("shortname")),
            "moodle_idnumber": _clean(scope["course"].get("idnumber")),
            "subject_code": ", ".join(sorted({r["subject_code"] for r in enrollment_subjects})) or scope["subject_code"],
            "code_match": scope["code_match"], "code_match_detail": scope["code_match_detail"],
            "code_candidates": scope["subject_code"],
            "subject": _clean((enrollment or {}).get("subject")) or ", ".join(sorted({r['subject_name'] for r in scope["candidates"]})),
            "academic_career": _clean((enrollment or {}).get("career")),
            "academic_career_code": (enrollment or {}).get("career_code"),
            "academic_subject_id": (enrollment or {}).get("subject_id"),
            "period": period["name"], "period_code": str(period["code"]),
            "academic_parallel": _clean((enrollment or {}).get("parallel")), "moodle_parallel": scope["parallel"],
            "period_careers": ", ".join(current_careers), "previous_careers": ", ".join(previous),
            "career_changes": "; ".join(transitions), "reason": reason,
        }
        rows.append(row)

    for snapshot in snapshots:
        resolution = subject_resolver.resolve(snapshot["course"])
        candidates = resolution.candidates
        scope = {**snapshot, "subject_code": resolution.code, "candidates": candidates, "uncertain": False,
                 "code_match": resolution.method, "code_match_detail": resolution.detail}
        scopes.append(scope)
        keys = {(r["career_code"], r["subject_id"]) for r in candidates}
        scope["expected"] = [r for r in enrollments if (r["career_code"], r["subject_id"]) in keys
                             and (student_codes is None or r["student_code"] in student_codes)
                             and (career_code is None or r["career_code"] == career_code)
                             and (scope["parallel"] == "*" or _clean(r.get("parallel")).upper() == scope["parallel"])]
        if resolution.error:
            scope["uncertain"] = True
            add("SIN_PENSUM", scope, reason=resolution.error)
            continue
        if snapshot.get("error"):
            scope["uncertain"] = True
            add("ERROR_MOODLE", scope, reason=snapshot["error"])
            continue
        matches: dict[int, list[dict]] = defaultdict(list)
        for user in {u["id"]: u for u in snapshot["users"]}.values():
            if not _is_moodle_student(user):
                if not user.get("roles") and not user.get("role_shortnames"):
                    scope["uncertain"] = True
                    add("NO_VERIFICABLE", scope, user=user, reason="Moodle no informó el rol de esta cuenta.")
                continue
            code, identity_status, possible = _match_identity(user, people, emails, documents)
            if student_codes is not None and ((code is not None and code not in student_codes)
                                              or (code is None and possible and not possible & student_codes)):
                continue
            if code is None:
                # An unresolved account could be an expected student: absence is not proven.
                scope["uncertain"] = True
                uncertain.update(_enrollment_key(r) for r in scope["expected"] if r["student_code"] in possible)
                add(identity_status, scope, user=user, reason="Revise el correo institucional y la identificación; no se asignó una identidad por similitud.")
                continue
            if identity_status == "INACTIVO":
                add("INACTIVO", scope, code, user, reason="Registro académico inactivo; excluido de las matrículas esperadas.")
                continue
            matches[code].append(user)
        for code, users in matches.items():
            eligible = [r for r in scope["expected"] if r["student_code"] == code]
            same_subject = [r for r in by_student[code] if (r["career_code"], r["subject_id"]) in keys]
            if len(users) > 1:
                uncertain.update(_enrollment_key(r) for r in eligible)
                add("DUPLICADO_MOODLE", scope, code, users[0], reason="Varias cuentas del curso coinciden con el mismo estudiante: " + ", ".join(str(u["id"]) for u in users))
            elif len(eligible) > 1:
                uncertain.update(_enrollment_key(r) for r in eligible)
                add("MATRICULA_DUPLICADA", scope, code, users[0], reason="Hay varias matrículas compatibles; revise carrera, materia y paralelo.")
            elif eligible:
                row = eligible[0]
                covered.add(_enrollment_key(row))
                if row.get("header_exists") == 0:
                    add("SIN_CABECERA", scope, code, users[0], row, "La materia existe en CARRERAXESTUD pero no tiene cabecera para el mismo estudiante, carrera y período.")
                else:
                    status = "SUSPENDIDO_MOODLE" if users[0].get("suspended") or not users[0].get("confirmed", True) else "COINCIDE"
                    add(status, scope, code, users[0], row, "Coincidencia por identidad, período, carrera de matrícula y código único de materia." if status == "COINCIDE" else "La matrícula coincide, pero la cuenta está suspendida o sin confirmar en Moodle.")
            elif same_subject:
                same_career = [r for r in same_subject if career_code is None or r["career_code"] == career_code]
                if same_career:
                    add("OTRO_PARALELO", scope, code, users[0], same_career[0], "La materia está matriculada en un paralelo diferente al seleccionado para este curso.")
                else:
                    add("OTRA_CARRERA", scope, code, users[0], same_subject[0], "La materia está matriculada en otra carrera del período, no en la carrera seleccionada.")
            else:
                old_subject = [r for r in past[code] if (r["career_code"], r["subject_id"]) in keys]
                career_codes = {r["career_code"] for r in by_student[code]}
                candidate_careers = {r["career_code"] for r in candidates}
                old_career_change = any(r["origin_code"] in candidate_careers and r["destination_code"] not in candidate_careers for r in changes[code])
                status = "CAMBIO_CARRERA" if (old_subject and any(r["career_code"] not in career_codes for r in old_subject)) or old_career_change else (
                    "OTRA_CARRERA" if career_codes and not career_codes & candidate_careers else "SIN_MATRICULA_PERIODO")
                detail = "No existe matrícula de esta materia en el período seleccionado."
                if old_subject:
                    detail += " Registros en otros períodos: " + ", ".join(sorted({r["period"] for r in old_subject})) + "."
                if status == "CAMBIO_CARRERA":
                    detail += " Hay antecedentes de otra carrera; revise si el aula corresponde a una matrícula histórica."
                add(status, scope, code, users[0], reason=detail)

    expected_scopes: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    for scope in scopes:
        for row in scope["expected"]:
            expected_scopes[_enrollment_key(row)].append((scope, row))
    for key, entries in expected_scopes.items():
        if key in covered:
            continue
        scope, row = entries[0]
        code = row["student_code"]
        person = people.get(code)
        if not person or not person["states"] & ACTIVE_STATES:
            continue
        ambiguous = (key in uncertain or any(s["uncertain"] for s, _ in entries)
                     or len(person["documents"]) > 1 or bool(person["states"] - ACTIVE_STATES))
        duplicate = sum(_enrollment_key(r) == key for r in enrollments) > 1
        missing_status = "NO_VERIFICABLE" if ambiguous else "MATRICULA_DUPLICADA" if duplicate else "SIN_CABECERA" if row.get("header_exists") == 0 else "FALTA_MOODLE"
        add(missing_status, scope, code, enrollment=row,
            reason=("No se pudo descartar una coincidencia por errores o identidades ambiguas." if ambiguous else
                    "La matrícula académica está duplicada y no aparece en las aulas consultadas." if duplicate else
                    "La materia no tiene cabecera de matrícula relacionada y no aparece en las aulas consultadas." if missing_status == "SIN_CABECERA" else
                    "La matrícula académica existe y no aparece en las aulas consultadas.") +
                   " Aulas comprobadas: " + ", ".join(str(s["course"]["id"]) for s, _ in entries) + ".")
    counts = Counter(row["status"] for row in rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "actor": actor,
        "period": period, "warnings": warnings,
        "scope": [{"id": s["course"]["id"], "name": s["course"]["fullname"], "parallel": s["parallel"],
                   "subject_code": s["subject_code"], "error": s.get("error", ""),
                   "code_match": s["code_match"], "code_match_detail": s["code_match_detail"]} for s in scopes],
        "summary": {"rows": len(rows), "matches": counts["COINCIDE"], "inactive": counts["INACTIVO"],
                    "findings": len(rows) - counts["COINCIDE"] - counts["INACTIVO"],
                    "career_history": sum(bool(r["previous_careers"] or r["career_changes"]) for r in rows)},
        "rows": sorted(rows, key=lambda r: (r["status"] == "COINCIDE", r["student"], r["course"])),
    }


class MoodleEnrollmentValidationService:
    def __init__(self, moodle: MoodleReadService, connection_factory: Callable = get_connection,
                 history_connection_factory: Callable = get_integration_control_connection):
        self._moodle = moodle
        self._connection = connection_factory
        self._history_connection = history_connection_factory
        self._reports: dict[str, tuple[float, str, dict]] = {}
        self._lock = Lock()

    async def catalog(self) -> dict:
        academic = await asyncio.to_thread(self._catalog)
        courses = await self._moodle.get_all_courses(refresh=True)
        parallels = set(academic["parallels"])
        return {**academic, "courses": [{"id": c["id"], "fullname": c["fullname"], "shortname": c["shortname"],
            "category": c.get("categoryname", ""), "parallel": guess if (guess := extract_parallel_from_course_name(c)) in parallels else ""}
            for c in courses], "max_courses": 100}

    def _catalog(self) -> dict:
        with self._connection() as conn:
            cursor = conn.cursor()
            periods = _fetch_dicts(cursor, """
                SELECT cod_periodo AS code, Detalle_Periodo AS name, TipoMatricula AS enrollment_type
                FROM dbo.PERIODO ORDER BY fechain DESC, cod_periodo DESC
            """)
            parallels = sorted(MoodleAcademicEnrollmentService._load_parallels(cursor))
            career_rows = _fetch_dicts(cursor, """
                SELECT DISTINCT TRY_CONVERT(int, ca.Cod_AnioBasica) AS code,
                    ca.Nombre_Basica AS name, TRY_CONVERT(int, cx.codigo_periodo) AS period_code
                FROM dbo.CARRERAS ca
                INNER JOIN (
                    SELECT cod_anio_Basica, codigo_periodo FROM dbo.CARRERAXESTUD
                    UNION SELECT cod_anio_Basica, codigo_periodo FROM dbo.CABECERA_MATRICULA
                ) cx ON cx.cod_anio_Basica = ca.Cod_AnioBasica
                WHERE TRY_CONVERT(int, ca.Cod_AnioBasica) IS NOT NULL
                    AND TRY_CONVERT(int, cx.codigo_periodo) IS NOT NULL
            """)
        careers = {}
        for row in career_rows:
            career = careers.setdefault(int(row["code"]), {"code": int(row["code"]), "name": _clean(row["name"]), "period_codes": []})
            career["period_codes"].append(int(row["period_code"]))
        return {"periods": [{"code": int(r["code"]), "name": _clean(r["name"]),
                             "enrollment_type": _clean(r["enrollment_type"])} for r in periods], "parallels": parallels,
                "careers": sorted(careers.values(), key=lambda r: r["name"].casefold())}

    def _load_academic(self, period_code: int) -> dict:
        with self._connection() as conn:
            cursor = conn.cursor()
            period = MoodleAcademicEnrollmentService._load_period(cursor, period_code)
            subjects = MoodleAcademicEnrollmentService._load_subjects(cursor)
            registry = _fetch_dicts(cursor, """
                SELECT TRY_CONVERT(int, d.codigo_estud) AS student_code,
                    d.Apellidos_nombre AS student, d.Cedula_Est AS document, d.Estado AS state,
                    d.correointec AS email, ce.CorreoIntec AS registry_email
                FROM dbo.DATOS_ESTUD d LEFT JOIN dbo.CorreosEstudIntec ce
                    ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, d.codigo_estud)
                WHERE TRY_CONVERT(int, d.codigo_estud) IS NOT NULL
            """)
            enrollments = self._enrollments(cursor, "cx.codigo_periodo = ?", [period_code])
        return {"period": {"code": period_code, "name": period["name"]}, "subjects": subjects,
                "registry": registry, "enrollments": enrollments}

    @staticmethod
    def _enrollments(cursor, condition: str, params: list) -> list[dict]:
        return _fetch_dicts(cursor, f"""
            SELECT TRY_CONVERT(int, cx.codigo_estud) AS student_code,
                TRY_CONVERT(int, cx.cod_anio_Basica) AS career_code,
                TRY_CONVERT(int, cx.codigo_materia) AS subject_id,
                TRY_CONVERT(int, cx.codigo_periodo) AS period_code,
                cx.paralelo AS parallel, ca.Nombre_Basica AS career, per.Detalle_Periodo AS period,
                CASE WHEN EXISTS (
                    SELECT 1 FROM dbo.CABECERA_MATRICULA cab
                    WHERE cab.codigo_estud = cx.codigo_estud AND cab.cod_anio_Basica = cx.cod_anio_Basica
                        AND cab.codigo_periodo = cx.codigo_periodo
                ) THEN 1 ELSE 0 END AS header_exists
            FROM dbo.CARRERAXESTUD cx
            LEFT JOIN dbo.CARRERAS ca ON ca.Cod_AnioBasica = cx.cod_anio_Basica
            LEFT JOIN dbo.PERIODO per ON per.cod_periodo = cx.codigo_periodo
            WHERE {condition}
        """, *params)

    def _load_enrollment_headers(self, period_code: int) -> list[dict]:
        with self._connection() as conn:
            return _fetch_dicts(conn.cursor(), """
                SELECT DISTINCT TRY_CONVERT(int, cab.codigo_estud) AS student_code,
                    TRY_CONVERT(int, cab.cod_anio_Basica) AS career_code,
                    TRY_CONVERT(int, cab.codigo_periodo) AS period_code,
                    ca.Nombre_Basica AS career, per.Detalle_Periodo AS period
                FROM dbo.CABECERA_MATRICULA cab
                LEFT JOIN dbo.CARRERAS ca ON ca.Cod_AnioBasica = cab.cod_anio_Basica
                LEFT JOIN dbo.PERIODO per ON per.cod_periodo = cab.codigo_periodo
                WHERE cab.codigo_periodo = ? AND TRY_CONVERT(int, cab.codigo_estud) IS NOT NULL
            """, period_code)

    def _load_history(self, codes: list[int], period_code: int) -> tuple[list, list, list]:
        history, changes, warnings = [], [], []
        if not codes:
            return history, changes, warnings
        with self._connection() as conn:
            for start in range(0, len(codes), 500):
                batch = codes[start:start + 500]
                marks = ",".join("?" for _ in batch)
                history.extend(self._enrollments(conn.cursor(), f"cx.codigo_estud IN ({marks}) AND cx.codigo_periodo <> ?", [*batch, period_code]))
        try:
            with self._history_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OBJECT_ID(N'sol.SolicitudCambioCarrera', N'U')")
                if cursor.fetchone()[0] is None:
                    warnings.append("No está disponible el registro de solicitudes de cambio de carrera; se consultaron las matrículas históricas.")
                else:
                    for start in range(0, len(codes), 500):
                        batch = codes[start:start + 500]
                        marks = ",".join("?" for _ in batch)
                        changes.extend(_fetch_dicts(cursor, f"""
                            SELECT CodigoEstud AS student_code, CarreraOrigen AS origin_code,
                                CarreraDestino AS destination_code, CarreraOrigenNombre AS origin,
                                CarreraDestinoNombre AS destination, FechaAplicacion AS applied_at
                            FROM sol.SolicitudCambioCarrera
                            WHERE Estado = N'APLICADA' AND CodigoEstud IN ({marks})
                            ORDER BY FechaAplicacion
                        """, *batch))
        except (pyodbc.Error, HTTPException, RuntimeError):
            warnings.append("No se pudo consultar el registro de cambios de carrera aplicados; esos antecedentes requieren revisión manual.")
        return history, changes, warnings

    async def course_snapshots(self, courses: list[dict], on_progress: Callable[[int], None] | None = None) -> list[dict]:
        courses_by_id = {int(c["id"]): c for c in await self._moodle.get_all_courses(refresh=True)}
        if any(c["id"] not in courses_by_id for c in courses):
            raise HTTPException(409, "Algún curso ya no está disponible en Moodle. Actualice el catálogo.")
        snapshots = []
        for selection in courses:
            course_id = selection["id"]
            snapshot = {"course": courses_by_id[course_id], "parallel": selection["parallel"], "users": [], "error": ""}
            try:
                snapshot["users"] = await self._moodle.get_course_enrolled_users(course_id, refresh=True)
            except MoodleError:
                snapshot["error"] = "Moodle no permitió consultar los participantes. Revise conexión y permisos y vuelva a validar."
            snapshots.append(snapshot)
            if on_progress:
                on_progress(len(snapshots))
        return snapshots

    async def validate(self, *, period_code: int, courses: list[dict], actor: str) -> dict:
        academic = await asyncio.to_thread(self._load_academic, period_code)
        snapshots = await self.course_snapshots(courses)
        indexes = _identity_indexes(academic["registry"])
        codes = {r["student_code"] for r in academic["enrollments"]}
        for snapshot in snapshots:
            for user in snapshot["users"]:
                if _is_moodle_student(user):
                    _, _, candidates = _match_identity(user, *indexes)
                    codes.update(candidates)
        history, changes, warnings = await asyncio.to_thread(self._load_history, sorted(c for c in codes if c is not None), period_code)
        report = await asyncio.to_thread(compare_enrollments, **academic, history=history, career_changes=changes,
                                         snapshots=snapshots, actor=actor, warnings=warnings)
        return self.store_report(report, actor)

    def store_report(self, report: dict, actor: str) -> dict:
        report["report_id"] = str(uuid4())
        with self._lock:
            self._expire()
            while len(self._reports) >= 32:
                self._reports.pop(next(iter(self._reports)))
            self._reports[report["report_id"]] = (monotonic(), actor, report)
        return report

    def _expire(self) -> None:
        for key, (created, _, _) in list(self._reports.items()):
            if monotonic() - created >= 1800:
                self._reports.pop(key)

    def report(self, report_id: str, actor: str) -> dict:
        with self._lock:
            self._expire()
            cached = self._reports.get(report_id)
            if not cached or cached[1] != actor:
                raise HTTPException(404, "El reporte no está disponible o caducó. Ejecute nuevamente la validación.")
            return cached[2]
