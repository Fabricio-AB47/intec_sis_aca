import calendar
from datetime import date, datetime
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Annotated, Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pyodbc
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.core.security import SessionUser, require_roles
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
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"
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


class ScholarshipContractGeneratePayload(BaseModel):
    beca_ids: list[int]
    codigo_periodo: str


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _is_no_scholarship(value: Any) -> bool:
    normalized = _clean(value).upper()
    return normalized in {"", "SIN BECA", "NO APLICA", "NINGUNA"}


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


def _normalized_scholarship(tipo_beca: Any, porcentaje_beca: Any, valor_beca: Any = 0) -> tuple[str, float, float]:
    scholarship_type = _clean(tipo_beca)
    if _is_no_scholarship(scholarship_type):
        return "", 0.0, 0.0
    percentage = 100.0 if _is_mintel_scholarship(scholarship_type) else min(max(float(porcentaje_beca or 0), 0), 100)
    scholarship_value = max(float(valor_beca or 0), 0)
    return scholarship_type, percentage, scholarship_value


def _ensure_scholarship_configuration_table() -> None:
    legacy_rows: list[tuple[str, float, float]] = []
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
    except pyodbc.Error:
        legacy_rows = []

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
        if is_empty:
            seeds = legacy_rows or [
                ("Beca Intec", 0.0, 100.0),
                ("Beca Futuro Femenino", 100.0, 100.0),
                ("Beca Mintel", 100.0, 100.0),
                ("Suzuki", 100.0, 100.0),
            ]
            for name, minimum, maximum in seeds:
                is_mintel = _is_mintel_scholarship(name)
                is_variable = not is_mintel and abs(maximum - minimum) > 0.001
                fixed_percentage = 100.0 if is_mintel else (None if is_variable else maximum)
                cursor.execute(
                    """
                    INSERT INTO cat.ConfiguracionBecaPreinscripcion
                        (Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo,
                         PorcentajeMaximo, Protegida, Activo, UsuarioCreacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'MIGRACION_INICIAL')
                    """,
                    _scholarship_code(name),
                    name,
                    int(is_variable),
                    fixed_percentage,
                    100.0 if is_mintel else minimum,
                    100.0 if is_mintel else maximum,
                    int(is_mintel),
                )
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


def _build_scholarship_contract_pdf(
    item: dict[str, Any],
    contract_number: str,
    contract_date: date,
) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=0.95 * cm,
        bottomMargin=1.15 * cm,
        title=f"Contrato de beca {contract_number}",
        author="Instituto Superior Tecnológico INTEC",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ScholarshipContractTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
    )
    body_style = ParagraphStyle(
        "ScholarshipContractBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.7,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#111111"),
        spaceAfter=3.2,
    )
    small_style = ParagraphStyle(
        "ScholarshipContractSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
    )
    cell_label = ParagraphStyle(
        "ScholarshipContractCellLabel",
        parent=small_style,
        alignment=0,
        fontName="Helvetica-Bold",
        fontSize=6.3,
        leading=7.4,
    )
    cell_value = ParagraphStyle(
        "ScholarshipContractCellValue",
        parent=cell_label,
        fontName="Helvetica",
    )

    def paragraph(value: Any, style: ParagraphStyle = cell_value) -> Paragraph:
        return Paragraph(escape(_clean(value) or "-"), style)

    def draw_contract_background(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_width, page_height = A4
        canvas.setFillColor(colors.HexColor("#F2DEDE"))
        canvas.setStrokeColor(colors.HexColor("#F2DEDE"))
        canvas.circle(-0.15 * cm, page_height * 0.55, 3.7 * cm, fill=1, stroke=0)
        path = canvas.beginPath()
        path.moveTo(0, page_height * 0.23)
        path.lineTo(6.3 * cm, page_height * 0.23)
        path.lineTo(8.8 * cm, page_height * 0.14)
        path.lineTo(4.8 * cm, 0)
        path.lineTo(0, 0)
        path.close()
        canvas.drawPath(path, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#9E1B17"))
        canvas.setLineWidth(0.8)
        canvas.line(doc.leftMargin, 0.78 * cm, page_width - doc.rightMargin, 0.78 * cm)
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(doc.leftMargin, 0.46 * cm, "www.intec.edu.ec")
        canvas.drawCentredString(page_width / 2, 0.46 * cm, "Contrato de beca institucional")
        canvas.drawRightString(page_width - doc.rightMargin, 0.46 * cm, f"N.° {contract_number}")
        canvas.restoreState()

    story: list[Any] = []
    logo: Any = _SvgLogo(_LOGO_PATH, 4.2 * cm) if _LOGO_PATH.exists() else paragraph("INTEC", title_style)
    header_right = Table(
        [
            [Paragraph(f"CONTRATO DE BECA - No. {escape(contract_number)}", title_style)],
            [Paragraph("INSTITUTO SUPERIOR TECNOLÓGICO INTEC", small_style)],
            [Paragraph(f"EMISIÓN: {contract_date.strftime('%d/%m/%Y')}", small_style)],
        ],
        colWidths=[12.0 * cm],
    )
    header_right.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#555555")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    header = Table([[logo, header_right]], colWidths=[4.8 * cm, 12.0 * cm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([header, Spacer(1, 0.12 * cm)])

    student_name = _clean(item.get("estudiante")) or "la persona beneficiaria"
    story.append(
        Paragraph(
            "Comparecen a la celebración del presente contrato el Instituto Superior Tecnológico INTEC y "
            f"<b>{escape(student_name)}</b>, en calidad de persona beneficiaria, quienes acuerdan las "
            "condiciones detalladas a continuación:",
            body_style,
        )
    )

    approved_percentage = f"{float(item.get('porcentaje_beca') or 0):g}%"
    details = [
        [paragraph("Nombres y apellidos", cell_label), paragraph(student_name), "", paragraph("N.° de beca", cell_label), paragraph(contract_number)],
        [paragraph("Identificación", cell_label), paragraph(item.get("cedula")), "", paragraph("Teléfono", cell_label), paragraph(item.get("telefono"))],
        [paragraph("Nivel de formación", cell_label), paragraph(item.get("nivel_formacion") or "Tecnología superior"), "", paragraph("Carrera", cell_label), paragraph(item.get("carrera") or item.get("codigo_carrera"))],
        [paragraph("Beca", cell_label), paragraph(item.get("tipo_beca")), "", paragraph("Discapacidad", cell_label), paragraph(f"{_scholarship_disability(item.get('discapacidad'))} - {_scholarship_disability_type(item)}")],
        [paragraph("Porcentaje / tipo", cell_label), paragraph(approved_percentage), paragraph(_format_money(item.get("valor_beca"))), paragraph("Porcentaje aprobado", cell_label), paragraph(approved_percentage)],
        [paragraph("Período de adjudicación", cell_label), paragraph(item.get("periodo") or item.get("codigo_periodo")), "", paragraph("Correo", cell_label), paragraph(item.get("correo"))],
    ]
    details_table = Table(details, colWidths=[3.0 * cm, 4.0 * cm, 2.4 * cm, 3.3 * cm, 4.1 * cm])
    details_table.setStyle(
        TableStyle(
            [
                ("SPAN", (1, 0), (2, 0)),
                ("SPAN", (1, 1), (2, 1)),
                ("SPAN", (1, 2), (2, 2)),
                ("SPAN", (1, 3), (2, 3)),
                ("SPAN", (1, 5), (2, 5)),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F1F1")),
                ("BACKGROUND", (3, 0), (3, -1), colors.HexColor("#F1F1F1")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#777777")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    story.extend([details_table, Spacer(1, 0.14 * cm)])

    scholarship_name = escape(_clean(item.get("tipo_beca")) or "la beca registrada")
    clauses = [
        ("PRIMERA. OBJETO", f"INTEC concede a <b>{escape(student_name)}</b> el beneficio <b>{scholarship_name}</b>, aprobado y registrado para el período académico señalado."),
        ("SEGUNDA. COBERTURA", escape(_scholarship_contract_scope(item))),
        ("TERCERA. VIGENCIA", "La beca rige exclusivamente durante el período de adjudicación indicado. No se renovará automáticamente y cualquier período posterior requerirá una nueva validación y aprobación."),
        ("CUARTA. RENDIMIENTO ACADÉMICO", "La persona beneficiaria mantendrá el rendimiento, asistencia y participación establecidos por la normativa institucional y cumplirá oportunamente todas las evaluaciones y actividades académicas."),
        ("QUINTA. OBLIGACIONES", "La persona beneficiaria mantendrá actualizados sus datos, observará las normas de convivencia, utilizará responsablemente los recursos institucionales y comunicará cualquier novedad que afecte el beneficio."),
        ("SEXTA. SEGUIMIENTO", "Bienestar Estudiantil, el área Académica y el área Financiera podrán verificar durante el período el cumplimiento de las condiciones de la beca y dejar constancia de sus resultados."),
        ("SÉPTIMA. SUSPENSIÓN", "El beneficio podrá suspenderse por incumplimiento académico, retiro, inactividad, falsedad documental o vulneración de la normativa institucional, previa verificación del caso."),
        ("OCTAVA. TERMINACIÓN", "El contrato termina al finalizar el período adjudicado, por renuncia de la persona beneficiaria o por resolución institucional debidamente motivada."),
        ("NOVENA. INFORMACIÓN", "La información utilizada proviene de los registros académicos y financieros vigentes. La persona beneficiaria autoriza su tratamiento para la administración, seguimiento y auditoría de la beca."),
        ("DÉCIMA. NOTIFICACIONES", "Las comunicaciones se efectuarán mediante el correo institucional o los datos de contacto registrados en el sistema académico."),
        ("DÉCIMA PRIMERA. SOLUCIÓN DE CONTROVERSIAS", "Las partes procurarán resolver cualquier diferencia mediante los procedimientos internos de INTEC y la normativa ecuatoriana aplicable."),
        ("DÉCIMA SEGUNDA. ACEPTACIÓN", "Las partes declaran conocer y aceptar íntegramente este contrato, que se incorpora al expediente estudiantil como requisito complementario del período académico."),
    ]
    for heading, text in clauses:
        story.append(Paragraph(f"<b>{heading}.</b> {text}", body_style))
    story.append(Spacer(1, 0.28 * cm))

    signature_line = "________________________________"
    signatures = Table(
        [
            [signature_line, signature_line],
            ["ING. JAIME RODER ORTEGA PEREIRA", _clean(item.get("estudiante")) or "PERSONA BENEFICIARIA"],
            ["RECTOR", "PERSONA BENEFICIARIA"],
            ["Instituto Superior Tecnológico INTEC", f"C.I. {_clean(item.get('cedula')) or '-'}"],
        ],
        colWidths=[8.4 * cm, 8.4 * cm],
    )
    signatures.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 1), (-1, 2), "Helvetica-Bold"),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111111")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    story.extend(
        [
            signatures,
            Spacer(1, 0.5 * cm),
            Paragraph(
                f"Documento generado desde información institucional vigente. Código de verificación: {escape(contract_number)}.",
                small_style,
            ),
        ]
    )
    document.build(story, onFirstPage=draw_contract_background, onLaterPages=draw_contract_background)
    return output.getvalue()


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
    limit: int = Query(default=1000, ge=1, le=2000),
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
                    COALESCE(NULLIF(LTRIM(RTRIM(lb.tipo_beca)), ''), tb.Nombre) AS TipoBeca,
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
                    active_student.Tipo_Capacidad AS TipoDiscapacidad,
                    eb.Codigo AS Estado
                FROM bec.BecaEstudiante b
                INNER JOIN core.Estudiante e ON e.EstudianteId = b.EstudianteId
                INNER JOIN fin.CuentaEstudiante c ON c.CuentaEstudianteId = b.CuentaEstudianteId
                    AND c.Activo = 1
                INNER JOIN INTECBDD.dbo.DATOS_ESTUD active_student
                    ON TRY_CONVERT(nvarchar(50), active_student.codigo_estud) = TRY_CONVERT(nvarchar(50), e.CodigoEstud)
                   AND UPPER(LTRIM(RTRIM(ISNULL(active_student.Estado, '')))) = 'A'
                INNER JOIN cat.TipoBeca tb ON tb.TipoBecaId = b.TipoBecaId
                INNER JOIN cat.EstadoBeca eb ON eb.EstadoBecaId = b.EstadoBecaId
                LEFT JOIN core.Carrera ca ON ca.CodigoCarrera = c.CodigoCarrera
                LEFT JOIN core.Periodo pe ON pe.CodigoPeriodo = c.CodigoPeriodo
                OUTER APPLY
                (
                    SELECT TOP (1) legacy.tipo_beca
                    FROM INTECBDD.dbo.Becas legacy
                    WHERE TRY_CONVERT(nvarchar(50), legacy.codestud) = TRY_CONVERT(nvarchar(50), e.CodigoEstud)
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
                      WHERE TRY_CONVERT(nvarchar(50), active_enrollment.codigo_estud) = TRY_CONVERT(nvarchar(50), e.CodigoEstud)
                  )
                  AND (
                    ? = '' OR e.NumeroIdentificacion LIKE ? OR e.NombreCompleto LIKE ?
                    OR ISNULL(ca.NombreCarrera, c.CodigoCarrera) LIKE ?
                    OR COALESCE(NULLIF(LTRIM(RTRIM(lb.tipo_beca)), ''), tb.Nombre) LIKE ?
                    OR c.CodigoPeriodo LIKE ? OR ISNULL(b.UsuarioAprobacion, '') LIKE ?
                  )
                ORDER BY COALESCE(b.FechaAprobacion, b.FechaSolicitud) DESC,
                         e.NombreCompleto ASC, b.BecaId DESC
                """,
                limit,
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
                """
                SELECT TOP (?)
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
                    ? = '' OR d.Cedula_Est LIKE ? OR d.Apellidos_nombre LIKE ?
                    OR ISNULL(c.Nombre_Basica, '') LIKE ? OR ISNULL(b.tipo_beca, '') LIKE ?
                    OR ISNULL(p.Detalle_Periodo, '') LIKE ?
                  )
                ORDER BY d.Apellidos_nombre, b.id
                """,
                limit,
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
                    "tipo_discapacidad": _clean(row.TipoDiscapacidad),
                    "estado": "REGISTRADA",
                }
            )
        items.sort(key=lambda item: (item["estudiante"].upper(), item["codigo_estud"]))
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
    limit: int = 2000,
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


@router.get("/becas/contratos/candidatos")
def list_scholarship_contract_candidates(
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
    query: str = Query(default="", max_length=120),
    tipo_beca: str = Query(default="", max_length=150),
    codigo_periodo: str = Query(default="", max_length=50),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        all_items = _scholarship_contract_candidates(current_user, query, "", "", limit)
        scholarship_types = sorted(
            {_clean(item.get("tipo_beca")) for item in all_items if _clean(item.get("tipo_beca"))},
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


@router.post("/becas/contratos/generar")
def generate_scholarship_contracts(
    payload: ScholarshipContractGeneratePayload,
    current_user: Annotated[SessionUser, Depends(_SCHOLARSHIP_APPROVAL_ACCESS)],
) -> StreamingResponse:
    scholarship_ids = list(dict.fromkeys(int(value) for value in payload.beca_ids))
    academic_period = _clean(payload.codigo_periodo)
    if not scholarship_ids:
        raise HTTPException(status_code=400, detail="Seleccione al menos un estudiante becado")
    if not academic_period:
        raise HTTPException(status_code=400, detail="Seleccione el período académico de la beca")
    if len(scholarship_ids) > 100:
        raise HTTPException(status_code=400, detail="Puede generar hasta 100 contratos por operación")

    try:
        candidates = _scholarship_contract_candidates(current_user, "", "", academic_period, 2000)
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

        contract_date = date.today()
        generated_files: list[tuple[str, bytes]] = []
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
                    pdf_bytes = _build_scholarship_contract_pdf(item, contract_number, contract_date)
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
                            NombreArchivo, RutaArchivo, HashSha256, EstadoCodigo, UsuarioGeneracion
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GENERADO', ?)
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
                        filename,
                        str(relative_path),
                        sha256(pdf_bytes).hexdigest(),
                        current_user.login,
                    )
                    generated_files.append((filename, pdf_bytes))
                conn.commit()
            except Exception:
                conn.rollback()
                for path in written_paths:
                    if path.exists() and path.is_relative_to(_PREINSCRIPTION_UPLOAD_ROOT):
                        path.unlink()
                raise

        if len(generated_files) == 1:
            filename, content = generated_files[0]
            return StreamingResponse(
                BytesIO(content),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Generated-Contracts": "1",
                },
            )

        bundle = BytesIO()
        with ZipFile(bundle, mode="w", compression=ZIP_DEFLATED) as archive:
            for filename, content in generated_files:
                archive.writestr(filename, content)
        bundle.seek(0)
        archive_name = f"contratos_beca_{contract_date.isoformat()}.zip"
        return StreamingResponse(
            bundle,
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
                    NumeroContrato, FechaContrato, NombreArchivo, HashSha256,
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
    filename = _safe_filename(_clean(file.filename) or "contrato-beca-firmado.pdf")
    content_type = _clean(file.content_type).lower() or "application/pdf"
    try:
        content = await file.read(_SCHOLARSHIP_CONTRACT_MAX_BYTES + 1)
    finally:
        await file.close()
    if not filename.lower().endswith(".pdf") or content_type not in {
        "application/pdf",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=400, detail="El contrato firmado debe ser un archivo PDF")
    if not content or len(content) > _SCHOLARSHIP_CONTRACT_MAX_BYTES:
        raise HTTPException(status_code=400, detail="El contrato firmado debe pesar entre 1 byte y 20 MB")
    if not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="El archivo seleccionado no contiene un PDF válido")

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
            extension_name = _safe_filename(file.filename or f"{field}.bin")
            target_dir = _PREINSCRIPTION_UPLOAD_ROOT / _safe_filename(str(code))
            target_dir.mkdir(parents=True, exist_ok=True)
            target_name = f"{field}-{extension_name}"
            target_path = target_dir / target_name
            content = await file.read()
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

    original_name = _safe_filename(file.filename or "foto-carnet")
    mime_type = _photo_mime_type(original_name, file.content_type)
    if not mime_type:
        raise HTTPException(status_code=400, detail="La foto debe ser una imagen JPG, PNG o WEBP")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail='La imagen esta vacía')
    if len(content) > _PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail='La imagen supera el límite de 8 MB')

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
