USE TITULACION_INTEC;
GO

/* ============================================================================
   Portal de Titulacion INTEC - Complemento SQL idempotente
   Prompt 02

   Objetivo:
   - Complementar TITULACION_INTEC para portal web de titulacion.
   - Mantener compatibilidad con objetos existentes del proyecto.
   - Evitar dependencias rigidas contra bases externas si no existen.
   ============================================================================ */

SET NOCOUNT ON;
GO

/* ============================================================================
   1. Esquemas
   ============================================================================ */
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'core') EXEC(N'CREATE SCHEMA core AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'tit') EXEC(N'CREATE SCHEMA tit AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'resp') EXEC(N'CREATE SCHEMA resp AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'eval') EXEC(N'CREATE SCHEMA eval AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'doc') EXEC(N'CREATE SCHEMA doc AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'stg') EXEC(N'CREATE SCHEMA stg AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'etl') EXEC(N'CREATE SCHEMA etl AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'seg') EXEC(N'CREATE SCHEMA seg AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'util') EXEC(N'CREATE SCHEMA util AUTHORIZATION dbo');
GO

/* ============================================================================
   2. Tablas base locales para integracion si no existen
   ============================================================================ */
IF OBJECT_ID(N'core.EstudianteRef', N'U') IS NULL
BEGIN
    CREATE TABLE core.EstudianteRef
    (
        EstudianteRefId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EstudianteRef PRIMARY KEY,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoEstud INT NULL,
        ApellidosNombres NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_EstudianteRef_Activo DEFAULT 1,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_EstudianteRef_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF COL_LENGTH(N'core.EstudianteRef', N'NumeroIdentificacion') IS NULL ALTER TABLE core.EstudianteRef ADD NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'core.EstudianteRef', N'CodigoEstud') IS NULL ALTER TABLE core.EstudianteRef ADD CodigoEstud INT NULL;
IF COL_LENGTH(N'core.EstudianteRef', N'ApellidosNombres') IS NULL ALTER TABLE core.EstudianteRef ADD ApellidosNombres NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'core.EstudianteRef', N'Activo') IS NULL ALTER TABLE core.EstudianteRef ADD Activo BIT NOT NULL CONSTRAINT DF_EstudianteRef_Activo_Add DEFAULT 1;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_EstudianteRef_NumeroIdentificacion' AND object_id = OBJECT_ID(N'core.EstudianteRef'))
BEGIN
    CREATE UNIQUE INDEX UX_EstudianteRef_NumeroIdentificacion
        ON core.EstudianteRef(NumeroIdentificacion)
        WHERE NumeroIdentificacion IS NOT NULL;
END;
GO

IF OBJECT_ID(N'core.CarreraRef', N'U') IS NULL
BEGIN
    CREATE TABLE core.CarreraRef
    (
        CarreraRefId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CarreraRef PRIMARY KEY,
        CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        NombreCarrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_CarreraRef_Activo DEFAULT 1,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_CarreraRef_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF COL_LENGTH(N'core.CarreraRef', N'CodigoCarrera') IS NULL ALTER TABLE core.CarreraRef ADD CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'core.CarreraRef', N'NombreCarrera') IS NULL ALTER TABLE core.CarreraRef ADD NombreCarrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
GO

IF OBJECT_ID(N'tit.ExpedienteTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.ExpedienteTitulacion
    (
        ExpedienteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ExpedienteTitulacion PRIMARY KEY,
        EstudianteRefId BIGINT NULL,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoEstud INT NULL,
        CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        CodAnioBasica NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoPeriodo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        TituloOtorgado NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoTitulacionId VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoExpediente VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Estado DEFAULT 'PENDIENTE',
        CedulaValidada BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Cedula DEFAULT 0,
        TituloBachillerCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Bachiller DEFAULT 0,
        InglesA2Cumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Ingles DEFAULT 0,
        MallaCurricularCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Malla DEFAULT 0,
        NoAdeudaFinanciero BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Financiero DEFAULT 0,
        AptoSustentacion BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Apto DEFAULT 0,
        PracticasPreprofesionalesCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Practicas DEFAULT 0,
        VinculacionCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Vinculacion DEFAULT 0,
        RubricaTitulacionCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Rubrica DEFAULT 0,
        PromedioAsignaturas DECIMAL(5,2) NULL,
        NotaPromedioAsignaturas80 DECIMAL(5,2) NULL,
        NotaProcesoTitulacion20 DECIMAL(5,2) NULL,
        NotaFinalGrado DECIMAL(5,2) NULL,
        NumeroActaGrado NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NumeroRefrendacion NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        FechaActaGrado DATE NULL,
        FechaRefrendacion DATE NULL,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Fecha DEFAULT SYSDATETIME(),
        UsuarioActualizacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        FechaActualizacion DATETIME2 NULL
    );
END;
GO

IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NumeroIdentificacion') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'CodigoEstud') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD CodigoEstud INT NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'CodigoCarrera') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'Carrera') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'CodAnioBasica') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD CodAnioBasica NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'CodigoPeriodo') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD CodigoPeriodo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'TituloOtorgado') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD TituloOtorgado NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'MecanismoTitulacionId') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD MecanismoTitulacionId VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'EstadoExpediente') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD EstadoExpediente VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Estado_Add DEFAULT 'PENDIENTE';
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'CedulaValidada') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD CedulaValidada BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Cedula_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'TituloBachillerCumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD TituloBachillerCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Bachiller_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'InglesA2Cumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD InglesA2Cumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Ingles_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'MallaCurricularCumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD MallaCurricularCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Malla_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NoAdeudaFinanciero') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NoAdeudaFinanciero BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Financiero_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'AptoSustentacion') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD AptoSustentacion BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Apto_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'PracticasPreprofesionalesCumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD PracticasPreprofesionalesCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Practicas_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'VinculacionCumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD VinculacionCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Vinculacion_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'RubricaTitulacionCumple') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD RubricaTitulacionCumple BIT NOT NULL CONSTRAINT DF_ExpedienteTitulacion_Rubrica_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'PromedioAsignaturas') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD PromedioAsignaturas DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NotaPromedioAsignaturas80') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NotaPromedioAsignaturas80 DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NotaProcesoTitulacion20') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NotaProcesoTitulacion20 DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NotaFinalGrado') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NotaFinalGrado DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'NumeroActaGrado') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD NumeroActaGrado NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'FechaActaGrado') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD FechaActaGrado DATE NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'UsuarioRegistro') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'FechaRegistro') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD FechaRegistro DATETIME2 NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'UsuarioActualizacion') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD UsuarioActualizacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExpedienteTitulacion', N'FechaActualizacion') IS NULL ALTER TABLE tit.ExpedienteTitulacion ADD FechaActualizacion DATETIME2 NULL;
GO

/* ============================================================================
   3. Catalogos
   ============================================================================ */
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

IF COL_LENGTH(N'cat.MecanismoTitulacion', N'RequiereProgramacion') IS NULL ALTER TABLE cat.MecanismoTitulacion ADD RequiereProgramacion BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Programacion_Add DEFAULT 1;
IF COL_LENGTH(N'cat.MecanismoTitulacion', N'RequiereTribunal') IS NULL ALTER TABLE cat.MecanismoTitulacion ADD RequiereTribunal BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Tribunal_Add DEFAULT 1;
IF COL_LENGTH(N'cat.MecanismoTitulacion', N'NotaMinima') IS NULL ALTER TABLE cat.MecanismoTitulacion ADD NotaMinima DECIMAL(10,2) NOT NULL CONSTRAINT DF_MecanismoTitulacion_NotaMinima_Add DEFAULT 7;
IF COL_LENGTH(N'cat.MecanismoTitulacion', N'Activo') IS NULL ALTER TABLE cat.MecanismoTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_MecanismoTitulacion_Activo_Add DEFAULT 1;
GO

IF OBJECT_ID(N'cat.EstadoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.EstadoTitulacion
    (
        EstadoTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EstadoTitulacion PRIMARY KEY,
        Codigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_EstadoTitulacion_Codigo UNIQUE,
        Nombre NVARCHAR(120) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Orden INT NOT NULL CONSTRAINT DF_EstadoTitulacion_Orden DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_EstadoTitulacion_Activo DEFAULT 1
    );
END;
GO

IF OBJECT_ID(N'cat.RolResponsableTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.RolResponsableTitulacion
    (
        RolResponsableTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RolResponsableTitulacion PRIMARY KEY,
        Codigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_RolResponsableTitulacion_Codigo UNIQUE,
        Nombre NVARCHAR(150) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EsTribunal BIT NOT NULL CONSTRAINT DF_RolResponsable_EsTribunal DEFAULT 0,
        Activo BIT NOT NULL CONSTRAINT DF_RolResponsable_Activo DEFAULT 1
    );
END;
GO

IF COL_LENGTH(N'cat.RolResponsableTitulacion', N'Codigo') IS NULL
    ALTER TABLE cat.RolResponsableTitulacion ADD Codigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.RolResponsableTitulacion', N'RolResponsableCodigo') IS NULL
    ALTER TABLE cat.RolResponsableTitulacion ADD RolResponsableCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.RolResponsableTitulacion', N'EsTribunal') IS NULL
    ALTER TABLE cat.RolResponsableTitulacion ADD EsTribunal BIT NOT NULL CONSTRAINT DF_RolResponsable_EsTribunal_Compat DEFAULT 0;
GO

UPDATE cat.RolResponsableTitulacion
   SET Codigo = COALESCE(Codigo, RolResponsableCodigo),
       RolResponsableCodigo = COALESCE(RolResponsableCodigo, Codigo)
 WHERE Codigo IS NULL
    OR RolResponsableCodigo IS NULL;
GO

IF OBJECT_ID(N'cat.TipoDocumentoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoDocumentoTitulacion
    (
        TipoDocumentoTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoDocumentoTitulacion PRIMARY KEY,
        Codigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_TipoDocumentoTitulacion_Codigo UNIQUE,
        Nombre NVARCHAR(180) COLLATE Modern_Spanish_CI_AS NOT NULL,
        AplicaMecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL,
        EsObligatorio BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Obligatorio DEFAULT 0,
        Orden INT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Orden DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Activo DEFAULT 1
    );
END;
GO

IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'Codigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD Codigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'TipoDocumentoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'AplicaMecanismoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD AplicaMecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'MecanismoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD MecanismoCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'BloqueaActa') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD BloqueaActa BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_BloqueaActa_Compat DEFAULT 0;
GO

UPDATE cat.TipoDocumentoTitulacion
   SET Codigo = COALESCE(Codigo, TipoDocumentoCodigo),
       TipoDocumentoCodigo = COALESCE(TipoDocumentoCodigo, Codigo),
       AplicaMecanismoCodigo = COALESCE(AplicaMecanismoCodigo, MecanismoCodigo),
       MecanismoCodigo = COALESCE(MecanismoCodigo, AplicaMecanismoCodigo)
 WHERE Codigo IS NULL
    OR TipoDocumentoCodigo IS NULL
    OR (AplicaMecanismoCodigo IS NULL AND MecanismoCodigo IS NOT NULL)
    OR (MecanismoCodigo IS NULL AND AplicaMecanismoCodigo IS NOT NULL);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TipoDocumentoTitulacion_Codigo_Compat' AND object_id = OBJECT_ID(N'cat.TipoDocumentoTitulacion'))
    CREATE UNIQUE INDEX UX_TipoDocumentoTitulacion_Codigo_Compat ON cat.TipoDocumentoTitulacion(Codigo) WHERE Codigo IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TipoDocumentoTitulacion_TipoCodigo_Compat' AND object_id = OBJECT_ID(N'cat.TipoDocumentoTitulacion'))
    CREATE UNIQUE INDEX UX_TipoDocumentoTitulacion_TipoCodigo_Compat ON cat.TipoDocumentoTitulacion(TipoDocumentoCodigo) WHERE TipoDocumentoCodigo IS NOT NULL;
GO

IF OBJECT_ID(N'cat.TipoComponenteCalificacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoComponenteCalificacion
    (
        TipoComponenteCalificacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoComponenteCalificacion PRIMARY KEY,
        Codigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_TipoComponenteCalificacion_Codigo UNIQUE,
        Nombre NVARCHAR(150) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NotaMaxima DECIMAL(5,2) NOT NULL CONSTRAINT DF_TipoComponente_NotaMax DEFAULT 10,
        Activo BIT NOT NULL CONSTRAINT DF_TipoComponente_Activo DEFAULT 1
    );
END;
GO

IF OBJECT_ID(N'cat.ParametroTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.ParametroTitulacion
    (
        ParametroTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ParametroTitulacion PRIMARY KEY,
        Codigo VARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT UQ_ParametroTitulacion_Codigo UNIQUE,
        Valor NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Descripcion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_ParametroTitulacion_Activo DEFAULT 1,
        FechaActualizacion DATETIME2 NOT NULL CONSTRAINT DF_ParametroTitulacion_Fecha DEFAULT SYSDATETIME()
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

MERGE cat.EstadoTitulacion AS T
USING (VALUES
    ('PENDIENTE', N'Pendiente', 1),
    ('APTO', N'Apto', 2),
    ('HABILITADO', N'Habilitado', 3),
    ('PROGRAMADO', N'Programado', 4),
    ('EN_CALIFICACION', N'En calificacion', 5),
    ('CALIFICADO', N'Calificado', 6),
    ('ACTA_GENERADA', N'Acta generada', 7),
    ('TITULO_REGISTRADO', N'Titulo registrado', 8),
    ('TITULO_INTEC_CARGADO', N'Titulo INTEC cargado', 9),
    ('CERRADO', N'Cerrado', 10),
    ('ANULADO', N'Anulado', 99)
) AS S(Codigo, Nombre, Orden)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET Nombre = S.Nombre, Orden = S.Orden, Activo = 1
WHEN NOT MATCHED THEN INSERT(Codigo, Nombre, Orden) VALUES(S.Codigo, S.Nombre, S.Orden);
GO

MERGE cat.RolResponsableTitulacion AS T
USING (VALUES
    ('RESPONSABLE_COMPLEXIVO', N'Responsable de examen complexivo', 0),
    ('PRESIDENTE_TRIBUNAL', N'Presidente del tribunal', 1),
    ('VOCAL_1', N'Vocal 1', 1),
    ('VOCAL_2', N'Vocal 2', 1),
    ('TUTOR', N'Tutor', 0),
    ('LECTOR', N'Lector', 0),
    ('COORDINADOR_ACADEMICO', N'Coordinador academico', 0),
    ('SECRETARIA_TITULACION', N'Secretaria de titulacion', 0),
    ('AUTORIDAD_ACADEMICA', N'Autoridad academica', 0)
) AS S(Codigo, Nombre, EsTribunal)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET Codigo = S.Codigo, RolResponsableCodigo = S.Codigo, Nombre = S.Nombre, EsTribunal = S.EsTribunal, Activo = 1
WHEN NOT MATCHED THEN INSERT(Codigo, RolResponsableCodigo, Nombre, EsTribunal) VALUES(S.Codigo, S.Codigo, S.Nombre, S.EsTribunal);
GO

MERGE cat.TipoDocumentoTitulacion AS T
USING (VALUES
    ('APTITUD_LEGAL', N'Aptitud legal', NULL, 1, 1),
    ('RUBRICA_TRABAJO_ESCRITO', N'Rubrica trabajo escrito', 'DEFENSA_GRADO', 1, 2),
    ('RUBRICA_DEFENSA_ORAL', N'Rubrica defensa oral', 'DEFENSA_GRADO', 1, 3),
    ('EVIDENCIA_EXAMEN_COMPLEXIVO', N'Evidencia examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 4),
    ('TRABAJO_FINAL_GRADO', N'Trabajo final de grado', 'DEFENSA_GRADO', 1, 5),
    ('ACTA_DEFENSA', N'Acta de defensa', 'DEFENSA_GRADO', 0, 6),
    ('ACTA_GRADO', N'Acta de grado', NULL, 0, 7),
    ('TITULO_REGISTRO_SENESCYT', N'Titulo registrado SENESCYT', NULL, 0, 8),
    ('TITULO_INTEC', N'Titulo INTEC', NULL, 0, 9),
    ('CERTIFICADO_PRACTICAS', N'Certificado de Practicas laborales', NULL, 1, 10),
    ('CERTIFICADO_VINCULACION', N'Certificado de Servicio Comunitario', NULL, 1, 11)
) AS S(Codigo, Nombre, AplicaMecanismoCodigo, EsObligatorio, Orden)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET Codigo = S.Codigo, TipoDocumentoCodigo = S.Codigo, Nombre = S.Nombre, AplicaMecanismoCodigo = S.AplicaMecanismoCodigo, MecanismoCodigo = S.AplicaMecanismoCodigo, EsObligatorio = S.EsObligatorio, BloqueaActa = S.EsObligatorio, Orden = S.Orden, Activo = 1
WHEN NOT MATCHED THEN INSERT(Codigo, TipoDocumentoCodigo, Nombre, AplicaMecanismoCodigo, MecanismoCodigo, EsObligatorio, BloqueaActa, Orden) VALUES(S.Codigo, S.Codigo, S.Nombre, S.AplicaMecanismoCodigo, S.AplicaMecanismoCodigo, S.EsObligatorio, S.EsObligatorio, S.Orden);
GO

MERGE cat.TipoComponenteCalificacion AS T
USING (VALUES
    ('TRABAJO_ESCRITO', N'Trabajo escrito', 10.00),
    ('DEFENSA_ORAL', N'Defensa oral', 10.00),
    ('EXAMEN_COMPLEXIVO', N'Examen complexivo', 10.00)
) AS S(Codigo, Nombre, NotaMaxima)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET Nombre = S.Nombre, NotaMaxima = S.NotaMaxima, Activo = 1
WHEN NOT MATCHED THEN INSERT(Codigo, Nombre, NotaMaxima) VALUES(S.Codigo, S.Nombre, S.NotaMaxima);
GO

MERGE cat.ParametroTitulacion AS T
USING (VALUES
    ('TIT_PESO_ASIGNATURAS', N'0.80', N'Peso del promedio academico.'),
    ('TIT_PESO_TITULACION', N'0.20', N'Peso del proceso de titulacion.'),
    ('TIT_NOTA_MINIMA_APROBACION', N'7.00', N'Nota minima para aprobar.'),
    ('TIT_MAX_ESTUDIANTES_DEFENSA', N'2', N'Maximo de estudiantes en defensa.'),
    ('TIT_MAX_ESTUDIANTES_COMPLEXIVO', N'999', N'Maximo de estudiantes en grupo de examen complexivo.'),
    ('TIT_EVALUADORES_REQUERIDOS', N'3', N'Evaluadores requeridos para calificacion final.'),
    ('TIT_PERMITIR_CIERRE_SIN_TITULOS', N'0', N'Permite cierre sin titulos registrados.')
) AS S(Codigo, Valor, Descripcion)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET Valor = S.Valor, Descripcion = S.Descripcion, Activo = 1, FechaActualizacion = SYSDATETIME()
WHEN NOT MATCHED THEN INSERT(Codigo, Valor, Descripcion) VALUES(S.Codigo, S.Valor, S.Descripcion);
GO

/* ============================================================================
   4. Tablas principales
   ============================================================================ */
IF OBJECT_ID(N'tit.HabilitacionTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.HabilitacionTitulacion
    (
        HabilitacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_HabilitacionTitulacion PRIMARY KEY,
        EstudianteId BIGINT NULL,
        ExpedienteId BIGINT NULL,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoEstud INT NULL,
        CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoPeriodo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_HabilitacionTitulacion_Estado DEFAULT 'HABILITADO',
        CumpleAcademico BIT NOT NULL CONSTRAINT DF_Habilitacion_Academico DEFAULT 0,
        CumplePracticas BIT NOT NULL CONSTRAINT DF_Habilitacion_Practicas DEFAULT 0,
        CumpleVinculacion BIT NOT NULL CONSTRAINT DF_Habilitacion_Vinculacion DEFAULT 0,
        CumpleFinanciero BIT NOT NULL CONSTRAINT DF_Habilitacion_Financiero DEFAULT 0,
        CumpleDocumental BIT NOT NULL CONSTRAINT DF_Habilitacion_Documental DEFAULT 0,
        CumpleIngles BIT NOT NULL CONSTRAINT DF_Habilitacion_Ingles DEFAULT 0,
        CumpleAptitudLegal BIT NOT NULL CONSTRAINT DF_Habilitacion_Aptitud DEFAULT 0,
        FechaHabilitacion DATETIME2 NOT NULL CONSTRAINT DF_Habilitacion_Fecha DEFAULT SYSDATETIME(),
        UsuarioHabilitacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_Habilitacion_Usuario DEFAULT N'SISTEMA',
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL
    );
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
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Fecha DEFAULT SYSDATETIME(),
        Activo BIT NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Activo DEFAULT 1,
        CONSTRAINT FK_ProgramacionTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_ProgramacionTitulacion_Mecanismo FOREIGN KEY(MecanismoTitulacionId) REFERENCES cat.MecanismoTitulacion(MecanismoTitulacionId)
    );
END;
GO

IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'ExpedienteId') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD ExpedienteId BIGINT NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'MecanismoTitulacionId') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD MecanismoTitulacionId INT NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'FechaProgramada') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD FechaProgramada DATE NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'HoraProgramada') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD HoraProgramada TIME NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'Lugar') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'Modalidad') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD Modalidad VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'EnlaceVirtual') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD EnlaceVirtual NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'EstadoProgramacion') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD EstadoProgramacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Estado_Add DEFAULT 'PROGRAMADA';
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'UsuarioRegistro') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'FechaRegistro') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD FechaRegistro DATETIME2 NULL;
IF COL_LENGTH(N'tit.ProgramacionTitulacion', N'Activo') IS NULL ALTER TABLE tit.ProgramacionTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_ProgramacionTitulacion_Activo_Add DEFAULT 1;
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
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_TribunalTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_TribunalTitulacion_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_TribunalTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_TribunalTitulacion_Mecanismo FOREIGN KEY(MecanismoTitulacionId) REFERENCES cat.MecanismoTitulacion(MecanismoTitulacionId)
    );
END;
GO

IF COL_LENGTH(N'tit.TribunalTitulacion', N'ExpedienteId') IS NULL ALTER TABLE tit.TribunalTitulacion ADD ExpedienteId BIGINT NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'MecanismoTitulacionId') IS NULL ALTER TABLE tit.TribunalTitulacion ADD MecanismoTitulacionId INT NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'RolTribunal') IS NULL ALTER TABLE tit.TribunalTitulacion ADD RolTribunal VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'NombreMiembro') IS NULL ALTER TABLE tit.TribunalTitulacion ADD NombreMiembro NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'CedulaMiembro') IS NULL ALTER TABLE tit.TribunalTitulacion ADD CedulaMiembro VARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'CorreoMiembro') IS NULL ALTER TABLE tit.TribunalTitulacion ADD CorreoMiembro NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'OrdenFirma') IS NULL ALTER TABLE tit.TribunalTitulacion ADD OrdenFirma INT NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'Activo') IS NULL ALTER TABLE tit.TribunalTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_TribunalTitulacion_Activo_Add DEFAULT 1;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'UsuarioRegistro') IS NULL ALTER TABLE tit.TribunalTitulacion ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.TribunalTitulacion', N'FechaRegistro') IS NULL ALTER TABLE tit.TribunalTitulacion ADD FechaRegistro DATETIME2 NULL;
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
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ExamenComplexivo_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ExamenComplexivo_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_ExamenComplexivo_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_ExamenComplexivo_Programacion FOREIGN KEY(ProgramacionTitulacionId) REFERENCES tit.ProgramacionTitulacion(ProgramacionTitulacionId)
    );
END;
GO

IF COL_LENGTH(N'tit.ExamenComplexivo', N'ExpedienteId') IS NULL ALTER TABLE tit.ExamenComplexivo ADD ExpedienteId BIGINT NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'ProgramacionTitulacionId') IS NULL ALTER TABLE tit.ExamenComplexivo ADD ProgramacionTitulacionId BIGINT NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'CodigoExamen') IS NULL ALTER TABLE tit.ExamenComplexivo ADD CodigoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'TipoExamen') IS NULL ALTER TABLE tit.ExamenComplexivo ADD TipoExamen VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'NotaExamen') IS NULL ALTER TABLE tit.ExamenComplexivo ADD NotaExamen DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'NotaPonderada20') IS NULL ALTER TABLE tit.ExamenComplexivo ADD NotaPonderada20 DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'Aprobado') IS NULL ALTER TABLE tit.ExamenComplexivo ADD Aprobado BIT NOT NULL CONSTRAINT DF_ExamenComplexivo_Aprobado_Add DEFAULT 0;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'RutaEvidencia') IS NULL ALTER TABLE tit.ExamenComplexivo ADD RutaEvidencia NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'Observacion') IS NULL ALTER TABLE tit.ExamenComplexivo ADD Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'UsuarioRegistro') IS NULL ALTER TABLE tit.ExamenComplexivo ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'FechaRegistro') IS NULL ALTER TABLE tit.ExamenComplexivo ADD FechaRegistro DATETIME2 NULL;
IF COL_LENGTH(N'tit.ExamenComplexivo', N'FechaActualizacion') IS NULL ALTER TABLE tit.ExamenComplexivo ADD FechaActualizacion DATETIME2 NULL;
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
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_DefensaGrado_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_DefensaGrado_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL,
        CONSTRAINT FK_DefensaGrado_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_DefensaGrado_Programacion FOREIGN KEY(ProgramacionTitulacionId) REFERENCES tit.ProgramacionTitulacion(ProgramacionTitulacionId)
    );
END;
GO

IF COL_LENGTH(N'tit.DefensaGrado', N'ExpedienteId') IS NULL ALTER TABLE tit.DefensaGrado ADD ExpedienteId BIGINT NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'ProgramacionTitulacionId') IS NULL ALTER TABLE tit.DefensaGrado ADD ProgramacionTitulacionId BIGINT NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'TemaTrabajo') IS NULL ALTER TABLE tit.DefensaGrado ADD TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'LineaInvestigacion') IS NULL ALTER TABLE tit.DefensaGrado ADD LineaInvestigacion NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'Tutor') IS NULL ALTER TABLE tit.DefensaGrado ADD Tutor NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'LectorOponente') IS NULL ALTER TABLE tit.DefensaGrado ADD LectorOponente NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'NotaTrabajoEscrito') IS NULL ALTER TABLE tit.DefensaGrado ADD NotaTrabajoEscrito DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'NotaDefensaOral') IS NULL ALTER TABLE tit.DefensaGrado ADD NotaDefensaOral DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'NotaFinalDefensa') IS NULL ALTER TABLE tit.DefensaGrado ADD NotaFinalDefensa DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'NotaPonderada20') IS NULL ALTER TABLE tit.DefensaGrado ADD NotaPonderada20 DECIMAL(10,2) NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'Aprobado') IS NULL ALTER TABLE tit.DefensaGrado ADD Aprobado BIT NOT NULL CONSTRAINT DF_DefensaGrado_Aprobado_Add DEFAULT 0;
IF COL_LENGTH(N'tit.DefensaGrado', N'Observacion') IS NULL ALTER TABLE tit.DefensaGrado ADD Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'UsuarioRegistro') IS NULL ALTER TABLE tit.DefensaGrado ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'FechaRegistro') IS NULL ALTER TABLE tit.DefensaGrado ADD FechaRegistro DATETIME2 NULL;
IF COL_LENGTH(N'tit.DefensaGrado', N'FechaActualizacion') IS NULL ALTER TABLE tit.DefensaGrado ADD FechaActualizacion DATETIME2 NULL;
GO

IF OBJECT_ID(N'tit.GrupoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE tit.GrupoTitulacion
    (
        GrupoTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GrupoTitulacion PRIMARY KEY,
        CodigoGrupo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        NombreGrupo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Tema NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        FechaProgramada DATE NULL,
        HoraInicio TIME NULL,
        HoraFin TIME NULL,
        HoraProgramada TIME NULL,
        AulaOLink NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Modalidad NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacion_EstadoCodigo DEFAULT 'PENDIENTE',
        EstadoGrupo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        EsGrupal BIT NOT NULL CONSTRAINT DF_GrupoTitulacion_EsGrupal DEFAULT 1,
        MaximoIntegrantes INT NOT NULL CONSTRAINT DF_GrupoTitulacion_Max DEFAULT 999,
        Activo BIT NOT NULL CONSTRAINT DF_GrupoTitulacion_Activo DEFAULT 1,
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacion_Usuario DEFAULT N'SISTEMA',
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_GrupoTitulacion_Fecha DEFAULT SYSDATETIME(),
        FechaActualizacion DATETIME2 NULL
    );
END;
GO

IF COL_LENGTH(N'tit.GrupoTitulacion', N'CodigoGrupo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD CodigoGrupo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'NombreGrupo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD NombreGrupo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'MecanismoCodigo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Tema') IS NULL ALTER TABLE tit.GrupoTitulacion ADD Tema NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'TemaTrabajo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD TemaTrabajo NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Carrera') IS NULL ALTER TABLE tit.GrupoTitulacion ADD Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'CodigoCarrera') IS NULL ALTER TABLE tit.GrupoTitulacion ADD CodigoCarrera NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'FechaProgramada') IS NULL ALTER TABLE tit.GrupoTitulacion ADD FechaProgramada DATE NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'HoraInicio') IS NULL ALTER TABLE tit.GrupoTitulacion ADD HoraInicio TIME NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'HoraFin') IS NULL ALTER TABLE tit.GrupoTitulacion ADD HoraFin TIME NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'HoraProgramada') IS NULL ALTER TABLE tit.GrupoTitulacion ADD HoraProgramada TIME NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'AulaOLink') IS NULL ALTER TABLE tit.GrupoTitulacion ADD AulaOLink NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Lugar') IS NULL ALTER TABLE tit.GrupoTitulacion ADD Lugar NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Modalidad') IS NULL ALTER TABLE tit.GrupoTitulacion ADD Modalidad NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'EstadoCodigo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoTitulacion_EstadoCodigo_Add DEFAULT 'PENDIENTE';
IF COL_LENGTH(N'tit.GrupoTitulacion', N'EstadoGrupo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD EstadoGrupo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'EsGrupal') IS NULL ALTER TABLE tit.GrupoTitulacion ADD EsGrupal BIT NOT NULL CONSTRAINT DF_GrupoTitulacion_EsGrupal_Add DEFAULT 1;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'MaximoIntegrantes') IS NULL ALTER TABLE tit.GrupoTitulacion ADD MaximoIntegrantes INT NOT NULL CONSTRAINT DF_GrupoTitulacion_Max_Add DEFAULT 999;
IF COL_LENGTH(N'tit.GrupoTitulacion', N'Activo') IS NULL ALTER TABLE tit.GrupoTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_GrupoTitulacion_Activo_Add DEFAULT 1;
GO

IF OBJECT_ID(N'tit.GrupoTitulacionEstudiante', N'U') IS NULL
BEGIN
    CREATE TABLE tit.GrupoTitulacionEstudiante
    (
        GrupoTitulacionEstudianteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GrupoTitulacionEstudiante PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NOT NULL,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        CodigoEstud INT NULL,
        OrdenIntegrante INT NULL,
        EsPrincipal BIT NOT NULL CONSTRAINT DF_GrupoEstudiante_Principal DEFAULT 0,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_GrupoEstudiante_Estado DEFAULT 'HABILITADO',
        Activo BIT NOT NULL CONSTRAINT DF_GrupoEstudiante_Activo DEFAULT 1,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_GrupoEstudiante_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_GrupoEstudiante_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_GrupoEstudiante_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_GrupoTitulacionEstudiante_Activo' AND object_id = OBJECT_ID(N'tit.GrupoTitulacionEstudiante'))
BEGIN
    CREATE UNIQUE INDEX UX_GrupoTitulacionEstudiante_Activo
        ON tit.GrupoTitulacionEstudiante(GrupoTitulacionId, ExpedienteId)
        WHERE Activo = 1;
END;
GO

IF OBJECT_ID(N'resp.ResponsableTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE resp.ResponsableTitulacion
    (
        ResponsableTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ResponsableTitulacion PRIMARY KEY,
        Cedula NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        Nombres NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Correo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Cargo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        RolCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_ResponsableTitulacion_Activo DEFAULT 1,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_ResponsableTitulacion_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF COL_LENGTH(N'resp.ResponsableTitulacion', N'ResponsableTitulacionId') IS NULL
    EXEC(N'ALTER TABLE resp.ResponsableTitulacion ADD ResponsableTitulacionId AS ResponsableId PERSISTED;');
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'Cedula') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD Cedula NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'CedulaResponsable') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD CedulaResponsable NVARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'Nombres') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD Nombres NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'NombreResponsable') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD NombreResponsable NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'Correo') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD Correo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'CorreoResponsable') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD CorreoResponsable NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'Cargo') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD Cargo NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'RolCodigo') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD RolCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'UsuarioRegistro') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'UsuarioCreacion') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD UsuarioCreacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'FechaRegistro') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD FechaRegistro DATETIME2 NULL;
IF COL_LENGTH(N'resp.ResponsableTitulacion', N'FechaCreacion') IS NULL
    ALTER TABLE resp.ResponsableTitulacion ADD FechaCreacion DATETIME2 NULL;
GO

UPDATE resp.ResponsableTitulacion
   SET Cedula = COALESCE(Cedula, CONVERT(NVARCHAR(20), CedulaResponsable)),
       CedulaResponsable = COALESCE(CedulaResponsable, Cedula),
       Nombres = COALESCE(Nombres, CONVERT(NVARCHAR(250), NombreResponsable)),
       NombreResponsable = COALESCE(NombreResponsable, Nombres),
       Correo = COALESCE(Correo, CONVERT(NVARCHAR(250), CorreoResponsable)),
       CorreoResponsable = COALESCE(CorreoResponsable, Correo),
       UsuarioRegistro = COALESCE(UsuarioRegistro, CONVERT(NVARCHAR(128), UsuarioCreacion), N'SISTEMA'),
       UsuarioCreacion = COALESCE(UsuarioCreacion, UsuarioRegistro, N'SISTEMA'),
       FechaRegistro = COALESCE(FechaRegistro, FechaCreacion, SYSDATETIME()),
       FechaCreacion = COALESCE(FechaCreacion, FechaRegistro, SYSDATETIME())
 WHERE Cedula IS NULL
    OR CedulaResponsable IS NULL
    OR Nombres IS NULL
    OR NombreResponsable IS NULL
    OR Correo IS NULL
    OR CorreoResponsable IS NULL
    OR UsuarioRegistro IS NULL
    OR UsuarioCreacion IS NULL
    OR FechaRegistro IS NULL
    OR FechaCreacion IS NULL;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    INNER JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    INNER JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE i.object_id = OBJECT_ID(N'resp.ResponsableTitulacion')
      AND i.is_unique = 1
      AND c.name = N'ResponsableTitulacionId'
)
    CREATE UNIQUE INDEX UX_ResponsableTitulacion_IdCompat ON resp.ResponsableTitulacion(ResponsableTitulacionId);
GO

IF OBJECT_ID(N'resp.AsignacionResponsableTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE resp.AsignacionResponsableTitulacion
    (
        AsignacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AsignacionResponsableTitulacion PRIMARY KEY,
        GrupoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NULL,
        ResponsableTitulacionId BIGINT NOT NULL,
        RolCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Orden INT NULL,
        EsTribunal BIT NOT NULL CONSTRAINT DF_AsignacionResponsable_EsTribunal DEFAULT 0,
        Activo BIT NOT NULL CONSTRAINT DF_AsignacionResponsable_Activo DEFAULT 1,
        FechaAsignacion DATETIME2 NOT NULL CONSTRAINT DF_AsignacionResponsable_Fecha DEFAULT SYSDATETIME(),
        UsuarioAsignacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_AsignacionResponsable_Usuario DEFAULT N'SISTEMA',
        CONSTRAINT FK_AsignacionResponsable_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_AsignacionResponsable_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_AsignacionResponsable_Responsable FOREIGN KEY(ResponsableTitulacionId) REFERENCES resp.ResponsableTitulacion(ResponsableTitulacionId)
    );
END;
GO

IF OBJECT_ID(N'eval.RubricaTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE eval.RubricaTitulacion
    (
        RubricaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EvalRubricaTitulacion PRIMARY KEY,
        CodigoRubrica VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Nombre NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreRubrica NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Version NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_EvalRubrica_Version DEFAULT N'1.0',
        Activo BIT NOT NULL CONSTRAINT DF_EvalRubrica_Activo DEFAULT 1
    );
END;
GO

IF COL_LENGTH(N'eval.RubricaTitulacion', N'CodigoRubrica') IS NULL ALTER TABLE eval.RubricaTitulacion ADD CodigoRubrica VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.RubricaTitulacion', N'MecanismoCodigo') IS NULL ALTER TABLE eval.RubricaTitulacion ADD MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.RubricaTitulacion', N'Nombre') IS NULL ALTER TABLE eval.RubricaTitulacion ADD Nombre NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.RubricaTitulacion', N'NombreRubrica') IS NULL ALTER TABLE eval.RubricaTitulacion ADD NombreRubrica NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.RubricaTitulacion', N'Version') IS NULL ALTER TABLE eval.RubricaTitulacion ADD Version NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.RubricaTitulacion', N'Activo') IS NULL ALTER TABLE eval.RubricaTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_EvalRubrica_Activo_Add DEFAULT 1;
GO

IF OBJECT_ID(N'eval.CriterioRubrica', N'U') IS NULL
BEGIN
    CREATE TABLE eval.CriterioRubrica
    (
        CriterioRubricaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CriterioRubrica PRIMARY KEY,
        RubricaId BIGINT NOT NULL,
        CodigoCriterio VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        ComponenteCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Nombre NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreCriterio NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        Descripcion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
        NotaMaxima DECIMAL(5,2) NOT NULL CONSTRAINT DF_CriterioRubrica_Nota DEFAULT 10,
        Ponderacion DECIMAL(5,2) NOT NULL,
        Orden INT NOT NULL CONSTRAINT DF_CriterioRubrica_Orden DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_CriterioRubrica_Activo DEFAULT 1,
        CONSTRAINT FK_CriterioRubrica_Rubrica FOREIGN KEY(RubricaId) REFERENCES eval.RubricaTitulacion(RubricaId)
    );
END;
GO

IF COL_LENGTH(N'eval.CriterioRubrica', N'CodigoCriterio') IS NULL ALTER TABLE eval.CriterioRubrica ADD CodigoCriterio VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'ComponenteCodigo') IS NULL ALTER TABLE eval.CriterioRubrica ADD ComponenteCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'Nombre') IS NULL ALTER TABLE eval.CriterioRubrica ADD Nombre NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'NombreCriterio') IS NULL ALTER TABLE eval.CriterioRubrica ADD NombreCriterio NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'Descripcion') IS NULL ALTER TABLE eval.CriterioRubrica ADD Descripcion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'NotaMaxima') IS NULL ALTER TABLE eval.CriterioRubrica ADD NotaMaxima DECIMAL(5,2) NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'Ponderacion') IS NULL ALTER TABLE eval.CriterioRubrica ADD Ponderacion DECIMAL(5,2) NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'Orden') IS NULL ALTER TABLE eval.CriterioRubrica ADD Orden INT NULL;
IF COL_LENGTH(N'eval.CriterioRubrica', N'Activo') IS NULL ALTER TABLE eval.CriterioRubrica ADD Activo BIT NOT NULL CONSTRAINT DF_CriterioRubrica_Activo_Add DEFAULT 1;
GO

IF OBJECT_ID(N'eval.CalificacionEvaluador', N'U') IS NULL
BEGIN
    CREATE TABLE eval.CalificacionEvaluador
    (
        CalificacionEvaluadorId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CalificacionEvaluador PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL,
        GrupoTitulacionId BIGINT NOT NULL,
        ResponsableTitulacionId BIGINT NOT NULL,
        EvaluadorNumero INT NOT NULL,
        NotaTrabajoEscrito DECIMAL(5,2) NULL,
        NotaDefensaOral DECIMAL(5,2) NULL,
        NotaExamenComplexivo DECIMAL(5,2) NULL,
        NotaTitulacionSobre20 DECIMAL(5,2) NULL,
        Observacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Cerrado BIT NOT NULL CONSTRAINT DF_CalificacionEvaluador_Cerrado DEFAULT 0,
        FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_CalificacionEvaluador_Fecha DEFAULT SYSDATETIME(),
        UsuarioRegistro NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_CalificacionEvaluador_Usuario DEFAULT N'SISTEMA',
        CONSTRAINT FK_CalificacionEvaluador_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_CalificacionEvaluador_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId),
        CONSTRAINT FK_CalificacionEvaluador_Responsable FOREIGN KEY(ResponsableTitulacionId) REFERENCES resp.ResponsableTitulacion(ResponsableTitulacionId),
        CONSTRAINT CK_CalificacionEvaluador_Numero CHECK (EvaluadorNumero BETWEEN 1 AND 3),
        CONSTRAINT CK_CalificacionEvaluador_Notas CHECK (
            (NotaTrabajoEscrito IS NULL OR NotaTrabajoEscrito BETWEEN 0 AND 10) AND
            (NotaDefensaOral IS NULL OR NotaDefensaOral BETWEEN 0 AND 10) AND
            (NotaExamenComplexivo IS NULL OR NotaExamenComplexivo BETWEEN 0 AND 10)
        )
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_CalificacionEvaluador_EstudianteEvaluador' AND object_id = OBJECT_ID(N'eval.CalificacionEvaluador'))
BEGIN
    CREATE UNIQUE INDEX UX_CalificacionEvaluador_EstudianteEvaluador
        ON eval.CalificacionEvaluador(ExpedienteId, GrupoTitulacionId, EvaluadorNumero);
END;
GO

IF OBJECT_ID(N'eval.CalificacionConsolidada', N'U') IS NULL
BEGIN
    CREATE TABLE eval.CalificacionConsolidada
    (
        CalificacionConsolidadaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EvalCalificacionConsolidada PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL CONSTRAINT UQ_EvalCalificacionConsolidada_Expediente UNIQUE,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        NotaAsignaturas DECIMAL(5,2) NULL,
        EquivalenciaAsignaturas80 DECIMAL(5,2) NULL,
        PromedioTrabajoEscrito DECIMAL(5,2) NULL,
        PromedioDefensaOral DECIMAL(5,2) NULL,
        PromedioExamenComplexivo DECIMAL(5,2) NULL,
        NotaTitulacionSobre20 DECIMAL(5,2) NULL,
        EquivalenciaTitulacion20 DECIMAL(5,2) NULL,
        NotaFinalGrado DECIMAL(5,2) NULL,
        EvaluadoresCompletos BIT NOT NULL CONSTRAINT DF_EvalConsolidada_Completos DEFAULT 0,
        Aprobado BIT NOT NULL CONSTRAINT DF_EvalConsolidada_Aprobado DEFAULT 0,
        FechaConsolidacion DATETIME2 NOT NULL CONSTRAINT DF_EvalConsolidada_Fecha DEFAULT SYSDATETIME(),
        CONSTRAINT FK_EvalConsolidada_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId)
    );
END;
GO

IF OBJECT_ID(N'doc.DocumentoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE doc.DocumentoTitulacion
    (
        DocumentoTitulacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentoTitulacion PRIMARY KEY,
        ExpedienteId BIGINT NULL,
        GrupoTitulacionId BIGINT NULL,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreArchivo NVARCHAR(260) COLLATE Modern_Spanish_CI_AS NOT NULL,
        RutaNube NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        UrlPublica NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        HashArchivo VARBINARY(64) NULL,
        ContentType NVARCHAR(150) COLLATE Modern_Spanish_CI_AS NULL,
        Version INT NOT NULL CONSTRAINT DF_DocumentoTitulacion_Version DEFAULT 1,
        EsFirmadoElectronico BIT NOT NULL CONSTRAINT DF_DocumentoTitulacion_Firma DEFAULT 0,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_DocumentoTitulacion_Estado DEFAULT 'CARGADO',
        FechaCarga DATETIME2 NOT NULL CONSTRAINT DF_DocumentoTitulacion_Fecha DEFAULT SYSDATETIME(),
        UsuarioCarga NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_DocumentoTitulacion_Usuario DEFAULT N'SISTEMA',
        CONSTRAINT FK_DocumentoTitulacion_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId),
        CONSTRAINT FK_DocumentoTitulacion_Grupo FOREIGN KEY(GrupoTitulacionId) REFERENCES tit.GrupoTitulacion(GrupoTitulacionId)
    );
END;
GO

IF OBJECT_ID(N'tit.ActaGrado', N'U') IS NULL
BEGIN
    CREATE TABLE tit.ActaGrado
    (
        ActaGradoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ActaGrado PRIMARY KEY,
        ExpedienteId BIGINT NOT NULL,
        NumeroActa NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NumeroActaGrado NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL,
        NombresEstudiante NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Escuela NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        Modalidad NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        TituloOtorgado NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        FechaActa DATE NOT NULL,
        HoraActa TIME NULL,
        Ciudad NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        NotaAsignaturas DECIMAL(5,2) NULL,
        EquivalenciaAsignaturas80 DECIMAL(5,2) NULL,
        NotaProcesoTitulacion DECIMAL(5,2) NULL,
        EquivalenciaTitulacion20 DECIMAL(5,2) NULL,
        NotaFinalGrado DECIMAL(5,2) NULL,
        AutoridadAcademica NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        CoordinadorAcademico NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        DocenteEvaluador NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL,
        RutaActaPdf NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ActaGrado_Estado DEFAULT 'ACTA_GENERADA',
        FechaGeneracion DATETIME2 NOT NULL CONSTRAINT DF_ActaGrado_FechaGeneracion DEFAULT SYSDATETIME(),
        FechaCreacion DATETIME2 NULL,
        UsuarioGeneracion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ActaGrado_Usuario DEFAULT N'SISTEMA',
        UsuarioCreacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL,
        CONSTRAINT FK_ActaGrado_Expediente FOREIGN KEY(ExpedienteId) REFERENCES tit.ExpedienteTitulacion(ExpedienteId)
    );
END;
GO

IF COL_LENGTH(N'tit.ActaGrado', N'NumeroActa') IS NULL ALTER TABLE tit.ActaGrado ADD NumeroActa NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NumeroActaGrado') IS NULL ALTER TABLE tit.ActaGrado ADD NumeroActaGrado NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NumeroIdentificacion') IS NULL ALTER TABLE tit.ActaGrado ADD NumeroIdentificacion NVARCHAR(20) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NombresEstudiante') IS NULL ALTER TABLE tit.ActaGrado ADD NombresEstudiante NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'Carrera') IS NULL ALTER TABLE tit.ActaGrado ADD Carrera NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'Escuela') IS NULL ALTER TABLE tit.ActaGrado ADD Escuela NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'Modalidad') IS NULL ALTER TABLE tit.ActaGrado ADD Modalidad NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'MecanismoCodigo') IS NULL ALTER TABLE tit.ActaGrado ADD MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'TituloOtorgado') IS NULL ALTER TABLE tit.ActaGrado ADD TituloOtorgado NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NotaAsignaturas') IS NULL ALTER TABLE tit.ActaGrado ADD NotaAsignaturas DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'EquivalenciaAsignaturas80') IS NULL ALTER TABLE tit.ActaGrado ADD EquivalenciaAsignaturas80 DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NotaProcesoTitulacion') IS NULL ALTER TABLE tit.ActaGrado ADD NotaProcesoTitulacion DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'EquivalenciaTitulacion20') IS NULL ALTER TABLE tit.ActaGrado ADD EquivalenciaTitulacion20 DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'NotaFinalGrado') IS NULL ALTER TABLE tit.ActaGrado ADD NotaFinalGrado DECIMAL(5,2) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'RutaActaPdf') IS NULL ALTER TABLE tit.ActaGrado ADD RutaActaPdf NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'EstadoCodigo') IS NULL ALTER TABLE tit.ActaGrado ADD EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ActaGrado_Estado_Add DEFAULT 'ACTA_GENERADA';
IF COL_LENGTH(N'tit.ActaGrado', N'FechaGeneracion') IS NULL ALTER TABLE tit.ActaGrado ADD FechaGeneracion DATETIME2 NOT NULL CONSTRAINT DF_ActaGrado_FechaGeneracion_Add DEFAULT SYSDATETIME();
IF COL_LENGTH(N'tit.ActaGrado', N'UsuarioGeneracion') IS NULL ALTER TABLE tit.ActaGrado ADD UsuarioGeneracion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL CONSTRAINT DF_ActaGrado_Usuario_Add DEFAULT N'SISTEMA';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ActaGrado_Expediente' AND object_id = OBJECT_ID(N'tit.ActaGrado'))
BEGIN
    CREATE UNIQUE INDEX UX_ActaGrado_Expediente ON tit.ActaGrado(ExpedienteId);
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ActaGrado_NumeroActa' AND object_id = OBJECT_ID(N'tit.ActaGrado'))
BEGIN
    CREATE UNIQUE INDEX UX_ActaGrado_NumeroActa ON tit.ActaGrado(NumeroActa) WHERE NumeroActa IS NOT NULL;
END;
GO

/* ============================================================================
   5. Rubricas base
   ============================================================================ */
IF NOT EXISTS (SELECT 1 FROM eval.RubricaTitulacion WHERE MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND Activo = 1)
    INSERT INTO eval.RubricaTitulacion(CodigoRubrica, MecanismoCodigo, Nombre, NombreRubrica, Version)
    VALUES('RUB_EXAMEN_COMPLEXIVO_BASE', 'EXAMEN_COMPLEXIVO', N'Rubrica base examen complexivo', N'Rubrica base examen complexivo', N'1.0');
IF NOT EXISTS (SELECT 1 FROM eval.RubricaTitulacion WHERE MecanismoCodigo = 'DEFENSA_GRADO' AND Activo = 1)
    INSERT INTO eval.RubricaTitulacion(CodigoRubrica, MecanismoCodigo, Nombre, NombreRubrica, Version)
    VALUES('RUB_DEFENSA_GRADO_BASE', 'DEFENSA_GRADO', N'Rubrica base defensa de grado', N'Rubrica base defensa de grado', N'1.0');
GO

DECLARE @RubricaComplexivo BIGINT = (SELECT TOP 1 RubricaId FROM eval.RubricaTitulacion WHERE MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND Activo = 1 ORDER BY RubricaId);
DECLARE @RubricaDefensa BIGINT = (SELECT TOP 1 RubricaId FROM eval.RubricaTitulacion WHERE MecanismoCodigo = 'DEFENSA_GRADO' AND Activo = 1 ORDER BY RubricaId);

MERGE eval.CriterioRubrica AS T
USING (VALUES
    (@RubricaComplexivo, 'DOMINIO_TECNICO', 'EXAMEN_COMPLEXIVO', N'Dominio tecnico', N'Manejo conceptual y resolucion tecnica.', 10.00, 0.50, 1),
    (@RubricaComplexivo, 'RESOLUCION_CASOS', 'EXAMEN_COMPLEXIVO', N'Resolucion de casos', N'Aplicacion practica del conocimiento.', 10.00, 0.30, 2),
    (@RubricaComplexivo, 'ARGUMENTACION_ORAL', 'EXAMEN_COMPLEXIVO', N'Argumentacion oral', N'Claridad y sustento de respuestas.', 10.00, 0.20, 3),
    (@RubricaDefensa, 'TRABAJO_ESCRITO', 'TRABAJO_ESCRITO', N'Trabajo escrito', N'Calidad metodologica y documental.', 10.00, 0.50, 1),
    (@RubricaDefensa, 'DEFENSA_ORAL', 'DEFENSA_ORAL', N'Defensa oral', N'Exposicion, argumentacion y respuestas.', 10.00, 0.35, 2),
    (@RubricaDefensa, 'PERTINENCIA_APORTE', 'DEFENSA_ORAL', N'Pertinencia del aporte', N'Aporte academico/profesional.', 10.00, 0.15, 3)
) AS S(RubricaId, CodigoCriterio, ComponenteCodigo, Nombre, Descripcion, NotaMaxima, Ponderacion, Orden)
ON T.RubricaId = S.RubricaId
AND T.CodigoCriterio COLLATE Modern_Spanish_CI_AS = S.CodigoCriterio COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET ComponenteCodigo = S.ComponenteCodigo, Nombre = S.Nombre, NombreCriterio = S.Nombre, Descripcion = S.Descripcion, NotaMaxima = S.NotaMaxima, Ponderacion = S.Ponderacion, Orden = S.Orden, Activo = 1
WHEN NOT MATCHED THEN INSERT(RubricaId, CodigoCriterio, ComponenteCodigo, Nombre, NombreCriterio, Descripcion, NotaMaxima, Ponderacion, Orden)
VALUES(S.RubricaId, S.CodigoCriterio, S.ComponenteCodigo, S.Nombre, S.Nombre, S.Descripcion, S.NotaMaxima, S.Ponderacion, S.Orden);
GO

/* ============================================================================
   6. Vistas requeridas
   ============================================================================ */
CREATE OR ALTER VIEW rpt.vw_EstudiantesCumplenRequisitosTitulacion
AS
SELECT
    E.ExpedienteId,
    COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) AS NumeroIdentificacion,
    COALESCE(E.CodigoEstud, ER.CodigoEstud) AS CodigoEstud,
    ER.ApellidosNombres,
    E.CodigoCarrera,
    E.Carrera,
    E.CodigoPeriodo,
    E.PromedioAsignaturas,
    E.EstadoExpediente,
    E.MecanismoTitulacionId AS MecanismoCodigo
FROM tit.ExpedienteTitulacion E
LEFT JOIN core.EstudianteRef ER
    ON ER.EstudianteRefId = E.EstudianteRefId
WHERE ISNULL(E.CedulaValidada, 0) = 1
  AND ISNULL(E.TituloBachillerCumple, 0) = 1
  AND ISNULL(E.InglesA2Cumple, 0) = 1
  AND ISNULL(E.MallaCurricularCumple, 0) = 1
  AND ISNULL(E.NoAdeudaFinanciero, 0) = 1
  AND ISNULL(E.AptoSustentacion, 0) = 1
  AND ISNULL(E.PracticasPreprofesionalesCumple, 0) = 1
  AND ISNULL(E.VinculacionCumple, 0) = 1
  AND E.PromedioAsignaturas IS NOT NULL;
GO

CREATE OR ALTER VIEW rpt.vw_EstudiantesPendientesRequisitosTitulacion
AS
SELECT
    E.ExpedienteId,
    COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) AS NumeroIdentificacion,
    COALESCE(E.CodigoEstud, ER.CodigoEstud) AS CodigoEstud,
    ER.ApellidosNombres,
    E.CodigoCarrera,
    E.Carrera,
    E.CodigoPeriodo,
    E.EstadoExpediente,
    CONCAT(
        CASE WHEN ISNULL(E.CedulaValidada, 0) = 0 THEN N'Cedula; ' ELSE N'' END,
        CASE WHEN ISNULL(E.TituloBachillerCumple, 0) = 0 THEN N'Bachiller; ' ELSE N'' END,
        CASE WHEN ISNULL(E.InglesA2Cumple, 0) = 0 THEN N'Ingles; ' ELSE N'' END,
        CASE WHEN ISNULL(E.MallaCurricularCumple, 0) = 0 THEN N'Malla; ' ELSE N'' END,
        CASE WHEN ISNULL(E.NoAdeudaFinanciero, 0) = 0 THEN N'Financiero; ' ELSE N'' END,
        CASE WHEN ISNULL(E.AptoSustentacion, 0) = 0 THEN N'Aptitud; ' ELSE N'' END,
        CASE WHEN ISNULL(E.PracticasPreprofesionalesCumple, 0) = 0 THEN N'Practicas laborales; ' ELSE N'' END,
        CASE WHEN ISNULL(E.VinculacionCumple, 0) = 0 THEN N'Servicio Comunitario; ' ELSE N'' END,
        CASE WHEN E.PromedioAsignaturas IS NULL THEN N'Promedio; ' ELSE N'' END
    ) AS RequisitosPendientes
FROM tit.ExpedienteTitulacion E
LEFT JOIN core.EstudianteRef ER
    ON ER.EstudianteRefId = E.EstudianteRefId
WHERE NOT EXISTS (
    SELECT 1
    FROM rpt.vw_EstudiantesCumplenRequisitosTitulacion A
    WHERE A.ExpedienteId = E.ExpedienteId
);
GO

CREATE OR ALTER VIEW rpt.vw_HabilitacionesTitulacion
AS
SELECT *
FROM tit.HabilitacionTitulacion;
GO

CREATE OR ALTER VIEW rpt.vw_MecanismoTitulacionExpediente
AS
SELECT
    E.ExpedienteId,
    E.NumeroActaGrado,
    COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion) AS NumeroIdentificacion,
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
LEFT JOIN core.EstudianteRef ER
    ON ER.EstudianteRefId = E.EstudianteRefId
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
        WHEN B.MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND ISNULL(EX.Aprobado, 0) = 0 THEN N'Examen complexivo pendiente de aprobacion.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND DG.DefensaGradoId IS NULL THEN N'Pendiente registrar tema y calificar defensa.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND NULLIF(LTRIM(RTRIM(ISNULL(DG.TemaTrabajo, N''))), N'') IS NULL THEN N'Pendiente registrar tema de defensa.'
        WHEN B.MecanismoCodigo = 'DEFENSA_GRADO' AND ISNULL(DG.Aprobado, 0) = 0 THEN N'Defensa de grado pendiente de aprobacion.'
        ELSE N'Mecanismo de titulacion aprobado.'
    END AS MensajeMecanismo
FROM rpt.vw_MecanismoTitulacionExpediente B
LEFT JOIN tit.ExamenComplexivo EX
    ON EX.ExpedienteId = B.ExpedienteId
LEFT JOIN tit.DefensaGrado DG
    ON DG.ExpedienteId = B.ExpedienteId;
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
LEFT JOIN tit.ProgramacionTitulacion P
    ON P.ProgramacionTitulacionId = EX.ProgramacionTitulacionId;
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
LEFT JOIN tit.ProgramacionTitulacion P
    ON P.ProgramacionTitulacionId = DG.ProgramacionTitulacionId;
GO

CREATE OR ALTER VIEW rpt.vw_GruposComplexivo
AS
SELECT
    G.GrupoTitulacionId,
    G.CodigoGrupo,
    G.NombreGrupo,
    G.MecanismoCodigo,
    G.Tema,
    G.TemaTrabajo,
    G.Carrera,
    G.CodigoCarrera,
    G.FechaProgramada,
    G.HoraInicio,
    G.HoraFin,
    G.HoraProgramada,
    G.AulaOLink,
    G.Lugar,
    G.Modalidad,
    G.EstadoCodigo,
    G.EstadoGrupo,
    G.EsGrupal,
    G.MaximoIntegrantes,
    G.Activo,
    G.UsuarioRegistro,
    G.FechaRegistro,
    G.FechaActualizacion,
    COUNT(GE.GrupoTitulacionEstudianteId) AS TotalIntegrantes
FROM tit.GrupoTitulacion G
LEFT JOIN tit.GrupoTitulacionEstudiante GE
    ON GE.GrupoTitulacionId = G.GrupoTitulacionId
   AND GE.Activo = 1
WHERE G.MecanismoCodigo = 'EXAMEN_COMPLEXIVO'
  AND G.Activo = 1
GROUP BY
    G.GrupoTitulacionId, G.CodigoGrupo, G.NombreGrupo, G.MecanismoCodigo, G.Tema, G.TemaTrabajo,
    G.Carrera, G.CodigoCarrera, G.FechaProgramada, G.HoraInicio, G.HoraFin, G.HoraProgramada,
    G.AulaOLink, G.Lugar, G.Modalidad, G.EstadoCodigo, G.EstadoGrupo, G.EsGrupal,
    G.MaximoIntegrantes, G.Activo, G.UsuarioRegistro, G.FechaRegistro, G.FechaActualizacion;
GO

CREATE OR ALTER VIEW rpt.vw_DefensasGrado
AS
SELECT
    G.GrupoTitulacionId,
    G.CodigoGrupo,
    G.NombreGrupo,
    G.MecanismoCodigo,
    G.Tema,
    G.TemaTrabajo,
    G.Carrera,
    G.CodigoCarrera,
    G.FechaProgramada,
    G.HoraInicio,
    G.HoraFin,
    G.HoraProgramada,
    G.AulaOLink,
    G.Lugar,
    G.Modalidad,
    G.EstadoCodigo,
    G.EstadoGrupo,
    G.EsGrupal,
    G.MaximoIntegrantes,
    G.Activo,
    G.UsuarioRegistro,
    G.FechaRegistro,
    G.FechaActualizacion,
    COUNT(GE.GrupoTitulacionEstudianteId) AS TotalIntegrantes
FROM tit.GrupoTitulacion G
LEFT JOIN tit.GrupoTitulacionEstudiante GE
    ON GE.GrupoTitulacionId = G.GrupoTitulacionId
   AND GE.Activo = 1
WHERE G.MecanismoCodigo = 'DEFENSA_GRADO'
  AND G.Activo = 1
GROUP BY
    G.GrupoTitulacionId, G.CodigoGrupo, G.NombreGrupo, G.MecanismoCodigo, G.Tema, G.TemaTrabajo,
    G.Carrera, G.CodigoCarrera, G.FechaProgramada, G.HoraInicio, G.HoraFin, G.HoraProgramada,
    G.AulaOLink, G.Lugar, G.Modalidad, G.EstadoCodigo, G.EstadoGrupo, G.EsGrupal,
    G.MaximoIntegrantes, G.Activo, G.UsuarioRegistro, G.FechaRegistro, G.FechaActualizacion;
GO

CREATE OR ALTER VIEW rpt.vw_ResponsablesTribunal
AS
SELECT
    A.AsignacionId,
    A.GrupoTitulacionId,
    A.ExpedienteId,
    G.MecanismoCodigo,
    A.RolCodigo,
    A.Orden,
    A.EsTribunal,
    R.ResponsableTitulacionId,
    R.Cedula,
    R.Nombres,
    R.Correo,
    R.Cargo,
    A.FechaAsignacion,
    A.UsuarioAsignacion
FROM resp.AsignacionResponsableTitulacion A
INNER JOIN resp.ResponsableTitulacion R
    ON R.ResponsableTitulacionId = A.ResponsableTitulacionId
INNER JOIN tit.GrupoTitulacion G
    ON G.GrupoTitulacionId = A.GrupoTitulacionId
WHERE A.Activo = 1
  AND R.Activo = 1;
GO

CREATE OR ALTER VIEW rpt.vw_CalificacionesPendientes
AS
SELECT
    GE.ExpedienteId,
    GE.NumeroIdentificacion,
    GE.GrupoTitulacionId,
    G.MecanismoCodigo,
    G.CodigoGrupo,
    COUNT(DISTINCT C.EvaluadorNumero) AS EvaluadoresRegistrados,
    3 - COUNT(DISTINCT C.EvaluadorNumero) AS EvaluadoresPendientes
FROM tit.GrupoTitulacionEstudiante GE
INNER JOIN tit.GrupoTitulacion G
    ON G.GrupoTitulacionId = GE.GrupoTitulacionId
LEFT JOIN eval.CalificacionEvaluador C
    ON C.ExpedienteId = GE.ExpedienteId
   AND C.GrupoTitulacionId = GE.GrupoTitulacionId
   AND C.Cerrado = 1
WHERE GE.Activo = 1
GROUP BY GE.ExpedienteId, GE.NumeroIdentificacion, GE.GrupoTitulacionId, G.MecanismoCodigo, G.CodigoGrupo
HAVING COUNT(DISTINCT C.EvaluadorNumero) < 3;
GO

CREATE OR ALTER VIEW rpt.vw_CalificacionesConsolidadas
AS
SELECT *
FROM eval.CalificacionConsolidada;
GO

CREATE OR ALTER VIEW rpt.vw_ActasGeneradas
AS
SELECT *
FROM tit.ActaGrado;
GO

CREATE OR ALTER VIEW rpt.vw_TitulosCargados
AS
SELECT
    D.*
FROM doc.DocumentoTitulacion D
WHERE D.TipoDocumentoCodigo IN ('TITULO_REGISTRO_SENESCYT', 'TITULO_INTEC');
GO

/* ============================================================================
   7. Procedimientos requeridos
   ============================================================================ */
CREATE OR ALTER PROCEDURE tit.sp_ListarEstudiantesAptos
    @SoloAptos BIT = 1,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @AcademicaDisponible BIT =
        CASE WHEN DB_ID(N'INTECBDD') IS NOT NULL AND OBJECT_ID(N'INTECBDD.dbo.DATOS_ESTUD', N'U') IS NOT NULL THEN 1 ELSE 0 END;
    DECLARE @PracticasDisponible BIT =
        CASE WHEN DB_ID(N'INTEC_PRACTICAS_PREPROFESIONALES') IS NOT NULL THEN 1 ELSE 0 END;

    IF @SoloAptos = 1
    BEGIN
        SELECT
            A.*,
            @AcademicaDisponible AS FuenteAcademicaDisponible,
            @PracticasDisponible AS FuentePracticasDisponible
        FROM rpt.vw_EstudiantesCumplenRequisitosTitulacion A
        ORDER BY A.ApellidosNombres, A.NumeroIdentificacion;
        RETURN;
    END;

    SELECT
        P.*,
        @AcademicaDisponible AS FuenteAcademicaDisponible,
        @PracticasDisponible AS FuentePracticasDisponible
    FROM rpt.vw_EstudiantesPendientesRequisitosTitulacion P
    ORDER BY P.ApellidosNombres, P.NumeroIdentificacion;
END;
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

CREATE OR ALTER PROCEDURE tit.sp_CrearGrupoComplexivo
    @CodigoGrupo NVARCHAR(50) = NULL,
    @Tema NVARCHAR(1000) = NULL,
    @Carrera NVARCHAR(250) = NULL,
    @CodigoCarrera NVARCHAR(50) = NULL,
    @FechaProgramada DATE = NULL,
    @HoraInicio TIME = NULL,
    @HoraFin TIME = NULL,
    @AulaOLink NVARCHAR(500) = NULL,
    @Modalidad NVARCHAR(50) = NULL,
    @Usuario NVARCHAR(128) = NULL,
    @GrupoTitulacionId BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Maximo INT = ISNULL(TRY_CONVERT(INT, (SELECT Valor FROM cat.ParametroTitulacion WHERE Codigo = 'TIT_MAX_ESTUDIANTES_COMPLEXIVO' AND Activo = 1)), 999);

    INSERT INTO tit.GrupoTitulacion
    (
        CodigoGrupo, NombreGrupo, MecanismoCodigo, Tema, TemaTrabajo, Carrera, CodigoCarrera,
        FechaProgramada, HoraInicio, HoraFin, HoraProgramada, AulaOLink, Lugar, Modalidad,
        EstadoCodigo, EstadoGrupo, EsGrupal, MaximoIntegrantes, UsuarioRegistro
    )
    VALUES
    (
        @CodigoGrupo, COALESCE(@Tema, @CodigoGrupo, N'Examen complexivo'), 'EXAMEN_COMPLEXIVO', @Tema, @Tema, @Carrera, @CodigoCarrera,
        @FechaProgramada, @HoraInicio, @HoraFin, @HoraInicio, @AulaOLink, @AulaOLink, @Modalidad,
        CASE WHEN @FechaProgramada IS NULL THEN 'HABILITADO' ELSE 'PROGRAMADO' END,
        CASE WHEN @FechaProgramada IS NULL THEN 'CONFIGURADO' ELSE 'PROGRAMADO' END,
        1, @Maximo, COALESCE(@Usuario, SYSTEM_USER)
    );

    SET @GrupoTitulacionId = SCOPE_IDENTITY();
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_CrearDefensaGrado
    @ExpedienteId1 BIGINT,
    @ExpedienteId2 BIGINT = NULL,
    @CodigoGrupo NVARCHAR(50) = NULL,
    @Tema NVARCHAR(1000) = NULL,
    @Carrera NVARCHAR(250) = NULL,
    @CodigoCarrera NVARCHAR(50) = NULL,
    @FechaProgramada DATE = NULL,
    @HoraInicio TIME = NULL,
    @HoraFin TIME = NULL,
    @AulaOLink NVARCHAR(500) = NULL,
    @Modalidad NVARCHAR(50) = NULL,
    @Usuario NVARCHAR(128) = NULL,
    @GrupoTitulacionId BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @ExpedienteId2 IS NOT NULL AND @ExpedienteId2 = @ExpedienteId1
        THROW 59701, 'La defensa no puede repetir el mismo expediente.', 1;

    BEGIN TRAN;

    INSERT INTO tit.GrupoTitulacion
    (
        CodigoGrupo, NombreGrupo, MecanismoCodigo, Tema, TemaTrabajo, Carrera, CodigoCarrera,
        FechaProgramada, HoraInicio, HoraFin, HoraProgramada, AulaOLink, Lugar, Modalidad,
        EstadoCodigo, EstadoGrupo, EsGrupal, MaximoIntegrantes, UsuarioRegistro
    )
    VALUES
    (
        @CodigoGrupo, COALESCE(@Tema, @CodigoGrupo, N'Defensa de grado'), 'DEFENSA_GRADO', @Tema, @Tema, @Carrera, @CodigoCarrera,
        @FechaProgramada, @HoraInicio, @HoraFin, @HoraInicio, @AulaOLink, @AulaOLink, @Modalidad,
        CASE WHEN @FechaProgramada IS NULL THEN 'HABILITADO' ELSE 'PROGRAMADO' END,
        CASE WHEN @FechaProgramada IS NULL THEN 'CONFIGURADO' ELSE 'PROGRAMADO' END,
        CASE WHEN @ExpedienteId2 IS NULL THEN 0 ELSE 1 END, 2, COALESCE(@Usuario, SYSTEM_USER)
    );

    SET @GrupoTitulacionId = SCOPE_IDENTITY();

    INSERT INTO tit.GrupoTitulacionEstudiante(GrupoTitulacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, OrdenIntegrante, EsPrincipal, EstadoCodigo)
    SELECT @GrupoTitulacionId, E.ExpedienteId, COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion), COALESCE(E.CodigoEstud, ER.CodigoEstud), 1, 1, 'HABILITADO'
    FROM tit.ExpedienteTitulacion E
    LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
    WHERE E.ExpedienteId = @ExpedienteId1;

    IF @ExpedienteId2 IS NOT NULL
    BEGIN
        INSERT INTO tit.GrupoTitulacionEstudiante(GrupoTitulacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, OrdenIntegrante, EsPrincipal, EstadoCodigo)
        SELECT @GrupoTitulacionId, E.ExpedienteId, COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion), COALESCE(E.CodigoEstud, ER.CodigoEstud), 2, 0, 'HABILITADO'
        FROM tit.ExpedienteTitulacion E
        LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
        WHERE E.ExpedienteId = @ExpedienteId2;
    END;

    IF (SELECT COUNT(1) FROM tit.GrupoTitulacionEstudiante WHERE GrupoTitulacionId = @GrupoTitulacionId AND Activo = 1) > 2
        THROW 59702, 'La defensa de grado permite maximo 2 estudiantes.', 1;

    COMMIT;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_HabilitarEstudianteTitulacion
    @NumeroIdentificacion NVARCHAR(20),
    @MecanismoCodigo VARCHAR(30),
    @Tema NVARCHAR(1000) = NULL,
    @FechaProgramada DATE = NULL,
    @HoraInicio TIME = NULL,
    @HoraFin TIME = NULL,
    @Modalidad NVARCHAR(50) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @MecanismoCodigo NOT IN ('EXAMEN_COMPLEXIVO', 'DEFENSA_GRADO')
        THROW 59710, 'Mecanismo de titulacion no valido.', 1;

    DECLARE @Login NVARCHAR(128) = COALESCE(@Usuario, SYSTEM_USER);
    DECLARE @EstudianteRefId BIGINT;
    DECLARE @ExpedienteId BIGINT;
    DECLARE @GrupoTitulacionId BIGINT;

    BEGIN TRAN;

    SELECT @EstudianteRefId = EstudianteRefId
    FROM core.EstudianteRef
    WHERE NumeroIdentificacion COLLATE Modern_Spanish_CI_AS = @NumeroIdentificacion COLLATE Modern_Spanish_CI_AS;

    IF @EstudianteRefId IS NULL
    BEGIN
        INSERT INTO core.EstudianteRef(NumeroIdentificacion, ApellidosNombres)
        VALUES(@NumeroIdentificacion, @NumeroIdentificacion);
        SET @EstudianteRefId = SCOPE_IDENTITY();
    END;

    SELECT TOP (1) @ExpedienteId = ExpedienteId
    FROM tit.ExpedienteTitulacion
    WHERE NumeroIdentificacion COLLATE Modern_Spanish_CI_AS = @NumeroIdentificacion COLLATE Modern_Spanish_CI_AS
       OR EstudianteRefId = @EstudianteRefId
    ORDER BY ExpedienteId DESC;

    IF @ExpedienteId IS NULL
    BEGIN
        INSERT INTO tit.ExpedienteTitulacion(EstudianteRefId, NumeroIdentificacion, MecanismoTitulacionId, EstadoExpediente, UsuarioRegistro)
        VALUES(@EstudianteRefId, @NumeroIdentificacion, @MecanismoCodigo, 'HABILITADO', @Login);
        SET @ExpedienteId = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE tit.ExpedienteTitulacion
           SET MecanismoTitulacionId = @MecanismoCodigo,
               EstadoExpediente = 'HABILITADO',
               FechaActualizacion = SYSDATETIME(),
               UsuarioActualizacion = @Login
         WHERE ExpedienteId = @ExpedienteId;
    END;

    INSERT INTO tit.HabilitacionTitulacion
    (
        EstudianteId, ExpedienteId, NumeroIdentificacion, CodigoEstud, CodigoCarrera, Carrera,
        CodigoPeriodo, MecanismoCodigo, EstadoCodigo, CumpleAcademico, CumplePracticas,
        CumpleVinculacion, CumpleFinanciero, CumpleDocumental, CumpleIngles, CumpleAptitudLegal,
        UsuarioHabilitacion, Observacion
    )
    SELECT
        @EstudianteRefId, E.ExpedienteId, @NumeroIdentificacion, COALESCE(E.CodigoEstud, ER.CodigoEstud),
        E.CodigoCarrera, E.Carrera, E.CodigoPeriodo, @MecanismoCodigo, 'HABILITADO',
        CASE WHEN ISNULL(E.MallaCurricularCumple, 0) = 1 AND E.PromedioAsignaturas IS NOT NULL THEN 1 ELSE 0 END,
        ISNULL(E.PracticasPreprofesionalesCumple, 0), ISNULL(E.VinculacionCumple, 0),
        ISNULL(E.NoAdeudaFinanciero, 0), ISNULL(E.TituloBachillerCumple, 0),
        ISNULL(E.InglesA2Cumple, 0), ISNULL(E.AptoSustentacion, 0),
        @Login, @Tema
    FROM tit.ExpedienteTitulacion E
    LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
    WHERE E.ExpedienteId = @ExpedienteId;

    IF @MecanismoCodigo = 'EXAMEN_COMPLEXIVO'
    BEGIN
        EXEC tit.sp_CrearGrupoComplexivo
            @CodigoGrupo = NULL,
            @Tema = @Tema,
            @FechaProgramada = @FechaProgramada,
            @HoraInicio = @HoraInicio,
            @HoraFin = @HoraFin,
            @AulaOLink = NULL,
            @Modalidad = @Modalidad,
            @Usuario = @Login,
            @GrupoTitulacionId = @GrupoTitulacionId OUTPUT;
    END
    ELSE
    BEGIN
        EXEC tit.sp_CrearDefensaGrado
            @ExpedienteId1 = @ExpedienteId,
            @ExpedienteId2 = NULL,
            @Tema = @Tema,
            @FechaProgramada = @FechaProgramada,
            @HoraInicio = @HoraInicio,
            @HoraFin = @HoraFin,
            @Modalidad = @Modalidad,
            @Usuario = @Login,
            @GrupoTitulacionId = @GrupoTitulacionId OUTPUT;
    END;

    IF @MecanismoCodigo = 'EXAMEN_COMPLEXIVO'
    BEGIN
        INSERT INTO tit.GrupoTitulacionEstudiante(GrupoTitulacionId, ExpedienteId, NumeroIdentificacion, CodigoEstud, OrdenIntegrante, EsPrincipal, EstadoCodigo)
        SELECT @GrupoTitulacionId, E.ExpedienteId, @NumeroIdentificacion, COALESCE(E.CodigoEstud, ER.CodigoEstud), 1, 1, 'HABILITADO'
        FROM tit.ExpedienteTitulacion E
        LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
        WHERE E.ExpedienteId = @ExpedienteId
          AND NOT EXISTS (
              SELECT 1
              FROM tit.GrupoTitulacionEstudiante GE
              WHERE GE.GrupoTitulacionId = @GrupoTitulacionId
                AND GE.ExpedienteId = E.ExpedienteId
                AND GE.Activo = 1
          );
    END;

    COMMIT;

    SELECT @ExpedienteId AS ExpedienteId, @GrupoTitulacionId AS GrupoTitulacionId, @MecanismoCodigo AS MecanismoCodigo;
END;
GO

CREATE OR ALTER PROCEDURE resp.sp_AsignarResponsableComplexivo
    @GrupoTitulacionId BIGINT,
    @Cedula NVARCHAR(20),
    @Nombres NVARCHAR(250),
    @Correo NVARCHAR(250) = NULL,
    @Cargo NVARCHAR(250) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.GrupoTitulacion WHERE GrupoTitulacionId = @GrupoTitulacionId AND MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND Activo = 1)
        THROW 59720, 'El grupo no corresponde a examen complexivo.', 1;

    DECLARE @ResponsableId BIGINT;
    SELECT @ResponsableId = ResponsableTitulacionId
    FROM resp.ResponsableTitulacion
    WHERE Cedula COLLATE Modern_Spanish_CI_AS = @Cedula COLLATE Modern_Spanish_CI_AS
      AND RolCodigo = 'RESPONSABLE_COMPLEXIVO'
      AND Activo = 1;

    IF @ResponsableId IS NULL
    BEGIN
        INSERT INTO resp.ResponsableTitulacion(Cedula, CedulaResponsable, Nombres, NombreResponsable, Correo, CorreoResponsable, Cargo, RolCodigo, UsuarioRegistro, UsuarioCreacion)
        VALUES(@Cedula, @Cedula, @Nombres, @Nombres, @Correo, @Correo, @Cargo, 'RESPONSABLE_COMPLEXIVO', COALESCE(@Usuario, SYSTEM_USER), COALESCE(@Usuario, SYSTEM_USER));
        SET @ResponsableId = SCOPE_IDENTITY();
    END;

    INSERT INTO resp.AsignacionResponsableTitulacion(GrupoTitulacionId, ResponsableTitulacionId, RolCodigo, Orden, EsTribunal, UsuarioAsignacion)
    VALUES(@GrupoTitulacionId, @ResponsableId, 'RESPONSABLE_COMPLEXIVO', 1, 0, COALESCE(@Usuario, SYSTEM_USER));
END;
GO

CREATE OR ALTER PROCEDURE resp.sp_AsignarTribunalDefensa
    @GrupoTitulacionId BIGINT,
    @CedulaPresidente NVARCHAR(20),
    @NombrePresidente NVARCHAR(250),
    @CorreoPresidente NVARCHAR(250) = NULL,
    @CedulaVocal1 NVARCHAR(20),
    @NombreVocal1 NVARCHAR(250),
    @CorreoVocal1 NVARCHAR(250) = NULL,
    @CedulaVocal2 NVARCHAR(20),
    @NombreVocal2 NVARCHAR(250),
    @CorreoVocal2 NVARCHAR(250) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.GrupoTitulacion WHERE GrupoTitulacionId = @GrupoTitulacionId AND MecanismoCodigo = 'DEFENSA_GRADO' AND Activo = 1)
        THROW 59730, 'El grupo no corresponde a defensa de grado.', 1;

    DECLARE @Miembros TABLE(Orden INT, RolCodigo VARCHAR(50), Cedula NVARCHAR(20), Nombres NVARCHAR(250), Correo NVARCHAR(250));
    INSERT INTO @Miembros VALUES
        (1, 'PRESIDENTE_TRIBUNAL', @CedulaPresidente, @NombrePresidente, @CorreoPresidente),
        (2, 'VOCAL_1', @CedulaVocal1, @NombreVocal1, @CorreoVocal1),
        (3, 'VOCAL_2', @CedulaVocal2, @NombreVocal2, @CorreoVocal2);

    IF EXISTS (SELECT 1 FROM @Miembros WHERE NULLIF(LTRIM(RTRIM(Nombres)), N'') IS NULL)
        THROW 59731, 'Debe registrar los 3 miembros del tribunal.', 1;

    DECLARE @Orden INT, @RolCodigo VARCHAR(50), @Cedula NVARCHAR(20), @Nombres NVARCHAR(250), @Correo NVARCHAR(250), @ResponsableId BIGINT;
    DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT Orden, RolCodigo, Cedula, Nombres, Correo FROM @Miembros;
    OPEN c;
    FETCH NEXT FROM c INTO @Orden, @RolCodigo, @Cedula, @Nombres, @Correo;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SELECT @ResponsableId = ResponsableTitulacionId
        FROM resp.ResponsableTitulacion
        WHERE ISNULL(Cedula, N'') COLLATE Modern_Spanish_CI_AS = ISNULL(@Cedula, N'') COLLATE Modern_Spanish_CI_AS
          AND RolCodigo = @RolCodigo
          AND Activo = 1;

        IF @ResponsableId IS NULL
        BEGIN
            INSERT INTO resp.ResponsableTitulacion(Cedula, CedulaResponsable, Nombres, NombreResponsable, Correo, CorreoResponsable, RolCodigo, UsuarioRegistro, UsuarioCreacion)
            VALUES(@Cedula, @Cedula, @Nombres, @Nombres, @Correo, @Correo, @RolCodigo, COALESCE(@Usuario, SYSTEM_USER), COALESCE(@Usuario, SYSTEM_USER));
            SET @ResponsableId = SCOPE_IDENTITY();
        END;

        INSERT INTO resp.AsignacionResponsableTitulacion(GrupoTitulacionId, ResponsableTitulacionId, RolCodigo, Orden, EsTribunal, UsuarioAsignacion)
        VALUES(@GrupoTitulacionId, @ResponsableId, @RolCodigo, @Orden, 1, COALESCE(@Usuario, SYSTEM_USER));

        FETCH NEXT FROM c INTO @Orden, @RolCodigo, @Cedula, @Nombres, @Correo;
    END;
    CLOSE c;
    DEALLOCATE c;

    IF (SELECT COUNT(DISTINCT RolCodigo) FROM resp.AsignacionResponsableTitulacion WHERE GrupoTitulacionId = @GrupoTitulacionId AND EsTribunal = 1 AND Activo = 1) < 3
        THROW 59732, 'La defensa requiere 3 miembros activos del tribunal.', 1;
END;
GO

CREATE OR ALTER PROCEDURE eval.sp_CalcularConsolidadoEstudiante
    @ExpedienteId BIGINT,
    @GrupoTitulacionId BIGINT,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @MecanismoCodigo VARCHAR(30) = (SELECT MecanismoCodigo FROM tit.GrupoTitulacion WHERE GrupoTitulacionId = @GrupoTitulacionId);
    DECLARE @Evaluadores INT;
    DECLARE @PromedioTrabajo DECIMAL(5,2);
    DECLARE @PromedioOral DECIMAL(5,2);
    DECLARE @PromedioExamen DECIMAL(5,2);
    DECLARE @NotaTitulacionSobre20 DECIMAL(5,2);
    DECLARE @NotaAsignaturas DECIMAL(5,2) = (SELECT PromedioAsignaturas FROM tit.ExpedienteTitulacion WHERE ExpedienteId = @ExpedienteId);
    DECLARE @PesoAsignaturas DECIMAL(10,4) = ISNULL(TRY_CONVERT(DECIMAL(10,4), (SELECT Valor FROM cat.ParametroTitulacion WHERE Codigo = 'TIT_PESO_ASIGNATURAS')), 0.80);
    DECLARE @PesoTitulacion DECIMAL(10,4) = ISNULL(TRY_CONVERT(DECIMAL(10,4), (SELECT Valor FROM cat.ParametroTitulacion WHERE Codigo = 'TIT_PESO_TITULACION')), 0.20);
    DECLARE @NotaMinima DECIMAL(5,2) = ISNULL(TRY_CONVERT(DECIMAL(5,2), (SELECT Valor FROM cat.ParametroTitulacion WHERE Codigo = 'TIT_NOTA_MINIMA_APROBACION')), 7.00);

    SELECT
        @Evaluadores = COUNT(DISTINCT EvaluadorNumero),
        @PromedioTrabajo = AVG(NotaTrabajoEscrito),
        @PromedioOral = AVG(NotaDefensaOral),
        @PromedioExamen = AVG(NotaExamenComplexivo)
    FROM eval.CalificacionEvaluador
    WHERE ExpedienteId = @ExpedienteId
      AND GrupoTitulacionId = @GrupoTitulacionId
      AND Cerrado = 1;

    SET @NotaTitulacionSobre20 =
        CASE
            WHEN @MecanismoCodigo = 'EXAMEN_COMPLEXIVO' AND @PromedioOral IS NOT NULL THEN ROUND(ISNULL(@PromedioExamen, 0) + @PromedioOral, 2)
            WHEN @MecanismoCodigo = 'EXAMEN_COMPLEXIVO' THEN ROUND(ISNULL(@PromedioExamen, 0) * 2, 2)
            ELSE ROUND(ISNULL(@PromedioTrabajo, 0) + ISNULL(@PromedioOral, 0), 2)
        END;

    DECLARE @EquivAsignaturas DECIMAL(5,2) = ROUND(ISNULL(@NotaAsignaturas, 0) * @PesoAsignaturas, 2);
    DECLARE @EquivTitulacion DECIMAL(5,2) = ROUND(@NotaTitulacionSobre20 * (@PesoTitulacion / 2), 2);
    DECLARE @NotaFinal DECIMAL(5,2) = ROUND(@EquivAsignaturas + @EquivTitulacion, 2);
    DECLARE @Completos BIT = CASE WHEN ISNULL(@Evaluadores, 0) >= 3 THEN 1 ELSE 0 END;
    DECLARE @Aprobado BIT = CASE WHEN @Completos = 1 AND @NotaFinal >= @NotaMinima THEN 1 ELSE 0 END;
    DECLARE @NumeroIdentificacion NVARCHAR(20) = (
        SELECT TOP 1 COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion)
        FROM tit.ExpedienteTitulacion E
        LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
        WHERE E.ExpedienteId = @ExpedienteId
    );

    MERGE eval.CalificacionConsolidada AS T
    USING (SELECT @ExpedienteId AS ExpedienteId) AS S
    ON T.ExpedienteId = S.ExpedienteId
    WHEN MATCHED THEN
        UPDATE SET
            NumeroIdentificacion = @NumeroIdentificacion,
            NotaAsignaturas = @NotaAsignaturas,
            EquivalenciaAsignaturas80 = @EquivAsignaturas,
            PromedioTrabajoEscrito = @PromedioTrabajo,
            PromedioDefensaOral = @PromedioOral,
            PromedioExamenComplexivo = @PromedioExamen,
            NotaTitulacionSobre20 = @NotaTitulacionSobre20,
            EquivalenciaTitulacion20 = @EquivTitulacion,
            NotaFinalGrado = @NotaFinal,
            EvaluadoresCompletos = @Completos,
            Aprobado = @Aprobado,
            FechaConsolidacion = SYSDATETIME()
    WHEN NOT MATCHED THEN
        INSERT(ExpedienteId, NumeroIdentificacion, NotaAsignaturas, EquivalenciaAsignaturas80, PromedioTrabajoEscrito, PromedioDefensaOral, PromedioExamenComplexivo, NotaTitulacionSobre20, EquivalenciaTitulacion20, NotaFinalGrado, EvaluadoresCompletos, Aprobado)
        VALUES(@ExpedienteId, @NumeroIdentificacion, @NotaAsignaturas, @EquivAsignaturas, @PromedioTrabajo, @PromedioOral, @PromedioExamen, @NotaTitulacionSobre20, @EquivTitulacion, @NotaFinal, @Completos, @Aprobado);

    UPDATE tit.ExpedienteTitulacion
       SET NotaPromedioAsignaturas80 = @EquivAsignaturas,
           NotaProcesoTitulacion20 = @EquivTitulacion,
           NotaFinalGrado = @NotaFinal,
           RubricaTitulacionCumple = @Completos,
           EstadoExpediente = CASE WHEN @Aprobado = 1 THEN 'CALIFICADO' ELSE EstadoExpediente END,
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;

    SELECT * FROM eval.CalificacionConsolidada WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE eval.sp_RegistrarNotaEvaluador
    @ExpedienteId BIGINT,
    @GrupoTitulacionId BIGINT,
    @EvaluadorNumero INT,
    @ResponsableTitulacionId BIGINT = NULL,
    @NotaTrabajoEscrito DECIMAL(5,2) = NULL,
    @NotaDefensaOral DECIMAL(5,2) = NULL,
    @NotaExamenComplexivo DECIMAL(5,2) = NULL,
    @Observacion NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @EvaluadorNumero NOT BETWEEN 1 AND 3
        THROW 59740, 'El numero de evaluador debe estar entre 1 y 3.', 1;

    IF @ResponsableTitulacionId IS NULL
    BEGIN
        SELECT TOP (1) @ResponsableTitulacionId = ResponsableTitulacionId
        FROM resp.AsignacionResponsableTitulacion
        WHERE GrupoTitulacionId = @GrupoTitulacionId
          AND Orden = @EvaluadorNumero
          AND Activo = 1
        ORDER BY AsignacionId DESC;
    END;

    IF @ResponsableTitulacionId IS NULL
        THROW 59741, 'No existe responsable/evaluador asignado para este numero.', 1;

    DECLARE @NotaSobre20 DECIMAL(5,2) =
        CASE
            WHEN @NotaExamenComplexivo IS NOT NULL AND @NotaDefensaOral IS NOT NULL THEN ROUND(@NotaExamenComplexivo + @NotaDefensaOral, 2)
            WHEN @NotaExamenComplexivo IS NOT NULL THEN ROUND(@NotaExamenComplexivo * 2, 2)
            ELSE ROUND(ISNULL(@NotaTrabajoEscrito, 0) + ISNULL(@NotaDefensaOral, 0), 2)
        END;

    MERGE eval.CalificacionEvaluador AS T
    USING (SELECT @ExpedienteId AS ExpedienteId, @GrupoTitulacionId AS GrupoTitulacionId, @EvaluadorNumero AS EvaluadorNumero) AS S
    ON T.ExpedienteId = S.ExpedienteId
   AND T.GrupoTitulacionId = S.GrupoTitulacionId
   AND T.EvaluadorNumero = S.EvaluadorNumero
    WHEN MATCHED THEN
        UPDATE SET ResponsableTitulacionId = @ResponsableTitulacionId,
                   NotaTrabajoEscrito = @NotaTrabajoEscrito,
                   NotaDefensaOral = @NotaDefensaOral,
                   NotaExamenComplexivo = @NotaExamenComplexivo,
                   NotaTitulacionSobre20 = @NotaSobre20,
                   Observacion = @Observacion,
                   Cerrado = 1,
                   FechaRegistro = SYSDATETIME(),
                   UsuarioRegistro = COALESCE(@Usuario, SYSTEM_USER)
    WHEN NOT MATCHED THEN
        INSERT(ExpedienteId, GrupoTitulacionId, ResponsableTitulacionId, EvaluadorNumero, NotaTrabajoEscrito, NotaDefensaOral, NotaExamenComplexivo, NotaTitulacionSobre20, Observacion, Cerrado, UsuarioRegistro)
        VALUES(@ExpedienteId, @GrupoTitulacionId, @ResponsableTitulacionId, @EvaluadorNumero, @NotaTrabajoEscrito, @NotaDefensaOral, @NotaExamenComplexivo, @NotaSobre20, @Observacion, 1, COALESCE(@Usuario, SYSTEM_USER));

    EXEC eval.sp_CalcularConsolidadoEstudiante @ExpedienteId = @ExpedienteId, @GrupoTitulacionId = @GrupoTitulacionId, @Usuario = @Usuario;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_GenerarActaGradoEstudiante
    @ExpedienteId BIGINT,
    @NumeroActa NVARCHAR(100) = NULL,
    @FechaActa DATE,
    @HoraActa TIME = NULL,
    @Ciudad NVARCHAR(100) = N'Quito',
    @Escuela NVARCHAR(250) = NULL,
    @AutoridadAcademica NVARCHAR(250) = NULL,
    @CoordinadorAcademico NVARCHAR(250) = NULL,
    @DocenteEvaluador NVARCHAR(250) = NULL,
    @RutaActaPdf NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.HabilitacionTitulacion WHERE ExpedienteId = @ExpedienteId)
        THROW 59750, 'El expediente no esta habilitado para titulacion.', 1;

    IF EXISTS (SELECT 1 FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId)
        THROW 59751, 'El expediente ya tiene acta generada.', 1;

    IF EXISTS (
        SELECT 1
        FROM tit.ExpedienteTitulacion
        WHERE ExpedienteId = @ExpedienteId
          AND (ISNULL(PracticasPreprofesionalesCumple, 0) = 0 OR ISNULL(VinculacionCumple, 0) = 0)
    )
        THROW 59752, 'Faltan Practicas laborales o Servicio Comunitario reconocidos.', 1;

    IF EXISTS (
        SELECT 1
        FROM cat.TipoDocumentoTitulacion TD
        CROSS JOIN tit.ExpedienteTitulacion E
        WHERE E.ExpedienteId = @ExpedienteId
          AND TD.Activo = 1
          AND TD.EsObligatorio = 1
          AND TD.Codigo NOT IN ('TITULO_REGISTRO_SENESCYT', 'TITULO_INTEC')
          AND (TD.AplicaMecanismoCodigo IS NULL OR TD.AplicaMecanismoCodigo = E.MecanismoTitulacionId)
          AND NOT EXISTS (
              SELECT 1
              FROM doc.DocumentoTitulacion D
              WHERE D.ExpedienteId = E.ExpedienteId
                AND D.TipoDocumentoCodigo = TD.Codigo
                AND D.EstadoCodigo <> 'ANULADO'
          )
    )
        THROW 59753, 'Faltan documentos obligatorios para generar acta.', 1;

    IF NOT EXISTS (
        SELECT 1
        FROM eval.CalificacionConsolidada
        WHERE ExpedienteId = @ExpedienteId
          AND EvaluadoresCompletos = 1
          AND Aprobado = 1
    )
        THROW 59754, 'Faltan 3 evaluadores completos o la nota final no esta aprobada.', 1;

    DECLARE @NumeroIdentificacion NVARCHAR(20);
    DECLARE @Nombres NVARCHAR(250);
    DECLARE @Carrera NVARCHAR(250);
    DECLARE @MecanismoCodigo VARCHAR(30);
    DECLARE @TituloOtorgado NVARCHAR(300);

    SELECT TOP (1)
        @NumeroIdentificacion = COALESCE(E.NumeroIdentificacion, ER.NumeroIdentificacion),
        @Nombres = ER.ApellidosNombres,
        @Carrera = E.Carrera,
        @MecanismoCodigo = E.MecanismoTitulacionId,
        @TituloOtorgado = E.TituloOtorgado
    FROM tit.ExpedienteTitulacion E
    LEFT JOIN core.EstudianteRef ER ON ER.EstudianteRefId = E.EstudianteRefId
    WHERE E.ExpedienteId = @ExpedienteId;

    SET @NumeroActa = COALESCE(@NumeroActa, CONCAT(N'ACTA-', @ExpedienteId, N'-', FORMAT(SYSDATETIME(), 'yyyyMMddHHmmss')));

    INSERT INTO tit.ActaGrado
    (
        ExpedienteId, NumeroActa, NumeroActaGrado, NumeroIdentificacion, NombresEstudiante, Carrera, Escuela,
        Modalidad, MecanismoCodigo, TituloOtorgado, FechaActa, HoraActa, Ciudad,
        NotaAsignaturas, EquivalenciaAsignaturas80, NotaProcesoTitulacion, EquivalenciaTitulacion20,
        NotaFinalGrado, AutoridadAcademica, CoordinadorAcademico, DocenteEvaluador, RutaActaPdf,
        EstadoCodigo, UsuarioGeneracion, UsuarioCreacion, FechaCreacion
    )
    SELECT
        @ExpedienteId, @NumeroActa, @NumeroActa, @NumeroIdentificacion, @Nombres, @Carrera, @Escuela,
        @MecanismoCodigo, @MecanismoCodigo, @TituloOtorgado, @FechaActa, @HoraActa, @Ciudad,
        NotaAsignaturas, EquivalenciaAsignaturas80, NotaTitulacionSobre20, EquivalenciaTitulacion20,
        NotaFinalGrado, @AutoridadAcademica, @CoordinadorAcademico, @DocenteEvaluador, @RutaActaPdf,
        'ACTA_GENERADA', COALESCE(@Usuario, SYSTEM_USER), COALESCE(@Usuario, SYSTEM_USER), SYSDATETIME()
    FROM eval.CalificacionConsolidada
    WHERE ExpedienteId = @ExpedienteId;

    UPDATE tit.ExpedienteTitulacion
       SET NumeroActaGrado = @NumeroActa,
           FechaActaGrado = @FechaActa,
           EstadoExpediente = 'ACTA_GENERADA',
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;

    SELECT * FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_CargarTituloRegistrado
    @ExpedienteId BIGINT,
    @NumeroIdentificacion NVARCHAR(20) = NULL,
    @NombreArchivo NVARCHAR(260),
    @RutaNube NVARCHAR(1000) = NULL,
    @UrlPublica NVARCHAR(1000) = NULL,
    @HashArchivo VARBINARY(64) = NULL,
    @ContentType NVARCHAR(150) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId)
        THROW 59760, 'No se puede cargar titulo registrado sin acta de grado.', 1;

    INSERT INTO doc.DocumentoTitulacion(ExpedienteId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica, HashArchivo, ContentType, EstadoCodigo, UsuarioCarga)
    VALUES(@ExpedienteId, @NumeroIdentificacion, 'TITULO_REGISTRO_SENESCYT', @NombreArchivo, @RutaNube, @UrlPublica, @HashArchivo, @ContentType, 'TITULO_REGISTRADO', COALESCE(@Usuario, SYSTEM_USER));

    UPDATE tit.ExpedienteTitulacion
       SET EstadoExpediente = 'TITULO_REGISTRADO',
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_CargarTituloIntec
    @ExpedienteId BIGINT,
    @NumeroIdentificacion NVARCHAR(20) = NULL,
    @NombreArchivo NVARCHAR(260),
    @RutaNube NVARCHAR(1000) = NULL,
    @UrlPublica NVARCHAR(1000) = NULL,
    @HashArchivo VARBINARY(64) = NULL,
    @ContentType NVARCHAR(150) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId)
        THROW 59770, 'No se puede cargar titulo INTEC sin acta de grado.', 1;

    INSERT INTO doc.DocumentoTitulacion(ExpedienteId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica, HashArchivo, ContentType, EstadoCodigo, UsuarioCarga)
    VALUES(@ExpedienteId, @NumeroIdentificacion, 'TITULO_INTEC', @NombreArchivo, @RutaNube, @UrlPublica, @HashArchivo, @ContentType, 'TITULO_INTEC_CARGADO', COALESCE(@Usuario, SYSTEM_USER));

    UPDATE tit.ExpedienteTitulacion
       SET EstadoExpediente = 'TITULO_INTEC_CARGADO',
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;
END;
GO

/* ============================================================================
   8. Diagnostico final
   ============================================================================ */
CREATE OR ALTER PROCEDURE util.sp_DiagnosticoPortalTitulacion
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Resultado TABLE
    (
        Tipo NVARCHAR(40),
        Nombre NVARCHAR(200),
        Estado NVARCHAR(20),
        Detalle NVARCHAR(1000)
    );

    INSERT INTO @Resultado(Tipo, Nombre, Estado, Detalle)
    SELECT 'SCHEMA', V.Nombre, CASE WHEN S.name IS NULL THEN 'FALTA' ELSE 'OK' END, NULL
    FROM (VALUES ('cat'),('core'),('tit'),('resp'),('eval'),('doc'),('stg'),('rpt'),('etl'),('seg'),('util')) V(Nombre)
    LEFT JOIN sys.schemas S ON S.name = V.Nombre;

    INSERT INTO @Resultado(Tipo, Nombre, Estado, Detalle)
    SELECT 'TABLE', V.Nombre, CASE WHEN OBJECT_ID(V.Nombre, 'U') IS NULL THEN 'FALTA' ELSE 'OK' END, NULL
    FROM (VALUES
        ('cat.MecanismoTitulacion'), ('cat.EstadoTitulacion'), ('cat.RolResponsableTitulacion'),
        ('cat.TipoDocumentoTitulacion'), ('cat.TipoComponenteCalificacion'), ('cat.ParametroTitulacion'),
        ('tit.HabilitacionTitulacion'), ('tit.ProgramacionTitulacion'), ('tit.TribunalTitulacion'),
        ('tit.ExamenComplexivo'), ('tit.DefensaGrado'), ('tit.GrupoTitulacion'), ('tit.GrupoTitulacionEstudiante'),
        ('resp.ResponsableTitulacion'), ('resp.AsignacionResponsableTitulacion'),
        ('eval.RubricaTitulacion'), ('eval.CriterioRubrica'), ('eval.CalificacionEvaluador'),
        ('eval.CalificacionConsolidada'), ('doc.DocumentoTitulacion'), ('tit.ActaGrado')
    ) V(Nombre);

    INSERT INTO @Resultado(Tipo, Nombre, Estado, Detalle)
    SELECT 'VIEW', V.Nombre, CASE WHEN OBJECT_ID(V.Nombre, 'V') IS NULL THEN 'FALTA' ELSE 'OK' END, NULL
    FROM (VALUES
        ('rpt.vw_EstudiantesCumplenRequisitosTitulacion'), ('rpt.vw_EstudiantesPendientesRequisitosTitulacion'),
        ('rpt.vw_HabilitacionesTitulacion'), ('rpt.vw_MecanismoTitulacionExpediente'),
        ('rpt.vw_PrevalidacionMecanismoTitulacion'), ('rpt.vw_ExamenComplexivo'), ('rpt.vw_DefensaGrado'),
        ('rpt.vw_GruposComplexivo'), ('rpt.vw_DefensasGrado'),
        ('rpt.vw_ResponsablesTribunal'), ('rpt.vw_CalificacionesPendientes'), ('rpt.vw_CalificacionesConsolidadas'),
        ('rpt.vw_ActasGeneradas'), ('rpt.vw_TitulosCargados')
    ) V(Nombre);

    INSERT INTO @Resultado(Tipo, Nombre, Estado, Detalle)
    SELECT 'PROCEDURE', V.Nombre, CASE WHEN OBJECT_ID(V.Nombre, 'P') IS NULL THEN 'FALTA' ELSE 'OK' END, NULL
    FROM (VALUES
        ('tit.sp_ListarEstudiantesAptos'), ('tit.sp_HabilitarEstudianteTitulacion'),
        ('tit.sp_PrevalidarMecanismoTitulacion'),
        ('tit.sp_CrearGrupoComplexivo'), ('tit.sp_CrearDefensaGrado'),
        ('resp.sp_AsignarResponsableComplexivo'), ('resp.sp_AsignarTribunalDefensa'),
        ('eval.sp_RegistrarNotaEvaluador'), ('eval.sp_CalcularConsolidadoEstudiante'),
        ('tit.sp_GenerarActaGradoEstudiante'), ('doc.sp_CargarTituloRegistrado'),
        ('doc.sp_CargarTituloIntec'), ('util.sp_DiagnosticoPortalTitulacion')
    ) V(Nombre);

    INSERT INTO @Resultado(Tipo, Nombre, Estado, Detalle)
    VALUES
        ('CATALOG', 'Mecanismos', CASE WHEN (SELECT COUNT(1) FROM cat.MecanismoTitulacion WHERE Codigo IN ('EXAMEN_COMPLEXIVO','DEFENSA_GRADO')) = 2 THEN 'OK' ELSE 'FALTA' END, NULL),
        ('CATALOG', 'Estados', CASE WHEN (SELECT COUNT(1) FROM cat.EstadoTitulacion) >= 11 THEN 'OK' ELSE 'FALTA' END, NULL),
        ('CATALOG', 'Roles', CASE WHEN (SELECT COUNT(1) FROM cat.RolResponsableTitulacion) >= 9 THEN 'OK' ELSE 'FALTA' END, NULL),
        ('CATALOG', 'Documentos', CASE WHEN (SELECT COUNT(1) FROM cat.TipoDocumentoTitulacion) >= 11 THEN 'OK' ELSE 'FALTA' END, NULL),
        ('EXTERNAL', 'INTECBDD', CASE WHEN DB_ID(N'INTECBDD') IS NULL THEN 'NO_VALIDADO' ELSE 'OK' END, N'Se valida disponibilidad de la base, no se crea dependencia rigida.'),
        ('EXTERNAL', 'INTEC_PRACTICAS_PREPROFESIONALES', CASE WHEN DB_ID(N'INTEC_PRACTICAS_PREPROFESIONALES') IS NULL THEN 'NO_VALIDADO' ELSE 'OK' END, N'Se valida disponibilidad de la base, no se crea dependencia rigida.');

    SELECT *
    FROM @Resultado
    ORDER BY
        CASE Tipo
            WHEN 'SCHEMA' THEN 1
            WHEN 'TABLE' THEN 2
            WHEN 'VIEW' THEN 3
            WHEN 'PROCEDURE' THEN 4
            WHEN 'CATALOG' THEN 5
            ELSE 6
        END,
        Nombre;
END;
GO

EXEC util.sp_DiagnosticoPortalTitulacion @Usuario = NULL;
GO
