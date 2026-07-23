# Análisis del sistema académico integrado

## Propósito

Organizar el desarrollo existente como un sistema académico único, sin reemplazar `INTECBDD`, sin duplicar personas y sin convertir las bases complementarias en nuevas fuentes maestras. La modernización se concentra en navegación, controles de proceso, trazabilidad e interpretación de la información.

## Referentes revisados

- [Oracle PeopleSoft Campus Solutions](https://docs.oracle.com/cd/E56917_01/cs9pbr4/eng/cs/lsfn/concept_CampusSolutionsOverview-ab58bf.html): organiza el ciclo después de la admisión en activación, matrícula, calificación, evaluación y graduación.
- [Oracle Student Homepage](https://docs.oracle.com/en/applications/peoplesoft/campus-solutions/9.2.038/campus-solutions-application-fundamentals/using-student-homepage.html): separa progreso académico, expediente, cuenta financiera y autoservicio.
- [Oracle Activity Guides](https://docs.oracle.com/en/applications/peoplesoft/peoplesoft-common/enterprise-components/delivered-cs-activity-guides.html): presenta procesos complejos como tareas guiadas y verificables.
- [Oracle Class Enrollment Processing](https://docs.oracle.com/en/applications/peoplesoft/campus-solutions/9.2.038/student-records/class-enrollment-processing.html): valida persona, programa, periodo, requisitos y permisos antes de matricular.
- [Oracle Grade Import](https://docs.oracle.com/en/applications/peoplesoft/campus-solutions/9.2.038/student-administration-integration-pack/importing-grades1.html): exige matrícula activa, sección calificable, nota válida y fuente autorizada.
- [Oracle Graduation Tracking](https://docs.oracle.com/en/applications/peoplesoft/campus-solutions/9.2.038/student-records/tracking-graduation-progress.html): conserva requisitos, estados y el historial de revisión de graduación.
- [Moodle Learning Plans](https://docs.moodle.org/en/Learning_plans): organiza avance mediante planes reutilizables y revisión de competencias.

## Conclusión aplicable

El proyecto no necesita otra aplicación paralela. Necesita una capa de orquestación que presente los módulos actuales según la etapa del estudiante, aplique controles antes de cada transición y consulte cada dato en su fuente propietaria.

## Macroprocesos implementados

| Macroproceso | Procesos | Resultado operativo |
| --- | --- | --- |
| Ingreso | Admisión, financiamiento y matrícula | Estudiante admitido, condición financiera definida y matrícula activa |
| Formación | Expediente, malla, calificaciones y docencia | Avance académico consolidado y ejecución docente controlada |
| Culminación | Prácticas, vinculación, egreso y titulación | Cumplimientos reconocidos, actas y títulos registrados |
| Control | Reportes, certificados, SENESCYT e integraciones | Indicadores trazables desde la fuente institucional |

## Propiedad de datos

| Fuente | Propiedad |
| --- | --- |
| `INTECBDD` | Persona, estudiante, docente, carrera, pensum, periodo, matrícula y notas |
| `INTEC_EXPEDIENTE_ESTUDIANTIL` | Expediente, documentos, versiones y cambios de estado |
| `INTEC_FINANZAS_INSTITUCIONAL` | Becas, obligaciones, convenios, pagos y saldos |
| `INTEC_PRACTICAS_PREPROFESIONALES` | Prácticas preprofesionales y vinculación con la sociedad |
| `TITULACION_INTEC` | Habilitación, modalidad, responsables, calificaciones, actas y títulos |
| `INTEC_EVALUACION_360` | Evaluación docente e institucional |
| `INTECEDUCONTINUA` | Cursos y operación educativa continua |
| `INTEC_GRAPH_INTEGRACION` | Identificadores y trazabilidad de Microsoft 365 |
| `INTEC_INTEGRACION_CONTROL` | Ejecuciones, errores, conciliación y reintentos |
| Vistas `vw_Estado*Integracion` | Contratos estables de lectura entre dominios |

## Identidad institucional

1. La cédula o pasaporte normalizado representa a la persona.
2. `CodigoEstud` representa su identidad académica como estudiante.
3. `CodigoDoc` representa su identidad docente.
4. Una persona puede tener varios perfiles, carreras y periodos sin duplicarse.
5. Los registros complementarios deben conservar la cédula y el código institucional correspondiente.

## Controles de transición

### Admisión a matrícula

- Identidad válida y sin duplicidad.
- Carrera, periodo, modalidad y jornada vigentes.
- Beca con aprobación cuando supera el umbral.
- Convenio y documentación requeridos.

### Matrícula a formación

- Cabecera de matrícula activa.
- Materias pertenecientes al pensum y periodo.
- Paralelo y docente asignados.
- Tipo R/H aplicado sin mezclar reglas de calificación.

### Formación a culminación

- Materias de malla aprobadas con nota final entre 7 y 10.
- Inglés `A2+ - INTERMEDIATE` validado.
- Prácticas preprofesionales y vinculación con la sociedad cumplidas.
- Estados y documentos respaldados con auditoría.

### Culminación a titulación

- Modalidad seleccionada: examen complexivo o defensa de grado.
- Responsables o tribunal asignados.
- Calificaciones consolidadas.
- Acta, refrendación y título generados con historial documental.

## Navegación adoptada

- El menú continúa condicionado por perfil.
- El centro **Sistema académico** funciona como mapa operativo, no como reemplazo de las pantallas.
- Los procesos se filtran por Ingreso, Formación, Culminación y Control.
- Cada fila muestra responsable, registro central, resultado y disponibilidad de integración.
- Los portales de estudiante y docente permanecen separados del espacio administrativo.

## Estado técnico comprobado

- Nueve bases operativas disponibles.
- Tres contratos de lectura instalados y disponibles.
- Ocho dominios del ciclo académico con estado `READY`.
- Endpoint de diagnóstico: `GET /api/academic-system/integration-status`.

## Próximas mejoras recomendadas

1. Crear una bandeja unificada de tareas pendientes por perfil usando estados reales, no contadores duplicados.
2. Registrar toda transición de estado con origen, usuario, fecha, motivo y documento.
3. Centralizar reglas configurables como nota mínima, horas, umbrales de beca y requisitos de titulación.
4. Añadir pruebas de contrato para las vistas de integración y pruebas transaccionales para cada cambio de etapa.
5. Medir tiempos de respuesta y errores de sincronización desde `INTEC_INTEGRACION_CONTROL`.
