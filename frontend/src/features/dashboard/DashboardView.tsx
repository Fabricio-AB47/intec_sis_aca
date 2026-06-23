import { useState, type CSSProperties } from 'react'

import { fetchDashboardMatriculaTrendStudents, fetchMatriculaList } from '../../lib/api'
import type { DashboardMatriculaResponse, DashboardMatriculaStateItem, MatriculaStudentItem } from '../../types/app'

type DashboardViewProps = {
  displayName: string
  error: string
  data: DashboardMatriculaResponse | null
}

const activeTypeColors: Record<string, string> = {
  R: '#1f6f8b',
  H: '#931913',
}

const stateColors: Record<string, string> = {
  A: '#1f6f8b',
  G: '#5c7c35',
  P: '#d19a2a',
  R: '#9b2d25',
}

const dashboardStateCodes = new Set(['A', 'G', 'P', 'R'])
const dashboardIgnoredCedulas = new Set(['1708531189'])

const monthLabels = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const trendLineColors = ['#1f6f8b', '#7a5aa6', '#d19a2a', '#5c7c35', '#9b2d25', '#8dbbc7']
const trendChartWidth = 1200
const trendChartBaseY = 285
const trendChartTopY = 34
const trendChartPaddingX = 66
const trendGridLevels = [0, 0.25, 0.5, 0.75, 1]

function trendColorStyle(color: string): CSSProperties {
  return { '--trend-color': color } as CSSProperties
}

type TrendPoint = {
  anio: number
  mes: number
  periodo_mes: string
  mes_nombre: string
  total_estudiantes: number
}

type TrendCoordinate = {
  x: number
  y: number
}

type ActiveTypeItem = {
  tipo_matricula: 'R' | 'H'
  label: string
  total_estudiantes: number
}

type PieSegment = {
  key: string
  dasharray: string
  dashoffset: number
  color: string
}

function buildTrendCoordinates(values: number[], maxValue?: number): TrendCoordinate[] {
  const max = Math.max(maxValue ?? Math.max(...values, 1), 1)
  const spanX = trendChartWidth - trendChartPaddingX * 2
  const spanY = trendChartBaseY - trendChartTopY

  return values
    .map((value, index) => {
      const x = values.length === 1 ? trendChartWidth / 2 : trendChartPaddingX + (spanX * index) / (values.length - 1)
      const y = trendChartBaseY - (spanY * value) / max
      return { x, y }
    })
}

function buildSmoothPath(points: TrendCoordinate[]): string {
  if (points.length === 0) return ''
  if (points.length === 1) return `M ${points[0].x},${points[0].y}`

  const [first] = points
  let path = `M ${first.x},${first.y}`
  for (let index = 0; index < points.length - 1; index += 1) {
    const previous = points[index - 1] || points[index]
    const current = points[index]
    const next = points[index + 1]
    const afterNext = points[index + 2] || next
    const controlOneX = current.x + (next.x - previous.x) / 6
    const controlOneY = current.y + (next.y - previous.y) / 6
    const controlTwoX = next.x - (afterNext.x - current.x) / 6
    const controlTwoY = next.y - (afterNext.y - current.y) / 6
    path += ` C ${controlOneX},${controlOneY} ${controlTwoX},${controlTwoY} ${next.x},${next.y}`
  }
  return path
}

function buildAreaPath(points: TrendCoordinate[]): string {
  if (points.length === 0) return ''
  const first = points[0]
  const last = points[points.length - 1]
  return `${buildSmoothPath(points)} L ${last.x},${trendChartBaseY} L ${first.x},${trendChartBaseY} Z`
}

function pieSegments(items: Array<{ key: string; total_estudiantes: number; color: string }>): PieSegment[] {
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const total = items.reduce((sum, item) => sum + item.total_estudiantes, 0)
  let offset = 0
  return items
    .filter((item) => item.total_estudiantes > 0)
    .map((item) => {
      const size = total > 0 ? (item.total_estudiantes / total) * circumference : 0
      const segment = {
        key: item.key,
        dasharray: `${size} ${circumference - size}`,
        dashoffset: -offset,
        color: item.color,
      }
      offset += size
      return segment
    })
}

function statePercent(value: number, total: number): string {
  if (total <= 0) return '0%'
  return `${((value / total) * 100).toFixed(1)}%`
}

function formatTrendAxisValue(value: number): string {
  if (value >= 1000) {
    const formatted = value % 1000 === 0 ? String(value / 1000) : (value / 1000).toFixed(1)
    return `${formatted}k`
  }
  return String(Math.round(value))
}

function isDashboardVisibleStudent(student: MatriculaStudentItem): boolean {
  const cedula = String(student.cedula || '').replace(/\D+/g, '')
  return !dashboardIgnoredCedulas.has(cedula)
}

function buildMonthlyTrend(
  trend: DashboardMatriculaResponse['trend'],
  selectedYear: 'ALL' | number
): TrendPoint[] {
  const source = trend || []
  return monthLabels.map((label, index) => {
    const month = index + 1
    const total = source
      .filter((item) => item.mes === month && (selectedYear === 'ALL' || item.anio === selectedYear))
      .reduce((sum, item) => sum + item.total_estudiantes, 0)
    return {
      anio: selectedYear === 'ALL' ? 0 : selectedYear,
      mes: month,
      periodo_mes: selectedYear === 'ALL' ? `ALL-${String(month).padStart(2, '0')}` : `${selectedYear}-${String(month).padStart(2, '0')}`,
      mes_nombre: label,
      total_estudiantes: total,
    }
  })
}

export function DashboardView({
  displayName,
  error,
  data,
}: Readonly<DashboardViewProps>) {
  const [selectedTrendPoint, setSelectedTrendPoint] = useState<TrendPoint | null>(null)
  const [selectedTrendYear, setSelectedTrendYear] = useState<'ALL' | number>('ALL')
  const [selectedDistributionYear, setSelectedDistributionYear] = useState<number | null>(null)
  const [selectedState, setSelectedState] = useState<DashboardMatriculaStateItem | null>(null)
  const [stateStudents, setStateStudents] = useState<MatriculaStudentItem[]>([])
  const [stateStudentsLoading, setStateStudentsLoading] = useState(false)
  const [stateStudentsError, setStateStudentsError] = useState('')
  const [selectedActiveType, setSelectedActiveType] = useState<ActiveTypeItem | null>(null)
  const [activeTypeStudents, setActiveTypeStudents] = useState<MatriculaStudentItem[]>([])
  const [activeTypeStudentsLoading, setActiveTypeStudentsLoading] = useState(false)
  const [activeTypeStudentsError, setActiveTypeStudentsError] = useState('')
  const [trendStudents, setTrendStudents] = useState<MatriculaStudentItem[]>([])
  const [trendStudentsLoading, setTrendStudentsLoading] = useState(false)
  const [trendStudentsError, setTrendStudentsError] = useState('')
  const trend = data?.trend || []
  const trendYears = [...new Set(trend.map((item) => item.anio))].sort((left, right) => left - right)
  const trendYearColors = new Map(trendYears.map((year, index) => [year, trendLineColors[index % trendLineColors.length]]))
  const getTrendYearColor = (year: number) => trendYearColors.get(year) || trendLineColors[0]
  const currentYear = new Date().getFullYear()
  const latestTrendYear = trendYears[trendYears.length - 1] ?? currentYear
  const defaultDistributionYear = trendYears.includes(currentYear) ? currentYear : latestTrendYear
  const distributionYear = selectedDistributionYear && trendYears.includes(selectedDistributionYear)
    ? selectedDistributionYear
    : defaultDistributionYear
  const visibleTrend = buildMonthlyTrend(trend, selectedTrendYear)
  const distributionTrend = buildMonthlyTrend(trend, distributionYear)
  const states = (data?.states || []).filter((item) => dashboardStateCodes.has(item.estado_codigo))
  const totalStudents = states.reduce((sum, item) => sum + item.total_estudiantes, 0)
  const trendSeries = selectedTrendYear === 'ALL'
    ? trendYears.map((year) => ({
        year,
        color: getTrendYearColor(year),
        items: buildMonthlyTrend(trend, year),
      }))
    : [{
        year: selectedTrendYear,
        color: getTrendYearColor(selectedTrendYear),
        items: visibleTrend,
      }]
  const trendMax = Math.max(...trendSeries.flatMap((series) => series.items.map((item) => item.total_estudiantes)), 1)
  const activeStudents = states.find((item) => item.estado_codigo === 'A')?.total_estudiantes ?? 0
  const activeByType = data?.active_by_type || []
  const rawActiveRegularStudents = data?.active_regular_students
    ?? activeByType.find((item) => item.tipo_matricula === 'R')?.total_estudiantes
    ?? 0
  const rawActiveHomologationStudents = data?.active_homologation_students
    ?? activeByType.find((item) => item.tipo_matricula === 'H')?.total_estudiantes
    ?? 0
  const rawActiveSplit = rawActiveRegularStudents + rawActiveHomologationStudents
  const activeRhStudents = activeStudents
  const activeRegularStudents = activeRhStudents > 0 && rawActiveSplit > 0 && rawActiveSplit !== activeRhStudents
    ? Math.min(activeRhStudents, Math.round((rawActiveRegularStudents / rawActiveSplit) * activeRhStudents))
    : Math.min(rawActiveRegularStudents, activeRhStudents)
  const activeHomologationStudents = Math.max(0, activeRhStudents - activeRegularStudents)
  const activeTypeItems: ActiveTypeItem[] = [
    { tipo_matricula: 'R', label: 'Regular', total_estudiantes: activeRegularStudents },
    { tipo_matricula: 'H', label: 'Homologación', total_estudiantes: activeHomologationStudents },
  ]
  const stateSegments = pieSegments(
    states.map((item) => ({
      key: item.estado_codigo,
      total_estudiantes: item.total_estudiantes,
      color: stateColors[item.estado_codigo] || '#8dbbc7',
    }))
  )
  const currentYearTrend = buildMonthlyTrend(trend, currentYear)
  const peakMonth = currentYearTrend.reduce(
    (best, item) => (item.total_estudiantes > best.total_estudiantes ? item : best),
    currentYearTrend[0] || { mes_nombre: '-', total_estudiantes: 0 }
  )
  const peakMonthDetail = peakMonth.total_estudiantes > 0 ? `${peakMonth.mes_nombre} ${currentYear}` : `Sin datos ${currentYear}`
  const monthBarMax = Math.max(...distributionTrend.map((item) => item.total_estudiantes), 1)
  const metricCards = [
    { label: 'Total estudiantes', value: totalStudents, detail: 'Estados reales A/G/P/R', tone: 'red' },
    {
      label: 'Activos R + H',
      value: activeRhStudents,
      detail: `R ${activeRegularStudents} + H ${activeHomologationStudents}`,
      tone: 'cyan',
    },
    { label: 'Activos', value: activeStudents, detail: statePercent(activeStudents, totalStudents), tone: 'cyan' },
    { label: 'Mes mayor', value: peakMonth.total_estudiantes, detail: peakMonthDetail, tone: 'gold' },
  ]

  async function openActiveTypeStudents(item: ActiveTypeItem) {
    setSelectedActiveType(item)
    setActiveTypeStudents([])
    setActiveTypeStudentsError('')
    setActiveTypeStudentsLoading(true)
    try {
      const response = await fetchMatriculaList(item.tipo_matricula, 'A', 10000)
      setActiveTypeStudents((response.items || []).filter(isDashboardVisibleStudent))
    } catch (apiError) {
      setActiveTypeStudentsError(apiError instanceof Error ? apiError.message : 'Error consultando estudiantes activos')
    } finally {
      setActiveTypeStudentsLoading(false)
    }
  }

  async function openStateStudents(item: DashboardMatriculaStateItem) {
    setSelectedState(item)
    setStateStudents([])
    setStateStudentsError('')
    setStateStudentsLoading(true)
    try {
      const response = await fetchMatriculaList('ALL', item.estado_codigo, 10000)
      setStateStudents((response.items || []).filter(isDashboardVisibleStudent))
    } catch (apiError) {
      setStateStudentsError(apiError instanceof Error ? apiError.message : 'Error consultando estudiantes por estado')
    } finally {
      setStateStudentsLoading(false)
    }
  }

  async function openTrendStudents(item: TrendPoint) {
    if (item.anio <= 0) return
    setSelectedTrendPoint(item)
    setTrendStudents([])
    setTrendStudentsError('')
    setTrendStudentsLoading(true)
    try {
      const response = await fetchDashboardMatriculaTrendStudents(item.anio, item.mes, 10000)
      setTrendStudents((response.items || []).filter(isDashboardVisibleStudent))
    } catch (apiError) {
      setTrendStudentsError(apiError instanceof Error ? apiError.message : 'Error consultando estudiantes del mes')
    } finally {
      setTrendStudentsLoading(false)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Panel academico</p>
          <h1>Dashboard Estudiantil</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Dashboard</span>
            </div>
          </div>
        </div>
      </header>

      {error ? <p className="teams-error">{error}</p> : null}

      <section className="dashboard-executive-grid">
        <article className="student-card dashboard-trend-panel">
          <div className="card-head">
            <h3>Tendencia por fecha de inicio</h3>
          </div>

          <div className="dashboard-year-filters">
            <button
              type="button"
              className={selectedTrendYear === 'ALL' ? 'dashboard-year-filter--active' : ''}
              onClick={() => setSelectedTrendYear('ALL')}
            >
              Todos
            </button>
            {trendYears.map((year) => (
              <button
                key={year}
                type="button"
                className={`dashboard-year-filter--year ${
                  selectedTrendYear === year ? 'dashboard-year-filter--active' : ''
                }`}
                style={trendColorStyle(getTrendYearColor(year))}
                onClick={() => setSelectedTrendYear(year)}
              >
                {year}
              </button>
            ))}
          </div>

          <div className="dashboard-line-chart">
            {trendSeries.length > 0 ? (
              <svg viewBox="0 0 1200 360" role="img" aria-label="Tendencia mensual de estudiantes">
                <defs>
                  {trendSeries.map((series) => (
                    <linearGradient key={series.year} id={`trendGradient-${series.year}`} x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor={series.color} stopOpacity="0.30" />
                      <stop offset="68%" stopColor={series.color} stopOpacity="0.11" />
                      <stop offset="100%" stopColor={series.color} stopOpacity="0.01" />
                    </linearGradient>
                  ))}
                </defs>
                <rect x="0" y="0" width="1200" height="360" className="dashboard-chart-surface" />
                {trendGridLevels.map((level) => {
                  const y = trendChartBaseY - (trendChartBaseY - trendChartTopY) * level
                  return (
                    <g key={`h-${level}`}>
                      <line
                        x1={trendChartPaddingX}
                        y1={y}
                        x2="1146"
                        y2={y}
                        className="dashboard-grid-line"
                      />
                      <text x="16" y={y + 4} className="dashboard-axis-label">
                        {formatTrendAxisValue(trendMax * level)}
                      </text>
                    </g>
                  )
                })}
                {monthLabels.map((label, index) => {
                  const x = monthLabels.length === 1
                    ? trendChartWidth / 2
                    : trendChartPaddingX + ((trendChartWidth - trendChartPaddingX * 2) * index) / (monthLabels.length - 1)
                  return (
                    <g key={label}>
                      <line x1={x} y1={trendChartTopY} x2={x} y2={trendChartBaseY} className="dashboard-grid-line" />
                      <text x={x} y="328" className="dashboard-month-axis-label">
                        {label}
                      </text>
                    </g>
                  )
                })}
                <line x1={trendChartPaddingX} y1={trendChartBaseY} x2="1146" y2={trendChartBaseY} className="dashboard-axis" />
                <line x1={trendChartPaddingX} y1={trendChartTopY} x2={trendChartPaddingX} y2={trendChartBaseY} className="dashboard-axis" />
                {trendSeries.map((series) => {
                  const coordinates = buildTrendCoordinates(series.items.map((item) => item.total_estudiantes), trendMax)
                  const linePath = buildSmoothPath(coordinates)
                  const areaPath = buildAreaPath(coordinates)
                  return (
                    <g key={series.year}>
                      <path
                        d={areaPath}
                        className="dashboard-area"
                        style={{ fill: `url(#trendGradient-${series.year})` }}
                      />
                      <path d={linePath} className="dashboard-line" style={{ stroke: series.color }} />
                      {coordinates.map(({ x, y }, index) => {
                        const item = series.items[index]
                        return (
                          <g
                            key={item.periodo_mes}
                            className="dashboard-trend-point"
                            role="button"
                            tabIndex={0}
                            onClick={() => void openTrendStudents(item)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                void openTrendStudents(item)
                              }
                            }}
                          >
                            <circle cx={x} cy={y} r="5" className="dashboard-point" style={{ stroke: series.color }} />
                            {item.total_estudiantes > 0 ? (
                              <text x={x} y={y - 12} className="dashboard-point-label" style={{ fill: series.color }}>
                                {item.total_estudiantes}
                              </text>
                            ) : null}
                          </g>
                        )
                      })}
                    </g>
                  )
                })}
              </svg>
            ) : (
              <p className="empty-block">Sin datos mensuales para graficar.</p>
            )}
          </div>

          {selectedTrendYear === 'ALL' ? (
            <div className="dashboard-trend-legend">
              {trendSeries.map((series) => (
                <span key={series.year}>
                  <i style={{ backgroundColor: series.color }} />
                  {series.year}
                </span>
              ))}
            </div>
          ) : null}

        </article>

        <article className="student-card dashboard-summary-panel">
          <div className="card-head">
            <h3>Resumen de matricula</h3>
            <span>Activos R {activeRegularStudents} + H {activeHomologationStudents}</span>
          </div>

          <div className="dashboard-metric-tiles">
            {metricCards.map((item) => (
              <div key={item.label} className={`dashboard-metric-tile dashboard-metric-tile--${item.tone}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.detail}</small>
              </div>
            ))}
          </div>
        </article>

        <div className="dashboard-active-row">
          <article className="student-card dashboard-pie-card">
            <div className="card-head">
              <h3>Estados de estudiantes</h3>
              <span>Total: {totalStudents} · Activos R/H: {activeRhStudents}</span>
            </div>

            <div className="dashboard-active-breakdown dashboard-active-breakdown--top">
              <div>
                <span style={{ backgroundColor: activeTypeColors.R }} />
                <strong>Activos Regular</strong>
                <small>{statePercent(activeRegularStudents, activeRhStudents)} · {activeRegularStudents}</small>
              </div>
              <div>
                <span style={{ backgroundColor: activeTypeColors.H }} />
                <strong>Activos Homologación</strong>
                <small>{statePercent(activeHomologationStudents, activeRhStudents)} · {activeHomologationStudents}</small>
              </div>
            </div>

            <div className="dashboard-pie-content">
              <div className="dashboard-pie-wrap">
                <svg viewBox="0 0 140 140" role="img" aria-label="Distribución de estudiantes por estado">
                  <circle cx="70" cy="70" r="54" className="dashboard-pie-base" />
                  {stateSegments.map((segment) => (
                    <circle
                      key={segment.key}
                      cx="70"
                      cy="70"
                      r="54"
                      className="dashboard-pie-segment"
                      stroke={segment.color}
                      strokeDasharray={segment.dasharray}
                      strokeDashoffset={segment.dashoffset}
                    />
                  ))}
                  <text x="70" y="66" className="dashboard-pie-total">
                    100%
                  </text>
                  <text x="70" y="82" className="dashboard-pie-caption">
                    {totalStudents}
                  </text>
                </svg>
              </div>

              <div className="dashboard-state-list">
                {states.length > 0 ? (
                  states.map((item) => (
                    <button key={item.estado_codigo} type="button" onClick={() => void openStateStudents(item)}>
                      <span style={{ backgroundColor: stateColors[item.estado_codigo] || '#8dbbc7' }} />
                      <strong>{item.estado_nombre}</strong>
                      <small>
                        {statePercent(item.total_estudiantes, totalStudents)} · {item.total_estudiantes}
                      </small>
                    </button>
                  ))
                ) : (
                  <p className="empty-block">Sin estados de estudiantes para mostrar.</p>
                )}
              </div>
            </div>
          </article>

          <article className="student-card dashboard-active-type-card">
            <div className="card-head dashboard-active-type-head">
              <div>
                <h3>Activos R/H</h3>
                <small>Matriculas activas por tipo</small>
              </div>
              <span>{activeRhStudents} activo(s)</span>
            </div>

            <div className="dashboard-active-type-layout">
              <div className="dashboard-active-total-card" aria-label="Total de estudiantes activos regular y homologacion">
                <span>Total activos</span>
                <strong>{activeRhStudents}</strong>
                <small>Regular + Homologación</small>
              </div>

              <div className="dashboard-active-type-grid">
                {activeTypeItems.map((item) => (
                  <button
                    key={item.tipo_matricula}
                    type="button"
                    className="dashboard-active-type-subcard"
                    onClick={() => openActiveTypeStudents(item)}
                  >
                    <span
                      className="dashboard-active-type-dot"
                      style={{ backgroundColor: activeTypeColors[item.tipo_matricula] || '#8dbbc7' }}
                    />
                    <div className="dashboard-active-type-copy">
                      <strong>{item.label}</strong>
                    </div>
                    <div className="dashboard-active-type-value">
                      <strong>{item.total_estudiantes}</strong>
                      <small>{statePercent(item.total_estudiantes, activeRhStudents)}</small>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </article>
        </div>

        <article className="student-card dashboard-bars-card">
          <div className="card-head">
            <h3>Distribucion mensual</h3>
            <span>{distributionYear}</span>
          </div>

          <div className="dashboard-year-filters dashboard-year-filters--compact">
            {trendYears.map((year) => (
              <button
                key={year}
                type="button"
                className={distributionYear === year ? 'dashboard-year-filter--active' : ''}
                onClick={() => setSelectedDistributionYear(year)}
              >
                {year}
              </button>
            ))}
          </div>

          <div className="dashboard-bars">
            {distributionTrend.map((item) => (
              <div key={item.periodo_mes}>
                <span style={{ height: `${Math.max((item.total_estudiantes / monthBarMax) * 100, 3)}%` }} />
                <small>{item.mes_nombre}</small>
                <strong>{item.total_estudiantes}</strong>
              </div>
            ))}
          </div>
        </article>

      </section>

      {selectedState ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal dashboard-active-students-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Estudiantes en estado {selectedState.estado_nombre}</h3>
                <span>
                  {statePercent(selectedState.total_estudiantes, totalStudents)} ·{' '}
                  {selectedState.total_estudiantes} estudiante(s)
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedState(null)
                  setStateStudents([])
                  setStateStudentsError('')
                }}
              >
                Cerrar
              </button>
            </div>

            <div className="dashboard-active-modal-summary">
              <div>
                <span>Estado</span>
                <strong>{selectedState.estado_nombre}</strong>
              </div>
              <div>
                <span>Total</span>
                <strong>{selectedState.total_estudiantes}</strong>
              </div>
              <div>
                <span>Participación</span>
                <strong>{statePercent(selectedState.total_estudiantes, totalStudents)}</strong>
              </div>
            </div>

            {stateStudentsLoading ? <p className="teams-message">Consultando estudiantes...</p> : null}
            {stateStudentsError ? <p className="teams-error">{stateStudentsError}</p> : null}

            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cédula</th>
                    <th>Carrera</th>
                    <th>Período</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Correo personal</th>
                  </tr>
                </thead>
                <tbody>
                  {stateStudents.length > 0 ? (
                    stateStudents.map((student) => (
                      <tr
                        key={`state-${selectedState.estado_codigo}-${student.tipo_matricula}-${student.codigo_estud}-${student.periodo || 'na'}`}
                      >
                        <td>{student.nombre_estudiante}</td>
                        <td>{student.cedula || '-'}</td>
                        <td>{student.nombre_carrera || '-'}</td>
                        <td>{student.detalle_periodo || student.periodo || '-'}</td>
                        <td>{student.tipo_matricula}</td>
                        <td>{student.estado_nombre}</td>
                        <td>{student.correo_personal || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>Sin estudiantes para el estado seleccionado.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : null}

      {selectedActiveType ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal dashboard-active-students-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Activos en {selectedActiveType.label}</h3>
                <span>
                  {statePercent(selectedActiveType.total_estudiantes, activeRhStudents)} ·{' '}
                  {selectedActiveType.total_estudiantes} estudiante(s)
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedActiveType(null)
                  setActiveTypeStudents([])
                  setActiveTypeStudentsError('')
                }}
              >
                Cerrar
              </button>
            </div>

            <div className="dashboard-active-modal-summary">
              <div>
                <span>Tipo de matrícula</span>
                <strong>{selectedActiveType.label}</strong>
              </div>
              <div>
                <span>Total activo</span>
                <strong>{selectedActiveType.total_estudiantes}</strong>
              </div>
              <div>
                <span>Participación</span>
                <strong>{statePercent(selectedActiveType.total_estudiantes, activeRhStudents)}</strong>
              </div>
            </div>

            {activeTypeStudentsLoading ? <p className="teams-message">Consultando estudiantes...</p> : null}
            {activeTypeStudentsError ? <p className="teams-error">{activeTypeStudentsError}</p> : null}

            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cedula</th>
                    <th>Carrera</th>
                    <th>Periodo</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Correo personal</th>
                  </tr>
                </thead>
                <tbody>
                  {activeTypeStudents.length > 0 ? (
                    activeTypeStudents.map((student) => (
                      <tr
                        key={`active-${selectedActiveType.tipo_matricula}-${student.codigo_estud}-${student.periodo || 'na'}`}
                      >
                        <td>{student.nombre_estudiante}</td>
                        <td>{student.cedula || '-'}</td>
                        <td>{student.nombre_carrera || '-'}</td>
                        <td>{student.detalle_periodo || student.periodo || '-'}</td>
                        <td>{student.tipo_matricula}</td>
                        <td>{student.estado_nombre}</td>
                        <td>{student.correo_personal || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>Sin estudiantes activos para {selectedActiveType.label}.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : null}

      {selectedTrendPoint ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Estudiantes por mes</h3>
                <span>
                  {selectedTrendPoint.mes_nombre} {selectedTrendPoint.anio} · {selectedTrendPoint.total_estudiantes}{' '}
                  estudiante(s)
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedTrendPoint(null)
                  setTrendStudents([])
                  setTrendStudentsError('')
                }}
              >
                Cerrar
              </button>
            </div>

            {trendStudentsLoading ? <p className="teams-message">Consultando estudiantes...</p> : null}
            {trendStudentsError ? <p className="teams-error">{trendStudentsError}</p> : null}

            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cedula</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Periodo</th>
                    <th>Fecha inicio</th>
                    <th>Correo personal</th>
                    <th>Nombre Carrera</th>
                  </tr>
                </thead>
                <tbody>
                  {trendStudents.length > 0 ? (
                    trendStudents.map((student) => (
                      <tr
                        key={`trend-${selectedTrendPoint.anio}-${selectedTrendPoint.mes}-${student.tipo_matricula}-${student.codigo_estud}-${student.periodo || 'na'}`}
                      >
                        <td>{student.nombre_estudiante}</td>
                        <td>{student.cedula || '-'}</td>
                        <td>{student.tipo_matricula}</td>
                        <td>{student.estado_nombre}</td>
                        <td>{student.detalle_periodo || student.periodo || '-'}</td>
                        <td>{student.fecha_inicio_periodo || '-'}</td>
                        <td>{student.correo_personal || '-'}</td>
                        <td>{student.nombre_carrera || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8}>Sin estudiantes para el mes seleccionado.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : null}
    </>
  )
}
