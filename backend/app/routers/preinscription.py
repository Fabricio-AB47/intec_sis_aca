import calendar
from datetime import date, datetime
from html import escape
from pathlib import Path
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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
from app.services.db import get_connection

router = APIRouter(prefix="/api/students/preinscripcion", tags=["preinscripcion"])

_PREINSCRIPTION_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "ADMISIONES", "RECTOR")
_DOCUMENT_FILTERS = {"ALL", "PENDIENTES", "COMPLETOS", "CON_CABECERA", "SIN_CABECERA"}
_DOCUMENT_FIELDS = {"urlcedula", "urltitulo", "urldeposito", "urlconvenio"}
_PHOTO_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_PHOTO_MAX_BYTES = 8 * 1024 * 1024
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


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


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


def _payment_plan(payload: PreinscriptionCabeceraPayload) -> dict[str, float | int | str]:
    semester_count = _convenio_semester_count(payload.semestres_convenio)
    base_semester_cost = max(float(payload.costo_semestre or 0), 0)
    if base_semester_cost <= 0:
        base_semester_cost = max(float(payload.valor or 0), 0)
    total = round(base_semester_cost * semester_count, 2) if base_semester_cost > 0 else max(float(payload.valor or 0), 0)
    porcentaje_beca = min(max(float(payload.porcentaje_beca or 0), 0), 100)
    beca_valor = round(total * porcentaje_beca / 100, 2)
    descuento = max(float(payload.descuento or 0), 0)
    saldo = max(total - beca_valor - descuento, 0)
    num_cuotas = max(int(payload.num_cuotas or 1), 1)
    cuota_valor = round(saldo / num_cuotas, 2) if num_cuotas else saldo
    return {
        "total": round(total, 2),
        "costo_semestre": round(base_semester_cost, 2),
        "semestres": semester_count,
        "alcance": "Todos los semestres" if _clean(payload.semestres_convenio).upper() in {"TODOS", "TODO", "ALL"} else f"{semester_count} semestre(s)",
        "porcentaje_beca": round(porcentaje_beca, 2),
        "beca_valor": beca_valor,
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
                f"<b>Periodo:</b> {periodo or '-'}<br/>"
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
        raise ValueError("Campo de secuencia invalido")
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
            detail="Primero genera la prematricula para crear el estudiante antes de subir la foto de carnet",
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
            "mensaje": "No existe una foto de carnet cargada para aprobacion.",
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
        raise HTTPException(status_code=404, detail="No se encontro la preinscripcion seleccionada")
    return row


def _resolve_preinscription_student_code(row: Any) -> int:
    code = _int_value(getattr(row, "datos_codigo_estud", None)) or _int_value(getattr(row, "Codestu", None))
    if not code:
        raise HTTPException(
            status_code=400,
            detail="La preinscripcion no tiene codigo de estudiante valido para crear cabecera",
        )
    return code


def _resolve_preinscription_required_code(row: Any, field_name: str, label: str) -> int:
    code = _int_value(getattr(row, field_name, None))
    if not code:
        raise HTTPException(status_code=400, detail=f"La preinscripcion no tiene {label} valido")
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
                        TRY_CONVERT(decimal(18, 2), MAX(ISNULL(porcentaje_beca, 0))) AS amount
                    FROM dbo.Becas
                    WHERE NULLIF(LTRIM(RTRIM(tipo_beca)), '') IS NOT NULL
                    GROUP BY TRY_CONVERT(nvarchar(255), NULLIF(LTRIM(RTRIM(tipo_beca)), ''))
                    ORDER BY TRY_CONVERT(nvarchar(255), NULLIF(LTRIM(RTRIM(tipo_beca)), ''))
                END
                ELSE
                BEGIN
                    SELECT TOP (0)
                        TRY_CONVERT(nvarchar(255), '') AS option_value,
                        TRY_CONVERT(decimal(18, 2), 0) AS amount
                END
                """
            )
            becas = [
                {
                    "value": _clean(row.option_value),
                    "label": _clean(row.option_value),
                    "detail": f"{_number_value(row.amount) or 0:g}%",
                    "amount": _number_value(row.amount),
                }
                for row in cursor.fetchall()
                if _clean(row.option_value)
            ]
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
        raise HTTPException(status_code=500, detail=f"Error consultando catalogo de preinscripcion: {exc}") from exc


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
        raise HTTPException(status_code=400, detail="Filtro de documentos invalido")

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
        raise HTTPException(status_code=400, detail="La cedula debe tener 10 digitos")

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
        raise HTTPException(status_code=500, detail=f"Error validando cedula: {exc}") from exc


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
        raise HTTPException(status_code=400, detail="Ingresa el nombre del estudiante")
    if len(cedula) != 10:
        raise HTTPException(status_code=400, detail="La cedula debe tener 10 digitos")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            codprov = _int_value(payload.codprov)
            if codprov is None:
                raise HTTPException(status_code=400, detail="Selecciona una provincia valida")
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.Provincias WHERE TRY_CONVERT(int, Cod_Provincia) = ? AND ISNULL(activo, 1) = 1",
                codprov,
            )
            if int(cursor.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=400, detail="La provincia seleccionada no existe")

            codperiodo = _int_value(payload.codperiodo) or _default_preinscription_period(cursor)
            codcarrera = _int_value(payload.codcarrera) or _default_preinscription_career(cursor)
            if not codperiodo:
                raise HTTPException(status_code=400, detail="No se pudo resolver el periodo de preinscripcion")
            if not codcarrera:
                raise HTTPException(status_code=400, detail="No se pudo resolver la carrera de preinscripcion")

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
            conn.commit()
            row = _fetch_preinscription_row(cursor, str(num))
        return {
            "ok": True,
            "message": "Preinscripcion registrada correctamente.",
            "item": _preinscription_item(row),
            "asesor": {"codigo": str(codasesor), "usuario": usuario},
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error registrando preinscripcion: {exc}") from exc


@router.post("/{num}/cabecera")
def register_preinscription_cabecera(
    num: str,
    payload: PreinscriptionCabeceraPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
            plan = _payment_plan(payload)
            payload.valor = float(plan["total"])
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
        response = _cabecera_response_from_row(refreshed)
        response["message"] = (
            "Cabecera de matricula registrada correctamente. Convenio generado."
            if convenio_url
            else "Cabecera de matricula registrada correctamente."
        )
        response["action"] = action
        response["num_matricula"] = str(num_matricula)
        response["codigo_documentacion"] = codigo_documentacion
        response["convenio_url"] = convenio_url
        return response
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error registrando cabecera de matricula: {exc}") from exc


@router.put("/{num}/seguimiento")
def update_preinscription_followup(
    num: str,
    payload: PreinscriptionFollowupPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
            "message": "Seguimiento de preinscripcion actualizado.",
            "item": _preinscription_item(refreshed),
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error actualizando seguimiento de preinscripcion: {exc}") from exc


@router.put("/{num}/documentos")
def update_preinscription_documents(
    num: str,
    payload: PreinscriptionDocumentsPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            current_row = _fetch_preinscription_row(cursor, clean_num)
            current_item = _preinscription_item(current_row)
            if not current_item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail="Primero registra la cabecera de matricula para obtener el codigo de documentacion",
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
                raise HTTPException(status_code=404, detail="No se encontro la preinscripcion seleccionada")
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
            raise HTTPException(status_code=404, detail="No se encontro la preinscripcion actualizada")
        item = _preinscription_item(row)
        return {
            "ok": True,
            "message": "Documentos de preinscripcion actualizados.",
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
        raise HTTPException(status_code=500, detail=f"Error actualizando documentos de preinscripcion: {exc}") from exc


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
        raise HTTPException(status_code=400, detail="Campo de documento invalido")
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            item = _preinscription_item(row)
            if not item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail="Primero registra la cabecera de matricula para obtener el codigo de documentacion",
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
        raise HTTPException(status_code=500, detail=f"Error subiendo documento de preinscripcion: {exc}") from exc


@router.get("/{num}/foto-carnet")
def get_preinscription_carnet_photo_status(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
        raise HTTPException(status_code=500, detail=f"Error consultando foto de carnet: {exc}") from exc


@router.post("/{num}/foto-carnet/upload")
async def upload_preinscription_carnet_photo(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

    original_name = _safe_filename(file.filename or "foto-carnet")
    mime_type = _photo_mime_type(original_name, file.content_type)
    if not mime_type:
        raise HTTPException(status_code=400, detail="La foto debe ser una imagen JPG, PNG o WEBP")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="La imagen esta vacia")
    if len(content) > _PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="La imagen supera el limite de 8 MB")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            row = _fetch_preinscription_row(cursor, clean_num)
            item = _preinscription_item(row)
            if not item["en_cabecera_matricula"]:
                raise HTTPException(
                    status_code=400,
                    detail="Primero registra la cabecera de matricula para crear el estudiante antes de subir la foto",
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
                    "Foto reemplazada para revision previa",
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
                    "Foto de carnet pendiente",
                    "Imagen cargada desde preinscripcion para aprobacion previa",
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
                    "Foto cargada para revision previa",
                    _clean(current_user.login)[:100],
                )

            status = _photo_status_payload(cursor, code)
            conn.commit()
        return {
            "ok": True,
            "message": "Foto cargada. Queda pendiente de aprobacion antes de usarla en carnet.",
            "foto": status,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error subiendo foto de carnet: {exc}") from exc


@router.post("/{num}/foto-carnet/{request_id}/aprobar")
def approve_preinscription_carnet_photo(
    num: str,
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
                raise HTTPException(status_code=404, detail="No se encontro la solicitud de foto seleccionada")
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
                "Foto aprobada para carnet",
                _clean(current_user.login)[:100],
                request_id,
            )
            status = _photo_status_payload(cursor, codigo_estud)
            conn.commit()
        return {"ok": True, "message": "Foto aprobada para carnet.", "foto": status}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error aprobando foto de carnet: {exc}") from exc


@router.post("/{num}/foto-carnet/{request_id}/rechazar")
def reject_preinscription_carnet_photo(
    num: str,
    request_id: int,
    payload: PreinscriptionPhotoReviewPayload,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
                raise HTTPException(status_code=404, detail="No se encontro la solicitud de foto seleccionada")
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
        raise HTTPException(status_code=500, detail=f"Error rechazando foto de carnet: {exc}") from exc


@router.delete("/{num}/revertir")
def revert_preinscription_process(
    num: str,
    current_user: Annotated[SessionUser, Depends(_PREINSCRIPTION_ACCESS)],
) -> dict[str, Any]:
    del current_user
    clean_num = num.strip()
    if not clean_num:
        raise HTTPException(status_code=400, detail="Debes indicar el identificador num de la preinscripcion")

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
                raise HTTPException(status_code=404, detail="No se encontro la preinscripcion seleccionada")

            conn.commit()
        return {
            "ok": True,
            "message": "Proceso de inscripcion revertido correctamente.",
            "deleted": deleted,
        }
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error revirtiendo preinscripcion: {exc}") from exc
