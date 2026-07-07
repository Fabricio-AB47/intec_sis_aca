USE TITULACION_INTEC;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'util')
    EXEC(N'CREATE SCHEMA util AUTHORIZATION dbo');
GO

CREATE OR ALTER FUNCTION util.fn_NumeroRefrendacionDesdeActa
(
    @NumeroActaGrado VARCHAR(100)
)
RETURNS VARCHAR(100)
AS
BEGIN
    DECLARE @Raw VARCHAR(100) = UPPER(LTRIM(RTRIM(ISNULL(@NumeroActaGrado, ''))));
    DECLARE @Suffix VARCHAR(100);
    DECLARE @VgaPos INT;
    DECLARE @LastDashFromRight INT;
    DECLARE @LastDash INT;
    DECLARE @Prefix VARCHAR(100);
    DECLARE @Correlativo VARCHAR(30);

    IF @Raw = '' RETURN NULL;

    SET @VgaPos = CHARINDEX('VGA-', @Raw);
    SET @Suffix =
        CASE
            WHEN @VgaPos > 0 THEN SUBSTRING(@Raw, @VgaPos + 4, 100)
            ELSE @Raw
        END;

    SET @Suffix = REPLACE(REPLACE(@Suffix, ' ', ''), '_', '-');
    SET @LastDashFromRight = CHARINDEX('-', REVERSE(@Suffix));

    IF @LastDashFromRight <= 0
        RETURN NULLIF(REPLACE(@Suffix, '-', ''), '');

    SET @LastDash = LEN(@Suffix) - @LastDashFromRight + 1;
    SET @Prefix = LEFT(@Suffix, @LastDash - 1);
    SET @Correlativo = SUBSTRING(@Suffix, @LastDash + 1, 30);

    RETURN NULLIF(CONCAT(REPLACE(@Prefix, '-', ''), '-', @Correlativo), '-');
END;
GO

CREATE OR ALTER TRIGGER tit.trg_set_numero_refrendacion_desde_acta
ON tit.ExpedienteTitulacion
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF TRIGGER_NESTLEVEL() > 1 RETURN;

    UPDATE E
       SET NumeroRefrendacion = util.fn_NumeroRefrendacionDesdeActa(I.NumeroActaGrado),
           FechaActualizacion = COALESCE(E.FechaActualizacion, SYSDATETIME())
    FROM tit.ExpedienteTitulacion E
    INNER JOIN inserted I
        ON I.ExpedienteId = E.ExpedienteId
    WHERE NULLIF(LTRIM(RTRIM(ISNULL(I.NumeroActaGrado, ''))), '') IS NOT NULL
      AND ISNULL(E.NumeroRefrendacion COLLATE Modern_Spanish_CI_AS, '') <>
          ISNULL(util.fn_NumeroRefrendacionDesdeActa(I.NumeroActaGrado) COLLATE Modern_Spanish_CI_AS, '');
END;
GO

UPDATE tit.ExpedienteTitulacion
   SET NumeroRefrendacion = util.fn_NumeroRefrendacionDesdeActa(NumeroActaGrado),
       FechaActualizacion = COALESCE(FechaActualizacion, SYSDATETIME())
WHERE NULLIF(LTRIM(RTRIM(ISNULL(NumeroActaGrado, ''))), '') IS NOT NULL
  AND ISNULL(NumeroRefrendacion COLLATE Modern_Spanish_CI_AS, '') <>
      ISNULL(util.fn_NumeroRefrendacionDesdeActa(NumeroActaGrado) COLLATE Modern_Spanish_CI_AS, '');
GO

SELECT
    util.fn_NumeroRefrendacionDesdeActa('INTEC-VGA-EBSG-Q-A-20251204-02') AS Ejemplo01,
    util.fn_NumeroRefrendacionDesdeActa('INTEC-VGA-EBSG-Q-A-20251204-01') AS Ejemplo02;
GO
