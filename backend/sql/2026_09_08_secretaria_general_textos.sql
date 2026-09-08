USE [INTEC_SECRETARIA_GENERAL];
GO

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'cat.TipoDocumento', N'U') IS NULL
   OR OBJECT_ID(N'cat.PlantillaRequisitoDetalle', N'U') IS NULL
   OR OBJECT_ID(N'sec.ObservacionTramite', N'U') IS NULL
BEGIN
    THROW 51000, N'Primero aplique 2026_09_08_secretaria_general.sql.', 1;
END;
GO

BEGIN TRANSACTION;

MERGE cat.TipoDocumento AS target
USING (VALUES
    ('CEDULA', N'Cédula de identidad', N'Documento de identidad vigente.'),
    ('TITULO_BACHILLER', N'Título de bachiller', N'Requisito académico de ingreso.'),
    ('CERTIFICADO_NO_ADEUDAMIENTO', N'Certificado financiero de no adeudamiento', N'Certificación vigente emitida por el área financiera.'),
    ('RECORD_ACADEMICO_FIRMADO', N'Récord académico certificado', N'Récord académico completo, certificado y firmado por los responsables.'),
    ('CERTIFICADO_PRACTICAS', N'Documentación de prácticas laborales', N'Evidencia de cumplimiento de prácticas laborales o preprofesionales.'),
    ('CERTIFICADO_VINCULACION', N'Documentación de vinculación con la sociedad', N'Evidencia de cumplimiento de vinculación con la sociedad.'),
    ('DOCUMENTO_INGLES', N'Certificado o evidencia de Inglés', N'Documentación que acredita el cumplimiento del requisito de Inglés.'),
    ('DOCUMENTO_CERTIFICACIONES', N'Documento de certificaciones', N'Certificaciones presentadas para sustentar la homologación.'),
    ('DOCUMENTOS_UNIVERSIDAD_ORIGEN', N'Documentos de la universidad de origen', N'Documentación académica oficial emitida por la institución de origen.'),
    ('DOCUMENTO_HOMOLOGACION', N'Documento de homologación', N'Resolución o documento institucional que formaliza la homologación.'),
    ('HOMOLOGACION_ARTICULO_81', N'Respaldo del artículo 81', N'Documento aplicable a la homologación interna.'),
    ('HOMOLOGACION_ARTICULO_82', N'Respaldo del artículo 82', N'Documento aplicable a estudios externos con menos de 10 años.'),
    ('HOMOLOGACION_ARTICULO_83', N'Respaldo del artículo 83', N'Documento aplicable a estudios externos con más de 10 años.')
) AS source(Codigo, Nombre, Descripcion)
ON target.Codigo = source.Codigo
WHEN MATCHED THEN UPDATE SET
    Nombre = source.Nombre,
    Descripcion = source.Descripcion,
    Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, Descripcion)
    VALUES (source.Codigo, source.Nombre, source.Descripcion);

UPDATE detail
SET Instruccion = source.Instruccion,
    Activo = 1
FROM cat.PlantillaRequisitoDetalle detail
INNER JOIN cat.TipoDocumento document_type
    ON document_type.TipoDocumentoId = detail.TipoDocumentoId
INNER JOIN (VALUES
    ('CEDULA', N'Presentar una copia legible y vigente.'),
    ('TITULO_BACHILLER', N'Validar el título de bachiller registrado.'),
    ('CERTIFICADO_NO_ADEUDAMIENTO', N'Presentar el certificado vigente de no adeudamiento emitido por el área financiera.'),
    ('RECORD_ACADEMICO_FIRMADO', N'Presentar el récord académico completo, certificado y firmado por los responsables.'),
    ('CERTIFICADO_PRACTICAS', N'Validar la documentación de cumplimiento de prácticas laborales o preprofesionales.'),
    ('CERTIFICADO_VINCULACION', N'Validar la documentación de cumplimiento de vinculación con la sociedad.'),
    ('DOCUMENTO_INGLES', N'Validar el certificado o la evidencia oficial de cumplimiento de Inglés.'),
    ('DOCUMENTO_CERTIFICACIONES', N'Presentar las certificaciones que sustentan la homologación.'),
    ('DOCUMENTOS_UNIVERSIDAD_ORIGEN', N'Presentar los documentos académicos certificados por la universidad de origen.'),
    ('DOCUMENTO_HOMOLOGACION', N'Presentar la resolución o el documento institucional de homologación.'),
    ('HOMOLOGACION_ARTICULO_81', N'Presentar el respaldo aplicable a la homologación interna conforme al artículo 81.'),
    ('HOMOLOGACION_ARTICULO_82', N'Presentar el respaldo del artículo 82 para estudios con menos de 10 años.'),
    ('HOMOLOGACION_ARTICULO_83', N'Presentar el respaldo del artículo 83 para estudios con más de 10 años.')
) AS source(Codigo, Instruccion)
    ON source.Codigo = document_type.Codigo;

UPDATE detail
SET Activo = 0
FROM cat.PlantillaRequisitoDetalle detail
INNER JOIN cat.TipoDocumento document_type
    ON document_type.TipoDocumentoId = detail.TipoDocumentoId
WHERE document_type.Codigo IN ('RECORD_ACADEMICO', 'ACTA_GRADO', 'TITULO_INTEC', 'TITULO_SENESCYT');

UPDATE observation
SET Observacion = N'Falta cargar y presentar el documento obligatorio: ' + document_type.Nombre + N'.'
FROM sec.ObservacionTramite observation
INNER JOIN sec.TramiteRequisito requirement
    ON requirement.TramiteRequisitoId = observation.TramiteRequisitoId
INNER JOIN cat.TipoDocumento document_type
    ON document_type.TipoDocumentoId = requirement.TipoDocumentoId
WHERE observation.TipoObservacion = 'FALTANTE'
  AND observation.EsSistema = 1;

COMMIT TRANSACTION;
GO
