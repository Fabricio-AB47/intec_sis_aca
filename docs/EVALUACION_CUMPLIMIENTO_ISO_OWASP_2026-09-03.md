# Evaluación de cumplimiento ISO y OWASP del Sistema Académico INTEC

**Fecha de evaluación:** 3 de septiembre de 2026  
**Repositorio:** `intec_sis_aca`  
**Rama y versión revisadas:** `main`, commit `1a6b86b`  
**Modalidad:** revisión documental, análisis estático y comprobaciones externas no intrusivas  
**Resultado general:** **cumplimiento parcial; no certificable con la evidencia disponible**

## 1. Objetivo

Evaluar, punto por punto, la evidencia de seguridad y calidad del desarrollo frente a:

- OWASP Top 10:2025.
- ISO/IEC 27001:2022, gestión de seguridad de la información.
- ISO/IEC 27002:2022, controles de seguridad de la información.
- ISO/IEC 27005:2022, gestión de riesgos de seguridad.
- ISO/IEC 27034-1:2011, seguridad de aplicaciones.
- ISO/IEC/IEEE 12207:2026, procesos del ciclo de vida del software.
- ISO/IEC 25010:2023, modelo de calidad del producto de software.
- ISO/IEC 27701:2025, gestión de privacidad de información personal.

Esta evaluación explica el estado y propone acciones. **No se modificó código, configuración, IIS, base de datos ni datos de producción.** La creación de este informe es el único archivo generado.

## 2. Alcance y limitaciones

### 2.1 Incluido

- Backend FastAPI/Python, frontend React/TypeScript y configuración IIS versionada.
- Autenticación, autorización por rol y pantalla, sesiones, CSRF, CORS y cabeceras HTTP.
- Consultas SQL, manejo de excepciones, carga de archivos e integraciones externas.
- Dependencias, pruebas automatizadas y flujos de seguridad de GitHub Actions.
- Comprobación pública de HTTPS, protocolos TLS, certificado y cabeceras HTTP.
- Documentación de seguridad, despliegue y operación existente en el repositorio.

### 2.2 No incluido

- Prueba de penetración, DAST autenticado, explotación, fuzzing o carga destructiva.
- Revisión completa de permisos efectivos de SQL Server, Microsoft 365, Moodle o cuentas de servicio.
- Lectura de secretos, contenido académico o datos personales en producción.
- Entrevistas, contratos, inventarios institucionales, evidencias de capacitación, auditorías internas o revisión de la dirección.
- Revisión certificadora contra el texto completo licenciado de cada norma ISO.

Por estas limitaciones, “cumple” significa que existe evidencia técnica suficiente dentro del alcance; no equivale a una certificación ISO.

## 3. Criterio de evaluación

| Estado | Interpretación |
| --- | --- |
| Cumple | Existe evidencia verificable y no se observó una brecha material dentro del alcance. |
| Parcial | Hay controles implementados, pero existen brechas o falta validación operativa. |
| No cumple | Se comprobó una condición incompatible con el control evaluado. |
| No evidenciado | No se encontró evidencia suficiente; no implica necesariamente que el proceso no exista fuera del repositorio. |
| No aplica | El requisito no corresponde al alcance o arquitectura observada. |

## 4. Resumen ejecutivo

El sistema tiene una base de seguridad técnica relevante: autenticación obligatoria para las rutas privadas, autorización por roles y pantallas, contraseñas nuevas con Argon2, cookies `HttpOnly`, validación de JWT, defensa CSRF, cabeceras de seguridad en la API, trazabilidad por `request_id`, contexto de auditoría SQL, dependencias fijadas, análisis CodeQL/Gitleaks/Dependabot y una suite de pruebas amplia.

La revisión ejecutó **543 pruebas y 216 subpruebas**, todas aprobadas, con una advertencia de deprecación. `npm audit --audit-level=high --omit=dev` informó **0 vulnerabilidades**. No fue posible repetir localmente `pip-audit` porque la herramienta no está instalada en el entorno virtual; sí está declarada como control obligatorio en CI.

No obstante, todavía no puede declararse cumplimiento integral ni aptitud final de producción. Los principales motivos son:

1. El endpoint público acepta **TLS 1.0 y TLS 1.1**, protocolos heredados que deben quedar deshabilitados.
2. La configuración efectiva de los procesos en ejecución no pudo acreditarse como `production`; la configuración cargada desde una sesión administrativa separada devolvió perfil `development`, cifrado SQL no obligatorio y compatibilidad con contraseña legada. El código contiene un bloqueo de arranque seguro para producción, pero este solo protege si el entorno se identifica correctamente.
3. Se localizaron **38 puntos** que construyen respuestas HTTP a partir de `str(exc)` o detalles derivados de excepciones. El middleware enmascara los errores 500 y, cuando reconoce producción, todos los 5xx; una identificación incorrecta del entorno permite que respuestas 502/503/504 revelen información interna. El error ODBC mostrado previamente por la operación de becas es consistente con esta brecha.
4. El limitador de acceso es local en memoria, mientras que el servicio observado usa dos trabajadores en el puerto principal; por ello, el límite no es global ni persistente.
5. El límite global de cuerpo es 2,2 GB y no se encontró un control antimalware transversal para adjuntos. Además, la validación global depende de `Content-Length`, por lo que deben evaluarse cargas fragmentadas y límites en IIS/proxy.
6. No hay evidencia suficiente de un SGSI/PIMS formal: alcance, inventario y clasificación de activos, registro de riesgos, Declaración de Aplicabilidad, responsables, aceptación de riesgos, métricas, auditorías internas, revisión directiva, privacidad, retención y respuesta a incidentes.

### 4.1 Conteo de hallazgos

| Prioridad | Cantidad | Identificadores |
| --- | ---: | --- |
| Alta | 5 | H-01 a H-05 |
| Media | 4 | H-06 a H-09 |
| Baja | 1 | H-10 |

No se identificó un hallazgo crítico mediante esta revisión no intrusiva. Esto no descarta vulnerabilidades que solo aparecerían en una prueba de penetración autenticada.

## 5. Evaluación OWASP Top 10:2025

OWASP Top 10 es un documento de concienciación sobre riesgos, no un esquema de certificación. Para una verificación posterior basada en requisitos comprobables conviene usar OWASP ASVS 5.0, nivel 2 como mínimo por el tratamiento de información académica y personal.

### A01:2025 — Broken Access Control

**Estado: Parcial**  
**Riesgo residual: Medio**

Evidencia favorable:

- `backend/app/core/security.py` implementa `get_current_user`, `require_roles`, `require_screen_access` y `require_any_screen_access`.
- `backend/tests/test_http_security.py:38` recorre las rutas API y falla si una ruta privada no depende de una sesión autenticada.
- Los accesos por pantalla se comprueban en backend; el menú visual no es el único control.
- Hay pruebas específicas de ámbito docente, documentos, idiomas, calificaciones y pantallas.

Brechas:

- La prueba de cobertura confirma autenticación, pero no demuestra por sí sola autorización objeto por objeto contra todos los identificadores de estudiante, curso, solicitud o documento.
- No existe evidencia de una matriz institucional aprobada de roles, operaciones, propietarios y segregación de funciones.
- No se realizó una prueba IDOR/BOLA autenticada con perfiles cruzados.

Acción recomendada: mantener la prueba automática actual, añadir pruebas negativas por objeto y operación, aprobar una matriz RBAC/ABAC y ejecutar pentest autenticado con al menos estudiante, docente, secretaría, financiero y administrador.

### A02:2025 — Security Misconfiguration

**Estado: Parcial**  
**Riesgo residual: Alto**

Evidencia favorable:

- `backend/app/core/config.py:273` contiene validaciones que impiden iniciar un entorno declarado como producción con documentación API, cookies, CSRF, CORS, hosts, HSTS, errores internos o TLS SQL inseguros.
- La API pública devuelve CSP restrictiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, no-cache y HSTS.
- IIS redirige HTTP a HTTPS en `frontend/public/web.config`.

Brechas verificadas:

- TLS 1.0 y TLS 1.1 fueron aceptados por `sistema-academico.intec.edu.ec` el 3 de septiembre de 2026.
- El HTML y los recursos estáticos de IIS publican HSTS, pero no CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP ni CORP.
- Se exponen `Server: Microsoft-IIS/10.0` y, en la API, `X-Powered-By: ARR/3.0`.
- La sesión administrativa usada para revisar el repositorio cargó valores de desarrollo. No fue posible probar que el entorno de cada trabajador Uvicorn usa el perfil seguro.

Acción recomendada: deshabilitar TLS 1.0/1.1 en SCHANNEL/IIS, verificar TLS después del reinicio controlado, acreditar las variables efectivas sin revelar secretos, añadir cabeceras al frontend estático y reducir la identificación de servidor. Hacer estos cambios primero en una ventana con respaldo y rollback.

### A03:2025 — Software Supply Chain Failures

**Estado: Parcial**  
**Riesgo residual: Medio**

Evidencia favorable:

- Las 28 dependencias Python de `backend/requirements.txt` están fijadas con versión exacta.
- `frontend/package-lock.json` está versionado; la auditoría npm ejecutada no encontró vulnerabilidades.
- `.github/dependabot.yml` revisa semanalmente pip, npm y GitHub Actions.
- `.github/workflows/security-ci.yml`, `codeql.yml` y `secret-scan.yml` incorporan pruebas, auditorías de dependencias, CodeQL y Gitleaks.
- No se encontraron `.env`, llaves privadas o certificados privados versionados; solo el ejemplo permitido.

Brechas:

- No se pudo ejecutar localmente `pip-audit`; debe confirmarse el resultado del último CI exitoso.
- Las acciones de GitHub se referencian por etiquetas mayores (`@v2`, `@v3`, `@v4`, `@v7`) y no por SHA inmutable.
- No se encontró SBOM, firma de artefactos, procedencia verificable, inventario de componentes desplegados ni política documentada de respuesta a vulnerabilidades de terceros.

Acción recomendada: exigir CI verde antes del despliegue, fijar Actions por SHA con actualización automatizada, producir SBOM CycloneDX/SPDX por versión, firmar artefactos y conservar evidencia de procedencia y aprobación.

### A04:2025 — Cryptographic Failures

**Estado: Parcial**  
**Riesgo residual: Alto**

Evidencia favorable:

- `backend/app/core/security.py` usa Argon2 para hashes nuevos.
- Los JWT validan algoritmo permitido, emisor, audiencia, identificador, tipo, inicio y expiración.
- Las cookies de sesión son `HttpOnly`; el endpoint público opera con HTTPS y HSTS.
- El certificado público observado es válido, emitido por Let's Encrypt, vigente del 5 de agosto al 3 de noviembre de 2026.
- La configuración de producción exige cifrado SQL, validación del certificado y TLS para Moodle/SMTP.

Brechas:

- TLS 1.0/1.1 siguen habilitados.
- La compatibilidad con contraseñas legadas está habilitada en el perfil cargado durante la revisión. Si existen valores históricos no Argon2, podrían compararse como texto plano.
- La sesión revisora mostró `DB_ENCRYPT=no` y `DB_TRUST_CERT=yes`; la configuración efectiva de los procesos publicados no fue atestiguada.
- No hay evidencia de política de rotación de secretos, custodia en bóveda, inventario de claves, caducidad ni simulacro de renovación del certificado.

Acción recomendada: eliminar protocolos heredados, completar migración Argon2, desactivar el modo legado, exigir certificado SQL confiable y documentar ciclo de vida de secretos/certificados con alerta de renovación previa al vencimiento.

### A05:2025 — Injection

**Estado: Parcial**  
**Riesgo residual: Medio**

Evidencia favorable:

- Se observó uso amplio de parámetros `?` de `pyodbc` y validación de entradas con Pydantic/FastAPI.
- La revisión simple contabilizó 1.052 llamadas `execute`/`executemany` y no encontró una llamada directa de la forma `execute(f"...")` en la misma línea.
- Las pruebas cubren múltiples reglas académicas y operaciones de escritura.

Brechas:

- La ausencia del patrón directo no demuestra que todas las consultas sean seguras: el repositorio construye fragmentos SQL auxiliares e identificadores dinámicos que necesitan revisión de flujo de datos y listas permitidas.
- El error de collation aportado en el proceso de becas muestra que errores SQL internos han llegado a la interfaz.
- No se ejecutaron SAST especializado de SQL, DAST, pruebas de inyección ni revisión manual completa de las 1.052 ejecuciones.

Acción recomendada: inventariar toda interpolación de identificadores, usar listas permitidas cerradas, revisar procedimientos almacenados y ejecutar pruebas automatizadas de SQLi, XSS, command injection, template injection y LDAP/XML cuando corresponda.

### A06:2025 — Insecure Design

**Estado: Parcial**  
**Riesgo residual: Medio-Alto**

Evidencia favorable:

- Existen validaciones de negocio en backend, controles independientes de la interfaz, límites de entrada, auditoría y pruebas funcionales por módulo.
- La configuración segura de producción aplica un enfoque de fallo al cerrar para varias opciones sensibles.

Brechas:

- No se encontró modelo de amenazas, casos de abuso, clasificación de datos, requisitos de seguridad trazables ni criterios formales de aceptación de riesgo.
- No se evidenció revisión arquitectónica de límites de confianza entre IIS, FastAPI, SQL Server, Moodle, Microsoft Graph, OneDrive y SMTP.
- La carga potencial de hasta 2,2 GB y las integraciones de larga duración requieren un diseño explícito contra agotamiento de recursos, reintentos, duplicados y fallos parciales.

Acción recomendada: elaborar diagramas de flujo de datos, STRIDE por módulo crítico, casos de abuso, límites de consumo, idempotencia y criterios de aceptación de seguridad antes de cada funcionalidad sensible.

### A07:2025 — Authentication Failures

**Estado: Parcial**  
**Riesgo residual: Alto**

Evidencia favorable:

- Mensaje genérico ante credenciales inválidas.
- Limitación por IP y hash de cuenta, bloqueo temporal y pruebas del limitador.
- JWT con caducidad, cookie segura/`HttpOnly` y estado OAuth firmado, corto y de un solo uso.
- Selección de perfil valida que el perfil pertenezca a la cuenta.

Brechas:

- `backend/app/core/rate_limit.py:19` almacena límites solo en memoria. El proceso principal observado usa dos trabajadores, así que los intentos se reparten entre memorias distintas y se reinician con el servicio.
- Persiste compatibilidad con credenciales heredadas en el perfil inspeccionado.
- No se evidenció MFA obligatorio para cuentas privilegiadas, revocación central de sesiones, lista de JTI revocados, cierre de todas las sesiones ni política institucional de reautenticación.

Acción recomendada: usar un almacén compartido y atómico para rate limiting, completar migración de claves, habilitar MFA para privilegios altos y definir revocación/rotación de sesiones.

### A08:2025 — Software or Data Integrity Failures

**Estado: Parcial**  
**Riesgo residual: Medio-Alto**

Evidencia favorable:

- Hay hashes SHA-256 en diversos expedientes y respaldos lógicos, validación de JWT y controles CI.
- Se validan extensiones, tipos y tamaños en varios flujos documentales.
- Gitleaks y CodeQL están incorporados al repositorio.

Brechas:

- No se encontró antimalware transversal para archivos cargados, cuarentena ni Content Disarm and Reconstruction.
- La validación MIME/extensión no equivale a validar el contenido real de todos los formatos.
- No se evidenció firma de compilaciones, verificación de artefactos desplegados, SBOM ni protección formal del pipeline por SHA.
- No se revisó la integridad de los paquetes que ya están instalados en el servidor.

Acción recomendada: escaneo antimalware antes de publicación, cuarentena, detección por magic bytes, firmas/procedencia del build y verificación de hash durante el despliegue.

### A09:2025 — Security Logging and Alerting Failures

**Estado: Parcial**  
**Riesgo residual: Medio-Alto**

Evidencia favorable:

- `backend/app/main.py:141` genera/valida `X-Request-ID` y vincula usuario, rol, método, ruta e IP al contexto de auditoría.
- `backend/app/services/db.py` transmite contexto a SQL Server con `sp_set_session_context`.
- Existen pruebas de contexto y auditoría total de base de datos.
- Las excepciones no controladas se registran en servidor con identificador de seguimiento.

Brechas:

- No se encontró SIEM o centralización demostrable, reglas de alerta, responsables de guardia, SLA de atención, protección/retención de logs ni simulacro de incidente.
- El registro de eventos no acredita detección de fuerza bruta distribuida, exfiltración, cambios masivos de permisos o abuso de integraciones.
- No se verificó sincronización horaria, inmutabilidad, control de acceso ni respaldo de las bitácoras.

Acción recomendada: definir catálogo de eventos, niveles y datos prohibidos; centralizar logs; activar alertas accionables; proteger la integridad y retención; probar un caso de respuesta de extremo a extremo.

### A10:2025 — Mishandling of Exceptional Conditions

**Estado: Parcial**  
**Riesgo residual: Alto**

Evidencia favorable:

- `backend/app/main.py:210` captura excepciones no controladas, registra el evento y devuelve un código de seguimiento.
- Los errores 500 se enmascaran cuando `EXPOSE_INTERNAL_ERRORS=false`; en un entorno reconocido como producción se enmascara cualquier 5xx.
- Hay transacciones y `rollback` en numerosos procesos de escritura, además de pruebas funcionales.

Brechas:

- Se encontraron 38 construcciones que introducen `str(exc)` o detalles derivados en respuestas HTTP, sobre todo en Teams, evaluación docente, títulos, Moodle e historial de integración.
- En un proceso no reconocido como producción, los 502/503/504 no quedan necesariamente enmascarados.
- El error ODBC detallado observado en becas demuestra impacto operacional: tecnología, driver, motor, código y preparación SQL llegaron al usuario.
- No se evidenciaron patrones comunes de timeout, circuit breaker, reintento con jitter, idempotencia y compensación para todas las integraciones.

Acción recomendada: usar un catálogo de errores públicos estable, prohibir `str(exc)` en respuestas, conservar detalle solo en logs protegidos, probar fallos parciales y asegurar rollback/idempotencia en cada escritura e integración.

### 5.1 Resumen OWASP

| Riesgo | Estado | Prioridad |
| --- | --- | --- |
| A01 Control de acceso roto | Parcial | Media |
| A02 Configuración incorrecta | Parcial | Alta |
| A03 Cadena de suministro | Parcial | Media |
| A04 Fallos criptográficos | Parcial | Alta |
| A05 Inyección | Parcial | Media |
| A06 Diseño inseguro | Parcial | Media-Alta |
| A07 Fallos de autenticación | Parcial | Alta |
| A08 Integridad de software/datos | Parcial | Media-Alta |
| A09 Registro y alertas | Parcial | Media-Alta |
| A10 Condiciones excepcionales | Parcial | Alta |

## 6. Evaluación ISO punto por punto

### 6.1 ISO/IEC 27001:2022 — Sistema de Gestión de Seguridad de la Información

**Estado global: No evidenciado como SGSI; controles técnicos parciales**

| Componente de gestión | Estado | Evidencia o brecha |
| --- | --- | --- |
| Contexto, alcance y partes interesadas | No evidenciado | No se encontró alcance formal del SGSI, dependencias críticas, partes interesadas ni exclusiones justificadas. |
| Liderazgo, política y responsabilidades | No evidenciado | `SECURITY.md` contiene reglas técnicas, pero no sustituye política institucional aprobada, roles, autoridad y rendición de cuentas. |
| Planificación y tratamiento de riesgos | No evidenciado | No se encontró metodología, registro de riesgos, propietarios, criterios, aceptación ni Declaración de Aplicabilidad. |
| Soporte y competencia | No evidenciado | No hay evidencia de formación, competencia, concienciación ni control formal de documentos. |
| Operación | Parcial | Existen CI, pruebas, controles de producción y guías de despliegue para algunos módulos; falta evidencia uniforme de operación controlada. |
| Evaluación del desempeño | No evidenciado | No se encontraron KPI/KRI, programa de auditoría interna, revisión de dirección ni evaluación periódica del SGSI. |
| Mejora | Parcial | El historial Git muestra correcciones continuas, pero no existe proceso formal de no conformidad, causa raíz y acción correctiva. |

Conclusión 27001: el repositorio aporta controles tecnológicos útiles, pero no permite sostener conformidad con el sistema de gestión. Para certificar se requiere evidencia organizacional, alcance, evaluación de riesgos, Declaración de Aplicabilidad y ciclo de auditoría/mejora.

### 6.2 ISO/IEC 27002:2022 — Controles de seguridad

**Estado global: Parcial**

| Dominio aplicable | Estado | Evaluación |
| --- | --- | --- |
| Inventario, clasificación y uso aceptable de información | No evidenciado | No se encontró inventario/clasificación de datos académicos, financieros, identidad, salud/bienestar o documentos. |
| Identidad, autenticación y derechos de acceso | Parcial | RBAC, pantallas, sesión y pruebas presentes; faltan recertificación, segregación formal, MFA y evidencia de bajas oportunas. |
| Relaciones con proveedores y nube | Parcial | Integraciones Microsoft/Moodle usan TLS configurable; faltan evaluación de proveedor, responsabilidades, SLA, salida y seguimiento. |
| Gestión de incidentes | No evidenciado | Hay logs, pero no plan, clasificación, escalamiento, contactos, preservación de evidencia ni lecciones aprendidas demostrables. |
| Continuidad, respaldo y recuperación | Parcial | Hay respaldo/rollback documentado para Titulación; no se acreditó cobertura, RPO/RTO y restauración probada de todo el sistema. |
| Cumplimiento legal, registros y privacidad | No evidenciado | No se encontró matriz legal, retención, eliminación, consentimiento/base jurídica, solicitudes del titular o revisión periódica. |
| Protección contra malware | No cumple en cargas | No se encontró escaneo antimalware transversal para adjuntos. |
| Gestión de vulnerabilidades | Parcial | Dependabot, npm audit, pip-audit en CI y CodeQL; faltan SLA, inventario desplegado, DAST/pentest y evidencia del último cierre. |
| Configuración segura | Parcial | Guardas de producción y HSTS presentes; TLS legado y cabeceras estáticas incompletas. |
| Copias, redundancia y capacidad | Parcial | Algunos mecanismos documentados; no hay evidencia transversal ni pruebas periódicas de recuperación/capacidad. |
| Registro, monitoreo y sincronización | Parcial | Buena correlación técnica; faltan centralización, alertas, retención e inmutabilidad comprobadas. |
| Redes y criptografía | Parcial | HTTPS/certificado válidos y controles TLS de aplicación; TLS 1.0/1.1 y transporte SQL efectivo sin acreditar. |
| Desarrollo seguro y pruebas de seguridad | Parcial | Pruebas, CI, revisión de rutas y configuración segura; faltan threat modeling, ASVS, DAST, pentest y criterios de aceptación. |
| Datos de prueba, separación de ambientes y cambios | Parcial | CI usa valores sintéticos; no se acreditó segregación completa, anonimización, aprobación del cambio ni evidencia de rollback global. |

### 6.3 ISO/IEC 27005:2022 — Gestión de riesgos

**Estado global: No evidenciado**

| Etapa | Estado | Evaluación |
| --- | --- | --- |
| Establecer contexto y criterios | No evidenciado | No hay escalas institucionales de impacto/probabilidad ni apetito de riesgo. |
| Identificar riesgos | Parcial | `docs/SEGURIDAD_OWASP.md` enumera brechas técnicas, pero no constituye un registro completo de activos, amenazas y consecuencias. |
| Analizar y evaluar | No evidenciado | No se encontraron valoración inherente/residual, propietarios ni fecha de revisión. |
| Tratar el riesgo | Parcial | Existen recomendaciones y controles implementados, sin plan formal con responsable, plazo, costo y riesgo residual aceptado. |
| Comunicar y consultar | No evidenciado | No hay evidencia de comité, aprobación del negocio ni comunicación a partes interesadas. |
| Monitorear y revisar | Parcial | Dependabot y CI son monitoreo técnico; falta revisión periódica integral y seguimiento de riesgo. |

### 6.4 ISO/IEC 27034-1:2011 — Seguridad de aplicaciones

**Estado global: Parcial**

| Elemento | Estado | Evaluación |
| --- | --- | --- |
| Marco organizacional de seguridad de aplicaciones | No evidenciado | No se encontró un marco institucional aprobado que asigne gobierno, roles, riesgo y controles por aplicación. |
| Proceso de gestión de seguridad de la aplicación | Parcial | Hay controles técnicos y CI, pero no un proceso formal desde requisitos hasta retiro. |
| Contexto y nivel objetivo de confianza | No evidenciado | No se clasificó formalmente la aplicación ni se definió un nivel objetivo verificable. |
| Controles de seguridad de aplicación | Parcial | Autenticación, autorización, validación, trazabilidad y configuración segura están implementadas de forma relevante. |
| Verificación y aceptación | Parcial | Pruebas automatizadas amplias; faltan ASVS trazable, DAST, pentest y aprobación de riesgo previa a producción. |
| Operación y mejora | Parcial | Hay documentación de endurecimiento y cambios frecuentes; faltan métricas, incidentes, retroalimentación y reevaluación formal. |

### 6.5 ISO/IEC/IEEE 12207:2026 — Ciclo de vida del software

**Estado global: Parcial**

| Proceso de ciclo de vida | Estado | Evaluación |
| --- | --- | --- |
| Adquisición y suministro | No evidenciado | No se revisaron contratos, criterios de aceptación de proveedores o licencias. |
| Necesidades y requisitos de partes interesadas | Parcial | Existe documentación funcional extensa, pero no trazabilidad completa requisito-cambio-prueba-aceptación. |
| Arquitectura y diseño | Parcial | La arquitectura se deduce del código y documentos; faltan decisiones arquitectónicas formales y análisis de amenazas. |
| Implementación e integración | Parcial | Git, módulos separados, compilación y pruebas demuestran un proceso activo; faltan revisiones/aprobaciones uniformes. |
| Verificación y validación | Parcial | 543 pruebas y 216 subpruebas aprobadas; falta cobertura medida, pruebas E2E, rendimiento, seguridad dinámica y aceptación del usuario. |
| Transición y despliegue | Parcial | Hay IIS operativo y guías para algunos módulos; no existe evidencia uniforme de versionado de artefactos, aprobación, smoke test y rollback. |
| Operación y mantenimiento | Parcial | El sistema está monitorizado operativamente de forma básica y recibe correcciones; falta SLO/SLA, observabilidad central y gestión formal de incidentes/problemas. |
| Retiro y disposición | No evidenciado | No se encontró plan de retiro, migración, conservación o eliminación segura de datos y componentes. |
| Gestión de configuración y cambios | Parcial | Git y CI presentes; mensajes genéricos y despliegues posteriores a `git pull` no acreditan revisión, segregación, etiquetado y aprobación formal. |
| Medición y mejora de procesos | No evidenciado | No se encontraron métricas de entrega, defectos, seguridad, disponibilidad o mejora de procesos. |

### 6.6 ISO/IEC 25010:2023 — Calidad del producto

**Estado global: Parcial**

| Característica de calidad | Estado | Evaluación |
| --- | --- | --- |
| Adecuación funcional | Parcial | Amplia cobertura funcional y pruebas por módulos; no hay matriz completa requisito-prueba-aceptación. |
| Eficiencia de desempeño | No evidenciado | No se encontraron objetivos, pruebas de carga, percentiles de latencia, capacidad o perfiles de consumo. |
| Compatibilidad | Parcial | Integraciones y formatos están implementados; faltan matrices de versiones, navegadores y pruebas contractuales. |
| Capacidad de interacción | Parcial | Hay trabajo responsive y flujos por perfil; no se evidenció investigación de usuarios ni evaluación sistemática de usabilidad. |
| Fiabilidad | Parcial | Manejo de errores y transacciones presentes; faltan SLO, pruebas de resiliencia, recuperación y fallos de dependencias. |
| Seguridad | Parcial | Controles relevantes, con las brechas OWASP descritas en este informe. |
| Mantenibilidad | Parcial | Separación modular, pruebas y CI; algunos routers son muy extensos, lo que eleva complejidad y costo de revisión. |
| Flexibilidad | Parcial | Configuración por entorno e integraciones desacopladas parcialmente; no hay métricas de modificabilidad/adaptabilidad. |
| Protección frente a riesgos (safety) | No evidenciado | Deben documentarse consecuencias de errores de matrícula, notas, becas, pagos y cambios académicos, y sus controles de reversión. |

### 6.7 ISO/IEC 27701:2025 — Gestión de privacidad

**Estado global: No evidenciado como PIMS; controles técnicos parciales**

| Elemento de privacidad | Estado | Evaluación |
| --- | --- | --- |
| Alcance y roles de responsable/encargado | No evidenciado | No se encontró alcance PIMS ni distribución de responsabilidades con terceros. |
| Inventario de PII y finalidades | No evidenciado | El sistema trata identidad, contacto, matrícula, notas, documentos y posiblemente información financiera/bienestar, sin inventario formal encontrado. |
| Base jurídica, transparencia y consentimiento | No evidenciado | No se revisaron avisos, bases legales, consentimientos o registro de preferencias. |
| Minimización, exactitud y limitación de uso | Parcial | Hay controles funcionales, pero no una matriz de necesidad por campo/finalidad. |
| Retención, eliminación y anonimización | No evidenciado | No se encontró calendario de retención ni eliminación segura por categoría. |
| Derechos del titular | No evidenciado | No se evidenciaron procedimientos para acceso, rectificación, oposición, portabilidad o eliminación cuando aplique. |
| Privacidad desde el diseño y evaluación de impacto | No evidenciado | No se encontró DPIA/EIPD ni checklist de privacidad en cambios. |
| Seguridad y trazabilidad | Parcial | RBAC, sesión, auditoría y TLS aportan protección; persisten brechas de transporte, errores y monitoreo. |
| Terceros y transferencias | No evidenciado | Microsoft 365/Graph, Moodle y correo requieren registro de transferencias, contratos, ubicación y garantías. |
| Incidentes de datos personales | No evidenciado | No se encontró procedimiento, plazo, responsable, evaluación de impacto o plantillas de notificación. |

## 7. Registro priorizado de hallazgos

| ID | Prioridad | Hallazgo | Impacto principal | Recomendación verificable |
| --- | --- | --- | --- | --- |
| H-01 | Alta | TLS 1.0 y 1.1 aceptados públicamente | Downgrade y uso de protocolos criptográficos obsoletos | Aceptar solo TLS 1.2/1.3 y repetir prueba externa. |
| H-02 | Alta | Configuración efectiva de producción no atestiguada; el perfil de revisión cargó valores de desarrollo | Las guardas seguras pueden no activarse si el entorno está mal rotulado | Inventariar variables efectivas por proceso, validar arranque y guardar evidencia sin secretos. |
| H-03 | Alta | 38 respuestas potenciales con detalle de excepción | Divulgación de SQL, rutas, proveedores y datos internos | Sustituir por códigos públicos y comprobar que ningún 4xx/5xx expone excepciones. |
| H-04 | Alta | Rate limiting en memoria con múltiples trabajadores | Evasión parcial del bloqueo, pérdida de estado al reiniciar | Usar almacén compartido y probar concurrencia/múltiples nodos. |
| H-05 | Alta | Cargas grandes sin antimalware transversal | Malware, almacenamiento abusivo y agotamiento de recursos | Cuotas por flujo/usuario, streaming, proxy limits, cuarentena y antimalware. |
| H-06 | Media | Cabeceras defensivas incompletas en archivos estáticos | Mayor superficie de XSS/clickjacking/MIME y aislamiento débil | Aplicar CSP y cabeceras coherentes en IIS, con pruebas de regresión. |
| H-07 | Media | Cadena de suministro sin SHA, SBOM, firma ni procedencia | Compromiso de pipeline/artefacto difícil de detectar | Fijar Actions por SHA, generar SBOM y firmar/verificar builds. |
| H-08 | Media | Sin DAST/pentest autenticado demostrado | Riesgos de lógica, IDOR e inyección no detectados por unit tests | Ejecutar DAST y pentest con cierre formal de hallazgos. |
| H-09 | Media | Logs sin centralización/alertas y gobernanza demostrable | Detección tardía y evidencia insuficiente | SIEM, reglas, SLA, retención, acceso e incident drill. |
| H-10 | Baja | Identificación de IIS/ARR en respuestas | Facilita reconocimiento tecnológico | Suprimir encabezados cuando no sean necesarios. |

## 8. Plan recomendado de cumplimiento

Las acciones siguientes son una propuesta; **no fueron ejecutadas**.

### Fase 1 — Contención y evidencia, 0 a 15 días

1. Deshabilitar TLS 1.0/1.1, mantener TLS 1.2/1.3 y verificar desde fuera de la red.
2. Crear una evidencia firmada de configuración efectiva por sitio/proceso sin incluir secretos.
3. Eliminar exposición pública de excepciones en todos los códigos HTTP.
4. Confirmar resultado del último `pip-audit`, CodeQL y Gitleaks; resolver cualquier alerta abierta.
5. Definir responsables y fechas para cada hallazgo de prioridad alta.

Criterio de cierre: pruebas externas de protocolo, matriz de configuración aprobada, prueba automática de errores sin detalle y CI de seguridad verde.

### Fase 2 — Endurecimiento, 15 a 45 días

1. Migrar todas las contraseñas a Argon2 y desactivar el modo legado.
2. Implementar limitación distribuida, MFA privilegiado y revocación de sesión.
3. Aplicar cabeceras de seguridad al frontend y ocultar firmas del servidor.
4. Implantar cuotas, streaming, antimalware y cuarentena para adjuntos.
5. Crear SBOM, firma/procedencia del build y fijación SHA del pipeline.

Criterio de cierre: pruebas negativas automatizadas, escaneo de adjuntos, artefacto verificable y control distribuido demostrado con dos trabajadores.

### Fase 3 — Verificación independiente, 45 a 90 días

1. Adoptar OWASP ASVS 5.0 L2 y trazar requisito, evidencia y resultado.
2. Ejecutar threat modeling, DAST y pentest autenticado; corregir y repetir pruebas.
3. Definir SLO, pruebas de carga, capacidad, resiliencia, backup y restauración.
4. Centralizar monitoreo y ejecutar un simulacro de incidente.

Criterio de cierre: informe independiente sin hallazgos altos abiertos, ASVS trazable y restauración/simulacro satisfactorios.

### Fase 4 — Gobierno ISO, 60 a 180 días

1. Definir alcance SGSI/PIMS, propietarios, activos, clasificación y partes interesadas.
2. Aprobar metodología y registro de riesgos, plan de tratamiento y Declaración de Aplicabilidad.
3. Documentar privacidad: finalidades, base jurídica, minimización, retención, derechos, terceros y DPIA/EIPD.
4. Formalizar cambios, segregación, aceptación, métricas, auditoría interna y revisión de dirección.
5. Solicitar auditoría de preparación y después, si la institución lo decide, auditoría de certificación.

Criterio de cierre: paquete documental aprobado, evidencias operativas de al menos un ciclo, auditoría interna y revisión de dirección completadas.

## 9. Evidencia técnica revisada

| Evidencia | Resultado |
| --- | --- |
| Estado Git | Rama `main`, commit `1a6b86b`; limpio antes de generar este informe. |
| Backend tests | 543 aprobadas, 216 subpruebas aprobadas, 1 advertencia de deprecación. |
| npm audit | 0 vulnerabilidades con nivel alto y dependencias de producción. |
| pip-audit local | No ejecutable: módulo ausente; control configurado en CI. |
| Dependencias | 28/28 paquetes Python fijados exactamente; lockfile npm v3 versionado. |
| CI de seguridad | Pruebas y auditorías semanales, Dependabot, CodeQL y Gitleaks. |
| Autenticación | Argon2, JWT validado, cookie `HttpOnly`, rate limiting, OAuth state de un solo uso. |
| Autorización | Dependencias de sesión/rol/pantalla y prueba automática de cobertura de rutas privadas. |
| Cabeceras API públicas | CSP, DENY, nosniff, referrer, permissions, COOP/CORP, no-store, HSTS. |
| Cabeceras frontend públicas | HSTS y no-store; faltan las demás cabeceras defensivas observadas en la API. |
| TLS público | TLS 1.0, 1.1, 1.2 y 1.3 aceptados. |
| Certificado público | Let's Encrypt; CN correcto; vigencia 2026-08-05 a 2026-11-03. |
| Manejo de errores | Middleware genérico presente; 38 puntos potenciales con detalles de excepción. |
| Secretos versionados | No se observaron archivos `.env` reales, llaves o certificados privados rastreados por Git. |
| Gobierno formal | No se encontró evidencia suficiente de SGSI, PIMS, riesgo, SoA, auditoría o revisión directiva. |

## 10. Conclusión

El Sistema Académico INTEC presenta un **nivel técnico intermedio de seguridad** y controles superiores a una aplicación sin endurecimiento: pruebas amplias, autenticación/autorización backend, cabeceras API, trazabilidad, configuración defensiva y controles de cadena de suministro.

El resultado de cumplimiento es **parcial**. No corresponde declarar “cumple ISO”, “certificado”, “seguro” ni “libre de vulnerabilidades” hasta cerrar los hallazgos altos, demostrar la configuración efectiva, realizar verificación dinámica independiente y establecer el sistema de gestión organizacional que exigen las normas ISO.

La prioridad inmediata es cerrar H-01 a H-05. En paralelo, la institución debe transformar los controles técnicos existentes en evidencia gestionada: alcance, propietarios, riesgos, decisiones, métricas, revisiones y mejora continua.

## 11. Referencias oficiales

- [OWASP Top 10:2025](https://owasp.org/Top10/)
- [OWASP Top 10:2025 — introducción](https://owasp.org/Top10/2025/0x00_2025-Introduction/)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)
- [ISO/IEC 27002:2022](https://www.iso.org/standard/75652.html)
- [ISO/IEC 27005:2022](https://www.iso.org/standard/80585.html)
- [ISO/IEC 27034-1:2011](https://www.iso.org/standard/44378.html)
- [ISO/IEC/IEEE 12207:2026](https://www.iso.org/cms/%20render/live/en/sites/isoorg/contents/data/standard/09/02/90219.html)
- [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html)
- [ISO/IEC 27701:2025](https://www.iso.org/standard/27701)
