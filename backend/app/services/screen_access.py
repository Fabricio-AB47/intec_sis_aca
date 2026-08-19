from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable

import pyodbc

from app.services.db import get_integration_control_connection


class ScreenAccessUnavailableError(RuntimeError):
    """Raised when the central screen assignment cannot be consulted."""


_catalog_bootstrap_lock = Lock()
_catalog_bootstrapped = False


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
    return {
        "page": page,
        "label": label,
        "description": description,
        "group": group,
        "parent_page": "",
        "kind": "screen",
    }


def _flow(parent_page: str, key: str, label: str, group: str) -> dict[str, str]:
    return {
        "page": f"{parent_page}/{key}",
        "label": label,
        "description": f"Acceso independiente al flujo {label.lower()}.",
        "group": group,
        "parent_page": parent_page,
        "kind": "flow",
    }


BASE_SCREEN_CATALOG: tuple[dict[str, str], ...] = (
    _screen("dashboard", "Dashboard", "Indicadores generales y resumen institucional.", "Inicio"),
    _screen("sistema-academico", "Sistema academico", "Flujo academico institucional integrado.", "Inicio"),
    _screen(
        "preinscripcion",
        "Inscripcion de estudiantes",
        "Registro previo, inscripcion, becas y matricula inicial.",
        "Inscripcion",
    ),
    _screen("matricula", "Consulta de matriculas", "Resumen y consulta general de matriculas.", "Matricula"),
    _screen(
        "matricula-acad",
        "Matriculacion academica",
        "Registro y actualizacion de la cabecera de matricula y materias del estudiante.",
        "Matricula",
    ),
    _screen("matricula-docente", "Matricula docente", "Asignacion docente por materia y periodo.", "Docencia"),
    _screen("estado-docente", "Estado docente", "Activacion, inactivacion y observaciones docentes.", "Docencia"),
    _screen("actualizar-datos-estudiante", "Actualizacion de datos", "Datos personales de estudiantes y docentes.", "Personas"),
    _screen(
        "actualizar-correo-intec",
        "Actualizacion de correo INTEC",
        "Consulta, comparacion y actualizacion individual o masiva del correo institucional estudiantil.",
        "Actualizaciones",
    ),
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
    _screen("portal-estudiante", "Inicio del estudiante", "Resumen y estado academico del estudiante.", "Portal estudiante"),
    _screen("portal-estudiante-malla-curricular", "Malla curricular del estudiante", "Materias, niveles, codigos y creditos de la carrera.", "Portal estudiante"),
    _screen("portal-estudiante-malla-academica", "Avance de malla del estudiante", "Materias aprobadas, pendientes y avance academico.", "Portal estudiante"),
    _screen("portal-estudiante-calificaciones", "Calificaciones del estudiante", "Notas del estudiante organizadas por periodo academico.", "Portal estudiante"),
    _screen(
        "ingles",
        "Escuela de Idiomas",
        "Matricula vigente, evidencias por parcial y calificaciones de idiomas.",
        "Calificaciones",
    ),
    _screen("expedientes-documentales", "Expedientes documentales", "Documentos de Ingles, titulacion, practicas y vinculacion almacenados en Microsoft 365.", "Documentos"),
    _screen("portal-docente", "Cursos y calificaciones docentes", "Cursos asignados, estudiantes y registro de calificaciones.", "Portal docente"),
    _screen("portal-docente-informe", "Informe docente", "Informe de cumplimiento y firma electronica.", "Portales"),
    _screen("portal-docente-planificacion", "Silabo y PEA", "Planificacion academica y firma electronica.", "Portales"),
    _screen("portal-docente-contratos", "Contrato docente", "Condiciones contractuales y carga asignada.", "Portales"),
)


PREINSCRIPTION_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    _flow("preinscripcion", "registro", "Inscripcion", "Inscripcion / Flujo"),
    _flow("preinscripcion", "inscritos", "Estudiantes inscritos", "Inscripcion / Flujo"),
    _flow("preinscripcion", "cabecera", "Cabecera de matricula", "Inscripcion / Matricula"),
    _flow("preinscripcion", "documentos", "Documentos de matricula", "Inscripcion / Matricula"),
    _flow("preinscripcion", "materias", "Matricular primer nivel", "Inscripcion / Matricula"),
    _flow("preinscripcion", "seguimiento", "Seguimiento de inscripcion", "Inscripcion / Seguimiento"),
    _flow("preinscripcion", "gestion-becas", "Gestion de becas", "Inscripcion / Becas"),
    _flow("preinscripcion", "becas", "Aprobaciones de becas", "Inscripcion / Becas"),
    _flow("preinscripcion", "becados", "Listado de becados", "Inscripcion / Becas"),
)


MATRICULA_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    _flow("matricula-acad", "individual", "Matricula individual", "Matricula / Operacion"),
    _flow("matricula-acad", "masiva", "Matricula masiva", "Matricula / Operacion"),
    _flow(
        "matricula-acad",
        "prerrequisitos",
        "Prerrequisitos de materias",
        "Matricula / Control academico",
    ),
)


SISACADEMICO_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    _flow("gestion-sisacademico", "preinscripciones", "Aspirantes y asesores", "Operacion / Matricula"),
    _flow("gestion-sisacademico", "datos_factura", "Datos de factura", "Operacion / Matricula"),
    _flow("gestion-sisacademico", "cabecera_matricula", "Cabecera de matricula y pagos", "Operacion / Matricula"),
    _flow("gestion-sisacademico", "matricula_materias", "Materias matriculadas y notas", "Operacion / Matricula"),
    _flow("gestion-sisacademico", "pagos_matricula", "Pagos y valores", "Operacion / Matricula"),
    _flow("gestion-sisacademico", "estudiantes", "Ficha del estudiante", "Operacion / Estudiantes"),
    _flow("gestion-sisacademico", "registro_documentos_estudiante", "Documentos del estudiante", "Operacion / Estudiantes"),
    _flow("gestion-sisacademico", "seguimiento", "Seguimiento academico", "Operacion / Estudiantes"),
    _flow("gestion-sisacademico", "actualizacion_estudiantes", "Estado del estudiante", "Operacion / Estudiantes"),
    _flow("gestion-sisacademico", "docentes", "Ficha docente", "Operacion / Docentes"),
    _flow("gestion-sisacademico", "docente_materias", "Materias asignadas al docente", "Operacion / Docentes"),
    _flow("gestion-sisacademico", "actualizacion_est", "Estado docente", "Operacion / Docentes"),
    _flow("gestion-sisacademico", "numero_preguntas", "Control de cuestionarios", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "cuestionarios", "Banco de preguntas", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "preguntas_evaluacion", "Preguntas de evaluacion", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "planes_foros", "Planes, cuestionarios y foros", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "evaluacion_resultados", "Resultados de evaluacion", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "autoevaluacion_resultados", "Resultados de autoevaluacion", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "fechas_autoevaluacion", "Apertura de autoevaluacion", "Operacion / Evaluacion"),
    _flow("gestion-sisacademico", "usuarios", "Registrar usuarios", "Operacion / Seguridad"),
    _flow("gestion-sisacademico", "menu_usuarios", "Accesos por usuario", "Operacion / Seguridad"),
    _flow("gestion-sisacademico", "menu_general", "Mapa operativo", "Operacion / Seguridad"),
    _flow("gestion-sisacademico", "talento_humano_empleados", "Empleados", "Operacion / Talento humano"),
    _flow("gestion-sisacademico", "talento_humano_solicitudes", "Solicitudes de talento humano", "Operacion / Talento humano"),
    _flow("gestion-sisacademico", "talento_humano_tareas", "Tareas de talento humano", "Operacion / Talento humano"),
    _flow("gestion-sisacademico", "moodle_notas", "Notas Moodle", "Operacion / Integraciones"),
    _flow("gestion-sisacademico", "moodle_sincronizacion", "Sincronizacion Moodle", "Operacion / Integraciones"),
    _flow("gestion-sisacademico", "microsoft365_audit", "Auditoria Microsoft 365", "Operacion / Integraciones"),
    _flow("gestion-sisacademico", "practicas", "Practicas profesionales", "Operacion / Practicas"),
    _flow("gestion-sisacademico", "practicas_vinculacion", "Vinculacion con la sociedad", "Operacion / Practicas"),
    _flow("gestion-sisacademico", "empresas", "Empresas de practicas", "Operacion / Practicas"),
    _flow("gestion-sisacademico", "carreras", "Carreras", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "materias", "Materias y pensum", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "mallas", "Mallas academicas", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "materia_homo_textof", "Textos de materias de homologacion", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "paralelos", "Paralelos", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "periodos", "Periodos academicos", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "provincias", "Provincias", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "jornadas", "Jornadas", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "modalidades", "Modalidades", "Operacion / Catalogos"),
    _flow("gestion-sisacademico", "fechas_notas", "Apertura de notas", "Operacion / Control academico"),
    _flow("gestion-sisacademico", "asistencia_estudiantes", "Asistencia de estudiantes", "Operacion / Control academico"),
    _flow("gestion-sisacademico", "dias_matricula", "Dias de matricula", "Operacion / Control academico"),
    _flow("gestion-sisacademico", "horarios_matricula", "Horarios de matricula", "Operacion / Control academico"),
    _flow("gestion-sisacademico", "cambio_periodo_hr", "Migracion de homologacion a regular", "Operacion / Control academico"),
    _flow("gestion-sisacademico", "certificados_generados", "Historial de certificados", "Operacion / Documentos"),
    _flow("gestion-sisacademico", "credenciales_curso", "Credenciales de curso", "Operacion / Documentos"),
    _flow("gestion-sisacademico", "repositorio", "Repositorio digital", "Operacion / Documentos"),
    _flow("gestion-sisacademico", "cursos_edu_continua", "Cursos de educacion continua", "Operacion / Educacion continua"),
    _flow("gestion-sisacademico", "corte_curso", "Cortes de curso", "Operacion / Educacion continua"),
    _flow("gestion-sisacademico", "corte_curso_estudiante", "Estudiantes por corte", "Operacion / Educacion continua"),
)


REPORT_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    _flow("reporteria-integral", "carrera", "Reporte por carrera", "Reporteria / Institucional"),
    _flow("reporteria-integral", "genero", "Reporte por genero", "Reporteria / Institucional"),
    _flow("reporteria-integral", "genero_docentes", "Genero de docentes", "Reporteria / Institucional"),
    _flow("reporteria-integral", "graduados_2025", "Reporte de graduados", "Reporteria / Institucional"),
    _flow("reporteria-integral", "periodo", "Reporte por periodo", "Reporteria / Institucional"),
    _flow("reporteria-integral", "provincia", "Reporte por provincia", "Reporteria / Institucional"),
    _flow("reportes-individuales", "evaluacion_docente", "Evaluacion docente individual", "Reporteria / Individual"),
    _flow("reportes-individuales", "notas_carrera_materia", "Calificaciones de estudiantes", "Reporteria / Individual"),
)


TITLE_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    _flow("titulos-registrados", "senescyt", "Titulos registrados SENESCYT", "Titulacion / Registros"),
    _flow("titulos-registrados", "institucional", "Titulos institucionales", "Titulacion / Registros"),
)


FLOW_SCREEN_CATALOG = (
    PREINSCRIPTION_FLOW_CATALOG
    + MATRICULA_FLOW_CATALOG
    + SISACADEMICO_FLOW_CATALOG
    + REPORT_FLOW_CATALOG
    + TITLE_FLOW_CATALOG
)
SCREEN_CATALOG: tuple[dict[str, str], ...] = BASE_SCREEN_CATALOG + FLOW_SCREEN_CATALOG

FLOW_PARENT_BY_PAGE: dict[str, str] = {
    screen["page"]: screen["parent_page"]
    for screen in FLOW_SCREEN_CATALOG
}
FLOW_PAGES_BY_PARENT: dict[str, tuple[str, ...]] = {
    parent: tuple(
        screen["page"]
        for screen in FLOW_SCREEN_CATALOG
        if screen["parent_page"] == parent
    )
    for parent in {screen["parent_page"] for screen in FLOW_SCREEN_CATALOG}
}
CONTAINER_PAGES = frozenset(FLOW_PAGES_BY_PARENT)
KNOWN_PAGES: tuple[str, ...] = tuple(screen["page"] for screen in SCREEN_CATALOG)
ASSIGNABLE_SCREEN_CATALOG: tuple[dict[str, str], ...] = tuple(
    screen
    for screen in SCREEN_CATALOG
    if screen["page"] not in CONTAINER_PAGES
)
# ALL_PAGES intentionally contains only options that open a concrete view. A
# parent with child flows remains in the catalog as navigation metadata, but it
# is never counted or persisted as an additional permission.
ALL_PAGES: tuple[str, ...] = tuple(screen["page"] for screen in ASSIGNABLE_SCREEN_CATALOG)
ADMIN_ONLY_PAGES = frozenset({"sistema-academico", "asignacion-pantallas"})
ROLE_DENIED_PAGES: dict[str, frozenset[str]] = {
    "ESTUDIANTE": frozenset({"expedientes-documentales"}),
}


def _flow_codes(parent_page: str, keys: Iterable[str] | None = None) -> tuple[str, ...]:
    available = FLOW_PAGES_BY_PARENT.get(parent_page, ())
    if keys is None:
        return available
    selected = {f"{parent_page}/{key}" for key in keys}
    return tuple(page for page in available if page in selected)


def _combine_pages(*collections: Iterable[str]) -> tuple[str, ...]:
    selected = {page for collection in collections for page in collection}
    return tuple(page for page in ALL_PAGES if page in selected)

_ACADEMIC_PAGES = (
    "dashboard", "preinscripcion", "matricula", "matricula-acad",
    "matricula-docente", "estado-docente", "actualizar-datos-estudiante",
    "actualizar-correo-intec",
    "reportes-individuales", "admin-notas-asignatura", "reporteria-integral",
    "gestion-sisacademico", "periodo-academico",
    "periodo-matriculados", "rango-edades", "certificados", "fecha-grado",
    "titulacion", "titulacion-proceso", "titulacion-responsables",
    "matricula-excel-certificados", "renombrar-certificados", "carnet-institucional",
    "evaluacion-docente-avance", "evaluacion-docente-reportes",
    "formato-informe-docente", "practicas-institucionales",
    "ingles", "expedientes-documentales",
)

_ACADEMIC_SIS_FLOWS = _flow_codes(
    "gestion-sisacademico",
    (
        "estudiantes", "registro_documentos_estudiante", "correos",
        "matricula_materias", "seguimiento", "actualizacion_estudiantes",
        "docentes", "docente_materias", "actualizacion_est",
        "preguntas_evaluacion", "evaluacion_resultados",
        "autoevaluacion_resultados", "fechas_autoevaluacion", "carreras",
        "materias", "mallas", "paralelos", "periodos", "fechas_notas",
        "asistencia_estudiantes", "jornadas", "modalidades", "practicas",
        "practicas_vinculacion", "empresas",
    ),
)
_ACADEMIC_REPORT_FLOWS = _combine_pages(
    _flow_codes(
        "reportes-individuales",
        ("notas_carrera_materia", "evaluacion_docente"),
    ),
    _flow_codes("reporteria-integral", ("genero_docentes",)),
)
_ADMISSIONS_SIS_FLOWS = _flow_codes(
    "gestion-sisacademico",
    ("preinscripciones", "estudiantes", "cabecera_matricula", "pagos_matricula", "datos_factura"),
)
_FINANCIAL_SIS_FLOWS = _flow_codes(
    "gestion-sisacademico",
    ("cabecera_matricula", "pagos_matricula", "datos_factura"),
)
_FINANCIAL_REPORT_FLOWS = _flow_codes(
    "reporteria-integral",
    ("provincia", "genero", "carrera", "periodo", "graduados_2025"),
)

DEFAULT_ACCESS: dict[str, tuple[str, ...]] = {
    "ADMINISTRADOR": ALL_PAGES,
    "ACADEMICO": _combine_pages(
        _ACADEMIC_PAGES,
        _flow_codes("preinscripcion"),
        _flow_codes("matricula-acad"),
        _ACADEMIC_SIS_FLOWS,
        _ACADEMIC_REPORT_FLOWS,
    ),
    "BIENESTAR": _combine_pages(
        (
            "dashboard", "preinscripcion", "actualizar-datos-estudiante",
            "admin-notas-asignatura", "reportes-individuales", "reporteria-integral",
            "carnet-institucional",
        ),
        _flow_codes("preinscripcion", ("gestion-becas", "becas", "becados")),
        _ACADEMIC_REPORT_FLOWS,
    ),
    "ADMISIONES": _combine_pages(
        ("dashboard", "preinscripcion", "gestion-sisacademico"),
        _flow_codes("preinscripcion"),
        _ADMISSIONS_SIS_FLOWS,
    ),
    "FINANCIERO": _combine_pages(
        (
            "dashboard", "preinscripcion", "ingreso-ventas",
            "gestion-sisacademico", "reporteria-integral",
            "carnet-institucional",
        ),
        _flow_codes("preinscripcion", ("registro", "documentos")),
        _FINANCIAL_SIS_FLOWS,
        _FINANCIAL_REPORT_FLOWS,
    ),
    "SECRETARIA": _combine_pages(
        (
            "practicas-institucionales", "fecha-grado",
            "senescyt-estudiantes", "titulacion", "titulacion-proceso",
            "titulacion-responsables", "titulos-registrados", "expedientes-documentales",
        ),
        _flow_codes("titulos-registrados"),
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
    "ESTUDIANTE": (
        "portal-estudiante", "portal-estudiante-malla-curricular",
        "portal-estudiante-malla-academica", "portal-estudiante-calificaciones",
        "ingles", "evaluacion-docente", "practicas-institucionales", "carnet-institucional",
    ),
}


_SPLIT_SCREEN_MIGRATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "portal-estudiante",
        (
            "portal-estudiante-malla-curricular",
            "portal-estudiante-malla-academica",
            "portal-estudiante-calificaciones",
        ),
    ),
)

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


def _is_page_or_flow_of(page: str, parent_page: str) -> bool:
    return page == parent_page or page.startswith(f"{parent_page}/")


def _is_restricted_page(page: str, restricted_pages: Iterable[str]) -> bool:
    return any(_is_page_or_flow_of(page, parent) for parent in restricted_pages)


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
    catalog_rows = [
        (
            screen["page"],
            screen["label"],
            screen["description"],
            screen["group"],
            order,
        )
        for order, screen in enumerate(SCREEN_CATALOG, start=1)
    ]
    if catalog_rows:
        row_sql = (
            "(CAST(? AS VARCHAR(80)), CAST(? AS NVARCHAR(160)), "
            "CAST(? AS NVARCHAR(500)), CAST(? AS NVARCHAR(100)), CAST(? AS INT))"
        )
        values_sql = ", ".join(row_sql for _ in catalog_rows)
        params = [value for row in catalog_rows for value in row]
        cursor.execute(
            f"""
            MERGE cfg.PantallaPortal AS target
            USING (VALUES {values_sql}) AS source (Codigo, Nombre, Descripcion, Grupo, Orden)
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
            *params,
        )

    placeholders = ", ".join("?" for _ in KNOWN_PAGES)
    cursor.execute(
        f"UPDATE cfg.PantallaPortal SET Activo = 0, FechaActualizacion = SYSDATETIME() WHERE Activo <> 0 AND Codigo NOT IN ({placeholders})",
        *KNOWN_PAGES,
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
                 WHERE RolCodigo = ?
                   AND (PantallaCodigo = ? OR PantallaCodigo LIKE ?)
                   AND Activo <> 0
                """,
                role,
                page,
                f"{page}/%",
            )


def _deactivate_container_assignments(cursor: Any) -> None:
    """Removes legacy parent grants after their child permissions exist."""
    if not CONTAINER_PAGES:
        return
    placeholders = ", ".join("?" for _ in CONTAINER_PAGES)
    cursor.execute(
        f"""
        UPDATE cfg.AccesoPantallaRol
           SET Activo = 0,
               FechaActualizacion = SYSDATETIME(),
               UsuarioActualizacion = N'SISTEMA_CONTENEDORES'
         WHERE Activo <> 0
           AND PantallaCodigo IN ({placeholders})
        """,
        *sorted(CONTAINER_PAGES),
    )


def _materialize_role_screen_matrix(cursor: Any) -> None:
    """Create missing role/screen rows without changing saved assignments."""
    role_codes = tuple(role["value"] for role in ROLE_CATALOG)
    if not role_codes or not ALL_PAGES:
        return

    role_values = ", ".join("(?)" for _ in role_codes)
    page_values = ", ".join("(?)" for _ in ALL_PAGES)
    cursor.execute(
        f"""
        MERGE cfg.AccesoPantallaRol AS target
        USING
        (
            SELECT
                roles.RolCodigo,
                screens.PantallaCodigo,
                CAST(CASE WHEN roles.RolCodigo = 'ADMINISTRADOR' THEN 1 ELSE 0 END AS BIT) AS Activo
            FROM (VALUES {role_values}) AS roles(RolCodigo)
            CROSS JOIN (VALUES {page_values}) AS screens(PantallaCodigo)
        ) AS source
           ON target.RolCodigo = source.RolCodigo
          AND target.PantallaCodigo = source.PantallaCodigo
        WHEN NOT MATCHED THEN
            INSERT (RolCodigo, PantallaCodigo, Activo, UsuarioActualizacion)
            VALUES (source.RolCodigo, source.PantallaCodigo, source.Activo, N'SISTEMA_CATALOGO');
        """,
        *role_codes,
        *ALL_PAGES,
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


def _migrate_split_screen_assignments(cursor: Any) -> None:
    """Conserva el acceso previo al separar una pantalla en opciones individuales."""
    for role_meta in ROLE_CATALOG:
        role = role_meta["value"]
        for legacy_page, split_pages in _SPLIT_SCREEN_MIGRATIONS:
            for split_page in split_pages:
                cursor.execute(
                    """
                    MERGE cfg.AccesoPantallaRol AS target
                    USING
                    (
                        SELECT
                            ? AS RolCodigo,
                            ? AS PantallaCodigo,
                            CAST(
                                CASE WHEN EXISTS
                                (
                                    SELECT 1
                                    FROM cfg.AccesoPantallaRol AS legacy
                                    WHERE legacy.RolCodigo = ?
                                      AND legacy.PantallaCodigo = ?
                                      AND legacy.Activo = 1
                                ) THEN 1 ELSE 0 END
                                AS BIT
                            ) AS Activo
                    ) AS source
                       ON target.RolCodigo = source.RolCodigo
                      AND target.PantallaCodigo = source.PantallaCodigo
                    WHEN NOT MATCHED THEN
                        INSERT (RolCodigo, PantallaCodigo, Activo, UsuarioActualizacion)
                        VALUES (source.RolCodigo, source.PantallaCodigo, source.Activo, N'SISTEMA_MIGRACION');
                    """,
                    role,
                    split_page,
                    role,
                    legacy_page,
                )


def _migrate_flow_screen_assignments(cursor: Any) -> None:
    """Creates each flow permission once, preserving the previous parent access."""
    for role_meta in ROLE_CATALOG:
        role = role_meta["value"]
        if role == "ADMINISTRADOR":
            continue
        role_defaults = set(DEFAULT_ACCESS.get(role, ()))
        for flow_page, parent_page in FLOW_PARENT_BY_PAGE.items():
            cursor.execute(
                """
                MERGE cfg.AccesoPantallaRol AS target
                USING
                (
                    SELECT
                        ? AS RolCodigo,
                        ? AS PantallaCodigo,
                        CAST(
                            CASE WHEN ? = 1 AND EXISTS
                            (
                                SELECT 1
                                FROM cfg.AccesoPantallaRol AS parent_access
                                WHERE parent_access.RolCodigo = ?
                                  AND parent_access.PantallaCodigo = ?
                                  AND parent_access.Activo = 1
                            ) THEN 1 ELSE 0 END
                            AS BIT
                        ) AS Activo
                ) AS source
                   ON target.RolCodigo = source.RolCodigo
                  AND target.PantallaCodigo = source.PantallaCodigo
                WHEN NOT MATCHED THEN
                    INSERT (RolCodigo, PantallaCodigo, Activo, UsuarioActualizacion)
                    VALUES (source.RolCodigo, source.PantallaCodigo, source.Activo, N'SISTEMA_FLUJOS');
                """,
                role,
                flow_page,
                int(flow_page in role_defaults),
                role,
                parent_page,
            )


def _role_screen_matrix_is_complete(cursor: Any) -> bool:
    role_codes = tuple(role["value"] for role in ROLE_CATALOG)
    if not role_codes or not ALL_PAGES:
        return True

    role_placeholders = ", ".join("?" for _ in role_codes)
    page_placeholders = ", ".join("?" for _ in ALL_PAGES)
    cursor.execute(
        f"""
        SELECT COUNT_BIG(*) AS Total
        FROM cfg.AccesoPantallaRol
        WHERE RolCodigo IN ({role_placeholders})
          AND PantallaCodigo IN ({page_placeholders})
        """,
        *role_codes,
        *ALL_PAGES,
    )
    row = cursor.fetchone()
    if row is None:
        total = 0
    else:
        value = getattr(row, "Total", None)
        total = int(value if value is not None else row[0])
    return total == len(role_codes) * len(ALL_PAGES)


def _synchronize_screen_catalog(cursor: Any) -> None:
    """Installs and migrates the catalog before normal permission reads."""
    _ensure_tables(cursor)
    _sync_catalog(cursor)
    if not _role_screen_matrix_is_complete(cursor):
        _initialize_role_assignments(cursor)
        _migrate_split_screen_assignments(cursor)
        _migrate_flow_screen_assignments(cursor)
        _materialize_role_screen_matrix(cursor)
    _deactivate_container_assignments(cursor)


def _ensure_screen_catalog_ready() -> None:
    """Runs static catalog synchronization once per application process."""
    global _catalog_bootstrapped
    if _catalog_bootstrapped:
        return

    with _catalog_bootstrap_lock:
        if _catalog_bootstrapped:
            return
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            _synchronize_screen_catalog(cursor)
            conn.commit()
        _catalog_bootstrapped = True


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
                if not _is_restricted_page(page, ADMIN_ONLY_PAGES)
                and not _is_restricted_page(page, denied_pages)
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


def role_has_screen_access(role: str, page: str) -> bool:
    """Checks the effective assignment without applying role-based fallbacks."""
    role_code = normalize_role(role)
    page_code = str(page or "").strip()
    valid_roles = {item["value"] for item in ROLE_CATALOG}

    if page_code not in KNOWN_PAGES:
        raise ValueError(f"Pantalla no reconocida: {page_code or '(vacia)'}")
    if role_code not in valid_roles:
        return False
    if role_code == "ADMINISTRADOR":
        return True
    if _is_restricted_page(page_code, ADMIN_ONLY_PAGES) or _is_restricted_page(
        page_code,
        ROLE_DENIED_PAGES.get(role_code, frozenset()),
    ):
        return False

    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1) 1
                FROM cfg.AccesoPantallaRol AS acceso
                INNER JOIN cfg.PantallaPortal AS pantalla
                  ON pantalla.Codigo = acceso.PantallaCodigo
                WHERE acceso.RolCodigo = ?
                  AND (acceso.PantallaCodigo = ? OR acceso.PantallaCodigo LIKE ?)
                  AND acceso.Activo = 1
                  AND pantalla.Activo = 1
                """,
                role_code,
                page_code,
                f"{page_code}/%",
            )
            return cursor.fetchone() is not None
    except (RuntimeError, pyodbc.Error) as exc:
        raise ScreenAccessUnavailableError(
            "No se pudo consultar la asignacion central de pantallas."
        ) from exc


def get_screen_access(role: str, *, include_all: bool = False) -> dict[str, Any]:
    current_role = normalize_role(role)
    valid_roles = {item["value"] for item in ROLE_CATALOG}
    if current_role not in valid_roles:
        raise ValueError("El tipo de usuario no forma parte del catalogo de accesos.")

    requested_roles = [item["value"] for item in ROLE_CATALOG] if include_all else [current_role]
    _ensure_screen_catalog_ready()
    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        roles = _role_payloads(cursor, requested_roles)

    return {
        "source": "INTEC_INTEGRACION_CONTROL.cfg",
        "synchronized_at": datetime.now(timezone.utc).isoformat(),
        "current_role": current_role,
        "screens": list(ASSIGNABLE_SCREEN_CATALOG),
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
    denied_pages = sorted(
        page
        for page in set(requested_pages)
        if _is_restricted_page(page, ROLE_DENIED_PAGES.get(role_code, frozenset()))
    )
    if denied_pages:
        raise ValueError(
            f"El perfil {role_code} no puede acceder a: {', '.join(denied_pages)}"
        )
    administrator_pages = sorted(
        page
        for page in set(requested_pages)
        if role_code != "ADMINISTRADOR" and _is_restricted_page(page, ADMIN_ONLY_PAGES)
    )
    if administrator_pages:
        raise ValueError(
            f"Solo el perfil ADMINISTRADOR puede acceder a: {', '.join(administrator_pages)}"
        )
    allowed_requested_pages = [
        page
        for page in requested_pages
        if role_code == "ADMINISTRADOR" or not _is_restricted_page(page, ADMIN_ONLY_PAGES)
    ]
    selected_pages = set(ALL_PAGES if role_code == "ADMINISTRADOR" else allowed_requested_pages)
    audit_user = str(updated_by or "SISTEMA").strip()[:128] or "SISTEMA"

    _ensure_screen_catalog_ready()
    with get_integration_control_connection() as conn:
        cursor = conn.cursor()
        ordered_selected_pages = [page for page in ALL_PAGES if page in selected_pages]
        if ordered_selected_pages:
            placeholders = ", ".join("?" for _ in ordered_selected_pages)
            cursor.execute(
                f"""
                UPDATE cfg.AccesoPantallaRol
                   SET Activo = CASE WHEN PantallaCodigo IN ({placeholders}) THEN 1 ELSE 0 END,
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE RolCodigo = ?
                """,
                *ordered_selected_pages,
                audit_user,
                role_code,
            )
        else:
            cursor.execute(
                """
                UPDATE cfg.AccesoPantallaRol
                   SET Activo = 0,
                       FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE RolCodigo = ?
                """,
                audit_user,
                role_code,
            )
        role_payload = _role_payloads(cursor, [role_code])[0]
        conn.commit()
    return role_payload
