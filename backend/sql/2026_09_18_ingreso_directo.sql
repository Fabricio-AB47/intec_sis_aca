-- Run in INTECBDD. The API also creates this table on its first saved admission.
-- This log makes repeated requests safe without changing legacy student tables.
IF OBJECT_ID(N'dbo.PORTAL_INGRESO_DIRECTO', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PORTAL_INGRESO_DIRECTO (
        solicitud_id uniqueidentifier NOT NULL CONSTRAINT PK_PORTAL_INGRESO_DIRECTO PRIMARY KEY,
        contenido_hash varchar(64) NOT NULL,
        codigo_estud int NOT NULL,
        cod_anio_basica int NOT NULL,
        codigo_periodo int NOT NULL,
        nivel int NOT NULL,
        registrado_por nvarchar(256) NOT NULL,
        fecha_registro datetime2 NOT NULL CONSTRAINT DF_PORTAL_INGRESO_DIRECTO_FECHA DEFAULT SYSUTCDATETIME(),
        resultado_json nvarchar(max) NOT NULL,
        CONSTRAINT CK_PORTAL_INGRESO_DIRECTO_NIVEL CHECK (nivel >= 1)
    );
END;
