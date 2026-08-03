from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.audit_context import AuditContext, reset_audit_context, set_audit_context
from app.core.config import get_settings
from app.services.db import (
    get_connection,
    get_evaluation_connection,
    get_expedient_connection,
    get_finance_connection,
    get_graph_database_connection,
    get_integration_control_connection,
    get_practices_connection,
    get_teams_connection,
    get_titulation_connection,
)

CONTROL_DATABASE = "INTEC_INTEGRACION_CONTROL"
SCHEMA_SCRIPT = ROOT / "sql" / "2026_08_03_auditoria_integracion_total.sql"
MAX_SAMPLE_ROWS = 100


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    name: str
    connect: Callable[[], pyodbc.Connection]


@dataclass(frozen=True, slots=True)
class TableInfo:
    object_id: int
    schema: str
    name: str


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    type_name: str
    encrypted: bool
    computed: bool


def _split_batches(sql: str) -> list[str]:
    return [
        batch.strip()
        for batch in re.split(r"(?im)^\s*GO\s*(?:--.*)?$", sql)
        if batch.strip()
    ]


def _quote(identifier: str) -> str:
    return f"[{identifier.replace(']', ']]')}]"


def _literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _is_sensitive(column_name: str) -> bool:
    normalized = _normalized(column_name).replace("_", "")
    markers = (
        "password",
        "contrasena",
        "passwd",
        "secret",
        "token",
        "privatekey",
        "llaveprivada",
        "credential",
        "credencial",
        "certificado",
        "archivop12",
        "p12",
        "salt",
        "hashpassword",
        "hashcontrasena",
    )
    return any(marker in normalized for marker in markers)


def _snapshot_expression(column: ColumnInfo) -> str:
    quoted = _quote(column.name)
    source = f"src.{quoted}"
    alias = quoted
    legacy_lob_types = {"text", "ntext", "image"}
    binary_types = {"binary", "varbinary", "timestamp", "rowversion"}

    # SQL Server no expone text/ntext/image desde inserted/deleted en triggers
    # AFTER. Se conserva el dato de que la columna existe sin intentar leerla.
    if column.type_name.lower() in legacy_lob_types:
        return f"N'[TIPO LEGACY NO CAPTURADO]' AS {alias}"

    if column.encrypted or _is_sensitive(column.name):
        return (
            f"CASE WHEN {source} IS NULL THEN NULL "
            f"ELSE N'[PROTEGIDO]' END AS {alias}"
        )
    if column.type_name.lower() in binary_types:
        return (
            f"CASE WHEN {source} IS NULL THEN NULL ELSE CONCAT(N'[BINARIO:', "
            f"CONVERT(NVARCHAR(30), DATALENGTH({source})), N' bytes]') END AS {alias}"
        )
    return f"LEFT(TRY_CONVERT(NVARCHAR(512), {source}), 512) AS {alias}"


def _key_expression(column_name: str) -> str:
    quoted = _quote(column_name)
    return f"LEFT(TRY_CONVERT(NVARCHAR(512), src.{quoted}), 512) AS {quoted}"


def _trigger_name(database: str, schema: str, table: str) -> str:
    digest = hashlib.sha1(f"{database}.{schema}.{table}".encode("utf-8")).hexdigest()[:24]
    return f"trg_AUD_DML_{digest}"


def _build_dml_trigger(
    *,
    database: str,
    table: TableInfo,
    columns: list[ColumnInfo],
    primary_keys: list[str],
    capture_data: bool,
    max_rows: int,
) -> tuple[str, str]:
    trigger_name = _trigger_name(database, table.schema, table.name)
    qualified_table = f"{_quote(table.schema)}.{_quote(table.name)}"
    changed_columns = " + ".join(
        f"CASE WHEN UPDATE({_quote(column.name)}) THEN {_literal(column.name + ',')} ELSE N'' END"
        for column in columns
        if not column.computed
    ) or "N''"
    snapshot_projection = ",\n                    ".join(
        _snapshot_expression(column) for column in columns
    )
    key_projection = ", ".join(_key_expression(name) for name in primary_keys)

    before_snapshot = ""
    after_snapshot = ""
    if capture_data and snapshot_projection:
        before_snapshot = f"""
            IF @FilasEliminadas > 0
                SELECT @DatosAntes =
                (
                    SELECT TOP ({max_rows})
                    {snapshot_projection}
                    FROM deleted AS src
                    FOR JSON PATH, INCLUDE_NULL_VALUES
                );"""
        after_snapshot = f"""
            IF @FilasInsertadas > 0
                SELECT @DatosDespues =
                (
                    SELECT TOP ({max_rows})
                    {snapshot_projection}
                    FROM inserted AS src
                    FOR JSON PATH, INCLUDE_NULL_VALUES
                );"""

    key_capture = ""
    if key_projection:
        key_capture = f"""
            DECLARE @ClavesAntes NVARCHAR(MAX) = N'[]';
            DECLARE @ClavesDespues NVARCHAR(MAX) = N'[]';
            IF @FilasEliminadas > 0
                SELECT @ClavesAntes =
                (
                    SELECT TOP ({max_rows}) {key_projection}
                    FROM deleted AS src
                    FOR JSON PATH, INCLUDE_NULL_VALUES
                );
            IF @FilasInsertadas > 0
                SELECT @ClavesDespues =
                (
                    SELECT TOP ({max_rows}) {key_projection}
                    FROM inserted AS src
                    FOR JSON PATH, INCLUDE_NULL_VALUES
                );
            SET @Claves = CONCAT(N'{{"antes":', COALESCE(@ClavesAntes, N'[]'),
                                 N',"despues":', COALESCE(@ClavesDespues, N'[]'), N'}}');"""

    qualified_trigger = f"{_quote(table.schema)}.{_quote(trigger_name)}"
    sql = f"""CREATE OR ALTER TRIGGER {qualified_trigger}
ON {qualified_table}
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF TRY_CONVERT(BIT, SESSION_CONTEXT(N'audit_suppress')) = 1 RETURN;

    BEGIN TRY
        DECLARE @FilasInsertadas BIGINT = (SELECT COUNT_BIG(1) FROM inserted);
        DECLARE @FilasEliminadas BIGINT = (SELECT COUNT_BIG(1) FROM deleted);
        DECLARE @Operacion VARCHAR(10) = CASE
            WHEN @FilasInsertadas > 0 AND @FilasEliminadas > 0 THEN 'UPDATE'
            WHEN @FilasInsertadas > 0 THEN 'INSERT'
            ELSE 'DELETE'
        END;
        DECLARE @CantidadFilas BIGINT = CASE
            WHEN @FilasInsertadas > @FilasEliminadas THEN @FilasInsertadas
            ELSE @FilasEliminadas
        END;
        DECLARE @Columnas NVARCHAR(MAX) = CASE
            WHEN @Operacion = 'UPDATE' THEN {changed_columns}
            ELSE N'*'
        END;
        DECLARE @Claves NVARCHAR(MAX) = NULL;
        DECLARE @DatosAntes NVARCHAR(MAX) = NULL;
        DECLARE @DatosDespues NVARCHAR(MAX) = NULL;
        DECLARE @BaseActual SYSNAME = DB_NAME();
        DECLARE @MuestraLimitada BIT = CASE
            WHEN @CantidadFilas > {max_rows} THEN 1 ELSE 0
        END;

        IF RIGHT(@Columnas, 1) = N','
            SET @Columnas = LEFT(@Columnas, LEN(@Columnas) - 1);
        {key_capture}
        {before_snapshot}
        {after_snapshot}

        EXEC {_quote(CONTROL_DATABASE)}.[aud].[sp_RegistrarCambio]
            @BaseDatos = @BaseActual,
            @Esquema = {_literal(table.schema)},
            @Objeto = {_literal(table.name)},
            @Operacion = @Operacion,
            @CantidadFilas = @CantidadFilas,
            @ColumnasAfectadas = @Columnas,
            @ClavesAfectadas = @Claves,
            @DatosAntes = @DatosAntes,
            @DatosDespues = @DatosDespues,
            @MuestraLimitada = @MuestraLimitada;
    END TRY
    BEGIN CATCH
        -- La auditoria nunca debe bloquear la operacion academica original.
    END CATCH;
END;"""
    return trigger_name, sql


def _build_ddl_trigger() -> tuple[str, str]:
    trigger_name = "trg_AUD_DDL_IntegracionTotal"
    sql = f"""CREATE OR ALTER TRIGGER {_quote(trigger_name)}
ON DATABASE
FOR DDL_DATABASE_LEVEL_EVENTS
AS
BEGIN
    SET NOCOUNT ON;
    IF TRY_CONVERT(BIT, SESSION_CONTEXT(N'audit_suppress')) = 1 RETURN;

    BEGIN TRY
        DECLARE @Evento XML = EVENTDATA();
        DECLARE @TipoEvento NVARCHAR(128) = @Evento.value('(/EVENT_INSTANCE/EventType)[1]', 'nvarchar(128)');
        DECLARE @Esquema SYSNAME = NULLIF(@Evento.value('(/EVENT_INSTANCE/SchemaName)[1]', 'sysname'), N'');
        DECLARE @Objeto SYSNAME = NULLIF(@Evento.value('(/EVENT_INSTANCE/ObjectName)[1]', 'sysname'), N'');
        DECLARE @BaseActual SYSNAME = DB_NAME();
        DECLARE @EsquemaEvento SYSNAME = COALESCE(@Esquema, N'DATABASE');
        DECLARE @ObjetoEvento SYSNAME = COALESCE(@Objeto, N'*');
        DECLARE @Detalle NVARCHAR(MAX);

        SELECT @Detalle =
        (
            SELECT
                @TipoEvento AS tipo_evento,
                NULLIF(@Evento.value('(/EVENT_INSTANCE/ObjectType)[1]', 'nvarchar(128)'), N'') AS tipo_objeto,
                NULLIF(@Evento.value('(/EVENT_INSTANCE/LoginName)[1]', 'nvarchar(256)'), N'') AS login,
                NULLIF(@Evento.value('(/EVENT_INSTANCE/UserName)[1]', 'nvarchar(256)'), N'') AS usuario,
                NULLIF(@Evento.value('(/EVENT_INSTANCE/PostTime)[1]', 'nvarchar(64)'), N'') AS fecha_servidor
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
        );

        EXEC {_quote(CONTROL_DATABASE)}.[aud].[sp_RegistrarCambio]
            @BaseDatos = @BaseActual,
            @Esquema = @EsquemaEvento,
            @Objeto = @ObjetoEvento,
            @Operacion = 'DDL',
            @CantidadFilas = 0,
            @ColumnasAfectadas = @TipoEvento,
            @DatosDespues = @Detalle;
    END TRY
    BEGIN CATCH
        -- La auditoria nunca debe bloquear un mantenimiento autorizado.
    END CATCH;
END;"""
    return trigger_name, sql


def _configured_targets() -> list[DatabaseTarget]:
    settings = get_settings()
    candidates = [
        DatabaseTarget(settings.db_name, get_connection),
        DatabaseTarget(settings.eval_db_name or "", get_evaluation_connection),
        DatabaseTarget(settings.practices_db_name or "", get_practices_connection),
        DatabaseTarget(settings.titulation_db_name or "", get_titulation_connection),
        DatabaseTarget(settings.teams_db_name, get_teams_connection),
        DatabaseTarget(settings.expedient_db_name, get_expedient_connection),
        DatabaseTarget(settings.finance_db_name, get_finance_connection),
        DatabaseTarget(settings.graph_db_name, get_graph_database_connection),
        DatabaseTarget(settings.integration_control_db_name, get_integration_control_connection),
    ]
    seen: set[str] = set()
    result: list[DatabaseTarget] = []
    for target in candidates:
        key = target.name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result


def _apply_schema(connection: pyodbc.Connection) -> None:
    sql = SCHEMA_SCRIPT.read_text(encoding="utf-8")
    cursor = connection.cursor()
    for batch in _split_batches(sql):
        cursor.execute(batch)
        while cursor.nextset():
            pass
    connection.commit()


def _load_tables(cursor: pyodbc.Cursor) -> list[TableInfo]:
    rows = cursor.execute(
        """
        SELECT T.object_id, S.name AS Esquema, T.name AS Tabla
        FROM sys.tables T
        INNER JOIN sys.schemas S ON S.schema_id = T.schema_id
        WHERE T.is_ms_shipped = 0
          AND T.temporal_type <> 1
          AND T.is_filetable = 0
          AND S.name <> N'aud'
        ORDER BY S.name, T.name
        """
    ).fetchall()
    return [TableInfo(int(row[0]), str(row[1]), str(row[2])) for row in rows]


def _load_columns(cursor: pyodbc.Cursor, object_id: int) -> list[ColumnInfo]:
    rows = cursor.execute(
        """
        SELECT C.name, TYPE_NAME(C.system_type_id) AS Tipo, C.encryption_type, C.is_computed
        FROM sys.columns C
        WHERE C.object_id = ?
        ORDER BY C.column_id
        """,
        object_id,
    ).fetchall()
    return [
        ColumnInfo(
            str(row[0]),
            str(row[1] or "nvarchar"),
            row[2] is not None,
            bool(row[3]),
        )
        for row in rows
    ]


def _load_primary_keys(cursor: pyodbc.Cursor, object_id: int) -> list[str]:
    rows = cursor.execute(
        """
        SELECT C.name
        FROM sys.indexes I
        INNER JOIN sys.index_columns IC
            ON IC.object_id = I.object_id AND IC.index_id = I.index_id
        INNER JOIN sys.columns C
            ON C.object_id = IC.object_id AND C.column_id = IC.column_id
        WHERE I.object_id = ?
          AND I.is_primary_key = 1
        ORDER BY IC.key_ordinal
        """,
        object_id,
    ).fetchall()
    return [str(row[0]) for row in rows]


def _register_base(cursor: pyodbc.Cursor, database: str) -> None:
    cursor.execute(
        "EXEC aud.sp_RegistrarBaseAuditada @BaseDatos=?, @CapturarDatos=1, @MaximoFilasMuestra=?",
        database,
        MAX_SAMPLE_ROWS,
    )
    cursor.execute("EXEC aud.sp_PrepararCobertura @BaseDatos=?", database)


def _register_coverage(
    cursor: pyodbc.Cursor,
    *,
    database: str,
    schema: str,
    object_name: str,
    capture_type: str,
    trigger_name: str,
    installed: bool,
    error: str | None = None,
) -> None:
    cursor.execute(
        """
        EXEC aud.sp_RegistrarCobertura
            @BaseDatos=?, @Esquema=?, @Objeto=?, @TipoCaptura=?,
            @NombreTrigger=?, @Instalado=?, @UltimoError=?
        """,
        database,
        schema,
        object_name,
        capture_type,
        trigger_name,
        int(installed),
        (error or "")[:2000],
    )


def _install_target(
    target: DatabaseTarget,
    control_cursor: pyodbc.Cursor,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    installed = 0
    errors = 0
    _register_base(control_cursor, target.name)

    with target.connect() as connection:
        connection.commit()
        connection.autocommit = True
        cursor = connection.cursor()
        actual_database = str(cursor.execute("SELECT DB_NAME()").fetchone()[0])
        if actual_database.lower() != target.name.lower():
            raise RuntimeError(
                f"La conexion esperaba {target.name} pero SQL Server abrio {actual_database}"
            )
        compatibility = int(
            cursor.execute(
                "SELECT compatibility_level FROM sys.databases WHERE name = DB_NAME()"
            ).fetchone()[0]
        )
        if compatibility < 130:
            raise RuntimeError(
                f"{target.name} requiere nivel de compatibilidad 130 o superior para FOR JSON"
            )

        cursor.execute(
            "EXEC sys.sp_set_session_context @key=N'audit_suppress', @value=1"
        )
        for table in _load_tables(cursor):
            columns = _load_columns(cursor, table.object_id)
            primary_keys = _load_primary_keys(cursor, table.object_id)
            trigger_name, trigger_sql = _build_dml_trigger(
                database=target.name,
                table=table,
                columns=columns,
                primary_keys=primary_keys,
                capture_data=True,
                max_rows=MAX_SAMPLE_ROWS,
            )
            try:
                if not dry_run:
                    cursor.execute(trigger_sql)
                _register_coverage(
                    control_cursor,
                    database=target.name,
                    schema=table.schema,
                    object_name=table.name,
                    capture_type="DML",
                    trigger_name=trigger_name,
                    installed=not dry_run,
                    error="Vista previa; no instalado" if dry_run else None,
                )
                installed += int(not dry_run)
            except pyodbc.Error as exc:
                errors += 1
                _register_coverage(
                    control_cursor,
                    database=target.name,
                    schema=table.schema,
                    object_name=table.name,
                    capture_type="DML",
                    trigger_name=trigger_name,
                    installed=False,
                    error=str(exc),
                )

        ddl_name, ddl_sql = _build_ddl_trigger()
        try:
            if not dry_run:
                cursor.execute(ddl_sql)
            _register_coverage(
                control_cursor,
                database=target.name,
                schema="DATABASE",
                object_name="*",
                capture_type="DDL",
                trigger_name=ddl_name,
                installed=not dry_run,
                error="Vista previa; no instalado" if dry_run else None,
            )
            installed += int(not dry_run)
        except pyodbc.Error as exc:
            errors += 1
            _register_coverage(
                control_cursor,
                database=target.name,
                schema="DATABASE",
                object_name="*",
                capture_type="DDL",
                trigger_name=ddl_name,
                installed=False,
                error=str(exc),
            )
        finally:
            cursor.execute(
                "EXEC sys.sp_set_session_context @key=N'audit_suppress', @value=0"
            )

    return installed, errors


def _select_targets(
    configured: Iterable[DatabaseTarget],
    requested: list[str],
) -> list[DatabaseTarget]:
    targets = list(configured)
    if not requested:
        return targets
    wanted = {name.strip().lower() for name in requested if name.strip()}
    selected = [target for target in targets if target.name.lower() in wanted]
    missing = sorted(wanted - {target.name.lower() for target in selected})
    if missing:
        raise ValueError(f"Bases no configuradas: {', '.join(missing)}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Instala la auditoria transversal en las bases integradas."
    )
    parser.add_argument(
        "--database",
        action="append",
        default=[],
        help="Limita la instalacion a una base configurada; puede repetirse.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida metadatos y genera cobertura sin crear triggers.",
    )
    args = parser.parse_args()

    targets = _select_targets(_configured_targets(), args.database)
    audit_token = set_audit_context(
        AuditContext(
            user="INSTALADOR_AUDITORIA_TOTAL",
            role="SISTEMA",
            origin="SCRIPT_SQL",
            method="INSTALL",
            path="scripts/install_total_audit.py",
        )
    )
    total_installed = 0
    total_errors = 0
    try:
        with get_integration_control_connection() as control:
            _apply_schema(control)
            control_cursor = control.cursor()
            for target in targets:
                installed, errors = _install_target(
                    target,
                    control_cursor,
                    dry_run=args.dry_run,
                )
                control.commit()
                total_installed += installed
                total_errors += errors
                print(
                    f"{target.name}: {installed} captura(s) instalada(s), "
                    f"{errors} error(es)"
                )

            coverage = control_cursor.execute(
                """
                SELECT
                    COUNT(*) AS Registrados,
                    SUM(CASE WHEN Instalado = 1 THEN 1 ELSE 0 END) AS Instalados,
                    SUM(CASE WHEN Instalado = 0 THEN 1 ELSE 0 END) AS Pendientes
                FROM aud.CoberturaObjeto
                WHERE BaseDatos IN ({})
                """.format(",".join("?" for _ in targets)),
                *(target.name for target in targets),
            ).fetchone()
            print(
                "Cobertura total: "
                f"{int(coverage[1] or 0)}/{int(coverage[0] or 0)} instalada(s), "
                f"{int(coverage[2] or 0)} pendiente(s)"
            )
    finally:
        reset_audit_context(audit_token)

    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
