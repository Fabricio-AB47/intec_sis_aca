from __future__ import annotations

import io
import csv
import re
import shutil
import subprocess
import tarfile
import tempfile
import unicodedata
import zlib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from zipfile import ZIP_STORED, BadZipFile, ZipFile

import pyodbc
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/certificados/renombrar", tags=["certificados-renombrar"])

CertificateRenameAccess = Depends(
    require_roles(
        "ADMINISTRADOR",
        "ACADEMICO",
        "ADMISIONES",
        "RECTOR",
        "VICERRECTOR",
        "SOPORTE",
    )
)

MAX_FILES = 200
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 120 * 1024 * 1024
MAX_OCR_PAGES = 3

COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_filename(value: str, fallback: str = "SIN_NOMBRE") -> str:
    normalized = unicodedata.normalize("NFD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9._ -]+", " ", ascii_text)
    safe = re.sub(r"\s+", " ", safe).strip(" ._-")
    return safe[:210] or fallback


def _normalize_for_search(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _pdf_literal_unescape(value: str) -> str:
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    value = re.sub(r"\\([0-7]{1,3})", lambda match: chr(int(match.group(1), 8)), value)
    value = re.sub(r"\\([nrtbf])", " ", value)
    return value


def _decode_pdf_stream(stream: bytes, dictionary: bytes) -> str:
    data = stream.strip(b"\r\n")
    filters = dictionary.decode("latin-1", errors="ignore")

    try:
        if "ASCII85Decode" in filters or "/A85" in filters:
            import base64

            prepared = re.sub(rb"\s+", b"", data)
            if prepared.endswith(b"~>"):
                data = base64.a85decode(prepared, adobe=True)
            else:
                data = base64.a85decode(prepared.rstrip(b">"), adobe=False)
        if "FlateDecode" in filters or "/Fl" in filters:
            data = zlib.decompress(data)
    except Exception:
        return ""

    text = _pdf_literal_unescape(data.decode("latin-1", errors="ignore"))
    literals = [_pdf_literal_unescape(match) for match in re.findall(r"\((.*?)\)", text, flags=re.DOTALL)]
    return "\n".join([text, *literals])


def _extract_text_with_optional_lib(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _extract_text_with_poppler(data: bytes) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return ""

    input_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(data)
            input_path = temp_pdf.name

        completed = subprocess.run(
            [pdftotext, "-enc", "UTF-8", input_path, "-"],
            check=False,
            capture_output=True,
            timeout=20,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    finally:
        if input_path:
            try:
                Path(input_path).unlink(missing_ok=True)
            except Exception:
                pass


def _tesseract_executable() -> str:
    executable = shutil.which("tesseract")
    if executable:
        return executable
    for path in COMMON_TESSERACT_PATHS:
        if Path(path).exists():
            return path
    return ""


def _ocr_is_available() -> bool:
    if not _tesseract_executable():
        return False
    if shutil.which("pdftoppm") or shutil.which("pdftocairo"):
        return True
    try:
        import pypdfium2  # type: ignore[import-not-found]  # noqa: F401

        return True
    except Exception:
        return False


def _extract_text_with_pdfium_ocr(data: bytes) -> str:
    tesseract = _tesseract_executable()
    if not tesseract:
        return ""
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except Exception:
        return ""

    try:
        pytesseract.pytesseract.tesseract_cmd = tesseract
    except Exception:
        pass

    try:
        document = pdfium.PdfDocument(data)
    except Exception:
        return ""

    text_parts: list[str] = []
    try:
        page_count = min(len(document), MAX_OCR_PAGES)
        for page_index in range(page_count):
            page = document[page_index]
            try:
                bitmap = page.render(scale=3.2, rotation=0)
                image = bitmap.to_pil()
                width, height = image.size
                crops = [
                    image,
                    image.crop((0, int(height * 0.18), width, int(height * 0.62))),
                ]
                for crop in crops:
                    for config in ("--psm 6", "--psm 11"):
                        try:
                            text = pytesseract.image_to_string(crop, lang="spa+eng", config=config)
                        except Exception:
                            text = pytesseract.image_to_string(crop, config=config)
                        if text:
                            text_parts.append(text)
                            joined = "\n".join(text_parts)
                            if _cedula_candidates(joined) and _document_info_from_text(joined).get("nombres"):
                                return joined
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    finally:
        try:
            document.close()
        except Exception:
            pass
    return "\n".join(text_parts)


def _extract_text_with_tesseract_cli(data: bytes) -> str:
    tesseract = _tesseract_executable()
    pdftoppm = shutil.which("pdftoppm")
    pdftocairo = shutil.which("pdftocairo")
    if not tesseract or not (pdftoppm or pdftocairo):
        return ""

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.pdf"
            output_prefix = temp_path / "page"
            input_path.write_bytes(data)

            if pdftoppm:
                render_command = [
                    pdftoppm,
                    "-r",
                    "260",
                    "-png",
                    "-f",
                    "1",
                    "-l",
                    str(MAX_OCR_PAGES),
                    str(input_path),
                    str(output_prefix),
                ]
                image_pattern = "page-*.png"
            else:
                render_command = [
                    pdftocairo or "",
                    "-r",
                    "260",
                    "-png",
                    "-f",
                    "1",
                    "-l",
                    str(MAX_OCR_PAGES),
                    str(input_path),
                    str(output_prefix),
                ]
                image_pattern = "page-*.png"

            rendered = subprocess.run(render_command, check=False, capture_output=True, timeout=30)
            if rendered.returncode != 0:
                return ""

            text_parts: list[str] = []
            for image_path in sorted(temp_path.glob(image_pattern)):
                for psm in ("6", "11"):
                    completed = subprocess.run(
                        [tesseract, str(image_path), "stdout", "--psm", psm],
                        check=False,
                        capture_output=True,
                        timeout=30,
                    )
                    if completed.stdout:
                        text_parts.append(completed.stdout.decode("utf-8", errors="ignore"))
                        if _cedula_candidates("\n".join(text_parts)):
                            return "\n".join(text_parts)
            return "\n".join(text_parts)
    except Exception:
        return ""


def _extract_text_with_optional_ocr(data: bytes) -> str:
    tesseract = _tesseract_executable()
    if not tesseract:
        return ""
    pdfium_text = _extract_text_with_pdfium_ocr(data)
    if pdfium_text:
        return pdfium_text
    if not shutil.which("pdftoppm") and not shutil.which("pdftocairo"):
        return ""

    cli_text = _extract_text_with_tesseract_cli(data)
    if cli_text:
        return cli_text

    try:
        from pdf2image import convert_from_bytes  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except Exception:
        return ""

    try:
        pytesseract.pytesseract.tesseract_cmd = tesseract
    except Exception:
        pass

    try:
        images = convert_from_bytes(
            data,
            dpi=260,
            first_page=1,
            last_page=MAX_OCR_PAGES,
            thread_count=1,
        )
    except Exception:
        return ""

    text_parts: list[str] = []
    for image in images:
        try:
            width, height = image.size
            crops = [
                image,
                image.crop((0, int(height * 0.26), width, int(height * 0.48))),
            ]
            for crop in crops:
                for config in ("--psm 6", "--psm 11"):
                    text_parts.append(pytesseract.image_to_string(crop, config=config))
        except Exception:
            continue
    return "\n".join(text_parts)


def _extract_pdf_text(data: bytes) -> str:
    parts: list[str] = []
    library_text = _extract_text_with_optional_lib(data)
    if library_text:
        parts.append(library_text)

    poppler_text = _extract_text_with_poppler(data)
    if poppler_text:
        parts.append(poppler_text)

    ocr_text = _extract_text_with_optional_ocr(data)
    if ocr_text:
        parts.append(ocr_text)

    raw_text = data.decode("latin-1", errors="ignore")
    parts.append(raw_text)

    for match in re.finditer(rb"(<<.*?>>)\s*stream\s*(.*?)\s*endstream", data, flags=re.DOTALL):
        decoded = _decode_pdf_stream(match.group(2), match.group(1))
        if decoded:
            parts.append(decoded)

    for match in re.finditer(rb"(<<.*?/Filter.*?>>)\s*stream\s*(.*?)\s*endstream", data, flags=re.DOTALL):
        decoded = _decode_pdf_stream(match.group(2), match.group(1))
        if decoded:
            parts.append(decoded)

    return "\n".join(parts)


def _cedula_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def append_candidate(value: str, *, validate: bool = True) -> None:
        digits = re.sub(r"\D+", "", value)
        if len(digits) == 9 and not validate:
            digits = f"0{digits}"
        if len(digits) == 10 and (not validate or _is_valid_ecuador_cedula(digits)) and digits not in seen:
            seen.add(digits)
            candidates.append(digits)

    normalized_text = _normalize_for_search(_pdf_literal_unescape(text))
    specific_patterns = [
        r"titular\s+de\s+la\s+cedula\s*(?:no|nro|num|numero|#)?\.?\s*[:\-]?\s*(\d[\d\s.\-]{7,18}\d)",
        r"titular\s+de\s+la\s+cedula\D{0,35}(\d[\d\s.\-]{7,18}\d)",
        r"cedula\s*(?:no|nro|num|numero|#)?\.?\s*[:\-]?\s*(\d[\d\s.\-]{7,18}\d)",
        r"cedula\D{0,35}(\d[\d\s.\-]{7,18}\d)",
    ]
    for pattern in specific_patterns:
        for match in re.findall(pattern, normalized_text, flags=re.IGNORECASE):
            append_candidate(match, validate=False)
    if candidates:
        return candidates

    for match in re.findall(r"(?<!\d)(\d[\d\s.\-]{8,18}\d)(?!\d)", text):
        append_candidate(match)
    return candidates


def _single_line(value: str) -> str:
    value = _pdf_literal_unescape(value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(
        r"\b(?:cedula|c[eé]dula|titular|carrera|semestre|periodo|fecha)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _clean(value.strip(" :;,.|-"))


def _visible_pdf_lines(text: str) -> list[str]:
    return [
        _pdf_literal_unescape(line)
        for line in text.splitlines()
        if line.strip() and " Tj" not in line and " Tm " not in line and not line.lstrip().startswith(("BT", "ET", "/F"))
    ]


def _extract_document_field(text: str, label_pattern: str) -> str:
    visible_lines = _visible_pdf_lines(text)
    patterns = [
        rf"^\s*(?:{label_pattern})\s*[:\-]\s*([^\n\r]+)",
        rf"^\s*(?:{label_pattern})\s+([^\n\r]+)",
    ]
    for line in visible_lines:
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                value = _single_line(match.group(1))
                if value:
                    return value

    fallback_patterns = [
        rf"(?:{label_pattern})\s*[:\-]\s*([^\n\r]+)",
        rf"(?:{label_pattern})\s+([^\n\r]+)",
    ]
    for pattern in fallback_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _single_line(match.group(1))
    return ""


def _extract_certificate_type(text: str) -> str:
    visible_text = "\n".join(_visible_pdf_lines(text))
    normalized = _normalize_for_search(visible_text or text)
    if "matricula" in normalized:
        return "CERTIFICADO_MATRICULA"
    if "promocion" in normalized:
        return "CERTIFICADO_PROMOCION"
    if "asistencia" in normalized:
        return "CERTIFICADO_ASISTENCIA"
    if "calificaciones" in normalized or "notas" in normalized:
        return "CERTIFICADO_CALIFICACIONES"

    candidates = [
        r"certificado\s+de\s+([a-záéíóúñü\s]{3,80})",
        r"certifica(?:do)?\s+que",
    ]
    for pattern in candidates:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        if match.groups():
            value = _single_line(match.group(1))
            if value:
                return f"CERTIFICADO_{_safe_filename(value).replace(' ', '_').upper()}"
        return "CERTIFICADO"
    if "matricula" in normalized:
        return "CERTIFICADO_MATRICULA"
    return "CERTIFICADO"


def _extract_document_student_name(text: str) -> str:
    visible_text = "\n".join(_visible_pdf_lines(text))
    patterns = [
        r"estudiante\s*:\s*(.*?)\s*,?\s*titular\s+de\s+la\s+c[eé]dula",
        r"el/la\s+estudiante\s*:\s*(.*?)\s*,?\s*titular",
        r"el\s*/?\s*la\s+estudiante\s*:\s*(.*?)\s*,?\s*titular",
        r"(?:el|la)\s+estudiante\s*:\s*(.*?)\s*,?\s*titular",
        r"(?:a\s+petici[oó]n\s+de|se\s+certifica\s+que)\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{8,120})",
        r"estudiante\s*:\s*([^\n\r]+)",
        r"estudiante\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{8,120})",
        r"nombre\s*:\s*([^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, visible_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            name = _single_line(match.group(1))
            if name:
                return name

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            name = _single_line(match.group(1))
            if name:
                return name
    return ""


def _document_info_from_text(text: str) -> dict[str, str]:
    return {
        "tipo_certificado": _extract_certificate_type(text),
        "nombres": _extract_document_student_name(text),
        "carrera": _extract_document_field(text, r"carrera"),
        "periodo": _extract_document_field(text, r"periodo\s+acad[eé]mico|periodo"),
    }


def _rename_from_document(
    *,
    original_name: str,
    selected_cedula: str,
    text: str,
    detail: str,
) -> dict[str, Any]:
    document_info = _document_info_from_text(text)
    tipo_certificado = _clean(document_info.get("tipo_certificado")) or "CERTIFICADO"
    nombres = _clean(document_info.get("nombres")) or _safe_filename(Path(original_name).stem)
    carrera = _clean(document_info.get("carrera"))
    periodo = _clean(document_info.get("periodo"))
    name_parts = [
        tipo_certificado,
        selected_cedula,
        nombres,
        carrera,
        periodo,
    ]
    new_name = f"{_safe_filename(' - '.join(part for part in name_parts if part))}.pdf"
    return {
        "original_name": original_name,
        "new_name": new_name,
        "cedula": selected_cedula,
        "nombres": nombres,
        "codigo_estud": "",
        "carrera": carrera,
        "periodo": periodo,
        "status": "RENOMBRADO_DOCUMENTO",
        "detail": detail,
    }


def _is_valid_ecuador_cedula(cedula: str) -> bool:
    if not re.fullmatch(r"\d{10}", cedula):
        return False
    province = int(cedula[:2])
    third_digit = int(cedula[2])
    if province < 1 or province > 24 or third_digit > 5:
        return False

    coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for index, coefficient in enumerate(coefficients):
        value = int(cedula[index]) * coefficient
        total += value - 9 if value > 9 else value
    verifier = (10 - (total % 10)) % 10
    return verifier == int(cedula[9])


def _student_lookup(cedulas: list[str]) -> dict[str, dict[str, Any]]:
    if not cedulas:
        return {}

    placeholders = ",".join("?" for _ in cedulas)
    sql = f"""
    SELECT
        LTRIM(RTRIM(TRY_CONVERT(VARCHAR(50), d.Cedula_Est))) AS cedula,
        TRY_CONVERT(VARCHAR(50), d.codigo_estud) AS codigo_estud,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), d.Apellidos_nombre))) AS nombres,
        LTRIM(RTRIM(TRY_CONVERT(VARCHAR(150), d.correo))) AS correo,
        LTRIM(RTRIM(TRY_CONVERT(VARCHAR(150), d.correointec))) AS correo_intec,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), ca.Nombre_Basica))) AS carrera,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), pe.Detalle_Periodo))) AS periodo
    FROM dbo.DATOS_ESTUD d
    OUTER APPLY (
        SELECT TOP 1 cm.cod_anio_Basica, cm.codigo_periodo
        FROM dbo.CABECERA_MATRICULA cm
        WHERE cm.codigo_estud = d.codigo_estud
        ORDER BY cm.codigo_periodo DESC, cm.numcodigo DESC
    ) ultima
    LEFT JOIN dbo.CARRERAS ca
        ON ca.Cod_AnioBasica = ultima.cod_anio_Basica
    LEFT JOIN dbo.PERIODO pe
        ON pe.cod_periodo = ultima.codigo_periodo
    WHERE LTRIM(RTRIM(TRY_CONVERT(VARCHAR(50), d.Cedula_Est))) IN ({placeholders})
    """

    fallback_sql = f"""
    SELECT
        LTRIM(RTRIM(TRY_CONVERT(VARCHAR(50), p.Cedula))) AS cedula,
        TRY_CONVERT(VARCHAR(50), p.Codestu) AS codigo_estud,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), p.Apellidos_nombre))) AS nombres,
        LTRIM(RTRIM(TRY_CONVERT(VARCHAR(150), p.correo))) AS correo,
        CAST(NULL AS VARCHAR(150)) AS correo_intec,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), ca.Nombre_Basica))) AS carrera,
        LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), pe.Detalle_Periodo))) AS periodo
    FROM dbo.PREINSCRIPCION p
    LEFT JOIN dbo.CARRERAS ca
        ON ca.Cod_AnioBasica = p.codcarrera
    LEFT JOIN dbo.PERIODO pe
        ON pe.cod_periodo = p.codperiodo
    WHERE LTRIM(RTRIM(TRY_CONVERT(VARCHAR(50), p.Cedula))) IN ({placeholders})
    """

    found: dict[str, dict[str, Any]] = {}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, cedulas)
            columns = [column[0] for column in cursor.description]
            for row in cursor.fetchall():
                item = {column: value for column, value in zip(columns, row)}
                found[_clean(item.get("cedula"))] = item

            missing = [cedula for cedula in cedulas if cedula not in found]
            if missing:
                cursor.execute(fallback_sql.replace(placeholders, ",".join("?" for _ in missing)), missing)
                columns = [column[0] for column in cursor.description]
                for row in cursor.fetchall():
                    item = {column: value for column, value in zip(columns, row)}
                    found.setdefault(_clean(item.get("cedula")), item)
    except pyodbc.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo consultar estudiantes por cedula",
        ) from exc

    return found


def _analyze_pdf(original_name: str, data: bytes, index: int) -> dict[str, Any]:
    if not original_name.lower().endswith(".pdf"):
        return {
            "original_name": original_name,
            "new_name": "",
            "cedula": "",
            "nombres": "",
            "codigo_estud": "",
            "carrera": "",
            "periodo": "",
            "status": "NO_PDF",
            "detail": "El archivo no es PDF.",
        }

    text = _extract_pdf_text(data)
    candidates = _cedula_candidates(text)
    students = _student_lookup(candidates)
    selected_cedula = next((cedula for cedula in candidates if cedula in students), candidates[0] if candidates else "")
    student = students.get(selected_cedula, {})

    if not selected_cedula:
        detail = "No se encontro una cedula valida; se renombro con informacion detectada en el PDF."
        if not _ocr_is_available():
            detail = (
                "No se encontro una cedula valida y OCR no esta disponible; "
                "se renombro con el texto seleccionable o el nombre original del documento."
            )
        return _rename_from_document(
            original_name=original_name,
            selected_cedula="",
            text=text,
            detail=detail,
        )

    if not student:
        return _rename_from_document(
            original_name=original_name,
            selected_cedula=selected_cedula,
            text=text,
            detail="La cedula no existe en DATOS_ESTUD/PREINSCRIPCION; se renombro con informacion detectada en el PDF.",
        )

    nombres = _clean(student.get("nombres"))
    codigo = _clean(student.get("codigo_estud"))
    carrera = _clean(student.get("carrera"))
    periodo = _clean(student.get("periodo"))
    name_parts = [
        "CERTIFICADO_MATRICULA",
        selected_cedula,
        nombres,
        carrera,
        periodo,
    ]
    new_name = f"{_safe_filename(' - '.join(part for part in name_parts if part))}.pdf"
    return {
        "original_name": original_name,
        "new_name": new_name,
        "cedula": selected_cedula,
        "nombres": nombres,
        "codigo_estud": codigo,
        "carrera": carrera,
        "periodo": periodo,
        "status": "LISTO",
        "detail": "Renombrado con datos de la base.",
    }


def _append_file(
    result: list[tuple[str, bytes]],
    *,
    name: str,
    data: bytes,
    total_size: int,
) -> int:
    if len(result) >= MAX_FILES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Maximo {MAX_FILES} archivos por lote.")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} supera 12 MB.")
    total_size += len(data)
    if total_size > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El lote supera 120 MB.")
    result.append((name, data))
    return total_size


def _zip_pdf_entries(zip_name: str, data: bytes) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                raw_name = _clean(info.filename).replace("\\", "/")
                if not raw_name or raw_name.startswith("__MACOSX/"):
                    continue
                if not raw_name.lower().endswith(".pdf"):
                    continue
                if info.file_size > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{Path(raw_name).name} dentro de {zip_name} supera 12 MB.",
                    )
                entry_name = _safe_filename(f"{Path(zip_name).stem} - {Path(raw_name).name}", f"archivo_{len(entries) + 1}.pdf")
                entries.append((entry_name, archive.read(info)))
    except BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{zip_name} no es un ZIP valido.") from exc

    return entries


async def _read_files(files: list[UploadFile] | None) -> list[tuple[str, bytes]]:
    uploads = files or []
    if not uploads:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sube al menos un PDF o un ZIP con PDFs.")
    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Maximo {MAX_FILES} archivos por lote.")

    total_size = 0
    result: list[tuple[str, bytes]] = []
    for upload in uploads:
        original_name = _clean(upload.filename)
        name = _safe_filename(original_name, f"archivo_{len(result) + 1}.pdf")
        data = await upload.read()
        if original_name.lower().endswith(".zip"):
            if len(data) > MAX_TOTAL_BYTES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} supera 120 MB.")
            zip_entries = _zip_pdf_entries(name, data)
            if not zip_entries:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} no contiene PDFs para renombrar.")
            for entry_name, entry_data in zip_entries:
                total_size = _append_file(result, name=entry_name, data=entry_data, total_size=total_size)
            continue

        total_size = _append_file(result, name=name, data=data, total_size=total_size)

    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se encontraron PDFs para procesar.")
    return result


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name

    stem = Path(name).stem
    suffix = Path(name).suffix or ".pdf"
    counter = 2
    while True:
        candidate = f"{stem}_{counter}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def _analysis_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "ready": sum(1 for item in items if item.get("status") in {"LISTO", "RENOMBRADO_DOCUMENTO"}),
        "without_cedula": sum(1 for item in items if item.get("status") == "SIN_CEDULA"),
        "not_found": sum(1 for item in items if item.get("status") == "CEDULA_NO_ENCONTRADA"),
        "not_pdf": sum(1 for item in items if item.get("status") == "NO_PDF"),
    }


def _analyze_uploaded_files(read_files: list[tuple[str, bytes]]) -> list[tuple[dict[str, Any], bytes]]:
    return [(_analyze_pdf(name, data, index + 1), data) for index, (name, data) in enumerate(read_files)]


def _report_csv_bytes(items: list[dict[str, Any]]) -> bytes:
    report = io.StringIO()
    writer = csv.DictWriter(
        report,
        fieldnames=[
            "original_name",
            "new_name",
            "cedula",
            "nombres",
            "codigo_estud",
            "carrera",
            "periodo",
            "status",
            "detail",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow({field: item.get(field, "") for field in writer.fieldnames or []})
    return report.getvalue().encode("utf-8-sig")


def _renamed_archive_name(item: dict[str, Any], used_names: set[str]) -> str:
    if item.get("status") in {"LISTO", "CEDULA_NO_ENCONTRADA", "RENOMBRADO_DOCUMENTO"} and item.get("new_name"):
        filename = _unique_name(_clean(item["new_name"]), used_names)
    else:
        filename = _unique_name(f"SIN_RENOMBRAR_{_safe_filename(_clean(item.get('original_name')), 'archivo.pdf')}", used_names)
    item["new_name"] = filename
    return filename


def _local_export_root() -> Path:
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return downloads / "certificados_renombrados"
    return Path.cwd() / "exports" / "certificados_renombrados"


@router.post("/analizar")
async def analyze_certificate_rename_files(
    files: Annotated[list[UploadFile] | None, File()] = None,
    _: SessionUser = CertificateRenameAccess,
) -> dict[str, Any]:
    read_files = await _read_files(files)
    items = [_analyze_pdf(name, data, index + 1) for index, (name, data) in enumerate(read_files)]
    return {
        "items": items,
        "summary": _analysis_summary(items),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.post("/descargar")
async def download_renamed_certificate_files(
    files: Annotated[list[UploadFile] | None, File()] = None,
    _: SessionUser = CertificateRenameAccess,
) -> StreamingResponse:
    read_files = await _read_files(files)
    analyzed = _analyze_uploaded_files(read_files)

    output = io.BytesIO()
    used_names: set[str] = set()
    with ZipFile(output, "w", ZIP_STORED) as archive:
        report_items: list[dict[str, Any]] = []
        for item, data in analyzed:
            filename = _renamed_archive_name(item, used_names)
            report_items.append(item)
            archive.writestr(filename, data)

        archive.writestr("reporte_renombrado_certificados.csv", _report_csv_bytes(report_items))

    output.seek(0)
    filename = f"certificados-renombrados-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        output,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/guardar-local")
async def save_renamed_certificate_files_local(
    files: Annotated[list[UploadFile] | None, File()] = None,
    _: SessionUser = CertificateRenameAccess,
) -> dict[str, Any]:
    read_files = await _read_files(files)
    analyzed = _analyze_uploaded_files(read_files)

    batch_dir = _local_export_root() / datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    report_items: list[dict[str, Any]] = []
    saved = 0
    for item, data in analyzed:
        filename = _renamed_archive_name(item, used_names)
        (batch_dir / filename).write_bytes(data)
        report_items.append(item)
        saved += 1

    report_name = "reporte_renombrado_certificados.csv"
    (batch_dir / report_name).write_bytes(_report_csv_bytes(report_items))

    return {
        "local_dir": str(batch_dir),
        "report": str(batch_dir / report_name),
        "saved": saved,
        "summary": _analysis_summary(report_items),
        "items": report_items,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.post("/descargar-tar")
async def download_renamed_certificate_files_tar(
    files: Annotated[list[UploadFile] | None, File()] = None,
    _: SessionUser = CertificateRenameAccess,
) -> StreamingResponse:
    read_files = await _read_files(files)
    analyzed = _analyze_uploaded_files(read_files)

    output = io.BytesIO()
    used_names: set[str] = set()
    report_items: list[dict[str, Any]] = []
    with tarfile.open(fileobj=output, mode="w") as archive:
        for item, data in analyzed:
            filename = _renamed_archive_name(item, used_names)
            report_items.append(item)
            info = tarfile.TarInfo(filename)
            info.size = len(data)
            info.mtime = int(datetime.now().timestamp())
            archive.addfile(info, io.BytesIO(data))

        report_bytes = _report_csv_bytes(report_items)
        report_info = tarfile.TarInfo("reporte_renombrado_certificados.csv")
        report_info.size = len(report_bytes)
        report_info.mtime = int(datetime.now().timestamp())
        archive.addfile(report_info, io.BytesIO(report_bytes))

    output.seek(0)
    filename = f"certificados-renombrados-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar"
    return StreamingResponse(
        output,
        media_type="application/x-tar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
