from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Callable

import pyodbc

from app.services.db import (
    get_expedient_connection,
    get_finance_connection,
    get_graph_database_connection,
    get_integration_control_connection,
)


@dataclass(frozen=True)
class ComplementStepResult:
    module: str
    name: str
    ok: bool
    rows: int = 0
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "ok": self.ok,
            "rows": self.rows,
            "detail": self.detail,
        }


def _run_step(
    module: str,
    name: str,
    operation: Callable[[], int],
) -> ComplementStepResult:
    try:
        return ComplementStepResult(module, name, True, max(operation(), 0), "Sincronizado")
    except (pyodbc.Error, RuntimeError, ValueError) as exc:
        return ComplementStepResult(module, name, False, 0, str(exc)[:3900])


def _sync_expedient_preinscription(data: dict[str, Any]) -> int:
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE core.Persona AS target
            USING (SELECT ? AS NumeroIdentificacion) AS source
               ON target.NumeroIdentificacion = source.NumeroIdentificacion
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(?, target.CodigoEstud),
                ApellidosNombres = ?, CorreoPersonal = ?, Celular = ?,
                FuenteUltimaActualizacion = 'INTECBDD_PREINSCRIPCION',
                FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (NumeroIdentificacion, CodigoEstud, ApellidosNombres, CorreoPersonal,
                 Celular, FuenteUltimaActualizacion)
            VALUES (?, ?, ?, ?, ?, 'INTECBDD_PREINSCRIPCION');
            """,
            data["cedula"], data.get("codigo_estud"), data.get("nombre"),
            data.get("correo"), data.get("telefono"), data["cedula"],
            data.get("codigo_estud"), data.get("nombre"), data.get("correo"),
            data.get("telefono"),
        )
        cursor.execute(
            "SELECT PersonaId FROM core.Persona WHERE NumeroIdentificacion = ?",
            data["cedula"],
        )
        persona_id = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT OrigenExpedienteId FROM cat.OrigenExpediente WHERE Codigo = 'PREINSCRIPCION' AND Activo = 1"
        )
        origin_row = cursor.fetchone()
        if not origin_row:
            raise RuntimeError("No existe el origen PREINSCRIPCION en Expediente Estudiantil")
        origin_id = int(origin_row[0])
        metadata = json.dumps(
            {
                "codigo_modalidad": data.get("codigo_modalidad"),
                "codigo_jornada": data.get("codigo_jornada"),
                "codigo_asesor": data.get("codigo_asesor"),
            },
            ensure_ascii=False,
        )
        cursor.execute(
            """
            MERGE adm.InscripcionReferencia AS target
            USING (SELECT ? AS OrigenExpedienteId, ? AS OrigenId) AS source
               ON target.OrigenExpedienteId = source.OrigenExpedienteId
              AND target.OrigenId = source.OrigenId
            WHEN MATCHED THEN UPDATE SET
                PersonaId = ?, TipoOferta = 'REGULAR', CodigoEstud = ?,
                NumeroIdentificacion = ?, ApellidosNombres = ?, Correo = ?, Telefono = ?,
                CodigoCarrera = ?, CodigoPeriodo = ?, EstadoOrigen = ?,
                UrlCedula = ?, UrlTituloBachiller = ?, UrlComprobantePago = ?,
                UrlConvenioPago = ?, MetadataJson = ?, FechaSincronizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (OrigenExpedienteId, PersonaId, OrigenTabla, OrigenId, TipoOferta,
                 CodigoEstud, NumeroIdentificacion, ApellidosNombres, Correo, Telefono,
                 CodigoCarrera, CodigoPeriodo, FechaInscripcion, EstadoOrigen,
                 UrlCedula, UrlTituloBachiller, UrlComprobantePago, UrlConvenioPago,
                 MetadataJson)
            VALUES (?, ?, 'dbo.PREINSCRIPCION', ?, 'REGULAR', ?, ?, ?, ?, ?, ?, ?,
                    SYSDATETIME(), ?, ?, ?, ?, ?, ?);
            """,
            origin_id, str(data["origen_id"]), persona_id, data.get("codigo_estud"),
            data["cedula"], data.get("nombre"), data.get("correo"), data.get("telefono"),
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            data.get("estado") or "REGISTRADA", data.get("url_cedula"),
            data.get("url_titulo"), data.get("url_deposito"), data.get("url_convenio"), metadata,
            origin_id, persona_id, str(data["origen_id"]), data.get("codigo_estud"),
            data["cedula"], data.get("nombre"), data.get("correo"), data.get("telefono"),
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            data.get("estado") or "REGISTRADA", data.get("url_cedula"),
            data.get("url_titulo"), data.get("url_deposito"), data.get("url_convenio"), metadata,
        )
        cursor.execute(
            """
            SELECT InscripcionRefId FROM adm.InscripcionReferencia
            WHERE OrigenExpedienteId = ? AND OrigenId = ?
            """,
            origin_id, str(data["origen_id"]),
        )
        inscription_id = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT TipoExpedienteId FROM cat.TipoExpediente WHERE Codigo = 'REGULAR' AND Activo = 1"
        )
        type_row = cursor.fetchone()
        cursor.execute(
            "SELECT EstadoExpedienteId FROM cat.EstadoExpediente WHERE Codigo = 'DOCUMENTOS_PENDIENTES' AND Activo = 1"
        )
        status_row = cursor.fetchone()
        if not type_row or not status_row:
            raise RuntimeError("Faltan catalogos REGULAR/DOCUMENTOS_PENDIENTES en Expediente Estudiantil")
        cursor.execute(
            """
            IF NOT EXISTS (
                SELECT 1 FROM exp.ExpedienteEstudiantil
                WHERE InscripcionRefId = ? AND Activo = 1
            )
            BEGIN
                INSERT INTO exp.ExpedienteEstudiantil
                    (TipoExpedienteId, EstadoExpedienteId, PersonaId, InscripcionRefId,
                     CodigoEstud, NumeroIdentificacion, CodigoCarrera, CodigoPeriodo,
                     TipoOferta, TieneBeca, TieneComprobantePago, UsuarioApertura)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REGULAR', ?, ?, ?)
            END
            ELSE
            BEGIN
                UPDATE exp.ExpedienteEstudiantil
                   SET PersonaId = ?, CodigoEstud = ?, NumeroIdentificacion = ?,
                       CodigoCarrera = ?, CodigoPeriodo = ?, TieneBeca = ?,
                       TieneComprobantePago = ?, FechaActualizacion = SYSDATETIME(),
                       UsuarioActualizacion = ?
                 WHERE InscripcionRefId = ? AND Activo = 1
            END
            """,
            inscription_id, int(type_row[0]), int(status_row[0]), persona_id,
            inscription_id, data.get("codigo_estud"), data["cedula"],
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            bool(data.get("tiene_beca")), bool(data.get("url_deposito")), data.get("usuario") or "api",
            persona_id, data.get("codigo_estud"), data["cedula"],
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            bool(data.get("tiene_beca")), bool(data.get("url_deposito")),
            data.get("usuario") or "api", inscription_id,
        )
        conn.commit()
    return 3


def _sync_graph_student(data: dict[str, Any]) -> int:
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE core.PersonaGraphRef AS target
            USING (SELECT 'ESTUDIANTE' AS TipoPersonaCodigo, ? AS NumeroIdentificacion) AS source
               ON target.TipoPersonaCodigo = source.TipoPersonaCodigo
              AND target.NumeroIdentificacion = source.NumeroIdentificacion
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(?, target.CodigoEstud), NombreCompleto = ?,
                CorreoPersonal = ?, Telefono = ?, Celular = ?, CodigoCarrera = ?,
                CodigoPeriodo = ?, OrigenFuente = 'INTECBDD_PREINSCRIPCION',
                MetadataJson = ?, Activo = 1, FechaSincronizacion = SYSDATETIME(),
                FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (TipoPersonaCodigo, NumeroIdentificacion, CodigoEstud, NombreCompleto,
                 CorreoPersonal, Telefono, Celular, CodigoCarrera, CodigoPeriodo,
                 OrigenFuente, MetadataJson)
            VALUES ('ESTUDIANTE', ?, ?, ?, ?, ?, ?, ?, ?, 'INTECBDD_PREINSCRIPCION', ?);
            """,
            data["cedula"], data.get("codigo_estud"), data.get("nombre") or data["cedula"],
            data.get("correo"), data.get("telefono"), data.get("telefono"),
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            json.dumps({"preinscripcion_id": str(data["origen_id"])}, ensure_ascii=False),
            data["cedula"], data.get("codigo_estud"), data.get("nombre") or data["cedula"],
            data.get("correo"), data.get("telefono"), data.get("telefono"),
            str(data.get("codigo_carrera") or ""), str(data.get("codigo_periodo") or ""),
            json.dumps({"preinscripcion_id": str(data["origen_id"])}, ensure_ascii=False),
        )
        conn.commit()
    return 1


def _sync_expedient_person(data: dict[str, Any]) -> int:
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE core.Persona AS target
            USING (SELECT ? AS NumeroIdentificacion) AS source
               ON target.NumeroIdentificacion = source.NumeroIdentificacion
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(?, target.CodigoEstud), ApellidosNombres = ?,
                CorreoPersonal = ?, Telefono = ?, Celular = ?,
                FuenteUltimaActualizacion = 'INTECBDD', FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (NumeroIdentificacion, CodigoEstud, ApellidosNombres, CorreoPersonal,
                 Telefono, Celular, FuenteUltimaActualizacion)
            VALUES (?, ?, ?, ?, ?, ?, 'INTECBDD');
            """,
            data["cedula"], data.get("codigo"), data.get("nombre"), data.get("correo"),
            data.get("telefono"), data.get("movil"), data["cedula"], data.get("codigo"),
            data.get("nombre"), data.get("correo"), data.get("telefono"), data.get("movil"),
        )
        conn.commit()
    return 1


def _sync_finance_student(data: dict[str, Any]) -> int:
    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE core.Estudiante AS target
            USING (SELECT ? AS NumeroIdentificacion) AS source
               ON target.NumeroIdentificacion = source.NumeroIdentificacion
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(?, target.CodigoEstud), NombreCompleto = ?,
                Correo = ?, Telefono = ?, Movil = ?, FuenteOrigen = 'INTECBDD',
                FechaSincronizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (CodigoEstud, NumeroIdentificacion, NombreCompleto, Correo, Telefono,
                 Movil, FuenteOrigen)
            VALUES (?, ?, ?, ?, ?, ?, 'INTECBDD');
            """,
            data["cedula"], data.get("codigo"), data.get("nombre") or data["cedula"],
            data.get("correo"), data.get("telefono"), data.get("movil"),
            data.get("codigo"), data["cedula"], data.get("nombre") or data["cedula"],
            data.get("correo"), data.get("telefono"), data.get("movil"),
        )
        conn.commit()
    return 1


def _sync_graph_person(data: dict[str, Any], person_type: str) -> int:
    graph_type = "DOCENTE" if person_type == "docente" else "ESTUDIANTE"
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE core.PersonaGraphRef AS target
            USING (SELECT ? AS TipoPersonaCodigo, ? AS NumeroIdentificacion) AS source
               ON target.TipoPersonaCodigo = source.TipoPersonaCodigo
              AND target.NumeroIdentificacion = source.NumeroIdentificacion
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = CASE WHEN ? = 'ESTUDIANTE' THEN COALESCE(?, target.CodigoEstud) ELSE target.CodigoEstud END,
                CodigoDocente = CASE WHEN ? = 'DOCENTE' THEN COALESCE(?, target.CodigoDocente) ELSE target.CodigoDocente END,
                NombreCompleto = ?, CorreoPersonal = ?, Telefono = ?, Celular = ?,
                OrigenFuente = 'INTECBDD', Activo = 1,
                FechaSincronizacion = SYSDATETIME(), FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (TipoPersonaCodigo, NumeroIdentificacion, CodigoEstud, CodigoDocente,
                 NombreCompleto, CorreoPersonal, Telefono, Celular, OrigenFuente)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'INTECBDD');
            """,
            graph_type, data["cedula"], graph_type, data.get("codigo"), graph_type,
            str(data.get("codigo") or ""), data.get("nombre") or data["cedula"],
            data.get("correo"), data.get("telefono"), data.get("movil"), graph_type,
            data["cedula"], data.get("codigo") if graph_type == "ESTUDIANTE" else None,
            str(data.get("codigo") or "") if graph_type == "DOCENTE" else None,
            data.get("nombre") or data["cedula"], data.get("correo"),
            data.get("telefono"), data.get("movil"),
        )
        conn.commit()
    return 1


def _record_execution(
    event_type: str,
    user: str,
    results: list[ComplementStepResult],
) -> dict[str, Any]:
    try:
        with get_integration_control_connection() as conn:
            cursor = conn.cursor()
            errors = sum(not result.ok for result in results)
            cursor.execute(
                """
                INSERT INTO sync.Ejecucion
                    (TipoEjecucion, EstadoEjecucion, UsuarioEjecucion, HostEjecucion,
                     Aplicacion, TotalPasos, PasosCorrectos, PasosError, Resumen)
                OUTPUT INSERTED.EjecucionId
                VALUES (?, ?, ?, ?, 'INTEC_SIS_ACA_API', ?, ?, ?, ?)
                """,
                event_type[:50], "ERROR" if errors else "COMPLETADO", user[:128],
                socket.gethostname()[:128], len(results), len(results) - errors, errors,
                f"Integracion complementaria {event_type}"[:1000],
            )
            execution_id = int(cursor.fetchone()[0])
            for index, result in enumerate(results, start=1):
                cursor.execute(
                    """
                    INSERT INTO sync.EjecucionPaso
                        (EjecucionId, NumeroPaso, ModuloCodigo, NombrePaso, EstadoPaso,
                         FechaInicio, FechaFin, FilasAfectadas, Mensaje)
                    OUTPUT INSERTED.EjecucionPasoId
                    VALUES (?, ?, ?, ?, ?, SYSDATETIME(), SYSDATETIME(), ?, ?)
                    """,
                    execution_id, index, result.module, result.name[:250],
                    "COMPLETADO" if result.ok else "ERROR", result.rows, result.detail[:3900],
                )
                step_id = int(cursor.fetchone()[0])
                if not result.ok:
                    cursor.execute(
                        """
                        INSERT INTO sync.ErrorIntegracion
                            (EjecucionId, EjecucionPasoId, ModuloCodigo, ErrorMessage, UsuarioRegistro)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        execution_id, step_id, result.module, result.detail[:3900], user[:128],
                    )
            cursor.execute(
                "UPDATE sync.Ejecucion SET FechaFin = SYSDATETIME() WHERE EjecucionId = ?",
                execution_id,
            )
            conn.commit()
        return {"ok": True, "execution_id": execution_id}
    except (pyodbc.Error, RuntimeError) as exc:
        return {"ok": False, "detail": f"No se pudo registrar trazabilidad: {exc}"}


def record_complement_execution(
    event_type: str,
    user: str,
    results: list[ComplementStepResult],
) -> dict[str, Any]:
    return _record_execution(event_type, user, results)


def sync_preinscription_complements(
    data: dict[str, Any],
    finance_result: dict[str, Any],
    event_type: str = "PREINSCRIPCION",
) -> dict[str, Any]:
    results = [
        ComplementStepResult(
            "FINANZAS",
            "Sincronizar preinscripcion y beca",
            bool(finance_result.get("ok")),
            1 if finance_result.get("ok") else 0,
            str(finance_result.get("detail") or "Sincronizado"),
        ),
        _run_step("EXPEDIENTE", "Anexar expediente de preinscripcion", lambda: _sync_expedient_preinscription(data)),
        _run_step("GRAPH", "Anexar referencia del estudiante", lambda: _sync_graph_student(data)),
    ]
    trace = _record_execution(event_type, str(data.get("usuario") or "api"), results)
    return {
        "ok": all(result.ok for result in results) and bool(trace.get("ok")),
        "steps": [result.as_dict() for result in results],
        "control": trace,
    }


def sync_person_complements(data: dict[str, Any], person_type: str) -> dict[str, Any]:
    if person_type not in {"estudiante", "docente"}:
        raise ValueError("Tipo de persona complementaria no soportado")
    results: list[ComplementStepResult] = []
    if person_type == "estudiante":
        results.extend(
            [
                _run_step("EXPEDIENTE", "Actualizar persona estudiante", lambda: _sync_expedient_person(data)),
                _run_step("FINANZAS", "Actualizar referencia estudiante", lambda: _sync_finance_student(data)),
            ]
        )
    results.append(
        _run_step("GRAPH", f"Actualizar referencia {person_type}", lambda: _sync_graph_person(data, person_type))
    )
    trace = _record_execution(
        f"ACTUALIZACION_{person_type.upper()}",
        str(data.get("usuario") or "api"),
        results,
    )
    return {
        "ok": all(result.ok for result in results) and bool(trace.get("ok")),
        "steps": [result.as_dict() for result in results],
        "control": trace,
    }
