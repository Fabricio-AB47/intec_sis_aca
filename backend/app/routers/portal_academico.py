from datetime import date, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Annotated, Any
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
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Image as PdfImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/portal", tags=["portal-academico"])

_STUDENT_ACCESS = require_roles("ESTUDIANTE")
_TEACHER_ACCESS = require_roles("DOCENTE")
_PORTAL_ADMIN_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR")
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_REPORT_TEMPLATE_PATH = _PROJECT_ROOT / "frontend" / "doc" / "Plantilla word (1) - copia (1).docx"
_TEACHER_COMPLIANCE_WORD_TEMPLATE_PATH = Path.home() / "Documents" / "FABRICIO BORJA" / "FABRICIO BORJA CUMPLIMIENTO GRSI.docx"
_TEACHER_COMPLIANCE_BACKGROUND_PATH = _BACKEND_ROOT.parent / "backend" / ".codex_template_image1.png"
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"
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
        summary = _record_summary(items)
        visible_items = [item for item in items if item["aprobada"]] if approved_only else items
        return {
            "student": profile,
            "summary": summary,
            "curriculum_summary": curriculum_resume,
            "curriculum": curriculum,
            "academic_grid": academic_grid,
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
    filename = f"{filename_stem}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    evidence_images: list[dict[str, Any]] = []
    labels = evidencia_label or []
    for index, upload in enumerate(evidencia or []):
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
                "label": labels[index] if index < len(labels) else upload.filename,
                "content": content,
            }
        )
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
