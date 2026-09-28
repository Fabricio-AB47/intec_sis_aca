# Frontend unico

La aplicacion desplegable es `frontend/` (React/Vite). La antigua aplicacion
Angular se traslado a componentes React en `frontend/src/features/titulacion/`;
no se usa un iframe, un segundo servidor web ni otro inicio de sesion.

La raiz del repositorio debe contener solamente `frontend/` como aplicacion
de interfaz. `frontend-angular/` no debe permanecer ni como carpeta vacia ni
con restos de `.angular`, `node_modules` o compilaciones. `npm run check:frontend`
comprueba esa ausencia antes de compilar y exige el portal ya integrado.
Si el explorador del editor conserva la carpeta anterior, actualizar su vista;
los archivos eliminados pueden seguir visibles en Control de codigo fuente
hasta registrar los cambios en Git, sin existir ya en el disco.

## Navegacion y datos

Abrir **Titulacion > Proceso de titulacion**:

- **Expediente individual** conserva el flujo FastAPI existente.
- **Gestion integral** incorpora resumen, aptos, habilitaciones, grupos,
  complexivo/Teams, defensa, responsables, calificaciones, documentos, titulos,
  actas y reportes del antiguo portal. Se carga bajo demanda.

Los datos no se copian a otra base. Las operaciones grupales siguen usando los
contratos y validaciones del servicio .NET existente; los expedientes
individuales siguen usando sus endpoints actuales. No se ejecuta SQL de
migracion ni sincronizacion automatica al abrir la interfaz.

## Conexion del servicio existente

Configurar en `backend/.env`, sin incluir secretos reales en Git:

```dotenv
TITULATION_PORTAL_URL=http://127.0.0.1:8007
TITULATION_PORTAL_SIGNING_KEY=<clave aleatoria fuerte de al menos 32 caracteres>
TITULATION_PORTAL_ISSUER=INTEC
TITULATION_PORTAL_AUDIENCE=INTEC_PORTAL_TITULACION
```

En el servicio .NET deben coincidir `Jwt__SigningKey`, `Jwt__Issuer` y
`Jwt__Audience`. Mantener sus conexiones SQL y almacenamiento actuales. Si el
servicio es remoto, la URL debe ser HTTPS con certificado valido; solo se
permite HTTP en localhost. No usar la clave predeterminada de desarrollo.

Reiniciar los servicios tras configurar. Si faltan estos parametros, Gestion
integral muestra un aviso y el expediente individual permanece disponible.
No se intentan escrituras ni conexiones SQL durante las pruebas de interfaz.

El navegador usa la cookie academica existente. FastAPI valida acceso a
`titulacion-proceso`, emite un JWT de dos minutos con el usuario real y lo envia
exclusivamente al servicio. El JWT nunca se devuelve al navegador. No se usan
`intec_token` ni roles definidos por localStorage. .NET conserva la validacion
de permisos de cada operacion.

Mapeo de perfiles:

- Administrador: administracion, coordinacion y evaluacion.
- Academico: coordinacion.
- Secretaria: documentos y titulos.
- Rector y vicerrector: autoridad academica.
- Soporte: consulta, sin escritura.
- Docente: evaluador, solo si tiene acceso a la pantalla asignado.
- Estudiante y otros perfiles: sin acceso al puente.

Hay una lista cerrada de rutas, limite de carga de 32 MB, tiempo de espera,
respuesta sin cache y sin reintentos automaticos de escritura. Ante timeout,
consultar el resultado antes de repetir una operacion.

## Tema y despliegue

`shared/ui/tokens.css`, `shared/ui/components.css` y `shared/ui/navigation.css`
son la fuente del tema.
El login conserva su composicion institucional separada de las superficies
operativas. El menu usa fondo blanco, texto gris y seleccion roja sobre un tono claro;
los botones comparten radio de 6 px. Los formatos PDF no heredan estos estilos.

Ejecutar `npm ci` y `npm run build` desde `frontend`. Desplegar solamente
`frontend/dist`; enrutar `/api` a FastAPI. No desplegar Angular ni el puerto 4200.
La API .NET sigue siendo un servicio interno, no otro frontend.

Antes de retirar Angular se guardaron sus 37 archivos de codigo/configuracion
locales en `.runlogs/frontend-angular-before-unification-20260922.zip`. Sus
artefactos generados estan en `.runlogs/frontend-angular-generated-20260922/`.
Son copias locales ignoradas por Git; el historial Git conserva las fuentes.

## Pruebas

Desde `frontend`, ejecutar `npm run test:frontend` para verificar la estructura:
aplicacion unica, ausencia de carpetas residuales, dependencias sin Angular y
presencia del portal de titulacion. Las pruebas crean y limpian un directorio
temporal aislado en `.runlogs`; no modifican el codigo de la aplicacion.

```powershell
$env:FRONTEND_TEST_URL='http://127.0.0.1:5175'
.venv/Scripts/python.exe frontend/tests/verify_login_navigation.py
.venv/Scripts/python.exe frontend/tests/verify_unified_styles.py
.venv/Scripts/python.exe frontend/tests/verify_titulation_portal.py
```

Desde `backend`: `../.venv/Scripts/python.exe -m pytest tests/test_titulation_portal.py -q`.
Las pruebas interceptan todas las solicitudes, verifican archivos y contenido
de reportes, permisos, identidad, errores, contraste y pantallas adaptables.
La conexion real al servicio .NET requiere validacion en el entorno configurado.
