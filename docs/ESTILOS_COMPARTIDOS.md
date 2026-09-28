# Estilos compartidos

El frontend unico React utiliza el mismo tema en todos sus modulos. No es necesario copiar
colores ni tipografias entre modulos.

## Fuente de verdad

- `shared/ui/tokens.css`: paleta semantica, tipografia, tamanos, espaciado,
  bordes, sombras y alias compatibles con el CSS existente.
- `shared/ui/components.css`: controles, formularios, tablas, estados,
  ventanas, acceso y foco visible comunes.
- `shared/ui/navigation.css`: menu lateral claro, iconos sin recuadros,
  seleccion, submenus, cierre de sesion y controles moviles.

La paleta conserva el rojo institucional para acciones principales, turquesa
para seleccion y avance, superficies neutras y colores propios para mensajes de
exito, advertencia y error. Los graficos conservan series diferenciadas.

El menu usa fondo blanco, iconos y texto gris legible, y seleccion roja sobre
un fondo rojo tenue con indicador lateral. No utiliza un fondo rojo continuo
ni bordes alrededor de cada icono. Los nombres permanecen visibles al expandir;
las descripciones secundarias se conservan en los titulos al pasar el cursor.
Los encabezados de trabajo son planos, los bordes son suaves y las metricas
usan acentos pequenos de color en lugar de fondos saturados. No se alteran
colores semanticos de alertas, graficos ni formatos imprimibles.

## Prioridad y mantenimiento

El orden de capas es `legacy, ui`. Los estilos locales conservan distribucion,
dimensiones, tablas desplazables, selectores de estado y consultas adaptables en
`legacy`; los controles compartidos se definen en `ui`. Asi, importar despues
una pantalla de carga diferida no cambia el tema de los controles comunes.

El acceso conserva su composicion propia dentro de `.app--auth`: panel gris,
titulo blanco y celeste, campos claros y boton de inicio con degradado institucional.
Estas reglas viven en `shared/ui/components.css`, con colores `--ui-auth-*`, y
no se heredan en las pantallas de trabajo. El control de visibilidad de contrasena
conserva su icono accesible y se alinea con el campo tambien en movil.

Para nuevas pantallas:

1. Mantener la distribucion especifica en `@layer legacy`.
2. Usar `var(--ui-...)` para colores y tipografia; reutilizar las clases de
   acciones existentes (`primary-action`, `ghost-button`, `danger-button`).
3. Incorporar cambios comunes en `shared/ui`, no mediante copias locales ni
   `!important` visual. Las excepciones de distribucion existentes se conservan.
4. Mantener los estilos de PDF, Excel, contratos, firmas y documentos imprimibles
   en sus generadores o marcos de vista previa. No importar el tema en ellos.

La unificacion visual no modifica consultas SQL. La incorporacion del antiguo
portal esta documentada en `FRONTEND_UNIFICADO.md`. Se conservan las reglas
de distribucion para evitar alterar los flujos existentes.

## Verificacion

Desde `frontend`, ejecutar `npm run check:styles` o `npm run build`.
La comprobacion revisa las hojas del frontend, colores literales, tokens inexistentes,
capas, tipografia dependiente del ancho, prioridad visual y contraste de los
pares semanticos principales. `npm run build` ejecuta esta comprobacion antes
de compilar React. `check:frontend` impide reintroducir una segunda aplicacion Angular.

`frontend/scripts/unify-styles.cjs` conserva la migracion mecanica reproducible:
sin argumentos informa diferencias; `--write` normaliza las hojas locales;
`--check` valida sin escribir. No debe ejecutarse `--write` sobre nuevas reglas
sin revisar su resultado. No modifica estilos dentro de generadores de documentos.

Con los servidores locales activos, desde la raiz en PowerShell:

```powershell
$env:FRONTEND_TEST_URL = 'http://127.0.0.1:5175'
.venv/Scripts/python.exe frontend/tests/verify_unified_styles.py
.venv/Scripts/python.exe frontend/tests/verify_login_navigation.py
.venv/Scripts/python.exe frontend/tests/verify_light_navigation.py
```

Las pruebas utilizan respuestas API simuladas y no escriben datos institucionales.
Revisan escritorio y movil, orden de carga CSS, controles, foco, estados,
movimiento reducido, login, seleccion del menu y aislamiento de documentos.
