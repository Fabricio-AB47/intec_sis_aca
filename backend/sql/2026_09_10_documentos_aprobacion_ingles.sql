USE [INTEC_GRAPH_INTEGRACION];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'cat.EstadoDocumentoGraph', N'U') IS NULL
    THROW 51000, N'Primero aplique 2026_07_30_graph_expedientes_documentales.sql.', 1;
GO

MERGE cat.EstadoDocumentoGraph AS target
USING (VALUES
    ('VALIDADO', N'Validado', 1),
    ('OBSERVADO', N'Observado', 0)
) AS source(Codigo, Nombre, EsFinal)
   ON target.EstadoDocumentoGraphCodigo = source.Codigo
WHEN MATCHED THEN
    UPDATE SET Nombre = source.Nombre, EsFinal = source.EsFinal, Activo = 1
WHEN NOT MATCHED THEN
    INSERT(EstadoDocumentoGraphCodigo, Nombre, EsFinal)
    VALUES(source.Codigo, source.Nombre, source.EsFinal);
GO

PRINT N'Estados de revisión para la documentación de Inglés instalados correctamente.';
GO
