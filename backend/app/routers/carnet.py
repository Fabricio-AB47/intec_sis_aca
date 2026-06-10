from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pyodbc
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

from app.core.security import ALLOWED_ROLES, SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/carnet", tags=["carnet"])

_CARNET_ACCESS = require_roles(*ALLOWED_ROLES)
_CARNET_MANAGE_ACCESS = require_roles(
    "ADMINISTRADOR",
    "ACADEMICO",
    "ADMISIONES",
    "BIENESTAR",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
)
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
UPLOAD_ROOT = _BACKEND_ROOT / "uploads"
_CARNET_UPLOAD_ROOT = UPLOAD_ROOT / "carnet"
_LOGO_PATH = _PROJECT_ROOT / "frontend" / "public" / "Intec-Logowithslogangray.svg"
_PHOTO_MAX_BYTES = 8 * 1024 * 1024
_PHOTO_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_PERSON_TYPES = {"ESTUDIANTE", "DOCENTE", "ADMINISTRATIVO"}
_STUDENT_VALIDITY_MONTHS = 8
_STAFF_VALIDITY_MONTHS = 24


class CarnetPhotoReviewPayload(BaseModel):
    observacion: str | None = ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _int_value(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_filename(value: str) -> str:
    name = Path(value or "foto-carnet").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "foto-carnet"


def _photo_mime_type(filename: str, upload_mime: str | None = None) -> str:
    extension = Path(filename or "").suffix.lower()
    mime = _PHOTO_MIME_BY_EXTENSION.get(extension)
    if not mime:
        raise HTTPException(status_code=400, detail="Solo se permiten imagenes JPG, PNG o WEBP")
    if upload_mime and upload_mime not in {"application/octet-stream", mime} and not upload_mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo no parece ser una imagen valida")
    return mime


def _normalize_person_type(value: str) -> str:
    normalized = _clean(value).upper()
    if normalized not in _PERSON_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de persona no valido")
    return normalized


def _validity_months(person_type: str) -> int:
    return _STUDENT_VALIDITY_MONTHS if _normalize_person_type(person_type) == "ESTUDIANTE" else _STAFF_VALIDITY_MONTHS


def _date_payload(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    return text.split(".")[0]


def _sql_datetime_expr(value: str) -> str:
    return f"TRY_CONVERT(datetime2(0), {value})"


def _ensure_carnet_tables(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.CARNET_USUARIO_IMAGEN', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.CARNET_USUARIO_IMAGEN(
                id_imagen bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo_persona varchar(20) NOT NULL,
                codigo_persona varchar(50) NOT NULL,
                cedula varchar(30) NULL,
                nombre nvarchar(200) NULL,
                correo nvarchar(150) NULL,
                tipo_imagen varchar(30) NOT NULL,
                nombre_archivo nvarchar(260) NOT NULL,
                ruta_archivo nvarchar(500) NOT NULL,
                mime_type varchar(100) NOT NULL,
                tamano_bytes bigint NOT NULL,
                es_principal bit NOT NULL CONSTRAINT DF_CARNET_USUARIO_IMAGEN_principal DEFAULT ((0)),
                estado char(1) NOT NULL CONSTRAINT DF_CARNET_USUARIO_IMAGEN_estado DEFAULT ('A'),
                usuario_creacion nvarchar(100) NULL,
                fecha_creacion datetime2(0) NOT NULL CONSTRAINT DF_CARNET_USUARIO_IMAGEN_fecha DEFAULT (SYSDATETIME())
            )
        END

        IF OBJECT_ID(N'dbo.CARNET_USUARIO_FOTO_SOLICITUD', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.CARNET_USUARIO_FOTO_SOLICITUD(
                id_solicitud bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                id_imagen bigint NOT NULL,
                tipo_persona varchar(20) NOT NULL,
                codigo_persona varchar(50) NOT NULL,
                cedula varchar(30) NULL,
                nombre nvarchar(200) NULL,
                correo nvarchar(150) NULL,
                estado varchar(20) NOT NULL CONSTRAINT DF_CARNET_USUARIO_SOL_estado DEFAULT ('PENDIENTE'),
                observacion nvarchar(500) NULL,
                usuario_solicitud nvarchar(100) NULL,
                fecha_solicitud datetime2(0) NOT NULL CONSTRAINT DF_CARNET_USUARIO_SOL_fecha DEFAULT (SYSDATETIME()),
                usuario_revision nvarchar(100) NULL,
                fecha_revision datetime2(0) NULL,
                meses_vigencia int NULL,
                fecha_vigencia_hasta datetime2(0) NULL,
                carnet_emitido bit NOT NULL CONSTRAINT DF_CARNET_USUARIO_SOL_emitido DEFAULT ((0)),
                fecha_emision datetime2(0) NULL
            )
        END

        IF COL_LENGTH('dbo.CARNET_USUARIO_FOTO_SOLICITUD', 'meses_vigencia') IS NULL
            ALTER TABLE dbo.CARNET_USUARIO_FOTO_SOLICITUD ADD meses_vigencia int NULL

        IF COL_LENGTH('dbo.CARNET_USUARIO_FOTO_SOLICITUD', 'fecha_vigencia_hasta') IS NULL
            ALTER TABLE dbo.CARNET_USUARIO_FOTO_SOLICITUD ADD fecha_vigencia_hasta datetime2(0) NULL

        IF COL_LENGTH('dbo.CARNET_USUARIO_FOTO_SOLICITUD', 'carnet_emitido') IS NULL
            ALTER TABLE dbo.CARNET_USUARIO_FOTO_SOLICITUD ADD carnet_emitido bit NOT NULL CONSTRAINT DF_CARNET_USUARIO_SOL_emitido2 DEFAULT ((0))

        IF COL_LENGTH('dbo.CARNET_USUARIO_FOTO_SOLICITUD', 'fecha_emision') IS NULL
            ALTER TABLE dbo.CARNET_USUARIO_FOTO_SOLICITUD ADD fecha_emision datetime2(0) NULL

        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'IX_CARNET_USUARIO_SOL_persona'
              AND object_id = OBJECT_ID(N'dbo.CARNET_USUARIO_FOTO_SOLICITUD')
        )
        BEGIN
            CREATE INDEX IX_CARNET_USUARIO_SOL_persona
            ON dbo.CARNET_USUARIO_FOTO_SOLICITUD(tipo_persona, codigo_persona, estado, fecha_solicitud DESC)
        END
        """
    )


def _person_from_row(row: Any) -> dict[str, Any]:
    return {
        "tipo_persona": _clean(row.tipo_persona),
        "codigo_persona": _clean(row.codigo_persona),
        "cedula": _clean(row.cedula),
        "nombre": _clean(row.nombre),
        "correo": _clean(row.correo),
        "fuente": _clean(row.fuente),
    }


def _person_status_payload(cursor: pyodbc.Cursor, person: dict[str, Any]) -> dict[str, Any]:
    _ensure_carnet_tables(cursor)
    cursor.execute(
        """
        SELECT TOP (1)
            s.id_solicitud,
            s.estado,
            s.observacion,
            s.fecha_solicitud,
            s.fecha_revision,
            COALESCE(
                s.fecha_vigencia_hasta,
                CASE
                    WHEN s.estado = 'APROBADA' AND s.fecha_revision IS NOT NULL
                    THEN DATEADD(month, CASE WHEN s.tipo_persona = 'ESTUDIANTE' THEN ? ELSE ? END, s.fecha_revision)
                    ELSE NULL
                END
            ) AS fecha_vigencia_hasta,
            COALESCE(s.meses_vigencia, CASE WHEN s.tipo_persona = 'ESTUDIANTE' THEN ? ELSE ? END) AS meses_vigencia,
            ISNULL(s.carnet_emitido, 0) AS carnet_emitido,
            s.fecha_emision,
            img.id_imagen,
            img.nombre_archivo,
            img.ruta_archivo,
            img.mime_type,
            img.tamano_bytes,
            img.es_principal,
            img.fecha_creacion
        FROM dbo.CARNET_USUARIO_FOTO_SOLICITUD s
        INNER JOIN dbo.CARNET_USUARIO_IMAGEN img ON img.id_imagen = s.id_imagen
        WHERE s.tipo_persona = ?
          AND s.codigo_persona = ?
        ORDER BY
            CASE s.estado WHEN 'PENDIENTE' THEN 0 WHEN 'APROBADA' THEN 1 WHEN 'RECHAZADA' THEN 2 ELSE 3 END,
            s.fecha_solicitud DESC,
            s.id_solicitud DESC
        """,
        _STUDENT_VALIDITY_MONTHS,
        _STAFF_VALIDITY_MONTHS,
        _STUDENT_VALIDITY_MONTHS,
        _STAFF_VALIDITY_MONTHS,
        person["tipo_persona"],
        person["codigo_persona"],
    )
    row = cursor.fetchone()
    if not row:
        return {
            "persona": person,
            "estado": "SIN_FOTO",
            "mensaje": "No existe una foto de carnet cargada para aprobacion.",
            "puede_subir": True,
            "meses_vigencia": _validity_months(person["tipo_persona"]),
        }
    raw_status = _clean(row.estado) or "PENDIENTE"
    valid_until = getattr(row, "fecha_vigencia_hasta", None)
    is_approved = raw_status == "APROBADA"
    is_active = bool(is_approved and valid_until and valid_until >= datetime.now())
    status = "VENCIDA" if is_approved and not is_active else raw_status
    can_upload = raw_status in {"SIN_FOTO", "RECHAZADA", "CANCELADA"} or status == "VENCIDA"
    can_download = is_active
    return {
        "persona": person,
        "id_solicitud": _clean(row.id_solicitud),
        "id_imagen": _clean(row.id_imagen),
        "estado": status,
        "estado_revision": raw_status,
        "observacion": _clean(row.observacion),
        "foto_url": _clean(row.ruta_archivo),
        "nombre_archivo": _clean(row.nombre_archivo),
        "mime_type": _clean(row.mime_type),
        "tamano_bytes": _int_value(row.tamano_bytes),
        "es_principal": bool(row.es_principal),
        "fecha_solicitud": _date_payload(row.fecha_solicitud),
        "fecha_revision": _date_payload(row.fecha_revision),
        "fecha_creacion": _date_payload(row.fecha_creacion),
        "fecha_vigencia_hasta": _date_payload(valid_until),
        "fecha_emision": _date_payload(getattr(row, "fecha_emision", "")),
        "meses_vigencia": _int_value(getattr(row, "meses_vigencia", None)),
        "carnet_emitido": bool(getattr(row, "carnet_emitido", False)),
        "puede_subir": can_upload,
        "puede_descargar_carnet": can_download,
        "mensaje_vigencia": (
            f"Foto vigente hasta {_date_payload(valid_until)}. Podra solicitar actualizacion al vencer."
            if is_active
            else "La vigencia expiro. Puede cargar una nueva foto para revision."
            if status == "VENCIDA"
            else ""
        ),
    }


def _fetch_person(cursor: pyodbc.Cursor, person_type: str, code: str) -> dict[str, Any]:
    person_type = _normalize_person_type(person_type)
    code = _clean(code)
    if not code:
        raise HTTPException(status_code=400, detail="Codigo de persona requerido")

    if person_type == "ESTUDIANTE":
        cursor.execute(
            """
            SELECT TOP (1)
                'ESTUDIANTE' AS tipo_persona,
                TRY_CONVERT(varchar(50), ce.codestud) AS codigo_persona,
                TRY_CONVERT(varchar(30), de.Cedula_Est) AS cedula,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(200), ce.Nombres), N''), TRY_CONVERT(nvarchar(200), de.Apellidos_nombre)) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), ce.CorreoIntec), N''), TRY_CONVERT(nvarchar(150), de.correointec), TRY_CONVERT(nvarchar(150), ce.CorreoPersonal), TRY_CONVERT(nvarchar(150), de.correo)) AS correo,
                'CorreosEstudIntec' AS fuente
            FROM dbo.CorreosEstudIntec ce
            LEFT JOIN dbo.DATOS_ESTUD de
              ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, ce.codestud)
            WHERE TRY_CONVERT(varchar(50), ce.codestud) = ?
            """,
            code,
        )
    elif person_type == "DOCENTE":
        cursor.execute(
            """
            SELECT TOP (1)
                'DOCENTE' AS tipo_persona,
                TRY_CONVERT(varchar(50), COALESCE(d.codigo_doc, u.Codigo_Usuario)) AS codigo_persona,
                COALESCE(TRY_CONVERT(varchar(30), d.cedula_doc), TRY_CONVERT(varchar(30), u.cedula)) AS cedula,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(200), d.apellidos_nombre), N''), TRY_CONVERT(nvarchar(200), u.login)) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), d.correo), N''), TRY_CONVERT(nvarchar(150), d.correop), TRY_CONVERT(nvarchar(150), u.login)) AS correo,
                'USUARIOS' AS fuente
            FROM dbo.USUARIOS u
            LEFT JOIN dbo.DATOSDOCENTE d
              ON TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, u.Codigo_Usuario)
              OR TRY_CONVERT(nvarchar(50), d.cedula_doc) COLLATE SQL_Latin1_General_CP1_CI_AS =
                 TRY_CONVERT(nvarchar(50), u.cedula) COLLATE SQL_Latin1_General_CP1_CI_AS
            WHERE TRY_CONVERT(varchar(50), COALESCE(d.codigo_doc, u.Codigo_Usuario)) = ?
              AND COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1
            """,
            code,
        )
    else:
        cursor.execute(
            """
            SELECT TOP (1)
                'ADMINISTRATIVO' AS tipo_persona,
                TRY_CONVERT(varchar(50), us.id_usuarios) AS codigo_persona,
                TRY_CONVERT(varchar(30), us.login) AS cedula,
                TRY_CONVERT(nvarchar(200), us.nombres) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), us.email), N''), TRY_CONVERT(nvarchar(150), us.login)) AS correo,
                'USUARIO_SIS' AS fuente
            FROM dbo.USUARIO_SIS us
            WHERE TRY_CONVERT(varchar(50), us.id_usuarios) = ?
            """,
            code,
        )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontro la persona para carnet")
    return _person_from_row(row)


def _current_person(cursor: pyodbc.Cursor, current_user: SessionUser) -> dict[str, Any]:
    if current_user.rol == "ESTUDIANTE" and current_user.codigo_estud is not None:
        return _fetch_person(cursor, "ESTUDIANTE", str(current_user.codigo_estud))
    if current_user.rol == "DOCENTE" and current_user.codigo_doc is not None:
        return _fetch_person(cursor, "DOCENTE", str(current_user.codigo_doc))
    if current_user.id_usuario is not None:
        return _fetch_person(cursor, "ADMINISTRATIVO", str(current_user.id_usuario))
    raise HTTPException(status_code=404, detail="La sesion no tiene una persona vinculada para carnet")


def _search_people(cursor: pyodbc.Cursor, query: str, person_type: str, limit: int) -> list[dict[str, Any]]:
    text = f"%{_clean(query)}%"
    limit = min(max(limit, 1), 100)
    filters = _normalize_person_type(person_type) if person_type and person_type != "TODOS" else ""
    results: list[dict[str, Any]] = []

    if not filters or filters == "ESTUDIANTE":
        cursor.execute(
            f"""
            SELECT TOP ({limit})
                'ESTUDIANTE' AS tipo_persona,
                TRY_CONVERT(varchar(50), ce.codestud) AS codigo_persona,
                TRY_CONVERT(varchar(30), de.Cedula_Est) AS cedula,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(200), ce.Nombres), N''), TRY_CONVERT(nvarchar(200), de.Apellidos_nombre)) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), ce.CorreoIntec), N''), TRY_CONVERT(nvarchar(150), de.correointec), TRY_CONVERT(nvarchar(150), ce.CorreoPersonal), TRY_CONVERT(nvarchar(150), de.correo)) AS correo,
                'CorreosEstudIntec' AS fuente
            FROM dbo.CorreosEstudIntec ce
            LEFT JOIN dbo.DATOS_ESTUD de ON TRY_CONVERT(int, de.codigo_estud) = TRY_CONVERT(int, ce.codestud)
            WHERE ? = '%%'
               OR TRY_CONVERT(varchar(50), ce.codestud) LIKE ?
               OR TRY_CONVERT(varchar(30), de.Cedula_Est) LIKE ?
               OR TRY_CONVERT(nvarchar(200), ce.Nombres) LIKE ?
               OR TRY_CONVERT(nvarchar(200), de.Apellidos_nombre) LIKE ?
               OR TRY_CONVERT(nvarchar(150), ce.CorreoIntec) LIKE ?
            ORDER BY nombre
            """,
            text,
            text,
            text,
            text,
            text,
            text,
        )
        results.extend(_person_from_row(row) for row in cursor.fetchall())

    if not filters or filters == "DOCENTE":
        cursor.execute(
            f"""
            SELECT TOP ({limit})
                'DOCENTE' AS tipo_persona,
                TRY_CONVERT(varchar(50), COALESCE(d.codigo_doc, u.Codigo_Usuario)) AS codigo_persona,
                COALESCE(TRY_CONVERT(varchar(30), d.cedula_doc), TRY_CONVERT(varchar(30), u.cedula)) AS cedula,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(200), d.apellidos_nombre), N''), TRY_CONVERT(nvarchar(200), u.login)) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), d.correo), N''), TRY_CONVERT(nvarchar(150), d.correop), TRY_CONVERT(nvarchar(150), u.login)) AS correo,
                'USUARIOS' AS fuente
            FROM dbo.USUARIOS u
            LEFT JOIN dbo.DATOSDOCENTE d
              ON TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, u.Codigo_Usuario)
              OR TRY_CONVERT(nvarchar(50), d.cedula_doc) COLLATE SQL_Latin1_General_CP1_CI_AS =
                 TRY_CONVERT(nvarchar(50), u.cedula) COLLATE SQL_Latin1_General_CP1_CI_AS
            WHERE COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1
              AND (
                  ? = '%%'
               OR TRY_CONVERT(varchar(50), COALESCE(d.codigo_doc, u.Codigo_Usuario)) LIKE ?
               OR TRY_CONVERT(varchar(30), COALESCE(d.cedula_doc, u.cedula)) LIKE ?
               OR TRY_CONVERT(nvarchar(200), d.apellidos_nombre) LIKE ?
               OR TRY_CONVERT(nvarchar(150), u.login) LIKE ?
              )
            ORDER BY nombre
            """,
            text,
            text,
            text,
            text,
            text,
        )
        results.extend(_person_from_row(row) for row in cursor.fetchall())

    if not filters or filters == "ADMINISTRATIVO":
        cursor.execute(
            f"""
            SELECT TOP ({limit})
                'ADMINISTRATIVO' AS tipo_persona,
                TRY_CONVERT(varchar(50), us.id_usuarios) AS codigo_persona,
                TRY_CONVERT(varchar(30), us.login) AS cedula,
                TRY_CONVERT(nvarchar(200), us.nombres) AS nombre,
                COALESCE(NULLIF(TRY_CONVERT(nvarchar(150), us.email), N''), TRY_CONVERT(nvarchar(150), us.login)) AS correo,
                'USUARIO_SIS' AS fuente
            FROM dbo.USUARIO_SIS us
            WHERE ? = '%%'
               OR TRY_CONVERT(varchar(50), us.id_usuarios) LIKE ?
               OR TRY_CONVERT(varchar(30), us.login) LIKE ?
               OR TRY_CONVERT(nvarchar(200), us.nombres) LIKE ?
               OR TRY_CONVERT(nvarchar(150), us.email) LIKE ?
            ORDER BY nombre
            """,
            text,
            text,
            text,
            text,
            text,
        )
        results.extend(_person_from_row(row) for row in cursor.fetchall())

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in results:
        key = (item["tipo_persona"], item["codigo_persona"])
        if item["codigo_persona"] and key not in unique:
            unique[key] = item
    return list(unique.values())[:limit]


def _active_approved_photo(cursor: pyodbc.Cursor, person: dict[str, Any]) -> Any | None:
    cursor.execute(
        """
        SELECT TOP (1)
            id_solicitud,
            fecha_revision,
            COALESCE(
                fecha_vigencia_hasta,
                CASE
                    WHEN fecha_revision IS NOT NULL
                    THEN DATEADD(month, CASE WHEN tipo_persona = 'ESTUDIANTE' THEN ? ELSE ? END, fecha_revision)
                    ELSE NULL
                END
            ) AS fecha_vigencia_hasta
        FROM dbo.CARNET_USUARIO_FOTO_SOLICITUD
        WHERE tipo_persona = ?
          AND codigo_persona = ?
          AND estado = 'APROBADA'
        ORDER BY fecha_revision DESC, id_solicitud DESC
        """,
        _STUDENT_VALIDITY_MONTHS,
        _STAFF_VALIDITY_MONTHS,
        person["tipo_persona"],
        person["codigo_persona"],
    )
    row = cursor.fetchone()
    if row and getattr(row, "fecha_vigencia_hasta", None) and row.fecha_vigencia_hasta >= datetime.now():
        return row
    return None


def _assert_can_upload_photo(cursor: pyodbc.Cursor, person: dict[str, Any]) -> None:
    active = _active_approved_photo(cursor, person)
    if active:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ya existe una foto aprobada vigente hasta "
                f"{_date_payload(active.fecha_vigencia_hasta)}. "
                "Debe esperar al vencimiento para solicitar una nueva actualizacion."
            ),
        )


def _save_uploaded_photo(
    cursor: pyodbc.Cursor,
    person: dict[str, Any],
    file_bytes: bytes,
    original_name: str,
    mime_type: str,
    login: str,
) -> dict[str, Any]:
    _ensure_carnet_tables(cursor)
    _assert_can_upload_photo(cursor, person)
    target_dir = _CARNET_UPLOAD_ROOT / person["tipo_persona"].lower() / _safe_filename(person["codigo_persona"])
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"foto-carnet-{datetime.now().strftime('%Y%m%d%H%M%S')}-{_safe_filename(original_name)}"
    target_path = target_dir / target_name
    target_path.write_bytes(file_bytes)
    relative_url = f"/uploads/carnet/{person['tipo_persona'].lower()}/{_safe_filename(person['codigo_persona'])}/{target_name}"

    cursor.execute(
        """
        SELECT id_solicitud, id_imagen
        FROM dbo.CARNET_USUARIO_FOTO_SOLICITUD
        WHERE tipo_persona = ?
          AND codigo_persona = ?
          AND estado = 'PENDIENTE'
        """,
        person["tipo_persona"],
        person["codigo_persona"],
    )
    pending_rows = cursor.fetchall()
    for row in pending_rows:
        cursor.execute(
            """
            UPDATE dbo.CARNET_USUARIO_IMAGEN
            SET estado = 'I'
            WHERE id_imagen = ?
            """,
            row.id_imagen,
        )
        cursor.execute(
            """
            UPDATE dbo.CARNET_USUARIO_FOTO_SOLICITUD
            SET estado = 'CANCELADA',
                observacion = COALESCE(observacion, N'') + CASE WHEN observacion IS NULL OR observacion = N'' THEN N'' ELSE N' | ' END + N'Reemplazada por nueva foto',
                usuario_revision = ?,
                fecha_revision = SYSDATETIME()
            WHERE id_solicitud = ?
            """,
            login,
            row.id_solicitud,
        )

    cursor.execute(
        """
        INSERT INTO dbo.CARNET_USUARIO_IMAGEN (
            tipo_persona, codigo_persona, cedula, nombre, correo, tipo_imagen,
            nombre_archivo, ruta_archivo, mime_type, tamano_bytes, es_principal, estado, usuario_creacion
        )
        OUTPUT INSERTED.id_imagen
        VALUES (?, ?, ?, ?, ?, 'FOTO_CARNET', ?, ?, ?, ?, 0, 'A', ?)
        """,
        person["tipo_persona"],
        person["codigo_persona"],
        person.get("cedula"),
        person.get("nombre"),
        person.get("correo"),
        target_name,
        relative_url,
        mime_type,
        len(file_bytes),
        login,
    )
    image_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO dbo.CARNET_USUARIO_FOTO_SOLICITUD (
            id_imagen, tipo_persona, codigo_persona, cedula, nombre, correo, estado, observacion, usuario_solicitud
        )
        VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', N'Foto de carnet pendiente de aprobacion', ?)
        """,
        image_id,
        person["tipo_persona"],
        person["codigo_persona"],
        person.get("cedula"),
        person.get("nombre"),
        person.get("correo"),
        login,
    )
    return _person_status_payload(cursor, person)


async def _read_photo_file(file: UploadFile) -> tuple[bytes, str, str]:
    original_name = _safe_filename(file.filename or "foto-carnet")
    mime_type = _photo_mime_type(original_name, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="La imagen esta vacia")
    if len(data) > _PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="La imagen no debe superar 8 MB")
    return data, original_name, mime_type


def _upload_url_to_path(url: str) -> Path | None:
    clean_url = _clean(url)
    if not clean_url.startswith("/uploads/"):
        return None
    relative = clean_url.replace("/uploads/", "", 1).replace("/", "\\")
    path = (UPLOAD_ROOT / relative).resolve()
    try:
        path.relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return None
    return path if path.exists() else None


def _draw_logo(canvas: Any, x: float, y: float, width: float, height: float) -> None:
    if not _LOGO_PATH.exists():
        return
    try:
        drawing = svg2rlg(str(_LOGO_PATH))
        if drawing:
            scale = min(width / max(drawing.width, 1), height / max(drawing.height, 1))
            drawing.scale(scale, scale)
            renderPDF.draw(drawing, canvas, x, y)
            return
    except Exception:
        pass
    try:
        canvas.drawImage(ImageReader(str(_LOGO_PATH)), x, y, width=width, height=height, mask="auto")
    except Exception:
        return


def _build_carnet_pdf(status: dict[str, Any]) -> bytes:
    person = status.get("persona") or {}
    output = BytesIO()
    page_width, page_height = A4
    card_width = 8.6 * cm
    card_height = 5.4 * cm
    x = (page_width - card_width) / 2
    y = page_height - card_height - 3 * cm
    canvas = pdf_canvas.Canvas(output, pagesize=A4)

    rojo = colors.HexColor("#931913")
    celeste = colors.HexColor("#8DBBC7")
    gris = colors.HexColor("#C7C6C6")
    gris_oscuro = colors.HexColor("#777777")
    azul = colors.HexColor("#071B46")

    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    canvas.setFillColor(rojo)
    canvas.rect(x, y + card_height - 0.32 * cm, card_width, 0.32 * cm, stroke=0, fill=1)
    canvas.setStrokeColor(gris)
    canvas.setLineWidth(1)
    canvas.roundRect(x, y, card_width, card_height, 10, stroke=1, fill=0)
    _draw_logo(canvas, x + 0.35 * cm, y + card_height - 1.55 * cm, 3.1 * cm, 1.05 * cm)

    photo_path = _upload_url_to_path(status.get("foto_url", ""))
    photo_x = x + 0.38 * cm
    photo_y = y + 0.72 * cm
    photo_w = 2.25 * cm
    photo_h = 2.65 * cm
    canvas.setFillColor(colors.HexColor("#F4F8FA"))
    canvas.roundRect(photo_x, photo_y, photo_w, photo_h, 7, stroke=0, fill=1)
    if photo_path:
        try:
            canvas.drawImage(ImageReader(str(photo_path)), photo_x, photo_y, width=photo_w, height=photo_h, mask="auto")
        except Exception:
            pass

    canvas.setFillColor(azul)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(x + 3.0 * cm, y + card_height - 1.15 * cm, "CARNET INSTITUCIONAL")
    canvas.setFillColor(rojo)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(x + 3.0 * cm, y + card_height - 1.55 * cm, _clean(person.get("tipo_persona")) or "INTEC")

    name = _clean(person.get("nombre")).upper()
    cedula = _clean(person.get("cedula"))
    codigo = _clean(person.get("codigo_persona"))
    correo = _clean(person.get("correo"))
    valid_until = _date_payload(status.get("fecha_vigencia_hasta"))

    text_x = x + 3.0 * cm
    text_y = y + 3.0 * cm
    canvas.setFillColor(azul)
    canvas.setFont("Helvetica-Bold", 8)
    for index, line in enumerate(re.findall(r".{1,32}(?:\s|$)", name)[:3] or [name[:32]]):
        canvas.drawString(text_x, text_y - index * 0.34 * cm, line.strip())
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(gris_oscuro)
    canvas.drawString(text_x, y + 1.65 * cm, f"Cedula/Login: {cedula or '-'}")
    canvas.drawString(text_x, y + 1.30 * cm, f"Codigo: {codigo or '-'}")
    canvas.drawString(text_x, y + 0.95 * cm, f"Correo: {correo[:36] or '-'}")
    canvas.setFillColor(celeste)
    canvas.rect(x, y, card_width, 0.46 * cm, stroke=0, fill=1)
    canvas.setFillColor(azul)
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.drawString(x + 0.35 * cm, y + 0.16 * cm, f"Vigente hasta: {valid_until or '-'}")
    canvas.save()
    return output.getvalue()


def _carnet_pdf_response(cursor: pyodbc.Cursor, person: dict[str, Any], login: str) -> StreamingResponse:
    status = _person_status_payload(cursor, person)
    if not status.get("puede_descargar_carnet"):
        raise HTTPException(status_code=400, detail="El carnet solo se puede generar con una foto aprobada y vigente.")
    pdf_bytes = _build_carnet_pdf(status)
    cursor.execute(
        """
        UPDATE dbo.CARNET_USUARIO_FOTO_SOLICITUD
        SET carnet_emitido = 1,
            fecha_emision = COALESCE(fecha_emision, SYSDATETIME()),
            observacion = COALESCE(NULLIF(observacion, N''), N'Foto aprobada para carnet')
        WHERE id_solicitud = ?
        """,
        status.get("id_solicitud"),
    )
    filename = f"carnet-{_safe_filename(person.get('tipo_persona', 'usuario'))}-{_safe_filename(person.get('cedula') or person.get('codigo_persona') or login)}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/me")
def get_my_carnet_status(current_user: Annotated[SessionUser, Depends(_CARNET_ACCESS)]) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _current_person(cursor, current_user)
            return _person_status_payload(cursor, person)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando carnet: {exc}") from exc


@router.post("/me/foto")
async def upload_my_carnet_photo(
    current_user: Annotated[SessionUser, Depends(_CARNET_ACCESS)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    data, original_name, mime_type = await _read_photo_file(file)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _current_person(cursor, current_user)
            status = _save_uploaded_photo(cursor, person, data, original_name, mime_type, current_user.login)
            conn.commit()
            return {"ok": True, "message": "Foto cargada. Queda pendiente de aprobacion.", "foto": status}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error subiendo foto de carnet: {exc}") from exc


@router.get("/me/pdf")
def download_my_carnet_pdf(current_user: Annotated[SessionUser, Depends(_CARNET_ACCESS)]) -> StreamingResponse:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _current_person(cursor, current_user)
            response = _carnet_pdf_response(cursor, person, current_user.login)
            conn.commit()
            return response
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando carnet: {exc}") from exc


@router.get("/personas")
def search_carnet_people(
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
    q: Annotated[str, Query(description="Cedula, codigo, nombre o correo")] = "",
    tipo: Annotated[str, Query(description="TODOS, ESTUDIANTE, DOCENTE o ADMINISTRATIVO")] = "TODOS",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    _ = current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            people = _search_people(cursor, q, tipo, limit)
            items = []
            for person in people:
                status = _person_status_payload(cursor, person)
                items.append({**person, "foto": status})
            return {"total": len(items), "items": items}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error buscando personas para carnet: {exc}") from exc


@router.get("/personas/{tipo_persona}/{codigo_persona}/foto")
def get_person_carnet_photo(
    tipo_persona: str,
    codigo_persona: str,
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
) -> dict[str, Any]:
    _ = current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _fetch_person(cursor, tipo_persona, codigo_persona)
            return _person_status_payload(cursor, person)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando foto de carnet: {exc}") from exc


@router.post("/personas/{tipo_persona}/{codigo_persona}/foto")
async def upload_person_carnet_photo(
    tipo_persona: str,
    codigo_persona: str,
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    data, original_name, mime_type = await _read_photo_file(file)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _fetch_person(cursor, tipo_persona, codigo_persona)
            status = _save_uploaded_photo(cursor, person, data, original_name, mime_type, current_user.login)
            conn.commit()
            return {"ok": True, "message": "Foto cargada. Queda pendiente de aprobacion.", "foto": status}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error subiendo foto de carnet: {exc}") from exc


@router.get("/personas/{tipo_persona}/{codigo_persona}/pdf")
def download_person_carnet_pdf(
    tipo_persona: str,
    codigo_persona: str,
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
) -> StreamingResponse:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            person = _fetch_person(cursor, tipo_persona, codigo_persona)
            response = _carnet_pdf_response(cursor, person, current_user.login)
            conn.commit()
            return response
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error generando carnet: {exc}") from exc


@router.post("/solicitudes/{request_id}/aprobar")
def approve_carnet_photo(
    request_id: int,
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _ensure_carnet_tables(cursor)
            cursor.execute(
                """
                SELECT id_imagen, tipo_persona, codigo_persona
                FROM dbo.CARNET_USUARIO_FOTO_SOLICITUD
                WHERE id_solicitud = ?
                """,
                request_id,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontro la solicitud de foto")
            person = _fetch_person(cursor, _clean(row.tipo_persona), _clean(row.codigo_persona))
            months = _validity_months(person["tipo_persona"])
            cursor.execute(
                """
                UPDATE dbo.CARNET_USUARIO_IMAGEN
                SET es_principal = 0
                WHERE tipo_persona = ?
                  AND codigo_persona = ?
                  AND tipo_imagen = 'FOTO_CARNET'
                """,
                person["tipo_persona"],
                person["codigo_persona"],
            )
            cursor.execute(
                """
                UPDATE dbo.CARNET_USUARIO_IMAGEN
                SET es_principal = 1,
                    estado = 'A'
                WHERE id_imagen = ?
                """,
                row.id_imagen,
            )
            cursor.execute(
                """
                UPDATE dbo.CARNET_USUARIO_FOTO_SOLICITUD
                SET estado = 'APROBADA',
                    observacion = N'Foto aprobada para carnet',
                    meses_vigencia = ?,
                    fecha_vigencia_hasta = DATEADD(month, ?, SYSDATETIME()),
                    usuario_revision = ?,
                    fecha_revision = SYSDATETIME()
                WHERE id_solicitud = ?
                """,
                months,
                months,
                current_user.login,
                request_id,
            )
            conn.commit()
            return {"ok": True, "message": "Foto aprobada para carnet.", "foto": _person_status_payload(cursor, person)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error aprobando foto de carnet: {exc}") from exc


@router.post("/solicitudes/{request_id}/rechazar")
def reject_carnet_photo(
    request_id: int,
    payload: CarnetPhotoReviewPayload,
    current_user: Annotated[SessionUser, Depends(_CARNET_MANAGE_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _ensure_carnet_tables(cursor)
            cursor.execute(
                """
                SELECT id_imagen, tipo_persona, codigo_persona
                FROM dbo.CARNET_USUARIO_FOTO_SOLICITUD
                WHERE id_solicitud = ?
                """,
                request_id,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No se encontro la solicitud de foto")
            person = _fetch_person(cursor, _clean(row.tipo_persona), _clean(row.codigo_persona))
            cursor.execute(
                """
                UPDATE dbo.CARNET_USUARIO_IMAGEN
                SET estado = 'I',
                    es_principal = 0
                WHERE id_imagen = ?
                """,
                row.id_imagen,
            )
            cursor.execute(
                """
                UPDATE dbo.CARNET_USUARIO_FOTO_SOLICITUD
                SET estado = 'RECHAZADA',
                    observacion = ?,
                    usuario_revision = ?,
                    fecha_revision = SYSDATETIME()
                WHERE id_solicitud = ?
                """,
                _clean(payload.observacion) or "Foto rechazada",
                current_user.login,
                request_id,
            )
            conn.commit()
            return {"ok": True, "message": "Foto rechazada.", "foto": _person_status_payload(cursor, person)}
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Error rechazando foto de carnet: {exc}") from exc
