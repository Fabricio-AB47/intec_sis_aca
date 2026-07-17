USE TITULACION_INTEC;
GO

/*
Prompt 08 - Cierre operativo idempotente

- Normaliza defaults antiguos de auditoria que usaban SYSTEM_USER directamente.
- Mantiene el patron solicitado para procedimientos: @Usuario = NULL y
  COALESCE(@Usuario, SYSTEM_USER) dentro del cuerpo del procedimiento.
*/

SET NOCOUNT ON;
GO

IF SCHEMA_ID(N'cat') IS NULL EXEC(N'CREATE SCHEMA cat');
GO

IF OBJECT_ID(N'cat.TipoDocumentoTitulacion', N'U') IS NULL
BEGIN
    CREATE TABLE cat.TipoDocumentoTitulacion
    (
        TipoDocumentoTitulacionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TipoDocumentoTitulacion_Prompt08 PRIMARY KEY,
        Codigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL,
        Nombre NVARCHAR(500) COLLATE Modern_Spanish_CI_AS NOT NULL,
        AplicaMecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL,
        MecanismoCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL,
        EsObligatorio BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Obligatorio_Prompt08 DEFAULT 0,
        BloqueaActa BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_BloqueaActa_Prompt08 DEFAULT 0,
        Orden INT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Orden_Prompt08 DEFAULT 1,
        Activo BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_Activo_Prompt08 DEFAULT 1
    );
END;
GO

IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'Codigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD Codigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'TipoDocumentoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD TipoDocumentoCodigo VARCHAR(80) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'AplicaMecanismoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD AplicaMecanismoCodigo VARCHAR(40) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'MecanismoCodigo') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD MecanismoCodigo VARCHAR(50) COLLATE Modern_Spanish_CI_AS NULL;
IF COL_LENGTH(N'cat.TipoDocumentoTitulacion', N'BloqueaActa') IS NULL
    ALTER TABLE cat.TipoDocumentoTitulacion ADD BloqueaActa BIT NOT NULL CONSTRAINT DF_TipoDocumentoTitulacion_BloqueaActa_Cierre08 DEFAULT 0;
GO

UPDATE cat.TipoDocumentoTitulacion
   SET Codigo = COALESCE(Codigo, TipoDocumentoCodigo),
       TipoDocumentoCodigo = COALESCE(TipoDocumentoCodigo, Codigo),
       AplicaMecanismoCodigo = COALESCE(AplicaMecanismoCodigo, MecanismoCodigo),
       MecanismoCodigo = COALESCE(MecanismoCodigo, AplicaMecanismoCodigo)
 WHERE Codigo IS NULL
    OR TipoDocumentoCodigo IS NULL
    OR (AplicaMecanismoCodigo IS NULL AND MecanismoCodigo IS NOT NULL)
    OR (MecanismoCodigo IS NULL AND AplicaMecanismoCodigo IS NOT NULL);
GO

MERGE cat.TipoDocumentoTitulacion AS T
USING (VALUES
    ('APTITUD_LEGAL', N'Aptitud legal', NULL, 1, 1),
    ('PROGRAMACION_EXAMEN', N'Programacion de examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 2),
    ('EVIDENCIA_EXAMEN_COMPLEXIVO', N'Evidencia de examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 3),
    ('RUBRICA_EVALUADORES', N'Rubricas de evaluadores', 'EXAMEN_COMPLEXIVO', 1, 4),
    ('ACTA_EXAMEN_COMPLEXIVO', N'Acta de examen complexivo', 'EXAMEN_COMPLEXIVO', 0, 5),
    ('TRABAJO_FINAL_GRADO', N'Trabajo final de grado', 'DEFENSA_GRADO', 1, 2),
    ('PROGRAMACION_DEFENSA', N'Programacion de defensa', 'DEFENSA_GRADO', 1, 3),
    ('ACTA_DEFENSA', N'Acta de defensa', 'DEFENSA_GRADO', 1, 4),
    ('RUBRICA_TRABAJO_ESCRITO', N'Rubrica de trabajo escrito', 'DEFENSA_GRADO', 1, 5),
    ('RUBRICA_DEFENSA_ORAL', N'Rubrica de defensa oral', 'DEFENSA_GRADO', 1, 6),
    ('ACTA_GRADO', N'Acta de grado', NULL, 0, 90),
    ('ACTA_GRADO_FIRMADA', N'Acta de grado firmada', NULL, 0, 91),
    ('TITULO_REGISTRO_SENESCYT', N'Titulo registrado SENESCYT', NULL, 0, 100),
    ('TITULO_INTEC', N'Titulo INTEC', NULL, 0, 101)
) AS S(Codigo, Nombre, AplicaMecanismoCodigo, EsObligatorio, Orden)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN UPDATE SET
    Codigo = S.Codigo,
    TipoDocumentoCodigo = S.Codigo,
    Nombre = S.Nombre,
    AplicaMecanismoCodigo = S.AplicaMecanismoCodigo,
    MecanismoCodigo = S.AplicaMecanismoCodigo,
    EsObligatorio = S.EsObligatorio,
    BloqueaActa = S.EsObligatorio,
    Orden = S.Orden,
    Activo = 1
WHEN NOT MATCHED THEN
    INSERT(Codigo, TipoDocumentoCodigo, Nombre, AplicaMecanismoCodigo, MecanismoCodigo, EsObligatorio, BloqueaActa, Orden)
    VALUES(S.Codigo, S.Codigo, S.Nombre, S.AplicaMecanismoCodigo, S.AplicaMecanismoCodigo, S.EsObligatorio, S.EsObligatorio, S.Orden);
GO

DECLARE @DefaultsUsuario TABLE
(
    SchemaName SYSNAME NOT NULL,
    TableName SYSNAME NOT NULL,
    ColumnName SYSNAME NOT NULL,
    ConstraintName SYSNAME NOT NULL
);

INSERT INTO @DefaultsUsuario(SchemaName, TableName, ColumnName, ConstraintName)
VALUES
    (N'tit',  N'ProgramacionTitulacion',          N'UsuarioRegistro', N'DF_ProgramacionTitulacion_Usuario'),
    (N'tit',  N'TribunalTitulacion',              N'UsuarioRegistro', N'DF_TribunalTitulacion_Usuario'),
    (N'tit',  N'ExamenComplexivo',                N'UsuarioRegistro', N'DF_ExamenComplexivo_Usuario'),
    (N'tit',  N'DefensaGrado',                    N'UsuarioRegistro', N'DF_DefensaGrado_Usuario'),
    (N'tit',  N'GrupoTitulacion',                 N'UsuarioRegistro', N'DF_GrupoTitulacion_Usuario'),
    (N'tit',  N'GrupoTitulacionExpediente',       N'UsuarioRegistro', N'DF_GrupoTitulacionExpediente_Usuario'),
    (N'tit',  N'EvaluadorTitulacion',             N'UsuarioRegistro', N'DF_EvaluadorTitulacion_Usuario'),
    (N'tit',  N'CalificacionEvaluadorTitulacion', N'UsuarioRegistro', N'DF_CalificacionEvaluadorTitulacion_Usuario'),
    (N'tit',  N'RubricaTitulacion',               N'UsuarioRegistro', N'DF_RubricaTitulacion_Usuario'),
    (N'tit',  N'RubricaCriterio',                 N'UsuarioRegistro', N'DF_RubricaCriterio_Usuario'),
    (N'tit',  N'CalificacionConsolidadaTitulacion', N'UsuarioRegistro', N'DF_CalificacionConsolidada_Usuario'),
    (N'aud',  N'AuditoriaTitulacion',             N'UsuarioRegistro', N'DF_AuditoriaTitulacion_Usuario');

DECLARE
    @SchemaName SYSNAME,
    @TableName SYSNAME,
    @ColumnName SYSNAME,
    @ConstraintName SYSNAME,
    @ObjectId INT,
    @ExistingConstraint SYSNAME,
    @ExistingDefinition NVARCHAR(MAX),
    @Sql NVARCHAR(MAX);

DECLARE defaults_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT SchemaName, TableName, ColumnName, ConstraintName
FROM @DefaultsUsuario;

OPEN defaults_cursor;
FETCH NEXT FROM defaults_cursor INTO @SchemaName, @TableName, @ColumnName, @ConstraintName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @ObjectId = OBJECT_ID(QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@TableName), N'U');

    IF @ObjectId IS NOT NULL AND COL_LENGTH(@SchemaName + N'.' + @TableName, @ColumnName) IS NOT NULL
    BEGIN
        SELECT
            @ExistingConstraint = dc.name,
            @ExistingDefinition = dc.definition
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON c.object_id = dc.parent_object_id
           AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = @ObjectId
          AND c.name = @ColumnName;

        IF @ExistingConstraint IS NOT NULL AND LOWER(ISNULL(@ExistingDefinition, N'')) LIKE N'%system_user%'
        BEGIN
            SET @Sql = N'ALTER TABLE ' + QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@TableName)
                + N' DROP CONSTRAINT ' + QUOTENAME(@ExistingConstraint) + N';';
            EXEC sys.sp_executesql @Sql;
            SET @ExistingConstraint = NULL;
        END;

        IF @ExistingConstraint IS NULL
        BEGIN
            SET @Sql = N'ALTER TABLE ' + QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@TableName)
                + N' ADD CONSTRAINT ' + QUOTENAME(@ConstraintName)
                + N' DEFAULT N''SISTEMA'' FOR ' + QUOTENAME(@ColumnName) + N';';
            EXEC sys.sp_executesql @Sql;
        END;
    END;

    SET @ExistingConstraint = NULL;
    SET @ExistingDefinition = NULL;

    FETCH NEXT FROM defaults_cursor INTO @SchemaName, @TableName, @ColumnName, @ConstraintName;
END;

CLOSE defaults_cursor;
DEALLOCATE defaults_cursor;
GO

PRINT 'Prompt 08 cierre aplicado: defaults de usuario normalizados.';
GO
