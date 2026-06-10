import { useState } from 'react'

import type {
  MatriculaPeriodSummaryItem,
  MatriculaStudentItem,
  MatriculaTipo,
  MatriculaYearSummaryItem,
} from '../../types/app'

type EstadoFilter = 'ALL' | 'A' | 'P' | 'R' | 'G'
type PuntoFilter = 'ALL' | 'PRIMERA' | 'ULTIMA'

type PeriodoAcademicoViewProps = {
  variant?: 'academic' | 'movement'
  displayName: string
  loading: boolean
  loadingStudents: boolean
  error: string
  studentsError: string
  periodSummaryItems: MatriculaPeriodSummaryItem[]
  yearSummaryItems: MatriculaYearSummaryItem[]
  students: MatriculaStudentItem[]
  onLoadSummary: () => void
  onSelectYear: (anio: number | null) => void
}

function buildFallbackYears(items: MatriculaPeriodSummaryItem[]): MatriculaYearSummaryItem[] {
  const byYear = new Map<number, MatriculaYearSummaryItem>()

  for (const item of items) {
    if (item.anio_periodo === null || item.anio_periodo === undefined) continue
    const current = byYear.get(item.anio_periodo) || {
      anio_periodo: item.anio_periodo,
      total_estudiantes: 0,
      activos: 0,
      inactivos: 0,
      retirados: 0,
      graduados: 0,
    }

    current.total_estudiantes += item.total_estudiantes
    current.activos += item.activos
    current.inactivos += item.inactivos
    current.retirados += item.retirados
    current.graduados += item.graduados
    byYear.set(item.anio_periodo, current)
  }

  return Array.from(byYear.values()).sort((a, b) => (b.anio_periodo || 0) - (a.anio_periodo || 0))
}

export function PeriodoAcademicoView({
  variant = 'academic',
  displayName,
  loading,
  loadingStudents,
  error,
  studentsError,
  periodSummaryItems,
  yearSummaryItems,
  students,
  onLoadSummary,
  onSelectYear,
}: Readonly<PeriodoAcademicoViewProps>) {
  const isMovement = variant === 'movement'
  const [selectedYear, setSelectedYear] = useState<string>('ALL')
  const [tipoFilter, setTipoFilter] = useState<'ALL' | MatriculaTipo>('ALL')
  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>('ALL')
  const [puntoFilter, setPuntoFilter] = useState<PuntoFilter>('ALL')
  const [search, setSearch] = useState('')
  const [selectedListLabel, setSelectedListLabel] = useState('')

  const years = yearSummaryItems.length > 0 ? yearSummaryItems : buildFallbackYears(periodSummaryItems)
  const normalizedSearch = search.trim().toLowerCase()
  const filteredRows = periodSummaryItems.filter((row) => {
    if (selectedYear !== 'ALL' && String(row.anio_periodo ?? '') !== selectedYear) {
      return false
    }
    if (tipoFilter !== 'ALL' && row.tipo_matricula !== tipoFilter) {
      return false
    }
    if (isMovement && puntoFilter !== 'ALL' && row.punto_matricula !== puntoFilter) {
      return false
    }
    if (!normalizedSearch) {
      return true
    }

    return `${row.codigo_periodo} ${row.detalle_periodo}`.toLowerCase().includes(normalizedSearch)
  })

  const selectedYearSummary = years.find((year) => String(year.anio_periodo ?? '') === selectedYear)
  const selectedStudents = students.filter((student) => {
    if (tipoFilter !== 'ALL' && student.tipo_matricula !== tipoFilter) {
      return false
    }
    if (selectedYear !== 'ALL' && String(student.anio_periodo ?? '') !== selectedYear) {
      return false
    }
    if (estadoFilter !== 'ALL' && student.estado_codigo !== estadoFilter) {
      return false
    }
    return true
  })
  const listSummary = selectedListLabel
    ? `${selectedListLabel} / ${selectedStudents.length} estudiantes`
    : 'Selecciona una tarjeta'
  const titleEyebrow = isMovement ? 'Periodo matriculados' : 'Periodo academico'
  const titleHeading = isMovement ? 'Movimiento por primera y ultima matricula' : 'Primera matricula historica por año'
  const userLabel = isMovement ? 'Periodo matriculados' : 'Periodo academico'

  const handleYearClick = (yearValue: string, label: string, anio: number | null) => {
    setSelectedYear(yearValue)
    setEstadoFilter('ALL')
    setPuntoFilter('ALL')
    setSelectedListLabel(label)
    onSelectYear(anio)
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">{titleEyebrow}</p>
          <h1>{titleHeading}</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>{userLabel}</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        <button
          type="button"
          className={`student-card student-card--stat periodo-year-card ${selectedYear === 'ALL' ? 'periodo-year-card--active' : ''}`}
          onClick={() => handleYearClick('ALL', 'Todos los años', null)}
        >
          <p>Todos los años</p>
          <h2>{years.reduce((sum, year) => sum + year.total_estudiantes, 0)}</h2>
          <small>{isMovement ? 'Primera + ultima matricula' : 'Primera matricula'}</small>
        </button>
        {years.map((year) => (
          <button
            key={year.anio_periodo ?? 'sin-anio'}
            type="button"
            className={`student-card student-card--stat periodo-year-card ${String(year.anio_periodo ?? '') === selectedYear ? 'periodo-year-card--active' : ''}`}
            onClick={() => handleYearClick(String(year.anio_periodo ?? ''), String(year.anio_periodo ?? 'Sin año'), year.anio_periodo ?? null)}
          >
            <p>{year.anio_periodo ?? 'Sin año'}</p>
            <h2>{year.total_estudiantes}</h2>
            <small>{isMovement ? `Primera ${year.primeras ?? 0} / Ultima ${year.ultimas ?? 0}` : 'Primera matricula unicamente'}</small>
          </button>
        ))}
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Detalle de periodos</h3>
            <span>{loading ? 'Cargando...' : `${filteredRows.length} registros`}</span>
          </div>

          <div className="teams-controls periodo-controls">
            <label>
              <span>Tipo</span>
              <select value={tipoFilter} onChange={(event) => setTipoFilter(event.target.value as 'ALL' | MatriculaTipo)}>
                <option value="ALL">Todos</option>
                <option value="R">Regular (R)</option>
                <option value="H">Homologacion (H)</option>
              </select>
            </label>
            {isMovement ? (
              <label>
                <span>Punto de matricula</span>
                <select value={puntoFilter} onChange={(event) => setPuntoFilter(event.target.value as PuntoFilter)}>
                  <option value="ALL">Primera y ultima</option>
                  <option value="PRIMERA">Primera matricula</option>
                  <option value="ULTIMA">Ultima matricula</option>
                </select>
              </label>
            ) : null}
            <label>
              <span>Buscar periodo</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Codigo o detalle"
              />
            </label>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={onLoadSummary} disabled={loading}>
              {loading ? 'Actualizando...' : 'Actualizar periodos'}
            </button>
          </div>

          {selectedYearSummary ? (
            <>
              <div className="periodo-inline-summary">
                {([
                  ['ALL', 'Total', selectedYearSummary.total_estudiantes],
                  ['A', 'Activo', selectedYearSummary.activos],
                  ['P', 'Inactivo', selectedYearSummary.inactivos],
                  ['R', 'Retirado', selectedYearSummary.retirados],
                  ['G', 'Graduado', selectedYearSummary.graduados],
                ] as const).map(([estado, label, total]) => (
                  <button
                    key={estado}
                    type="button"
                    className={`periodo-filter-pill ${estadoFilter === estado ? 'periodo-filter-pill--active' : ''}`}
                    onClick={() => setEstadoFilter(estado)}
                  >
                    {label} {total}
                  </button>
                ))}
              </div>
              {isMovement ? (
                <div className="periodo-inline-summary">
                  {([
                    ['ALL', 'Ambos', `${selectedYearSummary.primeras ?? 0} / ${selectedYearSummary.ultimas ?? 0}`],
                    ['PRIMERA', 'Primera', `${selectedYearSummary.primeras ?? 0}`],
                    ['ULTIMA', 'Ultima', `${selectedYearSummary.ultimas ?? 0}`],
                  ] as const).map(([punto, label, total]) => (
                    <button
                      key={punto}
                      type="button"
                      className={`periodo-filter-pill ${puntoFilter === punto ? 'periodo-filter-pill--active' : ''}`}
                      onClick={() => setPuntoFilter(punto)}
                    >
                      {label} {total}
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}

          {error ? <p className="teams-error">{error}</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Año</th>
                  {isMovement ? <th>Punto</th> : null}
                  <th>Periodo</th>
                  <th>Detalle</th>
                  <th>Tipo</th>
                  <th>Activo</th>
                  <th>Inactivo</th>
                  <th>Retirado</th>
                  <th>Graduado</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length > 0 ? (
                  filteredRows.map((row) => (
                    <tr key={`${row.punto_matricula || 'ALL'}-${row.tipo_matricula}-${row.anio_periodo ?? 'na'}-${row.codigo_periodo}`}>
                      <td>{row.anio_periodo ?? '-'}</td>
                      {isMovement ? <td>{row.punto_matricula || '-'}</td> : null}
                      <td>{row.codigo_periodo || '-'}</td>
                      <td>{row.detalle_periodo || '-'}</td>
                      <td>{row.tipo_matricula}</td>
                      <td>{row.activos}</td>
                      <td>{row.inactivos}</td>
                      <td>{row.retirados}</td>
                      <td>{row.graduados}</td>
                      <td>{row.total_estudiantes}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={isMovement ? 10 : 9}>Sin datos por periodo para los filtros seleccionados.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Listado de estudiantes</h3>
            <span>{loadingStudents ? 'Cargando...' : listSummary}</span>
          </div>

          {studentsError ? <p className="teams-error">{studentsError}</p> : null}
          {loadingStudents ? <p className="teams-message">Consultando estudiantes...</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Codigo</th>
                  <th>Estudiante</th>
                  <th>Año</th>
                  {isMovement ? <th>Punto</th> : null}
                  <th>Tipo</th>
                  <th>Estado</th>
                  <th>Periodo</th>
                  <th>Correo personal</th>
                  <th>Nombre Carrera</th>
                </tr>
              </thead>
              <tbody>
                {selectedStudents.length > 0 ? (
                  selectedStudents.map((student) => (
                    <tr key={`${student.punto_matricula || 'ALL'}-${student.codigo_estud}-${student.anio_periodo ?? 'na'}-${student.periodo || 'na'}`}>
                      <td>{student.codigo_estud || '-'}</td>
                      <td>{student.nombre_estudiante}</td>
                      <td>{student.anio_periodo ?? '-'}</td>
                      {isMovement ? <td>{student.punto_matricula || '-'}</td> : null}
                      <td>{student.tipo_matricula}</td>
                      <td>{student.estado_nombre}</td>
                      <td>{student.detalle_periodo || student.periodo || '-'}</td>
                      <td>{student.correo_personal || '-'}</td>
                      <td>{student.nombre_carrera || '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={isMovement ? 9 : 8}>
                      {selectedListLabel
                        ? 'Sin estudiantes para la tarjeta seleccionada.'
                        : 'Selecciona una tarjeta de año para cargar estudiantes.'}
                    </td>
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
