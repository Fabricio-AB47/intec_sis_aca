USE TITULACION_INTEC;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'tit') EXEC(N'CREATE SCHEMA tit AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud') EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'tit.RubricaTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.RubricaTitulacion
    (
        RubricaTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RubricaTitulacion PRIMARY KEY,
        MecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoRubrica VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreRubrica NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NOT NULL,
        VersionRubrica VARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_RubricaTitulacion_Version DEFAULT '1.0',
        Activo BIT NOT NULL CONSTRAINT DF_RubricaTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_RubricaTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_RubricaTitulacion_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT CK_RubricaTitulacion_Mecanismo CHECK (MecanismoCodigo IN ('EXAMEN_COMPLEXIVO', 'DEFENSA_GRADO')),
        CONSTRAINT UQ_RubricaTitulacion_Codigo UNIQUE(CodigoRubrica)
    );
END;
GO

IF OBJECT_ID(N'tit.RubricaCriterioTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.RubricaCriterioTitulacion
    (
        RubricaCriterioTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RubricaCriterioTitulacion PRIMARY KEY,
        RubricaTitulacionId BIGINT NOT NULL,
        CodigoCriterio VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreCriterio NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Descripcion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Peso DECIMAL(10,4) NOT NULL,
        PuntajeMaximo DECIMAL(10,2) NOT NULL CONSTRAINT DF_RubricaCriterio_Puntaje DEFAULT 10,
        Orden INT NOT NULL CONSTRAINT DF_RubricaCriterio_Orden DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_RubricaCriterio_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_RubricaCriterio_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_RubricaCriterio_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_RubricaCriterio_Rubrica FOREIGN KEY(RubricaTitulacionId) REFERENCES tit.RubricaTitulacion(RubricaTitulacionId),
        CONSTRAINT CK_RubricaCriterio_Peso CHECK (Peso > 0 AND Peso <= 1),
        CONSTRAINT CK_RubricaCriterio_Puntaje CHECK (PuntajeMaximo > 0)
    );

    CREATE UNIQUE INDEX UX_RubricaCriterio_Activo
        ON tit.RubricaCriterioTitulacion(RubricaTitulacionId, CodigoCriterio)
        WHERE Activo = 1;
END;
GO

IF OBJECT_ID(N'tit.CalificacionConsolidadaTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.CalificacionConsolidadaTitulacion
    (
        CalificacionConsolidadaTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CalificacionConsolidadaTitulacion PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NOT NULL,
        MecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        TotalEvaluadores INT NOT NULL,
        PromedioTrabajoEscrito DECIMAL(10,2) NULL,
        PromedioEvaluacionOral DECIMAL(10,2) NULL,
        NotaTitulacionSobre20 DECIMAL(10,2) NULL,
        NotaTitulacionSobre10 DECIMAL(10,2) NULL,
        NotaAsignaturasSobre10 DECIMAL(10,2) NULL,
        EquivalenciaAsignaturas DECIMAL(10,2) NULL,
        EquivalenciaTitulacion DECIMAL(10,2) NULL,
        NotaFinalGrado DECIMAL(10,2) NULL,
        Aprobado BIT NOT NULL CONSTRAINT DF_CalificacionConsolidada_Aprobado DEFAULT 0,
        FechaConsolidacion DATETIME2 NOT NULL CONSTRAINT DF_CalificacionConsolidada_Fecha DEFAULT SYSDATETIME(),
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_CalificacionConsolidada_Usuario DEFAULT N'SISTEMA',
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_CalificacionConsolidada_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_CalificacionConsolidada_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT UQ_CalificacionConsolidada_GrupoExpediente UNIQUE(GrupoTitulacionId, ExpedienteId)
    );
END;
GO

IF OBJECT_ID(N'aud.AuditoriaTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE aud.AuditoriaTitulacion
    (
        AuditoriaTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AuditoriaTitulacion PRIMARY KEY,
        Entidad VARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EntidadId BIGINT NULL,
        ExpedienteId BIGINT NULL,
        GrupoTitulacionId BIGINT NULL,
        Accion VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Detalle NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_AuditoriaTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_AuditoriaTitulacion_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM tit.RubricaTitulacion WHERE CodigoRubrica = 'RUB_EXAMEN_COMPLEXIVO_BASE')
BEGIN
    INSERT INTO tit.RubricaTitulacion(MecanismoCodigo, CodigoRubrica, NombreRubrica, VersionRubrica)
    VALUES('EXAMEN_COMPLEXIVO', 'RUB_EXAMEN_COMPLEXIVO_BASE', N'Rubrica base de examen complexivo', '1.0');
END;
GO

IF NOT EXISTS (SELECT 1 FROM tit.RubricaTitulacion WHERE CodigoRubrica = 'RUB_DEFENSA_GRADO_BASE')
BEGIN
    INSERT INTO tit.RubricaTitulacion(MecanismoCodigo, CodigoRubrica, NombreRubrica, VersionRubrica)
    VALUES('DEFENSA_GRADO', 'RUB_DEFENSA_GRADO_BASE', N'Rubrica base de defensa de grado', '1.0');
END;
GO

DECLARE @RubricaExamen BIGINT = (SELECT RubricaTitulacionId FROM tit.RubricaTitulacion WHERE CodigoRubrica = 'RUB_EXAMEN_COMPLEXIVO_BASE');
DECLARE @RubricaDefensa BIGINT = (SELECT RubricaTitulacionId FROM tit.RubricaTitulacion WHERE CodigoRubrica = 'RUB_DEFENSA_GRADO_BASE');

MERGE tit.RubricaCriterioTitulacion AS T
USING (VALUES
    (@RubricaExamen, 'DOMINIO_TECNICO', N'Dominio tecnico', N'Manejo conceptual y aplicacion tecnica del examen.', 0.4000, 10.00, 1),
    (@RubricaExamen, 'RESOLUCION_CASOS', N'Resolucion de casos', N'Capacidad para resolver escenarios academicos o profesionales.', 0.3500, 10.00, 2),
    (@RubricaExamen, 'ARGUMENTACION_ORAL', N'Argumentacion oral', N'Claridad y sustento de respuestas frente a evaluadores.', 0.2500, 10.00, 3),
    (@RubricaDefensa, 'TRABAJO_ESCRITO', N'Trabajo escrito', N'Estructura, rigor metodologico y resultados documentados.', 0.5000, 10.00, 1),
    (@RubricaDefensa, 'DEFENSA_ORAL', N'Defensa oral', N'Exposicion, argumentacion y respuesta a preguntas.', 0.3500, 10.00, 2),
    (@RubricaDefensa, 'PERTINENCIA_APORTE', N'Pertinencia del aporte', N'Alineacion del trabajo con la carrera y contexto profesional.', 0.1500, 10.00, 3)
) AS S(RubricaTitulacionId, CodigoCriterio, NombreCriterio, Descripcion, Peso, PuntajeMaximo, Orden)
ON T.RubricaTitulacionId = S.RubricaTitulacionId
AND T.CodigoCriterio COLLATE Modern_Spanish_CI_AS = S.CodigoCriterio COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN
    UPDATE SET NombreCriterio = S.NombreCriterio, Descripcion = S.Descripcion, Peso = S.Peso, PuntajeMaximo = S.PuntajeMaximo, Orden = S.Orden, Activo = 1, FechaActualizacion = SYSDATETIME()
WHEN NOT MATCHED THEN
    INSERT(RubricaTitulacionId, CodigoCriterio, NombreCriterio, Descripcion, Peso, PuntajeMaximo, Orden)
    VALUES(S.RubricaTitulacionId, S.CodigoCriterio, S.NombreCriterio, S.Descripcion, S.Peso, S.PuntajeMaximo, S.Orden);
GO

CREATE OR ALTER VIEW rpt.vw_DashboardTitulacion
AS
SELECT
    COUNT_BIG(1) AS TotalExpedientes,
    COALESCE(SUM(CASE WHEN E.EstadoExpediente IN ('APTO_TITULACION', 'EN_TITULACION', 'APROBADO_TITULACION') THEN 1 ELSE 0 END), 0) AS TotalEnProceso,
    COALESCE(SUM(CASE WHEN E.MecanismoTitulacionId = 'EXAMEN_COMPLEXIVO' THEN 1 ELSE 0 END), 0) AS TotalComplexivo,
    COALESCE(SUM(CASE WHEN E.MecanismoTitulacionId = 'DEFENSA_GRADO' THEN 1 ELSE 0 END), 0) AS TotalDefensa,
    COALESCE(SUM(CASE WHEN E.NumeroActaGrado IS NOT NULL THEN 1 ELSE 0 END), 0) AS TotalActas,
    COALESCE(SUM(CASE WHEN RS.RegistroSenescytId IS NOT NULL THEN 1 ELSE 0 END), 0) AS TotalTitulosRegistrados,
    COALESCE(SUM(CASE WHEN TI.TituloIntecId IS NOT NULL THEN 1 ELSE 0 END), 0) AS TotalTitulosIntec,
    COALESCE(SUM(CASE WHEN E.NotaFinalGrado >= 7 THEN 1 ELSE 0 END), 0) AS TotalAprobados,
    COALESCE(SUM(CASE WHEN E.NotaFinalGrado IS NOT NULL AND E.NotaFinalGrado < 7 THEN 1 ELSE 0 END), 0) AS TotalReprobados,
    COALESCE(SUM(CASE WHEN E.CedulaValidada = 1 AND E.TituloBachillerCumple = 1 AND E.InglesA2Cumple = 1 AND E.MallaCurricularCumple = 1 AND E.NoAdeudaFinanciero = 1 AND E.AptoSustentacion = 1 AND E.PracticasPreprofesionalesCumple = 1 AND E.VinculacionCumple = 1 AND E.PromedioAsignaturas IS NOT NULL THEN 1 ELSE 0 END), 0) AS TotalAptosEstricto
FROM tit.ExpedienteTitulacion E
OUTER APPLY (SELECT TOP 1 RegistroSenescytId FROM tit.RegistroSenescyt WHERE ExpedienteId = E.ExpedienteId ORDER BY RegistroSenescytId DESC) RS
OUTER APPLY (SELECT TOP 1 TituloIntecId FROM tit.TituloIntec WHERE ExpedienteId = E.ExpedienteId ORDER BY TituloIntecId DESC) TI;
GO

CREATE OR ALTER VIEW rpt.vw_ReporteExpedienteTitulacion
AS
SELECT
    E.ExpedienteId,
    ER.CodigoEstud,
    ER.NumeroIdentificacion,
    ER.ApellidosNombres,
    CR.NombreCarrera,
    E.CodAnioBasica,
    E.CodigoPeriodo,
    E.EstadoExpediente,
    E.MecanismoTitulacionId AS MecanismoCodigo,
    E.PromedioAsignaturas,
    E.NotaPromedioAsignaturas80,
    E.NotaProcesoTitulacion20,
    E.NotaFinalGrado,
    E.NumeroActaGrado,
    E.FechaActaGrado,
    G.GrupoTitulacionId,
    G.NombreGrupo,
    G.EstadoGrupo,
    ISNULL(Cal.TotalCalificaciones, 0) AS TotalCalificaciones,
    ISNULL(Cal.TotalEvaluadores, 0) AS TotalEvaluadores,
    CASE WHEN ISNULL(Cal.TotalEvaluadores, 0) >= 3 THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS CalificacionCompleta,
    P.FechaProgramada,
    P.HoraProgramada,
    P.Modalidad,
    P.Lugar,
    Doc.TotalDocumentos,
    CASE WHEN AG.ActaGradoId IS NULL THEN CAST(0 AS BIT) ELSE CAST(1 AS BIT) END AS TieneActa,
    CASE WHEN RS.RegistroSenescytId IS NULL THEN CAST(0 AS BIT) ELSE CAST(1 AS BIT) END AS TieneTituloRegistrado,
    CASE WHEN TI.TituloIntecId IS NULL THEN CAST(0 AS BIT) ELSE CAST(1 AS BIT) END AS TieneTituloIntec
FROM tit.ExpedienteTitulacion E
INNER JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
LEFT JOIN core.CarreraRef CR ON CR.CarreraRefId = E.CarreraRefId
OUTER APPLY
(
    SELECT TOP 1 GE.GrupoTitulacionId, GT.NombreGrupo, GT.EstadoGrupo
    FROM tit.GrupoTitulacionExpediente GE
    INNER JOIN tit.GrupoTitulacion GT ON GT.GrupoTitulacionId = GE.GrupoTitulacionId
    WHERE GE.ExpedienteId = E.ExpedienteId AND GE.Activo = 1 AND GT.Activo = 1
    ORDER BY GE.GrupoTitulacionExpedienteId DESC
) G
OUTER APPLY
(
    SELECT COUNT(DISTINCT C.CalificacionEvaluadorTitulacionId) AS TotalCalificaciones,
           COUNT(DISTINCT C.EvaluadorTitulacionId) AS TotalEvaluadores
    FROM tit.CalificacionEvaluadorTitulacion C
    WHERE C.ExpedienteId = E.ExpedienteId AND C.Activo = 1
) Cal
OUTER APPLY
(
    SELECT TOP 1 FechaProgramada, HoraProgramada, Modalidad, Lugar
    FROM tit.ProgramacionTitulacion
    WHERE ExpedienteId = E.ExpedienteId AND Activo = 1
    ORDER BY ProgramacionTitulacionId DESC
) P
OUTER APPLY (SELECT COUNT(1) AS TotalDocumentos FROM doc.DocumentoExpediente WHERE ExpedienteId = E.ExpedienteId AND Activo = 1) Doc
OUTER APPLY (SELECT TOP 1 ActaGradoId FROM tit.ActaGrado WHERE ExpedienteId = E.ExpedienteId ORDER BY ActaGradoId DESC) AG
OUTER APPLY (SELECT TOP 1 RegistroSenescytId FROM tit.RegistroSenescyt WHERE ExpedienteId = E.ExpedienteId ORDER BY RegistroSenescytId DESC) RS
OUTER APPLY (SELECT TOP 1 TituloIntecId FROM tit.TituloIntec WHERE ExpedienteId = E.ExpedienteId ORDER BY TituloIntecId DESC) TI;
GO

CREATE OR ALTER VIEW rpt.vw_AuditoriaTitulacion
AS
SELECT
    AuditoriaTitulacionId,
    Entidad,
    EntidadId,
    ExpedienteId,
    GrupoTitulacionId,
    Accion,
    Detalle,
    UsuarioRegistro,
    FechaRegistro
FROM aud.AuditoriaTitulacion;
GO
