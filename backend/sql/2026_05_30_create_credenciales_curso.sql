USE [INTECBDD];
GO

IF OBJECT_ID('dbo.CREDENCIALES_CURSO', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CREDENCIALES_CURSO (
        id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CREDENCIALES_CURSO PRIMARY KEY,
        cod_curso NVARCHAR(50) NOT NULL,
        curso NVARCHAR(200) NOT NULL,
        primer_nombre NVARCHAR(60) NOT NULL,
        segundo_nombre NVARCHAR(60) NULL,
        primer_apellido NVARCHAR(60) NOT NULL,
        segundo_apellido NVARCHAR(60) NULL,
        cedula VARCHAR(20) NOT NULL,
        correo_electronico VARCHAR(150) NOT NULL,
        usuario_generado VARCHAR(150) NOT NULL,
        clave_temporal VARCHAR(80) NOT NULL,
        graph_user_id NVARCHAR(80) NULL,
        graph_user_principal_name NVARCHAR(150) NULL,
        graph_mail_sender NVARCHAR(150) NULL,
        estado_graph VARCHAR(60) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_estado_graph DEFAULT ('PENDIENTE_GRAPH'),
        error_graph NVARCHAR(1000) NULL,
        mensaje_enviado NVARCHAR(MAX) NULL,
        link_induccion VARCHAR(600) NOT NULL,
        correo_enviado BIT NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_correo_enviado DEFAULT (0),
        estado_envio VARCHAR(40) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_estado_envio DEFAULT ('PENDIENTE'),
        error_envio NVARCHAR(1000) NULL,
        fecha_creacion DATETIME2(0) NOT NULL CONSTRAINT DF_CREDENCIALES_CURSO_fecha_creacion DEFAULT (SYSDATETIME()),
        usuario_creacion VARCHAR(100) NULL,
        fecha_graph DATETIME2(0) NULL,
        fecha_envio DATETIME2(0) NULL,
        fecha_actualizacion DATETIME2(0) NULL
    );

    CREATE UNIQUE INDEX UX_CREDENCIALES_CURSO_cedula_curso
        ON dbo.CREDENCIALES_CURSO (cedula, cod_curso);
END;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_user_id') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_user_id NVARCHAR(80) NULL;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_user_principal_name') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_user_principal_name NVARCHAR(150) NULL;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'graph_mail_sender') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD graph_mail_sender NVARCHAR(150) NULL;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'estado_graph') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD estado_graph VARCHAR(60) NOT NULL
        CONSTRAINT DF_CREDENCIALES_CURSO_estado_graph DEFAULT ('PENDIENTE_GRAPH') WITH VALUES;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'error_graph') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD error_graph NVARCHAR(1000) NULL;
GO

IF COL_LENGTH('dbo.CREDENCIALES_CURSO', 'fecha_graph') IS NULL
    ALTER TABLE dbo.CREDENCIALES_CURSO ADD fecha_graph DATETIME2(0) NULL;
GO
