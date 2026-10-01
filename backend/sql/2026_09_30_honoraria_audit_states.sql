-- Non-destructive, idempotent extension of the teacher report audit states.
-- Execute against INTEC_INTEGRACION_CONTROL after the audit table exists.
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 15000;
IF OBJECT_ID(N'aud.EventoInformeDocente', N'U') IS NULL
    THROW 51000, 'The teacher report audit table is missing.', 1;
BEGIN TRANSACTION;
DECLARE @lock_result int;
EXEC @lock_result = sys.sp_getapplock
    @Resource=N'INTEC:honoraria-audit-schema:20260930',
    @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=15000;
IF @lock_result < 0
    THROW 51001, 'Could not lock the teacher report audit schema.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id=OBJECT_ID(N'aud.EventoInformeDocente')
      AND name=N'CK_AudEventoInforme_Etapa'
      AND definition LIKE '%ENVIANDO%' AND definition LIKE '%ENVIADO%'
      AND is_disabled=0 AND is_not_trusted=0
)
BEGIN
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'aud.EventoInformeDocente') AND name=N'CK_AudEventoInforme_Etapa')
        ALTER TABLE aud.EventoInformeDocente DROP CONSTRAINT CK_AudEventoInforme_Etapa;
    ALTER TABLE aud.EventoInformeDocente WITH CHECK ADD CONSTRAINT CK_AudEventoInforme_Etapa
        CHECK (Etapa IN ('GENERADO','FIRMADO','ARCHIVADO','ERROR','ENVIANDO','ENVIADO'));
END;
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id=OBJECT_ID(N'aud.EventoInformeDocente')
      AND name=N'CK_AudEventoInforme_Estado'
      AND definition LIKE '%INCIERTO%'
      AND is_disabled=0 AND is_not_trusted=0
)
BEGIN
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'aud.EventoInformeDocente') AND name=N'CK_AudEventoInforme_Estado')
        ALTER TABLE aud.EventoInformeDocente DROP CONSTRAINT CK_AudEventoInforme_Estado;
    ALTER TABLE aud.EventoInformeDocente WITH CHECK ADD CONSTRAINT CK_AudEventoInforme_Estado
        CHECK (Estado IN ('EXITOSO','ERROR','INCIERTO'));
END;
COMMIT TRANSACTION;
