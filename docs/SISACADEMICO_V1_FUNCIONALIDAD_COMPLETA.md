# SisAcademicoV1 - Funcionalidad completa para clonacion

## Objetivo

Este documento consolida la informacion extraida directamente del proyecto `SisAcademicoV1` para completar la clonacion funcional dentro del sistema moderno.

Regla principal: no se ejecuta Crystal Reports. Los `.rpt` quedan como referencia y los documentos se generan por codigo usando PDF/Excel/HTML desde backend.

## Totales detectados

| Indicador | Valor |
|---|---:|
| Artefactos revisados | 407 |
| Archivos `aspx` | 186 |
| Archivos `config` | 4 |
| Archivos `rpt` | 39 |
| Archivos `vb` | 178 |
| Estado `base` | 313 |
| Estado `excluded` | 14 |
| Estado `partial` | 80 |
| Tablas SQL detectadas | 89 |
| Archivos con riesgo DELETE/mantenimiento | 48 |

## Mapa de modulos

| Modulo | Estado | Artefactos | Tablas detectadas | Operaciones | Frontend/backend moderno |
|---|---|---:|---|---|---|
| Catalogos academicos | base | 22 | CARRERAXESTUD, CARRERAS, PERIODO, PENSUM, MALLA_PENSUM, EMPRESA, REQ_EXAMENES_ESTUD, MATERIAHOMOTEXTOF, PROVINCIAS, DATOS_ESTUD | DELETE:17, INSERT:10, SELECT:33, UPDATE:66 | sisacademico_admin.py, carreras, materias, mallas, materia_homo_textof, periodos, paralelos, jornadas, modalidades, provincias |
| Admision y preinscripcion | base | 17 | PREINSCRIPCION, PERIODO, CABECERA_MATRICULA, DATOS_ESTUD, MODALIDADMATRICULA, DATOSFACTURA, CORREOSESTUDINTEC, IN_LECONTACTO, IN_ENTERO, IN_DESEAINGRESAR | INSERT:18, SELECT:78, UPDATE:10 | preinscription.py, sisacademico_admin.py, preinscripciones, datos_factura |
| Certificados y reportes | base | 74 | DATOS_ESTUD, PERIODO, CARRERAXESTUD, CARRERAS, PREINSCRIPCION, CABECERA_MATRICULA, MAXNIVELESTUDIANTE, NOTASMAXIMACARRERA, USUARIOS, FALTASJUSTINJUS | SELECT:52, UPDATE:4 | certificados.py, credential_generator.py, legacy_reports.py, sisacademico_admin.py, certificados_generados, credenciales_curso |
| Docentes y asignaciones | base | 14 | DATOSDOCENTE, CARRERAXDOCENTE, USUARIOS, PERIODO, CARRERAS, PARALELOS, PENSUM, JORNADA, MALLA_PENSUM | DELETE:9, INSERT:9, SELECT:27, UPDATE:33 | teacher_evaluation.py, sisacademico_admin.py, docentes, actualizacion_est, docente_materias |
| Educacion continua | base | 20 | DATOS_ESTUD, PENSUM, CARRERAS, CARRERAXESTUD, JORNADA, PERIODO, USUARIOS, PRACTICASPROFESIONALES, REPOSITORIO, MODALIDADMATRICULA | DELETE:8, INSERT:20, SELECT:45, UPDATE:29 | sisacademico_admin.py, cursos_edu_continua, corte_curso, corte_curso_estudiante, credenciales_curso |
| Estudiantes y ficha academica | base | 15 | DATOS_ESTUD, REGISTRODOCESTUD, CORREOSESTUDINTEC, PREINSCRIPCION, CABECERA_MATRICULA, PERIODO, PRACTICASPROFESIONALES, ESTADO, CARRERAXESTUD, CARRERAS | DELETE:6, INSERT:16, SELECT:31, UPDATE:47 | students.py, sisacademico_admin.py, estudiantes, actualizacion_estudiantes, registro_documentos_estudiante, correos, seguimiento |
| Evaluacion docente y cuestionarios | base | 50 | PERIODO, CARRERAXDOCENTE, PENSUM, CARRERAS, DATOSDOCENTE, CUESTIONARIO, CARRERAXESTUD, RESULTADOAUTOEVALUACION, ACTIVARAUTOEVALUACION, NUMEROPREGALEAT | DELETE:7, INSERT:11, SELECT:86, UPDATE:125 | teacher_evaluation.py, sisacademico_admin.py, numero_preguntas, cuestionarios, preguntas_evaluacion, evaluacion_resultados, autoevaluacion_resultados, fechas_autoevaluacion, planes_foros |
| Financiero, pagos y convenios | base | 9 | REGISTROPAGOS, DATOS_ESTUD, PERIODO, CARRERAS | INSERT:1, SELECT:10, UPDATE:2 | preinscription.py, legacy_reports.py, sisacademico_admin.py, pagos_matricula, datos_factura |
| Integraciones Moodle y Microsoft 365 | base | 8 | CORREOSESTUDINTEC, PERIODO, REGISTROPAGOS, VB | SELECT:8, UPDATE:6 | teams.py, mass_email.py, credential_generator.py, sisacademico_admin.py, moodle_notas, moodle_sincronizacion, microsoft365_audit, credenciales_curso |
| Mantenimiento controlado y operaciones sensibles | partial | 15 | PREINSCRIPCION, CARRERAXESTUD, DATOS_ESTUD, CARRERAS, CABECERA_MATRICULA, MODALIDADMATRICULA, PENSUM, AUXREG, USUARIOS, DATOSFACTURA | DELETE:8, INSERT:2, SELECT:14, UPDATE:7 | sisacademico_admin.py, academic_enrollment.py, preinscription.py, estudiantes, cabecera_matricula, matricula_materias, preinscripciones |
| Matricula academica y financiera | base | 26 | CARRERAXESTUD, CABECERA_MATRICULA, PERIODO, PENSUM, CARRERAS, DATOS_ESTUD, MODALIDADMATRICULA, CONTROLMATRICULA, CABECERA_MATRICULA_VARIOS, REGISTROPAGOS | DELETE:21, INSERT:23, SELECT:90, UPDATE:100 | academic_enrollment.py, sisacademico_admin.py, cabecera_matricula, matricula_materias, pagos_matricula, cambio_periodo_hr |
| Notas y apertura de calificaciones | partial | 46 | CARRERAXESTUD, PENSUM, PERIODO, CARRERAS, DATOSDOCENTE, ACTIVAREXAMEN, PARALELOS, CARRERAXDOCENTE, MATRICULAACTUALPROVISIONAL, DATOS_ESTUD | DELETE:3, INSERT:2, SELECT:120, UPDATE:235 | portal_academico.py, sisacademico_admin.py, matricula_materias, fechas_notas, moodle_notas, moodle_sincronizacion |
| Practicas y vinculacion con la sociedad | base | 8 | PRACTICASVINCULACION, DATOSDOCENTE, DATOS_ESTUD, PRACTICASPROFESIONALES, EMPRESA, PERIODO, CARRERAS, PROYECTO | DELETE:8, INSERT:10, SELECT:31, UPDATE:26 | practicas_institucionales.py, sisacademico_admin.py, practicas, practicas_vinculacion, empresas |
| Repositorio y documentos | base | 30 | REPOSITORIO, DATOS_ESTUD, REG_MENU_C_FORO, CARRERAS, DATOSNOMIGRADOS, PERIODO, CARRERAXDOCENTE, ENCABEZADO, RETENCIONENCABEZADO, ENCABEZADOFACTURAS | DELETE:14, INSERT:9, SELECT:29, UPDATE:18 | sisacademico_admin.py, repositorio, registro_documentos_estudiante |
| Seguridad, usuarios y menu | base | 20 | USUARIO_SIS, MENU_GENERAL, MENU_USUARIOS, TIPOINGRESO, CONTROLINGRESO, CARRERAS, CORREOSESTUDINTEC, USUARIOS, THE | DELETE:2, INSERT:6, SELECT:19, UPDATE:14 | auth.py, sisacademico_admin.py, usuarios, menu_usuarios, menu_general |
| Soporte legacy no migrable | excluded | 14 | - | - | - |
| Talento humano | base | 0 | - | - | sisacademico_admin.py, talento_humano_empleados, talento_humano_solicitudes, talento_humano_tareas |
| Titulacion, complexivo y defensa | partial | 19 | CARRERAXESTUD, PERIODO, DATOS_ESTUD, PENSUM, CARRERAS, CABECERA_MATRICULA, CARRERA_ESTUD_MES, MALLA_PENSUM, VALOR_CRED, USUARIOS | DELETE:4, INSERT:2, SELECT:25, UPDATE:35 | titulacion.py, titulos_registrados.py, certificados_generados, fecha_grado, titulacion |

## Detalle por modulo

### Catalogos academicos

- Clave: `academico`
- Estado: `base`
- Artefactos: `22`
- Rutas backend modernas: sisacademico_admin.py
- Secciones frontend/admin modernas: carreras, materias, mallas, materia_homo_textof, periodos, paralelos, jornadas, modalidades, provincias
- Tablas configuradas: CARRERAS, PENSUM, MALLA_PENSUM, MATERIAHOMOTEXTOF, PERIODO, PARALELOS, JORNADA, ModalidadMatricula, Provincias
- Tablas detectadas: CARRERAXESTUD, CARRERAS, PERIODO, PENSUM, MALLA_PENSUM, EMPRESA, REQ_EXAMENES_ESTUD, MATERIAHOMOTEXTOF, PROVINCIAS, DATOS_ESTUD, REG_TIPOLIC_ESTUD, REQ_EXAMENES, PARALELOS, MODALIDADMATRICULA
- Operaciones SQL: DELETE:17, INSERT:10, SELECT:33, UPDATE:66
- Referencias de reporte: -
- Nota: Mantenimiento directo expuesto; reglas complejas se deben mover a endpoints dedicados.

### Admision y preinscripcion

- Clave: `admision`
- Estado: `base`
- Artefactos: `17`
- Rutas backend modernas: preinscription.py, sisacademico_admin.py
- Secciones frontend/admin modernas: preinscripciones, datos_factura
- Tablas configuradas: PREINSCRIPCION, DATOSFACTURA, IN_LECONTACTO, IN_ENTERO, IN_DESEAINGRESAR, IN_DESCCONVE, IN_DESCONVVALOR, IN_DESDEPOTRANS
- Tablas detectadas: PREINSCRIPCION, PERIODO, CABECERA_MATRICULA, DATOS_ESTUD, MODALIDADMATRICULA, DATOSFACTURA, CORREOSESTUDINTEC, IN_LECONTACTO, IN_ENTERO, IN_DESEAINGRESAR, IN_DESCCONVE, IN_DESCONVVALOR, IN_DESDEPOTRANS, PENSUM, CARRERAXESTUD, CARRERAS, PROVINCIAS, JORNADA, USUARIO_SIS, TIPODOCUMENTOS
- Operaciones SQL: INSERT:18, SELECT:78, UPDATE:10
- Referencias de reporte: -
- Nota: El flujo moderno de preinscripcion reemplaza formularios duplicados de WebForms.

### Certificados y reportes

- Clave: `certificados`
- Estado: `base`
- Artefactos: `74`
- Rutas backend modernas: certificados.py, credential_generator.py, legacy_reports.py, sisacademico_admin.py
- Secciones frontend/admin modernas: certificados_generados, credenciales_curso
- Tablas configuradas: CERTIFICADOS_GENERADOS, CREDENCIALES_CURSO
- Tablas detectadas: DATOS_ESTUD, PERIODO, CARRERAXESTUD, CARRERAS, PREINSCRIPCION, CABECERA_MATRICULA, MAXNIVELESTUDIANTE, NOTASMAXIMACARRERA, USUARIOS, FALTASJUSTINJUS, DATOSFACTURA, CURSOSEDUCONTINUA, PENSUM
- Operaciones SQL: SELECT:52, UPDATE:4
- Referencias de reporte: /CryAcadxEstud.rpt, /CryAcadxEstudHomo.rpt, /ReporteAcad/CryAcadxEstud.rpt, /ReporteAcad/CryAcadxEstudGeneral.rpt, /ReporteAcad/CryAcadxEstudGeneralPASE.rpt, /ReporteAcad/CryAcadxEstudv1.rpt, /ReporteAcad/CryEncuestaPorEstud.rpt, /ReporteAcad/CryListaTotalEstudNumMat.rpt, /ReporteAcad/ReporteAcad.rpt, /Reporteshtml/CryEstudPeriodoHorario.rpt, /Reporteshtml/CryEstudPeriodoHorarioNivel.rpt, /Reporteshtml/CryEstudPeriodoOnline.rpt, /SisAcademicoV1/CryAcadxEstud.rpt, /SisAcademicoV1/CryAcadxEstudHomo.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudAnioCarrera.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudAnioEstado.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudAnioGenero.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudAnioProvincia.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudModalidadCNE.rpt, /SisAcademicoV1/ReporteAcad/CryListaTotalEstudPeriodo.rpt
- Nota: Los reportes heredados se reemplazan por PDF/Excel/HTML moderno, no se copia el motor Crystal.

### Docentes y asignaciones

- Clave: `docentes`
- Estado: `base`
- Artefactos: `14`
- Rutas backend modernas: teacher_evaluation.py, sisacademico_admin.py
- Secciones frontend/admin modernas: docentes, actualizacion_est, docente_materias
- Tablas configuradas: DATOSDOCENTE, USUARIOS, CARRERAXDOCENTE, CONTRATOSDOCENTE
- Tablas detectadas: DATOSDOCENTE, CARRERAXDOCENTE, USUARIOS, PERIODO, CARRERAS, PARALELOS, PENSUM, JORNADA, MALLA_PENSUM
- Operaciones SQL: DELETE:9, INSERT:9, SELECT:27, UPDATE:33
- Referencias de reporte: /ReporteAcad/CrysListaProfesorMateria.rpt
- Nota: No sobrescribir el parche docente actual; se mantiene como puente seguro.

### Educacion continua

- Clave: `educacion_continua`
- Estado: `base`
- Artefactos: `20`
- Rutas backend modernas: sisacademico_admin.py
- Secciones frontend/admin modernas: cursos_edu_continua, corte_curso, corte_curso_estudiante, credenciales_curso
- Tablas configuradas: CursosEduContinua, CORTE_CURSO, CORTE_CURSO_ESTUDIANTE, CABECERAEDUCONTINUA, EstudiantesEdContinua
- Tablas detectadas: DATOS_ESTUD, PENSUM, CARRERAS, CARRERAXESTUD, JORNADA, PERIODO, USUARIOS, PRACTICASPROFESIONALES, REPOSITORIO, MODALIDADMATRICULA, ESTUDIANTESEDCONTINUA, CABECERA_MATRICULA, CABECERA_MATRICULA_VARIOS, MALLA_PENSUM, CABECERAEDUCONTINUA, CURSOSEDUCONTINUA, NUMACTAGRADOESTUD, DIASMATRICULA, CARRERA_ESTUD_MES
- Operaciones SQL: DELETE:8, INSERT:20, SELECT:45, UPDATE:29
- Referencias de reporte: -
- Nota: Falta una vista dedicada si se requiere flujo completo de inscripcion y certificacion.

### Estudiantes y ficha academica

- Clave: `estudiantes`
- Estado: `base`
- Artefactos: `15`
- Rutas backend modernas: students.py, sisacademico_admin.py
- Secciones frontend/admin modernas: estudiantes, actualizacion_estudiantes, registro_documentos_estudiante, correos, seguimiento
- Tablas configuradas: DATOS_ESTUD, CorreosEstudIntec, REGISTRODOCESTUD, ESTADO
- Tablas detectadas: DATOS_ESTUD, REGISTRODOCESTUD, CORREOSESTUDINTEC, PREINSCRIPCION, CABECERA_MATRICULA, PERIODO, PRACTICASPROFESIONALES, ESTADO, CARRERAXESTUD, CARRERAS, USUARIOS, PROVINCIAS
- Operaciones SQL: DELETE:6, INSERT:16, SELECT:31, UPDATE:47
- Referencias de reporte: -
- Nota: Se mantiene INTECBDD como fuente; cargas nuevas deben pasar por backend validado.

### Evaluacion docente y cuestionarios

- Clave: `evaluacion_docente`
- Estado: `base`
- Artefactos: `50`
- Rutas backend modernas: teacher_evaluation.py, sisacademico_admin.py
- Secciones frontend/admin modernas: numero_preguntas, cuestionarios, preguntas_evaluacion, evaluacion_resultados, autoevaluacion_resultados, fechas_autoevaluacion, planes_foros
- Tablas configuradas: CUESTIONARIO, CUESTIONARIOEVALUA, NUMEROPREGALEAT, RESULTADO_EVALUACION, RESULTADOAUTOEVALUACION, ACTIVARAUTOEVALUACION
- Tablas detectadas: PERIODO, CARRERAXDOCENTE, PENSUM, CARRERAS, DATOSDOCENTE, CUESTIONARIO, CARRERAXESTUD, RESULTADOAUTOEVALUACION, ACTIVARAUTOEVALUACION, NUMEROPREGALEAT, CUESTIONARIOEVALUA, RESULTADO_EVALUACION, REG_MENU_C_FORO, NO_UNIDADES, ACTIVAREXAMEN, CURSO, DB_A1FCF8_CENESTURBDD_ADMIN, PARALELOS, USUARIO_SIS, ACTIVARENCUESTAS, PERIODO_ACAD, MATERIACURSO, DATOS_DOCENTE, ANIO, TIPOCURSO, MALLA_PENSUM, CUESTIONARIOFINAL, REG_CUES_FORO_DOC
- Operaciones SQL: DELETE:7, INSERT:11, SELECT:86, UPDATE:125
- Referencias de reporte: /EncuestaDocEstud/Reportes/CryEstudEvaluaProfe.rpt, /EncuestaDocEstud/Reportes/CryEstudEvaluaProfeAgrupado.rpt, /EncuestaDocEstud/Reportes/CryEvaluaciondocente.rpt, /EncuestaDocEstud/Reportes/CryNumEstudEvaluaProfe.rpt, /EncuestaDocEstud/Reportes/EstudNOEvaluaProfe.rpt, /sistemaweb/SistemaWeb/EncuestaCadetes/CryRepEncuesta.rpt
- Nota: El motor moderno de evaluacion debe prevalecer; tablas V1 quedan como fuente historica y administrable.

### Financiero, pagos y convenios

- Clave: `financiero_convenios`
- Estado: `base`
- Artefactos: `9`
- Rutas backend modernas: preinscription.py, legacy_reports.py, sisacademico_admin.py
- Secciones frontend/admin modernas: pagos_matricula, datos_factura
- Tablas configuradas: REGISTROPAGOS, DATOSFACTURA, CABECERA_MATRICULA
- Tablas detectadas: REGISTROPAGOS, DATOS_ESTUD, PERIODO, CARRERAS
- Operaciones SQL: INSERT:1, SELECT:10, UPDATE:2
- Referencias de reporte: /RepFinanciero/CryConvenioPagos.rpt
- Nota: Los convenios se generan como PDF moderno y los adjuntos deben subirse por endpoint controlado.

### Integraciones Moodle y Microsoft 365

- Clave: `integraciones`
- Estado: `base`
- Artefactos: `8`
- Rutas backend modernas: teams.py, mass_email.py, credential_generator.py, sisacademico_admin.py
- Secciones frontend/admin modernas: moodle_notas, moodle_sincronizacion, microsoft365_audit, credenciales_curso
- Tablas configuradas: intec_estudiantenota, intec_logmatriculacion, intec_moodlegradesynclog, Microsoft365Audit, CREDENCIALES_CURSO
- Tablas detectadas: CORREOSESTUDINTEC, PERIODO, REGISTROPAGOS, VB
- Operaciones SQL: SELECT:8, UPDATE:6
- Referencias de reporte: -
- Nota: No exponer tokens ni credenciales; usar variables de entorno.

### Mantenimiento controlado y operaciones sensibles

- Clave: `mantenimiento_controlado`
- Estado: `partial`
- Artefactos: `15`
- Rutas backend modernas: sisacademico_admin.py, academic_enrollment.py, preinscription.py
- Secciones frontend/admin modernas: estudiantes, cabecera_matricula, matricula_materias, preinscripciones
- Tablas configuradas: CARRERAXESTUD, CABECERA_MATRICULA, PREINSCRIPCION, DATOS_ESTUD
- Tablas detectadas: PREINSCRIPCION, CARRERAXESTUD, DATOS_ESTUD, CARRERAS, CABECERA_MATRICULA, MODALIDADMATRICULA, PENSUM, AUXREG, USUARIOS, DATOSFACTURA, CORREOSESTUDINTEC, AUXCEDULA, PROVINCIAS, JORNADA, PERIODO
- Operaciones SQL: DELETE:8, INSERT:2, SELECT:14, UPDATE:7
- Referencias de reporte: /SisAcademicoV1/pruebas/CrystalReport.rpt, /SisAcademicoV1/pruebas/cryprueba.rpt
- Nota: Debe ejecutarse con auditoria, confirmacion y permisos altos; no se replica el boton de eliminar de WebForms.

### Matricula academica y financiera

- Clave: `matricula`
- Estado: `base`
- Artefactos: `26`
- Rutas backend modernas: academic_enrollment.py, sisacademico_admin.py
- Secciones frontend/admin modernas: cabecera_matricula, matricula_materias, pagos_matricula, cambio_periodo_hr
- Tablas configuradas: CABECERA_MATRICULA, CARRERAXESTUD, REGISTROPAGOS, CONTROLMATRICULA, ESTADOMATRICULA
- Tablas detectadas: CARRERAXESTUD, CABECERA_MATRICULA, PERIODO, PENSUM, CARRERAS, DATOS_ESTUD, MODALIDADMATRICULA, CONTROLMATRICULA, CABECERA_MATRICULA_VARIOS, REGISTROPAGOS, DIASMATRICULA, HORARIOMATRICULA, CARRERA_ESTUD_MES, MALLA_PENSUM, JORNADA, ESTADOMATRICULA, PARALELOS, MATERIAS_CONSECUTIVAS, AUXMATC, TIPO_MATRICULA, VALOR_CRED, CORREOSESTUDINTEC
- Operaciones SQL: DELETE:21, INSERT:23, SELECT:90, UPDATE:100
- Referencias de reporte: -
- Nota: Las operaciones transaccionales deben permanecer en backend; el CRUD generico queda para mantenimiento.

### Notas y apertura de calificaciones

- Clave: `notas`
- Estado: `partial`
- Artefactos: `46`
- Rutas backend modernas: portal_academico.py, sisacademico_admin.py
- Secciones frontend/admin modernas: matricula_materias, fechas_notas, moodle_notas, moodle_sincronizacion
- Tablas configuradas: CARRERAXESTUD, CARRERAXDOCENTE, ACTIVAREXAMEN, intec_estudiantenota, intec_moodlegradesynclog
- Tablas detectadas: CARRERAXESTUD, PENSUM, PERIODO, CARRERAS, DATOSDOCENTE, ACTIVAREXAMEN, PARALELOS, CARRERAXDOCENTE, MATRICULAACTUALPROVISIONAL, DATOS_ESTUD, MALLA_PENSUM, CABECERA_MATRICULA, MODALIDADMATRICULA, JORNADA, TIPO_MATRICULA
- Operaciones SQL: DELETE:3, INSERT:2, SELECT:120, UPDATE:235
- Referencias de reporte: -
- Nota: Lectura, reportes y administracion base estan cubiertas; falta cerrar ingreso masivo de notas V1 como flujo dedicado.

### Practicas y vinculacion con la sociedad

- Clave: `practicas`
- Estado: `base`
- Artefactos: `8`
- Rutas backend modernas: practicas_institucionales.py, sisacademico_admin.py
- Secciones frontend/admin modernas: practicas, practicas_vinculacion, empresas
- Tablas configuradas: PRACTICASPROFESIONALES, PRACTICASVINCULACION, EMPRESA, Proyecto
- Tablas detectadas: PRACTICASVINCULACION, DATOSDOCENTE, DATOS_ESTUD, PRACTICASPROFESIONALES, EMPRESA, PERIODO, CARRERAS, PROYECTO
- Operaciones SQL: DELETE:8, INSERT:10, SELECT:31, UPDATE:26
- Referencias de reporte: -
- Nota: El modulo independiente puede reconocer datos legacy sin eliminarlos.

### Repositorio y documentos

- Clave: `repositorio`
- Estado: `base`
- Artefactos: `30`
- Rutas backend modernas: sisacademico_admin.py
- Secciones frontend/admin modernas: repositorio, registro_documentos_estudiante
- Tablas configuradas: REPOSITORIO, REGISTRODOCESTUD, TAMANIOARCHIVOS, TIPODOCUMENTOS
- Tablas detectadas: REPOSITORIO, DATOS_ESTUD, REG_MENU_C_FORO, CARRERAS, DATOSNOMIGRADOS, PERIODO, CARRERAXDOCENTE, ENCABEZADO, RETENCIONENCABEZADO, ENCABEZADOFACTURAS, REGISTRODOCELECTRONICOS, ENCABEZADONOTASENTREGA, CORREOSESTUDINTEC, CARRERAXESTUD, CABECERA_MATRICULA, DATOSDOCENTE, TAMANIOARCHIVOS, PENSUM, PREINSCRIPCION
- Operaciones SQL: DELETE:14, INSERT:9, SELECT:29, UPDATE:18
- Referencias de reporte: -
- Nota: Los archivos historicos se conservan; nuevas cargas deben pasar por backend validado.

### Seguridad, usuarios y menu

- Clave: `seguridad`
- Estado: `base`
- Artefactos: `20`
- Rutas backend modernas: auth.py, sisacademico_admin.py
- Secciones frontend/admin modernas: usuarios, menu_usuarios, menu_general
- Tablas configuradas: USUARIOS, USUARIO_SIS, TIPO_USUARIO, MENU_GENERAL, MENU_TIPO_USU, MENU_USUARIOS
- Tablas detectadas: USUARIO_SIS, MENU_GENERAL, MENU_USUARIOS, TIPOINGRESO, CONTROLINGRESO, CARRERAS, CORREOSESTUDINTEC, USUARIOS, THE
- Operaciones SQL: DELETE:2, INSERT:6, SELECT:19, UPDATE:14
- Referencias de reporte: -
- Nota: El login WebForms no se copia; se conserva autenticacion moderna y datos legacy administrables.

### Soporte legacy no migrable

- Clave: `soporte_legacy_no_migrable`
- Estado: `excluded`
- Artefactos: `14`
- Rutas backend modernas: -
- Secciones frontend/admin modernas: -
- Tablas configuradas: -
- Tablas detectadas: -
- Operaciones SQL: -
- Referencias de reporte: CrystalDecisions.Shared.Rpt, CrystalDecisions.Web.Compilation.Rpt
- Nota: Se conserva como referencia historica del proyecto, pero no se clona en backend/frontend moderno.

### Talento humano

- Clave: `talento_humano`
- Estado: `base`
- Artefactos: `0`
- Rutas backend modernas: sisacademico_admin.py
- Secciones frontend/admin modernas: talento_humano_empleados, talento_humano_solicitudes, talento_humano_tareas
- Tablas configuradas: TH_EMPLEADO, TH_JEFATURA, TH_SOLICITUD, TH_SOLICITUD_ARCHIVO, TH_TAREA, TH_TIPO_SOLICITUD
- Tablas detectadas: -
- Operaciones SQL: -
- Referencias de reporte: -
- Nota: Los binarios de solicitud deben descargarse mediante endpoint dedicado, no en listados.

### Titulacion, complexivo y defensa

- Clave: `titulacion`
- Estado: `partial`
- Artefactos: `19`
- Rutas backend modernas: titulacion.py, titulos_registrados.py
- Secciones frontend/admin modernas: certificados_generados, fecha_grado, titulacion
- Tablas configuradas: CARRERAXESTUD, CABECERA_MATRICULA, PENSUM, MALLA_PENSUM, CERTIFICADOS_GENERADOS
- Tablas detectadas: CARRERAXESTUD, PERIODO, DATOS_ESTUD, PENSUM, CARRERAS, CABECERA_MATRICULA, CARRERA_ESTUD_MES, MALLA_PENSUM, VALOR_CRED, USUARIOS
- Operaciones SQL: DELETE:4, INSERT:2, SELECT:25, UPDATE:35
- Referencias de reporte: /SisAcademicoV1/certificados/certificado.rpt, /SisAcademicoV1/certificados/certificadoEdContinua.rpt, /SisAcademicoV1/certificados/certificadosf.rpt, /certificados/certificado.rpt, /certificados/certificadosf.rpt
- Nota: La verificacion y proceso moderno estan en desarrollo; se conserva lectura legacy.

## Archivos de mantenimiento sensible

Estos archivos no deben clonarse como botones directos. Deben convertirse en operaciones auditadas, con confirmacion y permisos altos.

| Archivo | Modulo | Operaciones | Tablas |
|---|---|---|---|
| `accesousuarios/Accesousuarios.aspx.vb` | seguridad | DELETE, INSERT, SELECT, UPDATE | CARRERAS, MENU_GENERAL, MENU_USUARIOS, USUARIO_SIS |
| `Actualiza_Estud.aspx.vb` | estudiantes | DELETE, INSERT, SELECT, UPDATE | CORREOSESTUDINTEC, DATOS_ESTUD, ESTADO, REGISTRODOCESTUD |
| `Actualiza_EstudPeriodo.aspx.vb` | estudiantes | DELETE, INSERT, SELECT, UPDATE | CABECERA_MATRICULA, CARRERAS, CARRERAXESTUD, CORREOSESTUDINTEC, DATOS_ESTUD, ESTADO, PERIODO, PREINSCRIPCION, REGISTRODOCESTUD |
| `Actualiza_Examenes.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | DATOS_ESTUD, REG_TIPOLIC_ESTUD, REQ_EXAMENES, REQ_EXAMENES_ESTUD |
| `actualizar/CopiarMaterias.aspx` | mantenimiento_controlado | - | - |
| `actualizar/CopiarMaterias.aspx.vb` | mantenimiento_controlado | INSERT, SELECT, UPDATE | AUXREG, CARRERAS, CARRERAXESTUD, PENSUM |
| `actualizar/EliminarEstud.aspx` | mantenimiento_controlado | - | - |
| `actualizar/EliminarEstud.aspx.vb` | mantenimiento_controlado | DELETE | DATOS_ESTUD, USUARIOS |
| `actualizar/EliminarMatricula.aspx` | matricula | - | - |
| `actualizar/EliminarMatricula.aspx.vb` | matricula | DELETE, SELECT | CABECERA_MATRICULA, CARRERAS, CARRERAXESTUD, DATOS_ESTUD, PERIODO |
| `actualizar/EliminarPreMatricula.aspx` | mantenimiento_controlado | - | - |
| `actualizar/EliminarPreMatricula.aspx.vb` | mantenimiento_controlado | DELETE, SELECT | CABECERA_MATRICULA, CARRERAXESTUD, CORREOSESTUDINTEC, DATOSFACTURA, DATOS_ESTUD, PREINSCRIPCION |
| `actualizar/EliminarProfe.aspx` | docentes | - | - |
| `actualizar/EliminarProfe.aspx.vb` | docentes | DELETE, SELECT | CARRERAXDOCENTE, DATOSDOCENTE, USUARIOS |
| `ActualizarProfe.aspx.vb` | docentes | DELETE, INSERT, SELECT, UPDATE | CARRERAS, CARRERAXDOCENTE, DATOSDOCENTE, JORNADA, MALLA_PENSUM, PARALELOS, PENSUM, PERIODO |
| `autoridades/NuevoProfe.aspx.vb` | docentes | DELETE, INSERT, SELECT, UPDATE | CARRERAS, CARRERAXDOCENTE, DATOSDOCENTE, PARALELOS, PENSUM, PERIODO, USUARIOS |
| `Carreras.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | CARRERAS |
| `fechasingresonotas/IngFechasAutoevaluacion.aspx.vb` | evaluacion_docente | DELETE, INSERT, SELECT, UPDATE | ACTIVARAUTOEVALUACION, PERIODO |
| `fechasingresonotas/IngFechasIngNotas.aspx.vb` | notas | DELETE, INSERT, SELECT, UPDATE | ACTIVAREXAMEN, PERIODO |
| `fechasingresonotas/ListaPeriodoAnteriorActual.aspx.vb` | notas | DELETE, INSERT, SELECT, UPDATE | CABECERA_MATRICULA, CARRERAS, CARRERAXESTUD, MATRICULAACTUALPROVISIONAL, PERIODO |
| `IngresarCurso.aspx.vb` | educacion_continua | DELETE, INSERT, SELECT, UPDATE | CARRERAS, MALLA_PENSUM, PENSUM |
| `IngresarMaterias.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | CARRERAS, MALLA_PENSUM, PENSUM |
| `IngresoDiasMatricula.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | DIASMATRICULA |
| `IngresoEmpresas.aspx.vb` | practicas | DELETE, INSERT, SELECT, UPDATE | EMPRESA |
| `IngresoHorasMatricula.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | HORARIOMATRICULA |
| `IngresoMallaCarrera.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | CARRERAS, MALLA_PENSUM |
| `IngresoMateriahomoTexto.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | MATERIAHOMOTEXTOF, PENSUM, PERIODO |
| `IngresoModalidadMatricula.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | MODALIDADMATRICULA |
| `IngresoParalelos.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | PARALELOS, PERIODO |
| `Ingresoproyecto.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | EMPRESA |
| `inscripciones/Ingresorepositorio.aspx.vb` | educacion_continua | DELETE, INSERT, SELECT, UPDATE | CARRERAS, REPOSITORIO |
| `inscripciones/MatriculaIngles.aspx.vb` | educacion_continua | DELETE, INSERT, SELECT, UPDATE | CABECERA_MATRICULA, CABECERA_MATRICULA_VARIOS, CARRERAS, CARRERAXESTUD, CARRERA_ESTUD_MES, DIASMATRICULA, JORNADA, MODALIDADMATRICULA, PENSUM, PERIODO |
| `MatriculaComplexivo.aspx.vb` | titulacion | DELETE, INSERT, SELECT, UPDATE | CARRERAS, CARRERAXESTUD, CARRERA_ESTUD_MES, DATOS_ESTUD, MALLA_PENSUM, PENSUM, PERIODO, USUARIOS, VALOR_CRED |
| `ModificarMaterias.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | AUXMATC, CABECERA_MATRICULA, CABECERA_MATRICULA_VARIOS, CARRERAS, CARRERAXESTUD, CARRERA_ESTUD_MES, CONTROLMATRICULA, DATOS_ESTUD, MALLA_PENSUM, MATERIAS_CONSECUTIVAS, MODALIDADMATRICULA, PARALELOS |
| `ModificarMateriasConvalida.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | CABECERA_MATRICULA, CARRERAS, CARRERAXESTUD, CARRERA_ESTUD_MES, CORREOSESTUDINTEC, DATOS_ESTUD, MALLA_PENSUM, PENSUM, PERIODO, TIPO_MATRICULA, VALOR_CRED |
| `ModificarMateriasHaR.aspx.vb` | matricula | DELETE, INSERT, SELECT, UPDATE | AUXMATC, CABECERA_MATRICULA, CABECERA_MATRICULA_VARIOS, CARRERAS, CARRERAXESTUD, CARRERA_ESTUD_MES, CONTROLMATRICULA, DATOS_ESTUD, MALLA_PENSUM, MATERIAS_CONSECUTIVAS, MODALIDADMATRICULA, PARALELOS |
| `NuevoProfe.aspx.vb` | docentes | DELETE, INSERT, SELECT, UPDATE | CARRERAS, CARRERAXDOCENTE, DATOSDOCENTE, PARALELOS, PENSUM, PERIODO, USUARIOS |
| `numpreguntas/ControlCuestionarios.aspx.vb` | evaluacion_docente | DELETE, INSERT, SELECT, UPDATE | CARRERAS, MALLA_PENSUM, NUMEROPREGALEAT, PENSUM, PERIODO |
| `PeriodosAcademicos.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | PERIODO |
| `planes/Subirarchivos.aspx.vb` | repositorio | DELETE, INSERT, SELECT, UPDATE | CARRERAS, CARRERAXDOCENTE, DATOSDOCENTE, PERIODO, REG_MENU_C_FORO, TAMANIOARCHIVOS |
| `PracticasProfesionales.aspx.vb` | practicas | DELETE, INSERT, SELECT, UPDATE | CARRERAS, DATOSDOCENTE, DATOS_ESTUD, EMPRESA, PERIODO, PRACTICASPROFESIONALES |
| `PracticasVinculacion.aspx.vb` | practicas | DELETE, INSERT, SELECT, UPDATE | CARRERAS, DATOSDOCENTE, DATOS_ESTUD, PERIODO, PRACTICASVINCULACION, PROYECTO |
| `Provincias.aspx.vb` | academico | DELETE, INSERT, SELECT, UPDATE | PERIODO, PROVINCIAS |
| `Registropagos.aspx.vb` | matricula | DELETE, INSERT, SELECT | CARRERAS, DATOS_ESTUD, PERIODO, REGISTROPAGOS |
| `repositorio/Ingresorepositorio.aspx.vb` | repositorio | DELETE, INSERT, SELECT, UPDATE | CARRERAS, REPOSITORIO |
| `SUBIRARCHIVO/EnviararchivoLista.aspx.vb` | repositorio | DELETE, INSERT, SELECT | CABECERA_MATRICULA, CARRERAXESTUD, CORREOSESTUDINTEC, DATOSNOMIGRADOS, DATOS_ESTUD, PENSUM, PERIODO, PREINSCRIPCION |
| `SubirCuestionario.aspx.vb` | evaluacion_docente | DELETE, INSERT, SELECT, UPDATE | CARRERAXDOCENTE, CUESTIONARIO, CUESTIONARIOFINAL, NO_UNIDADES, NUMEROPREGALEAT, REG_CUES_FORO_DOC, REG_MENU_C_FORO |
| `Vinculacion.aspx.vb` | practicas | DELETE, INSERT, SELECT, UPDATE | CARRERAS, DATOSDOCENTE, DATOS_ESTUD, EMPRESA, PERIODO, PRACTICASVINCULACION |

## Plan para documentos PDF sin Crystal Reports

1. Tomar cada familia `.rpt` como referencia de columnas, filtros y layout.
2. Reconstruir el dataset en SQL parametrizado dentro de FastAPI.
3. Generar PDF con reportlab o equivalente ya usado por el backend.
4. Generar Excel con openpyxl cuando el reporte sea tabular.
5. Validar visualmente contra formatos de Secretaria, Financiero o Coordinacion.
6. Mantener endpoints antiguos solo como alias de compatibilidad, nunca como ejecucion Crystal.
