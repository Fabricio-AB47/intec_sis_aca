from __future__ import annotations

import asyncio
from io import BytesIO
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.core.file_security import read_secure_upload
from app.core.security import SessionUser, require_screen_access
from app.services.curriculum_updater import analyze_curriculum, generate_curriculum_workbook


router = APIRouter(prefix="/api/curriculum-updater", tags=["curriculum-updater"])

_SCREEN_ACCESS = require_screen_access("actualizar-malla-carrera")
_MAX_WORKBOOK_BYTES = 30 * 1024 * 1024
_MAX_ACADEMIC_DOCUMENT_BYTES = 30 * 1024 * 1024
_MAX_ACADEMIC_DOCUMENTS = 60
_MAX_TOTAL_ACADEMIC_DOCUMENT_BYTES = 350 * 1024 * 1024


class CurriculumProposal(BaseModel):
    field: str = Field(default="", max_length=12_000)
    learning_outcomes: str = Field(default="", max_length=24_000)
    minimum_contents: str = Field(default="", max_length=24_000)


class CurriculumUpdate(BaseModel):
    row_number: int = Field(ge=1, le=100_000)
    subject_name: str = Field(min_length=1, max_length=500)
    period: str = Field(default="", max_length=120)
    apply: bool = False
    status: str = Field(default="", max_length=80)
    source_file: str = Field(default="", max_length=500)
    proposal: CurriculumProposal = Field(default_factory=CurriculumProposal)


def _parse_updates(raw: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError
        updates = [CurriculumUpdate.model_validate(item).model_dump() for item in payload]
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La selección de materias no tiene un formato válido.",
        ) from exc
    if len(updates) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La selección supera el máximo de 500 materias.",
        )
    return updates


async def _read_workbook(workbook: UploadFile) -> tuple[str, bytes]:
    return await read_secure_upload(
        workbook,
        maximum=_MAX_WORKBOOK_BYTES,
        label="archivo de malla",
        allowed_extensions={".xlsx"},
        allowed_content_types={
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream",
        },
    )


async def _read_academic_files(uploads: list[UploadFile]) -> list[tuple[str, bytes]]:
    if len(uploads) > _MAX_ACADEMIC_DOCUMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Puede analizar hasta {_MAX_ACADEMIC_DOCUMENTS} documentos PEA o sílabo por proceso.",
        )
    documents: list[tuple[str, bytes]] = []
    total_size = 0
    for upload in uploads:
        filename, content = await read_secure_upload(
            upload,
            maximum=_MAX_ACADEMIC_DOCUMENT_BYTES,
            label="documento PEA o sílabo",
            allowed_extensions={".pdf"},
            allowed_content_types={"application/pdf", "application/octet-stream"},
        )
        total_size += len(content)
        if total_size > _MAX_TOTAL_ACADEMIC_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Los documentos PEA o sílabo superan el tamaño total permitido de 350 MB.",
            )
        documents.append((filename, content))
    return documents


@router.post("/analyze")
async def analyze_curriculum_files(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    workbook: Annotated[UploadFile, File()],
    academic_files: Annotated[list[UploadFile] | None, File()] = None,
    pea_files: Annotated[list[UploadFile] | None, File()] = None,
    career_name: Annotated[str, Form(max_length=180)] = "",
) -> dict[str, Any]:
    del current_user
    workbook_filename, workbook_content = await _read_workbook(workbook)
    documents = await _read_academic_files([*(academic_files or []), *(pea_files or [])])
    try:
        return await asyncio.to_thread(
            analyze_curriculum,
            workbook_content,
            workbook_filename,
            documents,
            career_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/generate")
async def generate_curriculum_file(
    current_user: Annotated[SessionUser, Depends(_SCREEN_ACCESS)],
    workbook: Annotated[UploadFile, File()],
    updates_json: Annotated[str, Form()],
    career_name: Annotated[str, Form(max_length=180)] = "",
) -> StreamingResponse:
    workbook_filename, workbook_content = await _read_workbook(workbook)
    updates = _parse_updates(updates_json)
    try:
        content, filename, result = await asyncio.to_thread(
            generate_curriculum_workbook,
            workbook_content,
            workbook_filename,
            career_name,
            updates,
            current_user.login,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Curriculum-Target-Sheet": str(result["target_sheet"]),
            "X-Curriculum-Applied": str(result["applied"]),
        },
    )
