import { useMemo, useState } from 'react'

import { uploadExcelValidation } from '../../lib/api'
import type { ExcelValidationResponse, ExcelValidationRow } from '../../types/app'

type ExcelValidationViewProps = {
  displayName: string
}

const statusLabels: Record<string, string> = {
  ENCONTRADO: 'Encontrado',
  PARCIAL: 'Parcial',
  NO_ENCONTRADO: 'No encontrado',
  SIN_IDENTIFICADOR: 'Sin identificador',
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function percentOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text ? `${text}%` : '-'
}

function statusLabel(value?: string): string {
  return statusLabels[value || ''] || value || 'Pendiente'
}

function statusClass(value?: string): string {
  return `cruce-status cruce-status--${(value || 'pendiente').toLowerCase().replaceAll('_', '-')}`
}

function boolText(value?: boolean): string {
  return value ? 'Si' : 'No'
}

function csvValue(value: string | number | boolean | null | undefined): string {
  const text = String(value ?? '')
  return `"${text.replaceAll('"', '""')}"`
}

function downloadCsv(rows: ExcelValidationRow[]) {
  const headers = [
    'Fila Excel',
    'Resultado',
    'Cruce por',
    'Codigo Excel',
    'Cedula Excel',
    'Correo Excel',
    'Nombre Excel',
    'Existe DATOS_ESTUD',
    'Existe CorreosIntec',
    'Existe PREINSCRIPCION',
    'Tiene matricula',
    'Codigo BD',
    'Cedula BD',
    'Estudiante BD',
    'Estado BD',
    'Correo BD',
    'Correo INTEC BD',
    'Beca',
    'Porcentaje beca',
    'Periodo',
    'Carrera',
  ]
  const body = rows.map((row) => [
    row.row_number,
    statusLabel(row.status),
    row.match_field,
    row.excel?.codigo,
    row.excel?.cedula,
    row.excel?.correo || row.excel?.correo_intec,
    row.excel?.nombre,
    boolText(row.exists?.datos_estud),
    boolText(row.exists?.correos_intec),
    boolText(row.exists?.preinscripcion),
    boolText(row.exists?.matricula),
    row.db?.codigo_estud,
    row.db?.cedula,
    row.db?.estudiante,
    row.db?.estado,
    row.db?.correo,
    row.db?.correo_intec,
    row.db?.tipo_beca,
    row.db?.porcentaje_beca,
    row.db?.periodo,
    row.db?.carrera,
  ])
  const csv = [headers, ...body].map((line) => line.map(csvValue).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `validacion-excel-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function ExcelValidationView({ displayName }: Readonly<ExcelValidationViewProps>) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [data, setData] = useState<ExcelValidationResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [tableFilter, setTableFilter] = useState('')

  const rows = data?.rows || []
  const summary = data?.summary
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      [
        row.status,
        row.match_field,
        row.excel?.codigo,
        row.excel?.cedula,
        row.excel?.correo,
        row.excel?.correo_intec,
        row.excel?.nombre,
        row.db?.codigo_estud,
        row.db?.cedula,
        row.db?.estudiante,
        row.db?.correo,
        row.db?.correo_intec,
        row.db?.periodo,
        row.db?.carrera,
        row.db?.tipo_beca,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [rows, tableFilter])

  async function analyzeExcel() {
    setError('')
    if (!selectedFile) {
      setError('Selecciona un archivo .xlsx para analizar.')
      return
    }

    setLoading(true)
    try {
      const payload = await uploadExcelValidation(selectedFile)
      setData(payload)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo analizar el Excel')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const statItems = [
    ['Total filas', summary?.total],
    ['Encontrados', summary?.encontrados],
    ['Parciales', summary?.parciales],
    ['No encontrados', summary?.no_encontrados],
    ['Sin identificador', summary?.sin_identificador],
    ['Duplicados Excel', summary?.duplicados_excel],
    ['DATOS_ESTUD', summary?.en_datos_estud],
    ['Correos INTEC', summary?.en_correos_intec],
    ['PREINSCRIPCION', summary?.en_preinscripcion],
    ['Con matricula', summary?.con_matricula],
  ] as const

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Validacion Excel</p>
          <h1>Verificar datos en base</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Cruce SQL</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content excel-validation-grid">
        <article className="student-card student-card--wide excel-validation-upload-card">
          <div className="card-head">
            <h3>Cargar archivo</h3>
            <span>{selectedFile ? selectedFile.name : 'Archivo .xlsx'}</span>
          </div>

          <div className="excel-validation-upload">
            <label>
              <span>Excel a validar</span>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
              />
            </label>
            <div className="excel-validation-help">
              <strong>Columnas reconocidas</strong>
              <span>codigo, codestud, cedula, identificacion, correo, correo_intec, estudiante, nombres.</span>
            </div>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void analyzeExcel()} disabled={loading}>
              {loading ? 'Analizando...' : 'Analizar Excel'}
            </button>
            <button type="button" onClick={() => downloadCsv(visibleRows)} disabled={visibleRows.length === 0}>
              Descargar CSV
            </button>
          </div>

          {error ? <p className="teams-error">{error}</p> : null}
          {data?.warnings?.length ? (
            <div className="cruce-warning-list">
              {data.warnings.map((warning) => (
                <p key={warning} className="teams-message">
                  {warning}
                </p>
              ))}
            </div>
          ) : null}
        </article>
      </section>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {statItems.map(([label, value]) => (
          <article key={label} className="student-card student-card--stat matricula-stat-card">
            <p>{label}</p>
            <h2>{formatNumber(value)}</h2>
            <small>{data?.filename || 'Pendiente de analisis'}</small>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide excel-validation-results-card">
          <div className="card-head">
            <h3>Resultado de validacion</h3>
            <span>{loading ? 'Procesando...' : `${formatNumber(rows.length)} fila(s)`}</span>
          </div>

          {data?.detected_columns ? (
            <div className="excel-validation-detected">
              {Object.entries(data.detected_columns).map(([key, value]) => (
                <span key={key}>
                  <strong>{key}</strong>
                  <em>{value || 'No detectada'}</em>
                </span>
              ))}
            </div>
          ) : null}

          <div className="excel-toolbar">
            <label>
              <span>Filtrar tabla</span>
              <input
                value={tableFilter}
                onChange={(event) => setTableFilter(event.target.value)}
                placeholder="Buscar por nombre, cedula, correo, estado o carrera"
              />
            </label>
            <div>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <span>de {formatNumber(rows.length)} fila(s)</span>
            </div>
            <small>{data?.generated_at ? `Generado ${data.generated_at.slice(0, 19)}` : 'Sin archivo procesado'}</small>
          </div>

          <div className="matricula-table-wrap excel-table-wrap excel-validation-table-wrap">
            <table className="matricula-table excel-validation-table">
              <thead>
                <tr>
                  <th>Fila</th>
                  <th>Resultado</th>
                  <th>Excel</th>
                  <th>Base de datos</th>
                  <th>Existencias</th>
                  <th>Beca</th>
                  <th>Ultima matricula</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? (
                  visibleRows.map((row, index) => (
                    <tr key={`excel-validation-${row.row_number}-${index}`}>
                      <td>{row.row_number || index + 1}</td>
                      <td>
                        <span className={statusClass(row.status)}>{statusLabel(row.status)}</span>
                        <small>{row.match_field ? `Cruce por ${row.match_field}` : 'Sin cruce'}</small>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <strong>{valueOrDash(row.excel?.nombre)}</strong>
                          <span>{valueOrDash(row.excel?.cedula || row.excel?.codigo)}</span>
                          <small>{valueOrDash(row.excel?.correo_intec || row.excel?.correo)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <strong>{valueOrDash(row.db?.estudiante)}</strong>
                          <span>{valueOrDash(row.db?.cedula || row.db?.codigo_estud)}</span>
                          <small>{valueOrDash(row.db?.correo_intec || row.db?.correo)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="excel-validation-exists">
                          <span className={row.exists?.datos_estud ? 'excel-validation-exists--ok' : ''}>DATOS {boolText(row.exists?.datos_estud)}</span>
                          <span className={row.exists?.correos_intec ? 'excel-validation-exists--ok' : ''}>Correos {boolText(row.exists?.correos_intec)}</span>
                          <span className={row.exists?.preinscripcion ? 'excel-validation-exists--ok' : ''}>Preins {boolText(row.exists?.preinscripcion)}</span>
                          <span className={row.exists?.matricula ? 'excel-validation-exists--ok' : ''}>Matricula {boolText(row.exists?.matricula)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.db?.tipo_beca || 'Sin beca')}</span>
                          <small>{percentOrDash(row.db?.porcentaje_beca)}</small>
                        </div>
                      </td>
                      <td>
                        <div className="cruce-source-stack">
                          <span>{valueOrDash(row.db?.periodo)}</span>
                          <small>{valueOrDash(row.db?.carrera)}</small>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>{loading ? 'Analizando Excel...' : 'Sube un archivo .xlsx para ver resultados.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </>
  )
}
