# Auditoria De Seguridad

## Riesgo Actual

Antes del ajuste, la aplicacion tenia tres problemas mayores:

1. La autenticacion comparaba `login` y `password` dentro del SQL.
2. Teams y matricula se exponian sin una sesion real del backend.
3. El frontend guardaba la sesion en `localStorage`, por lo que la "proteccion" era solo visual.

## Cambios Aplicados

- Se movio la verificacion de password fuera de la consulta SQL.
- Se introdujo una cookie de sesion firmada (`HttpOnly`, configurable por entorno).
- Se agregaron `/api/auth/me` y `/api/auth/logout`.
- Se protegieron los routers de Teams y estudiantes con dependencias de autenticacion.
- Se centralizo la configuracion de Microsoft Graph en `Settings`, evitando lecturas inconsistentes de `.env`.
- El frontend ya no persiste la identidad en `localStorage`; ahora bootstrappea la sesion desde `/api/auth/me`.
- Se dejo compatibilidad heredada activa para passwords en texto plano mientras se realiza la migracion.

## Riesgos Pendientes

### Critico

- Si la tabla `USUARIO_SIS.password` sigue almacenando texto plano, el sistema sigue dependiendo de un dato inseguro en origen. El fallback legado sigue activo para no romper el acceso y debe retirarse tras la migracion.

### Alto

- Falta rate limiting para `login`.
- No hay trazabilidad de auditoria para altas/matriculas en Teams.
- No existe una matriz de permisos fina por rol y operacion.

### Medio

- No hay pruebas automatizadas para auth, expiracion de sesion y permisos.
- La cookie segura debe activarse en produccion con HTTPS (`SESSION_COOKIE_SECURE=true`).
- El secreto de sesion debe separarse del `CLIENT_SECRET` de Graph cuando se despliegue el entorno definitivo.

## Plan De Correccion

1. Migrar contrasenas a Argon2 y desactivar `AUTH_LEGACY_PLAINTEXT_ENABLED`.
2. Definir RBAC por endpoint: lectura, creacion y matriculacion de Teams por rol.
3. Agregar rate limiting y bloqueo temporal a `login`.
4. Registrar auditoria de eventos sensibles: login, logout, altas de Team, matriculas.
5. Agregar pruebas automatizadas de autenticacion, expiracion de sesion y permisos.
6. Separar secretos de sesion, Graph y base de datos por ambiente.
