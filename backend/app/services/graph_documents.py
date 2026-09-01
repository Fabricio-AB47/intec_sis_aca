from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.services.db import get_graph_database_connection
from app.services.graph import get_graph_token


MAX_DOCUMENT_BYTES = 1024 * 1024 * 1024
GRAPH_DOCUMENT_ROOT = "EXPEDIENTES ESTUDIANTILES"
GRAPH_SIMPLE_UPLOAD_MAX_BYTES = 250 * 1024 * 1024
GRAPH_UPLOAD_CHUNK_BYTES = 32 * 320 * 1024
GRAPH_MODULE_FOLDERS = {
    "BECAS": "BECAS",
    "INGLES": "IDIOMAS",
    "TITULACION": "TITULACION",
    "PRACTICAS": "PRACTICAS PREPROFESIONALES",
    "VINCULACION": "VINCULACION CON LA SOCIEDAD",
    "SOLICITUDES": "SOLICITUDES",
    "FACTURACION": "FACTURAS",
}
GRAPH_EXPEDIENT_TYPES = {
    "BECAS": (
        "Becas",
        "Contratos de beca y documentos complementarios por período académico.",
    ),
    "INGLES": (
        "Inglés",
        "Archivos y evidencias de evaluación del idioma Inglés.",
    ),
    "TITULACION": (
        "Titulación",
        "Documentos habilitantes, actas y títulos.",
    ),
    "PRACTICAS": (
        "Prácticas preprofesionales",
        "Documentos del expediente de prácticas preprofesionales.",
    ),
    "VINCULACION": (
        "Vinculación con la sociedad",
        "Documentos del expediente de vinculación con la sociedad.",
    ),
    "SOLICITUDES": (
        "Solicitudes",
        "Respaldos y documentos de solicitudes académicas del estudiante.",
    ),
    "FACTURACION": (
        "Facturación",
        "Facturas electrónicas XML y representaciones impresas RIDE del estudiante.",
    ),
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_filename(value: str, allowed_extensions: set[str] | None = None) -> str:
    filename = Path(value.replace("\\", "/")).name.strip()
    filename = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    if not filename:
        raise ValueError('El archivo no tiene un nombre válido.')
    extension = Path(filename).suffix.lower()
    if allowed_extensions is not None and extension not in allowed_extensions:
        raise ValueError(f"El formato {extension or 'sin extensión'} no está permitido.")
    return filename[:255]


def safe_folder_part(
    value: str,
    fallback: str = "expediente",
    *,
    max_length: int = 120,
) -> str:
    normalized = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", clean(value))
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    return (normalized or fallback)[:max_length].rstrip(" .")


def _student_root_from_folder_path(path: str, identification: str) -> str:
    """Return the stable student root only when the path belongs to the identity."""
    document = re.sub(r"\D+", "", identification)
    parts = [
        part.strip()
        for part in clean(path).replace("\\", "/").split("/")
        if part.strip()
    ]
    if not document or len(parts) < 2:
        return ""
    if parts[0].casefold() != GRAPH_DOCUMENT_ROOT.casefold():
        return ""
    if not parts[1].casefold().endswith(f" - {document}".casefold()):
        return ""
    return "/".join(parts[:2])


def build_expedient_folder_path(
    *,
    module_code: str,
    identification: str,
    student_code: int | None,
    student_name: str,
    origin_id: str | int,
    expedient_code: str = "",
    student_root_path: str = "",
) -> str:
    module = clean(module_code).upper()
    document = re.sub(r"\D+", "", identification)
    if module not in GRAPH_MODULE_FOLDERS:
        raise ValueError('Módulo documental no permitido.')
    if not document:
        raise ValueError('La identificación del estudiante es obligatoria.')

    student_root = _student_root_from_folder_path(student_root_path, document)
    if not student_root:
        fallback_name = f"ESTUDIANTE {student_code or document}"
        available_name_length = max(20, 100 - len(document) - 3)
        normalized_name = safe_folder_part(
            student_name,
            fallback_name,
            max_length=available_name_length,
        )
        student_folder = safe_folder_part(
            f"{normalized_name} - {document}",
            document,
            max_length=100,
        )
        student_root = f"{GRAPH_DOCUMENT_ROOT}/{student_folder}"

    origin = safe_folder_part(str(origin_id), "SIN-ID", max_length=30)
    case_code = safe_folder_part(
        expedient_code,
        module,
        max_length=max(20, 75 - len(origin)),
    )
    case_folder = safe_folder_part(
        f"CASO {origin} - {case_code}",
        f"CASO {origin}",
        max_length=85,
    )
    return "/".join([student_root, GRAPH_MODULE_FOLDERS[module], case_folder])


def graph_owner_upn() -> str:
    owner = clean(get_settings().graph_mail_sender)
    if not owner:
        raise RuntimeError(
            "Configura GRAPH_MAIL_SENDER para almacenar expedientes en Microsoft Graph."
        )
    return owner


def _auth_headers(*, json_content: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {get_graph_token()}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _drive_base() -> str:
    return f"https://graph.microsoft.com/v1.0/users/{quote(graph_owner_upn(), safe='')}/drive"


def _encoded_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/") if part)


def _item_path_url(path: str) -> str:
    return f"{_drive_base()}/root:/{_encoded_path(path)}"


def _children_url(parent_id: str) -> str:
    return f"{_drive_base()}/root/children" if parent_id == "root" else f"{_drive_base()}/items/{quote(parent_id, safe='')}/children"


def ensure_folder(path: str) -> dict[str, Any]:
    parent_id = "root"
    current_path = ""
    item: dict[str, Any] = {}
    with httpx.Client(timeout=30.0) as client:
        for part in [segment for segment in path.split("/") if segment]:
            current_path = f"{current_path}/{part}".strip("/")
            response = client.get(f"{_item_path_url(current_path)}:", headers=_auth_headers())
            if response.status_code == 404:
                response = client.post(
                    _children_url(parent_id),
                    headers=_auth_headers(json_content=True),
                    json={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                )
                if response.status_code == 409:
                    response = client.get(f"{_item_path_url(current_path)}:", headers=_auth_headers())
            response.raise_for_status()
            item = response.json()
            parent_id = clean(item.get("id")) or parent_id
    return item


def _find_graph_student_root(identification: str) -> dict[str, Any] | None:
    """Recover an existing student folder even when its database link is missing."""
    document = re.sub(r"\D+", "", identification)
    if not document:
        return None

    search_url = f"{_item_path_url(GRAPH_DOCUMENT_ROOT)}:/search(q='{document}')"
    params: dict[str, str] | None = {
        "$select": "id,name,folder,parentReference,webUrl,createdDateTime,lastModifiedDateTime",
        "$top": "200",
    }
    matches: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        while search_url:
            response = client.get(search_url, headers=_auth_headers(), params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("value") or []:
                if not isinstance(item, dict) or not isinstance(item.get("folder"), dict):
                    continue
                name = clean(item.get("name"))
                candidate = f"{GRAPH_DOCUMENT_ROOT}/{name}"
                if not _student_root_from_folder_path(candidate, document):
                    continue
                parent_path = unquote(
                    clean((item.get("parentReference") or {}).get("path"))
                ).rstrip("/")
                expected_parent = f"/drive/root:/{GRAPH_DOCUMENT_ROOT}".casefold()
                if not parent_path.casefold().endswith(expected_parent):
                    continue
                matches.append({**item, "path": candidate})
            search_url = clean(payload.get("@odata.nextLink"))
            params = None

    if not matches:
        return None
    matches.sort(
        key=lambda item: (
            clean(item.get("createdDateTime")),
            clean(item.get("name")).casefold(),
        )
    )
    return matches[0]


def create_upload_session(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{_item_path_url(path)}:/createUploadSession",
            headers=_auth_headers(json_content=True),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        response.raise_for_status()
        return response.json()


def upload_bytes(
    path: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Upload a complete in-memory document to the configured OneDrive."""
    if not content:
        raise ValueError("El archivo que se enviará a OneDrive está vacío.")

    if len(content) <= GRAPH_SIMPLE_UPLOAD_MAX_BYTES:
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
            response = client.put(
                f"{_item_path_url(path)}:/content",
                headers={
                    **_auth_headers(),
                    "Content-Type": content_type or "application/octet-stream",
                },
                content=content,
            )
            response.raise_for_status()
            return response.json()

    session = create_upload_session(path)
    upload_url = clean(session.get("uploadUrl"))
    if not upload_url:
        raise RuntimeError("Microsoft Graph no devolvió una sesión de carga válida.")

    total_size = len(content)
    uploaded_item: dict[str, Any] | None = None
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        for start in range(0, total_size, GRAPH_UPLOAD_CHUNK_BYTES):
            chunk = content[start : start + GRAPH_UPLOAD_CHUNK_BYTES]
            end = start + len(chunk) - 1
            response = client.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Content-Type": content_type or "application/octet-stream",
                },
                content=chunk,
            )
            response.raise_for_status()
            if response.status_code in {200, 201}:
                uploaded_item = response.json()

    if uploaded_item is None:
        uploaded_item = item_by_path(path)
    if not uploaded_item:
        raise RuntimeError("Microsoft Graph no confirmó la carga completa del archivo.")
    return uploaded_item


def item_by_path(path: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{_item_path_url(path)}:", headers=_auth_headers())
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


def item_by_id(item_id: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{_drive_base()}/items/{quote(item_id, safe='')}",
            headers=_auth_headers(),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


def delete_item(item_id: str) -> None:
    if not item_id:
        return
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(
            f"{_drive_base()}/items/{quote(item_id, safe='')}",
            headers=_auth_headers(),
        )
        if response.status_code not in {204, 404}:
            response.raise_for_status()


def _parse_graph_datetime(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _assert_schema(cursor: Any) -> None:
    if not cursor.execute("SELECT OBJECT_ID(N'doc.ExpedienteGraph', N'U')").fetchval():
        raise RuntimeError(
            "Falta aplicar backend/sql/2026_07_30_graph_expedientes_documentales.sql "
            "en INTEC_GRAPH_INTEGRACION."
        )


def _ensure_expedient_type(cursor: Any, module_code: str) -> None:
    module = clean(module_code).upper()
    expedient_type = GRAPH_EXPEDIENT_TYPES.get(module)
    if not expedient_type:
        raise ValueError("Módulo documental no permitido.")
    cursor.execute(
        """
        MERGE cat.TipoExpedienteGraph AS target
        USING (SELECT ? AS Codigo, ? AS Nombre, ? AS Descripcion) AS source
           ON target.TipoExpedienteGraphCodigo = source.Codigo
        WHEN MATCHED THEN UPDATE SET
            Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
        WHEN NOT MATCHED THEN
            INSERT(TipoExpedienteGraphCodigo, Nombre, Descripcion)
            VALUES(source.Codigo, source.Nombre, source.Descripcion);
        """,
        module,
        expedient_type[0],
        expedient_type[1],
    )


def _ensure_person(
    cursor: Any,
    *,
    identification: str,
    student_code: int | None,
    name: str,
    email: str = "",
) -> int:
    cursor.execute(
        """
        SET NOCOUNT ON;
        DECLARE @PersonaResultado TABLE (PersonaGraphRefId BIGINT NOT NULL);

        MERGE core.PersonaGraphRef AS target
        USING (SELECT 'ESTUDIANTE' AS TipoPersonaCodigo, ? AS NumeroIdentificacion) AS source
           ON target.TipoPersonaCodigo = source.TipoPersonaCodigo
          AND target.NumeroIdentificacion = source.NumeroIdentificacion
        WHEN MATCHED THEN UPDATE SET
            CodigoEstud = COALESCE(?, target.CodigoEstud),
            NombreCompleto = COALESCE(NULLIF(?, N''), target.NombreCompleto),
            CorreoPersonal = COALESCE(NULLIF(?, N''), target.CorreoPersonal),
            OrigenFuente = 'EXPEDIENTE_DOCUMENTAL', Activo = 1,
            FechaSincronizacion = SYSUTCDATETIME(), FechaActualizacion = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT
            (TipoPersonaCodigo, NumeroIdentificacion, CodigoEstud, NombreCompleto,
             CorreoPersonal, OrigenFuente)
        VALUES ('ESTUDIANTE', ?, ?, ?, NULLIF(?, N''), 'EXPEDIENTE_DOCUMENTAL')
        OUTPUT INSERTED.PersonaGraphRefId INTO @PersonaResultado (PersonaGraphRefId);

        SELECT TOP (1) PersonaGraphRefId FROM @PersonaResultado;
        """,
        identification,
        student_code,
        name,
        email,
        identification,
        student_code,
        name or identification,
        email,
    )
    return int(cursor.fetchone()[0])


def _find_registered_student_root_path(cursor: Any, identification: str) -> str:
    document = re.sub(r"\D+", "", identification)
    if not document:
        return ""
    cursor.execute(
        """
        SELECT TOP (25) RutaCarpeta
        FROM doc.ExpedienteGraph
        WHERE Activo = 1
          AND REPLACE(
                REPLACE(REPLACE(LTRIM(RTRIM(NumeroIdentificacion)), '-', ''), ' ', ''),
                '.', ''
              ) = ?
          AND NULLIF(LTRIM(RTRIM(RutaCarpeta)), N'') IS NOT NULL
        ORDER BY FechaActualizacion DESC, ExpedienteGraphId DESC
        """,
        document,
    )
    for row in cursor.fetchall():
        candidate = _student_root_from_folder_path(clean(row[0]), document)
        if candidate:
            return candidate
    return ""


def prepare_expedient(
    *,
    module_code: str,
    identification: str,
    student_code: int | None,
    student_name: str,
    student_email: str,
    base_origin: str,
    schema_origin: str,
    table_origin: str,
    origin_id: str | int,
    expedient_code: str = "",
    audit_user: str,
) -> dict[str, Any]:
    module = clean(module_code).upper()
    document = re.sub(r"\D+", "", identification)
    if module not in GRAPH_MODULE_FOLDERS:
        raise ValueError('Módulo documental no permitido.')
    if not document:
        raise ValueError('La identificación del estudiante es obligatoria.')

    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        student_root_path = _find_registered_student_root_path(cursor, document)

    graph_student_root = None
    if not student_root_path:
        graph_student_root = _find_graph_student_root(document)
        student_root_path = clean((graph_student_root or {}).get("path"))
    student_folder_reused = bool(student_root_path)

    folder_path = build_expedient_folder_path(
        module_code=module,
        identification=document,
        student_code=student_code,
        student_name=student_name,
        origin_id=origin_id,
        expedient_code=expedient_code,
        student_root_path=student_root_path,
    )
    folder_item = ensure_folder(folder_path)
    drive_id = clean((folder_item.get("parentReference") or {}).get("driveId"))
    owner = graph_owner_upn()

    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        _ensure_expedient_type(cursor, module)
        person_id = _ensure_person(
            cursor,
            identification=document,
            student_code=student_code,
            name=student_name,
            email=student_email,
        )
        cursor.execute(
            """
            SET NOCOUNT ON;
            DECLARE @ExpedienteResultado TABLE (ExpedienteGraphId BIGINT NOT NULL);

            MERGE doc.ExpedienteGraph AS target
            USING (SELECT ? AS TipoCodigo, ? AS BaseOrigen, ? AS EsquemaOrigen,
                          ? AS TablaOrigen, ? AS OrigenId) AS source
               ON target.TipoExpedienteGraphCodigo = source.TipoCodigo
              AND target.BaseOrigen = source.BaseOrigen
              AND target.EsquemaOrigen = source.EsquemaOrigen
              AND target.TablaOrigen = source.TablaOrigen
              AND target.OrigenId = source.OrigenId
            WHEN MATCHED THEN UPDATE SET
                PersonaGraphRefId = ?, NumeroIdentificacion = ?, CodigoEstud = ?,
                CodigoExpediente = NULLIF(?, N''), DriveOwnerUPN = ?, GraphDriveId = NULLIF(?, N''),
                GraphFolderItemId = NULLIF(?, N''), RutaCarpeta = ?, GraphWebUrl = NULLIF(?, N''),
                Activo = 1, FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
            WHEN NOT MATCHED THEN INSERT
                (TipoExpedienteGraphCodigo, PersonaGraphRefId, NumeroIdentificacion, CodigoEstud,
                 BaseOrigen, EsquemaOrigen, TablaOrigen, OrigenId, CodigoExpediente,
                 DriveOwnerUPN, GraphDriveId, GraphFolderItemId, RutaCarpeta, GraphWebUrl,
                 UsuarioCreacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, N''), ?, NULLIF(?, N''),
                    NULLIF(?, N''), ?, NULLIF(?, N''), ?)
            OUTPUT INSERTED.ExpedienteGraphId INTO @ExpedienteResultado (ExpedienteGraphId);

            SELECT TOP (1) ExpedienteGraphId FROM @ExpedienteResultado;
            """,
            module,
            base_origin,
            schema_origin,
            table_origin,
            str(origin_id),
            person_id,
            document,
            student_code,
            expedient_code,
            owner,
            drive_id,
            clean(folder_item.get("id")),
            folder_path,
            clean(folder_item.get("webUrl")),
            audit_user,
            module,
            person_id,
            document,
            student_code,
            base_origin,
            schema_origin,
            table_origin,
            str(origin_id),
            expedient_code,
            owner,
            drive_id,
            clean(folder_item.get("id")),
            folder_path,
            clean(folder_item.get("webUrl")),
            audit_user,
        )
        expedient_id = int(cursor.fetchone()[0])
        cursor.execute(
            """
            IF NOT EXISTS
            (
                SELECT 1 FROM integ.EnlaceProcesoGraph
                WHERE BaseOrigen = ? AND ISNULL(EsquemaOrigen, N'') = ?
                  AND ISNULL(TablaOrigen, N'') = ? AND OrigenTipo = ? AND OrigenId = ?
            )
            BEGIN
                INSERT INTO integ.EnlaceProcesoGraph
                    (BaseOrigen, EsquemaOrigen, TablaOrigen, OrigenTipo, OrigenId,
                     PersonaGraphRefId, EstadoOperacionCodigo, Observacion, UsuarioEnlace)
                VALUES (?, ?, ?, ?, ?, ?, 'COMPLETADO', ?, ?)
            END
            """,
            base_origin,
            schema_origin,
            table_origin,
            f"EXPEDIENTE_{module}",
            str(origin_id),
            base_origin,
            schema_origin,
            table_origin,
            f"EXPEDIENTE_{module}",
            str(origin_id),
            person_id,
            f"Expediente documental Graph {expedient_id}",
            audit_user,
        )
        cursor.execute(
            """
            INSERT INTO aud.AuditoriaGraph(EntidadTipo, EntidadId, Accion, Detalle, UsuarioAccion)
            VALUES('EXPEDIENTE_DOCUMENTAL', ?, 'PREPARAR_CARPETA', ?, ?)
            """,
            expedient_id,
            (
                "REUTILIZAR_CARPETA_ESTUDIANTE"
                if student_folder_reused
                else "CREAR_CARPETA_ESTUDIANTE"
            )
            + f" | {folder_path}",
            audit_user,
        )
        conn.commit()

    return {
        "expedient_graph_id": expedient_id,
        "folder_path": folder_path,
        "folder_item_id": clean(folder_item.get("id")),
        "drive_id": drive_id,
        "web_url": clean(folder_item.get("webUrl")),
        "student_folder_reused": student_folder_reused,
    }


def register_upload_session(
    *,
    session_id: UUID,
    expedient_graph_id: int,
    document_type_code: str,
    original_filename: str,
    cloud_filename: str,
    graph_path: str,
    content_type: str,
    expected_size: int,
    upload_url: str,
    expires_at: Any,
    audit_user: str,
    max_expected_size: int = MAX_DOCUMENT_BYTES,
) -> None:
    if max_expected_size <= 0:
        raise ValueError('El límite documental configurado no es válido.')
    if expected_size <= 0 or expected_size > max_expected_size:
        max_gb = max_expected_size / (1024 * 1024 * 1024)
        limit_label = f"{max_gb:g} GB"
        raise ValueError(f"El archivo debe pesar entre 1 byte y {limit_label}.")
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            INSERT INTO doc.SesionCargaGraph
                (SesionCargaGraphId, ExpedienteGraphId, TipoDocumentoCodigo,
                 EstadoDocumentoGraphCodigo, NombreArchivoOriginal, NombreArchivoNube,
                 RutaGraph, ContentType, TamanoEsperado, UploadUrlHash,
                 FechaExpiracionGraph, UsuarioCarga)
            VALUES (?, ?, ?, 'CARGA_INICIADA', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            str(session_id),
            expedient_graph_id,
            document_type_code,
            original_filename,
            cloud_filename,
            graph_path,
            content_type or "application/octet-stream",
            expected_size,
            hashlib.sha256(upload_url.encode("utf-8")).digest() if upload_url else None,
            _parse_graph_datetime(expires_at),
            audit_user,
        )
        cursor.execute(
            """
            INSERT INTO aud.AuditoriaGraph(EntidadTipo, EntidadId, Accion, Detalle, UsuarioAccion)
            VALUES('EXPEDIENTE_DOCUMENTAL', ?, 'INICIAR_CARGA', ?, ?)
            """,
            expedient_graph_id,
            f"Sesión {session_id}; archivo {original_filename}; {expected_size} bytes",
            audit_user,
        )
        conn.commit()


def upload_session(session_id: UUID | str) -> dict[str, Any] | None:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            SELECT
                S.SesionCargaGraphId, S.ExpedienteGraphId, S.DocumentoGraphId,
                S.TipoDocumentoCodigo, S.EstadoDocumentoGraphCodigo,
                S.NombreArchivoOriginal, S.NombreArchivoNube, S.RutaGraph,
                S.ContentType, S.TamanoEsperado, S.FechaExpiracionGraph,
                S.UsuarioCarga, E.TipoExpedienteGraphCodigo, E.NumeroIdentificacion,
                E.CodigoEstud, E.BaseOrigen, E.EsquemaOrigen, E.TablaOrigen, E.OrigenId
            FROM doc.SesionCargaGraph S
            INNER JOIN doc.ExpedienteGraph E ON E.ExpedienteGraphId = S.ExpedienteGraphId
            WHERE S.SesionCargaGraphId = ?
            """,
            str(session_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {column[0]: value for column, value in zip(cursor.description, row)}


def complete_upload_session(
    *,
    session_id: UUID | str,
    graph_item: dict[str, Any],
    edit_deadline: datetime | None,
    audit_user: str,
    append_document: bool = False,
) -> dict[str, Any]:
    graph_item_id = clean(graph_item.get("id"))
    graph_web_url = clean(graph_item.get("webUrl"))
    graph_drive_id = clean((graph_item.get("parentReference") or {}).get("driveId"))
    graph_etag = clean(graph_item.get("eTag"))
    graph_size = int(graph_item.get("size") or 0)
    mime_type = clean((graph_item.get("file") or {}).get("mimeType"))
    if not graph_item_id:
        raise ValueError("Microsoft Graph no devolvió el identificador del archivo.")

    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            SELECT ExpedienteGraphId, TipoDocumentoCodigo, EstadoDocumentoGraphCodigo,
                   NombreArchivoOriginal, RutaGraph, ContentType, TamanoEsperado,
                   DocumentoGraphId, GraphItemId
            FROM doc.SesionCargaGraph WITH (UPDLOCK, HOLDLOCK)
            WHERE SesionCargaGraphId = ?
            """,
            str(session_id),
        )
        session = cursor.fetchone()
        if not session:
            raise ValueError('No existe la sesión documental.')
        if session.DocumentoGraphId is not None:
            cursor.execute(
                """
                SELECT DocumentoGraphId, VersionActual, GraphItemId, GraphWebUrl,
                       TamanoBytes, ContentType
                FROM doc.DocumentoGraph WITH (UPDLOCK, HOLDLOCK)
                WHERE DocumentoGraphId = ? AND Activo = 1
                """,
                int(session.DocumentoGraphId),
            )
            completed = cursor.fetchone()
            if completed and clean(completed.GraphItemId) == graph_item_id:
                cursor.execute(
                    """
                    UPDATE doc.DocumentoGraph
                       SET EstadoDocumentoGraphCodigo = 'CARGADO',
                           GraphDriveId = COALESCE(NULLIF(?, N''), GraphDriveId),
                           GraphETag = COALESCE(NULLIF(?, N''), GraphETag),
                           GraphWebUrl = COALESCE(NULLIF(?, N''), GraphWebUrl),
                           FechaActualizacion = SYSUTCDATETIME(), UsuarioActualizacion = ?
                     WHERE DocumentoGraphId = ?
                    """,
                    graph_drive_id,
                    graph_etag,
                    graph_web_url,
                    audit_user,
                    int(completed.DocumentoGraphId),
                )
                cursor.execute(
                    """
                    UPDATE doc.DocumentoGraphVersion
                       SET EstadoDocumentoGraphCodigo = 'CARGADO'
                     WHERE DocumentoGraphId = ? AND NumeroVersion = ?
                    """,
                    int(completed.DocumentoGraphId),
                    int(completed.VersionActual),
                )
                cursor.execute(
                    """
                    UPDATE doc.SesionCargaGraph
                       SET EstadoDocumentoGraphCodigo = 'CARGADO', UltimoError = NULL,
                           FechaFin = SYSUTCDATETIME(), GraphWebUrl = COALESCE(NULLIF(?, N''), GraphWebUrl)
                     WHERE SesionCargaGraphId = ?
                    """,
                    graph_web_url,
                    str(session_id),
                )
                conn.commit()
                return {
                    "document_graph_id": int(completed.DocumentoGraphId),
                    "version": int(completed.VersionActual),
                    "graph_item_id": clean(completed.GraphItemId),
                    "graph_web_url": graph_web_url or clean(completed.GraphWebUrl),
                    "size": int(completed.TamanoBytes or 0),
                    "content_type": clean(completed.ContentType) or "application/octet-stream",
                }
        if graph_size != int(session.TamanoEsperado):
            raise ValueError('El tamaño confirmado por Microsoft Graph no coincide con la carga solicitada.')

        current = None
        if not append_document:
            cursor.execute(
                """
                SELECT TOP (1) DocumentoGraphId, VersionActual
                FROM doc.DocumentoGraph WITH (UPDLOCK, HOLDLOCK)
                WHERE ExpedienteGraphId = ? AND TipoDocumentoCodigo = ? AND Activo = 1
                ORDER BY DocumentoGraphId DESC
                """,
                int(session.ExpedienteGraphId),
                clean(session.TipoDocumentoCodigo),
            )
            current = cursor.fetchone()
        version = int(current.VersionActual or 0) + 1 if current else 1
        final_content_type = mime_type or clean(session.ContentType) or "application/octet-stream"
        if current:
            document_id = int(current.DocumentoGraphId)
            cursor.execute(
                """
                UPDATE doc.DocumentoGraph
                   SET EstadoDocumentoGraphCodigo = 'CARGADO', NombreArchivo = ?, ContentType = ?,
                       TamanoBytes = ?, VersionActual = ?, GraphDriveId = NULLIF(?, N''),
                       GraphItemId = ?, GraphETag = NULLIF(?, N''), GraphWebUrl = NULLIF(?, N''),
                       RutaGraph = ?, FechaLimiteEdicion = ?, FechaActualizacion = SYSUTCDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE DocumentoGraphId = ?
                """,
                clean(session.NombreArchivoOriginal),
                final_content_type,
                graph_size,
                version,
                graph_drive_id,
                graph_item_id,
                graph_etag,
                graph_web_url,
                clean(session.RutaGraph),
                edit_deadline,
                audit_user,
                document_id,
            )
        else:
            cursor.execute(
                """
                SET NOCOUNT ON;
                DECLARE @DocumentoResultado TABLE (DocumentoGraphId BIGINT NOT NULL);

                INSERT INTO doc.DocumentoGraph
                    (ExpedienteGraphId, TipoDocumentoCodigo, EstadoDocumentoGraphCodigo,
                     NombreArchivo, ContentType, TamanoBytes, VersionActual, GraphDriveId,
                     GraphItemId, GraphETag, GraphWebUrl, RutaGraph, FechaLimiteEdicion,
                     UsuarioCarga)
                OUTPUT INSERTED.DocumentoGraphId INTO @DocumentoResultado (DocumentoGraphId)
                VALUES (?, ?, 'CARGADO', ?, ?, ?, 1, NULLIF(?, N''), ?, NULLIF(?, N''),
                        NULLIF(?, N''), ?, ?, ?)

                SELECT TOP (1) DocumentoGraphId FROM @DocumentoResultado;
                """,
                int(session.ExpedienteGraphId),
                clean(session.TipoDocumentoCodigo),
                clean(session.NombreArchivoOriginal),
                final_content_type,
                graph_size,
                graph_drive_id,
                graph_item_id,
                graph_etag,
                graph_web_url,
                clean(session.RutaGraph),
                edit_deadline,
                audit_user,
            )
            document_id = int(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO doc.DocumentoGraphVersion
                (DocumentoGraphId, NumeroVersion, EstadoDocumentoGraphCodigo,
                 NombreArchivo, ContentType, TamanoBytes, GraphDriveId, GraphItemId,
                 GraphETag, GraphWebUrl, RutaGraph, UsuarioCarga)
            VALUES (?, ?, 'CARGADO', ?, ?, ?, NULLIF(?, N''), ?, NULLIF(?, N''),
                    NULLIF(?, N''), ?, ?)
            """,
            document_id,
            version,
            clean(session.NombreArchivoOriginal),
            final_content_type,
            graph_size,
            graph_drive_id,
            graph_item_id,
            graph_etag,
            graph_web_url,
            clean(session.RutaGraph),
            audit_user,
        )
        cursor.execute(
            """
            UPDATE doc.SesionCargaGraph
               SET DocumentoGraphId = ?, EstadoDocumentoGraphCodigo = 'CARGADO',
                   GraphItemId = ?, GraphWebUrl = NULLIF(?, N''), FechaFin = SYSUTCDATETIME(),
                   UltimoError = NULL
             WHERE SesionCargaGraphId = ?
            """,
            document_id,
            graph_item_id,
            graph_web_url,
            str(session_id),
        )
        cursor.execute(
            """
            INSERT INTO aud.AuditoriaGraph(EntidadTipo, EntidadId, Accion, Detalle, UsuarioAccion)
            VALUES('DOCUMENTO_EXPEDIENTE', ?, 'CARGA_COMPLETADA', ?, ?)
            """,
            document_id,
            f"Version {version}; GraphItemId {graph_item_id}; {graph_size} bytes",
            audit_user,
        )
        conn.commit()
    return {
        "document_graph_id": document_id,
        "version": version,
        "graph_item_id": graph_item_id,
        "graph_web_url": graph_web_url,
        "size": graph_size,
        "content_type": final_content_type,
    }


def set_document_origin(document_graph_id: int, origin_id: str | int) -> None:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            "UPDATE doc.DocumentoGraph SET DocumentoOrigenId = ?, FechaActualizacion = SYSUTCDATETIME() WHERE DocumentoGraphId = ?",
            str(origin_id),
            document_graph_id,
        )
        conn.commit()


def mark_upload_error(session_id: UUID | str, error: str, audit_user: str) -> None:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            SELECT DocumentoGraphId
            FROM doc.SesionCargaGraph WITH (UPDLOCK, HOLDLOCK)
            WHERE SesionCargaGraphId = ?
            """,
            str(session_id),
        )
        session = cursor.fetchone()
        cursor.execute(
            """
            UPDATE doc.SesionCargaGraph
               SET EstadoDocumentoGraphCodigo = 'ERROR', UltimoError = ?, FechaFin = SYSUTCDATETIME()
             WHERE SesionCargaGraphId = ?
            """,
            clean(error)[:2000],
            str(session_id),
        )
        if session and session.DocumentoGraphId is not None:
            document_id = int(session.DocumentoGraphId)
            cursor.execute(
                """
                UPDATE doc.DocumentoGraph
                   SET EstadoDocumentoGraphCodigo = 'ERROR', FechaActualizacion = SYSUTCDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE DocumentoGraphId = ? AND DocumentoOrigenId IS NULL
                """,
                audit_user,
                document_id,
            )
            cursor.execute(
                """
                UPDATE doc.DocumentoGraphVersion
                   SET EstadoDocumentoGraphCodigo = 'ERROR'
                 WHERE DocumentoGraphId = ?
                   AND NumeroVersion = (SELECT VersionActual FROM doc.DocumentoGraph WHERE DocumentoGraphId = ?)
                   AND NOT EXISTS (
                       SELECT 1 FROM doc.DocumentoGraph
                       WHERE DocumentoGraphId = ? AND DocumentoOrigenId IS NOT NULL
                   )
                """,
                document_id,
                document_id,
                document_id,
            )
        cursor.execute(
            """
            INSERT INTO aud.AuditoriaGraph(EntidadTipo, EntidadId, Accion, Detalle, UsuarioAccion)
            SELECT 'EXPEDIENTE_DOCUMENTAL', ExpedienteGraphId, 'ERROR_CARGA', ?, ?
            FROM doc.SesionCargaGraph WHERE SesionCargaGraphId = ?
            """,
            clean(error)[:2000],
            audit_user,
            str(session_id),
        )
        conn.commit()


def list_documents(identification: str) -> list[dict[str, Any]]:
    document = re.sub(r"\D+", "", identification)
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            SELECT
                E.ExpedienteGraphId, E.TipoExpedienteGraphCodigo, E.BaseOrigen,
                E.EsquemaOrigen, E.TablaOrigen, E.OrigenId, E.CodigoExpediente,
                E.RutaCarpeta, E.GraphWebUrl AS ExpedienteWebUrl,
                D.DocumentoGraphId, D.TipoDocumentoCodigo, D.DocumentoOrigenId,
                D.NombreArchivo, D.ContentType, D.TamanoBytes, D.VersionActual,
                D.EstadoDocumentoGraphCodigo, D.GraphItemId, D.GraphWebUrl,
                D.FechaCarga, D.UsuarioCarga
            FROM doc.ExpedienteGraph E
            LEFT JOIN doc.DocumentoGraph D
              ON D.ExpedienteGraphId = E.ExpedienteGraphId AND D.Activo = 1
            WHERE E.NumeroIdentificacion = ? AND E.Activo = 1
            ORDER BY E.TipoExpedienteGraphCodigo, D.FechaCarga DESC, D.DocumentoGraphId DESC
            """,
            document,
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def document_record(document_graph_id: int) -> dict[str, Any] | None:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        cursor.execute(
            """
            SELECT D.DocumentoGraphId, D.GraphItemId, D.GraphWebUrl, D.NombreArchivo,
                   D.ContentType, D.TamanoBytes, E.NumeroIdentificacion,
                   E.TipoExpedienteGraphCodigo
            FROM doc.DocumentoGraph D
            INNER JOIN doc.ExpedienteGraph E ON E.ExpedienteGraphId = D.ExpedienteGraphId
            WHERE D.DocumentoGraphId = ? AND D.Activo = 1
            """,
            document_graph_id,
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {column[0]: value for column, value in zip(cursor.description, row)}
