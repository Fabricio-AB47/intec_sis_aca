from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import logging
from threading import Lock
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException

from app.integrations.moodle.exceptions import MoodleError
from app.services.moodle_academic_enrollment import _clean, _is_moodle_student
from app.services.moodle_enrollment_subjects import EnrollmentSubjectResolver
from app.services.moodle_enrollment_validation import (
    ACTIVE_STATES, STATUS_LABELS, MoodleEnrollmentValidationService, _identity_indexes, _match_identity,
    compare_enrollments,
)


logger = logging.getLogger(__name__)
ACADEMIC_SCOPE = (
    "Estudiantes activos matriculados en la carrera y período académicos seleccionados. "
    "Moodle devuelve matrículas activas en aulas accesibles a la integración. "
    "La coincidencia de materia no confirma el período del aula Moodle. "
    "Un aula no devuelta puede estar pendiente de apertura, inactiva o fuera de los permisos de consulta."
)
SELECTED_SCOPE = (
    "Estudiantes activos de la carrera y período seleccionados, comparados únicamente con las aulas "
    "y paralelos elegidos. Las demás materias se muestran como contexto, fuera de esta validación. "
    "La cohorte del aula debe corresponder al período elegido; no se deduce del código de materia. "
    "Consulta de solo lectura: no se modificaron matrículas."
)
LABELS = {**STATUS_LABELS, "MATERIA_MATRICULADA": "Materia matriculada en el período",
          "ANTECEDENTE_ACADEMICO": "Materia con matrícula en otro período",
          "SIN_AULA_ACTIVA": "Sin aula activa visible",
          "SIN_MATERIAS_ACADEMICAS": "Cabecera sin materias asignadas",
          "CUENTA_NO_ENCONTRADA": "Cuenta Moodle no encontrada",
          "OTRA_CARRERA_PERIODO": "Matriculada en otra carrera del período"}


def _key(row: dict) -> tuple:
    return row["career_code"], row["subject_id"]


def student_audit(*, person: dict, career: dict, period: dict, subjects: list[dict],
                  enrollments: list[dict], history: list[dict], changes: list[dict],
                  snapshots: list[dict], user: dict | None, problem: str = "", problem_detail: str = "",
                  resolver: EnrollmentSubjectResolver, headers: list[dict] | None = None) -> dict:
    current = [r for r in enrollments if r["student_code"] == person["student_code"]]
    academic = [r for r in current if r["career_code"] == career["code"]]
    past = [r for r in history if r["student_code"] == person["student_code"]]
    transitions = [r for r in changes if r["student_code"] == person["student_code"]]
    student_headers = [r for r in headers or [] if r["student_code"] == person["student_code"]]
    pensum = defaultdict(list)
    for subject in subjects:
        pensum[_key(subject)].append(subject)
    base = {
        "student_code": str(person["student_code"]), "student": _clean(person.get("student")),
        "document": _clean(person.get("document")), "email": ", ".join(sorted(person["emails"])),
        "moodle_email": _clean((user or {}).get("email")), "moodle_user_id": str((user or {}).get("id") or ""),
        "period": period["name"], "period_code": str(period["code"]), "academic_career": career["name"],
        "period_careers": ", ".join(sorted({_clean(r.get("career")) for r in [*current, *student_headers]})),
        "previous_careers": ", ".join(sorted({_clean(r.get("career")) for r in past} - {career["name"]})),
        "career_changes": "; ".join(f"{r['origin']} → {r['destination']} ({_clean(r.get('applied_at'))})" for r in transitions),
        "moodle_parallel": "*", "academic_parallel": "", "enrollment_periods": "",
        "subject_careers": "", "period_relation": "Período del aula Moodle no confirmado",
    }
    rows, courses, linked, unresolved = [], [], set(), set()
    for snapshot in snapshots:
        course = snapshot["course"]
        resolution = resolver.resolve(course)
        keys = {_key(r) for r in resolution.candidates}
        eligible = [r for r in academic if _key(r) in keys]
        other_current = [r for r in current if _key(r) in keys]
        historic = [r for r in past if _key(r) in keys]
        related = eligible or other_current or historic
        if resolution.error:
            status, reason = "SIN_PENSUM", resolution.error
            unresolved.update(keys)
        elif snapshot.get("error"):
            status, reason = "NO_VERIFICABLE", snapshot["error"]
            unresolved.update(keys)
        elif problem:
            status, reason = problem, problem_detail
            unresolved.update(keys)
        elif len(eligible) > 1:
            status, reason = "MATRICULA_DUPLICADA", "Hay varias matrículas de la materia en la carrera y período consultados."
            unresolved.update(keys)
        elif eligible:
            linked.update(keys)
            status = "SIN_CABECERA" if eligible[0].get("header_exists") == 0 else "MATERIA_MATRICULADA"
            reason = ("El estudiante está matriculado en esta materia de su carrera en el período seleccionado. "
                      "Verifique que la cohorte del aula Moodle corresponda al período académico." if status == "MATERIA_MATRICULADA"
                      else "La materia existe, pero no tiene cabecera para el mismo estudiante, carrera y período.")
        elif other_current:
            status, reason = "OTRA_CARRERA_PERIODO", "La materia está matriculada en otra carrera del mismo período; revise ambas matrículas."
        elif historic:
            status, reason = "ANTECEDENTE_ACADEMICO", "Existe matrícula de la materia en otro período. El aula puede ser un antecedente; no se considera automáticamente una matrícula incorrecta."
        elif any(r["career_code"] == career["code"] for r in resolution.candidates):
            status, reason = "SIN_MATRICULA_PERIODO", "La materia pertenece al pénsum de la carrera, pero no está matriculada en el período seleccionado."
        else:
            status, reason = "OTRA_CARRERA", "El código del aula corresponde al pénsum de otra carrera, sin matrícula académica relacionada del estudiante."
        row = {**base, "status": status, "status_label": LABELS[status], "reason": reason,
               "course_id": str(course["id"]), "course": _clean(course.get("fullname")),
               "moodle_code": _clean(course.get("shortname")), "moodle_idnumber": _clean(course.get("idnumber")),
               "subject_code": resolution.code, "subject": ", ".join(sorted({r["subject_name"] for r in resolution.candidates})),
               "code_candidates": resolution.code, "code_match": resolution.method, "code_match_detail": resolution.detail,
               "subject_careers": ", ".join(sorted({r["career_name"] for r in resolution.candidates})),
               "academic_parallel": ", ".join(sorted({_clean(r.get("parallel")) for r in related})),
               "enrollment_periods": "; ".join(sorted({f"{_clean(r.get('period'))} ({r['period_code']}) · {_clean(r.get('career'))}" for r in related}))}
        rows.append(row)
        courses.append(row)

    academic_subjects = []
    if not academic:
        status = problem or "SIN_MATERIAS_ACADEMICAS"
        rows.append({**base, "status": status, "status_label": LABELS[status],
                     "reason": problem_detail or "Existe cabecera de matrícula, pero no hay materias asignadas en CARRERAXESTUD para esta carrera y período.",
                     "course_id": "", "course": "", "moodle_code": "", "moodle_idnumber": "", "subject_code": "", "subject": "",
                     "code_candidates": "", "code_match": "Sin comparación", "code_match_detail": ""})
    for record in academic:
        key = _key(record)
        matches = pensum[key]
        item = {"subject_id": record["subject_id"], "subject_code": ", ".join(sorted({r["subject_code"] for r in matches})),
                "subject": ", ".join(sorted({r["subject_name"] for r in matches})) or f"Materia {record['subject_id']}",
                "semester": max((r.get("level") or 0 for r in matches), default=0),
                "parallel": _clean(record.get("parallel")), "period": period["name"], "period_code": str(period["code"]),
                "career": career["name"], "career_code": str(career["code"]), "linked": key in linked}
        academic_subjects.append(item)
        if key in linked:
            continue
        status = problem or ("SIN_PENSUM" if not matches else "NO_VERIFICABLE" if key in unresolved else "SIN_AULA_ACTIVA")
        rows.append({**base, "status": status, "status_label": LABELS[status],
                     "reason": problem_detail or ("No se encontró la materia y su código único en el pénsum de la carrera." if not matches else
                                                  "No se pudo confirmar el aula por errores o códigos ambiguos." if key in unresolved
                                                  else "No aparece un aula activa visible para esta materia; revise apertura modular, vigencia y permisos Moodle."),
                     "course_id": "", "course": "", "moodle_code": "", "moodle_idnumber": "",
                     "subject_code": item["subject_code"], "subject": item["subject"], "academic_parallel": item["parallel"],
                     "code_candidates": "", "code_match": "Sin comparación", "code_match_detail": "",
                     "enrollment_periods": f"{period['name']} ({period['code']})"})
    return {**base, "career_code": str(career["code"]), "rows": rows, "moodle_courses": courses,
            "academic_subjects": sorted(academic_subjects, key=lambda r: (r["semester"], r["subject"])),
            "findings": sum(r["status"] not in {"MATERIA_MATRICULADA", "ANTECEDENTE_ACADEMICO"} for r in rows),
            "query_error": problem_detail}


class MoodleAcademicValidationService:
    def __init__(self, validation: MoodleEnrollmentValidationService):
        self.validation = validation
        self._jobs: dict[str, dict] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = Lock()

    async def start(self, *, period_code: int, career_code: int, actor: str, courses: list[dict] | None = None) -> dict:
        selection = sorted(({"id": c["id"], "parallel": c["parallel"]} for c in courses), key=lambda c: c["id"]) if courses is not None else None
        if selection is not None and (not selection or len(selection) > 100 or len({c["id"] for c in selection}) != len(selection)):
            raise HTTPException(422, "Seleccione de 1 a 100 cursos distintos.")
        with self._lock:
            self._jobs = {key: job for key, job in self._jobs.items()
                          if job["status"] == "running" or monotonic() - job["updated"] < 1800}
            for job in self._jobs.values():
                if job["actor"] == actor and job["status"] == "running":
                    if (job["period_code"], job["career_code"], job.get("courses")) == (period_code, career_code, selection):
                        return self._public(job)
                    raise HTTPException(409, "Ya tiene una validación en curso. Espere a que termine.")
            if sum(job["status"] == "running" for job in self._jobs.values()) >= 4:
                raise HTTPException(409, "Hay varias validaciones en curso. Inténtelo nuevamente al finalizar.")
            while len(self._jobs) >= 32:
                oldest = next(key for key, job in self._jobs.items() if job["status"] != "running")
                del self._jobs[oldest]
            job_id = str(uuid4())
            job = {"job_id": job_id, "actor": actor, "period_code": period_code, "career_code": career_code,
                   "courses": selection, "unit": "courses" if selection is not None else "students",
                   "status": "running", "processed": 0, "total": 0, "error": "", "report": None, "updated": monotonic()}
            self._jobs[job_id] = job
        task = asyncio.create_task(self._run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return self._public(job)

    @staticmethod
    def _public(job: dict) -> dict:
        return {key: job[key] for key in ("job_id", "status", "processed", "total", "error", "report", "unit")}

    def get(self, job_id: str, actor: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["actor"] != actor or (job["status"] != "running" and monotonic() - job["updated"] >= 1800):
                raise HTTPException(404, "La validación no está disponible. Vuelva a ejecutarla.")
            return self._public(job)

    def _update(self, job_id: str, **values) -> None:
        with self._lock:
            self._jobs[job_id].update(values, updated=monotonic())

    async def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            await self._scan(job)
        except asyncio.CancelledError:
            self._update(job_id, status="error", error="La consulta fue interrumpida. Vuelva a ejecutarla.")
            raise
        except HTTPException as exc:
            self._update(job_id, status="error", error=str(exc.detail))
        except Exception:
            logger.exception("Academic Moodle audit failed job_id=%s", job_id)
            self._update(job_id, status="error", error="No se pudo completar la consulta. Revise la conexión y los permisos Moodle de usuarios y cursos; puede volver a intentar.")

    async def _scan(self, job: dict) -> None:
        academic = await asyncio.to_thread(self.validation._load_academic, job["period_code"])
        headers = await asyncio.to_thread(self.validation._load_enrollment_headers, job["period_code"])
        selected = [r for r in [*academic["enrollments"], *headers] if r["career_code"] == job["career_code"]]
        if not selected:
            self._update(job["job_id"], status="error", error="No hay matrículas para esa carrera y período.")
            return
        career = {"code": job["career_code"], "name": _clean(selected[0]["career"])}
        indexes = _identity_indexes(academic["registry"])
        people = indexes[0]
        codes = sorted({r["student_code"] for r in selected if r["student_code"] in people
                        and people[r["student_code"]]["states"] & ACTIVE_STATES}, key=lambda code: _clean(people[code]["student"]))
        if job.get("courses") is not None:
            await self._scan_selected(job, academic, headers, career, codes, people, selected)
            return
        self._update(job["job_id"], total=len(codes))
        users_by_student, ambiguous = defaultdict(list), set()
        if codes:
            directory = await self.validation._moodle.get_all_users(refresh=True)
            for user in {u["id"]: u for u in directory}.values():
                code, status, possible = _match_identity(user, *indexes)
                if code is None:
                    ambiguous.update(possible)
                elif status != "INACTIVO":
                    users_by_student[code].append(user)
        history, changes, warnings = await asyncio.to_thread(self.validation._load_history, codes, job["period_code"])
        resolver = EnrollmentSubjectResolver(academic["subjects"])
        participants, students, scope = {}, [], {}
        for index, code in enumerate(codes):
            accounts, snapshots, problem, detail = users_by_student[code], [], "", ""
            user = accounts[0] if len(accounts) == 1 and code not in ambiguous else None
            if code in ambiguous or len(accounts) > 1 or people[code]["states"] - ACTIVE_STATES:
                problem, detail = "IDENTIDAD_AMBIGUA", "Revise las cuentas e identidades duplicadas o contradictorias; no se eligió una cuenta por semejanza."
            elif not user:
                problem, detail = "CUENTA_NO_ENCONTRADA", "No se encontró una cuenta Moodle por correo institucional o documento exacto."
            else:
                if user.get("suspended") or not user.get("confirmed", True):
                    problem, detail = "SUSPENDIDO_MOODLE", "La cuenta Moodle está suspendida o sin confirmar."
                try:
                    user_courses = await self.validation._moodle.get_user_courses(user["id"])
                    for course in {c["id"]: c for c in user_courses}.values():
                        course_id = course["id"]
                        if course_id not in participants:
                            try:
                                participants[course_id] = {u["id"]: u for u in await self.validation._moodle.get_course_enrolled_users(course_id, refresh=True)}
                            except MoodleError:
                                participants[course_id] = {}
                        member = participants[course_id].get(user["id"])
                        error = "" if member and _is_moodle_student(member) else "No se pudo confirmar el rol de estudiante en esta aula Moodle."
                        snapshots.append({"course": course, "error": error})
                        scope[course_id] = {"id": course_id, "name": course["fullname"], "parallel": "*",
                                            "subject_code": "", "error": ""}
                except MoodleError:
                    problem, detail = "NO_VERIFICABLE", "No se pudieron consultar los cursos activos. Verifique que core_enrol_get_users_courses esté habilitada y que la integración tenga permisos."
            audit = await asyncio.to_thread(student_audit, person=people[code], career=career, period=academic["period"],
                                           subjects=academic["subjects"], enrollments=academic["enrollments"],
                                           history=history, changes=changes, snapshots=snapshots, user=user,
                                           problem=problem, problem_detail=detail, resolver=resolver, headers=headers)
            students.append(audit)
            for row in audit["moodle_courses"]:
                scope[int(row["course_id"])].update(subject_code=row["subject_code"], code_match=row["code_match"], code_match_detail=row["code_match_detail"])
            self._update(job["job_id"], processed=index + 1)
        rows = [row for student in students for row in student["rows"]]
        report = {"mode": "academic", "career": career, "period": academic["period"], "students": students,
                  "generated_at": datetime.now(timezone.utc).isoformat(), "actor": job["actor"],
                  "scope": list(scope.values()), "scope_text": ACADEMIC_SCOPE, "warnings": [ACADEMIC_SCOPE, *warnings], "rows": rows,
                  "summary": {"rows": len(rows), "students": len(students), "matches": sum(r["status"] == "MATERIA_MATRICULADA" for r in rows),
                              "findings": sum(s["findings"] for s in students),
                              "inactive": len({r["student_code"] for r in selected if r["student_code"] in people and not people[r["student_code"]]["states"] & ACTIVE_STATES}),
                              "career_history": sum(bool(s["previous_careers"]) for s in students)}}
        report = self.validation.store_report(report, job["actor"])
        self._update(job["job_id"], status="completed", report=report)

    async def _scan_selected(self, job: dict, academic: dict, headers: list[dict], career: dict,
                             codes: list[int], people: dict, selected: list[dict]) -> None:
        self._update(job["job_id"], total=len(job["courses"]))
        snapshots = await self.validation.course_snapshots(
            job["courses"], lambda processed: self._update(job["job_id"], processed=processed))
        history, changes, warnings = await asyncio.to_thread(self.validation._load_history, codes, job["period_code"])
        report = await asyncio.to_thread(selected_course_audit, academic=academic, headers=headers, career=career,
                                        codes=codes, people=people, history=history, changes=changes,
                                        snapshots=snapshots, actor=job["actor"], warnings=warnings)
        report["summary"]["inactive"] = len({r["student_code"] for r in selected if r["student_code"] in people
                                             and not people[r["student_code"]]["states"] & ACTIVE_STATES})
        report = self.validation.store_report(report, job["actor"])
        self._update(job["job_id"], status="completed", report=report)


def selected_course_audit(*, academic: dict, headers: list[dict], career: dict, codes: list[int], people: dict,
                          history: list[dict], changes: list[dict], snapshots: list[dict], actor: str,
                          warnings: list[str]) -> dict:
    # Reuse the bidirectional comparison: absence is evaluated only inside the selected scope.
    report = compare_enrollments(**academic, history=history, career_changes=changes, snapshots=snapshots,
                                 actor=actor, warnings=warnings, career_code=career["code"], student_codes=set(codes))
    resolver = EnrollmentSubjectResolver(academic["subjects"])
    scopes = {snapshot["course"]["id"]: (resolver.resolve(snapshot["course"]), snapshot["parallel"]) for snapshot in snapshots}
    by_student = defaultdict(list)
    for row in report["rows"]:
        by_student[row["student_code"]].append(row)
        resolution = scopes[int(row["course_id"])][0]
        keys = {_key(candidate) for candidate in resolution.candidates}
        related = [r for r in [*academic["enrollments"], *history]
                   if str(r["student_code"]) == row["student_code"] and _key(r) in keys]
        row.update(subject_careers=", ".join(sorted({r["career_name"] for r in resolution.candidates})),
                   enrollment_periods="; ".join(sorted({f"{_clean(r.get('period'))} ({r['period_code']}) · {_clean(r.get('career'))}" for r in related})),
                   period_relation="Aula seleccionada para contrastar con el período académico; cohorte no inferida del código.")
    students = []
    for code in codes:
        audit = student_audit(person=people[code], career=career, period=academic["period"],
                              subjects=academic["subjects"], enrollments=academic["enrollments"],
                              history=history, changes=changes, snapshots=[], user=None, resolver=resolver, headers=headers)
        rows = by_student[str(code)]
        if not audit["academic_subjects"]:
            rows.extend(audit["rows"])
            report["rows"].extend(audit["rows"])
        for subject in audit["academic_subjects"]:
            key = (career["code"], subject["subject_id"])
            subject["in_scope"] = any(key in {_key(r) for r in resolution.candidates}
                                       and (parallel == "*" or parallel == _clean(subject["parallel"]).upper())
                                       for resolution, parallel in scopes.values())
            subject["linked"] = any(row["status"] == "COINCIDE" and row.get("academic_subject_id") == key[1]
                                     and row.get("academic_career_code") == key[0]
                                     and _clean(row["academic_parallel"]).upper() == _clean(subject["parallel"]).upper() for row in rows)
        audit.update(rows=rows, moodle_courses=[r for r in rows if r["moodle_user_id"]],
                     findings=sum(r["status"] != "COINCIDE" for r in rows),
                     evaluated_subjects=sum(s["in_scope"] for s in audit["academic_subjects"]))
        students.append(audit)
    report.update(mode="academic", course_selection=True, career=career, students=students, scope_text=SELECTED_SCOPE,
                  warnings=[SELECTED_SCOPE, *warnings])
    unattributed = sum(not r["student_code"] for r in report["rows"])
    if unattributed:
        report["warnings"].append(f"Hay {unattributed} hallazgo(s) de curso o identidad sin estudiante confirmado. Revise el detalle por materia.")
    report["summary"].update(rows=len(report["rows"]), students=len(students),
                             findings=sum(r["status"] != "COINCIDE" for r in report["rows"]),
                             career_history=sum(bool(s["previous_careers"] or s["career_changes"]) for s in students))
    return report
