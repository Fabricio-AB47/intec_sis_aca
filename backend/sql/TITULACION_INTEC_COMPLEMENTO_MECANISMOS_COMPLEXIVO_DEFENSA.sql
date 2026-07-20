USE TITULACION_INTEC;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'tit') EXEC(N'CREATE SCHEMA tit AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'cat.MecanismoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.MecanismoTitulacion
    (
        MecanismoTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_MecanismoTitulacion PRIMARY KEY,
        Codigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_MecanismoTitulacion_Codigo UNIQUE,
        Nombre NVARCHAR(180) COLLATE Modern_Spanish_CI_AS NOT NULL,
        RequiereProgramacion BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Programacion DEFAULT 1,
        RequiereTribunal BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Tribunal DEFAULT 1,
        NotaMinima DECIMAL(10,2) NOT NULL CONSTRAINT DF_MecanismoTitulacion_NotaMinima DEFAULT 7,
        Activo BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_MecanismoTitulacion_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

MERGE cat.MecanismoTitulacion AS T
USING (VALUES
    ('EXAMEN_COMPLEXIVO', N'Examen complexivo', 1, 1, 7.00),
    ('DEFENSA_GRADO', N'Defensa de grado', 1, 1, 7.00)
) AS S(Codigo, Nombre, RequiereProgramacion, RequiereTribunal, NotaMinima)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN
    UPDATE SET Nombre = S.Nombre, RequiereProgramacion = S.RequiereProgramacion, RequiereTribunal = S.RequiereTribunal, NotaMinima = S.NotaMinima, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(Codigo, Nombre, RequiereProgramacion, RequiereTribunal, NotaMinima)
    VALUES(S.Codigo, S.Nombre, S.RequiereProgramacion, S.RequiereTribunal, S.NotaMinima);
GO

IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'MecanismoTitulacionId') IS NULL
BEGIN
    ALTER TABLE tit.ExpedienteTitulacion ADD MecanismoTitulacionId VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
END;
GO

IF OBJECT_ID(N'tit.ProgramacionTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.ProgramacionTitulacion
    (
        ProgramacionTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProgramacionTitulacion PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL,
        MecanismoTitulacionId INT NOT NULL,
        FechaProgramada DATE NOT NULL,
        HoraProgramada TIME NULL,
        Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Modalidad VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        EnlaceVirtual NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoProgramacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Estado DEFAULT 'PROGRAMADA',
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Usuario DEFAULT SYSTEM_USER,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Fecha DEFAULT SYSDATETIME(),
        Activo BIT NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Activo DEFAULT 1,
        CONSTRAINT FK_ProgramacionTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_ProgramacionTitulacion_Mecanismo FOREIGN KEY(MecanismoTitulacionId) REFERENCES cat.MecanismoTitulacion(MecanismoTitulacionId)
    );
END;
GO

IF OBJECT_ID(N'tit.TribunalTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.TribunalTitulacion
    (
        TribunalTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TribunalTitulacion PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL,
        MecanismoTitulacionId INT NOT NULL,
        RolTribunal VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreMiembro NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CedulaMiembro VARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        CorreoMiembro NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        OrdenFirma INT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_TribunalTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_TribunalTitulacion_Usuario DEFAULT SYSTEM_USER,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_TribunalTitulacion_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_TribunalTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_TribunalTitulacion_Mecanismo FOREIGN KEY(MecanismoTitulacionId) REFERENCES cat.MecanismoTitulacion(MecanismoTitulacionId)
    );
END;
GO

IF OBJECT_ID(N'tit.ExamenComplexivo', N'U') IS NULL
BEGIN
    CREATE TABLE tit.ExamenComplexivo
    (
        ExamenComplexivoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ExamenComplexivo PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL CONSTRAINT UQ_ExamenComplexivo_Expediente UNIQUE,
        ProgramacionTitulacionId BIGINT NULL,
        CodigoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        TipoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        NotaExamen DECIMAL(10,2) NULL,
        NotaPonderada20 DECIMAL(10,2) NULL,
        Aprobado BIT NOT NULL CONSTRAINT DF_ExamenComplexivo_Aprobado DEFAULT 0,
        RutaEvidencia NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExamenComplexivo_Usuario DEFAULT SYSTEM_USER,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ExamenComplexivo_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_ExamenComplexivo_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_ExamenComplexivo_Programacion FOREIGN KEY(ProgramacionTitulacionId) REFERENCES tit.ProgramacionTitulacion(ProgramacionTitulacionId)
    );
END;
GO

IF OBJECT_ID(N'tit.DefensaGrado', N'U') IS NULL
BEGIN
    CREATE TABLE tit.DefensaGrado
    (
        DefensaGradoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DefensaGrado PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL CONSTRAINT UQ_DefensaGrado_Expediente UNIQUE,
        ProgramacionTitulacionId BIGINT NULL,
        TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        LineaInvestigacion NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Tutor NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        LectorOponente NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL,
        NotaTrabajoEscrito DECIMAL(10,2) NULL,
        NotaDefensaOral DECIMAL(10,2) NULL,
        NotaFinalDefensa DECIMAL(10,2) NULL,
        NotaPonderada20 DECIMAL(10,2) NULL,
        Aprobado BIT NOT NULL CONSTRAINT DF_DefensaGrado_Aprobado DEFAULT 0,
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_DefensaGrado_Usuario DEFAULT SYSTEM_USER,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_DefensaGrado_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_DefensaGrado_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_DefensaGrado_Programacion FOREIGN KEY(ProgramacionTitulacionId) REFERENCES tit.ProgramacionTitulacion(ProgramacionTitulacionId)
    );
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_SeleccionarMecanismoTitulacion
    @ExpedienteId BIGINT,
    @MecanismoCodigo VARCHAR(40),
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @MecanismoId INT;
    SELECT @MecanismoId = MecanismoTitulacionId
    FROM cat.MecanismoTitulacion
    WHERE Codigo COLLATE Modern_Spanish_CI_AS = @MecanismoCodigo COLLATE Modern_Spanish_CI_AS
      AND Activo = 1;

    IF @MecanismoId IS NULL THROW 59601, 'Mecanismo de titulación no válido.', 1;
    IF NOT EXISTS (SELECT 1 FROM tit.ExpedienteTitulacion WHERE ExpedienteId = @ExpedienteId) THROW 59602, 'No existe expediente de titulación.', 1;

    UPDATE tit.ExpedienteTitulacion
       SET MecanismoTitulacionId = @MecanismoCodigo,
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;

    SELECT @ExpedienteId AS ExpedienteId, @MecanismoCodigo AS MecanismoCodigo, N'Mecanismo seleccionado correctamente.' AS Mensaje;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_ProgramarExamenComplexivo
    @ExpedienteId BIGINT,
    @FechaProgramada DATE,
    @HoraProgramada TIME = NULL,
    @Lugar NVARCHAR(250) = NULL,
    @Modalidad VARCHAR(30) = NULL,
    @EnlaceVirtual NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @MecanismoId INT = (SELECT MecanismoTitulacionId FROM cat.MecanismoTitulacion WHERE Codigo = 'EXAMEN_COMPLEXIVO');
    DECLARE @ProgramacionId BIGINT;

    EXEC tit.sp_SeleccionarMecanismoTitulacion @ExpedienteId, 'EXAMEN_COMPLEXIVO', @Usuario;

    SELECT TOP 1 @ProgramacionId = ProgramacionTitulacionId
    FROM tit.ProgramacionTitulacion
    WHERE ExpedienteId = @ExpedienteId AND MecanismoTitulacionId = @MecanismoId AND Activo = 1
    ORDER BY ProgramacionTitulacionId DESC;

    IF @ProgramacionId IS NULL
    BEGIN
        INSERT INTO tit.ProgramacionTitulacion(ExpedienteId, MecanismoTitulacionId, FechaProgramada, HoraProgramada, Lugar, Modalidad, EnlaceVirtual, UsuarioRegistro)
        VALUES(@ExpedienteId, @MecanismoId, @FechaProgramada, @HoraProgramada, @Lugar, @Modalidad, @EnlaceVirtual, COALESCE(@Usuario, SYSTEM_USER));
        SET @ProgramacionId = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE tit.ProgramacionTitulacion
           SET FechaProgramada = @FechaProgramada, HoraProgramada = @HoraProgramada, Lugar = @Lugar, Modalidad = @Modalidad, EnlaceVirtual = @EnlaceVirtual, EstadoProgramacion = 'PROGRAMADA'
         WHERE ProgramacionTitulacionId = @ProgramacionId;
    END;

    IF NOT EXISTS (SELECT 1 FROM tit.ExamenComplexivo WHERE ExpedienteId = @ExpedienteId)
        INSERT INTO tit.ExamenComplexivo(ExpedienteId, ProgramacionTitulacionId, UsuarioRegistro) VALUES(@ExpedienteId, @ProgramacionId, COALESCE(@Usuario, SYSTEM_USER));
    ELSE
        UPDATE tit.ExamenComplexivo SET ProgramacionTitulacionId = @ProgramacionId, FechaActualizacion = SYSDATETIME() WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_CalificarExamenComplexivo
    @ExpedienteId BIGINT,
    @NotaExamen DECIMAL(10,2),
    @CodigoExamen VARCHAR(80) = NULL,
    @TipoExamen VARCHAR(80) = NULL,
    @RutaEvidencia NVARCHAR(1000) = NULL,
    @Observacion NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @NotaExamen < 0 OR @NotaExamen > 10 THROW 59610, 'La nota del examen debe estar entre 0 y 10.', 1;

    DECLARE @MecanismoId INT = (SELECT MecanismoTitulacionId FROM cat.MecanismoTitulacion WHERE Codigo = 'EXAMEN_COMPLEXIVO');
    DECLARE @NotaMinima DECIMAL(10,2) = ISNULL(TRY_CONVERT(DECIMAL(10,2), (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'NOTA_MINIMA_TITULACION')), 7);
    DECLARE @Ponderada DECIMAL(10,2) = ROUND(@NotaExamen * 0.20, 2);
    DECLARE @Aprobado BIT = CASE WHEN @NotaExamen >= @NotaMinima THEN 1 ELSE 0 END;

    EXEC tit.sp_SeleccionarMecanismoTitulacion @ExpedienteId, 'EXAMEN_COMPLEXIVO', @Usuario;

    IF NOT EXISTS (SELECT 1 FROM tit.ExamenComplexivo WHERE ExpedienteId = @ExpedienteId)
        INSERT INTO tit.ExamenComplexivo(ExpedienteId, CodigoExamen, TipoExamen, NotaExamen, NotaPonderada20, Aprobado, RutaEvidencia, Observacion, UsuarioRegistro)
        VALUES(@ExpedienteId, @CodigoExamen, @TipoExamen, @NotaExamen, @Ponderada, @Aprobado, @RutaEvidencia, @Observacion, COALESCE(@Usuario, SYSTEM_USER));
    ELSE
        UPDATE tit.ExamenComplexivo
           SET CodigoExamen = COALESCE(@CodigoExamen, CodigoExamen),
               TipoExamen = COALESCE(@TipoExamen, TipoExamen),
               NotaExamen = @NotaExamen,
               NotaPonderada20 = @Ponderada,
               Aprobado = @Aprobado,
               RutaEvidencia = COALESCE(@RutaEvidencia, RutaEvidencia),
               Observacion = @Observacion,
               FechaActualizacion = SYSDATETIME()
         WHERE ExpedienteId = @ExpedienteId;

    UPDATE tit.ExpedienteTitulacion
       SET MecanismoTitulacionId = 'EXAMEN_COMPLEXIVO',
           NotaProcesoTitulacion20 = @Ponderada,
           RubricaTitulacionCumple = @Aprobado,
           AptoSustentacion = CASE WHEN @Aprobado = 1 THEN 1 ELSE AptoSustentacion END,
           NotaFinalGrado = CASE WHEN NotaPromedioAsignaturas80 IS NULL THEN NotaFinalGrado ELSE ROUND(NotaPromedioAsignaturas80 + @Ponderada, 2) END,
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_RegistrarTemaDefensaGrado
    @ExpedienteId BIGINT,
    @TemaTrabajo NVARCHAR(500),
    @LineaInvestigacion NVARCHAR(250) = NULL,
    @Tutor NVARCHAR(200) = NULL,
    @LectorOponente NVARCHAR(200) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@TemaTrabajo)), N'') IS NULL THROW 59620, 'Debe registrar el tema del trabajo de defensa.', 1;
    EXEC tit.sp_SeleccionarMecanismoTitulacion @ExpedienteId, 'DEFENSA_GRADO', @Usuario;

    IF NOT EXISTS (SELECT 1 FROM tit.DefensaGrado WHERE ExpedienteId = @ExpedienteId)
        INSERT INTO tit.DefensaGrado(ExpedienteId, TemaTrabajo, LineaInvestigacion, Tutor, LectorOponente, UsuarioRegistro)
        VALUES(@ExpedienteId, @TemaTrabajo, @LineaInvestigacion, @Tutor, @LectorOponente, COALESCE(@Usuario, SYSTEM_USER));
    ELSE
        UPDATE tit.DefensaGrado
           SET TemaTrabajo = @TemaTrabajo, LineaInvestigacion = @LineaInvestigacion, Tutor = @Tutor, LectorOponente = @LectorOponente, FechaActualizacion = SYSDATETIME()
         WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_ProgramarDefensaGrado
    @ExpedienteId BIGINT,
    @FechaProgramada DATE,
    @HoraProgramada TIME = NULL,
    @Lugar NVARCHAR(250) = NULL,
    @Modalidad VARCHAR(30) = NULL,
    @EnlaceVirtual NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @MecanismoId INT = (SELECT MecanismoTitulacionId FROM cat.MecanismoTitulacion WHERE Codigo = 'DEFENSA_GRADO');
    DECLARE @ProgramacionId BIGINT;

    EXEC tit.sp_SeleccionarMecanismoTitulacion @ExpedienteId, 'DEFENSA_GRADO', @Usuario;

    IF NOT EXISTS (SELECT 1 FROM tit.DefensaGrado WHERE ExpedienteId = @ExpedienteId)
        INSERT INTO tit.DefensaGrado(ExpedienteId, UsuarioRegistro) VALUES(@ExpedienteId, COALESCE(@Usuario, SYSTEM_USER));

    SELECT TOP 1 @ProgramacionId = ProgramacionTitulacionId
    FROM tit.ProgramacionTitulacion
    WHERE ExpedienteId = @ExpedienteId AND MecanismoTitulacionId = @MecanismoId AND Activo = 1
    ORDER BY ProgramacionTitulacionId DESC;

    IF @ProgramacionId IS NULL
    BEGIN
        INSERT INTO tit.ProgramacionTitulacion(ExpedienteId, MecanismoTitulacionId, FechaProgramada, HoraProgramada, Lugar, Modalidad, EnlaceVirtual, UsuarioRegistro)
        VALUES(@ExpedienteId, @MecanismoId, @FechaProgramada, @HoraProgramada, @Lugar, @Modalidad, @EnlaceVirtual, COALESCE(@Usuario, SYSTEM_USER));
        SET @ProgramacionId = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE tit.ProgramacionTitulacion
           SET FechaProgramada = @FechaProgramada, HoraProgramada = @HoraProgramada, Lugar = @Lugar, Modalidad = @Modalidad, EnlaceVirtual = @EnlaceVirtual, EstadoProgramacion = 'PROGRAMADA'
         WHERE ProgramacionTitulacionId = @ProgramacionId;
    END;

    UPDATE tit.DefensaGrado SET ProgramacionTitulacionId = @ProgramacionId, FechaActualizacion = SYSDATETIME() WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_CalificarDefensaGrado
    @ExpedienteId BIGINT,
    @NotaTrabajoEscrito DECIMAL(10,2),
    @NotaDefensaOral DECIMAL(10,2),
    @Observacion NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @NotaTrabajoEscrito < 0 OR @NotaTrabajoEscrito > 10 OR @NotaDefensaOral < 0 OR @NotaDefensaOral > 10
        THROW 59630, 'Las notas de defensa deben estar entre 0 y 10.', 1;

    DECLARE @MecanismoId INT = (SELECT MecanismoTitulacionId FROM cat.MecanismoTitulacion WHERE Codigo = 'DEFENSA_GRADO');
    DECLARE @NotaMinima DECIMAL(10,2) = ISNULL(TRY_CONVERT(DECIMAL(10,2), (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'NOTA_MINIMA_TITULACION')), 7);
    DECLARE @NotaFinal DECIMAL(10,2) = ROUND((@NotaTrabajoEscrito * 0.50) + (@NotaDefensaOral * 0.50), 2);
    DECLARE @Ponderada DECIMAL(10,2) = ROUND(@NotaFinal * 0.20, 2);
    DECLARE @Aprobado BIT = CASE WHEN @NotaFinal >= @NotaMinima THEN 1 ELSE 0 END;

    EXEC tit.sp_SeleccionarMecanismoTitulacion @ExpedienteId, 'DEFENSA_GRADO', @Usuario;

    IF NOT EXISTS (SELECT 1 FROM tit.DefensaGrado WHERE ExpedienteId = @ExpedienteId)
        INSERT INTO tit.DefensaGrado(ExpedienteId, NotaTrabajoEscrito, NotaDefensaOral, NotaFinalDefensa, NotaPonderada20, Aprobado, Observacion, UsuarioRegistro)
        VALUES(@ExpedienteId, @NotaTrabajoEscrito, @NotaDefensaOral, @NotaFinal, @Ponderada, @Aprobado, @Observacion, COALESCE(@Usuario, SYSTEM_USER));
    ELSE
        UPDATE tit.DefensaGrado
           SET NotaTrabajoEscrito = @NotaTrabajoEscrito,
               NotaDefensaOral = @NotaDefensaOral,
               NotaFinalDefensa = @NotaFinal,
               NotaPonderada20 = @Ponderada,
               Aprobado = @Aprobado,
               Observacion = @Observacion,
               FechaActualizacion = SYSDATETIME()
         WHERE ExpedienteId = @ExpedienteId;

    UPDATE tit.ExpedienteTitulacion
       SET MecanismoTitulacionId = 'DEFENSA_GRADO',
           NotaProcesoTitulacion20 = @Ponderada,
           RubricaTitulacionCumple = @Aprobado,
           AptoSustentacion = CASE WHEN @Aprobado = 1 THEN 1 ELSE AptoSustentacion END,
           NotaFinalGrado = CASE WHEN NotaPromedioAsignaturas80 IS NULL THEN NotaFinalGrado ELSE ROUND(NotaPromedioAsignaturas80 + @Ponderada, 2) END,
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_RegistrarTribunalTitulacion
    @ExpedienteId BIGINT,
    @MecanismoCodigo VARCHAR(40),
    @RolTribunal VARCHAR(50),
    @NombreMiembro NVARCHAR(200),
    @CedulaMiembro VARCHAR(20) = NULL,
    @CorreoMiembro NVARCHAR(200) = NULL,
    @OrdenFirma INT = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @MecanismoId INT = (SELECT MecanismoTitulacionId FROM cat.MecanismoTitulacion WHERE Codigo COLLATE Modern_Spanish_CI_AS = @MecanismoCodigo COLLATE Modern_Spanish_CI_AS AND Activo = 1);
    IF @MecanismoId IS NULL THROW 59640, 'Mecanismo de tribunal no válido.', 1;
    IF NULLIF(LTRIM(RTRIM(@NombreMiembro)), N'') IS NULL THROW 59641, 'Debe registrar el nombre del miembro del tribunal.', 1;

    INSERT INTO tit.TribunalTitulacion(ExpedienteId, MecanismoTitulacionId, RolTribunal, NombreMiembro, CedulaMiembro, CorreoMiembro, OrdenFirma, UsuarioRegistro)
    VALUES(@ExpedienteId, @MecanismoId, @RolTribunal, @NombreMiembro, @CedulaMiembro, @CorreoMiembro, @OrdenFirma, COALESCE(@Usuario, SYSTEM_USER));
END;
GO

CREATE OR ALTER VIEW rpt.vw_MecanismoTitulacionExpediente
AS
SELECT
    E.ExpedienteId,
    E.NumeroActaGrado,
    ER.NumeroIdentificacion,
    ER.ApellidosNombres,
    M.MecanismoTitulacionId,
    M.Codigo AS MecanismoCodigo,
    M.Nombre AS MecanismoNombre,
    M.NotaMinima,
    E.RubricaTitulacionCumple,
    E.AptoSustentacion,
    E.NotaProcesoTitulacion20,
    E.NotaFinalGrado
FROM tit.ExpedienteTitulacion E
INNER JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
LEFT JOIN cat.MecanismoTitulacion M
    ON M.Codigo COLLATE Modern_Spanish_CI_AS = E.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS;
GO

CREATE OR ALTER VIEW rpt.vw_PrevalidacionMecanismoTitulacion
AS
SELECT
    B.ExpedienteId,
    B.NumeroIdentificacion,
    B.MecanismoCodigo,
    B.MecanismoNombre,
    CAST(CASE
        WHEN B.MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND ISNULL(EX.Aprobado, 0) = 1 THEN 1
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND ISNULL(DG.Aprobado, 0) = 1 THEN 1
        ELSE 0
    END AS BIT) AS MecanismoAprobado,
    CASE
        WHEN B.MecanismoCodigo IS NULL THEN N'Debe seleccionar examen complexivo o defensa de grado.'
        WHEN B.MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND EX.ExamenComplexivoId IS NULL THEN N'Pendiente programar o calificar examen complexivo.'
        WHEN B.MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND ISNULL(EX.Aprobado, 0) = 0 THEN N'Examen complexivo pendiente de aprobación.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND DG.DefensaGradoId IS NULL THEN N'Pendiente registrar tema y calificar defensa.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND NULLIF(LTRIM(RTRIM(ISNULL(DG.TemaTrabajo, N''))), N'') IS NULL THEN N'Pendiente registrar tema de defensa.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND ISNULL(DG.Aprobado, 0) = 0 THEN N'Defensa de grado pendiente de aprobación.'
        ELSE N'Mecanismo de titulación aprobado.'
    END AS MensajeMecanismo
FROM rpt.vw_MecanismoTitulacionExpediente B
LEFT JOIN tit.ExamenComplexivo EX ON EX.ExpedienteId = B.ExpedienteId
LEFT JOIN tit.DefensaGrado DG ON DG.ExpedienteId = B.ExpedienteId;
GO

CREATE OR ALTER PROCEDURE tit.sp_PrevalidarMecanismoTitulacion
    @ExpedienteId BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT *
    FROM rpt.vw_PrevalidacionMecanismoTitulacion
    WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER VIEW rpt.vw_ExamenComplexivo
AS
SELECT
    EX.*,
    P.FechaProgramada,
    P.HoraProgramada,
    P.Lugar,
    P.Modalidad,
    P.EnlaceVirtual
FROM tit.ExamenComplexivo EX
LEFT JOIN tit.ProgramacionTitulacion P ON P.ProgramacionTitulacionId = EX.ProgramacionTitulacionId;
GO

CREATE OR ALTER VIEW rpt.vw_DefensaGrado
AS
SELECT
    DG.*,
    P.FechaProgramada,
    P.HoraProgramada,
    P.Lugar,
    P.Modalidad,
    P.EnlaceVirtual
FROM tit.DefensaGrado DG
LEFT JOIN tit.ProgramacionTitulacion P ON P.ProgramacionTitulacionId = DG.ProgramacionTitulacionId;
GO
