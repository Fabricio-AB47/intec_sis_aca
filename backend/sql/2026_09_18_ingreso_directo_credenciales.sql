-- Created on the first provisioning request, after the academic admission exists.
-- Passwords remain encrypted in the existing CREDENCIAL_APROVISIONAMIENTO archive.
DECLARE @schema_lock int;
EXEC @schema_lock=sys.sp_getapplock @Resource=N'PORTAL_INGRESO_CREDENCIALES_SCHEMA',
    @LockMode=N'Exclusive', @LockOwner=N'Transaction', @LockTimeout=15000;
IF @schema_lock < 0 THROW 51000, 'No se pudo preparar el registro de credenciales.', 1;
IF OBJECT_ID(N'dbo.PORTAL_INGRESO_CREDENCIALES', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PORTAL_INGRESO_CREDENCIALES (
        solicitud_id uniqueidentifier NOT NULL CONSTRAINT PK_PORTAL_INGRESO_CREDENCIALES PRIMARY KEY,
        persona_json nvarchar(max) NOT NULL,
        resultado_json nvarchar(max) NULL,
        reporte_credencial_id bigint NULL,
        registrado_por nvarchar(256) NOT NULL,
        fecha_actualizacion datetime2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_INGRESO_CREDENCIALES_SOLICITUD FOREIGN KEY (solicitud_id)
            REFERENCES dbo.PORTAL_INGRESO_DIRECTO(solicitud_id)
    );
END;
