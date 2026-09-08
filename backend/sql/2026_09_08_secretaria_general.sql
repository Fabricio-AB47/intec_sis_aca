USE [master];
GO

IF DB_ID(N'INTEC_SECRETARIA_GENERAL') IS NULL
BEGIN
    CREATE DATABASE [INTEC_SECRETARIA_GENERAL] COLLATE Modern_Spanish_CI_AS;
END;
GO

USE [INTEC_SECRETARIA_GENERAL];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET ARITHABORT ON;
SET NUMERIC_ROUNDABORT OFF;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'sec') EXEC(N'CREATE SCHEMA sec AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'doc') EXEC(N'CREATE SCHEMA doc AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ofc') EXEC(N'CREATE SCHEMA ofc AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'integ') EXEC(N'CREATE SCHEMA integ AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'aud') EXEC(N'CREATE SCHEMA aud AUTHORIZATION dbo;');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo;');
GO

IF DATABASE_PRINCIPAL_ID(N'secretaria_reader') IS NULL
    CREATE ROLE secretaria_reader AUTHORIZATION dbo;
IF DATABASE_PRINCIPAL_ID(N'secretaria_operator') IS NULL
    CREATE ROLE secretaria_operator AUTHORIZATION dbo;
GO

IF OBJECT_ID(N'cat.TipoTramite', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoTramite
    (
        TipoTramiteId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoTramite PRIMARY KEY,
        Codigo varchar(50) NOT NULL CONSTRAINT UQ_TipoTramite_Codigo UNIQUE,
        Nombre nvarchar(150) NOT NULL,
        Descripcion nvarchar(500) NULL,
        Activo bit NOT NULL CONSTRAINT DF_TipoTramite_Activo DEFAULT (1),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_TipoTramite_Fecha DEFAULT (SYSUTCDATETIME())
    );
END;
GO

IF OBJECT_ID(N'cat.EstadoTramite', N'U') IS NULL
BEGIN
    CREATE TABLE cat.EstadoTramite
    (
        EstadoTramiteId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_EstadoTramite PRIMARY KEY,
        Codigo varchar(30) NOT NULL CONSTRAINT UQ_EstadoTramite_Codigo UNIQUE,
        Nombre nvarchar(100) NOT NULL,
        EsFinal bit NOT NULL CONSTRAINT DF_EstadoTramite_EsFinal DEFAULT (0),
        Orden int NOT NULL,
        Activo bit NOT NULL CONSTRAINT DF_EstadoTramite_Activo DEFAULT (1)
    );
END;
GO

IF OBJECT_ID(N'cat.TipoDocumento', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoDocumento
    (
        TipoDocumentoId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_SecretariaTipoDocumento PRIMARY KEY,
        Codigo varchar(80) NOT NULL CONSTRAINT UQ_SecretariaTipoDocumento_Codigo UNIQUE,
        Nombre nvarchar(180) NOT NULL,
        Descripcion nvarchar(500) NULL,
        Activo bit NOT NULL CONSTRAINT DF_SecretariaTipoDocumento_Activo DEFAULT (1),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_SecretariaTipoDocumento_Fecha DEFAULT (SYSUTCDATETIME())
    );
END;
GO

IF OBJECT_ID(N'cat.PlantillaRequisitoVersion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.PlantillaRequisitoVersion
    (
        PlantillaRequisitoVersionId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PlantillaRequisitoVersion PRIMARY KEY,
        TipoTramiteId int NOT NULL,
        CodigoVersion varchar(50) NOT NULL,
        Nombre nvarchar(180) NOT NULL,
        VigenteDesde date NOT NULL,
        VigenteHasta date NULL,
        Activo bit NOT NULL CONSTRAINT DF_PlantillaVersion_Activo DEFAULT (1),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_PlantillaVersion_Fecha DEFAULT (SYSUTCDATETIME()),
        UsuarioCreacion nvarchar(256) NOT NULL CONSTRAINT DF_PlantillaVersion_Usuario DEFAULT (N'MIGRACION'),
        CONSTRAINT FK_PlantillaVersion_TipoTramite FOREIGN KEY (TipoTramiteId) REFERENCES cat.TipoTramite(TipoTramiteId),
        CONSTRAINT UQ_PlantillaVersion UNIQUE (TipoTramiteId, CodigoVersion),
        CONSTRAINT CK_PlantillaVersion_Fechas CHECK (VigenteHasta IS NULL OR VigenteHasta >= VigenteDesde)
    );
END;
GO

IF OBJECT_ID(N'cat.PlantillaRequisitoDetalle', N'U') IS NULL
BEGIN
    CREATE TABLE cat.PlantillaRequisitoDetalle
    (
        PlantillaRequisitoDetalleId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PlantillaRequisitoDetalle PRIMARY KEY,
        PlantillaRequisitoVersionId int NOT NULL,
        TipoDocumentoId int NOT NULL,
        EsObligatorio bit NOT NULL CONSTRAINT DF_PlantillaDetalle_Obligatorio DEFAULT (1),
        AplicaProximo bit NOT NULL CONSTRAINT DF_PlantillaDetalle_Proximo DEFAULT (1),
        AplicaEgresado bit NOT NULL CONSTRAINT DF_PlantillaDetalle_Egresado DEFAULT (1),
        AplicaGraduado bit NOT NULL CONSTRAINT DF_PlantillaDetalle_Graduado DEFAULT (1),
        Orden int NOT NULL,
        Instruccion nvarchar(500) NULL,
        Activo bit NOT NULL CONSTRAINT DF_PlantillaDetalle_Activo DEFAULT (1),
        CONSTRAINT FK_PlantillaDetalle_Version FOREIGN KEY (PlantillaRequisitoVersionId) REFERENCES cat.PlantillaRequisitoVersion(PlantillaRequisitoVersionId),
        CONSTRAINT FK_PlantillaDetalle_TipoDocumento FOREIGN KEY (TipoDocumentoId) REFERENCES cat.TipoDocumento(TipoDocumentoId),
        CONSTRAINT UQ_PlantillaDetalle UNIQUE (PlantillaRequisitoVersionId, TipoDocumentoId),
        CONSTRAINT CK_PlantillaDetalle_Orden CHECK (Orden > 0)
    );
END;
GO

IF OBJECT_ID(N'sec.Tramite', N'U') IS NULL
BEGIN
    CREATE TABLE sec.Tramite
    (
        TramiteId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Tramite PRIMARY KEY,
        CodigoTramite varchar(60) NOT NULL CONSTRAINT UQ_Tramite_Codigo UNIQUE,
        TipoTramiteId int NOT NULL,
        EstadoTramiteId int NOT NULL,
        PlantillaRequisitoVersionId int NOT NULL,
        CodigoEstud bigint NOT NULL,
        NumeroIdentificacion varchar(20) NOT NULL,
        ApellidosNombres nvarchar(250) NOT NULL,
        CodigoCarrera nvarchar(50) NULL,
        NombreCarrera nvarchar(250) NULL,
        CodigoPeriodo nvarchar(50) NULL,
        NombrePeriodo nvarchar(250) NULL,
        TipoMatricula char(1) NOT NULL CONSTRAINT DF_Tramite_TipoMatricula DEFAULT ('R'),
        TipoHomologacion varchar(30) NULL,
        EtapaAcademica varchar(20) NOT NULL,
        MateriasRequeridas int NOT NULL CONSTRAINT DF_Tramite_MateriasRequeridas DEFAULT (24),
        MateriasAprobadas int NOT NULL CONSTRAINT DF_Tramite_MateriasAprobadas DEFAULT (0),
        PorcentajeMalla decimal(5,2) NOT NULL CONSTRAINT DF_Tramite_PorcentajeMalla DEFAULT (0),
        PromedioAprobadas decimal(5,2) NULL,
        FechaGrado date NULL,
        Origen varchar(30) NOT NULL CONSTRAINT DF_Tramite_Origen DEFAULT ('INTECBDD'),
        Activo bit NOT NULL CONSTRAINT DF_Tramite_Activo DEFAULT (1),
        FechaApertura datetime2(0) NOT NULL CONSTRAINT DF_Tramite_FechaApertura DEFAULT (SYSUTCDATETIME()),
        UsuarioApertura nvarchar(256) NOT NULL,
        FechaActualizacion datetime2(0) NULL,
        UsuarioActualizacion nvarchar(256) NULL,
        VersionFila rowversion NOT NULL,
        CONSTRAINT FK_Tramite_Tipo FOREIGN KEY (TipoTramiteId) REFERENCES cat.TipoTramite(TipoTramiteId),
        CONSTRAINT FK_Tramite_Estado FOREIGN KEY (EstadoTramiteId) REFERENCES cat.EstadoTramite(EstadoTramiteId),
        CONSTRAINT FK_Tramite_Plantilla FOREIGN KEY (PlantillaRequisitoVersionId) REFERENCES cat.PlantillaRequisitoVersion(PlantillaRequisitoVersionId),
        CONSTRAINT CK_Tramite_Etapa CHECK (EtapaAcademica IN ('PROXIMO', 'EGRESADO', 'GRADUADO')),
        CONSTRAINT CK_Tramite_TipoMatricula CHECK (TipoMatricula IN ('R', 'H')),
        CONSTRAINT CK_Tramite_TipoHomologacion CHECK
            (TipoHomologacion IS NULL OR TipoHomologacion IN ('INTERNA_ART81', 'EXTERNA_ART82', 'EXTERNA_ART83')),
        CONSTRAINT CK_Tramite_Progreso CHECK (PorcentajeMalla BETWEEN 0 AND 100),
        CONSTRAINT CK_Tramite_Materias CHECK (MateriasAprobadas >= 0 AND MateriasRequeridas > 0)
    );
    CREATE UNIQUE INDEX UX_Tramite_EstudianteTipo_Activo
        ON sec.Tramite(CodigoEstud, TipoTramiteId) WHERE Activo = 1;
    CREATE INDEX IX_Tramite_EtapaEstado
        ON sec.Tramite(EtapaAcademica, EstadoTramiteId, Activo)
        INCLUDE (CodigoEstud, NumeroIdentificacion, ApellidosNombres, PorcentajeMalla);
END;
GO

IF OBJECT_ID(N'sec.TramiteSnapshotAcademico', N'U') IS NULL
BEGIN
    CREATE TABLE sec.TramiteSnapshotAcademico
    (
        TramiteSnapshotAcademicoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_TramiteSnapshot PRIMARY KEY,
        TramiteId bigint NOT NULL,
        EtapaAcademica varchar(20) NOT NULL,
        MateriasAprobadas int NOT NULL,
        MateriasRequeridas int NOT NULL,
        PorcentajeMalla decimal(5,2) NOT NULL,
        PromedioAprobadas decimal(5,2) NULL,
        EstadoAcademico varchar(10) NULL,
        DatosJson nvarchar(max) NULL,
        FechaCaptura datetime2(0) NOT NULL CONSTRAINT DF_TramiteSnapshot_Fecha DEFAULT (SYSUTCDATETIME()),
        UsuarioCaptura nvarchar(256) NOT NULL,
        CONSTRAINT FK_TramiteSnapshot_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId),
        CONSTRAINT CK_TramiteSnapshot_Json CHECK (DatosJson IS NULL OR ISJSON(DatosJson) = 1)
    );
    CREATE INDEX IX_TramiteSnapshot_TramiteFecha ON sec.TramiteSnapshotAcademico(TramiteId, FechaCaptura DESC);
END;
GO

IF OBJECT_ID(N'sec.TramiteRequisito', N'U') IS NULL
BEGIN
    CREATE TABLE sec.TramiteRequisito
    (
        TramiteRequisitoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_TramiteRequisito PRIMARY KEY,
        TramiteId bigint NOT NULL,
        TipoDocumentoId int NOT NULL,
        EsObligatorio bit NOT NULL,
        EsAplicable bit NOT NULL CONSTRAINT DF_TramiteRequisito_Aplicable DEFAULT (1),
        Orden int NOT NULL,
        EstadoCodigo varchar(20) NOT NULL CONSTRAINT DF_TramiteRequisito_Estado DEFAULT ('FALTANTE'),
        ObservacionActual nvarchar(1000) NULL,
        FechaUltimaRevision datetime2(0) NULL,
        UsuarioUltimaRevision nvarchar(256) NULL,
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_TramiteRequisito_Fecha DEFAULT (SYSUTCDATETIME()),
        FechaActualizacion datetime2(0) NULL,
        VersionFila rowversion NOT NULL,
        CONSTRAINT FK_TramiteRequisito_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId),
        CONSTRAINT FK_TramiteRequisito_TipoDocumento FOREIGN KEY (TipoDocumentoId) REFERENCES cat.TipoDocumento(TipoDocumentoId),
        CONSTRAINT UQ_TramiteRequisito UNIQUE (TramiteId, TipoDocumentoId),
        CONSTRAINT CK_TramiteRequisito_Estado CHECK (EstadoCodigo IN ('FALTANTE', 'PRESENTE', 'EN_REVISION', 'VALIDADO', 'OBSERVADO', 'RECHAZADO', 'NO_APLICA'))
    );
    CREATE INDEX IX_TramiteRequisito_TramiteEstado ON sec.TramiteRequisito(TramiteId, EstadoCodigo, EsAplicable);
END;
GO

IF OBJECT_ID(N'doc.DocumentoPresentado', N'U') IS NULL
BEGIN
    CREATE TABLE doc.DocumentoPresentado
    (
        DocumentoPresentadoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentoPresentado PRIMARY KEY,
        TramiteRequisitoId bigint NOT NULL,
        SistemaOrigen varchar(50) NOT NULL,
        EntidadOrigen nvarchar(150) NOT NULL,
        EntidadOrigenId nvarchar(100) NOT NULL,
        DocumentoGraphId bigint NULL,
        NombreArchivo nvarchar(260) NULL,
        ContentType nvarchar(150) NULL,
        TamanoBytes bigint NULL,
        HashArchivo varchar(128) NULL,
        RutaReferencia nvarchar(1200) NULL,
        EstadoOrigen varchar(50) NULL,
        EsEvidenciaVigente bit NOT NULL CONSTRAINT DF_DocumentoPresentado_Vigente DEFAULT (1),
        FechaDocumento datetime2(0) NULL,
        FechaSincronizacion datetime2(0) NOT NULL CONSTRAINT DF_DocumentoPresentado_Sync DEFAULT (SYSUTCDATETIME()),
        UsuarioCargaOrigen nvarchar(256) NULL,
        UsuarioSincronizacion nvarchar(256) NOT NULL,
        CONSTRAINT FK_DocumentoPresentado_Requisito FOREIGN KEY (TramiteRequisitoId) REFERENCES sec.TramiteRequisito(TramiteRequisitoId),
        CONSTRAINT UQ_DocumentoPresentado_Origen UNIQUE (SistemaOrigen, EntidadOrigen, EntidadOrigenId),
        CONSTRAINT CK_DocumentoPresentado_Tamano CHECK (TamanoBytes IS NULL OR TamanoBytes >= 0)
    );
    CREATE INDEX IX_DocumentoPresentado_Requisito ON doc.DocumentoPresentado(TramiteRequisitoId, EsEvidenciaVigente, FechaSincronizacion DESC);
END;
GO

IF OBJECT_ID(N'doc.ValidacionAutomatica', N'U') IS NULL
BEGIN
    CREATE TABLE doc.ValidacionAutomatica
    (
        ValidacionAutomaticaId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ValidacionAutomatica PRIMARY KEY,
        DocumentoPresentadoId bigint NOT NULL,
        ReglaCodigo varchar(80) NOT NULL,
        ResultadoCodigo varchar(20) NOT NULL,
        Detalle nvarchar(1000) NULL,
        DatosJson nvarchar(max) NULL,
        FechaValidacion datetime2(0) NOT NULL CONSTRAINT DF_ValidacionAutomatica_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_ValidacionAutomatica_Documento FOREIGN KEY (DocumentoPresentadoId) REFERENCES doc.DocumentoPresentado(DocumentoPresentadoId),
        CONSTRAINT CK_ValidacionAutomatica_Resultado CHECK (ResultadoCodigo IN ('CUMPLE', 'NO_CUMPLE', 'ADVERTENCIA')),
        CONSTRAINT CK_ValidacionAutomatica_Json CHECK (DatosJson IS NULL OR ISJSON(DatosJson) = 1)
    );
END;
GO

IF OBJECT_ID(N'doc.RevisionHumana', N'U') IS NULL
BEGIN
    CREATE TABLE doc.RevisionHumana
    (
        RevisionHumanaId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_RevisionHumana PRIMARY KEY,
        TramiteRequisitoId bigint NOT NULL,
        DocumentoPresentadoId bigint NULL,
        EstadoAnterior varchar(20) NOT NULL,
        EstadoNuevo varchar(20) NOT NULL,
        Observacion nvarchar(1000) NULL,
        UsuarioRevision nvarchar(256) NOT NULL,
        RolRevision nvarchar(100) NOT NULL,
        FechaRevision datetime2(0) NOT NULL CONSTRAINT DF_RevisionHumana_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_RevisionHumana_Requisito FOREIGN KEY (TramiteRequisitoId) REFERENCES sec.TramiteRequisito(TramiteRequisitoId),
        CONSTRAINT FK_RevisionHumana_Documento FOREIGN KEY (DocumentoPresentadoId) REFERENCES doc.DocumentoPresentado(DocumentoPresentadoId),
        CONSTRAINT CK_RevisionHumana_Estado CHECK (EstadoNuevo IN ('FALTANTE', 'PRESENTE', 'EN_REVISION', 'VALIDADO', 'OBSERVADO', 'RECHAZADO'))
    );
    CREATE INDEX IX_RevisionHumana_RequisitoFecha ON doc.RevisionHumana(TramiteRequisitoId, FechaRevision DESC);
END;
GO

IF OBJECT_ID(N'sec.ObservacionTramite', N'U') IS NULL
BEGIN
    CREATE TABLE sec.ObservacionTramite
    (
        ObservacionTramiteId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ObservacionTramite PRIMARY KEY,
        TramiteId bigint NOT NULL,
        TramiteRequisitoId bigint NULL,
        TipoObservacion varchar(30) NOT NULL,
        Observacion nvarchar(1000) NOT NULL,
        EsSistema bit NOT NULL CONSTRAINT DF_ObservacionTramite_Sistema DEFAULT (0),
        Resuelta bit NOT NULL CONSTRAINT DF_ObservacionTramite_Resuelta DEFAULT (0),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_ObservacionTramite_Fecha DEFAULT (SYSUTCDATETIME()),
        UsuarioCreacion nvarchar(256) NOT NULL,
        FechaResolucion datetime2(0) NULL,
        UsuarioResolucion nvarchar(256) NULL,
        CONSTRAINT FK_ObservacionTramite_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId),
        CONSTRAINT FK_ObservacionTramite_Requisito FOREIGN KEY (TramiteRequisitoId) REFERENCES sec.TramiteRequisito(TramiteRequisitoId),
        CONSTRAINT CK_ObservacionTramite_Tipo CHECK (TipoObservacion IN ('FALTANTE', 'REVISION', 'GENERAL'))
    );
    CREATE INDEX IX_ObservacionTramite_Activa ON sec.ObservacionTramite(TramiteId, Resuelta, TramiteRequisitoId);
END;
GO

IF OBJECT_ID(N'sec.AsignacionTramite', N'U') IS NULL
BEGIN
    CREATE TABLE sec.AsignacionTramite
    (
        AsignacionTramiteId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AsignacionTramite PRIMARY KEY,
        TramiteId bigint NOT NULL,
        UsuarioAsignado nvarchar(256) NOT NULL,
        RolAsignado nvarchar(100) NOT NULL,
        Activo bit NOT NULL CONSTRAINT DF_AsignacionTramite_Activo DEFAULT (1),
        FechaAsignacion datetime2(0) NOT NULL CONSTRAINT DF_AsignacionTramite_Fecha DEFAULT (SYSUTCDATETIME()),
        UsuarioAsignacion nvarchar(256) NOT NULL,
        FechaFin datetime2(0) NULL,
        CONSTRAINT FK_AsignacionTramite_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId)
    );
    CREATE UNIQUE INDEX UX_AsignacionTramite_Activa ON sec.AsignacionTramite(TramiteId, UsuarioAsignado) WHERE Activo = 1;
END;
GO

IF OBJECT_ID(N'sec.DecisionTramite', N'U') IS NULL
BEGIN
    CREATE TABLE sec.DecisionTramite
    (
        DecisionTramiteId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DecisionTramite PRIMARY KEY,
        TramiteId bigint NOT NULL,
        DecisionCodigo varchar(20) NOT NULL,
        Observacion nvarchar(1000) NULL,
        UsuarioDecision nvarchar(256) NOT NULL,
        RolDecision nvarchar(100) NOT NULL,
        FechaDecision datetime2(0) NOT NULL CONSTRAINT DF_DecisionTramite_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_DecisionTramite_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId),
        CONSTRAINT CK_DecisionTramite_Codigo CHECK (DecisionCodigo IN ('APROBADO', 'RECHAZADO', 'ARCHIVADO', 'REABIERTO'))
    );
END;
GO

IF OBJECT_ID(N'ofc.SecuenciaDocumento', N'U') IS NULL
BEGIN
    CREATE TABLE ofc.SecuenciaDocumento
    (
        Anio int NOT NULL,
        TipoDocumento varchar(50) NOT NULL,
        UltimoNumero bigint NOT NULL CONSTRAINT DF_SecuenciaDocumento_Numero DEFAULT (0),
        FechaActualizacion datetime2(0) NOT NULL CONSTRAINT DF_SecuenciaDocumento_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_SecuenciaDocumento PRIMARY KEY (Anio, TipoDocumento)
    );
END;
GO

IF OBJECT_ID(N'ofc.DocumentoEmitido', N'U') IS NULL
BEGIN
    CREATE TABLE ofc.DocumentoEmitido
    (
        DocumentoEmitidoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentoEmitido PRIMARY KEY,
        TramiteId bigint NOT NULL,
        TipoDocumento varchar(50) NOT NULL,
        NumeroDocumento varchar(80) NOT NULL CONSTRAINT UQ_DocumentoEmitido_Numero UNIQUE,
        RutaReferencia nvarchar(1200) NULL,
        HashArchivo varchar(128) NULL,
        FechaEmision datetime2(0) NOT NULL CONSTRAINT DF_DocumentoEmitido_Fecha DEFAULT (SYSUTCDATETIME()),
        UsuarioEmision nvarchar(256) NOT NULL,
        Anulado bit NOT NULL CONSTRAINT DF_DocumentoEmitido_Anulado DEFAULT (0),
        CONSTRAINT FK_DocumentoEmitido_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId)
    );
END;
GO

IF OBJECT_ID(N'integ.OutboxEvento', N'U') IS NULL
BEGIN
    CREATE TABLE integ.OutboxEvento
    (
        OutboxEventoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_OutboxEvento PRIMARY KEY,
        TipoEvento varchar(100) NOT NULL,
        AgregadoTipo varchar(80) NOT NULL,
        AgregadoId nvarchar(100) NOT NULL,
        PayloadJson nvarchar(max) NOT NULL,
        EstadoCodigo varchar(20) NOT NULL CONSTRAINT DF_OutboxEvento_Estado DEFAULT ('PENDIENTE'),
        Intentos int NOT NULL CONSTRAINT DF_OutboxEvento_Intentos DEFAULT (0),
        FechaDisponible datetime2(0) NOT NULL CONSTRAINT DF_OutboxEvento_Disponible DEFAULT (SYSUTCDATETIME()),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_OutboxEvento_Fecha DEFAULT (SYSUTCDATETIME()),
        FechaProcesamiento datetime2(0) NULL,
        UltimoError nvarchar(2000) NULL,
        CONSTRAINT CK_OutboxEvento_Payload CHECK (ISJSON(PayloadJson) = 1),
        CONSTRAINT CK_OutboxEvento_Estado CHECK (EstadoCodigo IN ('PENDIENTE', 'PROCESANDO', 'COMPLETADO', 'ERROR'))
    );
    CREATE INDEX IX_OutboxEvento_Pendiente ON integ.OutboxEvento(EstadoCodigo, FechaDisponible) INCLUDE (TipoEvento, AgregadoId);
END;
GO

IF OBJECT_ID(N'integ.ErrorOperacion', N'U') IS NULL
BEGIN
    CREATE TABLE integ.ErrorOperacion
    (
        ErrorOperacionId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ErrorOperacion PRIMARY KEY,
        CodigoSeguimiento varchar(128) NOT NULL,
        Operacion nvarchar(150) NOT NULL,
        SistemaOrigen varchar(50) NULL,
        Detalle nvarchar(2000) NOT NULL,
        Resuelto bit NOT NULL CONSTRAINT DF_ErrorOperacion_Resuelto DEFAULT (0),
        FechaCreacion datetime2(0) NOT NULL CONSTRAINT DF_ErrorOperacion_Fecha DEFAULT (SYSUTCDATETIME()),
        FechaResolucion datetime2(0) NULL,
        CONSTRAINT UQ_ErrorOperacion_Seguimiento UNIQUE (CodigoSeguimiento)
    );
END;
GO

IF OBJECT_ID(N'aud.EventoSecretaria', N'U') IS NULL
BEGIN
    CREATE TABLE aud.EventoSecretaria
    (
        EventoSecretariaId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_EventoSecretaria PRIMARY KEY,
        TramiteId bigint NULL,
        Entidad nvarchar(100) NOT NULL,
        EntidadId nvarchar(100) NULL,
        Accion varchar(50) NOT NULL,
        DatosJson nvarchar(max) NULL,
        Usuario nvarchar(256) NOT NULL,
        Rol nvarchar(100) NOT NULL,
        RequestId varchar(128) NULL,
        DireccionIp varchar(64) NULL,
        FechaEvento datetime2(0) NOT NULL CONSTRAINT DF_EventoSecretaria_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_EventoSecretaria_Tramite FOREIGN KEY (TramiteId) REFERENCES sec.Tramite(TramiteId),
        CONSTRAINT CK_EventoSecretaria_Json CHECK (DatosJson IS NULL OR ISJSON(DatosJson) = 1)
    );
    CREATE INDEX IX_EventoSecretaria_TramiteFecha ON aud.EventoSecretaria(TramiteId, FechaEvento DESC);
END;
GO

IF OBJECT_ID(N'aud.AccesoDocumento', N'U') IS NULL
BEGIN
    CREATE TABLE aud.AccesoDocumento
    (
        AccesoDocumentoId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AccesoDocumento PRIMARY KEY,
        DocumentoPresentadoId bigint NOT NULL,
        Accion varchar(30) NOT NULL,
        Usuario nvarchar(256) NOT NULL,
        Rol nvarchar(100) NOT NULL,
        FechaAcceso datetime2(0) NOT NULL CONSTRAINT DF_AccesoDocumento_Fecha DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_AccesoDocumento_Documento FOREIGN KEY (DocumentoPresentadoId) REFERENCES doc.DocumentoPresentado(DocumentoPresentadoId)
    );
END;
GO

IF COL_LENGTH(N'sec.Tramite', N'TipoMatricula') IS NULL
    ALTER TABLE sec.Tramite
        ADD TipoMatricula char(1) NOT NULL
            CONSTRAINT DF_Tramite_TipoMatricula DEFAULT ('R') WITH VALUES;
GO

UPDATE sec.Tramite
   SET TipoMatricula = 'H'
WHERE TipoMatricula <> 'H'
  AND
  (
      UPPER(ISNULL(NombrePeriodo, N'')) LIKE N'%HOMO%'
      OR UPPER(ISNULL(CodigoPeriodo, N'')) LIKE N'H%'
  );
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sec.Tramite')
      AND name = N'CK_Tramite_TipoMatricula'
)
    ALTER TABLE sec.Tramite WITH CHECK ADD CONSTRAINT CK_Tramite_TipoMatricula CHECK (TipoMatricula IN ('R', 'H'));
GO

IF COL_LENGTH(N'sec.Tramite', N'TipoHomologacion') IS NULL
    ALTER TABLE sec.Tramite ADD TipoHomologacion varchar(30) NULL;
GO

UPDATE sec.Tramite SET TipoHomologacion = NULL WHERE TipoMatricula = 'R' AND TipoHomologacion IS NOT NULL;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sec.Tramite')
      AND name = N'CK_Tramite_TipoHomologacion'
)
    ALTER TABLE sec.Tramite WITH CHECK ADD CONSTRAINT CK_Tramite_TipoHomologacion CHECK
        (TipoHomologacion IS NULL OR TipoHomologacion IN ('INTERNA_ART81', 'EXTERNA_ART82', 'EXTERNA_ART83'));
GO

IF COL_LENGTH(N'doc.DocumentoPresentado', N'UsuarioCargaOrigen') IS NULL
    ALTER TABLE doc.DocumentoPresentado ADD UsuarioCargaOrigen nvarchar(256) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.Tramite') AND name = N'UX_Tramite_EstudianteTipo_Activo')
    CREATE UNIQUE INDEX UX_Tramite_EstudianteTipo_Activo ON sec.Tramite(CodigoEstud, TipoTramiteId) WHERE Activo = 1;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.Tramite') AND name = N'IX_Tramite_EtapaEstado')
    CREATE INDEX IX_Tramite_EtapaEstado ON sec.Tramite(EtapaAcademica, EstadoTramiteId, Activo)
        INCLUDE (CodigoEstud, NumeroIdentificacion, ApellidosNombres, PorcentajeMalla);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.TramiteSnapshotAcademico') AND name = N'IX_TramiteSnapshot_TramiteFecha')
    CREATE INDEX IX_TramiteSnapshot_TramiteFecha ON sec.TramiteSnapshotAcademico(TramiteId, FechaCaptura DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.TramiteRequisito') AND name = N'IX_TramiteRequisito_TramiteEstado')
    CREATE INDEX IX_TramiteRequisito_TramiteEstado ON sec.TramiteRequisito(TramiteId, EstadoCodigo, EsAplicable);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'doc.DocumentoPresentado') AND name = N'IX_DocumentoPresentado_Requisito')
    CREATE INDEX IX_DocumentoPresentado_Requisito ON doc.DocumentoPresentado(TramiteRequisitoId, EsEvidenciaVigente, FechaSincronizacion DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'doc.RevisionHumana') AND name = N'IX_RevisionHumana_RequisitoFecha')
    CREATE INDEX IX_RevisionHumana_RequisitoFecha ON doc.RevisionHumana(TramiteRequisitoId, FechaRevision DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.ObservacionTramite') AND name = N'IX_ObservacionTramite_Activa')
    CREATE INDEX IX_ObservacionTramite_Activa ON sec.ObservacionTramite(TramiteId, Resuelta, TramiteRequisitoId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'sec.AsignacionTramite') AND name = N'UX_AsignacionTramite_Activa')
    CREATE UNIQUE INDEX UX_AsignacionTramite_Activa ON sec.AsignacionTramite(TramiteId, UsuarioAsignado) WHERE Activo = 1;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'integ.OutboxEvento') AND name = N'IX_OutboxEvento_Pendiente')
    CREATE INDEX IX_OutboxEvento_Pendiente ON integ.OutboxEvento(EstadoCodigo, FechaDisponible) INCLUDE (TipoEvento, AgregadoId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'aud.EventoSecretaria') AND name = N'IX_EventoSecretaria_TramiteFecha')
    CREATE INDEX IX_EventoSecretaria_TramiteFecha ON aud.EventoSecretaria(TramiteId, FechaEvento DESC);
GO

MERGE cat.TipoTramite AS target
USING (VALUES
    ('REVISION_EXPEDIENTE_GRADO', N'Revisión de expediente para grado', N'Validación documental de estudiantes próximos a graduarse, egresados o graduados.')
) AS source(Codigo, Nombre, Descripcion)
ON target.Codigo = source.Codigo
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, Descripcion) VALUES (source.Codigo, source.Nombre, source.Descripcion);
GO

MERGE cat.EstadoTramite AS target
USING (VALUES
    ('RECIBIDO', N'Recibido', 0, 10),
    ('ASIGNADO', N'Asignado', 0, 20),
    ('EN_VALIDACION', N'En validación', 0, 30),
    ('OBSERVADO', N'Observado', 0, 40),
    ('APROBADO', N'Aprobado', 1, 50),
    ('RECHAZADO', N'Rechazado', 1, 60),
    ('ARCHIVADO', N'Archivado', 1, 70),
    ('ANULADO', N'Anulado', 1, 80)
) AS source(Codigo, Nombre, EsFinal, Orden)
ON target.Codigo = source.Codigo
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, EsFinal = source.EsFinal, Orden = source.Orden, Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, EsFinal, Orden) VALUES (source.Codigo, source.Nombre, source.EsFinal, source.Orden);
GO

MERGE cat.TipoDocumento AS target
USING (VALUES
    ('CEDULA', N'Cédula de identidad', N'Documento de identidad vigente.'),
    ('TITULO_BACHILLER', N'Título de bachiller', N'Requisito académico de ingreso.'),
    ('CERTIFICADO_NO_ADEUDAMIENTO', N'Certificado financiero de no adeudamiento', N'Certificación vigente emitida por el área financiera.'),
    ('RECORD_ACADEMICO_FIRMADO', N'Récord académico certificado', N'Récord académico completo, certificado y firmado por los responsables.'),
    ('CERTIFICADO_PRACTICAS', N'Documentación de prácticas laborales', N'Evidencia de cumplimiento de prácticas laborales o preprofesionales.'),
    ('CERTIFICADO_VINCULACION', N'Documentación de vinculación con la sociedad', N'Evidencia de cumplimiento de vinculación con la sociedad.'),
    ('DOCUMENTO_INGLES', N'Certificado o evidencia de Inglés', N'Documentación que acredita el cumplimiento del requisito de Inglés.'),
    ('DOCUMENTO_CERTIFICACIONES', N'Documento de certificaciones', N'Certificaciones presentadas para sustentar la homologación.'),
    ('DOCUMENTOS_UNIVERSIDAD_ORIGEN', N'Documentos de la universidad de origen', N'Documentación académica oficial emitida por la institución de origen.'),
    ('DOCUMENTO_HOMOLOGACION', N'Documento de homologación', N'Resolución o documento institucional que formaliza la homologación.'),
    ('HOMOLOGACION_ARTICULO_81', N'Respaldo del artículo 81', N'Documento aplicable a la homologación interna.'),
    ('HOMOLOGACION_ARTICULO_82', N'Respaldo del artículo 82', N'Documento aplicable a estudios externos con menos de 10 años.'),
    ('HOMOLOGACION_ARTICULO_83', N'Respaldo del artículo 83', N'Documento aplicable a estudios externos con más de 10 años.')
) AS source(Codigo, Nombre, Descripcion)
ON target.Codigo = source.Codigo
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, Descripcion) VALUES (source.Codigo, source.Nombre, source.Descripcion);
GO

DECLARE @TipoTramiteId int = (SELECT TipoTramiteId FROM cat.TipoTramite WHERE Codigo = 'REVISION_EXPEDIENTE_GRADO');
IF NOT EXISTS
(
    SELECT 1 FROM cat.PlantillaRequisitoVersion
    WHERE TipoTramiteId = @TipoTramiteId AND CodigoVersion = 'EXPEDIENTE_GRADO_V1'
)
BEGIN
    INSERT cat.PlantillaRequisitoVersion
        (TipoTramiteId, CodigoVersion, Nombre, VigenteDesde, Activo, UsuarioCreacion)
    VALUES
        (@TipoTramiteId, 'EXPEDIENTE_GRADO_V1', N'Expediente documental de grado', '2026-01-01', 1, N'MIGRACION_2026_09_08');
END;

DECLARE @VersionId int =
(
    SELECT PlantillaRequisitoVersionId
    FROM cat.PlantillaRequisitoVersion
    WHERE TipoTramiteId = @TipoTramiteId AND CodigoVersion = 'EXPEDIENTE_GRADO_V1'
);

MERGE cat.PlantillaRequisitoDetalle AS target
USING
(
    SELECT @VersionId, td.TipoDocumentoId, data.EsObligatorio, data.AplicaProximo,
           data.AplicaEgresado, data.AplicaGraduado, data.Orden, data.Instruccion
    FROM (VALUES
        ('CEDULA', 1, 1, 1, 1, 10, N'Presentar una copia legible y vigente.'),
        ('TITULO_BACHILLER', 1, 1, 1, 1, 20, N'Validar el título de bachiller registrado.'),
        ('CERTIFICADO_NO_ADEUDAMIENTO', 1, 1, 1, 1, 30, N'Presentar el certificado vigente de no adeudamiento emitido por el área financiera.'),
        ('RECORD_ACADEMICO_FIRMADO', 1, 1, 1, 1, 40, N'Presentar el récord académico completo, certificado y firmado por los responsables.'),
        ('CERTIFICADO_PRACTICAS', 1, 1, 1, 1, 50, N'Validar la documentación de cumplimiento de prácticas laborales o preprofesionales.'),
        ('CERTIFICADO_VINCULACION', 1, 1, 1, 1, 60, N'Validar la documentación de cumplimiento de vinculación con la sociedad.'),
        ('DOCUMENTO_INGLES', 1, 1, 1, 1, 70, N'Validar el certificado o la evidencia oficial de cumplimiento de Inglés.'),
        ('DOCUMENTO_CERTIFICACIONES', 1, 1, 1, 1, 80, N'Presentar las certificaciones que sustentan la homologación.'),
        ('DOCUMENTOS_UNIVERSIDAD_ORIGEN', 1, 1, 1, 1, 90, N'Presentar los documentos académicos certificados por la universidad de origen.'),
        ('DOCUMENTO_HOMOLOGACION', 1, 1, 1, 1, 100, N'Presentar la resolución o el documento institucional de homologación.'),
        ('HOMOLOGACION_ARTICULO_81', 1, 1, 1, 1, 110, N'Presentar el respaldo aplicable a la homologación interna conforme al artículo 81.'),
        ('HOMOLOGACION_ARTICULO_82', 1, 1, 1, 1, 120, N'Presentar el respaldo del artículo 82 para estudios con menos de 10 años.'),
        ('HOMOLOGACION_ARTICULO_83', 1, 1, 1, 1, 130, N'Presentar el respaldo del artículo 83 para estudios con más de 10 años.')
    ) AS data(Codigo, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
    INNER JOIN cat.TipoDocumento td ON td.Codigo = data.Codigo
) AS source(PlantillaRequisitoVersionId, TipoDocumentoId, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
ON target.PlantillaRequisitoVersionId = source.PlantillaRequisitoVersionId
AND target.TipoDocumentoId = source.TipoDocumentoId
WHEN MATCHED THEN UPDATE SET
    EsObligatorio = source.EsObligatorio,
    AplicaProximo = source.AplicaProximo,
    AplicaEgresado = source.AplicaEgresado,
    AplicaGraduado = source.AplicaGraduado,
    Orden = source.Orden,
    Instruccion = source.Instruccion,
    Activo = 1
WHEN NOT MATCHED THEN INSERT
    (PlantillaRequisitoVersionId, TipoDocumentoId, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
VALUES
    (source.PlantillaRequisitoVersionId, source.TipoDocumentoId, source.EsObligatorio, source.AplicaProximo, source.AplicaEgresado, source.AplicaGraduado, source.Orden, source.Instruccion);

UPDATE detail
   SET Activo = 0
FROM cat.PlantillaRequisitoDetalle detail
INNER JOIN cat.TipoDocumento document_type ON document_type.TipoDocumentoId = detail.TipoDocumentoId
WHERE detail.PlantillaRequisitoVersionId = @VersionId
  AND document_type.Codigo IN ('RECORD_ACADEMICO', 'ACTA_GRADO', 'TITULO_INTEC', 'TITULO_SENESCYT');
GO

CREATE OR ALTER VIEW rpt.vw_ResumenTramiteDocumental
AS
    SELECT
        t.TramiteId,
        t.CodigoTramite,
        tt.Codigo AS TipoTramiteCodigo,
        et.Codigo AS EstadoTramiteCodigo,
        et.Nombre AS EstadoTramite,
        t.CodigoEstud,
        t.NumeroIdentificacion,
        t.ApellidosNombres,
        t.CodigoCarrera,
        t.NombreCarrera,
        t.CodigoPeriodo,
        t.NombrePeriodo,
        t.TipoMatricula,
        t.TipoHomologacion,
        t.EtapaAcademica,
        t.MateriasAprobadas,
        t.MateriasRequeridas,
        t.PorcentajeMalla,
        t.PromedioAprobadas,
        t.FechaGrado,
        SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 THEN 1 ELSE 0 END) AS RequisitosObligatorios,
        SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 AND tr.EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END) AS RequisitosValidados,
        SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 AND tr.EstadoCodigo = 'FALTANTE' THEN 1 ELSE 0 END) AS RequisitosFaltantes,
        SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EstadoCodigo IN ('OBSERVADO', 'RECHAZADO') THEN 1 ELSE 0 END) AS RequisitosObservados,
        CAST(CASE
            WHEN SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 THEN 1 ELSE 0 END) = 0 THEN 0
            ELSE 100.0 * SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 AND tr.EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END)
                / SUM(CASE WHEN tr.EsAplicable = 1 AND tr.EsObligatorio = 1 THEN 1 ELSE 0 END)
        END AS decimal(5,2)) AS PorcentajeDocumental,
        t.FechaApertura,
        t.FechaActualizacion
    FROM sec.Tramite t
    INNER JOIN cat.TipoTramite tt ON tt.TipoTramiteId = t.TipoTramiteId
    INNER JOIN cat.EstadoTramite et ON et.EstadoTramiteId = t.EstadoTramiteId
    LEFT JOIN sec.TramiteRequisito tr ON tr.TramiteId = t.TramiteId
    WHERE t.Activo = 1
    GROUP BY
        t.TramiteId, t.CodigoTramite, tt.Codigo, et.Codigo, et.Nombre,
        t.CodigoEstud, t.NumeroIdentificacion, t.ApellidosNombres,
        t.CodigoCarrera, t.NombreCarrera, t.CodigoPeriodo, t.NombrePeriodo,
        t.TipoMatricula, t.TipoHomologacion, t.EtapaAcademica, t.MateriasAprobadas, t.MateriasRequeridas,
        t.PorcentajeMalla, t.PromedioAprobadas, t.FechaGrado,
        t.FechaApertura, t.FechaActualizacion;
GO

GRANT SELECT ON SCHEMA::cat TO secretaria_reader;
GRANT SELECT ON SCHEMA::sec TO secretaria_reader;
GRANT SELECT ON SCHEMA::doc TO secretaria_reader;
GRANT SELECT ON SCHEMA::ofc TO secretaria_reader;
GRANT SELECT ON SCHEMA::rpt TO secretaria_reader;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.database_role_members membership
    WHERE membership.role_principal_id = DATABASE_PRINCIPAL_ID(N'secretaria_reader')
      AND membership.member_principal_id = DATABASE_PRINCIPAL_ID(N'secretaria_operator')
)
    ALTER ROLE secretaria_reader ADD MEMBER secretaria_operator;
GRANT SELECT, INSERT, UPDATE ON SCHEMA::sec TO secretaria_operator;
GRANT SELECT, INSERT, UPDATE ON SCHEMA::doc TO secretaria_operator;
GRANT SELECT, INSERT, UPDATE ON SCHEMA::ofc TO secretaria_operator;
GRANT SELECT, INSERT, UPDATE ON SCHEMA::integ TO secretaria_operator;
GRANT SELECT, INSERT ON SCHEMA::aud TO secretaria_operator;
DENY DELETE ON SCHEMA::sec TO secretaria_operator;
DENY DELETE ON SCHEMA::doc TO secretaria_operator;
DENY DELETE ON SCHEMA::aud TO secretaria_operator;
GO

IF DB_ID(N'INTEC_GRAPH_INTEGRACION') IS NOT NULL
BEGIN
    EXEC(N'
        USE [INTEC_GRAPH_INTEGRACION];
        MERGE cat.TipoExpedienteGraph AS target
        USING (VALUES
            (''SECRETARIA'', N''Secretaría General'', N''Documentos revisados por Secretaría General'', 1)
        ) AS source(TipoExpedienteGraphCodigo, Nombre, Descripcion, Activo)
        ON target.TipoExpedienteGraphCodigo = source.TipoExpedienteGraphCodigo
        WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = source.Activo
        WHEN NOT MATCHED THEN INSERT (TipoExpedienteGraphCodigo, Nombre, Descripcion, Activo)
            VALUES (source.TipoExpedienteGraphCodigo, source.Nombre, source.Descripcion, source.Activo);
    ');
END;
GO
