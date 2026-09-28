"""Same-origin access to the existing graduation service, using the academic session."""
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import httpx
import jwt

from app.core.config import get_settings
from app.core.security import SessionUser, require_screen_access

router = APIRouter(prefix="/api/titulation-portal", tags=["titulacion"])
_ACCESS = require_screen_access("titulacion-proceso")
_ROLES = {
    "ADMINISTRADOR": ["ADMIN_TITULACION", "COORDINADOR_ACADEMICO", "EVALUADOR_TITULACION"],
    "ACADEMICO": ["COORDINADOR_ACADEMICO"],
    "SECRETARIA": ["SECRETARIA_TITULACION"],
    "RECTOR": ["AUTORIDAD_ACADEMICA"],
    "VICERRECTOR": ["AUTORIDAD_ACADEMICA"],
    "SOPORTE": ["CONSULTA_TITULACION"],
    "DOCENTE": ["EVALUADOR_TITULACION"],
}
# An explicit allowlist prevents the bridge becoming a general-purpose proxy.
_ROUTES = {
    "GET": [r"dashboard/resumen", r"estudiantes-aptos(?:/[\w-]+)?", r"habilitaciones(?:/\d+)?",
            r"grupos(?:/\d+(?:/responsables)?)?", r"responsables", r"actas(?:/\d+/pdf)?",
            r"titulos(?:/[\w-]+)?", r"documentos/\d+/historial",
            r"expedientes/\d+/(?:documentos|acta|calificaciones(?:/consolidado)?)"],
    "POST": [r"estudiantes-aptos/sincronizar", r"habilitaciones", r"grupos/(?:complexivo(?:/teams)?|defensa-grado)",
             r"grupos/\d+/(?:estudiantes|responsable-complexivo|tribunal-defensa)", r"responsables",
             r"documentos/upload", r"titulos/(?:registro|intec)/upload", r"actas/\d+/firmada/upload",
             r"expedientes/\d+/(?:calificaciones/(?:evaluador|consolidar)|acta/generar)"],
    "PUT": [r"habilitaciones/\d+/anular", r"grupos/\d+/programacion", r"responsables/\d+",
            r"documentos/\d+/(?:validar|observar)", r"actas/\d+/anular"],
    "DELETE": [r"grupos/\d+/estudiantes/[\w-]+", r"responsables/\d+"],
}
_MAX_BODY = 32 * 1024 * 1024
_MAX_RESPONSE = 48 * 1024 * 1024


def portal_roles(user: SessionUser) -> list[str]:
    roles = _ROLES.get(user.rol.upper())
    if not roles:
        raise HTTPException(403, "Su perfil no tiene acceso al portal de titulación.")
    return roles


def portal_config():
    settings = get_settings()
    url = settings.titulation_portal_url.rstrip("/")
    key = settings.titulation_portal_signing_key
    parsed = urlsplit(url)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (not key or len(key.get_secret_value()) < 32 or "CHANGE_ME" in key.get_secret_value().upper()
            or not settings.titulation_portal_issuer.strip() or not settings.titulation_portal_audience.strip() or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
            or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
        raise HTTPException(503, "Configure la conexión segura del servicio de titulación en el servidor.")
    return settings, url, key.get_secret_value()


def portal_token(user: SessionUser, settings, key: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": user.login, "unique_name": user.login, "role": portal_roles(user),
        "iss": settings.titulation_portal_issuer, "aud": settings.titulation_portal_audience,
        "iat": now, "nbf": now, "exp": now + timedelta(minutes=2), "jti": str(uuid4()),
    }, key, algorithm="HS256")


@router.get("/status")
def portal_status(user: SessionUser = Depends(_ACCESS)):
    roles = portal_roles(user)
    try:
        portal_config()
    except HTTPException:
        return {"configured": False, "roles": roles}
    return {"configured": True, "roles": roles}


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def forward_portal(path: str, request: Request, user: SessionUser = Depends(_ACCESS)):
    portal_roles(user)
    if not any(re.fullmatch(pattern, path, flags=re.ASCII) for pattern in _ROUTES.get(request.method, [])):
        raise HTTPException(404, "Operación de titulación no disponible.")
    settings, url, key = portal_config()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY:
            raise HTTPException(413, "El archivo supera el tamaño permitido de 32 MB.")
        body.extend(chunk)
    headers = {"Authorization": f"Bearer {portal_token(user, settings, key)}"}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10), follow_redirects=False) as client:
            async with client.stream(request.method, f"{url}/api/titulacion/{path}",
                                     params=request.query_params.multi_items(), content=bytes(body), headers=headers) as upstream:
                if 300 <= upstream.status_code < 400 or upstream.status_code >= 500:
                    raise HTTPException(502, "El servicio de titulación no pudo completar la operación. Consulte el estado antes de reintentar.")
                if upstream.status_code == 401:
                    raise HTTPException(502, "Revise la configuración de autenticación entre los servicios de titulación.")
                content = bytearray()
                async for chunk in upstream.aiter_bytes():
                    if len(content) + len(chunk) > _MAX_RESPONSE:
                        raise HTTPException(502, "La respuesta del servicio supera el tamaño permitido.")
                    content.extend(chunk)
                response_headers = {"Cache-Control": "no-store"}
                for name in ("content-type", "content-disposition"):
                    if upstream.headers.get(name):
                        response_headers[name] = upstream.headers[name]
                return Response(bytes(content), status_code=upstream.status_code, headers=response_headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "El servicio tardó demasiado. Consulte el estado antes de volver a guardar.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, "No se pudo conectar con el servicio de titulación.") from exc
