"""Confidential admission receipts, one student per page, built only in memory."""

from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg


_LOGO = Path(__file__).resolve().parents[3] / "frontend/public/Intec-Logowithslogangray.svg"
_RED = colors.HexColor("#A91F1B")
_TEAL = colors.HexColor("#147D87")
_GRAY = colors.HexColor("#536270")
_CONFIRMED = {"CREADO_GRAPH", "EXISTENTE_GRAPH", "CREADO_MOODLE", "EXISTENTE_MOODLE"}


class _Check(Flowable):
    def __init__(self, checked):
        super().__init__()
        self.width = self.height = 12
        self.checked = checked

    def draw(self):
        self.canv.setStrokeColor(_TEAL if self.checked else _GRAY)
        self.canv.setLineWidth(1)
        self.canv.rect(0, 0, 10, 10)
        if self.checked:
            self.canv.setLineWidth(1.5)
            self.canv.line(2, 5, 4, 2)
            self.canv.line(4, 2, 8, 8)


@lru_cache(maxsize=1)
def _logo():
    return svg2rlg(str(_LOGO)) if _LOGO.is_file() else None


def platform_status(status):
    if status in {"CREADO_GRAPH", "CREADO_MOODLE"}:
        return "Creado"
    if status in {"EXISTENTE_GRAPH", "EXISTENTE_MOODLE"}:
        return "Existente verificado"
    if status and ("ERROR" in status or "CONFLICTO" in status):
        return "Con novedades; no confirmado"
    return "Pendiente de verificaci\u00f3n"


def build_receipt_pdf(items: list[dict], operator: str) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
        topMargin=94, bottomMargin=48, title="Comprobante de matr\u00edcula y accesos", author="INTEC")
    body = ParagraphStyle("ReceiptBody", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#162E43"), splitLongWords=True)
    small = ParagraphStyle("ReceiptSmall", parent=body, fontSize=8.5, leading=12, textColor=_GRAY)
    heading = ParagraphStyle("ReceiptHeading", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=12)
    section = ParagraphStyle("ReceiptSection", parent=body, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=7)
    generated = datetime.now(ZoneInfo("America/Guayaquil")).strftime("%d/%m/%Y %H:%M")

    def text(value, style=body):
        return Paragraph(escape(str(value or "No registrado")), style)

    def table(rows, widths):
        result = Table(rows, colWidths=widths, hAlign="LEFT")
        result.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#CBD7DF"))]))
        return result

    def page_header(canvas, doc):
        canvas.saveState()
        drawing = _logo()
        if drawing and drawing.width and drawing.height:
            scale = min(168 / drawing.width, 42 / drawing.height)
            canvas.saveState()
            canvas.translate(42, A4[1] - 70)
            canvas.scale(scale, scale)
            renderPDF.draw(drawing, canvas, 0, 0)
            canvas.restoreState()
        else:
            canvas.setFont("Helvetica-Bold", 18)
            canvas.setFillColor(_RED)
            canvas.drawString(42, A4[1] - 45, "INTEC")
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(_GRAY)
        canvas.drawRightString(A4[0] - 42, A4[1] - 40, "MATR\u00cdCULA Y ACCESOS")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 42, A4[1] - 55, generated + " \u00b7 Ecuador")
        canvas.setStrokeColor(_RED)
        canvas.line(42, A4[1] - 81, A4[0] - 42, A4[1] - 81)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 28, "Confidencial. Contiene credenciales personales; debe custodiarse.")
        canvas.drawRightString(A4[0] - 42, 28, f"{doc.page} / {len(items)}")
        canvas.restoreState()

    story = []
    for number, item in enumerate(items):
        if number:
            story.append(PageBreak())
        content = [text("Comprobante de matr\u00edcula y accesos", heading), text(item["name"], section)]
        content.append(table([[text(label, small), text(value)] for label, value in [
            ("Identificaci\u00f3n", item["identity"]), ("C\u00f3digo de estudiante", item["code"]),
            ("Carrera", item.get("career")), ("Per\u00edodo", item.get("period")),
            ("Nivel", item.get("level")), ("Solicitud", item["request_id"]),
        ]], [126, document.width - 126]))
        content.append(text("Credenciales institucionales", section))
        content.append(table([[text("Correo institucional", small), text(item.get("email"))],
            *[[text(f"Contrase\u00f1a emitida \u00b7 {label}", small), text(item["passwords"].get(key) or
                "No disponible en el registro cifrado. No se modific\u00f3 una contrase\u00f1a existente.", body)]
                for key, label in [("office", "Office 365"), ("moodle", "Moodle")]]], [168, document.width - 168]))
        content.append(text("Verificaci\u00f3n de plataformas", section))
        statuses = table([[text("Visto", small), text("Plataforma", small), text("Estado", small)],
            *[[_Check(item.get(key) in _CONFIRMED), text(label), text(platform_status(item.get(key)))]
                for key, label in [("estado_graph", "Office 365"), ("estado_moodle", "Moodle")]],
            [_Check(item.get("email_synchronized")), text("Correo en INTECBDD"),
                text("Sincronizado en DATOS_ESTUD y CorreosEstudIntec" if item.get("email_synchronized") else "Sincronizaci\u00f3n pendiente")]],
            [42, 160, document.width - 202])
        statuses.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF5F7"))]))
        content.append(statuses)
        content.append(Spacer(1, 10))
        license_ok = item.get("estado_licencia") in {"ASIGNADA_ESTUDIANTE", "YA_ASIGNADA_ESTUDIANTE"}
        content.append(text("Licencia educativa: " + ("asignada / verificada" if license_ok else "pendiente o con novedades"), small))
        content.append(text("Los vistos confirman la creaci\u00f3n o existencia verificada de las cuentas; no implican matr\u00edcula en cursos Moodle.", small))
        content.append(text("Se muestran contrase\u00f1as emitidas y conservadas cifradas por el sistema. Su vigencia posterior no se comprueba y las contrase\u00f1as existentes no se restablecen.", small))
        if item.get("password_dates"):
            content.append(text("Emisi\u00f3n registrada: " + " \u00b7 ".join(item["password_dates"]), small))
        if item.get("errors"):
            content.append(text("Novedades: " + "; ".join(item["errors"])[:420], small))
        content.append(text("Documento generado por: " + operator, small))
        story.append(KeepInFrame(document.width, A4[1] - 148, content, mode="shrink", hAlign="LEFT", vAlign="TOP"))
    document.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return output.getvalue()
