from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys
from typing import Any

import pyodbc

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.complement_sync import ComplementStepResult, record_complement_execution
from app.services.db import (
    get_connection,
    get_expedient_connection,
    get_finance_connection,
    get_graph_database_connection,
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def source_people() -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TRY_CONVERT(bigint, codigo_estud),
                   REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), Cedula_Est))), '-', ''), ' ', ''),
                   TRY_CONVERT(nvarchar(250), Apellidos_nombre),
                   TRY_CONVERT(nvarchar(250), correo),
                   TRY_CONVERT(nvarchar(50), NumHogar),
                   TRY_CONVERT(nvarchar(50), movil)
            FROM dbo.DATOS_ESTUD
            WHERE NULLIF(REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), Cedula_Est))), '-', ''), ' ', ''), '') IS NOT NULL
            """
        )
        students_by_document = {clean(row[1]): tuple(row) for row in cursor.fetchall() if clean(row[1])}
        cursor.execute(
            """
            SELECT TRY_CONVERT(nvarchar(50), codigo_doc),
                   REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), cedula_doc))), '-', ''), ' ', ''),
                   TRY_CONVERT(nvarchar(250), apellidos_nombre),
                   COALESCE(TRY_CONVERT(nvarchar(250), correo), TRY_CONVERT(nvarchar(250), correop)),
                   TRY_CONVERT(nvarchar(50), telefono),
                   TRY_CONVERT(nvarchar(50), movil)
            FROM dbo.DATOSDOCENTE
            WHERE NULLIF(REPLACE(REPLACE(LTRIM(RTRIM(TRY_CONVERT(varchar(30), cedula_doc))), '-', ''), ' ', ''), '') IS NOT NULL
            """
        )
        teachers_by_document = {clean(row[1]): tuple(row) for row in cursor.fetchall() if clean(row[1])}
    return list(students_by_document.values()), list(teachers_by_document.values())


def sync_expedient(students: list[tuple[Any, ...]]) -> int:
    with get_expedient_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE #EstudianteFuente (CodigoEstud bigint NULL, Cedula varchar(30) COLLATE DATABASE_DEFAULT NOT NULL, Nombre nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Correo nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Telefono nvarchar(50) COLLATE DATABASE_DEFAULT NULL, Movil nvarchar(50) COLLATE DATABASE_DEFAULT NULL)"
        )
        cursor.executemany(
            "INSERT INTO #EstudianteFuente VALUES (?, ?, ?, ?, ?, ?)",
            students,
        )
        cursor.execute(
            """
            MERGE core.Persona AS target
            USING #EstudianteFuente AS source
               ON target.NumeroIdentificacion = source.Cedula
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(source.CodigoEstud, target.CodigoEstud),
                ApellidosNombres = source.Nombre, CorreoPersonal = source.Correo,
                Telefono = source.Telefono, Celular = source.Movil,
                FuenteUltimaActualizacion = 'INTECBDD_RECONCILIACION',
                FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (NumeroIdentificacion, CodigoEstud, ApellidosNombres, CorreoPersonal,
                 Telefono, Celular, FuenteUltimaActualizacion)
            VALUES (source.Cedula, source.CodigoEstud, source.Nombre, source.Correo,
                    source.Telefono, source.Movil, 'INTECBDD_RECONCILIACION');
            """
        )
        conn.commit()
    return len(students)


def sync_finance(students: list[tuple[Any, ...]]) -> int:
    with get_finance_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE #EstudianteFuente (CodigoEstud decimal(18,0) NULL, Cedula nvarchar(30) COLLATE DATABASE_DEFAULT NOT NULL, Nombre nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Correo nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Telefono nvarchar(50) COLLATE DATABASE_DEFAULT NULL, Movil nvarchar(50) COLLATE DATABASE_DEFAULT NULL)"
        )
        cursor.executemany("INSERT INTO #EstudianteFuente VALUES (?, ?, ?, ?, ?, ?)", students)
        cursor.execute(
            """
            MERGE core.Estudiante AS target
            USING #EstudianteFuente AS source
               ON target.NumeroIdentificacion = source.Cedula
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(source.CodigoEstud, target.CodigoEstud),
                NombreCompleto = COALESCE(source.Nombre, target.NombreCompleto),
                Correo = source.Correo, Telefono = source.Telefono, Movil = source.Movil,
                FuenteOrigen = 'INTECBDD', FechaSincronizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (CodigoEstud, NumeroIdentificacion, NombreCompleto, Correo, Telefono, Movil, FuenteOrigen)
            VALUES (source.CodigoEstud, source.Cedula, COALESCE(source.Nombre, source.Cedula),
                    source.Correo, source.Telefono, source.Movil, 'INTECBDD');
            """
        )
        conn.commit()
    return len(students)


def sync_graph(students: list[tuple[Any, ...]], teachers: list[tuple[Any, ...]]) -> int:
    people = [
        ("ESTUDIANTE", row[1], row[0], None, row[2], row[3], row[4], row[5])
        for row in students
    ] + [
        ("DOCENTE", row[1], None, row[0], row[2], row[3], row[4], row[5])
        for row in teachers
    ]
    with get_graph_database_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE #PersonaFuente (Tipo varchar(30) COLLATE DATABASE_DEFAULT NOT NULL, Cedula varchar(30) COLLATE DATABASE_DEFAULT NOT NULL, CodigoEstud bigint NULL, CodigoDocente nvarchar(50) COLLATE DATABASE_DEFAULT NULL, Nombre nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Correo nvarchar(250) COLLATE DATABASE_DEFAULT NULL, Telefono nvarchar(50) COLLATE DATABASE_DEFAULT NULL, Movil nvarchar(50) COLLATE DATABASE_DEFAULT NULL)"
        )
        cursor.executemany("INSERT INTO #PersonaFuente VALUES (?, ?, ?, ?, ?, ?, ?, ?)", people)
        cursor.execute(
            """
            MERGE core.PersonaGraphRef AS target
            USING #PersonaFuente AS source
               ON target.TipoPersonaCodigo = source.Tipo
              AND target.NumeroIdentificacion = source.Cedula
            WHEN MATCHED THEN UPDATE SET
                CodigoEstud = COALESCE(source.CodigoEstud, target.CodigoEstud),
                CodigoDocente = COALESCE(source.CodigoDocente, target.CodigoDocente),
                NombreCompleto = COALESCE(source.Nombre, target.NombreCompleto),
                CorreoPersonal = source.Correo, Telefono = source.Telefono,
                Celular = source.Movil, OrigenFuente = 'INTECBDD', Activo = 1,
                FechaSincronizacion = SYSDATETIME(), FechaActualizacion = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (TipoPersonaCodigo, NumeroIdentificacion, CodigoEstud, CodigoDocente,
                 NombreCompleto, CorreoPersonal, Telefono, Celular, OrigenFuente)
            VALUES (source.Tipo, source.Cedula, source.CodigoEstud, source.CodigoDocente,
                    COALESCE(source.Nombre, source.Cedula), source.Correo, source.Telefono,
                    source.Movil, 'INTECBDD');
            """
        )
        conn.commit()
    return len(people)


def run_step(module: str, name: str, callback: Callable[[], int]) -> ComplementStepResult:
    try:
        rows = callback()
        print(f"{module}: OK ({rows} referencia(s))")
        return ComplementStepResult(module, name, True, rows, "Reconciliacion completada")
    except (pyodbc.Error, RuntimeError, ValueError) as exc:
        print(f"{module}: ERROR - {exc}")
        return ComplementStepResult(module, name, False, 0, str(exc)[:3900])


def main() -> int:
    students, teachers = source_people()
    print(f"Fuente principal: {len(students)} estudiante(s), {len(teachers)} docente(s)")
    results = [
        run_step("EXPEDIENTE", "Reconciliar personas estudiantes", lambda: sync_expedient(students)),
        run_step("FINANZAS", "Reconciliar referencias estudiantes", lambda: sync_finance(students)),
        run_step("GRAPH", "Reconciliar estudiantes y docentes", lambda: sync_graph(students, teachers)),
    ]
    trace = record_complement_execution("RECONCILIACION_REFERENCIAS", "script", results)
    print(f"CONTROL: {'OK' if trace.get('ok') else 'ERROR'} {trace}")
    return 0 if all(result.ok for result in results) and trace.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
