# Validacion de matriculas Moodle

## Acceso y alcance

- Menu: Integraciones > Validacion de matriculas Moodle.
- Permiso: `moodle/enrollment-validation`, asignado inicialmente a ADMINISTRADOR.
- Una sola pantalla: periodo, carrera con matriculas y seleccion explicita de
  hasta 100 cursos Moodle, con paralelo por aula. No hay modos separados.
- Incluye estudiantes activos con materias o solo cabecera en la carrera y periodo.
- Cambiar periodo o carrera limpia los cursos y resultados anteriores. Buscar
  cursos no cambia la seleccion; `Seleccionar visibles` conserva los paralelos elegidos.
- `*` incluye todos los paralelos. No se deduce el periodo a partir del nombre del curso.
- La comparacion es de solo lectura: no matricula, elimina, mueve ni cambia notas.
- Las ausencias se comprueban en las aulas seleccionadas. No representan
  una busqueda en todos los cursos existentes en Moodle.

## Fuentes y reglas

- `DATOS_ESTUD` y `CorreosEstudIntec`: identidad y estado del estudiante.
- `CARRERAXESTUD`, `PENSUM`, `CARRERAS` y `PERIODO`: materia y carrera de la matricula.
- `CABECERA_MATRICULA`: relacion por estudiante, carrera y periodo. No se iguala su
  `Num_Matricula` con el intento de matricula de cada materia.
- `sol.SolicitudCambioCarrera` en la conexion de control: cambios APLICADA. Si no
  puede consultarse, el reporte contiene una advertencia; nunca crea su esquema.
- Moodle: catalogo de cursos y participantes, con refresco y lectura secuencial.

La identidad exige correo institucional o documento exacto; conserva letras de
pasaportes y ceros iniciales. Las contradicciones y duplicidades quedan en revision.
No se enlazan estudiantes por semejanza de nombres. Solo los activos son esperados;
los inactivos se excluyen de la poblacion y se contabilizan en el resumen.
Los participantes identificados en otras carreras, ajenos a la poblacion elegida,
no se califican como errores solo por compartir un aula.

La materia se resuelve mediante el codigo unico y la relacion compuesta de carrera
y materia en PENSUM. Las materias comunes pueden pertenecer a distintas carreras.
Un antecedente en otra carrera no invalida una matricula correcta del periodo.
Las cuentas sin identidad o rol verificable y los errores de Moodle impiden declarar
una ausencia como confirmada. Varias aulas compatibles se revisan conjuntamente.

### Conciliacion del codigo unico

- Se comparan nombre corto y numero ID de Moodle con `PENSUM.cod_materia`.
- Se normalizan mayusculas, Unicode, separadores, ceros iniciales del numero de
  materia y sufijos del aula (R30, H12026, etc.). Tambien se reconocen codigos
  compactos como `VGAES202395R30` y variantes equivalentes entre carreras.
- Si no hay coincidencia exacta o normalizada, se admite un prefijo parecido
  solo cuando conserva el ano y numero de materia y hay una unica familia
  compatible. Se identifica como `Similitud controlada` para revisar el origen.
- Si cambia el ano o numero de materia, una diferencia de un caracter o una
  transposicion solo genera candidatos para revision. No se valida por cercania
  numerica, ni se confunden materias 1, 10 y 12.
- Los identificadores contradictorios y los candidatos multiples bloquean la
  validacion del aula. Las matriculas potencialmente afectadas quedan como no
  verificables, nunca como ausencias confirmadas.
- No se escoge un codigo solo porque el estudiante tenga una matricula en el.
  Primero se resuelve la materia y despues se comprueba la matricula del periodo
  por carrera y materia. Los nombres de materias no reemplazan al codigo unico.
- La depuracion es de comparacion: no se reescribe ningun dato en SQL ni Moodle.
  Pantalla, detalle, Excel y PDF incluyen los codigos originales y el criterio.

## Exportaciones

Excel y PDF usan el mismo resultado del servidor, sin volver a consultar ni aceptar
filas enviadas por el navegador. Incluyen periodo, aulas, responsable, fecha,
identificadores, carreras, paralelos, antecedentes y observaciones.

La vista incluye una fila resumen por estudiante y un detalle con
materias academicas ordenadas por semestre, paralelos y matriculas en las aulas
seleccionadas. Las otras materias se indican como `Fuera de la seleccion`, sin
generar ausencias ni coincidencias. La hoja `Matriculas academicas` conserva
el listado academico; `Detalle` contiene las relaciones y hallazgos, incluso
cabeceras sin materias. Los estudiantes inactivos no se consultan en Moodle.

## Consulta Unificada

1. Se obtiene la poblacion desde `CABECERA_MATRICULA` y `CARRERAXESTUD` del periodo
   y carrera seleccionados; no se usa una carrera actual del perfil para sustituir
   la carrera de una matricula historica.
2. Se recupera el catalogo actualizado y se verifica que todos los cursos elegidos
   sigan disponibles. No se incluyen aulas adicionales automaticamente.
3. `core_enrol_get_enrolled_users` consulta cada aula elegida una sola vez,
   secuencialmente. La identidad de sus participantes se resuelve por correo o
   documento exactos. Los fallos de permisos no se traducen en falsas ausencias.
4. El codigo unico identifica las materias del pensum. Se separan materias
   matriculadas en la carrera/periodo, materias de otra carrera del periodo,
   antecedentes de otros periodos, materias del pensum no matriculadas y aulas
   sin codigo verificable. Los antecedentes no son errores automaticos.
5. Solo las materias y paralelos cubiertos por la seleccion se evaluan por ausencia.
   Una coincidencia en cualquiera de las aulas compatibles evita una falta falsa
   en otra aula. Las identidades ambiguas y errores quedan como no verificables.
   La igualdad del codigo NO confirma la cohorte ni el periodo del aula; esa
   limitacion aparece en pantalla y exportaciones.
6. Los hallazgos de aula o identidad sin estudiante confirmado permanecen en
   `Detalle por materia`, los contadores y ambos reportes, con una advertencia visible.

El flujo unificado usa las funciones de catalogo y participantes; no requiere
consultar el directorio global de usuarios ni todas las aulas de cada estudiante.
Los endpoints anteriores se conservan para compatibilidad: `/preview` y
`/academic` sin `courses`. La interfaz envia siempre `period_code`, `career_code`
y una lista no vacia de `courses` al endpoint `/academic`.

El barrido es secuencial y se ejecuta en segundo plano con avance por curso.
Se permite un barrido activo por usuario y hasta cuatro en el proceso; repetir la
misma solicitud en ejecucion recupera su avance; deben coincidir periodo,
carrera, cursos y paralelos, independientemente del orden. No hay limite de estudiantes
del periodo/carrera. Los trabajos son de solo lectura, locales al proceso y con
retencion de 30 minutos tras finalizar (hasta 32 trabajos); un reinicio requiere
repetir la consulta. Con varios workers se necesita afinidad o almacenamiento
compartido. No modifica matriculas, codigos, notas ni esquemas de base de datos.

El resultado temporal pertenece al usuario que lo genero. Caduca a los 30 minutos,
al reiniciar el proceso o al superar 32 resultados en memoria. En esos casos se debe
validar nuevamente. El almacen es local al proceso; un despliegue con varios workers
requiere afinidad de sesion o sustituirlo por un almacen compartido con el mismo
control de propietario y vencimiento.

## Verificacion

```powershell
# Desde backend
../.venv/Scripts/python.exe -m pytest tests/test_moodle_enrollment_validation.py -q
# Desde la raiz, con Vite iniciado
$env:FRONTEND_TEST_URL='http://127.0.0.1:5175'
.venv/Scripts/python.exe frontend/tests/verify_moodle_enrollment_validation.py
```

Las pruebas de interfaz y de escritura del reporte usan datos sinteticos. Las
comprobaciones realizadas contra SQL Server y Moodle son consultas sin escrituras.
