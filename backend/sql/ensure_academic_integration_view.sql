CREATE OR ALTER VIEW dbo.vw_EstadoAcademicoIntegracion
AS
WITH Malla AS
(
    SELECT
        CONVERT(NVARCHAR(50), p.Cod_AnioBasica) COLLATE Modern_Spanish_CI_AS AS CodigoCarrera,
        COUNT(DISTINCT p.codigo_materia) AS TotalMateriasMalla
    FROM dbo.PENSUM p
    GROUP BY CONVERT(NVARCHAR(50), p.Cod_AnioBasica) COLLATE Modern_Spanish_CI_AS
),
Notas AS
(
    SELECT
        TRY_CONVERT(BIGINT, cxe.codigo_estud) AS CodigoEstud,
        CONVERT(NVARCHAR(50), cxe.cod_anio_Basica) COLLATE Modern_Spanish_CI_AS AS CodigoCarrera,
        CONVERT(NVARCHAR(50), MAX(cxe.codigo_periodo)) COLLATE Modern_Spanish_CI_AS AS CodigoPeriodo,
        COUNT(DISTINCT CASE
            WHEN UPPER(LTRIM(RTRIM(ISNULL(CONVERT(VARCHAR(10), cxe.ControlAprueba), '')))) = 'A'
              OR COALESCE(cxe.PromedioFinal, cxe.PromedioAux, cxe.Promedio, 0) >= COALESCE(per.NotaAprobar, 7)
            THEN cxe.codigo_materia END) AS TotalMateriasAprobadas,
        CONVERT(DECIMAL(10,2), AVG(CASE
            WHEN COALESCE(cxe.PromedioFinal, cxe.PromedioAux, cxe.Promedio) IS NOT NULL
            THEN CONVERT(DECIMAL(10,4), COALESCE(cxe.PromedioFinal, cxe.PromedioAux, cxe.Promedio)) END)) AS PromedioCarrera
    FROM dbo.CARRERAXESTUD cxe
    LEFT JOIN dbo.PERIODO per ON per.cod_periodo = cxe.codigo_periodo
    GROUP BY cxe.codigo_estud, cxe.cod_anio_Basica
)
SELECT
    n.CodigoEstud,
    CONVERT(VARCHAR(30), de.Cedula_Est) COLLATE Modern_Spanish_CI_AS AS NumeroIdentificacion,
    CONVERT(NVARCHAR(250), de.Apellidos_nombre) COLLATE Modern_Spanish_CI_AS AS NombreCompleto,
    n.CodigoCarrera,
    CONVERT(NVARCHAR(250), ca.Nombre_Basica) COLLATE Modern_Spanish_CI_AS AS NombreCarrera,
    n.CodigoPeriodo,
    ISNULL(m.TotalMateriasMalla, 0) AS TotalMateriasMalla,
    ISNULL(n.TotalMateriasAprobadas, 0) AS TotalMateriasAprobadas,
    CONVERT(BIT, CASE
        WHEN ISNULL(m.TotalMateriasMalla, 0) > 0
         AND ISNULL(n.TotalMateriasAprobadas, 0) >= m.TotalMateriasMalla
        THEN 1 ELSE 0 END) AS MallaCumple,
    n.PromedioCarrera
FROM Notas n
INNER JOIN dbo.DATOS_ESTUD de ON TRY_CONVERT(BIGINT, de.codigo_estud) = n.CodigoEstud
LEFT JOIN Malla m ON m.CodigoCarrera = n.CodigoCarrera
LEFT JOIN dbo.CARRERAS ca
    ON CONVERT(NVARCHAR(50), ca.Cod_AnioBasica) COLLATE Modern_Spanish_CI_AS = n.CodigoCarrera;
