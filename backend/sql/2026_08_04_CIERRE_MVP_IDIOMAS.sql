USE [INTEC_EXPEDIENTE_ESTUDIANTIL];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'ing.ExamenIngles', N'U') IS NULL
   OR OBJECT_ID(N'ing.ComponenteExamenIngles', N'U') IS NULL
   OR OBJECT_ID(N'ing.CargaExamenIngles', N'U') IS NULL
BEGIN
    THROW 51001, 'Primero instale las tablas base del modulo de Idiomas.', 1;
END;
GO

IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'InstruccionesActividad') IS NULL
    ALTER TABLE ing.ComponenteExamenIngles
        ADD InstruccionesActividad NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL;

IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'NumeroReaperturas') IS NULL
    ALTER TABLE ing.ComponenteExamenIngles
        ADD NumeroReaperturas INT NOT NULL
            CONSTRAINT DF_ComponenteExamenIngles_Reaperturas_Migracion DEFAULT 0 WITH VALUES;

IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'FechaUltimaReapertura') IS NULL
    ALTER TABLE ing.ComponenteExamenIngles ADD FechaUltimaReapertura DATETIME2 NULL;

IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'MotivoUltimaReapertura') IS NULL
    ALTER TABLE ing.ComponenteExamenIngles
        ADD MotivoUltimaReapertura NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;

IF COL_LENGTH(N'ing.ComponenteExamenIngles', N'UsuarioUltimaReapertura') IS NULL
    ALTER TABLE ing.ComponenteExamenIngles
        ADD UsuarioUltimaReapertura NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;
GO

BEGIN TRANSACTION;

IF OBJECT_ID(N'ing.ConfiguracionActividadIngles', N'U') IS NULL
BEGIN
    CREATE TABLE ing.ConfiguracionActividadIngles
    (
        ConfiguracionActividadInglesId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ConfiguracionActividadIngles PRIMARY KEY,
        CodigoPeriodo NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoMateria NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoComponente VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NumeroParcial TINYINT NOT NULL,
        Nombre NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Instrucciones NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaInicioActividad DATETIME2 NOT NULL,
        FechaLimiteActividad DATETIME2 NOT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_ConfiguracionActividadIngles_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL
            CONSTRAINT DF_ConfiguracionActividadIngles_Fecha DEFAULT SYSUTCDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        UsuarioActualizacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CONSTRAINT UQ_ConfiguracionActividadIngles_Alcance
            UNIQUE (CodigoPeriodo, CodigoMateria, CodigoComponente),
        CONSTRAINT CK_ConfiguracionActividadIngles_Componente
            CHECK (CodigoComponente IN ('P1', 'P2', 'P3')),
        CONSTRAINT CK_ConfiguracionActividadIngles_Fechas
            CHECK (FechaLimiteActividad > FechaInicioActividad)
    );
END;

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'ing.ConfiguracionActividadIngles')
      AND name = N'IX_ConfiguracionActividadIngles_Consulta'
)
    CREATE INDEX IX_ConfiguracionActividadIngles_Consulta
        ON ing.ConfiguracionActividadIngles(CodigoPeriodo, CodigoMateria, Activo, NumeroParcial);

IF OBJECT_ID(N'ing.AuditoriaConfiguracionActividadIngles', N'U') IS NULL
BEGIN
    CREATE TABLE ing.AuditoriaConfiguracionActividadIngles
    (
        AuditoriaConfiguracionActividadInglesId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_AuditoriaConfiguracionActividadIngles PRIMARY KEY,
        ConfiguracionActividadInglesId BIGINT NOT NULL,
        CodigoPeriodo NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoMateria NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoComponente VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        InstruccionesAnteriores NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
        InstruccionesNuevas NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaInicioAnterior DATETIME2 NULL,
        FechaLimiteAnterior DATETIME2 NULL,
        FechaInicioNueva DATETIME2 NOT NULL,
        FechaLimiteNueva DATETIME2 NOT NULL,
        ComponentesActualizados INT NOT NULL,
        ComponentesOmitidos INT NOT NULL,
        Usuario NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaEvento DATETIME2 NOT NULL
            CONSTRAINT DF_AuditoriaConfiguracionActividadIngles_Fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_AuditoriaConfiguracionActividadIngles_Configuracion
            FOREIGN KEY (ConfiguracionActividadInglesId)
            REFERENCES ing.ConfiguracionActividadIngles(ConfiguracionActividadInglesId)
    );
END;

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'ing.AuditoriaConfiguracionActividadIngles')
      AND name = N'IX_AuditoriaConfiguracionActividadIngles_AlcanceFecha'
)
    CREATE INDEX IX_AuditoriaConfiguracionActividadIngles_AlcanceFecha
        ON ing.AuditoriaConfiguracionActividadIngles
            (CodigoPeriodo, CodigoMateria, CodigoComponente, FechaEvento DESC);

IF OBJECT_ID(N'ing.ReaperturaExamenIngles', N'U') IS NULL
BEGIN
    CREATE TABLE ing.ReaperturaExamenIngles
    (
        ReaperturaExamenInglesId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ReaperturaExamenIngles PRIMARY KEY,
        ExamenInglesId BIGINT NOT NULL,
        ComponenteExamenInglesId BIGINT NOT NULL,
        CargaExamenInglesId UNIQUEIDENTIFIER NULL,
        EstadoAnterior VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        FechaLimiteAnterior DATETIME2 NULL,
        NuevaFechaLimite DATETIME2 NOT NULL,
        Motivo NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        UsuarioResponsable NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaReapertura DATETIME2 NOT NULL
            CONSTRAINT DF_ReaperturaExamenIngles_Fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ReaperturaExamenIngles_Examen
            FOREIGN KEY (ExamenInglesId) REFERENCES ing.ExamenIngles(ExamenInglesId),
        CONSTRAINT FK_ReaperturaExamenIngles_Componente
            FOREIGN KEY (ComponenteExamenInglesId)
            REFERENCES ing.ComponenteExamenIngles(ComponenteExamenInglesId),
        CONSTRAINT FK_ReaperturaExamenIngles_Carga
            FOREIGN KEY (CargaExamenInglesId)
            REFERENCES ing.CargaExamenIngles(CargaExamenInglesId)
    );
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'ing.ReaperturaExamenIngles')
      AND name = N'IX_ReaperturaExamenIngles_ComponenteFecha'
)
    CREATE INDEX IX_ReaperturaExamenIngles_ComponenteFecha
        ON ing.ReaperturaExamenIngles(ComponenteExamenInglesId, FechaReapertura DESC);

/* Toda matricula de Idiomas trabaja con P1, P2 y P3, incluso si proviene de
   una instalacion anterior que utilizaba un unico componente. */
INSERT INTO ing.ComponenteExamenIngles
(
    ExamenInglesId, Codigo, NumeroParcial, Nombre, TipoEvaluacion,
    FechaInicioActividad, FechaLimiteActividad, InstruccionesActividad,
    UsuarioActualizacion
)
SELECT
    examen.ExamenInglesId,
    parcial.Codigo,
    parcial.NumeroParcial,
    parcial.Nombre,
    'VIDEO',
    referencia.FechaInicioActividad,
    referencia.FechaLimiteActividad,
    COALESCE(
        NULLIF(referencia.InstruccionesActividad, N''),
        CONCAT(N'Entregue el video correspondiente a ', parcial.Nombre, N'.')
    ),
    N'migracion-cierre-mvp-idiomas'
FROM ing.ExamenIngles examen
CROSS JOIN
(
    VALUES
        ('P1', CONVERT(TINYINT, 1), N'Parcial 1'),
        ('P2', CONVERT(TINYINT, 2), N'Parcial 2'),
        ('P3', CONVERT(TINYINT, 3), N'Parcial 3')
) parcial(Codigo, NumeroParcial, Nombre)
OUTER APPLY
(
    SELECT TOP (1)
        componente.FechaInicioActividad,
        componente.FechaLimiteActividad,
        componente.InstruccionesActividad
    FROM ing.ComponenteExamenIngles componente
    WHERE componente.ExamenInglesId = examen.ExamenInglesId
    ORDER BY
        CASE WHEN componente.Codigo = 'P1' THEN 0 ELSE 1 END,
        componente.ComponenteExamenInglesId
) referencia
WHERE examen.Activo = 1
  AND NOT EXISTS
  (
      SELECT 1
      FROM ing.ComponenteExamenIngles existente
      WHERE existente.ExamenInglesId = examen.ExamenInglesId
        AND existente.Codigo = parcial.Codigo
  );

UPDATE componente
   SET InstruccionesActividad = COALESCE(
           NULLIF(LTRIM(RTRIM(componente.InstruccionesActividad)), N''),
           CONCAT(N'Entregue el video correspondiente a ', componente.Nombre, N'.')
       ),
       FechaInicioActividad = COALESCE(
           componente.FechaInicioActividad,
           DATEADD(HOUR, 5, TRY_CONVERT(DATETIME2, periodo.fechain))
       ),
       FechaLimiteActividad = COALESCE(
           componente.FechaLimiteActividad,
           DATEADD(
               MILLISECOND,
               -1,
               DATEADD(HOUR, 5, DATEADD(DAY, 1, TRY_CONVERT(DATETIME2, periodo.fechafin)))
           )
       ),
       FechaActualizacion = SYSUTCDATETIME(),
       UsuarioActualizacion = N'migracion-cierre-mvp-idiomas'
FROM ing.ComponenteExamenIngles componente
INNER JOIN ing.ExamenIngles examen
    ON examen.ExamenInglesId = componente.ExamenInglesId
LEFT JOIN INTECBDD.dbo.PERIODO periodo
    ON TRY_CONVERT(INT, periodo.cod_periodo) = TRY_CONVERT(INT, examen.CodigoPeriodo)
WHERE componente.Codigo IN ('P1', 'P2', 'P3')
  AND
  (
      NULLIF(LTRIM(RTRIM(componente.InstruccionesActividad)), N'') IS NULL
      OR (componente.FechaInicioActividad IS NULL AND periodo.fechain IS NOT NULL)
      OR (componente.FechaLimiteActividad IS NULL AND periodo.fechafin IS NOT NULL)
  );

UPDATE carga
   SET ComponenteExamenInglesId = parcial_uno.ComponenteExamenInglesId
FROM ing.CargaExamenIngles carga
INNER JOIN ing.ComponenteExamenIngles legado
    ON legado.ComponenteExamenInglesId = carga.ComponenteExamenInglesId
INNER JOIN ing.ComponenteExamenIngles parcial_uno
    ON parcial_uno.ExamenInglesId = carga.ExamenInglesId
   AND parcial_uno.Codigo = 'P1'
WHERE legado.Codigo NOT IN ('P1', 'P2', 'P3');

;WITH versiones_activas AS
(
    SELECT
        carga.CargaExamenInglesId,
        ROW_NUMBER() OVER
        (
            PARTITION BY carga.ComponenteExamenInglesId
            ORDER BY carga.NumeroVersion DESC, carga.FechaCarga DESC,
                     carga.CargaExamenInglesId DESC
        ) AS orden
    FROM ing.CargaExamenIngles carga
    WHERE carga.Activo = 1
      AND carga.ComponenteExamenInglesId IS NOT NULL
)
UPDATE carga
   SET Activo = 0,
       Estado = CASE WHEN carga.Estado IN ('CONFIRMADO', 'CARGADO')
                     THEN 'VERSION_ANTERIOR' ELSE carga.Estado END
FROM ing.CargaExamenIngles carga
INNER JOIN versiones_activas version
    ON version.CargaExamenInglesId = carga.CargaExamenInglesId
WHERE version.orden > 1;

UPDATE ing.ComponenteExamenIngles
   SET Activo = 0,
       FechaActualizacion = SYSUTCDATETIME(),
       UsuarioActualizacion = N'migracion-cierre-mvp-idiomas'
WHERE Codigo NOT IN ('P1', 'P2', 'P3')
  AND Activo = 1;

;WITH configuraciones_origen AS
(
    SELECT
        TRY_CONVERT(NVARCHAR(100), examen.CodigoPeriodo) AS CodigoPeriodo,
        TRY_CONVERT(NVARCHAR(100), examen.CodigoMateria) AS CodigoMateria,
        componente.Codigo AS CodigoComponente,
        componente.NumeroParcial,
        componente.Nombre,
        componente.InstruccionesActividad,
        componente.FechaInicioActividad,
        componente.FechaLimiteActividad,
        ROW_NUMBER() OVER
        (
            PARTITION BY examen.CodigoPeriodo, examen.CodigoMateria, componente.Codigo
            ORDER BY COALESCE(componente.FechaActualizacion, componente.FechaCreacion) DESC,
                     componente.ComponenteExamenInglesId DESC
        ) AS orden
    FROM ing.ExamenIngles examen
    INNER JOIN ing.ComponenteExamenIngles componente
        ON componente.ExamenInglesId = examen.ExamenInglesId
    WHERE examen.Activo = 1
      AND componente.Activo = 1
      AND componente.Codigo IN ('P1', 'P2', 'P3')
      AND examen.CodigoPeriodo IS NOT NULL
      AND examen.CodigoMateria IS NOT NULL
      AND componente.FechaInicioActividad IS NOT NULL
      AND componente.FechaLimiteActividad IS NOT NULL
)
INSERT INTO ing.ConfiguracionActividadIngles
(
    CodigoPeriodo, CodigoMateria, CodigoComponente, NumeroParcial, Nombre,
    Instrucciones, FechaInicioActividad, FechaLimiteActividad, UsuarioActualizacion
)
SELECT
    origen.CodigoPeriodo,
    origen.CodigoMateria,
    origen.CodigoComponente,
    origen.NumeroParcial,
    origen.Nombre,
    COALESCE(
        NULLIF(LTRIM(RTRIM(origen.InstruccionesActividad)), N''),
        CONCAT(N'Entregue el video correspondiente a ', origen.Nombre, N'.')
    ),
    origen.FechaInicioActividad,
    origen.FechaLimiteActividad,
    N'migracion-configuracion-idiomas'
FROM configuraciones_origen origen
WHERE origen.orden = 1
  AND origen.FechaLimiteActividad > origen.FechaInicioActividad
  AND NOT EXISTS
  (
      SELECT 1
      FROM ing.ConfiguracionActividadIngles configuracion
      WHERE configuracion.CodigoPeriodo = origen.CodigoPeriodo
        AND configuracion.CodigoMateria = origen.CodigoMateria
        AND configuracion.CodigoComponente = origen.CodigoComponente
  );

COMMIT TRANSACTION;
GO

SELECT
    ComponentesActivos = COUNT_BIG(*),
    MatriculasConTresParciales = COUNT_BIG(DISTINCT ExamenInglesId)
FROM ing.ComponenteExamenIngles
WHERE Activo = 1
  AND Codigo IN ('P1', 'P2', 'P3');
GO
