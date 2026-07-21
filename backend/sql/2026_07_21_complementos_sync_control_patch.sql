/* Completa las tablas de control omitidas durante la instalacion V6/V5. */
SET NOCOUNT ON;
GO

USE INTEC_EXPEDIENTE_ESTUDIANTIL;
GO

IF OBJECT_ID(N'integ.EjecucionSincronizacion', N'U') IS NULL
BEGIN
    CREATE TABLE integ.EjecucionSincronizacion
    (
        EjecucionSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Exp_EjecucionSync PRIMARY KEY,
        ProcesoCodigo VARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_Exp_Sync_Inicio DEFAULT SYSDATETIME(),
        FechaFin DATETIME2 NULL,
        FilasProcesadas BIGINT NULL,
        UsuarioEjecucion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        Mensaje NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL
    );
END;
GO

IF OBJECT_ID(N'integ.ErrorSincronizacion', N'U') IS NULL
BEGIN
    CREATE TABLE integ.ErrorSincronizacion
    (
        ErrorSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Exp_ErrorSync PRIMARY KEY,
        EjecucionSincronizacionId BIGINT NULL,
        NumeroError INT NULL,
        ProcedimientoError NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
        LineaError INT NULL,
        MensajeError NVARCHAR(4000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaError DATETIME2 NOT NULL CONSTRAINT DF_Exp_ErrorSync_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_Exp_ErrorSync_Ejecucion FOREIGN KEY(EjecucionSincronizacionId)
            REFERENCES integ.EjecucionSincronizacion(EjecucionSincronizacionId)
    );
END;
GO

USE INTEC_FINANZAS_INSTITUCIONAL;
GO

IF OBJECT_ID(N'integ.EjecucionSincronizacion', N'U') IS NULL
BEGIN
    CREATE TABLE integ.EjecucionSincronizacion
    (
        EjecucionSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Fin_EjecucionSync PRIMARY KEY,
        ProcesoCodigo VARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_Fin_Sync_Inicio DEFAULT SYSDATETIME(),
        FechaFin DATETIME2 NULL,
        FilasProcesadas BIGINT NULL,
        UsuarioEjecucion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        Mensaje NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL
    );
END;
GO

IF OBJECT_ID(N'integ.ErrorSincronizacion', N'U') IS NULL
BEGIN
    CREATE TABLE integ.ErrorSincronizacion
    (
        ErrorSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Fin_ErrorSync PRIMARY KEY,
        EjecucionSincronizacionId BIGINT NULL,
        NumeroError INT NULL,
        ProcedimientoError NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
        LineaError INT NULL,
        MensajeError NVARCHAR(4000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaError DATETIME2 NOT NULL CONSTRAINT DF_Fin_ErrorSync_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_Fin_ErrorSync_Ejecucion FOREIGN KEY(EjecucionSincronizacionId)
            REFERENCES integ.EjecucionSincronizacion(EjecucionSincronizacionId)
    );
END;
GO

SELECT DB_NAME() AS BaseDatos, N'Parche de control de sincronizacion aplicado.' AS Resultado;
GO
