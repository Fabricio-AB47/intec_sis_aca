/* ============================================================================
   INTEC_EXPEDIENTE_ESTUDIANTIL - FLUJO DE EVALUACION DE IDIOMAS

   Parche aditivo e idempotente para:
   - carga temporal y confirmacion definitiva del video;
   - vigencia de la actividad;
   - rubrica y borrador docente;
   - publicacion de la nota;
   - trazabilidad de cada cambio de estado.

   No elimina expedientes, documentos, cargas ni calificaciones existentes.
   ============================================================================ */
USE [INTEC_EXPEDIENTE_ESTUDIANTIL];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'ing.ComponenteExamenIngles', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaInicioActividad') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD FechaInicioActividad DATETIME2 NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaLimiteActividad') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD FechaLimiteActividad DATETIME2 NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'EstadoRevision') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD EstadoRevision VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL
            CONSTRAINT DF_ComponenteExamenIngles_Revision_Migracion DEFAULT 'PENDIENTE_ENTREGA' WITH VALUES;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'NotaBorrador') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD NotaBorrador DECIMAL(4,2) NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'ObservacionBorrador') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD ObservacionBorrador NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'RubricaBorradorJson') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD RubricaBorradorJson NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaBorrador') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD FechaBorrador DATETIME2 NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'UsuarioBorrador') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD UsuarioBorrador NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaPublicacion') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD FechaPublicacion DATETIME2 NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'UsuarioPublicacion') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD UsuarioPublicacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaNotificacionDocente') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD FechaNotificacionDocente DATETIME2 NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'EstadoNotificacion') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD EstadoNotificacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'DetalleNotificacion') IS NULL
        ALTER TABLE ing.ComponenteExamenIngles ADD DetalleNotificacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_ComponenteExamenIngles_NotaBorrador'
          AND parent_object_id = OBJECT_ID(N'ing.ComponenteExamenIngles')
    )
        EXEC(N'ALTER TABLE ing.ComponenteExamenIngles WITH CHECK
            ADD CONSTRAINT CK_ComponenteExamenIngles_NotaBorrador
            CHECK (NotaBorrador IS NULL OR (NotaBorrador >= 0 AND NotaBorrador <= 10));');
END;
GO

IF OBJECT_ID(N'ing.CargaExamenIngles', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'ing.CargaExamenIngles', N'FechaConfirmacion') IS NULL
        ALTER TABLE ing.CargaExamenIngles ADD FechaConfirmacion DATETIME2 NULL;

    IF COL_LENGTH(N'ing.CargaExamenIngles', N'UsuarioConfirmacion') IS NULL
        ALTER TABLE ing.CargaExamenIngles ADD UsuarioConfirmacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;

    IF COL_LENGTH(N'ing.CargaExamenIngles', N'IntegridadValidada') IS NULL
        ALTER TABLE ing.CargaExamenIngles ADD IntegridadValidada BIT NOT NULL
            CONSTRAINT DF_CargaExamenIngles_Integridad_Migracion DEFAULT 0 WITH VALUES;

    IF COL_LENGTH(N'ing.CargaExamenIngles', N'HashIntegridad') IS NULL
        ALTER TABLE ing.CargaExamenIngles ADD HashIntegridad NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_CargaExamenIngles_Tamano_V3'
          AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
    )
    BEGIN
        IF EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_CargaExamenIngles_Tamano'
              AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
            ALTER TABLE ing.CargaExamenIngles DROP CONSTRAINT CK_CargaExamenIngles_Tamano;

        IF EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_CargaExamenIngles_Tamano_V2'
              AND parent_object_id = OBJECT_ID(N'ing.CargaExamenIngles')
        )
            ALTER TABLE ing.CargaExamenIngles DROP CONSTRAINT CK_CargaExamenIngles_Tamano_V2;

        ALTER TABLE ing.CargaExamenIngles WITH CHECK
            ADD CONSTRAINT CK_CargaExamenIngles_Tamano_V3
            CHECK (TamanoEsperado > 0 AND TamanoEsperado <= 2147483648);
    END;
END;
GO

IF OBJECT_ID(N'ing.ExamenIngles', N'U') IS NOT NULL
   AND OBJECT_ID(N'ing.ComponenteExamenIngles', N'U') IS NOT NULL
   AND OBJECT_ID(N'ing.AuditoriaExamenIngles', N'U') IS NULL
BEGIN
    CREATE TABLE ing.AuditoriaExamenIngles
    (
        AuditoriaExamenInglesId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_AuditoriaExamenIngles PRIMARY KEY,
        ExamenInglesId BIGINT NOT NULL,
        ComponenteExamenInglesId BIGINT NULL,
        CargaExamenInglesId UNIQUEIDENTIFIER NULL,
        Evento VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EstadoAnterior VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoNuevo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        Detalle NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        Usuario NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaEvento DATETIME2 NOT NULL
            CONSTRAINT DF_AuditoriaExamenIngles_Fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_AuditoriaExamenIngles_Examen FOREIGN KEY (ExamenInglesId)
            REFERENCES ing.ExamenIngles(ExamenInglesId),
        CONSTRAINT FK_AuditoriaExamenIngles_Componente FOREIGN KEY (ComponenteExamenInglesId)
            REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId)
    );

    CREATE INDEX IX_AuditoriaExamenIngles_ExamenFecha
        ON ing.AuditoriaExamenIngles(ExamenInglesId, FechaEvento DESC);
END;
GO

SELECT
    N'Flujo de evaluación de Idiomas actualizado sin eliminar información.' AS Resultado,
    OBJECT_ID(N'ing.AuditoriaExamenIngles', N'U') AS AuditoriaExamenInglesId;
GO
