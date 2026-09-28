-- Ejecutar en INTECBDD. Conserva la auditoría DDL cuando la base de control
-- está disponible y evita bloquear migraciones cuando no existe en el servidor.
EXEC sys.sp_set_session_context @key=N'audit_suppress', @value=1;
GO
CREATE OR ALTER TRIGGER [trg_AUD_DDL_IntegracionTotal]
ON DATABASE
FOR DDL_DATABASE_LEVEL_EVENTS
AS
BEGIN
    SET NOCOUNT ON;
    IF TRY_CONVERT(BIT, SESSION_CONTEXT(N'audit_suppress')) = 1 RETURN;

    BEGIN TRY
        IF DB_ID(N'INTEC_INTEGRACION_CONTROL') IS NULL RETURN;

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

        -- La llamada dinámica evita que SQL Server resuelva una base ausente
        -- antes de que el control TRY/CATCH pueda manejar la condición.
        EXEC sys.sp_executesql
            N'EXEC [INTEC_INTEGRACION_CONTROL].[aud].[sp_RegistrarCambio]
                @BaseDatos=@pBase, @Esquema=@pEsquema, @Objeto=@pObjeto,
                @Operacion=N''DDL'', @CantidadFilas=0,
                @ColumnasAfectadas=@pTipo, @DatosDespues=@pDetalle;',
            N'@pBase sysname, @pEsquema sysname, @pObjeto sysname, @pTipo nvarchar(128), @pDetalle nvarchar(max)',
            @pBase=@BaseActual,
            @pEsquema=@EsquemaEvento,
            @pObjeto=@ObjetoEvento,
            @pTipo=@TipoEvento,
            @pDetalle=@Detalle;
    END TRY
    BEGIN CATCH
        -- La auditoría no debe bloquear un mantenimiento autorizado.
        RETURN;
    END CATCH;
END;
GO
EXEC sys.sp_set_session_context @key=N'audit_suppress', @value=NULL;
GO
