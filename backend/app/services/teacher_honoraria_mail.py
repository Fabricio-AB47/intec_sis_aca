from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.services.graph import get_graph_token


HONORARIA_RECIPIENTS = ("roberto.castro@intec.edu.ec", "veronica.cevallos@intec.edu.ec")
HONORARIA_SUBJECT = "Honorarios docentes"
_SMALL_ATTACHMENT_LIMIT = 3 * 1024 * 1024
_UPLOAD_CHUNK = 10 * 320 * 1024
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class TeacherMailDeliveryUncertain(RuntimeError):
    """The send request may have succeeded; manual verification is required before retry."""


def teacher_copy_address(identity: dict[str, Any]) -> str:
    for key in ("correo", "correo_personal"):
        address = str(identity.get(key) or "").strip()
        if _EMAIL_PATTERN.fullmatch(address) and address.lower() not in HONORARIA_RECIPIENTS:
            return address
    raise ValueError("El docente no tiene un correo válido para recibir la copia del expediente.")


def send_teacher_honoraria_mail(identity: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    """Send from the configured institutional mailbox; never impersonate the teacher."""
    sender = str(get_settings().graph_mail_sender or "").strip()
    if not _EMAIL_PATTERN.fullmatch(sender):
        raise ValueError("Configure GRAPH_MAIL_SENDER con un buzón institucional válido.")
    copy_address = teacher_copy_address(identity)
    if {str(item.get("document_type")) for item in documents} != {
        "INFORME", "NOTAS", "CONTRATO", "FACTURA_XML", "RIDE"
    } or len(documents) != 5:
        raise ValueError("El correo requiere los tres PDF firmados, la factura XML y el RIDE.")

    def recipient(address: str) -> dict[str, Any]:
        return {"emailAddress": {"address": address}}

    base_url = f"https://graph.microsoft.com/v1.0/users/{quote(sender, safe='')}/messages"
    message = {
        "subject": HONORARIA_SUBJECT,
        "body": {
            "contentType": "Text",
            "content": (
                "Se remiten los documentos firmados para el trámite de honorarios docentes.\n"
                f"Docente: {identity.get('nombre') or ''}\n"
                f"Cédula: {identity.get('cedula') or ''}\n"
                "Adjuntos: informe de cumplimiento, reporte de notas, contrato, factura XML y RIDE."
            ),
        },
        "toRecipients": [recipient(address) for address in HONORARIA_RECIPIENTS],
        "ccRecipients": [recipient(copy_address)],
    }
    headers = {"Authorization": f"Bearer {get_graph_token()}"}
    draft_id = ""
    with httpx.Client(timeout=120.0) as client:
        response = client.post(base_url, json=message, headers=headers)
        response.raise_for_status()
        draft_id = str(response.json().get("id") or "")
        if not draft_id:
            raise RuntimeError("Microsoft Graph no confirmó el borrador del correo.")
        draft_url = f"{base_url}/{quote(draft_id, safe='')}"
        for item in documents:
            try:
                filename = str(item["filename"])
                content = item["content"]
                content_type = str(item["content_type"])
                if len(content) < _SMALL_ATTACHMENT_LIMIT:
                    attachment = {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": filename,
                        "contentType": content_type,
                        "contentBytes": base64.b64encode(content).decode("ascii"),
                    }
                    result = client.post(f"{draft_url}/attachments", json=attachment, headers=headers)
                    result.raise_for_status()
                    continue
                session_response = client.post(
                    f"{draft_url}/attachments/createUploadSession",
                    json={"AttachmentItem": {"attachmentType": "file", "name": filename, "size": len(content), "contentType": content_type}},
                    headers=headers,
                )
                session_response.raise_for_status()
                upload_url = str(session_response.json().get("uploadUrl") or "")
                if not upload_url:
                    raise RuntimeError(f"No se pudo iniciar la carga de {filename}.")
                for offset in range(0, len(content), _UPLOAD_CHUNK):
                    chunk = content[offset : offset + _UPLOAD_CHUNK]
                    upload = client.put(
                        upload_url,
                        content=chunk,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{len(content)}",
                        },
                    )
                    upload.raise_for_status()
                    if offset + len(chunk) == len(content) and upload.status_code not in {200, 201}:
                        raise RuntimeError(f"Microsoft Graph no confirmó el adjunto completo: {filename}.")
            except Exception:
                try:
                    client.delete(draft_url, headers=headers).raise_for_status()
                except Exception:
                    pass
                raise
        try:
            sent = client.post(f"{draft_url}/send", headers=headers)
            sent.raise_for_status()
            if sent.status_code != 202:
                raise TeacherMailDeliveryUncertain("Microsoft Graph no confirmó el envío del borrador.")
        except httpx.RequestError as exc:
            raise TeacherMailDeliveryUncertain("No se pudo confirmar la respuesta de Microsoft Graph al enviar.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise TeacherMailDeliveryUncertain("Microsoft Graph no confirmó si procesó el envío.") from exc
            raise
    return draft_id
