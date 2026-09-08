USE [INTEC_SECRETARIA_GENERAL];
GO

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'sec.Tramite', N'U') IS NULL
   OR OBJECT_ID(N'sec.TramiteRequisito', N'U') IS NULL
   OR OBJECT_ID(N'cat.TipoDocumento', N'U') IS NULL
   OR OBJECT_ID(N'cat.PlantillaRequisitoDetalle', N'U') IS NULL
BEGIN
    THROW 51000, N'Primero aplique 2026_09_08_secretaria_general.sql.', 1;
END;
GO

IF COL_LENGTH(N'sec.Tramite', N'TipoHomologacion') IS NULL
    ALTER TABLE sec.Tramite ADD TipoHomologacion varchar(30) NULL;
GO

UPDATE sec.Tramite
SET TipoHomologacion = NULL
WHERE TipoMatricula = 'R' AND TipoHomologacion IS NOT NULL;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sec.Tramite')
      AND name = N'CK_Tramite_TipoHomologacion'
)
    ALTER TABLE sec.Tramite WITH CHECK ADD CONSTRAINT CK_Tramite_TipoHomologacion CHECK
        (TipoHomologacion IS NULL OR TipoHomologacion IN ('INTERNA_ART81', 'EXTERNA_ART82', 'EXTERNA_ART83'));
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
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, Descripcion)
    VALUES (source.Codigo, source.Nombre, source.Descripcion);

DECLARE @TipoTramiteId int =
(
    SELECT TipoTramiteId
    FROM cat.TipoTramite
    WHERE Codigo = 'REVISION_EXPEDIENTE_GRADO'
);
DECLARE @VersionId int =
(
    SELECT TOP (1) PlantillaRequisitoVersionId
    FROM cat.PlantillaRequisitoVersion
    WHERE TipoTramiteId = @TipoTramiteId AND Activo = 1
    ORDER BY VigenteDesde DESC, PlantillaRequisitoVersionId DESC
);

IF @VersionId IS NULL
    THROW 51001, N'No existe una plantilla documental activa para Secretaría General.', 1;

MERGE cat.PlantillaRequisitoDetalle AS target
USING
(
    SELECT @VersionId, document_type.TipoDocumentoId, requirement.EsObligatorio,
           requirement.AplicaProximo, requirement.AplicaEgresado,
           requirement.AplicaGraduado, requirement.Orden, requirement.Instruccion
    FROM (VALUES
        ('CEDULA', 1, 1, 1, 1, 10, N'Presentar una copia legible y vigente.'),
        ('TITULO_BACHILLER', 1, 1, 1, 1, 20, N'Validar el título de bachiller registrado.'),
        ('CERTIFICADO_NO_ADEUDAMIENTO', 1, 1, 1, 1, 30, N'Presentar el certificado vigente de no adeudamiento emitido por el área financiera.'),
        ('RECORD_ACADEMICO_FIRMADO', 1, 1, 1, 1, 40, N'Presentar el récord académico completo, certificado y firmado por los responsables.'),
        ('CERTIFICADO_PRACTICAS', 1, 1, 1, 1, 50, N'Validar la documentación de cumplimiento de prácticas laborales o preprofesionales.'),
        ('CERTIFICADO_VINCULACION', 1, 1, 1, 1, 60, N'Validar la documentación de cumplimiento de vinculación con la sociedad.'),
        ('DOCUMENTO_INGLES', 1, 1, 1, 1, 70, N'Validar el certificado o la evidencia oficial de cumplimiento de Inglés.'),
        ('DOCUMENTO_CERTIFICACIONES', 1, 1, 1, 1, 80, N'Presentar las certificaciones que sustentan la homologación.'),
        ('DOCUMENTOS_UNIVERSIDAD_ORIGEN', 1, 1, 1, 1, 90, N'Presentar los documentos académicos certificados por la universidad de origen.'),
        ('DOCUMENTO_HOMOLOGACION', 1, 1, 1, 1, 100, N'Presentar la resolución o el documento institucional de homologación.'),
        ('HOMOLOGACION_ARTICULO_81', 1, 1, 1, 1, 110, N'Presentar el respaldo aplicable a la homologación interna conforme al artículo 81.'),
        ('HOMOLOGACION_ARTICULO_82', 1, 1, 1, 1, 120, N'Presentar el respaldo del artículo 82 para estudios con menos de 10 años.'),
        ('HOMOLOGACION_ARTICULO_83', 1, 1, 1, 1, 130, N'Presentar el respaldo del artículo 83 para estudios con más de 10 años.')
    ) AS requirement(Codigo, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
    INNER JOIN cat.TipoDocumento document_type ON document_type.Codigo = requirement.Codigo
) AS source(PlantillaRequisitoVersionId, TipoDocumentoId, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
ON target.PlantillaRequisitoVersionId = source.PlantillaRequisitoVersionId
AND target.TipoDocumentoId = source.TipoDocumentoId
WHEN MATCHED THEN UPDATE SET
    EsObligatorio = source.EsObligatorio,
    AplicaProximo = source.AplicaProximo,
    AplicaEgresado = source.AplicaEgresado,
    AplicaGraduado = source.AplicaGraduado,
    Orden = source.Orden,
    Instruccion = source.Instruccion,
    Activo = 1
WHEN NOT MATCHED THEN INSERT
    (PlantillaRequisitoVersionId, TipoDocumentoId, EsObligatorio, AplicaProximo, AplicaEgresado, AplicaGraduado, Orden, Instruccion)
VALUES
    (source.PlantillaRequisitoVersionId, source.TipoDocumentoId, source.EsObligatorio, source.AplicaProximo, source.AplicaEgresado, source.AplicaGraduado, source.Orden, source.Instruccion);

UPDATE detail
SET Activo = 0
FROM cat.PlantillaRequisitoDetalle detail
INNER JOIN cat.TipoDocumento document_type ON document_type.TipoDocumentoId = detail.TipoDocumentoId
WHERE detail.PlantillaRequisitoVersionId = @VersionId
  AND document_type.Codigo IN ('RECORD_ACADEMICO', 'ACTA_GRADO', 'TITULO_INTEC', 'TITULO_SENESCYT');

INSERT sec.TramiteRequisito
    (TramiteId, TipoDocumentoId, EsObligatorio, EsAplicable, Orden, EstadoCodigo)
SELECT
    process.TramiteId,
    detail.TipoDocumentoId,
    detail.EsObligatorio,
    applicability.EsAplicable,
    detail.Orden,
    CASE WHEN applicability.EsAplicable = 1 THEN 'FALTANTE' ELSE 'NO_APLICA' END
FROM sec.Tramite process
INNER JOIN cat.PlantillaRequisitoDetalle detail
    ON detail.PlantillaRequisitoVersionId = process.PlantillaRequisitoVersionId
   AND detail.Activo = 1
INNER JOIN cat.TipoDocumento document_type ON document_type.TipoDocumentoId = detail.TipoDocumentoId
CROSS APPLY
(
    SELECT CAST(CASE
        WHEN document_type.Codigo IN
            ('CEDULA', 'TITULO_BACHILLER', 'CERTIFICADO_NO_ADEUDAMIENTO', 'RECORD_ACADEMICO_FIRMADO',
             'CERTIFICADO_PRACTICAS', 'CERTIFICADO_VINCULACION', 'DOCUMENTO_INGLES') THEN 1
        WHEN process.TipoMatricula = 'H'
         AND document_type.Codigo IN
            ('DOCUMENTO_CERTIFICACIONES', 'DOCUMENTOS_UNIVERSIDAD_ORIGEN', 'DOCUMENTO_HOMOLOGACION') THEN 1
        WHEN process.TipoMatricula = 'H' AND
        (
            (process.TipoHomologacion = 'INTERNA_ART81' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_81')
            OR (process.TipoHomologacion = 'EXTERNA_ART82' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_82')
            OR (process.TipoHomologacion = 'EXTERNA_ART83' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_83')
        ) THEN 1
        ELSE 0
    END AS bit) AS EsAplicable
) applicability
WHERE process.Activo = 1
  AND NOT EXISTS
  (
      SELECT 1
      FROM sec.TramiteRequisito current_requirement
      WHERE current_requirement.TramiteId = process.TramiteId
        AND current_requirement.TipoDocumentoId = detail.TipoDocumentoId
  );

UPDATE requirement
SET EsObligatorio = detail.EsObligatorio,
    EsAplicable = applicability.EsAplicable,
    Orden = detail.Orden,
    EstadoCodigo = CASE
        WHEN applicability.EsAplicable = 0 THEN 'NO_APLICA'
        WHEN requirement.EstadoCodigo = 'NO_APLICA' THEN 'FALTANTE'
        ELSE requirement.EstadoCodigo
    END,
    FechaActualizacion = SYSUTCDATETIME()
FROM sec.TramiteRequisito requirement
INNER JOIN sec.Tramite process ON process.TramiteId = requirement.TramiteId
INNER JOIN cat.PlantillaRequisitoDetalle detail
    ON detail.PlantillaRequisitoVersionId = process.PlantillaRequisitoVersionId
   AND detail.TipoDocumentoId = requirement.TipoDocumentoId
   AND detail.Activo = 1
INNER JOIN cat.TipoDocumento document_type ON document_type.TipoDocumentoId = detail.TipoDocumentoId
CROSS APPLY
(
    SELECT CAST(CASE
        WHEN document_type.Codigo IN
            ('CEDULA', 'TITULO_BACHILLER', 'CERTIFICADO_NO_ADEUDAMIENTO', 'RECORD_ACADEMICO_FIRMADO',
             'CERTIFICADO_PRACTICAS', 'CERTIFICADO_VINCULACION', 'DOCUMENTO_INGLES') THEN 1
        WHEN process.TipoMatricula = 'H'
         AND document_type.Codigo IN
            ('DOCUMENTO_CERTIFICACIONES', 'DOCUMENTOS_UNIVERSIDAD_ORIGEN', 'DOCUMENTO_HOMOLOGACION') THEN 1
        WHEN process.TipoMatricula = 'H' AND
        (
            (process.TipoHomologacion = 'INTERNA_ART81' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_81')
            OR (process.TipoHomologacion = 'EXTERNA_ART82' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_82')
            OR (process.TipoHomologacion = 'EXTERNA_ART83' AND document_type.Codigo = 'HOMOLOGACION_ARTICULO_83')
        ) THEN 1
        ELSE 0
    END AS bit) AS EsAplicable
) applicability
WHERE process.Activo = 1;

UPDATE requirement
SET EsAplicable = 0,
    EstadoCodigo = 'NO_APLICA',
    FechaActualizacion = SYSUTCDATETIME()
FROM sec.TramiteRequisito requirement
INNER JOIN sec.Tramite process ON process.TramiteId = requirement.TramiteId
WHERE process.Activo = 1
  AND NOT EXISTS
  (
      SELECT 1
      FROM cat.PlantillaRequisitoDetalle detail
      WHERE detail.PlantillaRequisitoVersionId = process.PlantillaRequisitoVersionId
        AND detail.TipoDocumentoId = requirement.TipoDocumentoId
        AND detail.Activo = 1
  );

UPDATE observation
SET Resuelta = 1,
    FechaResolucion = SYSUTCDATETIME(),
    UsuarioResolucion = N'MIGRACION_2026_09_08'
FROM sec.ObservacionTramite observation
INNER JOIN sec.TramiteRequisito requirement
    ON requirement.TramiteRequisitoId = observation.TramiteRequisitoId
WHERE observation.TipoObservacion = 'FALTANTE'
  AND observation.EsSistema = 1
  AND observation.Resuelta = 0
  AND (requirement.EsAplicable = 0 OR requirement.EstadoCodigo <> 'FALTANTE');

INSERT sec.ObservacionTramite
    (TramiteId, TramiteRequisitoId, TipoObservacion, Observacion, EsSistema, UsuarioCreacion)
SELECT
    requirement.TramiteId,
    requirement.TramiteRequisitoId,
    'FALTANTE',
    N'Falta cargar y presentar el documento obligatorio: ' + document_type.Nombre + N'.',
    1,
    N'MIGRACION_2026_09_08'
FROM sec.TramiteRequisito requirement
INNER JOIN cat.TipoDocumento document_type ON document_type.TipoDocumentoId = requirement.TipoDocumentoId
WHERE requirement.EsAplicable = 1
  AND requirement.EsObligatorio = 1
  AND requirement.EstadoCodigo = 'FALTANTE'
  AND NOT EXISTS
  (
      SELECT 1
      FROM sec.ObservacionTramite observation
      WHERE observation.TramiteRequisitoId = requirement.TramiteRequisitoId
        AND observation.TipoObservacion = 'FALTANTE'
        AND observation.EsSistema = 1
        AND observation.Resuelta = 0
  );

UPDATE process
SET EstadoTramiteId = process_state.EstadoTramiteId,
    FechaActualizacion = SYSUTCDATETIME(),
    UsuarioActualizacion = N'MIGRACION_2026_09_08'
FROM sec.Tramite process
CROSS APPLY
(
    SELECT
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 THEN 1 ELSE 0 END) AS Total,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 AND requirement.EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END) AS Validados,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EstadoCodigo IN ('OBSERVADO', 'RECHAZADO') THEN 1 ELSE 0 END) AS Observados
    FROM sec.TramiteRequisito requirement
    WHERE requirement.TramiteId = process.TramiteId
) totals
INNER JOIN cat.EstadoTramite process_state
    ON process_state.Codigo = CASE
        WHEN ISNULL(totals.Observados, 0) > 0 THEN 'OBSERVADO'
        WHEN process.TipoMatricula = 'H' AND process.TipoHomologacion IS NULL THEN 'EN_VALIDACION'
        WHEN ISNULL(totals.Total, 0) > 0 AND totals.Total = ISNULL(totals.Validados, 0) THEN 'APROBADO'
        ELSE 'EN_VALIDACION'
    END
WHERE process.Activo = 1;

COMMIT TRANSACTION;
GO

CREATE OR ALTER VIEW rpt.vw_ResumenTramiteDocumental
AS
    SELECT
        process.TramiteId,
        process.CodigoTramite,
        process_type.Codigo AS TipoTramiteCodigo,
        process_state.Codigo AS EstadoTramiteCodigo,
        process_state.Nombre AS EstadoTramite,
        process.CodigoEstud,
        process.NumeroIdentificacion,
        process.ApellidosNombres,
        process.CodigoCarrera,
        process.NombreCarrera,
        process.CodigoPeriodo,
        process.NombrePeriodo,
        process.TipoMatricula,
        process.TipoHomologacion,
        process.EtapaAcademica,
        process.MateriasAprobadas,
        process.MateriasRequeridas,
        process.PorcentajeMalla,
        process.PromedioAprobadas,
        process.FechaGrado,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 THEN 1 ELSE 0 END) AS RequisitosObligatorios,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 AND requirement.EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END) AS RequisitosValidados,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 AND requirement.EstadoCodigo = 'FALTANTE' THEN 1 ELSE 0 END) AS RequisitosFaltantes,
        SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EstadoCodigo IN ('OBSERVADO', 'RECHAZADO') THEN 1 ELSE 0 END) AS RequisitosObservados,
        CAST(CASE
            WHEN SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 THEN 1 ELSE 0 END) = 0 THEN 0
            ELSE 100.0 * SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 AND requirement.EstadoCodigo = 'VALIDADO' THEN 1 ELSE 0 END)
                / SUM(CASE WHEN requirement.EsAplicable = 1 AND requirement.EsObligatorio = 1 THEN 1 ELSE 0 END)
        END AS decimal(5,2)) AS PorcentajeDocumental,
        process.FechaApertura,
        process.FechaActualizacion
    FROM sec.Tramite process
    INNER JOIN cat.TipoTramite process_type ON process_type.TipoTramiteId = process.TipoTramiteId
    INNER JOIN cat.EstadoTramite process_state ON process_state.EstadoTramiteId = process.EstadoTramiteId
    LEFT JOIN sec.TramiteRequisito requirement ON requirement.TramiteId = process.TramiteId
    WHERE process.Activo = 1
    GROUP BY
        process.TramiteId, process.CodigoTramite, process_type.Codigo,
        process_state.Codigo, process_state.Nombre, process.CodigoEstud,
        process.NumeroIdentificacion, process.ApellidosNombres, process.CodigoCarrera,
        process.NombreCarrera, process.CodigoPeriodo, process.NombrePeriodo,
        process.TipoMatricula, process.TipoHomologacion, process.EtapaAcademica,
        process.MateriasAprobadas, process.MateriasRequeridas, process.PorcentajeMalla,
        process.PromedioAprobadas, process.FechaGrado, process.FechaApertura,
        process.FechaActualizacion;
GO
