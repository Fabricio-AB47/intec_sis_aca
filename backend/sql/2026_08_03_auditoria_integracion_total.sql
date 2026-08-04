/* ============================================================================
   INTEC_INTEGRACION_CONTROL - AUDITORIA TOTAL DE CAMBIOS

   Parche aditivo e idempotente. Centraliza INSERT, UPDATE, DELETE y DDL de las
   bases integradas. Los disparadores se instalan con:

       python scripts/install_total_audit.py

   La aplicacion propaga usuario, rol, origen y solicitud mediante
   SESSION_CONTEXT. Las operaciones directas desde SSMS conservan login SQL,
   host y nombre de aplicacion. No se auditan lecturas SELECT.
   ============================================================================ */
USE [INTEC_INTEGRACION_CONTROL];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud')
    EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt')
    EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'util')
    EXEC(N'CREATE SCHEMA util AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'aud.BaseAuditada', N'U') IS NULL
BEGIN
    CREATE TABLE aud.BaseAuditada
    (
        BaseDatos SYSNAME NOT NULL CONSTRAINT PK_AudBaseAuditada PRIMARY KEY,
        Activa BIT NOT NULL CONSTRAINT DF_AudBaseAuditada_Activa DEFAULT 1,
        CapturarDatos BIT NOT NULL CONSTRAINT DF_AudBaseAuditada_Datos DEFAULT 1,
        MaximoFilasMuestra SMALLINT NOT NULL CONSTRAINT DF_AudBaseAuditada_Filas DEFAULT 100,
        FechaRegistro DATETIME2(3) NOT NULL CONSTRAINT DF_AudBaseAuditada_Registro DEFAULT SYSUTCDATETIME(),
        FechaActualizacion DATETIME2(3) NOT NULL CONSTRAINT DF_AudBaseAuditada_Actualizacion DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_AudBaseAuditada_Filas CHECK (MaximoFilasMuestra BETWEEN 1 AND 100)
    );
END;
GO

IF OBJECT_ID(N'aud.CoberturaObjeto', N'U') IS NULL
BEGIN
    CREATE TABLE aud.CoberturaObjeto
    (
        CoberturaObjetoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AudCoberturaObjeto PRIMARY KEY,
        BaseDatos SYSNAME NOT NULL,
        Esquema SYSNAME NOT NULL,
        Objeto SYSNAME NOT NULL,
        TipoCaptura VARCHAR(10) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreTrigger SYSNAME NULL,
        Instalado BIT NOT NULL CONSTRAINT DF_AudCobertura_Instalado DEFAULT 0,
        UltimoError NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        FechaUltimoIntento DATETIME2(3) NOT NULL CONSTRAINT DF_AudCobertura_Intento DEFAULT SYSUTCDATETIME(),
        FechaInstalacion DATETIME2(3) NULL,
        CONSTRAINT UQ_AudCoberturaObjeto UNIQUE(BaseDatos, Esquema, Objeto, TipoCaptura),
        CONSTRAINT CK_AudCobertura_Tipo CHECK (TipoCaptura IN ('DML', 'DDL'))
    );
END;
GO

IF OBJECT_ID(N'aud.EventoCambio', N'U') IS NULL
BEGIN
    CREATE TABLE aud.EventoCambio
    (
        EventoCambioId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AudEventoCambio PRIMARY KEY,
        FechaEventoUtc DATETIME2(3) NOT NULL CONSTRAINT DF_AudEvento_Fecha DEFAULT SYSUTCDATETIME(),
        BaseDatos SYSNAME NOT NULL,
        Esquema SYSNAME NOT NULL,
        Objeto SYSNAME NOT NULL,
        Operacion VARCHAR(10) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CantidadFilas BIGINT NOT NULL CONSTRAINT DF_AudEvento_Filas DEFAULT 0,
        ColumnasAfectadas NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        ClavesAfectadas NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        DatosAntes NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        DatosDespues NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        MuestraLimitada BIT NOT NULL CONSTRAINT DF_AudEvento_Limitada DEFAULT 0,
        UsuarioAplicacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        RolAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioIdAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        OrigenAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        LoginSql NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL,
        UsuarioSql NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        HostCliente NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        AplicacionCliente NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        DireccionCliente NVARCHAR(64) COLLATE Modern_Spanish_CI_AS NULL,
        IdSolicitud NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        MetodoHttp VARCHAR(10) COLLATE Modern_Spanish_CI_AS NULL,
        RutaHttp NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        HashEvento VARBINARY(32) NULL,
        CONSTRAINT CK_AudEvento_Operacion CHECK (Operacion IN ('INSERT', 'UPDATE', 'DELETE', 'DDL')),
        CONSTRAINT CK_AudEvento_Filas CHECK (CantidadFilas >= 0)
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'aud.EventoCambio')
      AND name = N'IX_AudEvento_Fecha'
)
    CREATE INDEX IX_AudEvento_Fecha
        ON aud.EventoCambio(FechaEventoUtc DESC, EventoCambioId DESC);
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'aud.EventoCambio')
      AND name = N'IX_AudEvento_ObjetoFecha'
)
    CREATE INDEX IX_AudEvento_ObjetoFecha
        ON aud.EventoCambio(BaseDatos, Esquema, Objeto, FechaEventoUtc DESC)
        INCLUDE(Operacion, CantidadFilas, UsuarioAplicacion, LoginSql);
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'aud.EventoCambio')
      AND name = N'IX_AudEvento_UsuarioFecha'
)
    CREATE INDEX IX_AudEvento_UsuarioFecha
        ON aud.EventoCambio(UsuarioAplicacion, FechaEventoUtc DESC)
        INCLUDE(BaseDatos, Esquema, Objeto, Operacion, CantidadFilas);
GO

CREATE OR ALTER PROCEDURE aud.sp_RegistrarBaseAuditada
    @BaseDatos SYSNAME,
    @CapturarDatos BIT = 1,
    @MaximoFilasMuestra SMALLINT = 100
AS
BEGIN
    SET NOCOUNT ON;

    SET @MaximoFilasMuestra = CASE
        WHEN @MaximoFilasMuestra < 1 THEN 1
        WHEN @MaximoFilasMuestra > 100 THEN 100
        ELSE @MaximoFilasMuestra
    END;

    MERGE aud.BaseAuditada AS destino
    USING
    (
        SELECT
            CONVERT(SYSNAME, @BaseDatos) AS BaseDatos,
            @CapturarDatos AS CapturarDatos,
            @MaximoFilasMuestra AS MaximoFilasMuestra
    ) AS origen
       ON origen.BaseDatos = destino.BaseDatos
    WHEN MATCHED THEN
        UPDATE SET
            Activa = 1,
            CapturarDatos = origen.CapturarDatos,
            MaximoFilasMuestra = origen.MaximoFilasMuestra,
            FechaActualizacion = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT(BaseDatos, Activa, CapturarDatos, MaximoFilasMuestra)
        VALUES(origen.BaseDatos, 1, origen.CapturarDatos, origen.MaximoFilasMuestra);
END;
GO

CREATE OR ALTER PROCEDURE aud.sp_PrepararCobertura
    @BaseDatos SYSNAME
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE aud.CoberturaObjeto
       SET Instalado = 0,
           UltimoError = N'Pendiente de sincronizacion',
           FechaUltimoIntento = SYSUTCDATETIME()
     WHERE BaseDatos = @BaseDatos;
END;
GO

CREATE OR ALTER PROCEDURE aud.sp_RegistrarCobertura
    @BaseDatos SYSNAME,
    @Esquema SYSNAME,
    @Objeto SYSNAME,
    @TipoCaptura VARCHAR(10),
    @NombreTrigger SYSNAME = NULL,
    @Instalado BIT,
    @UltimoError NVARCHAR(2000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    MERGE aud.CoberturaObjeto AS destino
    USING
    (
        SELECT
            @BaseDatos AS BaseDatos,
            @Esquema AS Esquema,
            @Objeto AS Objeto,
            @TipoCaptura AS TipoCaptura
    ) AS origen
       ON origen.BaseDatos = destino.BaseDatos
      AND origen.Esquema = destino.Esquema
      AND origen.Objeto = destino.Objeto
      AND origen.TipoCaptura = destino.TipoCaptura
    WHEN MATCHED THEN
        UPDATE SET
            NombreTrigger = @NombreTrigger,
            Instalado = @Instalado,
            UltimoError = NULLIF(@UltimoError, N''),
            FechaUltimoIntento = SYSUTCDATETIME(),
            FechaInstalacion = CASE WHEN @Instalado = 1 THEN SYSUTCDATETIME() ELSE destino.FechaInstalacion END
    WHEN NOT MATCHED THEN
        INSERT
        (
            BaseDatos, Esquema, Objeto, TipoCaptura, NombreTrigger,
            Instalado, UltimoError, FechaInstalacion
        )
        VALUES
        (
            @BaseDatos, @Esquema, @Objeto, @TipoCaptura, @NombreTrigger,
            @Instalado, NULLIF(@UltimoError, N''),
            CASE WHEN @Instalado = 1 THEN SYSUTCDATETIME() ELSE NULL END
        );
END;
GO

CREATE OR ALTER PROCEDURE aud.sp_RegistrarCambio
    @BaseDatos SYSNAME,
    @Esquema SYSNAME,
    @Objeto SYSNAME,
    @Operacion VARCHAR(10),
    @CantidadFilas BIGINT = 0,
    @ColumnasAfectadas NVARCHAR(MAX) = NULL,
    @ClavesAfectadas NVARCHAR(MAX) = NULL,
    @DatosAntes NVARCHAR(MAX) = NULL,
    @DatosDespues NVARCHAR(MAX) = NULL,
    @MuestraLimitada BIT = 0
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Fecha DATETIME2(3) = SYSUTCDATETIME();
    DECLARE @UsuarioAplicacion NVARCHAR(256) = NULLIF(TRY_CONVERT(NVARCHAR(256), SESSION_CONTEXT(N'app_user')), N'');
    DECLARE @RolAplicacion NVARCHAR(100) = NULLIF(TRY_CONVERT(NVARCHAR(100), SESSION_CONTEXT(N'app_role')), N'');
    DECLARE @UsuarioId NVARCHAR(100) = NULLIF(TRY_CONVERT(NVARCHAR(100), SESSION_CONTEXT(N'app_user_id')), N'');
    DECLARE @Origen NVARCHAR(100) = NULLIF(TRY_CONVERT(NVARCHAR(100), SESSION_CONTEXT(N'app_origin')), N'');
    DECLARE @Solicitud NVARCHAR(128) = NULLIF(TRY_CONVERT(NVARCHAR(128), SESSION_CONTEXT(N'request_id')), N'');
    DECLARE @Metodo VARCHAR(10) = NULLIF(TRY_CONVERT(VARCHAR(10), SESSION_CONTEXT(N'request_method')), '');
    DECLARE @Ruta NVARCHAR(1000) = NULLIF(TRY_CONVERT(NVARCHAR(1000), SESSION_CONTEXT(N'request_path')), N'');
    DECLARE @Ip NVARCHAR(64) = COALESCE
    (
        NULLIF(TRY_CONVERT(NVARCHAR(64), SESSION_CONTEXT(N'request_ip')), N''),
        TRY_CONVERT(NVARCHAR(64), CONNECTIONPROPERTY('client_net_address'))
    );

    SET @UsuarioAplicacion = COALESCE(@UsuarioAplicacion, NULLIF(ORIGINAL_LOGIN(), N''), N'SISTEMA');
    SET @Operacion = UPPER(LTRIM(RTRIM(@Operacion)));
    SET @CantidadFilas = CASE WHEN @CantidadFilas < 0 THEN 0 ELSE @CantidadFilas END;

    -- Impide que una operacion masiva o un texto extenso convierta la bitacora
    -- en repositorio de archivos. La marca MuestraLimitada conserva el contexto.
    IF LEN(@ClavesAfectadas) > 1000000
    BEGIN
        SET @ClavesAfectadas = LEFT(@ClavesAfectadas, 999950) + N'...[TRUNCADO]';
        SET @MuestraLimitada = 1;
    END;
    IF LEN(@DatosAntes) > 1000000
    BEGIN
        SET @DatosAntes = LEFT(@DatosAntes, 999950) + N'...[TRUNCADO]';
        SET @MuestraLimitada = 1;
    END;
    IF LEN(@DatosDespues) > 1000000
    BEGIN
        SET @DatosDespues = LEFT(@DatosDespues, 999950) + N'...[TRUNCADO]';
        SET @MuestraLimitada = 1;
    END;

    INSERT INTO aud.EventoCambio
    (
        FechaEventoUtc, BaseDatos, Esquema, Objeto, Operacion, CantidadFilas,
        ColumnasAfectadas, ClavesAfectadas, DatosAntes, DatosDespues, MuestraLimitada,
        UsuarioAplicacion, RolAplicacion, UsuarioIdAplicacion, OrigenAplicacion,
        LoginSql, UsuarioSql, HostCliente, AplicacionCliente, DireccionCliente,
        IdSolicitud, MetodoHttp, RutaHttp
    )
    VALUES
    (
        @Fecha, @BaseDatos, @Esquema, @Objeto, @Operacion, @CantidadFilas,
        NULLIF(@ColumnasAfectadas, N''), NULLIF(@ClavesAfectadas, N''),
        NULLIF(@DatosAntes, N''), NULLIF(@DatosDespues, N''), @MuestraLimitada,
        @UsuarioAplicacion, @RolAplicacion, @UsuarioId, @Origen,
        ORIGINAL_LOGIN(), SUSER_SNAME(), HOST_NAME(), APP_NAME(), @Ip,
        @Solicitud, @Metodo, @Ruta
    );

    DECLARE @EventoId BIGINT = SCOPE_IDENTITY();
    UPDATE aud.EventoCambio
       SET HashEvento = HASHBYTES
       (
           'SHA2_256',
           CONVERT(VARBINARY(MAX), CONCAT
           (
               @EventoId, N'|', CONVERT(NVARCHAR(33), @Fecha, 126), N'|',
               @BaseDatos, N'|', @Esquema, N'|', @Objeto, N'|', @Operacion, N'|',
               @CantidadFilas, N'|', @UsuarioAplicacion, N'|', ORIGINAL_LOGIN(), N'|',
               COALESCE(@Solicitud, N''), N'|', COALESCE(@ClavesAfectadas, N''), N'|',
               COALESCE(@DatosAntes, N''), N'|', COALESCE(@DatosDespues, N'')
           ))
       )
     WHERE EventoCambioId = @EventoId;
END;
GO

CREATE OR ALTER VIEW rpt.vw_AuditoriaIntegracion
AS
SELECT
    E.EventoCambioId,
    E.FechaEventoUtc,
    FechaEventoEcuador = DATEADD(HOUR, -5, E.FechaEventoUtc),
    E.BaseDatos,
    E.Esquema,
    E.Objeto,
    ObjetoCompleto = CONCAT(E.BaseDatos, N'.', E.Esquema, N'.', E.Objeto),
    E.Operacion,
    E.CantidadFilas,
    E.ColumnasAfectadas,
    E.ClavesAfectadas,
    E.DatosAntes,
    E.DatosDespues,
    E.MuestraLimitada,
    E.UsuarioAplicacion,
    E.RolAplicacion,
    E.UsuarioIdAplicacion,
    E.OrigenAplicacion,
    E.LoginSql,
    E.UsuarioSql,
    E.HostCliente,
    E.AplicacionCliente,
    E.DireccionCliente,
    E.IdSolicitud,
    E.MetodoHttp,
    E.RutaHttp,
    HashEventoHex = CONVERT(VARCHAR(64), E.HashEvento, 2)
FROM aud.EventoCambio E;
GO

CREATE OR ALTER VIEW rpt.vw_CoberturaAuditoriaIntegracion
AS
SELECT
    B.BaseDatos,
    B.Activa,
    B.CapturarDatos,
    B.MaximoFilasMuestra,
    ObjetosRegistrados = COUNT(C.CoberturaObjetoId),
    ObjetosInstalados = SUM(CASE WHEN C.Instalado = 1 THEN 1 ELSE 0 END),
    ObjetosConError = SUM(CASE WHEN C.Instalado = 0 THEN 1 ELSE 0 END),
    UltimoIntento = MAX(C.FechaUltimoIntento),
    UltimaInstalacion = MAX(C.FechaInstalacion)
FROM aud.BaseAuditada B
LEFT JOIN aud.CoberturaObjeto C ON C.BaseDatos = B.BaseDatos
GROUP BY B.BaseDatos, B.Activa, B.CapturarDatos, B.MaximoFilasMuestra;
GO

CREATE OR ALTER PROCEDURE aud.sp_ConsultarCambios
    @BaseDatos SYSNAME = NULL,
    @Esquema SYSNAME = NULL,
    @Objeto SYSNAME = NULL,
    @Operacion VARCHAR(10) = NULL,
    @Usuario NVARCHAR(256) = NULL,
    @DesdeUtc DATETIME2(3) = NULL,
    @HastaUtc DATETIME2(3) = NULL,
    @Limite INT = 500
AS
BEGIN
    SET NOCOUNT ON;
    SET @Limite = CASE WHEN @Limite < 1 THEN 1 WHEN @Limite > 5000 THEN 5000 ELSE @Limite END;

    SELECT TOP (@Limite) *
    FROM rpt.vw_AuditoriaIntegracion
    WHERE (@BaseDatos IS NULL OR BaseDatos = @BaseDatos)
      AND (@Esquema IS NULL OR Esquema = @Esquema)
      AND (@Objeto IS NULL OR Objeto = @Objeto)
      AND (@Operacion IS NULL OR Operacion = UPPER(@Operacion))
      AND
      (
          @Usuario IS NULL
          OR UsuarioAplicacion LIKE N'%' + @Usuario + N'%'
          OR LoginSql LIKE N'%' + @Usuario + N'%'
      )
      AND (@DesdeUtc IS NULL OR FechaEventoUtc >= @DesdeUtc)
      AND (@HastaUtc IS NULL OR FechaEventoUtc < @HastaUtc)
    ORDER BY EventoCambioId DESC;
END;
GO

CREATE OR ALTER PROCEDURE util.sp_DiagnosticoAuditoriaTotal
AS
BEGIN
    SET NOCOUNT ON;

    SELECT *
    FROM rpt.vw_CoberturaAuditoriaIntegracion
    ORDER BY BaseDatos;

    SELECT TOP (50)
        EventoCambioId, FechaEventoUtc, BaseDatos, Esquema, Objeto,
        Operacion, CantidadFilas, UsuarioAplicacion, RolAplicacion,
        LoginSql, AplicacionCliente, IdSolicitud, RutaHttp
    FROM aud.EventoCambio
    ORDER BY EventoCambioId DESC;
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'aud_writer' AND type = 'R')
    CREATE ROLE aud_writer AUTHORIZATION dbo;
GO

GRANT EXECUTE ON aud.sp_RegistrarCambio TO aud_writer;
GRANT EXECUTE ON aud.sp_RegistrarCobertura TO aud_writer;
GRANT EXECUTE ON aud.sp_RegistrarBaseAuditada TO aud_writer;
GO

DECLARE @UsuarioActual SYSNAME = USER_NAME();
IF @UsuarioActual NOT IN (N'dbo', N'guest', N'INFORMATION_SCHEMA', N'sys')
   AND NOT EXISTS
   (
       SELECT 1
       FROM sys.database_role_members RM
       INNER JOIN sys.database_principals R ON R.principal_id = RM.role_principal_id
       INNER JOIN sys.database_principals U ON U.principal_id = RM.member_principal_id
       WHERE R.name = N'aud_writer'
         AND U.name = @UsuarioActual
   )
BEGIN
    DECLARE @SqlAgregarMiembro NVARCHAR(1000) =
        N'ALTER ROLE aud_writer ADD MEMBER ' + QUOTENAME(@UsuarioActual) + N';';
    EXEC sys.sp_executesql @SqlAgregarMiembro;
END;
GO

DENY INSERT, UPDATE, DELETE ON aud.EventoCambio TO public;
GO

SELECT
    N'Auditoria de integracion central preparada. Ejecute scripts/install_total_audit.py para sincronizar cobertura.' AS Resultado,
    OBJECT_ID(N'aud.EventoCambio', N'U') AS EventoCambioObjectId;
GO
