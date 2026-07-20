# SisAcademicoV1 - Auditoria total de clonacion

## Conteo real del proyecto revisado

Desde la carpeta local `SisAcademicoV1` se detectaron:

| Tipo | Cantidad |
|---|---:|
| Pantallas `.aspx` | 186 |
| Code-behind `.vb` | 178 |
| Reportes heredados `.rpt` | 39 |
| Total revisado | 403 |

## Clasificacion de pantallas `.aspx`

| Grupo | Pantallas | Tratamiento moderno |
|---|---:|---|
| Notas | 28 | Parcial: lectura, reportes y administracion base; falta cerrar flujo masivo especializado. |
| Evaluacion docente | 17 | Clonado como base en backend/frontend moderno. |
| Reporteria academica | 16 | Modernizado en `legacy_reports.py`; no se ejecutan `.rpt`. |
| Docentes | 14 | Clonado como base, respetando el parche docente existente. |
| Repositorio/documentos | 14 | Clonado como base para metadata; cargas fisicas deben ir por endpoints controlados. |
| Matricula | 14 | Clonado como base con router transaccional y secciones administrativas. |
| Seguridad/menu | 10 | Clonado funcionalmente con autenticacion moderna; no se copia WebForms. |
| Estudiantes | 10 | Clonado como base con ficha, documentos, correos y seguimiento. |
| Soporte estatico/menu antiguo | 10 | No migrable: respaldos visuales y menus antiguos. |
| Academico/catalogos | 9 | Clonado como base. |
| Admision/preinscripcion | 9 | Clonado como base. |
| Educacion continua | 9 | Clonado como base; pendiente vista dedicada si se requiere flujo completo. |
| Mantenimiento sensible | 6 | Parcial/controlado: eliminar/copiar no debe exponerse como WebForms. |
| Certificados | 6 | Clonado como base y generacion moderna. |
| Practicas/vinculacion | 4 | Clonado como base. |
| Titulacion | 3 | Parcial: proceso moderno existe, falta validacion extremo a extremo con datos reales. |
| Integraciones | 2 | Clonado como base/auditoria; secretos se manejan por `.env`. |
| Financiero/convenios | 9 artefactos relacionados | Clonado como base para pagos, datos factura y reportes PDF modernos. |

## Conclusion de auditoria

No es correcto decir que el 100% de `SisAcademicoV1` esta clonado como pantalla moderna equivalente uno a uno.

Si es correcto decir que:

- El nucleo funcional academico, matricula, estudiantes, docentes, evaluacion, practicas, certificados, reporteria y administracion de tablas esta cubierto por backend/frontend moderno.
- Los reportes `.rpt` no se usan como motor; se reconstruyen como reportes modernos.
- Las pantallas duplicadas, antiguas, de prueba o de soporte no se clonan porque no son modulos operativos.
- Las pantallas destructivas de `actualizar/*` se tratan como mantenimiento controlado con auditoria y permisos, no como botones directos.
- El inventario backend ya clasifica todos los artefactos locales; no quedan archivos en `pendiente_clasificacion`.

## Modulos aun parciales

### Notas

Cubierto:

- Lectura academica.
- Reportes individuales y por carrera.
- Portal docente/estudiante.
- Moodle/notas sincronizadas.
- Fechas de ingreso de notas como mantenimiento.

Pendiente:

- Flujo dedicado de ingreso masivo que cubra todos los casos V1:
  - regular `R`
  - homologacion `H`
  - convalidacion
  - repeticion
  - bloqueo/desbloqueo controlado

### Titulacion

Cubierto:

- Verificacion de requisitos.
- Paso a proceso.
- Complexivo/defensa.
- Responsables/tribunal.
- Registro documental base.

Pendiente:

- Validacion final con datos reales de actas, notas y documentos.
- Ajustar reportes/actas finales segun formato de Secretaria.

### Educacion continua

Cubierto:

- Tablas base, cortes, estudiantes y credenciales.

Pendiente:

- Vista dedicada si se requiere operacion completa de inscripcion, cortes y certificados desde frontend.

## Evidencia en codigo moderno

Backend:

- `backend/app/routers/sisacademico_admin.py`
- `backend/app/routers/academic_enrollment.py`
- `backend/app/routers/legacy_reports.py`
- `backend/app/routers/portal_academico.py`
- `backend/app/routers/teacher_evaluation.py`
- `backend/app/routers/practicas_institucionales.py`
- `backend/app/routers/titulacion.py`
- `backend/app/routers/certificados.py`

Frontend:

- `frontend/src/features/matricula/SisAcademicoV1CloneView.tsx`
- `frontend/src/features/matricula/GestionSisAcademicoView.tsx`
- `frontend/src/features/matricula/MatriculaAcadView.tsx`
- `frontend/src/features/matricula/ReporteriaIntegralView.tsx`
- `frontend/src/features/matricula/ReportesIndividualesView.tsx`
- `frontend/src/features/portal/PortalDocenteView.tsx`
- `frontend/src/features/evaluacion/TeacherEvaluationAdminView.tsx`
- `frontend/src/features/practicas/PracticasInstitucionalesView.tsx`
- `frontend/src/features/matricula/TitulacionView.tsx`

## Criterio final

El proyecto esta clonado funcionalmente por modulos, no copiado visualmente 1:1. Para cerrar la clonacion total operativa faltan principalmente:

1. Pantalla dedicada de notas masivas.
2. Validacion completa de titulacion con datos reales.
3. Vista dedicada de educacion continua si el usuario final la necesita como flujo, no solo como administracion.
