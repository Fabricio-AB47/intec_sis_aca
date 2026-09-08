USE [INTEC_SECRETARIA_GENERAL];
GO

SET XACT_ABORT ON;
GO

IF COL_LENGTH(N'sec.Tramite', N'TipoMatricula') IS NULL
    ALTER TABLE sec.Tramite
        ADD TipoMatricula char(1) NOT NULL
            CONSTRAINT DF_Tramite_TipoMatricula DEFAULT ('R') WITH VALUES;
GO

UPDATE sec.Tramite
   SET TipoMatricula = 'H'
WHERE TipoMatricula <> 'H'
  AND
  (
      UPPER(ISNULL(NombrePeriodo, N'')) LIKE N'%HOMO%'
      OR UPPER(ISNULL(CodigoPeriodo, N'')) LIKE N'H%'
  );
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'sec.Tramite')
      AND name = N'CK_Tramite_TipoMatricula'
)
    ALTER TABLE sec.Tramite WITH CHECK ADD CONSTRAINT CK_Tramite_TipoMatricula CHECK (TipoMatricula IN ('R', 'H'));
GO

IF COL_LENGTH(N'doc.DocumentoPresentado', N'UsuarioCargaOrigen') IS NULL
    ALTER TABLE doc.DocumentoPresentado ADD UsuarioCargaOrigen nvarchar(256) NULL;
GO

MERGE cat.TipoDocumento AS target
USING (VALUES
    ('CEDULA', N'Cédula de identidad', N'Documento de identidad vigente.'),
    ('TITULO_BACHILLER', N'Título de bachiller', N'Requisito académico de ingreso.'),
    ('CERTIFICADO_NO_ADEUDAMIENTO', N'Certificado de no adeudamiento', N'Certificación institucional de obligaciones económicas cumplidas.'),
    ('RECORD_ACADEMICO_FIRMADO', N'Récord académico firmado', N'Registro consolidado de calificaciones con las firmas responsables.'),
    ('CERTIFICADO_PRACTICAS', N'Certificado de prácticas preprofesionales', N'Evidencia de cumplimiento de prácticas.'),
    ('CERTIFICADO_VINCULACION', N'Certificado de vinculación con la sociedad', N'Evidencia de cumplimiento de vinculación.'),
    ('ACTA_GRADO', N'Acta de grado', N'Acta oficial emitida al concluir el proceso de titulación.'),
    ('TITULO_INTEC', N'Título INTEC', N'Título institucional emitido.'),
    ('TITULO_SENESCYT', N'Registro o título SENESCYT', N'Evidencia del registro externo del título.')
) AS source(Codigo, Nombre, Descripcion)
ON target.Codigo = source.Codigo
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = 1
WHEN NOT MATCHED THEN INSERT (Codigo, Nombre, Descripcion) VALUES (source.Codigo, source.Nombre, source.Descripcion);
GO

DECLARE @TipoTramiteId int = (SELECT TipoTramiteId FROM cat.TipoTramite WHERE Codigo = 'REVISION_EXPEDIENTE_GRADO');
DECLARE @VersionId int =
(
    SELECT TOP (1) PlantillaRequisitoVersionId
    FROM cat.PlantillaRequisitoVersion
    WHERE TipoTramiteId = @TipoTramiteId AND Activo = 1
    ORDER BY VigenteDesde DESC, PlantillaRequisitoVersionId DESC
);

MERGE cat.PlantillaRequisitoDetalle AS target
USING
(
    SELECT @VersionId, document_type.TipoDocumentoId, requirement.EsObligatorio,
           requirement.AplicaProximo, requirement.AplicaEgresado,
           requirement.AplicaGraduado, requirement.Orden, requirement.Instruccion
    FROM (VALUES
        ('CEDULA', 1, 1, 1, 1, 10, N'Presentar una copia legible y vigente.'),
        ('TITULO_BACHILLER', 1, 1, 1, 1, 20, N'Validar el título de bachiller registrado.'),
        ('CERTIFICADO_NO_ADEUDAMIENTO', 1, 1, 1, 1, 30, N'Presentar el certificado institucional vigente de no adeudamiento.'),
        ('RECORD_ACADEMICO_FIRMADO', 1, 1, 1, 1, 40, N'Presentar el récord académico completo y firmado por los responsables.'),
        ('CERTIFICADO_PRACTICAS', 1, 1, 1, 1, 50, N'Validar el cierre aprobado de prácticas preprofesionales.'),
        ('CERTIFICADO_VINCULACION', 1, 1, 1, 1, 60, N'Validar el cierre aprobado de vinculación con la sociedad.'),
        ('ACTA_GRADO', 1, 0, 0, 1, 70, N'Validar el acta oficial de grado.'),
        ('TITULO_INTEC', 1, 0, 0, 1, 80, N'Validar el título institucional emitido.'),
        ('TITULO_SENESCYT', 1, 0, 0, 1, 90, N'Validar el registro del título en SENESCYT.')
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
  AND document_type.Codigo = 'RECORD_ACADEMICO';

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
        WHEN process.TipoMatricula = 'R'
         AND document_type.Codigo IN ('CEDULA', 'TITULO_BACHILLER', 'CERTIFICADO_NO_ADEUDAMIENTO', 'RECORD_ACADEMICO_FIRMADO') THEN 1
        WHEN process.TipoMatricula = 'R' THEN 0
        WHEN process.EtapaAcademica = 'PROXIMO' THEN detail.AplicaProximo
        WHEN process.EtapaAcademica = 'EGRESADO' THEN detail.AplicaEgresado
        ELSE detail.AplicaGraduado
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
SET EsAplicable = applicability.EsAplicable,
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
        WHEN process.TipoMatricula = 'R'
         AND document_type.Codigo IN ('CEDULA', 'TITULO_BACHILLER', 'CERTIFICADO_NO_ADEUDAMIENTO', 'RECORD_ACADEMICO_FIRMADO') THEN 1
        WHEN process.TipoMatricula = 'R' THEN 0
        WHEN process.EtapaAcademica = 'PROXIMO' THEN detail.AplicaProximo
        WHEN process.EtapaAcademica = 'EGRESADO' THEN detail.AplicaEgresado
        ELSE detail.AplicaGraduado
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
        process.TipoMatricula, process.EtapaAcademica, process.MateriasAprobadas,
        process.MateriasRequeridas, process.PorcentajeMalla, process.PromedioAprobadas,
        process.FechaGrado, process.FechaApertura, process.FechaActualizacion;
GO

USE [INTEC_GRAPH_INTEGRACION];
GO

MERGE cat.TipoExpedienteGraph AS target
USING (VALUES
    ('SECRETARIA', N'Secretaría General', N'Documentos oficiales para la verificación del expediente de grado.', 1)
) AS source(TipoExpedienteGraphCodigo, Nombre, Descripcion, Activo)
ON target.TipoExpedienteGraphCodigo = source.TipoExpedienteGraphCodigo
WHEN MATCHED THEN UPDATE SET Nombre = source.Nombre, Descripcion = source.Descripcion, Activo = source.Activo
WHEN NOT MATCHED THEN INSERT (TipoExpedienteGraphCodigo, Nombre, Descripcion, Activo)
    VALUES (source.TipoExpedienteGraphCodigo, source.Nombre, source.Descripcion, source.Activo);
GO
