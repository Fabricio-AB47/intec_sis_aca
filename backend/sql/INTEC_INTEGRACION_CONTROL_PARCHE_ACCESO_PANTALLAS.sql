USE [INTEC_INTEGRACION_CONTROL];
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cfg')
    EXEC(N'CREATE SCHEMA cfg AUTHORIZATION dbo');
GO

IF OBJECT_ID(N'cfg.PantallaPortal', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.PantallaPortal
    (
        Codigo VARCHAR(80) NOT NULL CONSTRAINT PK_PantallaPortal PRIMARY KEY,
        Nombre NVARCHAR(160) NOT NULL,
        Descripcion NVARCHAR(500) NULL,
        Grupo NVARCHAR(100) NOT NULL,
        Orden INT NOT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_PantallaPortal_Activo DEFAULT 1,
        FechaActualizacion DATETIME2 NOT NULL CONSTRAINT DF_PantallaPortal_Fecha DEFAULT SYSDATETIME()
    );
END;
GO

IF OBJECT_ID(N'cfg.AccesoPantallaRol', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.AccesoPantallaRol
    (
        RolCodigo VARCHAR(40) NOT NULL,
        PantallaCodigo VARCHAR(80) NOT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_AccesoPantallaRol_Activo DEFAULT 1,
        FechaActualizacion DATETIME2 NOT NULL CONSTRAINT DF_AccesoPantallaRol_Fecha DEFAULT SYSDATETIME(),
        UsuarioActualizacion NVARCHAR(128) NULL,
        CONSTRAINT PK_AccesoPantallaRol PRIMARY KEY (RolCodigo, PantallaCodigo),
        CONSTRAINT FK_AccesoPantallaRol_Pantalla FOREIGN KEY (PantallaCodigo)
            REFERENCES cfg.PantallaPortal(Codigo)
    );
END;
GO
