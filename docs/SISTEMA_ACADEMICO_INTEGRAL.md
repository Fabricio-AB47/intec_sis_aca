# Sistema académico integral INTEC

## Objetivo

Unificar la operación académica existente sin duplicar estudiantes ni reemplazar `INTECBDD`. El sistema moderno funciona como capa de procesos, validación, documentos, integración y experiencia de usuario sobre las fuentes institucionales actuales.

## Ciclo institucional

1. **Prospecto:** identificación, contacto, carrera, periodo y asesor.
2. **Admisión:** validación de identidad, requisitos, beca y decisión de ingreso.
3. **Financiamiento:** matrícula, arancel, convenio, obligaciones, pagos y comprobantes.
4. **Matrícula académica:** carrera, periodo, paralelo, tipo R/H y materias del pensum.
5. **Cursado:** asistencia, planificación, aulas, recursos y seguimiento.
6. **Evaluación:** parciales o teórico/práctico, nota final, promoción y expediente.
7. **Prácticas y vinculación:** horas, responsables, documentos, cierre y certificados.
8. **Egreso y titulación:** malla, inglés, prácticas, modalidad, tribunal, acta y títulos.

## Propiedad de la información

| Dominio | Fuente principal | Regla |
| --- | --- | --- |
| Persona, estudiante, carrera y notas | `INTECBDD` | Fuente académica maestra; no duplicar ni reconstruir |
| Preinscripción y matrícula | `INTECBDD` + complementos | Registrar transacciones enlazadas por cédula y código de estudiante |
| Expediente estudiantil | `INTEC_EXPEDIENTE_ESTUDIANTIL` | Documentos, historial y trazabilidad |
| Finanzas | `INTEC_FINANZAS_INSTITUCIONAL` | Obligaciones, aplicaciones, becas y saldos |
| Microsoft 365 | `INTEC_GRAPH_INTEGRACION` | Identificadores, sincronización y auditoría Graph |
| Evaluación 360 | `INTEC_EVALUACION_360` | Evaluación institucional y docente por periodo |
| Teams y educación continua | `INTECEDUCONTINUA` | Aulas virtuales, cursos y operación asociada |
| Integraciones | `INTEC_INTEGRACION_CONTROL` | Lotes, errores, reintentos y conciliación |
| Contratos de lectura | Vistas `vw_Estado*Integracion` | Contrato estable entre `INTECBDD`, expediente y prácticas |
| Prácticas | `INTEC_PRACTICAS_PREPROFESIONALES` | Expedientes PPF y vinculación con la sociedad |
| Titulación | `TITULACION_INTEC` | Requisitos, evaluación, actas y títulos |

## Identidad y relaciones

- La cédula o pasaporte normalizado identifica a la persona.
- `CodigoEstud` identifica el expediente académico del estudiante.
- Toda integración conserva ambos identificadores cuando estén disponibles.
- Una persona se muestra una sola vez; sus carreras, periodos y roles son relaciones, no personas nuevas.
- Docente, estudiante y administrativo pueden coexistir como perfiles de una misma identidad.

## Estados controlados

`PROSPECTO -> ADMITIDO -> MATRICULADO -> ACTIVO -> EGRESADO -> TITULADO`

Estados alternos: `OBSERVADO`, `INACTIVO`, `RETIRADO`, `ANULADO` y `GRADUADO`. Cada cambio debe registrar usuario, fecha, motivo, documento de respaldo y estado anterior.

## Reglas transversales

- No matricular materias sin estudiante, carrera, periodo y cabecera válidos.
- No continuar una beca superior al umbral institucional sin aprobación.
- La Beca INTEC afecta el arancel y no el valor de matrícula.
- No publicar una nota sin matrícula activa, materia válida y docente autorizado.
- La nota aprobatoria es mayor o igual a 7 y no puede superar 10.
- El tipo R usa parciales y nota final; el tipo H usa componentes teórico y práctico.
- No habilitar titulación sin malla, inglés, prácticas y vinculación cumplidos.
- Toda generación documental conserva versión, hash, usuario y fecha.

## Integración segura

- Consultas de lectura para tableros y expedientes consolidados.
- Procedimientos o servicios transaccionales para cambios de estado.
- Idempotencia en sincronizaciones para evitar duplicados.
- Auditoría de solicitudes, resultados y errores de servicios externos.
- Permisos por perfil aplicados en backend y reflejados en frontend.
- Indicadores calculados desde las fuentes maestras, no desde valores estáticos.

## Interfaz implementada

La página **Sistema académico** centraliza indicadores y abre cada dominio según el perfil autenticado. No sustituye las pantallas operativas: las ordena dentro del ciclo institucional y reutiliza su lógica y sus datos actuales.

La ruta autenticada `GET /api/academic-system/integration-status` verifica en paralelo la base principal y cada complemento. La interfaz utiliza esa respuesta para mostrar disponibilidad real por fuente y estado de integración por etapa, sin exponer credenciales ni información del servidor.
