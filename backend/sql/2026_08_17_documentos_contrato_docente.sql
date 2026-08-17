/*
  Versionado privado de contratos docentes.
  El PDF base puede contener la firma del rector; la firma del docente se
  conserva como una nueva version para no sobrescribir el documento original.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'rrhh.ContratoDocenteDocumento', N'U') IS NULL
BEGIN
    CREATE TABLE rrhh.ContratoDocenteDocumento
    (
        ContratoDocumentoId BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ContratoDocenteDocumento PRIMARY KEY,
        ContratoDocenteId BIGINT NOT NULL,
        TipoDocumento VARCHAR(20) NOT NULL,
        ModalidadAcademica VARCHAR(20) NOT NULL,
        NombreArchivo NVARCHAR(260) NOT NULL,
        RutaInterna NVARCHAR(1000) NOT NULL,
        MimeType VARCHAR(100) NOT NULL
            CONSTRAINT DF_ContratoDocenteDocumento_MimeType DEFAULT ('application/pdf'),
        TamanoBytes BIGINT NOT NULL,
        HashSha256 CHAR(64) NOT NULL,
        EsVigente BIT NOT NULL
            CONSTRAINT DF_ContratoDocenteDocumento_EsVigente DEFAULT (1),
        UsuarioCarga NVARCHAR(256) NULL,
        FechaCarga DATETIME2 NOT NULL
            CONSTRAINT DF_ContratoDocenteDocumento_FechaCarga DEFAULT (SYSDATETIME()),
        FirmanteDocumento NVARCHAR(300) NULL,
        FechaFirma DATETIME2 NULL,
        FirmaMotivo NVARCHAR(500) NULL,
        CONSTRAINT FK_ContratoDocenteDocumento_Contrato
            FOREIGN KEY (ContratoDocenteId)
            REFERENCES rrhh.ContratoDocente(ContratoDocenteId),
        CONSTRAINT CK_ContratoDocenteDocumento_Tipo
            CHECK (TipoDocumento IN ('ORIGINAL', 'FIRMADO')),
        CONSTRAINT CK_ContratoDocenteDocumento_Modalidad
            CHECK (ModalidadAcademica IN ('REGULAR', 'HOMOLOGACION')),
        CONSTRAINT CK_ContratoDocenteDocumento_Tamano
            CHECK (TamanoBytes > 0)
    );
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'rrhh.ContratoDocenteDocumento')
      AND name = N'IX_ContratoDocenteDocumento_ContratoVigente'
)
BEGIN
    CREATE INDEX IX_ContratoDocenteDocumento_ContratoVigente
        ON rrhh.ContratoDocenteDocumento
        (
            ContratoDocenteId,
            TipoDocumento,
            EsVigente,
            ContratoDocumentoId DESC
        );
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'rrhh.ContratoDocenteDocumento')
      AND name = N'IX_ContratoDocenteDocumento_Hash'
)
BEGIN
    CREATE INDEX IX_ContratoDocenteDocumento_Hash
        ON rrhh.ContratoDocenteDocumento(HashSha256);
END;
