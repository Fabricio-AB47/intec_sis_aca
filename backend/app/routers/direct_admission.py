from datetime import date
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import pyodbc

from app.core.security import SessionUser, require_screen_access
from app.routers import academic_enrollment as academic
from app.routers.certificate_renamer import _is_valid_ecuador_cedula
from app.routers.students import (
    _legacy_data_update_catalogs,
    _same_catalog_code,
    _validate_territorial_updates,
)
from app.services.db import get_connection
from app.services.academic_student_identity import find_academic_student
from app.services.direct_admission_excel import COLUMNS, CREDENTIAL_COLUMNS, SIMPLE_COLUMNS, MAX_FILE_BYTES, build_template, read_students
from app.services.direct_admission_credentials import (
    CredentialNames, get_admission_credential_state, provision_admission_credentials, require_provisioning_admin,
    admission_receipts,
)

router = APIRouter(prefix="/api/students/ingreso-directo", tags=["ingreso-directo"])
_ACCESS = require_screen_access("matricula-acad/ingreso-directo")
_SCHEMA = (Path(__file__).resolve().parents[2] / "sql/2026_09_18_ingreso_directo.sql").read_text(encoding="utf-8")
_CATALOG_FIELDS = [
    "Sexo", "EstadoCivil", "Etnia", "tipodocumento", "paisNacionalidadId",
    "provinciaNacimeintoId", "cantonNacimeintoId", "paisResidenciaId", "codprov", "Canton",
]


class DirectStudentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identificacion: str = Field(min_length=3, max_length=10)
    tipo_documento: Literal[1, 2, 3] = 1
    nombres: str = Field(min_length=2, max_length=70)
    apellidos: str = Field(min_length=2, max_length=70)
    correo: str = Field(default="", max_length=80)
    correo_intec: str = Field(default="", max_length=100)
    telefono: str = Field(default="", max_length=30)
    movil: str = Field(default="", max_length=15)
    fecha_nacimiento: date | None = None
    # Defaults defined by the supplied DATOS_ESTUD schema for unspecified data.
    sexo: int = Field(default=3, gt=0)
    estado_civil: int = Field(default=6, gt=0)
    etnia: int = Field(default=9, gt=0)
    pais_nacionalidad: str = Field(default="", max_length=100)
    provincia_nacimiento: str = Field(default="", max_length=100)
    canton_nacimiento: str = Field(default="", max_length=100)
    pais_residencia: str = Field(default="", max_length=100)
    provincia_residencia: int | None = Field(default=None, gt=0)
    canton_residencia: str = Field(default="", max_length=40)
    direccion: str = Field(default="", max_length=150)
    colegio: str = Field(default="", max_length=100)
    titulo_bachiller: str = Field(default="", max_length=100)

    @field_validator("nombres", "apellidos")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split()).upper()
        if not any(character.isalpha() for character in value):
            raise ValueError("Ingrese nombres y apellidos válidos.")
        return value

    @field_validator("correo", "correo_intec")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.lower()
        if value and not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", value):
            raise ValueError("Ingrese una dirección de correo válida.")
        if value:
            local, domain = value.rsplit("@", 1)
            if (len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local
                    or any(len(label) > 63 or label.startswith("-") or label.endswith("-") for label in domain.split("."))):
                raise ValueError("Ingrese una dirección de correo válida.")
        return value

    @model_validator(mode="after")
    def validate_identity(self):
        self.identificacion = self.identificacion.upper()
        if self.tipo_documento == 1 and not _is_valid_ecuador_cedula(self.identificacion):
            raise ValueError("La cédula ecuatoriana no es válida; revise sus diez dígitos.")
        if not re.fullmatch(r"[A-Z0-9]+", self.identificacion):
            raise ValueError("La identificación debe contener únicamente letras o números.")
        if len(f"{self.apellidos} {self.nombres}") > 70:
            raise ValueError("Apellidos y nombres no pueden superar 70 caracteres en DATOS_ESTUD.")
        if self.correo_intec and not self.correo_intec.endswith("@intec.edu.ec"):
            raise ValueError("El correo institucional debe pertenecer a @intec.edu.ec.")
        if self.fecha_nacimiento and self.fecha_nacimiento >= date.today():
            raise ValueError("La fecha de nacimiento debe ser anterior a hoy.")
        return self


class DirectEnrollmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    cod_anio_basica: int = Field(gt=0)
    codigo_periodo: int = Field(gt=0)
    nivel: int = Field(ge=1)
    materia_codes: list[int] = Field(min_length=1)
    paralelo: str = Field(min_length=1, max_length=4)
    num_grupo: int = Field(default=1, ge=1)
    tipo_matricula: Literal["R", "H", "E"] = "R"
    cod_jornada: int = Field(gt=0)
    inscrip_valor: float = Field(default=0, ge=0)
    matri_valor: float = Field(default=0, ge=0)
    valor: float = Field(default=0, ge=0)
    fecha_pago: date | None = None
    prerequisite_exception_codes: list[int] = Field(default_factory=list)
    prerequisite_exception_reason: str | None = Field(default=None, max_length=1000)

    @field_validator("materia_codes", "prerequisite_exception_codes")
    @classmethod
    def positive_subjects(cls, value: list[int]) -> list[int]:
        if any(code <= 0 for code in value):
            raise ValueError("Los códigos de materia deben ser positivos.")
        return sorted(set(value))

    def academic_payload(self, student_code: int) -> academic.AcademicEnrollmentPayload:
        fields = self.model_dump(exclude={"nivel", "fecha_pago"})
        return academic.AcademicEnrollmentPayload(
            **fields, codigo_estud=student_code,
            fecha_pago=self.fecha_pago.isoformat() if self.fecha_pago else None,
            remove_unselected=False,
        )


class DirectAdmissionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solicitud_id: UUID
    estudiante: DirectStudentPayload
    matricula: DirectEnrollmentPayload
    credenciales: CredentialNames | None = None

    @model_validator(mode="after")
    def validate_credential_names(self):
        if self.credenciales and not self.credenciales.matches(self.estudiante.nombres, self.estudiante.apellidos):
            raise ValueError("Los nombres para Office 365 y Moodle deben coincidir con los datos del estudiante.")
        return self


class AdmissionReceiptsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solicitud_ids: list[UUID] = Field(min_length=1)


def _student_fields(student: DirectStudentPayload) -> dict[str, Any]:
    return {
        "Sexo": student.sexo, "EstadoCivil": student.estado_civil, "Etnia": student.etnia,
        "tipodocumento": student.tipo_documento,
        "paisNacionalidadId": student.pais_nacionalidad,
        "provinciaNacimeintoId": student.provincia_nacimiento,
        "cantonNacimeintoId": student.canton_nacimiento,
        "paisResidenciaId": student.pais_residencia,
        "codprov": student.provincia_residencia, "Canton": student.canton_residencia,
    }


def _validate_student_catalogs(cursor, student: DirectStudentPayload) -> None:
    fields = _student_fields(student)
    catalogs = _legacy_data_update_catalogs(cursor, _CATALOG_FIELDS, "estudiantes")
    for field in ("Sexo", "EstadoCivil", "Etnia", "tipodocumento"):
        options = catalogs.get(field, [])
        if not options or not any(_same_catalog_code(option["value"], fields[field]) for option in options):
            raise HTTPException(400, detail=f"Seleccione un valor vigente para {field}.")
    _validate_territorial_updates(cursor, "estudiantes", fields, set(fields))


def _ensure_new_identity(cursor, student: DirectStudentPayload, existing_code: int | None = None) -> None:
    numeric_id = int(student.identificacion) if student.identificacion.isdigit() else 0
    cursor.execute(
        """
        SELECT TOP (1) codigo_estud
        FROM dbo.DATOS_ESTUD WITH (UPDLOCK, HOLDLOCK)
        WHERE (UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Cedula_Est)), ' ', ''), '-', ''), '.', '')) = ?
           OR (? > 0 AND Cedula = ?)
           OR LOWER(LTRIM(RTRIM(correo))) IN (NULLIF(?, ''), NULLIF(?, ''))
           OR LOWER(LTRIM(RTRIM(correointec))) IN (NULLIF(?, ''), NULLIF(?, '')))
          AND (? IS NULL OR codigo_estud <> ?)
        """,
        student.identificacion, numeric_id, numeric_id, student.correo, student.correo_intec,
        student.correo, student.correo_intec,
        existing_code, existing_code,
    )
    if cursor.fetchone():
        raise HTTPException(409, detail="La identificación o el correo ya pertenece a un estudiante. Utilice Matrícula individual; no se modificó su información.")
    cursor.execute(
        """
        SELECT TOP (1) Codestu FROM dbo.PREINSCRIPCION WITH (UPDLOCK, HOLDLOCK)
        WHERE (UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(Cedula)), ' ', ''), '-', ''), '.', '')) = ?
           OR LOWER(LTRIM(RTRIM(correo))) IN (NULLIF(?, ''), NULLIF(?, '')))
          AND (? IS NULL OR Codestu <> ?)
        """, student.identificacion, student.correo, student.correo_intec, existing_code, existing_code,
    )
    if cursor.fetchone():
        raise HTTPException(409, detail="El estudiante ya tiene una preinscripción. Continúe su primera matrícula desde Admisiones.")
    cursor.execute(
        """
        SELECT TOP (1) codestud FROM dbo.CorreosEstudIntec WITH (UPDLOCK, HOLDLOCK)
        WHERE (LOWER(LTRIM(RTRIM(CorreoPersonal))) IN (NULLIF(?, ''), NULLIF(?, ''))
           OR LOWER(LTRIM(RTRIM(CorreoIntec))) IN (NULLIF(?, ''), NULLIF(?, '')))
          AND (? IS NULL OR codestud IS NULL OR codestud <> ?)
        """, student.correo, student.correo_intec, student.correo, student.correo_intec, existing_code, existing_code,
    )
    if cursor.fetchone():
        raise HTTPException(409, detail="El correo ya está asociado a otra identidad institucional.")


def _resolve_student_identity(cursor, student: DirectStudentPayload):
    existing = find_academic_student(cursor, student.identificacion, for_update=True)
    if existing:
        if str(existing.Estado or "").strip().upper() != "A":
            raise HTTPException(409, detail="El estudiante ya existe y no está activo. No se duplicará ni se reactivará automáticamente.")
        if " ".join(str(existing.Apellidos_nombre).split()).upper() != f"{student.apellidos} {student.nombres}":
            raise HTTPException(409, detail="La cédula ya existe con otros nombres en el sistema académico. Revise sus datos; no se creó otro estudiante.")
        known_email = str(existing.correointec or "").strip().lower()
        if student.correo_intec and known_email and student.correo_intec != known_email:
            raise HTTPException(409, detail="El estudiante ya tiene otro correo institucional. No se modificó su identidad.")
    _ensure_new_identity(cursor, student, int(existing.codigo_estud) if existing else None)
    return existing


def _validate_level(cursor, enrollment: DirectEnrollmentPayload) -> None:
    pensum = academic._fetch_pensum_by_code(cursor, enrollment.cod_anio_basica)
    if any(code not in pensum or int(pensum[code].get("semestre") or 0) != enrollment.nivel for code in enrollment.materia_codes):
        raise HTTPException(400, detail="Todas las materias seleccionadas deben pertenecer a la carrera y al nivel indicado.")


def _insert_student(cursor, student: DirectStudentPayload, enrollment: DirectEnrollmentPayload, user: SessionUser) -> int:
    cursor.execute(
        """
        SELECT COALESCE(MAX(codigo), 0) + 1 FROM (
            SELECT TRY_CONVERT(int, codigo_estud) AS codigo FROM dbo.DATOS_ESTUD WITH (UPDLOCK, HOLDLOCK)
            UNION ALL
            SELECT TRY_CONVERT(int, Codestu) FROM dbo.PREINSCRIPCION WITH (UPDLOCK, HOLDLOCK)
            UNION ALL
            SELECT TRY_CONVERT(int, codestud) FROM dbo.CorreosEstudIntec WITH (UPDLOCK, HOLDLOCK)
            UNION ALL
            SELECT TRY_CONVERT(int, codigo_estud) FROM dbo.CABECERA_MATRICULA WITH (UPDLOCK, HOLDLOCK)
            UNION ALL
            SELECT TRY_CONVERT(int, codigo_estud) FROM dbo.CARRERAXESTUD WITH (UPDLOCK, HOLDLOCK)
        ) reserved_codes
        """
    )
    code = int(cursor.fetchone()[0])
    name = f"{student.apellidos} {student.nombres}"
    cursor.execute(
        """
        INSERT INTO dbo.DATOS_ESTUD (
            codigo_estud, Cedula_Est, Apellidos_nombre, correo, correointec, telefono, movil,
            Fecha_Nac, EstadoCivil, Etnia, Sexo, Cedula, Fotos, Tipodoc, Estado, NumMigracion,
            Fecha_Ingreso, Usuario, paisNacionalidadId, provinciaNacimeintoId, cantonNacimeintoId,
            paisResidenciaId, codprov, Canton, calle_principal, Colegio, TituloBachiller,
            nivelAcademicoQueCursa, Paralelo, fechaMatricula, tipodocumento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'A', 0,
                  CAST(GETDATE() AS date), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        code, student.identificacion, name, student.correo, student.correo_intec,
        student.telefono, student.movil, student.fecha_nacimiento, student.estado_civil,
        student.etnia, student.sexo,
        int(student.identificacion) if student.identificacion.isdigit() else 0,
        student.tipo_documento, user.login[:10], student.pais_nacionalidad,
        student.provincia_nacimiento, student.canton_nacimiento, student.pais_residencia,
        student.provincia_residencia, student.canton_residencia, student.direccion,
        student.colegio, student.titulo_bachiller, str(enrollment.nivel),
        enrollment.paralelo.upper(), date.today().isoformat(), str(student.tipo_documento),
    )
    # Pending credentials are not invented, sent to Moodle, or stored as plaintext.
    cursor.execute(
        """
        INSERT INTO dbo.CorreosEstudIntec (
            codestud, Nombres, CorreoPersonal, CorreoIntec, Password, fecha,
            Periodo, CorreoEnviado, Estado, TipoCursoMigra
        ) VALUES (?, ?, ?, ?, '', CAST(GETDATE() AS date), ?, 0, 'PENDIENTE', 'N')
        """, code, name, student.correo, student.correo_intec, enrollment.codigo_periodo,
    )
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.DATOSFACTURA', N'U') IS NOT NULL
            INSERT INTO dbo.DATOSFACTURA (CODESTUD, CEDESTUD, CEDRUCFACTURA, NOMBRES, DIRECCION, TELELFONO, CORREO)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, str(code), student.identificacion, student.identificacion, name,
        student.direccion, student.telefono or student.movil, student.correo,
    )
    return code


@router.get("/catalog")
def direct_admission_catalog(current_user: Annotated[SessionUser, Depends(_ACCESS)]) -> dict[str, Any]:
    result = academic.matricula_acad_catalog(current_user)
    with get_connection() as conn:
        result["datos_catalogos"] = _legacy_data_update_catalogs(conn.cursor(), _CATALOG_FIELDS, "estudiantes")
    return result


@router.get("/pensum")
def direct_admission_pensum(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    cod_anio_basica: Annotated[int, Query(gt=0)],
) -> dict[str, Any]:
    return academic.matricula_acad_pensum(current_user, cod_anio_basica)


def _excel_catalog(current_user: SessionUser, career_code: int) -> tuple[dict, dict]:
    catalog = direct_admission_catalog(current_user)
    career = next((item for item in catalog.get("carreras", []) if int(item["cod_anio_basica"]) == career_code), None)
    if not career:
        raise HTTPException(400, detail="Seleccione una carrera activa para el ingreso desde Excel.")
    return catalog, career


@router.get("/excel/plantilla")
def direct_admission_excel_template(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    cod_anio_basica: Annotated[int, Query(gt=0)],
) -> StreamingResponse:
    catalog, career = _excel_catalog(current_user, cod_anio_basica)
    pensum = direct_admission_pensum(current_user, cod_anio_basica)
    content = build_template(career, catalog["datos_catalogos"], pensum.get("items", []))
    return StreamingResponse(
        BytesIO(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ingreso_intec_carrera_{cod_anio_basica}.xlsx"'},
    )


@router.post("/excel/validar")
def validate_direct_admission_excel(
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
    matricula: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    crear_credenciales: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    if crear_credenciales:
        require_provisioning_admin(current_user)
    try:
        enrollment = DirectEnrollmentPayload.model_validate_json(matricula)
    except ValidationError as error:
        raise HTTPException(422, detail="Revise carrera, período, nivel, jornada, paralelo y materias antes de validar el Excel.") from error
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, detail="Utilice un archivo .xlsx descargado desde este apartado.")
    catalog, career = _excel_catalog(current_user, enrollment.cod_anio_basica)
    rows = read_students(file.file.read(MAX_FILE_BYTES + 1), enrollment.cod_anio_basica, catalog["datos_catalogos"])
    # Detect collisions across the entire file, including invalid/unselected rows.
    identities, emails = {}, {}
    for row in rows:
        data = row["datos"]
        identity = str(data["identificacion"]).upper()
        if identity:
            identity = (identity.lstrip("0") or "0") if identity.isdigit() else identity
            identities.setdefault(identity, []).append(row)
        for email in {data["correo"].lower(), data["correo_intec"].lower()} - {""}:
            emails.setdefault(email, []).append(row)
    for label, groups in [("Identificación", identities), ("Correo", emails)]:
        for group in groups.values():
            if len(group) > 1:
                numbers = ", ".join(str(row["fila"]) for row in group[:20])
                if len(group) > 20:
                    numbers += f" y {len(group) - 20} filas más"
                for row in group:
                    row["errores"].append(f"{label} repetido en las filas {numbers}.")
    labels = {field: label for field, label, _, _ in COLUMNS + CREDENTIAL_COLUMNS + SIMPLE_COLUMNS}
    items = []
    for row in rows:
        data, issues, payload = row["datos"], row["errores"], None
        identity_info = None
        if not issues:
            try:
                student = DirectStudentPayload.model_validate({**data, "tipo_documento": int(data["tipo_documento"])})
                names = CredentialNames.model_validate(row.get("credenciales") or {}) if crear_credenciales else None
                admission = DirectAdmissionPayload(solicitud_id=uuid4(), estudiante=student, matricula=enrollment, credenciales=names)
                preview = preview_direct_admission(admission, current_user)
                identity_info = preview.get("estudiante")
                if int(preview.get("summary", {}).get("bloqueadas_por_prerrequisito") or 0) > 0:
                    issues.append("Hay prerrequisitos pendientes; revise el nivel o justifique una excepción.")
                else:
                    payload = admission.model_dump(mode="json")
            except ValidationError as error:
                issues.extend(f"{labels.get(str(item['loc'][0]), 'Estudiante') if item['loc'] else 'Estudiante'}: {item['msg']}" for item in error.errors())
            except HTTPException as error:
                if error.status_code >= 500:
                    raise
                issues.append(str(error.detail))
        items.append({
            "fila": row["fila"], "identificacion": data["identificacion"],
            "nombre_estudiante": f"{data['apellidos']} {data['nombres']}".strip(),
            "correo": data["correo"], "errores": issues, "payload": payload,
            "estudiante_existente": identity_info["accion"] == "EXISTENTE" if identity_info else None,
            "codigo_estud_existente": identity_info.get("codigo_estud") if identity_info else None,
        })
    valid = sum(item["payload"] is not None for item in items)
    return {"carrera": career, "total": len(items), "validos": valid, "invalidos": len(items) - valid, "items": items}


@router.post("/preview")
def preview_direct_admission(
    payload: DirectAdmissionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    if payload.credenciales:
        require_provisioning_admin(current_user)
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            _validate_student_catalogs(cursor, payload.estudiante)
            existing = _resolve_student_identity(cursor, payload.estudiante)
            _validate_level(cursor, payload.matricula)
            # -1 is a virtual student: preview stays read-only, including its triggers.
            preview = academic._preview_with_cursor(
                cursor, payload.matricula.academic_payload(int(existing.codigo_estud) if existing else -1),
                student_pending_creation=existing is None,
            )
            return {**preview, "estudiante": {"accion": "EXISTENTE" if existing else "CREAR",
                    "codigo_estud": str(existing.codigo_estud) if existing else None}}
        finally:
            conn.rollback()


@router.post("/save")
def save_direct_admission(
    payload: DirectAdmissionPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    if payload.credenciales:
        require_provisioning_admin(current_user)
    fields = payload.model_dump(mode="json", exclude={"credenciales"} if payload.credenciales is None else set())
    fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DECLARE @lock_result int;
                EXEC @lock_result = sys.sp_getapplock @Resource=N'PORTAL_INGRESO_DIRECTO',
                    @LockMode=N'Exclusive', @LockOwner=N'Transaction', @LockTimeout=15000;
                IF @lock_result < 0 THROW 51000, 'No se pudo bloquear el ingreso directo. Reintente.', 1;
                """
            )
            cursor.execute(_SCHEMA)
            cursor.execute(
                "SELECT contenido_hash, registrado_por, resultado_json FROM dbo.PORTAL_INGRESO_DIRECTO WITH (UPDLOCK, HOLDLOCK) WHERE solicitud_id = ?",
                str(payload.solicitud_id),
            )
            previous = cursor.fetchone()
            if previous:
                if previous.contenido_hash != fingerprint or previous.registrado_por != current_user.login:
                    raise HTTPException(409, detail="La solicitud ya fue utilizada. Revise los ingresos registrados antes de repetirla.")
                result = json.loads(previous.resultado_json)
                conn.commit()
                return {**result, "reused": True}
            _validate_student_catalogs(cursor, payload.estudiante)
            existing = _resolve_student_identity(cursor, payload.estudiante)
            _validate_level(cursor, payload.matricula)
            code = int(existing.codigo_estud) if existing else _insert_student(cursor, payload.estudiante, payload.matricula, current_user)
            enrollment = academic._save_enrollment_with_cursor(
                cursor, payload.matricula.academic_payload(code), current_user.login[:10], date.today(),
                student_already_resolved=True,
            )
            completed = int(enrollment.get("inserted") or 0) + int(enrollment.get("existing_skipped") or 0)
            if not enrollment.get("ok") or completed != len(payload.matricula.materia_codes):
                raise HTTPException(409, detail="No se pudo completar toda la matrícula; el ingreso se revirtió sin dejar registros parciales.")
            result = {
                "ok": True, "message": ("Estudiante existente verificado. Matrícula completada sin duplicar registros."
                                        if existing else "Estudiante registrado y matriculado correctamente."),
                "estudiante_existente": existing is not None,
                "solicitud_id": str(payload.solicitud_id), "codigo_estud": str(code),
                "identificacion": payload.estudiante.identificacion,
                "nombre_estudiante": f"{payload.estudiante.apellidos} {payload.estudiante.nombres}",
                "nivel": payload.matricula.nivel, "matricula": enrollment,
                "documentos_pendientes": True,
                "datos_credenciales": {"nombres": payload.estudiante.nombres, "apellidos": payload.estudiante.apellidos},
                "credenciales": payload.credenciales.model_dump() if payload.credenciales else None,
            }
            cursor.execute(
                """
                INSERT INTO dbo.PORTAL_INGRESO_DIRECTO (
                    solicitud_id, contenido_hash, codigo_estud, cod_anio_basica, codigo_periodo,
                    nivel, registrado_por, resultado_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, str(payload.solicitud_id), fingerprint, code, payload.matricula.cod_anio_basica,
                payload.matricula.codigo_periodo, payload.matricula.nivel, current_user.login,
                json.dumps(result, ensure_ascii=True),
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


@router.post("/comprobantes")
def download_admission_receipts(
    payload: AdmissionReceiptsPayload,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> StreamingResponse:
    return StreamingResponse(BytesIO(admission_receipts(payload.solicitud_ids, current_user)), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="comprobantes_matricula.pdf"',
                 "Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.get("/{solicitud_id}/comprobante")
def download_admission_receipt(
    solicitud_id: UUID,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> StreamingResponse:
    return StreamingResponse(BytesIO(admission_receipts([solicitud_id], current_user)), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="comprobante_matricula_{solicitud_id}.pdf"',
                 "Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.get("/{solicitud_id}/credenciales")
def direct_admission_credentials_state(
    solicitud_id: UUID,
    response: Response,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return get_admission_credential_state(solicitud_id, current_user)


@router.post("/{solicitud_id}/credenciales")
async def direct_admission_credentials_provision(
    solicitud_id: UUID,
    payload: CredentialNames,
    response: Response,
    current_user: Annotated[SessionUser, Depends(_ACCESS)],
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return await provision_admission_credentials(solicitud_id, payload, current_user)


@router.get("/history")
def direct_admission_history(current_user: Annotated[SessionUser, Depends(_ACCESS)]) -> dict[str, Any]:
    del current_user
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT OBJECT_ID(N'dbo.PORTAL_INGRESO_DIRECTO', N'U')")
        if not cursor.fetchone()[0]:
            return {"items": []}
        cursor.execute(
            """
            SELECT TOP (100) a.solicitud_id, a.codigo_estud, d.Cedula_Est, d.Apellidos_nombre,
                c.Nombre_Basica, p.Detalle_Periodo, a.nivel, a.registrado_por, a.fecha_registro
            FROM dbo.PORTAL_INGRESO_DIRECTO a
            JOIN dbo.DATOS_ESTUD d ON d.codigo_estud = a.codigo_estud
            JOIN dbo.CARRERAS c ON c.Cod_AnioBasica = a.cod_anio_basica
            JOIN dbo.PERIODO p ON p.cod_periodo = a.codigo_periodo
            ORDER BY a.fecha_registro DESC, a.solicitud_id
            """
        )
        return {"items": [
            {"solicitud_id": str(row.solicitud_id), "codigo_estud": str(row.codigo_estud),
             "identificacion": str(row.Cedula_Est).strip(), "nombre_estudiante": str(row.Apellidos_nombre).strip(),
             "carrera": str(row.Nombre_Basica).strip(), "periodo": str(row.Detalle_Periodo).strip(),
             "nivel": row.nivel, "registrado_por": row.registrado_por,
             "fecha_registro": row.fecha_registro.isoformat()}
            for row in cursor.fetchall()
        ]}
