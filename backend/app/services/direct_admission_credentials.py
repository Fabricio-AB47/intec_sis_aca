"""Idempotent provisioning after admission, isolated from academic transactions."""

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import SessionUser
from app.integrations.moodle.client import MoodleClient
from app.routers import credential_generator as credentials
from app.services.db import get_connection
from app.services.academic_student_identity import find_academic_student, same_identification
from app.services.direct_admission_receipt import build_receipt_pdf


_SCHEMA = (Path(__file__).resolve().parents[2] / "sql/2026_09_18_ingreso_directo_credenciales.sql").read_text(encoding="utf-8")


class CredentialNames(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    primer_nombre: str = Field(min_length=1, max_length=70)
    segundo_nombre: str = Field(default="", max_length=70)
    primer_apellido: str = Field(min_length=1, max_length=70)
    segundo_apellido: str = Field(default="", max_length=70)

    @field_validator("primer_nombre", "segundo_nombre", "primer_apellido", "segundo_apellido")
    @classmethod
    def normalize(cls, value: str):
        value = " ".join(value.split()).upper()
        if value and not any(character.isalpha() for character in value):
            raise ValueError("Ingrese nombres y apellidos válidos para las credenciales.")
        return value

    def matches(self, names: str, surnames: str) -> bool:
        return (f"{self.primer_nombre} {self.segundo_nombre}".strip() == " ".join(names.split()).upper()
                and f"{self.primer_apellido} {self.segundo_apellido}".strip() == " ".join(surnames.split()).upper())


def require_provisioning_admin(user: SessionUser):
    if user.rol != "ADMINISTRADOR":
        raise HTTPException(403, detail="El aprovisionamiento de Office 365 y Moodle requiere el perfil Administrador.")


def _safe_error(error: Exception, password: str = "") -> str:
    detail = credentials._graph_error_detail(error)
    return detail.replace(password, "[CREDENCIAL]") if password else detail


def _profile(cursor, request_id: UUID) -> dict:
    cursor.execute("SELECT OBJECT_ID(N'dbo.PORTAL_INGRESO_DIRECTO', N'U')")
    if not cursor.fetchone()[0]:
        raise HTTPException(404, detail="El ingreso académico no existe.")
    cursor.execute(
        """SELECT a.resultado_json, a.codigo_estud, a.codigo_periodo,
            d.Cedula_Est, d.Apellidos_nombre, d.Estado, d.correointec AS correo_datos, ce.CorreoIntec AS correo_credenciales
        FROM dbo.PORTAL_INGRESO_DIRECTO a
        JOIN dbo.DATOS_ESTUD d ON d.codigo_estud = a.codigo_estud
        LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud = a.codigo_estud
        WHERE a.solicitud_id = ?""", str(request_id),
    )
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise HTTPException(404 if not rows else 409, detail="El ingreso no tiene una identidad estudiantil única.")
    row = rows[0]
    if credentials._clean(row.Estado).upper() != "A":
        raise HTTPException(409, detail="Solo se pueden aprovisionar estudiantes activos.")
    result = json.loads(row.resultado_json)
    academic_student = find_academic_student(cursor, result["identificacion"])
    if (not academic_student or int(academic_student.codigo_estud) != int(row.codigo_estud)
            or not same_identification(row.Cedula_Est, result["identificacion"])):
        raise HTTPException(409, detail="La identificación del estudiante cambió; revise el ingreso antes de aprovisionar.")
    emails = {credentials._clean(value).lower() for value in [row.correo_datos, row.correo_credenciales] if credentials._clean(value)}
    if len(emails) > 1:
        raise HTTPException(409, detail="DATOS_ESTUD y CorreosEstudIntec tienen correos institucionales diferentes.")
    return {"record": result, "identity": result["identificacion"], "stored_identity": row.Cedula_Est,
            "correo_datos": credentials._clean(row.correo_datos).lower(),
            "correo_credenciales": credentials._clean(row.correo_credenciales).lower(),
            "personal_email": credentials._clean(getattr(academic_student, "correo", "")),
            "name": " ".join(credentials._clean(row.Apellidos_nombre).split()).upper(),
            "code": int(row.codigo_estud), "period": int(row.codigo_periodo), "email": next(iter(emails), "")}


def _read_state(cursor, request_id: UUID):
    cursor.execute("SELECT OBJECT_ID(N'dbo.PORTAL_INGRESO_CREDENCIALES', N'U')")
    if not cursor.fetchone()[0]:
        return None
    cursor.execute("SELECT persona_json, resultado_json, reporte_credencial_id FROM dbo.PORTAL_INGRESO_CREDENCIALES WHERE solicitud_id = ?", str(request_id))
    row = cursor.fetchone()
    return ({"persona": json.loads(row.persona_json), "result": json.loads(row.resultado_json) if row.resultado_json else None,
             "report_id": row.reporte_credencial_id} if row else None)


def get_admission_credential_state(request_id: UUID, user: SessionUser):
    require_provisioning_admin(user)
    with get_connection() as conn:
        profile = _profile(conn.cursor(), request_id)
        state = _read_state(conn.cursor(), request_id)
        return {"estado_general": "PENDIENTE", "datos_persona": state["persona"] if state else profile["record"].get("credenciales"),
                "datos_credenciales": profile["record"].get("datos_credenciales"), **((state or {}).get("result") or {}),
                "estado_correo_academico": "SINCRONIZADO" if _email_synchronized(profile, profile["email"]) else "PENDIENTE",
                "reporte_credencial_id": (state or {}).get("report_id")}


def _email_synchronized(profile, email):
    return bool(email and profile.get("correo_datos") == email and profile.get("correo_credenciales") == email)


def _issued_passwords(cursor, profile, result):
    passwords, dates, archive_ids = {}, [], set()
    cursor.execute("SELECT OBJECT_ID(N'dbo.CREDENCIAL_APROVISIONAMIENTO', N'U')")
    if not cursor.fetchone()[0]:
        return passwords, dates, archive_ids
    for key, label, field, created, existing in [
        ("office", "Office 365", "estado_graph", "CREADO_GRAPH", "EXISTENTE_GRAPH"),
        ("moodle", "Moodle", "estado_moodle", "CREADO_MOODLE", "EXISTENTE_MOODLE"),
    ]:
        if result.get(field) not in {created, existing}:
            continue
        cursor.execute(f"""SELECT TOP (1) id, cedula, correo_institucional, tipo_persona, clave_cifrada, fecha_creacion
            FROM dbo.CREDENCIAL_APROVISIONAMIENTO
            WHERE cedula=? AND LOWER(LTRIM(RTRIM(correo_institucional)))=? AND tipo_persona='ESTUDIANTE'
              AND clave_emitida=1 AND {field}=?
            ORDER BY fecha_creacion DESC, id DESC""", profile["identity"], profile["email"], created)
        row = cursor.fetchone()
        if not row:
            continue
        if (not same_identification(row.cedula, profile["identity"])
                or credentials._clean(row.correo_institucional).lower() != profile["email"]
                or credentials._clean(row.tipo_persona) != "ESTUDIANTE"):
            raise HTTPException(409, detail="La credencial archivada no corresponde al estudiante y correo verificados.")
        if not row.clave_cifrada:
            continue
        try:
            password = credentials._decrypt_credential_password(row.clave_cifrada)
        except RuntimeError as error:
            raise HTTPException(409, detail="No se pudo descifrar la credencial archivada; revise la configuración de cifrado.") from error
        if password:
            passwords[key] = password
            archive_ids.add(int(row.id))
            date = row.fecha_creacion
            dates.append(f"{label}: {date.strftime('%d/%m/%Y %H:%M') if hasattr(date, 'strftime') else date}")
    return passwords, dates, archive_ids


def admission_receipts(request_ids: list[UUID], user: SessionUser) -> bytes:
    require_provisioning_admin(user)
    items, archive_ids = [], set()
    with get_connection() as conn:
        cursor = conn.cursor()
        for request_id in dict.fromkeys(request_ids):
            profile = _profile(cursor, request_id)
            result = ((_read_state(cursor, request_id) or {}).get("result") or {})
            if result.get("correo_institucional") and result["correo_institucional"] != profile["email"]:
                raise HTTPException(409, detail="El correo académico cambió después del aprovisionamiento; vuelva a verificar sus cuentas.")
            passwords, dates, ids = _issued_passwords(cursor, profile, result)
            archive_ids.update(ids)
            cursor.execute("""SELECT c.Nombre_Basica, p.Detalle_Periodo
                FROM dbo.PORTAL_INGRESO_DIRECTO a
                LEFT JOIN dbo.CARRERAS c ON c.Cod_AnioBasica=a.cod_anio_basica
                LEFT JOIN dbo.PERIODO p ON p.cod_periodo=a.codigo_periodo
                WHERE a.solicitud_id=?""", str(request_id))
            academic = cursor.fetchone()
            items.append({"request_id": str(request_id), "identity": profile["identity"], "name": profile["name"],
                "code": profile["code"], "career": academic.Nombre_Basica if academic else None,
                "period": academic.Detalle_Periodo if academic else str(profile["period"]),
                "level": profile["record"].get("nivel"), "email": profile["email"],
                "passwords": passwords, "password_dates": dates, "estado_graph": result.get("estado_graph"),
                "estado_moodle": result.get("estado_moodle"), "estado_licencia": result.get("estado_licencia"),
                "email_synchronized": _email_synchronized(profile, profile["email"]), "errors": result.get("errores") or []})
        content = build_receipt_pdf(items, user.login)
        for record_id in archive_ids:
            cursor.execute("""UPDATE dbo.CREDENCIAL_APROVISIONAMIENTO
                SET numero_descargas=COALESCE(numero_descargas,0)+1,
                    fecha_ultima_descarga=SYSDATETIME(), usuario_ultima_descarga=? WHERE id=?""", user.login, record_id)
        conn.commit()
        return content


def _begin(request_id: UUID, names: CredentialNames, user: SessionUser):
    conn = get_connection()
    acquired = False
    student_lock = None
    try:
        cursor = conn.cursor()
        resource = f"PORTAL_INGRESO_CREDENCIALES:{request_id}"
        cursor.execute("""SET NOCOUNT ON; DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=?, @LockMode='Exclusive',
            @LockOwner='Session', @LockTimeout=0; SELECT @r;""", resource)
        if cursor.fetchone()[0] < 0:
            raise HTTPException(409, detail="Las credenciales de este ingreso ya se están procesando. Consulte su estado.")
        acquired = True
        profile = _profile(cursor, request_id)
        cursor.execute("""DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=?, @LockMode='Exclusive',
            @LockOwner='Session', @LockTimeout=0; SELECT @r;""", f"PORTAL_INGRESO_CREDENCIALES_ESTUDIANTE:{profile['code']}")
        if cursor.fetchone()[0] < 0:
            raise HTTPException(409, detail="Este estudiante ya está verificando sus cuentas en otro ingreso. Consulte su estado antes de reintentar.")
        student_lock = profile["code"]
        original = profile["record"].get("datos_credenciales")
        full_name = f"{names.primer_apellido} {names.segundo_apellido} {names.primer_nombre} {names.segundo_nombre}"
        if (" ".join(full_name.split()) != profile["name"]
                or (original and not names.matches(original["nombres"], original["apellidos"]))):
            raise HTTPException(409, detail="Los nombres de credenciales deben corresponder exactamente al estudiante matriculado.")
        if len(profile["identity"]) < 4:
            raise HTTPException(422, detail="La identificación no permite aplicar la regla establecida para la contraseña.")
        cursor.execute(_SCHEMA)
        previous = _read_state(cursor, request_id)
        person = names.model_dump()
        if previous and previous["persona"] != person:
            raise HTTPException(409, detail="Este ingreso ya inició el aprovisionamiento con otra distribución de nombres; revise su historial.")
        if not previous:
            cursor.execute("INSERT INTO dbo.PORTAL_INGRESO_CREDENCIALES(solicitud_id, persona_json, registrado_por) VALUES (?, ?, ?)",
                           str(request_id), json.dumps(person), user.login)
        processing = {**((previous or {}).get("result") or {}), "estado_general": "PROCESANDO",
                      "observacion": "La matrícula está guardada. Se están verificando las cuentas externas."}
        cursor.execute("UPDATE dbo.PORTAL_INGRESO_CREDENCIALES SET resultado_json=?, fecha_actualizacion=SYSUTCDATETIME() WHERE solicitud_id=?", json.dumps(processing), str(request_id))
        conn.commit()
        return conn, profile, previous
    except Exception:
        conn.rollback()
        if acquired:
            _release(conn, request_id, student_lock)
        else:
            conn.close()
        raise


def _release(conn, request_id, student_code=None):
    try:
        if student_code is not None:
            conn.cursor().execute("EXEC sys.sp_releaseapplock @Resource=?, @LockOwner='Session'", f"PORTAL_INGRESO_CREDENCIALES_ESTUDIANTE:{student_code}")
        conn.cursor().execute("EXEC sys.sp_releaseapplock @Resource=?, @LockOwner='Session'", f"PORTAL_INGRESO_CREDENCIALES:{request_id}")
        conn.commit()
    finally:
        conn.close()


def _local_owner_check(email: str, identity: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        credentials._ensure_tables(cursor)
        cursor.execute("""SELECT identity_code FROM (
            SELECT cedula AS identity_code FROM dbo.CREDENCIAL_IDENTIDAD WHERE LOWER(correo_institucional)=?
            UNION ALL SELECT d.Cedula_Est FROM dbo.DATOS_ESTUD d
            LEFT JOIN dbo.CorreosEstudIntec ce ON ce.codestud=d.codigo_estud
            WHERE LOWER(LTRIM(RTRIM(d.correointec)))=? OR LOWER(LTRIM(RTRIM(ce.CorreoIntec)))=?
        ) owners""", email, email, email)
        if any(not same_identification(row[0], identity) for row in cursor.fetchall()):
            raise RuntimeError("El correo institucional pertenece a otra identidad en INTECBDD.")


async def _remote_identity(person: dict, moodle: MoodleClient, known_email: str):
    identity = person["cedula"]
    reserved_email = await asyncio.to_thread(credentials._existing_email_for_cedula, identity)
    if known_email and reserved_email and reserved_email != known_email:
        raise RuntimeError("La identidad local ya tiene otro correo reservado; revise el historial.")
    known_email = known_email or reserved_email
    graph_matches = await asyncio.to_thread(credentials._graph_users_by_employee_id, identity)
    moodle_matches = await credentials._moodle_users(moodle, "idnumber", identity)
    if len(graph_matches) > 1 or len(moodle_matches) > 1:
        raise RuntimeError("La identificación está asociada a varias cuentas; se requiere una revisión manual.")
    remote_emails = {credentials._valid_institutional_email(item.get("userPrincipalName")) for item in graph_matches}
    remote_emails.update(credentials._valid_institutional_email(item.get("email")) for item in moodle_matches)
    if "" in remote_emails or len(remote_emails) > 1 or (known_email and remote_emails and known_email not in remote_emails):
        raise RuntimeError("Las cuentas existentes no tienen el mismo correo institucional; se requiere una revisión manual.")
    fixed_email = known_email or next(iter(remote_emails), "")
    candidates = [fixed_email] if fixed_email else [f"{local}@{credentials._graph_domain()}" for local in credentials._email_candidates(person)]
    for email in candidates:
        if credentials._valid_institutional_email(email) != email:
            raise RuntimeError("El correo existente no pertenece al dominio de Office 365 configurado.")
        try:
            await asyncio.to_thread(_local_owner_check, email, identity)
            graph_user = await asyncio.to_thread(credentials._graph_user, email)
            by_email = await credentials._moodle_users(moodle, "email", email)
            by_username = await credentials._moodle_users(moodle, "username", email)
            all_moodle = {str(item["id"]): item for item in moodle_matches + by_email + by_username}
            if (graph_user and (not graph_user.get("id") or credentials._clean(graph_user.get("employeeId")) != identity)
                    or any(not item.get("id") or credentials._clean(item.get("idnumber")) != identity for item in all_moodle.values())
                    or len(all_moodle) > 1):
                raise RuntimeError("El correo o nombre de usuario corresponde a otra identidad o no tiene identificación verificada.")
            if graph_matches and (not graph_user or graph_user.get("id") != graph_matches[0].get("id")):
                raise RuntimeError("La cuenta Microsoft 365 no coincide con la identificación encontrada.")
            moodle_user = next(iter(all_moodle.values()), None)
            if moodle_user and credentials._clean(moodle_user.get("email")).lower() != email:
                raise RuntimeError("El usuario Moodle tiene un correo diferente al institucional.")
            if (graph_user and graph_user.get("accountEnabled") is False) or (moodle_user and moodle_user.get("suspended")):
                raise RuntimeError("Una cuenta existente está deshabilitada; no se reactivará automáticamente.")
        except RuntimeError:
            if fixed_email:
                raise
            continue
        reserved = await asyncio.to_thread(credentials._reserve_identity, person, email, person["operator"])
        if reserved != email:
            raise RuntimeError("La identidad fue reservada con otro correo. Consulte el estado antes de reintentar.")
        return email, graph_user, moodle_user
    raise RuntimeError("No existe un correo institucional disponible para este estudiante.")


async def _provision(person: dict, known_email: str, moodle: MoodleClient, license_info):
    email, graph_user, moodle_user = await _remote_identity(person, moodle, known_email)
    assigned = (graph_user or {}).get("assignedLicenses") or []
    if license_info.available_units <= 0 and not any(str(item.get("skuId", "")).lower() == license_info.sku_id for item in assigned):
        raise RuntimeError("No hay licencias educativas disponibles; no se crearon ni modificaron cuentas.")
    password = credentials._permanent_password(person)
    row = {**person, "correo_institucional": email, "estado_graph": "EXISTENTE_GRAPH" if graph_user else "NO_PROCESADO",
           "estado_moodle": "EXISTENTE_MOODLE" if moodle_user else "NO_PROCESADO", "estado_licencia": "OMITIDA",
           "licencia_nombre": license_info.name, "licencia_sku_part_number": license_info.sku_part_number,
           "error_graph": "", "error_moodle": "", "error_licencia": "", "clave_emitida": False, "clave_permanente": ""}
    graph_created = moodle_created = False
    try:
        if not graph_user:
            graph_user = await asyncio.to_thread(credentials._create_graph_user, person, email, password)
            if not graph_user or not graph_user.get("id"):
                raise RuntimeError("Office 365 no confirmó la creación. Reintente para verificar si la cuenta existe.")
            graph_created = True
            row["estado_graph"] = "CREADO_GRAPH"
    except Exception as error:
        row.update(estado_graph="ERROR_GRAPH", error_graph=_safe_error(error, password))
    if graph_user and row["estado_graph"] in {"CREADO_GRAPH", "EXISTENTE_GRAPH"}:
        try:
            row["estado_licencia"], row["error_licencia"] = await asyncio.to_thread(credentials._assign_graph_license, graph_user, license_info)
        except Exception as error:
            row.update(estado_licencia="ERROR_LICENCIA_ESTUDIANTE", error_licencia=_safe_error(error, password))
        if not moodle_user:
            # Recheck both unique fields immediately before creating, including races.
            try:
                row_moodle = await credentials._provision_moodle(moodle, person, email, password, strict_identity=True)
                moodle_user, row["estado_moodle"], row["error_moodle"], moodle_created = row_moodle
            except Exception as error:
                row.update(estado_moodle="ERROR_MOODLE", error_moodle=_safe_error(error, password))
    row.update(graph_user_id=(graph_user or {}).get("id", ""), moodle_user_id=(moodle_user or {}).get("id"),
               moodle_username=(moodle_user or {}).get("username", ""), clave_emitida=graph_created or moodle_created,
               clave_permanente=password if graph_created or moodle_created else "",
               observacion=credentials._credential_observation(graph_created, moodle_created))
    row["estado_general"] = credentials._overall_status(row["estado_graph"], row["estado_licencia"], row["estado_moodle"])
    for key in ("error_graph", "error_licencia", "error_moodle"):
        row[key] = row[key].replace(password, "[CREDENCIAL]")
    return row


def _finish(conn, request_id, person, row, profile):
    cursor = conn.cursor()
    credentials._ensure_tables(cursor)
    batch_id = str(uuid4())
    credentials._record_audit(batch_id, "INDIVIDUAL", [row], person["operator"])
    cursor.execute("SELECT TOP (1) id FROM dbo.CREDENCIAL_APROVISIONAMIENTO WHERE lote_id=? AND clave_emitida=1 ORDER BY id DESC", batch_id)
    report_row = cursor.fetchone()
    report_id = report_row[0] if report_row else None
    result = {key: value for key, value in row.items() if key not in {"clave_permanente", "operator"}}
    result["errores"] = [row[key] for key in ("error_graph", "error_licencia", "error_moodle") if row.get(key)] + row.get("errores", [])
    result["datos_persona"] = {key: person[key] for key in CredentialNames.model_fields}
    if row["estado_graph"] in {"CREADO_GRAPH", "EXISTENTE_GRAPH"}:
        _local_owner_check(row["correo_institucional"], profile["identity"])
        cursor.execute("UPDATE dbo.DATOS_ESTUD SET correointec=? WHERE codigo_estud=? AND Cedula_Est=?", row["correo_institucional"], profile["code"], profile.get("stored_identity", profile["identity"]))
        # Never overwrite existing passwords or pretend an existing password was issued.
        cursor.execute("""UPDATE dbo.CorreosEstudIntec SET CorreoIntec=?,
            CorreoPersonal=COALESCE(NULLIF(?,''),CorreoPersonal), Nombres=?, Periodo=?, Estado=? WHERE codestud=?""",
            row["correo_institucional"], profile.get("personal_email", ""), profile["name"], profile["period"], row["estado_general"], profile["code"])
        cursor.execute("""IF NOT EXISTS (SELECT 1 FROM dbo.CorreosEstudIntec WITH (UPDLOCK, HOLDLOCK) WHERE codestud=?)
            INSERT INTO dbo.CorreosEstudIntec (codestud, Nombres, CorreoPersonal, CorreoIntec, Password,
                fecha, Periodo, CorreoEnviado, Estado, TipoCursoMigra)
            VALUES (?, ?, ?, ?, '', CAST(GETDATE() AS date), ?, 0, ?, 'N')""",
            profile["code"], profile["code"], profile["name"], profile.get("personal_email", ""),
            row["correo_institucional"], profile["period"], row["estado_general"])
        synchronized = _profile(cursor, request_id)
        if not _email_synchronized(synchronized, row["correo_institucional"]):
            raise HTTPException(409, detail="No se pudo unificar el correo en DATOS_ESTUD y CorreosEstudIntec. La matrícula permanece guardada.")
        result["estado_correo_academico"] = "SINCRONIZADO"
    cursor.execute("""UPDATE dbo.PORTAL_INGRESO_CREDENCIALES SET resultado_json=?,
        reporte_credencial_id=COALESCE(?,reporte_credencial_id), fecha_actualizacion=SYSUTCDATETIME() WHERE solicitud_id=?""", json.dumps(result), report_id, str(request_id))
    conn.commit()
    state = _read_state(cursor, request_id)
    return {**result, "reporte_credencial_id": state["report_id"]}


async def provision_admission_credentials(request_id: UUID, names: CredentialNames, user: SessionUser) -> dict[str, Any]:
    require_provisioning_admin(user)
    if not credentials._graph_is_configured() or not credentials._moodle_is_configured():
        raise HTTPException(409, detail="Configure Office 365 y habilite las lecturas y escrituras de Moodle antes de aprovisionar.")
    settings = credentials.get_settings()
    if urlsplit(settings.moodle_base_url).scheme.lower() != "https" or not settings.moodle_verify_tls:
        raise HTTPException(409, detail="El aprovisionamiento requiere Moodle mediante HTTPS y la verificación TLS habilitada.")
    conn, profile, _ = await asyncio.to_thread(_begin, request_id, names, user)
    try:
        person = {**names.model_dump(), "cedula": profile["identity"], "tipo_persona": "ESTUDIANTE", "operator": user.login}
        try:
            license_info = await asyncio.to_thread(credentials._education_license, "ESTUDIANTE", True)
            async with httpx.AsyncClient(timeout=float(settings.moodle_timeout_seconds), verify=bool(settings.moodle_verify_tls)) as http:
                row = await _provision(person, profile["email"], MoodleClient(settings, http), license_info)
        except Exception as error:
            row = {**person, "estado_general": "ERROR", "estado_graph": "NO_PROCESADO", "estado_moodle": "NO_PROCESADO",
                   "estado_licencia": "OMITIDA", "clave_emitida": False, "clave_permanente": "", "errores": [credentials._graph_error_detail(error)],
                   "observacion": "La matrícula permanece guardada. Verifique las cuentas existentes antes de reintentar."}
        return await asyncio.to_thread(_finish, conn, request_id, person, row, profile)
    except Exception:
        await asyncio.to_thread(conn.rollback)
        raise
    finally:
        await asyncio.to_thread(_release, conn, request_id, profile["code"])
