import { useEffect, useMemo, useState } from 'react'

import {
  fetchAcademicTeacherStateCatalog,
  fetchAcademicTeacherStates,
  updateAcademicTeacherState,
} from '../../lib/api'
import type { AcademicTeacherStateItem, AcademicTeacherStateOption } from '../../types/app'

type EstadoDocenteViewProps = {
  displayName: string
}

const VALID_TEACHER_STATES = new Set(['A', 'P'])

function valueOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function teacherLabel(teacher: AcademicTeacherStateItem): string {
  return teacher.descripcion || teacher.login || teacher.correo || `Docente ${teacher.codigo_doc}`
}

function statusLabel(teacher: AcademicTeacherStateItem): string {
  if (teacher.estado_nombre && teacher.estado) {
    return `${teacher.estado_nombre} (${teacher.estado})`
  }
  return teacher.estado_nombre || teacher.estado || 'Sin estado'
}

export function EstadoDocenteView({ displayName }: Readonly<EstadoDocenteViewProps>) {
  const [states, setStates] = useState<AcademicTeacherStateOption[]>([])
  const [teachers, setTeachers] = useState<AcademicTeacherStateItem[]>([])
  const [selectedTeacher, setSelectedTeacher] = useState<AcademicTeacherStateItem | null>(null)
  const [query, setQuery] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [targetState, setTargetState] = useState('')
  const [validateUser, setValidateUser] = useState(true)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const summary = useMemo(() => {
    return teachers.reduce(
      (current, teacher) => {
        current.total += 1
        if (teacher.usuario_validado) {
          current.conUsuario += 1
        } else {
          current.sinUsuario += 1
        }

        const status = teacher.estado || 'SIN ESTADO'
        current.porEstado[status] = (current.porEstado[status] ?? 0) + 1
        return current
      },
      { total: 0, conUsuario: 0, sinUsuario: 0, porEstado: {} as Record<string, number> },
    )
  }, [teachers])

  const selectedStateName =
    states.find((state) => state.codigo === targetState)?.nombre ||
    states.find((state) => state.codigo === selectedTeacher?.estado)?.nombre ||
    ''

  async function loadCatalog() {
    const payload = await fetchAcademicTeacherStateCatalog()
    const items = (payload.items || []).filter((state) => VALID_TEACHER_STATES.has(state.codigo.toUpperCase()))
    setStates(items)
    if (!targetState && items.length > 0) {
      setTargetState(items[0].codigo)
    }
  }

  async function loadTeachers() {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchAcademicTeacherStates(query.trim(), stateFilter, validateUser, 10000)
      const items = payload.items || []
      setTeachers(items)
      setSelectedTeacher((current) => {
        if (!current) return null
        return items.find((teacher) => teacher.codigo_doc === current.codigo_doc) || null
      })
      if (items.length === 0) {
        setMessage('No se encontraron docentes para los filtros indicados.')
      }
    } catch (apiError) {
      setError(handleError(apiError, 'Error consultando estados de docentes'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadInitialData() {
      setLoading(true)
      setError('')
      try {
        const [statePayload, teacherPayload] = await Promise.all([
          fetchAcademicTeacherStateCatalog(),
          fetchAcademicTeacherStates('', '', true, 10000),
        ])
        if (cancelled) return
        const stateItems = (statePayload.items || []).filter((state) => VALID_TEACHER_STATES.has(state.codigo.toUpperCase()))
        setStates(stateItems)
        setTargetState(stateItems[0]?.codigo || '')
        setTeachers(teacherPayload.items || [])
      } catch (apiError) {
        if (!cancelled) {
          setError(handleError(apiError, 'Error cargando estados de docentes'))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadInitialData()

    return () => {
      cancelled = true
    }
  }, [])

  async function refreshAll() {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await loadCatalog()
      await loadTeachers()
    } finally {
      setLoading(false)
    }
  }

  async function saveTeacherState() {
    if (!selectedTeacher) {
      setError('Selecciona un docente antes de actualizar el estado.')
      return
    }
    if (!selectedTeacher.usuario_validado) {
      setError('El docente seleccionado no tiene usuario vinculado en USUARIOS.')
      return
    }
    if (!targetState) {
      setError('Selecciona el estado que se aplicara al docente.')
      return
    }
    if (!VALID_TEACHER_STATES.has(targetState)) {
      setError('Solo se permite actualizar a Activo o Inactivo.')
      return
    }

    const teacherCode = Number(selectedTeacher.codigo_doc)
    if (!Number.isFinite(teacherCode)) {
      setError('El codigo del docente no es valido.')
      return
    }

    const confirmed = globalThis.confirm(
      `Actualizar estado de ${teacherLabel(selectedTeacher)} a ${selectedStateName || targetState}?`,
    )
    if (!confirmed) return

    setSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await updateAcademicTeacherState({
        codigo_doc: teacherCode,
        codigo_usuario: selectedTeacher.codigo_usuario ? Number(selectedTeacher.codigo_usuario) : teacherCode,
        estado_codigo: targetState,
      })
      const updated = payload.docente || {
        ...selectedTeacher,
        estado: payload.estado?.codigo || targetState,
        estado_nombre: payload.estado?.nombre || selectedStateName,
      }
      setSelectedTeacher(updated)
      setTeachers((current) =>
        current.map((teacher) => (teacher.codigo_doc === updated.codigo_doc ? updated : teacher)),
      )
      setMessage(payload.message || 'Estado del docente actualizado correctamente.')
    } catch (apiError) {
      setError(handleError(apiError, 'Error actualizando estado del docente'))
    } finally {
      setSaving(false)
    }
  }

  function selectTeacher(teacher: AcademicTeacherStateItem) {
    setSelectedTeacher(teacher)
    setTargetState(teacher.estado || states[0]?.codigo || '')
    setError('')
    setMessage('')
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Estado docente</p>
          <h2>{displayName}</h2>
          <p className="report-description">
            Consulta docentes desde DATOSDOCENTE, valida el usuario vinculado y actualiza solo entre Activo e Inactivo.
          </p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Actualizacion de estado</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        <article className="student-card student-card--stat">
          <p>Docentes listados</p>
          <h2>{summary.total}</h2>
          <small>{loading ? 'Consultando...' : 'DATOSDOCENTE'}</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Con usuario</p>
          <h2>{summary.conUsuario}</h2>
          <small>USUARIOS validado</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Sin usuario</p>
            <h2>{summary.sinUsuario}</h2>
          <small>Fuera de actualizacion</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Estado filtrado</p>
          <h2>{stateFilter || 'ALL'}</h2>
          <small>{stateFilter ? states.find((state) => state.codigo === stateFilter)?.nombre : 'Todos'}</small>
        </article>
      </section>

      <section className="student-grid student-grid--content estado-docente-grid">
        <article className="student-card student-card--wide estado-docente-list-card">
          <div className="card-head">
            <h3>Docentes</h3>
            <span>{loading ? 'Cargando...' : `${teachers.length} resultado(s)`}</span>
          </div>

          <div className="teams-controls estado-docente-controls">
            <label>
              <span>Buscar docente</span>
              <input
                value={query}
                placeholder="Cedula, login, correo o nombre"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void loadTeachers()
                  }
                }}
              />
            </label>
            <label>
              <span>Estado actual</span>
              <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                <option value="">Todos</option>
                {states.map((state) => (
                  <option key={state.codigo} value={state.codigo}>
                    {state.nombre} ({state.codigo})
                  </option>
                ))}
              </select>
            </label>
            <label className="estado-docente-check">
              <input
                type="checkbox"
                checked={validateUser}
                onChange={(event) => setValidateUser(event.target.checked)}
              />
              Solo con usuario
            </label>
          </div>

          <div className="teams-actions estado-docente-actions">
            <button type="button" onClick={() => void loadTeachers()} disabled={loading}>
              {loading ? 'Buscando...' : 'Buscar docentes'}
            </button>
            <button type="button" onClick={() => void refreshAll()} disabled={loading}>
              Actualizar estados
            </button>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          <div className="matricula-table-wrap estado-docente-table-wrap">
            <table className="matricula-table estado-docente-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Docente</th>
                  <th>Cedula</th>
                  <th>Usuario</th>
                  <th>Estado</th>
                  <th>Info academica</th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((teacher) => {
                  const checked = selectedTeacher?.codigo_doc === teacher.codigo_doc
                  return (
                    <tr
                      key={teacher.codigo_doc}
                      className={checked ? 'estado-docente-row--active' : ''}
                      onClick={() => selectTeacher(teacher)}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => selectTeacher(teacher)}
                          onClick={(event) => event.stopPropagation()}
                        />
                      </td>
                      <td>
                        <strong>{teacherLabel(teacher)}</strong>
                        <span>{valueOrDash(teacher.correo || teacher.correo_personal)}</span>
                      </td>
                      <td>{valueOrDash(teacher.cedula)}</td>
                      <td>
                        <strong>{teacher.usuario_validado ? valueOrDash(teacher.login) : 'Sin usuario'}</strong>
                        <span>{valueOrDash(teacher.codigo_usuario)}</span>
                      </td>
                      <td>{statusLabel(teacher)}</td>
                      <td>
                        {valueOrDash(teacher.tipo_docente)} · {teacher.total_carreras_docente ?? 0} carrera(s) ·{' '}
                        {teacher.total_materias_docente ?? 0} materia(s)
                      </td>
                    </tr>
                  )
                })}
                {teachers.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Sin docentes para los filtros seleccionados.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="student-card estado-docente-detail-card">
          <div className="card-head">
            <h3>Analisis</h3>
            <span>{selectedTeacher ? selectedTeacher.codigo_doc : 'Sin docente'}</span>
          </div>

          {selectedTeacher ? (
            <>
              <div className="estado-docente-selected">
                <span>Docente</span>
                <strong>{teacherLabel(selectedTeacher)}</strong>
                <small>{statusLabel(selectedTeacher)}</small>
              </div>

              <div className="estado-docente-detail-list">
                <p><span>Cedula</span><strong>{valueOrDash(selectedTeacher.cedula)}</strong></p>
                <p><span>Login</span><strong>{valueOrDash(selectedTeacher.login)}</strong></p>
                <p><span>Correo</span><strong>{valueOrDash(selectedTeacher.correo || selectedTeacher.correo_personal)}</strong></p>
                <p><span>Telefono</span><strong>{valueOrDash(selectedTeacher.telefono || selectedTeacher.movil)}</strong></p>
                <p><span>Tipo docente</span><strong>{valueOrDash(selectedTeacher.tipo_docente)}</strong></p>
                <p><span>Unidad academica</span><strong>{valueOrDash(selectedTeacher.unidad_academica)}</strong></p>
                <p><span>Nivel formacion</span><strong>{valueOrDash(selectedTeacher.nivel_formacion)}</strong></p>
                <p><span>Tercer nivel</span><strong>{valueOrDash(selectedTeacher.tercer_nivel)}</strong></p>
                <p><span>Cuarto nivel</span><strong>{valueOrDash(selectedTeacher.cuarto_nivel)}</strong></p>
                <p><span>Fecha ingreso IES</span><strong>{valueOrDash(selectedTeacher.fecha_ingreso_ies)}</strong></p>
                <p><span>Matriculas docente</span><strong>{selectedTeacher.total_matriculas_docente ?? 0}</strong></p>
                <p><span>Ultimo periodo</span><strong>{valueOrDash(selectedTeacher.ultimo_periodo_docente)}</strong></p>
              </div>

              <label className="estado-docente-update-field">
                <span>Nuevo estado</span>
                <select value={targetState} onChange={(event) => setTargetState(event.target.value)}>
                  {states.map((state) => (
                    <option key={state.codigo} value={state.codigo}>
                      {state.nombre} ({state.codigo})
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="button"
                className="primary-action estado-docente-save"
                onClick={() => void saveTeacherState()}
                disabled={saving || !selectedTeacher.usuario_validado || !targetState}
              >
                {saving ? 'Actualizando...' : 'Actualizar estado'}
              </button>

              {!selectedTeacher.usuario_validado ? (
                <p className="form-error">Este docente no tiene usuario vinculado y no puede actualizarse.</p>
              ) : null}
            </>
          ) : (
            <p className="form-success">Selecciona un docente de la lista para ver sus datos y aplicar el cambio de estado.</p>
          )}
        </aside>
      </section>
    </>
  )
}
