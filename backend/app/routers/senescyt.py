from datetime import date, datetime
from io import BytesIO
import re
from typing import Annotated, Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
import pandas as pd
from pydantic import BaseModel, Field

from app.core.security import SessionUser, require_roles
from app.routers.students import _MATRICULA_CNE_CTE
from app.services.db import get_connection

router = APIRouter(prefix="/api/students/senescyt", tags=["senescyt"])

_SENESCYT_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR", "SECRETARIA")

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

_STUDENT_MODEL_ALIASES = {
    "ingresosestudianteId": "ingresoEstudianteId",
    "bonodesarrolloId": "bonoDesarrolloId",
}
_STUDENT_MODEL_COLUMNS = [_STUDENT_MODEL_ALIASES.get(column, column) for column in _REPORT_COLUMNS]

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
    _MATRICULA_CNE_CTE
    + """
SELECT COUNT(*)
FROM matricula_cne_catalogada cne
WHERE cne.estado_codigo = 'A';
"""
)

_STUDENT_SELECT = """
SELECT
    TRY_CONVERT(varchar(50), e.codigo_estud) AS codigoEstud,
    e.tipodocumento AS tipoDocumentoId,
    COALESCE(
        NULLIF(LTRIM(RTRIM(TRY_CONVERT(varchar(50), e.Cedula_Est))), ''),
        cne.Cedula_Est
    ) AS numeroIdentificacion,
    COALESCE(
        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), e.Apellidos_nombre))), ''),
        cne.Apellidos_nombre
    ) AS Apellidos_nombre,
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
    e.codprov AS provinciaResidenciaId,
    e.Canton AS cantonResidenciaId,
    e.tipoColegioId,
    e.ModalidadEstudio AS modalidadCarrera,
    e.Jornada AS jornadaCarrera,
    e.Fecha_Ingreso AS fechaInicioCarrera,
    {fecha_matricula} AS fechaMatricula,
    e.tipoMatriculaId,
    {nivel_academico} AS nivelAcademicoQueCursa,
    e.duracionPeriodoAcademico,
    e.haRepetidoAlMenosUnaMateria,
    {paralelo_id} AS paraleloId,
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
    correo.CorreoIntec AS correoElectronico,
    e.movil AS numeroCelular,
    e.nivelFormacionPadre,
    e.nivelFormacionMadre,
    e.IngresoHogar AS ingresoTotalHogar,
    e.Numpersonasvive AS cantidadMiembrosHogar,
    cne.nombre_carrera AS nombreCarrera
"""

_STUDENT_EMAIL_APPLY = """
OUTER APPLY (
    SELECT TOP (1) correos.CorreoIntec
    FROM dbo.CorreosEstudIntec correos
    WHERE TRY_CONVERT(varchar(50), correos.codestud) = TRY_CONVERT(varchar(50), e.codigo_estud)
    ORDER BY
        CASE WHEN NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(320), correos.CorreoIntec))), '') IS NULL THEN 1 ELSE 0 END,
        TRY_CONVERT(nvarchar(320), correos.CorreoIntec)
) correo
"""

_QUERY = _MATRICULA_CNE_CTE + _STUDENT_SELECT.format(
    fecha_matricula="e.fechaMatricula", nivel_academico="e.nivelAcademicoQueCursa",
    paralelo_id="e.Paralelo",
) + """
FROM matricula_cne_catalogada cne
OUTER APPLY (
    SELECT TOP (1) datos.*
    FROM dbo.DATOS_ESTUD datos
    WHERE LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), datos.Cedula_Est))) = cne.Cedula_Est
    ORDER BY TRY_CONVERT(bigint, datos.codigo_estud) DESC
) e
""" + _STUDENT_EMAIL_APPLY + """
WHERE cne.estado_codigo = 'A';
"""


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


def _clean_income(value: Any) -> float | None:
    if pd.isna(value):
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _clean_amount(value: Any) -> Any:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.upper() == "NA":
        return "NA"
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return "NA"
    return number


def _normalize_conadis(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.upper() == "NA":
        return "NA"
    digits = re.sub(r"\D", "", text)
    if digits and int(digits) == 0:
        return "0"
    return digits if len(digits) == 7 else "NA"


def _format_province(value: Any) -> str | None:
    return _model_geographic_code(value, 2)


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
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


def _fetch_datos_estud_raw(codigo_estud: str) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM dbo.DATOS_ESTUD
            WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
            """,
            codigo_estud,
        )
        row = cursor.fetchone()
        if not row:
            return {"columns": [], "fields": {}}
        columns = [column[0] for column in cursor.description]
        values = {column: _normalize_payload_value(value) for column, value in zip(columns, row)}
        return {"columns": columns, "fields": values}


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
        raise HTTPException(status_code=404, detail="Estudiante no encontrado en los datos de SENESCYT.")
    return matches.iloc[0]


def _student_detail_response(row: pd.Series) -> dict[str, Any]:
    raw = _fetch_datos_estud_raw(str(row.get("codigoEstud") or ""))
    return {
        "student": _student_summary(row),
        "fields": {column: _normalize_payload_value(row.get(column)) for column in _REPORT_COLUMNS},
        "report_columns": _REPORT_COLUMNS,
        "datos_estud_fields": raw["fields"],
        "datos_estud_columns": raw["columns"],
    }


def _normalize_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["nombreCarrera"] = df["nombreCarrera"].apply(
        lambda value: re.sub(r"\s+", " ", str(value or "Sin carrera")).strip() or "Sin carrera"
    )
    for column in _NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["ingresoTotalHogar"] = df["ingresoTotalHogar"].apply(_clean_income)
    df["ingresoTotalHogar"] = pd.to_numeric(df["ingresoTotalHogar"], errors="coerce")

    # Do not turn missing source values into affirmative SENESCYT codes.
    for column in ("tipoSangre", "tipoDiscapacidad", "discapacidad", "pueblonacionalidadId",
                   "tipoColegioId", "financiamientoBeca", "tipoDocumentoId", "haPerdidoLaGratuidad",
                   "recibePensionDiferenciada", "haRepetidoAlMenosUnaMateria", "sectorEconomicoPracticaProfesional",
                   "tipoBecaId", "bonodesarrolloId", "paraleloId", "ingresosestudianteId",
                   "haRealizadoPracticasPreprofesionales", "entornoInstitucionalPracticasProfesionales",
                   "participaEnProyectoVinculacionSociedad", "tipoAlcanceProyectoVinculacionId"):
        df[column] = df[column].where(df[column].ne(0))
    df["numeroCelular"] = df["numeroCelular"].where(df["numeroCelular"].isna(), df["numeroCelular"].astype(str))
    for column in ("primeraRazonBecaId", "segundaRazonBecaId", "terceraRazonBecaId",
                   "cuartaRazonBecaId", "quintaRazonBecaId", "sextaRazonBecaId"):
        df[column] = df[column].where(df[column].ne(0))
    for column in ["montoAyudaEconomica", "montoCreditoEducativo"]:
        df[column] = df[column].apply(_clean_amount)
    df["montoBeca"] = pd.to_numeric(df["montoBeca"], errors="coerce")
    df["nroHorasPracticasPreprofesionalesPorPeriodo"] = df[
        "nroHorasPracticasPreprofesionalesPorPeriodo"
    ].apply(lambda value: None if pd.isna(value) or str(value).strip() == "" else value)
    df["porcientoBecaCoberturaArancel"] = pd.to_numeric(
        df["porcientoBecaCoberturaArancel"], errors="coerce"
    ).apply(lambda value: None if pd.isna(value) else int(value))
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
    raw = _read_student_audit_source(None, None)
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
        warnings.append("El total exportable no coincide con los estudiantes activos del tablero de matrícula.")

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
            "fuente": "DATOS_ESTUD para datos personales; CARRERAXESTUD y PENSUM para el semestre más alto; PERIODO y CARRERAXESTUD para la matrícula del último período elegible y PARALELOS.num para paraleloId.",
            "activos": "Mismo criterio del tablero de matrícula; excluye a los estudiantes sin carrera registrada.",
            "matricula": "Matrícula actual validada contra la carrera, el pensum y el estado del tablero.",
            "export": "Un archivo de Excel por carrera dentro de un ZIP.",
        },
    }


def _dataframe_to_workbook_bytes(dataframe: pd.DataFrame) -> bytes:
    return _student_model_workbook(dataframe)


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
        raise HTTPException(status_code=500, detail=f"Error al buscar estudiantes en SENESCYT: {exc}") from exc

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
        raise HTTPException(status_code=400, detail='No hay campos válidos para actualizar.')

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
        raise HTTPException(status_code=500, detail=f"Error al generar el reporte de SENESCYT: {exc}") from exc
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
        raise HTTPException(status_code=500, detail=f"Error al exportar el reporte de SENESCYT: {exc}") from exc

    filename = f"senescyt_estudiantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_TEACHER_REPORT_COLUMNS = [
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
    "direccionDomiciliaria",
    "provinciaSufragio",
    "numeroCelular",
    "correoElectronico",
    "numDomicilio",
    "discapacidad",
    "porcentajeDiscapacidad",
    "numCarnetDiscapacidad",
    "tipoDiscapacidad",
    "tipoEnfermedadCatastrofica",
    "fechaNacimiento",
    "paisNacionalidadId",
    "nivelFormacion",
    "fechaIngresoIES",
    "fechaSalidaIES",
    "relacionLaboralIESId",
    "ingresoConConcursoMeritos",
    "escalafonDocenteId",
    "cargoDirectivoId",
    "tiempoDedicacionId",
    "nombreUnidadAcademica",
    "nroasignaturasdocente",
    "nroHorasLaborablesSemanaEnCarreraPrograma",
    "nroHorasClaseSemanaCarreraPrograma",
    "nroHorasInvestigacionSemanaCarreraPrograma",
    "nroHorasAdministrativasSemanaCarreraPrograma",
    "nroHorasOtrasActividadesSemanaCarreraPrograma",
    "nroHorasVinculacionSociedad",
    "salarioMensual",
    "docenciaTecnicoSuperior",
    "docenciaTecnologico",
    "estaEnPeriodoSabatico",
    "fechaInicioPeriodoSabatico",
    "estaCursandoEstudiosId",
    "institucionDondeCursaEstudios",
    "paisEstudiosId",
    "tituloAObtener",
    "poseeBecaId",
    "tipoBecaId",
    "montoBeca",
    "financiamientoBecaId",
    "pubRevistasCienInIndexadasId",
    "numPubRevistasCientifIndexadas",
    "docenciaTecnologicoUniversitario",
    "docenciaEspecializacionTecnologica",
    "docenciaMaestriaTecnologica",
]

_STUDENT_AUDIT_COLUMNS = _REPORT_COLUMNS

_REPORT_TARGETS = {"estudiantes", "docentes"}
_EXPORT_MODES = {"completo", "faltantes"}


def _read_sql_dataframe(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        columns = [column[0] for column in cursor.description]
        rows = [tuple(row) for row in cursor.fetchall()]
    return pd.DataFrame.from_records(rows, columns=columns)


def _career_catalog() -> list[dict[str, Any]]:
    dataframe = _read_sql_dataframe(
        """
        SELECT
            TRY_CONVERT(varchar(50), Cod_AnioBasica) AS codigo_carrera,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), Nombre_Basica))) AS nombre_carrera
        FROM dbo.CARRERAS
        WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), Nombre_Basica))), '') IS NOT NULL
        ORDER BY Nombre_Basica
        """
    )
    return [
        {
            "codigo_carrera": str(row.codigo_carrera or "").strip(),
            "nombre_carrera": str(row.nombre_carrera or "").strip(),
        }
        for row in dataframe.itertuples()
    ]


def _split_report_name(full_name: Any) -> dict[str, Any]:
    values = _split_names(full_name)
    return {key: _normalize_payload_value(values.get(key)) for key in _NAME_FIELDS}


def _period_catalog() -> list[dict[str, Any]]:
    dataframe = _read_sql_dataframe("""
        SELECT cod_periodo AS codigo_periodo,
            LTRIM(RTRIM(Detalle_Periodo)) AS nombre_periodo,
            CONVERT(varchar(10), fechain, 23) AS fecha_inicio,
            CONVERT(varchar(10), fechafin, 23) AS fecha_fin
        FROM dbo.PERIODO
        ORDER BY fechain DESC, cod_periodo DESC
    """)
    return [
        {
            "codigo_periodo": int(row.codigo_periodo),
            "nombre_periodo": str(row.nombre_periodo or row.codigo_periodo).strip(),
            "fecha_inicio": _normalize_payload_value(row.fecha_inicio),
            "fecha_fin": _normalize_payload_value(row.fecha_fin),
        }
        for row in dataframe.itertuples()
    ]


def _academic_scope_sql(periods: list[int] | None, cutoff: date | None, *, target: str) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    selected = list(dict.fromkeys(periods or []))
    if selected:
        conditions.append(f"p.cod_periodo IN ({', '.join('?' for _ in selected)})")
        params.extend(selected)
    if cutoff:
        if target == "estudiantes":
            # Missing enrollment dates cannot establish eligibility before the cutoff.
            conditions.append("TRY_CONVERT(date, cx.Fecha_Matricula) <= ?")
            params.append(cutoff)
        else:
            conditions.append("p.fechain <= ?")
            params.append(cutoff)
            conditions.append("(ingreso.fecha IS NULL OR ingreso.fecha <= ?)")
            params.append(cutoff)
    return "".join(f" AND {condition}" for condition in conditions), params


def _read_student_audit_source(periods: list[int] | None, cutoff: date | None) -> pd.DataFrame:
    scope, params = _academic_scope_sql(periods, cutoff, target="estudiantes")
    # Resolve the parallel within each eligible period, never across a student's history.
    # Use the institutional enrollment catalog ID, not the separate scheduling catalog Paralelo.
    sql = """
    WITH matriculas AS (
        SELECT cx.codigo_estud, cx.cod_anio_Basica, cx.codigo_periodo,
            MIN(TRY_CONVERT(date, cx.Fecha_Matricula)) AS fecha_matricula,
            MAX(p.fechain) AS inicio_periodo,
            MAX(CASE WHEN TRY_CONVERT(int, pen.Semestre) > 0
                THEN TRY_CONVERT(int, pen.Semestre) END) AS semestre,
            CASE WHEN COUNT(DISTINCT NULLIF(UPPER(LTRIM(RTRIM(cx.paralelo))), '')) = 1
                AND COUNT(NULLIF(LTRIM(RTRIM(cx.paralelo)), '')) = COUNT(*)
                THEN MIN(UPPER(LTRIM(RTRIM(cx.paralelo)))) END AS paralelo
        FROM dbo.CARRERAXESTUD cx
        INNER JOIN dbo.PERIODO p ON cx.codigo_periodo = p.cod_periodo
        LEFT JOIN dbo.PENSUM pen ON pen.codigo_materia = cx.codigo_materia
            AND pen.Cod_AnioBasica = cx.cod_anio_Basica
        WHERE UPPER(LTRIM(RTRIM(p.TipoMatricula))) IN ('R', 'H')
            AND cx.cod_anio_Basica NOT IN (12, 13)
    """ + scope + """
        GROUP BY cx.codigo_estud, cx.cod_anio_Basica, cx.codigo_periodo
    ), seleccion AS (
        SELECT *, MAX(semestre) OVER (
            PARTITION BY codigo_estud, cod_anio_Basica
        ) AS nivel_academico,
        ROW_NUMBER() OVER (
            PARTITION BY codigo_estud, cod_anio_Basica
            ORDER BY COALESCE(inicio_periodo, fecha_matricula) DESC,
                codigo_periodo DESC, fecha_matricula DESC
        ) AS posicion
        FROM matriculas
    ), matricula_cne_catalogada AS (
        SELECT s.codigo_estud, s.fecha_matricula, s.nivel_academico,
            catalogo.paralelo_id, e.Cedula_Est, e.Apellidos_nombre,
            LTRIM(RTRIM(c.Nombre_Basica)) AS nombre_carrera
        FROM seleccion s
        INNER JOIN dbo.DATOS_ESTUD e ON e.codigo_estud = s.codigo_estud
        INNER JOIN dbo.ESTADO estado ON e.Estado = estado.IDESTADO
        INNER JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = s.cod_anio_Basica
        OUTER APPLY (
            SELECT CASE WHEN COUNT(*) = 1
                THEN MIN(TRY_CONVERT(int, par.num)) END AS paralelo_id
            FROM dbo.PARALELOS par
            WHERE UPPER(LTRIM(RTRIM(par.paralelo))) = s.paralelo
                AND TRY_CONVERT(int, par.num) BETWEEN 1 AND 20
        ) catalogo
        WHERE s.posicion = 1
            AND UPPER(LTRIM(RTRIM(TRY_CONVERT(varchar(10), estado.IDESTADO)))) = 'A'
    )
    """ + _STUDENT_SELECT.format(
        fecha_matricula="cne.fecha_matricula", nivel_academico="cne.nivel_academico",
        paralelo_id="cne.paralelo_id",
    ) + """
    FROM matricula_cne_catalogada cne
    INNER JOIN dbo.DATOS_ESTUD e ON e.codigo_estud = cne.codigo_estud
        AND e.Cedula_Est = cne.Cedula_Est
    """ + _STUDENT_EMAIL_APPLY
    return _read_sql_dataframe(sql, params)


def _prepare_student_audit_dataframe(periods: list[int] | None = None, cutoff: date | None = None) -> pd.DataFrame:
    raw = _read_student_audit_source(periods, cutoff)
    if raw.empty:
        return pd.DataFrame(columns=_STUDENT_AUDIT_COLUMNS + ["codigo", "nombreCompleto", "nombreCarrera"])

    df = _dedupe_career_model_rows(_apply_student_model_context(_normalize_dataframe(raw)), "fechaMatricula")
    df = df.rename(columns={"codigoEstud": "codigo"})
    for column in _STUDENT_AUDIT_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df["nombreCompleto"] = df.apply(_student_display_name, axis=1)
    df["nombreCarrera"] = df["nombreCarrera"].apply(
        lambda value: re.sub(r"\s+", " ", str(value or "Sin carrera")).strip() or "Sin carrera"
    )
    return df[_STUDENT_AUDIT_COLUMNS + ["codigo", "nombreCompleto", "nombreCarrera"]]


def _read_teacher_audit_dataframe(periods: list[int] | None = None, cutoff: date | None = None) -> pd.DataFrame:
    scope, params = _academic_scope_sql(periods, cutoff, target="docentes")
    sql = """
    SELECT DISTINCT
        TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo,
        d.apellidos_nombre AS nombreOriginal,
        d.tipoDocumentoId,
        LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.cedula_doc))) AS numeroIdentificacion,
        d.sexo AS sexoId,
        d.generoId,
        d.estado_civil AS estadocivilId,
        d.etniaId,
        CAST(NULL AS nvarchar(100)) AS pueblonacionalidadId,
        d.numDomicilio AS numDomicilio,
        d.Direccion AS direccionDomiciliaria,
        d.provinciaSufragio,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.movil))), ''),
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.telefono))), '')
        ) AS numeroCelular,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(320), d.correo))), ''),
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(320), d.correop))), '')
        ) AS correoElectronico,
        d.discapacidad,
        d.porcen_discapa AS porcentajeDiscapacidad,
        d.num_carnet_cona AS numCarnetDiscapacidad,
        d.tipo_discapa AS tipoDiscapacidad,
        d.tipoEnfermedadCatastrofica,
        d.fecha_nac AS fechaNacimiento,
        d.paisNacionalidadId,
        d.nivelFormacion,
        d.fechaIngresoIES,
        d.fechaSalidaIES,
        d.relacionLaboralIESId,
        d.ingresoConCursoMeritos AS ingresoConConcursoMeritos,
        d.escalafonDocenteId,
        d.cargoDirectivoId,
        d.tiempoDedicacionId,
        d.nombreUnidadAcademica,
        d.nroasignaturasdocente AS nroasignaturasdocente,
        d.nroHorasLaborablesSemanaEnCarreraPrograma,
        d.nroHorasClaseSemanaCarreraPrograma,
        d.nroHorasInvestigacionSemanaCarreraPrograma,
        d.nroHorasAdministrativasSemanaCarreraPrograma,
        d.nroHorasOtrasActividadesSemanaCarreraPrograma,
        d.nroHorasVinculacionSociedad,
        d.salarioMensual,
        d.docenciaTecnicoSuperior,
        d.docenciaTecnologico,
        d.estaEnPeriodoSabatico,
        d.fechaInicioPeriodoSabatico,
        d.estaCursandoEstudiosId,
        d.institucionDOndeCursaEstudios AS institucionDondeCursaEstudios,
        d.paisEstudiosId,
        d.tituloAObtener,
        d.poseeBecaId,
        d.tipoBecaId,
        d.montoBeca,
        d.financiamientoBecaId,
        d.pubRevistasCienInIndexadasId,
        d.numPubRevistasCientifIndexadas,
        d.docenciaTecnologicoUniversitario,
        d.docenciaEspecializacionTecnologica,
        d.docenciaMaestriaTecnologica,
        COALESCE(
            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), c.Nombre_Basica))), ''),
            N'Sin carrera'
        ) AS nombreCarrera
    FROM dbo.CARRERAXDOCENTE cd
    INNER JOIN dbo.CARRERAS c
        ON TRY_CONVERT(varchar(50), cd.cod_Anio_Basica) = TRY_CONVERT(varchar(50), c.Cod_AnioBasica)
    INNER JOIN dbo.DATOSDOCENTE d
        ON TRY_CONVERT(varchar(50), cd.codigo_doc) = TRY_CONVERT(varchar(50), d.codigo_doc)
    INNER JOIN dbo.PERIODO p ON cd.codigo_periodo = p.cod_periodo
    OUTER APPLY (
        SELECT COALESCE(
            TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(d.fechaIngresoIES)), ''), 23),
            TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(d.fechaIngresoIES)), ''), 126),
            TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(d.fechaIngresoIES)), ''), 103)
        ) AS fecha
    ) ingreso
    WHERE EXISTS (
        SELECT 1
        FROM dbo.USUARIOS u
        WHERE LTRIM(RTRIM(TRY_CONVERT(varchar(50), u.cedula))) = LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.cedula_doc)))
          AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), u.Estado)))) IN (N'A', N'ACTIVO', N'ACTIVA')
    )
    """ + scope + """
    ORDER BY nombreCarrera, nombreOriginal
    """
    raw = _read_sql_dataframe(sql, params)
    if raw.empty:
        return pd.DataFrame(columns=_TEACHER_REPORT_COLUMNS + ["codigo", "nombreCompleto", "nombreCarrera"])

    names = raw["nombreOriginal"].apply(_split_report_name).apply(pd.Series)
    df = pd.concat([raw.drop(columns=["nombreOriginal"], errors="ignore"), names], axis=1)
    for column in _TEACHER_REPORT_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = _apply_teacher_model_context(df)
    df["nombreCompleto"] = df.apply(
        lambda row: " ".join(str(row.get(field) or "").strip() for field in [
            "primerApellido",
            "segundoApellido",
            "primerNombre",
            "segundoNombre",
        ] if _filled(row.get(field))) or "Sin nombre",
        axis=1,
    )
    df["nombreCarrera"] = df["nombreCarrera"].apply(
        lambda value: re.sub(r"\s+", " ", str(value or "Sin carrera")).strip() or "Sin carrera"
    )
    df = _dedupe_career_model_rows(df, "fechaIngresoIES")
    return df[_TEACHER_REPORT_COLUMNS + ["codigo", "nombreCompleto", "nombreCarrera"]]


def _load_senescyt_audit_dataframe(
    target: str, periods: list[int] | None = None, cutoff: date | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    if target == "estudiantes":
        return _prepare_student_audit_dataframe(periods, cutoff), _STUDENT_AUDIT_COLUMNS
    if target == "docentes":
        return _read_teacher_audit_dataframe(periods, cutoff), _TEACHER_REPORT_COLUMNS
    raise HTTPException(status_code=400, detail='Tipo de reporte SENESCYT no válido.')


def _normalize_career_filters(careers: list[str] | None) -> list[str]:
    selected: list[str] = []
    values = [careers] if isinstance(careers, str) else (careers or [])
    for value in values:
        for item in str(value or "").split("|"):
            name = re.sub(r"\s+", " ", item).strip()
            if name and name.casefold() not in {career.casefold() for career in selected}:
                selected.append(name)
    return selected


def _filter_by_career(dataframe: pd.DataFrame, careers: list[str] | None) -> pd.DataFrame:
    selected = _normalize_career_filters(careers)
    if not selected:
        return dataframe
    names = dataframe["nombreCarrera"].fillna("").astype(str).str.casefold()
    mask = names.isin({career.casefold() for career in selected})
    return dataframe[mask].copy()


_NO_APLICA_MARKERS = {"NA", "N/A", "N.A", "N.A.", "NO APLICA", "NO APLICA.", "NO_APLICA"}
_EMPTY_MARKERS = {"", "NONE", "NULL", "NULO", "SIN DATO", "SIN DATOS"}
_UNSELECTED_MARKERS = {
    "0",
    "0.0",
    "00",
    "000",
    "0000",
    "SELECCIONE",
    "-- SELECCIONE --",
    "- SELECCIONE -",
    "SELECCIONE ESTADO",
}

_ZERO_ALLOWED_FIELDS = {
    ("estudiantes", "ingresoTotalHogar"),
}

_ZERO_CONTEXT_FIELDS = {
    ("estudiantes", "porcentajeDiscapacidad"),
    ("estudiantes", "numCarnetConadis"),
    ("estudiantes", "montoBeca"),
    ("docentes", "porcentajeDiscapacidad"),
    ("docentes", "numCarnetDiscapacidad"),
    ("docentes", "montoBeca"),
    ("docentes", "numPubRevistasCientifIndexadas"),
}

_STUDENT_CODE_FIELDS = {
    "tipoDocumentoId",
    "sexoId",
    "generoId",
    "estadocivilId",
    "etniaId",
    "pueblonacionalidadId",
    "tipoSangre",
    "discapacidad",
    "tipoDiscapacidad",
    "paisNacionalidadId",
    "provinciaNacimientoId",
    "cantonNacimientoId",
    "paisResidenciaId",
    "provinciaResidenciaId",
    "cantonResidenciaId",
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
    "porcientoBecaCoberturaArancel",
    "porcientoBecaCoberturaManuntencion",
    "financiamientoBeca",
    "participaEnProyectoVinculacionSociedad",
    "tipoAlcanceProyectoVinculacionId",
    "nivelFormacionPadre",
    "nivelFormacionMadre",
}

_TEACHER_CODE_FIELDS = {
    "tipoDocumentoId",
    "sexoId",
    "generoId",
    "estadocivilId",
    "etniaId",
    "pueblonacionalidadId",
    "provinciaSufragio",
    "discapacidad",
    "tipoDiscapacidad",
    "paisNacionalidadId",
    "nivelFormacion",
    "relacionLaboralIESId",
    "ingresoConConcursoMeritos",
    "escalafonDocenteId",
    "cargoDirectivoId",
    "tiempoDedicacionId",
    "docenciaTecnicoSuperior",
    "docenciaTecnologico",
    "docenciaTecnologicoUniversitario",
    "docenciaEspecializacionTecnologica",
    "docenciaMaestriaTecnologica",
    "estaEnPeriodoSabatico",
    "estaCursandoEstudiosId",
    "paisEstudiosId",
    "poseeBecaId",
    "tipoBecaId",
    "financiamientoBecaId",
    "pubRevistasCienInIndexadasId",
}

_COMMON_GUIDE_CODES = {
    "sexoId": {"1", "2"},
    "generoId": {"1", "2"},
    "estadocivilId": {str(code) for code in range(1, 6)},
    "etniaId": {str(code) for code in range(1, 10)},
    "discapacidad": {"1", "2"},
    "tipoDiscapacidad": {str(code) for code in range(1, 8)},
}
_STUDENT_GUIDE_CODES = {
    **_COMMON_GUIDE_CODES,
    "tipoSangre": {str(code) for code in range(1, 9)},
    "tipoColegioId": {str(code) for code in range(1, 7)},
    "modalidadCarrera": {str(code) for code in range(1, 7)},
    "jornadaCarrera": {str(code) for code in range(1, 5)},
    "tipoMatriculaId": {"1", "2", "3"},
    "nivelAcademicoQueCursa": {str(code) for code in range(1, 10)},
    "paraleloId": {str(code) for code in range(1, 21)},
    "haRepetidoAlMenosUnaMateria": {"1", "2"},
    "haPerdidoLaGratuidad": {"1", "2", "3"},
    "recibePensionDiferenciada": {"1", "2", "3"},
    "estudianteocupacionId": {"1", "2"},
    "ingresosestudianteId": {"1", "2", "3", "4"},
    "bonodesarrolloId": {"1", "2"},
    "haRealizadoPracticasPreprofesionales": {"1", "2"},
    "tipoBecaId": {"1", "2", "3"},
    "financiamientoBeca": {"1", "2", "3", "4"},
    "participaEnProyectoVinculacionSociedad": {"1", "2", "3"},
    "tipoAlcanceProyectoVinculacionId": {str(code) for code in range(1, 6)},
    "nivelFormacionPadre": {str(code) for code in range(1, 11)},
    "nivelFormacionMadre": {str(code) for code in range(1, 11)},
}
_STUDENT_GUIDE_CODES.update({
    column: {"1", "2"} for column in (
        "primeraRazonBecaId", "segundaRazonBecaId", "terceraRazonBecaId",
        "cuartaRazonBecaId", "quintaRazonBecaId", "sextaRazonBecaId"
    )
})
_TEACHER_GUIDE_CODES = {
    **_COMMON_GUIDE_CODES,
    "relacionLaboralIESId": {str(code) for code in range(1, 6)},
    "ingresoConConcursoMeritos": {"1", "2"},
    "escalafonDocenteId": {str(code) for code in range(1, 7)},
    "cargoDirectivoId": {str(code) for code in range(1, 8)},
    "tiempoDedicacionId": {"1", "2", "3"},
    "estaCursandoEstudiosId": {str(code) for code in range(1, 12)},
    "poseeBecaId": {"1", "2"},
    "tipoBecaId": {"1", "2", "3"},
    "financiamientoBecaId": {str(code) for code in range(1, 6)},
    "pubRevistasCienInIndexadasId": {"1", "2"},
}
_TEACHER_GUIDE_CODES.update({
    column: {"1", "2"} for column in (
        "docenciaTecnicoSuperior", "docenciaTecnologico", "docenciaTecnologicoUniversitario",
        "docenciaEspecializacionTecnologica", "docenciaMaestriaTecnologica", "estaEnPeriodoSabatico"
    )
})

_DOCUMENT_TYPE_CEDULA = "1"
_DOCUMENT_TYPE_PASSPORT = "2"
_DOCUMENT_TYPE_LABELS = {
    _DOCUMENT_TYPE_CEDULA: "Cedula",
    _DOCUMENT_TYPE_PASSPORT: "Pasaporte",
}
_PASSPORT_PATTERNS = (
    ("Ecuador / Espana / Argentina", re.compile(r"^[A-Z]{3}\d{6}$")),
    ("Estados Unidos", re.compile(r"^[A-Z]\d{8}$")),
    ("Pasaporte de 9 caracteres", re.compile(r"^[A-Z0-9]{9}$")),
)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _cell_code(value: Any) -> str:
    return re.sub(r"\s+", " ", _cell_text(value)).strip().upper()


def _is_zero_text(text: str) -> bool:
    if not text:
        return False
    try:
        return float(text.replace(",", ".")) == 0
    except ValueError:
        return False


def _is_no_code(value: Any) -> bool:
    return _cell_code(value) in {"2", "NO", "N", "FALSE", "FALSO"}


def _has_selected_code(value: Any) -> bool:
    code = _cell_code(value)
    return bool(code) and code not in _EMPTY_MARKERS and code not in _UNSELECTED_MARKERS and "SELECCIONE" not in code


def _normalize_document_number(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _cell_text(value).upper())


def _infer_document_type(number: Any) -> str:
    normalized = _normalize_document_number(number)
    if re.fullmatch(r"\d{10}", normalized):
        return _DOCUMENT_TYPE_CEDULA
    if any(pattern.fullmatch(normalized) for _, pattern in _PASSPORT_PATTERNS):
        return _DOCUMENT_TYPE_PASSPORT
    return ""


def _document_country_format(number: Any) -> str:
    normalized = _normalize_document_number(number)
    for label, pattern in _PASSPORT_PATTERNS:
        if pattern.fullmatch(normalized):
            return label
    return ""


def _document_analysis(row: pd.Series) -> dict[str, Any]:
    type_code = _cell_code(row.get("tipoDocumentoId"))
    number = _normalize_document_number(row.get("numeroIdentificacion"))
    inferred_code = _infer_document_type(number)
    expected_code = inferred_code or (type_code if type_code in _DOCUMENT_TYPE_LABELS else "")
    is_type_selected = type_code in _DOCUMENT_TYPE_LABELS
    is_number_valid = bool(inferred_code)
    format_label = ""

    if inferred_code == _DOCUMENT_TYPE_CEDULA:
        format_label = "Cédula ecuatoriana: 10 dígitos"
    elif inferred_code == _DOCUMENT_TYPE_PASSPORT:
        format_label = _document_country_format(number)

    is_consistent = bool(is_type_selected and is_number_valid and type_code == inferred_code)
    suggested_code = expected_code if expected_code in _DOCUMENT_TYPE_LABELS else ""
    issues: list[str] = []
    if not is_type_selected:
        issues.append("tipoDocumentoId debe ser 1 para cédula o 2 para pasaporte.")
    if not number:
        issues.append("numeroIdentificacion está vacío.")
    elif not is_number_valid:
        issues.append(
            "numeroIdentificacion no cumple los 10 dígitos de cédula ni el formato de pasaporte permitido."
        )
    if is_type_selected and inferred_code and type_code != inferred_code:
        issues.append(
            f"tipoDocumentoId registrado {type_code} no coincide con el documento; sugerido {inferred_code}"
        )

    return {
        "tipo_actual": type_code,
        "tipo_actual_label": _DOCUMENT_TYPE_LABELS.get(type_code, "Sin seleccionar"),
        "numero": number,
        "tipo_sugerido": suggested_code,
        "tipo_sugerido_label": _DOCUMENT_TYPE_LABELS.get(suggested_code, ""),
        "formato": format_label,
        "valido": is_consistent,
        "numero_valido": is_number_valid,
        "tipo_valido": is_type_selected,
        "observaciones": issues,
    }


def _is_no_beca_student(row: pd.Series) -> bool:
    return _cell_code(row.get("tipoBecaId")) == "3"


def _is_no_study_teacher(row: pd.Series) -> bool:
    return _cell_code(row.get("estaCursandoEstudiosId")) in {"8", "NA", "N/A", "NO APLICA"}


def _is_no_beca_teacher(row: pd.Series) -> bool:
    return _is_no_study_teacher(row) or _is_no_code(row.get("poseeBecaId"))


def _field_has_contextual_no_aplica_code(row: pd.Series, column: str, target: str, code: str) -> bool:
    if target == "estudiantes":
        if column == "pueblonacionalidadId" and code == "34":
            return True
        if column == "tipoDiscapacidad" and code == "7":
            return True
        if column == "entornoInstitucionalPracticasProfesionales" and code == "5":
            return True
        if column == "sectorEconomicoPracticaProfesional" and code == "22":
            return True
        if column == "financiamientoBeca" and code == "4":
            return True
        if column == "tipoAlcanceProyectoVinculacionId" and code == "5":
            return True

    if target == "docentes":
        if column == "tipoDiscapacidad" and code == "7":
            return True
        if column == "tipoBecaId" and code == "3":
            return True
        if column == "financiamientoBecaId" and code == "5":
            return True

    return False


def _field_allows_zero(row: pd.Series, column: str, target: str) -> bool:
    if (target, column) in _ZERO_ALLOWED_FIELDS:
        return True
    if target == "estudiantes":
        if column in {"porcentajeDiscapacidad", "numCarnetConadis"}:
            return _is_no_code(row.get("discapacidad"))
        if column == "montoBeca":
            return _is_no_beca_student(row)
    if target == "docentes":
        if column in {"porcentajeDiscapacidad", "numCarnetDiscapacidad"}:
            return _is_no_code(row.get("discapacidad"))
        if column == "montoBeca":
            return _is_no_beca_teacher(row)
        if column == "numPubRevistasCientifIndexadas":
            return _is_no_code(row.get("pubRevistasCienInIndexadasId"))
    return True


def _field_allows_no_aplica(row: pd.Series, column: str, target: str) -> bool:
    if target == "estudiantes":
        if column in {"correoElectronico", "ingresoTotalHogar"}:
            return True
        if column in {"provinciaNacimientoId", "cantonNacimientoId"}:
            return _has_selected_code(row.get("paisNacionalidadId")) and _cell_code(row.get("paisNacionalidadId")) != "56"
        if column in {"provinciaResidenciaId", "cantonResidenciaId"}:
            return _has_selected_code(row.get("paisResidenciaId")) and _cell_code(row.get("paisResidenciaId")) != "56"
        if column == "pueblonacionalidadId":
            etnia = row.get("etniaId")
            return _has_selected_code(etnia) and _cell_code(etnia) != "1"
        if column == "porcientoBecaCoberturaManuntencion":
            return True
        if column == "porcientoBecaCoberturaArancel":
            return _is_no_beca_student(row)
        if column in {"montoAyudaEconomica", "montoCreditoEducativo"}:
            return True
        if _is_no_code(row.get("discapacidad")) and column in {
            "porcentajeDiscapacidad",
            "numCarnetConadis",
            "tipoDiscapacidad",
        }:
            return True
        if _is_no_code(row.get("haRealizadoPracticasPreprofesionales")) and column in {
            "nroHorasPracticasPreprofesionalesPorPeriodo",
            "entornoInstitucionalPracticasProfesionales",
            "sectorEconomicoPracticaProfesional",
        }:
            return True
        if _is_no_beca_student(row) and column in {
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
        }:
            return True
        if _cell_code(row.get("participaEnProyectoVinculacionSociedad")) in {"2", "3", "NO", "N"} and column == "tipoAlcanceProyectoVinculacionId":
            return True

    if target == "docentes":
        if column == "numDomicilio":
            return True
        if column == "provinciaSufragio":
            return _has_selected_code(row.get("paisNacionalidadId")) and _cell_code(row.get("paisNacionalidadId")) != "56"
        if column == "fechaSalidaIES":
            return True  # The teacher source is limited to active users.
        if _is_no_code(row.get("discapacidad")) and column in {
            "tipoDiscapacidad",
            "porcentajeDiscapacidad",
            "numCarnetDiscapacidad",
        }:
            return True
        if _is_no_code(row.get("estaEnPeriodoSabatico")) and column == "fechaInicioPeriodoSabatico":
            return True
        if _is_no_study_teacher(row) and column in {
            "institucionDondeCursaEstudios",
            "paisEstudiosId",
            "tituloAObtener",
            "poseeBecaId",
            "tipoBecaId",
            "montoBeca",
            "financiamientoBecaId",
        }:
            return True
        if _is_no_beca_teacher(row) and column in {"tipoBecaId", "montoBeca", "financiamientoBecaId"}:
            return True
        if _is_no_code(row.get("pubRevistasCienInIndexadasId")) and column == "numPubRevistasCientifIndexadas":
            return True

    return False


def _audit_field_filled(row: pd.Series, column: str, target: str) -> bool:
    if column == "tipoDocumentoId":
        analysis = _document_analysis(row)
        return bool(analysis["tipo_valido"] and analysis["tipo_actual"] == analysis["tipo_sugerido"])
    if column == "numeroIdentificacion":
        return bool(_document_analysis(row)["numero_valido"])
    text = _cell_text(row.get(column))
    code = _cell_code(row.get(column))
    if code in _EMPTY_MARKERS or "SELECCIONE" in code:
        return False
    if _is_zero_text(text) and (target, column) in _ZERO_ALLOWED_FIELDS:
        return True
    if _is_zero_text(text) and (target, column) in _ZERO_CONTEXT_FIELDS:
        return _field_allows_zero(row, column, target)
    if code in _NO_APLICA_MARKERS:
        return _field_allows_no_aplica(row, column, target)
    if _field_has_contextual_no_aplica_code(row, column, target, code):
        return _field_allows_no_aplica(row, column, target)
    if code in {"0001-01-01", "0001-01-01 00:00:00"}:
        return _field_allows_no_aplica(row, column, target)
    date_columns = {"fechaNacimiento", "fechaInicioCarrera", "fechaMatricula"} if target == "estudiantes" else {
        "fechaNacimiento", "fechaIngresoIES", "fechaSalidaIES", "fechaInicioPeriodoSabatico"
    }
    if column in date_columns:
        normalized_date = _model_date(row.get(column))
        return bool(normalized_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized_date))
    if column == "numeroCelular":
        return bool(re.fullmatch(r"\d{10}", text))
    if column in {"numCarnetConadis", "numCarnetDiscapacidad"}:
        return bool(re.fullmatch(r"\d{7}", text))
    if column == "correoElectronico":
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))
    if target == "docentes" and column == "nroHorasLaborablesSemanaEnCarreraPrograma":
        parts = ("nroHorasClaseSemanaCarreraPrograma", "nroHorasInvestigacionSemanaCarreraPrograma",
                 "nroHorasAdministrativasSemanaCarreraPrograma", "nroHorasOtrasActividadesSemanaCarreraPrograma",
                 "nroHorasVinculacionSociedad")
        hours = [_cell_text(row.get(field)) for field in (column, *parts)]
        return all(value.isdigit() for value in hours) and int(hours[0]) == sum(int(value) for value in hours[1:])
    if target == "estudiantes" and column in {
        "provinciaNacimientoId", "cantonNacimientoId", "provinciaResidenciaId", "cantonResidenciaId"
    }:
        width = 4 if column.startswith("canton") else 2
        return bool(re.fullmatch(rf"\d{{{width}}}", _model_geographic_code(row.get(column), width) or ""))
    guide_codes = _STUDENT_GUIDE_CODES if target == "estudiantes" else _TEACHER_GUIDE_CODES
    if column in guide_codes:
        return code in guide_codes[column]
    code_fields = _STUDENT_CODE_FIELDS if target == "estudiantes" else _TEACHER_CODE_FIELDS
    if column in code_fields and code in _UNSELECTED_MARKERS:
        return False
    if _is_zero_text(text) and column in code_fields:
        return False
    return bool(text)


def _missing_columns(row: pd.Series, report_columns: list[str], target: str) -> list[str]:
    return [column for column in report_columns if not _audit_field_filled(row, column, target)]


def _count_filled(dataframe: pd.DataFrame, column: str, target: str) -> int:
    return int(sum(1 for _, row in dataframe.iterrows() if _audit_field_filled(row, column, target)))


def _excel_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _missing_export_record(
    row: pd.Series,
    target: str,
    report_columns: list[str],
    missing: list[str],
) -> dict[str, Any]:
    filled = len(report_columns) - len(missing)
    document = _document_analysis(row)
    record: dict[str, Any] = {
        "tipo": target,
        "codigo": str(row.get("codigo") or "").strip(),
        "identificacion": str(row.get("numeroIdentificacion") or "").strip(),
        "tipo_documento_actual": document.get("tipo_actual"),
        "tipo_documento_sugerido": document.get("tipo_sugerido"),
        "documento_formato": document.get("formato"),
        "documento_observaciones": "; ".join(document.get("observaciones") or []),
        "nombre": str(row.get("nombreCompleto") or "Sin nombre").strip(),
        "carrera": str(row.get("nombreCarrera") or "Sin carrera").strip(),
        "correo": str(row.get("correoElectronico") or row.get("correoPersonal") or "").strip(),
        "telefono": str(row.get("numeroCelular") or "").strip(),
        "campos_llenos": filled,
        "campos_pendientes": len(missing),
        "campos_totales": len(report_columns),
        "porcentaje_lleno": round((filled / max(len(report_columns), 1)) * 100, 2),
        "campos_faltantes": ", ".join(missing),
    }
    record.update({column: _excel_value(row.get(column)) for column in report_columns})
    return record


def _dedupe_missing_records(records: list[dict[str, Any]], include_career: bool) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for record in sorted(
        records,
        key=lambda item: (
            -int(item.get("campos_pendientes") or 0),
            str(item.get("nombre") or ""),
            str(item.get("carrera") or ""),
        ),
    ):
        identity = str(record.get("identificacion") or record.get("codigo") or "").strip().casefold()
        if not identity:
            identity = f"sin-id:{record.get('nombre', '')}".casefold()
        career_key = str(record.get("carrera") or "").strip().casefold() if include_career else ""
        selected.setdefault((identity, career_key), record)
    return sorted(selected.values(), key=lambda item: (str(item.get("carrera") or ""), str(item.get("nombre") or "")))


def _unique_sheet_name(writer: pd.ExcelWriter, base: str) -> str:
    clean = _safe_filename(base).replace("'", "")[:31] or "Hoja"
    name = clean
    suffix = 2
    while name in writer.book.sheetnames:
        extra = f" {suffix}"
        name = f"{clean[:31 - len(extra)]}{extra}"
        suffix += 1
    return name


def _build_document_summary(dataframe: pd.DataFrame) -> dict[str, Any]:
    totals = {
        "total_registros": int(len(dataframe)),
        "documentos_validos": 0,
        "cedulas_validas": 0,
        "pasaportes_validos": 0,
        "tipo_incorrecto": 0,
        "numero_invalido": 0,
        "sin_tipo": 0,
        "sin_numero": 0,
        "pendientes": 0,
        "porcentaje_validos": 0,
        "reglas": [
            {
                "codigo": 1,
                "tipo": "Cédula",
                "formato": "10 dígitos numéricos",
            },
            {
                "codigo": 2,
                "tipo": "Pasaporte",
                "formato": "9 caracteres alfanumericos en mayusculas",
            },
        ],
    }
    if dataframe.empty:
        return totals

    for _, row in dataframe.iterrows():
        analysis = _document_analysis(row)
        suggested = analysis["tipo_sugerido"]
        if analysis["valido"]:
            totals["documentos_validos"] += 1
            if suggested == _DOCUMENT_TYPE_CEDULA:
                totals["cedulas_validas"] += 1
            elif suggested == _DOCUMENT_TYPE_PASSPORT:
                totals["pasaportes_validos"] += 1
        else:
            totals["pendientes"] += 1
        if not analysis["tipo_valido"]:
            totals["sin_tipo"] += 1
        elif analysis["tipo_sugerido"] and analysis["tipo_actual"] != analysis["tipo_sugerido"]:
            totals["tipo_incorrecto"] += 1
        if not analysis["numero"]:
            totals["sin_numero"] += 1
        elif not analysis["numero_valido"]:
            totals["numero_invalido"] += 1

    totals["porcentaje_validos"] = round(
        (totals["documentos_validos"] / max(totals["total_registros"], 1)) * 100,
        2,
    )
    return totals


def _build_senescyt_audit_from_dataframe(
    target: str,
    dataframe: pd.DataFrame,
    report_columns: list[str],
    selected_careers: list[str] | None = None,
) -> dict[str, Any]:
    selected_careers = selected_careers or []
    total_rows = int(len(dataframe))
    total_cells = max(total_rows * len(report_columns), 1)
    field_totals = {column: _count_filled(dataframe, column, target) for column in report_columns} if total_rows else {
        column: 0 for column in report_columns
    }
    filled_cells = int(sum(field_totals.values()))

    row_summaries: list[dict[str, Any]] = []
    missing_records: list[dict[str, Any]] = []
    missing_field_records: list[dict[str, Any]] = []
    for _, row in dataframe.iterrows():
        missing = _missing_columns(row, report_columns, target)
        filled = len(report_columns) - len(missing)
        document_analysis = _document_analysis(row)
        row_summary = {
            "codigo": str(row.get("codigo") or "").strip(),
            "identificacion": str(row.get("numeroIdentificacion") or "").strip(),
            "documento": document_analysis,
            "nombre": str(row.get("nombreCompleto") or "Sin nombre").strip(),
            "nombre_carrera": str(row.get("nombreCarrera") or "Sin carrera").strip(),
            "correo": str(row.get("correoElectronico") or row.get("correoPersonal") or "").strip(),
            "telefono": str(row.get("numeroCelular") or "").strip(),
            "campos_llenos": filled,
            "campos_pendientes": len(missing),
            "campos_totales": len(report_columns),
            "porcentaje_lleno": round((filled / max(len(report_columns), 1)) * 100, 2),
            "campos_faltantes": missing,
            "fields": {column: _excel_value(row.get(column)) for column in report_columns},
        }
        row_summaries.append(row_summary)
        if missing:
            missing_records.append(_missing_export_record(row, target, report_columns, missing))
            for column in missing:
                missing_field_records.append({
                    "tipo": target,
                    "codigo": row_summary["codigo"],
                    "identificacion": row_summary["identificacion"],
                    "nombre": row_summary["nombre"],
                    "carrera": row_summary["nombre_carrera"],
                    "correo": row_summary["correo"],
                    "telefono": row_summary["telefono"],
                    "campo": column,
                    "valor_actual": _excel_value(row.get(column)),
                })

    career_rows: list[dict[str, Any]] = []
    if total_rows:
        for career_name, group in dataframe.groupby("nombreCarrera", dropna=False):
            group_filled = int(sum(_count_filled(group, column, target) for column in report_columns))
            group_cells = max(len(group) * len(report_columns), 1)
            career_missing_students = [
                item for item in row_summaries if item["nombre_carrera"] == str(career_name or "Sin carrera")
            ]
            career_rows.append({
                "nombre_carrera": str(career_name or "Sin carrera"),
                "total_registros": int(len(group)),
                "campos_llenos": group_filled,
                "campos_totales": group_cells,
                "campos_pendientes": int(group_cells - group_filled),
                "registros_con_pendientes": sum(1 for item in career_missing_students if item["campos_pendientes"] > 0),
                "porcentaje_lleno": round((group_filled / group_cells) * 100, 2),
            })

    missing_fields = sorted(
        (
            {
                "campo": column,
                "llenos": filled,
                "pendientes": total_rows - filled,
                "porcentaje_lleno": round((filled / max(total_rows, 1)) * 100, 2),
            }
            for column, filled in field_totals.items()
        ),
        key=lambda item: (-item["pendientes"], item["campo"]),
    )
    row_summaries.sort(key=lambda item: (-item["campos_pendientes"], item["nombre"]))
    career_rows.sort(key=lambda item: item["nombre_carrera"])
    missing_records_by_career = _dedupe_missing_records(missing_records, include_career=True)
    missing_records_global = _dedupe_missing_records(missing_records, include_career=False)
    document_summary = _build_document_summary(dataframe)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "career_filter": selected_careers,
        "dataframe": dataframe,
        "report_columns": report_columns,
        "summary": {
            "total_registros": total_rows,
            "total_carreras": len(career_rows),
            "total_columnas": len(report_columns),
            "campos_llenos": filled_cells,
            "campos_totales": total_cells if total_rows else 0,
            "campos_pendientes": max((total_rows * len(report_columns)) - filled_cells, 0),
            "porcentaje_lleno": round((filled_cells / total_cells) * 100, 2) if total_rows else 0,
            "registros_con_pendientes": sum(1 for item in row_summaries if item["campos_pendientes"] > 0),
        },
        "documentos": document_summary,
        "careers": career_rows,
        "rows": [item for item in row_summaries if item["campos_pendientes"] > 0][:100],
        "missing_fields": missing_fields,
        "missing_records": missing_records_by_career,
        "missing_records_global": missing_records_global,
        "missing_field_records": missing_field_records,
    }


def _build_senescyt_audit(
    target: str, careers: list[str] | None = None,
    periods: list[int] | None = None, cutoff: date | None = None,
) -> dict[str, Any]:
    selected_careers = _normalize_career_filters(careers)
    selected_periods = list(dict.fromkeys(periods or []))
    dataframe, report_columns = _load_senescyt_audit_dataframe(target, selected_periods, cutoff)
    dataframe = _filter_by_career(dataframe, selected_careers)
    report = _build_senescyt_audit_from_dataframe(target, dataframe, report_columns, selected_careers)
    report.update({
        "period_filter": selected_periods,
        "cutoff_date": cutoff.isoformat() if cutoff else None,
        "active_only": True,
    })
    return report


def _audit_export_workbook(report: dict[str, Any], mode: str) -> bytes:
    dataframe: pd.DataFrame = report["dataframe"]
    report_columns: list[str] = report["report_columns"]
    target = report["target"]
    missing_export_columns = [
        "tipo",
        "codigo",
        "identificacion",
        "tipo_documento_actual",
        "tipo_documento_sugerido",
        "documento_formato",
        "documento_observaciones",
        "nombre",
        "carrera",
        "correo",
        "telefono",
        "campos_llenos",
        "campos_pendientes",
        "campos_totales",
        "porcentaje_lleno",
        "campos_faltantes",
        *report_columns,
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if mode == "faltantes":
            global_rows = report.get("missing_records_global") or []
            career_rows = report.get("missing_records") or []
            detail_rows = report.get("missing_field_records") or []
            pd.DataFrame(global_rows, columns=missing_export_columns).to_excel(
                writer,
                index=False,
                sheet_name="Faltantes global",
            )
            pd.DataFrame(career_rows, columns=missing_export_columns).to_excel(
                writer,
                index=False,
                sheet_name="Faltantes carreras",
            )
            pd.DataFrame(detail_rows).to_excel(
                writer,
                index=False,
                sheet_name="Detalle campos",
            )
            if career_rows:
                career_dataframe = pd.DataFrame(career_rows, columns=missing_export_columns)
                for career_name, group in career_dataframe.groupby("carrera", dropna=False):
                    sheet_name = _unique_sheet_name(writer, f"F {career_name}")
                    group.to_excel(writer, index=False, sheet_name=sheet_name)
        else:
            export_columns = report_columns + ["codigo", "nombreCompleto", "nombreCarrera"]
            if dataframe.empty:
                pd.DataFrame(columns=export_columns).to_excel(writer, index=False, sheet_name="Datos")
            else:
                sheet_count = 0
                for career_name, group in dataframe.groupby("nombreCarrera", dropna=False):
                    sheet_count += 1
                    sheet_name = _unique_sheet_name(writer, str(career_name or f"Carrera {sheet_count}"))
                    group[export_columns].to_excel(writer, index=False, sheet_name=sheet_name)
                if sheet_count == 0:
                    dataframe[export_columns].to_excel(writer, index=False, sheet_name=target.title())

        for worksheet in writer.book.worksheets:
            _style_header(worksheet)
            worksheet.freeze_panes = "A2"
            for column in worksheet.columns:
                column_letter = column[0].column_letter
                width = min(max(len(str(cell.value or "")) for cell in column) + 2, 48)
                worksheet.column_dimensions[column_letter].width = max(width, 12)

    output.seek(0)
    return output.getvalue()


def _model_workbook(dataframe: pd.DataFrame, columns: list[str], *, text_columns: tuple[str, ...]) -> bytes:
    values = dataframe.reindex(columns=columns)
    if "numeroIdentificacion" in values:
        values["numeroIdentificacion"] = values["numeroIdentificacion"].map(_normalize_document_number)
    for column in ("primerApellido", "segundoApellido", "primerNombre", "segundoNombre", "nombreUnidadAcademica"):
        if column in values:
            values[column] = values[column].map(
                lambda value: _cell_text(value).upper() if _cell_text(value) else None)
    for column in ("fechaNacimiento", "fechaIngresoIES", "fechaSalidaIES", "fechaInicioPeriodoSabatico",
                   "fechaInicioCarrera", "fechaMatricula"):
        if column in values:
            values[column] = values[column].map(_model_date)
    values = values.map(_normalize_payload_value)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        values.to_excel(writer, index=False, sheet_name="Sheet1", na_rep="")
        worksheet = writer.book["Sheet1"]
        header_border = Border(left=Side(style="thin"), right=Side(style="thin"))
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="top")
            cell.border = header_border
        for column in text_columns:
            index = columns.index(column) + 1
            for cells in worksheet.iter_cols(min_col=index, max_col=index, min_row=2):
                for cell in cells:
                    cell.number_format = "@"
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
    return output.getvalue()


def _model_date(value: Any) -> str | None:
    normalized = _normalize_payload_value(value)
    if normalized is None:
        return None
    if isinstance(normalized, datetime):
        return normalized.date().isoformat()
    if isinstance(normalized, date):
        return normalized.isoformat()
    value_text = str(normalized)
    try:
        return datetime.fromisoformat(value_text).date().isoformat()
    except ValueError:
        pass
    for format_string in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value_text, format_string).date().isoformat()
        except ValueError:
            continue
    return value_text


def _dedupe_model_rows(dataframe: pd.DataFrame, date_column: str) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    rows = dataframe.copy()
    identities = []
    for position, (_, row) in enumerate(rows.iterrows()):
        document = _normalize_document_number(row.get("numeroIdentificacion"))
        code = _cell_text(row.get("codigo"))
        identities.append(f"documento:{document}" if document else f"codigo:{code}" if code else f"fila:{position}")
    rows["_model_identity"] = identities
    if date_column in rows:
        rows["_model_date"] = pd.to_datetime(rows[date_column].map(_model_date), format="%Y-%m-%d", errors="coerce")
        rows = rows.sort_values("_model_date", ascending=False, kind="stable", na_position="last")
        rows = rows.drop(columns="_model_date")
    return rows.drop_duplicates(subset="_model_identity").drop(columns="_model_identity")


def _dedupe_career_model_rows(dataframe: pd.DataFrame, date_column: str) -> pd.DataFrame:
    if dataframe.empty or "nombreCarrera" not in dataframe:
        return dataframe.copy()
    return pd.concat(
        [_dedupe_model_rows(group, date_column) for _, group in dataframe.groupby("nombreCarrera", dropna=False)],
        ignore_index=True,
    )


def _teacher_model_workbook(report: dict[str, Any]) -> bytes:
    dataframe: pd.DataFrame = report["dataframe"]
    unique = _apply_teacher_model_context(_dedupe_model_rows(dataframe, "fechaIngresoIES"))
    if "provinciaSufragio" in unique:
        unique["provinciaSufragio"] = unique["provinciaSufragio"].map(lambda value: _model_geographic_code(value, 2))
    if "fechaSalidaIES" in unique:
        unique["fechaSalidaIES"] = unique["fechaSalidaIES"].map(lambda value: _model_date(value) or "NA")
    unique = unique.reindex(columns=_TEACHER_REPORT_COLUMNS)
    if not unique.empty:
        unique = unique.sort_values(by=["primerApellido", "segundoApellido", "primerNombre", "segundoNombre"],
                                    key=lambda series: series.fillna("").astype(str).str.casefold())
    return _model_workbook(unique, _TEACHER_REPORT_COLUMNS,
                           text_columns=("numeroIdentificacion", "numeroCelular", "provinciaSufragio",
                                         "numCarnetDiscapacidad"))


def _model_geographic_code(value: Any, width: int) -> str | None:
    normalized = _normalize_payload_value(value)
    if normalized is None:
        return None
    code = str(normalized)
    if re.fullmatch(r"\d+(?:\.0+)?", code):
        return code.split(".", 1)[0].zfill(width)
    return code


def _set_model_values_for_codes(dataframe: pd.DataFrame, source: str, codes: set[str], updates: dict[str, Any]) -> None:
    if source not in dataframe:
        return
    selected = dataframe[source].map(_cell_code).isin(codes)
    for column, value in updates.items():
        if column in dataframe:
            if isinstance(value, str):
                dataframe[column] = dataframe[column].astype(object)
            dataframe.loc[selected, column] = value


def _apply_student_model_context(dataframe: pd.DataFrame) -> pd.DataFrame:
    values = dataframe.reindex(columns=list(dict.fromkeys([*dataframe.columns, *_REPORT_COLUMNS]))).copy()
    if "etniaId" in values and "pueblonacionalidadId" in values:
        known_non_indigenous = values["etniaId"].map(lambda value: _cell_code(value) in {str(code) for code in range(2, 10)})
        values.loc[known_non_indigenous, "pueblonacionalidadId"] = 34
    _set_model_values_for_codes(values, "discapacidad", {"2"}, {
        "porcentajeDiscapacidad": "NA", "numCarnetConadis": "NA", "tipoDiscapacidad": 7,
    })
    _set_model_values_for_codes(values, "estudianteocupacionId", {"1"}, {"ingresosestudianteId": 4})
    _set_model_values_for_codes(values, "haRealizadoPracticasPreprofesionales", {"2"}, {
        "nroHorasPracticasPreprofesionalesPorPeriodo": "NA",
        "entornoInstitucionalPracticasProfesionales": 5,
        "sectorEconomicoPracticaProfesional": 22,
    })
    _set_model_values_for_codes(values, "tipoBecaId", {"3"}, {
        "primeraRazonBecaId": 2, "segundaRazonBecaId": 2, "terceraRazonBecaId": 2,
        "cuartaRazonBecaId": 2, "quintaRazonBecaId": 2, "sextaRazonBecaId": 2,
        "montoBeca": "NA", "porcientoBecaCoberturaArancel": "NA",
        "porcientoBecaCoberturaManuntencion": "NA", "financiamientoBeca": 4,
    })
    _set_model_values_for_codes(values, "participaEnProyectoVinculacionSociedad", {"2", "3"}, {
        "tipoAlcanceProyectoVinculacionId": 5,
    })
    for column in ("montoAyudaEconomica", "montoCreditoEducativo", "ingresoTotalHogar"):
        if column in values:
            zero = values[column].map(lambda value: _cell_code(value) in {"0", "0.0"})
            values[column] = values[column].astype(object)
            values.loc[zero, column] = "NA"
    for country, columns in (("paisNacionalidadId", ("provinciaNacimientoId", "cantonNacimientoId")),
                             ("paisResidenciaId", ("provinciaResidenciaId", "cantonResidenciaId"))):
        if country in values:
            foreign = values[country].map(lambda value: bool(re.fullmatch(r"\d+", _cell_code(value)))
                                          and _cell_code(value) != "56")
            for column in columns:
                if column in values:
                    values[column] = values[column].astype(object)
                    values.loc[foreign, column] = "NA"
    return values


def _apply_teacher_model_context(dataframe: pd.DataFrame) -> pd.DataFrame:
    values = dataframe.reindex(columns=list(dict.fromkeys([*dataframe.columns, *_TEACHER_REPORT_COLUMNS]))).copy()
    if "fechaSalidaIES" in values:
        missing_exit = values["fechaSalidaIES"].map(lambda value: not _cell_text(value))
        values["fechaSalidaIES"] = values["fechaSalidaIES"].astype(object)
        values.loc[missing_exit, "fechaSalidaIES"] = "NA"
    if "etniaId" in values and "pueblonacionalidadId" in values:
        known_non_indigenous = values["etniaId"].map(lambda value: _cell_code(value) in {str(code) for code in range(2, 10)})
        values["pueblonacionalidadId"] = values["pueblonacionalidadId"].astype(object)
        values.loc[known_non_indigenous, "pueblonacionalidadId"] = "NA"
    _set_model_values_for_codes(values, "discapacidad", {"2"}, {
        "porcentajeDiscapacidad": "NA", "numCarnetDiscapacidad": "NA", "tipoDiscapacidad": 7,
    })
    _set_model_values_for_codes(values, "estaEnPeriodoSabatico", {"2"}, {"fechaInicioPeriodoSabatico": "NA"})
    _set_model_values_for_codes(values, "estaCursandoEstudiosId", {"8"}, {
        "institucionDondeCursaEstudios": "NA", "paisEstudiosId": "NA", "tituloAObtener": "NA",
    })
    _set_model_values_for_codes(values, "poseeBecaId", {"2"}, {
        "tipoBecaId": 3, "montoBeca": "NA", "financiamientoBecaId": 5,
    })
    _set_model_values_for_codes(values, "pubRevistasCienInIndexadasId", {"2"}, {
        "numPubRevistasCientifIndexadas": "NA",
    })
    return values


def _student_model_workbook(dataframe: pd.DataFrame) -> bytes:
    values = _apply_student_model_context(_dedupe_model_rows(dataframe, "fechaMatricula"))
    values = values.rename(columns=_STUDENT_MODEL_ALIASES)
    for column, width in (("provinciaNacimientoId", 2), ("cantonNacimientoId", 4),
                          ("provinciaResidenciaId", 2), ("cantonResidenciaId", 4)):
        if column in values:
            values[column] = values[column].map(lambda value: _model_geographic_code(value, width))
    return _model_workbook(values, _STUDENT_MODEL_COLUMNS,
                           text_columns=("numeroIdentificacion", "numeroCelular", "provinciaNacimientoId",
                                         "cantonNacimientoId", "provinciaResidenciaId", "cantonResidenciaId",
                                         "numCarnetConadis"))


def _audit_export_zip(report: dict[str, Any], mode: str) -> bytes:
    dataframe: pd.DataFrame = report["dataframe"]
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        if dataframe.empty or "nombreCarrera" not in dataframe.columns:
            archive.writestr(
                f"senescyt_{report['target']}_{mode}.xlsx",
                (_student_model_workbook(dataframe) if report["target"] == "estudiantes" and mode == "completo"
                 else _teacher_model_workbook(report) if report["target"] == "docentes" and mode == "completo"
                 else _audit_export_workbook(report, mode)),
            )
        else:
            career_series = (
                dataframe["nombreCarrera"]
                .fillna("Sin carrera")
                .astype(str)
                .str.strip()
                .replace({"": "Sin carrera"})
            )
            career_names = sorted(career_series.unique(), key=lambda value: str(value).casefold())
            for index, career_name in enumerate(career_names, start=1):
                group = dataframe[career_series == career_name].copy()
                career_report = _build_senescyt_audit_from_dataframe(
                    report["target"],
                    group,
                    report["report_columns"],
                    [str(career_name)],
                )
                filename = f"{index:02d}_{_safe_filename(str(career_name))}_{mode}.xlsx"
                archive.writestr(filename,
                    _student_model_workbook(group) if report["target"] == "estudiantes" and mode == "completo"
                    else _teacher_model_workbook(career_report) if report["target"] == "docentes" and mode == "completo"
                    else _audit_export_workbook(career_report, mode))
    output.seek(0)
    return output.getvalue()


@router.get("/catalogo")
def senescyt_catalog(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        careers = _career_catalog()
        periods = _period_catalog()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error cargando catálogo SENESCYT: {exc}") from exc
    return {
        "careers": careers,
        "periods": periods,
        "targets": sorted(_REPORT_TARGETS),
        "export_modes": sorted(_EXPORT_MODES),
    }


@router.get("/datos")
def senescyt_audit_report(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
    target: Annotated[str, Query(pattern="^(estudiantes|docentes)$")] = "estudiantes",
    carrera: Annotated[list[str] | None, Query()] = None,
    periodo: Annotated[list[Annotated[int, Field(ge=1, le=2147483647)]] | None, Query()] = None,
    fecha_limite: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    del current_user
    try:
        report = _build_senescyt_audit(target, carrera, periodo, fecha_limite)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando auditoria SENESCYT: {exc}") from exc

    return {
        "generated_at": report["generated_at"],
        "target": report["target"],
        "career_filter": report["career_filter"],
        "period_filter": report["period_filter"],
        "cutoff_date": report["cutoff_date"],
        "active_only": True,
        "summary": report["summary"],
        "careers": report["careers"],
        "rows": report["rows"],
        "missing_fields": report["missing_fields"],
        "report_columns": report["report_columns"],
    }


@router.get("/datos/export")
def senescyt_audit_export(
    current_user: Annotated[SessionUser, Depends(_SENESCYT_ACCESS)],
    target: Annotated[str, Query(pattern="^(estudiantes|docentes)$")] = "estudiantes",
    mode: Annotated[str, Query(pattern="^(completo|faltantes)$")] = "completo",
    carrera: Annotated[list[str] | None, Query()] = None,
    periodo: Annotated[list[Annotated[int, Field(ge=1, le=2147483647)]] | None, Query()] = None,
    fecha_limite: Annotated[date | None, Query()] = None,
) -> StreamingResponse:
    del current_user
    try:
        report = _build_senescyt_audit(target, carrera, periodo, fecha_limite)
        content = _audit_export_zip(report, mode)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error exportando reporte SENESCYT: {exc}") from exc

    selected_careers = _normalize_career_filters(carrera)
    suffix = _safe_filename("_".join(selected_careers[:3])) if selected_careers else "todas_las_carreras"
    if len(selected_careers) > 3:
        suffix = f"{suffix}_y_{len(selected_careers) - 3}_mas"
    filename = f"senescyt_{target}_{mode}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
