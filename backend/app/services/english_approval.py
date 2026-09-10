from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

import pyodbc

from app.services.db import get_expedient_connection, get_titulation_connection
from app.services.graph_documents import list_documents, review_document


ENGLISH_APPROVAL_DOCUMENT_TYPES: tuple[dict[str, str], ...] = (
    {
        "code": "CERTIFICADO_APROBACION_INGLES",
        "name": "Certificado de aprobación A2+",
    },
    {
        "code": "ACTA_CALIFICACIONES_INGLES",
        "name": "Acta de calificaciones de Inglés",
    },
    {
        "code": "EVIDENCIA_EXAMEN_INGLES",
        "name": "Evidencia del examen de Inglés",
    },
)
ENGLISH_APPROVAL_DOCUMENT_CODES = frozenset(
    item["code"] for item in ENGLISH_APPROVAL_DOCUMENT_TYPES
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _identification(value: Any) -> str:
    return re.sub(r"\D+", "", _clean(value))


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _english_grade(identification: str) -> dict[str, Any]:
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        if not cursor.execute("SELECT OBJECT_ID(N'ing.ExamenIngles', N'U')").fetchval():
            return {
                "found": False,
                "exam_id": None,
                "final_grade": None,
                "status": "SIN_REGISTRO",
                "approved": False,
            }
        cursor.execute(
            """
            SELECT TOP (1)
                E.ExamenInglesId, E.NotaFinal, E.Estado,
                COALESCE(E.FechaActualizacion, E.FechaCalificacion, E.FechaCreacion) AS FechaEstado
            FROM ing.ExamenIngles E
            WHERE REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(E.NumeroIdentificacion)), '-', ''), ' ', ''), '.', '') = ?
              AND E.Activo = 1
              AND UPPER(LTRIM(RTRIM(E.Nivel))) LIKE N'A2+%'
            ORDER BY
                CASE
                    WHEN UPPER(LTRIM(RTRIM(E.Estado))) = 'APROBADO'
                      OR TRY_CONVERT(decimal(4,2), E.NotaFinal) >= 7 THEN 0
                    ELSE 1
                END,
                COALESCE(E.FechaActualizacion, E.FechaCalificacion, E.FechaCreacion) DESC,
                E.ExamenInglesId DESC
            """,
            identification,
        )
        row = cursor.fetchone()
    if not row:
        return {
            "found": False,
            "exam_id": None,
            "final_grade": None,
            "status": "SIN_REGISTRO",
            "approved": False,
        }
    grade = float(row.NotaFinal) if row.NotaFinal is not None else None
    state = _clean(row.Estado).upper() or "PENDIENTE"
    return {
        "found": True,
        "exam_id": int(row.ExamenInglesId),
        "final_grade": grade,
        "status": state,
        "approved": state == "APROBADO" or bool(grade is not None and grade >= 7),
        "updated_at": _iso(row.FechaEstado),
    }


def _required_document_rows(identification: str) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in list_documents(identification):
        if _clean(row.get("TipoExpedienteGraphCodigo")).upper() != "INGLES":
            continue
        code = _clean(row.get("TipoDocumentoCodigo")).upper()
        if code not in ENGLISH_APPROVAL_DOCUMENT_CODES or row.get("DocumentoGraphId") is None:
            continue
        current = selected.get(code)
        current_key = (
            current.get("FechaActualizacion") or current.get("FechaCarga") or datetime.min,
            int(current.get("DocumentoGraphId") or 0),
        ) if current else (datetime.min, 0)
        row_key = (
            row.get("FechaActualizacion") or row.get("FechaCarga") or datetime.min,
            int(row.get("DocumentoGraphId") or 0),
        )
        if not current or row_key > current_key:
            selected[code] = row
    return selected


def english_approval_status(identification: str) -> dict[str, Any]:
    document = _identification(identification)
    if not document:
        raise ValueError("Indique una cédula válida para consultar la aprobación de Inglés.")

    rows = _required_document_rows(document)
    requirements: list[dict[str, Any]] = []
    for definition in ENGLISH_APPROVAL_DOCUMENT_TYPES:
        row = rows.get(definition["code"])
        state = _clean(row.get("EstadoDocumentoGraphCodigo") if row else "").upper()
        uploaded = bool(row) and state not in {"", "ERROR", "ELIMINADO", "EXPIRADO", "REEMPLAZADO"}
        requirements.append(
            {
                **definition,
                "document_graph_id": int(row["DocumentoGraphId"]) if row else None,
                "filename": _clean(row.get("NombreArchivo") if row else ""),
                "version": int(row.get("VersionActual") or 1) if row else None,
                "status": state or "PENDIENTE",
                "uploaded": uploaded,
                "validated": uploaded and state == "VALIDADO",
                "observed": uploaded and state == "OBSERVADO",
                "uploaded_at": _iso(row.get("FechaCarga") if row else None),
                "uploaded_by": _clean(row.get("UsuarioCarga") if row else ""),
                "reviewed_at": _iso(row.get("FechaRevision") if row else None),
                "reviewed_by": _clean(row.get("UsuarioRevision") if row else ""),
                "observation": _clean(row.get("ObservacionRevision") if row else ""),
            }
        )

    grade = _english_grade(document)
    uploaded_count = sum(1 for item in requirements if item["uploaded"])
    validated_count = sum(1 for item in requirements if item["validated"])
    observed = any(item["observed"] for item in requirements)
    all_uploaded = uploaded_count == len(ENGLISH_APPROVAL_DOCUMENT_TYPES)
    all_validated = validated_count == len(ENGLISH_APPROVAL_DOCUMENT_TYPES)
    approved = bool(grade["approved"] and all_validated)
    if approved:
        state = "APROBADO"
        message = "La nota A2+ y los tres documentos se encuentran validados."
    elif observed:
        state = "OBSERVADO"
        message = "Existe documentación observada que debe corregirse y volver a cargarse."
    elif not all_uploaded:
        state = "PENDIENTE_DOCUMENTOS"
        message = f"Falta cargar {len(ENGLISH_APPROVAL_DOCUMENT_TYPES) - uploaded_count} de 3 documentos obligatorios."
    elif not all_validated:
        state = "EN_REVISION"
        message = "Los tres documentos están cargados y pendientes de validación."
    else:
        state = "PENDIENTE_NOTA"
        message = "La documentación está validada; falta aprobar la calificación A2+."

    return {
        "identification": document,
        "status": state,
        "message": message,
        "approved": approved,
        "grade": grade,
        "documents": requirements,
        "required_count": len(ENGLISH_APPROVAL_DOCUMENT_TYPES),
        "uploaded_count": uploaded_count,
        "validated_count": validated_count,
        "all_documents_uploaded": all_uploaded,
        "all_documents_validated": all_validated,
    }


def review_english_approval_document(
    *,
    identification: str,
    document_graph_id: int,
    approved: bool,
    observation: str,
    audit_user: str,
) -> dict[str, Any]:
    document = _identification(identification)
    if not document:
        raise ValueError("La cédula del estudiante no es válida.")
    review_document(
        document_graph_id=document_graph_id,
        identification=document,
        module_code="INGLES",
        allowed_document_types=set(ENGLISH_APPROVAL_DOCUMENT_CODES),
        status_code="VALIDADO" if approved else "OBSERVADO",
        observation=observation,
        audit_user=audit_user,
    )
    status = english_approval_status(document)
    try:
        status["titulation_synced"] = sync_titulation_english_approval(
            document,
            audit_user,
            status=status,
        )
    except (RuntimeError, pyodbc.Error):
        status["titulation_synced"] = False
        status["sync_warning"] = (
            "La revisión documental se guardó, pero Titulación no pudo sincronizarse en este momento."
        )
    return status


def sync_titulation_english_approval(
    identification: str,
    audit_user: str,
    *,
    status: dict[str, Any] | None = None,
) -> bool:
    document = _identification(identification)
    if not document:
        return False
    approval = status or english_approval_status(document)
    with get_titulation_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE E
               SET InglesA2Cumple = ?, FechaActualizacion = SYSDATETIME(),
                   UsuarioActualizacion = ?
            FROM tit.ExpedienteTitulacion E
            INNER JOIN core.EstudianteRef ER
                ON ER.EstudianteRefId = E.EstudianteRefId
            WHERE REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(CONVERT(VARCHAR(30), ER.NumeroIdentificacion))), '-', ''), ' ', ''), '.', '') = ?
            """,
            1 if approval.get("approved") else 0,
            audit_user,
            document,
        )
        updated = int(cursor.rowcount or 0) > 0
        conn.commit()
        return updated
