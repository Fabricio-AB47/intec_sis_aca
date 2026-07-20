USE TITULACION_INTEC;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'tit') EXEC(N'CREATE SCHEMA tit AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'tit.GrupoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.GrupoTitulacion
    (
        GrupoTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GrupoTitulacion PRIMARY KEY,
        MecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreGrupo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoGrupo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        FechaProgramada DATE NULL,
        HoraProgramada TIME NULL,
        Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Modalidad VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        EnlaceVirtual NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        TipoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        LineaInvestigacion NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Tutor NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        LectorOponente NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoGrupo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacion_Estado DEFAULT 'BORRADOR',
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_GrupoTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_GrupoTitulacion_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT CK_GrupoTitulacion_Mecanismo CHECK (MecanismoCodigo IN ('EXAMEN_COMPLEXIVO', 'DEFENSA_GRADO'))
    );
END;
GO

IF COL_LENGTH(N'tit.GrupoTitulacion', N'NombreGrupo') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD NombreGrupo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'CodigoGrupo') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD CodigoGrupo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'FechaProgramada') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD FechaProgramada DATE NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'HoraProgramada') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD HoraProgramada TIME NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Lugar') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Modalidad') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD Modalidad VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'EnlaceVirtual') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD EnlaceVirtual NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'CodigoExamen') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD CodigoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'TipoExamen') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD TipoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'TemaTrabajo') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'LineaInvestigacion') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD LineaInvestigacion NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Tutor') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD Tutor NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'LectorOponente') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD LectorOponente NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'EstadoGrupo') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD EstadoGrupo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Observacion') IS NULL
    ALTER TABLE tit.GrupoTitulacion ADD Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
GO

IF OBJECT_ID(N'tit.GrupoTitulacionExpediente', N'U') IS NULL
BEGIN
    CREATE TABLE tit.GrupoTitulacionExpediente
    (
        GrupoTitulacionExpedienteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GrupoTitulacionExpediente PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NOT NULL,
        OrdenEstudiante INT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_GrupoTitulacionExpediente_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacionExpediente_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_GrupoTitulacionExpediente_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_GrupoTitulacionExpediente_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_GrupoTitulacionExpediente_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId)
    );

    CREATE UNIQUE INDEX UX_GrupoTitulacionExpediente_Activo
        ON tit.GrupoTitulacionExpediente(GrupoTitulacionId, ExpedienteId)
        WHERE Activo = 1;
END;
GO

IF OBJECT_ID(N'tit.EvaluadorTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.EvaluadorTitulacion
    (
        EvaluadorTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EvaluadorTitulacion PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        OrdenEvaluador INT NOT NULL,
        RolEvaluador VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreEvaluador NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CedulaEvaluador VARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        CorreoEvaluador NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_EvaluadorTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_EvaluadorTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_EvaluadorTitulacion_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_EvaluadorTitulacion_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT CK_EvaluadorTitulacion_Orden CHECK (OrdenEvaluador BETWEEN 1 AND 3)
    );

    CREATE UNIQUE INDEX UX_EvaluadorTitulacion_GrupoOrden_Activo
        ON tit.EvaluadorTitulacion(GrupoTitulacionId, OrdenEvaluador)
        WHERE Activo = 1;
END;
GO

IF OBJECT_ID(N'tit.CalificacionEvaluadorTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.CalificacionEvaluadorTitulacion
    (
        CalificacionEvaluadorTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CalificacionEvaluadorTitulacion PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NOT NULL,
        EvaluadorTitulacionId BIGINT NOT NULL,
        NotaTrabajoEscrito DECIMAL(10,2) NULL,
        NotaEvaluacionOral DECIMAL(10,2) NULL,
        NotaTotalSobre20 DECIMAL(10,2) NULL,
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_CalificacionEvaluadorTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_CalificacionEvaluadorTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_CalificacionEvaluadorTitulacion_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_CalificacionEvaluadorTitulacion_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_CalificacionEvaluadorTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_CalificacionEvaluadorTitulacion_Evaluador FOREIGN KEY(EvaluadorTitulacionId) REFERENCES tit.EvaluadorTitulacion(EvaluadorTitulacionId),
        CONSTRAINT CK_CalificacionEvaluadorTitulacion_Trabajo CHECK (NotaTrabajoEscrito IS NULL OR NotaTrabajoEscrito BETWEEN 0 AND 10),
        CONSTRAINT CK_CalificacionEvaluadorTitulacion_Oral CHECK (NotaEvaluacionOral IS NULL OR NotaEvaluacionOral BETWEEN 0 AND 10),
        CONSTRAINT CK_CalificacionEvaluadorTitulacion_Total CHECK (NotaTotalSobre20 IS NULL OR NotaTotalSobre20 BETWEEN 0 AND 20)
    );

    CREATE UNIQUE INDEX UX_CalificacionEvaluadorTitulacion_Activo
        ON tit.CalificacionEvaluadorTitulacion(GrupoTitulacionId, ExpedienteId, EvaluadorTitulacionId)
        WHERE Activo = 1;
END;
GO

MERGE cat.ParametroGeneral AS T
USING (VALUES
    ('TIT_PESO_ASIGNATURAS', N'0.80', N'Peso del promedio de asignaturas en la nota final de grado.'),
    ('TIT_PESO_TITULACION', N'0.20', N'Peso del proceso de titulación en la nota final de grado.'),
    ('TIT_NOTA_MINIMA_APROBACION', N'7.00', N'Nota mínima para aprobar el mecanismo de titulación.'),
    ('TIT_MAX_ESTUDIANTES_DEFENSA', N'2', N'Máximo de estudiantes permitidos en una defensa de grado.'),
    ('TIT_EVALUADORES_REQUERIDOS', N'3', N'Cantidad de evaluadores requerida para calificar titulación.')
) AS S(Codigo, Valor, Descripcion)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN
    UPDATE SET Valor = S.Valor, Descripcion = S.Descripcion, Activo = 1, FechaActualizacion = SYSDATETIME()
WHEN NOT MATCHED THEN
    INSERT(Codigo, Valor, Descripcion, Activo)
    VALUES(S.Codigo, S.Valor, S.Descripcion, 1);
GO

CREATE OR ALTER VIEW rpt.vw_GrupoTitulacionDetalle
AS
SELECT
    G.GrupoTitulacionId,
    G.MecanismoCodigo,
    G.NombreGrupo,
    G.CodigoGrupo,
    G.FechaProgramada,
    G.HoraProgramada,
    G.Lugar,
    G.Modalidad,
    G.EnlaceVirtual,
    G.CodigoExamen,
    G.TipoExamen,
    G.TemaTrabajo,
    G.LineaInvestigacion,
    G.Tutor,
    G.LectorOponente,
    G.EstadoGrupo,
    G.Observacion,
    COUNT(DISTINCT CASE WHEN GE.Activo = 1 THEN GE.ExpedienteId END) AS TotalEstudiantes,
    COUNT(DISTINCT CASE WHEN EV.Activo = 1 THEN EV.EvaluadorTitulacionId END) AS TotalEvaluadores,
    COUNT(DISTINCT CASE WHEN CAL.Activo = 1 THEN CONCAT(CAL.ExpedienteId, ':', CAL.EvaluadorTitulacionId) END) AS TotalCalificaciones,
    STRING_AGG(CONVERT(NVARCHAR(MAX), CASE WHEN EV.Activo = 1 THEN CONCAT(EV.OrdenEvaluador, '. ', EV.RolEvaluador, ': ', EV.NombreEvaluador) END), N'; ')
        WITHIN GROUP (ORDER BY EV.OrdenEvaluador) AS Evaluadores
FROM tit.GrupoTitulacion G
LEFT JOIN tit.GrupoTitulacionExpediente GE
    ON GE.GrupoTitulacionId = G.GrupoTitulacionId
LEFT JOIN tit.EvaluadorTitulacion EV
    ON EV.GrupoTitulacionId = G.GrupoTitulacionId
LEFT JOIN tit.CalificacionEvaluadorTitulacion CAL
    ON CAL.GrupoTitulacionId = G.GrupoTitulacionId
   AND CAL.ExpedienteId = GE.ExpedienteId
   AND CAL.EvaluadorTitulacionId = EV.EvaluadorTitulacionId
   AND CAL.Activo = 1
WHERE G.Activo = 1
GROUP BY
    G.GrupoTitulacionId,
    G.MecanismoCodigo,
    G.NombreGrupo,
    G.CodigoGrupo,
    G.FechaProgramada,
    G.HoraProgramada,
    G.Lugar,
    G.Modalidad,
    G.EnlaceVirtual,
    G.CodigoExamen,
    G.TipoExamen,
    G.TemaTrabajo,
    G.LineaInvestigacion,
    G.Tutor,
    G.LectorOponente,
    G.EstadoGrupo,
    G.Observacion;
GO
