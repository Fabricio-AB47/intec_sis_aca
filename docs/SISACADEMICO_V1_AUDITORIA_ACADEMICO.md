# SisAcademicoV1 - Auditoria de clonacion academica

## Resultado general

La clonacion academica no es una copia visual de WebForms. El sistema moderno ya cubre el nucleo academico mediante:

- Backend FastAPI sobre `INTECBDD`.
- Administrador generico `sisacademico_admin.py` para tablas heredadas.
- Routers especializados para procesos transaccionales.
- Frontend React con navegacion por modulo, formularios modernos y estilos del proyecto.

## Cobertura por modulo academico

| Modulo V1 | Archivos V1 revisados | Backend moderno | Frontend moderno | Estado |
|---|---|---|---|---|
| Catalogos academicos | `Carreras.aspx`, `IngresarMaterias.aspx`, `IngresoMallaCarrera.aspx`, `PeriodosAcademicos.aspx`, `IngresoParalelos.aspx`, `IngresoModalidadMatricula.aspx` | `sisacademico_admin.py` | `GestionSisAcademicoView`, hub `SisAcademicoV1CloneView` | Base clonada |
| Matricula academica | `ModificarMaterias.aspx`, `ModificarMateriasHaR.aspx`, `ModificarMateriasConvalida.aspx`, `ImprimirMatricula.aspx`, `ImprimirPreMatricula.aspx`, `ListaMatriPeriodo*.aspx` | `academic_enrollment.py`, `sisacademico_admin.py`, `legacy_reports.py` | `MatriculaAcadView`, `MatriculaView`, `GestionSisAcademicoView` | Base clonada |
| Notas | `IngNotasAsignatura*.aspx`, `IngresoNotasDocente.aspx`, `BloqueoNotas.aspx`, `fechasingresonotas/*`, `ReporteNotas/Notasweb/*` | `portal_academico.py`, `legacy_reports.py`, `sisacademico_admin.py` | `PortalDocenteView`, `ReportesIndividualesView`, `GestionSisAcademicoView` | Parcial |
| Docentes | `NuevoProfe.aspx`, `IngNuevoDocente.aspx`, `ActualizarProfe.aspx`, `ConsultaProfe.aspx`, `ListaProfesores.aspx` | `teacher_evaluation.py`, `portal_academico.py`, `sisacademico_admin.py` | `TeacherEvaluationAdminView`, `PortalDocenteView`, `GestionSisAcademicoView` | Base clonada |
| Evaluacion docente | `EvaluacionEstud.aspx`, `AutoEvaluacion.aspx`, `EncuestaDocEstud/*`, reportes de evaluacion | `teacher_evaluation.py`, `legacy_reports.py`, `sisacademico_admin.py` | `TeacherEvaluationView`, `TeacherEvaluationAdminView` | Base clonada |
| Practicas y vinculacion | `PracticasProfesionales.aspx`, `PracticasVinculacion.aspx`, `Vinculacion.aspx`, reportes de practicas | `practicas_institucionales.py`, `legacy_reports.py`, `sisacademico_admin.py` | `PracticasInstitucionalesView`, `GestionSisAcademicoView` | Base clonada |
| Titulacion | `MatriculaComplexivo.aspx`, `IngNotasComplexivo.aspx`, `IngresoFechaGrado.aspx`, `ImprimirNotasComplexivo.aspx` | `titulacion.py`, `titulos_registrados.py`, `sisacademico_admin.py` | `TitulacionView`, `TitulosRegistradosView`, hub de responsables/proceso | Parcial |
| Reporteria academica | `ReporteAcad/*`, `ReporteNotas/*`, `.rpt` heredados | `legacy_reports.py`, `portal_academico.py` | `ReporteriaIntegralView`, `ReportesIndividualesView` | Base modernizada |

## Lo que ya esta clonado en backend

- `sisacademico_admin.py`: mantenimiento de tablas V1 por secciones.
- `academic_enrollment.py`: matricula academica y operaciones transaccionales.
- `portal_academico.py`: portal docente/estudiante, notas y reportes academicos.
- `legacy_reports.py`: reportes modernos PDF/Excel/HTML equivalentes a reportes heredados.
- `teacher_evaluation.py`: evaluacion docente.
- `practicas_institucionales.py`: practicas preprofesionales y vinculacion con la sociedad.
- `titulacion.py`: verificacion, modalidad, responsables y proceso de titulacion.
- `certificados.py`, `credential_generator.py`: certificados y credenciales.

## Lo que ya esta clonado en frontend

- `SisAcademicoV1CloneView`: hub de clonacion y navegacion mejorada.
- `GestionSisAcademicoView`: administrador de secciones heredadas.
- `MatriculaAcadView`, `MatriculaView`, `PeriodoAcademicoView`, `PeriodoMatriculadosView`.
- `PortalDocenteView`, `PortalEstudianteView`.
- `TeacherEvaluationView`, `TeacherEvaluationAdminView`.
- `PracticasInstitucionalesView`.
- `TitulacionView`, `TitulosRegistradosView`.
- `ReporteriaIntegralView`, `ReportesIndividualesView`, `ReporteriaCarrerasView`.

## Pendientes reales

1. Notas V1: falta cerrar una pantalla dedicada de ingreso masivo que replique todos los casos de `IngNotasAsignatura*.aspx`.
2. Titulacion: el flujo existe, pero debe validarse extremo a extremo con datos reales de complexivo/defensa.
3. Reportes heredados: no se usa Crystal Reports; se deben validar plantillas PDF/Excel con Secretaria.
4. Archivos historicos: las cargas fisicas deben manejarse por endpoint controlado, no por ruta directa WebForms.

## Criterio de clonacion

Un modulo se considera clonado cuando cumple:

- Tiene fuente de datos identificada en `INTECBDD`.
- Tiene endpoint backend o seccion administrativa.
- Tiene entrada frontend navegable.
- Usa estilos y controles del sistema moderno.
- No depende de WebForms, Crystal Reports ni credenciales embebidas.

