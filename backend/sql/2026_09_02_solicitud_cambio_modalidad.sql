SET NOCOUNT ON;
SET XACT_ABORT ON;

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'sol')
    EXEC(N'CREATE SCHEMA sol AUTHORIZATION dbo');

IF OBJECT_ID(N'sol.SolicitudCambioModalidad', N'U') IS NULL
BEGIN
    CREATE TABLE sol.SolicitudCambioModalidad
    (
        IdSolicitud BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_SolicitudCambioModalidad PRIMARY KEY,
        CodigoEstud INT NOT NULL,
        Cedula NVARCHAR(32) NOT NULL,
        Estudiante NVARCHAR(250) NOT NULL,
        CarreraOrigen INT NOT NULL,
        CarreraOrigenNombre NVARCHAR(250) NOT NULL,
        CarreraDestino INT NOT NULL,
        CarreraDestinoNombre NVARCHAR(250) NOT NULL,
        ModalidadOrigen INT NULL,
        ModalidadOrigenNombre NVARCHAR(150) NULL,
        CodigoPeriodoOrigen INT NOT NULL,
        PeriodoOrigenNombre NVARCHAR(250) NOT NULL,
        TipoPeriodoOrigen NCHAR(1) NOT NULL,
        ModalidadDestino INT NOT NULL,
        ModalidadDestinoNombre NVARCHAR(150) NOT NULL,
        CodigoPeriodoHomologacion INT NOT NULL,
        PeriodoHomologacionNombre NVARCHAR(250) NOT NULL,
        TipoPeriodoDestino NCHAR(1) NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_TipoPeriodo DEFAULT N'H',
        Estado NVARCHAR(20) NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Estado DEFAULT N'PENDIENTE',
        Motivo NVARCHAR(1000) NOT NULL,
        ArchivoNombre NVARCHAR(260) NOT NULL,
        ArchivoRuta NVARCHAR(600) NOT NULL,
        ArchivoSha256 CHAR(64) NOT NULL,
        ArchivoTamano BIGINT NOT NULL,
        GraphDocumentoId BIGINT NULL,
        GraphWebUrl NVARCHAR(1200) NULL,
        EstadoExpediente NVARCHAR(30) NULL,
        TotalMateriasPensum INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Total DEFAULT 0,
        MateriasMatriculadas INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Matriculadas DEFAULT 0,
        MateriasExistentes INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Existentes DEFAULT 0,
        MateriasMigradas INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Migradas DEFAULT 0,
        MateriasOrigenRetiradas INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_MateriasRetiradas DEFAULT 0,
        CabecerasOrigenRetiradas INT NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_CabecerasRetiradas DEFAULT 0,
        CabeceraCreada BIT NULL,
        CreadoPor NVARCHAR(256) NOT NULL,
        FechaCreacion DATETIME2 NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidad_Fecha DEFAULT SYSUTCDATETIME(),
        RevisadoPor NVARCHAR(256) NULL,
        FechaRevision DATETIME2 NULL,
        ObservacionRevision NVARCHAR(1000) NULL,
        AplicadoPor NVARCHAR(256) NULL,
        FechaAplicacion DATETIME2 NULL,
        CONSTRAINT CK_SolicitudCambioModalidad_Estado
            CHECK (Estado IN (N'PENDIENTE', N'APROBADA', N'RECHAZADA', N'APLICADA')),
        CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodo
            CHECK (TipoPeriodoDestino IN (N'R', N'H')),
        CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodoOrigen
            CHECK (TipoPeriodoOrigen IN (N'R', N'H'))
    );

    CREATE INDEX IX_SolicitudCambioModalidad_Estudiante
        ON sol.SolicitudCambioModalidad(CodigoEstud, FechaCreacion DESC);
    CREATE INDEX IX_SolicitudCambioModalidad_Estado
        ON sol.SolicitudCambioModalidad(Estado, FechaCreacion DESC);
END;

IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'CodigoPeriodoOrigen') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD CodigoPeriodoOrigen INT NULL;
IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'PeriodoOrigenNombre') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD PeriodoOrigenNombre NVARCHAR(250) NULL;
IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'TipoPeriodoOrigen') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD TipoPeriodoOrigen NCHAR(1) NULL;
IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'MateriasMigradas') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD MateriasMigradas INT NOT NULL
        CONSTRAINT DF_SolicitudCambioModalidad_Migradas DEFAULT 0 WITH VALUES;
IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'MateriasOrigenRetiradas') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD MateriasOrigenRetiradas INT NOT NULL
        CONSTRAINT DF_SolicitudCambioModalidad_MateriasRetiradas DEFAULT 0 WITH VALUES;
IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'CabecerasOrigenRetiradas') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidad ADD CabecerasOrigenRetiradas INT NOT NULL
        CONSTRAINT DF_SolicitudCambioModalidad_CabecerasRetiradas DEFAULT 0 WITH VALUES;

IF COL_LENGTH(N'sol.SolicitudCambioModalidad', N'TipoPeriodoDestino') IS NULL
BEGIN
    ALTER TABLE sol.SolicitudCambioModalidad
    ADD TipoPeriodoDestino NCHAR(1) NOT NULL
        CONSTRAINT DF_SolicitudCambioModalidad_TipoPeriodo DEFAULT N'H' WITH VALUES;
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sol.SolicitudCambioModalidad')
      AND name = N'CK_SolicitudCambioModalidad_TipoPeriodo'
)
BEGIN
    EXEC
    (
        N'ALTER TABLE sol.SolicitudCambioModalidad '
        + N'ADD CONSTRAINT CK_SolicitudCambioModalidad_TipoPeriodo '
        + N'CHECK (TipoPeriodoDestino IN (N''R'', N''H''));'
    );
END;

IF OBJECT_ID(N'sol.SolicitudCambioModalidadMateria', N'U') IS NULL
BEGIN
    CREATE TABLE sol.SolicitudCambioModalidadMateria
    (
        IdDetalle BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_SolicitudCambioModalidadMateria PRIMARY KEY,
        IdSolicitud BIGINT NOT NULL,
        CodigoMateria INT NOT NULL,
        CodigoComun NVARCHAR(100) NULL,
        NombreMateria NVARCHAR(300) NOT NULL,
        Nivel INT NULL,
        Creditos DECIMAL(8,2) NULL,
        MateriaOrigen INT NULL,
        CodigoComunOrigen NVARCHAR(100) NULL,
        NotaOrigen DECIMAL(18,3) NULL,
        Estado NVARCHAR(20) NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidadMateria_Estado DEFAULT N'PENDIENTE',
        NumMatricula INT NULL,
        Observacion NVARCHAR(500) NULL,
        CONSTRAINT FK_SolicitudCambioModalidadMateria_Solicitud
            FOREIGN KEY (IdSolicitud)
            REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
        CONSTRAINT UQ_SolicitudCambioModalidadMateria
            UNIQUE (IdSolicitud, CodigoMateria),
        CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado
            CHECK (Estado IN (N'PENDIENTE', N'EXISTENTE', N'MATRICULADA', N'MIGRADA'))
    );
END;

IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'MateriaOrigen') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD MateriaOrigen INT NULL;
IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'CodigoComunOrigen') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD CodigoComunOrigen NVARCHAR(100) NULL;
IF COL_LENGTH(N'sol.SolicitudCambioModalidadMateria', N'NotaOrigen') IS NULL
    ALTER TABLE sol.SolicitudCambioModalidadMateria ADD NotaOrigen DECIMAL(18,3) NULL;

IF EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sol.SolicitudCambioModalidadMateria')
      AND name = N'CK_SolicitudCambioModalidadMateria_Estado'
      AND definition NOT LIKE N'%MIGRADA%'
)
BEGIN
    ALTER TABLE sol.SolicitudCambioModalidadMateria
        DROP CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado;
    ALTER TABLE sol.SolicitudCambioModalidadMateria
        ADD CONSTRAINT CK_SolicitudCambioModalidadMateria_Estado
        CHECK (Estado IN (N'PENDIENTE', N'EXISTENTE', N'MATRICULADA', N'MIGRADA'));
END;

IF OBJECT_ID(N'sol.SolicitudCambioModalidadArchivo', N'U') IS NULL
BEGIN
    CREATE TABLE sol.SolicitudCambioModalidadArchivo
    (
        IdArchivo BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_SolicitudCambioModalidadArchivo PRIMARY KEY,
        IdSolicitud BIGINT NOT NULL,
        Orden INT NOT NULL,
        ArchivoNombreOriginal NVARCHAR(260) NOT NULL,
        ArchivoNombreNube NVARCHAR(260) NULL,
        ArchivoRuta NVARCHAR(600) NULL,
        ArchivoSha256 CHAR(64) NOT NULL,
        ArchivoTamano BIGINT NOT NULL,
        GraphDocumentoId BIGINT NULL,
        GraphWebUrl NVARCHAR(1200) NULL,
        EstadoExpediente NVARCHAR(30) NOT NULL
            CONSTRAINT DF_SolicitudCambioModalidadArchivo_Estado DEFAULT N'PENDIENTE',
        FechaCarga DATETIME2(3) NULL,
        CONSTRAINT FK_SolicitudCambioModalidadArchivo_Solicitud
            FOREIGN KEY (IdSolicitud) REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
        CONSTRAINT UQ_SolicitudCambioModalidadArchivo_Orden
            UNIQUE (IdSolicitud, Orden),
        CONSTRAINT CK_SolicitudCambioModalidadArchivo_Estado
            CHECK (EstadoExpediente IN (N'PENDIENTE', N'CARGADO', N'ERROR')),
        CONSTRAINT CK_SolicitudCambioModalidadArchivo_Tamano
            CHECK (ArchivoTamano > 0)
    );
    CREATE INDEX IX_SolicitudCambioModalidadArchivo_Solicitud
        ON sol.SolicitudCambioModalidadArchivo(IdSolicitud, Orden);
END;

IF OBJECT_ID(N'sol.RespaldoCambioModalidad', N'U') IS NULL
BEGIN
    CREATE TABLE sol.RespaldoCambioModalidad
    (
        IdRespaldo BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_RespaldoCambioModalidad PRIMARY KEY,
        IdSolicitud BIGINT NOT NULL,
        CodigoEstud INT NOT NULL,
        CarreraOrigen INT NOT NULL,
        CarreraDestino INT NOT NULL,
        PeriodoOrigen INT NOT NULL,
        PeriodoDestino INT NOT NULL,
        ModalidadOrigen INT NULL,
        ModalidadDestino INT NOT NULL,
        TotalCabeceras INT NOT NULL,
        TotalMaterias INT NOT NULL,
        HashContenido CHAR(64) NOT NULL,
        FechaRespaldo DATETIME2(3) NOT NULL
            CONSTRAINT DF_RespaldoCambioModalidad_Fecha DEFAULT SYSUTCDATETIME(),
        RespaldadoPor NVARCHAR(256) NOT NULL,
        CONSTRAINT FK_RespaldoCambioModalidad_Solicitud
            FOREIGN KEY (IdSolicitud) REFERENCES sol.SolicitudCambioModalidad(IdSolicitud),
        CONSTRAINT UQ_RespaldoCambioModalidad_Solicitud UNIQUE (IdSolicitud)
    );
END;

IF OBJECT_ID(N'sol.RespaldoCambioModalidadFila', N'U') IS NULL
BEGIN
    CREATE TABLE sol.RespaldoCambioModalidadFila
    (
        IdFila BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_RespaldoCambioModalidadFila PRIMARY KEY,
        IdRespaldo BIGINT NOT NULL,
        TipoRegistro NVARCHAR(20) NOT NULL,
        ClaveNatural NVARCHAR(600) NOT NULL,
        DatosJson NVARCHAR(MAX) NOT NULL,
        Sha256 CHAR(64) NOT NULL,
        CONSTRAINT FK_RespaldoCambioModalidadFila_Respaldo
            FOREIGN KEY (IdRespaldo) REFERENCES sol.RespaldoCambioModalidad(IdRespaldo),
        CONSTRAINT UQ_RespaldoCambioModalidadFila_Registro
            UNIQUE (IdRespaldo, TipoRegistro, ClaveNatural),
        CONSTRAINT CK_RespaldoCambioModalidadFila_Tipo
            CHECK (TipoRegistro IN (N'CABECERA', N'MATERIA'))
    );
    CREATE INDEX IX_RespaldoCambioModalidadFila_Respaldo
        ON sol.RespaldoCambioModalidadFila(IdRespaldo, TipoRegistro);
END;
