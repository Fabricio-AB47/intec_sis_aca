/* ============================================================================
   PARCHE V9 - EVALUADORES VARIABLES Y PROMEDIOS POR RUBRICA
   BASE: TITULACION_INTEC
   OBJETIVO:
   - Permitir 3 jueces o mas por trabajo de titulacion.
   - Calcular promedio final usando todos los evaluadores finalizados.
   - Separar notas de trabajo escrito y defensa oral para DEFENSA_GRADO.
   - Mantener EXAMEN_COMPLEXIVO con trabajo practico.
   - Agregar carga directa de nota final de rubrica por evaluador, ademas de la
     carga detallada por criterios ya existente.
   ============================================================================ */

SET NOCOUNT ON;
GO

USE TITULACION_INTEC;
GO

IF OBJECT_ID(N'tit.TrabajoTitulacion', N'U') IS NULL
    THROW 79000, 'Falta tit.TrabajoTitulacion. Ejecute primero el script maestro V8/V9.', 1;
GO

IF OBJECT_ID(N'eval.EvaluadorTrabajoTitulacion', N'U') IS NULL
    THROW 79001, 'Falta eval.EvaluadorTrabajoTitulacion. Ejecute primero el script maestro V8/V9.', 1;
GO

/* --------------------------------------------------------------------------
   1. PARAMETROS GENERALES DE CALIFICACION
   -------------------------------------------------------------------------- */
MERGE cat.ParametroGeneral AS T
USING (VALUES
    ('MIN_EVALUADORES_TITULACION', N'3', N'Minimo de evaluadores/jueces requeridos por componente de rubrica. Puede subirse a 4, 5 o mas.'),
    ('PERMITE_EVALUADORES_ADICIONALES', N'1', N'Permite agregar evaluadores adicionales al tribunal o al examen complexivo.'),
    ('PESO_DEFENSA_TRABAJO_ESCRITO', N'50', N'Peso porcentual del trabajo escrito dentro del proceso de defensa de grado.'),
    ('PESO_DEFENSA_ORAL', N'50', N'Peso porcentual de la defensa oral dentro del proceso de defensa de grado.'),
    ('PESO_COMPLEXIVO_TRABAJO_PRACTICO', N'100', N'Peso porcentual del trabajo practico dentro del examen complexivo.')
) AS S(Codigo, Valor, Descripcion)
ON T.Codigo COLLATE Modern_Spanish_CI_AS = S.Codigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN
    UPDATE SET Valor = S.Valor,
               Descripcion = S.Descripcion,
               Activo = 1,
               FechaActualizacion = SYSDATETIME()
WHEN NOT MATCHED THEN
    INSERT (Codigo, Valor, Descripcion)
    VALUES (S.Codigo, S.Valor, S.Descripcion);
GO

/* Sincroniza pesos base de componentes con los parametros. */
UPDATE eval.ComponenteEvaluacion
SET PesoDentroProceso = TRY_CONVERT(DECIMAL(10,2), (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'PESO_COMPLEXIVO_TRABAJO_PRACTICO'))
WHERE CodigoComponente = 'COMPLEXIVO_TRABAJO_PRACTICO';

UPDATE eval.ComponenteEvaluacion
SET PesoDentroProceso = TRY_CONVERT(DECIMAL(10,2), (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'PESO_DEFENSA_TRABAJO_ESCRITO'))
WHERE CodigoComponente = 'DEFENSA_TRABAJO_ESCRITO';

UPDATE eval.ComponenteEvaluacion
SET PesoDentroProceso = TRY_CONVERT(DECIMAL(10,2), (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'PESO_DEFENSA_ORAL'))
WHERE CodigoComponente = 'DEFENSA_ORAL';
GO

/* --------------------------------------------------------------------------
   2. ROLES PARA EVALUADORES ADICIONALES
   -------------------------------------------------------------------------- */
MERGE cat.RolResponsableTitulacion AS T
USING (VALUES
    ('EVALUADOR_ADICIONAL_DEFENSA', N'Evaluador adicional de defensa de grado', 'DEFENSA_GRADO', 1, 0, 0, 1),
    ('EVALUADOR_ADICIONAL_COMPLEXIVO', N'Evaluador adicional del examen complexivo', 'EXAMEN_COMPLEXIVO', 1, 0, 0, 1)
) AS S(RolResponsableCodigo, Nombre, AplicaMecanismoCodigo, EsCalificador, EsRevisionTrabajo, EsAutoridad, Activo)
ON T.RolResponsableCodigo COLLATE Modern_Spanish_CI_AS = S.RolResponsableCodigo COLLATE Modern_Spanish_CI_AS
WHEN MATCHED THEN
    UPDATE SET Nombre = S.Nombre,
               AplicaMecanismoCodigo = S.AplicaMecanismoCodigo,
               EsCalificador = S.EsCalificador,
               EsRevisionTrabajo = S.EsRevisionTrabajo,
               EsAutoridad = S.EsAutoridad,
               Activo = S.Activo
WHEN NOT MATCHED THEN
    INSERT (RolResponsableCodigo, Nombre, AplicaMecanismoCodigo, EsCalificador, EsRevisionTrabajo, EsAutoridad, Activo)
    VALUES (S.RolResponsableCodigo, S.Nombre, S.AplicaMecanismoCodigo, S.EsCalificador, S.EsRevisionTrabajo, S.EsAutoridad, S.Activo);
GO

/* --------------------------------------------------------------------------
   3. COLUMNAS NUEVAS PARA MINIMO DE EVALUADORES Y NOTAS SEPARADAS
   -------------------------------------------------------------------------- */
IF COL_LENGTH(N'tit.TrabajoTitulacion', N'MinimoEvaluadoresRequeridos') IS NULL
BEGIN
    ALTER TABLE tit.TrabajoTitulacion
    ADD MinimoEvaluadoresRequeridos INT NULL;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'MinimoEvaluadoresRequeridos') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD MinimoEvaluadoresRequeridos INT NOT NULL CONSTRAINT DF_Consol_MinEvalReq DEFAULT 3;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'CantidadEvaluadoresAsignados') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD CantidadEvaluadoresAsignados INT NOT NULL CONSTRAINT DF_Consol_EvalAsign DEFAULT 0;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'CantidadEvaluadoresMinimosPorComponente') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD CantidadEvaluadoresMinimosPorComponente INT NOT NULL CONSTRAINT DF_Consol_EvalMinComp DEFAULT 0;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'NotaTrabajoPractico10') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD NotaTrabajoPractico10 DECIMAL(10,2) NULL;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'NotaTrabajoEscrito10') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD NotaTrabajoEscrito10 DECIMAL(10,2) NULL;
END;
GO

IF COL_LENGTH(N'eval.ConsolidadoExpediente', N'NotaDefensaOral10') IS NULL
BEGIN
    ALTER TABLE eval.ConsolidadoExpediente
    ADD NotaDefensaOral10 DECIMAL(10,2) NULL;
END;
GO

/* --------------------------------------------------------------------------
   4. INDICES: PERMITEN JUECES ADICIONALES SIN DUPLICAR EL MISMO RESPONSABLE
   -------------------------------------------------------------------------- */
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_EvalTrabajo_Rol_Activo' AND object_id = OBJECT_ID(N'eval.EvaluadorTrabajoTitulacion'))
BEGIN
    DROP INDEX UX_EvalTrabajo_Rol_Activo ON eval.EvaluadorTrabajoTitulacion;
END;
GO

/*
   No se recrea un indice unico por rol porque ahora existen roles adicionales
   que pueden repetirse para admitir 4, 5 o mas jueces.
   La unicidad de roles oficiales se controla en eval.sp_AsignarEvaluadorTrabajo
   y la duplicidad del mismo juez se bloquea con el indice por ResponsableId.
*/
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_EvalTrabajo_RolOficial_Activo' AND object_id = OBJECT_ID(N'eval.EvaluadorTrabajoTitulacion'))
BEGIN
    DROP INDEX UX_EvalTrabajo_RolOficial_Activo ON eval.EvaluadorTrabajoTitulacion;
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_EvalTrabajo_ResponsableCalificador_Activo' AND object_id = OBJECT_ID(N'eval.EvaluadorTrabajoTitulacion'))
BEGIN
    CREATE UNIQUE INDEX UX_EvalTrabajo_ResponsableCalificador_Activo
    ON eval.EvaluadorTrabajoTitulacion(TrabajoTitulacionId, ResponsableId)
    WHERE Activo = 1 AND EsCalificador = 1;
END;
GO

/* --------------------------------------------------------------------------
   5. CONFIGURAR MINIMO DE EVALUADORES POR TRABAJO
   -------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE eval.sp_ConfigurarEvaluadoresTrabajo
    @TrabajoTitulacionId BIGINT,
    @MinimoEvaluadoresRequeridos INT = 3,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @MinimoEvaluadoresRequeridos IS NULL OR @MinimoEvaluadoresRequeridos < 1
        THROW 79100, 'El minimo de evaluadores debe ser mayor o igual a 1.', 1;

    IF NOT EXISTS (SELECT 1 FROM tit.TrabajoTitulacion WHERE TrabajoTitulacionId = @TrabajoTitulacionId AND Activo = 1)
        THROW 79101, 'El trabajo de titulacion no existe o esta inactivo.', 1;

    UPDATE tit.TrabajoTitulacion
    SET MinimoEvaluadoresRequeridos = @MinimoEvaluadoresRequeridos,
        FechaActualizacion = SYSDATETIME(),
        UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId;

    SELECT
        @TrabajoTitulacionId AS TrabajoTitulacionId,
        @MinimoEvaluadoresRequeridos AS MinimoEvaluadoresRequeridos,
        N'Minimo de evaluadores configurado correctamente.' AS Mensaje;
END;
GO

/* --------------------------------------------------------------------------
   6. ASIGNACION DE EVALUADORES: OFICIALES Y ADICIONALES
   -------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE eval.sp_AsignarEvaluadorTrabajo
    @TrabajoTitulacionId BIGINT,
    @ResponsableId BIGINT,
    @RolResponsableCodigo VARCHAR(60),
    @OrdenEvaluador INT = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE
        @Mecanismo VARCHAR(50),
        @Aplica VARCHAR(50),
        @EsCalificador BIT,
        @PermiteMultiple BIT,
        @EvaluadorTrabajoId BIGINT,
        @OrdenFinal INT;

    SELECT @Mecanismo = MecanismoTitulacionCodigo
    FROM tit.TrabajoTitulacion
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId
      AND Activo = 1;

    IF @Mecanismo IS NULL
        THROW 71200, 'El trabajo de titulacion no existe o esta inactivo.', 1;

    SELECT @Aplica = AplicaMecanismoCodigo,
           @EsCalificador = EsCalificador
    FROM cat.RolResponsableTitulacion
    WHERE RolResponsableCodigo = @RolResponsableCodigo COLLATE Modern_Spanish_CI_AS
      AND Activo = 1;

    IF @EsCalificador IS NULL
        THROW 71201, 'El rol del evaluador no existe o esta inactivo.', 1;

    IF @Aplica IS NOT NULL AND @Aplica COLLATE Modern_Spanish_CI_AS <> @Mecanismo COLLATE Modern_Spanish_CI_AS
        THROW 71202, 'El rol no aplica al mecanismo del trabajo.', 1;

    IF NOT EXISTS (SELECT 1 FROM resp.ResponsableTitulacion WHERE ResponsableId = @ResponsableId AND Activo = 1)
        THROW 71203, 'El responsable/evaluador no existe o esta inactivo.', 1;

    SET @PermiteMultiple = CASE
        WHEN @RolResponsableCodigo IN ('EVALUADOR_ADICIONAL_DEFENSA','EVALUADOR_ADICIONAL_COMPLEXIVO') THEN 1
        ELSE 0
    END;

    SELECT @OrdenFinal = COALESCE(@OrdenEvaluador, MAX(OrdenEvaluador) + 1, 1)
    FROM eval.EvaluadorTrabajoTitulacion
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId
      AND Activo = 1;

    IF @PermiteMultiple = 1
    BEGIN
        SELECT TOP 1 @EvaluadorTrabajoId = EvaluadorTrabajoId
        FROM eval.EvaluadorTrabajoTitulacion
        WHERE TrabajoTitulacionId = @TrabajoTitulacionId
          AND ResponsableId = @ResponsableId
          AND RolResponsableCodigo = @RolResponsableCodigo COLLATE Modern_Spanish_CI_AS
          AND Activo = 1;

        IF @EvaluadorTrabajoId IS NULL
        BEGIN
            IF @EsCalificador = 1 AND EXISTS
            (
                SELECT 1
                FROM eval.EvaluadorTrabajoTitulacion
                WHERE TrabajoTitulacionId = @TrabajoTitulacionId
                  AND ResponsableId = @ResponsableId
                  AND Activo = 1
                  AND EsCalificador = 1
            )
                THROW 71204, 'El responsable ya esta asignado como calificador en este trabajo.', 1;

            INSERT INTO eval.EvaluadorTrabajoTitulacion
            (TrabajoTitulacionId, ResponsableId, RolResponsableCodigo, OrdenEvaluador, EsCalificador, UsuarioAsignacion)
            VALUES
            (@TrabajoTitulacionId, @ResponsableId, @RolResponsableCodigo, @OrdenFinal, @EsCalificador, COALESCE(@Usuario, SYSTEM_USER));

            SET @EvaluadorTrabajoId = SCOPE_IDENTITY();
        END
        ELSE
        BEGIN
            UPDATE eval.EvaluadorTrabajoTitulacion
            SET OrdenEvaluador = @OrdenFinal,
                EsCalificador = @EsCalificador,
                UsuarioAsignacion = COALESCE(@Usuario, SYSTEM_USER),
                FechaAsignacion = SYSDATETIME()
            WHERE EvaluadorTrabajoId = @EvaluadorTrabajoId;
        END;
    END
    ELSE
    BEGIN
        SELECT TOP 1 @EvaluadorTrabajoId = EvaluadorTrabajoId
        FROM eval.EvaluadorTrabajoTitulacion
        WHERE TrabajoTitulacionId = @TrabajoTitulacionId
          AND RolResponsableCodigo = @RolResponsableCodigo COLLATE Modern_Spanish_CI_AS
          AND Activo = 1;

        IF @EsCalificador = 1 AND EXISTS
        (
            SELECT 1
            FROM eval.EvaluadorTrabajoTitulacion
            WHERE TrabajoTitulacionId = @TrabajoTitulacionId
              AND ResponsableId = @ResponsableId
              AND Activo = 1
              AND EsCalificador = 1
              AND (@EvaluadorTrabajoId IS NULL OR EvaluadorTrabajoId <> @EvaluadorTrabajoId)
        )
            THROW 71205, 'El responsable ya esta asignado como calificador en este trabajo.', 1;

        IF @EvaluadorTrabajoId IS NULL
        BEGIN
            INSERT INTO eval.EvaluadorTrabajoTitulacion
            (TrabajoTitulacionId, ResponsableId, RolResponsableCodigo, OrdenEvaluador, EsCalificador, UsuarioAsignacion)
            VALUES
            (@TrabajoTitulacionId, @ResponsableId, @RolResponsableCodigo, @OrdenFinal, @EsCalificador, COALESCE(@Usuario, SYSTEM_USER));

            SET @EvaluadorTrabajoId = SCOPE_IDENTITY();
        END
        ELSE
        BEGIN
            UPDATE eval.EvaluadorTrabajoTitulacion
            SET ResponsableId = @ResponsableId,
                OrdenEvaluador = @OrdenFinal,
                EsCalificador = @EsCalificador,
                UsuarioAsignacion = COALESCE(@Usuario, SYSTEM_USER),
                FechaAsignacion = SYSDATETIME()
            WHERE EvaluadorTrabajoId = @EvaluadorTrabajoId;
        END;
    END;

    SELECT
        et.EvaluadorTrabajoId,
        et.TrabajoTitulacionId,
        et.ResponsableId,
        r.NombreResponsable,
        et.RolResponsableCodigo,
        et.OrdenEvaluador,
        et.EsCalificador,
        N'Evaluador/responsable asignado correctamente.' AS Mensaje
    FROM eval.EvaluadorTrabajoTitulacion et
    INNER JOIN resp.ResponsableTitulacion r
        ON r.ResponsableId = et.ResponsableId
    WHERE et.EvaluadorTrabajoId = @EvaluadorTrabajoId;
END;
GO

/* --------------------------------------------------------------------------
   7. CARGA DIRECTA DE NOTA FINAL DE RUBRICA POR EVALUADOR
      Alternativa a la carga detallada por criterios.
   -------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE eval.sp_RegistrarNotaComponenteDirecta
    @ExpedienteId BIGINT,
    @TrabajoTitulacionId BIGINT,
    @CodigoComponente VARCHAR(80),
    @EvaluadorTrabajoId BIGINT,
    @NotaNormalizada10 DECIMAL(10,2) = NULL,
    @NotaComponente15 DECIMAL(10,2) = NULL,
    @Observacion NVARCHAR(1000) = NULL,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE
        @Mecanismo VARCHAR(50),
        @ComponenteId INT,
        @RubricaComponenteId INT,
        @PuntajeMaximoFinal DECIMAL(10,2),
        @CalificacionComponenteId BIGINT;

    IF @NotaNormalizada10 IS NULL AND @NotaComponente15 IS NULL
        THROW 79300, 'Debe ingresar NotaNormalizada10 o NotaComponente15.', 1;

    SELECT @Mecanismo = MecanismoTitulacionCodigo
    FROM tit.TrabajoTitulacion
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId
      AND Activo = 1;

    IF @Mecanismo IS NULL
        THROW 79301, 'El trabajo de titulacion no existe o esta inactivo.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM tit.TrabajoTitulacionIntegrante
        WHERE TrabajoTitulacionId = @TrabajoTitulacionId
          AND ExpedienteId = @ExpedienteId
          AND Activo = 1
    )
        THROW 79302, 'El expediente no pertenece al trabajo de titulacion indicado.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM eval.EvaluadorTrabajoTitulacion
        WHERE EvaluadorTrabajoId = @EvaluadorTrabajoId
          AND TrabajoTitulacionId = @TrabajoTitulacionId
          AND Activo = 1
          AND EsCalificador = 1
    )
        THROW 79303, 'El evaluador no pertenece al trabajo o no es calificador.', 1;

    SELECT TOP 1
        @ComponenteId = ce.ComponenteId,
        @RubricaComponenteId = rc.RubricaComponenteId,
        @PuntajeMaximoFinal = rc.PuntajeMaximoFinal
    FROM eval.ComponenteEvaluacion ce
    INNER JOIN eval.RubricaComponente rc
        ON rc.ComponenteId = ce.ComponenteId
       AND rc.Activo = 1
    WHERE ce.CodigoComponente = @CodigoComponente COLLATE Modern_Spanish_CI_AS
      AND ce.MecanismoTitulacionCodigo = @Mecanismo COLLATE Modern_Spanish_CI_AS
      AND ce.Activo = 1
    ORDER BY rc.RubricaComponenteId DESC;

    IF @ComponenteId IS NULL
        THROW 79304, 'El componente no existe o no aplica al mecanismo del trabajo.', 1;

    IF @NotaNormalizada10 IS NOT NULL AND (@NotaNormalizada10 < 0 OR @NotaNormalizada10 > 10)
        THROW 79305, 'La nota normalizada debe estar entre 0 y 10.', 1;

    IF @NotaComponente15 IS NOT NULL AND (@NotaComponente15 < 0 OR @NotaComponente15 > @PuntajeMaximoFinal)
        THROW 79306, 'La nota del componente no puede ser menor que 0 ni mayor al puntaje maximo de la rubrica.', 1;

    IF @NotaNormalizada10 IS NULL
        SET @NotaNormalizada10 = ROUND((@NotaComponente15 / NULLIF(@PuntajeMaximoFinal, 0)) * 10.0, 2);

    IF @NotaComponente15 IS NULL
        SET @NotaComponente15 = ROUND((@NotaNormalizada10 / 10.0) * @PuntajeMaximoFinal, 2);

    SELECT @CalificacionComponenteId = CalificacionComponenteId
    FROM eval.CalificacionComponenteEvaluador
    WHERE ExpedienteId = @ExpedienteId
      AND ComponenteId = @ComponenteId
      AND EvaluadorTrabajoId = @EvaluadorTrabajoId;

    IF @CalificacionComponenteId IS NULL
    BEGIN
        INSERT INTO eval.CalificacionComponenteEvaluador
        (ExpedienteId, TrabajoTitulacionId, ComponenteId, RubricaComponenteId, EvaluadorTrabajoId, NotaComponente15, NotaNormalizada10, EstadoCalificacion, Observacion, FechaCalificacion, UsuarioCalificacion)
        VALUES
        (@ExpedienteId, @TrabajoTitulacionId, @ComponenteId, @RubricaComponenteId, @EvaluadorTrabajoId, @NotaComponente15, @NotaNormalizada10, 'FINALIZADA', @Observacion, SYSDATETIME(), COALESCE(@Usuario, SYSTEM_USER));

        SET @CalificacionComponenteId = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE eval.CalificacionComponenteEvaluador
        SET TrabajoTitulacionId = @TrabajoTitulacionId,
            RubricaComponenteId = @RubricaComponenteId,
            NotaComponente15 = @NotaComponente15,
            NotaNormalizada10 = @NotaNormalizada10,
            EstadoCalificacion = 'FINALIZADA',
            Observacion = @Observacion,
            FechaCalificacion = SYSDATETIME(),
            UsuarioCalificacion = COALESCE(@Usuario, SYSTEM_USER)
        WHERE CalificacionComponenteId = @CalificacionComponenteId;
    END;

    SELECT
        @CalificacionComponenteId AS CalificacionComponenteId,
        @CodigoComponente AS CodigoComponente,
        @NotaComponente15 AS NotaComponente15,
        @NotaNormalizada10 AS NotaNormalizada10,
        N'Nota final de rubrica registrada correctamente.' AS Mensaje;
END;
GO

CREATE OR ALTER PROCEDURE eval.sp_RegistrarNotasDefensaPorEvaluador
    @ExpedienteId BIGINT,
    @TrabajoTitulacionId BIGINT,
    @EvaluadorTrabajoId BIGINT,
    @NotaTrabajoEscrito10 DECIMAL(10,2),
    @NotaDefensaOral10 DECIMAL(10,2),
    @Usuario NVARCHAR(128) = NULL,
    @Observacion NVARCHAR(1000) = NULL,
    @RecalcularConsolidado BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM tit.TrabajoTitulacion
        WHERE TrabajoTitulacionId = @TrabajoTitulacionId
          AND MecanismoTitulacionCodigo = 'DEFENSA_GRADO'
          AND Activo = 1
    )
        THROW 79350, 'El trabajo indicado no corresponde a DEFENSA_GRADO.', 1;

    EXEC eval.sp_RegistrarNotaComponenteDirecta
        @ExpedienteId = @ExpedienteId,
        @TrabajoTitulacionId = @TrabajoTitulacionId,
        @CodigoComponente = 'DEFENSA_TRABAJO_ESCRITO',
        @EvaluadorTrabajoId = @EvaluadorTrabajoId,
        @NotaNormalizada10 = @NotaTrabajoEscrito10,
        @Observacion = @Observacion,
        @Usuario = @Usuario;

    EXEC eval.sp_RegistrarNotaComponenteDirecta
        @ExpedienteId = @ExpedienteId,
        @TrabajoTitulacionId = @TrabajoTitulacionId,
        @CodigoComponente = 'DEFENSA_ORAL',
        @EvaluadorTrabajoId = @EvaluadorTrabajoId,
        @NotaNormalizada10 = @NotaDefensaOral10,
        @Observacion = @Observacion,
        @Usuario = @Usuario;

    IF @RecalcularConsolidado = 1
    BEGIN
        EXEC eval.sp_CalcularConsolidadoExpediente
            @ExpedienteId = @ExpedienteId,
            @Usuario = @Usuario;
    END;
END;
GO

CREATE OR ALTER PROCEDURE eval.sp_RegistrarNotaComplexivoPorEvaluador
    @ExpedienteId BIGINT,
    @TrabajoTitulacionId BIGINT,
    @EvaluadorTrabajoId BIGINT,
    @NotaTrabajoPractico10 DECIMAL(10,2),
    @Usuario NVARCHAR(128) = NULL,
    @Observacion NVARCHAR(1000) = NULL,
    @RecalcularConsolidado BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM tit.TrabajoTitulacion
        WHERE TrabajoTitulacionId = @TrabajoTitulacionId
          AND MecanismoTitulacionCodigo = 'EXAMEN_COMPLEXIVO'
          AND Activo = 1
    )
        THROW 79360, 'El trabajo indicado no corresponde a EXAMEN_COMPLEXIVO.', 1;

    EXEC eval.sp_RegistrarNotaComponenteDirecta
        @ExpedienteId = @ExpedienteId,
        @TrabajoTitulacionId = @TrabajoTitulacionId,
        @CodigoComponente = 'COMPLEXIVO_TRABAJO_PRACTICO',
        @EvaluadorTrabajoId = @EvaluadorTrabajoId,
        @NotaNormalizada10 = @NotaTrabajoPractico10,
        @Observacion = @Observacion,
        @Usuario = @Usuario;

    IF @RecalcularConsolidado = 1
    BEGIN
        EXEC eval.sp_CalcularConsolidadoExpediente
            @ExpedienteId = @ExpedienteId,
            @Usuario = @Usuario;
    END;
END;
GO

/* --------------------------------------------------------------------------
   8. CONSOLIDADO VARIABLE: PROMEDIA TODOS LOS JUECES FINALIZADOS
   -------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE eval.sp_CalcularConsolidadoExpediente
    @ExpedienteId BIGINT,
    @Usuario NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE
        @TrabajoTitulacionId BIGINT,
        @Mecanismo VARCHAR(50),
        @PromedioAsignaturas DECIMAL(10,2),
        @Nota80 DECIMAL(10,2),
        @ReqComp INT,
        @CompCompletos INT,
        @EvalMax INT,
        @EvalMin INT,
        @EvalAsignados INT,
        @RevisionOK BIT,
        @MinEval INT,
        @FactorProm DECIMAL(10,4),
        @FactorTit DECIMAL(10,4),
        @NotaPractico15 DECIMAL(10,2),
        @NotaEscrito15 DECIMAL(10,2),
        @NotaOral15 DECIMAL(10,2),
        @NotaPractico10 DECIMAL(10,2),
        @NotaEscrito10 DECIMAL(10,2),
        @NotaOral10 DECIMAL(10,2),
        @Proceso10 DECIMAL(10,2),
        @Proceso20 DECIMAL(10,2),
        @Final DECIMAL(10,2),
        @RubricasCompletas BIT;

    SELECT TOP 1
        @TrabajoTitulacionId = ti.TrabajoTitulacionId,
        @Mecanismo = tt.MecanismoTitulacionCodigo,
        @MinEval = COALESCE(tt.MinimoEvaluadoresRequeridos, TRY_CONVERT(INT, (SELECT Valor FROM cat.ParametroGeneral WHERE Codigo = 'MIN_EVALUADORES_TITULACION')), 3)
    FROM tit.TrabajoTitulacionIntegrante ti
    INNER JOIN tit.TrabajoTitulacion tt
        ON tt.TrabajoTitulacionId = ti.TrabajoTitulacionId
    WHERE ti.ExpedienteId = @ExpedienteId
      AND ti.Activo = 1
      AND tt.Activo = 1
    ORDER BY ti.TrabajoIntegranteId DESC;

    IF @TrabajoTitulacionId IS NULL
        THROW 71400, 'El expediente no tiene trabajo de titulacion asociado.', 1;

    IF @MinEval IS NULL OR @MinEval < 1
        SET @MinEval = 3;

    SELECT @PromedioAsignaturas = PromedioAsignaturas
    FROM tit.ExpedienteTitulacion
    WHERE ExpedienteId = @ExpedienteId;

    SELECT @FactorProm = ISNULL(TRY_CONVERT(DECIMAL(10,4), Valor), 0.80)
    FROM cat.ParametroGeneral
    WHERE Codigo = 'FACTOR_PROMEDIO_ASIGNATURAS';

    SELECT @FactorTit = ISNULL(TRY_CONVERT(DECIMAL(10,4), Valor), 0.20)
    FROM cat.ParametroGeneral
    WHERE Codigo = 'FACTOR_PROCESO_TITULACION';

    SET @FactorProm = ISNULL(@FactorProm, 0.80);
    SET @FactorTit = ISNULL(@FactorTit, 0.20);
    SET @Nota80 = ROUND(ISNULL(@PromedioAsignaturas, 0) * @FactorProm, 2);

    SELECT @ReqComp = COUNT(1)
    FROM eval.ComponenteEvaluacion
    WHERE MecanismoTitulacionCodigo = @Mecanismo COLLATE Modern_Spanish_CI_AS
      AND Activo = 1;

    SELECT @EvalAsignados = COUNT(1)
    FROM eval.EvaluadorTrabajoTitulacion
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId
      AND Activo = 1
      AND EsCalificador = 1;

    ;WITH comp AS
    (
        SELECT
            ce.ComponenteId,
            ce.CodigoComponente,
            ce.PesoDentroProceso,
            COUNT(DISTINCT cce.EvaluadorTrabajoId) AS EvalFinalizados,
            AVG(CAST(cce.NotaComponente15 AS DECIMAL(18,4))) AS Promedio15,
            AVG(CAST(cce.NotaNormalizada10 AS DECIMAL(18,4))) AS Promedio10
        FROM eval.ComponenteEvaluacion ce
        LEFT JOIN eval.CalificacionComponenteEvaluador cce
            ON cce.ComponenteId = ce.ComponenteId
           AND cce.ExpedienteId = @ExpedienteId
           AND cce.TrabajoTitulacionId = @TrabajoTitulacionId
           AND cce.EstadoCalificacion = 'FINALIZADA'
        WHERE ce.MecanismoTitulacionCodigo = @Mecanismo COLLATE Modern_Spanish_CI_AS
          AND ce.Activo = 1
        GROUP BY ce.ComponenteId, ce.CodigoComponente, ce.PesoDentroProceso
    )
    SELECT
        @CompCompletos = SUM(CASE WHEN EvalFinalizados >= @MinEval THEN 1 ELSE 0 END),
        @EvalMax = MAX(EvalFinalizados),
        @EvalMin = MIN(EvalFinalizados),
        @NotaPractico15 = MAX(CASE WHEN CodigoComponente = 'COMPLEXIVO_TRABAJO_PRACTICO' THEN ROUND(Promedio15, 2) END),
        @NotaEscrito15 = MAX(CASE WHEN CodigoComponente = 'DEFENSA_TRABAJO_ESCRITO' THEN ROUND(Promedio15, 2) END),
        @NotaOral15 = MAX(CASE WHEN CodigoComponente = 'DEFENSA_ORAL' THEN ROUND(Promedio15, 2) END),
        @NotaPractico10 = MAX(CASE WHEN CodigoComponente = 'COMPLEXIVO_TRABAJO_PRACTICO' THEN ROUND(Promedio10, 2) END),
        @NotaEscrito10 = MAX(CASE WHEN CodigoComponente = 'DEFENSA_TRABAJO_ESCRITO' THEN ROUND(Promedio10, 2) END),
        @NotaOral10 = MAX(CASE WHEN CodigoComponente = 'DEFENSA_ORAL' THEN ROUND(Promedio10, 2) END),
        @Proceso10 = ROUND(SUM(CASE WHEN EvalFinalizados >= @MinEval THEN ISNULL(Promedio10, 0) * PesoDentroProceso / 100.0 ELSE 0 END), 2)
    FROM comp;

    SET @CompCompletos = ISNULL(@CompCompletos, 0);
    SET @EvalMax = ISNULL(@EvalMax, 0);
    SET @EvalMin = ISNULL(@EvalMin, 0);
    SET @RubricasCompletas = CASE WHEN @ReqComp = @CompCompletos AND @ReqComp > 0 THEN 1 ELSE 0 END;

    SELECT @RevisionOK = CASE WHEN EstadoRevision = 'APROBADO' OR @Mecanismo = 'EXAMEN_COMPLEXIVO' THEN 1 ELSE 0 END
    FROM tit.TrabajoTitulacion
    WHERE TrabajoTitulacionId = @TrabajoTitulacionId;

    SET @Proceso20 = ROUND(ISNULL(@Proceso10, 0) * @FactorTit, 2);
    SET @Final = ROUND(@Nota80 + @Proceso20, 2);

    MERGE eval.ConsolidadoExpediente AS tgt
    USING (SELECT @ExpedienteId AS ExpedienteId) AS src
    ON tgt.ExpedienteId = src.ExpedienteId
    WHEN MATCHED THEN
        UPDATE SET TrabajoTitulacionId = @TrabajoTitulacionId,
                   MecanismoTitulacionCodigo = @Mecanismo,
                   NotaTrabajoPractico15 = @NotaPractico15,
                   NotaTrabajoEscrito15 = @NotaEscrito15,
                   NotaDefensaOral15 = @NotaOral15,
                   NotaTrabajoPractico10 = @NotaPractico10,
                   NotaTrabajoEscrito10 = @NotaEscrito10,
                   NotaDefensaOral10 = @NotaOral10,
                   NotaProcesoSobre10 = @Proceso10,
                   NotaProcesoTitulacion20 = @Proceso20,
                   PromedioAsignaturas = @PromedioAsignaturas,
                   NotaPromedioAsignaturas80 = @Nota80,
                   NotaFinalGrado = @Final,
                   CantidadEvaluadoresCalificadores = @EvalMax,
                   CantidadEvaluadoresAsignados = ISNULL(@EvalAsignados, 0),
                   CantidadEvaluadoresMinimosPorComponente = @EvalMin,
                   MinimoEvaluadoresRequeridos = @MinEval,
                   CantidadComponentesRequeridos = @ReqComp,
                   CantidadComponentesCompletos = @CompCompletos,
                   RubricasCompletas = @RubricasCompletas,
                   RevisionTrabajoAprobada = ISNULL(@RevisionOK, 0),
                   EstadoConsolidado = CASE WHEN @RubricasCompletas = 1 AND ISNULL(@RevisionOK, 0) = 1 THEN 'COMPLETO' ELSE 'PENDIENTE' END,
                   FechaCalculo = SYSDATETIME(),
                   UsuarioCalculo = COALESCE(@Usuario, SYSTEM_USER)
    WHEN NOT MATCHED THEN
        INSERT
        (
            ExpedienteId, TrabajoTitulacionId, MecanismoTitulacionCodigo,
            NotaTrabajoPractico15, NotaTrabajoEscrito15, NotaDefensaOral15,
            NotaTrabajoPractico10, NotaTrabajoEscrito10, NotaDefensaOral10,
            NotaProcesoSobre10, NotaProcesoTitulacion20, PromedioAsignaturas,
            NotaPromedioAsignaturas80, NotaFinalGrado, CantidadEvaluadoresCalificadores,
            CantidadEvaluadoresAsignados, CantidadEvaluadoresMinimosPorComponente, MinimoEvaluadoresRequeridos,
            CantidadComponentesRequeridos, CantidadComponentesCompletos, RubricasCompletas,
            RevisionTrabajoAprobada, EstadoConsolidado, UsuarioCalculo
        )
        VALUES
        (
            @ExpedienteId, @TrabajoTitulacionId, @Mecanismo,
            @NotaPractico15, @NotaEscrito15, @NotaOral15,
            @NotaPractico10, @NotaEscrito10, @NotaOral10,
            @Proceso10, @Proceso20, @PromedioAsignaturas,
            @Nota80, @Final, @EvalMax,
            ISNULL(@EvalAsignados, 0), @EvalMin, @MinEval,
            @ReqComp, @CompCompletos, @RubricasCompletas,
            ISNULL(@RevisionOK, 0), CASE WHEN @RubricasCompletas = 1 AND ISNULL(@RevisionOK, 0) = 1 THEN 'COMPLETO' ELSE 'PENDIENTE' END,
            COALESCE(@Usuario, SYSTEM_USER)
        );

    UPDATE tit.ExpedienteTitulacion
    SET RubricaTitulacionCumple = @RubricasCompletas,
        NotaProcesoTitulacion20 = @Proceso20,
        NotaPromedioAsignaturas80 = @Nota80,
        NotaFinalGrado = @Final,
        EstadoExpediente = CASE WHEN @RubricasCompletas = 1 AND ISNULL(@RevisionOK, 0) = 1 THEN 'CALIFICADO' ELSE EstadoExpediente END,
        FechaActualizacion = SYSDATETIME(),
        UsuarioActualizacion = COALESCE(@Usuario, SYSTEM_USER)
    WHERE ExpedienteId = @ExpedienteId;

    SELECT *
    FROM eval.ConsolidadoExpediente
    WHERE ExpedienteId = @ExpedienteId;
END;
GO

/* --------------------------------------------------------------------------
   9. VISTAS DE PROMEDIOS Y PREVALIDACION
   -------------------------------------------------------------------------- */
CREATE OR ALTER VIEW rpt.vw_PromedioComponentesPorExpediente
AS
SELECT
    cce.ExpedienteId,
    cce.TrabajoTitulacionId,
    tt.CodigoTrabajo,
    tt.MecanismoTitulacionCodigo,
    ce.CodigoComponente,
    ce.NombreComponente,
    ce.PesoDentroProceso,
    COUNT(DISTINCT cce.EvaluadorTrabajoId) AS CantidadJuecesFinalizados,
    AVG(CAST(cce.NotaComponente15 AS DECIMAL(18,4))) AS PromedioComponente15,
    AVG(CAST(cce.NotaNormalizada10 AS DECIMAL(18,4))) AS PromedioComponente10,
    MIN(cce.NotaNormalizada10) AS NotaMinimaJuez10,
    MAX(cce.NotaNormalizada10) AS NotaMaximaJuez10
FROM eval.CalificacionComponenteEvaluador cce
INNER JOIN eval.ComponenteEvaluacion ce
    ON ce.ComponenteId = cce.ComponenteId
INNER JOIN tit.TrabajoTitulacion tt
    ON tt.TrabajoTitulacionId = cce.TrabajoTitulacionId
WHERE cce.EstadoCalificacion = 'FINALIZADA'
GROUP BY
    cce.ExpedienteId,
    cce.TrabajoTitulacionId,
    tt.CodigoTrabajo,
    tt.MecanismoTitulacionCodigo,
    ce.CodigoComponente,
    ce.NombreComponente,
    ce.PesoDentroProceso;
GO

CREATE OR ALTER VIEW rpt.vw_ConsolidadoFinalRubricas
AS
SELECT
    c.ConsolidadoId,
    c.ExpedienteId,
    er.NumeroIdentificacion,
    er.ApellidosNombres,
    e.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS AS MecanismoTitulacionCodigo,
    c.TrabajoTitulacionId,
    tt.CodigoTrabajo,
    tt.TituloTrabajo,
    c.MinimoEvaluadoresRequeridos,
    c.CantidadEvaluadoresAsignados,
    c.CantidadEvaluadoresCalificadores AS MaximoJuecesFinalizadosEnComponente,
    c.CantidadEvaluadoresMinimosPorComponente AS MinimoJuecesFinalizadosEnComponente,
    c.NotaTrabajoPractico10,
    c.NotaTrabajoPractico15,
    c.NotaTrabajoEscrito10,
    c.NotaTrabajoEscrito15,
    c.NotaDefensaOral10,
    c.NotaDefensaOral15,
    c.NotaProcesoSobre10,
    c.NotaProcesoTitulacion20,
    c.PromedioAsignaturas,
    c.NotaPromedioAsignaturas80,
    c.NotaFinalGrado,
    c.RubricasCompletas,
    c.RevisionTrabajoAprobada,
    c.EstadoConsolidado,
    c.FechaCalculo
FROM eval.ConsolidadoExpediente c
INNER JOIN tit.ExpedienteTitulacion e
    ON e.ExpedienteId = c.ExpedienteId
INNER JOIN core.EstudianteRef er
    ON er.EstudianteRefId = e.EstudianteRefId
LEFT JOIN tit.TrabajoTitulacion tt
    ON tt.TrabajoTitulacionId = c.TrabajoTitulacionId;
GO

CREATE OR ALTER VIEW rpt.vw_PrevalidacionActaConRubricas
AS
SELECT
    e.ExpedienteId,
    er.NumeroIdentificacion,
    er.ApellidosNombres,
    e.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS AS MecanismoTitulacionCodigo,
    e.NumeroActaGrado,
    tt.TrabajoTitulacionId,
    tt.CodigoTrabajo,
    tt.TituloTrabajo,
    tt.EstadoRevision,
    c.MinimoEvaluadoresRequeridos,
    c.CantidadEvaluadoresAsignados,
    c.CantidadEvaluadoresMinimosPorComponente,
    c.NotaTrabajoPractico10,
    c.NotaTrabajoPractico15,
    c.NotaTrabajoEscrito10,
    c.NotaTrabajoEscrito15,
    c.NotaDefensaOral10,
    c.NotaDefensaOral15,
    c.NotaProcesoSobre10,
    c.NotaProcesoTitulacion20,
    c.NotaFinalGrado,
    c.CantidadEvaluadoresCalificadores,
    c.CantidadComponentesRequeridos,
    c.CantidadComponentesCompletos,
    c.RubricasCompletas,
    c.RevisionTrabajoAprobada,
    CASE
        WHEN c.ConsolidadoId IS NULL THEN CAST(0 AS BIT)
        WHEN c.RubricasCompletas = 0 THEN CAST(0 AS BIT)
        WHEN e.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS = 'DEFENSA_GRADO' AND c.RevisionTrabajoAprobada = 0 THEN CAST(0 AS BIT)
        WHEN e.CedulaValidada = 0 OR e.TituloBachillerCumple = 0 OR e.InglesA2Cumple = 0 OR e.MallaCurricularCumple = 0 OR e.NoAdeudaFinanciero = 0 OR e.AptoSustentacion = 0 THEN CAST(0 AS BIT)
        WHEN e.PracticasPreprofesionalesCumple = 0 OR e.VinculacionCumple = 0 THEN CAST(0 AS BIT)
        ELSE CAST(1 AS BIT)
    END AS PuedeGenerarActa,
    CASE
        WHEN c.ConsolidadoId IS NULL THEN N'No existe consolidado de calificaciones.'
        WHEN c.RubricasCompletas = 0 THEN N'Faltan rubricas o calificaciones del minimo de evaluadores requerido.'
        WHEN e.MecanismoTitulacionId COLLATE Modern_Spanish_CI_AS = 'DEFENSA_GRADO' AND c.RevisionTrabajoAprobada = 0 THEN N'Falta aprobacion del responsable de revision del trabajo de titulacion.'
        WHEN e.CedulaValidada = 0 OR e.TituloBachillerCumple = 0 OR e.InglesA2Cumple = 0 OR e.MallaCurricularCumple = 0 OR e.NoAdeudaFinanciero = 0 OR e.AptoSustentacion = 0 THEN N'Faltan requisitos academicos, legales o financieros.'
        WHEN e.PracticasPreprofesionalesCumple = 0 OR e.VinculacionCumple = 0 THEN N'Falta cumplimiento de Practicas laborales o Servicio Comunitario.'
        ELSE N'Expediente apto para acta de grado.'
    END AS MensajeValidacion
FROM tit.ExpedienteTitulacion e
INNER JOIN core.EstudianteRef er
    ON er.EstudianteRefId = e.EstudianteRefId
LEFT JOIN tit.TrabajoTitulacionIntegrante ti
    ON ti.ExpedienteId = e.ExpedienteId
   AND ti.Activo = 1
LEFT JOIN tit.TrabajoTitulacion tt
    ON tt.TrabajoTitulacionId = ti.TrabajoTitulacionId
   AND tt.Activo = 1
LEFT JOIN eval.ConsolidadoExpediente c
    ON c.ExpedienteId = e.ExpedienteId;
GO

SELECT 'PARCHE V9 INSTALADO: evaluadores variables y promedios por rubrica habilitados.' AS Resultado;
GO
