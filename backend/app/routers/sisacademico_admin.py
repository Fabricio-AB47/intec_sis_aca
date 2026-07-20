from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection

router = APIRouter(prefix="/api/students/sisacademico", tags=["sisacademico"])

AllowedEditor = Depends(require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR"))

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_STUDENT_STATE_DOCUMENT_ROOT = _BACKEND_ROOT / "uploads" / "estados_estudiantes"
_STUDENT_STATE_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
_STUDENT_STATE_MAX_FILE_SIZE = 15 * 1024 * 1024


class FieldMeta(BaseModel):
    name: str
    label: str
    type: str = "text"
    required: bool = False
    readonly: bool = False
    options: list[dict[str, str]] = Field(default_factory=list)


class SectionMeta(BaseModel):
    key: str
    title: str
    category: str
    description: str
    table: str
    key_fields: list[str]
    list_fields: list[FieldMeta]
    detail_fields: list[FieldMeta]
    editable_fields: list[FieldMeta]
    create_fields: list[FieldMeta] = Field(default_factory=list)


class SavePayload(BaseModel):
    values: dict[str, Any]


def field(name: str, label: str, type_: str = "text", required: bool = False, readonly: bool = False) -> FieldMeta:
    return FieldMeta(name=name, label=label, type=type_, required=required, readonly=readonly)


def fields(*items: tuple[str, str, str] | tuple[str, str] | FieldMeta) -> list[FieldMeta]:
    result: list[FieldMeta] = []
    for item in items:
        if isinstance(item, FieldMeta):
            result.append(item)
        elif len(item) == 3:
            result.append(field(item[0], item[1], item[2]))
        else:
            result.append(field(item[0], item[1]))
    return result


STUDENT_IDENTITY_FIELDS = {"estudiante_nombre", "estudiante_cedula"}
STUDENT_CODE_FIELD_BY_SECTION = {
    "matricula_materias": "codigo_estud",
    "cabecera_matricula": "codigo_estud",
    "correos": "codestud",
    "practicas": "codigo_estud",
    "pagos_matricula": "Codestu",
    "seguimiento": "codigo_estud",
    "datos_factura": "CODESTUD",
    "asistencia_estudiantes": "codigo_estud",
    "evaluacion_resultados": "Cod_Docente",
    "registro_documentos_estudiante": "IDESTUD",
    "practicas_vinculacion": "codigo_estud",
}


SECTIONS: dict[str, dict[str, Any]] = {
    "estudiantes": {
        "title": "Estudiantes",
        "category": "Personas",
        "description": "Datos academicos, contacto y campos regulatorios principales de DATOS_ESTUD.",
        "table": "[dbo].[DATOS_ESTUD]",
        "key_fields": ["Cedula_Est"],
        "list_fields": fields(
            ("codigo_estud", "Codigo", "number"),
            ("Cedula_Est", "Cedula"),
            ("Apellidos_nombre", "Estudiante"),
            ("Estado", "Estado"),
            ("correo", "Correo"),
            ("correointec", "Correo INTEC"),
            ("movil", "Movil"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo", "number"),
            ("Cedula_Est", "Cedula"),
            ("Apellidos_nombre", "Estudiante"),
            ("ciudad", "Ciudad"),
            ("codprov", "Provincia", "number"),
            ("Canton", "Canton"),
            ("Fecha_Nac", "Fecha nacimiento", "date"),
            ("correo", "Correo"),
            ("correointec", "Correo INTEC"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("EstadoCivil", "Estado civil", "number"),
            ("Sexo", "Sexo", "number"),
            ("Estado", "Estado"),
            ("Nacionalidad", "Nacionalidad"),
            ("tiposangre", "Tipo sangre"),
            ("Ocupacion", "Ocupacion"),
            ("empresa", "Empresa"),
            ("discapacidad", "Discapacidad"),
        ),
        "editable_fields": fields(
            ("Apellidos_nombre", "Estudiante"),
            ("ciudad", "Ciudad"),
            ("codprov", "Provincia", "number"),
            ("Canton", "Canton"),
            ("Fecha_Nac", "Fecha nacimiento", "date"),
            ("correo", "Correo"),
            ("correointec", "Correo INTEC"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("EstadoCivil", "Estado civil", "number"),
            ("Sexo", "Sexo", "number"),
            ("Estado", "Estado"),
            ("Nacionalidad", "Nacionalidad"),
            ("tiposangre", "Tipo sangre"),
            ("Ocupacion", "Ocupacion"),
            ("empresa", "Empresa"),
            ("discapacidad", "Discapacidad"),
        ),
        "search_fields": ["codigo_estud", "Cedula_Est", "Apellidos_nombre", "correo", "correointec", "movil"],
        "order_by": "Apellidos_nombre",
    },
    "actualizacion_estudiantes": {
        "title": "Actualizacion estados estudiantes",
        "category": "Personas",
        "description": "Actualiza el estado academico del estudiante en DATOS_ESTUD usando el catalogo dbo.ESTADO.",
        "table": "dbo.DATOS_ESTUD + dbo.ESTADO",
        "key_fields": ["Cedula_Est"],
        "list_fields": fields(
            ("codigo_estud", "Codigo", "number"),
            ("Apellidos_nombre", "Nombre"),
            ("correo", "Correo personal"),
            ("codigo_periodo", "Período"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo", "number"),
            ("Cedula_Est", "Cedula"),
            ("Apellidos_nombre", "Estudiante"),
            ("codigo_periodo", "Período"),
            ("Estado", "Estado"),
            ("estado_nombre", "Detalle estado"),
            ("Informacion", "Descripción"),
            ("DocumentoEstado", "Documento de respaldo"),
            ("correo", "Correo personal"),
            ("correointec", "Correo INTEC"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("ciudad", "Ciudad"),
            ("Nacionalidad", "Nacionalidad"),
            ("total_matriculas", "Matriculas", "number"),
            ("total_materias", "Materias registradas", "number"),
            ("ultimo_periodo", "Ultimo periodo", "number"),
        ),
        "editable_fields": fields(
            field("Estado", "Estado estudiante", required=True),
            ("Informacion", "Descripción", "textarea"),
        ),
        "search_fields": ["codigo_estud", "Cedula_Est", "Apellidos_nombre", "correo", "correointec", "movil", "Estado", "estado_nombre"],
        "order_by": "Apellidos_nombre",
    },
    "docentes": {
        "title": "Docentes",
        "category": "Personas",
        "description": "Ficha editable del docente, contacto, perfil y datos academicos.",
        "table": "[dbo].[DATOSDOCENTE]",
        "key_fields": ["cedula_doc"],
        "list_fields": fields(
            ("codigo_doc", "Codigo", "number"),
            ("cedula_doc", "Cedula"),
            ("apellidos_nombre", "Docente"),
            ("correo", "Correo"),
            ("movil", "Movil"),
            ("TipoDocente", "Tipo"),
        ),
        "detail_fields": fields(
            ("codigo_doc", "Codigo", "number"),
            ("cedula_doc", "Cedula"),
            ("apellidos_nombre", "Docente"),
            ("correo", "Correo"),
            ("correop", "Correo personal"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("sexo", "Sexo"),
            ("nacionalidad", "Nacionalidad"),
            ("fecha_nac", "Fecha nacimiento", "date"),
            ("estado_civil", "Estado civil"),
            ("Perfil", "Perfil", "textarea"),
            ("Direccion", "Direccion", "textarea"),
            ("tercernivel", "Tercer nivel"),
            ("cuartonivel", "Cuarto nivel"),
            ("TipoDocente", "Tipo docente"),
            ("nivelFormacion", "Nivel formacion"),
            ("fechaIngresoIES", "Fecha ingreso IES"),
            ("relacionLaboralIESId", "Relacion laboral"),
            ("tiempoDedicacionId", "Tiempo dedicacion"),
        ),
        "editable_fields": fields(
            ("apellidos_nombre", "Docente"),
            ("correo", "Correo"),
            ("correop", "Correo personal"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("sexo", "Sexo"),
            ("nacionalidad", "Nacionalidad"),
            ("fecha_nac", "Fecha nacimiento", "date"),
            ("estado_civil", "Estado civil"),
            ("Perfil", "Perfil", "textarea"),
            ("Direccion", "Direccion", "textarea"),
            ("tercernivel", "Tercer nivel"),
            ("cuartonivel", "Cuarto nivel"),
            ("TipoDocente", "Tipo docente"),
            ("nivelFormacion", "Nivel formacion"),
            ("fechaIngresoIES", "Fecha ingreso IES"),
            ("relacionLaboralIESId", "Relacion laboral"),
            ("tiempoDedicacionId", "Tiempo dedicacion"),
        ),
        "create_fields": fields(
            field("codigo_doc", "Codigo", "number", required=True),
            field("cedula_doc", "Cedula", required=True),
            field("apellidos_nombre", "Docente", required=True),
            ("login", "Login usuario"),
            ("password", "Clave usuario"),
            ("correo", "Correo"),
            ("telefono", "Telefono"),
            ("movil", "Movil"),
            ("TipoDocente", "Tipo docente"),
        ),
        "search_fields": ["codigo_doc", "cedula_doc", "apellidos_nombre", "correo", "correop", "movil"],
        "order_by": "apellidos_nombre",
    },
    "actualizacion_est": {
        "title": "Actualización estados docentes",
        "category": "Docencia",
        "description": "Verifica DATOSDOCENTE y todos los usuarios vinculados para activar o inactivar docentes.",
        "table": "dbo.DATOSDOCENTE + dbo.USUARIOS",
        "key_fields": ["codigo_doc", "Codigo_Usuario"],
        "list_fields": fields(
            ("codigo_doc", "Código docente", "number"),
            ("cedula_doc", "Cédula docente"),
            ("apellidos_nombre", "Nombre"),
            ("correo_docente", "Correo docente"),
            ("movil", "Móvil"),
            ("Codigo_Usuario", "Código usuario", "number"),
            ("cedula", "Cédula usuario"),
            ("login", "Usuario"),
            ("fecha_ingreso_usuario", "Ingreso", "datetime"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("codigo_doc", "Código docente", "number"),
            ("Codigo_Usuario", "Código usuario", "number"),
            ("cedula", "Cédula usuario"),
            ("login", "Login"),
            ("tipo_usuario", "Tipo usuario"),
            ("fecha_ingreso_usuario", "Fecha ingreso usuario", "datetime"),
            ("CambioClave", "Cambio clave"),
            ("Estado", "Estado usuario"),
            ("Informacion", "Descripción usuario", "textarea"),
            ("cedula_doc", "Cédula docente"),
            ("apellidos_nombre", "Docente"),
            ("correo_docente", "Correo docente"),
            ("correo_personal", "Correo personal"),
            ("telefono", "Teléfono"),
            ("movil", "Móvil"),
            ("TipoDocente", "Tipo docente"),
            ("nivelFormacion", "Nivel formación"),
            ("sexo", "Sexo"),
            ("nacionalidad", "Nacionalidad"),
            field("fecha_nac", "Fecha nacimiento", "date"),
            ("tipo_discapa", "Tipo discapacidad"),
            ("carnet_conadis", "Carnet CONADIS"),
            ("num_carnet_cona", "Número carnet"),
            ("porcen_discapa", "Porcentaje discapacidad"),
            ("estado_civil", "Estado civil"),
        ),
        "editable_fields": fields(
            field("Estado", "Estado docente", required=True),
            ("Informacion", "Descripción", "textarea"),
        ),
        "search_fields": ["codigo_doc", "cedula", "cedula_doc", "apellidos_nombre", "correo", "correop", "login", "Estado", "estado_nombre"],
        "order_by": "apellidos_nombre",
    },
    "preinscripciones": {
        "title": "Proceso de preinscripcion",
        "category": "Admision",
        "description": "Aspirantes, asesor asignado, documentos y avance del proceso de ingreso.",
        "table": "[dbo].[PREINSCRIPCION]",
        "key_fields": ["Cedula"],
        "list_fields": fields(
            ("Codestu", "Codigo", "number"),
            ("Cedula", "Cedula"),
            ("Apellidos_nombre", "Aspirante"),
            ("codperiodo", "Periodo", "number"),
            ("codcarrera", "Carrera", "number"),
            ("correo", "Correo"),
            ("telefono", "Telefono"),
            ("codasesor", "Asesor", "number"),
            ("Prematricula", "Prematricula", "number"),
            ("ProcesoFinalilzado", "Finalizado", "number"),
        ),
        "detail_fields": fields(
            ("Codestu", "Codigo", "number"),
            ("Cedula", "Cedula"),
            ("Apellidos_nombre", "Aspirante"),
            ("codperiodo", "Periodo", "number"),
            ("correo", "Correo"),
            ("telefono", "Telefono"),
            ("Fecha_Ingreso", "Fecha ingreso", "datetime"),
            ("Usuario", "Usuario"),
            ("codprov", "Provincia", "number"),
            ("codcarrera", "Carrera", "number"),
            ("codmodalida", "Modalidad", "number"),
            ("codjornada", "Jornada", "number"),
            ("contacte", "Contacto"),
            ("hora", "Hora"),
            ("codasesor", "Asesor", "number"),
            ("Observacioncontacto", "Obs. contacto", "textarea"),
            ("ObservacionIngreso", "Obs. ingreso", "textarea"),
            ("codLecontacto", "Medio contacto", "number"),
            ("Prematricula", "Prematricula", "number"),
            ("urlcedula", "URL cedula"),
            ("urltitulo", "URL titulo"),
            ("urldeposito", "URL deposito"),
            ("urlconvenio", "URL convenio"),
            ("Correoenviado", "Correo enviado", "number"),
            ("asignado", "Asignado", "number"),
            ("ProcesoFinalilzado", "Finalizado", "number"),
            ("ControlIngreso", "Control ingreso", "number"),
            ("Nom_Representante", "Representante"),
            ("Num_Representante", "Cedula representante"),
        ),
        "editable_fields": fields(
            ("Apellidos_nombre", "Aspirante"),
            ("codperiodo", "Periodo", "number"),
            ("correo", "Correo"),
            ("telefono", "Telefono"),
            ("codprov", "Provincia", "number"),
            ("codcarrera", "Carrera", "number"),
            ("codmodalida", "Modalidad", "number"),
            ("codjornada", "Jornada", "number"),
            ("contacte", "Contacto"),
            ("hora", "Hora"),
            ("codasesor", "Asesor", "number"),
            ("Observacioncontacto", "Obs. contacto", "textarea"),
            ("ObservacionIngreso", "Obs. ingreso", "textarea"),
            ("codLecontacto", "Medio contacto", "number"),
            ("Prematricula", "Prematricula", "number"),
            ("urlcedula", "URL cedula"),
            ("urltitulo", "URL titulo"),
            ("urldeposito", "URL deposito"),
            ("urlconvenio", "URL convenio"),
            ("Correoenviado", "Correo enviado", "number"),
            ("asignado", "Asignado", "number"),
            ("ProcesoFinalilzado", "Finalizado", "number"),
            ("ControlIngreso", "Control ingreso", "number"),
            ("Nom_Representante", "Representante"),
            ("Num_Representante", "Cedula representante"),
        ),
        "create_fields": fields(
            field("Codestu", "Codigo aspirante", "number", required=True),
            field("Cedula", "Cedula", required=True),
            field("Apellidos_nombre", "Aspirante", required=True),
            ("codperiodo", "Periodo", "number"),
            ("correo", "Correo"),
            ("telefono", "Telefono"),
            ("codprov", "Provincia", "number"),
            ("codcarrera", "Carrera", "number"),
            ("codmodalida", "Modalidad", "number"),
            ("codjornada", "Jornada", "number"),
            ("codLecontacto", "Medio contacto", "number"),
            ("Observacioncontacto", "Obs. contacto", "textarea"),
            ("ObservacionIngreso", "Obs. ingreso", "textarea"),
            ("Prematricula", "Prematricula", "number"),
            ("asignado", "Asignado", "number"),
            ("ProcesoFinalilzado", "Finalizado", "number"),
            ("ControlIngreso", "Control ingreso", "number"),
        ),
        "search_fields": ["Codestu", "Cedula", "Apellidos_nombre", "correo", "telefono", "codperiodo", "codcarrera", "codasesor"],
        "order_by": "Fecha_Ingreso DESC, Apellidos_nombre",
        "defaults": {
            "Fecha_Ingreso": "now",
            "Usuario": "current_user",
            "codasesor": "current_user_id",
            "codperiodo": 0,
            "codprov": 0,
            "codcarrera": 0,
            "codmodalida": 1,
            "codjornada": 0,
            "codLecontacto": 1,
            "Prematricula": 0,
            "asignado": 0,
            "ProcesoFinalilzado": 0,
            "ControlIngreso": 1,
        },
    },
    "carreras": {
        "title": "Carreras",
        "category": "Academico",
        "description": "Catalogo de carreras o escuelas academicas.",
        "table": "[dbo].[CARRERAS]",
        "key_fields": ["Cod_AnioBasica"],
        "list_fields": fields(
            ("Cod_AnioBasica", "Codigo", "number"),
            ("Nombre_Basica", "Carrera"),
            ("Estado", "Estado"),
            ("Abrevia", "Abrevia"),
            ("tp_escuela", "Tipo escuela"),
        ),
        "detail_fields": fields(
            ("Cod_AnioBasica", "Codigo", "number"),
            ("Nombre_Basica", "Carrera"),
            ("Estado", "Estado"),
            ("Abrevia", "Abrevia"),
            ("tp_escuela", "Tipo escuela"),
        ),
        "editable_fields": fields(
            ("Nombre_Basica", "Carrera"),
            ("Estado", "Estado"),
            ("Abrevia", "Abrevia"),
            ("tp_escuela", "Tipo escuela"),
        ),
        "create_fields": fields(
            field("Cod_AnioBasica", "Codigo", "number", required=True),
            field("Nombre_Basica", "Carrera", required=True),
            ("Estado", "Estado"),
            ("Abrevia", "Abrevia"),
            ("tp_escuela", "Tipo escuela"),
        ),
        "search_fields": ["Cod_AnioBasica", "Nombre_Basica", "Abrevia", "tp_escuela"],
        "order_by": "Nombre_Basica",
    },
    "paralelos": {
        "title": "Paralelos",
        "category": "Academico",
        "description": "Catalogo base de paralelos utilizados en matricula y docencia.",
        "table": "[dbo].[PARALELOS]",
        "key_fields": ["paralelo"],
        "list_fields": fields(
            ("num", "Numero", "number"),
            ("paralelo", "Paralelo"),
        ),
        "detail_fields": fields(
            ("num", "Numero", "number"),
            ("paralelo", "Paralelo"),
        ),
        "editable_fields": fields(("paralelo", "Paralelo")),
        "create_fields": fields(field("paralelo", "Paralelo", required=True)),
        "search_fields": ["num", "paralelo"],
        "order_by": "paralelo",
    },
    "materias": {
        "title": "Materias y pensum",
        "category": "Academico",
        "description": "Malla, materia, semestre, creditos, horas y estado.",
        "table": "[dbo].[PENSUM]",
        "key_fields": ["codigo_materia"],
        "list_fields": fields(
            ("codigo_materia", "Codigo", "number"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("Nomb_Materia", "Materia"),
            ("Semestre", "Semestre", "number"),
            ("Creditos", "Creditos", "decimal"),
            ("estado_mat", "Estado"),
        ),
        "detail_fields": fields(
            ("codigo_materia", "Codigo", "number"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("Unidad_Organiza", "Unidad"),
            ("Nomb_Materia", "Materia"),
            ("Semestre", "Semestre", "number"),
            ("Creditos", "Creditos", "decimal"),
            ("Orden", "Orden", "number"),
            ("NumMalla", "Malla", "number"),
            ("cod_materia", "Codigo textual"),
            ("Horas", "Horas", "number"),
            ("ValorHora", "Valor hora", "decimal"),
            ("ValorHoraVirtual", "Valor hora virtual", "decimal"),
            ("verreporte", "Ver reporte", "number"),
            ("SecuenciaMateria", "Secuencia"),
            ("tipomateria", "Tipo materia"),
            ("estado_mat", "Estado"),
        ),
        "editable_fields": fields(
            ("Cod_AnioBasica", "Carrera", "number"),
            ("Unidad_Organiza", "Unidad"),
            ("Nomb_Materia", "Materia"),
            ("Semestre", "Semestre", "number"),
            ("Creditos", "Creditos", "decimal"),
            ("Orden", "Orden", "number"),
            ("NumMalla", "Malla", "number"),
            ("cod_materia", "Codigo textual"),
            ("Horas", "Horas", "number"),
            ("ValorHora", "Valor hora", "decimal"),
            ("ValorHoraVirtual", "Valor hora virtual", "decimal"),
            ("verreporte", "Ver reporte", "number"),
            ("SecuenciaMateria", "Secuencia"),
            ("tipomateria", "Tipo materia"),
            ("estado_mat", "Estado"),
        ),
        "create_fields": fields(
            field("Cod_AnioBasica", "Carrera", "number", required=True),
            ("Unidad_Organiza", "Unidad"),
            field("Nomb_Materia", "Materia", required=True),
            field("Semestre", "Semestre", "number", required=True),
            field("Creditos", "Creditos", "decimal", required=True),
            ("Orden", "Orden", "number"),
            field("NumMalla", "Malla", "number", required=True),
            ("cod_materia", "Codigo textual"),
            field("Horas", "Horas", "number", required=True),
            ("ValorHora", "Valor hora", "decimal"),
            ("ValorHoraVirtual", "Valor hora virtual", "decimal"),
            ("verreporte", "Ver reporte", "number"),
            ("SecuenciaMateria", "Secuencia"),
            ("tipomateria", "Tipo materia"),
            ("estado_mat", "Estado"),
        ),
        "defaults": {
            "ValorHora": 0,
            "ValorHoraVirtual": 0,
            "verreporte": 1,
            "SecuenciaMateria": "0",
            "estado_mat": "ACTIVO",
        },
        "search_fields": ["codigo_materia", "Cod_AnioBasica", "Nomb_Materia", "cod_materia", "estado_mat"],
        "order_by": "Nomb_Materia",
    },
    "periodos": {
        "title": "Periodos academicos",
        "category": "Academico",
        "description": "Configuracion de periodos, fechas, visibilidad y control de plataforma.",
        "table": "[dbo].[PERIODO]",
        "key_fields": ["cod_periodo"],
        "list_fields": fields(
            ("cod_periodo", "Codigo", "number"),
            ("Detalle_Periodo", "Periodo"),
            ("Estado", "Estado"),
            ("Periodo", "Etiqueta"),
            ("anio", "Anio", "number"),
            ("TipoMatricula", "Tipo matricula"),
        ),
        "detail_fields": fields(
            ("cod_periodo", "Codigo", "number"),
            ("Detalle_Periodo", "Periodo"),
            ("Estado", "Estado"),
            ("Periodo", "Etiqueta"),
            ("Orden", "Orden", "number"),
            ("NotaAprobar", "Nota aprobar", "decimal"),
            ("ControlPlataforma", "Control plataforma"),
            ("VerInscripcion", "Ver inscripcion", "number"),
            ("VerNotas", "Ver notas", "number"),
            ("TipoMatricula", "Tipo matricula"),
            ("VerReporte", "Ver reporte", "number"),
            ("fechain", "Fecha inicio", "date"),
            ("fechafin", "Fecha fin", "date"),
            ("anio", "Anio", "number"),
            ("estado_ed", "Estado ED"),
        ),
        "editable_fields": fields(
            ("Detalle_Periodo", "Periodo"),
            ("Estado", "Estado"),
            ("Periodo", "Etiqueta"),
            ("Orden", "Orden", "number"),
            ("NotaAprobar", "Nota aprobar", "decimal"),
            ("ControlPlataforma", "Control plataforma"),
            ("VerInscripcion", "Ver inscripcion", "number"),
            ("VerNotas", "Ver notas", "number"),
            ("TipoMatricula", "Tipo matricula"),
            ("VerReporte", "Ver reporte", "number"),
            ("fechain", "Fecha inicio", "date"),
            ("fechafin", "Fecha fin", "date"),
            ("anio", "Anio", "number"),
            ("estado_ed", "Estado ED"),
        ),
        "create_fields": fields(
            field("Detalle_Periodo", "Periodo", required=True),
            field("Estado", "Estado", required=True),
            ("Detalle_Reg", "Detalle registro"),
            ("Periodo", "Etiqueta"),
            ("Orden", "Orden", "number"),
            ("NotaAprobar", "Nota aprobar", "decimal"),
            ("ControlPlataforma", "Control plataforma"),
            ("VersionCalificacion", "Version calificacion", "number"),
            ("NotaPromedioMax", "Nota promedio max", "number"),
            ("VerInscripcion", "Ver inscripcion", "number"),
            ("VerNotas", "Ver notas", "number"),
            ("TipoMatricula", "Tipo matricula"),
            ("VerReporte", "Ver reporte", "number"),
            ("fechain", "Fecha inicio", "date"),
            ("fechafin", "Fecha fin", "date"),
            ("anio", "Anio", "number"),
            ("estado_ed", "Estado ED"),
        ),
        "defaults": {
            "NotaAprobar": 10,
            "ControlPlataforma": "P",
            "VersionCalificacion": 1,
            "NotaPromedioMax": 0,
            "VerInscripcion": 0,
            "VerNotas": 0,
            "TipoMatricula": "R",
            "VerReporte": 0,
            "estado_ed": "Inactivo",
        },
        "search_fields": ["cod_periodo", "Detalle_Periodo", "Periodo", "anio", "TipoMatricula"],
        "order_by": "cod_periodo DESC",
    },
    "matricula_materias": {
        "title": "Materias matriculadas y notas",
        "category": "Matricula",
        "description": "Detalle CARRERAXESTUD con notas, asistencia, estado Moodle y seguimiento.",
        "table": "[dbo].[CARRERAXESTUD]",
        "key_fields": ["codigo_estud", "cod_anio_Basica", "codigo_materia", "Num_Matricula", "paralelo", "NumGrupo"],
        "list_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("paralelo", "Paralelo"),
            ("TipoMatricula", "Tipo"),
            ("PromedioFinal", "Promedio final", "decimal"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Num_Matricula", "Matricula", "number"),
            ("paralelo", "Paralelo"),
            ("NumGrupo", "Grupo", "number"),
            ("P1Tareas", "P1 tareas", "decimal"),
            ("P1Proyectos", "P1 proyectos", "decimal"),
            ("P1Examen", "P1 examen", "decimal"),
            ("promP1", "Prom P1", "decimal"),
            ("P2Tareas", "P2 tareas", "decimal"),
            ("P2Proyectos", "P2 proyectos", "decimal"),
            ("P2Examen", "P2 examen", "decimal"),
            ("promP2", "Prom P2", "decimal"),
            ("P3Tareas", "P3 tareas", "decimal"),
            ("P3Proyectos", "P3 proyectos", "decimal"),
            ("P3Examen", "P3 examen", "decimal"),
            ("promP3", "Prom P3", "decimal"),
            ("PromedioFinal", "Promedio final", "decimal"),
            ("Asistencia", "Asistencia", "decimal"),
            ("Recuperacion", "Recuperacion", "decimal"),
            ("caprueba", "Aprueba"),
            ("estadoMoodle", "Estado Moodle", "bool"),
            ("seguimiento", "Seguimiento"),
            ("observaciones", "Observaciones", "textarea"),
        ),
        "editable_fields": fields(
            ("P1Tareas", "P1 tareas", "decimal"),
            ("P1Proyectos", "P1 proyectos", "decimal"),
            ("P1Examen", "P1 examen", "decimal"),
            ("promP1", "Prom P1", "decimal"),
            ("P2Tareas", "P2 tareas", "decimal"),
            ("P2Proyectos", "P2 proyectos", "decimal"),
            ("P2Examen", "P2 examen", "decimal"),
            ("promP2", "Prom P2", "decimal"),
            ("P3Tareas", "P3 tareas", "decimal"),
            ("P3Proyectos", "P3 proyectos", "decimal"),
            ("P3Examen", "P3 examen", "decimal"),
            ("promP3", "Prom P3", "decimal"),
            ("PromedioFinal", "Promedio final", "decimal"),
            ("Asistencia", "Asistencia", "decimal"),
            ("Recuperacion", "Recuperacion", "decimal"),
            ("caprueba", "Aprueba"),
            ("estadoMoodle", "Estado Moodle", "bool"),
            ("seguimiento", "Seguimiento"),
            ("observaciones", "Observaciones", "textarea"),
        ),
        "create_fields": fields(
            field("codigo_estud", "Estudiante", "number", required=True),
            field("cod_anio_Basica", "Carrera", "number", required=True),
            field("codigo_materia", "Materia", "number", required=True),
            field("codigo_periodo", "Periodo", "number", required=True),
            ("Num_Matricula", "Matricula", "number"),
            field("paralelo", "Paralelo", required=True),
            ("NumGrupo", "Grupo", "number"),
            ("Num_Creditos", "Creditos", "number"),
            ("Fecha_Matricula", "Fecha matricula", "date"),
            ("TipoMatricula", "Tipo"),
            ("ControlMatricula", "Control matricula", "number"),
            ("NumCertificado", "Certificado", "number"),
            ("gcer", "Genera certificado", "number"),
            ("NumMatricuMod", "Modificacion matricula", "number"),
            ("TipoCursoMigra", "Tipo curso"),
        ),
        "search_fields": ["codigo_estud", "cod_anio_Basica", "codigo_materia", "codigo_periodo", "paralelo", "seguimiento"],
        "order_by": "codigo_periodo DESC, codigo_estud",
        "defaults": {
            "Num_Matricula": 1,
            "NumGrupo": 0,
            "Num_Creditos": 0,
            "Fecha_Matricula": "today",
            "TipoMatricula": "N",
            "ControlMatricula": 1,
            "NumCertificado": 0,
            "gcer": 0,
            "NumMatricuMod": 0,
            "TipoCursoMigra": "R",
        },
    },
    "docente_materias": {
        "title": "Asignacion docente",
        "category": "Docencia",
        "description": "Relaciones docente, carrera, materia, periodo, jornada y paralelo.",
        "table": "[dbo].[CARRERAXDOCENTE]",
        "key_fields": ["codigo_doc", "codigo_materia", "Paralelo", "codigo_periodo", "Cod_Jornada"],
        "list_fields": fields(
            ("codigo_doc", "Docente", "number"),
            ("cod_Anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Paralelo", "Paralelo"),
            ("Cod_Jornada", "Jornada", "number"),
            ("estadoMoodleDoc", "Moodle", "bool"),
        ),
        "detail_fields": fields(
            ("codigo_doc", "Docente", "number"),
            ("cod_Anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("Paralelo", "Paralelo"),
            ("codigo_periodo", "Periodo", "number"),
            ("Cod_Jornada", "Jornada", "number"),
            ("estadoMoodleDoc", "Moodle", "bool"),
        ),
        "editable_fields": fields(("estadoMoodleDoc", "Moodle", "bool")),
        "create_fields": fields(
            field("codigo_doc", "Docente", "number", required=True),
            field("cod_Anio_Basica", "Carrera", "number", required=True),
            field("codigo_materia", "Materia", "number", required=True),
            field("Paralelo", "Paralelo", required=True),
            field("codigo_periodo", "Periodo", "number", required=True),
            field("Cod_Jornada", "Jornada", "number", required=True),
            ("estadoMoodleDoc", "Moodle", "bool"),
        ),
        "search_fields": ["codigo_doc", "cod_Anio_Basica", "codigo_materia", "codigo_periodo", "Paralelo", "Cod_Jornada"],
        "order_by": "codigo_periodo DESC, codigo_doc",
    },
    "cabecera_matricula": {
        "title": "Cabecera matricula y pagos",
        "category": "Matricula",
        "description": "Cabecera economica/documental de matricula por estudiante, carrera y periodo.",
        "table": "[dbo].[CABECERA_MATRICULA]",
        "key_fields": ["codigo_estud", "cod_anio_Basica", "codigo_periodo"],
        "list_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("fecha_pago", "Fecha pago", "date"),
            ("valor", "Valor", "decimal"),
            ("ControlMatricula", "Control", "number"),
            ("Jornada", "Jornada"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Num_Matricula", "Matricula", "number"),
            ("fecha_pago", "Fecha pago", "date"),
            ("valor", "Valor", "decimal"),
            ("num_dep_transf", "Deposito"),
            ("InscripValor", "Inscripcion", "decimal"),
            ("MatriValor", "Matricula valor", "decimal"),
            ("Cuota1", "Cuota 1", "decimal"),
            ("Beca", "Beca", "decimal"),
            ("Descuento", "Descuento", "decimal"),
            ("Jornada", "Jornada"),
            ("ControlMatricula", "Control matricula", "number"),
            ("codhorario", "Horario", "number"),
            ("codmodalidad", "Modalidad", "number"),
            ("coddias", "Dias", "number"),
            ("codjornada", "Jornada codigo", "number"),
            ("codestadoMat", "Estado matricula", "number"),
            ("urlcedula", "URL cedula"),
            ("urltitulo", "URL titulo"),
            ("urldeposito", "URL deposito"),
            ("urlconvenio", "URL convenio"),
            ("linkUrl", "Link"),
        ),
        "editable_fields": fields(
            ("fecha_pago", "Fecha pago", "date"),
            ("valor", "Valor", "decimal"),
            ("num_dep_transf", "Deposito"),
            ("InscripValor", "Inscripcion", "decimal"),
            ("MatriValor", "Matricula valor", "decimal"),
            ("Cuota1", "Cuota 1", "decimal"),
            ("Beca", "Beca", "decimal"),
            ("Descuento", "Descuento", "decimal"),
            ("Jornada", "Jornada"),
            ("ControlMatricula", "Control matricula", "number"),
            ("codhorario", "Horario", "number"),
            ("codmodalidad", "Modalidad", "number"),
            ("coddias", "Dias", "number"),
            ("codjornada", "Jornada codigo", "number"),
            ("codestadoMat", "Estado matricula", "number"),
            ("urlcedula", "URL cedula"),
            ("urltitulo", "URL titulo"),
            ("urldeposito", "URL deposito"),
            ("urlconvenio", "URL convenio"),
            ("linkUrl", "Link"),
        ),
        "create_fields": fields(
            field("codigo_estud", "Estudiante", "number", required=True),
            field("cod_anio_Basica", "Carrera", "number", required=True),
            field("codigo_periodo", "Periodo", "number", required=True),
            ("Num_Matricula", "Matricula", "number"),
            ("fecha_pago", "Fecha pago", "date"),
            ("valor", "Valor", "decimal"),
            ("num_dep_transf", "Deposito"),
            ("InscripValor", "Inscripcion", "decimal"),
            ("MatriValor", "Matricula valor", "decimal"),
            ("Cuota1", "Cuota 1", "decimal"),
            ("Beca", "Beca", "decimal"),
            ("Descuento", "Descuento", "decimal"),
            ("Jornada", "Jornada"),
            ("ControlMatricula", "Control matricula", "number"),
            ("codhorario", "Horario", "number"),
            ("codmodalidad", "Modalidad", "number"),
            ("coddias", "Dias", "number"),
            ("codjornada", "Jornada codigo", "number"),
            ("codestadoMat", "Estado matricula", "number"),
            ("urlcedula", "URL cedula"),
            ("urltitulo", "URL titulo"),
            ("urldeposito", "URL deposito"),
            ("urlconvenio", "URL convenio"),
            ("linkUrl", "Link"),
        ),
        "search_fields": ["codigo_estud", "cod_anio_Basica", "codigo_periodo", "Jornada", "num_dep_transf"],
        "order_by": "codigo_periodo DESC, codigo_estud",
        "defaults": {
            "Num_Matricula": 1,
            "fecha_pago": "today",
            "valor": 0,
            "InscripValor": 0,
            "MatriValor": 0,
            "ControlMatricula": 1,
            "codhorario": 0,
            "codmodalidad": 1,
            "coddias": 0,
            "codjornada": 0,
        },
    },
    "usuarios": {
        "title": "Registrar usuarios",
        "category": "Seguridad",
        "description": "Registro y mantenimiento de usuarios administrativos en USUARIO_SIS sin exponer contrasenas.",
        "table": "[dbo].[USUARIO_SIS]",
        "key_fields": ["login"],
        "list_fields": fields(
            ("login", "Login"),
            ("nombres", "Nombres"),
            ("estado", "Estado"),
            ("email", "Email"),
            ("cedula", "Cedula"),
            ("tipousuario", "Tipo", "number"),
            ("tp_us", "Perfil"),
        ),
        "detail_fields": fields(
            ("login", "Login"),
            ("nombres", "Nombres"),
            ("fecha_ingreso", "Fecha ingreso", "datetime"),
            ("estado", "Estado"),
            ("email", "Email"),
            ("coordcarrera", "Coord carrera", "number"),
            ("codprovincia", "Provincia"),
            ("tipousuario", "Tipo usuario", "number"),
            ("tp_us", "Perfil"),
            ("cedula", "Cedula"),
        ),
        "editable_fields": fields(
            ("nombres", "Nombres"),
            ("estado", "Estado"),
            ("email", "Email"),
            ("coordcarrera", "Coord carrera", "number"),
            ("codprovincia", "Provincia"),
            ("tipousuario", "Tipo usuario", "number"),
            ("tp_us", "Perfil"),
            ("cedula", "Cedula"),
        ),
        "create_fields": fields(
            field("login", "Login", required=True),
            field("password", "Contraseña", required=True),
            field("nombres", "Nombres", required=True),
            ("fecha_ingreso", "Fecha ingreso", "date"),
            ("estado", "Estado"),
            ("email", "Email"),
            ("cedula", "Cedula"),
            ("coordcarrera", "Coord carrera", "number"),
            ("codprovincia", "Provincia"),
            ("tp_us", "Perfil"),
        ),
        "search_fields": ["login", "nombres", "email", "cedula", "estado", "tp_us"],
        "order_by": "nombres",
        "defaults": {"fecha_ingreso": "now", "estado": "A", "tipousuario": 0, "tp_us": "1"},
    },
    "correos": {
        "title": "Correos institucionales",
        "category": "Cuentas",
        "description": "Administracion de correos INTEC sin mostrar claves.",
        "table": "[dbo].[CorreosEstudIntec]",
        "key_fields": ["codestud"],
        "list_fields": fields(
            ("codestud", "Codigo estudiante", "number"),
            ("Nombres", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("CorreoPersonal", "Correo personal"),
            ("CorreoIntec", "Correo INTEC"),
            ("Periodo", "Periodo", "number"),
            ("CorreoEnviado", "Enviado", "number"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("codestud", "Codigo estudiante", "number"),
            ("Nombres", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("CorreoPersonal", "Correo personal"),
            ("CorreoIntec", "Correo INTEC"),
            ("fecha", "Fecha", "date"),
            ("Periodo", "Periodo", "number"),
            ("CorreoEnviado", "Enviado", "number"),
            ("Estado", "Estado"),
            ("Descripcion", "Descripcion", "textarea"),
            ("ultAccesoMoodle", "Ultimo Moodle", "date"),
            ("NumMigracion", "Migracion", "number"),
            ("TipoCursoMigra", "Tipo curso"),
        ),
        "editable_fields": fields(
            ("Nombres", "Estudiante"),
            ("CorreoPersonal", "Correo personal"),
            ("CorreoIntec", "Correo INTEC"),
            ("fecha", "Fecha", "date"),
            ("Periodo", "Periodo", "number"),
            ("CorreoEnviado", "Enviado", "number"),
            ("Estado", "Estado"),
            ("Descripcion", "Descripcion", "textarea"),
            ("ultAccesoMoodle", "Ultimo Moodle", "date"),
            ("NumMigracion", "Migracion", "number"),
            ("TipoCursoMigra", "Tipo curso"),
        ),
        "search_fields": ["codestud", "Nombres", "CorreoPersonal", "CorreoIntec", "Estado"],
        "order_by": "fecha DESC, Nombres",
    },
    "empresas": {
        "title": "Empresas",
        "category": "Vinculacion",
        "description": "Empresas para practicas profesionales.",
        "table": "[dbo].[EMPRESA]",
        "key_fields": ["Num_emp"],
        "list_fields": fields(
            ("Num_emp", "Codigo", "number"),
            ("Empresa", "Empresa"),
            ("Direccion", "Direccion"),
            ("Telefono", "Telefono"),
            ("Correo", "Correo"),
        ),
        "detail_fields": fields(
            ("Num_emp", "Codigo", "number"),
            ("Empresa", "Empresa"),
            ("Direccion", "Direccion", "textarea"),
            ("Telefono", "Telefono"),
            ("Correo", "Correo"),
        ),
        "editable_fields": fields(
            ("Empresa", "Empresa"),
            ("Direccion", "Direccion", "textarea"),
            ("Telefono", "Telefono"),
            ("Correo", "Correo"),
        ),
        "create_fields": fields(
            field("Empresa", "Empresa", required=True),
            ("Direccion", "Direccion", "textarea"),
            ("Telefono", "Telefono"),
            ("Correo", "Correo"),
        ),
        "search_fields": ["Num_emp", "Empresa", "Direccion", "Telefono", "Correo"],
        "order_by": "Empresa",
    },
    "practicas": {
        "title": "Practicas profesionales",
        "category": "Vinculacion",
        "description": "Practicas por estudiante, empresa, tutor, fechas y horas.",
        "table": "[dbo].[PRACTICASPROFESIONALES]",
        "key_fields": ["codigo_estud", "cod_anio_Basica", "codigo_periodo", "FechaInicio"],
        "list_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Cod_empresa", "Empresa", "number"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFinal", "Fin", "date"),
            ("NoHoras", "Horas", "number"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Cod_empresa", "Empresa", "number"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFinal", "Fin", "date"),
            ("NoHoras", "Horas", "number"),
            ("CodDocente", "Docente tutor", "number"),
            ("DetalleProyecto", "Proyecto", "textarea"),
            ("Semestre", "Semestre", "number"),
            ("pathAr", "Archivo"),
        ),
        "editable_fields": fields(
            ("Cod_empresa", "Empresa", "number"),
            ("FechaFinal", "Fin", "date"),
            ("NoHoras", "Horas", "number"),
            ("CodDocente", "Docente tutor", "number"),
            ("DetalleProyecto", "Proyecto", "textarea"),
            ("Semestre", "Semestre", "number"),
            ("pathAr", "Archivo"),
        ),
        "search_fields": ["codigo_estud", "cod_anio_Basica", "codigo_periodo", "Cod_empresa", "CodDocente", "DetalleProyecto"],
        "order_by": "FechaInicio DESC",
    },
    "pagos_matricula": {
        "title": "Pagos de matricula",
        "category": "Matricula",
        "description": "Registro de pagos, depositos y valores asociados a matricula.",
        "table": "[dbo].[REGISTROPAGOS]",
        "key_fields": ["NumReg"],
        "list_fields": fields(
            ("NumReg", "Registro", "number"),
            ("Codestu", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("codperiodo", "Periodo", "number"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("fechapago", "Fecha pago", "date"),
            ("Detalle", "Detalle"),
            ("Valor", "Valor", "decimal"),
        ),
        "detail_fields": fields(
            ("NumReg", "Registro", "number"),
            ("Codestu", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("Num", "Numero", "number"),
            ("codperiodo", "Periodo", "number"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("fechapago", "Fecha pago", "date"),
            ("Detalle", "Detalle", "textarea"),
            ("Valor", "Valor", "decimal"),
            ("FechaRegistro", "Fecha registro", "datetime"),
            ("usuarioreg", "Usuario"),
            ("urldeposito", "URL deposito"),
            ("NoDeposito", "No. deposito"),
            ("Banco", "Banco"),
            ("FechaDeposito", "Fecha deposito", "date"),
            ("ValorRegistrado", "Valor registrado", "decimal"),
        ),
        "editable_fields": fields(
            ("fechapago", "Fecha pago", "date"),
            ("Detalle", "Detalle", "textarea"),
            ("Valor", "Valor", "decimal"),
            ("urldeposito", "URL deposito"),
            ("NoDeposito", "No. deposito"),
            ("Banco", "Banco"),
            ("FechaDeposito", "Fecha deposito", "date"),
            ("ValorRegistrado", "Valor registrado", "decimal"),
        ),
        "create_fields": fields(
            field("Codestu", "Estudiante", "number", required=True),
            ("Num", "Numero", "number"),
            field("codperiodo", "Periodo", "number", required=True),
            field("cod_anio_Basica", "Carrera", "number", required=True),
            ("fechapago", "Fecha pago", "date"),
            ("Detalle", "Detalle", "textarea"),
            ("Valor", "Valor", "decimal"),
            ("NoDeposito", "No. deposito"),
            ("Banco", "Banco"),
            ("FechaDeposito", "Fecha deposito", "date"),
            ("ValorRegistrado", "Valor registrado", "decimal"),
            ("urldeposito", "URL deposito"),
        ),
        "search_fields": ["NumReg", "Codestu", "codperiodo", "cod_anio_Basica", "Detalle", "NoDeposito", "Banco"],
        "order_by": "fechapago DESC, NumReg DESC",
        "defaults": {"fechapago": "today", "FechaRegistro": "now", "usuarioreg": "current_user", "Num": 0, "Valor": 0},
    },
    "mallas": {
        "title": "Mallas por carrera",
        "category": "Academico",
        "description": "Mallas activas por carrera usadas para materias, niveles y asignacion docente.",
        "table": "[dbo].[MALLA_PENSUM]",
        "key_fields": ["Malla", "Cod_Carrera"],
        "list_fields": fields(
            ("Malla", "Malla", "number"),
            ("Cod_Carrera", "Carrera", "number"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("Num", "Registro", "number"),
            ("Malla", "Malla", "number"),
            ("Cod_Carrera", "Carrera", "number"),
            ("Estado", "Estado"),
        ),
        "editable_fields": fields(("Estado", "Estado")),
        "create_fields": fields(
            field("Malla", "Malla", "number", required=True),
            field("Cod_Carrera", "Carrera", "number", required=True),
            ("Estado", "Estado"),
        ),
        "search_fields": ["Malla", "Cod_Carrera", "Estado"],
        "order_by": "Cod_Carrera, Malla",
        "defaults": {"Estado": "A"},
    },
    "materia_homo_textof": {
        "title": "Textos de materias HOMO",
        "category": "Academico",
        "description": "Texto, URL y fecha visible por materia homologada y periodo academico.",
        "table": "[dbo].[MATERIAHOMOTEXTOF]",
        "key_fields": ["num"],
        "list_fields": fields(
            ("num", "Registro", "number"),
            ("cod_materia", "Codigo materia"),
            ("materia", "Materia"),
            ("cod_periodo", "Periodo", "number"),
            ("textofecha", "Texto fecha", "textarea"),
            ("url", "URL"),
        ),
        "detail_fields": fields(
            ("num", "Registro", "number"),
            ("cod_materia", "Codigo materia"),
            ("materia", "Materia"),
            ("cod_periodo", "Periodo", "number"),
            ("textofecha", "Texto fecha", "textarea"),
            ("url", "URL"),
        ),
        "editable_fields": fields(
            ("cod_materia", "Codigo materia"),
            ("materia", "Materia"),
            ("cod_periodo", "Periodo", "number"),
            ("textofecha", "Texto fecha", "textarea"),
            ("url", "URL"),
        ),
        "create_fields": fields(
            field("cod_materia", "Codigo materia", required=True),
            ("materia", "Materia"),
            field("cod_periodo", "Periodo", "number", required=True),
            field("textofecha", "Texto fecha", "textarea", required=True),
            ("url", "URL"),
        ),
        "search_fields": ["num", "cod_materia", "cod_periodo", "materia", "textofecha", "url"],
        "order_by": "cod_periodo DESC, cod_materia",
    },
    "cambio_periodo_hr": {
        "title": "Migración matrícula H a R",
        "category": "Academico",
        "description": "Migra matrículas HOMO a matrícula regular con excepciones por cédula.",
        "table": "dbo.CARRERAXESTUD + dbo.CABECERA_MATRICULA + dbo.PERIODO",
        "key_fields": ["codigo_periodo"],
        "list_fields": fields(
            ("codigo_periodo", "Periodo origen", "number"),
            ("TipoMatricula", "Tipo matricula"),
        ),
        "detail_fields": fields(
            ("codigo_periodo", "Periodo origen", "number"),
            ("TipoMatricula", "Tipo matricula"),
        ),
        "editable_fields": fields(),
        "create_fields": fields(),
        "search_fields": ["codigo_periodo", "TipoMatricula"],
        "order_by": "codigo_periodo DESC",
    },
    "jornadas": {
        "title": "Jornadas",
        "category": "Catalogos",
        "description": "Catalogo de jornadas por modalidad.",
        "table": "[dbo].[JORNADA]",
        "key_fields": ["NumJ"],
        "list_fields": fields(
            ("NumJ", "Codigo", "number"),
            ("DetalleJ", "Jornada"),
            ("codmodalidad", "Modalidad", "number"),
        ),
        "detail_fields": fields(
            ("NumJ", "Codigo", "number"),
            ("DetalleJ", "Jornada"),
            ("codmodalidad", "Modalidad", "number"),
        ),
        "editable_fields": fields(("DetalleJ", "Jornada"), ("codmodalidad", "Modalidad", "number")),
        "create_fields": fields(
            field("NumJ", "Codigo", "number", required=True),
            field("DetalleJ", "Jornada", required=True),
            ("codmodalidad", "Modalidad", "number"),
        ),
        "search_fields": ["NumJ", "DetalleJ", "codmodalidad"],
        "order_by": "DetalleJ",
        "defaults": {"codmodalidad": 1},
    },
    "modalidades": {
        "title": "Modalidades de matricula",
        "category": "Catalogos",
        "description": "Modalidades usadas en admision y matricula.",
        "table": "[dbo].[ModalidadMatricula]",
        "key_fields": ["NumM"],
        "list_fields": fields(("NumM", "Codigo", "number"), ("DetalleM", "Modalidad")),
        "detail_fields": fields(("NumM", "Codigo", "number"), ("DetalleM", "Modalidad")),
        "editable_fields": fields(("DetalleM", "Modalidad")),
        "create_fields": fields(field("DetalleM", "Modalidad", required=True)),
        "search_fields": ["NumM", "DetalleM"],
        "order_by": "DetalleM",
    },
    "menu_general": {
        "title": "Mapa operativo SisAcademicoV1",
        "category": "Seguridad",
        "description": "Mapa funcional de procesos clonados desde SisAcademicoV1. La tabla legacy queda como respaldo tecnico.",
        "table": "[dbo].[MENU_GENERAL]",
        "key_fields": ["ID", "idGrupo", "idOpcion"],
        "list_fields": fields(
            ("ID", "Id", "number"),
            ("idGrupo", "Grupo id", "number"),
            ("Grupo", "Grupo"),
            ("idOpcion", "Opcion id", "number"),
            ("Opcion", "Opcion"),
            ("url", "URL"),
            ("ReporteCry", "Reporte", "number"),
        ),
        "detail_fields": fields(
            ("ID", "Id", "number"),
            ("idGrupo", "Grupo id", "number"),
            ("Grupo", "Grupo"),
            ("idOpcion", "Opcion id", "number"),
            ("Opcion", "Opcion"),
            ("url", "URL"),
            ("ReporteCry", "Reporte", "number"),
        ),
        "editable_fields": fields(("Grupo", "Grupo"), ("Opcion", "Opcion"), ("url", "URL"), ("ReporteCry", "Reporte", "number")),
        "search_fields": ["ID", "idGrupo", "Grupo", "idOpcion", "Opcion", "url"],
        "order_by": "idGrupo, idOpcion",
    },
    "menu_usuarios": {
        "title": "Accesos operativos por usuario",
        "category": "Seguridad",
        "description": "Mapa funcional de accesos por perfil. La tabla MENU_USUARIOS queda como respaldo tecnico.",
        "table": "[dbo].[MENU_USUARIOS]",
        "key_fields": ["id_usuarios", "idGrupo", "idOpcion"],
        "list_fields": fields(
            ("id_usuarios", "Usuario", "number"),
            ("idGrupo", "Grupo id", "number"),
            ("Grupo", "Grupo"),
            ("idOpcion", "Opcion id", "number"),
            ("Opcion", "Opcion"),
            ("url", "URL"),
        ),
        "detail_fields": fields(
            ("id_usuarios", "Usuario", "number"),
            ("idGrupo", "Grupo id", "number"),
            ("Grupo", "Grupo"),
            ("idOpcion", "Opcion id", "number"),
            ("Opcion", "Opcion"),
            ("url", "URL"),
            ("ReporteCry", "Reporte", "number"),
            ("Num", "Registro", "number"),
        ),
        "editable_fields": fields(("Grupo", "Grupo"), ("Opcion", "Opcion"), ("url", "URL"), ("ReporteCry", "Reporte", "number")),
        "create_fields": fields(
            field("id_usuarios", "Usuario", "number", required=True),
            field("idGrupo", "Grupo id", "number", required=True),
            ("Grupo", "Grupo"),
            field("idOpcion", "Opcion id", "number", required=True),
            ("Opcion", "Opcion"),
            ("url", "URL"),
            ("ReporteCry", "Reporte", "number"),
        ),
        "search_fields": ["id_usuarios", "idGrupo", "Grupo", "idOpcion", "Opcion", "url"],
        "order_by": "id_usuarios, idGrupo, idOpcion",
    },
    "seguimiento": {
        "title": "Seguimiento estudiante",
        "category": "Acompanamiento",
        "description": "Observaciones y seguimiento activo por estudiante, periodo y materia.",
        "table": "[dbo].[SEGUIMIENTO_ESTUDIANTE]",
        "key_fields": ["id"],
        "list_fields": fields(
            ("id", "Id", "number"),
            ("codigo_estud", "Codigo estudiante"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("codigo_periodo", "Periodo"),
            ("codigo_materia", "Materia"),
            ("tipo_seguimiento", "Tipo"),
            ("fecha_registro", "Fecha", "datetime"),
            ("activo", "Activo", "bool"),
        ),
        "detail_fields": fields(
            ("id", "Id", "number"),
            ("codigo_estud", "Codigo estudiante"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("codigo_periodo", "Periodo"),
            ("codigo_materia", "Materia"),
            ("tipo_seguimiento", "Tipo"),
            ("observacion", "Observacion", "textarea"),
            ("fecha_registro", "Fecha registro", "datetime"),
            ("usuario_registro", "Usuario"),
            ("activo", "Activo", "bool"),
            ("fecha_modificacion", "Fecha modificacion", "datetime"),
            ("usuario_modificacion", "Usuario modificacion"),
            ("nombres", "Nombres"),
        ),
        "editable_fields": fields(
            ("tipo_seguimiento", "Tipo"),
            ("observacion", "Observacion", "textarea"),
            ("usuario_registro", "Usuario"),
            ("activo", "Activo", "bool"),
            ("usuario_modificacion", "Usuario modificacion"),
            ("nombres", "Nombres"),
        ),
        "create_fields": fields(
            field("codigo_estud", "Estudiante", required=True),
            field("codigo_periodo", "Periodo", required=True),
            field("codigo_materia", "Materia", required=True),
            ("tipo_seguimiento", "Tipo"),
            field("observacion", "Observacion", "textarea", required=True),
            ("usuario_registro", "Usuario"),
            ("nombres", "Nombres"),
        ),
        "search_fields": ["id", "codigo_estud", "codigo_periodo", "codigo_materia", "tipo_seguimiento", "observacion", "nombres"],
        "order_by": "fecha_registro DESC",
        "defaults": {"fecha_registro": "now", "activo": True},
    },
    "datos_factura": {
        "title": "Datos de factura",
        "category": "Admision",
        "description": "Datos tributarios heredados del flujo de preinscripcion y prematricula.",
        "table": "[dbo].[DATOSFACTURA]",
        "key_fields": ["CODESTUD"],
        "list_fields": fields(
            ("CODESTUD", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula estudiante"),
            ("CEDRUCFACTURA", "Cedula/RUC"),
            ("NOMBRES", "Nombre factura"),
            ("TELELFONO", "Telefono"),
            ("CORREO", "Correo"),
        ),
        "detail_fields": fields(
            ("CODESTUD", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula estudiante"),
            ("CEDESTUD", "Cedula estudiante"),
            ("CEDRUCFACTURA", "Cedula/RUC"),
            ("NOMBRES", "Nombre factura"),
            ("DIRECCION", "Direccion", "textarea"),
            ("TELELFONO", "Telefono"),
            ("CORREO", "Correo"),
        ),
        "editable_fields": fields(
            ("CEDRUCFACTURA", "Cedula/RUC"),
            ("NOMBRES", "Nombre factura"),
            ("DIRECCION", "Direccion", "textarea"),
            ("TELELFONO", "Telefono"),
            ("CORREO", "Correo"),
        ),
        "create_fields": fields(
            field("CODESTUD", "Codigo estudiante", "number", required=True),
            field("CEDESTUD", "Cedula estudiante", required=True),
            field("CEDRUCFACTURA", "Cedula/RUC", required=True),
            field("NOMBRES", "Nombre factura", required=True),
            ("DIRECCION", "Direccion", "textarea"),
            ("TELELFONO", "Telefono"),
            ("CORREO", "Correo"),
        ),
        "search_fields": ["CODESTUD", "CEDESTUD", "CEDRUCFACTURA", "NOMBRES", "TELELFONO", "CORREO"],
        "order_by": "NOMBRES",
    },
    "fechas_notas": {
        "title": "Apertura de notas",
        "category": "Control academico",
        "description": "Rangos de fechas para habilitar ingreso de notas por parcial y periodo.",
        "table": "[dbo].[ACTIVAREXAMEN]",
        "key_fields": ["NumNota", "periodo_acad"],
        "list_fields": fields(
            ("periodo_acad", "Periodo", "number"),
            ("NumNota", "Parcial", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "detail_fields": fields(
            ("NumNota", "Parcial", "number"),
            ("periodo_acad", "Periodo", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "editable_fields": fields(
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "create_fields": fields(
            field("NumNota", "Parcial", "number", required=True),
            field("periodo_acad", "Periodo", "number", required=True),
            field("fecha_inicio", "Inicio", "datetime", required=True),
            field("fecha_final", "Fin", "datetime", required=True),
            ("estado", "Estado"),
        ),
        "search_fields": ["NumNota", "periodo_acad", "estado"],
        "order_by": "periodo_acad DESC, NumNota",
        "defaults": {"estado": "A"},
    },
    "fechas_autoevaluacion": {
        "title": "Apertura de autoevaluacion",
        "category": "Control academico",
        "description": "Rango vigente para autoevaluacion docente por periodo academico.",
        "table": "[dbo].[ACTIVARAUTOEVALUACION]",
        "key_fields": ["periodo_acad"],
        "list_fields": fields(
            ("periodo_acad", "Periodo", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "detail_fields": fields(
            ("periodo_acad", "Periodo", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "editable_fields": fields(
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("estado", "Estado"),
        ),
        "create_fields": fields(
            field("periodo_acad", "Periodo", "number", required=True),
            field("fecha_inicio", "Inicio", "datetime", required=True),
            field("fecha_final", "Fin", "datetime", required=True),
            ("estado", "Estado"),
        ),
        "search_fields": ["periodo_acad", "estado"],
        "order_by": "periodo_acad DESC",
        "defaults": {"estado": "A"},
    },
    "evaluacion_resultados": {
        "title": "Resultados de evaluacion",
        "category": "Docencia",
        "description": "Respuestas y puntajes de evaluacion docente, pares academicos y autoevaluacion.",
        "table": "[dbo].[RESULTADO_EVALUACION]",
        "key_fields": ["Cod_Docente", "NoPregunta", "TipoPreg", "Cod_periodo", "Cod_Materia"],
        "list_fields": fields(
            ("Cod_periodo", "Periodo", "number"),
            ("Cod_Doc_Eval", "Docente evaluado", "number"),
            ("Cod_Docente", "Evaluador/estudiante", "number"),
            ("Cod_Materia", "Materia", "number"),
            ("NoPregunta", "Pregunta", "number"),
            ("TipoPreg", "Tipo", "number"),
            ("Puntaje", "Puntaje", "number"),
            ("fecha", "Fecha", "datetime"),
        ),
        "detail_fields": fields(
            ("Cod_Docente", "Evaluador/estudiante", "number"),
            ("Cod_Doc_Eval", "Docente evaluado", "number"),
            ("NoPregunta", "Pregunta", "number"),
            ("Detalle_Preg", "Detalle pregunta", "textarea"),
            ("TipoPreg", "Tipo pregunta", "number"),
            ("Cod_periodo", "Periodo", "number"),
            ("fecha", "Fecha", "datetime"),
            ("Puntaje", "Puntaje", "number"),
            ("Cod_Materia", "Materia", "number"),
            ("Jornada", "Jornada"),
            ("Paralelo", "Paralelo"),
        ),
        "editable_fields": fields(
            ("Detalle_Preg", "Detalle pregunta", "textarea"),
            ("fecha", "Fecha", "datetime"),
            ("Puntaje", "Puntaje", "number"),
            ("Cod_Doc_Eval", "Docente evaluado", "number"),
            ("Jornada", "Jornada"),
            ("Paralelo", "Paralelo"),
        ),
        "create_fields": fields(
            field("Cod_Docente", "Evaluador/estudiante", "number", required=True),
            field("NoPregunta", "Pregunta", "number", required=True),
            field("Detalle_Preg", "Detalle pregunta", "textarea", required=True),
            field("TipoPreg", "Tipo pregunta", "number", required=True),
            field("Cod_periodo", "Periodo", "number", required=True),
            ("fecha", "Fecha", "datetime"),
            field("Puntaje", "Puntaje", "number", required=True),
            field("Cod_Materia", "Materia", "number", required=True),
            ("Cod_Doc_Eval", "Docente evaluado", "number"),
            ("Jornada", "Jornada"),
            ("Paralelo", "Paralelo"),
        ),
        "search_fields": ["Cod_Docente", "Cod_Doc_Eval", "NoPregunta", "TipoPreg", "Cod_periodo", "Cod_Materia", "Detalle_Preg", "Jornada", "Paralelo"],
        "order_by": "Cod_periodo DESC, Cod_Doc_Eval, Cod_Materia, NoPregunta",
        "defaults": {"fecha": "now"},
    },
    "preguntas_evaluacion": {
        "title": "Preguntas de evaluacion",
        "category": "Docencia",
        "description": "Banco de preguntas usado por evaluacion docente, pares academicos y autoevaluacion.",
        "table": "[dbo].[CUESTIONARIOEVALUA]",
        "key_fields": ["NoPregunta", "TipoPreg", "control"],
        "list_fields": fields(
            ("NoPregunta", "No. pregunta", "number"),
            ("Detalle_Preg", "Pregunta", "textarea"),
            ("TipoPreg", "Tipo pregunta", "number"),
            ("Comentariocoord", "Comentario coordinacion", "textarea"),
            ("control", "Control", "number"),
        ),
        "detail_fields": fields(
            ("NoPregunta", "No. pregunta", "number"),
            ("Detalle_Preg", "Pregunta", "textarea"),
            ("TipoPreg", "Tipo pregunta", "number"),
            ("Comentariocoord", "Comentario coordinacion", "textarea"),
            ("control", "Control", "number"),
        ),
        "editable_fields": fields(
            ("Detalle_Preg", "Pregunta", "textarea"),
            ("Comentariocoord", "Comentario coordinacion", "textarea"),
            ("control", "Control", "number"),
        ),
        "create_fields": fields(
            field("NoPregunta", "No. pregunta", "number", required=True),
            field("Detalle_Preg", "Pregunta", "textarea", required=True),
            field("TipoPreg", "Tipo pregunta", "number", required=True),
            ("Comentariocoord", "Comentario coordinacion", "textarea"),
            ("control", "Control", "number"),
        ),
        "search_fields": ["NoPregunta", "Detalle_Preg", "TipoPreg", "Comentariocoord", "control"],
        "order_by": "control, TipoPreg, NoPregunta",
        "defaults": {"control": 1},
    },
    "asistencia_estudiantes": {
        "title": "Asistencia estudiantes",
        "category": "Control academico",
        "description": "Registro de asistencia por estudiante, materia, periodo, paralelo, fecha y jornada.",
        "table": "[dbo].[ASISTENCIAESTUD]",
        "key_fields": ["codigo_estud", "cod_anio_Basica", "codigo_materia", "codigo_periodo", "paralelo", "FechaHora"],
        "list_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("paralelo", "Paralelo"),
            ("Fecha", "Fecha", "date"),
            ("Asistencia", "Asistencia", "number"),
        ),
        "detail_fields": fields(
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_materia", "Materia", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("paralelo", "Paralelo"),
            ("FechaHora", "Fecha/hora", "datetime"),
            ("Fecha", "Fecha", "date"),
            ("jornada", "Jornada"),
            ("Hora", "Hora"),
            ("Asistencia", "Asistencia", "number"),
        ),
        "editable_fields": fields(
            ("FechaHora", "Fecha/hora", "datetime"),
            ("Fecha", "Fecha", "date"),
            ("jornada", "Jornada"),
            ("Hora", "Hora"),
            ("Asistencia", "Asistencia", "number"),
        ),
        "create_fields": fields(
            field("codigo_estud", "Estudiante", "number", required=True),
            field("cod_anio_Basica", "Carrera", "number", required=True),
            field("codigo_materia", "Materia", "number", required=True),
            field("codigo_periodo", "Periodo", "number", required=True),
            field("paralelo", "Paralelo", required=True),
            ("FechaHora", "Fecha/hora", "datetime"),
            ("Fecha", "Fecha", "date"),
            ("jornada", "Jornada"),
            ("Hora", "Hora"),
            ("Asistencia", "Asistencia", "number"),
        ),
        "search_fields": ["codigo_estud", "cod_anio_Basica", "codigo_materia", "codigo_periodo", "paralelo", "jornada", "Asistencia"],
        "order_by": "FechaHora DESC, codigo_estud",
        "defaults": {"FechaHora": "now", "Fecha": "today", "Asistencia": 1},
    },
    "provincias": {
        "title": "Provincias",
        "category": "Catalogos",
        "description": "Catalogo territorial utilizado en inscripcion y datos del estudiante.",
        "table": "[dbo].[Provincias]",
        "key_fields": ["Cod_Provincia"],
        "list_fields": fields(
            ("Cod_Provincia", "Codigo"),
            ("Descripcion_Prov", "Provincia"),
            ("Cod_Pais", "Pais"),
            ("activo", "Activo", "bool"),
        ),
        "detail_fields": fields(
            ("Cod_Provincia", "Codigo"),
            ("Cod_Pais", "Pais"),
            ("Descripcion_Prov", "Provincia"),
            ("activo", "Activo", "bool"),
            ("fecha_creacion", "Fecha creacion", "datetime"),
        ),
        "editable_fields": fields(
            ("Cod_Pais", "Pais"),
            ("Descripcion_Prov", "Provincia"),
            ("activo", "Activo", "bool"),
        ),
        "create_fields": fields(
            field("Cod_Provincia", "Codigo", required=True),
            field("Cod_Pais", "Pais", required=True),
            field("Descripcion_Prov", "Provincia", required=True),
            ("activo", "Activo", "bool"),
            ("fecha_creacion", "Fecha creacion", "datetime"),
        ),
        "search_fields": ["Cod_Provincia", "Cod_Pais", "Descripcion_Prov"],
        "order_by": "Descripcion_Prov",
        "defaults": {"activo": True, "fecha_creacion": "now"},
    },
    "dias_matricula": {
        "title": "Dias de matricula",
        "category": "Catalogos",
        "description": "Catalogo legacy de dias usados por el proceso de matricula.",
        "table": "[dbo].[DiasMatricula]",
        "key_fields": ["numd"],
        "list_fields": fields(("numd", "Codigo", "number"), ("Detalledias", "Detalle")),
        "detail_fields": fields(("numd", "Codigo", "number"), ("Detalledias", "Detalle")),
        "editable_fields": fields(("Detalledias", "Detalle")),
        "create_fields": fields(field("Detalledias", "Detalle", required=True)),
        "search_fields": ["numd", "Detalledias"],
        "order_by": "Detalledias",
    },
    "horarios_matricula": {
        "title": "Horarios de matricula",
        "category": "Catalogos",
        "description": "Catalogo legacy de horarios usados por el proceso de matricula.",
        "table": "[dbo].[HorarioMatricula]",
        "key_fields": ["Numh"],
        "list_fields": fields(("Numh", "Codigo", "number"), ("DetalleH", "Detalle")),
        "detail_fields": fields(("Numh", "Codigo", "number"), ("DetalleH", "Detalle")),
        "editable_fields": fields(("DetalleH", "Detalle")),
        "create_fields": fields(field("DetalleH", "Detalle", required=True)),
        "search_fields": ["Numh", "DetalleH"],
        "order_by": "DetalleH",
    },
    "repositorio": {
        "title": "Repositorio digital",
        "category": "Documentacion",
        "description": "Documentos bibliograficos y enlaces por carrera del repositorio legacy.",
        "table": "[dbo].[REPOSITORIO]",
        "key_fields": ["num"],
        "list_fields": fields(
            ("num", "Codigo", "number"),
            ("codcarrera", "Carrera", "number"),
            ("tipodocumento", "Tipo documento"),
            ("titulo", "Titulo"),
            ("autor", "Autor"),
            ("materia", "Materia"),
            ("anio", "Anio", "number"),
        ),
        "detail_fields": fields(
            ("num", "Codigo", "number"),
            ("codcarrera", "Carrera", "number"),
            ("tipodocumento", "Tipo documento"),
            ("titulo", "Titulo"),
            ("autor", "Autor"),
            ("palabraclave", "Palabras clave", "textarea"),
            ("fechapublica", "Fecha publicacion", "date"),
            ("editorial", "Editorial"),
            ("url", "URL"),
            ("materia", "Materia"),
            ("resumen", "Resumen", "textarea"),
            ("urlarchivo", "Archivo"),
            ("anio", "Anio", "number"),
        ),
        "editable_fields": fields(
            ("codcarrera", "Carrera", "number"),
            ("tipodocumento", "Tipo documento"),
            ("titulo", "Titulo"),
            ("autor", "Autor"),
            ("palabraclave", "Palabras clave", "textarea"),
            ("editorial", "Editorial"),
            ("url", "URL"),
            ("materia", "Materia"),
            ("resumen", "Resumen", "textarea"),
            ("urlarchivo", "Archivo"),
            ("anio", "Anio", "number"),
        ),
        "create_fields": fields(
            field("codcarrera", "Carrera", "number", required=True),
            ("tipodocumento", "Tipo documento"),
            field("titulo", "Titulo", required=True),
            ("autor", "Autor"),
            ("palabraclave", "Palabras clave", "textarea"),
            ("fechapublica", "Fecha publicacion", "date"),
            ("editorial", "Editorial"),
            ("url", "URL"),
            ("materia", "Materia"),
            ("resumen", "Resumen", "textarea"),
            ("urlarchivo", "Archivo"),
            ("anio", "Anio", "number"),
        ),
        "search_fields": ["num", "codcarrera", "tipodocumento", "titulo", "autor", "palabraclave", "materia", "anio"],
        "order_by": "anio DESC, titulo",
        "defaults": {"fechapublica": "today"},
    },
    "registro_documentos_estudiante": {
        "title": "Documentos del estudiante",
        "category": "Documentacion",
        "description": "Archivos y observaciones anexados a la ficha del estudiante en legacy.",
        "table": "[dbo].[REGISTRODOCESTUD]",
        "key_fields": ["num"],
        "list_fields": fields(
            ("num", "Codigo", "number"),
            ("IDESTUD", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("DETALLE", "Detalle"),
            ("LINKURL", "Archivo"),
        ),
        "detail_fields": fields(
            ("num", "Codigo", "number"),
            ("IDESTUD", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("DETALLE", "Detalle", "textarea"),
            ("LINKURL", "Archivo"),
        ),
        "editable_fields": fields(
            ("IDESTUD", "Codigo estudiante", "number"),
            ("DETALLE", "Detalle", "textarea"),
            ("LINKURL", "Archivo"),
        ),
        "create_fields": fields(
            field("IDESTUD", "Codigo estudiante", "number", required=True),
            field("DETALLE", "Detalle", "textarea", required=True),
            ("LINKURL", "Archivo"),
        ),
        "search_fields": ["num", "IDESTUD", "DETALLE", "LINKURL"],
        "order_by": "num DESC",
    },
    "numero_preguntas": {
        "title": "Control de cuestionarios",
        "category": "Docencia",
        "description": "Numero de preguntas, intentos y tiempo de resolucion por materia y periodo.",
        "table": "[dbo].[NUMEROPREGALEAT]",
        "key_fields": ["Cod_Materia", "Cod_periodo"],
        "list_fields": fields(
            ("Cod_periodo", "Periodo", "number"),
            ("Cod_Materia", "Materia", "number"),
            ("NotaBaseEval", "Nota base", "decimal"),
            ("Numero_Preg", "Preguntas", "number"),
            ("Num_Intentos", "Intentos", "number"),
            ("Tiempo_resolver", "Tiempo", "number"),
            ("unidades", "Unidades", "number"),
        ),
        "detail_fields": fields(
            ("Cod_periodo", "Periodo", "number"),
            ("Cod_Materia", "Materia", "number"),
            ("NotaBaseEval", "Nota base", "decimal"),
            ("Numero_Preg", "Preguntas", "number"),
            ("Num_Intentos", "Intentos", "number"),
            ("Tiempo_resolver", "Tiempo resolver", "number"),
            ("unidades", "Unidades", "number"),
        ),
        "editable_fields": fields(
            ("NotaBaseEval", "Nota base", "decimal"),
            ("Numero_Preg", "Preguntas", "number"),
            ("Num_Intentos", "Intentos", "number"),
            ("Tiempo_resolver", "Tiempo resolver", "number"),
            ("unidades", "Unidades", "number"),
        ),
        "create_fields": fields(
            field("Cod_periodo", "Periodo", "number", required=True),
            field("Cod_Materia", "Materia", "number", required=True),
            ("NotaBaseEval", "Nota base", "decimal"),
            ("Numero_Preg", "Preguntas", "number"),
            ("Num_Intentos", "Intentos", "number"),
            ("Tiempo_resolver", "Tiempo resolver", "number"),
            ("unidades", "Unidades", "number"),
        ),
        "search_fields": ["Cod_periodo", "Cod_Materia"],
        "order_by": "Cod_periodo DESC, Cod_Materia",
    },
    "cuestionarios": {
        "title": "Banco de preguntas",
        "category": "Docencia",
        "description": "Preguntas, respuestas y retroalimentacion de cuestionarios por unidad.",
        "table": "[dbo].[CUESTIONARIO]",
        "key_fields": ["No_Pregunta", "cod_periodo", "cod_materia", "Unidad", "Tipo_Pregunta"],
        "list_fields": fields(
            ("cod_periodo", "Periodo", "number"),
            ("cod_materia", "Materia", "number"),
            ("Unidad", "Unidad", "number"),
            ("No_Pregunta", "Pregunta", "number"),
            ("Tipo_Pregunta", "Tipo", "number"),
            ("Pregunta", "Texto"),
            ("cod_doc", "Docente", "number"),
        ),
        "detail_fields": fields(
            ("No_Pregunta", "Pregunta", "number"),
            ("cod_doc", "Docente", "number"),
            ("cod_periodo", "Periodo", "number"),
            ("cod_materia", "Materia", "number"),
            ("Unidad", "Unidad", "number"),
            ("Tipo_Pregunta", "Tipo", "number"),
            ("Pregunta", "Texto", "textarea"),
            ("Resp1", "Respuesta 1"),
            ("Resp2", "Respuesta 2"),
            ("Resp3", "Respuesta 3"),
            ("Resp4", "Respuesta 4"),
            ("Resp_Correcta", "Respuesta correcta", "number"),
            ("RespVerdadFalso", "Verdadero/Falso"),
            ("Explica_Resp", "Explicacion", "textarea"),
            ("pathimagen", "Imagen"),
        ),
        "editable_fields": fields(
            ("Pregunta", "Texto", "textarea"),
            ("Resp1", "Respuesta 1"),
            ("Resp2", "Respuesta 2"),
            ("Resp3", "Respuesta 3"),
            ("Resp4", "Respuesta 4"),
            ("Resp_Correcta", "Respuesta correcta", "number"),
            ("RespVerdadFalso", "Verdadero/Falso"),
            ("Explica_Resp", "Explicacion", "textarea"),
            ("pathimagen", "Imagen"),
        ),
        "create_fields": fields(
            field("No_Pregunta", "Pregunta", "number", required=True),
            field("cod_doc", "Docente", "number", required=True),
            field("cod_periodo", "Periodo", "number", required=True),
            field("cod_materia", "Materia", "number", required=True),
            field("Unidad", "Unidad", "number", required=True),
            field("Tipo_Pregunta", "Tipo", "number", required=True),
            field("Pregunta", "Texto", "textarea", required=True),
            ("Resp1", "Respuesta 1"),
            ("Resp2", "Respuesta 2"),
            ("Resp3", "Respuesta 3"),
            ("Resp4", "Respuesta 4"),
            ("Resp_Correcta", "Respuesta correcta", "number"),
            ("RespVerdadFalso", "Verdadero/Falso"),
            ("Explica_Resp", "Explicacion", "textarea"),
            ("pathimagen", "Imagen"),
        ),
        "search_fields": ["No_Pregunta", "cod_periodo", "cod_materia", "Pregunta", "cod_doc"],
        "order_by": "cod_periodo DESC, cod_materia, Unidad, No_Pregunta",
    },
    "planes_foros": {
        "title": "Planes, cuestionarios y foros",
        "category": "Docencia",
        "description": "Menu legacy de cuestionarios, foros, fechas y recursos por materia.",
        "table": "[dbo].[REG_MENU_C_FORO]",
        "key_fields": ["Cod_Unidad", "Orden", "cod_materia", "cod_periodo"],
        "list_fields": fields(
            ("cod_periodo", "Periodo", "number"),
            ("cod_materia", "Materia", "number"),
            ("Cod_Unidad", "Unidad", "number"),
            ("Orden", "Orden", "number"),
            ("Detalle_Cuest_Foro", "Detalle"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
        ),
        "detail_fields": fields(
            ("Cod_Unidad", "Unidad", "number"),
            ("Orden", "Orden", "number"),
            ("cod_doc", "Docente", "number"),
            ("cod_materia", "Materia", "number"),
            ("cod_periodo", "Periodo", "number"),
            ("Detalle_Cuest_Foro", "Detalle", "textarea"),
            ("Link_Cuest_Foro", "Link"),
            ("Path_Imagen", "Imagen"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("Mes", "Mes", "number"),
            ("Trimestre", "Trimestre", "number"),
        ),
        "editable_fields": fields(
            ("Detalle_Cuest_Foro", "Detalle", "textarea"),
            ("Link_Cuest_Foro", "Link"),
            ("Path_Imagen", "Imagen"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("Mes", "Mes", "number"),
            ("Trimestre", "Trimestre", "number"),
        ),
        "create_fields": fields(
            field("Cod_Unidad", "Unidad", "number", required=True),
            field("Orden", "Orden", "number", required=True),
            ("cod_doc", "Docente", "number"),
            field("cod_materia", "Materia", "number", required=True),
            field("cod_periodo", "Periodo", "number", required=True),
            ("Detalle_Cuest_Foro", "Detalle", "textarea"),
            ("Link_Cuest_Foro", "Link"),
            ("Path_Imagen", "Imagen"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_final", "Fin", "datetime"),
            ("Mes", "Mes", "number"),
            ("Trimestre", "Trimestre", "number"),
        ),
        "search_fields": ["Cod_Unidad", "Orden", "cod_materia", "cod_periodo", "Detalle_Cuest_Foro", "cod_doc"],
        "order_by": "cod_periodo DESC, cod_materia, Cod_Unidad, Orden",
    },
    "autoevaluacion_resultados": {
        "title": "Resultados de autoevaluacion",
        "category": "Docencia",
        "description": "Puntajes y comentarios de autoevaluacion, coordinacion y direccion.",
        "table": "[dbo].[RESULTADOAUTOEVALUACION]",
        "key_fields": ["Cod_Docente", "NoPregunta", "TipoPreg", "Cod_periodo", "Cod_Carrera"],
        "list_fields": fields(
            ("Cod_periodo", "Periodo", "number"),
            ("Cod_Carrera", "Carrera", "number"),
            ("Cod_Docente", "Docente", "number"),
            ("NoPregunta", "Pregunta", "number"),
            ("TipoPreg", "Tipo", "number"),
            ("Puntaje", "Puntaje", "number"),
            ("Calificacion", "Calificacion", "decimal"),
        ),
        "detail_fields": fields(
            ("Cod_Docente", "Docente", "number"),
            ("NoPregunta", "Pregunta", "number"),
            ("Detalle_Preg", "Detalle", "textarea"),
            ("TipoPreg", "Tipo", "number"),
            ("Cod_periodo", "Periodo", "number"),
            ("fecha", "Fecha", "datetime"),
            ("Puntaje", "Puntaje", "number"),
            ("Cod_Carrera", "Carrera", "number"),
            ("Comentariocoord", "Comentario", "textarea"),
            ("Calificacion", "Calificacion", "decimal"),
        ),
        "editable_fields": fields(
            ("Detalle_Preg", "Detalle", "textarea"),
            ("fecha", "Fecha", "datetime"),
            ("Puntaje", "Puntaje", "number"),
            ("Comentariocoord", "Comentario", "textarea"),
            ("Calificacion", "Calificacion", "decimal"),
        ),
        "create_fields": fields(
            field("Cod_Docente", "Docente", "number", required=True),
            field("NoPregunta", "Pregunta", "number", required=True),
            field("TipoPreg", "Tipo", "number", required=True),
            field("Cod_periodo", "Periodo", "number", required=True),
            field("Cod_Carrera", "Carrera", "number", required=True),
            ("Detalle_Preg", "Detalle", "textarea"),
            ("fecha", "Fecha", "datetime"),
            ("Puntaje", "Puntaje", "number"),
            ("Comentariocoord", "Comentario", "textarea"),
            ("Calificacion", "Calificacion", "decimal"),
        ),
        "search_fields": ["Cod_Docente", "NoPregunta", "TipoPreg", "Cod_periodo", "Cod_Carrera", "Detalle_Preg"],
        "order_by": "Cod_periodo DESC, Cod_Carrera, Cod_Docente, NoPregunta",
        "defaults": {"fecha": "now"},
    },
    "practicas_vinculacion": {
        "title": "Vinculación con la sociedad",
        "category": "Vinculación con la sociedad",
        "description": "Registro de proyectos de vinculación con la sociedad, empresa, docente, horas y evidencias.",
        "table": "[dbo].[PRACTICASVINCULACION]",
        "key_fields": ["num"],
        "list_fields": fields(
            ("num", "Codigo", "number"),
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("NoHoras", "Horas", "number"),
            ("Semestre", "Nivel", "number"),
            ("NombreProyecto", "Proyecto"),
        ),
        "detail_fields": fields(
            ("num", "Codigo", "number"),
            ("codigo_estud", "Codigo estudiante", "number"),
            ("estudiante_nombre", "Estudiante"),
            ("estudiante_cedula", "Cedula"),
            ("cod_anio_Basica", "Carrera", "number"),
            ("codigo_periodo", "Periodo", "number"),
            ("Cod_empresa", "Empresa", "number"),
            ("FechaInicio", "Fecha inicio", "date"),
            ("FechaFinal", "Fecha final", "date"),
            ("NoHoras", "Horas", "number"),
            ("CodDocente", "Docente", "number"),
            ("DetalleProyecto", "Detalle proyecto", "textarea"),
            ("Semestre", "Nivel", "number"),
            ("pathAr", "Archivo"),
            ("NombreProyecto", "Proyecto"),
        ),
        "editable_fields": fields(
            ("Cod_empresa", "Empresa", "number"),
            ("FechaInicio", "Fecha inicio", "date"),
            ("FechaFinal", "Fecha final", "date"),
            ("NoHoras", "Horas", "number"),
            ("CodDocente", "Docente", "number"),
            ("DetalleProyecto", "Detalle proyecto", "textarea"),
            ("Semestre", "Nivel", "number"),
            ("pathAr", "Archivo"),
            ("NombreProyecto", "Proyecto"),
        ),
        "create_fields": fields(
            field("codigo_estud", "Estudiante", "number", required=True),
            field("cod_anio_Basica", "Carrera", "number", required=True),
            field("codigo_periodo", "Periodo", "number", required=True),
            field("Cod_empresa", "Empresa", "number", required=True),
            field("FechaInicio", "Fecha inicio", "date", required=True),
            field("FechaFinal", "Fecha final", "date", required=True),
            field("NoHoras", "Horas", "number", required=True),
            field("CodDocente", "Docente", "number", required=True),
            field("DetalleProyecto", "Detalle proyecto", "textarea", required=True),
            ("Semestre", "Nivel", "number"),
            ("pathAr", "Archivo"),
            ("NombreProyecto", "Proyecto"),
        ),
        "search_fields": ["num", "codigo_estud", "cod_anio_Basica", "codigo_periodo", "Cod_empresa", "CodDocente", "NombreProyecto", "DetalleProyecto"],
        "order_by": "num DESC",
    },
    "certificados_generados": {
        "title": "Certificados generados",
        "category": "Certificados",
        "description": "Historial de certificados institucionales generados desde SisAcademicoV1.",
        "table": "[dbo].[CERTIFICADOS_GENERADOS]",
        "key_fields": ["CertificadoId"],
        "list_fields": fields(
            ("CertificadoId", "Codigo", "number"),
            ("TipoCertificado", "Tipo"),
            ("NumeroCertificado", "Numero"),
            ("CedulaEst", "Cedula"),
            ("ApellidosNombre", "Estudiante"),
            ("FechaGeneracion", "Fecha", "datetime"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("CertificadoId", "Codigo", "number"),
            ("TipoCertificado", "Tipo"),
            ("TipoOrigen", "Origen"),
            ("NumeroCertificado", "Numero"),
            ("CodigoEstud", "Codigo estudiante", "number"),
            ("CedulaEst", "Cedula"),
            ("ApellidosNombre", "Estudiante"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("Num_Matricula", "Matricula", "number"),
            ("CodCurso", "Curso", "number"),
            ("FechaGeneracion", "Fecha generacion", "datetime"),
            ("UsuarioGenero", "Usuario"),
            ("RutaArchivo", "Archivo"),
            ("CodigoVerificacion", "Codigo verificacion"),
            ("Estado", "Estado"),
            ("FechaAnulacion", "Fecha anulacion", "datetime"),
            ("UsuarioAnulacion", "Usuario anulacion"),
            ("MotivoAnulacion", "Motivo anulacion", "textarea"),
            ("Observacion", "Observacion", "textarea"),
        ),
        "editable_fields": fields(
            ("RutaArchivo", "Archivo"),
            ("CodigoVerificacion", "Codigo verificacion"),
            ("Estado", "Estado"),
            ("FechaAnulacion", "Fecha anulacion", "datetime"),
            ("UsuarioAnulacion", "Usuario anulacion"),
            ("MotivoAnulacion", "Motivo anulacion", "textarea"),
            ("Observacion", "Observacion", "textarea"),
        ),
        "search_fields": ["CertificadoId", "TipoCertificado", "TipoOrigen", "NumeroCertificado", "CodigoEstud", "CedulaEst", "ApellidosNombre", "CodigoVerificacion", "Estado"],
        "order_by": "FechaGeneracion DESC, CertificadoId DESC",
    },
    "cursos_edu_continua": {
        "title": "Cursos de educación continua",
        "category": "Educación continua",
        "description": "Cursos cortos y ofertas de educación continua del sistema anterior.",
        "table": "[dbo].[CursosEduContinua]",
        "key_fields": ["CodCurso"],
        "list_fields": fields(
            ("CodCurso", "Codigo", "number"),
            ("Curso", "Curso"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFinal", "Fin", "date"),
            ("Horas", "Horas", "number"),
            ("Estado", "Estado"),
        ),
        "detail_fields": fields(
            ("CodCurso", "Codigo", "number"),
            ("Curso", "Curso"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFinal", "Fin", "date"),
            ("Estado", "Estado"),
            ("Horas", "Horas", "number"),
        ),
        "editable_fields": fields(
            ("Curso", "Curso"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFinal", "Fin", "date"),
            ("Estado", "Estado"),
            ("Horas", "Horas", "number"),
        ),
        "create_fields": fields(
            field("Curso", "Curso", required=True),
            field("FechaInicio", "Inicio", "date", required=True),
            field("FechaFinal", "Fin", "date", required=True),
            field("Estado", "Estado", required=True),
            ("Horas", "Horas", "number"),
        ),
        "search_fields": ["CodCurso", "Curso", "Estado"],
        "order_by": "FechaInicio DESC, CodCurso DESC",
    },
    "corte_curso": {
        "title": "Cortes de curso",
        "category": "Educación continua",
        "description": "Cortes, cupos, fechas y estado de cursos regulares, materias o educación continua.",
        "table": "[dbo].[CORTE_CURSO]",
        "key_fields": ["CorteId"],
        "list_fields": fields(
            ("CorteId", "Codigo", "number"),
            ("TipoOferta", "Oferta"),
            ("NombreCorte", "Corte"),
            ("NumeroCorte", "Numero", "number"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFin", "Fin", "date"),
            ("EstadoCorte", "Estado"),
        ),
        "detail_fields": fields(
            ("CorteId", "Codigo", "number"),
            ("TipoOferta", "Oferta"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("CodCurso", "Curso", "number"),
            ("NumeroCorte", "Numero", "number"),
            ("NombreCorte", "Corte"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFin", "Fin", "date"),
            ("CupoEsperado", "Cupo", "number"),
            ("Horas", "Horas", "number"),
            ("EstadoCorte", "Estado"),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioRegistro", "Usuario registro"),
            ("FechaRegistro", "Fecha registro", "datetime"),
            ("UsuarioModifica", "Usuario modifica"),
            ("FechaModifica", "Fecha modifica", "datetime"),
        ),
        "editable_fields": fields(
            ("TipoOferta", "Oferta"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("CodCurso", "Curso", "number"),
            ("NumeroCorte", "Numero", "number"),
            ("NombreCorte", "Corte"),
            ("FechaInicio", "Inicio", "date"),
            ("FechaFin", "Fin", "date"),
            ("CupoEsperado", "Cupo", "number"),
            ("Horas", "Horas", "number"),
            ("EstadoCorte", "Estado"),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioModifica", "Usuario modifica"),
            ("FechaModifica", "Fecha modifica", "datetime"),
        ),
        "create_fields": fields(
            field("TipoOferta", "Oferta", required=True),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("CodCurso", "Curso", "number"),
            field("NumeroCorte", "Numero", "number", required=True),
            field("NombreCorte", "Corte", required=True),
            field("FechaInicio", "Inicio", "date", required=True),
            ("FechaFin", "Fin", "date"),
            ("CupoEsperado", "Cupo", "number"),
            ("Horas", "Horas", "number"),
            field("EstadoCorte", "Estado", required=True),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioRegistro", "Usuario registro"),
            ("FechaRegistro", "Fecha registro", "datetime"),
        ),
        "search_fields": ["CorteId", "TipoOferta", "Cod_AnioBasica", "CodigoPeriodo", "CodigoMateria", "CodCurso", "NombreCorte", "EstadoCorte"],
        "order_by": "FechaInicio DESC, CorteId DESC",
        "defaults": {"FechaRegistro": "now"},
    },
    "corte_curso_estudiante": {
        "title": "Estudiantes por corte",
        "category": "Educación continua",
        "description": "Participantes vinculados a cortes de curso y su estado de registro.",
        "table": "[dbo].[CORTE_CURSO_ESTUDIANTE]",
        "key_fields": ["CorteEstudianteId"],
        "list_fields": fields(
            ("CorteEstudianteId", "Codigo", "number"),
            ("CorteId", "Corte", "number"),
            ("CodigoEstud", "Codigo estudiante", "number"),
            ("CedulaEst", "Cedula"),
            ("ApellidosNombre", "Estudiante"),
            ("EstadoParticipacion", "Participacion"),
            ("EstadoRegistro", "Registro"),
        ),
        "detail_fields": fields(
            ("CorteEstudianteId", "Codigo", "number"),
            ("CorteId", "Corte", "number"),
            ("CodigoEstud", "Codigo estudiante", "number"),
            ("CedulaEst", "Cedula"),
            ("ApellidosNombre", "Estudiante"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("Num_Matricula", "Matricula", "number"),
            ("CodCurso", "Curso", "number"),
            ("FechaInicioEstudiante", "Fecha inicio", "date"),
            ("EstadoParticipacion", "Participacion"),
            ("EstadoRegistro", "Registro"),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioRegistro", "Usuario registro"),
            ("FechaRegistro", "Fecha registro", "datetime"),
            ("UsuarioModifica", "Usuario modifica"),
            ("FechaModifica", "Fecha modifica", "datetime"),
        ),
        "editable_fields": fields(
            ("FechaInicioEstudiante", "Fecha inicio", "date"),
            ("EstadoParticipacion", "Participacion"),
            ("EstadoRegistro", "Registro"),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioModifica", "Usuario modifica"),
            ("FechaModifica", "Fecha modifica", "datetime"),
        ),
        "create_fields": fields(
            field("CorteId", "Corte", "number", required=True),
            field("CodigoEstud", "Codigo estudiante", "number", required=True),
            ("CedulaEst", "Cedula"),
            ("ApellidosNombre", "Estudiante"),
            ("Cod_AnioBasica", "Carrera", "number"),
            ("CodigoPeriodo", "Periodo", "number"),
            ("CodigoMateria", "Materia", "number"),
            ("Num_Matricula", "Matricula", "number"),
            ("CodCurso", "Curso", "number"),
            ("FechaInicioEstudiante", "Fecha inicio", "date"),
            field("EstadoParticipacion", "Participacion", required=True),
            field("EstadoRegistro", "Registro", required=True),
            ("Observacion", "Observacion", "textarea"),
            ("UsuarioRegistro", "Usuario registro"),
            ("FechaRegistro", "Fecha registro", "datetime"),
        ),
        "search_fields": ["CorteEstudianteId", "CorteId", "CodigoEstud", "CedulaEst", "ApellidosNombre", "EstadoParticipacion", "EstadoRegistro"],
        "order_by": "CorteEstudianteId DESC",
        "defaults": {"FechaRegistro": "now"},
    },
    "credenciales_curso": {
        "title": "Credenciales de curso",
        "category": "Certificados",
        "description": "Usuarios, credenciales temporales y estado de creación/envío de cursos.",
        "table": "[dbo].[CREDENCIALES_CURSO]",
        "key_fields": ["id"],
        "list_fields": fields(
            ("id", "Codigo", "number"),
            ("curso", "Curso"),
            ("cedula", "Cedula"),
            ("primer_apellido", "Primer apellido"),
            ("primer_nombre", "Primer nombre"),
            ("correo_electronico", "Correo"),
            ("estado_graph", "Graph"),
            ("estado_envio", "Envio"),
        ),
        "detail_fields": fields(
            ("id", "Codigo", "number"),
            ("cod_curso", "Codigo curso"),
            ("curso", "Curso"),
            ("primer_nombre", "Primer nombre"),
            ("segundo_nombre", "Segundo nombre"),
            ("primer_apellido", "Primer apellido"),
            ("segundo_apellido", "Segundo apellido"),
            ("cedula", "Cedula"),
            ("correo_electronico", "Correo"),
            ("usuario_generado", "Usuario generado"),
            ("clave_temporal", "Clave temporal"),
            ("graph_user_id", "Graph user id"),
            ("graph_user_principal_name", "Graph UPN"),
            ("graph_mail_sender", "Remitente"),
            ("estado_graph", "Estado Graph"),
            ("error_graph", "Error Graph", "textarea"),
            ("link_induccion", "Link induccion"),
            ("correo_enviado", "Correo enviado", "bool"),
            ("estado_envio", "Estado envio"),
            ("error_envio", "Error envio", "textarea"),
            ("fecha_creacion", "Fecha creacion", "datetime"),
            ("usuario_creacion", "Usuario creacion"),
            ("fecha_graph", "Fecha Graph", "datetime"),
            ("fecha_envio", "Fecha envio", "datetime"),
            ("fecha_actualizacion", "Fecha actualizacion", "datetime"),
        ),
        "editable_fields": fields(
            ("estado_graph", "Estado Graph"),
            ("error_graph", "Error Graph", "textarea"),
            ("correo_enviado", "Correo enviado", "bool"),
            ("estado_envio", "Estado envio"),
            ("error_envio", "Error envio", "textarea"),
            ("fecha_graph", "Fecha Graph", "datetime"),
            ("fecha_envio", "Fecha envio", "datetime"),
            ("fecha_actualizacion", "Fecha actualizacion", "datetime"),
        ),
        "search_fields": ["id", "cod_curso", "curso", "cedula", "primer_nombre", "primer_apellido", "correo_electronico", "usuario_generado", "estado_graph", "estado_envio"],
        "order_by": "fecha_creacion DESC, id DESC",
    },
    "talento_humano_empleados": {
        "title": "Empleados",
        "category": "Talento humano",
        "description": "Ficha base de empleados usada por el modulo RRHH de SisAcademicoV1.",
        "table": "[dbo].[TH_EMPLEADO]",
        "key_fields": ["empleado_id"],
        "list_fields": fields(
            ("empleado_id", "Codigo", "number"),
            ("usuario_id", "Usuario", "number"),
            ("nombres", "Nombres"),
            ("cargo", "Cargo"),
            ("tipo_personal", "Tipo"),
            ("estado", "Estado"),
        ),
        "detail_fields": fields(
            ("empleado_id", "Codigo", "number"),
            ("usuario_id", "Usuario", "number"),
            ("nombres", "Nombres"),
            ("cargo", "Cargo"),
            ("tipo_personal", "Tipo personal"),
            ("estado", "Estado"),
            ("fecha_ingreso", "Fecha ingreso", "date"),
        ),
        "editable_fields": fields(
            ("usuario_id", "Usuario", "number"),
            ("nombres", "Nombres"),
            ("cargo", "Cargo"),
            ("tipo_personal", "Tipo personal"),
            ("estado", "Estado"),
            ("fecha_ingreso", "Fecha ingreso", "date"),
        ),
        "create_fields": fields(
            field("usuario_id", "Usuario", "number", required=True),
            field("nombres", "Nombres", required=True),
            ("cargo", "Cargo"),
            field("tipo_personal", "Tipo personal", required=True),
            field("estado", "Estado", required=True),
            field("fecha_ingreso", "Fecha ingreso", "date", required=True),
        ),
        "search_fields": ["empleado_id", "usuario_id", "nombres", "cargo", "tipo_personal", "estado"],
        "order_by": "nombres",
    },
    "talento_humano_solicitudes": {
        "title": "Solicitudes RRHH",
        "category": "Talento humano",
        "description": "Solicitudes de permisos, vacaciones y validaciones del flujo de talento humano.",
        "table": "[dbo].[TH_SOLICITUD]",
        "key_fields": ["solicitud_id"],
        "list_fields": fields(
            ("solicitud_id", "Codigo", "number"),
            ("cedula", "Cedula"),
            ("correo_institucional", "Correo"),
            ("unidad", "Unidad"),
            ("fecha_inicio", "Inicio", "date"),
            ("fecha_fin", "Fin", "date"),
            ("estado_actual", "Estado"),
        ),
        "detail_fields": fields(
            ("solicitud_id", "Codigo", "number"),
            ("empleado_id", "Empleado", "number"),
            ("tipo_id", "Tipo", "number"),
            ("fecha_inicio", "Inicio", "date"),
            ("fecha_fin", "Fin", "date"),
            ("motivo", "Motivo", "textarea"),
            ("estado_actual", "Estado"),
            ("created_by", "Creado por", "number"),
            ("created_at", "Creado", "datetime"),
            ("cedula", "Cedula"),
            ("unidad", "Unidad"),
            ("jefe_inmediato_nombre", "Jefe inmediato"),
            ("correo_institucional", "Correo"),
            ("lugar_permanencia", "Lugar permanencia"),
            ("telefono_contacto", "Telefono"),
            ("numero_dias_horas", "Dias/horas", "number"),
            ("documentos_respaldo", "Documentos", "textarea"),
            ("jefe_observaciones", "Observaciones jefe", "textarea"),
            ("th_validacion_nombre", "Validacion TH"),
            ("th_validacion_fecha", "Fecha validacion", "datetime"),
            ("th_validacion_observaciones", "Observaciones TH", "textarea"),
            ("tipo_flags", "Flags"),
            ("jefe_firma_nombre", "Firma jefe"),
            ("jefe_firma_fecha", "Fecha firma jefe", "datetime"),
            ("th_firma_nombre", "Firma TH"),
            ("th_firma_fecha", "Fecha firma TH", "datetime"),
        ),
        "editable_fields": fields(
            ("estado_actual", "Estado"),
            ("jefe_observaciones", "Observaciones jefe", "textarea"),
            ("th_validacion_nombre", "Validacion TH"),
            ("th_validacion_fecha", "Fecha validacion", "datetime"),
            ("th_validacion_observaciones", "Observaciones TH", "textarea"),
            ("jefe_firma_nombre", "Firma jefe"),
            ("jefe_firma_fecha", "Fecha firma jefe", "datetime"),
            ("th_firma_nombre", "Firma TH"),
            ("th_firma_fecha", "Fecha firma TH", "datetime"),
        ),
        "search_fields": ["solicitud_id", "empleado_id", "cedula", "unidad", "jefe_inmediato_nombre", "correo_institucional", "estado_actual", "motivo"],
        "order_by": "created_at DESC, solicitud_id DESC",
    },
    "talento_humano_tareas": {
        "title": "Tareas RRHH",
        "category": "Talento humano",
        "description": "Tareas, delegaciones, prioridades y seguimiento interno de RRHH.",
        "table": "[dbo].[TH_TAREA]",
        "key_fields": ["tarea_id"],
        "list_fields": fields(
            ("tarea_id", "Codigo", "number"),
            ("titulo", "Titulo"),
            ("estado", "Estado"),
            ("prioridad", "Prioridad"),
            ("asignado_usuario_id", "Usuario asignado", "number"),
            ("fecha_limite", "Limite", "date"),
            ("created_at", "Creado", "datetime"),
        ),
        "detail_fields": fields(
            ("tarea_id", "Codigo", "number"),
            ("titulo", "Titulo"),
            ("descripcion", "Descripcion", "textarea"),
            ("created_by", "Creado por", "number"),
            ("asignado_usuario_id", "Usuario asignado", "number"),
            ("asignado_empleado_id", "Empleado asignado", "number"),
            ("area_tipo_personal", "Area/tipo personal"),
            ("estado", "Estado"),
            ("prioridad", "Prioridad"),
            ("requiere_ayuda", "Requiere ayuda", "bool"),
            ("delegada_a_empleado_id", "Delegada a empleado", "number"),
            ("delegada_por_usuario_id", "Delegada por usuario", "number"),
            ("delegada_at", "Fecha delegacion", "datetime"),
            ("fecha_limite", "Fecha limite", "date"),
            ("created_at", "Creado", "datetime"),
            ("updated_at", "Actualizado", "datetime"),
            ("closed_at", "Cerrado", "datetime"),
        ),
        "editable_fields": fields(
            ("titulo", "Titulo"),
            ("descripcion", "Descripcion", "textarea"),
            ("asignado_usuario_id", "Usuario asignado", "number"),
            ("asignado_empleado_id", "Empleado asignado", "number"),
            ("area_tipo_personal", "Area/tipo personal"),
            ("estado", "Estado"),
            ("prioridad", "Prioridad"),
            ("requiere_ayuda", "Requiere ayuda", "bool"),
            ("delegada_a_empleado_id", "Delegada a empleado", "number"),
            ("delegada_por_usuario_id", "Delegada por usuario", "number"),
            ("delegada_at", "Fecha delegacion", "datetime"),
            ("fecha_limite", "Fecha limite", "date"),
            ("updated_at", "Actualizado", "datetime"),
            ("closed_at", "Cerrado", "datetime"),
        ),
        "search_fields": ["tarea_id", "titulo", "descripcion", "estado", "prioridad", "area_tipo_personal"],
        "order_by": "created_at DESC, tarea_id DESC",
    },
    "moodle_notas": {
        "title": "Notas Moodle",
        "category": "Integraciones",
        "description": "Notas sincronizadas desde Moodle por estudiante, materia y componente.",
        "table": "[dbo].[intec_estudiantenota]",
        "key_fields": ["id"],
        "list_fields": fields(
            ("id", "Codigo", "number"),
            ("codigo_estudiante", "Estudiante"),
            ("periodo", "Periodo"),
            ("codigo_materia", "Materia"),
            ("componente_nota", "Componente"),
            ("nota_obtenida", "Nota", "decimal"),
            ("estado", "Estado"),
        ),
        "detail_fields": fields(
            ("id", "Codigo", "number"),
            ("codigo_estudiante", "Estudiante"),
            ("periodo", "Periodo"),
            ("codigo_materia", "Materia"),
            ("paralelo", "Paralelo"),
            ("tipo_matricula", "Tipo matricula"),
            ("componente_nota", "Componente"),
            ("nota_obtenida", "Nota", "decimal"),
            ("nota_maxima", "Nota maxima", "decimal"),
            ("porcentaje", "Porcentaje", "decimal"),
            ("estado", "Estado"),
            ("moodle_course_id", "Moodle course", "number"),
            ("moodle_grade_item_id", "Moodle item", "number"),
            ("fecha_calificacion", "Fecha calificacion", "datetime"),
            ("fecha_sincronizacion", "Fecha sincronizacion", "datetime"),
            ("fecha_creacion", "Fecha creacion", "datetime"),
            ("comentario_profesor", "Comentario", "textarea"),
            ("calificado_por", "Calificado por"),
        ),
        "editable_fields": fields(
            ("nota_obtenida", "Nota", "decimal"),
            ("estado", "Estado"),
            ("comentario_profesor", "Comentario", "textarea"),
            ("calificado_por", "Calificado por"),
        ),
        "search_fields": ["codigo_estudiante", "periodo", "codigo_materia", "paralelo", "tipo_matricula", "componente_nota", "estado", "calificado_por"],
        "order_by": "fecha_sincronizacion DESC, id DESC",
    },
    "moodle_sincronizacion": {
        "title": "Sincronización Moodle",
        "category": "Integraciones",
        "description": "Historial de sincronización de notas desde Moodle.",
        "table": "[dbo].[intec_moodlegradesynclog]",
        "key_fields": ["id"],
        "list_fields": fields(
            ("id", "Codigo", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("periodo", "Periodo"),
            ("modo_ejecucion", "Modo"),
            ("estado", "Estado"),
            ("notas_procesadas", "Procesadas", "number"),
            ("notas_error", "Errores", "number"),
        ),
        "detail_fields": fields(
            ("id", "Codigo", "number"),
            ("fecha_inicio", "Inicio", "datetime"),
            ("fecha_fin", "Fin", "datetime"),
            ("duracion_segundos", "Duracion", "decimal"),
            ("periodo", "Periodo"),
            ("modo_ejecucion", "Modo"),
            ("estado", "Estado"),
            ("notas_procesadas", "Procesadas", "number"),
            ("notas_actualizadas", "Actualizadas", "number"),
            ("notas_insertadas", "Insertadas", "number"),
            ("notas_error", "Errores", "number"),
            ("mensaje", "Mensaje", "textarea"),
            ("errores_detalle", "Errores detalle", "textarea"),
            ("estadisticas", "Estadisticas", "textarea"),
            ("usuario_id", "Usuario", "number"),
        ),
        "editable_fields": fields(
            ("mensaje", "Mensaje", "textarea"),
            ("errores_detalle", "Errores detalle", "textarea"),
            ("estadisticas", "Estadisticas", "textarea"),
        ),
        "search_fields": ["id", "periodo", "modo_ejecucion", "estado", "mensaje", "errores_detalle"],
        "order_by": "fecha_inicio DESC, id DESC",
    },
    "microsoft365_audit": {
        "title": "Auditoría Microsoft 365",
        "category": "Integraciones",
        "description": "Acciones, estados y errores de operaciones Microsoft 365.",
        "table": "[dbo].[Microsoft365Audit]",
        "key_fields": ["Id"],
        "list_fields": fields(
            ("Id", "Codigo", "number"),
            ("correo", "Correo"),
            ("fecha", "Fecha", "datetime"),
            ("accion", "Accion"),
            ("estado", "Estado"),
            ("skuIdAsignado", "SKU"),
        ),
        "detail_fields": fields(
            ("Id", "Codigo", "number"),
            ("correo", "Correo"),
            ("fecha", "Fecha", "datetime"),
            ("accion", "Accion"),
            ("estado", "Estado"),
            ("skuIdAsignado", "SKU"),
            ("mensaje_error", "Error", "textarea"),
        ),
        "editable_fields": fields(
            ("estado", "Estado"),
            ("mensaje_error", "Error", "textarea"),
        ),
        "search_fields": ["correo", "accion", "estado", "skuIdAsignado", "mensaje_error"],
        "order_by": "fecha DESC, Id DESC",
    },
}


LOOKUP_QUERIES: dict[str, dict[str, list[str]]] = {
    "usuarios": {
        "tipousuario": [
            """
            SELECT
                TRY_CONVERT(nvarchar(100), Codigo_tipo_us) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Codigo_tipo_us), N' - ', LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), detalle_tipo_us)))) AS option_label
            FROM dbo.TIPO_USUARIO
            WHERE Codigo_tipo_us IS NOT NULL
            ORDER BY TRY_CONVERT(int, Codigo_tipo_us), detalle_tipo_us
            """,
        ],
        "tp_us": [
            """
            SELECT
                TRY_CONVERT(nvarchar(100), Codigo_tipo_us) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Codigo_tipo_us), N' - ', LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), detalle_tipo_us)))) AS option_label
            FROM dbo.TIPO_USUARIO
            WHERE Codigo_tipo_us IS NOT NULL
            ORDER BY TRY_CONVERT(int, Codigo_tipo_us), detalle_tipo_us
            """,
        ],
        "codprovincia": [
            """
            SELECT
                TRY_CONVERT(nvarchar(100), TRY_CONVERT(int, Cod_Provincia)) AS option_value,
                CONCAT(
                    TRY_CONVERT(nvarchar(100), TRY_CONVERT(int, Cod_Provincia)),
                    N' - ',
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), Descripcion_Prov)))
                ) AS option_label
            FROM dbo.Provincias
            WHERE Cod_Provincia IS NOT NULL
            ORDER BY Descripcion_Prov
            """,
        ],
    },
    "preinscripciones": {
        "codasesor": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), id_usuarios) AS option_value,
                COALESCE(
                    NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), nombres))), N''),
                    CONCAT(N'Asesor ', TRY_CONVERT(nvarchar(100), id_usuarios))
                ) AS option_label
            FROM dbo.USUARIO_SIS
            WHERE id_usuarios IS NOT NULL
            ORDER BY nombres, id_usuarios
            """,
        ],
    },
    "materias": {
        "Cod_AnioBasica": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), Cod_AnioBasica) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_AnioBasica), N' - ', LTRIM(RTRIM(Nombre_Basica))) AS option_label
            FROM dbo.CARRERAS
            WHERE Cod_AnioBasica IS NOT NULL
            ORDER BY Nombre_Basica
            """,
        ],
        "Semestre": [
            """
            SELECT N'1' AS option_value, N'1' AS option_label
            UNION ALL
            SELECT N'2', N'2'
            UNION ALL
            SELECT N'3', N'3'
            UNION ALL
            SELECT N'4', N'4'
            """,
        ],
        "NumMalla": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), Malla) AS option_value,
                CONCAT(
                    TRY_CONVERT(nvarchar(100), Malla),
                    N' - ',
                    COALESCE(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), Nombre))), N'Malla')
                ) AS option_label
            FROM dbo.MALLA
            WHERE Malla IS NOT NULL
            ORDER BY Malla
            """,
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), Malla) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Malla), N' - Malla') AS option_label
            FROM dbo.MALLA_PENSUM
            WHERE Malla IS NOT NULL
            GROUP BY Malla
            ORDER BY Malla
            """,
        ],
        "estado_mat": [
            """
            SELECT DISTINCT TOP (100)
                LTRIM(RTRIM(estado_mat)) AS option_value,
                LTRIM(RTRIM(estado_mat)) AS option_label
            FROM dbo.PENSUM
            WHERE NULLIF(LTRIM(RTRIM(estado_mat)), N'') IS NOT NULL
            ORDER BY option_label
            """,
        ],
    },
    "periodos": {
        "Estado": [
            """
            SELECT N'A' AS option_value, N'A - Activo' AS option_label
            UNION ALL
            SELECT N'P', N'P - Pendiente'
            UNION ALL
            SELECT N'I', N'I - Inactivo'
            """,
        ],
        "ControlPlataforma": [
            """
            SELECT N'A' AS option_value, N'A - Abierto'
            UNION ALL
            SELECT N'P', N'P - Pendiente'
            UNION ALL
            SELECT N'C', N'C - Cerrado'
            """,
        ],
        "TipoMatricula": [
            """
            SELECT N'R' AS option_value, N'R - Regular'
            UNION ALL
            SELECT N'H', N'H - Homologacion'
            UNION ALL
            SELECT N'E', N'E - Educacion continua'
            """,
        ],
        "estado_ed": [
            """
            SELECT N'Activo' AS option_value, N'Activo' AS option_label
            UNION ALL
            SELECT N'Inactivo', N'Inactivo'
            """,
        ],
    },
    "actualizacion_estudiantes": {
        "Estado": [
            """
            SELECT TOP (100)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))) AS option_value,
                CONCAT(
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))),
                    N' - ',
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), ESTADO)))
                ) AS option_label
            FROM dbo.ESTADO
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))), N'') IS NOT NULL
            ORDER BY
                CASE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))))
                    WHEN 'A' THEN 1
                    WHEN 'P' THEN 2
                    WHEN 'I' THEN 3
                    ELSE 10
                END,
                TRY_CONVERT(nvarchar(255), ESTADO)
            """,
        ],
    },
    "actualizacion_est": {
        "Estado": [
            """
            SELECT TOP (100)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))) AS option_value,
                CONCAT(
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))),
                    N' - ',
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), ESTADO)))
                ) AS option_label
            FROM dbo.ESTADO
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))), N'') IS NOT NULL
              AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) IN (N'A', N'P')
            ORDER BY
                CASE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))))
                    WHEN 'A' THEN 1
                    WHEN 'P' THEN 2
                    ELSE 10
                END,
                TRY_CONVERT(nvarchar(255), ESTADO)
            """,
        ],
    },
    "estudiantes": {
        "codprov": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), TRY_CONVERT(int, Cod_Provincia)) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), TRY_CONVERT(int, Cod_Provincia)), N' - ', LTRIM(RTRIM(Descripcion_Prov))) AS option_label
            FROM dbo.Provincias
            WHERE NULLIF(LTRIM(RTRIM(Descripcion_Prov)), N'') IS NOT NULL
            ORDER BY Descripcion_Prov
            """,
        ],
        "Canton": [
            """
            SELECT TOP (500)
                LTRIM(RTRIM(nombre_canton)) AS option_value,
                LTRIM(RTRIM(nombre_canton)) AS option_label
            FROM dbo.Canton
            WHERE NULLIF(LTRIM(RTRIM(nombre_canton)), N'') IS NOT NULL
            ORDER BY nombre_canton
            """,
        ],
        "EstadoCivil": [
            """
            SELECT TOP (100)
                TRY_CONVERT(nvarchar(100), codigo_estado_civil) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_estado_civil), N' - ', LTRIM(RTRIM(nombre_estado_civil))) AS option_label
            FROM dbo.EstadoCivil
            WHERE activo = 1 OR activo IS NULL
            ORDER BY codigo_estado_civil
            """,
        ],
        "Sexo": [
            """
            SELECT TOP (100)
                TRY_CONVERT(nvarchar(100), id_sexo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), id_sexo), N' - ', LTRIM(RTRIM(detalle_sexo))) AS option_label
            FROM dbo.Sexo
            ORDER BY id_sexo
            """,
        ],
        "Estado": [
            """
            SELECT TOP (100)
                LTRIM(RTRIM(IDESTADO)) AS option_value,
                CONCAT(LTRIM(RTRIM(IDESTADO)), N' - ', LTRIM(RTRIM(ESTADO))) AS option_label
            FROM dbo.ESTADO
            ORDER BY IDESTADO
            """,
        ],
        "Nacionalidad": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), codigo_nacionalidad) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_nacionalidad), N' - ', LTRIM(RTRIM(nombre_nacionalidad))) AS option_label
            FROM dbo.Nacionalidad
            WHERE NULLIF(LTRIM(RTRIM(nombre_nacionalidad)), N'') IS NOT NULL
            ORDER BY nombre_nacionalidad
            """,
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), Cod_Pais) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_Pais), N' - ', LTRIM(RTRIM(Descripcion_Pais))) AS option_label
            FROM dbo.Pais
            WHERE NULLIF(LTRIM(RTRIM(Descripcion_Pais)), N'') IS NOT NULL
            ORDER BY Descripcion_Pais
            """,
            """
            SELECT TOP (300)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Nacionalidad))) AS option_value,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Nacionalidad))) AS option_label
            FROM dbo.DATOS_ESTUD
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Nacionalidad))), N'') IS NOT NULL
            GROUP BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Nacionalidad)))
            ORDER BY option_label
            """,
        ],
        "tiposangre": [
            """
            SELECT TOP (100)
                TRY_CONVERT(nvarchar(100), codigo_tipo_sangre) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_tipo_sangre), N' - ', LTRIM(RTRIM(nombre_tipo_sangre))) AS option_label
            FROM dbo.TipoSangre
            WHERE NULLIF(LTRIM(RTRIM(nombre_tipo_sangre)), N'') IS NOT NULL
            ORDER BY nombre_tipo_sangre
            """,
            """
            SELECT TOP (100)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), tiposangre))) AS option_value,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), tiposangre))) AS option_label
            FROM dbo.DATOS_ESTUD
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), tiposangre))), N'') IS NOT NULL
            GROUP BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), tiposangre)))
            ORDER BY option_label
            """,
        ],
        "Ocupacion": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), codigo_ocupacion) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_ocupacion), N' - ', LTRIM(RTRIM(nombre_ocupacion))) AS option_label
            FROM dbo.Ocupacion
            WHERE NULLIF(LTRIM(RTRIM(nombre_ocupacion)), N'') IS NOT NULL
            ORDER BY nombre_ocupacion
            """,
            """
            SELECT TOP (300)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Ocupacion))) AS option_value,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Ocupacion))) AS option_label
            FROM dbo.DATOS_ESTUD
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Ocupacion))), N'') IS NOT NULL
            GROUP BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Ocupacion)))
            ORDER BY option_label
            """,
        ],
        "empresa": [
            """
            SELECT TOP (300)
                LTRIM(RTRIM(Empresa)) AS option_value,
                LTRIM(RTRIM(Empresa)) AS option_label
            FROM dbo.EMPRESA
            WHERE NULLIF(LTRIM(RTRIM(Empresa)), N'') IS NOT NULL
            ORDER BY Empresa
            """,
            """
            SELECT TOP (300)
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), empresa))) AS option_value,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), empresa))) AS option_label
            FROM dbo.DATOS_ESTUD
            WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), empresa))), N'') IS NOT NULL
            GROUP BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), empresa)))
            ORDER BY option_label
            """,
        ],
        "discapacidad": [
            """
            SELECT TOP (100)
                TRY_CONVERT(nvarchar(100), codigo_discapacidad) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_discapacidad), N' - ', LTRIM(RTRIM(nombre_discapacidad))) AS option_label
            FROM dbo.Discapacidad
            WHERE activo = 1 OR activo IS NULL
            ORDER BY nombre_discapacidad
            """,
        ],
    },
    "materia_homo_textof": {
        "cod_materia": [
            """
            WITH materias_unicas AS (
                SELECT
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))) AS option_value,
                    CONCAT(
                        LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))),
                        N' - ',
                        LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), p.Nomb_Materia))),
                        N' (codigo interno ',
                        TRY_CONVERT(nvarchar(100), p.codigo_materia),
                        N' · carrera ',
                        COALESCE(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), c.Nombre_Basica))), TRY_CONVERT(nvarchar(100), p.Cod_AnioBasica)),
                        N')'
                    ) AS option_label,
                    ROW_NUMBER() OVER (
                        PARTITION BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia)))
                        ORDER BY LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), p.Nomb_Materia))), TRY_CONVERT(int, p.codigo_materia)
                    ) AS rn
                FROM dbo.PENSUM p
                LEFT JOIN dbo.CARRERAS c
                  ON TRY_CONVERT(int, c.Cod_AnioBasica) = TRY_CONVERT(int, p.Cod_AnioBasica)
                WHERE NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), p.cod_materia))), N'') IS NOT NULL
            )
            SELECT TOP (1000) option_value, option_label
            FROM materias_unicas
            WHERE rn = 1
            ORDER BY option_label
            """,
        ],
        "cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(
                    TRY_CONVERT(nvarchar(100), cod_periodo),
                    N' - ',
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), Detalle_Periodo)))
                ) AS option_label
            FROM dbo.PERIODO
            WHERE cod_periodo IS NOT NULL
              AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(30), TipoMatricula)))) = N'H'
            ORDER BY cod_periodo DESC
            """,
        ],
    },
    "datos_factura": {
        "CODESTUD": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_estud) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_estud), N' - ', LTRIM(RTRIM(Apellidos_nombre)), N' - ', LTRIM(RTRIM(Cedula_Est))) AS option_label
            FROM dbo.DATOS_ESTUD
            ORDER BY Apellidos_nombre
            """,
        ],
    },
    "fechas_notas": {
        "periodo_acad": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
    },
    "fechas_autoevaluacion": {
        "periodo_acad": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
    },
    "evaluacion_resultados": {
        "Cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "Cod_Materia": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_materia) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_materia), N' - ', LTRIM(RTRIM(Nomb_Materia))) AS option_label
            FROM dbo.PENSUM
            ORDER BY Nomb_Materia
            """,
        ],
        "Cod_Doc_Eval": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_doc) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_doc), N' - ', LTRIM(RTRIM(apellidos_nombre))) AS option_label
            FROM dbo.DATOSDOCENTE
            ORDER BY apellidos_nombre
            """,
        ],
    },
    "asistencia_estudiantes": {
        "codigo_estud": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_estud) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_estud), N' - ', LTRIM(RTRIM(Apellidos_nombre)), N' - ', LTRIM(RTRIM(Cedula_Est))) AS option_label
            FROM dbo.DATOS_ESTUD
            ORDER BY Apellidos_nombre
            """,
        ],
        "cod_anio_Basica": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), Cod_AnioBasica) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_AnioBasica), N' - ', LTRIM(RTRIM(Nombre_Basica))) AS option_label
            FROM dbo.CARRERAS
            ORDER BY Nombre_Basica
            """,
        ],
        "codigo_materia": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_materia) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_materia), N' - ', LTRIM(RTRIM(Nomb_Materia))) AS option_label
            FROM dbo.PENSUM
            ORDER BY Nomb_Materia
            """,
        ],
        "codigo_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "paralelo": [
            """
            SELECT TOP (200)
                LTRIM(RTRIM(paralelo)) AS option_value,
                LTRIM(RTRIM(paralelo)) AS option_label
            FROM dbo.PARALELOS
            ORDER BY paralelo
            """,
        ],
    },
    "provincias": {
        "Cod_Pais": [
            """
            SELECT DISTINCT TOP (100)
                LTRIM(RTRIM(Cod_Pais)) AS option_value,
                LTRIM(RTRIM(Cod_Pais)) AS option_label
            FROM dbo.Provincias
            WHERE NULLIF(LTRIM(RTRIM(Cod_Pais)), N'') IS NOT NULL
            ORDER BY Cod_Pais
            """,
        ],
    },
    "repositorio": {
        "codcarrera": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), Cod_AnioBasica) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_AnioBasica), N' - ', LTRIM(RTRIM(Nombre_Basica))) AS option_label
            FROM dbo.CARRERAS
            ORDER BY Nombre_Basica
            """,
        ],
    },
    "registro_documentos_estudiante": {
        "IDESTUD": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_estud) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_estud), N' - ', LTRIM(RTRIM(Apellidos_nombre)), N' - ', LTRIM(RTRIM(Cedula_Est))) AS option_label
            FROM dbo.DATOS_ESTUD
            ORDER BY Apellidos_nombre
            """,
        ],
    },
    "numero_preguntas": {
        "Cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "Cod_Materia": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_materia) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_materia), N' - ', LTRIM(RTRIM(Nomb_Materia))) AS option_label
            FROM dbo.PENSUM
            ORDER BY Nomb_Materia
            """,
        ],
    },
    "cuestionarios": {
        "cod_doc": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_doc) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_doc), N' - ', LTRIM(RTRIM(apellidos_nombre))) AS option_label
            FROM dbo.DATOSDOCENTE
            ORDER BY apellidos_nombre
            """,
        ],
        "cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "cod_materia": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_materia) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_materia), N' - ', LTRIM(RTRIM(Nomb_Materia))) AS option_label
            FROM dbo.PENSUM
            ORDER BY Nomb_Materia
            """,
        ],
    },
    "planes_foros": {
        "cod_doc": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_doc) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_doc), N' - ', LTRIM(RTRIM(apellidos_nombre))) AS option_label
            FROM dbo.DATOSDOCENTE
            ORDER BY apellidos_nombre
            """,
        ],
        "cod_materia": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_materia) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_materia), N' - ', LTRIM(RTRIM(Nomb_Materia))) AS option_label
            FROM dbo.PENSUM
            ORDER BY Nomb_Materia
            """,
        ],
        "cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
    },
    "autoevaluacion_resultados": {
        "Cod_Docente": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_doc) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_doc), N' - ', LTRIM(RTRIM(apellidos_nombre))) AS option_label
            FROM dbo.DATOSDOCENTE
            ORDER BY apellidos_nombre
            """,
        ],
        "Cod_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "Cod_Carrera": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), Cod_AnioBasica) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_AnioBasica), N' - ', LTRIM(RTRIM(Nombre_Basica))) AS option_label
            FROM dbo.CARRERAS
            ORDER BY Nombre_Basica
            """,
        ],
    },
    "practicas_vinculacion": {
        "codigo_estud": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_estud) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_estud), N' - ', LTRIM(RTRIM(Apellidos_nombre)), N' - ', LTRIM(RTRIM(Cedula_Est))) AS option_label
            FROM dbo.DATOS_ESTUD
            ORDER BY Apellidos_nombre
            """,
        ],
        "cod_anio_Basica": [
            """
            SELECT TOP (300)
                TRY_CONVERT(nvarchar(100), Cod_AnioBasica) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Cod_AnioBasica), N' - ', LTRIM(RTRIM(Nombre_Basica))) AS option_label
            FROM dbo.CARRERAS
            ORDER BY Nombre_Basica
            """,
        ],
        "codigo_periodo": [
            """
            SELECT TOP (500)
                TRY_CONVERT(nvarchar(100), cod_periodo) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), cod_periodo), N' - ', LTRIM(RTRIM(Detalle_Periodo))) AS option_label
            FROM dbo.PERIODO
            ORDER BY cod_periodo DESC
            """,
        ],
        "Cod_empresa": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), Num_emp) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), Num_emp), N' - ', LTRIM(RTRIM(Empresa))) AS option_label
            FROM dbo.EMPRESA
            ORDER BY Empresa
            """,
        ],
        "CodDocente": [
            """
            SELECT TOP (1000)
                TRY_CONVERT(nvarchar(100), codigo_doc) AS option_value,
                CONCAT(TRY_CONVERT(nvarchar(100), codigo_doc), N' - ', LTRIM(RTRIM(apellidos_nombre))) AS option_label
            FROM dbo.DATOSDOCENTE
            ORDER BY apellidos_nombre
            """,
        ],
    },
}


def _section(key: str) -> dict[str, Any]:
    section = SECTIONS.get(key)
    if not section:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seccion no disponible")
    return section


def _column_names(items: list[FieldMeta]) -> list[str]:
    seen: set[str] = set()
    columns: list[str] = []
    for item in items:
        if item.name not in seen:
            seen.add(item.name)
            columns.append(item.name)
    return columns


def _all_read_columns(section: dict[str, Any]) -> list[str]:
    names = list(section["key_fields"])
    for name in _column_names(section["detail_fields"]):
        if name not in names:
            names.append(name)
    return names


def _selectable_columns(columns: list[str]) -> list[str]:
    return [column for column in columns if column not in STUDENT_IDENTITY_FIELDS]


def _student_lookup_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        numeric = Decimal(text)
        if numeric == numeric.to_integral_value():
            return str(int(numeric))
    except Exception:
        return text
    return text


def _optional_int_filter(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(Decimal(text))
    except Exception:
        return None


def _quote_column(column: str) -> str:
    if column not in {meta.name for config in SECTIONS.values() for group in ("list_fields", "detail_fields", "editable_fields", "create_fields") for meta in config.get(group, [])} and not any(column in config["key_fields"] or column in config.get("search_fields", []) for config in SECTIONS.values()):
        raise ValueError("Columna no permitida")
    return f"[{column}]"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return None
    return value


def _rows_from_cursor(cursor: Any, section_key: str, key_fields: list[str]) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    rows: list[dict[str, Any]] = []
    for record in cursor.fetchall():
        row = {column: _serialize_value(value) for column, value in zip(columns, record)}
        row["_section"] = section_key
        row["_record_key"] = _encode_key([row.get(field_name) for field_name in key_fields])
        rows.append(row)
    return rows


def _actualizacion_estudiante_row(row: Any) -> dict[str, Any]:
    record = {
        "codigo_estud": _serialize_value(getattr(row, "codigo_estud", "")),
        "Cedula_Est": _serialize_value(getattr(row, "Cedula_Est", "")),
        "Apellidos_nombre": _serialize_value(getattr(row, "Apellidos_nombre", "")),
        "codigo_periodo": _serialize_value(getattr(row, "codigo_periodo", "")),
        "Estado": _serialize_value(getattr(row, "Estado", "")),
        "estado_nombre": _serialize_value(getattr(row, "estado_nombre", "")) or _serialize_value(getattr(row, "Estado", "")),
        "Informacion": _serialize_value(getattr(row, "Informacion", "")),
        "DocumentoEstado": _serialize_value(getattr(row, "DocumentoEstado", "")),
        "correo": _serialize_value(getattr(row, "correo", "")),
        "correointec": _serialize_value(getattr(row, "correointec", "")),
        "telefono": _serialize_value(getattr(row, "telefono", "")),
        "movil": _serialize_value(getattr(row, "movil", "")),
        "ciudad": _serialize_value(getattr(row, "ciudad", "")),
        "Nacionalidad": _serialize_value(getattr(row, "Nacionalidad", "")),
        "total_matriculas": _serialize_value(getattr(row, "total_matriculas", 0)) or 0,
        "total_materias": _serialize_value(getattr(row, "total_materias", 0)) or 0,
        "ultimo_periodo": _serialize_value(getattr(row, "ultimo_periodo", None)),
    }
    record["_section"] = "actualizacion_estudiantes"
    record["_record_key"] = _encode_key([record["Cedula_Est"]])
    return record


def _actualizacion_estudiante_select(limit: int | None, where_sql: str = "", periodo: int | None = None) -> str:
    top_clause = f"TOP ({limit}) " if limit else ""
    periodo_value = str(periodo) if periodo else "stats.ultimo_periodo"
    return f"""
        SELECT {top_clause}
            TRY_CONVERT(varchar(50), d.codigo_estud) AS codigo_estud,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.Cedula_Est))) AS Cedula_Est,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre))) AS Apellidos_nombre,
            TRY_CONVERT(varchar(50), {periodo_value}) AS codigo_periodo,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.Estado))) AS Estado,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), est.ESTADO))) AS estado_nombre,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(1000), state_document.DETALLE))) AS Informacion,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(1000), state_document.LINKURL))) AS DocumentoEstado,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correo))) AS correo,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correointec))) AS correointec,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.telefono))) AS telefono,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.movil))) AS movil,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.ciudad))) AS ciudad,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.Nacionalidad))) AS Nacionalidad,
            stats.total_matriculas,
            stats.total_materias,
            stats.ultimo_periodo
        FROM dbo.DATOS_ESTUD d
        LEFT JOIN dbo.ESTADO est
          ON UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), est.IDESTADO)))) =
             UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.Estado))))
        OUTER APPLY (
            SELECT
                COUNT(DISTINCT TRY_CONVERT(int, cm.codigo_periodo)) AS total_matriculas,
                COUNT(*) AS total_materias,
                MAX(TRY_CONVERT(int, cm.codigo_periodo)) AS ultimo_periodo
            FROM dbo.CARRERAXESTUD cm
            WHERE TRY_CONVERT(decimal(18, 0), cm.codigo_estud) = TRY_CONVERT(decimal(18, 0), d.codigo_estud)
        ) stats
        OUTER APPLY (
            SELECT TOP (1)
                rd.DETALLE,
                rd.LINKURL
            FROM dbo.REGISTRODOCESTUD rd
            WHERE TRY_CONVERT(decimal(18, 0), rd.IDESTUD) = TRY_CONVERT(decimal(18, 0), d.codigo_estud)
              AND TRY_CONVERT(nvarchar(1000), rd.DETALLE) LIKE N'[[]CAMBIO DE ESTADO]%'
            ORDER BY TRY_CONVERT(bigint, rd.num) DESC
        ) state_document
        {where_sql}
        ORDER BY
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre))),
            TRY_CONVERT(int, d.codigo_estud)
    """


def _list_actualizacion_estudiantes_records(section: dict[str, Any], query: str | None, limit: int | None, periodo: str | None = None) -> dict[str, Any]:
    cleaned_query = str(query or "").strip()
    periodo_codigo = _optional_int_filter(periodo)
    params: list[Any] = []
    where_parts: list[str] = []
    if cleaned_query:
        like = f"%{cleaned_query}%"
        where_parts.append(
            """
        (
               TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre) LIKE ?
            OR TRY_CONVERT(nvarchar(100), d.Cedula_Est) LIKE ?
            OR TRY_CONVERT(nvarchar(255), d.correo) LIKE ?
            OR TRY_CONVERT(nvarchar(255), d.correointec) LIKE ?
            OR TRY_CONVERT(nvarchar(100), d.movil) LIKE ?
            OR TRY_CONVERT(nvarchar(100), d.Estado) LIKE ?
            OR TRY_CONVERT(nvarchar(255), est.ESTADO) LIKE ?
            OR TRY_CONVERT(varchar(50), d.codigo_estud) = ?
        )
        """
        )
        params = [like, like, like, like, like, like, like, cleaned_query]
    if periodo_codigo:
        where_parts.append(
            f"""
        EXISTS (
            SELECT 1
            FROM dbo.CARRERAXESTUD cm_periodo
            WHERE TRY_CONVERT(decimal(18, 0), cm_periodo.codigo_estud) = TRY_CONVERT(decimal(18, 0), d.codigo_estud)
              AND TRY_CONVERT(int, cm_periodo.codigo_periodo) = {periodo_codigo}
        )
        """
        )
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_actualizacion_estudiante_select(limit, where_sql, periodo_codigo), params)
            rows = [_actualizacion_estudiante_row(row) for row in cursor.fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar la actualizacion de estados de estudiantes") from exc
    return {
        "section": _section_meta("actualizacion_estudiantes", section).model_dump(),
        "rows": rows,
        "total": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_actualizacion_estudiantes_record(section: dict[str, Any], record_key: str) -> dict[str, Any]:
    key_values = _decode_key(record_key, 1)
    where_sql = "WHERE LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.Cedula_Est))) = LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), ?)))"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_actualizacion_estudiante_select(1, where_sql), key_values)
            row = cursor.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar el estado del estudiante") from exc
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estudiante no encontrado")
    return {"section": _section_meta("actualizacion_estudiantes", section).model_dump(), "record": _actualizacion_estudiante_row(row)}


def _update_actualizacion_estudiantes_record(section: dict[str, Any], record_key: str, payload: SavePayload) -> dict[str, Any]:
    del section, record_key, payload
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="El cambio de estado requiere motivo y documento de respaldo",
    )


def _actualizacion_est_row(row: Any) -> dict[str, Any]:
    usuario_validado = bool(getattr(row, "Codigo_Usuario", None))
    correo_docente = _serialize_value(getattr(row, "correo", "")) or _serialize_value(getattr(row, "correop", ""))
    record = {
        "codigo_doc": _serialize_value(getattr(row, "codigo_doc", "")),
        "Codigo_Usuario": _serialize_value(getattr(row, "Codigo_Usuario", "")),
        "cedula": _serialize_value(getattr(row, "cedula", "")),
        "cedula_doc": _serialize_value(getattr(row, "cedula_doc", "")),
        "apellidos_nombre": _serialize_value(getattr(row, "apellidos_nombre", "")),
        "login": _serialize_value(getattr(row, "login", "")),
        "tipo_usuario": _serialize_value(getattr(row, "tipo_usuario", "")),
        "fecha_ingreso_usuario": _serialize_value(getattr(row, "fecha_ingreso_usuario", "")),
        "CambioClave": _serialize_value(getattr(row, "CambioClave", "")),
        "Estado": _serialize_value(getattr(row, "Estado", "")),
        "estado_nombre": _serialize_value(getattr(row, "estado_nombre", "")) or _serialize_value(getattr(row, "Estado", "")),
        "Informacion": _serialize_value(getattr(row, "Informacion", "")),
        "correo": _serialize_value(getattr(row, "correo", "")),
        "correop": _serialize_value(getattr(row, "correop", "")),
        "correo_docente": correo_docente,
        "correo_personal": _serialize_value(getattr(row, "correop", "")) or _serialize_value(getattr(row, "correo", "")),
        "telefono": _serialize_value(getattr(row, "telefono", "")),
        "movil": _serialize_value(getattr(row, "movil", "")),
        "TipoDocente": _serialize_value(getattr(row, "TipoDocente", "")),
        "nivelFormacion": _serialize_value(getattr(row, "nivelFormacion", "")),
        "sexo": _serialize_value(getattr(row, "sexo", "")),
        "nacionalidad": _serialize_value(getattr(row, "nacionalidad", "")),
        "fecha_nac": _serialize_value(getattr(row, "fecha_nac", "")),
        "tipo_discapa": _serialize_value(getattr(row, "tipo_discapa", "")),
        "carnet_conadis": _serialize_value(getattr(row, "carnet_conadis", "")),
        "num_carnet_cona": _serialize_value(getattr(row, "num_carnet_cona", "")),
        "porcen_discapa": _serialize_value(getattr(row, "porcen_discapa", "")),
        "estado_civil": _serialize_value(getattr(row, "estado_civil", "")),
        "usuario_validado": usuario_validado,
    }
    record["_section"] = "actualizacion_est"
    record["_record_key"] = _encode_key([record["codigo_doc"], record["Codigo_Usuario"]])
    return record


def _actualizacion_est_select(limit: int | None, where_sql: str = "") -> str:
    top_clause = f"TOP ({limit}) " if limit else ""
    return f"""
        SELECT {top_clause}
            TRY_CONVERT(varchar(50), d.codigo_doc) AS codigo_doc,
            TRY_CONVERT(varchar(50), u.Codigo_Usuario) AS Codigo_Usuario,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))) AS cedula,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.cedula_doc))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))), N'')
            ) AS cedula_doc,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), u.login))), N''),
                N'Sin ficha docente'
            ) AS apellidos_nombre,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), u.login))) AS login,
            COALESCE(NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.tipo_usuario))), N''), N'DOCENTE') AS tipo_usuario,
            TRY_CONVERT(datetime, u.fecha_ingreso) AS fecha_ingreso_usuario,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.CambioClave))) AS CambioClave,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.Estado))) AS Estado,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), est.ESTADO))) AS estado_nombre,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(1000), u.Descripcion))) AS Informacion,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correo))) AS correo,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.correop))) AS correop,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.telefono))) AS telefono,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.movil))) AS movil,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.TipoDocente))) AS TipoDocente,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), d.nivelFormacion))) AS nivelFormacion,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.sexo))) AS sexo,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.nacionalidad))) AS nacionalidad,
            TRY_CONVERT(date, d.fecha_nac) AS fecha_nac,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.tipo_discapa))) AS tipo_discapa,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.carnet_conadis))) AS carnet_conadis,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.num_carnet_cona))) AS num_carnet_cona,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.porcen_discapa))) AS porcen_discapa,
            LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.estado_civil))) AS estado_civil
        FROM dbo.USUARIOS u
        FULL OUTER JOIN dbo.DATOSDOCENTE d
          ON (
                TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, d.codigo_doc)
             OR LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))) =
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.cedula_doc)))
          )
        LEFT JOIN dbo.ESTADO est
          ON UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), est.IDESTADO)))) =
             UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), u.Estado))))
        {where_sql}
        ORDER BY
            CASE WHEN u.Codigo_Usuario IS NULL THEN 1 ELSE 0 END,
            COALESCE(
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.apellidos_nombre))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), u.login))), N''),
                NULLIF(LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), u.cedula))), N'')
            ),
            TRY_CONVERT(int, u.Codigo_Usuario),
            TRY_CONVERT(int, d.codigo_doc)
    """


def _list_actualizacion_est_records(section: dict[str, Any], query: str | None, limit: int | None) -> dict[str, Any]:
    cleaned_query = str(query or "").strip()
    params: list[Any] = []
    where_parts: list[str] = ["(u.Codigo_Usuario IS NULL OR COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1)"]
    if cleaned_query:
        like = f"%{cleaned_query}%"
        where_parts.append(
            """
        (
               TRY_CONVERT(nvarchar(4000), d.apellidos_nombre) LIKE ?
            OR TRY_CONVERT(nvarchar(100), u.cedula) LIKE ?
            OR TRY_CONVERT(nvarchar(100), d.cedula_doc) LIKE ?
            OR TRY_CONVERT(nvarchar(255), d.correo) LIKE ?
            OR TRY_CONVERT(nvarchar(255), d.correop) LIKE ?
            OR TRY_CONVERT(nvarchar(255), u.login) LIKE ?
            OR TRY_CONVERT(nvarchar(100), u.Estado) LIKE ?
            OR TRY_CONVERT(nvarchar(255), est.ESTADO) LIKE ?
            OR TRY_CONVERT(varchar(50), d.codigo_doc) = ?
            OR TRY_CONVERT(varchar(50), u.Codigo_Usuario) = ?
        )
        """
        )
        params = [like, like, like, like, like, like, like, like, cleaned_query, cleaned_query]
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_actualizacion_est_select(limit, where_sql), params)
            rows = [_actualizacion_est_row(row) for row in cursor.fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar la actualizacion de estados docentes") from exc
    return {
        "section": _section_meta("actualizacion_est", section).model_dump(),
        "rows": rows,
        "total": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_actualizacion_est_record(section: dict[str, Any], record_key: str) -> dict[str, Any]:
    key_values = _decode_key(record_key, 2)
    codigo_doc, codigo_usuario = key_values
    params: list[Any] = []
    where_parts: list[str] = ["(u.Codigo_Usuario IS NULL OR COALESCE(TRY_CONVERT(int, u.tipo_usuario), 2) <> 1)"]
    if str(codigo_doc or "").strip():
        where_parts.append("TRY_CONVERT(int, d.codigo_doc) = TRY_CONVERT(int, ?)")
        params.append(codigo_doc)
    else:
        where_parts.append("d.codigo_doc IS NULL")
    if str(codigo_usuario or "").strip():
        where_parts.append("TRY_CONVERT(int, u.Codigo_Usuario) = TRY_CONVERT(int, ?)")
        params.append(codigo_usuario)
    else:
        where_parts.append("u.Codigo_Usuario IS NULL")
    where_sql = f"WHERE {' AND '.join(where_parts)}"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_actualizacion_est_select(1, where_sql), params)
            row = cursor.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar el estado del docente") from exc
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Docente no encontrado")
    return {"section": _section_meta("actualizacion_est", section).model_dump(), "record": _actualizacion_est_row(row)}


def _update_actualizacion_est_record(section: dict[str, Any], record_key: str, payload: SavePayload) -> dict[str, Any]:
    del section
    key_values = _decode_key(record_key, 2)
    codigo_doc, codigo_usuario_key = key_values
    estado_codigo = str(payload.values.get("Estado") or "").strip().upper()
    informacion = str(payload.values.get("Informacion") or "").strip()
    update_information = "Informacion" in payload.values
    if not estado_codigo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selecciona el estado del docente")
    if estado_codigo not in {"A", "P"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado docente permitido: A (Activo) o P (Inactivo)")
    if not str(codigo_usuario_key or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El registro no tiene usuario vinculado en USUARIOS")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))) AS codigo,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), ESTADO))) AS nombre
                FROM dbo.ESTADO
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) = ?
                  AND UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) IN (N'A', N'P')
                """,
                estado_codigo,
            )
            state = cursor.fetchone()
            if not state:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El estado seleccionado no existe en dbo.ESTADO")

            cursor.execute(
                """
                SELECT TOP (1)
                    TRY_CONVERT(int, Codigo_Usuario) AS codigo_usuario
                FROM dbo.USUARIOS
                WHERE TRY_CONVERT(int, Codigo_Usuario) = TRY_CONVERT(int, ?)
                  AND COALESCE(TRY_CONVERT(int, tipo_usuario), 2) <> 1
                """,
                codigo_usuario_key,
            )
            usuario = cursor.fetchone()
            if not usuario:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario docente no existe en USUARIOS")
            codigo_usuario = getattr(usuario, "codigo_usuario", None)
            if codigo_usuario is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El registro no tiene usuario vinculado en USUARIOS")

            cursor.execute(
                """
                UPDATE dbo.USUARIOS
                SET
                    Estado = ?,
                    Descripcion = CASE WHEN ? = 1 THEN NULLIF(?, N'') ELSE Descripcion END
                WHERE TRY_CONVERT(int, Codigo_Usuario) = ?
                """,
                estado_codigo,
                1 if update_information else 0,
                informacion,
                codigo_usuario,
            )
            affected = cursor.rowcount
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo actualizar el estado del docente") from exc

    return {
        "ok": True,
        "message": f"Estado docente actualizado a {_serialize_value(state.nombre) or estado_codigo}",
        "affected_rows": affected,
    }


def _attach_student_identity(cursor: Any, rows: list[dict[str, Any]], section_key: str) -> None:
    code_field = STUDENT_CODE_FIELD_BY_SECTION.get(section_key)
    if not code_field or not rows:
        return

    codes = sorted({_student_lookup_code(row.get(code_field)) for row in rows if _student_lookup_code(row.get(code_field))})
    if not codes:
        return

    lookup: dict[str, dict[str, str]] = {}
    for index in range(0, len(codes), 700):
        chunk = codes[index : index + 700]
        placeholders = ", ".join("?" for _ in chunk)
        cursor.execute(
            f"""
            SELECT
                TRY_CONVERT(varchar(50), codigo_estud) AS codigo_estud,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Cedula_Est))) AS estudiante_cedula,
                LTRIM(RTRIM(TRY_CONVERT(nvarchar(200), Apellidos_nombre))) AS estudiante_nombre
            FROM dbo.DATOS_ESTUD
            WHERE TRY_CONVERT(varchar(50), codigo_estud) IN ({placeholders})
            """,
            chunk,
        )
        for record in cursor.fetchall():
            code = _student_lookup_code(getattr(record, "codigo_estud", ""))
            lookup[code] = {
                "estudiante_nombre": _serialize_value(getattr(record, "estudiante_nombre", "")) or "",
                "estudiante_cedula": _serialize_value(getattr(record, "estudiante_cedula", "")) or "",
            }

    for row in rows:
        code = _student_lookup_code(row.get(code_field))
        identity = lookup.get(code, {})
        row["estudiante_nombre"] = identity.get("estudiante_nombre") or row.get("Nombres") or row.get("nombres") or ""
        row["estudiante_cedula"] = identity.get("estudiante_cedula") or ""


def _encode_key(values: list[Any]) -> str:
    raw = json.dumps([_serialize_value(value) for value in values], separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_key(record_key: str, expected_len: int) -> list[Any]:
    try:
        padding = "=" * (-len(record_key) % 4)
        values = json.loads(base64.urlsafe_b64decode((record_key + padding).encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clave de registro invalida") from exc
    if not isinstance(values, list) or len(values) != expected_len:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clave de registro incompleta")
    return values


def _field_map(section: dict[str, Any], group: str) -> dict[str, FieldMeta]:
    return {meta.name: meta for meta in section.get(group, [])}


def _normalize_value(value: Any, meta: FieldMeta | None) -> Any:
    if value == "":
        return None
    if value is None:
        return None
    field_type = (meta.type if meta else "text").lower()
    if field_type in {"number", "int"}:
        return int(value)
    if field_type == "decimal":
        return Decimal(str(value))
    if field_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "si", "yes", "on"}
    return value


def _default_value(default: Any, current_user: SessionUser) -> Any:
    if default == "now":
        return datetime.now()
    if default == "today":
        return date.today()
    if default == "current_user":
        return current_user.login
    if default == "current_user_id":
        return int(current_user.id_usuario or 0)
    return default


def _where_clause(key_fields: list[str]) -> str:
    return " AND ".join(f"{_quote_column(field_name)} = ?" for field_name in key_fields)


def _lookup_rows(cursor: Any, queries: list[str]) -> list[dict[str, str]]:
    for sql in queries:
        try:
            cursor.execute(sql)
            options: list[dict[str, str]] = []
            seen: set[str] = set()
            for row in cursor.fetchall():
                value = str(_serialize_value(row.option_value) or "").strip()
                label = str(_serialize_value(row.option_label) or value).strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                options.append({"value": value, "label": label})
            if options:
                return options
        except Exception:
            continue
    return []


def _lookup_options_by_section() -> dict[str, dict[str, list[dict[str, str]]]]:
    lookups: dict[str, dict[str, list[dict[str, str]]]] = {}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            for section_key, field_queries in LOOKUP_QUERIES.items():
                section_lookups: dict[str, list[dict[str, str]]] = {}
                for field_name, queries in field_queries.items():
                    options = _lookup_rows(cursor, queries)
                    if options:
                        section_lookups[field_name] = options
                if section_lookups:
                    lookups[section_key] = section_lookups
    except Exception:
        return {}
    return lookups


def _attach_options(fields: list[FieldMeta], options: dict[str, list[dict[str, str]]] | None) -> list[FieldMeta]:
    if not options:
        return fields
    return [field_meta.model_copy(update={"options": options.get(field_meta.name, field_meta.options)}) for field_meta in fields]


def _section_meta(section_key: str, section: dict[str, Any], options: dict[str, list[dict[str, str]]] | None = None) -> SectionMeta:
    return SectionMeta(
        key=section_key,
        title=section["title"],
        category=section["category"],
        description=section["description"],
        table=section["table"].replace("[dbo].", "dbo."),
        key_fields=section["key_fields"],
        list_fields=_attach_options(section["list_fields"], options),
        detail_fields=_attach_options(section["detail_fields"], options),
        editable_fields=_attach_options(section["editable_fields"], options),
        create_fields=_attach_options(section.get("create_fields", []), options),
    )


LEGACY_CLONE_MODULES: list[dict[str, Any]] = [
    {
        "key": "seguridad",
        "title": "Seguridad, usuarios y menu",
        "description": "Login, perfiles, accesos y menus heredados.",
        "source_paths": ["Default.aspx", "Index.aspx", "Cabecera.aspx", "cabeceras.aspx", "izquierda.aspx", "menus.aspx", "blanco.aspx", "MensajeError.aspx", "accesousuarios/"],
        "tables": ["USUARIOS", "USUARIO_SIS", "TIPO_USUARIO", "MENU_GENERAL", "MENU_TIPO_USU", "MENU_USUARIOS"],
        "modern_sections": ["usuarios", "menu_usuarios", "menu_general"],
        "modern_routes": ["auth.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "El login WebForms no se copia; se conserva autenticacion moderna y datos legacy administrables.",
    },
    {
        "key": "estudiantes",
        "title": "Estudiantes y ficha academica",
        "description": "Datos personales, estado, correo institucional, documentos y seguimiento.",
        "source_paths": ["IngNuevoEstudianteWeb.aspx", "IngNuevoEstudianteWeb.aspx - copia.vb", "Actualiza_Estud.aspx", "Actualiza_EstudPeriodo.aspx", "Actualiza_Informacion.aspx", "Informacion.aspx", "ImprimirEstudianteWeb.aspx", "SubirDocumentos.aspx"],
        "tables": ["DATOS_ESTUD", "CorreosEstudIntec", "REGISTRODOCESTUD", "ESTADO"],
        "modern_sections": ["estudiantes", "actualizacion_estudiantes", "registro_documentos_estudiante", "correos", "seguimiento"],
        "modern_routes": ["students.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Se mantiene INTECBDD como fuente; cargas nuevas deben pasar por backend validado.",
    },
    {
        "key": "admision",
        "title": "Admision y preinscripcion",
        "description": "Aspirantes, asesores, datos de factura, documentos y paso a matricula.",
        "source_paths": ["Inscripcion.aspx", "InscripcionPre.aspx", "Datosprematricula.aspx", "Datosprematricula.aspx - copia.vb", "AsignaAsesor.aspx", "AsesorEstudiante.aspx", "InscripcionSAEC/"],
        "tables": ["PREINSCRIPCION", "DATOSFACTURA", "IN_LECONTACTO", "IN_ENTERO", "IN_DESEAINGRESAR", "IN_DESCCONVE", "IN_DESCONVVALOR", "IN_DESDEPOTRANS"],
        "modern_sections": ["preinscripciones", "datos_factura"],
        "modern_routes": ["preinscription.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "El flujo moderno de preinscripcion reemplaza formularios duplicados de WebForms.",
    },
    {
        "key": "matricula",
        "title": "Matricula academica y financiera",
        "description": "Cabecera, materias, pagos, convenios y cambios H/R.",
        "source_paths": [
            "ModificarMaterias.aspx",
            "ModificarMateriasHaR.aspx",
            "ModificarMateriasConvalida.aspx",
            "actualizar/EliminarMatricula.aspx",
            "ImprimirConvalida.aspx",
            "ImprimirMatricula.aspx",
            "ImprimirPreMatricula.aspx",
            "IngresoDiasMatricula.aspx",
            "IngresoHorasMatricula.aspx",
            "IngresoModalidadMatricula.aspx",
            "Reporteshtml/ListaMatriPeriodo.aspx",
            "Reporteshtml/ListaMatriPeriodoNotas.aspx",
            "Registropagos.aspx",
        ],
        "tables": ["CABECERA_MATRICULA", "CARRERAXESTUD", "REGISTROPAGOS", "CONTROLMATRICULA", "ESTADOMATRICULA"],
        "modern_sections": ["cabecera_matricula", "matricula_materias", "pagos_matricula", "cambio_periodo_hr"],
        "modern_routes": ["academic_enrollment.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Las operaciones transaccionales deben permanecer en backend; el CRUD generico queda para mantenimiento.",
    },
    {
        "key": "academico",
        "title": "Catalogos academicos",
        "description": "Carreras, pensum, mallas, periodos, jornadas, paralelos y modalidades.",
        "source_paths": [
            "Carreras.aspx",
            "Actualiza_Examenes.aspx",
            "IngresarMaterias.aspx",
            "IngresoMallaCarrera.aspx",
            "IngresoMateriahomoTexto.aspx",
            "IngModificarExa.aspx",
            "Ingresoproyecto.aspx",
            "PeriodosAcademicos.aspx",
            "IngresoParalelos.aspx",
            "IngresoModalidadMatricula.aspx",
            "Provincias.aspx",
            "Reporteshtml/ActualizarParaleloMatriPeriodo.aspx",
        ],
        "tables": ["CARRERAS", "PENSUM", "MALLA_PENSUM", "MATERIAHOMOTEXTOF", "PERIODO", "PARALELOS", "JORNADA", "ModalidadMatricula", "Provincias"],
        "modern_sections": ["carreras", "materias", "mallas", "materia_homo_textof", "periodos", "paralelos", "jornadas", "modalidades", "provincias"],
        "modern_routes": ["sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Mantenimiento directo expuesto; reglas complejas se deben mover a endpoints dedicados.",
    },
    {
        "key": "notas",
        "title": "Notas y apertura de calificaciones",
        "description": "Ingreso de notas regulares, homologacion, repeticion, Moodle y fechas de apertura.",
        "source_paths": [
            "IngNotasAsignatura.aspx",
            "IngNotasAsignaturaConvav1.aspx",
            "IngNotasAsignaturaConvavDoce.aspx",
            "IngNotasAsignaturaDocente.aspx",
            "IngNotasAsignaturaNO.aspx",
            "IngNotasAsignaturaRepa.aspx",
            "IngresoNotasDocente.aspx",
            "BloqueoNotas.aspx",
            "PasarnotasdeIngles.aspx",
            "fechasingresonotas/IngFechasIngNotas.aspx",
            "fechasingresonotas/IngNotasAsignatura.aspx",
            "fechasingresonotas/ListaPeriodoAnteriorActual.aspx",
            "ReporteNotas/Notasweb/",
        ],
        "tables": ["CARRERAXESTUD", "CARRERAXDOCENTE", "ACTIVAREXAMEN", "intec_estudiantenota", "intec_moodlegradesynclog"],
        "modern_sections": ["matricula_materias", "fechas_notas", "moodle_notas", "moodle_sincronizacion"],
        "modern_routes": ["portal_academico.py", "sisacademico_admin.py"],
        "coverage": "partial",
        "notes": "Lectura, reportes y administracion base estan cubiertas; falta cerrar ingreso masivo de notas V1 como flujo dedicado.",
    },
    {
        "key": "docentes",
        "title": "Docentes y asignaciones",
        "description": "Ficha docente, usuario, materias asignadas, contratos y estado.",
        "source_paths": [
            "NuevoProfe.aspx",
            "autoridades/NuevoProfe.aspx",
            "IngNuevoDocente.aspx",
            "ActualizarProfe.aspx",
            "ConsultaProfe.aspx",
            "actualizar/EliminarProfe.aspx",
            "ReporteAcad/ListaProfesores.aspx",
        ],
        "tables": ["DATOSDOCENTE", "USUARIOS", "CARRERAXDOCENTE", "CONTRATOSDOCENTE"],
        "modern_sections": ["docentes", "actualizacion_est", "docente_materias"],
        "modern_routes": ["teacher_evaluation.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "No sobrescribir el parche docente actual; se mantiene como puente seguro.",
    },
    {
        "key": "evaluacion_docente",
        "title": "Evaluacion docente y cuestionarios",
        "description": "Evaluacion estudiantil, autoevaluacion, banco de preguntas, planes y foros.",
        "source_paths": ["EvaluacionEstud.aspx", "AutoEvaluacion.aspx", "EncuestaDocEstud/", "CuestionarioVF.aspx", "CuestPregOpMult.aspx", "SubirCuestionario.aspx", "fechasingresonotas/IngFechasAutoevaluacion.aspx", "IngVerEvaluacionalProfe.aspx", "ModificaFechaCuest.aspx", "numpreguntas/"],
        "tables": ["CUESTIONARIO", "CUESTIONARIOEVALUA", "NUMEROPREGALEAT", "RESULTADO_EVALUACION", "RESULTADOAUTOEVALUACION", "ACTIVARAUTOEVALUACION"],
        "modern_sections": ["numero_preguntas", "cuestionarios", "preguntas_evaluacion", "evaluacion_resultados", "autoevaluacion_resultados", "fechas_autoevaluacion", "planes_foros"],
        "modern_routes": ["teacher_evaluation.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "El motor moderno de evaluacion debe prevalecer; tablas V1 quedan como fuente historica y administrable.",
    },
    {
        "key": "practicas",
        "title": "Practicas y vinculacion con la sociedad",
        "description": "Practicas preprofesionales, vinculacion con la sociedad, empresas y proyectos.",
        "source_paths": ["PracticasProfesionales.aspx", "PracticasVinculacion.aspx", "Vinculacion.aspx", "IngresoEmpresas.aspx"],
        "tables": ["PRACTICASPROFESIONALES", "PRACTICASVINCULACION", "EMPRESA", "Proyecto"],
        "modern_sections": ["practicas", "practicas_vinculacion", "empresas"],
        "modern_routes": ["practicas_institucionales.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "El modulo independiente puede reconocer datos legacy sin eliminarlos.",
    },
    {
        "key": "titulacion",
        "title": "Titulacion, complexivo y defensa",
        "description": "Verificacion, complexivo, defensa de grado, actas y documentos finales.",
        "source_paths": [
            "MatriculaComplexivo.aspx",
            "IngNotasComplexivo.aspx",
            "IngresoFechaGrado.aspx",
            "ReporteNotas/Notasweb/ImprimirNotasComplexivo.aspx",
            "certificados/",
        ],
        "tables": ["CARRERAXESTUD", "CABECERA_MATRICULA", "PENSUM", "MALLA_PENSUM", "CERTIFICADOS_GENERADOS"],
        "modern_sections": ["certificados_generados", "fecha_grado", "titulacion"],
        "modern_routes": ["titulacion.py", "titulos_registrados.py"],
        "coverage": "partial",
        "notes": "La verificacion y proceso moderno estan en desarrollo; se conserva lectura legacy.",
    },
    {
        "key": "certificados",
        "title": "Certificados y reportes",
        "description": "Certificados institucionales y reportes historicos modernizados.",
        "source_paths": ["certificados/", "ReporteAcad/", "ReporteNotas/", "Reporteshtml/", "ReporteAcadxEstudDirecto.aspx"],
        "tables": ["CERTIFICADOS_GENERADOS", "CREDENCIALES_CURSO"],
        "modern_sections": ["certificados_generados", "credenciales_curso"],
        "modern_routes": ["certificados.py", "credential_generator.py", "legacy_reports.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Los reportes heredados se reemplazan por PDF/Excel/HTML moderno, no se copia el motor Crystal.",
    },
    {
        "key": "financiero_convenios",
        "title": "Financiero, pagos y convenios",
        "description": "Registro de pagos, convenios de pago y documentos financieros heredados.",
        "source_paths": [
            "RegistropagosFin.aspx",
            "RepFinanciero/",
            "SubirArchivoConenioPagos.aspx",
        ],
        "tables": ["REGISTROPAGOS", "DATOSFACTURA", "CABECERA_MATRICULA"],
        "modern_sections": ["pagos_matricula", "datos_factura"],
        "modern_routes": ["preinscription.py", "legacy_reports.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Los convenios se generan como PDF moderno y los adjuntos deben subirse por endpoint controlado.",
    },
    {
        "key": "educacion_continua",
        "title": "Educacion continua",
        "description": "Cursos, cortes, estudiantes, credenciales y certificados de educacion continua.",
        "source_paths": ["inscripciones/", "IngresarCurso.aspx", "certificados/RepcertificadosEdContinua.aspx"],
        "tables": ["CursosEduContinua", "CORTE_CURSO", "CORTE_CURSO_ESTUDIANTE", "CABECERAEDUCONTINUA", "EstudiantesEdContinua"],
        "modern_sections": ["cursos_edu_continua", "corte_curso", "corte_curso_estudiante", "credenciales_curso"],
        "modern_routes": ["sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Falta una vista dedicada si se requiere flujo completo de inscripcion y certificacion.",
    },
    {
        "key": "repositorio",
        "title": "Repositorio y documentos",
        "description": "Repositorio digital, documentos subidos y anexos por estudiante o materia.",
        "source_paths": ["repositorio/", "SUBIRARCHIVO/", "planes/Subirarchivos.aspx", "VerArchivos.aspx", "VerArchivosEstado.aspx"],
        "tables": ["REPOSITORIO", "REGISTRODOCESTUD", "TAMANIOARCHIVOS", "TIPODOCUMENTOS"],
        "modern_sections": ["repositorio", "registro_documentos_estudiante"],
        "modern_routes": ["sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Los archivos historicos se conservan; nuevas cargas deben pasar por backend validado.",
    },
    {
        "key": "integraciones",
        "title": "Integraciones Moodle y Microsoft 365",
        "description": "Notas Moodle, logs de sincronizacion, auditoria Microsoft y credenciales.",
        "source_paths": ["Intec/", "correo.aspx", "correo/", "CertificadoDigital/"],
        "tables": ["intec_estudiantenota", "intec_logmatriculacion", "intec_moodlegradesynclog", "Microsoft365Audit", "CREDENCIALES_CURSO"],
        "modern_sections": ["moodle_notas", "moodle_sincronizacion", "microsoft365_audit", "credenciales_curso"],
        "modern_routes": ["teams.py", "mass_email.py", "credential_generator.py", "sisacademico_admin.py"],
        "coverage": "base",
        "notes": "No exponer tokens ni credenciales; usar variables de entorno.",
    },
    {
        "key": "talento_humano",
        "title": "Talento humano",
        "description": "Empleados, jefaturas, solicitudes, archivos, tareas y roles RRHH.",
        "source_paths": ["TH_* en script SQL"],
        "tables": ["TH_EMPLEADO", "TH_JEFATURA", "TH_SOLICITUD", "TH_SOLICITUD_ARCHIVO", "TH_TAREA", "TH_TIPO_SOLICITUD"],
        "modern_sections": ["talento_humano_empleados", "talento_humano_solicitudes", "talento_humano_tareas"],
        "modern_routes": ["sisacademico_admin.py"],
        "coverage": "base",
        "notes": "Los binarios de solicitud deben descargarse mediante endpoint dedicado, no en listados.",
    },
    {
        "key": "mantenimiento_controlado",
        "title": "Mantenimiento controlado y operaciones sensibles",
        "description": "Pantallas V1 de eliminacion, copia o cambios auxiliares que no deben clonarse como acciones directas.",
        "source_paths": ["actualizar/CopiarMaterias.aspx", "actualizar/EliminarEstud.aspx", "actualizar/EliminarPreMatricula.aspx", "AuxCambios/cambios.aspx", "pruebas/"],
        "tables": ["CARRERAXESTUD", "CABECERA_MATRICULA", "PREINSCRIPCION", "DATOS_ESTUD"],
        "modern_sections": ["estudiantes", "cabecera_matricula", "matricula_materias", "preinscripciones"],
        "modern_routes": ["sisacademico_admin.py", "academic_enrollment.py", "preinscription.py"],
        "coverage": "partial",
        "notes": "Debe ejecutarse con auditoria, confirmacion y permisos altos; no se replica el boton de eliminar de WebForms.",
    },
    {
        "key": "soporte_legacy_no_migrable",
        "title": "Soporte legacy no migrable",
        "description": "Respaldos visuales, menus antiguos, archivos estaticos WebForms y visor Crystal que no son modulos operativos.",
        "source_paths": ["static/page_menu/", "aspnet_client/*/crystalreportviewers13/", "Bin/", ".vs/", "__Intec/", "Web.config", "WebV0.config", "packages.config", "cgi-bin/"],
        "tables": [],
        "modern_sections": [],
        "modern_routes": [],
        "coverage": "excluded",
        "notes": "Se conserva como referencia historica del proyecto, pero no se clona en backend/frontend moderno.",
    },
]


@router.get("/catalog")
def catalog(_: SessionUser = AllowedEditor) -> dict[str, Any]:
    section_options = _lookup_options_by_section()
    sections = [
        _section_meta(section_key, section, section_options.get(section_key, {})).model_dump()
        for section_key, section in SECTIONS.items()
    ]
    categories = sorted({section["category"] for section in SECTIONS.values()})
    return {"sections": sections, "categories": categories}


@router.get("/legacy-v1/modules")
def legacy_v1_modules(_: SessionUser = AllowedEditor) -> dict[str, Any]:
    totals = {
        "modules": len(LEGACY_CLONE_MODULES),
        "base": sum(1 for module in LEGACY_CLONE_MODULES if module["coverage"] == "base"),
        "partial": sum(1 for module in LEGACY_CLONE_MODULES if module["coverage"] == "partial"),
        "pending": sum(1 for module in LEGACY_CLONE_MODULES if module["coverage"] == "pending"),
        "excluded": sum(1 for module in LEGACY_CLONE_MODULES if module["coverage"] == "excluded"),
    }
    all_sections = set(SECTIONS.keys())
    modules = []
    for module in LEGACY_CLONE_MODULES:
        modern_sections = list(module.get("modern_sections", []))
        modules.append(
            {
                **module,
                "available_sections": [section for section in modern_sections if section in all_sections],
                "missing_sections": [section for section in modern_sections if section not in all_sections],
            }
        )
    return {
        "project": "SisAcademicoV1",
        "strategy": "Clonacion funcional por modulos, manteniendo INTECBDD y usando parches no destructivos.",
        "database": "INTECBDD",
        "compat_schema": "sisv1",
        "totals": totals,
        "modules": modules,
    }


def _student_state_safe_filename(filename: str) -> str:
    original = Path(str(filename or "documento")).name
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original).stem).strip("-_") or "documento"
    extension = Path(original).suffix.lower()
    return f"{stem[:80]}{extension}"


@router.post("/actualizacion_estudiantes/{record_key}/cambio-estado-documentado")
async def update_student_state_with_document(
    record_key: str,
    estado: str = Form(...),
    detalle: str = Form(...),
    documento: UploadFile = File(...),
    current_user: SessionUser = AllowedEditor,
) -> dict[str, Any]:
    cedula = str(_decode_key(record_key, 1)[0] or "").strip()
    estado_codigo = str(estado or "").strip().upper()
    motivo = str(detalle or "").strip()
    original_name = Path(str(documento.filename or "")).name
    extension = Path(original_name).suffix.lower()

    if not cedula:
        raise HTTPException(status_code=400, detail="Clave de estudiante incompleta")
    if not estado_codigo:
        raise HTTPException(status_code=400, detail="Selecciona el nuevo estado")
    if len(motivo) < 5:
        raise HTTPException(status_code=400, detail="Describe el motivo del cambio de estado")
    if extension not in _STUDENT_STATE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Adjunta un documento PDF, imagen, DOC o DOCX")

    file_bytes = await documento.read(_STUDENT_STATE_MAX_FILE_SIZE + 1)
    await documento.close()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="El documento esta vacio")
    if len(file_bytes) > _STUDENT_STATE_MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El documento supera el limite de 15 MB")

    saved_path: Path | None = None
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    TRY_CONVERT(varchar(50), d.codigo_estud) AS codigo_estud,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), d.Estado))) AS estado_anterior,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), d.Apellidos_nombre))) AS estudiante
                FROM dbo.DATOS_ESTUD d
                WHERE LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), d.Cedula_Est))) = ?
                """,
                cedula,
            )
            student = cursor.fetchone()
            if not student:
                raise HTTPException(status_code=404, detail="Estudiante no existe en DATOS_ESTUD")

            cursor.execute(
                """
                SELECT TOP (1)
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO))) AS codigo,
                    LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), ESTADO))) AS nombre
                FROM dbo.ESTADO
                WHERE UPPER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(50), IDESTADO)))) = ?
                """,
                estado_codigo,
            )
            state = cursor.fetchone()
            if not state:
                raise HTTPException(status_code=400, detail="El estado seleccionado no existe en dbo.ESTADO")

            estado_anterior = str(student.estado_anterior or "").strip().upper()
            if estado_anterior == estado_codigo:
                raise HTTPException(status_code=400, detail="Selecciona un estado diferente al estado actual")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target_dir = _STUDENT_STATE_DOCUMENT_ROOT / str(student.codigo_estud)
            target_dir.mkdir(parents=True, exist_ok=True)
            saved_name = f"{timestamp}_{_student_state_safe_filename(original_name)}"
            saved_path = target_dir / saved_name
            saved_path.write_bytes(file_bytes)
            document_url = f"/uploads/estados_estudiantes/{student.codigo_estud}/{saved_name}"

            user_name = str(current_user.nombres or current_user.login or "usuario").strip()
            state_detail = (
                f"[CAMBIO DE ESTADO] {estado_anterior or 'SIN ESTADO'} -> {estado_codigo}. "
                f"Motivo: {motivo}. Usuario: {user_name}. Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."
            )[:1000]

            cursor.execute(
                """
                UPDATE dbo.DATOS_ESTUD
                SET Estado = ?
                WHERE LTRIM(RTRIM(TRY_CONVERT(nvarchar(100), Cedula_Est))) = ?
                """,
                estado_codigo,
                cedula,
            )
            affected = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO dbo.REGISTRODOCESTUD (IDESTUD, LINKURL, DETALLE, TIPO)
                VALUES (?, ?, ?, 0)
                """,
                student.codigo_estud,
                document_url,
                state_detail,
            )
            conn.commit()
    except HTTPException:
        if saved_path is not None:
            saved_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if saved_path is not None:
            saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="No se pudo registrar el cambio de estado documentado") from exc

    return {
        "ok": True,
        "message": f"Estado actualizado a {_serialize_value(state.nombre) or estado_codigo} con documento de respaldo",
        "affected_rows": affected,
        "document_url": document_url,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _legacy_project_root() -> Path:
    return _repo_root() / "SisAcademicoV1"


def _path_matches_source(relative_path: str, source: str) -> bool:
    normalized_path = relative_path.replace("\\", "/").lower()
    comparable_paths = [normalized_path]
    if normalized_path.endswith(".aspx.vb"):
        comparable_paths.append(normalized_path[:-3])
    normalized_source = source.replace("\\", "/").lower().rstrip("/")
    if not normalized_source:
        return False
    if normalized_source.endswith("*"):
        return any(path.startswith(normalized_source[:-1]) for path in comparable_paths)
    return any(path == normalized_source or path.startswith(f"{normalized_source}/") for path in comparable_paths)


def _classify_legacy_artifact(relative_path: str) -> dict[str, str]:
    normalized = relative_path.replace("\\", "/")
    lower_path = normalized.lower()
    extension = Path(normalized).suffix.lower().lstrip(".") or "archivo"

    for module in LEGACY_CLONE_MODULES:
        for source in module.get("source_paths", []):
            if _path_matches_source(normalized, source):
                return {
                    "module_key": str(module["key"]),
                    "module_title": str(module["title"]),
                    "coverage": str(module["coverage"]),
                    "artifact_type": extension,
                }

    if "/static/" in lower_path or "/aspnet_client/" in lower_path or "/bin/" in lower_path:
        return {
            "module_key": "soporte_legacy_no_migrable",
            "module_title": "Soporte legacy no migrable",
            "coverage": "excluded",
            "artifact_type": extension,
        }
    if "/actualizar/" in lower_path or "/auxcambios/" in lower_path or "/pruebas/" in lower_path:
        return {
            "module_key": "mantenimiento_controlado",
            "module_title": "Mantenimiento controlado y operaciones sensibles",
            "coverage": "partial",
            "artifact_type": extension,
        }
    if "/reporteacad/" in lower_path or "/reportenotas/" in lower_path or "/reporteshtml/" in lower_path or lower_path.endswith(".rpt"):
        return {
            "module_key": "certificados",
            "module_title": "Certificados y reportes",
            "coverage": "base",
            "artifact_type": extension,
        }
    return {
        "module_key": "pendiente_clasificacion",
        "module_title": "Pendiente de clasificacion",
        "coverage": "pending",
        "artifact_type": extension,
    }


@router.get("/legacy-v1/artifacts")
def legacy_v1_artifacts(_: SessionUser = AllowedEditor) -> dict[str, Any]:
    project_root = _legacy_project_root()
    if not project_root.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe la carpeta local SisAcademicoV1")

    artifacts: list[dict[str, Any]] = []
    extensions = {".aspx", ".vb", ".rpt", ".config"}
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        relative_path = str(path.relative_to(project_root)).replace("\\", "/")
        classification = _classify_legacy_artifact(relative_path)
        artifacts.append(
            {
                "path": relative_path,
                "file_name": path.name,
                "extension": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
                **classification,
            }
        )

    by_extension: dict[str, int] = {}
    by_coverage: dict[str, int] = {}
    by_module: dict[str, int] = {}
    for artifact in artifacts:
        by_extension[str(artifact["extension"])] = by_extension.get(str(artifact["extension"]), 0) + 1
        by_coverage[str(artifact["coverage"])] = by_coverage.get(str(artifact["coverage"]), 0) + 1
        by_module[str(artifact["module_key"])] = by_module.get(str(artifact["module_key"]), 0) + 1

    return {
        "project": "SisAcademicoV1",
        "root": str(project_root),
        "strategy": "Clonacion total navegable: cada artefacto legacy se clasifica como modulo moderno, mantenimiento controlado o soporte no migrable.",
        "totals": {
            "artifacts": len(artifacts),
            "by_extension": by_extension,
            "by_coverage": by_coverage,
            "by_module": by_module,
        },
        "artifacts": artifacts,
    }


@router.get("/{section_key}")
def list_records(
    section_key: str,
    query: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    periodo: str | None = Query(default=None),
    _: SessionUser = AllowedEditor,
) -> dict[str, Any]:
    del limit
    section = _section(section_key)
    if section_key == "actualizacion_estudiantes":
        return _list_actualizacion_estudiantes_records(section, query, None, periodo)
    if section_key == "actualizacion_est":
        return _list_actualizacion_est_records(section, query, None)
    if section_key == "cambio_periodo_hr":
        return {
            "section": _section_meta(section_key, section).model_dump(),
            "rows": [],
            "total": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    columns = _selectable_columns(_column_names(section["list_fields"]))
    select_columns = ", ".join(_quote_column(column) for column in columns)
    sql_params: list[Any] = []
    where = ""
    cleaned_query = str(query or "").strip()
    if cleaned_query:
        like = f"%{cleaned_query}%"
        search_parts = [f"CAST({_quote_column(column)} AS nvarchar(max)) LIKE ?" for column in section.get("search_fields", [])]
        code_field = STUDENT_CODE_FIELD_BY_SECTION.get(section_key)
        if code_field:
            search_parts.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM dbo.DATOS_ESTUD datos_estud_busqueda
                    WHERE TRY_CONVERT(decimal(18, 0), datos_estud_busqueda.codigo_estud)
                        = TRY_CONVERT(decimal(18, 0), {_quote_column(code_field)})
                      AND (
                          CAST(datos_estud_busqueda.Cedula_Est AS nvarchar(max)) LIKE ?
                          OR CAST(datos_estud_busqueda.Apellidos_nombre AS nvarchar(max)) LIKE ?
                      )
                )
                """
            )
        where = f"WHERE {' OR '.join(search_parts)}"
        sql_params = [like for _ in section.get("search_fields", [])]
        if code_field:
            sql_params.extend([like, like])
    sql = f"""
        SELECT {select_columns}
        FROM {section["table"]}
        {where}
        ORDER BY {section["order_by"]}
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, sql_params)
            rows = _rows_from_cursor(cursor, section_key, section["key_fields"])
            _attach_student_identity(cursor, rows, section_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar la seccion") from exc
    return {
        "section": _section_meta(section_key, section).model_dump(),
        "rows": rows,
        "total": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{section_key}/{record_key}")
def get_record(section_key: str, record_key: str, _: SessionUser = AllowedEditor) -> dict[str, Any]:
    section = _section(section_key)
    if section_key == "actualizacion_estudiantes":
        return _get_actualizacion_estudiantes_record(section, record_key)
    if section_key == "actualizacion_est":
        return _get_actualizacion_est_record(section, record_key)

    key_values = _decode_key(record_key, len(section["key_fields"]))
    columns = _selectable_columns(_all_read_columns(section))
    sql = f"""
        SELECT {", ".join(_quote_column(column) for column in columns)}
        FROM {section["table"]}
        WHERE {_where_clause(section["key_fields"])}
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, key_values)
            rows = _rows_from_cursor(cursor, section_key, section["key_fields"])
            _attach_student_identity(cursor, rows, section_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo consultar el registro") from exc
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro no encontrado")
    return {"section": _section_meta(section_key, section).model_dump(), "record": rows[0]}


@router.put("/{section_key}/{record_key}")
def update_record(
    section_key: str,
    record_key: str,
    payload: SavePayload,
    current_user: SessionUser = AllowedEditor,
) -> dict[str, Any]:
    section = _section(section_key)
    if section_key == "actualizacion_estudiantes":
        return _update_actualizacion_estudiantes_record(section, record_key, payload)
    if section_key == "actualizacion_est":
        return _update_actualizacion_est_record(section, record_key, payload)

    editable = _field_map(section, "editable_fields")
    updates: dict[str, Any] = {}
    for name, value in payload.values.items():
        if name in editable:
            updates[name] = _normalize_value(value, editable[name])
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay campos editables para guardar")
    if "fecha_modificacion" in _all_read_columns(section) and "fecha_modificacion" in editable:
        updates["fecha_modificacion"] = datetime.now()
    if "usuario_modificacion" in editable and "usuario_modificacion" not in updates:
        updates["usuario_modificacion"] = current_user.login

    key_values = _decode_key(record_key, len(section["key_fields"]))
    set_clause = ", ".join(f"{_quote_column(column)} = ?" for column in updates)
    sql = f"""
        UPDATE {section["table"]}
        SET {set_clause}
        WHERE {_where_clause(section["key_fields"])}
    """
    params = list(updates.values()) + key_values
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            affected = cursor.rowcount
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar el registro") from exc
    return {"ok": True, "message": "Registro actualizado", "affected_rows": affected}


def _create_docente_with_user(payload: SavePayload) -> dict[str, Any]:
    section = _section("docentes")
    creatable = _field_map(section, "create_fields")
    values: dict[str, Any] = {}
    for name, meta in creatable.items():
        value = payload.values.get(name)
        if meta.required and (value is None or value == ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campo requerido: {meta.label}")
        if value is not None and value != "":
            values[name] = _normalize_value(value, meta)

    docente_columns = [
        "codigo_doc",
        "cedula_doc",
        "apellidos_nombre",
        "correo",
        "telefono",
        "movil",
        "TipoDocente",
    ]
    insert_columns = [column for column in docente_columns if column in values]
    if not {"codigo_doc", "cedula_doc", "apellidos_nombre"}.issubset(values):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Faltan datos base del docente")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO dbo.DATOSDOCENTE ({", ".join(_quote_column(column) for column in insert_columns)})
                VALUES ({", ".join("?" for _ in insert_columns)})
                """,
                [values[column] for column in insert_columns],
            )

            password = str(values.get("password") or "").strip()
            if password:
                login = str(values.get("login") or values.get("correo") or values["cedula_doc"]).strip()
                cursor.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1
                        FROM dbo.USUARIOS
                        WHERE cedula = ? AND tipo_usuario = 2
                    )
                    BEGIN
                        INSERT INTO dbo.USUARIOS
                            (Codigo_Usuario, cedula, login, password, tipo_usuario, fecha_ingreso)
                        VALUES (?, ?, ?, ?, 2, ?)
                    END
                    """,
                    values["cedula_doc"],
                    values["codigo_doc"],
                    values["cedula_doc"],
                    login,
                    password,
                    datetime.now(),
                )
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo crear el docente") from exc

    return {"ok": True, "message": "Docente creado"}


def _create_or_update_materia_homo_text(payload: SavePayload) -> dict[str, Any]:
    section = _section("materia_homo_textof")
    creatable = _field_map(section, "create_fields")
    values: dict[str, Any] = {}
    for name, meta in creatable.items():
        value = payload.values.get(name)
        if meta.required and (value is None or value == ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campo requerido: {meta.label}")
        if value is not None and value != "":
            values[name] = _normalize_value(value, meta)

    cod_materia = str(values.get("cod_materia") or "").strip()
    cod_periodo = values.get("cod_periodo")
    textofecha = str(values.get("textofecha") or "").strip()
    if not cod_materia:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Codigo materia")
    if cod_periodo is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Periodo")
    if not textofecha:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Texto fecha")

    materia = values.get("materia") or cod_materia
    url = values.get("url")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM dbo.MATERIAHOMOTEXTOF
                WHERE cod_materia = ? AND cod_periodo = ?
                """,
                cod_materia,
                cod_periodo,
            )
            exists = cursor.fetchone() is not None
            if exists:
                cursor.execute(
                    """
                    UPDATE dbo.MATERIAHOMOTEXTOF
                    SET materia = ?, textofecha = ?, url = ?
                    WHERE cod_materia = ? AND cod_periodo = ?
                    """,
                    materia,
                    textofecha,
                    url,
                    cod_materia,
                    cod_periodo,
                )
                action = "updated"
                message = "Texto HOMO actualizado"
            else:
                cursor.execute(
                    """
                    INSERT INTO dbo.MATERIAHOMOTEXTOF (cod_materia, cod_periodo, materia, textofecha, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    cod_materia,
                    cod_periodo,
                    materia,
                    textofecha,
                    url,
                )
                action = "created"
                message = "Texto HOMO creado"
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar el texto HOMO") from exc

    return {"ok": True, "message": message, "affected_rows": 1, "action": action}


def _create_usuario_sis(payload: SavePayload) -> dict[str, Any]:
    section = _section("usuarios")
    creatable = _field_map(section, "create_fields")
    values: dict[str, Any] = {}
    for name, meta in creatable.items():
        value = payload.values.get(name)
        if meta.required and (value is None or value == ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campo requerido: {meta.label}")
        if value is not None and value != "":
            values[name] = _normalize_value(value, meta)
    for name, default in section.get("defaults", {}).items():
        if name not in values:
            values[name] = _default_value(default, None)

    login = str(values.get("login") or "").strip()
    password = str(values.get("password") or "").strip()
    nombres = str(values.get("nombres") or "").strip()
    if not login:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Login")
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Contraseña")
    if not nombres:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campo requerido: Nombres")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña debe tener al menos 8 caracteres")
    if len(login) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login no puede superar 100 caracteres")
    if len(password) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña no puede superar 50 caracteres")
    if len(nombres) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombres no puede superar 100 caracteres")

    values["login"] = login
    values["password"] = password
    values["nombres"] = nombres
    estado = str(values.get("estado") or "").strip()
    if estado:
        values["estado"] = estado[0].upper()
    else:
        values["estado"] = "A"
    if not values.get("fecha_ingreso"):
        values["fecha_ingreso"] = datetime.now()
    values["tipousuario"] = 0
    if "email" in values:
        values["email"] = str(values.get("email") or "").strip()
        if len(str(values["email"])) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email no puede superar 50 caracteres")
    if "cedula" in values:
        values["cedula"] = str(values.get("cedula") or "").strip()
        if len(str(values["cedula"])) > 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cedula no puede superar 10 caracteres")
    if "tp_us" in values:
        values["tp_us"] = str(values.get("tp_us") or "").strip() or "1"
        if len(str(values["tp_us"])) > 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfil no puede superar 2 caracteres")

    allowed_columns = {
        "login",
        "password",
        "nombres",
        "fecha_ingreso",
        "estado",
        "email",
        "coordcarrera",
        "codprovincia",
        "tipousuario",
        "tp_us",
        "cedula",
    }
    insert_values = {key: value for key, value in values.items() if key in allowed_columns}
    columns = list(insert_values)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM dbo.USUARIO_SIS
                WHERE LOWER(LTRIM(RTRIM(TRY_CONVERT(nvarchar(255), login)))) = LOWER(?)
                """,
                login,
            )
            if cursor.fetchone():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con ese login")
            cursor.execute(
                f"""
                INSERT INTO dbo.USUARIO_SIS ({", ".join(_quote_column(column) for column in columns)})
                VALUES ({", ".join("?" for _ in columns)})
                """,
                list(insert_values.values()),
            )
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo registrar el usuario: {exc}") from exc

    return {"ok": True, "message": "Usuario registrado en USUARIO_SIS", "affected_rows": 1}


@router.post("/{section_key}")
def create_record(
    section_key: str,
    payload: SavePayload,
    current_user: SessionUser = AllowedEditor,
) -> dict[str, Any]:
    if section_key == "usuarios":
        return _create_usuario_sis(payload)
    if section_key == "docentes":
        return _create_docente_with_user(payload)
    if section_key == "materia_homo_textof":
        return _create_or_update_materia_homo_text(payload)

    section = _section(section_key)
    creatable = _field_map(section, "create_fields")
    if not creatable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta seccion no permite creacion directa")
    values: dict[str, Any] = {}
    for name, meta in creatable.items():
        value = payload.values.get(name)
        if meta.required and (value is None or value == ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campo requerido: {meta.label}")
        if value is not None and value != "":
            values[name] = _normalize_value(value, meta)
    for name, default in section.get("defaults", {}).items():
        if name not in values:
            values[name] = _default_value(default, current_user)
    if "usuario_registro" in creatable and "usuario_registro" not in values:
        values["usuario_registro"] = current_user.login

    columns = list(values)
    sql = f"""
        INSERT INTO {section["table"]} ({", ".join(_quote_column(column) for column in columns)})
        VALUES ({", ".join("?" for _ in columns)})
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, list(values.values()))
            conn.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el registro: {exc}",
        ) from exc
    return {"ok": True, "message": "Registro creado"}
