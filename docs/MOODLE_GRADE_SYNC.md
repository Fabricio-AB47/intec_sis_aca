# Sincronización de notas Moodle

## Objetivo

El proceso consulta los ítems de calificación de Moodle y prepara las notas de los exámenes teóricos y prácticos para la matrícula académica coincidente en `INTECBDD`.

La migración considera exclusivamente actividades ubicadas dentro de una sección visible cuyo nombre contenga la palabra completa `Evaluación` o `Evaluaciones`. Las calificaciones de tareas, cuestionarios u otros recursos ubicados fuera de esa sección no se procesan.

La relación se valida con cuatro datos:

1. El `idnumber` o `shortname` del curso Moodle debe coincidir exactamente con `PENSUM.cod_materia` después de normalizar únicamente separadores finales.
2. El curso Moodle debe estar asociado a un `PERIODO.cod_periodo` configurado.
3. El correo Moodle debe coincidir con el correo institucional del estudiante activo.
4. Debe existir una única fila de `CARRERAXESTUD` para estudiante, materia, período, carrera, paralelo y grupo.

No se realizan coincidencias aproximadas de códigos ni de estudiantes.

## Regla de calificación

- **Regular (`R`)**: `Examen práctico P1`, `P2` o `P3` duplica su nota en `PnTareas` (30%) y `PnExamen` (40%) del mismo parcial. Nunca se replica entre parciales.
- **Regular (`R`)**: `Examen teórico P1`, `P2` o `P3` actualiza únicamente `PnProyectos` (30%) del parcial correspondiente. Luego el sistema calcula el parcial con 30% de tareas, 30% de proyectos y 40% de examen.
- **Homologación (`H`)**: el examen teórico se registra una sola vez en `teoriaHomo` (40%) y el práctico en `practicahomo` (60%).
- Toda escala Moodle se normaliza a una nota entre 0 y 10.
- Un cuestionario Moodle visible y habilitado se interpreta como examen teórico, salvo que su nombre indique expresamente que es práctico.
- Si existen varios cuestionarios habilitados para el mismo componente y parcial, se utiliza la mayor nota obtenida por el estudiante. `grademax` se usa únicamente para normalizar la escala y nunca como nota del estudiante.
- Los cuestionarios ocultos, no visibles o deshabilitados no participan en la sincronización.
- En matrícula regular, un ítem que no identifica P1, P2 o P3 se ignora para impedir cruces entre parciales.
- Una calificación ya migrada se vuelve a aplicar únicamente cuando Moodle entrega un valor diferente al último registrado en el historial de sincronización.

Después de aplicar una nota se recalculan los parciales, el promedio final y el estado aprobado/reprobado con las reglas académicas existentes.

## Protección de datos

La ejecución funciona primero como vista previa. Una nota solo se puede escribir cuando el campo está vacío o cuando conserva exactamente el último valor sincronizado desde Moodle. Una modificación manual posterior se reporta como conflicto y se conserva.

Cada escritura utiliza:

- Una transacción SQL.
- `sp_getapplock` por curso y período para impedir ejecuciones simultáneas.
- Un registro por componente en `intec_estudiantenota`.
- Un resumen de ejecución en `intec_moodlegradesynclog`.

## Configuración

Configure en `backend/.env` las relaciones explícitas `curso Moodle:período INTECBDD`:

```dotenv
MOODLE_GRADE_SYNC_ENABLED=true
MOODLE_GRADE_SYNC_APPLY_ENABLED=false
MOODLE_GRADE_SYNC_NIGHTLY_ENABLED=false
MOODLE_GRADE_SYNC_CHANGES_ENABLED=false
MOODLE_GRADE_SYNC_INTERVAL_MINUTES=5
MOODLE_GRADE_SYNC_MAPPINGS=123:1050,124:1051
MOODLE_GRADE_SYNC_LOCK_TIMEOUT_MS=5000
```

Los dos interruptores de escritura permanecen en `false` durante la validación inicial.

## Validación manual

Desde `Moodle > Migración de notas`, seleccione el curso y el período. Revise:

- Estudiantes encontrados por correo institucional.
- Tipo de matrícula `R` o `H`.
- Ítem Moodle utilizado y nota normalizada.
- Campo académico de destino.
- Conflictos manuales o matrículas no encontradas.

Para validar desde consola sin escribir:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe scripts\sync_moodle_grades.py
```

## Ejecución a medianoche

Después de aprobar la vista previa:

1. Cambie `MOODLE_GRADE_SYNC_APPLY_ENABLED=true`.
2. Cambie `MOODLE_GRADE_SYNC_NIGHTLY_ENABLED=true`.
3. Ejecute PowerShell con los permisos requeridos:

```powershell
backend\scripts\install_moodle_grade_sync_task.ps1
```

La tarea de Windows se ejecuta diariamente a las `00:00`. El registro queda en `backend/logs/moodle-grade-sync.log`. El ejecutor devuelve un código distinto de cero si alguna correspondencia falla, por lo que puede integrarse con alertas operativas.

La programación se mantiene fuera del proceso FastAPI: así no depende de que el servidor web permanezca iniciado y evita que varios trabajadores ejecuten la misma revisión.

## Detección periódica de cambios

Para revisar nuevos ingresos o modificaciones de notas durante el día:

1. Valide primero cada correspondencia desde la vista previa administrativa.
2. Configure `MOODLE_GRADE_SYNC_APPLY_ENABLED=true`.
3. Configure `MOODLE_GRADE_SYNC_CHANGES_ENABLED=true`.
4. Mantenga en `MOODLE_GRADE_SYNC_MAPPINGS` únicamente los cursos y períodos autorizados.
5. Registre la tarea periódica:

```powershell
backend\scripts\install_moodle_grade_sync_change_task.ps1 -IntervalMinutes 5
```

La tarea consulta Moodle cada cinco minutos por defecto. No reescribe toda la matrícula: compara cada componente de `Evaluación` con `intec_estudiantenota`, migra solo valores nuevos o modificados y conserva cualquier cambio académico manual como conflicto. El detalle de cada ejecución se registra en `intec_moodlegradesynclog` y en `backend/logs/moodle-grade-sync.log`.

El instalador rechaza la creación de la tarea si la escritura, la detección de cambios o las relaciones `curso Moodle:período INTECBDD` no están configuradas. Cada ejecución automática se identifica como `AUTOMATICO_CAMBIOS` en la bitácora.
