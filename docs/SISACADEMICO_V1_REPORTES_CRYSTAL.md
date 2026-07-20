# SisAcademicoV1 - Reportes heredados y migracion moderna

## Objetivo

Reemplazar los reportes heredados `.rpt` por reportes modernos generados desde el backend actual:

- SQL Server como fuente de datos.
- FastAPI como capa de parametros, seguridad y consulta.
- `openpyxl` para reportes tabulares Excel.
- `reportlab` para reportes PDF institucionales.
- Frontend React para filtros, vista previa y descarga.

No se debe ejecutar Crystal Reports en el sistema nuevo. Los `.rpt` quedan solo como referencia visual y funcional.

## Inventario tecnico

Se detectaron:

- 176 archivos `.aspx.vb`.
- 30 pantallas con uso de Crystal Reports o formulas `.rpt`.
- 37 archivos `.rpt` fisicos.
- 23 referencias directas a `.rpt` desde codigo VB.

## Familias de reportes

| Familia | Reportes V1 | Estado moderno |
|---|---|---|
| Academico por estudiante | `CryAcadxEstud.rpt`, `CryAcadxEstudHomo.rpt`, `CryAcadxEstudGeneral.rpt` | Base modernizada en portal academico y titulacion |
| Totales matricula R/H | `CryListaTotalEstudPeriodo*.rpt`, `CryListaTotalEstudAnio*.rpt` | Modernizado en reportería integral Excel |
| Docentes por materia | `CrysListaProfesorMateria.rpt` | Base en reportería integral y portal docente |
| Egresados | `CryListaEgresados.rpt` | Base en módulo de titulación |
| Practicas | `CrysReporteParcticasProfesional*.rpt` | Base en prácticas institucionales y reportería |
| Convenio pagos | `CryConvenioPagos.rpt` | Modernizado como PDF backend |
| Certificados | `certificadosf.rpt`, `certificado.rpt` | Modernizado como PDF/ZIP backend |
| Educación continua | `certificadosEduCon.rpt`, `certificadoEdContinua.rpt` | Pendiente PDF específico |
| Evaluación docente | `CryEvaluaciondocente.rpt`, `CryEstudEvaluaProfe*.rpt` | Modernizado con PDF/ZIP reportlab |

## Reglas de migracion

### 1. No copiar el visor heredado

El codigo V1 usa patrones como:

```vb
CrystalReportSource1.ReportDocument.RecordSelectionFormula = "{DATOS_ESTUD.codigo_estud}=" & cod
CrystalReportViewer1.Visible = True
```

En el sistema nuevo eso debe convertirse a:

1. Endpoint backend con parametros tipados.
2. Consulta SQL parametrizada.
3. Respuesta JSON, Excel o PDF.
4. Vista React con filtros claros.

### 2. Reemplazar `RecordSelectionFormula`

Cada formula se traduce a `WHERE` SQL parametrizado. Ejemplo:

```text
{DATOS_ESTUD.codigo_estud}=cod and {PENSUM.verreporte}=1
```

Debe ser:

```sql
WHERE de.codigo_estud = ?
  AND p.verreporte = 1
```

### 3. Mantener reglas academicas

Para reportes de notas:

- Tipo `R`: mostrar parciales `P1`, `P2`, `P3`, promedio final y estado.
- Tipo `H`: mostrar teorico, practico, promedio final y estado.
- Aprobado: nota final mayor o igual a 7.
- Reprobado: nota final menor a 7.
- Maximo permitido: 10.

### 4. Reportes masivos

Los reportes que antes se mostraban con visor heredado deben tener:

- Exportacion Excel para datos masivos.
- PDF institucional cuando el documento se entrega al estudiante/docente.
- ZIP cuando se generen documentos individuales por lote.

## Endpoint creado

Se agrego el catalogo moderno:

```http
GET /api/students/reporteria-integral/modern-catalog
```

Devuelve:

- Reporte heredado.
- Archivo `.rpt` original.
- Pantallas V1 que lo usaban.
- Tablas fuente.
- Filtros heredados.
- Equivalente moderno.
- Estado de migracion.

## Estados

| Estado | Significado |
|---|---|
| `modernizado` | Ya existe ruta funcional moderna que reemplaza el `.rpt`. |
| `base` | Existe la estructura/dataset, falta igualar todo el formato documental. |
| `pendiente` | Requiere crear generador PDF/Excel especifico. |

## Prioridad siguiente

1. Completar PDF de educación continua.
2. Separar PDF académico regular y homologación con diseño institucional.
3. Agregar exportación PDF a reportes de prácticas.
4. Consolidar egresados/titulación como reporte de estudiantes aptos.
5. Crear descarga masiva ZIP para actas/certificados académicos si Secretaría lo requiere.
