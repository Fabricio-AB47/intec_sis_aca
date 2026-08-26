# Integración Moodle y control de cuentas

## Alcance

La integración conecta el sistema académico con Moodle para consultar:

- Estado del servicio y funciones habilitadas.
- Usuarios existentes.
- Cursos existentes.
- Estado activo o suspendido de cada cuenta.

La única escritura autorizada es activar o suspender una cuenta existente. Antes de hacerlo, el backend valida que el correo exacto de Moodle exista en `INTECBDD.dbo.CorreosEstudIntec`, relacionado con `dbo.DATOS_ESTUD`, y registra el cambio en la auditoría de integración. No crea ni elimina usuarios y no modifica cursos, matrículas, módulos o calificaciones. Tampoco expone un ejecutor genérico de funciones Moodle.

## Arquitectura

El flujo es `frontend -> /api/moodle -> MoodleReadService -> MoodleClient -> Moodle REST`.

- `MoodleClient` realiza solicitudes `POST` de formulario y aplica listas cerradas e independientes para consulta y control de estado.
- `MoodleReadService` elimina campos privados, normaliza los datos, cachea resultados y ejecuta búsqueda, filtros y paginación local.
- El menú principal **Moodle** se construye desde **Asignación de pantallas** y ordena sus opciones alfabéticamente.
- Los permisos `moodle/courses`, `moodle/status` y `moodle/users` habilitan de forma independiente los submenús Cursos, Estado de la integración y Usuarios.
- Cada endpoint valida el permiso de su submenú; asignar una consulta no habilita las demás.
- La vista **Moodle** muestra únicamente las secciones asignadas al perfil. El control de cuentas se encuentra en **Usuarios** y requiere sus banderas específicas.
- El perfil **Administrador** recibe las tres pantallas de Moodle de forma predeterminada. Ningún otro perfil las recibe automáticamente; un administrador puede habilitarlas expresamente desde **Asignación de pantallas**.

## Funciones autorizadas

La lista permitida contiene exclusivamente:

1. `core_webservice_get_site_info`
2. `core_user_get_users`
3. `core_course_get_courses_by_field`
4. `core_user_update_users`, exclusivamente para el campo `suspended`.

Cualquier otra función se rechaza antes de realizar una solicitud HTTP. El navegador nunca envía `wsfunction` ni recibe el token.

## Configuración

```dotenv
MOODLE_BASE_URL=https://aulasintec.ec
MOODLE_ADMIN_TOKEN=
MOODLE_ENABLED=false
MOODLE_READS_ENABLED=true
MOODLE_WRITES_ENABLED=false
MOODLE_USER_STATUS_UPDATE_ENABLED=false
MOODLE_TIMEOUT_SECONDS=60
MOODLE_VERIFY_TLS=true
MOODLE_CACHE_TTL_SECONDS=120
MOODLE_FULL_USER_SCAN_ENABLED=false
MOODLE_MAX_USER_SCAN_ITEMS=20000
```

`MOODLE_TOKEN` también se acepta como alias de `MOODLE_ADMIN_TOKEN`. El token se carga como `SecretStr`, se envía solamente en el cuerpo del `POST` y no debe registrarse en Git. La aplicación puede iniciar sin el token; en ese caso, únicamente los endpoints Moodle responden `503`.

Para permitir activaciones y suspensiones deben estar habilitadas simultáneamente `MOODLE_WRITES_ENABLED=true` y `MOODLE_USER_STATUS_UPDATE_ENABLED=true`. Las banderas destructivas, de eliminación, desmatriculación y actualización de calificaciones permanecen independientes y deshabilitadas.

Para consultar el catálogo completo de usuarios debe habilitarse expresamente `MOODLE_FULL_USER_SCAN_ENABLED=true`. El límite `MOODLE_MAX_USER_SCAN_ITEMS` evita procesar respuestas mayores a lo autorizado.

## Endpoints

| Método | Ruta | Función Moodle |
| --- | --- | --- |
| `GET` | `/api/moodle/status` | `core_webservice_get_site_info` |
| `GET` | `/api/moodle/users` | `core_user_get_users` |
| `PATCH` | `/api/moodle/users/{user_id}/status` | `core_user_update_users` |
| `GET` | `/api/moodle/courses` | `core_course_get_courses_by_field` |

Usuarios acepta `page`, `page_size`, `email`, `state` y `refresh`; la búsqueda se realiza exclusivamente por correo electrónico. El cambio de estado acepta únicamente `{"active": true|false}`. Cursos acepta `page`, `page_size`, `search`, `visibility`, `category_id` y `refresh`. `page_size` admite entre 1 y 200 registros.

No existen rutas `/execute`, `/raw` o `/call`.

## Datos expuestos

Usuarios:

`id`, `username`, `firstname`, `lastname`, `fullname`, `email`, `idnumber`, `institution`, `department`, `auth`, `suspended`, `confirmed`, `firstaccess`, `lastaccess`, `profileimageurlsmall` y `status`.

Cursos:

`id`, `fullname`, `displayname`, `shortname`, `idnumber`, `categoryid`, `categoryname`, `summary`, `format`, `visible`, `startdate`, `enddate`, `enablecompletion`, `timecreated` y `timemodified`.

El resumen HTML del curso se convierte a texto. Se descartan contraseñas, claves privadas, `userprivateaccesskey`, campos personalizados, archivos internos, advertencias, `debuginfo` y cualquier propiedad no incluida expresamente.

## Caché y paginación

Usuarios y cursos mantienen cachés independientes con bloqueos asíncronos para evitar cargas duplicadas. Moodle entrega el catálogo al backend; los filtros, el orden y la paginación se ejecutan localmente. `refresh=true` invalida únicamente el catálogo consultado.

La consulta global de usuarios puede ser costosa en instalaciones grandes. Debe mantenerse un TTL razonable y un límite acorde a la capacidad del servidor Moodle.

## Errores

- Configuración ausente, integración deshabilitada o límite excedido: `503`.
- Error de conexión o respuesta Moodle inválida: `502`.
- Tiempo agotado: `504`.
- Parámetros locales inválidos: `422`.
- Correo institucional inexistente o cuenta no confirmada: `409`.
- Escritura de estado deshabilitada: `503`.
- Sesión o pantalla no autorizada: comportamiento estándar `401/403` del proyecto.

Los mensajes remotos se truncan y sanitizan. Cuando existe contexto de auditoría, el router incluye `X-Request-ID`.

## Pruebas

Desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q tests/test_moodle_client.py
..\.venv\Scripts\python.exe -m pytest -q tests/test_moodle_read_service.py
..\.venv\Scripts\python.exe -m pytest -q tests/test_moodle_router.py
```

Las pruebas utilizan `httpx.MockTransport` y servicios simulados; no se conectan a `aulasintec.ec`.

## Inicio local

Desde `backend`, inicie FastAPI sin recarga automática para evitar conflictos de sockets en Windows:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Desde `frontend`:

```powershell
npm run dev
```

La interfaz queda disponible en `http://127.0.0.1:5174/`. La pantalla **Moodle** aparece dentro de **Integraciones** y se habilita por perfil desde **Asignación de pantallas**.

## Operación segura

- Mantener `MOODLE_WRITES_ENABLED=false` y `MOODLE_USER_STATUS_UPDATE_ENABLED=false` cuando no se requiera administrar cuentas.
- Habilitar ambas banderas solo en ambientes autorizados y conservar `core_user_update_users` como única función de escritura publicada para este módulo.
- Mantener deshabilitadas todas las banderas destructivas existentes en el entorno.
- Asignar la pantalla Moodle solo a perfiles administrativos autorizados.
- Rotar inmediatamente cualquier token que haya sido compartido fuera del gestor de secretos.
