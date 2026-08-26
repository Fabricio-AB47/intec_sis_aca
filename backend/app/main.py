from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.audit_context import AuditContext, reset_audit_context, set_audit_context
from app.core.config import get_settings
from app.core.security import decode_session_token
from app.routers.academic_enrollment import router as academic_enrollment_router
from app.routers.academic_system import router as academic_system_router
from app.routers.age_ranges import router as age_ranges_router
from app.routers.auth import router as auth_router
from app.routers.carnet import router as carnet_router
from app.routers.certificados import router as certificados_router
from app.routers.certificate_renamer import router as certificate_renamer_router
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

app = FastAPI(
    title="Reportería API",
    version="1.0.0",
    root_path=""
)

origins = settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-OneDrive-Saved",
        "X-OneDrive-Root",
        "X-OneDrive-Item-Count",
        "X-OneDrive-Same-Folder",
    ],
)


@app.middleware("http")
async def bind_database_audit_context(request: Request, call_next):
    request_id = (request.headers.get("X-Request-ID") or str(uuid4())).strip()[:128]
    user = None
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        try:
            user = decode_session_token(session_token)
        except Exception:
            user = None

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
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
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
app.include_router(titulos_registrados_router)
app.include_router(titulacion_router)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT), check_dir=False), name="uploads")


@app.get("/")
def root():
    return {"message": "API de Reportería activa"}
