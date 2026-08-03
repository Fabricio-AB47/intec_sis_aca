/* ============================================================================
   INTEC_GRAPH_INTEGRACION - EXPEDIENTES DOCUMENTALES

   Esta capa NO reemplaza los expedientes funcionales de Titulacion, Practicas,
   Vinculacion o Ingles. Registra la ubicacion Microsoft Graph, sus versiones,
   sesiones de carga y el enlace logico con la entidad propietaria.
   ============================================================================ */
USE [INTEC_GRAPH_INTEGRACION];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'doc')
    EXEC(N'CREATE SCHEMA doc AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat')
    EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'app')
    EXEC(N'CREATE SCHEMA app AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'cat.TipoOperacionGraph', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoOperacionGraph
    (
        TipoOperacionCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL
            CONSTRAINT PK_TipoOperacionGraph PRIMARY KEY,
        Nombre NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NOT NULL,
        HttpMethod VARCHAR(10) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EndpointBase NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Descripcion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_TipoOperacionGraph_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_TipoOperacionGraph_Fecha DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID(N'app.PermisoGraphRequerido', N'U') IS NULL
BEGIN
    CREATE TABLE app.PermisoGraphRequerido
    (
        PermisoGraphRequeridoId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_PermisoGraphRequerido PRIMARY KEY,
        TipoOperacionCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Permiso NVARCHAR(200) COLLATE Modern_Spanish_CI_AS NOT NULL,
        TipoPermiso VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EsPrivilegioMinimo BIT NOT NULL CONSTRAINT DF_PermisoGraphRequerido_Minimo DEFAULT 0,
        RequiereConsentimientoAdmin BIT NOT NULL CONSTRAINT DF_PermisoGraphRequerido_Consentimiento DEFAULT 0,
        Justificacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_PermisoGraphRequerido_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_PermisoGraphRequerido_Fecha DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_PermisoGraphRequerido_TipoOperacion FOREIGN KEY(TipoOperacionCodigo)
            REFERENCES cat.TipoOperacionGraph(TipoOperacionCodigo),
        CONSTRAINT UQ_PermisoGraphRequerido UNIQUE(TipoOperacionCodigo, Permiso)
    );
END;
GO

IF OBJECT_ID(N'cat.TipoExpedienteGraph', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoExpedienteGraph
    (
        TipoExpedienteGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL
            CONSTRAINT PK_TipoExpedienteGraph PRIMARY KEY,
        Nombre NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Descripcion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_TipoExpedienteGraph_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_TipoExpedienteGraph_Fecha DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID(N'cat.EstadoDocumentoGraph', N'U') IS NULL
BEGIN
    CREATE TABLE cat.EstadoDocumentoGraph
    (
        EstadoDocumentoGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL
            CONSTRAINT PK_EstadoDocumentoGraph PRIMARY KEY,
        Nombre NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EsFinal BIT NOT NULL CONSTRAINT DF_EstadoDocumentoGraph_EsFinal DEFAULT 0,
        Activo BIT NOT NULL CONSTRAINT DF_EstadoDocumentoGraph_Activo DEFAULT 1
    );
END;
GO

MERGE cat.TipoExpedienteGraph AS target
USING (VALUES
    ('INGLES', N'Ingles', N'Archivos y evidencias de evaluacion del idioma Ingles.'),
    ('TITULACION', N'Titulacion', N'Documentos habilitantes, actas y titulos.'),
    ('PRACTICAS', N'Practicas preprofesionales', N'Documentos del expediente de practicas preprofesionales.'),
    ('VINCULACION', N'Vinculacion con la sociedad', N'Documentos del expediente de vinculacion con la sociedad.')
) AS source(Codigo, Nombre, Descripcion)
ON target.TipoExpedienteGraphCodigo = source.Codigo
WHEN MATCHED THEN
    UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(TipoExpedienteGraphCodigo, Nombre, Descripcion)
    VALUES(source.Codigo, source.Nombre, source.Descripcion);
GO

MERGE cat.EstadoDocumentoGraph AS target
USING (VALUES
    ('CARGA_INICIADA', N'Carga iniciada', 0),
    ('CARGADO', N'Cargado', 1),
    ('REEMPLAZADO', N'Reemplazado', 1),
    ('EXPIRADO', N'Expirado', 1),
    ('ERROR', N'Error', 1),
    ('ELIMINADO', N'Eliminado', 1)
) AS source(Codigo, Nombre, EsFinal)
ON target.EstadoDocumentoGraphCodigo = source.Codigo
WHEN MATCHED THEN
    UPDATE SET Nombre = source.Nombre, EsFinal = source.EsFinal, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(EstadoDocumentoGraphCodigo, Nombre, EsFinal)
    VALUES(source.Codigo, source.Nombre, source.EsFinal);
GO

MERGE cat.TipoOperacionGraph AS target
USING (VALUES
    ('FILE_UPLOAD', N'Cargar archivo de expediente', 'PUT', N'/drives/{drive-id}/items/{item-id}/content', N'Crea una sesion y carga un archivo versionado en Microsoft Graph.'),
    ('FILE_READ', N'Consultar archivo de expediente', 'GET', N'/drives/{drive-id}/items/{item-id}', N'Consulta o descarga un archivo de expediente desde Microsoft Graph.'),
    ('FOLDER_ENSURE', N'Preparar carpeta de expediente', 'POST', N'/drives/{drive-id}/items/{parent-id}/children', N'Crea o reutiliza la carpeta del expediente en Microsoft Graph.')
) AS source(Codigo, Nombre, HttpMethod, EndpointBase, Descripcion)
ON target.TipoOperacionCodigo = source.Codigo
WHEN MATCHED THEN
    UPDATE SET Nombre = source.Nombre, HttpMethod = source.HttpMethod,
               EndpointBase = source.EndpointBase, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(TipoOperacionCodigo, Nombre, HttpMethod, EndpointBase, Descripcion)
    VALUES(source.Codigo, source.Nombre, source.HttpMethod, source.EndpointBase, source.Descripcion);
GO

MERGE app.PermisoGraphRequerido AS target
USING (VALUES
    ('FILE_UPLOAD', N'Files.ReadWrite.All', 'APPLICATION', 1, 1, N'Gestion de expedientes documentales institucionales.'),
    ('FILE_UPLOAD', N'Sites.ReadWrite.All', 'APPLICATION', 1, 1, N'Gestion de bibliotecas documentales institucionales.'),
    ('FILE_READ', N'Files.Read.All', 'APPLICATION', 1, 1, N'Consulta de documentos de expedientes institucionales.')
) AS source(TipoOperacionCodigo, Permiso, TipoPermiso, EsPrivilegioMinimo, RequiereConsentimientoAdmin, Justificacion)
ON target.TipoOperacionCodigo = source.TipoOperacionCodigo AND target.Permiso = source.Permiso
WHEN MATCHED THEN
    UPDATE SET TipoPermiso = source.TipoPermiso, EsPrivilegioMinimo = source.EsPrivilegioMinimo,
               RequiereConsentimientoAdmin = source.RequiereConsentimientoAdmin,
               Justificacion = source.Justificacion, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(TipoOperacionCodigo, Permiso, TipoPermiso, EsPrivilegioMinimo, RequiereConsentimientoAdmin, Justificacion)
    VALUES(source.TipoOperacionCodigo, source.Permiso, source.TipoPermiso, source.EsPrivilegioMinimo,
           source.RequiereConsentimientoAdmin, source.Justificacion);
GO

IF OBJECT_ID(N'doc.ExpedienteGraph', N'U') IS NULL
BEGIN
    CREATE TABLE doc.ExpedienteGraph
    (
        ExpedienteGraphId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ExpedienteGraph PRIMARY KEY,
        TipoExpedienteGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        PersonaGraphRefId BIGINT NULL,
        NumeroIdentificacion VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoEstud BIGINT NULL,
        BaseOrigen NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EsquemaOrigen NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        TablaOrigen NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        OrigenId NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CodigoExpediente NVARCHAR(160) COLLATE Modern_Spanish_CI_AS NULL,
        DriveOwnerUPN NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        GraphDriveId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphFolderItemId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        RutaCarpeta NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        GraphWebUrl NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        Activo BIT NOT NULL CONSTRAINT DF_ExpedienteGraph_Activo DEFAULT 1,
        FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_ExpedienteGraph_Fecha DEFAULT SYSUTCDATETIME(),
        UsuarioCreacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaActualizacion DATETIME2 NULL,
        UsuarioActualizacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
        CONSTRAINT FK_ExpedienteGraph_Tipo FOREIGN KEY(TipoExpedienteGraphCodigo)
            REFERENCES cat.TipoExpedienteGraph(TipoExpedienteGraphCodigo),
        CONSTRAINT FK_ExpedienteGraph_Persona FOREIGN KEY(PersonaGraphRefId)
            REFERENCES core.PersonaGraphRef(PersonaGraphRefId),
        CONSTRAINT UQ_ExpedienteGraph_Origen UNIQUE
            (TipoExpedienteGraphCodigo, BaseOrigen, EsquemaOrigen, TablaOrigen, OrigenId)
    );

    CREATE INDEX IX_ExpedienteGraph_Persona
        ON doc.ExpedienteGraph(NumeroIdentificacion, TipoExpedienteGraphCodigo, Activo);
END;
GO

IF OBJECT_ID(N'doc.DocumentoGraph', N'U') IS NULL
BEGIN
    CREATE TABLE doc.DocumentoGraph
    (
        DocumentoGraphId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_DocumentoGraph PRIMARY KEY,
        ExpedienteGraphId BIGINT NOT NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        DocumentoOrigenId NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL,
        EstadoDocumentoGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreArchivo NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
        ContentType NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        TamanoBytes BIGINT NULL,
        HashSha256 VARCHAR(64) COLLATE Modern_Spanish_CI_AS NULL,
        VersionActual INT NOT NULL CONSTRAINT DF_DocumentoGraph_Version DEFAULT 1,
        GraphDriveId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphItemId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphETag NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        GraphWebUrl NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        RutaGraph NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaLimiteEdicion DATETIME2 NULL,
        Activo BIT NOT NULL CONSTRAINT DF_DocumentoGraph_Activo DEFAULT 1,
        FechaCarga DATETIME2 NOT NULL CONSTRAINT DF_DocumentoGraph_Fecha DEFAULT SYSUTCDATETIME(),
        UsuarioCarga NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaActualizacion DATETIME2 NULL,
        UsuarioActualizacion NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NULL,
        CONSTRAINT FK_DocumentoGraph_Expediente FOREIGN KEY(ExpedienteGraphId)
            REFERENCES doc.ExpedienteGraph(ExpedienteGraphId),
        CONSTRAINT FK_DocumentoGraph_Estado FOREIGN KEY(EstadoDocumentoGraphCodigo)
            REFERENCES cat.EstadoDocumentoGraph(EstadoDocumentoGraphCodigo),
        CONSTRAINT CK_DocumentoGraph_Tamano CHECK(TamanoBytes IS NULL OR TamanoBytes >= 0),
        CONSTRAINT CK_DocumentoGraph_Version CHECK(VersionActual > 0)
    );

    CREATE INDEX IX_DocumentoGraph_Expediente
        ON doc.DocumentoGraph(ExpedienteGraphId, Activo, TipoDocumentoCodigo, FechaCarga DESC);
    CREATE INDEX IX_DocumentoGraph_GraphItem
        ON doc.DocumentoGraph(GraphItemId) WHERE GraphItemId IS NOT NULL;
END;
GO

IF OBJECT_ID(N'doc.DocumentoGraphVersion', N'U') IS NULL
BEGIN
    CREATE TABLE doc.DocumentoGraphVersion
    (
        DocumentoGraphVersionId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_DocumentoGraphVersion PRIMARY KEY,
        DocumentoGraphId BIGINT NOT NULL,
        NumeroVersion INT NOT NULL,
        EstadoDocumentoGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreArchivo NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
        ContentType NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        TamanoBytes BIGINT NULL,
        HashSha256 VARCHAR(64) COLLATE Modern_Spanish_CI_AS NULL,
        GraphDriveId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphItemId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphETag NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NULL,
        GraphWebUrl NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        RutaGraph NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaCarga DATETIME2 NOT NULL CONSTRAINT DF_DocumentoGraphVersion_Fecha DEFAULT SYSUTCDATETIME(),
        UsuarioCarga NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CONSTRAINT FK_DocumentoGraphVersion_Documento FOREIGN KEY(DocumentoGraphId)
            REFERENCES doc.DocumentoGraph(DocumentoGraphId),
        CONSTRAINT FK_DocumentoGraphVersion_Estado FOREIGN KEY(EstadoDocumentoGraphCodigo)
            REFERENCES cat.EstadoDocumentoGraph(EstadoDocumentoGraphCodigo),
        CONSTRAINT UQ_DocumentoGraphVersion UNIQUE(DocumentoGraphId, NumeroVersion)
    );
END;
GO

IF OBJECT_ID(N'doc.SesionCargaGraph', N'U') IS NULL
BEGIN
    CREATE TABLE doc.SesionCargaGraph
    (
        SesionCargaGraphId UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT PK_SesionCargaGraph PRIMARY KEY,
        ExpedienteGraphId BIGINT NOT NULL,
        DocumentoGraphId BIGINT NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        EstadoDocumentoGraphCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreArchivoOriginal NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
        NombreArchivoNube NVARCHAR(520) COLLATE Modern_Spanish_CI_AS NOT NULL,
        RutaGraph NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NOT NULL,
        ContentType NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        TamanoEsperado BIGINT NOT NULL,
        UploadUrlHash VARBINARY(32) NULL,
        FechaExpiracionGraph DATETIME2 NULL,
        GraphItemId NVARCHAR(300) COLLATE Modern_Spanish_CI_AS NULL,
        GraphWebUrl NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        CorrelationId UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_SesionCargaGraph_Correlation DEFAULT NEWID(),
        UltimoError NVARCHAR(2000) COLLATE Modern_Spanish_CI_AS NULL,
        FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_SesionCargaGraph_Inicio DEFAULT SYSUTCDATETIME(),
        FechaFin DATETIME2 NULL,
        UsuarioCarga NVARCHAR(256) COLLATE Modern_Spanish_CI_AS NOT NULL,
        CONSTRAINT FK_SesionCargaGraph_Expediente FOREIGN KEY(ExpedienteGraphId)
            REFERENCES doc.ExpedienteGraph(ExpedienteGraphId),
        CONSTRAINT FK_SesionCargaGraph_Documento FOREIGN KEY(DocumentoGraphId)
            REFERENCES doc.DocumentoGraph(DocumentoGraphId),
        CONSTRAINT FK_SesionCargaGraph_Estado FOREIGN KEY(EstadoDocumentoGraphCodigo)
            REFERENCES cat.EstadoDocumentoGraph(EstadoDocumentoGraphCodigo),
        CONSTRAINT CK_SesionCargaGraph_Tamano CHECK(TamanoEsperado > 0 AND TamanoEsperado <= 1073741824)
    );

    CREATE INDEX IX_SesionCargaGraph_Expediente
        ON doc.SesionCargaGraph(ExpedienteGraphId, EstadoDocumentoGraphCodigo, FechaInicio DESC);
END;
GO

CREATE OR ALTER VIEW rpt.vw_ExpedientesDocumentalesGraph
AS
SELECT
    E.ExpedienteGraphId,
    E.TipoExpedienteGraphCodigo,
    T.Nombre AS TipoExpediente,
    E.NumeroIdentificacion,
    E.CodigoEstud,
    P.NombreCompleto,
    E.BaseOrigen,
    E.EsquemaOrigen,
    E.TablaOrigen,
    E.OrigenId,
    E.CodigoExpediente,
    E.RutaCarpeta,
    E.GraphWebUrl AS ExpedienteWebUrl,
    D.DocumentoGraphId,
    D.TipoDocumentoCodigo,
    D.DocumentoOrigenId,
    D.NombreArchivo,
    D.ContentType,
    D.TamanoBytes,
    D.VersionActual,
    D.EstadoDocumentoGraphCodigo,
    D.GraphItemId,
    D.GraphWebUrl,
    D.FechaCarga,
    D.UsuarioCarga,
    E.Activo AS ExpedienteActivo,
    D.Activo AS DocumentoActivo
FROM doc.ExpedienteGraph E
INNER JOIN cat.TipoExpedienteGraph T
    ON T.TipoExpedienteGraphCodigo = E.TipoExpedienteGraphCodigo
LEFT JOIN core.PersonaGraphRef P
    ON P.PersonaGraphRefId = E.PersonaGraphRefId
LEFT JOIN doc.DocumentoGraph D
    ON D.ExpedienteGraphId = E.ExpedienteGraphId;
GO

IF OBJECT_ID(N'rpt.vw_EstadoGraphIntegracion', N'V') IS NOT NULL
    PRINT N'Expedientes documentales Graph instalados correctamente.';
GO
