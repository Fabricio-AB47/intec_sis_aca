from datetime import datetime
from io import BytesIO
import re
from typing import Annotated, Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl.styles import Font, PatternFill
import pandas as pd
from pydantic import BaseModel, Field

from app.core.security import SessionUser, require_roles
from app.routers.students import _MATRICULA_ACTUAL_CTE
from app.services.db import get_connection

router = APIRouter(prefix="/api/students/senescyt", tags=["senescyt"])

_SENESCYT_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")

_REPORT_COLUMNS = [
    "tipoDocumentoId",
    "numeroIdentificacion",
    "primerApellido",
    "segundoApellido",
    "primerNombre",
    "segundoNombre",
    "sexoId",
    "generoId",
    "estadocivilId",
    "etniaId",
    "pueblonacionalidadId",
    "tipoSangre",
    "discapacidad",
    "porcentajeDiscapacidad",
    "numCarnetConadis",
    "tipoDiscapacidad",
    "fechaNacimiento",
    "paisNacionalidadId",
    "provinciaNacimientoId",
    "cantonNacimientoId",
    "paisResidenciaId",
    "provinciaResidenciaId",
    "cantonResidenciaId",
    "tipoColegioId",
    "modalidadCarrera",
    "jornadaCarrera",
    "fechaInicioCarrera",
    "fechaMatricula",
    "tipoMatriculaId",
    "nivelAcademicoQueCursa",
    "duracionPeriodoAcademico",
    "haRepetidoAlMenosUnaMateria",
    "paraleloId",
    "haPerdidoLaGratuidad",
    "recibePensionDiferenciada",
    "estudianteocupacionId",
    "ingresosestudianteId",
    "bonodesarrolloId",
    "haRealizadoPracticasPreprofesionales",
    "nroHorasPracticasPreprofesionalesPorPeriodo",
    "entornoInstitucionalPracticasProfesionales",
    "sectorEconomicoPracticaProfesional",
    "tipoBecaId",
    "primeraRazonBecaId",
    "segundaRazonBecaId",
    "terceraRazonBecaId",
    "cuartaRazonBecaId",
    "quintaRazonBecaId",
    "sextaRazonBecaId",
    "montoBeca",
    "porcientoBecaCoberturaArancel",
    "porcientoBecaCoberturaManuntencion",
    "financiamientoBeca",
    "montoAyudaEconomica",
    "montoCreditoEducativo",
    "participaEnProyectoVinculacionSociedad",
    "tipoAlcanceProyectoVinculacionId",
    "correoElectronico",
    "numeroCelular",
    "nivelFormacionPadre",
    "nivelFormacionMadre",
    "ingresoTotalHogar",
    "cantidadMiembrosHogar",
]

_NUMERIC_COLUMNS = [
    "tipoDocumentoId",
    "sexoId",
    "generoId",
    "estadocivilId",
    "etniaId",
    "pueblonacionalidadId",
    "tipoSangre",
    "tipoDiscapacidad",
    "discapacidad",
    "porcentajeDiscapacidad",
    "tipoColegioId",
    "modalidadCarrera",
    "jornadaCarrera",
    "tipoMatriculaId",
    "nivelAcademicoQueCursa",
    "duracionPeriodoAcademico",
    "haRepetidoAlMenosUnaMateria",
    "paraleloId",
    "haPerdidoLaGratuidad",
    "recibePensionDiferenciada",
    "estudianteocupacionId",
    "ingresosestudianteId",
    "bonodesarrolloId",
    "haRealizadoPracticasPreprofesionales",
    "entornoInstitucionalPracticasProfesionales",
    "sectorEconomicoPracticaProfesional",
    "tipoBecaId",
    "primeraRazonBecaId",
    "segundaRazonBecaId",
    "terceraRazonBecaId",
    "cuartaRazonBecaId",
    "quintaRazonBecaId",
    "sextaRazonBecaId",
    "financiamientoBeca",
    "montoAyudaEconomica",
    "montoCreditoEducativo",
    "participaEnProyectoVinculacionSociedad",
    "tipoAlcanceProyectoVinculacionId",
    "nivelFormacionPadre",
    "nivelFormacionMadre",
    "ingresoTotalHogar",
    "cantidadMiembrosHogar",
]

_UPDATE_FIELD_MAP = {
    "tipoDocumentoId": "tipodocumento",
    "numeroIdentificacion": "Cedula_Est",
    "sexoId": "Sexo",
    "generoId": "generoId",
    "estadocivilId": "EstadoCivil",
    "etniaId": "Etnia",
    "pueblonacionalidadId": "Nacionalidad",
    "tipoSangre": "tiposangre",
    "discapacidad": "discapacidad",
    "porcentajeDiscapacidad": "Porce_Capacidad",
    "numCarnetConadis": "No_Carnet",
    "tipoDiscapacidad": "Tipo_Capacidad",
    "fechaNacimiento": "Fecha_Nac",
    "paisNacionalidadId": "paisNacionalidadId",
    "provinciaNacimientoId": "provinciaNacimeintoId",
    "cantonNacimientoId": "cantonNacimeintoId",
    "paisResidenciaId": "paisResidenciaId",
    "provinciaResidenciaId": "codprov",
    "cantonResidenciaId": "Canton",
    "tipoColegioId": "tipoColegioId",
    "modalidadCarrera": "ModalidadEstudio",
    "jornadaCarrera": "Jornada",
    "fechaInicioCarrera": "Fecha_Ingreso",
    "fechaMatricula": "fechaMatricula",
    "tipoMatriculaId": "tipoMatriculaId",
    "nivelAcademicoQueCursa": "nivelAcademicoQueCursa",
    "duracionPeriodoAcademico": "duracionPeriodoAcademico",
    "haRepetidoAlMenosUnaMateria": "haRepetidoAlMenosUnaMateria",
    "paraleloId": "Paralelo",
    "haPerdidoLaGratuidad": "haPerdidoLaGratuidad",
    "recibePensionDiferenciada": "recibePensionDiferenciada",
    "estudianteocupacionId": "Ocupacion",
    "ingresosestudianteId": "ingresoEstudianteId",
    "bonodesarrolloId": "bonoDesarrolloId",
    "haRealizadoPracticasPreprofesionales": "haRealizadoPracticasPreprofesionales",
    "nroHorasPracticasPreprofesionalesPorPeriodo": "nroHorasPracticasPreprofesionales",
    "entornoInstitucionalPracticasProfesionales": "entornoInstitucionalPracticasProfesionales",
    "sectorEconomicoPracticaProfesional": "sectorEconomicoPracticaProfesional",
    "tipoBecaId": "tipoBecaId",
    "primeraRazonBecaId": "primeraRazonBecaId",
    "segundaRazonBecaId": "segundaRazonBecaId",
    "terceraRazonBecaId": "terceraRazonBecaId",
    "cuartaRazonBecaId": "cuartaRazonBecaId",
    "quintaRazonBecaId": "quintaRazonBecaId",
    "sextaRazonBecaId": "sextaRazonBecaId",
    "montoBeca": "montoBeca",
    "porcientoBecaCoberturaArancel": "porcientoBecaCoberturaArancel",
    "porcientoBecaCoberturaManuntencion": "porcientoBecaCoberturaManuntencion",
    "financiamientoBeca": "financiamientoBeca",
    "montoAyudaEconomica": "montoAyudaEconomica",
    "montoCreditoEducativo": "montoCreditoEducativo",
    "participaEnProyectoVinculacionSociedad": "participaEnProyectoVinculacionSociedad",
    "tipoAlcanceProyectoVinculacionId": "tipoAlcanceProyectoVinculacionId",
    "correoElectronico": "correointec",
    "numeroCelular": "movil",
    "nivelFormacionPadre": "nivelFormacionPadre",
    "nivelFormacionMadre": "nivelFormacionMadre",
    "ingresoTotalHogar": "IngresoHogar",
    "cantidadMiembrosHogar": "Numpersonasvive",
}

_NAME_FIELDS = {"primerApellido", "segundoApellido", "primerNombre", "segundoNombre"}


class SenescytStudentUpdatePayload(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)

_DASHBOARD_ACTIVE_COUNT_QUERY = (
    _MATRICULA_ACTUAL_CTE
    + """
SELECT COUNT(*)
FROM base_cruce bc
WHERE bc.estado_codigo = 'A'
  AND bc.cod_anio_Basica IS NOT NULL
  AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), bc.nombre_carrera))), '') IS NOT NULL
  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), bc.nombre_carrera)))) NOT LIKE N'SIN CARRERA%';
"""
)

_QUERY = (
    _MATRICULA_ACTUAL_CTE
    + """
SELECT
    TRY_CONVERT(varchar(50), bc.codigo_estud) AS codigoEstud,
    e.tipodocumento AS tipoDocumentoId,
    e.Cedula_Est AS numeroIdentificacion,
    e.Apellidos_nombre,
    e.Sexo AS sexoId,
    e.generoId,
    e.EstadoCivil AS estadocivilId,
    e.Etnia AS etniaId,
    e.Nacionalidad AS pueblonacionalidadId,
    e.tiposangre AS tipoSangre,
    e.discapacidad,
    e.Porce_Capacidad AS porcentajeDiscapacidad,
    e.No_Carnet AS numCarnetConadis,
    e.Tipo_Capacidad AS tipoDiscapacidad,
    e.Fecha_Nac AS fechaNacimiento,
    e.paisNacionalidadId,
    e.provinciaNacimeintoId AS provinciaNacimientoId,
    e.cantonNacimeintoId AS cantonNacimientoId,
    e.paisResidenciaId,
    COALESCE(e.codprov, e.provinciaNacimeintoId) AS provinciaResidenciaId,
    COALESCE(e.Canton, e.cantonNacimeintoId) AS cantonResidenciaId,
    e.tipoColegioId,
    e.ModalidadEstudio AS modalidadCarrera,
    e.Jornada AS jornadaCarrera,
    e.Fecha_Ingreso AS fechaInicioCarrera,
    e.fechaMatricula,
    e.tipoMatriculaId,
    e.nivelAcademicoQueCursa,
    e.duracionPeriodoAcademico,
    e.haRepetidoAlMenosUnaMateria,
    e.Paralelo AS paraleloId,
    e.haPerdidoLaGratuidad,
    e.recibePensionDiferenciada,
    e.Ocupacion AS estudianteocupacionId,
    e.ingresoEstudianteId AS ingresosestudianteId,
    e.bonoDesarrolloId AS bonodesarrolloId,
    e.haRealizadoPracticasPreprofesionales,
    e.nroHorasPracticasPreprofesionales AS nroHorasPracticasPreprofesionalesPorPeriodo,
    e.entornoInstitucionalPracticasProfesionales,
    e.sectorEconomicoPracticaProfesional,
    e.tipoBecaId,
    e.primeraRazonBecaId,
    e.segundaRazonBecaId,
    e.terceraRazonBecaId,
    e.cuartaRazonBecaId,
    e.quintaRazonBecaId,
    e.sextaRazonBecaId,
    e.montoBeca,
    e.porcientoBecaCoberturaArancel,
    e.porcientoBecaCoberturaManuntencion,
    e.financiamientoBeca,
    e.montoAyudaEconomica,
    e.montoCreditoEducativo,
    e.participaEnProyectoVinculacionSociedad,
    e.tipoAlcanceProyectoVinculacionId,
    COALESCE(
        NULLIF(TRY_CONVERT(nvarchar(320), e.correointec), ''),
        NULLIF(TRY_CONVERT(nvarchar(320), e.correo), ''),
        NULLIF(TRY_CONVERT(nvarchar(320), c.correointec), ''),
        NULLIF(TRY_CONVERT(nvarchar(320), bc.correo_intec_datos), '')
    ) AS correoElectronico,
    e.movil AS numeroCelular,
    e.nivelFormacionPadre,
    e.nivelFormacionMadre,
    e.IngresoHogar AS ingresoTotalHogar,
    e.Numpersonasvive AS cantidadMiembrosHogar,
    COALESCE(
        NULLIF(TRY_CONVERT(nvarchar(255), ca.Nombre_Basica), ''),
        NULLIF(TRY_CONVERT(nvarchar(255), bc.nombre_carrera), ''),
        N'Sin carrera'
    ) AS nombreCarrera
FROM base_cruce bc
INNER JOIN dbo.DATOS_ESTUD e
    ON TRY_CONVERT(varchar(50), e.codigo_estud) = TRY_CONVERT(varchar(50), bc.codigo_estud)
OUTER APPLY (
    SELECT TOP (1) TRY_CONVERT(nvarchar(320), ci.correointec) AS correointec
    FROM dbo.CorreosEstudIntec ci
    WHERE TRY_CONVERT(varchar(50), ci.codestud) = TRY_CONVERT(varchar(50), bc.codigo_estud)
    ORDER BY
        CASE
            WHEN UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), ci.Estado)))) = N'ACTIVO' THEN 0
            ELSE 1
        END,
        TRY_CONVERT(nvarchar(320), ci.correointec)
) c
OUTER APPLY (
    SELECT TOP (1) ca.Nombre_Basica
    FROM dbo.CARRERAS ca
    WHERE TRY_CONVERT(varchar(50), ca.Cod_AnioBasica) = TRY_CONVERT(varchar(50), bc.cod_anio_Basica)
    ORDER BY TRY_CONVERT(nvarchar(255), ca.Nombre_Basica)
) ca
WHERE bc.estado_codigo = 'A'
  AND bc.cod_anio_Basica IS NOT NULL
  AND NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), bc.nombre_carrera))), '') IS NOT NULL
  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), bc.nombre_carrera)))) NOT LIKE N'SIN CARRERA%';
"""
)


def _read_dataframe() -> pd.DataFrame:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY)
        columns = [column[0] for column in cursor.description]
        rows = [tuple(row) for row in cursor.fetchall()]
    return pd.DataFrame.from_records(rows, columns=columns)


def _count_scalar(sql: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        return int(cursor.fetchone()[0] or 0)


def _clean_income(value: Any) -> float:
    if pd.isna(value):
        return 0
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return 0
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return 0


def _clean_amount(value: Any) -> Any:
    if pd.isna(value):
        return "NA"
    text = str(value).strip()
    if not text or text.upper() == "NA":
        return "NA"
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return "NA"
    return number


def _normalize_conadis(value: Any) -> str:
    if pd.isna(value):
        return "NA"
    text = str(value).strip()
    if not text:
        return "NA"
    digits = re.sub(r"\D", "", text)
    if digits and int(digits) == 0:
        return "0"
    return digits if len(digits) == 10 else "NA"


def _format_province(value: Any) -> str | None:
    if pd.isna(value):
        return None
    digits = re.sub(r"\D", "", str(value).strip())
    if not digits:
        return None
    base = str(int(digits))
    if base == "50":
        return "05"
    if len(base) >= 2:
        return base[:2]
    return base.zfill(2)


def _split_names(full_name: Any) -> pd.Series:
    parts = str(full_name or "").split()
    return pd.Series(
        {
            "primerApellido": parts[0] if len(parts) > 0 else None,
            "segundoApellido": parts[1] if len(parts) > 1 else None,
            "primerNombre": parts[2] if len(parts) > 2 else None,
            "segundoNombre": " ".join(parts[3:]) if len(parts) > 3 else "NA",
        }
    )


def _filled(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.upper() not in {"NA", "N/A", "NONE", "NULL"}


def _safe_filename(value: Any) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "", str(value or "Sin carrera")).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "Sin carrera"


def _style_header(worksheet: Any) -> None:
    fill = PatternFill("solid", fgColor="DDEBF7")
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
        cell.fill = fill


def _student_display_name(row: pd.Series) -> str:
    parts = [
        row.get("primerApellido"),
        row.get("segundoApellido"),
        row.get("primerNombre"),
        row.get("segundoNombre"),
    ]
    name = " ".join(str(part).strip() for part in parts if _filled(part))
    return name or "Sin nombre"


def _student_missing_detail(row: pd.Series) -> dict[str, Any] | None:
    missing = [column for column in _REPORT_COLUMNS if not _filled(row.get(column))]
    if not missing:
        return None
    filled = len(_REPORT_COLUMNS) - len(missing)
    return {
        "codigo_estud": str(row.get("codigoEstud") or "").strip(),
        "estudiante": _student_display_name(row),
        "numero_identificacion": str(row.get("numeroIdentificacion") or "").strip(),
        "campos_llenos": filled,
        "campos_pendientes": len(missing),
        "campos_totales": len(_REPORT_COLUMNS),
        "porcentaje_lleno": round((filled / max(len(_REPORT_COLUMNS), 1)) * 100, 2),
        "campos_faltantes": missing,
    }


def _normalize_payload_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text != "" else None
    return value


def _student_summary(row: pd.Series) -> dict[str, Any]:
    missing = [column for column in _REPORT_COLUMNS if not _filled(row.get(column))]
    filled = len(_REPORT_COLUMNS) - len(missing)
    return {
        "codigo_estud": str(row.get("codigoEstud") or "").strip(),
        "estudiante": _student_display_name(row),
        "numero_identificacion": str(row.get("numeroIdentificacion") or "").strip(),
        "nombre_carrera": str(row.get("nombreCarrera") or "Sin carrera").strip(),
        "campos_llenos": filled,
        "campos_pendientes": len(missing),
        "campos_totales": len(_REPORT_COLUMNS),
        "porcentaje_lleno": round((filled / max(len(_REPORT_COLUMNS), 1)) * 100, 2),
        "campos_faltantes": missing,
    }


def _load_normalized_students() -> pd.DataFrame:
    return _normalize_dataframe(_read_dataframe())


def _find_student_row(codigo_estud: str) -> pd.Series:
    dataframe = _load_normalized_students()
    matches = dataframe[
        dataframe["codigoEstud"].astype(str).str.strip() == str(codigo_estud).strip()
    ]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado en datos SENECYT.")
    return matches.iloc[0]


def _student_detail_response(row: pd.Series) -> dict[str, Any]:
    return {
        "student": _student_summary(row),
        "fields": {column: _normalize_payload_value(row.get(column)) for column in _REPORT_COLUMNS},
        "report_columns": _REPORT_COLUMNS,
    }


def _normalize_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["nombreCarrera"] = df["nombreCarrera"].apply(
        lambda value: re.sub(r"\s+", " ", str(value or "Sin carrera")).strip() or "Sin carrera"
    )
    for column in _NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["ingresoTotalHogar"] = df["ingresoTotalHogar"].apply(_clean_income)
    df["ingresoTotalHogar"] = pd.to_numeric(df["ingresoTotalHogar"], errors="coerce").fillna(0)

    df["porcentajeDiscapacidad"] = df["porcentajeDiscapacidad"].fillna(0)
    df["tipoSangre"] = df["tipoSangre"].fillna(0).replace(0, 7)
    df["tipoDiscapacidad"] = df["tipoDiscapacidad"].fillna(7).replace(0, 7)
    df["discapacidad"] = df["discapacidad"].fillna(0).replace(0, 2)
    df["pueblonacionalidadId"] = df["pueblonacionalidadId"].fillna(0).replace(0, 34)
    df["tipoColegioId"] = df["tipoColegioId"].fillna(0).replace(0, 1)
    df["financiamientoBeca"] = df["financiamientoBeca"].fillna(4).replace(0, 4)
    df["numeroCelular"] = df["numeroCelular"].where(df["numeroCelular"].isna(), df["numeroCelular"].astype(str))
    df["tipoDocumentoId"] = df["tipoDocumentoId"].fillna(0).replace(0, 1)
    df["haPerdidoLaGratuidad"] = df["haPerdidoLaGratuidad"].fillna(0).replace(0, 3)
    df["recibePensionDiferenciada"] = df["recibePensionDiferenciada"].fillna(0).replace(0, 2)
    df["haRepetidoAlMenosUnaMateria"] = df["haRepetidoAlMenosUnaMateria"].fillna(0).replace(0, 2)
    df["sectorEconomicoPracticaProfesional"] = df["sectorEconomicoPracticaProfesional"].fillna(0).replace(0, 22)
    df["tipoBecaId"] = df["tipoBecaId"].fillna(0).replace(0, 3)
    df["bonodesarrolloId"] = df["bonodesarrolloId"].fillna(0).replace(0, 2)
    df["paraleloId"] = df["paraleloId"].fillna(0).replace(0, 1)
    df["ingresosestudianteId"] = df["ingresosestudianteId"].fillna(0).replace(0, 4)
    for column in [
        "primeraRazonBecaId",
        "segundaRazonBecaId",
        "terceraRazonBecaId",
        "cuartaRazonBecaId",
        "quintaRazonBecaId",
        "sextaRazonBecaId",
    ]:
        df[column] = df[column].fillna(0).replace(0, 2)
    df["haRealizadoPracticasPreprofesionales"] = df["haRealizadoPracticasPreprofesionales"].fillna(0).replace(0, 2)
    df["entornoInstitucionalPracticasProfesionales"] = df["entornoInstitucionalPracticasProfesionales"].fillna(0).replace(0, 5)
    for column in ["montoAyudaEconomica", "montoCreditoEducativo"]:
        df[column] = df[column].apply(_clean_amount)
    df["montoBeca"] = pd.to_numeric(df["montoBeca"], errors="coerce").fillna(0)
    df["participaEnProyectoVinculacionSociedad"] = df["participaEnProyectoVinculacionSociedad"].fillna(0).replace(0, 3)
    df["tipoAlcanceProyectoVinculacionId"] = df["tipoAlcanceProyectoVinculacionId"].fillna(0).replace(0, 5)
    df["nroHorasPracticasPreprofesionalesPorPeriodo"] = df[
        "nroHorasPracticasPreprofesionalesPorPeriodo"
    ].apply(lambda value: "NA" if pd.isna(value) or str(value).strip() == "" else value)
    df["porcientoBecaCoberturaArancel"] = pd.to_numeric(
        df["porcientoBecaCoberturaArancel"], errors="coerce"
    ).apply(lambda value: "NA" if pd.isna(value) else int(value))
    df["numCarnetConadis"] = df["numCarnetConadis"].apply(_normalize_conadis)
    df["provinciaResidenciaId"] = df["provinciaResidenciaId"].apply(_format_province)

    names = df["Apellidos_nombre"].apply(_split_names)
    df = df.drop(columns=["Apellidos_nombre"])
    df = pd.concat(
        [
            df[["tipoDocumentoId", "numeroIdentificacion"]],
            names,
            df.drop(columns=["tipoDocumentoId", "numeroIdentificacion"]),
        ],
        axis=1,
    )
    return df[_REPORT_COLUMNS + ["nombreCarrera", "codigoEstud"]]


def _build_report() -> dict[str, Any]:
    raw = _read_dataframe()
    final = _normalize_dataframe(raw)
    total_report = len(final)
    total_active_dashboard = _count_scalar(_DASHBOARD_ACTIVE_COUNT_QUERY)
    total_active_datos_estud = total_report

    field_totals = {
        column: int(final[column].map(_filled).sum())
        for column in _REPORT_COLUMNS
    }
    total_cells = max(total_report * len(_REPORT_COLUMNS), 1)
    filled_cells = sum(field_totals.values())

    career_rows: list[dict[str, Any]] = []
    student_missing_rows: list[dict[str, Any]] = []
    if total_report:
        for career, group in final.groupby("nombreCarrera", dropna=False):
            filled = int(sum(group[column].map(_filled).sum() for column in _REPORT_COLUMNS))
            cells = max(len(group) * len(_REPORT_COLUMNS), 1)
            students_missing = [
                detail
                for _, row in group.iterrows()
                if (detail := _student_missing_detail(row)) is not None
            ]
            students_missing.sort(key=lambda item: (-item["campos_pendientes"], item["estudiante"]))
            career_name = str(career or "Sin carrera")
            for student in students_missing:
                student_missing_rows.append({"nombre_carrera": career_name, **student})
            career_rows.append(
                {
                    "nombre_carrera": career_name,
                    "total_estudiantes": int(len(group)),
                    "campos_llenos": filled,
                    "campos_totales": cells,
                    "campos_pendientes": int(cells - filled),
                    "estudiantes_con_pendientes": len(students_missing),
                    "porcentaje_lleno": round((filled / cells) * 100, 2),
                    "students_missing": students_missing,
                }
            )
    career_rows.sort(key=lambda item: item["nombre_carrera"])

    missing_fields = sorted(
        (
            {
                "campo": column,
                "llenos": filled,
                "pendientes": total_report - filled,
                "porcentaje_lleno": round((filled / max(total_report, 1)) * 100, 2),
            }
            for column, filled in field_totals.items()
        ),
        key=lambda item: (-item["pendientes"], item["campo"]),
    )

    warnings: list[str] = []
    if total_report != total_active_dashboard:
        warnings.append("El total exportable no coincide con los activos del tablero de matricula.")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataframe": final,
        "summary": {
            "total_reporte": total_report,
            "total_activos_sistema": total_active_dashboard,
            "total_activos_datos_estud": total_active_datos_estud,
            "coincide_activos": total_report == total_active_dashboard,
            "total_carreras": len(career_rows),
            "total_columnas": len(_REPORT_COLUMNS),
            "campos_llenos": filled_cells,
            "campos_totales": total_cells,
            "porcentaje_lleno": round((filled_cells / total_cells) * 100, 2),
        },
        "careers": career_rows,
        "students_missing": student_missing_rows,
        "missing_fields": missing_fields[:15],
        "warnings": warnings,
        "criteria": {
            "fuente": "DATOS_ESTUD directo para los datos del estudiante; CARRERAXESTUD/PENSUM solo definen carrera y estado del reporte",
            "activos": "Mismo criterio del tablero de matricula; excluye estudiantes sin carrera registrada",
            "matricula": "Matricula actual validada contra carrera, pensum y estado del tablero",
            "export": "Un archivo Excel por carrera dentro de un ZIP",
        },
    }


def _dataframe_to_workbook_bytes(dataframe: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Datos")
        worksheet = writer.book["Datos"]
        _style_header(worksheet)
        for column in worksheet.columns:
            column_letter = column[0].column_letter
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 42)
            worksheet.column_dimensions[column_letter].width = max(width, 12)
    output.seek(0)
    return output.getvalue()


def _summary_workbook_bytes(report: dict[str, Any]) -> bytes:
    summary = report["summary"]
    rows = [
        {"Indicador": key, "Valor": value}
        for key, value in summary.items()
    ]
    criteria_rows = [
        {"Indicador": key, "Valor": value}
        for key, value in report["criteria"].items()
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows + [{}] + criteria_rows).to_excel(writer, index=False, sheet_name="Resumen")
        career_rows = [
            {key: value for key, value in item.items() if key != "students_missing"}
            for item in report["careers"]
        ]
        pd.DataFrame(career_rows).to_excel(writer, index=False, sheet_name="Carreras")
        pd.DataFrame(report["missing_fields"]).to_excel(writer, index=False, sheet_name="Campos pendientes")
        if report.get("students_missing"):
            pending_rows = [
                {
                    **item,
                    "campos_faltantes": ", ".join(item.get("campos_faltantes") or []),
                }
                for item in report["students_missing"]
            ]
            pd.DataFrame(pending_rows).to_excel(writer, index=False, sheet_name="Estudiantes pendientes")
        for worksheet in writer.book.worksheets:
            _style_header(worksheet)
            for column in worksheet.columns:
                column_letter = column[0].column_letter
                width = min(max(len(str(cell.value or "")) for cell in column) + 2, 48)
                worksheet.column_dimensions[column_letter].width = max(width, 14)
    output.seek(0)
    return output.getvalue()


@router.get("/estudiantes/buscar")
def search_senescyt_students(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
    q: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    del current_user
    try:
        dataframe = _load_normalized_students()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error buscando estudiantes SENECYT: {exc}") from exc

    text = q.strip().casefold()
    if text:
        searchable = (
            dataframe["codigoEstud"].fillna("").astype(str)
            + " "
            + dataframe["numeroIdentificacion"].fillna("").astype(str)
            + " "
            + dataframe["primerApellido"].fillna("").astype(str)
            + " "
            + dataframe["segundoApellido"].fillna("").astype(str)
            + " "
            + dataframe["primerNombre"].fillna("").astype(str)
            + " "
            + dataframe["segundoNombre"].fillna("").astype(str)
        ).str.casefold()
        dataframe = dataframe[searchable.str.contains(re.escape(text), regex=True, na=False)]

    rows = [_student_summary(row) for _, row in dataframe.head(limit).iterrows()]
    return {"rows": rows, "total": int(len(dataframe)), "limit": limit, "query": q}


@router.get("/estudiantes/datos/{codigo_estud}")
def get_senescyt_student_data(
    codigo_estud: str,
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
) -> dict[str, Any]:
    del current_user
    return _student_detail_response(_find_student_row(codigo_estud))


@router.put("/estudiantes/datos/{codigo_estud}")
def update_senescyt_student_data(
    codigo_estud: str,
    payload: SenescytStudentUpdatePayload,
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
) -> dict[str, Any]:
    del current_user
    current_row = _find_student_row(codigo_estud)
    updates: dict[str, Any] = {}

    name_changed = bool(_NAME_FIELDS.intersection(payload.fields))
    if name_changed:
        name_values = {
            field: _normalize_payload_value(payload.fields.get(field, current_row.get(field)))
            for field in _NAME_FIELDS
        }
        full_name = " ".join(str(name_values[field]).strip() for field in [
            "primerApellido",
            "segundoApellido",
            "primerNombre",
            "segundoNombre",
        ] if _filled(name_values[field]))
        updates["Apellidos_nombre"] = full_name or None

    for field, value in payload.fields.items():
        column = _UPDATE_FIELD_MAP.get(field)
        if not column:
            continue
        updates[column] = _normalize_payload_value(value)

    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos validos para actualizar.")

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values()) + [codigo_estud]
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE dbo.DATOS_ESTUD
                SET {set_clause}
                WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                """,
                params,
            )
            affected = cursor.rowcount
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error actualizando DATOS_ESTUD: {exc}") from exc

    updated_row = _find_student_row(codigo_estud)
    return {
        "ok": True,
        "message": "Datos del estudiante actualizados.",
        "updated_fields": sorted(payload.fields.keys()),
        "affected_rows": int(affected or 0),
        **_student_detail_response(updated_row),
    }


@router.get("/estudiantes")
def senescyt_students_report(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        report = _build_report()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando reporte SENECYT: {exc}") from exc
    return {
        "generated_at": report["generated_at"],
        "summary": report["summary"],
        "careers": report["careers"],
        "missing_fields": report["missing_fields"],
        "warnings": report["warnings"],
        "criteria": report["criteria"],
    }


@router.get("/estudiantes/export")
def senescyt_students_export(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
    split_by_career: Annotated[bool, Query(description="Generar un Excel por carrera dentro del ZIP")] = True,
) -> StreamingResponse:
    del current_user
    try:
        report = _build_report()
        dataframe: pd.DataFrame = report["dataframe"]
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("resumen_senescyt.xlsx", _summary_workbook_bytes(report))
            if split_by_career:
                for career, group in dataframe.groupby("nombreCarrera", dropna=False):
                    filename = f"EstudiantesPorCarrera/{_safe_filename(career)}.xlsx"
                    archive.writestr(
                        filename,
                        _dataframe_to_workbook_bytes(group.drop(columns=["nombreCarrera", "codigoEstud"])),
                    )
            else:
                archive.writestr(
                    "senescyt_estudiantes.xlsx",
                    _dataframe_to_workbook_bytes(dataframe.drop(columns=["nombreCarrera", "codigoEstud"])),
                )
        output.seek(0)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error exportando reporte SENECYT: {exc}") from exc

    filename = f"senescyt_estudiantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
