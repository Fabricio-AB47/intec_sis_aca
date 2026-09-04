import calendar
from datetime import date, datetime
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, Literal
import unicodedata
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
import pyodbc
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.core.security import SessionUser, require_roles
from app.core.file_security import read_secure_upload
from app.services.complement_sync import sync_preinscription_complements
from app.services.db import get_connection, get_finance_connection
from app.services.graph_documents import (
    complete_upload_session,
    delete_item,
    ensure_folder,
    mark_upload_error,
    prepare_expedient,
    register_upload_session,
    set_document_origin,
    upload_bytes,
)

router = APIRouter(prefix="/api/students/preinscripcion", tags=["preinscripcion"])

_PREINSCRIPTION_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "ADMISIONES", "BIENESTAR", "RECTOR")
_SCHOLARSHIP_APPROVAL_ACCESS = require_roles("ADMINISTRADOR", "BIENESTAR")
_SCHOLARSHIP_APPROVAL_THRESHOLD = 15.0
_ACADEMIC_SEMESTER_COST = 750.0
_STANDARD_ENROLLMENT_COST = 75.0
_GASTRONOMY_ENROLLMENT_COST = 100.0
_SUBJECTS_PER_SEMESTER = 6
_DOCUMENT_FILTERS = {"ALL", "PENDIENTES", "COMPLETOS", "CON_CABECERA", "SIN_CABECERA"}
_DOCUMENT_FIELDS = {"urlcedula", "urltitulo", "urldeposito", "urlconvenio"}
_PHOTO_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_PHOTO_MAX_BYTES = 8 * 1024 * 1024
_SCHOLARSHIP_CONTRACT_MAX_BYTES = 20 * 1024 * 1024
_PREINSCRIPTION_DOCUMENT_MAX_BYTES = 25 * 1024 * 1024
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"
_SCHOLARSHIP_CONTRACT_BACKGROUND_PATH = (
    _BACKEND_ROOT / "app" / "assets" / "scholarship_contract_background.png"
)
_SCHOLARSHIP_CONTRACT_TABLE_HEADER_COLOR = colors.HexColor("#B64D5B")
_SCHOLARSHIP_CONTRACT_TABLE_LABEL_COLOR = colors.HexColor("#EDDBDA")
_SCHOLARSHIP_CONTRACT_TABLE_INNER_HEADER_COLOR = colors.HexColor("#F1F1F7")
_SCHOLARSHIP_CONTRACT_TABLE_VALUE_COLOR = colors.HexColor("#FFFFFF")
_SCHOLARSHIP_CONTRACT_TABLE_BORDER_COLOR = colors.HexColor("#4A4A4A")
UPLOAD_ROOT = _BACKEND_ROOT / "uploads"
_PREINSCRIPTION_UPLOAD_ROOT = UPLOAD_ROOT / "preinscripcion"


class PreinscriptionDocumentsPayload(BaseModel):
    urlcedula: str | None = ""
    urltitulo: str | None = ""
    urldeposito: str | None = ""
    urlconvenio: str | None = ""


class PreinscriptionPhotoReviewPayload(BaseModel):
    observacion: str | None = ""


class PreinscriptionCabeceraPayload(BaseModel):
    fecha_pago: str | None = None
    valor: float = 0
    inscrip_valor: float = 0
    matri_valor: float = 0
    costo_semestre: float = 0
    semestres_convenio: str | int | None = "1"
    control_matricula: int = 1
    num_cuotas: int = 1
    tipo_beca: str | None = ""
    porcentaje_beca: float = 0
    descuento: float = 0
    num_pago: int = 1
    detalle_pago: str | None = "Convenio de pago"
    no_deposito: str | None = ""
    banco: str | None = ""


class PreinscriptionFollowupPayload(BaseModel):
    contacte: str | None = ""
    hora: str | None = ""
    observacion_contacto: str | None = ""
    observacion_ingreso: str | None = ""
    cod_lecontacto: str | int | None = ""
    cod_desea_ingresar: str | int | None = ""
    cod_como_conoce: str | int | None = ""
    coddescconve: str | int | None = ""
    coddescconvevalor: str | int | None = ""
    coddescdeptransf: str | int | None = ""
    nom_representante: str | None = ""
    num_representante: str | None = ""
    prematricula: bool = False
    proceso_finalizado: bool = False
    control_ingreso: bool = False
    correo_enviado: bool = False
    asignado: bool = False


class PreinscriptionCreatePayload(BaseModel):
    apellidos_nombre: str | None = ""
    nombres: str | None = ""
    apellidos: str | None = ""
    cedula: str
    codprov: str
    codperiodo: str | None = None
    codcarrera: str | None = None
    correo: str | None = ""
    telefono: str | None = ""
    codmodalida: int = 1
    codjornada: int = 0
    tipo_beca: str | None = ""
    porcentaje_beca: float = 0
    valor_beca: float = 0
    motivo_beca: str | None = ""
    semestres_convenio: str | int | None = "1"


class ScholarshipConfigurationPayload(BaseModel):
    codigo: str | None = ""
    nombre: str
    es_variable: bool = False
    porcentaje: float | None = 0
    porcentaje_minimo: float | None = 0
    porcentaje_maximo: float | None = 100
    activo: bool = True


class ScholarshipContractProjectionPayload(BaseModel):
    rubro: str = Field(default="", max_length=200)
    periodicidad: str = Field(default="", max_length=300)


def _default_tax_incentive_projection() -> list[ScholarshipContractProjectionPayload]:
    return [
        ScholarshipContractProjectionPayload(
            rubro="Matrícula y arancel",
            periodicidad="{PORCENTAJE_BECA} del arancel académico durante {PERIODO}",
        ),
        ScholarshipContractProjectionPayload(
            rubro="Ayuda económica",
            periodicidad="{VALOR_BECA} durante {PERIODO}",
        ),
    ]


class ScholarshipContractClausePayload(BaseModel):
    titulo: str = Field(default="", max_length=250)
    contenido: str = Field(default="", max_length=6000)


class ScholarshipContractTableLabelsPayload(BaseModel):
    numero_contrato: str = Field(default="No.", max_length=40)
    identificacion_firma: str = Field(default="C.C.:", max_length=80)
    becario: str = Field(default="Apellidos y nombres del/la becario/a:", max_length=200)
    numero_beca: str = Field(default="Beca No.", max_length=120)
    cedula: str = Field(default="Cédula de ciudadanía / identidad:", max_length=200)
    telefono: str = Field(default="Teléfono:", max_length=120)
    nivel_formacion: str = Field(default="Nivel de formación:", max_length=160)
    carrera_programa: str = Field(default="Carrera/programa:", max_length=160)
    tipo_beca: str = Field(default="Tipo de beca:", max_length=160)
    discapacidad: str = Field(default="Discapacidad:", max_length=160)
    porcentaje_discapacidad: str = Field(default="Porcentaje de discapacidad:", max_length=200)
    tipo_discapacidad: str = Field(default="Tipo de discapacidad:", max_length=180)
    beneficio: str = Field(default="Porcentaje de beca y monto otorgado:", max_length=220)
    beneficio_sufijo: str = Field(default="del valor del arancel vigente", max_length=220)
    periodo_adjudicacion: str = Field(default="Período de adjudicación:", max_length=180)
    correo_notificaciones: str = Field(default="Correo INTEC para notificaciones:", max_length=220)
    nombres: str = Field(default="Apellidos y Nombres:", max_length=160)
    documento_identidad: str = Field(default="Documento de identidad:", max_length=160)
    prefijo_documento_identidad: str = Field(default="CÉDULA -", max_length=80)
    programa: str = Field(default="Programa:", max_length=120)
    pais: str = Field(default="País:", max_length=120)
    fecha_fin_financiamiento: str = Field(default="Fecha final financiamiento:", max_length=200)
    institucion_educacion: str = Field(default="Institución de Educación:", max_length=200)
    duracion_financiamiento: str = Field(default="Duración financiamiento:", max_length=180)
    auspiciante: str = Field(default="Auspiciante:", max_length=120)
    fecha_inicio_estudios: str = Field(default="Fecha inicio estudios:", max_length=180)
    carrera: str = Field(default="Carrera:", max_length=120)
    fecha_fin_estudios: str = Field(default="Fecha finalización estudios:", max_length=200)
    nivel_estudios: str = Field(default="Nivel de estudios:", max_length=160)
    duracion_estudios: str = Field(default="Duración de estudios:", max_length=180)
    fecha_inicio_financiamiento: str = Field(default="Fecha inicial financiamiento:", max_length=200)
    periodo_pago: str = Field(default="Período de pago:", max_length=160)
    numero: str = Field(default="Nº", max_length=40)
    rubro: str = Field(default="Rubro", max_length=120)
    periodicidad_rubro: str = Field(default="Periodicidad del rubro", max_length=180)


class ScholarshipContractTemplatePayload(BaseModel):
    titulo_contrato: str = Field(default="CONTRATO DE BECA", max_length=120)
    texto_completo: str | None = Field(default=None, max_length=60000)
    fecha_contrato: str | None = Field(default=None, max_length=10)
    ciudad: str = Field(default="Quito, D.M.", max_length=120)
    resolucion: str = Field(
        default="Resolución No. 002-CR-INTEC-2024, de 19 de diciembre de 2024",
        max_length=300,
    )
    rector_tratamiento: str = Field(default="Ingeniero", max_length=80)
    rector_nombre: str = Field(default="JAIME RODER ORTEGA PEREIRA", max_length=200)
    rector_titulo: str = Field(default="MGT.", max_length=40)
    correo_notificaciones: str = Field(default="dir.bienestar@intec.edu.ec", max_length=180)
    programa: str = Field(default="", max_length=1500)
    pais: str = Field(default="Ecuador", max_length=100)
    institucion_educacion: str = Field(
        default="Instituto Superior Tecnológico de Técnicas Empresariales y del Conocimiento (INTEC)",
        max_length=300,
    )
    auspiciante: str = Field(default="INTEC", max_length=200)
    nivel_estudios: str = Field(default="Tecnólogo Superior", max_length=160)
    fecha_inicio_estudios: str | None = Field(default=None, max_length=10)
    fecha_fin_estudios: str | None = Field(default=None, max_length=10)
    fecha_inicio_financiamiento: str | None = Field(default=None, max_length=10)
    fecha_fin_financiamiento: str | None = Field(default=None, max_length=10)
    duracion_estudios: str = Field(default="Durante el período académico adjudicado", max_length=250)
    duracion_financiamiento: str = Field(default="Durante el período académico adjudicado", max_length=250)
    periodo_pago: str = Field(default="TOTAL", max_length=120)
    proyeccion: list[ScholarshipContractProjectionPayload] = Field(default_factory=list, max_length=10)
    introduccion_institucional: str | None = Field(default=None, max_length=6000)
    clausulas_institucionales: list[ScholarshipContractClausePayload] | None = Field(
        default=None,
        max_length=50,
    )
    introduccion_programa: str | None = Field(default=None, max_length=6000)
    clausulas_programa: list[ScholarshipContractClausePayload] | None = Field(
        default=None,
        max_length=50,
    )
    titulo_tabla_datos: str = Field(default="DATOS BECA", max_length=120)
    titulo_tabla_proyeccion: str = Field(default="PROYECCIÓN DE LA BECA", max_length=120)
    rotulos_tabla: ScholarshipContractTableLabelsPayload = Field(
        default_factory=ScholarshipContractTableLabelsPayload,
    )
    firma_rector_tratamiento: str = Field(default="Ing.", max_length=80)
    firma_rector_nombre: str = Field(default="JAIME RODER ORTEGA PEREIRA", max_length=200)
    firma_rector_titulo: str = Field(default="MGT.", max_length=40)
    firma_rector_etiqueta: str = Field(default="RECTOR", max_length=120)
    firma_becario_tratamiento: str = Field(default="Sr.(a)(ita):", max_length=120)
    firma_becario_etiqueta: str = Field(default="BECARIO/A", max_length=120)
    color_cabecera_tabla: str = Field(
        default="#B64D5B",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    color_celda_etiqueta: str = Field(
        default="#EDDBDA",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    color_cabecera_interior: str = Field(
        default="#F1F1F7",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    color_celda_valor: str = Field(
        default="#FFFFFF",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    color_borde_tabla: str = Field(
        default="#4A4A4A",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class ScholarshipContractGeneratePayload(BaseModel):
    beca_ids: list[int]
    codigo_periodo: str
    formato_contrato: Literal["BECA", "INCENTIVOS_TRIBUTARIOS"] = "BECA"
    plantilla: ScholarshipContractTemplatePayload = Field(default_factory=ScholarshipContractTemplatePayload)

    @field_validator("formato_contrato", mode="before")
    @classmethod
    def normalize_contract_format(cls, value: Any) -> str:
        return _canonical_scholarship_contract_format(value)


class ScholarshipContractPreviewPayload(BaseModel):
    beca_id: int | None = None
    codigo_periodo: str = Field(default="", max_length=50)
    tipo_beca: str = Field(default="", max_length=150)
    periodo: str = Field(default="", max_length=220)
    formato_contrato: Literal["BECA", "INCENTIVOS_TRIBUTARIOS"] = "BECA"
    plantilla: ScholarshipContractTemplatePayload = Field(default_factory=ScholarshipContractTemplatePayload)

    @field_validator("formato_contrato", mode="before")
    @classmethod
    def normalize_contract_format(cls, value: Any) -> str:
        return _canonical_scholarship_contract_format(value)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _canonical_scholarship_contract_format(value: Any) -> Literal["BECA", "INCENTIVOS_TRIBUTARIOS"]:
    normalized = _clean(value).upper()
    if normalized in {"INCENTIVOS_TRIBUTARIOS", "PROGRAMA"}:
        return "INCENTIVOS_TRIBUTARIOS"
    return "BECA"


def _stream_scholarship_contract_archive(bundle: Any, chunk_size: int = 1024 * 1024):
    try:
        while chunk := bundle.read(chunk_size):
            yield chunk
    finally:
        bundle.close()


def _scholarship_contract_generation_selection(
    payload: ScholarshipContractGeneratePayload,
) -> tuple[list[int], str]:
    scholarship_ids = list(dict.fromkeys(int(value) for value in payload.beca_ids))
    academic_period = _clean(payload.codigo_periodo)
    if not scholarship_ids:
        raise HTTPException(status_code=400, detail="Seleccione al menos un estudiante becado")
    if not academic_period:
        raise HTTPException(status_code=400, detail="Seleccione el período académico de la beca")
    return scholarship_ids, academic_period


def _is_no_scholarship(value: Any) -> bool:
    normalized = _clean(value).upper()
    return normalized in {"", "SIN BECA", "NO APLICA", "NINGUNA", "NINGUNO"}


def _is_mintel_scholarship(value: Any) -> bool:
    return "MINTEL" in _clean(value).upper()


def _is_intec_scholarship(value: Any) -> bool:
    normalized = re.sub(r"[^A-Z0-9]+", " ", _clean(value).upper()).strip()
    return not _is_mintel_scholarship(value) and (
        normalized == "INTEC" or normalized.startswith("BECA INTEC")
    )


def _is_english_career(career_code: Any = "", career_name: Any = "") -> bool:
    normalized_code = _clean(career_code).upper()
    normalized_name = re.sub(r"[^A-Z0-9]+", " ", _clean(career_name).upper()).strip()
    return normalized_code == "12" or "INGL" in normalized_name or "IDIOMA" in normalized_name


def _exclude_english_scholarship_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if not _is_english_career(item.get("codigo_carrera"), item.get("carrera"))
    ]


def _scholarship_code(value: Any) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", _clean(value).upper()).strip("_")
    return normalized[:50] or "BECA"


def _scholarship_relation_key(value: Any) -> str:
    """Matches scholarship sources by name without duplicating spelling variants."""
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", _clean(value).upper())
        if unicodedata.category(character) != "Mn"
    )
    key = re.sub(r"[^A-Z0-9]+", "_", normalized).strip("_")
    if key.startswith("BECA_"):
        key = key[5:]
    if key == "SUSUKI":
        key = "SUZUKI"
    return key


def _combined_scholarship_seeds(
    *sources: list[tuple[str, float, float]],
) -> list[tuple[str, float, float]]:
    combined: list[tuple[str, float, float]] = []
    known_keys: set[str] = set()
    for source in sources:
        for name, minimum, maximum in source:
            relation_key = _scholarship_relation_key(name)
            if not relation_key or _is_no_scholarship(name) or relation_key in known_keys:
                continue
            combined.append((name, minimum, maximum))
            known_keys.add(relation_key)
    return combined


def _normalized_scholarship(tipo_beca: Any, porcentaje_beca: Any, valor_beca: Any = 0) -> tuple[str, float, float]:
    scholarship_type = _clean(tipo_beca)
    if _is_no_scholarship(scholarship_type):
        return "", 0.0, 0.0
    percentage = 100.0 if _is_mintel_scholarship(scholarship_type) else min(max(float(porcentaje_beca or 0), 0), 100)
    scholarship_value = max(float(valor_beca or 0), 0)
    return scholarship_type, percentage, scholarship_value


def _ensure_scholarship_configuration_table() -> None:
    legacy_rows: list[tuple[str, float, float]] = []
    agreement_discount_rows: list[tuple[str, float, float]] = []
    try:
        with get_connection() as legacy_conn:
            legacy_cursor = legacy_conn.cursor()
            legacy_cursor.execute(
                """
                IF OBJECT_ID(N'dbo.Becas', N'U') IS NOT NULL
                    SELECT LTRIM(RTRIM(tipo_beca)),
                           MIN(ISNULL(TRY_CONVERT(decimal(9,2), porcentaje_beca), 0)),
                           MAX(ISNULL(TRY_CONVERT(decimal(9,2), porcentaje_beca), 0))
                    FROM dbo.Becas
                    WHERE NULLIF(LTRIM(RTRIM(tipo_beca)), '') IS NOT NULL
                    GROUP BY LTRIM(RTRIM(tipo_beca))
                ELSE
                    SELECT TOP (0) '', CAST(0 AS decimal(9,2)), CAST(0 AS decimal(9,2))
                """
            )
            legacy_rows = [(_clean(row[0]), float(row[1] or 0), float(row[2] or 0)) for row in legacy_cursor.fetchall()]
            legacy_cursor.execute(
                """
                IF OBJECT_ID(N'dbo.IN_DESCCONVE', N'U') IS NOT NULL
                    SELECT LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), DetalleDesConve))),
                           TRY_CONVERT(decimal(9,2), Porcentaje)
                    FROM dbo.IN_DESCCONVE
                    WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), DetalleDesConve))), '') IS NOT NULL
                    ORDER BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), DetalleDesConve)))
                ELSE
                    SELECT TOP (0) N'', CAST(0 AS decimal(9,2))
                """
            )
            agreement_discount_rows = [
                (_clean(row[0]), float(row[1] or 0), float(row[1] or 0))
                for row in legacy_cursor.fetchall()
            ]
    except pyodbc.Error:
        legacy_rows = []
        agreement_discount_rows = []

    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat')
                EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');

            IF OBJECT_ID(N'cat.ConfiguracionBecaPreinscripcion', N'U') IS NULL
            BEGIN
                CREATE TABLE cat.ConfiguracionBecaPreinscripcion
                (
                    ConfiguracionBecaId INT IDENTITY(1,1) NOT NULL
                        CONSTRAINT PK_ConfiguracionBecaPreinscripcion PRIMARY KEY,
                    Codigo VARCHAR(50) NOT NULL,
                    Nombre NVARCHAR(150) NOT NULL,
                    EsVariable BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_EsVariable DEFAULT 0,
                    PorcentajeFijo DECIMAL(9,2) NULL,
                    PorcentajeMinimo DECIMAL(9,2) NULL,
                    PorcentajeMaximo DECIMAL(9,2) NULL,
                    Protegida BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_Protegida DEFAULT 0,
                    Activo BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_Activo DEFAULT 1,
                    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_ConfiguracionBeca_Fecha DEFAULT SYSDATETIME(),
                    UsuarioCreacion NVARCHAR(128) NULL,
                    FechaActualizacion DATETIME2 NULL,
                    UsuarioActualizacion NVARCHAR(128) NULL,
                    CONSTRAINT UQ_ConfiguracionBeca_Codigo UNIQUE(Codigo),
                    CONSTRAINT CK_ConfiguracionBeca_Porcentajes CHECK
                    (
                        (PorcentajeFijo IS NULL OR PorcentajeFijo BETWEEN 0 AND 100)
                        AND (PorcentajeMinimo IS NULL OR PorcentajeMinimo BETWEEN 0 AND 100)
                        AND (PorcentajeMaximo IS NULL OR PorcentajeMaximo BETWEEN 0 AND 100)
                    )
                );
            END
            """
        )
        cursor.execute("SELECT COUNT(1) FROM cat.ConfiguracionBecaPreinscripcion")
        is_empty = int(cursor.fetchone()[0] or 0) == 0
        seeds = _combined_scholarship_seeds(legacy_rows, agreement_discount_rows)
        migration_user = "MIGRACION_INICIAL" if is_empty else "SINCRONIZACION_HISTORICA"
        if is_empty and not seeds:
            seeds = [
                ("Beca Intec", 0.0, 100.0),
                ("Beca Futuro Femenino", 100.0, 100.0),
                ("Beca Mintel", 100.0, 100.0),
                ("Suzuki", 100.0, 100.0),
            ]
        cursor.execute("SELECT Nombre FROM cat.ConfiguracionBecaPreinscripcion")
        configured_relation_keys = {
            _scholarship_relation_key(row[0])
            for row in cursor.fetchall()
            if _scholarship_relation_key(row[0])
        }
        for name, minimum, maximum in seeds:
            relation_key = _scholarship_relation_key(name)
            if relation_key in configured_relation_keys:
                continue
            is_mintel = _is_mintel_scholarship(name)
            is_variable = not is_mintel and abs(maximum - minimum) > 0.001
            fixed_percentage = 100.0 if is_mintel else (None if is_variable else maximum)
            cursor.execute(
                """
                MERGE cat.ConfiguracionBecaPreinscripcion WITH (HOLDLOCK) AS target
                USING
                (
                    SELECT
                        ? AS Codigo, ? AS Nombre, ? AS EsVariable, ? AS PorcentajeFijo,
                        ? AS PorcentajeMinimo, ? AS PorcentajeMaximo, ? AS Protegida,
                        ? AS UsuarioCreacion
                ) AS source
                   ON target.Codigo = source.Codigo
                WHEN NOT MATCHED THEN
                    INSERT
                    (
                        Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo,
                        PorcentajeMaximo, Protegida, Activo, UsuarioCreacion
                    )
                    VALUES
                    (
                        source.Codigo, source.Nombre, source.EsVariable, source.PorcentajeFijo,
                        source.PorcentajeMinimo, source.PorcentajeMaximo, source.Protegida, 1,
                        source.UsuarioCreacion
                    );
                """,
                _scholarship_code(name),
                name,
                int(is_variable),
                fixed_percentage,
                100.0 if is_mintel else minimum,
                100.0 if is_mintel else maximum,
                int(is_mintel),
                migration_user,
            )
            configured_relation_keys.add(relation_key)
        cursor.execute(
            """
            UPDATE cat.ConfiguracionBecaPreinscripcion
               SET EsVariable = 0, PorcentajeFijo = 100, PorcentajeMinimo = 100,
                   PorcentajeMaximo = 100, Protegida = 1, Activo = 1,
                   FechaActualizacion = SYSDATETIME(), UsuarioActualizacion = N'SISTEMA'
             WHERE (UPPER(Codigo) = 'BECA_MINTEL' OR UPPER(Nombre) LIKE '%MINTEL%')
               AND
               (
                   EsVariable <> 0 OR ISNULL(PorcentajeFijo, -1) <> 100
                   OR ISNULL(PorcentajeMinimo, -1) <> 100
                   OR ISNULL(PorcentajeMaximo, -1) <> 100
                   OR Protegida <> 1 OR Activo <> 1
               );

            IF NOT EXISTS
            (
                SELECT 1 FROM cat.ConfiguracionBecaPreinscripcion
                WHERE UPPER(Codigo) = 'BECA_MINTEL' OR UPPER(Nombre) LIKE '%MINTEL%'
            )
                INSERT INTO cat.ConfiguracionBecaPreinscripcion
                    (Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo,
                     PorcentajeMaximo, Protegida, Activo, UsuarioCreacion)
                VALUES ('BECA_MINTEL', N'Beca Mintel', 0, 100, 100, 100, 1, 1, N'SISTEMA');

            UPDATE cat.ConfiguracionBecaPreinscripcion
               SET EsVariable = 1, PorcentajeFijo = NULL, PorcentajeMinimo = 0,
                   PorcentajeMaximo = 100, FechaActualizacion = SYSDATETIME(),
                   UsuarioActualizacion = N'MIGRACION_INICIAL'
             WHERE Codigo = 'BECA_INTEC'
               AND UsuarioCreacion = N'MIGRACION_INICIAL'
               AND EsVariable = 0;
            """
        )
        conn.commit()


def _scholarship_configurations(active_only: bool = False) -> list[dict[str, Any]]:
    _ensure_scholarship_configuration_table()
    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ConfiguracionBecaId, Codigo, Nombre, EsVariable, PorcentajeFijo,
                   PorcentajeMinimo, PorcentajeMaximo, Protegida, Activo,
                   FechaActualizacion, UsuarioActualizacion
            FROM cat.ConfiguracionBecaPreinscripcion
            WHERE (? = 0 OR Activo = 1)
            ORDER BY Activo DESC, Nombre
            """,
            int(active_only),
        )
        rows = cursor.fetchall()
    return [
        {
            "id": int(row.ConfiguracionBecaId),
            "codigo": _clean(row.Codigo),
            "nombre": _clean(row.Nombre),
            "es_variable": bool(row.EsVariable),
            "porcentaje": None if row.PorcentajeFijo is None else float(row.PorcentajeFijo),
            "porcentaje_minimo": None if row.PorcentajeMinimo is None else float(row.PorcentajeMinimo),
            "porcentaje_maximo": None if row.PorcentajeMaximo is None else float(row.PorcentajeMaximo),
            "protegida": bool(row.Protegida),
            "activo": bool(row.Activo),
            "fecha_actualizacion": _date_text(row.FechaActualizacion),
            "usuario_actualizacion": _clean(row.UsuarioActualizacion),
        }
        for row in rows
    ]


def _validate_scholarship_selection(tipo_beca: Any, porcentaje_beca: Any) -> tuple[str, float]:
    scholarship_type, percentage, _ = _normalized_scholarship(tipo_beca, porcentaje_beca)
    if not scholarship_type:
        return "", 0.0

    configurations = _scholarship_configurations(active_only=True)
    selected_code = _scholarship_code(scholarship_type)
    selected = next(
        (
            item
            for item in configurations
            if item["codigo"].upper() == selected_code or item["nombre"].upper() == scholarship_type.upper()
        ),
        None,
    )
    if not selected:
        raise HTTPException(status_code=400, detail="La beca seleccionada no está disponible en inscripción")

    if selected["es_variable"]:
        minimum = float(selected["porcentaje_minimo"] or 0)
        maximum = float(selected["porcentaje_maximo"] if selected["porcentaje_maximo"] is not None else 100)
        if percentage < minimum or percentage > maximum:
            raise HTTPException(
                status_code=400,
                detail=f"El porcentaje de {selected['nombre']} debe estar entre {minimum:g}% y {maximum:g}%",
            )
    else:
        percentage = float(selected["porcentaje"] or 0)
    return selected["nombre"], percentage


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _clean(value)


def _number_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_int_payload(value: Any, fallback: int | None = None) -> int | None:
    text = _clean(value)
    if not text:
        return fallback
    return _int_value(text)


def _bool_from_db(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _clean(value).upper()
    return normalized in {"1", "A", "ACTIVO", "ACTIVA", "TRUE", "SI", "S", "Y", "YES"}


def _document_url(value: Any) -> str:
    text = _clean(value)
    return text if text and text.upper() not in {"NULL", "NONE", "N/A"} else ""


def _safe_filename(value: str) -> str:
    name = Path(value or "documento").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "documento"


def _convenio_semester_count(value: str | int | None) -> int:
    text = _clean(value).upper()
    if text in {"TODOS", "TODO", "ALL"}:
        return 4
    try:
        return min(max(int(float(text or "1")), 1), 4)
    except ValueError:
        return 1


def _institutional_study_costs(
    semesters: str | int | None,
    career_name: str = "",
) -> dict[str, float | int]:
    semester_count = _convenio_semester_count(semesters)
    is_gastronomy = "GASTRONOM" in _clean(career_name).upper()
    enrollment_cost = _GASTRONOMY_ENROLLMENT_COST if is_gastronomy else _STANDARD_ENROLLMENT_COST
    base_semester_cost = _ACADEMIC_SEMESTER_COST + enrollment_cost
    academic_total = round(_ACADEMIC_SEMESTER_COST * semester_count, 2)
    enrollment_total = round(enrollment_cost * semester_count, 2)
    total = round(academic_total + enrollment_total, 2)
    return {
        "total": total,
        "costo_semestre": round(base_semester_cost, 2),
        "valor_academico": academic_total,
        "valor_matricula": enrollment_total,
        "materias": _SUBJECTS_PER_SEMESTER * semester_count,
        "semestres": semester_count,
    }


def _payment_plan(
    payload: PreinscriptionCabeceraPayload,
    career_name: str = "",
) -> dict[str, float | int | str]:
    costs = _institutional_study_costs(payload.semestres_convenio, career_name)
    semester_count = int(costs["semestres"])
    total = float(costs["total"])
    _, porcentaje_beca, _ = _normalized_scholarship(payload.tipo_beca, payload.porcentaje_beca)
    scholarship_base = float(costs["valor_academico"]) if _is_intec_scholarship(payload.tipo_beca) else total
    beca_valor = round(scholarship_base * porcentaje_beca / 100, 2)
    descuento = max(float(payload.descuento or 0), 0)
    saldo = max(total - beca_valor - descuento, 0)
    num_cuotas = max(int(payload.num_cuotas or 1), 1)
    cuota_valor = round(saldo / num_cuotas, 2) if num_cuotas else saldo
    return {
        "total": round(total, 2),
        "costo_semestre": costs["costo_semestre"],
        "valor_academico": costs["valor_academico"],
        "valor_matricula": costs["valor_matricula"],
        "materias": costs["materias"],
        "semestres": semester_count,
        "alcance": "Todos los semestres" if _clean(payload.semestres_convenio).upper() in {"TODOS", "TODO", "ALL"} else f"{semester_count} semestre(s)",
        "porcentaje_beca": round(porcentaje_beca, 2),
        "beca_valor": beca_valor,
        "beca_aplica_solo_arancel": _is_intec_scholarship(payload.tipo_beca),
        "descuento": round(descuento, 2),
        "saldo": round(saldo, 2),
        "num_cuotas": num_cuotas,
        "cuota_valor": cuota_valor,
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
            self.canv.setFont("Helvetica-Bold", 28)
            self.canv.setFillColor(colors.HexColor("#808285"))
            self.canv.drawString(0, 0.35 * cm, "intec")
            return
        self.canv.saveState()
        self.canv.scale(self.scale, self.scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()


def _format_money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _scholarship_contract_scope(item: dict[str, Any]) -> str:
    scholarship_name = _clean(item.get("tipo_beca"))
    percentage = float(item.get("porcentaje_beca") or 0)
    if _is_intec_scholarship(scholarship_name):
        return (
            f"La beca cubre el {percentage:g}% del arancel académico correspondiente. "
            "Este beneficio no se aplica al valor de matrícula ni a otros rubros administrativos."
        )
    if _is_mintel_scholarship(scholarship_name):
        return (
            "La Beca MINTEL conserva el porcentaje institucional fijo registrado para el período "
            "académico y se aplicará conforme a la cuenta estudiantil aprobada."
        )
    return (
        f"La beca cubre el {percentage:g}% conforme a la aprobación registrada para el período "
        "académico y a los rubros autorizados por la institución."
    )


def _scholarship_contract_initial(value: Any) -> str:
    words = re.findall(r"[A-Z0-9]+", _clean(value).upper())
    ignored = {"BECA", "AYUDA", "ECONOMICA", "ECONÓMICA", "DE", "DEL", "LA", "EL"}
    significant = next((word for word in words if word not in ignored), "BECA")
    return significant[0]


def _scholarship_contract_base_number(item: dict[str, Any], contract_date: date) -> str:
    initial = _scholarship_contract_initial(item.get("tipo_beca"))
    scholarship_id = abs(int(item.get("beca_id") or 0))
    period_digits = re.sub(r"\D+", "", _clean(item.get("codigo_periodo")))
    period_part = (period_digits[-4:] if period_digits else "0000").zfill(4)
    return f"{initial}{scholarship_id:04d}{period_part}{contract_date.year}"


def _scholarship_contract_preview_item(
    payload: ScholarshipContractPreviewPayload,
) -> dict[str, Any]:
    contract_format = _canonical_scholarship_contract_format(payload.formato_contrato)
    scholarship_type = _clean(payload.tipo_beca) or (
        "INCENTIVOS TRIBUTARIOS"
        if contract_format == "INCENTIVOS_TRIBUTARIOS"
        else "BECA INSTITUCIONAL"
    )
    academic_period = _clean(payload.codigo_periodo) or "PERIODO-VISTA-PREVIA"
    return {
        "beca_id": 0,
        "codigo_estud": "VISTA-PREVIA",
        "cedula": "0000000000",
        "estudiante": "ESTUDIANTE DE VISTA PREVIA",
        "codigo_carrera": "",
        "carrera": "CARRERA DE VISTA PREVIA",
        "codigo_periodo": academic_period,
        "periodo": _clean(payload.periodo) or academic_period,
        "tipo_beca": scholarship_type,
        "porcentaje_beca": 100,
        "valor_beca": _ACADEMIC_SEMESTER_COST,
        "telefono": "0000000000",
        "nivel_formacion": "TERCER NIVEL - TECNÓLOGO SUPERIOR",
        "discapacidad": "NO",
        "porcentaje_discapacidad": "0",
        "tipo_discapacidad": "NINGUNA",
    }


def _next_scholarship_contract_number(
    cursor: pyodbc.Cursor,
    item: dict[str, Any],
    contract_date: date,
) -> str:
    base_number = _scholarship_contract_base_number(item, contract_date)
    origin = "INTECBDD" if int(item["beca_id"]) < 0 else "FINANZAS"
    cursor.execute(
        """
        SELECT COUNT(1)
        FROM bec.ContratoBeca
        WHERE BecaOrigenId = ? AND Origen = ? AND CodigoPeriodo = ?
        """,
        int(item["beca_id"]),
        origin,
        _clean(item.get("codigo_periodo")),
    )
    generated = int(cursor.fetchone()[0] or 0)
    return base_number if generated == 0 else f"{base_number}-R{generated + 1}"


def _scholarship_disability(value: Any) -> str:
    normalized = _clean(value).upper()
    if normalized in {"1", "SI", "SÍ", "TRUE"}:
        return "SÍ"
    return "NO"


def _scholarship_disability_type(item: dict[str, Any]) -> str:
    if _scholarship_disability(item.get("discapacidad")) == "NO":
        return "NINGUNA"
    value = _clean(item.get("tipo_discapacidad"))
    return "NINGUNA" if value in {"", "0", "7"} else value


def _scholarship_disability_percentage(item: dict[str, Any]) -> str:
    if _scholarship_disability(item.get("discapacidad")) == "NO":
        return "0 %"
    value = _clean(item.get("porcentaje_discapacidad"))
    if not value or value.upper() in {"NA", "N/A", "NO APLICA"}:
        return "NO REGISTRADO"
    normalized = value.rstrip("% ").replace(",", ".")
    try:
        return f"{float(normalized):g} %"
    except ValueError:
        return value.upper()


def _scholarship_education_level(value: Any) -> str:
    level = _clean(value).upper()
    if not level or level.isdigit():
        return "TERCER NIVEL - TECNÓLOGO SUPERIOR"
    if "TERCER NIVEL" in level or "TECNÓLOG" in level:
        return level
    return level


def _scholarship_period_label(value: Any) -> str:
    period = _clean(value).upper()
    if not period:
        return "NO REGISTRADO"
    months = (
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    )
    found = [(match.start(), month) for month in months for match in re.finditer(month, period)]
    found.sort()
    years = re.findall(r"\b(?:19|20)\d{2}\b", period)
    if len(found) >= 2 and years:
        first_month, last_month = found[0][1], found[-1][1]
        if len(set(years)) == 1:
            return f"{first_month}-{last_month} {years[-1]}"
        return f"{first_month} {years[0]}-{last_month} {years[-1]}"
    return period


def _scholarship_contract_template_text(
    template: dict[str, Any],
    field_name: str,
    default: str,
) -> str:
    if field_name in template:
        return _clean(template.get(field_name))
    return default


def _scholarship_contract_template_multiline(
    template: dict[str, Any],
    field_name: str,
    default: str,
) -> str:
    if field_name not in template or template.get(field_name) is None:
        return default
    return str(template.get(field_name) or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _scholarship_contract_table_label(
    template: dict[str, Any],
    field_name: str,
    default: str,
) -> str:
    raw_labels = template.get("rotulos_tabla")
    if isinstance(raw_labels, BaseModel):
        raw_labels = raw_labels.model_dump()
    if not isinstance(raw_labels, dict) or field_name not in raw_labels:
        return default
    return _clean(raw_labels.get(field_name))


def _scholarship_contract_color(
    template: dict[str, Any],
    field_name: str,
    default: colors.Color,
) -> colors.Color:
    value = _clean(template.get(field_name))
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return default
    try:
        return colors.HexColor(value)
    except (TypeError, ValueError):
        return default


def _institutional_scholarship_contract_intro() -> str:
    return (
        "En la ciudad de {CIUDAD}, a los {FECHA_CONTRATO}, comparecen el {RECTOR}, en su calidad de "
        "Rector del Instituto Superior Tecnológico de Técnicas Empresariales y del Conocimiento "
        "(INTEC), de conformidad con la {RESOLUCION}; y el/la señor(a)(ita) {ESTUDIANTE}, con cédula "
        "de ciudadanía No. {CEDULA}, a quien en adelante se denominará como el/la “BECARIO/A”, "
        "conforme a las cláusulas que a continuación se detallan:"
    )


def _institutional_scholarship_contract_clauses() -> list[dict[str, str]]:
    return [
        {
            "titulo": "CLÁUSULA PRIMERA.- OBJETO.-",
            "contenido": (
                "Es política del INTEC el otorgamiento de becas y ayudas económicas que aseguren el "
                "cumplimiento del artículo 356 de la Constitución de la República del Ecuador, que "
                "establece: “el cobro de aranceles en la educación superior particular contará con "
                "mecanismos tales como becas, créditos, cuotas de ingreso u otros que permitan la "
                "integración y equidad social en sus múltiples dimensiones”; el principio de igualdad "
                "de oportunidades y las demás disposiciones establecidas en la Constitución, en la "
                "Ley Orgánica de Educación Superior (LOES) y demás normativa aplicable."
            ),
        },
        {
            "titulo": "CLÁUSULA SEGUNDA.- OBJETIVO ESPECÍFICO.-",
            "contenido": (
                "El INTEC otorga la BECA de acuerdo con las especificaciones registradas en la tabla "
                "de datos de la beca."
            ),
        },
        {
            "titulo": "CLÁUSULA TERCERA.- MONTO Y RUBROS DE LA BECA.-",
            "contenido": (
                "El monto y los rubros que cubre la beca dependerán del número de asignaturas, créditos "
                "u horas matriculadas por el/la estudiante en cada período académico y constarán en el "
                "estado académico del/la estudiante. {ALCANCE_BECA}"
            ),
        },
        {
            "titulo": "CLÁUSULA TERCERA.- DURACIÓN.-",
            "contenido": (
                "La beca se otorgará por los períodos académicos ordinarios de duración oficial de la "
                "carrera. La renovación de la beca estará sujeta a su aprobación por parte de la "
                "Dirección de Bienestar del INTEC en cada período académico ordinario, se efectuará en "
                "los mismos términos y condiciones previstos en este contrato y no requerirá la "
                "suscripción de uno nuevo. En caso de cambio de carrera, modalidad, tipo de beca, fuente "
                "de financiamiento, porcentaje otorgado o rubro que cubre la beca, se procederá a la "
                "suscripción de un nuevo contrato, que incluirá dichas modificaciones y dejará sin efecto "
                "el último contrato suscrito por el/la becario/a."
            ),
        },
        {
            "titulo": "CLÁUSULA CUARTA.- OBLIGACIONES DEL/LA BECARIO/A.-",
            "contenido": (
                "El/la becario/a se obliga a cumplir con las siguientes obligaciones y compromisos:\n"
                "a) Para renovar la beca, deberá mantener en cada período académico un promedio de "
                "7/10 sin aproximaciones.\n"
                "b) Cumplir las normas disciplinarias y de convivencia del INTEC.\n"
                "c) No abandonar su formación académica para evitar sanciones económicas."
            ),
        },
        {
            "titulo": "CLÁUSULA QUINTA.- CAMBIO DE CARRERA.-",
            "contenido": (
                "El/la becario/a podrá realizar el trámite de cambio de carrera según el proceso "
                "determinado en el Reglamento del Estudiante. Para mantener la beca en la nueva carrera, "
                "deberá acreditar el promedio de renovación establecido en el Reglamento de Becas y "
                "Ayudas Económicas, según el tipo de beca otorgada. Este beneficio por cambio de carrera "
                "se aplicará por una sola ocasión."
            ),
        },
        {
            "titulo": "CLÁUSULA SEXTA.- SUSPENSIÓN TEMPORAL.-",
            "contenido": (
                "El INTEC, a través de la Dirección de Bienestar, podrá suspender temporalmente la beca "
                "o ayuda económica en los siguientes casos:\n"
                "a) A petición de la parte interesada, se podrá suspender por única vez la beca o ayuda "
                "económica hasta por dos períodos académicos consecutivos, por circunstancias de caso "
                "fortuito o fuerza mayor debidamente justificadas.\n"
                "b) Cuando el/la becario/a no apruebe una asignatura, pero cumpla el promedio mínimo "
                "establecido para la renovación, deberá solicitar la suspensión temporal de la beca para "
                "el siguiente período académico. Una vez que apruebe la asignatura reprobada, se "
                "procederá, previa autorización de la Dirección de Bienestar del INTEC, a la reactivación "
                "de la beca. El/la becario/a deberá asumir el pago de dicha asignatura y esta salvedad se "
                "aplicará máximo por dos ocasiones durante la carrera."
            ),
        },
        {
            "titulo": "CLÁUSULA SÉPTIMA.- SUSPENSIÓN DEFINITIVA.-",
            "contenido": (
                "Serán causales de suspensión definitiva las siguientes:\n"
                "a) Cuando el/la becario/a o beneficiario/a de una ayuda económica no apruebe dos o más "
                "asignaturas en el período académico correspondiente;\n"
                "b) Haber sido sancionado/a por faltas disciplinarias;\n"
                "c) Por la comprobación de falsedad o alteración de los documentos o datos consignados "
                "para el otorgamiento de la beca o ayuda económica; y,\n"
                "d) Por incumplimiento de las obligaciones establecidas en el Reglamento de Becas y "
                "Ayudas Económicas y en el presente contrato.\n"
                "En estos casos, la Dirección de Bienestar notificará al/la becario/a el incumplimiento "
                "de las obligaciones y le concederá el término de tres días para que presente los "
                "argumentos que considere procedentes. Transcurrido el término señalado, la Coordinación "
                "Académica de la carrera pondrá el caso en conocimiento de la Dirección de Bienestar del "
                "INTEC para la aprobación de la suspensión definitiva y, de ser procedente, dispondrá que "
                "el/la beneficiario/a restituya los valores financiados e intereses generados. El/la "
                "becario/a o beneficiario/a se obliga de manera expresa y sin requerimiento de formalidad "
                "alguna a devolver en su totalidad los valores señalados cuando así se determine."
            ),
        },
        {
            "titulo": "CLÁUSULA OCTAVA.- RENUNCIA A LA BECA O AYUDA ECONÓMICA.-",
            "contenido": (
                "El/la becario/a podrá renunciar a la beca o ayuda económica otorgada por fuerza mayor, "
                "caso fortuito debidamente motivado o por las situaciones calamitosas establecidas en el "
                "Reglamento de Becas y Ayudas Económicas. Corresponderá a la Comisión de Becas y Ayudas "
                "Económicas aprobar la terminación del contrato por mutuo acuerdo. Si el/la becario/a "
                "renuncia por otras razones o no presenta la carta de renuncia, esta situación se "
                "considerará causal para la terminación unilateral del contrato; en este caso será "
                "sancionado/a por incumplimiento de las obligaciones contractuales y reglamentarias y no "
                "podrá postularse ni beneficiarse de otro tipo de beca o renovación."
            ),
        },
        {
            "titulo": "CLÁUSULA NOVENA.- MODIFICACIONES.-",
            "contenido": (
                "Las condiciones para el otorgamiento y renovación de los diversos tipos de becas están "
                "sujetas a "
                "las resoluciones modificatorias del Reglamento de Becas y Ayudas Económicas que expida "
                "el Órgano Colegiado Superior del Instituto Superior Tecnológico de Técnicas Empresariales "
                "y del Conocimiento (INTEC)."
            ),
        },
        {
            "titulo": "CLÁUSULA DÉCIMA.- CONTROVERSIAS.-",
            "contenido": (
                "En caso de controversias, las partes se someterán a la resolución de un juez de la ciudad "
                "de {CIUDAD}, conforme a las disposiciones del Código Orgánico General de Procesos."
            ),
        },
        {
            "titulo": "CLÁUSULA DÉCIMA PRIMERA.- INCORPORACIÓN DE LEYES.-",
            "contenido": (
                "Quedan incorporadas al presente instrumento todas las disposiciones pertinentes del "
                "Código Civil y demás leyes sobre la materia."
            ),
        },
        {
            "titulo": "CLÁUSULA DÉCIMA SEGUNDA.- ACEPTACIÓN Y RATIFICACIÓN.-",
            "contenido": (
                "Las partes declaran expresamente que aceptan los términos y condiciones del presente "
                "contrato por convenir a sus mutuos intereses, por lo que se ratifican en todo su "
                "contenido y, para muestra de aquello, lo suscriben en dos ejemplares del mismo tenor y "
                "valor en la ciudad de {CIUDAD}, a los {FECHA_CONTRATO}."
            ),
        },
    ]


def _program_scholarship_contract_intro() -> str:
    return (
        "En la ciudad de {CIUDAD}, a los {FECHA_CONTRATO}, comparecen el {RECTOR}, en su calidad de "
        "Rector del Instituto Superior Tecnológico de Técnicas Empresariales y del Conocimiento "
        "(INTEC), de conformidad con la {RESOLUCION}; y el/la señor(a)(ita) {ESTUDIANTE}, con cédula "
        "de ciudadanía No. {CEDULA}, a quien en adelante se le denominará como el/la “BECARIO/A”, "
        "conforme a las cláusulas que a continuación se detallan:"
    )


def _tax_incentive_scholarship_program() -> str:
    return (
        "Programa de acceso a la educación superior tecnológica por medio de becas y ayudas "
        "económicas para la población de escasos recursos y vulnerables del Ecuador, en "
        "coordinación con el sector empresarial ecuatoriano, para estudiar en el INTEC"
    )


def _program_scholarship_contract_clauses() -> list[dict[str, str]]:
    return [
        {
            "titulo": "CLÁUSULA PRIMERA.- ANTECEDENTES.-",
            "contenido": (
                "Es política del INTEC otorgar becas y ayudas económicas que aseguren el cumplimiento "
                "del artículo 356 de la Constitución de la República del Ecuador. Es política del INTEC "
                "el otorgamiento de becas y ayudas económicas que aseguren el cumplimiento del artículo "
                "356 de la Constitución de la República del Ecuador, que establece: “el "
                "cobro de aranceles en la educación superior particular contará con mecanismos tales "
                "como becas, créditos, cuotas de ingreso u otros que permitan la integración y equidad "
                "social en sus múltiples dimensiones”; el principio de igualdad de oportunidades y las "
                "demás disposiciones establecidas en la Constitución, en la Ley Orgánica de Educación "
                "Superior (LOES) y demás normativa aplicable."
            ),
        },
        {
            "titulo": "CLÁUSULA SEGUNDA.- OBJETO Y NATURALEZA DEL CONTRATO.-",
            "contenido": (
                "El INTEC otorga la BECA de acuerdo con las especificaciones registradas en las tablas "
                "de datos y proyección de la beca."
            ),
        },
        {
            "titulo": "CLÁUSULA TERCERA.- PLAZO DEL CONTRATO.-",
            "contenido": (
                "El presente contrato rige a partir de su suscripción, sin perjuicio de la fecha de "
                "adjudicación de la beca, y estará vigente hasta su finiquito."
            ),
        },
        {
            "titulo": "CLÁUSULA CUARTA.- ENTREGA DE RECURSOS Y FORMA DE PAGO.-",
            "contenido": (
                "La beca cuenta con el patrocinio de {AUSPICIANTE}, quien es responsable de cubrir los "
                "rubros contenidos en el presente contrato."
            ),
        },
        {
            "titulo": "CLÁUSULA QUINTA.- OBLIGACIONES Y COMPROMISOS DE LAS PARTES.-",
            "contenido": (
                "5.1. OBLIGACIONES DEL INTEC. Son obligaciones del INTEC las siguientes:\n"
                "1. Realizar el seguimiento y control para el cumplimiento de las obligaciones y plazos "
                "estipulados en el presente contrato.\n"
                "2. Cubrir costos adicionales como inglés, derechos de titulación y otros costos de "
                "servicio.\n"
                "5.2. OBLIGACIONES DEL/LA BECARIO/A:\n"
                "1. Cumplir con el objeto para el cual se le otorgó la beca.\n"
                "2. Cumplir con las normas, reglamentos y obligaciones académicas establecidas por el "
                "INTEC.\n"
                "3. Aprobar la carrera en el plazo establecido en el contrato de financiamiento.\n"
                "5. Entregar documentación legítima, válida, veraz y legible para el proceso de "
                "seguimiento de la beca hasta su culminación.\n"
                "6. Cuidar el equipo tecnológico entregado en este programa para garantizar su "
                "conectividad y proceso formativo."
            ),
        },
        {
            "titulo": "CLÁUSULA SEXTA.- CONTROVERSIAS.-",
            "contenido": (
                "En caso de controversias, las partes se someterán a la resolución de un juez de la "
                "ciudad de {CIUDAD}, conforme a las estipulaciones establecidas en el Código Civil y "
                "demás normativa aplicable para este efecto."
            ),
        },
        {
            "titulo": "CLÁUSULA SÉPTIMA.- ACEPTACIÓN Y RATIFICACIÓN.-",
            "contenido": (
                "Las partes declaran expresamente que aceptan los términos y condiciones del presente "
                "contrato de beca, por convenir a sus mutuos intereses; se ratifican en todo su contenido "
                "y lo suscriben en la ciudad de {CIUDAD}, a los {FECHA_CONTRATO}."
            ),
        },
    ]


def _scholarship_contract_full_text(
    introduction: str,
    clauses: list[dict[str, str]],
    contract_format: str,
) -> str:
    parts = [_clean(introduction)] if _clean(introduction) else []
    for index, clause in enumerate(clauses):
        if index == 2:
            parts.append("[[TABLA_DATOS]]")
            if _canonical_scholarship_contract_format(contract_format) == "INCENTIVOS_TRIBUTARIOS":
                parts.append("[[TABLA_PROYECCION]]")
        title = _clean(clause.get("titulo"))
        content = str(clause.get("contenido") or "").strip()
        clause_text = "\n".join(value for value in (title, content) if value)
        if clause_text:
            parts.append(clause_text)
    if len(clauses) < 3:
        parts.append("[[TABLA_DATOS]]")
        if _canonical_scholarship_contract_format(contract_format) == "INCENTIVOS_TRIBUTARIOS":
            parts.append("[[TABLA_PROYECCION]]")
    parts.append("[[FIRMAS]]")
    return "\n\n".join(parts)


def _default_scholarship_contract_template_data(contract_format: str) -> dict[str, Any]:
    canonical_format = _canonical_scholarship_contract_format(contract_format)
    institutional_clauses = _institutional_scholarship_contract_clauses()
    program_clauses = _program_scholarship_contract_clauses()
    template = ScholarshipContractTemplatePayload().model_dump(mode="json")
    template.update(
        {
            "introduccion_institucional": _institutional_scholarship_contract_intro(),
            "clausulas_institucionales": institutional_clauses,
            "introduccion_programa": _program_scholarship_contract_intro(),
            "clausulas_programa": program_clauses,
            "texto_completo": _scholarship_contract_full_text(
                _program_scholarship_contract_intro()
                if canonical_format == "INCENTIVOS_TRIBUTARIOS"
                else _institutional_scholarship_contract_intro(),
                program_clauses
                if canonical_format == "INCENTIVOS_TRIBUTARIOS"
                else institutional_clauses,
                canonical_format,
            ),
        }
    )
    if canonical_format == "INCENTIVOS_TRIBUTARIOS":
        template.update(
            {
                "titulo_contrato": "CONTRATO DE BECA",
                "titulo_tabla_datos": "DATOS BECA",
                "titulo_tabla_proyeccion": "PROYECCIÓN DE LA BECA",
                "rector_tratamiento": "MGT.",
                "rector_titulo": "",
                "programa": _tax_incentive_scholarship_program(),
                "institucion_educacion": (
                    "IST de Técnicas Empresariales y del Conocimiento - INTEC"
                ),
                "proyeccion": [
                    item.model_dump(mode="json")
                    for item in _default_tax_incentive_projection()
                ],
            }
        )
    else:
        template["proyeccion"] = []
    template["titulo_contrato"] = "CONTRATO DE BECA"
    return template


def _resolved_scholarship_contract_template(
    contract_format: str,
    template: ScholarshipContractTemplatePayload | dict[str, Any] | None,
) -> ScholarshipContractTemplatePayload:
    defaults = _default_scholarship_contract_template_data(contract_format)
    if template is None:
        return ScholarshipContractTemplatePayload.model_validate(defaults)

    if isinstance(template, BaseModel):
        overrides = template.model_dump(mode="json", exclude_unset=True)
    else:
        overrides = dict(template)

    override_keys = set(overrides)
    label_overrides = overrides.pop("rotulos_tabla", None)
    overrides.pop("titulo_contrato", None)
    defaults.update(overrides)
    if isinstance(label_overrides, dict):
        defaults["rotulos_tabla"] = {
            **defaults["rotulos_tabla"],
            **label_overrides,
        }
    canonical_format = _canonical_scholarship_contract_format(contract_format)
    content_fields = (
        {"introduccion_programa", "clausulas_programa"}
        if canonical_format == "INCENTIVOS_TRIBUTARIOS"
        else {"introduccion_institucional", "clausulas_institucionales"}
    )
    if "texto_completo" not in override_keys and content_fields & override_keys:
        introduction_field = (
            "introduccion_programa"
            if canonical_format == "INCENTIVOS_TRIBUTARIOS"
            else "introduccion_institucional"
        )
        clauses_field = (
            "clausulas_programa"
            if canonical_format == "INCENTIVOS_TRIBUTARIOS"
            else "clausulas_institucionales"
        )
        defaults["texto_completo"] = _scholarship_contract_full_text(
            str(defaults.get(introduction_field) or ""),
            _scholarship_contract_clauses(defaults, clauses_field, []),
            canonical_format,
        )
    return ScholarshipContractTemplatePayload.model_validate(defaults)


def _scholarship_contract_clauses(
    template: dict[str, Any],
    field_name: str,
    defaults: list[dict[str, str]],
) -> list[dict[str, str]]:
    raw_clauses = template.get(field_name) if field_name in template else None
    if raw_clauses is None:
        return [dict(clause) for clause in defaults]
    if not isinstance(raw_clauses, (list, tuple)):
        return [dict(clause) for clause in defaults]
    result: list[dict[str, str]] = []
    for clause in raw_clauses:
        raw_clause = clause.model_dump() if isinstance(clause, BaseModel) else clause
        if not isinstance(raw_clause, dict):
            continue
        result.append(
            {
                "titulo": _clean(raw_clause.get("titulo")),
                "contenido": str(raw_clause.get("contenido") or "")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .strip(),
            }
        )
    return result


def _scholarship_contract_render_text(value: Any, context: dict[str, Any]) -> str:
    rendered = str(value or "")
    for field_name, field_value in context.items():
        rendered = rendered.replace(f"{{{field_name}}}", _clean(field_value))
    return rendered


def _scholarship_contract_markup(value: Any, context: dict[str, Any]) -> str:
    rendered = _scholarship_contract_render_text(value, context)
    return escape(rendered).replace("\r\n", "<br/>").replace("\r", "<br/>").replace("\n", "<br/>")


def _scholarship_contract_clause_paragraph(
    clause: dict[str, str],
    context: dict[str, Any],
    style: ParagraphStyle,
) -> Paragraph:
    title = _scholarship_contract_markup(clause.get("titulo"), context)
    content = _scholarship_contract_markup(clause.get("contenido"), context)
    separator = " " if title and content else ""
    return Paragraph(f"<b>{title}</b>{separator}{content}", style)


_SCHOLARSHIP_CONTRACT_STRUCTURE_PATTERN = re.compile(
    r"(?m)^\s*\[\[(TABLA_DATOS|TABLA_PROYECCION|FIRMAS)\]\]\s*$"
)


def _scholarship_contract_complete_text(
    template: dict[str, Any],
) -> str | None:
    if "texto_completo" not in template:
        return None
    value = template.get("texto_completo")
    if value is None:
        return None
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _scholarship_contract_ensure_structure_markers(
    text: str,
    marker_names: list[str],
) -> str:
    normalized = text.strip()
    for index, marker_name in enumerate(marker_names):
        marker = f"[[{marker_name}]]"
        if marker in normalized:
            continue
        next_marker = next(
            (
                f"[[{next_name}]]"
                for next_name in marker_names[index + 1 :]
                if f"[[{next_name}]]" in normalized
            ),
            "",
        )
        if next_marker:
            normalized = normalized.replace(next_marker, f"{marker}\n\n{next_marker}", 1)
        else:
            normalized = f"{normalized}\n\n{marker}".strip()
    return normalized


def _scholarship_contract_full_text_paragraph(
    value: str,
    context: dict[str, Any],
    style: ParagraphStyle,
) -> Paragraph | None:
    text = value.strip()
    if not text:
        return None
    lines = text.splitlines()
    first_line = lines[0].strip()
    title_like = (
        len(lines) > 1
        and 2 < len(first_line) <= 250
        and first_line == first_line.upper()
        and any(character.isalpha() for character in first_line)
    )
    if title_like:
        title = _scholarship_contract_markup(first_line, context)
        content = _scholarship_contract_markup("\n".join(lines[1:]), context)
        return Paragraph(f"<b>{title}</b>{' ' if content else ''}{content}", style)
    return Paragraph(_scholarship_contract_markup(text, context), style)


def _scholarship_contract_full_text_story(
    text: str,
    context: dict[str, Any],
    style: ParagraphStyle,
    structures: dict[str, Flowable],
) -> list[Any]:
    complete_text = _scholarship_contract_ensure_structure_markers(
        text,
        list(structures),
    )
    parts = _SCHOLARSHIP_CONTRACT_STRUCTURE_PATTERN.split(complete_text)
    story: list[Any] = []
    inserted_structures: set[str] = set()
    for index, part in enumerate(parts):
        if index % 2 == 1:
            if part in structures and part not in inserted_structures:
                if story and part != "FIRMAS":
                    story.append(Spacer(1, 0.02 * cm))
                story.append(structures[part])
                inserted_structures.add(part)
            continue
        for paragraph_text in re.split(r"\n\s*\n+", part):
            paragraph = _scholarship_contract_full_text_paragraph(
                paragraph_text,
                context,
                style,
            )
            if paragraph is not None:
                story.append(paragraph)
    return story


def _scholarship_contract_template_history(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _scholarship_contract_rector(
    template: dict[str, Any],
    default_treatment: str = "Ingeniero",
    default_title: str = "MGT.",
) -> str:
    treatment = _scholarship_contract_template_text(
        template,
        "rector_tratamiento",
        default_treatment,
    )
    name = _scholarship_contract_template_text(
        template,
        "rector_nombre",
        "JAIME RODER ORTEGA PEREIRA",
    ).upper()
    title = _scholarship_contract_template_text(template, "rector_titulo", default_title)
    suffix = f", {title}" if title else ""
    return f"{treatment} {name}{suffix}"


def _scholarship_contract_rector_signature(template: dict[str, Any]) -> str:
    treatment = _scholarship_contract_template_text(
        template,
        "firma_rector_tratamiento",
        "Ing.",
    )
    name = _scholarship_contract_template_text(
        template,
        "firma_rector_nombre",
        "JAIME RODER ORTEGA PEREIRA",
    ).upper()
    title = _scholarship_contract_template_text(
        template,
        "firma_rector_titulo",
        "MGT.",
    )
    suffix = f", {title}" if title else ""
    return f"{treatment} {name}{suffix}"


def _scholarship_contract_date_text(value: date) -> str:
    months = (
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    )
    return f"{value.day} días del mes de {months[value.month - 1]} de {value.year}"


def _scholarship_contract_display_date(value: Any, default: str = "NO REGISTRADA") -> str:
    text = _clean(value)
    if not text:
        return default
    try:
        parsed = date.fromisoformat(text[:10])
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return text.upper()


def _scholarship_period_bounds(value: Any) -> tuple[date | None, date | None]:
    period = _clean(value).upper()
    month_numbers = {
        "ENERO": 1,
        "FEBRERO": 2,
        "MARZO": 3,
        "ABRIL": 4,
        "MAYO": 5,
        "JUNIO": 6,
        "JULIO": 7,
        "AGOSTO": 8,
        "SEPTIEMBRE": 9,
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }
    months = sorted(
        (match.start(), number)
        for name, number in month_numbers.items()
        for match in re.finditer(name, period)
    )
    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", period)]
    if not months or not years:
        return None, None
    start_year = years[0]
    end_year = years[-1]
    start_month = months[0][1]
    end_month = months[-1][1]
    return (
        date(start_year, start_month, 1),
        date(end_year, end_month, calendar.monthrange(end_year, end_month)[1]),
    )


def _scholarship_contract_fonts() -> tuple[str, str, str, str]:
    regular_name = "IntecContractCalibri"
    bold_name = "IntecContractCalibriBold"
    italic_name = "IntecContractCalibriItalic"
    bold_italic_name = "IntecContractCalibriBoldItalic"
    if regular_name in pdfmetrics.getRegisteredFontNames():
        return regular_name, bold_name, italic_name, bold_italic_name

    font_dir = Path("C:/Windows/Fonts")
    font_paths = (
        font_dir / "calibri.ttf",
        font_dir / "calibrib.ttf",
        font_dir / "calibrii.ttf",
        font_dir / "calibriz.ttf",
    )
    if not all(path.is_file() for path in font_paths):
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"
    try:
        pdfmetrics.registerFont(TTFont(regular_name, str(font_paths[0])))
        pdfmetrics.registerFont(TTFont(bold_name, str(font_paths[1])))
        pdfmetrics.registerFont(TTFont(italic_name, str(font_paths[2])))
        pdfmetrics.registerFont(TTFont(bold_italic_name, str(font_paths[3])))
        pdfmetrics.registerFontFamily(
            regular_name,
            normal=regular_name,
            bold=bold_name,
            italic=italic_name,
            boldItalic=bold_italic_name,
        )
        return regular_name, bold_name, italic_name, bold_italic_name
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"


def _build_scholarship_contract_pdf(
    item: dict[str, Any],
    contract_number: str,
    contract_date: date,
    template: ScholarshipContractTemplatePayload | dict[str, Any] | None = None,
) -> bytes:
    template_data = _resolved_scholarship_contract_template(
        "BECA",
        template,
    ).model_dump(mode="json")
    contract_title = _scholarship_contract_template_text(
        template_data,
        "titulo_contrato",
        "CONTRATO DE BECA",
    ).upper()
    city = _scholarship_contract_template_text(template_data, "ciudad", "Quito, D.M.")
    resolution = _scholarship_contract_template_text(
        template_data,
        "resolucion",
        "Resolución No. 002-CR-INTEC-2024, de 19 de diciembre de 2024",
    )
    rector = _scholarship_contract_rector(template_data)
    rector_signature = _scholarship_contract_rector_signature(template_data)
    notification_email = _scholarship_contract_template_text(
        template_data,
        "correo_notificaciones",
        "dir.bienestar@intec.edu.ec",
    )
    table_header_color = _scholarship_contract_color(
        template_data,
        "color_cabecera_tabla",
        _SCHOLARSHIP_CONTRACT_TABLE_HEADER_COLOR,
    )
    table_label_color = _scholarship_contract_color(
        template_data,
        "color_celda_etiqueta",
        _SCHOLARSHIP_CONTRACT_TABLE_LABEL_COLOR,
    )
    table_value_color = _scholarship_contract_color(
        template_data,
        "color_celda_valor",
        _SCHOLARSHIP_CONTRACT_TABLE_VALUE_COLOR,
    )
    table_border_color = _scholarship_contract_color(
        template_data,
        "color_borde_tabla",
        _SCHOLARSHIP_CONTRACT_TABLE_BORDER_COLOR,
    )
    data_table_title = _scholarship_contract_template_text(
        template_data,
        "titulo_tabla_datos",
        "DATOS BECA",
    )
    rector_signature_label = _scholarship_contract_template_text(
        template_data,
        "firma_rector_etiqueta",
        "RECTOR",
    )
    scholarship_signature_treatment = _scholarship_contract_template_text(
        template_data,
        "firma_becario_tratamiento",
        "Sr.(a)(ita):",
    )
    scholarship_signature_label = _scholarship_contract_template_text(
        template_data,
        "firma_becario_etiqueta",
        "BECARIO/A",
    )
    contract_number_label = _scholarship_contract_table_label(
        template_data,
        "numero_contrato",
        "No.",
    )
    signature_identification_label = _scholarship_contract_table_label(
        template_data,
        "identificacion_firma",
        "C.C.:",
    )
    output = BytesIO()
    regular_font, bold_font, italic_font, _ = _scholarship_contract_fonts()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=0.94 * cm,
        leftMargin=1.30 * cm,
        topMargin=1.59 * cm,
        bottomMargin=1.72 * cm,
        title=f"Contrato de beca {contract_number}",
        author="Instituto Superior Tecnológico INTEC",
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ScholarshipContractBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=8.0,
        leading=9.25,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#111111"),
        spaceBefore=0,
        spaceAfter=0.25,
        allowWidows=1,
        allowOrphans=1,
    )
    list_style = ParagraphStyle(
        "ScholarshipContractList",
        parent=body_style,
        leftIndent=0.48 * cm,
        firstLineIndent=-0.34 * cm,
    )
    cell_label = ParagraphStyle(
        "ScholarshipContractCellLabel",
        parent=styles["Normal"],
        alignment=0,
        fontName=bold_font,
        fontSize=8.04,
        leading=8.15,
        textColor=colors.HexColor("#111111"),
    )
    cell_value = ParagraphStyle(
        "ScholarshipContractCellValue",
        parent=cell_label,
        fontName=bold_font,
    )
    cell_value_regular = ParagraphStyle(
        "ScholarshipContractCellValueRegular",
        parent=cell_label,
        fontName=regular_font,
    )
    cell_header = ParagraphStyle(
        "ScholarshipContractCellHeader",
        parent=cell_label,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    email_style = ParagraphStyle(
        "ScholarshipContractEmail",
        parent=cell_value_regular,
        textColor=colors.HexColor("#0563C1"),
    )
    signature_style = ParagraphStyle(
        "ScholarshipContractSignature",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=8.04,
        leading=8.55,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
    )

    def paragraph(value: Any, style: ParagraphStyle = cell_value) -> Paragraph:
        return Paragraph(escape(_clean(value) or "-"), style)

    empty_cell = Paragraph("", cell_value_regular)

    def draw_contract_background(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_width, page_height = A4

        if _SCHOLARSHIP_CONTRACT_BACKGROUND_PATH.is_file():
            background_width = 13.34 * cm
            background_height = 22.61 * cm
            canvas.drawImage(
                str(_SCHOLARSHIP_CONTRACT_BACKGROUND_PATH),
                0.03 * cm,
                page_height - 5.72 * cm - background_height,
                width=background_width,
                height=background_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        else:
            canvas.setFillColor(colors.HexColor("#EFDADA"))
            canvas.setStrokeColor(colors.HexColor("#EFDADA"))
            path = canvas.beginPath()
            path.moveTo(0, page_height - 5.72 * cm)
            path.lineTo(9.55 * cm, page_height - 5.72 * cm)
            path.lineTo(11.45 * cm, page_height - 7.15 * cm)
            path.curveTo(9.0 * cm, page_height - 9.8 * cm, 1.0 * cm, page_height - 8.6 * cm, 1.0 * cm, page_height - 12.0 * cm)
            path.curveTo(1.0 * cm, page_height - 15.0 * cm, 8.5 * cm, page_height - 13.7 * cm, 7.0 * cm, page_height - 17.3 * cm)
            path.curveTo(5.7 * cm, page_height - 20.2 * cm, 1.2 * cm, page_height - 18.9 * cm, 1.35 * cm, page_height - 21.1 * cm)
            path.curveTo(1.5 * cm, page_height - 23.3 * cm, 7.8 * cm, page_height - 22.2 * cm, 6.9 * cm, page_height - 25.3 * cm)
            path.lineTo(0, page_height - 24.0 * cm)
            path.close()
            canvas.drawPath(path, fill=1, stroke=0)

        logo = _SvgLogo(_LOGO_PATH, 3.2 * cm)
        logo.drawOn(canvas, 0.72 * cm, page_height - 1.68 * cm)

        title_x = 5.55 * cm
        title_y = page_height - 1.50 * cm
        title_width = 11.52 * cm
        title_height = 0.70 * cm
        canvas.setStrokeColor(colors.HexColor("#A6A6A6"))
        canvas.setLineWidth(0.45)
        canvas.rect(title_x, title_y, title_width, title_height, fill=0, stroke=1)
        canvas.setFillColor(colors.HexColor("#000000"))
        canvas.setFont(bold_font, 14.0)
        canvas.drawCentredString(
            title_x + title_width / 2,
            title_y + 0.18 * cm,
            f"{contract_title} - {contract_number_label} {contract_number}".strip(),
        )

        if not _SCHOLARSHIP_CONTRACT_BACKGROUND_PATH.is_file():
            canvas.setFillColor(colors.HexColor("#7F7F7F"))
            canvas.setFont(regular_font, 14.0)
            canvas.drawCentredString(page_width / 2, 0.66 * cm, "w w w . i n t e c . e d u . e c")
        canvas.setFillColor(colors.HexColor("#111111"))
        canvas.setFont(regular_font, 5.9)
        canvas.drawCentredString(page_width / 2, 0.23 * cm, f"Página {doc.page}")
        canvas.drawRightString(page_width - 1.25 * cm, 0.23 * cm, "N/C 272")
        canvas.restoreState()

    student_name = _clean(item.get("estudiante")) or "la persona beneficiaria"
    student_name_upper = student_name.upper()
    cedula = _clean(item.get("cedula")) or "NO REGISTRADA"
    contract_date_text = _scholarship_contract_date_text(contract_date)
    approved_percentage = f"{float(item.get('porcentaje_beca') or 0):g}%"
    granted_amount = _format_money(item.get("valor_beca")).replace("$ ", "") + " $"
    scholarship_name = _clean(item.get("tipo_beca")) or "BECA REGISTRADA"
    period_label = _scholarship_period_label(item.get("periodo") or item.get("codigo_periodo"))
    contract_context = {
        "CIUDAD": city,
        "FECHA_CONTRATO": contract_date_text,
        "RECTOR": rector,
        "RESOLUCION": resolution,
        "ESTUDIANTE": student_name_upper,
        "CEDULA": cedula,
        "CONTRATO": contract_number,
        "BECA": scholarship_name.upper(),
        "PORCENTAJE_BECA": approved_percentage,
        "VALOR_BECA": _format_money(item.get("valor_beca")),
        "PERIODO": period_label,
        "ALCANCE_BECA": _scholarship_contract_scope(item),
        "CARRERA": _clean(item.get("carrera") or item.get("codigo_carrera")).upper(),
        "AUSPICIANTE": _clean(template_data.get("auspiciante")) or "INTEC",
    }
    introduction = _scholarship_contract_template_multiline(
        template_data,
        "introduccion_institucional",
        _institutional_scholarship_contract_intro(),
    )
    clauses = _scholarship_contract_clauses(
        template_data,
        "clausulas_institucionales",
        _institutional_scholarship_contract_clauses(),
    )
    story: list[Any] = []
    first_clause = clauses[0] if clauses else None
    opening_markup = _scholarship_contract_markup(introduction, contract_context)
    if first_clause:
        clause_title = _scholarship_contract_markup(first_clause.get("titulo"), contract_context)
        clause_content = _scholarship_contract_markup(first_clause.get("contenido"), contract_context)
        opening_markup = (
            f"{opening_markup}{' ' if opening_markup else ''}<b>{clause_title}</b>"
            f"{' ' if clause_content else ''}{clause_content}"
        )
    if opening_markup:
        story.append(Paragraph(opening_markup, body_style))
    if len(clauses) > 1:
        story.append(_scholarship_contract_clause_paragraph(clauses[1], contract_context, body_style))

    benefit_suffix = _scholarship_contract_table_label(
        template_data,
        "beneficio_sufijo",
        "del valor del arancel vigente",
    )
    benefit_value = (
        f"<b>{escape(approved_percentage)} &nbsp;&nbsp; - &nbsp;&nbsp; {escape(granted_amount)}</b>"
        f"{' &nbsp;&nbsp; ' + escape(benefit_suffix) if benefit_suffix else ''}"
    )
    details = [
        [Paragraph(escape(data_table_title), cell_header), empty_cell, empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "becario", "Apellidos y nombres del/la becario/a:"), cell_label), paragraph(student_name_upper), empty_cell, empty_cell, paragraph(f"{_scholarship_contract_table_label(template_data, 'numero_beca', 'Beca No.')} {contract_number}".strip())],
        [paragraph(_scholarship_contract_table_label(template_data, "cedula", "Cédula de ciudadanía / identidad:"), cell_label), paragraph(cedula), empty_cell, paragraph(_scholarship_contract_table_label(template_data, "telefono", "Teléfono:"), cell_label), paragraph(item.get("telefono"))],
        [paragraph(_scholarship_contract_table_label(template_data, "nivel_formacion", "Nivel de formación:"), cell_label), paragraph(_scholarship_education_level(item.get("nivel_formacion"))), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "carrera_programa", "Carrera/programa:"), cell_label), paragraph((_clean(item.get("carrera")) or _clean(item.get("codigo_carrera"))).upper()), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "tipo_beca", "Tipo de beca:"), cell_label), paragraph(scholarship_name.upper()), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "discapacidad", "Discapacidad:"), cell_label), paragraph(_scholarship_disability(item.get("discapacidad"))), paragraph(_scholarship_contract_table_label(template_data, "porcentaje_discapacidad", "Porcentaje de discapacidad:"), cell_label), empty_cell, paragraph(_scholarship_disability_percentage(item))],
        [paragraph(_scholarship_contract_table_label(template_data, "tipo_discapacidad", "Tipo de discapacidad:"), cell_label), paragraph(_scholarship_disability_type(item).upper()), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "beneficio", "Porcentaje de beca y monto otorgado:"), cell_label), Paragraph(benefit_value, cell_value_regular), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "periodo_adjudicacion", "Período de adjudicación:"), cell_label), paragraph(period_label), empty_cell, empty_cell, empty_cell],
        [paragraph(_scholarship_contract_table_label(template_data, "correo_notificaciones", "Correo INTEC para notificaciones:"), cell_label), Paragraph(f'<link href="mailto:{escape(notification_email)}">{escape(notification_email)}</link>', email_style), empty_cell, empty_cell, empty_cell],
    ]
    details_table = Table(details, colWidths=[6.75 * cm, 3.50 * cm, 1.50 * cm, 3.00 * cm, 3.60 * cm])
    details_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (4, 0)),
                ("BACKGROUND", (0, 0), (-1, -1), table_value_color),
                ("BACKGROUND", (0, 0), (4, 0), table_header_color),
                ("BACKGROUND", (0, 1), (0, 10), table_label_color),
                ("BACKGROUND", (3, 2), (3, 2), table_label_color),
                ("BACKGROUND", (2, 6), (2, 6), table_label_color),
                ("ALIGN", (0, 0), (4, 0), "CENTER"),
                ("SPAN", (1, 1), (3, 1)),
                ("SPAN", (1, 2), (2, 2)),
                ("SPAN", (1, 3), (4, 3)),
                ("SPAN", (1, 4), (4, 4)),
                ("SPAN", (1, 5), (4, 5)),
                ("SPAN", (2, 6), (3, 6)),
                ("SPAN", (1, 7), (4, 7)),
                ("SPAN", (1, 8), (4, 8)),
                ("SPAN", (1, 9), (4, 9)),
                ("SPAN", (1, 10), (4, 10)),
                ("GRID", (0, 0), (-1, -1), 0.45, table_border_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7.0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7.0),
                ("TOPPADDING", (0, 0), (-1, -1), 0.65),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.65),
                ("TOPPADDING", (0, 0), (4, 0), 1.4),
                ("BOTTOMPADDING", (0, 0), (4, 0), 1.4),
            ]
        )
    )
    story.extend([details_table, Spacer(1, 0.02 * cm)])

    for clause in clauses[2:]:
        story.append(_scholarship_contract_clause_paragraph(clause, contract_context, body_style))

    signature_line = "________________________________________"
    signatures = Table(
        [
            [signature_line, signature_line],
            [
                Paragraph(
                    f"{escape(rector_signature)}<br/>{escape(rector_signature_label)}",
                    signature_style,
                ),
                Paragraph(
                    f"{escape(scholarship_signature_treatment)} <b>{escape(student_name_upper)}</b><br/>"
                    f"{escape(scholarship_signature_label)} – {escape(signature_identification_label)} <b>{escape(cedula)}</b>",
                    signature_style,
                ),
            ],
        ],
        colWidths=[8.95 * cm, 8.95 * cm],
        rowHeights=[2.55 * cm, None],
        splitByRow=0,
    )
    signatures.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), regular_font),
                ("FONTSIZE", (0, 0), (-1, 0), 7.0),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111111")),
                ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                ("VALIGN", (0, 1), (-1, 1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    complete_text = _scholarship_contract_complete_text(
        template_data,
    )
    if complete_text is None:
        story.append(signatures)
    else:
        story = _scholarship_contract_full_text_story(
            complete_text,
            contract_context,
            body_style,
            {
                "TABLA_DATOS": details_table,
                "FIRMAS": signatures,
            },
        )
    one_page_story = [KeepInFrame(document.width, document.height, story, mode="shrink")]
    document.build(
        one_page_story,
        onFirstPage=draw_contract_background,
        onLaterPages=draw_contract_background,
    )
    return output.getvalue()


def _build_program_scholarship_contract_pdf(
    item: dict[str, Any],
    contract_number: str,
    contract_date: date,
    template: ScholarshipContractTemplatePayload | dict[str, Any] | None = None,
) -> bytes:
    template_data = _resolved_scholarship_contract_template(
        "INCENTIVOS_TRIBUTARIOS",
        template,
    ).model_dump(mode="json")
    contract_title = _scholarship_contract_template_text(
        template_data,
        "titulo_contrato",
        "CONTRATO DE BECA",
    ).upper()
    city = _scholarship_contract_template_text(template_data, "ciudad", "Quito, D.M.")
    resolution = _scholarship_contract_template_text(
        template_data,
        "resolucion",
        "Resolución No. 002-CR-INTEC-2024, de 19 de diciembre de 2024",
    )
    rector = _scholarship_contract_rector(
        template_data,
        default_treatment="MGT.",
        default_title="",
    )
    rector_signature = _scholarship_contract_rector_signature(template_data)
    table_header_color = _scholarship_contract_color(
        template_data,
        "color_cabecera_tabla",
        _SCHOLARSHIP_CONTRACT_TABLE_HEADER_COLOR,
    )
    table_label_color = _scholarship_contract_color(
        template_data,
        "color_celda_etiqueta",
        _SCHOLARSHIP_CONTRACT_TABLE_LABEL_COLOR,
    )
    table_inner_header_color = _scholarship_contract_color(
        template_data,
        "color_cabecera_interior",
        _SCHOLARSHIP_CONTRACT_TABLE_INNER_HEADER_COLOR,
    )
    table_value_color = _scholarship_contract_color(
        template_data,
        "color_celda_valor",
        _SCHOLARSHIP_CONTRACT_TABLE_VALUE_COLOR,
    )
    table_border_color = _scholarship_contract_color(
        template_data,
        "color_borde_tabla",
        _SCHOLARSHIP_CONTRACT_TABLE_BORDER_COLOR,
    )
    data_table_title = _scholarship_contract_template_text(
        template_data,
        "titulo_tabla_datos",
        "DATOS BECA",
    )
    projection_table_title = _scholarship_contract_template_text(
        template_data,
        "titulo_tabla_proyeccion",
        "PROYECCIÓN DE LA BECA",
    )
    rector_signature_label = _scholarship_contract_template_text(
        template_data,
        "firma_rector_etiqueta",
        "RECTOR",
    )
    scholarship_signature_treatment = _scholarship_contract_template_text(
        template_data,
        "firma_becario_tratamiento",
        "Sr.(a)(ita):",
    )
    scholarship_signature_label = _scholarship_contract_template_text(
        template_data,
        "firma_becario_etiqueta",
        "BECARIO/A",
    )
    contract_number_label = _scholarship_contract_table_label(
        template_data,
        "numero_contrato",
        "No.",
    )
    signature_identification_label = _scholarship_contract_table_label(
        template_data,
        "identificacion_firma",
        "C.C.:",
    )
    program = _scholarship_contract_template_text(
        template_data,
        "programa",
        _tax_incentive_scholarship_program(),
    )
    institution = _scholarship_contract_template_text(
        template_data,
        "institucion_educacion",
        "IST de Técnicas Empresariales y del Conocimiento - INTEC",
    )
    country = _scholarship_contract_template_text(template_data, "pais", "Ecuador")
    sponsor = _scholarship_contract_template_text(template_data, "auspiciante", "INTEC")
    education_level = _scholarship_contract_template_text(
        template_data,
        "nivel_estudios",
        _scholarship_education_level(item.get("nivel_formacion")),
    )
    study_duration = _scholarship_contract_template_text(
        template_data,
        "duracion_estudios",
        "Durante el período académico adjudicado",
    )
    financing_duration = _scholarship_contract_template_text(
        template_data,
        "duracion_financiamiento",
        "Durante el período académico adjudicado",
    )
    payment_period = _scholarship_contract_template_text(template_data, "periodo_pago", "TOTAL")
    period_value = item.get("periodo") or item.get("codigo_periodo")
    period_label = _scholarship_period_label(period_value)
    period_start, period_end = _scholarship_period_bounds(period_value)
    start_default = period_start.isoformat() if period_start else ""
    end_default = period_end.isoformat() if period_end else ""
    study_start = _scholarship_contract_display_date(
        template_data.get("fecha_inicio_estudios") or start_default,
    )
    study_end = _scholarship_contract_display_date(
        template_data.get("fecha_fin_estudios") or end_default,
    )
    financing_start = _scholarship_contract_display_date(
        template_data.get("fecha_inicio_financiamiento") or start_default,
    )
    financing_end = _scholarship_contract_display_date(
        template_data.get("fecha_fin_financiamiento") or end_default,
    )

    output = BytesIO()
    regular_font, bold_font, _, _ = _scholarship_contract_fonts()
    contract_page_size = LETTER
    document = SimpleDocTemplate(
        output,
        pagesize=contract_page_size,
        rightMargin=1.20 * cm,
        leftMargin=1.20 * cm,
        topMargin=2.45 * cm,
        bottomMargin=1.15 * cm,
        title=f"{contract_title} {contract_number}",
        author="Instituto Superior Tecnológico INTEC",
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ScholarshipProgramBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=8.15,
        leading=10.5,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#111111"),
        spaceBefore=0,
        spaceAfter=1.2,
        allowWidows=1,
        allowOrphans=1,
    )
    cell_label = ParagraphStyle(
        "ScholarshipProgramCellLabel",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=7.25,
        leading=7.85,
        textColor=colors.HexColor("#111111"),
    )
    cell_value = ParagraphStyle(
        "ScholarshipProgramCellValue",
        parent=cell_label,
        fontName=regular_font,
    )
    cell_header = ParagraphStyle(
        "ScholarshipProgramCellHeader",
        parent=cell_label,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    signature_style = ParagraphStyle(
        "ScholarshipProgramSignature",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=7.75,
        leading=8.4,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
    )

    def paragraph(value: Any, style: ParagraphStyle = cell_value) -> Paragraph:
        return Paragraph(escape(_clean(value) or "-"), style)

    def draw_program_background(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_width, page_height = contract_page_size
        if _SCHOLARSHIP_CONTRACT_BACKGROUND_PATH.is_file():
            canvas.drawImage(
                str(_SCHOLARSHIP_CONTRACT_BACKGROUND_PATH),
                0,
                0.20 * cm,
                width=10.4 * cm,
                height=17.7 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )
        logo = _SvgLogo(_LOGO_PATH, 3.4 * cm)
        logo.drawOn(canvas, 0.75 * cm, page_height - 1.80 * cm)
        title_x = 4.30 * cm
        title_y = page_height - 1.58 * cm
        title_width = page_width - title_x - 1.20 * cm
        title_height = 0.82 * cm
        canvas.setStrokeColor(colors.HexColor("#D2D2D2"))
        canvas.setLineWidth(0.45)
        canvas.roundRect(
            title_x,
            title_y,
            title_width,
            title_height,
            0.12 * cm,
            fill=0,
            stroke=1,
        )
        canvas.setFillColor(table_header_color)
        canvas.setFont(bold_font, 13.5)
        canvas.drawCentredString(
            title_x + title_width / 2,
            title_y + 0.22 * cm,
            f"{contract_title} {contract_number_label} {contract_number}".strip(),
        )
        canvas.setFont(regular_font, 5.8)
        canvas.drawCentredString(page_width / 2, 0.42 * cm, f"Página {doc.page}")
        canvas.restoreState()

    student_name = (_clean(item.get("estudiante")) or "LA PERSONA BENEFICIARIA").upper()
    cedula = _clean(item.get("cedula")) or "NO REGISTRADA"
    career = (_clean(item.get("carrera")) or _clean(item.get("codigo_carrera")) or "NO REGISTRADA").upper()
    date_text = _scholarship_contract_date_text(contract_date)
    scholarship_name = (_clean(item.get("tipo_beca")) or "BECA REGISTRADA").upper()
    percentage = float(item.get("porcentaje_beca") or 0)
    granted_amount = _format_money(item.get("valor_beca"))
    contract_context = {
        "CIUDAD": city,
        "FECHA_CONTRATO": date_text,
        "RECTOR": rector,
        "RESOLUCION": resolution,
        "ESTUDIANTE": student_name,
        "CEDULA": cedula,
        "CONTRATO": contract_number,
        "BECA": scholarship_name,
        "PORCENTAJE_BECA": f"{percentage:g}%",
        "VALOR_BECA": granted_amount,
        "PERIODO": period_label,
        "ALCANCE_BECA": _scholarship_contract_scope(item),
        "AUSPICIANTE": sponsor,
        "CARRERA": career,
    }
    introduction = _scholarship_contract_template_multiline(
        template_data,
        "introduccion_programa",
        _program_scholarship_contract_intro(),
    )
    clauses = _scholarship_contract_clauses(
        template_data,
        "clausulas_programa",
        _program_scholarship_contract_clauses(),
    )
    story: list[Any] = []
    first_clause = clauses[0] if clauses else None
    opening_markup = _scholarship_contract_markup(introduction, contract_context)
    if first_clause:
        clause_title = _scholarship_contract_markup(first_clause.get("titulo"), contract_context)
        clause_content = _scholarship_contract_markup(first_clause.get("contenido"), contract_context)
        opening_markup = (
            f"{opening_markup}{' ' if opening_markup else ''}<b>{clause_title}</b>"
            f"{' ' if clause_content else ''}{clause_content}"
        )
    if opening_markup:
        story.append(Paragraph(opening_markup, body_style))
    if len(clauses) > 1:
        story.append(_scholarship_contract_clause_paragraph(clauses[1], contract_context, body_style))

    data_rows = [
        [Paragraph(escape(data_table_title), cell_header), "", "", ""],
        [paragraph(_scholarship_contract_table_label(template_data, "nombres", "Apellidos y Nombres"), cell_label), paragraph(student_name), paragraph(_scholarship_contract_table_label(template_data, "documento_identidad", "Documento de identidad"), cell_label), paragraph(f"{_scholarship_contract_table_label(template_data, 'prefijo_documento_identidad', 'CÉDULA -')} {cedula}".strip())],
        [paragraph(_scholarship_contract_table_label(template_data, "programa", "Programa"), cell_label), paragraph(program), "", ""],
        [paragraph(_scholarship_contract_table_label(template_data, "pais", "País"), cell_label), paragraph(country), paragraph(_scholarship_contract_table_label(template_data, "fecha_fin_financiamiento", "Fecha final financiamiento"), cell_label), paragraph(financing_end)],
        [paragraph(_scholarship_contract_table_label(template_data, "institucion_educacion", "Institución de Educación"), cell_label), paragraph(institution), paragraph(_scholarship_contract_table_label(template_data, "duracion_financiamiento", "Duración financiamiento"), cell_label), paragraph(financing_duration)],
        [paragraph(_scholarship_contract_table_label(template_data, "auspiciante", "Auspiciante"), cell_label), paragraph(sponsor), paragraph(_scholarship_contract_table_label(template_data, "fecha_inicio_estudios", "Fecha inicio estudios"), cell_label), paragraph(study_start)],
        [paragraph(_scholarship_contract_table_label(template_data, "carrera", "Carrera"), cell_label), paragraph(career), paragraph(_scholarship_contract_table_label(template_data, "fecha_fin_estudios", "Fecha finalización estudios"), cell_label), paragraph(study_end)],
        [paragraph(_scholarship_contract_table_label(template_data, "nivel_estudios", "Nivel de estudios"), cell_label), paragraph(education_level), paragraph(_scholarship_contract_table_label(template_data, "duracion_estudios", "Duración de estudios"), cell_label), paragraph(study_duration)],
        [paragraph(_scholarship_contract_table_label(template_data, "fecha_inicio_financiamiento", "Fecha inicial financiamiento"), cell_label), paragraph(financing_start), paragraph(_scholarship_contract_table_label(template_data, "periodo_pago", "Período de pago"), cell_label), paragraph(payment_period)],
    ]
    data_table = Table(data_rows, colWidths=[3.75 * cm, 5.45 * cm, 3.75 * cm, 5.45 * cm])
    data_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (3, 0)),
                ("SPAN", (1, 2), (3, 2)),
                ("BACKGROUND", (0, 0), (-1, -1), table_value_color),
                ("BACKGROUND", (0, 0), (3, 0), table_header_color),
                ("BACKGROUND", (0, 1), (0, 8), table_label_color),
                ("BACKGROUND", (2, 1), (2, 1), table_label_color),
                ("BACKGROUND", (2, 3), (2, 8), table_label_color),
                ("ALIGN", (0, 0), (3, 0), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, table_border_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]
        )
    )
    story.extend([data_table, Spacer(1, 0.07 * cm)])

    projection_items = template_data.get("proyeccion") or []
    if not projection_items:
        projection_items = [
            {
                "rubro": "Matrícula y arancel",
                "periodicidad": f"{percentage:g}% del arancel académico durante {period_label}",
            },
            {
                "rubro": "Ayuda económica",
                "periodicidad": f"{granted_amount} durante {period_label}",
            },
        ]
    projection_rows: list[list[Any]] = [
        [Paragraph(escape(projection_table_title), cell_header), "", ""],
        [
            paragraph(_scholarship_contract_table_label(template_data, "numero", "Nº"), cell_label),
            paragraph(_scholarship_contract_table_label(template_data, "rubro", "Rubro"), cell_label),
            paragraph(
                _scholarship_contract_table_label(
                    template_data,
                    "periodicidad_rubro",
                    "Periodicidad del rubro",
                ),
                cell_label,
            ),
        ],
    ]
    for index, projection in enumerate(projection_items, start=1):
        raw_projection = (
            projection.model_dump() if isinstance(projection, BaseModel) else dict(projection)
        )
        projection_rows.append(
            [
                paragraph(index),
                paragraph(_scholarship_contract_render_text(raw_projection.get("rubro"), contract_context)),
                paragraph(
                    _scholarship_contract_render_text(
                        raw_projection.get("periodicidad"),
                        contract_context,
                    )
                ),
            ]
        )
    projection_table = Table(projection_rows, colWidths=[1.0 * cm, 7.0 * cm, 10.4 * cm])
    projection_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (2, 0)),
                ("BACKGROUND", (0, 0), (-1, -1), table_value_color),
                ("BACKGROUND", (0, 0), (2, 0), table_header_color),
                ("BACKGROUND", (0, 1), (2, 1), table_inner_header_color),
                ("ALIGN", (0, 0), (2, 1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, table_border_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]
        )
    )
    story.extend([projection_table, Spacer(1, 0.06 * cm)])

    for clause in clauses[2:]:
        story.append(_scholarship_contract_clause_paragraph(clause, contract_context, body_style))

    signatures = Table(
        [
            ["________________________________________", "________________________________________"],
            [
                Paragraph(
                    f"{escape(rector_signature)}<br/>{escape(rector_signature_label)}",
                    signature_style,
                ),
                Paragraph(
                    f"{escape(scholarship_signature_treatment)} <b>{escape(student_name)}</b><br/>"
                    f"{escape(scholarship_signature_label)} - {escape(signature_identification_label)} <b>{escape(cedula)}</b>",
                    signature_style,
                ),
            ],
        ],
        colWidths=[9.2 * cm, 9.2 * cm],
        rowHeights=[4.20 * cm, None],
        splitByRow=0,
    )
    signatures.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), regular_font),
                ("FONTSIZE", (0, 0), (-1, 0), 6.5),
                ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                ("VALIGN", (0, 1), (-1, 1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    complete_text = _scholarship_contract_complete_text(
        template_data,
    )
    if complete_text is None:
        story.append(signatures)
    else:
        story = _scholarship_contract_full_text_story(
            complete_text,
            contract_context,
            body_style,
            {
                "TABLA_DATOS": data_table,
                "TABLA_PROYECCION": projection_table,
                "FIRMAS": signatures,
            },
        )
    one_page_story = [KeepInFrame(document.width, document.height, story, mode="shrink")]
    document.build(
        one_page_story,
        onFirstPage=draw_program_background,
        onLaterPages=draw_program_background,
    )
    return output.getvalue()


def _build_selected_scholarship_contract_pdf(
    item: dict[str, Any],
    contract_number: str,
    contract_date: date,
    contract_format: str,
    template: ScholarshipContractTemplatePayload | dict[str, Any] | None = None,
) -> bytes:
    if _canonical_scholarship_contract_format(contract_format) == "INCENTIVOS_TRIBUTARIOS":
        return _build_program_scholarship_contract_pdf(
            item,
            contract_number,
            contract_date,
            template,
        )
    return _build_scholarship_contract_pdf(item, contract_number, contract_date, template)


def _date_from_iso(value: str | None) -> date:
    text = _clean(value)
    if not text:
        return date.today()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return date.today()


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _payment_plan_rows(
    plan: dict[str, float | int],
    payload: PreinscriptionCabeceraPayload,
    first_payment_date: str,
) -> list[list[str]]:
    cuotas = max(int(plan["num_cuotas"]), 1)
    saldo = float(plan["saldo"])
    cuota = float(plan["cuota_valor"])
    detalle = _clean(payload.detalle_pago) or "Convenio de pago"
    start_date = _date_from_iso(first_payment_date)
    rows: list[list[str]] = [["No. Pago", "Detalle", "Fecha de Pago", "Valor"]]
    accumulated = 0.0
    for index in range(cuotas):
        value = round(cuota, 2)
        if index == cuotas - 1:
            value = round(max(saldo - accumulated, 0), 2)
        accumulated = round(accumulated + value, 2)
        rows.append(
            [
                str(index + 1),
                detalle if cuotas == 1 else f"Cuota {index + 1} - {detalle}",
                _add_months(start_date, index).strftime("%d/%m/%Y"),
                _format_money(value),
            ]
        )
    return rows


def _write_convenio_document(
    row: Any,
    codigo_documentacion: str,
    plan: dict[str, float | int],
    payload: PreinscriptionCabeceraPayload,
    fecha_pago: str,
) -> str:
    code = _clean(codigo_documentacion) or _clean(getattr(row, "num", ""))
    if not code:
        return ""
    target_dir = _PREINSCRIPTION_UPLOAD_ROOT / code
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"carta-compromiso-{_safe_filename(code)}.pdf"
    target_path = target_dir / filename
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CrystalTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=11, leading=14, spaceAfter=0))
    styles.add(ParagraphStyle(name="CrystalBody", parent=styles["BodyText"], fontSize=10, leading=13, spaceAfter=7))
    styles.add(ParagraphStyle(name="CrystalJustified", parent=styles["BodyText"], alignment=TA_JUSTIFY, fontSize=9.4, leading=12.6, spaceAfter=9))
    styles.add(ParagraphStyle(name="CrystalSmall", parent=styles["BodyText"], fontSize=6.8, leading=8.2, spaceAfter=0))
    styles.add(ParagraphStyle(name="CrystalFooter", parent=styles["BodyText"], fontSize=7.5, leading=9, spaceAfter=0))

    student = _clean(getattr(row, "Apellidos_nombre", ""))
    cedula = _clean(getattr(row, "Cedula", ""))
    periodo = _clean(getattr(row, "Detalle_Periodo", "")) or _clean(getattr(row, "codperiodo", ""))
    carrera = _clean(getattr(row, "Nombre_Basica", "")) or _clean(getattr(row, "codcarrera", ""))
    alcance = _clean(plan.get("alcance")) or f"{int(plan.get('semestres') or 1)} semestre(s)"
    tipo_beca = _clean(payload.tipo_beca) or "Sin beca"

    story: list[Any] = [
        _SvgLogo(_LOGO_PATH, 4.4 * cm),
        Spacer(1, 0.15 * cm),
        Paragraph("<b>CARTA DE COMPROMISO DE PAGO - ARANCELES</b>", styles["CrystalTitle"]),
        Spacer(1, 0.8 * cm),
        Paragraph("Quito,", styles["CrystalBody"]),
        Spacer(1, 0.25 * cm),
        Paragraph("Señores", styles["CrystalBody"]),
        Spacer(1, 0.18 * cm),
        Paragraph(
            "INSTITUTO SUPERIOR TECNOLOGICO DE TÉCNICAS<br/>"
            "EMPRESARIALES Y DEL CONOCIMIENTO &quot;INTEC&quot;<br/>"
            "Ciudad",
            styles["CrystalBody"],
        ),
        Spacer(1, 0.25 * cm),
        Paragraph("De mis consideraciones:", styles["CrystalBody"]),
        Spacer(1, 3.25 * cm),
    ]

    table = Table(_payment_plan_rows(plan, payload, fecha_pago), colWidths=[2.0 * cm, 7.4 * cm, 4.2 * cm, 2.4 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.85, colors.black),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#bdbdbd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend(
        [
            Paragraph(
                f"<b>Estudiante:</b> {student or '-'} &nbsp;&nbsp; <b>Cédula:</b> {cedula or '-'}<br/>"
                f"<b>Carrera:</b> {carrera or '-'}<br/>"
                f"<b>Período:</b> {periodo or '-'}<br/>"
                f"<b>Alcance del convenio:</b> {alcance} &nbsp;&nbsp; "
                f"<b>Costo por semestre:</b> {_format_money(plan.get('costo_semestre'))} &nbsp;&nbsp; "
                f"<b>Beca:</b> {tipo_beca} ({float(plan.get('porcentaje_beca') or 0):.2f}%)",
                styles["CrystalBody"],
            ),
            Spacer(1, 0.18 * cm),
            table,
            Spacer(1, 0.2 * cm),
            Paragraph(
                '<b>En el caso de que la fecha de pago coincida en fin de semana o feriado, el pago se lo deberá '
                'realizar el siguiente día hábil, mediante transferencia a la Cuenta de Corriente No. 2100297203 '
                'en el Banco Pichincha a nombre del "INTEC" con RUC 1793206794001 y enviar el comprobante por '
                'correo electrónico a <font color="#0066cc">vice.financiero@intec.edu.ec</font></b>',
                styles["CrystalJustified"],
            ),
            Paragraph(
                "Además, estoy plenamente consciente que al suscribir la carta compromiso, asumo las consecuencias "
                "que pueden devenir por el no pago de cada una de las cuotas establecidas; así como, la aplicación "
                "de las medidas académicas por parte de la Institución. También dejo constancia que, al recibir el "
                "beneficio del pago de los valores en cuotas, me será aplicado el recargo del 5% anual si el pago "
                "se realiza con cualquier tarjeta de crédito o débito.",
                styles["CrystalJustified"],
            ),
            Paragraph(
                "Con la firma y rúbrica que ponga en el documento, me doy por notificado que, en caso de "
                "incumplimiento de la obligación contraída, no podré hacer uso de la misma en segunda ocasión.",
                styles["CrystalJustified"],
            ),
            Spacer(1, 0.15 * cm),
            Paragraph("Atentamente,", styles["CrystalBody"]),
            Spacer(1, 4.6 * cm),
            Paragraph("<b>Notas:</b>", styles["CrystalFooter"]),
            Paragraph(
                '• El estudiante podrá enviar la carta de compromiso al correo: '
                '<font color="#0066cc">bienestar@intec.edu.ec</font> y '
                '<font color="#0066cc">vice.financiero@intec.edu.ec</font>',
                styles["CrystalSmall"],
            ),
        ]
    )

    SimpleDocTemplate(
        str(target_path),
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        title=f"Carta compromiso {code}",
    ).build(story)
    return f"/uploads/preinscripcion/{code}/{filename}"


def _split_student_name(full_name: str) -> tuple[str, str, str, str]:
    parts = [part for part in _clean(full_name).upper().split(" ") if part]
    apellido1 = parts[0] if len(parts) > 0 else ""
    apellido2 = parts[1] if len(parts) > 1 else ""
    nombre1 = parts[2] if len(parts) > 2 else ""
    nombre2 = " ".join(parts[3:]) if len(parts) > 3 else ""
    return nombre1[:50], nombre2[:50], apellido1[:50], apellido2[:50]


def _next_preinscription_code(cursor: pyodbc.Cursor, field_name: str) -> int:
    if field_name not in {"Codestu", "num"}:
        raise ValueError('Campo de secuencia inválido')
    cursor.execute(f"SELECT COALESCE(MAX(TRY_CONVERT(int, {field_name})), 0) + 1 FROM dbo.PREINSCRIPCION")
    return int(cursor.fetchone()[0] or 1)


def _default_preinscription_period(cursor: pyodbc.Cursor) -> int:
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, cod_periodo)
        FROM dbo.PERIODO
        WHERE TRY_CONVERT(int, cod_periodo) IS NOT NULL
        ORDER BY COALESCE(TRY_CONVERT(int, anio), 0) DESC, TRY_CONVERT(int, cod_periodo) DESC
        """
    )
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _default_preinscription_career(cursor: pyodbc.Cursor) -> int:
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, Cod_AnioBasica)
        FROM dbo.CARRERAS
        WHERE TRY_CONVERT(int, Cod_AnioBasica) IS NOT NULL
        ORDER BY
            CASE WHEN ISNULL(TRY_CONVERT(nvarchar(20), Estado), N'A') = N'A' THEN 0 ELSE 1 END,
            TRY_CONVERT(nvarchar(4000), Nombre_Basica)
        """
    )
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _resolve_current_asesor(cursor: pyodbc.Cursor, current_user: SessionUser) -> tuple[int, str]:
    if current_user.id_usuario:
        return int(current_user.id_usuario), str(current_user.id_usuario)
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, Codigo_Usuario) AS Codigo_Usuario
        FROM dbo.USUARIOS
        WHERE LOWER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), login)))) = LOWER(LTRIM(RTRIM(?)))
        """,
        current_user.login,
    )
    row = cursor.fetchone()
    if row and row.Codigo_Usuario is not None:
        return int(row.Codigo_Usuario), str(row.Codigo_Usuario)
    return 0, _clean(current_user.login)[:20]


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
        ) base
        """,
        codigo_estud,
        codigo_estud,
    )
    return int(cursor.fetchone()[0] or 1)


def _document_summary(row: Any) -> dict[str, Any]:
    documents = {
        "urlcedula": _document_url(getattr(row, "urlcedula", "")),
        "urltitulo": _document_url(getattr(row, "urltitulo", "")),
        "urldeposito": _document_url(getattr(row, "urldeposito", "")),
        "urlconvenio": _document_url(getattr(row, "urlconvenio", "")),
    }
    required = ("urlcedula", "urltitulo", "urldeposito")
    completed = sum(1 for key in required if documents[key])
    return {
        **documents,
        "total_requeridos": len(required),
        "total_cargados": completed,
        "completos": completed == len(required),
    }


def _ensure_carnet_photo_tables(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.ESTUDIANTE_IMAGEN', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.ESTUDIANTE_IMAGEN(
                id_imagen bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                codigo_estud decimal(18,0) NOT NULL,
                Cedula_Est varchar(50) NOT NULL,
                tipo_imagen varchar(30) NOT NULL,
                titulo nvarchar(150) NULL,
                descripcion nvarchar(500) NULL,
                nombre_original nvarchar(255) NULL,
                ruta_archivo nvarchar(500) NOT NULL,
                mime_type varchar(80) NOT NULL,
                tamanio_bytes bigint NULL,
                es_principal bit NOT NULL CONSTRAINT DF_ESTUDIANTE_IMAGEN_es_principal DEFAULT ((0)),
                estado char(1) NOT NULL CONSTRAINT DF_ESTUDIANTE_IMAGEN_estado DEFAULT ('A'),
                usuario_creacion varchar(100) NULL,
                fecha_creacion datetime2(0) NOT NULL CONSTRAINT DF_ESTUDIANTE_IMAGEN_fecha_creacion DEFAULT (SYSDATETIME()),
                fecha_actualizacion datetime2(0) NULL
            )
        END
        """
    )
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD(
                id_solicitud_foto bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                codigo_estud decimal(18,0) NOT NULL,
                Cedula_Est varchar(50) NOT NULL,
                id_imagen bigint NOT NULL,
                estado varchar(20) NOT NULL CONSTRAINT DF_FOTO_CARNET_SOL_estado DEFAULT ('PENDIENTE'),
                observacion_estudiante nvarchar(500) NULL,
                observacion_admin nvarchar(500) NULL,
                usuario_solicita varchar(100) NULL,
                fecha_solicitud datetime2(0) NOT NULL CONSTRAINT DF_FOTO_CARNET_SOL_fecha DEFAULT (SYSDATETIME()),
                usuario_revisa varchar(100) NULL,
                fecha_revision datetime2(0) NULL
            )
        END
        """
    )
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1
            FROM sys.indexes
            WHERE name = N'IX_FOTO_CARNET_SOL_estudiante'
              AND object_id = OBJECT_ID(N'dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD')
        )
        BEGIN
            CREATE INDEX IX_FOTO_CARNET_SOL_estudiante
            ON dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD(codigo_estud, estado, fecha_solicitud DESC)
        END
        """
    )


def _photo_mime_type(filename: str, upload_mime: str | None) -> str:
    mime_type = _clean(upload_mime).lower()
    if mime_type in set(_PHOTO_MIME_BY_EXTENSION.values()):
        return mime_type
    return _PHOTO_MIME_BY_EXTENSION.get(Path(filename).suffix.lower(), "")


def _fetch_student_for_photo(cursor: pyodbc.Cursor, row: Any) -> Any:
    codigo_estud = _resolve_preinscription_student_code(row)
    cedula = re.sub(r"\D+", "", _clean(getattr(row, "Cedula", "")))
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(int, codigo_estud) AS codigo_estud,
            LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) AS Cedula_Est,
            LTRIM(RTRIM(Apellidos_nombre)) AS Apellidos_nombre
        FROM dbo.DATOS_ESTUD
        WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
           OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) = LTRIM(RTRIM(?))
        ORDER BY
            CASE WHEN TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?) THEN 0 ELSE 1 END,
            codigo_estud DESC
        """,
        codigo_estud,
        cedula,
        codigo_estud,
    )
    student = cursor.fetchone()
    if not student:
        raise HTTPException(
            status_code=400,
            detail="Primero genere la prematrícula para crear al estudiante antes de subir la foto para el carné.",
        )
    return student


def _photo_status_payload(cursor: pyodbc.Cursor, codigo_estud: int | str) -> dict[str, Any]:
    _ensure_carnet_photo_tables(cursor)
    cursor.execute(
        """
        SELECT TOP (1)
            s.id_solicitud_foto,
            s.codigo_estud,
            s.Cedula_Est,
            s.id_imagen,
            s.estado,
            s.observacion_estudiante,
            s.observacion_admin,
            s.usuario_solicita,
            s.fecha_solicitud,
            s.usuario_revisa,
            s.fecha_revision,
            img.ruta_archivo,
            img.nombre_original,
            img.mime_type,
            img.tamanio_bytes,
            img.es_principal
        FROM dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD s
        INNER JOIN dbo.ESTUDIANTE_IMAGEN img ON img.id_imagen = s.id_imagen
        WHERE TRY_CONVERT(varchar(50), s.codigo_estud) = TRY_CONVERT(varchar(50), ?)
        ORDER BY
            CASE s.estado WHEN 'PENDIENTE' THEN 0 WHEN 'APROBADA' THEN 1 ELSE 2 END,
            s.fecha_solicitud DESC
        """,
        codigo_estud,
    )
    row = cursor.fetchone()
    if not row:
        return {
            "existe": False,
            "estado": "SIN_FOTO",
            "mensaje": "No existe una foto para el carné cargada para aprobación.",
        }
    return {
        "existe": True,
        "id_solicitud_foto": _clean(getattr(row, "id_solicitud_foto", "")),
        "codigo_estud": _clean(getattr(row, "codigo_estud", "")),
        "cedula": _clean(getattr(row, "Cedula_Est", "")),
        "id_imagen": _clean(getattr(row, "id_imagen", "")),
        "estado": _clean(getattr(row, "estado", "")) or "PENDIENTE",
        "foto_url": _document_url(getattr(row, "ruta_archivo", "")),
        "nombre_original": _clean(getattr(row, "nombre_original", "")),
        "mime_type": _clean(getattr(row, "mime_type", "")),
        "tamanio_bytes": _int_value(getattr(row, "tamanio_bytes", None)),
        "es_principal": _bool_from_db(getattr(row, "es_principal", None)),
        "observacion_estudiante": _clean(getattr(row, "observacion_estudiante", "")),
        "observacion_admin": _clean(getattr(row, "observacion_admin", "")),
        "usuario_solicita": _clean(getattr(row, "usuario_solicita", "")),
        "fecha_solicitud": _date_text(getattr(row, "fecha_solicitud", "")),
        "usuario_revisa": _clean(getattr(row, "usuario_revisa", "")),
        "fecha_revision": _date_text(getattr(row, "fecha_revision", "")),
    }


def _sync_student_scholarship(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    tipo_beca: str | None,
    porcentaje_beca: float,
    beca_valor: float,
) -> None:
    scholarship_type = _clean(tipo_beca) or ("Sin beca" if float(porcentaje_beca or 0) <= 0 else "PREMATRICULA")
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.Becas', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM dbo.Becas
                WHERE TRY_CONVERT(varchar(50), codestud) = TRY_CONVERT(varchar(50), ?)
            )
            BEGIN
                UPDATE dbo.Becas
                SET porcentaje_beca = ?,
                    valor_monto_beca = ?,
                    tipo_beca = ?
                WHERE TRY_CONVERT(varchar(50), codestud) = TRY_CONVERT(varchar(50), ?)
            END
            ELSE
            BEGIN
                INSERT INTO dbo.Becas (codestud, porcentaje_beca, tipo_beca, valor_monto_beca)
                VALUES (?, ?, ?, ?)
            END
        END
        """,
        str(codigo_estud),
        porcentaje_beca,
        beca_valor,
        scholarship_type,
        str(codigo_estud),
        str(codigo_estud),
        porcentaje_beca,
        scholarship_type,
        beca_valor,
    )


def _finance_scholarship_code(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "", value.upper())
    if "SOCIO" in normalized:
        return "SOCIOECONOMICA"
    if "MERIT" in normalized or "EXCEL" in normalized:
        return "MERITO"
    if "CONVEN" in normalized:
        return "CONVENIO"
    if "DEPORT" in normalized:
        return "DEPORTIVA"
    return "INSTITUCIONAL"


def _sync_financial_preinscription(
    *,
    codestu: int,
    cedula: str,
    student_name: str,
    codperiodo: int,
    codcarrera: int,
    codmodalidad: int,
    codjornada: int,
    correo: str,
    telefono: str,
    codasesor: str,
    usuario: str,
    tipo_beca: str,
    porcentaje_beca: float,
    valor_beca: float,
    motivo_beca: str,
) -> dict[str, Any]:
    scholarship_type, percentage, scholarship_value = _normalized_scholarship(
        tipo_beca, porcentaje_beca, valor_beca
    )

    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                MERGE adm.PreinscripcionFinanciera AS tgt
                USING (SELECT ? AS Cedula, ? AS CodigoPeriodo, ? AS CodigoCarrera) AS src
                   ON tgt.Cedula = src.Cedula
                  AND tgt.CodigoPeriodo = src.CodigoPeriodo
                  AND tgt.CodigoCarrera = src.CodigoCarrera
                WHEN MATCHED THEN UPDATE SET
                    Codestu = ?, ApellidosNombre = ?, CodigoModalidad = ?, CodigoJornada = ?,
                    Correo = ?, Telefono = ?, UsuarioOrigen = ?, CodigoAsesor = ?,
                    ObservacionIngreso = ?, Prematricula = 0, FechaSincronizacion = SYSDATETIME()
                WHEN NOT MATCHED THEN INSERT
                    (Codestu, Cedula, ApellidosNombre, CodigoPeriodo, CodigoCarrera,
                     CodigoModalidad, CodigoJornada, Correo, Telefono, UsuarioOrigen,
                     FechaIngreso, CodigoAsesor, ObservacionIngreso, Prematricula)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSDATETIME(), ?, ?, 0);
                """,
                cedula, str(codperiodo), str(codcarrera),
                codestu, student_name, str(codmodalidad), str(codjornada), correo, telefono,
                usuario, codasesor, "Registro previo creado desde preinscripción",
                codestu, cedula, student_name, str(codperiodo), str(codcarrera),
                str(codmodalidad), str(codjornada), correo, telefono, usuario, codasesor,
                "Registro previo creado desde preinscripción",
            )
            cursor.execute(
                """
                MERGE core.Estudiante AS tgt
                USING (SELECT ? AS NumeroIdentificacion) AS src
                   ON tgt.NumeroIdentificacion = src.NumeroIdentificacion
                WHEN MATCHED THEN UPDATE SET
                    CodigoEstud = COALESCE(tgt.CodigoEstud, ?), NombreCompleto = ?,
                    Correo = ?, Telefono = ?, FuenteOrigen = 'PREINSCRIPCION',
                    FechaSincronizacion = SYSDATETIME()
                WHEN NOT MATCHED THEN INSERT
                    (CodigoEstud, NumeroIdentificacion, NombreCompleto, Correo, Telefono, FuenteOrigen)
                VALUES (?, ?, ?, ?, ?, 'PREINSCRIPCION');
                """,
                cedula, codestu, student_name, correo, telefono,
                codestu, cedula, student_name, correo, telefono,
            )
            cursor.execute(
                "SELECT EstudianteId FROM core.Estudiante WHERE NumeroIdentificacion = ?",
                cedula,
            )
            estudiante_id = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT TOP (1) CuentaEstudianteId
                FROM fin.CuentaEstudiante
                WHERE EstudianteId = ? AND ISNULL(CodigoCarrera, '') = ?
                  AND ISNULL(CodigoPeriodo, '') = ? AND Activo = 1
                """,
                estudiante_id, str(codcarrera), str(codperiodo),
            )
            account_row = cursor.fetchone()
            if account_row:
                cuenta_id = int(account_row[0])
            else:
                cursor.execute(
                    """
                    INSERT INTO fin.CuentaEstudiante
                        (EstudianteId, CodigoCarrera, CodigoPeriodo, UsuarioApertura)
                    OUTPUT INSERTED.CuentaEstudianteId
                    VALUES (?, ?, ?, ?)
                    """,
                    estudiante_id, str(codcarrera), str(codperiodo), usuario,
                )
                cuenta_id = int(cursor.fetchone()[0])

            beca_id: int | None = None
            scholarship_status = "SIN_BECA"
            if scholarship_type and percentage > 0:
                type_code = _finance_scholarship_code(scholarship_type)
                cursor.execute(
                    "SELECT TipoBecaId FROM cat.TipoBeca WHERE Codigo = ? AND Activo = 1",
                    type_code,
                )
                type_row = cursor.fetchone()
                desired_status_code = (
                    "SOLICITADA" if percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD else "APROBADA"
                )
                cursor.execute(
                    "SELECT EstadoBecaId FROM cat.EstadoBeca WHERE Codigo = ? AND Activo = 1",
                    desired_status_code,
                )
                status_row = cursor.fetchone()
                if not type_row or not status_row:
                    raise RuntimeError("No estan configurados los catalogos de beca solicitada")
                cursor.execute(
                    """
                    SELECT TOP (1) b.BecaId, eb.Codigo
                    FROM bec.BecaEstudiante b
                    INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
                    WHERE b.EstudianteId = ? AND b.CuentaEstudianteId = ?
                      AND eb.Codigo IN ('SOLICITADA', 'APROBADA')
                    ORDER BY b.BecaId DESC
                    """,
                    estudiante_id, cuenta_id,
                )
                scholarship_row = cursor.fetchone()
                if scholarship_row:
                    beca_id = int(scholarship_row[0])
                    current_status = _clean(scholarship_row[1]).upper()
                    if percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD and current_status == "APROBADA":
                        cursor.execute(
                            "SELECT EstadoBecaId FROM cat.EstadoBeca WHERE Codigo = 'APROBADA' AND Activo = 1"
                        )
                        approved_status = cursor.fetchone()
                        if approved_status:
                            status_row = approved_status
                            desired_status_code = "APROBADA"
                    cursor.execute(
                        """
                        UPDATE bec.BecaEstudiante
                        SET TipoBecaId = ?, EstadoBecaId = ?, PorcentajeBeca = ?,
                            ValorBeca = ?, Motivo = ?, FechaSolicitud = CAST(GETDATE() AS DATE),
                            FechaAprobacion = CASE WHEN ? = 'APROBADA' THEN COALESCE(FechaAprobacion, CAST(GETDATE() AS DATE)) ELSE NULL END,
                            UsuarioAprobacion = CASE WHEN ? = 'APROBADA' THEN COALESCE(UsuarioAprobacion, ?) ELSE NULL END
                        WHERE BecaId = ?
                        """,
                        int(type_row[0]), int(status_row[0]), percentage, scholarship_value,
                        motivo_beca or f"Solicitud registrada en preinscripción: {scholarship_type}",
                        desired_status_code, desired_status_code, usuario, beca_id,
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO bec.BecaEstudiante
                            (EstudianteId, CuentaEstudianteId, TipoBecaId, EstadoBecaId,
                             CodigoBeca, PorcentajeBeca, ValorBeca, Motivo, FechaSolicitud,
                             FechaAprobacion, UsuarioAprobacion)
                        OUTPUT INSERTED.BecaId
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(GETDATE() AS DATE),
                                CASE WHEN ? = 'APROBADA' THEN CAST(GETDATE() AS DATE) END,
                                CASE WHEN ? = 'APROBADA' THEN ? END)
                        """,
                        estudiante_id, cuenta_id, int(type_row[0]), int(status_row[0]),
                        f"PRE-{codestu}-{codperiodo}", percentage, scholarship_value,
                        motivo_beca or f"Solicitud registrada en preinscripción: {scholarship_type}",
                        desired_status_code, desired_status_code, usuario,
                    )
                    beca_id = int(cursor.fetchone()[0])
                scholarship_status = desired_status_code
            conn.commit()
        requires_approval = percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD
        return {
            "ok": True,
            "cuenta_estudiante_id": cuenta_id,
            "beca_id": beca_id,
            "beca_estado": scholarship_status,
            "requiere_aprobacion": requires_approval,
            "puede_continuar": not requires_approval or scholarship_status == "APROBADA",
            "porcentaje_beca": percentage,
        }
    except (pyodbc.Error, RuntimeError) as exc:
        return {"ok": False, "detail": f"No se pudo sincronizar Finanzas: {exc}"}


def _financial_scholarship_status(cedula: str, codperiodo: Any, codcarrera: Any) -> dict[str, Any]:
    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (1)
                b.BecaId,
                tb.Nombre AS TipoBeca,
                b.PorcentajeBeca,
                b.ValorBeca,
                eb.Codigo AS Estado,
                b.FechaSolicitud,
                b.FechaAprobacion,
                b.UsuarioAprobacion
            FROM core.Estudiante e
            INNER JOIN fin.CuentaEstudiante c ON c.EstudianteId = e.EstudianteId AND c.Activo = 1
            INNER JOIN bec.BecaEstudiante b ON b.EstudianteId = e.EstudianteId
                AND b.CuentaEstudianteId = c.CuentaEstudianteId
            INNER JOIN cat.TipoBeca tb ON tb.TipoBecaId = b.TipoBecaId
            INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
            WHERE e.NumeroIdentificacion = ?
              AND ISNULL(c.CodigoPeriodo, '') = ?
              AND ISNULL(c.CodigoCarrera, '') = ?
            ORDER BY b.BecaId DESC
            """,
            _clean(cedula), _clean(codperiodo), _clean(codcarrera),
        )
        row = cursor.fetchone()
    if not row:
        return {
            "beca_id": None,
            "tipo_beca": "Sin beca",
            "porcentaje_beca": 0.0,
            "valor_beca": 0.0,
            "estado": "SIN_BECA",
            "requiere_aprobacion": False,
            "puede_continuar": True,
        }
    percentage = float(row.PorcentajeBeca or 0)
    status_code = _clean(row.Estado).upper()
    requires_approval = percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD
    return {
        "beca_id": int(row.BecaId),
        "tipo_beca": _clean(row.TipoBeca),
        "porcentaje_beca": percentage,
        "valor_beca": float(row.ValorBeca or 0),
        "estado": status_code,
        "requiere_aprobacion": requires_approval,
        "puede_continuar": not requires_approval or status_code == "APROBADA",
        "fecha_solicitud": _date_text(row.FechaSolicitud),
        "fecha_aprobacion": _date_text(row.FechaAprobacion),
        "usuario_aprobacion": _clean(row.UsuarioAprobacion),
    }


def _preinscription_scholarship_status(row: Any) -> dict[str, Any]:
    if _is_english_career(
        getattr(row, "codcarrera", ""),
        getattr(row, "Nombre_Basica", ""),
    ):
        return {
            "beca_id": None,
            "tipo_beca": "Sin beca",
            "porcentaje_beca": 0.0,
            "valor_beca": 0.0,
            "estado": "NO_APLICA_INGLES",
            "requiere_aprobacion": False,
            "puede_continuar": True,
        }
    return _financial_scholarship_status(
        _clean(getattr(row, "Cedula", "")),
        getattr(row, "codperiodo", ""),
        getattr(row, "codcarrera", ""),
    )


def _approve_financial_scholarship(beca_id: int, usuario: str) -> dict[str, Any]:
    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT b.PorcentajeBeca, eb.Codigo,
                   c.CodigoCarrera,
                   COALESCE(ca.NombreCarrera, c.CodigoCarrera) AS Carrera
            FROM bec.BecaEstudiante b
            INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
            INNER JOIN fin.CuentaEstudiante c ON c.CuentaEstudianteId = b.CuentaEstudianteId
            LEFT JOIN core.Carrera ca ON ca.CodigoCarrera = c.CodigoCarrera
            WHERE b.BecaId = ?
            """,
            beca_id,
        )
        scholarship_row = cursor.fetchone()
        if not scholarship_row:
            raise HTTPException(status_code=404, detail="No existe la solicitud de beca")
        if _is_english_career(scholarship_row.CodigoCarrera, scholarship_row.Carrera):
            raise HTTPException(status_code=400, detail="Las becas no aplican a la carrera de Inglés")
        if float(scholarship_row.PorcentajeBeca or 0) <= _SCHOLARSHIP_APPROVAL_THRESHOLD:
            raise HTTPException(status_code=400, detail="Esta beca no requiere aprobación especial")
        if _clean(scholarship_row.Codigo).upper() == "APROBADA":
            return {"beca_id": beca_id, "estado": "APROBADA", "already_approved": True}

        cursor.execute(
            "SELECT EstadoBecaId FROM cat.EstadoBeca WHERE Codigo = 'APROBADA' AND Activo = 1"
        )
        approved_row = cursor.fetchone()
        if not approved_row:
            raise HTTPException(status_code=500, detail="No está configurado el estado APROBADA en Finanzas")
        cursor.execute(
            """
            UPDATE bec.BecaEstudiante
            SET EstadoBecaId = ?,
                FechaAprobacion = CAST(GETDATE() AS DATE),
                UsuarioAprobacion = ?
            WHERE BecaId = ?
            """,
            int(approved_row[0]),
            usuario[:128],
            beca_id,
        )
        conn.commit()
    return {"beca_id": beca_id, "estado": "APROBADA", "already_approved": False}


def _sync_registration_payment(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    cod_anio_basica: int,
    codigo_periodo: int,
    fecha_pago: str,
    payload: PreinscriptionCabeceraPayload,
    usuario: str,
) -> None:
    num_pago = max(int(payload.num_pago or 1), 1)
    detalle = _clean(payload.detalle_pago) or "Convenio de pago"
    no_deposito = _clean(payload.no_deposito)[:50]
    banco = _clean(payload.banco)[:100]
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.REGISTROPAGOS', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM dbo.REGISTROPAGOS
                WHERE TRY_CONVERT(varchar(50), Codestu) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), codperiodo) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), cod_anio_Basica) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), Num) = TRY_CONVERT(varchar(50), ?)
            )
            BEGIN
                UPDATE dbo.REGISTROPAGOS
                SET fechapago = ?,
                    Detalle = ?,
                    Valor = ?,
                    FechaRegistro = GETDATE(),
                    usuarioreg = ?,
                    NoDeposito = ?,
                    Banco = ?,
                    FechaDeposito = ?,
                    ValorRegistrado = ?
                WHERE TRY_CONVERT(varchar(50), Codestu) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), codperiodo) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), cod_anio_Basica) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), Num) = TRY_CONVERT(varchar(50), ?)
            END
            ELSE
            BEGIN
                INSERT INTO dbo.REGISTROPAGOS (
                    Codestu, Num, codperiodo, cod_anio_Basica, fechapago,
                    Detalle, Valor, FechaRegistro, usuarioreg,
                    NoDeposito, Banco, FechaDeposito, ValorRegistrado
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, ?, ?, ?)
            END
        END
        """,
        codigo_estud,
        codigo_periodo,
        cod_anio_basica,
        num_pago,
        fecha_pago,
        detalle[:500],
        payload.valor,
        usuario[:50],
        no_deposito,
        banco,
        fecha_pago,
        payload.valor,
        codigo_estud,
        codigo_periodo,
        cod_anio_basica,
        num_pago,
        codigo_estud,
        num_pago,
        codigo_periodo,
        cod_anio_basica,
        fecha_pago,
        detalle[:500],
        payload.valor,
        usuario[:50],
        no_deposito,
        banco,
        fecha_pago,
        payload.valor,
    )


def _institutional_email(row: Any, cedula: str) -> str:
    personal_email = _clean(getattr(row, "correo", ""))
    if personal_email.lower().endswith("@intec.edu.ec"):
        return personal_email[:100]
    return f"{cedula}@intec.edu.ec"[:100] if cedula else "pendiente@intec.edu.ec"


def _sync_preinscription_student_records(
    cursor: pyodbc.Cursor,
    row: Any,
    codigo_estud: int,
    codigo_periodo: int,
) -> None:
    cedula = re.sub(r"\D+", "", _clean(getattr(row, "Cedula", "")))[:50]
    student_name = _clean(getattr(row, "Apellidos_nombre", "")).upper()[:100]
    correo = _clean(getattr(row, "correo", ""))[:100]
    telefono = _clean(getattr(row, "telefono", ""))[:60]
    codprov = _int_value(getattr(row, "codprov", None))
    numeric_cedula = _int_value(cedula) or 0

    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, codigo_estud) AS codigo_estud
        FROM dbo.DATOS_ESTUD
        WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
           OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) = LTRIM(RTRIM(?))
        ORDER BY
            CASE WHEN TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?) THEN 0 ELSE 1 END,
            codigo_estud DESC
        """,
        codigo_estud,
        cedula,
        codigo_estud,
    )
    existing_student = cursor.fetchone()
    if existing_student:
        cursor.execute(
            """
            UPDATE dbo.DATOS_ESTUD
            SET Apellidos_nombre = ?,
                correo = COALESCE(NULLIF(?, ''), correo),
                telefono = COALESCE(NULLIF(?, ''), telefono),
                movil = COALESCE(NULLIF(?, ''), movil),
                codprov = COALESCE(?, codprov),
                Estado = COALESCE(NULLIF(Estado, ''), 'A')
            WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
               OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) = LTRIM(RTRIM(?))
            """,
            student_name[:70],
            correo[:80],
            telefono[:30],
            telefono[:15],
            codprov,
            codigo_estud,
            cedula,
        )
    else:
        cursor.execute(
            """
            INSERT INTO dbo.DATOS_ESTUD (
                codigo_estud, Cedula_Est, Apellidos_nombre, codprov, correo,
                telefono, movil, Fecha_Ingreso, EstadoCivil, Etnia, Sexo,
                Cedula, Fotos, Tipodoc, Estado, NumMigracion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 1, 1, 1, ?, 0, 1, 'A', 0)
            """,
            codigo_estud,
            cedula,
            student_name[:70],
            codprov,
            correo[:80],
            telefono[:30],
            telefono[:15],
            numeric_cedula,
        )

    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.DATOSFACTURA', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (
                SELECT 1 FROM dbo.DATOSFACTURA
                WHERE TRY_CONVERT(varchar(50), CODESTUD) = TRY_CONVERT(varchar(50), ?)
                   OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), CEDESTUD))) = LTRIM(RTRIM(?))
            )
            BEGIN
                UPDATE dbo.DATOSFACTURA
                SET CEDESTUD = ?,
                    CEDRUCFACTURA = ?,
                    NOMBRES = ?,
                    TELELFONO = ?,
                    CORREO = ?
                WHERE TRY_CONVERT(varchar(50), CODESTUD) = TRY_CONVERT(varchar(50), ?)
                   OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), CEDESTUD))) = LTRIM(RTRIM(?))
            END
            ELSE
            BEGIN
                INSERT INTO dbo.DATOSFACTURA (CODESTUD, CEDESTUD, CEDRUCFACTURA, NOMBRES, DIRECCION, TELELFONO, CORREO)
                VALUES (?, ?, ?, ?, '', ?, ?)
            END
        END
        """,
        str(codigo_estud)[:10],
        cedula[:10],
        cedula[:10],
        cedula[:15],
        student_name[:100],
        telefono[:60],
        correo[:100],
        str(codigo_estud)[:10],
        cedula[:10],
        str(codigo_estud)[:10],
        cedula[:10],
        cedula[:15],
        student_name[:100],
        telefono[:60],
        correo[:100],
    )

    correo_intec = _institutional_email(row, cedula)
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.CorreosEstudIntec', N'U') IS NOT NULL
        BEGIN
            IF EXISTS (
                SELECT 1 FROM dbo.CorreosEstudIntec
                WHERE TRY_CONVERT(varchar(50), codestud) = TRY_CONVERT(varchar(50), ?)
            )
            BEGIN
                UPDATE dbo.CorreosEstudIntec
                SET Nombres = ?,
                    CorreoPersonal = COALESCE(NULLIF(?, ''), CorreoPersonal),
                    Periodo = ?,
                    Estado = COALESCE(NULLIF(Estado, ''), 'PENDIENTE')
                WHERE TRY_CONVERT(varchar(50), codestud) = TRY_CONVERT(varchar(50), ?)
            END
            ELSE
            BEGIN
                INSERT INTO dbo.CorreosEstudIntec (
                    codestud, Nombres, CorreoPersonal, CorreoIntec, Password,
                    fecha, Periodo, CorreoEnviado, Estado, TipoCursoMigra
                )
                VALUES (?, ?, ?, ?, ?, CAST(GETDATE() AS date), ?, 0, 'PENDIENTE', 'N')
            END
        END
        """,
        codigo_estud,
        student_name[:100],
        correo[:100],
        codigo_periodo,
        codigo_estud,
        codigo_estud,
        student_name[:100],
        correo[:100],
        correo_intec,
        (cedula[-6:] or "CAMBIAR")[:30],
        codigo_periodo,
    )


def _sync_cabecera_documents(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    cod_anio_basica: int,
    codigo_periodo: int,
    documents: dict[str, Any],
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    for field_name, value in documents.items():
        if field_name in _DOCUMENT_FIELDS:
            updates.append(f"{field_name} = ?")
            params.append(_document_url(value))
    if not updates:
        return
    params.extend([codigo_estud, cod_anio_basica, codigo_periodo])
    cursor.execute(
        f"""
        UPDATE dbo.CABECERA_MATRICULA
        SET {", ".join(updates)}
        WHERE codigo_estud = ?
          AND cod_anio_Basica = ?
          AND codigo_periodo = ?
        """,
        *params,
    )


def _preinscription_item(row: Any) -> dict[str, Any]:
    documents = _document_summary(row)
    en_cabecera = bool(getattr(row, "cabecera_codigo_estud", None))
    return {
        "num": _clean(getattr(row, "num", "")),
        "codestu": _clean(getattr(row, "Codestu", "")),
        "datos_codigo_estud": _clean(getattr(row, "datos_codigo_estud", "")),
        "cedula": _clean(getattr(row, "Cedula", "")),
        "apellidos_nombre": _clean(getattr(row, "Apellidos_nombre", "")),
        "codperiodo": _clean(getattr(row, "codperiodo", "")),
        "periodo": _clean(getattr(row, "Detalle_Periodo", "")),
        "correo": _clean(getattr(row, "correo", "")),
        "telefono": _clean(getattr(row, "telefono", "")),
        "usuario": _clean(getattr(row, "Usuario", "")),
        "fecha_ingreso": _date_text(getattr(row, "Fecha_Ingreso", "")),
        "codprov": _clean(getattr(row, "codprov", "")),
        "codcarrera": _clean(getattr(row, "codcarrera", "")),
        "carrera": _clean(getattr(row, "Nombre_Basica", "")),
        "codmodalida": _clean(getattr(row, "codmodalida", "")),
        "codjornada": _int_value(getattr(row, "codjornada", None)),
        "contacte": _clean(getattr(row, "contacte", "")),
        "hora": _clean(getattr(row, "hora", "")),
        "codasesor": _clean(getattr(row, "codasesor", "")),
        "observacion_contacto": _clean(getattr(row, "Observacioncontacto", "")),
        "observacion_ingreso": _clean(getattr(row, "ObservacionIngreso", "")),
        "cod_lecontacto": _clean(getattr(row, "codLecontacto", "")),
        "cod_desea_ingresar": _clean(getattr(row, "codDeseaIngresar", "")),
        "prematricula": _bool_from_db(getattr(row, "Prematricula", None)),
        "cod_como_conoce": _clean(getattr(row, "codComoConoce", "")),
        "coddescconve": _clean(getattr(row, "coddescconve", "")),
        "coddescconvevalor": _number_value(getattr(row, "coddescconvevalor", None)),
        "coddescdeptransf": _clean(getattr(row, "coddescdeptransf", "")),
        "correo_enviado": _bool_from_db(getattr(row, "Correoenviado", None)),
        "asignado": _bool_from_db(getattr(row, "asignado", None)),
        "nombre1": _clean(getattr(row, "Nombre1", "")),
        "nombre2": _clean(getattr(row, "Nombre2", "")),
        "apellido1": _clean(getattr(row, "Apellido1", "")),
        "apellido2": _clean(getattr(row, "Apellido2", "")),
        "proceso_finalizado": _bool_from_db(getattr(row, "ProcesoFinalilzado", None)),
        "control_ingreso": _bool_from_db(getattr(row, "ControlIngreso", None)),
        "nom_representante": _clean(getattr(row, "Nom_Representante", "")),
        "num_representante": _clean(getattr(row, "Num_Representante", "")),
        "documentos": documents,
        "en_cabecera_matricula": en_cabecera,
        "cabecera": {
            "codigo_estud": _clean(getattr(row, "cabecera_codigo_estud", "")),
            "cod_anio_basica": _clean(getattr(row, "cabecera_cod_anio_basica", "")),
            "codigo_periodo": _clean(getattr(row, "cabecera_codigo_periodo", "")),
            "num_matricula": _clean(getattr(row, "cabecera_num_matricula", "")),
            "numcodigo": _clean(getattr(row, "cabecera_numcodigo", "")),
            "fecha_pago": _date_text(getattr(row, "cabecera_fecha_pago", "")),
            "valor": _number_value(getattr(row, "cabecera_valor", None)),
            "inscrip_valor": _number_value(getattr(row, "cabecera_inscrip_valor", None)),
            "matri_valor": _number_value(getattr(row, "cabecera_matri_valor", None)),
            "cuota1": _number_value(getattr(row, "cabecera_cuota1", None)),
            "beca": _number_value(getattr(row, "cabecera_beca", None)),
            "descuento": _number_value(getattr(row, "cabecera_descuento", None)),
            "tipo_beca": _clean(getattr(row, "cabecera_tipo_beca", "")),
            "porcentaje_beca": _number_value(getattr(row, "cabecera_porcentaje_beca", None)),
            "num_pago": _int_value(getattr(row, "pago_num", None)),
            "detalle_pago": _clean(getattr(row, "pago_detalle", "")),
            "no_deposito": _clean(getattr(row, "pago_no_deposito", "")),
            "banco": _clean(getattr(row, "pago_banco", "")),
            "valor_registrado": _number_value(getattr(row, "pago_valor_registrado", None)),
            "control_matricula": _int_value(getattr(row, "cabecera_control_matricula", None)),
        },
    }


def _base_preinscription_select(where_sql: str = "") -> str:
    return f"""
        SELECT
            p.Codestu,
            p.Cedula,
            p.Apellidos_nombre,
            p.codperiodo,
            pe.Detalle_Periodo,
            p.correo,
            p.telefono,
            p.Usuario,
            p.Fecha_Ingreso,
            p.codprov,
            p.codcarrera,
            c.Nombre_Basica,
            p.codmodalida,
            p.codjornada,
            p.contacte,
            p.hora,
            p.codasesor,
            p.Observacioncontacto,
            p.ObservacionIngreso,
            p.codLecontacto,
            p.codDeseaIngresar,
            p.Prematricula,
            p.codComoConoce,
            p.coddescconve,
            p.coddescconvevalor,
            p.coddescdeptransf,
            p.num,
            p.urlcedula,
            p.urltitulo,
            p.urldeposito,
            p.urlconvenio,
            p.Correoenviado,
            p.asignado,
            p.Nombre1,
            p.Nombre2,
            p.Apellido1,
            p.Apellido2,
            p.ProcesoFinalilzado,
            p.ControlIngreso,
            p.Nom_Representante,
            p.Num_Representante,
            d.codigo_estud AS datos_codigo_estud,
            cm.codigo_estud AS cabecera_codigo_estud,
            cm.cod_anio_Basica AS cabecera_cod_anio_basica,
            cm.codigo_periodo AS cabecera_codigo_periodo,
            cm.Num_Matricula AS cabecera_num_matricula,
            cm.numcodigo AS cabecera_numcodigo,
            cm.fecha_pago AS cabecera_fecha_pago,
            cm.valor AS cabecera_valor,
            cm.InscripValor AS cabecera_inscrip_valor,
            cm.MatriValor AS cabecera_matri_valor,
            cm.Cuota1 AS cabecera_cuota1,
            cm.Beca AS cabecera_beca,
            cm.Descuento AS cabecera_descuento,
            bec.tipo_beca AS cabecera_tipo_beca,
            bec.porcentaje_beca AS cabecera_porcentaje_beca,
            rp.Num AS pago_num,
            rp.Detalle AS pago_detalle,
            rp.NoDeposito AS pago_no_deposito,
            rp.Banco AS pago_banco,
            rp.ValorRegistrado AS pago_valor_registrado,
            cm.ControlMatricula AS cabecera_control_matricula
        FROM dbo.PREINSCRIPCION p
        LEFT JOIN dbo.PERIODO pe ON pe.cod_periodo = p.codperiodo
        LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = p.codcarrera
        OUTER APPLY (
            SELECT TOP (1) d.codigo_estud
            FROM dbo.DATOS_ESTUD d
            WHERE TRY_CONVERT(varchar(50), d.codigo_estud) = TRY_CONVERT(varchar(50), p.Codestu)
               OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Cedula_Est))) = LTRIM(RTRIM(TRY_CONVERT(varchar(50), p.Cedula)))
            ORDER BY
                CASE
                    WHEN TRY_CONVERT(varchar(50), d.codigo_estud) = TRY_CONVERT(varchar(50), p.Codestu) THEN 0
                    ELSE 1
                END,
                d.codigo_estud DESC
        ) d
        OUTER APPLY (
            SELECT TOP (1) cab.*
            FROM dbo.CABECERA_MATRICULA cab
            WHERE TRY_CONVERT(varchar(50), cab.codigo_estud) = COALESCE(
                    TRY_CONVERT(varchar(50), d.codigo_estud),
                    TRY_CONVERT(varchar(50), p.Codestu)
                )
              AND TRY_CONVERT(varchar(50), cab.codigo_periodo) = TRY_CONVERT(varchar(50), p.codperiodo)
              AND TRY_CONVERT(varchar(50), cab.cod_anio_Basica) = TRY_CONVERT(varchar(50), p.codcarrera)
            ORDER BY
                TRY_CONVERT(int, cab.Num_Matricula) DESC,
                cab.fecha_pago DESC
        ) cm
        OUTER APPLY (
            SELECT TOP (1) b.tipo_beca, b.porcentaje_beca
            FROM dbo.Becas b
            WHERE TRY_CONVERT(varchar(50), b.codestud) = COALESCE(
                    TRY_CONVERT(varchar(50), cm.codigo_estud),
                    TRY_CONVERT(varchar(50), d.codigo_estud),
                    TRY_CONVERT(varchar(50), p.Codestu)
                )
        ) bec
        OUTER APPLY (
            SELECT TOP (1) pay.*
            FROM dbo.REGISTROPAGOS pay
            WHERE TRY_CONVERT(varchar(50), pay.Codestu) = COALESCE(
                    TRY_CONVERT(varchar(50), cm.codigo_estud),
                    TRY_CONVERT(varchar(50), d.codigo_estud),
                    TRY_CONVERT(varchar(50), p.Codestu)
                )
              AND TRY_CONVERT(varchar(50), pay.codperiodo) = TRY_CONVERT(varchar(50), p.codperiodo)
              AND TRY_CONVERT(varchar(50), pay.cod_anio_Basica) = TRY_CONVERT(varchar(50), p.codcarrera)
            ORDER BY pay.fechapago DESC, pay.FechaRegistro DESC
        ) rp
        {where_sql}
    """


def _matches_document_filter(item: dict[str, Any], document_filter: str) -> bool:
    if document_filter == "ALL":
        return True
    if document_filter == "PENDIENTES":
        return not bool(item["documentos"]["completos"])
    if document_filter == "COMPLETOS":
        return bool(item["documentos"]["completos"])
    if document_filter == "CON_CABECERA":
        return bool(item["en_cabecera_matricula"])
    if document_filter == "SIN_CABECERA":
        return not bool(item["en_cabecera_matricula"])
    return True


def _preinscription_totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "con_cabecera": sum(1 for item in items if item["en_cabecera_matricula"]),
        "sin_cabecera": sum(1 for item in items if not item["en_cabecera_matricula"]),
        "documentos_completos": sum(1 for item in items if item["documentos"]["completos"]),
        "documentos_pendientes": sum(1 for item in items if not item["documentos"]["completos"]),
    }


def _preinscription_user_total(
    items: list[dict[str, Any]],
    current_user: SessionUser,
    codasesor: int,
    usuario: str,
) -> int:
    asesor_tokens = {str(value).strip() for value in (codasesor, current_user.id_usuario) if value not in (None, "")}
    usuario_tokens = {
        _clean(value).upper()
        for value in (usuario, current_user.login, current_user.nombres, current_user.email)
        if _clean(value)
    }

    total = 0
    for item in items:
        item_codasesor = _clean(item.get("codasesor"))
        item_usuario = _clean(item.get("usuario")).upper()
        if (item_codasesor and item_codasesor in asesor_tokens) or (item_usuario and item_usuario in usuario_tokens):
            total += 1
    return total


def _fetch_preinscription_row(cursor: pyodbc.Cursor, num: str) -> Any:
    cursor.execute(
        _base_preinscription_select("WHERE TRY_CONVERT(varchar(50), p.num) = ?"),
        num,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='No se encontró la preinscripción seleccionada')
    return row


def _resolve_preinscription_student_code(row: Any) -> int:
    code = _int_value(getattr(row, "datos_codigo_estud", None)) or _int_value(getattr(row, "Codestu", None))
    if not code:
        raise HTTPException(
            status_code=400,
            detail='La preinscripción no tiene código de estudiante válido para crear cabecera',
        )
    return code


def _resolve_preinscription_required_code(row: Any, field_name: str, label: str) -> int:
    code = _int_value(getattr(row, field_name, None))
    if not code:
        raise HTTPException(status_code=400, detail=f"La preinscripción no tiene {label} válido.")
    return code


def _cabecera_response_from_row(row: Any) -> dict[str, Any]:
    item = _preinscription_item(row)
    codigo_documentacion = item["cabecera"].get("numcodigo") or item["cabecera"].get("num_matricula") or ""
    return {
        "ok": True,
        "item": item,
        "cabecera": item["cabecera"],
        "num_matricula": item["cabecera"].get("num_matricula") or "",
        "codigo_documentacion": codigo_documentacion,
        "convenio_url": item["documentos"].get("urlconvenio") or "",
    }


@router.get("/catalog")
def preinscription_catalog(
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (120)
                    pe.cod_periodo,
                    pe.Detalle_Periodo,
                    pe.Estado,
                    pe.Periodo,
                    pe.anio,
                    COUNT(p.num) AS total_preinscripciones
                FROM dbo.PERIODO pe
                LEFT JOIN dbo.PREINSCRIPCION p ON pe.cod_periodo = p.codperiodo
                GROUP BY pe.cod_periodo, pe.Detalle_Periodo, pe.Estado, pe.Periodo, pe.anio
                ORDER BY COALESCE(pe.anio, 0) DESC, pe.cod_periodo DESC
                """
            )
            periodos = [
                {
                    "codigo_periodo": _clean(row.cod_periodo),
                    "detalle_periodo": _clean(row.Detalle_Periodo),
                    "estado": _clean(row.Estado),
                    "periodo": _clean(row.Periodo),
                    "anio": _int_value(row.anio),
                    "total_preinscripciones": int(row.total_preinscripciones or 0),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    c.Cod_AnioBasica,
                    c.Nombre_Basica,
                    c.Estado,
                    c.Abrevia,
                    c.tp_escuela,
                    costs.semestres_disponibles,
                    costs.costo_presencial_total,
                    costs.costo_virtual_total,
                    costs.costo_presencial_semestre,
                    costs.costo_virtual_semestre,
                    COUNT(p.num) AS total_preinscripciones
                FROM dbo.CARRERAS c
                LEFT JOIN dbo.PREINSCRIPCION p ON c.Cod_AnioBasica = p.codcarrera
                OUTER APPLY (
                    SELECT
                        COUNT(DISTINCT TRY_CONVERT(int, pen.Semestre)) AS semestres_disponibles,
                        SUM(COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0)) AS costo_presencial_total,
                        SUM(COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHoraVirtual), TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0)) AS costo_virtual_total,
                        SUM(CASE WHEN TRY_CONVERT(int, pen.Semestre) = 1 THEN COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0) ELSE 0 END) AS costo_presencial_semestre,
                        SUM(CASE WHEN TRY_CONVERT(int, pen.Semestre) = 1 THEN COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHoraVirtual), TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0) ELSE 0 END) AS costo_virtual_semestre
                    FROM dbo.PENSUM pen
                    WHERE TRY_CONVERT(varchar(50), pen.Cod_AnioBasica) = TRY_CONVERT(varchar(50), c.Cod_AnioBasica)
                      AND TRY_CONVERT(int, pen.Semestre) BETWEEN 1 AND 4
                ) costs
                GROUP BY
                    c.Cod_AnioBasica, c.Nombre_Basica, c.Estado, c.Abrevia, c.tp_escuela,
                    costs.semestres_disponibles, costs.costo_presencial_total, costs.costo_virtual_total,
                    costs.costo_presencial_semestre, costs.costo_virtual_semestre
                ORDER BY c.Nombre_Basica
                """
            )
            carreras = [
                {
                    "cod_anio_basica": _clean(row.Cod_AnioBasica),
                    "nombre_basica": _clean(row.Nombre_Basica) or "Sin carrera",
                    "estado": _clean(row.Estado),
                    "abrevia": _clean(row.Abrevia),
                    "tipo_escuela": _clean(row.tp_escuela),
                    "semestres_disponibles": _int_value(row.semestres_disponibles) or 0,
                    "costo_presencial_total": _number_value(row.costo_presencial_total) or 0,
                    "costo_virtual_total": _number_value(row.costo_virtual_total) or 0,
                    "costo_presencial_semestre": _number_value(row.costo_presencial_semestre) or 0,
                    "costo_virtual_semestre": _number_value(row.costo_virtual_semestre) or 0,
                    "total_preinscripciones": int(row.total_preinscripciones or 0),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), Cod_Provincia) AS Cod_Provincia,
                    TRY_CONVERT(nvarchar(255), Descripcion_Prov) AS Descripcion_Prov
                FROM dbo.Provincias
                WHERE ISNULL(activo, 1) = 1
                ORDER BY TRY_CONVERT(nvarchar(255), Descripcion_Prov)
                """
            )
            provincias = [
                {
                    "codprov": _clean(row.Cod_Provincia),
                    "descripcion": _clean(row.Descripcion_Prov),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), Num_Le) AS option_value,
                    TRY_CONVERT(nvarchar(255), Lecontacto) AS option_label
                FROM dbo.IN_LECONTACTO
                ORDER BY TRY_CONVERT(nvarchar(255), Lecontacto)
                """
            )
            le_contactos = [{"value": _clean(row.option_value), "label": _clean(row.option_label)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), Num_Deseaing) AS option_value,
                    TRY_CONVERT(nvarchar(255), DeseaIngresar) AS option_label
                FROM dbo.IN_DESEAINGRESAR
                ORDER BY TRY_CONVERT(nvarchar(255), DeseaIngresar)
                """
            )
            desea_ingresar = [{"value": _clean(row.option_value), "label": _clean(row.option_label)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), Num_Entero) AS option_value,
                    TRY_CONVERT(nvarchar(255), detalleentero) AS option_label
                FROM dbo.IN_ENTERO
                ORDER BY TRY_CONVERT(nvarchar(255), detalleentero)
                """
            )
            como_conoce = [{"value": _clean(row.option_value), "label": _clean(row.option_label)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), NumDesConv) AS option_value,
                    TRY_CONVERT(nvarchar(255), DetalleDesConve) AS option_label,
                    TRY_CONVERT(nvarchar(50), Porcentaje) AS detail
                FROM dbo.IN_DESCCONVE
                ORDER BY TRY_CONVERT(nvarchar(255), DetalleDesConve)
                """
            )
            descuentos_convenio = [
                {"value": _clean(row.option_value), "label": _clean(row.option_label), "detail": _clean(row.detail)}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), numDesConvValor) AS option_value,
                    TRY_CONVERT(decimal(18, 2), DetalleDescConveValor) AS amount,
                    TRY_CONVERT(nvarchar(20), NumDesConv) AS parent,
                    TRY_CONVERT(nvarchar(20), CodModalidaMatricula) AS modalidad
                FROM dbo.IN_DESCONVVALOR
                ORDER BY TRY_CONVERT(decimal(18, 2), DetalleDescConveValor)
                """
            )
            descuentos_valores = [
                {
                    "value": _clean(row.option_value),
                    "label": _clean(row.amount),
                    "amount": _number_value(row.amount),
                    "parent": _clean(row.parent),
                    "modalidad": _clean(row.modalidad),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), num) AS option_value,
                    TRY_CONVERT(decimal(18, 2), valordescdeptrs) AS amount,
                    TRY_CONVERT(nvarchar(20), CodModalidaMatricula) AS modalidad
                FROM dbo.IN_DESDEPOTRANS
                ORDER BY TRY_CONVERT(decimal(18, 2), valordescdeptrs)
                """
            )
            descuentos_deposito = [
                {
                    "value": _clean(row.option_value),
                    "label": _clean(row.amount),
                    "amount": _number_value(row.amount),
                    "modalidad": _clean(row.modalidad),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(varchar(50), pen.Cod_AnioBasica) AS cod_anio_basica,
                    TRY_CONVERT(int, pen.Semestre) AS semestre,
                    SUM(COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0)) AS costo_presencial,
                    SUM(COALESCE(TRY_CONVERT(decimal(18, 2), pen.ValorHoraVirtual), TRY_CONVERT(decimal(18, 2), pen.ValorHora), 0)) AS costo_virtual
                FROM dbo.PENSUM pen
                WHERE TRY_CONVERT(int, pen.Semestre) BETWEEN 1 AND 4
                  AND TRY_CONVERT(varchar(50), pen.Cod_AnioBasica) IS NOT NULL
                GROUP BY TRY_CONVERT(varchar(50), pen.Cod_AnioBasica), TRY_CONVERT(int, pen.Semestre)
                ORDER BY TRY_CONVERT(varchar(50), pen.Cod_AnioBasica), TRY_CONVERT(int, pen.Semestre)
                """
            )
            costs_by_career: dict[str, list[dict[str, Any]]] = {}
            for row in cursor.fetchall():
                career_key = _clean(row.cod_anio_basica)
                if not career_key:
                    continue
                costs_by_career.setdefault(career_key, []).append(
                    {
                        "semestre": _int_value(row.semestre) or 0,
                        "presencial": _number_value(row.costo_presencial) or 0,
                        "virtual": _number_value(row.costo_virtual) or 0,
                    }
                )
            for career in carreras:
                career["costos_semestres"] = costs_by_career.get(career["cod_anio_basica"], [])
            cursor.execute(
                """
                IF OBJECT_ID(N'dbo.Becas', N'U') IS NOT NULL
                BEGIN
                    SELECT TOP (120)
                        TRY_CONVERT(nvarchar(255), NULLIF(LTRIM(RTRIM(tipo_beca)), '')) AS option_value,
                        TRY_CONVERT(decimal(18, 2), MIN(ISNULL(porcentaje_beca, 0))) AS min_amount,
                        TRY_CONVERT(decimal(18, 2), MAX(ISNULL(porcentaje_beca, 0))) AS max_amount
                    FROM dbo.Becas
                    WHERE NULLIF(LTRIM(RTRIM(tipo_beca)), '') IS NOT NULL
                    GROUP BY TRY_CONVERT(nvarchar(255), NULLIF(LTRIM(RTRIM(tipo_beca)), ''))
                    ORDER BY TRY_CONVERT(nvarchar(255), NULLIF(LTRIM(RTRIM(tipo_beca)), ''))
                END
                ELSE
                BEGIN
                    SELECT TOP (0)
                        TRY_CONVERT(nvarchar(255), '') AS option_value,
                        TRY_CONVERT(decimal(18, 2), 0) AS min_amount,
                        TRY_CONVERT(decimal(18, 2), 0) AS max_amount
                END
                """
            )
            becas = []
            for row in cursor.fetchall():
                scholarship_name = _clean(row.option_value)
                if not scholarship_name:
                    continue
                minimum = _number_value(row.min_amount) or 0
                maximum = _number_value(row.max_amount) or 0
                is_mintel = _is_mintel_scholarship(scholarship_name)
                is_variable = not is_mintel and abs(maximum - minimum) > 0.001
                fixed_amount = 100.0 if is_mintel else maximum
                becas.append(
                    {
                        "value": scholarship_name,
                        "label": scholarship_name,
                        "detail": "Fija 100%" if is_mintel else (f"Variable ({minimum:g}% - {maximum:g}%)" if is_variable else f"{maximum:g}%"),
                        "amount": None if is_variable else fixed_amount,
                        "variable": is_variable,
                        "min_amount": fixed_amount if is_mintel else minimum,
                        "max_amount": fixed_amount if is_mintel else maximum,
                    }
                )
            cursor.execute(
                """
                SELECT
                    TRY_CONVERT(nvarchar(20), NumM) AS option_value,
                    TRY_CONVERT(nvarchar(255), DetalleM) AS option_label
                FROM dbo.ModalidadMatricula
                ORDER BY TRY_CONVERT(nvarchar(255), DetalleM)
                """
            )
            modalidades = [{"value": _clean(row.option_value), "label": _clean(row.option_label)} for row in cursor.fetchall()]
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
            jornadas = [
                {
                    "value": _clean(row.option_value),
                    "label": _clean(row.option_label),
                    "modalidad": _clean(row.modalidad),
                }
                for row in cursor.fetchall()
            ]
        try:
            with get_finance_connection() as finance_conn:
                finance_cursor = finance_conn.cursor()
                finance_cursor.execute(
                    "SELECT Codigo, Nombre FROM cat.TipoBeca WHERE Activo = 1 ORDER BY Nombre"
                )
                known_scholarships = {_clean(option["value"]).upper() for option in becas}
                for row in finance_cursor.fetchall():
                    code = _clean(row.Codigo)
                    name = _clean(row.Nombre)
                    if code and code.upper() not in known_scholarships:
                        becas.append(
                            {
                                "value": code,
                                "label": name or code,
                                "detail": "Porcentaje variable",
                                "amount": None,
                                "variable": True,
                            }
                        )
                        known_scholarships.add(code.upper())
        except (pyodbc.Error, RuntimeError):
            pass
        try:
            managed_scholarships = _scholarship_configurations(active_only=True)
            if managed_scholarships:
                becas = [
                    {
                        "value": item["nombre"],
                        "label": item["nombre"],
                        "detail": (
                            f"Variable ({float(item['porcentaje_minimo'] or 0):g}% - {float(item['porcentaje_maximo'] or 100):g}%)"
                            if item["es_variable"]
                            else f"Fija {float(item['porcentaje'] or 0):g}%"
                        ),
                        "amount": None if item["es_variable"] else item["porcentaje"],
                        "variable": item["es_variable"],
                        "min_amount": item["porcentaje_minimo"],
                        "max_amount": item["porcentaje_maximo"],
                    }
                    for item in managed_scholarships
                ]
        except (pyodbc.Error, RuntimeError):
            pass
        return {
            "periodos": periodos,
            "carreras": carreras,
            "provincias": provincias,
            "modalidades": modalidades,
            "jornadas": jornadas,
            "le_contactos": le_contactos,
            "desea_ingresar": desea_ingresar,
            "como_conoce": como_conoce,
            "descuentos_convenio": descuentos_convenio,
            "descuentos_valores": descuentos_valores,
            "descuentos_deposito": descuentos_deposito,
            "becas": becas,
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error al consultar el catálogo de preinscripción: {exc}") from exc


@router.get("")
def preinscription_list(
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
    query: str = "",
    codigo_periodo: str = "",
    cod_anio_basica: str = "",
    documentos: Annotated[str, Query(description="ALL, PENDIENTES, COMPLETOS, CON_CABECERA, SIN_CABECERA")] = "ALL",
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict[str, Any]:
    document_filter = documentos.strip().upper() or "ALL"
    if document_filter not in _DOCUMENT_FILTERS:
        raise HTTPException(status_code=400, detail='Filtro de documentos inválido')

    where_parts: list[str] = []
    params: list[Any] = []
    search = query.strip()
    if search:
        like = f"%{search}%"
        digits = re.sub(r"\D+", "", search)
        where_parts.append(
            """
            (
                p.Apellidos_nombre LIKE ?
                OR TRY_CONVERT(varchar(50), p.Cedula) LIKE ?
                OR p.correo LIKE ?
                OR TRY_CONVERT(varchar(50), p.Codestu) = ?
                OR (? <> '' AND TRY_CONVERT(varchar(50), p.Cedula) LIKE ?)
            )
            """
        )
        params.extend([like, like, like, search, digits, f"%{digits}%"])
    if codigo_periodo:
        where_parts.append("TRY_CONVERT(varchar(50), p.codperiodo) = ?")
        params.append(codigo_periodo)
    if cod_anio_basica:
        where_parts.append("TRY_CONVERT(varchar(50), p.codcarrera) = ?")
        params.append(cod_anio_basica)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sql = (
        f"SELECT TOP ({limit}) * FROM ("
        + _base_preinscription_select(where_sql)
        + ") base_preinscripcion ORDER BY Fecha_Ingreso DESC, Apellidos_nombre"
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            raw_items = [_preinscription_item(row) for row in cursor.fetchall()]
            codasesor, usuario = _resolve_current_asesor(cursor, current_user)
        items = [item for item in raw_items if _matches_document_filter(item, document_filter)]
        totals = _preinscription_totals(items)
        current_user_total = _preinscription_user_total(items, current_user, codasesor, usuario)
        totals["mis_registros"] = current_user_total
        totals["usuario_actual"] = current_user_total
        return {
            "total": len(items),
            "items": items,
            "totals": totals,
            "criteria": {
                "query": search,
                "codigo_periodo": codigo_periodo,
                "cod_anio_basica": cod_anio_basica,
                "documentos": document_filter,
                "link_cabecera": "PREINSCRIPCION.Codestu/Cedula + codperiodo + codcarrera -> CABECERA_MATRICULA",
            },
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando preinscripciones: {exc}") from exc


@router.get("/validar-cedula")
def validate_preinscription_cedula(
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
    cedula: Annotated[str, Query(min_length=1)] = "",
    codigo_periodo: Annotated[str, Query()] = "",
) -> dict[str, Any]:
    del current_user
    clean_cedula = re.sub(r"\D+", "", _clean(cedula))
    clean_periodo = _clean(codigo_periodo)
    if len(clean_cedula) != 10:
        raise HTTPException(status_code=400, detail='La cédula debe tener 10 dígitos')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            where_period = "AND TRY_CONVERT(varchar(50), codperiodo) = ?" if clean_periodo else ""
            params: list[Any] = [clean_cedula]
            if clean_periodo:
                params.append(clean_periodo)
            cursor.execute(
                f"""
                SELECT TOP (1)
                    TRY_CONVERT(varchar(50), num) AS num,
                    TRY_CONVERT(varchar(50), Codestu) AS codestu,
                    TRY_CONVERT(varchar(50), Cedula) AS cedula,
                    TRY_CONVERT(varchar(200), Apellidos_nombre) AS apellidos_nombre,
                    TRY_CONVERT(varchar(50), codperiodo) AS codperiodo,
                    TRY_CONVERT(varchar(50), codcarrera) AS codcarrera,
                    Fecha_Ingreso
                FROM dbo.PREINSCRIPCION
                WHERE LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula))) = ?
                  {where_period}
                ORDER BY Fecha_Ingreso DESC
                """,
                *params,
            )
            row = cursor.fetchone()
        if not row:
            return {"exists": False, "message": ""}
        return {
            "exists": True,
            "message": "estudiante inscrito",
            "item": {
                "num": _clean(getattr(row, "num", "")),
                "codestu": _clean(getattr(row, "codestu", "")),
                "cedula": _clean(getattr(row, "cedula", "")),
                "apellidos_nombre": _clean(getattr(row, "apellidos_nombre", "")),
                "codperiodo": _clean(getattr(row, "codperiodo", "")),
                "codcarrera": _clean(getattr(row, "codcarrera", "")),
                "fecha_ingreso": _iso_date(getattr(row, "Fecha_Ingreso", None)),
            },
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error al validar la cédula: {exc}") from exc


@router.post("")
def create_preinscription(
    payload: PreinscriptionCreatePayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    apellidos = _clean(payload.apellidos)
    nombres = _clean(payload.nombres)
    student_name = _clean(payload.apellidos_nombre)
    if not student_name and (apellidos or nombres):
        student_name = _clean(f"{apellidos} {nombres}")
    student_name = student_name.upper()
    cedula = re.sub(r"\D+", "", _clean(payload.cedula))
    if not student_name:
        raise HTTPException(status_code=400, detail='Ingrese el nombre del estudiante')
    if len(cedula) != 10:
        raise HTTPException(status_code=400, detail='La cédula debe tener 10 dígitos')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            codprov = _int_value(payload.codprov)
            if codprov is None:
                raise HTTPException(status_code=400, detail='Seleccione una provincia válida')
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.Provincias WHERE TRY_CONVERT(int, Cod_Provincia) = ? AND ISNULL(activo, 1) = 1",
                codprov,
            )
            if int(cursor.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=400, detail="La provincia seleccionada no existe")

            codperiodo = _int_value(payload.codperiodo) or _default_preinscription_period(cursor)
            codcarrera = _int_value(payload.codcarrera) or _default_preinscription_career(cursor)
            if not codperiodo:
                raise HTTPException(status_code=400, detail='No se pudo resolver el período de preinscripción')
            if not codcarrera:
                raise HTTPException(status_code=400, detail='No se pudo resolver la carrera de preinscripción')

            cursor.execute(
                """
                SELECT TOP (1) TRY_CONVERT(varchar(50), num) AS num
                FROM dbo.PREINSCRIPCION
                WHERE LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula))) = ?
                  AND TRY_CONVERT(varchar(50), codperiodo) = TRY_CONVERT(varchar(50), ?)
                ORDER BY Fecha_Ingreso DESC
                """,
                cedula,
                codperiodo,
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="estudiante inscrito")

            codestu = _next_preinscription_code(cursor, "Codestu")
            num = _next_preinscription_code(cursor, "num")
            codasesor, usuario = _resolve_current_asesor(cursor, current_user)
            nombre1, nombre2, apellido1, apellido2 = _split_student_name(student_name)

            cursor.execute(
                """
                INSERT INTO dbo.PREINSCRIPCION (
                    Codestu, Cedula, Apellidos_nombre, codperiodo, correo, telefono,
                    Usuario, Fecha_Ingreso, codprov, codcarrera, codmodalida, codjornada,
                    contacte, hora, codasesor, Observacioncontacto, ObservacionIngreso,
                    codLecontacto, Prematricula, num, Correoenviado, asignado, Nombre1, Nombre2,
                    Apellido1, Apellido2, ProcesoFinalilzado, ControlIngreso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, 0, 0, ?, ?, ?, ?, 0, 0)
                """,
                codestu,
                cedula,
                student_name[:100],
                codperiodo,
                _clean(payload.correo)[:100],
                _clean(payload.telefono)[:100],
                usuario[:20],
                codprov,
                codcarrera,
                int(payload.codmodalida or 1),
                int(payload.codjornada or 0),
                "Registro",
                datetime.now().strftime("%H:%M"),
                codasesor,
                "Registro creado desde Reporteria",
                "Registro inicial",
                num,
                nombre1,
                nombre2,
                apellido1,
                apellido2,
            )
            cursor.execute(
                "SELECT TOP (1) Nombre_Basica FROM dbo.CARRERAS WHERE Cod_AnioBasica = ?",
                codcarrera,
            )
            career_row = cursor.fetchone()
            career_name = _clean(getattr(career_row, "Nombre_Basica", ""))
            if _is_english_career(codcarrera, career_name):
                scholarship_type = ""
                scholarship_percentage = 0.0
                scholarship_value = 0.0
            else:
                scholarship_type, scholarship_percentage = _validate_scholarship_selection(
                    payload.tipo_beca, payload.porcentaje_beca
                )
                scholarship_value = max(float(payload.valor_beca or 0), 0)
                if scholarship_type and scholarship_percentage <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail='Ingrese el porcentaje otorgado para la beca seleccionada',
                    )
                if scholarship_percentage > 0 and not scholarship_type:
                    raise HTTPException(status_code=400, detail='Seleccione el tipo de beca')
                if scholarship_percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD and not _clean(payload.motivo_beca):
                    raise HTTPException(
                        status_code=400,
                        detail="Las becas mayores al 15% requieren un motivo para solicitar aprobación",
                    )
            institutional_costs = _institutional_study_costs(
                payload.semestres_convenio,
                career_name,
            )
            scholarship_value = round(
                float(institutional_costs["total"]) * scholarship_percentage / 100,
                2,
            )
            _sync_student_scholarship(
                cursor,
                codestu,
                scholarship_type,
                scholarship_percentage,
                scholarship_value,
            )
            conn.commit()
            row = _fetch_preinscription_row(cursor, str(num))
        finance_sync = _sync_financial_preinscription(
            codestu=codestu,
            cedula=cedula,
            student_name=student_name,
            codperiodo=codperiodo,
            codcarrera=codcarrera,
            codmodalidad=int(payload.codmodalida or 1),
            codjornada=int(payload.codjornada or 0),
            correo=_clean(payload.correo)[:150],
            telefono=_clean(payload.telefono)[:50],
            codasesor=str(codasesor),
            usuario=usuario[:80],
            tipo_beca=scholarship_type,
            porcentaje_beca=scholarship_percentage,
            valor_beca=scholarship_value,
            motivo_beca=_clean(payload.motivo_beca)[:1000],
        )
        complement_sync = sync_preinscription_complements(
            {
                "origen_id": str(num),
                "codigo_estud": codestu,
                "cedula": cedula,
                "nombre": student_name,
                "codigo_periodo": codperiodo,
                "codigo_carrera": codcarrera,
                "codigo_modalidad": int(payload.codmodalida or 1),
                "codigo_jornada": int(payload.codjornada or 0),
                "codigo_asesor": str(codasesor),
                "correo": _clean(payload.correo)[:150],
                "telefono": _clean(payload.telefono)[:50],
                "estado": "REGISTRADA",
                "tiene_beca": bool(scholarship_type and scholarship_percentage > 0),
                "usuario": usuario[:80],
            },
            finance_sync,
        )
        requires_approval = scholarship_percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD
        return {
            "ok": True,
            "message": (
                "Preinscripción registrada. La beca requiere aprobación antes de continuar."
                if requires_approval
                else "Preinscripción registrada correctamente."
            ),
            "item": _preinscription_item(row),
            "asesor": {"codigo": str(codasesor), "usuario": usuario},
            "finanzas": finance_sync,
            "complementos": complement_sync,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al registrar la preinscripción: {exc}") from exc


def _validated_scholarship_configuration(payload: ScholarshipConfigurationPayload) -> dict[str, Any]:
    name = _clean(payload.nombre)
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la beca es obligatorio")
    code = _scholarship_code(payload.codigo or name)
    is_mintel = _is_mintel_scholarship(code) or _is_mintel_scholarship(name)
    is_variable = False if is_mintel else bool(payload.es_variable)
    fixed = 100.0 if is_mintel else min(max(float(payload.porcentaje or 0), 0), 100)
    minimum = 100.0 if is_mintel else min(max(float(payload.porcentaje_minimo or 0), 0), 100)
    maximum = 100.0 if is_mintel else min(max(float(payload.porcentaje_maximo or 100), 0), 100)
    if is_variable and minimum > maximum:
        raise HTTPException(status_code=400, detail="El porcentaje mínimo no puede superar al máximo")
    return {
        "codigo": code,
        "nombre": "Beca Mintel" if is_mintel else name,
        "es_variable": is_variable,
        "porcentaje": None if is_variable else fixed,
        "porcentaje_minimo": minimum if is_variable else fixed,
        "porcentaje_maximo": maximum if is_variable else fixed,
        "protegida": is_mintel,
        "activo": True if is_mintel else bool(payload.activo),
    }


@router.get("/becas/configuracion")
def list_scholarship_configurations(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        items = _scholarship_configurations(active_only=False)
        return {"ok": True, "items": items, "total": len(items)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo consultar la configuración de becas: {exc}") from exc


@router.post("/becas/configuracion")
def create_scholarship_configuration(
    payload: ScholarshipConfigurationPayload,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> dict[str, Any]:
    values = _validated_scholarship_configuration(payload)
    try:
        _ensure_scholarship_configuration_table()
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cat.ConfiguracionBecaPreinscripcion
                    (Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo,
                     PorcentajeMaximo, Protegida, Activo, UsuarioCreacion)
                OUTPUT INSERTED.ConfiguracionBecaId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values["codigo"], values["nombre"], int(values["es_variable"]),
                values["porcentaje"], values["porcentaje_minimo"], values["porcentaje_maximo"],
                int(values["protegida"]), int(values["activo"]), current_user.login[:128],
            )
            configuration_id = int(cursor.fetchone()[0])
            conn.commit()
        item = next(item for item in _scholarship_configurations() if item["id"] == configuration_id)
        return {"ok": True, "message": "Beca creada y disponible en inscripción.", "item": item}
    except pyodbc.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ya existe una beca con ese código") from exc
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo crear la beca: {exc}") from exc


@router.put("/becas/configuracion/{configuration_id}")
def update_scholarship_configuration(
    configuration_id: int,
    payload: ScholarshipConfigurationPayload,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> dict[str, Any]:
    values = _validated_scholarship_configuration(payload)
    try:
        _ensure_scholarship_configuration_table()
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT Protegida FROM cat.ConfiguracionBecaPreinscripcion WHERE ConfiguracionBecaId = ?",
                configuration_id,
            )
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="No existe la configuración de beca")
            if bool(existing.Protegida):
                values.update({
                    "codigo": "BECA_MINTEL",
                    "nombre": "Beca Mintel",
                    "es_variable": False,
                    "porcentaje": 100.0,
                    "porcentaje_minimo": 100.0,
                    "porcentaje_maximo": 100.0,
                    "protegida": True,
                    "activo": True,
                })
            cursor.execute(
                """
                UPDATE cat.ConfiguracionBecaPreinscripcion
                SET Codigo = ?, Nombre = ?, EsVariable = ?, PorcentajeFijo = ?,
                    PorcentajeMinimo = ?, PorcentajeMaximo = ?, Protegida = ?, Activo = ?,
                    FechaActualizacion = SYSDATETIME(), UsuarioActualizacion = ?
                WHERE ConfiguracionBecaId = ?
                """,
                values["codigo"], values["nombre"], int(values["es_variable"]),
                values["porcentaje"], values["porcentaje_minimo"], values["porcentaje_maximo"],
                int(values["protegida"]), int(values["activo"]), current_user.login[:128],
                configuration_id,
            )
            conn.commit()
        item = next(item for item in _scholarship_configurations() if item["id"] == configuration_id)
        return {"ok": True, "message": "Beca actualizada en el catálogo de inscripción.", "item": item}
    except HTTPException:
        raise
    except pyodbc.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ya existe una beca con ese código") from exc
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo actualizar la beca: {exc}") from exc


@router.get("/becas/pendientes")
def list_pending_preinscription_scholarships(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=250, ge=1, le=1000),
) -> dict[str, Any]:
    del current_user
    search = _clean(query)
    pattern = f"%{search}%"
    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (?)
                    b.BecaId,
                    e.CodigoEstud,
                    e.NumeroIdentificacion,
                    e.NombreCompleto,
                    c.CodigoCarrera,
                    COALESCE(ca.NombreCarrera, c.CodigoCarrera) AS Carrera,
                    c.CodigoPeriodo,
                    COALESCE(pe.NombrePeriodo, c.CodigoPeriodo) AS Periodo,
                    tb.Nombre AS TipoBeca,
                    b.PorcentajeBeca,
                    b.ValorBeca,
                    b.Motivo,
                    b.FechaSolicitud,
                    eb.Codigo AS Estado
                FROM bec.BecaEstudiante b
                INNER JOIN core.Estudiante e ON e.EstudianteId = b.EstudianteId
                INNER JOIN fin.CuentaEstudiante c ON c.CuentaEstudianteId = b.CuentaEstudianteId
                INNER JOIN INTECBDD.dbo.DATOS_ESTUD active_student
                    ON TRY_CONVERT(nvarchar(50), active_student.codigo_estud) = TRY_CONVERT(nvarchar(50), e.CodigoEstud)
                   AND UPPER(LTRIM(RTRIM(ISNULL(active_student.Estado, '')))) = 'A'
                INNER JOIN cat.TipoBeca tb ON tb.TipoBecaId = b.TipoBecaId
                INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
                LEFT JOIN core.Carrera ca ON ca.CodigoCarrera = c.CodigoCarrera
                LEFT JOIN core.Periodo pe ON pe.CodigoPeriodo = c.CodigoPeriodo
                WHERE ISNULL(b.PorcentajeBeca, 0) > ?
                  AND eb.Codigo = 'SOLICITADA'
                  AND (
                    ? = '' OR e.NumeroIdentificacion LIKE ? OR e.NombreCompleto LIKE ?
                    OR ISNULL(ca.NombreCarrera, c.CodigoCarrera) LIKE ?
                    OR tb.Nombre LIKE ? OR c.CodigoPeriodo LIKE ?
                  )
                ORDER BY b.FechaSolicitud ASC, e.NombreCompleto ASC, b.BecaId ASC
                """,
                limit,
                _SCHOLARSHIP_APPROVAL_THRESHOLD,
                search,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
            )
            rows = cursor.fetchall()

        items = [
            {
                "beca_id": int(row.BecaId),
                "codigo_estud": str(row.CodigoEstud or ""),
                "cedula": _clean(row.NumeroIdentificacion),
                "estudiante": _clean(row.NombreCompleto),
                "codigo_carrera": _clean(row.CodigoCarrera),
                "carrera": _clean(row.Carrera),
                "codigo_periodo": _clean(row.CodigoPeriodo),
                "periodo": _clean(row.Periodo),
                "tipo_beca": _clean(row.TipoBeca),
                "porcentaje_beca": float(row.PorcentajeBeca or 0),
                "valor_beca": float(row.ValorBeca or 0),
                "motivo": _clean(row.Motivo),
                "fecha_solicitud": _date_text(row.FechaSolicitud),
                "estado": _clean(row.Estado).upper(),
            }
            for row in rows
        ]
        items = _exclude_english_scholarship_items(items)
        return {
            "ok": True,
            "items": items,
            "total": len(items),
            "threshold": _SCHOLARSHIP_APPROVAL_THRESHOLD,
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudieron consultar las becas pendientes: {exc}") from exc


@router.get("/becas/beneficiarios")
def list_preinscription_scholarship_beneficiaries(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    query: str = Query(default="", max_length=120),
    limit: int | None = Query(default=1000, ge=1),
) -> dict[str, Any]:
    del current_user
    search = _clean(query)
    pattern = f"%{search}%"
    top_clause = "TOP (?)" if limit is not None else ""
    limit_params: list[Any] = [limit] if limit is not None else []
    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT {top_clause}
                    b.BecaId,
                    e.CodigoEstud,
                    e.NumeroIdentificacion,
                    e.NombreCompleto,
                    c.CodigoCarrera,
                    COALESCE(ca.NombreCarrera, c.CodigoCarrera) AS Carrera,
                    c.CodigoPeriodo,
                    COALESCE(pe.NombrePeriodo, c.CodigoPeriodo) AS Periodo,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(lb.tipo_beca COLLATE DATABASE_DEFAULT)), ''),
                        tb.Nombre COLLATE DATABASE_DEFAULT
                    ) AS TipoBeca,
                    b.PorcentajeBeca,
                    b.ValorBeca,
                    b.Motivo,
                    b.FechaSolicitud,
                    b.FechaAprobacion,
                    b.UsuarioAprobacion,
                    active_student.movil AS Telefono,
                    COALESCE(NULLIF(active_student.correointec, ''), active_student.correo) AS Correo,
                    active_student.nivelAcademicoQueCursa AS NivelFormacion,
                    active_student.discapacidad AS Discapacidad,
                    active_student.Porce_Capacidad AS PorcentajeDiscapacidad,
                    active_student.Tipo_Capacidad AS TipoDiscapacidad,
                    eb.Codigo AS Estado
                FROM bec.BecaEstudiante b
                INNER JOIN core.Estudiante e ON e.EstudianteId = b.EstudianteId
                INNER JOIN fin.CuentaEstudiante c ON c.CuentaEstudianteId = b.CuentaEstudianteId
                    AND c.Activo = 1
                INNER JOIN INTECBDD.dbo.DATOS_ESTUD active_student
                    ON TRY_CONVERT(nvarchar(50), active_student.codigo_estud) COLLATE DATABASE_DEFAULT
                     = TRY_CONVERT(nvarchar(50), e.CodigoEstud) COLLATE DATABASE_DEFAULT
                   AND UPPER(LTRIM(RTRIM(ISNULL(active_student.Estado, '')))) = 'A'
                INNER JOIN cat.TipoBeca tb ON tb.TipoBecaId = b.TipoBecaId
                INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
                LEFT JOIN core.Carrera ca ON ca.CodigoCarrera = c.CodigoCarrera
                LEFT JOIN core.Periodo pe ON pe.CodigoPeriodo = c.CodigoPeriodo
                OUTER APPLY
                (
                    SELECT TOP (1) legacy.tipo_beca
                    FROM INTECBDD.dbo.Becas legacy
                    WHERE TRY_CONVERT(nvarchar(50), legacy.codestud) COLLATE DATABASE_DEFAULT
                        = TRY_CONVERT(nvarchar(50), e.CodigoEstud) COLLATE DATABASE_DEFAULT
                      AND ISNULL(TRY_CONVERT(decimal(9,2), legacy.porcentaje_beca), 0) > 0
                    ORDER BY
                        CASE WHEN ABS(ISNULL(TRY_CONVERT(decimal(9,2), legacy.porcentaje_beca), 0) - ISNULL(b.PorcentajeBeca, 0)) < 0.01 THEN 0 ELSE 1 END,
                        legacy.tipo_beca
                ) lb
                WHERE eb.Codigo = 'APROBADA'
                  AND ISNULL(b.PorcentajeBeca, 0) > 0
                  AND EXISTS
                  (
                      SELECT 1
                      FROM INTECBDD.dbo.CARRERAXESTUD active_enrollment
                      WHERE TRY_CONVERT(nvarchar(50), active_enrollment.codigo_estud) COLLATE DATABASE_DEFAULT
                          = TRY_CONVERT(nvarchar(50), e.CodigoEstud) COLLATE DATABASE_DEFAULT
                  )
                  AND (
                    ? = ''
                    OR e.NumeroIdentificacion COLLATE DATABASE_DEFAULT LIKE ?
                    OR e.NombreCompleto COLLATE DATABASE_DEFAULT LIKE ?
                    OR ISNULL(ca.NombreCarrera, c.CodigoCarrera) COLLATE DATABASE_DEFAULT LIKE ?
                    OR COALESCE(
                        NULLIF(LTRIM(RTRIM(lb.tipo_beca COLLATE DATABASE_DEFAULT)), ''),
                        tb.Nombre COLLATE DATABASE_DEFAULT
                    ) LIKE ?
                    OR c.CodigoPeriodo COLLATE DATABASE_DEFAULT LIKE ?
                    OR ISNULL(b.UsuarioAprobacion, '') COLLATE DATABASE_DEFAULT LIKE ?
                  )
                ORDER BY COALESCE(b.FechaAprobacion, b.FechaSolicitud) DESC,
                         e.NombreCompleto ASC, b.BecaId DESC
                """,
                *limit_params,
                search,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
            )
            rows = cursor.fetchall()

        items = [
            {
                "beca_id": int(row.BecaId),
                "codigo_estud": str(row.CodigoEstud or ""),
                "cedula": _clean(row.NumeroIdentificacion),
                "estudiante": _clean(row.NombreCompleto),
                "codigo_carrera": _clean(row.CodigoCarrera),
                "carrera": _clean(row.Carrera),
                "codigo_periodo": _clean(row.CodigoPeriodo),
                "periodo": _clean(row.Periodo),
                "tipo_beca": _clean(row.TipoBeca),
                "porcentaje_beca": float(row.PorcentajeBeca or 0),
                "valor_beca": float(row.ValorBeca or 0),
                "motivo": _clean(row.Motivo),
                "fecha_solicitud": _date_text(row.FechaSolicitud),
                "fecha_aprobacion": _date_text(row.FechaAprobacion),
                "usuario_aprobacion": _clean(row.UsuarioAprobacion),
                "telefono": _clean(row.Telefono),
                "correo": _clean(row.Correo),
                "nivel_formacion": _clean(row.NivelFormacion),
                "discapacidad": _clean(row.Discapacidad),
                "porcentaje_discapacidad": _clean(row.PorcentajeDiscapacidad),
                "tipo_discapacidad": _clean(row.TipoDiscapacidad),
                "estado": _clean(row.Estado).upper(),
            }
            for row in rows
        ]
        items = _exclude_english_scholarship_items(items)
        financial_student_codes = {item["codigo_estud"] for item in items if item["codigo_estud"]}
        with get_connection() as legacy_conn:
            legacy_cursor = legacy_conn.cursor()
            legacy_cursor.execute(
                f"""
                SELECT {top_clause}
                    b.id AS BecaId,
                    b.codestud AS CodigoEstud,
                    d.Cedula_Est AS NumeroIdentificacion,
                    d.Apellidos_nombre AS NombreCompleto,
                    TRY_CONVERT(nvarchar(50), ce.cod_anio_Basica) AS CodigoCarrera,
                    COALESCE(c.Nombre_Basica, TRY_CONVERT(nvarchar(50), ce.cod_anio_Basica)) AS Carrera,
                    TRY_CONVERT(nvarchar(50), ce.codigo_periodo) AS CodigoPeriodo,
                    COALESCE(p.Detalle_Periodo, TRY_CONVERT(nvarchar(50), ce.codigo_periodo)) AS Periodo,
                    b.tipo_beca AS TipoBeca,
                    b.porcentaje_beca AS PorcentajeBeca,
                    b.valor_monto_beca AS ValorBeca,
                    d.movil AS Telefono,
                    COALESCE(NULLIF(d.correointec, ''), d.correo) AS Correo,
                    d.nivelAcademicoQueCursa AS NivelFormacion,
                    d.discapacidad AS Discapacidad,
                    d.Porce_Capacidad AS PorcentajeDiscapacidad,
                    d.Tipo_Capacidad AS TipoDiscapacidad
                FROM dbo.Becas b
                INNER JOIN dbo.DATOS_ESTUD d
                    ON TRY_CONVERT(nvarchar(50), d.codigo_estud) = TRY_CONVERT(nvarchar(50), b.codestud)
                   AND UPPER(LTRIM(RTRIM(ISNULL(d.Estado, '')))) = 'A'
                OUTER APPLY
                (
                    SELECT TOP (1) cx.cod_anio_Basica, cx.codigo_periodo
                    FROM dbo.CARRERAXESTUD cx
                    WHERE TRY_CONVERT(nvarchar(50), cx.codigo_estud) = TRY_CONVERT(nvarchar(50), b.codestud)
                    ORDER BY cx.Fecha_Matricula DESC, cx.codigo_periodo DESC, cx.num DESC
                ) ce
                LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = ce.cod_anio_Basica
                LEFT JOIN dbo.PERIODO p ON p.cod_periodo = ce.codigo_periodo
                WHERE ISNULL(TRY_CONVERT(decimal(9,2), b.porcentaje_beca), 0) > 0
                  AND ce.codigo_periodo IS NOT NULL
                  AND (
                    ? = ''
                    OR d.Cedula_Est COLLATE DATABASE_DEFAULT LIKE ?
                    OR d.Apellidos_nombre COLLATE DATABASE_DEFAULT LIKE ?
                    OR ISNULL(c.Nombre_Basica, '') COLLATE DATABASE_DEFAULT LIKE ?
                    OR ISNULL(b.tipo_beca, '') COLLATE DATABASE_DEFAULT LIKE ?
                    OR ISNULL(p.Detalle_Periodo, '') COLLATE DATABASE_DEFAULT LIKE ?
                  )
                ORDER BY d.Apellidos_nombre, b.id
                """,
                *limit_params,
                search,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
            )
            legacy_rows = legacy_cursor.fetchall()

        for row in legacy_rows:
            student_code = str(row.CodigoEstud or "")
            if student_code in financial_student_codes:
                continue
            if _is_english_career(row.CodigoCarrera, row.Carrera):
                continue
            items.append(
                {
                    "beca_id": -int(row.BecaId),
                    "codigo_estud": student_code,
                    "cedula": _clean(row.NumeroIdentificacion),
                    "estudiante": _clean(row.NombreCompleto) or f"Estudiante {student_code}",
                    "codigo_carrera": _clean(row.CodigoCarrera),
                    "carrera": _clean(row.Carrera),
                    "codigo_periodo": _clean(row.CodigoPeriodo),
                    "periodo": _clean(row.Periodo),
                    "tipo_beca": _clean(row.TipoBeca),
                    "porcentaje_beca": float(row.PorcentajeBeca or 0),
                    "valor_beca": float(row.ValorBeca or 0),
                    "motivo": "Registro histórico de INTECBDD",
                    "fecha_solicitud": "",
                    "fecha_aprobacion": "",
                    "usuario_aprobacion": "INTECBDD",
                    "telefono": _clean(row.Telefono),
                    "correo": _clean(row.Correo),
                    "nivel_formacion": _clean(row.NivelFormacion),
                    "discapacidad": _clean(row.Discapacidad),
                    "porcentaje_discapacidad": _clean(row.PorcentajeDiscapacidad),
                    "tipo_discapacidad": _clean(row.TipoDiscapacidad),
                    "estado": "REGISTRADA",
                }
            )
        items.sort(key=lambda item: (item["estudiante"].upper(), item["codigo_estud"]))
        if limit is not None:
            items = items[:limit]
        return {
            "ok": True,
            "items": items,
            "total": len(items),
            "valor_total": round(sum(item["valor_beca"] for item in items), 2),
            "porcentaje_promedio": (
                round(sum(item["porcentaje_beca"] for item in items) / len(items), 2)
                if items else 0.0
            ),
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo consultar el listado de becados: {exc}") from exc


def _ensure_scholarship_contract_table(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'bec')
            EXEC(N'CREATE SCHEMA bec AUTHORIZATION dbo');

        IF OBJECT_ID(N'bec.ContratoBeca', N'U') IS NULL
        BEGIN
            CREATE TABLE bec.ContratoBeca
            (
                ContratoBecaId BIGINT IDENTITY(1,1) NOT NULL
                    CONSTRAINT PK_ContratoBeca PRIMARY KEY,
                BecaOrigenId BIGINT NOT NULL,
                Origen VARCHAR(20) NOT NULL,
                CodigoEstud NVARCHAR(50) NOT NULL,
                NumeroIdentificacion NVARCHAR(30) NULL,
                Estudiante NVARCHAR(250) NOT NULL,
                CodigoCarrera NVARCHAR(50) NULL,
                Carrera NVARCHAR(250) NULL,
                CodigoPeriodo NVARCHAR(50) NULL,
                Periodo NVARCHAR(250) NULL,
                TipoBeca NVARCHAR(200) NOT NULL,
                PorcentajeBeca DECIMAL(9,2) NOT NULL,
                ValorBeca DECIMAL(18,2) NOT NULL,
                NumeroContrato NVARCHAR(100) NOT NULL,
                FechaContrato DATE NOT NULL,
                FormatoContrato VARCHAR(30) NOT NULL
                    CONSTRAINT DF_ContratoBeca_Formato DEFAULT 'BECA',
                PlantillaJson NVARCHAR(MAX) NULL,
                NombreArchivo NVARCHAR(260) NOT NULL,
                RutaArchivo NVARCHAR(1000) NOT NULL,
                HashSha256 CHAR(64) NOT NULL,
                GraphDocumentoId BIGINT NULL,
                GraphWebUrl NVARCHAR(2000) NULL,
                NombreArchivoFirmado NVARCHAR(260) NULL,
                HashFirmado CHAR(64) NULL,
                FechaCargaExpediente DATETIME2 NULL,
                UsuarioCargaExpediente NVARCHAR(128) NULL,
                EstadoExpedienteCodigo VARCHAR(30) NULL,
                EstadoCodigo VARCHAR(30) NOT NULL
                    CONSTRAINT DF_ContratoBeca_Estado DEFAULT 'GENERADO',
                UsuarioGeneracion NVARCHAR(128) NOT NULL,
                FechaGeneracion DATETIME2 NOT NULL
                    CONSTRAINT DF_ContratoBeca_FechaGeneracion DEFAULT SYSDATETIME(),
                CONSTRAINT UQ_ContratoBeca_NumeroContrato UNIQUE (NumeroContrato),
                CONSTRAINT CK_ContratoBeca_Porcentaje CHECK (PorcentajeBeca BETWEEN 0 AND 100)
            );

            CREATE INDEX IX_ContratoBeca_Estudiante
                ON bec.ContratoBeca (CodigoEstud, FechaGeneracion DESC);
            CREATE INDEX IX_ContratoBeca_Beca
                ON bec.ContratoBeca (BecaOrigenId, Origen, FechaGeneracion DESC);
        END

        IF COL_LENGTH(N'bec.ContratoBeca', N'GraphDocumentoId') IS NULL
            ALTER TABLE bec.ContratoBeca ADD GraphDocumentoId BIGINT NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'GraphWebUrl') IS NULL
            ALTER TABLE bec.ContratoBeca ADD GraphWebUrl NVARCHAR(2000) NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'NombreArchivoFirmado') IS NULL
            ALTER TABLE bec.ContratoBeca ADD NombreArchivoFirmado NVARCHAR(260) NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'HashFirmado') IS NULL
            ALTER TABLE bec.ContratoBeca ADD HashFirmado CHAR(64) NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'FechaCargaExpediente') IS NULL
            ALTER TABLE bec.ContratoBeca ADD FechaCargaExpediente DATETIME2 NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'UsuarioCargaExpediente') IS NULL
            ALTER TABLE bec.ContratoBeca ADD UsuarioCargaExpediente NVARCHAR(128) NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'EstadoExpedienteCodigo') IS NULL
            ALTER TABLE bec.ContratoBeca ADD EstadoExpedienteCodigo VARCHAR(30) NULL;
        IF COL_LENGTH(N'bec.ContratoBeca', N'FormatoContrato') IS NULL
            ALTER TABLE bec.ContratoBeca ADD FormatoContrato VARCHAR(30) NOT NULL
                CONSTRAINT DF_ContratoBeca_Formato DEFAULT 'BECA';
        IF COL_LENGTH(N'bec.ContratoBeca', N'PlantillaJson') IS NULL
            ALTER TABLE bec.ContratoBeca ADD PlantillaJson NVARCHAR(MAX) NULL;

        IF NOT EXISTS
        (
            SELECT 1
            FROM sys.indexes
            WHERE object_id = OBJECT_ID(N'bec.ContratoBeca')
              AND name = N'IX_ContratoBeca_EstudiantePeriodo'
        )
            CREATE INDEX IX_ContratoBeca_EstudiantePeriodo
                ON bec.ContratoBeca (CodigoEstud, CodigoPeriodo, FechaGeneracion DESC);
        """
    )


def _scholarship_contract_candidates(
    current_user: SessionUser,
    query: str = "",
    scholarship_type: str = "",
    academic_period: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    response = list_preinscription_scholarship_beneficiaries(
        current_user=current_user,
        query=query,
        limit=limit,
    )
    selected_type = _scholarship_code(scholarship_type) if _clean(scholarship_type) else ""
    selected_period = _clean(academic_period)
    items = [
        dict(item)
        for item in response.get("items", [])
        if not selected_type or _scholarship_code(item.get("tipo_beca")) == selected_type
        if not selected_period or _clean(item.get("codigo_periodo")) == selected_period
    ]
    if not items:
        return []

    with get_finance_connection() as conn:
        cursor = conn.cursor()
        _ensure_scholarship_contract_table(cursor)
        cursor.execute(
            """
            SELECT BecaOrigenId, Origen, CodigoPeriodo, COUNT(1) AS TotalContratos,
                   MAX(ContratoBecaId) AS UltimoContratoId,
                   MAX(FechaGeneracion) AS UltimaGeneracion
            FROM bec.ContratoBeca
            WHERE EstadoCodigo IN ('GENERADO', 'ARCHIVADO')
            GROUP BY BecaOrigenId, Origen, CodigoPeriodo
            """
        )
        contract_rows = cursor.fetchall()
        conn.commit()

    generated = {
        (int(row.BecaOrigenId), _clean(row.Origen).upper(), _clean(row.CodigoPeriodo)): {
            "contratos_generados": int(row.TotalContratos or 0),
            "ultimo_contrato_id": int(row.UltimoContratoId or 0),
            "ultima_generacion": _date_text(row.UltimaGeneracion),
        }
        for row in contract_rows
    }
    for item in items:
        origin = "INTECBDD" if int(item["beca_id"]) < 0 else "FINANZAS"
        item.update(
            generated.get(
                (int(item["beca_id"]), origin, _clean(item.get("codigo_periodo"))),
                {"contratos_generados": 0, "ultimo_contrato_id": 0, "ultima_generacion": ""},
            )
        )
    return items


@router.get("/becas/contratos/plantilla")
def get_scholarship_contract_template(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    formato_contrato: Literal["BECA", "INCENTIVOS_TRIBUTARIOS"] = Query(default="BECA"),
) -> dict[str, Any]:
    del current_user
    return _default_scholarship_contract_template_data(formato_contrato)


@router.get("/becas/contratos/candidatos")
def list_scholarship_contract_candidates(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    query: str = Query(default="", max_length=120),
    tipo_beca: str = Query(default="", max_length=150),
    codigo_periodo: str = Query(default="", max_length=50),
    limit: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    try:
        all_items = _scholarship_contract_candidates(current_user, query, "", "", limit)
        configured_types = {
            _clean(item.get("nombre"))
            for item in _scholarship_configurations(active_only=True)
            if _clean(item.get("nombre"))
        }
        scholarship_types = sorted(
            configured_types
            | {_clean(item.get("tipo_beca")) for item in all_items if _clean(item.get("tipo_beca"))},
            key=str.casefold,
        )
        selected_code = _scholarship_code(tipo_beca) if _clean(tipo_beca) else ""
        type_items = [
            item
            for item in all_items
            if not selected_code or _scholarship_code(item.get("tipo_beca")) == selected_code
        ]
        periods_by_code: dict[str, dict[str, Any]] = {}
        if selected_code:
            for item in type_items:
                period_code = _clean(item.get("codigo_periodo"))
                if not period_code:
                    continue
                option = periods_by_code.setdefault(
                    period_code,
                    {
                        "codigo_periodo": period_code,
                        "periodo": _clean(item.get("periodo")) or period_code,
                        "total": 0,
                    },
                )
                option["total"] += 1
        periods = sorted(
            periods_by_code.values(),
            key=lambda item: (item["periodo"].casefold(), item["codigo_periodo"]),
            reverse=True,
        )
        selected_period = _clean(codigo_periodo)
        items = [
            item
            for item in type_items
            if selected_code
            and selected_period
            and _clean(item.get("codigo_periodo")) == selected_period
        ]
        return {
            "ok": True,
            "items": items,
            "total": len(items),
            "tipos_beca": scholarship_types,
            "periodos": periods,
            "criteria": {
                "query": _clean(query),
                "tipo_beca": _clean(tipo_beca),
                "codigo_periodo": selected_period,
                "estado_estudiante": "A",
            },
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudieron consultar los contratos de beca: {exc}") from exc


@router.post("/becas/contratos/vista-previa")
def preview_scholarship_contract(
    payload: ScholarshipContractPreviewPayload,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> StreamingResponse:
    item = _scholarship_contract_preview_item(payload)
    if payload.beca_id is not None:
        try:
            candidates = _scholarship_contract_candidates(
                current_user,
                "",
                "",
                _clean(payload.codigo_periodo),
                None,
            )
        except pyodbc.Error as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo preparar la vista previa del contrato: {exc}",
            ) from exc
        selected = next(
            (candidate for candidate in candidates if int(candidate.get("beca_id") or 0) == payload.beca_id),
            None,
        )
        if selected is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "El estudiante seleccionado ya no corresponde a una beca activa. "
                    "Actualice el listado antes de generar la vista previa."
                ),
            )
        item = selected

    contract_format = _canonical_scholarship_contract_format(payload.formato_contrato)
    contract_template = _resolved_scholarship_contract_template(
        contract_format,
        payload.plantilla,
    )
    contract_date = _date_from_iso(contract_template.fecha_contrato)
    contract_number = _scholarship_contract_base_number(item, contract_date)
    pdf_bytes = _build_selected_scholarship_contract_pdf(
        item,
        contract_number,
        contract_date,
        contract_format,
        contract_template,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="vista-previa-contrato-beca.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/becas/contratos/generar")
def generate_scholarship_contracts(
    payload: ScholarshipContractGeneratePayload,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> StreamingResponse:
    scholarship_ids, academic_period = _scholarship_contract_generation_selection(payload)
    try:
        candidates = _scholarship_contract_candidates(current_user, "", "", academic_period, None)
        candidates_by_id = {int(item["beca_id"]): item for item in candidates}
        selected = [candidates_by_id[item_id] for item_id in scholarship_ids if item_id in candidates_by_id]
        missing = [item_id for item_id in scholarship_ids if item_id not in candidates_by_id]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Uno o más registros ya no corresponden a estudiantes activos con una beca vigente. "
                    "Actualice el listado y vuelva a seleccionar."
                ),
            )
        selected_types = {_scholarship_code(item.get("tipo_beca")) for item in selected}
        if len(selected_types) != 1:
            raise HTTPException(status_code=400, detail="Genere los contratos de un solo tipo de beca por operación")
        selected_periods = {_clean(item.get("codigo_periodo")) for item in selected}
        if selected_periods != {academic_period}:
            raise HTTPException(
                status_code=400,
                detail="Cada operación debe contener una sola beca y un único período académico",
            )

        contract_format = _canonical_scholarship_contract_format(payload.formato_contrato)
        contract_template = _resolved_scholarship_contract_template(
            contract_format,
            payload.plantilla,
        )
        contract_template_json = json.dumps(
            contract_template.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        contract_date = _date_from_iso(contract_template.fecha_contrato)
        generated_files: list[tuple[str, Path]] = []
        written_paths: list[Path] = []
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            _ensure_scholarship_contract_table(cursor)
            try:
                for item in selected:
                    student_code = _safe_filename(_clean(item.get("codigo_estud")) or _clean(item.get("cedula")))
                    period_code = _safe_filename(_clean(item.get("codigo_periodo")))
                    contract_number = _next_scholarship_contract_number(cursor, item, contract_date)
                    filename = _safe_filename(f"{contract_number}.pdf")
                    pdf_bytes = _build_selected_scholarship_contract_pdf(
                        item,
                        contract_number,
                        contract_date,
                        contract_format,
                        contract_template,
                    )
                    target_directory = (
                        _PREINSCRIPTION_UPLOAD_ROOT / "contratos-becas" / student_code / period_code
                    )
                    target_directory.mkdir(parents=True, exist_ok=True)
                    target_path = target_directory / filename
                    target_path.write_bytes(pdf_bytes)
                    written_paths.append(target_path)
                    relative_path = target_path.relative_to(_BACKEND_ROOT)
                    origin = "INTECBDD" if int(item["beca_id"]) < 0 else "FINANZAS"
                    cursor.execute(
                        """
                        INSERT INTO bec.ContratoBeca
                        (
                            BecaOrigenId, Origen, CodigoEstud, NumeroIdentificacion, Estudiante,
                            CodigoCarrera, Carrera, CodigoPeriodo, Periodo, TipoBeca,
                            PorcentajeBeca, ValorBeca, NumeroContrato, FechaContrato,
                            FormatoContrato, PlantillaJson, NombreArchivo, RutaArchivo,
                            HashSha256, EstadoCodigo, UsuarioGeneracion
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GENERADO', ?)
                        """,
                        int(item["beca_id"]),
                        origin,
                        _clean(item.get("codigo_estud")),
                        _clean(item.get("cedula")),
                        _clean(item.get("estudiante")),
                        _clean(item.get("codigo_carrera")),
                        _clean(item.get("carrera")),
                        _clean(item.get("codigo_periodo")),
                        _clean(item.get("periodo")),
                        _clean(item.get("tipo_beca")),
                        float(item.get("porcentaje_beca") or 0),
                        float(item.get("valor_beca") or 0),
                        contract_number,
                        contract_date,
                        contract_format,
                        contract_template_json,
                        filename,
                        str(relative_path),
                        sha256(pdf_bytes).hexdigest(),
                        current_user.login,
                    )
                    generated_files.append((filename, target_path))
                conn.commit()
            except Exception:
                conn.rollback()
                for path in written_paths:
                    if path.exists() and path.is_relative_to(_PREINSCRIPTION_UPLOAD_ROOT):
                        path.unlink()
                raise

        if len(generated_files) == 1:
            filename, contract_path = generated_files[0]
            return StreamingResponse(
                _stream_scholarship_contract_archive(contract_path.open("rb")),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Generated-Contracts": "1",
                },
            )

        bundle = SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
        try:
            with ZipFile(bundle, mode="w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
                for filename, contract_path in generated_files:
                    archive.write(contract_path, arcname=filename)
            bundle.seek(0)
        except Exception:
            bundle.close()
            raise
        archive_name = f"contratos_beca_{contract_date.isoformat()}.zip"
        return StreamingResponse(
            _stream_scholarship_contract_archive(bundle),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{archive_name}"',
                "X-Generated-Contracts": str(len(generated_files)),
            },
        )
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudieron generar los contratos de beca: {exc}") from exc


@router.get("/becas/contratos/historial")
def list_scholarship_contract_history(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    del current_user
    search = _clean(query)
    pattern = f"%{search}%"
    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            _ensure_scholarship_contract_table(cursor)
            cursor.execute(
                """
                SELECT TOP (?)
                    ContratoBecaId, BecaOrigenId, Origen, CodigoEstud,
                    NumeroIdentificacion, Estudiante, CodigoCarrera, Carrera,
                    CodigoPeriodo, Periodo, TipoBeca, PorcentajeBeca, ValorBeca,
                    NumeroContrato, FechaContrato, FormatoContrato, PlantillaJson,
                    NombreArchivo, HashSha256,
                    EstadoCodigo, UsuarioGeneracion, FechaGeneracion,
                    GraphDocumentoId, GraphWebUrl, NombreArchivoFirmado, HashFirmado,
                    FechaCargaExpediente, UsuarioCargaExpediente, EstadoExpedienteCodigo
                FROM bec.ContratoBeca
                WHERE
                    ? = '' OR NumeroIdentificacion LIKE ? OR Estudiante LIKE ?
                    OR Carrera LIKE ? OR Periodo LIKE ? OR TipoBeca LIKE ?
                    OR NumeroContrato LIKE ? OR UsuarioGeneracion LIKE ?
                    OR ISNULL(NombreArchivoFirmado, '') LIKE ?
                    OR ISNULL(EstadoExpedienteCodigo, '') LIKE ?
                    OR ISNULL(FormatoContrato, '') LIKE ?
                ORDER BY FechaGeneracion DESC, ContratoBecaId DESC
                """,
                limit,
                search,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
            )
            rows = cursor.fetchall()
            conn.commit()
        items = [
            {
                "contrato_id": int(row.ContratoBecaId),
                "beca_id": int(row.BecaOrigenId),
                "origen": _clean(row.Origen),
                "codigo_estud": _clean(row.CodigoEstud),
                "cedula": _clean(row.NumeroIdentificacion),
                "estudiante": _clean(row.Estudiante),
                "codigo_carrera": _clean(row.CodigoCarrera),
                "carrera": _clean(row.Carrera),
                "codigo_periodo": _clean(row.CodigoPeriodo),
                "periodo": _clean(row.Periodo),
                "tipo_beca": _clean(row.TipoBeca),
                "porcentaje_beca": float(row.PorcentajeBeca or 0),
                "valor_beca": float(row.ValorBeca or 0),
                "numero_contrato": _clean(row.NumeroContrato),
                "fecha_contrato": _date_text(row.FechaContrato),
                "formato_contrato": _canonical_scholarship_contract_format(row.FormatoContrato),
                "plantilla": _scholarship_contract_template_history(row.PlantillaJson),
                "nombre_archivo": _clean(row.NombreArchivo),
                "hash_sha256": _clean(row.HashSha256),
                "estado": _clean(row.EstadoCodigo),
                "usuario_generacion": _clean(row.UsuarioGeneracion),
                "fecha_generacion": _date_text(row.FechaGeneracion),
                "expediente_documento_id": (
                    int(row.GraphDocumentoId) if row.GraphDocumentoId is not None else None
                ),
                "expediente_url": _clean(row.GraphWebUrl),
                "nombre_archivo_firmado": _clean(row.NombreArchivoFirmado),
                "hash_firmado": _clean(row.HashFirmado),
                "estado_expediente": _clean(row.EstadoExpedienteCodigo),
                "usuario_carga_expediente": _clean(row.UsuarioCargaExpediente),
                "fecha_carga_expediente": _date_text(row.FechaCargaExpediente),
            }
            for row in rows
        ]
        items = _exclude_english_scholarship_items(items)
        return {"ok": True, "items": items, "total": len(items)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo consultar el historial de contratos: {exc}") from exc


@router.get("/becas/contratos/{contract_id}/descargar")
def download_scholarship_contract(
    contract_id: int,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> StreamingResponse:
    del current_user
    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            _ensure_scholarship_contract_table(cursor)
            cursor.execute(
                """
                SELECT NombreArchivo, RutaArchivo
                FROM bec.ContratoBeca
                WHERE ContratoBecaId = ? AND EstadoCodigo IN ('GENERADO', 'ARCHIVADO')
                """,
                contract_id,
            )
            row = cursor.fetchone()
            conn.commit()
        if not row:
            raise HTTPException(status_code=404, detail="No se encontró el contrato de beca")
        contract_root = (_PREINSCRIPTION_UPLOAD_ROOT / "contratos-becas").resolve()
        target_path = (_BACKEND_ROOT / _clean(row.RutaArchivo)).resolve()
        if not target_path.is_relative_to(contract_root) or not target_path.is_file():
            raise HTTPException(status_code=404, detail="El archivo del contrato no está disponible")
        filename = _safe_filename(_clean(row.NombreArchivo) or target_path.name)
        return StreamingResponse(
            BytesIO(target_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo descargar el contrato de beca: {exc}") from exc


@router.post("/becas/contratos/{contract_id}/expediente")
async def upload_signed_scholarship_contract(
    contract_id: int,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    raw_filename, content = await read_secure_upload(
        file,
        maximum=_SCHOLARSHIP_CONTRACT_MAX_BYTES,
        label="contrato firmado",
        allowed_extensions={".pdf"},
        allowed_content_types={"application/pdf", "application/octet-stream"},
    )
    filename = _safe_filename(raw_filename)
    content_type = "application/pdf"

    try:
        with get_finance_connection() as conn:
            cursor = conn.cursor()
            _ensure_scholarship_contract_table(cursor)
            cursor.execute(
                """
                SELECT
                    cb.ContratoBecaId, cb.CodigoEstud, cb.NumeroIdentificacion,
                    cb.Estudiante, cb.CodigoPeriodo, cb.NumeroContrato,
                    COALESCE(NULLIF(d.correointec, ''), d.correo, '') AS Correo
                FROM bec.ContratoBeca cb
                LEFT JOIN INTECBDD.dbo.DATOS_ESTUD d
                  ON TRY_CONVERT(nvarchar(50), d.codigo_estud) = cb.CodigoEstud
                WHERE cb.ContratoBecaId = ?
                  AND cb.EstadoCodigo IN ('GENERADO', 'ARCHIVADO')
                """,
                contract_id,
            )
            contract = cursor.fetchone()
            conn.commit()
        if not contract:
            raise HTTPException(status_code=404, detail="No se encontró el contrato de beca")

        student_code_text = _clean(contract.CodigoEstud)
        student_code = int(student_code_text) if student_code_text.isdigit() else None
        period_code = _clean(contract.CodigoPeriodo)
        if not period_code:
            raise HTTPException(
                status_code=409,
                detail="El contrato no tiene un período académico asociado y no puede archivarse",
            )

        session_id = uuid4()
        graph_item: dict[str, Any] | None = None
        session_registered = False
        graph_expedient = prepare_expedient(
            module_code="BECAS",
            identification=_clean(contract.NumeroIdentificacion),
            student_code=student_code,
            student_name=_clean(contract.Estudiante),
            student_email=_clean(contract.Correo),
            base_origin="INTEC_FINANZAS_INSTITUCIONAL",
            schema_origin="bec",
            table_origin="ContratoBeca",
            origin_id=f"{student_code_text}-{period_code}",
            expedient_code=f"BECA-{period_code}",
            audit_user=current_user.login,
        )
        upload_folder = f"{graph_expedient['folder_path']}/CONTRATO DE BECA"
        ensure_folder(upload_folder)
        cloud_filename = _safe_filename(
            f"CONTRATO-BECA-FIRMADO-{_clean(contract.NumeroContrato)}.pdf"
        )
        graph_path = f"{upload_folder}/{cloud_filename}"
        register_upload_session(
            session_id=session_id,
            expedient_graph_id=int(graph_expedient["expedient_graph_id"]),
            document_type_code="CONTRATO_BECA_FIRMADO",
            original_filename=filename,
            cloud_filename=cloud_filename,
            graph_path=graph_path,
            content_type="application/pdf",
            expected_size=len(content),
            upload_url="",
            expires_at=None,
            audit_user=current_user.login,
            max_expected_size=_SCHOLARSHIP_CONTRACT_MAX_BYTES,
        )
        session_registered = True
        graph_item = upload_bytes(graph_path, content, "application/pdf")
        graph_document = complete_upload_session(
            session_id=session_id,
            graph_item=graph_item,
            edit_deadline=None,
            audit_user=current_user.login,
            append_document=False,
        )
        document_id = int(graph_document["document_graph_id"])
        set_document_origin(document_id, contract_id)

        with get_finance_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bec.ContratoBeca
                   SET GraphDocumentoId = ?, GraphWebUrl = ?, NombreArchivoFirmado = ?,
                       HashFirmado = ?, FechaCargaExpediente = SYSDATETIME(),
                       UsuarioCargaExpediente = ?, EstadoExpedienteCodigo = 'CARGADO',
                       EstadoCodigo = 'ARCHIVADO'
                 WHERE ContratoBecaId = ?
                """,
                document_id,
                _clean(graph_document.get("graph_web_url")),
                cloud_filename,
                sha256(content).hexdigest(),
                current_user.login,
                contract_id,
            )
            conn.commit()
        return {
            "ok": True,
            "contrato_id": contract_id,
            "numero_contrato": _clean(contract.NumeroContrato),
            "expediente_documento_id": document_id,
            "expediente_url": _clean(graph_document.get("graph_web_url")),
            "nombre_archivo": cloud_filename,
            "estado_expediente": "CARGADO",
        }
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        if "session_registered" in locals() and session_registered:
            try:
                mark_upload_error(session_id, str(exc), current_user.login)
            except (RuntimeError, pyodbc.Error):
                pass
        if "graph_item" in locals() and graph_item and _clean(graph_item.get("id")):
            try:
                delete_item(_clean(graph_item.get("id")))
            except httpx.HTTPError:
                pass
        raise HTTPException(status_code=502, detail=f"Microsoft OneDrive no pudo archivar el contrato: {exc}") from exc
    except (RuntimeError, ValueError, pyodbc.Error) as exc:
        if "session_registered" in locals() and session_registered:
            try:
                mark_upload_error(session_id, str(exc), current_user.login)
            except (RuntimeError, pyodbc.Error):
                pass
        if "graph_item" in locals() and graph_item and _clean(graph_item.get("id")):
            try:
                delete_item(_clean(graph_item.get("id")))
            except httpx.HTTPError:
                pass
        status_code = 503 if isinstance(exc, (RuntimeError, pyodbc.Error)) else 400
        raise HTTPException(status_code=status_code, detail=f"No se pudo archivar el contrato de beca: {exc}") from exc


@router.post("/becas/{beca_id}/aprobar")
def approve_pending_preinscription_scholarship(
    beca_id: int,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> dict[str, Any]:
    try:
        result = _approve_financial_scholarship(beca_id, current_user.login)
        return {
            "ok": True,
            "message": "Beca aprobada. El estudiante puede continuar con la matrícula.",
            **result,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo aprobar la beca: {exc}") from exc


@router.get("/{num}/beca")
def get_preinscription_scholarship(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            row = _fetch_preinscription_row(conn.cursor(), num.strip())
        return {"ok": True, **_preinscription_scholarship_status(row)}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo consultar la aprobación de la beca: {exc}") from exc


@router.post("/{num}/beca/aprobar")
def approve_preinscription_scholarship(
    num: str,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            row = _fetch_preinscription_row(conn.cursor(), num.strip())
        status_data = _preinscription_scholarship_status(row)
        beca_id = status_data.get("beca_id")
        if not beca_id:
            raise HTTPException(status_code=404, detail="La preinscripción no tiene una solicitud de beca")
        if float(status_data.get("porcentaje_beca") or 0) <= _SCHOLARSHIP_APPROVAL_THRESHOLD:
            raise HTTPException(status_code=400, detail="Esta beca no requiere aprobación especial")
        _approve_financial_scholarship(int(beca_id), current_user.login)
        refreshed = _preinscription_scholarship_status(row)
        return {"ok": True, "message": "Beca aprobada. El proceso puede continuar.", **refreshed}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo aprobar la beca: {exc}") from exc


@router.post("/{num}/cabecera")
def register_preinscription_cabecera(
    num: str,
    payload: PreinscriptionCabeceraPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            codigo_estud = _resolve_preinscription_student_code(row)
            cod_anio_basica = _resolve_preinscription_required_code(row, "codcarrera", "carrera")
            codigo_periodo = _resolve_preinscription_required_code(row, "codperiodo", "periodo")
            cod_jornada = _int_value(getattr(row, "codjornada", None)) or 0
            cod_modalidad = _int_value(getattr(row, "codmodalida", None)) or 0
            fecha_pago = payload.fecha_pago or date.today().isoformat()
            if _is_english_career(cod_anio_basica, getattr(row, "Nombre_Basica", "")):
                scholarship_type, scholarship_percentage = "", 0.0
            else:
                scholarship_type, scholarship_percentage = _validate_scholarship_selection(
                    payload.tipo_beca, payload.porcentaje_beca
                )
            payload.tipo_beca = scholarship_type
            payload.porcentaje_beca = scholarship_percentage
            if scholarship_type and scholarship_percentage <= 0:
                raise HTTPException(status_code=400, detail='Ingrese el porcentaje otorgado para la beca seleccionada')
            plan = _payment_plan(payload, _clean(getattr(row, "Nombre_Basica", "")))
            payload.valor = float(plan["total"])
            payload.costo_semestre = float(plan["costo_semestre"])
            payload.inscrip_valor = float(plan["valor_academico"])
            payload.matri_valor = float(plan["valor_matricula"])
            if scholarship_percentage > _SCHOLARSHIP_APPROVAL_THRESHOLD:
                approval = _preinscription_scholarship_status(row)
                if _clean(approval.get("estado")).upper() != "APROBADA":
                    raise HTTPException(
                        status_code=409,
                        detail="La beca superior al 15% está pendiente de aprobación. No se puede continuar con la matrícula.",
                    )
            _sync_preinscription_student_records(cursor, row, codigo_estud, codigo_periodo)

            cursor.execute(
                """
                SELECT TOP (1) Num_Matricula
                FROM dbo.CABECERA_MATRICULA
                WHERE codigo_estud = ?
                  AND cod_anio_Basica = ?
                  AND codigo_periodo = ?
                ORDER BY TRY_CONVERT(int, Num_Matricula) DESC
                """,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
            )
            cabecera_row = cursor.fetchone()
            if cabecera_row:
                num_matricula = int(cabecera_row.Num_Matricula or 0) or _next_student_matricula(cursor, codigo_estud)
                cursor.execute(
                    """
                    UPDATE dbo.CABECERA_MATRICULA
                    SET fecha_pago = ?,
                        valor = ?,
                        InscripValor = ?,
                        MatriValor = ?,
                        Cuota1 = ?,
                        Beca = ?,
                        Descuento = ?,
                        num_dep_transf = ?,
                        ControlMatricula = ?,
                        codjornada = ?,
                        codmodalidad = ?
                    WHERE codigo_estud = ?
                      AND cod_anio_Basica = ?
                      AND codigo_periodo = ?
                    """,
                    fecha_pago,
                    payload.valor,
                    payload.inscrip_valor,
                    payload.matri_valor,
                    plan["cuota_valor"],
                    plan["beca_valor"],
                    plan["descuento"],
                    _clean(payload.no_deposito)[:30],
                    payload.control_matricula,
                    cod_jornada,
                    cod_modalidad,
                    codigo_estud,
                    cod_anio_basica,
                    codigo_periodo,
                )
                action = "ACTUALIZADA"
            else:
                num_matricula = _next_student_matricula(cursor, codigo_estud)
                cursor.execute(
                    """
                    INSERT INTO dbo.CABECERA_MATRICULA (
                        codigo_estud, cod_anio_Basica, codigo_periodo, Num_Matricula, fecha_pago,
                        valor, num_dep_transf, InscripValor, MatriValor, Cuota1, RecargoMatricula, Beca, Descuento,
                        Jornada, AyudaEcono, ControlMatricula, ValorNivelacion, codhorario, codmodalidad,
                        coddias, codjornada, codestadoMat, reingreso,
                        Descuentoprontopago, Descuentoreferidos
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '', 0, ?, 0, 0, ?, 0, ?, 0, 0, 0, 0)
                    """,
                    codigo_estud,
                    cod_anio_basica,
                    codigo_periodo,
                    num_matricula,
                    fecha_pago,
                    payload.valor,
                    _clean(payload.no_deposito)[:30],
                    payload.inscrip_valor,
                    payload.matri_valor,
                    plan["cuota_valor"],
                    plan["beca_valor"],
                    plan["descuento"],
                    payload.control_matricula,
                    cod_modalidad,
                    cod_jornada,
                )
                action = "INSERTADA"
            cursor.execute(
                """
                SELECT TOP (1)
                    Num_Matricula,
                    numcodigo
                FROM dbo.CABECERA_MATRICULA
                WHERE codigo_estud = ?
                  AND cod_anio_Basica = ?
                  AND codigo_periodo = ?
                ORDER BY numcodigo DESC
                """,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
            )
            cabecera_code_row = cursor.fetchone()
            codigo_documentacion = (
                _clean(getattr(cabecera_code_row, "numcodigo", ""))
                or _clean(getattr(cabecera_code_row, "Num_Matricula", ""))
                or str(num_matricula)
            )
            _sync_student_scholarship(
                cursor,
                codigo_estud,
                payload.tipo_beca,
                float(plan["porcentaje_beca"]),
                float(plan["beca_valor"]),
            )
            _sync_registration_payment(
                cursor,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
                fecha_pago,
                payload,
                current_user.login,
            )
            convenio_url = _write_convenio_document(row, codigo_documentacion, plan, payload, fecha_pago)
            if convenio_url:
                cursor.execute(
                    """
                    UPDATE dbo.PREINSCRIPCION
                    SET urlconvenio = ?
                    WHERE TRY_CONVERT(varchar(50), num) = ?
                    """,
                    convenio_url,
                    clean_num,
                )
                _sync_cabecera_documents(
                    cursor,
                    codigo_estud,
                    cod_anio_basica,
                    codigo_periodo,
                    {"urlconvenio": convenio_url},
                )
            conn.commit()
            refreshed = _fetch_preinscription_row(cursor, clean_num)
        finance_sync = _sync_financial_preinscription(
            codestu=codigo_estud,
            cedula=_clean(getattr(row, "Cedula", "")),
            student_name=_clean(getattr(row, "Apellidos_nombre", "")),
            codperiodo=codigo_periodo,
            codcarrera=cod_anio_basica,
            codmodalidad=cod_modalidad,
            codjornada=cod_jornada,
            correo=_clean(getattr(row, "correo", ""))[:150],
            telefono=_clean(getattr(row, "telefono", ""))[:50],
            codasesor=_clean(getattr(row, "codasesor", "")),
            usuario=current_user.login[:80],
            tipo_beca=_clean(payload.tipo_beca),
            porcentaje_beca=float(plan["porcentaje_beca"]),
            valor_beca=float(plan["beca_valor"]),
            motivo_beca="Beca confirmada al generar la cabecera de matrícula.",
        )
        complement_sync = sync_preinscription_complements(
            {
                "origen_id": clean_num,
                "codigo_estud": codigo_estud,
                "cedula": _clean(getattr(row, "Cedula", "")),
                "nombre": _clean(getattr(row, "Apellidos_nombre", "")),
                "codigo_periodo": codigo_periodo,
                "codigo_carrera": cod_anio_basica,
                "codigo_modalidad": cod_modalidad,
                "codigo_jornada": cod_jornada,
                "codigo_asesor": _clean(getattr(row, "codasesor", "")),
                "correo": _clean(getattr(row, "correo", ""))[:150],
                "telefono": _clean(getattr(row, "telefono", ""))[:50],
                "estado": "CABECERA_GENERADA",
                "url_cedula": _clean(getattr(row, "urlcedula", "")),
                "url_titulo": _clean(getattr(row, "urltitulo", "")),
                "url_deposito": _clean(getattr(row, "urldeposito", "")),
                "url_convenio": convenio_url or _clean(getattr(row, "urlconvenio", "")),
                "tiene_beca": bool(_clean(payload.tipo_beca) and float(plan["porcentaje_beca"]) > 0),
                "usuario": current_user.login[:80],
            },
            finance_sync,
            event_type="PREINSCRIPCION_CABECERA",
        )
        response = _cabecera_response_from_row(refreshed)
        response["message"] = (
            "Cabecera de matrícula registrada correctamente. Convenio generado."
            if convenio_url
            else "Cabecera de matrícula registrada correctamente."
        )
        response["action"] = action
        response["num_matricula"] = str(num_matricula)
        response["codigo_documentacion"] = codigo_documentacion
        response["convenio_url"] = convenio_url
        response["finanzas"] = finance_sync
        response["complementos"] = complement_sync
        return response
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al registrar la cabecera de matrícula: {exc}") from exc


@router.put("/{num}/seguimiento")
def update_preinscription_followup(
    num: str,
    payload: PreinscriptionFollowupPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            cod_lecontacto = _optional_int_payload(
                payload.cod_lecontacto,
                _int_value(getattr(row, "codLecontacto", None)) or 1,
            )
            cursor.execute(
                """
                UPDATE dbo.PREINSCRIPCION
                SET contacte = ?,
                    hora = ?,
                    Observacioncontacto = ?,
                    ObservacionIngreso = ?,
                    codLecontacto = ?,
                    codDeseaIngresar = ?,
                    codComoConoce = ?,
                    coddescconve = ?,
                    coddescconvevalor = ?,
                    coddescdeptransf = ?,
                    Nom_Representante = ?,
                    Num_Representante = ?,
                    Prematricula = ?,
                    ProcesoFinalilzado = ?,
                    ControlIngreso = ?,
                    Correoenviado = ?,
                    asignado = ?
                WHERE TRY_CONVERT(varchar(50), num) = ?
                """,
                _clean(payload.contacte)[:50],
                _clean(payload.hora)[:50],
                _clean(payload.observacion_contacto)[:500],
                _clean(payload.observacion_ingreso)[:500],
                cod_lecontacto,
                _optional_int_payload(payload.cod_desea_ingresar),
                _optional_int_payload(payload.cod_como_conoce),
                _optional_int_payload(payload.coddescconve),
                _optional_int_payload(payload.coddescconvevalor),
                _optional_int_payload(payload.coddescdeptransf),
                _clean(payload.nom_representante)[:100],
                _clean(payload.num_representante)[:10],
                1 if payload.prematricula else 0,
                1 if payload.proceso_finalizado else 0,
                1 if payload.control_ingreso else 0,
                1 if payload.correo_enviado else 0,
                1 if payload.asignado else 0,
                clean_num,
            )
            conn.commit()
            refreshed = _fetch_preinscription_row(cursor, clean_num)
        return {
            "ok": True,
            "message": 'Seguimiento de preinscripción actualizado.',
            "item": _preinscription_item(refreshed),
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al actualizar el seguimiento de la preinscripción: {exc}") from exc


@router.put("/{num}/documentos")
def update_preinscription_documents(
    num: str,
    payload: PreinscriptionDocumentsPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            current_row = _fetch_preinscription_row(cursor, clean_num)
            current_item = _preinscription_item(current_row)
            if not current_item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail='Primero, registre la cabecera de matrícula para obtener el código de documentación.',
                )
            codigo_estud = _resolve_preinscription_student_code(current_row)
            cod_anio_basica = _resolve_preinscription_required_code(current_row, "codcarrera", "carrera")
            codigo_periodo = _resolve_preinscription_required_code(current_row, "codperiodo", "periodo")
            cursor.execute(
                """
                UPDATE dbo.PREINSCRIPCION
                SET urlcedula = ?,
                    urltitulo = ?,
                    urldeposito = ?,
                    urlconvenio = ?
                WHERE TRY_CONVERT(varchar(50), num) = ?
                """,
                _document_url(payload.urlcedula),
                _document_url(payload.urltitulo),
                _document_url(payload.urldeposito),
                _document_url(payload.urlconvenio),
                clean_num,
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail='No se encontró la preinscripción seleccionada')
            _sync_cabecera_documents(
                cursor,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
                {
                    "urlcedula": payload.urlcedula,
                    "urltitulo": payload.urltitulo,
                    "urldeposito": payload.urldeposito,
                    "urlconvenio": payload.urlconvenio,
                },
            )
            conn.commit()

            row = _fetch_preinscription_row(cursor, clean_num)
        if not row:
            raise HTTPException(status_code=404, detail='No se encontró la preinscripción actualizada')
        item = _preinscription_item(row)
        return {
            "ok": True,
            "message": 'Documentos de preinscripción actualizados.',
            "item": item,
            "en_cabecera_matricula": item["en_cabecera_matricula"],
            "codigo_documentacion": item["cabecera"].get("numcodigo") or item["cabecera"].get("num_matricula") or "",
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al actualizar los documentos de la preinscripción: {exc}") from exc


@router.post("/{num}/documentos/{document_field}/upload")
async def upload_preinscription_document(
    num: str,
    document_field: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    field = document_field.strip().lower()
    if field not in _DOCUMENT_FIELDS:
        raise HTTPException(status_code=400, detail='Campo de documento inválido')
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    extension_name, content = await read_secure_upload(
        file,
        maximum=_PREINSCRIPTION_DOCUMENT_MAX_BYTES,
        label="documento de preinscripción",
    )
    extension_name = _safe_filename(extension_name)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            item = _preinscription_item(row)
            if not item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail='Primero, registre la cabecera de matrícula para obtener el código de documentación.',
                )
            code = item["cabecera"].get("numcodigo") or item["cabecera"].get("num_matricula") or clean_num
            target_dir = _PREINSCRIPTION_UPLOAD_ROOT / _safe_filename(str(code))
            target_dir.mkdir(parents=True, exist_ok=True)
            target_name = f"{field}-{extension_name}"
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/preinscripcion/{_safe_filename(str(code))}/{target_name}"
            cursor.execute(
                f"""
                UPDATE dbo.PREINSCRIPCION
                SET {field} = ?
                WHERE TRY_CONVERT(varchar(50), num) = ?
                """,
                relative_url,
                clean_num,
            )
            codigo_estud = _resolve_preinscription_student_code(row)
            cod_anio_basica = _resolve_preinscription_required_code(row, "codcarrera", "carrera")
            codigo_periodo = _resolve_preinscription_required_code(row, "codperiodo", "periodo")
            _sync_cabecera_documents(
                cursor,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
                {field: relative_url},
            )
            conn.commit()
            refreshed = _fetch_preinscription_row(cursor, clean_num)
        refreshed_item = _preinscription_item(refreshed)
        return {
            "ok": True,
            "message": "Documento subido correctamente.",
            "field": field,
            "url": relative_url,
            "item": refreshed_item,
            "codigo_documentacion": refreshed_item["cabecera"].get("numcodigo") or refreshed_item["cabecera"].get("num_matricula") or "",
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al subir el documento de la preinscripción: {exc}") from exc


@router.get("/{num}/foto-carnet")
def get_preinscription_carnet_photo_status(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            student = _fetch_student_for_photo(cursor, row)
            status = _photo_status_payload(cursor, getattr(student, "codigo_estud"))
            conn.commit()
        return {"ok": True, "foto": status}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error al consultar la foto para el carné: {exc}") from exc


@router.post("/{num}/foto-carnet/upload")
async def upload_preinscription_carnet_photo(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    raw_name, content = await read_secure_upload(
        file,
        maximum=_PHOTO_MAX_BYTES,
        label="foto para carné",
        allowed_extensions={".jpg", ".jpeg", ".png", ".webp"},
        allowed_content_types={
            "application/octet-stream",
            "image/jpeg",
            "image/png",
            "image/webp",
        },
    )
    original_name = _safe_filename(raw_name)
    mime_type = _photo_mime_type(original_name)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            item = _preinscription_item(row)
            if not item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail='Primero registra la cabecera de matrícula para crear el estudiante antes de subir la foto',
                )
            student = _fetch_student_for_photo(cursor, row)
            _ensure_carnet_photo_tables(cursor)
            code = getattr(student, "codigo_estud")
            cedula = _clean(getattr(student, "Cedula_Est", ""))
            target_dir = _PREINSCRIPTION_UPLOAD_ROOT / _safe_filename(str(item["cabecera"].get("numcodigo") or clean_num)) / "foto-carnet"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_name = f"foto-carnet-{datetime.now().strftime('%Y%m%d%H%M%S')}-{original_name}"
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/preinscripcion/{_safe_filename(str(item['cabecera'].get('numcodigo') or clean_num))}/foto-carnet/{target_name}"

            cursor.execute(
                """
                SELECT TOP (1) id_solicitud_foto, id_imagen
                FROM dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                  AND estado = 'PENDIENTE'
                ORDER BY fecha_solicitud DESC
                """,
                code,
            )
            pending = cursor.fetchone()
            if pending:
                image_id = getattr(pending, "id_imagen")
                request_id = getattr(pending, "id_solicitud_foto")
                cursor.execute(
                    """
                    UPDATE dbo.ESTUDIANTE_IMAGEN
                    SET ruta_archivo = ?,
                        nombre_original = ?,
                        mime_type = ?,
                        tamanio_bytes = ?,
                        es_principal = 0,
                        estado = 'A',
                        fecha_actualizacion = SYSDATETIME()
                    WHERE id_imagen = ?
                    """,
                    relative_url,
                    original_name,
                    mime_type,
                    len(content),
                    image_id,
                )
                cursor.execute(
                    """
                    UPDATE dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                    SET observacion_estudiante = ?,
                        observacion_admin = NULL,
                        usuario_solicita = ?,
                        fecha_solicitud = SYSDATETIME(),
                        usuario_revisa = NULL,
                        fecha_revision = NULL
                    WHERE id_solicitud_foto = ?
                    """,
                    "Foto reemplazada para revisión previa.",
                    _clean(current_user.login)[:100],
                    request_id,
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO dbo.ESTUDIANTE_IMAGEN (
                        codigo_estud, Cedula_Est, tipo_imagen, titulo, descripcion,
                        nombre_original, ruta_archivo, mime_type, tamanio_bytes,
                        es_principal, estado, usuario_creacion
                    )
                    OUTPUT INSERTED.id_imagen
                    VALUES (?, ?, 'FOTO_CARNET', ?, ?, ?, ?, ?, ?, 0, 'A', ?)
                    """,
                    code,
                    cedula,
                    "Foto para el carné pendiente",
                    "Imagen cargada desde preinscripción para aprobación previa",
                    original_name,
                    relative_url,
                    mime_type,
                    len(content),
                    _clean(current_user.login)[:100],
                )
                image_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD (
                        codigo_estud, Cedula_Est, id_imagen, estado,
                        observacion_estudiante, usuario_solicita
                    )
                    VALUES (?, ?, ?, 'PENDIENTE', ?, ?)
                    """,
                    code,
                    cedula,
                    image_id,
                    "Foto cargada para revisión previa.",
                    _clean(current_user.login)[:100],
                )

            status = _photo_status_payload(cursor, code)
            conn.commit()
        return {
            "ok": True,
            "message": "Foto cargada. Queda pendiente de aprobación antes de usarla en el carné.",
            "foto": status,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al subir la foto para el carné: {exc}") from exc


@router.post("/{num}/foto-carnet/{request_id}/aprobar")
def approve_preinscription_carnet_photo(
    num: str,
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            student = _fetch_student_for_photo(cursor, row)
            _ensure_carnet_photo_tables(cursor)
            cursor.execute(
                """
                SELECT TOP (1) id_solicitud_foto, codigo_estud, id_imagen, estado
                FROM dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                WHERE id_solicitud_foto = ?
                  AND TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                """,
                request_id,
                getattr(student, "codigo_estud"),
            )
            request_row = cursor.fetchone()
            if not request_row:
                raise HTTPException(status_code=404, detail='No se encontró la solicitud de foto seleccionada')
            if _clean(getattr(request_row, "estado", "")).upper() == "RECHAZADA":
                raise HTTPException(status_code=400, detail="No se puede aprobar una solicitud rechazada")

            codigo_estud = getattr(request_row, "codigo_estud")
            image_id = getattr(request_row, "id_imagen")
            cursor.execute(
                """
                UPDATE dbo.ESTUDIANTE_IMAGEN
                SET es_principal = 0
                WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                  AND tipo_imagen = 'FOTO_CARNET'
                """,
                codigo_estud,
            )
            cursor.execute(
                """
                UPDATE dbo.ESTUDIANTE_IMAGEN
                SET es_principal = 1,
                    estado = 'A',
                    fecha_actualizacion = SYSDATETIME()
                WHERE id_imagen = ?
                """,
                image_id,
            )
            cursor.execute(
                """
                UPDATE dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                SET estado = 'APROBADA',
                    observacion_admin = ?,
                    usuario_revisa = ?,
                    fecha_revision = SYSDATETIME()
                WHERE id_solicitud_foto = ?
                """,
                "Foto aprobada para el carné",
                _clean(current_user.login)[:100],
                request_id,
            )
            status = _photo_status_payload(cursor, codigo_estud)
            conn.commit()
        return {"ok": True, "message": "Foto aprobada para el carné.", "foto": status}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al aprobar la foto para el carné: {exc}") from exc


@router.post("/{num}/foto-carnet/{request_id}/rechazar")
def reject_preinscription_carnet_photo(
    num: str,
    request_id: int,
    payload: PreinscriptionPhotoReviewPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            student = _fetch_student_for_photo(cursor, row)
            _ensure_carnet_photo_tables(cursor)
            cursor.execute(
                """
                SELECT TOP (1) id_solicitud_foto, codigo_estud, id_imagen
                FROM dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                WHERE id_solicitud_foto = ?
                  AND TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                """,
                request_id,
                getattr(student, "codigo_estud"),
            )
            request_row = cursor.fetchone()
            if not request_row:
                raise HTTPException(status_code=404, detail='No se encontró la solicitud de foto seleccionada')
            cursor.execute(
                """
                UPDATE dbo.ESTUDIANTE_IMAGEN
                SET es_principal = 0,
                    estado = 'I',
                    fecha_actualizacion = SYSDATETIME()
                WHERE id_imagen = ?
                """,
                getattr(request_row, "id_imagen"),
            )
            cursor.execute(
                """
                UPDATE dbo.ESTUDIANTE_FOTO_CARNET_SOLICITUD
                SET estado = 'RECHAZADA',
                    observacion_admin = ?,
                    usuario_revisa = ?,
                    fecha_revision = SYSDATETIME()
                WHERE id_solicitud_foto = ?
                """,
                (_clean(payload.observacion) or "Foto rechazada. Debe cargar una nueva imagen.")[:500],
                _clean(current_user.login)[:100],
                request_id,
            )
            status = _photo_status_payload(cursor, getattr(request_row, "codigo_estud"))
            conn.commit()
        return {"ok": True, "message": "Foto rechazada. El estudiante debe subir una nueva imagen.", "foto": status}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al rechazar la foto para el carné: {exc}") from exc


@router.delete("/{num}/revertir")
def revert_preinscription_process(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail='Debe indicar el identificador num de la preinscripción')

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            codigo_estud = _resolve_preinscription_student_code(row)
            cod_anio_basica = _resolve_preinscription_required_code(row, "codcarrera", "carrera")
            codigo_periodo = _resolve_preinscription_required_code(row, "codperiodo", "periodo")
            cedula = re.sub(r"\D+", "", _clean(getattr(row, "Cedula", "")))

            deleted: dict[str, int] = {}

            cursor.execute(
                """
                IF OBJECT_ID(N'dbo.REGISTROPAGOS', N'U') IS NOT NULL
                BEGIN
                    DELETE FROM dbo.REGISTROPAGOS
                    WHERE TRY_CONVERT(varchar(50), Codestu) = TRY_CONVERT(varchar(50), ?)
                      AND TRY_CONVERT(varchar(50), codperiodo) = TRY_CONVERT(varchar(50), ?)
                      AND TRY_CONVERT(varchar(50), cod_anio_Basica) = TRY_CONVERT(varchar(50), ?)
                END
                """,
                codigo_estud,
                codigo_periodo,
                cod_anio_basica,
            )
            deleted["REGISTROPAGOS"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                DELETE FROM dbo.CARRERAXESTUD
                WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), cod_anio_Basica) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), codigo_periodo) = TRY_CONVERT(varchar(50), ?)
                """,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
            )
            deleted["CARRERAXESTUD"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                DELETE FROM dbo.CABECERA_MATRICULA
                WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), cod_anio_Basica) = TRY_CONVERT(varchar(50), ?)
                  AND TRY_CONVERT(varchar(50), codigo_periodo) = TRY_CONVERT(varchar(50), ?)
                """,
                codigo_estud,
                cod_anio_basica,
                codigo_periodo,
            )
            deleted["CABECERA_MATRICULA"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                IF OBJECT_ID(N'dbo.DATOSFACTURA', N'U') IS NOT NULL
                BEGIN
                    DELETE FROM dbo.DATOSFACTURA
                    WHERE TRY_CONVERT(varchar(50), CODESTUD) = TRY_CONVERT(varchar(50), ?)
                       OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), CEDESTUD))) = LTRIM(RTRIM(?))
                END
                """,
                str(codigo_estud)[:10],
                cedula[:10],
            )
            deleted["DATOSFACTURA"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                IF OBJECT_ID(N'dbo.CorreosEstudIntec', N'U') IS NOT NULL
                BEGIN
                    DELETE FROM dbo.CorreosEstudIntec
                    WHERE TRY_CONVERT(varchar(50), codestud) = TRY_CONVERT(varchar(50), ?)
                END
                """,
                codigo_estud,
            )
            deleted["CorreosEstudIntec"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM dbo.CABECERA_MATRICULA
                    WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                )
                AND NOT EXISTS (
                    SELECT 1 FROM dbo.CARRERAXESTUD
                    WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                )
                BEGIN
                    DELETE FROM dbo.DATOS_ESTUD
                    WHERE TRY_CONVERT(varchar(50), codigo_estud) = TRY_CONVERT(varchar(50), ?)
                       OR LTRIM(RTRIM(TRY_CONVERT(varchar(50), Cedula_Est))) = LTRIM(RTRIM(?))
                END
                """,
                codigo_estud,
                codigo_estud,
                codigo_estud,
                cedula,
            )
            deleted["DATOS_ESTUD"] = max(cursor.rowcount, 0)

            cursor.execute(
                """
                DELETE FROM dbo.PREINSCRIPCION
                WHERE TRY_CONVERT(varchar(50), num) = ?
                """,
                clean_num,
            )
            deleted["PREINSCRIPCION"] = max(cursor.rowcount, 0)
            if deleted["PREINSCRIPCION"] == 0:
                raise HTTPException(status_code=404, detail='No se encontró la preinscripción seleccionada')

            conn.commit()
        return {
            "ok": True,
            "message": 'Proceso de inscripción revertido correctamente.',
            "deleted": deleted,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al revertir la preinscripción: {exc}") from exc
