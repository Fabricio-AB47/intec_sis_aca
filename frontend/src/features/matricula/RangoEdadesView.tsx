import { useEffect, useMemo, useState } from 'react'

import { downloadAgeRangesWorkbook, fetchAgeRanges, fetchAgeRangesCatalog } from '../../lib/api'
import type { AgeRangeCatalogResponse, AgeRangeFilters, AgeRangeResponse, AgeRangeRow } from '../../types/app'

type RangoEdadesViewProps = {
  displayName: string
}

function formatNumber(value?: number | string | null): string {
  const number = typeof value === 'number' ? value : Number(String(value ?? '').replace(',', '.'))
  return new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(Number.isFinite(number) ? number : 0)
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function percentOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text ? `${formatNumber(value)}%` : '-'
}

function downloadBlob(blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `rango-edades-${new Date().toISOString().slice(0, 10)}.xlsx`
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function rowMatches(row: AgeRangeRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    row.estudiante_codigo,
    row.cedula,
    row.estudiante,
    row.correo_personal,
    row.correo_intec,
    row.telefono,
    row.celular,
    row.estado,
    row.rango_edad,
    row.tipo_beca,
    row.periodo,
    row.carrera,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .includes(needle)
}

export function RangoEdadesView({ displayName }: Readonly<RangoEdadesViewProps>) {
  const [catalog, setCatalog] = useState<AgeRangeCatalogResponse | null>(null)
  const [data, setData] = useState<AgeRangeResponse | null>(null)
  const [periodo, setPeriodo] = useState('')
  const [carrera, setCarrera] = useState('')
  const [estado, setEstado] = useState('A')
  const [tipoBeca, setTipoBeca] = useState('')
  const [rangoEdad, setRangoEdad] = useState('')
  const [buscar, setBuscar] = useState('')
  const [limit, setLimit] = useState(1000)
  const [tableFilter, setTableFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [error, setError] = useState('')

  const rows = data?.rows || []
  const ranges = data?.ranges || []
  const maxRangeTotal = useMemo(() => Math.max(1, ...ranges.map((item) => item.total || 0)), [ranges])
  const visibleRows = useMemo(() => rows.filter((row) => rowMatches(row, tableFilter)), [rows, tableFilter])
  const filters = useMemo<AgeRangeFilters>(
    () => ({
      periodo: periodo.trim(),
      carrera: carrera.trim(),
      estado: estado.trim(),
      tipo_beca: tipoBeca.trim(),
      rango_edad: rangoEdad.trim(),
      buscar: buscar.trim(),
      limit,
    }),
    [buscar, carrera, estado, limit, periodo, rangoEdad, tipoBeca],
  )

  async function loadCatalog() {
    setCatalogLoading(true)
    try {
      const payload = await fetchAgeRangesCatalog()
      setCatalog(payload)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el catalogo de rango de edades')
    } finally {
      setCatalogLoading(false)
    }
  }

  async function loadData(nextFilters: AgeRangeFilters = filters) {
    setError('')
    setLoading(true)
    try {
      const payload = await fetchAgeRanges(nextFilters)
      setData(payload)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar el rango de edades')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  async function exportExcel() {
    setError('')
    setDownloadLoading(true)
    try {
      const blob = await downloadAgeRangesWorkbook({ ...filters, limit: Math.max(limit, 10000) })
      downloadBlob(blob)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el Excel')
    } finally {
      setDownloadLoading(false)
    }
  }

  useEffect(() => {
    void loadCatalog()
    void loadData()
  }, [])

  const statItems = [
    ['Total estudiantes', data?.summary?.total],
    ['Edad calculada', data?.summary?.edad_calculada],
    ['Sin fecha valida', data?.summary?.sin_fecha],
    ['Con beca', data?.summary?.con_beca],
    ['Sin beca', data?.summary?.sin_beca],
  ] as const

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Reporteria</p>
          <h1>Rango de edades</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>{data?.fecha_calculo ? `Calculo ${data.fecha_calculo}` : 'Edades y becas'}</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {statItems.map(([label, value]) => (
          <article key={label} className="student-card student-card--stat matricula-stat-card">
            <p>{label}</p>
            <h2>{formatNumber(value)}</h2>
            <small>{data?.generated_at ? data.generated_at.slice(0, 10) : 'Pendiente'}</small>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--content age-ranges-grid">
        <article className="student-card student-card--wide age-ranges-filter-card">
          <div className="card-head">
            <h3>Filtros</h3>
            <span>{catalogLoading ? 'Cargando catalogo...' : `${catalog?.becas?.length || 0} beca(s)`}</span>
          </div>

          <div className="matricula-acad-form age-ranges-form">
            <label>
              <span>Periodo</span>
              <input value={periodo} onChange={(event) => setPeriodo(event.target.value)} placeholder="Codigo periodo" />
            </label>
            <label>
              <span>Carrera</span>
              <input value={carrera} onChange={(event) => setCarrera(event.target.value)} placeholder="Codigo carrera" />
            </label>
            <label>
              <span>Estado</span>
              <select value={estado} onChange={(event) => setEstado(event.target.value)}>
                <option value="">Todos</option>
                {(catalog?.estados || []).map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Rango</span>
              <select value={rangoEdad} onChange={(event) => setRangoEdad(event.target.value)}>
                <option value="">Todos</option>
                {(catalog?.rangos || []).map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Beca</span>
              <select value={tipoBeca} onChange={(event) => setTipoBeca(event.target.value)}>
                <option value="">Todas</option>
                <option value="Sin beca">Sin beca</option>
                {(catalog?.becas || []).map((beca) => (
                  <option key={beca} value={beca}>
                    {beca}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Limite</span>
              <input
                type="number"
                min={1}
                max={10000}
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value) || 1000)}
              />
            </label>
            <label className="age-ranges-field--wide">
              <span>Buscar</span>
              <input value={buscar} onChange={(event) => setBuscar(event.target.value)} placeholder="Nombre, cedula, codigo, carrera o beca" />
            </label>
          </div>

          <div className="teams-actions age-ranges-actions">
            <button type="button" onClick={() => void loadData()} disabled={loading}>
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
            <button type="button" onClick={() => void exportExcel()} disabled={downloadLoading || rows.length === 0}>
              {downloadLoading ? 'Generando...' : 'Generar Excel'}
            </button>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
        </article>

        <article className="student-card student-card--wide age-ranges-chart-card">
          <div className="card-head">
            <h3>Comparativo por rangos</h3>
            <span>{formatNumber(rows.length)} fila(s)</span>
          </div>

          <div className="age-ranges-chart">
            {ranges.map((item) => {
              const totalWidth = `${Math.max(3, ((item.total || 0) / maxRangeTotal) * 100)}%`
              const scholarshipWidth = item.total ? `${Math.min(100, ((item.con_beca || 0) / item.total) * 100)}%` : '0%'
              return (
                <div key={item.rango_edad} className="age-ranges-chart__row">
                  <div className="age-ranges-chart__label">
                    <strong>{item.rango_edad}</strong>
                    <span>{formatNumber(item.total)} estudiante(s)</span>
                  </div>
                  <div className="age-ranges-chart__track">
                    <span className="age-ranges-chart__bar" style={{ width: totalWidth }}>
                      <em style={{ width: scholarshipWidth }} />
                    </span>
                  </div>
                  <div className="age-ranges-chart__meta">
                    <span>Beca {formatNumber(item.con_beca)}</span>
                    <span>Sin beca {formatNumber(item.sin_beca)}</span>
                    <span>Prom. {formatNumber(item.promedio_beca)}%</span>
                  </div>
                </div>
              )
            })}
          </div>
        </article>

        <article className="student-card student-card--wide age-ranges-results-card">
          <div className="card-head">
            <h3>Estudiantes</h3>
            <span>{formatNumber(visibleRows.length)} visible(s)</span>
          </div>

          <div className="excel-toolbar age-ranges-toolbar">
            <label>
              <span>Filtrar tabla</span>
              <input value={tableFilter} onChange={(event) => setTableFilter(event.target.value)} placeholder="Filtrar resultados cargados" />
            </label>
            <div>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <span>de {formatNumber(rows.length)}</span>
            </div>
            <small>{data?.fecha_calculo ? `Edad calculada con fecha ${data.fecha_calculo}` : 'Sin consulta'}</small>
          </div>

          <div className="matricula-table-wrap excel-table-wrap age-ranges-table-wrap">
            <table className="matricula-table age-ranges-table">
              <thead>
                <tr>
                  <th>Codigo</th>
                  <th>Estudiante</th>
                  <th>Contacto</th>
                  <th>Edad</th>
                  <th>Rango</th>
                  <th>Beca</th>
                  <th>Periodo</th>
                  <th>Carrera</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? (
                  visibleRows.map((row, index) => (
                    <tr key={`${row.estudiante_codigo || row.cedula || index}-${index}`}>
                      <td>
                        <strong>{valueOrDash(row.estudiante_codigo)}</strong>
                        <small>{valueOrDash(row.cedula)}</small>
                      </td>
                      <td>
                        <strong>{valueOrDash(row.estudiante)}</strong>
                        <small>{valueOrDash(row.estado)}</small>
                      </td>
                      <td>
                        <strong>{valueOrDash(row.correo_intec || row.correo_personal)}</strong>
                        <small>{row.correo_intec && row.correo_personal ? valueOrDash(row.correo_personal) : 'Correo personal -'}</small>
                        <small>Cel. {valueOrDash(row.celular)} | Tel. {valueOrDash(row.telefono)}</small>
                      </td>
                      <td>
                        <strong>{row.edad === null || row.edad === undefined ? '-' : formatNumber(row.edad)}</strong>
                        <small>{valueOrDash(row.fecha_nacimiento)}</small>
                      </td>
                      <td>
                        <span className="age-ranges-badge">{valueOrDash(row.rango_edad)}</span>
                      </td>
                      <td>
                        <strong>{valueOrDash(row.tipo_beca || 'Sin beca')}</strong>
                        <small>{percentOrDash(row.porcentaje_beca)}</small>
                      </td>
                      <td>
                        <strong>{valueOrDash(row.periodo_codigo)}</strong>
                        <small>{valueOrDash(row.periodo)}</small>
                      </td>
                      <td>
                        <strong>{valueOrDash(row.carrera_codigo)}</strong>
                        <small>{valueOrDash(row.carrera)}</small>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8}>{loading ? 'Consultando...' : 'Sin resultados para mostrar.'}</td>
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
