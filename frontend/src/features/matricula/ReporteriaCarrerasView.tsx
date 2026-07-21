import { useMemo, useState } from 'react'

import { fetchMatriculaCareerStateStudents } from '../../lib/api'
import type {
  MatriculaCareerStateSummaryItem,
  MatriculaCareerStateSummaryResponse,
  MatriculaStudentItem,
  MatriculaTipo,
} from '../../types/app'

type ReporteriaCarrerasViewProps = {
  displayName: string
  loading: boolean
  error: string
  report: MatriculaCareerStateSummaryResponse | null
  onLoad: () => void
}

const estadoOptions = [
  { label: 'Activo', codigo: 'A' },
  { label: 'Graduado', codigo: 'G' },
  { label: 'Inactivo', codigo: 'P' },
  { label: 'Retirado', codigo: 'R' },
] as const

const tipoOptions: MatriculaTipo[] = ['R', 'H']

type CareerReportRow = {
  key: string
  escuela: string
  cod_anio_basica: string
  nombre_carrera: string
  total: number
  byTipo: Record<string, number>
  byEstado: Record<string, number>
}

function buildRows(items: MatriculaCareerStateSummaryItem[]): CareerReportRow[] {
  const rows = new Map<string, CareerReportRow>()
  for (const item of items) {
    const key = `${item.escuela}|${item.cod_anio_basica}|${item.nombre_carrera}`
    const row = rows.get(key) || {
      key,
      escuela: item.escuela || 'Sin escuela',
      cod_anio_basica: item.cod_anio_basica || '',
      nombre_carrera: item.nombre_carrera || 'Sin carrera registrada',
      total: 0,
      byTipo: { R: 0, H: 0 },
      byEstado: { A: 0, G: 0, P: 0, R: 0 },
    }
    row.total += item.total_estudiantes
    row.byTipo[item.tipo_matricula] = (row.byTipo[item.tipo_matricula] || 0) + item.total_estudiantes
    row.byEstado[item.estado_codigo] = (row.byEstado[item.estado_codigo] || 0) + item.total_estudiantes
    rows.set(key, row)
  }
  return [...rows.values()].sort((left, right) =>
    `${left.escuela} ${left.nombre_carrera}`.localeCompare(`${right.escuela} ${right.nombre_carrera}`)
  )
}

export function ReporteriaCarrerasView({
  displayName,
  loading,
  error,
  report,
  onLoad,
}: Readonly<ReporteriaCarrerasViewProps>) {
  const [schoolFilter, setSchoolFilter] = useState('ALL')
  const [estadoFilter, setEstadoFilter] = useState('ALL')
  const [tipoFilter, setTipoFilter] = useState<'ALL' | MatriculaTipo>('ALL')
  const [studentModalRow, setStudentModalRow] = useState<CareerReportRow | null>(null)
  const [careerStudents, setCareerStudents] = useState<MatriculaStudentItem[]>([])
  const [careerStudentsLoading, setCareerStudentsLoading] = useState(false)
  const [careerStudentsError, setCareerStudentsError] = useState('')
  const items = useMemo(() => report?.items || [], [report?.items])
  const schools = useMemo(
    () => [...new Set(items.map((item) => item.escuela || 'Sin escuela'))].sort((a, b) => a.localeCompare(b)),
    [items]
  )
  const filteredItems = useMemo(
    () =>
      items.filter((item) => {
        const matchesSchool = schoolFilter === 'ALL' || item.escuela === schoolFilter
        const matchesEstado = estadoFilter === 'ALL' || item.estado_codigo === estadoFilter
        const matchesTipo = tipoFilter === 'ALL' || item.tipo_matricula === tipoFilter
        return matchesSchool && matchesEstado && matchesTipo
      }),
    [estadoFilter, items, schoolFilter, tipoFilter]
  )
  const rows = useMemo(() => buildRows(filteredItems), [filteredItems])
  const totalFiltrado = rows.reduce((sum, row) => sum + row.total, 0)
  const totalsByEstado = report?.totals_by_estado || {}
  const totalsByTipo = report?.totals_by_tipo || {}
  async function openCareerStudents(row: CareerReportRow) {
    setStudentModalRow(row)
    setCareerStudents([])
    setCareerStudentsError('')
    setCareerStudentsLoading(true)
    try {
      const response = await fetchMatriculaCareerStateStudents({
        cod_anio_basica: row.cod_anio_basica || undefined,
        nombre_carrera: row.nombre_carrera,
        escuela: row.escuela,
        estado_codigo: estadoFilter === 'ALL' ? undefined : estadoFilter,
        tipo_matricula: tipoFilter === 'ALL' ? undefined : tipoFilter,
      })
      setCareerStudents(response.items || [])
    } catch (apiError) {
      setCareerStudentsError(apiError instanceof Error ? apiError.message : 'Error consultando estudiantes de la carrera')
    } finally {
      setCareerStudentsLoading(false)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Reporteria</p>
          <h1>Escuela, carrera y estados</h1>
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

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {tipoOptions.map((tipo) => (
          <article key={tipo} className="student-card student-card--stat matricula-stat-card">
            <p>Tipo {tipo}</p>
            <h2>{totalsByTipo[tipo] ?? 0}</h2>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {estadoOptions.map(({ label, codigo }) => (
          <article key={codigo} className="student-card student-card--stat matricula-stat-card">
            <p>{label}</p>
            <h2>{totalsByEstado[codigo] ?? 0}</h2>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--content reporteria-carreras-grid">
        <article className="student-card reporteria-carreras-card">
          <div className="card-head">
            <h3>Reporte por carrera</h3>
            <span>{loading ? 'Cargando...' : `${rows.length} carrera(s), ${totalFiltrado} estudiante(s)`}</span>
          </div>

          <div className="matricula-acad-form">
            <label>
              <span>Escuela</span>
              <select value={schoolFilter} onChange={(event) => setSchoolFilter(event.target.value)}>
                <option value="ALL">Todas</option>
                {schools.map((school) => (
                  <option key={school} value={school}>
                    {school}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Estado</span>
              <select value={estadoFilter} onChange={(event) => setEstadoFilter(event.target.value)}>
                <option value="ALL">Todos</option>
                {estadoOptions.map(({ label, codigo }) => (
                  <option key={codigo} value={codigo}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Tipo</span>
              <select value={tipoFilter} onChange={(event) => setTipoFilter(event.target.value as 'ALL' | MatriculaTipo)}>
                <option value="ALL">Todos</option>
                {tipoOptions.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    Tipo {tipo}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={onLoad} disabled={loading}>
              {loading ? 'Actualizando...' : 'Actualizar reporte'}
            </button>
          </div>

          {error ? <p className="teams-error">{error}</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Carrera</th>
                  <th>Total</th>
                  <th>Tipo R</th>
                  <th>Tipo H</th>
                  <th>Activo</th>
                  <th>Graduado</th>
                  <th>Inactivo</th>
                  <th>Retirado</th>
                  <th>Ver</th>
                </tr>
              </thead>
              <tbody>
                {rows.length > 0 ? (
                  rows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.nombre_carrera}</td>
                      <td>{row.total}</td>
                      <td>{row.byTipo.R || 0}</td>
                      <td>{row.byTipo.H || 0}</td>
                      <td>{row.byEstado.A || 0}</td>
                      <td>{row.byEstado.G || 0}</td>
                      <td>{row.byEstado.P || 0}</td>
                      <td>{row.byEstado.R || 0}</td>
                      <td>
                        <button type="button" className="reporteria-row-action" onClick={() => void openCareerStudents(row)}>
                          Ver
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9}>Sin datos para los filtros seleccionados.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {studentModalRow ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Estudiantes de la carrera</h3>
                <span>
                  {studentModalRow.nombre_carrera}
                  {estadoFilter !== 'ALL' ? ` / Estado ${estadoFilter}` : ''}
                  {tipoFilter !== 'ALL' ? ` / Tipo ${tipoFilter}` : ''}
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setStudentModalRow(null)
                  setCareerStudents([])
                  setCareerStudentsError('')
                }}
              >
                Cerrar
              </button>
            </div>

            {careerStudentsLoading ? <p className="teams-message">Consultando estudiantes...</p> : null}
            {careerStudentsError ? <p className="teams-error">{careerStudentsError}</p> : null}

            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cedula</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Periodo</th>
                    <th>Correo personal</th>
                    <th>Correo Intec</th>
                  </tr>
                </thead>
                <tbody>
                  {careerStudents.length > 0 ? (
                    careerStudents.map((student) => (
                      <tr key={`${student.tipo_matricula}-${student.codigo_estud}-${student.periodo || 'na'}`}>
                        <td>{student.nombre_estudiante}</td>
                        <td>{student.cedula || '-'}</td>
                        <td>{student.tipo_matricula}</td>
                        <td>{student.estado_nombre}</td>
                        <td>{student.detalle_periodo || student.periodo || '-'}</td>
                        <td>{student.correo_personal || '-'}</td>
                        <td>{student.correo_intec || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>Sin estudiantes para la carrera seleccionada.</td>
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
