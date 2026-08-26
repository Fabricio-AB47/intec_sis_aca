import { useEffect, useMemo, useState } from 'react'

import { fetchMoodleGradeAlerts } from '../../lib/api'
import type {
  MoodleGradeAlertComponent,
  MoodleGradeAlertItem,
  MoodleGradeAlertKind,
  MoodleGradeAlertResponse,
} from '../../types/app'

type AlertFilter = 'TODOS' | MoodleGradeAlertKind
type SourceFilter = 'TODAS' | 'INTECBDD' | 'MOODLE' | 'AMBAS'
type EnrollmentFilter = 'TODOS' | 'R' | 'H'

const PAGE_SIZE = 50
const COURSE_ERROR_PAGE_SIZE = 20

type MoodleGradeCourseError = MoodleGradeAlertResponse['errors'][number]

type MoodleGradeCourseIssue = MoodleGradeCourseError & {
  key: string
  course: string
  courseCodes: string[]
  matters: string[]
  careers: string[]
  teachers: string[]
  relatedAlerts: MoodleGradeAlertItem[]
  affectedStudents: number
}

function uniqueText(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.map((value) => String(value ?? '').trim()).filter(Boolean)))
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudieron consultar las alertas de calificación de Moodle.'
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatGrade(value: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '-'
  return new Intl.NumberFormat('es-EC', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Sin registro'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function kindLabel(kind: MoodleGradeAlertKind): string {
  if (kind === 'SIN_CALIFICAR') return 'Sin calificar'
  if (kind === 'REVISAR') return 'Requiere revisión'
  return 'Datos académicos'
}

function componentLabel(component: string): string {
  const labels: Record<string, string> = {
    P1Tareas: 'P1 examen práctico · Tareas (30 %)',
    P1Proyectos: 'P1 examen práctico · Proyectos (30 %)',
    P1Examen: 'P1 examen teórico · Examen (40 %)',
    P2Tareas: 'P2 examen práctico · Tareas (30 %)',
    P2Proyectos: 'P2 examen práctico · Proyectos (30 %)',
    P2Examen: 'P2 examen teórico · Examen (40 %)',
    P3Tareas: 'P3 examen práctico · Tareas (30 %)',
    P3Proyectos: 'P3 examen práctico · Proyectos (30 %)',
    P3Examen: 'P3 examen teórico · Examen (40 %)',
    teoriaHomo: 'Teoría de homologación',
    practicahomo: 'Práctica de homologación',
  }
  return labels[component] ?? component
}

function componentStatusLabel(component: MoodleGradeAlertComponent): string {
  if (!component.academic_registered && !component.moodle_registered) return 'Pendiente en ambas fuentes'
  if (!component.academic_registered) return 'Pendiente en INTECBDD'
  if (!component.moodle_registered) return 'Pendiente en Moodle'
  const labels: Record<string, string> = {
    no_change: 'Sin cambios',
    unchanged: 'Sin cambios',
    insert: 'Lista para registrar',
    update: 'Lista para actualizar',
    replace: 'Lista para reemplazar',
    conflict: 'Requiere revisión',
    not_checked: 'Moodle no verificado',
  }
  return labels[component.status] ?? (component.status.replaceAll('_', ' ') || 'Comparada')
}

function sourceMatches(item: MoodleGradeAlertItem, source: SourceFilter): boolean {
  if (source === 'TODAS') return true
  const sources = new Set(item.missing_sources ?? [])
  if (source === 'AMBAS') return sources.has('INTECBDD') && sources.has('MOODLE')
  return sources.has(source)
}

function matchesSearch(item: MoodleGradeAlertItem, search: string): boolean {
  if (!search) return true
  const componentValues = (item.component_details ?? []).flatMap((component) => [
    component.component,
    component.field,
    component.moodle_grade_item,
    ...(component.moodle_grade_items ?? []),
    component.status,
    component.reason,
  ])
  const value = [
    item.student,
    item.student_code,
    item.identity,
    item.email,
    item.moodle_email,
    item.teacher,
    item.course,
    item.course_code,
    item.matter,
    item.malla_code,
    item.matter_code,
    item.career,
    item.period,
    item.period_code,
    item.parallel,
    item.enrollment_number,
    item.group_number,
    item.message,
    ...componentValues,
  ].join(' ').toLocaleLowerCase('es-EC')
  return value.includes(search)
}

function DetailValue({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value === '' ? '-' : value}</dd>
    </div>
  )
}

export function MoodleGradeAlertsPanel() {
  const [data, setData] = useState<MoodleGradeAlertResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<AlertFilter>('TODOS')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('TODAS')
  const [enrollmentFilter, setEnrollmentFilter] = useState<EnrollmentFilter>('TODOS')
  const [selectedAlert, setSelectedAlert] = useState<MoodleGradeAlertItem | null>(null)
  const [courseIssuesOpen, setCourseIssuesOpen] = useState(false)
  const [selectedCourseIssue, setSelectedCourseIssue] = useState<MoodleGradeCourseIssue | null>(null)
  const [courseIssueSearch, setCourseIssueSearch] = useState('')
  const [courseIssuePage, setCourseIssuePage] = useState(1)
  const [page, setPage] = useState(1)

  const closeCourseIssues = () => {
    setCourseIssuesOpen(false)
    setSelectedCourseIssue(null)
    setCourseIssueSearch('')
    setCourseIssuePage(1)
  }

  const loadAlerts = async (refresh = false) => {
    setLoading(true)
    setError('')
    setSelectedAlert(null)
    try {
      setData(await fetchMoodleGradeAlerts(refresh))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    fetchMoodleGradeAlerts(false)
      .then((response) => {
        if (active) setData(response)
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedAlert && !courseIssuesOpen) return undefined
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (selectedAlert) {
        setSelectedAlert(null)
        return
      }
      if (selectedCourseIssue) {
        setSelectedCourseIssue(null)
        return
      }
      setCourseIssuesOpen(false)
      setCourseIssueSearch('')
      setCourseIssuePage(1)
    }
    window.addEventListener('keydown', closeWithEscape)
    return () => window.removeEventListener('keydown', closeWithEscape)
  }, [courseIssuesOpen, selectedAlert, selectedCourseIssue])

  const visibleItems = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase('es-EC')
    return (data?.items ?? []).filter((item) => (
      (filter === 'TODOS' || item.kind === filter)
      && sourceMatches(item, sourceFilter)
      && (enrollmentFilter === 'TODOS' || item.type === enrollmentFilter)
      && matchesSearch(item, normalizedSearch)
    ))
  }, [data, enrollmentFilter, filter, search, sourceFilter])

  const courseIssues = useMemo<MoodleGradeCourseIssue[]>(() => {
    if (!data) return []
    return data.errors.map((issue, index) => {
      const relatedAlerts = data.items.filter((item) => item.course_id === issue.course_id)
      const courseNames = uniqueText(relatedAlerts.map((item) => item.course))
      const relatedStudents = new Set(
        relatedAlerts.map((item) => item.student_code || item.identity || item.email).filter(Boolean),
      )
      return {
        ...issue,
        key: `${issue.course_id}-${issue.period_codes.join('-')}-${index}`,
        course: courseNames[0] || `Curso Moodle ${issue.course_id}`,
        courseCodes: uniqueText(relatedAlerts.map((item) => item.course_code)),
        matters: uniqueText(relatedAlerts.map((item) => item.matter)),
        careers: uniqueText(relatedAlerts.map((item) => item.career)),
        teachers: uniqueText(relatedAlerts.map((item) => item.teacher)),
        relatedAlerts,
        affectedStudents: relatedStudents.size,
      }
    })
  }, [data])

  const visibleCourseIssues = useMemo(() => {
    const normalizedSearch = courseIssueSearch.trim().toLocaleLowerCase('es-EC')
    if (!normalizedSearch) return courseIssues
    return courseIssues.filter((issue) => [
      issue.course_id,
      issue.course,
      issue.message,
      ...issue.period_codes,
      ...issue.courseCodes,
      ...issue.matters,
      ...issue.careers,
      ...issue.teachers,
    ].join(' ').toLocaleLowerCase('es-EC').includes(normalizedSearch))
  }, [courseIssueSearch, courseIssues])

  const courseIssueTotalPages = Math.max(
    1,
    Math.ceil(visibleCourseIssues.length / COURSE_ERROR_PAGE_SIZE),
  )
  const currentCourseIssuePage = Math.min(courseIssuePage, courseIssueTotalPages)
  const paginatedCourseIssues = useMemo(
    () => visibleCourseIssues.slice(
      (currentCourseIssuePage - 1) * COURSE_ERROR_PAGE_SIZE,
      currentCourseIssuePage * COURSE_ERROR_PAGE_SIZE,
    ),
    [currentCourseIssuePage, visibleCourseIssues],
  )

  const totalPages = Math.max(1, Math.ceil(visibleItems.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const paginatedItems = useMemo(
    () => visibleItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [currentPage, visibleItems],
  )

  const scopeLabel = data?.scope === 'DOCENTE'
    ? 'Asignaciones del docente autenticado'
    : 'Advertencia institucional para Académico y Administrador'

  return (
    <section className="moodle-section moodle-grade-alerts" aria-labelledby="moodle-grade-alerts-title">
      <div className="moodle-section__heading">
        <div>
          <span>Seguimiento de evaluación</span>
          <h2 id="moodle-grade-alerts-title">Alertas de calificación</h2>
          <p>{scopeLabel}</p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--primary"
          disabled={loading}
          onClick={() => void loadAlerts(true)}
        >
          {loading ? 'Verificando...' : 'Actualizar alertas'}
        </button>
      </div>

      {error && <div className="moodle-alert moodle-alert--error" role="alert">{error}</div>}

      {loading && (
        <div className="moodle-grade-alert-loading" role="status" aria-live="polite">
          <strong>Verificando matrículas activas y calificaciones...</strong>
          <span>Se comparan INTECBDD, CorreoIntec y la sección Evaluación de Moodle.</span>
        </div>
      )}

      {data && (
        <>
          <div className="moodle-grade-alert-summary" aria-label="Resumen de alertas">
            <div><span>Total de alertas</span><strong>{formatNumber(data.summary.total)}</strong></div>
            <div><span>Sin calificar</span><strong>{formatNumber(data.summary.ungraded)}</strong></div>
            <div><span>Por revisar</span><strong>{formatNumber(data.summary.review)}</strong></div>
            <div><span>Datos académicos</span><strong>{formatNumber(data.summary.data_issues)}</strong></div>
            <div><span>Pendientes INTECBDD</span><strong>{formatNumber(data.summary.missing_intecbdd)}</strong></div>
            <div><span>Pendientes Moodle</span><strong>{formatNumber(data.summary.missing_moodle)}</strong></div>
            <div><span>Estudiantes</span><strong>{formatNumber(data.summary.students)}</strong></div>
            <div><span>Cursos Moodle</span><strong>{formatNumber(data.summary.courses)}</strong></div>
          </div>

          <section className="moodle-grade-alert-validation" aria-labelledby="moodle-grade-validation-title">
            <div className="moodle-grade-alert-validation__heading">
              <div>
                <span>Validación de identidad y matrícula</span>
                <h3 id="moodle-grade-validation-title">Cobertura de la consulta</h3>
              </div>
              <strong>{formatNumber(data.summary.assignments)} asignación(es) revisada(s)</strong>
            </div>
            <dl>
              <DetailValue label="Períodos" value={formatNumber(data.validation.selected_periods)} />
              <DetailValue label="Matrículas INTECBDD" value={formatNumber(data.validation.academic_enrollments)} />
              <DetailValue label="Usuarios del curso Moodle" value={formatNumber(data.validation.moodle_course_users)} />
              <DetailValue label="Coincidencias por correo" value={formatNumber(data.validation.matched_by_email)} />
              <DetailValue label="Coincidencias por registro" value={formatNumber(data.validation.matched_by_registry)} />
              <DetailValue label="Coincidencias complementarias" value={formatNumber(data.validation.matched_by_data_fallback)} />
              <DetailValue label="Sin CorreoIntec" value={formatNumber(data.validation.missing_institutional_email)} />
              <DetailValue label="No inscritos en Moodle" value={formatNumber(data.validation.not_enrolled_in_course)} />
              <DetailValue label="Usuarios ambiguos" value={formatNumber(data.validation.ambiguous_users)} />
            </dl>
          </section>

          <div className="moodle-grade-alert-toolbar">
            <label>
              <span>Buscar</span>
              <input
                type="search"
                value={search}
                placeholder="Estudiante, cédula, correo, asignatura, período o docente"
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(1)
                }}
              />
            </label>
            <label>
              <span>Advertencia</span>
              <select value={filter} onChange={(event) => {
                setFilter(event.target.value as AlertFilter)
                setPage(1)
              }}>
                <option value="TODOS">Todas</option>
                <option value="SIN_CALIFICAR">Sin calificar</option>
                <option value="REVISAR">Requiere revisión</option>
                {data.scope === 'INSTITUCIONAL' && <option value="DATOS">Datos académicos</option>}
              </select>
            </label>
            <label>
              <span>Fuente pendiente</span>
              <select value={sourceFilter} onChange={(event) => {
                setSourceFilter(event.target.value as SourceFilter)
                setPage(1)
              }}>
                <option value="TODAS">Todas</option>
                <option value="INTECBDD">INTECBDD</option>
                <option value="MOODLE">Moodle</option>
                <option value="AMBAS">Ambas fuentes</option>
              </select>
            </label>
            <label>
              <span>Tipo de matrícula</span>
              <select value={enrollmentFilter} onChange={(event) => {
                setEnrollmentFilter(event.target.value as EnrollmentFilter)
                setPage(1)
              }}>
                <option value="TODOS">Regular y homologación</option>
                <option value="R">Regular</option>
                <option value="H">Homologación</option>
              </select>
            </label>
            <div className="moodle-grade-alert-toolbar__status">
              <span>Última verificación</span>
              <strong>{formatDate(data.generated_at)}</strong>
              <small>{data.cached ? 'Resultado en caché' : 'Consulta actualizada'}</small>
            </div>
          </div>

          <div className="moodle-results-summary">
            <strong>{formatNumber(visibleItems.length)} advertencia(s) visible(s)</strong>
            <span>
              {formatNumber(data.summary.regular)} regular(es) · {formatNumber(data.summary.homologation)} homologación(es)
            </span>
          </div>

          <div className="moodle-table-wrap">
            <table className="moodle-table moodle-grade-alert-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Asignatura y carrera</th>
                  <th>Período</th>
                  <th>Docente responsable</th>
                  <th>Estado</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {paginatedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.student || 'Estudiante sin nombre'}</strong>
                      <small>{item.identity || 'Sin identificación'} · {item.email || 'Sin correo institucional'}</small>
                    </td>
                    <td>
                      <strong>{item.matter || item.course || 'Asignatura sin nombre'}</strong>
                      <small>{item.course_code || 'Sin código'} · {item.career || 'Sin carrera'}</small>
                    </td>
                    <td>
                      <strong>{item.period || `Período ${item.period_code}`}</strong>
                      <small>Tipo {item.type || '-'} · Paralelo {item.parallel || '-'}</small>
                    </td>
                    <td>{item.teacher || 'Sin docente asignado'}</td>
                    <td>
                      <span className={`moodle-grade-alert-badge moodle-grade-alert-badge--${item.kind.toLocaleLowerCase('es-EC')}`}>
                        {kindLabel(item.kind)}
                      </span>
                      <p>{item.message || 'La calificación requiere atención.'}</p>
                      {(item.missing_sources ?? []).length > 0 && (
                        <div className="moodle-grade-alert-sources" aria-label="Fuentes con calificaciones pendientes">
                          {(item.missing_sources ?? []).map((source) => <span key={source}>{source}</span>)}
                        </div>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="moodle-button moodle-grade-alert-detail-button"
                        onClick={() => setSelectedAlert(item)}
                      >
                        Ver detalle
                      </button>
                    </td>
                  </tr>
                ))}
                {visibleItems.length === 0 && (
                  <tr>
                    <td colSpan={6} className="moodle-table__empty">
                      {data.summary.total === 0
                        ? 'No existen calificaciones pendientes con el alcance actual.'
                        : 'No existen advertencias con los filtros seleccionados.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {visibleItems.length > PAGE_SIZE && (
            <div className="moodle-grade-alert-pagination" aria-label="Paginación de alertas">
              <span>
                Página {currentPage} de {totalPages} · {formatNumber(visibleItems.length)} registro(s)
              </span>
              <div>
                <button
                  type="button"
                  className="moodle-button"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  Anterior
                </button>
                <button
                  type="button"
                  className="moodle-button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                >
                  Siguiente
                </button>
              </div>
            </div>
          )}

          {data.errors.length > 0 && (
            <div className="moodle-grade-alert-errors" role="status">
              <div>
                <strong>{formatNumber(data.errors.length)} curso(s) no pudieron verificarse</strong>
                <span>Abra el listado para revisar cada incidencia y su relación académica.</span>
              </div>
              <button
                type="button"
                className="moodle-button"
                onClick={() => {
                  setCourseIssuesOpen(true)
                  setSelectedCourseIssue(null)
                  setCourseIssuePage(1)
                }}
              >
                Ver cursos
              </button>
            </div>
          )}
        </>
      )}

      {!data && !loading && !error && (
        <div className="moodle-empty">No se ha ejecutado la verificación de calificaciones.</div>
      )}

      {courseIssuesOpen && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeCourseIssues()
          }}
        >
          <section
            className="moodle-confirm-dialog moodle-grade-course-issues"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-grade-course-issues-title"
          >
            <header className="moodle-confirm-dialog__header">
              <div>
                <span>Validación de cursos Moodle</span>
                <h2 id="moodle-grade-course-issues-title">
                  {selectedCourseIssue ? 'Detalle del curso no verificado' : 'Cursos no verificados'}
                </h2>
              </div>
              <button type="button" className="moodle-button" onClick={closeCourseIssues}>
                Cerrar
              </button>
            </header>

            <div className="moodle-confirm-dialog__body moodle-grade-course-issues__body">
              {selectedCourseIssue ? (
                <>
                  <div className="moodle-grade-course-issues__notice" role="alert">
                    <strong>{selectedCourseIssue.course}</strong>
                    <span>{selectedCourseIssue.message}</span>
                  </div>

                  <dl className="moodle-grade-alert-detail__grid moodle-grade-course-issues__grid">
                    <DetailValue label="ID del curso Moodle" value={selectedCourseIssue.course_id} />
                    <DetailValue
                      label="Código(s) académico(s)"
                      value={selectedCourseIssue.courseCodes.join(', ') || 'Sin relación identificada'}
                    />
                    <DetailValue
                      label="Período(s) consultado(s)"
                      value={selectedCourseIssue.period_codes.join(', ') || 'Sin período identificado'}
                    />
                    <DetailValue
                      label="Asignatura(s) relacionada(s)"
                      value={selectedCourseIssue.matters.join(', ') || 'Sin relación identificada'}
                    />
                    <DetailValue
                      label="Carrera(s) relacionada(s)"
                      value={selectedCourseIssue.careers.join(', ') || 'Sin relación identificada'}
                    />
                    <DetailValue
                      label="Docente(s) relacionado(s)"
                      value={selectedCourseIssue.teachers.join(', ') || 'Sin docente identificado'}
                    />
                    <DetailValue
                      label="Estudiantes afectados"
                      value={formatNumber(selectedCourseIssue.affectedStudents)}
                    />
                    <DetailValue
                      label="Alertas académicas relacionadas"
                      value={formatNumber(selectedCourseIssue.relatedAlerts.length)}
                    />
                    <DetailValue label="Estado" value="Verificación pendiente" />
                  </dl>

                  <section className="moodle-grade-course-issues__relations">
                    <div className="moodle-grade-alert-detail__section-heading">
                      <h3>Matrículas académicas relacionadas</h3>
                      <span>{formatNumber(selectedCourseIssue.relatedAlerts.length)} registro(s)</span>
                    </div>
                    <div className="moodle-table-wrap">
                      <table className="moodle-table moodle-grade-course-issue-relations-table">
                        <thead>
                          <tr>
                            <th>Estudiante</th>
                            <th>Asignatura y carrera</th>
                            <th>Período</th>
                            <th>Docente</th>
                            <th>Incidencia</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCourseIssue.relatedAlerts.map((item) => (
                            <tr key={item.id}>
                              <td>
                                <strong>{item.student || 'Estudiante sin nombre'}</strong>
                                <small>{item.identity || 'Sin identificación'}</small>
                              </td>
                              <td>
                                <strong>{item.matter || 'Sin asignatura'}</strong>
                                <small>{item.career || 'Sin carrera'}</small>
                              </td>
                              <td>
                                <strong>{item.period || item.period_code || 'Sin período'}</strong>
                                <small>Tipo {item.type || '-'} · Paralelo {item.parallel || '-'}</small>
                              </td>
                              <td>{item.teacher || 'Sin docente asignado'}</td>
                              <td>{item.message || selectedCourseIssue.message}</td>
                            </tr>
                          ))}
                          {selectedCourseIssue.relatedAlerts.length === 0 && (
                            <tr>
                              <td colSpan={5} className="moodle-table__empty">
                                El curso no pudo vincularse con una matrícula académica para mostrar más datos.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              ) : (
                <>
                  <div className="moodle-grade-course-issues__toolbar">
                    <label>
                      <span>Buscar curso o incidencia</span>
                      <input
                        type="search"
                        value={courseIssueSearch}
                        placeholder="Nombre, ID, código, período, docente o motivo"
                        onChange={(event) => {
                          setCourseIssueSearch(event.target.value)
                          setCourseIssuePage(1)
                        }}
                      />
                    </label>
                    <div>
                      <span>Resultados</span>
                      <strong>{formatNumber(visibleCourseIssues.length)}</strong>
                    </div>
                  </div>

                  <div className="moodle-table-wrap">
                    <table className="moodle-table moodle-grade-course-issues-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Curso Moodle</th>
                          <th>Relación académica</th>
                          <th>Período(s)</th>
                          <th>Motivo</th>
                          <th>Acción</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedCourseIssues.map((issue, index) => (
                          <tr key={issue.key}>
                            <td>{(currentCourseIssuePage - 1) * COURSE_ERROR_PAGE_SIZE + index + 1}</td>
                            <td>
                              <strong>{issue.course}</strong>
                              <small>ID {issue.course_id}</small>
                            </td>
                            <td>
                              <strong>{issue.matters.join(', ') || 'Sin asignatura relacionada'}</strong>
                              <small>{issue.courseCodes.join(', ') || 'Sin código académico'}</small>
                            </td>
                            <td>{issue.period_codes.join(', ') || 'Sin período'}</td>
                            <td className="moodle-grade-course-issues-table__message">{issue.message}</td>
                            <td>
                              <button
                                type="button"
                                className="moodle-button moodle-grade-course-issues-table__detail"
                                onClick={() => setSelectedCourseIssue(issue)}
                              >
                                Detalle
                              </button>
                            </td>
                          </tr>
                        ))}
                        {visibleCourseIssues.length === 0 && (
                          <tr>
                            <td colSpan={6} className="moodle-table__empty">
                              No existen cursos no verificados con el criterio ingresado.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {visibleCourseIssues.length > COURSE_ERROR_PAGE_SIZE && (
                    <div className="moodle-grade-alert-pagination" aria-label="Paginación de cursos no verificados">
                      <span>
                        Página {currentCourseIssuePage} de {courseIssueTotalPages} ·{' '}
                        {formatNumber(visibleCourseIssues.length)} curso(s)
                      </span>
                      <div>
                        <button
                          type="button"
                          className="moodle-button"
                          disabled={currentCourseIssuePage <= 1}
                          onClick={() => setCourseIssuePage((value) => Math.max(1, value - 1))}
                        >
                          Anterior
                        </button>
                        <button
                          type="button"
                          className="moodle-button"
                          disabled={currentCourseIssuePage >= courseIssueTotalPages}
                          onClick={() => setCourseIssuePage((value) => Math.min(courseIssueTotalPages, value + 1))}
                        >
                          Siguiente
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <footer className="moodle-confirm-dialog__actions">
              {selectedCourseIssue && (
                <button type="button" className="moodle-button" onClick={() => setSelectedCourseIssue(null)}>
                  Volver al listado
                </button>
              )}
              <button type="button" className="moodle-button moodle-button--primary" onClick={closeCourseIssues}>
                Cerrar subpantalla
              </button>
            </footer>
          </section>
        </div>
      )}

      {selectedAlert && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedAlert(null)
          }}
        >
          <section
            className="moodle-confirm-dialog moodle-grade-alert-detail"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-grade-alert-detail-title"
          >
            <header className="moodle-confirm-dialog__header">
              <div>
                <span>Detalle de calificaciones</span>
                <h2 id="moodle-grade-alert-detail-title">{selectedAlert.student || 'Estudiante sin nombre'}</h2>
              </div>
              <button type="button" className="moodle-button" onClick={() => setSelectedAlert(null)}>
                Cerrar
              </button>
            </header>

            <div className="moodle-confirm-dialog__body moodle-grade-alert-detail__body">
              <div className={`moodle-grade-alert-detail__notice moodle-grade-alert-detail__notice--${selectedAlert.severity}`}>
                <span className={`moodle-grade-alert-badge moodle-grade-alert-badge--${selectedAlert.kind.toLocaleLowerCase('es-EC')}`}>
                  {kindLabel(selectedAlert.kind)}
                </span>
                <div>
                  <strong>{selectedAlert.message || 'La calificación requiere atención.'}</strong>
                  <small>Estado técnico: {selectedAlert.status || 'Sin estado'}</small>
                </div>
                <div className="moodle-grade-alert-sources">
                  {(selectedAlert.missing_sources ?? []).map((source) => <span key={source}>{source}</span>)}
                </div>
              </div>

              <section className="moodle-grade-alert-detail__section">
                <h3>Identidad y matrícula</h3>
                <dl className="moodle-grade-alert-detail__grid">
                  <DetailValue label="Código del estudiante" value={selectedAlert.student_code} />
                  <DetailValue label="Identificación" value={selectedAlert.identity} />
                  <DetailValue label="Correo institucional" value={selectedAlert.email} />
                  <DetailValue label="Origen del correo" value={selectedAlert.email_source} />
                  <DetailValue label="Correo en Moodle" value={selectedAlert.moodle_email} />
                  <DetailValue label="ID de usuario Moodle" value={selectedAlert.moodle_user_id} />
                  <DetailValue label="Carrera" value={selectedAlert.career} />
                  <DetailValue label="Malla / materia" value={`${selectedAlert.malla_code || '-'} / ${selectedAlert.matter_code || '-'}`} />
                  <DetailValue label="Período" value={`${selectedAlert.period_code || '-'} · ${selectedAlert.period || '-'}`} />
                  <DetailValue label="Matrícula / paralelo" value={`${selectedAlert.type || '-'} · ${selectedAlert.parallel || '-'}`} />
                  <DetailValue label="Número de matrícula" value={selectedAlert.enrollment_number} />
                  <DetailValue label="Grupo" value={selectedAlert.group_number} />
                  <DetailValue label="Registro CARRERAXESTUD" value={selectedAlert.record_id} />
                  <DetailValue
                    label="Inscripción Moodle validada"
                    value={selectedAlert.course_enrollment_validated ? 'Sí' : 'No'}
                  />
                </dl>
              </section>

              <section className="moodle-grade-alert-detail__section">
                <h3>Asignación académica y curso Moodle</h3>
                <dl className="moodle-grade-alert-detail__grid">
                  <DetailValue label="Asignatura" value={selectedAlert.matter} />
                  <DetailValue label="Código académico" value={selectedAlert.course_code} />
                  <DetailValue label="Curso Moodle" value={selectedAlert.course} />
                  <DetailValue label="ID del curso Moodle" value={selectedAlert.course_id} />
                  <DetailValue label="Docente responsable" value={selectedAlert.teacher} />
                  <DetailValue
                    label="Códigos docentes"
                    value={(selectedAlert.teacher_codes ?? []).join(', ') || '-'}
                  />
                  <DetailValue
                    label="Cursos Moodle consolidados"
                    value={(selectedAlert.moodle_courses ?? [])
                      .map((course) => `${course.course || course.course_code} (${course.course_id})`)
                      .join(', ') || '-'}
                  />
                  <DetailValue
                    label="Moodle verificado"
                    value={selectedAlert.moodle_checked ? 'Sí' : 'No'}
                  />
                </dl>
                {selectedAlert.moodle_error && (
                  <div className="moodle-alert moodle-alert--error" role="alert">
                    {selectedAlert.moodle_error}
                  </div>
                )}
              </section>

              <section className="moodle-grade-alert-detail__section">
                <div className="moodle-grade-alert-detail__section-heading">
                  <h3>Comparación completa de calificaciones</h3>
                  <span>{selectedAlert.component_details.length} componente(s)</span>
                </div>
                <div className="moodle-table-wrap">
                  <table className="moodle-table moodle-grade-alert-component-table">
                    <thead>
                      <tr>
                        <th>Componente</th>
                        <th>INTECBDD</th>
                        <th>Moodle / 10</th>
                        <th>Validación de escala</th>
                        <th>Actividad de Moodle</th>
                        <th>Validación</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAlert.component_details.map((component) => (
                        <tr key={component.field}>
                          <td>
                            <strong>{componentLabel(component.field)}</strong>
                            <small>{component.component || component.field}</small>
                          </td>
                          <td>
                            <strong>{formatGrade(component.academic_grade)}</strong>
                            <small>{component.academic_registered ? 'Registrada' : 'Sin nota'}</small>
                          </td>
                          <td>
                            <strong>{formatGrade(component.moodle_grade)}</strong>
                            <small>{component.moodle_registered ? 'Normalizada' : 'Sin nota'}</small>
                          </td>
                          <td>
                            <strong>Sobre 10</strong>
                            <small>
                              {component.moodle_grade_scale_source === 'gradeformatted_direct_10'
                                ? 'Se conservó la calificación visible en Moodle'
                                : `Normalizada desde el rango ${formatGrade(component.moodle_grade_min)} a ${formatGrade(component.moodle_grade_max)}`}
                            </small>
                          </td>
                          <td>
                            <strong>{component.moodle_grade_item || 'Sin actividad identificada'}</strong>
                            <small>
                              {component.moodle_grade_item_count > 1
                                ? `${component.moodle_grade_item_count} actividades; se tomó la nota más alta`
                                : `${component.moodle_grade_item_count} actividad(es)`}
                            </small>
                            {component.moodle_grade_items.length > 1 && (
                              <small>{component.moodle_grade_items.join(', ')}</small>
                            )}
                          </td>
                          <td>
                            <strong>{componentStatusLabel(component)}</strong>
                            {component.reason && <small>{component.reason}</small>}
                            {component.previous_synced_grade != null && (
                              <small>Sincronización anterior: {formatGrade(component.previous_synced_grade)}</small>
                            )}
                          </td>
                        </tr>
                      ))}
                      {selectedAlert.component_details.length === 0 && (
                        <tr>
                          <td colSpan={6} className="moodle-table__empty">
                            No existen componentes de calificación disponibles para este registro.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="moodle-grade-alert-detail__section">
                <h3>Resultado académico</h3>
                <dl className="moodle-grade-alert-detail__grid moodle-grade-alert-detail__grid--result">
                  <DetailValue label="Promedio final" value={formatGrade(selectedAlert.final_grade)} />
                  <DetailValue label="Recuperación" value={formatGrade(selectedAlert.recovery_grade)} />
                  <DetailValue label="Aprobación registrada" value={selectedAlert.approval} />
                  <DetailValue
                    label="Pendientes en INTECBDD"
                    value={(selectedAlert.academic_missing_components ?? []).map(componentLabel).join(', ') || 'Ninguno'}
                  />
                  <DetailValue
                    label="Pendientes en Moodle"
                    value={(selectedAlert.moodle_missing_components ?? []).map(componentLabel).join(', ') || 'Ninguno'}
                  />
                </dl>
              </section>
            </div>

          </section>
        </div>
      )}
    </section>
  )
}
