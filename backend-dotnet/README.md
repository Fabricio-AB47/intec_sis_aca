# Portal de Titulacion INTEC - Backend .NET 8

Solucion Web API por capas para el modulo `TITULACION_INTEC`.

## Estructura

- `Titulacion.Api`: controladores REST, Swagger, JWT, middleware de errores.
- `Titulacion.Application`: servicios, validaciones FluentValidation e interfaces.
- `Titulacion.Domain`: reglas de dominio, codigos de error y calculo de notas.
- `Titulacion.Infrastructure`: Dapper, SQL Server, storage local y PDF de acta.
- `Titulacion.Contracts`: DTOs y requests.
- `Titulacion.Tests`: pruebas unitarias e integracion HTTP con roles.

## Configuracion

La API lee la conexion desde:

```json
{
  "ConnectionStrings": {
    "Titulacion": "Server=127.0.0.1;Database=TITULACION_INTEC;Trusted_Connection=True;TrustServerCertificate=True;MultipleActiveResultSets=True"
  }
}
```

Tambien se puede sobreescribir con variable de entorno:

```powershell
$env:ConnectionStrings__Titulacion="Server=...;Database=TITULACION_INTEC;User Id=...;Password=...;TrustServerCertificate=True"
```

Para crear reuniones Teams desde el apartado de examen complexivo, configure Microsoft Graph:

```powershell
$env:Titulacion__Teams__TenantId="AZURE_TENANT_ID"
$env:Titulacion__Teams__ClientId="AZURE_APP_CLIENT_ID"
$env:Titulacion__Teams__ClientSecret="AZURE_APP_CLIENT_SECRET"
$env:Titulacion__Teams__OrganizerUser="titulacion@intec.edu.ec"
$env:Titulacion__Teams__TimeZone="SA Pacific Standard Time"
```

La app de Entra necesita permiso de aplicacion `Calendars.ReadWrite` con consentimiento de administrador.

Antes de usar la API debe estar aplicado el script SQL:

```text
backend/sql/TITULACION_INTEC_PORTAL_COMPLETO_PROMPT_02.sql
```

## Ejecucion

```powershell
dotnet restore backend-dotnet/Titulacion.slnx
dotnet build backend-dotnet/Titulacion.slnx
dotnet test backend-dotnet/Titulacion.slnx
dotnet run --project backend-dotnet/Titulacion.Api/Titulacion.Api.csproj
```

## QA y seguridad

Roles soportados:

- `ADMIN_TITULACION`
- `SECRETARIA_TITULACION`
- `COORDINADOR_ACADEMICO`
- `EVALUADOR_TITULACION`
- `AUTORIDAD_ACADEMICA`
- `CONSULTA_TITULACION`

Smoke SQL:

```powershell
sqlcmd -S 192.168.100.8 -d TITULACION_INTEC -E -b -I -i backend\sql\TITULACION_INTEC_QA_SMOKE.sql
```

Despliegue, backup y rollback:

```powershell
backend-dotnet\scripts\migrate-titulacion.ps1 -SqlServer "192.168.100.8" -Database "TITULACION_INTEC"
backend-dotnet\scripts\rollback-titulacion.ps1 -SqlServer "192.168.100.8" -BackupFile "D:\Backups\Titulacion\TITULACION_INTEC.bak"
```

Guia completa: `docs/TITULACION_QA_DESPLIEGUE.md`.

Swagger queda disponible en:

```text
https://localhost:{puerto}/swagger
```

Nota: para ejecutar la API en `net8.0` hace falta tener instalado `Microsoft.AspNetCore.App 8.x`. En este equipo las pruebas corren porque usan `Microsoft.NETCore.App 8`, pero la API Web requiere el runtime ASP.NET Core 8.

## Endpoints principales

- `GET /api/titulacion/dashboard/resumen`
- `GET /api/titulacion/estudiantes-aptos`
- `GET /api/titulacion/estudiantes-aptos/{cedula}`
- `POST /api/titulacion/estudiantes-aptos/sincronizar`
- `POST /api/titulacion/habilitaciones`
- `GET /api/titulacion/habilitaciones`
- `PUT /api/titulacion/habilitaciones/{id}/anular`
- `POST /api/titulacion/grupos/complexivo`
- `POST /api/titulacion/grupos/complexivo/teams`
- `POST /api/titulacion/grupos/defensa-grado`
- `GET /api/titulacion/grupos`
- `POST /api/titulacion/grupos/{id}/estudiantes`
- `PUT /api/titulacion/grupos/{id}/programacion`
- `GET /api/titulacion/responsables`
- `POST /api/titulacion/grupos/{grupoId}/responsable-complexivo`
- `POST /api/titulacion/grupos/{grupoId}/tribunal-defensa`
- `POST /api/titulacion/expedientes/{expedienteId}/calificaciones/evaluador`
- `POST /api/titulacion/expedientes/{expedienteId}/calificaciones/consolidar`
- `POST /api/titulacion/documentos/upload`
- `POST /api/titulacion/expedientes/{expedienteId}/acta/generar`
- `POST /api/titulacion/titulos/registro/upload`
- `POST /api/titulacion/titulos/intec/upload`
