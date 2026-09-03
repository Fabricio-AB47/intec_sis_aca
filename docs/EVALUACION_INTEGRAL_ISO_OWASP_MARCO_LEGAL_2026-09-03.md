# Evaluación integral del Sistema Académico INTEC

## ISO, OWASP Top 10, marco legal ecuatoriano, mejoras y puntuación

**Fecha:** 3 de septiembre de 2026  
**Versión:** rama `main`, commit `1a6b86b`  
**Calificación:** **5,1/10**  
**Dictamen:** cumplimiento parcial con riesgos altos pendientes.

> Esta es una evaluación técnica de brechas, no una certificación ISO, opinión jurídica ni prueba de penetración. La aplicabilidad legal definitiva debe confirmarse con el delegado de protección de datos y la asesoría jurídica institucional.

## 1. Resumen ejecutivo

El proyecto tiene una base técnica relevante: autenticación y autorización en backend, permisos por rol y pantalla, Argon2, JWT validado, cookies protegidas, CSRF, cabeceras defensivas en la API, trazabilidad, auditoría SQL, integración continua y pruebas amplias.

El nuevo análisis confirmó:

- 378 endpoints, 59 archivos Python, 76 archivos TypeScript/TSX y 34 archivos de prueba.
- 543 pruebas y 216 subpruebas aprobadas; una advertencia de deprecación.
- Build frontend correcto; 126 accesos y 57 vistas raíz verificados.
- Dependencias npm de producción sin vulnerabilidades.
- Tres avisos recientes para `pypdf 6.15.0`.
- Una vulnerabilidad alta en `browserslist 4.28.4` y una moderada en `@humanfs/node 0.16.7`, ambas de la cadena de desarrollo.
- TLS 1.0, 1.1, 1.2 y 1.3 aceptados por el sitio público.

Los mayores vacíos están en protocolos TLS heredados, dependencias, manejo de errores, archivos, limitación distribuida, monitoreo, privacidad y gobierno ISO.

## 2. Alcance y limitaciones

Se revisaron FastAPI/Python, React/TypeScript, IIS, SQL, autenticación, permisos, sesiones, cargas, documentos, integraciones Microsoft/Moodle, dependencias, CI, pruebas, documentación y HTTPS público.

No se ejecutaron explotación, DAST, pentest, lectura de secretos, acceso a expedientes reales ni modificaciones de código, IIS o bases de datos. Tampoco se revisaron contratos, actas, políticas o evidencias institucionales que no están en el repositorio.

Estados utilizados:

| Estado | Significado |
| --- | --- |
| Cumple | Evidencia suficiente, sin brecha material observada. |
| Parcial | Control presente, pero incompleto o no acreditado. |
| No cumple | Condición comprobada incompatible. |
| No evidenciado | No se encontró soporte verificable. |
| Condicional | Depende de la institución o tratamiento. |

## 3. Puntuación sobre 10

| Dimensión | Peso | Nota | Aporte |
| --- | ---: | ---: | ---: |
| OWASP y aplicación | 30 % | 5,5 | 1,65 |
| Ingeniería y calidad | 15 % | 7,5 | 1,13 |
| Infraestructura y criptografía | 15 % | 5,0 | 0,75 |
| Cadena de suministro | 10 % | 4,0 | 0,40 |
| Operación y resiliencia | 10 % | 4,5 | 0,45 |
| Gobierno ISO | 10 % | 3,5 | 0,35 |
| Legal y privacidad | 10 % | 3,5 | 0,35 |
| **Total** | **100 %** |  | **5,08 ≈ 5,1** |

La nota preliminar de 5,8 se ajusta a **5,1** porque esta revisión amplió el alcance legal y detectó avisos de dependencias publicados recientemente. No representa deterioro funcional; representa evidencia adicional.

## 4. Datos y procesos regulados

El sistema gestiona identidad, contacto, matrícula, notas, asistencia, evaluación, becas, pagos, facturas, prácticas, titulación, expedientes, contratos, certificados, imágenes y videos. También aparecen datos de discapacidad, etnia y salud/bienestar, que necesitan especial protección.

Los flujos alcanzan SQL Server, Microsoft 365/Graph/Teams/OneDrive, Moodle, SMTP y SENESCYT. Esta amplitud exige inventario de datos, Registro de Actividades de Tratamiento, clasificación, retención y mapa de transferencias.

## 5. Hallazgos priorizados

| ID | Prioridad | Hallazgo | Riesgo |
| --- | --- | --- | --- |
| F-01 | Alta | TLS 1.0/1.1 habilitados | Criptografía heredada y downgrade. |
| F-02 | Alta | Tres avisos para `pypdf 6.15.0` | PDF manipulado puede agotar recursos o provocar un bucle. |
| F-03 | Alta | `browserslist 4.28.4` vulnerable | Consumo de memoria o caída en herramientas de build. |
| F-04 | Alta | 38 respuestas potenciales con excepciones | Divulgación de SQL, rutas o proveedores. |
| F-05 | Alta | Rate limiting local con varios trabajadores | Evasión parcial del bloqueo. |
| F-06 | Alta | Cargas grandes sin antimalware transversal | Malware y denegación de servicio. |
| F-07 | Alta | Gobierno de privacidad no evidenciado | Riesgo LOPDP e ISO 27701. |
| F-08 | Alta | Configuración productiva no atestiguada | Guardas seguras pueden no activarse. |
| F-09 | Media | Cabeceras incompletas en frontend | Defensa web desigual. |
| F-10 | Media | Sin SIEM, alertas e incidentes demostrados | Detección y notificación tardías. |
| F-11 | Media | Pipeline sin SHA, SBOM o firma | Procedencia del artefacto no demostrable. |
| F-12 | Media | Sin ASVS, DAST o pentest | Riesgos lógicos e IDOR no comprobados. |
| F-13 | Media | Continuidad integral no demostrada | Recuperación y RPO/RTO desconocidos. |
| F-14 | Media | Accesibilidad sin prueba formal | Barreras de uso y riesgo legal. |
| F-15 | Baja | Firmas IIS/ARR visibles | Reconocimiento tecnológico. |

## 6. OWASP Top 10:2025

### A01 — Broken Access Control: 7,0/10, parcial

Hay sesión obligatoria, permisos backend por roles/pantallas y pruebas de alcance. Faltan matriz de segregación, autorización objeto por objeto y pentest IDOR/BOLA. Se recomienda RBAC/ABAC aprobado, pruebas negativas por operación y recertificación trimestral.

### A02 — Security Misconfiguration: 5,0/10, parcial

La API tiene cabeceras sólidas y existen guardas de producción. Persisten TLS 1.0/1.1, cabeceras incompletas en estáticos, firmas IIS/ARR y configuración efectiva no atestiguada. Se requiere línea base IIS, TLS 1.2/1.3 únicamente y verificación automatizada.

### A03 — Software Supply Chain Failures: 4,0/10, parcial alto

Hay versiones fijadas, lockfile, Dependabot, CodeQL y Gitleaks. Sin embargo:

- `pypdf 6.15.0` está afectado por GHSA-23w6-3w8w-8484, GHSA-763m-79hh-57f2 y GHSA-jp53-mhqp-8xcg; 6.16.1 es la versión corregida común. El riesgo es aplicable porque `certificate_renamer.py` procesa PDF recibidos y ejecuta extracción de texto; el límite específico de 12 MB reduce, pero no elimina, el riesgo de agotamiento.
- `browserslist 4.28.4` tiene alerta alta.
- `@humanfs/node 0.16.7` tiene alerta moderada.
- Faltan Actions fijadas por SHA, SBOM, firma, procedencia e inventario de licencias.

Se recomienda actualizar mediante PR probado, probar PDF hostiles, exigir auditorías verdes, generar SBOM y firmar el build.

### A04 — Cryptographic Failures: 5,0/10, parcial alto

Hay Argon2, JWT completo, cookies seguras, HTTPS/HSTS y certificado válido hasta el 3 de noviembre de 2026. Reducen la nota TLS heredado, compatibilidad con claves legadas, transporte SQL no atestiguado y ausencia de gestión formal de secretos/certificados.

### A05 — Injection: 6,5/10, parcial

Existe validación Pydantic/FastAPI y uso amplio de parámetros `?`. En 1.052 llamadas SQL no apareció el patrón directo `execute(f"...")` en la misma línea. Esto no descarta fragmentos dinámicos: faltan revisión de flujo y DAST de SQLi, XSS, XML y comandos.

### A06 — Insecure Design: 5,5/10, parcial

Las reglas de negocio, transacciones y autorizaciones backend son favorables. Faltan modelo de amenazas, casos de abuso, clasificación formal, límites de confianza e idempotencia transversal. Se recomiendan DFD, STRIDE y criterios no funcionales por proceso crítico.

### A07 — Authentication Failures: 6,0/10, parcial

Hay mensajes genéricos, límites por IP/cuenta, JWT/cookie y estado OAuth de un solo uso. El limitador no es compartido, persiste el modo legado y no se evidenció MFA o revocación central. Se recomienda almacén atómico, MFA privilegiado y gestión central de sesiones.

### A08 — Software or Data Integrity Failures: 5,0/10, parcial

Hay hashes, validaciones de archivos, JWT y controles CI. Faltan antimalware, cuarentena, verificación real uniforme de contenido, SBOM y firma de artefactos.

### A09 — Security Logging and Alerting Failures: 4,5/10, parcial

Se registra `request_id`, usuario, rol, IP, método, ruta y contexto SQL. No se evidenciaron SIEM, reglas, retención, inmutabilidad, guardia o procedimiento LOPDP de vulneración. Deben centralizarse logs, definirse alertas/SLA y realizar simulacros.

### A10 — Mishandling of Exceptional Conditions: 5,5/10, parcial alto

Existe middleware global y rollback frecuente. Se encontraron 38 puntos con detalles derivados de excepciones; fuera de producción reconocida, algunos 502/503/504 pueden filtrar información. Debe usarse un catálogo de errores públicos y una regla CI contra `str(exc)` en respuestas.

## 7. Evaluación ISO

### ISO/IEC 27001:2022 — 3,5/10

**Estado:** SGSI no evidenciado; controles técnicos parciales.

- Contexto y alcance: no evidenciados.
- Política, liderazgo y responsabilidades: no evidenciados formalmente.
- Método, registro, propietarios y aceptación de riesgos: no evidenciados.
- Declaración de Aplicabilidad: no evidenciada.
- Operación: parcial mediante CI, pruebas y algunas guías.
- Métricas, auditoría interna y revisión directiva: no evidenciadas.
- Mejora: cambios frecuentes, sin proceso formal de causa raíz y cierre.

### ISO/IEC 27002:2022 — 5,0/10

| Área | Estado |
| --- | --- |
| Inventario y clasificación | No evidenciado |
| Identidad y acceso | Parcial |
| Proveedores y nube | Parcial |
| Incidentes | No evidenciado |
| Continuidad y respaldo | Parcial |
| Cumplimiento y privacidad | No evidenciado |
| Protección contra malware | No cumple |
| Vulnerabilidades | Parcial, con alertas abiertas |
| Configuración segura | Parcial |
| Logging y monitoreo | Parcial |
| Red y criptografía | Parcial |
| Desarrollo seguro | Parcial |
| Separación de ambientes/cambio | Parcial |

### ISO/IEC 27005:2022 — 3,0/10

No se evidenciaron contexto, apetito, criterios, registro, propietarios ni riesgo residual aceptado. Los documentos OWASP identifican riesgos técnicos, pero no reemplazan el proceso institucional. Se requiere metodología, evaluación, tratamiento, comunicación y seguimiento periódico.

### ISO/IEC 27034-1:2011 — 5,0/10

Los controles de aplicación son relevantes, pero no existe un marco institucional de seguridad de aplicaciones, nivel objetivo de confianza, proceso formal desde requisitos hasta retiro ni aceptación de riesgo. Las pruebas automatizadas deben complementarse con ASVS, DAST y pentest.

### ISO/IEC/IEEE 12207:2026 — 6,0/10

| Proceso | Estado |
| --- | --- |
| Requisitos | Parcial; documentación amplia, trazabilidad incompleta |
| Arquitectura | Parcial; decisiones y amenazas no formalizadas |
| Implementación | Parcial-alto; Git, módulos, build y pruebas |
| Verificación | Parcial-alto; faltan cobertura, E2E, carga y seguridad dinámica |
| Despliegue | Parcial; falta artefacto firmado y rollback transversal |
| Operación | Parcial; faltan SLO e incidentes/problemas formales |
| Retiro | No evidenciado |
| Cambio/configuración | Parcial |
| Medición/mejora | No evidenciado |

### ISO/IEC 25010:2023 — 6,0/10

| Característica | Nota |
| --- | ---: |
| Adecuación funcional | 8,0 |
| Eficiencia de desempeño | 4,0 |
| Compatibilidad | 6,0 |
| Capacidad de interacción | 6,0 |
| Fiabilidad | 5,0 |
| Seguridad | 5,1 |
| Mantenibilidad | 6,0 |
| Flexibilidad | 6,0 |
| Protección frente a riesgos | 4,5 |

### ISO/IEC 27701:2025 — 3,0/10

No se evidenció un PIMS. Faltan alcance, responsables, inventario de PII, finalidades, bases, transparencia, retención, derechos, privacidad desde diseño, EIPD, transferencias e incidentes. RBAC, auditoría y TLS aportan controles técnicos, pero no demuestran responsabilidad legal.

### Normas complementarias recomendadas

- ISO 22301 para continuidad, BIA y RTO/RPO.
- ISO/IEC 20000-1 para servicios, incidentes, problemas y cambios.
- ISO 9001 para gestión de calidad.
- ISO/IEC 29100 para arquitectura de privacidad.
- ISO/IEC 27017 y 27018 para nube y PII en nube, cuando apliquen.

## 8. Marco legal ecuatoriano

### Resultado general: 3,5/10, cumplimiento no demostrable

El software seguro es solo una parte del cumplimiento. También se necesitan finalidades, base jurídica, transparencia, derechos, retención, contratos, transferencias, incidentes y responsabilidad demostrable.

### Constitución del Ecuador

Los artículos 66.19 y 92 protegen los datos personales y el hábeas data. **Estado: parcial.** Existen funciones de consulta/actualización, pero no un proceso integral y trazable que alcance bases, copias, documentos y terceros.

### Ley Orgánica de Protección de Datos Personales

| Obligación | Referencia | Estado |
| --- | --- | --- |
| Principios de tratamiento | Art. 10 | No evidenciado |
| Información al titular | Art. 12 | No evidenciado |
| Acceso | Art. 13 | No evidenciado |
| Rectificación/actualización | Arts. 14 y relacionados | Parcial |
| Eliminación | Art. 15 | No evidenciado |
| Oposición y otros derechos | Arts. 16–22 | No evidenciado |
| Acceso/transferencia a terceros | Arts. 33–36 | Parcial |
| Seguridad | Art. 37 | Parcial |
| Sector público, si aplica | Art. 38 | Condicional |
| Privacidad desde diseño/defecto | Art. 39 | No evidenciado |
| Riesgos y vulnerabilidades | Art. 40 | No evidenciado |
| Medidas según riesgo | Art. 41 | Parcial |
| Evaluación de impacto | Art. 42 | No evidenciado |
| Notificación de vulneración | Arts. 43 y 46 | No evidenciado |
| Obligaciones responsable/encargado | Art. 47 | Parcial |
| Delegado de protección | Arts. 48–50 | No evidenciado |
| Registro aplicable | Art. 51 y regulación | No evidenciado |
| Transferencias internacionales | Arts. 55–61 | No evidenciado |

Las medidas necesarias son: ROPA, avisos, matriz de bases y finalidades, procedimiento de derechos, retención/bloqueo/eliminación, EIPD, gestión de brechas, DPO cuando corresponda y contratos/transferencias documentados.

### Regulación de la SPDP

El índice oficial consultado incluye reglas de 2025 y 2026 sobre riesgos/EIPD, cláusulas contractuales, delegado, anonimización/bloqueo/eliminación, interés legítimo, transferencias, tratamiento a gran escala e IA. **Estado: no evidenciado.** Debe evaluarse especialmente si el ecosistema académico constituye tratamiento a gran escala.

### LOES y Reglamento de Régimen Académico

**Estado: parcial y pendiente de validar contra las últimas reformas.** El sistema cubre matrícula, notas, prácticas, titulación y expedientes. Deben mapearse exactitud, custodia, rectificación autorizada, conservación, reportes CES/SENESCYT, acceso del estudiante y debido proceso.

### Comercio electrónico y firma

**Aplicación condicional.** Para contratos, certificados, actas o notificaciones electrónicas se deben definir firma requerida, integridad, sello de tiempo, no repudio, conservación y evidencia de recepción.

### Transparencia

**Aplicación condicional.** Si la institución entra en el ámbito de LOTAIP, debe separar información pública, datos personales/confidenciales e información académica reservada, generando versiones anonimizadas cuando corresponda.

### Accesibilidad y no discriminación

**Estado técnico: parcial.** Se contabilizaron 385 usos ARIA y seis imágenes con seis atributos `alt`, pero no se encontró axe, pa11y o Lighthouse en CI. Se recomienda WCAG 2.1 AA, automatización y evaluación manual con teclado, lector, zoom y contraste.

## 9. Plan de mejoras

### 0–7 días

1. Actualizar `pypdf` a una versión corregida común igual o superior a 6.16.1 y probar PDF hostiles.
2. Actualizar `browserslist` y `@humanfs/node` mediante lockfile controlado.
3. Deshabilitar TLS 1.0/1.1 y comprobar externamente TLS 1.2/1.3.
4. Atestiguar la configuración efectiva de todos los trabajadores sin revelar secretos.
5. Enmascarar excepciones en todos los códigos HTTP.
6. Asignar propietario y fecha a cada hallazgo alto.

### 8–30 días

1. Rate limiting compartido y atómico.
2. MFA privilegiado y revocación central de sesiones.
3. Antimalware, cuarentena, magic bytes y límites de archivo por flujo.
4. Límites coherentes en IIS, proxy y API, incluso para cargas fragmentadas.
5. Cabeceras uniformes en frontend/API y reducción de firmas del servidor.
6. SIEM, alertas, SLA y runbooks.
7. Migración completa a Argon2 y desactivación del modo legado.

### 31–60 días

1. OWASP ASVS 5.0 nivel 2 trazable.
2. Modelo de amenazas para autenticación, matrícula, notas, becas, pagos y expedientes.
3. DAST y pentest autenticado con corrección y nueva prueba.
4. SBOM, Actions por SHA, firma y procedencia del build.
5. Pruebas de carga, resiliencia, recuperación y accesibilidad.

### 0–90 días: legal y privacidad

1. Designar responsables jurídicos y de privacidad.
2. Crear ROPA con finalidad, base, titulares, datos, sistemas, terceros, país, retención y seguridad.
3. Publicar avisos de privacidad por punto de captura.
4. Implementar derechos con identidad, plazos y propagación.
5. Elaborar EIPD y análisis de gran escala.
6. Revisar contratos y transferencias Microsoft/Moodle/otros.
7. Definir retención, bloqueo, anonimización y eliminación.
8. Crear procedimiento de vulneraciones y notificación.
9. Validar LOES/RRA por proceso y última reforma.
10. Revisar firma electrónica, transparencia y accesibilidad.

### 60–180 días: gobierno ISO

1. Alcance SGSI/PIMS, política, partes interesadas y responsabilidades.
2. Inventario y clasificación de activos/información.
3. Método y registro de riesgos.
4. Plan de tratamiento y Declaración de Aplicabilidad.
5. Indicadores, auditoría interna y revisión directiva.
6. BIA, RTO/RPO, respaldo, restauración y continuidad.
7. Un ciclo completo de evidencias antes de preauditoría.

## 10. Metas de puntuación

- **6,5/10:** cerrar F-01 a F-06, auditorías verdes, configuración acreditada, rate limiting distribuido y antimalware.
- **7,5/10:** ASVS, threat model, DAST/pentest, MFA, SIEM, SBOM/firma, restauración probada y procesos LOPDP operativos.
- **8,5/10 o más:** SGSI/PIMS con métricas, riesgos aceptados, auditoría interna, revisión directiva, continuidad ejercitada y verificación independiente periódica.

## 11. Evidencia consolidada

| Evidencia | Resultado |
| --- | --- |
| Backend | 543 pruebas y 216 subpruebas aprobadas |
| Frontend | Build correcto; 126 accesos y 57 vistas raíz |
| npm producción | 0 vulnerabilidades |
| npm completo | 1 alta y 1 moderada |
| Python/OSV | 28 paquetes; 3 avisos para `pypdf 6.15.0` |
| SQL | 1.052 ejecuciones; sin f-string directo en la misma línea |
| Excepciones | 38 puntos potenciales |
| Cargas | 78 referencias `UploadFile`; sin antimalware transversal encontrado |
| TLS | 1.0, 1.1, 1.2 y 1.3 aceptados |
| Certificado | Let's Encrypt; vence 2026-11-03 |
| API | CSP, DENY, nosniff, referente, permisos, COOP/CORP y HSTS |
| Frontend | HSTS/no-store; otras cabeceras no observadas |
| Gobierno | SGSI/PIMS/ROPA/SoA/EIPD no evidenciados |

## 12. Conclusión

El sistema es funcional y tiene buena base de ingeniería, pero todavía no demuestra cumplimiento integral ni preparación para certificación. La nota **5,1/10** refleja controles técnicos y pruebas sólidas frente a brechas relevantes de TLS, dependencias, errores, archivos, monitoreo, privacidad y gestión institucional.

La corrección técnica debe avanzar junto con ROPA, EIPD, contratos, transferencias, derechos, retención, incidentes, riesgos, SoA y auditoría. Sin esas evidencias no será posible demostrar ISO/LOPDP aunque el código quede endurecido.

## 13. Referencias

### OWASP e ISO

- [OWASP Top 10:2025](https://owasp.org/Top10/)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)
- [ISO/IEC 27002:2022](https://www.iso.org/standard/75652.html)
- [ISO/IEC 27005:2022](https://www.iso.org/standard/80585.html)
- [ISO/IEC 27034-1:2011](https://www.iso.org/standard/44378.html)
- [ISO/IEC/IEEE 12207:2026](https://www.iso.org/cms/%20render/live/en/sites/isoorg/contents/data/standard/09/02/90219.html)
- [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html)
- [ISO/IEC 27701:2025](https://www.iso.org/standard/27701)

### Ecuador

- [Constitución — Asamblea Nacional](https://www.asambleanacional.gob.ec/sites/default/files/documents/old/constitucion_de_bolsillo.pdf)
- [LOPDP — fuente gubernamental](https://www.finanzaspopulares.gob.ec/wp-content/uploads/2021/07/ley_organica_de_proteccion_de_datos_personales.pdf)
- [Resoluciones de la SPDP](https://spdp.gob.ec/resoluciones2/)
- [Guía SPDP de riesgos y EIPD](https://spdp.gob.ec/resolucion-n-spdp-spd-2025-0003-r-guia-de-gestion-de-riesgos-y-evaluacion-de-impacto-del-tratamiento-de-datos-personales-con-su-anexo/)
- [Cláusulas de protección de datos — SPDP](https://spdp.gob.ec/resolucion6/)
- [Delegado de protección de datos — SPDP](https://spdp.gob.ec/resolucion_028/)
- [LOES — CES](https://www.ces.gob.ec/documentos/Normativa/LOES.pdf)
- [Reglamento de Régimen Académico — CES](https://www.ces.gob.ec/lotaip/Anexos%20Generales/a3_Reformas/r.r.academico.pdf)

### Avisos de dependencias

- [GHSA-23w6-3w8w-8484](https://github.com/advisories/GHSA-23w6-3w8w-8484)
- [GHSA-763m-79hh-57f2](https://github.com/advisories/GHSA-763m-79hh-57f2)
- [GHSA-jp53-mhqp-8xcg](https://github.com/advisories/GHSA-jp53-mhqp-8xcg)
- [GHSA-c83g-rgw3-j3cx](https://github.com/advisories/GHSA-c83g-rgw3-j3cx)
- [GHSA-73wf-gq98-2v4g](https://github.com/advisories/GHSA-73wf-gq98-2v4g)
- [GHSA-p498-v437-472g](https://github.com/advisories/GHSA-p498-v437-472g)
