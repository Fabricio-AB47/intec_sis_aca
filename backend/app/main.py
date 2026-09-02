import logging
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.core.audit_context import AuditContext, reset_audit_context, set_audit_context
from app.core.config import get_settings
from app.core.security import SessionUser, decode_session_token, get_current_user
from app.routers.academic_enrollment import router as academic_enrollment_router
from app.routers.academic_system import router as academic_system_router
from app.routers.age_ranges import router as age_ranges_router
from app.routers.auth import router as auth_router
from app.routers.carnet import router as carnet_router
from app.routers.certificados import router as certificados_router
from app.routers.certificate_renamer import router as certificate_renamer_router
from app.routers.career_change_requests import router as career_change_requests_router
from app.routers.modality_change_requests import router as modality_change_requests_router
from app.routers.credential_generator import router as credential_generator_router
from app.routers.document_expedients import router as document_expedients_router
from app.routers.excel_validator import router as excel_validator_router
from app.routers.english_exams import router as english_exams_router
from app.routers.health import router as health_router
from app.routers.institutional_email import router as institutional_email_router
from app.routers.integration_history import router as integration_history_router
from app.routers.legacy_reports import router as legacy_reports_router
from app.routers.mass_email import router as mass_email_router
from app.routers.moodle import router as moodle_router
from app.routers.portal_academico import router as portal_academico_router
from app.routers.practicas_institucionales import router as practicas_institucionales_router
from app.routers.practicas_operativas import router as practicas_operativas_router
from app.routers.preinscription import UPLOAD_ROOT, router as preinscription_router
from app.routers.senescyt import router as senescyt_router
from app.routers.screen_access import router as screen_access_router
from app.routers.sisacademico_admin import router as sisacademico_admin_router
from app.routers.students import router as students_router
from app.routers.teams import router as teams_router
from app.routers.teacher_evaluation import router as teacher_evaluation_router
from app.routers.titulos_registrados import router as titulos_registrados_router
from app.routers.titulacion import router as titulacion_router

settings = get_settings()
logger = logging.getLogger("intec_sis_aca.security")

app = FastAPI(
    title="Reportería API",
    version="1.0.0",
    root_path="",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

origins = settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=settings.cors_allowed_headers_list,
    expose_headers=[
        "Content-Disposition",
        "X-OneDrive-Saved",
        "X-OneDrive-Root",
        "X-OneDrive-Item-Count",
        "X-OneDrive-Same-Folder",
    ],
)

if settings.trusted_hosts_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_origin(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _origin_allowed(request: Request, origin: str) -> bool:
    configured = {_request_origin(item) for item in settings.cors_origins_list}
    if origin in configured:
        return True
    current = f"{request.url.scheme.lower()}://{request.url.netloc.lower()}"
    return origin == current


def _safe_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if _REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid4())


def _apply_security_headers(request: Request, response, request_id: str) -> None:
    response.headers["X-Request-ID"] = request_id
    if not settings.security_headers_enabled:
        return
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        if request.url.path in {"/docs", "/redoc"}
        else "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    if settings.security_hsts_enabled and (request.url.scheme == "https" or forwarded_proto == "https"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def _cors_for_error(request: Request, response: JSONResponse) -> None:
    origin = _request_origin(request.headers.get("Origin"))
    if origin and _origin_allowed(request, origin):
        response.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"


@app.middleware("http")
async def bind_database_audit_context(request: Request, call_next):
    request_id = _safe_request_id(request.headers.get("X-Request-ID"))
    user = None
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        try:
            user = decode_session_token(session_token)
        except Exception:
            user = None

    # La dependencia de autenticacion reutiliza esta validacion dentro de la
    # misma solicitud. Los tokens invalidos se vuelven a validar para conservar
    # el detalle y el codigo de respuesta actuales.
    request.state.session_user = user

    context_token = set_audit_context(
        AuditContext(
            user=(user.login if user else "NO_AUTENTICADO"),
            role=(user.rol if user else "PUBLICO"),
            user_id=(str(user.id_usuario) if user and user.id_usuario is not None else ""),
            origin=(user.origen if user and user.origen else "API"),
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=(request.client.host if request.client else ""),
        )
    )
    try:
        content_length = request.headers.get("Content-Length", "").strip()
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size < 0:
                response = JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Longitud de solicitud inválida."},
                )
                _cors_for_error(request, response)
                _apply_security_headers(request, response, request_id)
                return response
            if declared_size > settings.max_request_body_bytes:
                response = JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "La solicitud supera el tamaño máximo permitido."},
                )
                _cors_for_error(request, response)
                _apply_security_headers(request, response, request_id)
                return response

        if settings.csrf_protection_enabled and request.method.upper() in _UNSAFE_METHODS and session_token:
            fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
            origin = _request_origin(request.headers.get("Origin"))
            if not origin:
                origin = _request_origin(request.headers.get("Referer"))
            missing_origin = not origin and fetch_site not in {"same-origin", "same-site"}
            if (
                fetch_site == "cross-site"
                or (origin and not _origin_allowed(request, origin))
                or (settings.csrf_require_origin and missing_origin)
            ):
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Solicitud rechazada por la política de origen."},
                )
                _cors_for_error(request, response)
                _apply_security_headers(request, response, request_id)
                return response

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Error no controlado. request_id=%s path=%s", request_id, request.url.path)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": f"Ocurrió un error interno. Código de seguimiento: {request_id}"},
            )
            _cors_for_error(request, response)

        must_mask_server_error = response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR or (
            settings.is_production and response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if must_mask_server_error and not settings.expose_internal_errors:
            response = JSONResponse(
                status_code=response.status_code,
                content={"detail": f"Ocurrió un error interno. Código de seguimiento: {request_id}"},
            )
            _cors_for_error(request, response)
        _apply_security_headers(request, response, request_id)
        return response
    finally:
        reset_audit_context(context_token)


app.include_router(health_router)
app.include_router(institutional_email_router)
app.include_router(integration_history_router)
app.include_router(teams_router)
app.include_router(auth_router)
app.include_router(carnet_router)
app.include_router(certificados_router)
app.include_router(certificate_renamer_router)
app.include_router(career_change_requests_router)
app.include_router(modality_change_requests_router)
app.include_router(credential_generator_router)
app.include_router(mass_email_router)
app.include_router(moodle_router)
app.include_router(excel_validator_router)
app.include_router(english_exams_router)
app.include_router(document_expedients_router)
app.include_router(students_router)
app.include_router(age_ranges_router)
app.include_router(academic_enrollment_router)
app.include_router(academic_system_router)
app.include_router(preinscription_router)
app.include_router(senescyt_router)
app.include_router(screen_access_router)
app.include_router(legacy_reports_router)
app.include_router(sisacademico_admin_router)
app.include_router(portal_academico_router)
app.include_router(teacher_evaluation_router)
app.include_router(practicas_institucionales_router)
app.include_router(practicas_operativas_router)
app.include_router(titulos_registrados_router)
app.include_router(titulacion_router)


@app.get("/uploads/{file_path:path}", include_in_schema=False)
def download_protected_upload(
    file_path: str,
    _current_user: Annotated[SessionUser, Depends(get_current_user)],
) -> FileResponse:
    upload_root = Path(UPLOAD_ROOT).resolve()
    target = (upload_root / file_path).resolve()
    try:
        target.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.") from exc
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

    inline_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}
    response = FileResponse(
        target,
        filename=target.name,
        content_disposition_type="inline" if target.suffix.lower() in inline_suffixes else "attachment",
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@app.get("/")
def root():
    return {"message": "API de Reportería activa"}
