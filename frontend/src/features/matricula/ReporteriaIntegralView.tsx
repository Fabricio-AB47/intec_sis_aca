import { useEffect, useMemo, useState } from 'react'

import {
  downloadLegacyReportWorkbook,
  fetchLegacyReport,
  fetchLegacyReportsCatalog,
} from '../../lib/api'
import type {
  LegacyFunctionalInventoryItem,
  LegacyReportOption,
  LegacyReportDefinition,
  LegacyReportFilters,
  LegacyReportKey,
  LegacyReportResponse,
  LegacyReportRow,
} from '../../types/app'

type ReporteriaIntegralViewProps = {
  displayName: string
  heading?: string
  eyebrow?: string
  individualMode?: boolean
  initialReportKey?: string
}

const defaultReports: LegacyReportDefinition[] = [
  {
    key: 'matriculados',
    title: 'Estudiantes matriculados',
    category: 'Academico',
    description: 'Reporte por periodo, carrera, estado y paralelo.',
    source_tables: ['CARRERAXESTUD', 'DATOS_ESTUD', 'CARRERAS', 'PERIODO'],
    estado_options: [
      { value: 'A', label: 'Activo' },
      { value: 'G', label: 'Graduado' },
      { value: 'P', label: 'Inactivo' },
      { value: 'R', label: 'Retirado' },
    ],
  },
]

const ageRangeOrder = ['Menor de 18', '18 a 29', '30 a 40', '41 a 50', '51 a 60', '61 o mas', 'Sin fecha']

type AgeRangeSummary = {
  range: string
  total: number
  scholarship: number
  withoutScholarship: number
  scholarshipPercentTotal: number
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function formatCell(value: LegacyReportRow[string]): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'Si' : 'No'
  if (typeof value === 'number') return new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(value)
  return String(value)
}

function columnLabel(column: string): string {
  return column
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (value) => value.toUpperCase())
}

function cellNumber(value: LegacyReportRow[string]): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const parsed = Number(String(value ?? '').replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

function ageRangeSortValue(range: string): number {
  const index = ageRangeOrder.indexOf(range)
  return index >= 0 ? index : ageRangeOrder.length
}

function downloadBlob(blob: Blob, reportKey: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `reporteria-integral-${reportKey}-${new Date().toISOString().slice(0, 10)}.xlsx`
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function ReporteriaIntegralView({
  displayName,
  heading = 'Reportes operativos',
  eyebrow = 'Reporteria',
  individualMode = false,
  initialReportKey = '',
}: Readonly<ReporteriaIntegralViewProps>) {
  const [reports, setReports] = useState<LegacyReportDefinition[]>(defaultReports)
  const [inventory, setInventory] = useState<LegacyFunctionalInventoryItem[]>([])
  const [periodOptions, setPeriodOptions] = useState<LegacyReportOption[]>([])
  const [careerOptions, setCareerOptions] = useState<LegacyReportOption[]>([])
  const [reportKey, setReportKey] = useState<LegacyReportKey>(
    (initialReportKey as LegacyReportKey) || 'matriculados',
  )
  const [appliedInitialReport, setAppliedInitialReport] = useState('')
  const [periodo, setPeriodo] = useState('')
  const [carrera, setCarrera] = useState('')
  const [estado, setEstado] = useState('')
  const [buscar, setBuscar] = useState('')
  const [limit, setLimit] = useState(500)
  const [loading, setLoading] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState<LegacyReportResponse | null>(null)
  const [tableFilter, setTableFilter] = useState('')

  const selectedReport = useMemo(
    () => reports.find((report) => report.key === reportKey) || reports[0],
    [reportKey, reports],
  )
  const directReportMode = individualMode && Boolean(initialReportKey)
  const enabledFilters = useMemo(
    () => new Set(selectedReport?.filters?.length ? selectedReport.filters : ['periodo', 'carrera', 'estado', 'buscar', 'limite']),
    [selectedReport],
  )
  const columns = data?.columns || []
  const rows = data?.rows || []
  const ageRangeSummary = useMemo((): AgeRangeSummary[] => {
    if (reportKey !== 'becas_edades') return []
    const summary = new Map<string, AgeRangeSummary>()
    for (const row of rows) {
      const range = String(row.rango_edad || 'Sin fecha')
      const current =
        summary.get(range) ||
        {
          range,
          total: 0,
          scholarship: 0,
          withoutScholarship: 0,
          scholarshipPercentTotal: 0,
        }
      const scholarshipName = String(row.tipo_beca || '').trim()
      const hasScholarship = scholarshipName !== '' && scholarshipName.toLowerCase() !== 'sin beca'
      current.total += 1
      if (hasScholarship) {
        current.scholarship += 1
        current.scholarshipPercentTotal += cellNumber(row.porcentaje_beca)
      } else {
        current.withoutScholarship += 1
      }
      summary.set(range, current)
    }
    return Array.from(summary.values()).sort((left, right) => ageRangeSortValue(left.range) - ageRangeSortValue(right.range))
  }, [reportKey, rows])
  const ageRangeMaxTotal = useMemo(
    () => Math.max(1, ...ageRangeSummary.map((item) => item.total)),
    [ageRangeSummary],
  )
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      columns.some((column) => formatCell(row[column]).toLowerCase().includes(needle)),
    )
  }, [columns, rows, tableFilter])
  const sourceTables = selectedReport?.source_tables || []
  const estadoOptions = selectedReport?.estado_options || []
  const activeFilters = [
    enabledFilters.has('periodo') && periodo ? `Periodo ${periodOptions.find((option) => option.value === periodo)?.label || periodo}` : '',
    enabledFilters.has('carrera') && carrera ? `Carrera ${careerOptions.find((option) => option.value === carrera)?.label || carrera}` : '',
    enabledFilters.has('estado') && estado ? `Estado ${estado}` : '',
    enabledFilters.has('buscar') && buscar ? `Busqueda "${buscar}"` : '',
  ].filter(Boolean)

  function filtersForReport(nextReportKey: LegacyReportKey) {
    const report = reports.find((item) => item.key === nextReportKey) || selectedReport
    return new Set(report?.filters?.length ? report.filters : ['periodo', 'carrera', 'estado', 'buscar', 'limite'])
  }

  function filters(nextReportKey: LegacyReportKey = reportKey, nextEstado: string = estado): LegacyReportFilters {
    const nextEnabledFilters = filtersForReport(nextReportKey)
    return {
      reportKey: nextReportKey,
      periodo: nextEnabledFilters.has('periodo') ? periodo.trim() : '',
      carrera: nextEnabledFilters.has('carrera') ? carrera.trim() : '',
      estado: nextEnabledFilters.has('estado') ? nextEstado.trim() : '',
      buscar: nextEnabledFilters.has('buscar') ? buscar.trim() : '',
      limit,
    }
  }

  function validateFiltersForReport(nextReportKey: LegacyReportKey) {
    if (nextReportKey === 'estud_per_c_m' && !periodo.trim()) {
      return 'Selecciona un periodo para consultar estudiantes, carreras y materias matriculadas.'
    }
    return ''
  }

  async function loadReport(nextReportKey: LegacyReportKey = reportKey, nextEstado: string = estado) {
    setError('')
    const validationMessage = validateFiltersForReport(nextReportKey)
    if (validationMessage) {
      setData(null)
      setError(validationMessage)
      return
    }
    setLoading(true)
    try {
      const payload = await fetchLegacyReport(filters(nextReportKey, nextEstado))
      setData(payload)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Error generando el reporte integral')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  async function exportReport() {
    setError('')
    const validationMessage = validateFiltersForReport(reportKey)
    if (validationMessage) {
      setError(validationMessage)
      return
    }
    setDownloadLoading(true)
    try {
      const blob = await downloadLegacyReportWorkbook({ ...filters(), limit: Math.max(limit, 5000) })
      downloadBlob(blob, reportKey)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Error exportando el reporte integral')
    } finally {
      setDownloadLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      try {
        const payload = await fetchLegacyReportsCatalog()
        if (cancelled) return
        if (payload.reports?.length) {
          setReports(payload.reports)
        }
        setInventory(payload.functional_inventory || [])
        setPeriodOptions(payload.periodos || [])
        setCareerOptions(payload.carreras || [])
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'Error cargando catalogo integral')
        }
      } finally {
        if (!cancelled) {
          setCatalogLoading(false)
        }
      }
    }

    void loadCatalog()
    void loadReport()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!initialReportKey || initialReportKey === appliedInitialReport) return
    const exists = reports.some((report) => report.key === initialReportKey)
    if (!exists) return
    const nextReportKey = initialReportKey as LegacyReportKey
    setAppliedInitialReport(initialReportKey)
    setReportKey(nextReportKey)
    setEstado('')
    setData(null)
    void loadReport(nextReportKey, '')
  }, [appliedInitialReport, initialReportKey, reports])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{heading}</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Reporteria</span>
            </div>
          </div>
        </div>
      </header>

      {!directReportMode ? (
        <section className="student-grid student-grid--stats matricula-stats-grid">
          <article className="student-card student-card--stat matricula-stat-card">
            <p>Consultas disponibles</p>
            <h2>{formatNumber(reports.length)}</h2>
          </article>
          <article className="student-card student-card--stat matricula-stat-card">
            <p>Filas consultadas</p>
            <h2>{formatNumber(data?.total)}</h2>
          </article>
          <article className="student-card student-card--stat matricula-stat-card">
            <p>Columnas</p>
            <h2>{formatNumber(columns.length)}</h2>
          </article>
          <article className="student-card student-card--stat matricula-stat-card">
            <p>Fuentes SQL</p>
            <h2>{formatNumber(sourceTables.length)}</h2>
          </article>
        </section>
      ) : null}

      <section className={`student-grid student-grid--content reporteria-integral-grid ${directReportMode ? 'reporteria-integral-grid--single' : ''}`}>
        <article className="student-card student-card--wide reporteria-integral-panel">
          <div className="card-head">
            <h3>Consulta y exportacion</h3>
            <span>{catalogLoading ? 'Cargando catalogo...' : selectedReport?.category || 'Reporte'}</span>
          </div>

          {individualMode && !directReportMode ? (
            <div className="reporteria-individual-list">
              {reports.map((report) => (
                <button
                  key={report.key}
                  type="button"
                  className={report.key === reportKey ? 'reporteria-individual-list__item reporteria-individual-list__item--active' : 'reporteria-individual-list__item'}
                  onClick={() => {
                    setReportKey(report.key)
                    setEstado('')
                    setData(null)
                    void loadReport(report.key, '')
                  }}
                >
                  <strong>{report.title}</strong>
                  <span>{report.category || 'Reporte'}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className={`matricula-acad-form reporteria-integral-form ${directReportMode ? 'reporteria-integral-form--direct' : ''}`}>
            {!directReportMode ? (
              <label>
                <span>Consulta</span>
                <select
                  value={reportKey}
                  onChange={(event) => {
                    setReportKey(event.target.value as LegacyReportKey)
                    setEstado('')
                  }}
                >
                  {reports.map((report) => (
                    <option key={report.key} value={report.key}>
                      {report.title}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('periodo') ? (
              <label>
                <span>Periodo</span>
                {periodOptions.length > 0 ? (
                  <select value={periodo} onChange={(event) => setPeriodo(event.target.value)}>
                    <option value="">Todos los periodos</option>
                    {periodOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input value={periodo} onChange={(event) => setPeriodo(event.target.value)} placeholder="Codigo periodo" />
                )}
              </label>
            ) : null}
            {enabledFilters.has('carrera') ? (
              <label>
                <span>Carrera</span>
                {careerOptions.length > 0 ? (
                  <select value={carrera} onChange={(event) => setCarrera(event.target.value)}>
                    <option value="">Todas las carreras</option>
                    {careerOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input value={carrera} onChange={(event) => setCarrera(event.target.value)} placeholder="Codigo carrera" />
                )}
              </label>
            ) : null}
            {enabledFilters.has('estado') ? (
              <label>
                <span>Estado</span>
                <select value={estado} onChange={(event) => setEstado(event.target.value)} disabled={estadoOptions.length === 0}>
                  <option value="">Todos</option>
                  {estadoOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('buscar') ? (
              <label>
                <span>Buscar</span>
                <input value={buscar} onChange={(event) => setBuscar(event.target.value)} placeholder="Nombre, cedula o materia" />
              </label>
            ) : null}
            {enabledFilters.has('limite') ? (
              <label>
                <span>Limite</span>
                <input
                  type="number"
                  min={1}
                  max={10000}
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value) || 500)}
                />
              </label>
            ) : null}
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void loadReport()} disabled={loading}>
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
            <button type="button" onClick={() => void exportReport()} disabled={downloadLoading || loading}>
              {downloadLoading ? 'Exportando...' : 'Exportar Excel'}
            </button>
          </div>

          {!directReportMode && selectedReport?.description ? <p className="reporteria-integral-description">{selectedReport.description}</p> : null}
          {!directReportMode && activeFilters.length > 0 ? <p className="teams-message">{activeFilters.join(' / ')}</p> : null}
          {error ? <p className="teams-error">{error}</p> : null}

          {reportKey === 'becas_edades' && ageRangeSummary.length > 0 ? (
            <div className="reporteria-age-chart" aria-label="Comparativo por rangos de edad">
              <div className="reporteria-age-chart__head">
                <div>
                  <strong>Comparativo por rangos de edad</strong>
                  <span>{formatNumber(rows.length)} estudiante(s) con edad calculada o pendiente</span>
                </div>
                <small>Barras por total, con lectura de becados y sin beca</small>
              </div>
              <div className="reporteria-age-chart__rows">
                {ageRangeSummary.map((item) => {
                  const width = `${Math.max((item.total / ageRangeMaxTotal) * 100, 4)}%`
                  const averageScholarship = item.scholarship > 0 ? item.scholarshipPercentTotal / item.scholarship : 0
                  return (
                    <div key={item.range} className="reporteria-age-chart__row">
                      <div className="reporteria-age-chart__label">
                        <strong>{item.range}</strong>
                        <span>{formatNumber(item.total)} estudiante(s)</span>
                      </div>
                      <div className="reporteria-age-chart__bar" aria-hidden="true">
                        <span style={{ width }} />
                      </div>
                      <div className="reporteria-age-chart__meta">
                        <span>Becados {formatNumber(item.scholarship)}</span>
                        <span>Sin beca {formatNumber(item.withoutScholarship)}</span>
                        <span>Prom. beca {averageScholarship.toFixed(1)}%</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}

          {!directReportMode ? (
            <div className="reporteria-integral-source-list">
              {sourceTables.map((source) => (
                <span key={source}>{source}</span>
              ))}
            </div>
          ) : null}

          <div className="excel-toolbar">
            <label>
              <span>Filtrar tabla</span>
              <input
                value={tableFilter}
                onChange={(event) => setTableFilter(event.target.value)}
                placeholder="Buscar dentro del resultado"
              />
            </label>
            <div>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <span>de {formatNumber(rows.length)} fila(s)</span>
            </div>
            <small>{formatNumber(columns.length)} columna(s) visibles</small>
          </div>

          <div className="matricula-table-wrap reporteria-integral-table-wrap excel-table-wrap">
            <table className="matricula-table reporteria-integral-table">
              <thead>
                <tr>
                  <th>#</th>
                  {columns.length > 0 ? (
                    columns.map((column) => <th key={column}>{columnLabel(column)}</th>)
                  ) : (
                    <th>Reporte</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? (
                  visibleRows.map((row, rowIndex) => (
                    <tr key={`legacy-report-row-${rowIndex}`}>
                      <td>{rowIndex + 1}</td>
                      {columns.map((column) => (
                        <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>
                      ))}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={Math.max(columns.length + 1, 2)}>
                      {loading ? 'Consultando informacion...' : 'Sin datos para los filtros seleccionados.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>

        {!directReportMode ? (
          <article className="student-card reporteria-integral-panel reporteria-integral-inventory">
            <div className="card-head">
                  <h3>Areas disponibles</h3>
              <span>{formatNumber(inventory.length)} bloque(s)</span>
            </div>

            {inventory.length > 0 ? (
              inventory.map((item) => (
                <div key={item.module} className="reporteria-integral-inventory-item">
                  <strong>{item.module}</strong>
                  <p>{(item.capabilities || []).join(' / ')}</p>
                  <small>{(item.legacy_sources || []).join(', ')}</small>
                </div>
              ))
            ) : (
              <p className="empty-block">El inventario se cargara desde el backend.</p>
            )}
          </article>
        ) : null}
      </section>
    </>
  )
}
