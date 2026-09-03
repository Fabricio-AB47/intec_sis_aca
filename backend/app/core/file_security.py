from __future__ import annotations

import asyncio
import re
import socket
import struct
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Iterable
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

_SCAN_CHUNK_SIZE = 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 10_000
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsm": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}


def _safe_filename(upload: UploadFile, label: str) -> str:
    raw = str(upload.filename or "").strip()
    filename = re.split(r"[\\/]", raw)[-1].strip()
    if not filename or filename in {".", ".."} or _CONTROL_CHARACTERS.search(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El nombre de {label} no es válido.",
        )
    return filename


def _validate_archive(
    content: bytes,
    *,
    maximum: int,
    required_entries: set[str] | None = None,
) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > _MAX_ARCHIVE_ENTRIES:
                raise ValueError("demasiados elementos")
            expanded_limit = max(maximum, 100 * 1024 * 1024)
            expanded_size = 0
            names: set[str] = set()
            for item in entries:
                normalized = PurePosixPath(item.filename.replace("\\", "/"))
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise ValueError("ruta interna no permitida")
                if item.flag_bits & 0x1:
                    raise ValueError("archivo cifrado no permitido")
                expanded_size += max(int(item.file_size), 0)
                if expanded_size > expanded_limit:
                    raise ValueError("contenido expandido demasiado grande")
                names.add(item.filename)
            if required_entries and not required_entries.issubset(names):
                raise ValueError("estructura del documento incompleta")
    except (BadZipFile, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo comprimido no tiene una estructura válida o segura.",
        ) from exc


def _validate_signature(filename: str, content: bytes, maximum: int) -> None:
    extension = Path(filename).suffix.casefold()
    if extension == ".pdf":
        if not content[:1024].lstrip().startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El contenido de {filename} no coincide con su extensión.",
            )
        return
    if extension == ".webp":
        if len(content) < 12 or not content.startswith(b"RIFF") or content[8:12] != b"WEBP":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El contenido de {filename} no coincide con su extensión.",
            )
        return
    signatures = _SIGNATURES.get(extension)
    if signatures and not any(content.startswith(signature) for signature in signatures):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El contenido de {filename} no coincide con su extensión.",
        )
    archive_requirements = {
        ".xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
        ".xlsm": {"[Content_Types].xml", "xl/workbook.xml"},
        ".docx": {"[Content_Types].xml", "word/document.xml"},
    }
    if extension in {".zip", *archive_requirements}:
        _validate_archive(
            content,
            maximum=maximum,
            required_entries=archive_requirements.get(extension),
        )


def _clamav_scan(content: bytes) -> None:
    settings = get_settings()
    try:
        with socket.create_connection(
            (settings.upload_antimalware_host, settings.upload_antimalware_port),
            timeout=settings.upload_antimalware_timeout_seconds,
        ) as scanner:
            scanner.settimeout(settings.upload_antimalware_timeout_seconds)
            scanner.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), _SCAN_CHUNK_SIZE):
                chunk = content[offset : offset + _SCAN_CHUNK_SIZE]
                scanner.sendall(struct.pack(">I", len(chunk)))
                scanner.sendall(chunk)
            scanner.sendall(struct.pack(">I", 0))
            response = scanner.recv(4096).decode("utf-8", errors="replace").strip("\x00\r\n ")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El análisis de seguridad de archivos no está disponible.",
        ) from exc
    if response.endswith(" FOUND"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo fue rechazado por el control de seguridad.",
        )
    if not response.endswith(" OK"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El análisis de seguridad no pudo confirmar el archivo.",
        )


def verify_antimalware_available() -> None:
    settings = get_settings()
    if not settings.upload_antimalware_enabled:
        return
    try:
        with socket.create_connection(
            (settings.upload_antimalware_host, settings.upload_antimalware_port),
            timeout=settings.upload_antimalware_timeout_seconds,
        ) as scanner:
            scanner.settimeout(settings.upload_antimalware_timeout_seconds)
            scanner.sendall(b"zPING\0")
            response = scanner.recv(64).decode("utf-8", errors="replace").strip("\x00\r\n ")
    except OSError as exc:
        raise RuntimeError("El servicio antimalware no está disponible") from exc
    if response != "PONG":
        raise RuntimeError("El servicio antimalware devolvió una respuesta inválida")


async def read_secure_upload(
    upload: UploadFile,
    *,
    maximum: int,
    label: str = "archivo",
    allowed_extensions: Iterable[str] | None = None,
    allowed_content_types: Iterable[str] | None = None,
    validate_signature: bool = True,
    allow_empty: bool = False,
) -> tuple[str, bytes]:
    """Lee con límite, valida el formato y analiza el archivo antes de devolverlo."""
    try:
        filename = _safe_filename(upload, label)
        extension = Path(filename).suffix.casefold()
        if allowed_extensions is not None:
            extensions = {value.casefold() for value in allowed_extensions}
            if extension not in extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El formato de {label} no está permitido.",
                )
        if allowed_content_types is not None and upload.content_type:
            content_type = upload.content_type.split(";", maxsplit=1)[0].strip().casefold()
            accepted_types = {value.casefold() for value in allowed_content_types}
            if content_type not in accepted_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El tipo de contenido de {label} no está permitido.",
                )

        content = await upload.read(maximum + 1)
        if len(content) > maximum:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"{label.capitalize()} supera el tamaño máximo permitido.",
            )
        if not content and not allow_empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label.capitalize()} está vacío.",
            )
        if content and validate_signature:
            _validate_signature(filename, content, maximum)
        if content and get_settings().upload_antimalware_enabled:
            await asyncio.to_thread(_clamav_scan, content)
        return filename, content
    finally:
        await upload.close()
