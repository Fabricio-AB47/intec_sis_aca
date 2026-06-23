from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.routers.academic_enrollment import router as academic_enrollment_router
from app.routers.age_ranges import router as age_ranges_router
from app.routers.auth import router as auth_router
from app.routers.carnet import router as carnet_router
from app.routers.certificados import router as certificados_router
from app.routers.certificate_renamer import router as certificate_renamer_router
from app.routers.credential_generator import router as credential_generator_router
from app.routers.excel_validator import router as excel_validator_router
from app.routers.health import router as health_router
from app.routers.legacy_reports import router as legacy_reports_router
from app.routers.mass_email import router as mass_email_router
from app.routers.portal_academico import router as portal_academico_router
from app.routers.preinscription import UPLOAD_ROOT, router as preinscription_router
from app.routers.senescyt import router as senescyt_router
from app.routers.sisacademico_admin import router as sisacademico_admin_router
from app.routers.students import router as students_router
from app.routers.teams import router as teams_router
from app.routers.teacher_evaluation import router as teacher_evaluation_router

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
)

app.include_router(health_router)
app.include_router(teams_router)
app.include_router(auth_router)
app.include_router(carnet_router)
app.include_router(certificados_router)
app.include_router(certificate_renamer_router)
app.include_router(credential_generator_router)
app.include_router(mass_email_router)
app.include_router(excel_validator_router)
app.include_router(students_router)
app.include_router(age_ranges_router)
app.include_router(academic_enrollment_router)
app.include_router(preinscription_router)
app.include_router(senescyt_router)
app.include_router(legacy_reports_router)
app.include_router(sisacademico_admin_router)
app.include_router(portal_academico_router)
app.include_router(teacher_evaluation_router)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT), check_dir=False), name="uploads")


@app.get("/")
def root():
    return {"message": "API de Reportería activa"}
