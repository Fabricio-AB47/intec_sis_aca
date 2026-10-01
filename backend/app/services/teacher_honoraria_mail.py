from __future__ import annotations

import base64
import json
import re
from uuid import uuid4
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.services.graph import get_graph_token


HONORARIA_RECIPIENTS = ("roberto.castro@intec.edu.ec", "veronica.cevallos@intec.edu.ec")
HONORARIA_SUBJECT = "Honorarios docentes"
_SMALL_ATTACHMENT_LIMIT = 3 * 1024 * 1024
_UPLOAD_CHUNK = 10 * 320 * 1024
_DIRECT_REQUEST_LIMIT = 3 * 1024 * 1024
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class TeacherMailDeliveryUncertain(RuntimeError):
    """The send request may have succeeded; manual verification is required before retry."""


class TeacherMailConfigurationError(RuntimeError):
    """Safe configuration explanation that may be shown to the user."""


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
        "INFORME", "NOTAS", "NOTAS_POR_CARRERA", "CONTRATO", "FACTURA_XML", "RIDE"
    } or len(documents) != 6:
        raise ValueError("El correo requiere los cuatro PDF firmados, la factura XML y el RIDE.")

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
                "Adjuntos: informe de cumplimiento, reporte de notas, anexo de notas por carrera, contrato, factura XML y RIDE."
            ),
        },
        "toRecipients": [recipient(address) for address in HONORARIA_RECIPIENTS],
        "ccRecipients": [recipient(copy_address)],
    }
    headers = {"Authorization": f"Bearer {get_graph_token()}"}
    # Keep the encoded request below the request-size limit. Small expedientes
    # can use Mail.Send without requiring permission to create mailbox drafts.
    if sum(len(item["content"]) for item in documents) < _DIRECT_REQUEST_LIMIT:
        direct_message = {**message, "attachments": [
            {"@odata.type": "#microsoft.graph.fileAttachment", "name": str(item["filename"]),
             "contentType": str(item["content_type"]),
             "contentBytes": base64.b64encode(item["content"]).decode("ascii")}
            for item in documents
        ]}
        body = json.dumps({"message": direct_message, "saveToSentItems": True}, ensure_ascii=False).encode("utf-8")
        if len(body) < _DIRECT_REQUEST_LIMIT:
            request_id = str(uuid4())
            try:
                with httpx.Client(timeout=120.0) as client:
                    sent = client.post(
                        f"https://graph.microsoft.com/v1.0/users/{quote(sender, safe='')}/sendMail",
                        content=body,
                        headers={**headers, "Content-Type": "application/json", "client-request-id": request_id},
                    )
                    sent.raise_for_status()
                    if sent.status_code != 202:
                        raise TeacherMailDeliveryUncertain("Microsoft Graph no confirmó la aceptación del correo.")
            except httpx.RequestError as exc:
                raise TeacherMailDeliveryUncertain("No se pudo confirmar la respuesta de Microsoft Graph al enviar.") from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    raise TeacherMailDeliveryUncertain("Microsoft Graph no confirmó si procesó el envío.") from exc
                if exc.response.status_code in {401, 403}:
                    raise TeacherMailConfigurationError("Microsoft Graph rechazó el envío. Revise Mail.Send y el acceso al buzón institucional.") from exc
                raise
            return f"sendMail:{sent.headers.get('request-id') or request_id}"
    draft_id = ""
    with httpx.Client(timeout=120.0) as client:
        response = client.post(base_url, json=message, headers=headers)
        if response.status_code in {401, 403}:
            raise TeacherMailConfigurationError(
                "Los adjuntos requieren la carga de archivos grandes. Configure Mail.ReadWrite "
                "con consentimiento administrativo en Microsoft Graph. Los documentos permanecen archivados."
            )
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
