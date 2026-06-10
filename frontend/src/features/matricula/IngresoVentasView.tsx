import { useMemo, useState } from 'react'

import type { IngresoVentasResponse, IngresoVentasRow } from '../../types/app'

type IngresoVentasViewProps = {
  displayName: string
  loading: boolean
  error: string
  data: IngresoVentasResponse | null
  onLoad: () => void
}

type EstadoFilter = 'ALL' | 'A' | 'G' | 'P' | 'R' | 'SIN_MATRICULA'
type TipoPeriodoFilter = 'ALL' | 'R' | 'H'
type RiskFilter = 'ALL' | 'green' | 'yellow' | 'red'
type StatKey =
  | 'preinscripciones'
  | 'validadas'
  | 'datos_estud'
  | 'carreraxestud'
  | 'sin_matricula'
  | 'asesores'
  | 'activos'
  | 'periodo_r'
  | 'periodo_h'
  | 'inactivos'
  | 'retirados'
  | 'graduados'
type UserSalesBar = {
  key: string
  name: string
  total: number
  porcentaje: number
  color: string
  risk: RiskFilter
}

const EMPTY_INGRESO_VENTAS_SUMMARY: NonNullable<IngresoVentasResponse['summary']> = []
const EMPTY_INGRESO_VENTAS_ROWS: IngresoVentasRow[] = []
const EMPTY_INGRESO_VENTAS_TOTALS: NonNullable<IngresoVentasResponse['totals']> = {}

const estadoOptions: Array<{ value: EstadoFilter; label: string }> = [
  { value: 'ALL', label: 'Todos' },
  { value: 'A', label: 'Activo' },
  { value: 'G', label: 'Graduado' },
  { value: 'P', label: 'Inactivo' },
  { value: 'R', label: 'Retirado' },
  { value: 'SIN_MATRICULA', label: 'Sin matricula' },
]
function salesRisk(index: number, total: number): RiskFilter {
  if (total <= 1 || index < Math.ceil(total / 3)) return 'green'
  if (index < Math.ceil((total * 2) / 3)) return 'yellow'
  return 'red'
}

function salesRiskColor(risk: RiskFilter): string {
  if (risk === 'green') return '#1f7a4d'
  if (risk === 'yellow') return '#d19a2a'
  if (risk === 'red') return '#b42318'
  return '#1f6f8b'
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function advisorKey(row: Pick<IngresoVentasRow, 'usuario_id' | 'codasesor' | 'usuario_preinscripcion'>): string {
  return row.usuario_id || row.codasesor || row.usuario_preinscripcion || 'SIN_ASESOR'
}

function estadoKey(row: IngresoVentasRow): EstadoFilter | 'SIN_ESTADO' {
  if (!row.matricula_validada) return 'SIN_MATRICULA'
  const estado = (row.estado_codigo_matricula || '').trim().toUpperCase()
  return ['A', 'G', 'P', 'R'].includes(estado) ? (estado as EstadoFilter) : 'SIN_ESTADO'
}

function estadoDatosKey(row: IngresoVentasRow): EstadoFilter | 'SIN_ESTADO' {
  const estado = (row.estado_codigo_matricula || '').trim().toUpperCase()
  return ['A', 'G', 'P', 'R'].includes(estado) ? (estado as EstadoFilter) : 'SIN_ESTADO'
}

function estadoLabel(row: IngresoVentasRow): string {
  if (!row.matricula_validada) return 'Sin matricula'
  return row.estado_nombre_matricula || row.estado_codigo_matricula || 'Sin estado'
}

function statusClass(row: IngresoVentasRow): string {
  const key = row.matricula_validada ? row.estado_cruce || row.estado_codigo_matricula || 'matriculado' : 'sin-matricula'
  return `cruce-status cruce-status--${key.toLowerCase().replaceAll('_', '-')}`
}

export function IngresoVentasView({
  displayName,
  loading,
  error,
  data,
  onLoad,
}: Readonly<IngresoVentasViewProps>) {
  const [selectedAdvisor, setSelectedAdvisor] = useState<string | null>(null)
  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>('ALL')
  const [tipoPeriodoFilter, setTipoPeriodoFilter] = useState<TipoPeriodoFilter>('ALL')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('ALL')
  const [selectedStatKey, setSelectedStatKey] = useState<StatKey | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const summary = data?.summary ?? EMPTY_INGRESO_VENTAS_SUMMARY
  const rows = data?.items ?? EMPTY_INGRESO_VENTAS_ROWS
  const datosEstudRows = data?.datos_estud_items ?? EMPTY_INGRESO_VENTAS_ROWS
  const totals = data?.totals ?? EMPTY_INGRESO_VENTAS_TOTALS
  const normalizedSearch = searchTerm.trim().toLowerCase()
  const selectedSummary = summary.find((item) => item.usuario_key === selectedAdvisor)
  const totalBasePorcentaje = totals.total_base_porcentaje ?? totals.total_matriculados ?? 0
  const salesBars = useMemo<UserSalesBar[]>(() => {
    return [...summary]
      .sort((left, right) => right.total_matriculados - left.total_matriculados)
      .map((user, index) => ({
        key: user.usuario_key,
        name: user.usuario_nombre,
        total: user.total_matriculados,
        porcentaje: totalBasePorcentaje > 0 ? (user.total_matriculados / totalBasePorcentaje) * 100 : 0,
        risk: salesRisk(index, summary.length),
        color: salesRiskColor(salesRisk(index, summary.length)),
      }))
  }, [summary, totalBasePorcentaje])
  const visibleSalesBars = useMemo(
    () => salesBars.filter((bar) => riskFilter === 'ALL' || bar.risk === riskFilter),
    [riskFilter, salesBars],
  )
  const statDetailRows = useMemo(() => {
    switch (selectedStatKey) {
      case 'preinscripciones':
        return rows
      case 'validadas':
        return datosEstudRows.filter((row) => row.matricula_validada)
      case 'datos_estud':
        return datosEstudRows
      case 'carreraxestud':
        return datosEstudRows.filter((row) => row.existe_carreraxestud)
      case 'sin_matricula':
        return datosEstudRows.filter((row) => !row.matricula_validada)
      case 'activos':
        return datosEstudRows.filter((row) => estadoDatosKey(row) === 'A')
      case 'periodo_r':
        return datosEstudRows.filter((row) => row.matricula_validada && row.tipo_matricula === 'R')
      case 'periodo_h':
        return datosEstudRows.filter((row) => row.matricula_validada && row.tipo_matricula === 'H')
      case 'inactivos':
        return datosEstudRows.filter((row) => estadoDatosKey(row) === 'P')
      case 'retirados':
        return datosEstudRows.filter((row) => estadoDatosKey(row) === 'R')
      case 'graduados':
        return datosEstudRows.filter((row) => estadoDatosKey(row) === 'G')
      default:
        return []
    }
  }, [datosEstudRows, rows, selectedStatKey])

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        if (!selectedAdvisor || advisorKey(row) !== selectedAdvisor) {
          return false
        }
        if (estadoFilter !== 'ALL' && estadoKey(row) !== estadoFilter) {
          return false
        }
        if (tipoPeriodoFilter !== 'ALL' && row.tipo_matricula !== tipoPeriodoFilter) {
          return false
        }
        if (!normalizedSearch) {
          return true
        }
        return [
          row.codestu,
          row.cedula_final,
          row.nombre_final,
          row.usuario_nombre,
          row.usuario_login,
          row.carrera_final,
          row.periodo_final,
          row.correo_preinscripcion,
        ]
          .join(' ')
          .toLowerCase()
          .includes(normalizedSearch)
      }),
    [estadoFilter, normalizedSearch, rows, selectedAdvisor, tipoPeriodoFilter],
  )

  function openAdvisorDetail(advisor: string) {
    setSelectedAdvisor(advisor)
    setEstadoFilter('ALL')
    setTipoPeriodoFilter('ALL')
    setSearchTerm('')
  }

  const statItems: Array<{ key: StatKey; label: string; value?: number }> = [
    { key: 'preinscripciones', label: 'Preinscripciones', value: totals.total_preinscripciones },
    { key: 'validadas', label: 'Validadas', value: totals.total_matriculados },
    { key: 'datos_estud', label: 'DATOS_ESTUD', value: totals.total_datos_estud },
    { key: 'carreraxestud', label: 'CARRERAXESTUD', value: totals.total_carreraxestud },
    { key: 'sin_matricula', label: 'Sin matricula', value: totals.sin_matricula },
    { key: 'asesores', label: 'Asesores', value: totals.asesores },
    { key: 'activos', label: 'Activos', value: totals.activos },
    { key: 'periodo_r', label: 'Periodo R', value: totals.regular_r },
    { key: 'periodo_h', label: 'Periodo H', value: totals.homologacion_h },
    { key: 'inactivos', label: 'Inactivos', value: totals.inactivos },
    { key: 'retirados', label: 'Retirados', value: totals.retirados },
    { key: 'graduados', label: 'Graduados', value: totals.graduados },
  ]
  const selectedStat = statItems.find((item) => item.key === selectedStatKey)

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Ingreso x ventas</p>
          <h1>Movimiento por usuario</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Ingreso x ventas</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {statItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className="student-card student-card--stat matricula-stat-card ingreso-ventas-stat-card"
            onClick={() => setSelectedStatKey(item.key)}
          >
            <p>{item.label}</p>
            <h2>{formatNumber(item.value)}</h2>
          </button>
        ))}
      </section>

      <section className="student-grid student-grid--content ingreso-ventas-grid">
        <article className="student-card student-card--wide ingreso-ventas-panel ingreso-ventas-history-card">
          <div className="card-head">
            <h3>Ventas por usuario</h3>
            <span>% sobre {formatNumber(totalBasePorcentaje)} en DATOS_ESTUD + CARRERAXESTUD</span>
          </div>

          <div className="teams-actions ingreso-ventas-refresh-actions">
            <button type="button" onClick={onLoad} disabled={loading}>
              {loading ? 'Actualizando...' : 'Actualizar'}
            </button>
          </div>

          {error ? <p className="teams-error">{error}</p> : null}

          <div className="ingreso-ventas-risk-legend">
            <button
              type="button"
              className={riskFilter === 'ALL' ? 'ingreso-ventas-risk-legend--active' : ''}
              onClick={() => setRiskFilter('ALL')}
            >
              Todos
            </button>
            <button
              type="button"
              className={riskFilter === 'green' ? 'ingreso-ventas-risk-legend--active' : ''}
              onClick={() => setRiskFilter((current) => (current === 'green' ? 'ALL' : 'green'))}
            >
              <i className="ingreso-ventas-risk-legend__green" />Mayor venta
            </button>
            <button
              type="button"
              className={riskFilter === 'yellow' ? 'ingreso-ventas-risk-legend--active' : ''}
              onClick={() => setRiskFilter((current) => (current === 'yellow' ? 'ALL' : 'yellow'))}
            >
              <i className="ingreso-ventas-risk-legend__yellow" />Seguimiento
            </button>
            <button
              type="button"
              className={riskFilter === 'red' ? 'ingreso-ventas-risk-legend--active' : ''}
              onClick={() => setRiskFilter((current) => (current === 'red' ? 'ALL' : 'red'))}
            >
              <i className="ingreso-ventas-risk-legend__red" />Riesgo
            </button>
          </div>

          <div className="ingreso-ventas-bar-chart">
            {visibleSalesBars.length > 0 ? (
              visibleSalesBars.map((bar) => (
                <button
                  key={bar.key}
                  type="button"
                  className="ingreso-ventas-bar-row"
                  onClick={() => openAdvisorDetail(bar.key)}
                >
                  <div className="ingreso-ventas-bar-label">
                    <strong>{bar.name}</strong>
                    <span>
                      {formatNumber(bar.total)} venta(s) / {bar.porcentaje.toFixed(1)}%
                    </span>
                  </div>
                  <div className="ingreso-ventas-bar-track">
                    <span style={{ width: `${Math.max(bar.porcentaje, bar.total > 0 ? 4 : 0)}%`, backgroundColor: bar.color }} />
                  </div>
                  <small>{formatNumber(bar.total)} de {formatNumber(totalBasePorcentaje)} estudiantes validados</small>
                </button>
              ))
            ) : (
              <p className="empty-block">Sin usuarios para el filtro seleccionado.</p>
            )}
          </div>
        </article>
      </section>

      {selectedSummary ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal ingreso-ventas-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Detalle de estudiantes</h3>
                <span>
                  {selectedSummary.usuario_nombre} / {formatNumber(filteredRows.length)} fila(s)
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedAdvisor(null)
                  setEstadoFilter('ALL')
                  setTipoPeriodoFilter('ALL')
                  setSearchTerm('')
                }}
              >
                Cerrar
              </button>
            </div>

            <div className="teams-controls ingreso-ventas-modal-controls">
              <label>
                <span>Estado</span>
                <select value={estadoFilter} onChange={(event) => setEstadoFilter(event.target.value as EstadoFilter)}>
                  {estadoOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Tipo periodo</span>
                <select
                  value={tipoPeriodoFilter}
                  onChange={(event) => setTipoPeriodoFilter(event.target.value as TipoPeriodoFilter)}
                >
                  <option value="ALL">Todos</option>
                  <option value="R">Regular (R)</option>
                  <option value="H">Homologacion (H)</option>
                </select>
              </label>
              <label>
                <span>Buscar</span>
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Estudiante, cedula, carrera o periodo"
                />
              </label>
            </div>

            <div className="matricula-table-wrap">
              <table className="matricula-table ingreso-ventas-detail-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Estado</th>
                    <th>Tipo periodo</th>
                    <th>Carrera</th>
                    <th>Periodo ingreso</th>
                    <th>Preinscripcion</th>
                    <th>Correo / Telefono</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length > 0 ? (
                    filteredRows.map((row, index) => (
                      <tr key={`${row.codestu}-${row.codperiodo_preinscripcion || 'na'}-${index}`}>
                        <td>
                          <div className="cruce-source-stack">
                            <strong>{valueOrDash(row.nombre_final)}</strong>
                            <small>{valueOrDash([row.codestu, row.cedula_final].filter(Boolean).join(' / '))}</small>
                          </div>
                        </td>
                        <td>
                          <span className={statusClass(row)}>{estadoLabel(row)}</span>
                        </td>
                        <td>{valueOrDash(row.tipo_matricula)}</td>
                        <td>
                          <div className="cruce-source-stack">
                            <span>{valueOrDash(row.carrera_final)}</span>
                            <small>{valueOrDash(row.codcarrera_matricula || row.codcarrera_preinscripcion)}</small>
                          </div>
                        </td>
                        <td>
                          <div className="cruce-source-stack">
                            <span>{valueOrDash(row.periodo_final)}</span>
                            <small>{valueOrDash(row.anio_final)}</small>
                          </div>
                        </td>
                        <td>
                          <div className="ingreso-ventas-flags">
                            <span>{row.prematricula ? 'Prematricula' : 'Sin prematricula'}</span>
                            <span>{row.control_ingreso ? 'Ingreso' : 'Pendiente'}</span>
                          </div>
                        </td>
                        <td>
                          <div className="cruce-source-stack">
                            <span>{valueOrDash(row.correo_preinscripcion)}</span>
                            <small>{valueOrDash(row.telefono)}</small>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>Sin estudiantes para los filtros seleccionados.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : null}

      {selectedStat ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal ingreso-ventas-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>{selectedStat.label}</h3>
                <span>
                  {selectedStat.key === 'asesores'
                    ? `${formatNumber(summary.length)} usuario(s)`
                    : `${formatNumber(statDetailRows.length)} fila(s)`}
                </span>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setSelectedStatKey(null)}>
                Cerrar
              </button>
            </div>

            {selectedStat.key === 'asesores' ? (
              <div className="matricula-table-wrap">
                <table className="matricula-table ingreso-ventas-summary-table">
                  <thead>
                    <tr>
                      <th>Usuario</th>
                      <th>Total</th>
                      <th>Validadas</th>
                      <th>Activos</th>
                      <th>Tipo R</th>
                      <th>Tipo H</th>
                      <th>Sin matricula</th>
                      <th>Ver</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.map((item) => (
                      <tr key={item.usuario_key}>
                        <td>
                          <div className="cruce-source-stack">
                            <strong>{item.usuario_nombre}</strong>
                            <small>{item.usuario_login || item.codasesor || item.usuario_id || '-'}</small>
                          </div>
                        </td>
                        <td>{formatNumber(item.total_preinscripciones)}</td>
                        <td>{formatNumber(item.total_matriculados)}</td>
                        <td>{formatNumber(item.activos)}</td>
                        <td>{formatNumber(item.regular_r)}</td>
                        <td>{formatNumber(item.homologacion_h)}</td>
                        <td>{formatNumber(item.sin_matricula)}</td>
                        <td>
                          <button
                            type="button"
                            className="reporteria-row-action"
                            onClick={() => {
                              setSelectedStatKey(null)
                              openAdvisorDetail(item.usuario_key)
                            }}
                          >
                            Ver
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="matricula-table-wrap">
                <table className="matricula-table ingreso-ventas-detail-table">
                  <thead>
                    <tr>
                      <th>Estudiante</th>
                      <th>Usuario</th>
                      <th>Estado</th>
                      <th>Tipo periodo</th>
                      <th>Carrera</th>
                      <th>Periodo ingreso</th>
                      <th>Correo / Telefono</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statDetailRows.length > 0 ? (
                      statDetailRows.map((row, index) => (
                        <tr key={`stat-${selectedStat.key}-${row.codestu}-${row.codperiodo_preinscripcion || 'na'}-${index}`}>
                          <td>
                            <div className="cruce-source-stack">
                              <strong>{valueOrDash(row.nombre_final)}</strong>
                              <small>{valueOrDash([row.codestu, row.cedula_final].filter(Boolean).join(' / '))}</small>
                            </div>
                          </td>
                          <td>
                            <div className="cruce-source-stack">
                              <span>{valueOrDash(row.usuario_nombre || row.usuario_preinscripcion)}</span>
                              <small>{valueOrDash(row.usuario_login || row.codasesor)}</small>
                            </div>
                          </td>
                          <td>
                            <span className={statusClass(row)}>{estadoLabel(row)}</span>
                          </td>
                          <td>{valueOrDash(row.tipo_matricula)}</td>
                          <td>
                            <div className="cruce-source-stack">
                              <span>{valueOrDash(row.carrera_final)}</span>
                              <small>{valueOrDash(row.codcarrera_matricula || row.codcarrera_preinscripcion)}</small>
                            </div>
                          </td>
                          <td>
                            <div className="cruce-source-stack">
                              <span>{valueOrDash(row.periodo_final)}</span>
                              <small>{valueOrDash(row.anio_final)}</small>
                            </div>
                          </td>
                          <td>
                            <div className="cruce-source-stack">
                              <span>{valueOrDash(row.correo_preinscripcion)}</span>
                              <small>{valueOrDash(row.telefono)}</small>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7}>Sin informacion para esta tarjeta.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        </div>
      ) : null}
    </>
  )
}
