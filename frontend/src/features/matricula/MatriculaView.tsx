import { useState } from 'react'

import type {
  MatriculaStudentItem,
  MatriculaSummaryItem,
  MatriculaTipo,
} from '../../types/app'

type MatriculaViewProps = {
  displayName: string
  loadingSummary: boolean
  loadingList: boolean
  summaryError: string
  listError: string
  summaryItems: MatriculaSummaryItem[]
  totalsByEstado: Record<string, number>
  selectedTipo: MatriculaTipo
  selectedEstado: string
  students: MatriculaStudentItem[]
  onLoadSummary: () => void
  onSelectTipo: (tipo: MatriculaTipo) => void
  onSelectEstado: (estado: string) => void
  onSelectEstadoGlobal: (estado: string) => void
  onSelectTotalRh: () => void
}

const estadoOptions = [
  { label: 'Activo', codigo: 'A' },
  { label: 'Graduado', codigo: 'G' },
  { label: 'Inactivo', codigo: 'P' },
  { label: 'Retirado', codigo: 'R' },
] as const

export function MatriculaView({
  displayName,
  loadingSummary,
  loadingList,
  summaryError,
  listError,
  summaryItems,
  totalsByEstado,
  selectedTipo,
  selectedEstado,
  students,
  onLoadSummary,
  onSelectTipo,
  onSelectEstado,
  onSelectEstadoGlobal,
  onSelectTotalRh,
}: Readonly<MatriculaViewProps>) {
  const [isListModalOpen, setIsListModalOpen] = useState(false)
  const [listScopeLabel, setListScopeLabel] = useState('')
  const [summaryScope, setSummaryScope] = useState<'unificado' | 'tipo'>('unificado')
  const totals: Record<string, number> = { R: 0, H: 0 }
  const fallbackEstadoTotals: Record<string, number> = Object.fromEntries(
    estadoOptions.map(({ codigo }) => [codigo, 0])
  )

  for (const item of summaryItems) {
    if (item.tipo_matricula in totals) {
      totals[item.tipo_matricula] += item.total_estudiantes
    }
    if (item.estado_codigo in fallbackEstadoTotals) {
      fallbackEstadoTotals[item.estado_codigo] += item.total_estudiantes
    }
  }

  const visibleTipos = (['R', 'H'] as const).filter((tipo) => totals[tipo] > 0)
  const tipoCards = visibleTipos.length > 0 ? visibleTipos : (['R'] as const)
  const hasBackendEstadoTotals = Object.values(totalsByEstado).some((value) => value > 0)
  const unifiedTotals: Record<string, number> = hasBackendEstadoTotals
    ? Object.fromEntries(estadoOptions.map(({ codigo }) => [codigo, totalsByEstado[codigo] ?? 0]))
    : Object.fromEntries(estadoOptions.map(({ codigo }) => [codigo, fallbackEstadoTotals[codigo] ?? 0]))
  const unifiedTotalGeneral = Object.values(unifiedTotals).reduce((sum, value) => sum + value, 0)
  const typeRows = summaryItems.filter((item) => item.tipo_matricula === selectedTipo)
  const summaryRows =
    summaryScope === 'unificado'
      ? estadoOptions
          .map(({ label, codigo }) => ({
            estado_codigo: codigo,
            estado_nombre: label,
            total_estudiantes: unifiedTotals[codigo] ?? 0,
            tipo_label: 'Reporte unificado',
          }))
          .filter((row) => row.total_estudiantes > 0)
      : typeRows.map((row) => ({
          estado_codigo: row.estado_codigo,
          estado_nombre: row.estado_nombre,
          total_estudiantes: row.total_estudiantes,
          tipo_label: `Tipo ${row.tipo_matricula}`,
        }))
  const getEstadoTotal = (codigo: string) => totalsByEstado[codigo] ?? fallbackEstadoTotals[codigo] ?? 0

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Validacion de matricula</p>
          <h1>Estados por tipo R y H</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Matricula</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {tipoCards.map((tipo) => (
          <article key={tipo} className="student-card student-card--stat matricula-stat-card">
            <p>Tipo {tipo}</p>
            <h2>{totals[tipo]}</h2>
            <small>Estudiantes unicos por tipo</small>
          </article>
        ))}
      </section>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        {estadoOptions.map(({ label: estado, codigo }) => (
          <button
            key={estado}
            type="button"
            className="student-card student-card--stat matricula-stat-card"
            onClick={() => {
              setListScopeLabel('Cruce unico global')
              setIsListModalOpen(true)
              void onSelectEstadoGlobal(codigo)
            }}
          >
            <p>{estado}</p>
            <h2>{getEstadoTotal(codigo)}</h2>
            <small>Primera matricula historica</small>
          </button>
        ))}
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Resumen por estado</h3>
            <span>{loadingSummary ? 'Cargando...' : summaryScope === 'unificado' ? 'Reporte unificado' : `Tipo ${selectedTipo}`}</span>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={onLoadSummary} disabled={loadingSummary}>
              {loadingSummary ? 'Actualizando...' : 'Actualizar resumen'}
            </button>
            {tipoCards.map((tipo) => (
              <button
                key={tipo}
                type="button"
                onClick={() => {
                  setSummaryScope('tipo')
                  onSelectTipo(tipo)
                }}
              >
                Tipo {tipo}
              </button>
            ))}
          </div>

          {summaryError ? <p className="teams-error">{summaryError}</p> : null}
          <div className="periodo-inline-summary">
            <button
              type="button"
              className="periodo-filter-pill periodo-filter-pill--active"
              onClick={() => {
                setListScopeLabel('Reporte unificado')
                setIsListModalOpen(true)
                setSummaryScope('unificado')
                void onSelectTotalRh()
              }}
            >
              Total R + H {unifiedTotalGeneral}
            </button>
            {estadoOptions.map(({ label: estado, codigo }) => (
              <button
                key={`rh-${codigo}`}
                type="button"
                className={`periodo-filter-pill ${selectedEstado === codigo ? 'periodo-filter-pill--active' : ''}`}
                onClick={() => {
                  setListScopeLabel('Reporte unificado')
                  setIsListModalOpen(true)
                  setSummaryScope('unificado')
                  void onSelectEstadoGlobal(codigo)
                }}
              >
                {estado} {unifiedTotals[codigo] ?? 0}
              </button>
            ))}
          </div>
          <div className="matricula-summary-grid">
            {summaryRows.map((row) => (
              <button
                key={`${row.tipo_label}-${row.estado_codigo}`}
                type="button"
                className={`matricula-state-btn ${selectedEstado === row.estado_codigo ? 'matricula-state-btn--active' : ''}`}
                onClick={() => {
                  setListScopeLabel(row.tipo_label)
                  setIsListModalOpen(true)
                  if (summaryScope === 'unificado') {
                    void onSelectEstadoGlobal(row.estado_codigo)
                  } else {
                    void onSelectEstado(row.estado_codigo)
                  }
                }}
              >
                <strong>{row.estado_nombre}</strong>
                <span>{row.tipo_label}</span>
                <small>{row.total_estudiantes} estudiantes</small>
              </button>
            ))}
          </div>
        </article>

        <article className="student-card student-card--wide matricula-help-card">
          <p className="empty-block">
            El resumen cuenta estudiantes de DATOS_ESTUD con al menos una materia en CARRERAXESTUD,
            validada contra PENSUM y CARRERAS.
          </p>
        </article>
      </section>

      {isListModalOpen ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>Listado de estudiantes</h3>
                <span>
                  {listScopeLabel || `Tipo ${selectedTipo}`}
                  {selectedEstado ? ` / Estado ${selectedEstado}` : ''}
                </span>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setIsListModalOpen(false)}>
                Cerrar
              </button>
            </div>

            {loadingList ? <p className="teams-message">Consultando estudiantes...</p> : null}
            {listError ? <p className="teams-error">{listError}</p> : null}

            <div className="matricula-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Periodo</th>
                    <th>Correo personal</th>
                    <th>Nombre Carrera</th>
                  </tr>
                </thead>
                <tbody>
                  {students.length > 0 ? (
                    students.map((student) => (
                      <tr key={`${student.tipo_matricula}-${student.codigo_estud}-${student.periodo || 'na'}`}>
                        <td>{student.nombre_estudiante}</td>
                        <td>{student.tipo_matricula}</td>
                        <td>{student.estado_nombre}</td>
                        <td>{student.detalle_periodo || student.periodo || '-'}</td>
                        <td>{student.correo_personal || '-'}</td>
                        <td>{student.nombre_carrera || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>Sin datos para los filtros seleccionados.</td>
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
