"""Renderiza únicamente el informe local a PDF; no accede al sistema académico."""
from pathlib import Path
import hashlib
import json
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
for name, filename in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / filename)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle('BodyAudit', fontName='Arial', fontSize=9.3, leading=13.2, spaceAfter=7, splitLongWords=True))
styles.add(ParagraphStyle('TitleAudit', fontName='Arial-Bold', fontSize=22, leading=27, textColor=colors.HexColor('#12354A'), spaceAfter=17))
styles.add(ParagraphStyle('H2Audit', fontName='Arial-Bold', fontSize=14, leading=18, spaceBefore=15, spaceAfter=8, keepWithNext=True, textColor=colors.HexColor('#12354A')))
styles.add(ParagraphStyle('H3Audit', fontName='Arial-Bold', fontSize=11, leading=15, spaceBefore=12, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor('#147D88')))
styles.add(ParagraphStyle('CellAudit', fontName='Arial', fontSize=8, leading=10.5, splitLongWords=True))
styles.add(ParagraphStyle('BulletAudit', parent=styles['BodyAudit'], leftIndent=11, firstLineIndent=-8))

def inline(text):
    text = escape(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<link href="\2" color="#126A91">\1</link>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font color="#315269">\1</font>', text)
    return text

story = []
lines = (ROOT / 'INFORME_VULNERABILIDADES.md').read_text(encoding='utf-8').splitlines()
i = 0
width = A4[0] - 36 * mm
while i < len(lines):
    line = lines[i].strip()
    if not line:
        i += 1
        continue
    if line.startswith('|'):
        rows = []
        while i < len(lines) and lines[i].strip().startswith('|'):
            cells = [v.strip() for v in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[:\-\s]+', v) for v in cells):
                rows.append([Paragraph(inline(v), styles['CellAudit']) for v in cells])
            i += 1
        weights = [0.10, 0.16, 0.74] if rows and rows[0][0].text == 'ID' else [0.28, 0.34, 0.38]
        if len(rows[0]) == 2:
            weights = [0.28, 0.72]
        table = Table(rows, colWidths=[width * w for w in weights], repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DFECF1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FA')]),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#C6D5DF')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.extend([table, Spacer(1, 9)])
        continue
    if line.startswith('### '):
        story.append(Paragraph(inline(line[4:]), styles['H3Audit']))
    elif line.startswith('## '):
        story.append(Paragraph(inline(line[3:]), styles['H2Audit']))
    elif line.startswith('# '):
        story.append(Paragraph(inline(line[2:]), styles['TitleAudit']))
    elif line.startswith('- '):
        story.append(Paragraph('• ' + inline(line[2:]), styles['BulletAudit']))
    else:
        story.append(Paragraph(inline(line), styles['BodyAudit']))
    i += 1

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#C6D5DF'))
    canvas.line(18 * mm, 17 * mm, A4[0] - 18 * mm, 17 * mm)
    canvas.setFont('Arial', 7.5)
    canvas.setFillColor(colors.HexColor('#526A78'))
    canvas.drawString(18 * mm, 12 * mm, 'INTEC | Seguridad | Uso interno | 21-09-2026')
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f'Página {doc.page}')
    canvas.restoreState()

dest = ROOT / 'INFORME_VULNERABILIDADES.pdf'
doc = SimpleDocTemplate(str(dest), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=23*mm,
                        title='Informe de vulnerabilidades - Sistema académico INTEC - 2026-09-21', author='Revisión técnica del proyecto INTEC')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(dest)

repo = ROOT.parents[2]
reviewed = [
    'backend/app/main.py', 'backend/app/core/config.py', 'backend/app/core/security.py',
    'backend/app/core/session_revocation.py', 'backend/app/core/rate_limit.py',
    'backend/app/core/file_security.py', 'backend/app/services/db.py',
    'backend/app/services/auth.py', 'backend/app/routers/sisacademico_admin.py',
    'backend/app/routers/credential_generator.py', 'backend/app/routers/teacher_evaluation.py',
    'backend/app/routers/direct_admission.py', 'backend/app/services/direct_admission_credentials.py',
    'backend/app/routers/document_expedients.py', 'backend/app/services/graph_documents.py',
    'backend/app/routers/english_exams.py', 'backend/app/routers/preinscription.py',
    'backend/app/routers/carnet.py', 'backend/app/routers/titulos_registrados.py',
    'backend/app/routers/institutional_email.py', 'backend/app/integrations/moodle/client.py',
    'backend/app/services/screen_access.py', 'backend/requirements.txt',
    'backend/sql/2026_09_20_auditoria_ddl_tolerante.sql', 'backend/web.config',
    'frontend/public/web.config', 'frontend/package-lock.json',
    'frontend-angular/package-lock.json',
]
inputs = {}
for relative in reviewed:
    source = repo / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    inputs[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
artifacts = {}
for artifact in sorted(ROOT.rglob('*')):
    if artifact.is_file() and artifact.name != 'manifiesto_sha256.json' and '__pycache__' not in artifact.parts:
        artifacts[str(artifact.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(artifact.read_bytes()).hexdigest()
manifest = {
    'fecha': '2026-09-21', 'algoritmo': 'SHA-256',
    'nota': 'Huellas para comprobar integridad y versión, no firma digital ni lista exhaustiva de archivos del proyecto. No incluye archivos .env ni secretos.',
    'fuentes_revisadas': inputs, 'entregables_y_evidencias': artifacts,
}
(ROOT / 'evidencias' / 'manifiesto_sha256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Manifiesto SHA-256 generado')
