# Auditoria de integracion total

La auditoria central vive en `INTEC_INTEGRACION_CONTROL` y registra cambios
`INSERT`, `UPDATE`, `DELETE` y DDL de todas las bases configuradas por el
backend. Las consultas `SELECT` no se auditan porque no modifican informacion.

## Identidad registrada

Cada solicitud del backend propaga a SQL Server el usuario autenticado, rol,
origen, identificador de usuario, ruta HTTP, metodo, IP e identificador de
solicitud. Una operacion directa desde SSMS conserva el login SQL, equipo y
aplicacion cliente como respaldo.

Las columnas que contienen claves, tokens, secretos, certificados o archivos
P12 se registran como `[PROTEGIDO]`. Los binarios no se copian: solo se conserva
su tamano. Cada evento guarda como maximo 100 filas de muestra.

## Consulta

```sql
USE INTEC_INTEGRACION_CONTROL;
GO

EXEC aud.sp_ConsultarCambios
    @BaseDatos = N'INTECBDD',
    @UsuarioAplicacion = NULL,
    @FechaDesdeUtc = DATEADD(DAY, -1, SYSUTCDATETIME()),
    @FechaHastaUtc = NULL,
    @Limite = 500;
GO

SELECT *
FROM rpt.vw_AuditoriaIntegracion
ORDER BY EventoCambioId DESC;
GO

EXEC util.sp_DiagnosticoAuditoriaTotal;
GO
```

## Sincronizacion de cobertura

El instalador es aditivo e idempotente. Debe volver a ejecutarse despues de
crear tablas nuevas:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\install_total_audit.py
```

La instalacion correcta debe terminar sin pendientes en
`rpt.vw_CoberturaAuditoriaIntegracion`.
