/*
   INTEC_PRACTICAS_PREPROFESIONALES - CAPA OPERATIVA INTEGRAL

   Migración aditiva e idempotente para inscripción institucional,
   seguimiento, horas, evaluaciones, calificación, vinculación,
   reaperturas, notificaciones, auditoría y conciliación con titulación.
*/
USE [INTEC_PRACTICAS_PREPROFESIONALES];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    IF SCHEMA_ID(N'ops') IS NULL
        EXEC(N'CREATE SCHEMA ops AUTHORIZATION dbo');
    
    IF OBJECT_ID(N'ops.configuracion_proceso', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.configuracion_proceso (
            configuracion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            tipo_proceso_codigo varchar(3) NOT NULL,
            codigo_carrera nvarchar(50) NULL,
            nivel nvarchar(50) NULL,
            codigo_periodo nvarchar(50) NULL,
            horas_requeridas decimal(10,2) NOT NULL,
            documentos_requeridos int NOT NULL,
            nota_minima_aprobacion decimal(5,2) NOT NULL,
            requiere_evaluacion_docente bit NOT NULL CONSTRAINT DF_ops_config_eval_docente DEFAULT (1),
            requiere_evaluacion_tutor bit NOT NULL CONSTRAINT DF_ops_config_eval_tutor DEFAULT (0),
            requiere_autoevaluacion bit NOT NULL CONSTRAINT DF_ops_config_autoevaluacion DEFAULT (0),
            requiere_resultado_vinculacion bit NOT NULL CONSTRAINT DF_ops_config_resultado_vin DEFAULT (0),
            peso_docente decimal(5,2) NOT NULL CONSTRAINT DF_ops_config_peso_docente DEFAULT (100),
            peso_tutor decimal(5,2) NOT NULL CONSTRAINT DF_ops_config_peso_tutor DEFAULT (0),
            peso_autoevaluacion decimal(5,2) NOT NULL CONSTRAINT DF_ops_config_peso_auto DEFAULT (0),
            activo bit NOT NULL CONSTRAINT DF_ops_config_activo DEFAULT (1),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_config_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT CK_ops_config_proceso CHECK (tipo_proceso_codigo IN ('PPF', 'VIN')),
            CONSTRAINT CK_ops_config_horas CHECK (horas_requeridas > 0 AND horas_requeridas <= 10000),
            CONSTRAINT CK_ops_config_documentos CHECK (documentos_requeridos >= 0 AND documentos_requeridos <= 100),
            CONSTRAINT CK_ops_config_nota CHECK (nota_minima_aprobacion >= 0 AND nota_minima_aprobacion <= 10),
            CONSTRAINT CK_ops_config_pesos CHECK (
                peso_docente >= 0 AND peso_docente <= 100 AND
                peso_tutor >= 0 AND peso_tutor <= 100 AND
                peso_autoevaluacion >= 0 AND peso_autoevaluacion <= 100 AND
                peso_docente + peso_tutor + peso_autoevaluacion > 0 AND
                peso_docente + peso_tutor + peso_autoevaluacion <= 100
            )
        );
    END;
    
    IF NOT EXISTS (
        SELECT 1 FROM ops.configuracion_proceso
        WHERE tipo_proceso_codigo = 'PPF'
          AND codigo_carrera IS NULL AND nivel IS NULL AND codigo_periodo IS NULL
    )
    BEGIN
        INSERT INTO ops.configuracion_proceso (
            tipo_proceso_codigo, horas_requeridas, documentos_requeridos,
            nota_minima_aprobacion, requiere_evaluacion_docente,
            requiere_evaluacion_tutor, requiere_autoevaluacion,
            requiere_resultado_vinculacion, peso_docente, peso_tutor,
            peso_autoevaluacion, usuario_registro
        ) VALUES ('PPF', 240, 5, 7, 1, 1, 0, 0, 60, 40, 0, N'MIGRACION_AUTOMATICA');
    END;
    
    IF NOT EXISTS (
        SELECT 1 FROM ops.configuracion_proceso
        WHERE tipo_proceso_codigo = 'VIN'
          AND codigo_carrera IS NULL AND nivel IS NULL AND codigo_periodo IS NULL
    )
    BEGIN
        INSERT INTO ops.configuracion_proceso (
            tipo_proceso_codigo, horas_requeridas, documentos_requeridos,
            nota_minima_aprobacion, requiere_evaluacion_docente,
            requiere_evaluacion_tutor, requiere_autoevaluacion,
            requiere_resultado_vinculacion, peso_docente, peso_tutor,
            peso_autoevaluacion, usuario_registro
        ) VALUES ('VIN', 60, 4, 7, 1, 0, 0, 1, 100, 0, 0, N'MIGRACION_AUTOMATICA');
    END;
    
    IF OBJECT_ID(N'ops.inscripcion_cumplimiento', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.inscripcion_cumplimiento (
            inscripcion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            tipo_proceso_codigo varchar(3) NOT NULL,
            codigo_estud decimal(18,0) NOT NULL,
            cod_anio_basica decimal(18,0) NOT NULL,
            codigo_periodo_academico_origen numeric(18,0) NOT NULL,
            codigo_periodo_institucional numeric(18,0) NOT NULL,
            estado nvarchar(30) NOT NULL CONSTRAINT DF_ops_inscripcion_estado DEFAULT (N'INSCRITO'),
            es_matricula_academica bit NOT NULL CONSTRAINT DF_ops_inscripcion_no_academica DEFAULT (0),
            fuente_academica nvarchar(120) NOT NULL CONSTRAINT DF_ops_inscripcion_fuente DEFAULT (N'CARRERAXESTUD_SOLO_LECTURA'),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_inscripcion_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_inscripcion_expediente UNIQUE (expediente_id),
            CONSTRAINT CK_ops_inscripcion_proceso CHECK (tipo_proceso_codigo IN ('PPF', 'VIN')),
            CONSTRAINT CK_ops_inscripcion_estado CHECK (estado IN (N'INSCRITO', N'EN_PROCESO', N'EN_REVISION', N'CUMPLIDO', N'NO_CUMPLIDO', N'ANULADO')),
            CONSTRAINT CK_ops_inscripcion_no_academica CHECK (es_matricula_academica = 0)
        );
    END;
    
    IF OBJECT_ID(N'ops.entidad_receptora', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.entidad_receptora (
            entidad_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            nombre nvarchar(250) NOT NULL,
            ruc nvarchar(20) NULL,
            tipo_entidad nvarchar(80) NULL,
            sector_economico nvarchar(160) NULL,
            direccion nvarchar(500) NULL,
            contacto_nombre nvarchar(250) NULL,
            contacto_correo nvarchar(250) NULL,
            contacto_telefono nvarchar(30) NULL,
            activo bit NOT NULL CONSTRAINT DF_ops_entidad_activo DEFAULT (1),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_entidad_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL
        );
    END;
    
    IF OBJECT_ID(N'ops.convenio_institucional', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.convenio_institucional (
            convenio_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            entidad_id bigint NOT NULL,
            tipo_proceso_codigo varchar(3) NOT NULL,
            codigo_convenio nvarchar(80) NOT NULL,
            objeto nvarchar(max) NULL,
            fecha_inicio date NOT NULL,
            fecha_fin date NOT NULL,
            estado nvarchar(30) NOT NULL CONSTRAINT DF_ops_convenio_estado DEFAULT (N'VIGENTE'),
            archivo_url nvarchar(1000) NULL,
            activo bit NOT NULL CONSTRAINT DF_ops_convenio_activo DEFAULT (1),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_convenio_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT FK_ops_convenio_entidad FOREIGN KEY (entidad_id)
                REFERENCES ops.entidad_receptora(entidad_id),
            CONSTRAINT CK_ops_convenio_proceso CHECK (tipo_proceso_codigo IN ('PPF', 'VIN')),
            CONSTRAINT CK_ops_convenio_fechas CHECK (fecha_fin >= fecha_inicio)
        );
    END;
    
    IF OBJECT_ID(N'ops.proyecto_vinculacion', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.proyecto_vinculacion (
            proyecto_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            entidad_id bigint NULL,
            convenio_id bigint NULL,
            codigo_proyecto nvarchar(80) NOT NULL,
            nombre nvarchar(300) NOT NULL,
            linea_intervencion nvarchar(250) NOT NULL,
            poblacion_objetivo nvarchar(max) NULL,
            beneficiarios_previstos int NULL,
            objetivo_general nvarchar(max) NULL,
            fecha_inicio date NOT NULL,
            fecha_fin date NOT NULL,
            estado nvarchar(30) NOT NULL CONSTRAINT DF_ops_proyecto_estado DEFAULT (N'PLANIFICADO'),
            activo bit NOT NULL CONSTRAINT DF_ops_proyecto_activo DEFAULT (1),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_proyecto_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT FK_ops_proyecto_entidad FOREIGN KEY (entidad_id)
                REFERENCES ops.entidad_receptora(entidad_id),
            CONSTRAINT FK_ops_proyecto_convenio FOREIGN KEY (convenio_id)
                REFERENCES ops.convenio_institucional(convenio_id),
            CONSTRAINT CK_ops_proyecto_fechas CHECK (fecha_fin >= fecha_inicio)
        );
    END;
    
    IF OBJECT_ID(N'ops.plan_proceso', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.plan_proceso (
            plan_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            tipo_proceso_codigo varchar(3) NOT NULL,
            entidad_id bigint NULL,
            convenio_id bigint NULL,
            proyecto_id bigint NULL,
            tutor_externo_nombre nvarchar(250) NULL,
            tutor_externo_correo nvarchar(250) NULL,
            tutor_externo_telefono nvarchar(30) NULL,
            objetivo_general nvarchar(max) NULL,
            resultados_aprendizaje nvarchar(max) NULL,
            actividades_planificadas nvarchar(max) NULL,
            fecha_inicio date NULL,
            fecha_fin date NULL,
            horas_planificadas decimal(10,2) NOT NULL CONSTRAINT DF_ops_plan_horas DEFAULT (0),
            estado nvarchar(30) NOT NULL CONSTRAINT DF_ops_plan_estado DEFAULT (N'BORRADOR'),
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_plan_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_plan_expediente UNIQUE (expediente_id),
            CONSTRAINT FK_ops_plan_entidad FOREIGN KEY (entidad_id)
                REFERENCES ops.entidad_receptora(entidad_id),
            CONSTRAINT FK_ops_plan_convenio FOREIGN KEY (convenio_id)
                REFERENCES ops.convenio_institucional(convenio_id),
            CONSTRAINT FK_ops_plan_proyecto FOREIGN KEY (proyecto_id)
                REFERENCES ops.proyecto_vinculacion(proyecto_id),
            CONSTRAINT CK_ops_plan_proceso CHECK (tipo_proceso_codigo IN ('PPF', 'VIN')),
            CONSTRAINT CK_ops_plan_fechas CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio)
        );
    END;
    
    IF OBJECT_ID(N'ops.registro_actividad', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.registro_actividad (
            actividad_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            fecha_actividad date NOT NULL,
            descripcion nvarchar(1500) NOT NULL,
            horas decimal(8,2) NOT NULL,
            evidencia_url nvarchar(1000) NULL,
            evidencia_nombre nvarchar(300) NULL,
            estado_revision nvarchar(30) NOT NULL CONSTRAINT DF_ops_actividad_estado DEFAULT (N'PENDIENTE'),
            observacion_revision nvarchar(1000) NULL,
            revisado_por nvarchar(150) NULL,
            fecha_revision datetime2(3) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_actividad_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT CK_ops_actividad_horas CHECK (horas > 0 AND horas <= 24),
            CONSTRAINT CK_ops_actividad_estado CHECK (estado_revision IN (N'PENDIENTE', N'VALIDADO', N'OBSERVADO', N'RECHAZADO'))
        );
    END;
    
    IF COL_LENGTH(N'ops.registro_actividad', N'hora_inicio') IS NULL
        ALTER TABLE ops.registro_actividad ADD hora_inicio time(0) NULL;
    IF COL_LENGTH(N'ops.registro_actividad', N'hora_fin') IS NULL
        ALTER TABLE ops.registro_actividad ADD hora_fin time(0) NULL;
    IF COL_LENGTH(N'ops.registro_actividad', N'descanso_minutos') IS NULL
        ALTER TABLE ops.registro_actividad ADD descanso_minutos int NOT NULL CONSTRAINT DF_ops_actividad_descanso DEFAULT (0);
    IF COL_LENGTH(N'ops.registro_actividad', N'modalidad') IS NULL
        ALTER TABLE ops.registro_actividad ADD modalidad nvarchar(30) NULL;
    IF COL_LENGTH(N'ops.registro_actividad', N'lugar') IS NULL
        ALTER TABLE ops.registro_actividad ADD lugar nvarchar(300) NULL;
    IF COL_LENGTH(N'ops.registro_actividad', N'origen_horas') IS NULL
        ALTER TABLE ops.registro_actividad ADD origen_horas nvarchar(30) NOT NULL CONSTRAINT DF_ops_actividad_origen_horas DEFAULT (N'MANUAL');
    
    IF OBJECT_ID(N'ops.meta_indicador', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.meta_indicador (
            indicador_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            nombre nvarchar(300) NOT NULL,
            unidad_medida nvarchar(80) NOT NULL,
            meta decimal(14,2) NOT NULL,
            resultado decimal(14,2) NULL,
            evidencia_url nvarchar(1000) NULL,
            observacion nvarchar(1000) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_indicador_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT CK_ops_indicador_meta CHECK (meta >= 0),
            CONSTRAINT CK_ops_indicador_resultado CHECK (resultado IS NULL OR resultado >= 0)
        );
    END;
    
    IF OBJECT_ID(N'ops.cierre_proceso', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.cierre_proceso (
            cierre_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            supervision_realizada bit NOT NULL CONSTRAINT DF_ops_cierre_supervision DEFAULT (0),
            evaluacion_entidad decimal(5,2) NULL,
            informe_final_validado bit NOT NULL CONSTRAINT DF_ops_cierre_informe DEFAULT (0),
            acta_aceptacion_validada bit NOT NULL CONSTRAINT DF_ops_cierre_acta DEFAULT (0),
            certificado_emitido bit NOT NULL CONSTRAINT DF_ops_cierre_certificado DEFAULT (0),
            observacion nvarchar(1500) NULL,
            fecha_cierre datetime2(3) NULL,
            cerrado_por nvarchar(150) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_cierre_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_cierre_expediente UNIQUE (expediente_id),
            CONSTRAINT CK_ops_cierre_evaluacion CHECK (evaluacion_entidad IS NULL OR (evaluacion_entidad >= 0 AND evaluacion_entidad <= 10))
        );
    END;
    
    IF OBJECT_ID(N'ops.evaluacion_practica', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.evaluacion_practica (
            evaluacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            estado nvarchar(40) NOT NULL CONSTRAINT DF_ops_evaluacion_estado DEFAULT (N'PENDIENTE_REVISION'),
            calificacion decimal(5,2) NULL,
            nota_minima_aprobacion decimal(5,2) NOT NULL CONSTRAINT DF_ops_evaluacion_nota_minima DEFAULT (7.00),
            resultado nvarchar(20) NOT NULL CONSTRAINT DF_ops_evaluacion_resultado DEFAULT (N'PENDIENTE'),
            observacion_revision nvarchar(1500) NULL,
            observacion_calificacion nvarchar(1500) NULL,
            enviado_por nvarchar(150) NULL,
            fecha_envio_revision datetime2(3) NULL,
            revisado_por nvarchar(150) NULL,
            fecha_revision datetime2(3) NULL,
            calificado_por nvarchar(150) NULL,
            fecha_calificacion datetime2(3) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_evaluacion_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_evaluacion_expediente UNIQUE (expediente_id),
            CONSTRAINT CK_ops_evaluacion_estado CHECK (estado IN (N'PENDIENTE_REVISION', N'EN_REVISION', N'PENDIENTE_CALIFICACION', N'CALIFICADA')),
            CONSTRAINT CK_ops_evaluacion_resultado CHECK (resultado IN (N'PENDIENTE', N'APROBADO', N'REPROBADO')),
            CONSTRAINT CK_ops_evaluacion_calificacion CHECK (calificacion IS NULL OR (calificacion >= 0 AND calificacion <= 10)),
            CONSTRAINT CK_ops_evaluacion_nota_minima CHECK (nota_minima_aprobacion >= 0 AND nota_minima_aprobacion <= 10),
            CONSTRAINT CK_ops_evaluacion_consistencia CHECK (
                (estado = N'CALIFICADA' AND calificacion IS NOT NULL AND resultado IN (N'APROBADO', N'REPROBADO'))
                OR
                (estado <> N'CALIFICADA' AND calificacion IS NULL AND resultado = N'PENDIENTE')
            )
        );
    END;
    
    IF COL_LENGTH(N'ops.evaluacion_practica', N'origen_calificacion') IS NULL
        ALTER TABLE ops.evaluacion_practica ADD origen_calificacion nvarchar(50) NULL;
    IF COL_LENGTH(N'ops.evaluacion_practica', N'detalle_calculo') IS NULL
        ALTER TABLE ops.evaluacion_practica ADD detalle_calculo nvarchar(max) NULL;
    
    IF OBJECT_ID(N'ops.evaluacion_actor', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.evaluacion_actor (
            evaluacion_actor_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            rol_evaluador nvarchar(30) NOT NULL,
            calificacion decimal(5,2) NOT NULL,
            peso decimal(5,2) NOT NULL,
            evaluador_nombre nvarchar(250) NULL,
            evaluador_correo nvarchar(250) NULL,
            observacion nvarchar(1500) NULL,
            evidencia_url nvarchar(1000) NULL,
            estado nvarchar(20) NOT NULL CONSTRAINT DF_ops_eval_actor_estado DEFAULT (N'REGISTRADA'),
            validado_por nvarchar(150) NULL,
            fecha_validacion datetime2(3) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_eval_actor_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_eval_actor_expediente_rol UNIQUE (expediente_id, rol_evaluador),
            CONSTRAINT CK_ops_eval_actor_rol CHECK (rol_evaluador IN (N'DOCENTE_ACADEMICO', N'TUTOR_EMPRESARIAL', N'AUTOEVALUACION')),
            CONSTRAINT CK_ops_eval_actor_nota CHECK (calificacion >= 0 AND calificacion <= 10),
            CONSTRAINT CK_ops_eval_actor_peso CHECK (peso >= 0 AND peso <= 100),
            CONSTRAINT CK_ops_eval_actor_estado CHECK (estado IN (N'REGISTRADA', N'VALIDADA', N'OBSERVADA'))
        );
    END;
    
    IF OBJECT_ID(N'ops.historial_calificacion', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.historial_calificacion (
            historial_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            evaluacion_id bigint NOT NULL,
            expediente_id bigint NOT NULL,
            accion nvarchar(40) NOT NULL,
            estado nvarchar(40) NOT NULL,
            calificacion decimal(5,2) NULL,
            nota_minima_aprobacion decimal(5,2) NOT NULL,
            resultado nvarchar(20) NOT NULL,
            origen_calificacion nvarchar(50) NULL,
            detalle_calculo nvarchar(max) NULL,
            observacion nvarchar(1500) NULL,
            usuario nvarchar(150) NOT NULL,
            fecha datetime2(3) NOT NULL CONSTRAINT DF_ops_hist_calificacion_fecha DEFAULT (SYSDATETIME())
        );
    END;
    
    IF OBJECT_ID(N'ops.resultado_vinculacion', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.resultado_vinculacion (
            resultado_vinculacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            beneficiarios_reales int NOT NULL,
            resumen_impacto nvarchar(max) NOT NULL,
            observacion nvarchar(1500) NULL,
            evidencia_url nvarchar(1000) NULL,
            estado nvarchar(20) NOT NULL CONSTRAINT DF_ops_resultado_vin_estado DEFAULT (N'REGISTRADO'),
            validado_por nvarchar(150) NULL,
            fecha_validacion datetime2(3) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_resultado_vin_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT UQ_ops_resultado_vin_expediente UNIQUE (expediente_id),
            CONSTRAINT CK_ops_resultado_vin_beneficiarios CHECK (beneficiarios_reales >= 0),
            CONSTRAINT CK_ops_resultado_vin_estado CHECK (estado IN (N'REGISTRADO', N'VALIDADO', N'OBSERVADO'))
        );
    END;
    
    IF OBJECT_ID(N'ops.producto_vinculacion', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.producto_vinculacion (
            producto_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            nombre nvarchar(300) NOT NULL,
            descripcion nvarchar(1500) NULL,
            cantidad decimal(14,2) NOT NULL,
            unidad_medida nvarchar(80) NOT NULL,
            evidencia_url nvarchar(1000) NULL,
            estado_revision nvarchar(20) NOT NULL CONSTRAINT DF_ops_producto_vin_estado DEFAULT (N'PENDIENTE'),
            observacion_revision nvarchar(1000) NULL,
            revisado_por nvarchar(150) NULL,
            fecha_revision datetime2(3) NULL,
            usuario_registro nvarchar(150) NOT NULL,
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_producto_vin_fecha DEFAULT (SYSDATETIME()),
            usuario_modifica nvarchar(150) NULL,
            fecha_modifica datetime2(3) NULL,
            CONSTRAINT CK_ops_producto_vin_cantidad CHECK (cantidad >= 0),
            CONSTRAINT CK_ops_producto_vin_estado CHECK (estado_revision IN (N'PENDIENTE', N'VALIDADO', N'OBSERVADO', N'RECHAZADO'))
        );
    END;
    
    IF OBJECT_ID(N'ops.reapertura_expediente', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.reapertura_expediente (
            reapertura_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            evaluacion_id bigint NULL,
            estado_anterior nvarchar(40) NULL,
            resultado_anterior nvarchar(20) NULL,
            calificacion_anterior decimal(5,2) NULL,
            motivo nvarchar(1500) NOT NULL,
            requiere_reversion_titulacion bit NOT NULL CONSTRAINT DF_ops_reapertura_titulacion DEFAULT (0),
            usuario nvarchar(150) NOT NULL,
            fecha datetime2(3) NOT NULL CONSTRAINT DF_ops_reapertura_fecha DEFAULT (SYSDATETIME())
        );
    END;
    
    IF OBJECT_ID(N'ops.notificacion_proceso', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.notificacion_proceso (
            notificacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            clave_evento nvarchar(220) NOT NULL,
            expediente_id bigint NULL,
            tipo_proceso_codigo varchar(3) NULL,
            destinatario_login nvarchar(150) NULL,
            destinatario_rol nvarchar(50) NOT NULL,
            nivel nvarchar(20) NOT NULL,
            titulo nvarchar(250) NOT NULL,
            mensaje nvarchar(1200) NOT NULL,
            leida bit NOT NULL CONSTRAINT DF_ops_notificacion_leida DEFAULT (0),
            fecha_lectura datetime2(3) NULL,
            activa bit NOT NULL CONSTRAINT DF_ops_notificacion_activa DEFAULT (1),
            fecha_registro datetime2(3) NOT NULL CONSTRAINT DF_ops_notificacion_fecha DEFAULT (SYSDATETIME()),
            CONSTRAINT CK_ops_notificacion_nivel CHECK (nivel IN (N'INFORMATIVA', N'ADVERTENCIA', N'CRITICA'))
        );
    END;
    
    IF OBJECT_ID(N'ops.conciliacion_titulacion', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.conciliacion_titulacion (
            conciliacion_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            expediente_id bigint NOT NULL,
            tipo_proceso_codigo varchar(3) NOT NULL,
            estado nvarchar(30) NOT NULL,
            intentos int NOT NULL CONSTRAINT DF_ops_conciliacion_intentos DEFAULT (0),
            proximo_intento datetime2(3) NULL,
            ultimo_error nvarchar(2000) NULL,
            respuesta nvarchar(max) NULL,
            usuario_solicita nvarchar(150) NOT NULL,
            fecha_solicitud datetime2(3) NOT NULL CONSTRAINT DF_ops_conciliacion_fecha DEFAULT (SYSDATETIME()),
            fecha_ultimo_intento datetime2(3) NULL,
            fecha_completado datetime2(3) NULL,
            CONSTRAINT UQ_ops_conciliacion_expediente UNIQUE (expediente_id, tipo_proceso_codigo),
            CONSTRAINT CK_ops_conciliacion_estado CHECK (estado IN (N'PENDIENTE', N'PROCESANDO', N'COMPLETADO', N'ERROR'))
        );
    END;
    
    IF OBJECT_ID(N'ops.auditoria_operativa', N'U') IS NULL
    BEGIN
        CREATE TABLE ops.auditoria_operativa (
            auditoria_id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
            modulo nvarchar(80) NOT NULL,
            entidad nvarchar(120) NOT NULL,
            entidad_id nvarchar(80) NULL,
            accion nvarchar(30) NOT NULL,
            detalle nvarchar(max) NULL,
            usuario nvarchar(150) NOT NULL,
            fecha datetime2(3) NOT NULL CONSTRAINT DF_ops_auditoria_fecha DEFAULT (SYSDATETIME())
        );
    END;
    
    IF OBJECT_ID(N'pp.expediente_practica', N'U') IS NOT NULL
       AND OBJECT_ID(N'cat.tipo_proceso', N'U') IS NOT NULL
       AND OBJECT_ID(N'cat.estado_expediente', N'U') IS NOT NULL
    BEGIN
        INSERT INTO ops.inscripcion_cumplimiento (
            expediente_id, tipo_proceso_codigo, codigo_estud, cod_anio_basica,
            codigo_periodo_academico_origen, codigo_periodo_institucional,
            estado, es_matricula_academica, fuente_academica, usuario_registro
        )
        SELECT
            e.expediente_id,
            tp.codigo,
            e.codigo_estud,
            e.cod_anio_basica,
            e.codigo_periodo,
            e.codigo_periodo,
            CASE
                WHEN ee.codigo IN (N'APROBADO', N'VALIDADO', N'FINALIZADO', N'CERRADO') THEN N'CUMPLIDO'
                WHEN ee.codigo IN (N'RECHAZADO', N'ANULADO') THEN N'NO_CUMPLIDO'
                WHEN ee.codigo IN (N'OBSERVADO', N'EN_REVISION') THEN N'EN_REVISION'
                ELSE N'EN_PROCESO'
            END,
            0,
            N'EXPEDIENTE_HISTORICO_SOLO_LECTURA',
            N'MIGRACION_AUTOMATICA'
        FROM pp.expediente_practica e
        INNER JOIN cat.tipo_proceso tp ON tp.tipo_proceso_id = e.tipo_proceso_id
        INNER JOIN cat.estado_expediente ee ON ee.estado_expediente_id = e.estado_expediente_id
        WHERE tp.codigo IN ('PPF', 'VIN')
          AND NOT EXISTS (
              SELECT 1
              FROM ops.inscripcion_cumplimiento i
              WHERE i.expediente_id = e.expediente_id
          );
    END;
    
    IF OBJECT_ID(N'pp.expediente_practica', N'U') IS NOT NULL
       AND OBJECT_ID(N'cat.tipo_proceso', N'U') IS NOT NULL
       AND OBJECT_ID(N'cat.estado_expediente', N'U') IS NOT NULL
    BEGIN
        INSERT INTO ops.evaluacion_practica (
            expediente_id, estado, calificacion, nota_minima_aprobacion, resultado,
            observacion_revision, enviado_por, fecha_envio_revision,
            revisado_por, fecha_revision, calificado_por, fecha_calificacion,
            usuario_registro
        )
        SELECT
            e.expediente_id,
            CASE WHEN cierre.evaluacion_entidad IS NOT NULL THEN N'CALIFICADA' ELSE N'PENDIENTE_CALIFICACION' END,
            cierre.evaluacion_entidad,
            7.00,
            CASE
                WHEN cierre.evaluacion_entidad IS NULL THEN N'PENDIENTE'
                WHEN cierre.evaluacion_entidad >= 7.00 THEN N'APROBADO'
                ELSE N'REPROBADO'
            END,
            N'Expediente histórico incorporado al flujo formal de evaluación.',
            N'MIGRACION_AUTOMATICA',
            SYSDATETIME(),
            N'MIGRACION_AUTOMATICA',
            SYSDATETIME(),
            CASE WHEN cierre.evaluacion_entidad IS NOT NULL THEN N'MIGRACION_AUTOMATICA' ELSE NULL END,
            CASE WHEN cierre.evaluacion_entidad IS NOT NULL THEN SYSDATETIME() ELSE NULL END,
            N'MIGRACION_AUTOMATICA'
        FROM pp.expediente_practica e
        INNER JOIN cat.estado_expediente ee ON ee.estado_expediente_id = e.estado_expediente_id
        LEFT JOIN ops.cierre_proceso cierre ON cierre.expediente_id = e.expediente_id
        WHERE ee.codigo IN (N'APROBADO', N'VALIDADO', N'FINALIZADO', N'CERRADO', N'REPROBADO')
          AND NOT EXISTS (
              SELECT 1
              FROM ops.evaluacion_practica evaluacion
              WHERE evaluacion.expediente_id = e.expediente_id
          );
    END;
    
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_inscripcion_seguimiento' AND object_id = OBJECT_ID(N'ops.inscripcion_cumplimiento'))
        CREATE INDEX IX_ops_inscripcion_seguimiento ON ops.inscripcion_cumplimiento(tipo_proceso_codigo, codigo_periodo_institucional, estado, codigo_estud);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_evaluacion_estado' AND object_id = OBJECT_ID(N'ops.evaluacion_practica'))
        CREATE INDEX IX_ops_evaluacion_estado ON ops.evaluacion_practica(estado, resultado, fecha_calificacion, expediente_id);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_convenio_vigencia' AND object_id = OBJECT_ID(N'ops.convenio_institucional'))
        CREATE INDEX IX_ops_convenio_vigencia ON ops.convenio_institucional(tipo_proceso_codigo, activo, fecha_inicio, fecha_fin);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_actividad_expediente' AND object_id = OBJECT_ID(N'ops.registro_actividad'))
        CREATE INDEX IX_ops_actividad_expediente ON ops.registro_actividad(expediente_id, fecha_actividad, estado_revision);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_notificacion_destinatario' AND object_id = OBJECT_ID(N'ops.notificacion_proceso'))
        CREATE INDEX IX_ops_notificacion_destinatario ON ops.notificacion_proceso(destinatario_rol, destinatario_login, activa, leida, fecha_registro DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_auditoria_fecha' AND object_id = OBJECT_ID(N'ops.auditoria_operativa'))
        CREATE INDEX IX_ops_auditoria_fecha ON ops.auditoria_operativa(fecha DESC, modulo, accion);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ops_configuracion_alcance' AND object_id = OBJECT_ID(N'ops.configuracion_proceso'))
        CREATE UNIQUE INDEX UX_ops_configuracion_alcance
            ON ops.configuracion_proceso(tipo_proceso_codigo, codigo_carrera, nivel, codigo_periodo);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_eval_actor_expediente' AND object_id = OBJECT_ID(N'ops.evaluacion_actor'))
        CREATE INDEX IX_ops_eval_actor_expediente ON ops.evaluacion_actor(expediente_id, rol_evaluador, estado);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_hist_calificacion_expediente' AND object_id = OBJECT_ID(N'ops.historial_calificacion'))
        CREATE INDEX IX_ops_hist_calificacion_expediente ON ops.historial_calificacion(expediente_id, fecha DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_producto_vin_expediente' AND object_id = OBJECT_ID(N'ops.producto_vinculacion'))
        CREATE INDEX IX_ops_producto_vin_expediente ON ops.producto_vinculacion(expediente_id, estado_revision, producto_id);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ops_reapertura_expediente' AND object_id = OBJECT_ID(N'ops.reapertura_expediente'))
        CREATE INDEX IX_ops_reapertura_expediente ON ops.reapertura_expediente(expediente_id, fecha DESC);
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

SELECT
    DB_NAME() AS BaseDatos,
    (SELECT COUNT_BIG(*) FROM ops.configuracion_proceso WHERE activo = 1) AS ConfiguracionesActivas,
    OBJECT_ID(N'ops.evaluacion_practica', N'U') AS EvaluacionPracticaObjectId,
    OBJECT_ID(N'ops.historial_calificacion', N'U') AS HistorialCalificacionObjectId;
GO

