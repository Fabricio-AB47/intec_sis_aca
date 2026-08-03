from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.services.db import get_graph_database_connection
from app.services.graph import get_graph_token


MAX_DOCUMENT_BYTES = 1024 * 1024 * 1024
GRAPH_DOCUMENT_ROOT = "EXPEDIENTES ACADEMICOS"


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_filename(value: str, allowed_extensions: set[str] | None = None) -> str:
    filename = Path(value.replace("\\", "/")).name.strip()
    filename = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    if not filename:
        raise ValueError("El archivo no tiene un nombre valido.")
    extension = Path(filename).suffix.lower()
    if allowed_extensions is not None and extension not in allowed_extensions:
        raise ValueError(f"El formato {extension or 'sin extension'} no esta permitido.")
    return filename[:255]


def safe_folder_part(value: str, fallback: str = "expediente") -> str:
    normalized = re.sub(r"[^0-9A-Za-z._ -]+", "_", clean(value))
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    return (normalized or fallback)[:120]


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


def create_upload_session(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{_item_path_url(path)}:/createUploadSession",
            headers=_auth_headers(json_content=True),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        response.raise_for_status()
        return response.json()


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
        OUTPUT INSERTED.PersonaGraphRefId;
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
    if module not in {"INGLES", "TITULACION", "PRACTICAS", "VINCULACION"}:
        raise ValueError("Modulo documental no permitido.")
    if not document:
        raise ValueError("La identificacion del estudiante es obligatoria.")

    folder_path = "/".join(
        [
            GRAPH_DOCUMENT_ROOT,
            safe_folder_part(f"{student_code or 'SIN-CODIGO'}-{document}", document),
            module,
            safe_folder_part(str(origin_id), "expediente"),
        ]
    )
    folder_item = ensure_folder(folder_path)
    drive_id = clean((folder_item.get("parentReference") or {}).get("driveId"))
    owner = graph_owner_upn()

    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        _assert_schema(cursor)
        person_id = _ensure_person(
            cursor,
            identification=document,
            student_code=student_code,
            name=student_name,
            email=student_email,
        )
        cursor.execute(
            """
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
            OUTPUT INSERTED.ExpedienteGraphId;
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
            folder_path,
            audit_user,
        )
        conn.commit()

    return {
        "expedient_graph_id": expedient_id,
        "folder_path": folder_path,
        "folder_item_id": clean(folder_item.get("id")),
        "drive_id": drive_id,
        "web_url": clean(folder_item.get("webUrl")),
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
) -> None:
    if expected_size <= 0 or expected_size > MAX_DOCUMENT_BYTES:
        raise ValueError("El archivo debe pesar entre 1 byte y 1 GB.")
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
            f"Sesion {session_id}; archivo {original_filename}; {expected_size} bytes",
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
) -> dict[str, Any]:
    graph_item_id = clean(graph_item.get("id"))
    graph_web_url = clean(graph_item.get("webUrl"))
    graph_drive_id = clean((graph_item.get("parentReference") or {}).get("driveId"))
    graph_etag = clean(graph_item.get("eTag"))
    graph_size = int(graph_item.get("size") or 0)
    mime_type = clean((graph_item.get("file") or {}).get("mimeType"))
    if not graph_item_id:
        raise ValueError("Microsoft Graph no devolvio el identificador del archivo.")

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
            raise ValueError("No existe la sesion documental.")
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
            raise ValueError("El tamano confirmado por Microsoft Graph no coincide con la carga solicitada.")

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
                INSERT INTO doc.DocumentoGraph
                    (ExpedienteGraphId, TipoDocumentoCodigo, EstadoDocumentoGraphCodigo,
                     NombreArchivo, ContentType, TamanoBytes, VersionActual, GraphDriveId,
                     GraphItemId, GraphETag, GraphWebUrl, RutaGraph, FechaLimiteEdicion,
                     UsuarioCarga)
                OUTPUT INSERTED.DocumentoGraphId
                VALUES (?, ?, 'CARGADO', ?, ?, ?, 1, NULLIF(?, N''), ?, NULLIF(?, N''),
                        NULLIF(?, N''), ?, ?, ?)
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
