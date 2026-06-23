from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import re
import uuid
from typing import Any

import pyodbc
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.db import get_connection, get_evaluation_connection

router = APIRouter(prefix="/api/evaluacion-docente", tags=["evaluacion-docente"])

_NUMBER_PATTERN = re.compile(r"\d+")
_QUESTION_PREFIX_PATTERN = re.compile(r"^(\s*(?:\d+|[ivxlcdm]+)\s*(?:[.)-]|\s+)\s*)+", re.IGNORECASE)
_SUBMITTED_STATES = ("ENVIADA", "FINALIZADA", "COMPLETADA", "REGISTRADA")

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
    "auto_docente": {
        "label": "Autoevaluación docente",
        "instrument_codes": ("AUTO_DOCENTE_360_V1", "AUTO_DOCENTE", "AUTOEVALUACION_DOCENTE"),
        "type_codes": ("AUTO_DOCENTE", "AUTOEVALUACION_DOCENTE", "AUTOEVALUACION"),
        "keywords": ("AUTO", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "PAR"),
        "evaluator_type": "DOCENTE_AUTO",
        "campaign_prefix": "AUTO_DOCENTE",
        "anonymous": False,
    },
    "par_docente": {
        "label": "Evaluación par docente",
        "instrument_codes": ("PAR_DOCENTE_360_V1", "PAR_DOCENTE", "EVAL_PAR_DOCENTE", "DOCENTE_PAR", "DOCENTE_DOCENTE"),
        "type_codes": ("PAR_DOCENTE", "DOCENTE_PAR", "DOCENTE_DOCENTE"),
        "keywords": ("PAR", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "AUTO"),
        "evaluator_type": "DOCENTE_PAR",
        "campaign_prefix": "PAR_DOCENTE",
        "anonymous": False,
    },
    "academico_docente": {
        "label": "Evaluación académica docente",
        "instrument_codes": (
            "ACA_DOCENTE_360_V1",
            "ACA_DOCENTE",
            "ACADEMICO_DOCENTE",
            "EVAL_ACADEMICA_DOCENTE",
            "AUTORIDAD_DOCENTE",
            "COORD_DOCENTE",
            "DIRECTIVO_DOCENTE",
        ),
        "type_codes": (
            "ACA_DOCENTE",
            "ACADEMICO_DOCENTE",
            "EVAL_ACADEMICA_DOCENTE",
            "AUTORIDAD_DOCENTE",
            "COORD_DOCENTE",
            "DIRECTIVO_DOCENTE",
        ),
        "keywords": ("ACADEMIC", "ACADEM", "DOCENTE"),
        "exclude_keywords": ("ESTUDIANTE", "AUTO", "PAR"),
        "evaluator_type": "ACADEMICO",
        "campaign_prefix": "ACA_DOCENTE",
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


def _stable_numeric_code(value: str) -> int:
    text = _clean_text(value) or "academico"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _flow_config(flow: str) -> dict[str, Any]:
    config = _EVALUATION_FLOWS.get(flow)
    if not config:
        raise HTTPException(status_code=400, detail="Tipo de evaluación no válido.")
    return config


def _fetch_student(cursor: pyodbc.Cursor, cedula: str) -> dict[str, Any] | None:
    cedula_digits = _digits(cedula)
    cursor.execute(
        """
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
        """
        SELECT TOP 1
            dd.codigo_doc,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.correo)) AS correo_personal,
            LTRIM(RTRIM(dd.correop)) AS correo_intec_datos,
            LTRIM(RTRIM(u.login)) AS usuario
        FROM dbo.DATOSDOCENTE dd
        LEFT JOIN dbo.USUARIOS u
            ON REPLACE(REPLACE(LTRIM(RTRIM(u.cedula)), '-', ''), ' ', '') =
               REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '')
        WHERE REPLACE(REPLACE(LTRIM(RTRIM(dd.cedula_doc)), '-', ''), ' ', '') = ?
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


def _course_from_row(data: dict[str, Any]) -> dict[str, Any]:
    codigo_periodo = _safe_int(data.get("codigo_periodo"))
    codigo_materia = _safe_int(data.get("codigo_materia"))
    codigo_docente_eval = _safe_int(data.get("codigo_docente_eval"))
    paralelo = str(data.get("paralelo") or "").strip()
    respuestas = _safe_int(data.get("respuestas_registradas"))
    return {
        "key": f"{codigo_periodo}-{codigo_materia}-{codigo_docente_eval}-{paralelo}",
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
            cxd.codigo_doc AS codigo_docente_eval,
            LTRIM(RTRIM(dd.apellidos_nombre)) AS docente,
            LTRIM(RTRIM(dd.cedula_doc)) AS cedula_doc,
            CAST(cxd.Cod_Jornada AS varchar(20)) AS cod_jornada,
            LTRIM(RTRIM(CAST(cm.Jornada AS varchar(50)))) AS jornada,
            CAST(0 AS int) AS respuestas_registradas
        FROM dbo.CARRERAXESTUD ce
        INNER JOIN dbo.PERIODO per ON ce.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON ce.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON ce.cod_anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.CARRERAXDOCENTE cxd ON cxd.codigo_materia = ce.codigo_materia
            AND cxd.codigo_periodo = ce.codigo_periodo
            AND cxd.cod_Anio_Basica = ce.cod_anio_Basica
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = cxd.codigo_doc
        LEFT JOIN dbo.CABECERA_MATRICULA cm ON cm.codigo_estud = ce.codigo_estud
            AND cm.cod_anio_Basica = ce.cod_anio_Basica
            AND cm.codigo_periodo = ce.codigo_periodo
        WHERE ce.codigo_estud = ?
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
        WHERE cxd.codigo_doc = ?
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
            AND peer.codigo_periodo = mine.codigo_periodo
            AND LTRIM(RTRIM(CAST(peer.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(mine.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            AND peer.codigo_doc <> mine.codigo_doc
        INNER JOIN dbo.PERIODO per ON peer.codigo_periodo = per.cod_periodo
        INNER JOIN dbo.PENSUM pen ON peer.codigo_materia = pen.codigo_materia
        INNER JOIN dbo.CARRERAS car ON peer.cod_Anio_Basica = car.Cod_AnioBasica
        INNER JOIN dbo.DATOSDOCENTE dd ON dd.codigo_doc = peer.codigo_doc
        WHERE mine.codigo_doc = ?
        {extra_where}
        ORDER BY per.Orden DESC, peer.codigo_periodo DESC, LTRIM(RTRIM(car.Nombre_Basica)), LTRIM(RTRIM(pen.Nomb_Materia)), LTRIM(RTRIM(dd.apellidos_nombre))
    """


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
    category = _fallback_question_category(data, id_dimension, tipo_preg)
    return {
        "id_pregunta": _safe_int(data.get("Id_Pregunta")),
        "id_dimension": id_dimension,
        "no_pregunta": _safe_int(data.get("NoPregunta"), _safe_int(data.get("Orden"), 0)),
        "tipo_preg": tipo_preg,
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
    return "|".join(
        [
            flow,
            str(actor_code),
            str(course.get("codigo_periodo") or ""),
            str(course.get("codigo_materia") or ""),
            str(course.get("codigo_docente_eval") or ""),
            str(course.get("paralelo") or ""),
        ]
    )


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
    cursor.execute(
        f"""
        SELECT COUNT(1)
        FROM eval360.Aplicacion
        WHERE Id_Tipo_Evaluacion = ?
          AND Tipo_Evaluador = ?
          AND Cod_Periodo = ?
          AND Cod_Materia = ?
          AND Cod_Docente_Evaluado = ?
          AND ISNULL(LTRIM(RTRIM(Paralelo)), '') = ?
          AND Estado IN ({states})
          AND (Cod_Evaluador = ? OR Origen_Evaluador_Clave = ? OR Origen_Clave = ?)
        """,
        _safe_int(instrument.get("Id_Tipo_Evaluacion")),
        config["evaluator_type"],
        str(_safe_int(course.get("codigo_periodo"))),
        str(_safe_int(course.get("codigo_materia"))),
        str(_safe_int(course.get("codigo_docente_eval"))),
        str(course.get("paralelo") or ""),
        *_SUBMITTED_STATES,
        str(evaluator_code),
        str(evaluator_code),
        origin_key or "",
    )
    row = cursor.fetchone()
    return _safe_int(row[0] if row else 0)


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
          AND Estado = 'ACTIVO'
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
        VALUES (?, ?, ?, ?, ?, 'ACTIVO', ?)
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
    question_ids = sorted({answer.id_pregunta for answer in answers})
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
    cursor.execute(
        _courses_query(
            """
            AND ce.codigo_periodo = ?
            AND ce.codigo_materia = ?
            AND cxd.codigo_doc = ?
            AND LTRIM(RTRIM(CAST(ce.paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(? AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            """
        ),
        student_code,
        payload.codigo_periodo,
        payload.codigo_materia,
        payload.codigo_docente_eval,
        payload.paralelo,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="La materia seleccionada no está asignada al estudiante con ese docente.",
        )
    return _course_from_row(_row_dict(cursor, row))


def _find_teacher_course(
    cursor: pyodbc.Cursor,
    teacher_code: int,
    payload: TeacherRoleEvaluationSubmitPayload,
) -> dict[str, Any]:
    query = _teacher_courses_query if payload.flow == "auto_docente" else _peer_courses_query
    cursor.execute(
        query(
            """
            AND cxd.codigo_periodo = ?
            AND cxd.codigo_materia = ?
            AND LTRIM(RTRIM(CAST(cxd.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(? AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            """
        )
        if payload.flow == "auto_docente"
        else query(
            """
            AND peer.codigo_periodo = ?
            AND peer.codigo_materia = ?
            AND peer.codigo_doc = ?
            AND LTRIM(RTRIM(CAST(peer.Paralelo AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS =
                LTRIM(RTRIM(CAST(? AS varchar(20)))) COLLATE SQL_Latin1_General_CP1_CI_AS
            """
        ),
        teacher_code,
        payload.codigo_periodo,
        payload.codigo_materia,
        *(()
          if payload.flow == "auto_docente"
          else (payload.codigo_docente_eval,)),
        payload.paralelo,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró la materia seleccionada para el docente.")
    course = _course_from_row(_row_dict(cursor, row))
    if payload.flow == "auto_docente":
        course["codigo_docente_eval"] = teacher_code
    return course


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
             Origen_Evaluador_Tabla, Origen_Evaluador_Clave,
             Origen_Evaluado_Tabla, Origen_Evaluado_Clave)
        OUTPUT INSERTED.Id_Aplicacion
        VALUES
            (NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'ENVIADA',
             NULL, ?, ?, ?, ?, ?, ?, ?)
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



@router.get("/identity/{cedula}")
def get_teacher_evaluation_identity(cedula: str) -> dict[str, Any]:
    """Resolve una cedula contra estudiantes y docentes para abrir el flujo correcto."""
    cleaned = _digits(cedula)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Ingrese un numero de cedula valido.")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            student = _fetch_student(cursor, cleaned)
            teacher = _fetch_teacher(cursor, cleaned)

            if not student and not teacher:
                raise HTTPException(
                    status_code=404,
                    detail="No se encontro informacion para esa cedula en estudiantes ni docentes.",
                )

            student_courses: list[dict[str, Any]] = []
            auto_courses: list[dict[str, Any]] = []
            peer_courses: list[dict[str, Any]] = []
            warnings: list[str] = []

            if student:
                cursor.execute(_courses_query(), student["codigo_estud"])
                student_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                student_courses = _apply_evaluation_status(student["codigo_estud"], student_courses, "student")
                if not student_courses:
                    warnings.append("No existen materias con docente asignado para esta cedula.")

            if teacher:
                cursor.execute(_teacher_courses_query(), teacher["codigo_doc"])
                auto_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                cursor.execute(_peer_courses_query(), teacher["codigo_doc"])
                peer_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
                auto_courses = _apply_evaluation_status(teacher["codigo_doc"], auto_courses, "auto_docente")
                peer_courses = _apply_evaluation_status(teacher["codigo_doc"], peer_courses, "par_docente")
                if not auto_courses and not peer_courses:
                    warnings.append("No existen materias asignadas ni docentes pares para esta cedula.")

            roles: list[str] = []
            if student:
                roles.append("student")
            if teacher:
                roles.append("teacher")

            return {
                "cedula": cleaned,
                "roles": roles,
                "student": student,
                "teacher": teacher,
                "student_courses": student_courses,
                "auto_courses": auto_courses,
                "peer_courses": peer_courses,
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
                raise HTTPException(status_code=404, detail="No se encontro un estudiante con esa cedula.")

            cursor.execute(_courses_query(), student["codigo_estud"])
            courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
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
                raise HTTPException(status_code=404, detail="No se encontro un docente con esa cedula.")

            cursor.execute(_teacher_courses_query(), teacher["codigo_doc"])
            auto_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]
            cursor.execute(_peer_courses_query(), teacher["codigo_doc"])
            peer_courses = [_course_from_row(_row_dict(cursor, row)) for row in cursor.fetchall()]

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
    flow = "student"
    try:
        with get_connection() as academic_conn:
            academic_cursor = academic_conn.cursor()
            student = _fetch_student(academic_cursor, payload.cedula)
            if not student:
                raise HTTPException(status_code=404, detail="No se encontro un estudiante con esa cedula.")
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
                    detail="Ya registraste la evaluacion de esta materia con este docente. La evaluacion quedo cerrada.",
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
                evaluated_student_code=None,
                course=course,
                answers=payload.answers,
                origin_table="INTECBDD.dbo.CARRERAXESTUD",
                origin_evaluator_table="INTECBDD.dbo.DATOS_ESTUD",
                origin_evaluated_table="INTECBDD.dbo.DATOSDOCENTE",
            )
            evaluation_conn.commit()
            return {
                **result,
                "student": student,
                "message": "Evaluacion docente registrada correctamente.",
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
            teacher = _fetch_teacher(academic_cursor, payload.cedula)
            if not teacher:
                raise HTTPException(status_code=404, detail="No se encontro un docente con esa cedula.")
            course = _find_teacher_course(academic_cursor, teacher["codigo_doc"], payload)

        with get_evaluation_connection() as evaluation_conn:
            evaluation_cursor = evaluation_conn.cursor()
            instrument = _get_instrument(evaluation_cursor, flow)
            _validate_questions(evaluation_cursor, payload.answers, instrument_id=_safe_int(instrument["Id_Instrumento"]))

            origin_key = _origin_key(teacher["codigo_doc"], course, flow)
            existing = _evaluation_count(
                evaluation_cursor,
                flow=flow,
                instrument=instrument,
                evaluator_code=teacher["codigo_doc"],
                course=course,
                origin_key=origin_key,
            )
            if existing > 0:
                raise HTTPException(
                    status_code=409,
                    detail="Ya registraste esta evaluacion para la materia seleccionada. La evaluacion quedo cerrada.",
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
                evaluator_code=teacher["codigo_doc"],
                evaluated_student_code=None,
                course=course,
                answers=payload.answers,
                origin_table="INTECBDD.dbo.CARRERAXDOCENTE",
                origin_evaluator_table="INTECBDD.dbo.DATOSDOCENTE",
                origin_evaluated_table="INTECBDD.dbo.DATOSDOCENTE",
            )
            evaluation_conn.commit()
            return {
                **result,
                "teacher": teacher,
                "message": "Evaluacion docente registrada correctamente.",
            }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (pyodbc.Error, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la evaluacion docente: {exc}") from exc
