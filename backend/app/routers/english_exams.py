from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

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

_MAX_FILE_BYTES = 1024 * 1024 * 1024
_EDIT_WINDOW_MINUTES = 15
_PASSING_GRADE = Decimal("7.00")
_LEVEL_NAME = "A2+ - INTERMEDIATE"
_GRAPH_ROOT_FOLDER = "EXPEDIENTES INGLES"
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
          AND TRY_CONVERT(INT, cxd.codigo_periodo) = TRY_CONVERT(INT, cx.codigo_periodo)
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_docente.tp_escuela)))) = N'IDIOMA'
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cxd.Paralelo)))) =
              UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), cx.Paralelo))))
    )
"""


class UploadSessionPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=_MAX_FILE_BYTES)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    component_code: str = Field(default="P1", min_length=1, max_length=20)


class UploadFinalizePayload(BaseModel):
    upload_id: UUID


class GradePayload(BaseModel):
    grade: Decimal = Field(ge=0, le=10, max_digits=4, decimal_places=2)
    observation: str = Field(default="", max_length=1500)
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
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pensum.Nomb_Materia)))) = UPPER(?)",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), periodo.Estado)))) = N'A'",
        "(periodo.fechain IS NULL OR periodo.fechain <= CONVERT(DATE, GETDATE()))",
        "(periodo.fechafin IS NULL OR periodo.fechafin >= CONVERT(DATE, GETDATE()))",
        "TRY_CONVERT(BIGINT, cx.num) IS NOT NULL",
    ]
    enrollment_params: list[Any] = [_LEVEL_NAME]
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

    exam_filters = [
        "e.Activo = 1",
        "e.CarreraXEstudNum IS NOT NULL",
        "NULLIF(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), e.CodigoPeriodo))), N'') IS NOT NULL",
    ]
    exam_params: list[Any] = []
    scope_filter, scope_params = _reviewer_scope_filter(current_user)
    if scope_filter:
        exam_filters.append(scope_filter)
        exam_params.extend(scope_params)
    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(NVARCHAR(100), e.CodigoPeriodo) AS codigo_periodo,
            COALESCE(
                NULLIF(MAX(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pe.Detalle_Periodo)))), N''),
                TRY_CONVERT(NVARCHAR(100), e.CodigoPeriodo)
            ) AS detalle_periodo,
            MAX(COALESCE(
                TRY_CONVERT(INT, pe.Orden),
                TRY_CONVERT(INT, pe.cod_periodo),
                TRY_CONVERT(INT, e.CodigoPeriodo),
                0
            )) AS periodo_orden,
            COUNT(DISTINCT e.ExamenInglesId) AS total_estudiantes
        FROM ing.ExamenIngles e
        LEFT JOIN INTECBDD.dbo.PERIODO pe
            ON TRY_CONVERT(INT, pe.cod_periodo) = TRY_CONVERT(INT, e.CodigoPeriodo)
        WHERE {" AND ".join(exam_filters)}
        GROUP BY TRY_CONVERT(NVARCHAR(100), e.CodigoPeriodo)
        """,
        *exam_params,
    )
    for row in cursor.fetchall():
        code = _clean(row.codigo_periodo)
        detail = _clean(row.detalle_periodo)
        existing = period_map.get(code)
        if existing:
            existing["student_count"] = max(existing["student_count"], int(row.total_estudiantes or 0))
            existing["sort_order"] = max(existing["sort_order"], int(row.periodo_orden or 0))
            continue
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


def _reviewer_enrollments(
    cursor: Any,
    selected_period: str,
    current_user: SessionUser,
    search: str = "",
) -> list[dict[str, Any]]:
    if not selected_period:
        return []
    if current_user.rol == "DOCENTE" and current_user.codigo_doc is None:
        return []

    filters = [
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), d.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.Estado)))) = N'A'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), carrera_ingles.tp_escuela)))) = N'IDIOMA'",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pensum.Nomb_Materia)))) = UPPER(?)",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), periodo.Estado)))) = N'A'",
        "(periodo.fechain IS NULL OR periodo.fechain <= CONVERT(DATE, GETDATE()))",
        "(periodo.fechafin IS NULL OR periodo.fechafin >= CONVERT(DATE, GETDATE()))",
        "TRY_CONVERT(BIGINT, cx.num) IS NOT NULL",
        "LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), cx.codigo_periodo))) = ?",
    ]
    params: list[Any] = [_LEVEL_NAME, selected_period]
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
            codigo_periodo, detalle_periodo, paralelo, tipo_matricula,
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


def _safe_folder_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._ -]+", "_", _clean(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:120]


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
                Nota DECIMAL(4,2) NULL,
                Estado VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ComponenteExamenIngles_Estado DEFAULT 'PENDIENTE',
                Observacion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
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
                CONSTRAINT UQ_ComponenteExamenIngles_Codigo UNIQUE (ExamenInglesId, Codigo)
            );
            CREATE INDEX IX_ComponenteExamenIngles_Activo
                ON ing.ComponenteExamenIngles(ExamenInglesId, Activo, NumeroParcial);
        END;

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
                UsuarioCarga NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
                Activo BIT NOT NULL CONSTRAINT DF_CargaExamenIngles_Activo DEFAULT 0,
                CONSTRAINT FK_CargaExamenIngles_Examen FOREIGN KEY (ExamenInglesId)
                    REFERENCES ing.ExamenIngles(ExamenInglesId),
                CONSTRAINT FK_CargaExamenIngles_Componente FOREIGN KEY (ComponenteExamenInglesId)
                    REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId),
                CONSTRAINT FK_CargaExamenIngles_Documento FOREIGN KEY (DocumentoExpedienteId)
                    REFERENCES doc.DocumentoExpediente(DocumentoExpedienteId),
                CONSTRAINT CK_CargaExamenIngles_Tamano CHECK (TamanoEsperado > 0 AND TamanoEsperado <= 1073741824)
            );
            CREATE UNIQUE INDEX UX_CargaExamenIngles_Version
                ON ing.CargaExamenIngles(ExamenInglesId, NumeroVersion);
            CREATE INDEX IX_CargaExamenIngles_Actual
                ON ing.CargaExamenIngles(ExamenInglesId, Activo, FechaCarga DESC);
        END;

        IF COL_LENGTH(N'ing.CargaExamenIngles', N'ComponenteExamenInglesId') IS NULL
            ALTER TABLE ing.CargaExamenIngles ADD ComponenteExamenInglesId BIGINT NULL;

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
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), pi.Nomb_Materia)))) = UPPER(?)
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
            _LEVEL_NAME,
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
                f"en Inglés {_LEVEL_NAME}."
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
        "paralelo": _clean(row.paralelo),
        "tipo_matricula": _normalize_enrollment_type(row.tipo_matricula),
    }


def _catalog_id(cursor: Any, table: str, code: str, id_column: str) -> int:
    cursor.execute(f"SELECT {id_column} FROM {table} WHERE Codigo = ?", code)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"No existe el catálogo {table}.{code}")
    return int(row[0])


def _ensure_components(cursor: Any, exam_id: int, enrollment_type: str, audit_user: str) -> None:
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
                       FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                 WHERE ComponenteExamenInglesId = ?
                """,
                spec["number"],
                spec["label"],
                spec["evaluation_type"],
                audit_user,
                int(existing[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ing.ComponenteExamenIngles
                    (ExamenInglesId, Codigo, NumeroParcial, Nombre, TipoEvaluacion, UsuarioActualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                exam_id,
                spec["code"],
                spec["number"],
                spec["label"],
                spec["evaluation_type"],
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
        _ensure_components(cursor, exam_id, profile["tipo_matricula"], audit_user)
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
    _ensure_components(cursor, exam_id, profile["tipo_matricula"], audit_user)
    return exam_id


def _component_payload(row: Any) -> dict[str, Any]:
    now = _utc_now_naive()
    deadline = getattr(row, "fecha_limite_edicion", None)
    seconds_remaining = max(0, int((deadline - now).total_seconds())) if isinstance(deadline, datetime) else 0
    grade_raw = getattr(row, "nota", None)
    grade = float(grade_raw) if grade_raw is not None else None
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
        "can_edit": seconds_remaining > 0 and grade is None,
        "edit_deadline": _iso_utc(deadline),
        "seconds_remaining": seconds_remaining,
    }


def _load_component_rows(cursor: Any, exam_ids: list[int]) -> dict[int, list[Any]]:
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
            componente.Nota AS nota,
            componente.Estado AS estado,
            componente.Observacion AS observacion,
            componente.NombreEvaluador AS nombre_evaluador,
            componente.FechaCalificacion AS fecha_calificacion,
            carga.CargaExamenInglesId AS upload_id,
            carga.NombreArchivoOriginal AS nombre_archivo,
            carga.ContentType AS content_type,
            carga.TamanoBytes AS tamano_bytes,
            carga.NumeroVersion AS numero_version,
            carga.FechaCarga AS fecha_carga,
            carga.FechaLimiteEdicion AS fecha_limite_edicion,
            carga.GraphWebUrl AS graph_web_url
        FROM ing.ComponenteExamenIngles componente
        OUTER APPLY
        (
            SELECT TOP (1) ce.*
            FROM ing.CargaExamenIngles ce
            WHERE ce.ComponenteExamenInglesId = componente.ComponenteExamenInglesId
              AND ce.Activo = 1 AND ce.Estado = 'CARGADO'
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
        "submitted_components": sum(1 for item in components if item["file"]),
        "graded_components": sum(1 for item in components if item["grade"] is not None),
        "can_edit": any(item["can_edit"] for item in components),
        "edit_deadline": max(active_deadlines) if active_deadlines else None,
        "seconds_remaining": max((item["seconds_remaining"] for item in components), default=0),
        "edit_window_minutes": _EDIT_WINDOW_MINUTES,
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
        "graded_components": 0,
        "can_edit": False,
        "edit_deadline": None,
        "seconds_remaining": 0,
        "edit_window_minutes": _EDIT_WINDOW_MINUTES,
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
                     AND carga.Activo = 1 AND carga.Estado = 'CARGADO'
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
            SELECT ComponenteExamenInglesId, Nombre, Nota
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
        component_id = int(component.ComponenteExamenInglesId)
        cursor.execute(
            """
            SELECT TOP (1) FechaLimiteEdicion
            FROM ing.CargaExamenIngles
            WHERE ComponenteExamenInglesId = ? AND Estado = 'CARGADO'
            ORDER BY NumeroVersion DESC
            """,
            component_id,
        )
        previous = cursor.fetchone()
        now = _utc_now_naive()
        if previous and isinstance(previous[0], datetime) and now >= previous[0]:
            raise HTTPException(status_code=409, detail="La ventana de edición de 15 minutos ya finalizó.")
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
            expedient_code=f"ING-{profile['codigo_estud']}",
            audit_user=current_user.login,
        )
        folder = _clean(graph_expedient["folder_path"])
        cloud_filename = f"v{version:02d}-{str(upload_id)[:8]}-{filename}"
        component_folder = _safe_folder_part(_clean(component.Nombre), component_code)
        graph_path = f"{folder}/{component_folder}/{cloud_filename}"
        _ensure_graph_folder(f"{folder}/{component_folder}")
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
        conn.commit()

    return {
        "upload_id": str(upload_id),
        "upload_url": graph_session.get("uploadUrl"),
        "expires_at": graph_session.get("expirationDateTime"),
        "chunk_size": 10 * 1024 * 1024,
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
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        cursor.execute(
            """
            SELECT
                ce.CargaExamenInglesId, ce.ExamenInglesId, ce.NumeroVersion,
                ce.NombreArchivoOriginal, ce.RutaGraph, ce.ContentType, ce.TamanoEsperado,
                ce.ComponenteExamenInglesId, componente.Codigo AS CodigoComponente,
                componente.Nombre AS NombreComponente, componente.Nota AS NotaComponente,
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

        try:
            graph_item = _graph_item_by_path(_clean(upload.RutaGraph))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo verificar el archivo en Microsoft Graph: {exc}") from exc

        graph_item_id = _clean(graph_item.get("id"))
        graph_size = int(graph_item.get("size") or 0)
        if not graph_item_id or graph_size != int(upload.TamanoEsperado):
            raise HTTPException(
                status_code=409,
                detail="La carga no está completa: el tamaño confirmado por Microsoft Graph no coincide con el archivo seleccionado.",
            )

        cursor.execute(
            """
            SELECT TOP (1) FechaLimiteEdicion
            FROM ing.CargaExamenIngles
            WHERE ComponenteExamenInglesId = ? AND Estado = 'CARGADO'
            ORDER BY NumeroVersion DESC
            """,
            int(upload.ComponenteExamenInglesId),
        )
        previous = cursor.fetchone()
        now = _utc_now_naive()
        deadline = previous[0] if previous and isinstance(previous[0], datetime) else now + timedelta(minutes=_EDIT_WINDOW_MINUTES)
        if previous and now >= deadline:
            _delete_graph_item(graph_item_id)
            cursor.execute(
                "UPDATE ing.CargaExamenIngles SET Estado = 'EXPIRADO', Activo = 0 WHERE CargaExamenInglesId = ?",
                str(payload.upload_id),
            )
            conn.commit()
            raise HTTPException(status_code=409, detail="La ventana de edición de 15 minutos finalizó antes de completar el reemplazo.")

        document_type_id = _catalog_id(cursor, "cat.TipoDocumento", "EVIDENCIA_EXAMEN_INGLES", "TipoDocumentoId")
        loaded_state_id = _catalog_id(cursor, "cat.EstadoDocumento", "CARGADO", "EstadoDocumentoId")
        review_state_id = _catalog_id(cursor, "cat.EstadoExpediente", "EN_REVISION", "EstadoExpedienteId")
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
        document_observation = f"Entrega de Inglés: {_clean(upload.NombreComponente)}."
        web_url = _clean(graph_item.get("webUrl"))
        mime_type = _clean((graph_item.get("file") or {}).get("mimeType")) or _clean(upload.ContentType)
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
             WHERE ComponenteExamenInglesId = ? AND Estado = 'CARGADO' AND Activo = 1
            """,
            int(upload.ComponenteExamenInglesId),
        )
        cursor.execute(
            """
            UPDATE ing.CargaExamenIngles
               SET DocumentoExpedienteId = ?, TamanoBytes = ?, GraphItemId = ?, GraphWebUrl = ?,
                   Estado = 'CARGADO', FechaCarga = SYSUTCDATETIME(), FechaLimiteEdicion = ?, Activo = 1
             WHERE CargaExamenInglesId = ?
            """,
            document_id,
            graph_size,
            graph_item_id,
            web_url,
            deadline,
            str(payload.upload_id),
        )
        _refresh_exam_status(cursor, int(upload.ExamenInglesId), current_user.login)
        cursor.execute(
            """
            UPDATE exp.ExpedienteEstudiantil
               SET EstadoExpedienteId = ?, FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ExpedienteEstudiantilId = ?
            """,
            review_state_id,
            current_user.login,
            int(upload.ExpedienteEstudiantilId),
        )
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

    return _load_student_exam(profile, current_user.login)


@router.get("/submissions")
def reviewer_submissions(
    current_user: Annotated[SessionUser, Depends(_REVIEWER_ACCESS)],
    search: Annotated[str, Query(max_length=120)] = "",
    state: Annotated[str, Query(max_length=30)] = "TODOS",
    period_code: Annotated[str, Query(max_length=100)] = "",
) -> dict[str, Any]:
    term = _clean(search)
    normalized_state = _clean(state).upper() or "TODOS"
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        _ensure_schema(cursor)
        conn.commit()
        periods = _reviewer_periods(cursor, current_user)
        selected_period = _select_reviewer_period(periods, period_code, current_user)
        selected_period_info = next(
            (item for item in periods if _clean(item.get("code")) == selected_period),
            None,
        )
        enrollments = _reviewer_enrollments(cursor, selected_period, current_user, term)
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
        component_rows = _load_component_rows(cursor, [int(row.examen_id) for row in rows])
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
        "enrolled": int(selected_period_info.get("student_count") or 0) if selected_period_info else 0,
        "total": sum(1 for item in items if item["submitted_components"] > 0),
        "pending": sum(1 for item in items if item["result"] == "PENDIENTE"),
        "approved": sum(1 for item in items if item["result"] == "APROBADO"),
        "failed": sum(1 for item in items if item["result"] == "REPROBADO"),
        "periods": periods,
        "selected_period_code": selected_period,
        "reviewer": {"name": current_user.nombres or current_user.login, "role": current_user.rol},
    }


def _authorize_file(cursor: Any, upload_id: UUID, current_user: SessionUser) -> Any:
    cursor.execute(
        """
        SELECT ce.GraphItemId, ce.GraphWebUrl, ce.NombreArchivoOriginal, e.CodigoEstud,
               e.ExamenInglesId
        FROM ing.CargaExamenIngles ce
        INNER JOIN ing.ExamenIngles e ON e.ExamenInglesId = ce.ExamenInglesId
        WHERE ce.CargaExamenInglesId = ? AND ce.Estado IN ('CARGADO', 'REEMPLAZADO')
        """,
        str(upload_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró el archivo solicitado.")
    if current_user.rol == "ESTUDIANTE" and int(row.CodigoEstud) != int(current_user.codigo_estud or 0):
        raise HTTPException(status_code=403, detail="No puede acceder al expediente de otro estudiante.")
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
                  AND ce.Activo = 1 AND ce.Estado = 'CARGADO'
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
               SET Nota = ?, Estado = ?, Observacion = NULLIF(?, N''),
                   CodigoDocEvaluador = ?, NombreEvaluador = ?, FechaCalificacion = SYSUTCDATETIME(),
                   FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
             WHERE ComponenteExamenInglesId = ?
            """,
            grade,
            component_state,
            payload.observation.strip(),
            current_user.codigo_doc,
            evaluator_name,
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
        conn.commit()
        cursor.execute(_exam_select("e.ExamenInglesId = ?"), exam_id)
        updated = cursor.fetchone()
        component_rows = _load_component_rows(cursor, [exam_id]).get(exam_id, [])

    _sync_titulation_english(_clean(updated.numero_identificacion), final_approved, current_user.login)
    return _row_payload(updated, component_rows, include_student=True)
