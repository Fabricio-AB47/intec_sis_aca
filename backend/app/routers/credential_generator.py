from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import SessionUser, require_roles
from app.services.db import get_connection
from app.services.graph import graph_get, graph_patch, graph_post

router = APIRouter(prefix="/api/admin/credenciales", tags=["credenciales"])

AdminOnly = Depends(require_roles("ADMINISTRADOR"))

DEFAULT_TRAINING_LINK = (
    "https://intececu-my.sharepoint.com/:v:/g/personal/fabricio_borja_intec_edu_ec/"
    "EVtqmA6h3pFKmjR-ZtZgZkQBtAPZ3WeHY4t8VjiVPeliig?e=HU7DHT"
)

DEFAULT_MESSAGE_TEMPLATE = """Estimado/a {primer_nombre} {primer_apellido},

Se han creado sus credenciales Microsoft para el curso {curso}.

Usuario: {usuario}
Clave temporal: {clave}

Revise el siguiente enlace de induccion:
{link}

Saludos,
INTEC"""


class CredentialCourse(BaseModel):
    cod_curso: str
    curso: str
    estado: str | None = None
    fecha_inicio: str | None = None
    fecha_final: str | None = None
    source: str | None = None
    codigo_materia: str | None = None
    cod_materia: str | None = None
    carrera: str | None = None
    semestre: str | None = None


class CredentialUserPayload(BaseModel):
    primer_nombre: str = Field(min_length=1, max_length=60)
    segundo_nombre: str | None = Field(default="", max_length=60)
    primer_apellido: str = Field(min_length=1, max_length=60)
    segundo_apellido: str | None = Field(default="", max_length=60)
    cedula: str = Field(min_length=5, max_length=20)
    correo_electronico: str = Field(min_length=5, max_length=150)
    correo_enviado: bool = False


class CredentialBulkPayload(BaseModel):
    cod_curso: str = Field(min_length=1, max_length=50)
    curso: str = Field(min_length=1, max_length=200)
    mensaje: str = Field(min_length=1, max_length=4000)
    link: str = Field(default=DEFAULT_TRAINING_LINK, max_length=600)
    enviar_correo: bool = False
    usuarios: list[CredentialUserPayload] = Field(min_length=1, max_length=300)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _ensure_table(cursor: Any) -> None:
    cursor.execute(
        """
        IF OBJECT_ID('dbo.CREDENCIALES_CURSO', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.CREDENCIALES_CURSO (
                id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CREDENCIALES_CURSO PRIMARY KEY,
                cod_curso NVARCHAR(50) NOT NULL,
                curso NVARCHAR(200) NOT NULL,
                primer_nombre NVARCHAR(60) NOT NULL,
                segundo_nombre NVARCHAR(60) NULL,
                primer_apellido NVARCHAR(60) NOT NULL,
                segundo_apellido NVARCHAR(60) NULL,
                cedula VARCHAR(20) NOT NULL,
                correo_electronico VARCHAR(150) NOT NULL,
                usuario_generado VARCHAR(150) NOT NULL,
                clave_temporal VARCHAR(80) NOT NULL,
                graph_user_id NVARCHAR(80) NULL,
                graph_user_principal_name NVARCHAR(150) NULL,
                graph_mail_sender NVARCHAR(150) NULL,
                estado_graph VARCHAR(60) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_estado_graph DEFAULT ('PENDIENTE_GRAPH'),
                error_graph NVARCHAR(1000) NULL,
                mensaje_enviado NVARCHAR(MAX) NULL,
                link_induccion VARCHAR(600) NOT NULL,
                correo_enviado BIT NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_correo_enviado DEFAULT (0),
                estado_envio VARCHAR(40) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_estado_envio DEFAULT ('PENDIENTE'),
                error_envio NVARCHAR(1000) NULL,
                fecha_creacion DATETIME2(0) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_fecha_creacion DEFAULT (SYSDATETIME()),
                usuario_creacion VARCHAR(100) NULL,
                fecha_graph DATETIME2(0) NULL,
                fecha_envio DATETIME2(0) NULL,
                fecha_actualizacion DATETIME2(0) NULL
            );

            CREATE UNIQUE INDEX UX_CREDENCIALES_CURSO_cedula_curso
                ON dbo.CREDENCIALES_CURSO (cedula, cod_curso);
        END
        """
    )
    cursor.execute(
        """
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_user_id') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_user_id NVARCHAR(80) NULL;
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_user_principal_name') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_user_principal_name NVARCHAR(150) NULL;
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_mail_sender') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_mail_sender NVARCHAR(150) NULL;
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'estado_graph') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD estado_graph VARCHAR(60) NOT NULL
                CONSTRAINT DF_CREDENCIALES_CURSO_estado_graph DEFAULT ('PENDIENTE_GRAPH') WITH VALUES;
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'error_graph') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD error_graph NVARCHAR(1000) NULL;
        IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'fecha_graph') IS NULL
            ALTER TABLE dbo.CREDENCIALES_CURSO ADD fecha_graph DATETIME2(0) NULL;
        """
    )


def _normalize_ascii(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    ascii_value = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-zA-Z0-9._-]+", "", ascii_value).lower()


def _generate_username(user: CredentialUserPayload) -> str:
    domain = _graph_user_domain()
    local_part = _generate_mail_nickname(user)
    return f"{local_part}@{domain}"[:150]


def _generate_mail_nickname(user: CredentialUserPayload) -> str:
    base = _normalize_ascii(
        ".".join(
            part
            for part in (
                _clean(user.primer_nombre),
                _clean(user.primer_apellido),
                re.sub(r"\D+", "", user.cedula),
            )
            if part
        )
    )
    if len(base) < 3:
        base = f"usuario.{secrets.token_hex(3)}"
    return base[:64].strip(".-_") or f"usuario.{secrets.token_hex(3)}"


def _generate_password() -> str:
    groups = [
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "@#%*-_",
    ]
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(10))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _render_message(template: str, user: CredentialUserPayload, curso: str, usuario: str, clave: str, link: str) -> str:
    values = {
        "primer_nombre": _clean(user.primer_nombre),
        "segundo_nombre": _clean(user.segundo_nombre),
        "primer_apellido": _clean(user.primer_apellido),
        "segundo_apellido": _clean(user.segundo_apellido),
        "cedula": _clean(user.cedula),
        "correo": _clean(user.correo_electronico),
        "curso": curso,
        "usuario": usuario,
        "clave": clave,
        "link": link,
    }
    try:
        message = template.format(**values)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variable no valida en el mensaje: {exc.args[0]}",
        ) from exc
    if link not in message:
        message = f"{message.rstrip()}\n\nEnlace de induccion:\n{link}"
    return message


def _graph_user_domain() -> str:
    settings = get_settings()
    domain = _clean(settings.graph_user_domain).lower().lstrip("@")
    if not domain:
        raise RuntimeError("Define GRAPH_USER_DOMAIN en .env para crear usuarios en Microsoft Graph.")
    return domain


def _graph_mail_sender() -> str:
    settings = get_settings()
    sender = _clean(settings.graph_mail_sender)
    if not sender:
        raise RuntimeError("Define GRAPH_MAIL_SENDER en .env para enviar correos con Microsoft Graph.")
    return sender


def _graph_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        payload = exc.response.json()
    except ValueError:
        return exc.response.text or str(exc)

    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            code = _clean(error_payload.get("code"))
            message = _clean(error_payload.get("message"))
            return f"{code}: {message}" if code else message
    return str(payload)


def _graph_get_user(user_principal_name: str) -> dict[str, Any] | None:
    encoded_user = quote(user_principal_name, safe="")
    try:
        return graph_get(
            "https://graph.microsoft.com/v1.0/users/"
            f"{encoded_user}?$select=id,displayName,mail,userPrincipalName"
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def _create_or_update_graph_user(
    user: CredentialUserPayload,
    user_principal_name: str,
    password: str,
) -> tuple[dict[str, Any] | None, str, str | None]:
    display_name = " ".join(
        part
        for part in (
            _clean(user.primer_nombre),
            _clean(user.segundo_nombre),
            _clean(user.primer_apellido),
            _clean(user.segundo_apellido),
        )
        if part
    )
    mail_nickname = user_principal_name.split("@", 1)[0]
    payload = {
        "accountEnabled": True,
        "displayName": display_name,
        "mailNickname": mail_nickname,
        "userPrincipalName": user_principal_name,
        "passwordProfile": {
            "forceChangePasswordNextSignIn": True,
            "password": password,
        },
    }

    try:
        created = graph_post("https://graph.microsoft.com/v1.0/users", payload)
        return created, "CREADO_GRAPH", None
    except httpx.HTTPStatusError as exc:
        existing = _graph_get_user(user_principal_name)
        if not existing:
            return None, "ERROR_GRAPH", _graph_error_detail(exc)

        try:
            graph_patch(
                f"https://graph.microsoft.com/v1.0/users/{quote(str(existing.get('id') or user_principal_name), safe='')}",
                {
                    "displayName": display_name,
                    "passwordProfile": {
                        "forceChangePasswordNextSignIn": True,
                        "password": password,
                    },
                },
            )
            refreshed = _graph_get_user(user_principal_name) or existing
            return refreshed, "ACTUALIZADO_GRAPH", None
        except httpx.HTTPStatusError as update_exc:
            return existing, "ERROR_GRAPH", _graph_error_detail(update_exc)


def _send_graph_email(to_email: str, subject: str, body: str) -> tuple[bool, str | None, str | None]:
    sender = _graph_mail_sender()
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                    }
                }
            ],
        },
        "saveToSentItems": True,
    }

    try:
        graph_post(f"https://graph.microsoft.com/v1.0/users/{quote(sender, safe='')}/sendMail", payload)
    except httpx.HTTPStatusError as exc:
        return False, _graph_error_detail(exc), sender
    except RuntimeError as exc:
        return False, str(exc), sender

    return True, None, sender


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "cod_curso": _clean(row.cod_curso),
        "curso": _clean(row.curso),
        "primer_nombre": _clean(row.primer_nombre),
        "segundo_nombre": _clean(row.segundo_nombre),
        "primer_apellido": _clean(row.primer_apellido),
        "segundo_apellido": _clean(row.segundo_apellido),
        "cedula": _clean(row.cedula),
        "correo_electronico": _clean(row.correo_electronico),
        "usuario_generado": _clean(row.usuario_generado),
        "clave_temporal": _clean(row.clave_temporal),
        "graph_user_id": _clean(getattr(row, "graph_user_id", "")),
        "graph_user_principal_name": _clean(getattr(row, "graph_user_principal_name", "")),
        "graph_mail_sender": _clean(getattr(row, "graph_mail_sender", "")),
        "estado_graph": _clean(getattr(row, "estado_graph", "")),
        "error_graph": _clean(getattr(row, "error_graph", "")),
        "correo_enviado": bool(row.correo_enviado),
        "estado_envio": _clean(row.estado_envio),
        "error_envio": _clean(row.error_envio),
        "fecha_creacion": row.fecha_creacion.isoformat() if row.fecha_creacion else None,
        "fecha_graph": row.fecha_graph.isoformat() if getattr(row, "fecha_graph", None) else None,
        "fecha_envio": row.fecha_envio.isoformat() if row.fecha_envio else None,
    }


@router.get("/catalog")
def credentials_catalog(current_user: SessionUser = AdminOnly) -> dict[str, Any]:
    del current_user
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _ensure_table(cursor)
            courses: list[dict[str, Any]] = []
            cursor.execute(
                """
                SELECT TOP (300)
                    TRY_CONVERT(nvarchar(50), CodCurso) AS cod_curso,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(200), Curso))) AS curso,
                    TRY_CONVERT(nvarchar(10), Estado) AS estado,
                    TRY_CONVERT(varchar(10), FechaInicio, 23) AS fecha_inicio,
                    TRY_CONVERT(varchar(10), FechaFinal, 23) AS fecha_final
                FROM dbo.CursosEduContinua
                ORDER BY FechaInicio DESC, Curso
                """
            )
            for row in cursor.fetchall():
                course_name = _clean(row.curso)
                if not course_name:
                    continue
                courses.append(
                    CredentialCourse(
                        cod_curso=_clean(row.cod_curso),
                        curso=course_name,
                        estado=_clean(row.estado) or None,
                        fecha_inicio=_clean(row.fecha_inicio) or None,
                        fecha_final=_clean(row.fecha_final) or None,
                        source="EDUCACION_CONTINUA",
                    ).model_dump()
                )

            cursor.execute(
                """
                SELECT TOP (1200)
                    TRY_CONVERT(nvarchar(50), p.codigo_materia) AS codigo_materia,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(220), p.Nomb_Materia))) AS curso,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), p.cod_materia))) AS cod_materia,
                    TRY_CONVERT(nvarchar(20), p.Semestre) AS semestre,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(180), c.Nombre_Basica))) AS carrera
                FROM dbo.PENSUM p
                LEFT JOIN dbo.CARRERAS c
                    ON p.Cod_AnioBasica = c.Cod_AnioBasica
                WHERE p.Nomb_Materia IS NOT NULL
                ORDER BY p.Nomb_Materia, c.Nombre_Basica, p.Semestre
                """
            )
            seen_pensum: set[str] = set()
            for row in cursor.fetchall():
                codigo_materia = _clean(row.codigo_materia)
                course_name = _clean(row.curso)
                if not codigo_materia or not course_name or codigo_materia in seen_pensum:
                    continue
                seen_pensum.add(codigo_materia)
                courses.append(
                    CredentialCourse(
                        cod_curso=f"PENSUM:{codigo_materia}",
                        curso=course_name,
                        source="PENSUM",
                        codigo_materia=codigo_materia,
                        cod_materia=_clean(row.cod_materia) or None,
                        carrera=_clean(row.carrera) or None,
                        semestre=_clean(row.semestre) or None,
                    ).model_dump()
                )
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo cargar cursos") from exc

    return {
        "courses": courses,
        "default_message": DEFAULT_MESSAGE_TEMPLATE,
        "default_link": DEFAULT_TRAINING_LINK,
        "graph_user_domain": _clean(get_settings().graph_user_domain),
        "graph_mail_sender": _clean(get_settings().graph_mail_sender),
    }


@router.get("")
def list_credentials(
    cod_curso: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: SessionUser = AdminOnly,
) -> dict[str, Any]:
    del current_user
    where = ""
    params: list[Any] = []
    if cod_curso:
        where = "WHERE cod_curso = ?"
        params.append(cod_curso)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _ensure_table(cursor)
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    id, cod_curso, curso, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                    cedula, correo_electronico, usuario_generado, clave_temporal,
                    graph_user_id, graph_user_principal_name, graph_mail_sender, estado_graph, error_graph,
                    correo_enviado, estado_envio, error_envio, fecha_creacion, fecha_graph, fecha_envio
                FROM dbo.CREDENCIALES_CURSO
                {where}
                ORDER BY fecha_creacion DESC, id DESC
                """,
                params,
            )
            rows = [_row_to_dict(row) for row in cursor.fetchall()]
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo cargar credenciales") from exc

    return {"rows": rows, "count": len(rows)}


@router.post("/bulk")
def save_credentials_bulk(
    payload: CredentialBulkPayload,
    current_user: SessionUser = AdminOnly,
) -> dict[str, Any]:
    try:
        _graph_user_domain()
        if payload.enviar_correo:
            _graph_mail_sender()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    seen: set[tuple[str, str]] = set()
    created = 0
    updated = 0
    graph_created = 0
    graph_updated = 0
    graph_failed = 0
    sent = 0
    failed = 0
    rows: list[dict[str, Any]] = []

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            _ensure_table(cursor)
            for user in payload.usuarios:
                cedula = re.sub(r"\s+", "", _clean(user.cedula))
                correo = _clean(user.correo_electronico)
                if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", correo):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Correo no valido para la cedula {cedula or '-'}",
                    )
                key = (payload.cod_curso, cedula)
                if key in seen:
                    continue
                seen.add(key)

                usuario = _generate_username(user)
                clave = _generate_password()
                message_body = _render_message(payload.mensaje, user, payload.curso, usuario, clave, payload.link)
                graph_user: dict[str, Any] | None = None
                graph_user_id: str | None = None
                graph_upn: str | None = usuario
                estado_graph = "PENDIENTE_GRAPH"
                error_graph: str | None = None
                fecha_graph: datetime | None = None
                correo_enviado = bool(user.correo_enviado)
                estado_envio = "MARCADO_ENVIADO" if correo_enviado else "PENDIENTE"
                error_envio: str | None = None
                fecha_envio: datetime | None = datetime.now() if correo_enviado else None
                graph_mail_sender: str | None = None

                try:
                    graph_user, estado_graph, error_graph = _create_or_update_graph_user(user, usuario, clave)
                    fecha_graph = datetime.now()
                    if estado_graph == "CREADO_GRAPH":
                        graph_created += 1
                    elif estado_graph == "ACTUALIZADO_GRAPH":
                        graph_updated += 1
                    elif estado_graph == "ERROR_GRAPH":
                        graph_failed += 1
                    if graph_user:
                        graph_user_id = _clean(graph_user.get("id")) or None
                        graph_upn = _clean(graph_user.get("userPrincipalName")) or usuario
                except RuntimeError as exc:
                    estado_graph = "ERROR_CONFIG_GRAPH"
                    error_graph = str(exc)
                    graph_failed += 1
                    fecha_graph = datetime.now()
                except httpx.HTTPStatusError as exc:
                    estado_graph = "ERROR_GRAPH"
                    error_graph = _graph_error_detail(exc)
                    graph_failed += 1
                    fecha_graph = datetime.now()

                if payload.enviar_correo and not correo_enviado and not estado_graph.startswith("ERROR"):
                    ok, error, sender = _send_graph_email(
                        correo,
                        f"Credenciales de acceso - {payload.curso}",
                        message_body,
                    )
                    graph_mail_sender = sender
                    correo_enviado = ok
                    if ok:
                        estado_envio = "ENVIADO"
                        fecha_envio = datetime.now()
                        sent += 1
                    else:
                        estado_envio = "ERROR_ENVIO"
                        error_envio = error
                        failed += 1
                elif payload.enviar_correo and not correo_enviado and estado_graph.startswith("ERROR"):
                    estado_envio = "NO_ENVIADO_GRAPH"
                    error_envio = "No se envio correo porque la creacion/actualizacion en Microsoft Graph fallo."
                    failed += 1

                cursor.execute(
                    """
                    SELECT id
                    FROM dbo.CREDENCIALES_CURSO
                    WHERE cod_curso = ? AND cedula = ?
                    """,
                    payload.cod_curso,
                    cedula,
                )
                exists = cursor.fetchone() is not None
                if exists:
                    cursor.execute(
                        """
                        UPDATE dbo.CREDENCIALES_CURSO
                        SET curso = ?, primer_nombre = ?, segundo_nombre = ?, primer_apellido = ?, segundo_apellido = ?,
                            correo_electronico = ?, usuario_generado = ?, clave_temporal = ?, mensaje_enviado = ?,
                            link_induccion = ?, graph_user_id = ?, graph_user_principal_name = ?, graph_mail_sender = ?,
                            estado_graph = ?, error_graph = ?, correo_enviado = ?, estado_envio = ?, error_envio = ?,
                            fecha_graph = ?, fecha_envio = ?, fecha_actualizacion = SYSDATETIME()
                        WHERE cod_curso = ? AND cedula = ?
                        """,
                        payload.curso,
                        _clean(user.primer_nombre),
                        _clean(user.segundo_nombre) or None,
                        _clean(user.primer_apellido),
                        _clean(user.segundo_apellido) or None,
                        correo,
                        usuario,
                        clave,
                        message_body,
                        payload.link,
                        graph_user_id,
                        graph_upn,
                        graph_mail_sender,
                        estado_graph,
                        error_graph,
                        1 if correo_enviado else 0,
                        estado_envio,
                        error_envio,
                        fecha_graph,
                        fecha_envio,
                        payload.cod_curso,
                        cedula,
                    )
                    updated += 1
                else:
                    cursor.execute(
                        """
                        INSERT INTO dbo.CREDENCIALES_CURSO (
                            cod_curso, curso, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                            cedula, correo_electronico, usuario_generado, clave_temporal, mensaje_enviado,
                            link_induccion, graph_user_id, graph_user_principal_name, graph_mail_sender,
                            estado_graph, error_graph, correo_enviado, estado_envio, error_envio,
                            usuario_creacion, fecha_graph, fecha_envio
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        payload.cod_curso,
                        payload.curso,
                        _clean(user.primer_nombre),
                        _clean(user.segundo_nombre) or None,
                        _clean(user.primer_apellido),
                        _clean(user.segundo_apellido) or None,
                        cedula,
                        correo,
                        usuario,
                        clave,
                        message_body,
                        payload.link,
                        graph_user_id,
                        graph_upn,
                        graph_mail_sender,
                        estado_graph,
                        error_graph,
                        1 if correo_enviado else 0,
                        estado_envio,
                        error_envio,
                        current_user.login,
                        fecha_graph,
                        fecha_envio,
                    )
                    created += 1

                rows.append(
                    {
                        "cedula": cedula,
                        "correo_electronico": correo,
                        "usuario_generado": usuario,
                        "clave_temporal": clave,
                        "graph_user_id": graph_user_id,
                        "graph_user_principal_name": graph_upn,
                        "graph_mail_sender": graph_mail_sender,
                        "estado_graph": estado_graph,
                        "error_graph": error_graph,
                        "correo_enviado": correo_enviado,
                        "estado_envio": estado_envio,
                        "error_envio": error_envio,
                    }
                )

            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar credenciales") from exc

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "graph_created": graph_created,
        "graph_updated": graph_updated,
        "graph_failed": graph_failed,
        "sent": sent,
        "failed": failed,
        "rows": rows,
        "message": f"Credenciales procesadas: {created + updated}. Nuevas: {created}. Actualizadas: {updated}.",
    }
