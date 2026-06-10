import { useMemo, useState } from 'react'
import type {
  MatriculaTipo,
  MatriculaPeriodSummaryItem,
  MatriculaStudentItem,
  MatriculaYearSummaryItem,
} from '../../types/app'

type Props = Readonly<{
  periodSummaryItems: MatriculaPeriodSummaryItem[]
  yearSummaryItems: MatriculaYearSummaryItem[]
  students: MatriculaStudentItem[]
  displayName: string
  loading: boolean
  loadingStudents: boolean
  error: string | null
  studentsError: string | null
  onLoadSummary: () => Promise<void>
  onSelectYear: (year: number | null) => Promise<void>
}>

type YearTotals = {
  hasSummary: boolean
  year: number
  total: number
  acumulado: number
  activos: number
  inactivos: number
  retirados: number
  graduados: number
  r: number
  h: number
}

function emptyYearTotals(year: number): YearTotals {
  return {
    hasSummary: false,
    year,
    total: 0,
    acumulado: 0,
    activos: 0,
    inactivos: 0,
    retirados: 0,
    graduados: 0,
    r: 0,
    h: 0,
  }
}

function applyPeriodSummaryItem(target: YearTotals, item: MatriculaPeriodSummaryItem) {
  if (item.estado_codigo === 'A') {
    target.activos += item.total_estudiantes
  } else if (item.estado_codigo === 'P') {
    target.inactivos += item.total_estudiantes
  } else if (item.estado_codigo === 'R') {
    target.retirados += item.total_estudiantes
  } else if (item.estado_codigo === 'G') {
    target.graduados += item.total_estudiantes
  }

  if (item.tipo_matricula === 'R') {
    target.r += item.total_estudiantes
  } else if (item.tipo_matricula === 'H') {
    target.h += item.total_estudiantes
  }
}

function buildYearTotals(
  periodSummaryItems: MatriculaPeriodSummaryItem[],
  yearSummaryItems: MatriculaYearSummaryItem[],
) {
  const totals = new Map<number, YearTotals>()

  for (const item of yearSummaryItems) {
    if (item.anio_periodo == null) {
      continue
    }

    totals.set(item.anio_periodo, {
      ...emptyYearTotals(item.anio_periodo),
      hasSummary: true,
      total: item.total_estudiantes,
      acumulado: item.acumulado_estudiantes ?? 0,
      activos: item.activos ?? 0,
      inactivos: item.inactivos ?? 0,
      retirados: item.retirados ?? 0,
      graduados: item.graduados ?? 0,
    })
  }

  for (const item of periodSummaryItems) {
    if (item.anio_periodo == null) {
      continue
    }

    const current = totals.get(item.anio_periodo) ?? emptyYearTotals(item.anio_periodo)
    if (!current.hasSummary) {
      current.total += item.total_estudiantes
    }

    applyPeriodSummaryItem(current, item)

    totals.set(item.anio_periodo, current)
  }

  return [...totals.values()].sort((left, right) => left.year - right.year)
}

export function PeriodoMatriculadosView({
  periodSummaryItems,
  yearSummaryItems,
  students,
  loading,
  displayName,
  loadingStudents,
  error,
  studentsError,
  onLoadSummary,
  onSelectYear,
}: Props) {
  const [selectedYear, setSelectedYear] = useState<string>('ALL')
  const [tipoFilter, setTipoFilter] = useState<'ALL' | MatriculaTipo>('ALL')
  const [estadoFilter, setEstadoFilter] = useState<'ALL' | 'A' | 'P' | 'R' | 'G'>('ALL')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedListLabel, setSelectedListLabel] = useState('')

  const years = useMemo(
    () => buildYearTotals(periodSummaryItems, yearSummaryItems),
    [periodSummaryItems, yearSummaryItems],
  )

  const normalizedSearch = searchTerm.trim().toLowerCase()
  const filteredSummary = useMemo(() => {
    return periodSummaryItems.filter((item) => {
      if (selectedYear !== 'ALL' && String(item.anio_periodo ?? '') !== selectedYear) {
        return false
      }
      if (tipoFilter !== 'ALL' && item.tipo_matricula !== tipoFilter) {
        return false
      }
      if (estadoFilter !== 'ALL' && item.estado_codigo !== estadoFilter) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      return [
        String(item.anio_periodo ?? ''),
        item.tipo_matricula,
        item.estado_nombre ?? '',
        item.estado_codigo ?? '',
      ]
        .join(' ')
        .toLowerCase()
        .includes(normalizedSearch)
    })
  }, [estadoFilter, normalizedSearch, periodSummaryItems, selectedYear, tipoFilter])

  const filteredStudents = useMemo(() => {
    return students.filter((student) => {
      if (selectedYear !== 'ALL' && String(student.anio_periodo ?? '') !== selectedYear) {
        return false
      }
      if (tipoFilter !== 'ALL' && student.tipo_matricula !== tipoFilter) {
        return false
      }
      if (estadoFilter !== 'ALL' && student.estado_codigo !== estadoFilter) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      return [
        student.codigo_estud,
        student.nombre_estudiante,
        student.nombre_carrera,
        student.tipo_matricula,
        student.punto_matricula ?? '',
      ]
        .join(' ')
        .toLowerCase()
        .includes(normalizedSearch)
    })
  }, [estadoFilter, normalizedSearch, selectedYear, students, tipoFilter])

  const selectedYearSummary = years.find((year) => String(year.year) === selectedYear)
  const filteredSummaryTotal = filteredSummary.reduce((sum, item) => sum + (item.total_estudiantes || 0), 0)
  const filteredStudentsTotal = filteredStudents.length
  const listSummary = selectedListLabel
    ? `${selectedListLabel} / ${filteredStudentsTotal} estudiantes`
    : 'Selecciona una tarjeta'

  const handleYearClick = async (yearValue: string, label: string, year: number | null) => {
    setSelectedYear(yearValue)
    setSelectedListLabel(label)
    await onSelectYear(year)
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Periodo matriculados</p>
          <h2>{displayName}</h2>
          <p className="report-description">
            Cada registro cuenta una sola vez por estudiante y se agrupa por año, tipo y estado para evitar desfases.
          </p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Periodo matriculados</span>
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
          <h2>{years.reduce((sum, year) => sum + year.total, 0)}</h2>
          <small>Base {years.length > 0 ? years[0].year : '-'}</small>
        </button>
        {years.map((year) => (
          <button
            key={year.year}
            type="button"
            className={`student-card student-card--stat periodo-year-card ${String(year.year) === selectedYear ? 'periodo-year-card--active' : ''}`}
            onClick={() => handleYearClick(String(year.year), `Año ${year.year}`, year.year)}
          >
            <p>Año {year.year}</p>
            <h2>{year.total}</h2>
            <small>Acumulado {year.acumulado} | R {year.r} / H {year.h}</small>
          </button>
        ))}
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Inscripciones por periodo</h3>
            <span>{loading ? 'Cargando...' : `${filteredSummary.length} filas`}</span>
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
            <label>
              <span>Estado</span>
              <select value={estadoFilter} onChange={(event) => setEstadoFilter(event.target.value as 'ALL' | 'A' | 'P' | 'R' | 'G')}>
                <option value="ALL">Todos</option>
                <option value="A">Activo</option>
                <option value="P">Inactivo</option>
                <option value="R">Retirado</option>
                <option value="G">Graduado</option>
              </select>
            </label>
            <label>
              <span>Buscar</span>
              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Año, tipo o estado"
              />
            </label>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={onLoadSummary} disabled={loading}>
              {loading ? 'Actualizando...' : 'Actualizar resumen'}
            </button>
          </div>

          {selectedYearSummary ? (
            <div className="periodo-inline-summary">
              <button type="button" className="periodo-filter-pill">Total {selectedYearSummary.total}</button>
              <button type="button" className="periodo-filter-pill">Activos {selectedYearSummary.activos}</button>
              <button type="button" className="periodo-filter-pill">Inactivos {selectedYearSummary.inactivos}</button>
              <button type="button" className="periodo-filter-pill">Retirados {selectedYearSummary.retirados}</button>
              <button type="button" className="periodo-filter-pill">Graduados {selectedYearSummary.graduados}</button>
            </div>
          ) : null}

          {error ? <p className="teams-error">{error}</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Año</th>
                  <th>Periodo</th>
                  <th>Detalle</th>
                  <th>Tipo</th>
                  <th>Estado</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {filteredSummary.map((item, index) => (
                  <tr key={`${item.anio_periodo ?? 'na'}-${item.tipo_matricula}-${item.estado_codigo ?? 'na'}-${index}`}>
                    <td>{item.anio_periodo ?? 'Sin año'}</td>
                    <td>{item.codigo_periodo || 'Sin periodo'}</td>
                    <td>{item.detalle_periodo || '-'}</td>
                    <td>{item.tipo_matricula}</td>
                    <td>{item.estado_nombre ?? item.estado_codigo ?? 'Sin estado'}</td>
                    <td>{item.total_estudiantes}</td>
                  </tr>
                ))}
                {filteredSummary.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Sin resultados para los filtros seleccionados.</td>
                  </tr>
                ) : null}
              </tbody>
              {filteredSummary.length > 0 ? (
                <tfoot>
                  <tr>
                    <td colSpan={5}>Total estudiantes</td>
                    <td>{filteredSummaryTotal}</td>
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Estudiantes únicos del año</h3>
            <span>{loadingStudents ? 'Cargando...' : listSummary}</span>
          </div>

          {studentsError ? <p className="teams-error">{studentsError}</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Nombre</th>
                  <th>Año</th>
                  <th>Tipo</th>
                  <th>Estado</th>
                  <th>Carrera</th>
                </tr>
              </thead>
              <tbody>
                {filteredStudents.map((student) => (
                  <tr key={`${student.codigo_estud}-${student.anio_periodo ?? 'na'}-${student.tipo_matricula}`}>
                    <td>{student.codigo_estud}</td>
                    <td>{student.nombre_estudiante}</td>
                    <td>{student.anio_periodo ?? 'Sin año'}</td>
                    <td>{student.tipo_matricula}</td>
                    <td>{student.estado_nombre}</td>
                    <td>{student.nombre_carrera}</td>
                  </tr>
                ))}
                {filteredStudents.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      {selectedListLabel
                        ? 'Sin estudiantes para la tarjeta seleccionada.'
                        : 'Selecciona una tarjeta de año para cargar estudiantes.'}
                    </td>
                  </tr>
                ) : null}
              </tbody>
              {filteredStudents.length > 0 ? (
                <tfoot>
                  <tr>
                    <td colSpan={5}>Total estudiantes</td>
                    <td>{filteredStudentsTotal}</td>
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
