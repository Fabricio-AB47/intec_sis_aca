/*
Complemento 05 - Documentos, actas y portal de titulos
Base destino: TITULACION_INTEC
Idempotente: agrega metadatos documentales, historial, numeracion configurable
y procedimientos complementarios para actas/titulos.
*/

USE TITULACION_INTEC;
GO

IF SCHEMA_ID(N'doc') IS NULL EXEC(N'CREATE SCHEMA doc');
IF SCHEMA_ID(N'tit') IS NULL EXEC(N'CREATE SCHEMA tit');
IF SCHEMA_ID(N'cat') IS NULL EXEC(N'CREATE SCHEMA cat');
GO

IF OBJECT_ID(N'cat.TipoDocumentoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoDocumentoTitulacion
    (
        TipoDocumentoTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoDocumentoTitulacion_05 PRIMARY KEY,
        Codigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        Nombre NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        AplicaMecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        EsObligatorio BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Obligatorio_05 DEFAULT 0,
        BloqueaActa BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_BloqueaActa_05 DEFAULT 0,
        Orden INT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Orden_05 DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Activo_05 DEFAULT 1
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
    ALTER TABLE cat.TipoDocumentoTitulacion ADD BloqueaActa BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_BloqueaActa_Compat_05 DEFAULT 0;
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

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TipoDocumentoTitulacion_Codigo_Compat_05' AND object_id = OBJECT_ID(N'cat.TipoDocumentoTitulacion'))
    CREATE UNIQUE INDEX UX_TipoDocumentoTitulacion_Codigo_Compat_05 ON cat.TipoDocumentoTitulacion(Codigo) WHERE Codigo IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_TipoDocumentoTitulacion_TipoCodigo_Compat_05' AND object_id = OBJECT_ID(N'cat.TipoDocumentoTitulacion'))
    CREATE UNIQUE INDEX UX_TipoDocumentoTitulacion_TipoCodigo_Compat_05 ON cat.TipoDocumentoTitulacion(TipoDocumentoCodigo) WHERE TipoDocumentoCodigo IS NOT NULL;
GO

IF COL_LENGTH(N'doc.DocumentoTitulacion', N'CodigoRegistroSenescyt') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD CodigoRegistroSenescyt NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'FechaRegistroSenescyt') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD FechaRegistroSenescyt DATE NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'NumeroTituloIntec') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD NumeroTituloIntec NVARCHAR(100) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'FechaEmisionTitulo') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD FechaEmisionTitulo DATE NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'CodigoVerificacionQr') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD CodigoVerificacionQr NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'Observacion') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD Observacion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'UsuarioValidacion') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD UsuarioValidacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'FechaValidacion') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD FechaValidacion DATETIME2 NULL;
IF COL_LENGTH(N'doc.DocumentoTitulacion', N'Activo') IS NULL
    ALTER TABLE doc.DocumentoTitulacion ADD Activo BIT NOT NULL CONSTRAINT DF_DocumentoTitulacion_Activo_05 DEFAULT 1;
GO

IF COL_LENGTH(N'tit.ActaGrado', N'NombreInstitucion') IS NULL
    ALTER TABLE tit.ActaGrado ADD NombreInstitucion NVARCHAR(250) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'TextoVariableActa') IS NULL
    ALTER TABLE tit.ActaGrado ADD TextoVariableActa NVARCHAR(MAX) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'HashPdf') IS NULL
    ALTER TABLE tit.ActaGrado ADD HashPdf VARBINARY(64) NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'Activo') IS NULL
    ALTER TABLE tit.ActaGrado ADD Activo BIT NOT NULL CONSTRAINT DF_ActaGrado_Activo_05 DEFAULT 1;
IF COL_LENGTH(N'tit.ActaGrado', N'MotivoAnulacion') IS NULL
    ALTER TABLE tit.ActaGrado ADD MotivoAnulacion NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'UsuarioAnulacion') IS NULL
    ALTER TABLE tit.ActaGrado ADD UsuarioAnulacion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'tit.ActaGrado', N'FechaAnulacion') IS NULL
    ALTER TABLE tit.ActaGrado ADD FechaAnulacion DATETIME2 NULL;
GO

IF OBJECT_ID(N'doc.DocumentoTitulacionHistorial', N'U') IS NULL
BEGIN
    CREATE TABLE doc.DocumentoTitulacionHistorial
    (
        HistorialId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentoTitulacionHistorial PRIMARY KEY,
        DocumentoTitulacionId BIGINT NOT NULL,
        ExpedienteId BIGINT NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Version INT NULL,
        EstadoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NULL,
        Accion VARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        Observacion NVARCHAR(1500) COLLATE Modern_Spanish_CI_AS NULL,
        NombreArchivo NVARCHAR(260) COLLATE Modern_Spanish_CI_AS NULL,
        RutaNube NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        UrlPublica NVARCHAR(1000) COLLATE Modern_Spanish_CI_AS NULL,
        UsuarioAccion NVARCHAR(128) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaAccion DATETIME2 NOT NULL CONSTRAINT DF_DocHistorial_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF OBJECT_ID(N'tit.SecuenciaActaGrado', N'U') IS NULL
BEGIN
    CREATE TABLE tit.SecuenciaActaGrado
    (
        SecuenciaActaGradoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_SecuenciaActaGrado PRIMARY KEY,
        EscuelaCodigo NVARCHAR(50) COLLATE Modern_Spanish_CI_AS NOT NULL,
        MecanismoCodigo VARCHAR(30) COLLATE Modern_Spanish_CI_AS NOT NULL,
        FechaActa DATE NOT NULL,
        Secuencial INT NOT NULL,
        CONSTRAINT UQ_SecuenciaActaGrado UNIQUE(EscuelaCodigo, MecanismoCodigo, FechaActa)
    );
END;
GO

MERGE cat.TipoDocumentoTitulacion AS T
USING (VALUES
    ('APTITUD_LEGAL', N'Aptitud legal', NULL, 1, 1),
    ('PROGRAMACION_EXAMEN', N'Programacion de examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 2),
    ('EVIDENCIA_EXAMEN_COMPLEXIVO', N'Evidencia de examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 3),
    ('RUBRICA_EVALUADORES', N'Rubricas de evaluadores', 'EXAMEN_COMPLEXIVO', 1, 4),
    ('ACTA_EXAMEN_COMPLEXIVO', N'Acta de examen complexivo', 'EXAMEN_COMPLEXIVO', 0, 5),
    ('TRABAJO_FINAL_GRADO', N'Trabajo final de grado', 'DEFENSA_GRADO', 1, 2),
    ('PROGRAMACION_DEFENSA', N'Programacion de defensa', 'DEFENSA_GRADO', 1, 3),
    ('ACTA_DEFENSA', N'Acta de defensa', 'DEFENSA_GRADO', 1, 4),
    ('RUBRICA_TRABAJO_ESCRITO', N'Rubrica de trabajo escrito', 'DEFENSA_GRADO', 1, 5),
    ('RUBRICA_DEFENSA_ORAL', N'Rubrica de defensa oral', 'DEFENSA_GRADO', 1, 6),
    ('ACTA_GRADO', N'Acta de grado', NULL, 0, 90),
    ('ACTA_GRADO_FIRMADA', N'Acta de grado firmada', NULL, 0, 91),
    ('TITULO_REGISTRO_SENESCYT', N'Titulo registrado SENESCYT', NULL, 0, 100),
    ('TITULO_INTEC', N'Titulo INTEC', NULL, 0, 101)
) AS S(Codigo, Nombre, AplicaMecanismoCodigo, EsObligatorio, Orden)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET
    Codigo = S.Codigo,
    TipoDocumentoCodigo = S.Codigo,
    Nombre = S.Nombre,
    AplicaMecanismoCodigo = S.AplicaMecanismoCodigo,
    MecanismoCodigo = S.AplicaMecanismoCodigo,
    EsObligatorio = S.EsObligatorio,
    BloqueaActa = S.EsObligatorio,
    Orden = S.Orden,
    Activo = 1
WHEN NOT MATCHED THEN
    INSERT(Codigo, TipoDocumentoCodigo, Nombre, AplicaMecanismoCodigo, MecanismoCodigo, EsObligatorio, BloqueaActa, Orden)
    VALUES(S.Codigo, S.Codigo, S.Nombre, S.AplicaMecanismoCodigo, S.AplicaMecanismoCodigo, S.EsObligatorio, S.EsObligatorio, S.Orden);
GO

CREATE OR ALTER PROCEDURE tit.sp_GenerarNumeroActaGrado
    @ExpedienteId BIGINT,
    @FechaActa DATE,
    @EscuelaCodigo NVARCHAR(50) = NULL,
    @NumeroActa NVARCHAR(100) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @MecanismoCodigo VARCHAR(30);
    SELECT
        @MecanismoCodigo = COALESCE(E.MecanismoTitulacionId, 'SIN_MECANISMO'),
        @EscuelaCodigo = COALESCE(NULLIF(@EscuelaCodigo, N''), NULLIF(E.CodigoCarrera, N''), N'GENERAL')
    FROM tit.ExpedienteTitulacion E
    WHERE E.ExpedienteId = @ExpedienteId;

    IF @MecanismoCodigo IS NULL THROW 59801, 'No existe expediente para generar numero de acta.', 1;

    MERGE tit.SecuenciaActaGrado AS T
    USING (SELECT @EscuelaCodigo AS EscuelaCodigo, @MecanismoCodigo AS MecanismoCodigo, @FechaActa AS FechaActa) AS S
    ON T.EscuelaCodigo = S.EscuelaCodigo AND T.MecanismoCodigo = S.MecanismoCodigo AND T.FechaActa = S.FechaActa
    WHEN MATCHED THEN UPDATE SET Secuencial = T.Secuencial + 1
    WHEN NOT MATCHED THEN INSERT(EscuelaCodigo, MecanismoCodigo, FechaActa, Secuencial) VALUES(S.EscuelaCodigo, S.MecanismoCodigo, S.FechaActa, 1);

    DECLARE @Secuencial INT = (
        SELECT Secuencial
        FROM tit.SecuenciaActaGrado
        WHERE EscuelaCodigo = @EscuelaCodigo AND MecanismoCodigo = @MecanismoCodigo AND FechaActa = @FechaActa
    );

    SET @NumeroActa = CONCAT(N'INTEC-VGA-', @EscuelaCodigo, N'-', CASE WHEN @MecanismoCodigo = 'EXAMEN_COMPLEXIVO' THEN N'Q' ELSE N'D' END, N'-A-', FORMAT(@FechaActa, 'yyyyMMdd'), N'-', FORMAT(@Secuencial, '00'));
END;
GO

CREATE OR ALTER VIEW rpt.vw_TitulosPortal
AS
SELECT
    D.DocumentoTitulacionId AS DocumentoId,
    D.ExpedienteId,
    D.GrupoTitulacionId,
    D.NumeroIdentificacion,
    A.NombresEstudiante,
    A.Carrera,
    A.NumeroActa,
    A.NumeroActaGrado,
    D.TipoDocumentoCodigo,
    D.NombreArchivo,
    D.RutaNube,
    D.UrlPublica,
    D.HashArchivo,
    D.Version,
    D.EstadoCodigo,
    D.CodigoRegistroSenescyt,
    D.FechaRegistroSenescyt,
    D.NumeroTituloIntec,
    D.FechaEmisionTitulo,
    D.CodigoVerificacionQr,
    D.Observacion,
    D.FechaCarga,
    D.UsuarioCarga,
    D.FechaValidacion,
    D.UsuarioValidacion
FROM doc.DocumentoTitulacion D
LEFT JOIN tit.ActaGrado A
    ON A.ExpedienteId = D.ExpedienteId
WHERE D.TipoDocumentoCodigo IN ('TITULO_REGISTRO_SENESCYT', 'TITULO_INTEC')
  AND ISNULL(D.Activo, 1) = 1;
GO

CREATE OR ALTER PROCEDURE doc.sp_RegistrarHistorialDocumento
    @DocumentoTitulacionId BIGINT,
    @Accion VARCHAR(50),
    @Observacion NVARCHAR(1500) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO doc.DocumentoTitulacionHistorial
    (
        DocumentoTitulacionId, ExpedienteId, TipoDocumentoCodigo, Version, EstadoCodigo, Accion,
        Observacion, NombreArchivo, RutaNube, UrlPublica, UsuarioAccion
    )
    SELECT
        D.DocumentoTitulacionId, D.ExpedienteId, D.TipoDocumentoCodigo, D.Version, D.EstadoCodigo, @Accion,
        COALESCE(@Observacion, D.Observacion), D.NombreArchivo, D.RutaNube, D.UrlPublica, COALESCE(@Usuario, SYSTEM_USER)
    FROM doc.DocumentoTitulacion D
    WHERE D.DocumentoTitulacionId = @DocumentoTitulacionId;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_CargarTituloRegistradoV2
    @ExpedienteId BIGINT,
    @NumeroIdentificacion NVARCHAR(20) = NULL,
    @NombreArchivo NVARCHAR(260),
    @RutaNube NVARCHAR(1000) = NULL,
    @UrlPublica NVARCHAR(1000) = NULL,
    @HashArchivo VARBINARY(64) = NULL,
    @ContentType NVARCHAR(150) = NULL,
    @CodigoRegistroSenescyt NVARCHAR(100),
    @FechaRegistroSenescyt DATE,
    @Observacion NVARCHAR(1500) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId AND ISNULL(Activo, 1) = 1)
        THROW 59820, 'No se puede cargar titulo registrado sin acta de grado activa.', 1;

    DECLARE @Version INT = ISNULL((
        SELECT MAX(Version)
        FROM doc.DocumentoTitulacion
        WHERE ExpedienteId = @ExpedienteId AND TipoDocumentoCodigo = 'TITULO_REGISTRO_SENESCYT'
    ), 0) + 1;

    INSERT INTO doc.DocumentoTitulacion
    (
        ExpedienteId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica,
        HashArchivo, ContentType, Version, EstadoCodigo, CodigoRegistroSenescyt, FechaRegistroSenescyt,
        Observacion, UsuarioCarga
    )
    VALUES
    (
        @ExpedienteId, @NumeroIdentificacion, 'TITULO_REGISTRO_SENESCYT', @NombreArchivo, @RutaNube, @UrlPublica,
        @HashArchivo, @ContentType, @Version, 'CARGADO', @CodigoRegistroSenescyt, @FechaRegistroSenescyt,
        @Observacion, COALESCE(@Usuario, SYSTEM_USER)
    );

    DECLARE @DocumentoId BIGINT = SCOPE_IDENTITY();
    EXEC doc.sp_RegistrarHistorialDocumento @DocumentoTitulacionId = @DocumentoId, @Accion = 'CARGA', @Usuario = @Usuario;

    UPDATE tit.ExpedienteTitulacion
       SET EstadoExpediente = 'TITULO_REGISTRADO',
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;

    SELECT * FROM rpt.vw_TitulosPortal WHERE DocumentoId = @DocumentoId;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_CargarTituloIntecV2
    @ExpedienteId BIGINT,
    @NumeroIdentificacion NVARCHAR(20) = NULL,
    @NombreArchivo NVARCHAR(260),
    @RutaNube NVARCHAR(1000) = NULL,
    @UrlPublica NVARCHAR(1000) = NULL,
    @HashArchivo VARBINARY(64) = NULL,
    @ContentType NVARCHAR(150) = NULL,
    @NumeroTituloIntec NVARCHAR(100),
    @FechaEmisionTitulo DATE,
    @CodigoVerificacionQr NVARCHAR(250) = NULL,
    @Observacion NVARCHAR(1500) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM tit.ActaGrado WHERE ExpedienteId = @ExpedienteId AND ISNULL(Activo, 1) = 1)
        THROW 59830, 'No se puede cargar titulo INTEC sin acta de grado activa.', 1;

    DECLARE @Version INT = ISNULL((
        SELECT MAX(Version)
        FROM doc.DocumentoTitulacion
        WHERE ExpedienteId = @ExpedienteId AND TipoDocumentoCodigo = 'TITULO_INTEC'
    ), 0) + 1;

    INSERT INTO doc.DocumentoTitulacion
    (
        ExpedienteId, NumeroIdentificacion, TipoDocumentoCodigo, NombreArchivo, RutaNube, UrlPublica,
        HashArchivo, ContentType, Version, EstadoCodigo, NumeroTituloIntec, FechaEmisionTitulo,
        CodigoVerificacionQr, Observacion, UsuarioCarga
    )
    VALUES
    (
        @ExpedienteId, @NumeroIdentificacion, 'TITULO_INTEC', @NombreArchivo, @RutaNube, @UrlPublica,
        @HashArchivo, @ContentType, @Version, 'CARGADO', @NumeroTituloIntec, @FechaEmisionTitulo,
        @CodigoVerificacionQr, @Observacion, COALESCE(@Usuario, SYSTEM_USER)
    );

    DECLARE @DocumentoId BIGINT = SCOPE_IDENTITY();
    EXEC doc.sp_RegistrarHistorialDocumento @DocumentoTitulacionId = @DocumentoId, @Accion = 'CARGA', @Usuario = @Usuario;

    UPDATE tit.ExpedienteTitulacion
       SET EstadoExpediente = 'TITULO_INTEC_CARGADO',
           FechaActualizacion = SYSDATETIME(),
           UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
     WHERE ExpedienteId = @ExpedienteId;

    SELECT * FROM rpt.vw_TitulosPortal WHERE DocumentoId = @DocumentoId;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_ValidarDocumentoTitulacion
    @DocumentoTitulacionId BIGINT,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE doc.DocumentoTitulacion
       SET EstadoCodigo = 'VALIDADO',
           UsuarioValidacion = COALESCE(@Usuario, SYSTEM_USER),
           FechaValidacion = SYSDATETIME()
     WHERE DocumentoTitulacionId = @DocumentoTitulacionId;

    EXEC doc.sp_RegistrarHistorialDocumento @DocumentoTitulacionId = @DocumentoTitulacionId, @Accion = 'VALIDACION', @Usuario = @Usuario;
END;
GO

CREATE OR ALTER PROCEDURE doc.sp_ObservarDocumentoTitulacion
    @DocumentoTitulacionId BIGINT,
    @Observacion NVARCHAR(1500),
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE doc.DocumentoTitulacion
       SET EstadoCodigo = 'OBSERVADO',
           Observacion = @Observacion,
           UsuarioValidacion = COALESCE(@Usuario, SYSTEM_USER),
           FechaValidacion = SYSDATETIME()
     WHERE DocumentoTitulacionId = @DocumentoTitulacionId;

    EXEC doc.sp_RegistrarHistorialDocumento @DocumentoTitulacionId = @DocumentoTitulacionId, @Accion = 'OBSERVACION', @Observacion = @Observacion, @Usuario = @Usuario;
END;
GO

CREATE OR ALTER PROCEDURE tit.sp_AnularActaGrado
    @ActaGradoId BIGINT,
    @Motivo NVARCHAR(1000),
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE tit.ActaGrado
       SET EstadoCodigo = 'ANULADO',
           Activo = 0,
           MotivoAnulacion = @Motivo,
           UsuarioAnulacion = COALESCE(@Usuario, SYSTEM_USER),
           FechaAnulacion = SYSDATETIME()
     WHERE ActaGradoId = @ActaGradoId;
END;
GO

CREATE OR ALTER VIEW rpt.vw_DiagnosticoDocumentosActasTitulos
AS
SELECT 'COLUMN' AS Tipo, 'doc.DocumentoTitulacion.CodigoRegistroSenescyt' AS Nombre, CASE WHEN COL_LENGTH(N'doc.DocumentoTitulacion', N'CodigoRegistroSenescyt') IS NULL THEN 'FALTA' ELSE 'OK' END AS Estado
UNION ALL SELECT 'COLUMN', 'doc.DocumentoTitulacion.NumeroTituloIntec', CASE WHEN COL_LENGTH(N'doc.DocumentoTitulacion', N'NumeroTituloIntec') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'COLUMN', 'tit.ActaGrado.TextoVariableActa', CASE WHEN COL_LENGTH(N'tit.ActaGrado', N'TextoVariableActa') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'TABLE', 'doc.DocumentoTitulacionHistorial', CASE WHEN OBJECT_ID(N'doc.DocumentoTitulacionHistorial', N'U') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'TABLE', 'tit.SecuenciaActaGrado', CASE WHEN OBJECT_ID(N'tit.SecuenciaActaGrado', N'U') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'VIEW', 'rpt.vw_TitulosPortal', CASE WHEN OBJECT_ID(N'rpt.vw_TitulosPortal', N'V') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'PROC', 'doc.sp_CargarTituloRegistradoV2', CASE WHEN OBJECT_ID(N'doc.sp_CargarTituloRegistradoV2', N'P') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'PROC', 'doc.sp_CargarTituloIntecV2', CASE WHEN OBJECT_ID(N'doc.sp_CargarTituloIntecV2', N'P') IS NULL THEN 'FALTA' ELSE 'OK' END
UNION ALL SELECT 'PROC', 'tit.sp_AnularActaGrado', CASE WHEN OBJECT_ID(N'tit.sp_AnularActaGrado', N'P') IS NULL THEN 'FALTA' ELSE 'OK' END;
GO

SELECT * FROM rpt.vw_DiagnosticoDocumentosActasTitulos;
GO
