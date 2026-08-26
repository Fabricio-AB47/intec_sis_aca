/* ============================================================================
   INTEC_INTEGRACION_CONTROL - HISTORICO DE INTEGRACIONES E INFORMES DOCENTES

   Parche aditivo e idempotente. Complementa aud.EventoCambio con el ciclo de
   vida documental del informe de cumplimiento docente. Nunca almacena el
   certificado electronico, su clave ni el contenido de los documentos.
   ============================================================================ */
USE [INTEC_INTEGRACION_CONTROL];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud')
    EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt')
    EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'aud.EventoInformeDocente', N'U') IS NULL
BEGIN
    CREATE TABLE aud.EventoInformeDocente
    (
        EventoInformeId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_AudEventoInformeDocente PRIMARY KEY,
        FechaEventoUtc DATETIME2(3) NOT NULL
            CONSTRAINT DF_AudEventoInformeDocente_Fecha DEFAULT SYSUTCDATETIME(),
        Etapa VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Estado VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        TipoDocumento VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoDocente NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        CedulaDocente NVARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        NombreDocente NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoMateria NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NombreMateria NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        PeriodosJson NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        Paralelo NVARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        Jornada NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NombreArchivo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        RutaDocumento NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
        UrlDocumento NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        CantidadEstudiantes INT NULL,
        UsuarioAplicacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        RolAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioIdAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        OrigenAplicacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        IdSolicitud NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        MetodoHttp VARCHAR(10) COLLATE Modern_Spanish_CI_AS NULL,
        RutaHttp NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Detalle NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        MetadatosJson NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        HashEvento VARBINARY(32) NULL,
        CONSTRAINT CK_AudEventoInforme_Etapa
            CHECK (Etapa IN ('GENERADO', 'FIRMADO', 'ARCHIVADO', 'ERROR')),
        CONSTRAINT CK_AudEventoInforme_Estado
            CHECK (Estado IN ('EXITOSO', 'ERROR')),
        CONSTRAINT CK_AudEventoInforme_Estudiantes
            CHECK (CantidadEstudiantes IS NULL OR CantidadEstudiantes >= 0)
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'aud.EventoInformeDocente')
      AND name = N'IX_AudEventoInforme_Fecha'
)
    CREATE INDEX IX_AudEventoInforme_Fecha
        ON aud.EventoInformeDocente(FechaEventoUtc DESC, EventoInformeId DESC)
        INCLUDE(Etapa, Estado, TipoDocumento, CodigoDocente, CodigoMateria);
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'aud.EventoInformeDocente')
      AND name = N'IX_AudEventoInforme_DocenteFecha'
)
    CREATE INDEX IX_AudEventoInforme_DocenteFecha
        ON aud.EventoInformeDocente(CodigoDocente, FechaEventoUtc DESC)
        INCLUDE(Etapa, Estado, CodigoMateria, NombreArchivo, UsuarioAplicacion);
GO

CREATE OR ALTER VIEW rpt.vw_HistoricoInformeDocente
AS
    SELECT
        evento.*,
        DATEADD(MINUTE, -300, evento.FechaEventoUtc) AS FechaEventoEcuador,
        CONVERT(VARCHAR(64), evento.HashEvento, 2) AS HashEventoHex
    FROM aud.EventoInformeDocente AS evento;
GO

-- No se conceden ni deniegan permisos a public. La aplicación conserva el
-- modelo de permisos configurado para su usuario de conexión y la consulta
-- funcional se expone únicamente mediante la API protegida por pantalla.
