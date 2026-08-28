# Endurecimiento de seguridad OWASP

Este documento describe los controles técnicos incorporados en `INTEC_SIS_ACA` y las condiciones necesarias para desplegarlo. La referencia funcional es OWASP Top 10:2025 y el criterio de verificación recomendado es OWASP ASVS 5.0.

## Controles incorporados

| Riesgo OWASP 2025 | Control en el proyecto |
| --- | --- |
| A01 Control de acceso roto | Dependencias de rol y pantalla en el backend, eliminación de la ampliación implícita de roles, rutas administrativas de evaluación protegidas y archivos locales disponibles solo con sesión. |
| A02 Configuración incorrecta | Validación que impide iniciar producción con documentación API, CORS, cookies, hosts, HSTS, CSRF o errores internos configurados de forma insegura. |
| A03 Cadena de suministro | Versiones fijadas, auditoría semanal de `pip` y `npm`, Dependabot, análisis CodeQL y detección de secretos con Gitleaks. |
| A04 Fallos criptográficos | Argon2 para contraseñas nuevas, JWT con emisor, audiencia, tipo, vigencia e identificador único; TLS obligatorio para SQL Server, Moodle, Graph y SMTP en producción. |
| A05 Inyección | Uso de parámetros en consultas `pyodbc`; las entradas no deben concatenarse como identificadores SQL sin listas permitidas. |
| A06 Diseño inseguro | Límites de tamaño, validaciones del lado servidor, bloqueo de configuración insegura y autorización independiente de la interfaz. |
| A07 Fallos de autenticación | Respuesta de acceso genérica, limitación de intentos por IP y cuenta, cookie `HttpOnly`, control de expiración y estado OAuth de un solo uso. |
| A08 Integridad de software o datos | Dependencias auditadas, trazabilidad de operaciones, control de tipos/tamaños en los flujos documentales y descargas forzadas para formatos no visualizables. |
| A09 Registro y alertas | `request_id`, contexto de usuario en SQL Server y registro servidor de excepciones sin exponer detalles al cliente. |
| A10 Manejo de condiciones excepcionales | Respuesta global genérica para errores no controlados, detalle disponible únicamente en logs internos y límites defensivos de solicitudes. |

## Perfil obligatorio de producción

Configure, como mínimo:

```dotenv
APP_ENVIRONMENT=production
API_DOCS_ENABLED=false
EXPOSE_INTERNAL_ERRORS=false
SECURITY_HEADERS_ENABLED=true
SECURITY_HSTS_ENABLED=true
CSRF_PROTECTION_ENABLED=true
CSRF_REQUIRE_ORIGIN=true
TRUSTED_HOSTS=api.dominio-institucional.ec
CORS_ORIGINS=https://sistema.dominio-institucional.ec
CORS_ALLOWED_HEADERS=Accept,Accept-Language,Authorization,Content-Language,Content-Type,If-Modified-Since,If-None-Match,Range,X-Evaluation-Token,X-Request-ID,X-Requested-With
FRONTEND_BASE_URL=https://sistema.dominio-institucional.ec
GRAPH_DELEGATE_REDIRECT_URI=https://api.dominio-institucional.ec/api/auth/microsoft/callback

SESSION_SECRET=<valor-aleatorio-de-al-menos-32-caracteres>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
AUTH_LEGACY_PLAINTEXT_ENABLED=false

DB_DRIVER=ODBC Driver 18 for SQL Server
DB_ENCRYPT=yes
DB_TRUST_CERT=no
```

Las bases complementarias deben heredar esos valores o declarar sus correspondientes `*_DB_ENCRYPT=yes` y `*_DB_TRUST_CERT=no`. El certificado de SQL Server debe ser válido para el nombre usado en `DB_HOST`.

## Operación requerida

1. Migrar las contraseñas heredadas a Argon2 antes de deshabilitar definitivamente el modo heredado. No se permite texto plano en producción.
2. Rotar cualquier token o contraseña que haya aparecido en commits, capturas, chats o logs. Eliminarlo del código no revoca el secreto.
3. Ejecutar las pruebas, Gitleaks, `pip-audit` y `npm audit` antes de desplegar.
4. Usar cuentas SQL distintas por servicio, con permisos mínimos y sin rol `db_owner` para la aplicación.
5. Centralizar logs y alertas, conservar `X-Request-ID` y restringir el acceso a datos de auditoría.
6. En despliegues con varios procesos o servidores, sustituir el limitador local por Redis u otro almacén compartido.
7. Analizar adjuntos con antimalware antes de su publicación y mantener el directorio de carga fuera de la raíz pública.
8. Realizar una prueba DAST y una prueba de penetración autenticada antes de declarar el sistema apto para producción.
9. La prueba `test_sensitive_api_routes_require_an_authenticated_session` debe permanecer activa: evita incorporar rutas API sensibles sin sesión por error.

## Verificación

```powershell
cd backend
python -m pytest tests -q

cd ../frontend
npm audit --audit-level=high
npm run build
```

Estos controles reducen los riesgos identificados; no constituyen por sí solos una certificación ni reemplazan la revisión de infraestructura, permisos efectivos, rotación de secretos y pruebas de penetración.
