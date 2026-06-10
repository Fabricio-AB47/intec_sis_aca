from datetime import date, datetime
from decimal import Decimal
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import pyodbc

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/students/matricula-acad", tags=["matricula-acad"])

_ACADEMIC_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")
_VALID_TIPO_MATRICULA = {"R", "H", "E"}
_VALID_TEACHER_STATE_CODES = {"A", "P"}
_PASSING_FINAL_GRADE = 7.0


class AcademicEnrollmentPayload(BaseModel):
    codigo_estud: int
    cod_anio_basica: int
    codigo_periodo: int
    materia_codes: list[int] = Field(default_factory=list)
    paralelo: str = "A"
    num_grupo: int = 1
    tipo_matricula: str = "R"
    control_matricula: int = 1
    cod_jornada: int = 1
    inscrip_valor: float = 0
    matri_valor: float = 0
    valor: float = 0
    fecha_pago: str | None = None
    remove_unselected: bool = False


class AcademicParallelBalancePayload(BaseModel):
    cod_anio_basica: int
    codigo_periodo: int


class AcademicTeacherEnrollmentPayload(BaseModel):
    codigo_doc: int
    cod_anio_basica: int
    codigo_materia: int
    codigo_periodo: int
    paralelo: str = "A"
    cod_jornada: int = 1
    estado_moodle_doc: int = 0


class AcademicTeacherUniqueEnrollmentPayload(BaseModel):
    codigo_doc: int
    cod_materia: str = Field(min_length=1, max_length=100)
    codigo_periodo: int
    paralelo: str = "A"
    semestre: int | None = None
    cod_jornada: int = 1
    estado_moodle_doc: int = 0


class AcademicTeacherStatePayload(BaseModel):
    codigo_doc: int | None = None
    codigo_usuario: int | None = None
    estado_codigo: str = Field(min_length=1, max_length=10)


class AcademicBulkEnrollmentPayload(BaseModel):
    cod_anio_basica: int
    source_codigo_periodo: int
    target_codigo_periodo: int
    materia_codes: list[int] = Field(default_factory=list)
    student_codes: list[int] = Field(default_factory=list)
    paralelo_filter: str | None = None
    paralelo_default: str = "A"
    num_grupo_default: int = 1
    tipo_matricula: str = "R"
    control_matricula: int = 1
    cod_jornada: int = 1
    inscrip_valor: float = 0
    matri_valor: float = 0
    valor: float = 0
    fecha_pago: str | None = None
    remove_unselected: bool = False


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _clean(value)


def _int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_passing_final_grade(value: Any) -> bool:
    grade = _number_value(value)
    return grade is not None and grade >= _PASSING_FINAL_GRADE


def _normalize_document(value: Any) -> str:
    digits = re.sub(r"\D+", "", _clean(value))
    if not digits:
        return ""
    if len(digits) == 13 and digits.endswith("001"):
        digits = digits[:10]
    elif len(digits) > 10:
        digits = digits[-10:]
    return digits.zfill(10)


def _natural_sort_key(value: str) -> list[tuple[int, Any]]:
    parts = re.split(r"(\d+)", _clean(value).upper())
    return [(0, int(part)) if part.isdigit() else (1, part) for part in parts if part]


def _student_item(row: Any) -> dict[str, Any]:
    correo_personal = _clean(getattr(row, "correo", "")) or _clean(getattr(row, "CorreoPersonal", ""))
    correo_intec = (
        _clean(getattr(row, "correo_intec", ""))
        or _clean(getattr(row, "CorreoIntec", ""))
        or _clean(getattr(row, "correointec", ""))
    )
    return {
        "codigo_estud": str(row.codigo_estud),
        "cedula": _clean(row.Cedula_Est),
        "cedula_normalizada": _normalize_document(row.Cedula_Est),
        "nombre_estudiante": _clean(row.Apellidos_nombre),
        "estado_codigo": _clean(row.Estado),
        "correo_personal": correo_personal,
        "correo_intec": correo_intec,
        "carrera_actual": _clean(getattr(row, "Nombre_Basica", "")),
        "cod_anio_basica_actual": str(getattr(row, "cod_anio_Basica", "") or ""),
        "periodo_actual": str(getattr(row, "codigo_periodo", "") or ""),
        "detalle_periodo_actual": _clean(getattr(row, "Detalle_Periodo", "")),
        "materias_actuales": int(getattr(row, "materias_actuales", 0) or 0),
    }


def _career_item(row: Any) -> dict[str, Any]:
    return {
        "cod_anio_basica": str(row.Cod_AnioBasica),
        "nombre_basica": _clean(row.Nombre_Basica),
        "estado": _clean(row.Estado),
        "abrevia": _clean(row.Abrevia),
        "tipo_escuela": _clean(row.tp_escuela),
        "total_matriculados": int(getattr(row, "total_matriculados", 0) or 0),
    }


def _period_item(row: Any) -> dict[str, Any]:
    return {
        "codigo_periodo": str(row.cod_periodo),
        "detalle_periodo": _clean(row.Detalle_Periodo),
        "estado": _clean(row.Estado),
        "periodo": _clean(row.Periodo),
        "anio": _int_value(row.anio),
        "fecha_inicio": _date_text(row.fechain),
        "fecha_fin": _date_text(row.fechafin),
        "tipo_matricula": _clean(row.TipoMatricula),
        "total_matriculados": int(getattr(row, "total_matriculados", 0) or 0),
    }


def _jornada_item(row: Any) -> dict[str, Any]:
    return {
        "value": _clean(row.option_value),
        "label": _clean(row.option_label),
        "modalidad": _clean(getattr(row, "modalidad", "")),
    }


def _subject_item(row: Any) -> dict[str, Any]:
    return {
        "codigo_materia": str(row.codigo_materia),
        "cod_materia": _clean(row.cod_materia),
        "nombre_materia": _clean(row.Nomb_Materia),
        "semestre": _int_value(row.Semestre),
        "creditos": _number_value(row.Creditos),
        "orden": _int_value(row.Orden),
        "num_malla": _int_value(row.NumMalla),
        "horas": _int_value(row.Horas),
        "tipo_materia": _clean(row.tipomateria),
    }


def _teacher_item(row: Any) -> dict[str, Any]:
    codigo_doc = getattr(row, "codigo_doc", None)
    if codigo_doc is None:
        codigo_doc = getattr(row, "Codigo_Usuario", "")
    cedula = getattr(row, "cedula", None)
    if cedula is None:
        cedula = getattr(row, "cedula_doc", "")
    descripcion = getattr(row, "Descripcion", None)
    if descripcion is None:
        descripcion = getattr(row, "apellidos_nombre", "")
    return {
        "codigo_doc": str(codigo_doc or ""),
        "cedula": _clean(cedula),
        "login": _clean(getattr(row, "login", "")),
        "tipo_usuario": _clean(getattr(row, "tipo_usuario", "")),
        "estado": _clean(getattr(row, "Estado", "")),
        "descripcion": _clean(descripcion),
        "correo": _clean(getattr(row, "correo", "")),
        "correo_personal": _clean(getattr(row, "correop", "")),
        "telefono": _clean(getattr(row, "telefono", "")),
        "movil": _clean(getattr(row, "movil", "")),
        "perfil": _clean(getattr(row, "Perfil", "")),
        "tipo_docente": _clean(getattr(row, "TipoDocente", "")),
        "unidad_academica": _clean(getattr(row, "nombreUnidadAcademica", "")),
        "nivel_formacion": _clean(getattr(row, "nivelFormacion", "")),
        "tercer_nivel": _clean(getattr(row, "tercernivel", "")),
        "cuarto_nivel": _clean(getattr(row, "cuartonivel", "")),
        "total_matriculas_docente": _int_value(getattr(row, "total_matriculas_docente", None)) or 0,
        "total_carreras_docente": _int_value(getattr(row, "total_carreras_docente", None)) or 0,
        "total_materias_docente": _int_value(getattr(row, "total_materias_docente", None)) or 0,
        "ultimo_periodo_docente": _int_value(getattr(row, "ultimo_periodo_docente", None)),
        "usuario_validado": bool(_int_value(getattr(row, "usuario_validado", None))),
    }


def _teacher_enrollment_item(row: Any) -> dict[str, Any]:
    return {
        "codigo_doc": str(row.codigo_doc),
        "cod_anio_basica": str(row.cod_Anio_Basica),
        "codigo_materia": str(row.codigo_materia),
        "paralelo": _clean(row.Paralelo),
        "codigo_periodo": str(row.codigo_periodo),
        "cod_jornada": _int_value(row.Cod_Jornada),
        "estado_moodle_doc": _int_value(row.estadoMoodleDoc),
        "cedula": _clean(getattr(row, "cedula", "")),
        "login": _clean(getattr(row, "login", "")),
        "descripcion": _clean(getattr(row, "Descripcion", "")),
        "tipo_usuario": _clean(getattr(row, "tipo_usuario", "")),
        "estado": _clean(getattr(row, "Estado", "")),
        "correo": _clean(getattr(row, "correo", "")),
        "correo_personal": _clean(getattr(row, "correop", "")),
        "telefono": _clean(getattr(row, "telefono", "")),
        "movil": _clean(getattr(row, "movil", "")),
        "perfil": _clean(getattr(row, "Perfil", "")),
        "tipo_docente": _clean(getattr(row, "TipoDocente", "")),
        "unidad_academica": _clean(getattr(row, "nombreUnidadAcademica", "")),
        "nivel_formacion": _clean(getattr(row, "nivelFormacion", "")),
        "nombre_materia": _clean(getattr(row, "Nomb_Materia", "")),
        "nombre_carrera": _clean(getattr(row, "Nombre_Basica", "")),
        "detalle_periodo": _clean(getattr(row, "Detalle_Periodo", "")),
    }


def _estado_docente_item(row: Any) -> dict[str, Any]:
    estado_codigo = _clean(getattr(row, "Estado", ""))
    estado_nombre = _clean(getattr(row, "estado_nombre", "")) or estado_codigo or "Sin estado"
    codigo_doc = _clean(getattr(row, "codigo_doc", "")) or _clean(getattr(row, "Codigo_Usuario", ""))
    cedula = _clean(getattr(row, "cedula_doc", "")) or _clean(getattr(row, "cedula_usuario", ""))
    descripcion = (
        _clean(getattr(row, "apellidos_nombre", ""))
        or _clean(getattr(row, "login", ""))
        or "Sin ficha docente"
    )
    return {
        "codigo_doc": codigo_doc,
        "codigo_usuario": str(getattr(row, "Codigo_Usuario", "") or ""),
        "cedula": cedula,
        "login": _clean(getattr(row, "login", "")),
        "tipo_usuario": _clean(getattr(row, "tipo_usuario", "")),
        "estado": estado_codigo,
        "estado_nombre": estado_nombre,
        "descripcion": descripcion,
        "correo": _clean(getattr(row, "correo", "")),
        "correo_personal": _clean(getattr(row, "correop", "")),
        "telefono": _clean(getattr(row, "telefono", "")),
        "movil": _clean(getattr(row, "movil", "")),
        "perfil": _clean(getattr(row, "Perfil", "")),
        "tipo_docente": _clean(getattr(row, "TipoDocente", "")),
        "unidad_academica": _clean(getattr(row, "nombreUnidadAcademica", "")),
        "nivel_formacion": _clean(getattr(row, "nivelFormacion", "")),
        "tercer_nivel": _clean(getattr(row, "tercernivel", "")),
        "cuarto_nivel": _clean(getattr(row, "cuartonivel", "")),
        "fecha_ingreso_ies": _date_text(getattr(row, "fechaIngresoIES", "")),
        "relacion_laboral": _clean(getattr(row, "relacionLaboralIESId", "")),
        "tiempo_dedicacion": _clean(getattr(row, "tiempoDedicacionId", "")),
        "usuario_validado": bool(_int_value(getattr(row, "usuario_validado", None))),
        "total_matriculas_docente": _int_value(getattr(row, "total_matriculas_docente", None)) or 0,
        "total_carreras_docente": _int_value(getattr(row, "total_carreras_docente", None)) or 0,
        "total_materias_docente": _int_value(getattr(row, "total_materias_docente", None)) or 0,
        "ultimo_periodo_docente": _int_value(getattr(row, "ultimo_periodo_docente", None)),
    }


def _fetch_estado_docente_by_code(cursor: pyodbc.Cursor, codigo_doc: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
            TRY_CONVERT(varchar(50), u.Codigo_Usuario) AS Codigo_Usuario,
            TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula_doc,
            TRY_CONVERT(nvarchar(100), u.cedula) AS cedula_usuario,
            TRY_CONVERT(nvarchar(255), u.login) AS login,
            COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), u.tipo_usuario), N''), N'DOCENTE') AS tipo_usuario,
            TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
            TRY_CONVERT(nvarchar(255), est.ESTADO) AS estado_nombre,
            TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) AS apellidos_nombre,
            TRY_CONVERT(nvarchar(255), d.correo) AS correo,
            TRY_CONVERT(nvarchar(255), d.correop) AS correop,
            TRY_CONVERT(nvarchar(100), d.telefono) AS telefono,
            TRY_CONVERT(nvarchar(100), d.movil) AS movil,
            TRY_CONVERT(nvarchar(4000), d.Perfil) AS Perfil,
            TRY_CONVERT(nvarchar(255), d.TipoDocente) AS TipoDocente,
            TRY_CONVERT(nvarchar(4000), d.nombreUnidadAcademica) AS nombreUnidadAcademica,
            TRY_CONVERT(nvarchar(255), d.nivelFormacion) AS nivelFormacion,
            TRY_CONVERT(nvarchar(4000), d.tercernivel) AS tercernivel,
            TRY_CONVERT(nvarchar(4000), d.cuartonivel) AS cuartonivel,
            d.fechaIngresoIES,
            TRY_CONVERT(nvarchar(100), d.relacionLaboralIESId) AS relacionLaboralIESId,
            TRY_CONVERT(nvarchar(100), d.tiempoDedicacionId) AS tiempoDedicacionId,
            CASE WHEN u.Codigo_Usuario IS NULL THEN 0 ELSE 1 END AS usuario_validado,
            stats.total_matriculas_docente,
            stats.total_carreras_docente,
            stats.total_materias_docente,
            stats.ultimo_periodo_docente
        FROM dbo.USUARIOS u
        FULL OUTER JOIN dbo.DATOSDOCENTE d
          ON (
                TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
             OR LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))) =
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.cedula_doc)))
          )
        LEFT JOIN dbo.ESTADO est
          ON UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), est.IDESTADO)))) =
             UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), u.Estado))))
        OUTER APPLY (
            SELECT
                COUNT(*) AS total_matriculas_docente,
                COUNT(DISTINCT TRY_CONVERT(int, cxd.cod_Anio_Basica)) AS total_carreras_docente,
                COUNT(DISTINCT TRY_CONVERT(int, cxd.codigo_materia)) AS total_materias_docente,
                MAX(TRY_CONVERT(int, cxd.codigo_periodo)) AS ultimo_periodo_docente
            FROM dbo.CARRERAXDOCENTE cxd
            WHERE TRY_CONVERT(int, cxd.codigo_doc) =
                  TRY_CONVERT(int, COALESCE(d.codigo_doc, u.Codigo_Usuario))
        ) stats
        WHERE TRY_CONVERT(int, u.Codigo_Usuario) = ?
          AND COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1
        """,
        codigo_doc,
    )
    row = cursor.fetchone()
    return _estado_docente_item(row) if row else None


def _current_subject_item(row: Any) -> dict[str, Any]:
    return {
        "codigo_materia": str(row.codigo_materia),
        "nombre_materia": _clean(row.Nomb_Materia),
        "semestre": _int_value(row.Semestre),
        "creditos": _number_value(row.Num_Creditos if row.Num_Creditos is not None else row.Creditos),
        "paralelo": _clean(row.paralelo),
        "num_grupo": _int_value(row.NumGrupo),
        "num_matricula": str(row.Num_Matricula),
        "fecha_matricula": _date_text(row.Fecha_Matricula),
        "tipo_matricula": _clean(row.TipoMatricula),
        "control_matricula": _int_value(row.ControlMatricula),
        "tiene_notas": bool(row.tiene_notas),
    }


def _cabecera_item(row: Any) -> dict[str, Any]:
    return {
        "codigo_estud": str(row.codigo_estud),
        "cod_anio_basica": str(row.cod_anio_Basica),
        "codigo_periodo": str(row.codigo_periodo),
        "num_matricula": str(row.Num_Matricula or ""),
        "fecha_pago": _date_text(row.fecha_pago),
        "valor": _number_value(row.valor),
        "inscrip_valor": _number_value(row.InscripValor),
        "matri_valor": _number_value(row.MatriValor),
        "jornada": _clean(row.Jornada),
        "cod_jornada": _int_value(getattr(row, "codjornada", None)),
        "control_matricula": _int_value(row.ControlMatricula),
        "carrera": _clean(row.Nombre_Basica),
        "periodo": _clean(row.Detalle_Periodo),
    }


def _cohort_base_row(row: Any) -> dict[str, Any]:
    nota = _number_value(getattr(row, "PromedioFinal", None))
    return {
        "codigo_estud": str(row.codigo_estud),
        "cedula": _clean(row.Cedula_Est),
        "cedula_normalizada": _normalize_document(row.Cedula_Est),
        "nombre_estudiante": _clean(row.Apellidos_nombre),
        "estado_codigo": _clean(row.Estado),
        "correo_personal": _clean(row.correo),
        "correo_intec": _clean(row.correointec),
        "cod_anio_basica": str(row.cod_anio_Basica),
        "nombre_carrera": _clean(row.Nombre_Basica),
        "codigo_periodo": str(row.codigo_periodo),
        "detalle_periodo": _clean(row.Detalle_Periodo),
        "num_matricula": str(row.Num_Matricula or ""),
        "paralelo": _clean(row.paralelo),
        "num_grupo": _int_value(row.NumGrupo),
        "codigo_materia": str(row.codigo_materia or ""),
        "nombre_materia": _clean(row.Nomb_Materia),
        "semestre": _int_value(row.Semestre),
        "nota": nota,
        "tipo_matricula": _clean(row.TipoMatricula),
    }


def _cohort_response(rows: list[Any]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    balance_by_parallel: dict[str, dict[str, Any]] = {}
    seen_parallel_students: set[tuple[str, str, str, str]] = set()
    for raw_row in rows:
        row = _cohort_base_row(raw_row)
        paralelo = row["paralelo"] or "SIN PARALELO"
        parallel_bucket = balance_by_parallel.setdefault(
            paralelo,
            {"paralelo": paralelo, "total_estudiantes": 0, "total_materias": 0},
        )
        parallel_student_key = (paralelo, row["codigo_estud"], row["cod_anio_basica"], row["codigo_periodo"])
        if parallel_student_key not in seen_parallel_students:
            seen_parallel_students.add(parallel_student_key)
            parallel_bucket["total_estudiantes"] += 1
        if row["codigo_materia"]:
            parallel_bucket["total_materias"] += 1

        key = (row["codigo_estud"], row["cod_anio_basica"], row["codigo_periodo"])
        item = grouped.setdefault(
            key,
            {
                "codigo_estud": row["codigo_estud"],
                "cedula": row["cedula"],
                "cedula_normalizada": row["cedula_normalizada"],
                "nombre_estudiante": row["nombre_estudiante"],
                "estado_codigo": row["estado_codigo"],
                "correo_personal": row["correo_personal"],
                "correo_intec": row["correo_intec"],
                "cod_anio_basica": row["cod_anio_basica"],
                "nombre_carrera": row["nombre_carrera"],
                "codigo_periodo": row["codigo_periodo"],
                "detalle_periodo": row["detalle_periodo"],
                "num_matricula": row["num_matricula"],
                "paralelo": "",
                "_paralelos": set(),
                "num_grupo": row["num_grupo"],
                "tipo_matricula": row["tipo_matricula"],
                "materias_actuales": 0,
                "nivel_actual": None,
                "aprobadas_nivel_actual": 0,
                "habilitado_promocion": False,
                "materias_reprobadas": [],
                "materias": [],
            },
        )
        item["_paralelos"].add(paralelo)
        if not item.get("tipo_matricula") and row["tipo_matricula"]:
            item["tipo_matricula"] = row["tipo_matricula"]
        if item.get("num_grupo") is None and row["num_grupo"] is not None:
            item["num_grupo"] = row["num_grupo"]
        if row["codigo_materia"]:
            item["materias_actuales"] += 1
            if row["semestre"] is not None:
                current_level = item["nivel_actual"]
                item["nivel_actual"] = max(current_level or row["semestre"], row["semestre"])
            item["materias"].append(
                {
                    "codigo_materia": row["codigo_materia"],
                    "nombre_materia": row["nombre_materia"],
                    "semestre": row["semestre"],
                    "nota": row["nota"],
                    "aprobada": _is_passing_final_grade(row["nota"]),
                }
            )
            if row["nota"] is not None and not _is_passing_final_grade(row["nota"]):
                item["materias_reprobadas"].append(
                    {
                        "codigo_materia": row["codigo_materia"],
                        "nombre_materia": row["nombre_materia"],
                        "semestre": row["semestre"],
                        "nota": row["nota"],
                    }
                )

    students: list[dict[str, Any]] = []
    for item in grouped.values():
        paralelos = sorted(str(value) for value in item.pop("_paralelos", set()) if value)
        item["paralelo"] = ", ".join(paralelos) if paralelos else "SIN PARALELO"
        current_level = item.get("nivel_actual")
        approved_current_subjects = {
            subject["codigo_materia"]
            for subject in item["materias"]
            if current_level is not None
            and subject.get("semestre") == current_level
            and subject.get("aprobada")
            and subject.get("codigo_materia")
        }
        current_level_subjects = {
            subject["codigo_materia"]
            for subject in item["materias"]
            if current_level is not None
            and subject.get("semestre") == current_level
            and subject.get("codigo_materia")
        }
        item["aprobadas_nivel_actual"] = len(approved_current_subjects)
        item["materias_nivel_actual"] = len(current_level_subjects)
        item["habilitado_promocion"] = bool(
            current_level is not None
            and len(current_level_subjects) > 0
            and len(approved_current_subjects) >= len(current_level_subjects)
        )
        students.append(item)

    students = sorted(
        students,
        key=lambda item: (
            str(item["nombre_carrera"]),
            str(item["paralelo"]),
            str(item["nombre_estudiante"]),
        ),
    )
    balance_by_career: dict[str, dict[str, Any]] = {}
    balance_by_level: dict[str, dict[str, Any]] = {}
    for item in students:
        career_key = str(item["nombre_carrera"] or "SIN CARRERA")
        career_bucket = balance_by_career.setdefault(
            career_key,
            {"cod_anio_basica": item["cod_anio_basica"], "nombre_carrera": career_key, "total_estudiantes": 0},
        )
        career_bucket["total_estudiantes"] += 1

        level_key = str(item["nivel_actual"] or "SIN NIVEL")
        level_bucket = balance_by_level.setdefault(
            level_key,
            {"nivel": level_key, "total_estudiantes": 0, "total_materias": 0},
        )
        level_bucket["total_estudiantes"] += 1
        level_bucket["total_materias"] += int(item["materias_actuales"] or 0)

    return {
        "total": len(students),
        "items": students,
        "paralelos": sorted(balance_by_parallel.values(), key=lambda item: str(item["paralelo"])),
        "balance": {
            "por_carrera": sorted(balance_by_career.values(), key=lambda item: str(item["nombre_carrera"])),
            "por_paralelo": sorted(balance_by_parallel.values(), key=lambda item: str(item["paralelo"])),
            "por_nivel": sorted(balance_by_level.values(), key=lambda item: str(item["nivel"])),
        },
    }


def _validate_payload(payload: AcademicEnrollmentPayload) -> None:
    payload.tipo_matricula = payload.tipo_matricula.strip().upper() or "R"
    payload.paralelo = (payload.paralelo.strip().upper() or "A")[:4]
    if payload.tipo_matricula not in _VALID_TIPO_MATRICULA:
        raise HTTPException(status_code=400, detail="tipo_matricula debe ser R, H o E")
    if payload.num_grupo < 0:
        raise HTTPException(status_code=400, detail="num_grupo no puede ser negativo")
    if payload.cod_jornada < 0:
        raise HTTPException(status_code=400, detail="cod_jornada no puede ser negativo")
    if not payload.materia_codes:
        raise HTTPException(status_code=400, detail="Selecciona al menos una materia del pensum")
    payload.materia_codes = sorted({int(code) for code in payload.materia_codes})


def _preinscription_source_for_student(cursor: pyodbc.Cursor, codigo_estud: int) -> Any | None:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, Codestu) AS Codestu,
            TRY_CONVERT(varchar(20), Cedula) AS Cedula,
            TRY_CONVERT(nvarchar(100), Apellidos_nombre) AS Apellidos_nombre,
            TRY_CONVERT(varchar(100), correo) AS correo,
            TRY_CONVERT(varchar(100), telefono) AS telefono,
            TRY_CONVERT(int, codprov) AS codprov
        FROM dbo.PREINSCRIPCION
        WHERE TRY_CONVERT(int, Codestu) = ?
        ORDER BY Fecha_Ingreso DESC
        """,
        codigo_estud,
    )
    return cursor.fetchone()


def _resolve_or_create_student_from_preinscription(
    cursor: pyodbc.Cursor,
    payload: AcademicEnrollmentPayload,
    create_missing: bool,
) -> bool:
    source = _preinscription_source_for_student(cursor, payload.codigo_estud)
    if not source:
        return False

    cedula = _clean(source.Cedula)
    if cedula:
        cursor.execute(
            """
            SELECT TOP (1) TRY_CONVERT(int, codigo_estud) AS codigo_estud
            FROM dbo.DATOS_ESTUD
            WHERE LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) = LTRIM(RTRIM(?))
            """,
            cedula,
        )
        existing = cursor.fetchone()
        if existing and existing.codigo_estud is not None:
            payload.codigo_estud = int(existing.codigo_estud)
            return True

    if not create_missing:
        return True

    numeric_cedula = _int_value(cedula) or 0
    cursor.execute(
        """
        INSERT INTO dbo.DATOS_ESTUD (
            codigo_estud, Cedula_Est, Apellidos_nombre, codprov, correo,
            telefono, movil, Fecha_Ingreso, EstadoCivil, Etnia, Sexo,
            Cedula, Fotos, Tipodoc, Estado, NumMigracion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 1, 1, 1, ?, 0, 1, 'A', 0)
        """,
        payload.codigo_estud,
        cedula[:50],
        _clean(source.Apellidos_nombre)[:70],
        source.codprov,
        _clean(source.correo)[:80],
        _clean(source.telefono)[:30],
        _clean(source.telefono)[:15],
        numeric_cedula,
    )
    return True


def _ensure_entity_exists(
    cursor: pyodbc.Cursor,
    payload: AcademicEnrollmentPayload,
    allow_preinscription_student: bool = False,
) -> None:
    cursor.execute("SELECT COUNT(*) FROM dbo.DATOS_ESTUD WHERE codigo_estud = ?", payload.codigo_estud)
    if int(cursor.fetchone()[0] or 0) == 0 and not (
        allow_preinscription_student and _resolve_or_create_student_from_preinscription(cursor, payload, False)
    ):
        raise HTTPException(status_code=404, detail="No se encontro el estudiante seleccionado")
    cursor.execute("SELECT COUNT(*) FROM dbo.CARRERAS WHERE Cod_AnioBasica = ?", payload.cod_anio_basica)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro la carrera seleccionada")
    cursor.execute("SELECT COUNT(*) FROM dbo.PERIODO WHERE cod_periodo = ?", payload.codigo_periodo)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro el periodo seleccionado")
    if payload.cod_jornada:
        cursor.execute("SELECT COUNT(*) FROM dbo.JORNADA WHERE NumJ = ?", payload.cod_jornada)
        if int(cursor.fetchone()[0] or 0) == 0:
            raise HTTPException(status_code=404, detail="No se encontro la jornada seleccionada")


def _fetch_jornada_name(cursor: pyodbc.Cursor, cod_jornada: int) -> str:
    if not cod_jornada:
        return ""
    cursor.execute(
        """
        SELECT TOP (1) DetalleJ
        FROM dbo.JORNADA
        WHERE NumJ = ?
        """,
        cod_jornada,
    )
    row = cursor.fetchone()
    return _clean(row.DetalleJ) if row else ""


def _is_inactive_teacher_status(value: Any) -> bool:
    status = _clean(value).upper()
    return status in {"0", "I", "INACTIVO", "INACTIVA", "FALSE", "NO", "N"}


def _validate_teacher_payload(payload: AcademicTeacherEnrollmentPayload) -> None:
    payload.paralelo = (payload.paralelo.strip().upper() or "A")[:4]
    if payload.cod_jornada < 0:
        raise HTTPException(status_code=400, detail="cod_jornada no puede ser negativo")
    payload.estado_moodle_doc = 1 if int(payload.estado_moodle_doc or 0) else 0


def _ensure_teacher_entities_exist(cursor: pyodbc.Cursor, payload: AcademicTeacherEnrollmentPayload) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
            TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula,
            COALESCE(
                NULLIF(TRY_CONVERT(nvarchar(255), u.login), N''),
                NULLIF(TRY_CONVERT(nvarchar(255), d.correo), N''),
                TRY_CONVERT(nvarchar(255), d.correop)
            ) AS login,
            COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), u.tipo_usuario), N''), N'DOCENTE') AS tipo_usuario,
            TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
            COALESCE(
                NULLIF(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre), N''),
                TRY_CONVERT(nvarchar(4000), u.Descripcion)
            ) AS Descripcion,
            TRY_CONVERT(nvarchar(255), d.correo) AS correo,
            TRY_CONVERT(nvarchar(255), d.correop) AS correop,
            TRY_CONVERT(nvarchar(100), d.telefono) AS telefono,
            TRY_CONVERT(nvarchar(100), d.movil) AS movil,
            TRY_CONVERT(nvarchar(4000), d.Perfil) AS Perfil,
            TRY_CONVERT(nvarchar(255), d.TipoDocente) AS TipoDocente,
            TRY_CONVERT(nvarchar(4000), d.nombreUnidadAcademica) AS nombreUnidadAcademica,
            TRY_CONVERT(nvarchar(255), d.nivelFormacion) AS nivelFormacion,
            TRY_CONVERT(nvarchar(4000), d.tercernivel) AS tercernivel,
            TRY_CONVERT(nvarchar(4000), d.cuartonivel) AS cuartonivel
        FROM dbo.DATOSDOCENTE d
        LEFT JOIN dbo.USUARIOS u
          ON TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
        WHERE TRY_CONVERT(int, d.codigo_doc) = ?
        """,
        payload.codigo_doc,
    )
    teacher = cursor.fetchone()
    if not teacher:
        cursor.execute(
            """
            SELECT TOP (1)
                TRY_CONVERT(varchar(50), Codigo_Usuario) AS codigo_doc,
                TRY_CONVERT(nvarchar(100), cedula) AS cedula,
                TRY_CONVERT(nvarchar(255), login) AS login,
                TRY_CONVERT(nvarchar(100), tipo_usuario) AS tipo_usuario,
                TRY_CONVERT(nvarchar(100), Estado) AS Estado,
                TRY_CONVERT(nvarchar(4000), Descripcion) AS Descripcion,
                CAST(NULL AS nvarchar(255)) AS correo,
                CAST(NULL AS nvarchar(255)) AS correop,
                CAST(NULL AS nvarchar(100)) AS telefono,
                CAST(NULL AS nvarchar(100)) AS movil,
                CAST(NULL AS nvarchar(4000)) AS Perfil,
                CAST(NULL AS nvarchar(255)) AS TipoDocente,
                CAST(NULL AS nvarchar(4000)) AS nombreUnidadAcademica,
                CAST(NULL AS nvarchar(255)) AS nivelFormacion,
                CAST(NULL AS nvarchar(4000)) AS tercernivel,
                CAST(NULL AS nvarchar(4000)) AS cuartonivel
            FROM dbo.USUARIOS
            WHERE TRY_CONVERT(int, Codigo_Usuario) = ?
            """,
            payload.codigo_doc,
        )
        teacher = cursor.fetchone()
    if not teacher:
        raise HTTPException(status_code=404, detail="No se encontro el docente seleccionado")
    if _clean(getattr(teacher, "Estado", "")) and _is_inactive_teacher_status(teacher.Estado):
        raise HTTPException(status_code=400, detail="El docente seleccionado esta inactivo")

    cursor.execute("SELECT COUNT(*) FROM dbo.PERIODO WHERE cod_periodo = ?", payload.codigo_periodo)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro el periodo seleccionado")
    if hasattr(payload, "cod_anio_basica") and hasattr(payload, "codigo_materia"):
        cursor.execute("SELECT COUNT(*) FROM dbo.CARRERAS WHERE Cod_AnioBasica = ?", payload.cod_anio_basica)
        if int(cursor.fetchone()[0] or 0) == 0:
            raise HTTPException(status_code=404, detail="No se encontro la carrera seleccionada")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dbo.PENSUM
            WHERE Cod_AnioBasica = ?
              AND codigo_materia = ?
            """,
            payload.cod_anio_basica,
            payload.codigo_materia,
        )
        if int(cursor.fetchone()[0] or 0) == 0:
            raise HTTPException(status_code=404, detail="La materia no pertenece al pensum de la carrera")
    return _teacher_item(teacher)


def _link_teacher_to_enrolled_students(
    cursor: pyodbc.Cursor,
    *,
    codigo_doc: int,
    cod_anio_basica: int,
    codigo_materia: int,
    codigo_periodo: int,
    paralelo: str,
) -> int:
    teacher_user = str(codigo_doc)[:10]
    cursor.execute(
        """
        UPDATE dbo.CARRERAXESTUD
        SET Usuario = ?
        WHERE TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_materia) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
          AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), paralelo), N'')))) = ?
        """,
        teacher_user,
        cod_anio_basica,
        codigo_materia,
        codigo_periodo,
        paralelo,
    )
    rowcount = cursor.rowcount
    return rowcount if isinstance(rowcount, int) and rowcount > 0 else 0


def _ensure_bulk_entities_exist(cursor: pyodbc.Cursor, payload: AcademicBulkEnrollmentPayload) -> None:
    cursor.execute("SELECT COUNT(*) FROM dbo.CARRERAS WHERE Cod_AnioBasica = ?", payload.cod_anio_basica)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro la carrera seleccionada")
    cursor.execute("SELECT COUNT(*) FROM dbo.PERIODO WHERE cod_periodo = ?", payload.source_codigo_periodo)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro el periodo inscrito")
    cursor.execute("SELECT COUNT(*) FROM dbo.PERIODO WHERE cod_periodo = ?", payload.target_codigo_periodo)
    if int(cursor.fetchone()[0] or 0) == 0:
        raise HTTPException(status_code=404, detail="No se encontro el periodo de matricula")
    if payload.cod_jornada:
        cursor.execute("SELECT COUNT(*) FROM dbo.JORNADA WHERE NumJ = ?", payload.cod_jornada)
        if int(cursor.fetchone()[0] or 0) == 0:
            raise HTTPException(status_code=404, detail="No se encontro la jornada seleccionada")


def _fetch_pensum_by_code(cursor: pyodbc.Cursor, cod_anio_basica: int) -> dict[int, dict[str, Any]]:
    cursor.execute(
        """
        SELECT codigo_materia, cod_materia, Nomb_Materia, Semestre, Creditos, Orden, NumMalla, Horas, tipomateria
        FROM dbo.PENSUM
        WHERE Cod_AnioBasica = ?
        ORDER BY Semestre, Orden, Nomb_Materia
        """,
        cod_anio_basica,
    )
    return {int(row.codigo_materia): _subject_item(row) for row in cursor.fetchall()}


def _fetch_existing_codes(cursor: pyodbc.Cursor, payload: AcademicEnrollmentPayload) -> dict[int, dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            cxe.codigo_materia,
            cxe.Num_Matricula,
            cxe.Promedio,
            cxe.PromedioFinal,
            cxe.Recuperacion,
            cxe.Asistencia,
            cxe.P1Tareas,
            cxe.P1Proyectos,
            cxe.P1Examen,
            cxe.P2Tareas,
            cxe.P2Proyectos,
            cxe.P2Examen,
            cxe.P3Tareas,
            cxe.P3Proyectos,
            cxe.P3Examen
        FROM dbo.CARRERAXESTUD cxe
        WHERE cxe.codigo_estud = ?
          AND cxe.cod_anio_Basica = ?
          AND cxe.codigo_periodo = ?
        """,
        payload.codigo_estud,
        payload.cod_anio_basica,
        payload.codigo_periodo,
    )
    existing: dict[int, dict[str, Any]] = {}
    grade_fields = (
        "Promedio",
        "PromedioFinal",
        "Recuperacion",
        "Asistencia",
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
    for row in cursor.fetchall():
        code = int(row.codigo_materia)
        has_grades = any(getattr(row, field) not in (None, 0, Decimal("0")) for field in grade_fields)
        num_matricula = _int_value(row.Num_Matricula) or 0
        current = existing.get(code)
        if current is None:
            existing[code] = {"tiene_notas": has_grades, "num_matricula": num_matricula}
        else:
            current["tiene_notas"] = bool(current["tiene_notas"] or has_grades)
            current["num_matricula"] = max(int(current.get("num_matricula") or 0), num_matricula)
    return existing


def _next_number(cursor: pyodbc.Cursor, table: str, column: str) -> int:
    cursor.execute(f"SELECT COALESCE(MAX(TRY_CONVERT(int, {column})), 0) + 1 FROM dbo.{table}")
    return int(cursor.fetchone()[0] or 1)


def _next_student_matricula(cursor: pyodbc.Cursor, codigo_estud: int) -> int:
    cursor.execute(
        """
        SELECT COALESCE(MAX(valor), 0) + 1
        FROM (
            SELECT TRY_CONVERT(int, Num_Matricula) AS valor
            FROM dbo.CABECERA_MATRICULA
            WHERE codigo_estud = ?
            UNION ALL
            SELECT TRY_CONVERT(int, Num_Matricula) AS valor
            FROM dbo.CARRERAXESTUD
            WHERE codigo_estud = ?
        ) x
        """,
        codigo_estud,
        codigo_estud,
    )
    return int(cursor.fetchone()[0] or 1)


def _next_subject_matricula(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    cod_anio_basica: int,
    codigo_materia: int,
) -> int:
    cursor.execute(
        """
        SELECT COALESCE(MAX(TRY_CONVERT(int, Num_Matricula)), 0) + 1
        FROM dbo.CARRERAXESTUD
        WHERE codigo_estud = ?
          AND cod_anio_Basica = ?
          AND codigo_materia = ?
        """,
        codigo_estud,
        cod_anio_basica,
        codigo_materia,
    )
    return int(cursor.fetchone()[0] or 1)


def _fetch_target_period_subjects(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
    source_student: dict[str, Any],
    subject_codes: list[int],
) -> dict[int, int]:
    if not subject_codes:
        return {}
    ordered_codes = sorted({int(code) for code in subject_codes})
    placeholders = ",".join("?" for _ in ordered_codes)
    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(int, codigo_materia) AS codigo_materia,
            COALESCE(MAX(TRY_CONVERT(int, Num_Matricula)), 1) AS num_matricula
        FROM dbo.CARRERAXESTUD
        WHERE TRY_CONVERT(int, codigo_estud) = ?
          AND TRY_CONVERT(int, cod_anio_Basica) = ?
          AND TRY_CONVERT(int, codigo_periodo) = ?
          AND TRY_CONVERT(int, codigo_materia) IN ({placeholders})
        GROUP BY TRY_CONVERT(int, codigo_materia)
        """,
        int(source_student["codigo_estud"]),
        payload.cod_anio_basica,
        payload.target_codigo_periodo,
        *ordered_codes,
    )
    existing: dict[int, int] = {}
    for row in cursor.fetchall():
        code = _int_value(row.codigo_materia)
        if code is not None:
            existing[code] = _int_value(row.num_matricula) or 1
    return existing


def _fetch_target_enrollment_status(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    cod_anio_basica: int,
    codigo_periodo: int,
) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM dbo.CABECERA_MATRICULA cm
             WHERE TRY_CONVERT(int, cm.codigo_estud) = ?
               AND TRY_CONVERT(int, cm.cod_anio_Basica) = ?
               AND TRY_CONVERT(int, cm.codigo_periodo) = ?) AS cabeceras,
            (SELECT COUNT(*)
             FROM dbo.CARRERAXESTUD cxe
             WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
               AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
               AND TRY_CONVERT(int, cxe.codigo_periodo) = ?) AS materias
        """,
        codigo_estud,
        cod_anio_basica,
        codigo_periodo,
        codigo_estud,
        cod_anio_basica,
        codigo_periodo,
    )
    row = cursor.fetchone()
    cabeceras = int(row.cabeceras or 0) if row else 0
    materias = int(row.materias or 0) if row else 0
    return {
        "existe": cabeceras > 0 or materias > 0,
        "cabeceras": cabeceras,
        "materias": materias,
    }


def _audit_tables_exist(cursor: pyodbc.Cursor) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME IN ('AUD_MATRICULA_ACAD', 'AUD_MATRICULA_ACAD_DET')
        """
    )
    return int(cursor.fetchone()[0] or 0) == 2


def _fetch_audited_successful_subjects(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
) -> set[tuple[int, int]]:
    if not _audit_tables_exist(cursor):
        return set()
    cursor.execute(
        """
        SELECT codigo_estud, codigo_materia
        FROM dbo.AUD_MATRICULA_ACAD_DET
        WHERE periodo_destino = ?
          AND cod_anio_basica = ?
          AND ISNULL(fue_matriculado, 0) = 1
        """,
        payload.target_codigo_periodo,
        payload.cod_anio_basica,
    )
    audited: set[tuple[int, int]] = set()
    for row in cursor.fetchall():
        student_code = _int_value(row.codigo_estud)
        subject_code = _int_value(row.codigo_materia)
        if student_code is not None and subject_code is not None:
            audited.add((student_code, subject_code))
    return audited


def _fetch_career_name(cursor: pyodbc.Cursor, cod_anio_basica: int) -> str:
    cursor.execute(
        """
        SELECT TOP (1) Nombre_Basica
        FROM dbo.CARRERAS
        WHERE Cod_AnioBasica = ?
        """,
        cod_anio_basica,
    )
    row = cursor.fetchone()
    return _clean(row.Nombre_Basica) if row else ""


def _create_academic_audit_header(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
    user_code: str,
    preview: dict[str, Any],
) -> int | None:
    if not _audit_tables_exist(cursor):
        return None
    summary = preview.get("summary", {})
    total_listos = int(summary.get("insertar", 0) or 0) + int(summary.get("actualizar", 0) or 0)
    total_omitidos = (
        int(summary.get("bloqueadas_por_prerrequisito", 0) or 0)
        + int(summary.get("bloqueadas_por_notas", 0) or 0)
        + int(summary.get("estudiantes_sin_materias_habilitadas", 0) or 0)
        + int(summary.get("estudiantes_ya_matriculados", 0) or 0)
        + int(summary.get("ya_auditadas", 0) or 0)
        + int(summary.get("bloqueadas_por_num_matricula", 0) or 0)
        + int(summary.get("existentes", 0) or 0)
    )
    cursor.execute(
        """
        INSERT INTO dbo.AUD_MATRICULA_ACAD (
            fecha_creacion, usuario, periodo_origen, periodo_destino, carreras,
            estado, observacion, total_estudiantes, total_materias, total_listos,
            total_matriculados, total_omitidos
        )
        OUTPUT INSERTED.id_auditoria
        VALUES (GETDATE(), ?, ?, ?, ?, 'EN_PROCESO', ?, ?, ?, ?, 0, ?)
        """,
        user_code,
        payload.source_codigo_periodo,
        payload.target_codigo_periodo,
        str(payload.cod_anio_basica),
        "Matricula academica masiva",
        int(summary.get("estudiantes_origen", 0) or 0),
        int(summary.get("estudiantes_origen", 0) or 0) * len(payload.materia_codes),
        total_listos,
        total_omitidos,
    )
    row = cursor.fetchone()
    return int(row.id_auditoria if hasattr(row, "id_auditoria") else row[0])


def _update_academic_audit_header(
    cursor: pyodbc.Cursor,
    audit_id: int | None,
    summary: dict[str, Any],
) -> None:
    if audit_id is None:
        return
    total_matriculados = int(summary.get("inserted", 0) or 0) + int(summary.get("updated", 0) or 0)
    total_omitidos = (
        int(summary.get("blocked_by_prerequisite", 0) or 0)
        + int(summary.get("blocked_by_grades", 0) or 0)
        + int(summary.get("blocked_by_repetition", 0) or 0)
        + int(summary.get("skipped_students", 0) or 0)
        + int(summary.get("already_audited", 0) or 0)
        + int(summary.get("existing_skipped", 0) or 0)
    )
    cursor.execute(
        """
        UPDATE dbo.AUD_MATRICULA_ACAD
        SET estado = 'PROCESADO',
            total_matriculados = ?,
            total_omitidos = ?,
            observacion = ?
        WHERE id_auditoria = ?
        """,
        total_matriculados,
        total_omitidos,
        "Matricula academica masiva procesada",
        audit_id,
    )


def _insert_academic_audit_detail(
    cursor: pyodbc.Cursor,
    audit_id: int | None,
    source_student: dict[str, Any],
    payload: AcademicBulkEnrollmentPayload,
    career_name: str,
    codigo_materia: int,
    materia: str,
    nivel_origen: int | None,
    nivel_destino: int | None,
    num_matricula: int | None,
    estado_validacion: str,
    observacion: str,
    fue_matriculado: bool,
    fecha_matricula: date | None,
    promedio: float | None = None,
) -> None:
    if audit_id is None:
        return
    cursor.execute(
        """
        INSERT INTO dbo.AUD_MATRICULA_ACAD_DET (
            id_auditoria, codigo_estud, cedula, estudiante, cod_anio_basica, carrera,
            periodo_origen, periodo_destino, nivel_origen, nivel_destino,
            codigo_materia, materia, promedio, num_matricula, estado_validacion,
            observacion, fue_matriculado, fecha_matricula
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        audit_id,
        int(source_student["codigo_estud"]),
        source_student.get("cedula") or "",
        source_student.get("nombre_estudiante") or "",
        payload.cod_anio_basica,
        career_name,
        payload.source_codigo_periodo,
        payload.target_codigo_periodo,
        nivel_origen,
        nivel_destino,
        codigo_materia,
        materia,
        promedio,
        num_matricula,
        estado_validacion[:50],
        observacion,
        1 if fue_matriculado else 0,
        fecha_matricula.isoformat() if fecha_matricula else None,
    )


def _preview_with_cursor(cursor: pyodbc.Cursor, payload: AcademicEnrollmentPayload) -> dict[str, Any]:
    _validate_payload(payload)
    _ensure_entity_exists(cursor, payload, allow_preinscription_student=True)

    pensum_by_code = _fetch_pensum_by_code(cursor, payload.cod_anio_basica)
    selected_codes = set(payload.materia_codes)
    invalid_codes = sorted(selected_codes - set(pensum_by_code))
    if invalid_codes:
        raise HTTPException(
            status_code=400,
            detail=f"Materias fuera del pensum de la carrera: {', '.join(str(code) for code in invalid_codes)}",
        )

    target_status = _fetch_target_enrollment_status(
        cursor,
        payload.codigo_estud,
        payload.cod_anio_basica,
        payload.codigo_periodo,
    )
    if target_status["existe"]:
        def blocked_subject_action(code: int) -> dict[str, Any]:
            subject = dict(pensum_by_code.get(code, {"codigo_materia": str(code), "nombre_materia": ""}))
            subject["accion"] = "BLOQUEADA_PERIODO"
            return subject

        return {
            "criteria": payload.model_dump(),
            "cabecera": {
                "accion": "EXISTENTE",
                "existe": True,
                "bloqueada_por_periodo": True,
            },
            "summary": {
                "seleccionadas": len(selected_codes),
                "insertar": 0,
                "actualizar": 0,
                "existentes": int(target_status["materias"] or 0),
                "remover": 0,
                "bloqueadas_por_notas": 0,
                "bloqueadas_por_periodo": len(selected_codes),
            },
            "items": [blocked_subject_action(code) for code in sorted(selected_codes)],
        }

    existing = _fetch_existing_codes(cursor, payload)
    existing_codes = set(existing)
    insert_codes = sorted(selected_codes - existing_codes)
    existing_selected_codes = sorted(selected_codes & existing_codes)
    update_codes: list[int] = []
    removable_codes = sorted(existing_codes - selected_codes) if payload.remove_unselected else []
    blocked_remove_codes = [code for code in removable_codes if existing[code]["tiene_notas"]]
    safe_remove_codes = [code for code in removable_codes if code not in blocked_remove_codes]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM dbo.CABECERA_MATRICULA
        WHERE codigo_estud = ?
          AND cod_anio_Basica = ?
          AND codigo_periodo = ?
        """,
        payload.codigo_estud,
        payload.cod_anio_basica,
        payload.codigo_periodo,
    )
    has_cabecera = int(cursor.fetchone()[0] or 0) > 0

    def subject_action(code: int, action: str) -> dict[str, Any]:
        subject = dict(pensum_by_code.get(code, {"codigo_materia": str(code), "nombre_materia": ""}))
        subject["accion"] = action
        return subject

    return {
        "criteria": payload.model_dump(),
        "cabecera": {
            "accion": "EXISTENTE" if has_cabecera else "CREAR",
            "existe": has_cabecera,
        },
        "summary": {
            "seleccionadas": len(selected_codes),
            "insertar": len(insert_codes),
            "actualizar": len(update_codes),
            "existentes": len(existing_selected_codes),
            "remover": len(safe_remove_codes),
            "bloqueadas_por_notas": len(blocked_remove_codes),
        },
        "items": [subject_action(code, "INSERTAR") for code in insert_codes]
        + [subject_action(code, "EXISTENTE") for code in existing_selected_codes]
        + [subject_action(code, "REMOVER") for code in safe_remove_codes]
        + [subject_action(code, "BLOQUEADA_NOTAS") for code in blocked_remove_codes],
    }


def _validate_bulk_payload(payload: AcademicBulkEnrollmentPayload) -> None:
    payload.tipo_matricula = payload.tipo_matricula.strip().upper() or "R"
    payload.paralelo_default = (payload.paralelo_default.strip().upper() or "A")[:4]
    payload.paralelo_filter = (payload.paralelo_filter or "").strip().upper() or None
    if payload.tipo_matricula not in _VALID_TIPO_MATRICULA:
        raise HTTPException(status_code=400, detail="tipo_matricula debe ser R, H o E")
    if payload.num_grupo_default < 0:
        raise HTTPException(status_code=400, detail="num_grupo_default no puede ser negativo")
    if payload.cod_jornada < 0:
        raise HTTPException(status_code=400, detail="cod_jornada no puede ser negativo")
    if not payload.materia_codes:
        raise HTTPException(status_code=400, detail="Selecciona al menos una materia del pensum")
    payload.materia_codes = sorted({int(code) for code in payload.materia_codes})
    payload.student_codes = sorted({int(code) for code in payload.student_codes})


def _fetch_bulk_source_students(cursor: pyodbc.Cursor, payload: AcademicBulkEnrollmentPayload) -> list[dict[str, Any]]:
    cursor.execute(
        """
        WITH cxe_source AS (
            SELECT
                cxe.codigo_estud,
                cxe.cod_anio_Basica,
                cxe.codigo_periodo,
                cxe.paralelo,
                cxe.NumGrupo,
                COUNT(*) AS total_materias
            FROM dbo.CARRERAXESTUD cxe
            WHERE cxe.cod_anio_Basica = ?
              AND cxe.codigo_periodo = ?
            GROUP BY cxe.codigo_estud, cxe.cod_anio_Basica, cxe.codigo_periodo, cxe.paralelo, cxe.NumGrupo
        ),
        source_base AS (
            SELECT codigo_estud, cod_anio_Basica, codigo_periodo
            FROM cxe_source
            UNION
            SELECT cm.codigo_estud, cm.cod_anio_Basica, cm.codigo_periodo
            FROM dbo.CABECERA_MATRICULA cm
            WHERE cm.cod_anio_Basica = ?
              AND cm.codigo_periodo = ?
        ),
        source_assignment AS (
            SELECT *
            FROM (
                SELECT
                    cxe_source.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY cxe_source.codigo_estud
                        ORDER BY cxe_source.total_materias DESC, ISNULL(cxe_source.paralelo, ''), ISNULL(cxe_source.NumGrupo, 0)
                    ) AS rn
                FROM cxe_source
            ) ranked
            WHERE rn = 1
        )
        SELECT
            base.codigo_estud,
            d.Apellidos_nombre,
            d.Cedula_Est,
            assignment.paralelo,
            assignment.NumGrupo,
            COALESCE(assignment.total_materias, 0) AS materias_origen
        FROM source_base base
        INNER JOIN dbo.DATOS_ESTUD d ON d.codigo_estud = base.codigo_estud
        LEFT JOIN source_assignment assignment ON assignment.codigo_estud = base.codigo_estud
        WHERE (? IS NULL OR UPPER(ISNULL(assignment.paralelo, 'SIN PARALELO')) = ?)
        ORDER BY d.Apellidos_nombre, base.codigo_estud
        """,
        payload.cod_anio_basica,
        payload.source_codigo_periodo,
        payload.cod_anio_basica,
        payload.source_codigo_periodo,
        payload.paralelo_filter,
        payload.paralelo_filter,
    )
    students = [
        {
            "codigo_estud": int(row.codigo_estud),
            "nombre_estudiante": _clean(row.Apellidos_nombre),
            "cedula": _clean(row.Cedula_Est),
            "paralelo": _clean(row.paralelo),
            "num_grupo": _int_value(row.NumGrupo),
            "materias_origen": int(row.materias_origen or 0),
        }
        for row in cursor.fetchall()
    ]
    if payload.student_codes:
        selected_codes = set(payload.student_codes)
        found_codes = {int(student["codigo_estud"]) for student in students}
        missing_codes = sorted(selected_codes - found_codes)
        if missing_codes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Los estudiantes seleccionados no tienen matricula en el periodo/carrera origen: "
                    + ", ".join(str(code) for code in missing_codes[:20])
                ),
            )
        students = [student for student in students if int(student["codigo_estud"]) in selected_codes]
    return students


def _bulk_student_payload(
    source_student: dict[str, Any],
    payload: AcademicBulkEnrollmentPayload,
    materia_codes: list[int] | None = None,
) -> AcademicEnrollmentPayload:
    return AcademicEnrollmentPayload(
        codigo_estud=int(source_student["codigo_estud"]),
        cod_anio_basica=payload.cod_anio_basica,
        codigo_periodo=payload.target_codigo_periodo,
        materia_codes=list(materia_codes if materia_codes is not None else payload.materia_codes),
        paralelo=(source_student.get("paralelo") or payload.paralelo_default or "A"),
        num_grupo=int(source_student.get("num_grupo") or payload.num_grupo_default or 1),
        tipo_matricula=payload.tipo_matricula,
        control_matricula=payload.control_matricula,
        cod_jornada=payload.cod_jornada,
        inscrip_valor=payload.inscrip_valor,
        matri_valor=payload.matri_valor,
        valor=payload.valor,
        fecha_pago=payload.fecha_pago,
        remove_unselected=payload.remove_unselected,
    )


def _fetch_consecutive_rules(cursor: pyodbc.Cursor, payload: AcademicBulkEnrollmentPayload) -> dict[int, list[int]]:
    if not payload.materia_codes:
        return {}
    placeholders = ",".join("?" for _ in payload.materia_codes)
    cursor.execute(
        f"""
        SELECT
            TRY_CONVERT(int, cod_materia) AS materia_previa,
            TRY_CONVERT(int, cod_materia_consecutiva) AS materia_consecutiva
        FROM dbo.MATERIAS_CONSECUTIVAS
        WHERE TRY_CONVERT(int, cod_carrera) = ?
          AND ISNULL(bloqueada_por_reprobacion, 0) = 1
          AND TRY_CONVERT(int, cod_materia_consecutiva) IN ({placeholders})
        """,
        payload.cod_anio_basica,
        *payload.materia_codes,
    )
    rules: dict[int, list[int]] = {}
    for row in cursor.fetchall():
        previous_code = _int_value(row.materia_previa)
        next_code = _int_value(row.materia_consecutiva)
        if previous_code is None or next_code is None:
            continue
        rules.setdefault(next_code, []).append(previous_code)
    return rules


def _grade_candidate(value: Any) -> float | None:
    number = _number_value(value)
    if number is None:
        return None
    return number


def _fetch_passed_previous_subjects(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
    source_student: dict[str, Any],
    previous_codes: set[int],
) -> dict[int, float]:
    if not previous_codes:
        return {}
    ordered_codes = sorted(previous_codes)
    placeholders = ",".join("?" for _ in ordered_codes)
    cursor.execute(
        f"""
        SELECT codigo_materia, PromedioFinal, Promedio, PromedioAux
        FROM dbo.CARRERAXESTUD
        WHERE codigo_estud = ?
          AND cod_anio_Basica = ?
          AND codigo_periodo = ?
          AND codigo_materia IN ({placeholders})
        """,
        int(source_student["codigo_estud"]),
        payload.cod_anio_basica,
        payload.source_codigo_periodo,
        *ordered_codes,
    )
    passed: dict[int, float] = {}
    for row in cursor.fetchall():
        code = int(row.codigo_materia)
        grade = _grade_candidate(row.PromedioFinal)
        if grade is None:
            continue
        if _is_passing_final_grade(grade):
            passed[code] = grade
    return passed


def _fetch_bulk_student_progress(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
    source_student: dict[str, Any],
) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT
            cxe.codigo_materia,
            pensum.Semestre,
            cxe.PromedioFinal,
            cxe.Promedio,
            cxe.PromedioAux
        FROM dbo.CARRERAXESTUD cxe
        LEFT JOIN dbo.PENSUM pensum
          ON pensum.Cod_AnioBasica = cxe.cod_anio_Basica
         AND pensum.codigo_materia = cxe.codigo_materia
        WHERE cxe.codigo_estud = ?
          AND cxe.cod_anio_Basica = ?
          AND cxe.codigo_periodo = ?
        """,
        int(source_student["codigo_estud"]),
        payload.cod_anio_basica,
        payload.source_codigo_periodo,
    )
    subjects: dict[int, dict[str, Any]] = {}
    for row in cursor.fetchall():
        code = _int_value(row.codigo_materia)
        if code is None:
            continue
        grade = _grade_candidate(row.PromedioFinal)
        current = subjects.get(code)
        if current is None:
            subjects[code] = {"semestre": _int_value(row.Semestre), "grade": grade}
        elif grade is not None:
            current["grade"] = max(value for value in (current.get("grade"), grade) if value is not None)

    levels = [item["semestre"] for item in subjects.values() if item.get("semestre") is not None]
    current_level = max(levels) if levels else None
    approved_current = {
        code
        for code, item in subjects.items()
        if current_level is not None
        and item.get("semestre") == current_level
        and item.get("grade") is not None
        and _is_passing_final_grade(item["grade"])
    }
    return {
        "nivel_actual": current_level,
        "aprobadas_nivel_actual": len(approved_current),
        "materias_aprobadas": approved_current,
    }


def _bulk_allowed_subjects(
    cursor: pyodbc.Cursor,
    payload: AcademicBulkEnrollmentPayload,
    source_student: dict[str, Any],
    consecutive_rules: dict[int, list[int]],
    pensum_by_code: dict[int, dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]]]:
    def block_all(motivo: str) -> tuple[list[int], list[dict[str, Any]]]:
        return [], [
            {
                "codigo_materia": str(code),
                "materias_previas": [],
                "motivo": motivo,
            }
            for code in payload.materia_codes
        ]

    target_levels = {pensum_by_code.get(code, {}).get("semestre") for code in payload.materia_codes}
    target_levels.discard(None)
    if len(target_levels) != 1:
        return block_all("Las materias seleccionadas deben pertenecer al mismo nivel")

    target_level = int(next(iter(target_levels)))
    target_level_codes = {
        int(code)
        for code, subject in pensum_by_code.items()
        if _int_value(subject.get("semestre")) == target_level
    }
    selected_codes = {int(code) for code in payload.materia_codes}
    if not target_level_codes:
        return block_all("No hay materias configuradas en el nivel destino")
    if selected_codes != target_level_codes:
        return block_all("La matriculacion masiva debe contener todas las materias del nivel destino")

    progress = _fetch_bulk_student_progress(cursor, payload, source_student)
    current_level = progress["nivel_actual"]
    if current_level is None:
        return block_all("No se pudo determinar el nivel actual del estudiante")
    if target_level != current_level + 1:
        return block_all("El nivel destino debe ser exactamente el siguiente nivel del estudiante")
    current_level_codes = {
        int(code)
        for code, subject in pensum_by_code.items()
        if _int_value(subject.get("semestre")) == current_level
    }
    required_current_count = len(current_level_codes)
    if required_current_count <= 0:
        return block_all("No hay materias configuradas en el nivel actual del estudiante")
    if int(progress["aprobadas_nivel_actual"] or 0) < required_current_count:
        return block_all(
            "El estudiante no alcanzo PromedioFinal mayor o igual a "
            f"{_PASSING_FINAL_GRADE:g} en todas las materias del nivel actual "
            f"({progress['aprobadas_nivel_actual']}/{required_current_count})"
        )

    previous_codes = {previous for previous_list in consecutive_rules.values() for previous in previous_list}
    passed_previous = _fetch_passed_previous_subjects(cursor, payload, source_student, previous_codes)
    allowed: list[int] = []
    blocked: list[dict[str, Any]] = []
    for code in payload.materia_codes:
        required_previous = consecutive_rules.get(code, [])
        missing = [previous for previous in required_previous if previous not in passed_previous]
        if missing:
            blocked.append(
                {
                    "codigo_materia": str(code),
                    "materias_previas": [str(previous) for previous in missing],
                    "motivo": f"Materia previa sin PromedioFinal aprobatorio mayor o igual a {_PASSING_FINAL_GRADE:g}",
                }
            )
        else:
            allowed.append(code)
    return allowed, blocked


def _bulk_subject_preview_items(pensum_by_code: dict[int, dict[str, Any]], codes: list[int]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in sorted({int(value) for value in codes}):
        subject = pensum_by_code.get(code, {})
        items.append(
            {
                "codigo_materia": str(code),
                "nombre_materia": subject.get("nombre_materia") or subject.get("Nomb_Materia") or "",
                "semestre": _int_value(subject.get("semestre")),
                "creditos": _number_value(subject.get("creditos")),
            }
        )
    return items


def _bulk_preview_item(
    source_student: dict[str, Any],
    payload: AcademicBulkEnrollmentPayload,
    career_name: str,
    pensum_by_code: dict[int, dict[str, Any]],
    progress: dict[str, Any] | None,
    target_level: int | None,
    cabecera: str,
    pending_codes: list[int],
    existing_count: int,
    remover_count: int,
    blocked_subjects: list[dict[str, Any]],
    blocked_by_attempt: int,
    already_audited: int,
    status: str,
    motivo: str = "",
) -> dict[str, Any]:
    return {
        "codigo_estud": str(source_student["codigo_estud"]),
        "cedula": source_student.get("cedula") or "",
        "nombre_estudiante": source_student.get("nombre_estudiante") or "",
        "cod_anio_basica": str(payload.cod_anio_basica),
        "carrera": career_name,
        "paralelo": source_student.get("paralelo") or payload.paralelo_default,
        "num_grupo": source_student.get("num_grupo") or payload.num_grupo_default,
        "nivel_origen": _int_value((progress or {}).get("nivel_actual")),
        "nivel_destino": target_level,
        "estado": status,
        "motivo": motivo,
        "cabecera": cabecera,
        "insertar": len(pending_codes),
        "actualizar": 0,
        "existentes": existing_count,
        "remover": remover_count,
        "bloqueadas_por_prerrequisito": len(blocked_subjects),
        "bloqueadas_por_num_matricula": blocked_by_attempt,
        "ya_auditadas": already_audited,
        "materias_insertar": _bulk_subject_preview_items(pensum_by_code, pending_codes),
        "materias_bloqueadas": blocked_subjects,
    }


def _bulk_preview_with_cursor(cursor: pyodbc.Cursor, payload: AcademicBulkEnrollmentPayload) -> dict[str, Any]:
    _validate_bulk_payload(payload)
    _ensure_bulk_entities_exist(cursor, payload)
    pensum_by_code = _fetch_pensum_by_code(cursor, payload.cod_anio_basica)
    invalid_codes = sorted(set(payload.materia_codes) - set(pensum_by_code))
    if invalid_codes:
        raise HTTPException(
            status_code=400,
            detail=f"Materias fuera del pensum de la carrera: {', '.join(str(code) for code in invalid_codes)}",
        )

    source_students = _fetch_bulk_source_students(cursor, payload)
    if not source_students:
        raise HTTPException(status_code=404, detail="No hay estudiantes en el periodo inscrito para la carrera seleccionada")

    career_name = _fetch_career_name(cursor, payload.cod_anio_basica)
    target_levels = {pensum_by_code.get(code, {}).get("semestre") for code in payload.materia_codes}
    target_levels.discard(None)
    target_level = int(next(iter(target_levels))) if len(target_levels) == 1 else None
    summary = {
        "estudiantes_origen": len(source_students),
        "materias_seleccionadas": len(payload.materia_codes),
        "cabeceras_crear": 0,
        "cabeceras_actualizar": 0,
        "cabeceras_existentes": 0,
        "insertar": 0,
        "actualizar": 0,
        "existentes": 0,
        "remover": 0,
        "bloqueadas_por_notas": 0,
        "bloqueadas_por_prerrequisito": 0,
        "bloqueadas_por_num_matricula": 0,
        "estudiantes_ya_matriculados": 0,
        "estudiantes_sin_materias_habilitadas": 0,
        "ya_auditadas": 0,
    }
    consecutive_rules = _fetch_consecutive_rules(cursor, payload)
    audited_successful = _fetch_audited_successful_subjects(cursor, payload)
    items: list[dict[str, Any]] = []
    for source_student in source_students:
        progress = _fetch_bulk_student_progress(cursor, payload, source_student)
        target_status = _fetch_target_enrollment_status(
            cursor,
            int(source_student["codigo_estud"]),
            payload.cod_anio_basica,
            payload.target_codigo_periodo,
        )
        if target_status["existe"]:
            summary["estudiantes_ya_matriculados"] += 1
            summary["cabeceras_existentes"] += 1 if int(target_status["cabeceras"] or 0) > 0 else 0
            summary["existentes"] += int(target_status["materias"] or 0)
            items.append(
                _bulk_preview_item(
                    source_student,
                    payload,
                    career_name,
                    pensum_by_code,
                    progress,
                    target_level,
                    "YA_MATRICULADO_PERIODO",
                    [],
                    int(target_status["materias"] or 0),
                    0,
                    [],
                    0,
                    0,
                    "YA_MATRICULADO",
                    "El estudiante ya tiene matricula en la carrera y periodo destino",
                )
            )
            continue
        allowed_codes, blocked_subjects = _bulk_allowed_subjects(
            cursor,
            payload,
            source_student,
            consecutive_rules,
            pensum_by_code,
        )
        summary["bloqueadas_por_prerrequisito"] += len(blocked_subjects)
        pending_codes: list[int] = []
        already_audited = 0
        blocked_by_attempt = 0
        existing_target = _fetch_target_period_subjects(cursor, payload, source_student, allowed_codes)
        existing_in_target = 0
        for code in allowed_codes:
            if int(code) in existing_target:
                existing_in_target += 1
                continue
            audit_key = (int(source_student["codigo_estud"]), int(code))
            if audit_key in audited_successful:
                already_audited += 1
                continue
            next_attempt = _next_subject_matricula(
                cursor,
                int(source_student["codigo_estud"]),
                payload.cod_anio_basica,
                int(code),
            )
            if next_attempt > 3:
                blocked_by_attempt += 1
                continue
            pending_codes.append(code)
        summary["existentes"] += existing_in_target
        summary["ya_auditadas"] += already_audited
        summary["bloqueadas_por_num_matricula"] += blocked_by_attempt
        if not pending_codes:
            summary["estudiantes_sin_materias_habilitadas"] += 1
            block_reason = ""
            if blocked_subjects:
                block_reason = blocked_subjects[0].get("motivo") or "Materia bloqueada"
            elif blocked_by_attempt:
                block_reason = "La materia supera el tercer numero de matricula permitido"
            elif already_audited:
                block_reason = "La materia ya fue procesada en una auditoria previa"
            elif existing_in_target:
                block_reason = "Las materias ya existen en el periodo destino"
            else:
                block_reason = "No hay materias pendientes para insertar"
            items.append(
                _bulk_preview_item(
                    source_student,
                    payload,
                    career_name,
                    pensum_by_code,
                    progress,
                    target_level,
                    "SIN_MATERIAS_PENDIENTES",
                    [],
                    existing_in_target,
                    0,
                    blocked_subjects,
                    blocked_by_attempt,
                    already_audited,
                    "BLOQUEADO",
                    block_reason,
                )
            )
            continue
        student_payload = _bulk_student_payload(source_student, payload, pending_codes)
        preview = _preview_with_cursor(cursor, student_payload)
        if preview["cabecera"]["existe"]:
            summary["cabeceras_existentes"] += 1
        else:
            summary["cabeceras_crear"] += 1
        summary["insertar"] += int(preview["summary"]["insertar"] or 0)
        summary["actualizar"] += int(preview["summary"]["actualizar"] or 0)
        summary["existentes"] += int(preview["summary"].get("existentes", 0) or 0)
        summary["remover"] += int(preview["summary"]["remover"] or 0)
        summary["bloqueadas_por_notas"] += int(preview["summary"]["bloqueadas_por_notas"] or 0)
        items.append(
            _bulk_preview_item(
                source_student,
                payload,
                career_name,
                pensum_by_code,
                progress,
                target_level,
                preview["cabecera"]["accion"],
                pending_codes,
                existing_in_target + int(preview["summary"].get("existentes", 0) or 0),
                int(preview["summary"]["remover"] or 0),
                blocked_subjects,
                blocked_by_attempt,
                already_audited,
                "LISTO",
                "Listo para matricular en el nivel inmediato superior",
            )
        )

    return {
        "criteria": payload.model_dump(),
        "summary": summary,
        "items": items,
    }


def _save_enrollment_with_cursor(
    cursor: pyodbc.Cursor,
    payload: AcademicEnrollmentPayload,
    user_code: str,
    today: date,
) -> dict[str, Any]:
    _validate_payload(payload)
    if not _resolve_or_create_student_from_preinscription(cursor, payload, True):
        _ensure_entity_exists(cursor, payload)
    preview = _preview_with_cursor(cursor, payload)
    if int(preview.get("summary", {}).get("bloqueadas_por_periodo", 0) or 0) > 0:
        subject_results = [
            {
                "codigo_materia": int(item.get("codigo_materia") or 0),
                "nombre_materia": item.get("nombre_materia") or "",
                "num_matricula": None,
                "accion": "BLOQUEADA_PERIODO",
                "fue_matriculado": False,
                "observacion": "El estudiante ya tiene matricula registrada en la carrera y periodo destino; no se realizo ningun cambio",
            }
            for item in preview.get("items", [])
        ]
        return {
            "ok": True,
            "message": "El estudiante ya tiene matricula en la carrera y periodo destino; no se generaron registros duplicados.",
            "num_matricula": "",
            "inserted": 0,
            "updated": 0,
            "existing_skipped": int(preview.get("summary", {}).get("existentes", 0) or 0),
            "removed": 0,
            "blocked_by_grades": 0,
            "blocked_by_repetition": 0,
            "blocked_by_period": int(preview.get("summary", {}).get("bloqueadas_por_periodo", 0) or 0),
            "subject_results": subject_results,
            "preview": preview,
        }
    selected_codes = set(payload.materia_codes)
    pensum_by_code = _fetch_pensum_by_code(cursor, payload.cod_anio_basica)
    fecha_pago = payload.fecha_pago or today.isoformat()

    cursor.execute(
        """
        SELECT TOP (1) Num_Matricula
        FROM dbo.CABECERA_MATRICULA
        WHERE codigo_estud = ?
          AND cod_anio_Basica = ?
          AND codigo_periodo = ?
        ORDER BY Num_Matricula DESC
        """,
        payload.codigo_estud,
        payload.cod_anio_basica,
        payload.codigo_periodo,
    )
    cabecera_row = cursor.fetchone()
    # La cabecera academica se crea una sola vez por estudiante/carrera/periodo.
    # Si no existe, nace como primera matricula de ese periodo; si existe, no se modifica.
    num_matricula = int(cabecera_row.Num_Matricula) if cabecera_row and cabecera_row.Num_Matricula else 1
    jornada_nombre = _fetch_jornada_name(cursor, payload.cod_jornada)

    if not cabecera_row:
        cursor.execute(
            """
            INSERT INTO dbo.CABECERA_MATRICULA (
                codigo_estud, cod_anio_Basica, codigo_periodo, Num_Matricula, fecha_pago,
                valor, InscripValor, MatriValor, Cuota1, RecargoMatricula, Beca, Descuento,
                Jornada, AyudaEcono, ControlMatricula, ValorNivelacion, codhorario, codmodalidad,
                coddias, codjornada, codestadoMat, reingreso,
                Descuentoprontopago, Descuentoreferidos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, 0, ?, 0, 0, 0, 0, ?, 0, 0, 0, 0)
            """,
            payload.codigo_estud,
            payload.cod_anio_basica,
            payload.codigo_periodo,
            num_matricula,
            fecha_pago,
            payload.valor,
            payload.inscrip_valor,
            payload.matri_valor,
            jornada_nombre,
            payload.control_matricula,
            payload.cod_jornada,
        )

    existing = _fetch_existing_codes(cursor, payload)
    next_reg = _next_number(cursor, "CARRERAXESTUD", "Num_Reg_Mat")
    inserted = 0
    updated = 0
    existing_skipped = 0
    blocked_by_repetition = 0
    subject_results: list[dict[str, Any]] = []
    for code in sorted(selected_codes):
        subject = pensum_by_code[code]
        credits = int(float(subject.get("creditos") or 0))
        if code in existing:
            subject_num_matricula = int(existing[code].get("num_matricula") or num_matricula)
            existing_skipped += 1
            subject_results.append(
                {
                    "codigo_materia": code,
                    "nombre_materia": subject.get("nombre_materia") or "",
                    "num_matricula": subject_num_matricula,
                    "accion": "EXISTENTE",
                    "fue_matriculado": False,
                    "observacion": "Materia ya existe en el periodo destino; no se realizo ningun cambio",
                }
            )
        else:
            subject_num_matricula = _next_subject_matricula(
                cursor,
                payload.codigo_estud,
                payload.cod_anio_basica,
                code,
            )
            if subject_num_matricula > 3:
                blocked_by_repetition += 1
                subject_results.append(
                    {
                        "codigo_materia": code,
                        "nombre_materia": subject.get("nombre_materia") or "",
                        "num_matricula": subject_num_matricula,
                        "accion": "BLOQUEADA_NUM_MATRICULA",
                        "fue_matriculado": False,
                        "observacion": "La materia supera el tercer numero de matricula permitido",
                    }
                )
                continue
            cursor.execute(
                """
                INSERT INTO dbo.CARRERAXESTUD (
                    codigo_estud, cod_anio_Basica, codigo_materia, codigo_periodo,
                    Num_Matricula, paralelo, NumGrupo, Num_Creditos, Fecha_Matricula,
                    Num_Reg_Mat, TipoMatricula, ControlMatricula, NumCertificado,
                    gcer, NumMatricuMod, TipoCursoMigra, CodUsuaMat
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, '', ?)
                """,
                payload.codigo_estud,
                payload.cod_anio_basica,
                code,
                payload.codigo_periodo,
                subject_num_matricula,
                payload.paralelo,
                payload.num_grupo,
                credits,
                today.isoformat(),
                next_reg,
                payload.tipo_matricula,
                payload.control_matricula,
                user_code,
            )
            inserted += 1
            subject_results.append(
                {
                    "codigo_materia": code,
                    "nombre_materia": subject.get("nombre_materia") or "",
                    "num_matricula": subject_num_matricula,
                    "accion": "INSERTAR",
                    "fue_matriculado": True,
                    "observacion": "Materia insertada en CARRERAXESTUD",
                }
            )
            next_reg += 1

    removed = 0
    blocked = 0
    if payload.remove_unselected:
        for item in preview["items"]:
            if item["accion"] == "REMOVER":
                cursor.execute(
                    """
                    DELETE FROM dbo.CARRERAXESTUD
                    WHERE codigo_estud = ?
                      AND cod_anio_Basica = ?
                      AND codigo_periodo = ?
                      AND codigo_materia = ?
                    """,
                    payload.codigo_estud,
                    payload.cod_anio_basica,
                    payload.codigo_periodo,
                    int(item["codigo_materia"]),
                )
                removed += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            elif item["accion"] == "BLOQUEADA_NOTAS":
                blocked += 1

    return {
        "ok": True,
        "message": "Matricula academica guardada correctamente.",
        "num_matricula": str(num_matricula),
        "inserted": inserted,
        "updated": updated,
        "existing_skipped": existing_skipped,
        "removed": removed,
        "blocked_by_grades": blocked,
        "blocked_by_repetition": blocked_by_repetition,
        "subject_results": subject_results,
        "preview": preview,
    }


@router.get("/catalog")
def matricula_acad_catalog(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT Cod_AnioBasica, Nombre_Basica, Estado, Abrevia, tp_escuela
                FROM dbo.CARRERAS
                WHERE ISNULL(Estado, 'A') = 'A'
                ORDER BY Nombre_Basica
                """
            )
            carreras = [_career_item(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                WITH matriculas AS (
                    SELECT codigo_estud, cod_anio_Basica, codigo_periodo
                    FROM dbo.CABECERA_MATRICULA
                    UNION
                    SELECT codigo_estud, cod_anio_Basica, codigo_periodo
                    FROM dbo.CARRERAXESTUD
                )
                SELECT TOP (120)
                    p.cod_periodo,
                    p.Detalle_Periodo,
                    p.Estado,
                    p.Periodo,
                    p.anio,
                    p.fechain,
                    p.fechafin,
                    p.TipoMatricula,
                    COUNT(DISTINCT CASE
                        WHEN m.codigo_estud IS NULL THEN NULL
                        ELSE CONCAT(TRY_CONVERT(varchar(50), m.codigo_estud), ':', TRY_CONVERT(varchar(50), m.cod_anio_Basica))
                    END) AS total_matriculados
                FROM dbo.PERIODO p
                LEFT JOIN matriculas m ON m.codigo_periodo = p.cod_periodo
                GROUP BY p.cod_periodo, p.Detalle_Periodo, p.Estado, p.Periodo, p.anio, p.fechain, p.fechafin, p.TipoMatricula
                ORDER BY
                    CASE
                        WHEN CAST(GETDATE() AS date) BETWEEN COALESCE(p.fechain, CAST('19000101' AS date)) AND COALESCE(p.fechafin, CAST('99991231' AS date)) THEN 0
                        WHEN COALESCE(p.fechain, CAST('19000101' AS date)) <= CAST(GETDATE() AS date) THEN 1
                        ELSE 2
                    END,
                    CASE WHEN COUNT(DISTINCT CASE
                        WHEN m.codigo_estud IS NULL THEN NULL
                        ELSE CONCAT(TRY_CONVERT(varchar(50), m.codigo_estud), ':', TRY_CONVERT(varchar(50), m.cod_anio_Basica))
                    END) > 0 THEN 0 ELSE 1 END,
                    COALESCE(p.anio, 0) DESC,
                    p.cod_periodo DESC
                """
            )
            periodos = [_period_item(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), NumJ) AS option_value,
                    TRY_CONVERT(nvarchar(255), DetalleJ) AS option_label,
                    TRY_CONVERT(nvarchar(20), codmodalidad) AS modalidad
                FROM dbo.JORNADA
                ORDER BY TRY_CONVERT(nvarchar(255), DetalleJ)
                """
            )
            jornadas = [_jornada_item(row) for row in cursor.fetchall()]
        return {
            "carreras": carreras,
            "periodos": periodos,
            "jornadas": jornadas,
            "tipos_matricula": [
                {"value": "R", "label": "Regular"},
                {"value": "H", "label": "Homologacion"},
                {"value": "E", "label": "Especial"},
            ],
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando catalogo academico: {exc}") from exc


@router.get("/careers")
def matricula_acad_careers(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int | None, Query(description="Periodo inscrito para filtrar carreras")] = None,
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            if codigo_periodo is None:
                cursor.execute(
                    """
                    SELECT Cod_AnioBasica, Nombre_Basica, Estado, Abrevia, tp_escuela, 0 AS total_matriculados
                    FROM dbo.CARRERAS
                    WHERE ISNULL(Estado, 'A') = 'A'
                    ORDER BY Nombre_Basica
                    """
                )
            else:
                cursor.execute(
                    """
                    WITH carreras_periodo AS (
                        SELECT codigo_estud, cod_anio_Basica
                        FROM dbo.CABECERA_MATRICULA
                        WHERE codigo_periodo = ?
                        UNION
                        SELECT codigo_estud, cod_anio_Basica
                        FROM dbo.CARRERAXESTUD
                        WHERE codigo_periodo = ?
                    )
                    SELECT
                        c.Cod_AnioBasica,
                        c.Nombre_Basica,
                        c.Estado,
                        c.Abrevia,
                        c.tp_escuela,
                        COUNT(DISTINCT carreras_periodo.codigo_estud) AS total_matriculados
                    FROM carreras_periodo
                    INNER JOIN dbo.CARRERAS c
                      ON c.Cod_AnioBasica = carreras_periodo.cod_anio_Basica
                    GROUP BY c.Cod_AnioBasica, c.Nombre_Basica, c.Estado, c.Abrevia, c.tp_escuela
                    ORDER BY c.Nombre_Basica
                    """,
                    codigo_periodo,
                    codigo_periodo,
                )
            items = [_career_item(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando carreras del periodo: {exc}") from exc


@router.get("/students")
def matricula_acad_students(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    query: Annotated[str, Query(min_length=2)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    del current_user
    search = f"%{query.strip()}%"
    document = f"%{re.sub(r'\\D+', '', query)}%" if re.sub(r"\D+", "", query) else search
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH latest_cxe AS (
                    SELECT *
                    FROM (
                        SELECT
                            cxe.codigo_estud,
                            cxe.cod_anio_Basica,
                            cxe.codigo_periodo,
                            COUNT(*) OVER (PARTITION BY cxe.codigo_estud, cxe.cod_anio_Basica, cxe.codigo_periodo) AS materias_actuales,
                            ROW_NUMBER() OVER (
                                PARTITION BY cxe.codigo_estud
                                ORDER BY
                                    COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC,
                                    TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                                    TRY_CONVERT(int, cxe.Num_Matricula) DESC
                            ) AS rn
                        FROM dbo.CARRERAXESTUD cxe
                    ) ranked
                    WHERE rn = 1
                )
                SELECT TOP ({limit})
                    d.codigo_estud,
                    d.Cedula_Est,
                    d.Apellidos_nombre,
                    d.Estado,
                    COALESCE(NULLIF(TRY_CONVERT(varchar(100), d.correo), ''), NULLIF(TRY_CONVERT(varchar(100), ce.CorreoPersonal), '')) AS correo,
                    COALESCE(NULLIF(TRY_CONVERT(varchar(100), ce.CorreoIntec), ''), NULLIF(TRY_CONVERT(varchar(100), d.correointec), '')) AS correointec,
                    x.cod_anio_Basica,
                    x.codigo_periodo,
                    x.materias_actuales,
                    c.Nombre_Basica,
                    p.Detalle_Periodo
                FROM dbo.DATOS_ESTUD d
                LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud = d.codigo_estud
                LEFT JOIN latest_cxe x ON x.codigo_estud = d.codigo_estud
                LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = x.cod_anio_Basica
                LEFT JOIN dbo.PERIODO p ON p.cod_periodo = x.codigo_periodo
                WHERE d.Apellidos_nombre LIKE ?
                   OR d.Cedula_Est LIKE ?
                   OR TRY_CONVERT(varchar(50), d.codigo_estud) = ?
                ORDER BY d.Apellidos_nombre
                """,
                search,
                document,
                query.strip(),
            )
            items = [_student_item(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error buscando estudiantes: {exc}") from exc


@router.get("/pensum")
def matricula_acad_pensum(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    cod_anio_basica: Annotated[int, Query(description="Carrera a consultar")],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dbo.CARRERAS WHERE Cod_AnioBasica = ?", cod_anio_basica)
            if int(cursor.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=404, detail="No se encontro la carrera seleccionada")
            items = list(_fetch_pensum_by_code(cursor, cod_anio_basica).values())
        return {"total": len(items), "items": items}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando pensum: {exc}") from exc


@router.get("/docentes")
def matricula_acad_docentes(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    query: str = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    validar_usuario: Annotated[bool, Query(description="Validar que exista usuario vinculado")] = False,
) -> dict[str, Any]:
    del current_user
    search = f"%{query.strip()}%"
    document = f"%{re.sub(r'\\D+', '', query)}%" if re.sub(r"\D+", "", query) else search
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(255), u.login), N''),
                        NULLIF(TRY_CONVERT(nvarchar(255), d.correo), N''),
                        TRY_CONVERT(nvarchar(255), d.correop)
                    ) AS login,
                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), u.tipo_usuario), N''), N'DOCENTE') AS tipo_usuario,
                    TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre), N''),
                        TRY_CONVERT(nvarchar(4000), u.Descripcion)
                    ) AS Descripcion,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correop) AS correop,
                    TRY_CONVERT(nvarchar(100), d.telefono) AS telefono,
                    TRY_CONVERT(nvarchar(100), d.movil) AS movil,
                    TRY_CONVERT(nvarchar(4000), d.Perfil) AS Perfil,
                    TRY_CONVERT(nvarchar(255), d.TipoDocente) AS TipoDocente,
                    TRY_CONVERT(nvarchar(4000), d.nombreUnidadAcademica) AS nombreUnidadAcademica,
                    TRY_CONVERT(nvarchar(255), d.nivelFormacion) AS nivelFormacion,
                    TRY_CONVERT(nvarchar(4000), d.tercernivel) AS tercernivel,
                    TRY_CONVERT(nvarchar(4000), d.cuartonivel) AS cuartonivel,
                    CASE WHEN u.Codigo_Usuario IS NULL THEN 0 ELSE 1 END AS usuario_validado,
                    stats.total_matriculas_docente,
                    stats.total_carreras_docente,
                    stats.total_materias_docente,
                    stats.ultimo_periodo_docente
                FROM dbo.DATOSDOCENTE d
                OUTER APPLY (
                    SELECT TOP (1) u.*
                    FROM dbo.USUARIOS u
                    WHERE TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
                    ORDER BY
                        CASE WHEN NULLIF(TRY_CONVERT(nvarchar(100), u.Estado), N'') IS NULL THEN 1 ELSE 0 END,
                        TRY_CONVERT(nvarchar(255), u.login)
                ) u
                OUTER APPLY (
                    SELECT
                        COUNT(*) AS total_matriculas_docente,
                        COUNT(DISTINCT TRY_CONVERT(int, cxd.cod_Anio_Basica)) AS total_carreras_docente,
                        COUNT(DISTINCT TRY_CONVERT(int, cxd.codigo_materia)) AS total_materias_docente,
                        MAX(TRY_CONVERT(int, cxd.codigo_periodo)) AS ultimo_periodo_docente
                    FROM dbo.CARRERAXDOCENTE cxd
                    WHERE TRY_CONVERT(int, cxd.codigo_doc) = TRY_CONVERT(int, d.codigo_doc)
                ) stats
                WHERE (
                       ? = N''
                    OR TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correo) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correop) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), d.cedula_doc) LIKE ?
                    OR TRY_CONVERT(varchar(50), d.codigo_doc) = ?
                )
                  AND (? = 0 OR u.Codigo_Usuario IS NOT NULL)
                ORDER BY
                    TRY_CONVERT(nvarchar(4000), d.apellidos_nombre),
                    TRY_CONVERT(nvarchar(255), d.correo)
                """,
                query.strip(),
                search,
                search,
                search,
                document,
                query.strip(),
                1 if validar_usuario else 0,
            )
            items = [_teacher_item(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando docentes: {exc}") from exc


@router.get("/docentes/materias-unicas")
def matricula_acad_teacher_unique_subjects(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int, Query(description="Periodo a consultar")],
    buscar: Annotated[str | None, Query(description="Codigo o nombre de materia")] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 120,
) -> dict[str, Any]:
    del current_user
    search = _clean(buscar)
    search_like = f"%{search}%" if search else None
    top_limit = max(50, min(int(limite or 120) * 20, 5000))
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH cxe_rows AS (
                    SELECT
                        TRY_CONVERT(int, cxe.codigo_estud) AS codigo_estud,
                        TRY_CONVERT(int, cxe.cod_anio_Basica) AS cod_anio_basica,
                        TRY_CONVERT(int, cxe.codigo_materia) AS codigo_materia
                    FROM dbo.CARRERAXESTUD cxe
                    WHERE TRY_CONVERT(int, cxe.codigo_periodo) = ?
                )
                SELECT TOP ({top_limit})
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N''),
                        TRY_CONVERT(nvarchar(100), p.codigo_materia)
                    ) AS cod_materia,
                    TRY_CONVERT(varchar(50), p.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(varchar(50), p.Cod_AnioBasica) AS Cod_AnioBasica,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS Nomb_Materia,
                    TRY_CONVERT(int, p.Semestre) AS Semestre,
                    TRY_CONVERT(float, p.Creditos) AS Creditos,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS Nombre_Basica,
                    COUNT(DISTINCT cxe.codigo_estud) AS total_estudiantes
                FROM cxe_rows cxe
                INNER JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = cxe.cod_anio_basica
                 AND TRY_CONVERT(int, p.codigo_materia) = cxe.codigo_materia
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, p.Cod_AnioBasica)
                WHERE (
                    ? IS NULL
                    OR TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), p.cod_materia) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), p.codigo_materia) LIKE ?
                )
                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N''),
                        TRY_CONVERT(nvarchar(100), p.codigo_materia)
                    ),
                    TRY_CONVERT(varchar(50), p.codigo_materia),
                    TRY_CONVERT(varchar(50), p.Cod_AnioBasica),
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia),
                    TRY_CONVERT(int, p.Semestre),
                    TRY_CONVERT(float, p.Creditos),
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica)
                ORDER BY
                    TRY_CONVERT(int, p.Semestre),
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia),
                    TRY_CONVERT(varchar(50), p.codigo_materia)
                """,
                codigo_periodo,
                search_like,
                search_like,
                search_like,
                search_like,
            )
            rows = cursor.fetchall()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            common_code = _clean(row.cod_materia)
            if not common_code:
                continue
            bucket = grouped.get(common_code)
            if not bucket:
                bucket = {
                    "cod_materia": common_code,
                    "nombre_materia": _clean(row.Nomb_Materia),
                    "semestre": _int_value(row.Semestre),
                    "niveles": [],
                    "creditos": _number_value(row.Creditos),
                    "codigo_materias": [],
                    "carreras": [],
                    "total_estudiantes": 0,
                }
                grouped[common_code] = bucket
            semester = _int_value(row.Semestre)
            if semester is not None and semester not in bucket["niveles"]:
                bucket["niveles"].append(semester)
            codigo_materia = str(row.codigo_materia or "")
            if codigo_materia and codigo_materia not in bucket["codigo_materias"]:
                bucket["codigo_materias"].append(codigo_materia)
            career_code = str(row.Cod_AnioBasica or "")
            if career_code and not any(item["cod_anio_basica"] == career_code for item in bucket["carreras"]):
                bucket["carreras"].append(
                    {
                        "cod_anio_basica": career_code,
                        "nombre_carrera": _clean(row.Nombre_Basica) or career_code,
                    }
                )
            bucket["total_estudiantes"] += int(row.total_estudiantes or 0)

        for bucket in grouped.values():
            bucket["niveles"].sort()
            if bucket["semestre"] is None and bucket["niveles"]:
                bucket["semestre"] = bucket["niveles"][0]

        items = list(grouped.values())[:limite]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando materias unicas de docentes: {exc}") from exc


@router.get("/docentes/estados/catalogo")
def matricula_acad_teacher_state_catalog(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(50), IDESTADO) AS codigo,
                    TRY_CONVERT(nvarchar(255), ESTADO) AS nombre
                FROM dbo.ESTADO
                WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))), N'') IS NOT NULL
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) IN (N'A', N'P')
                ORDER BY
                    CASE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))))
                        WHEN 'A' THEN 1
                        WHEN 'P' THEN 2
                        ELSE 5
                    END,
                    TRY_CONVERT(nvarchar(255), ESTADO)
                """
            )
            items = [
                {
                    "codigo": _clean(row.codigo).upper(),
                    "nombre": _clean(row.nombre) or _clean(row.codigo).upper(),
                }
                for row in cursor.fetchall()
            ]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estados de docentes: {exc}") from exc


@router.get("/docentes/estados")
def matricula_acad_teacher_states(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    query: str = "",
    estado: str = "",
    validar_usuario: Annotated[bool, Query(description="Mostrar solo docentes con usuario vinculado")] = False,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
) -> dict[str, Any]:
    del current_user
    query_value = query.strip()
    estado_value = _clean(estado).upper()
    if estado_value and estado_value not in _VALID_TEACHER_STATE_CODES:
        raise HTTPException(status_code=400, detail="Estado docente permitido: A (Activo) o P (Inactivo).")
    search = f"%{query_value}%"
    document = f"%{re.sub(r'\\D+', '', query_value)}%" if re.sub(r"\D+", "", query_value) else search
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(varchar(50), u.Codigo_Usuario) AS Codigo_Usuario,
                    TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula_doc,
                    TRY_CONVERT(nvarchar(100), u.cedula) AS cedula_usuario,
                    TRY_CONVERT(nvarchar(255), u.login) AS login,
                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), u.tipo_usuario), N''), N'DOCENTE') AS tipo_usuario,
                    TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
                    TRY_CONVERT(nvarchar(255), est.ESTADO) AS estado_nombre,
                    TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) AS apellidos_nombre,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correop) AS correop,
                    TRY_CONVERT(nvarchar(100), d.telefono) AS telefono,
                    TRY_CONVERT(nvarchar(100), d.movil) AS movil,
                    TRY_CONVERT(nvarchar(4000), d.Perfil) AS Perfil,
                    TRY_CONVERT(nvarchar(255), d.TipoDocente) AS TipoDocente,
                    TRY_CONVERT(nvarchar(4000), d.nombreUnidadAcademica) AS nombreUnidadAcademica,
                    TRY_CONVERT(nvarchar(255), d.nivelFormacion) AS nivelFormacion,
                    TRY_CONVERT(nvarchar(4000), d.tercernivel) AS tercernivel,
                    TRY_CONVERT(nvarchar(4000), d.cuartonivel) AS cuartonivel,
                    d.fechaIngresoIES,
                    TRY_CONVERT(nvarchar(100), d.relacionLaboralIESId) AS relacionLaboralIESId,
                    TRY_CONVERT(nvarchar(100), d.tiempoDedicacionId) AS tiempoDedicacionId,
                    CASE WHEN u.Codigo_Usuario IS NULL THEN 0 ELSE 1 END AS usuario_validado,
                    stats.total_matriculas_docente,
                    stats.total_carreras_docente,
                    stats.total_materias_docente,
                    stats.ultimo_periodo_docente
                FROM dbo.USUARIOS u
                FULL OUTER JOIN dbo.DATOSDOCENTE d
                  ON (
                        TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
                     OR LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))) =
                        LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.cedula_doc)))
                  )
                LEFT JOIN dbo.ESTADO est
                  ON UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), est.IDESTADO)))) =
                     UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), u.Estado))))
                OUTER APPLY (
                    SELECT
                        COUNT(*) AS total_matriculas_docente,
                        COUNT(DISTINCT TRY_CONVERT(int, cxd.cod_Anio_Basica)) AS total_carreras_docente,
                        COUNT(DISTINCT TRY_CONVERT(int, cxd.codigo_materia)) AS total_materias_docente,
                        MAX(TRY_CONVERT(int, cxd.codigo_periodo)) AS ultimo_periodo_docente
                    FROM dbo.CARRERAXDOCENTE cxd
                    WHERE TRY_CONVERT(int, cxd.codigo_doc) =
                          TRY_CONVERT(int, COALESCE(d.codigo_doc, u.Codigo_Usuario))
                ) stats
                WHERE (
                       ? = N''
                    OR TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), u.cedula) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correo) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), d.correop) LIKE ?
                    OR TRY_CONVERT(nvarchar(255), u.login) LIKE ?
                    OR TRY_CONVERT(nvarchar(4000), u.Descripcion) LIKE ?
                    OR TRY_CONVERT(nvarchar(100), d.cedula_doc) LIKE ?
                    OR TRY_CONVERT(varchar(50), d.codigo_doc) = ?
                    OR TRY_CONVERT(varchar(50), u.Codigo_Usuario) = ?
                )
                  AND (
                    ? = N''
                    OR UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), u.Estado)))) = ?
                  )
                  AND (u.Codigo_Usuario IS NULL OR COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1)
                  AND (? = 0 OR u.Codigo_Usuario IS NOT NULL)
                ORDER BY
                    CASE WHEN u.Codigo_Usuario IS NULL THEN 1 ELSE 0 END,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre))), N''),
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), u.login))), N''),
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))), N'')
                    ),
                    TRY_CONVERT(nvarchar(255), d.correo)
                """,
                query_value,
                search,
                document,
                search,
                search,
                search,
                search,
                document,
                query_value,
                query_value,
                estado_value,
                estado_value,
                1 if validar_usuario else 0,
            )
            items = [_estado_docente_item(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estados de docentes: {exc}") from exc


@router.post("/docentes/estado")
def matricula_acad_update_teacher_state(
    payload: AcademicTeacherStatePayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    estado_codigo = _clean(payload.estado_codigo).upper()
    if estado_codigo not in _VALID_TEACHER_STATE_CODES:
        raise HTTPException(status_code=400, detail="Solo se permite Activo (A) o Inactivo (P) para docentes.")
    codigo_usuario = payload.codigo_usuario or payload.codigo_doc
    if not codigo_usuario:
        raise HTTPException(status_code=400, detail="Selecciona un usuario docente para actualizar el estado.")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    TRY_CONVERT(nvarchar(50), IDESTADO) AS codigo,
                    TRY_CONVERT(nvarchar(255), ESTADO) AS nombre
                FROM dbo.ESTADO
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) = ?
                """,
                estado_codigo,
            )
            state = cursor.fetchone()
            if not state:
                raise HTTPException(status_code=400, detail="Estado no existe en dbo.ESTADO")

            cursor.execute(
                """
                SELECT TOP (1) TRY_CONVERT(varchar(50), Codigo_Usuario) AS Codigo_Usuario
                FROM dbo.USUARIOS
                WHERE TRY_CONVERT(int, Codigo_Usuario) = ?
                  AND COALESCE(TRY_CONVERT(int, tipo_usuario), 2) <> 1
                """,
                codigo_usuario,
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="El usuario docente no existe en USUARIOS")

            cursor.execute(
                """
                UPDATE dbo.USUARIOS
                SET Estado = ?
                WHERE TRY_CONVERT(int, Codigo_Usuario) = ?
                """,
                estado_codigo,
                codigo_usuario,
            )
            teacher = _fetch_estado_docente_by_code(cursor, codigo_usuario)
            conn.commit()
        return {
            "ok": True,
            "message": f"Estado del docente actualizado a {_clean(state.nombre) or estado_codigo}.",
            "estado": {
                "codigo": estado_codigo,
                "nombre": _clean(state.nombre) or estado_codigo,
            },
            "docente": teacher,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error actualizando estado del docente: {exc}") from exc


@router.get("/docentes/matriculas")
def matricula_acad_teacher_enrollments(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int, Query(description="Periodo a consultar")],
    cod_anio_basica: Annotated[list[int] | None, Query(description="Carrera(s) a consultar")] = None,
    codigo_materia: Annotated[str | None, Query(description="Materia opcional")] = None,
    paralelo: Annotated[str | None, Query(description="Paralelo opcional")] = None,
    semestre: Annotated[int | None, Query(description="Nivel/Semestre opcional")] = None,
) -> dict[str, Any]:
    del current_user
    parallel = paralelo.strip().upper() if paralelo else None
    subject_filter = _clean(codigo_materia).upper() if codigo_materia else None
    career_codes = sorted({int(code) for code in (cod_anio_basica or []) if int(code) > 0})
    career_condition = ""
    if career_codes:
        career_condition = f"TRY_CONVERT(int, cxd.cod_Anio_Basica) IN ({', '.join('?' for _ in career_codes)}) AND"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    TRY_CONVERT(varchar(50), cxd.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(varchar(50), cxd.cod_Anio_Basica) AS cod_Anio_Basica,
                    TRY_CONVERT(varchar(50), cxd.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(nvarchar(100), cxd.Paralelo) AS Paralelo,
                    TRY_CONVERT(varchar(50), cxd.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(int, cxd.Cod_Jornada) AS Cod_Jornada,
                    TRY_CONVERT(int, cxd.estadoMoodleDoc) AS estadoMoodleDoc,
                    COALESCE(TRY_CONVERT(nvarchar(100), d.cedula_doc), TRY_CONVERT(nvarchar(100), u.cedula)) AS cedula,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(255), u.login), N''),
                        NULLIF(TRY_CONVERT(nvarchar(255), d.correo), N''),
                        TRY_CONVERT(nvarchar(255), d.correop)
                    ) AS login,
                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), u.tipo_usuario), N''), N'DOCENTE') AS tipo_usuario,
                    TRY_CONVERT(nvarchar(100), u.Estado) AS Estado,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre), N''),
                        TRY_CONVERT(nvarchar(4000), u.Descripcion)
                    ) AS Descripcion,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correop) AS correop,
                    TRY_CONVERT(nvarchar(100), d.telefono) AS telefono,
                    TRY_CONVERT(nvarchar(100), d.movil) AS movil,
                    TRY_CONVERT(nvarchar(4000), d.Perfil) AS Perfil,
                    TRY_CONVERT(nvarchar(255), d.TipoDocente) AS TipoDocente,
                    TRY_CONVERT(nvarchar(4000), d.nombreUnidadAcademica) AS nombreUnidadAcademica,
                    TRY_CONVERT(nvarchar(255), d.nivelFormacion) AS nivelFormacion,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS Nomb_Materia,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS Nombre_Basica,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS Detalle_Periodo
                FROM dbo.CARRERAXDOCENTE cxd
                LEFT JOIN dbo.DATOSDOCENTE d
                  ON TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, cxd.codigo_doc)
                LEFT JOIN dbo.USUARIOS u
                  ON TRY_CONVERT(varchar(50), u.Codigo_Usuario) = TRY_CONVERT(varchar(50), cxd.codigo_doc)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                LEFT JOIN dbo.CARRERAS c ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                LEFT JOIN dbo.PERIODO pe ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                WHERE {career_condition}
                  TRY_CONVERT(int, cxd.codigo_periodo) = ?
                  AND (
                    ? IS NULL
                    OR TRY_CONVERT(nvarchar(100), cxd.codigo_materia) = ?
                    OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p.cod_materia), N'')))) = ?
                  )
                  AND (? IS NULL OR TRY_CONVERT(int, p.Semestre) = ?)
                  AND (
                    ? IS NULL
                    OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), cxd.Paralelo), N'')))) = ?
                  )
                ORDER BY
                    TRY_CONVERT(int, p.Semestre),
                    TRY_CONVERT(int, p.Orden),
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia),
                    TRY_CONVERT(nvarchar(100), cxd.Paralelo),
                    COALESCE(
                        TRY_CONVERT(nvarchar(4000), d.apellidos_nombre),
                        TRY_CONVERT(nvarchar(4000), u.Descripcion)
                    )
                """,
                *career_codes,
                codigo_periodo,
                subject_filter,
                subject_filter,
                subject_filter,
                semestre,
                semestre,
                parallel,
                parallel,
            )
            items = [_teacher_enrollment_item(row) for row in cursor.fetchall()]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando matriculas de docentes: {exc}") from exc


@router.get("/docentes/paralelos")
def matricula_acad_teacher_parallel_options(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int, Query(description="Periodo a consultar")],
    cod_anio_basica: Annotated[list[int] | None, Query(description="Carrera(s) a consultar")] = None,
    codigo_materia: Annotated[str | None, Query(description="Materia opcional")] = None,
    semestre: Annotated[int | None, Query(description="Nivel/Semestre opcional")] = None,
) -> dict[str, Any]:
    del current_user
    subject_filter = _clean(codigo_materia).upper() if codigo_materia else None
    career_codes = sorted({int(code) for code in (cod_anio_basica or []) if int(code) > 0})
    career_condition = ""
    if career_codes:
        career_condition = f"AND TRY_CONVERT(int, cxe.cod_anio_Basica) IN ({', '.join('?' for _ in career_codes)})"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH parallel_catalog AS (
                    SELECT DISTINCT
                        UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), paralelo)))) AS paralelo
                    FROM dbo.PARALELOS
                    WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), paralelo))), N'') IS NOT NULL
                    UNION
                    SELECT DISTINCT
                        UPPER(
                            LTRIM(
                                RTRIM(
                                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                                )
                            )
                        ) AS paralelo
                    FROM dbo.CARRERAXESTUD cxe
                    WHERE TRY_CONVERT(int, cxe.codigo_periodo) = ?
                      AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), cxe.paralelo))), N'') IS NOT NULL
                ),
                cxe_rows AS (
                    SELECT *
                    FROM (
                        SELECT
                            cxe.codigo_estud,
                            cxe.cod_anio_Basica,
                            cxe.codigo_periodo,
                            cxe.codigo_materia,
                            UPPER(
                                LTRIM(
                                    RTRIM(
                                        COALESCE(
                                            NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''),
                                            N'SIN PARALELO'
                                        )
                                    )
                                )
                            ) AS paralelo,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    TRY_CONVERT(int, cxe.codigo_estud),
                                    TRY_CONVERT(int, cxe.cod_anio_Basica),
                                    TRY_CONVERT(int, cxe.codigo_periodo),
                                    TRY_CONVERT(int, cxe.codigo_materia),
                                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                                ORDER BY
                                    COALESCE(TRY_CONVERT(int, cxe.num), 0) DESC,
                                    COALESCE(TRY_CONVERT(int, cxe.Num_Reg_Mat), 0) DESC,
                                    COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC
                            ) AS rn
                        FROM dbo.CARRERAXESTUD cxe
                        LEFT JOIN dbo.PENSUM p
                          ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                         AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                        WHERE TRY_CONVERT(int, cxe.codigo_periodo) = ?
                          {career_condition}
                          AND (? IS NULL OR TRY_CONVERT(int, p.Semestre) = ?)
                          AND (
                            ? IS NULL
                            OR TRY_CONVERT(nvarchar(100), cxe.codigo_materia) = ?
                            OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p.cod_materia), N'')))) = ?
                          )
                    ) ranked
                    WHERE rn = 1
                ),
                counts_by_parallel AS (
                    SELECT
                        paralelo,
                        COUNT(DISTINCT TRY_CONVERT(varchar(50), codigo_estud)) AS total_estudiantes,
                        COUNT(*) AS total_materias
                    FROM cxe_rows
                    GROUP BY paralelo
                )
                SELECT
                    pc.paralelo,
                    COALESCE(cbp.total_estudiantes, 0) AS total_estudiantes,
                    COALESCE(cbp.total_materias, 0) AS total_materias
                FROM parallel_catalog pc
                LEFT JOIN counts_by_parallel cbp ON cbp.paralelo = pc.paralelo
                ORDER BY
                    CASE WHEN COALESCE(cbp.total_estudiantes, 0) > 0 THEN 0 ELSE 1 END,
                    pc.paralelo
                """,
                codigo_periodo,
                codigo_periodo,
                *career_codes,
                semestre,
                semestre,
                subject_filter,
                subject_filter,
                subject_filter,
            )
            items = [
                {
                    "paralelo": _clean(row.paralelo),
                    "total_estudiantes": int(row.total_estudiantes or 0),
                    "total_materias": int(row.total_materias or 0),
                }
                for row in cursor.fetchall()
            ]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando paralelos matriculados: {exc}") from exc


@router.get("/docentes/estudiantes-paralelo")
def matricula_acad_teacher_parallel_students(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int, Query(description="Periodo a consultar")],
    codigo_materia: Annotated[str, Query(description="Materia a consultar")],
    paralelo: Annotated[str, Query(description="Paralelo a consultar")],
    cod_anio_basica: Annotated[list[int] | None, Query(description="Carrera(s) opcionales")] = None,
    semestre: Annotated[int | None, Query(description="Nivel/Semestre opcional")] = None,
) -> dict[str, Any]:
    del current_user
    subject_filter = _clean(codigo_materia).upper()
    parallel = _clean(paralelo).upper()
    if not subject_filter:
        raise HTTPException(status_code=400, detail="Selecciona una materia")
    if not parallel:
        raise HTTPException(status_code=400, detail="Selecciona un paralelo")

    career_codes = sorted({int(code) for code in (cod_anio_basica or []) if int(code) > 0})
    career_condition = ""
    if career_codes:
        career_condition = f"AND TRY_CONVERT(int, cxe.cod_anio_Basica) IN ({', '.join('?' for _ in career_codes)})"

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH student_rows AS (
                    SELECT
                        cxe.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                TRY_CONVERT(int, cxe.codigo_estud),
                                TRY_CONVERT(int, cxe.cod_anio_Basica),
                                TRY_CONVERT(int, cxe.codigo_periodo),
                                TRY_CONVERT(int, cxe.codigo_materia),
                                COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                            ORDER BY
                                COALESCE(TRY_CONVERT(int, cxe.num), 0) DESC,
                                COALESCE(TRY_CONVERT(int, cxe.Num_Reg_Mat), 0) DESC,
                                COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC
                        ) AS rn
                    FROM dbo.CARRERAXESTUD cxe
                    LEFT JOIN dbo.PENSUM p_filter
                      ON TRY_CONVERT(int, p_filter.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                     AND TRY_CONVERT(int, p_filter.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                    WHERE TRY_CONVERT(int, cxe.codigo_periodo) = ?
                      {career_condition}
                      AND (? IS NULL OR TRY_CONVERT(int, p_filter.Semestre) = ?)
                      AND (
                            TRY_CONVERT(nvarchar(100), cxe.codigo_materia) = ?
                            OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p_filter.cod_materia), N'')))) = ?
                      )
                      AND UPPER(
                            LTRIM(
                                RTRIM(
                                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                                )
                            )
                          ) = ?
                )
                SELECT TOP (1000)
                    TRY_CONVERT(varchar(50), sr.codigo_estud) AS codigo_estud,
                    TRY_CONVERT(nvarchar(100), d.Cedula_Est) AS Cedula_Est,
                    TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre) AS Apellidos_nombre,
                    TRY_CONVERT(nvarchar(100), d.Estado) AS Estado,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correointec) AS correointec,
                    TRY_CONVERT(varchar(50), sr.cod_anio_Basica) AS cod_anio_Basica,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS Nombre_Basica,
                    TRY_CONVERT(varchar(50), sr.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS Detalle_Periodo,
                    TRY_CONVERT(varchar(50), sr.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS Nomb_Materia,
                    TRY_CONVERT(nvarchar(100), sr.paralelo) AS paralelo,
                    TRY_CONVERT(varchar(50), sr.Num_Matricula) AS Num_Matricula,
                    TRY_CONVERT(nvarchar(100), sr.TipoMatricula) AS TipoMatricula,
                    TRY_CONVERT(float, sr.PromedioFinal) AS PromedioFinal
                FROM student_rows sr
                INNER JOIN dbo.DATOS_ESTUD d ON TRY_CONVERT(int, d.codigo_estud) = TRY_CONVERT(int, sr.codigo_estud)
                LEFT JOIN dbo.CARRERAS c ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, sr.cod_anio_Basica)
                LEFT JOIN dbo.PERIODO pe ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, sr.codigo_periodo)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, sr.cod_anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, sr.codigo_materia)
                WHERE sr.rn = 1
                ORDER BY
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica),
                    TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre)
                """,
                codigo_periodo,
                *career_codes,
                semestre,
                semestre,
                subject_filter,
                subject_filter,
                parallel,
            )
            rows = cursor.fetchall()

        items = [
            {
                "codigo_estud": str(row.codigo_estud or ""),
                "cedula": _clean(row.Cedula_Est),
                "nombre_estudiante": _clean(row.Apellidos_nombre),
                "estado_codigo": _clean(row.Estado),
                "correo_personal": _clean(row.correo),
                "correo_intec": _clean(row.correointec),
                "cod_anio_basica": str(row.cod_anio_Basica or ""),
                "nombre_carrera": _clean(row.Nombre_Basica),
                "codigo_periodo": str(row.codigo_periodo or ""),
                "detalle_periodo": _clean(row.Detalle_Periodo),
                "codigo_materia": str(row.codigo_materia or ""),
                "nombre_materia": _clean(row.Nomb_Materia),
                "paralelo": _clean(row.paralelo),
                "num_matricula": str(row.Num_Matricula or ""),
                "tipo_matricula": _clean(row.TipoMatricula),
                "promedio_final": _number_value(row.PromedioFinal),
            }
            for row in rows
        ]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estudiantes del paralelo: {exc}") from exc


@router.get("/docentes/estudiantes")
def matricula_acad_teacher_students(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_doc: Annotated[int, Query(description="Docente a consultar")],
    codigo_periodo: Annotated[list[int] | None, Query(description="Periodo(s) opcionales")] = None,
    cod_anio_basica: Annotated[list[int] | None, Query(description="Carrera(s) opcionales")] = None,
    codigo_materia: Annotated[str | None, Query(description="Materia opcional")] = None,
    paralelo: Annotated[str | None, Query(description="Paralelo opcional")] = None,
) -> dict[str, Any]:
    del current_user
    period_codes = sorted({int(code) for code in (codigo_periodo or []) if int(code) > 0})
    career_codes = sorted({int(code) for code in (cod_anio_basica or []) if int(code) > 0})
    parallel = paralelo.strip().upper() if paralelo else None
    subject_filter = _clean(codigo_materia).upper() if codigo_materia else None
    where_parts = ["TRY_CONVERT(int, cxd.codigo_doc) = ?"]
    params: list[Any] = [codigo_doc]
    if period_codes:
        where_parts.append(f"TRY_CONVERT(int, cxd.codigo_periodo) IN ({', '.join('?' for _ in period_codes)})")
        params.extend(period_codes)
    if career_codes:
        where_parts.append(f"TRY_CONVERT(int, cxd.cod_Anio_Basica) IN ({', '.join('?' for _ in career_codes)})")
        params.extend(career_codes)
    if subject_filter:
        where_parts.append(
            """
            (
                TRY_CONVERT(nvarchar(100), cxd.codigo_materia) = ?
                OR EXISTS (
                    SELECT 1
                    FROM dbo.PENSUM p_filter
                    WHERE TRY_CONVERT(int, p_filter.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                      AND TRY_CONVERT(int, p_filter.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                      AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p_filter.cod_materia), N'')))) = ?
                )
            )
            """
        )
        params.extend([subject_filter, subject_filter])
    if parallel:
        where_parts.append(
            """
            UPPER(
                LTRIM(
                    RTRIM(
                        COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxd.Paralelo), N''), N'SIN PARALELO')
                    )
                )
            ) = ?
            """
        )
        params.append(parallel)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH teacher_assignments AS (
                    SELECT DISTINCT
                        TRY_CONVERT(int, cxd.cod_Anio_Basica) AS cod_anio_basica,
                        TRY_CONVERT(int, cxd.codigo_materia) AS codigo_materia,
                        TRY_CONVERT(int, cxd.codigo_periodo) AS codigo_periodo,
                        UPPER(
                            LTRIM(
                                RTRIM(
                                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxd.Paralelo), N''), N'SIN PARALELO')
                                )
                            )
                        ) AS paralelo
                    FROM dbo.CARRERAXDOCENTE cxd
                    WHERE {' AND '.join(where_parts)}
                ),
                student_rows AS (
                    SELECT
                        cxe.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                TRY_CONVERT(int, cxe.codigo_estud),
                                TRY_CONVERT(int, cxe.cod_anio_Basica),
                                TRY_CONVERT(int, cxe.codigo_periodo),
                                TRY_CONVERT(int, cxe.codigo_materia),
                                COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                            ORDER BY
                                COALESCE(TRY_CONVERT(int, cxe.num), 0) DESC,
                                COALESCE(TRY_CONVERT(int, cxe.Num_Reg_Mat), 0) DESC,
                                COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC
                        ) AS rn
                    FROM dbo.CARRERAXESTUD cxe
                    INNER JOIN teacher_assignments ta
                      ON ta.cod_anio_basica = TRY_CONVERT(int, cxe.cod_anio_Basica)
                     AND ta.codigo_materia = TRY_CONVERT(int, cxe.codigo_materia)
                     AND ta.codigo_periodo = TRY_CONVERT(int, cxe.codigo_periodo)
                     AND ta.paralelo = UPPER(
                            LTRIM(
                                RTRIM(
                                    COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                                )
                            )
                        )
                )
                SELECT TOP (1000)
                    TRY_CONVERT(varchar(50), sr.codigo_estud) AS codigo_estud,
                    TRY_CONVERT(nvarchar(100), d.Cedula_Est) AS Cedula_Est,
                    TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre) AS Apellidos_nombre,
                    TRY_CONVERT(nvarchar(100), d.Estado) AS Estado,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correointec) AS correointec,
                    TRY_CONVERT(varchar(50), sr.cod_anio_Basica) AS cod_anio_Basica,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS Nombre_Basica,
                    TRY_CONVERT(varchar(50), sr.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS Detalle_Periodo,
                    TRY_CONVERT(varchar(50), sr.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS Nomb_Materia,
                    TRY_CONVERT(nvarchar(100), sr.paralelo) AS paralelo,
                    TRY_CONVERT(varchar(50), sr.Num_Matricula) AS Num_Matricula,
                    TRY_CONVERT(nvarchar(100), sr.TipoMatricula) AS TipoMatricula,
                    TRY_CONVERT(float, sr.PromedioFinal) AS PromedioFinal
                FROM student_rows sr
                INNER JOIN dbo.DATOS_ESTUD d ON TRY_CONVERT(int, d.codigo_estud) = TRY_CONVERT(int, sr.codigo_estud)
                LEFT JOIN dbo.CARRERAS c ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, sr.cod_anio_Basica)
                LEFT JOIN dbo.PERIODO pe ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, sr.codigo_periodo)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, sr.cod_anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, sr.codigo_materia)
                WHERE sr.rn = 1
                ORDER BY
                    TRY_CONVERT(int, sr.codigo_periodo) DESC,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica),
                    TRY_CONVERT(nvarchar(100), sr.paralelo),
                    TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre)
                """,
                *params,
            )
            rows = cursor.fetchall()
        items = [
            {
                "codigo_estud": str(row.codigo_estud or ""),
                "cedula": _clean(row.Cedula_Est),
                "nombre_estudiante": _clean(row.Apellidos_nombre),
                "estado_codigo": _clean(row.Estado),
                "correo_personal": _clean(row.correo),
                "correo_intec": _clean(row.correointec),
                "cod_anio_basica": str(row.cod_anio_Basica or ""),
                "nombre_carrera": _clean(row.Nombre_Basica),
                "codigo_periodo": str(row.codigo_periodo or ""),
                "detalle_periodo": _clean(row.Detalle_Periodo),
                "codigo_materia": str(row.codigo_materia or ""),
                "nombre_materia": _clean(row.Nomb_Materia),
                "paralelo": _clean(row.paralelo),
                "num_matricula": str(row.Num_Matricula or ""),
                "tipo_matricula": _clean(row.TipoMatricula),
                "promedio_final": _number_value(row.PromedioFinal),
            }
            for row in rows
        ]
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estudiantes del docente: {exc}") from exc


@router.post("/docentes/matricula")
def matricula_acad_save_teacher_enrollment(
    payload: AcademicTeacherEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _validate_teacher_payload(payload)
            teacher = _ensure_teacher_entities_exist(cursor, payload)
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dbo.CARRERAXDOCENTE
                WHERE TRY_CONVERT(int, codigo_doc) = ?
                  AND TRY_CONVERT(int, cod_Anio_Basica) = ?
                  AND TRY_CONVERT(int, codigo_materia) = ?
                  AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), Paralelo), N'')))) = ?
                  AND TRY_CONVERT(int, codigo_periodo) = ?
                  AND COALESCE(TRY_CONVERT(int, Cod_Jornada), -1) = ?
                """,
                payload.codigo_doc,
                payload.cod_anio_basica,
                payload.codigo_materia,
                payload.paralelo,
                payload.codigo_periodo,
                payload.cod_jornada,
            )
            existing_count = int(cursor.fetchone()[0] or 0)
            students_linked = _link_teacher_to_enrolled_students(
                cursor,
                codigo_doc=payload.codigo_doc,
                cod_anio_basica=payload.cod_anio_basica,
                codigo_materia=payload.codigo_materia,
                codigo_periodo=payload.codigo_periodo,
                paralelo=payload.paralelo,
            )
            if existing_count > 0:
                action = "EXISTENTE"
            else:
                cursor.execute(
                    """
                    INSERT INTO dbo.CARRERAXDOCENTE (
                        codigo_doc, cod_Anio_Basica, codigo_materia, Paralelo,
                        codigo_periodo, Cod_Jornada, estadoMoodleDoc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload.codigo_doc,
                    payload.cod_anio_basica,
                    payload.codigo_materia,
                    payload.paralelo,
                    payload.codigo_periodo,
                    payload.cod_jornada,
                    payload.estado_moodle_doc,
                )
                action = "INSERTADA"
            conn.commit()
        already_exists = action == "EXISTENTE"
        return {
            "ok": not already_exists,
            "already_exists": already_exists,
            "message": (
                "La matricula docente ya existe para la materia, periodo, paralelo y jornada seleccionados."
                if already_exists
                else "Matricula docente guardada correctamente."
            ),
            "action": action,
            "inserted_count": 0 if already_exists else 1,
            "existing_count": existing_count,
            "duplicate_count": max(existing_count - 1, 0),
            "students_linked": students_linked,
            "docente": teacher,
            "criteria": payload.model_dump(),
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error guardando matricula docente: {exc}") from exc


@router.post("/docentes/matricula/materia-unica")
def matricula_acad_save_teacher_unique_subject_enrollment(
    payload: AcademicTeacherUniqueEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _validate_teacher_payload(payload)  # type: ignore[arg-type]
            teacher = _ensure_teacher_entities_exist(cursor, payload)  # type: ignore[arg-type]
            subject_key = _clean(payload.cod_materia).upper()
            if not subject_key:
                raise HTTPException(status_code=400, detail="Selecciona una materia valida")

            cursor.execute(
                """
                SELECT DISTINCT
                    TRY_CONVERT(int, p.Cod_AnioBasica) AS cod_anio_basica,
                    TRY_CONVERT(int, p.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS Nomb_Materia,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS Nombre_Basica
                FROM dbo.CARRERAXESTUD cxe
                INNER JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, p.Cod_AnioBasica)
                WHERE TRY_CONVERT(int, cxe.codigo_periodo) = ?
                  AND UPPER(
                        LTRIM(
                            RTRIM(
                                COALESCE(NULLIF(TRY_CONVERT(nvarchar(100), cxe.paralelo), N''), N'SIN PARALELO')
                            )
                        )
                      ) = ?
                      AND (
                        TRY_CONVERT(nvarchar(100), p.codigo_materia) = ?
                        OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p.cod_materia), N'')))) = ?
                      )
                  AND (? IS NULL OR TRY_CONVERT(int, p.Semestre) = ?)
                ORDER BY
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica),
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia)
                """,
                payload.codigo_periodo,
                payload.paralelo,
                subject_key,
                subject_key,
                payload.semestre,
                payload.semestre,
            )
            targets = cursor.fetchall()
            if not targets:
                raise HTTPException(
                    status_code=404,
                    detail="No se encontraron estudiantes matriculados para esa materia, periodo y paralelo.",
                )

            inserted = 0
            existing = 0
            duplicate_count = 0
            students_linked = 0
            assignments: list[dict[str, Any]] = []
            for target in targets:
                cod_anio_basica = _int_value(target.cod_anio_basica)
                codigo_materia = _int_value(target.codigo_materia)
                if cod_anio_basica is None or codigo_materia is None:
                    continue
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM dbo.CARRERAXDOCENTE
                    WHERE TRY_CONVERT(int, codigo_doc) = ?
                      AND TRY_CONVERT(int, cod_Anio_Basica) = ?
                      AND TRY_CONVERT(int, codigo_materia) = ?
                      AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), Paralelo), N'')))) = ?
                      AND TRY_CONVERT(int, codigo_periodo) = ?
                      AND COALESCE(TRY_CONVERT(int, Cod_Jornada), -1) = ?
                    """,
                    payload.codigo_doc,
                    cod_anio_basica,
                    codigo_materia,
                    payload.paralelo,
                    payload.codigo_periodo,
                    payload.cod_jornada,
                )
                existing_rows = int(cursor.fetchone()[0] or 0)
                if existing_rows > 0:
                    existing += 1
                    duplicate_count += max(existing_rows - 1, 0)
                else:
                    cursor.execute(
                        """
                        INSERT INTO dbo.CARRERAXDOCENTE (
                            codigo_doc, cod_Anio_Basica, codigo_materia, Paralelo,
                            codigo_periodo, Cod_Jornada, estadoMoodleDoc
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        payload.codigo_doc,
                        cod_anio_basica,
                        codigo_materia,
                        payload.paralelo,
                        payload.codigo_periodo,
                        payload.cod_jornada,
                        payload.estado_moodle_doc,
                    )
                    inserted += 1
                students_linked += _link_teacher_to_enrolled_students(
                    cursor,
                    codigo_doc=payload.codigo_doc,
                    cod_anio_basica=cod_anio_basica,
                    codigo_materia=codigo_materia,
                    codigo_periodo=payload.codigo_periodo,
                    paralelo=payload.paralelo,
                )
                assignments.append(
                    {
                        "cod_anio_basica": str(cod_anio_basica),
                        "codigo_materia": str(codigo_materia),
                        "nombre_materia": _clean(target.Nomb_Materia),
                        "nombre_carrera": _clean(target.Nombre_Basica),
                    }
            )
            conn.commit()

        already_exists = inserted == 0 and existing > 0
        return {
            "ok": not already_exists,
            "already_exists": already_exists,
            "message": (
                "La matricula docente ya existe para la materia, periodo, paralelo y jornada seleccionados."
                if already_exists
                else "Matricula docente guardada por materia unica."
            ),
            "action": "EXISTENTE" if already_exists else "INSERTADA" if inserted and not existing else "MIXTA",
            "inserted_count": inserted,
            "updated_count": 0,
            "existing_count": existing,
            "duplicate_count": duplicate_count,
            "students_linked": students_linked,
            "docente": teacher,
            "assignments": assignments,
            "criteria": payload.model_dump(),
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error guardando matricula docente por materia unica: {exc}") from exc


@router.get("/cohort")
def matricula_acad_cohort(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_periodo: Annotated[int, Query(description="Periodo academico a consultar")],
    cod_anio_basica: Annotated[int | None, Query(description="Carrera opcional")] = None,
    paralelo: Annotated[str | None, Query(description="Paralelo opcional")] = None,
) -> dict[str, Any]:
    del current_user
    parallel = paralelo.strip().upper() if paralelo else None
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                WITH cxe_rows AS (
                    SELECT *
                    FROM (
                        SELECT
                            cxe.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    cxe.codigo_estud,
                                    cxe.cod_anio_Basica,
                                    cxe.codigo_periodo,
                                    cxe.codigo_materia,
                                    ISNULL(cxe.paralelo, '')
                                ORDER BY
                                    COALESCE(TRY_CONVERT(int, cxe.num), 0) DESC,
                                    COALESCE(TRY_CONVERT(int, cxe.Num_Reg_Mat), 0) DESC,
                                    COALESCE(TRY_CONVERT(datetime2, cxe.Fecha_Matricula), CAST('19000101' AS datetime2)) DESC
                            ) AS rn
                        FROM dbo.CARRERAXESTUD cxe
                        WHERE cxe.codigo_periodo = ?
                          AND (? IS NULL OR cxe.cod_anio_Basica = ?)
                    ) ranked
                    WHERE rn = 1
                ),
                base_matricula AS (
                    SELECT codigo_estud, cod_anio_Basica, codigo_periodo
                    FROM cxe_rows
                    UNION
                    SELECT cm.codigo_estud, cm.cod_anio_Basica, cm.codigo_periodo
                    FROM dbo.CABECERA_MATRICULA cm
                    WHERE cm.codigo_periodo = ?
                      AND (? IS NULL OR cm.cod_anio_Basica = ?)
                )
                SELECT
                    base.codigo_estud,
                    d.Cedula_Est,
                    d.Apellidos_nombre,
                    d.Estado,
                    COALESCE(NULLIF(TRY_CONVERT(varchar(100), d.correo), ''), NULLIF(TRY_CONVERT(varchar(100), ce.CorreoPersonal), '')) AS correo,
                    COALESCE(NULLIF(TRY_CONVERT(varchar(100), ce.CorreoIntec), ''), NULLIF(TRY_CONVERT(varchar(100), d.correointec), '')) AS correointec,
                    base.cod_anio_Basica,
                    c.Nombre_Basica,
                    base.codigo_periodo,
                    pe.Detalle_Periodo,
                    COALESCE(cm.Num_Matricula, cxe.Num_Matricula) AS Num_Matricula,
                    cxe.paralelo,
                    cxe.NumGrupo,
                    cxe.codigo_materia,
                    pensum.Nomb_Materia,
                    pensum.Semestre,
                    cxe.PromedioFinal,
                    cxe.Promedio,
                    cxe.PromedioAux,
                    cxe.TipoMatricula
                FROM base_matricula base
                INNER JOIN dbo.DATOS_ESTUD d ON d.codigo_estud = base.codigo_estud
                LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud = d.codigo_estud
                LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = base.cod_anio_Basica
                LEFT JOIN dbo.PERIODO pe ON pe.cod_periodo = base.codigo_periodo
                LEFT JOIN dbo.CABECERA_MATRICULA cm
                  ON cm.codigo_estud = base.codigo_estud
                 AND cm.cod_anio_Basica = base.cod_anio_Basica
                 AND cm.codigo_periodo = base.codigo_periodo
                LEFT JOIN cxe_rows cxe
                  ON cxe.codigo_estud = base.codigo_estud
                 AND cxe.cod_anio_Basica = base.cod_anio_Basica
                 AND cxe.codigo_periodo = base.codigo_periodo
                LEFT JOIN dbo.PENSUM pensum
                  ON pensum.Cod_AnioBasica = cxe.cod_anio_Basica
                 AND pensum.codigo_materia = cxe.codigo_materia
                WHERE (? IS NULL OR UPPER(ISNULL(cxe.paralelo, 'SIN PARALELO')) = ?)
                ORDER BY c.Nombre_Basica, ISNULL(cxe.paralelo, 'SIN PARALELO'), d.Apellidos_nombre, pensum.Semestre, pensum.Orden
                """,
                codigo_periodo,
                cod_anio_basica,
                cod_anio_basica,
                codigo_periodo,
                cod_anio_basica,
                cod_anio_basica,
                parallel,
                parallel,
            )
            rows = cursor.fetchall()
        response = _cohort_response(rows)
        response["criteria"] = {
            "codigo_periodo": str(codigo_periodo),
            "cod_anio_basica": str(cod_anio_basica or ""),
            "paralelo": parallel or "",
        }
        return response
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando cohorte academica: {exc}") from exc


@router.get("/students/{codigo_estud}")
def matricula_acad_student_detail(
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
    codigo_estud: int,
    cod_anio_basica: Annotated[int | None, Query()] = None,
    codigo_periodo: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                       d.codigo_estud,
                       d.Cedula_Est,
                       d.Apellidos_nombre,
                       d.Estado,
                       COALESCE(NULLIF(TRY_CONVERT(varchar(100), d.correo), ''), NULLIF(TRY_CONVERT(varchar(100), ce.CorreoPersonal), '')) AS correo,
                       COALESCE(NULLIF(TRY_CONVERT(varchar(100), ce.CorreoIntec), ''), NULLIF(TRY_CONVERT(varchar(100), d.correointec), '')) AS correointec,
                       NULL AS cod_anio_Basica, NULL AS codigo_periodo, 0 AS materias_actuales,
                       NULL AS Nombre_Basica, NULL AS Detalle_Periodo,
                       NULL AS pre_codcarrera, NULL AS pre_codperiodo
                FROM dbo.DATOS_ESTUD d
                LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud = d.codigo_estud
                WHERE d.codigo_estud = ?
                """,
                codigo_estud,
            )
            student_row = cursor.fetchone()
            if not student_row:
                cursor.execute(
                    """
                    SELECT TOP (1)
                        TRY_CONVERT(int, pre.Codestu) AS codigo_estud,
                        TRY_CONVERT(varchar(50), pre.Cedula) AS Cedula_Est,
                        TRY_CONVERT(nvarchar(70), pre.Apellidos_nombre) AS Apellidos_nombre,
                        'A' AS Estado,
                        COALESCE(NULLIF(TRY_CONVERT(varchar(100), pre.correo), ''), NULLIF(TRY_CONVERT(varchar(100), ce.CorreoPersonal), '')) AS correo,
                        NULLIF(TRY_CONVERT(varchar(100), ce.CorreoIntec), '') AS correointec,
                        NULL AS cod_anio_Basica,
                        NULL AS codigo_periodo,
                        0 AS materias_actuales,
                        NULL AS Nombre_Basica,
                        NULL AS Detalle_Periodo,
                        TRY_CONVERT(int, pre.codcarrera) AS pre_codcarrera,
                        TRY_CONVERT(int, pre.codperiodo) AS pre_codperiodo
                    FROM dbo.PREINSCRIPCION pre
                    LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud = TRY_CONVERT(int, pre.Codestu)
                    WHERE TRY_CONVERT(int, pre.Codestu) = ?
                    ORDER BY pre.Fecha_Ingreso DESC
                    """,
                    codigo_estud,
                )
                student_row = cursor.fetchone()
                if not student_row:
                    raise HTTPException(status_code=404, detail="No se encontro el estudiante")

            cursor.execute(
                """
                SELECT
                    cm.codigo_estud,
                    cm.cod_anio_Basica,
                    cm.codigo_periodo,
                    cm.Num_Matricula,
                    cm.fecha_pago,
                    cm.valor,
                    cm.InscripValor,
                    cm.MatriValor,
                    cm.Jornada,
                    cm.codjornada,
                    cm.ControlMatricula,
                    c.Nombre_Basica,
                    p.Detalle_Periodo
                FROM dbo.CABECERA_MATRICULA cm
                LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = cm.cod_anio_Basica
                LEFT JOIN dbo.PERIODO p ON p.cod_periodo = cm.codigo_periodo
                WHERE cm.codigo_estud = ?
                ORDER BY cm.codigo_periodo DESC, cm.cod_anio_Basica
                """,
                codigo_estud,
            )
            cabeceras = [_cabecera_item(row) for row in cursor.fetchall()]

            selected_career = (
                cod_anio_basica
                or _int_value(cabeceras[0]["cod_anio_basica"] if cabeceras else None)
                or _int_value(getattr(student_row, "pre_codcarrera", None))
            )
            selected_period = (
                codigo_periodo
                or _int_value(cabeceras[0]["codigo_periodo"] if cabeceras else None)
                or _int_value(getattr(student_row, "pre_codperiodo", None))
            )

            pensum: list[dict[str, Any]] = []
            current_subjects: list[dict[str, Any]] = []
            if selected_career:
                cursor.execute(
                    """
                    SELECT codigo_materia, cod_materia, Nomb_Materia, Semestre, Creditos, Orden, NumMalla, Horas, tipomateria
                    FROM dbo.PENSUM
                    WHERE Cod_AnioBasica = ?
                    ORDER BY Semestre, Orden, Nomb_Materia
                    """,
                    selected_career,
                )
                pensum = [_subject_item(row) for row in cursor.fetchall()]
            if selected_career and selected_period:
                cursor.execute(
                    """
                    SELECT
                        cxe.codigo_materia,
                        p.Nomb_Materia,
                        p.Semestre,
                        p.Creditos,
                        cxe.Num_Creditos,
                        cxe.paralelo,
                        cxe.NumGrupo,
                        cxe.Num_Matricula,
                        cxe.Fecha_Matricula,
                        cxe.TipoMatricula,
                        cxe.ControlMatricula,
                        CASE
                            WHEN cxe.Promedio IS NOT NULL OR cxe.PromedioFinal IS NOT NULL OR cxe.Recuperacion IS NOT NULL
                              OR cxe.P1Tareas IS NOT NULL OR cxe.P1Proyectos IS NOT NULL OR cxe.P1Examen IS NOT NULL
                              OR cxe.P2Tareas IS NOT NULL OR cxe.P2Proyectos IS NOT NULL OR cxe.P2Examen IS NOT NULL
                              OR cxe.P3Tareas IS NOT NULL OR cxe.P3Proyectos IS NOT NULL OR cxe.P3Examen IS NOT NULL
                            THEN 1 ELSE 0 END AS tiene_notas
                    FROM dbo.CARRERAXESTUD cxe
                    LEFT JOIN dbo.PENSUM p
                      ON p.Cod_AnioBasica = cxe.cod_anio_Basica
                     AND p.codigo_materia = cxe.codigo_materia
                    WHERE cxe.codigo_estud = ?
                      AND cxe.cod_anio_Basica = ?
                      AND cxe.codigo_periodo = ?
                    ORDER BY p.Semestre, p.Orden, p.Nomb_Materia
                    """,
                    codigo_estud,
                    selected_career,
                    selected_period,
                )
                current_subjects = [_current_subject_item(row) for row in cursor.fetchall()]

        student = _student_item(student_row)
        selected_cabecera = next(
            (
                cabecera
                for cabecera in cabeceras
                if _int_value(cabecera.get("cod_anio_basica")) == selected_career
                and _int_value(cabecera.get("codigo_periodo")) == selected_period
            ),
            cabeceras[0] if cabeceras else None,
        )
        if selected_cabecera:
            student["carrera_actual"] = selected_cabecera.get("carrera") or student.get("carrera_actual") or ""
            student["cod_anio_basica_actual"] = selected_cabecera.get("cod_anio_basica") or student.get("cod_anio_basica_actual") or ""
            student["periodo_actual"] = selected_cabecera.get("codigo_periodo") or student.get("periodo_actual") or ""
            student["detalle_periodo_actual"] = selected_cabecera.get("periodo") or student.get("detalle_periodo_actual") or ""

        return {
            "student": student,
            "selected": {
                "cod_anio_basica": str(selected_career or ""),
                "codigo_periodo": str(selected_period or ""),
            },
            "cabeceras": cabeceras,
            "pensum": pensum,
            "materias_actuales": current_subjects,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando detalle de matricula: {exc}") from exc


@router.post("/preview")
def matricula_acad_preview(
    payload: AcademicEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            return _preview_with_cursor(cursor, payload)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando vista previa: {exc}") from exc


@router.post("/bulk/preview")
def matricula_acad_bulk_preview(
    payload: AcademicBulkEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            return _bulk_preview_with_cursor(cursor, payload)
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando vista previa masiva: {exc}") from exc


@router.post("/bulk/save")
def matricula_acad_bulk_save(
    payload: AcademicBulkEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    today = date.today()
    user_code = (current_user.login or "APP")[:10]
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            preview = _bulk_preview_with_cursor(cursor, payload)
            pensum_by_code = _fetch_pensum_by_code(cursor, payload.cod_anio_basica)
            source_students = _fetch_bulk_source_students(cursor, payload)
            career_name = _fetch_career_name(cursor, payload.cod_anio_basica)
            audit_id = _create_academic_audit_header(cursor, payload, user_code, preview)
            audited_successful = _fetch_audited_successful_subjects(cursor, payload)
            target_levels = {pensum_by_code.get(code, {}).get("semestre") for code in payload.materia_codes}
            target_levels.discard(None)
            target_level = int(next(iter(target_levels))) if len(target_levels) == 1 else None
            summary = {
                "estudiantes_procesados": 0,
                "inserted": 0,
                "updated": 0,
                "removed": 0,
                "blocked_by_grades": 0,
                "blocked_by_prerequisite": int(preview["summary"].get("bloqueadas_por_prerrequisito", 0) or 0),
                "blocked_by_repetition": 0,
                "skipped_students": 0,
                "already_audited": 0,
                "already_enrolled_students": 0,
                "existing_skipped": 0,
            }
            consecutive_rules = _fetch_consecutive_rules(cursor, payload)
            detail_items: list[dict[str, Any]] = []
            for source_student in source_students:
                progress = _fetch_bulk_student_progress(cursor, payload, source_student)
                nivel_origen = _int_value(progress.get("nivel_actual"))
                target_status = _fetch_target_enrollment_status(
                    cursor,
                    int(source_student["codigo_estud"]),
                    payload.cod_anio_basica,
                    payload.target_codigo_periodo,
                )
                if target_status["existe"]:
                    summary["skipped_students"] += 1
                    summary["already_enrolled_students"] += 1
                    summary["existing_skipped"] += int(target_status["materias"] or 0)
                    for code in payload.materia_codes:
                        subject = pensum_by_code.get(int(code), {})
                        _insert_academic_audit_detail(
                            cursor,
                            audit_id,
                            source_student,
                            payload,
                            career_name,
                            int(code),
                            subject.get("nombre_materia") or "",
                            nivel_origen,
                            target_level,
                            None,
                            "YA_MATRICULADO",
                            "El estudiante ya tiene matricula en la carrera y periodo destino; no se generaron registros duplicados",
                            False,
                            None,
                        )
                    if len(detail_items) < 20:
                        detail_items.append(
                            {
                                "codigo_estud": str(source_student["codigo_estud"]),
                                "nombre_estudiante": source_student["nombre_estudiante"],
                                "paralelo": source_student.get("paralelo") or payload.paralelo_default,
                                "num_matricula": "",
                                "inserted": 0,
                                "updated": 0,
                                "existing_skipped": int(target_status["materias"] or 0),
                                "blocked_by_prerequisite": 0,
                                "blocked_by_repetition": 0,
                                "already_audited": 0,
                                "already_enrolled": True,
                            }
                        )
                    continue
                allowed_codes, blocked_subjects = _bulk_allowed_subjects(
                    cursor,
                    payload,
                    source_student,
                    consecutive_rules,
                    pensum_by_code,
                )
                pending_codes: list[int] = []
                blocked_attempt_codes: list[int] = []
                existing_target = _fetch_target_period_subjects(cursor, payload, source_student, allowed_codes)
                existing_codes = sorted(existing_target)
                already_audited = 0
                for code in allowed_codes:
                    if int(code) in existing_target:
                        continue
                    audit_key = (int(source_student["codigo_estud"]), int(code))
                    if audit_key in audited_successful:
                        already_audited += 1
                        continue
                    next_attempt = _next_subject_matricula(
                        cursor,
                        int(source_student["codigo_estud"]),
                        payload.cod_anio_basica,
                        int(code),
                    )
                    if next_attempt > 3:
                        blocked_attempt_codes.append(code)
                        continue
                    pending_codes.append(code)
                summary["existing_skipped"] += len(existing_codes)
                summary["already_audited"] += already_audited
                summary["blocked_by_repetition"] += len(blocked_attempt_codes)
                for blocked_subject in blocked_subjects:
                    code = int(blocked_subject["codigo_materia"])
                    subject = pensum_by_code.get(code, {})
                    _insert_academic_audit_detail(
                        cursor,
                        audit_id,
                        source_student,
                        payload,
                        career_name,
                        code,
                        subject.get("nombre_materia") or "",
                        nivel_origen,
                        target_level,
                        None,
                        "BLOQUEADA_PRERREQ",
                        blocked_subject.get("motivo") or "Materia bloqueada por prerrequisito",
                        False,
                        None,
                    )
                for code in blocked_attempt_codes:
                    subject = pensum_by_code.get(code, {})
                    _insert_academic_audit_detail(
                        cursor,
                        audit_id,
                        source_student,
                        payload,
                        career_name,
                        int(code),
                        subject.get("nombre_materia") or "",
                        nivel_origen,
                        target_level,
                        4,
                        "BLOQUEADA_NUM_MAT",
                        "La materia supera el tercer numero de matricula permitido",
                        False,
                        None,
                    )
                for code in existing_codes:
                    subject = pensum_by_code.get(code, {})
                    _insert_academic_audit_detail(
                        cursor,
                        audit_id,
                        source_student,
                        payload,
                        career_name,
                        int(code),
                        subject.get("nombre_materia") or "",
                        nivel_origen,
                        target_level,
                        existing_target.get(int(code)),
                        "EXISTENTE",
                        "Materia ya existe en el periodo destino; no se realizo ningun cambio",
                        False,
                        None,
                    )
                if not pending_codes:
                    summary["skipped_students"] += 1
                    if len(detail_items) < 20:
                        detail_items.append(
                            {
                                "codigo_estud": str(source_student["codigo_estud"]),
                                "nombre_estudiante": source_student["nombre_estudiante"],
                                "paralelo": source_student.get("paralelo") or payload.paralelo_default,
                                "num_matricula": "",
                                "inserted": 0,
                                "updated": 0,
                                "existing_skipped": len(existing_codes),
                                "blocked_by_prerequisite": len(blocked_subjects),
                                "blocked_by_repetition": len(blocked_attempt_codes),
                                "already_audited": already_audited,
                            }
                        )
                    continue
                student_payload = _bulk_student_payload(source_student, payload, pending_codes)
                result = _save_enrollment_with_cursor(cursor, student_payload, user_code, today)
                summary["estudiantes_procesados"] += 1
                summary["inserted"] += int(result["inserted"] or 0)
                summary["updated"] += int(result["updated"] or 0)
                summary["existing_skipped"] += int(result.get("existing_skipped", 0) or 0)
                summary["removed"] += int(result["removed"] or 0)
                summary["blocked_by_grades"] += int(result["blocked_by_grades"] or 0)
                summary["blocked_by_repetition"] += int(result["blocked_by_repetition"] or 0)
                for subject_result in result.get("subject_results", []):
                    code = int(subject_result["codigo_materia"])
                    _insert_academic_audit_detail(
                        cursor,
                        audit_id,
                        source_student,
                        payload,
                        career_name,
                        code,
                        subject_result.get("nombre_materia") or "",
                        nivel_origen,
                        target_level,
                        _int_value(subject_result.get("num_matricula")),
                        subject_result.get("accion") or "",
                        subject_result.get("observacion") or "",
                        bool(subject_result.get("fue_matriculado")),
                        today if subject_result.get("fue_matriculado") else None,
                    )
                if len(detail_items) < 20:
                    detail_items.append(
                        {
                            "codigo_estud": str(source_student["codigo_estud"]),
                            "nombre_estudiante": source_student["nombre_estudiante"],
                            "paralelo": student_payload.paralelo,
                            "num_matricula": result["num_matricula"],
                            "inserted": result["inserted"],
                            "updated": result["updated"],
                            "existing_skipped": len(existing_codes) + int(result.get("existing_skipped", 0) or 0),
                            "blocked_by_prerequisite": len(blocked_subjects),
                            "blocked_by_repetition": len(blocked_attempt_codes) + int(result["blocked_by_repetition"] or 0),
                            "already_audited": already_audited,
                        }
                    )

            _update_academic_audit_header(cursor, audit_id, summary)
            conn.commit()
            return {
                "ok": True,
                "message": "Matriculacion masiva guardada correctamente.",
                "audit_id": audit_id,
                "summary": summary,
                "items": detail_items,
                "preview": preview,
            }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error guardando matricula masiva: {exc}") from exc


@router.post("/balance-paralelos")
def matricula_acad_balance_paralelos(
    payload: AcademicParallelBalancePayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    user_code = (current_user.login or "APP")[:10]
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT Nombre_Basica
                FROM dbo.CARRERAS
                WHERE Cod_AnioBasica = ?
                """,
                payload.cod_anio_basica,
            )
            career_row = cursor.fetchone()
            if not career_row:
                raise HTTPException(status_code=404, detail="No se encontro la carrera seleccionada")
            career_name = _clean(career_row.Nombre_Basica)
            if "INGL" not in career_name.upper():
                raise HTTPException(status_code=400, detail="El balance de paralelos solo esta habilitado para Ingles")

            cursor.execute(
                """
                SELECT
                    cxe.codigo_estud,
                    d.Apellidos_nombre,
                    cxe.paralelo
                FROM dbo.CARRERAXESTUD cxe
                INNER JOIN dbo.DATOS_ESTUD d ON d.codigo_estud = cxe.codigo_estud
                WHERE cxe.cod_anio_Basica = ?
                  AND cxe.codigo_periodo = ?
                ORDER BY d.Apellidos_nombre, cxe.codigo_estud
                """,
                payload.cod_anio_basica,
                payload.codigo_periodo,
            )
            rows = cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No hay estudiantes en CARRERAXESTUD para balancear")

            students: dict[str, dict[str, Any]] = {}
            before_distribution: dict[str, set[str]] = {}
            for row in rows:
                code = str(row.codigo_estud)
                parallel = _clean(row.paralelo)
                if parallel:
                    before_distribution.setdefault(parallel, set()).add(code)
                student = students.setdefault(
                    code,
                    {
                        "codigo_estud": code,
                        "nombre_estudiante": _clean(row.Apellidos_nombre),
                        "paralelos_ingles": set(),
                        "paralelo_fuente": "",
                        "carrera_fuente": "",
                    },
                )
                if parallel:
                    student["paralelos_ingles"].add(parallel)

            cursor.execute(
                """
                WITH estudiantes_ingles AS (
                    SELECT DISTINCT codigo_estud
                    FROM dbo.CARRERAXESTUD
                    WHERE cod_anio_Basica = ?
                      AND codigo_periodo = ?
                )
                SELECT
                    cxe.codigo_estud,
                    cxe.cod_anio_Basica,
                    c.Nombre_Basica,
                    UPPER(LTRIM(RTRIM(cxe.paralelo))) AS paralelo,
                    COUNT(*) AS total_materias
                FROM dbo.CARRERAXESTUD cxe
                INNER JOIN estudiantes_ingles ei
                  ON ei.codigo_estud = cxe.codigo_estud
                LEFT JOIN dbo.CARRERAS c
                  ON c.Cod_AnioBasica = cxe.cod_anio_Basica
                WHERE cxe.codigo_periodo = ?
                  AND cxe.cod_anio_Basica <> ?
                  AND NULLIF(LTRIM(RTRIM(cxe.paralelo)), '') IS NOT NULL
                GROUP BY cxe.codigo_estud, cxe.cod_anio_Basica, c.Nombre_Basica, UPPER(LTRIM(RTRIM(cxe.paralelo)))
                ORDER BY cxe.codigo_estud, total_materias DESC, paralelo
                """,
                payload.cod_anio_basica,
                payload.codigo_periodo,
                payload.codigo_periodo,
                payload.cod_anio_basica,
            )
            reference_candidates: dict[str, list[dict[str, Any]]] = {}
            source_distribution: dict[str, set[str]] = {}
            for row in cursor.fetchall():
                code = str(row.codigo_estud)
                if code not in students:
                    continue
                parallel = _clean(row.paralelo).upper()
                if not parallel:
                    continue
                source_distribution.setdefault(parallel, set()).add(code)
                reference_candidates.setdefault(code, []).append(
                    {
                        "paralelo": parallel,
                        "carrera": _clean(row.Nombre_Basica),
                        "total_materias": int(row.total_materias or 0),
                    }
                )

            def reference_rank(item: dict[str, Any]) -> tuple[int, int, list[tuple[int, Any]]]:
                parallel = str(item["paralelo"]).upper()
                if parallel.startswith("PBS"):
                    group = 0
                elif parallel == "ABS":
                    group = 1
                else:
                    group = 2
                return (group, -int(item["total_materias"] or 0), _natural_sort_key(parallel))

            for code, candidates in reference_candidates.items():
                selected_reference = sorted(candidates, key=reference_rank)[0]
                students[code]["paralelo_fuente"] = selected_reference["paralelo"]
                students[code]["carrera_fuente"] = selected_reference["carrera"]

            source_parallels = sorted(source_distribution, key=_natural_sort_key)
            target_parallels = sorted(
                [parallel for parallel in source_distribution if parallel.upper().startswith("PBS")],
                key=_natural_sort_key,
            )
            if not target_parallels:
                raise HTTPException(
                    status_code=400,
                    detail="No existen paralelos PBS en las otras carreras del periodo para llevarlos hacia Ingles",
                )

            ordered_students = sorted(
                students.values(),
                key=lambda item: (_clean(item["nombre_estudiante"]).upper(), _int_value(item["codigo_estud"]) or 0),
            )
            total_students = len(ordered_students)
            base_size = total_students // len(target_parallels)
            remainder = total_students % len(target_parallels)
            target_counts = {
                parallel: base_size + (1 if index < remainder else 0)
                for index, parallel in enumerate(target_parallels)
            }

            assignments: dict[str, str] = {}
            current_buckets: dict[str, list[dict[str, Any]]] = {parallel: [] for parallel in target_parallels}
            redistribution_queue: list[dict[str, Any]] = []
            target_parallel_names = {parallel.upper(): parallel for parallel in target_parallels}
            for student in ordered_students:
                source_parallel = str(student.get("paralelo_fuente") or "").upper()
                if source_parallel in target_parallel_names:
                    current_buckets[target_parallel_names[source_parallel]].append(student)
                else:
                    redistribution_queue.append(student)

            for parallel in target_parallels:
                students_in_parallel = current_buckets[parallel]
                keep_count = min(len(students_in_parallel), target_counts[parallel])
                for student in students_in_parallel[:keep_count]:
                    assignments[str(student["codigo_estud"])] = parallel
                redistribution_queue.extend(students_in_parallel[keep_count:])

            redistribution_queue = sorted(
                redistribution_queue,
                key=lambda item: (_clean(item["nombre_estudiante"]).upper(), _int_value(item["codigo_estud"]) or 0),
            )
            queue_index = 0
            for parallel in target_parallels:
                missing = target_counts[parallel] - sum(1 for value in assignments.values() if value == parallel)
                for _ in range(missing):
                    if queue_index >= len(redistribution_queue):
                        break
                    assignments[str(redistribution_queue[queue_index]["codigo_estud"])] = parallel
                    queue_index += 1

            updated_students = 0
            updated_rows = 0
            for student in ordered_students:
                code = str(student["codigo_estud"])
                target_parallel = assignments[code]
                current_parallels = {str(item).upper() for item in student["paralelos_ingles"] if item}
                if current_parallels != {target_parallel.upper()}:
                    updated_students += 1
                cursor.execute(
                    """
                    UPDATE dbo.CARRERAXESTUD
                    SET paralelo = ?,
                        CodUsuaMat = ?,
                        NumMatricuMod = COALESCE(NumMatricuMod, 0) + 1
                    WHERE codigo_estud = ?
                      AND cod_anio_Basica = ?
                      AND codigo_periodo = ?
                      AND (
                        paralelo IS NULL
                        OR UPPER(LTRIM(RTRIM(paralelo))) <> ?
                      )
                    """,
                    target_parallel,
                    user_code,
                    code,
                    payload.cod_anio_basica,
                    payload.codigo_periodo,
                    target_parallel.upper(),
                )
                updated_rows += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

            conn.commit()
            before = [
                {"paralelo": parallel, "total_estudiantes": len(before_distribution.get(parallel, set()))}
                for parallel in sorted(before_distribution, key=_natural_sort_key)
            ]
            source = [
                {"paralelo": parallel, "total_estudiantes": len(source_distribution.get(parallel, set()))}
                for parallel in source_parallels
            ]
            after = [
                {"paralelo": parallel, "total_estudiantes": target_counts[parallel]}
                for parallel in target_parallels
            ]
            zeroed = [
                {"paralelo": parallel, "total_estudiantes": 0}
                for parallel in source_parallels
                if parallel not in target_counts
            ]
            return {
                "ok": True,
                "message": "Balance de paralelos PBS aplicado correctamente.",
                "codigo_periodo": str(payload.codigo_periodo),
                "cod_anio_basica": str(payload.cod_anio_basica),
                "carrera": career_name,
                "total_estudiantes": total_students,
                "total_paralelos": len(target_parallels),
                "updated_students": updated_students,
                "updated_rows": updated_rows,
                "before": before,
                "source": source,
                "after": after + zeroed,
            }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error balanceando paralelos: {exc}") from exc


@router.post("/save")
def matricula_acad_save(
    payload: AcademicEnrollmentPayload,
    current_user: Annotated[SessionUser, Depends(_ACADEMIC_ACCESS)],
) -> dict[str, Any]:
    today = date.today()
    user_code = (current_user.login or "APP")[:10]
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            result = _save_enrollment_with_cursor(cursor, payload, user_code, today)
            conn.commit()
            return result
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error guardando matricula academica: {exc}") from exc
