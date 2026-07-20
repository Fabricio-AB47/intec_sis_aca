/*
QA smoke tests - TITULACION_INTEC
Ejecutar contra la base TITULACION_INTEC despues de las migraciones.
No inserta, actualiza ni elimina datos.
*/

USE TITULACION_INTEC;
GO

SET NOCOUNT ON;

DECLARE @Fallas TABLE
(
    Tipo NVARCHAR(40) NOT NULL,
    Nombre NVARCHAR(200) NOT NULL,
    Detalle NVARCHAR(500) NULL
);

INSERT INTO @Fallas(Tipo, Nombre, Detalle)
SELECT 'TABLE', 'tit.ProgramacionTitulacion', 'Tabla requerida para programacion'
WHERE OBJECT_ID(N'tit.ProgramacionTitulacion', N'U') IS NULL
UNION ALL SELECT 'TABLE', 'tit.ExamenComplexivo', 'Tabla requerida para examen complexivo'
WHERE OBJECT_ID(N'tit.ExamenComplexivo', N'U') IS NULL
UNION ALL SELECT 'TABLE', 'tit.DefensaGrado', 'Tabla requerida para defensa de grado'
WHERE OBJECT_ID(N'tit.DefensaGrado', N'U') IS NULL
UNION ALL SELECT 'TABLE', 'tit.TribunalTitulacion', 'Tabla requerida para tribunal'
WHERE OBJECT_ID(N'tit.TribunalTitulacion', N'U') IS NULL
UNION ALL SELECT 'TABLE', 'doc.DocumentoTitulacionHistorial', 'Historial documental requerido'
WHERE OBJECT_ID(N'doc.DocumentoTitulacionHistorial', N'U') IS NULL
UNION ALL SELECT 'TABLE', 'tit.SecuenciaActaGrado', 'Numeracion configurable de actas'
WHERE OBJECT_ID(N'tit.SecuenciaActaGrado', N'U') IS NULL
UNION ALL SELECT 'VIEW', 'rpt.vw_TitulosPortal', 'Vista requerida para portal de titulos'
WHERE OBJECT_ID(N'rpt.vw_TitulosPortal', N'V') IS NULL
UNION ALL SELECT 'PROC', 'tit.sp_GenerarNumeroActaGrado', 'Procedimiento requerido para numeracion'
WHERE OBJECT_ID(N'tit.sp_GenerarNumeroActaGrado', N'P') IS NULL
UNION ALL SELECT 'PROC', 'doc.sp_CargarTituloRegistradoV2', 'Procedimiento requerido para titulo SENESCYT'
WHERE OBJECT_ID(N'doc.sp_CargarTituloRegistradoV2', N'P') IS NULL
UNION ALL SELECT 'PROC', 'doc.sp_CargarTituloIntecV2', 'Procedimiento requerido para titulo INTEC'
WHERE OBJECT_ID(N'doc.sp_CargarTituloIntecV2', N'P') IS NULL
UNION ALL SELECT 'PROC', 'tit.sp_AnularActaGrado', 'Procedimiento requerido para anulacion'
WHERE OBJECT_ID(N'tit.sp_AnularActaGrado', N'P') IS NULL
UNION ALL SELECT 'COLUMN', 'doc.DocumentoTitulacion.CodigoRegistroSenescyt', 'Metadato SENESCYT'
WHERE COL_LENGTH(N'doc.DocumentoTitulacion', N'CodigoRegistroSenescyt') IS NULL
UNION ALL SELECT 'COLUMN', 'doc.DocumentoTitulacion.NumeroTituloIntec', 'Metadato titulo INTEC'
WHERE COL_LENGTH(N'doc.DocumentoTitulacion', N'NumeroTituloIntec') IS NULL
UNION ALL SELECT 'COLUMN', 'tit.ActaGrado.TextoVariableActa', 'Texto variable del acta'
WHERE COL_LENGTH(N'tit.ActaGrado', N'TextoVariableActa') IS NULL
UNION ALL SELECT 'CATALOGO', 'TITULO_REGISTRO_SENESCYT', 'Tipo documental requerido'
WHERE NOT EXISTS (SELECT 1 FROM cat.TipoDocumentoTitulacion WHERE Codigo = 'TITULO_REGISTRO_SENESCYT' AND Activo = 1)
UNION ALL SELECT 'CATALOGO', 'TITULO_INTEC', 'Tipo documental requerido'
WHERE NOT EXISTS (SELECT 1 FROM cat.TipoDocumentoTitulacion WHERE Codigo = 'TITULO_INTEC' AND Activo = 1)
UNION ALL SELECT 'CATALOGO', 'ACTA_GRADO_FIRMADA', 'Tipo documental requerido'
WHERE NOT EXISTS (SELECT 1 FROM cat.TipoDocumentoTitulacion WHERE Codigo = 'ACTA_GRADO_FIRMADA' AND Activo = 1);

IF EXISTS (SELECT 1 FROM @Fallas)
BEGIN
    SELECT * FROM @Fallas ORDER BY Tipo, Nombre;
    THROW 59990, 'QA smoke TITULACION_INTEC fallo. Revise el resultado anterior.', 1;
END;

SELECT 'OK' AS Estado, 'QA smoke TITULACION_INTEC completado sin fallas.' AS Mensaje;
GO
