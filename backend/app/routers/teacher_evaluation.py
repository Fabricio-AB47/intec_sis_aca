from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
from html import escape
from io import BytesIO
from pathlib import Path
import re
import uuid
from typing import Any

import pyodbc
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.services.db import get_connection, get_evaluation_connection

router = APIRouter(prefix="/api/evaluacion-docente", tags=["evaluacion-docente"])

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_REPORT_TEMPLATE_PATH = _PROJECT_ROOT / "frontend" / "doc" / "Plantilla word (1) - copia (1).docx"
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"

_NUMBER_PATTERN = re.compile(r"\d+")
_QUESTION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:(?:pregunta|item|ítem|indicador)\s*)?(?:(?:\d+(?:\.\d+)*)\s*(?:[.)\-–—:]|\s+)+|(?:[ivxlcdm]+)\s*[.)\-–—:]+)",
    re.IGNORECASE,
)
_SUBMITTED_STATES = ("FINALIZADA",)
_LIKERT_5_LABELS = {
    1: "Nunca",
    2: "Rara vez",
    3: "A veces",
    4: "Casi siempre",
    5: "Siempre",
}

_EVALUATION_FLOWS: dict[str, dict[str, Any]] = {
    "student": {
        "label": "Evaluación estudiante-docente",
        "instrument_codes": ("EST_DOCENTE_360_V1", "EST_DOCENTE", "ESTUDIANTE_DOCENTE", "EVAL_EST_DOCENTE"),
        "type_codes": ("EST_DOCENTE", "ESTUDIANTE_DOCENTE", "ESTUDIANTE-DOCENTE"),
        "keywords": ("ESTUDIANTE", "DOCENTE"),
        "exclude_keywords": ("AUTO", "PAR"),
        "fallback_type_id": 4,
        "evaluator_type": "ESTUDIANTE",
        "campaign_prefix": "EST_DOCENTE",
        "anonymous": True,
    },
    "auto_estudiante": {
        "label": "Autoevaluación estudiantil",
        "instrument_codes": ("AUTO_ESTUDIANTE_360_V1", "AUTO_ESTUDIANTE", "AUTOEVALUACION_ESTUDIANTE"),
        "type_codes": ("AUTO_ESTUDIANTE", "AUTOEVALUACION_ESTUDIANTE"),
        "keywords": ("AUTO", "ESTUDIANTE"),
        "exclude_keywords": ("DOCENTE", "PAR"),
        "evaluator_type": "AUTO",
        "campaign_prefix": "AUTO_ESTUDIANTE",
        "anonymous": False,
    },
    "auto_docente": {
        "label": "Autoevaluación docente",
        "instrument_codes": ("AUTO_DOCENTE_360_V1", "AUTO_DOCENTE", "AUTOEVALUACION_DOCENTE"),
        "type_codes": ("AUTO_DOCENTE", "AUTOEVALUACION_DOCENTE", "AUTOEVALUACION"),
        "keywords": ("AUTO", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "PAR"),
        "evaluator_type": "AUTO",
        "campaign_prefix": "AUTO_DOCENTE",
        "anonymous": False,
    },
    "par_docente": {
        "label": "Evaluación par docente",
        "instrument_codes": ("PAR_DOCENTE_360_V1", "PAR_DOCENTE", "EVAL_PAR_DOCENTE", "DOCENTE_PAR", "DOCENTE_DOCENTE"),
        "type_codes": ("PAR_DOCENTE", "DOCENTE_PAR", "DOCENTE_DOCENTE"),
        "keywords": ("PAR", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "AUTO"),
        "evaluator_type": "DOCENTE",
        "campaign_prefix": "PAR_DOCENTE",
        "anonymous": False,
    },
    "academico_docente": {
        "label": "Evaluación administrativa docente",
        "instrument_codes": (
            "AUTORIDAD_COORD_360_V1",
            "AUTORIDAD_COORDINADOR",
            "ACA_DOCENTE_360_V1",
            "ACA_DOCENTE",
            "ACADEMICO_DOCENTE",
            "EVAL_ACADEMICA_DOCENTE",
            "AUTORIDAD_DOCENTE",
            "COORD_DOCENTE",
            "DIRECTIVO_DOCENTE",
        ),
        "type_codes": (
            "AUTORIDAD_COORDINADOR",
            "ACA_DOCENTE",
            "ACADEMICO_DOCENTE",
            "EVAL_ACADEMICA_DOCENTE",
            "AUTORIDAD_DOCENTE",
            "COORD_DOCENTE",
            "DIRECTIVO_DOCENTE",
        ),
        "keywords": ("AUTORIDAD", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "AUTO", "PAR"),
        "evaluator_type": "AUTORIDAD",
        "campaign_prefix": "AUTORIDAD_COORD",
        "anonymous": False,
    },
}


class TeacherEvaluationAnswer(BaseModel):
    id_pregunta: int
    no_pregunta: int | None = None
    tipo_preg: int | None = None
    detalle_preg: str | None = None
    puntaje: float = Field(ge=0, le=10)


class TeacherEvaluationSubmitPayload(BaseModel):
    flow: str | None = Field(default=None, pattern="^(student|auto_estudiante)$")
    cedula: str = Field(min_length=1)
    codigo_periodo: int
    codigo_materia: int
    codigo_docente_eval: int
    paralelo: str = Field(min_length=1, max_length=20)
    jornada: str | None = None
    answers: list[TeacherEvaluationAnswer] = Field(min_length=1)


class TeacherRoleEvaluationSubmitPayload(TeacherEvaluationSubmitPayload):
    flow: str = Field(pattern="^(auto_docente|par_docente|academico_docente)$")


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def _safe_filename(value: Any) -> str:
    text = _clean_text(value)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:120] or "archivo"


def _display_question_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", _clean_text(value)).strip()
    if not text:
        return ""
    cleaned = text
    previous = ""
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = _QUESTION_PREFIX_PATTERN.sub("", cleaned).strip()
    return cleaned or text


def _likert_scale_options(min_score: float, max_score: float) -> list[dict[str, Any]]:
    min_value = max(1, int(min_score or 1))
    max_value = min(10, int(max_score or 5))
    if max_value < min_value:
        max_value = min_value

    options: list[dict[str, Any]] = []
    for value in range(min_value, max_value + 1):
        label = _LIKERT_5_LABELS.get(value, str(value)) if min_value == 1 and max_value == 5 else str(value)
        options.append(
            {
                "valor": value,
                "etiqueta": label,
                "texto": f"{value} - {label}",
            }
        )
    return options


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)

    text = _clean_text(value)
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        match = _NUMBER_PATTERN.search(text)
        return int(match.group(0)) if match else default


def _safe_float(value: Any, default: float = 0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_to_100(value: Any) -> float:
    score = _safe_float(value)
    if score <= 0:
        return 0.0
    if score <= 5:
        return round(score * 20, 2)
    return round(score, 2)


def _normalize_teacher_score_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    normalized = dict(row)
    for field in fields:
        if field in normalized:
            normalized[field] = _score_to_100(normalized.get(field))
    return normalized


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _row_dict(cursor: pyodbc.Cursor, row: pyodbc.Row) -> dict[str, Any]:
    return {col[0]: _clean(value) for col, value in zip(cursor.description, row)}


def _placeholders(values: tuple[Any, ...] | list[Any]) -> str:
    return ", ".join("?" for _ in values)


def _quote_identifier(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def _load_table_columns(cursor: pyodbc.Cursor, table_name: str) -> set[str]:
    try:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
              AND UPPER(TABLE_NAME) = UPPER(?)
            """,
            table_name,
        )
        return {str(row[0]) for row in cursor.fetchall()}
    except pyodbc.Error:
        return set()


def _pick_column(columns: set[str], *candidates: str) -> str | None:
    normalized = {column.lower(): column for column in columns}
    for candidate in candidates:
        column = normalized.get(candidate.lower())
        if column:
            return column
    return None


def _select_text_column(column: str | None, alias: str, size: int = 255) -> str:
    if not column:
        return f"CAST(NULL AS varchar({size})) AS {alias}"
    return f"LTRIM(RTRIM(CAST({_quote_identifier(column)} AS varchar({size})))) AS {alias}"


def _where_text_equals(column: str) -> str:
    return f"LTRIM(RTRIM(CAST({_quote_identifier(column)} AS varchar(255)))) = ?"


def _where_digits_equals(column: str) -> str:
    quoted = _quote_identifier(column)
    return f"REPLACE(REPLACE(LTRIM(RTRIM(CAST({quoted} AS varchar(255)))), '-', ''), ' ', '') = ?"


def _active_state_condition(expression: str) -> str:
    return (
        f"UPPER(LTRIM(RTRIM(TRY_CONVERT(varchar(50), {expression})))) "
        "IN ('A', 'ACTIVO', 'ACTIVA')"
    )


def _stable_numeric_code(value: str) -> int:
    text = _clean_text(value) or "academico"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _flow_config(flow: str) -> dict[str, Any]:
    config = _EVALUATION_FLOWS.get(flow)
    if not config:
        raise HTTPException(status_code=400, detail="Tipo de evaluación no válido.")
    return config


def _period_row(row: pyodbc.Row) -> dict[str, Any]:
    return {
        "codigo_periodo": _clean(row.codigo_periodo),
        "detalle_periodo": _clean(row.detalle_periodo),
    }


def _fetch_student(cursor: pyodbc.Cursor, cedula: str) -> dict[str, Any] | None:
    cedula_digits = _digits(cedula)
    cursor.execute(
        f"""
        SELECT TOP 1
            de.codigo_estud,
            LTRIM(RTRIM(de.Cedula_Est)) AS cedula,
            LTRIM(RTRIM(de.Apellidos_nombre)) AS estudiante,
            LTRIM(RTRIM(de.correo)) AS correo_personal,
            LTRIM(RTRIM(de.correointec)) AS correo_intec_datos,
            LTRIM(RTRIM(cei.CorreoIntec)) AS correo_intec
        FROM dbo.DATOS_ESTUD de
        LEFT JOIN dbo.CorreosEstudIntec cei ON cei.codestud = de.codigo_estud
        WHERE REPLACE(REPLACE(LTRIM(RTRIM(de.Cedula_Est)), '-', ''), ' ', '') = ?
          AND {_active_state_condition("de.Estado")}
        """,
        cedula_digits,
    )
    row = cursor.fetchone()
    if not row:
        return None
    student = _row_dict(cursor, row)
    student["codigo_estud"] = _safe_int(student["codigo_estud"])
    student["correo_intec"] = student.get("correo_intec") or student.get("correo_intec_datos")
    student.pop("correo_intec_datos", None)
    return student


def _fetch_teacher(cursor: pyodbc.Cursor, cedula: str) -> dict[str, Any] | None:
    cedula_digits = _digits(cedula)
    cursor.execute(
        f"""
        SELECT TOP 1
            dd.codigo_doc,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.correo)) AS correo_personal,
            LTRIM(RTRIM(dd.correop)) AS correo_intec_datos,
            LTRIM(RTRIM(u.login)) AS usuario
        FROM dbo.DATOSDOCENTE dd
        INNER JOIN dbo.USUARIOS u
            ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '') = ?
          AND {_active_state_condition("u.Estado")}
        ORDER BY dd.codigo_doc
        """,
        cedula_digits,
    )
    row = cursor.fetchone()
    if not row:
        return None
    teacher = _row_dict(cursor, row)
    teacher["codigo_doc"] = _safe_int(teacher["codigo_doc"])
    teacher["correo_intec"] = teacher.get("usuario") or teacher.get("correo_intec_datos")
    teacher.pop("correo_intec_datos", None)
    return teacher


def _fetch_authority(cursor: pyodbc.Cursor, cedula: str) -> dict[str, Any] | None:
    identifier = _clean_text(cedula)
    cedula_digits = _digits(cedula)
    cursor.execute(
        f"""
        SELECT TOP 1
            us.id_usuarios,
            LTRIM(RTRIM(CAST(us.cedula AS varchar(30)))) AS cedula,
            LTRIM(RTRIM(CAST(us.login AS varchar(100)))) AS login,
            LTRIM(RTRIM(CAST(us.nombres AS varchar(200)))) AS nombres,
            LTRIM(RTRIM(CAST(us.email AS varchar(150)))) AS email,
            LTRIM(RTRIM(CAST(us.coordcarrera AS varchar(50)))) AS coordcarrera,
            LTRIM(RTRIM(CAST(us.tipousuario AS varchar(50)))) AS tipousuario,
            LTRIM(RTRIM(CAST(us.tp_us AS varchar(50)))) AS tp_us,
            LTRIM(RTRIM(CAST(us.estado AS varchar(50)))) AS estado
        FROM dbo.USUARIO_SIS us
        WHERE (
              (
                  ? <> ''
                  AND REPLACE(REPLACE(LTRIM(RTRIM(CAST(us.cedula AS varchar(30)))), '-', ''), ' ', '') = ?
              )
           OR UPPER(LTRIM(RTRIM(CAST(us.login AS varchar(100))))) = UPPER(?)
        )
          AND {_active_state_condition("us.estado")}
        ORDER BY us.id_usuarios
        """,
        cedula_digits,
        cedula_digits,
        identifier,
    )
    row = cursor.fetchone()
    if not row:
        return None
    authority = _row_dict(cursor, row)
    authority["codigo_autoridad"] = _safe_int(authority.get("id_usuarios")) or _stable_numeric_code(
        authority.get("login") or cedula_digits
    )
    authority["autoridad"] = authority.get("nombres") or authority.get("login") or cedula_digits
    return authority


def _authority_source_key(authority: dict[str, Any]) -> str:
    return str(authority.get("id_usuarios") or authority.get("codigo_autoridad") or authority.get("login") or "").strip()


def _authority_cedula_digits(authority: dict[str, Any]) -> str:
    return _digits(str(authority.get("cedula") or ""))


def _authority_evaluator_code(authority: dict[str, Any]) -> int:
    return _safe_int(authority.get("id_autoridad_eval360")) or _safe_int(authority.get("codigo_autoridad"))


def _fetch_registered_authority(cursor: pyodbc.Cursor, authority: dict[str, Any]) -> dict[str, Any] | None:
    source_key = _authority_source_key(authority)
    cedula_digits = _authority_cedula_digits(authority)
    login = _clean_text(authority.get("login"))
    cursor.execute(
        """
        SELECT TOP 1
            Id_Autoridad,
            Tipo_Origen,
            Codigo_Usuario_Origen,
            Cedula,
            Login,
            Nombres,
            Email,
            Cargo,
            Cod_Carrera
        FROM eval360.AutoridadAcademica
        WHERE Activo = 1
          AND (
                (Tipo_Origen = 'USUARIO_SIS' AND Codigo_Usuario_Origen = ?)
             OR (? <> '' AND REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(Cedula, ''))), '-', ''), ' ', '') = ?)
             OR (? <> '' AND UPPER(LTRIM(RTRIM(ISNULL(Login, '')))) = UPPER(?))
          )
        ORDER BY
            CASE WHEN Tipo_Origen = 'USUARIO_SIS' AND Codigo_Usuario_Origen = ? THEN 0 ELSE 1 END,
            Id_Autoridad
        """,
        source_key,
        cedula_digits,
        cedula_digits,
        login,
        login,
        source_key,
    )
    row = cursor.fetchone()
    return _row_dict(cursor, row) if row else None


def _ensure_authority_record(cursor: pyodbc.Cursor, authority: dict[str, Any]) -> dict[str, Any]:
    registered = _fetch_registered_authority(cursor, authority)
    if registered:
        return registered

    source_key = _authority_source_key(authority)
    if not source_key:
        raise HTTPException(status_code=400, detail="El usuario academico no tiene identificador en USUARIO_SIS.")

    cursor.execute(
        """
        INSERT INTO eval360.AutoridadAcademica
            (Tipo_Origen, Codigo_Usuario_Origen, Cedula, Login, Nombres, Email, Cargo, Cod_Carrera, Observacion, Activo)
        OUTPUT
            INSERTED.Id_Autoridad,
            INSERTED.Tipo_Origen,
            INSERTED.Codigo_Usuario_Origen,
            INSERTED.Cedula,
            INSERTED.Login,
            INSERTED.Nombres,
            INSERTED.Email,
            INSERTED.Cargo,
            INSERTED.Cod_Carrera
        VALUES ('USUARIO_SIS', ?, ?, ?, ?, ?, 'AUTORIDAD', ?, ?, 1)
        """,
        source_key,
        _clean_text(authority.get("cedula")) or None,
        _clean_text(authority.get("login")) or None,
        _clean_text(authority.get("nombres")) or _clean_text(authority.get("login")) or "Autoridad academica",
        _clean_text(authority.get("email")) or None,
        _clean_text(authority.get("coordcarrera")) or None,
        "Registrado automaticamente desde el modulo de evaluacion 360 usando INTECBDD.dbo.USUARIO_SIS.cedula.",
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="No se pudo registrar la autoridad academica.")
    return _row_dict(cursor, row)


def _course_from_row(data: dict[str, Any]) -> dict[str, Any]:
    codigo_periodo = _safe_int(data.get("codigo_periodo"))
    codigo_materia = _safe_int(data.get("codigo_materia"))
    codigo_docente_eval = _safe_int(data.get("codigo_docente_eval"))
    paralelo = str(data.get("paralelo") or "").strip()
    respuestas = _safe_int(data.get("respuestas_registradas"))
    return {
        "key": f"{codigo_periodo}-{codigo_materia}",
        "codigo_periodo": codigo_periodo,
        "detalle_periodo": data.get("detalle_periodo"),
        "orden_periodo": data.get("Orden"),
        "cod_anio_basica": data.get("cod_anio_Basica"),
        "carrera": data.get("carrera"),
        "codigo_materia": codigo_materia,
        "codigo_materia_interno": data.get("codigo_materia_interno"),
        "materia": data.get("materia"),
        "nivel": data.get("nivel"),
        "paralelo": paralelo,
        "tipo_matricula": data.get("tipo_matricula"),
        "codigo_docente_eval": codigo_docente_eval,
        "docente": data.get("docente"),
        "cedula_docente": data.get("cedula_doc"),
        "cod_jornada": data.get("cod_jornada"),
        "jornada": data.get("jornada"),
        "respuestas_registradas": respuestas,
        "evaluado": respuestas > 0,
    }


def _course_subject_key(course: dict[str, Any], *, include_teacher: bool = False) -> str:
    subject_code = _clean_text(course.get("codigo_materia_interno")) or str(_safe_int(course.get("codigo_materia")))
    parts = [
        str(_safe_int(course.get("codigo_periodo"))),
        subject_code.upper(),
    ]
    if include_teacher:
        parts.append(str(_safe_int(course.get("codigo_docente_eval"))))
    return "|".join(parts)


def _deduplicate_subject_courses(courses: list[dict[str, Any]], *, include_teacher: bool = False) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    careers_by_key: dict[str, set[str]] = {}
    parallels_by_key: dict[str, set[str]] = {}
    teachers_by_key: dict[str, set[str]] = {}
    components_by_key: dict[str, list[dict[str, Any]]] = {}
    component_seen_by_key: dict[str, set[str]] = {}
    subject_ids_by_key: dict[str, set[int]] = {}
    for course in courses:
        key = _course_subject_key(course, include_teacher=include_teacher)
        if key not in grouped:
            grouped[key] = dict(course)
            grouped[key]["key"] = key.replace("|", "-")
            careers_by_key[key] = set()
            parallels_by_key[key] = set()
            teachers_by_key[key] = set()
            components_by_key[key] = []
            component_seen_by_key[key] = set()
            subject_ids_by_key[key] = set()
        carrera = _clean_text(course.get("carrera"))
        paralelo = _clean_text(course.get("paralelo"))
        docente = _clean_text(course.get("docente"))
        subject_id = _safe_int(course.get("codigo_materia"))
        if subject_id:
            subject_ids_by_key[key].add(subject_id)
        component_key = "|".join(
            [
                carrera,
                paralelo,
                docente,
                _clean_text(course.get("cedula_docente")),
                _clean_text(course.get("cod_anio_basica")),
            ]
        )
        if component_key not in component_seen_by_key[key]:
            component_seen_by_key[key].add(component_key)
            components_by_key[key].append(
                {
                    "periodo": course.get("detalle_periodo") or course.get("codigo_periodo"),
                    "codigo_periodo": course.get("codigo_periodo"),
                    "codigo_materia": course.get("codigo_materia"),
                    "codigo_materia_interno": course.get("codigo_materia_interno"),
                    "materia": course.get("materia"),
                    "carrera": carrera,
                    "cod_anio_basica": course.get("cod_anio_basica"),
                    "paralelo": paralelo,
                    "docente": docente,
                    "cedula_docente": course.get("cedula_docente"),
                    "jornada": course.get("jornada"),
                }
            )
        if carrera:
            careers_by_key[key].add(carrera)
        if paralelo:
            parallels_by_key[key].add(paralelo)
        if docente:
            teachers_by_key[key].add(docente)

    for key, course in grouped.items():
        carreras = sorted(careers_by_key.get(key) or [])
        paralelos = sorted(parallels_by_key.get(key) or [])
        docentes = sorted(teachers_by_key.get(key) or [])
        if carreras:
            course["carrera"] = " / ".join(carreras[:4]) + (" / ..." if len(carreras) > 4 else "")
            course["carreras_relacionadas"] = carreras
        if paralelos:
            course["paralelo"] = " / ".join(paralelos[:4]) + (" / ..." if len(paralelos) > 4 else "")
            course["paralelos_relacionados"] = paralelos
        if docentes:
            course["docente"] = " / ".join(docentes[:3]) + (" / ..." if len(docentes) > 3 else "")
            course["docentes_relacionados"] = docentes
        codigos_materia = sorted(subject_ids_by_key.get(key) or [])
        if codigos_materia:
            course["codigos_materia_relacionados"] = codigos_materia
        course["componentes_relacionados"] = components_by_key.get(key, [])
    return list(grouped.values())


def _courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT
            ce.codigo_estud,
            ce.cod_anio_Basica,
            ce.codigo_materia,
            ce.codigo_periodo,
            LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) AS paralelo,
            LTRIM(RTRIM(CAST(ce.TipoMatricula AS varchar(5)))) AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            COALESCE(doc_exact.codigo_doc, doc_hist.codigo_doc, 0) AS codigo_docente_eval,
            COALESCE(
                LTRIM(RTRIM(doc_exact.apellidos_nombre)),
                LTRIM(RTRIM(doc_hist.apellidos_nombre)),
                'Docente por asignar'
            ) AS docente,
            COALESCE(LTRIM(RTRIM(doc_exact.cedula_doc)), LTRIM(RTRIM(doc_hist.cedula_doc)), '') AS cedula_doc,
            CAST(COALESCE(doc_exact.Cod_Jornada, doc_hist.Cod_Jornada, cm.Jornada) AS varchar(20)) AS cod_jornada,
            LTRIM(RTRIM(CAST(cm.Jornada AS varchar(50)))) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
        LEFT JOIN dbo.CABECERA_MATRICULA cm ON cm.codigo_estud = ce.codigo_estud
            AND cm.cod_anio_Basica = ce.cod_anio_Basica
            AND cm.codigo_periodo = ce.codigo_periodo
        OUTER APPLY (
            SELECT TOP 1
                cxd.codigo_doc,
                cxd.Cod_Jornada,
                dd.apellidos_nombre,
                dd.cedula_doc
            FROM dbo.CARRERAXDOCENTE cxd
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS du
                ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            WHERE cxd.codigo_materia = ce.codigo_materia
              AND cxd.codigo_periodo = ce.codigo_periodo
              AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
              AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                  LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
              AND {_active_state_condition("du.Estado")}
            ORDER BY cxd.codigo_doc
        ) doc_exact
        OUTER APPLY (
            SELECT TOP 1
                cxd.codigo_doc,
                cxd.Cod_Jornada,
                dd.apellidos_nombre,
                dd.cedula_doc
            FROM dbo.CARRERAXDOCENTE cxd
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS du
                ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            WHERE cxd.codigo_materia = ce.codigo_materia
              AND {_active_state_condition("du.Estado")}
            ORDER BY
                CASE WHEN cxd.codigo_periodo = ce.codigo_periodo THEN 0 ELSE 1 END,
                CASE WHEN cxd.cod_Anio_Basica = ce.cod_anio_Basica THEN 0 ELSE 1 END,
                CASE WHEN LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                          LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS THEN 0 ELSE 1 END,
                ABS(TRY_CONVERT(int, cxd.codigo_periodo) - TRY_CONVERT(int, ce.codigo_periodo)),
                cxd.codigo_doc
        ) doc_hist
        WHERE ce.codigo_estud = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
        {extra_where}
        ORDER BY per.Orden DESC, ce.codigo_periodo DESC, pen.Semestre, LTRIM(RTRIM(pen.Nomb_Materia))
    """


def _auto_student_courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT
            ce.codigo_estud,
            ce.cod_anio_Basica,
            ce.codigo_materia,
            ce.codigo_periodo,
            LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) AS paralelo,
            LTRIM(RTRIM(CAST(ce.TipoMatricula AS varchar(5)))) AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            CAST(0 AS int) AS codigo_docente_eval,
            CAST('Autoevaluación estudiantil' AS nvarchar(250)) AS docente,
            CAST('' AS varchar(50)) AS cedula_doc,
            LTRIM(RTRIM(CAST(cm.Jornada AS varchar(20)))) AS cod_jornada,
            LTRIM(RTRIM(CAST(cm.Jornada AS varchar(50)))) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
        LEFT JOIN dbo.CABECERA_MATRICULA cm ON cm.codigo_estud = ce.codigo_estud
            AND cm.cod_anio_Basica = ce.cod_anio_Basica
            AND cm.codigo_periodo = ce.codigo_periodo
        WHERE ce.codigo_estud = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
        {extra_where}
        ORDER BY per.Orden DESC, ce.codigo_periodo DESC, pen.Semestre, LTRIM(RTRIM(pen.Nomb_Materia))
    """


def _teacher_courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT
            cxd.codigo_doc,
            cxd.cod_Anio_Basica AS cod_anio_Basica,
            cxd.codigo_materia,
            cxd.codigo_periodo,
            LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
            'D' AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            dd.codigo_doc AS codigo_docente_eval,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
            CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXDOCENTE cxd
        INNER JOIN dbo.PERIODO per ON cxd.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON cxd.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON cxd.cod_Anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        INNER JOIN dbo.USUARIOS u
            ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE cxd.codigo_doc = ?
          AND EXISTS (
              SELECT 1
              FROM dbo.CARRERAXESTUD ce
              WHERE ce.codigo_materia = cxd.codigo_materia
                AND ce.codigo_periodo = cxd.codigo_periodo
                AND ce.cod_anio_Basica = cxd.cod_Anio_Basica
                AND LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
                AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          )
          AND {_active_state_condition("u.Estado")}
        {extra_where}
        ORDER BY per.Orden DESC, cxd.codigo_periodo DESC, pen.Semestre, LTRIM(RTRIM(pen.Nomb_Materia))
    """


def _peer_courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT
            mine.codigo_doc,
            peer.cod_Anio_Basica AS cod_anio_Basica,
            peer.codigo_materia,
            peer.codigo_periodo,
            LTRIM(RTRIM(CAST(peer.Paralelo AS varchar(20)))) AS paralelo,
            'PAR' AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            peer.codigo_doc AS codigo_docente_eval,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(peer.Cod_Jornada AS varchar(20)) AS cod_jornada,
            CAST(peer.Cod_Jornada AS varchar(50)) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXDOCENTE mine
        INNER JOIN dbo.CARRERAXDOCENTE peer ON peer.codigo_materia = mine.codigo_materia
            AND peer.codigo_doc <> mine.codigo_doc
        INNER JOIN dbo.PERIODO per ON peer.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON peer.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON peer.cod_Anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = peer.codigo_doc
        INNER JOIN dbo.USUARIOS peer_u
            ON REPLACE(REPLACE(LTRIM(RTRIM(peer_u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE mine.codigo_doc = ?
          AND EXISTS (
              SELECT 1
              FROM dbo.CARRERAXESTUD ce
              WHERE ce.codigo_materia = peer.codigo_materia
                AND ce.codigo_periodo = peer.codigo_periodo
                AND ce.cod_anio_Basica = peer.cod_Anio_Basica
                AND LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(peer.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
                AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          )
          AND {_active_state_condition("peer_u.Estado")}
        {extra_where}
        ORDER BY per.Orden DESC, peer.codigo_periodo DESC, LTRIM(RTRIM(car.Nombre_Basica)), LTRIM(RTRIM(pen.Nomb_Materia)), LTRIM(RTRIM(dd.apellidos_nombre))
    """


def _authority_courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT
            cxd.codigo_doc,
            cxd.cod_Anio_Basica AS cod_anio_Basica,
            cxd.codigo_materia,
            cxd.codigo_periodo,
            LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
            'AUTORIDAD' AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            cxd.codigo_doc AS codigo_docente_eval,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
            CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
            AND cxd.codigo_periodo = ce.codigo_periodo
            AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
        INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        INNER JOIN dbo.USUARIOS u
            ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE LTRIM(RTRIM(CAST(cxd.cod_Anio_Basica AS varchar(50)))) = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          AND {_active_state_condition("u.Estado")}
        {extra_where}
        ORDER BY per.Orden DESC, cxd.codigo_periodo DESC, LTRIM(RTRIM(car.Nombre_Basica)), LTRIM(RTRIM(pen.Nomb_Materia)), LTRIM(RTRIM(dd.apellidos_nombre))
    """


def _authority_all_courses_query(extra_where: str = "") -> str:
    return f"""
        SELECT DISTINCT TOP 2000
            cxd.codigo_doc,
            cxd.cod_Anio_Basica AS cod_anio_Basica,
            cxd.codigo_materia,
            cxd.codigo_periodo,
            LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
            'AUTORIDAD' AS tipo_matricula,
            LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
            per.Orden,
            LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
            LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
            pen.Semestre AS nivel,
            LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
            cxd.codigo_doc AS codigo_docente_eval,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
            CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
            AND cxd.codigo_periodo = ce.codigo_periodo
            AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
        INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        INNER JOIN dbo.USUARIOS u
            ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE 1 = 1
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          AND {_active_state_condition("u.Estado")}
        {extra_where}
        ORDER BY per.Orden DESC, cxd.codigo_periodo DESC, LTRIM(RTRIM(car.Nombre_Basica)), LTRIM(RTRIM(pen.Nomb_Materia)), LTRIM(RTRIM(dd.apellidos_nombre))
    """


def _fetch_authority_assignments(cursor: pyodbc.Cursor, authority_id: int) -> list[dict[str, Any]]:
    if not authority_id:
        return []
    cursor.execute(
        """
        SELECT
            Id_Autoridad_Docente,
            Id_Autoridad,
            Cod_Periodo,
            Cod_Carrera,
            Cod_Docente,
            Cod_Materia,
            Jornada,
            Paralelo,
            Modalidad
        FROM eval360.AutoridadDocenteMateria
        WHERE Activo = 1
          AND Id_Autoridad = ?
        ORDER BY Cod_Periodo DESC, Cod_Docente, Cod_Materia
        """,
        authority_id,
    )
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


def _authority_courses_from_assignments(
    cursor: pyodbc.Cursor,
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    courses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for assignment in assignments:
        params: list[Any] = [str(assignment.get("Cod_Docente") or "")]
        filters = [
            "LTRIM(RTRIM(CAST(cxd.codigo_doc AS varchar(50)))) = ?",
        ]
        if _clean_text(assignment.get("Cod_Periodo")):
            filters.append("LTRIM(RTRIM(CAST(cxd.codigo_periodo AS varchar(50)))) = ?")
            params.append(_clean_text(assignment.get("Cod_Periodo")))
        if _clean_text(assignment.get("Cod_Carrera")):
            filters.append("LTRIM(RTRIM(CAST(cxd.cod_Anio_Basica AS varchar(50)))) = ?")
            params.append(_clean_text(assignment.get("Cod_Carrera")))
        if _clean_text(assignment.get("Cod_Materia")):
            filters.append("LTRIM(RTRIM(CAST(cxd.codigo_materia AS varchar(50)))) = ?")
            params.append(_clean_text(assignment.get("Cod_Materia")))
        if _clean_text(assignment.get("Paralelo")):
            filters.append(
                "LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS = "
                "LTRIM(RTRIM(CAST(? AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS"
            )
            params.append(_clean_text(assignment.get("Paralelo")))

        cursor.execute(
            f"""
            SELECT DISTINCT
                cxd.codigo_doc,
                cxd.cod_Anio_Basica AS cod_anio_Basica,
                cxd.codigo_materia,
                cxd.codigo_periodo,
                LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
                'AUTORIDAD' AS tipo_matricula,
                LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
                per.Orden,
                LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
                LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
                pen.Semestre AS nivel,
                LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
                cxd.codigo_doc AS codigo_docente_eval,
                LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
                LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
                CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
                CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
                CAST(0 AS int) AS respuestas_registradas
            FROM dbo.CARRERAXESTUD ce
            INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
                AND cxd.codigo_periodo = ce.codigo_periodo
                AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
                AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
            INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
            INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS u
                ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            WHERE {" AND ".join(filters)}
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              AND {_active_state_condition("u.Estado")}
            ORDER BY per.Orden DESC, cxd.codigo_periodo DESC, LTRIM(RTRIM(car.Nombre_Basica)), LTRIM(RTRIM(pen.Nomb_Materia)), LTRIM(RTRIM(dd.apellidos_nombre))
            """,
            *params,
        )
        for row in cursor.fetchall():
            course = _course_from_row(_row_dict(cursor, row))
            key = course["key"]
            if key in seen:
                continue
            seen.add(key)
            courses.append(course)
    return courses


def _fallback_question_category(data: dict[str, Any], id_dimension: int, tipo_preg: int) -> str:
    category = (
        _clean_text(data.get("categoria"))
        or _clean_text(data.get("categoria_pregunta"))
        or _clean_text(data.get("dimension_global_nombre"))
        or _clean_text(data.get("dimension_nombre"))
        or _clean_text(data.get("instrumento_nombre"))
        or _clean_text(data.get("tipo_evaluacion_nombre"))
    )
    if category:
        return category
    if id_dimension:
        return f"Categoría {id_dimension}"
    if tipo_preg:
        return f"Categoría {tipo_preg}"
    return "Categoría general"


def _question_from_row(data: dict[str, Any]) -> dict[str, Any]:
    puntaje_min = _safe_float(data.get("Puntaje_Min"), 1)
    puntaje_max = _safe_float(data.get("Puntaje_Max"), 5)
    id_dimension = _safe_int(data.get("Id_Dimension"), 0)
    tipo_preg = _safe_int(data.get("TipoPreg"), id_dimension)
    tipo_preg_codigo = _clean_text(data.get("TipoPreg"))
    category = _fallback_question_category(data, id_dimension, tipo_preg)
    return {
        "id_pregunta": _safe_int(data.get("Id_Pregunta")),
        "id_dimension": id_dimension,
        "no_pregunta": _safe_int(data.get("NoPregunta"), _safe_int(data.get("Orden"), 0)),
        "tipo_preg": tipo_preg,
        "tipo_preg_codigo": tipo_preg_codigo,
        "tipo_label": category,
        "categoria": category,
        "categoria_pregunta": category,
        "dimension_global_nombre": _clean_text(data.get("dimension_global_nombre")),
        "dimension_nombre": category,
        "dimension_codigo": _clean_text(data.get("dimension_codigo")),
        "categoria_codigo": _clean_text(data.get("categoria_codigo")),
        "instrumento_codigo": _clean_text(data.get("instrumento_codigo")),
        "instrumento_nombre": _clean_text(data.get("instrumento_nombre")),
        "tipo_evaluacion_codigo": _clean_text(data.get("tipo_evaluacion_codigo")),
        "tipo_evaluacion_nombre": _clean_text(data.get("tipo_evaluacion_nombre")),
        "detalle_preg": _display_question_text(data.get("Detalle_Preg")),
        "peso_pregunta": _safe_float(data.get("Peso_Pregunta"), 1),
        "puntaje_min": puntaje_min,
        "puntaje_max": puntaje_max,
        "escala_likert": _likert_scale_options(puntaje_min, puntaje_max),
        "orden": _safe_int(data.get("Orden")),
    }


def _instrument_row(cursor: pyodbc.Cursor, row: pyodbc.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = _row_dict(cursor, row)
    data["Id_Instrumento"] = _safe_int(data.get("Id_Instrumento"))
    data["Id_Tipo_Evaluacion"] = _safe_int(data.get("Id_Tipo_Evaluacion"))
    return data


def _get_instrument(cursor: pyodbc.Cursor, flow: str) -> dict[str, Any]:
    config = _flow_config(flow)
    instrument_codes = tuple(config.get("instrument_codes") or ())
    if instrument_codes:
        cursor.execute(
            f"""
            SELECT TOP 1
                i.Id_Instrumento,
                i.Id_Tipo_Evaluacion,
                i.Codigo,
                i.Nombre,
                te.Codigo AS tipo_evaluacion_codigo,
                te.Nombre AS tipo_evaluacion_nombre
            FROM eval360.Instrumento i
            LEFT JOIN eval360.TipoEvaluacion te ON te.Id_Tipo_Evaluacion = i.Id_Tipo_Evaluacion
            WHERE i.Activo = 1
              AND UPPER(LTRIM(RTRIM(i.Codigo))) IN ({_placeholders(instrument_codes)})
            ORDER BY i.Id_Instrumento DESC
            """,
            *[str(code).upper() for code in instrument_codes],
        )
        instrument = _instrument_row(cursor, cursor.fetchone())
        if instrument:
            return instrument

    type_codes = tuple(config.get("type_codes") or ())
    if type_codes:
        cursor.execute(
            f"""
            SELECT TOP 1
                i.Id_Instrumento,
                i.Id_Tipo_Evaluacion,
                i.Codigo,
                i.Nombre,
                te.Codigo AS tipo_evaluacion_codigo,
                te.Nombre AS tipo_evaluacion_nombre
            FROM eval360.Instrumento i
            INNER JOIN eval360.TipoEvaluacion te ON te.Id_Tipo_Evaluacion = i.Id_Tipo_Evaluacion
            WHERE i.Activo = 1
              AND te.Activo = 1
              AND UPPER(LTRIM(RTRIM(te.Codigo))) IN ({_placeholders(type_codes)})
            ORDER BY i.Id_Instrumento DESC
            """,
            *[str(code).upper() for code in type_codes],
        )
        instrument = _instrument_row(cursor, cursor.fetchone())
        if instrument:
            return instrument

    keywords = tuple(config.get("keywords") or ())
    if keywords:
        search_expr = "UPPER(CONCAT(i.Codigo, ' ', i.Nombre, ' ', ISNULL(te.Codigo, ''), ' ', ISNULL(te.Nombre, '')))"
        keyword_where = " AND ".join(f"{search_expr} LIKE ?" for _ in keywords)
        exclude_keywords = tuple(config.get("exclude_keywords") or ())
        exclude_where = ""
        params = [f"%{keyword.upper()}%" for keyword in keywords]
        if exclude_keywords:
            exclude_where = " AND " + " AND ".join(f"{search_expr} NOT LIKE ?" for _ in exclude_keywords)
            params.extend(f"%{keyword.upper()}%" for keyword in exclude_keywords)
        cursor.execute(
            f"""
            SELECT TOP 1
                i.Id_Instrumento,
                i.Id_Tipo_Evaluacion,
                i.Codigo,
                i.Nombre,
                te.Codigo AS tipo_evaluacion_codigo,
                te.Nombre AS tipo_evaluacion_nombre
            FROM eval360.Instrumento i
            LEFT JOIN eval360.TipoEvaluacion te ON te.Id_Tipo_Evaluacion = i.Id_Tipo_Evaluacion
            WHERE i.Activo = 1
              AND {keyword_where}
              {exclude_where}
            ORDER BY i.Id_Instrumento DESC
            """,
            *params,
        )
        instrument = _instrument_row(cursor, cursor.fetchone())
        if instrument:
            return instrument

    fallback_type_id = config.get("fallback_type_id")
    if fallback_type_id:
        cursor.execute(
            """
            SELECT TOP 1
                i.Id_Instrumento,
                i.Id_Tipo_Evaluacion,
                i.Codigo,
                i.Nombre,
                te.Codigo AS tipo_evaluacion_codigo,
                te.Nombre AS tipo_evaluacion_nombre
            FROM eval360.Instrumento i
            LEFT JOIN eval360.TipoEvaluacion te ON te.Id_Tipo_Evaluacion = i.Id_Tipo_Evaluacion
            WHERE i.Activo = 1
              AND i.Id_Tipo_Evaluacion = ?
            ORDER BY i.Id_Instrumento DESC
            """,
            fallback_type_id,
        )
        instrument = _instrument_row(cursor, cursor.fetchone())
        if instrument:
            return instrument

    raise HTTPException(status_code=404, detail=f"No existe instrumento activo para {config['label']}.")


def _fetch_question_rows(cursor: pyodbc.Cursor, flow: str) -> tuple[dict[str, Any], list[pyodbc.Row]]:
    instrument = _get_instrument(cursor, flow)
    instrument_id = _safe_int(instrument.get("Id_Instrumento"))
    cursor.execute(
        """
        SELECT
            p.Id_Pregunta,
            p.Id_Dimension,
            p.NoPregunta,
            p.Detalle_Preg,
            p.TipoPreg,
            p.Peso_Pregunta,
            p.Puntaje_Min,
            p.Puntaje_Max,
            p.Orden,
            di.Codigo AS dimension_codigo,
            di.Nombre AS dimension_nombre,
            dg.Codigo AS categoria_codigo,
            dg.Nombre AS dimension_global_nombre,
            COALESCE(
                NULLIF(LTRIM(RTRIM(dg.Nombre)), ''),
                NULLIF(LTRIM(RTRIM(di.Nombre)), ''),
                NULLIF(LTRIM(RTRIM(dg.Descripcion)), ''),
                CONCAT('Categoría ', COALESCE(CAST(p.Id_Dimension AS NVARCHAR(20)), CAST(p.TipoPreg AS NVARCHAR(20)), 'general'))
            ) AS categoria,
            i.Codigo AS instrumento_codigo,
            i.Nombre AS instrumento_nombre,
            te.Codigo AS tipo_evaluacion_codigo,
            te.Nombre AS tipo_evaluacion_nombre
        FROM eval360.Pregunta p
        INNER JOIN eval360.DimensionInstrumento di
            ON di.Id_Dimension = p.Id_Dimension
            AND di.Activo = 1
        LEFT JOIN eval360.DimensionGlobal dg
            ON dg.Id_Dimension_Global = di.Id_Dimension_Global
            AND dg.Activo = 1
        INNER JOIN eval360.Instrumento i
            ON i.Id_Instrumento = di.Id_Instrumento
            AND i.Activo = 1
        LEFT JOIN eval360.TipoEvaluacion te
            ON te.Id_Tipo_Evaluacion = i.Id_Tipo_Evaluacion
            AND te.Activo = 1
        WHERE p.Activo = 1
          AND i.Id_Instrumento = ?
        ORDER BY ISNULL(di.Orden, 9999), ISNULL(p.Orden, 9999), p.Id_Pregunta
        """,
        instrument_id,
    )
    rows = cursor.fetchall()
    return instrument, rows


def _origin_key(actor_code: int, course: dict[str, Any], flow: str) -> str:
    parts = [
        flow,
        str(actor_code),
        str(course.get("codigo_periodo") or ""),
        str(course.get("codigo_materia") or ""),
    ]
    if flow in {"academico_docente", "par_docente"}:
        parts.append(str(course.get("codigo_docente_eval") or ""))
    return "|".join(parts)


def _evaluation_count(
    cursor: pyodbc.Cursor,
    *,
    flow: str,
    instrument: dict[str, Any],
    evaluator_code: int,
    course: dict[str, Any],
    origin_key: str | None = None,
) -> int:
    config = _flow_config(flow)
    states = ", ".join("?" for _ in _SUBMITTED_STATES)
    subject_ids = sorted({_safe_int(value) for value in (course.get("codigos_materia_relacionados") or []) if _safe_int(value)})
    if not subject_ids:
        subject_ids = [_safe_int(course.get("codigo_materia"))]
    subject_placeholders = ", ".join("?" for _ in subject_ids)
    teacher_filter = ""
    teacher_params: list[Any] = []
    if flow in {"academico_docente", "par_docente"}:
        teacher_filter = " AND Cod_Docente_Evaluado = ?"
        teacher_params.append(str(_safe_int(course.get("codigo_docente_eval"))))
    cursor.execute(
        f"""
        SELECT COUNT(1)
        FROM eval360.Aplicacion
        WHERE Id_Tipo_Evaluacion = ?
          AND Tipo_Evaluador = ?
          AND Cod_Periodo = ?
          AND Cod_Materia IN ({subject_placeholders})
          AND Estado IN ({states})
          {teacher_filter}
          AND (Cod_Evaluador = ? OR Origen_Evaluador_Clave = ? OR Origen_Clave = ?)
        """,
        _safe_int(instrument.get("Id_Tipo_Evaluacion")),
        config["evaluator_type"],
        str(_safe_int(course.get("codigo_periodo"))),
        *[str(value) for value in subject_ids],
        *_SUBMITTED_STATES,
        *teacher_params,
        str(evaluator_code),
        str(evaluator_code),
        origin_key or "",
    )
    row = cursor.fetchone()
    return _safe_int(row[0] if row else 0)


def _evaluation_any_authority_count(
    cursor: pyodbc.Cursor,
    *,
    instrument: dict[str, Any],
    course: dict[str, Any],
) -> int:
    states = ", ".join("?" for _ in _SUBMITTED_STATES)
    subject_ids = sorted({_safe_int(value) for value in (course.get("codigos_materia_relacionados") or []) if _safe_int(value)})
    if not subject_ids:
        subject_ids = [_safe_int(course.get("codigo_materia"))]
    subject_placeholders = ", ".join("?" for _ in subject_ids)
    teacher_filter = ""
    teacher_params: list[Any] = []
    if _safe_int(course.get("codigo_docente_eval")):
        teacher_filter = " AND Cod_Docente_Evaluado = ?"
        teacher_params.append(str(_safe_int(course.get("codigo_docente_eval"))))
    cursor.execute(
        f"""
        SELECT COUNT(1)
        FROM eval360.Aplicacion
        WHERE Id_Tipo_Evaluacion = ?
          AND Tipo_Evaluador = 'AUTORIDAD'
          AND Cod_Periodo = ?
          AND Cod_Materia IN ({subject_placeholders})
          {teacher_filter}
          AND Estado IN ({states})
        """,
        _safe_int(instrument.get("Id_Tipo_Evaluacion")),
        str(_safe_int(course.get("codigo_periodo"))),
        *[str(value) for value in subject_ids],
        *teacher_params,
        *_SUBMITTED_STATES,
    )
    row = cursor.fetchone()
    return _safe_int(row[0] if row else 0)


def _evaluation_weights_for_period(cursor: pyodbc.Cursor, periodo: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            te.Id_Tipo_Evaluacion,
            te.Codigo,
            te.Nombre,
            COALESCE(p.Peso_Porcentaje, te.Peso_Default, 0) AS Peso_Porcentaje,
            te.Peso_Default
        FROM eval360.TipoEvaluacion te
        OUTER APPLY (
            SELECT TOP 1
                pon.Peso_Porcentaje
            FROM eval360.Ponderacion pon
            WHERE pon.Id_Tipo_Evaluacion = te.Id_Tipo_Evaluacion
              AND (
                    TRY_CONVERT(varchar(50), pon.Cod_Periodo) = ?
                 OR UPPER(LTRIM(RTRIM(TRY_CONVERT(varchar(50), pon.Cod_Periodo)))) = 'DEFAULT'
              )
              AND ISNULL(pon.Activo, 1) = 1
            ORDER BY
                CASE WHEN TRY_CONVERT(varchar(50), pon.Cod_Periodo) = ? THEN 0 ELSE 1 END,
                pon.Fecha_Creacion DESC,
                pon.Id_Ponderacion DESC
        ) p
        WHERE te.Activo = 1
        """,
        periodo,
        periodo,
    )
    columns = [column[0] for column in cursor.description]
    return [{column: _clean(value) for column, value in zip(columns, row)} for row in cursor.fetchall()]


def _evaluation_type_weight(cursor: pyodbc.Cursor, instrument: dict[str, Any], periodo: str | None = None) -> float:
    type_id = _safe_int(instrument.get("Id_Tipo_Evaluacion"))
    if not type_id:
        return 0
    if periodo:
        cursor.execute(
            """
            SELECT TOP 1 Peso_Porcentaje
            FROM eval360.Ponderacion
            WHERE Id_Tipo_Evaluacion = ?
              AND (
                    TRY_CONVERT(varchar(50), Cod_Periodo) = ?
                 OR UPPER(LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cod_Periodo)))) = 'DEFAULT'
              )
              AND ISNULL(Activo, 1) = 1
            ORDER BY
                CASE WHEN TRY_CONVERT(varchar(50), Cod_Periodo) = ? THEN 0 ELSE 1 END,
                Fecha_Creacion DESC,
                Id_Ponderacion DESC
            """,
            type_id,
            periodo,
            periodo,
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return _safe_float(row[0])
    cursor.execute(
        """
        SELECT TOP 1 Peso_Default
        FROM eval360.TipoEvaluacion
        WHERE Id_Tipo_Evaluacion = ?
        """,
        type_id,
    )
    row = cursor.fetchone()
    return _safe_float(row[0] if row else 0)


def _flow_weight_from_rows(weights: list[dict[str, Any]], flow: str) -> float:
    component = _result_component_for_flow(flow)
    if not component:
        return 0.0
    _, type_code = component
    for row in weights or []:
        if _clean_text(row.get("Codigo")).upper() == type_code:
            return _safe_float(row.get("Peso_Porcentaje") if row.get("Peso_Porcentaje") is not None else row.get("Peso_Default"))
    return 0.0


def _weighted_teacher_result_score(row: dict[str, Any], weights: list[dict[str, Any]]) -> float:
    components = [
        ("student", "Promedio_Estudiantes"),
        ("par_docente", "Promedio_Par_Docente"),
        ("academico_docente", "Promedio_Autoridad"),
        ("auto_docente", "Promedio_Autoevaluacion"),
    ]
    total = 0.0
    used_weight = 0.0
    for flow, field in components:
        score = _score_to_100(row.get(field))
        weight = _flow_weight_from_rows(weights, flow)
        if score > 0 and weight > 0:
            total += score * (weight / 100.0)
            used_weight += weight
    if used_weight <= 0:
        return _score_to_100(row.get("Puntaje_Final_360"))
    return round(total, 2)


def _apply_evaluation_status(actor_code: int, courses: list[dict[str, Any]], flow: str) -> list[dict[str, Any]]:
    if not courses:
        return courses

    try:
        with get_evaluation_connection() as conn:
            cursor = conn.cursor()
            instrument = _get_instrument(cursor, flow)
            for course in courses:
                key = _origin_key(actor_code, course, flow)
                count = _evaluation_count(
                    cursor,
                    flow=flow,
                    instrument=instrument,
                    evaluator_code=actor_code,
                    course=course,
                    origin_key=key,
                )
                course["respuestas_registradas"] = count
                course["evaluado"] = count > 0
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo verificar evaluaciones registradas: {exc}") from exc

    return courses


def _get_or_create_campaign(
    cursor: pyodbc.Cursor,
    *,
    codigo_periodo: int,
    detalle_periodo: str | None,
    flow: str,
) -> int:
    config = _flow_config(flow)
    now = datetime.now()
    cursor.execute(
        """
        SELECT TOP 1 Id_Campania
        FROM eval360.Campania
        WHERE Cod_Periodo = ?
          AND Estado = 'ABIERTA'
          AND ? BETWEEN Fecha_Inicio AND Fecha_Fin
        ORDER BY Id_Campania DESC
        """,
        str(codigo_periodo),
        now,
    )
    row = cursor.fetchone()
    if row:
        return _safe_int(row[0])

    campaign_code = f"{config['campaign_prefix']}_{codigo_periodo}"
    campaign_name = f"{config['label']} {detalle_periodo or codigo_periodo}"
    cursor.execute(
        """
        INSERT INTO eval360.Campania
            (Codigo, Nombre, Cod_Periodo, Fecha_Inicio, Fecha_Fin, Estado, Observacion)
        OUTPUT INSERTED.Id_Campania
        VALUES (?, ?, ?, ?, ?, 'ABIERTA', ?)
        """,
        campaign_code,
        campaign_name,
        str(codigo_periodo),
        now,
        now + timedelta(days=180),
        "Campaña creada automáticamente desde el módulo público de evaluación docente.",
    )
    created = cursor.fetchone()
    if not created:
        raise HTTPException(status_code=500, detail="No se pudo crear la campaña de evaluación activa.")
    return _safe_int(created[0])


def _validate_questions(
    cursor: pyodbc.Cursor,
    answers: list[TeacherEvaluationAnswer],
    *,
    instrument_id: int,
) -> dict[int, dict[str, Any]]:
    if not answers:
        raise HTTPException(status_code=400, detail="Debe responder todas las preguntas obligatorias antes de enviar.")

    question_ids = sorted({answer.id_pregunta for answer in answers})
    if len(question_ids) != len(answers):
        raise HTTPException(status_code=400, detail="Existen preguntas duplicadas en la evaluación enviada.")

    cursor.execute(
        """
        SELECT p.Id_Pregunta, p.Puntaje_Min, p.Puntaje_Max
        FROM eval360.Pregunta p
        INNER JOIN eval360.DimensionInstrumento di
            ON di.Id_Dimension = p.Id_Dimension
           AND di.Id_Instrumento = ?
           AND di.Activo = 1
        WHERE p.Activo = 1
        """,
        instrument_id,
    )
    all_rows = {_safe_int(row.Id_Pregunta): _row_dict(cursor, row) for row in cursor.fetchall()}
    if not all_rows:
        raise HTTPException(status_code=400, detail="No existen preguntas activas para este instrumento.")

    required_ids = set(all_rows)
    answer_ids = set(question_ids)
    missing_required = sorted(required_ids - answer_ids)
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Debe responder todas las preguntas obligatorias. Faltan {len(missing_required)} pregunta(s).",
        )

    cursor.execute(
        f"""
        SELECT p.Id_Pregunta, p.Puntaje_Min, p.Puntaje_Max
        FROM eval360.Pregunta p
        INNER JOIN eval360.DimensionInstrumento di
            ON di.Id_Dimension = p.Id_Dimension
           AND di.Id_Instrumento = ?
           AND di.Activo = 1
        WHERE p.Activo = 1
          AND p.Id_Pregunta IN ({_placeholders(question_ids)})
        """,
        instrument_id,
        *question_ids,
    )
    rows = {_safe_int(row.Id_Pregunta): _row_dict(cursor, row) for row in cursor.fetchall()}
    missing = [question_id for question_id in question_ids if question_id not in rows]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Existen preguntas no válidas para este instrumento: {', '.join(map(str, missing))}.",
        )

    for answer in answers:
        question = rows[answer.id_pregunta]
        min_score = _safe_float(question.get("Puntaje_Min"), 1)
        max_score = _safe_float(question.get("Puntaje_Max"), 5)
        if answer.puntaje < min_score or answer.puntaje > max_score:
            raise HTTPException(
                status_code=400,
                detail=f"El puntaje de la pregunta {answer.id_pregunta} debe estar entre {min_score:g} y {max_score:g}.",
            )

    return rows


def _find_student_course(cursor: pyodbc.Cursor, student_code: int, payload: TeacherEvaluationSubmitPayload) -> dict[str, Any]:
    query = _auto_student_courses_query if payload.flow == "auto_estudiante" else _courses_query
    cursor.execute(
        query(
            """
            AND ce.codigo_periodo = ?
            AND ce.codigo_materia = ?
            """
        ),
        student_code,
        payload.codigo_periodo,
        payload.codigo_materia,
    )
    row = cursor.fetchone()
    if not row:
        detail = (
            "La materia seleccionada no tiene promedio final registrado para la autoevaluación estudiantil."
            if payload.flow == "auto_estudiante"
            else "La materia seleccionada no está asignada al estudiante en ese periodo."
        )
        raise HTTPException(status_code=404, detail=detail)
    course = _course_from_row(_row_dict(cursor, row))
    if payload.flow != "auto_estudiante" and _safe_int(course.get("codigo_docente_eval")) <= 0:
        raise HTTPException(
            status_code=404,
            detail="La materia tiene promedio final, pero no tiene docente asignado para registrar la evaluación.",
        )
    return course


def _find_teacher_course(
    cursor: pyodbc.Cursor,
    teacher_code: int,
    payload: TeacherRoleEvaluationSubmitPayload,
) -> dict[str, Any]:
    if payload.flow == "auto_docente":
        cursor.execute(
            _teacher_courses_query(
                """
                AND cxd.codigo_periodo = ?
                AND cxd.codigo_materia = ?
                """
            ),
            teacher_code,
            payload.codigo_periodo,
            payload.codigo_materia,
        )
    else:
        cursor.execute(
            _peer_courses_query(
                """
                AND mine.codigo_materia = ?
                AND peer.codigo_periodo = ?
                AND peer.codigo_materia = ?
                AND peer.codigo_doc = ?
                """
            ),
            teacher_code,
            payload.codigo_materia,
            payload.codigo_periodo,
            payload.codigo_materia,
            payload.codigo_docente_eval,
        )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró la materia seleccionada para el docente.")
    course = _course_from_row(_row_dict(cursor, row))
    if payload.flow == "auto_docente":
        course["codigo_docente_eval"] = teacher_code
    if payload.flow == "par_docente":
        course["codigo_periodo"] = payload.codigo_periodo
        course["codigo_materia"] = payload.codigo_materia
        course["codigo_docente_eval"] = payload.codigo_docente_eval
    return course


def _find_authority_course(
    cursor: pyodbc.Cursor,
    authority: dict[str, Any],
    payload: TeacherRoleEvaluationSubmitPayload,
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if assignments:
        courses = _authority_courses_from_assignments(cursor, assignments)
        for course in courses:
            if (
                _safe_int(course.get("codigo_periodo")) == payload.codigo_periodo
                and _safe_int(course.get("codigo_materia")) == payload.codigo_materia
            ):
                return course
        raise HTTPException(
            status_code=404,
            detail="La materia seleccionada no esta asignada a esta autoridad academica.",
        )

    coordcarrera = _clean_text(authority.get("coordcarrera"))
    filter_sql = """
        AND cxd.codigo_periodo = ?
        AND cxd.codigo_materia = ?
    """
    if coordcarrera:
        cursor.execute(
            _authority_courses_query(filter_sql),
            coordcarrera,
            payload.codigo_periodo,
            payload.codigo_materia,
        )
    else:
        cursor.execute(
            _authority_all_courses_query(filter_sql),
            payload.codigo_periodo,
            payload.codigo_materia,
        )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró la materia seleccionada para la autoridad académica.")
    return _course_from_row(_row_dict(cursor, row))


def _admin_expected_rows(cursor: pyodbc.Cursor, periodo: str, flow: str, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 1000))
    if flow == "student":
        cursor.execute(
            f"""
            SELECT DISTINCT TOP {limit}
                ce.codigo_estud AS evaluator_code,
                LTRIM(RTRIM(de.Apellidos_nombre)) AS evaluator_name,
                LTRIM(RTRIM(de.Cedula_Est)) AS evaluator_cedula,
                ce.codigo_estud,
                ce.cod_anio_Basica,
                ce.codigo_materia,
                ce.codigo_periodo,
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) AS paralelo,
                LTRIM(RTRIM(CAST(ce.TipoMatricula AS varchar(5)))) AS tipo_matricula,
                LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
                per.Orden,
                LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
                LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
                pen.Semestre AS nivel,
                LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
                cxd.codigo_doc AS codigo_docente_eval,
                LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
                LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
                CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
                LTRIM(RTRIM(CAST(cm.Jornada AS varchar(50)))) AS jornada,
                CAST(0 AS int) AS respuestas_registradas
            FROM dbo.CARRERAXESTUD ce
            INNER JOIN dbo.DATOS_ESTUD de ON de.codigo_estud = ce.codigo_estud
            INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
            INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
            INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
            INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
                AND cxd.codigo_periodo = ce.codigo_periodo
                AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
                AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS du
                ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            LEFT JOIN dbo.CABECERA_MATRICULA cm ON cm.codigo_estud = ce.codigo_estud
                AND cm.cod_anio_Basica = ce.cod_anio_Basica
                AND cm.codigo_periodo = ce.codigo_periodo
            WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              AND {_active_state_condition("de.Estado")}
              AND {_active_state_condition("du.Estado")}
            ORDER BY LTRIM(RTRIM(de.Apellidos_nombre)), LTRIM(RTRIM(pen.Nomb_Materia))
            """,
            periodo,
        )
    elif flow == "auto_estudiante":
        cursor.execute(
            f"""
            SELECT DISTINCT TOP {limit}
                ce.codigo_estud AS evaluator_code,
                LTRIM(RTRIM(de.Apellidos_nombre)) AS evaluator_name,
                LTRIM(RTRIM(de.Cedula_Est)) AS evaluator_cedula,
                ce.codigo_estud,
                ce.cod_anio_Basica,
                ce.codigo_materia,
                ce.codigo_periodo,
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) AS paralelo,
                LTRIM(RTRIM(CAST(ce.TipoMatricula AS varchar(5)))) AS tipo_matricula,
                LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
                per.Orden,
                LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
                LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
                pen.Semestre AS nivel,
                LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
                CAST(0 AS int) AS codigo_docente_eval,
                CAST('Autoevaluación estudiantil' AS nvarchar(250)) AS docente,
                CAST('' AS varchar(50)) AS cedula_doc,
                LTRIM(RTRIM(CAST(cm.Jornada AS varchar(20)))) AS cod_jornada,
                LTRIM(RTRIM(CAST(cm.Jornada AS varchar(50)))) AS jornada,
                CAST(0 AS int) AS respuestas_registradas
            FROM dbo.CARRERAXESTUD ce
            INNER JOIN dbo.DATOS_ESTUD de ON de.codigo_estud = ce.codigo_estud
            INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
            INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
            INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
            LEFT JOIN dbo.CABECERA_MATRICULA cm ON cm.codigo_estud = ce.codigo_estud
                AND cm.cod_anio_Basica = ce.cod_anio_Basica
                AND cm.codigo_periodo = ce.codigo_periodo
            WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              AND {_active_state_condition("de.Estado")}
            ORDER BY LTRIM(RTRIM(de.Apellidos_nombre)), LTRIM(RTRIM(pen.Nomb_Materia))
            """,
            periodo,
        )
    elif flow in {"auto_docente", "par_docente"}:
        cursor.execute(
            f"""
            SELECT DISTINCT TOP {limit}
                cxd.codigo_doc AS evaluator_code,
                LTRIM(RTRIM(dd.apellidos_nombre)) AS evaluator_name,
                LTRIM(RTRIM(dd.cedula_doc)) AS evaluator_cedula,
                cxd.codigo_doc,
                cxd.cod_Anio_Basica AS cod_anio_Basica,
                cxd.codigo_materia,
                cxd.codigo_periodo,
                LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
                'D' AS tipo_matricula,
                LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
                per.Orden,
                LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
                LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
                pen.Semestre AS nivel,
                LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
                cxd.codigo_doc AS codigo_docente_eval,
                LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
                LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
                CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
                CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
                CAST(0 AS int) AS respuestas_registradas
            FROM dbo.CARRERAXESTUD ce
            INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
                AND cxd.codigo_periodo = ce.codigo_periodo
                AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
                AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
            INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
            INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS u
                ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              AND {_active_state_condition("u.Estado")}
            ORDER BY LTRIM(RTRIM(dd.apellidos_nombre)), LTRIM(RTRIM(pen.Nomb_Materia))
            """,
            periodo,
        )
    else:
        cursor.execute(
            f"""
            SELECT DISTINCT TOP {limit}
                CAST(NULL AS int) AS evaluator_code,
                'Administrativo' AS evaluator_name,
                CAST(NULL AS varchar(50)) AS evaluator_cedula,
                cxd.codigo_doc,
                cxd.cod_Anio_Basica AS cod_anio_Basica,
                cxd.codigo_materia,
                cxd.codigo_periodo,
                LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) AS paralelo,
                'AUTORIDAD' AS tipo_matricula,
                LTRIM(RTRIM(per.Detalle_Periodo)) AS detalle_periodo,
                per.Orden,
                LTRIM(RTRIM(pen.Nomb_Materia)) AS materia,
                LTRIM(RTRIM(pen.cod_materia)) AS codigo_materia_interno,
                pen.Semestre AS nivel,
                LTRIM(RTRIM(car.Nombre_Basica)) AS carrera,
                cxd.codigo_doc AS codigo_docente_eval,
                LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
                LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
                CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
                CAST(cxd.Cod_Jornada AS varchar(50)) AS jornada,
                CAST(0 AS int) AS respuestas_registradas
            FROM dbo.CARRERAXDOCENTE cxd
            INNER JOIN dbo.PERIODO per ON cxd.codigo_periodo = per.cod_periodo
            INNER JOIN dbo.PENSUM pen ON cxd.codigo_materia = pen.codigo_materia
            INNER JOIN dbo.CARRERAS car ON cxd.cod_Anio_Basica = car.Cod_AnioBasica
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS u
                ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            WHERE TRY_CONVERT(varchar(50), cxd.codigo_periodo) = ?
              AND EXISTS (
                  SELECT 1
                  FROM dbo.CARRERAXESTUD ce
                  WHERE ce.codigo_materia = cxd.codigo_materia
                    AND ce.codigo_periodo = cxd.codigo_periodo
                    AND ce.cod_anio_Basica = cxd.cod_Anio_Basica
                    AND LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                        LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
                    AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              )
              AND {_active_state_condition("u.Estado")}
            ORDER BY LTRIM(RTRIM(dd.apellidos_nombre)), LTRIM(RTRIM(pen.Nomb_Materia))
            """,
            periodo,
        )

    rows = []
    for row in cursor.fetchall():
        data = _row_dict(cursor, row)
        course = _course_from_row(data)
        rows.append(
            {
                "flow": flow,
                "flow_label": _flow_config(flow)["label"],
                "evaluator_code": _safe_int(data.get("evaluator_code")),
                "evaluator_name": _clean_text(data.get("evaluator_name")),
                "evaluator_cedula": _clean_text(data.get("evaluator_cedula")),
                "course": course,
            }
        )

    grouped: dict[str, dict[str, Any]] = {}
    course_groups: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        course = item["course"]
        key = "|".join(
            [
                flow,
                str(item.get("evaluator_code") or ""),
                _course_subject_key(course),
            ]
        )
        if key not in grouped:
            grouped[key] = {**item, "course": dict(course)}
            course_groups[key] = []
        course_groups[key].append(course)

    for key, item in grouped.items():
        deduped = _deduplicate_subject_courses(course_groups[key])
        if deduped:
            item["course"] = deduped[0]
    return list(grouped.values())


def _student_progress_expected(cursor: pyodbc.Cursor, periodo: str, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 2000))
    cursor.execute(
        f"""
        SELECT TOP {limit}
            ce.codigo_estud,
            LTRIM(RTRIM(de.Cedula_Est)) AS cedula,
            LTRIM(RTRIM(de.Apellidos_nombre)) AS estudiante,
            COUNT(DISTINCT TRY_CONVERT(varchar(50), ce.codigo_materia)) AS materias_autoevaluables,
            COUNT(DISTINCT CASE
                WHEN cxd.codigo_doc IS NOT NULL THEN TRY_CONVERT(varchar(50), ce.codigo_materia)
                ELSE NULL
            END) AS materias_evaluables,
            STRING_AGG(CONVERT(nvarchar(max), LTRIM(RTRIM(car.Nombre_Basica))), N' / ') AS carreras
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.DATOS_ESTUD de ON de.codigo_estud = ce.codigo_estud
        LEFT JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
            AND cxd.codigo_periodo = ce.codigo_periodo
            AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
        LEFT JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        LEFT JOIN dbo.USUARIOS du
            ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        INNER JOIN dbo.CARRERAS car ON car.Cod_AnioBasica = ce.cod_anio_Basica
        WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          AND {_active_state_condition("de.Estado")}
          AND (du.cedula IS NULL OR {_active_state_condition("du.Estado")})
        GROUP BY ce.codigo_estud, de.Cedula_Est, de.Apellidos_nombre
        ORDER BY LTRIM(RTRIM(de.Apellidos_nombre))
        """,
        periodo,
    )
    columns = [column[0] for column in cursor.description]
    rows: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        item = {column: _clean(value) for column, value in zip(columns, row)}
        carreras = sorted({part.strip() for part in _clean_text(item.get("carreras")).split("/") if part.strip()})
        rows.append(
            {
                "codigo_estud": _safe_int(item.get("codigo_estud")),
                "cedula": _clean_text(item.get("cedula")),
                "estudiante": _clean_text(item.get("estudiante")),
                "carreras": " / ".join(carreras[:4]) + (" / ..." if len(carreras) > 4 else ""),
                "materias_evaluables": _safe_int(item.get("materias_evaluables")),
                "materias_autoevaluables": _safe_int(item.get("materias_autoevaluables")),
            }
        )
    return rows


def _student_progress_completed(
    cursor: pyodbc.Cursor,
    periodo: str,
    student_codes: list[int],
    flow: str,
) -> dict[int, int]:
    if not student_codes:
        return {}
    instrument = _get_instrument(cursor, flow)
    config = _flow_config(flow)
    placeholders = ", ".join("?" for _ in student_codes)
    states = ", ".join("?" for _ in _SUBMITTED_STATES)
    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(int, Cod_Evaluador) AS codigo_estud,
            COUNT(DISTINCT Cod_Materia) AS completadas
        FROM eval360.Aplicacion
        WHERE Id_Tipo_Evaluacion = ?
          AND Tipo_Evaluador = ?
          AND Cod_Periodo = ?
          AND Estado IN ({states})
          AND TRY_CONVERT(int, Cod_Evaluador) IN ({placeholders})
        GROUP BY TRY_CONVERT(int, Cod_Evaluador)
        """,
        _safe_int(instrument.get("Id_Tipo_Evaluacion")),
        config["evaluator_type"],
        periodo,
        *_SUBMITTED_STATES,
        *student_codes,
    )
    return {_safe_int(row.codigo_estud): _safe_int(row.completadas) for row in cursor.fetchall()}


def _student_period_grades(cursor: pyodbc.Cursor, periodo: str, codigo_estud: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            ce.codigo_estud,
            ce.codigo_materia,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), pen.Nomb_Materia))) AS materia,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), car.Nombre_Basica))) AS carrera,
            LTRIM(RTRIM(TRY_CONVERT(varchar(20), ce.paralelo))) AS paralelo,
            TRY_CONVERT(float, ce.PromedioFinal) AS promedio_final
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.PENSUM pen ON pen.codigo_materia = ce.codigo_materia
        INNER JOIN dbo.CARRERAS car ON car.Cod_AnioBasica = ce.cod_anio_Basica
        WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
          AND ce.codigo_estud = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
        ORDER BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), pen.Nomb_Materia)))
        """,
        periodo,
        codigo_estud,
    )
    return [
        {
            "codigo_materia": _clean(row.codigo_materia),
            "materia": _clean(row.materia),
            "carrera": _clean(row.carrera),
            "paralelo": _clean(row.paralelo),
            "promedio_final": _safe_float(row.promedio_final),
        }
        for row in cursor.fetchall()
    ]


def _expected_students_for_teacher_subject(
    cursor: pyodbc.Cursor,
    periodo: str,
    codigo_docente: str,
    codigo_materia: str,
) -> int:
    cursor.execute(
        f"""
        SELECT COUNT(DISTINCT ce.codigo_estud)
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.DATOS_ESTUD de ON de.codigo_estud = ce.codigo_estud
        INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
            AND cxd.codigo_periodo = ce.codigo_periodo
            AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        INNER JOIN dbo.USUARIOS du
            ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
          AND TRY_CONVERT(varchar(50), cxd.codigo_doc) = ?
          AND TRY_CONVERT(varchar(50), ce.codigo_materia) = ?
          AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
          AND {_active_state_condition("de.Estado")}
          AND {_active_state_condition("du.Estado")}
        """,
        periodo,
        codigo_docente,
        codigo_materia,
    )
    row = cursor.fetchone()
    return _safe_int(row[0] if row else 0)


def _report_row_key(
    codigo_docente: Any,
    codigo_materia: Any,
    jornada: Any = "",
    paralelo: Any = "",
) -> str:
    return "|".join(
        [
            _clean_text(codigo_docente),
            _clean_text(codigo_materia),
            _clean_text(jornada),
            _clean_text(paralelo),
        ]
    )


def _teacher_evaluation_academic_maps(
    periodo: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], str]:
    teachers: dict[str, dict[str, Any]] = {}
    subjects: dict[str, dict[str, Any]] = {}
    student_coverage: dict[str, dict[str, Any]] = {}
    period_label = periodo
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1 LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), Detalle_Periodo)))
            FROM dbo.PERIODO
            WHERE TRY_CONVERT(varchar(50), cod_periodo) = ?
            """,
            periodo,
        )
        row = cursor.fetchone()
        if row and row[0]:
            period_label = _clean_text(row[0])

        cursor.execute(
            """
            SELECT DISTINCT
                TRY_CONVERT(varchar(50), cxd.codigo_doc) AS codigo_doc,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), dd.apellidos_nombre))) AS docente,
                LTRIM(RTRIM(TRY_CONVERT(varchar(50), dd.cedula_doc))) AS cedula_doc,
                TRY_CONVERT(varchar(50), cxd.codigo_materia) AS codigo_materia,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), pen.Nomb_Materia))) AS materia,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), car.Nombre_Basica))) AS carrera
            FROM dbo.CARRERAXDOCENTE cxd
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.PENSUM pen ON pen.codigo_materia = cxd.codigo_materia
            INNER JOIN dbo.CARRERAS car ON car.Cod_AnioBasica = cxd.cod_Anio_Basica
            WHERE TRY_CONVERT(varchar(50), cxd.codigo_periodo) = ?
            """,
            periodo,
        )
        columns = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            item = {column: _clean(value) for column, value in zip(columns, row)}
            teachers.setdefault(
                item["codigo_doc"],
                {
                    "codigo_doc": item["codigo_doc"],
                    "docente": item["docente"],
                    "cedula_doc": item["cedula_doc"],
                },
            )
            subjects.setdefault(
                f"{item['codigo_doc']}|{item['codigo_materia']}",
                {
                    "materia": item["materia"],
                    "carrera": item["carrera"],
                },
            )

        cursor.execute(
            f"""
            SELECT
                TRY_CONVERT(varchar(50), cxd.codigo_doc) AS codigo_doc,
                TRY_CONVERT(varchar(50), ce.codigo_materia) AS codigo_materia,
                LTRIM(RTRIM(TRY_CONVERT(varchar(50), cxd.Cod_Jornada))) AS jornada,
                LTRIM(RTRIM(TRY_CONVERT(varchar(20), ce.paralelo))) AS paralelo,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), car.Nombre_Basica))) AS carrera,
                COUNT(DISTINCT ce.codigo_estud) AS estudiantes_esperados
            FROM dbo.CARRERAXESTUD ce
            INNER JOIN dbo.DATOS_ESTUD de ON de.codigo_estud = ce.codigo_estud
            INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
                AND cxd.codigo_periodo = ce.codigo_periodo
                AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
                AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                    LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
            INNER JOIN dbo.USUARIOS du
                ON REPLACE(REPLACE(LTRIM(RTRIM(du.cedula)), '-', ''), ' ', '') =
                   REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
            INNER JOIN dbo.CARRERAS car ON car.Cod_AnioBasica = ce.cod_anio_Basica
            WHERE TRY_CONVERT(varchar(50), ce.codigo_periodo) = ?
              AND TRY_CONVERT(float, ce.PromedioFinal) IS NOT NULL
              AND {_active_state_condition("de.Estado")}
              AND {_active_state_condition("du.Estado")}
            GROUP BY cxd.codigo_doc, ce.codigo_materia, cxd.Cod_Jornada, ce.paralelo, car.Nombre_Basica
            """,
            periodo,
        )
        coverage_columns = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            item = {column: _clean(value) for column, value in zip(coverage_columns, row)}
            key = _report_row_key(item.get("codigo_doc"), item.get("codigo_materia"), item.get("jornada"), item.get("paralelo"))
            coverage = student_coverage.setdefault(
                key,
                {
                    "estudiantes_esperados": 0,
                    "carreras": {},
                },
            )
            expected = _safe_int(item.get("estudiantes_esperados"))
            coverage["estudiantes_esperados"] += expected
            carrera = _clean_text(item.get("carrera")) or "Sin carrera"
            coverage["carreras"][carrera] = _safe_int(coverage["carreras"].get(carrera)) + expected

        for coverage in student_coverage.values():
            careers = coverage.get("carreras") or {}
            coverage["carreras_detalle"] = " / ".join(
                f"{career} ({count})" for career, count in sorted(careers.items())
            )

    return teachers, subjects, student_coverage, period_label


def _result_component_for_flow(flow: str) -> tuple[str, str] | None:
    return {
        "student": ("Promedio_Estudiantes", "ESTUDIANTE_DOCENTE"),
        "par_docente": ("Promedio_Par_Docente", "PAR_DOCENTE"),
        "academico_docente": ("Promedio_Autoridad", "AUTORIDAD_COORDINADOR"),
        "auto_docente": ("Promedio_Autoevaluacion", "AUTO_DOCENTE"),
    }.get(flow)


def _flow_from_type_text(value: Any) -> str:
    text = _clean_text(value).upper()
    if "AUTO" in text and "ESTUDIANTE" not in text:
        return "auto_docente"
    if "PAR" in text:
        return "par_docente"
    if "AUTORIDAD" in text or "ADMIN" in text or "COORD" in text or "ACADEMIC" in text:
        return "academico_docente"
    if "ESTUDIANTE" in text and "DOCENTE" in text:
        return "student"
    return ""


def _fetch_teacher_grade_report(
    periodo: str,
    codigo_docente: str | None = None,
    flow: str = "all",
    document_type: str = "certificado",
) -> dict[str, Any]:
    selected_teacher = _clean_text(codigo_docente)
    report_flow = _clean_text(flow or "all")
    if report_flow != "all" and report_flow not in {"student", "auto_docente", "par_docente", "academico_docente"}:
        raise HTTPException(status_code=400, detail="Tipo de evaluacion no valido para el PDF.")
    teachers, subjects, student_coverage, period_label = _teacher_evaluation_academic_maps(periodo)
    with get_evaluation_connection() as conn:
        cursor = conn.cursor()
        params: list[Any] = [periodo]
        teacher_where = ""
        if selected_teacher:
            teacher_where = " AND Cod_Docente_Evaluado = ?"
            params.append(selected_teacher)
        cursor.execute(
            f"""
            SELECT
                Cod_Periodo,
                Cod_Docente_Evaluado,
                Cod_Materia,
                Jornada,
                Paralelo,
                Promedio_Estudiantes,
                Promedio_Par_Docente,
                Promedio_Autoridad,
                Promedio_Autoevaluacion,
                Puntaje_Final_360
            FROM eval360.vw_Resultado_360_Docente
            WHERE Cod_Periodo = ?
              {teacher_where}
            ORDER BY Cod_Docente_Evaluado, Cod_Materia, Paralelo
            """,
            *params,
        )
        result_columns = [column[0] for column in cursor.description]
        results = [
            _normalize_teacher_score_fields(
                {column: _clean(value) for column, value in zip(result_columns, row)},
                (
                    "Promedio_Estudiantes",
                    "Promedio_Par_Docente",
                    "Promedio_Autoridad",
                    "Promedio_Autoevaluacion",
                    "Puntaje_Final_360",
                ),
            )
            for row in cursor.fetchall()
        ]

        cursor.execute(
            f"""
            SELECT
                Cod_Docente_Evaluado,
                Cod_Materia,
                Jornada,
                Paralelo,
                Codigo_Tipo_Evaluacion,
                Tipo_Evaluacion,
                Total_Evaluaciones,
                Total_Respuestas,
                Promedio_Tipo
            FROM eval360.vw_Resultado_Tipo_Docente
            WHERE Cod_Periodo = ?
              {teacher_where}
            ORDER BY Cod_Docente_Evaluado, Cod_Materia, Codigo_Tipo_Evaluacion
            """,
            *params,
        )
        type_columns = [column[0] for column in cursor.description]
        type_rows = [
            _normalize_teacher_score_fields(
                {column: _clean(value) for column, value in zip(type_columns, row)},
                ("Promedio_Tipo",),
            )
            for row in cursor.fetchall()
        ]

        cursor.execute(
            f"""
            SELECT
                Cod_Docente_Evaluado,
                Cod_Materia,
                Jornada,
                Paralelo,
                Tipo_Evaluacion,
                Dimension_Global,
                Total_Evaluaciones,
                Total_Respuestas,
                Promedio_Dimension
            FROM eval360.vw_Resultado_Dimension_Docente
            WHERE Cod_Periodo = ?
              {teacher_where}
            ORDER BY Cod_Docente_Evaluado, Cod_Materia, Tipo_Evaluacion, Dimension_Global
            """,
            *params,
        )
        dimension_columns = [column[0] for column in cursor.description]
        dimension_rows = [
            _normalize_teacher_score_fields(
                {column: _clean(value) for column, value in zip(dimension_columns, row)},
                ("Promedio_Dimension",),
            )
            for row in cursor.fetchall()
        ]

        weight_rows = _evaluation_weights_for_period(cursor, periodo)

    def key_for(item: dict[str, Any]) -> str:
        return _report_row_key(
            item.get("Cod_Docente_Evaluado"),
            item.get("Cod_Materia"),
            item.get("Jornada"),
            item.get("Paralelo"),
        )

    student_completed_by_key: dict[str, int] = {}
    for item in type_rows:
        if _clean_text(item.get("Codigo_Tipo_Evaluacion")).upper() != "ESTUDIANTE_DOCENTE":
            continue
        key = key_for(item)
        student_completed_by_key[key] = student_completed_by_key.get(key, 0) + _safe_int(item.get("Total_Evaluaciones"))

    def apply_student_coverage(row: dict[str, Any]) -> None:
        key = key_for(row)
        coverage = student_coverage.get(key) or {}
        expected = _safe_int(coverage.get("estudiantes_esperados"))
        completed = _safe_int(student_completed_by_key.get(key))
        raw_student_score = _score_to_100(row.get("Promedio_Estudiantes"))
        coverage_ratio = min(completed / expected, 1.0) if expected > 0 else (1.0 if raw_student_score > 0 else 0.0)
        row["Promedio_Estudiantes_Original"] = raw_student_score
        row["Promedio_Estudiantes"] = round(raw_student_score * coverage_ratio, 2)
        row["Estudiantes_Esperados"] = expected
        row["Estudiantes_Completaron"] = completed
        row["Cobertura_Estudiantes"] = round(coverage_ratio * 100.0, 2)
        row["Carreras_Detalle"] = _clean_text(coverage.get("carreras_detalle"))

    if report_flow != "all":
        component = _result_component_for_flow(report_flow)
        if component:
            component_field, type_code = component
            results = []
            for item in type_rows:
                if _clean_text(item.get("Codigo_Tipo_Evaluacion")).upper() != type_code:
                    continue
                score = _score_to_100(item.get("Promedio_Tipo"))
                row = {
                    "Cod_Periodo": periodo,
                    "Cod_Docente_Evaluado": item.get("Cod_Docente_Evaluado"),
                    "Cod_Materia": item.get("Cod_Materia"),
                    "Jornada": item.get("Jornada"),
                    "Paralelo": item.get("Paralelo"),
                    "Promedio_Estudiantes": 0,
                    "Promedio_Par_Docente": 0,
                    "Promedio_Autoridad": 0,
                    "Promedio_Autoevaluacion": 0,
                    "Puntaje_Final_360": score,
                }
                row[component_field] = score
                if report_flow == "student":
                    apply_student_coverage(row)
                    row["Puntaje_Final_360"] = row["Promedio_Estudiantes"]
                results.append(row)
            type_rows = [
                item
                for item in type_rows
                if _clean_text(item.get("Codigo_Tipo_Evaluacion")).upper() == type_code
            ]
            dimension_rows = [
                item
                for item in dimension_rows
                if _clean_text(item.get("Tipo_Evaluacion")).upper()
                == _clean_text(type_rows[0].get("Tipo_Evaluacion")).upper()
            ] if type_rows else []
    else:
        for item in results:
            apply_student_coverage(item)
            item["Puntaje_Final_360"] = _weighted_teacher_result_score(item, weight_rows)

    types_by_key: dict[str, list[dict[str, Any]]] = {}
    for item in type_rows:
        types_by_key.setdefault(key_for(item), []).append(item)

    dimensions_by_key: dict[str, list[dict[str, Any]]] = {}
    for item in dimension_rows:
        dimensions_by_key.setdefault(key_for(item), []).append(item)

    grouped: dict[str, dict[str, Any]] = {}
    for item in results:
        doc_code = _clean(item.get("Cod_Docente_Evaluado"))
        subject_key = f"{doc_code}|{_clean(item.get('Cod_Materia'))}"
        teacher = teachers.get(doc_code, {"codigo_doc": doc_code, "docente": f"Docente {doc_code}", "cedula_doc": ""})
        subject = subjects.get(subject_key, {"materia": _clean(item.get("Cod_Materia")), "carrera": ""})
        row_key = key_for(item)
        grouped.setdefault(
            doc_code,
            {
                "teacher": teacher,
                "rows": [],
            },
        )["rows"].append(
            {
                **item,
                "materia": subject["materia"],
                "carrera": _clean_text(item.get("Carreras_Detalle")) or subject["carrera"],
                "tipos": types_by_key.get(row_key, []),
                "dimensiones": dimensions_by_key.get(row_key, []),
            }
        )

    return {
        "periodo": periodo,
        "periodo_detalle": period_label,
        "codigo_docente": selected_teacher,
        "flow": report_flow,
        "document_type": _clean_text(document_type or "certificado"),
        "teachers": list(grouped.values()),
        "weights": weight_rows,
    }


class _SvgLogo(Flowable):
    def __init__(self, path: Path, width: float) -> None:
        super().__init__()
        self.drawing = svg2rlg(str(path)) if path.exists() else None
        if self.drawing:
            self.scale = width / float(self.drawing.width or width)
            self.width = width
            self.height = float(self.drawing.height or 0) * self.scale
        else:
            self.scale = 1
            self.width = width
            self.height = 1.1 * cm

    def draw(self) -> None:
        if not self.drawing:
            self.canv.setFont("Helvetica-Bold", 18)
            self.canv.setFillColor(colors.HexColor("#777777"))
            self.canv.drawString(0, 0.25 * cm, "INTEC")
            return
        self.canv.saveState()
        self.canv.scale(self.scale, self.scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()


class _ComplianceBars(Flowable):
    def __init__(self, values: list[tuple[str, float, float]], width: float, height: float = 3.0 * cm) -> None:
        super().__init__()
        self.values = values
        self.width = width
        self.height = height

    def draw(self) -> None:
        canvas = self.canv
        label_width = 3.7 * cm
        value_width = 1.85 * cm
        bar_width = max(self.width - label_width - value_width - 0.25 * cm, 1 * cm)
        row_height = self.height / max(len(self.values), 1)
        canvas.setFont("Helvetica", 7)
        for index, (label, raw_value, raw_target) in enumerate(self.values):
            value = max(0.0, float(raw_value or 0))
            target = max(float(raw_target or 0), value, 1.0)
            percent = max(0.0, min((value / target) * 100.0, 100.0))
            y = self.height - ((index + 1) * row_height) + 0.16 * cm
            canvas.setFillColor(colors.HexColor("#0c1f42"))
            canvas.drawString(0, y + 0.06 * cm, label[:34])
            canvas.setFillColor(colors.HexColor("#e6edf1"))
            canvas.roundRect(label_width, y, bar_width, 0.24 * cm, 3, stroke=0, fill=1)
            fill_color = "#1f6f8b" if percent >= 85 else "#d99a2a" if percent >= 65 else "#a61d16"
            canvas.setFillColor(colors.HexColor(fill_color))
            canvas.roundRect(label_width, y, bar_width * (percent / 100), 0.24 * cm, 3, stroke=0, fill=1)
            canvas.setFillColor(colors.HexColor("#0c1f42"))
            canvas.drawRightString(label_width + bar_width + value_width, y + 0.04 * cm, f"{value:.2f}/{target:.2f}")


def _template_page_image() -> bytes | None:
    if not _REPORT_TEMPLATE_PATH.exists():
        return None
    try:
        from zipfile import ZipFile

        with ZipFile(_REPORT_TEMPLATE_PATH) as archive:
            media_names = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
            if not media_names:
                return None
            return archive.read(media_names[0])
    except Exception:
        return None


def _grade_level(value: Any) -> str:
    number = _safe_float(value)
    if number >= 95:
        return "EXCELENTE"
    if number >= 85:
        return "MUY BUENO"
    if number >= 75:
        return "BUENO"
    if number >= 60:
        return "SATISFACTORIO"
    return "EN MEJORA"


def _document_number(periodo: str, teacher: dict[str, Any]) -> str:
    source = f"{periodo}|{teacher.get('codigo_doc')}|{teacher.get('cedula_doc')}"
    return str(int(hashlib.sha1(source.encode("utf-8")).hexdigest()[:8], 16))[-6:].zfill(6)


def _average(values: list[Any]) -> float:
    numbers = [_safe_float(value) for value in values if _clean(value) != ""]
    numbers = [value for value in numbers if value > 0]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 2)


def _weighted_average(rows: list[dict[str, Any]], value_field: str, weight_field: str) -> float:
    total = 0.0
    total_weight = 0.0
    for row in rows:
        value = _safe_float(row.get(value_field))
        weight = _safe_float(row.get(weight_field))
        if weight <= 0:
            continue
        total += value * weight
        total_weight += weight
    if total_weight <= 0:
        return _average([row.get(value_field) for row in rows])
    return round(total / total_weight, 2)


def _teacher_group_averages(rows: list[dict[str, Any]], report: dict[str, Any] | None = None) -> dict[str, float]:
    averages = {
        "estudiantes": _weighted_average(rows, "Promedio_Estudiantes", "Estudiantes_Esperados"),
        "par": _average([row.get("Promedio_Par_Docente") for row in rows]),
        "autoridad": _average([row.get("Promedio_Autoridad") for row in rows]),
        "auto": _average([row.get("Promedio_Autoevaluacion") for row in rows]),
        "final": _average([row.get("Puntaje_Final_360") for row in rows]),
    }
    if report and _clean_text(report.get("flow")) == "student":
        averages["final"] = averages["estudiantes"]
    if report and _clean_text(report.get("flow") or "all") == "all":
        flow_map = {
            "student": "estudiantes",
            "par_docente": "par",
            "academico_docente": "autoridad",
            "auto_docente": "auto",
        }
        weighted_total = 0.0
        weight_total = 0.0
        for flow, key in flow_map.items():
            score = averages.get(key, 0.0)
            weight = _flow_weight_from_rows(report.get("weights") or [], flow)
            if score > 0 and weight > 0:
                weighted_total += score * (weight / 100.0)
                weight_total += weight
        if weight_total > 0:
            averages["final"] = round(weighted_total, 2)
    return averages


def _teacher_component_breakdown(averages: dict[str, float], report: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    flow_map = {
        "student": "estudiantes",
        "par_docente": "par",
        "academico_docente": "autoridad",
        "auto_docente": "auto",
    }
    labels = {
        "student": "Evaluación estudiante-docente",
        "par_docente": "Evaluación par docente",
        "academico_docente": "Evaluación administrativa docente",
        "auto_docente": "Autoevaluación docente",
    }
    report_flow = _clean_text((report or {}).get("flow") or "all")
    components: dict[str, dict[str, float]] = {}
    final = 0.0
    for flow, average_key in flow_map.items():
        score = _safe_float(averages.get(average_key))
        weight = _flow_weight_from_rows((report or {}).get("weights") or [], flow)
        if report_flow != "all":
            weight = 100.0 if report_flow == flow else 0.0
        aporte = round(score * (weight / 100.0), 2) if weight > 0 else 0.0
        final += aporte
        components[flow] = {
            "label": labels[flow],
            "score": round(score, 2),
            "weight": round(weight, 2),
            "aporte": aporte,
        }
    components["final"] = {"score": round(final, 2), "weight": 100.0, "aporte": round(final, 2)}
    return components


def _component_targets(report: dict[str, Any], averages: dict[str, float]) -> dict[str, float]:
    targets = {"estudiantes": 0.0, "par": 0.0, "autoridad": 0.0, "auto": 0.0}
    for row in report.get("weights") or []:
        text = f"{_clean(row.get('Codigo'))} {_clean(row.get('Nombre'))}".upper()
        weight = _safe_float(row.get("Peso_Porcentaje") if row.get("Peso_Porcentaje") is not None else row.get("Peso_Default"))
        if weight <= 0:
            continue
        if "AUTO" in text and "ESTUDIANTE" not in text:
            targets["auto"] = max(targets["auto"], weight)
        elif "PAR" in text:
            targets["par"] = max(targets["par"], weight)
        elif "AUTORIDAD" in text or "ACADEMIC" in text or "COORD" in text or "DIRECT" in text:
            targets["autoridad"] = max(targets["autoridad"], weight)
        elif "ESTUDIANTE" in text:
            targets["estudiantes"] = max(targets["estudiantes"], weight)

    for key, value in averages.items():
        if key in targets and targets[key] <= 0:
            targets[key] = value or 100.0
    return targets


def _pdf_grade_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="EvalTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=14, leading=17, textColor=colors.HexColor("#0c1f42")))
    styles.add(ParagraphStyle(name="EvalSubtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8.5, leading=11, textColor=colors.HexColor("#4d5a78")))
    styles.add(ParagraphStyle(name="EvalSection", parent=styles["Heading2"], fontSize=10, leading=12, spaceBefore=5, textColor=colors.HexColor("#0c1f42")))
    styles.add(ParagraphStyle(name="EvalBody", parent=styles["BodyText"], fontSize=7.5, leading=9.2, textColor=colors.HexColor("#0c1f42")))
    styles.add(ParagraphStyle(name="EvalCell", parent=styles["BodyText"], fontSize=6.6, leading=7.8, textColor=colors.HexColor("#0c1f42")))
    styles.add(ParagraphStyle(name="EvalCellBold", parent=styles["EvalCell"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="EvalNote", parent=styles["BodyText"], fontSize=7, leading=9, textColor=colors.HexColor("#334155")))
    return styles


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    cleaned = _clean(value)
    return Paragraph(escape(str(cleaned)) if cleaned not in (None, "") else "-", style)


def _report_document_title(report: dict[str, Any]) -> str:
    flow = _clean_text(report.get("flow") or "all")
    document_type = _clean_text(report.get("document_type") or "certificado")
    flow_label = {
        "all": "EVALUACIÓN DESEMPEÑO DOCENTE 360",
        "student": "EVALUACIÓN DEL ESTUDIANTE AL DOCENTE",
        "auto_docente": "AUTOEVALUACIÓN DOCENTE",
        "par_docente": "EVALUACIÓN PAR DOCENTE",
        "academico_docente": "EVALUACIÓN ADMINISTRATIVA DOCENTE",
    }.get(flow, "EVALUACIÓN DOCENTE")
    prefix = {
        "certificado": "CERTIFICADO",
        "resumen": "REPORTE RESUMEN",
        "detalle": "REPORTE DETALLADO",
    }.get(document_type, "CERTIFICADO")
    return f"{prefix} DE {flow_label}"


def _build_teacher_grade_pdf(report: dict[str, Any]) -> bytes:
    output = BytesIO()
    styles = _pdf_grade_styles()
    page_width, page_height = A4
    template_bytes = _template_page_image()
    template_reader = ImageReader(BytesIO(template_bytes)) if template_bytes else None
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=1.05 * cm,
        rightMargin=1.05 * cm,
        topMargin=1.15 * cm,
        bottomMargin=1.0 * cm,
        title="Certificado de evaluacion docente",
    )
    story: list[Any] = []

    teachers = report.get("teachers") or []
    document_title = _report_document_title(report)
    document_type = _clean_text(report.get("document_type") or "certificado")
    if not teachers:
        story.extend(
            [
                _SvgLogo(_LOGO_PATH, 4.8 * cm),
                Spacer(1, 0.35 * cm),
                Paragraph(document_title, styles["EvalTitle"]),
                Paragraph(
                    f"Periodo: {escape(report.get('periodo_detalle') or report.get('periodo') or '-')}",
                    styles["EvalSubtitle"],
                ),
                Spacer(1, 0.5 * cm),
            ]
        )
        story.append(Paragraph("No existen calificaciones registradas para el periodo seleccionado.", styles["EvalBody"]))
    for teacher_index, teacher_group in enumerate(teachers):
        if teacher_index:
            story.append(PageBreak())
        teacher = teacher_group["teacher"]
        rows = teacher_group.get("rows") or []
        averages = _teacher_group_averages(rows, report)
        components = _teacher_component_breakdown(averages, report)
        document_number = _document_number(_clean(report.get("periodo")), teacher)
        period_label = _clean(report.get("periodo_detalle")) or _clean(report.get("periodo"))
        final_score = _safe_float(components.get("final", {}).get("aporte")) or averages["final"]
        level = _grade_level(final_score)
        first_row = rows[0] if rows else {}
        targets = _component_targets(report, averages)

        header_table = Table(
            [
                [
                    _SvgLogo(_LOGO_PATH, 4.8 * cm),
                    Paragraph(
                        "<b>INSTITUTO TECNOLÓGICO SUPERIOR INTEC</b><br/>"
                        "QUITO - ECUADOR<br/>"
                        f"<font size='13'><b>{escape(document_title)}</b></font>",
                        styles["EvalSubtitle"],
                    ),
                    Paragraph(f"<b>Documento # {escape(document_number)}</b>", styles["EvalBody"]),
                ]
            ],
            colWidths=[4.9 * cm, 9.7 * cm, 4.2 * cm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 0.15 * cm))

        data_table = Table(
            [
                [
                    Paragraph("<b>DATOS DOCENTE</b>", styles["EvalCellBold"]),
                    Paragraph("<b>DATOS DE EVALUACIÓN</b>", styles["EvalCellBold"]),
                ],
                [
                    Paragraph(
                        f"<b>Cédula:</b> {escape(_clean(teacher.get('cedula_doc')) or '-')}<br/>"
                        f"<b>Docente:</b> {escape(_clean(teacher.get('docente')) or '-')}<br/>"
                        f"<b>Código docente:</b> {escape(_clean(teacher.get('codigo_doc')) or '-')}<br/>"
                        f"<b>Periodo:</b> {escape(period_label or '-')}",
                        styles["EvalBody"],
                    ),
                    Paragraph(
                        f"<b>Carrera:</b> {escape(_clean(first_row.get('carrera')) or '-')}<br/>"
                        f"<b>Materias evaluadas:</b> {len(rows)}<br/>"
                        f"<b>Fecha de emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/>"
                        f"<b>Modelo:</b> {escape(_clean_text(report.get('flow')) or 'all').upper()} · {escape(_clean_text(report.get('document_type')) or 'certificado').upper()}",
                        styles["EvalBody"],
                    ),
                ],
            ],
            colWidths=[9.35 * cm, 9.35 * cm],
        )
        data_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8d8d8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0c1f42")),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#3f3f46")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#a8a8a8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(data_table)
        story.append(Spacer(1, 0.22 * cm))

        summary_rows: list[list[Any]] = [[
            _p("Materia", styles["EvalCellBold"]),
            _p("Carrera", styles["EvalCellBold"]),
            _p("Paralelo", styles["EvalCellBold"]),
            _p("Base est.", styles["EvalCellBold"]),
            _p("Cob.", styles["EvalCellBold"]),
            _p("Est.", styles["EvalCellBold"]),
            _p("Par", styles["EvalCellBold"]),
            _p("Autoridad", styles["EvalCellBold"]),
            _p("Auto", styles["EvalCellBold"]),
            _p("Final", styles["EvalCellBold"]),
        ]]
        for row in rows:
            summary_rows.append([
                _p(row.get("materia"), styles["EvalCell"]),
                _p(row.get("carrera"), styles["EvalCell"]),
                _p(row.get("Paralelo"), styles["EvalCell"]),
                _p(f"{_safe_int(row.get('Estudiantes_Completaron'))}/{_safe_int(row.get('Estudiantes_Esperados'))}", styles["EvalCell"]),
                _p(f"{_safe_float(row.get('Cobertura_Estudiantes')):.2f}%", styles["EvalCell"]),
                _p(row.get("Promedio_Estudiantes"), styles["EvalCell"]),
                _p(row.get("Promedio_Par_Docente"), styles["EvalCell"]),
                _p(row.get("Promedio_Autoridad"), styles["EvalCell"]),
                _p(row.get("Promedio_Autoevaluacion"), styles["EvalCell"]),
                _p(row.get("Puntaje_Final_360"), styles["EvalCell"]),
            ])
        table = Table(
            summary_rows,
            colWidths=[3.25 * cm, 3.25 * cm, 1.25 * cm, 1.45 * cm, 1.35 * cm, 1.35 * cm, 1.35 * cm, 1.55 * cm, 1.25 * cm, 1.55 * cm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b8b8b8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0c1f42")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#8e8e8e")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Paragraph("<b>MATRIZ DE COMPONENTES</b>", styles["EvalSection"]))
        story.append(table)

        story.append(Spacer(1, 0.2 * cm))
        if _clean_text(report.get("flow") or "all") == "all":
            weights_table_rows: list[list[Any]] = [[
                _p("Componente", styles["EvalCellBold"]),
                _p("Ponderación máxima", styles["EvalCellBold"]),
                _p("Promedio ajustado", styles["EvalCellBold"]),
                _p("Aporte real", styles["EvalCellBold"]),
            ]]
            weight_components = [
                ("Evaluación estudiante-docente", "student", "estudiantes"),
                ("Evaluación par docente", "par_docente", "par"),
                ("Evaluación administrativa docente", "academico_docente", "autoridad"),
                ("Autoevaluación docente", "auto_docente", "auto"),
            ]
            for label, flow_key, average_key in weight_components:
                component = components.get(flow_key, {})
                weight = _safe_float(component.get("weight"))
                average = _safe_float(component.get("score") or averages.get(average_key))
                aporte = _safe_float(component.get("aporte"))
                weights_table_rows.append([
                    _p(label, styles["EvalCell"]),
                    _p(f"{weight:.2f}%", styles["EvalCell"]),
                    _p(f"{average:.2f}", styles["EvalCell"]),
                    _p(f"{aporte:.2f}", styles["EvalCell"]),
                ])
            weights_table = Table(weights_table_rows, colWidths=[7.4 * cm, 3.8 * cm, 3.2 * cm, 3.2 * cm], repeatRows=1)
            weights_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8d8d8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#8e8e8e")),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(Paragraph("<b>PONDERACIONES DEL PERIODO</b>", styles["EvalSection"]))
            story.append(weights_table)
            story.append(Spacer(1, 0.2 * cm))

        score_table = Table(
            [
                [
                    Paragraph("<b>CUMPLIMIENTO POR COMPONENTE</b>", styles["EvalCellBold"]),
                    Paragraph("<b>PUNTAJE FINAL</b>", styles["EvalCellBold"]),
                    Paragraph("<b>NIVEL</b>", styles["EvalCellBold"]),
                ],
                [
                    _ComplianceBars(
                        [
                            ("Heteroevaluación", _safe_float(components.get("student", {}).get("aporte")), _safe_float(components.get("student", {}).get("weight"))),
                            ("Coevaluación pares", _safe_float(components.get("par_docente", {}).get("aporte")), _safe_float(components.get("par_docente", {}).get("weight"))),
                            ("Evaluación autoridad", _safe_float(components.get("academico_docente", {}).get("aporte")), _safe_float(components.get("academico_docente", {}).get("weight"))),
                            ("Autoevaluación", _safe_float(components.get("auto_docente", {}).get("aporte")), _safe_float(components.get("auto_docente", {}).get("weight"))),
                            ("Final 360", final_score, 100.0),
                        ],
                        width=9.2 * cm,
                    ),
                    Paragraph(f"<font size='24'><b>{final_score:.0f}</b></font><br/><font size='8'>{final_score:.2f}/100</font>", styles["EvalSubtitle"]),
                    Paragraph(f"<font size='16'><b>{escape(level)}</b></font>", styles["EvalSubtitle"]),
                ],
            ],
            colWidths=[9.7 * cm, 3.8 * cm, 5.2 * cm],
        )
        score_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8d8d8")),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (1, 1), (-1, 1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#3f3f46")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#a8a8a8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(score_table)
        story.append(Spacer(1, 0.28 * cm))

        if document_type == "detalle":
            detail_rows: list[list[Any]] = [[
                _p("Materia", styles["EvalCellBold"]),
                _p("Tipo", styles["EvalCellBold"]),
                _p("Dimensión", styles["EvalCellBold"]),
                _p("Evaluaciones", styles["EvalCellBold"]),
                _p("Respuestas", styles["EvalCellBold"]),
                _p("Promedio", styles["EvalCellBold"]),
            ]]
            for row in rows:
                for dimension in row.get("dimensiones") or []:
                    detail_rows.append([
                        _p(row.get("materia"), styles["EvalCell"]),
                        _p(dimension.get("Tipo_Evaluacion"), styles["EvalCell"]),
                        _p(dimension.get("Dimension_Global"), styles["EvalCell"]),
                        _p(dimension.get("Total_Evaluaciones"), styles["EvalCell"]),
                        _p(dimension.get("Total_Respuestas"), styles["EvalCell"]),
                        _p(dimension.get("Promedio_Dimension"), styles["EvalCell"]),
                    ])
            if len(detail_rows) > 1:
                detail_table = Table(detail_rows, colWidths=[4.2 * cm, 3.4 * cm, 4.5 * cm, 2.1 * cm, 2.1 * cm, 2.0 * cm], repeatRows=1)
                detail_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8d8d8")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#8e8e8e")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
                    ("ALIGN", (3, 1), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(Paragraph("<b>DETALLE POR DIMENSIÓN</b>", styles["EvalSection"]))
                story.append(detail_table)
                story.append(Spacer(1, 0.2 * cm))

        note = (
            "Nota: El personal académico que no esté de acuerdo con los resultados de su evaluación "
            "podrá presentar la impugnación respectiva ante la autoridad académica correspondiente, "
            "según la normativa institucional vigente de evaluación integral del desempeño docente."
        )
        story.append(Paragraph(note, styles["EvalNote"]))
        story.append(Spacer(1, 0.2 * cm))
        story.append(
            Table(
                [[Paragraph("<br/><br/>____________________________<br/><b>Coordinación Académica</b>", styles["EvalSubtitle"])]],
                colWidths=[18.7 * cm],
            )
        )

    def draw_template(canvas: Any, _doc: Any) -> None:
        canvas.saveState()
        if template_reader:
            canvas.drawImage(template_reader, 0, 0, width=page_width, height=page_height, mask="auto")
            if hasattr(canvas, "setFillAlpha"):
                canvas.setFillAlpha(0.96)
        canvas.setFillColor(colors.white)
        canvas.roundRect(0.55 * cm, 0.75 * cm, page_width - 1.1 * cm, page_height - 1.5 * cm, 8, stroke=0, fill=1)
        if hasattr(canvas, "setFillAlpha"):
            canvas.setFillAlpha(1)
        canvas.setStrokeColor(colors.HexColor("#808080"))
        canvas.setLineWidth(0.55)
        canvas.roundRect(0.55 * cm, 0.75 * cm, page_width - 1.1 * cm, page_height - 1.5 * cm, 8, stroke=1, fill=0)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.drawCentredString(page_width / 2, 0.42 * cm, "Documento generado por el Sistema Académico INTEC")
        canvas.drawRightString(page_width - 0.85 * cm, 0.42 * cm, f"Página {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_template, onLaterPages=draw_template)
    return output.getvalue()


def _save_application(
    evaluation_cursor: pyodbc.Cursor,
    *,
    flow: str,
    instrument: dict[str, Any],
    campaign_id: int,
    evaluator_code: int,
    evaluated_student_code: int | None,
    course: dict[str, Any],
    answers: list[TeacherEvaluationAnswer],
    origin_table: str,
    origin_evaluator_table: str,
    origin_evaluated_table: str,
    authority_id: int | None = None,
) -> dict[str, Any]:
    config = _flow_config(flow)
    now = datetime.now()
    origin_key = _origin_key(evaluator_code, course, flow)
    jornada = course.get("cod_jornada") or course.get("jornada") or ""
    token = str(uuid.uuid4()) if config.get("anonymous") else None
    evaluation_cursor.execute(
        """
        INSERT INTO eval360.Aplicacion
            (Id_Asignacion, Id_Campania, Id_Tipo_Evaluacion, Id_Instrumento,
             Cod_Periodo, Cod_Materia, Jornada, Paralelo, Modalidad,
             Cod_Docente_Evaluado, Cod_Estudiante_Evaluado, Tipo_Evaluador,
             Cod_Evaluador, Token_Anonimo, Fecha_Inicio, Fecha_Envio, Estado,
             Observacion_General, Origen_Tabla, Origen_Clave, Cod_Carrera,
             Id_Autoridad, Origen_Evaluador_Tabla, Origen_Evaluador_Clave,
             Origen_Evaluado_Tabla, Origen_Evaluado_Clave)
        OUTPUT INSERTED.Id_Aplicacion
        VALUES
            (NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'FINALIZADA',
             NULL, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        campaign_id,
        _safe_int(instrument["Id_Tipo_Evaluacion"]),
        _safe_int(instrument["Id_Instrumento"]),
        str(_safe_int(course.get("codigo_periodo"))),
        str(_safe_int(course.get("codigo_materia"))),
        str(jornada),
        str(course.get("paralelo") or ""),
        str(_safe_int(course.get("codigo_docente_eval"))),
        str(evaluated_student_code) if evaluated_student_code is not None else None,
        config["evaluator_type"],
        str(evaluator_code),
        token,
        now,
        now,
        origin_table,
        origin_key,
        str(course.get("cod_anio_basica") or ""),
        authority_id,
        origin_evaluator_table,
        str(evaluator_code),
        origin_evaluated_table,
        str(_safe_int(course.get("codigo_docente_eval"))),
    )
    application_row = evaluation_cursor.fetchone()
    if not application_row:
        raise HTTPException(status_code=500, detail="No se pudo crear la aplicación de evaluación.")
    application_id = _safe_int(application_row[0])

    for answer in answers:
        evaluation_cursor.execute(
            """
            INSERT INTO eval360.Respuesta
                (Id_Aplicacion, Id_Pregunta, Puntaje, Respuesta_Texto, Fecha_Respuesta)
            VALUES (?, ?, ?, NULL, ?)
            """,
            application_id,
            answer.id_pregunta,
            answer.puntaje,
            now,
        )

    total = len(answers)
    average = round(sum(answer.puntaje for answer in answers) / total, 2) if total else 0
    course["evaluado"] = True
    course["respuestas_registradas"] = total
    return {
        "saved": total,
        "average": average,
        "application_id": application_id,
        "course": course,
    }


@router.get("/questions")
def get_teacher_evaluation_questions(flow: str = Query(default="student")) -> dict[str, Any]:
    try:
        with get_evaluation_connection() as conn:
            cursor = conn.cursor()
            instrument, rows = _fetch_question_rows(cursor, flow)
            items = [_question_from_row(_row_dict(cursor, row)) for row in rows]
            return {"flow": flow, "instrument": instrument, "items": items, "total": len(items)}
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar el cuestionario 360: {exc}") from exc


@router.get("/admin/periodos")
def get_teacher_evaluation_admin_periods(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP {limit}
                    TRY_CONVERT(varchar(50), p.cod_periodo) AS codigo_periodo,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), p.Detalle_Periodo))) AS detalle_periodo,
                    ISNULL(TRY_CONVERT(int, p.Orden), 0) AS orden
                FROM dbo.PERIODO p
                WHERE EXISTS (
                    SELECT 1
                    FROM dbo.CARRERAXDOCENTE cxd
                    WHERE cxd.codigo_periodo = p.cod_periodo
                )
                GROUP BY p.cod_periodo, p.Detalle_Periodo, p.Orden
                ORDER BY ISNULL(TRY_CONVERT(int, p.Orden), 0) DESC, TRY_CONVERT(int, p.cod_periodo) DESC
                """
            )
            items = [_period_row(row) for row in cursor.fetchall()]
            return {"items": items, "total": len(items)}
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar periodos de evaluacion docente: {exc}") from exc


@router.get("/admin/pendientes")
def get_teacher_evaluation_admin_pending(
    periodo: str = Query(..., min_length=1),
    flow: str = Query(default="all"),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict[str, Any]:
    allowed_flows = ("student", "auto_estudiante", "auto_docente", "par_docente", "academico_docente")
    flows = list(allowed_flows) if flow == "all" else [flow]
    for item in flows:
        if item not in allowed_flows:
            raise HTTPException(status_code=400, detail="Tipo de evaluacion no valido para reporte administrativo.")

    items: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {
        item: {
            "flow": item,
            "flow_label": _flow_config(item)["label"],
            "expected": 0,
            "completed": 0,
            "pending": 0,
            "progress_percent": 0,
            "ponderacion": 0,
        }
        for item in flows
    }
    period_label = periodo
    teacher_progress: dict[str, dict[str, Any]] = {}
    flow_weights: dict[str, float] = {}

    try:
        with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
            academic_cursor = academic_conn.cursor()
            evaluation_cursor = evaluation_conn.cursor()
            academic_cursor.execute(
                """
                SELECT TOP 1 LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), Detalle_Periodo)))
                FROM dbo.PERIODO
                WHERE TRY_CONVERT(varchar(50), cod_periodo) = ?
                """,
                periodo,
            )
            period_row = academic_cursor.fetchone()
            if period_row and period_row[0]:
                period_label = _clean_text(period_row[0])

            for current_flow in flows:
                instrument = _get_instrument(evaluation_cursor, current_flow)
                flow_weight = _evaluation_type_weight(evaluation_cursor, instrument, periodo)
                flow_weights[current_flow] = flow_weight
                summary[current_flow]["ponderacion"] = flow_weight
                expected_rows = _admin_expected_rows(academic_cursor, periodo, current_flow, limit)
                summary[current_flow]["expected"] = len(expected_rows)
                for expected in expected_rows:
                    course = expected["course"]
                    if current_flow == "academico_docente":
                        completed = _evaluation_any_authority_count(evaluation_cursor, instrument=instrument, course=course)
                    else:
                        origin_key = _origin_key(expected["evaluator_code"], course, current_flow)
                        completed = _evaluation_count(
                            evaluation_cursor,
                            flow=current_flow,
                            instrument=instrument,
                            evaluator_code=expected["evaluator_code"],
                            course=course,
                            origin_key=origin_key,
                        )
                    teacher_code = _safe_int(course.get("codigo_docente_eval"))
                    if teacher_code:
                        progress_flow = current_flow
                        progress_flow_label = _flow_config(current_flow)["label"]
                        progress_key = "|".join(
                            [
                                progress_flow,
                                str(teacher_code),
                                _course_subject_key(course, include_teacher=True),
                            ]
                        )
                        if progress_key not in teacher_progress:
                            teacher_progress[progress_key] = {
                                "flow": progress_flow,
                                "flow_label": progress_flow_label,
                                "codigo_doc": str(teacher_code),
                                "docente": _clean_text(course.get("docente")) or f"Docente {teacher_code}",
                                "cedula_doc": _clean_text(course.get("cedula_docente")),
                                "codigo_periodo": str(_safe_int(course.get("codigo_periodo"))),
                                "periodo_detalle": period_label,
                                "codigo_materia": str(_safe_int(course.get("codigo_materia"))),
                                "codigo_materia_interno": _clean_text(course.get("codigo_materia_interno")),
                                "materia": _clean_text(course.get("materia")) or f"Materia {course.get('codigo_materia')}",
                                "carrera": _clean_text(course.get("carrera")),
                                "paralelo": _clean_text(course.get("paralelo")),
                                "expected": 0,
                                "completed": 0,
                                "pending": 0,
                                "progress_percent": 0,
                                "ponderacion": 0,
                                "ponderacion_aplicada": 0,
                                "flows": {},
                            }
                        teacher_progress[progress_key]["expected"] += 1
                        flow_detail = teacher_progress[progress_key]["flows"].setdefault(
                            current_flow,
                            {"expected": 0, "completed": 0, "ponderacion": flow_weight},
                        )
                        flow_detail["expected"] += 1
                        if completed > 0:
                            teacher_progress[progress_key]["completed"] += 1
                            flow_detail["completed"] += 1
                    if completed > 0:
                        summary[current_flow]["completed"] += 1
                        continue
                    summary[current_flow]["pending"] += 1
                    items.append(
                        {
                            **expected,
                            "periodo": periodo,
                            "periodo_detalle": period_label,
                            "estado": "PENDIENTE",
                        }
                    )
                expected_total = _safe_int(summary[current_flow]["expected"])
                completed_total = _safe_int(summary[current_flow]["completed"])
                summary[current_flow]["progress_percent"] = round((completed_total / expected_total) * 100, 2) if expected_total else 0

        teacher_progress_items = []
        for progress in teacher_progress.values():
            expected = _safe_int(progress.get("expected"))
            completed = _safe_int(progress.get("completed"))
            progress["pending"] = max(expected - completed, 0)
            progress["progress_percent"] = round((completed / expected) * 100, 2) if expected else 0
            assigned_weight = 0.0
            applied_weight = 0.0
            for flow_detail in (progress.get("flows") or {}).values():
                flow_expected = _safe_int(flow_detail.get("expected"))
                flow_completed = _safe_int(flow_detail.get("completed"))
                flow_weight = _safe_float(flow_detail.get("ponderacion"))
                if flow_expected <= 0:
                    continue
                assigned_weight += flow_weight
                applied_weight += (flow_completed / flow_expected) * flow_weight
            progress["ponderacion"] = round(assigned_weight, 2)
            progress["ponderacion_aplicada"] = round(applied_weight, 2)
            progress.pop("flows", None)
            teacher_progress_items.append(progress)
        teacher_progress_items.sort(
            key=lambda row: (
                _clean_text(row.get("materia")).upper(),
                _clean_text(row.get("docente")).upper(),
                _clean_text(row.get("flow_label")).upper(),
            )
        )

        return {
            "periodo": periodo,
            "periodo_detalle": period_label,
            "flow": flow,
            "summary": list(summary.values()),
            "teacher_progress": teacher_progress_items,
            "items": items[:limit],
            "total": len(items[:limit]),
        }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar pendientes de evaluacion docente: {exc}") from exc


def _related_subject_codes(cursor: pyodbc.Cursor, codigo_materia: str) -> list[str]:
    code = _clean_text(codigo_materia)
    if not code:
        return []
    cursor.execute(
        """
        SELECT DISTINCT TRY_CONVERT(varchar(50), related.codigo_materia) AS codigo_materia
        FROM dbo.PENSUM selected
        INNER JOIN dbo.PENSUM related
            ON LTRIM(RTRIM(related.cod_materia)) = LTRIM(RTRIM(selected.cod_materia))
        WHERE TRY_CONVERT(varchar(50), selected.codigo_materia) = ?
          AND NULLIF(LTRIM(RTRIM(selected.cod_materia)), '') IS NOT NULL
        ORDER BY TRY_CONVERT(varchar(50), related.codigo_materia)
        """,
        code,
    )
    codes = [_clean_text(row.codigo_materia) for row in cursor.fetchall() if _clean_text(row.codigo_materia)]
    if code not in codes:
        codes.insert(0, code)
    return codes


@router.get("/admin/progreso-detalle")
def get_teacher_evaluation_progress_detail(
    periodo: str = Query(..., min_length=1),
    codigo_docente: str = Query(..., min_length=1),
    codigo_materia: str = Query(..., min_length=1),
    flow: str = Query(default="all"),
) -> dict[str, Any]:
    report_flow = _clean_text(flow or "all")
    if report_flow != "all" and report_flow not in {"student", "auto_docente", "par_docente", "academico_docente"}:
        raise HTTPException(status_code=400, detail="Tipo de evaluacion no valido para el grafico.")
    try:
        teachers, subjects, _, period_label = _teacher_evaluation_academic_maps(periodo)
        teacher = teachers.get(
            _clean_text(codigo_docente),
            {"codigo_doc": _clean_text(codigo_docente), "docente": f"Docente {codigo_docente}", "cedula_doc": ""},
        )
        subject = subjects.get(
            f"{_clean_text(codigo_docente)}|{_clean_text(codigo_materia)}",
            {"materia": _clean_text(codigo_materia), "carrera": ""},
        )
        with get_connection() as academic_conn:
            academic_cursor = academic_conn.cursor()
            subject_codes = _related_subject_codes(academic_cursor, codigo_materia)
            expected_student_total = sum(
                _expected_students_for_teacher_subject(
                    academic_cursor,
                    periodo,
                    codigo_docente,
                    subject_code,
                )
                for subject_code in subject_codes
            )
        with get_evaluation_connection() as conn:
            cursor = conn.cursor()
            weights = _evaluation_weights_for_period(cursor, periodo)
            subject_codes = subject_codes or [_clean_text(codigo_materia)]
            placeholders = ", ".join("?" for _ in subject_codes)
            cursor.execute(
                f"""
                SELECT
                    Tipo_Evaluacion,
                    Dimension_Global,
                    SUM(ISNULL(Total_Evaluaciones, 0)) AS Total_Evaluaciones,
                    SUM(ISNULL(Total_Respuestas, 0)) AS Total_Respuestas,
                    AVG(TRY_CONVERT(float, Promedio_Dimension)) AS Promedio_Dimension
                FROM eval360.vw_Resultado_Dimension_Docente
                WHERE Cod_Periodo = ?
                  AND Cod_Docente_Evaluado = ?
                  AND Cod_Materia IN ({placeholders})
                GROUP BY Tipo_Evaluacion, Dimension_Global
                ORDER BY Tipo_Evaluacion, Dimension_Global
                """,
                periodo,
                codigo_docente,
                *subject_codes,
            )
            rows = [_row_dict(cursor, row) for row in cursor.fetchall()]

        prepared_rows: list[tuple[dict[str, Any], str]] = []
        flow_category_counts: dict[str, int] = {}
        for row in rows:
            item_flow = _flow_from_type_text(row.get("Tipo_Evaluacion"))
            if report_flow != "all" and item_flow != report_flow:
                continue
            prepared_rows.append((row, item_flow))
            flow_category_counts[item_flow] = flow_category_counts.get(item_flow, 0) + 1

        items: list[dict[str, Any]] = []
        for row, item_flow in prepared_rows:
            average = _score_to_100(row.get("Promedio_Dimension"))
            evaluations = _safe_int(row.get("Total_Evaluaciones"))
            coverage_expected = expected_student_total if item_flow == "student" else evaluations
            coverage = min(evaluations / coverage_expected, 1.0) if coverage_expected > 0 else 0.0
            adjusted_average = round(average * coverage, 2) if item_flow == "student" else average
            type_weight = _flow_weight_from_rows(weights, item_flow) if item_flow else 0.0
            category_count = max(flow_category_counts.get(item_flow, 0), 1)
            category_weight = type_weight / category_count if type_weight else 0.0
            items.append(
                {
                    "flow": item_flow or "all",
                    "flow_label": _clean_text(row.get("Tipo_Evaluacion")) or "Evaluacion",
                    "categoria": _clean_text(row.get("Dimension_Global")) or "Categoria general",
                    "promedio": average,
                    "promedio_ajustado": adjusted_average,
                    "ponderacion": round(category_weight, 2),
                    "ponderacion_tipo": round(type_weight, 2),
                    "aporte": round(adjusted_average * category_weight / 100.0, 2),
                    "cobertura": round(coverage * 100.0, 2),
                    "esperadas": coverage_expected,
                    "evaluaciones": evaluations,
                    "respuestas": _safe_int(row.get("Total_Respuestas")),
                }
            )

        return {
            "periodo": periodo,
            "periodo_detalle": period_label,
            "flow": report_flow,
            "codigo_docente": _clean_text(codigo_docente),
            "codigo_materia": _clean_text(codigo_materia),
            "docente": teacher.get("docente"),
            "cedula_doc": teacher.get("cedula_doc"),
            "materia": subject.get("materia"),
            "carrera": subject.get("carrera"),
            "weights": weights,
            "items": items,
            "total": len(items),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar detalle de progreso docente: {exc}") from exc


@router.get("/admin/progreso-participantes")
def get_teacher_evaluation_progress_participants(
    periodo: str = Query(..., min_length=1),
    codigo_docente: str = Query(..., min_length=1),
    codigo_materia: str = Query(..., min_length=1),
    flow: str = Query(default="all"),
    estado: str = Query(default="completadas"),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> dict[str, Any]:
    report_flow = _clean_text(flow or "all")
    status = _clean_text(estado).lower()
    if report_flow != "all" and report_flow not in _EVALUATION_FLOWS:
        raise HTTPException(status_code=400, detail="Tipo de evaluacion no valido para participantes.")
    if status not in {"completadas", "pendientes"}:
        raise HTTPException(status_code=400, detail="Estado no valido para participantes.")
    flows = ("student", "auto_estudiante", "auto_docente", "par_docente", "academico_docente") if report_flow == "all" else (report_flow,)

    try:
        with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
            academic_cursor = academic_conn.cursor()
            evaluation_cursor = evaluation_conn.cursor()
            academic_cursor.execute(
                """
                SELECT TOP 1 LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), Detalle_Periodo)))
                FROM dbo.PERIODO
                WHERE TRY_CONVERT(varchar(50), cod_periodo) = ?
                """,
                periodo,
            )
            period_row = academic_cursor.fetchone()
            period_label = _clean_text(period_row[0]) if period_row and period_row[0] else periodo

            items: list[dict[str, Any]] = []
            subject_label = _clean_text(codigo_materia)
            teacher_label = f"Docente {codigo_docente}"
            for current_flow in flows:
                if current_flow not in _EVALUATION_FLOWS:
                    continue
                instrument = _get_instrument(evaluation_cursor, current_flow)
                expected_rows = _admin_expected_rows(academic_cursor, periodo, current_flow, limit)
                for expected in expected_rows:
                    course = expected.get("course") or {}
                    if _clean_text(course.get("codigo_docente_eval")) != _clean_text(codigo_docente):
                        continue
                    if _clean_text(course.get("codigo_materia")) != _clean_text(codigo_materia):
                        continue
                    subject_label = _clean_text(course.get("materia")) or subject_label
                    teacher_label = _clean_text(course.get("docente")) or teacher_label
                    if current_flow == "academico_docente":
                        completed = _evaluation_any_authority_count(evaluation_cursor, instrument=instrument, course=course)
                    else:
                        origin_key = _origin_key(expected.get("evaluator_code") or 0, course, current_flow)
                        completed = _evaluation_count(
                            evaluation_cursor,
                            flow=current_flow,
                            instrument=instrument,
                            evaluator_code=_safe_int(expected.get("evaluator_code")),
                            course=course,
                            origin_key=origin_key,
                        )
                    is_completed = completed > 0
                    if status == "completadas" and not is_completed:
                        continue
                    if status == "pendientes" and is_completed:
                        continue
                    evaluator_code = _safe_int(expected.get("evaluator_code"))
                    items.append(
                        {
                            "flow": current_flow,
                            "flow_label": _flow_config(current_flow)["label"],
                            "estado": "COMPLETADA" if is_completed else "PENDIENTE",
                            "evaluator_code": evaluator_code,
                            "evaluator_name": _clean_text(expected.get("evaluator_name")) or "Administrativo",
                            "evaluator_cedula": _clean_text(expected.get("evaluator_cedula")),
                            "can_view_grades": current_flow in {"student", "auto_estudiante"} and evaluator_code > 0,
                            "completed_count": completed,
                        }
                    )
        return {
            "periodo": periodo,
            "periodo_detalle": period_label,
            "codigo_docente": _clean_text(codigo_docente),
            "codigo_materia": _clean_text(codigo_materia),
            "docente": teacher_label,
            "materia": subject_label,
            "flow": report_flow,
            "estado": status,
            "items": items,
            "total": len(items),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar participantes de evaluacion: {exc}") from exc


@router.get("/admin/avance-estudiantes")
def get_teacher_evaluation_student_progress(
    periodo: str = Query(..., min_length=1),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
            academic_cursor = academic_conn.cursor()
            evaluation_cursor = evaluation_conn.cursor()
            academic_cursor.execute(
                """
                SELECT TOP 1 LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), Detalle_Periodo)))
                FROM dbo.PERIODO
                WHERE TRY_CONVERT(varchar(50), cod_periodo) = ?
                """,
                periodo,
            )
            period_row = academic_cursor.fetchone()
            period_label = _clean_text(period_row[0]) if period_row and period_row[0] else periodo

            expected = _student_progress_expected(academic_cursor, periodo, limit)
            student_codes = [_safe_int(item.get("codigo_estud")) for item in expected if _safe_int(item.get("codigo_estud"))]
            completed_student = _student_progress_completed(evaluation_cursor, periodo, student_codes, "student")
            completed_auto = _student_progress_completed(evaluation_cursor, periodo, student_codes, "auto_estudiante")
            student_weight = _evaluation_type_weight(evaluation_cursor, _get_instrument(evaluation_cursor, "student"))
            auto_weight = _evaluation_type_weight(evaluation_cursor, _get_instrument(evaluation_cursor, "auto_estudiante"))

        items: list[dict[str, Any]] = []
        total_expected = 0
        total_auto_expected = 0
        total_student_completed = 0
        total_auto_completed = 0
        for item in expected:
            code = _safe_int(item.get("codigo_estud"))
            expected_count = _safe_int(item.get("materias_evaluables"))
            auto_expected_count = _safe_int(item.get("materias_autoevaluables")) or expected_count
            student_done = min(_safe_int(completed_student.get(code)), expected_count)
            auto_done = min(_safe_int(completed_auto.get(code)), auto_expected_count)
            total_expected += expected_count
            total_auto_expected += auto_expected_count
            total_student_completed += student_done
            total_auto_completed += auto_done
            item_payload = {
                **item,
                "evaluacion_docente": {
                    "ponderacion": student_weight,
                    "esperadas": expected_count,
                    "completadas": student_done,
                    "pendientes": max(expected_count - student_done, 0),
                    "avance_percent": round((student_done / expected_count) * 100, 2) if expected_count else 0,
                },
                "autoevaluacion_estudiante": {
                    "ponderacion": auto_weight,
                    "esperadas": auto_expected_count,
                    "completadas": auto_done,
                    "pendientes": max(auto_expected_count - auto_done, 0),
                    "avance_percent": round((auto_done / auto_expected_count) * 100, 2) if auto_expected_count else 0,
                },
            }
            combined_expected = expected_count + auto_expected_count
            item_payload["avance_total_percent"] = round(((student_done + auto_done) / combined_expected) * 100, 2) if combined_expected else 0
            items.append(item_payload)

        summary = {
            "estudiantes": len(items),
            "materias_evaluables": total_expected,
            "materias_autoevaluables": total_auto_expected,
            "evaluacion_docente": {
                "ponderacion": student_weight,
                "completadas": total_student_completed,
                "pendientes": max(total_expected - total_student_completed, 0),
                "avance_percent": round((total_student_completed / total_expected) * 100, 2) if total_expected else 0,
            },
            "autoevaluacion_estudiante": {
                "ponderacion": auto_weight,
                "completadas": total_auto_completed,
                "pendientes": max(total_auto_expected - total_auto_completed, 0),
                "avance_percent": round((total_auto_completed / total_auto_expected) * 100, 2) if total_auto_expected else 0,
            },
        }
        return {
            "periodo": periodo,
            "periodo_detalle": period_label,
            "summary": summary,
            "items": items,
            "total": len(items),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar avance por estudiante: {exc}") from exc


@router.get("/admin/autoevaluacion-estudiantes")
def get_teacher_evaluation_auto_student_list(
    periodo: str = Query(..., min_length=1),
    estado: str = Query(default="pendientes"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    normalized_status = _clean_text(estado).lower()
    if normalized_status not in {"pendientes", "realizadas", "todos"}:
        raise HTTPException(status_code=400, detail="Estado no valido para autoevaluacion estudiantil.")
    try:
        with get_connection() as academic_conn, get_evaluation_connection() as evaluation_conn:
            academic_cursor = academic_conn.cursor()
            evaluation_cursor = evaluation_conn.cursor()
            expected = _student_progress_expected(academic_cursor, periodo, limit)
            completed = _student_progress_completed(
                evaluation_cursor,
                periodo,
                [_safe_int(item.get("codigo_estud")) for item in expected],
                "auto_estudiante",
            )
            items: list[dict[str, Any]] = []
            for item in expected:
                code = _safe_int(item.get("codigo_estud"))
                expected_count = _safe_int(item.get("materias_autoevaluables")) or _safe_int(item.get("materias_evaluables"))
                done = min(_safe_int(completed.get(code)), expected_count)
                pending = max(expected_count - done, 0)
                is_complete = expected_count > 0 and pending == 0
                if normalized_status == "pendientes" and is_complete:
                    continue
                if normalized_status == "realizadas" and not is_complete:
                    continue
                items.append(
                    {
                        **item,
                        "esperadas": expected_count,
                        "completadas": done,
                        "pendientes": pending,
                        "avance_percent": round((done / expected_count) * 100, 2) if expected_count else 0,
                        "estado": "REALIZADA" if is_complete else "PENDIENTE",
                    }
                )
        return {"periodo": periodo, "estado": normalized_status, "items": items, "total": len(items)}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar autoevaluacion estudiantil: {exc}") from exc


@router.get("/admin/estudiante-notas")
def get_teacher_evaluation_student_grades(
    periodo: str = Query(..., min_length=1),
    codigo_estud: int = Query(..., ge=1),
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1
                    de.codigo_estud,
                    LTRIM(RTRIM(de.Cedula_Est)) AS cedula,
                    LTRIM(RTRIM(de.Apellidos_nombre)) AS estudiante
                FROM dbo.DATOS_ESTUD de
                WHERE de.codigo_estud = ?
                """,
                codigo_estud,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontro el estudiante.")
            grades = _student_period_grades(cursor, periodo, codigo_estud)
            return {
                "periodo": periodo,
                "codigo_estud": _safe_int(row.codigo_estud),
                "cedula": _clean(row.cedula),
                "estudiante": _clean(row.estudiante),
                "items": grades,
                "total": len(grades),
            }
    except HTTPException:
        raise
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar notas del estudiante: {exc}") from exc


@router.get("/admin/docentes-calificados")
def get_teacher_evaluation_graded_teachers(
    periodo: str = Query(..., min_length=1),
    flow: str = Query(default="all"),
) -> dict[str, Any]:
    try:
        teachers, _, _, period_label = _teacher_evaluation_academic_maps(periodo)
        with get_evaluation_connection() as conn:
            cursor = conn.cursor()
            report_flow = _clean_text(flow or "all")
            if report_flow == "all":
                flow_label = "Resultado final 360"
                weight_rows = _evaluation_weights_for_period(cursor, periodo)
                cursor.execute(
                    """
                    SELECT
                        Cod_Docente_Evaluado,
                        COUNT(1) AS total_registros,
                        SUM(1) AS total_evaluaciones,
                        SUM(0) AS total_respuestas,
                        AVG(TRY_CONVERT(float, Promedio_Estudiantes)) AS Promedio_Estudiantes,
                        AVG(TRY_CONVERT(float, Promedio_Par_Docente)) AS Promedio_Par_Docente,
                        AVG(TRY_CONVERT(float, Promedio_Autoridad)) AS Promedio_Autoridad,
                        AVG(TRY_CONVERT(float, Promedio_Autoevaluacion)) AS Promedio_Autoevaluacion,
                        AVG(TRY_CONVERT(float, Puntaje_Final_360)) AS promedio_final
                    FROM eval360.vw_Resultado_360_Docente
                    WHERE Cod_Periodo = ?
                    GROUP BY Cod_Docente_Evaluado
                    ORDER BY Cod_Docente_Evaluado
                    """,
                    periodo,
                )
            else:
                weight_rows = []
                if report_flow not in _EVALUATION_FLOWS or report_flow == "auto_estudiante":
                    raise HTTPException(status_code=400, detail="Tipo de evaluacion no valido para docentes calificados.")
                instrument = _get_instrument(cursor, report_flow)
                flow_label = _flow_config(report_flow)["label"]
                cursor.execute(
                    """
                    SELECT
                        Cod_Docente_Evaluado,
                        Codigo_Tipo_Evaluacion,
                        MAX(Tipo_Evaluacion) AS Tipo_Evaluacion,
                        COUNT(1) AS total_registros,
                        SUM(ISNULL(Total_Evaluaciones, 0)) AS total_evaluaciones,
                        SUM(ISNULL(Total_Respuestas, 0)) AS total_respuestas,
                        AVG(TRY_CONVERT(float, Promedio_Tipo)) AS promedio_final
                    FROM eval360.vw_Resultado_Tipo_Docente
                    WHERE Cod_Periodo = ?
                      AND Codigo_Tipo_Evaluacion = ?
                    GROUP BY Cod_Docente_Evaluado, Codigo_Tipo_Evaluacion
                    ORDER BY Cod_Docente_Evaluado
                    """,
                    periodo,
                    _clean_text(instrument.get("tipo_evaluacion_codigo")),
                )
            items: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                code = _clean_text(row.Cod_Docente_Evaluado)
                teacher = teachers.get(code, {"codigo_doc": code, "docente": f"Docente {code}", "cedula_doc": ""})
                if report_flow == "all":
                    promedio_final = _weighted_teacher_result_score(
                        {
                            "Promedio_Estudiantes": row.Promedio_Estudiantes,
                            "Promedio_Par_Docente": row.Promedio_Par_Docente,
                            "Promedio_Autoridad": row.Promedio_Autoridad,
                            "Promedio_Autoevaluacion": row.Promedio_Autoevaluacion,
                            "Puntaje_Final_360": row.promedio_final,
                        },
                        weight_rows,
                    )
                else:
                    promedio_final = _score_to_100(row.promedio_final)
                items.append(
                    {
                        **teacher,
                        "total_registros": _safe_int(row.total_registros),
                        "total_evaluaciones": _safe_int(row.total_evaluaciones),
                        "total_respuestas": _safe_int(row.total_respuestas),
                        "promedio_final": promedio_final,
                        "flow": report_flow,
                        "flow_label": _clean_text(getattr(row, "Tipo_Evaluacion", "")) or flow_label,
                    }
                )
            return {
                "periodo": periodo,
                "periodo_detalle": period_label,
                "flow": report_flow,
                "flow_label": flow_label,
                "items": items,
                "total": len(items),
            }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar docentes calificados: {exc}") from exc


@router.get("/admin/reporte-docentes.pdf")
def download_teacher_evaluation_grades_pdf(
    periodo: str = Query(..., min_length=1),
    codigo_docente: str = Query(default=""),
    flow: str = Query(default="all"),
    document_type: str = Query(default="certificado"),
) -> StreamingResponse:
    try:
        teacher_code = _clean_text(codigo_docente)
        report = _fetch_teacher_grade_report(periodo, teacher_code or None, flow=flow, document_type=document_type)
        pdf_bytes = _build_teacher_grade_pdf(report)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF de calificaciones docentes: {exc}") from exc

    teacher_suffix = f"_{_safe_filename(teacher_code)}" if teacher_code else "_todos"
    filename = (
        f"{_safe_filename(document_type or 'certificado')}_evaluacion_docente_"
        f"{_safe_filename(flow or 'all')}_{_safe_int(periodo)}{teacher_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.get("/identity/{cedula}")
def get_teacher_evaluation_identity(cedula: str) -> dict[str, Any]:
    """Resolve una cedula contra estudiantes y docentes para abrir el flujo correcto."""
    cleaned = _clean_text(cedula)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Ingrese un numero de cedula valido.")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            student = _fetch_student(cursor, cleaned)
            teacher = _fetch_teacher(cursor, cleaned)
            authority = _fetch_authority(cursor, cleaned)

            if not student and not teacher and not authority:
                raise HTTPException(
                    status_code=404,
                    detail="No se encontro informacion activa para esa cedula en estudiantes, docentes ni usuarios academicos.",
                )

            student_courses: list[dict[str, Any]] = []
            auto_student_courses: list[dict[str, Any]] = []
            auto_courses: list[dict[str, Any]] = []
            peer_courses: list[dict[str, Any]] = []
            authority_courses: list[dict[str, Any]] = []
            warnings: list[str] = []

            if student:
                cursor.execute(_courses_query(), student["codigo_estud"])
                student_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                student_courses = _deduplicate_subject_courses(student_courses)
                student_courses = _apply_evaluation_status(student["codigo_estud"], student_courses, "student")
                cursor.execute(_auto_student_courses_query(), student["codigo_estud"])
                auto_student_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                auto_student_courses = _deduplicate_subject_courses(auto_student_courses)
                auto_student_courses = _apply_evaluation_status(
                    student["codigo_estud"], auto_student_courses, "auto_estudiante"
                )
                if not student_courses:
                    warnings.append("No existen materias con docente asignado para esta cedula.")
                if not auto_student_courses:
                    warnings.append("No existen materias con promedio final para autoevaluacion estudiantil.")

            if teacher:
                cursor.execute(_teacher_courses_query(), teacher["codigo_doc"])
                auto_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                cursor.execute(_peer_courses_query(), teacher["codigo_doc"])
                peer_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                auto_courses = _deduplicate_subject_courses(auto_courses)
                peer_courses = _deduplicate_subject_courses(peer_courses, include_teacher=True)
                auto_courses = _apply_evaluation_status(teacher["codigo_doc"], auto_courses, "auto_docente")
                peer_courses = _apply_evaluation_status(teacher["codigo_doc"], peer_courses, "par_docente")
                if not auto_courses and not peer_courses:
                    warnings.append("No existen materias asignadas ni docentes pares para esta cedula.")

            if authority:
                registered_authority: dict[str, Any] | None = None
                authority_assignments: list[dict[str, Any]] = []
                try:
                    with get_evaluation_connection() as evaluation_conn:
                        evaluation_cursor = evaluation_conn.cursor()
                        registered_authority = _fetch_registered_authority(evaluation_cursor, authority)
                        if registered_authority:
                            authority["id_autoridad_eval360"] = _safe_int(registered_authority.get("Id_Autoridad"))
                            authority["cargo"] = registered_authority.get("Cargo")
                            authority["cod_carrera_autoridad"] = registered_authority.get("Cod_Carrera")
                            authority_assignments = _fetch_authority_assignments(
                                evaluation_cursor,
                                _safe_int(registered_authority.get("Id_Autoridad")),
                            )
                except RuntimeError as exc:
                    raise HTTPException(status_code=500, detail=str(exc)) from exc

                coordcarrera = _clean_text(authority.get("coordcarrera"))
                if authority_assignments:
                    authority_courses = _authority_courses_from_assignments(cursor, authority_assignments)
                elif coordcarrera:
                    cursor.execute(_authority_courses_query(), coordcarrera)
                    authority_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                else:
                    cursor.execute(_authority_all_courses_query())
                    authority_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                authority_courses = _deduplicate_subject_courses(authority_courses, include_teacher=True)

                authority_evaluator_code = _authority_evaluator_code(authority)
                if authority_courses and authority_evaluator_code:
                    authority_courses = _apply_evaluation_status(
                        authority_evaluator_code, authority_courses, "academico_docente"
                    )
                if not authority_courses:
                    warnings.append("No existen docentes asignados para evaluacion academica en esta cedula.")

            roles: list[str] = []
            if student:
                roles.append("student")
            if teacher:
                roles.append("teacher")
            if authority:
                roles.append("authority")

            return {
                "cedula": cleaned,
                "roles": roles,
                "student": student,
                "teacher": teacher,
                "authority": authority,
                "student_courses": student_courses,
                "auto_student_courses": auto_student_courses,
                "auto_courses": auto_courses,
                "peer_courses": peer_courses,
                "authority_courses": authority_courses,
                "advertencias": warnings,
            }
    except HTTPException:
        raise
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar la evaluacion docente: {exc}") from exc

@router.get("/student/{cedula}")
def get_teacher_evaluation_student(cedula: str) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            student = _fetch_student(cursor, cedula)
            if not student:
                raise HTTPException(status_code=404, detail="No se encontro un estudiante activo con esa cedula.")

            cursor.execute(_courses_query(), student["codigo_estud"])
            courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
            courses = _deduplicate_subject_courses(courses)
            courses = _apply_evaluation_status(student["codigo_estud"], courses, "student")
            return {"student": student, "courses": courses, "total": len(courses)}
    except HTTPException:
        raise
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar la evaluacion docente: {exc}") from exc


@router.get("/teacher/{cedula}")
def get_teacher_evaluation_teacher(cedula: str) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            teacher = _fetch_teacher(cursor, cedula)
            if not teacher:
                raise HTTPException(status_code=404, detail="No se encontro un docente activo con esa cedula.")

            cursor.execute(_teacher_courses_query(), teacher["codigo_doc"])
            auto_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
            cursor.execute(_peer_courses_query(), teacher["codigo_doc"])
            peer_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]

            auto_courses = _deduplicate_subject_courses(auto_courses)
            peer_courses = _deduplicate_subject_courses(peer_courses, include_teacher=True)
            auto_courses = _apply_evaluation_status(teacher["codigo_doc"], auto_courses, "auto_docente")
            peer_courses = _apply_evaluation_status(teacher["codigo_doc"], peer_courses, "par_docente")
            return {
                "teacher": teacher,
                "auto_courses": auto_courses,
                "peer_courses": peer_courses,
                "total_auto": len(auto_courses),
                "total_peer": len(peer_courses),
            }
    except HTTPException:
        raise
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo consultar la evaluacion docente: {exc}") from exc


@router.post("/evaluate")
def save_teacher_evaluation(payload: TeacherEvaluationSubmitPayload) -> dict[str, Any]:
    flow = payload.flow or "student"
    try:
        with get_connection() as academic_conn:
            academic_cursor = academic_conn.cursor()
            student = _fetch_student(academic_cursor, payload.cedula)
            if not student:
                raise HTTPException(status_code=404, detail="No se encontro un estudiante activo con esa cedula.")
            course = _find_student_course(academic_cursor, student["codigo_estud"], payload)

        with get_evaluation_connection() as evaluation_conn:
            evaluation_cursor = evaluation_conn.cursor()
            instrument = _get_instrument(evaluation_cursor, flow)
            _validate_questions(evaluation_cursor, payload.answers, instrument_id=_safe_int(instrument["Id_Instrumento"]))

            origin_key = _origin_key(student["codigo_estud"], course, flow)
            existing = _evaluation_count(
                evaluation_cursor,
                flow=flow,
                instrument=instrument,
                evaluator_code=student["codigo_estud"],
                course=course,
                origin_key=origin_key,
            )
            if existing > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Ya registraste la evaluacion de esta materia en este periodo. La evaluacion quedo cerrada.",
                )

            campaign_id = _get_or_create_campaign(
                evaluation_cursor,
                codigo_periodo=payload.codigo_periodo,
                detalle_periodo=str(course.get("detalle_periodo") or ""),
                flow=flow,
            )
            result = _save_application(
                evaluation_cursor,
                flow=flow,
                instrument=instrument,
                campaign_id=campaign_id,
                evaluator_code=student["codigo_estud"],
                evaluated_student_code=student["codigo_estud"] if flow == "auto_estudiante" else None,
                course=course,
                answers=payload.answers,
                origin_table="INTECBDD.dbo.CARRERAXESTUD",
                origin_evaluator_table="INTECBDD.dbo.DATOS_ESTUD",
                origin_evaluated_table=(
                    "INTECBDD.dbo.DATOS_ESTUD" if flow == "auto_estudiante" else "INTECBDD.dbo.DATOSDOCENTE"
                ),
            )
            evaluation_conn.commit()
            return {
                **result,
                "student": student,
                "message": (
                    "Autoevaluacion estudiantil registrada correctamente."
                    if flow == "auto_estudiante"
                    else "Evaluacion docente registrada correctamente."
                ),
            }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la evaluacion docente: {exc}") from exc


@router.post("/teacher/evaluate")
def save_teacher_role_evaluation(payload: TeacherRoleEvaluationSubmitPayload) -> dict[str, Any]:
    flow = payload.flow
    try:
        with get_connection() as academic_conn:
            academic_cursor = academic_conn.cursor()
            authority: dict[str, Any] | None = None
            teacher: dict[str, Any] | None = None
            registered_authority: dict[str, Any] | None = None
            authority_assignments: list[dict[str, Any]] = []
            if flow == "academico_docente":
                authority = _fetch_authority(academic_cursor, payload.cedula)
                if not authority:
                    raise HTTPException(status_code=404, detail="No se encontro un usuario academico activo con esa cedula.")
            else:
                teacher = _fetch_teacher(academic_cursor, payload.cedula)
                if not teacher:
                    raise HTTPException(status_code=404, detail="No se encontro un docente activo con esa cedula.")
                course = _find_teacher_course(academic_cursor, teacher["codigo_doc"], payload)
                evaluator_code = teacher["codigo_doc"]
                origin_evaluator_table = "INTECBDD.dbo.DATOSDOCENTE"

            with get_evaluation_connection() as evaluation_conn:
                evaluation_cursor = evaluation_conn.cursor()

                if flow == "academico_docente":
                    if authority is None:
                        raise HTTPException(status_code=404, detail="No se encontro un usuario academico activo con esa cedula.")
                    registered_authority = _ensure_authority_record(evaluation_cursor, authority)
                    authority["id_autoridad_eval360"] = _safe_int(registered_authority.get("Id_Autoridad"))
                    authority["cargo"] = registered_authority.get("Cargo")
                    authority["cod_carrera_autoridad"] = registered_authority.get("Cod_Carrera")
                    authority_assignments = _fetch_authority_assignments(
                        evaluation_cursor,
                        _safe_int(registered_authority.get("Id_Autoridad")),
                    )
                    course = _find_authority_course(academic_cursor, authority, payload, authority_assignments)
                    evaluator_code = _authority_evaluator_code(authority)
                    origin_evaluator_table = "INTECBDD.dbo.USUARIO_SIS"

                instrument = _get_instrument(evaluation_cursor, flow)
                _validate_questions(evaluation_cursor, payload.answers, instrument_id=_safe_int(instrument["Id_Instrumento"]))

                origin_key = _origin_key(evaluator_code, course, flow)
                existing = _evaluation_count(
                    evaluation_cursor,
                    flow=flow,
                    instrument=instrument,
                    evaluator_code=evaluator_code,
                    course=course,
                    origin_key=origin_key,
                )
                if existing > 0:
                    raise HTTPException(
                        status_code=409,
                        detail="Ya registraste esta evaluacion para la materia seleccionada en este periodo. La evaluacion quedo cerrada.",
                    )

                campaign_id = _get_or_create_campaign(
                    evaluation_cursor,
                    codigo_periodo=payload.codigo_periodo,
                    detalle_periodo=str(course.get("detalle_periodo") or ""),
                    flow=flow,
                )
                result = _save_application(
                    evaluation_cursor,
                    flow=flow,
                    instrument=instrument,
                    campaign_id=campaign_id,
                    evaluator_code=evaluator_code,
                    evaluated_student_code=None,
                    course=course,
                    answers=payload.answers,
                    origin_table=(
                        "INTECBDD.dbo.USUARIO_SIS" if flow == "academico_docente" else "INTECBDD.dbo.CARRERAXDOCENTE"
                    ),
                    origin_evaluator_table=origin_evaluator_table,
                    origin_evaluated_table="INTECBDD.dbo.DATOSDOCENTE",
                    authority_id=(
                        _safe_int(registered_authority.get("Id_Autoridad"))
                        if registered_authority
                        else None
                    ),
                )
                evaluation_conn.commit()
                response = {
                    **result,
                    "message": "Evaluacion docente registrada correctamente.",
                }
                if teacher:
                    response["teacher"] = teacher
                if authority:
                    response["authority"] = authority
                return response
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la evaluacion docente: {exc}") from exc
