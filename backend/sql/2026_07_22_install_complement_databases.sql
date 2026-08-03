/*
    Instalacion idempotente de las bases complementarias consumidas por INTEC SIS ACA.
    Destino esperado: el servidor configurado por DB_HOST1 (servidor complementario).
    La carga inicial de referencias se ejecuta despues con sync_complement_references.py,
    que toma INTECBDD principal como fuente autoritativa.
*/
SET NOCOUNT ON;
GO

USE master;
GO

IF DB_ID(N'INTEC_EXPEDIENTE_ESTUDIANTIL') IS NULL CREATE DATABASE INTEC_EXPEDIENTE_ESTUDIANTIL;
IF DB_ID(N'INTEC_FINANZAS_INSTITUCIONAL') IS NULL CREATE DATABASE INTEC_FINANZAS_INSTITUCIONAL;
IF DB_ID(N'INTEC_GRAPH_INTEGRACION') IS NULL CREATE DATABASE INTEC_GRAPH_INTEGRACION;
IF DB_ID(N'INTEC_INTEGRACION_CONTROL') IS NULL CREATE DATABASE INTEC_INTEGRACION_CONTROL;
GO

/* ======================== EXPEDIENTE ESTUDIANTIL ======================== */
USE INTEC_EXPEDIENTE_ESTUDIANTIL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'core') EXEC(N'CREATE SCHEMA core AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'adm') EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'exp') EXEC(N'CREATE SCHEMA exp AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'doc') EXEC(N'CREATE SCHEMA doc AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'cron') EXEC(N'CREATE SCHEMA cron AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'integ') EXEC(N'CREATE SCHEMA integ AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'etl') EXEC(N'CREATE SCHEMA etl AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'core.Persona', N'U') IS NULL
CREATE TABLE core.Persona (
    PersonaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Exp_Persona PRIMARY KEY,
    NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT UQ_Exp_Persona_Documento UNIQUE,
    CodigoEstud BIGINT NULL,
    ApellidosNombres NVARCHAR(250) NULL,
    CorreoPersonal NVARCHAR(250) NULL,
    Telefono NVARCHAR(50) NULL,
    Celular NVARCHAR(50) NULL,
    FuenteUltimaActualizacion VARCHAR(80) NULL,
    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_Exp_Persona_Creacion DEFAULT SYSDATETIME(),
    FechaActualizacion DATETIME2 NULL,
    Activo BIT NOT NULL CONSTRAINT DF_Exp_Persona_Activo DEFAULT 1
);
GO

IF OBJECT_ID(N'cat.OrigenExpediente', N'U') IS NULL
CREATE TABLE cat.OrigenExpediente (
    OrigenExpedienteId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OrigenExpediente PRIMARY KEY,
    Codigo VARCHAR(50) NOT NULL CONSTRAINT UQ_OrigenExpediente_Codigo UNIQUE,
    Nombre NVARCHAR(150) NOT NULL,
    Activo BIT NOT NULL CONSTRAINT DF_OrigenExpediente_Activo DEFAULT 1
);

IF OBJECT_ID(N'cat.TipoExpediente', N'U') IS NULL
CREATE TABLE cat.TipoExpediente (
    TipoExpedienteId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoExpediente PRIMARY KEY,
    Codigo VARCHAR(50) NOT NULL CONSTRAINT UQ_TipoExpediente_Codigo UNIQUE,
    Nombre NVARCHAR(150) NOT NULL,
    Activo BIT NOT NULL CONSTRAINT DF_TipoExpediente_Activo DEFAULT 1
);

IF OBJECT_ID(N'cat.EstadoExpediente', N'U') IS NULL
CREATE TABLE cat.EstadoExpediente (
    EstadoExpedienteId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EstadoExpediente PRIMARY KEY,
    Codigo VARCHAR(50) NOT NULL CONSTRAINT UQ_EstadoExpediente_Codigo UNIQUE,
    Nombre NVARCHAR(150) NOT NULL,
    Activo BIT NOT NULL CONSTRAINT DF_EstadoExpediente_Activo DEFAULT 1
);
GO

MERGE cat.OrigenExpediente AS t USING (VALUES ('PREINSCRIPCION',N'Preinscripcion'),('MATRICULA',N'Matricula')) s(Codigo,Nombre)
ON t.Codigo=s.Codigo WHEN MATCHED THEN UPDATE SET Nombre=s.Nombre,Activo=1
WHEN NOT MATCHED THEN INSERT(Codigo,Nombre) VALUES(s.Codigo,s.Nombre);
MERGE cat.TipoExpediente AS t USING (VALUES ('REGULAR',N'Expediente regular')) s(Codigo,Nombre)
ON t.Codigo=s.Codigo WHEN MATCHED THEN UPDATE SET Nombre=s.Nombre,Activo=1
WHEN NOT MATCHED THEN INSERT(Codigo,Nombre) VALUES(s.Codigo,s.Nombre);
MERGE cat.EstadoExpediente AS t USING (VALUES ('DOCUMENTOS_PENDIENTES',N'Documentos pendientes'),('COMPLETO',N'Completo'),('CERRADO',N'Cerrado')) s(Codigo,Nombre)
ON t.Codigo=s.Codigo WHEN MATCHED THEN UPDATE SET Nombre=s.Nombre,Activo=1
WHEN NOT MATCHED THEN INSERT(Codigo,Nombre) VALUES(s.Codigo,s.Nombre);
GO

IF OBJECT_ID(N'adm.InscripcionReferencia', N'U') IS NULL
CREATE TABLE adm.InscripcionReferencia (
    InscripcionRefId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_InscripcionReferencia PRIMARY KEY,
    OrigenExpedienteId INT NOT NULL,
    PersonaId BIGINT NOT NULL,
    OrigenTabla NVARCHAR(128) NOT NULL,
    OrigenId NVARCHAR(100) NOT NULL,
    TipoOferta VARCHAR(30) NULL,
    CodigoEstud BIGINT NULL,
    NumeroIdentificacion VARCHAR(30) NOT NULL,
    ApellidosNombres NVARCHAR(250) NULL,
    Correo NVARCHAR(250) NULL,
    Telefono NVARCHAR(50) NULL,
    CodigoCarrera VARCHAR(50) NULL,
    CodigoPeriodo VARCHAR(50) NULL,
    FechaInscripcion DATETIME2 NULL,
    EstadoOrigen NVARCHAR(80) NULL,
    UrlCedula NVARCHAR(1000) NULL,
    UrlTituloBachiller NVARCHAR(1000) NULL,
    UrlComprobantePago NVARCHAR(1000) NULL,
    UrlConvenioPago NVARCHAR(1000) NULL,
    MetadataJson NVARCHAR(MAX) NULL,
    FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_InscripcionRef_Sync DEFAULT SYSDATETIME(),
    CONSTRAINT FK_InscripcionRef_Origen FOREIGN KEY(OrigenExpedienteId) REFERENCES cat.OrigenExpediente(OrigenExpedienteId),
    CONSTRAINT FK_InscripcionRef_Persona FOREIGN KEY(PersonaId) REFERENCES core.Persona(PersonaId),
    CONSTRAINT UQ_InscripcionRef_Origen UNIQUE(OrigenExpedienteId,OrigenId)
);
GO

IF OBJECT_ID(N'exp.ExpedienteEstudiantil', N'U') IS NULL
CREATE TABLE exp.ExpedienteEstudiantil (
    ExpedienteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ExpedienteEstudiantil PRIMARY KEY,
    TipoExpedienteId INT NOT NULL,
    EstadoExpedienteId INT NOT NULL,
    PersonaId BIGINT NOT NULL,
    InscripcionRefId BIGINT NULL,
    CodigoEstud BIGINT NULL,
    NumeroIdentificacion VARCHAR(30) NOT NULL,
    CodigoCarrera VARCHAR(50) NULL,
    CodigoPeriodo VARCHAR(50) NULL,
    TipoOferta VARCHAR(30) NULL,
    TieneBeca BIT NOT NULL CONSTRAINT DF_Expediente_Beca DEFAULT 0,
    TieneComprobantePago BIT NOT NULL CONSTRAINT DF_Expediente_Pago DEFAULT 0,
    UsuarioApertura NVARCHAR(128) NULL,
    FechaApertura DATETIME2 NOT NULL CONSTRAINT DF_Expediente_Apertura DEFAULT SYSDATETIME(),
    FechaActualizacion DATETIME2 NULL,
    UsuarioActualizacion NVARCHAR(128) NULL,
    Activo BIT NOT NULL CONSTRAINT DF_Expediente_Activo DEFAULT 1,
    CONSTRAINT FK_Expediente_Tipo FOREIGN KEY(TipoExpedienteId) REFERENCES cat.TipoExpediente(TipoExpedienteId),
    CONSTRAINT FK_Expediente_Estado FOREIGN KEY(EstadoExpedienteId) REFERENCES cat.EstadoExpediente(EstadoExpedienteId),
    CONSTRAINT FK_Expediente_Persona FOREIGN KEY(PersonaId) REFERENCES core.Persona(PersonaId),
    CONSTRAINT FK_Expediente_Inscripcion FOREIGN KEY(InscripcionRefId) REFERENCES adm.InscripcionReferencia(InscripcionRefId)
);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'exp.ExpedienteEstudiantil') AND name=N'UX_Expediente_Inscripcion_Activo')
    CREATE UNIQUE INDEX UX_Expediente_Inscripcion_Activo ON exp.ExpedienteEstudiantil(InscripcionRefId) WHERE InscripcionRefId IS NOT NULL AND Activo=1;
GO

IF OBJECT_ID(N'doc.DocumentoExpediente', N'U') IS NULL
CREATE TABLE doc.DocumentoExpediente (
    DocumentoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentoExpediente PRIMARY KEY,
    ExpedienteId BIGINT NOT NULL,
    TipoDocumentoCodigo VARCHAR(80) NOT NULL,
    NombreArchivo NVARCHAR(260) NOT NULL,
    RutaArchivo NVARCHAR(1000) NULL,
    UrlArchivo NVARCHAR(1000) NULL,
    HashArchivo VARCHAR(128) NULL,
    ContentType VARCHAR(150) NULL,
    EstadoCodigo VARCHAR(50) NOT NULL CONSTRAINT DF_Documento_Estado DEFAULT 'CARGADO',
    MetadataJson NVARCHAR(MAX) NULL,
    UsuarioCarga NVARCHAR(128) NULL,
    FechaCarga DATETIME2 NOT NULL CONSTRAINT DF_Documento_Carga DEFAULT SYSDATETIME(),
    Activo BIT NOT NULL CONSTRAINT DF_Documento_Activo DEFAULT 1,
    CONSTRAINT FK_Documento_Expediente FOREIGN KEY(ExpedienteId) REFERENCES exp.ExpedienteEstudiantil(ExpedienteId)
);

IF OBJECT_ID(N'cron.CronogramaAcademico', N'U') IS NULL
CREATE TABLE cron.CronogramaAcademico (
    CronogramaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CronogramaAcademico PRIMARY KEY,
    CodigoPeriodo VARCHAR(50) NOT NULL,
    CodigoActividad VARCHAR(80) NOT NULL,
    NombreActividad NVARCHAR(250) NOT NULL,
    FechaInicio DATETIME2 NOT NULL,
    FechaFin DATETIME2 NULL,
    Activo BIT NOT NULL CONSTRAINT DF_Cronograma_Activo DEFAULT 1,
    CONSTRAINT UQ_Cronograma_PeriodoActividad UNIQUE(CodigoPeriodo,CodigoActividad)
);
GO

IF OBJECT_ID(N'integ.EjecucionSincronizacion', N'U') IS NULL
CREATE TABLE integ.EjecucionSincronizacion (
    EjecucionSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Exp_EjecucionSync PRIMARY KEY,
    ProcesoCodigo VARCHAR(100) NOT NULL, EstadoCodigo VARCHAR(30) NOT NULL,
    FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_Exp_Sync_Inicio DEFAULT SYSDATETIME(), FechaFin DATETIME2 NULL,
    FilasProcesadas BIGINT NULL, UsuarioEjecucion NVARCHAR(128) NULL, Mensaje NVARCHAR(2000) NULL
);
IF OBJECT_ID(N'integ.ErrorSincronizacion', N'U') IS NULL
CREATE TABLE integ.ErrorSincronizacion (
    ErrorSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Exp_ErrorSync PRIMARY KEY,
    EjecucionSincronizacionId BIGINT NULL, NumeroError INT NULL, ProcedimientoError NVARCHAR(256) NULL,
    LineaError INT NULL, MensajeError NVARCHAR(4000) NOT NULL,
    FechaError DATETIME2 NOT NULL CONSTRAINT DF_Exp_ErrorSync_Fecha DEFAULT SYSDATETIME(),
    CONSTRAINT FK_Exp_ErrorSync_Ejecucion FOREIGN KEY(EjecucionSincronizacionId) REFERENCES integ.EjecucionSincronizacion(EjecucionSincronizacionId)
);
GO

CREATE OR ALTER VIEW rpt.vw_EstadoDocumentalIntegracion AS
SELECT e.ExpedienteId,e.NumeroIdentificacion,e.CodigoEstud,e.CodigoCarrera,e.CodigoPeriodo,
       ee.Codigo AS EstadoCodigo,COUNT(d.DocumentoId) AS TotalDocumentos,
       MAX(d.FechaCarga) AS UltimoDocumento
FROM exp.ExpedienteEstudiantil e
JOIN cat.EstadoExpediente ee ON ee.EstadoExpedienteId=e.EstadoExpedienteId
LEFT JOIN doc.DocumentoExpediente d ON d.ExpedienteId=e.ExpedienteId AND d.Activo=1
WHERE e.Activo=1
GROUP BY e.ExpedienteId,e.NumeroIdentificacion,e.CodigoEstud,e.CodigoCarrera,e.CodigoPeriodo,ee.Codigo;
GO
CREATE OR ALTER VIEW rpt.vw_ExpedienteIdentidadIntegracion AS
SELECT p.PersonaId,p.NumeroIdentificacion,p.CodigoEstud,p.ApellidosNombres,p.CorreoPersonal,p.Telefono,p.Celular,
       e.ExpedienteId,e.CodigoCarrera,e.CodigoPeriodo,ee.Codigo AS EstadoExpediente
FROM core.Persona p
LEFT JOIN exp.ExpedienteEstudiantil e ON e.PersonaId=p.PersonaId AND e.Activo=1
LEFT JOIN cat.EstadoExpediente ee ON ee.EstadoExpedienteId=e.EstadoExpedienteId
WHERE p.Activo=1;
GO
CREATE OR ALTER PROCEDURE etl.sp_SincronizarModuloCompleto @Usuario NVARCHAR(128)=N'SQL'
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO integ.EjecucionSincronizacion(ProcesoCodigo,EstadoCodigo,UsuarioEjecucion,FechaFin,FilasProcesadas,Mensaje)
    VALUES('MODULO_COMPLETO','COMPLETADO',@Usuario,SYSDATETIME(),0,N'Use sync_complement_references.py para reconciliar con la fuente principal.');
END;
GO

/* ============================= FINANZAS ================================ */
USE INTEC_FINANZAS_INSTITUCIONAL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'core') EXEC(N'CREATE SCHEMA core AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'cat') EXEC(N'CREATE SCHEMA cat AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'adm') EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'fin') EXEC(N'CREATE SCHEMA fin AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'bec') EXEC(N'CREATE SCHEMA bec AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'pag') EXEC(N'CREATE SCHEMA pag AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'fac') EXEC(N'CREATE SCHEMA fac AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'integ') EXEC(N'CREATE SCHEMA integ AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'core.Estudiante', N'U') IS NULL
CREATE TABLE core.Estudiante (
    EstudianteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Fin_Estudiante PRIMARY KEY,
    CodigoEstud DECIMAL(18,0) NULL,
    NumeroIdentificacion NVARCHAR(30) NOT NULL CONSTRAINT UQ_Fin_Estudiante_Documento UNIQUE,
    NombreCompleto NVARCHAR(250) NOT NULL, Correo NVARCHAR(250) NULL,
    Telefono NVARCHAR(50) NULL, Movil NVARCHAR(50) NULL, FuenteOrigen VARCHAR(80) NULL,
    FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_Fin_Estudiante_Sync DEFAULT SYSDATETIME(),
    Activo BIT NOT NULL CONSTRAINT DF_Fin_Estudiante_Activo DEFAULT 1
);
IF OBJECT_ID(N'core.Carrera', N'U') IS NULL
CREATE TABLE core.Carrera (CodigoCarrera VARCHAR(50) NOT NULL CONSTRAINT PK_Fin_Carrera PRIMARY KEY,NombreCarrera NVARCHAR(250) NOT NULL,Activo BIT NOT NULL CONSTRAINT DF_Fin_Carrera_Activo DEFAULT 1);
IF OBJECT_ID(N'core.Periodo', N'U') IS NULL
CREATE TABLE core.Periodo (CodigoPeriodo VARCHAR(50) NOT NULL CONSTRAINT PK_Fin_Periodo PRIMARY KEY,NombrePeriodo NVARCHAR(250) NOT NULL,Activo BIT NOT NULL CONSTRAINT DF_Fin_Periodo_Activo DEFAULT 1);
GO

IF OBJECT_ID(N'cat.TipoBeca', N'U') IS NULL
CREATE TABLE cat.TipoBeca (TipoBecaId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoBeca PRIMARY KEY,Codigo VARCHAR(50) NOT NULL CONSTRAINT UQ_TipoBeca_Codigo UNIQUE,Nombre NVARCHAR(150) NOT NULL,Activo BIT NOT NULL CONSTRAINT DF_TipoBeca_Activo DEFAULT 1);
IF OBJECT_ID(N'cat.EstadoBeca', N'U') IS NULL
CREATE TABLE cat.EstadoBeca (EstadoBecaId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EstadoBeca PRIMARY KEY,Codigo VARCHAR(50) NOT NULL CONSTRAINT UQ_EstadoBeca_Codigo UNIQUE,Nombre NVARCHAR(150) NOT NULL,Activo BIT NOT NULL CONSTRAINT DF_EstadoBeca_Activo DEFAULT 1);
GO
MERGE cat.TipoBeca t USING (VALUES ('INSTITUCIONAL',N'Institucional'),('SOCIOECONOMICA',N'Socioeconomica'),('MERITO',N'Merito'),('CONVENIO',N'Convenio'),('DEPORTIVA',N'Deportiva')) s(Codigo,Nombre)
ON t.Codigo=s.Codigo WHEN MATCHED THEN UPDATE SET Nombre=s.Nombre,Activo=1 WHEN NOT MATCHED THEN INSERT(Codigo,Nombre) VALUES(s.Codigo,s.Nombre);
MERGE cat.EstadoBeca t USING (VALUES ('SOLICITADA',N'Solicitada'),('APROBADA',N'Aprobada'),('RECHAZADA',N'Rechazada'),('ANULADA',N'Anulada')) s(Codigo,Nombre)
ON t.Codigo=s.Codigo WHEN MATCHED THEN UPDATE SET Nombre=s.Nombre,Activo=1 WHEN NOT MATCHED THEN INSERT(Codigo,Nombre) VALUES(s.Codigo,s.Nombre);
GO

IF OBJECT_ID(N'adm.PreinscripcionFinanciera', N'U') IS NOT NULL
   AND COL_LENGTH(N'adm.PreinscripcionFinanciera',N'Cedula') IS NULL
BEGIN
    IF EXISTS (SELECT 1 FROM adm.PreinscripcionFinanciera)
        THROW 51000,N'No se puede reemplazar adm.PreinscripcionFinanciera: contiene datos.',1;
    DROP TABLE adm.PreinscripcionFinanciera;
END;

IF OBJECT_ID(N'adm.PreinscripcionFinanciera', N'U') IS NULL
CREATE TABLE adm.PreinscripcionFinanciera (
    PreinscripcionFinancieraId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PreinscripcionFinanciera PRIMARY KEY,
    Codestu DECIMAL(18,0) NULL,Cedula NVARCHAR(30) NOT NULL,ApellidosNombre NVARCHAR(250) NOT NULL,
    CodigoPeriodo VARCHAR(50) NOT NULL,CodigoCarrera VARCHAR(50) NOT NULL,CodigoModalidad VARCHAR(50) NULL,CodigoJornada VARCHAR(50) NULL,
    Correo NVARCHAR(250) NULL,Telefono NVARCHAR(50) NULL,UsuarioOrigen NVARCHAR(128) NULL,CodigoAsesor NVARCHAR(80) NULL,
    ObservacionIngreso NVARCHAR(1000) NULL,Prematricula BIT NOT NULL CONSTRAINT DF_PreinsFin_Prematricula DEFAULT 0,
    FechaIngreso DATETIME2 NOT NULL CONSTRAINT DF_PreinsFin_Ingreso DEFAULT SYSDATETIME(),
    FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_PreinsFin_Sync DEFAULT SYSDATETIME(),
    CONSTRAINT UQ_PreinscripcionFinanciera UNIQUE(Cedula,CodigoPeriodo,CodigoCarrera)
);
GO

IF OBJECT_ID(N'fin.CuentaEstudiante', N'U') IS NULL
CREATE TABLE fin.CuentaEstudiante (
    CuentaEstudianteId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CuentaEstudiante PRIMARY KEY,
    EstudianteId BIGINT NOT NULL,CodigoCarrera VARCHAR(50) NULL,CodigoPeriodo VARCHAR(50) NULL,
    Saldo DECIMAL(18,2) NOT NULL CONSTRAINT DF_Cuenta_Saldo DEFAULT 0,
    UsuarioApertura NVARCHAR(128) NULL,FechaApertura DATETIME2 NOT NULL CONSTRAINT DF_Cuenta_Apertura DEFAULT SYSDATETIME(),
    Activo BIT NOT NULL CONSTRAINT DF_Cuenta_Activo DEFAULT 1,
    CONSTRAINT FK_Cuenta_Estudiante FOREIGN KEY(EstudianteId) REFERENCES core.Estudiante(EstudianteId)
);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'fin.CuentaEstudiante') AND name=N'UX_Cuenta_Estudiante_Periodo')
    CREATE UNIQUE INDEX UX_Cuenta_Estudiante_Periodo ON fin.CuentaEstudiante(EstudianteId,CodigoCarrera,CodigoPeriodo) WHERE Activo=1;
GO

IF OBJECT_ID(N'bec.BecaEstudiante', N'U') IS NULL
CREATE TABLE bec.BecaEstudiante (
    BecaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BecaEstudiante PRIMARY KEY,
    EstudianteId BIGINT NOT NULL,CuentaEstudianteId BIGINT NOT NULL,TipoBecaId INT NOT NULL,EstadoBecaId INT NOT NULL,
    CodigoBeca VARCHAR(100) NULL,PorcentajeBeca DECIMAL(9,2) NOT NULL CONSTRAINT DF_Beca_Porcentaje DEFAULT 0,
    ValorBeca DECIMAL(18,2) NOT NULL CONSTRAINT DF_Beca_Valor DEFAULT 0,Motivo NVARCHAR(1000) NULL,
    FechaSolicitud DATE NULL,FechaAprobacion DATE NULL,UsuarioAprobacion NVARCHAR(128) NULL,
    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_Beca_Creacion DEFAULT SYSDATETIME(),Activo BIT NOT NULL CONSTRAINT DF_Beca_Activo DEFAULT 1,
    CONSTRAINT FK_Beca_Estudiante FOREIGN KEY(EstudianteId) REFERENCES core.Estudiante(EstudianteId),
    CONSTRAINT FK_Beca_Cuenta FOREIGN KEY(CuentaEstudianteId) REFERENCES fin.CuentaEstudiante(CuentaEstudianteId),
    CONSTRAINT FK_Beca_Tipo FOREIGN KEY(TipoBecaId) REFERENCES cat.TipoBeca(TipoBecaId),
    CONSTRAINT FK_Beca_Estado FOREIGN KEY(EstadoBecaId) REFERENCES cat.EstadoBeca(EstadoBecaId)
);
GO

IF OBJECT_ID(N'fin.ObligacionEstudiante', N'U') IS NULL
CREATE TABLE fin.ObligacionEstudiante (
    ObligacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Obligacion PRIMARY KEY,CuentaEstudianteId BIGINT NOT NULL,
    CodigoConcepto VARCHAR(80) NOT NULL,Descripcion NVARCHAR(250) NULL,ValorOriginal DECIMAL(18,2) NOT NULL,
    SaldoPendiente DECIMAL(18,2) NOT NULL,FechaVencimiento DATE NULL,EstadoCodigo VARCHAR(40) NOT NULL CONSTRAINT DF_Obligacion_Estado DEFAULT 'PENDIENTE',
    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_Obligacion_Creacion DEFAULT SYSDATETIME(),
    CONSTRAINT FK_Obligacion_Cuenta FOREIGN KEY(CuentaEstudianteId) REFERENCES fin.CuentaEstudiante(CuentaEstudianteId)
);
IF OBJECT_ID(N'pag.PagoEstudiante', N'U') IS NULL
CREATE TABLE pag.PagoEstudiante (
    PagoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PagoEstudiante PRIMARY KEY,CuentaEstudianteId BIGINT NOT NULL,
    Referencia NVARCHAR(150) NULL,Valor DECIMAL(18,2) NOT NULL,FechaPago DATETIME2 NOT NULL,EstadoCodigo VARCHAR(40) NOT NULL CONSTRAINT DF_Pago_Estado DEFAULT 'REGISTRADO',
    CONSTRAINT FK_Pago_Cuenta FOREIGN KEY(CuentaEstudianteId) REFERENCES fin.CuentaEstudiante(CuentaEstudianteId)
);
IF OBJECT_ID(N'fac.Factura', N'U') IS NULL
CREATE TABLE fac.Factura (
    FacturaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Factura PRIMARY KEY,CuentaEstudianteId BIGINT NOT NULL,
    NumeroFactura NVARCHAR(100) NOT NULL,ValorTotal DECIMAL(18,2) NOT NULL,FechaEmision DATETIME2 NOT NULL,EstadoCodigo VARCHAR(40) NOT NULL CONSTRAINT DF_Factura_Estado DEFAULT 'EMITIDA',
    CONSTRAINT UQ_Factura_Numero UNIQUE(NumeroFactura),CONSTRAINT FK_Factura_Cuenta FOREIGN KEY(CuentaEstudianteId) REFERENCES fin.CuentaEstudiante(CuentaEstudianteId)
);
GO

IF OBJECT_ID(N'integ.EjecucionSincronizacion', N'U') IS NULL
CREATE TABLE integ.EjecucionSincronizacion (EjecucionSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Fin_EjecucionSync PRIMARY KEY,ProcesoCodigo VARCHAR(100) NOT NULL,EstadoCodigo VARCHAR(30) NOT NULL,FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_Fin_Sync_Inicio DEFAULT SYSDATETIME(),FechaFin DATETIME2 NULL,FilasProcesadas BIGINT NULL,UsuarioEjecucion NVARCHAR(128) NULL,Mensaje NVARCHAR(2000) NULL);
IF OBJECT_ID(N'integ.ErrorSincronizacion', N'U') IS NULL
CREATE TABLE integ.ErrorSincronizacion (ErrorSincronizacionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Fin_ErrorSync PRIMARY KEY,EjecucionSincronizacionId BIGINT NULL,NumeroError INT NULL,ProcedimientoError NVARCHAR(256) NULL,LineaError INT NULL,MensajeError NVARCHAR(4000) NOT NULL,FechaError DATETIME2 NOT NULL CONSTRAINT DF_Fin_ErrorSync_Fecha DEFAULT SYSDATETIME(),CONSTRAINT FK_Fin_ErrorSync_Ejecucion FOREIGN KEY(EjecucionSincronizacionId) REFERENCES integ.EjecucionSincronizacion(EjecucionSincronizacionId));
GO

CREATE OR ALTER VIEW rpt.vw_EstadoFinancieroIntegracion AS
SELECT e.EstudianteId,e.CodigoEstud,e.NumeroIdentificacion,e.NombreCompleto,c.CuentaEstudianteId,c.CodigoCarrera,c.CodigoPeriodo,
       c.Saldo,ISNULL(SUM(CASE WHEN o.EstadoCodigo='PENDIENTE' THEN o.SaldoPendiente ELSE 0 END),0) AS ObligacionesPendientes
FROM core.Estudiante e JOIN fin.CuentaEstudiante c ON c.EstudianteId=e.EstudianteId AND c.Activo=1
LEFT JOIN fin.ObligacionEstudiante o ON o.CuentaEstudianteId=c.CuentaEstudianteId
WHERE e.Activo=1 GROUP BY e.EstudianteId,e.CodigoEstud,e.NumeroIdentificacion,e.NombreCompleto,c.CuentaEstudianteId,c.CodigoCarrera,c.CodigoPeriodo,c.Saldo;
GO
CREATE OR ALTER PROCEDURE fin.sp_SincronizarProcesoFinancieroCompleto @Usuario NVARCHAR(128)=N'SQL'
AS
BEGIN
 SET NOCOUNT ON;
 INSERT INTO integ.EjecucionSincronizacion(ProcesoCodigo,EstadoCodigo,UsuarioEjecucion,FechaFin,FilasProcesadas,Mensaje)
 VALUES('PROCESO_FINANCIERO_COMPLETO','COMPLETADO',@Usuario,SYSDATETIME(),0,N'Use sync_complement_references.py para reconciliar con la fuente principal.');
END;
GO

/* ======================== INTEGRACION MICROSOFT GRAPH ================== */
USE INTEC_GRAPH_INTEGRACION;
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'core') EXEC(N'CREATE SCHEMA core AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'graph') EXEC(N'CREATE SCHEMA graph AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'identity') EXEC(N'CREATE SCHEMA [identity] AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'teams') EXEC(N'CREATE SCHEMA teams AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'mail') EXEC(N'CREATE SCHEMA mail AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'core.PersonaGraphRef', N'U') IS NULL
CREATE TABLE core.PersonaGraphRef (
    PersonaGraphRefId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PersonaGraphRef PRIMARY KEY,
    TipoPersonaCodigo VARCHAR(30) NOT NULL,NumeroIdentificacion VARCHAR(30) NOT NULL,CodigoEstud BIGINT NULL,CodigoDocente NVARCHAR(50) NULL,
    NombreCompleto NVARCHAR(250) NOT NULL,CorreoPersonal NVARCHAR(250) NULL,Telefono NVARCHAR(50) NULL,Celular NVARCHAR(50) NULL,
    CodigoCarrera VARCHAR(50) NULL,CodigoPeriodo VARCHAR(50) NULL,OrigenFuente VARCHAR(80) NULL,MetadataJson NVARCHAR(MAX) NULL,
    Activo BIT NOT NULL CONSTRAINT DF_PersonaGraph_Activo DEFAULT 1,FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_PersonaGraph_Sync DEFAULT SYSDATETIME(),
    FechaActualizacion DATETIME2 NULL,CONSTRAINT UQ_PersonaGraph_TipoDocumento UNIQUE(TipoPersonaCodigo,NumeroIdentificacion)
);
GO

IF OBJECT_ID(N'graph.OperacionGraph', N'U') IS NULL
CREATE TABLE graph.OperacionGraph (
    OperacionGraphId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OperacionGraph PRIMARY KEY,
    TipoOperacion VARCHAR(80) NOT NULL,EntidadTipo VARCHAR(80) NULL,EntidadId NVARCHAR(250) NULL,PayloadJson NVARCHAR(MAX) NULL,
    EstadoCodigo VARCHAR(30) NOT NULL CONSTRAINT DF_OperacionGraph_Estado DEFAULT 'PENDIENTE',Intentos INT NOT NULL CONSTRAINT DF_OperacionGraph_Intentos DEFAULT 0,
    LeaseHasta DATETIME2 NULL,LeaseOwner NVARCHAR(128) NULL,ResultadoJson NVARCHAR(MAX) NULL,UltimoError NVARCHAR(4000) NULL,
    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_OperacionGraph_Creacion DEFAULT SYSDATETIME(),FechaActualizacion DATETIME2 NULL
);
IF OBJECT_ID(N'[identity].UsuarioOffice365', N'U') IS NULL
CREATE TABLE [identity].UsuarioOffice365 (
    UsuarioOffice365Id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_UsuarioOffice365 PRIMARY KEY,PersonaGraphRefId BIGINT NULL,
    GraphUserId NVARCHAR(100) NOT NULL,UserPrincipalName NVARCHAR(320) NOT NULL,DisplayName NVARCHAR(250) NULL,Mail NVARCHAR(320) NULL,
    AccountEnabled BIT NULL,FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_Usuario365_Sync DEFAULT SYSDATETIME(),Activo BIT NOT NULL CONSTRAINT DF_Usuario365_Activo DEFAULT 1,
    CONSTRAINT UQ_Usuario365_Graph UNIQUE(GraphUserId),CONSTRAINT FK_Usuario365_Persona FOREIGN KEY(PersonaGraphRefId) REFERENCES core.PersonaGraphRef(PersonaGraphRefId)
);
IF OBJECT_ID(N'teams.EquipoClase', N'U') IS NULL
CREATE TABLE teams.EquipoClase (
    EquipoClaseId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EquipoClase PRIMARY KEY,GraphTeamId NVARCHAR(100) NOT NULL,
    DisplayName NVARCHAR(250) NOT NULL,CodigoPeriodo VARCHAR(50) NULL,CodigoCarrera VARCHAR(50) NULL,CodigoMateria VARCHAR(80) NULL,
    EstadoCodigo VARCHAR(30) NOT NULL CONSTRAINT DF_EquipoClase_Estado DEFAULT 'ACTIVO',FechaSincronizacion DATETIME2 NOT NULL CONSTRAINT DF_EquipoClase_Sync DEFAULT SYSDATETIME(),
    CONSTRAINT UQ_EquipoClase_Graph UNIQUE(GraphTeamId)
);
IF OBJECT_ID(N'mail.CorreoSalida', N'U') IS NULL
CREATE TABLE mail.CorreoSalida (
    CorreoSalidaId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CorreoSalida PRIMARY KEY,Remitente NVARCHAR(320) NULL,Destinatarios NVARCHAR(MAX) NOT NULL,
    Asunto NVARCHAR(500) NOT NULL,Cuerpo NVARCHAR(MAX) NULL,EstadoCodigo VARCHAR(30) NOT NULL CONSTRAINT DF_CorreoSalida_Estado DEFAULT 'PENDIENTE',
    GraphMessageId NVARCHAR(250) NULL,Intentos INT NOT NULL CONSTRAINT DF_CorreoSalida_Intentos DEFAULT 0,UltimoError NVARCHAR(4000) NULL,
    FechaCreacion DATETIME2 NOT NULL CONSTRAINT DF_CorreoSalida_Creacion DEFAULT SYSDATETIME(),FechaEnvio DATETIME2 NULL
);
GO

CREATE OR ALTER VIEW rpt.vw_EstadoGraphIntegracion AS
SELECT p.PersonaGraphRefId,p.TipoPersonaCodigo,p.NumeroIdentificacion,p.CodigoEstud,p.CodigoDocente,p.NombreCompleto,p.CorreoPersonal,
       u.GraphUserId,u.UserPrincipalName,u.AccountEnabled,u.FechaSincronizacion AS FechaSincronizacionOffice
FROM core.PersonaGraphRef p LEFT JOIN [identity].UsuarioOffice365 u ON u.PersonaGraphRefId=p.PersonaGraphRefId AND u.Activo=1
WHERE p.Activo=1;
GO
CREATE OR ALTER PROCEDURE graph.sp_RenovarLeaseOperacion @OperacionGraphId BIGINT,@LeaseOwner NVARCHAR(128),@Minutos INT=5
AS
BEGIN
 SET NOCOUNT ON; UPDATE graph.OperacionGraph SET LeaseOwner=@LeaseOwner,LeaseHasta=DATEADD(MINUTE,@Minutos,SYSDATETIME()),FechaActualizacion=SYSDATETIME()
 WHERE OperacionGraphId=@OperacionGraphId AND EstadoCodigo IN('PENDIENTE','PROCESANDO'); SELECT @@ROWCOUNT AS FilasAfectadas;
END;
GO
CREATE OR ALTER PROCEDURE graph.sp_RecuperarOperacionesVencidas
AS
BEGIN
 SET NOCOUNT ON; UPDATE graph.OperacionGraph SET EstadoCodigo='PENDIENTE',LeaseOwner=NULL,LeaseHasta=NULL,FechaActualizacion=SYSDATETIME()
 WHERE EstadoCodigo='PROCESANDO' AND LeaseHasta<SYSDATETIME(); SELECT @@ROWCOUNT AS FilasRecuperadas;
END;
GO

/* ========================= CONTROL DE INTEGRACION ====================== */
USE INTEC_INTEGRACION_CONTROL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'sync') EXEC(N'CREATE SCHEMA sync AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'snap') EXEC(N'CREATE SCHEMA snap AUTHORIZATION dbo');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'rpt') EXEC(N'CREATE SCHEMA rpt AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'sync.Ejecucion', N'U') IS NULL
CREATE TABLE sync.Ejecucion (
    EjecucionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Control_Ejecucion PRIMARY KEY,TipoEjecucion VARCHAR(50) NOT NULL,EstadoEjecucion VARCHAR(30) NOT NULL,
    UsuarioEjecucion NVARCHAR(128) NULL,HostEjecucion NVARCHAR(128) NULL,Aplicacion NVARCHAR(100) NULL,
    FechaInicio DATETIME2 NOT NULL CONSTRAINT DF_Control_Ejecucion_Inicio DEFAULT SYSDATETIME(),FechaFin DATETIME2 NULL,
    TotalPasos INT NOT NULL CONSTRAINT DF_Control_TotalPasos DEFAULT 0,PasosCorrectos INT NOT NULL CONSTRAINT DF_Control_PasosOk DEFAULT 0,
    PasosError INT NOT NULL CONSTRAINT DF_Control_PasosError DEFAULT 0,Resumen NVARCHAR(1000) NULL
);
IF OBJECT_ID(N'sync.EjecucionPaso', N'U') IS NULL
CREATE TABLE sync.EjecucionPaso (
    EjecucionPasoId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Control_EjecucionPaso PRIMARY KEY,EjecucionId BIGINT NOT NULL,NumeroPaso INT NOT NULL,
    ModuloCodigo VARCHAR(50) NOT NULL,NombrePaso NVARCHAR(250) NOT NULL,EstadoPaso VARCHAR(30) NOT NULL,FechaInicio DATETIME2 NOT NULL,FechaFin DATETIME2 NULL,
    FilasAfectadas BIGINT NULL,Mensaje NVARCHAR(4000) NULL,CONSTRAINT FK_Control_Paso_Ejecucion FOREIGN KEY(EjecucionId) REFERENCES sync.Ejecucion(EjecucionId)
);
IF OBJECT_ID(N'sync.ErrorIntegracion', N'U') IS NULL
CREATE TABLE sync.ErrorIntegracion (
    ErrorIntegracionId BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Control_Error PRIMARY KEY,EjecucionId BIGINT NULL,EjecucionPasoId BIGINT NULL,
    ModuloCodigo VARCHAR(50) NULL,ErrorMessage NVARCHAR(4000) NOT NULL,UsuarioRegistro NVARCHAR(128) NULL,
    FechaRegistro DATETIME2 NOT NULL CONSTRAINT DF_Control_Error_Fecha DEFAULT SYSDATETIME(),
    CONSTRAINT FK_Control_Error_Ejecucion FOREIGN KEY(EjecucionId) REFERENCES sync.Ejecucion(EjecucionId),
    CONSTRAINT FK_Control_Error_Paso FOREIGN KEY(EjecucionPasoId) REFERENCES sync.EjecucionPaso(EjecucionPasoId)
);
GO

IF OBJECT_ID(N'snap.EstadoAcademico', N'U') IS NULL CREATE TABLE snap.EstadoAcademico (NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT PK_Snap_Academico PRIMARY KEY,CodigoEstud BIGINT NULL,CodigoCarrera VARCHAR(50) NULL,CodigoPeriodo VARCHAR(50) NULL,EstadoCodigo VARCHAR(50) NULL,FechaSnapshot DATETIME2 NOT NULL CONSTRAINT DF_Snap_Academico_Fecha DEFAULT SYSDATETIME());
IF OBJECT_ID(N'snap.EstadoDocumental', N'U') IS NULL CREATE TABLE snap.EstadoDocumental (NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT PK_Snap_Documental PRIMARY KEY,ExpedienteId BIGINT NULL,EstadoCodigo VARCHAR(50) NULL,TotalDocumentos INT NOT NULL CONSTRAINT DF_Snap_Documentos DEFAULT 0,FechaSnapshot DATETIME2 NOT NULL CONSTRAINT DF_Snap_Documental_Fecha DEFAULT SYSDATETIME());
IF OBJECT_ID(N'snap.EstadoFinanciero', N'U') IS NULL CREATE TABLE snap.EstadoFinanciero (NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT PK_Snap_Financiero PRIMARY KEY,CuentaEstudianteId BIGINT NULL,Saldo DECIMAL(18,2) NULL,ObligacionesPendientes DECIMAL(18,2) NULL,FechaSnapshot DATETIME2 NOT NULL CONSTRAINT DF_Snap_Financiero_Fecha DEFAULT SYSDATETIME());
IF OBJECT_ID(N'snap.EstadoPracticas', N'U') IS NULL CREATE TABLE snap.EstadoPracticas (NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT PK_Snap_Practicas PRIMARY KEY,EstadoCodigo VARCHAR(50) NULL,PorcentajeAvance DECIMAL(9,2) NULL,FechaSnapshot DATETIME2 NOT NULL CONSTRAINT DF_Snap_Practicas_Fecha DEFAULT SYSDATETIME());
IF OBJECT_ID(N'snap.EstadoIdioma', N'U') IS NULL CREATE TABLE snap.EstadoIdioma (NumeroIdentificacion VARCHAR(30) NOT NULL CONSTRAINT PK_Snap_Idioma PRIMARY KEY,EstadoCodigo VARCHAR(50) NULL,Nivel NVARCHAR(80) NULL,FechaSnapshot DATETIME2 NOT NULL CONSTRAINT DF_Snap_Idioma_Fecha DEFAULT SYSDATETIME());
GO

CREATE OR ALTER VIEW rpt.vw_EstadoIntegralEstudiante AS
SELECT a.NumeroIdentificacion,a.CodigoEstud,a.CodigoCarrera,a.CodigoPeriodo,a.EstadoCodigo AS EstadoAcademico,
       d.EstadoCodigo AS EstadoDocumental,d.TotalDocumentos,f.Saldo,f.ObligacionesPendientes,
       p.EstadoCodigo AS EstadoPracticas,p.PorcentajeAvance,i.EstadoCodigo AS EstadoIdioma,i.Nivel,
       (SELECT MAX(v.FechaSnapshot) FROM (VALUES(a.FechaSnapshot),(d.FechaSnapshot),(f.FechaSnapshot),(p.FechaSnapshot),(i.FechaSnapshot)) v(FechaSnapshot)) AS FechaUltimaActualizacion
FROM snap.EstadoAcademico a
LEFT JOIN snap.EstadoDocumental d ON d.NumeroIdentificacion=a.NumeroIdentificacion
LEFT JOIN snap.EstadoFinanciero f ON f.NumeroIdentificacion=a.NumeroIdentificacion
LEFT JOIN snap.EstadoPracticas p ON p.NumeroIdentificacion=a.NumeroIdentificacion
LEFT JOIN snap.EstadoIdioma i ON i.NumeroIdentificacion=a.NumeroIdentificacion;
GO
CREATE OR ALTER PROCEDURE sync.sp_EjecutarSincronizacionCompleta @Usuario NVARCHAR(128)=N'SQL'
AS
BEGIN
 SET NOCOUNT ON;
 INSERT INTO sync.Ejecucion(TipoEjecucion,EstadoEjecucion,UsuarioEjecucion,HostEjecucion,Aplicacion,TotalPasos,PasosCorrectos,PasosError,Resumen,FechaFin)
 VALUES('SNAPSHOT_COMPLETO','COMPLETADO',@Usuario,HOST_NAME(),APP_NAME(),0,0,0,N'Control preparado; la API registra cada integracion complementaria.',SYSDATETIME());
 SELECT SCOPE_IDENTITY() AS EjecucionId;
END;
GO

SELECT DB_NAME() AS BaseDatos,N'Instalacion complementaria completada' AS Resultado;
GO
