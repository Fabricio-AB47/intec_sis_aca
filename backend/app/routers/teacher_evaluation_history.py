from datetime import datetime, timedelta, timezone
import re
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
import jwt
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.security import SessionUser, require_roles, require_screen_access
from app.routers import teacher_evaluation as evaluation
from app.services.db import get_connection, get_evaluation_connection
from app.services.teacher_evaluation_generation import (
    GENERATION_POLICY_VERSION,
    GENERATION_PREFIX,
    acquire_self_evaluation_lock,
    decode_generation_metadata,
    encode_generation_metadata,
    generate_self_evaluation_answers,
    generation_fingerprint,
)

router = APIRouter(
    prefix="/api/evaluacion-docente/admin/autoevaluaciones-historicas",
    tags=["evaluacion-docente"],
    dependencies=[Depends(require_roles(*evaluation._ADMIN_EVALUATION_ROLES))],
)
_ACCESS = require_screen_access("evaluacion-docente-historicas")
_SQL_SELECTION_CHUNK_SIZE = 500
_GENERATION_BATCH_SIZE = 100


class HistoricalSelfEvaluationSelection(BaseModel):
    periods: list[int] = Field(min_length=1)
    teachers: list[int] = Field(min_length=1)

    @field_validator("periods", "teachers")
    @classmethod
    def validate_selection(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values) or len(set(values)) != len(values):
            raise ValueError("Seleccione códigos positivos sin duplicados.")
        return sorted(values)


class HistoricalSelfEvaluationConfirm(BaseModel):
    preview_token: str = Field(min_length=1)
    confirmed: Literal[True]
    reason: str = Field(min_length=10, max_length=250)
    offset: int | None = Field(default=None, ge=0)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Registre un motivo de al menos 10 caracteres.")
        return value


def _historical_periods(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT p.cod_periodo AS codigo_periodo,
            LTRIM(RTRIM(p.Detalle_Periodo)) AS detalle_periodo,
            TRY_CONVERT(date, p.fechain) AS fecha_inicio
        FROM dbo.PERIODO p
        WHERE EXISTS (SELECT 1 FROM dbo.CARRERAXDOCENTE cxd WHERE cxd.codigo_periodo = p.cod_periodo)
        ORDER BY TRY_CONVERT(date, p.fechain), p.Orden, p.cod_periodo
        """
    )
    items = []
    for raw in cursor.fetchall():
        row = evaluation._row_dict(cursor, raw)
        date = str(row.get("fecha_inicio") or "")
        years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", date or str(row.get("detalle_periodo") or ""))
        year = int(years[0]) if years else 0
        if 2023 <= year <= 2025:
            items.append({"codigo_periodo": int(row["codigo_periodo"]), "detalle_periodo": row["detalle_periodo"], "year": year})
    return items


def _validate_periods(cursor: Any, periods: list[int]) -> list[dict[str, Any]]:
    available = {item["codigo_periodo"]: item for item in _historical_periods(cursor)}
    if any(period not in available for period in periods):
        raise HTTPException(status_code=400, detail="Solo se admiten períodos con inicio entre 2023 y 2025 y asignaciones docentes.")
    return [available[period] for period in periods]


def _active_teacher_condition(alias: str) -> str:
    return f"""EXISTS (
        SELECT 1 FROM dbo.USUARIOS teacher_user
        WHERE REPLACE(REPLACE(LTRIM(RTRIM(teacher_user.cedula)), '-', ''), ' ', '') =
              REPLACE(REPLACE(LTRIM(RTRIM({alias}.cedula_doc)), '-', ''), ' ', '')
          AND NULLIF(REPLACE(REPLACE(LTRIM(RTRIM({alias}.cedula_doc)), '-', ''), ' ', ''), '') IS NOT NULL
          AND {evaluation._active_state_condition("teacher_user.Estado")}
    )"""


def _historical_teachers(cursor: Any, teachers: list[int] | None = None, *, periods: list[int] | None = None) -> list[dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    teacher_chunks = _selection_chunks(teachers) if teachers is not None else [None]
    period_chunks = _selection_chunks(periods) if periods is not None else [None]
    for teacher_chunk in teacher_chunks:
        selection_condition = f"AND dd.codigo_doc IN ({evaluation._placeholders(teacher_chunk)})" if teacher_chunk is not None else ""
        for period_chunk in period_chunks:
            period_condition = f"AND cxd.codigo_periodo IN ({evaluation._placeholders(period_chunk)})" if period_chunk is not None else ""
            cursor.execute(
                f"""
                SELECT DISTINCT dd.codigo_doc AS codigo_doc,
                    LTRIM(RTRIM(dd.apellidos_nombre)) AS docente, LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
                    cxd.codigo_periodo AS codigo_periodo
                FROM dbo.DATOSDOCENTE dd
                INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_doc = dd.codigo_doc
                WHERE {_active_teacher_condition("dd")}
                  {selection_condition} {period_condition}
                ORDER BY LTRIM(RTRIM(dd.apellidos_nombre)), dd.codigo_doc, cxd.codigo_periodo
                """, *(teacher_chunk or []), *(period_chunk or []),
            )
            for raw in cursor.fetchall():
                row = evaluation._row_dict(cursor, raw)
                code = int(row["codigo_doc"])
                item = result.setdefault(code, {"codigo_doc": code, "docente": row["docente"], "cedula_doc": row["cedula_doc"], "periods": set()})
                item["periods"].add(int(row["codigo_periodo"]))
    return sorted(({**item, "periods": sorted(item["periods"])} for item in result.values()),
                  key=lambda item: (item["docente"], item["codigo_doc"]))


def _selection_chunks(values: list[int]) -> list[list[int]]:
    return [values[start:start + _SQL_SELECTION_CHUNK_SIZE] for start in range(0, len(values), _SQL_SELECTION_CHUNK_SIZE)]


def _validate_teachers(cursor: Any, teachers: list[int], periods: list[int]) -> None:
    available = {int(teacher["codigo_doc"]) for teacher in _historical_teachers(cursor, teachers, periods=periods)}
    if available != set(teachers):
        raise HTTPException(status_code=400, detail="La selección incluye docentes inactivos o sin clases asignadas en los períodos seleccionados. Actualice el catálogo y revise la selección.")


def _teacher_identity(course: dict[str, Any]) -> dict[str, Any]:
    cedula = evaluation._clean_text(course.get("cedula_docente")).replace("-", "").replace(" ", "")
    if not cedula:
        raise HTTPException(status_code=400, detail="El docente no tiene una cédula registrada. Actualice sus datos antes de generar la autoevaluación.")
    return {"teacher_code": int(course["codigo_docente_eval"]),
            "teacher_name": evaluation._clean_text(course.get("docente")), "teacher_cedula": cedula}


def _historical_courses(cursor: Any, periods: list[int], teachers: list[int]) -> list[dict[str, Any]]:
    rows = []
    for period_chunk in _selection_chunks(periods):
        for teacher_chunk in _selection_chunks(teachers):
            rows.extend(_historical_course_rows(cursor, period_chunk, teacher_chunk))
    grouped: dict[str, dict[str, Any]] = {}
    for raw in rows:
        course = evaluation._course_from_row(raw)
        key = generation_fingerprint([
            course["codigo_docente_eval"], course["codigo_periodo"],
            str(course.get("codigo_materia_interno") or course["codigo_materia"]).upper(),
            str(course.get("paralelo") or "").upper(), str(course.get("cod_jornada") or "").upper(),
        ])
        if key not in grouped:
            grouped[key] = {**course, "key": key, "codigos_materia_relacionados": [], "carreras_relacionadas": []}
        item = grouped[key]
        if course["codigo_materia"] not in item["codigos_materia_relacionados"]:
            item["codigos_materia_relacionados"].append(course["codigo_materia"])
        if course.get("carrera") and course["carrera"] not in item["carreras_relacionadas"]:
            item["carreras_relacionadas"].append(course["carrera"])
    result = list(grouped.values())
    for course in result:
        course["codigos_materia_relacionados"].sort()
        course["carreras_relacionadas"].sort()
        course["carrera"] = " / ".join(course["carreras_relacionadas"])
    return sorted(result, key=lambda course: course["key"])


def _historical_course_rows(cursor: Any, periods: list[int], teachers: list[int]) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT DISTINCT cxd.codigo_doc AS codigo_docente_eval,
            cxd.cod_Anio_Basica AS cod_anio_Basica, cxd.codigo_materia, cxd.codigo_periodo,
            LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo, per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel, LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
            CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
            'D' AS tipo_matricula, 0 AS respuestas_registradas
        FROM dbo.CARRERAXDOCENTE cxd
        INNER JOIN dbo.PERIODO per ON per.cod_periodo = cxd.codigo_periodo
        INNER JOIN dbo.PENSUM pen ON pen.codigo_materia = cxd.codigo_materia
            AND pen.Cod_AnioBasica = cxd.cod_Anio_Basica
        INNER JOIN dbo.CARRERAS car ON car.Cod_AnioBasica = cxd.cod_Anio_Basica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        WHERE cxd.codigo_periodo IN ({evaluation._placeholders(periods)})
          AND cxd.codigo_doc IN ({evaluation._placeholders(teachers)})
          AND {_active_teacher_condition("dd")}
          AND EXISTS (
            SELECT 1 FROM dbo.CARRERAXESTUD ce
            WHERE ce.codigo_periodo = cxd.codigo_periodo AND ce.codigo_materia = cxd.codigo_materia
              AND ce.cod_anio_Basica = cxd.cod_Anio_Basica
              AND LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) = LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20))))
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          )
        ORDER BY cxd.codigo_periodo, LTRIM(RTRIM(dd.apellidos_nombre)), cxd.codigo_materia
        """,
        *periods, *teachers,
    )
    return [evaluation._row_dict(cursor, row) for row in cursor.fetchall()]


def _generation_plan(academic_cursor: Any, evaluation_cursor: Any, selection: HistoricalSelfEvaluationSelection, seed: str) -> dict[str, Any]:
    periods = _validate_periods(academic_cursor, selection.periods)
    _validate_teachers(academic_cursor, selection.teachers, selection.periods)
    courses = _historical_courses(academic_cursor, selection.periods, selection.teachers)
    if not courses:
        raise HTTPException(status_code=400, detail="No existen materias finalizadas asignadas a los docentes y períodos seleccionados.")
    for course in courses:
        _teacher_identity(course)
    instrument, raw_questions = evaluation._fetch_question_rows(evaluation_cursor, "auto_docente")
    questions = [evaluation._question_from_row(evaluation._row_dict(evaluation_cursor, row)) for row in raw_questions]
    existing_index = _existing_self_evaluation_index(evaluation_cursor, selection.periods, instrument)
    items = []
    for course in courses:
        try:
            generated = generate_self_evaluation_answers(questions, seed, course["key"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        existing = _has_existing_self_evaluation(existing_index, course)
        items.append({"course": course, "status": "EXISTENTE" if existing else "PENDIENTE", **generated})
    fingerprint = generation_fingerprint({"periods": periods, "courses": courses, "instrument": instrument,
                                          "questions": questions, "generation_policy": GENERATION_POLICY_VERSION})
    return {"items": items, "instrument": instrument, "questions": questions, "fingerprint": fingerprint,
            "pending": sum(item["status"] == "PENDIENTE" for item in items), "existing": sum(item["status"] == "EXISTENTE" for item in items)}


def _existing_self_evaluation_index(cursor: Any, periods: list[int], instrument: dict[str, Any]) -> dict[tuple[int, int, int], set[tuple[str, str]]]:
    rows = []
    for chunk in _selection_chunks(periods):
        cursor.execute(
            f"""
            SELECT Cod_Periodo, Cod_Materia, Cod_Evaluador, Origen_Evaluador_Clave, Origen_Clave, Jornada, Paralelo
            FROM eval360.Aplicacion
            WHERE Id_Tipo_Evaluacion = ? AND Tipo_Evaluador = 'AUTO' AND Estado = 'FINALIZADA'
              AND Cod_Periodo IN ({evaluation._placeholders(chunk)})
            """, instrument["Id_Tipo_Evaluacion"], *[str(period) for period in chunk],
        )
        rows.extend(evaluation._row_dict(cursor, raw) for raw in cursor.fetchall())
    index: dict[tuple[int, int, int], set[tuple[str, str]]] = {}
    for row in rows:
        actors = {evaluation._safe_int(row.get("Cod_Evaluador")), evaluation._safe_int(row.get("Origen_Evaluador_Clave"))}
        origin_parts = str(row.get("Origen_Clave") or "").split("|")
        if len(origin_parts) >= 2 and origin_parts[0] == "auto_docente":
            actors.add(evaluation._safe_int(origin_parts[1]))
        for actor in actors - {0}:
            key = (actor, evaluation._safe_int(row["Cod_Periodo"]), evaluation._safe_int(row["Cod_Materia"]))
            index.setdefault(key, set()).add((str(row.get("Jornada") or "").strip().casefold(), str(row.get("Paralelo") or "").strip().casefold()))
    return index


def _has_existing_self_evaluation(index: dict[tuple[int, int, int], set[tuple[str, str]]], course: dict[str, Any]) -> bool:
    jornada = str(course.get("cod_jornada") or course.get("jornada") or "").strip().casefold()
    paralelo = str(course.get("paralelo") or "").strip().casefold()
    subjects = course.get("codigos_materia_relacionados") or [course["codigo_materia"]]
    for subject in subjects:
        sections = index.get((int(course["codigo_docente_eval"]), int(course["codigo_periodo"]), int(subject)), set())
        if any((not jornada or jornada == existing_jornada) and (not paralelo or paralelo == existing_parallel) for existing_jornada, existing_parallel in sections):
            return True
    return False


def _preview_token(user: SessionUser, selection: HistoricalSelfEvaluationSelection, seed: str, fingerprint: str, *, batch_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return str(jwt.encode({
        "sub": user.login, "actor_id": user.id_usuario, "actor_role": user.rol, "typ": "historical_self_evaluation_preview",
        "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "iat": now, "nbf": now,
        "exp": now + timedelta(minutes=30), "jti": batch_id or str(uuid.uuid4()),
        "selection": selection.model_dump(), "seed": seed, "fingerprint": fingerprint,
    }, settings.signing_secret, algorithm="HS256"))


def _decode_preview_token(token: str, user: SessionUser) -> dict[str, Any]:
    settings = get_settings()
    try:
        data = jwt.decode(token, settings.signing_secret, algorithms=["HS256"], issuer=settings.jwt_issuer,
                          audience=settings.jwt_audience, options={"require": ["sub", "exp", "iat", "nbf", "jti", "iss", "aud"]})
        if (data.get("typ") != "historical_self_evaluation_preview" or data["sub"] != user.login
                or data.get("actor_id") != user.id_usuario or data.get("actor_role") != user.rol):
            raise ValueError("actor")
        HistoricalSelfEvaluationSelection.model_validate(data["selection"])
        if not data.get("seed") or not data.get("fingerprint"):
            raise ValueError("preview")
        return data
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="La vista previa no es válida o expiró. Genérela nuevamente.") from exc


@router.get("/catalogo")
def get_historical_self_evaluation_catalog(current_user: SessionUser = Depends(_ACCESS)) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        periods = _historical_periods(cursor)
        teachers = _historical_teachers(cursor, periods=[period["codigo_periodo"] for period in periods])
    return {"periods": periods, "teachers": teachers, "max_applications": None, "max_teachers": None}


@router.post("/vista-previa")
def preview_historical_self_evaluations(selection: HistoricalSelfEvaluationSelection, current_user: SessionUser = Depends(_ACCESS)) -> dict[str, Any]:
    seed = str(uuid.uuid4())
    with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
        plan = _generation_plan(academic_conn.cursor(), evaluation_conn.cursor(), selection, seed)
    token = _preview_token(current_user, selection, seed, plan.pop("fingerprint"))
    return {**plan, "preview_token": token, "expires_in_minutes": 30}


@router.post("/generar")
def generate_historical_self_evaluations(payload: HistoricalSelfEvaluationConfirm, current_user: SessionUser = Depends(_ACCESS)) -> dict[str, Any]:
    preview = _decode_preview_token(payload.preview_token, current_user)
    selection = HistoricalSelfEvaluationSelection.model_validate(preview["selection"])
    created = []
    skipped = []
    batch_id = preview["jti"]
    with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
        cursor = evaluation_conn.cursor()
        try:
            acquire_self_evaluation_lock(cursor)
            plan = _generation_plan(academic_conn.cursor(), cursor, selection, preview["seed"])
            if plan["fingerprint"] != preview["fingerprint"]:
                raise HTTPException(status_code=409, detail="Las asignaciones, el instrumento o la regla de generación cambiaron. Genere una nueva vista previa.")
            total = len(plan["items"])
            start = payload.offset or 0
            if start > total:
                raise HTTPException(status_code=400, detail="La posición del proceso no corresponde a esta vista previa.")
            end = min(start + _GENERATION_BATCH_SIZE, total) if payload.offset is not None else total
            campaigns: dict[int, int] = {}
            for item in plan["items"][start:end]:
                course = item["course"]
                if item["status"] == "EXISTENTE":
                    skipped.append({"course": course, "status": "EXISTENTE"})
                    continue
                answers = [evaluation.TeacherEvaluationAnswer.model_validate(answer) for answer in item["answers"]]
                metadata = {"kind": "ADMINISTRATIVE_RANDOM_SELF_EVALUATION", "batch_id": batch_id,
                            "record_origin": "ADMINISTRATIVO", **_teacher_identity(course),
                            "actor_login": current_user.login, "actor_name": current_user.nombres,
                            "actor_role": current_user.rol,
                            "actor_user_id": current_user.id_usuario, "created_at": datetime.now(timezone.utc).isoformat(),
                            "reason": payload.reason, "score_10": item["score_10"], "instrument_id": plan["instrument"]["Id_Instrumento"],
                            "generation_policy": GENERATION_POLICY_VERSION}
                period = int(course["codigo_periodo"])
                if period not in campaigns:
                    campaigns[period] = evaluation._get_or_create_campaign(cursor, codigo_periodo=period,
                                                                          detalle_periodo=str(course["detalle_periodo"]), flow="auto_docente")
                campaign = campaigns[period]
                result = evaluation._save_application(
                    cursor, flow="auto_docente", instrument=plan["instrument"], campaign_id=campaign,
                    evaluator_code=int(course["codigo_docente_eval"]), evaluated_student_code=None,
                    course=dict(course), answers=answers, origin_table="INTECBDD.dbo.CARRERAXDOCENTE",
                    origin_evaluator_table="SISACA.AUTO_DOCENTE_GENERADA", origin_evaluated_table="INTECBDD.dbo.DATOSDOCENTE",
                    observation=encode_generation_metadata(metadata), bulk_answers=True,
                )
                created.append({"application_id": result["application_id"], "course": course, "score_10": item["score_10"], **metadata})
            evaluation_conn.commit()
        except Exception:
            evaluation_conn.rollback()
            raise
    next_offset = end if end < total else None
    next_token = _preview_token(current_user, selection, preview["seed"], preview["fingerprint"], batch_id=batch_id) if next_offset is not None else None
    return {"batch_id": batch_id, "created": len(created), "skipped": len(skipped), "items": created,
            "existing_items": skipped, "processed": end, "total": total, "next_offset": next_offset,
            "preview_token": next_token,
            "message": "Autoevaluaciones administrativas generadas e identificadas en los informes 360."}


@router.get("/historial")
def get_historical_self_evaluation_history(limit: int = Query(default=500, ge=1, le=2000), current_user: SessionUser = Depends(_ACCESS)) -> dict[str, Any]:
    with get_evaluation_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP {limit} a.Id_Aplicacion, a.Cod_Periodo, a.Cod_Materia,
                a.Cod_Docente_Evaluado, a.Paralelo, a.Fecha_Envio, a.Observacion_General
            FROM eval360.Aplicacion a
            WHERE LEFT(a.Observacion_General, ?) = ? AND a.Estado = 'FINALIZADA'
            ORDER BY a.Id_Aplicacion DESC
            """, len(GENERATION_PREFIX), GENERATION_PREFIX,
        )
        items = []
        for raw in cursor.fetchall():
            row = evaluation._row_dict(cursor, raw)
            metadata = decode_generation_metadata(row.pop("Observacion_General", None))
            if metadata:
                items.append({**row, **metadata, "record_origin": "ADMINISTRATIVO"})
    return {"items": items, "total": len(items)}
