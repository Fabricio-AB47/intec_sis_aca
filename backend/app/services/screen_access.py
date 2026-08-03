from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.db import get_integration_control_connection


ROLE_CATALOG: tuple[dict[str, str], ...] = (
    {"value": "ADMINISTRADOR", "label": "Administrador", "description": "Acceso total y configuracion institucional."},
    {"value": "ACADEMICO", "label": "Academico", "description": "Matricula, estudiantes, notas y titulacion."},
    {"value": "BIENESTAR", "label": "Bienestar", "description": "Indicadores, becas, calificaciones y acompanamiento estudiantil."},
    {"value": "ADMISIONES", "label": "Admisiones", "description": "Inscripcion, aspirantes y matricula inicial."},
    {"value": "FINANCIERO", "label": "Financiero", "description": "Pagos, convenios, becas e ingresos."},
    {"value": "SECRETARIA", "label": "Secretaria", "description": "Practicas, grado, titulacion y registros."},
    {"value": "SOPORTE", "label": "Soporte", "description": "Soporte tecnico y operacion extendida."},
    {"value": "INVITADO_SOP", "label": "Invitado de soporte", "description": "Consulta tecnica temporal y controlada."},
    {"value": "RECTOR", "label": "Rector", "description": "Consulta ejecutiva de indicadores."},
    {"value": "VICERRECTOR", "label": "Vicerrector", "description": "Consulta ejecutiva y seguimiento."},
    {"value": "DOCENTE", "label": "Docente", "description": "Cursos, calificaciones y documentos docentes."},
    {"value": "ESTUDIANTE", "label": "Estudiante", "description": "Portal academico y servicios estudiantiles."},
)


def _screen(page: str, label: str, description: str, group: str) -> dict[str, str]:
    return {"page": page, "label": label, "description": description, "group": group}


SCREEN_CATALOG: tuple[dict[str, str], ...] = (
    _screen("dashboard", "Dashboard", "Indicadores generales y resumen institucional.", "Inicio"),
    _screen("sistema-academico", "Sistema academico", "Flujo academico institucional integrado.", "Inicio"),
    _screen("preinscripcion", "Preinscripcion y becas", "Aspirantes, inscripcion, becas y matricula inicial.", "Admision"),
    _screen("matricula", "Consulta de matricula", "Resumen y consulta general de matriculas.", "Matricula"),
    _screen("matricula-acad", "Matricula academica", "Cabecera, materias y control academico.", "Matricula"),
    _screen("matricula-docente", "Matricula docente", "Asignacion docente por materia y periodo.", "Docencia"),
    _screen("estado-docente", "Estado docente", "Activacion, inactivacion y observaciones docentes.", "Docencia"),
    _screen("actualizar-datos-estudiante", "Actualizacion de datos", "Datos personales de estudiantes y docentes.", "Personas"),
    _screen("gestion-sisacademico", "Gestion operativa", "Tablas y procesos modernizados de SisAcademicoV1.", "Operacion"),
    _screen("asignacion-pantallas", "Asignacion de pantallas", "Permisos de navegacion por tipo de usuario.", "Administracion"),
    _screen("periodo-academico", "Periodo academico", "Resumen por periodo y estudiantes.", "Academico"),
    _screen("periodo-matriculados", "Matriculados por periodo", "Detalle de matriculados por periodo academico.", "Academico"),
    _screen("admin-notas-asignatura", "Notas por asignatura", "Docente, asignatura, periodo y estudiantes.", "Calificaciones"),
    _screen("reporteria-carreras", "Reporteria por carreras", "Indicadores y resultados por carrera.", "Reportes"),
    _screen("reporteria-integral", "Reporteria integral", "Reportes institucionales modernos.", "Reportes"),
    _screen("reportes-individuales", "Reportes individuales", "Notas y documentos por estudiante o docente.", "Reportes"),
    _screen("senescyt-estudiantes", "Datos SENESCYT", "Reportes regulatorios y datos de estudiantes.", "Reportes"),
    _screen("rango-edades", "Rangos de edad", "Distribucion estudiantil por edades.", "Reportes"),
    _screen("ingreso-ventas", "Ingresos y ventas", "Movimientos e indicadores financieros.", "Financiero"),
    _screen("cruce-datos", "Cruce de datos", "Comparacion de informacion academica y archivos.", "Herramientas"),
    _screen("validar-excel", "Validar Excel", "Validacion estructurada de archivos de carga.", "Herramientas"),
    _screen("teams", "Movimientos Teams", "Equipos, clases, grabaciones y actividad Microsoft 365.", "Microsoft 365"),
    _screen("teams-matricula", "Matricula en Teams", "Creacion de aulas y matriculacion en Microsoft Teams.", "Microsoft 365"),
    _screen("certificados", "Certificados", "Emision y consulta de certificados.", "Documentos"),
    _screen("matricula-excel-certificados", "Certificados desde Excel", "Generacion masiva de certificados desde Excel.", "Documentos"),
    _screen("renombrar-certificados", "Renombrar certificados", "Organizacion y renombrado de documentos.", "Documentos"),
    _screen("credenciales", "Credenciales", "Generacion institucional de credenciales.", "Documentos"),
    _screen("correos-masivos", "Correos masivos", "Envios institucionales y documentos asociados.", "Comunicacion"),
    _screen("carnet-institucional", "Carnet institucional", "Foto, aprobacion y emision de carnets.", "Comunicacion"),
    _screen("fecha-grado", "Fecha de grado", "Carga SENESCYT, actas y datos de grado.", "Titulacion"),
    _screen("titulacion", "Verificacion de titulacion", "Requisitos previos y seleccion de modalidad.", "Titulacion"),
    _screen("titulacion-proceso", "Proceso de titulacion", "Complexivo, defensa, fechas y enlaces.", "Titulacion"),
    _screen("titulacion-responsables", "Responsables de titulacion", "Tribunal y responsables de examen complexivo.", "Titulacion"),
    _screen("titulos-registrados", "Titulos registrados", "Registro y documentos de titulos emitidos.", "Titulacion"),
    _screen("practicas-institucionales", "Practicas institucionales", "Practicas preprofesionales y vinculacion con la sociedad.", "Practicas"),
    _screen("evaluacion-docente", "Evaluacion docente", "Formulario de evaluacion para estudiantes.", "Evaluacion"),
    _screen("evaluacion-docente-admin", "Administrar evaluacion", "Configuracion administrativa de evaluaciones.", "Evaluacion"),
    _screen("evaluacion-docente-avance", "Avance de evaluacion", "Seguimiento y ponderacion de evaluaciones.", "Evaluacion"),
    _screen("evaluacion-docente-reportes", "Reportes de evaluacion", "Documentos y resultados de evaluacion docente.", "Evaluacion"),
    _screen("formato-informe-docente", "Formato de informe docente", "Configuracion institucional del informe docente.", "Evaluacion"),
    _screen("portal-estudiante", "Portal estudiante", "Malla, notas y estado academico del estudiante.", "Portales"),
    _screen("ingles", "Evaluacion de Ingles", "Entrega, expediente y calificacion del examen de Ingles.", "Portales"),
    _screen("expedientes-documentales", "Expedientes documentales", "Documentos de Ingles, titulacion, practicas y vinculacion almacenados en Microsoft 365.", "Documentos"),
    _screen("portal-docente", "Portal docente", "Cursos, estudiantes y registro de notas.", "Portales"),
    _screen("portal-docente-informe", "Informe docente", "Informe de cumplimiento y firma electronica.", "Portales"),
    _screen("portal-docente-planificacion", "Silabo y PEA", "Planificacion academica y firma electronica.", "Portales"),
    _screen("portal-docente-contratos", "Contrato docente", "Condiciones contractuales y carga asignada.", "Portales"),
)


ALL_PAGES: tuple[str, ...] = tuple(screen["page"] for screen in SCREEN_CATALOG)
ADMIN_ONLY_PAGES = frozenset({"sistema-academico", "asignacion-pantallas"})
ROLE_DENIED_PAGES: dict[str, frozenset[str]] = {
    "ESTUDIANTE": frozenset({"expedientes-documentales"}),
}

_ACADEMIC_PAGES = (
    "dashboard", "preinscripcion", "matricula", "matricula-acad",
    "matricula-docente", "estado-docente", "actualizar-datos-estudiante",
    "reportes-individuales", "admin-notas-asignatura", "reporteria-integral",
    "gestion-sisacademico", "periodo-academico",
    "periodo-matriculados", "rango-edades", "certificados", "fecha-grado",
    "titulacion", "titulacion-proceso", "titulacion-responsables",
    "matricula-excel-certificados", "renombrar-certificados", "carnet-institucional",
    "evaluacion-docente-avance", "evaluacion-docente-reportes",
    "formato-informe-docente", "practicas-institucionales",
    "ingles", "expedientes-documentales",
)

DEFAULT_ACCESS: dict[str, tuple[str, ...]] = {
    "ADMINISTRADOR": ALL_PAGES,
    "ACADEMICO": _ACADEMIC_PAGES,
    "BIENESTAR": (
        "dashboard", "preinscripcion", "actualizar-datos-estudiante",
        "admin-notas-asignatura", "reportes-individuales", "reporteria-integral",
        "carnet-institucional",
    ),
    "ADMISIONES": ("dashboard", "preinscripcion", "gestion-sisacademico"),
    "FINANCIERO": (
        "dashboard", "preinscripcion", "ingreso-ventas",
        "gestion-sisacademico", "reporteria-integral",
        "carnet-institucional",
    ),
    "SECRETARIA": (
        "practicas-institucionales", "fecha-grado",
        "senescyt-estudiantes", "titulacion", "titulacion-proceso",
        "titulacion-responsables", "titulos-registrados", "expedientes-documentales",
    ),
    "SOPORTE": tuple(
        page for page in ALL_PAGES
        if page not in ADMIN_ONLY_PAGES
        and not page.startswith("portal-")
        and page not in {"evaluacion-docente", "asignacion-pantallas", "expedientes-documentales"}
    ),
    "INVITADO_SOP": ("dashboard", "teams"),
    "RECTOR": ("dashboard",),
    "VICERRECTOR": ("dashboard",),
    "DOCENTE": (
        "portal-docente", "portal-docente-informe", "portal-docente-planificacion",
        "portal-docente-contratos", "ingles", "carnet-institucional",
    ),
    "ESTUDIANTE": ("portal-estudiante", "ingles", "evaluacion-docente", "practicas-institucionales", "carnet-institucional"),
}

_TP_US_ROLE_CATALOG = {
    "1": "ADMINISTRADOR",
    "2": "FINANCIERO",
    "3": "BIENESTAR",
    "4": "ACADEMICO",
    "5": "ADMISIONES",
    "6": "RECTOR",
    "7": "VICERRECTOR",
    "8": "SOPORTE",
    "9": "INVITADO_SOP",
    "10": "SECRETARIA",
}

_ROLE_ALIASES = {
    **_TP_US_ROLE_CATALOG,
    "ADM": "ADMINISTRADOR",
    "ADMIN": "ADMINISTRADOR",
    "ADMINISTRACION": "ADMINISTRADOR",
    "ADMINISTRADOR": "ADMINISTRADOR",
    "ACA": "ACADEMICO",
    "ACADEMICA": "ACADEMICO",
    "ACADEMICO": "ACADEMICO",
    "ADMISION": "ADMISIONES",
    "ADMISIONES": "ADMISIONES",
    "BIENESTAR": "BIENESTAR",
    "BIENESTAR ESTUDIANTIL": "BIENESTAR",
    "DOC": "DOCENTE",
    "DOCENTE": "DOCENTE",
    "EST": "ESTUDIANTE",
    "ESTUDIANTE": "ESTUDIANTE",
    "FIN": "FINANCIERO",
    "FINANCIERO": "FINANCIERO",
    "INVITADO": "INVITADO_SOP",
    "INVITADO DE SOPORTE": "INVITADO_SOP",
    "INVITADO SOP": "INVITADO_SOP",
    "REC": "RECTOR",
    "RECTOR": "RECTOR",
    "SECRETARIA": "SECRETARIA",
    "SECRETARIA ACADEMICA": "SECRETARIA",
    "SOPORTE": "SOPORTE",
    "SOPORTE TECNICO": "SOPORTE",
    "TECNOLOGIA": "SOPORTE",
    "TI": "SOPORTE",
    "VICERRECTOR": "VICERRECTOR",
}


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().upper().replace("_", " ").replace("-", " ")
    role = "".join(
        character
        for character in unicodedata.normalize("NFD", role)
        if unicodedata.category(character) != "Mn"
    )
    role = " ".join(role.split())
    return _ROLE_ALIASES.get(role, role)


def _ensure_tables(cursor: Any) -> None:
    cursor.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cfg')
            EXEC(N'CREATE SCHEMA cfg AUTHORIZATION dbo');

        IF OBJECT_ID(N'cfg.PantallaPortal', N'U') IS NULL
        BEGIN
            CREATE TABLE cfg.PantallaPortal
            (
                Codigo VARCHAR(80) NOT NULL CONSTRAINT PK_PantallaPortal PRIMARY KEY,
                Nombre NVARCHAR(160) NOT NULL,
                Descripcion NVARCHAR(500) NULL,
                Grupo NVARCHAR(100) NOT NULL,
                Orden INT NOT NULL,
                Activo BIT NOT NULL CONSTRAINT DF_PantallaPortal_Activo DEFAULT 1,
                FechaActualizacion DATETIME2 NOT NULL CONSTRAINT DF_PantallaPortal_Fecha DEFAULT SYSDATETIME()
            );
        END;

        IF OBJECT_ID(N'cfg.AccesoPantallaRol', N'U') IS NULL
        BEGIN
            CREATE TABLE cfg.AccesoPantallaRol
            (
                RolCodigo VARCHAR(40) NOT NULL,
                PantallaCodigo VARCHAR(80) NOT NULL,
                Activo BIT NOT NULL CONSTRAINT DF_AccesoPantallaRol_Activo DEFAULT 1,
                FechaActualizacion DATETIME2 NOT NULL CONSTRAINT DF_AccesoPantallaRol_Fecha DEFAULT SYSDATETIME(),
                UsuarioActualizacion NVARCHAR(128) NULL,
                CONSTRAINT PK_AccesoPantallaRol PRIMARY KEY (RolCodigo, PantallaCodigo),
                CONSTRAINT FK_AccesoPantallaRol_Pantalla FOREIGN KEY (PantallaCodigo)
                    REFERENCES cfg.PantallaPortal(Codigo)
            );
        END;
        """
    )


def _sync_catalog(cursor: Any) -> None:
    for order, screen in enumerate(SCREEN_CATALOG, start=1):
        cursor.execute(
            """
            MERGE cfg.PantallaPortal AS target
            USING (SELECT ? AS Codigo, ? AS Nombre, ? AS Descripcion, ? AS Grupo, ? AS Orden) AS source
               ON target.Codigo = source.Codigo
            WHEN MATCHED AND
            (
                ISNULL(target.Nombre, N'') <> ISNULL(source.Nombre, N'')
                OR ISNULL(target.Descripcion, N'') <> ISNULL(source.Descripcion, N'')
                OR ISNULL(target.Grupo, N'') <> ISNULL(source.Grupo, N'')
                OR target.Orden <> source.Orden
                OR target.Activo <> 1
            ) THEN
                UPDATE SET Nombre = source.Nombre,
                           Descripcion = source.Descripcion,
                           Grupo = source.Grupo,
                           Orden = source.Orden,
                           Activo = 1,
                           FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (Codigo, Nombre, Descripcion, Grupo, Orden, Activo)
                VALUES (source.Codigo, source.Nombre, source.Descripcion, source.Grupo, source.Orden, 1);
            """,
            screen["page"],
            screen["label"],
            screen["description"],
            screen["group"],
            order,
        )

    placeholders = ", ".join("?" for _ in ALL_PAGES)
    cursor.execute(
        f"UPDATE cfg.PantallaPortal SET Activo = 0, FechaActualizacion = SYSDATETIME() WHERE Activo <> 0 AND Codigo NOT IN ({placeholders})",
        *ALL_PAGES,
    )

    # Los expedientes institucionales contienen documentos internos. Aunque
    # exista una asignacion historica, nunca se exponen al perfil estudiante.
    for role, denied_pages in ROLE_DENIED_PAGES.items():
        for page in denied_pages:
            cursor.execute(
                """
                UPDATE cfg.AccesoPantallaRol
                   SET Activo = 0,
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = N'SISTEMA'
                 WHERE RolCodigo = ? AND PantallaCodigo = ? AND Activo <> 0
                """,
                role,
                page,
            )


def _initialize_role_assignments(cursor: Any) -> None:
    """Materializa una sola vez la configuracion inicial de cada perfil."""
    cursor.execute("SELECT DISTINCT RolCodigo FROM cfg.AccesoPantallaRol")
    configured_roles: set[str] = set()
    for row in cursor.fetchall():
        role_value = getattr(row, "RolCodigo", None)
        configured_roles.add(normalize_role(role_value if role_value is not None else row[0]))

    for role_meta in ROLE_CATALOG:
        role = role_meta["value"]
        if role == "ADMINISTRADOR" or role in configured_roles:
            continue

        denied_pages = ROLE_DENIED_PAGES.get(role, frozenset())
        initial_pages = {
            page
            for page in DEFAULT_ACCESS.get(role, ())
            if page not in ADMIN_ONLY_PAGES and page not in denied_pages
        }
        for page in ALL_PAGES:
            cursor.execute(
                """
                MERGE cfg.AccesoPantallaRol AS target
                USING (SELECT ? AS RolCodigo, ? AS PantallaCodigo, ? AS Activo) AS source
                   ON target.RolCodigo = source.RolCodigo
                  AND target.PantallaCodigo = source.PantallaCodigo
                WHEN NOT MATCHED THEN
                    INSERT (RolCodigo, PantallaCodigo, Activo, UsuarioActualizacion)
                    VALUES (source.RolCodigo, source.PantallaCodigo, source.Activo, N'SISTEMA_INICIAL');
                """,
                role,
                page,
                int(page in initial_pages),
            )


def _as_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _ordered_pages(values: Iterable[str]) -> list[str]:
    selected = {str(value).strip() for value in values if str(value).strip() in ALL_PAGES}
    return [page for page in ALL_PAGES if page in selected]


def _role_payloads(cursor: Any, roles: Iterable[str]) -> list[dict[str, Any]]:
    role_codes = [normalize_role(role) for role in roles]
    stored: dict[str, dict[str, Any]] = {}
    if role_codes:
        placeholders = ", ".join("?" for _ in role_codes)
        cursor.execute(
            f"""
            SELECT RolCodigo, PantallaCodigo, Activo, FechaActualizacion, UsuarioActualizacion
            FROM cfg.AccesoPantallaRol
            WHERE RolCodigo IN ({placeholders})
            """,
            *role_codes,
        )
        for row in cursor.fetchall():
            role = normalize_role(row.RolCodigo)
            entry = stored.setdefault(role, {"rows": 0, "pages": [], "updated_at": None, "updated_by": None})
            entry["rows"] += 1
            if bool(row.Activo) and str(row.PantallaCodigo) in ALL_PAGES:
                entry["pages"].append(str(row.PantallaCodigo))
            if not entry["updated_at"] or row.FechaActualizacion > entry["updated_at"]:
                entry["updated_at"] = row.FechaActualizacion
                entry["updated_by"] = str(row.UsuarioActualizacion or "").strip() or None

    metadata = {item["value"]: item for item in ROLE_CATALOG}
    result: list[dict[str, Any]] = []
    for role in role_codes:
        meta = metadata[role]
        configured = role in stored and stored[role]["rows"] > 0
        # La navegacion efectiva siempre sale de cfg.AccesoPantallaRol. Los
        # valores recomendados solo se usan al inicializar un perfil nuevo.
        pages = _ordered_pages(stored[role]["pages"]) if configured else []
        if role == "ADMINISTRADOR":
            pages = list(ALL_PAGES)
        else:
            denied_pages = ROLE_DENIED_PAGES.get(role, frozenset())
            pages = [
                page
                for page in pages
                if page not in ADMIN_ONLY_PAGES and page not in denied_pages
            ]
        result.append(
            {
                **meta,
                "pages": pages,
                "default_pages": list(DEFAULT_ACCESS.get(role, ())),
                "configured": configured,
                "protected": role == "ADMINISTRADOR",
                "updated_at": _as_iso(stored.get(role, {}).get("updated_at")),
                "updated_by": stored.get(role, {}).get("updated_by"),
            }
        )
    return result


def get_screen_access(role: str, *, include_all: bool = False) -> dict[str, Any]:
    current_role = normalize_role(role)
    valid_roles = {item["value"] for item in ROLE_CATALOG}
    if current_role not in valid_roles:
        raise ValueError("El tipo de usuario no forma parte del catalogo de accesos.")

    requested_roles = [item["value"] for item in ROLE_CATALOG] if include_all else [current_role]
    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        _ensure_tables(cursor)
        _sync_catalog(cursor)
        _initialize_role_assignments(cursor)
        roles = _role_payloads(cursor, requested_roles)
        conn.commit()

    return {
        "source": "INTEC_INTEGRACION_CONTROL.cfg",
        "synchronized_at": datetime.now(timezone.utc).isoformat(),
        "current_role": current_role,
        "screens": list(SCREEN_CATALOG),
        "roles": roles,
    }


def save_screen_access(role: str, pages: Iterable[str], *, updated_by: str) -> dict[str, Any]:
    role_code = normalize_role(role)
    valid_roles = {item["value"] for item in ROLE_CATALOG}
    if role_code not in valid_roles:
        raise ValueError("El tipo de usuario no forma parte del catalogo de accesos.")

    requested_pages = [str(page).strip() for page in pages]
    invalid_pages = sorted({page for page in requested_pages if page not in ALL_PAGES})
    if invalid_pages:
        raise ValueError(f"Pantallas no reconocidas: {', '.join(invalid_pages)}")
    denied_pages = sorted(set(requested_pages) & ROLE_DENIED_PAGES.get(role_code, frozenset()))
    if denied_pages:
        raise ValueError(
            f"El perfil {role_code} no puede acceder a: {', '.join(denied_pages)}"
        )
    allowed_requested_pages = [
        page
        for page in requested_pages
        if role_code == "ADMINISTRADOR" or page not in ADMIN_ONLY_PAGES
    ]
    if role_code != "ADMINISTRADOR" and not allowed_requested_pages:
        raise ValueError("Debe asignar al menos una pantalla al tipo de usuario.")

    selected_pages = set(ALL_PAGES if role_code == "ADMINISTRADOR" else allowed_requested_pages)
    audit_user = str(updated_by or "SISTEMA").strip()[:128] or "SISTEMA"

    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        _ensure_tables(cursor)
        _sync_catalog(cursor)
        _initialize_role_assignments(cursor)
        cursor.execute(
            "UPDATE cfg.AccesoPantallaRol SET Activo = 0, FechaActualizacion = SYSDATETIME(), UsuarioActualizacion = ? WHERE RolCodigo = ?",
            audit_user,
            role_code,
        )
        for page in ALL_PAGES:
            cursor.execute(
                """
                MERGE cfg.AccesoPantallaRol AS target
                USING (SELECT ? AS RolCodigo, ? AS PantallaCodigo, ? AS Activo) AS source
                   ON target.RolCodigo = source.RolCodigo
                  AND target.PantallaCodigo = source.PantallaCodigo
                WHEN MATCHED THEN
                    UPDATE SET Activo = source.Activo,
                               FechaActualizacion = SYSDATETIME(),
                               UsuarioActualizacion = ?
                WHEN NOT MATCHED THEN
                    INSERT (RolCodigo, PantallaCodigo, Activo, UsuarioActualizacion)
                    VALUES (source.RolCodigo, source.PantallaCodigo, source.Activo, ?);
                """,
                role_code,
                page,
                int(page in selected_pages),
                audit_user,
                audit_user,
            )
        role_payload = _role_payloads(cursor, [role_code])[0]
        conn.commit()
    return role_payload
