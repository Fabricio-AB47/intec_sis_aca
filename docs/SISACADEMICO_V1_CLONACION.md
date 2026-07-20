# SisAcademicoV1 - Analisis y plan de clonacion moderna

## Objetivo

Clonar funcionalmente `SisAcademicoV1` dentro del sistema actual `intec_sis_aca`, respetando la arquitectura existente:

- Backend: FastAPI en `backend/app/routers`, servicios en `backend/app/services` y conexion principal a `INTECBDD`.
- Frontend: React/Vite en `frontend/src/features/matricula` y navegacion en `frontend/src/components/StudentLayout.tsx`.
- Base de datos: mantener `INTECBDD` como base principal y aplicar solo parches complementarios, no destructivos e idempotentes.
- Docencia: no romper el parche docente actual; las funciones docentes se integran como continuidad, no reemplazo brusco.

## Lectura general del proyecto V1

`SisAcademicoV1` es una aplicacion ASP.NET WebForms/VB.NET que trabaja casi directamente contra SQL Server. La mayor parte de la logica esta embebida en archivos `.aspx.vb` con consultas SQL directas. El proyecto contiene:

- 186 paginas `.aspx`.
- 178 archivos `.vb`.
- 39 reportes heredados `.rpt` que no se ejecutan en el sistema nuevo.
- Miles de archivos historicos subidos (`pdf`, `jpg`, `docx`, `zip`, etc.).
- Configuracion en `Web.config` con conexion directa a `INTECBDD`.
- Tablas principales y tablas complementarias incluidas en `sistema_acad_fot.sql`.

No se deben copiar credenciales desde `Web.config`. La version moderna debe seguir usando variables `.env`.

## Componentes funcionales detectados

### 1. Seguridad, acceso y menu

**V1**

- `Default.aspx`, `Index.aspx`, `Cabecera.aspx`, `izquierda.aspx`.
- `accesousuarios/NuevoUsuario.aspx`.
- `accesousuarios/Accesousuarios.aspx`.

**Tablas**

- `USUARIOS`
- `USUARIO_SIS`
- `TIPO_USUARIO`
- `MENU_GENERAL`
- `MENU_TIPO_USU`
- `MENU_USUARIOS`
- `ControlIngreso`
- `TIPOINGRESO`

**Clonacion moderna**

- Mantener login centralizado en `auth.py`.
- Mantener menus por rol en `StudentLayout.tsx`.
- Exponer mantenimiento legacy mediante `sisacademico_admin.py`.
- No migrar el login WebForms; se reemplaza por autenticacion moderna.

### 2. Estudiantes y ficha academica

**V1**

- `IngNuevoEstudianteWeb.aspx`
- `Actualiza_Estud.aspx`
- `Actualiza_EstudPeriodo.aspx`
- `Actualiza_Informacion.aspx`
- `ImprimirEstudianteWeb.aspx`
- `SubirDocumentos.aspx`

**Tablas**

- `DATOS_ESTUD`
- `CorreosEstudIntec`
- `REGISTRODOCESTUD`
- `ESTADO`
- `Provincias`, `Canton`, `Pais`, `Sexo`, `EstadoCivil`
- catalogos SENESCYT y datos socioeconomicos

**Clonacion moderna**

- Ya existe: `students.py`, `ActualizarDatosEstudianteView.tsx`, `GestionSisAcademicoView.tsx`.
- Mantener CRUD generico para tablas legacy.
- Agregar vistas especializadas cuando el flujo sea operativo, no solo mantenimiento.

### 3. Admision, preinscripcion y asesores

**V1**

- `Inscripcion.aspx`
- `InscripcionPre.aspx`
- `Datosprematricula.aspx`
- `AsignaAsesor.aspx`
- `AsesorEstudiante.aspx`
- `InscripcionSAEC/*`

**Tablas**

- `PREINSCRIPCION`
- `DATOSFACTURA`
- `IN_LECONTACTO`
- `IN_ENTERO`
- `IN_DESEAINGRESAR`
- `IN_DESCCONVE`
- `IN_DESCONVVALOR`
- `IN_DESDEPOTRANS`
- `INSCRIPCION_SOLICITUD_PAGO`

**Clonacion moderna**

- Ya existe: `preinscription.py` y `PreinscripcionView.tsx`.
- Complementar catalogos V1 en `sisacademico_admin.py`.
- Mantener el flujo actual como principal y usar tablas legacy como fuente.

### 4. Matricula academica y financiera

**V1**

- `Datosprematricula.aspx`
- `ModificarMaterias.aspx`
- `ModificarMateriasHaR.aspx`
- `ModificarMateriasConvalida.aspx`
- `MatriculaComplexivo.aspx`
- `Registropagos.aspx`
- `RegistropagosFin.aspx`
- `SubirArchivoConenioPagos.aspx`

**Tablas**

- `CABECERA_MATRICULA`
- `CARRERAXESTUD`
- `REGISTROPAGOS`
- `CABECERA_MATRICULA_VARIOS`
- `CONTROLMATRICULA`
- `ESTADOMATRICULA`
- `TIPO_MATRICULA`
- `valor_matricula`
- `ValorCredito`
- `PensionDiferida`

**Reglas relevantes**

- Matricula regular `R`: se evalua con parciales `Nota1`, `Nota2`, `Nota3` y promedio/final.
- Homologacion `H`: se evalua con teorico/practico y final.
- Aprobacion: nota final mayor o igual a 7 sobre 10.

**Clonacion moderna**

- Ya existe: `academic_enrollment.py`, `MatriculaAcadView.tsx`, `GestionSisAcademicoView.tsx`.
- Mantener calculos centralizados en backend para evitar reglas duplicadas en frontend.
- Crear endpoints especializados para matricula cuando la operacion requiera transacciones.

### 5. Carreras, malla, pensum y catalogos academicos

**V1**

- `Carreras.aspx`
- `IngresarMaterias.aspx`
- `IngresarCurso.aspx`
- `IngresoMallaCarrera.aspx`
- `IngresoParalelos.aspx`
- `PeriodosAcademicos.aspx`
- `IngresoMateriahomoTexto.aspx`

**Tablas**

- `CARRERAS`
- `PENSUM`
- `MALLA_PENSUM`
- `MATERIAHOMOTEXTOF`
- `MATERIAS_CONSECUTIVAS`
- `PERIODO`
- `PARALELOS`, `Paralelo`
- `JORNADA`, `JornadaCarrera`
- `ModalidadMatricula`, `ModalidadCarrera`

**Clonacion moderna**

- Ya cubierto en gran parte por `sisacademico_admin.py`.
- Agregar validaciones de integridad antes de crear/editar materias y mallas.

### 6. Notas, evaluaciones y apertura de periodos

**V1**

- `IngNotasAsignatura.aspx`
- `IngNotasAsignaturaDocente.aspx`
- `IngresoNotasDocente.aspx`
- `IngNotasAsignaturaNO.aspx`
- `IngNotasAsignaturaRepa.aspx`
- `IngNotasAsignaturaConvav1.aspx`
- `fechasingresonotas/IngFechasIngNotas.aspx`
- `BloqueoNotas.aspx`
- `PasarnotasdeIngles.aspx`

**Tablas**

- `CARRERAXESTUD`
- `CARRERAXDOCENTE`
- `ACTIVAREXAMEN`
- `MatriculaActualProvisional`
- `intec_estudiantenota`
- `intec_moodlegradesynclog`

**Clonacion moderna**

- Ya existe visualizacion y administracion de notas.
- Debe mantenerse la regla:
  - `R`: mostrar parciales.
  - `H`: mostrar teorico/practico.
  - aprobado con final >= 7.
- Moodle queda como modulo de integracion, no como sustituto de la tabla oficial.

### 7. Docentes y asignaciones

**V1**

- `NuevoProfe.aspx`
- `IngNuevoDocente.aspx`
- `ActualizarProfe.aspx`
- `ConsultaProfe.aspx`
- `CARRERAXDOCENTE`
- `CONTRATOSDOCENTE`

**Tablas**

- `DATOSDOCENTE`
- `USUARIOS`
- `CARRERAXDOCENTE`
- `CONTRATOSDOCENTE`

**Clonacion moderna**

- Este modulo ya tiene parche docente. No debe ser sobrescrito.
- Se mantiene `actualizacion_est` como puente seguro entre `DATOSDOCENTE` y `USUARIOS`.
- Cualquier mejora docente debe ser incremental y validada contra usuarios existentes.

### 8. Evaluacion docente, autoevaluacion y cuestionarios

**V1**

- `EvaluacionEstud.aspx`
- `AutoEvaluacion.aspx`
- `EncuestaDocEstud/*`
- `CuestionarioVF.aspx`
- `CuestPregOpMult.aspx`
- `SubirCuestionario.aspx`
- `numpreguntas/ControlCuestionarios.aspx`

**Tablas**

- `CUESTIONARIO`
- `CUESTIONARIOEVALUA`
- `NUMEROPREGALEAT`
- `RESULTADO_EVALUACION`
- `RESULTADOAUTOEVALUACION`
- `ACTIVARAUTOEVALUACION`
- `REG_MENU_C_FORO`
- `REG_CUES_FORO_DOC`

**Clonacion moderna**

- Ya existe: `teacher_evaluation.py`, vistas de evaluacion y reportes.
- El sistema moderno debe mantener el motor de ponderacion ya trabajado y exponer tablas V1 solo como respaldo/administracion.

### 9. Practicas preprofesionales y vinculacion con la sociedad

**V1**

- `PracticasProfesionales.aspx`
- `PracticasVinculacion.aspx`
- `Vinculacion.aspx`
- `IngresoEmpresas.aspx`
- `Ingresoproyecto.aspx`

**Tablas**

- `PRACTICASPROFESIONALES`
- `PRACTICASVINCULACION`
- `EMPRESA`
- `Proyecto`
- catalogos de practicas y vinculacion

**Clonacion moderna**

- Ya existe modulo independiente `practicas_institucionales.py`.
- `INTECBDD` se usa como fuente legacy; el nuevo modulo puede reconocer o sincronizar sin eliminar datos V1.
- Nombre visible correcto: "Vinculacion con la sociedad".

### 10. Titulacion, complexivo y defensa

**V1**

- `MatriculaComplexivo.aspx`
- `IngNotasComplexivo.aspx`
- `IngresoFechaGrado.aspx`
- certificados y reportes de grado

**Tablas**

- `CARRERAXESTUD`
- `CABECERA_MATRICULA`
- `MALLA_PENSUM`
- `PENSUM`
- tablas de acta/certificado cuando existan en el parche moderno

**Clonacion moderna**

- Ya existe modulo `titulacion.py` y `TitulacionView.tsx`.
- Flujo moderno requerido:
  1. Verificacion de malla, ingles `A2+ - INTERMEDIATE`, practicas preprofesionales y vinculacion con la sociedad.
  2. Dar paso a egresamiento/proceso.
  3. Seleccionar examen complexivo o defensa de grado.
  4. Registrar responsables/tribunal.
  5. Registrar notas, generar acta y documentos.

### 11. Certificados y reportes modernizados

**V1**

- `certificados/*`
- `ReporteAcad/*`
- `ReporteNotas/*`
- `Reporteshtml/*`
- archivos `.rpt`

**Tablas**

- `CERTIFICADOS_GENERADOS`
- `CREDENCIALES_CURSO`
- multiples vistas de reporte

**Clonacion moderna**

- Crystal Reports no se usa como motor en la plataforma nueva.
- Los `.rpt` quedan solo como referencia historica para validar columnas, filtros y formato.
- Se reemplaza por endpoints de consulta + generacion PDF/Excel/HTML en Python.
- Ya se expusieron certificados generados y credenciales en el administrador moderno.

### 12. Educacion continua

**V1**

- `inscripciones/Inscripcion.aspx`
- reportes de cursos
- certificados de educacion continua

**Tablas**

- `CursosEduContinua`
- `CORTE_CURSO`
- `CORTE_CURSO_ESTUDIANTE`
- `CABECERAEDUCONTINUA`
- `EstudiantesEdContinua`

**Clonacion moderna**

- Se agregaron secciones base en `sisacademico_admin.py`.
- Pendiente: crear flujo dedicado si se requiere inscripcion, cortes, certificados y credenciales con UI propia.

### 13. Repositorio y documentos

**V1**

- `repositorio/*`
- `SUBIRARCHIVO/*`
- `planes/Subirarchivos.aspx`

**Tablas**

- `REPOSITORIO`
- `REGISTRODOCESTUD`
- `TAMANIOARCHIVOS`
- `TIPODOCUMENTOS`

**Clonacion moderna**

- Mantener archivos como almacenamiento historico.
- Exponer metadatos por backend y mover nuevas cargas a un servicio controlado.
- Ya existen secciones de repositorio y documentos del estudiante.

### 14. Integraciones Moodle y Microsoft 365

**V1 / parches posteriores**

- `intec_estudiantenota`
- `intec_logmatriculacion`
- `intec_moodleconfig`
- `intec_moodlegradesynclog`
- `Microsoft365Audit`
- `CREDENCIALES_CURSO`

**Clonacion moderna**

- No exponer secretos como campos editables sin control.
- Usar `.env` para credenciales.
- Mantener auditoria visible.
- Usar routers especificos para operaciones Graph/Moodle si se automatizan.

### 15. Talento humano

**V1 / parches complementarios**

- `TH_EMPLEADO`
- `TH_JEFATURA`
- `TH_SOLICITUD`
- `TH_SOLICITUD_ARCHIVO`
- `TH_TAREA`
- `TH_TIPO_SOLICITUD`
- `TH_USUARIO_ROL_RRHH`

**Clonacion moderna**

- Ya se agregaron secciones base para empleados, solicitudes y tareas.
- Los archivos binarios de solicitudes deben tratarse con cuidado; no conviene descargarlos automaticamente en listados.

## Reportes heredados modernizados

El inventario especifico de reportes heredados `.rpt`, pantallas VB asociadas, filtros heredados y equivalentes modernos se encuentra en:

- `docs/SISACADEMICO_V1_REPORTES_CRYSTAL.md`

Tambien se expone desde backend en:

- `GET /api/students/reporteria-integral/modern-catalog`
- `GET /api/students/reporteria-integral/modern-catalog/{report_key}`
- `GET /api/students/reporteria-integral/crystal-catalog`

Los endpoints `crystal-catalog` quedan solo por compatibilidad y devuelven `deprecated = true`. La ruta operativa es `modern-catalog`.

La regla de clonacion es no ejecutar Crystal Reports en la plataforma nueva. Cada reporte heredado se reconstruye como consulta parametrizada y salida PDF/Excel/HTML con el mismo concepto usado por los reportes modernos existentes.

## Auditoria de clonacion academica

La revision de cobertura de los modulos academicos de `SisAcademicoV1` se encuentra en:

- `docs/SISACADEMICO_V1_AUDITORIA_ACADEMICO.md`
- `docs/SISACADEMICO_V1_AUDITORIA_TOTAL.md`
- `docs/SISACADEMICO_V1_FUNCIONALIDAD_COMPLETA.md`
- `docs/SISACADEMICO_V1_FLUJO_OPERATIVO.md`

Esos documentos separan lo que esta clonado como base, lo que esta parcial, lo no migrable, las tablas detectadas, operaciones SQL, controles WebForms y los pendientes reales de notas, titulacion, educacion continua y reporteria.

## Estrategia de base de datos

### Principios

- `INTECBDD` no se elimina ni se reconstruye.
- Los parches deben ser `IF OBJECT_ID(...) IS NULL` o `CREATE OR ALTER`.
- Si se agregan tablas nuevas, usar prefijos claros o esquemas nuevos solo cuando sea necesario.
- No cambiar collation global.
- No cambiar tipos de columnas existentes sin script de migracion y respaldo.
- No mover datos historicos sin procedimiento reversible.

### Parche complementario recomendado

Crear scripts por modulo:

- `backend/sql/001_sisacademico_v1_compat_views.sql`
- `backend/sql/patches/002_sisacademico_v1_views.sql`
- `backend/sql/patches/003_sisacademico_v1_indexes.sql`

Contenido esperado:

- Vistas normalizadas para frontend moderno.
- Indices no destructivos para consultas frecuentes.
- Procedimientos `CREATE OR ALTER` para operaciones transaccionales.
- No incluir credenciales.

## Mapa hacia la arquitectura nueva

| Area V1 | Backend moderno | Frontend moderno | Estado |
|---|---|---|---|
| Seguridad/menu | `auth.py`, `sisacademico_admin.py` | `StudentLayout.tsx` | Parcial cubierto |
| Estudiantes | `students.py`, `sisacademico_admin.py` | `GestionSisAcademicoView`, `ActualizarDatosEstudianteView` | Cubierto base |
| Preinscripcion | `preinscription.py`, `sisacademico_admin.py` | `PreinscripcionView` | Cubierto base |
| Matricula | `academic_enrollment.py`, `sisacademico_admin.py` | `MatriculaAcadView`, `GestionSisAcademicoView` | Cubierto base |
| Notas | `sisacademico_admin.py`, futuro `grades.py` | `GestionSisAcademicoView`, reportes | Parcial |
| Docentes | `teacher_evaluation.py`, `sisacademico_admin.py` | Docente + evaluacion | No tocar parche |
| Evaluacion docente | `teacher_evaluation.py` | vistas de evaluacion | Cubierto base |
| Practicas/vinculacion | `practicas_institucionales.py` | Practicas institucionales | Cubierto moderno |
| Titulacion | `titulacion.py` | `TitulacionView` | En desarrollo |
| Certificados | `certificados.py`, `sisacademico_admin.py` | Certificados + historial | Parcial |
| Educacion continua | `sisacademico_admin.py`, futuro `educacion_continua.py` | Gestion generica | Base agregada |
| Repositorio | `sisacademico_admin.py` | Gestion generica | Base agregada |
| Integraciones | `credential_generator.py`, `teams.py`, `mass_email.py`, `sisacademico_admin.py` | vistas existentes + gestion | Parcial |
| Talento humano | `sisacademico_admin.py`, futuro `talento_humano.py` | Gestion generica | Base agregada |

## Orden recomendado de clonacion

1. Congelar inventario y tablas activas.
2. Completar metadata de `sisacademico_admin.py` para todas las tablas V1 que se deban administrar.
3. Crear routers especializados solo para procesos con transacciones:
   - matricula
   - notas
   - preinscripcion
   - certificados
   - titulacion
   - educacion continua
4. Crear vistas React dedicadas donde el flujo no sea CRUD simple.
5. Sustituir los reportes heredados por PDF/Excel/HTML moderno.
6. Crear pruebas de lectura para `INTECBDD` y pruebas de escritura en entorno de pruebas.
7. Retirar acceso WebForms solo cuando cada modulo tenga equivalencia validada.

## Riesgos detectados

- SQL embebido y concatenado en VB.NET: riesgo de inyeccion y errores de tipo.
- Credenciales en `Web.config`: deben rotarse y quedarse fuera del repo.
- Reportes heredados: requieren redisenar salida PDF/Excel/HTML sin ejecutar `.rpt`.
- Archivos historicos: no todos tienen metadata completa.
- Tablas con nombres similares (`PARALELOS` y `Paralelo`, `TIPO_SANGRE` y `TipoSangre`).
- Algunas referencias de V1 apuntan a objetos no presentes en el script entregado; deben verificarse contra la base montada.

## Regla de implementacion

La clonacion no debe ser una copia visual de WebForms. Debe conservar comportamiento y datos, pero con:

- endpoints claros,
- UI responsive,
- validacion centralizada,
- transacciones backend,
- permisos por rol,
- logs/auditoria,
- y parches SQL idempotentes.
