import { useEffect, useMemo, useState } from 'react'

import {
  downloadLegacyReportWorkbook,
  fetchLegacyReport,
  fetchLegacyReportsCatalog,
} from '../../lib/api'
import type {
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
    key: 'provincia',
    title: 'Provincia',
    category: 'Reportería R/H',
    description: 'Totales por provincia separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'Provincias'],
    filters: ['anio', 'estado', 'buscar', 'limite'],
  },
  {
    key: 'provincia_genero',
    title: 'Provincia por género',
    category: 'Reportería R/H',
    description: 'Consolidado por provincia y género separado en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias', 'Sexo'],
    filters: ['anio', 'estado', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'provincia_carrera',
    title: 'Provincia por carreras',
    category: 'Reportería R/H',
    description: 'Consolidado por provincia y carrera separado en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias'],
    filters: ['anio', 'estado', 'carrera', 'buscar', 'limite'],
  },
  {
    key: 'carrera',
    title: 'Carrera',
    category: 'Reportería R/H',
    description: 'Totales por carrera separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS'],
    filters: ['anio', 'estado', 'carrera', 'buscar', 'limite'],
  },
  {
    key: 'graduados_2025',
    title: 'Graduados',
    category: 'Reportería R/H',
    description: 'Listado de graduados por año, provincia, carrera y género.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias', 'ESTADO'],
    filters: ['anio', 'estado', 'carrera', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'genero',
    title: 'Género',
    category: 'Reportería R/H',
    description: 'Distribución por género separada en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'Sexo'],
    filters: ['anio', 'estado', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'periodo',
    title: 'Período',
    category: 'Reportería R/H',
    description: 'Totales por período separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Sexo'],
    filters: ['anio', 'estado', 'carrera', 'genero', 'buscar', 'limite'],
  },
]

const fallbackYearOptions: LegacyReportOption[] = [
  { value: '', label: 'Todos' },
  { value: '2026', label: '2026' },
  { value: '2025', label: '2025' },
  { value: '2024', label: '2024' },
  { value: '2023', label: '2023' },
]
const studentEstadoOptions: LegacyReportOption[] = [
  { value: '', label: 'Todos los estados' },
  { value: 'A', label: 'Activo' },
  { value: 'G', label: 'Graduado' },
  { value: 'P', label: 'Inactivo' },
  { value: 'R', label: 'Retirado' },
]
const genderOptions = [
  { value: '', label: 'Todos los géneros' },
  { value: 'Masculino', label: 'Masculino' },
  { value: 'Femenino', label: 'Femenino' },
]

function defaultEstadoForReport(reportKey: LegacyReportKey): string {
  return reportKey === 'graduados_2025' ? 'G' : ''
}

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
  const labels: Record<string, string> = {
    anio: 'Año',
    periodo: 'Período',
    periodo_codigo: 'Código período',
    genero: 'Género',
    cedula: 'Cédula',
  }
  if (labels[column]) return labels[column]
  return column
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (value) => value.toUpperCase())
}

function cellNumber(value: LegacyReportRow[string]): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const parsed = Number(String(value ?? '').replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

function isTotalColumn(column: string): boolean {
  const normalized = column.toLowerCase()
  if (normalized.includes('codigo') || normalized.includes('cedula') || normalized === 'anio') return false
  return (
    normalized === 'regular' ||
    normalized === 'homologacion' ||
    normalized === 'total' ||
    normalized === 'cantidad' ||
    normalized === 'graduados' ||
    normalized.startsWith('total_') ||
    normalized.endsWith('_total') ||
    normalized.includes('total_estudiantes')
  )
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
  const [periodOptions, setPeriodOptions] = useState<LegacyReportOption[]>([])
  const [careerOptions, setCareerOptions] = useState<LegacyReportOption[]>([])
  const [yearOptions, setYearOptions] = useState<LegacyReportOption[]>(fallbackYearOptions)
  const [reportKey, setReportKey] = useState<LegacyReportKey>(
    (initialReportKey as LegacyReportKey) || 'provincia_genero',
  )
  const [appliedInitialReport, setAppliedInitialReport] = useState('')
  const [anio, setAnio] = useState('')
  const [periodos, setPeriodos] = useState<string[]>([])
  const [carrera, setCarrera] = useState('')
  const [estado, setEstado] = useState(defaultEstadoForReport((initialReportKey as LegacyReportKey) || 'provincia_genero'))
  const [genero, setGenero] = useState('')
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
    () => new Set(selectedReport?.filters?.length ? selectedReport.filters : ['anio', 'carrera', 'genero', 'buscar', 'limite']),
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
  const totalsRow = useMemo(() => {
    if (!visibleRows.length || !columns.length) return null
    const totals: Record<string, number> = {}
    let hasTotals = false

    for (const column of columns) {
      if (!isTotalColumn(column)) continue
      const columnTotal = visibleRows.reduce((sum, row) => sum + cellNumber(row[column]), 0)
      totals[column] = columnTotal
      hasTotals = true
    }

    return hasTotals ? totals : null
  }, [columns, visibleRows])
  const totalSummaryItems = useMemo(
    () =>
      totalsRow
        ? columns
            .filter((column) => isTotalColumn(column))
            .map((column) => ({
              key: column,
              label: columnLabel(column),
              value: totalsRow[column] ?? 0,
            }))
        : [],
    [columns, totalsRow],
  )
  const sourceTables = selectedReport?.source_tables || []
  const estadoOptions = selectedReport?.estado_options?.length ? selectedReport.estado_options : studentEstadoOptions
  const estadoLabel = estadoOptions.find((option) => option.value === estado)?.label || estado
  const selectedPeriodLabels = useMemo(
    () =>
      periodos.map((value) => periodOptions.find((option) => option.value === value)?.label || value),
    [periodOptions, periodos],
  )
  const activeFilters = [
    enabledFilters.has('anio') ? `Año ${anio || 'Todos'}` : '',
    enabledFilters.has('periodo') && periodos.length === 1 ? `Período ${selectedPeriodLabels[0]}` : '',
    enabledFilters.has('periodo') && periodos.length > 1 ? `${periodos.length} períodos seleccionados` : '',
    enabledFilters.has('carrera') && carrera ? `Carrera ${careerOptions.find((option) => option.value === carrera)?.label || carrera}` : '',
    enabledFilters.has('estado') && estado ? `Estado ${estadoLabel}` : '',
    enabledFilters.has('genero') ? `Género ${genero || 'Todos'}` : '',
    enabledFilters.has('buscar') && buscar ? `Búsqueda "${buscar}"` : '',
  ].filter(Boolean)

  function filtersForReport(nextReportKey: LegacyReportKey) {
    const report = reports.find((item) => item.key === nextReportKey) || selectedReport
    return new Set(report?.filters?.length ? report.filters : ['anio', 'carrera', 'genero', 'buscar', 'limite'])
  }

  function filters(nextReportKey: LegacyReportKey = reportKey, nextEstado: string = estado): LegacyReportFilters {
    const nextEnabledFilters = filtersForReport(nextReportKey)
    return {
      reportKey: nextReportKey,
      anio: nextEnabledFilters.has('anio') ? anio.trim() : '',
      periodo: nextEnabledFilters.has('periodo') && periodos.length === 1 ? periodos[0] : '',
      periodos: nextEnabledFilters.has('periodo') ? periodos : [],
      carrera: nextEnabledFilters.has('carrera') ? carrera.trim() : '',
      estado: nextEnabledFilters.has('estado') ? nextEstado.trim() : '',
      genero: nextEnabledFilters.has('genero') ? genero.trim() : '',
      buscar: nextEnabledFilters.has('buscar') ? buscar.trim() : '',
      limit,
    }
  }

  function validateFiltersForReport(nextReportKey: LegacyReportKey) {
    if (nextReportKey === 'estud_per_c_m' && periodos.length === 0) {
      return 'Selecciona un periodo para consultar estudiantes, carreras y materias matriculadas.'
    }
    return ''
  }

  function togglePeriod(value: string) {
    setPeriodos((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    )
  }

  function selectAllPeriods() {
    setPeriodos(periodOptions.map((option) => option.value))
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
        setPeriodOptions(payload.periodos || [])
        setCareerOptions(payload.carreras || [])
        const catalogYears = (payload.anios || [])
          .filter((option) => option.value)
          .map((option) => ({ value: option.value, label: option.label || option.value }))
        setYearOptions(catalogYears.length ? [{ value: '', label: 'Todos' }, ...catalogYears] : fallbackYearOptions)
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
    setAnio('')
    const nextEstado = defaultEstadoForReport(nextReportKey)
    setEstado(nextEstado)
    setGenero('')
    setData(null)
    void loadReport(nextReportKey, nextEstado)
  }, [appliedInitialReport, initialReportKey, reports])

  useEffect(() => {
    if (reportKey !== 'graduados_2025') return
    const timeout = window.setTimeout(() => {
      void loadReport('graduados_2025', estado)
    }, 250)

    return () => window.clearTimeout(timeout)
  }, [reportKey, anio, carrera, genero, estado])

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
                    setAnio('')
                    const nextEstado = defaultEstadoForReport(report.key)
                    setEstado(nextEstado)
                    setGenero('')
                    setData(null)
                    void loadReport(report.key, nextEstado)
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
                    const nextReportKey = event.target.value as LegacyReportKey
                    setReportKey(nextReportKey)
                    setAnio('')
                    setEstado(defaultEstadoForReport(nextReportKey))
                    setGenero('')
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
            {enabledFilters.has('anio') ? (
              <label className="reporteria-year-filter">
                <span>Año</span>
                <select value={anio} onChange={(event) => setAnio(event.target.value)}>
                  {yearOptions.map((option) => (
                    <option key={option.value || 'todos'} value={option.value}>
                      {option.label || option.value || 'Todos'}
                    </option>
                  ))}
                </select>
                <small>{anio ? `Año seleccionado: ${anio}` : 'Año seleccionado: Todos'}</small>
              </label>
            ) : null}
            {enabledFilters.has('periodo') ? (
              <label>
                <span>Periodo</span>
                {periodOptions.length > 0 ? (
                  <div className="report-period-picker">
                    <div className="report-period-toolbar">
                      <strong>{periodos.length ? `${periodos.length} seleccionado(s)` : 'Todos los períodos'}</strong>
                      <button type="button" onClick={selectAllPeriods}>
                        Seleccionar todos
                      </button>
                      <button type="button" onClick={() => setPeriodos([])}>
                        Limpiar
                      </button>
                    </div>
                    <div className="report-period-options">
                      {periodOptions.map((option) => (
                        <label key={option.value} className="report-period-option">
                          <input
                            type="checkbox"
                            checked={periodos.includes(option.value)}
                            onChange={() => togglePeriod(option.value)}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : (
                  <textarea
                    value={periodos.join('\n')}
                    onChange={(event) =>
                      setPeriodos(event.target.value.split(/[\n,]+/).map((value) => value.trim()).filter(Boolean))
                    }
                    placeholder="Códigos de período, uno por línea"
                  />
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
                <select value={estado} onChange={(event) => setEstado(event.target.value)}>
                  <option value="">Todos</option>
                  {estadoOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('genero') ? (
              <label>
                <span>Género</span>
                <select value={genero} onChange={(event) => setGenero(event.target.value)}>
                  {genderOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('buscar') ? (
              <label>
                <span>Buscar</span>
                <input value={buscar} onChange={(event) => setBuscar(event.target.value)} placeholder="Cédula, estudiante, provincia, carrera o período" />
              </label>
            ) : null}
            {enabledFilters.has('limite') ? (
              <label>
                <span>Límite</span>
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

          <div className="reporteria-total-summary" aria-label="Totales del resultado filtrado">
            <div className="reporteria-total-summary__lead">
              <span>Total del resultado</span>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <small>{visibleRows.length === 1 ? 'fila filtrada' : 'filas filtradas'}</small>
            </div>
            {totalSummaryItems.length > 0 ? (
              <div className="reporteria-total-summary__items">
                {totalSummaryItems.map((item) => (
                  <div key={item.key} className="reporteria-total-summary__item">
                    <span>{item.label}</span>
                    <strong>{formatCell(item.value)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <small className="reporteria-total-summary__empty">
                El resultado actual no tiene columnas numericas para totalizar.
              </small>
            )}
          </div>

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
              {totalsRow ? (
                <tfoot>
                  <tr>
                    <td>Total</td>
                    {columns.map((column) => (
                      <td key={`total-${column}`} className={isTotalColumn(column) ? 'reporteria-total-cell' : undefined}>
                        {isTotalColumn(column) ? formatCell(totalsRow[column] ?? 0) : ''}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
        </article>

      </section>
    </>
  )
}
