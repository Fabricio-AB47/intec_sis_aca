import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  applyMoodleManualEnrollment,
  fetchMoodleManualEnrollmentCatalog,
  previewMoodleManualEnrollment,
  searchMoodleManualEnrollment,
} from '../../lib/api'
import type {
  MoodleManualEnrollmentApplyResponse,
  MoodleManualEnrollmentCatalogResponse,
  MoodleManualEnrollmentPreviewResponse,
  MoodleManualEnrollmentRole,
  MoodleManualEnrollmentSearchResponse,
} from '../../types/app'

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudo completar la matrícula manual en Moodle.'
}

function parseNames(value: string): string[] {
  const seen = new Set<string>()
  return value
    .split(/\r?\n/)
    .map((name) => name.trim().replace(/\s+/g, ' '))
    .filter((name) => {
      if (!name) return false
      const key = name.toLocaleLowerCase('es')
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function statusLabel(status: string): string {
  return {
    UNICO: 'Coincidencia única',
    AMBIGUO: 'Requiere selección',
    NO_ENCONTRADO: 'No encontrado',
    ACTIVO: 'Activo',
    SUSPENDIDO: 'Suspendido',
    NO_CONFIRMADO: 'No confirmado',
    EXISTENTE: 'Ya asignado',
    OTRO_ROL: 'Matriculado con otro rol',
    NO_MATRICULADO: 'Sin matrícula',
    SUSPENDIDA: 'Matrícula suspendida',
    LISTO: 'Listo',
    BLOQUEADO: 'Bloqueado',
    MATRICULAR: 'Matricular',
    ASIGNAR_ROL: 'Agregar rol',
    NINGUNA: 'Sin cambios',
    MATRICULADO: 'Completado',
  }[status] ?? status
}

function statusTone(status: string): string {
  if (['UNICO', 'ACTIVO', 'LISTO', 'MATRICULADO'].includes(status)) return 'is-success'
  if (['AMBIGUO', 'EXISTENTE', 'OTRO_ROL', 'NINGUNA'].includes(status)) return 'is-warning'
  return 'is-error'
}

export function MoodleManualEnrollmentPanel() {
  const [catalog, setCatalog] = useState<MoodleManualEnrollmentCatalogResponse | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [courseSearch, setCourseSearch] = useState('')
  const [courseId, setCourseId] = useState(0)
  const [role, setRole] = useState<MoodleManualEnrollmentRole>('student')
  const [namesText, setNamesText] = useState('')
  const [searchResult, setSearchResult] = useState<MoodleManualEnrollmentSearchResponse | null>(null)
  const [selectionByQuery, setSelectionByQuery] = useState<Record<number, number>>({})
  const [preview, setPreview] = useState<MoodleManualEnrollmentPreviewResponse | null>(null)
  const [applyResult, setApplyResult] = useState<MoodleManualEnrollmentApplyResponse | null>(null)
  const [loading, setLoading] = useState<'search' | 'preview' | 'apply' | ''>('')
  const [error, setError] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true)
    setError('')
    try {
      setCatalog(await fetchMoodleManualEnrollmentCatalog())
    } catch (loadError) {
      setError(errorMessage(loadError))
    } finally {
      setCatalogLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  const resetResults = () => {
    setSearchResult(null)
    setSelectionByQuery({})
    setPreview(null)
    setApplyResult(null)
    setConfirmOpen(false)
    setError('')
  }

  const filteredCourses = useMemo(() => {
    const query = courseSearch.trim().toLocaleLowerCase('es')
    const courses = catalog?.courses ?? []
    const matches = query
      ? courses.filter((course) => [
        course.fullname,
        course.shortname,
        course.idnumber,
        course.category,
      ].some((value) => value.toLocaleLowerCase('es').includes(query)))
      : courses
    const limited = matches.slice(0, 150)
    const selected = courses.find((course) => course.id === courseId)
    return selected && !limited.some((course) => course.id === selected.id)
      ? [selected, ...limited]
      : limited
  }, [catalog?.courses, courseId, courseSearch])

  const names = useMemo(() => parseNames(namesText), [namesText])
  const selectedIds = useMemo(
    () => Array.from(new Set(Object.values(selectionByQuery).filter((value) => value > 0))),
    [selectionByQuery],
  )
  const selectedOccurrences = Object.values(selectionByQuery).filter((value) => value > 0).length
  const duplicateSelections = selectedOccurrences - selectedIds.length
  const unresolvedQueries = searchResult
    ? searchResult.queries.filter((query) => !selectionByQuery[query.index]).length
    : 0

  const selectRole = (value: MoodleManualEnrollmentRole) => {
    if (value === role) return
    setRole(value)
    resetResults()
  }

  const submitSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setPreview(null)
    setApplyResult(null)
    if (!courseId) {
      setError('Seleccione el curso Moodle de destino.')
      return
    }
    if (!names.length) {
      setError('Ingrese al menos un nombre para buscar en Moodle.')
      return
    }
    if (names.length > (catalog?.limits.names ?? 100)) {
      setError(`Puede buscar un máximo de ${catalog?.limits.names ?? 100} nombres.`)
      return
    }
    if (names.some((name) => name.length > 256)) {
      setError('Cada nombre puede contener hasta 256 caracteres.')
      return
    }

    setLoading('search')
    try {
      const response = await searchMoodleManualEnrollment({
        course_id: courseId,
        role,
        names,
      })
      setSearchResult(response)
      setSelectionByQuery(Object.fromEntries(
        response.queries
          .filter((query) => query.selected_user_id)
          .map((query) => [query.index, Number(query.selected_user_id)]),
      ))
    } catch (searchError) {
      setSearchResult(null)
      setSelectionByQuery({})
      setError(errorMessage(searchError))
    } finally {
      setLoading('')
    }
  }

  const loadPreview = async () => {
    setError('')
    setApplyResult(null)
    if (!selectedIds.length) {
      setError('Seleccione al menos un usuario Moodle.')
      return
    }
    if (unresolvedQueries) {
      setError('Resuelva cada nombre antes de generar la vista previa.')
      return
    }
    if (duplicateSelections) {
      setError('Un mismo usuario fue seleccionado para más de un nombre. Corrija la selección.')
      return
    }
    setLoading('preview')
    try {
      setPreview(await previewMoodleManualEnrollment({
        course_id: courseId,
        role,
        user_ids: selectedIds,
      }))
    } catch (previewError) {
      setPreview(null)
      setError(errorMessage(previewError))
    } finally {
      setLoading('')
    }
  }

  const applyEnrollment = async () => {
    if (!preview) return
    setLoading('apply')
    setError('')
    try {
      const response = await applyMoodleManualEnrollment({
        course_id: courseId,
        role,
        user_ids: selectedIds,
        preview_fingerprint: preview.preview_fingerprint,
      })
      setApplyResult(response)
      setPreview(null)
      setConfirmOpen(false)
    } catch (applyError) {
      setConfirmOpen(false)
      setError(errorMessage(applyError))
    } finally {
      setLoading('')
    }
  }

  const selectedCourse = catalog?.courses.find((course) => course.id === courseId)
  const roleLabel = role === 'student' ? 'estudiante' : 'docente'

  return (
    <div className="moodle-section moodle-manual-enrollment">
      <div className="moodle-section__heading">
        <div>
          <span>Matrícula directa en Moodle</span>
          <h2>Asignación masiva por nombres</h2>
          <p>Curso único, identidades validadas y rol independiente.</p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={catalogLoading || Boolean(loading)}
          onClick={() => void loadCatalog()}
        >
          Actualizar catálogo
        </button>
      </div>

      {error && <div className="moodle-alert moodle-alert--error">{error}</div>}
      {catalogLoading && <div className="moodle-empty">Consultando cursos y permisos Moodle...</div>}
      {catalog && !catalog.capability.enabled && (
        <div className="moodle-alert moodle-alert--warning">{catalog.capability.reason}</div>
      )}

      {catalog && (
        <>
          <div className="moodle-user-modes" aria-label="Tipo de matrícula">
            <button
              type="button"
              className={role === 'student' ? 'is-active' : ''}
              disabled={Boolean(loading)}
              onClick={() => selectRole('student')}
            >
              Estudiantes
            </button>
            <button
              type="button"
              className={role === 'teacher' ? 'is-active' : ''}
              disabled={Boolean(loading)}
              onClick={() => selectRole('teacher')}
            >
              Docentes
            </button>
          </div>

          <form className="moodle-manual-form" onSubmit={submitSearch}>
            <section className="moodle-manual-course">
              <div className="moodle-manual-step-heading">
                <span>1</span>
                <div>
                  <strong>Curso Moodle</strong>
                  <small>{catalog.courses.length.toLocaleString('es-EC')} curso(s) disponible(s)</small>
                </div>
              </div>
              <label>
                <span>Buscar curso</span>
                <input
                  type="search"
                  value={courseSearch}
                  placeholder="Nombre, nombre corto o código"
                  disabled={Boolean(loading)}
                  onChange={(event) => setCourseSearch(event.target.value)}
                />
              </label>
              <label>
                <span>Curso de destino</span>
                <select
                  value={courseId || ''}
                  disabled={Boolean(loading)}
                  onChange={(event) => {
                    setCourseId(Number(event.target.value) || 0)
                    resetResults()
                  }}
                >
                  <option value="">Seleccione un curso Moodle</option>
                  {filteredCourses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.fullname} · {course.shortname || `ID ${course.id}`}
                      {!course.visible ? ' · Oculto' : ''}
                    </option>
                  ))}
                </select>
                <small>
                  {filteredCourses.length} coincidencia(s) visible(s)
                  {selectedCourse?.category ? ` · ${selectedCourse.category}` : ''}
                </small>
              </label>
            </section>

            <section className="moodle-manual-names">
              <div className="moodle-manual-step-heading">
                <span>2</span>
                <div>
                  <strong>Nombres de {role === 'student' ? 'estudiantes' : 'docentes'}</strong>
                  <small>{names.length} de {catalog.limits.names}</small>
                </div>
              </div>
              <label>
                <span>Un nombre, correo, usuario o cédula por línea</span>
                <textarea
                  rows={8}
                  maxLength={25_700}
                  value={namesText}
                  disabled={Boolean(loading)}
                  placeholder={'Nombres y apellidos\ncorreo@intec.edu.ec\n1712345678'}
                  onChange={(event) => {
                    setNamesText(event.target.value)
                    resetResults()
                  }}
                />
              </label>
              <button
                type="submit"
                className="moodle-button moodle-button--primary"
                disabled={Boolean(loading) || !courseId || !names.length}
              >
                {loading === 'search' ? 'Buscando...' : 'Buscar y validar en Moodle'}
              </button>
            </section>
          </form>
        </>
      )}

      {searchResult && (
        <section className="moodle-manual-results" aria-live="polite">
          <header>
            <div>
              <span>3</span>
              <div>
                <strong>Resolver identidades</strong>
                <small>{selectedIds.length} usuario(s) seleccionado(s)</small>
              </div>
            </div>
            <button
              type="button"
              className="moodle-button moodle-button--primary"
              disabled={Boolean(loading) || !selectedIds.length || Boolean(unresolvedQueries) || Boolean(duplicateSelections)}
              onClick={() => void loadPreview()}
            >
              {loading === 'preview' ? 'Validando...' : 'Generar vista previa'}
            </button>
          </header>

          <div className="moodle-manual-summary">
            <div><span>Consultas</span><strong>{searchResult.summary.queries}</strong></div>
            <div><span>Únicas</span><strong>{searchResult.summary.unique}</strong></div>
            <div><span>Ambiguas</span><strong>{searchResult.summary.ambiguous}</strong></div>
            <div><span>No encontradas</span><strong>{searchResult.summary.not_found}</strong></div>
            <div><span>Seleccionados</span><strong>{selectedIds.length}</strong></div>
          </div>

          {(unresolvedQueries > 0 || duplicateSelections > 0) && (
            <div className="moodle-alert moodle-alert--warning">
              {unresolvedQueries > 0 && `${unresolvedQueries} nombre(s) requieren una selección válida. `}
              {duplicateSelections > 0 && `${duplicateSelections} selección(es) apuntan al mismo usuario.`}
            </div>
          )}

          <div className="moodle-manual-query-list">
            {searchResult.queries.map((query) => (
              <article key={`${query.index}-${query.query}`}>
                <header>
                  <div>
                    <strong>{query.index}. {query.query}</strong>
                    <small>{query.candidates.length} coincidencia(s)</small>
                  </div>
                  <span className={`moodle-manual-status ${statusTone(query.status)}`}>
                    {statusLabel(query.status)}
                  </span>
                </header>
                {query.candidates.length ? (
                  <div className="moodle-manual-candidates">
                    {query.candidates.map((candidate) => (
                      <label
                        key={candidate.id}
                        className={!candidate.selectable ? 'is-disabled' : ''}
                      >
                        <input
                          type="radio"
                          name={`manual-user-${query.index}`}
                          value={candidate.id}
                          checked={selectionByQuery[query.index] === candidate.id}
                          disabled={!candidate.selectable || Boolean(loading)}
                          onChange={() => {
                            setSelectionByQuery((current) => ({
                              ...current,
                              [query.index]: candidate.id,
                            }))
                            setPreview(null)
                            setApplyResult(null)
                          }}
                        />
                        <span className="moodle-manual-candidate-identity">
                          <strong>{candidate.fullname}</strong>
                          <small>{candidate.email || candidate.username || `ID ${candidate.id}`}</small>
                        </span>
                        <span className="moodle-manual-candidate-reference">
                          <strong>{candidate.idnumber || 'Sin cédula/código'}</strong>
                          <small>{candidate.username}</small>
                        </span>
                        <span className={`moodle-manual-status ${statusTone(candidate.account_status)}`}>
                          {statusLabel(candidate.account_status)}
                        </span>
                        <span className={`moodle-manual-status ${statusTone(candidate.enrollment_status)}`}>
                          {statusLabel(candidate.enrollment_status)}
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p>No existe una identidad Moodle que coincida de forma segura.</p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {preview && (
        <section className="moodle-manual-preview">
          <header>
            <div>
              <span>4</span>
              <div>
                <strong>Vista previa de matrícula</strong>
                <small>{preview.course.fullname} · Rol {preview.role_label}</small>
              </div>
            </div>
            <button
              type="button"
              className="moodle-button moodle-button--success"
              disabled={!preview.can_apply || Boolean(loading)}
              onClick={() => setConfirmOpen(true)}
            >
              Aplicar en Moodle
            </button>
          </header>
          <div className="moodle-manual-summary">
            <div><span>Seleccionados</span><strong>{preview.summary.selected}</strong></div>
            <div><span>Listos</span><strong>{preview.summary.ready}</strong></div>
            <div><span>Ya asignados</span><strong>{preview.summary.existing}</strong></div>
            <div><span>Nuevas matrículas</span><strong>{preview.summary.new_enrollments}</strong></div>
            <div><span>Roles por agregar</span><strong>{preview.summary.role_additions}</strong></div>
          </div>
          {preview.summary.blocked > 0 && (
            <div className="moodle-alert moodle-alert--error">
              {preview.summary.blocked} usuario(s) bloqueado(s). La operación no puede aplicarse.
            </div>
          )}
          <div className="moodle-table-wrap">
            <table className="moodle-table moodle-manual-table">
              <thead>
                <tr>
                  <th>Persona</th>
                  <th>Cuenta Moodle</th>
                  <th>Roles actuales</th>
                  <th>Acción</th>
                  <th>Validación</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.fullname}</strong><small>ID Moodle {item.id}</small></td>
                    <td>{item.email || item.username}<small>{item.username}</small></td>
                    <td>{item.current_roles.map((currentRole) => currentRole.name || currentRole.shortname).join(', ') || 'Sin roles en el curso'}</td>
                    <td><span className={`moodle-manual-status ${statusTone(item.action)}`}>{statusLabel(item.action)}</span></td>
                    <td><span className={`moodle-manual-status ${statusTone(item.status)}`}>{statusLabel(item.status)}</span><small>{item.message}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {applyResult && (
        <section className="moodle-manual-complete" aria-live="polite">
          <div className="moodle-alert moodle-alert--success">
            Se asignó el rol {applyResult.role_label.toLocaleLowerCase('es')} a {applyResult.summary.enrolled} usuario(s) y se verificó el resultado en Moodle.
          </div>
          {applyResult.warning && <div className="moodle-alert moodle-alert--warning">{applyResult.warning}</div>}
          <div className="moodle-table-wrap">
            <table className="moodle-table moodle-manual-table">
              <thead><tr><th>Persona</th><th>Cuenta</th><th>Resultado</th><th>Detalle</th></tr></thead>
              <tbody>
                {applyResult.items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.fullname}</strong><small>ID Moodle {item.id}</small></td>
                    <td>{item.email || item.username}</td>
                    <td><span className={`moodle-manual-status ${statusTone(item.status)}`}>{statusLabel(item.status)}</span></td>
                    <td>{item.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {confirmOpen && preview && (
        <div className="moodle-confirm-overlay" role="presentation" onMouseDown={() => setConfirmOpen(false)}>
          <div
            className="moodle-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-manual-confirm-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Confirmación final</span>
                <h2 id="moodle-manual-confirm-title">Matricular {preview.summary.ready} {roleLabel}(s)</h2>
              </div>
            </div>
            <div className="moodle-confirm-dialog__body">
              <p><strong>Curso:</strong> {preview.course.fullname}</p>
              <p><strong>Rol:</strong> {preview.role_label} · ID {preview.role_id}</p>
              <p>La selección se validará nuevamente antes de asignar el rol.</p>
            </div>
            <div className="moodle-confirm-dialog__actions">
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={loading === 'apply'}
                onClick={() => setConfirmOpen(false)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="moodle-button moodle-button--success"
                disabled={loading === 'apply'}
                onClick={() => void applyEnrollment()}
              >
                {loading === 'apply' ? 'Aplicando...' : 'Confirmar matrícula'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
