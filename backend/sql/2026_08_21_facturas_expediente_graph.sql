USE [INTEC_GRAPH_INTEGRACION];
GO

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'cat.TipoExpedienteGraph', N'U') IS NULL
BEGIN
    THROW 51000, N'Primero aplique 2026_07_30_graph_expedientes_documentales.sql.', 1;
END;
GO

MERGE cat.TipoExpedienteGraph AS target
USING (
    VALUES (
        'FACTURACION',
        N'Facturación',
        N'Facturas electrónicas XML y representaciones impresas RIDE del estudiante.'
    )
) AS source (Codigo, Nombre, Descripcion)
ON target.TipoExpedienteGraphCodigo = source.Codigo
WHEN MATCHED THEN
    UPDATE SET
        Nombre = source.Nombre,
        Descripcion = source.Descripcion,
        Activo = 1
WHEN NOT MATCHED THEN
    INSERT (TipoExpedienteGraphCodigo, Nombre, Descripcion, Activo)
    VALUES (source.Codigo, source.Nombre, source.Descripcion, 1);
GO

