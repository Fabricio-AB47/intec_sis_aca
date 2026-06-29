# Auditoria de seguridad OWASP Top 10

Fecha: 2026-06-29

Alcance revisado:
- Backend FastAPI en `backend/app`
- Frontend React/Vite en `frontend/src`
- Configuracion de entorno y cookies
- Subida de archivos, reportes PDF/Excel y evaluacion 360
- Dependencias frontend con `npm audit`

Referencia: OWASP Top 10 oficial.

## Resumen ejecutivo

El sistema tiene una base razonable en varias areas: uso de cookies `HttpOnly`, JWT firmado, consultas SQL mayoritariamente parametrizadas, roles en muchos routers, limites de tamano en varias cargas de archivos y `npm audit` sin vulnerabilidades detectadas.

Los riesgos principales estan en autorizacion incompleta de evaluacion 360, configuracion insegura por defecto para produccion, fallback de contrasenas en texto plano, falta de rate limiting/auditoria y endurecimiento HTTP incompleto.

## Hallazgos priorizados

### Critico - Evaluacion docente expone endpoints administrativos sin autenticacion

Categoria OWASP: Broken Access Control.

Evidencia:
- `backend/app/routers/teacher_evaluation.py` define `router = APIRouter(...)` sin dependencias globales.
- El archivo solo importa `APIRouter, HTTPException, Query`, no importa `Depends`, `get_current_user` ni `require_roles`.
- Endpoints administrativos sin dependencia visible: `/admin/periodos`, `/admin/pendientes`, `/admin/progreso-detalle`, `/admin/progreso-participantes`, `/admin/avance-estudiantes`, `/admin/docentes-calificados`, `/admin/reporte-docentes.pdf`.

Impacto:
- Cualquier cliente que conozca la URL podria consultar avance, participantes, calificaciones, docentes y generar PDF de evaluaciones.

Mejora:
- Separar router publico y router administrativo.
- Agregar `require_roles("ADMINISTRADOR", "ACADEMICO", "RECTOR", "VICERRECTOR")` a endpoints `/admin/*`.
- Para endpoints publicos de evaluacion, no confiar solo en cedula; usar token de aplicacion, sesion o enlace firmado por periodo/materia.

### Alto - Identidad por cedula y flujos publicos pueden filtrar datos personales

Categoria OWASP: Identification and Authentication Failures / Broken Access Control.

Evidencia:
- Endpoints publicos: `/identity/{cedula}`, `/student/{cedula}`, `/teacher/{cedula}`, `/evaluate`, `/teacher/evaluate`.
- El flujo usa cedula como llave para consultar informacion academica/evaluacion.

Impacto:
- Enumeracion de cedulas y exposicion de datos de estudiantes/docentes.
- Riesgo de evaluaciones no autorizadas si no se valida la identidad real del evaluador.

Mejora:
- Requerir sesion para estudiantes/docentes cuando sea posible.
- Si debe ser publico, generar tokens firmados por periodo, evaluador, materia y expiracion.
- Agregar rate limiting por IP/cedula y respuestas genericas.

### Alto - Contrasenas heredadas en texto plano siguen aceptadas

Categoria OWASP: Cryptographic Failures / Identification and Authentication Failures.

Evidencia:
- `auth_legacy_plaintext_enabled: bool = True`.
- `verify_password` acepta comparacion directa si el hash no es valido.
- `SECURITY_AUDIT.md` anterior ya indicaba esta deuda.

Impacto:
- Si una tabla de usuarios conserva texto plano, una filtracion de base expone credenciales reutilizables.

Mejora:
- Migrar a Argon2.
- En cada login exitoso con password legado, rehashear y guardar.
- Cambiar `AUTH_LEGACY_PLAINTEXT_ENABLED=false` en produccion.

### Alto - Cookies y TLS no estan endurecidos por defecto

Categoria OWASP: Security Misconfiguration / Cryptographic Failures.

Evidencia:
- `session_cookie_secure: bool = False`.
- `db_encrypt: str = "no"`.
- `db_trust_cert: str = "yes"`.
- Cookies Microsoft usan `secure=settings.session_cookie_secure`.

Impacto:
- En produccion sin HTTPS estricto, cookies pueden viajar sin marca `Secure`.
- Conexion SQL podria no validar cifrado/certificado.

Mejora:
- Produccion: `SESSION_COOKIE_SECURE=true`, `SESSION_COOKIE_SAMESITE=strict` o `lax` segun flujo.
- SQL Server: `DB_ENCRYPT=yes`, `DB_TRUST_CERT=no` con certificado valido.
- HSTS en proxy/IIS.

### Alto - Falta rate limiting en login y endpoints sensibles

Categoria OWASP: Identification and Authentication Failures / Security Logging and Monitoring Failures.

Evidencia:
- `/api/auth/login` no muestra bloqueo temporal ni limite por IP/usuario.
- Evaluacion publica por cedula tampoco muestra limite.

Impacto:
- Fuerza bruta, enumeracion de usuarios/cedulas y abuso de endpoints de reporte.

Mejora:
- Agregar middleware tipo slowapi/redis o limitador propio.
- Limites sugeridos: login 5 intentos/5 min por usuario+IP; identidad/evaluacion 30 req/min por IP.
- Registrar intentos fallidos.

### Medio - CSRF no esta tratado explicitamente

Categoria OWASP: Broken Access Control.

Evidencia:
- La sesion usa cookie `HttpOnly` con `SameSite=lax`, pero no se observa token CSRF para POST/PUT/DELETE.
- CORS permite credenciales.

Impacto:
- `SameSite=lax` mitiga bastante, pero no cubre todos los escenarios ni cambios futuros de dominios.

Mejora:
- Agregar token CSRF doble cookie/header para operaciones mutables.
- Mantener CORS con lista estricta, nunca `*` con credenciales.

### Medio - Falta auditoria funcional de acciones sensibles

Categoria OWASP: Security Logging and Monitoring Failures.

Evidencia:
- No se observa registro centralizado de login/logout, generacion de PDF, envios masivos, cambios de matricula, evaluaciones o subidas.

Impacto:
- Dificulta investigar cambios no autorizados o abuso interno.

Mejora:
- Crear tabla `AUDITORIA_SEGURIDAD` o similar.
- Registrar usuario, rol, IP, user-agent, accion, recurso, resultado y timestamp.
- No guardar passwords, tokens ni contenido sensible.

### Medio - Subidas de archivos tienen controles parciales

Categoria OWASP: Security Misconfiguration / Software and Data Integrity Failures.

Cumple:
- Hay limites en carnet, renombrador de certificados y correos masivos.
- Se sanea nombre de archivo en varios flujos.

Brechas:
- Preinscripcion documentos lee archivo completo y no se ve limite de tamano para documentos generales.
- Archivos subidos se sirven bajo `/uploads`; si entra contenido activo o HTML podria exponerse.

Mejora:
- Limitar tamano en todos los endpoints de upload.
- Validar extension y MIME real por tipo documental.
- Servir uploads con `Content-Disposition: attachment` donde aplique.
- Bloquear HTML/SVG/JS subido por usuarios.
- Considerar antivirus para adjuntos.

### Medio - SQL dinamico existe, aunque mayormente con partes controladas

Categoria OWASP: Injection.

Cumple:
- Muchas consultas usan parametros `?`.
- Los `IN ({placeholders})` se construyen con placeholders.

Riesgo:
- Hay SQL dinamico con nombres de columnas/tablas y `WHERE {" AND ".join(...)}`. Varias partes parecen controladas por catalogos internos, pero deben mantenerse con allowlists estrictas.

Mejora:
- Documentar helper de SQL seguro.
- Prohibir interpolar valores de usuario en SQL.
- Para columnas/tablas dinamicas, usar mapas allowlist.
- Agregar tests de inyeccion para filtros de busqueda.

### Medio - Headers de seguridad HTTP incompletos

Categoria OWASP: Security Misconfiguration.

Evidencia:
- `frontend/public/web.config` define cache headers, pero no CSP, HSTS, X-Frame-Options, Permissions-Policy, Referrer-Policy.

Mejora:
- Agregar en IIS/proxy:
  - `Strict-Transport-Security`
  - `Content-Security-Policy`
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy`

### Bajo - Dependencias frontend sin vulnerabilidades conocidas

Categoria OWASP: Vulnerable and Outdated Components.

Resultado:
- `npm audit --audit-level=moderate` retorno `found 0 vulnerabilities`.

Pendiente:
- No se ejecuto `pip-audit` porque no esta instalado en el entorno.

Mejora:
- Agregar `pip-audit` o `safety` al pipeline.
- Automatizar `npm audit` y `pip-audit` en CI.

## Matriz OWASP

| Categoria OWASP | Estado | Observacion |
| --- | --- | --- |
| Broken Access Control | No cumple completo | Evaluacion 360 admin sin auth visible; falta CSRF. |
| Cryptographic Failures | Parcial | JWT/cookies ok, pero TLS/SQL/cookies secure por defecto no productivo y password legado. |
| Injection | Parcial | Parametrizacion amplia; SQL dinamico requiere allowlists auditadas. |
| Insecure Design | Parcial | Flujos publicos por cedula deben reforzarse con token/sesion. |
| Security Misconfiguration | Parcial | Faltan headers, settings productivos y endurecimiento de uploads. |
| Vulnerable and Outdated Components | Parcial | Frontend limpio; falta auditoria Python automatizada. |
| Identification and Authentication Failures | Parcial | Sin rate limit; password legado; endpoints publicos enumerables. |
| Software and Data Integrity Failures | Parcial | Falta antivirus/validacion fuerte para uploads y adjuntos. |
| Security Logging and Monitoring Failures | No cumple completo | Falta auditoria central de eventos sensibles. |
| SSRF | Sin evidencia directa | No se detectaron fetches arbitrarios desde URLs de usuario; mantener allowlists en integraciones Graph. |

## Plan recomendado

### Prioridad 1

1. Proteger `/api/evaluacion-docente/admin/*` con roles.
2. Definir estrategia segura para evaluaciones publicas: sesion o token firmado.
3. Activar `SESSION_COOKIE_SECURE=true`, `SESSION_SECRET` propio y HTTPS.
4. Agregar rate limiting a login, identidad y evaluacion.

### Prioridad 2

1. Migrar passwords a Argon2 y desactivar fallback texto plano.
2. Agregar auditoria de eventos sensibles.
3. Validar y limitar todos los uploads, incluyendo documentos generales de preinscripcion.
4. Agregar headers de seguridad en IIS/proxy.

### Prioridad 3

1. Agregar pruebas automatizadas de auth/RBAC/CSRF.
2. Integrar `npm audit` y `pip-audit` al pipeline.
3. Revisar todos los SQL dinamicos con allowlists.
4. Documentar matriz de permisos por rol y endpoint.
