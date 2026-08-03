USE INTECBDD;
GO

IF OBJECT_ID(N'dbo.AUD_EXCEPCION_PRERREQUISITO', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AUD_EXCEPCION_PRERREQUISITO
    (
        IdExcepcion BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_AUD_EXCEPCION_PRERREQUISITO PRIMARY KEY,
        codigo_estud INT NOT NULL,
        cod_anio_basica INT NOT NULL,
        codigo_periodo INT NOT NULL,
        codigo_materia INT NOT NULL,
        materias_previas_pendientes NVARCHAR(500) NOT NULL,
        motivo NVARCHAR(1000) NOT NULL,
        usuario NVARCHAR(128) NOT NULL,
        fecha_registro DATETIME2 NOT NULL
            CONSTRAINT DF_AUD_EXCEPCION_PRERREQUISITO_FECHA DEFAULT SYSDATETIME()
    );

    CREATE INDEX IX_AUD_EXCEPCION_PRERREQUISITO_ESTUDIANTE
        ON dbo.AUD_EXCEPCION_PRERREQUISITO
        (codigo_estud, codigo_periodo, codigo_materia, fecha_registro DESC);
END;
GO
