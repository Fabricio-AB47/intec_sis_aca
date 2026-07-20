import { useState, type CSSProperties } from 'react'

import { fetchDashboardAdmissionsStudents, fetchDashboardMatriculaTrendStudents, fetchMatriculaList } from '../../lib/api'
import type {
  AdmissionsDashboardStudentItem,
  DashboardMatriculaResponse,
  DashboardMatriculaStateItem,
  MatriculaStudentItem,
} from '../../types/app'

type DashboardViewProps = {
  displayName: string
  error: string
  data: DashboardMatriculaResponse | null
  role?: string
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

type AdmissionsDetailSelection = {
  estado: string
  label: string
  total: number
  codigo_periodo?: string
  detalle_periodo?: string
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
  role = '',
}: Readonly<DashboardViewProps>) {
  const normalizedRole = role.trim().toUpperCase()
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
  const [selectedAdmissionsDetail, setSelectedAdmissionsDetail] = useState<AdmissionsDetailSelection | null>(null)
  const [admissionsStudents, setAdmissionsStudents] = useState<AdmissionsDashboardStudentItem[]>([])
  const [admissionsStudentsLoading, setAdmissionsStudentsLoading] = useState(false)
  const [admissionsStudentsError, setAdmissionsStudentsError] = useState('')
  const isAdmissionsPayload = data?.dashboard_type === 'admisiones'
  const isAdmissionsDashboard = isAdmissionsPayload || normalizedRole === 'ADMISIONES'
  const dashboardData = isAdmissionsDashboard && !isAdmissionsPayload ? null : data
  const trend = dashboardData?.trend || []
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
  const states = isAdmissionsDashboard
    ? (dashboardData?.states || [])
    : (dashboardData?.states || []).filter((item) => dashboardStateCodes.has(item.estado_codigo))
  const admissionTotals = dashboardData?.admissions || {}
  const admissionsByUserPeriod = admissionTotals.por_usuario_periodo || []
  const admissionsEnrolled = admissionTotals.ingresaron_cabecera_matricula
    ?? admissionsByUserPeriod.reduce(
      (sum, row) => sum + (row.ingresaron_cabecera_matricula ?? row.ingresaron_carreraxestud ?? 0),
      0
    )
  const admissionsActive = admissionTotals.activos_desde_admision
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.activos ?? 0), 0)
  const admissionsInactive = admissionTotals.inactivos_desde_admision
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.inactivos ?? 0), 0)
  const admissionsGraduated = admissionTotals.graduados_desde_admision
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.graduados ?? 0), 0)
  const admissionsRetired = admissionTotals.retirados_desde_admision
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.retirados ?? 0), 0)
  const admissionsPendingEnrollment = admissionTotals.pendientes_matricula
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.pendientes_matricula ?? 0), 0)
  const admissionsWithoutState = admissionTotals.sin_estado_desde_admision
    ?? admissionsByUserPeriod.reduce((sum, row) => sum + (row.sin_estado ?? 0), 0)
  const totalStudents = isAdmissionsDashboard
    ? admissionTotals.total_ingresados ?? dashboardData?.total_estudiantes ?? 0
    : states.reduce((sum, item) => sum + item.total_estudiantes, 0)
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
  const activeStudents = isAdmissionsDashboard
    ? admissionTotals.activos_desde_admision ?? 0
    : states.find((item) => item.estado_codigo === 'A')?.total_estudiantes ?? 0
  const activeByType = dashboardData?.active_by_type || []
  const rawActiveRegularStudents = dashboardData?.active_regular_students
    ?? activeByType.find((item) => item.tipo_matricula === 'R')?.total_estudiantes
    ?? 0
  const rawActiveHomologationStudents = dashboardData?.active_homologation_students
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
    (isAdmissionsDashboard
      ? [
          {
            estado_codigo: 'A',
            total_estudiantes: admissionTotals.activos_desde_admision ?? 0,
          },
          {
            estado_codigo: 'PEN',
            total_estudiantes: admissionTotals.pendientes_o_no_activos ?? 0,
          },
        ]
      : states).map((item) => ({
      key: item.estado_codigo,
      total_estudiantes: item.total_estudiantes,
      color: item.estado_codigo === 'PEN' ? '#d19a2a' : stateColors[item.estado_codigo] || '#8dbbc7',
    }))
  )
  const currentYearTrend = buildMonthlyTrend(trend, currentYear)
  const peakMonth = currentYearTrend.reduce(
    (best, item) => (item.total_estudiantes > best.total_estudiantes ? item : best),
    currentYearTrend[0] || { mes_nombre: '-', total_estudiantes: 0 }
  )
  const peakMonthDetail = peakMonth.total_estudiantes > 0 ? `${peakMonth.mes_nombre} ${currentYear}` : `Sin datos ${currentYear}`
  const monthBarMax = Math.max(...distributionTrend.map((item) => item.total_estudiantes), 1)
  const metricCards = isAdmissionsDashboard
    ? [
        { label: 'Preinscritos', value: totalStudents, detail: 'Registros en preinscripción', tone: 'red' },
        {
          label: 'Con cabecera matrícula',
          value: admissionsEnrolled,
          detail: statePercent(admissionsEnrolled, totalStudents),
          tone: 'cyan',
        },
        {
          label: 'Se mantienen activos',
          value: activeStudents,
          detail: statePercent(activeStudents, totalStudents),
          tone: 'cyan',
        },
        { label: 'Mes mayor', value: peakMonth.total_estudiantes, detail: peakMonthDetail, tone: 'gold' },
      ]
    : [
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
      const response = await fetchMatriculaList(item.tipo_matricula, 'A', 10000, null, undefined, 'CNE')
      setActiveTypeStudents(response.items || [])
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
      const response = await fetchMatriculaList('ALL', item.estado_codigo, 10000, null, undefined, 'CNE')
      setStateStudents(response.items || [])
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

  async function openAdmissionsStudents(selection: AdmissionsDetailSelection) {
    setSelectedAdmissionsDetail(selection)
    setAdmissionsStudents([])
    setAdmissionsStudentsError('')
    setAdmissionsStudentsLoading(true)
    try {
      const response = await fetchDashboardAdmissionsStudents({
        estado: selection.estado,
        codigo_periodo: selection.codigo_periodo,
        limit: 10000,
      })
      setAdmissionsStudents(response.items || [])
    } catch (apiError) {
      setAdmissionsStudentsError(
        apiError instanceof Error ? apiError.message : 'Error consultando estudiantes de admisiones'
      )
    } finally {
      setAdmissionsStudentsLoading(false)
    }
  }

  if (isAdmissionsDashboard) {
    const personalTotal = admissionTotals.total_ingresados ?? totalStudents
    const personalEnrolled = admissionsEnrolled
    const personalActive = admissionsActive
    const conversion = statePercent(personalEnrolled, personalTotal)
    const retention = statePercent(personalActive, personalTotal)
    const monthMax = Math.max(...visibleTrend.map((item) => item.total_estudiantes), 1)
    const hasNoAdvisorRecords = personalTotal === 0

    return (
      <>
        <header className="student-topbar">
          <div>
            <p className="eyebrow">Panel ventas</p>
            <h1>Dashboard de admisiones</h1>
          </div>

          <div className="student-topbar__right">
            <div className="student-user-pill">
              <div>
                <strong>{displayName}</strong>
                <span>
                  Ventas personales{admissionTotals.codigo_asesor ? ` · Asesor ${admissionTotals.codigo_asesor}` : ''}
                </span>
              </div>
            </div>
          </div>
        </header>

        {error ? <p className="teams-error">{error}</p> : null}
        {hasNoAdvisorRecords ? (
          <p className="teams-error teams-error--info">
            {admissionTotals.mensaje_vista ||
              `No hay preinscripciones vinculadas por codigo de asesor a ${admissionTotals.usuario_consultado || displayName}.`}
          </p>
        ) : null}

        <section className="student-grid student-grid--content dashboard-executive-grid dashboard-admissions-grid">
          <article className="student-card dashboard-summary-panel">
            <div className="card-head">
              <h3>Resumen personal</h3>
              <span>{conversion} conversion a matricula</span>
            </div>

            <div className="dashboard-metric-tiles">
              <button
                type="button"
                className="dashboard-metric-tile dashboard-metric-tile--red dashboard-metric-tile--clickable"
                onClick={() => void openAdmissionsStudents({ estado: 'ALL', label: 'Preinscritos', total: personalTotal })}
              >
                <span>Preinscritos</span>
                <strong>{personalTotal}</strong>
                <small>Registros creados en PREINSCRIPCION</small>
              </button>
              <button
                type="button"
                className="dashboard-metric-tile dashboard-metric-tile--cyan dashboard-metric-tile--clickable"
                onClick={() => void openAdmissionsStudents({ estado: 'CABECERA_MATRICULA', label: 'Con cabecera de matrícula', total: personalEnrolled })}
              >
                <span>Con cabecera de matrícula</span>
                <strong>{personalEnrolled}</strong>
                <small>{conversion} registrados en CABECERA_MATRICULA</small>
              </button>
              <button
                type="button"
                className="dashboard-metric-tile dashboard-metric-tile--cyan dashboard-metric-tile--clickable"
                onClick={() => void openAdmissionsStudents({ estado: 'A', label: 'Se mantienen activos', total: personalActive })}
              >
                <span>Se mantienen activos</span>
                <strong>{personalActive}</strong>
                <small>{retention} de los preinscritos</small>
              </button>
              <button
                type="button"
                className="dashboard-metric-tile dashboard-metric-tile--gold dashboard-metric-tile--clickable"
                onClick={() => void openAdmissionsStudents({ estado: 'PENDIENTE_MATRICULA', label: 'Pendientes de matrícula', total: admissionsPendingEnrollment })}
              >
                <span>Pendientes de matrícula</span>
                <strong>{admissionsPendingEnrollment}</strong>
                <small>Sin cabecera de matrícula</small>
              </button>
            </div>
          </article>

          <article className="student-card dashboard-pie-card">
            <div className="card-head">
              <h3>Estado de tus ventas</h3>
              <span>Activos {personalActive} de {personalTotal}</span>
            </div>

            <div className="dashboard-state-list dashboard-state-list--static">
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'A', label: 'Activos', total: personalActive })}>
                <span style={{ backgroundColor: stateColors.A }} />
                <strong>Activos</strong>
                <small>{statePercent(personalActive, personalTotal)} · {personalActive}</small>
              </button>
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'P', label: 'Inactivos', total: admissionsInactive })}>
                <span style={{ backgroundColor: stateColors.P }} />
                <strong>Inactivos</strong>
                <small>{statePercent(admissionsInactive, personalTotal)} · {admissionsInactive}</small>
              </button>
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'G', label: 'Graduados', total: admissionsGraduated })}>
                <span style={{ backgroundColor: stateColors.G }} />
                <strong>Graduados</strong>
                <small>{statePercent(admissionsGraduated, personalTotal)} · {admissionsGraduated}</small>
              </button>
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'R', label: 'Retirados', total: admissionsRetired })}>
                <span style={{ backgroundColor: stateColors.R }} />
                <strong>Retirados</strong>
                <small>{statePercent(admissionsRetired, personalTotal)} · {admissionsRetired}</small>
              </button>
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'PENDIENTE_MATRICULA', label: 'Pendientes matrícula', total: admissionsPendingEnrollment })}>
                <span style={{ backgroundColor: '#8dbbc7' }} />
                <strong>Pendientes matrícula</strong>
                <small>{statePercent(admissionsPendingEnrollment, personalTotal)} · {admissionsPendingEnrollment}</small>
              </button>
              <button type="button" onClick={() => void openAdmissionsStudents({ estado: 'SIN_ESTADO', label: 'Sin estado', total: admissionsWithoutState })}>
                <span style={{ backgroundColor: '#6b7280' }} />
                <strong>Sin estado</strong>
                <small>{statePercent(admissionsWithoutState, personalTotal)} · {admissionsWithoutState}</small>
              </button>
            </div>
          </article>

          <article className="student-card dashboard-admissions-kpi-card">
            <div className="card-head">
              <h3>Lectura rápida</h3>
              <span>Asesor {admissionTotals.codigo_asesor || '-'}</span>
            </div>
            <div className="dashboard-admissions-kpis">
              <div>
                <span>Conversión</span>
                <strong>{conversion}</strong>
                <small>{personalEnrolled} de {personalTotal} con cabecera</small>
              </div>
              <div>
                <span>Retención activa</span>
                <strong>{retention}</strong>
                <small>{personalActive} activos desde admisión</small>
              </div>
              <div>
                <span>No activos</span>
                <strong>{admissionsInactive + admissionsRetired + admissionsWithoutState}</strong>
                <small>Inactivos, retirados o sin estado</small>
              </div>
            </div>
          </article>

          <article className="student-card dashboard-bars-card">
            <div className="card-head">
              <h3>Movimiento mensual</h3>
              <span>Preinscripciones por fecha de ingreso</span>
            </div>

            <div className="dashboard-bars">
              {visibleTrend.map((item) => (
                <div key={item.periodo_mes}>
                  <span style={{ height: `${Math.max((item.total_estudiantes / monthMax) * 100, 3)}%` }} />
                  <small>{item.mes_nombre}</small>
                  <strong>{item.total_estudiantes}</strong>
                </div>
              ))}
            </div>
          </article>

          <article className="student-card student-card--wide dashboard-bars-card">
            <div className="card-head">
              <h3>Detalle por periodo académico</h3>
              <span>{admissionsByUserPeriod.length} periodo(s)</span>
            </div>
            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Periodo académico</th>
                    <th>Preinscritos</th>
                    <th>Cabecera matrícula</th>
                    <th>Activos</th>
                    <th>Inactivos</th>
                    <th>Graduados</th>
                    <th>Retirados</th>
                    <th>Pendientes matrícula</th>
                    <th>Sin estado</th>
                    <th>Conversión</th>
                  </tr>
                </thead>
                <tbody>
                  {admissionsByUserPeriod.length > 0 ? (
                    admissionsByUserPeriod.map((row, index) => {
                      const total = row.total_ingresados ?? 0
                      const enrolled = row.ingresaron_cabecera_matricula ?? row.ingresaron_carreraxestud ?? 0
                      const periodSelection = (estado: string, label: string, value: number): AdmissionsDetailSelection => ({
                        estado,
                        label,
                        total: value,
                        codigo_periodo: row.codigo_periodo,
                        detalle_periodo: row.detalle_periodo,
                      })
                      return (
                        <tr key={`${row.codigo_periodo || 'sp'}-${index}`}>
                          <td>
                            <strong>{row.detalle_periodo || 'Sin periodo'}</strong>
                            <br />
                            <small>{row.codigo_periodo || '-'}</small>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('ALL', 'Preinscritos', total))}>
                              {total}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('CABECERA_MATRICULA', 'Con cabecera de matrícula', enrolled))}>
                              {enrolled}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('A', 'Activos', row.activos ?? 0))}>
                              {row.activos ?? 0}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('P', 'Inactivos', row.inactivos ?? 0))}>
                              {row.inactivos ?? 0}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('G', 'Graduados', row.graduados ?? 0))}>
                              {row.graduados ?? 0}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('R', 'Retirados', row.retirados ?? 0))}>
                              {row.retirados ?? 0}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('PENDIENTE_MATRICULA', 'Pendientes matrícula', row.pendientes_matricula ?? 0))}>
                              {row.pendientes_matricula ?? 0}
                            </button>
                          </td>
                          <td>
                            <button type="button" className="dashboard-table-link" onClick={() => void openAdmissionsStudents(periodSelection('SIN_ESTADO', 'Sin estado', row.sin_estado ?? 0))}>
                              {row.sin_estado ?? 0}
                            </button>
                          </td>
                          <td>{statePercent(enrolled, total)}</td>
                        </tr>
                      )
                    })
                  ) : (
                    <tr>
                      <td colSpan={10}>No hay ventas registradas para tu usuario de admisiones.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        {selectedAdmissionsDetail ? (
          <div className="matricula-modal-overlay">
            <article className="matricula-modal dashboard-active-students-modal dashboard-admissions-students-modal">
              <div className="matricula-modal-head">
                <div className="matricula-modal-title">
                  <h3>{selectedAdmissionsDetail.label}</h3>
                  <span>
                    {selectedAdmissionsDetail.detalle_periodo || 'Todos los periodos'} ·{' '}
                    {admissionsStudents.length} estudiante(s)
                  </span>
                </div>
                <button
                  type="button"
                  className="matricula-modal-close"
                  onClick={() => {
                    setSelectedAdmissionsDetail(null)
                    setAdmissionsStudents([])
                    setAdmissionsStudentsError('')
                  }}
                >
                  Cerrar
                </button>
              </div>

              <div className="dashboard-active-modal-summary">
                <div>
                  <span>Filtro</span>
                  <strong>{selectedAdmissionsDetail.label}</strong>
                </div>
                <div>
                  <span>Periodo</span>
                  <strong>{selectedAdmissionsDetail.detalle_periodo || 'Todos'}</strong>
                </div>
                <div>
                  <span>Total esperado</span>
                  <strong>{selectedAdmissionsDetail.total}</strong>
                </div>
              </div>

              {admissionsStudentsLoading ? <p className="teams-message">Consultando estudiantes...</p> : null}
              {admissionsStudentsError ? <p className="teams-error">{admissionsStudentsError}</p> : null}

              {!admissionsStudentsLoading && !admissionsStudentsError ? (
                <div className="matricula-table-wrap">
                  <table className="matricula-table">
                    <thead>
                      <tr>
                        <th>Estudiante</th>
                        <th>Cédula</th>
                        <th>Periodo</th>
                        <th>Carrera</th>
                        <th>Estado</th>
                        <th>Ingreso</th>
                      </tr>
                    </thead>
                    <tbody>
                      {admissionsStudents.length > 0 ? (
                        admissionsStudents.map((student, index) => (
                          <tr key={`${student.codigo_periodo || 'sp'}-${student.cedula || student.codestu || index}`}>
                            <td>
                              <strong>{student.nombre_estudiante || 'Sin nombre'}</strong>
                              <br />
                              <small>{student.codigo_estud || student.codestu || '-'}</small>
                            </td>
                            <td>{student.cedula || '-'}</td>
                            <td>
                              <strong>{student.detalle_periodo || '-'}</strong>
                              <br />
                              <small>{student.codigo_periodo || '-'}</small>
                            </td>
                            <td>{student.carrera || '-'}</td>
                            <td>
                              <strong>{student.estado_nombre || student.estado_codigo || '-'}</strong>
                              <br />
                              <small>{student.tipo_matricula || '-'}</small>
                            </td>
                            <td>{student.fecha_ingreso || '-'}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={6}>No hay estudiantes para el filtro seleccionado.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </article>
          </div>
        ) : null}
      </>
    )
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">{isAdmissionsDashboard ? 'Panel admisiones' : 'Panel academico'}</p>
          <h1>{isAdmissionsDashboard ? 'Dashboard de admisiones' : 'Dashboard Estudiantil'}</h1>
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
            <h3>{isAdmissionsDashboard ? 'Tendencia por fecha de ingreso' : 'Tendencia por fecha de inicio'}</h3>
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
                            role={isAdmissionsDashboard ? undefined : 'button'}
                            tabIndex={isAdmissionsDashboard ? -1 : 0}
                            onClick={() => {
                              if (!isAdmissionsDashboard) void openTrendStudents(item)
                            }}
                            onKeyDown={(event) => {
                              if (isAdmissionsDashboard) return
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
            <h3>{isAdmissionsDashboard ? 'Resumen de admisiones' : 'Resumen de matricula'}</h3>
            <span>
              {isAdmissionsDashboard
                ? `Activos ${activeStudents} de ${totalStudents}`
                : `Activos R ${activeRegularStudents} + H ${activeHomologationStudents}`}
            </span>
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
              <h3>{isAdmissionsDashboard ? 'Ingreso y permanencia' : 'Estados de estudiantes'}</h3>
              <span>
                {isAdmissionsDashboard
                  ? `Ingresados: ${totalStudents} · Activos: ${activeStudents}`
                  : `Total: ${totalStudents} · Activos R/H: ${activeRhStudents}`}
              </span>
            </div>

            {!isAdmissionsDashboard ? (
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
            ) : null}

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
                {isAdmissionsDashboard ? (
                  <>
                    <div>
                      <span style={{ backgroundColor: stateColors.A }} />
                      <strong>Se mantienen activos</strong>
                      <small>
                        {statePercent(activeStudents, totalStudents)} · {activeStudents}
                      </small>
                    </div>
                    <div>
                      <span style={{ backgroundColor: '#d19a2a' }} />
                      <strong>Pendientes o no activos</strong>
                      <small>
                        {statePercent(admissionTotals.pendientes_o_no_activos ?? 0, totalStudents)} · {admissionTotals.pendientes_o_no_activos ?? 0}
                      </small>
                    </div>
                  </>
                ) : states.length > 0 ? (
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

          {!isAdmissionsDashboard ? (
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
          ) : null}
        </div>

        <article className="student-card dashboard-bars-card">
          <div className="card-head">
            <h3>{isAdmissionsDashboard ? 'Distribucion mensual de ingresos' : 'Distribucion mensual'}</h3>
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

        {admissionsByUserPeriod.length > 0 || !isAdmissionsDashboard ? (
          <article className="student-card student-card--wide dashboard-bars-card">
            <div className="card-head">
              <h3>Preinscripciones por usuario de admisiones</h3>
              <span>{admissionsByUserPeriod.length} registro(s)</span>
            </div>
            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Periodo académico</th>
                    <th>Usuario admisiones</th>
                    <th>Tipo usuario</th>
                    <th>Preinscritos</th>
                    <th>Cabecera matrícula</th>
                    <th>Activos</th>
                    <th>Inactivos</th>
                    <th>Graduados</th>
                    <th>Retirados</th>
                    <th>Pendientes matrícula</th>
                    <th>Sin estado</th>
                  </tr>
                </thead>
                <tbody>
                  {admissionsByUserPeriod.length > 0 ? (
                    admissionsByUserPeriod.map((row, index) => (
                      <tr key={`${row.codigo_periodo || 'sp'}-${row.usuario_id || row.usuario_login || 'su'}-${index}`}>
                        <td>
                          <strong>{row.detalle_periodo || 'Sin periodo'}</strong>
                          <br />
                          <small>{row.codigo_periodo || '-'}</small>
                        </td>
                        <td>
                          <strong>{row.usuario_nombre || 'Sin asesor'}</strong>
                          <br />
                          <small>{row.usuario_login || row.usuario_id || '-'}</small>
                        </td>
                        <td>{row.tipo_usuario || 'ADMISIONES'}</td>
                        <td>{row.total_ingresados ?? 0}</td>
                        <td>{row.ingresaron_cabecera_matricula ?? row.ingresaron_carreraxestud ?? 0}</td>
                        <td>{row.activos ?? 0}</td>
                        <td>{row.inactivos ?? 0}</td>
                        <td>{row.graduados ?? 0}</td>
                        <td>{row.retirados ?? 0}</td>
                        <td>{row.pendientes_matricula ?? 0}</td>
                        <td>{row.sin_estado ?? 0}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={10}>No hay preinscripciones agrupadas por usuario de admisiones.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        ) : null}

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
