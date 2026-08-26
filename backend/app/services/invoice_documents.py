from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from fastapi import HTTPException, UploadFile

from app.services.graph_documents import safe_filename


MAX_INVOICE_XML_BYTES = 20 * 1024 * 1024
MAX_RIDE_PDF_BYTES = 50 * 1024 * 1024


async def read_upload(upload: UploadFile, *, maximum: int, label: str) -> bytes:
    content = await upload.read(maximum + 1)
    await upload.close()
    if not content:
        raise HTTPException(status_code=400, detail=f"{label} está vacío.")
    if len(content) > maximum:
        size_mb = maximum // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"{label} supera el límite de {size_mb} MB.",
        )
    return content


def validate_invoice_xml(filename: str, content: bytes) -> str:
    try:
        normalized = safe_filename(filename, {".xml"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Factura XML: {exc}") from exc

    uppercase_content = content[: min(len(content), 1024 * 1024)].upper()
    if b"<!DOCTYPE" in uppercase_content or b"<!ENTITY" in uppercase_content:
        raise HTTPException(
            status_code=400,
            detail="El XML contiene declaraciones externas que no están permitidas.",
        )
    try:
        ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise HTTPException(
            status_code=400,
            detail="La factura XML no contiene un documento XML válido.",
        ) from exc
    return normalized


def validate_ride_pdf(filename: str, content: bytes) -> str:
    try:
        normalized = safe_filename(filename, {".pdf"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"RIDE: {exc}") from exc
    if not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="El RIDE seleccionado no es un PDF válido.")
    return normalized


def backup_storage_name(prefix: str, original_name: str, extension: str, token: str) -> str:
    stem = Path(original_name).stem[:80]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return safe_filename(
        f"{prefix}_{timestamp}_{token}_{stem}{extension}",
        {extension},
    )
