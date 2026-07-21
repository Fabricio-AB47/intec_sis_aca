from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unicodedata
from typing import Annotated, Any, Literal
from zipfile import ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from openpyxl import Workbook
from PIL import Image as PILImage
from pydantic import BaseModel, Field
import pyodbc
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography import x509 as crypto_x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12 as crypto_pkcs12
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, SigSeedSubFilter
from pyhanko.stamp import QRStampStyle
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Image as PdfImage, Indenter, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/portal", tags=["portal-academico"])
logger = logging.getLogger(__name__)

_STUDENT_ACCESS = require_roles("ESTUDIANTE")
_TEACHER_ACCESS = require_roles("DOCENTE")
_PORTAL_ADMIN_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_REPORT_TEMPLATE_PATH = _PROJECT_ROOT / "frontend" / "doc" / "Plantilla word (1) - copia (1).docx"
_TEACHER_COMPLIANCE_WORD_TEMPLATE_PATH = Path.home() / "Documents" / "FABRICIO BORJA" / "FABRICIO BORJA CUMPLIMIENTO GRSI.docx"
_TEACHER_COMPLIANCE_BACKGROUND_PATH = _BACKEND_ROOT.parent / "backend" / ".codex_template_image1.png"
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"
_ACADEMIC_PLANNING_PEA_BACKGROUND_PATH = _BACKEND_ROOT / "app" / "assets" / "academic_planning_pea_background.png"
_ACADEMIC_PLANNING_SYLLABUS_BACKGROUND_PATH = _BACKEND_ROOT / "app" / "assets" / "academic_planning_silabo_background.png"
_PORTAL_CONFIG_ROOT = _BACKEND_ROOT / "data"
_TEACHER_COMPLIANCE_FORMAT_PATH = _PORTAL_CONFIG_ROOT / "teacher_compliance_format.json"


class TeacherGradePayload(BaseModel):
    codigo_estud: int
    cod_anio_basica: int
    codigo_periodo: int
    codigo_materia: int
    paralelo: str = Field(min_length=1, max_length=10)
    num_matricula: int | None = None
    num_grupo: int | None = None
    teoria_homo: float | None = Field(default=None, ge=0, le=10)
    practica_homo: float | None = Field(default=None, ge=0, le=10)
    p1_tareas: float | None = Field(default=None, ge=0, le=10)
    p1_proyectos: float | None = Field(default=None, ge=0, le=10)
    p1_examen: float | None = Field(default=None, ge=0, le=10)
    prom_p1: float | None = Field(default=None, ge=0, le=10)
    p2_tareas: float | None = Field(default=None, ge=0, le=10)
    p2_proyectos: float | None = Field(default=None, ge=0, le=10)
    p2_examen: float | None = Field(default=None, ge=0, le=10)
    prom_p2: float | None = Field(default=None, ge=0, le=10)
    p3_tareas: float | None = Field(default=None, ge=0, le=10)
    p3_proyectos: float | None = Field(default=None, ge=0, le=10)
    p3_examen: float | None = Field(default=None, ge=0, le=10)
    prom_p3: float | None = Field(default=None, ge=0, le=10)
    promedio: float | None = Field(default=None, ge=0, le=10)
    asistencia: float | None = Field(default=None, ge=0, le=100)
    recuperacion: float | None = Field(default=None, ge=0, le=10)
    promedio_final: float | None = Field(default=None, ge=0, le=10)
    caprueba: str | None = Field(default=None, max_length=10)


class AcademicPlanningTopicPayload(BaseModel):
    tema: str = Field(min_length=1, max_length=500)
    semana: int = Field(ge=1, le=52)
    horas_docencia: int = Field(default=0, ge=0, le=100)
    horas_practica: int = Field(default=0, ge=0, le=100)
    horas_autonomo: int = Field(default=0, ge=0, le=100)
    actividad_docencia: str = Field(default="", max_length=1000)
    actividad_practica: str = Field(default="", max_length=1000)
    actividad_autonoma: str = Field(default="", max_length=1000)
    evaluacion: str = Field(default="", max_length=500)


class AcademicPlanningUnitPayload(BaseModel):
    nombre: str = Field(min_length=1, max_length=300)
    resultado_aprendizaje: str = Field(default="", max_length=1500)
    temas: list[AcademicPlanningTopicPayload] = Field(default_factory=list, max_length=30)


class AcademicPlanningPayload(BaseModel):
    document_type: Literal["pea", "silabo"]
    codigo_periodos: list[int] = Field(min_length=1, max_length=4)
    codigo_materia: str = Field(min_length=1, max_length=100)
    paralelo: str = Field(min_length=1, max_length=10)
    cod_anio_basica: int | None = None
    cod_jornada: int | None = None
    nivel: str = Field(default="", max_length=100)
    unidad_curricular: str = Field(default="", max_length=150)
    campo_formacion: str = Field(default="", max_length=150)
    modalidad: str = Field(default="Presencial / En línea", max_length=150)
    prerrequisitos: str = Field(default="", max_length=500)
    correquisitos: str = Field(default="", max_length=500)
    horario_clases: str = Field(default="", max_length=500)
    horario_tutorias: str = Field(default="", max_length=500)
    descripcion: str = Field(default="", max_length=5000)
    objetivo_general: str = Field(default="", max_length=3000)
    resultados_aprendizaje: str = Field(default="", max_length=5000)
    mision_intec: str = Field(default="", max_length=3000)
    mision_escuela: str = Field(default="", max_length=3000)
    mision_carrera: str = Field(default="", max_length=3000)
    unidades: list[AcademicPlanningUnitPayload] = Field(min_length=1, max_length=12)
    estrategias_metodologicas: str = Field(default="", max_length=5000)
    formacion_ciudadana: str = Field(default="", max_length=3000)
    sostenibilidad: str = Field(default="", max_length=3000)
    recursos_didacticos: str = Field(default="", max_length=5000)
    evaluacion_tareas: int = Field(default=30, ge=0, le=100)
    evaluacion_individual: int = Field(default=15, ge=0, le=100)
    evaluacion_colaborativo: int = Field(default=15, ge=0, le=100)
    evaluacion_acumulativa: int = Field(default=40, ge=0, le=100)
    bibliografia_basica: str = Field(default="", max_length=5000)
    bibliografia_complementaria: str = Field(default="", max_length=5000)
    proyecto_tema: str = Field(default="", max_length=1000)
    proyecto_tiempo: str = Field(default="Un semestre", max_length=300)
    proyecto_objetivo: str = Field(default="", max_length=2000)
    proyecto_contexto: str = Field(default="", max_length=5000)
    version: str = Field(default="001", max_length=20)
    fecha_elaboracion: date = Field(default_factory=date.today)


class TeacherComplianceReportFormat(BaseModel):
    title: str = Field(default="REPORTE ACADÉMICO", max_length=180)
    pea_heading: str = Field(default="Cumplimiento del PEA y sílabo", max_length=180)
    pea_instruction: str = Field(
        default="Evidenciar el sílabo y PEA cargado en el sistema de aulas virtuales, debidamente firmado electrónicamente.",
        max_length=1000,
    )
    syllabus_update_heading: str = Field(default="Reporte de actualización del sílabo", max_length=180)
    syllabus_update_default: str = Field(default="Sin cambios realizados.", max_length=1000)
    virtual_classroom_heading: str = Field(default="Reporte del aula virtual", max_length=180)
    virtual_classroom_intro: str = Field(
        default="En el reporte consolidado se evidencia en el sistema de aulas virtuales que se cargaron los siguientes recursos en material académico:",
        max_length=1200,
    )
    resources: list[str] = Field(
        default_factory=lambda: [
            "Bibliografía del material académico",
            "Presentación PPT cargada como PDF por cada clase",
            "Link de grabaciones de cada clase o tutoría impartida",
            "Simulador de examen y banco de preguntas, para los casos que aplique",
            "Evaluación(es) teórica(s)",
            "Componente(s) práctico(s)",
        ]
    )
    teams_heading: str = Field(default="Evidencia de clases grabadas en TEAMS", max_length=180)
    attendance_heading: str = Field(default="Asistencias", max_length=180)
    grades_heading: str = Field(default="Reporte de notas", max_length=180)
    grades_instruction: str = Field(
        default="Se incluye resumen de nota máxima, nota mínima y casos reprobados según el reporte de notas registrado en el sistema académico.",
        max_length=1000,
    )
    annexes_heading: str = Field(default="Anexos", max_length=180)
    annexes_intro: str = Field(default="El presente informe debe ir acompañado de la siguiente documentación de respaldo:", max_length=1000)
    annexes: list[str] = Field(
        default_factory=lambda: [
            "Contrato firmado electrónicamente",
            "Reporte de notas firmado electrónicamente",
            "Factura electrónica emitida de acuerdo al número de contrato y valor",
        ]
    )
    closing: str = Field(default="Saludos cordiales,", max_length=300)
    signature_label: str = Field(default="Firma electrónica", max_length=120)
    signature_role: str = Field(default="DOCENTE", max_length=120)


_GRADE_COLUMN_MAP = {
    "teoria_homo": "teoriaHomo",
    "practica_homo": "practicahomo",
    "p1_tareas": "P1Tareas",
    "p1_proyectos": "P1Proyectos",
    "p1_examen": "P1Examen",
    "prom_p1": "promP1",
    "p2_tareas": "P2Tareas",
    "p2_proyectos": "P2Proyectos",
    "p2_examen": "P2Examen",
    "prom_p2": "promP2",
    "p3_tareas": "P3Tareas",
    "p3_proyectos": "P3Proyectos",
    "p3_examen": "P3Examen",
    "prom_p3": "promP3",
    "promedio": "Promedio",
    "asistencia": "Asistencia",
    "recuperacion": "Recuperacion",
    "promedio_final": "PromedioFinal",
    "caprueba": "caprueba",
}


def _default_teacher_compliance_format() -> dict[str, Any]:
    return TeacherComplianceReportFormat().model_dump()


def _sanitize_text_list(values: list[str]) -> list[str]:
    return [_clean(item) for item in values if _clean(item)]


def _read_teacher_compliance_format() -> dict[str, Any]:
    defaults = _default_teacher_compliance_format()
    if not _TEACHER_COMPLIANCE_FORMAT_PATH.exists():
        return defaults
    try:
        payload = json.loads(_TEACHER_COMPLIANCE_FORMAT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults
    merged = {**defaults, **payload}
    merged["resources"] = _sanitize_text_list(merged.get("resources") or defaults["resources"]) or defaults["resources"]
    merged["annexes"] = _sanitize_text_list(merged.get("annexes") or defaults["annexes"]) or defaults["annexes"]
    return TeacherComplianceReportFormat(**merged).model_dump()


def _write_teacher_compliance_format(payload: TeacherComplianceReportFormat) -> dict[str, Any]:
    data = payload.model_dump()
    data["resources"] = _sanitize_text_list(data.get("resources") or [])
    data["annexes"] = _sanitize_text_list(data.get("annexes") or [])
    _PORTAL_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    _TEACHER_COMPLIANCE_FORMAT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def _image_evidence_flowables(
    images: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    max_width: float = 16.8 * cm,
    max_height: float = 10.5 * cm,
    show_labels: bool = False,
) -> list[Any]:
    flowables: list[Any] = []
    for item in images:
        content = item.get("content")
        if not content:
            continue
        try:
            image = PILImage.open(BytesIO(content))
            image.verify()
            image = PILImage.open(BytesIO(content))
        except Exception:
            continue
        width, height = image.size
        if width <= 0 or height <= 0:
            continue
        ratio = min(max_width / width, max_height / height, 1)
        label = _clean(item.get("label")) or "Captura de pantalla"
        buffer = BytesIO(content)
        flowables.append(Spacer(1, 0.08 * cm))
        if show_labels:
            flowables.append(Paragraph(f"<b>{_pdf_text(label)}</b>", styles["ComplianceSmall"]))
        flowable = PdfImage(buffer, width=width * ratio, height=height * ratio)
        flowable._evidence_buffer = buffer  # type: ignore[attr-defined]
        flowables.append(flowable)
        flowables.append(Spacer(1, 0.12 * cm))
    return flowables


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\xa0", " ").strip()


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _clean(value)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _weighted_regular_partial(tareas: Any, proyectos: Any, examen: Any) -> float | None:
    tareas_value = _number(tareas)
    proyectos_value = _number(proyectos)
    examen_value = _number(examen)
    if tareas_value is None or proyectos_value is None or examen_value is None:
        return None
    return round((tareas_value * 0.30) + (proyectos_value * 0.40) + (examen_value * 0.30), 2)


def _weighted_homologation_final(teoria: Any, practica: Any) -> float | None:
    teoria_value = _number(teoria)
    practica_value = _number(practica)
    if teoria_value is None or practica_value is None:
        return None
    return round((teoria_value * 0.40) + (practica_value * 0.60), 2)


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _is_homologation_type(*values: Any) -> bool:
    text = " ".join(_clean(value).upper() for value in values)
    return "HOMO" in text or text in {"H", "HOMOLOGACION", "HOMOLOGADO"}


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
            self.height = 1.0 * cm

    def draw(self) -> None:
        if not self.drawing:
            self.canv.setFont("Helvetica-Bold", 22)
            self.canv.setFillColor(colors.HexColor("#808285"))
            self.canv.drawString(0, 0.25 * cm, "intec")
            return
        self.canv.saveState()
        self.canv.scale(self.scale, self.scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()


def _template_logo(width: float) -> Flowable:
    if _REPORT_TEMPLATE_PATH.exists():
        try:
            with ZipFile(_REPORT_TEMPLATE_PATH) as archive:
                with archive.open("word/media/image1.png") as source:
                    image = PILImage.open(source).convert("RGBA")
                    full_width, full_height = image.size
                    logo = image.crop(
                        (
                            int(full_width * 0.04),
                            int(full_height * 0.035),
                            int(full_width * 0.45),
                            int(full_height * 0.16),
                        )
                    )
                    buffer = BytesIO()
                    logo.save(buffer, format="PNG")
                    buffer.seek(0)
                    height = width * (logo.height / max(logo.width, 1))
                    flowable = PdfImage(buffer, width=width, height=height)
                    flowable._template_buffer = buffer  # type: ignore[attr-defined]
                    return flowable
        except Exception:
            pass
    return _SvgLogo(_LOGO_PATH, width)


def _template_page_image() -> bytes:
    with ZipFile(_REPORT_TEMPLATE_PATH) as archive:
        media_names = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
        if not media_names:
            raise HTTPException(status_code=500, detail="La plantilla Word no contiene imagen base")
        return archive.read(media_names[0])


def _safe_filename(value: Any) -> str:
    text = _clean(value).lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "reporte"


def _grade_status(final: Any, fallback: Any = "") -> str:
    value = _number(final)
    if value is not None:
        return "Aprobada" if value >= 7 else "Reprobada"
    fallback_text = _clean(fallback)
    return fallback_text or "Pendiente"


def _grade_text(value: Any, decimals: int = 2) -> str:
    number = _number(value)
    if number is None:
        return "-"
    return f"{number:.{decimals}f}"


def _pdf_text(value: Any) -> str:
    text = _clean(value)
    return escape(text) if text else "-"


def _pdf_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_pdf_text(value), style)


def _report_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=14,
            leading=17,
            textColor=colors.HexColor("#0c1f42"),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#4d5a78"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["BodyText"],
            fontSize=8.2,
            leading=10,
            textColor=colors.HexColor("#0c1f42"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Cell",
            parent=styles["BodyText"],
            fontSize=6.4,
            leading=7.6,
            textColor=colors.HexColor("#0c1f42"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CellBold",
            parent=styles["Cell"],
            fontName="Helvetica-Bold",
        )
    )
    return styles


def _student_meta_table(profile: dict[str, Any], career: str, styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            Paragraph(f"<b>Estudiante:</b> {_pdf_text(profile.get('nombre_estudiante'))}", styles["Meta"]),
            Paragraph(f"<b>Cedula:</b> {_pdf_text(profile.get('cedula'))}", styles["Meta"]),
            Paragraph(f"<b>Codigo:</b> {_pdf_text(profile.get('codigo_estud'))}", styles["Meta"]),
        ],
        [
            Paragraph(f"<b>Correo INTEC:</b> {_pdf_text(profile.get('correo_intec'))}", styles["Meta"]),
            Paragraph(f"<b>Carrera:</b> {_pdf_text(career)}", styles["Meta"]),
            Paragraph(f"<b>Fecha:</b> {date.today().strftime('%d/%m/%Y')}", styles["Meta"]),
        ],
    ]
    table = Table(data, colWidths=[6.5 * cm, 5.8 * cm, 5.8 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5fafc")),
                ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#b7c8cf")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5e0e5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _subject_code_text(item: dict[str, Any]) -> str:
    code = _clean(item.get("cod_materia"))
    internal = _clean(item.get("codigo_materia"))
    if code and internal and code != internal:
        return f"{escape(code)}<br/><font size=\"6.5\">{escape(internal)}</font>"
    return escape(code or internal or "-")


def _build_student_report_pdf(
    title: str,
    subtitle: str,
    profile: dict[str, Any],
    career: str,
    headers: list[str],
    rows: list[list[Any]],
    col_widths: list[float],
) -> bytes:
    if not _REPORT_TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="No se encontro la plantilla Word para generar el PDF")

    styles = _report_styles()
    template_reader = ImageReader(BytesIO(_template_page_image()))
    story: list[Any] = [
        Paragraph(title, styles["ReportTitle"]),
        Paragraph(subtitle, styles["ReportSubtitle"]),
        _student_meta_table(profile, career, styles),
        Spacer(1, 0.3 * cm),
    ]

    table_data: list[list[Any]] = [[Paragraph(f"<b>{escape(header)}</b>", styles["CellBold"]) for header in headers]]
    table_data.extend(rows)
    if len(table_data) == 1:
        table_data.append([Paragraph("No hay informacion para mostrar.", styles["Cell"]) for _ in headers])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f3f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0c1f42")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cad5dc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbfc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)

    def draw_template(canvas: Any, _doc: Any) -> None:
        page_width, page_height = A4
        canvas.saveState()
        canvas.drawImage(template_reader, 0, 0, width=page_width, height=page_height, mask="auto")
        if hasattr(canvas, "setFillAlpha"):
            canvas.setFillAlpha(0.96)
        canvas.setFillColor(colors.white)
        canvas.roundRect(0.65 * cm, 1.1 * cm, page_width - 1.3 * cm, page_height - 4.9 * cm, 8, stroke=0, fill=1)
        canvas.restoreState()

    output = BytesIO()
    SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=0.75 * cm,
        leftMargin=0.75 * cm,
        topMargin=3.8 * cm,
        bottomMargin=1.3 * cm,
        title=title,
    ).build(story, onFirstPage=draw_template, onLaterPages=draw_template)
    output.seek(0)
    return output.getvalue()


def _academic_pdf_rows(items: list[dict[str, Any]]) -> list[list[Any]]:
    styles = _report_styles()
    cell = styles["Cell"]
    rows: list[list[Any]] = []
    for item in items:
        is_homo = _is_homologation_type(
            item.get("tipo_matricula"),
            item.get("ultimo_periodo"),
            item.get("esquema_calificacion"),
        )
        final = _number(item.get("promedio_final"))
        status = _grade_status(final, item.get("estado_academico"))
        rows.append(
            [
                _pdf_paragraph(item.get("semestre"), cell),
                Paragraph(_subject_code_text(item), cell),
                _pdf_paragraph(item.get("nombre_materia"), cell),
                _pdf_paragraph(_grade_text(item.get("creditos")), cell),
                _pdf_paragraph(item.get("esquema_calificacion") or ("HOMOLOGACION" if is_homo else "REGULAR"), cell),
                _pdf_paragraph(
                    f"T: {_grade_text(item.get('teoria_homo'))} / P: {_grade_text(item.get('practica_homo'))}"
                    if is_homo
                    else "-",
                    cell,
                ),
                _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p1")), cell),
                _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p2")), cell),
                _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p3")), cell),
                _pdf_paragraph(_grade_text(final) if final is not None else "0", cell),
                _pdf_paragraph(status, cell),
            ]
        )
    return rows


def _calificaciones_pdf_rows(items: list[dict[str, Any]], homologation_only: bool = False) -> list[list[Any]]:
    styles = _report_styles()
    cell = styles["Cell"]
    rows: list[list[Any]] = []
    for item in items:
        is_homo = _is_homologation_type(
            item.get("tipo_matricula"),
            item.get("detalle_periodo"),
            item.get("esquema_calificacion"),
        )
        final = _number(item.get("promedio_final"))
        base_row = [
            _pdf_paragraph(item.get("semestre"), cell),
            _pdf_paragraph(item.get("detalle_periodo") or item.get("codigo_periodo"), cell),
            Paragraph(_subject_code_text(item), cell),
            _pdf_paragraph(item.get("nombre_materia"), cell),
            _pdf_paragraph(item.get("esquema_calificacion") or ("HOMOLOGACION" if is_homo else "REGULAR"), cell),
        ]
        if not homologation_only:
            base_row.extend(
                [
                    _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p1")), cell),
                    _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p2")), cell),
                    _pdf_paragraph("-" if is_homo else _grade_text(item.get("prom_p3")), cell),
                ]
            )
        base_row.extend(
            [
                _pdf_paragraph(_grade_text(final), cell),
                _pdf_paragraph(_grade_status(final, item.get("estado_academico")), cell),
            ]
        )
        rows.append(base_row)
    return rows


def _practice_search_text(value: Any) -> str:
    text = _clean(value).upper()
    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _practice_requirement_code(item: dict[str, Any]) -> str:
    text = _practice_search_text(
        " ".join(
            [
                _clean(item.get("nombre_materia")),
                _clean(item.get("cod_materia")),
                _clean(item.get("codigo_materia")),
            ]
        )
    )
    if "VINCULACION" in text or "SERVICIO COMUNITARIO" in text:
        return "VIN"
    if "PRACTICA" in text:
        return "PPF"
    return ""


def _academic_grid_with_practice_requirements(items: list[dict[str, Any]], career: str = "") -> list[dict[str, Any]]:
    result = [dict(item) for item in items]
    existing_codes = {_practice_requirement_code(item) for item in result}
    defaults = [
        {
            "code": "PPF",
            "cod_materia": "PPF-240",
            "codigo_materia": "PPF-240",
            "nombre_materia": "PRÁCTICAS PREPROFESIONALES - 240 HORAS",
            "horas": 240,
        },
        {
            "code": "VIN",
            "cod_materia": "VIN-060",
            "codigo_materia": "VIN-060",
            "nombre_materia": "VINCULACIÓN - 60 HORAS",
            "horas": 60,
        },
    ]
    for default in defaults:
        if default["code"] in existing_codes:
            continue
        result.append(
            {
                "semestre": 3,
                "orden": 99980 if default["code"] == "VIN" else 99970,
                "cod_materia": default["cod_materia"],
                "codigo_materia": default["codigo_materia"],
                "nombre_materia": default["nombre_materia"],
                "nombre_carrera": career,
                "creditos": None,
                "horas": default["horas"],
                "esquema_calificacion": "REQUISITO",
                "estado_academico": "Pendiente",
                "promedio_final": None,
                "nota_aprobar": 7,
                "ultimo_periodo": "Requisito institucional",
                "codigo_periodo": "PRACTICAS",
                "detalle_periodo": "Requisito institucional",
            }
        )
    return result


def _student_profile_from_row(row: Any) -> dict[str, Any]:
    return {
        "codigo_estud": _clean(getattr(row, "codigo_estud", "")),
        "cedula": _clean(getattr(row, "cedula", "")),
        "nombre_estudiante": _clean(getattr(row, "nombre_estudiante", "")),
        "correo_personal": _clean(getattr(row, "correo_personal", "")),
        "correo_intec": _clean(getattr(row, "correo_intec", "")),
        "estado_codigo": _clean(getattr(row, "estado_codigo", "")),
    }


def _fetch_student_profile(cursor: pyodbc.Cursor, codigo_estud: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TOP (1)
            TRY_CONVERT(varchar(50), de.codigo_estud) AS codigo_estud,
            TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS cedula,
            TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS nombre_estudiante,
            TRY_CONVERT(nvarchar(255), de.correo) AS correo_personal,
            COALESCE(
                NULLIF(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N''),
                TRY_CONVERT(nvarchar(255), de.correointec)
            ) AS correo_intec,
            TRY_CONVERT(nvarchar(50), de.Estado) AS estado_codigo
        FROM dbo.DATOS_ESTUD de
        LEFT JOIN dbo.CorreosEstudIntec ce
          ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, de.codigo_estud)
        WHERE TRY_CONVERT(int, de.codigo_estud) = ?
        """,
        codigo_estud,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontro el estudiante vinculado a la sesion")
    return _student_profile_from_row(row)


def _record_item(row: Any) -> dict[str, Any]:
    es_homologacion = _is_homologation_type(
        getattr(row, "tipo_matricula", ""),
        getattr(row, "detalle_periodo", ""),
    )
    nota_final = (
        _number(getattr(row, "promedio_final_raw", None))
        if es_homologacion
        else _number(getattr(row, "nota_final", None))
    )
    nota_aprobar = 7.0
    if nota_final is None:
        estado = "En curso"
        aprobada = False
    elif nota_final >= nota_aprobar:
        estado = "Aprobada"
        aprobada = True
    else:
        estado = "Reprobada"
        aprobada = False

    return {
        "codigo_estud": _clean(row.codigo_estud),
        "cod_anio_basica": _clean(row.cod_anio_basica),
        "nombre_carrera": _clean(row.nombre_carrera),
        "codigo_periodo": _clean(row.codigo_periodo),
        "detalle_periodo": _clean(row.detalle_periodo),
        "anio_periodo": _int(getattr(row, "anio_periodo", None)),
        "codigo_materia": _clean(row.codigo_materia),
        "cod_materia": _clean(row.cod_materia),
        "nombre_materia": _clean(row.nombre_materia),
        "semestre": _int(row.semestre),
        "creditos": _number(row.creditos),
        "horas": _number(getattr(row, "horas", None)),
        "orden": _int(getattr(row, "orden", None)),
        "num_malla": _int(getattr(row, "num_malla", None)),
        "paralelo": _clean(row.paralelo),
        "num_grupo": _int(row.num_grupo),
        "num_matricula": _clean(row.num_matricula),
        "fecha_matricula": _date_text(row.fecha_matricula),
        "tipo_matricula": _clean(row.tipo_matricula),
        "es_homologacion": es_homologacion,
        "esquema_calificacion": "HOMOLOGACION" if es_homologacion else "REGULAR",
        "teoria_homo": _number(getattr(row, "teoria_homo", None)),
        "practica_homo": _number(getattr(row, "practica_homo", None)),
        "p1_tareas": _number(row.p1_tareas),
        "p1_proyectos": _number(row.p1_proyectos),
        "p1_examen": _number(row.p1_examen),
        "prom_p1": _number(row.prom_p1),
        "p2_tareas": _number(row.p2_tareas),
        "p2_proyectos": _number(row.p2_proyectos),
        "p2_examen": _number(row.p2_examen),
        "prom_p2": _number(row.prom_p2),
        "p3_tareas": _number(row.p3_tareas),
        "p3_proyectos": _number(row.p3_proyectos),
        "p3_examen": _number(row.p3_examen),
        "prom_p3": _number(row.prom_p3),
        "promedio": _number(row.promedio),
        "asistencia": _number(row.asistencia),
        "recuperacion": _number(row.recuperacion),
        "promedio_final": nota_final,
        "nota_aprobar": nota_aprobar,
        "aprobada": aprobada,
        "estado_academico": estado,
        "observaciones": _clean(getattr(row, "observaciones", "")),
        "seguimiento": _clean(getattr(row, "seguimiento", "")),
    }


def _fetch_student_record(cursor: pyodbc.Cursor, codigo_estud: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        """
        SELECT TOP (3000)
            TRY_CONVERT(varchar(50), de.codigo_estud) AS codigo_estud,
            TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS cedula,
            TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS nombre_estudiante,
            TRY_CONVERT(nvarchar(255), de.correo) AS correo_personal,
            COALESCE(
                NULLIF(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N''),
                TRY_CONVERT(nvarchar(255), de.correointec)
            ) AS correo_intec,
            TRY_CONVERT(nvarchar(50), de.Estado) AS estado_codigo,
            TRY_CONVERT(varchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
            TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
            TRY_CONVERT(varchar(50), cxe.codigo_periodo) AS codigo_periodo,
            TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS detalle_periodo,
            TRY_CONVERT(int, pe.anio) AS anio_periodo,
            TRY_CONVERT(varchar(50), cxe.codigo_materia) AS codigo_materia,
            TRY_CONVERT(varchar(100), p.cod_materia) AS cod_materia,
            TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
            TRY_CONVERT(int, p.Semestre) AS semestre,
            TRY_CONVERT(int, p.NumMalla) AS num_malla,
            TRY_CONVERT(float, p.Horas) AS horas,
            TRY_CONVERT(int, p.Orden) AS orden,
            TRY_CONVERT(float, COALESCE(NULLIF(cxe.Num_Creditos, 0), p.Creditos)) AS creditos,
            TRY_CONVERT(nvarchar(50), cxe.paralelo) AS paralelo,
            TRY_CONVERT(int, cxe.NumGrupo) AS num_grupo,
            TRY_CONVERT(varchar(50), cxe.Num_Matricula) AS num_matricula,
            cxe.Fecha_Matricula AS fecha_matricula,
            TRY_CONVERT(nvarchar(20), cxe.TipoMatricula) AS tipo_matricula,
            TRY_CONVERT(float, cxe.teoriaHomo) AS teoria_homo,
            TRY_CONVERT(float, cxe.practicahomo) AS practica_homo,
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
            TRY_CONVERT(float, cxe.Promedio) AS promedio,
            TRY_CONVERT(float, cxe.Asistencia) AS asistencia,
            TRY_CONVERT(float, cxe.Recuperacion) AS recuperacion,
            TRY_CONVERT(float, cxe.PromedioFinal) AS promedio_final_raw,
            COALESCE(
                TRY_CONVERT(float, cxe.PromedioFinal),
                CASE
                    WHEN (
                            UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.TipoMatricula), N'')))) = N'H'
                         OR UPPER(COALESCE(TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                         )
                     AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                     AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                    THEN (TRY_CONVERT(float, cxe.teoriaHomo) * 0.4) + (TRY_CONVERT(float, cxe.practicahomo) * 0.6)
                END,
                CASE
                    WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                     AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                     AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                    THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                END,
                TRY_CONVERT(float, cxe.Promedio),
                TRY_CONVERT(float, cxe.PromedioAux)
            ) AS nota_final,
            COALESCE(TRY_CONVERT(float, pe.NotaAprobar), 7) AS nota_aprobar,
            CASE
                WHEN UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.caprueba), N'')))) LIKE N'A%' THEN 1
                WHEN COALESCE(
                        TRY_CONVERT(float, cxe.PromedioFinal),
                        CASE
                            WHEN (
                                    UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.TipoMatricula), N'')))) = N'H'
                                 OR UPPER(COALESCE(TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                                 )
                             AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                            THEN (TRY_CONVERT(float, cxe.teoriaHomo) * 0.4) + (TRY_CONVERT(float, cxe.practicahomo) * 0.6)
                        END,
                        CASE
                            WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                            THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                        END,
                        TRY_CONVERT(float, cxe.Promedio),
                        TRY_CONVERT(float, cxe.PromedioAux)
                     ) >= COALESCE(TRY_CONVERT(float, pe.NotaAprobar), 7)
                THEN 1
                ELSE 0
            END AS aprobada,
            TRY_CONVERT(nvarchar(max), cxe.observaciones) AS observaciones,
            TRY_CONVERT(nvarchar(255), cxe.seguimiento) AS seguimiento
        FROM dbo.CARRERAXESTUD cxe
        INNER JOIN dbo.DATOS_ESTUD de
          ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, cxe.codigo_estud)
        LEFT JOIN dbo.CorreosEstudIntec ce
          ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, de.codigo_estud)
        LEFT JOIN dbo.CARRERAS c
          ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
        LEFT JOIN dbo.PERIODO pe
          ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
        LEFT JOIN dbo.PENSUM p
          ON TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
         AND TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
        ORDER BY
            COALESCE(TRY_CONVERT(int, pe.Orden), TRY_CONVERT(int, pe.cod_periodo)) DESC,
            TRY_CONVERT(int, pe.cod_periodo) DESC,
            TRY_CONVERT(nvarchar(4000), c.Nombre_Basica),
            TRY_CONVERT(int, p.Semestre),
            TRY_CONVERT(int, p.Orden),
            TRY_CONVERT(nvarchar(4000), p.Nomb_Materia)
        """,
        codigo_estud,
    )
    rows = cursor.fetchall()
    profile = _student_profile_from_row(rows[0]) if rows else _fetch_student_profile(cursor, codigo_estud)
    return profile, [_record_item(row) for row in rows]


def _record_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    aprobadas = sum(1 for item in items if item["aprobada"])
    reprobadas = sum(1 for item in items if item["estado_academico"] == "Reprobada")
    en_curso = sum(1 for item in items if item["estado_academico"] == "En curso")
    notas = [item["promedio_final"] for item in items if item["promedio_final"] is not None]
    creditos_aprobados = sum(float(item["creditos"] or 0) for item in items if item["aprobada"])
    return {
        "total_materias": total,
        "aprobadas": aprobadas,
        "reprobadas": reprobadas,
        "en_curso": en_curso,
        "creditos_aprobados": round(creditos_aprobados, 2),
        "promedio_general": round(sum(notas) / len(notas), 2) if notas else None,
        "cumplimiento_academico": round((aprobadas / total) * 100, 2) if total else 0,
    }


def _record_sort_value(item: dict[str, Any]) -> tuple[int, int, float, int]:
    final = _number(item.get("promedio_final"))
    try:
        period = int(str(item.get("codigo_periodo") or "0").strip())
    except ValueError:
        period = 0
    return (
        1 if item.get("aprobada") else 0,
        1 if final is not None else 0,
        final if final is not None else -1,
        period,
    )


def _curriculum_item(row: Any) -> dict[str, Any]:
    return {
        "cod_anio_basica": _clean(row.cod_anio_basica),
        "nombre_carrera": _clean(row.nombre_carrera),
        "codigo_materia": _clean(row.codigo_materia),
        "cod_materia": _clean(row.cod_materia),
        "nombre_materia": _clean(row.nombre_materia),
        "semestre": _int(row.semestre),
        "creditos": _number(row.creditos),
        "horas": _number(row.horas),
        "orden": _int(row.orden),
        "num_malla": _int(row.num_malla),
        "unidad_organiza": _clean(getattr(row, "unidad_organiza", "")),
        "estado_materia": _clean(getattr(row, "estado_materia", "")),
    }


def _curriculum_from_record_items(record_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_subject: dict[str, dict[str, Any]] = {}
    for item in record_items:
        subject_code = _clean(item.get("codigo_materia"))
        if not subject_code or subject_code in by_subject:
            continue
        by_subject[subject_code] = {
            "cod_anio_basica": _clean(item.get("cod_anio_basica")),
            "nombre_carrera": _clean(item.get("nombre_carrera")),
            "codigo_materia": subject_code,
            "cod_materia": _clean(item.get("cod_materia")),
            "nombre_materia": _clean(item.get("nombre_materia")),
            "semestre": _int(item.get("semestre")),
            "creditos": _number(item.get("creditos")),
            "horas": _number(item.get("horas")),
            "orden": _int(item.get("orden")),
            "num_malla": _int(item.get("num_malla")),
            "unidad_organiza": "",
            "estado_materia": "Desde record academico",
        }
    return sorted(
        by_subject.values(),
        key=lambda item: (
            _int(item.get("semestre")) or 999,
            _clean(item.get("nombre_materia")),
        ),
    )


def _student_career_from_record(items: list[dict[str, Any]]) -> int | None:
    for item in items:
        value = _int(item.get("cod_anio_basica"))
        if value is not None:
            return value
    return None


def _fetch_student_current_career(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    items: list[dict[str, Any]],
) -> int | None:
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, cm.cod_anio_Basica) AS cod_anio_basica
        FROM dbo.CABECERA_MATRICULA cm
        LEFT JOIN dbo.PERIODO pe
          ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cm.codigo_periodo)
        WHERE TRY_CONVERT(int, cm.codigo_estud) = ?
          AND TRY_CONVERT(int, cm.cod_anio_Basica) IS NOT NULL
        ORDER BY
            COALESCE(TRY_CONVERT(int, pe.Orden), TRY_CONVERT(int, cm.codigo_periodo)) DESC,
            TRY_CONVERT(int, cm.codigo_periodo) DESC,
            TRY_CONVERT(int, cm.cod_anio_Basica)
        """,
        codigo_estud,
    )
    row = cursor.fetchone()
    career_from_header = _int(row.cod_anio_basica) if row else None
    if career_from_header is not None:
        return career_from_header

    career_from_record = _student_career_from_record(items)
    if career_from_record is not None:
        return career_from_record
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, cxe.cod_anio_Basica) AS cod_anio_basica
        FROM dbo.CARRERAXESTUD cxe
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
        ORDER BY
            TRY_CONVERT(int, cxe.codigo_periodo) DESC,
            TRY_CONVERT(int, cxe.cod_anio_Basica)
        """,
        codigo_estud,
    )
    row = cursor.fetchone()
    return _int(row.cod_anio_basica) if row else None


def _fetch_student_payments(cursor: pyodbc.Cursor, codigo_estud: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT TOP (12)
            cm.codigo_periodo,
            pe.Detalle_Periodo,
            cm.cod_anio_Basica,
            c.Nombre_Basica,
            cm.Num_Matricula,
            cm.numcodigo,
            cm.fecha_pago,
            cm.valor,
            cm.InscripValor,
            cm.MatriValor,
            cm.Cuota1,
            cm.Beca,
            cm.Descuento,
            COALESCE(cm.urlconvenio, pre.urlconvenio) AS urlconvenio,
            rp.Num AS pago_num,
            rp.Detalle AS pago_detalle,
            rp.fechapago AS pago_fecha,
            rp.ValorRegistrado AS pago_valor,
            rp.NoDeposito AS pago_referencia,
            rp.Banco AS pago_banco
        FROM dbo.CABECERA_MATRICULA cm
        LEFT JOIN dbo.PERIODO pe ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cm.codigo_periodo)
        LEFT JOIN dbo.CARRERAS c ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cm.cod_anio_Basica)
        OUTER APPLY (
            SELECT TOP (1) pay.*
            FROM dbo.REGISTROPAGOS pay
            WHERE TRY_CONVERT(int, pay.Codestu) = TRY_CONVERT(int, cm.codigo_estud)
              AND TRY_CONVERT(int, pay.codperiodo) = TRY_CONVERT(int, cm.codigo_periodo)
              AND TRY_CONVERT(int, pay.cod_anio_Basica) = TRY_CONVERT(int, cm.cod_anio_Basica)
            ORDER BY TRY_CONVERT(int, pay.Num) DESC, pay.fechapago DESC
        ) rp
        OUTER APPLY (
            SELECT TOP (1) p.urlconvenio
            FROM dbo.PREINSCRIPCION p
            WHERE TRY_CONVERT(int, p.Codestu) = TRY_CONVERT(int, cm.codigo_estud)
               OR LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), p.Cedula))) IN (
                    SELECT TOP (1) LTRIM(RTRIM(TRY_CONVERT(nvarchar(20), d.Cedula_Est)))
                    FROM dbo.DATOS_ESTUD d
                    WHERE TRY_CONVERT(int, d.codigo_estud) = TRY_CONVERT(int, cm.codigo_estud)
                )
            ORDER BY TRY_CONVERT(int, p.num) DESC
        ) pre
        WHERE TRY_CONVERT(int, cm.codigo_estud) = ?
        ORDER BY
            TRY_CONVERT(int, cm.codigo_periodo) DESC,
            TRY_CONVERT(int, cm.Num_Matricula) DESC,
            cm.fecha_pago DESC
        """,
        codigo_estud,
    )
    payments: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        total = _number(getattr(row, "valor", None)) or 0
        beca = _number(getattr(row, "Beca", None)) or 0
        descuento = _number(getattr(row, "Descuento", None)) or 0
        saldo = max(round(total - beca - descuento, 2), 0)
        cuota = _number(getattr(row, "Cuota1", None)) or 0
        cuotas = int(round(saldo / cuota)) if saldo > 0 and cuota > 0 else 1
        payments.append(
            {
                "codigo_periodo": _clean(getattr(row, "codigo_periodo", "")),
                "periodo": _clean(getattr(row, "Detalle_Periodo", "")),
                "cod_anio_basica": _clean(getattr(row, "cod_anio_Basica", "")),
                "carrera": _clean(getattr(row, "Nombre_Basica", "")),
                "num_matricula": _clean(getattr(row, "Num_Matricula", "")),
                "codigo_documentacion": _clean(getattr(row, "numcodigo", "")),
                "fecha_pago": _date_text(getattr(row, "fecha_pago", "")),
                "total": total,
                "inscripcion": _number(getattr(row, "InscripValor", None)) or 0,
                "matricula": _number(getattr(row, "MatriValor", None)) or 0,
                "beca": beca,
                "descuento": descuento,
                "saldo": saldo,
                "cuota": cuota,
                "cuotas": cuotas,
                "convenio_url": _clean(getattr(row, "urlconvenio", "")),
                "pago_num": _int(getattr(row, "pago_num", None)),
                "pago_detalle": _clean(getattr(row, "pago_detalle", "")),
                "pago_fecha": _date_text(getattr(row, "pago_fecha", "")),
                "pago_valor": _number(getattr(row, "pago_valor", None)) or 0,
                "pago_referencia": _clean(getattr(row, "pago_referencia", "")),
                "pago_banco": _clean(getattr(row, "pago_banco", "")),
            }
        )
    return payments


def _fetch_student_current_pensum(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    career_code: int,
    items: list[dict[str, Any]],
) -> int | None:
    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, mp.Malla) AS num_malla
        FROM dbo.MALLA_PENSUM mp
        WHERE TRY_CONVERT(int, mp.Cod_Carrera) = ?
          AND UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(20), mp.Estado), N'')))) = N'A'
          AND TRY_CONVERT(int, mp.Malla) IS NOT NULL
        ORDER BY
            TRY_CONVERT(int, mp.Malla) DESC,
            TRY_CONVERT(int, mp.Num) DESC
        """,
        career_code,
    )
    row = cursor.fetchone()
    active_malla = _int(row.num_malla) if row else None
    if active_malla is not None:
        return active_malla

    counts: dict[int, int] = {}
    for item in items:
        item_career = _int(item.get("cod_anio_basica"))
        if item_career is not None and item_career != career_code:
            continue
        num_malla = _int(item.get("num_malla"))
        if num_malla is None:
            continue
        counts[num_malla] = counts.get(num_malla, 0) + 1
    if counts:
        return max(counts, key=lambda key: (counts[key], key))

    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, p.NumMalla) AS num_malla
        FROM dbo.CARRERAXESTUD cxe
        INNER JOIN dbo.PENSUM p
          ON TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
         AND TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
        WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
          AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
          AND TRY_CONVERT(int, p.NumMalla) IS NOT NULL
        GROUP BY TRY_CONVERT(int, p.NumMalla)
        ORDER BY
            COUNT(*) DESC,
            MAX(TRY_CONVERT(int, cxe.codigo_periodo)) DESC,
            TRY_CONVERT(int, p.NumMalla) DESC
        """,
        codigo_estud,
        career_code,
    )
    row = cursor.fetchone()
    current_malla = _int(row.num_malla) if row else None
    if current_malla is not None:
        return current_malla

    cursor.execute(
        """
        SELECT TOP (1) TRY_CONVERT(int, p.NumMalla) AS num_malla
        FROM dbo.PENSUM p
        WHERE TRY_CONVERT(int, p.Cod_AnioBasica) = ?
          AND TRY_CONVERT(int, p.NumMalla) IS NOT NULL
        GROUP BY TRY_CONVERT(int, p.NumMalla)
        ORDER BY
            TRY_CONVERT(int, p.NumMalla) DESC,
            COUNT(*) DESC
        """,
        career_code,
    )
    row = cursor.fetchone()
    return _int(row.num_malla) if row else None


def _academic_grid_items(
    curriculum: list[dict[str, Any]],
    record_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records_by_subject: dict[str, list[dict[str, Any]]] = {}
    for item in record_items:
        subject_code = _clean(item.get("codigo_materia"))
        if subject_code:
            records_by_subject.setdefault(subject_code, []).append(item)

    grid: list[dict[str, Any]] = []
    for subject in curriculum:
        subject_code = _clean(subject.get("codigo_materia"))
        attempts = records_by_subject.get(subject_code, [])
        best_attempt = max(attempts, key=_record_sort_value) if attempts else None
        best_final = _number(best_attempt.get("promedio_final")) if best_attempt else None
        has_attempt = bool(best_attempt)

        if best_final is not None:
            academic_status = "Aprobada" if best_final >= 7 else "Reprobada"
        elif has_attempt:
            academic_status = "En curso"
        else:
            academic_status = "Pendiente"

        if best_final is not None:
            approved = best_final >= 7
        elif best_attempt and best_attempt.get("aprobada"):
            approved = True
        else:
            approved = False

        if approved:
            academic_status = "Aprobada"

        grid.append(
            {
                **subject,
                "estado_academico": academic_status,
                "aprobada": approved,
                "faltante": not approved,
                "intentos": len(attempts),
                "ultimo_periodo": best_attempt.get("detalle_periodo") if best_attempt else "",
                "codigo_periodo": best_attempt.get("codigo_periodo") if best_attempt else "",
                "paralelo": best_attempt.get("paralelo") if best_attempt else "",
                "tipo_matricula": best_attempt.get("tipo_matricula") if best_attempt else "",
                "esquema_calificacion": best_attempt.get("esquema_calificacion") if best_attempt else "",
                "teoria_homo": best_attempt.get("teoria_homo") if best_attempt else None,
                "practica_homo": best_attempt.get("practica_homo") if best_attempt else None,
                "p1_tareas": best_attempt.get("p1_tareas") if best_attempt else None,
                "p1_proyectos": best_attempt.get("p1_proyectos") if best_attempt else None,
                "p1_examen": best_attempt.get("p1_examen") if best_attempt else None,
                "prom_p1": best_attempt.get("prom_p1") if best_attempt else None,
                "p2_tareas": best_attempt.get("p2_tareas") if best_attempt else None,
                "p2_proyectos": best_attempt.get("p2_proyectos") if best_attempt else None,
                "p2_examen": best_attempt.get("p2_examen") if best_attempt else None,
                "prom_p2": best_attempt.get("prom_p2") if best_attempt else None,
                "p3_tareas": best_attempt.get("p3_tareas") if best_attempt else None,
                "p3_proyectos": best_attempt.get("p3_proyectos") if best_attempt else None,
                "p3_examen": best_attempt.get("p3_examen") if best_attempt else None,
                "prom_p3": best_attempt.get("prom_p3") if best_attempt else None,
                "promedio_final": best_final if best_final is not None else None,
                "nota_aprobar": best_attempt.get("nota_aprobar") if best_attempt else 7.0,
            }
        )
    return grid


def _curriculum_summary(grid: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(grid)
    aprobadas = 0
    en_curso = 0
    reprobadas = 0
    creditos_totales = sum(float(item.get("creditos") or 0) for item in grid)
    creditos_aprobados = 0.0
    for item in grid:
        final = _number(item.get("promedio_final"))
        if final is None:
            if item.get("estado_academico") == "En curso":
                en_curso += 1
            continue
        if final >= 7:
            aprobadas += 1
            creditos_aprobados += float(item.get("creditos") or 0)
        else:
            reprobadas += 1
    return {
        "total_materias": total,
        "aprobadas": aprobadas,
        "faltantes": max(total - aprobadas, 0),
        "en_curso": en_curso,
        "reprobadas": reprobadas,
        "creditos_totales": round(creditos_totales, 2),
        "creditos_aprobados": round(creditos_aprobados, 2),
        "porcentaje_avance": round((aprobadas / total) * 100, 2) if total else 0,
    }


def _fetch_student_curriculum(
    cursor: pyodbc.Cursor,
    codigo_estud: int,
    record_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    career_code = _fetch_student_current_career(cursor, codigo_estud, record_items)
    if career_code is None:
        curriculum = _curriculum_from_record_items(record_items)
        academic_grid = _academic_grid_items(curriculum, record_items)
        return curriculum, academic_grid, _curriculum_summary(academic_grid)

    num_malla = _fetch_student_current_pensum(cursor, codigo_estud, career_code, record_items)
    curriculum_sql = """
        SELECT
            TRY_CONVERT(varchar(50), p.Cod_AnioBasica) AS cod_anio_basica,
            TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
            TRY_CONVERT(varchar(50), p.codigo_materia) AS codigo_materia,
            TRY_CONVERT(varchar(100), p.cod_materia) AS cod_materia,
            TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
            TRY_CONVERT(int, p.Semestre) AS semestre,
            TRY_CONVERT(float, p.Creditos) AS creditos,
            TRY_CONVERT(float, p.Horas) AS horas,
            TRY_CONVERT(int, p.Orden) AS orden,
            COALESCE(TRY_CONVERT(int, mp.Malla), TRY_CONVERT(int, p.NumMalla)) AS num_malla,
            TRY_CONVERT(nvarchar(255), p.Unidad_Organiza) AS unidad_organiza,
            TRY_CONVERT(nvarchar(100), p.estado_mat) AS estado_materia
        FROM dbo.PENSUM p
        LEFT JOIN dbo.CARRERAS c
          ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, p.Cod_AnioBasica)
        LEFT JOIN dbo.MALLA_PENSUM mp
          ON TRY_CONVERT(int, mp.Cod_Carrera) = TRY_CONVERT(int, p.Cod_AnioBasica)
         AND TRY_CONVERT(int, mp.Malla) = TRY_CONVERT(int, p.NumMalla)
        WHERE {where_clause}
        ORDER BY
            TRY_CONVERT(int, p.Semestre),
            TRY_CONVERT(int, p.Orden),
            TRY_CONVERT(int, p.codigo_materia)
        """

    def fetch_curriculum(where_clause: str, *params: Any) -> list[dict[str, Any]]:
        cursor.execute(curriculum_sql.format(where_clause=where_clause), *params)
        return [_curriculum_item(row) for row in cursor.fetchall()]

    if num_malla is not None:
        curriculum = fetch_curriculum(
            "TRY_CONVERT(int, p.Cod_AnioBasica) = ? "
            "AND COALESCE(TRY_CONVERT(int, mp.Malla), TRY_CONVERT(int, p.NumMalla)) = ?",
            career_code,
            num_malla,
        )
    else:
        curriculum = []

    if not curriculum:
        curriculum = fetch_curriculum("TRY_CONVERT(int, p.Cod_AnioBasica) = ?", career_code)

    if not curriculum:
        career_name = next((_clean(item.get("nombre_carrera")) for item in record_items if _clean(item.get("nombre_carrera"))), "")
        if career_name:
            if num_malla is not None:
                curriculum = fetch_curriculum(
                    "UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), c.Nombre_Basica)))) = UPPER(LTRIM(RTRIM(?))) "
                    "AND COALESCE(TRY_CONVERT(int, mp.Malla), TRY_CONVERT(int, p.NumMalla)) = ?",
                    career_name,
                    num_malla,
                )
            if not curriculum:
                curriculum = fetch_curriculum(
                    "UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), c.Nombre_Basica)))) = UPPER(LTRIM(RTRIM(?)))",
                    career_name,
                )
    if not curriculum:
        curriculum = _curriculum_from_record_items(record_items)
    academic_grid = _academic_grid_items(curriculum, record_items)
    return curriculum, academic_grid, _curriculum_summary(academic_grid)


@router.get("/student/me")
def student_profile(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> dict[str, Any]:
    if current_user.codigo_estud is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene estudiante vinculado")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            profile, items = _fetch_student_record(cursor, current_user.codigo_estud)
        return {"student": profile, "summary": _record_summary(items)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando perfil del estudiante: {exc}") from exc


@router.get("/student/record")
def student_record(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    approved_only: Annotated[bool, Query(description="Mostrar solo materias aprobadas")] = False,
) -> dict[str, Any]:
    if current_user.codigo_estud is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene estudiante vinculado")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            profile, items = _fetch_student_record(cursor, current_user.codigo_estud)
            curriculum, academic_grid, curriculum_resume = _fetch_student_curriculum(
                cursor,
                current_user.codigo_estud,
                items,
            )
            payments = _fetch_student_payments(cursor, current_user.codigo_estud)
        summary = _record_summary(items)
        visible_items = [item for item in items if item["aprobada"]] if approved_only else items
        return {
            "student": profile,
            "summary": summary,
            "curriculum_summary": curriculum_resume,
            "curriculum": curriculum,
            "academic_grid": academic_grid,
            "payments": payments,
            "items": visible_items,
            "total": len(visible_items),
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando record academico: {exc}") from exc


@router.get("/student/record/export")
def student_record_export(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    approved_only: Annotated[bool, Query(description="Parametro heredado; la exportacion incluye aprobadas y reprobadas")] = False,
    codigo_periodo: Annotated[str | None, Query(description="Periodo seleccionado para exportar calificaciones")] = None,
) -> StreamingResponse:
    _ = approved_only
    if current_user.codigo_estud is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene estudiante vinculado")
    selected_period = _clean(codigo_periodo)
    if not selected_period:
        raise HTTPException(status_code=400, detail="Seleccione un periodo para exportar calificaciones")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            profile, items = _fetch_student_record(cursor, current_user.codigo_estud)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error exportando record academico: {exc}") from exc

    period_items = []
    for item in items:
        if item["codigo_periodo"] == selected_period or item["detalle_periodo"] == selected_period:
            period_items.append(item)

    visible_items = list(period_items)
    visible_items.sort(
        key=lambda item: (
            _int(item.get("semestre")) or 999,
            _int(item.get("orden")) or 9999,
            _int(item.get("codigo_materia")) or 999999,
            _clean(item.get("nombre_materia")),
        )
    )
    selected_period_label = next(
        (item["detalle_periodo"] for item in period_items if item["detalle_periodo"]),
        selected_period,
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Calificaciones"
    sheet.append(["Estudiante", profile["nombre_estudiante"]])
    sheet.append(["Cedula", profile["cedula"]])
    sheet.append(["Codigo", profile["codigo_estud"]])
    sheet.append(["Correo INTEC", profile["correo_intec"]])
    sheet.append(["Periodo", selected_period_label])
    sheet.append(["Carrera", next((item["nombre_carrera"] for item in period_items if item["nombre_carrera"]), "")])
    sheet.append([])
    homologation_only = bool(visible_items) and all(
        _is_homologation_type(
            item.get("tipo_matricula"),
            item.get("detalle_periodo"),
            item.get("esquema_calificacion"),
        )
        for item in visible_items
    )
    if homologation_only:
        sheet.append(["#", "Periodo", "Nivel", "Materia", "Codigo materia", "Esquema", "Nota final", "Estado"])
    else:
        sheet.append([
            "#",
            "Periodo",
            "Nivel",
            "Materia",
            "Codigo materia",
            "Esquema",
            "Prom. 1",
            "Prom. 2",
            "Prom. 3",
            "Nota final",
            "Estado",
        ])
    for index, item in enumerate(visible_items, start=1):
        final = _number(item.get("promedio_final"))
        if final is None:
            estado = "En curso"
        elif final >= 7:
            estado = "Aprobada"
        else:
            estado = "Reprobada"
        is_homo = _is_homologation_type(item.get("tipo_matricula"), item.get("detalle_periodo"))
        row = [
            index,
            item["detalle_periodo"],
            item["semestre"],
            item["nombre_materia"],
            item["cod_materia"] or item["codigo_materia"],
            item["esquema_calificacion"],
        ]
        if not homologation_only:
            row.extend([None if is_homo else item["prom_p1"], None if is_homo else item["prom_p2"], None if is_homo else item["prom_p3"]])
        row.extend([final, estado])
        sheet.append(row)

    for worksheet in workbook.worksheets:
        for column in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            worksheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 42)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    period_suffix = selected_period.replace("/", "-").replace("\\", "-").replace(" ", "-")
    filename = f"calificaciones-{profile['codigo_estud']}-{period_suffix}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/student/record/export-pdf")
def student_record_pdf_export(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    tipo: Annotated[str, Query(description="academica o calificaciones")] = "calificaciones",
    codigo_periodo: Annotated[str | None, Query(description="Periodo seleccionado para calificaciones")] = None,
) -> StreamingResponse:
    if current_user.codigo_estud is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene estudiante vinculado")

    report_type = _clean(tipo).lower()
    if report_type not in {"academica", "calificaciones"}:
        raise HTTPException(status_code=400, detail="Tipo de reporte no valido")

    selected_period = _clean(codigo_periodo)
    if report_type == "calificaciones" and not selected_period:
        raise HTTPException(status_code=400, detail="Seleccione un periodo para exportar calificaciones")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            profile, items = _fetch_student_record(cursor, current_user.codigo_estud)
            curriculum, academic_grid, curriculum_resume = _fetch_student_curriculum(
                cursor,
                current_user.codigo_estud,
                items,
            )
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando PDF academico: {exc}") from exc

    career = (
        next((_clean(item.get("nombre_carrera")) for item in academic_grid if _clean(item.get("nombre_carrera"))), "")
        or next((_clean(item.get("nombre_carrera")) for item in curriculum if _clean(item.get("nombre_carrera"))), "")
        or next((_clean(item.get("nombre_carrera")) for item in items if _clean(item.get("nombre_carrera"))), "")
    )

    if report_type == "academica":
        academic_grid = _academic_grid_with_practice_requirements(academic_grid, career)
        academic_grid.sort(
            key=lambda item: (
                _int(item.get("semestre")) or 999,
                _int(item.get("orden")) or 9999,
                _int(item.get("codigo_materia")) or 999999,
                _clean(item.get("nombre_materia")),
            )
        )
        pdf_bytes = _build_student_report_pdf(
            "Malla academica",
            f"Malla y calificaciones consolidadas | Avance {curriculum_resume.get('porcentaje_avance', 0)}%",
            profile,
            career,
            ["Nivel", "Codigo materia", "Materia", "Creditos", "Esquema", "HOMO", "Prom. 1", "Prom. 2", "Prom. 3", "Final", "Estado"],
            _academic_pdf_rows(academic_grid),
            [0.8 * cm, 2.2 * cm, 5.4 * cm, 1.2 * cm, 1.6 * cm, 1.7 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.5 * cm],
        )
        filename = f"malla-academica-{_safe_filename(profile.get('codigo_estud'))}.pdf"
    else:
        period_items = [
            item
            for item in items
            if item["codigo_periodo"] == selected_period or item["detalle_periodo"] == selected_period
        ]
        period_items.sort(
            key=lambda item: (
                _int(item.get("semestre")) or 999,
                _int(item.get("orden")) or 9999,
                _int(item.get("codigo_materia")) or 999999,
                _clean(item.get("nombre_materia")),
            )
        )
        selected_period_label = next(
            (item["detalle_periodo"] for item in period_items if item["detalle_periodo"]),
            selected_period,
        )
        homologation_only = bool(period_items) and all(
            _is_homologation_type(
                item.get("tipo_matricula"),
                item.get("detalle_periodo"),
                item.get("esquema_calificacion"),
            )
            for item in period_items
        )
        headers = (
            ["Nivel", "Periodo", "Codigo", "Materia", "Esquema", "Final", "Estado"]
            if homologation_only
            else ["Nivel", "Periodo", "Codigo", "Materia", "Esquema", "Prom. 1", "Prom. 2", "Prom. 3", "Final", "Estado"]
        )
        col_widths = (
            [0.8 * cm, 3.2 * cm, 2.0 * cm, 6.4 * cm, 1.9 * cm, 1.3 * cm, 1.7 * cm]
            if homologation_only
            else [0.8 * cm, 3.0 * cm, 2.0 * cm, 5.4 * cm, 1.6 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.2 * cm, 1.4 * cm]
        )
        pdf_bytes = _build_student_report_pdf(
            "Calificaciones",
            f"Periodo: {selected_period_label}",
            profile,
            career,
            headers,
            _calificaciones_pdf_rows(period_items, homologation_only),
            col_widths,
        )
        filename = f"calificaciones-{_safe_filename(profile.get('codigo_estud'))}-{_safe_filename(selected_period_label)}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/student/record/export-secretaria-pdf")
def student_record_secretary_pdf_export(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    codigo_periodo: Annotated[str | None, Query(description="Periodo seleccionado para reporte de notas formato Secretaria")] = None,
    tipo: Annotated[str, Query(description="calificaciones o malla")] = "calificaciones",
) -> StreamingResponse:
    if current_user.codigo_estud is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene estudiante vinculado")

    selected_period = _clean(codigo_periodo)
    report_type = _clean(tipo).lower()
    if report_type not in {"calificaciones", "malla"}:
        raise HTTPException(status_code=400, detail="Tipo de reporte no valido")
    if report_type == "calificaciones" and not selected_period:
        raise HTTPException(status_code=400, detail="Seleccione un periodo para exportar el reporte de notas")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            profile, items = _fetch_student_record(cursor, current_user.codigo_estud)
            curriculum, academic_grid, _curriculum_resume = _fetch_student_curriculum(
                cursor,
                current_user.codigo_estud,
                items,
            )
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando reporte de notas formato Secretaria: {exc}") from exc

    if report_type == "malla":
        career = (
            next((_clean(item.get("nombre_carrera")) for item in academic_grid if _clean(item.get("nombre_carrera"))), "")
            or next((_clean(item.get("nombre_carrera")) for item in curriculum if _clean(item.get("nombre_carrera"))), "")
            or next((_clean(item.get("nombre_carrera")) for item in items if _clean(item.get("nombre_carrera"))), "")
        )
        report_items = list(academic_grid)
        report_items = _academic_grid_with_practice_requirements(report_items, career)
        selected_period_label = "Malla academica general"
        for item in report_items:
            item["detalle_periodo"] = item.get("ultimo_periodo") or selected_period_label
            item["codigo_periodo"] = item.get("codigo_periodo") or "MALLA"
            item["nombre_carrera"] = item.get("nombre_carrera") or career
    else:
        report_items = [
            item
            for item in items
            if item["codigo_periodo"] == selected_period or item["detalle_periodo"] == selected_period
        ]
        selected_period_label = next(
            (item["detalle_periodo"] for item in report_items if item["detalle_periodo"]),
            selected_period,
        )

    report_items.sort(
        key=lambda item: (
            _int(item.get("semestre")) or 999,
            _int(item.get("orden")) or 9999,
            _int(item.get("codigo_materia")) or 999999,
            _clean(item.get("nombre_materia")),
        )
    )
    for item in report_items:
        item["codigo_estud"] = item.get("codigo_estud") or profile.get("codigo_estud")
        item["cedula"] = item.get("cedula") or profile.get("cedula")
        item["nombre_estudiante"] = item.get("nombre_estudiante") or profile.get("nombre_estudiante")

    pdf_bytes = _student_secretaria_notes_pdf(profile, report_items, report_type, selected_period_label)
    filename_prefix = "malla-secretaria" if report_type == "malla" else "reporte-notas-secretaria"
    filename = f"{filename_prefix}-{_safe_filename(profile.get('codigo_estud'))}-{_safe_filename(selected_period_label)}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _teacher_code(current_user: SessionUser) -> int:
    if current_user.codigo_doc is None:
        raise HTTPException(status_code=403, detail="La sesion no tiene docente vinculado")
    return current_user.codigo_doc


def _course_item(row: Any) -> dict[str, Any]:
    codigo_periodo = _clean(row.codigo_periodo)
    detalle_periodo = _clean(row.detalle_periodo)
    tipo_periodo = _clean(getattr(row, "tipo_periodo", ""))
    es_homologacion = _is_homologation_type(tipo_periodo, detalle_periodo)
    internal_code = _clean(row.codigo_materia)
    common_code = _clean(getattr(row, "cod_materia", "")) or internal_code
    return {
        "codigo_doc": _clean(row.codigo_doc),
        "cod_anio_basica": _clean(row.cod_anio_basica),
        "cod_anio_basicas": [_clean(row.cod_anio_basica)] if _clean(row.cod_anio_basica) else [],
        "nombre_carrera": _clean(row.nombre_carrera),
        "codigo_materia": common_code,
        "codigo_materias": [internal_code] if internal_code else [],
        "cod_materia": common_code,
        "nombre_materia": _clean(row.nombre_materia),
        "codigo_periodo": codigo_periodo,
        "codigo_periodos": [codigo_periodo] if codigo_periodo else [],
        "detalle_periodo": detalle_periodo,
        "detalle_periodos": detalle_periodo,
        "tipo_periodo": tipo_periodo,
        "es_homologacion": es_homologacion,
        "paralelo": _clean(row.paralelo),
        "cod_jornada": _int(row.cod_jornada),
        "jornada": _clean(getattr(row, "jornada", "")) or (
            f"Jornada {_clean(row.cod_jornada)}" if _clean(row.cod_jornada) else ""
        ),
        "semestre": _int(getattr(row, "semestre", None)),
        "unidad_curricular": _clean(getattr(row, "unidad_curricular", "")),
        "periodo_orden": _int(getattr(row, "periodo_orden", None)) or _int(codigo_periodo) or 0,
        "period_count": 1,
        "total_estudiantes": _int(row.total_estudiantes) or 0,
        "estado_moodle_doc": bool(_int(row.estado_moodle_doc)),
    }


def _group_teacher_courses(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    period_groups: dict[tuple[str, str, str, str, bool], dict[str, Any]] = {}
    for item in items:
        common_code = _clean(item.get("cod_materia") or item.get("codigo_materia"))
        key = (
            common_code,
            _clean(item.get("codigo_periodo")),
            _clean(item.get("paralelo")).upper(),
            _clean(item.get("cod_jornada")),
            bool(item.get("es_homologacion")),
        )
        bucket = period_groups.get(key)
        if not bucket:
            bucket = item.copy()
            bucket["codigo_materia"] = common_code
            bucket["cod_materia"] = common_code
            bucket["cod_anio_basicas"] = []
            bucket["codigo_materias"] = []
            bucket["_nombre_carreras"] = []
            bucket["total_estudiantes"] = 0
            period_groups[key] = bucket
        career_code = _clean(item.get("cod_anio_basica"))
        if career_code and career_code not in bucket["cod_anio_basicas"]:
            bucket["cod_anio_basicas"].append(career_code)
        internal_code_values = item.get("codigo_materias") if isinstance(item.get("codigo_materias"), list) else [item.get("codigo_materia")]
        for internal_code in internal_code_values:
            internal_code = _clean(internal_code)
            if internal_code and internal_code not in bucket["codigo_materias"]:
                bucket["codigo_materias"].append(internal_code)
        career_name = _clean(item.get("nombre_carrera"))
        if career_name and career_name not in bucket["_nombre_carreras"]:
            bucket["_nombre_carreras"].append(career_name)
        bucket["total_estudiantes"] = max(
            _int(bucket.get("total_estudiantes")) or 0,
            _int(item.get("total_estudiantes")) or 0,
        )

    normalized_items: list[dict[str, Any]] = []
    for bucket in period_groups.values():
        career_names = bucket.pop("_nombre_carreras", [])
        bucket["cod_anio_basica"] = ", ".join(bucket["cod_anio_basicas"])
        bucket["nombre_carrera"] = " / ".join(career_names) if len(career_names) <= 2 else f"{len(career_names)} carreras"
        normalized_items.append(bucket)

    grouped: list[dict[str, Any]] = []
    regular_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for item in normalized_items:
        if item.get("es_homologacion"):
            grouped.append(item)
            continue
        key = (
            _clean(item.get("cod_materia") or item.get("codigo_materia")),
            _clean(item.get("nombre_materia")),
            _clean(item.get("paralelo")).upper(),
            _clean(item.get("cod_jornada")),
        )
        regular_groups.setdefault(key, []).append(item)

    for courses in regular_groups.values():
        sorted_courses = sorted(
            courses,
            key=lambda item: (_int(item.get("periodo_orden")) or 0, _int(item.get("codigo_periodo")) or 0),
            reverse=True,
        )
        for index in range(0, len(sorted_courses), 2):
            chunk = sorted_courses[index:index + 2]
            base = chunk[0].copy()
            period_codes = [_clean(item.get("codigo_periodo")) for item in chunk if _clean(item.get("codigo_periodo"))]
            period_names = [_clean(item.get("detalle_periodo")) or _clean(item.get("codigo_periodo")) for item in chunk]
            base["codigo_periodos"] = period_codes
            base["codigo_periodo"] = period_codes[0] if period_codes else ""
            base["detalle_periodos"] = " / ".join(period_names)
            base["detalle_periodo"] = base["detalle_periodos"]
            base["period_count"] = len(chunk)
            base["total_estudiantes"] = sum(_int(item.get("total_estudiantes")) or 0 for item in chunk)
            grouped.append(base)

    return sorted(
        grouped,
        key=lambda item: (
            _int(item.get("periodo_orden")) or 0,
            0 if item.get("es_homologacion") else 1,
            _clean(item.get("nombre_carrera")),
            _clean(item.get("nombre_materia")),
        ),
        reverse=True,
    )


@router.get("/teacher/me")
def teacher_profile(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
) -> dict[str, Any]:
    codigo_doc = _teacher_code(current_user)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(nvarchar(100), d.cedula_doc) AS cedula,
                    TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) AS docente,
                    TRY_CONVERT(nvarchar(255), d.correo) AS correo,
                    TRY_CONVERT(nvarchar(255), d.correop) AS correo_personal,
                    TRY_CONVERT(nvarchar(255), d.TipoDocente) AS tipo_docente,
                    TRY_CONVERT(nvarchar(4000), d.Perfil) AS perfil
                FROM dbo.DATOSDOCENTE d
                WHERE TRY_CONVERT(int, d.codigo_doc) = ?
                """,
                codigo_doc,
            )
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No se encontro el docente vinculado a la sesion")
        return {
            "teacher": {
                "codigo_doc": _clean(row.codigo_doc),
                "cedula": _clean(row.cedula),
                "docente": _clean(row.docente),
                "correo": _clean(row.correo),
                "correo_personal": _clean(row.correo_personal),
                "tipo_docente": _clean(row.tipo_docente),
                "perfil": _clean(row.perfil),
            }
        }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando perfil docente: {exc}") from exc


@router.get("/teacher/courses")
def teacher_courses(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
) -> dict[str, Any]:
    codigo_doc = _teacher_code(current_user)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1000)
                    TRY_CONVERT(varchar(50), cxd.codigo_doc) AS codigo_doc,
                    TRY_CONVERT(varchar(50), cxd.cod_Anio_Basica) AS cod_anio_basica,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
                    TRY_CONVERT(varchar(50), cxd.codigo_materia) AS codigo_materia,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N''),
                        TRY_CONVERT(nvarchar(100), p.codigo_materia),
                        TRY_CONVERT(nvarchar(100), cxd.codigo_materia)
                    ) AS cod_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
                    TRY_CONVERT(varchar(50), cxd.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS detalle_periodo,
                    TRY_CONVERT(nvarchar(100), pe.TipoMatricula) AS tipo_periodo,
                    COALESCE(TRY_CONVERT(int, pe.Orden), TRY_CONVERT(int, pe.cod_periodo)) AS periodo_orden,
                    TRY_CONVERT(nvarchar(50), cxd.Paralelo) AS paralelo,
                    TRY_CONVERT(int, cxd.Cod_Jornada) AS cod_jornada,
                    TRY_CONVERT(nvarchar(255), j.DetalleJ) AS jornada,
                    TRY_CONVERT(int, p.Semestre) AS semestre,
                    TRY_CONVERT(nvarchar(255), p.Unidad_Organiza) AS unidad_curricular,
                    TRY_CONVERT(int, cxd.estadoMoodleDoc) AS estado_moodle_doc,
                    stats.total_estudiantes
                FROM dbo.CARRERAXDOCENTE cxd
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                LEFT JOIN dbo.PERIODO pe
                  ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                LEFT JOIN dbo.JORNADA j
                  ON TRY_CONVERT(int, j.NumJ) = TRY_CONVERT(int, cxd.Cod_Jornada)
                OUTER APPLY (
                    SELECT COUNT(DISTINCT TRY_CONVERT(int, cxe.codigo_estud)) AS total_estudiantes
                    FROM dbo.CARRERAXESTUD cxe
                    LEFT JOIN dbo.PENSUM pxe
                      ON TRY_CONVERT(int, pxe.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                     AND TRY_CONVERT(int, pxe.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                    WHERE TRY_CONVERT(int, cxe.codigo_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                      AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxe.paralelo)))) =
                          UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo))))
                      AND UPPER(LTRIM(RTRIM(COALESCE(
                            NULLIF(TRY_CONVERT(nvarchar(100), pxe.cod_materia), N''),
                            TRY_CONVERT(nvarchar(100), pxe.codigo_materia),
                            TRY_CONVERT(nvarchar(100), cxe.codigo_materia),
                            N''
                      )))) = UPPER(LTRIM(RTRIM(COALESCE(
                            NULLIF(TRY_CONVERT(nvarchar(100), p.cod_materia), N''),
                            TRY_CONVERT(nvarchar(100), p.codigo_materia),
                            TRY_CONVERT(nvarchar(100), cxd.codigo_materia),
                            N''
                      ))))
                ) stats
                WHERE TRY_CONVERT(int, cxd.codigo_doc) = ?
                ORDER BY
                    COALESCE(TRY_CONVERT(int, pe.Orden), TRY_CONVERT(int, pe.cod_periodo)) DESC,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica),
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia),
                    TRY_CONVERT(nvarchar(50), cxd.Paralelo)
                """,
                codigo_doc,
            )
            items = _group_teacher_courses([_course_item(row) for row in cursor.fetchall()])
        return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando materias del docente: {exc}") from exc


def _teacher_student_item(row: Any) -> dict[str, Any]:
    item = _record_item(row)
    item.update(
        {
            "cedula": _clean(row.cedula),
            "nombre_estudiante": _clean(row.nombre_estudiante),
            "correo_personal": _clean(row.correo_personal),
            "correo_intec": _clean(row.correo_intec),
        }
    )
    return item


def _teacher_course_students_for_report(
    current_user: SessionUser,
    period_codes: list[int],
    subject_filter: str,
    parallel: str,
    cod_anio_basica: int | None = None,
    cod_jornada: int | None = None,
) -> list[dict[str, Any]]:
    students_by_key: dict[str, dict[str, Any]] = {}
    chunks = [period_codes[index:index + 2] for index in range(0, len(period_codes), 2)]
    for chunk in chunks:
        payload = teacher_course_students(
            current_user=current_user,
            codigo_periodo=chunk,
            codigo_materia=subject_filter,
            paralelo=parallel,
            cod_anio_basica=cod_anio_basica,
            cod_jornada=cod_jornada,
        )
        for item in payload.get("items") or []:
            key = "|".join(
                [
                    _clean(item.get("codigo_estud")),
                    _clean(item.get("codigo_periodo")),
                    _clean(item.get("cod_anio_basica")),
                    _clean(item.get("codigo_materia")),
                    _clean(item.get("paralelo")),
                    _clean(item.get("num_matricula")),
                    _clean(item.get("num_grupo")),
                ]
            )
            students_by_key[key] = item
    return list(students_by_key.values())


@router.get("/teacher/course-students")
def teacher_course_students(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    cod_anio_basica: Annotated[int | None, Query()] = None,
    cod_jornada: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    codigo_doc = _teacher_code(current_user)
    parallel = paralelo.strip().upper()
    subject_filter = _clean(codigo_materia).upper()
    period_codes = list(dict.fromkeys(codigo_periodo))
    if not period_codes:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un periodo")
    if not subject_filter:
        raise HTTPException(status_code=400, detail="Debe seleccionar una materia")
    if len(period_codes) > 2:
        raise HTTPException(status_code=400, detail="Solo se pueden consultar hasta 2 periodos regulares unidos")
    period_placeholders = ", ".join("?" for _ in period_codes)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                WITH teacher_assignment AS (
                    SELECT DISTINCT
                        cxd.codigo_periodo,
                        cxd.Paralelo,
                        cxd.Cod_Jornada,
                        COALESCE(
                            NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), pta.cod_materia))), N''),
                            TRY_CONVERT(nvarchar(100), pta.codigo_materia),
                            TRY_CONVERT(nvarchar(100), cxd.codigo_materia)
                        ) AS common_subject_code
                    FROM dbo.CARRERAXDOCENTE cxd
                    LEFT JOIN dbo.PENSUM pta
                      ON TRY_CONVERT(int, pta.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                     AND TRY_CONVERT(int, pta.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                    WHERE TRY_CONVERT(int, cxd.codigo_doc) = ?
                      AND (? IS NULL OR TRY_CONVERT(int, cxd.cod_Anio_Basica) = ?)
                      AND (? IS NULL OR TRY_CONVERT(int, cxd.Cod_Jornada) = ?)
                      AND (
                            TRY_CONVERT(nvarchar(100), cxd.codigo_materia) = ?
                            OR UPPER(LTRIM(RTRIM(COALESCE(
                                NULLIF(TRY_CONVERT(nvarchar(100), pta.cod_materia), N''),
                                TRY_CONVERT(nvarchar(100), pta.codigo_materia),
                                TRY_CONVERT(nvarchar(100), cxd.codigo_materia),
                                N''
                            )))) = ?
                      )
                      AND TRY_CONVERT(int, cxd.codigo_periodo) IN ({period_placeholders})
                      AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo)))) = ?
                )
                SELECT TOP (1000)
                    TRY_CONVERT(varchar(50), de.codigo_estud) AS codigo_estud,
                    TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS cedula,
                    TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS nombre_estudiante,
                    TRY_CONVERT(nvarchar(255), de.correo) AS correo_personal,
                    COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(255), ce.CorreoIntec), N''),
                        TRY_CONVERT(nvarchar(255), de.correointec)
                    ) AS correo_intec,
                    TRY_CONVERT(varchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
                    TRY_CONVERT(varchar(50), cxe.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS detalle_periodo,
                    TRY_CONVERT(int, pe.anio) AS anio_periodo,
                    TRY_CONVERT(varchar(50), cxe.codigo_materia) AS codigo_materia,
                    TRY_CONVERT(varchar(100), p.cod_materia) AS cod_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
                    TRY_CONVERT(int, p.Semestre) AS semestre,
                    TRY_CONVERT(int, p.NumMalla) AS num_malla,
                    TRY_CONVERT(float, p.Horas) AS horas,
                    TRY_CONVERT(int, p.Orden) AS orden,
                    TRY_CONVERT(float, COALESCE(NULLIF(cxe.Num_Creditos, 0), p.Creditos)) AS creditos,
                    TRY_CONVERT(nvarchar(50), cxe.paralelo) AS paralelo,
                    TRY_CONVERT(int, cxe.NumGrupo) AS num_grupo,
                    TRY_CONVERT(varchar(50), cxe.Num_Matricula) AS num_matricula,
                    cxe.Fecha_Matricula AS fecha_matricula,
                    TRY_CONVERT(nvarchar(20), cxe.TipoMatricula) AS tipo_matricula,
                    TRY_CONVERT(float, cxe.teoriaHomo) AS teoria_homo,
                    TRY_CONVERT(float, cxe.practicahomo) AS practica_homo,
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
                    TRY_CONVERT(float, cxe.Promedio) AS promedio,
                    TRY_CONVERT(float, cxe.Asistencia) AS asistencia,
                    TRY_CONVERT(float, cxe.Recuperacion) AS recuperacion,
                    TRY_CONVERT(float, cxe.PromedioFinal) AS promedio_final_raw,
                    COALESCE(
                        TRY_CONVERT(float, cxe.PromedioFinal),
                        CASE
                            WHEN (
                                    UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.TipoMatricula), N'')))) = N'H'
                                 OR UPPER(COALESCE(TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                                 )
                             AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                            THEN (TRY_CONVERT(float, cxe.teoriaHomo) * 0.4) + (TRY_CONVERT(float, cxe.practicahomo) * 0.6)
                        END,
                        CASE
                            WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                             AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                            THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                        END,
                        TRY_CONVERT(float, cxe.Promedio),
                        TRY_CONVERT(float, cxe.PromedioAux)
                    ) AS nota_final,
                    COALESCE(TRY_CONVERT(float, pe.NotaAprobar), 7) AS nota_aprobar,
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.caprueba), N'')))) LIKE N'A%' THEN 1
                        WHEN COALESCE(
                                TRY_CONVERT(float, cxe.PromedioFinal),
                                CASE
                                    WHEN (
                                            UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.TipoMatricula), N'')))) = N'H'
                                         OR UPPER(COALESCE(TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                                         )
                                     AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.teoriaHomo) * 0.4) + (TRY_CONVERT(float, cxe.practicahomo) * 0.6)
                                END,
                                CASE
                                    WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                                     AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                                    THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                                END,
                                TRY_CONVERT(float, cxe.Promedio),
                                TRY_CONVERT(float, cxe.PromedioAux)
                             ) >= COALESCE(TRY_CONVERT(float, pe.NotaAprobar), 7)
                        THEN 1
                        ELSE 0
                    END AS aprobada,
                    TRY_CONVERT(nvarchar(max), cxe.observaciones) AS observaciones,
                    TRY_CONVERT(nvarchar(255), cxe.seguimiento) AS seguimiento
                FROM dbo.CARRERAXESTUD cxe
                INNER JOIN dbo.DATOS_ESTUD de
                  ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, cxe.codigo_estud)
                LEFT JOIN dbo.CorreosEstudIntec ce
                  ON TRY_CONVERT(int, ce.codestud) = TRY_CONVERT(int, de.codigo_estud)
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                LEFT JOIN dbo.PERIODO pe
                  ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                WHERE (? IS NULL OR TRY_CONVERT(int, cxe.cod_anio_Basica) = ?)
                  AND EXISTS (
                      SELECT 1
                      FROM teacher_assignment ta
                      WHERE TRY_CONVERT(int, ta.codigo_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
                        AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), ta.Paralelo)))) =
                            UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxe.paralelo))))
                        AND UPPER(LTRIM(RTRIM(COALESCE(ta.common_subject_code, N'')))) =
                            UPPER(LTRIM(RTRIM(COALESCE(
                                NULLIF(TRY_CONVERT(nvarchar(100), p.cod_materia), N''),
                                TRY_CONVERT(nvarchar(100), p.codigo_materia),
                                TRY_CONVERT(nvarchar(100), cxe.codigo_materia),
                                N''
                            ))))
                  )
                ORDER BY
                    TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                    TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre)
                """,
                codigo_doc,
                cod_anio_basica,
                cod_anio_basica,
                cod_jornada,
                cod_jornada,
                subject_filter,
                subject_filter,
                *period_codes,
                parallel,
                cod_anio_basica,
                cod_anio_basica,
            )
            rows = cursor.fetchall()
        return {"total": len(rows), "items": [_teacher_student_item(row) for row in rows]}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando estudiantes del curso: {exc}") from exc


def _legacy_grade_text(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "-"
    return f"{number:.2f}".replace(".", ",")


def _teacher_course_report_meta(
    codigo_doc: int,
    period_codes: list[int],
    subject_filter: str,
    parallel: str,
    cod_anio_basica: int | None,
) -> dict[str, Any]:
    if not period_codes:
        return {}
    period_placeholders = ", ".join("?" for _ in period_codes)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT TOP (50)
                    TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
                    TRY_CONVERT(varchar(50), cxd.codigo_materia) AS codigo_materia,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N''),
                        TRY_CONVERT(nvarchar(100), p.codigo_materia),
                        TRY_CONVERT(nvarchar(100), cxd.codigo_materia)
                    ) AS cod_materia,
                    TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
                    TRY_CONVERT(varchar(50), cxd.codigo_periodo) AS codigo_periodo,
                    TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS detalle_periodo,
                    TRY_CONVERT(nvarchar(100), pe.TipoMatricula) AS tipo_periodo,
                    TRY_CONVERT(nvarchar(50), cxd.Paralelo) AS paralelo,
                    TRY_CONVERT(int, cxd.Cod_Jornada) AS cod_jornada,
                    TRY_CONVERT(nvarchar(255), j.DetalleJ) AS jornada,
                    TRY_CONVERT(int, p.Semestre) AS semestre,
                    TRY_CONVERT(nvarchar(255), p.Unidad_Organiza) AS unidad_curricular,
                    TRY_CONVERT(float, p.Horas) AS horas
                FROM dbo.CARRERAXDOCENTE cxd
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                LEFT JOIN dbo.PERIODO pe
                  ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                LEFT JOIN dbo.PENSUM p
                  ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                 AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                LEFT JOIN dbo.JORNADA j
                  ON TRY_CONVERT(int, j.NumJ) = TRY_CONVERT(int, cxd.Cod_Jornada)
                WHERE TRY_CONVERT(int, cxd.codigo_doc) = ?
                  AND (? IS NULL OR TRY_CONVERT(int, cxd.cod_Anio_Basica) = ?)
                  AND (
                        TRY_CONVERT(nvarchar(100), cxd.codigo_materia) = ?
                        OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), p.cod_materia), N'')))) = ?
                  )
                  AND TRY_CONVERT(int, cxd.codigo_periodo) IN ({period_placeholders})
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo)))) = ?
                ORDER BY TRY_CONVERT(int, cxd.codigo_periodo) DESC
                """,
                codigo_doc,
                cod_anio_basica,
                cod_anio_basica,
                subject_filter,
                subject_filter,
                *period_codes,
                parallel,
            )
            rows = cursor.fetchall()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando datos del reporte docente: {exc}") from exc

    if not rows:
        return {}
    careers: list[str] = []
    periods: list[str] = []
    first = rows[0]
    for row in rows:
        career = _clean(row.nombre_carrera)
        if career and career not in careers:
            careers.append(career)
        period = _clean(row.detalle_periodo) or _clean(row.codigo_periodo)
        if period and period not in periods:
            periods.append(period)
    return {
        "nombre_carrera": " / ".join(careers) if len(careers) <= 2 else f"{len(careers)} carreras",
        "detalle_periodo": " / ".join(periods),
        "codigo_materia": _clean(first.codigo_materia),
        "cod_materia": _clean(first.cod_materia),
        "nombre_materia": _clean(first.nombre_materia),
        "paralelo": _clean(first.paralelo),
        "cod_jornada": _clean(first.cod_jornada),
        "jornada": _clean(first.jornada) or (f"Jornada {_clean(first.cod_jornada)}" if _clean(first.cod_jornada) else ""),
        "semestre": _int(first.semestre),
        "unidad_curricular": _clean(first.unidad_curricular),
        "horas": _number(first.horas),
        "es_homologacion": _is_homologation_type(first.tipo_periodo, first.detalle_periodo),
    }


def _teacher_report_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_pdf_text(value), style)


def _teacher_notes_report_pdf(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
) -> bytes:
    red = colors.HexColor("#931913")
    light_blue = colors.HexColor("#EAF5F8")
    blue = colors.HexColor("#8DBBC7")
    gray = colors.HexColor("#777777")
    dark = colors.HexColor("#111A3A")
    border = colors.HexColor("#BFC7CC")

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TeacherReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=13,
            leading=15,
            textColor=dark,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportCenter",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=8,
            leading=9.5,
            textColor=dark,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportMeta",
            parent=styles["BodyText"],
            fontSize=7.4,
            leading=9,
            textColor=dark,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportCell",
            parent=styles["BodyText"],
            fontSize=5.5,
            leading=6.35,
            textColor=dark,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportCellBold",
            parent=styles["TeacherReportCell"],
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            textColor=dark,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportHeaderWhite",
            parent=styles["TeacherReportCellBold"],
            textColor=colors.white,
            fontSize=5.6,
            leading=6.25,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportHeaderLight",
            parent=styles["TeacherReportCellBold"],
            textColor=dark,
            fontSize=5.4,
            leading=6.2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TeacherReportTiny",
            parent=styles["BodyText"],
            fontSize=6.3,
            leading=7.5,
            textColor=gray,
        )
    )

    period_label = _clean(meta.get("detalle_periodo")) or "-"
    subject_name = _clean(meta.get("nombre_materia")) or _clean(meta.get("codigo_materia")) or "-"
    is_homologation = bool(meta.get("es_homologacion")) or any(item.get("es_homologacion") for item in students)
    logo = _template_logo(3.45 * cm)

    def _status(value: Any) -> str:
        number = _number(value)
        if number is None:
            return "Pendiente"
        return "Aprobado" if number >= 7 else "Reprobado"

    story: list[Any] = []

    header_table = Table(
        [
            [
                logo,
                [
                    Paragraph(
                        "INSTITUTO SUPERIOR TECNOLÓGICO DE TÉCNICAS EMPRESARIALES Y DEL CONOCIMIENTO",
                        styles["TeacherReportCenter"],
                    ),
                    Paragraph("Reporte de notas por docente", styles["TeacherReportTitle"]),
                    Paragraph(f"Período académico: {period_label}", styles["TeacherReportCenter"]),
                ],
                Paragraph(
                    f"<b>Emitido:</b><br/>{datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    styles["TeacherReportTiny"],
                ),
            ]
        ],
        colWidths=[4.1 * cm, 17.2 * cm, 6.8 * cm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 1.2, red),
            ]
        )
    )
    story.extend([header_table, Spacer(1, 0.18 * cm)])

    jornada_label = _clean(meta.get("jornada")) or (
        f"Jornada {_clean(meta.get('cod_jornada'))}" if _clean(meta.get("cod_jornada")) else "-"
    )
    meta_rows = [
        [
            Paragraph(f"<b>Carrera:</b> {_pdf_text(meta.get('nombre_carrera'))}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Paralelo:</b> {_pdf_text(meta.get('paralelo'))}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Jornada:</b> {_pdf_text(jornada_label)}", styles["TeacherReportMeta"]),
        ],
        [
            Paragraph(f"<b>Docente:</b> {_pdf_text(teacher.get('docente'))}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Asignatura:</b> {_pdf_text(subject_name)}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Código:</b> {_pdf_text(meta.get('cod_materia') or meta.get('codigo_materia'))}", styles["TeacherReportMeta"]),
        ],
        [
            Paragraph(f"<b>Semestre:</b> {_pdf_text(meta.get('semestre'))}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Horas:</b> {_legacy_grade_text(meta.get('horas')) if _number(meta.get('horas')) is not None else '-'}", styles["TeacherReportMeta"]),
            Paragraph(f"<b>Estudiantes:</b> {len(students)}", styles["TeacherReportMeta"]),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[10.0 * cm, 10.0 * cm, 8.1 * cm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), light_blue),
                ("BOX", (0, 0), (-1, -1), 0.45, blue),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E3E8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 0.16 * cm)])

    if is_homologation:
        headers = [
            "No.",
            "CARRERA",
            "CEDULA",
            "APELLIDOS Y NOMBRES",
            "TEORIA 40%",
            "PRACTICA 60%",
            "Promedio Final",
            "Estado",
        ]
        col_widths = [0.8 * cm, 4.1 * cm, 2.35 * cm, 9.1 * cm, 2.35 * cm, 2.35 * cm, 2.2 * cm, 2.5 * cm]
        table_rows = [
            [
                _teacher_report_paragraph(index, styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("nombre_carrera"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("cedula"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("nombre_estudiante"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("teoria_homo")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("practica_homo")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("promedio_final")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_status(item.get("promedio_final")), styles["TeacherReportCell"]),
            ]
            for index, item in enumerate(students, start=1)
        ]
        table_data: list[list[Any]] = [
            [Paragraph(f"<b>{escape(header)}</b>", styles["TeacherReportHeaderWhite"]) for header in headers]
        ]
        repeat_rows = 1
        table_style_commands: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), red),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    else:
        header_group = [
            "No.",
            "CARRERA",
            "CEDULA",
            "APELLIDOS Y NOMBRES",
            "Parcial 1",
            "",
            "",
            "",
            "Parcial 2",
            "",
            "",
            "",
            "Parcial 3",
            "",
            "",
            "",
            "Prom.",
            "Recup.",
            "Final",
            "Estado",
        ]
        header_detail = [
            "",
            "",
            "",
            "",
            "Tareas 30%",
            "Proy. 40%",
            "Examen 30%",
            "Prom.",
            "Tareas 30%",
            "Proy. 40%",
            "Examen 30%",
            "Prom.",
            "Tareas 30%",
            "Proy. 40%",
            "Examen 30%",
            "Prom.",
            "",
            "",
            "",
            "",
        ]
        col_widths = [
            0.62 * cm,
            2.75 * cm,
            2.0 * cm,
            5.35 * cm,
            0.88 * cm,
            0.88 * cm,
            0.88 * cm,
            0.95 * cm,
            0.88 * cm,
            0.88 * cm,
            0.88 * cm,
            0.95 * cm,
            0.88 * cm,
            0.88 * cm,
            0.88 * cm,
            0.95 * cm,
            0.95 * cm,
            0.95 * cm,
            0.95 * cm,
            1.45 * cm,
        ]
        table_rows = [
            [
                _teacher_report_paragraph(index, styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("nombre_carrera"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("cedula"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(item.get("nombre_estudiante"), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p1_tareas")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p1_proyectos")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p1_examen")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("prom_p1")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p2_tareas")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p2_proyectos")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p2_examen")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("prom_p2")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p3_tareas")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p3_proyectos")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("p3_examen")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("prom_p3")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("promedio")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("recuperacion")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_legacy_grade_text(item.get("promedio_final")), styles["TeacherReportCell"]),
                _teacher_report_paragraph(_status(item.get("promedio_final")), styles["TeacherReportCell"]),
            ]
            for index, item in enumerate(students, start=1)
        ]
        table_data = [
            [
                Paragraph(f"<b>{escape(header)}</b>", styles["TeacherReportHeaderWhite" if header else "TeacherReportHeaderLight"])
                for header in header_group
            ],
            [
                Paragraph(f"<b>{escape(header)}</b>", styles["TeacherReportHeaderLight"])
                for header in header_detail
            ],
        ]
        repeat_rows = 2
        table_style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), red),
            ("BACKGROUND", (0, 1), (-1, 1), light_blue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (1, 1)),
            ("SPAN", (2, 0), (2, 1)),
            ("SPAN", (3, 0), (3, 1)),
            ("SPAN", (4, 0), (7, 0)),
            ("SPAN", (8, 0), (11, 0)),
            ("SPAN", (12, 0), (15, 0)),
            ("SPAN", (16, 0), (16, 1)),
            ("SPAN", (17, 0), (17, 1)),
            ("SPAN", (18, 0), (18, 1)),
            ("SPAN", (19, 0), (19, 1)),
        ]

    table_data.extend(table_rows)
    if len(table_rows) == 0:
        table_data.append([Paragraph("Sin estudiantes matriculados.", styles["TeacherReportCell"])] + [""] * (len(col_widths) - 1))

    grade_table = Table(table_data, colWidths=col_widths, repeatRows=repeat_rows)
    grade_table.setStyle(
        TableStyle(
            [
                *table_style_commands,
                ("GRID", (0, 0), (-1, -1), 0.25, border),
                ("FONTNAME", (0, 0), (-1, repeat_rows - 1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (1, repeat_rows), (3, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, repeat_rows), (-1, -1), [colors.white, colors.HexColor("#F7FAFB")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(grade_table)

    finals = [_number(item.get("promedio_final")) for item in students if _number(item.get("promedio_final")) is not None]
    average = round(sum(finals) / len(finals), 2) if finals else None
    story.extend(
        [
            Spacer(1, 0.18 * cm),
            Table(
                [[Paragraph(f"<b>Promedio general del curso:</b> {_legacy_grade_text(average)}", styles["TeacherReportMeta"])]],
                colWidths=[28.1 * cm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FCFD")),
                        ("BOX", (0, 0), (-1, -1), 0.35, blue),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
            ),
            Spacer(1, 0.85 * cm),
        ]
    )

    signature_style = styles["TeacherReportCenter"]
    signatures = Table(
        [
            ["____________________________", "____________________________", "____________________________"],
            [
                Paragraph("Secretaria Academica INTEC", signature_style),
                Paragraph("Firma del docente", signature_style),
                Paragraph("Coordinacion Academica", signature_style),
            ],
            [
                "",
                Paragraph(f"CI: {_pdf_text(teacher.get('cedula'))}", signature_style),
                "",
            ],
        ],
        colWidths=[6.4 * cm, 6.4 * cm, 6.4 * cm],
    )
    signatures.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(signatures)

    def draw_page(canvas: Any, _doc: Any) -> None:
        page_width, page_height = landscape(A4)
        canvas.saveState()
        canvas.setStrokeColor(red)
        canvas.setLineWidth(2.0)
        canvas.line(0.55 * cm, page_height - 0.45 * cm, page_width - 0.55 * cm, page_height - 0.45 * cm)
        canvas.setFont("Helvetica", 6.3)
        canvas.setFillColor(gray)
        canvas.drawString(0.6 * cm, 0.42 * cm, "Reporte academico INTEC")
        canvas.drawRightString(page_width - 0.6 * cm, 0.42 * cm, f"Pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    output = BytesIO()
    SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=0.55 * cm,
        leftMargin=0.55 * cm,
        topMargin=0.72 * cm,
        bottomMargin=0.7 * cm,
        title="Notas Por Docente",
    ).build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    output.seek(0)
    return output.getvalue()


def _student_grade_report_rows(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in students:
        key = "|".join(
            [
                _clean(item.get("codigo_estud")),
                _clean(item.get("codigo_periodo")),
                _clean(item.get("cod_anio_basica")),
            ]
        )
        if key.strip("|"):
            groups[key] = item

    result: list[dict[str, Any]] = []
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            for source in groups.values():
                cursor.execute(
                    """
                    SELECT
                        TRY_CONVERT(varchar(50), de.codigo_estud) AS codigo_estud,
                        TRY_CONVERT(nvarchar(100), de.Cedula_Est) AS cedula,
                        TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre) AS nombre_estudiante,
                        TRY_CONVERT(varchar(50), cxe.cod_anio_Basica) AS cod_anio_basica,
                        TRY_CONVERT(nvarchar(4000), c.Nombre_Basica) AS nombre_carrera,
                        TRY_CONVERT(varchar(50), cxe.codigo_periodo) AS codigo_periodo,
                        TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo) AS detalle_periodo,
                        TRY_CONVERT(nvarchar(100), pe.TipoMatricula) AS tipo_periodo,
                        TRY_CONVERT(varchar(50), cxe.codigo_materia) AS codigo_materia,
                        TRY_CONVERT(varchar(100), p.cod_materia) AS cod_materia,
                        TRY_CONVERT(nvarchar(4000), p.Nomb_Materia) AS nombre_materia,
                        TRY_CONVERT(float, COALESCE(NULLIF(cxe.Num_Creditos, 0), p.Creditos)) AS creditos,
                        TRY_CONVERT(float, cxe.teoriaHomo) AS teoria_homo,
                        TRY_CONVERT(float, cxe.practicahomo) AS practica_homo,
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
                        TRY_CONVERT(float, cxe.Promedio) AS promedio,
                        TRY_CONVERT(float, cxe.Recuperacion) AS recuperacion,
                        COALESCE(
                            TRY_CONVERT(float, cxe.PromedioFinal),
                            CASE
                                WHEN (
                                        UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(50), cxe.TipoMatricula), N'')))) = N'H'
                                     OR UPPER(COALESCE(TRY_CONVERT(nvarchar(4000), pe.Detalle_Periodo), N'')) LIKE N'%HOMO%'
                                     )
                                 AND TRY_CONVERT(float, cxe.teoriaHomo) IS NOT NULL
                                 AND TRY_CONVERT(float, cxe.practicahomo) IS NOT NULL
                                THEN (TRY_CONVERT(float, cxe.teoriaHomo) * 0.4) + (TRY_CONVERT(float, cxe.practicahomo) * 0.6)
                            END,
                            CASE
                                WHEN TRY_CONVERT(float, cxe.promP1) IS NOT NULL
                                 AND TRY_CONVERT(float, cxe.promP2) IS NOT NULL
                                 AND TRY_CONVERT(float, cxe.promP3) IS NOT NULL
                                THEN (TRY_CONVERT(float, cxe.promP1) + TRY_CONVERT(float, cxe.promP2) + TRY_CONVERT(float, cxe.promP3)) / 3
                            END,
                            TRY_CONVERT(float, cxe.Promedio)
                        ) AS promedio_final,
                        COALESCE(TRY_CONVERT(float, pe.NotaAprobar), 7) AS nota_aprobar,
                        TRY_CONVERT(nvarchar(50), cxe.TipoMatricula) AS tipo_matricula,
                        TRY_CONVERT(nvarchar(50), cxe.paralelo) AS paralelo,
                        TRY_CONVERT(int, p.Orden) AS orden_materia
                    FROM dbo.CARRERAXESTUD cxe
                    INNER JOIN dbo.DATOS_ESTUD de
                      ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, cxe.codigo_estud)
                    LEFT JOIN dbo.CARRERAS c
                      ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                    LEFT JOIN dbo.PERIODO pe
                      ON TRY_CONVERT(int, pe.cod_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
                    LEFT JOIN dbo.PENSUM p
                      ON TRY_CONVERT(int, p.Cod_AnioBasica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                     AND TRY_CONVERT(int, p.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                    WHERE TRY_CONVERT(int, cxe.codigo_estud) = ?
                      AND TRY_CONVERT(int, cxe.codigo_periodo) = ?
                      AND TRY_CONVERT(int, cxe.cod_anio_Basica) = ?
                    ORDER BY TRY_CONVERT(int, p.Orden), TRY_CONVERT(nvarchar(4000), p.Nomb_Materia)
                    """,
                    _int(source.get("codigo_estud")),
                    _int(source.get("codigo_periodo")),
                    _int(source.get("cod_anio_basica")),
                )
                columns = [column[0] for column in cursor.description or []]
                rows = [{column: getattr(row, column) for column in columns} for row in cursor.fetchall()]
                if rows:
                    result.extend(rows)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando reporte de notas del estudiante: {exc}") from exc
    return result


def _student_secretaria_notes_pdf(
    profile: dict[str, Any],
    items: list[dict[str, Any]],
    report_type: str,
    period_label: str,
) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=landscape(A4))
    width, height = landscape(A4)
    generated_at = datetime.now()
    hour = generated_at.hour % 12 or 12
    display_date = f"{generated_at.day} de {generated_at.strftime('%B')} de {generated_at.year}"

    def clean(value: Any, fallback: str = "") -> str:
        text = _clean(value)
        return text or fallback

    def fit_text(text: Any, max_chars: int) -> str:
        value = clean(text, "-")
        if len(value) <= max_chars:
            return value
        return value[: max(max_chars - 1, 1)].rstrip() + "…"

    def grade(value: Any, empty: str = "") -> str:
        number = _number(value)
        if number is None:
            return empty
        return f"{number:.2f}"

    def credit(value: Any) -> str:
        number = _number(value)
        if number is None:
            return ""
        return f"{number:.2f}".replace(".", ",")

    def final_status(item: dict[str, Any]) -> str:
        final = _number(item.get("promedio_final"))
        if final is None:
            return "PENDIENTE"
        minimum = _number(item.get("nota_aprobar")) or 7
        return "APROBADO" if final >= minimum else "REPROBADO"

    def row_values(item: dict[str, Any]) -> list[str]:
        is_homo = _is_homologation_type(
            item.get("tipo_matricula"),
            item.get("detalle_periodo") or item.get("ultimo_periodo"),
            item.get("esquema_calificacion"),
        )
        partial_values = [
            grade(item.get("p1_tareas")),
            grade(item.get("p1_proyectos")),
            grade(item.get("p1_examen")),
            grade(item.get("prom_p1")),
            grade(item.get("p2_tareas")),
            grade(item.get("p2_proyectos")),
            grade(item.get("p2_examen")),
            grade(item.get("prom_p2")),
            grade(item.get("p3_tareas")),
            grade(item.get("p3_proyectos")),
            grade(item.get("p3_examen")),
            grade(item.get("prom_p3")),
        ]
        if is_homo and all(value == "-" for value in partial_values):
            partial_values = [
                grade(item.get("teoria_homo")),
                grade(item.get("practica_homo")),
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
            ]
        subject_name = item.get("nombre_materia") or item.get("codigo_materia")
        subject_max_chars = 50 if _practice_requirement_code(item) else 36
        return [
            fit_text(subject_name, subject_max_chars),
            credit(item.get("creditos")),
            *partial_values,
            grade(item.get("recuperacion")),
            grade(item.get("promedio_final")),
            final_status(item),
        ]

    def period_key(item: dict[str, Any]) -> tuple[int, str]:
        code = _int(item.get("codigo_periodo"))
        label = clean(item.get("detalle_periodo") or item.get("ultimo_periodo") or period_label or "Malla academica general")
        return (code or 999999, label)

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(period_key(item), []).append(item)
    for (_code, label), group_items in sorted(grouped.items(), key=lambda pair: pair[0]):
        groups.append((label, group_items))
    if not groups:
        groups = [(period_label or "Malla academica general", [])]

    def draw_logo() -> None:
        if not _LOGO_PATH.exists():
            canvas.setFont("Helvetica-Bold", 38)
            canvas.setFillColor(colors.HexColor("#808285"))
            canvas.drawString(36, height - 48, "intec")
            return
        drawing = svg2rlg(str(_LOGO_PATH))
        if not drawing:
            return
        target_width = 130
        scale = target_width / float(drawing.width or target_width)
        canvas.saveState()
        canvas.translate(36, height - 58)
        canvas.scale(scale, scale)
        renderPDF.draw(drawing, canvas, 0, 0)
        canvas.restoreState()

    def draw_header(page_number: int) -> None:
        canvas.setFillColor(colors.black)
        canvas.rect(0, height - 5, width, 5, stroke=0, fill=1)
        if page_number == 1:
            draw_logo()
            canvas.setFont("Helvetica-Bold", 18)
            canvas.drawCentredString(width / 2, height - 52, "RECORD ACADÉMICO")
        canvas.setFont("Helvetica-Bold", 7.6)
        career = next((clean(item.get("nombre_carrera")) for item in items if clean(item.get("nombre_carrera"))), "")
        canvas.drawString(54, height - 72, "Estudiante:")
        canvas.drawString(114, height - 72, fit_text(profile.get("nombre_estudiante"), 42))
        canvas.drawString(378, height - 72, "Cédula:")
        canvas.setFont("Helvetica", 7.6)
        canvas.drawString(422, height - 72, fit_text(profile.get("cedula"), 18))
        canvas.setFont("Helvetica-Bold", 7.6)
        canvas.drawString(74, height - 90, "Carrera:")
        canvas.setFont("Helvetica", 7.6)
        canvas.drawString(114, height - 90, fit_text(career, 48))
        canvas.setFont("Helvetica-Bold", 7.6)
        canvas.drawString(62, height - 108, "Modalidad:")
        canvas.setFont("Helvetica", 7.6)
        canvas.drawString(114, height - 108, "En linea")

    x_positions = [30, 228, 282, 306, 330, 354, 402, 426, 450, 474, 522, 546, 570, 594, 642, 684, 740]
    col_widths = [194, 38, 23, 23, 23, 42, 23, 23, 23, 42, 23, 23, 23, 42, 34, 40, 62]
    row_height = 16.2
    header_y = height - 126
    first_row_y = height - 155
    bottom_y = 76

    def center_text(text: str, x: float, y: float, w: float, font: str = "Helvetica", size: float = 7) -> None:
        canvas.setFont(font, size)
        canvas.drawCentredString(x + (w / 2), y, text)

    def draw_table_header() -> None:
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.drawString(54, header_y + 1, "Asignatura")
        center_text("Créditos", x_positions[1], header_y + 1, col_widths[1], "Helvetica-Bold", 7.2)
        center_text("PARCIAL 1", x_positions[2], header_y + 10, sum(col_widths[2:6]), "Helvetica-Bold", 7.2)
        center_text("PARCIAL 2", x_positions[6], header_y + 10, sum(col_widths[6:10]), "Helvetica-Bold", 7.2)
        center_text("PARCIAL 3", x_positions[10], header_y + 10, sum(col_widths[10:14]), "Helvetica-Bold", 7.2)
        center_text("Recup.", x_positions[14], header_y + 1, col_widths[14], "Helvetica-Bold", 6.6)
        center_text("Promedio", x_positions[15], header_y + 9, col_widths[15], "Helvetica-Bold", 6.6)
        center_text("final", x_positions[15], header_y - 1, col_widths[15], "Helvetica-Bold", 6.6)
        center_text("Estado", x_positions[16], header_y + 1, col_widths[16], "Helvetica-Bold", 7.2)
        labels = ["N 1", "N 2", "N3", "PROM 1", "N 1", "N 2", "N3", "PROM 2", "N 1", "N 2", "N3", "PROM 3"]
        for index, label in enumerate(labels, start=2):
            center_text(label, x_positions[index], header_y - 7, col_widths[index], "Helvetica-Bold", 6.3)

    def draw_dotted_line(y: float) -> None:
        canvas.saveState()
        canvas.setDash(1, 3)
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(0.45)
        canvas.line(0, y - 5, width, y - 5)
        canvas.restoreState()

    def group_stats(group_items: list[dict[str, Any]]) -> tuple[str, str]:
        finals = [_number(item.get("promedio_final")) for item in group_items if _number(item.get("promedio_final")) is not None]
        credits = [_number(item.get("creditos")) for item in group_items if _number(item.get("creditos")) is not None]
        average = sum(finals) / len(finals) if finals else None
        total_credits = sum(credits) if credits else None
        return credit(total_credits), grade(average)

    def draw_row(item: dict[str, Any], y: float) -> None:
        values = row_values(item)
        canvas.setFont("Helvetica", 6.7)
        canvas.drawString(x_positions[0], y, values[0])
        canvas.setFont("Helvetica", 6.5)
        for index, value in enumerate(values[1:], start=1):
            if index == 16:
                canvas.drawString(x_positions[index], y, fit_text(value, 10))
            else:
                canvas.drawRightString(x_positions[index] + col_widths[index] - 2, y, value)
        draw_dotted_line(y)

    def draw_group_footer(group_items: list[dict[str, Any]], y: float) -> float:
        total_credits, average = group_stats(group_items)
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.drawString(162, y, "Total Créditos:")
        canvas.drawRightString(258, y, total_credits)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(648, y, "Promedio")
        canvas.drawRightString(742, y, average)
        return y - 18

    def draw_final_footer(y: float) -> None:
        footer_y = min(y, 204)
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(32, footer_y - 20, "NOTA:  *  Información basada en los soportes de los archivos y registros académicos que reposan en el Departamento de Secretaría General, cualquier alteración al texto del")
        canvas.drawString(32, footer_y - 32, "presente documento, como enmendadura, tachado, borrón o repisado entre otros lo inválida.")
        canvas.drawString(32, footer_y - 80, "* Este documento tiene una validez si tiene firma y sello del Instituto INTEC")
        canvas.drawRightString(width - 74, footer_y - 102, display_date)
        canvas.line(340, footer_y - 158, 535, footer_y - 158)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawCentredString(437, footer_y - 180, "María Verónica Cevallos Calderón")
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.drawCentredString(437, footer_y - 198, "Vicerrectora General Académico")

    def new_page(page_number: int) -> float:
        if page_number > 1:
            canvas.showPage()
        draw_header(page_number)
        draw_table_header()
        return first_row_y

    page_number = 1
    y = new_page(page_number)
    for label, group_items in groups:
        if y < bottom_y + (row_height * 3):
            page_number += 1
            y = new_page(page_number)
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.drawString(36, y, fit_text(label, 78))
        y -= row_height
        if not group_items:
            draw_row({"nombre_materia": "No hay informacion para mostrar.", "estado_academico": "PENDIENTE"}, y)
            y -= row_height
        for item in group_items:
            if y < bottom_y:
                page_number += 1
                y = new_page(page_number)
            draw_row(item, y)
            y -= row_height
        if y < bottom_y:
            page_number += 1
            y = new_page(page_number)
        y = draw_group_footer(group_items, y)

    if y < 224:
        page_number += 1
        y = new_page(page_number)
    draw_final_footer(y)

    canvas.save()
    output.seek(0)
    return output.getvalue()


def _student_grade_report_pdf(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
    include_teacher: bool = True,
) -> bytes:
    rows = _student_grade_report_rows(students)
    if not rows:
        rows = students

    red = colors.HexColor("#931913")
    dark = colors.HexColor("#111111")
    soft = colors.HexColor("#F4F8FA")
    border = colors.HexColor("#9DA8B0")
    gray = colors.HexColor("#555555")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SecretaryTitle", parent=styles["Title"], fontSize=14, leading=16, alignment=TA_CENTER, textColor=dark))
    styles.add(ParagraphStyle(name="SecretaryMeta", parent=styles["BodyText"], fontSize=8.6, leading=10.2, textColor=dark))
    styles.add(ParagraphStyle(name="SecretaryMetaRight", parent=styles["SecretaryMeta"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="SecretaryCell", parent=styles["BodyText"], fontSize=6.0, leading=6.8, textColor=dark))
    styles.add(ParagraphStyle(name="SecretaryCellBold", parent=styles["SecretaryCell"], fontName="Helvetica-Bold", alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="SecretaryTiny", parent=styles["BodyText"], fontSize=6.4, leading=7.8, textColor=gray))

    def status(value: Any, minimum: Any = 7) -> str:
        number = _number(value)
        min_value = _number(minimum) or 7
        if number is None:
            return "PENDIENTE"
        return "APROBADO" if number >= min_value else "REPROBADO"

    def grade(value: Any) -> str:
        number = _number(value)
        if number is None:
            return "-"
        return f"{number:.2f}"

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = "|".join([_clean(row.get("codigo_estud")), _clean(row.get("codigo_periodo")), _clean(row.get("cod_anio_basica"))])
        grouped.setdefault(key, []).append(row)

    story: list[Any] = []
    if not grouped:
        logo = _template_logo(3.1 * cm)
        header = Table(
            [
                [
                    logo,
                    [
                        Paragraph("INSTITUTO SUPERIOR TECNOLÓGICO INTEC", styles["SecretaryTitle"]),
                        Paragraph("Reporte de notas", styles["SecretaryMeta"]),
                    ],
                    Paragraph(datetime.now().strftime("%d/%m/%Y, %H:%M"), styles["SecretaryMetaRight"]),
                ]
            ],
            colWidths=[3.5 * cm, 10.5 * cm, 4.5 * cm],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 1.1, red)]))
        story.extend(
            [
                header,
                Spacer(1, 0.35 * cm),
                Paragraph("No existen estudiantes o calificaciones para generar el reporte con los filtros seleccionados.", styles["SecretaryMeta"]),
            ]
        )

    for group_index, group_rows in enumerate(grouped.values()):
        first = group_rows[0]
        if group_index:
            story.append(PageBreak())

        logo = _template_logo(3.1 * cm)
        header = Table(
            [
                [
                    logo,
                    [
                        Paragraph("INSTITUTO SUPERIOR TECNOLÓGICO INTEC", styles["SecretaryTitle"]),
                        Paragraph("Reporte de notas", styles["SecretaryMeta"]),
                    ],
                    Paragraph(datetime.now().strftime("%d/%m/%Y, %H:%M"), styles["SecretaryMetaRight"]),
                ]
            ],
            colWidths=[3.5 * cm, 10.5 * cm, 4.5 * cm],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 1.1, red)]))
        story.extend([header, Spacer(1, 0.18 * cm)])

        meta_table = Table(
            [
                [
                    Paragraph(f"<b>Carrera:</b> {_pdf_text(first.get('nombre_carrera'))}", styles["SecretaryMeta"]),
                    Paragraph(f"<b>Estudiante:</b> {_pdf_text(first.get('nombre_estudiante'))}", styles["SecretaryMeta"]),
                    Paragraph(f"<b>Cédula:</b> {_pdf_text(first.get('cedula'))}", styles["SecretaryMeta"]),
                ],
                [
                    Paragraph(f"<b>Período:</b> {_pdf_text(first.get('detalle_periodo') or first.get('codigo_periodo'))}", styles["SecretaryMeta"]),
                    Paragraph(f"<b>Modalidad:</b> En línea", styles["SecretaryMeta"]),
                    Paragraph(
                        f"<b>Docente:</b> {_pdf_text(teacher.get('docente'))}"
                        if include_teacher
                        else f"<b>Código:</b> {_pdf_text(first.get('codigo_estud'))}",
                        styles["SecretaryMeta"],
                    ),
                ],
            ],
            colWidths=[6.1 * cm, 7.2 * cm, 5.2 * cm],
        )
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), soft),
                    ("BOX", (0, 0), (-1, -1), 0.35, border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.2, border),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([meta_table, Spacer(1, 0.18 * cm)])

        header_1 = [
            "Asignatura",
            "Parcial 1", "", "", "",
            "Parcial 2", "", "", "",
            "Parcial 3", "", "", "",
            "Promedio final",
            "Recup.",
            "Estado",
            "Créditos",
        ]
        header_2 = [
            "",
            "N1", "N2", "N3", "PROM",
            "N1", "N2", "N3", "PROM",
            "N1", "N2", "N3", "PROM",
            "", "", "", "",
        ]
        table_rows = [
            [Paragraph(f"<b>{escape(item)}</b>", styles["SecretaryCellBold"]) for item in header_1],
            [Paragraph(f"<b>{escape(item)}</b>", styles["SecretaryCellBold"]) for item in header_2],
        ]
        for item in group_rows:
            table_rows.append(
                [
                    Paragraph(_pdf_text(item.get("nombre_materia")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p1_tareas")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p1_proyectos")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p1_examen")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("prom_p1")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p2_tareas")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p2_proyectos")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p2_examen")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("prom_p2")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p3_tareas")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p3_proyectos")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("p3_examen")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("prom_p3")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("promedio_final")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("recuperacion")), styles["SecretaryCell"]),
                    Paragraph(status(item.get("promedio_final"), item.get("nota_aprobar")), styles["SecretaryCell"]),
                    Paragraph(grade(item.get("creditos")), styles["SecretaryCell"]),
                ]
            )

        col_widths = [4.0 * cm] + [0.82 * cm] * 12 + [1.18 * cm, 0.95 * cm, 1.32 * cm, 0.95 * cm]
        grades_table = Table(table_rows, colWidths=col_widths, repeatRows=2)
        grades_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), red),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#E8EEF1")),
                    ("SPAN", (0, 0), (0, 1)),
                    ("SPAN", (1, 0), (4, 0)),
                    ("SPAN", (5, 0), (8, 0)),
                    ("SPAN", (9, 0), (12, 0)),
                    ("SPAN", (13, 0), (13, 1)),
                    ("SPAN", (14, 0), (14, 1)),
                    ("SPAN", (15, 0), (15, 1)),
                    ("SPAN", (16, 0), (16, 1)),
                    ("GRID", (0, 0), (-1, -1), 0.25, border),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (0, 2), (0, -1), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(grades_table)

        finals = [_number(item.get("promedio_final")) for item in group_rows if _number(item.get("promedio_final")) is not None]
        credits = [_number(item.get("creditos")) for item in group_rows if _number(item.get("creditos")) is not None]
        average = sum(finals) / len(finals) if finals else None
        failed = sum(1 for item in group_rows if status(item.get("promedio_final"), item.get("nota_aprobar")) == "REPROBADO")
        story.extend(
            [
                Spacer(1, 0.16 * cm),
                Table(
                    [
                        [
                            Paragraph(f"<b>Promedio:</b> {grade(average)}", styles["SecretaryMeta"]),
                            Paragraph(f"<b>Total créditos:</b> {grade(sum(credits) if credits else None)}", styles["SecretaryMeta"]),
                            Paragraph(f"<b>Reprobadas:</b> {failed}", styles["SecretaryMeta"]),
                        ]
                    ],
                    colWidths=[6.1 * cm, 6.1 * cm, 6.3 * cm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), soft),
                            ("BOX", (0, 0), (-1, -1), 0.35, border),
                            ("INNERGRID", (0, 0), (-1, -1), 0.2, border),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    ),
                ),
                Spacer(1, 0.55 * cm),
                Paragraph("____________________________", styles["SecretaryMetaRight"]),
                Paragraph("Vicerrectora General Académico", styles["SecretaryMetaRight"]),
                Paragraph("María Verónica Cevallos Calderón", styles["SecretaryMetaRight"]),
                Spacer(1, 0.22 * cm),
                Paragraph(
                    "NOTA: Información basada en los soportes de los archivos y registros académicos que reposan en el Departamento de Secretaría General; cualquier alteración al texto del presente documento, como enmendadura, tachado, borrón o repisado, lo invalida.",
                    styles["SecretaryTiny"],
                ),
                Paragraph("* Este documento tiene validez si tiene firma y sello del Instituto INTEC.", styles["SecretaryTiny"]),
            ]
        )

    def draw_page(canvas: Any, _doc: Any) -> None:
        width, height = letter
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(gray)
        canvas.drawString(0.7 * cm, 0.45 * cm, "INTEC")
        canvas.drawRightString(width - 0.7 * cm, 0.45 * cm, f"Página {canvas.getPageNumber()}")
        canvas.restoreState()

    output = BytesIO()
    SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.62 * cm,
        leftMargin=0.62 * cm,
        topMargin=0.62 * cm,
        bottomMargin=0.7 * cm,
        title="Reporte de Notas Secretaria",
    ).build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    output.seek(0)
    return output.getvalue()


def _teacher_compliance_report_pdf(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
    report_format: dict[str, Any],
    params: dict[str, Any],
    evidence_images: list[dict[str, Any]] | None = None,
) -> bytes:
    return _teacher_compliance_model_pdf(teacher, meta, students, report_format, params, evidence_images)


def _teacher_compliance_model_pdf(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
    report_format: dict[str, Any],
    params: dict[str, Any],
    evidence_images: list[dict[str, Any]] | None = None,
) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=A4)
    width, height = A4
    margin_x = 72
    body_x = 72
    body_right = width - 58
    content_width = body_right - body_x
    dark = colors.HexColor("#111111")

    def draw_page_background() -> None:
        if not _TEACHER_COMPLIANCE_BACKGROUND_PATH.exists():
            return
        canvas.saveState()
        canvas.drawImage(
            ImageReader(str(_TEACHER_COMPLIANCE_BACKGROUND_PATH)),
            0,
            0,
            width=width,
            height=height,
            preserveAspectRatio=False,
            mask="auto",
        )
        canvas.restoreState()

    def draw_logo() -> None:
        drawing = svg2rlg(str(_LOGO_PATH)) if _LOGO_PATH.exists() else None
        if drawing:
            scale = 190 / float(drawing.width or 190)
            canvas.saveState()
            canvas.translate(34, height - 104)
            canvas.scale(scale, scale)
            renderPDF.draw(drawing, canvas, 0, 0)
            canvas.restoreState()
        else:
            canvas.setFont("Helvetica-Bold", 58)
            canvas.setFillColor(colors.HexColor("#808285"))
            canvas.drawString(34, height - 86, "intec")

    def draw_header(page_num: int) -> None:
        if not _TEACHER_COMPLIANCE_BACKGROUND_PATH.exists():
            draw_logo()
        x = 242
        y = height - 123
        w = 322
        bottom_h = 38
        row_h = 24
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(1)
        canvas.rect(x, y, w, bottom_h + row_h * 2, stroke=1, fill=0)
        canvas.line(x, y + bottom_h, x + w, y + bottom_h)
        canvas.line(x, y + bottom_h + row_h, x + w, y + bottom_h + row_h)
        canvas.line(x + 194, y, x + 194, y + bottom_h)
        canvas.setFillColor(dark)
        canvas.setFont("Times-Bold", 12)
        canvas.drawCentredString(x + w / 2, y + bottom_h + row_h + 7, "Instituto Superior Tecnológico INTEC")
        canvas.drawCentredString(x + w / 2, y + bottom_h + 7, "Vicerrectorado Académico")
        canvas.setFont("Times-Roman", 12)
        canvas.drawCentredString(x + 97, y + 21, "Informe de finalización de asignatura")
        canvas.drawCentredString(x + 97, y + 8, "para pago")
        canvas.setFont("Times-Roman", 14)
        canvas.drawCentredString(x + 258, y + 15, f"Página {page_num} de 4")

    def draw_watermark() -> None:
        canvas.saveState()
        canvas.setFillColor(colors.Color(0.55, 0.0, 0.0, alpha=0.13))
        canvas.setFont("Helvetica-Bold", 620)
        canvas.drawString(-150, -20, "e")
        canvas.restoreState()

    def draw_footer() -> None:
        canvas.saveState()
        canvas.setFillColor(gray)
        canvas.setFont("Helvetica", 13)
        text = canvas.beginText(width / 2 - 90, 34)
        text.setCharSpace(6)
        text.textLine("www.intec.edu.ec")
        canvas.drawText(text)
        canvas.restoreState()

    def start_page(page_num: int) -> None:
        draw_page_background()
        draw_header(page_num)
        if not _TEACHER_COMPLIANCE_BACKGROUND_PATH.exists():
            draw_watermark()
            draw_footer()
        canvas.setFillColor(dark)

    def new_page(page_num: int) -> None:
        canvas.showPage()
        start_page(page_num)

    def line(text: str, x: float, y: float, size: int = 11, bold: bool = False) -> float:
        canvas.setFillColor(dark)
        canvas.setFont("Times-Bold" if bold else "Times-Roman", size)
        canvas.drawString(x, y, text)
        return y - (size + 4)

    def wrapped(text: str, x: float, y: float, max_width: float, size: int = 11, bold: bool = False, leading: float = 13) -> float:
        canvas.setFont("Times-Bold" if bold else "Times-Roman", size)
        words = _clean(text).split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if canvas.stringWidth(candidate, "Times-Bold" if bold else "Times-Roman", size) <= max_width:
                current = candidate
            else:
                canvas.drawString(x, y, current)
                y -= leading
                current = word
        if current:
            canvas.drawString(x, y, current)
            y -= leading
        return y

    def highlight(text: str, x: float, y: float, size: int = 11) -> None:
        canvas.setFont("Times-Bold", size)
        tw = canvas.stringWidth(text, "Times-Bold", size)
        canvas.setFillColor(colors.yellow)
        canvas.rect(x - 1, y - 2, tw + 2, size + 2, stroke=0, fill=1)
        canvas.setFillColor(dark)
        canvas.drawString(x, y, text)

    def evidence_group(*terms: str) -> list[dict[str, Any]]:
        lowered_terms = [term.lower() for term in terms]
        return [
            item
            for item in (evidence_images or [])
            if any(term in _clean(item.get("label")).lower() for term in lowered_terms)
        ]

    def draw_image(content: bytes, x: float, y: float, max_w: float, max_h: float) -> float:
        try:
            image = PILImage.open(BytesIO(content))
            image.verify()
            image = PILImage.open(BytesIO(content))
        except Exception:
            return y
        iw, ih = image.size
        if iw <= 0 or ih <= 0:
            return y
        ratio = min(max_w / iw, max_h / ih, 1)
        draw_w = iw * ratio
        draw_h = ih * ratio
        canvas.drawImage(ImageReader(BytesIO(content)), x, y - draw_h, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        return y - draw_h - 12

    def draw_group(terms: tuple[str, ...], x: float, y: float, max_w: float, max_h_each: float, max_count: int | None = None) -> float:
        items = evidence_group(*terms)
        if max_count is not None:
            items = items[:max_count]
        for item in items:
            content = item.get("content")
            if content:
                y = draw_image(content, x, y, max_w, max_h_each)
        return y

    def draw_selected_students_table(x: float, y: float, max_w: float) -> float:
        row_h = 12
        headers = ["No.", "Estudiante", "Cédula", "Carrera", "Final"]
        col_widths = [24, 170, 72, 118, 42]
        table_w = min(sum(col_widths), max_w)
        max_rows = 7
        visible_students = students[:max_rows]
        total_rows = 1 + len(visible_students)
        table_h = total_rows * row_h
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c7c7c7"))
        canvas.setLineWidth(0.45)
        canvas.setFillColor(colors.HexColor("#f2f2f2"))
        canvas.rect(x, y - row_h, table_w, row_h, stroke=1, fill=1)
        cursor_x = x
        canvas.setFillColor(dark)
        canvas.setFont("Times-Bold", 6.8)
        for header, col_w in zip(headers, col_widths):
            canvas.drawString(cursor_x + 3, y - 8, header)
            canvas.line(cursor_x, y, cursor_x, y - table_h)
            cursor_x += col_w
        canvas.line(x + table_w, y, x + table_w, y - table_h)
        canvas.line(x, y, x + table_w, y)
        canvas.line(x, y - row_h, x + table_w, y - row_h)
        canvas.setFont("Times-Roman", 6.6)
        current_y = y - row_h
        for index, item in enumerate(visible_students, start=1):
            next_y = current_y - row_h
            canvas.line(x, next_y, x + table_w, next_y)
            values = [
                str(index),
                _clean(item.get("nombre_estudiante")) or _clean(item.get("estudiante")) or "-",
                _clean(item.get("cedula")) or _clean(item.get("numero_identificacion")) or "-",
                _clean(item.get("nombre_carrera")) or "-",
                _legacy_grade_text(item.get("promedio_final")),
            ]
            cursor_x = x
            for value, col_w in zip(values, col_widths):
                text = value
                while canvas.stringWidth(text, "Times-Roman", 6.6) > col_w - 6 and len(text) > 4:
                    text = text[:-4].rstrip() + "..."
                canvas.drawString(cursor_x + 3, current_y - 8, text)
                canvas.line(cursor_x, current_y, cursor_x, next_y)
                cursor_x += col_w
            canvas.line(x + table_w, current_y, x + table_w, next_y)
            current_y = next_y
        canvas.restoreState()
        y_after = y - table_h - 8
        if len(students) > max_rows:
            canvas.setFont("Times-Italic", 7)
            canvas.setFillColor(dark)
            canvas.drawString(x, y_after, f"Se muestran {max_rows} de {len(students)} estudiante(s) seleccionados.")
            y_after -= 10
        return y_after

    def draw_grade_summary_table(x: float, y: float) -> float:
        headers = ["Nota máxima", "Nota mínima", "Estudiantes reprobados"]
        values = [
            _grade_text(max(grade_values) if grade_values else None),
            _grade_text(min(grade_values) if grade_values else None),
            str(failed),
        ]
        col_w = 118
        row_h = 16
        table_w = col_w * len(headers)
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c7c7c7"))
        canvas.setLineWidth(0.5)
        canvas.setFillColor(colors.HexColor("#f2f2f2"))
        canvas.rect(x, y - row_h, table_w, row_h, stroke=1, fill=1)
        canvas.setFillColor(dark)
        canvas.setFont("Times-Bold", 7.4)
        for index, header in enumerate(headers):
            cell_x = x + (index * col_w)
            canvas.drawCentredString(cell_x + col_w / 2, y - 10.5, header)
            canvas.line(cell_x, y, cell_x, y - row_h * 2)
        canvas.line(x + table_w, y, x + table_w, y - row_h * 2)
        canvas.line(x, y, x + table_w, y)
        canvas.line(x, y - row_h, x + table_w, y - row_h)
        canvas.line(x, y - row_h * 2, x + table_w, y - row_h * 2)
        canvas.setFont("Times-Bold", 8)
        for index, value in enumerate(values):
            cell_x = x + (index * col_w)
            canvas.drawCentredString(cell_x + col_w / 2, y - row_h - 10.5, value)
        canvas.restoreState()
        return y - (row_h * 2) - 10

    teacher_name = _clean(teacher.get("docente"))
    name_parts = teacher_name.split()
    first_names = " ".join(name_parts[2:]) if len(name_parts) > 2 else teacher_name
    last_names = " ".join(name_parts[:2]) if len(name_parts) > 2 else "-"
    course_name = _clean(meta.get("nombre_materia")) or _clean(meta.get("cod_materia"))
    grade_values = [_number(item.get("promedio_final")) for item in students]
    grade_values = [value for value in grade_values if value is not None]
    failed = sum(1 for value in grade_values if value < 7)

    start_page(1)
    y = 662
    y = line("1.   DATOS DEL DOCENTE:", body_x, y, 12, True)
    y = line(f"Nombres del Docente: {first_names}", body_x + 38, y, 11)
    y = line(f"Apellidos del Docente: {last_names}", body_x + 38, y, 11)
    y = line(f"Cédula: {_clean(teacher.get('cedula'))}", body_x + 38, y, 11)
    y = line(f"Correo institucional: {_clean(teacher.get('correo')) or _clean(teacher.get('correo_personal'))}", body_x + 38, y, 11)
    y = line(f"Teléfono de contacto: {_clean(params.get('telefono')) or '-'}", body_x + 38, y, 11)
    y -= 14
    canvas.setFont("Times-Bold", 12)
    canvas.drawString(body_x, y, "2.   DATOS DE LA ASIGNATRURA:")
    canvas.setFont("Times-Roman", 11)
    canvas.drawString(body_x + 205, y, f"Asignatura: {course_name}")
    y -= 16
    y = line(f"Fecha de inicio: {_clean(params.get('fecha_inicio')) or '-'}", body_x + 38, y, 11)
    y = line(f"Fecha fin: {_clean(params.get('fecha_fin')) or '-'}", body_x + 38, y, 11)
    y = line(f"Número de estudiantes matriculados: {len(students)}", body_x + 38, y, 11)
    y = draw_selected_students_table(body_x + 38, y + 4, 426)
    y -= 14
    y = line("3.   REPORTE ACADÉMICO", body_x, y, 12, True)
    y -= 14
    canvas.setFont("Times-Bold", 11)
    canvas.drawString(body_x + 18, y, "3.1.")
    canvas.drawString(body_x + 56, y, "Cumplimiento del PEA Y silabo")
    highlight("(debidamente firmado)", body_x + 228, y, 11)
    y -= 24
    y = wrapped("Evidenciar (captura de pantalla) silabo y PEA cargado en el sistema de Aula virtuales, debidamente firmado electrónicamente.", body_x, y, content_width, 11)
    y = line("Ejemplo:", body_x, y - 4, 11)
    y = draw_group(("pea", "sílabo", "silabo"), body_x + 26, y, 468, 68, 1)
    y -= 4
    canvas.setFont("Times-Bold", 11)
    canvas.drawString(body_x + 18, y, "3.2.")
    canvas.drawString(body_x + 56, y, "Reporte de actualización del silabo")
    highlight("(Describir actualizaciones realizadas al sílabo", body_x + 260, y, 11)
    y -= 14
    highlight("y su justificativo)", body_x + 56, y, 11)
    y -= 28
    y = line(_clean(params.get("actualizaciones")) or "Sin cambios realizados.", body_x, y, 11, True)
    y -= 22
    y = line("3.3.     Reporte del aula virtual.", body_x + 18, y, 11, True)
    y -= 16
    y = wrapped("En el reporte consolidado evidencia en el sistema de aulas virtuales que se cargaron los siguientes recursos en material académico a través de capturas de pantalla:", body_x, y, content_width, 11)
    for item in [
        "Bibliografía del material académico",
        "Presentación PPT cargado como PDF por cada clase.",
        "Link de grabaciones de cada clase o tutoría impartida",
        "Simulador de examen (para los casos que aplique) y su banco de preguntas.",
    ]:
        y = line(f"•    {item}", body_x + 18, y - 1, 11)

    new_page(2)
    y = 702
    for item in ["Evaluación(es) teórica(s)", "Componente(s) práctico(s)", "Evidencia de clases grabadas en TEAMS Ejemplo:"]:
        y = line(f"•    {item}", body_x + 18, y, 11)
    y = draw_group(("aula", "virtual", "recursos"), body_x + 18, y - 6, 494, 150, 3)

    new_page(3)
    y = 718
    y = draw_group(("teams", "clases"), body_x + 18, y, 494, 105, 1)
    y -= 42
    y = line("3.4.     Asistencias", body_x + 18, y, 11, True)
    y = draw_group(("asistencia",), body_x + 58, y - 6, 455, 105, 1)
    y -= 12
    y = line("3.5.     Reporte de Notas", body_x + 18, y, 11, True)
    y -= 14
    y = wrapped("Indicar la nota máxima obtenida y la nota mínima obtenida y si existieron casos de estudiantes reprobados, junto con captura de pantalla del reporte de notas debidamente firmado electrónicamente y de las notas subidas en el sistema académico:", body_x, y, content_width, 11)
    y = line("Ejemplo:", body_x, y - 4, 11)
    y = draw_group(("notas", "reporte"), body_x + 24, y, 470, 205, 1)
    y = draw_grade_summary_table(body_x + 24, y)

    new_page(4)
    y = 662
    y = line("3.6.     Anexos:", body_x + 18, y, 12, True)
    y -= 16
    y = wrapped("El presente informe debe ir acompañado de la siguiente documentación de respaldo:", body_x, y, content_width, 11)
    for item in [
        "Contrato firmado electrónicamente",
        "Reporte de notas firmado electrónicamente",
        "Factura electrónica, emitida de acuerdo al número de contrato y valor",
    ]:
        y = line(f"      -    {item}", body_x + 18, y - 2, 11)
    y -= 34
    y = line("Saludos cordiales,", body_x, y, 11)
    y -= 84
    y = line("Firma electrónica", body_x, y, 11)
    y = line(teacher_name.title(), body_x, y, 11)
    y = line("DOCENTE", body_x, y, 11)
    line(f"Cédula: {_clean(teacher.get('cedula'))}", body_x, y, 11)
    canvas.save()
    output.seek(0)
    return output.getvalue()

def _teacher_compliance_report_pdf_legacy(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
    report_format: dict[str, Any],
    params: dict[str, Any],
    evidence_images: list[dict[str, Any]] | None = None,
) -> bytes:
    light_gray = colors.HexColor("#F4F4F4")
    dark = colors.HexColor("#111111")
    border = colors.HexColor("#BFC7CC")

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ComplianceTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=dark,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ComplianceSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=dark,
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ComplianceBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=dark,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ComplianceJustify",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=dark,
            alignment=TA_JUSTIFY,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ComplianceSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9,
            textColor=dark,
        )
    )

    def p(value: Any, style: str = "ComplianceBody") -> Paragraph:
        return Paragraph(_pdf_text(value), styles[style])

    def bp(value: Any, style: str = "ComplianceBody") -> Paragraph:
        return Paragraph(f"<b>{_pdf_text(value)}</b>", styles[style])

    def section(title: Any, body: Any | None = None, body_style: str = "ComplianceBody") -> None:
        story.append(bp(title, "ComplianceBody"))
        if body:
            story.append(p(body, body_style))
            story.append(Spacer(1, 0.08 * cm))

    def grade_cell(value: Any) -> Paragraph:
        return Paragraph(_pdf_text(value), styles["ComplianceSmall"])

    def add_grades_annex() -> None:
        if not students:
            story.append(p("No existen estudiantes seleccionados para adjuntar calificaciones.", "ComplianceSmall"))
            return
        story.append(Spacer(1, 0.1 * cm))
        story.append(p("Cuadro de notas", "ComplianceBody"))
        story.append(
            p(
                (
                    f"Periodo: {_clean(meta.get('detalle_periodo')) or '-'} | "
                    f"Paralelo: {_clean(meta.get('paralelo')) or '-'} | "
                    f"Jornada: {_clean(meta.get('jornada')) or '-'} | "
                    f"Semestre: {_clean(meta.get('semestre')) or '-'} | "
                    f"Horas: {_grade_text(meta.get('horas'), 0)}"
                ),
                "ComplianceSmall",
            )
        )
        rows: list[list[Any]] = [[
            grade_cell("No."),
            grade_cell("Carrera"),
            grade_cell("Cédula"),
            grade_cell("Apellidos y nombres"),
            grade_cell("P1"),
            grade_cell("P2"),
            grade_cell("P3"),
            grade_cell("Promedio"),
            grade_cell("Recuperación"),
            grade_cell("Final"),
        ]]
        for index, item in enumerate(students, start=1):
            rows.append([
                grade_cell(index),
                grade_cell(item.get("nombre_carrera")),
                grade_cell(item.get("cedula")),
                grade_cell(item.get("nombre_estudiante")),
                grade_cell(_legacy_grade_text(item.get("prom_p1"))),
                grade_cell(_legacy_grade_text(item.get("prom_p2"))),
                grade_cell(_legacy_grade_text(item.get("prom_p3"))),
                grade_cell(_legacy_grade_text(item.get("promedio"))),
                grade_cell(_legacy_grade_text(item.get("recuperacion"))),
                grade_cell(_legacy_grade_text(item.get("promedio_final"))),
            ])
        table = Table(
            rows,
            repeatRows=1,
            colWidths=[0.7 * cm, 2.5 * cm, 2.0 * cm, 4.3 * cm, 1.15 * cm, 1.15 * cm, 1.15 * cm, 1.45 * cm, 1.65 * cm, 1.25 * cm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), light_gray),
                    ("BOX", (0, 0), (-1, -1), 0.45, border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, border),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (4, 1), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

    grade_values = [_number(item.get("promedio_final")) for item in students]
    grade_values = [value for value in grade_values if value is not None]
    failed = sum(1 for value in grade_values if value < 7)
    max_grade = max(grade_values) if grade_values else None
    min_grade = min(grade_values) if grade_values else None

    def evidence_group(*terms: str) -> list[dict[str, Any]]:
        lowered_terms = [term.lower() for term in terms]
        return [
            item
            for item in (evidence_images or [])
            if any(term in _clean(item.get("label")).lower() for term in lowered_terms)
        ]

    def add_evidence(*terms: str, always_example: bool = False) -> None:
        flowables = _image_evidence_flowables(evidence_group(*terms), styles)
        if flowables or always_example:
            story.append(p("Ejemplo:", "ComplianceBody"))
        if flowables:
            story.extend(flowables)

    teacher_name = _clean(teacher.get("docente"))
    name_parts = teacher_name.split()
    first_names = " ".join(name_parts[2:]) if len(name_parts) > 2 else teacher_name
    last_names = " ".join(name_parts[:2]) if len(name_parts) > 2 else "-"
    course_name = _clean(meta.get("nombre_materia")) or _clean(meta.get("cod_materia"))

    story: list[Any] = []
    story.append(bp("DATOS DEL DOCENTE:", "ComplianceBody"))
    story.append(p(f"Nombres del Docente: {first_names}   Apellidos del Docente: {last_names}", "ComplianceBody"))
    story.append(p(f"Cédula: {_clean(teacher.get('cedula'))}", "ComplianceBody"))
    story.append(p(f"Correo institucional: {_clean(teacher.get('correo')) or _clean(teacher.get('correo_personal'))}", "ComplianceBody"))
    story.append(p(f"Teléfono de contacto: {_clean(params.get('telefono')) or '-'}", "ComplianceBody"))
    story.append(Spacer(1, 0.28 * cm))
    story.append(Paragraph(f"<b>DATOS DE LA ASIGNATRURA:</b> Asignatura: {_pdf_text(course_name)}", styles["ComplianceBody"]))
    story.append(p(f"Fecha de inicio: {_clean(params.get('fecha_inicio')) or '-'}", "ComplianceBody"))
    story.append(p(f"Fecha fin: {_clean(params.get('fecha_fin')) or '-'}", "ComplianceBody"))
    story.append(p(f"Número de estudiantes matriculados: {len(students)}", "ComplianceBody"))
    initial_flowables = _image_evidence_flowables(evidence_group("datos", "matriculados", "inicial"), styles)
    if initial_flowables:
        story.append(Spacer(1, 0.12 * cm))
        story.extend(initial_flowables)
    story.append(Spacer(1, 0.35 * cm))
    story.append(bp("REPORTE ACADÉMICO", "ComplianceBody"))
    story.append(Spacer(1, 0.2 * cm))

    story.append(bp("Cumplimiento del PEA Y silabo (debidamente firmado)", "ComplianceBody"))
    story.append(p("Evidenciar (captura de pantalla) silabo y PEA cargado en el sistema de Aula virtuales, debidamente firmado electrónicamente.", "ComplianceBody"))
    add_evidence("pea", "sílabo", "silabo", always_example=True)

    story.append(Spacer(1, 0.16 * cm))
    story.append(bp("Reporte de actualización del silabo (Describir actualizaciones realizadas al sílabo y su justificativo)", "ComplianceBody"))
    story.append(bp(_clean(params.get("actualizaciones")) or "Sin cambios realizados.", "ComplianceBody"))

    story.append(Spacer(1, 0.16 * cm))
    story.append(bp("Reporte del aula virtual.", "ComplianceBody"))
    story.append(p("En el reporte consolidado evidencia en el sistema de aulas virtuales que se cargaron los siguientes recursos en material académico a través de capturas de pantalla:", "ComplianceJustify"))
    add_evidence("aula", "virtual", "recursos")
    for item in report_format.get("resources") or []:
        story.append(p(item, "ComplianceBody"))

    story.append(Spacer(1, 0.16 * cm))
    story.append(p("Evidencia de clases grabadas en TEAMS Ejemplo:", "ComplianceBody"))
    if _clean(params.get("observaciones")):
        story.append(p(_clean(params.get("observaciones")), "ComplianceBody"))
    add_evidence("teams", "clases")

    story.append(Spacer(1, 0.16 * cm))
    story.append(bp("Asistencias", "ComplianceBody"))
    add_evidence("asistencia")
    section(
        "Reporte de Notas",
        (
            "Indicar la nota máxima obtenida y la nota mínima obtenida y si existieron casos de estudiantes reprobados, "
            "junto con captura de pantalla del reporte de notas debidamente firmado electrónicamente y de las notas subidas en el sistema académico:"
        ),
        "ComplianceJustify",
    )
    add_evidence("notas", "reporte", always_example=True)
    story.append(
        p(
            (
                f"Resumen generado: Nota máxima: {_grade_text(max_grade)}. "
                f"Nota mínima: {_grade_text(min_grade)}. Estudiantes reprobados: {failed}."
            ),
            "ComplianceSmall",
        )
    )
    add_grades_annex()
    story.append(Spacer(1, 0.22 * cm))
    story.append(bp("Anexos:", "ComplianceBody"))
    story.append(p("El presente informe debe ir acompañado de la siguiente documentación de respaldo:", "ComplianceBody"))
    for item in report_format.get("annexes") or []:
        story.append(p(item, "ComplianceBody"))
    story.append(Spacer(1, 0.55 * cm))
    story.append(p("Saludos cordiales,", "ComplianceBody"))
    story.append(Spacer(1, 0.9 * cm))
    story.append(p("Firma electrónica", "ComplianceBody"))
    story.append(p(teacher_name, "ComplianceBody"))
    story.append(p("DOCENTE", "ComplianceBody"))
    story.append(p(f"Cédula: {_clean(teacher.get('cedula'))}", "ComplianceBody"))

    output = BytesIO()
    SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=2.1 * cm,
        leftMargin=2.1 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
        title="Informe de cumplimiento docente",
    ).build(story)
    output.seek(0)
    return output.getvalue()


def _docx_clear_body(document: Any) -> None:
    body = document._element.body
    for child in list(body):
        if child.tag.endswith("sectPr"):
            continue
        body.remove(child)


def _docx_paragraph(document: Any, text: str = "", bold: bool = False, justify: bool = False, space_after: int = 0) -> Any:
    paragraph = document.add_paragraph()
    if justify:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.space_after = Pt(space_after)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    return paragraph


def _docx_add_picture(document: Any, image_bytes: bytes, width_cm: float = 16.6) -> None:
    try:
        image = PILImage.open(BytesIO(image_bytes))
        image.verify()
    except Exception:
        return
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(BytesIO(image_bytes), width=Cm(width_cm))


def _teacher_compliance_report_docx(
    teacher: dict[str, Any],
    meta: dict[str, Any],
    students: list[dict[str, Any]],
    report_format: dict[str, Any],
    params: dict[str, Any],
    evidence_images: list[dict[str, Any]] | None = None,
) -> bytes:
    template_path = _TEACHER_COMPLIANCE_WORD_TEMPLATE_PATH
    document = Document(str(template_path)) if template_path.exists() else Document()
    _docx_clear_body(document)

    def evidence_group(*terms: str) -> list[dict[str, Any]]:
        lowered_terms = [term.lower() for term in terms]
        return [
            item
            for item in (evidence_images or [])
            if any(term in _clean(item.get("label")).lower() for term in lowered_terms)
        ]

    def add_evidence(*terms: str, width_cm: float = 16.6, always_example: bool = False) -> None:
        images = evidence_group(*terms)
        if images or always_example:
            _docx_paragraph(document, "Ejemplo:")
        for item in images:
            content = item.get("content")
            if content:
                _docx_add_picture(document, content, width_cm)

    teacher_name = _clean(teacher.get("docente"))
    name_parts = teacher_name.split()
    first_names = " ".join(name_parts[2:]) if len(name_parts) > 2 else teacher_name
    last_names = " ".join(name_parts[:2]) if len(name_parts) > 2 else "-"
    course_name = _clean(meta.get("nombre_materia")) or _clean(meta.get("cod_materia"))

    grade_values = [_number(item.get("promedio_final")) for item in students]
    grade_values = [value for value in grade_values if value is not None]
    failed = sum(1 for value in grade_values if value < 7)
    max_grade = max(grade_values) if grade_values else None
    min_grade = min(grade_values) if grade_values else None

    _docx_paragraph(document, "DATOS DEL DOCENTE:", bold=True)
    _docx_paragraph(document, f"Nombres del Docente: {first_names}")
    _docx_paragraph(document, f"Apellidos del Docente: {last_names}")
    _docx_paragraph(document, f"Cédula: {_clean(teacher.get('cedula'))}")
    _docx_paragraph(document, f"Correo institucional: {_clean(teacher.get('correo')) or _clean(teacher.get('correo_personal'))}")
    _docx_paragraph(document, f"Teléfono de contacto: {_clean(params.get('telefono')) or '-'}")
    _docx_paragraph(document)
    _docx_paragraph(document, f"DATOS DE LA ASIGNATRURA:  Asignatura: {course_name}", bold=True)
    _docx_paragraph(document, f"Fecha de inicio: {_clean(params.get('fecha_inicio')) or '-'}")
    _docx_paragraph(document, f"Fecha fin: {_clean(params.get('fecha_fin')) or '-'}")
    _docx_paragraph(document, f"Número de estudiantes matriculados: {len(students)}")
    for item in evidence_group("datos", "matriculados", "inicial"):
        if item.get("content"):
            _docx_add_picture(document, item["content"], 13.4)

    _docx_paragraph(document)
    _docx_paragraph(document, "REPORTE ACADÉMICO", bold=True)
    _docx_paragraph(document)
    _docx_paragraph(document, "Cumplimiento del PEA Y silabo (debidamente firmado)", bold=True)
    _docx_paragraph(
        document,
        "Evidenciar (captura de pantalla) silabo y PEA cargado en el sistema de Aula virtuales, debidamente firmado electrónicamente.",
    )
    add_evidence("pea", "sílabo", "silabo", width_cm=16.6, always_example=True)

    _docx_paragraph(document)
    _docx_paragraph(document, "Reporte de actualización del silabo (Describir actualizaciones realizadas al sílabo y su justificativo)", bold=True)
    _docx_paragraph(document, _clean(params.get("actualizaciones")) or "Sin cambios realizados.", bold=True)

    _docx_paragraph(document)
    _docx_paragraph(document, "Reporte del aula virtual.", bold=True)
    _docx_paragraph(
        document,
        "En el reporte consolidado evidencia en el sistema de aulas virtuales que se cargaron los siguientes recursos en material académico a través de capturas de pantalla:",
        justify=True,
    )
    for item in report_format.get("resources") or []:
        _docx_paragraph(document, item)
    for item in evidence_group("aula", "virtual", "recursos"):
        if item.get("content"):
            _docx_add_picture(document, item["content"], 16.6)

    _docx_paragraph(document, "Evidencia de clases grabadas en TEAMS Ejemplo:")
    if _clean(params.get("observaciones")):
        _docx_paragraph(document, _clean(params.get("observaciones")))
    for item in evidence_group("teams", "clases"):
        if item.get("content"):
            _docx_add_picture(document, item["content"], 16.6)

    _docx_paragraph(document)
    _docx_paragraph(document, "Asistencias", bold=True)
    for item in evidence_group("asistencia"):
        if item.get("content"):
            _docx_add_picture(document, item["content"], 16.6)

    _docx_paragraph(document)
    _docx_paragraph(document, "Reporte de Notas", bold=True)
    _docx_paragraph(
        document,
        (
            "Indicar la nota máxima obtenida y la nota mínima obtenida y si existieron casos de estudiantes reprobados, "
            "junto con captura de pantalla del reporte de notas debidamente firmado electrónicamente y de las notas subidas en el sistema académico:"
        ),
        justify=True,
    )
    add_evidence("notas", "reporte", width_cm=16.6, always_example=True)
    _docx_paragraph(
        document,
        f"Resumen generado: Nota máxima: {_grade_text(max_grade)}. Nota mínima: {_grade_text(min_grade)}. Estudiantes reprobados: {failed}.",
    )

    if students:
        _docx_paragraph(document, "Cuadro de notas", bold=True)
        table = document.add_table(rows=1, cols=7)
        try:
            table.style = "Table Grid"
        except KeyError:
            pass
        headers = ["No.", "Carrera", "Cédula", "Apellidos y nombres", "P1", "P2", "Final"]
        for index, header in enumerate(headers):
            table.rows[0].cells[index].text = header
        for row_index, item in enumerate(students, start=1):
            cells = table.add_row().cells
            values = [
                str(row_index),
                _clean(item.get("nombre_carrera")),
                _clean(item.get("cedula")),
                _clean(item.get("nombre_estudiante")),
                _legacy_grade_text(item.get("prom_p1")),
                _legacy_grade_text(item.get("prom_p2")),
                _legacy_grade_text(item.get("promedio_final")),
            ]
            for index, value in enumerate(values):
                cells[index].text = value

    _docx_paragraph(document)
    _docx_paragraph(document, "Anexos:", bold=True)
    _docx_paragraph(document, "El presente informe debe ir acompañado de la siguiente documentación de respaldo:")
    for item in report_format.get("annexes") or []:
        _docx_paragraph(document, item)
    _docx_paragraph(document)
    _docx_paragraph(document, "Saludos cordiales,")
    _docx_paragraph(document)
    _docx_paragraph(document)
    _docx_paragraph(document, "Firma electrónica")
    _docx_paragraph(document, teacher_name)
    _docx_paragraph(document, "DOCENTE")
    _docx_paragraph(document, f"Cédula: {_clean(teacher.get('cedula'))}")

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output.getvalue()


def _docx_bytes_to_pdf_bytes(docx_bytes: bytes, filename_stem: str) -> bytes:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="No se puede convertir el informe a PDF porque falta pywin32 en el entorno del backend.",
        ) from exc

    with TemporaryDirectory(prefix="intec_compliance_") as temp_dir:
        temp_path = Path(temp_dir)
        safe_stem = (_safe_filename(filename_stem) or "informe-cumplimiento")[:90]
        docx_path = temp_path / f"{safe_stem}.docx"
        pdf_path = temp_path / f"{safe_stem}.pdf"
        docx_path.write_bytes(docx_bytes)

        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            document = word.Documents.Open(str(docx_path), ReadOnly=True)
            try:
                document.ExportAsFixedFormat(str(pdf_path), 17)
            finally:
                document.Close(False)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="No se pudo convertir el informe Word a PDF. Verifica que Microsoft Word esté instalado y disponible en Windows.",
            ) from exc
        finally:
            if word is not None:
                word.Quit()
            pythoncom.CoUninitialize()

        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise HTTPException(status_code=500, detail="La conversión del informe a PDF no generó un archivo válido.")
        return pdf_path.read_bytes()


@router.get("/admin/teacher-compliance-format")
def get_teacher_compliance_format(
    current_user: Annotated[SessionUser, Depends(_PORTAL_ADMIN_ACCESS)],
) -> dict[str, Any]:
    return _read_teacher_compliance_format()


@router.put("/admin/teacher-compliance-format")
def update_teacher_compliance_format(
    payload: TeacherComplianceReportFormat,
    current_user: Annotated[SessionUser, Depends(_PORTAL_ADMIN_ACCESS)],
) -> dict[str, Any]:
    return _write_teacher_compliance_format(payload)


def _build_teacher_compliance_pdf(
    current_user: SessionUser,
    codigo_periodo: list[int],
    codigo_materia: str,
    paralelo: str,
    codigo_estud: list[int] | None = None,
    cod_anio_basica: int | None = None,
    cod_jornada: int | None = None,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    telefono: str = "",
    actualizaciones: str = "",
    observaciones: str = "",
    evidence_images: list[dict[str, Any]] | None = None,
) -> tuple[bytes, str]:
    codigo_doc = _teacher_code(current_user)
    parallel = paralelo.strip().upper()
    subject_filter = _clean(codigo_materia).upper()
    period_codes = list(dict.fromkeys(codigo_periodo))
    if not period_codes:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un periodo")
    if len(period_codes) > 4:
        raise HTTPException(status_code=400, detail="Solo se pueden seleccionar hasta 4 periodos para el informe")
    if not subject_filter:
        raise HTTPException(status_code=400, detail="Debe seleccionar una materia")

    teacher = teacher_profile(current_user)["teacher"]
    students = _teacher_course_students_for_report(
        current_user=current_user,
        period_codes=period_codes,
        subject_filter=subject_filter,
        parallel=parallel,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
    )
    selected_student_codes = {str(code) for code in (codigo_estud or [])}
    if selected_student_codes:
        students = [item for item in students if _clean(item.get("codigo_estud")) in selected_student_codes]
    meta = _teacher_course_report_meta(codigo_doc, period_codes, subject_filter, parallel, cod_anio_basica)
    if students:
        first = students[0]
        period_names: list[str] = []
        career_names: list[str] = []
        for item in students:
            period = _clean(item.get("detalle_periodo")) or _clean(item.get("codigo_periodo"))
            if period and period not in period_names:
                period_names.append(period)
            career = _clean(item.get("nombre_carrera"))
            if career and career not in career_names:
                career_names.append(career)
        meta = {
            **meta,
            "nombre_carrera": meta.get("nombre_carrera") or (" / ".join(career_names) if len(career_names) <= 2 else f"{len(career_names)} carreras"),
            "detalle_periodo": meta.get("detalle_periodo") or " / ".join(period_names),
            "codigo_materia": meta.get("codigo_materia") or _clean(first.get("codigo_materia")),
            "cod_materia": meta.get("cod_materia") or _clean(first.get("cod_materia")),
            "nombre_materia": meta.get("nombre_materia") or _clean(first.get("nombre_materia")),
            "paralelo": meta.get("paralelo") or _clean(first.get("paralelo")),
            "jornada": meta.get("jornada") or _clean(first.get("jornada")),
            "semestre": meta.get("semestre") or _int(first.get("semestre")),
            "horas": meta.get("horas") or _number(first.get("horas")),
        }
    report_format = _read_teacher_compliance_format()
    filename_stem = (
        f"cumplimiento-docente-{_safe_filename(meta.get('nombre_materia') or subject_filter)}-"
        f"{_safe_filename(meta.get('detalle_periodo') or '-'.join(str(code) for code in period_codes))}"
    )[:110]
    report_params = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "telefono": telefono,
        "actualizaciones": actualizaciones,
        "observaciones": observaciones,
    }
    pdf_bytes = _teacher_compliance_report_pdf(
        teacher,
        meta,
        students,
        report_format,
        report_params,
        evidence_images=evidence_images,
    )
    return pdf_bytes, filename_stem


def _teacher_compliance_response(
    current_user: SessionUser,
    codigo_periodo: list[int],
    codigo_materia: str,
    paralelo: str,
    codigo_estud: list[int] | None = None,
    cod_anio_basica: int | None = None,
    cod_jornada: int | None = None,
    fecha_inicio: str = "",
    fecha_fin: str = "",
    telefono: str = "",
    actualizaciones: str = "",
    observaciones: str = "",
    evidence_images: list[dict[str, Any]] | None = None,
) -> StreamingResponse:
    pdf_bytes, filename_stem = _build_teacher_compliance_pdf(
        current_user=current_user,
        codigo_periodo=codigo_periodo,
        codigo_materia=codigo_materia,
        paralelo=paralelo,
        codigo_estud=codigo_estud,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        telefono=telefono,
        actualizaciones=actualizaciones,
        observaciones=observaciones,
        evidence_images=evidence_images,
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename_stem}.pdf"'},
    )


async def _read_compliance_evidence(
    uploads: list[UploadFile] | None,
    labels: list[str] | None,
) -> list[dict[str, Any]]:
    evidence_images: list[dict[str, Any]] = []
    evidence_labels = labels or []
    for index, upload in enumerate(uploads or []):
        if not upload.filename:
            continue
        content_type = (upload.content_type or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Las evidencias deben ser imágenes")
        content = await upload.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Cada captura debe pesar máximo 5 MB")
        evidence_images.append(
            {
                "label": evidence_labels[index] if index < len(evidence_labels) else upload.filename,
                "content": content,
            }
        )
    return evidence_images


def _certificate_subject_text(certificate: Any) -> str:
    subject = certificate.subject.native
    values: list[str] = []
    for value in subject.values():
        if isinstance(value, (list, tuple)):
            values.extend(_clean(item) for item in value if _clean(item))
        elif _clean(value):
            values.append(_clean(value))
    return " | ".join(values)


def _certificate_signer_name(certificate: Any, current_user: SessionUser) -> str:
    subject = certificate.subject.native
    candidate = subject.get("common_name") or subject.get("name") or current_user.nombres or current_user.login
    if isinstance(candidate, (list, tuple)):
        candidate = " ".join(_clean(value) for value in candidate if _clean(value))
    normalized = unicodedata.normalize("NFKD", _clean(candidate)).encode("ascii", "ignore").decode("ascii")
    return (normalized or "DOCENTE INTEC").upper()[:100]


def _validate_signing_certificate(certificate: Any) -> str:
    validity = certificate["tbs_certificate"]["validity"]
    valid_from = validity["not_before"].native
    valid_until = validity["not_after"].native
    now = datetime.now(timezone.utc)
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    if now < valid_from:
        raise HTTPException(status_code=400, detail="El certificado todavía no se encuentra vigente")
    if now > valid_until:
        raise HTTPException(status_code=400, detail="El certificado de firma electrónica está caducado")

    subject_text = _certificate_subject_text(certificate)
    return subject_text


def _pkcs12_private_key_entries(pkcs12_bytes: bytes, password: bytes) -> list[tuple[Any, str]]:
    """Read every private key bag; cryptography's PKCS#12 loader returns only one."""
    try:
        pfx = asn1_pkcs12.Pfx.load(pkcs12_bytes)
        authenticated_safe = asn1_pkcs12.AuthenticatedSafe.load(pfx["auth_safe"]["content"].native)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="El archivo .p12 no tiene una estructura PKCS#12 válida") from exc

    entries: list[tuple[Any, str]] = []

    def read_bags(safe_contents: Any) -> None:
        for bag in safe_contents:
            bag_type = bag["bag_id"].native
            friendly_name = ""
            for attribute in bag["bag_attributes"] or []:
                if attribute["type"].native == "friendly_name" and len(attribute["values"]):
                    friendly_name = _clean(attribute["values"][0].native)
                    break

            try:
                if bag_type == "pkcs8_shrouded_key_bag":
                    key = serialization.load_der_private_key(bag["bag_value"].untag().dump(), password=password)
                    entries.append((key, friendly_name))
                elif bag_type == "key_bag":
                    key = serialization.load_der_private_key(bag["bag_value"].untag().dump(), password=None)
                    entries.append((key, friendly_name))
                elif bag_type == "safe_contents":
                    read_bags(bag["bag_value"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail="No se pudo abrir el archivo .p12. Verifique el archivo y la contraseña",
                ) from exc

    for content_info in authenticated_safe:
        if content_info["content_type"].native != "data":
            continue
        read_bags(asn1_pkcs12.SafeContents.load(content_info["content"].native))
    return entries


def _public_key_der(value: Any) -> bytes:
    public_key = value.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _certificate_signature_usage(certificate: crypto_x509.Certificate) -> tuple[bool, bool]:
    try:
        usage = certificate.extensions.get_extension_for_class(crypto_x509.KeyUsage).value
    except crypto_x509.ExtensionNotFound:
        return True, False
    may_sign = usage.digital_signature or usage.content_commitment
    return may_sign, usage.digital_signature


def _certificate_chain(
    leaf: crypto_x509.Certificate,
    certificates: list[crypto_x509.Certificate],
) -> list[crypto_x509.Certificate]:
    chain: list[crypto_x509.Certificate] = []
    current = leaf
    remaining = [certificate for certificate in certificates if certificate != leaf]
    while current.issuer != current.subject:
        issuer = next((certificate for certificate in remaining if certificate.subject == current.issuer), None)
        if issuer is None:
            break
        chain.append(issuer)
        remaining.remove(issuer)
        current = issuer
    return chain


def _load_digital_signature_pkcs12(pkcs12_bytes: bytes, password: str) -> signers.SimpleSigner:
    password_bytes = password.encode("utf-8")
    try:
        primary_key, primary_certificate, additional_certificates = crypto_pkcs12.load_key_and_certificates(
            pkcs12_bytes,
            password_bytes,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="No se pudo abrir el archivo .p12. Verifique el archivo y la contraseña",
        ) from exc

    certificates = [
        certificate
        for certificate in [primary_certificate, *(additional_certificates or [])]
        if certificate is not None
    ]
    key_entries = _pkcs12_private_key_entries(pkcs12_bytes, password_bytes)
    if primary_key is not None and all(_public_key_der(key) != _public_key_der(primary_key) for key, _ in key_entries):
        key_entries.append((primary_key, ""))

    candidates: list[tuple[int, Any, crypto_x509.Certificate]] = []
    for key, friendly_name in key_entries:
        key_public = _public_key_der(key)
        certificate = next(
            (candidate for candidate in certificates if _public_key_der(candidate) == key_public),
            None,
        )
        if certificate is None:
            continue
        may_sign, has_digital_signature = _certificate_signature_usage(certificate)
        if not may_sign:
            continue
        normalized_name = friendly_name.casefold()
        score = (100 if has_digital_signature else 60) + (40 if "signing" in normalized_name else 0)
        candidates.append((score, key, certificate))

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail=(
                "El archivo .p12 no contiene una clave habilitada para firma digital. "
                "No se puede firmar con una clave destinada únicamente a cifrado"
            ),
        )

    _, signing_key, signing_certificate = max(candidates, key=lambda candidate: candidate[0])
    chain = _certificate_chain(signing_certificate, certificates)
    normalized_pkcs12 = crypto_pkcs12.serialize_key_and_certificates(
        name=b"FirmaDocente",
        key=signing_key,
        cert=signing_certificate,
        cas=chain,
        encryption_algorithm=serialization.BestAvailableEncryption(password_bytes),
    )
    signer = signers.SimpleSigner.load_pkcs12_data(
        normalized_pkcs12,
        other_certs=[],
        passphrase=password_bytes,
    )
    if signer is None or signer.signing_cert is None:
        raise HTTPException(status_code=400, detail="No se pudo preparar el certificado para firma digital")
    return signer


async def _sign_pdf_with_pkcs12(
    pdf_bytes: bytes,
    pkcs12_bytes: bytes,
    password: str,
    current_user: SessionUser,
    reason: str,
    location: str,
    contact: str,
    signature_box: tuple[float, float, float, float] = (72, 450, 392, 520),
    field_name: str = "FirmaDocente",
    readable_field_name: str = "Firma electrónica del docente",
) -> bytes:
    signer = _load_digital_signature_pkcs12(pkcs12_bytes, password)

    _validate_signing_certificate(signer.signing_cert)
    signer_name = _certificate_signer_name(signer.signing_cert, current_user)
    stamp_reason = _clean(reason) or "Informe de cumplimiento docente"
    stamp_text = (
        "Firmado electronicamente por:\n"
        f"{signer_name}\n"
        "Validar unicamente con FirmaEC"
    )
    writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
    metadata = signers.PdfSignatureMetadata(
        field_name=field_name,
        md_algorithm="sha512",
        location=_clean(location)[:120] or None,
        reason=stamp_reason[:200],
        contact_info=_clean(contact)[:200] or None,
        subfilter=SigSeedSubFilter.ADOBE_PKCS7_DETACHED,
    )
    pdf_signer = signers.PdfSigner(
        metadata,
        signer=signer,
        stamp_style=QRStampStyle(
            border_width=0,
            stamp_text=stamp_text,
            qr_inner_size=58,
        ),
        new_field_spec=SigFieldSpec(
            sig_field_name=field_name,
            on_page=-1,
            box=signature_box,
            readable_field_name=readable_field_name,
        ),
    )
    output = BytesIO()
    try:
        await pdf_signer.async_sign_pdf(
            writer,
            output=output,
            appearance_text_params={"url": "https://www.firmadigital.gob.ec/"},
        )
    except Exception as exc:
        logger.exception("No se pudo firmar el informe de cumplimiento con el certificado PKCS#12")
        technical_detail = _clean(str(exc))[:240]
        detail = f"No se pudo aplicar la firma electrónica al PDF ({type(exc).__name__})"
        if technical_detail:
            detail = f"{detail}: {technical_detail}"
        raise HTTPException(status_code=400, detail=detail) from exc
    return output.getvalue()


def _planning_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    text = escape(_clean(value)).replace("\n", "<br/>") or "-"
    return Paragraph(text, style)


def _teacher_academic_planning_pdf(
    payload: AcademicPlanningPayload,
    teacher: dict[str, Any],
    meta: dict[str, Any],
) -> bytes:
    dark = colors.black
    red = colors.HexColor("#CC0000")
    pale = colors.HexColor("#EEDDDD")
    header_fill = colors.HexColor("#D9DADA")
    border = colors.HexColor("#888888")
    page_size = A4 if payload.document_type == "pea" else landscape(A4)
    page_width, page_height = page_size
    background_path = (
        _ACADEMIC_PLANNING_PEA_BACKGROUND_PATH
        if payload.document_type == "pea"
        else _ACADEMIC_PLANNING_SYLLABUS_BACKGROUND_PATH
    )
    content_width = 17.8 * cm if payload.document_type == "pea" else 26.6 * cm
    narrative_width = 17.8 * cm
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PlanningTitle", parent=styles["Title"], fontSize=20, leading=23, alignment=TA_CENTER, textColor=dark, spaceAfter=4))
    styles.add(ParagraphStyle(name="PlanningHeading", parent=styles["Heading2"], fontSize=10, leading=12, textColor=dark, alignment=TA_CENTER, spaceBefore=9, spaceAfter=5))
    styles.add(ParagraphStyle(name="PlanningBody", parent=styles["BodyText"], fontSize=7.2, leading=9.2, textColor=dark, alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle(name="PlanningCell", parent=styles["BodyText"], fontSize=6.4, leading=7.8, textColor=dark))
    styles.add(ParagraphStyle(name="PlanningCellCenter", parent=styles["PlanningCell"], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="PlanningCellBold", parent=styles["PlanningCell"], fontName="Helvetica-Bold"))

    def p(value: Any, style: str = "PlanningBody") -> Paragraph:
        return _planning_paragraph(value, styles[style])

    def section(title: str, value: Any = None) -> None:
        story.append(p(title, "PlanningHeading"))
        if _clean(value):
            story.append(p(value))
            story.append(Spacer(1, 4))

    def boxed_section(title: str, value: Any) -> None:
        story.append(table([
            [p(title, "PlanningCellBold")],
            [p(value)],
        ], [narrative_width]))
        story.append(Spacer(1, 5))

    def structured_section(title: str, value: Any) -> None:
        raw_lines = [line.strip(" -•\t") for line in _clean(value).splitlines() if line.strip(" -•\t")]
        pairs: list[tuple[str, str]] = []
        for line in raw_lines:
            if ":" in line:
                label, detail = line.split(":", 1)
                pairs.append((label.strip(), detail.strip()))
            else:
                pairs.append(("", line))
        if not pairs:
            pairs = [("", "-")]
        rows: list[list[Any]] = [[p(title, "PlanningCellBold"), ""]]
        rows.extend([
            [p(label, "PlanningCellBold") if label else "", p(detail)]
            for label, detail in pairs
        ])
        result = table(rows, [narrative_width * 0.30, narrative_width * 0.70])
        result.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("ALIGN", (0, 0), (1, 0), "CENTER"),
        ]))
        story.append(result)
        story.append(Spacer(1, 6))

    def table(
        data: list[list[Any]],
        widths: list[float],
        header_rows: int = 0,
        header_background: Any = None,
        h_align: str = "LEFT",
    ) -> Table:
        result = Table(data, colWidths=widths, repeatRows=header_rows, hAlign=h_align)
        commands: list[tuple[Any, ...]] = [
            ("GRID", (0, 0), (-1, -1), 0.45, border),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header_rows:
            commands.extend([
                ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, header_rows - 1), "CENTER"),
            ])
            if header_background is not None:
                commands.append(("BACKGROUND", (0, 0), (-1, header_rows - 1), header_background))
        result.setStyle(TableStyle(commands))
        return result

    total_docencia = sum(topic.horas_docencia for unit in payload.unidades for topic in unit.temas)
    total_practica = sum(topic.horas_practica for unit in payload.unidades for topic in unit.temas)
    total_autonomo = sum(topic.horas_autonomo for unit in payload.unidades for topic in unit.temas)
    document_label = "PEA" if payload.document_type == "pea" else "Silabo"
    subject = _clean(meta.get("nombre_materia") or meta.get("cod_materia") or payload.codigo_materia)
    career = _clean(meta.get("nombre_carrera"))
    period = _clean(meta.get("detalle_periodo") or meta.get("detalle_periodos") or ", ".join(str(code) for code in payload.codigo_periodos))
    teacher_name = _clean(teacher.get("docente")) or "DOCENTE INTEC"
    coordinator_name = "Roberto Castro"
    spanish_months = (
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    )
    change_date = f"{spanish_months[payload.fecha_elaboracion.month - 1]} {payload.fecha_elaboracion.year}"
    semester = _int(meta.get("semestre"))
    level = f"{semester}.º semestre" if semester else (_clean(payload.nivel) or "-")
    curricular_unit = _clean(meta.get("unidad_curricular")) or _clean(payload.unidad_curricular) or "-"

    story: list[Flowable] = [Spacer(1, 2.15 * cm if payload.document_type == "pea" else 0.68 * cm)]
    story.append(p(f"{document_label} DE LA ASIGNATURA", "PlanningTitle"))
    story.append(p(subject.upper(), "PlanningTitle"))
    story.append(Spacer(1, 1.05 * cm))
    control_total = 15.0 * cm
    control_widths = [control_total * 0.42, control_total * 0.14, control_total * 0.24, control_total * 0.20]
    control_table = table([
        [p("CONTROL DE CAMBIOS", "PlanningCellBold"), "", "", ""],
        [p("Descripción", "PlanningCellBold"), p("Versión", "PlanningCellBold"), p("Responsable", "PlanningCellBold"), p("Fecha", "PlanningCellBold")],
        [p(f"Desarrollo de {document_label}", "PlanningCell"), p(payload.version, "PlanningCellCenter"), p(teacher_name.upper(), "PlanningCell"), p(change_date, "PlanningCellCenter")],
        ["", "", "", ""],
        ["", "", "", ""],
    ], control_widths, 2, h_align="CENTER")
    control_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
    ]))
    story.append(control_table)
    story.append(Spacer(1, 8))
    if payload.document_type == "silabo":
        story.append(Indenter(left=1.0 * cm))
    overview_widths = [
        narrative_width * 0.18, narrative_width * 0.15,
        narrative_width * 0.18, narrative_width * 0.15,
        narrative_width * 0.18, narrative_width * 0.16,
    ]
    overview_table = table([
        [p("PROGRAMA DE ESTUDIOS DE ASIGNATURA - PEA", "PlanningCellBold"), "", "", "", "", ""],
        [p("Carrera:", "PlanningCellBold"), p(career), "", "", "", ""],
        [p("Datos Generales:", "PlanningCellBold"), "", "", "", "", ""],
        [p("Código de la asignatura", "PlanningCellBold"), p(meta.get("cod_materia") or payload.codigo_materia), p("Nombre de la asignatura", "PlanningCellBold"), p(subject), "", ""],
        [p("Nivel de la asignatura", "PlanningCellBold"), p(level), p("Unidad de organización curricular", "PlanningCellBold"), p(curricular_unit), p("Campo de formación", "PlanningCellBold"), p(payload.campo_formacion)],
        [p("Distribución de horas en las actividades de aprendizaje", "PlanningCellBold"), "", "", "", "", ""],
        [p("Docencia:", "PlanningCellBold"), p(total_docencia, "PlanningCellCenter"), p("Trabajo Autónomo", "PlanningCellBold"), p(total_autonomo, "PlanningCellCenter"), p("Prácticas Aprendizaje", "PlanningCellBold"), p(total_practica, "PlanningCellCenter")],
        [p("Práctica profesional", "PlanningCellBold"), p(0, "PlanningCellCenter"), p("Vinculación", "PlanningCellBold"), p(0, "PlanningCellCenter"), p("Trabajo de titulación", "PlanningCellBold"), p(0, "PlanningCellCenter")],
        [p("Periodo Académico", "PlanningCellBold"), p(period, "PlanningCellCenter"), "", p("Modalidad", "PlanningCellBold"), p(payload.modalidad, "PlanningCellCenter"), ""],
        [p("Prerrequisitos de la asignatura", "PlanningCellBold"), "", "", p("Co Requisitos de la asignatura", "PlanningCellBold"), "", ""],
        [p(payload.prerrequisitos), "", "", p(payload.correquisitos), "", ""],
        [p("Horario de clases", "PlanningCellBold"), "", "", p("Horario atención de tutorías", "PlanningCellBold"), "", ""],
        [p(payload.horario_clases), "", "", p(payload.horario_tutorias), "", ""],
    ], overview_widths)
    overview_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("SPAN", (0, 0), (-1, 0)),
        ("SPAN", (1, 1), (-1, 1)),
        ("SPAN", (0, 2), (-1, 2)),
        ("SPAN", (3, 3), (-1, 3)),
        ("SPAN", (0, 5), (-1, 5)),
        ("SPAN", (1, 8), (2, 8)),
        ("SPAN", (4, 8), (5, 8)),
        ("SPAN", (0, 9), (2, 9)),
        ("SPAN", (3, 9), (5, 9)),
        ("SPAN", (0, 10), (2, 10)),
        ("SPAN", (3, 10), (5, 10)),
        ("SPAN", (0, 11), (2, 11)),
        ("SPAN", (3, 11), (5, 11)),
        ("SPAN", (0, 12), (2, 12)),
        ("SPAN", (3, 12), (5, 12)),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 5), (-1, 5), "LEFT"),
        ("ALIGN", (0, 9), (-1, 9), "CENTER"),
        ("ALIGN", (0, 11), (-1, 11), "CENTER"),
    ]))
    story.append(overview_table)
    if payload.document_type == "silabo":
        story.append(PageBreak())
    boxed_section("Descripción de la asignatura:", payload.descripcion)
    boxed_section("Objetivo General:", payload.objetivo_general)
    boxed_section("Resultados de Aprendizaje de la asignatura y como aporta al perfil profesional:", payload.resultados_aprendizaje)
    if payload.document_type == "silabo":
        section("ALINEAMIENTO CURRICULAR")
        story.append(PageBreak())
    else:
        section("ALINEAMIENTO CURRICULAR")
    story.append(table([
        [p("Misión INTEC", "PlanningCellBold"), p("Misión Escuela", "PlanningCellBold"), p("Misión Carrera", "PlanningCellBold")],
        [p(payload.mision_intec), p(payload.mision_escuela), p(payload.mision_carrera)],
    ], [narrative_width / 3, narrative_width / 3, narrative_width / 3], 1))
    if payload.document_type == "silabo":
        story.append(Indenter(left=-1.0 * cm))
    section("CONTENIDOS DE LA ASIGNATURA")

    class VerticalPlanningLabel(Flowable):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text
            self.width = 10
            self.height = 45

        def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
            return min(self.width, available_width), min(self.height, available_height)

        def draw(self) -> None:
            self.canv.saveState()
            self.canv.setFont("Helvetica", 5.4)
            self.canv.rotate(90)
            self.canv.drawString(0, -6, self.text)
            self.canv.restoreState()

    silabo_header_added = False
    for unit_index, unit in enumerate(payload.unidades, start=1):
        if payload.document_type == "pea":
            rows = [
                [p(f"UNIDAD {unit_index}: {unit.nombre}", "PlanningCellBold"), "", "", "", "", ""],
                [p("Resultado de Aprendizaje:", "PlanningCellBold"), p(unit.resultado_aprendizaje), "", "", "", ""],
                [p("Contenidos", "PlanningCellBold"), p("Horas de la Unidad", "PlanningCellBold"), "", "", p("Observaciones", "PlanningCellBold"), ""],
                ["", p("Docencia", "PlanningCellBold"), p("Prácticas", "PlanningCellBold"), p("Autónomo", "PlanningCellBold"), p("Trabajo Autónomo del estudiante", "PlanningCellBold"), p("Mecanismo de Evaluación", "PlanningCellBold")],
            ]
            rows.extend([
                [p(topic.tema), p(topic.horas_docencia, "PlanningCellCenter"), p(topic.horas_practica, "PlanningCellCenter"),
                 p(topic.horas_autonomo, "PlanningCellCenter"), p(topic.actividad_autonoma), p(topic.evaluacion)]
                for topic in unit.temas
            ])
            rows.append([
                p("Total", "PlanningCellBold"),
                p(sum(topic.horas_docencia for topic in unit.temas), "PlanningCellCenter"),
                p(sum(topic.horas_practica for topic in unit.temas), "PlanningCellCenter"),
                p(sum(topic.horas_autonomo for topic in unit.temas), "PlanningCellCenter"), "", "",
            ])
            unit_table = table(rows, [content_width * 0.30, content_width * 0.09, content_width * 0.09, content_width * 0.10, content_width * 0.23, content_width * 0.19], 4)
            unit_table.setStyle(TableStyle([
                ("SPAN", (0, 0), (-1, 0)),
                ("SPAN", (1, 1), (-1, 1)),
                ("SPAN", (0, 2), (0, 3)),
                ("SPAN", (1, 2), (3, 2)),
                ("SPAN", (4, 2), (5, 2)),
                ("ALIGN", (0, 0), (-1, 3), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(unit_table)
        else:
            widths = [
                content_width * 0.117, content_width * 0.169, content_width * 0.081,
                content_width * 0.043, content_width * 0.043, content_width * 0.043,
                content_width * 0.157, content_width * 0.131, content_width * 0.102,
                content_width * 0.114,
            ]
            if not silabo_header_added:
                header_rows = [
                    [p("UNIDAD"), p("TEMA"), p("SEMANA"), p("No. Horas"), "", "", p("Componente de docencia"), p("Componente de práctica de aplicación y experimentación de los aprendizajes"), p("Componente de aprendizaje autónomo"), p("Actividad calificada")],
                    ["", "", "", VerticalPlanningLabel("DOCENCIA"), VerticalPlanningLabel("PRÁCTICA"), VerticalPlanningLabel("AUTÓNOMO"), "", "", "", ""],
                ]
                header_table = Table(header_rows, colWidths=widths, rowHeights=[3.2 * cm, 1.5 * cm], hAlign="LEFT")
                header_table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.6, border),
                    ("BACKGROUND", (0, 0), (-1, -1), header_fill),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("SPAN", (0, 0), (0, 1)),
                    ("SPAN", (1, 0), (1, 1)),
                    ("SPAN", (2, 0), (2, 1)),
                    ("SPAN", (3, 0), (5, 0)),
                    ("SPAN", (6, 0), (6, 1)),
                    ("SPAN", (7, 0), (7, 1)),
                    ("SPAN", (8, 0), (8, 1)),
                    ("SPAN", (9, 0), (9, 1)),
                ]))
                story.append(header_table)
                story.append(PageBreak())
                silabo_header_added = True

            rows = [
                [p(f"UNIDAD {unit_index}: {unit.nombre}" if topic_index == 0 else ""), p(topic.tema), p(topic.semana, "PlanningCellCenter"), p(topic.horas_docencia, "PlanningCellCenter"),
                 p(topic.horas_practica, "PlanningCellCenter"), p(topic.horas_autonomo, "PlanningCellCenter"),
                 p(topic.actividad_docencia), p(topic.actividad_practica), p(topic.actividad_autonoma), p(topic.evaluacion)]
                for topic_index, topic in enumerate(unit.temas)
            ]
            if not rows:
                rows = [[
                    p(f"UNIDAD {unit_index}: {unit.nombre}"),
                    p("Pendiente de registrar"),
                    p("-", "PlanningCellCenter"),
                    p("0", "PlanningCellCenter"),
                    p("0", "PlanningCellCenter"),
                    p("0", "PlanningCellCenter"),
                    p("-"),
                    p("-"),
                    p("-"),
                    p("-"),
                ]]
            unit_table = table(
                rows,
                widths,
            )
            evaluation_commands: list[tuple[Any, ...]] = []
            for row_index, topic in enumerate(unit.temas):
                if "EVALU" in f"{topic.tema} {topic.evaluacion}".upper() or "PARCIAL" in f"{topic.tema} {topic.evaluacion}".upper():
                    evaluation_commands.extend([
                        ("BACKGROUND", (0, row_index), (-1, row_index), red),
                        ("TEXTCOLOR", (0, row_index), (-1, row_index), colors.white),
                    ])
            if evaluation_commands:
                unit_table.setStyle(TableStyle(evaluation_commands))
            story.append(unit_table)
        story.append(Spacer(1, 5))

    if payload.document_type == "silabo":
        story.append(Indenter(left=1.0 * cm))
    structured_section("Estrategias Metodológicas", payload.estrategias_metodologicas)
    structured_section("1. Formación ciudadana / Desarrollo de habilidades blandas", payload.formacion_ciudadana)
    structured_section("1.2. Educación ambiental / Desarrollo sostenible", payload.sostenibilidad)
    structured_section("Recursos Didácticos", payload.recursos_didacticos)
    section("EVALUACIÓN")
    if payload.document_type == "silabo":
        story.append(Indenter(left=-1.0 * cm))
        story.append(PageBreak())
    evaluation_rows: list[list[Any]] = [["", p("Actividad", "PlanningCellBold"), p("Peso", "PlanningCellBold")]]
    for partial in range(1, 4):
        evaluation_rows.extend([
            [p(f"PARCIAL {partial}", "PlanningCellBold"), p("Tareas"), p(f"{payload.evaluacion_tareas}%", "PlanningCellCenter")],
            ["", p("Trabajo individual"), p(f"{payload.evaluacion_individual}%", "PlanningCellCenter")],
            ["", p("Trabajo colaborativo"), p(f"{payload.evaluacion_colaborativo}%", "PlanningCellCenter")],
            ["", p("Evaluación acumulativa"), p(f"{payload.evaluacion_acumulativa}%", "PlanningCellCenter")],
        ])
    evaluation_table = table(
        evaluation_rows,
        [4.0 * cm, 5.0 * cm, 2.0 * cm],
        1,
        h_align="CENTER",
    )
    evaluation_style: list[tuple[Any, ...]] = []
    for start in (1, 5, 9):
        evaluation_style.extend([
            ("SPAN", (0, start), (0, start + 3)),
            ("BACKGROUND", (0, start), (0, start + 3), red),
            ("TEXTCOLOR", (0, start), (0, start + 3), colors.white),
            ("ALIGN", (0, start), (0, start + 3), "CENTER"),
            ("VALIGN", (0, start), (0, start + 3), "MIDDLE"),
        ])
    evaluation_table.setStyle(TableStyle(evaluation_style))
    story.append(evaluation_table)
    if payload.document_type == "silabo":
        story.append(PageBreak())
    section("BIBLIOGRAFÍA BÁSICA", payload.bibliografia_basica)
    section("BIBLIOGRAFÍA COMPLEMENTARIA", payload.bibliografia_complementaria)
    section("PROYECTO DE APLICACIÓN PRÁCTICA")
    story.append(table([
        [p("Tema", "PlanningCellBold"), p(payload.proyecto_tema)],
        [p("Tiempo", "PlanningCellBold"), p(payload.proyecto_tiempo)],
        [p("Objetivo", "PlanningCellBold"), p(payload.proyecto_objetivo)],
        [p("Contexto", "PlanningCellBold"), p(payload.proyecto_contexto)],
    ], [narrative_width * 0.18, narrative_width * 0.82], h_align="CENTER"))
    story.append(PageBreak())
    story.append(Spacer(1, 4.1 * cm if payload.document_type == "pea" else 2.2 * cm))
    signature_table = Table([
        [p("Elaborado por", "PlanningCellBold"), p("Revisado por", "PlanningCellBold")],
        ["", ""],
        [p("Cargo: Docente\nNombre: " + teacher_name + "\nFecha: " + payload.fecha_elaboracion.isoformat()),
         p("Cargo: Coordinador Académico\nNombre: " + coordinator_name + "\nFecha: " + payload.fecha_elaboracion.isoformat())],
    ], [5.3 * cm, 5.3 * cm], rowHeights=[0.8 * cm, 3.1 * cm, 1.8 * cm], hAlign="CENTER")
    signature_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, border),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(signature_table)

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=4.3 * cm,
        bottomMargin=1.5 * cm,
        title=f"{document_label} - {subject}",
        author=teacher_name,
    )

    def page_header(canvas: Canvas, doc: Any) -> None:
        canvas.saveState()
        width, height = page_size

        if background_path.exists():
            canvas.drawImage(
                ImageReader(str(background_path)),
                0,
                0,
                width=width,
                height=height,
                preserveAspectRatio=False,
                mask="auto",
            )

        # El fondo procede de los documentos oficiales. Solo se reemplazan las
        # celdas variables de materia y paginacion, conservando sus bordes.
        header_x = 262.0
        subject_split = 447.5
        header_right = 553.6
        header_y = height - 117.6
        bottom_row_height = 33.5
        canvas.setFillColor(colors.white)
        canvas.rect(
            header_x + 0.8,
            header_y + 0.8,
            subject_split - header_x - 1.6,
            bottom_row_height - 1.6,
            fill=1,
            stroke=0,
        )
        canvas.rect(
            subject_split + 0.8,
            header_y + 0.8,
            header_right - subject_split - 1.6,
            bottom_row_height - 1.6,
            fill=1,
            stroke=0,
        )
        canvas.setFillColor(dark)
        canvas.setFont("Helvetica", 9.5)
        canvas.drawCentredString((header_x + subject_split) / 2, header_y + 13.0, subject[:42])
        canvas.drawCentredString((subject_split + header_right) / 2, header_y + 18.0, f"Página {canvas.getPageNumber()} de")
        if payload.document_type == "silabo":
            canvas.setStrokeColor(border)
            canvas.setLineWidth(0.6)
            canvas.line(header_x, header_y, header_right, header_y)
        canvas.restoreState()

    total_x = (447.5 + 553.6) / 2
    total_y = page_height - 114.0

    class PlanningNumberedCanvas(Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict[str, Any]] = []

        def showPage(self) -> None:
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.setFillColor(dark)
                self.setFont("Helvetica-Bold", 9.5)
                self.drawCentredString(total_x, total_y, str(page_count))
                super().showPage()
            super().save()

    document.build(
        story,
        onFirstPage=page_header,
        onLaterPages=page_header,
        canvasmaker=PlanningNumberedCanvas,
    )
    return output.getvalue()


@router.post("/teacher/academic-planning-pdf")
def teacher_academic_planning_pdf(
    payload: AcademicPlanningPayload,
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    preview: Annotated[bool, Query()] = False,
) -> StreamingResponse:
    if not preview and payload.evaluacion_tareas + payload.evaluacion_individual + payload.evaluacion_colaborativo + payload.evaluacion_acumulativa != 100:
        raise HTTPException(status_code=400, detail="Los porcentajes de evaluación deben sumar 100%")
    if not preview and not any(unit.temas for unit in payload.unidades):
        raise HTTPException(status_code=400, detail="Debe registrar al menos un tema en la planificación")
    codigo_doc = _teacher_code(current_user)
    meta = _teacher_course_report_meta(
        codigo_doc,
        payload.codigo_periodos,
        payload.codigo_materia.strip().upper(),
        payload.paralelo.strip().upper(),
        payload.cod_anio_basica,
    )
    if not meta:
        raise HTTPException(status_code=404, detail="La asignatura seleccionada no está vinculada al docente autenticado")
    teacher = teacher_profile(current_user)["teacher"]
    pdf_bytes = _teacher_academic_planning_pdf(payload, teacher, meta)
    document_label = "pea" if payload.document_type == "pea" else "silabo"
    filename = f"{document_label}-{_safe_filename(meta.get('nombre_materia') or payload.codigo_materia)}.pdf"
    disposition = "inline" if preview else "attachment"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.post("/teacher/academic-planning-sign")
async def teacher_sign_academic_planning_pdf(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    payload_json: Annotated[str, Form()],
    certificado: Annotated[UploadFile, File()],
    contrasena_certificado: Annotated[str, Form()],
    firma_motivo: Annotated[str, Form()] = "Planificación académica docente",
    firma_ubicacion: Annotated[str, Form()] = "Quito",
    firma_contacto: Annotated[str, Form()] = "",
) -> StreamingResponse:
    try:
        payload = AcademicPlanningPayload.model_validate_json(payload_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="La información de planificación no es válida") from exc
    if payload.evaluacion_tareas + payload.evaluacion_individual + payload.evaluacion_colaborativo + payload.evaluacion_acumulativa != 100:
        raise HTTPException(status_code=400, detail="Los porcentajes de evaluación deben sumar 100%")
    if not any(unit.temas for unit in payload.unidades):
        raise HTTPException(status_code=400, detail="Debe registrar al menos un tema en la planificación")
    if not certificado.filename or not certificado.filename.lower().endswith((".p12", ".pfx")):
        raise HTTPException(status_code=400, detail="Seleccione un certificado PKCS#12 con extensión .p12 o .pfx")
    certificate_bytes = await certificado.read()
    if not certificate_bytes or len(certificate_bytes) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El certificado está vacío o supera el máximo de 2 MB")
    codigo_doc = _teacher_code(current_user)
    meta = _teacher_course_report_meta(
        codigo_doc,
        payload.codigo_periodos,
        payload.codigo_materia.strip().upper(),
        payload.paralelo.strip().upper(),
        payload.cod_anio_basica,
    )
    if not meta:
        raise HTTPException(status_code=404, detail="La asignatura seleccionada no está vinculada al docente autenticado")
    teacher = teacher_profile(current_user)["teacher"]
    pdf_bytes = _teacher_academic_planning_pdf(payload, teacher, meta)
    signed_pdf = await _sign_pdf_with_pkcs12(
        pdf_bytes=pdf_bytes,
        pkcs12_bytes=certificate_bytes,
        password=contrasena_certificado,
        current_user=current_user,
        reason=firma_motivo,
        location=firma_ubicacion,
        contact=firma_contacto,
        signature_box=(150, 510, 290, 590) if payload.document_type == "pea" else (275, 315, 415, 395),
        field_name=f"FirmaDocente{payload.document_type.upper()}",
        readable_field_name=f"Firma electrónica docente del {payload.document_type.upper()}",
    )
    document_label = "pea" if payload.document_type == "pea" else "silabo"
    filename = f"{document_label}-{_safe_filename(meta.get('nombre_materia') or payload.codigo_materia)}-firmado.pdf"
    return StreamingResponse(
        BytesIO(signed_pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/teacher/course-report-pdf")
def teacher_course_report_pdf(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    cod_anio_basica: Annotated[int | None, Query()] = None,
    cod_jornada: Annotated[int | None, Query()] = None,
) -> StreamingResponse:
    codigo_doc = _teacher_code(current_user)
    parallel = paralelo.strip().upper()
    subject_filter = _clean(codigo_materia).upper()
    period_codes = list(dict.fromkeys(codigo_periodo))
    if not period_codes:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un periodo")
    if not subject_filter:
        raise HTTPException(status_code=400, detail="Debe seleccionar una materia")

    teacher = teacher_profile(current_user)["teacher"]
    students = _teacher_course_students_for_report(
        current_user=current_user,
        period_codes=period_codes,
        subject_filter=subject_filter,
        parallel=parallel,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
    )
    meta = _teacher_course_report_meta(codigo_doc, period_codes, subject_filter, parallel, cod_anio_basica)
    if students:
        first = students[0]
        period_names: list[str] = []
        career_names: list[str] = []
        for item in students:
            period = _clean(item.get("detalle_periodo")) or _clean(item.get("codigo_periodo"))
            if period and period not in period_names:
                period_names.append(period)
            career = _clean(item.get("nombre_carrera"))
            if career and career not in career_names:
                career_names.append(career)
        meta = {
            **meta,
            "nombre_carrera": meta.get("nombre_carrera") or (" / ".join(career_names) if len(career_names) <= 2 else f"{len(career_names)} carreras"),
            "detalle_periodo": meta.get("detalle_periodo") or " / ".join(period_names),
            "codigo_materia": meta.get("codigo_materia") or _clean(first.get("codigo_materia")),
            "cod_materia": meta.get("cod_materia") or _clean(first.get("cod_materia")),
            "nombre_materia": meta.get("nombre_materia") or _clean(first.get("nombre_materia")),
            "paralelo": meta.get("paralelo") or _clean(first.get("paralelo")),
            "jornada": meta.get("jornada") or _clean(first.get("jornada")),
            "semestre": meta.get("semestre") or _int(first.get("semestre")),
            "horas": meta.get("horas") or _number(first.get("horas")),
            "es_homologacion": meta.get("es_homologacion") or any(item.get("es_homologacion") for item in students),
        }
    pdf_bytes = _teacher_notes_report_pdf(teacher, meta, students)
    filename = (
        f"notas-docente-{_safe_filename(meta.get('nombre_materia') or subject_filter)}-"
        f"{_safe_filename(meta.get('detalle_periodo') or '-'.join(str(code) for code in period_codes))}.pdf"
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/teacher/student-grade-report-pdf")
def teacher_student_grade_report_pdf(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    cod_anio_basica: Annotated[int | None, Query()] = None,
    cod_jornada: Annotated[int | None, Query()] = None,
) -> StreamingResponse:
    codigo_doc = _teacher_code(current_user)
    parallel = paralelo.strip().upper()
    subject_filter = _clean(codigo_materia).upper()
    period_codes = list(dict.fromkeys(codigo_periodo))
    if not period_codes:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un periodo")
    if not subject_filter:
        raise HTTPException(status_code=400, detail="Debe seleccionar una materia")

    teacher = teacher_profile(current_user)["teacher"]
    students = _teacher_course_students_for_report(
        current_user=current_user,
        period_codes=period_codes,
        subject_filter=subject_filter,
        parallel=parallel,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
    )
    meta = _teacher_course_report_meta(codigo_doc, period_codes, subject_filter, parallel, cod_anio_basica)
    if students:
        first = students[0]
        meta = {
            **meta,
            "nombre_carrera": meta.get("nombre_carrera") or _clean(first.get("nombre_carrera")),
            "detalle_periodo": meta.get("detalle_periodo") or _clean(first.get("detalle_periodo")),
            "codigo_materia": meta.get("codigo_materia") or _clean(first.get("codigo_materia")),
            "cod_materia": meta.get("cod_materia") or _clean(first.get("cod_materia")),
            "nombre_materia": meta.get("nombre_materia") or _clean(first.get("nombre_materia")),
            "paralelo": meta.get("paralelo") or _clean(first.get("paralelo")),
        }
    pdf_bytes = _student_grade_report_pdf(teacher, meta, students)
    filename = (
        f"reporte-notas-secretaria-{_safe_filename(meta.get('nombre_materia') or subject_filter)}-"
        f"{_safe_filename(meta.get('detalle_periodo') or '-'.join(str(code) for code in period_codes))}.pdf"
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/teacher/compliance-report-docx")
@router.get("/teacher/compliance-report-pdf")
def teacher_compliance_report_pdf(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    codigo_estud: Annotated[list[int] | None, Query()] = None,
    cod_anio_basica: Annotated[int | None, Query()] = None,
    cod_jornada: Annotated[int | None, Query()] = None,
    fecha_inicio: Annotated[str, Query(max_length=40)] = "",
    fecha_fin: Annotated[str, Query(max_length=40)] = "",
    telefono: Annotated[str, Query(max_length=40)] = "",
    actualizaciones: Annotated[str, Query(max_length=1000)] = "",
    observaciones: Annotated[str, Query(max_length=1000)] = "",
) -> StreamingResponse:
    return _teacher_compliance_response(
        current_user=current_user,
        codigo_periodo=codigo_periodo,
        codigo_materia=codigo_materia,
        paralelo=paralelo,
        codigo_estud=codigo_estud,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        telefono=telefono,
        actualizaciones=actualizaciones,
        observaciones=observaciones,
    )


@router.post("/teacher/compliance-report-docx")
@router.post("/teacher/compliance-report-pdf")
async def teacher_compliance_report_pdf_with_evidence(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Form()],
    codigo_materia: Annotated[str, Form()],
    paralelo: Annotated[str, Form(min_length=1)],
    codigo_estud: Annotated[list[int] | None, Form()] = None,
    cod_anio_basica: Annotated[int | None, Form()] = None,
    cod_jornada: Annotated[int | None, Form()] = None,
    fecha_inicio: Annotated[str, Form(max_length=40)] = "",
    fecha_fin: Annotated[str, Form(max_length=40)] = "",
    telefono: Annotated[str, Form(max_length=40)] = "",
    actualizaciones: Annotated[str, Form(max_length=1000)] = "",
    observaciones: Annotated[str, Form(max_length=1000)] = "",
    evidencia_label: Annotated[list[str] | None, Form()] = None,
    evidencia: Annotated[list[UploadFile] | None, File()] = None,
) -> StreamingResponse:
    evidence_images = await _read_compliance_evidence(evidencia, evidencia_label)
    return _teacher_compliance_response(
        current_user=current_user,
        codigo_periodo=codigo_periodo,
        codigo_materia=codigo_materia,
        paralelo=paralelo,
        codigo_estud=codigo_estud,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        telefono=telefono,
        actualizaciones=actualizaciones,
        observaciones=observaciones,
        evidence_images=evidence_images,
    )


@router.post("/teacher/compliance-report-sign")
async def teacher_sign_compliance_report(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Form()],
    codigo_materia: Annotated[str, Form()],
    paralelo: Annotated[str, Form(min_length=1)],
    certificado: Annotated[UploadFile, File()],
    contrasena_certificado: Annotated[str, Form(min_length=1, max_length=256)],
    firma_motivo: Annotated[str, Form(max_length=200)] = "Informe de cumplimiento docente",
    firma_ubicacion: Annotated[str, Form(max_length=120)] = "Quito, Ecuador",
    firma_contacto: Annotated[str, Form(max_length=200)] = "",
    codigo_estud: Annotated[list[int] | None, Form()] = None,
    cod_anio_basica: Annotated[int | None, Form()] = None,
    cod_jornada: Annotated[int | None, Form()] = None,
    fecha_inicio: Annotated[str, Form(max_length=40)] = "",
    fecha_fin: Annotated[str, Form(max_length=40)] = "",
    telefono: Annotated[str, Form(max_length=40)] = "",
    actualizaciones: Annotated[str, Form(max_length=1000)] = "",
    observaciones: Annotated[str, Form(max_length=1000)] = "",
    evidencia_label: Annotated[list[str] | None, Form()] = None,
    evidencia: Annotated[list[UploadFile] | None, File()] = None,
) -> StreamingResponse:
    certificate_name = _clean(certificado.filename).lower()
    if not certificate_name.endswith((".p12", ".pfx")):
        raise HTTPException(status_code=400, detail="Seleccione un certificado con extensión .p12 o .pfx")
    certificate_bytes = await certificado.read()
    if not certificate_bytes:
        raise HTTPException(status_code=400, detail="El archivo de certificado está vacío")
    if len(certificate_bytes) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo .p12 debe pesar máximo 2 MB")

    evidence_images = await _read_compliance_evidence(evidencia, evidencia_label)
    pdf_bytes, filename_stem = _build_teacher_compliance_pdf(
        current_user=current_user,
        codigo_periodo=codigo_periodo,
        codigo_materia=codigo_materia,
        paralelo=paralelo,
        codigo_estud=codigo_estud,
        cod_anio_basica=cod_anio_basica,
        cod_jornada=cod_jornada,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        telefono=telefono,
        actualizaciones=actualizaciones,
        observaciones=observaciones,
        evidence_images=evidence_images,
    )
    signed_pdf = await _sign_pdf_with_pkcs12(
        pdf_bytes=pdf_bytes,
        pkcs12_bytes=certificate_bytes,
        password=contrasena_certificado,
        current_user=current_user,
        reason=firma_motivo,
        location=firma_ubicacion,
        contact=firma_contacto,
    )
    return StreamingResponse(
        BytesIO(signed_pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_stem}-firmado.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.put("/teacher/grades")
def teacher_save_grades(
    payload: TeacherGradePayload,
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
) -> dict[str, Any]:
    codigo_doc = _teacher_code(current_user)
    parallel = payload.paralelo.strip().upper()
    values = payload.model_dump()
    final_grade: float | None = None
    if values.get("teoria_homo") is not None or values.get("practica_homo") is not None:
        final_grade = _weighted_homologation_final(values.get("teoria_homo"), values.get("practica_homo"))
    else:
        prom_p1 = _weighted_regular_partial(values.get("p1_tareas"), values.get("p1_proyectos"), values.get("p1_examen"))
        prom_p2 = _weighted_regular_partial(values.get("p2_tareas"), values.get("p2_proyectos"), values.get("p2_examen"))
        prom_p3 = _weighted_regular_partial(values.get("p3_tareas"), values.get("p3_proyectos"), values.get("p3_examen"))
        if prom_p1 is not None:
            values["prom_p1"] = prom_p1
        if prom_p2 is not None:
            values["prom_p2"] = prom_p2
        if prom_p3 is not None:
            values["prom_p3"] = prom_p3
        if prom_p1 is not None and prom_p2 is not None and prom_p3 is not None:
            final_grade = round((prom_p1 + prom_p2 + prom_p3) / 3, 2)

    if final_grade is not None:
        values["promedio"] = final_grade
        values["promedio_final"] = final_grade
        values["caprueba"] = "A" if final_grade >= 7 else "R"

    assignments: list[str] = []
    params: list[Any] = []
    for payload_key, column in _GRADE_COLUMN_MAP.items():
        value = values.get(payload_key)
        if value is not None:
            assignments.append(f"{column} = ?")
            params.append(value)
    if not assignments:
        raise HTTPException(status_code=400, detail="No hay notas para actualizar")

    assignments.append("Usuario = ?")
    params.append(str(codigo_doc)[:10])

    where_parts = [
        "TRY_CONVERT(int, codigo_estud) = ?",
        "TRY_CONVERT(int, cod_anio_Basica) = ?",
        "TRY_CONVERT(int, codigo_materia) = ?",
        "TRY_CONVERT(int, codigo_periodo) = ?",
        "UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), paralelo)))) = ?",
    ]
    where_params: list[Any] = [
        payload.codigo_estud,
        payload.cod_anio_basica,
        payload.codigo_materia,
        payload.codigo_periodo,
        parallel,
    ]
    if payload.num_matricula is not None:
        where_parts.append("TRY_CONVERT(int, Num_Matricula) = ?")
        where_params.append(payload.num_matricula)
    if payload.num_grupo is not None:
        where_parts.append("TRY_CONVERT(int, NumGrupo) = ?")
        where_params.append(payload.num_grupo)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dbo.CARRERAXDOCENTE cxd
                LEFT JOIN dbo.PENSUM assigned_pensum
                  ON TRY_CONVERT(int, assigned_pensum.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                 AND TRY_CONVERT(int, assigned_pensum.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                LEFT JOIN dbo.PENSUM target_pensum
                  ON TRY_CONVERT(int, target_pensum.Cod_AnioBasica) = ?
                 AND TRY_CONVERT(int, target_pensum.codigo_materia) = ?
                WHERE TRY_CONVERT(int, cxd.codigo_doc) = ?
                  AND TRY_CONVERT(int, cxd.codigo_periodo) = ?
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo)))) = ?
                  AND UPPER(LTRIM(RTRIM(COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(100), assigned_pensum.cod_materia), N''),
                        TRY_CONVERT(nvarchar(100), assigned_pensum.codigo_materia),
                        TRY_CONVERT(nvarchar(100), cxd.codigo_materia),
                        N''
                  )))) = UPPER(LTRIM(RTRIM(COALESCE(
                        NULLIF(TRY_CONVERT(nvarchar(100), target_pensum.cod_materia), N''),
                        TRY_CONVERT(nvarchar(100), target_pensum.codigo_materia),
                        TRY_CONVERT(nvarchar(100), ?),
                        N''
                  ))))
                """,
                payload.cod_anio_basica,
                payload.codigo_materia,
                codigo_doc,
                payload.codigo_periodo,
                parallel,
                payload.codigo_materia,
            )
            if int(cursor.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=403, detail="El curso no esta asignado al docente actual")

            cursor.execute(
                f"""
                UPDATE dbo.CARRERAXESTUD
                SET {', '.join(assignments)}
                WHERE {' AND '.join(where_parts)}
                """,
                *params,
                *where_params,
            )
            affected = cursor.rowcount if cursor.rowcount is not None else 0
            conn.commit()
        return {"ok": True, "message": "Notas actualizadas", "affected_rows": affected}
    except HTTPException:
        raise
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error guardando notas: {exc}") from exc
