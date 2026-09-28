# Revisión funcional del sistema académico

Fecha: 22/09/2026. Alcance: comparación con fuentes oficiales, inspección del repositorio y mejoras incrementales verificadas mediante pruebas. No es una certificación normativa ni una auditoría de todos los datos institucionales.

## Investigación

- [Workday: asesoría y planificación académica](https://www.workday.com/en-us/products/student/advising.html) reúne progreso, planificación, asesoría y acciones pendientes. Aplicación a INTEC: el centro académico debe mostrar trabajo pendiente real y permitir llegar al proceso responsable.
- [Ellucian: auditoría de progreso de titulación](https://anthology-help.ellucian.com/cns/26.2/webclient/content/ws/ar/dpa/degreeprogressaudit/tocdegreeprogressaudit.htm) compara estudios con requisitos de la versión del programa. Aplicación: carrera, pensum y matrícula deben conservar su contexto; no conviene sustituir esa relación por un porcentaje genérico.
- [Moodle: uso de analítica](https://docs.moodle.org/502/en/Using_analytics) distingue modelos, indicadores, contexto y acciones sobre los resultados. Aplicación: una actividad sin entrega no demuestra por sí sola abandono o riesgo; primero deben validarse matrícula, actividad aplicable, fechas y estado académico.

Las prioridades siguientes son conclusiones de la revisión del repositorio, no requisitos impuestos por esos proveedores. No se propone migrar de plataforma ni adquirir otro SIS.

## Cobertura observada

| Capacidad | Evidencia local | Evaluación y decisión |
| --- | --- | --- |
| Admisión e ingreso | `PreinscripcionView`, `IngresoDirectoView` | Existen inscripción, documentos y provisión de cuentas. Conservar; no crear otro registro de personas. |
| Matrícula | `MatriculaAcadView`, matrícula individual/masiva y solicitudes | Existen validaciones y procesos de cambio. Añadida consulta operativa de solicitudes pendientes; no modificar sus aprobaciones. |
| Carrera y pensum | `GestionSisAcademicoView`, `CurriculumUpdaterView` | Hay edición relacionada. Falta evaluar una política institucional de versionado y vigencia de mallas antes de cambiarla. |
| Docencia y calificaciones | `PortalDocenteView`, planificación, evaluación 360 | Existen flujos e indicadores. Mantener las alertas unificadas existentes, sin crear avisos duplicados. |
| Integración del aula | Paneles Moodle de copia, matrícula, fechas, notas y validación | No es una integración de solo lectura. Corregida esa afirmación desactualizada en README. |
| Secretaría y documentación | `SecretariaGeneralView`, expedientes, requisitos R/H | Existen cargas, evidencias y revisión. Incorporados estudiantes con faltantes a la bandeja administrativa. |
| Prácticas, inglés y titulación | Prácticas institucionales, inglés, titulación y puente al servicio especializado | Conservar módulos existentes. La disponibilidad del servicio de titulación debe verificarse en cada despliegue. |
| Reportería institucional | Reportería integral, certificados y SENESCYT | Conservar formatos y fuentes. No afirmar cumplimiento regulatorio solo por existir una descarga. |
| Control diario | `SistemaAcademicoView` era principalmente un mapa estático | Mejorado con pendientes reales, consultas acotadas, permisos por pantalla y diagnóstico bajo demanda. |
| Tutorías y permanencia | Planificación tiene información de tutorías; no se identificó un flujo completo de casos en la revisión | Pendiente de diseño: asignación de tutor, entrevistas, compromisos, seguimiento y cierre. No habilitar predicciones automáticas sin validación. |
| Calendario y capacidad | Existen períodos, aperturas de notas y catálogos de horarios | No equivalen a calendario consolidado ni asignación automática de cupos. Validar reglas, responsables y conflictos antes de automatizar. |

## Cambios implementados

1. **Centro unificado de notificaciones**: la franja superior **Ver pendientes** integra evaluación 360, calificaciones Moodle, documentación de Secretaría y solicitudes de cambio de carrera y modalidad. Las cinco tarjetas usan el mismo tamaño y muestran únicamente el detalle de la fuente seleccionada. Incluye fecha de consulta, paginación y acceso al módulo responsable; se retiró la bandeja separada de Sistema académico.
2. **Estados reales**: en solicitudes se incluyen `PENDIENTE` y `APROBADA` todavía sin aplicar. Se excluyen `APLICADA` y `RECHAZADA`. Las aprobadas indican que falta aplicar; no se ejecutan automáticamente.
3. **Unidades correctas**: Secretaría cuenta estudiantes candidatos con faltantes en expedientes existentes; los cambios de carrera y modalidad cuentan solicitudes. El total de la franja suma pendientes de las distintas fuentes, no personas únicas. Cada tarjeta identifica su unidad; la misma persona puede aparecer en más de un proceso.
4. **Permisos**: cada fuente se consulta solo si su pantalla está asignada. Los accesos del mapa comprueban el permiso concreto; tener el nombre de rol administrador no sustituye esa comprobación. El diagnóstico también exige permiso de Sistema académico.
5. **Errores y actualización**: una fuente fallida no oculta las demás ni muestra cero. Hay actualización manual, reintento y consulta cada cinco minutos mientras la pestaña está visible. La actualización conserva la fuente y la página seleccionadas. No se guarda información personal de la bandeja en almacenamiento persistente del navegador; las lecturas administrativas se cancelan al desmontar. Se conservan los recordatorios diarios personales de docentes y estudiantes. La subpantalla permite cerrar con Escape y devuelve el foco al control que la abrió.
6. **Carga**: las solicitudes usan diez filas por página con un conteo independiente del tamaño de la página. No se descargan todos los historiales ni se crean tablas para mostrar la bandeja. Las conexiones institucionales se consultan solo al abrir su apartado. El resumen se carga también al entrar directamente y se actualiza cada minuto con la pestaña visible.
7. **Secretaría con volumen**: el filtro de códigos usa un único parámetro XML para evitar el límite de 2100 parámetros de SQL Server. Si desaparece una página de resultados, se consulta la primera para no presentar un falso total cero.
8. **Limpieza**: se retiraron el segundo selector de etapas, los textos estáticos de supuestos resultados y bloques que repetían identidad, permisos y fuentes. Se conservaron los procesos, datos y accesos existentes.

## Arquitectura y garantías

- Un solo frontend React. Se reutiliza autenticación, cliente API, permisos, estilos y pantallas existentes.
- Nuevas lecturas: `GET /api/requests/career-change/pending` y `GET /api/requests/modality-change/pending`.
- Ambas leen las tablas `sol.SolicitudCambioCarrera` y `sol.SolicitudCambioModalidad` de la base de control existente. No agregan base, tabla, columna, trigger ni migración.
- SQL parametrizado, identificadores en lista fija, orden estable por fecha e ID, cierre explícito de conexión y tiempo máximo de consulta de 15 segundos en estas nuevas lecturas.
- Secretaría reutiliza `/api/secretaria-general/candidates?only_missing_documents=true`; conserva sus criterios de proximidad, egreso y graduación, no una nueva definición de estudiante activo.
- No se alteran notas, aprobaciones, solicitudes, documentos ni matrículas al abrir la bandeja.
- Los conteos son observaciones de consulta, no bloqueos transaccionales. Si otra persona resuelve un caso, se comprueba de nuevo en su módulo antes de aprobar o aplicar.
- Una fuente sin tabla instalada o sin permisos responde como no disponible; no se instala automáticamente desde la bandeja.

## Próximos incrementos

| Prioridad | Incremento | Definición necesaria y criterio de aceptación |
| --- | --- | --- |
| Alta | Reglas académicas versionadas | Acordar vigencias por carrera, malla, período y R/H; conservar la regla usada en cada decisión. No cambiar retroactivamente notas o requisitos. |
| Alta | Seguimiento de permanencia | Definir inactividad, ausencias, actividades vencidas, tutor responsable y cierre. Validar con casos reales y permitir revisión humana antes de contactar estudiantes. |
| Alta | Observabilidad de integraciones | Unificar estado de ejecución, último éxito, fallos recuperables y reintentos idempotentes sin repetir las alertas existentes. |
| Media | Calendario consolidado | Reunir ventanas de matrícula, calificación, actividades y titulación por período; conservar dueño de cada fecha y zona horaria. |
| Media | Cupos y conflictos de horario | Confirmar capacidad física/virtual y reglas para docente, aula y paralelo; detectar conflictos antes de aceptar matrícula. |
| Media | Respaldo y recuperación verificables | Documentar retención, cifrado, responsables y prueba de restauración. Una copia en la nube no demuestra recuperación. |

Estos puntos no se presentan como implementados. Requieren reglas institucionales, acuerdos de operación o pruebas del entorno; incorporarlos por suposición podría cambiar indebidamente la matrícula o los requisitos de graduación.

## Verificación reproducible

Desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_academic_pending_requests.py tests/test_secretaria_general.py tests/test_career_change_requests.py tests/test_modality_change_requests.py tests/test_screen_access.py -q
```

Desde la raíz, con Vite en ejecución:

```powershell
$env:FRONTEND_TEST_URL = 'http://127.0.0.1:5175'
.\.venv\Scripts\python.exe frontend/tests/verify_academic_work_center.py
.\.venv\Scripts\python.exe frontend/tests/verify_unified_notifications.py
```

Las pruebas automatizadas sustituyen conexiones y respuestas API. Cubren permisos, fuentes caídas, conteos mayores que la página, búsqueda, estados, límites, XML con 3001 códigos, navegación directa, subpantalla y reintentos. La comprobación del centro unificado incluye tamaños iguales en escritorio y móvil, aislamiento de detalles, foco, pausa de consultas en segundo plano y recordatorios diarios por perfil.

Resultados: 1224 pruebas de backend aprobadas, 3 omitidas; compilación y lint del frontend correctos; verificaciones de bandeja, estilos, login y regresión de carga aprobadas. Permanece una advertencia previa de deprecación de Starlette/httpx.

Se verificó adicionalmente en SQL Server una consulta sintética con 3001 identificadores, sin consultar ni modificar tablas institucionales. El XML se materializa en una variable de la consulta antes de extraer valores; el conteo, mínimo y máximo devolvieron `(3001, 1, 3001)`. Los conteos funcionales reales siguen dependiendo de los datos y permisos de cada despliegue.
