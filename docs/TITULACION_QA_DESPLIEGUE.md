# Portal de Titulacion INTEC - QA y despliegue

## Alcance QA

Cobertura automatizada agregada:

- Backend unitario: calculo de notas, validadores FluentValidation, servicios de habilitacion, responsables, calificaciones, documentos, titulos y actas.
- Backend integracion: endpoints con autenticacion de prueba y validacion de roles 401/403/200.
- SQL smoke: objetos criticos, catalogos, columnas, vistas y procedimientos de `TITULACION_INTEC`.
- Frontend unitario: guard de roles, formularios de titulos y carga documental.
- Frontend E2E Playwright: dashboard, estudiantes aptos, bloqueo de ruta por rol y validacion SENESCYT.

## Comandos de pruebas

Backend:

```powershell
dotnet restore backend-dotnet/Titulacion.slnx
dotnet build backend-dotnet/Titulacion.slnx --no-restore
dotnet test backend-dotnet/Titulacion.slnx --no-build
```

Frontend:

```powershell
cd frontend-angular
npm install
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
npm run e2e
```

SQL smoke:

```powershell
sqlcmd -S 192.168.100.8 -d TITULACION_INTEC -E -b -I -i backend\sql\TITULACION_INTEC_QA_SMOKE.sql
```

Si se usa usuario SQL:

```powershell
sqlcmd -S 192.168.100.8 -d TITULACION_INTEC -U APP_USER -P "********" -b -I -i backend\sql\TITULACION_INTEC_QA_SMOKE.sql
```

Con ODBC Driver 18 y certificados internos/no confiados, agregar `-C` a `sqlcmd`.

## Matriz de roles

- `ADMIN_TITULACION`: habilita estudiantes, administra catalogos operativos, carga titulos, genera/anula actas.
- `SECRETARIA_TITULACION`: gestiona documentos y titulos.
- `COORDINADOR_ACADEMICO`: habilita estudiantes, crea grupos/defensas, asigna responsables y tribunal, consolida.
- `EVALUADOR_TITULACION`: registra sus notas.
- `AUTORIDAD_ACADEMICA`: genera y consulta actas.
- `CONSULTA_TITULACION`: consulta reportes y seguimiento sin modificar.

Reglas protegidas en backend:

- Habilitacion: `ADMIN_TITULACION`, `COORDINADOR_ACADEMICO`.
- Asignacion de responsable/tribunal: `COORDINADOR_ACADEMICO`.
- Registro de notas: `EVALUADOR_TITULACION`.
- Generacion/anulacion de actas: `ADMIN_TITULACION`, `AUTORIDAD_ACADEMICA`.
- Carga de titulos: `ADMIN_TITULACION`, `SECRETARIA_TITULACION`.

## Variables de entorno

Archivo ejemplo: `backend-dotnet/deploy/titulacion.env.example`.

Variables principales:

```text
ASPNETCORE_ENVIRONMENT=Production
ASPNETCORE_URLS=http://0.0.0.0:8080
ConnectionStrings__Titulacion=Server=tcp:SQLSERVER_HOST,1433;Database=TITULACION_INTEC;User Id=APP_USER;Password=CHANGE_ME;Encrypt=True;TrustServerCertificate=False;MultipleActiveResultSets=True
Jwt__Issuer=INTEC
Jwt__Audience=INTEC_PORTAL_TITULACION
Jwt__SigningKey=CHANGE_ME_WITH_64_PLUS_RANDOM_CHARS
Titulacion__Storage__RootPath=D:\INTEC\storage\titulacion
Titulacion__Storage__PublicBaseUrl=https://portal.intec.edu.ec/files/titulacion
Titulacion__Teams__TenantId=AZURE_TENANT_ID
Titulacion__Teams__ClientId=AZURE_APP_CLIENT_ID
Titulacion__Teams__ClientSecret=AZURE_APP_CLIENT_SECRET
Titulacion__Teams__OrganizerUser=titulacion@intec.edu.ec
Titulacion__Teams__TimeZone=SA Pacific Standard Time
```

No guardar secretos reales en git.

Para crear reuniones Teams desde examen complexivo, la aplicacion de Entra debe tener permiso de aplicacion `Calendars.ReadWrite` con consentimiento de administrador y `OrganizerUser` debe ser una cuenta Microsoft 365 con calendario y Teams habilitados.

## Migracion

Script:

```powershell
backend-dotnet\scripts\migrate-titulacion.ps1 `
  -SqlServer "192.168.100.8" `
  -Database "TITULACION_INTEC" `
  -BackupDirectory "D:\Backups\Titulacion"
```

El script:

- crea respaldo previo con `BACKUP DATABASE`;
- aplica los SQL del modulo en orden;
- ejecuta `TITULACION_INTEC_QA_SMOKE.sql`;
- falla con codigo no cero si un script SQL falla.

Usar `-SkipBackup` solo si ya existe un respaldo externo verificado o si la ruta de backup no es accesible por el servicio SQL Server.

Para autenticacion SQL:

```powershell
backend-dotnet\scripts\migrate-titulacion.ps1 `
  -SqlServer "192.168.100.8" `
  -SqlUser "APP_USER" `
  -SqlPassword "********" `
  -TrustServerCertificate
```

Parche V9 de evaluadores variables y promedios por rubrica:

```powershell
backend-dotnet\scripts\migrate-titulacion.ps1 `
  -SqlServer "192.168.100.8" `
  -SqlUser "APP_USER" `
  -SqlPassword "********" `
  -TrustServerCertificate `
  -IncludePatchV9Rubricas
```

Ese parche requiere que existan previamente `tit.TrabajoTitulacion`, `eval.EvaluadorTrabajoTitulacion`, `eval.ConsolidadoExpediente`, `eval.ComponenteEvaluacion`, `eval.RubricaComponente` y `eval.CalificacionComponenteEvaluador`.

## Rollback

Restaurar el respaldo generado antes de la migracion:

```powershell
backend-dotnet\scripts\rollback-titulacion.ps1 `
  -SqlServer "192.168.100.8" `
  -Database "TITULACION_INTEC" `
  -BackupFile "D:\Backups\Titulacion\TITULACION_INTEC-YYYYMMDD-HHMMSS.bak"
```

El rollback cambia temporalmente la base a `SINGLE_USER`, ejecuta `RESTORE DATABASE ... WITH REPLACE` y vuelve a `MULTI_USER`.

## Checklist produccion

- Confirmar respaldo exitoso y restaurable.
- Confirmar que `TITULACION_INTEC_QA_SMOKE.sql` devuelve `OK`.
- Confirmar que el usuario SQL tiene solo permisos necesarios para la API.
- Confirmar `Jwt__SigningKey` fuerte y distinto por ambiente.
- Confirmar HTTPS en proxy/reverse proxy.
- Confirmar ruta de storage con permisos de escritura para la API.
- Confirmar permisos Microsoft Graph `Calendars.ReadWrite` y organizador Teams valido para `POST /api/titulacion/grupos/complexivo/teams`.
- Confirmar politica de retencion de PDFs, titulos y respaldos.
- Ejecutar `dotnet test`, `npm test` y `npm run e2e`.
- Validar manualmente un flujo completo: apto -> habilitacion -> grupo/defensa -> 3 notas -> acta -> titulo SENESCYT -> titulo INTEC.
- Revisar logs de autenticacion y errores SQL despues del despliegue.

## Criterios de salida

- 0 errores en build backend/frontend.
- 0 fallos en pruebas unitarias e integracion.
- Smoke SQL sin fallas.
- Endpoints sensibles devuelven 403 con roles no autorizados.
- Actas no se generan con calificacion incompleta ni documentos obligatorios pendientes.
