from datetime import date, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Annotated, Any
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from PIL import Image as PILImage
from pydantic import BaseModel, Field
import pyodbc
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, Image as PdfImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/portal", tags=["portal-academico"])

_STUDENT_ACCESS = require_roles("ESTUDIANTE")
_TEACHER_ACCESS = require_roles("DOCENTE")
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_REPORT_TEMPLATE_PATH = _PROJECT_ROOT / "frontend" / "doc" / "Plantilla word (1) - copia (1).docx"
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"


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
        bucket["total_estudiantes"] += _int(item.get("total_estudiantes")) or 0

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
                    WHERE TRY_CONVERT(int, cxe.cod_anio_Basica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                      AND TRY_CONVERT(int, cxe.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                      AND TRY_CONVERT(int, cxe.codigo_periodo) = TRY_CONVERT(int, cxd.codigo_periodo)
                      AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxe.paralelo)))) =
                          UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxd.Paralelo))))
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


@router.get("/teacher/course-students")
def teacher_course_students(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    cod_anio_basica: Annotated[int | None, Query()] = None,
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
                        cxd.cod_Anio_Basica,
                        cxd.codigo_materia,
                        cxd.codigo_periodo,
                        cxd.Paralelo,
                        cxd.Cod_Jornada
                    FROM dbo.CARRERAXDOCENTE cxd
                    LEFT JOIN dbo.PENSUM pta
                      ON TRY_CONVERT(int, pta.Cod_AnioBasica) = TRY_CONVERT(int, cxd.cod_Anio_Basica)
                     AND TRY_CONVERT(int, pta.codigo_materia) = TRY_CONVERT(int, cxd.codigo_materia)
                    WHERE TRY_CONVERT(int, cxd.codigo_doc) = ?
                      AND (? IS NULL OR TRY_CONVERT(int, cxd.cod_Anio_Basica) = ?)
                      AND (
                            TRY_CONVERT(nvarchar(100), cxd.codigo_materia) = ?
                            OR UPPER(LTRIM(RTRIM(COALESCE(TRY_CONVERT(nvarchar(100), pta.cod_materia), N'')))) = ?
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
                INNER JOIN teacher_assignment ta
                  ON TRY_CONVERT(int, ta.cod_Anio_Basica) = TRY_CONVERT(int, cxe.cod_anio_Basica)
                 AND TRY_CONVERT(int, ta.codigo_materia) = TRY_CONVERT(int, cxe.codigo_materia)
                 AND TRY_CONVERT(int, ta.codigo_periodo) = TRY_CONVERT(int, cxe.codigo_periodo)
                 AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), ta.Paralelo)))) =
                     UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), cxe.paralelo))))
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
                ORDER BY
                    TRY_CONVERT(int, cxe.codigo_periodo) DESC,
                    TRY_CONVERT(nvarchar(4000), de.Apellidos_nombre)
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


@router.get("/teacher/course-report-pdf")
def teacher_course_report_pdf(
    current_user: Annotated[SessionUser, Depends(_TEACHER_ACCESS)],
    codigo_periodo: Annotated[list[int], Query()],
    codigo_materia: Annotated[str, Query()],
    paralelo: Annotated[str, Query(min_length=1)],
    cod_anio_basica: Annotated[int | None, Query()] = None,
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
    payload = teacher_course_students(
        current_user=current_user,
        codigo_periodo=period_codes,
        codigo_materia=subject_filter,
        paralelo=parallel,
        cod_anio_basica=cod_anio_basica,
    )
    students = payload.get("items") or []
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
                FROM dbo.CARRERAXDOCENTE
                WHERE TRY_CONVERT(int, codigo_doc) = ?
                  AND TRY_CONVERT(int, cod_Anio_Basica) = ?
                  AND TRY_CONVERT(int, codigo_materia) = ?
                  AND TRY_CONVERT(int, codigo_periodo) = ?
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), Paralelo)))) = ?
                """,
                codigo_doc,
                payload.cod_anio_basica,
                payload.codigo_materia,
                payload.codigo_periodo,
                parallel,
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
