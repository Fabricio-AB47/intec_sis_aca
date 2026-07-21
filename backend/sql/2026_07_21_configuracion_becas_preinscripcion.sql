USE INTEC_FINANZAS_INSTITUCIONAL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat')
    EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'cat.ConfiguracionBecaPreinscripcion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.ConfiguracionBecaPreinscripcion
    (
        ConfiguracionBecaId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ConfiguracionBecaPreinscripcion PRIMARY KEY,
        Codigo VARCHAR(50) NOT NULL,
        Nombre NVARCHAR(150) NOT NULL,
        EsVariable BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_EsVariable DEFAULT 0,
        PorcentajeFijo DECIMAL(9,2) NULL,
        PorcentajeMinimo DECIMAL(9,2) NULL,
        PorcentajeMaximo DECIMAL(9,2) NULL,
        Protegida BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_Protegida DEFAULT 0,
        Activo BIT NOT NULL CONSTRAINT DF_ConfiguracionBeca_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_ConfiguracionBeca_Fecha DEFAULT SYSDATETIME(),
        UsuarioCreacion NVARCHAR(128) NULL,
        FechaActualizacion DATETIME2 NULL,
        UsuarioActualizacion NVARCHAR(128) NULL,
        CONSTRAINT UQ_ConfiguracionBeca_Codigo UNIQUE(Codigo),
        CONSTRAINT CK_ConfiguracionBeca_Porcentajes CHECK
        (
            (PorcentajeFijo IS NULL OR PorcentajeFijo BETWEEN 0 AND 100)
            AND (PorcentajeMinimo IS NULL OR PorcentajeMinimo BETWEEN 0 AND 100)
            AND (PorcentajeMaximo IS NULL OR PorcentajeMaximo BETWEEN 0 AND 100)
        )
    );
END;
GO

MERGE cat.ConfiguracionBecaPreinscripcion AS target
USING (VALUES ('BECA_MINTEL', N'Beca Mintel', CAST(0 AS BIT), 100.00, 100.00, 100.00, CAST(1 AS BIT), CAST(1 AS BIT)))
    AS source(Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo, PorcentajeMaximo, Protegida, Activo)
ON target.Codigo = source.Codigo OR target.Nombre = source.Nombre
WHEN MATCHED THEN UPDATE SET
    Codigo = source.Codigo,
    Nombre = source.Nombre,
    EsVariable = source.EsVariable,
    PorcentajeFijo = source.PorcentajeFijo,
    PorcentajeMinimo = source.PorcentajeMinimo,
    PorcentajeMaximo = source.PorcentajeMaximo,
    Protegida = source.Protegida,
    Activo = source.Activo,
    FechaActualizacion = SYSDATETIME(),
    UsuarioActualizacion = N'MIGRACION'
WHEN NOT MATCHED THEN INSERT
    (Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo, PorcentajeMaximo, Protegida, Activo, UsuarioCreacion)
VALUES
    (source.Codigo, source.Nombre, source.EsVariable, source.PorcentajeFijo, source.PorcentajeMinimo, source.PorcentajeMaximo, source.Protegida, source.Activo, N'MIGRACION');
GO

IF NOT EXISTS (SELECT 1 FROM cat.ConfiguracionBecaPreinscripcion WHERE Codigo = 'BECA_INTEC')
BEGIN
    INSERT INTO cat.ConfiguracionBecaPreinscripcion
        (Codigo, Nombre, EsVariable, PorcentajeFijo, PorcentajeMinimo, PorcentajeMaximo, Protegida, Activo, UsuarioCreacion)
    VALUES
        ('BECA_INTEC', N'Beca Intec', 1, NULL, 0.00, 100.00, 0, 1, N'MIGRACION');
END;
GO
