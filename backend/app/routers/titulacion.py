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


class TitulacionGrupoPayload(BaseModel):
    mecanismo_codigo: str = Field(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")
    nombre_grupo: str = Field(min_length=3, max_length=250)
    codigo_grupo: str | None = Field(default=None, max_length=80)
    expediente_ids: list[int] = Field(min_length=1)
    fecha_programada: str | None = None
    hora_programada: str | None = Field(default=None, max_length=20)
    lugar: str | None = Field(default=None, max_length=250)
    modalidad: str | None = Field(default=None, max_length=30)
    enlace_virtual: str | None = Field(default=None, max_length=1000)
    codigo_examen: str | None = Field(default=None, max_length=80)
    tipo_examen: str | None = Field(default=None, max_length=80)
    tema_trabajo: str | None = Field(default=None, max_length=500)
    linea_investigacion: str | None = Field(default=None, max_length=250)
    tutor: str | None = Field(default=None, max_length=200)
    lector_oponente: str | None = Field(default=None, max_length=200)
    observacion: str | None = Field(default=None, max_length=1000)


class TitulacionEvaluadorInput(BaseModel):
    orden_evaluador: int = Field(ge=1, le=3)
    rol_evaluador: str = Field(default="EVALUADOR", max_length=50)
    nombre_evaluador: str = Field(min_length=3, max_length=200)
    cedula_evaluador: str | None = Field(default=None, max_length=20)
    correo_evaluador: str | None = Field(default=None, max_length=200)


class TitulacionGrupoEvaluadoresPayload(BaseModel):
    evaluadores: list[TitulacionEvaluadorInput] = Field(min_length=3, max_length=3)


class TitulacionCalificacionEvaluadorInput(BaseModel):
    orden_evaluador: int = Field(ge=1, le=3)
    nota_trabajo_escrito: float = Field(ge=0, le=10)
    nota_evaluacion_oral: float = Field(ge=0, le=10)
    observacion: str | None = Field(default=None, max_length=1000)


class TitulacionGrupoCalificacionesPayload(BaseModel):
    expediente_id: int
    calificaciones: list[TitulacionCalificacionEvaluadorInput] = Field(min_length=3, max_length=3)


class TitulacionRubricaCriterioPayload(BaseModel):
    codigo_criterio: str = Field(min_length=2, max_length=80)
    nombre_criterio: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=1000)
    peso: float = Field(gt=0, le=1)
    puntaje_maximo: float = Field(default=10, gt=0, le=100)
    orden: int = Field(default=1, ge=1, le=100)


class TitulacionRubricaPayload(BaseModel):
    mecanismo_codigo: str = Field(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")
    codigo_rubrica: str = Field(min_length=2, max_length=80)
    nombre_rubrica: str = Field(min_length=2, max_length=200)
    version_rubrica: str = Field(default="1.0", max_length=20)
    criterios: list[TitulacionRubricaCriterioPayload] = Field(min_length=1)


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
    if row is None:
        return {}
    columns = [column[0] for column in cursor.description or []]
    return {column: getattr(row, column) for column in columns}


def _fetch_all(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


def _param_float(cursor: pyodbc.Cursor, code: str, default: float) -> float:
    cursor.execute(
        """
        SELECT TOP (1) Valor
        FROM cat.ParametroGeneral
        WHERE Codigo COLLATE Modern_Spanish_CI_AS = ? COLLATE Modern_Spanish_CI_AS
          AND Activo = 1
        """,
        code,
    )
    row = cursor.fetchone()
    try:
        return float(row.Valor) if row and row.Valor is not None else default
    except (TypeError, ValueError):
        return default


def _param_int(cursor: pyodbc.Cursor, code: str, default: int) -> int:
    cursor.execute(
        """
        SELECT TOP (1) Valor
        FROM cat.ParametroGeneral
        WHERE Codigo COLLATE Modern_Spanish_CI_AS = ? COLLATE Modern_Spanish_CI_AS
          AND Activo = 1
        """,
        code,
    )
    row = cursor.fetchone()
    try:
        return int(float(row.Valor)) if row and row.Valor is not None else default
    except (TypeError, ValueError):
        return default


def _titulation_parameters(cursor: pyodbc.Cursor) -> dict[str, float | int]:
    return {
        "peso_asignaturas": _param_float(cursor, "TIT_PESO_ASIGNATURAS", 0.80),
        "peso_titulacion": _param_float(cursor, "TIT_PESO_TITULACION", 0.20),
        "nota_minima": _param_float(cursor, "TIT_NOTA_MINIMA_APROBACION", 7.00),
        "max_estudiantes_defensa": _param_int(cursor, "TIT_MAX_ESTUDIANTES_DEFENSA", 2),
        "evaluadores_requeridos": _param_int(cursor, "TIT_EVALUADORES_REQUERIDOS", 3),
    }


def _unique_ids(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        item = int(value)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _placeholders(values: list[Any]) -> str:
    return ",".join("?" for _ in values)


def _mechanism_id(cursor: pyodbc.Cursor, mechanism_code: str) -> int:
    cursor.execute(
        """
        SELECT TOP (1) MecanismoTitulacionId
        FROM cat.MecanismoTitulacion
        WHERE Codigo COLLATE Modern_Spanish_CI_AS = ? COLLATE Modern_Spanish_CI_AS
          AND Activo = 1
        """,
        mechanism_code,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Mecanismo de titulación no válido.")
    return int(row.MecanismoTitulacionId)


def _validate_group_students(
    cursor: pyodbc.Cursor,
    mechanism_code: str,
    expediente_ids: list[int],
) -> list[dict[str, Any]]:
    ids = _unique_ids(expediente_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos un expediente.")

    parameters = _titulation_parameters(cursor)
    if mechanism_code == "DEFENSA_GRADO" and len(ids) > int(parameters["max_estudiantes_defensa"]):
        raise HTTPException(status_code=400, detail="La defensa de grado permite máximo 2 estudiantes.")

    cursor.execute(
        f"""
        SELECT
            E.ExpedienteId,
            ER.NumeroIdentificacion,
            ER.ApellidosNombres,
            E.CedulaValidada,
            E.TituloBachillerCumple,
            E.InglesA2Cumple,
            E.VinculacionCumple,
            E.PracticasPreprofesionalesCumple,
            E.MallaCurricularCumple,
            E.NoAdeudaFinanciero,
            E.AptoSustentacion,
            E.PromedioAsignaturas
        FROM tit.ExpedienteTitulacion E
        INNER JOIN core.EstudianteRef ER
            ON ER.EstudianteRefId = E.EstudianteRefId
        WHERE E.ExpedienteId IN ({_placeholders(ids)})
        """,
        *ids,
    )
    rows = _fetch_all(cursor)
    found_ids = {int(row["ExpedienteId"]) for row in rows}
    missing_ids = [value for value in ids if value not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"No existen expedientes: {', '.join(map(str, missing_ids))}")

    requirement_labels = {
        "CedulaValidada": "cédula validada",
        "TituloBachillerCumple": "título de bachiller",
        "InglesA2Cumple": "inglés A2",
        "VinculacionCumple": "Servicio Comunitario",
        "PracticasPreprofesionalesCumple": "Prácticas laborales",
        "MallaCurricularCumple": "malla curricular",
        "NoAdeudaFinanciero": "no adeudar valores",
        "AptoSustentacion": "sustentación APTO",
    }
    blocked: list[str] = []
    for row in rows:
        missing = [label for key, label in requirement_labels.items() if not _bool_db(row.get(key))]
        if row.get("PromedioAsignaturas") is None:
            missing.append("promedio académico")
        if missing:
            student = _clean(row.get("ApellidosNombres")) or _clean(row.get("NumeroIdentificacion"))
            blocked.append(f"{student}: {', '.join(missing)}")
    if blocked:
        raise HTTPException(
            status_code=400,
            detail="Hay estudiantes que aún no cumplen requisitos de titulación. " + " | ".join(blocked),
        )
    return rows


def _fetch_group(cursor: pyodbc.Cursor, grupo_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT TOP (1) *
        FROM rpt.vw_GrupoTitulacionDetalle
        WHERE GrupoTitulacionId = ?
        """,
        grupo_id,
    )
    row = cursor.fetchone()
    if not row:
        return None
    group = _row_dict(cursor, row)

    cursor.execute(
        """
        SELECT
            GE.GrupoTitulacionExpedienteId,
            GE.ExpedienteId,
            GE.OrdenEstudiante,
            ER.NumeroIdentificacion,
            ER.ApellidosNombres,
            CR.NombreCarrera,
            E.CodAnioBasica,
            E.CodigoPeriodo,
            E.EstadoExpediente,
            E.PromedioAsignaturas,
            E.NotaPromedioAsignaturas80,
            E.NotaProcesoTitulacion20,
            E.NotaFinalGrado,
            E.NumeroActaGrado
        FROM tit.GrupoTitulacionExpediente GE
        INNER JOIN tit.ExpedienteTitulacion E
            ON E.ExpedienteId = GE.ExpedienteId
        INNER JOIN core.EstudianteRef ER
            ON ER.EstudianteRefId = E.EstudianteRefId
        LEFT JOIN core.CarreraRef CR
            ON CR.CarreraRefId = E.CarreraRefId
        WHERE GE.GrupoTitulacionId = ?
          AND GE.Activo = 1
        ORDER BY ISNULL(GE.OrdenEstudiante, 999), ER.ApellidosNombres
        """,
        grupo_id,
    )
    group["estudiantes"] = _fetch_all(cursor)

    cursor.execute(
        """
        SELECT
            EvaluadorTitulacionId,
            OrdenEvaluador,
            RolEvaluador,
            NombreEvaluador,
            CedulaEvaluador,
            CorreoEvaluador
        FROM tit.EvaluadorTitulacion
        WHERE GrupoTitulacionId = ?
          AND Activo = 1
        ORDER BY OrdenEvaluador
        """,
        grupo_id,
    )
    group["evaluadores"] = _fetch_all(cursor)

    cursor.execute(
        """
        SELECT
            C.CalificacionEvaluadorTitulacionId,
            C.ExpedienteId,
            E.OrdenEvaluador,
            E.RolEvaluador,
            E.NombreEvaluador,
            C.NotaTrabajoEscrito,
            C.NotaEvaluacionOral,
            C.NotaTotalSobre20,
            C.Observacion
        FROM tit.CalificacionEvaluadorTitulacion C
        INNER JOIN tit.EvaluadorTitulacion E
            ON E.EvaluadorTitulacionId = C.EvaluadorTitulacionId
        WHERE C.GrupoTitulacionId = ?
          AND C.Activo = 1
        ORDER BY C.ExpedienteId, E.OrdenEvaluador
        """,
        grupo_id,
    )
    group["calificaciones"] = _fetch_all(cursor)
    return group


def _group_or_404(cursor: pyodbc.Cursor, grupo_id: int) -> dict[str, Any]:
    group = _fetch_group(cursor, grupo_id)
    if not group:
        raise HTTPException(status_code=404, detail="No existe grupo de titulación.")
    return group


def _sync_group_programming(
    cursor: pyodbc.Cursor,
    payload: TitulacionGrupoPayload,
    expediente_id: int,
    login: str,
) -> None:
    cursor.execute(
        """
        EXEC tit.sp_SeleccionarMecanismoTitulacion
            @ExpedienteId = ?,
            @MecanismoCodigo = ?,
            @Usuario = ?
        """,
        expediente_id,
        payload.mecanismo_codigo,
        login,
    )
    while cursor.nextset():
        pass

    if payload.fecha_programada:
        if payload.mecanismo_codigo == "EXAMEN_COMPLEXIVO":
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
                expediente_id,
                payload.fecha_programada,
                payload.hora_programada,
                _clean(payload.lugar),
                _clean(payload.modalidad),
                _clean(payload.enlace_virtual),
                login,
            )
        else:
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
                expediente_id,
                payload.fecha_programada,
                payload.hora_programada,
                _clean(payload.lugar),
                _clean(payload.modalidad),
                _clean(payload.enlace_virtual),
                login,
            )
        while cursor.nextset():
            pass

    if payload.mecanismo_codigo == "DEFENSA_GRADO" and _clean(payload.tema_trabajo):
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
            expediente_id,
            _clean(payload.tema_trabajo),
            _clean(payload.linea_investigacion),
            _clean(payload.tutor),
            _clean(payload.lector_oponente),
            login,
        )
        while cursor.nextset():
            pass

    cursor.execute(
        """
        UPDATE tit.ExpedienteTitulacion
           SET EstadoExpediente = CASE
                    WHEN EstadoExpediente IN ('BORRADOR', 'PREVALIDADO', 'EGRESAMIENTO') THEN 'EGRESAMIENTO'
                    ELSE EstadoExpediente
               END,
               FechaActualizacion = SYSDATETIME(),
               UsuarioActualizacion = ?
         WHERE ExpedienteId = ?
        """,
        login,
        expediente_id,
    )


def _upsert_evaluator_as_tribunal(
    cursor: pyodbc.Cursor,
    group: dict[str, Any],
    evaluator: TitulacionEvaluadorInput,
    expediente_id: int,
    login: str,
) -> None:
    mechanism_id = _mechanism_id(cursor, str(group["MecanismoCodigo"]))
    cursor.execute(
        """
        UPDATE tit.TribunalTitulacion
           SET RolTribunal = ?,
               NombreMiembro = ?,
               CedulaMiembro = ?,
               CorreoMiembro = ?,
               UsuarioRegistro = ?,
               FechaRegistro = SYSDATETIME()
         WHERE ExpedienteId = ?
           AND MecanismoTitulacionId = ?
           AND ISNULL(OrdenFirma, 0) = ?
           AND Activo = 1
        """,
        _clean(evaluator.rol_evaluador),
        _clean(evaluator.nombre_evaluador),
        _clean(evaluator.cedula_evaluador) or None,
        _clean(evaluator.correo_evaluador) or None,
        login,
        expediente_id,
        mechanism_id,
        evaluator.orden_evaluador,
    )
    if cursor.rowcount and cursor.rowcount > 0:
        return
    cursor.execute(
        """
        INSERT INTO tit.TribunalTitulacion
        (
            ExpedienteId,
            MecanismoTitulacionId,
            RolTribunal,
            NombreMiembro,
            CedulaMiembro,
            CorreoMiembro,
            OrdenFirma,
            UsuarioRegistro
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        expediente_id,
        mechanism_id,
        _clean(evaluator.rol_evaluador),
        _clean(evaluator.nombre_evaluador),
        _clean(evaluator.cedula_evaluador) or None,
        _clean(evaluator.correo_evaluador) or None,
        evaluator.orden_evaluador,
        login,
    )


def _audit_titulacion(
    cursor: pyodbc.Cursor,
    *,
    entidad: str,
    accion: str,
    login: str,
    entidad_id: int | None = None,
    expediente_id: int | None = None,
    grupo_id: int | None = None,
    detalle: str | None = None,
) -> None:
    try:
        cursor.execute(
            """
            INSERT INTO aud.AuditoriaTitulacion
            (
                Entidad,
                EntidadId,
                ExpedienteId,
                GrupoTitulacionId,
                Accion,
                Detalle,
                UsuarioRegistro
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            entidad,
            entidad_id,
            expediente_id,
            grupo_id,
            accion,
            detalle,
            login,
        )
    except pyodbc.Error:
        return


def _ensure_group_grade_complete(cursor: pyodbc.Cursor, expediente_id: int) -> None:
    cursor.execute(
        """
        SELECT TOP (1)
            GT.GrupoTitulacionId,
            GT.NombreGrupo,
            COUNT(DISTINCT C.EvaluadorTitulacionId) AS TotalEvaluadores
        FROM tit.GrupoTitulacionExpediente GE
        INNER JOIN tit.GrupoTitulacion GT
            ON GT.GrupoTitulacionId = GE.GrupoTitulacionId
           AND GT.Activo = 1
        LEFT JOIN tit.CalificacionEvaluadorTitulacion C
            ON C.GrupoTitulacionId = GE.GrupoTitulacionId
           AND C.ExpedienteId = GE.ExpedienteId
           AND C.Activo = 1
        WHERE GE.ExpedienteId = ?
          AND GE.Activo = 1
        GROUP BY GT.GrupoTitulacionId, GT.NombreGrupo, GE.GrupoTitulacionExpedienteId
        ORDER BY GE.GrupoTitulacionExpedienteId DESC
        """,
        expediente_id,
    )
    row = cursor.fetchone()
    if not row:
        return
    required_evaluators = int(_titulation_parameters(cursor)["evaluadores_requeridos"])
    total_evaluators = int(row.TotalEvaluadores or 0)
    if total_evaluators < required_evaluators:
        raise HTTPException(
            status_code=400,
            detail=(
                "No se puede generar acta: faltan calificaciones de evaluadores "
                f"en el grupo {row.NombreGrupo}. Registradas {total_evaluators}/{required_evaluators}."
            ),
        )


def _calculate_group_grade(
    cursor: pyodbc.Cursor,
    group: dict[str, Any],
    expediente_id: int,
    login: str,
) -> dict[str, Any]:
    parameters = _titulation_parameters(cursor)
    required_evaluators = int(parameters["evaluadores_requeridos"])
    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT C.EvaluadorTitulacionId) AS total_evaluadores,
            AVG(C.NotaTrabajoEscrito) AS promedio_trabajo,
            AVG(C.NotaEvaluacionOral) AS promedio_oral,
            AVG(C.NotaTotalSobre20) AS promedio_sobre20
        FROM tit.CalificacionEvaluadorTitulacion C
        INNER JOIN tit.EvaluadorTitulacion E
            ON E.EvaluadorTitulacionId = C.EvaluadorTitulacionId
           AND E.Activo = 1
        WHERE C.GrupoTitulacionId = ?
          AND C.ExpedienteId = ?
          AND C.Activo = 1
        """,
        int(group["GrupoTitulacionId"]),
        expediente_id,
    )
    summary = cursor.fetchone()
    total_evaluators = int(summary.total_evaluadores or 0) if summary else 0
    if total_evaluators < required_evaluators:
        raise HTTPException(status_code=400, detail=f"Debes registrar notas de {required_evaluators} evaluadores.")

    promedio_trabajo = round(float(summary.promedio_trabajo or 0), 2)
    promedio_oral = round(float(summary.promedio_oral or 0), 2)
    nota_sobre20 = round(float(summary.promedio_sobre20 or 0), 2)
    nota_proceso_sobre10 = round(nota_sobre20 / 2, 2)
    peso_asignaturas = float(parameters["peso_asignaturas"])
    peso_titulacion = float(parameters["peso_titulacion"])
    factor_titulacion = peso_titulacion / 2
    nota_titulacion_equivalente = round(nota_sobre20 * factor_titulacion, 2)
    nota_minima = float(parameters["nota_minima"])

    cursor.execute(
        """
        SELECT PromedioAsignaturas
        FROM tit.ExpedienteTitulacion
        WHERE ExpedienteId = ?
        """,
        expediente_id,
    )
    expediente = cursor.fetchone()
    if not expediente or expediente.PromedioAsignaturas is None:
        raise HTTPException(status_code=400, detail="El expediente no tiene promedio académico disponible.")
    promedio_asignaturas = round(float(expediente.PromedioAsignaturas), 2)
    nota_asignaturas_equivalente = round(promedio_asignaturas * peso_asignaturas, 2)
    nota_final = round(nota_asignaturas_equivalente + nota_titulacion_equivalente, 2)
    aprobado = nota_final >= nota_minima and nota_proceso_sobre10 >= nota_minima

    if group["MecanismoCodigo"] == "EXAMEN_COMPLEXIVO":
        cursor.execute(
            """
            UPDATE tit.ExamenComplexivo
               SET CodigoExamen = COALESCE(?, CodigoExamen),
                   TipoExamen = COALESCE(?, TipoExamen),
                   NotaExamen = ?,
                   NotaPonderada20 = ?,
                   Aprobado = ?,
                   Observacion = COALESCE(?, Observacion),
                   FechaActualizacion = SYSDATETIME()
             WHERE ExpedienteId = ?
            """,
            _clean(group.get("CodigoExamen")) or None,
            _clean(group.get("TipoExamen")) or None,
            nota_proceso_sobre10,
            nota_titulacion_equivalente,
            1 if aprobado else 0,
            _clean(group.get("Observacion")) or None,
            expediente_id,
        )
        if cursor.rowcount is None or cursor.rowcount <= 0:
            cursor.execute(
                """
                INSERT INTO tit.ExamenComplexivo
                (
                    ExpedienteId,
                    CodigoExamen,
                    TipoExamen,
                    NotaExamen,
                    NotaPonderada20,
                    Aprobado,
                    Observacion,
                    UsuarioRegistro
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                expediente_id,
                _clean(group.get("CodigoExamen")) or None,
                _clean(group.get("TipoExamen")) or None,
                nota_proceso_sobre10,
                nota_titulacion_equivalente,
                1 if aprobado else 0,
                _clean(group.get("Observacion")) or None,
                login,
            )
    else:
        cursor.execute(
            """
            UPDATE tit.DefensaGrado
               SET TemaTrabajo = COALESCE(?, TemaTrabajo),
                   LineaInvestigacion = COALESCE(?, LineaInvestigacion),
                   Tutor = COALESCE(?, Tutor),
                   LectorOponente = COALESCE(?, LectorOponente),
                   NotaTrabajoEscrito = ?,
                   NotaDefensaOral = ?,
                   NotaFinalDefensa = ?,
                   NotaPonderada20 = ?,
                   Aprobado = ?,
                   Observacion = COALESCE(?, Observacion),
                   FechaActualizacion = SYSDATETIME()
             WHERE ExpedienteId = ?
            """,
            _clean(group.get("TemaTrabajo")) or None,
            _clean(group.get("LineaInvestigacion")) or None,
            _clean(group.get("Tutor")) or None,
            _clean(group.get("LectorOponente")) or None,
            promedio_trabajo,
            promedio_oral,
            nota_proceso_sobre10,
            nota_titulacion_equivalente,
            1 if aprobado else 0,
            _clean(group.get("Observacion")) or None,
            expediente_id,
        )
        if cursor.rowcount is None or cursor.rowcount <= 0:
            cursor.execute(
                """
                INSERT INTO tit.DefensaGrado
                (
                    ExpedienteId,
                    TemaTrabajo,
                    LineaInvestigacion,
                    Tutor,
                    LectorOponente,
                    NotaTrabajoEscrito,
                    NotaDefensaOral,
                    NotaFinalDefensa,
                    NotaPonderada20,
                    Aprobado,
                    Observacion,
                    UsuarioRegistro
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                expediente_id,
                _clean(group.get("TemaTrabajo")) or None,
                _clean(group.get("LineaInvestigacion")) or None,
                _clean(group.get("Tutor")) or None,
                _clean(group.get("LectorOponente")) or None,
                promedio_trabajo,
                promedio_oral,
                nota_proceso_sobre10,
                nota_titulacion_equivalente,
                1 if aprobado else 0,
                _clean(group.get("Observacion")) or None,
                login,
            )

    cursor.execute(
        """
        UPDATE tit.ExpedienteTitulacion
           SET NotaPromedioAsignaturas80 = ?,
               NotaProcesoTitulacion20 = ?,
               NotaFinalGrado = ?,
               RubricaTitulacionCumple = 1,
               EstadoExpediente = CASE WHEN ? = 1 THEN 'APROBADO_TITULACION' ELSE 'REPROBADO_TITULACION' END,
               FechaActualizacion = SYSDATETIME(),
               UsuarioActualizacion = ?
         WHERE ExpedienteId = ?
        """,
        nota_asignaturas_equivalente,
        nota_titulacion_equivalente,
        nota_final,
        1 if aprobado else 0,
        login,
        expediente_id,
    )

    cursor.execute(
        """
        MERGE tit.CalificacionConsolidadaTitulacion AS T
        USING (
            SELECT
                ? AS GrupoTitulacionId,
                ? AS ExpedienteId
        ) AS S
        ON T.GrupoTitulacionId = S.GrupoTitulacionId
       AND T.ExpedienteId = S.ExpedienteId
        WHEN MATCHED THEN
            UPDATE SET
                MecanismoCodigo = ?,
                TotalEvaluadores = ?,
                PromedioTrabajoEscrito = ?,
                PromedioEvaluacionOral = ?,
                NotaTitulacionSobre20 = ?,
                NotaTitulacionSobre10 = ?,
                NotaAsignaturasSobre10 = ?,
                EquivalenciaAsignaturas = ?,
                EquivalenciaTitulacion = ?,
                NotaFinalGrado = ?,
                Aprobado = ?,
                FechaActualizacion = SYSDATETIME()
        WHEN NOT MATCHED THEN
            INSERT
            (
                GrupoTitulacionId,
                ExpedienteId,
                MecanismoCodigo,
                TotalEvaluadores,
                PromedioTrabajoEscrito,
                PromedioEvaluacionOral,
                NotaTitulacionSobre20,
                NotaTitulacionSobre10,
                NotaAsignaturasSobre10,
                EquivalenciaAsignaturas,
                EquivalenciaTitulacion,
                NotaFinalGrado,
                Aprobado,
                UsuarioRegistro
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        int(group["GrupoTitulacionId"]),
        expediente_id,
        _clean(group.get("MecanismoCodigo")),
        total_evaluators,
        promedio_trabajo,
        promedio_oral,
        nota_sobre20,
        nota_proceso_sobre10,
        promedio_asignaturas,
        nota_asignaturas_equivalente,
        nota_titulacion_equivalente,
        nota_final,
        1 if aprobado else 0,
        int(group["GrupoTitulacionId"]),
        expediente_id,
        _clean(group.get("MecanismoCodigo")),
        total_evaluators,
        promedio_trabajo,
        promedio_oral,
        nota_sobre20,
        nota_proceso_sobre10,
        promedio_asignaturas,
        nota_asignaturas_equivalente,
        nota_titulacion_equivalente,
        nota_final,
        1 if aprobado else 0,
        login,
    )

    return {
        "expediente_id": expediente_id,
        "promedio_asignaturas": promedio_asignaturas,
        "nota_asignaturas_80": nota_asignaturas_equivalente,
        "promedio_trabajo_escrito": promedio_trabajo,
        "promedio_evaluacion_oral": promedio_oral,
        "nota_titulacion_sobre20": nota_sobre20,
        "nota_titulacion_sobre10": nota_proceso_sobre10,
        "nota_titulacion_20": nota_titulacion_equivalente,
        "nota_final": nota_final,
        "aprobado": aprobado,
        "parametros": parameters,
    }


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
            pendientes.append("Prácticas laborales")
        if not cumple_vinculacion:
            pendientes.append("Servicio Comunitario")
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
            "practicas": f"Prácticas laborales cumplidas ({_HORAS_REQUERIDAS_PRACTICAS} horas)",
            "vinculacion": f"Servicio Comunitario cumplido ({_HORAS_REQUERIDAS_VINCULACION} horas)",
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
                COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) COLLATE DATABASE_DEFAULT LIKE ?
                OR COALESCE(ER.ApellidosNombres, E.NumeroIdentificacion) COLLATE DATABASE_DEFAULT LIKE ?
                OR COALESCE(CR.NombreCarrera, E.Carrera) COLLATE DATABASE_DEFAULT LIKE ?
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
                    COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) AS NumeroIdentificacion,
                    COALESCE(ER.ApellidosNombres, E.NumeroIdentificacion) AS ApellidosNombres,
                    COALESCE(CR.NombreCarrera, E.Carrera) AS NombreCarrera,
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
                LEFT JOIN core.EstudianteRef ER
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
                    COALESCE(ER.ApellidosNombres, E.NumeroIdentificacion)
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


@router.get("/parametros")
def get_titulacion_parametros(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            parameters = _titulation_parameters(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar parámetros de titulación") from exc
    return {"items": parameters}


@router.get("/dashboard/resumen")
@router.get("/dashboard")
def get_titulacion_dashboard(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT TOP (1) * FROM rpt.vw_DashboardTitulacion")
            summary = {
                key: 0 if value is None else value
                for key, value in (_row_dict(cursor, cursor.fetchone()) or {}).items()
            }
            cursor.execute(
                """
                SELECT TOP (12)
                    EstadoExpediente,
                    COUNT(1) AS Total
                FROM tit.ExpedienteTitulacion
                GROUP BY EstadoExpediente
                ORDER BY Total DESC, EstadoExpediente
                """
            )
            by_state = _fetch_all(cursor)
            cursor.execute(
                """
                SELECT TOP (12)
                    NombreCarrera,
                    COUNT(1) AS Total
                FROM rpt.vw_ReporteExpedienteTitulacion
                GROUP BY NombreCarrera
                ORDER BY Total DESC, NombreCarrera
                """
            )
            by_career = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar dashboard de titulación") from exc
    return {"summary": summary, "by_state": by_state, "by_career": by_career}


@router.get("/reportes/expedientes")
def get_titulacion_reporte_expedientes(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    mecanismo: Annotated[str | None, Query(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")] = None,
    estado: Annotated[str | None, Query(max_length=50)] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> dict[str, Any]:
    del current_user
    filters = ["1 = 1"]
    params: list[Any] = []
    if mecanismo:
        filters.append("MecanismoCodigo = ?")
        params.append(mecanismo)
    if estado:
        filters.append("EstadoExpediente = ?")
        params.append(_clean(estado))
    if search:
        term = f"%{_clean(search)}%"
        filters.append("(NumeroIdentificacion LIKE ? OR ApellidosNombres LIKE ? OR NombreCarrera LIKE ? OR NumeroActaGrado LIKE ?)")
        params.extend([term, term, term, term])
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({int(limit)}) *
                FROM rpt.vw_ReporteExpedienteTitulacion
                WHERE {" AND ".join(filters)}
                ORDER BY ExpedienteId DESC
                """,
                *params,
            )
            items = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar reporte de expedientes de titulación") from exc
    return {"items": items, "total": len(items)}


@router.get("/auditoria")
def get_titulacion_auditoria(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    expediente_id: Annotated[int | None, Query(ge=1)] = None,
    grupo_id: Annotated[int | None, Query(ge=1)] = None,
    entidad: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
) -> dict[str, Any]:
    del current_user
    filters = ["1 = 1"]
    params: list[Any] = []
    if expediente_id:
        filters.append("ExpedienteId = ?")
        params.append(expediente_id)
    if grupo_id:
        filters.append("GrupoTitulacionId = ?")
        params.append(grupo_id)
    if entidad:
        filters.append("Entidad = ?")
        params.append(_clean(entidad))
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({int(limit)}) *
                FROM rpt.vw_AuditoriaTitulacion
                WHERE {" AND ".join(filters)}
                ORDER BY AuditoriaTitulacionId DESC
                """,
                *params,
            )
            items = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar auditoría de titulación") from exc
    return {"items": items, "total": len(items)}


@router.get("/rubricas")
def get_titulacion_rubricas(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    mecanismo: Annotated[str | None, Query(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")] = None,
) -> dict[str, Any]:
    del current_user
    filters = ["R.Activo = 1"]
    params: list[Any] = []
    if mecanismo:
        filters.append("R.MecanismoCodigo = ?")
        params.append(mecanismo)
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    R.RubricaTitulacionId,
                    R.MecanismoCodigo,
                    R.CodigoRubrica,
                    R.NombreRubrica,
                    R.VersionRubrica,
                    R.FechaRegistro
                FROM tit.RubricaTitulacion R
                WHERE {" AND ".join(filters)}
                ORDER BY R.MecanismoCodigo, R.NombreRubrica
                """,
                *params,
            )
            rubrics = _fetch_all(cursor)
            for rubric in rubrics:
                cursor.execute(
                    """
                    SELECT
                        RubricaCriterioTitulacionId,
                        CodigoCriterio,
                        NombreCriterio,
                        Descripcion,
                        Peso,
                        PuntajeMaximo,
                        Orden
                    FROM tit.RubricaCriterioTitulacion
                    WHERE RubricaTitulacionId = ?
                      AND Activo = 1
                    ORDER BY Orden, RubricaCriterioTitulacionId
                    """,
                    int(rubric["RubricaTitulacionId"]),
                )
                rubric["criterios"] = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar rúbricas de titulación") from exc
    return {"items": rubrics, "total": len(rubrics)}


@router.post("/rubricas")
def save_titulacion_rubrica(
    payload: TitulacionRubricaPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    peso_total = round(sum(float(item.peso) for item in payload.criterios), 4)
    if abs(peso_total - 1) > 0.001:
        raise HTTPException(status_code=400, detail="La suma de pesos de la rúbrica debe ser 1.00.")
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tit.RubricaTitulacion
                   SET MecanismoCodigo = ?,
                       NombreRubrica = ?,
                       VersionRubrica = ?,
                       Activo = 1,
                       FechaActualizacion = SYSDATETIME()
                 WHERE CodigoRubrica = ?
                """,
                payload.mecanismo_codigo,
                _clean(payload.nombre_rubrica),
                _clean(payload.version_rubrica) or "1.0",
                _clean(payload.codigo_rubrica),
            )
            if cursor.rowcount is None or cursor.rowcount <= 0:
                cursor.execute(
                    """
                    INSERT INTO tit.RubricaTitulacion
                    (
                        MecanismoCodigo,
                        CodigoRubrica,
                        NombreRubrica,
                        VersionRubrica,
                        UsuarioRegistro
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    payload.mecanismo_codigo,
                    _clean(payload.codigo_rubrica),
                    _clean(payload.nombre_rubrica),
                    _clean(payload.version_rubrica) or "1.0",
                    current_user.login,
                )
            cursor.execute(
                """
                SELECT TOP (1) RubricaTitulacionId
                FROM tit.RubricaTitulacion
                WHERE CodigoRubrica = ?
                """,
                _clean(payload.codigo_rubrica),
            )
            row = cursor.fetchone()
            rubrica_id = int(row.RubricaTitulacionId)
            active_codes = [_clean(item.codigo_criterio) for item in payload.criterios]
            for criterion in payload.criterios:
                cursor.execute(
                    """
                    UPDATE tit.RubricaCriterioTitulacion
                       SET NombreCriterio = ?,
                           Descripcion = ?,
                           Peso = ?,
                           PuntajeMaximo = ?,
                           Orden = ?,
                           Activo = 1,
                           FechaActualizacion = SYSDATETIME()
                     WHERE RubricaTitulacionId = ?
                       AND CodigoCriterio = ?
                    """,
                    _clean(criterion.nombre_criterio),
                    _clean(criterion.descripcion) or None,
                    criterion.peso,
                    criterion.puntaje_maximo,
                    criterion.orden,
                    rubrica_id,
                    _clean(criterion.codigo_criterio),
                )
                if cursor.rowcount is None or cursor.rowcount <= 0:
                    cursor.execute(
                        """
                        INSERT INTO tit.RubricaCriterioTitulacion
                        (
                            RubricaTitulacionId,
                            CodigoCriterio,
                            NombreCriterio,
                            Descripcion,
                            Peso,
                            PuntajeMaximo,
                            Orden,
                            UsuarioRegistro
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rubrica_id,
                        _clean(criterion.codigo_criterio),
                        _clean(criterion.nombre_criterio),
                        _clean(criterion.descripcion) or None,
                        criterion.peso,
                        criterion.puntaje_maximo,
                        criterion.orden,
                        current_user.login,
                    )
            if active_codes:
                cursor.execute(
                    f"""
                    UPDATE tit.RubricaCriterioTitulacion
                       SET Activo = 0,
                           FechaActualizacion = SYSDATETIME()
                     WHERE RubricaTitulacionId = ?
                       AND CodigoCriterio NOT IN ({_placeholders(active_codes)})
                    """,
                    rubrica_id,
                    *active_codes,
                )
            _audit_titulacion(
                cursor,
                entidad="RubricaTitulacion",
                entidad_id=rubrica_id,
                accion="GUARDAR_RUBRICA",
                detalle=f"Rúbrica {payload.codigo_rubrica} para {payload.mecanismo_codigo}",
                login=current_user.login,
            )
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo guardar rúbrica de titulación") from exc
    return {"ok": True, "message": "Rúbrica de titulación guardada.", "rubrica_id": rubrica_id}


@router.get("/grupos")
def list_titulacion_grupos(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    mecanismo: Annotated[str | None, Query(pattern="^(EXAMEN_COMPLEXIVO|DEFENSA_GRADO)$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, Any]:
    del current_user
    filters = ["1 = 1"]
    params: list[Any] = []
    if mecanismo:
        filters.append("MecanismoCodigo = ?")
        params.append(mecanismo)
    if search:
        term = f"%{_clean(search)}%"
        filters.append("(NombreGrupo LIKE ? OR CodigoGrupo LIKE ? OR TemaTrabajo LIKE ? OR CodigoExamen LIKE ?)")
        params.extend([term, term, term, term])
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({int(limit)}) *
                FROM rpt.vw_GrupoTitulacionDetalle
                WHERE {" AND ".join(filters)}
                ORDER BY
                    CASE WHEN FechaProgramada IS NULL THEN 1 ELSE 0 END,
                    FechaProgramada DESC,
                    GrupoTitulacionId DESC
                """,
                *params,
            )
            items = _fetch_all(cursor)
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar grupos de titulación") from exc
    return {
        "items": items,
        "total": len(items),
        "complexivo": sum(1 for item in items if item.get("MecanismoCodigo") == "EXAMEN_COMPLEXIVO"),
        "defensa": sum(1 for item in items if item.get("MecanismoCodigo") == "DEFENSA_GRADO"),
    }


@router.get("/grupos/{grupo_id}")
def get_titulacion_grupo(
    grupo_id: int,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            group = _group_or_404(cursor, grupo_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar grupo de titulación") from exc
    return {"item": group}


@router.post("/grupos")
def create_titulacion_grupo(
    payload: TitulacionGrupoPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    expediente_ids = _unique_ids(payload.expediente_ids)
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            _validate_group_students(cursor, payload.mecanismo_codigo, expediente_ids)
            cursor.execute(
                """
                INSERT INTO tit.GrupoTitulacion
                (
                    MecanismoCodigo,
                    NombreGrupo,
                    CodigoGrupo,
                    FechaProgramada,
                    HoraProgramada,
                    Lugar,
                    Modalidad,
                    EnlaceVirtual,
                    CodigoExamen,
                    TipoExamen,
                    TemaTrabajo,
                    LineaInvestigacion,
                    Tutor,
                    LectorOponente,
                    EstadoGrupo,
                    Observacion,
                    UsuarioRegistro
                )
                OUTPUT INSERTED.GrupoTitulacionId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                payload.mecanismo_codigo,
                _clean(payload.nombre_grupo),
                _clean(payload.codigo_grupo) or None,
                payload.fecha_programada,
                payload.hora_programada,
                _clean(payload.lugar) or None,
                _clean(payload.modalidad) or None,
                _clean(payload.enlace_virtual) or None,
                _clean(payload.codigo_examen) or None,
                _clean(payload.tipo_examen) or None,
                _clean(payload.tema_trabajo) or None,
                _clean(payload.linea_investigacion) or None,
                _clean(payload.tutor) or None,
                _clean(payload.lector_oponente) or None,
                "PROGRAMADO" if payload.fecha_programada else "BORRADOR",
                _clean(payload.observacion) or None,
                current_user.login,
            )
            group_row = cursor.fetchone()
            group_id = int(group_row.GrupoTitulacionId)
            for order, expediente_id in enumerate(expediente_ids, start=1):
                cursor.execute(
                    """
                    INSERT INTO tit.GrupoTitulacionExpediente
                    (
                        GrupoTitulacionId,
                        ExpedienteId,
                        OrdenEstudiante,
                        UsuarioRegistro
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    group_id,
                    expediente_id,
                    order,
                    current_user.login,
                )
                _sync_group_programming(cursor, payload, expediente_id, current_user.login)
            _audit_titulacion(
                cursor,
                entidad="GrupoTitulacion",
                entidad_id=group_id,
                grupo_id=group_id,
                accion="CREAR_GRUPO",
                detalle=f"Grupo {payload.nombre_grupo} con {len(expediente_ids)} expediente(s).",
                login=current_user.login,
            )
            conn.commit()
            group = _group_or_404(cursor, group_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo crear grupo de titulación") from exc
    return {"ok": True, "message": "Grupo de titulación creado.", "item": group}


@router.post("/grupos/{grupo_id}/evaluadores")
def save_titulacion_grupo_evaluadores(
    grupo_id: int,
    payload: TitulacionGrupoEvaluadoresPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    orders = [item.orden_evaluador for item in payload.evaluadores]
    if sorted(orders) != [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Debes registrar exactamente los evaluadores 1, 2 y 3.")
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            group = _group_or_404(cursor, grupo_id)
            for evaluator in payload.evaluadores:
                cursor.execute(
                    """
                    UPDATE tit.EvaluadorTitulacion
                       SET RolEvaluador = ?,
                           NombreEvaluador = ?,
                           CedulaEvaluador = ?,
                           CorreoEvaluador = ?,
                           FechaActualizacion = SYSDATETIME()
                     WHERE GrupoTitulacionId = ?
                       AND OrdenEvaluador = ?
                       AND Activo = 1
                    """,
                    _clean(evaluator.rol_evaluador),
                    _clean(evaluator.nombre_evaluador),
                    _clean(evaluator.cedula_evaluador) or None,
                    _clean(evaluator.correo_evaluador) or None,
                    grupo_id,
                    evaluator.orden_evaluador,
                )
                if cursor.rowcount is None or cursor.rowcount <= 0:
                    cursor.execute(
                        """
                        INSERT INTO tit.EvaluadorTitulacion
                        (
                            GrupoTitulacionId,
                            OrdenEvaluador,
                            RolEvaluador,
                            NombreEvaluador,
                            CedulaEvaluador,
                            CorreoEvaluador,
                            UsuarioRegistro
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        grupo_id,
                        evaluator.orden_evaluador,
                        _clean(evaluator.rol_evaluador),
                        _clean(evaluator.nombre_evaluador),
                        _clean(evaluator.cedula_evaluador) or None,
                        _clean(evaluator.correo_evaluador) or None,
                        current_user.login,
                    )
                for student in group.get("estudiantes", []):
                    _upsert_evaluator_as_tribunal(
                        cursor,
                        group,
                        evaluator,
                        int(student["ExpedienteId"]),
                        current_user.login,
                    )
            cursor.execute(
                """
                UPDATE tit.GrupoTitulacion
                   SET EstadoGrupo = CASE WHEN EstadoGrupo = 'BORRADOR' THEN 'CONFIGURADO' ELSE EstadoGrupo END,
                       FechaActualizacion = SYSDATETIME()
                 WHERE GrupoTitulacionId = ?
                """,
                grupo_id,
            )
            _audit_titulacion(
                cursor,
                entidad="EvaluadorTitulacion",
                grupo_id=grupo_id,
                accion="GUARDAR_EVALUADORES",
                detalle=f"Evaluadores registrados para grupo {grupo_id}.",
                login=current_user.login,
            )
            conn.commit()
            group = _group_or_404(cursor, grupo_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo guardar evaluadores del grupo") from exc
    return {"ok": True, "message": "Evaluadores registrados.", "item": group}


@router.post("/grupos/{grupo_id}/calificaciones")
def save_titulacion_grupo_calificaciones(
    grupo_id: int,
    payload: TitulacionGrupoCalificacionesPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    orders = [item.orden_evaluador for item in payload.calificaciones]
    if sorted(orders) != [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Debes registrar notas para los evaluadores 1, 2 y 3.")
    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            group = _group_or_404(cursor, grupo_id)
            student_ids = {int(item["ExpedienteId"]) for item in group.get("estudiantes", [])}
            if payload.expediente_id not in student_ids:
                raise HTTPException(status_code=400, detail="El expediente no pertenece a este grupo.")
            evaluators = {int(item["OrdenEvaluador"]): int(item["EvaluadorTitulacionId"]) for item in group.get("evaluadores", [])}
            missing_evaluators = [order for order in (1, 2, 3) if order not in evaluators]
            if missing_evaluators:
                raise HTTPException(status_code=400, detail="Registra primero los tres evaluadores del grupo.")

            for grade in payload.calificaciones:
                evaluator_id = evaluators[grade.orden_evaluador]
                total = round(float(grade.nota_trabajo_escrito) + float(grade.nota_evaluacion_oral), 2)
                cursor.execute(
                    """
                    UPDATE tit.CalificacionEvaluadorTitulacion
                       SET NotaTrabajoEscrito = ?,
                           NotaEvaluacionOral = ?,
                           NotaTotalSobre20 = ?,
                           Observacion = ?,
                           FechaActualizacion = SYSDATETIME()
                     WHERE GrupoTitulacionId = ?
                       AND ExpedienteId = ?
                       AND EvaluadorTitulacionId = ?
                       AND Activo = 1
                    """,
                    grade.nota_trabajo_escrito,
                    grade.nota_evaluacion_oral,
                    total,
                    _clean(grade.observacion) or None,
                    grupo_id,
                    payload.expediente_id,
                    evaluator_id,
                )
                if cursor.rowcount is None or cursor.rowcount <= 0:
                    cursor.execute(
                        """
                        INSERT INTO tit.CalificacionEvaluadorTitulacion
                        (
                            GrupoTitulacionId,
                            ExpedienteId,
                            EvaluadorTitulacionId,
                            NotaTrabajoEscrito,
                            NotaEvaluacionOral,
                            NotaTotalSobre20,
                            Observacion,
                            UsuarioRegistro
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        grupo_id,
                        payload.expediente_id,
                        evaluator_id,
                        grade.nota_trabajo_escrito,
                        grade.nota_evaluacion_oral,
                        total,
                        _clean(grade.observacion) or None,
                        current_user.login,
                    )

            result = _calculate_group_grade(cursor, group, payload.expediente_id, current_user.login)
            _audit_titulacion(
                cursor,
                entidad="CalificacionEvaluadorTitulacion",
                expediente_id=payload.expediente_id,
                grupo_id=grupo_id,
                accion="GUARDAR_CALIFICACIONES",
                detalle=f"Nota final calculada: {result.get('nota_final')}.",
                login=current_user.login,
            )
            required_evaluators = int(_titulation_parameters(cursor)["evaluadores_requeridos"])
            cursor.execute(
                """
                WITH por_estudiante AS (
                    SELECT
                        GE.ExpedienteId,
                        COUNT(DISTINCT C.EvaluadorTitulacionId) AS TotalEvaluadores
                    FROM tit.GrupoTitulacionExpediente GE
                    LEFT JOIN tit.CalificacionEvaluadorTitulacion C
                        ON C.GrupoTitulacionId = GE.GrupoTitulacionId
                       AND C.ExpedienteId = GE.ExpedienteId
                       AND C.Activo = 1
                    WHERE GE.GrupoTitulacionId = ?
                      AND GE.Activo = 1
                    GROUP BY GE.ExpedienteId
                )
                SELECT
                    COUNT(1) AS TotalEstudiantes,
                    SUM(CASE WHEN TotalEvaluadores >= ? THEN 1 ELSE 0 END) AS EstudiantesCalificados
                FROM por_estudiante
                """,
                grupo_id,
                required_evaluators,
            )
            progress = cursor.fetchone()
            if progress and int(progress.TotalEstudiantes or 0) == int(progress.EstudiantesCalificados or 0):
                cursor.execute(
                    """
                    UPDATE tit.GrupoTitulacion
                       SET EstadoGrupo = 'CALIFICADO',
                           FechaActualizacion = SYSDATETIME()
                     WHERE GrupoTitulacionId = ?
                    """,
                    grupo_id,
                )
            conn.commit()
            group = _group_or_404(cursor, grupo_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo guardar calificaciones del grupo") from exc
    return {"ok": True, "message": "Calificaciones registradas.", "resultado": result, "item": group}


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
        raise _db_error(exc, "No se pudo sincronizar Prácticas laborales y Servicio Comunitario") from exc

    return {"ok": True, "message": "Prácticas laborales y Servicio Comunitario sincronizados.", **_response_payload(cedula, payload.expediente_id)}


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
            _ensure_group_grade_complete(cursor, payload.expediente_id)
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
            _audit_titulacion(
                cursor,
                entidad="ActaGrado",
                expediente_id=payload.expediente_id,
                accion="GENERAR_ACTA",
                detalle=f"Acta {payload.numero_acta_grado or 'autogenerada'} registrada.",
                login=current_user.login,
            )
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
            _audit_titulacion(
                cursor,
                entidad="RegistroSenescyt",
                expediente_id=expediente_id,
                accion="REGISTRAR_TITULO_SENESCYT",
                detalle=f"Registro SENESCYT {payload.codigo_registro_senescyt}.",
                login=current_user.login,
            )
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
            _audit_titulacion(
                cursor,
                entidad="TituloIntec",
                expediente_id=expediente_id,
                accion="REGISTRAR_TITULO_INTEC",
                detalle=f"Título INTEC {payload.numero_titulo}.",
                login=current_user.login,
            )
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
            _ensure_group_grade_complete(cursor, payload.expediente_id)
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
            _audit_titulacion(
                cursor,
                entidad="ExpedienteTitulacion",
                entidad_id=payload.expediente_id,
                expediente_id=payload.expediente_id,
                accion="GENERAR_TITULACION",
                detalle="Generación de titulación ejecutada.",
                login=current_user.login,
            )
            conn.commit()
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo generar titulación") from exc

    return {"ok": True, "message": "Expediente marcado según parámetros de titulación.", **_response_payload(cedula, payload.expediente_id)}
