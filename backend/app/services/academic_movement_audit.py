from __future__ import annotations

import base64
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from typing import Any

import pyodbc


_VALID_REQUEST_TYPES = {"CARRERA", "MODALIDAD"}
_VALID_ACTIONS = {"APLICAR", "RESTAURAR"}


def _canonical_json(value: dict[str, Any] | None) -> str:
    return json.dumps(
        value or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__type__": "time", "value": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "__type__": "bytes",
            "value": base64.b64encode(bytes(value)).decode("ascii"),
        }
    return {"__type__": "string", "value": str(value)}


def cursor_row_dict(cursor: pyodbc.Cursor, row: Any) -> dict[str, Any]:
    columns = [str(description[0]) for description in cursor.description or ()]
    return dict(zip(columns, row, strict=True))


def build_snapshot_row(
    record_type: str,
    data: dict[str, Any],
    key_columns: tuple[str, ...],
) -> dict[str, str]:
    missing = [column for column in key_columns if column not in data]
    if missing:
        raise ValueError(f"El respaldo no contiene su clave natural: {', '.join(missing)}.")
    safe_data = {column: _json_safe_value(value) for column, value in data.items()}
    data_json = json.dumps(
        safe_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    natural_key = json.dumps(
        [_json_safe_value(data[column]) for column in key_columns],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {
        "tipo_registro": record_type,
        "clave_natural": natural_key,
        "datos_json": data_json,
        "sha256": hashlib.sha256(data_json.encode("utf-8")).hexdigest(),
    }


def snapshot_digest(rows: list[dict[str, str]]) -> str:
    digest_source = "\n".join(
        f"{row['tipo_registro']}|{row['clave_natural']}|{row['sha256']}"
        for row in sorted(rows, key=lambda item: (item["tipo_registro"], item["clave_natural"]))
    )
    return hashlib.sha256(digest_source.encode("utf-8")).hexdigest()


def ensure_academic_movement_audit_schema(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud')
            EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo');

        IF OBJECT_ID(N'aud.MovimientoAcademico', N'U') IS NULL
        BEGIN
            CREATE TABLE aud.MovimientoAcademico
            (
                IdMovimiento BIGINT IDENTITY(1,1) NOT NULL
                    CONSTRAINT PK_MovimientoAcademico PRIMARY KEY,
                TipoSolicitud VARCHAR(20) NOT NULL,
                IdSolicitud BIGINT NOT NULL,
                Accion VARCHAR(20) NOT NULL,
                CodigoEstud INT NOT NULL,
                CarreraOrigen INT NULL,
                CarreraDestino INT NULL,
                PeriodoOrigen INT NULL,
                PeriodoDestino INT NULL,
                ModalidadOrigen INT NULL,
                ModalidadDestino INT NULL,
                TotalCabecerasRespaldo INT NOT NULL
                    CONSTRAINT DF_MovimientoAcademico_Cabeceras DEFAULT 0,
                TotalMateriasRespaldo INT NOT NULL
                    CONSTRAINT DF_MovimientoAcademico_Materias DEFAULT 0,
                TotalMateriasMigradas INT NOT NULL
                    CONSTRAINT DF_MovimientoAcademico_Migradas DEFAULT 0,
                TotalRegistrosEliminados INT NOT NULL
                    CONSTRAINT DF_MovimientoAcademico_Eliminados DEFAULT 0,
                HashRespaldo CHAR(64) NOT NULL,
                DatosAntes NVARCHAR(MAX) NOT NULL,
                DatosDespues NVARCHAR(MAX) NOT NULL,
                EjecutadoPor NVARCHAR(256) NOT NULL,
                FechaMovimiento DATETIME2(3) NOT NULL
                    CONSTRAINT DF_MovimientoAcademico_Fecha DEFAULT SYSUTCDATETIME(),
                HashMovimiento CHAR(64) NOT NULL,
                CONSTRAINT UQ_MovimientoAcademico_Solicitud
                    UNIQUE (TipoSolicitud, IdSolicitud, Accion),
                CONSTRAINT CK_MovimientoAcademico_Tipo
                    CHECK (TipoSolicitud IN ('CARRERA', 'MODALIDAD')),
                CONSTRAINT CK_MovimientoAcademico_Accion
                    CHECK (Accion IN ('APLICAR', 'RESTAURAR'))
            );

            CREATE INDEX IX_MovimientoAcademico_Estudiante
                ON aud.MovimientoAcademico(CodigoEstud, FechaMovimiento DESC);
        END;
        """
    )


def record_academic_movement(
    cursor: pyodbc.Cursor,
    *,
    request_type: str,
    request_id: int,
    action: str,
    student_code: int,
    source_career: int | None,
    target_career: int | None,
    source_period: int | None,
    target_period: int | None,
    source_modality: int | None,
    target_modality: int | None,
    backup_headers: int,
    backup_subjects: int,
    migrated_subjects: int,
    deleted_records: int,
    backup_hash: str,
    before: dict[str, Any],
    after: dict[str, Any],
    audit_user: str,
) -> dict[str, Any]:
    normalized_type = request_type.strip().upper()
    normalized_action = action.strip().upper()
    if normalized_type not in _VALID_REQUEST_TYPES:
        raise ValueError("Tipo de solicitud académica no permitido.")
    if normalized_action not in _VALID_ACTIONS:
        raise ValueError("Acción de movimiento académico no permitida.")
    normalized_hash = backup_hash.strip().lower()
    if len(normalized_hash) != 64:
        raise ValueError("El movimiento académico requiere un hash de respaldo válido.")

    ensure_academic_movement_audit_schema(cursor)
    before_json = _canonical_json(before)
    after_json = _canonical_json(after)
    hash_source = _canonical_json(
        {
            "accion": normalized_action,
            "antes": before,
            "despues": after,
            "hash_respaldo": normalized_hash,
            "id_solicitud": int(request_id),
            "tipo_solicitud": normalized_type,
        }
    )
    movement_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()

    cursor.execute(
        """
        SELECT TOP (1) IdMovimiento, HashRespaldo, HashMovimiento
        FROM aud.MovimientoAcademico WITH (UPDLOCK, HOLDLOCK)
        WHERE TipoSolicitud = ? AND IdSolicitud = ? AND Accion = ?
        """,
        normalized_type,
        request_id,
        normalized_action,
    )
    existing = cursor.fetchone()
    if existing:
        existing_backup_hash = str(existing.HashRespaldo or "").strip().lower()
        existing_movement_hash = str(existing.HashMovimiento or "").strip().lower()
        if existing_backup_hash != normalized_hash or existing_movement_hash != movement_hash:
            raise ValueError(
                "La auditoría existente no coincide con el movimiento académico solicitado."
            )
        return {
            "id_movimiento": int(existing.IdMovimiento),
            "hash_movimiento": existing_movement_hash,
            "created": False,
        }

    cursor.execute(
        """
        INSERT INTO aud.MovimientoAcademico
        (
            TipoSolicitud, IdSolicitud, Accion, CodigoEstud,
            CarreraOrigen, CarreraDestino, PeriodoOrigen, PeriodoDestino,
            ModalidadOrigen, ModalidadDestino,
            TotalCabecerasRespaldo, TotalMateriasRespaldo,
            TotalMateriasMigradas, TotalRegistrosEliminados,
            HashRespaldo, DatosAntes, DatosDespues, EjecutadoPor, HashMovimiento
        )
        OUTPUT INSERTED.IdMovimiento
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        normalized_type,
        request_id,
        normalized_action,
        student_code,
        source_career,
        target_career,
        source_period,
        target_period,
        source_modality,
        target_modality,
        max(int(backup_headers), 0),
        max(int(backup_subjects), 0),
        max(int(migrated_subjects), 0),
        max(int(deleted_records), 0),
        normalized_hash,
        before_json,
        after_json,
        (audit_user.strip() or "SISTEMA")[:256],
        movement_hash,
    )
    movement_id = int(cursor.fetchone()[0])

    cursor.execute("SELECT OBJECT_ID(N'aud.sp_RegistrarCambio', N'P')")
    procedure_row = cursor.fetchone()
    if procedure_row and procedure_row[0] is not None:
        keys_json = _canonical_json(
            {
                "id_movimiento": movement_id,
                "id_solicitud": request_id,
                "tipo_solicitud": normalized_type,
            }
        )
        cursor.execute(
            """
            EXEC aud.sp_RegistrarCambio
                @BaseDatos = N'INTECBDD',
                @Esquema = N'dbo',
                @Objeto = ?,
                @Operacion = N'UPDATE',
                @CantidadFilas = ?,
                @ColumnasAfectadas = N'Matrícula, modalidad, carrera, período y calificaciones',
                @ClavesAfectadas = ?,
                @DatosAntes = ?,
                @DatosDespues = ?,
                @MuestraLimitada = 0
            """,
            f"SolicitudCambio{normalized_type.title()}",
            max(int(deleted_records), 0) + max(int(migrated_subjects), 0),
            keys_json,
            before_json,
            after_json,
        )

    return {
        "id_movimiento": movement_id,
        "hash_movimiento": movement_hash,
        "created": True,
    }
