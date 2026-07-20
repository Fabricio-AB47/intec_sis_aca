from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import pyodbc
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.security import SessionUser, require_roles
from app.services.db import get_connection, get_practices_connection

router = APIRouter(prefix="/api/practicas", tags=["practicas-institucionales"])

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _BACKEND_ROOT / "uploads" / "practicas"
_MAX_UPLOAD_SIZE = 12 * 1024 * 1024

_ADMIN_ACCESS = require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE", "SECRETARIA")
_STUDENT_ACCESS = require_roles("ESTUDIANTE", "ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE")
_RESPONSIBLE_ACCESS = require_roles("DOCENTE", "ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE")
_ALL_ACCESS = require_roles(
    "ADMINISTRADOR",
    "ACADEMICO",
    "RECTOR",
    "VICERRECTOR",
    "SOPORTE",
    "SECRETARIA",
    "ESTUDIANTE",
    "DOCENTE",
)

PROCESS_LABELS = {
    "PPF": "Prácticas preprofesionales",
    "VIN": "Vinculación con la sociedad",
}


class CreateExpedientePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_estud: int | None = None
    codigo_carrera: str | None = None
    codigo_periodo: str | None = None
    observacion: str | None = None


class ResponsablePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    expediente_id: int | None = None
    nombre_responsable: str = Field(min_length=3, max_length=250)
    rol_responsable: str = Field(default="RESPONSABLE", max_length=50)
    codigo_docente: str | None = Field(default=None, max_length=50)
    cedula_responsable: str | None = Field(default=None, max_length=20)
    correo_responsable: str | None = Field(default=None, max_length=250)


class PeriodoResponsablePayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_periodo: str = Field(min_length=1, max_length=50)
    codigo_periodo_origen: str | None = Field(default=None, max_length=50)
    nombre_responsable: str = Field(min_length=3, max_length=250)
    rol_responsable: str = Field(default="RESPONSABLE", max_length=50)
    codigo_docente: str = Field(min_length=1, max_length=50)
    cedula_responsable: str | None = Field(default=None, max_length=20)
    correo_responsable: str | None = Field(default=None, max_length=250)
    estudiantes: list[int] = Field(default_factory=list)


class AssignResponsablePayload(BaseModel):
    responsable_proceso_id: int


class AutorizacionPracticaPayload(BaseModel):
    tipo_proceso_codigo: str = Field(pattern="^(PPF|VIN)$")
    codigo_estud: int
    codigo_periodo: str = Field(min_length=1, max_length=50)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [column[0] for column in cursor.description or []]
    return {column: getattr(row, column) for column in columns}


def _fetch_all(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    return [_row_dict(cursor, row) for row in cursor.fetchall()]


def _has_object(cursor: pyodbc.Cursor, name: str) -> bool:
    cursor.execute("SELECT CASE WHEN OBJECT_ID(?) IS NULL THEN 0 ELSE 1 END", name)
    row = cursor.fetchone()
    return bool(row and row[0])


def _has_column(cursor: pyodbc.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute("SELECT CASE WHEN COL_LENGTH(?, ?) IS NULL THEN 0 ELSE 1 END", table_name, column_name)
    row = cursor.fetchone()
    return bool(row and row[0])


def _use_legacy_schema(cursor: pyodbc.Cursor) -> bool:
    return _has_object(cursor, "cat.tipo_proceso") and not _has_object(cursor, "cat.TipoProceso")


def _ensure_period_designation_table(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID('pp.designacion_periodo_responsable', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.designacion_periodo_responsable (
                designacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo_proceso_id tinyint NOT NULL,
                codigo_periodo numeric(18,0) NOT NULL,
                codigo_periodo_origen numeric(18,0) NULL,
                codigo_docente decimal(18,0) NOT NULL,
                cedula_responsable varchar(50) NULL,
                nombre_responsable nvarchar(220) NOT NULL,
                correo_responsable nvarchar(180) NULL,
                rol_responsable nvarchar(180) NULL,
                cumple_requisitos bit NOT NULL CONSTRAINT DF_designacion_periodo_cumple DEFAULT (0),
                activo bit NOT NULL CONSTRAINT DF_designacion_periodo_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                periodo_origen_snapshot nvarchar(220) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_designacion_periodo_fecha DEFAULT (sysdatetime()),
                usuario_modifica varchar(100) NULL,
                fecha_modifica datetime2(3) NULL
            );
        END
        IF OBJECT_ID('pp.designacion_periodo_estudiante', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.designacion_periodo_estudiante (
                designacion_estudiante_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                designacion_id bigint NOT NULL,
                expediente_id bigint NULL,
                codigo_estud decimal(18,0) NOT NULL,
                cedula_est varchar(50) NULL,
                codigo_periodo_origen numeric(18,0) NULL,
                estudiante_snapshot nvarchar(220) NULL,
                cod_anio_basica decimal(18,0) NULL,
                carrera_snapshot nvarchar(250) NULL,
                cumple_requisitos bit NOT NULL CONSTRAINT DF_designacion_est_cumple DEFAULT (1),
                activo bit NOT NULL CONSTRAINT DF_designacion_est_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                periodo_origen_snapshot nvarchar(220) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_designacion_est_fecha DEFAULT (sysdatetime())
            );
        END
        IF OBJECT_ID('pp.autorizacion_practica_estudiante', 'U') IS NULL
        BEGIN
            CREATE TABLE pp.autorizacion_practica_estudiante (
                autorizacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo_proceso_id tinyint NOT NULL,
                codigo_estud decimal(18,0) NOT NULL,
                codigo_periodo numeric(18,0) NOT NULL,
                nombre_archivo nvarchar(260) NOT NULL,
                ruta_archivo nvarchar(500) NOT NULL,
                extension varchar(20) NULL,
                mime_type nvarchar(120) NULL,
                hash_archivo varchar(64) NULL,
                tamanio_bytes bigint NULL,
                activo bit NOT NULL CONSTRAINT DF_autorizacion_practica_activo DEFAULT (1),
                observacion nvarchar(500) NULL,
                usuario_registro varchar(100) NULL,
                fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_autorizacion_practica_fecha DEFAULT (sysdatetime())
            );
        END
        """
    )
    for table_name, column_name, definition in [
        ("pp.designacion_periodo_responsable", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.designacion_periodo_responsable", "periodo_origen_snapshot", "nvarchar(220) NULL"),
        ("pp.designacion_periodo_estudiante", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.designacion_periodo_estudiante", "periodo_origen_snapshot", "nvarchar(220) NULL"),
        ("pp.expediente_practica", "codigo_periodo_origen", "numeric(18,0) NULL"),
        ("pp.expediente_practica", "periodo_origen_snapshot", "nvarchar(220) NULL"),
    ]:
        if _has_object(cursor, table_name) and not _has_column(cursor, table_name, column_name):
            cursor.execute(f"ALTER TABLE {table_name} ADD {column_name} {definition}")


def _tipo_proceso_id(cursor: pyodbc.Cursor, process_code: str) -> int:
    cursor.execute("SELECT tipo_proceso_id FROM cat.tipo_proceso WHERE codigo = ? AND activo = 1", process_code)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tipo de proceso no encontrado.")
    return int(row.tipo_proceso_id)


def _db_error(exc: Exception, action: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{action}. Revisa que INTEC_PRACTICAS_PREPROFESIONALES exista y que B_NAME2/DB_HOST2 sean correctos. Detalle: {exc}",
    )


def _process_code(value: str) -> str:
    code = _clean(value).upper()
    if code not in PROCESS_LABELS:
        raise HTTPException(status_code=400, detail="Tipo de proceso no válido. Usa PPF o VIN.")
    return code


def _student_code(current_user: SessionUser, requested_code: int | None = None) -> int:
    if current_user.rol == "ESTUDIANTE":
        if current_user.codigo_estud is None:
            raise HTTPException(status_code=403, detail="La sesión no tiene estudiante vinculado.")
        return int(current_user.codigo_estud)
    if requested_code is None:
        raise HTTPException(status_code=400, detail="Indica el código de estudiante.")
    return requested_code


def _safe_filename(value: str, fallback: str = "documento.pdf") -> str:
    text = Path(value or fallback).name
    cleaned = "".join(char if char.isalnum() or char in "._- " else "_" for char in text).strip(" .")
    return cleaned[:160] or fallback


def _latest_carta_select(prefix: str = "e") -> str:
    return f"""
        OUTER APPLY (
            SELECT TOP 1
                dp.documento_id,
                ed.codigo AS estado_codigo,
                ed.nombre AS estado_nombre,
                dp.nombre_archivo,
                dp.ruta_archivo,
                dp.fecha_registro,
                dp.firmado,
                dp.validado
            FROM pp.documento_practica dp
            INNER JOIN cat.tipo_documento_practica td ON td.tipo_documento_id = dp.tipo_documento_id
            INNER JOIN cat.estado_documento ed ON ed.estado_documento_id = dp.estado_documento_id
            WHERE dp.expediente_id = {prefix}.expediente_id
              AND td.codigo = 'CARTA_COMPROMISO'
            ORDER BY dp.fecha_registro DESC, dp.documento_id DESC
        ) carta
    """


def _latest_certificado_select(prefix: str = "e") -> str:
    return f"""
        OUTER APPLY (
            SELECT TOP 1
                dp.documento_id,
                ed.codigo AS estado_codigo,
                ed.nombre AS estado_nombre,
                dp.nombre_archivo,
                dp.ruta_archivo,
                dp.fecha_registro,
                dp.firmado,
                dp.validado
            FROM pp.documento_practica dp
            INNER JOIN cat.tipo_documento_practica td ON td.tipo_documento_id = dp.tipo_documento_id
            INNER JOIN cat.estado_documento ed ON ed.estado_documento_id = dp.estado_documento_id
            WHERE dp.expediente_id = {prefix}.expediente_id
              AND td.codigo = 'OTRO'
              AND dp.observacion LIKE 'CERTIFICADO_PREPROFESIONALES%'
            ORDER BY dp.fecha_registro DESC, dp.documento_id DESC
        ) certificado
    """


def _fetch_legacy_expediente(cursor: pyodbc.Cursor, expediente_id: int) -> Any:
    cursor.execute(
        """
        SELECT TOP 1
            e.expediente_id,
            e.codigo_expediente,
            e.codigo_estud,
            e.cedula_est,
            e.estudiante_snapshot,
            e.cod_anio_basica,
            e.carrera_snapshot,
            e.codigo_periodo,
            e.periodo_snapshot,
            e.semestre,
            e.semestre_numero,
            tp.codigo AS tipo_proceso_codigo,
            tp.nombre AS tipo_proceso
        FROM pp.expediente_practica e
        INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
        WHERE e.expediente_id = ?
        """,
        expediente_id,
    )
    return cursor.fetchone()


def _register_responsable_for_expediente(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    codigo_docente: Any,
    nombre_responsable: str,
    cedula_responsable: str | None,
    correo_responsable: str | None,
    rol_responsable: str | None,
    usuario: str,
    observacion: str,
) -> int | None:
    cursor.execute(
        """
        EXEC pp.sp_registrar_responsable_proceso
            @expediente_id = ?,
            @tipo_responsable_codigo = ?,
            @tipo_referencia = ?,
            @codigo_referencia = ?,
            @cedula_ruc = ?,
            @nombres = ?,
            @correo = ?,
            @telefono = ?,
            @cargo = ?,
            @institucion = ?,
            @direccion = ?,
            @fecha_inicio = NULL,
            @fecha_fin = NULL,
            @principal = 1,
            @puede_validar_documentos = 1,
            @puede_aprobar = 1,
            @observacion = ?,
            @usuario_registro = ?
        """,
        expediente_id,
        "RESPONSABLE_ACADEMICO",
        "DOCENTE",
        int(codigo_docente) if codigo_docente is not None and str(codigo_docente).isdigit() else None,
        cedula_responsable,
        nombre_responsable,
        correo_responsable,
        None,
        rol_responsable or "RESPONSABLE",
        None,
        None,
        observacion,
        usuario,
    )
    row = cursor.fetchone()
    cursor.execute(
        """
        UPDATE pp.expediente_practica
        SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
            docente_tutor_snapshot = ?,
            usuario_modifica = ?,
            fecha_modifica = SYSDATETIME()
        WHERE expediente_id = ?
        """,
        codigo_docente,
        nombre_responsable,
        usuario,
        expediente_id,
    )
    return int(row.responsable_proceso_id) if row and getattr(row, "responsable_proceso_id", None) is not None else None


def _apply_period_designation_to_expediente(
    cursor: pyodbc.Cursor,
    expediente_id: int,
    tipo_proceso_id: int,
    codigo_periodo: Any,
    usuario: str,
) -> bool:
    _ensure_period_designation_table(cursor)
    cursor.execute(
        """
        SELECT TOP 1 *
        FROM pp.designacion_periodo_responsable
        WHERE tipo_proceso_id = ?
          AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
          AND activo = 1
        ORDER BY fecha_registro DESC, designacion_id DESC
        """,
        tipo_proceso_id,
        codigo_periodo,
    )
    designation = cursor.fetchone()
    if not designation:
        return False
    _register_responsable_for_expediente(
        cursor,
        expediente_id,
        designation.codigo_docente,
        _clean(designation.nombre_responsable),
        _clean(designation.cedula_responsable) or None,
        _clean(designation.correo_responsable) or None,
        _clean(designation.rol_responsable) or "RESPONSABLE",
        usuario,
        f"Designación automática periodo {codigo_periodo}",
    )
    return True


def _ensure_expediente_for_source(
    cursor: pyodbc.Cursor,
    source: Any,
    process_code: str,
    tipo_proceso_id: int,
    usuario: str,
    observacion: str | None = None,
    target_codigo_periodo: Any | None = None,
    target_periodo_nombre: str | None = None,
) -> int:
    target_period = target_codigo_periodo if target_codigo_periodo not in (None, "") else source.codigo_periodo
    target_period_name = _clean(target_periodo_nombre) or _clean(source.periodo)
    cursor.execute(
        """
        SELECT TOP 1 expediente_id
        FROM pp.expediente_practica
        WHERE tipo_proceso_id = ?
          AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
          AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
          AND cod_anio_basica = TRY_CONVERT(decimal(18,0), ?)
        ORDER BY expediente_id DESC
        """,
        tipo_proceso_id,
        target_period,
        source.codigo_estud,
        source.cod_anio_basica,
    )
    existing = cursor.fetchone()
    if existing:
        return int(existing.expediente_id)

    cursor.execute("SELECT estado_expediente_id FROM cat.estado_expediente WHERE codigo = 'BORRADOR'")
    estado_row = cursor.fetchone()
    if not estado_row:
        raise HTTPException(status_code=500, detail="Falta el estado BORRADOR para crear expediente.")
    cursor.execute("SELECT ISNULL(MAX(expediente_id), 0) + 1 FROM pp.expediente_practica WITH (UPDLOCK, HOLDLOCK)")
    next_id = int(cursor.fetchone()[0])
    code = f"{process_code}-{next_id:08d}"
    cursor.execute(
        """
        INSERT INTO pp.expediente_practica (
            codigo_expediente, codigo_estud, cedula_est, cod_anio_basica, codigo_periodo,
            codigo_periodo_origen, estudiante_snapshot, carrera_snapshot, periodo_snapshot,
            periodo_origen_snapshot, estado_expediente_id,
            tipo_proceso_id, semestre, semestre_numero, observacion, usuario_registro
        )
        OUTPUT INSERTED.expediente_id AS ExpedienteId
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        code,
        int(source.codigo_estud),
        str(source.cedula_est),
        int(source.cod_anio_basica),
        int(target_period),
        int(source.codigo_periodo),
        _clean(source.estudiante),
        _clean(source.carrera),
        target_period_name,
        _clean(source.periodo),
        int(estado_row.estado_expediente_id),
        tipo_proceso_id,
        str(source.semestre_numero or ""),
        int(source.semestre_numero or 3),
        observacion,
        usuario,
    )
    row = cursor.fetchone()
    return int(row.ExpedienteId)


def _ensure_student_owns_expediente(current_user: SessionUser, expediente: Any) -> None:
    if current_user.rol == "ESTUDIANTE" and int(expediente.codigo_estud) != int(current_user.codigo_estud or 0):
        raise HTTPException(status_code=403, detail="No puedes gestionar un expediente de otro estudiante.")


def _build_carta_compromiso_pdf(expediente: Any) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CartaTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0c1f42"),
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=1,
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "CartaBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        alignment=4,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "CartaSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4b5563"),
    )
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.7 * cm,
        title="Carta compromiso prácticas institucionales",
    )
    story: list[Any] = [
        Paragraph("INSTITUTO SUPERIOR TECNOLÓGICO INTEC", title_style),
        Paragraph("CARTA COMPROMISO DE PRÁCTICAS PREPROFESIONALES", title_style),
        Spacer(1, 0.2 * cm),
    ]
    table_data = [
        ["Expediente", _clean(expediente.codigo_expediente) or str(expediente.expediente_id)],
        ["Estudiante", _clean(expediente.estudiante_snapshot)],
        ["Cédula", _clean(expediente.cedula_est)],
        ["Carrera", _clean(expediente.carrera_snapshot)],
        ["Periodo", _clean(expediente.periodo_snapshot) or _clean(expediente.codigo_periodo)],
        ["Proceso", _clean(expediente.tipo_proceso)],
    ]
    table = Table(table_data, colWidths=[4.2 * cm, 11.0 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef8fb")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0c1f42")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#b8dce6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 0.55 * cm)])
    story.append(Paragraph(
        "Yo, estudiante identificado en el presente documento, declaro conocer y aceptar las responsabilidades "
        "académicas, administrativas y éticas asociadas al desarrollo de mis prácticas institucionales.",
        body_style,
    ))
    story.append(Paragraph(
        "Me comprometo a cumplir las actividades asignadas por la institución, empresa o proyecto receptor; "
        "mantener comunicación con el responsable designado; presentar evidencias y documentos requeridos; "
        "respetar la confidencialidad de la información a la que tenga acceso; y observar las normas internas "
        "del Instituto Superior Tecnológico INTEC.",
        body_style,
    ))
    story.append(Paragraph(
        "El incumplimiento de estas obligaciones podrá generar observaciones, suspensión del proceso o las "
        "acciones académicas que correspondan conforme a la normativa institucional vigente.",
        body_style,
    ))
    story.extend([Spacer(1, 1.3 * cm), Paragraph("Firma del estudiante: ________________________________", body_style)])
    story.append(Paragraph(f"Fecha de generación: {date.today().isoformat()}", small_style))
    doc.build(story)
    output.seek(0)
    return output.getvalue()


@router.get("/catalog")
def catalog(_: Annotated[SessionUser, Depends(_ALL_ACCESS)]) -> dict[str, Any]:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                cursor.execute(
                    """
                    SELECT
                        tipo_proceso_id AS TipoProcesoId,
                        codigo AS Codigo,
                        nombre AS Nombre,
                        descripcion AS Descripcion,
                        activo AS Activo
                    FROM cat.tipo_proceso
                    WHERE activo = 1
                    ORDER BY codigo
                    """
                )
                processes = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        td.tipo_documento_id AS TipoDocumentoId,
                        tp.codigo AS TipoProcesoCodigo,
                        td.codigo AS Codigo,
                        td.nombre AS Nombre,
                        CASE WHEN tp.codigo = 'VIN' THEN td.obligatorio_vinculacion ELSE td.obligatorio_practicas END AS EsObligatorio,
                        td.orden AS Orden
                    FROM cat.tipo_documento_practica td
                    CROSS JOIN cat.tipo_proceso tp
                    WHERE td.activo = 1
                      AND tp.activo = 1
                      AND (
                            (tp.codigo = 'PPF' AND td.aplica_practicas = 1)
                         OR (tp.codigo = 'VIN' AND td.aplica_vinculacion = 1)
                      )
                    ORDER BY tp.codigo, td.orden, td.nombre
                    """
                )
                documents = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT TOP 300
                        rp.responsable_proceso_id AS ResponsableProcesoId,
                        tp.codigo AS TipoProcesoCodigo,
                        rp.nombres AS NombreResponsable,
                        rp.cedula_ruc AS CedulaResponsable,
                        rp.correo AS CorreoResponsable,
                        trp.nombre AS RolResponsable,
                        CONVERT(varchar(50), rp.codigo_referencia) AS CodigoDocente,
                        rp.fecha_inicio AS FechaInicio,
                        rp.fecha_fin AS FechaFin,
                        rp.activo AS Activo
                    FROM pp.responsable_proceso rp
                    INNER JOIN pp.expediente_practica e ON e.expediente_id = rp.expediente_id
                    INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
                    LEFT JOIN cat.tipo_responsable_proceso trp ON trp.tipo_responsable_id = rp.tipo_responsable_id
                    WHERE rp.activo = 1
                    ORDER BY tp.codigo, rp.fecha_registro DESC
                    """
                )
                responsibles = _fetch_all(cursor)
            else:
                cursor.execute(
                    """
                    SELECT TipoProcesoId, Codigo, Nombre, Descripcion, Activo
                    FROM cat.TipoProceso
                    WHERE Activo = 1
                    ORDER BY Codigo
                    """
                )
                processes = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        td.TipoDocumentoId,
                        tp.Codigo AS TipoProcesoCodigo,
                        td.Codigo,
                        td.Nombre,
                        td.EsObligatorio,
                        td.Orden
                    FROM cat.TipoDocumento td
                    INNER JOIN cat.TipoProceso tp ON tp.TipoProcesoId = td.TipoProcesoId
                    WHERE td.Activo = 1
                    ORDER BY tp.Codigo, td.Orden, td.Nombre
                    """
                )
                documents = _fetch_all(cursor)

                cursor.execute(
                    """
                    SELECT
                        ResponsableProcesoId,
                        tp.Codigo AS TipoProcesoCodigo,
                        NombreResponsable,
                        CedulaResponsable,
                        CorreoResponsable,
                        RolResponsable,
                        CodigoDocente,
                        FechaInicio,
                        FechaFin,
                        Activo
                    FROM resp.ResponsableProceso rp
                    INNER JOIN cat.TipoProceso tp ON tp.TipoProcesoId = rp.TipoProcesoId
                    WHERE rp.Activo = 1
                    ORDER BY tp.Codigo, rp.NombreResponsable
                    """
                )
                responsibles = _fetch_all(cursor)

        return {
            "processes": processes,
            "documents": documents,
            "responsibles": responsibles,
            "defaults": [
                {"codigo": "PPF", "nombre": PROCESS_LABELS["PPF"]},
                {"codigo": "VIN", "nombre": PROCESS_LABELS["VIN"]},
            ],
        }
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo cargar el catálogo de prácticas institucionales") from exc


@router.get("/student/me")
def student_practices(
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    codigo_estud: int | None = Query(default=None),
) -> dict[str, Any]:
    student_code = _student_code(current_user, codigo_estud)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                cursor.execute(
                    """
                    SELECT TOP 100
                        codigo_estud,
                        cedula_est AS Cedula_Est,
                        estudiante AS Apellidos_nombre,
                        cod_anio_basica AS CodigoCarrera,
                        carrera AS Carrera,
                        codigo_periodo AS CodigoPeriodo,
                        periodo AS NombrePeriodo,
                        tipo_proceso_codigo AS TipoProcesoCodigo,
                        tipo_proceso AS TipoProceso,
                        semestre_numero AS SemestreMaximo,
                        elegible AS EsElegible
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE codigo_estud = ?
                    ORDER BY codigo_periodo DESC, cod_anio_basica, tipo_proceso_codigo
                    """,
                    student_code,
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP 100 *
                    FROM integ.vw_estudiantes_elegibles
                    WHERE codigo_estud = ?
                    ORDER BY CodigoPeriodo DESC, CodigoCarrera, TipoProcesoCodigo
                    """,
                    student_code,
                )
            eligibility = _fetch_all(cursor)

            if _use_legacy_schema(cursor):
                cursor.execute(
                    f"""
                    SELECT TOP 100
                        v.expediente_id AS ExpedienteId,
                        v.codigo_expediente AS CodigoExpediente,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.codigo_estud AS CodigoEstud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante_snapshot AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera_snapshot AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        TRY_CONVERT(varchar(50), v.cod_docente_tutor) AS CodigoDocenteTutor,
                        v.docente_tutor_snapshot AS DocenteTutor,
                        v.estado_codigo AS EstadoCodigo,
                        v.estado_expediente AS EstadoExpediente,
                        v.responsable_proceso_id AS ResponsableProcesoId,
                        v.responsable_principal AS NombreResponsable,
                        v.responsable_correo AS CorreoResponsable,
                        v.fecha_registro AS FechaCreacion,
                        carta.documento_id AS CartaCompromisoDocumentoId,
                        carta.estado_codigo AS CartaCompromisoEstadoCodigo,
                        carta.estado_nombre AS CartaCompromisoEstado,
                        carta.nombre_archivo AS CartaCompromisoArchivo,
                        carta.ruta_archivo AS CartaCompromisoUrl,
                        carta.fecha_registro AS CartaCompromisoFecha,
                        carta.firmado AS CartaCompromisoFirmado,
                        carta.validado AS CartaCompromisoValidado,
                        certificado.documento_id AS CertificadoDocumentoId,
                        certificado.estado_codigo AS CertificadoEstadoCodigo,
                        certificado.estado_nombre AS CertificadoEstado,
                        certificado.nombre_archivo AS CertificadoArchivo,
                        certificado.ruta_archivo AS CertificadoUrl,
                        certificado.fecha_registro AS CertificadoFecha,
                        certificado.firmado AS CertificadoFirmado,
                        certificado.validado AS CertificadoValidado
                    FROM pp.vw_admin_expedientes_control v
                    {_latest_carta_select("v")}
                    {_latest_certificado_select("v")}
                    WHERE v.codigo_estud = ?
                    ORDER BY v.fecha_registro DESC
                    """,
                    student_code,
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP 100 *
                    FROM exp.vw_expediente_resumen
                    WHERE CodigoEstud = ?
                    ORDER BY FechaCreacion DESC
                    """,
                    student_code,
                )
            expedientes = _fetch_all(cursor)

        return {"codigo_estud": student_code, "eligibility": eligibility, "expedientes": expedientes}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar prácticas institucionales del estudiante") from exc


@router.post("/student/expedientes")
def create_student_expediente(
    payload: CreateExpedientePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process_code = _process_code(payload.tipo_proceso_codigo)
    student_code = _student_code(current_user, payload.codigo_estud)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                cursor.execute(
                    """
                    SELECT TOP 1 *
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE codigo_estud = ?
                      AND tipo_proceso_codigo = ?
                      AND (? IS NULL OR CONVERT(varchar(50), cod_anio_basica) = ?)
                      AND (? IS NULL OR CONVERT(varchar(50), codigo_periodo) = ?)
                    ORDER BY codigo_periodo DESC
                    """,
                    student_code,
                    process_code,
                    payload.codigo_carrera,
                    payload.codigo_carrera,
                    payload.codigo_periodo,
                    payload.codigo_periodo,
                )
                source = cursor.fetchone()
                if not source:
                    raise HTTPException(status_code=404, detail="No se encontró matrícula elegible para crear el expediente.")
                if not bool(source.elegible):
                    raise HTTPException(status_code=400, detail=f"El estudiante no es elegible: {source.motivo_elegibilidad}")
                tipo_proceso_id = _tipo_proceso_id(cursor, process_code)
                cursor.execute("SELECT estado_expediente_id FROM cat.estado_expediente WHERE codigo = 'BORRADOR'")
                estado_row = cursor.fetchone()
                if not estado_row:
                    raise HTTPException(status_code=500, detail="Faltan catálogos base de prácticas.")
                cursor.execute("SELECT ISNULL(MAX(expediente_id), 0) + 1 FROM pp.expediente_practica WITH (UPDLOCK, HOLDLOCK)")
                next_id = int(cursor.fetchone()[0])
                code = f"{process_code}-{next_id:08d}"
                cursor.execute(
                    """
                    INSERT INTO pp.expediente_practica (
                        codigo_expediente, codigo_estud, cedula_est, cod_anio_basica, codigo_periodo,
                        estudiante_snapshot, carrera_snapshot, periodo_snapshot, estado_expediente_id,
                        tipo_proceso_id, semestre, semestre_numero, observacion, usuario_registro
                    )
                    OUTPUT INSERTED.expediente_id AS ExpedienteId, INSERTED.codigo_expediente AS CodigoExpediente
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    code,
                    int(source.codigo_estud),
                    str(source.cedula_est),
                    int(source.cod_anio_basica),
                    int(source.codigo_periodo),
                    _clean(source.estudiante),
                    _clean(source.carrera),
                    _clean(source.periodo),
                    int(estado_row.estado_expediente_id),
                    tipo_proceso_id,
                    str(source.semestre_numero or ""),
                    int(source.semestre_numero or 3),
                    payload.observacion,
                    current_user.login,
                )
                row = cursor.fetchone()
                response_payload = _row_dict(cursor, row) if row else {"ok": True, "message": "Expediente creado"}
                if row and getattr(row, "ExpedienteId", None) is not None:
                    assigned = _apply_period_designation_to_expediente(
                        cursor,
                        int(row.ExpedienteId),
                        tipo_proceso_id,
                        source.codigo_periodo,
                        current_user.login,
                    )
                    response_payload["responsable_periodo_asignado"] = assigned
            else:
                cursor.execute(
                    """
                    EXEC exp.sp_crear_expediente
                        @TipoProcesoCodigo = ?,
                        @CodigoEstud = ?,
                        @CodigoCarrera = ?,
                        @CodigoPeriodo = ?,
                        @UsuarioCreacion = ?,
                        @ObservacionGeneral = ?
                    """,
                    process_code,
                    student_code,
                    payload.codigo_carrera,
                    payload.codigo_periodo,
                    current_user.login,
                    payload.observacion,
                )
                row = cursor.fetchone()
                response_payload = _row_dict(cursor, row) if row else {"ok": True, "message": "Expediente creado"}
            conn.commit()
        return response_payload
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo crear el expediente") from exc


@router.get("/student/expedientes/{expediente_id}/carta-compromiso.pdf")
def download_carta_compromiso(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
) -> StreamingResponse:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La generación de carta está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_student_owns_expediente(current_user, expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="La carta compromiso aplica solo para prácticas preprofesionales.")
            content = _build_carta_compromiso_pdf(expediente)
        filename = _safe_filename(f"carta_compromiso_{expediente.codigo_expediente or expediente_id}.pdf")
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo generar la carta compromiso") from exc


@router.post("/student/expedientes/{expediente_id}/carta-compromiso")
async def upload_carta_compromiso(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    original_name = _safe_filename(file.filename or "carta_compromiso.pdf")
    extension = Path(original_name).suffix.lower()
    if extension != ".pdf":
        raise HTTPException(status_code=400, detail="Sube la carta compromiso firmada en formato PDF.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La carga de carta está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_student_owns_expediente(current_user, expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="La carta compromiso aplica solo para prácticas preprofesionales.")

            safe_code = _safe_filename(str(expediente.codigo_expediente or expediente_id), str(expediente_id))
            target_dir = _UPLOAD_ROOT / safe_code / "carta-compromiso"
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"carta_compromiso_firmada_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/{safe_code}/carta-compromiso/{target_name}"

            cursor.execute(
                """
                EXEC pp.sp_registrar_documento
                    @expediente_id = ?,
                    @tipo_documento_codigo = ?,
                    @nombre_archivo = ?,
                    @ruta_archivo = ?,
                    @extension = ?,
                    @mime_type = ?,
                    @hash_archivo = ?,
                    @tamanio_bytes = ?,
                    @numero_paginas = NULL,
                    @fecha_documento = NULL,
                    @firmado = 1,
                    @validado = 0,
                    @observacion = ?,
                    @usuario_registro = ?
                """,
                expediente_id,
                "CARTA_COMPROMISO",
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or "application/pdf",
                digest,
                len(content),
                "Carta compromiso firmada cargada por el estudiante.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Carta compromiso subida correctamente.",
            "documento_id": getattr(row, "documento_id", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir la carta compromiso") from exc


@router.post("/student/expedientes/{expediente_id}/certificado")
async def upload_certificado_preprofesional(
    expediente_id: int,
    current_user: Annotated[SessionUser, Depends(_STUDENT_ACCESS)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    original_name = _safe_filename(file.filename or "certificado_practicas.pdf")
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Sube el certificado en PDF, JPG o PNG.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La carga de certificado está disponible para la estructura actual de prácticas.")
            expediente = _fetch_legacy_expediente(cursor, expediente_id)
            if not expediente:
                raise HTTPException(status_code=404, detail="Expediente no encontrado.")
            _ensure_student_owns_expediente(current_user, expediente)
            if _clean(expediente.tipo_proceso_codigo).upper() != "PPF":
                raise HTTPException(status_code=400, detail="El certificado aplica solo para prácticas preprofesionales.")

            safe_code = _safe_filename(str(expediente.codigo_expediente or expediente_id), str(expediente_id))
            target_dir = _UPLOAD_ROOT / safe_code / "certificados"
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"certificado_preprofesional_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/{safe_code}/certificados/{target_name}"

            cursor.execute(
                """
                EXEC pp.sp_registrar_documento
                    @expediente_id = ?,
                    @tipo_documento_codigo = ?,
                    @nombre_archivo = ?,
                    @ruta_archivo = ?,
                    @extension = ?,
                    @mime_type = ?,
                    @hash_archivo = ?,
                    @tamanio_bytes = ?,
                    @numero_paginas = NULL,
                    @fecha_documento = NULL,
                    @firmado = 0,
                    @validado = 0,
                    @observacion = ?,
                    @usuario_registro = ?
                """,
                expediente_id,
                "OTRO",
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or ("application/pdf" if extension == ".pdf" else "image/jpeg"),
                digest,
                len(content),
                "CERTIFICADO_PREPROFESIONALES: Certificado cargado por el estudiante.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Certificado subido correctamente.",
            "documento_id": getattr(row, "documento_id", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir el certificado") from exc


@router.get("/admin/expedientes")
def admin_expedientes(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="", max_length=10),
    search: str = Query(default="", max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    params: list[Any] = []
    where = ["1 = 1"]
    process = _clean(tipo_proceso).upper()
    if process:
        _process_code(process)
        where.append("TipoProcesoCodigo = ?")
        params.append(process)
    term = f"%{_clean(search)}%"
    if search.strip():
        where.append(
            "(CodigoExpediente LIKE ? OR Cedula_Est LIKE ? OR Apellidos_nombre LIKE ? OR CodigoCarrera LIKE ? OR CodigoPeriodo LIKE ?)"
        )
        params.extend([term, term, term, term, term])

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                legacy_where = [clause
                    .replace("TipoProcesoCodigo", "v.tipo_proceso_codigo")
                    .replace("CodigoExpediente", "v.codigo_expediente")
                    .replace("Cedula_Est", "v.cedula_est")
                    .replace("Apellidos_nombre", "v.estudiante_snapshot")
                    .replace("CodigoCarrera", "CONVERT(varchar(50), v.cod_anio_basica)")
                    .replace("CodigoPeriodo", "CONVERT(varchar(50), v.codigo_periodo)")
                    for clause in where
                ]
                cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        v.expediente_id AS ExpedienteId,
                        v.codigo_expediente AS CodigoExpediente,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.codigo_estud AS CodigoEstud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante_snapshot AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera_snapshot AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        TRY_CONVERT(varchar(50), v.cod_docente_tutor) AS CodigoDocenteTutor,
                        v.docente_tutor_snapshot AS DocenteTutor,
                        v.estado_codigo AS EstadoCodigo,
                        v.estado_expediente AS EstadoExpediente,
                        v.responsable_proceso_id AS ResponsableProcesoId,
                        v.responsable_principal AS NombreResponsable,
                        v.responsable_correo AS CorreoResponsable,
                        v.fecha_registro AS FechaCreacion,
                        carta.documento_id AS CartaCompromisoDocumentoId,
                        carta.estado_codigo AS CartaCompromisoEstadoCodigo,
                        carta.estado_nombre AS CartaCompromisoEstado,
                        carta.nombre_archivo AS CartaCompromisoArchivo,
                        carta.ruta_archivo AS CartaCompromisoUrl,
                        carta.fecha_registro AS CartaCompromisoFecha,
                        carta.firmado AS CartaCompromisoFirmado,
                        carta.validado AS CartaCompromisoValidado,
                        certificado.documento_id AS CertificadoDocumentoId,
                        certificado.estado_codigo AS CertificadoEstadoCodigo,
                        certificado.estado_nombre AS CertificadoEstado,
                        certificado.nombre_archivo AS CertificadoArchivo,
                        certificado.ruta_archivo AS CertificadoUrl,
                        certificado.fecha_registro AS CertificadoFecha,
                        certificado.firmado AS CertificadoFirmado,
                        certificado.validado AS CertificadoValidado
                    FROM pp.vw_admin_expedientes_control v
                    {_latest_carta_select("v")}
                    {_latest_certificado_select("v")}
                    WHERE {' AND '.join(legacy_where)}
                    ORDER BY v.fecha_registro DESC
                    """,
                    *params,
                )
            else:
                cursor.execute(
                    f"""
                    SELECT TOP ({limit}) *
                    FROM exp.vw_expediente_resumen
                    WHERE {' AND '.join(where)}
                    ORDER BY FechaCreacion DESC
                    """,
                    *params,
                )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar expedientes") from exc


@router.get("/admin/elegibles")
def admin_eligible_students(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
    search: str = Query(default="", max_length=100),
    codigo_periodo: str = Query(default="", max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    term = f"%{_clean(search)}%"
    period = _clean(codigo_periodo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                _ensure_period_designation_table(cursor)
                cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        v.codigo_estud,
                        v.cedula_est AS Cedula_Est,
                        v.estudiante AS Apellidos_nombre,
                        v.cod_anio_basica AS CodigoCarrera,
                        v.carrera AS Carrera,
                        v.codigo_periodo AS CodigoPeriodo,
                        v.periodo AS NombrePeriodo,
                        v.tipo_proceso_codigo AS TipoProcesoCodigo,
                        v.tipo_proceso AS TipoProceso,
                        v.semestre_numero AS SemestreMaximo,
                        v.elegible AS EsElegible,
                        v.motivo_elegibilidad AS MotivoElegibilidad,
                        CASE WHEN auth.autorizacion_id IS NULL THEN 0 ELSE 1 END AS TieneAutorizacion,
                        auth.autorizacion_id AS AutorizacionId,
                        auth.nombre_archivo AS AutorizacionArchivo,
                        auth.ruta_archivo AS AutorizacionUrl,
                        auth.fecha_registro AS AutorizacionFecha,
                        CASE WHEN v.elegible = 1 OR auth.autorizacion_id IS NOT NULL THEN 1 ELSE 0 END AS PuedeMatricular
                    FROM pp.vw_estudiantes_elegibles_proceso v
                    INNER JOIN cat.tipo_proceso tp ON tp.codigo = v.tipo_proceso_codigo
                    OUTER APPLY (
                        SELECT TOP 1 a.*
                        FROM pp.autorizacion_practica_estudiante a
                        WHERE a.tipo_proceso_id = tp.tipo_proceso_id
                          AND a.codigo_estud = TRY_CONVERT(decimal(18,0), v.codigo_estud)
                          AND a.codigo_periodo = TRY_CONVERT(numeric(18,0), v.codigo_periodo)
                          AND a.activo = 1
                        ORDER BY a.fecha_registro DESC, a.autorizacion_id DESC
                    ) auth
                    WHERE v.tipo_proceso_codigo = ?
                      AND (? = '' OR CONVERT(varchar(50), v.codigo_periodo) = ?)
                      AND (
                            ? = '%%'
                         OR v.estudiante LIKE ?
                         OR v.cedula_est LIKE ?
                         OR v.carrera LIKE ?
                         OR v.periodo LIKE ?
                         OR CONVERT(varchar(50), v.codigo_estud) LIKE ?
                      )
                    ORDER BY v.elegible DESC, v.periodo DESC, v.estudiante
                    """,
                    process,
                    period,
                    period,
                    term,
                    term,
                    term,
                    term,
                    term,
                    term,
                )
            else:
                cursor.execute(
                    f"""
                    SELECT TOP ({limit}) *
                    FROM integ.vw_estudiantes_elegibles
                    WHERE TipoProcesoCodigo = ?
                      AND EsElegible = 1
                      AND (? = '' OR CONVERT(varchar(50), CodigoPeriodo) = ?)
                      AND (
                            ? = '%%'
                         OR Apellidos_nombre LIKE ?
                         OR Cedula_Est LIKE ?
                         OR Carrera LIKE ?
                         OR NombrePeriodo LIKE ?
                         OR CONVERT(varchar(50), codigo_estud) LIKE ?
                      )
                    ORDER BY NombrePeriodo DESC, Apellidos_nombre
                    """,
                    process,
                    period,
                    period,
                    term,
                    term,
                    term,
                    term,
                    term,
                    term,
                )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar estudiantes elegibles") from exc


@router.get("/admin/periodos")
def admin_periods(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    try:
        counts: dict[str, int] = {}
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _has_object(cursor, "pp.vw_estudiantes_elegibles_proceso"):
                cursor.execute(
                    """
                    SELECT
                        CONVERT(varchar(50), codigo_periodo) AS CodigoPeriodo,
                        COUNT(DISTINCT codigo_estud) AS TotalEstudiantes
                    FROM pp.vw_estudiantes_elegibles_proceso
                    WHERE tipo_proceso_codigo = ?
                    GROUP BY codigo_periodo
                    """,
                    process,
                )
                counts = {
                    _clean(row.CodigoPeriodo): int(row.TotalEstudiantes or 0)
                    for row in cursor.fetchall()
                }
            elif _has_object(cursor, "integ.vw_estudiantes_elegibles"):
                cursor.execute(
                    f"""
                    SELECT
                        CodigoPeriodo,
                        COUNT(DISTINCT codigo_estud) AS TotalEstudiantes
                    FROM integ.vw_estudiantes_elegibles
                    WHERE TipoProcesoCodigo = ?
                    GROUP BY CodigoPeriodo
                    """,
                    process,
                )
                counts = {
                    _clean(row.CodigoPeriodo): int(row.TotalEstudiantes or 0)
                    for row in cursor.fetchall()
                }

        try:
            with get_connection() as academic_conn:
                academic_cursor = academic_conn.cursor()
                academic_cursor.execute(
                    f"""
                    SELECT TOP ({limit})
                        CONVERT(varchar(50), cod_periodo) AS CodigoPeriodo,
                        LTRIM(RTRIM(CONVERT(nvarchar(150), Detalle_Periodo))) AS NombrePeriodo,
                        LTRIM(RTRIM(CONVERT(nvarchar(80), Detalle_Reg))) AS DetalleRegistro,
                        LTRIM(RTRIM(CONVERT(nvarchar(50), Periodo))) AS PeriodoCorto,
                        LTRIM(RTRIM(CONVERT(varchar(10), Estado))) AS EstadoPeriodo,
                        Orden AS OrdenPeriodo,
                        NotaAprobar,
                        LTRIM(RTRIM(CONVERT(nvarchar(80), TipoMatricula))) AS TipoMatricula,
                        fechain AS FechaInicio,
                        fechafin AS FechaFin,
                        anio AS Anio,
                        LTRIM(RTRIM(CONVERT(nvarchar(150), estado_ed))) AS EstadoEducativo
                    FROM dbo.PERIODO
                    ORDER BY ISNULL(Orden, cod_periodo) DESC, cod_periodo DESC
                    """
                )
                items = _fetch_all(academic_cursor)
            for item in items:
                item["TotalEstudiantes"] = counts.get(_clean(item.get("CodigoPeriodo")), 0)
            return {"items": items, "total": len(items)}
        except (pyodbc.Error, RuntimeError):
            items = [
                {
                    "CodigoPeriodo": code,
                    "NombrePeriodo": code,
                    "DetalleRegistro": None,
                    "PeriodoCorto": None,
                    "TotalEstudiantes": total,
                    "EstadoPeriodo": None,
                    "OrdenPeriodo": code,
                    "NotaAprobar": None,
                    "TipoMatricula": None,
                    "FechaInicio": None,
                    "FechaFin": None,
                    "Anio": None,
                    "EstadoEducativo": None,
                }
                for code, total in sorted(counts.items(), key=lambda pair: int(pair[0]) if pair[0].isdigit() else 0, reverse=True)
            ]
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar periodos de prácticas") from exc


@router.get("/admin/designaciones-periodo")
def admin_period_designations(
    _: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                return {"items": [], "total": 0}
            _ensure_period_designation_table(cursor)
            cursor.execute(
                """
                SELECT
                    d.designacion_id AS DesignacionId,
                    tp.codigo AS TipoProcesoCodigo,
                    d.codigo_periodo AS CodigoPeriodo,
                    d.codigo_periodo_origen AS CodigoPeriodoOrigen,
                    d.codigo_docente AS CodigoDocente,
                    d.cedula_responsable AS CedulaResponsable,
                    d.nombre_responsable AS NombreResponsable,
                    d.correo_responsable AS CorreoResponsable,
                    d.rol_responsable AS RolResponsable,
                    d.cumple_requisitos AS CumpleRequisitos,
                    d.activo AS Activo,
                    d.observacion AS Observacion,
                    d.periodo_origen_snapshot AS PeriodoOrigen,
                    d.fecha_registro AS FechaRegistro
                FROM pp.designacion_periodo_responsable d
                INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = d.tipo_proceso_id
                WHERE tp.codigo = ?
                  AND d.activo = 1
                ORDER BY d.codigo_periodo DESC, d.fecha_registro DESC
                """,
                process,
            )
            items = _fetch_all(cursor)
        return {"items": items, "total": len(items)}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar designaciones por periodo") from exc


@router.post("/admin/autorizaciones")
async def upload_admin_authorization(
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
    tipo_proceso_codigo: str = Form(...),
    codigo_estud: int = Form(...),
    codigo_periodo: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso_codigo)
    original_name = _safe_filename(file.filename or "autorizacion_practicas.pdf")
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Sube la autorización en PDF, JPG o PNG.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 12 MB.")

    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La autorización está disponible para la estructura actual de prácticas.")
            _ensure_period_designation_table(cursor)
            tipo_id = _tipo_proceso_id(cursor, process)
            cursor.execute(
                """
                SELECT TOP 1 codigo_estud
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
                """,
                process,
                codigo_periodo,
                codigo_estud,
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="No se encontró el estudiante en el periodo seleccionado.")

            safe_period = _safe_filename(str(codigo_periodo), "periodo")
            safe_student = _safe_filename(str(codigo_estud), "estudiante")
            target_dir = _UPLOAD_ROOT / "autorizaciones" / process / safe_period / safe_student
            target_dir.mkdir(parents=True, exist_ok=True)
            digest = sha256(content).hexdigest()
            target_name = _safe_filename(f"autorizacion_{digest[:10]}{extension}")
            target_path = target_dir / target_name
            target_path.write_bytes(content)
            relative_url = f"/uploads/practicas/autorizaciones/{process}/{safe_period}/{safe_student}/{target_name}"

            cursor.execute(
                """
                UPDATE pp.autorizacion_practica_estudiante
                SET activo = 0
                WHERE tipo_proceso_id = ?
                  AND codigo_estud = TRY_CONVERT(decimal(18,0), ?)
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND activo = 1
                """,
                tipo_id,
                codigo_estud,
                codigo_periodo,
            )
            cursor.execute(
                """
                INSERT INTO pp.autorizacion_practica_estudiante (
                    tipo_proceso_id, codigo_estud, codigo_periodo, nombre_archivo,
                    ruta_archivo, extension, mime_type, hash_archivo, tamanio_bytes,
                    activo, observacion, usuario_registro
                )
                OUTPUT INSERTED.autorizacion_id AS AutorizacionId
                VALUES (?, ?, TRY_CONVERT(numeric(18,0), ?), ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                tipo_id,
                codigo_estud,
                codigo_periodo,
                original_name,
                relative_url,
                extension.lstrip("."),
                file.content_type or ("application/pdf" if extension == ".pdf" else "image/jpeg"),
                digest,
                len(content),
                "Autorización administrativa para habilitar prácticas antes de tercer semestre.",
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return {
            "ok": True,
            "message": "Autorización cargada. El estudiante queda habilitado para matrícula.",
            "autorizacion_id": getattr(row, "AutorizacionId", None) if row else None,
            "url": relative_url,
            "nombre_archivo": original_name,
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo subir la autorización") from exc


@router.post("/admin/designaciones-periodo")
def save_period_designation(
    payload: PeriodoResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process = _process_code(payload.tipo_proceso_codigo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                raise HTTPException(status_code=400, detail="La designación por periodo está disponible para la estructura actual de prácticas.")
            _ensure_period_designation_table(cursor)
            tipo_id = _tipo_proceso_id(cursor, process)
            source_period = payload.codigo_periodo_origen or payload.codigo_periodo
            selected_students = sorted({int(item) for item in payload.estudiantes if int(item) > 0})
            if not selected_students:
                raise HTTPException(status_code=400, detail="Selecciona al menos un estudiante para la designación.")
            cursor.execute(
                """
                SELECT TOP 1 periodo
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                """,
                process,
                payload.codigo_periodo,
            )
            target_period_row = cursor.fetchone()
            target_period_name = _clean(target_period_row.periodo) if target_period_row else payload.codigo_periodo
            cursor.execute(
                """
                SELECT TOP 1 periodo
                FROM pp.vw_estudiantes_elegibles_proceso
                WHERE tipo_proceso_codigo = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                """,
                process,
                source_period,
            )
            source_period_row = cursor.fetchone()
            source_period_name = _clean(source_period_row.periodo) if source_period_row else source_period
            cursor.execute(
                """
                UPDATE pp.designacion_periodo_responsable
                SET activo = 0,
                    usuario_modifica = ?,
                    fecha_modifica = SYSDATETIME()
                WHERE tipo_proceso_id = ?
                  AND codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND codigo_docente = TRY_CONVERT(decimal(18,0), ?)
                  AND activo = 1
                """,
                current_user.login,
                tipo_id,
                payload.codigo_periodo,
                payload.codigo_docente,
            )
            cursor.execute(
                """
                INSERT INTO pp.designacion_periodo_responsable (
                    tipo_proceso_id, codigo_periodo, codigo_periodo_origen, codigo_docente, cedula_responsable,
                    nombre_responsable, correo_responsable, rol_responsable,
                    cumple_requisitos, activo, observacion, periodo_origen_snapshot, usuario_registro
                )
                OUTPUT INSERTED.designacion_id AS DesignacionId
                VALUES (?, TRY_CONVERT(numeric(18,0), ?), TRY_CONVERT(numeric(18,0), ?), TRY_CONVERT(decimal(18,0), ?), ?, ?, ?, ?, 1, 1, ?, ?, ?)
                """,
                tipo_id,
                payload.codigo_periodo,
                source_period,
                payload.codigo_docente,
                payload.cedula_responsable,
                payload.nombre_responsable,
                payload.correo_responsable,
                "RESPONSABLE",
                f"Docente responsable de {process}. Origen {source_period}; destino {payload.codigo_periodo}",
                source_period_name,
                current_user.login,
            )
            row = cursor.fetchone()
            student_placeholders = ",".join("?" for _ in selected_students)
            cursor.execute(
                f"""
                SELECT v.*
                FROM pp.vw_estudiantes_elegibles_proceso v
                INNER JOIN cat.tipo_proceso tp ON tp.codigo = v.tipo_proceso_codigo
                OUTER APPLY (
                    SELECT TOP 1 a.autorizacion_id
                    FROM pp.autorizacion_practica_estudiante a
                    WHERE a.tipo_proceso_id = tp.tipo_proceso_id
                      AND a.codigo_estud = TRY_CONVERT(decimal(18,0), v.codigo_estud)
                      AND a.codigo_periodo = TRY_CONVERT(numeric(18,0), v.codigo_periodo)
                      AND a.activo = 1
                    ORDER BY a.fecha_registro DESC, a.autorizacion_id DESC
                ) auth
                WHERE v.tipo_proceso_codigo = ?
                  AND v.codigo_periodo = TRY_CONVERT(numeric(18,0), ?)
                  AND v.codigo_estud IN ({student_placeholders})
                  AND (v.elegible = 1 OR auth.autorizacion_id IS NOT NULL)
                """,
                process,
                source_period,
                *selected_students,
            )
            sources = cursor.fetchall()
            found_students = {int(item.codigo_estud) for item in sources}
            missing_students = [item for item in selected_students if item not in found_students]
            if missing_students:
                raise HTTPException(
                    status_code=400,
                    detail=f"Estudiantes no encontrados, no están en tercer semestre o no tienen autorización cargada: {', '.join(map(str, missing_students))}",
                )
            expediente_ids: list[int] = []
            for source in sources:
                expediente_id = _ensure_expediente_for_source(
                    cursor,
                    source,
                    process,
                    tipo_id,
                    current_user.login,
                    f"Expediente creado desde periodo origen {source_period} para matrícula en periodo {payload.codigo_periodo}",
                    payload.codigo_periodo,
                    target_period_name,
                )
                _register_responsable_for_expediente(
                    cursor,
                    expediente_id,
                    payload.codigo_docente,
                    payload.nombre_responsable,
                    payload.cedula_responsable,
                    payload.correo_responsable,
                    "RESPONSABLE",
                    current_user.login,
                    f"Designación por periodo {payload.codigo_periodo}",
                )
                expediente_ids.append(expediente_id)
                cursor.execute(
                    """
                    INSERT INTO pp.designacion_periodo_estudiante (
                        designacion_id, expediente_id, codigo_estud, cedula_est, estudiante_snapshot,
                        codigo_periodo_origen, cod_anio_basica, carrera_snapshot, cumple_requisitos, activo,
                        observacion, periodo_origen_snapshot, usuario_registro
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)
                    """,
                    getattr(row, "DesignacionId", None),
                    expediente_id,
                    int(source.codigo_estud),
                    str(source.cedula_est),
                    _clean(source.estudiante),
                    int(source.codigo_periodo),
                    int(source.cod_anio_basica),
                    _clean(source.carrera),
                    f"Asignado a docente {payload.codigo_docente}. Origen {source_period}; destino {payload.codigo_periodo}",
                    source_period_name,
                    current_user.login,
                )
            conn.commit()
        return {
            "ok": True,
            "message": "Matrícula por periodo registrada en prácticas correctamente.",
            "designacion_id": getattr(row, "DesignacionId", None) if row else None,
            "expedientes_actualizados": len(expediente_ids),
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise _db_error(exc, "No se pudo guardar la designación por periodo") from exc


@router.get("/responsable/avance")
def responsable_progress(
    current_user: Annotated[SessionUser, Depends(_RESPONSIBLE_ACCESS)],
    tipo_proceso: str = Query(default="PPF", max_length=10),
) -> dict[str, Any]:
    process = _process_code(tipo_proceso)
    is_admin = current_user.rol in {"ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR", "SOPORTE"}
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if not _use_legacy_schema(cursor):
                return {"summary": {}, "items": []}

            cursor.execute(
                """
                SELECT COUNT(*) AS total_requeridos
                FROM cat.tipo_documento_practica td
                WHERE td.activo = 1
                  AND (
                        (? = 'PPF' AND td.aplica_practicas = 1 AND td.obligatorio_practicas = 1)
                     OR (? = 'VIN' AND td.aplica_vinculacion = 1 AND td.obligatorio_vinculacion = 1)
                  )
                """,
                process,
                process,
            )
            required_count = int((cursor.fetchone() or [0])[0] or 0)

            params: list[Any] = [process]
            user_filters: list[str] = []
            if not is_admin:
                if current_user.cedula:
                    user_filters.append("rp.cedula_ruc = ?")
                    params.append(current_user.cedula)
                if current_user.email:
                    user_filters.append("rp.correo = ?")
                    params.append(current_user.email)
                if current_user.codigo_doc is not None:
                    user_filters.append("TRY_CONVERT(varchar(50), rp.codigo_referencia) = ?")
                    params.append(str(current_user.codigo_doc))
                if not user_filters:
                    return {
                        "summary": {
                            "tipo_proceso": process,
                            "expedientes": 0,
                            "avance": 0,
                            "documentos_requeridos": required_count,
                            "documentos_cargados": 0,
                            "documentos_validados": 0,
                            "documentos_pendientes": 0,
                        },
                        "items": [],
                    }

            where_user = "" if is_admin else f"AND ({' OR '.join(user_filters)})"
            cursor.execute(
                f"""
                SELECT
                    v.expediente_id AS ExpedienteId,
                    v.codigo_expediente AS CodigoExpediente,
                    v.cedula_est AS Cedula_Est,
                    v.estudiante_snapshot AS Apellidos_nombre,
                    v.carrera_snapshot AS Carrera,
                    v.codigo_periodo AS CodigoPeriodo,
                    v.periodo_snapshot AS Periodo,
                    v.estado_expediente AS EstadoExpediente,
                    v.responsable_principal AS NombreResponsable,
                    ISNULL(v.total_documentos, 0) AS TotalDocumentos,
                    ISNULL(v.documentos_firmados, 0) AS DocumentosFirmados,
                    ISNULL(v.documentos_validados, 0) AS DocumentosValidados,
                    CASE
                        WHEN ? > ISNULL(v.documentos_validados, 0)
                        THEN ? - ISNULL(v.documentos_validados, 0)
                        ELSE 0
                    END AS DocumentosPendientes,
                    carta.estado_nombre AS CartaCompromisoEstado,
                    certificado.estado_nombre AS CertificadoEstado
                FROM pp.vw_admin_expedientes_control v
                INNER JOIN pp.responsable_proceso rp ON rp.responsable_proceso_id = v.responsable_proceso_id
                {_latest_carta_select("v")}
                {_latest_certificado_select("v")}
                WHERE v.tipo_proceso_codigo = ?
                  AND rp.activo = 1
                  {where_user}
                ORDER BY v.periodo_snapshot DESC, v.estudiante_snapshot
                """,
                required_count,
                required_count,
                *params,
            )
            items = _fetch_all(cursor)

        for item in items:
            validados = int(item.get("DocumentosValidados") or 0)
            item["DocumentosRequeridos"] = required_count
            item["Avance"] = round((validados / max(required_count, 1)) * 100, 2)

        total_required = required_count * len(items)
        total_validated = sum(int(item.get("DocumentosValidados") or 0) for item in items)
        total_loaded = sum(int(item.get("TotalDocumentos") or 0) for item in items)
        total_pending = max(total_required - total_validated, 0)
        summary = {
            "tipo_proceso": process,
            "expedientes": len(items),
            "avance": round((total_validated / max(total_required, 1)) * 100, 2),
            "documentos_requeridos": total_required,
            "documentos_cargados": total_loaded,
            "documentos_validados": total_validated,
            "documentos_pendientes": total_pending,
        }
        return {"summary": summary, "items": items}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo consultar el avance del responsable") from exc


@router.post("/admin/responsables")
def create_responsable(
    payload: ResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    process_code = _process_code(payload.tipo_proceso_codigo)
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                if not payload.expediente_id:
                    raise HTTPException(status_code=400, detail="Selecciona un expediente para designar el responsable.")
                cursor.execute(
                    """
                    EXEC pp.sp_registrar_responsable_proceso
                        @expediente_id = ?,
                        @tipo_responsable_codigo = ?,
                        @tipo_referencia = ?,
                        @codigo_referencia = ?,
                        @cedula_ruc = ?,
                        @nombres = ?,
                        @correo = ?,
                        @telefono = ?,
                        @cargo = ?,
                        @institucion = ?,
                        @direccion = ?,
                        @fecha_inicio = NULL,
                        @fecha_fin = NULL,
                        @principal = 1,
                        @puede_validar_documentos = 1,
                        @puede_aprobar = 1,
                        @observacion = ?,
                        @usuario_registro = ?
                    """,
                    payload.expediente_id,
                    "RESPONSABLE_ACADEMICO",
                    "DOCENTE" if payload.codigo_docente else "USUARIO",
                    int(payload.codigo_docente) if payload.codigo_docente and payload.codigo_docente.isdigit() else None,
                    payload.cedula_responsable,
                    payload.nombre_responsable,
                    payload.correo_responsable,
                    None,
                    payload.rol_responsable,
                    None,
                    None,
                    f"Designación {process_code}",
                    current_user.login,
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    UPDATE pp.expediente_practica
                    SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
                        docente_tutor_snapshot = ?,
                        usuario_modifica = ?,
                        fecha_modifica = SYSDATETIME()
                    WHERE expediente_id = ?
                    """,
                    payload.codigo_docente,
                    payload.nombre_responsable,
                    current_user.login,
                    payload.expediente_id,
                )
                conn.commit()
                return _row_dict(cursor, row) if row else {"message": "Responsable designado correctamente."}

            cursor.execute("SELECT TipoProcesoId FROM cat.TipoProceso WHERE Codigo = ? AND Activo = 1", process_code)
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Tipo de proceso no encontrado")
            tipo_proceso_id = int(row.TipoProcesoId)
            cursor.execute(
                """
                INSERT INTO resp.ResponsableProceso
                    (TipoProcesoId, CodigoDocente, CedulaResponsable, NombreResponsable, CorreoResponsable, RolResponsable)
                OUTPUT INSERTED.ResponsableProcesoId
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                tipo_proceso_id,
                payload.codigo_docente,
                payload.cedula_responsable,
                payload.nombre_responsable,
                payload.correo_responsable,
                payload.rol_responsable,
            )
            responsable_id = int(cursor.fetchone().ResponsableProcesoId)
            conn.commit()
        return {
            "responsable_proceso_id": responsable_id,
            "message": f"Responsable registrado por {current_user.login}.",
        }
    except HTTPException:
        raise
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo registrar el responsable") from exc


@router.post("/admin/expedientes/{expediente_id}/responsable")
def assign_responsable(
    expediente_id: int,
    payload: AssignResponsablePayload,
    current_user: Annotated[SessionUser, Depends(_ADMIN_ACCESS)],
) -> dict[str, Any]:
    try:
        with get_practices_connection() as conn:
            cursor = conn.cursor()
            if _use_legacy_schema(cursor):
                cursor.execute(
                    """
                    SELECT TOP 1
                        COALESCE(trp.codigo, 'RESPONSABLE_ACADEMICO') AS tipo_responsable_codigo,
                        rp.tipo_referencia,
                        rp.codigo_referencia,
                        rp.cedula_ruc,
                        rp.nombres,
                        rp.correo,
                        rp.telefono,
                        rp.cargo,
                        rp.institucion,
                        rp.direccion
                    FROM pp.responsable_proceso rp
                    LEFT JOIN cat.tipo_responsable_proceso trp ON trp.tipo_responsable_id = rp.tipo_responsable_id
                    WHERE rp.responsable_proceso_id = ?
                      AND rp.activo = 1
                    """,
                    payload.responsable_proceso_id,
                )
                responsable = cursor.fetchone()
                if not responsable:
                    raise HTTPException(status_code=404, detail="Responsable no encontrado o inactivo.")

                cursor.execute(
                    """
                    EXEC pp.sp_registrar_responsable_proceso
                        @expediente_id = ?,
                        @tipo_responsable_codigo = ?,
                        @tipo_referencia = ?,
                        @codigo_referencia = ?,
                        @cedula_ruc = ?,
                        @nombres = ?,
                        @correo = ?,
                        @telefono = ?,
                        @cargo = ?,
                        @institucion = ?,
                        @direccion = ?,
                        @fecha_inicio = NULL,
                        @fecha_fin = NULL,
                        @principal = 1,
                        @puede_validar_documentos = 1,
                        @puede_aprobar = 1,
                        @observacion = ?,
                        @usuario_registro = ?
                    """,
                    expediente_id,
                    responsable.tipo_responsable_codigo,
                    responsable.tipo_referencia,
                    responsable.codigo_referencia,
                    responsable.cedula_ruc,
                    responsable.nombres,
                    responsable.correo,
                    responsable.telefono,
                    responsable.cargo,
                    responsable.institucion,
                    responsable.direccion,
                    "Asignación de responsable existente",
                    current_user.login,
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    UPDATE pp.expediente_practica
                    SET cod_docente_tutor = TRY_CONVERT(decimal(18, 0), ?),
                        docente_tutor_snapshot = ?,
                        usuario_modifica = ?,
                        fecha_modifica = SYSDATETIME()
                    WHERE expediente_id = ?
                    """,
                    responsable.codigo_referencia,
                    responsable.nombres,
                    current_user.login,
                    expediente_id,
                )
                conn.commit()
                return _row_dict(cursor, row) if row else {"message": "Responsable asignado correctamente."}

            cursor.execute(
                """
                EXEC exp.sp_asignar_responsable_proceso
                    @ExpedienteId = ?,
                    @ResponsableProcesoId = ?,
                    @UsuarioActualizacion = ?
                """,
                expediente_id,
                payload.responsable_proceso_id,
                current_user.login,
            )
            row = cursor.fetchone()
            conn.commit()
        return _row_dict(cursor, row) if row else {"message": "Responsable asignado correctamente."}
    except (pyodbc.Error, RuntimeError) as exc:
        raise _db_error(exc, "No se pudo asignar el responsable") from exc
