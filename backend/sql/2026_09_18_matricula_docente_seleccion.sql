-- Execute in the academic database, inside the enrollment transaction.
DECLARE @selection_lock int;
EXEC @selection_lock = sys.sp_getapplock
    @Resource = N'INTEC:matricula-docente-seleccion',
    @LockMode = N'Exclusive', @LockOwner = N'Transaction', @LockTimeout = 15000;
IF @selection_lock < 0
    THROW 50001, 'No se pudo bloquear la seleccion de matricula docente. Reintente.', 1;

IF OBJECT_ID(N'dbo.PORTAL_MATRICULA_DOCENTE_SELECCION', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PORTAL_MATRICULA_DOCENTE_SELECCION (
        codigo_doc int NOT NULL,
        cod_anio_basica int NOT NULL,
        codigo_materia int NOT NULL,
        codigo_periodo int NOT NULL,
        paralelo nvarchar(4) NOT NULL,
        cod_jornada int NOT NULL,
        codigo_estud int NOT NULL,
        registrado_por nvarchar(256) NOT NULL,
        fecha_registro datetime2 NOT NULL CONSTRAINT DF_PORTAL_MD_SELECCION_FECHA DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_PORTAL_MD_SELECCION PRIMARY KEY (
            codigo_doc, cod_anio_basica, codigo_materia, codigo_periodo,
            paralelo, cod_jornada, codigo_estud
        ),
        CONSTRAINT CK_PORTAL_MD_SELECCION_ESTUD CHECK (codigo_estud > 0)
    );
END;
