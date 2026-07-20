# SisAcademicoV1 - Flujo operativo de clonacion

Este flujo ordena el clon moderno desde el primer contacto del estudiante hasta titulacion. La regla es conservar los datos y comportamiento de `SisAcademicoV1`, pero reemplazar pantallas WebForms dispersas por pasos operativos claros, auditables y responsivos.

## 1. Inscripcion y admision

**Origen V1:** `Preinscripcion`, datos de factura, documentos iniciales y asesores.

**Sistema moderno:** `PreinscripcionView`, `GestionSisAcademicoView` con `preinscripciones` y `datos_factura`.

**Objetivo:** registrar aspirante, completar informacion tributaria, asociar asesor y dejar evidencia documental inicial.

## 2. Actualizacion de datos

**Origen V1:** `SisAcademicoV1/Actualizar_Datos`.

**Sistema moderno:** `ActualizarDatosEstudianteView`, endpoints genericos para estudiantes y docentes.

**Objetivo:** mantener ficha personal, contacto, ubicacion, datos SENESCYT y datos docentes sin tocar la estructura principal de `INTECBDD`.

## 3. Matricula academica

**Origen V1:** cabecera de matricula, materias matriculadas, pagos y convenios.

**Sistema moderno:** `MatriculaAcadView`, secciones `cabecera_matricula`, `matricula_materias` y `pagos_matricula`.

**Objetivo:** registrar matricula del estudiante, materias, paralelo, periodo, valores y control financiero asociado.

## 4. Cursado, asistencia y notas

**Origen V1:** materias, notas por periodo, apertura de notas, asistencia y seguimiento.

**Sistema moderno:** `GestionSisAcademicoView`, portal docente, reportes individuales y sincronizacion Moodle cuando aplique.

**Objetivo:** registrar y consultar calificaciones. Para tipo `R` se considera P1, P2, P3 y promedio final; para tipo `H` se considera teorico, practico y promedio final. La nota aprobatoria es mayor o igual a 7 sobre 10.

## 5. Docencia y evaluacion

**Origen V1:** docentes, asignacion docente, evaluacion y autoevaluacion.

**Sistema moderno:** `MatriculaDocente`, `teacher_evaluation.py`, vistas de evaluacion docente y reportes modernos.

**Objetivo:** asignar docentes por materia/periodo/paralelo y evaluar cumplimiento sin modificar el parche docente existente.

## 6. Practicas y vinculacion con la sociedad

**Origen V1:** practicas profesionales, vinculacion, empresas y seguimiento.

**Sistema moderno:** `PracticasInstitucionalesView` y enlace con `INTEC_PRACTICAS_PREPROFESIONALES`.

**Objetivo:** validar practicas preprofesionales y vinculacion con la sociedad como requisito previo a titulacion.

## 7. Certificados y grado

**Origen V1:** certificados, fecha de grado, reportes y documentos generados.

**Sistema moderno:** certificados, fecha de grado, renombrador de PDF y reporteria moderna.

**Objetivo:** generar documentos institucionales y mantener trazabilidad documental. Los Crystal Reports se reconstruyen como PDF/Excel/HTML desde codigo moderno.

## 8. Titulacion

**Origen V1:** complexivo, defensa de grado, fechas de grado, actas y documentos finales.

**Sistema moderno:** `TitulacionView`, `TitulacionProcesoView`, `TitulacionResponsablesView`, `titulos_registrados.py` y `titulacion.py`.

**Objetivo:** verificar malla completa, ingles `A2+ - INTERMEDIATE`, practicas, vinculacion con la sociedad, aptitud legal y promedio final. Luego dar paso a egresamiento, seleccionar examen complexivo o defensa de grado, asignar responsables/tribunal, registrar notas y generar actas/documentos.

## Regla de navegacion

El sistema moderno debe mostrar primero este flujo y despues los modulos tecnicos. La administracion de tablas heredadas queda como soporte, no como experiencia principal del usuario.

