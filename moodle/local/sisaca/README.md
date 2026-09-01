# Complemento local SISACA para Moodle 4.3

Este complemento publica la funcion externa
`local_sisaca_bulk_update_evaluation_dates`. La funcion actualiza, dentro de
un curso verificado:

- tareas: apertura, entrega y cierre definitivo;
- cuestionarios: apertura y cierre;
- calendario, cache del curso y evento de auditoria de Moodle.

## Instalacion

1. Comprima la carpeta `sisaca` y carguela en **Administracion del sitio >
   Plugins > Instalar plugins**, como complemento de tipo `local`.
2. Complete la actualizacion de la base de datos de Moodle.
3. Revise **Administracion del sitio > Servidor > Servicios web > Servicios
   externos > SIS_ACA > Funciones**. La funcion se incorpora automaticamente
   cuando el servicio se llama `SIS_ACA`; si el servicio tiene otro nombre,
   agregue manualmente `local_sisaca_bulk_update_evaluation_dates`.
4. Confirme que el usuario propietario del token tenga la capacidad
   `moodle/course:manageactivities` en los cursos que administrara.
5. En el backend configure:

   ```env
   MOODLE_WRITES_ENABLED=true
   MOODLE_EVALUATION_DATES_UPDATE_ENABLED=true
   MOODLE_EVALUATION_DATES_FUNCTION=local_sisaca_bulk_update_evaluation_dates
   ```

La aplicacion comprueba que la funcion pertenezca al servicio del token antes
de habilitar los campos. Por ello, no se presentan controles de escritura que
Moodle no pueda ejecutar.
