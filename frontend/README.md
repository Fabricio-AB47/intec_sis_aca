# Frontend Reporteria

Cliente React + Vite para login institucional, dashboard, Teams y matricula.

## Scripts

- `npm run dev`: desarrollo local.
- `npm run build`: compilacion de produccion.
- `npm run lint`: analisis estatico.

## Estructura

- `src/features/auth`: login y validacion visual de sesion.
- `src/features/dashboard`: vista principal.
- `src/features/teams`: consulta y operaciones de Teams.
- `src/features/matricula`: resumen y listado modal.
- `src/hooks/useReporteriaApp.ts`: estado de aplicacion y coordinacion con la API.
- `src/lib/api.ts`: cliente HTTP centralizado con `credentials: 'include'`.
