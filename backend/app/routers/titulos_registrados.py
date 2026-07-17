from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from typing import Annotated, Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import SessionUser, require_roles
from app.services.graph import get_graph_token
from app.services.db import get_connection, get_titulation_connection
from app.routers.certificate_renamer import _extract_pdf_text

router = APIRouter(prefix="/api/titulos-registrados", tags=["titulos-registrados"])

_VIEW_ACCESS = require_roles("ADMINISTRADOR", "SECRETARIA", "ACADEMICO", "RECTOR", "VICERRECTOR")
_ADMIN_ACCESS = require_roles("ADMINISTRADOR")
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _BACKEND_ROOT / "uploads" / "titulos_registrados"
_INDEX_PATH = _UPLOAD_ROOT / "metadata.json"
_MAX_FILE_BYTES = 25 * 1024 * 1024
_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png"}
_ONEDRIVE_ROOT_FOLDER = "TITULACION GESTION DOCUMENTAL"
_MODEL_TYPES = {
    "senescyt": "Títulos registrados SENESCYT",
    "intec": "Títulos INTEC",
}
_ONEDRIVE_TYPE_FOLDERS = {
    "senescyt": "TITULOS REGISTRADOS SENESCYT",
    "intec": "TITULOS INTEC",
}


class TitleUpdatePayload(BaseModel):
    estudiante: str | None = None
    cedula: str | None = None
    carrera: str | None = None
    modelo: str | None = None
    observacion: str | None = None


class TitleFolderPayload(BaseModel):
    tipo: str
    nombre: str


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _safe_path_name(value: str, fallback: str = "archivo") -> str:
    text = _clean(value) or fallback
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._")
    return text[:120] or fallback


def _safe_folder_name(value: str, fallback: str = "carpeta") -> str:
    text = _clean(value) or fallback
    text = re.sub(r'[<>:"/\\|?*]+', "_", text).strip(" ._")
    return text[:120] or fallback


def _model_key(value: str) -> str:
    key = _clean(value).lower()
    if key not in _MODEL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Modelo de título inválido")
    return key


def _ensure_storage() -> None:
    _UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    if not _INDEX_PATH.exists():
        _INDEX_PATH.write_text("[]", encoding="utf-8")


def _read_index() -> list[dict[str, Any]]:
    _ensure_storage()
    try:
        data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []
    return data if isinstance(data, list) else []


def _write_index(items: list[dict[str, Any]]) -> None:
    _ensure_storage()
    _INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_url(relative_path: str) -> str:
    return f"/uploads/titulos_registrados/{relative_path.replace('\\', '/')}"


def _graph_drive_user() -> str:
    settings = get_settings()
    user = _clean(settings.graph_mail_sender)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configura GRAPH_MAIL_SENDER o MS_SENDER_USER_ID para almacenar títulos en OneDrive.",
        )
    return quote(user, safe="")


def _graph_headers(content_type: str = "application/json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_graph_token()}",
        "Content-Type": content_type,
    }


def _drive_item_path_url(path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/") if part)
    return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/root:/{encoded_path}"


def _drive_children_url(item_id: str = "root") -> str:
    if item_id == "root":
        return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/root/children"
    return f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/items/{quote(item_id, safe='')}/children"


def _ensure_onedrive_folder(path: str) -> dict[str, Any]:
    parts = [part for part in path.split("/") if part]
    current_path = ""
    parent_id = "root"
    item: dict[str, Any] = {}
    with httpx.Client(timeout=30.0) as client:
        for part in parts:
            current_path = f"{current_path}/{part}".strip("/")
            get_response = client.get(
                f"{_drive_item_path_url(current_path)}:",
                headers={"Authorization": f"Bearer {get_graph_token()}"},
            )
            if get_response.status_code == 404:
                create_response = client.post(
                    _drive_children_url(parent_id),
                    headers=_graph_headers(),
                    json={
                        "name": part,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "rename",
                    },
                )
                create_response.raise_for_status()
                item = create_response.json()
            else:
                get_response.raise_for_status()
                item = get_response.json()
            parent_id = str(item.get("id") or parent_id)
    return item


def _upload_to_onedrive(folder_path: str, filename: str, content: bytes, content_type: str) -> dict[str, Any]:
    _ensure_onedrive_folder(folder_path)
    upload_path = f"{folder_path}/{filename}"
    upload_url = f"{_drive_item_path_url(upload_path)}:/content"
    with httpx.Client(timeout=120.0) as client:
        response = client.put(
            upload_url,
            headers=_graph_headers(content_type or "application/octet-stream"),
            content=content,
        )
        response.raise_for_status()
        return response.json()


def _delete_onedrive_item(item_id: str) -> None:
    if not item_id:
        return
    url = f"https://graph.microsoft.com/v1.0/users/{_graph_drive_user()}/drive/items/{quote(item_id, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(url, headers={"Authorization": f"Bearer {get_graph_token()}"})
        if response.status_code == 404:
            return
        response.raise_for_status()


def _list_onedrive_folders(path: str) -> list[dict[str, Any]]:
    folder = _ensure_onedrive_folder(path)
    item_id = _clean(folder.get("id"))
    if not item_id:
        return []
    url = _drive_children_url(item_id)
    folders: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        while url:
            response = client.get(url, headers={"Authorization": f"Bearer {get_graph_token()}"})
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("value") or []:
                if isinstance(item, dict) and item.get("folder") is not None:
                    folders.append(
                        {
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "web_url": item.get("webUrl"),
                            "created_at": item.get("createdDateTime"),
                        }
                    )
            url = payload.get("@odata.nextLink")
    folders.sort(key=lambda item: _clean(item.get("name")).lower())
    return folders


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "tipo": item.get("tipo"),
        "tipo_nombre": _MODEL_TYPES.get(str(item.get("tipo")), str(item.get("tipo") or "")),
        "modelo": item.get("modelo", ""),
        "estudiante": item.get("estudiante", ""),
        "cedula": item.get("cedula", ""),
        "carrera": item.get("carrera", ""),
        "observacion": item.get("observacion", ""),
        "filename": item.get("filename", ""),
        "content_type": item.get("content_type", ""),
        "size": item.get("size", 0),
        "url": item.get("web_url") or (_public_url(str(item.get("relative_path", ""))) if item.get("relative_path") else ""),
        "storage": item.get("storage", "local"),
        "titulacion_status": item.get("titulacion_status", ""),
        "titulacion_expediente_id": item.get("titulacion_expediente_id"),
        "titulacion_message": item.get("titulacion_message", ""),
        "created_at": item.get("created_at", ""),
        "created_by": item.get("created_by", ""),
    }


def _senescyt_identifications_from_text(text: str) -> list[str]:
    normalized = _clean(text)
    candidates: list[str] = []
    for match in re.finditer(r"(?<!\d)(\d{10})(?!\d)(?=.{0,220}3048-\d{4}-\d+)", normalized, flags=re.IGNORECASE | re.DOTALL):
        value = match.group(1)
        if value not in candidates:
            candidates.append(value)
    if candidates:
        return candidates
    for value in re.findall(r"(?<!\d)(\d{10})(?!\d)", normalized):
        if value not in candidates:
            candidates.append(value)
    return candidates


def _identifications_from_filename(filename: str) -> list[str]:
    normalized = _clean(Path(filename).stem)
    candidates: list[str] = []
    for value in re.findall(r"(?<!\d)(\d{10})(?!\d)", normalized):
        if value not in candidates:
            candidates.append(value)
    for value in re.findall(r"(?<!\d)(\d[\d\s._-]{8,18}\d)(?!\d)", normalized):
        document = re.sub(r"\D+", "", value)
        if len(document) == 10 and document not in candidates:
            candidates.append(document)
    return candidates


def _bulk_identifications(title_type: str, filename: str, pdf_text: str) -> list[str]:
    filename_candidates = _identifications_from_filename(filename)
    text_candidates = _senescyt_identifications_from_text(pdf_text)
    ordered = filename_candidates + text_candidates if title_type == "intec" else text_candidates + filename_candidates
    result: list[str] = []
    for value in ordered:
        document = re.sub(r"\D+", "", value)
        if len(document) == 10 and document not in result:
            result.append(document)
    return result


def _lookup_students_by_identification(identifications: list[str]) -> dict[str, dict[str, str]]:
    cleaned = []
    for value in identifications:
        document = re.sub(r"\D+", "", value)
        if len(document) == 10 and document not in cleaned:
            cleaned.append(document)
    if not cleaned:
        return {}
    placeholders = ",".join("?" for _ in cleaned)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    TRY_CONVERT(varchar(50), d.codigo_estud) AS codigo_estud,
                    LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Cedula_Est))) AS cedula,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), d.Apellidos_nombre))) AS estudiante,
                    COALESCE(LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), c.Nombre_Basica))), N'') AS carrera,
                    LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Estado))) AS estado
                FROM dbo.DATOS_ESTUD d
                OUTER APPLY (
                    SELECT TOP (1) cx.cod_anio_Basica
                    FROM dbo.CARRERAXESTUD cx
                    WHERE TRY_CONVERT(varchar(50), cx.codigo_estud) = TRY_CONVERT(varchar(50), d.codigo_estud)
                    ORDER BY TRY_CONVERT(int, cx.codigo_periodo) DESC
                ) ult
                LEFT JOIN dbo.CARRERAS c
                    ON TRY_CONVERT(varchar(50), c.Cod_AnioBasica) = TRY_CONVERT(varchar(50), ult.cod_anio_Basica)
                WHERE REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Cedula_Est))), '-', ''), ' ', '') IN ({placeholders})
                """,
                *cleaned,
            )
            result: dict[str, dict[str, str]] = {}
            for row in cursor.fetchall():
                cedula = re.sub(r"\D+", "", _clean(row.cedula))
                if cedula:
                    result[cedula] = {
                        "codigo_estud": _clean(row.codigo_estud),
                        "cedula": cedula,
                        "estudiante": _clean(row.estudiante),
                        "carrera": _clean(row.carrera),
                        "estado": _clean(row.estado),
                    }
            return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo validar estudiantes en DATOS_ESTUD: {exc}") from exc


def _title_filename(prefix: str, cedula: str, estudiante: str, source_name: str, extension: str, item_id: str) -> str:
    student_part = _safe_path_name(estudiante, "estudiante")
    source_part = _safe_path_name(Path(source_name).stem, "documento")
    return _safe_path_name(f"{prefix}_{cedula}_{student_part}_{source_part}_{item_id[:8]}{extension}", "titulo.pdf")


def _senescyt_registration_code_from_text(text: str) -> str:
    match = re.search(r"\b(3048-\d{4}-\d+)\b", text or "")
    return _clean(match.group(1)) if match else ""


def _register_title_in_titulation(
    *,
    title_type: str,
    cedula: str,
    filename: str,
    web_url: str,
    item_id: str,
    user: str,
    senescyt_code: str = "",
) -> dict[str, Any]:
    document = re.sub(r"\D+", "", cedula)
    if not document:
        return {"status": "omitido", "message": "Sin cédula para vincular con TITULACION_INTEC."}

    tipo_documento = "TITULO_SENESCYT" if title_type == "senescyt" else "TITULO_INTEC"
    formato = "TITULO_SENESCYT_PDF" if title_type == "senescyt" else "TITULO_INTEC_PDF"
    nombre_documento = "Título registrado en SENESCYT" if title_type == "senescyt" else "Título generado por INTEC"
    ruta_nube = web_url or filename

    try:
        with get_titulation_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    E.ExpedienteId,
                    E.NumeroActaGrado
                FROM tit.ExpedienteTitulacion E
                LEFT JOIN core.EstudianteRef ER
                    ON ER.EstudianteRefId = E.EstudianteRefId
                WHERE REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(varchar(50), COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion)))), '-', ''), ' ', '') = ?
                ORDER BY
                    CASE WHEN EXISTS (
                        SELECT 1
                        FROM tit.ActaGrado A
                        WHERE A.ExpedienteId = E.ExpedienteId
                          AND ISNULL(A.Activo, 1) = 1
                    ) THEN 0 ELSE 1 END,
                    E.ExpedienteId DESC
                """,
                document,
            )
            expediente = cursor.fetchone()
            if not expediente:
                return {
                    "status": "sin_expediente",
                    "message": "No existe expediente de titulación para la cédula indicada.",
                }

            expediente_id = int(expediente.ExpedienteId)
            cursor.execute(
                """
                INSERT INTO doc.DocumentoExpediente
                (
                    ExpedienteId,
                    TipoDocumentoCodigo,
                    FormatoCargaCodigo,
                    NombreArchivo,
                    RutaNube,
                    EsFirmadoElectronico,
                    FechaDocumento,
                    UsuarioCarga,
                    Observacion
                )
                VALUES (?, ?, ?, ?, ?, 1, CAST(GETDATE() AS DATE), ?, ?)
                """,
                expediente_id,
                tipo_documento,
                formato,
                filename,
                ruta_nube,
                user,
                f"Registrado automáticamente desde módulo Títulos registrados. OneDriveItemId={item_id}",
            )

            if title_type == "senescyt":
                cursor.execute(
                    """
                    INSERT INTO tit.RegistroSenescyt
                    (
                        ExpedienteId,
                        CodigoRegistroSenescyt,
                        FechaRegistro,
                        RutaDocumentoNube,
                        UsuarioRegistro
                    )
                    VALUES (?, ?, CAST(GETDATE() AS DATE), ?, ?)
                    """,
                    expediente_id,
                    senescyt_code or item_id,
                    ruta_nube,
                    user,
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO tit.TituloIntec
                    (
                        ExpedienteId,
                        NumeroTitulo,
                        FechaEmision,
                        RutaDocumentoNube,
                        UsuarioGeneracion
                    )
                    VALUES (?, ?, CAST(GETDATE() AS DATE), ?, ?)
                    """,
                    expediente_id,
                    item_id,
                    ruta_nube,
                    user,
                )

            conn.commit()
            return {
                "status": "registrado",
                "expediente_id": expediente_id,
                "message": "Documento registrado en TITULACION_INTEC.",
            }
    except (pyodbc.Error, RuntimeError) as exc:
        return {"status": "error", "message": f"No se pudo registrar en TITULACION_INTEC: {exc}"}


@router.get("")
def list_registered_titles(
    current_user: Annotated[SessionUser, Depends(_VIEW_ACCESS)],
    tipo: Annotated[str, Query(max_length=20)] = "",
    search: Annotated[str, Query(max_length=120)] = "",
) -> dict[str, Any]:
    del current_user
    type_filter = _clean(tipo).lower()
    if type_filter and type_filter not in _MODEL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de título inválido")
    needle = _clean(search).lower()
    items = _read_index()
    filtered: list[dict[str, Any]] = []
    for item in items:
        if type_filter and item.get("tipo") != type_filter:
            continue
        haystack = " ".join(
            _clean(item.get(key)).lower()
            for key in ("estudiante", "cedula", "carrera", "modelo", "observacion", "filename", "tipo")
        )
        if needle and needle not in haystack:
            continue
        filtered.append(item)
    filtered.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    totals = {
        "total": len(items),
        "senescyt": sum(1 for item in items if item.get("tipo") == "senescyt"),
        "intec": sum(1 for item in items if item.get("tipo") == "intec"),
    }
    return {
        "items": [_serialize_item(item) for item in filtered],
        "totals": totals,
        "modelos": [{"value": key, "label": label} for key, label in _MODEL_TYPES.items()],
    }


@router.get("/folders")
def list_title_folders(
    current_user: Annotated[SessionUser, Depends(_VIEW_ACCESS)],
    tipo: Annotated[str, Query(max_length=20)] = "senescyt",
) -> dict[str, Any]:
    del current_user
    title_type = _model_key(tipo)
    folder_path = f"{_ONEDRIVE_ROOT_FOLDER}/{_ONEDRIVE_TYPE_FOLDERS[title_type]}"
    try:
        folders = _list_onedrive_folders(folder_path)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo consultar carpetas de OneDrive: {detail}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo consultar carpetas de OneDrive: {exc}") from exc
    return {"items": folders, "root": folder_path}


@router.post("/folders")
def create_title_folder(
    payload: TitleFolderPayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    title_type = _model_key(payload.tipo)
    folder_name = _safe_folder_name(payload.nombre)
    if not folder_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ingresa el nombre de la carpeta")
    folder_path = f"{_ONEDRIVE_ROOT_FOLDER}/{_ONEDRIVE_TYPE_FOLDERS[title_type]}/{folder_name}"
    try:
        folder = _ensure_onedrive_folder(folder_path)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo crear carpeta en OneDrive: {detail}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo crear carpeta en OneDrive: {exc}") from exc
    return {
        "ok": True,
        "message": "Carpeta disponible en OneDrive",
        "item": {"id": folder.get("id"), "name": folder.get("name"), "web_url": folder.get("webUrl")},
    }


@router.get("/students")
def search_title_students(
    current_user: Annotated[SessionUser, Depends(_VIEW_ACCESS)],
    search: Annotated[str, Query(min_length=2, max_length=120)],
) -> dict[str, Any]:
    del current_user
    text = _clean(search)
    document = re.sub(r"\D+", "", text)
    like = f"%{text}%"
    document_like = f"%{document or text}%"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (20)
                    TRY_CONVERT(varchar(50), d.codigo_estud) AS codigo_estud,
                    LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Cedula_Est))) AS cedula,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), d.Apellidos_nombre))) AS estudiante,
                    COALESCE(LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), c.Nombre_Basica))), N'') AS carrera,
                    LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Estado))) AS estado
                FROM dbo.DATOS_ESTUD d
                OUTER APPLY (
                    SELECT TOP (1) cx.cod_anio_Basica
                    FROM dbo.CARRERAXESTUD cx
                    WHERE TRY_CONVERT(varchar(50), cx.codigo_estud) = TRY_CONVERT(varchar(50), d.codigo_estud)
                    ORDER BY TRY_CONVERT(int, cx.codigo_periodo) DESC
                ) ult
                LEFT JOIN dbo.CARRERAS c
                    ON TRY_CONVERT(varchar(50), c.Cod_AnioBasica) = TRY_CONVERT(varchar(50), ult.cod_anio_Basica)
                WHERE
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(250), d.Apellidos_nombre))) LIKE ?
                    OR REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(50), d.Cedula_Est))), '-', ''), ' ', '') LIKE ?
                    OR TRY_CONVERT(varchar(50), d.codigo_estud) LIKE ?
                ORDER BY d.Apellidos_nombre
                """,
                like,
                document_like,
                like,
            )
            items = [
                {
                    "codigo_estud": _clean(row.codigo_estud),
                    "cedula": _clean(row.cedula),
                    "estudiante": _clean(row.estudiante),
                    "carrera": _clean(row.carrera),
                    "estado": _clean(row.estado),
                }
                for row in cursor.fetchall()
            ]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo buscar estudiante: {exc}") from exc
    return {"items": items}


@router.post("")
async def upload_registered_title(
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo: Annotated[str, Form()],
    modelo: Annotated[str, Form()],
    estudiante: Annotated[str, Form()] = "",
    cedula: Annotated[str, Form()] = "",
    carrera: Annotated[str, Form()] = "",
    observacion: Annotated[str, Form()] = "",
    file: UploadFile = File(...),
) -> dict[str, Any]:
    title_type = _model_key(tipo)
    clean_model = _clean(modelo)
    if not clean_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ingresa el modelo del título")
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selecciona un archivo")
    extension = Path(file.filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato no permitido para el título")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío")
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo supera 25 MB")

    item_id = uuid4().hex
    filename = f"{datetime.now():%Y%m%d_%H%M%S}_{item_id[:8]}_{_safe_path_name(file.filename, 'titulo')}"
    one_drive_folder = "/".join(
        [
            _ONEDRIVE_ROOT_FOLDER,
            _ONEDRIVE_TYPE_FOLDERS[title_type],
            _safe_folder_name(clean_model, "modelo"),
        ]
    )
    try:
        drive_item = _upload_to_onedrive(one_drive_folder, filename, content, _clean(file.content_type) or "application/octet-stream")
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo subir el título a OneDrive: {detail}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo subir el título a OneDrive: {exc}") from exc

    item = {
        "id": item_id,
        "tipo": title_type,
        "modelo": clean_model,
        "estudiante": _clean(estudiante),
        "cedula": _clean(cedula),
        "carrera": _clean(carrera),
        "observacion": _clean(observacion),
        "filename": _clean(file.filename),
        "content_type": _clean(file.content_type),
        "size": len(content),
        "storage": "onedrive",
        "onedrive_folder": one_drive_folder,
        "onedrive_item_id": _clean(drive_item.get("id")),
        "web_url": _clean(drive_item.get("webUrl")),
        "relative_path": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "created_by": current_user.login,
    }
    senescyt_code = ""
    if title_type == "senescyt" and extension == ".pdf":
        try:
            senescyt_code = _senescyt_registration_code_from_text(_extract_pdf_text(content))
        except Exception:
            senescyt_code = ""
    titulation_result = _register_title_in_titulation(
        title_type=title_type,
        cedula=_clean(cedula),
        filename=filename,
        web_url=_clean(drive_item.get("webUrl")),
        item_id=item_id,
        user=current_user.login,
        senescyt_code=senescyt_code,
    )
    item["titulacion_status"] = titulation_result.get("status", "")
    item["titulacion_expediente_id"] = titulation_result.get("expediente_id")
    item["titulacion_message"] = titulation_result.get("message", "")
    items = _read_index()
    items.append(item)
    _write_index(items)
    return {"ok": True, "message": "Título registrado correctamente", "item": _serialize_item(item)}


@router.post("/bulk")
@router.post("/bulk-senescyt")
async def upload_titles_bulk(
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    modelo: Annotated[str, Form()],
    tipo: Annotated[str, Form()] = "senescyt",
    observacion: Annotated[str, Form()] = "",
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    title_type = _model_key(tipo)
    type_label = "SENESCYT" if title_type == "senescyt" else "INTEC"
    clean_model = _clean(modelo)
    if not clean_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Selecciona o crea la carpeta destino {type_label}")
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Selecciona al menos un PDF {type_label}")

    one_drive_folder = "/".join(
        [
            _ONEDRIVE_ROOT_FOLDER,
            _ONEDRIVE_TYPE_FOLDERS[title_type],
            _safe_folder_name(clean_model, "modelo"),
        ]
    )
    batch_id = uuid4().hex
    items = _read_index()
    created_items: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for file in files:
        original_name = _clean(file.filename) or f"titulo_{title_type}.pdf"
        extension = Path(original_name).suffix.lower()
        if extension != ".pdf":
            results.append(
                {
                    "archivo": original_name,
                    "estado": "OMITIDO",
                    "mensaje": f"Solo se aceptan archivos PDF para carga masiva {type_label}.",
                }
            )
            continue
        content = await file.read()
        if not content:
            results.append({"archivo": original_name, "estado": "OMITIDO", "mensaje": "El archivo está vacío."})
            continue
        if len(content) > _MAX_FILE_BYTES:
            results.append({"archivo": original_name, "estado": "OMITIDO", "mensaje": "El archivo supera 25 MB."})
            continue

        try:
            text = _extract_pdf_text(content)
        except Exception:
            text = ""
        identifications = _bulk_identifications(title_type, original_name, text)
        senescyt_code = _senescyt_registration_code_from_text(text) if title_type == "senescyt" else ""
        students = _lookup_students_by_identification(identifications)
        valid_documents = [cedula for cedula in identifications if cedula in students]
        missing_documents = [cedula for cedula in identifications if cedula not in students]

        if not identifications:
            results.append(
                {
                    "archivo": original_name,
                    "estado": "SIN_IDENTIFICACION",
                    "mensaje": "No se encontró número de identificación en el PDF.",
                }
            )
            continue
        if not valid_documents:
            results.append(
                {
                    "archivo": original_name,
                    "estado": "NO_ENCONTRADO",
                    "identificaciones": identifications,
                    "mensaje": "Las identificaciones encontradas no existen en DATOS_ESTUD.",
                }
            )
            continue

        file_created: list[dict[str, Any]] = []
        for cedula in valid_documents:
            student = students[cedula]
            item_id = uuid4().hex
            renamed_filename = _title_filename(type_label, cedula, student.get("estudiante", ""), original_name, ".pdf", item_id)
            try:
                drive_item = _upload_to_onedrive(one_drive_folder, renamed_filename, content, "application/pdf")
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500] if exc.response is not None else str(exc)
                results.append(
                    {
                        "archivo": original_name,
                        "cedula": cedula,
                        "estado": "ERROR_ONEDRIVE",
                        "mensaje": f"No se pudo subir a OneDrive: {detail}",
                    }
                )
                continue
            except Exception as exc:
                results.append(
                    {
                        "archivo": original_name,
                        "cedula": cedula,
                        "estado": "ERROR_ONEDRIVE",
                        "mensaje": f"No se pudo subir a OneDrive: {exc}",
                    }
                )
                continue

            item = {
                "id": item_id,
                "tipo": title_type,
                "modelo": clean_model,
                "estudiante": student.get("estudiante", ""),
                "cedula": cedula,
                "carrera": student.get("carrera", ""),
                "observacion": _clean(observacion),
                "filename": renamed_filename,
                "original_filename": original_name,
                "content_type": "application/pdf",
                "size": len(content),
                "storage": "onedrive",
                "onedrive_folder": one_drive_folder,
                "onedrive_item_id": _clean(drive_item.get("id")),
                "web_url": _clean(drive_item.get("webUrl")),
                "relative_path": "",
                "batch_id": batch_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "created_by": current_user.login,
            }
            titulation_result = _register_title_in_titulation(
                title_type=title_type,
                cedula=cedula,
                filename=renamed_filename,
                web_url=_clean(drive_item.get("webUrl")),
                item_id=item_id,
                user=current_user.login,
                senescyt_code=senescyt_code,
            )
            item["titulacion_status"] = titulation_result.get("status", "")
            item["titulacion_expediente_id"] = titulation_result.get("expediente_id")
            item["titulacion_message"] = titulation_result.get("message", "")
            items.append(item)
            created_items.append(item)
            file_created.append(_serialize_item(item))

        results.append(
            {
                "archivo": original_name,
                "estado": "PROCESADO" if file_created else "SIN_REGISTROS",
                "registrados": len(file_created),
                "identificaciones": identifications,
                "no_encontrados": missing_documents,
                "items": file_created,
            }
        )

    if created_items:
        _write_index(items)

    message = f"Carga masiva {type_label} finalizada: {len(created_items)} título(s) registrado(s)."
    if not created_items:
        message = "Carga masiva finalizada sin títulos registrados. Revisa el detalle de identificaciones."
    return {
        "ok": True,
        "message": message,
        "affected_rows": len(created_items),
        "batch_id": batch_id,
        "items": [_serialize_item(item) for item in created_items],
        "results": results,
    }


@router.put("/{item_id}")
def update_registered_title(
    item_id: str,
    payload: TitleUpdatePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    items = _read_index()
    for item in items:
        if item.get("id") == item_id:
            for key in ("estudiante", "cedula", "carrera", "modelo", "observacion"):
                value = getattr(payload, key)
                if value is not None:
                    item[key] = _clean(value)
            _write_index(items)
            return {"ok": True, "message": "Título actualizado", "item": _serialize_item(item)}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Título no encontrado")


@router.delete("/{item_id}")
def delete_registered_title(
    item_id: str,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    del current_user
    items = _read_index()
    next_items: list[dict[str, Any]] = []
    removed: dict[str, Any] | None = None
    for item in items:
        if item.get("id") == item_id:
            removed = item
        else:
            next_items.append(item)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Título no encontrado")
    if removed.get("storage") == "onedrive":
        try:
            _delete_onedrive_item(_clean(removed.get("onedrive_item_id")))
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo eliminar el archivo de OneDrive: {detail}") from exc
    relative_path = _clean(removed.get("relative_path"))
    if relative_path and removed.get("storage") != "onedrive":
        target = (_UPLOAD_ROOT / relative_path).resolve()
        if _UPLOAD_ROOT.resolve() in target.parents and target.exists():
            target.unlink()
            parent = target.parent
            while parent != _UPLOAD_ROOT and parent.exists() and not any(parent.iterdir()):
                shutil.rmtree(parent)
                parent = parent.parent
    _write_index(next_items)
    return {"ok": True, "message": "Título eliminado", "affected_rows": 1}
