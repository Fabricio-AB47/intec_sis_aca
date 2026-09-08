from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
import pyodbc

from app.core.audit_context import get_audit_context
from app.core.security import SessionUser, require_screen_access
from app.services.db import (
    get_connection,
    get_expedient_connection,
    get_graph_database_connection,
    get_secretaria_connection,
    get_titulation_connection,
)


router = APIRouter(prefix="/api/secretaria-general", tags=["secretaria-general"])
_SCREEN_ACCESS = require_screen_access("secretaria-general")
_REQUIRED_SUBJECTS = 24
_PASSING_GRADE = 7.0
_NEAR_GRADUATION_SUBJECTS = 20
_VALID_STAGES = {"TODOS", "PROXIMO", "EGRESADO", "GRADUADO"}
_REVIEW_STATES = {"VALIDADO", "OBSERVADO", "RECHAZADO", "PRESENTE"}
_COMMON_DOCUMENT_CODES = {
    "CEDULA",
    "TITULO_BACHILLER",
    "CERTIFICADO_NO_ADEUDAMIENTO",
    "RECORD_ACADEMICO_FIRMADO",
    "CERTIFICADO_PRACTICAS",
    "CERTIFICADO_VINCULACION",
    "DOCUMENTO_INGLES",
}
_HOMOLOGATION_DOCUMENT_CODES = {
    "DOCUMENTO_CERTIFICACIONES",
    "DOCUMENTOS_UNIVERSIDAD_ORIGEN",
    "DOCUMENTO_HOMOLOGACION",
}
_HOMOLOGATION_ARTICLE_CODES = {
    "INTERNA_ART81": "HOMOLOGACION_ARTICULO_81",
    "EXTERNA_ART82": "HOMOLOGACION_ARTICULO_82",
    "EXTERNA_ART83": "HOMOLOGACION_ARTICULO_83",
}
_DOCUMENT_CODES = {
    *_COMMON_DOCUMENT_CODES,
    *_HOMOLOGATION_DOCUMENT_CODES,
    *_HOMOLOGATION_ARTICLE_CODES.values(),
}
_TRUSTED_VALID_STATES = {"VALIDADO", "APROBADO", "CERRADO", "FINALIZADO"}


class EnsureCasePayload(BaseModel):
    codigo_estud: int = Field(gt=0)


class RequirementReviewPayload(BaseModel):
    estado: Literal["VALIDADO", "OBSERVADO", "RECHAZADO", "PRESENTE"]
    observacion: str = Field(default="", max_length=1000)
    documento_presentado_id: int | None = Field(default=None, gt=0)


class HomologationClassificationPayload(BaseModel):
    tipo_homologacion: Literal["INTERNA_ART81", "EXTERNA_ART82", "EXTERNA_ART83"]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _document(value: Any) -> str:
    return re.sub(r"\D+", "", _clean(value))


def _enrollment_type(*values: Any) -> Literal["R", "H"]:
    normalized = " ".join(_clean(value).upper() for value in values if _clean(value))
    tokens = set(re.findall(r"[A-ZÁÉÍÓÚÑ]+", normalized))
    if "H" in tokens or any(token.startswith("HOMO") for token in tokens):
        return "H"
    return "R"


def _homologation_article_code(value: Any) -> str | None:
    return _HOMOLOGATION_ARTICLE_CODES.get(_clean(value).upper())


def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None and _clean(value) else None
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        return round(float(value), 2) if value is not None and _clean(value) else None
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [column[0] for column in cursor.description or []]
    return {column: _json_value(getattr(row, column)) for column in columns}


def _rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


_CANDIDATE_CTE = f"""
WITH UltimaMatriculaBase AS
(
    SELECT
        TRY_CONVERT(bigint, cxe.codigo_estud) AS codigo_estud,
        TRY_CONVERT(nvarchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
        TRY_CONVERT(nvarchar(50), cxe.codigo_periodo) AS codigo_periodo,
        TRY_CONVERT(nvarchar(20), cxe.TipoMatricula) AS tipo_matricula_origen,
        ROW_NUMBER() OVER
        (
            PARTITION BY TRY_CONVERT(bigint, cxe.codigo_estud)
            ORDER BY
                ISNULL(cxe.Fecha_Matricula, CONVERT(date, '19000101')) DESC,
                TRY_CONVERT(bigint, cxe.codigo_periodo) DESC,
                TRY_CONVERT(bigint, cxe.num) DESC
        ) AS fila
    FROM dbo.CARRERAXESTUD cxe
    WHERE TRY_CONVERT(bigint, cxe.codigo_estud) IS NOT NULL
),
UltimaMatricula AS
(
    SELECT codigo_estud, cod_anio_basica, codigo_periodo, tipo_matricula_origen
    FROM UltimaMatriculaBase
    WHERE fila = 1
),
PensumSinDuplicados AS
(
    SELECT
        TRY_CONVERT(nvarchar(50), p.Cod_AnioBasica) AS cod_anio_basica,
        TRY_CONVERT(nvarchar(50), p.codigo_materia) AS codigo_materia,
        TRY_CONVERT(int, p.Semestre) AS semestre,
        TRY_CONVERT(int, p.Orden) AS orden,
        ROW_NUMBER() OVER
        (
            PARTITION BY TRY_CONVERT(nvarchar(50), p.Cod_AnioBasica), TRY_CONVERT(nvarchar(50), p.codigo_materia)
            ORDER BY TRY_CONVERT(int, p.Semestre), TRY_CONVERT(int, p.Orden), TRY_CONVERT(nvarchar(250), p.Nomb_Materia)
        ) AS fila_materia
    FROM dbo.PENSUM p
    WHERE TRY_CONVERT(nvarchar(50), p.codigo_materia) IS NOT NULL
),
PensumOrdenado AS
(
    SELECT
        cod_anio_basica,
        codigo_materia,
        ROW_NUMBER() OVER
        (
            PARTITION BY cod_anio_basica
            ORDER BY ISNULL(semestre, 999), ISNULL(orden, 999), codigo_materia
        ) AS fila_pensum
    FROM PensumSinDuplicados
    WHERE fila_materia = 1
),
PensumBase AS
(
    SELECT cod_anio_basica, codigo_materia
    FROM PensumOrdenado
    WHERE fila_pensum <= {_REQUIRED_SUBJECTS}
),
NotasBase AS
(
    SELECT
        TRY_CONVERT(bigint, cxe.codigo_estud) AS codigo_estud,
        TRY_CONVERT(nvarchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
        TRY_CONVERT(nvarchar(50), cxe.codigo_materia) AS codigo_materia,
        COALESCE
        (
            CASE
                WHEN TRY_CONVERT(float, cxe.PromedioFinal) BETWEEN 0 AND 10
                THEN TRY_CONVERT(float, cxe.PromedioFinal)
            END,
            CASE
                WHEN
                    (
                        UPPER(LTRIM(RTRIM(COALESCE(CONVERT(nvarchar(50), cxe.TipoMatricula), CONVERT(nvarchar(50), pe.TipoMatricula), N'')))) = N'H'
                        OR UPPER(COALESCE(CONVERT(nvarchar(250), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                    )
                    AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                    AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                THEN (TRY_CONVERT(float, cxe.teoriaHomo) + TRY_CONVERT(float, cxe.practicahomo)) / 2.0
            END,
            CASE
                WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                 AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                 AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3.0
            END
        ) AS nota_final
    FROM dbo.CARRERAXESTUD cxe
    LEFT JOIN dbo.PERIODO pe
        ON TRY_CONVERT(nvarchar(50), pe.cod_periodo) = TRY_CONVERT(nvarchar(50), cxe.codigo_periodo)
    WHERE TRY_CONVERT(bigint, cxe.codigo_estud) IS NOT NULL
      AND TRY_CONVERT(nvarchar(50), cxe.codigo_materia) IS NOT NULL
),
MejorNota AS
(
    SELECT codigo_estud, cod_anio_basica, codigo_materia, MAX(nota_final) AS nota_final
    FROM NotasBase
    GROUP BY codigo_estud, cod_anio_basica, codigo_materia
),
ResumenAcademico AS
(
    SELECT
        um.codigo_estud,
        um.cod_anio_basica,
        um.codigo_periodo,
        um.tipo_matricula_origen,
        COUNT(pb.codigo_materia) AS materias_pensum,
        SUM(CASE WHEN mn.nota_final >= {_PASSING_GRADE} AND mn.nota_final <= 10 THEN 1 ELSE 0 END) AS materias_aprobadas,
        AVG(CASE WHEN mn.nota_final >= {_PASSING_GRADE} AND mn.nota_final <= 10 THEN mn.nota_final END) AS promedio_aprobadas
    FROM UltimaMatricula um
    LEFT JOIN PensumBase pb ON pb.cod_anio_basica = um.cod_anio_basica
    LEFT JOIN MejorNota mn
        ON mn.codigo_estud = um.codigo_estud
       AND mn.cod_anio_basica = um.cod_anio_basica
       AND mn.codigo_materia = pb.codigo_materia
    GROUP BY um.codigo_estud, um.cod_anio_basica, um.codigo_periodo, um.tipo_matricula_origen
),
CandidatosBase AS
(
    SELECT
        TRY_CONVERT(bigint, de.codigo_estud) AS codigo_estud,
        LTRIM(RTRIM(CONVERT(varchar(20), de.Cedula_Est))) AS numero_identificacion,
        LTRIM(RTRIM(CONVERT(nvarchar(250), de.Apellidos_nombre))) AS apellidos_nombres,
        LTRIM(RTRIM(CONVERT(nvarchar(250), de.correointec))) AS correo_institucional,
        LTRIM(RTRIM(CONVERT(nvarchar(250), de.TituloBachiller))) AS titulo_bachiller,
        LTRIM(RTRIM(CONVERT(varchar(10), de.Estado))) AS estado_academico,
        de.Fecha_Grado AS fecha_grado,
        de.Fecha_Emision_SENESCYT AS fecha_emision_senescyt,
        LTRIM(RTRIM(CONVERT(varchar(100), de.Cod_registro))) AS codigo_registro_senescyt,
        ra.cod_anio_basica,
        LTRIM(RTRIM(CONVERT(nvarchar(250), carrera.Nombre_Basica))) AS nombre_carrera,
        ra.codigo_periodo,
        ra.tipo_matricula_origen,
        LTRIM(RTRIM(CONVERT(nvarchar(250), periodo.Detalle_Periodo))) AS nombre_periodo,
        ISNULL(ra.materias_pensum, 0) AS materias_pensum,
        ISNULL(ra.materias_aprobadas, 0) AS materias_aprobadas,
        ra.promedio_aprobadas,
        CAST(CASE
            WHEN ISNULL(ra.materias_pensum, 0) = 0 THEN 0
            ELSE 100.0 * ISNULL(ra.materias_aprobadas, 0) / {_REQUIRED_SUBJECTS}
        END AS decimal(5,2)) AS porcentaje_malla,
        CASE
            WHEN LTRIM(RTRIM(CONVERT(varchar(10), de.Estado))) = 'G' OR de.Fecha_Grado IS NOT NULL THEN 'GRADUADO'
            WHEN ISNULL(ra.materias_aprobadas, 0) >= {_REQUIRED_SUBJECTS} THEN 'EGRESADO'
            ELSE 'PROXIMO'
        END AS etapa_academica
    FROM dbo.DATOS_ESTUD de
    INNER JOIN ResumenAcademico ra ON ra.codigo_estud = TRY_CONVERT(bigint, de.codigo_estud)
    OUTER APPLY
    (
        SELECT TOP (1) ca.Nombre_Basica
        FROM dbo.CARRERAS ca
        WHERE TRY_CONVERT(nvarchar(50), ca.Cod_AnioBasica) = ra.cod_anio_basica
        ORDER BY TRY_CONVERT(bigint, ca.Num) DESC
    ) carrera
    OUTER APPLY
    (
        SELECT TOP (1) pe.Detalle_Periodo
        FROM dbo.PERIODO pe
        WHERE TRY_CONVERT(nvarchar(50), pe.cod_periodo) = ra.codigo_periodo
    ) periodo
    WHERE TRY_CONVERT(bigint, de.codigo_estud) IS NOT NULL
),
Candidatos AS
(
    SELECT *
    FROM CandidatosBase
    WHERE etapa_academica IN ('GRADUADO', 'EGRESADO')
       OR
       (
           etapa_academica = 'PROXIMO'
           AND materias_aprobadas >= {_NEAR_GRADUATION_SUBJECTS}
           AND estado_academico IN ('A', 'C', 'D', 'E')
       )
)
"""


def _query_candidates(
    *,
    search: str = "",
    stage: str = "TODOS",
    page: int = 1,
    page_size: int = 25,
    exact_code: int | None = None,
    candidate_codes: list[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    normalized_stage = _clean(stage).upper() or "TODOS"
    if normalized_stage not in _VALID_STAGES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Etapa académica inválida.")
    term = _clean(search)
    like = f"%{term}%"
    offset = (page - 1) * page_size
    filtered_codes = sorted({int(code) for code in candidate_codes or [] if int(code) > 0})
    if candidate_codes is not None and not filtered_codes:
        return [], 0
    code_filter = ""
    if candidate_codes is not None:
        code_filter = f" AND codigo_estud IN ({','.join('?' for _ in filtered_codes)})"
    sql = _CANDIDATE_CTE + f"""
SELECT
    COUNT(1) OVER() AS total_registros,
    codigo_estud,
    numero_identificacion,
    apellidos_nombres,
    correo_institucional,
    titulo_bachiller,
    estado_academico,
    fecha_grado,
    fecha_emision_senescyt,
    codigo_registro_senescyt,
    cod_anio_basica,
    nombre_carrera,
    codigo_periodo,
    tipo_matricula_origen,
    nombre_periodo,
    materias_pensum,
    materias_aprobadas,
    promedio_aprobadas,
    porcentaje_malla,
    etapa_academica
FROM Candidatos
WHERE (? = 'TODOS' OR etapa_academica = ?)
  AND (? IS NULL OR codigo_estud = ?)
  AND
  (
      ? = ''
      OR CONVERT(varchar(30), codigo_estud) LIKE ?
      OR numero_identificacion LIKE ?
      OR apellidos_nombres LIKE ?
      OR ISNULL(nombre_carrera, N'') LIKE ?
  )
  {code_filter}
ORDER BY
    CASE etapa_academica WHEN 'GRADUADO' THEN 1 WHEN 'EGRESADO' THEN 2 ELSE 3 END,
    porcentaje_malla DESC,
    apellidos_nombres
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
"""
    parameters: list[Any] = [
        normalized_stage,
        normalized_stage,
        exact_code,
        exact_code,
        term,
        like,
        like,
        like,
        like,
    ]
    parameters.extend(filtered_codes)
    parameters.extend((offset, page_size))
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, *parameters)
        items = _rows(cursor)
    total = int(items[0].pop("total_registros", 0)) if items else 0
    for item in items[1:]:
        item.pop("total_registros", None)
    for item in items:
        item["tipo_matricula"] = _enrollment_type(
            item.pop("tipo_matricula_origen", ""),
            item.get("codigo_periodo"),
            item.get("nombre_periodo"),
        )
    return items, total


def _candidate_codes_with_missing_documents() -> list[int]:
    with get_secretaria_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT DISTINCT CodigoEstud
            FROM rpt.vw_ResumenTramiteDocumental
            WHERE RequisitosFaltantes > 0
              AND CodigoEstud IS NOT NULL
            ORDER BY CodigoEstud
            """
        )
        return [int(row[0]) for row in cursor.fetchall() if _int_value(row[0])]


def _candidate_counts() -> dict[str, int]:
    sql = _CANDIDATE_CTE + """
SELECT
    COUNT(1) AS total,
    SUM(CASE WHEN etapa_academica = 'PROXIMO' THEN 1 ELSE 0 END) AS proximos,
    SUM(CASE WHEN etapa_academica = 'EGRESADO' THEN 1 ELSE 0 END) AS egresados,
    SUM(CASE WHEN etapa_academica = 'GRADUADO' THEN 1 ELSE 0 END) AS graduados
FROM Candidatos;
"""
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
    return {
        "total": int(row.total or 0) if row else 0,
        "proximos": int(row.proximos or 0) if row else 0,
        "egresados": int(row.egresados or 0) if row else 0,
        "graduados": int(row.graduados or 0) if row else 0,
    }


def _case_summaries(codes: list[int]) -> dict[int, dict[str, Any]]:
    if not codes:
        return {}
    placeholders = ",".join("?" for _ in codes)
    with get_secretaria_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT
                TramiteId,
                CodigoEstud,
                CodigoTramite,
                EstadoTramiteCodigo,
                RequisitosFaltantes,
                RequisitosObservados,
                PorcentajeDocumental
            FROM rpt.vw_ResumenTramiteDocumental
            WHERE CodigoEstud IN ({placeholders})
            """,
            *codes,
        )
        rows = _rows(cursor)
    return {
        int(item["CodigoEstud"]): {
            "case_id": int(item["TramiteId"]),
            "case_code": _clean(item["CodigoTramite"]),
            "status": _clean(item["EstadoTramiteCodigo"]),
            "missing": int(item["RequisitosFaltantes"] or 0),
            "observed": int(item["RequisitosObservados"] or 0),
            "progress": _float_value(item["PorcentajeDocumental"]) or 0,
        }
        for item in rows
    }


def _audit(
    cursor: pyodbc.Cursor,
    *,
    case_id: int | None,
    entity: str,
    entity_id: str | int | None,
    action: str,
    user: SessionUser,
    data: dict[str, Any] | None = None,
) -> None:
    context = get_audit_context()
    cursor.execute(
        """
        INSERT aud.EventoSecretaria
            (TramiteId, Entidad, EntidadId, Accion, DatosJson, Usuario, Rol, RequestId, DireccionIp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        case_id,
        entity,
        _clean(entity_id) or None,
        action,
        json.dumps(data, ensure_ascii=False, default=_json_value) if data is not None else None,
        user.login,
        user.rol,
        context.request_id or None,
        context.client_ip or None,
    )


def _applicable_column(stage: str) -> str:
    return {
        "PROXIMO": "AplicaProximo",
        "EGRESADO": "AplicaEgresado",
        "GRADUADO": "AplicaGraduado",
    }[stage]


def _sql_code_list(values: set[str]) -> str:
    return ", ".join(f"'{code}'" for code in sorted(values))


def _apply_requirement_matrix(
    cursor: pyodbc.Cursor,
    *,
    case_id: int,
    stage: str,
    enrollment_type: Literal["R", "H"],
) -> None:
    applicable_column = _applicable_column(stage)
    common_codes = _sql_code_list(_COMMON_DOCUMENT_CODES)
    homologation_codes = _sql_code_list(_HOMOLOGATION_DOCUMENT_CODES)
    article_conditions = " OR ".join(
        f"(t.TipoHomologacion = '{classification}' AND td.Codigo = '{document_code}')"
        for classification, document_code in _HOMOLOGATION_ARTICLE_CODES.items()
    )
    cursor.execute(
        f"""
        DECLARE @TipoMatricula char(1) = ?;

        INSERT sec.TramiteRequisito
            (TramiteId, TipoDocumentoId, EsObligatorio, EsAplicable, Orden, EstadoCodigo)
        SELECT
            t.TramiteId,
            d.TipoDocumentoId,
            d.EsObligatorio,
            applicability.EsAplicable,
            d.Orden,
            CASE WHEN applicability.EsAplicable = 1 THEN 'FALTANTE' ELSE 'NO_APLICA' END
        FROM sec.Tramite t
        INNER JOIN cat.PlantillaRequisitoDetalle d
            ON d.PlantillaRequisitoVersionId = t.PlantillaRequisitoVersionId
           AND d.Activo = 1
        INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = d.TipoDocumentoId
        CROSS APPLY
        (
            SELECT CAST(CASE
                WHEN td.Codigo IN ({common_codes}) THEN 1
                WHEN @TipoMatricula = 'H' AND td.Codigo IN ({homologation_codes}) THEN d.{applicable_column}
                WHEN @TipoMatricula = 'H' AND ({article_conditions}) THEN d.{applicable_column}
                ELSE 0
            END AS bit) AS EsAplicable
        ) applicability
        WHERE t.TramiteId = ?
          AND NOT EXISTS
          (
              SELECT 1 FROM sec.TramiteRequisito current_requirement
              WHERE current_requirement.TramiteId = t.TramiteId
                AND current_requirement.TipoDocumentoId = d.TipoDocumentoId
          );

        UPDATE requirement
        SET EsObligatorio = d.EsObligatorio,
            EsAplicable = applicability.EsAplicable,
            Orden = d.Orden,
            EstadoCodigo = CASE
                WHEN applicability.EsAplicable = 0 THEN 'NO_APLICA'
                WHEN requirement.EstadoCodigo = 'NO_APLICA' THEN 'FALTANTE'
                ELSE requirement.EstadoCodigo
            END,
            FechaActualizacion = SYSUTCDATETIME()
        FROM sec.TramiteRequisito requirement
        INNER JOIN sec.Tramite t ON t.TramiteId = requirement.TramiteId
        INNER JOIN cat.PlantillaRequisitoDetalle d
            ON d.PlantillaRequisitoVersionId = t.PlantillaRequisitoVersionId
           AND d.TipoDocumentoId = requirement.TipoDocumentoId
           AND d.Activo = 1
        INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = d.TipoDocumentoId
        CROSS APPLY
        (
            SELECT CAST(CASE
                WHEN td.Codigo IN ({common_codes}) THEN 1
                WHEN @TipoMatricula = 'H' AND td.Codigo IN ({homologation_codes}) THEN d.{applicable_column}
                WHEN @TipoMatricula = 'H' AND ({article_conditions}) THEN d.{applicable_column}
                ELSE 0
            END AS bit) AS EsAplicable
        ) applicability
        WHERE requirement.TramiteId = ?;

        UPDATE requirement
        SET EsAplicable = 0,
            EstadoCodigo = 'NO_APLICA',
            FechaActualizacion = SYSUTCDATETIME()
        FROM sec.TramiteRequisito requirement
        INNER JOIN sec.Tramite t ON t.TramiteId = requirement.TramiteId
        WHERE requirement.TramiteId = ?
          AND NOT EXISTS
          (
              SELECT 1
              FROM cat.PlantillaRequisitoDetalle detail
              WHERE detail.PlantillaRequisitoVersionId = t.PlantillaRequisitoVersionId
                AND detail.TipoDocumentoId = requirement.TipoDocumentoId
                AND detail.Activo = 1
          );
        """,
        enrollment_type,
        case_id,
        case_id,
        case_id,
    )


def _ensure_case(candidate: dict[str, Any], user: SessionUser) -> tuple[int, bool]:
    stage = _clean(candidate["etapa_academica"]).upper()
    enrollment_type = _enrollment_type(
        candidate.get("tipo_matricula"),
        candidate.get("codigo_periodo"),
        candidate.get("nombre_periodo"),
    )
    with get_secretaria_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT TOP (1) t.TramiteId
            FROM sec.Tramite t
            INNER JOIN cat.TipoTramite tt ON tt.TipoTramiteId = t.TipoTramiteId
            WHERE t.CodigoEstud = ? AND tt.Codigo = 'REVISION_EXPEDIENTE_GRADO' AND t.Activo = 1
            """,
            candidate["codigo_estud"],
        )
        existing = cursor.fetchone()
        created = existing is None
        if existing:
            case_id = int(existing.TramiteId)
            cursor.execute(
                """
                UPDATE sec.Tramite
                SET NumeroIdentificacion = ?, ApellidosNombres = ?, CodigoCarrera = ?, NombreCarrera = ?,
                    CodigoPeriodo = ?, NombrePeriodo = ?, TipoMatricula = ?, EtapaAcademica = ?, MateriasAprobadas = ?,
                    PorcentajeMalla = ?, PromedioAprobadas = ?, FechaGrado = ?,
                    FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                WHERE TramiteId = ?
                """,
                candidate["numero_identificacion"],
                candidate["apellidos_nombres"],
                candidate.get("cod_anio_basica"),
                candidate.get("nombre_carrera"),
                candidate.get("codigo_periodo"),
                candidate.get("nombre_periodo"),
                enrollment_type,
                stage,
                candidate["materias_aprobadas"],
                candidate["porcentaje_malla"],
                candidate.get("promedio_aprobadas"),
                candidate.get("fecha_grado"),
                user.login,
                case_id,
            )
        else:
            code = f"SEC-{datetime.utcnow():%Y}-{uuid4().hex[:12].upper()}"
            cursor.execute(
                """
                DECLARE @TipoId int = (SELECT TipoTramiteId FROM cat.TipoTramite WHERE Codigo = 'REVISION_EXPEDIENTE_GRADO');
                DECLARE @EstadoId int = (SELECT EstadoTramiteId FROM cat.EstadoTramite WHERE Codigo = 'RECIBIDO');
                DECLARE @PlantillaId int =
                (
                    SELECT TOP (1) PlantillaRequisitoVersionId
                    FROM cat.PlantillaRequisitoVersion
                    WHERE TipoTramiteId = @TipoId AND Activo = 1
                      AND VigenteDesde <= CONVERT(date, SYSUTCDATETIME())
                      AND (VigenteHasta IS NULL OR VigenteHasta >= CONVERT(date, SYSUTCDATETIME()))
                    ORDER BY VigenteDesde DESC, PlantillaRequisitoVersionId DESC
                );
                INSERT sec.Tramite
                    (CodigoTramite, TipoTramiteId, EstadoTramiteId, PlantillaRequisitoVersionId,
                     CodigoEstud, NumeroIdentificacion, ApellidosNombres, CodigoCarrera, NombreCarrera,
                     CodigoPeriodo, NombrePeriodo, TipoMatricula, EtapaAcademica, MateriasRequeridas, MateriasAprobadas,
                     PorcentajeMalla, PromedioAprobadas, FechaGrado, UsuarioApertura)
                OUTPUT INSERTED.TramiteId
                VALUES (?, @TipoId, @EstadoId, @PlantillaId, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                code,
                candidate["codigo_estud"],
                candidate["numero_identificacion"],
                candidate["apellidos_nombres"],
                candidate.get("cod_anio_basica"),
                candidate.get("nombre_carrera"),
                candidate.get("codigo_periodo"),
                candidate.get("nombre_periodo"),
                enrollment_type,
                stage,
                _REQUIRED_SUBJECTS,
                candidate["materias_aprobadas"],
                candidate["porcentaje_malla"],
                candidate.get("promedio_aprobadas"),
                candidate.get("fecha_grado"),
                user.login,
            )
            inserted = cursor.fetchone()
            if not inserted:
                raise RuntimeError("No se pudo abrir el trámite documental.")
            case_id = int(inserted.TramiteId)

        if enrollment_type == "R":
            cursor.execute(
                "UPDATE sec.Tramite SET TipoHomologacion = NULL WHERE TramiteId = ?",
                case_id,
            )
        _apply_requirement_matrix(
            cursor,
            case_id=case_id,
            stage=stage,
            enrollment_type=enrollment_type,
        )
        cursor.execute(
            """
            INSERT sec.TramiteSnapshotAcademico
                (TramiteId, EtapaAcademica, MateriasAprobadas, MateriasRequeridas,
                 PorcentajeMalla, PromedioAprobadas, EstadoAcademico, DatosJson, UsuarioCaptura)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            case_id,
            stage,
            candidate["materias_aprobadas"],
            _REQUIRED_SUBJECTS,
            candidate["porcentaje_malla"],
            candidate.get("promedio_aprobadas"),
            candidate.get("estado_academico"),
            json.dumps(candidate, ensure_ascii=False, default=_json_value),
            user.login,
        )
        _audit(
            cursor,
            case_id=case_id,
            entity="Tramite",
            entity_id=case_id,
            action="APERTURA" if created else "ACTUALIZACION_ACADEMICA",
            user=user,
            data={
                "etapa": stage,
                "tipo_matricula": enrollment_type,
                "materias_aprobadas": candidate["materias_aprobadas"],
            },
        )
        connection.commit()
    return case_id, created


def _collect_expedient_documents(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with get_expedient_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    td.Codigo AS tipo_documento,
                    CONVERT(nvarchar(100), d.DocumentoExpedienteId) AS origen_id,
                    d.NombreArchivo AS nombre_archivo,
                    d.ContentType AS content_type,
                    d.TamanoBytes AS tamano_bytes,
                    CONVERT(varchar(128), d.HashArchivo, 2) AS hash_archivo,
                    COALESCE(d.RutaNube, d.RutaOrigenINTECBDD) AS ruta_referencia,
                    ed.Codigo AS estado_origen,
                    d.FechaCarga AS fecha_documento,
                    d.UsuarioCarga AS usuario_carga
                FROM exp.ExpedienteEstudiantil e
                INNER JOIN doc.DocumentoExpediente d
                    ON d.ExpedienteEstudiantilId = e.ExpedienteEstudiantilId AND d.Activo = 1
                INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = d.TipoDocumentoId
                INNER JOIN cat.EstadoDocumento ed ON ed.EstadoDocumentoId = d.EstadoDocumentoId
                WHERE e.Activo = 1
                  AND
                  (
                      TRY_CONVERT(bigint, e.CodigoEstud) = ?
                      OR REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(e.NumeroIdentificacion)), '-', ''), ' ', ''), '.', '') = ?
                  )
                """,
                candidate["codigo_estud"],
                _document(candidate["numero_identificacion"]),
            )
            rows = _rows(cursor)
        return [
            {**item, "sistema_origen": "INTEC_EXPEDIENTE_ESTUDIANTIL", "entidad_origen": "doc.DocumentoExpediente"}
            for item in rows
            if _clean(item.get("tipo_documento")).upper() in _DOCUMENT_CODES
        ]
    except (pyodbc.Error, RuntimeError):
        return []


def _collect_titulation_documents(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with get_titulation_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    d.TipoDocumentoCodigo AS tipo_documento,
                    CONVERT(nvarchar(100), d.DocumentoId) AS origen_id,
                    d.NombreArchivo AS nombre_archivo,
                    NULL AS content_type,
                    NULL AS tamano_bytes,
                    CONVERT(varchar(128), d.HashSha256, 2) AS hash_archivo,
                    d.RutaNube AS ruta_referencia,
                    d.EstadoDocumento AS estado_origen,
                    d.FechaCarga AS fecha_documento,
                    d.UsuarioCarga AS usuario_carga
                FROM core.EstudianteRef er
                INNER JOIN tit.ExpedienteTitulacion e ON e.EstudianteRefId = er.EstudianteRefId
                INNER JOIN doc.DocumentoExpediente d ON d.ExpedienteId = e.ExpedienteId AND d.Activo = 1
                WHERE TRY_CONVERT(bigint, er.CodigoEstud) = ?
                   OR REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(er.NumeroIdentificacion)), '-', ''), ' ', ''), '.', '') = ?
                """,
                candidate["codigo_estud"],
                _document(candidate["numero_identificacion"]),
            )
            rows = _rows(cursor)
        return [
            {**item, "sistema_origen": "TITULACION_INTEC", "entidad_origen": "doc.DocumentoExpediente"}
            for item in rows
            if _clean(item.get("tipo_documento")).upper() in _DOCUMENT_CODES
        ]
    except (pyodbc.Error, RuntimeError):
        return []


def _collect_graph_documents(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with get_graph_database_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    d.TipoDocumentoCodigo AS tipo_documento,
                    CONVERT(nvarchar(100), d.DocumentoGraphId) AS origen_id,
                    d.DocumentoGraphId AS documento_graph_id,
                    d.NombreArchivo AS nombre_archivo,
                    d.ContentType AS content_type,
                    d.TamanoBytes AS tamano_bytes,
                    d.HashSha256 AS hash_archivo,
                    COALESCE(d.GraphWebUrl, d.RutaGraph) AS ruta_referencia,
                    d.EstadoDocumentoGraphCodigo AS estado_origen,
                    COALESCE(d.FechaActualizacion, d.FechaCarga) AS fecha_documento,
                    d.UsuarioCarga AS usuario_carga
                FROM doc.ExpedienteGraph e
                INNER JOIN doc.DocumentoGraph d ON d.ExpedienteGraphId = e.ExpedienteGraphId AND d.Activo = 1
                WHERE e.Activo = 1
                  AND
                  (
                      TRY_CONVERT(bigint, e.CodigoEstud) = ?
                      OR REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(e.NumeroIdentificacion)), '-', ''), ' ', ''), '.', '') = ?
                  )
                """,
                candidate["codigo_estud"],
                _document(candidate["numero_identificacion"]),
            )
            rows = _rows(cursor)
        return [
            {**item, "sistema_origen": "INTEC_GRAPH_INTEGRACION", "entidad_origen": "doc.DocumentoGraph"}
            for item in rows
            if _clean(item.get("tipo_documento")).upper() in _DOCUMENT_CODES
        ]
    except (pyodbc.Error, RuntimeError):
        return []


def _recalculate_case(cursor: pyodbc.Cursor, case_id: int, user_login: str) -> None:
    cursor.execute(
        """
        DECLARE @EstadoCodigo varchar(30);
        DECLARE @Total int;
        DECLARE @Validados int;
        DECLARE @Observados int;
        DECLARE @TipoMatricula char(1);
        DECLARE @TipoHomologacion varchar(30);
        SELECT
            @Total = SUM(CASE WHEN EsAplicable = 1 AND EsObligatorio = 1 THEN 1 ELSE 0 END),
            @Validados = SUM(CASE WHEN EsAplicable = 1 AND EsObligatorio = 1 AND EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END),
            @Observados = SUM(CASE WHEN EsAplicable = 1 AND EstadoCodigo IN ('OBSERVADO', 'RECHAZADO') THEN 1 ELSE 0 END)
        FROM sec.TramiteRequisito
        WHERE TramiteId = ?;

        SELECT @TipoMatricula = TipoMatricula, @TipoHomologacion = TipoHomologacion
        FROM sec.Tramite
        WHERE TramiteId = ?;

        SET @EstadoCodigo = CASE
            WHEN ISNULL(@Observados, 0) > 0 THEN 'OBSERVADO'
            WHEN @TipoMatricula = 'H' AND @TipoHomologacion IS NULL THEN 'EN_VALIDACION'
            WHEN ISNULL(@Total, 0) > 0 AND @Total = ISNULL(@Validados, 0) THEN 'APROBADO'
            ELSE 'EN_VALIDACION'
        END;

        UPDATE t
        SET EstadoTramiteId = e.EstadoTramiteId,
            FechaActualizacion = SYSUTCDATETIME(),
            UsuarioActualizacion = ?
        FROM sec.Tramite t
        INNER JOIN cat.EstadoTramite e ON e.Codigo = @EstadoCodigo
        WHERE t.TramiteId = ?;
        """,
        case_id,
        case_id,
        user_login,
        case_id,
    )


def _refresh_missing_observations(cursor: pyodbc.Cursor, case_id: int, user_login: str) -> None:
    cursor.execute(
        """
        INSERT sec.ObservacionTramite
            (TramiteId, TramiteRequisitoId, TipoObservacion, Observacion, EsSistema, UsuarioCreacion)
        SELECT
            tr.TramiteId,
            tr.TramiteRequisitoId,
            'FALTANTE',
            N'Falta cargar y presentar el documento obligatorio: ' + td.Nombre + N'.',
            1,
            ?
        FROM sec.TramiteRequisito tr
        INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = tr.TipoDocumentoId
        WHERE tr.TramiteId = ?
          AND tr.EsAplicable = 1
          AND tr.EsObligatorio = 1
          AND tr.EstadoCodigo = 'FALTANTE'
          AND NOT EXISTS
          (
              SELECT 1
              FROM sec.ObservacionTramite observation
              WHERE observation.TramiteRequisitoId = tr.TramiteRequisitoId
                AND observation.TipoObservacion = 'FALTANTE'
                AND observation.EsSistema = 1
                AND observation.Resuelta = 0
          );

        UPDATE observation
        SET Resuelta = 1, FechaResolucion = SYSUTCDATETIME(), UsuarioResolucion = ?
        FROM sec.ObservacionTramite observation
        INNER JOIN sec.TramiteRequisito requirement
            ON requirement.TramiteRequisitoId = observation.TramiteRequisitoId
        WHERE observation.TramiteId = ?
          AND observation.TipoObservacion = 'FALTANTE'
          AND observation.EsSistema = 1
          AND observation.Resuelta = 0
          AND (requirement.EsAplicable = 0 OR requirement.EstadoCodigo <> 'FALTANTE');
        """,
        user_login,
        case_id,
        user_login,
        case_id,
    )


def _sync_case(case_id: int, candidate: dict[str, Any], user: SessionUser) -> dict[str, int]:
    documents = [
        *_collect_expedient_documents(candidate),
        *_collect_titulation_documents(candidate),
        *_collect_graph_documents(candidate),
    ]
    synchronized = 0
    with get_secretaria_connection() as connection:
        cursor = connection.cursor()
        for document in documents:
            code = _clean(document.get("tipo_documento")).upper()
            cursor.execute(
                """
                SELECT tr.TramiteRequisitoId, tr.EstadoCodigo
                FROM sec.TramiteRequisito tr
                INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = tr.TipoDocumentoId
                WHERE tr.TramiteId = ? AND td.Codigo = ? AND tr.EsAplicable = 1
                """,
                case_id,
                code,
            )
            requirement = cursor.fetchone()
            if not requirement:
                continue
            requirement_id = int(requirement.TramiteRequisitoId)
            cursor.execute(
                """
                MERGE doc.DocumentoPresentado AS target
                USING
                (
                    SELECT
                        ? AS TramiteRequisitoId, ? AS SistemaOrigen, ? AS EntidadOrigen,
                        ? AS EntidadOrigenId, ? AS DocumentoGraphId, ? AS NombreArchivo,
                        ? AS ContentType, ? AS TamanoBytes, ? AS HashArchivo,
                        ? AS RutaReferencia, ? AS EstadoOrigen, ? AS FechaDocumento,
                        ? AS UsuarioCargaOrigen, ? AS UsuarioSincronizacion
                ) AS source
                ON target.SistemaOrigen = source.SistemaOrigen
               AND target.EntidadOrigen = source.EntidadOrigen
               AND target.EntidadOrigenId = source.EntidadOrigenId
                WHEN MATCHED THEN UPDATE SET
                    TramiteRequisitoId = source.TramiteRequisitoId,
                    DocumentoGraphId = source.DocumentoGraphId,
                    NombreArchivo = source.NombreArchivo,
                    ContentType = source.ContentType,
                    TamanoBytes = source.TamanoBytes,
                    HashArchivo = source.HashArchivo,
                    RutaReferencia = source.RutaReferencia,
                    EstadoOrigen = source.EstadoOrigen,
                    EsEvidenciaVigente = 1,
                    FechaDocumento = source.FechaDocumento,
                    FechaSincronizacion = SYSUTCDATETIME(),
                    UsuarioCargaOrigen = source.UsuarioCargaOrigen,
                    UsuarioSincronizacion = source.UsuarioSincronizacion
                WHEN NOT MATCHED THEN INSERT
                    (TramiteRequisitoId, SistemaOrigen, EntidadOrigen, EntidadOrigenId,
                     DocumentoGraphId, NombreArchivo, ContentType, TamanoBytes, HashArchivo,
                     RutaReferencia, EstadoOrigen, FechaDocumento, UsuarioCargaOrigen,
                     UsuarioSincronizacion)
                VALUES
                    (source.TramiteRequisitoId, source.SistemaOrigen, source.EntidadOrigen,
                     source.EntidadOrigenId, source.DocumentoGraphId, source.NombreArchivo,
                     source.ContentType, source.TamanoBytes, source.HashArchivo,
                     source.RutaReferencia, source.EstadoOrigen, source.FechaDocumento,
                     source.UsuarioCargaOrigen, source.UsuarioSincronizacion);
                """,
                requirement_id,
                document["sistema_origen"],
                document["entidad_origen"],
                document["origen_id"],
                document.get("documento_graph_id"),
                document.get("nombre_archivo"),
                document.get("content_type"),
                document.get("tamano_bytes"),
                document.get("hash_archivo"),
                document.get("ruta_referencia"),
                document.get("estado_origen"),
                document.get("fecha_documento"),
                _clean(document.get("usuario_carga")) or None,
                user.login,
            )
            external_state = _clean(document.get("estado_origen")).upper()
            next_state = "VALIDADO" if external_state in _TRUSTED_VALID_STATES else "PRESENTE"
            cursor.execute(
                """
                UPDATE sec.TramiteRequisito
                SET EstadoCodigo = ?, FechaActualizacion = SYSUTCDATETIME()
                WHERE TramiteRequisitoId = ?
                  AND EstadoCodigo IN ('FALTANTE', 'PRESENTE', 'EN_REVISION')
                """,
                next_state,
                requirement_id,
            )
            synchronized += 1

        _refresh_missing_observations(cursor, case_id, user.login)
        _recalculate_case(cursor, case_id, user.login)
        _audit(
            cursor,
            case_id=case_id,
            entity="Tramite",
            entity_id=case_id,
            action="SINCRONIZACION_DOCUMENTAL",
            user=user,
            data={"documentos_detectados": len(documents), "documentos_relacionados": synchronized},
        )
        connection.commit()
    return {"detected": len(documents), "synchronized": synchronized}


def _case_detail(case_id: int) -> dict[str, Any]:
    with get_secretaria_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM rpt.vw_ResumenTramiteDocumental WHERE TramiteId = ?", case_id)
        header_row = cursor.fetchone()
        if not header_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expediente de Secretaría no encontrado.")
        raw_case = _row_dict(cursor, header_row)
        case = {
            "case_id": int(raw_case["TramiteId"]),
            "case_code": _clean(raw_case["CodigoTramite"]),
            "case_type": _clean(raw_case["TipoTramiteCodigo"]),
            "status": _clean(raw_case["EstadoTramiteCodigo"]),
            "status_name": _clean(raw_case["EstadoTramite"]),
            "codigo_estud": int(raw_case["CodigoEstud"]),
            "numero_identificacion": _clean(raw_case["NumeroIdentificacion"]),
            "apellidos_nombres": _clean(raw_case["ApellidosNombres"]),
            "codigo_carrera": _clean(raw_case["CodigoCarrera"]),
            "nombre_carrera": _clean(raw_case["NombreCarrera"]),
            "codigo_periodo": _clean(raw_case["CodigoPeriodo"]),
            "nombre_periodo": _clean(raw_case["NombrePeriodo"]),
            "enrollment_type": _enrollment_type(raw_case.get("TipoMatricula")),
            "homologation_classification": _clean(raw_case.get("TipoHomologacion")) or None,
            "stage": _clean(raw_case["EtapaAcademica"]),
            "approved_subjects": int(raw_case["MateriasAprobadas"] or 0),
            "required_subjects": int(raw_case["MateriasRequeridas"] or _REQUIRED_SUBJECTS),
            "academic_progress": _float_value(raw_case["PorcentajeMalla"]) or 0,
            "average": _float_value(raw_case["PromedioAprobadas"]),
            "graduation_date": raw_case["FechaGrado"],
            "required_documents": int(raw_case["RequisitosObligatorios"] or 0),
            "validated_documents": int(raw_case["RequisitosValidados"] or 0),
            "missing_documents": int(raw_case["RequisitosFaltantes"] or 0),
            "observed_documents": int(raw_case["RequisitosObservados"] or 0),
            "document_progress": _float_value(raw_case["PorcentajeDocumental"]) or 0,
            "opened_at": raw_case["FechaApertura"],
            "updated_at": raw_case["FechaActualizacion"],
        }
        cursor.execute(
            """
            SELECT
                tr.TramiteRequisitoId AS requisito_id,
                td.Codigo AS tipo_documento_codigo,
                td.Nombre AS tipo_documento,
                detail.Instruccion AS instruccion,
                tr.EsObligatorio AS es_obligatorio,
                tr.EsAplicable AS es_aplicable,
                tr.EstadoCodigo AS estado,
                tr.ObservacionActual AS observacion,
                tr.FechaUltimaRevision AS fecha_revision,
                tr.UsuarioUltimaRevision AS usuario_revision,
                evidence.DocumentoPresentadoId AS documento_presentado_id,
                evidence.DocumentoGraphId AS documento_graph_id,
                evidence.NombreArchivo AS nombre_archivo,
                evidence.ContentType AS content_type,
                evidence.TamanoBytes AS tamano_bytes,
                evidence.SistemaOrigen AS sistema_origen,
                evidence.EstadoOrigen AS estado_origen,
                evidence.RutaReferencia AS ruta_referencia,
                evidence.FechaDocumento AS fecha_documento,
                evidence.UsuarioCargaOrigen AS usuario_carga,
                evidence.UsuarioSincronizacion AS usuario_sincronizacion,
                evidence.TotalEvidencias AS total_evidencias
            FROM sec.TramiteRequisito tr
            INNER JOIN sec.Tramite t ON t.TramiteId = tr.TramiteId
            INNER JOIN cat.TipoDocumento td ON td.TipoDocumentoId = tr.TipoDocumentoId
            LEFT JOIN cat.PlantillaRequisitoDetalle detail
                ON detail.PlantillaRequisitoVersionId = t.PlantillaRequisitoVersionId
               AND detail.TipoDocumentoId = tr.TipoDocumentoId
            OUTER APPLY
            (
                SELECT TOP (1)
                    document.DocumentoPresentadoId,
                    document.DocumentoGraphId,
                    document.NombreArchivo,
                    document.ContentType,
                    document.TamanoBytes,
                    document.SistemaOrigen,
                    document.EstadoOrigen,
                    document.RutaReferencia,
                    document.FechaDocumento,
                    document.UsuarioCargaOrigen,
                    document.UsuarioSincronizacion,
                    COUNT(1) OVER() AS TotalEvidencias
                FROM doc.DocumentoPresentado document
                WHERE document.TramiteRequisitoId = tr.TramiteRequisitoId
                  AND document.EsEvidenciaVigente = 1
                ORDER BY document.FechaDocumento DESC, document.DocumentoPresentadoId DESC
            ) evidence
            WHERE tr.TramiteId = ? AND tr.EsAplicable = 1
            ORDER BY tr.Orden, tr.TramiteRequisitoId
            """,
            case_id,
        )
        requirements = _rows(cursor)
        cursor.execute(
            """
            SELECT
                ObservacionTramiteId AS observacion_id,
                TramiteRequisitoId AS requisito_id,
                TipoObservacion AS tipo,
                Observacion AS observacion,
                EsSistema AS es_sistema,
                FechaCreacion AS fecha,
                UsuarioCreacion AS usuario
            FROM sec.ObservacionTramite
            WHERE TramiteId = ? AND Resuelta = 0
            ORDER BY FechaCreacion DESC, ObservacionTramiteId DESC
            """,
            case_id,
        )
        observations = _rows(cursor)
    return {"case": case, "requirements": requirements, "observations": observations}


@router.get("/dashboard")
def secretaria_dashboard(
    _current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    try:
        candidates = _candidate_counts()
        with get_secretaria_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(1) AS expedientes,
                    SUM(CASE WHEN EstadoTramiteCodigo = 'EN_VALIDACION' THEN 1 ELSE 0 END) AS en_validacion,
                    SUM(CASE WHEN EstadoTramiteCodigo = 'OBSERVADO' THEN 1 ELSE 0 END) AS observados,
                    SUM(CASE WHEN EstadoTramiteCodigo = 'APROBADO' THEN 1 ELSE 0 END) AS aprobados,
                    SUM(RequisitosFaltantes) AS documentos_faltantes,
                    SUM(CASE WHEN RequisitosFaltantes > 0 THEN 1 ELSE 0 END) AS estudiantes_con_faltantes
                FROM rpt.vw_ResumenTramiteDocumental
                """
            )
            row = cursor.fetchone()
        cases = {
            "expedientes": int(row.expedientes or 0) if row else 0,
            "en_validacion": int(row.en_validacion or 0) if row else 0,
            "observados": int(row.observados or 0) if row else 0,
            "aprobados": int(row.aprobados or 0) if row else 0,
            "documentos_faltantes": int(row.documentos_faltantes or 0) if row else 0,
            "estudiantes_con_faltantes": int(row.estudiantes_con_faltantes or 0) if row else 0,
        }
        return {"candidates": candidates, "cases": cases}
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible consultar la información de Secretaría General. Verifique la base y su configuración.",
        ) from exc


@router.get("/candidates")
def secretaria_candidates(
    _current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    search: Annotated[str, Query(max_length=120)] = "",
    stage: Annotated[str, Query(max_length=20)] = "TODOS",
    only_missing_documents: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
) -> dict[str, Any]:
    try:
        candidate_codes = _candidate_codes_with_missing_documents() if only_missing_documents else None
        items, total = _query_candidates(
            search=search,
            stage=stage,
            page=page,
            page_size=page_size,
            candidate_codes=candidate_codes,
        )
        cases = _case_summaries([int(item["codigo_estud"]) for item in items])
        for item in items:
            item["secretaria"] = cases.get(int(item["codigo_estud"]))
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size) if total else 1,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible consultar la lista de estudiantes candidatos en Secretaría General.",
        ) from exc


@router.post("/cases")
def ensure_secretaria_case(
    payload: EnsureCasePayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    try:
        candidates, _ = _query_candidates(exact_code=payload.codigo_estud, page_size=1)
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El estudiante no está graduado ni cumple el umbral de proximidad a graduación.",
            )
        candidate = candidates[0]
        case_id, created = _ensure_case(candidate, current_user)
        sync = _sync_case(case_id, candidate, current_user)
        return {**_case_detail(case_id), "created": created, "sync": sync}
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible abrir el expediente en Secretaría General.",
        ) from exc


@router.get("/cases/{case_id}")
def secretaria_case_detail(
    case_id: int,
    _current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    try:
        return _case_detail(case_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible consultar el expediente de Secretaría General.",
        ) from exc


@router.post("/cases/{case_id}/sync")
def sync_secretaria_case(
    case_id: int,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    try:
        detail = _case_detail(case_id)
        code = int(detail["case"]["codigo_estud"])
        candidates, _ = _query_candidates(exact_code=code, page_size=1)
        if not candidates:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El estudiante ya no consta como candidato elegible.")
        _ensure_case(candidates[0], current_user)
        sync = _sync_case(case_id, candidates[0], current_user)
        return {**_case_detail(case_id), "sync": sync}
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible actualizar el expediente de Secretaría General.",
        ) from exc


@router.put("/cases/{case_id}/homologation-classification")
def update_homologation_classification(
    case_id: int,
    payload: HomologationClassificationPayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_secretaria_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TipoMatricula, TipoHomologacion, EtapaAcademica
                FROM sec.Tramite
                WHERE TramiteId = ? AND Activo = 1
                """,
                case_id,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Expediente de Secretaría no encontrado.",
                )
            if _enrollment_type(row.TipoMatricula) != "H":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La clasificación por artículos solo corresponde a matrículas de homologación.",
                )

            previous = _clean(row.TipoHomologacion).upper() or None
            classification = payload.tipo_homologacion
            cursor.execute(
                """
                UPDATE sec.Tramite
                SET TipoHomologacion = ?, FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                WHERE TramiteId = ? AND Activo = 1
                """,
                classification,
                current_user.login,
                case_id,
            )
            _apply_requirement_matrix(
                cursor,
                case_id=case_id,
                stage=_clean(row.EtapaAcademica).upper(),
                enrollment_type="H",
            )
            _refresh_missing_observations(cursor, case_id, current_user.login)
            _recalculate_case(cursor, case_id, current_user.login)
            _audit(
                cursor,
                case_id=case_id,
                entity="Tramite",
                entity_id=case_id,
                action="CLASIFICACION_HOMOLOGACION",
                user=current_user,
                data={
                    "tipo_anterior": previous,
                    "tipo_nuevo": classification,
                    "articulo_documental": _homologation_article_code(classification),
                },
            )
            connection.commit()
        return _case_detail(case_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible guardar la clasificación de homologación.",
        ) from exc


@router.post("/cases/{case_id}/requirements/{requirement_id}/review")
def review_secretaria_requirement(
    case_id: int,
    requirement_id: int,
    payload: RequirementReviewPayload,
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
) -> dict[str, Any]:
    next_state = payload.estado.upper()
    observation = _clean(payload.observacion)
    if next_state not in _REVIEW_STATES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Estado de revisión inválido.")
    if next_state in {"OBSERVADO", "RECHAZADO"} and len(observation) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Debe registrar una observación que explique la corrección requerida.",
        )

    try:
        with get_secretaria_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT tr.EstadoCodigo
                FROM sec.TramiteRequisito tr
                WHERE tr.TramiteId = ? AND tr.TramiteRequisitoId = ? AND tr.EsAplicable = 1
                """,
                case_id,
                requirement_id,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisito documental no encontrado.")
            previous_state = _clean(row.EstadoCodigo).upper()

            cursor.execute(
                """
                SELECT TOP (1) DocumentoPresentadoId
                FROM doc.DocumentoPresentado
                WHERE TramiteRequisitoId = ? AND EsEvidenciaVigente = 1
                  AND (? IS NULL OR DocumentoPresentadoId = ?)
                ORDER BY FechaDocumento DESC, DocumentoPresentadoId DESC
                """,
                requirement_id,
                payload.documento_presentado_id,
                payload.documento_presentado_id,
            )
            evidence = cursor.fetchone()
            evidence_id = int(evidence.DocumentoPresentadoId) if evidence else None
            if next_state == "VALIDADO" and evidence_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se puede validar un requisito sin documento o evidencia relacionada.",
                )

            cursor.execute(
                """
                INSERT doc.RevisionHumana
                    (TramiteRequisitoId, DocumentoPresentadoId, EstadoAnterior, EstadoNuevo,
                     Observacion, UsuarioRevision, RolRevision)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                requirement_id,
                evidence_id,
                previous_state,
                next_state,
                observation or None,
                current_user.login,
                current_user.rol,
            )
            cursor.execute(
                """
                UPDATE sec.TramiteRequisito
                SET EstadoCodigo = ?, ObservacionActual = ?, FechaUltimaRevision = SYSUTCDATETIME(),
                    UsuarioUltimaRevision = ?, FechaActualizacion = SYSUTCDATETIME()
                WHERE TramiteRequisitoId = ? AND TramiteId = ?
                """,
                next_state,
                observation or None,
                current_user.login,
                requirement_id,
                case_id,
            )
            if next_state in {"OBSERVADO", "RECHAZADO"}:
                cursor.execute(
                    """
                    INSERT sec.ObservacionTramite
                        (TramiteId, TramiteRequisitoId, TipoObservacion, Observacion, EsSistema, UsuarioCreacion)
                    VALUES (?, ?, 'REVISION', ?, 0, ?)
                    """,
                    case_id,
                    requirement_id,
                    observation,
                    current_user.login,
                )
            elif next_state == "VALIDADO":
                cursor.execute(
                    """
                    UPDATE sec.ObservacionTramite
                    SET Resuelta = 1, FechaResolucion = SYSUTCDATETIME(), UsuarioResolucion = ?
                    WHERE TramiteId = ? AND TramiteRequisitoId = ? AND Resuelta = 0
                    """,
                    current_user.login,
                    case_id,
                    requirement_id,
                )

            _recalculate_case(cursor, case_id, current_user.login)
            _audit(
                cursor,
                case_id=case_id,
                entity="TramiteRequisito",
                entity_id=requirement_id,
                action="REVISION_DOCUMENTAL",
                user=current_user,
                data={"estado_anterior": previous_state, "estado_nuevo": next_state, "observacion": observation},
            )
            connection.commit()
        return _case_detail(case_id)
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible guardar la revisión documental.",
        ) from exc
