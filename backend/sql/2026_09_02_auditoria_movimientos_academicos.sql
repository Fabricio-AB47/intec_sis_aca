SET NOCOUNT ON;
SET XACT_ABORT ON;

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
