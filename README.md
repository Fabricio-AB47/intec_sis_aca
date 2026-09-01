# Reporteria INTEC

Aplicacion institucional para integrar y mejorar procesos de `SisAcademicoV1` sobre una arquitectura separada en backend y frontend.

El sistema trabaja contra SQL Server `INTECBDD` y concentra admisiones, matricula, docentes, estudiantes, calificaciones, reporteria, credenciales Microsoft 365, SENESCYT y gestion academica.

## Estructura

- `backend/app`: API FastAPI, seguridad, SQL Server, Microsoft Graph, reportes y PDF.
- `backend/sql`: scripts SQL complementarios.
- `backend/uploads`: archivos subidos en ejecucion local.
- `frontend/src`: SPA React/Vite con modulos por dominio.
- `frontend/public`: recursos publicos como logos.
- `frontend/doc`: plantillas usadas para documentos.
- `SisAcademicoV1`: fuente legacy usada como referencia funcional.

## Requisitos

Backend:

- Python 3.12 recomendado.
- SQL Server / SQL Express con acceso a `INTECBDD`.
- ODBC Driver para SQL Server.
- Variables configuradas en `backend/.env`.

Frontend:

- Node.js 20 o superior.
- npm 10 o superior.

## Configuracion Backend

Desde `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edita `backend/.env` con los datos reales de SQL Server, Microsoft Graph, sesion y CORS.

Para iniciar la API:

```powershell
cd backend
.\dev.ps1
```

El script reutiliza la instancia existente cuando `8002` ya responde y evita
iniciar dos servidores sobre el mismo puerto. Para reiniciar deliberadamente:

```powershell
.\dev.ps1 -Restart
```

La documentacion queda disponible en:

```text
http://127.0.0.1:8002/docs
```

No ejecutes `fastapi dev` una segunda vez si la API ya esta activa. El mensaje
`WinError 10013` en este escenario indica que otra instancia del backend ya
ocupa `8002`; `dev.ps1` comprueba y reutiliza esa instancia.

## Configuracion Frontend

Desde `frontend`:

```powershell
npm install
npm run dev
```

La aplicacion queda disponible en:

```text
http://localhost:5173
```

El proxy de Vite apunta por defecto a:

```text
http://127.0.0.1:8002
```

Para cambiarlo temporalmente:

```powershell
$env:VITE_API_TARGET="http://127.0.0.1:8002"
npm run dev
```

## Modulos Principales

- Autenticacion por roles desde tablas legacy.
- Portal estudiante: dashboard, malla curricular, malla academica y calificaciones.
- Portal docente: materias asignadas, alumnos por periodo/paralelo y carga de notas.
- Admisiones: inscripcion, preinscritos, convenio de pago, documentos, materias y seguimiento.
- Matricula academica: estudiantes, paralelos, materias, pagos y docente.
- Administracion academica: carreras, pensum, periodos, mallas, textos HOMO y catalogos.
- Reporteria: consultas exportables desde datos legacy.
- Integraciones Microsoft 365: credenciales y operaciones Graph.
- Integración Moodle de solo lectura: estado del servicio, usuarios y cursos con filtros y paginación local.

## Integración Moodle

La primera fase de Moodle expone únicamente consultas administrativas. No crea ni modifica usuarios, cursos, matrículas o calificaciones. La configuración y las medidas operativas se documentan en `docs/MOODLE_READ_INTEGRATION.md`.

## Comandos Utiles

Validar backend:

```powershell
python -m compileall backend\app
cd backend
python -c "from app.main import app; print('backend import ok')"
```

Validar frontend:

```powershell
cd frontend
npm run build
```

## Notas Operativas

- No subir `.env`, `.venv`, `node_modules`, `dist`, `uploads` ni archivos generados.
- `backend/requirements.txt` es la fuente de dependencias Python.
- `frontend/package.json` y `frontend/package-lock.json` son la fuente real de dependencias del frontend.
- `frontend/requirements.txt` queda como referencia rapida de entorno y paquetes npm principales.

## Bases complementarias

El backend utiliza las bases `INTEC_EXPEDIENTE_ESTUDIANTIL`,
`INTEC_FINANZAS_INSTITUCIONAL`, `INTEC_GRAPH_INTEGRACION` e
`INTEC_INTEGRACION_CONTROL`. Su instalacion idempotente esta en:

```text
backend/sql/2026_07_22_install_complement_databases.sql
```

Despues de instalar el esquema y aplicar los parches SQL posteriores, carga las
referencias desde la base academica autoritativa y verifica la integracion:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\sync_complement_references.py
.\.venv\Scripts\python.exe scripts\check_complement_databases.py
```
