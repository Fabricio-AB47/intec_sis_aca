/* ============================================================================
   INTEC - Compatibilidad SisAcademicoV1 para backend/frontend moderno
   Base objetivo: INTECBDD

   Este parche NO elimina, NO reconstruye y NO altera columnas existentes.
   Crea un esquema de lectura/compatibilidad con vistas normalizadas para que
   FastAPI pueda consumir procesos heredados sin depender de paginas WebForms.
   ============================================================================ */

SET NOCOUNT ON;
GO

USE INTECBDD;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'sisv1')
    EXEC(N'CREATE SCHEMA sisv1 AUTHORIZATION dbo');
GO

/* ---------------------------------------------------------------------------
   Personas y seguridad
   --------------------------------------------------------------------------- */
CREATE OR ALTER VIEW sisv1.vw_estudiantes
AS
SELECT
    TRY_CONVERT(BIGINT, E.codigo_estud) AS codigo_estud,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), E.Cedula_Est))) AS cedula,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), E.Apellidos_nombre))) AS estudiante,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), E.Estado))) AS estado_codigo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), ES.ESTADO))) AS estado_nombre,
    TRY_CONVERT(DATE, E.Fecha_Nac) AS fecha_nacimiento,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), E.correo))) AS correo_personal,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), E.correointec))) AS correo_intec,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), E.movil))) AS movil,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), E.telefono))) AS telefono,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), E.ciudad))) AS ciudad,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), E.codprov))) AS provincia_codigo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), E.Canton))) AS canton
FROM dbo.DATOS_ESTUD E
LEFT JOIN dbo.ESTADO ES
    ON UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), ES.IDESTADO)))) =
       UPPER(LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), E.Estado))));
GO

CREATE OR ALTER VIEW sisv1.vw_docentes
AS
SELECT
    TRY_CONVERT(BIGINT, D.codigo_doc) AS codigo_doc,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), D.cedula_doc))) AS cedula,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), D.apellidos_nombre))) AS docente,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), D.correo))) AS correo_institucional,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), D.correop))) AS correo_personal,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), D.telefono))) AS telefono,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), D.movil))) AS movil,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), D.TipoDocente))) AS tipo_docente,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), D.nivelFormacion))) AS nivel_formacion
FROM dbo.DATOSDOCENTE D;
GO

CREATE OR ALTER VIEW sisv1.vw_usuarios
AS
SELECT
    TRY_CONVERT(BIGINT, U.Codigo_Usuario) AS codigo_usuario,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), U.login))) AS login,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), U.cedula))) AS cedula,
    TRY_CONVERT(INT, U.tipo_usuario) AS tipo_usuario,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), U.Estado))) AS estado,
    TRY_CONVERT(DATETIME, U.fecha_ingreso) AS fecha_ingreso,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), U.Descripcion))) AS descripcion
FROM dbo.USUARIOS U;
GO

/* ---------------------------------------------------------------------------
   Academico: carreras, periodos, pensum, matricula y notas
   --------------------------------------------------------------------------- */
CREATE OR ALTER VIEW sisv1.vw_carreras
AS
SELECT
    TRY_CONVERT(BIGINT, C.Cod_AnioBasica) AS cod_anio_basica,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), C.Nombre_Basica))) AS carrera,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), C.tp_escuela))) AS escuela_codigo
FROM dbo.CARRERAS C;
GO

CREATE OR ALTER VIEW sisv1.vw_periodos
AS
SELECT
    TRY_CONVERT(BIGINT, P.cod_periodo) AS codigo_periodo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), P.Detalle_Periodo))) AS periodo,
    TRY_CONVERT(DATE, P.FechaInicio) AS fecha_inicio,
    TRY_CONVERT(DATE, P.FechaFinal) AS fecha_fin,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), P.Estado))) AS estado,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), P.TipoMatricula))) AS tipo_matricula
FROM dbo.PERIODO P;
GO

CREATE OR ALTER VIEW sisv1.vw_pensum
AS
SELECT
    TRY_CONVERT(BIGINT, P.codigo_materia) AS codigo_materia,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), P.cod_materia))) AS cod_materia,
    TRY_CONVERT(BIGINT, P.Cod_AnioBasica) AS cod_anio_basica,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), P.Nomb_Materia))) AS materia,
    TRY_CONVERT(INT, P.Semestre) AS nivel,
    TRY_CONVERT(DECIMAL(10,2), P.Creditos) AS creditos,
    TRY_CONVERT(DECIMAL(10,2), P.Horas) AS horas,
    TRY_CONVERT(INT, P.NumMalla) AS malla,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), P.estado_mat))) AS estado
FROM dbo.PENSUM P;
GO

CREATE OR ALTER VIEW sisv1.vw_matricula_materias
AS
SELECT
    TRY_CONVERT(BIGINT, CE.codigo_estud) AS codigo_estud,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), DE.Cedula_Est))) AS cedula,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), DE.Apellidos_nombre))) AS estudiante,
    TRY_CONVERT(BIGINT, CE.cod_anio_Basica) AS cod_anio_basica,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), C.Nombre_Basica))) AS carrera,
    TRY_CONVERT(BIGINT, CE.codigo_periodo) AS codigo_periodo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), PE.Detalle_Periodo))) AS periodo,
    TRY_CONVERT(BIGINT, CE.codigo_materia) AS codigo_materia,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), P.Nomb_Materia))) AS materia,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), PE.TipoMatricula))) AS tipo_matricula,
    TRY_CONVERT(DECIMAL(10,2), CE.Nota1) AS nota1,
    TRY_CONVERT(DECIMAL(10,2), CE.Nota2) AS nota2,
    TRY_CONVERT(DECIMAL(10,2), CE.Nota3) AS nota3,
    TRY_CONVERT(DECIMAL(10,2), CE.teoriaHomo) AS teoria_homo,
    TRY_CONVERT(DECIMAL(10,2), CE.practicahomo) AS practica_homo,
    TRY_CONVERT(DECIMAL(10,2), CE.PromedioFinal) AS promedio_final,
    CASE
        WHEN TRY_CONVERT(DECIMAL(10,2), CE.PromedioFinal) >= 7 THEN CAST(1 AS BIT)
        ELSE CAST(0 AS BIT)
    END AS aprobado
FROM dbo.CARRERAXESTUD CE
LEFT JOIN dbo.DATOS_ESTUD DE
    ON TRY_CONVERT(BIGINT, DE.codigo_estud) = TRY_CONVERT(BIGINT, CE.codigo_estud)
LEFT JOIN dbo.CARRERAS C
    ON TRY_CONVERT(BIGINT, C.Cod_AnioBasica) = TRY_CONVERT(BIGINT, CE.cod_anio_Basica)
LEFT JOIN dbo.PERIODO PE
    ON TRY_CONVERT(BIGINT, PE.cod_periodo) = TRY_CONVERT(BIGINT, CE.codigo_periodo)
LEFT JOIN dbo.PENSUM P
    ON TRY_CONVERT(BIGINT, P.codigo_materia) = TRY_CONVERT(BIGINT, CE.codigo_materia);
GO

/* ---------------------------------------------------------------------------
   Admision, pagos y documentos
   --------------------------------------------------------------------------- */
CREATE OR ALTER VIEW sisv1.vw_preinscripciones
AS
SELECT
    TRY_CONVERT(BIGINT, P.Codestu) AS codigo_estud,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), P.Cedula))) AS cedula,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), P.Apellidos_nombre))) AS estudiante,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(200), P.correo))) AS correo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), P.telefono))) AS telefono,
    TRY_CONVERT(BIGINT, P.codigo_periodo) AS codigo_periodo,
    TRY_CONVERT(BIGINT, P.Cod_AnioBasica) AS cod_anio_basica,
    TRY_CONVERT(DATETIME, P.Fecha_Ingreso) AS fecha_ingreso,
    TRY_CONVERT(BIGINT, P.codasesor) AS codigo_asesor
FROM dbo.PREINSCRIPCION P;
GO

CREATE OR ALTER VIEW sisv1.vw_pagos
AS
SELECT
    TRY_CONVERT(BIGINT, R.Num) AS numero,
    TRY_CONVERT(BIGINT, R.Codestu) AS codigo_estud,
    TRY_CONVERT(BIGINT, R.codperiodo) AS codigo_periodo,
    TRY_CONVERT(DATE, R.fechapago) AS fecha_pago,
    TRY_CONVERT(DECIMAL(18,2), R.Valor) AS valor,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), R.Numerodocumento))) AS numero_documento,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), R.Estado))) AS estado,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), R.Observacion))) AS observacion
FROM dbo.REGISTROPAGOS R;
GO

CREATE OR ALTER VIEW sisv1.vw_documentos_estudiante
AS
SELECT
    TRY_CONVERT(BIGINT, D.num) AS documento_id,
    TRY_CONVERT(BIGINT, D.IDESTUD) AS codigo_estud,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), D.DETALLE))) AS detalle,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), D.LINKURL))) AS archivo
FROM dbo.REGISTRODOCESTUD D;
GO

/* ---------------------------------------------------------------------------
   Practicas, vinculacion y empresas
   --------------------------------------------------------------------------- */
CREATE OR ALTER VIEW sisv1.vw_practicas_preprofesionales
AS
SELECT
    TRY_CONVERT(BIGINT, P.num) AS practica_id,
    TRY_CONVERT(BIGINT, P.codigo_estud) AS codigo_estud,
    TRY_CONVERT(BIGINT, P.cod_anio_Basica) AS cod_anio_basica,
    TRY_CONVERT(BIGINT, P.codigo_periodo) AS codigo_periodo,
    TRY_CONVERT(DATE, P.FechaInicio) AS fecha_inicio,
    TRY_CONVERT(DATE, P.FechaFinal) AS fecha_fin,
    TRY_CONVERT(DECIMAL(10,2), P.NoHoras) AS horas,
    TRY_CONVERT(BIGINT, P.CodDocente) AS codigo_docente,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(MAX), P.DetalleProyecto))) AS detalle,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), P.pathAr))) AS archivo
FROM dbo.PRACTICASPROFESIONALES P;
GO

CREATE OR ALTER VIEW sisv1.vw_vinculacion_sociedad
AS
SELECT
    TRY_CONVERT(BIGINT, V.num) AS vinculacion_id,
    TRY_CONVERT(BIGINT, V.codigo_estud) AS codigo_estud,
    TRY_CONVERT(BIGINT, V.cod_anio_Basica) AS cod_anio_basica,
    TRY_CONVERT(BIGINT, V.codigo_periodo) AS codigo_periodo,
    TRY_CONVERT(DATE, V.FechaInicio) AS fecha_inicio,
    TRY_CONVERT(DATE, V.FechaFinal) AS fecha_fin,
    TRY_CONVERT(DECIMAL(10,2), V.NoHoras) AS horas,
    TRY_CONVERT(BIGINT, V.CodDocente) AS codigo_docente,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(MAX), V.DetalleProyecto))) AS detalle,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), V.pathAr))) AS archivo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(500), V.NombreProyecto))) AS proyecto
FROM dbo.PRACTICASVINCULACION V;
GO

/* ---------------------------------------------------------------------------
   Educacion continua, certificados e integraciones
   --------------------------------------------------------------------------- */
CREATE OR ALTER VIEW sisv1.vw_cursos_educacion_continua
AS
SELECT
    TRY_CONVERT(BIGINT, C.CodCurso) AS codigo_curso,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(250), C.Curso))) AS curso,
    TRY_CONVERT(DATE, C.FechaInicio) AS fecha_inicio,
    TRY_CONVERT(DATE, C.FechaFinal) AS fecha_fin,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(20), C.Estado))) AS estado,
    TRY_CONVERT(DECIMAL(10,2), C.Horas) AS horas
FROM dbo.CursosEduContinua C;
GO

CREATE OR ALTER VIEW sisv1.vw_certificados_generados
AS
SELECT
    TRY_CONVERT(BIGINT, C.CertificadoId) AS certificado_id,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), C.TipoCertificado))) AS tipo_certificado,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), C.TipoOrigen))) AS tipo_origen,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), C.NumeroCertificado))) AS numero_certificado,
    TRY_CONVERT(BIGINT, C.CodigoEstud) AS codigo_estud,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), C.CedulaEst))) AS cedula,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(300), C.ApellidosNombre))) AS estudiante,
    TRY_CONVERT(DATETIME2(0), C.FechaGeneracion) AS fecha_generacion,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(1000), C.RutaArchivo))) AS archivo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), C.CodigoVerificacion))) AS codigo_verificacion,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(30), C.Estado))) AS estado
FROM dbo.CERTIFICADOS_GENERADOS C;
GO

CREATE OR ALTER VIEW sisv1.vw_moodle_notas
AS
SELECT
    TRY_CONVERT(BIGINT, N.id) AS nota_id,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), N.codigo_estudiante))) AS codigo_estudiante,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), N.periodo))) AS periodo,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), N.codigo_materia))) AS codigo_materia,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(100), N.componente_nota))) AS componente,
    TRY_CONVERT(DECIMAL(10,2), N.nota_obtenida) AS nota_obtenida,
    TRY_CONVERT(DECIMAL(10,2), N.nota_maxima) AS nota_maxima,
    TRY_CONVERT(DECIMAL(10,2), N.porcentaje) AS porcentaje,
    LTRIM(RTRIM(TRY_CONVERT(NVARCHAR(50), N.estado))) AS estado,
    TRY_CONVERT(DATETIME2, N.fecha_sincronizacion) AS fecha_sincronizacion
FROM dbo.intec_estudiantenota N;
GO

SELECT 'Parche sisv1 de compatibilidad creado/actualizado correctamente.' AS Resultado;
GO

