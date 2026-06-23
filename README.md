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
fastapi dev app/main.py --host 127.0.0.1 --port 8002
```

Alternativa:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

La documentacion queda disponible en:

```text
http://127.0.0.1:8002/docs
```

Si aparece `WinError 10013` o puerto ocupado, usa otro puerto y ajusta `VITE_API_TARGET` en el frontend.

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
