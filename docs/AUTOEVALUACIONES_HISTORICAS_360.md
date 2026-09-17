# Autoevaluaciones históricas administrativas

## Ubicación y acceso

Desempeño > Autoevaluaciones históricas. La pantalla independiente
`evaluacion-docente-historicas` se incorpora al catálogo asignable, con acceso
inicial para Administrador. Las decisiones manuales de asignación se conservan.
El backend exige la pantalla y un rol administrativo de evaluación autorizado.

Avance y ponderación, Documentos de evaluación y Autoevaluaciones históricas
incluyen una navegación superior común de Desempeño. Cada acceso se muestra
únicamente cuando su pantalla está asignada. Desmarcar el permiso también lo
retira de esta navegación, sin accesos alternativos que eludan la asignación.

## Alcance

- Períodos cuyo inicio corresponde a 2023, 2024 o 2025. Se usa `PERIODO.fechain`;
  cuando no existe fecha, el primer año explícito del nombre del período.
- Docentes actualmente activos en `USUARIOS`, relacionados por cédula normalizada
  con `DATOSDOCENTE`, con asignaciones en `CARRERAXDOCENTE` y materias con al menos
  una matrícula con promedio final. El catálogo y los cursos excluyen inactivos.
  El estado se vuelve a validar en la vista previa y antes de confirmar; si un
  docente fue desactivado, se detiene el proceso sin confirmar el bloque actual.
  Los bloques confirmados previamente se conservan.
- El catálogo relaciona los docentes activos con sus períodos de clases en
  `CARRERAXDOCENTE`. Sin períodos seleccionados, no se muestran docentes para
  generar. Al seleccionar varios, se muestra la unión de docentes que dictaron
  clases en al menos uno de esos períodos, sin duplicados. Cambiar los períodos
  desmarca automáticamente los docentes que dejan de corresponder e invalida la
  vista previa. El servidor vuelve a comprobar esta relación antes de guardar.
- Materias comunes consolidadas por código único, docente, período, paralelo y
  jornada. Las materias numéricas relacionadas se revisan contra duplicados.
- Instrumento actual de autoevaluación, sin atribuirle una versión histórica
  inexistente. Solo se admite escala 1 a 5 y al menos dos preguntas; con una sola
  pregunta no es posible cumplir el rango sin alterar la escala. Todas se contestan.
- Respuestas aleatorias válidas 4 y 5, con promedio de autoevaluación desde 9,00
  y estrictamente menor que 10,00 sobre 10, equivalente a desde 90 y menos de 100
  sobre 100. El máximo alcanzable depende de la cantidad de preguntas. Se reserva
  una cantidad de respuestas 4 que impide alcanzar 10,00 por redondeo, incluso
  al redondear primero el promedio de la escala a dos decimales. No se modifica
  la ponderación ni se promete ese rango para el resultado final 360 de todos
  sus componentes. Las evaluaciones ya guardadas conservan sus notas originales.
- No existe un límite funcional en la cantidad de docentes, períodos o
  formularios seleccionados. Los períodos siguen restringidos a 2023-2025 y los
  docentes deben estar activos. La capacidad depende de los recursos del servidor.
- `Seleccionar todos` marca todos los docentes activos relacionados con los
  períodos seleccionados, incluso
  cuando existe un filtro de búsqueda. `Seleccionar visibles` mantiene la opción
  de seleccionar solo coincidencias y `Limpiar` desmarca toda la selección.

## Vista previa y guardado

La vista previa no crea campañas, aplicaciones ni respuestas. Un token firmado,
válido durante 30 minutos y vinculado al usuario, identifica la selección, la
semilla, la regla de generación y la configuración de preguntas y asignaciones. Las respuestas mostradas
son las mismas que se guardan, no se vuelven a sortear al confirmar.

La generación masiva no exige confirmación individual ni una sesión del docente.
La autorización del administrador del lote exige un motivo y aceptación explícita.
Se vuelven a revisar las
asignaciones, el instrumento y las evaluaciones existentes. Si cambió la
configuración o el rango de generación, se requiere otra vista previa. Las vistas
previas del rango anterior no pueden confirmarse con respuestas del nuevo rango.
Si apareció una autoevaluación
realizada, se conserva y se omite la generación correspondiente.

Un bloqueo transaccional compartido con la autoevaluación normal serializa los
guardados de esta aplicación. Las respuestas se insertan por lote y se reutiliza
la campaña por período. Ante un error se revierte el bloque actual. Repetir la
misma confirmación no reemplaza registros creados o existentes.

La interfaz confirma una sola selección y realiza solicitudes sucesivas de 100
formularios hasta completar todos. Este tamaño es interno, no un límite total.
Cada bloque tiene su propia transacción: un error revierte solo el bloque actual,
conservando los bloques previos. Una subpantalla se abre al iniciar el guardado y
muestra el porcentaje confirmado, formularios procesados, creados y existentes
conservados. Los errores y el botón de reintento están en esa misma subpantalla;
cerrarla solo oculta el avance, sin cancelar el lote mientras la página siga
abierta. `Ver avance` permite volver a abrirla y admite cierre con Escape.
El resumen verde de finalización se muestra únicamente dentro de esa subpantalla.
Al cerrarla se oculta, y al abrirla nuevamente conserva las cantidades y el lote,
sin repetir el guardado ni mostrar un mensaje duplicado en la página principal.
`Reintentar pendientes` vuelve al último bloque sin confirmar y omite duplicados.
El servidor renueva el token después de cada bloque, manteniendo el mismo lote,
usuario, semilla y configuración. No hay un límite de duración total del proceso,
aunque se mantienen las políticas normales de vigencia de la sesión.

La pantalla debe permanecer abierta durante el proceso. Si se cierra o se cambia
de apartado, se detienen las siguientes solicitudes después del bloque en curso.
Al volver, una nueva vista previa reconoce lo ya guardado y conserva esos registros.
No se ejecuta como tarea independiente en segundo plano.

Las consultas SQL dividen los identificadores en grupos internos de 500 para no
superar la cantidad de parámetros de SQL Server, sin recortar la selección. Los
clientes que envían `/generar` sin `offset` conservan el guardado sincrónico de la
selección completa en una transacción, también sin límite funcional de cantidad.

## Base de datos y trazabilidad

Se usan las tablas existentes `eval360.Aplicacion`, `eval360.Respuesta` y
`eval360.Campania` de la conexión de evaluaciones. No se requiere crear otra base
ni cambiar el esquema de tablas.

La creación de campañas y aplicaciones captura el identificador con `OUTPUT
INSERTED ... INTO` una variable de tabla y lo devuelve en un `SELECT` final.
Esto permite guardar con los disparadores de auditoría activos. Usar `OUTPUT`
sin `INTO` sobre estas tablas provocaba el error 334 de SQL Server y detenía el
lote antes de confirmar. No se deshabilita ni se omite la auditoría.

`Aplicacion.Observacion_General` guarda el prefijo
`AUTO_DOCENTE_GENERADA_V1:` y metadatos JSON: lote, responsable, rol, fecha real UTC,
motivo, instrumento, resultado y versión de la regla de generación. Los nuevos
registros también conservan código, nombre y cédula del docente al generar,
normalizando espacios y guiones sin convertir la cédula a un número ni perder
ceros iniciales. Si falta la cédula, la vista previa rechaza el proceso antes de
guardar. El origen del evaluador es
`SISACA.AUTO_DOCENTE_GENERADA`; el docente representa el sujeto de la
autoevaluación, no el autor material de las respuestas.

Las fechas de generación son actuales, nunca se retrofechan. Los informes
oficiales de autoevaluación y resultado 360 incluyen una advertencia explícita
de generación administrativa y su trazabilidad. Estas respuestas no deben
presentarse como realizadas personalmente por el docente.

Cada documento PDF docente se ajusta a una sola página A4, conservando las
preguntas completas, sus notas, la información del docente, la trazabilidad y
la firma. El detalle agrupa las celdas repetidas de materia y dimensión, y
reserva ancho suficiente para mostrar completos los encabezados de evaluaciones
y respuestas. Si el contenido supera el espacio, se ajusta proporcionalmente
sin truncar filas; los documentos más extensos pueden requerir ampliar el PDF
para leer el texto. Las descargas masivas mantienen un documento por docente.

El historial muestra los últimos 2000 registros identificados, paginados en la
interfaz: docente vinculado y cédula, origen administrativo, responsable real de
generación, fecha, lote y motivo. Usa la identidad conservada en el registro,
aunque el docente cambie de nombre o ya no esté en el catálogo de activos. Los
registros antiguos sin esa identidad usan el catálogo disponible, sin alterar
sus metadatos ni atribuir la generación al docente. La consulta es de solo lectura.

## Verificación

Las pruebas cubren rango y escala, semillas reproducibles, períodos históricos,
token vinculado al responsable, duplicados y códigos relacionados, confirmación,
reversión del bloque, permisos y advertencia en PDF. La verificación de navegador
usa API simulada, sin guardar evaluaciones institucionales.

También se verificó la navegación en escritorio y móvil con la asignación real
de Administrador y el catálogo consultado en INTECBDD: 26 períodos históricos y
49 docentes activos con asignaciones en esos períodos al momento de la revisión.
Los docentes con clases únicamente fuera de esos períodos no se incluyen. También
se comprobó el filtro para períodos individuales y el rechazo de docentes sin
clases en ellos. La sesión de navegador fue simulada;
no se ejecutaron solicitudes de escritura contra las bases institucionales.

La vista previa real de toda esa selección devuelve 782 formularios (781 pendientes
y uno existente), sin el antiguo tope de 500. Con el instrumento actual de 40
preguntas, las notas pendientes verificadas estuvieron entre 9,00 y 9,95. Esta
comprobación fue de solo lectura, sin generar registros institucionales.
Las pruebas simuladas de interfaz incluyen 550 docentes, 111 períodos y 701
formularios, interrupción intermedia y continuación hasta completar la selección.

Referencia del bloqueo:
[Microsoft: sys.sp_getapplock](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql).

Referencia de compatibilidad con disparadores:
[Microsoft: OUTPUT y triggers](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql#triggers).
