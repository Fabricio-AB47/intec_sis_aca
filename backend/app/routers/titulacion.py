from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import shutil
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
import pyodbc

from app.core.security import SessionUser, require_roles
from app.routers.students import _MATRICULA_ACTUAL_CTE
from app.services.db import get_connection, get_titulation_connection

router = APIRouter(prefix="/api/titulacion", tags=["titulacion"])

_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE", "SECRETARIA")
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _BACKEND_ROOT / "uploads" / "titulacion"
_MAX_UPLOAD_SIZE = 30 * 1024 * 1024
_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc"}
_HORAS_REQUERIDAS_PRACTICAS = 240
_HORAS_REQUERIDAS_VINCULACION = 60
_MATERIAS_REQUERIDAS_TITULACION = 24
_NOTA_MINIMA_MALLA = 7.0

_DOCUMENT_FORMATS = {
    "APTITUD_LEGAL": "APTITUD_LEGAL_XLSX",
    "RUBRICA_TITULACION": "RUBRICA_TITULACION_XLSX",
    "ACTA_GRADO": "ACTA_GRADO_PDF",
    "TITULO_SENESCYT": "TITULO_SENESCYT_PDF",
    "TITULO_INTEC": "TITULO_INTEC_PDF",
    "EVIDENCIA_EXAMEN_COMPLEXIVO": "EVIDENCIA_EXAMEN_COMPLEXIVO",
    "ACTA_EXAMEN_COMPLEXIVO": "ACTA_EXAMEN_COMPLEXIVO",
    "TRABAJO_FINAL_DEFENSA": "TRABAJO_FINAL_DEFENSA",
    "INFORME_TUTOR_DEFENSA": "INFORME_TUTOR_DEFENSA",
    "ACTA_DEFENSA_GRADO": "ACTA_DEFENSA_GRADO",
    "PRESENTACION_DEFENSA": "PRESENTACION_DEFENSA",
}


class TitulacionExpedientePayload(BaseModel):
    numero_identificacion: str = Field(min_length=5, max_length=20)
    cod_anio_basica: str | None = Field(default=None, max_length=50)
    codigo_periodo: str | None = Field(default=None, max_length=50)
    titulo_otorgado: str | None = Field(default=None, max_length=250)


class TitulacionNotasPayload(BaseModel):
    expediente_id: int
    promedio_asignaturas: float | None = Field(default=None, ge=0, le=10)
    nota_proceso_titulacion: float | None = Field(default=None, ge=0, le=10)
    cedula_validada: bool = True
    titulo_bachiller_cumple: bool = True
    ingles_a2_cumple: bool = False
    no_adeuda_financiero: bool = False
    apto_sustentacion: bool = False
    rubrica_titulacion_cumple: bool = False


class TitulacionSyncPayload(BaseModel):
    expediente_id: int


class TitulacionMecanismoPayload(BaseModel):
    expediente_id: int
    mecanismo_codigo: str = Field(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")


class TitulacionProgramacionPayload(BaseModel):
    expediente_id: int
    fecha_programada: str
    hora_programada: str | None = Field(default=None, max_length=20)
    lugar: str | None = Field(default=None, max_length=250)
    modalidad: str | None = Field(default=None, max_length=30)
    enlace_virtual: str | None = Field(default=None, max_length=1000)


class TitulacionTribunalPayload(BaseModel):
    expediente_id: int
    mecanismo_codigo: str = Field(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")
    rol_tribunal: str = Field(default="MIEMBRO", max_length=50)
    nombre_miembro: str = Field(min_length=3, max_length=200)
    cedula_miembro: str | None = Field(default=None, max_length=20)
    correo_miembro: str | None = Field(default=None, max_length=200)
    orden_firma: int | None = None


class ExamenComplexivoCalificacionPayload(BaseModel):
    expediente_id: int
    nota_examen: float = Field(ge=0, le=10)
    codigo_examen: str | None = Field(default=None, max_length=80)
    tipo_examen: str | None = Field(default=None, max_length=80)
    observacion: str | None = Field(default=None, max_length=1000)


class DefensaTemaPayload(BaseModel):
    expediente_id: int
    tema_trabajo: str = Field(min_length=3, max_length=500)
    linea_investigacion: str | None = Field(default=None, max_length=250)
    tutor: str | None = Field(default=None, max_length=200)
    lector_oponente: str | None = Field(default=None, max_length=200)


class DefensaCalificacionPayload(BaseModel):
    expediente_id: int
    nota_trabajo_escrito: float = Field(ge=0, le=10)
    nota_defensa_oral: float = Field(ge=0, le=10)
    observacion: str | None = Field(default=None, max_length=1000)


class ActaGradoPayload(BaseModel):
    expediente_id: int
    fecha_acta: str
    hora_acta: str | None = Field(default=None, max_length=20)
    numero_acta_grado: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default="Quito", max_length=100)
    escuela: str | None = Field(default=None, max_length=150)
    autoridad_academica: str | None = Field(default=None, max_length=200)
    docente_evaluador: str | None = Field(default=None, max_length=200)
    coordinador_academico: str | None = Field(default=None, max_length=200)
    ruta_acta_pdf: str | None = Field(default=None, max_length=1000)


class TituloSenescytPayload(BaseModel):
    numero_acta_grado: str = Field(min_length=3, max_length=100)
    codigo_registro_senescyt: str = Field(min_length=3, max_length=100)
    fecha_registro: str
    ruta_documento_nube: str | None = Field(default=None, max_length=1000)


class TituloIntecPayload(BaseModel):
    numero_acta_grado: str = Field(min_length=3, max_length=100)
    numero_titulo: str = Field(min_length=3, max_length=100)
    fecha_emision: str
    codigo_verificacion: str | None = Field(default=None, max_length=150)
    ruta_documento_nube: str | None = Field(default=None, max_length=1000)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_filename(value: str, fallback: str = "documento") -> str:
    text = _clean(value) or fallback
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._")
    return text[:140] or fallback


def _document(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _bool_db(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    return _clean(value).lower() in {"1", "true", "si", "sí", "yes"}


def _row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [column[0] for column in cursor.description or []]
    return {column: getattr(row, column) for column in columns}


def _fetch_all(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


def _public_url(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    return f"/uploads/titulacion/{normalized}"


def _db_error(exc: Exception, action: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{action}. Revisa que TITULACION_INTEC exista y que B_NAME3/DB_HOST3 sean correctos. Detalle: {exc}",
    )


def _academic_status(numero_identificacion: str, cod_anio_basica: str | None = None) -> dict[str, Any]:
    document = _document(numero_identificacion)
    if not document:
        return {"found": False, "message": "Número de identificación inválido."}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (1)
                TRY_CONVERT(bigint, de.codigo_estud) AS codigo_estud,
                LTRIM(RTRIM(CONVERT(varchar(50), de.Cedula_Est))) AS numero_identificacion,
                LTRIM(RTRIM(CONVERT(nvarchar(250), de.Apellidos_nombre))) AS apellidos_nombres,
                CONVERT(nvarchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
                CONVERT(nvarchar(250), ca.Nombre_Basica) AS nombre_carrera,
                CONVERT(nvarchar(50), cxe.codigo_periodo) AS codigo_periodo,
                CONVERT(nvarchar(250), pe.Detalle_Periodo) AS nombre_periodo,
                CONVERT(nvarchar(250), de.TituloBachiller) AS titulo_bachiller
            FROM dbo.DATOS_ESTUD de
            LEFT JOIN dbo.CARRERAXESTUD cxe
                ON TRY_CONVERT(bigint, cxe.codigo_estud) = TRY_CONVERT(bigint, de.codigo_estud)
            LEFT JOIN dbo.CARRERAS ca
                ON TRY_CONVERT(nvarchar(50), ca.Cod_AnioBasica) = TRY_CONVERT(nvarchar(50), cxe.cod_anio_Basica)
            LEFT JOIN dbo.PERIODO pe
                ON TRY_CONVERT(nvarchar(50), pe.cod_periodo) = TRY_CONVERT(nvarchar(50), cxe.codigo_periodo)
            WHERE REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), de.Cedula_Est))), '-', ''), ' ', '') = ?
              AND (? IS NULL OR CONVERT(nvarchar(50), cxe.cod_anio_Basica) = ?)
            ORDER BY TRY_CONVERT(int, cxe.codigo_periodo) DESC, TRY_CONVERT(bigint, cxe.num) DESC
            """,
            document,
            cod_anio_basica,
            cod_anio_basica,
        )
        student = cursor.fetchone()
        if not student:
            return {"found": False, "message": "No se encontró estudiante en INTECBDD."}

        career_code = _clean(student.cod_anio_basica)
        student_code = int(student.codigo_estud) if student.codigo_estud is not None else None

        cursor.execute(
            """
            WITH PensumOrdenado AS
            (
                SELECT
                    TRY_CONVERT(nvarchar(50), p.codigo_materia) AS codigo_materia,
                    ROW_NUMBER() OVER
                    (
                        PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)
                        ORDER BY
                            TRY_CONVERT(int, p.Semestre),
                            TRY_CONVERT(int, p.Orden),
                            TRY_CONVERT(nvarchar(250), p.Nomb_Materia)
                    ) AS materia_rn,
                    MIN(TRY_CONVERT(int, p.Semestre)) OVER (PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)) AS semestre,
                    MIN(TRY_CONVERT(int, p.Orden)) OVER (PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)) AS orden
                FROM dbo.PENSUM p
                WHERE TRY_CONVERT(nvarchar(50), p.Cod_AnioBasica) = ?
                  AND TRY_CONVERT(nvarchar(50), p.codigo_materia) IS NOT NULL
            ),
            PensumBase AS
            (
                SELECT TOP (24) codigo_materia
                FROM PensumOrdenado
                WHERE materia_rn = 1
                ORDER BY ISNULL(semestre, 999), ISNULL(orden, 999), codigo_materia
            )
            SELECT COUNT(1) AS total_materias
            FROM PensumBase
            """,
            career_code,
        )
        total_row = cursor.fetchone()
        total_subjects = int(total_row.total_materias or 0) if total_row else 0

        cursor.execute(
            """
            WITH PensumOrdenado AS
            (
                SELECT
                    TRY_CONVERT(nvarchar(50), p.codigo_materia) AS codigo_materia,
                    ROW_NUMBER() OVER
                    (
                        PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)
                        ORDER BY
                            TRY_CONVERT(int, p.Semestre),
                            TRY_CONVERT(int, p.Orden),
                            TRY_CONVERT(nvarchar(250), p.Nomb_Materia)
                    ) AS materia_rn,
                    MIN(TRY_CONVERT(int, p.Semestre)) OVER (PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)) AS semestre,
                    MIN(TRY_CONVERT(int, p.Orden)) OVER (PARTITION BY TRY_CONVERT(nvarchar(50), p.codigo_materia)) AS orden
                FROM dbo.PENSUM p
                WHERE TRY_CONVERT(nvarchar(50), p.Cod_AnioBasica) = ?
                  AND TRY_CONVERT(nvarchar(50), p.codigo_materia) IS NOT NULL
            ),
            PensumBase AS
            (
                SELECT TOP (24) codigo_materia
                FROM PensumOrdenado
                WHERE materia_rn = 1
                ORDER BY ISNULL(semestre, 999), ISNULL(orden, 999), codigo_materia
            ),
            Notas AS
            (
                SELECT
                    TRY_CONVERT(nvarchar(50), cxe.codigo_materia) AS codigo_materia,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                          OR UPPER(COALESCE(CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                        THEN N'H'
                        ELSE N'R'
                    END AS tipo_calculo,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                          OR UPPER(COALESCE(CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                        THEN
                            COALESCE(
                                CASE WHEN TRY_CONVERT(float, cxe.PromedioFinal) BETWEEN 0 AND 10 THEN TRY_CONVERT(float, cxe.PromedioFinal) END,
                                CASE
                                    WHEN TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.teoriaHomo) + TRY_CONVERT(float, cxe.practicahomo)) / 2
                                END
                            )
                        ELSE
                            COALESCE(
                                CASE WHEN TRY_CONVERT(float, cxe.PromedioFinal) BETWEEN 0 AND 10 THEN TRY_CONVERT(float, cxe.PromedioFinal) END,
                                CASE
                                    WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                                END
                            )
                    END AS nota_final,
                    CAST(? AS float) AS nota_aprobar
                FROM dbo.CARRERAXESTUD cxe
                LEFT JOIN dbo.PERIODO pe
                    ON TRY_CONVERT(nvarchar(50), pe.cod_periodo) = TRY_CONVERT(nvarchar(50), cxe.codigo_periodo)
                WHERE TRY_CONVERT(bigint, cxe.codigo_estud) = ?
                  AND TRY_CONVERT(nvarchar(50), cxe.cod_anio_Basica) = ?
                  AND TRY_CONVERT(nvarchar(50), cxe.codigo_materia) IS NOT NULL
            ),
            Mejores AS
            (
                SELECT
                    codigo_materia,
                    MAX(CASE WHEN nota_final >= nota_aprobar AND nota_final <= 10 THEN 1 ELSE 0 END) AS aprobada,
                    MAX(CASE WHEN nota_final >= 0 AND nota_final <= 10 THEN nota_final ELSE NULL END) AS mejor_nota
                FROM Notas
                GROUP BY codigo_materia
            )
            SELECT
                COUNT(1) AS cursadas,
                SUM(CASE WHEN aprobada = 1 THEN 1 ELSE 0 END) AS aprobadas,
                AVG(CASE WHEN aprobada = 1 THEN mejor_nota ELSE NULL END) AS promedio_aprobadas,
                AVG(mejor_nota) AS promedio_general
            FROM Mejores
            INNER JOIN PensumBase p
                ON p.codigo_materia = Mejores.codigo_materia
            """,
            career_code,
            _NOTA_MINIMA_MALLA,
            student_code,
            career_code,
        )
        summary = cursor.fetchone()

    approved = int(summary.aprobadas or 0) if summary else 0
    taken = int(summary.cursadas or 0) if summary else 0
    average = summary.promedio_aprobadas if summary and summary.promedio_aprobadas is not None else (summary.promedio_general if summary else None)
    progress = min(100, round((approved / _MATERIAS_REQUERIDAS_TITULACION) * 100, 2)) if total_subjects else 0
    complete = bool(total_subjects and approved >= _MATERIAS_REQUERIDAS_TITULACION)

    return {
        "found": True,
        "codigo_estud": student_code,
        "numero_identificacion": _clean(student.numero_identificacion),
        "apellidos_nombres": _clean(student.apellidos_nombres),
        "cod_anio_basica": career_code,
        "nombre_carrera": _clean(student.nombre_carrera),
        "codigo_periodo": _clean(student.codigo_periodo),
        "nombre_periodo": _clean(student.nombre_periodo),
        "titulo_bachiller": _clean(student.titulo_bachiller),
        "total_materias": _MATERIAS_REQUERIDAS_TITULACION,
        "materias_pensum": total_subjects,
        "materias_cursadas": taken,
        "materias_aprobadas": approved,
        "materias_pendientes": max(_MATERIAS_REQUERIDAS_TITULACION - approved, 0),
        "promedio_asignaturas": round(float(average), 2) if average is not None else None,
        "porcentaje_malla": progress,
        "malla_finalizada": complete,
    }


def _academic_grades(numero_identificacion: str, cod_anio_basica: str | None = None) -> dict[str, Any]:
    academic = _academic_status(numero_identificacion, cod_anio_basica)
    if not academic.get("found"):
        return {"found": False, "message": academic.get("message") or "No se encontró estudiante.", "items": []}

    student_code = academic.get("codigo_estud")
    career_code = _clean(academic.get("cod_anio_basica"))
    if not student_code or not career_code:
        return {"found": False, "message": "No se encontró carrera académica para consultar la malla.", "items": []}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH PensumOrdenado AS
            (
                SELECT
                    TRY_CONVERT(nvarchar(50), p.codigo_materia) AS codigo_materia,
                    MAX(CONVERT(nvarchar(250), p.Nomb_Materia)) AS nombre_materia,
                    MAX(TRY_CONVERT(int, p.Semestre)) AS semestre,
                    MAX(TRY_CONVERT(decimal(10,2), p.Creditos)) AS creditos,
                    MAX(TRY_CONVERT(int, p.Orden)) AS orden,
                    ROW_NUMBER() OVER
                    (
                        ORDER BY
                            ISNULL(MAX(TRY_CONVERT(int, p.Semestre)), 999),
                            ISNULL(MAX(TRY_CONVERT(int, p.Orden)), 999),
                            MAX(CONVERT(nvarchar(250), p.Nomb_Materia)),
                            TRY_CONVERT(nvarchar(50), p.codigo_materia)
                    ) AS pensum_rn
                FROM dbo.PENSUM p
                WHERE TRY_CONVERT(nvarchar(50), p.Cod_AnioBasica) = ?
                  AND TRY_CONVERT(nvarchar(50), p.codigo_materia) IS NOT NULL
                GROUP BY TRY_CONVERT(nvarchar(50), p.codigo_materia)
            ),
            PensumBase AS
            (
                SELECT TOP (24)
                    codigo_materia,
                    nombre_materia,
                    semestre,
                    creditos,
                    orden
                FROM PensumOrdenado
                WHERE pensum_rn <= 24
                ORDER BY ISNULL(semestre, 999), ISNULL(orden, 999), nombre_materia, codigo_materia
            ),
            NotasBase AS
            (
                SELECT
                    TRY_CONVERT(bigint, cxe.num) AS row_id,
                    TRY_CONVERT(nvarchar(50), cxe.codigo_materia) AS codigo_materia,
                    CONVERT(nvarchar(50), cxe.codigo_periodo) AS codigo_periodo,
                    CONVERT(nvarchar(250), pe.Detalle_Periodo) AS nombre_periodo,
                    CONVERT(nvarchar(50), cxe.Num_Matricula) AS num_matricula,
                    CONVERT(nvarchar(50), cxe.paralelo) AS paralelo,
                    TRY_CONVERT(int, cxe.NumGrupo) AS num_grupo,
                    CONVERT(nvarchar(50), cxe.TipoMatricula) AS tipo_matricula,
                    CONVERT(nvarchar(50), pe.TipoMatricula) AS tipo_periodo,
                    TRY_CONVERT(float, cxe.P1Tareas) AS p1_tareas,
                    TRY_CONVERT(float, cxe.P1Proyectos) AS p1_proyectos,
                    TRY_CONVERT(float, cxe.P1Examen) AS p1_examen,
                    TRY_CONVERT(float, cxe.promP1) AS prom_p1,
                    TRY_CONVERT(float, cxe.P2Tareas) AS p2_tareas,
                    TRY_CONVERT(float, cxe.P2Proyectos) AS p2_proyectos,
                    TRY_CONVERT(float, cxe.P2Examen) AS p2_examen,
                    TRY_CONVERT(float, cxe.promP2) AS prom_p2,
                    TRY_CONVERT(float, cxe.P3Tareas) AS p3_tareas,
                    TRY_CONVERT(float, cxe.P3Proyectos) AS p3_proyectos,
                    TRY_CONVERT(float, cxe.P3Examen) AS p3_examen,
                    TRY_CONVERT(float, cxe.promP3) AS prom_p3,
                    TRY_CONVERT(float, cxe.teoriaHomo) AS teoria_homo,
                    TRY_CONVERT(float, cxe.practicahomo) AS practica_homo,
                    TRY_CONVERT(float, cxe.Promedio) AS promedio,
                    TRY_CONVERT(float, cxe.Asistencia) AS asistencia,
                    TRY_CONVERT(float, cxe.Recuperacion) AS recuperacion,
                    TRY_CONVERT(float, cxe.PromedioFinal) AS promedio_final_registrado,
                    TRY_CONVERT(float, cxe.PromedioAux) AS promedio_aux,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                          OR UPPER(COALESCE(CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                        THEN N'H'
                        ELSE N'R'
                    END AS tipo_calculo,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                          OR UPPER(COALESCE(CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                        THEN
                            COALESCE(
                                CASE WHEN TRY_CONVERT(float, cxe.PromedioFinal) BETWEEN 0 AND 10 THEN TRY_CONVERT(float, cxe.PromedioFinal) END,
                                CASE
                                    WHEN TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.teoriaHomo) + TRY_CONVERT(float, cxe.practicahomo)) / 2
                                END
                            )
                        ELSE
                            COALESCE(
                                CASE WHEN TRY_CONVERT(float, cxe.PromedioFinal) BETWEEN 0 AND 10 THEN TRY_CONVERT(float, cxe.PromedioFinal) END,
                                CASE
                                    WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                                END
                            )
                    END AS nota_final,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                          OR UPPER(COALESCE(CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                        THEN N'H: teórico + práctico + final'
                        ELSE N'R: P1 + P2 + P3 + final'
                    END AS formula_nota,
                    CAST(? AS float) AS nota_aprobar,
                    TRY_CONVERT(bigint, cxe.num) AS num_registro
                FROM dbo.CARRERAXESTUD cxe
                LEFT JOIN dbo.PERIODO pe
                    ON TRY_CONVERT(nvarchar(50), pe.cod_periodo) = TRY_CONVERT(nvarchar(50), cxe.codigo_periodo)
                WHERE TRY_CONVERT(bigint, cxe.codigo_estud) = ?
                  AND TRY_CONVERT(nvarchar(50), cxe.cod_anio_Basica) = ?
                  AND TRY_CONVERT(nvarchar(50), cxe.codigo_materia) IS NOT NULL
            ),
            NotasRanked AS
            (
                SELECT
                    nb.*,
                    ROW_NUMBER() OVER
                    (
                        PARTITION BY nb.codigo_materia
                        ORDER BY
                            CASE WHEN nb.nota_final >= nb.nota_aprobar AND nb.nota_final <= 10 THEN 1 ELSE 0 END DESC,
                            CASE WHEN nb.nota_final >= 0 AND nb.nota_final <= 10 THEN 1 ELSE 0 END DESC,
                            nb.nota_final DESC,
                            TRY_CONVERT(bigint, nb.codigo_periodo) DESC,
                            nb.num_registro DESC
                    ) AS rn
                FROM NotasBase nb
            )
            SELECT
                p.codigo_materia,
                p.nombre_materia,
                p.semestre,
                p.creditos,
                p.orden,
                n.row_id,
                n.codigo_periodo,
                n.nombre_periodo,
                n.num_matricula,
                n.paralelo,
                n.num_grupo,
                n.tipo_matricula,
                n.tipo_periodo,
                n.tipo_calculo,
                n.p1_tareas,
                n.p1_proyectos,
                n.p1_examen,
                n.prom_p1,
                n.p2_tareas,
                n.p2_proyectos,
                n.p2_examen,
                n.prom_p2,
                n.p3_tareas,
                n.p3_proyectos,
                n.p3_examen,
                n.prom_p3,
                n.teoria_homo,
                n.practica_homo,
                n.promedio,
                n.asistencia,
                n.recuperacion,
                n.promedio_final_registrado,
                n.promedio_aux,
                n.nota_final,
                n.formula_nota,
                n.nota_aprobar,
                CASE
                    WHEN n.codigo_materia IS NULL THEN CAST(0 AS bit)
                    WHEN n.nota_final >= n.nota_aprobar AND n.nota_final <= 10 THEN CAST(1 AS bit)
                    ELSE CAST(0 AS bit)
                END AS aprobada,
                CASE
                    WHEN n.codigo_materia IS NULL THEN N'Pendiente'
                    WHEN n.nota_final >= n.nota_aprobar AND n.nota_final <= 10 THEN N'Aprobada'
                    WHEN n.nota_final IS NULL THEN N'Sin nota'
                    WHEN n.nota_final > 10 THEN N'Reprobada'
                    ELSE N'Reprobada'
                END AS estado
            FROM PensumBase p
            LEFT JOIN NotasRanked n
                ON n.codigo_materia = p.codigo_materia
               AND n.rn = 1
            ORDER BY ISNULL(p.semestre, 999), ISNULL(p.orden, 999), p.nombre_materia, p.codigo_materia
            """,
            career_code,
            _NOTA_MINIMA_MALLA,
            student_code,
            career_code,
        )
        items = _fetch_all(cursor)

    approved = sum(1 for item in items if _bool_db(item.get("aprobada")))
    total = len(items)
    return {
        "found": True,
        "academic": academic,
        "items": items,
        "summary": {
            "materias_requeridas": _MATERIAS_REQUERIDAS_TITULACION,
            "materias_pensum": total,
            "total_materias": total,
            "materias_aprobadas": approved,
            "materias_pendientes": max(total - approved, 0),
            "porcentaje_malla": min(100, round((approved / _MATERIAS_REQUERIDAS_TITULACION) * 100, 2)) if total else 0,
        },
    }


def _fetch_expediente(cursor: pyodbc.Cursor, expediente_id: int | None = None, numero_identificacion: str | None = None) -> dict[str, Any] | None:
    if expediente_id is None and not numero_identificacion:
        return None
    params: list[Any] = []
    where = "E.ExpedienteId = ?"
    if expediente_id is not None:
        params.append(expediente_id)
    else:
        where = "REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), ER.NumeroIdentificacion))), '-', ''), ' ', '') = ?"
        params.append(_document(numero_identificacion or ""))

    cursor.execute(
        f"""
        SELECT TOP (1)
            E.ExpedienteId,
            ER.CodigoEstud,
            ER.NumeroIdentificacion,
            ER.ApellidosNombres,
            E.CarreraRefId,
            E.CodAnioBasica,
            COALESCE(CR.NombreCarrera, E.CodAnioBasica) AS NombreCarrera,
            E.CodigoPeriodo,
            E.TituloOtorgado,
            E.MecanismoTitulacionId AS MecanismoCodigoRaw,
            MT.MecanismoTitulacionId,
            MT.Codigo AS MecanismoCodigo,
            MT.Nombre AS MecanismoNombre,
            E.NumeroActaGrado,
            E.NumeroRefrendacion,
            E.FechaActaGrado,
            E.FechaRefrendacion,
            E.CedulaValidada,
            E.TituloBachillerCumple,
            E.InglesA2Cumple,
            E.MallaCurricularCumple,
            E.NoAdeudaFinanciero,
            E.AptoSustentacion,
            E.PracticasPreprofesionalesCumple,
            E.VinculacionCumple,
            E.RubricaTitulacionCumple,
            E.PromedioAsignaturas,
            E.NotaPromedioAsignaturas80,
            E.NotaProcesoTitulacion20,
            E.NotaFinalGrado,
            E.EstadoExpediente,
            C.TotalHorasPracticasPreprofesionales,
            C.TotalHorasVinculacion,
            C.CumplePracticasPreprofesionales,
            C.CumpleVinculacion,
            C.FechaSincronizacion AS FechaSincronizacionPracticas
        FROM tit.ExpedienteTitulacion E
        INNER JOIN core.EstudianteRef ER
            ON ER.EstudianteRefId = E.EstudianteRefId
        LEFT JOIN core.CarreraRef CR
            ON CR.CarreraRefId = E.CarreraRefId
        LEFT JOIN vinc.CumplimientoPracticasVinculacion C
            ON C.ExpedienteId = E.ExpedienteId
        LEFT JOIN cat.MecanismoTitulacion MT
            ON MT.Codigo COLLATE Modern_Spanish_CI_AS = E.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS
        WHERE {where}
        ORDER BY E.ExpedienteId DESC
        """,
        *params,
    )
    row = cursor.fetchone()
    data = _row_dict(cursor, row) if row else None
    if data and _number(data.get("TotalHorasVinculacion")) >= _HORAS_REQUERIDAS_VINCULACION:
        data["VinculacionCumple"] = 1
        data["CumpleVinculacion"] = 1
    return data


def _fetch_documents(cursor: pyodbc.Cursor, expediente_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT TOP (100)
            DocumentoId,
            ExpedienteId,
            TipoDocumentoCodigo,
            FormatoCargaCodigo,
            NombreArchivo,
            RutaNube,
            EsFirmadoElectronico,
            FechaDocumento,
            EstadoDocumento,
            VersionDocumento,
            UsuarioCarga,
            FechaCarga,
            Observacion,
            Activo
        FROM doc.DocumentoExpediente
        WHERE ExpedienteId = ?
          AND Activo = 1
        ORDER BY FechaCarga DESC, DocumentoId DESC
        """,
        expediente_id,
    )
    return _fetch_all(cursor)


def _prevalidar(cursor: pyodbc.Cursor, numero_identificacion: str, expediente_id: int | None) -> dict[str, Any] | None:
    try:
        cursor.execute(
            """
            EXEC tit.sp_PrevalidarGeneracionTitulacion
                @NumeroIdentificacion = ?,
                @ExpedienteId = ?,
                @SincronizarPracticas = 0
            """,
            _document(numero_identificacion),
            expediente_id,
        )
        row = cursor.fetchone()
        return _row_dict(cursor, row) if row else None
    except pyodbc.Error:
        return None


def _fetch_one_query(cursor: pyodbc.Cursor, query: str, *params: Any) -> dict[str, Any] | None:
    cursor.execute(query, *params)
    row = cursor.fetchone()
    return _row_dict(cursor, row) if row else None


def _fetch_mechanism_detail(cursor: pyodbc.Cursor, expediente_id: int) -> dict[str, Any]:
    selected = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1) *
        FROM rpt.vw_MecanismoTitulacionExpediente
        WHERE ExpedienteId = ?
        """,
        expediente_id,
    )
    prevalidation = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1) *
        FROM rpt.vw_PrevalidacionMecanismoTitulacion
        WHERE ExpedienteId = ?
        """,
        expediente_id,
    )
    programacion = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1)
            P.ProgramacionTitulacionId,
            P.ExpedienteId,
            M.Codigo AS MecanismoCodigo,
            M.Nombre AS MecanismoNombre,
            P.FechaProgramada,
            P.HoraProgramada,
            P.Lugar,
            P.Modalidad,
            P.EnlaceVirtual,
            P.EstadoProgramacion,
            P.FechaRegistro
        FROM tit.ProgramacionTitulacion P
        INNER JOIN cat.MecanismoTitulacion M
            ON M.MecanismoTitulacionId = P.MecanismoTitulacionId
        WHERE P.ExpedienteId = ?
          AND P.Activo = 1
        ORDER BY P.ProgramacionTitulacionId DESC
        """,
        expediente_id,
    )
    examen = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1) *
        FROM rpt.vw_ExamenComplexivo
        WHERE ExpedienteId = ?
        """,
        expediente_id,
    )
    defensa = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1) *
        FROM rpt.vw_DefensaGrado
        WHERE ExpedienteId = ?
        """,
        expediente_id,
    )
    cursor.execute(
        """
        SELECT TOP (50)
            T.TribunalTitulacionId,
            M.Codigo AS MecanismoCodigo,
            T.RolTribunal,
            T.NombreMiembro,
            T.CedulaMiembro,
            T.CorreoMiembro,
            T.OrdenFirma,
            T.FechaRegistro
        FROM tit.TribunalTitulacion T
        INNER JOIN cat.MecanismoTitulacion M
            ON M.MecanismoTitulacionId = T.MecanismoTitulacionId
        WHERE T.ExpedienteId = ?
          AND T.Activo = 1
        ORDER BY ISNULL(T.OrdenFirma, 999), T.TribunalTitulacionId
        """,
        expediente_id,
    )
    tribunal = _fetch_all(cursor)

    return {
        "selected": selected,
        "prevalidation": prevalidation,
        "programacion": programacion,
        "examen": examen,
        "defensa": defensa,
        "tribunal": tribunal,
    }


def _mechanism_approved(cursor: pyodbc.Cursor, expediente_id: int) -> tuple[bool, str]:
    cursor.execute(
        """
        EXEC tit.sp_PrevalidarMecanismoTitulacion @ExpedienteId = ?
        """,
        expediente_id,
    )
    row = cursor.fetchone()
    if not row:
        return False, "Debe seleccionar y aprobar el mecanismo de titulación."
    data = _row_dict(cursor, row)
    return bool(data.get("MecanismoAprobado")), _clean(data.get("MensajeMecanismo")) or "Mecanismo pendiente."


def _fetch_generation_detail(cursor: pyodbc.Cursor, expediente_id: int) -> dict[str, Any]:
    acta = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1)
            ActaGradoId,
            ExpedienteId,
            NumeroActaGrado,
            FechaActa,
            HoraActa,
            Ciudad,
            Escuela,
            AutoridadAcademica,
            DocenteEvaluador,
            CoordinadorAcademico,
            RutaActaPDF,
            FechaCreacion,
            UsuarioCreacion
        FROM tit.ActaGrado
        WHERE ExpedienteId = ?
        ORDER BY ActaGradoId DESC
        """,
        expediente_id,
    )
    senescyt = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1)
            RegistroSenescytId,
            ExpedienteId,
            CodigoRegistroSenescyt,
            FechaRegistro,
            RutaDocumentoNube,
            EstadoRegistro,
            UsuarioRegistro,
            FechaCreacion
        FROM tit.RegistroSenescyt
        WHERE ExpedienteId = ?
        ORDER BY RegistroSenescytId DESC
        """,
        expediente_id,
    )
    intec = _fetch_one_query(
        cursor,
        """
        SELECT TOP (1)
            TituloIntecId,
            ExpedienteId,
            NumeroTitulo,
            FechaEmision,
            CodigoVerificacion,
            RutaDocumentoNube,
            EstadoTitulo,
            UsuarioGeneracion,
            FechaCreacion
        FROM tit.TituloIntec
        WHERE ExpedienteId = ?
        ORDER BY TituloIntecId DESC
        """,
        expediente_id,
    )
    return {"acta": acta, "senescyt": senescyt, "intec": intec}


def _response_payload(numero_identificacion: str, expediente_id: int | None = None) -> dict[str, Any]:
    academic = _academic_status(numero_identificacion)
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=expediente_id, numero_identificacion=numero_identificacion)
            documents = _fetch_documents(cursor, int(expediente["ExpedienteId"])) if expediente else []
            mechanism = _fetch_mechanism_detail(cursor, int(expediente["ExpedienteId"])) if expediente else None
            generation = _fetch_generation_detail(cursor, int(expediente["ExpedienteId"])) if expediente else None
            prevalidation = _prevalidar(
                cursor,
                str(expediente["NumeroIdentificacion"] if expediente else numero_identificacion),
                int(expediente["ExpedienteId"]) if expediente else None,
            )
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar titulación") from exc

    return {
        "academic": academic,
        "expediente": expediente,
        "documents": documents,
        "mechanism": mechanism,
        "generation": generation,
        "prevalidation": prevalidation,
    }


def _sync_student(cursor: pyodbc.Cursor, numero_identificacion: str) -> None:
    cursor.execute("EXEC etl.sp_SincronizarCatalogosDesdeINTECBDD")
    cursor.execute("EXEC etl.sp_SincronizarEstudiantesDesdeINTECBDD @NumeroIdentificacion = ?", _document(numero_identificacion))


@router.get("/expediente")
def get_titulacion_expediente(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    numero_identificacion: Annotated[str, Query(min_length=5, max_length=20)],
) -> dict[str, Any]:
    del current_user
    return _response_payload(numero_identificacion)


@router.get("/malla-calificaciones")
def get_titulacion_malla_calificaciones(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    numero_identificacion: Annotated[str, Query(min_length=5, max_length=20)],
    cod_anio_basica: Annotated[str | None, Query(max_length=50)] = None,
) -> dict[str, Any]:
    del current_user
    try:
        return _academic_grades(numero_identificacion, cod_anio_basica)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar calificaciones de la malla") from exc


@router.get("/mecanismos")
def get_titulacion_mecanismos(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    MecanismoTitulacionId,
                    Codigo,
                    Nombre,
                    RequiereProgramacion,
                    RequiereTribunal,
                    NotaMinima
                FROM cat.MecanismoTitulacion
                WHERE Activo = 1
                ORDER BY Nombre
                """
            )
            return {"items": _fetch_all(cursor)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar mecanismos de titulación") from exc


@router.get("/aptos")
def get_titulacion_estudiantes_aptos(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> dict[str, Any]:
    del current_user
    term = _clean(search)
    academic_params: list[Any] = []
    academic_where = """
    WHERE bc.estado_codigo = 'A'
    """
    if term:
        like = f"%{term}%"
        document = _document(term)
        academic_where += """
        AND
        (
            CONVERT(varchar(50), bc.codigo_estud) LIKE ?
            OR CONVERT(varchar(50), bc.Cedula_Est) LIKE ?
            OR CONVERT(nvarchar(250), bc.Apellidos_nombre) LIKE ?
            OR CONVERT(nvarchar(250), bc.nombre_carrera) LIKE ?
            OR (? <> '' AND REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), bc.Cedula_Est))), '-', ''), ' ', '') LIKE ?)
        )
        """
        academic_params.extend([like, like, like, like, document, f"%{document}%"])
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                _MATRICULA_ACTUAL_CTE
                + f"""
                , Base AS
                (
                    SELECT
                        TRY_CONVERT(bigint, bc.codigo_estud) AS CodigoEstud,
                        REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), bc.Cedula_Est))), '-', ''), ' ', '') AS DocumentoLimpio,
                        CONVERT(varchar(50), bc.Cedula_Est) AS NumeroIdentificacion,
                        CONVERT(nvarchar(250), bc.Apellidos_nombre) AS ApellidosNombres,
                        CONVERT(nvarchar(50), bc.cod_anio_Basica) AS CodAnioBasica,
                        CONVERT(nvarchar(250), bc.nombre_carrera) AS NombreCarrera,
                        CONVERT(nvarchar(50), bc.codigo_periodo) AS CodigoPeriodo,
                        CONVERT(nvarchar(250), bc.estado_nombre) AS EstadoAcademico,
                        MAX(TRY_CONVERT(bigint, bc.codigo_estud)) AS UltimoRegistro,
                        MAX(TRY_CONVERT(bigint, bc.codigo_periodo)) AS UltimoPeriodo,
                        CASE
                            WHEN UPPER(CONVERT(nvarchar(250), bc.nombre_carrera)) LIKE N'%INGL%' THEN 1
                            ELSE 0
                        END AS EsCarreraIngles
                    FROM base_cruce bc
                    {academic_where}
                    GROUP BY
                        bc.codigo_estud,
                        bc.Cedula_Est,
                        bc.Apellidos_nombre,
                        bc.cod_anio_Basica,
                        bc.nombre_carrera,
                        bc.codigo_periodo,
                        bc.estado_nombre,
                        CASE
                            WHEN UPPER(CONVERT(nvarchar(250), bc.nombre_carrera)) LIKE N'%INGL%' THEN 1
                            ELSE 0
                        END
                ),
                Unico AS
                (
                    SELECT
                        *,
                        ROW_NUMBER() OVER
                        (
                            PARTITION BY DocumentoLimpio
                            ORDER BY EsCarreraIngles ASC, UltimoPeriodo DESC, UltimoRegistro DESC, CodAnioBasica DESC
                        ) AS RN
                    FROM Base
                    WHERE DocumentoLimpio <> ''
                )
                SELECT TOP (?)
                    CodigoEstud,
                    NumeroIdentificacion,
                    ApellidosNombres,
                    CodAnioBasica,
                    NombreCarrera,
                    CodigoPeriodo,
                    EstadoAcademico,
                    UltimoRegistro
                FROM Unico
                WHERE RN = 1
                ORDER BY ApellidosNombres, NombreCarrera
                """,
                *academic_params,
                limit,
            )
            base_rows = _fetch_all(cursor)

        documents = sorted({_document(str(row.get("NumeroIdentificacion") or "")) for row in base_rows if _document(str(row.get("NumeroIdentificacion") or ""))})
        expediente_map: dict[tuple[str, str], dict[str, Any]] = {}
        if documents:
            placeholders = ",".join("?" for _ in documents)
            with get_titulation_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT
                        E.ExpedienteId,
                        ER.NumeroIdentificacion,
                        E.CodAnioBasica,
                        E.InglesA2Cumple,
                        E.MallaCurricularCumple,
                        E.PracticasPreprofesionalesCumple,
                        E.VinculacionCumple,
                        E.EstadoExpediente,
                        C.TotalHorasPracticasPreprofesionales,
                        C.TotalHorasVinculacion,
                        C.CumplePracticasPreprofesionales,
                        C.CumpleVinculacion
                    FROM tit.ExpedienteTitulacion E
                    INNER JOIN core.EstudianteRef ER
                        ON ER.EstudianteRefId = E.EstudianteRefId
                    LEFT JOIN vinc.CumplimientoPracticasVinculacion C
                        ON C.ExpedienteId = E.ExpedienteId
                    WHERE REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), ER.NumeroIdentificacion))), '-', ''), ' ', '') IN ({placeholders})
                    ORDER BY E.ExpedienteId DESC
                    """,
                    *documents,
                )
                for expediente in _fetch_all(cursor):
                    document_key = _document(str(expediente.get("NumeroIdentificacion") or ""))
                    career_key = _clean(expediente.get("CodAnioBasica"))
                    expediente_map.setdefault((document_key, career_key), expediente)
                    expediente_map.setdefault((document_key, ""), expediente)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar estudiantes activos para titulación") from exc

    items: list[dict[str, Any]] = []
    for row in base_rows:
        document = _document(str(row.get("NumeroIdentificacion") or ""))
        career = _clean(row.get("CodAnioBasica"))
        academic = _academic_status(document, career)
        expediente = expediente_map.get((document, career)) or expediente_map.get((document, ""))
        materias_aprobadas = int(academic.get("materias_aprobadas") or 0)
        total_materias = int(academic.get("total_materias") or 0)
        cumple_malla_24 = materias_aprobadas >= _MATERIAS_REQUERIDAS_TITULACION
        cumple_ingles_avanzado = _bool_db(expediente.get("InglesA2Cumple") if expediente else None)
        cumple_practicas = _bool_db(expediente.get("PracticasPreprofesionalesCumple") if expediente else None) or _bool_db(expediente.get("CumplePracticasPreprofesionales") if expediente else None)
        horas_vinculacion = _number(expediente.get("TotalHorasVinculacion") if expediente else 0)
        cumple_vinculacion = (
            _bool_db(expediente.get("VinculacionCumple") if expediente else None)
            or _bool_db(expediente.get("CumpleVinculacion") if expediente else None)
            or horas_vinculacion >= _HORAS_REQUERIDAS_VINCULACION
        )
        apto = cumple_malla_24 and cumple_ingles_avanzado and cumple_practicas and cumple_vinculacion
        pendientes = []
        if not cumple_malla_24:
            pendientes.append(f"Malla {_MATERIAS_REQUERIDAS_TITULACION} materias")
        if not cumple_ingles_avanzado:
            pendientes.append("Inglés A2+ - INTERMEDIATE")
        if not cumple_practicas:
            pendientes.append("Prácticas preprofesionales")
        if not cumple_vinculacion:
            pendientes.append("Vinculación con la sociedad")
        items.append({
            **row,
            **(expediente or {}),
            "NumeroIdentificacion": row.get("NumeroIdentificacion"),
            "ApellidosNombres": row.get("ApellidosNombres"),
            "CodAnioBasica": row.get("CodAnioBasica"),
            "NombreCarrera": row.get("NombreCarrera"),
            "CodigoPeriodo": row.get("CodigoPeriodo"),
            "TotalMaterias": total_materias,
            "MateriasAprobadas": materias_aprobadas,
            "CumpleMalla24": cumple_malla_24,
            "CumpleInglesA2Avanzado": cumple_ingles_avanzado,
            "CumplePracticasPreprofesionales": cumple_practicas,
            "CumpleVinculacion": cumple_vinculacion,
            "AptoTitulacion": apto,
            "Pendientes": pendientes,
            "PromedioAsignaturas": academic.get("promedio_asignaturas"),
        })

    return {
        "items": items,
        "total": len(items),
        "aptos": sum(1 for item in items if item["AptoTitulacion"]),
        "pendientes": sum(1 for item in items if not item["AptoTitulacion"]),
        "criteria": {
            "materias_requeridas": _MATERIAS_REQUERIDAS_TITULACION,
            "ingles": "A2+ - INTERMEDIATE validado",
            "practicas": f"Prácticas preprofesionales cumplidas ({_HORAS_REQUERIDAS_PRACTICAS} horas)",
            "vinculacion": f"Vinculación con la sociedad cumplida ({_HORAS_REQUERIDAS_VINCULACION} horas)",
        },
    }

@router.post("/expediente")
def create_or_update_titulacion_expediente(
    payload: TitulacionExpedientePayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    academic = _academic_status(payload.numero_identificacion, payload.cod_anio_basica)
    if not academic.get("found"):
        raise HTTPException(status_code=404, detail=str(academic.get("message") or "No se encontró estudiante."))

    cod_anio_basica = _clean(payload.cod_anio_basica) or _clean(academic.get("cod_anio_basica"))
    codigo_periodo = _clean(payload.codigo_periodo) or _clean(academic.get("codigo_periodo"))
    title = _clean(payload.titulo_otorgado) or None

    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            _sync_student(cursor, payload.numero_identificacion)
            cursor.execute(
                """
                DECLARE @ExpedienteId BIGINT;
                EXEC tit.sp_CrearActualizarExpedienteBasico
                    @NumeroIdentificacion = ?,
                    @CodAnioBasica = ?,
                    @CodigoPeriodo = ?,
                    @TituloOtorgado = ?,
                    @Usuario = ?,
                    @ExpedienteId = @ExpedienteId OUTPUT;
                SELECT @ExpedienteId AS ExpedienteId;
                """,
                _document(payload.numero_identificacion),
                cod_anio_basica,
                codigo_periodo,
                title,
                current_user.login,
            )
            row = cursor.fetchone()
            expediente_id = int(row.ExpedienteId)
            promedio = academic.get("promedio_asignaturas")
            cursor.execute(
                """
                UPDATE tit.ExpedienteTitulacion
                   SET MallaCurricularCumple = ?,
                       PromedioAsignaturas = COALESCE(?, PromedioAsignaturas),
                       NotaPromedioAsignaturas80 = CASE WHEN ? IS NULL THEN NotaPromedioAsignaturas80 ELSE ROUND(? * 0.80, 2) END,
                       TituloBachillerCumple = CASE WHEN ? = 1 THEN 1 ELSE TituloBachillerCumple END,
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE ExpedienteId = ?
                """,
                1 if academic.get("malla_finalizada") else 0,
                promedio,
                promedio,
                promedio,
                1 if academic.get("titulo_bachiller") else 0,
                current_user.login,
                expediente_id,
            )
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo crear o actualizar el expediente") from exc

    return {"ok": True, "message": "Expediente de titulación listo.", **_response_payload(payload.numero_identificacion, expediente_id)}


def _response_after_mechanism_update(expediente_id: int, message: str) -> dict[str, Any]:
    with get_titulation_connection() as conn:
        cursor = conn.cursor()
        expediente = _fetch_expediente(cursor, expediente_id=expediente_id)
        if not expediente:
            raise HTTPException(status_code=404, detail="No existe expediente de titulación.")
        cedula = _clean(expediente["NumeroIdentificacion"])
    return {"ok": True, "message": message, **_response_payload(cedula, expediente_id)}


@router.get("/programacion")
def get_titulacion_programacion(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    mecanismo: Annotated[str | None, Query(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> dict[str, Any]:
    del current_user
    term = f"%{_clean(search)}%" if search else None
    params: list[Any] = []
    filters = ["E.MecanismoTitulacionId IN ('EXAMEN_COMPLEXIVO','DEFENSA_GRADO')"]
    if mecanismo:
        filters.append("E.MecanismoTitulacionId = ?")
        params.append(mecanismo)
    if term:
        filters.append(
            """
            (
                ER.NumeroIdentificacion LIKE ?
                OR ER.ApellidosNombres LIKE ?
                OR CR.NombreCarrera LIKE ?
                OR E.NumeroActaGrado LIKE ?
            )
            """
        )
        params.extend([term, term, term, term])

    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({int(limit)})
                    E.ExpedienteId,
                    ER.NumeroIdentificacion,
                    ER.ApellidosNombres,
                    CR.NombreCarrera,
                    E.CodAnioBasica,
                    E.CodigoPeriodo,
                    E.EstadoExpediente,
                    E.MecanismoTitulacionId AS MecanismoCodigo,
                    CASE
                        WHEN E.MecanismoTitulacionId = 'EXAMEN_COMPLEXIVO' THEN N'Examen complexivo'
                        WHEN E.MecanismoTitulacionId = 'DEFENSA_GRADO' THEN N'Defensa de grado'
                        ELSE E.MecanismoTitulacionId
                    END AS MecanismoNombre,
                    P.ProgramacionTitulacionId,
                    P.FechaProgramada,
                    P.HoraProgramada,
                    P.Lugar,
                    P.Modalidad,
                    P.EnlaceVirtual,
                    P.EstadoProgramacion,
                    D.TemaTrabajo,
                    D.LineaInvestigacion,
                    D.Tutor,
                    D.LectorOponente,
                    EX.CodigoExamen,
                    EX.TipoExamen,
                    Tribunal.TotalMiembrosTribunal,
                    Tribunal.Responsables
                FROM tit.ExpedienteTitulacion E
                INNER JOIN core.EstudianteRef ER
                    ON ER.EstudianteRefId = E.EstudianteRefId
                LEFT JOIN core.CarreraRef CR
                    ON CR.CarreraRefId = E.CarreraRefId
                OUTER APPLY
                (
                    SELECT TOP (1)
                        P.ProgramacionTitulacionId,
                        P.FechaProgramada,
                        P.HoraProgramada,
                        P.Lugar,
                        P.Modalidad,
                        P.EnlaceVirtual,
                        P.EstadoProgramacion
                    FROM tit.ProgramacionTitulacion P
                    INNER JOIN cat.MecanismoTitulacion M
                        ON M.MecanismoTitulacionId = P.MecanismoTitulacionId
                    WHERE P.ExpedienteId = E.ExpedienteId
                      AND P.Activo = 1
                      AND M.Codigo = E.MecanismoTitulacionId
                    ORDER BY P.ProgramacionTitulacionId DESC
                ) P
                OUTER APPLY
                (
                    SELECT TOP (1)
                        TemaTrabajo,
                        LineaInvestigacion,
                        Tutor,
                        LectorOponente
                    FROM tit.DefensaGrado
                    WHERE ExpedienteId = E.ExpedienteId
                    ORDER BY DefensaGradoId DESC
                ) D
                OUTER APPLY
                (
                    SELECT TOP (1)
                        CodigoExamen,
                        TipoExamen
                    FROM tit.ExamenComplexivo
                    WHERE ExpedienteId = E.ExpedienteId
                    ORDER BY ExamenComplexivoId DESC
                ) EX
                OUTER APPLY
                (
                    SELECT
                        COUNT(1) AS TotalMiembrosTribunal,
                        STRING_AGG(CONCAT(T.RolTribunal, N': ', T.NombreMiembro), N'; ') WITHIN GROUP (ORDER BY ISNULL(T.OrdenFirma, 999), T.TribunalTitulacionId) AS Responsables
                    FROM tit.TribunalTitulacion T
                    INNER JOIN cat.MecanismoTitulacion M
                        ON M.MecanismoTitulacionId = T.MecanismoTitulacionId
                    WHERE T.ExpedienteId = E.ExpedienteId
                      AND T.Activo = 1
                      AND M.Codigo = E.MecanismoTitulacionId
                ) Tribunal
                WHERE {" AND ".join(filters)}
                ORDER BY
                    CASE WHEN P.FechaProgramada IS NULL THEN 1 ELSE 0 END,
                    P.FechaProgramada,
                    P.HoraProgramada,
                    ER.ApellidosNombres
                """,
                *params,
            )
            items = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar programación de titulación") from exc

    return {
        "items": items,
        "total": len(items),
        "complexivo": sum(1 for item in items if item.get("MecanismoCodigo") == "EXAMEN_COMPLEXIVO"),
        "defensa": sum(1 for item in items if item.get("MecanismoCodigo") == "DEFENSA_GRADO"),
    }


@router.post("/mecanismo")
def select_titulacion_mecanismo(
    payload: TitulacionMecanismoPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            if not _fetch_expediente(cursor, expediente_id=payload.expediente_id):
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")
            cursor.execute(
                """
                EXEC tit.sp_SeleccionarMecanismoTitulacion
                    @ExpedienteId = ?,
                    @MecanismoCodigo = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.mecanismo_codigo,
                current_user.login,
            )
            while cursor.nextset():
                pass
            cursor.execute(
                """
                UPDATE tit.ExpedienteTitulacion
                   SET EstadoExpediente = 'EGRESAMIENTO',
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE ExpedienteId = ?
                """,
                current_user.login,
                payload.expediente_id,
            )
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo seleccionar el mecanismo de titulación") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Estudiante enviado a egresamiento y mecanismo seleccionado.")


@router.post("/examen-complexivo/programar")
def program_examen_complexivo(
    payload: TitulacionProgramacionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_ProgramarExamenComplexivo
                    @ExpedienteId = ?,
                    @FechaProgramada = ?,
                    @HoraProgramada = ?,
                    @Lugar = ?,
                    @Modalidad = ?,
                    @EnlaceVirtual = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.fecha_programada,
                payload.hora_programada,
                _clean(payload.lugar),
                _clean(payload.modalidad),
                _clean(payload.enlace_virtual),
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo programar el examen complexivo") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Examen complexivo programado.")


@router.post("/examen-complexivo/calificar")
def grade_examen_complexivo(
    payload: ExamenComplexivoCalificacionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_CalificarExamenComplexivo
                    @ExpedienteId = ?,
                    @NotaExamen = ?,
                    @CodigoExamen = ?,
                    @TipoExamen = ?,
                    @RutaEvidencia = NULL,
                    @Observacion = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.nota_examen,
                _clean(payload.codigo_examen),
                _clean(payload.tipo_examen),
                _clean(payload.observacion),
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo calificar el examen complexivo") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Examen complexivo calificado.")


@router.post("/defensa-grado/tema")
def save_defensa_grado_tema(
    payload: DefensaTemaPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_RegistrarTemaDefensaGrado
                    @ExpedienteId = ?,
                    @TemaTrabajo = ?,
                    @LineaInvestigacion = ?,
                    @Tutor = ?,
                    @LectorOponente = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                _clean(payload.tema_trabajo),
                _clean(payload.linea_investigacion),
                _clean(payload.tutor),
                _clean(payload.lector_oponente),
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el tema de defensa") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Tema de defensa guardado.")


@router.post("/defensa-grado/programar")
def program_defensa_grado(
    payload: TitulacionProgramacionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_ProgramarDefensaGrado
                    @ExpedienteId = ?,
                    @FechaProgramada = ?,
                    @HoraProgramada = ?,
                    @Lugar = ?,
                    @Modalidad = ?,
                    @EnlaceVirtual = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.fecha_programada,
                payload.hora_programada,
                _clean(payload.lugar),
                _clean(payload.modalidad),
                _clean(payload.enlace_virtual),
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo programar la defensa de grado") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Defensa de grado programada.")


@router.post("/defensa-grado/calificar")
def grade_defensa_grado(
    payload: DefensaCalificacionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_CalificarDefensaGrado
                    @ExpedienteId = ?,
                    @NotaTrabajoEscrito = ?,
                    @NotaDefensaOral = ?,
                    @Observacion = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.nota_trabajo_escrito,
                payload.nota_defensa_oral,
                _clean(payload.observacion),
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo calificar la defensa de grado") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Defensa de grado calificada.")


@router.post("/tribunal")
def add_titulacion_tribunal(
    payload: TitulacionTribunalPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                EXEC tit.sp_RegistrarTribunalTitulacion
                    @ExpedienteId = ?,
                    @MecanismoCodigo = ?,
                    @RolTribunal = ?,
                    @NombreMiembro = ?,
                    @CedulaMiembro = ?,
                    @CorreoMiembro = ?,
                    @OrdenFirma = ?,
                    @Usuario = ?
                """,
                payload.expediente_id,
                payload.mecanismo_codigo,
                _clean(payload.rol_tribunal),
                _clean(payload.nombre_miembro),
                _clean(payload.cedula_miembro),
                _clean(payload.correo_miembro),
                payload.orden_firma,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el tribunal") from exc

    return _response_after_mechanism_update(payload.expediente_id, "Miembro del tribunal registrado.")


@router.post("/sincronizar-practicas")
def sync_titulacion_practicas(
    payload: TitulacionSyncPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=payload.expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")
            cursor.execute(
                "EXEC etl.sp_SincronizarCumplimientoPracticasVinculacion @ExpedienteId = ?, @Usuario = ?",
                payload.expediente_id,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
            cedula = _clean(expediente["NumeroIdentificacion"])
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo sincronizar prácticas y vinculación con la sociedad") from exc

    return {"ok": True, "message": "Prácticas y vinculación con la sociedad sincronizadas.", **_response_payload(cedula, payload.expediente_id)}


@router.post("/notas")
def save_titulacion_notas(
    payload: TitulacionNotasPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=payload.expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")

            cedula = _clean(expediente["NumeroIdentificacion"])
            academic = _academic_status(cedula, _clean(expediente.get("CodAnioBasica")))
            promedio = payload.promedio_asignaturas
            if promedio is None and academic.get("promedio_asignaturas") is not None:
                promedio = float(academic["promedio_asignaturas"])
            nota_titulacion = payload.nota_proceso_titulacion
            nota_80 = round(promedio * 0.80, 2) if promedio is not None else None
            nota_20 = round(nota_titulacion * 0.20, 2) if nota_titulacion is not None else None
            nota_final = round((nota_80 or 0) + (nota_20 or 0), 2) if nota_80 is not None and nota_20 is not None else None

            cursor.execute(
                """
                UPDATE tit.ExpedienteTitulacion
                   SET CedulaValidada = ?,
                       TituloBachillerCumple = ?,
                       InglesA2Cumple = ?,
                       MallaCurricularCumple = ?,
                       NoAdeudaFinanciero = ?,
                       AptoSustentacion = ?,
                       RubricaTitulacionCumple = ?,
                       PromedioAsignaturas = ?,
                       NotaPromedioAsignaturas80 = ?,
                       NotaProcesoTitulacion20 = ?,
                       NotaFinalGrado = ?,
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE ExpedienteId = ?
                """,
                1 if payload.cedula_validada else 0,
                1 if payload.titulo_bachiller_cumple else 0,
                1 if payload.ingles_a2_cumple else 0,
                1 if academic.get("malla_finalizada") else 0,
                1 if payload.no_adeuda_financiero else 0,
                1 if payload.apto_sustentacion else 0,
                1 if payload.rubrica_titulacion_cumple else 0,
                promedio,
                nota_80,
                nota_20,
                nota_final,
                current_user.login,
                payload.expediente_id,
            )
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo guardar notas y requisitos") from exc

    return {"ok": True, "message": "Notas y requisitos actualizados.", **_response_payload(cedula, payload.expediente_id)}


@router.post("/documentos")
async def upload_titulacion_document(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    expediente_id: Annotated[int, Form()],
    tipo_documento_codigo: Annotated[str, Form()],
    observacion: Annotated[str, Form()] = "",
    file: UploadFile = File(...),
) -> dict[str, Any]:
    doc_type = _clean(tipo_documento_codigo).upper()
    if doc_type not in _DOCUMENT_FORMATS:
        raise HTTPException(status_code=400, detail="Tipo de documento de titulación no válido.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Selecciona un archivo.")
    extension = Path(file.filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no permitido.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera 30 MB.")

    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")

            folder_key = _safe_filename(_clean(expediente["NumeroIdentificacion"]) or str(expediente_id), str(expediente_id))
            target_dir = _UPLOAD_ROOT / folder_key
            target_dir.mkdir(parents=True, exist_ok=True)
            stored_name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}_{_safe_filename(file.filename, 'documento')}"
            target = (target_dir / stored_name).resolve()
            if _UPLOAD_ROOT.resolve() not in target.parents:
                raise HTTPException(status_code=400, detail="Ruta de archivo inválida.")
            target.write_bytes(content)
            relative_path = f"{folder_key}/{stored_name}"
            ruta_nube = _public_url(relative_path)

            cursor.execute(
                """
                INSERT INTO doc.DocumentoExpediente
                (
                    ExpedienteId,
                    TipoDocumentoCodigo,
                    FormatoCargaCodigo,
                    NombreArchivo,
                    RutaNube,
                    HashSha256,
                    EsFirmadoElectronico,
                    FechaDocumento,
                    UsuarioCarga,
                    Observacion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CAST(GETDATE() AS DATE), ?, ?)
                """,
                expediente_id,
                doc_type,
                _DOCUMENT_FORMATS[doc_type],
                _clean(file.filename),
                ruta_nube,
                pyodbc.Binary(sha256(content).digest()),
                1 if doc_type == "ACTA_GRADO" else 0,
                current_user.login,
                _clean(observacion),
            )
            conn.commit()
            cedula = _clean(expediente["NumeroIdentificacion"])
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        if "target" in locals() and target.exists():
            target.unlink()
            parent = target.parent
            while parent != _UPLOAD_ROOT and parent.exists() and not any(parent.iterdir()):
                shutil.rmtree(parent)
                parent = parent.parent
        raise _db_error(exc, "No se pudo registrar documento de titulación") from exc

    return {"ok": True, "message": "Documento de titulación cargado.", **_response_payload(cedula, expediente_id)}


@router.post("/acta-grado")
def generate_acta_grado(
    payload: ActaGradoPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=payload.expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")
            cedula = _clean(expediente["NumeroIdentificacion"])
            approved, mechanism_message = _mechanism_approved(cursor, payload.expediente_id)
            if not approved:
                raise HTTPException(status_code=400, detail=f"No se puede generar acta: {mechanism_message}")
            cursor.execute(
                """
                EXEC tit.sp_GenerarActaGradoDesdeParametros
                    @NumeroIdentificacion = ?,
                    @ExpedienteId = ?,
                    @FechaActa = ?,
                    @HoraActa = ?,
                    @NumeroActaGrado = ?,
                    @Ciudad = ?,
                    @Escuela = ?,
                    @AutoridadAcademica = ?,
                    @DocenteEvaluador = ?,
                    @CoordinadorAcademico = ?,
                    @RutaActaPDF = ?,
                    @Usuario = ?
                """,
                cedula,
                payload.expediente_id,
                payload.fecha_acta,
                payload.hora_acta,
                _clean(payload.numero_acta_grado) or None,
                _clean(payload.ciudad) or "Quito",
                _clean(payload.escuela) or None,
                _clean(payload.autoridad_academica) or None,
                _clean(payload.docente_evaluador) or None,
                _clean(payload.coordinador_academico) or None,
                _clean(payload.ruta_acta_pdf) or None,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo generar o registrar el acta de grado") from exc

    return {"ok": True, "message": "Acta de grado registrada.", **_response_payload(cedula, payload.expediente_id)}


@router.post("/titulo-senescyt")
def register_titulo_senescyt(
    payload: TituloSenescytPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    E.ExpedienteId,
                    ER.NumeroIdentificacion
                FROM tit.ExpedienteTitulacion E
                INNER JOIN core.EstudianteRef ER
                    ON ER.EstudianteRefId = E.EstudianteRefId
                WHERE E.NumeroActaGrado COLLATE Modern_Spanish_CI_AS = ? COLLATE Modern_Spanish_CI_AS
                ORDER BY E.ExpedienteId DESC
                """,
                payload.numero_acta_grado,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No existe expediente con ese número de acta.")
            expediente_id = int(row.ExpedienteId)
            cedula = _clean(row.NumeroIdentificacion)
            cursor.execute(
                """
                EXEC tit.sp_RegistrarTituloSenescyt
                    @NumeroActaGrado = ?,
                    @CodigoRegistroSenescyt = ?,
                    @FechaRegistro = ?,
                    @RutaDocumentoNube = ?,
                    @Usuario = ?
                """,
                _clean(payload.numero_acta_grado),
                _clean(payload.codigo_registro_senescyt),
                payload.fecha_registro,
                _clean(payload.ruta_documento_nube) or None,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el título SENESCYT") from exc

    return {"ok": True, "message": "Título SENESCYT registrado.", **_response_payload(cedula, expediente_id)}


@router.post("/titulo-intec")
def register_titulo_intec(
    payload: TituloIntecPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    E.ExpedienteId,
                    ER.NumeroIdentificacion
                FROM tit.ExpedienteTitulacion E
                INNER JOIN core.EstudianteRef ER
                    ON ER.EstudianteRefId = E.EstudianteRefId
                WHERE E.NumeroActaGrado COLLATE Modern_Spanish_CI_AS = ? COLLATE Modern_Spanish_CI_AS
                ORDER BY E.ExpedienteId DESC
                """,
                payload.numero_acta_grado,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No existe expediente con ese número de acta.")
            expediente_id = int(row.ExpedienteId)
            cedula = _clean(row.NumeroIdentificacion)
            cursor.execute(
                """
                EXEC tit.sp_RegistrarTituloIntec
                    @NumeroActaGrado = ?,
                    @NumeroTitulo = ?,
                    @FechaEmision = ?,
                    @CodigoVerificacion = ?,
                    @RutaDocumentoNube = ?,
                    @Usuario = ?
                """,
                _clean(payload.numero_acta_grado),
                _clean(payload.numero_titulo),
                payload.fecha_emision,
                _clean(payload.codigo_verificacion) or None,
                _clean(payload.ruta_documento_nube) or None,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el título INTEC") from exc

    return {"ok": True, "message": "Título INTEC registrado.", **_response_payload(cedula, expediente_id)}


@router.post("/generar")
def generate_titulacion(
    payload: TitulacionSyncPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            expediente = _fetch_expediente(cursor, expediente_id=payload.expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="No existe expediente de titulación.")
            cedula = _clean(expediente["NumeroIdentificacion"])
            approved, mechanism_message = _mechanism_approved(cursor, payload.expediente_id)
            if not approved:
                raise HTTPException(
                    status_code=400,
                    detail=f"No se puede generar titulación: {mechanism_message}",
                )
            cursor.execute(
                """
                EXEC tit.sp_GenerarTitulacionSegunParametros
                    @NumeroIdentificacion = ?,
                    @ExpedienteId = ?,
                    @Usuario = ?,
                    @ForzarRecalculoNotas = 0
                """,
                cedula,
                payload.expediente_id,
                current_user.login,
            )
            while cursor.nextset():
                pass
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo generar titulación") from exc

    return {"ok": True, "message": "Expediente marcado según parámetros de titulación.", **_response_payload(cedula, payload.expediente_id)}
