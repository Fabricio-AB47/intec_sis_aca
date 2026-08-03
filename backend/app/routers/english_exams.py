from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import SessionUser, get_current_user, require_roles
from app.services.db import get_connection, get_expedient_connection, get_titulation_connection
from app.services.graph import get_graph_token
from app.services.graph_documents import (
    complete_upload_session as complete_graph_document_upload,
    mark_upload_error as mark_graph_document_upload_error,
    prepare_expedient as prepare_graph_expedient,
    register_upload_session as register_graph_document_upload,
    set_document_origin as set_graph_document_origin,
)
from app.services.grade_calculation import calculate_regular_grade_with_recovery


router = APIRouter(prefix="/api/english", tags=["english"])

_MIN_FILE_BYTES = 50 * 1024 * 1024
_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
_EDIT_WINDOW_MINUTES = 15
_PASSING_GRADE = Decimal("7.00")
_LEVEL_NAME = "A2+ - INTERMEDIATE"
_LOCAL_TIMEZONE = ZoneInfo("America/Guayaquil")
_RUBRIC_WEIGHTS: dict[str, Decimal] = {
    "language_mastery": Decimal("0.30"),
    "fluency_pronunciation": Decimal("0.30"),
    "content_coherence": Decimal("0.25"),
    "instruction_compliance": Decimal("0.15"),
}
_ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
}

_STUDENT_ACCESS = require_roles("ESTUDIANTE")
_REVIEWER_ACCESS = require_roles("DOCENTE", "ACADEMICO", "ADMINISTRADOR")

_TEACHER_ENROLLMENT_SCOPE_SQL = """
    EXISTS
    (
        SELECT 1
        FROM INTECBDD.dbo.CARRERAXDOCENTE cxd
        INNER JOIN INTECBDD.dbo.CARRERAS carrera_docente
            ON TRY_CONVERT(INT, carrera_docente.Cod_AnioBasica) = TRY_CONVERT(INT, cxd.cod_Anio_Basica)
        WHERE TRY_CONVERT(INT, cxd.codigo_doc) = ?
          AND TRY_CONVERT(INT, cxd.cod_Anio_Basica) = TRY_CONVERT(INT, e.CodigoCarrera)
          AND TRY_CONVERT(INT, cxd.codigo_materia) = TRY_CONVERT(INT, e.CodigoMateria)
          AND TRY_CONVERT(INT, cxd.codigo_periodo) = TRY_CONVERT(INT, e.CodigoPeriodo)
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_docente.tp_escuela)))) = N'IDIOMA'
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cxd.Paralelo)))) =
              UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), e.Paralelo))))
    )
    AND EXISTS
    (
        SELECT 1
        FROM INTECBDD.dbo.CARRERAXESTUD cxe
        WHERE TRY_CONVERT(BIGINT, cxe.num) = TRY_CONVERT(BIGINT, e.CarreraXEstudNum)
          AND TRY_CONVERT(BIGINT, cxe.codigo_estud) = TRY_CONVERT(BIGINT, e.CodigoEstud)
          AND TRY_CONVERT(INT, cxe.cod_anio_Basica) = TRY_CONVERT(INT, e.CodigoCarrera)
          AND TRY_CONVERT(INT, cxe.codigo_materia) = TRY_CONVERT(INT, e.CodigoMateria)
          AND TRY_CONVERT(INT, cxe.codigo_periodo) = TRY_CONVERT(INT, e.CodigoPeriodo)
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cxe.Paralelo)))) =
              UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), e.Paralelo))))
    )
"""

_TEACHER_ACTIVE_ENGLISH_SCOPE_SQL = """
    EXISTS
    (
        SELECT 1
        FROM INTECBDD.dbo.CARRERAXDOCENTE cxd
        INNER JOIN INTECBDD.dbo.CARRERAS carrera_docente
            ON TRY_CONVERT(INT, carrera_docente.Cod_AnioBasica) = TRY_CONVERT(INT, cxd.cod_Anio_Basica)
        WHERE TRY_CONVERT(INT, cxd.codigo_doc) = ?
          AND TRY_CONVERT(INT, cxd.cod_Anio_Basica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
          AND TRY_CONVERT(INT, cxd.codigo_materia) = TRY_CONVERT(INT, cx.codigo_materia)
          AND TRY_CONVERT(INT, cxd.codigo_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_docente.tp_escuela)))) = N'IDIOMA'
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cxd.Paralelo)))) =
              UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cx.Paralelo))))
    )
"""


class UploadSessionPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=_MIN_FILE_BYTES, le=_MAX_FILE_BYTES)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    component_code: str = Field(default="P1", min_length=1, max_length=20)


class UploadFinalizePayload(BaseModel):
    upload_id: UUID


class UploadConfirmPayload(BaseModel):
    upload_id: UUID
    component_code: str = Field(default="P1", min_length=1, max_length=20)


class GradePayload(BaseModel):
    grade: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    observation: str = Field(default="", max_length=1500)
    component_code: str = Field(default="P1", min_length=1, max_length=20)
    period_code: str = Field(min_length=1, max_length=100)


class RubricDraftPayload(BaseModel):
    language_mastery: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    fluency_pronunciation: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    content_coherence: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    instruction_compliance: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    observation: str = Field(default="", max_length=1500)
    component_code: str = Field(default="P1", min_length=1, max_length=20)
    period_code: str = Field(min_length=1, max_length=100)


class PublishGradePayload(BaseModel):
    component_code: str = Field(default="P1", min_length=1, max_length=20)
    period_code: str = Field(min_length=1, max_length=100)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _reviewer_scope_filter(current_user: SessionUser) -> tuple[str | None, list[Any]]:
    if current_user.rol != "DOCENTE":
        return None, []
    if current_user.codigo_doc is None:
        return "1 = 0", []
    return _TEACHER_ENROLLMENT_SCOPE_SQL, [current_user.codigo_doc]


def _require_teacher_exam_scope(
    cursor: Any,
    exam_id: int,
    current_user: SessionUser,
) -> None:
    if current_user.rol != "DOCENTE":
        return
    if current_user.codigo_doc is None:
        raise HTTPException(status_code=403, detail="La sesión docente no contiene un código válido.")
    cursor.execute(
        f"""
        SELECT TOP (1) 1
        FROM ing.ExamenIngles e
        INNER JOIN exp.ExpedienteEstudiantil ex
            ON ex.ExpedienteEstudiantilId = e.ExpedienteEstudiantilId
        WHERE e.ExamenInglesId = ?
          AND e.Activo = 1
          AND {_TEACHER_ENROLLMENT_SCOPE_SQL}
        """,
        exam_id,
        current_user.codigo_doc,
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=403,
            detail="El estudiante no pertenece a una carrera y período asignados al docente.",
        )


def _period_label(code: str, detail: str) -> str:
    if not detail or detail == code:
        return code
    if detail.upper().startswith(code.upper()):
        return detail
    return f"{code} - {detail}"


def _reviewer_periods(cursor: Any, current_user: SessionUser) -> list[dict[str, Any]]:
    if current_user.rol == "DOCENTE" and current_user.codigo_doc is None:
        return []

    enrollment_filters = [
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), d.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.tp_escuela)))) = N'IDIOMA'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), periodo.Estado)))) = N'A'",
        "(periodo.fechain IS NULL OR periodo.fechain <= CONVERT(DATE, GETDATE()))",
        "(periodo.fechafin IS NULL OR periodo.fechafin >= CONVERT(DATE, GETDATE()))",
        "TRY_CONVERT(BIGINT, cx.num) IS NOT NULL",
    ]
    enrollment_params: list[Any] = []
    if current_user.rol == "DOCENTE":
        enrollment_filters.append(_TEACHER_ACTIVE_ENGLISH_SCOPE_SQL)
        enrollment_params.append(current_user.codigo_doc)

    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo) AS codigo_periodo,
            COALESCE(
                NULLIF(MAX(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), periodo.Detalle_Periodo)))), N''),
                TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo)
            ) AS detalle_periodo,
            MAX(COALESCE(
                TRY_CONVERT(INT, periodo.Orden),
                TRY_CONVERT(INT, periodo.cod_periodo),
                TRY_CONVERT(INT, cx.codigo_periodo),
                0
            )) AS periodo_orden,
            COUNT(DISTINCT TRY_CONVERT(BIGINT, cx.codigo_estud)) AS total_estudiantes
        FROM INTECBDD.dbo.CARRERAXESTUD cx
        INNER JOIN INTECBDD.dbo.DATOS_ESTUD d
            ON TRY_CONVERT(BIGINT, d.codigo_estud) = TRY_CONVERT(BIGINT, cx.codigo_estud)
        INNER JOIN INTECBDD.dbo.CARRERAS carrera_ingles
            ON TRY_CONVERT(INT, carrera_ingles.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
        INNER JOIN INTECBDD.dbo.PENSUM pensum
            ON TRY_CONVERT(INT, pensum.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
           AND TRY_CONVERT(INT, pensum.codigo_materia) = TRY_CONVERT(INT, cx.codigo_materia)
        INNER JOIN INTECBDD.dbo.PERIODO periodo
            ON TRY_CONVERT(INT, periodo.cod_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
        WHERE {" AND ".join(enrollment_filters)}
        GROUP BY TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo)
        """,
        *enrollment_params,
    )
    period_map: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        code = _clean(row.codigo_periodo)
        detail = _clean(row.detalle_periodo)
        period_map[code] = {
            "code": code,
            "name": detail or code,
            "label": _period_label(code, detail),
            "student_count": int(row.total_estudiantes or 0),
            "sort_order": int(row.periodo_orden or 0),
        }

    periods = sorted(
        period_map.values(),
        key=lambda item: (int(item["sort_order"]), _clean(item["code"])),
        reverse=True,
    )
    for item in periods:
        item.pop("sort_order", None)
    return periods


def _select_reviewer_period(
    periods: list[dict[str, Any]],
    requested_period: str,
    current_user: SessionUser,
) -> str:
    requested = _clean(requested_period)
    available = {_clean(item.get("code")) for item in periods}
    if requested:
        if requested not in available:
            raise HTTPException(
                status_code=403 if current_user.rol == "DOCENTE" else 400,
                detail="El período de Inglés no está disponible para el perfil autenticado.",
            )
        return requested
    return _clean(periods[0].get("code")) if periods else ""


def _reviewer_subjects(
    cursor: Any,
    selected_period: str,
    current_user: SessionUser,
) -> list[dict[str, Any]]:
    if not selected_period:
        return []
    if current_user.rol == "DOCENTE" and current_user.codigo_doc is None:
        return []

    filters = [
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), d.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.tp_escuela)))) = N'IDIOMA'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), periodo.Estado)))) = N'A'",
        "(periodo.fechain IS NULL OR periodo.fechain <= CONVERT(DATE, GETDATE()))",
        "(periodo.fechafin IS NULL OR periodo.fechafin >= CONVERT(DATE, GETDATE()))",
        "TRY_CONVERT(BIGINT, cx.num) IS NOT NULL",
        "LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo))) = ?",
    ]
    params: list[Any] = [selected_period]
    if current_user.rol == "DOCENTE":
        filters.append(_TEACHER_ACTIVE_ENGLISH_SCOPE_SQL)
        params.append(current_user.codigo_doc)

    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(NVARCHAR(100), cx.codigo_materia) AS codigo_materia,
            COALESCE(
                NULLIF(MAX(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pensum.Nomb_Materia)))), N''),
                CONCAT(N'Asignatura ', TRY_CONVERT(NVARCHAR(100), cx.codigo_materia))
            ) AS nombre_materia,
            COUNT(DISTINCT TRY_CONVERT(BIGINT, cx.codigo_estud)) AS total_estudiantes
        FROM INTECBDD.dbo.CARRERAXESTUD cx
        INNER JOIN INTECBDD.dbo.DATOS_ESTUD d
            ON TRY_CONVERT(BIGINT, d.codigo_estud) = TRY_CONVERT(BIGINT, cx.codigo_estud)
        INNER JOIN INTECBDD.dbo.CARRERAS carrera_ingles
            ON TRY_CONVERT(INT, carrera_ingles.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
        INNER JOIN INTECBDD.dbo.PENSUM pensum
            ON TRY_CONVERT(INT, pensum.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
           AND TRY_CONVERT(INT, pensum.codigo_materia) = TRY_CONVERT(INT, cx.codigo_materia)
        INNER JOIN INTECBDD.dbo.PERIODO periodo
            ON TRY_CONVERT(INT, periodo.cod_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
        WHERE {" AND ".join(filters)}
        GROUP BY TRY_CONVERT(NVARCHAR(100), cx.codigo_materia)
        ORDER BY codigo_materia, nombre_materia
        """,
        *params,
    )
    return [
        {
            "code": _clean(row.codigo_materia),
            "name": _clean(row.nombre_materia),
            "label": f"{_clean(row.nombre_materia)} · código {_clean(row.codigo_materia)}",
            "student_count": int(row.total_estudiantes or 0),
        }
        for row in cursor.fetchall()
    ]


def _select_reviewer_subject(
    subjects: list[dict[str, Any]],
    requested_subject: str,
    current_user: SessionUser,
) -> str:
    requested = _clean(requested_subject)
    available = {_clean(item.get("code")) for item in subjects}
    if requested:
        if requested not in available:
            raise HTTPException(
                status_code=403 if current_user.rol == "DOCENTE" else 400,
                detail="La asignatura de Idiomas no está disponible para el perfil autenticado.",
            )
        return requested
    return _clean(subjects[0].get("code")) if subjects else ""


def _reviewer_enrollments(
    cursor: Any,
    selected_period: str,
    selected_subject: str,
    current_user: SessionUser,
    search: str = "",
) -> list[dict[str, Any]]:
    if not selected_period or not selected_subject:
        return []
    if current_user.rol == "DOCENTE" and current_user.codigo_doc is None:
        return []

    filters = [
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), d.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.tp_escuela)))) = N'IDIOMA'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), periodo.Estado)))) = N'A'",
        "(periodo.fechain IS NULL OR periodo.fechain <= CONVERT(DATE, GETDATE()))",
        "(periodo.fechafin IS NULL OR periodo.fechafin >= CONVERT(DATE, GETDATE()))",
        "TRY_CONVERT(BIGINT, cx.num) IS NOT NULL",
        "LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo))) = ?",
        "TRY_CONVERT(INT, cx.codigo_materia) = TRY_CONVERT(INT, ?)",
    ]
    params: list[Any] = [selected_period, selected_subject]
    if current_user.rol == "DOCENTE":
        filters.append(_TEACHER_ACTIVE_ENGLISH_SCOPE_SQL)
        params.append(current_user.codigo_doc)
    term = _clean(search)
    if term:
        filters.append(
            "(d.Apellidos_nombre LIKE ? OR d.Cedula_Est LIKE ? "
            "OR TRY_CONVERT(NVARCHAR(40), d.codigo_estud) LIKE ?)"
        )
        pattern = f"%{term}%"
        params.extend([pattern, pattern, pattern])

    cursor.execute(
        f"""
        WITH matriculas_ingles AS
        (
            SELECT
                TRY_CONVERT(BIGINT, d.codigo_estud) AS codigo_estud,
                LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), d.Cedula_Est))) AS cedula,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), d.Apellidos_nombre))) AS estudiante,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), d.correo))) AS correo,
                TRY_CONVERT(BIGINT, cx.num) AS carrera_x_estud_num,
                TRY_CONVERT(INT, cx.cod_anio_Basica) AS codigo_carrera,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), carrera_ingles.Nombre_Basica))) AS carrera_ingles,
                TRY_CONVERT(INT, cx.codigo_materia) AS codigo_materia,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pensum.Nomb_Materia))) AS nivel_ingles,
                TRY_CONVERT(INT, cx.codigo_periodo) AS codigo_periodo,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), periodo.Detalle_Periodo))) AS detalle_periodo,
                TRY_CONVERT(DATE, periodo.fechain) AS fecha_inicio_periodo,
                TRY_CONVERT(DATE, periodo.fechafin) AS fecha_fin_periodo,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cx.Paralelo))) AS paralelo,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), cx.TipoMatricula))) AS tipo_matricula,
                carrera_principal.codigo_carrera_principal,
                COALESCE(carrera_principal.carrera_principal, carrera_ingles.Nombre_Basica) AS carrera,
                ROW_NUMBER() OVER
                (
                    PARTITION BY TRY_CONVERT(BIGINT, d.codigo_estud)
                    ORDER BY cx.Fecha_Matricula DESC, TRY_CONVERT(BIGINT, cx.num) DESC
                ) AS numero_fila
            FROM INTECBDD.dbo.CARRERAXESTUD cx
            INNER JOIN INTECBDD.dbo.DATOS_ESTUD d
                ON TRY_CONVERT(BIGINT, d.codigo_estud) = TRY_CONVERT(BIGINT, cx.codigo_estud)
            INNER JOIN INTECBDD.dbo.CARRERAS carrera_ingles
                ON TRY_CONVERT(INT, carrera_ingles.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
            INNER JOIN INTECBDD.dbo.PENSUM pensum
                ON TRY_CONVERT(INT, pensum.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
               AND TRY_CONVERT(INT, pensum.codigo_materia) = TRY_CONVERT(INT, cx.codigo_materia)
            INNER JOIN INTECBDD.dbo.PERIODO periodo
                ON TRY_CONVERT(INT, periodo.cod_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
            OUTER APPLY
            (
                SELECT TOP (1)
                    TRY_CONVERT(INT, carrera.Cod_AnioBasica) AS codigo_carrera_principal,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), carrera.Nombre_Basica))) AS carrera_principal
                FROM INTECBDD.dbo.CARRERAXESTUD matricula
                INNER JOIN INTECBDD.dbo.CARRERAS carrera
                    ON TRY_CONVERT(INT, carrera.Cod_AnioBasica) = TRY_CONVERT(INT, matricula.cod_anio_Basica)
                WHERE TRY_CONVERT(BIGINT, matricula.codigo_estud) = TRY_CONVERT(BIGINT, d.codigo_estud)
                  AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(NVARCHAR(30), carrera.tp_escuela), N'')))) <> N'IDIOMA'
                ORDER BY TRY_CONVERT(INT, matricula.codigo_periodo) DESC,
                         matricula.Fecha_Matricula DESC,
                         TRY_CONVERT(BIGINT, matricula.num) DESC
            ) carrera_principal
            WHERE {" AND ".join(filters)}
        )
        SELECT
            codigo_estud, cedula, estudiante, correo, carrera_x_estud_num,
            codigo_carrera, carrera_ingles, codigo_materia, nivel_ingles,
            codigo_periodo, detalle_periodo, fecha_inicio_periodo, fecha_fin_periodo,
            paralelo, tipo_matricula,
            codigo_carrera_principal, carrera
        FROM matriculas_ingles
        WHERE numero_fila = 1
        ORDER BY estudiante, codigo_estud
        """,
        *params,
    )
    profiles: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        profiles.append(
            {
                "codigo_estud": int(row.codigo_estud),
                "cedula": _clean(row.cedula),
                "estudiante": _clean(row.estudiante),
                "correo": _clean(row.correo),
                "carrera_x_estud_num": int(row.carrera_x_estud_num),
                "codigo_carrera": int(row.codigo_carrera),
                "carrera_ingles": _clean(row.carrera_ingles),
                "codigo_materia": int(row.codigo_materia),
                "nivel": _clean(row.nivel_ingles) or _LEVEL_NAME,
                "carrera": _clean(row.carrera),
                "codigo_carrera_principal": _clean(row.codigo_carrera_principal),
                "codigo_periodo": int(row.codigo_periodo),
                "detalle_periodo": _clean(row.detalle_periodo),
                "fecha_inicio_periodo": getattr(row, "fecha_inicio_periodo", None),
                "fecha_fin_periodo": getattr(row, "fecha_fin_periodo", None),
                "paralelo": _clean(row.paralelo),
                "tipo_matricula": _normalize_enrollment_type(row.tipo_matricula),
            }
        )
    return profiles


def _normalize_enrollment_type(*values: Any) -> str:
    normalized = [
        _clean(value).upper().replace("Ó", "O")
        for value in values
        if _clean(value)
    ]
    if any(value == "H" or "HOMO" in value for value in normalized):
        return "H"
    return "R"


def _component_specs(enrollment_type: str) -> list[dict[str, Any]]:
    return [
        {"code": f"P{number}", "number": number, "label": f"Parcial {number}", "evaluation_type": "EXAMEN"}
        for number in range(1, 4)
    ]


def _aggregate_component_grade(enrollment_type: str, grades: dict[str, Any]) -> Decimal | None:
    required_codes = [item["code"] for item in _component_specs(enrollment_type)]
    normalized_grades: list[Decimal] = []
    for code in required_codes:
        value = grades.get(code)
        if value is None:
            return None
        normalized_grades.append(Decimal(str(value)))
    return (sum(normalized_grades, Decimal("0")) / Decimal(len(normalized_grades))).quantize(Decimal("0.01"))


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _period_boundary_utc(value: Any, *, end: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        local_value = value
    elif isinstance(value, date):
        local_value = datetime.combine(value, time.max if end else time.min)
    else:
        raw = _clean(value)
        if not raw:
            return None
        try:
            local_value = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if end and local_value.time() == time.min:
        local_value = datetime.combine(local_value.date(), time.max)
    if local_value.tzinfo is None:
        local_value = local_value.replace(tzinfo=_LOCAL_TIMEZONE)
    return local_value.astimezone(timezone.utc).replace(tzinfo=None)


def _activity_window(profile: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    return (
        _period_boundary_utc(profile.get("fecha_inicio_periodo")),
        _period_boundary_utc(profile.get("fecha_fin_periodo"), end=True),
    )


def _activity_state(start: Any, deadline: Any, *, now: datetime | None = None) -> tuple[bool, str]:
    current = now or _utc_now_naive()
    if isinstance(start, datetime) and current < start:
        return False, "AUN_NO_INICIA"
    if isinstance(deadline, datetime) and current > deadline:
        return False, "PLAZO_FINALIZADO"
    return True, "ABIERTA"


def _require_activity_open(start: Any, deadline: Any) -> None:
    is_open, state = _activity_state(start, deadline)
    if is_open:
        return
    if state == "AUN_NO_INICIA":
        raise HTTPException(status_code=409, detail="La actividad de este parcial todavía no está habilitada.")
    raise HTTPException(status_code=409, detail="El plazo de entrega de este parcial finalizó.")


def _rubric_values(payload: RubricDraftPayload) -> dict[str, Decimal]:
    return {
        "language_mastery": payload.language_mastery.quantize(Decimal("0.01")),
        "fluency_pronunciation": payload.fluency_pronunciation.quantize(Decimal("0.01")),
        "content_coherence": payload.content_coherence.quantize(Decimal("0.01")),
        "instruction_compliance": payload.instruction_compliance.quantize(Decimal("0.01")),
    }


def _rubric_grade(payload: RubricDraftPayload) -> Decimal:
    values = _rubric_values(payload)
    return sum(
        (values[criterion] * weight for criterion, weight in _RUBRIC_WEIGHTS.items()),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def _rubric_json(payload: RubricDraftPayload) -> str:
    return json.dumps(
        {key: float(value) for key, value in _rubric_values(payload).items()},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parse_rubric_json(value: Any) -> dict[str, float] | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    result: dict[str, float] = {}
    for key in _RUBRIC_WEIGHTS:
        try:
            result[key] = float(parsed[key])
        except (KeyError, TypeError, ValueError):
            return None
    return result


def _audit_event(
    cursor: Any,
    exam_id: int,
    event: str,
    audit_user: str,
    *,
    component_id: int | None = None,
    upload_id: UUID | str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    detail: Any = None,
) -> None:
    serialized_detail = None
    if detail is not None:
        serialized_detail = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str)
    cursor.execute(
        """
        INSERT INTO ing.AuditoriaExamenIngles
            (ExamenInglesId, ComponenteExamenInglesId, CargaExamenInglesId,
             Evento, EstadoAnterior, EstadoNuevo, Detalle, Usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        exam_id,
        component_id,
        str(upload_id) if upload_id else None,
        event[:50],
        previous_state,
        new_state,
        serialized_detail,
        audit_user,
    )


def _safe_filename(value: str) -> str:
    filename = Path(value.replace("\\", "/")).name.strip()
    filename = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    if not filename:
        raise HTTPException(status_code=400, detail="El archivo no tiene un nombre válido.")
    extension = Path(filename).suffix.lower()
    if extension not in _ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(_ALLOWED_VIDEO_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Solo se permiten videos en estos formatos: {allowed}.")
    return filename[:255]


def _safe_video_content_type(value: str) -> str:
    content_type = _clean(value).lower().split(";", maxsplit=1)[0].strip()
    if not content_type:
        return "application/octet-stream"
    if content_type != "application/octet-stream" and not content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="El archivo seleccionado no corresponde a un video válido.")
    return content_type


def _safe_folder_part(value: str, fallback: str, *, max_length: int = 120) -> str:
    cleaned = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", _clean(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:max_length].rstrip(" .")


def _graph_drive_user() -> str:
    user = _clean(get_settings().graph_mail_sender)
    if not user:
        raise HTTPException(
            status_code=500,
            detail="Configura GRAPH_MAIL_SENDER para almacenar los expedientes de Inglés en Microsoft 365.",
        )
    return quote(user, safe="")


def _graph_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_graph_token()}",
        "Content-Type": "application/json",
    }


def _drive_item_path_url(path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/") if part)
    return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/root:/{encoded_path}"


def _drive_children_url(item_id: str = "root") -> str:
    if item_id == "root":
        return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/root/children"
    return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/items/{quote(item_id, safe='')}/children"


def _ensure_graph_folder(path: str) -> None:
    parent_id = "root"
    current_path = ""
    with httpx.Client(timeout=30.0) as client:
        for part in [item for item in path.split("/") if item]:
            current_path = f"{current_path}/{part}".strip("/")
            response = client.get(
                f"{_drive_item_path_url(current_path)}:",
                headers={"Authorization": f"Bearer {get_graph_token()}"},
            )
            if response.status_code == 404:
                response = client.post(
                    _drive_children_url(parent_id),
                    headers=_graph_headers(),
                    json={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                )
                if response.status_code == 409:
                    response = client.get(
                        f"{_drive_item_path_url(current_path)}:",
                        headers={"Authorization": f"Bearer {get_graph_token()}"},
                    )
            response.raise_for_status()
            parent_id = _clean(response.json().get("id")) or parent_id


def _create_graph_upload_session(path: str) -> dict[str, Any]:
    url = f"{_drive_item_path_url(path)}:/createUploadSession"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            headers=_graph_headers(),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        response.raise_for_status()
        return response.json()


def _graph_item_by_path(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{_drive_item_path_url(path)}:",
            headers={"Authorization": f"Bearer {get_graph_token()}"},
        )
        if response.status_code == 404:
            raise HTTPException(status_code=409, detail="Microsoft Graph todavía no confirma la carga completa del archivo.")
        response.raise_for_status()
        return response.json()


def _graph_item(item_id: str) -> dict[str, Any]:
    url = f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/items/{quote(item_id, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {get_graph_token()}"})
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="El archivo ya no está disponible en Microsoft 365.")
        response.raise_for_status()
        return response.json()


def _delete_graph_item(item_id: str) -> None:
    if not item_id:
        return
    url = f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/items/{quote(item_id, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(url, headers={"Authorization": f"Bearer {get_graph_token()}"})
        if response.status_code not in {204, 404}:
            response.raise_for_status()


def _ensure_schema(cursor: Any) -> None:
    cursor.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ing')
            EXEC(N'CREATE SCHEMA ing AUTHORIZATION dbo');

        IF OBJECT_ID(N'ing.ExamenIngles', N'U') IS NULL
        BEGIN
            CREATE TABLE ing.ExamenIngles
            (
                ExamenInglesId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ExamenIngles PRIMARY KEY,
                ExpedienteEstudiantilId BIGINT NOT NULL,
                CodigoEstud BIGINT NOT NULL,
                NumeroIdentificacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
                CarreraXEstudNum BIGINT NULL,
                CodigoCarrera INT NULL,
                CodigoMateria INT NULL,
                CodigoPeriodo INT NULL,
                Paralelo NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
                Nivel NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExamenIngles_Nivel DEFAULT N'A2+ - INTERMEDIATE',
                TipoMatricula CHAR(1) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExamenIngles_TipoMatricula DEFAULT 'R',
                NotaFinal DECIMAL(4,2) NULL,
                Estado VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExamenIngles_Estado DEFAULT 'PENDIENTE',
                Observacion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
                CodigoDocEvaluador BIGINT NULL,
                NombreEvaluador NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
                FechaCalificacion DATETIME2 NULL,
                Activo BIT NOT NULL CONSTRAINT DF_ExamenIngles_Activo DEFAULT 1,
                FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_ExamenIngles_Fecha DEFAULT SYSUTCDATETIME(),
                FechaActualizacion DATETIME2 NULL,
                UsuarioActualizacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
                CONSTRAINT FK_ExamenIngles_Expediente FOREIGN KEY (ExpedienteEstudiantilId)
                    REFERENCES exp.ExpedienteEstudiantil(ExpedienteEstudiantilId),
                CONSTRAINT CK_ExamenIngles_Nota CHECK (NotaFinal IS NULL OR (NotaFinal >= 0 AND NotaFinal <= 10))
            );
            EXEC(N'CREATE UNIQUE INDEX UX_ExamenIngles_MatriculaActiva
                ON ing.ExamenIngles(CodigoEstud, CarreraXEstudNum)
                WHERE Activo = 1 AND CarreraXEstudNum IS NOT NULL;');
            EXEC(N'CREATE INDEX IX_ExamenIngles_PeriodoMateria
                ON ing.ExamenIngles(CodigoPeriodo, CodigoMateria, Paralelo, Activo);');
        END;

        IF COL_LENGTH(N'ing.ExamenIngles', N'TipoMatricula') IS NULL
            ALTER TABLE ing.ExamenIngles ADD TipoMatricula CHAR(1) COLLATE Modern_Spanish_CI_AS NOT NULL
                CONSTRAINT DF_ExamenIngles_TipoMatricula_Migracion DEFAULT 'R' WITH VALUES;

        IF COL_LENGTH(N'ing.ExamenIngles', N'CarreraXEstudNum') IS NULL
            ALTER TABLE ing.ExamenIngles ADD CarreraXEstudNum BIGINT NULL;
        IF COL_LENGTH(N'ing.ExamenIngles', N'CodigoCarrera') IS NULL
            ALTER TABLE ing.ExamenIngles ADD CodigoCarrera INT NULL;
        IF COL_LENGTH(N'ing.ExamenIngles', N'CodigoMateria') IS NULL
            ALTER TABLE ing.ExamenIngles ADD CodigoMateria INT NULL;
        IF COL_LENGTH(N'ing.ExamenIngles', N'CodigoPeriodo') IS NULL
            ALTER TABLE ing.ExamenIngles ADD CodigoPeriodo INT NULL;
        IF COL_LENGTH(N'ing.ExamenIngles', N'Paralelo') IS NULL
            ALTER TABLE ing.ExamenIngles ADD Paralelo NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;

        EXEC(N'
            UPDATE e
               SET CodigoCarrera = COALESCE(e.CodigoCarrera, TRY_CONVERT(INT, ex.CodigoCarrera)),
                   CodigoPeriodo = COALESCE(e.CodigoPeriodo, TRY_CONVERT(INT, ex.CodigoPeriodo))
            FROM ing.ExamenIngles e
            INNER JOIN exp.ExpedienteEstudiantil ex
                ON ex.ExpedienteEstudiantilId = e.ExpedienteEstudiantilId
            WHERE e.CodigoCarrera IS NULL OR e.CodigoPeriodo IS NULL;
        ');

        IF EXISTS
        (
            SELECT 1 FROM sys.indexes
            WHERE name = N'UX_ExamenIngles_EstudianteActivo'
              AND object_id = OBJECT_ID(N'ing.ExamenIngles')
        )
            DROP INDEX UX_ExamenIngles_EstudianteActivo ON ing.ExamenIngles;

        IF NOT EXISTS
        (
            SELECT 1 FROM sys.indexes
            WHERE name = N'UX_ExamenIngles_MatriculaActiva'
              AND object_id = OBJECT_ID(N'ing.ExamenIngles')
        )
            EXEC(N'CREATE UNIQUE INDEX UX_ExamenIngles_MatriculaActiva
                ON ing.ExamenIngles(CodigoEstud, CarreraXEstudNum)
                WHERE Activo = 1 AND CarreraXEstudNum IS NOT NULL;');

        IF NOT EXISTS
        (
            SELECT 1 FROM sys.indexes
            WHERE name = N'IX_ExamenIngles_PeriodoMateria'
              AND object_id = OBJECT_ID(N'ing.ExamenIngles')
        )
            EXEC(N'CREATE INDEX IX_ExamenIngles_PeriodoMateria
                ON ing.ExamenIngles(CodigoPeriodo, CodigoMateria, Paralelo, Activo);');

        IF OBJECT_ID(N'ing.ComponenteExamenIngles', N'U') IS NULL
        BEGIN
            CREATE TABLE ing.ComponenteExamenIngles
            (
                ComponenteExamenInglesId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ComponenteExamenIngles PRIMARY KEY,
                ExamenInglesId BIGINT NOT NULL,
                Codigo VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
                NumeroParcial TINYINT NOT NULL,
                Nombre NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
                TipoEvaluacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
                FechaInicioActividad DATETIME2 NULL,
                FechaLimiteActividad DATETIME2 NULL,
                Nota DECIMAL(4,2) NULL,
                Estado VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ComponenteExamenIngles_Estado DEFAULT 'PENDIENTE',
                EstadoRevision VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ComponenteExamenIngles_Revision DEFAULT 'PENDIENTE_ENTREGA',
                Observacion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
                NotaBorrador DECIMAL(4,2) NULL,
                ObservacionBorrador NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
                RubricaBorradorJson NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
                FechaBorrador DATETIME2 NULL,
                UsuarioBorrador NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
                FechaPublicacion DATETIME2 NULL,
                UsuarioPublicacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
                FechaNotificacionDocente DATETIME2 NULL,
                EstadoNotificacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
                DetalleNotificacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
                CodigoDocEvaluador BIGINT NULL,
                NombreEvaluador NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
                FechaCalificacion DATETIME2 NULL,
                Activo BIT NOT NULL CONSTRAINT DF_ComponenteExamenIngles_Activo DEFAULT 1,
                FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_ComponenteExamenIngles_Fecha DEFAULT SYSUTCDATETIME(),
                FechaActualizacion DATETIME2 NULL,
                UsuarioActualizacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
                CONSTRAINT FK_ComponenteExamenIngles_Examen FOREIGN KEY (ExamenInglesId)
                    REFERENCES ing.ExamenIngles(ExamenInglesId),
                CONSTRAINT CK_ComponenteExamenIngles_Nota CHECK (Nota IS NULL OR (Nota >= 0 AND Nota <= 10)),
                CONSTRAINT CK_ComponenteExamenIngles_NotaBorrador CHECK (NotaBorrador IS NULL OR (NotaBorrador >= 0 AND NotaBorrador <= 10)),
                CONSTRAINT UQ_ComponenteExamenIngles_Codigo UNIQUE (ExamenInglesId, Codigo)
            );
            CREATE INDEX IX_ComponenteExamenIngles_Activo
                ON ing.ComponenteExamenIngles(ExamenInglesId, Activo, NumeroParcial);
        END;

        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaInicioActividad') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD FechaInicioActividad DATETIME2 NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaLimiteActividad') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD FechaLimiteActividad DATETIME2 NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'EstadoRevision') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD EstadoRevision VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL
                CONSTRAINT DF_ComponenteExamenIngles_Revision_Migracion DEFAULT 'PENDIENTE_ENTREGA' WITH VALUES;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'NotaBorrador') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD NotaBorrador DECIMAL(4,2) NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'ObservacionBorrador') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD ObservacionBorrador NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'RubricaBorradorJson') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD RubricaBorradorJson NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaBorrador') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD FechaBorrador DATETIME2 NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'UsuarioBorrador') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD UsuarioBorrador NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaPublicacion') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD FechaPublicacion DATETIME2 NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'UsuarioPublicacion') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD UsuarioPublicacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaNotificacionDocente') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD FechaNotificacionDocente DATETIME2 NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'EstadoNotificacion') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD EstadoNotificacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'DetalleNotificacion') IS NULL
            ALTER TABLE ing.ComponenteExamenIngles ADD DetalleNotificacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
        IF NOT EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_ComponenteExamenIngles_NotaBorrador'
              AND parent_object_id = OBJECT_ID(N'ing.ComponenteExamenIngles')
        )
            EXEC(N'ALTER TABLE ing.ComponenteExamenIngles WITH CHECK
                ADD CONSTRAINT CK_ComponenteExamenIngles_NotaBorrador
                CHECK (NotaBorrador IS NULL OR (NotaBorrador >= 0 AND NotaBorrador <= 10));');

        IF OBJECT_ID(N'ing.CargaExamenIngles', N'U') IS NULL
        BEGIN
            CREATE TABLE ing.CargaExamenIngles
            (
                CargaExamenInglesId UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_CargaExamenIngles PRIMARY KEY,
                ExamenInglesId BIGINT NOT NULL,
                ComponenteExamenInglesId BIGINT NULL,
                DocumentoExpedienteId BIGINT NULL,
                NumeroVersion INT NOT NULL,
                NombreArchivoOriginal NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
                NombreArchivoNube NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
                RutaGraph NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NOT NULL,
                ContentType NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
                TamanoEsperado BIGINT NOT NULL,
                TamanoBytes BIGINT NULL,
                GraphItemId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
                GraphWebUrl NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
                Estado VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_CargaExamenIngles_Estado DEFAULT 'CARGA_INICIADA',
                FechaInicioCarga DATETIME2 NOT NULL CONSTRAINT DF_CargaExamenIngles_Inicio DEFAULT SYSUTCDATETIME(),
                FechaCarga DATETIME2 NULL,
                FechaLimiteEdicion DATETIME2 NULL,
                FechaConfirmacion DATETIME2 NULL,
                UsuarioConfirmacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
                IntegridadValidada BIT NOT NULL CONSTRAINT DF_CargaExamenIngles_Integridad DEFAULT 0,
                HashIntegridad NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
                UsuarioCarga NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
                Activo BIT NOT NULL CONSTRAINT DF_CargaExamenIngles_Activo DEFAULT 0,
                CONSTRAINT FK_CargaExamenIngles_Examen FOREIGN KEY (ExamenInglesId)
                    REFERENCES ing.ExamenIngles(ExamenInglesId),
                CONSTRAINT FK_CargaExamenIngles_Componente FOREIGN KEY (ComponenteExamenInglesId)
                    REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId),
                CONSTRAINT FK_CargaExamenIngles_Documento FOREIGN KEY (DocumentoExpedienteId)
                    REFERENCES doc.DocumentoExpediente(DocumentoExpedienteId),
                CONSTRAINT CK_CargaExamenIngles_Tamano_V3 CHECK (TamanoEsperado > 0 AND TamanoEsperado <= 2147483648)
            );
            CREATE UNIQUE INDEX UX_CargaExamenIngles_Version
                ON ing.CargaExamenIngles(ExamenInglesId, NumeroVersion);
            CREATE INDEX IX_CargaExamenIngles_Actual
                ON ing.CargaExamenIngles(ExamenInglesId, Activo, FechaCarga DESC);
        END;

        IF COL_LENGTH(N'ing.CargaExamenIngles', N'ComponenteExamenInglesId') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD ComponenteExamenInglesId BIGINT NULL;
        IF COL_LENGTH(N'ing.CargaExamenIngles', N'FechaConfirmacion') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD FechaConfirmacion DATETIME2 NULL;
        IF COL_LENGTH(N'ing.CargaExamenIngles', N'UsuarioConfirmacion') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD UsuarioConfirmacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;
        IF COL_LENGTH(N'ing.CargaExamenIngles', N'IntegridadValidada') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD IntegridadValidada BIT NOT NULL
                CONSTRAINT DF_CargaExamenIngles_Integridad_Migracion DEFAULT 0 WITH VALUES;
        IF COL_LENGTH(N'ing.CargaExamenIngles', N'HashIntegridad') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD HashIntegridad NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL;

        IF EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_CargaExamenIngles_Tamano'
              AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
            ALTER TABLE ing.CargaExamenIngles DROP CONSTRAINT CK_CargaExamenIngles_Tamano;
        IF NOT EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_CargaExamenIngles_Tamano_V3'
              AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
        BEGIN
            IF EXISTS
            (
                SELECT 1 FROM sys.check_constraints
                WHERE name = N'CK_CargaExamenIngles_Tamano_V2'
                  AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
            )
                ALTER TABLE ing.CargaExamenIngles DROP CONSTRAINT CK_CargaExamenIngles_Tamano_V2;

            ALTER TABLE ing.CargaExamenIngles WITH CHECK ADD CONSTRAINT CK_CargaExamenIngles_Tamano_V3
                CHECK (TamanoEsperado > 0 AND TamanoEsperado <= 2147483648);
        END;

        IF NOT EXISTS
        (
            SELECT 1
            FROM sys.foreign_keys
            WHERE name = N'FK_CargaExamenIngles_Componente'
              AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
            EXEC(N'ALTER TABLE ing.CargaExamenIngles WITH CHECK ADD CONSTRAINT FK_CargaExamenIngles_Componente
                FOREIGN KEY (ComponenteExamenInglesId) REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId);');

        IF NOT EXISTS
        (
            SELECT 1 FROM sys.indexes
            WHERE name = N'IX_CargaExamenIngles_ComponenteActual'
              AND object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
            EXEC(N'CREATE INDEX IX_CargaExamenIngles_ComponenteActual
                ON ing.CargaExamenIngles(ComponenteExamenInglesId, Activo, FechaCarga DESC);');

        IF OBJECT_ID(N'ing.AuditoriaExamenIngles', N'U') IS NULL
        BEGIN
            CREATE TABLE ing.AuditoriaExamenIngles
            (
                AuditoriaExamenInglesId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AuditoriaExamenIngles PRIMARY KEY,
                ExamenInglesId BIGINT NOT NULL,
                ComponenteExamenInglesId BIGINT NULL,
                CargaExamenInglesId UNIQUEIDENTIFIER NULL,
                Evento VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
                EstadoAnterior VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
                EstadoNuevo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
                Detalle NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
                Usuario NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
                FechaEvento DATETIME2 NOT NULL CONSTRAINT DF_AuditoriaExamenIngles_Fecha DEFAULT SYSUTCDATETIME(),
                CONSTRAINT FK_AuditoriaExamenIngles_Examen FOREIGN KEY (ExamenInglesId)
                    REFERENCES ing.ExamenIngles(ExamenInglesId),
                CONSTRAINT FK_AuditoriaExamenIngles_Componente FOREIGN KEY (ComponenteExamenInglesId)
                    REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId)
            );
            CREATE INDEX IX_AuditoriaExamenIngles_ExamenFecha
                ON ing.AuditoriaExamenIngles(ExamenInglesId, FechaEvento DESC);
        END;

        IF NOT EXISTS (SELECT 1 FROM cat.TipoExpediente WHERE Codigo = 'INGLES')
            INSERT INTO cat.TipoExpediente(Codigo, Nombre, Descripcion)
            VALUES('INGLES', N'Expediente de evaluación de Inglés', N'Evidencia, versiones y calificación del examen de Inglés.');

        IF NOT EXISTS (SELECT 1 FROM cat.TipoDocumento WHERE Codigo = 'EVIDENCIA_EXAMEN_INGLES')
            INSERT INTO cat.TipoDocumento(Codigo, Nombre, GrupoDocumento, Descripcion, PermiteMultiples, Versionable)
            VALUES('EVIDENCIA_EXAMEN_INGLES', N'Evidencia del examen de Inglés', 'ACADEMICO', N'Archivo entregado por el estudiante para evaluación de Inglés.', 1, 1);
        ELSE
            UPDATE cat.TipoDocumento SET PermiteMultiples = 1, Versionable = 1
            WHERE Codigo = 'EVIDENCIA_EXAMEN_INGLES';
        """
    )


def _student_profile(current_user: SessionUser) -> dict[str, Any]:
    codigo_estud = current_user.codigo_estud
    cedula = re.sub(r"\D+", "", _clean(current_user.cedula))
    if not codigo_estud and not cedula:
        raise HTTPException(status_code=400, detail="La sesión estudiantil no contiene código ni identificación.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (1)
                TRY_CONVERT(BIGINT, d.codigo_estud) AS codigo_estud,
                LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), d.Cedula_Est))) AS cedula,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), d.Apellidos_nombre))) AS estudiante,
                TRY_CONVERT(NVARCHAR(300), d.correo) AS correo,
                matricula_ingles.carrera_x_estud_num,
                matricula_ingles.codigo_carrera,
                matricula_ingles.carrera_ingles,
                matricula_ingles.codigo_materia,
                matricula_ingles.nivel_ingles,
                matricula_ingles.codigo_periodo,
                matricula_ingles.detalle_periodo,
                matricula_ingles.fecha_inicio_periodo,
                matricula_ingles.fecha_fin_periodo,
                matricula_ingles.paralelo,
                matricula_ingles.tipo_matricula,
                carrera_principal.codigo_carrera_principal,
                COALESCE(carrera_principal.carrera_principal, matricula_ingles.carrera_ingles) AS carrera
            FROM dbo.DATOS_ESTUD d
            OUTER APPLY
            (
                SELECT TOP (1)
                    TRY_CONVERT(BIGINT, cx.num) AS carrera_x_estud_num,
                    TRY_CONVERT(INT, cx.cod_anio_Basica) AS codigo_carrera,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), ci.Nombre_Basica))) AS carrera_ingles,
                    TRY_CONVERT(INT, cx.codigo_materia) AS codigo_materia,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pi.Nomb_Materia))) AS nivel_ingles,
                    TRY_CONVERT(INT, cx.codigo_periodo) AS codigo_periodo,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pe.Detalle_Periodo))) AS detalle_periodo,
                    TRY_CONVERT(DATE, pe.fechain) AS fecha_inicio_periodo,
                    TRY_CONVERT(DATE, pe.fechafin) AS fecha_fin_periodo,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cx.paralelo))) AS paralelo,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), cx.TipoMatricula))) AS tipo_matricula
                FROM dbo.CARRERAXESTUD cx
                INNER JOIN dbo.CARRERAS ci
                    ON TRY_CONVERT(INT, ci.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
                INNER JOIN dbo.PENSUM pi
                    ON TRY_CONVERT(INT, pi.Cod_AnioBasica) = TRY_CONVERT(INT, cx.cod_anio_Basica)
                   AND TRY_CONVERT(INT, pi.codigo_materia) = TRY_CONVERT(INT, cx.codigo_materia)
                INNER JOIN dbo.PERIODO pe
                    ON TRY_CONVERT(INT, pe.cod_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
                WHERE TRY_CONVERT(BIGINT, cx.codigo_estud) = TRY_CONVERT(BIGINT, d.codigo_estud)
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), d.Estado)))) = N'A'
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), ci.Estado)))) = N'A'
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), ci.tp_escuela)))) = N'IDIOMA'
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), pe.Estado)))) = N'A'
                  AND (pe.fechain IS NULL OR pe.fechain <= CONVERT(DATE, GETDATE()))
                  AND (pe.fechafin IS NULL OR pe.fechafin >= CONVERT(DATE, GETDATE()))
                  AND TRY_CONVERT(BIGINT, cx.num) IS NOT NULL
                ORDER BY COALESCE(TRY_CONVERT(INT, pe.Orden), TRY_CONVERT(INT, cx.codigo_periodo)) DESC,
                         cx.Fecha_Matricula DESC,
                         TRY_CONVERT(BIGINT, cx.num) DESC
            ) matricula_ingles
            OUTER APPLY
            (
                SELECT TOP (1)
                    TRY_CONVERT(INT, cp.Cod_AnioBasica) AS codigo_carrera_principal,
                    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), cp.Nombre_Basica))) AS carrera_principal
                FROM dbo.CARRERAXESTUD cxo
                INNER JOIN dbo.CARRERAS cp
                    ON TRY_CONVERT(INT, cp.Cod_AnioBasica) = TRY_CONVERT(INT, cxo.cod_anio_Basica)
                WHERE TRY_CONVERT(BIGINT, cxo.codigo_estud) = TRY_CONVERT(BIGINT, d.codigo_estud)
                  AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(NVARCHAR(30), cp.tp_escuela), N'')))) <> N'IDIOMA'
                ORDER BY TRY_CONVERT(INT, cxo.codigo_periodo) DESC,
                         cxo.Fecha_Matricula DESC,
                         TRY_CONVERT(BIGINT, cxo.num) DESC
            ) carrera_principal
            WHERE (? IS NOT NULL AND TRY_CONVERT(BIGINT, d.codigo_estud) = ?)
               OR (? <> '' AND REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(VARCHAR(30), d.Cedula_Est))), '-', ''), ' ', '') = ?)
            ORDER BY CASE WHEN ? IS NOT NULL AND TRY_CONVERT(BIGINT, d.codigo_estud) = ? THEN 0 ELSE 1 END
            """,
            codigo_estud,
            codigo_estud,
            cedula,
            cedula,
            codigo_estud,
            codigo_estud,
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró al estudiante en INTECBDD.")
    if row.carrera_x_estud_num is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "La carga no está habilitada porque el estudiante no tiene una matrícula vigente "
                "en una asignatura de Inglés o Idiomas."
            ),
        )
    return {
        "codigo_estud": int(row.codigo_estud),
        "cedula": _clean(row.cedula),
        "estudiante": _clean(row.estudiante),
        "correo": _clean(row.correo),
        "carrera_x_estud_num": int(row.carrera_x_estud_num),
        "codigo_carrera": int(row.codigo_carrera),
        "carrera_ingles": _clean(row.carrera_ingles),
        "codigo_materia": int(row.codigo_materia),
        "nivel": _clean(row.nivel_ingles) or _LEVEL_NAME,
        "carrera": _clean(row.carrera),
        "codigo_carrera_principal": _clean(row.codigo_carrera_principal),
        "codigo_periodo": int(row.codigo_periodo),
        "detalle_periodo": _clean(row.detalle_periodo),
        "fecha_inicio_periodo": getattr(row, "fecha_inicio_periodo", None),
        "fecha_fin_periodo": getattr(row, "fecha_fin_periodo", None),
        "paralelo": _clean(row.paralelo),
        "tipo_matricula": _normalize_enrollment_type(row.tipo_matricula),
    }


def _catalog_id(cursor: Any, table: str, code: str, id_column: str) -> int:
    cursor.execute(f"SELECT {id_column} FROM {table} WHERE Codigo = ?", code)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"No existe el catálogo {table}.{code}")
    return int(row[0])


def _ensure_components(
    cursor: Any,
    exam_id: int,
    enrollment_type: str,
    audit_user: str,
    activity_start: datetime | None = None,
    activity_deadline: datetime | None = None,
) -> None:
    specs = _component_specs(enrollment_type)
    required_codes = {item["code"] for item in specs}
    for spec in specs:
        cursor.execute(
            """
            SELECT ComponenteExamenInglesId
            FROM ing.ComponenteExamenIngles
            WHERE ExamenInglesId = ? AND Codigo = ?
            """,
            exam_id,
            spec["code"],
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE ing.ComponenteExamenIngles
                   SET NumeroParcial = ?, Nombre = ?, TipoEvaluacion = ?, Activo = 1,
                       FechaInicioActividad = COALESCE(?, FechaInicioActividad),
                       FechaLimiteActividad = COALESCE(?, FechaLimiteActividad),
                       FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                 WHERE ComponenteExamenInglesId = ?
                """,
                spec["number"],
                spec["label"],
                spec["evaluation_type"],
                activity_start,
                activity_deadline,
                audit_user,
                int(existing[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ing.ComponenteExamenIngles
                    (ExamenInglesId, Codigo, NumeroParcial, Nombre, TipoEvaluacion,
                     FechaInicioActividad, FechaLimiteActividad, UsuarioActualizacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                exam_id,
                spec["code"],
                spec["number"],
                spec["label"],
                spec["evaluation_type"],
                activity_start,
                activity_deadline,
                audit_user,
            )

    placeholders = ", ".join("?" for _ in required_codes)
    cursor.execute(
        f"""
        UPDATE ing.ComponenteExamenIngles
           SET Activo = 0, FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
         WHERE ExamenInglesId = ? AND Codigo NOT IN ({placeholders}) AND Activo = 1
        """,
        audit_user,
        exam_id,
        *sorted(required_codes),
    )
    first_code = specs[0]["code"]
    cursor.execute(
        """
        UPDATE carga
           SET ComponenteExamenInglesId = componente.ComponenteExamenInglesId
        FROM ing.CargaExamenIngles carga
        INNER JOIN ing.ComponenteExamenIngles componente
            ON componente.ExamenInglesId = carga.ExamenInglesId AND componente.Codigo = ?
        WHERE carga.ExamenInglesId = ? AND carga.ComponenteExamenInglesId IS NULL
        """,
        first_code,
        exam_id,
    )


def _ensure_exam(cursor: Any, profile: dict[str, Any], audit_user: str) -> int:
    _ensure_schema(cursor)
    activity_start, activity_deadline = _activity_window(profile)
    cursor.execute(
        "SELECT PersonaId FROM core.Persona WHERE NumeroIdentificacion = ?",
        profile["cedula"],
    )
    person = cursor.fetchone()
    if person:
        person_id = int(person[0])
        cursor.execute(
            """
            UPDATE core.Persona
               SET CodigoEstud = COALESCE(CodigoEstud, ?),
                   ApellidosNombres = COALESCE(NULLIF(?, N''), ApellidosNombres),
                   CorreoPersonal = COALESCE(NULLIF(?, N''), CorreoPersonal),
                   FuenteUltimaActualizacion = 'INTECBDD',
                   FechaActualizacion = SYSUTCDATETIME()
             WHERE PersonaId = ?
            """,
            profile["codigo_estud"],
            profile["estudiante"],
            profile["correo"],
            person_id,
        )
    else:
        cursor.execute(
            """
            INSERT INTO core.Persona
                (NumeroIdentificacion, CodigoEstud, ApellidosNombres, CorreoPersonal, FuenteUltimaActualizacion)
            OUTPUT INSERTED.PersonaId
            VALUES (?, ?, ?, ?, 'INTECBDD')
            """,
            profile["cedula"],
            profile["codigo_estud"],
            profile["estudiante"],
            profile["correo"] or None,
        )
        person_id = int(cursor.fetchone()[0])

    type_id = _catalog_id(cursor, "cat.TipoExpediente", "INGLES", "TipoExpedienteId")
    draft_state_id = _catalog_id(cursor, "cat.EstadoExpediente", "BORRADOR", "EstadoExpedienteId")
    cursor.execute(
        """
        SELECT TOP (1) ExpedienteEstudiantilId
        FROM exp.ExpedienteEstudiantil
        WHERE TipoExpedienteId = ? AND PersonaId = ? AND Activo = 1
          AND TRY_CONVERT(INT, CodigoCarrera) = ?
          AND TRY_CONVERT(INT, CodigoPeriodo) = ?
          AND TRY_CONVERT(INT, CodigoCurso) = ?
        ORDER BY ExpedienteEstudiantilId DESC
        """,
        type_id,
        person_id,
        profile["codigo_carrera"],
        profile["codigo_periodo"],
        profile["codigo_materia"],
    )
    expediente = cursor.fetchone()
    if expediente:
        expediente_id = int(expediente[0])
        cursor.execute(
            """
            UPDATE exp.ExpedienteEstudiantil
               SET CodigoEstud = ?, NumeroIdentificacion = ?, CodigoCarrera = ?, CodigoPeriodo = ?, CodigoCurso = ?,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ExpedienteEstudiantilId = ?
            """,
            profile["codigo_estud"],
            profile["cedula"],
            profile["codigo_carrera"],
            profile["codigo_periodo"],
            profile["codigo_materia"],
            audit_user,
            expediente_id,
        )
    else:
        cursor.execute(
            """
            INSERT INTO exp.ExpedienteEstudiantil
                (CodigoExpediente, TipoExpedienteId, EstadoExpedienteId, PersonaId, CodigoEstud,
                 NumeroIdentificacion, CodigoCarrera, CodigoPeriodo, CodigoCurso, Observacion, UsuarioApertura)
            OUTPUT INSERTED.ExpedienteEstudiantilId
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, N'Expediente automático para evaluación de Inglés.', ?)
            """,
            f"ING-{profile['codigo_estud']}-{profile['codigo_periodo']}-{profile['codigo_materia']}",
            type_id,
            draft_state_id,
            person_id,
            profile["codigo_estud"],
            profile["cedula"],
            profile["codigo_carrera"],
            profile["codigo_periodo"],
            profile["codigo_materia"],
            audit_user,
        )
        expediente_id = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT ExamenInglesId
        FROM ing.ExamenIngles
        WHERE CodigoEstud = ? AND CarreraXEstudNum = ? AND Activo = 1
        """,
        profile["codigo_estud"],
        profile["carrera_x_estud_num"],
    )
    exam = cursor.fetchone()
    if exam:
        exam_id = int(exam[0])
        cursor.execute(
            """
            UPDATE ing.ExamenIngles
               SET ExpedienteEstudiantilId = ?, NumeroIdentificacion = ?, TipoMatricula = ?,
                   CarreraXEstudNum = ?, CodigoCarrera = ?, CodigoMateria = ?, CodigoPeriodo = ?,
                   Paralelo = ?, Nivel = ?,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ExamenInglesId = ?
            """,
            expediente_id,
            profile["cedula"],
            profile["tipo_matricula"],
            profile["carrera_x_estud_num"],
            profile["codigo_carrera"],
            profile["codigo_materia"],
            profile["codigo_periodo"],
            profile["paralelo"] or None,
            profile["nivel"],
            audit_user,
            exam_id,
        )
        _ensure_components(
            cursor,
            exam_id,
            profile["tipo_matricula"],
            audit_user,
            activity_start,
            activity_deadline,
        )
        return exam_id
    cursor.execute(
        """
        INSERT INTO ing.ExamenIngles
            (ExpedienteEstudiantilId, CodigoEstud, NumeroIdentificacion, CarreraXEstudNum,
             CodigoCarrera, CodigoMateria, CodigoPeriodo, Paralelo, Nivel, TipoMatricula, UsuarioActualizacion)
        OUTPUT INSERTED.ExamenInglesId
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        expediente_id,
        profile["codigo_estud"],
        profile["cedula"],
        profile["carrera_x_estud_num"],
        profile["codigo_carrera"],
        profile["codigo_materia"],
        profile["codigo_periodo"],
        profile["paralelo"] or None,
        profile["nivel"],
        profile["tipo_matricula"],
        audit_user,
    )
    exam_id = int(cursor.fetchone()[0])
    _ensure_components(
        cursor,
        exam_id,
        profile["tipo_matricula"],
        audit_user,
        activity_start,
        activity_deadline,
    )
    _audit_event(
        cursor,
        exam_id,
        "EXPEDIENTE_CREADO",
        audit_user,
        new_state="PENDIENTE",
        detail={"carrera_x_estud_num": profile["carrera_x_estud_num"]},
    )
    return exam_id


def _component_payload(row: Any) -> dict[str, Any]:
    now = _utc_now_naive()
    deadline = getattr(row, "fecha_limite_edicion", None)
    seconds_remaining = max(0, int((deadline - now).total_seconds())) if isinstance(deadline, datetime) else 0
    activity_start = getattr(row, "fecha_inicio_actividad", None)
    activity_deadline = getattr(row, "fecha_limite_actividad", None)
    activity_open, activity_status = _activity_state(activity_start, activity_deadline, now=now)
    grade_raw = getattr(row, "nota", None)
    grade = float(grade_raw) if grade_raw is not None else None
    draft_grade_raw = getattr(row, "nota_borrador", None)
    draft_grade = float(draft_grade_raw) if draft_grade_raw is not None else None
    delivery_state = _clean(getattr(row, "estado_carga", None))
    confirmed = delivery_state in {"CONFIRMADO", "CARGADO"}
    file_payload = None
    if getattr(row, "upload_id", None):
        file_payload = {
            "upload_id": str(row.upload_id),
            "name": _clean(row.nombre_archivo),
            "content_type": _clean(row.content_type),
            "size": int(row.tamano_bytes or 0),
            "version": int(row.numero_version or 1),
            "uploaded_at": _iso_utc(row.fecha_carga),
            "web_url": _clean(row.graph_web_url),
            "delivery_state": delivery_state,
            "confirmed": confirmed,
            "confirmed_at": _iso_utc(getattr(row, "fecha_confirmacion", None)),
            "integrity_validated": bool(getattr(row, "integridad_validada", False) or delivery_state == "CARGADO"),
            "integrity_hash": _clean(getattr(row, "hash_integridad", None)),
        }
    return {
        "component_id": int(row.componente_id),
        "code": _clean(row.codigo),
        "number": int(row.numero_parcial),
        "label": _clean(row.nombre),
        "evaluation_type": _clean(row.tipo_evaluacion),
        "status": _clean(row.estado),
        "grade": grade,
        "result": "APROBADO" if grade is not None and grade >= float(_PASSING_GRADE) else "REPROBADO" if grade is not None else "PENDIENTE",
        "observation": _clean(row.observacion),
        "evaluator": _clean(row.nombre_evaluador),
        "graded_at": _iso_utc(row.fecha_calificacion),
        "file": file_payload,
        "delivery_state": delivery_state or "SIN_ENTREGA",
        "confirmed": confirmed,
        "can_confirm": bool(file_payload and not confirmed and delivery_state == "PENDIENTE_CONFIRMACION" and activity_open),
        "can_edit": bool(file_payload and delivery_state == "PENDIENTE_CONFIRMACION" and seconds_remaining > 0 and grade is None),
        "edit_deadline": _iso_utc(deadline),
        "seconds_remaining": seconds_remaining,
        "activity_start": _iso_utc(activity_start),
        "activity_deadline": _iso_utc(activity_deadline),
        "activity_open": activity_open,
        "activity_status": activity_status,
        "review_state": _clean(getattr(row, "estado_revision", None)) or "PENDIENTE_ENTREGA",
        "draft_grade": draft_grade,
        "draft_observation": _clean(getattr(row, "observacion_borrador", None)),
        "draft_rubric": _parse_rubric_json(getattr(row, "rubrica_borrador_json", None)),
        "drafted_at": _iso_utc(getattr(row, "fecha_borrador", None)),
        "drafted_by": _clean(getattr(row, "usuario_borrador", None)),
        "published_at": _iso_utc(getattr(row, "fecha_publicacion", None)),
        "published_by": _clean(getattr(row, "usuario_publicacion", None)),
        "notification_state": _clean(getattr(row, "estado_notificacion", None)),
    }


def _load_component_rows(
    cursor: Any,
    exam_ids: list[int],
    *,
    include_pending_confirmation: bool = True,
) -> dict[int, list[Any]]:
    if not exam_ids:
        return {}
    placeholders = ", ".join("?" for _ in exam_ids)
    cursor.execute(
        f"""
        SELECT
            componente.ComponenteExamenInglesId AS componente_id,
            componente.ExamenInglesId AS examen_id,
            componente.Codigo AS codigo,
            componente.NumeroParcial AS numero_parcial,
            componente.Nombre AS nombre,
            componente.TipoEvaluacion AS tipo_evaluacion,
            componente.FechaInicioActividad AS fecha_inicio_actividad,
            componente.FechaLimiteActividad AS fecha_limite_actividad,
            componente.Nota AS nota,
            componente.Estado AS estado,
            componente.EstadoRevision AS estado_revision,
            componente.Observacion AS observacion,
            componente.NotaBorrador AS nota_borrador,
            componente.ObservacionBorrador AS observacion_borrador,
            componente.RubricaBorradorJson AS rubrica_borrador_json,
            componente.FechaBorrador AS fecha_borrador,
            componente.UsuarioBorrador AS usuario_borrador,
            componente.FechaPublicacion AS fecha_publicacion,
            componente.UsuarioPublicacion AS usuario_publicacion,
            componente.EstadoNotificacion AS estado_notificacion,
            componente.NombreEvaluador AS nombre_evaluador,
            componente.FechaCalificacion AS fecha_calificacion,
            carga.CargaExamenInglesId AS upload_id,
            carga.NombreArchivoOriginal AS nombre_archivo,
            carga.ContentType AS content_type,
            carga.TamanoBytes AS tamano_bytes,
            carga.NumeroVersion AS numero_version,
            carga.FechaCarga AS fecha_carga,
            carga.FechaLimiteEdicion AS fecha_limite_edicion,
            carga.FechaConfirmacion AS fecha_confirmacion,
            carga.IntegridadValidada AS integridad_validada,
            carga.HashIntegridad AS hash_integridad,
            carga.Estado AS estado_carga,
            carga.GraphWebUrl AS graph_web_url
        FROM ing.ComponenteExamenIngles componente
        OUTER APPLY
        (
            SELECT TOP (1) ce.*
            FROM ing.CargaExamenIngles ce
            WHERE ce.ComponenteExamenInglesId = componente.ComponenteExamenInglesId
              AND ce.Activo = 1
              AND ce.Estado IN ({"'PENDIENTE_CONFIRMACION', 'CONFIRMADO', 'CARGADO'" if include_pending_confirmation else "'CONFIRMADO', 'CARGADO'"})
            ORDER BY ce.NumeroVersion DESC
        ) carga
        WHERE componente.Activo = 1 AND componente.ExamenInglesId IN ({placeholders})
        ORDER BY componente.ExamenInglesId, componente.NumeroParcial, componente.ComponenteExamenInglesId
        """,
        *exam_ids,
    )
    grouped: dict[int, list[Any]] = {}
    for row in cursor.fetchall():
        grouped.setdefault(int(row.examen_id), []).append(row)
    return grouped


def _row_payload(row: Any, component_rows: list[Any], *, include_student: bool = False) -> dict[str, Any]:
    components = [_component_payload(item) for item in component_rows]
    grade_raw = getattr(row, "nota_final", None)
    grade = float(grade_raw) if grade_raw is not None else None
    current_file = next((item["file"] for item in components if item["file"]), None)
    active_deadlines = [item["edit_deadline"] for item in components if item["edit_deadline"]]
    payload: dict[str, Any] = {
        "exam_id": int(row.examen_id),
        "expedient_id": int(row.expediente_id),
        "level": _clean(row.nivel) or _LEVEL_NAME,
        "enrollment_type": _normalize_enrollment_type(row.tipo_matricula),
        "scheme": "TRES_PARCIALES",
        "status": _clean(row.estado),
        "grade": grade,
        "result": "APROBADO" if grade is not None and grade >= float(_PASSING_GRADE) else "REPROBADO" if grade is not None else "PENDIENTE",
        "passing_grade": float(_PASSING_GRADE),
        "observation": _clean(row.observacion),
        "evaluator": _clean(row.nombre_evaluador),
        "graded_at": _iso_utc(row.fecha_calificacion),
        "file": current_file,
        "components": components,
        "required_components": len(components),
        "submitted_components": sum(1 for item in components if item["confirmed"]),
        "staged_components": sum(1 for item in components if item["file"] and not item["confirmed"]),
        "graded_components": sum(1 for item in components if item["grade"] is not None),
        "can_edit": any(item["can_edit"] for item in components),
        "edit_deadline": max(active_deadlines) if active_deadlines else None,
        "seconds_remaining": max((item["seconds_remaining"] for item in components), default=0),
        "edit_window_minutes": _EDIT_WINDOW_MINUTES,
        "min_file_bytes": _MIN_FILE_BYTES,
        "max_file_bytes": _MAX_FILE_BYTES,
        "enrollment": {
            "enabled": True,
            "enrollment_id": int(row.carrera_x_estud_num),
            "english_career_code": _clean(row.codigo_carrera_ingles),
            "english_career": _clean(row.carrera_ingles),
            "subject_code": _clean(row.codigo_materia),
            "subject": _clean(row.materia) or _LEVEL_NAME,
            "period_code": _clean(row.codigo_periodo),
            "period": _period_label(_clean(row.codigo_periodo), _clean(row.detalle_periodo)),
            "parallel": _clean(row.paralelo),
        },
    }
    if include_student:
        payload["student"] = {
            "code": int(row.codigo_estud),
            "identification": _clean(row.numero_identificacion),
            "name": _clean(row.estudiante),
            "career": _clean(row.carrera),
            "career_code": _clean(row.codigo_carrera),
            "period_code": _clean(row.codigo_periodo),
        }
    return payload


def _virtual_exam_payload(profile: dict[str, Any]) -> dict[str, Any]:
    enrollment_type = _normalize_enrollment_type(profile.get("tipo_matricula"))
    return {
        "exam_id": None,
        "expedient_id": None,
        "level": _clean(profile.get("nivel")) or _LEVEL_NAME,
        "enrollment_type": enrollment_type,
        "scheme": "TRES_PARCIALES",
        "status": "SIN_ENTREGA",
        "grade": None,
        "result": "PENDIENTE",
        "passing_grade": float(_PASSING_GRADE),
        "observation": "",
        "evaluator": "",
        "graded_at": None,
        "file": None,
        "components": [],
        "required_components": len(_component_specs(enrollment_type)),
        "submitted_components": 0,
        "staged_components": 0,
        "graded_components": 0,
        "can_edit": False,
        "edit_deadline": None,
        "seconds_remaining": 0,
        "edit_window_minutes": _EDIT_WINDOW_MINUTES,
        "min_file_bytes": _MIN_FILE_BYTES,
        "max_file_bytes": _MAX_FILE_BYTES,
        "enrollment": {
            "enabled": True,
            "enrollment_id": int(profile["carrera_x_estud_num"]),
            "english_career_code": _clean(profile.get("codigo_carrera")),
            "english_career": _clean(profile.get("carrera_ingles")),
            "subject_code": _clean(profile.get("codigo_materia")),
            "subject": _clean(profile.get("nivel")) or _LEVEL_NAME,
            "period_code": _clean(profile.get("codigo_periodo")),
            "period": _period_label(
                _clean(profile.get("codigo_periodo")),
                _clean(profile.get("detalle_periodo")),
            ),
            "parallel": _clean(profile.get("paralelo")),
        },
        "student": {
            "code": int(profile["codigo_estud"]),
            "identification": _clean(profile.get("cedula")),
            "name": _clean(profile.get("estudiante")),
            "career": _clean(profile.get("carrera")),
            "career_code": _clean(profile.get("codigo_carrera_principal")),
            "period_code": _clean(profile.get("codigo_periodo")),
        },
    }


def _apply_reviewer_profile(payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    payload["student"].update(
        {
            "code": int(profile["codigo_estud"]),
            "identification": _clean(profile.get("cedula")),
            "name": _clean(profile.get("estudiante")),
            "career": _clean(profile.get("carrera")),
            "career_code": _clean(profile.get("codigo_carrera_principal")),
            "period_code": _clean(profile.get("codigo_periodo")),
        }
    )
    payload["enrollment"].update(
        {
            "enabled": True,
            "enrollment_id": int(profile["carrera_x_estud_num"]),
            "english_career_code": _clean(profile.get("codigo_carrera")),
            "english_career": _clean(profile.get("carrera_ingles")),
            "subject_code": _clean(profile.get("codigo_materia")),
            "subject": _clean(profile.get("nivel")) or _LEVEL_NAME,
            "period_code": _clean(profile.get("codigo_periodo")),
            "period": _period_label(
                _clean(profile.get("codigo_periodo")),
                _clean(profile.get("detalle_periodo")),
            ),
            "parallel": _clean(profile.get("paralelo")),
        }
    )
    return payload


def _exam_select(where_clause: str) -> str:
    return f"""
        SELECT
            e.ExamenInglesId AS examen_id,
            e.ExpedienteEstudiantilId AS expediente_id,
            e.CodigoEstud AS codigo_estud,
            e.NumeroIdentificacion AS numero_identificacion,
            p.ApellidosNombres AS estudiante,
            COALESCE(carrera_principal.codigo_carrera, e.CodigoCarrera) AS codigo_carrera,
            e.CodigoCarrera AS codigo_carrera_ingles,
            e.CodigoMateria AS codigo_materia,
            e.CodigoPeriodo AS codigo_periodo,
            e.CarreraXEstudNum AS carrera_x_estud_num,
            e.Paralelo AS paralelo,
            e.Nivel AS nivel,
            e.TipoMatricula AS tipo_matricula,
            e.NotaFinal AS nota_final,
            e.Estado AS estado,
            e.Observacion AS observacion,
            e.NombreEvaluador AS nombre_evaluador,
            e.FechaCalificacion AS fecha_calificacion,
            COALESCE(carrera_principal.carrera, c.Nombre_Basica, TRY_CONVERT(NVARCHAR(100), e.CodigoCarrera)) AS carrera,
            COALESCE(c.Nombre_Basica, TRY_CONVERT(NVARCHAR(100), e.CodigoCarrera)) AS carrera_ingles,
            COALESCE(pensum.Nomb_Materia, e.Nivel, N'{_LEVEL_NAME}') AS materia,
            periodo.Detalle_Periodo AS detalle_periodo
        FROM ing.ExamenIngles e
        INNER JOIN exp.ExpedienteEstudiantil ex ON ex.ExpedienteEstudiantilId = e.ExpedienteEstudiantilId
        INNER JOIN core.Persona p ON p.PersonaId = ex.PersonaId
        LEFT JOIN INTECBDD.dbo.CARRERAS c
            ON TRY_CONVERT(INT, c.Cod_AnioBasica) = TRY_CONVERT(INT, e.CodigoCarrera)
        LEFT JOIN INTECBDD.dbo.PENSUM pensum
            ON TRY_CONVERT(INT, pensum.Cod_AnioBasica) = TRY_CONVERT(INT, e.CodigoCarrera)
           AND TRY_CONVERT(INT, pensum.codigo_materia) = TRY_CONVERT(INT, e.CodigoMateria)
        LEFT JOIN INTECBDD.dbo.PERIODO periodo
            ON TRY_CONVERT(INT, periodo.cod_periodo) = TRY_CONVERT(INT, e.CodigoPeriodo)
        OUTER APPLY
        (
            SELECT TOP (1)
                TRY_CONVERT(INT, cp.Cod_AnioBasica) AS codigo_carrera,
                LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), cp.Nombre_Basica))) AS carrera
            FROM INTECBDD.dbo.CARRERAXESTUD cxp
            INNER JOIN INTECBDD.dbo.CARRERAS cp
                ON TRY_CONVERT(INT, cp.Cod_AnioBasica) = TRY_CONVERT(INT, cxp.cod_anio_Basica)
            WHERE TRY_CONVERT(BIGINT, cxp.codigo_estud) = TRY_CONVERT(BIGINT, e.CodigoEstud)
              AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(NVARCHAR(30), cp.tp_escuela), N'')))) <> N'IDIOMA'
            ORDER BY TRY_CONVERT(INT, cxp.codigo_periodo) DESC,
                     cxp.Fecha_Matricula DESC,
                     TRY_CONVERT(BIGINT, cxp.num) DESC
        ) carrera_principal
        WHERE {where_clause}
    """


def _load_student_exam(profile: dict[str, Any], audit_user: str) -> dict[str, Any]:
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        exam_id = _ensure_exam(cursor, profile, audit_user)
        conn.commit()
        cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
        row = cursor.fetchone()
        component_rows = _load_component_rows(cursor, [exam_id]).get(exam_id, [])
    if not row:
        raise HTTPException(status_code=500, detail="No se pudo abrir el expediente de Inglés.")
    payload = _row_payload(row, component_rows, include_student=True)
    payload["student"]["career"] = profile["carrera"] or payload["student"]["career"]
    return payload


def _refresh_exam_status(cursor: Any, exam_id: int, audit_user: str) -> tuple[Decimal | None, bool]:
    cursor.execute("SELECT TipoMatricula FROM ing.ExamenIngles WHERE ExamenInglesId = ?", exam_id)
    exam = cursor.fetchone()
    if not exam:
        raise HTTPException(status_code=404, detail="No existe el examen de Inglés.")
    enrollment_type = _normalize_enrollment_type(exam[0])
    cursor.execute(
        """
        SELECT componente.Codigo, componente.Nota,
               CASE WHEN EXISTS
               (
                   SELECT 1 FROM ing.CargaExamenIngles carga
                   WHERE carga.ComponenteExamenInglesId = componente.ComponenteExamenInglesId
                     AND carga.Activo = 1 AND carga.Estado IN ('CONFIRMADO', 'CARGADO')
               ) THEN 1 ELSE 0 END AS tiene_archivo
        FROM ing.ComponenteExamenIngles componente
        WHERE componente.ExamenInglesId = ? AND componente.Activo = 1
        """,
        exam_id,
    )
    rows = cursor.fetchall()
    grades = {_clean(row.Codigo): row.Nota for row in rows}
    final_grade = _aggregate_component_grade(enrollment_type, grades)
    required_count = len(_component_specs(enrollment_type))
    submitted_count = sum(1 for row in rows if int(row.tiene_archivo or 0) == 1)
    complete = final_grade is not None and len(rows) == required_count
    if complete:
        state = "APROBADO" if final_grade >= _PASSING_GRADE else "REPROBADO"
    elif submitted_count >= required_count:
        state = "ENTREGADO"
    elif submitted_count > 0:
        state = "EN_PROCESO"
    else:
        state = "PENDIENTE"
    cursor.execute(
        """
        UPDATE ing.ExamenIngles
           SET NotaFinal = ?, Estado = ?,
               FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
         WHERE ExamenInglesId = ?
        """,
        final_grade,
        state,
        audit_user,
        exam_id,
    )
    return final_grade, complete


_ACADEMIC_EXAM_COLUMNS = {
    "P1": "P1Examen",
    "P2": "P2Examen",
    "P3": "P3Examen",
}


def _sync_academic_component_grade(
    cursor: Any,
    exam_id: int,
    component_code: str,
    grade: Decimal,
    audit_user: str,
) -> Decimal | None:
    exam_column = _ACADEMIC_EXAM_COLUMNS.get(component_code)
    if not exam_column:
        raise HTTPException(status_code=400, detail="El parcial indicado no es válido.")

    cursor.execute(
        """
        SELECT CarreraXEstudNum, CodigoEstud, CodigoCarrera, CodigoMateria, CodigoPeriodo, Paralelo
        FROM ing.ExamenIngles
        WHERE ExamenInglesId = ? AND Activo = 1
        """,
        exam_id,
    )
    exam = cursor.fetchone()
    if not exam or exam.CarreraXEstudNum is None:
        raise HTTPException(status_code=409, detail="El expediente no está enlazado con una matrícula de Inglés válida.")

    exact_where = """
        TRY_CONVERT(BIGINT, num) = ?
        AND TRY_CONVERT(BIGINT, codigo_estud) = ?
        AND TRY_CONVERT(INT, cod_anio_Basica) = ?
        AND TRY_CONVERT(INT, codigo_materia) = ?
        AND TRY_CONVERT(INT, codigo_periodo) = ?
        AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(NVARCHAR(20), paralelo), N'')))) = ?
    """
    exact_params = [
        int(exam.CarreraXEstudNum),
        int(exam.CodigoEstud),
        int(exam.CodigoCarrera),
        int(exam.CodigoMateria),
        int(exam.CodigoPeriodo),
        _clean(exam.Paralelo).upper(),
    ]
    cursor.execute(
        f"""
        UPDATE INTECBDD.dbo.CARRERAXESTUD
           SET {exam_column} = ?, Usuario = ?
         WHERE {exact_where}
        """,
        grade,
        audit_user[:10],
        *exact_params,
    )
    if int(cursor.rowcount or 0) != 1:
        raise HTTPException(
            status_code=409,
            detail="La matrícula de Inglés cambió o ya no está disponible; actualice la pantalla antes de calificar.",
        )

    cursor.execute(
        f"""
        SELECT P1Tareas, P1Proyectos, P1Examen,
               P2Tareas, P2Proyectos, P2Examen,
               P3Tareas, P3Proyectos, P3Examen,
               Recuperacion
        FROM INTECBDD.dbo.CARRERAXESTUD
        WHERE {exact_where}
        """,
        *exact_params,
    )
    academic = cursor.fetchone()
    if not academic:
        raise HTTPException(status_code=409, detail="No se pudo volver a consultar la matrícula de Inglés actualizada.")

    def number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    calculation = calculate_regular_grade_with_recovery(
        (
            (number(academic.P1Tareas), number(academic.P1Proyectos), number(academic.P1Examen)),
            (number(academic.P2Tareas), number(academic.P2Proyectos), number(academic.P2Examen)),
            (number(academic.P3Tareas), number(academic.P3Proyectos), number(academic.P3Examen)),
        ),
        number(academic.Recuperacion),
    )
    final_grade = Decimal(str(calculation.final)).quantize(Decimal("0.01")) if calculation.final is not None else None
    cursor.execute(
        f"""
        UPDATE INTECBDD.dbo.CARRERAXESTUD
           SET promP1 = ?, promP2 = ?, promP3 = ?,
               Promedio = ?, PromedioFinal = ?,
               caprueba = ?, Usuario = ?
         WHERE {exact_where}
        """,
        calculation.partials[0],
        calculation.partials[1],
        calculation.partials[2],
        calculation.final,
        calculation.final,
        "A" if calculation.final is not None and calculation.final >= 7 else "R" if calculation.final is not None else None,
        audit_user[:10],
        *exact_params,
    )
    if int(cursor.rowcount or 0) != 1:
        raise HTTPException(status_code=409, detail="No se pudo recalcular la matrícula académica de Inglés.")
    return final_grade


def _sync_titulation_english(identification: str, approved: bool, audit_user: str) -> None:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE E
                   SET InglesA2Cumple = ?, FechaActualizacion = SYSDATETIME(), UsuarioActualizacion = ?
                FROM tit.ExpedienteTitulacion E
                INNER JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
                WHERE REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(VARCHAR(30), ER.NumeroIdentificacion))), '-', ''), ' ', '') = ?
                """,
                1 if approved else 0,
                audit_user,
                re.sub(r"\D+", "", identification),
            )
            conn.commit()
    except (RuntimeError, pyodbc.Error):
        # El expediente de Inglés es la fuente primaria. Titulación se sincroniza
        # cuando la base complementaria está disponible.
        return


@router.get("/student")
def student_exam(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> dict[str, Any]:
    return _load_student_exam(_student_profile(current_user), current_user.login)


@router.post("/student/upload-session")
def create_student_upload_session(
    payload: UploadSessionPayload,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> dict[str, Any]:
    filename = _safe_filename(payload.filename)
    content_type = _safe_video_content_type(payload.content_type)
    component_code = _clean(payload.component_code).upper()
    profile = _student_profile(current_user)
    upload_id = uuid4()

    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        exam_id = _ensure_exam(cursor, profile, current_user.login)
        cursor.execute(
            """
            SELECT ComponenteExamenInglesId, Nombre, Nota,
                   FechaInicioActividad, FechaLimiteActividad, EstadoRevision
            FROM ing.ComponenteExamenIngles
            WHERE ExamenInglesId = ? AND Codigo = ? AND Activo = 1
            """,
            exam_id,
            component_code,
        )
        component = cursor.fetchone()
        if not component:
            raise HTTPException(status_code=400, detail="El componente solicitado no corresponde al tipo de matrícula del estudiante.")
        if component.Nota is not None:
            raise HTTPException(status_code=409, detail="Este componente ya fue calificado y no admite reemplazos.")
        _require_activity_open(component.FechaInicioActividad, component.FechaLimiteActividad)
        component_id = int(component.ComponenteExamenInglesId)
        cursor.execute(
            """
            SELECT TOP (1) Estado, FechaLimiteEdicion
            FROM ing.CargaExamenIngles
            WHERE ComponenteExamenInglesId = ? AND Activo = 1
              AND Estado IN ('PENDIENTE_CONFIRMACION', 'CONFIRMADO', 'CARGADO')
            ORDER BY NumeroVersion DESC
            """,
            component_id,
        )
        previous = cursor.fetchone()
        now = _utc_now_naive()
        if previous and _clean(previous.Estado) in {"CONFIRMADO", "CARGADO"}:
            raise HTTPException(
                status_code=409,
                detail="La entrega definitiva ya fue confirmada y no admite reemplazo ni eliminación.",
            )
        if (
            previous
            and _clean(previous.Estado) == "PENDIENTE_CONFIRMACION"
            and isinstance(previous.FechaLimiteEdicion, datetime)
            and now >= previous.FechaLimiteEdicion
        ):
            raise HTTPException(
                status_code=409,
                detail="Finalizó el plazo de reemplazo. Revise el video cargado y confirme la entrega definitiva.",
            )
        cursor.execute(
            "SELECT ISNULL(MAX(NumeroVersion), 0) + 1 FROM ing.CargaExamenIngles WITH (UPDLOCK, HOLDLOCK) WHERE ExamenInglesId = ?",
            exam_id,
        )
        version = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT ExpedienteEstudiantilId FROM ing.ExamenIngles WHERE ExamenInglesId = ?",
            exam_id,
        )
        expediente_id = int(cursor.fetchone()[0])
        graph_expedient = prepare_graph_expedient(
            module_code="INGLES",
            identification=profile["cedula"],
            student_code=profile["codigo_estud"],
            student_name=profile["estudiante"],
            student_email=profile["correo"],
            base_origin="INTEC_EXPEDIENTE_ESTUDIANTIL",
            schema_origin="ing",
            table_origin="ExamenIngles",
            origin_id=exam_id,
            expedient_code=(
                f"ING-{profile['codigo_estud']}-"
                f"{profile['codigo_periodo']}-{profile['codigo_materia']}"
            ),
            audit_user=current_user.login,
        )
        folder = _clean(graph_expedient["folder_path"])
        cloud_filename = f"v{version:02d}-{str(upload_id)[:8]}-{filename}"
        period_folder = _safe_folder_part(
            f"PERIODO {profile['codigo_periodo']} - {profile['detalle_periodo']}",
            f"PERIODO {profile['codigo_periodo']}",
            max_length=70,
        )
        subject_folder = _safe_folder_part(
            f"ASIGNATURA {profile['codigo_materia']} - {profile['nivel']}",
            f"ASIGNATURA {profile['codigo_materia']}",
            max_length=70,
        )
        component_folder = _safe_folder_part(
            f"{component_code} - {_clean(component.Nombre)}",
            component_code,
            max_length=45,
        )
        upload_folder = f"{folder}/{period_folder}/{subject_folder}/{component_folder}"
        graph_path = f"{upload_folder}/{cloud_filename}"
        _ensure_graph_folder(upload_folder)
        try:
            graph_session = _create_graph_upload_session(graph_path)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo preparar la carga en Microsoft Graph: {exc}") from exc

        try:
            register_graph_document_upload(
                session_id=upload_id,
                expedient_graph_id=int(graph_expedient["expedient_graph_id"]),
                document_type_code="EVIDENCIA_EXAMEN_INGLES",
                original_filename=filename,
                cloud_filename=cloud_filename,
                graph_path=graph_path,
                content_type=content_type,
                expected_size=payload.size,
                upload_url=_clean(graph_session.get("uploadUrl")),
                expires_at=graph_session.get("expirationDateTime"),
                audit_user=current_user.login,
            )
        except (RuntimeError, ValueError, pyodbc.Error) as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo registrar la sesion documental: {exc}") from exc

        cursor.execute(
            """
            INSERT INTO ing.CargaExamenIngles
                (CargaExamenInglesId, ExamenInglesId, ComponenteExamenInglesId, NumeroVersion, NombreArchivoOriginal,
                 NombreArchivoNube, RutaGraph, ContentType, TamanoEsperado, UsuarioCarga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            str(upload_id),
            exam_id,
            component_id,
            version,
            filename,
            cloud_filename,
            graph_path,
            content_type,
            payload.size,
            current_user.login,
        )
        _audit_event(
            cursor,
            exam_id,
            "CARGA_INICIADA",
            current_user.login,
            component_id=component_id,
            upload_id=upload_id,
            previous_state=_clean(component.EstadoRevision),
            new_state="CARGA_INICIADA",
            detail={"filename": filename, "size": payload.size, "content_type": content_type},
        )
        conn.commit()

    return {
        "upload_id": str(upload_id),
        "upload_url": graph_session.get("uploadUrl"),
        "expires_at": graph_session.get("expirationDateTime"),
        "chunk_size": 10 * 1024 * 1024,
        "min_file_bytes": _MIN_FILE_BYTES,
        "max_file_bytes": _MAX_FILE_BYTES,
        "version": version,
        "component_code": component_code,
    }


@router.post("/student/finalize")
def finalize_student_upload(
    payload: UploadFinalizePayload,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> dict[str, Any]:
    profile = _student_profile(current_user)
    replaced_graph_item_id = ""
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        cursor.execute(
            """
                SELECT
                    ce.CargaExamenInglesId, ce.ExamenInglesId, ce.NumeroVersion,
                    ce.NombreArchivoOriginal, ce.RutaGraph, ce.ContentType, ce.TamanoEsperado,
                    ce.Estado AS EstadoCarga,
                    ce.ComponenteExamenInglesId, componente.Codigo AS CodigoComponente,
                    componente.Nombre AS NombreComponente, componente.Nota AS NotaComponente,
                    componente.EstadoRevision, componente.FechaInicioActividad,
                    componente.FechaLimiteActividad,
                    e.ExpedienteEstudiantilId, e.CodigoEstud, e.CarreraXEstudNum
            FROM ing.CargaExamenIngles ce
            INNER JOIN ing.ExamenIngles e ON e.ExamenInglesId = ce.ExamenInglesId
            INNER JOIN ing.ComponenteExamenIngles componente
                ON componente.ComponenteExamenInglesId = ce.ComponenteExamenInglesId
            WHERE ce.CargaExamenInglesId = ?
            """,
            str(payload.upload_id),
        )
        upload = cursor.fetchone()
        if (
            not upload
            or int(upload.CodigoEstud) != profile["codigo_estud"]
            or int(upload.CarreraXEstudNum or 0) != profile["carrera_x_estud_num"]
        ):
            raise HTTPException(status_code=404, detail="No existe una carga pendiente para este estudiante.")
        if upload.NotaComponente is not None:
            raise HTTPException(status_code=409, detail="Este parcial ya fue calificado y no admite reemplazos.")
        if _clean(upload.EstadoCarga) != "CARGA_INICIADA":
            raise HTTPException(status_code=409, detail="Esta sesión de carga ya fue procesada.")
        _require_activity_open(upload.FechaInicioActividad, upload.FechaLimiteActividad)

        try:
            graph_item = _graph_item_by_path(_clean(upload.RutaGraph))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo verificar el archivo en Microsoft Graph: {exc}") from exc

        graph_item_id = _clean(graph_item.get("id"))
        graph_size = int(graph_item.get("size") or 0)
        graph_file = graph_item.get("file") if isinstance(graph_item.get("file"), dict) else None
        graph_mime = _clean((graph_file or {}).get("mimeType"))
        if (
            not graph_item_id
            or graph_file is None
            or graph_size != int(upload.TamanoEsperado)
            or graph_size < _MIN_FILE_BYTES
            or graph_size > _MAX_FILE_BYTES
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "La carga no superó la validación de integridad: debe ser un video completo "
                    "de 50 MB a 2 GB y coincidir con el tamaño informado."
                ),
            )
        _safe_filename(_clean(upload.NombreArchivoOriginal))
        mime_type = _safe_video_content_type(graph_mime or _clean(upload.ContentType))
        hash_values = (graph_file or {}).get("hashes") or {}
        integrity_hash = next(
            (
                _clean(hash_values.get(key))
                for key in ("sha256Hash", "sha1Hash", "quickXorHash")
                if _clean(hash_values.get(key))
            ),
            "",
        ) or _clean(graph_item.get("eTag")) or _clean(graph_item.get("cTag"))
        if not integrity_hash:
            raise HTTPException(
                status_code=409,
                detail="Microsoft Graph no devolvió una referencia de integridad para el video.",
            )

        cursor.execute(
            """
            SELECT TOP (1) CargaExamenInglesId, Estado, FechaLimiteEdicion, GraphItemId
            FROM ing.CargaExamenIngles
            WHERE ComponenteExamenInglesId = ? AND Activo = 1
              AND Estado IN ('PENDIENTE_CONFIRMACION', 'CONFIRMADO', 'CARGADO')
            ORDER BY NumeroVersion DESC
            """,
            int(upload.ComponenteExamenInglesId),
        )
        previous = cursor.fetchone()
        now = _utc_now_naive()
        if previous and _clean(previous.Estado) in {"CONFIRMADO", "CARGADO"}:
            _delete_graph_item(graph_item_id)
            cursor.execute(
                "UPDATE ing.CargaExamenIngles SET Estado = 'EXPIRADO', Activo = 0 WHERE CargaExamenInglesId = ?",
                str(payload.upload_id),
            )
            conn.commit()
            raise HTTPException(
                status_code=409,
                detail="La entrega definitiva ya fue confirmada y no admite reemplazo ni eliminación.",
            )
        deadline = (
            previous.FechaLimiteEdicion
            if previous and isinstance(previous.FechaLimiteEdicion, datetime)
            else now + timedelta(minutes=_EDIT_WINDOW_MINUTES)
        )
        if previous and now >= deadline:
            _delete_graph_item(graph_item_id)
            cursor.execute(
                "UPDATE ing.CargaExamenIngles SET Estado = 'EXPIRADO', Activo = 0 WHERE CargaExamenInglesId = ?",
                str(payload.upload_id),
            )
            conn.commit()
            raise HTTPException(status_code=409, detail="La ventana de reemplazo de 15 minutos ya finalizó.")
        if previous:
            replaced_graph_item_id = _clean(previous.GraphItemId)

        document_type_id = _catalog_id(cursor, "cat.TipoDocumento", "EVIDENCIA_EXAMEN_INGLES", "TipoDocumentoId")
        loaded_state_id = _catalog_id(cursor, "cat.EstadoDocumento", "CARGADO", "EstadoDocumentoId")
        cursor.execute(
            """
            SELECT TOP (1) documento.DocumentoExpedienteId, documento.VersionActual
            FROM ing.CargaExamenIngles carga
            INNER JOIN doc.DocumentoExpediente documento
                ON documento.DocumentoExpedienteId = carga.DocumentoExpedienteId
            WHERE carga.ComponenteExamenInglesId = ? AND documento.Activo = 1
            ORDER BY carga.NumeroVersion DESC
            """,
            int(upload.ComponenteExamenInglesId),
        )
        document = cursor.fetchone()
        document_observation = (
            f"Carga temporal de Inglés: {_clean(upload.NombreComponente)}; "
            "pendiente de confirmación definitiva del estudiante."
        )
        web_url = _clean(graph_item.get("webUrl"))
        if document:
            document_id = int(document.DocumentoExpedienteId)
            document_version = int(document.VersionActual or 0) + 1
            cursor.execute(
                """
                UPDATE doc.DocumentoExpediente
                   SET EstadoDocumentoId = ?, NombreArchivo = ?, RutaNube = ?, ContentType = ?,
                       TamanoBytes = ?, VersionActual = ?, ObservacionActual = ?,
                       FechaCarga = SYSUTCDATETIME(), UsuarioCarga = ?, FechaRevision = NULL, UsuarioRevision = NULL
                 WHERE DocumentoExpedienteId = ?
                """,
                loaded_state_id,
                _clean(upload.NombreArchivoOriginal),
                web_url,
                mime_type,
                graph_size,
                document_version,
                document_observation,
                current_user.login,
                document_id,
            )
        else:
            document_version = 1
            cursor.execute(
                """
                INSERT INTO doc.DocumentoExpediente
                    (ExpedienteEstudiantilId, TipoDocumentoId, EstadoDocumentoId, NombreArchivo,
                     RutaNube, ContentType, TamanoBytes, OrigenCarga, VersionActual,
                     ObservacionActual, UsuarioCarga)
                OUTPUT INSERTED.DocumentoExpedienteId
                VALUES (?, ?, ?, ?, ?, ?, ?, 'MICROSOFT_GRAPH', 1, ?, ?)
                """,
                int(upload.ExpedienteEstudiantilId),
                document_type_id,
                loaded_state_id,
                _clean(upload.NombreArchivoOriginal),
                web_url,
                mime_type,
                graph_size,
                document_observation,
                current_user.login,
            )
            document_id = int(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO doc.DocumentoVersion
                (DocumentoExpedienteId, NumeroVersion, NombreArchivo, RutaNube, ContentType,
                 TamanoBytes, Observacion, UsuarioCarga)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            document_id,
            document_version,
            _clean(upload.NombreArchivoOriginal),
            web_url,
            mime_type,
            graph_size,
            f"Versión de {_clean(upload.NombreComponente)} de Inglés.",
            current_user.login,
        )
        cursor.execute(
            """
            UPDATE ing.CargaExamenIngles
               SET Estado = 'REEMPLAZADO', Activo = 0
             WHERE ComponenteExamenInglesId = ?
               AND Estado = 'PENDIENTE_CONFIRMACION' AND Activo = 1
            """,
            int(upload.ComponenteExamenInglesId),
        )
        cursor.execute(
            """
            UPDATE ing.CargaExamenIngles
               SET DocumentoExpedienteId = ?, TamanoBytes = ?, GraphItemId = ?, GraphWebUrl = ?,
                   Estado = 'PENDIENTE_CONFIRMACION', FechaCarga = SYSUTCDATETIME(),
                   FechaLimiteEdicion = ?, IntegridadValidada = 1, HashIntegridad = ?, Activo = 1
             WHERE CargaExamenInglesId = ?
            """,
            document_id,
            graph_size,
            graph_item_id,
            web_url,
            deadline,
            integrity_hash,
            str(payload.upload_id),
        )
        cursor.execute(
            """
            UPDATE ing.ComponenteExamenIngles
               SET Estado = 'PENDIENTE_CONFIRMACION', EstadoRevision = 'PENDIENTE_CONFIRMACION',
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            current_user.login,
            int(upload.ComponenteExamenInglesId),
        )
        _audit_event(
            cursor,
            int(upload.ExamenInglesId),
            "CARGA_VALIDADA",
            current_user.login,
            component_id=int(upload.ComponenteExamenInglesId),
            upload_id=payload.upload_id,
            previous_state=_clean(upload.EstadoRevision),
            new_state="PENDIENTE_CONFIRMACION",
            detail={
                "size": graph_size,
                "content_type": mime_type,
                "integrity_hash": integrity_hash,
                "edit_deadline": deadline,
            },
        )
        _refresh_exam_status(cursor, int(upload.ExamenInglesId), current_user.login)
        conn.commit()

    try:
        graph_document = complete_graph_document_upload(
            session_id=payload.upload_id,
            graph_item=graph_item,
            edit_deadline=deadline,
            audit_user=current_user.login,
        )
        set_graph_document_origin(int(graph_document["document_graph_id"]), document_id)
    except (RuntimeError, ValueError, pyodbc.Error) as exc:
        try:
            mark_graph_document_upload_error(payload.upload_id, str(exc), current_user.login)
        except (RuntimeError, pyodbc.Error):
            pass
        raise HTTPException(status_code=502, detail=f"El archivo se cargo, pero no se pudo enlazar con el registro Graph: {exc}") from exc

    if replaced_graph_item_id and replaced_graph_item_id != graph_item_id:
        try:
            _delete_graph_item(replaced_graph_item_id)
        except httpx.HTTPError:
            # El nuevo video ya está registrado; la limpieza del temporal anterior
            # no debe invalidar una carga íntegra.
            pass

    return _load_student_exam(profile, current_user.login)


@router.post("/student/confirm")
def confirm_student_delivery(
    payload: UploadConfirmPayload,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> dict[str, Any]:
    profile = _student_profile(current_user)
    component_code = _clean(payload.component_code).upper()
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        cursor.execute(
            """
            SELECT
                carga.CargaExamenInglesId, carga.Estado AS EstadoCarga,
                carga.IntegridadValidada, carga.DocumentoExpedienteId,
                componente.ComponenteExamenInglesId, componente.Codigo,
                componente.EstadoRevision, componente.FechaInicioActividad,
                componente.FechaLimiteActividad,
                examen.ExamenInglesId, examen.ExpedienteEstudiantilId,
                examen.CodigoEstud, examen.CarreraXEstudNum
            FROM ing.CargaExamenIngles carga
            INNER JOIN ing.ComponenteExamenIngles componente
                ON componente.ComponenteExamenInglesId = carga.ComponenteExamenInglesId
            INNER JOIN ing.ExamenIngles examen
                ON examen.ExamenInglesId = carga.ExamenInglesId
            WHERE carga.CargaExamenInglesId = ?
              AND componente.Codigo = ?
              AND carga.Activo = 1
            """,
            str(payload.upload_id),
            component_code,
        )
        delivery = cursor.fetchone()
        if (
            not delivery
            or int(delivery.CodigoEstud) != profile["codigo_estud"]
            or int(delivery.CarreraXEstudNum or 0) != profile["carrera_x_estud_num"]
        ):
            raise HTTPException(status_code=404, detail="No existe una carga pendiente para confirmar.")
        current_state = _clean(delivery.EstadoCarga)
        if current_state in {"CONFIRMADO", "CARGADO"}:
            return _load_student_exam(profile, current_user.login)
        if current_state != "PENDIENTE_CONFIRMACION":
            raise HTTPException(status_code=409, detail="El video todavía no está listo para confirmación.")
        if not bool(delivery.IntegridadValidada):
            raise HTTPException(status_code=409, detail="El video no cuenta con una validación de integridad correcta.")
        _require_activity_open(delivery.FechaInicioActividad, delivery.FechaLimiteActividad)

        review_state_id = _catalog_id(cursor, "cat.EstadoExpediente", "EN_REVISION", "EstadoExpedienteId")
        cursor.execute(
            """
            UPDATE ing.CargaExamenIngles
               SET Estado = 'CONFIRMADO', FechaConfirmacion = SYSUTCDATETIME(),
                   UsuarioConfirmacion = ?, FechaLimiteEdicion = NULL
             WHERE CargaExamenInglesId = ? AND Estado = 'PENDIENTE_CONFIRMACION' AND Activo = 1
            """,
            current_user.login,
            str(payload.upload_id),
        )
        if int(cursor.rowcount or 0) != 1:
            raise HTTPException(status_code=409, detail="La entrega cambió mientras se confirmaba. Actualice la pantalla.")
        cursor.execute(
            """
            UPDATE ing.ComponenteExamenIngles
               SET Estado = 'ENTREGADO', EstadoRevision = 'PENDIENTE_REVISION',
                   FechaNotificacionDocente = SYSUTCDATETIME(),
                   EstadoNotificacion = 'DISPONIBLE_EN_BANDEJA',
                   DetalleNotificacion = N'Entrega definitiva disponible para revisión docente.',
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            current_user.login,
            int(delivery.ComponenteExamenInglesId),
        )
        if delivery.DocumentoExpedienteId:
            cursor.execute(
                """
                UPDATE doc.DocumentoExpediente
                   SET ObservacionActual = N'Entrega definitiva de evaluación de Inglés.'
                 WHERE DocumentoExpedienteId = ?
                """,
                int(delivery.DocumentoExpedienteId),
            )
        cursor.execute(
            """
            UPDATE exp.ExpedienteEstudiantil
               SET EstadoExpedienteId = ?, FechaActualizacion = SYSUTCDATETIME(),
                   UsuarioActualizacion = ?
             WHERE ExpedienteEstudiantilId = ?
            """,
            review_state_id,
            current_user.login,
            int(delivery.ExpedienteEstudiantilId),
        )
        _refresh_exam_status(cursor, int(delivery.ExamenInglesId), current_user.login)
        _audit_event(
            cursor,
            int(delivery.ExamenInglesId),
            "ENTREGA_CONFIRMADA",
            current_user.login,
            component_id=int(delivery.ComponenteExamenInglesId),
            upload_id=payload.upload_id,
            previous_state=_clean(delivery.EstadoRevision),
            new_state="PENDIENTE_REVISION",
            detail={"notification": "DISPONIBLE_EN_BANDEJA"},
        )
        conn.commit()

    return _load_student_exam(profile, current_user.login)


@router.get("/submissions")
def reviewer_submissions(
    current_user: Annotated[SessionUser, Depends(_REVIEWER_ACCESS)],
    search: Annotated[str, Query(max_length=120)] = "",
    state: Annotated[str, Query(max_length=30)] = "TODOS",
    period_code: Annotated[str, Query(max_length=100)] = "",
    subject_code: Annotated[str, Query(max_length=100)] = "",
) -> dict[str, Any]:
    term = _clean(search)
    normalized_state = _clean(state).upper() or "TODOS"
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        conn.commit()
        periods = _reviewer_periods(cursor, current_user)
        selected_period = _select_reviewer_period(periods, period_code, current_user)
        subjects = _reviewer_subjects(cursor, selected_period, current_user)
        selected_subject = _select_reviewer_subject(subjects, subject_code, current_user)
        selected_subject_info = next(
            (item for item in subjects if _clean(item.get("code")) == selected_subject),
            None,
        )
        enrollments = _reviewer_enrollments(
            cursor,
            selected_period,
            selected_subject,
            current_user,
            term,
        )
        enrollment_ids = [int(item["carrera_x_estud_num"]) for item in enrollments]
        rows: list[Any] = []
        for index in range(0, len(enrollment_ids), 1000):
            chunk = enrollment_ids[index:index + 1000]
            placeholders = ", ".join("?" for _ in chunk)
            cursor.execute(
                _exam_select(
                    f"e.Activo = 1 AND e.CarreraXEstudNum IN ({placeholders})"
                ),
                *chunk,
            )
            rows.extend(cursor.fetchall())
        component_rows = _load_component_rows(
            cursor,
            [int(row.examen_id) for row in rows],
            include_pending_confirmation=False,
        )
    exams_by_enrollment = {
        int(row.carrera_x_estud_num): _row_payload(
            row,
            component_rows.get(int(row.examen_id), []),
            include_student=True,
        )
        for row in rows
    }
    items = []
    for profile in enrollments:
        enrollment_id = int(profile["carrera_x_estud_num"])
        item = exams_by_enrollment.get(enrollment_id) or _virtual_exam_payload(profile)
        item = _apply_reviewer_profile(item, profile)
        if normalized_state in {"PENDIENTE", "APROBADO", "REPROBADO"} and item["result"] != normalized_state:
            continue
        items.append(item)
    return {
        "items": items,
        "enrolled": int(selected_subject_info.get("student_count") or 0) if selected_subject_info else 0,
        "total": sum(1 for item in items if item["submitted_components"] > 0),
        "pending": sum(1 for item in items if item["result"] == "PENDIENTE"),
        "approved": sum(1 for item in items if item["result"] == "APROBADO"),
        "failed": sum(1 for item in items if item["result"] == "REPROBADO"),
        "periods": periods,
        "selected_period_code": selected_period,
        "subjects": subjects,
        "selected_subject_code": selected_subject,
        "reviewer": {"name": current_user.nombres or current_user.login, "role": current_user.rol},
    }


def _authorize_file(cursor: Any, upload_id: UUID, current_user: SessionUser) -> Any:
    cursor.execute(
        """
        SELECT ce.GraphItemId, ce.GraphWebUrl, ce.NombreArchivoOriginal, ce.Estado,
               e.CodigoEstud, e.ExamenInglesId
        FROM ing.CargaExamenIngles ce
        INNER JOIN ing.ExamenIngles e ON e.ExamenInglesId = ce.ExamenInglesId
        WHERE ce.CargaExamenInglesId = ?
          AND ce.Estado IN ('PENDIENTE_CONFIRMACION', 'CONFIRMADO', 'CARGADO')
        """,
        str(upload_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el archivo solicitado.")
    if current_user.rol == "ESTUDIANTE" and int(row.CodigoEstud) != int(current_user.codigo_estud or 0):
        raise HTTPException(status_code=403, detail="No puede acceder al expediente de otro estudiante.")
    if current_user.rol != "ESTUDIANTE" and _clean(row.Estado) not in {"CONFIRMADO", "CARGADO"}:
        raise HTTPException(status_code=404, detail="La entrega todavía no fue confirmada por el estudiante.")
    _require_teacher_exam_scope(cursor, int(row.ExamenInglesId), current_user)
    return row


@router.get("/files/{upload_id}/open")
def open_file(
    upload_id: UUID,
    current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> RedirectResponse:
    if current_user.rol not in {"ESTUDIANTE", "DOCENTE", "ACADEMICO", "ADMINISTRADOR"}:
        raise HTTPException(status_code=403, detail="No tiene permisos para abrir este archivo.")
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        row = _authorize_file(cursor, upload_id, current_user)
    if not _clean(row.GraphWebUrl):
        raise HTTPException(status_code=404, detail="Microsoft Graph no devolvió una dirección de visualización.")
    return RedirectResponse(_clean(row.GraphWebUrl), status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/files/{upload_id}/download")
def download_file(
    upload_id: UUID,
    current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> RedirectResponse:
    if current_user.rol not in {"ESTUDIANTE", "DOCENTE", "ACADEMICO", "ADMINISTRADOR"}:
        raise HTTPException(status_code=403, detail="No tiene permisos para descargar este archivo.")
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        row = _authorize_file(cursor, upload_id, current_user)
    try:
        item = _graph_item(_clean(row.GraphItemId))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener el archivo desde Microsoft Graph: {exc}") from exc
    download_url = _clean(item.get("@microsoft.graph.downloadUrl"))
    if not download_url:
        raise HTTPException(status_code=404, detail="Microsoft Graph no devolvió un enlace temporal de descarga.")
    return RedirectResponse(download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def _review_component_target(
    cursor: Any,
    exam_id: int,
    component_code: str,
    period_code: str,
    current_user: SessionUser,
) -> tuple[Any, Any]:
    _require_teacher_exam_scope(cursor, exam_id, current_user)
    cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
    exam_row = cursor.fetchone()
    if not exam_row:
        raise HTTPException(status_code=404, detail="No existe el examen de Inglés.")
    if _clean(exam_row.codigo_periodo) != _clean(period_code):
        raise HTTPException(status_code=409, detail="El examen no corresponde al período de Idiomas seleccionado.")
    cursor.execute(
        """
        SELECT
            componente.ComponenteExamenInglesId, componente.Nombre,
            componente.Nota, componente.Estado, componente.EstadoRevision,
            componente.NotaBorrador, componente.ObservacionBorrador,
            componente.RubricaBorradorJson, componente.FechaPublicacion,
            carga.CargaExamenInglesId AS upload_id,
            carga.DocumentoExpedienteId AS documento_id
        FROM ing.ComponenteExamenIngles componente
        OUTER APPLY
        (
            SELECT TOP (1) ce.CargaExamenInglesId, ce.DocumentoExpedienteId
            FROM ing.CargaExamenIngles ce
            WHERE ce.ComponenteExamenInglesId = componente.ComponenteExamenInglesId
              AND ce.Activo = 1 AND ce.Estado IN ('CONFIRMADO', 'CARGADO')
            ORDER BY ce.NumeroVersion DESC
        ) carga
        WHERE componente.ExamenInglesId = ? AND componente.Codigo = ? AND componente.Activo = 1
        """,
        exam_id,
        component_code,
    )
    component = cursor.fetchone()
    if not component:
        raise HTTPException(status_code=400, detail="El parcial indicado no pertenece a esta matrícula de Idiomas.")
    if not component.upload_id:
        raise HTTPException(status_code=409, detail="El estudiante todavía no confirmó la entrega definitiva de este parcial.")
    return exam_row, component


def _updated_exam_payload(cursor: Any, exam_id: int) -> tuple[Any, dict[str, Any]]:
    cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No existe el examen de Inglés.")
    component_rows = _load_component_rows(
        cursor,
        [exam_id],
        include_pending_confirmation=False,
    ).get(exam_id, [])
    return row, _row_payload(row, component_rows, include_student=True)


@router.put("/submissions/{exam_id}/draft")
def save_rubric_draft(
    exam_id: int,
    payload: RubricDraftPayload,
    current_user: Annotated[SessionUser, Depends(_REVIEWER_ACCESS)],
) -> dict[str, Any]:
    component_code = _clean(payload.component_code).upper()
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        _, component = _review_component_target(
            cursor,
            exam_id,
            component_code,
            payload.period_code,
            current_user,
        )
        if _clean(component.EstadoRevision) == "PUBLICADO" or component.FechaPublicacion is not None:
            raise HTTPException(status_code=409, detail="La calificación ya fue publicada y se encuentra bloqueada.")
        draft_grade = _rubric_grade(payload)
        evaluator_name = _clean(current_user.nombres) or current_user.login
        previous_state = _clean(component.EstadoRevision)
        cursor.execute(
            """
            UPDATE ing.ComponenteExamenIngles
               SET NotaBorrador = ?, ObservacionBorrador = NULLIF(?, N''),
                   RubricaBorradorJson = ?, EstadoRevision = 'BORRADOR_DOCENTE',
                   CodigoDocEvaluador = ?, NombreEvaluador = ?,
                   FechaBorrador = SYSUTCDATETIME(), UsuarioBorrador = ?,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            draft_grade,
            payload.observation.strip(),
            _rubric_json(payload),
            current_user.codigo_doc,
            evaluator_name,
            current_user.login,
            current_user.login,
            int(component.ComponenteExamenInglesId),
        )
        _audit_event(
            cursor,
            exam_id,
            "BORRADOR_GUARDADO",
            current_user.login,
            component_id=int(component.ComponenteExamenInglesId),
            upload_id=component.upload_id,
            previous_state=previous_state,
            new_state="BORRADOR_DOCENTE",
            detail={"grade": draft_grade, "rubric": _rubric_values(payload)},
        )
        conn.commit()
        _, result = _updated_exam_payload(cursor, exam_id)
    return result


@router.post("/submissions/{exam_id}/publish")
def publish_rubric_grade(
    exam_id: int,
    payload: PublishGradePayload,
    current_user: Annotated[SessionUser, Depends(_REVIEWER_ACCESS)],
) -> dict[str, Any]:
    component_code = _clean(payload.component_code).upper()
    sync_identification = ""
    final_approved = False
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        exam_row, component = _review_component_target(
            cursor,
            exam_id,
            component_code,
            payload.period_code,
            current_user,
        )
        if _clean(component.EstadoRevision) == "PUBLICADO" or component.FechaPublicacion is not None:
            _, result = _updated_exam_payload(cursor, exam_id)
            return result
        if component.NotaBorrador is None or not _parse_rubric_json(component.RubricaBorradorJson):
            raise HTTPException(status_code=409, detail="Guarde primero una rúbrica completa como borrador.")

        grade = Decimal(str(component.NotaBorrador)).quantize(Decimal("0.01"))
        approved = grade >= _PASSING_GRADE
        component_state = "APROBADO" if approved else "REPROBADO"
        document_state = "VALIDADO" if approved else "OBSERVADO"
        document_state_id = _catalog_id(cursor, "cat.EstadoDocumento", document_state, "EstadoDocumentoId")
        evaluator_name = _clean(current_user.nombres) or current_user.login
        previous_state = _clean(component.EstadoRevision)
        cursor.execute(
            """
            UPDATE ing.ComponenteExamenIngles
               SET Nota = NotaBorrador, Estado = ?, EstadoRevision = 'PUBLICADO',
                   Observacion = ObservacionBorrador,
                   CodigoDocEvaluador = ?, NombreEvaluador = ?,
                   FechaCalificacion = SYSUTCDATETIME(), FechaPublicacion = SYSUTCDATETIME(),
                   UsuarioPublicacion = ?, FechaActualizacion = SYSUTCDATETIME(),
                   UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            component_state,
            current_user.codigo_doc,
            evaluator_name,
            current_user.login,
            current_user.login,
            int(component.ComponenteExamenInglesId),
        )
        if component.documento_id:
            cursor.execute(
                """
                UPDATE doc.DocumentoExpediente
                   SET EstadoDocumentoId = ?, ObservacionActual = NULLIF(?, N''),
                       FechaRevision = SYSUTCDATETIME(), UsuarioRevision = ?
                 WHERE DocumentoExpedienteId = ?
                """,
                document_state_id,
                _clean(component.ObservacionBorrador),
                current_user.login,
                int(component.documento_id),
            )
        academic_final = _sync_academic_component_grade(
            cursor,
            exam_id,
            component_code,
            grade,
            current_user.login,
        )
        final_grade, complete = _refresh_exam_status(cursor, exam_id, current_user.login)
        if complete and academic_final is not None:
            final_grade = academic_final
            cursor.execute(
                """
                UPDATE ing.ExamenIngles
                   SET NotaFinal = ?, Estado = ?, FechaActualizacion = SYSUTCDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE ExamenInglesId = ?
                """,
                final_grade,
                "APROBADO" if final_grade >= _PASSING_GRADE else "REPROBADO",
                current_user.login,
                exam_id,
            )
        final_approved = bool(complete and final_grade is not None and final_grade >= _PASSING_GRADE)
        expediente_state = "VALIDADO" if final_approved else "OBSERVADO" if complete else "EN_REVISION"
        expediente_state_id = _catalog_id(cursor, "cat.EstadoExpediente", expediente_state, "EstadoExpedienteId")
        cursor.execute(
            """
            UPDATE ing.ExamenIngles
               SET Observacion = CASE WHEN ? = 1 THEN NULLIF(?, N'') ELSE Observacion END,
                   CodigoDocEvaluador = ?, NombreEvaluador = ?,
                   FechaCalificacion = CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE FechaCalificacion END,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ExamenInglesId = ?
            """,
            1 if complete else 0,
            _clean(component.ObservacionBorrador),
            current_user.codigo_doc,
            evaluator_name,
            1 if complete else 0,
            current_user.login,
            exam_id,
        )
        cursor.execute(
            """
            UPDATE ex
               SET ex.EstadoExpedienteId = ?, ex.FechaActualizacion = SYSUTCDATETIME(),
                   ex.UsuarioActualizacion = ?
            FROM exp.ExpedienteEstudiantil ex
            INNER JOIN ing.ExamenIngles e
                ON e.ExpedienteEstudiantilId = ex.ExpedienteEstudiantilId
            WHERE e.ExamenInglesId = ?
            """,
            expediente_state_id,
            current_user.login,
            exam_id,
        )
        _audit_event(
            cursor,
            exam_id,
            "CALIFICACION_PUBLICADA",
            current_user.login,
            component_id=int(component.ComponenteExamenInglesId),
            upload_id=component.upload_id,
            previous_state=previous_state,
            new_state="PUBLICADO",
            detail={"grade": grade, "approved": approved, "academic_column": f"{component_code}Examen"},
        )
        conn.commit()
        updated, result = _updated_exam_payload(cursor, exam_id)
        sync_identification = _clean(updated.numero_identificacion)

    _sync_titulation_english(sync_identification, final_approved, current_user.login)
    return result


@router.put("/submissions/{exam_id}/grade")
def grade_submission(
    exam_id: int,
    payload: GradePayload,
    current_user: Annotated[SessionUser, Depends(_REVIEWER_ACCESS)],
) -> dict[str, Any]:
    component_code = _clean(payload.component_code).upper()
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        _require_teacher_exam_scope(cursor, exam_id, current_user)
        cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
        exam_row = cursor.fetchone()
        if not exam_row:
            raise HTTPException(status_code=404, detail="No existe el examen de Inglés.")
        if _clean(exam_row.codigo_periodo) != _clean(payload.period_code):
            raise HTTPException(
                status_code=409,
                detail="El examen no corresponde al período de Inglés seleccionado.",
            )
        cursor.execute(
            """
            SELECT componente.ComponenteExamenInglesId, componente.Nombre,
                   carga.CargaExamenInglesId AS upload_id, carga.FechaLimiteEdicion AS fecha_limite_edicion
            FROM ing.ComponenteExamenIngles componente
            OUTER APPLY
            (
                SELECT TOP (1) ce.CargaExamenInglesId, ce.FechaLimiteEdicion
                FROM ing.CargaExamenIngles ce
                WHERE ce.ComponenteExamenInglesId = componente.ComponenteExamenInglesId
                  AND ce.Activo = 1 AND ce.Estado IN ('CONFIRMADO', 'CARGADO')
                ORDER BY ce.NumeroVersion DESC
            ) carga
            WHERE componente.ExamenInglesId = ? AND componente.Codigo = ? AND componente.Activo = 1
            """,
            exam_id,
            component_code,
        )
        component = cursor.fetchone()
        if not component:
            raise HTTPException(status_code=400, detail="El componente no corresponde al tipo de matrícula del estudiante.")
        if not component.upload_id:
            raise HTTPException(status_code=404, detail="El estudiante todavía no entregó el archivo de este componente.")
        deadline = component.fecha_limite_edicion
        if isinstance(deadline, datetime) and _utc_now_naive() < deadline:
            raise HTTPException(status_code=409, detail="La entrega continúa dentro de los 15 minutos de edición del estudiante.")

        grade = payload.grade.quantize(Decimal("0.01"))
        component_approved = grade >= _PASSING_GRADE
        component_state = "APROBADO" if component_approved else "REPROBADO"
        document_state = "VALIDADO" if component_approved else "OBSERVADO"
        document_state_id = _catalog_id(cursor, "cat.EstadoDocumento", document_state, "EstadoDocumentoId")
        evaluator_name = _clean(current_user.nombres) or current_user.login
        cursor.execute(
            """
            UPDATE ing.ComponenteExamenIngles
               SET Nota = ?, NotaBorrador = ?, Estado = ?, EstadoRevision = 'PUBLICADO',
                   Observacion = NULLIF(?, N''), ObservacionBorrador = NULLIF(?, N''),
                   CodigoDocEvaluador = ?, NombreEvaluador = ?, FechaCalificacion = SYSUTCDATETIME(),
                   FechaPublicacion = SYSUTCDATETIME(), UsuarioPublicacion = ?,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            grade,
            grade,
            component_state,
            payload.observation.strip(),
            payload.observation.strip(),
            current_user.codigo_doc,
            evaluator_name,
            current_user.login,
            current_user.login,
            int(component.ComponenteExamenInglesId),
        )
        cursor.execute(
            """
            UPDATE d
               SET d.EstadoDocumentoId = ?, d.ObservacionActual = NULLIF(?, N''),
                   d.FechaRevision = SYSUTCDATETIME(), d.UsuarioRevision = ?
            FROM doc.DocumentoExpediente d
            INNER JOIN ing.CargaExamenIngles ce ON ce.DocumentoExpedienteId = d.DocumentoExpedienteId
            WHERE ce.ComponenteExamenInglesId = ? AND ce.Activo = 1
            """,
            document_state_id,
            payload.observation.strip(),
            current_user.login,
            int(component.ComponenteExamenInglesId),
        )
        academic_final = _sync_academic_component_grade(
            cursor,
            exam_id,
            component_code,
            grade,
            current_user.login,
        )
        final_grade, complete = _refresh_exam_status(cursor, exam_id, current_user.login)
        if complete and academic_final is not None:
            final_grade = academic_final
            cursor.execute(
                """
                UPDATE ing.ExamenIngles
                   SET NotaFinal = ?, Estado = ?, FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                 WHERE ExamenInglesId = ?
                """,
                final_grade,
                "APROBADO" if final_grade >= _PASSING_GRADE else "REPROBADO",
                current_user.login,
                exam_id,
            )
        final_approved = bool(complete and final_grade is not None and final_grade >= _PASSING_GRADE)
        expediente_state = "VALIDADO" if final_approved else "OBSERVADO" if complete else "EN_REVISION"
        expediente_state_id = _catalog_id(cursor, "cat.EstadoExpediente", expediente_state, "EstadoExpedienteId")
        cursor.execute(
            """
            UPDATE ing.ExamenIngles
               SET Observacion = CASE WHEN ? = 1 THEN NULLIF(?, N'') ELSE Observacion END,
                   CodigoDocEvaluador = ?, NombreEvaluador = ?,
                   FechaCalificacion = CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE NULL END,
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ExamenInglesId = ?
            """,
            1 if complete else 0,
            payload.observation.strip(),
            current_user.codigo_doc,
            evaluator_name,
            1 if complete else 0,
            current_user.login,
            exam_id,
        )
        cursor.execute(
            """
            UPDATE ex
               SET ex.EstadoExpedienteId = ?, ex.FechaActualizacion = SYSUTCDATETIME(), ex.UsuarioActualizacion = ?
            FROM exp.ExpedienteEstudiantil ex
            INNER JOIN ing.ExamenIngles e ON e.ExpedienteEstudiantilId = ex.ExpedienteEstudiantilId
            WHERE e.ExamenInglesId = ?
            """,
            expediente_state_id,
            current_user.login,
            exam_id,
        )
        _audit_event(
            cursor,
            exam_id,
            "CALIFICACION_PUBLICADA_LEGACY",
            current_user.login,
            component_id=int(component.ComponenteExamenInglesId),
            upload_id=component.upload_id,
            new_state="PUBLICADO",
            detail={"grade": grade, "component": component_code},
        )
        conn.commit()
        cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
        updated = cursor.fetchone()
        component_rows = _load_component_rows(
            cursor,
            [exam_id],
            include_pending_confirmation=False,
        ).get(exam_id, [])

    _sync_titulation_english(_clean(updated.numero_identificacion), final_approved, current_user.login)
    return _row_payload(updated, component_rows, include_student=True)
