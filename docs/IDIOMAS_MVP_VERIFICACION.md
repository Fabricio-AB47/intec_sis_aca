# Modulo de Idiomas - verificacion del MVP

## Alcance operativo

El modulo administra evidencias de video de los tres parciales de Idiomas. Solo
habilita al estudiante con matricula activa en `INTECBDD`, limita al docente a
sus asignaciones reales y conserva documentos, versiones, calificaciones y
auditoria en las bases complementarias.

Reglas vigentes:

- La matricula, materia, periodo, paralelo y docente se obtienen de
  `INTECBDD.dbo.CARRERAXESTUD` y `INTECBDD.dbo.CARRERAXDOCENTE`.
- El estudiante debe estar activo y matriculado en una carrera de tipo
  `IDIOMA` durante un periodo activo.
- Cada matricula dispone de P1, P2 y P3.
- Solo se admiten videos MP4, MOV, MKV o WEBM entre 50 MB y 2 GB.
- El limite de 2 GB se aplica de extremo a extremo en Idiomas: validacion del
  formulario, contrato del API, sesion documental y verificacion final contra
  el tamano informado por Microsoft Graph. Los otros modulos conservan su
  limite documental propio.
- Una carga temporal puede reemplazarse durante 15 minutos. La confirmacion
  definitiva o el cierre de la actividad bloquean el reemplazo ordinario.
- La calificacion se registra mediante rubrica de 0 a 10. Se aprueba con una
  nota igual o mayor a 7.
- Solo Academico o Administrador pueden reabrir una entrega, siempre con
  motivo y nueva fecha limite. La version anterior permanece en el historial.
- La publicacion sincroniza el examen del parcial en `CARRERAXESTUD` y actualiza
  el cumplimiento de Idiomas utilizado por Titulacion.

## Matriz de entregables

| ID | Estado | Evidencia implementada |
| --- | --- | --- |
| MI-01 | Cumple | Alcance y reglas documentados en este archivo y aplicados en el API. |
| MI-02 | Cumple | Consulta exacta de matricula, materia, periodo, paralelo y docente desde `INTECBDD`. |
| MI-03 | Cumple | Expediente, componentes, cargas, documentos, auditoria y reaperturas en `INTEC_EXPEDIENTE_ESTUDIANTIL`. |
| MI-04 | Cumple | Validacion de matricula activa para estudiante y alcance academico para docente. |
| MI-05 | Cumple | Autorizacion por rol y por pantalla `ingles`; el docente se restringe a su asignacion. |
| MI-06 | Cumple | Carga por sesion de Microsoft Graph hasta 2 GB; la base conserva metadatos y referencias, no el binario. |
| MI-07 | Cumple | Vista estudiantil con instrucciones, inicio, fecha limite, estado y parcial seleccionado. |
| MI-08 | Cumple | Validacion de video y tamano, progreso por fragmentos, vista previa y confirmacion explicita. |
| MI-09 | Cumple | Bloqueo por confirmacion, publicacion o vencimiento; reemplazo temporal de 15 minutos. |
| MI-10 | Cumple | Bandeja docente por periodo, asignatura, estudiante y estado de entrega. |
| MI-11 | Cumple | Reproduccion o apertura del video y observaciones asociadas a la rubrica. |
| MI-12 | Cumple | Rubrica ponderada, guardado de borrador y publicacion definitiva. |
| MI-13 | Cumple | Asentamiento controlado de P1/P2/P3 y recalculo academico en `INTECBDD`. |
| MI-14 | Cumple | Reapertura excepcional con motivo, nueva fecha, responsable, version anterior y auditoria. |
| MI-15 | Cumple | Pruebas automatizadas de archivos, fechas, rubrica, matricula docente y acceso por pantalla. |
| MI-16 | Cumple | Migracion idempotente y comandos reproducibles de validacion y despliegue. |
| MI-17 | Preparado | Guion de demostracion y acta de resultados incluidos en este documento. |

## Verificacion tecnica del ambiente - 04/08/2026

- Backend operativo en `http://127.0.0.1:8002`; `/health` y `/docs` responden
  HTTP 200.
- Frontend operativo en `http://127.0.0.1:5174` y compilacion de produccion
  completada.
- Microsoft Graph: credenciales configuradas, token emitido, unidad accesible
  y carpeta `EXPEDIENTES ESTUDIANTILES` localizada con HTTP 200.
- Base montada: 3 matriculas de Idiomas materializadas en 9 componentes
  activos P1/P2/P3. No existen componentes sin instrucciones, fecha de inicio
  o fecha limite.
- Estan disponibles las tablas de auditoria y reaperturas de Idiomas, junto
  con las tablas de expedientes y sesiones de carga de Graph.
- Regresion automatizada: 144 pruebas y 149 subpruebas aprobadas.
- Frontend: ESLint aprobado y catalogo validado con 118 accesos navegables.

La configuracion de una actividad puede realizarse antes de la primera carga:
la bandeja docente prepara el expediente exacto por matricula, periodo y
asignatura, y luego permite definir instrucciones y vigencia para P1, P2 o P3.

## Despliegue controlado

1. Ejecutar `backend/sql/2026_08_04_CIERRE_MVP_IDIOMAS.sql` con permisos de
   modificacion sobre `INTEC_EXPEDIENTE_ESTUDIANTIL`.
2. Verificar en `.env` la conexion a `INTECBDD`,
   `INTEC_EXPEDIENTE_ESTUDIANTIL`, Microsoft Graph y el sitio de expedientes.
3. Iniciar el backend en un puerto disponible:

   ```powershell
   cd backend
   .\scripts\ensure_backend_8002.ps1
   ```

4. Iniciar el frontend y abrir la pantalla asignada `Idiomas`:

   ```powershell
   cd frontend
   npm run dev
   ```

## Pruebas automatizadas

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run lint
npm run build
```

## Guion de aceptacion funcional

Registrar el resultado de cada caso como `Aprobado` o `Observado`.

| Caso | Resultado esperado | Resultado |
| --- | --- | --- |
| Estudiante activo y matriculado | Visualiza periodo, materia, P1-P3, instrucciones y vigencia. | Pendiente de acta |
| Estudiante sin matricula activa | La carga queda bloqueada y se informa la causa. | Pendiente de acta |
| Archivo no permitido o menor de 50 MB | El cliente y el servidor rechazan la carga. | Pendiente de acta |
| Video valido de hasta 2 GB | Muestra progreso, vista previa y opcion de confirmar. | Pendiente de acta |
| Reemplazo antes de 15 minutos | Crea nueva version y mantiene trazabilidad. | Pendiente de acta |
| Entrega confirmada o vencida | Impide reemplazo ordinario. | Pendiente de acta |
| Docente asignado | Ve solo sus periodos, materias, paralelos y estudiantes. | Pendiente de acta |
| Docente no asignado | No puede listar ni abrir la entrega. | Pendiente de acta |
| Borrador de rubrica | Guarda criterios y observacion sin publicar la nota. | Pendiente de acta |
| Publicacion de nota | Bloquea la rubrica, asienta el examen y recalcula la nota. | Pendiente de acta |
| Reapertura academica | Conserva version anterior, registra motivo y habilita un nuevo plazo. | Pendiente de acta |
| Perfil sin pantalla asignada | El backend responde 403 aunque conozca la ruta del API. | Pendiente de acta |

La presentacion MI-17 se considera aceptada cuando los responsables academicos
completan esta tabla con los resultados del ambiente de prueba y registran las
observaciones finales.
