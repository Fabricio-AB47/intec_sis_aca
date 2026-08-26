from __future__ import annotations

from datetime import datetime
import logging
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.security import SessionUser, require_screen_access
from app.services.graph_documents import delete_item, upload_bytes
from app.services.invoice_documents import (
    MAX_INVOICE_XML_BYTES as _MAX_INVOICE_XML_BYTES,
    MAX_RIDE_PDF_BYTES as _MAX_RIDE_PDF_BYTES,
    backup_storage_name as _backup_storage_name,
    read_upload as _read_upload,
    validate_invoice_xml as _validate_invoice_xml,
    validate_ride_pdf as _validate_ride_pdf,
)
from app.services.integration_history import (
    IntegrationHistoryUnavailableError,
    append_teacher_compliance_documents,
    get_teacher_compliance_archive,
    get_history_detail,
    integration_history_summary,
    list_database_events,
    list_teacher_compliance_documents,
    list_teacher_report_events,
)


router = APIRouter(prefix="/api/integrations/history", tags=["integration-history"])
_HISTORY_ACCESS = require_screen_access("historico-integraciones")
_COMPLIANCE_ACCESS = require_screen_access("informe-cumplimiento")
logger = logging.getLogger(__name__)

def _service_unavailable(exc: IntegrationHistoryUnavailableError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _archive_folder_path(value: object) -> str:
    normalized = str(value or "").strip().replace("\\", "/").strip("/")
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    if (
        len(parts) < 3
        or parts[0].casefold() != "docentes"
        or parts[2].casefold() != "documentos firmados"
        or any(part in {".", ".."} for part in parts)
    ):
        raise HTTPException(
            status_code=409,
            detail="El expediente no tiene una carpeta documental válida en Microsoft 365.",
        )
    return "/".join(parts)


async def _rollback_graph_items(items: list[dict]) -> None:
    for item in reversed(items):
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        try:
            await run_in_threadpool(delete_item, item_id)
        except Exception:
            logger.exception("No se pudo revertir un respaldo incompleto en Microsoft 365.")


@router.get("/summary")
def history_summary(
    _current_user: Annotated[SessionUser, Depends(_HISTORY_ACCESS)],
) -> dict:
    try:
        return integration_history_summary()
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc


@router.get("/database-events")
def database_events(
    _current_user: Annotated[SessionUser, Depends(_HISTORY_ACCESS)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
    operation: Literal["", "INSERT", "UPDATE", "DELETE"] = "",
    database: Annotated[str, Query(max_length=128)] = "",
    search: Annotated[str, Query(max_length=200)] = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    try:
        return list_database_events(
            page=page,
            page_size=page_size,
            operation=operation,
            database=database.strip(),
            search=search.strip(),
            date_from=date_from,
            date_to=date_to,
        )
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc


@router.get("/teacher-reports")
def teacher_report_events(
    _current_user: Annotated[SessionUser, Depends(_HISTORY_ACCESS)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
    stage: Literal["", "GENERADO", "FIRMADO", "ARCHIVADO", "ERROR"] = "",
    status: Literal["", "EXITOSO", "ERROR"] = "",
    search: Annotated[str, Query(max_length=200)] = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    try:
        return list_teacher_report_events(
            page=page,
            page_size=page_size,
            stage=stage,
            status=status,
            search=search.strip(),
            date_from=date_from,
            date_to=date_to,
        )
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc


@router.get("/compliance-documents")
def compliance_documents(
    _current_user: Annotated[SessionUser, Depends(_COMPLIANCE_ACCESS)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 25,
    search: Annotated[str, Query(max_length=200)] = "",
    document_type: Literal[
        "", "INFORME", "NOTAS", "CONTRATO", "PAQUETE", "FACTURA_XML", "RIDE", "CARPETA", "OTRO"
    ] = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    try:
        return list_teacher_compliance_documents(
            page=page,
            page_size=page_size,
            search=search.strip(),
            document_type=document_type,
            date_from=date_from,
            date_to=date_to,
        )
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc


@router.post("/compliance-documents/{event_id}/invoice-backups")
async def upload_compliance_invoice_backups(
    event_id: int,
    current_user: Annotated[SessionUser, Depends(_COMPLIANCE_ACCESS)],
    factura_xml: Annotated[UploadFile, File(description="Factura electrónica en formato XML")],
    ride_pdf: Annotated[UploadFile, File(description="Representación RIDE en formato PDF")],
) -> dict:
    try:
        archive = await run_in_threadpool(get_teacher_compliance_archive, event_id)
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc
    if archive is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el expediente archivado del informe de cumplimiento.",
        )

    folder_path = _archive_folder_path(archive.get("folder_path"))
    xml_content = await _read_upload(
        factura_xml,
        maximum=_MAX_INVOICE_XML_BYTES,
        label="La factura XML",
    )
    ride_content = await _read_upload(
        ride_pdf,
        maximum=_MAX_RIDE_PDF_BYTES,
        label="El RIDE",
    )
    xml_original = _validate_invoice_xml(factura_xml.filename or "factura.xml", xml_content)
    ride_original = _validate_ride_pdf(ride_pdf.filename or "ride.pdf", ride_content)

    backup_id = uuid4().hex
    token = backup_id[:8]
    stored_files = (
        {
            "original_name": xml_original,
            "stored_name": _backup_storage_name("FACTURA_XML", xml_original, ".xml", token),
            "content": xml_content,
            "content_type": "application/xml",
            "document_type": "FACTURA_XML",
        },
        {
            "original_name": ride_original,
            "stored_name": _backup_storage_name("RIDE", ride_original, ".pdf", token),
            "content": ride_content,
            "content_type": "application/pdf",
            "document_type": "RIDE",
        },
    )
    uploaded_items: list[dict] = []
    metadata_documents: list[dict] = []
    try:
        for stored_file in stored_files:
            item = await run_in_threadpool(
                upload_bytes,
                f"{folder_path}/{stored_file['stored_name']}",
                stored_file["content"],
                stored_file["content_type"],
            )
            uploaded_items.append(item)
            metadata_documents.append(
                {
                    "id": item.get("id"),
                    "nombre": item.get("name") or stored_file["stored_name"],
                    "nombre_original": stored_file["original_name"],
                    "url": item.get("webUrl"),
                    "tipo_documento": stored_file["document_type"],
                    "content_type": stored_file["content_type"],
                    "tamano_bytes": len(stored_file["content"]),
                    "respaldo_factura_id": backup_id,
                }
            )
    except Exception as exc:
        await _rollback_graph_items(uploaded_items)
        logger.exception("No se pudo guardar el respaldo de factura en Microsoft 365.")
        raise HTTPException(
            status_code=502,
            detail="No se pudieron guardar la factura XML y el RIDE en Microsoft 365.",
        ) from exc

    uploaded_by = current_user.email or current_user.login or "USUARIO"
    try:
        registered = await run_in_threadpool(
            append_teacher_compliance_documents,
            event_id=event_id,
            documents=metadata_documents,
            backup_id=backup_id,
            uploaded_by=uploaded_by,
        )
    except IntegrationHistoryUnavailableError as exc:
        await _rollback_graph_items(uploaded_items)
        raise _service_unavailable(exc) from exc
    if registered is None:
        await _rollback_graph_items(uploaded_items)
        raise HTTPException(
            status_code=404,
            detail="El expediente dejó de estar disponible antes de registrar los respaldos.",
        )

    return {
        "message": "La factura XML y el RIDE se guardaron en la carpeta del docente.",
        "event_id": event_id,
        "backup_id": backup_id,
        "folder_path": folder_path,
        "folder_url": archive.get("folder_url"),
        "documents": metadata_documents,
    }


@router.get("/detail/{kind}/{event_id}")
def history_detail(
    kind: Literal["database", "teacher-report"],
    event_id: int,
    _current_user: Annotated[SessionUser, Depends(_HISTORY_ACCESS)],
) -> dict:
    try:
        detail = get_history_detail(kind, event_id)
    except IntegrationHistoryUnavailableError as exc:
        raise _service_unavailable(exc) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="No se encontró el movimiento solicitado.")
    return {"kind": kind, "event": detail}
