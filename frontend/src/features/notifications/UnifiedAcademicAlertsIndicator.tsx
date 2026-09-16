import { useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchMoodleGradeAlerts,
  fetchTeacherEvaluationAdminPending,
  fetchTeacherEvaluationAdminPeriods,
  fetchTeacherEvaluationPendingAlerts,
  MOODLE_GRADE_ALERT_INVALIDATED_EVENT,
  TEACHER_EVALUATION_ALERT_INVALIDATED_EVENT,
} from '../../lib/api'
import type {
  MoodleGradeAlertItem,
  MoodleGradeAlertResponse,
  TeacherEvaluationAdminPendingResponse,
  TeacherEvaluationPendingAlertItem,
  TeacherEvaluationPendingAlertResponse,
} from '../../types/app'

type UnifiedAcademicAlertsIndicatorProps = {
  role: string
  cedula?: string
  canViewMoodle: boolean
  canViewTeacherEvaluation: boolean
  onOpenMoodle: () => void
  onOpenTeacherEvaluation: () => void
}

type LoadResult<T> = {
  data: T | null
  error: string
}

type EvaluationPendingCourse = TeacherEvaluationPendingAlertItem['pending_courses'][number] & {
  flow: TeacherEvaluationPendingAlertItem['flow']
  flowLabel: string
}

type TeacherEvaluationAlertData =
  | TeacherEvaluationPendingAlertResponse
  | TeacherEvaluationAdminPendingResponse

type EvaluationPendingRow = {
  key: string
  searchText: string
  columns: Array<{
    label: string
    value: string
    detail: string
  }>
}

const REFRESH_INTERVAL_MS = 5 * 60 * 1000
const PAGE_SIZE = 8

function emptyAdminEvaluationAlerts(): TeacherEvaluationAdminPendingResponse {
  return {
    periodo: '',
    periodo_detalle: '',
    flow: 'all',
    summary: [],
    teacher_progress: [],
    items: [],
    total: 0,
  }
}

async function fetchLatestAdminEvaluationAlerts(): Promise<TeacherEvaluationAdminPendingResponse> {
  const periods = await fetchTeacherEvaluationAdminPeriods()
  const latestPeriod = periods.items?.[0]?.codigo_periodo?.trim()
  if (!latestPeriod) return emptyAdminEvaluationAlerts()
  return fetchTeacherEvaluationAdminPending(latestPeriod, 'all', 5000)
}

function isAdminEvaluationAlerts(
  value: TeacherEvaluationAlertData | null,
): value is TeacherEvaluationAdminPendingResponse {
  return Boolean(value && 'summary' in value && 'periodo' in value)
}

async function capture<T>(task: Promise<T> | null, errorMessage: string): Promise<LoadResult<T>> {
  if (!task) return { data: null, error: '' }
  try {
    return { data: await task, error: '' }
  } catch {
    return { data: null, error: errorMessage }
  }
}

function formatCount(value: number) {
  return new Intl.NumberFormat('es-EC').format(value)
}

function localDateKey() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function evaluationFlowLabel(item: TeacherEvaluationPendingAlertItem) {
  const labels: Record<TeacherEvaluationPendingAlertItem['flow'], string> = {
    student: 'Evaluación al docente',
    auto_estudiante: 'Autoevaluación estudiantil',
    auto_docente: 'Autoevaluación docente',
    par_docente: 'Evaluación de pares',
  }
  return labels[item.flow] || item.label
}

function moodleKindLabel(item: MoodleGradeAlertItem) {
  if (item.kind === 'SIN_CALIFICAR') return 'Sin calificar'
  if (item.kind === 'REVISAR') return 'Requiere revisión'
  return 'Datos por corregir'
}

function moodleComponentLabel(component: string) {
  const labels: Record<string, string> = {
    P1Tareas: 'P1 práctico: tareas (30 %)',
    P1Proyectos: 'P1 práctico: proyectos (30 %)',
    P1Examen: 'P1 teórico: examen (40 %)',
    P2Tareas: 'P2 práctico: tareas (30 %)',
    P2Proyectos: 'P2 práctico: proyectos (30 %)',
    P2Examen: 'P2 teórico: examen (40 %)',
    P3Tareas: 'P3 práctico: tareas (30 %)',
    P3Proyectos: 'P3 práctico: proyectos (30 %)',
    P3Examen: 'P3 teórico: examen (40 %)',
    teoriaHomo: 'Teoría de homologación (40 %)',
    practicahomo: 'Práctica de homologación (60 %)',
  }
  return labels[component] || component
}

function Pager({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <div className="unified-alert-center__pager" aria-label="Paginación de pendientes">
      <button
        type="button"
        className="moodle-button moodle-button--secondary"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        Anterior
      </button>
      <span>Página {page} de {totalPages}</span>
      <button
        type="button"
        className="moodle-button moodle-button--secondary"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        Siguiente
      </button>
    </div>
  )
}

export function UnifiedAcademicAlertsIndicator({
  role,
  cedula,
  canViewMoodle,
  canViewTeacherEvaluation,
  onOpenMoodle,
  onOpenTeacherEvaluation,
}: UnifiedAcademicAlertsIndicatorProps) {
  const normalizedRole = role.trim().toUpperCase()
  const isAdminEvaluationObserver = normalizedRole === 'ADMINISTRADOR'
  const [moodleAlerts, setMoodleAlerts] = useState<MoodleGradeAlertResponse | null>(null)
  const [evaluationAlerts, setEvaluationAlerts] = useState<TeacherEvaluationAlertData | null>(null)
  const [moodleError, setMoodleError] = useState('')
  const [evaluationError, setEvaluationError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [evaluationPage, setEvaluationPage] = useState(1)
  const [evaluationQuery, setEvaluationQuery] = useState('')
  const [moodlePage, setMoodlePage] = useState(1)
  const dailyReminderRef = useRef('')

  useEffect(() => {
    let active = true
    let requestGeneration = 0
    setLoaded(false)
    setMoodleAlerts(null)
    setEvaluationAlerts(null)
    setMoodleError('')
    setEvaluationError('')
    setDialogOpen(false)
    setEvaluationPage(1)
    setEvaluationQuery('')
    setMoodlePage(1)

    const load = async (refreshMoodle = false) => {
      const generation = ++requestGeneration
      const [evaluationResult, moodleResult] = await Promise.all([
        capture<TeacherEvaluationAlertData>(
          canViewTeacherEvaluation
            ? isAdminEvaluationObserver
              ? fetchLatestAdminEvaluationAlerts()
              : fetchTeacherEvaluationPendingAlerts()
            : null,
          isAdminEvaluationObserver
            ? 'No se pudo consultar quién tiene pendiente la Evaluación 360.'
            : 'No se pudieron verificar las evaluaciones docentes.',
        ),
        capture(
          canViewMoodle ? fetchMoodleGradeAlerts(refreshMoodle) : null,
          'No se pudieron verificar las calificaciones de Moodle.',
        ),
      ])
      if (!active || generation !== requestGeneration) return

      if (canViewTeacherEvaluation) {
        if (evaluationResult.data) setEvaluationAlerts(evaluationResult.data)
        setEvaluationError(evaluationResult.error)
      } else {
        setEvaluationAlerts(null)
        setEvaluationError('')
      }
      if (canViewMoodle) {
        if (moodleResult.data) setMoodleAlerts(moodleResult.data)
        setMoodleError(moodleResult.error)
      } else {
        setMoodleAlerts(null)
        setMoodleError('')
      }
      setLoaded(true)
    }

    void load()
    const refreshMoodle = () => void load(true)
    const refreshEvaluation = () => void load(false)
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void load(false)
    }
    const intervalId = window.setInterval(refreshMoodle, REFRESH_INTERVAL_MS)
    window.addEventListener(MOODLE_GRADE_ALERT_INVALIDATED_EVENT, refreshMoodle)
    window.addEventListener(TEACHER_EVALUATION_ALERT_INVALIDATED_EVENT, refreshEvaluation)
    window.addEventListener('focus', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      active = false
      window.clearInterval(intervalId)
      window.removeEventListener(MOODLE_GRADE_ALERT_INVALIDATED_EVENT, refreshMoodle)
      window.removeEventListener(TEACHER_EVALUATION_ALERT_INVALIDATED_EVENT, refreshEvaluation)
      window.removeEventListener('focus', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [canViewMoodle, canViewTeacherEvaluation, cedula, isAdminEvaluationObserver, role])

  const adminEvaluationAlerts = isAdminEvaluationAlerts(evaluationAlerts) ? evaluationAlerts : null
  const personalEvaluationAlerts = evaluationAlerts && !adminEvaluationAlerts
    ? evaluationAlerts as TeacherEvaluationPendingAlertResponse
    : null
  const evaluationPending = adminEvaluationAlerts
    ? adminEvaluationAlerts.summary.reduce((total, item) => total + Number(item.pending || 0), 0)
    : personalEvaluationAlerts?.total_pending ?? 0
  const moodlePending = moodleAlerts?.summary.total ?? 0
  const totalPending = evaluationPending + moodlePending
  const hasErrors = Boolean(evaluationError || moodleError)
  const receivesDailyReminder = ['ESTUDIANTE', 'DOCENTE'].includes(normalizedRole)

  useEffect(() => {
    if (!loaded || totalPending <= 0 || !receivesDailyReminder) return

    const today = localDateKey()
    const reminderIdentity = `${normalizedRole}:${cedula || 'sin-cedula'}:${today}`
    if (dailyReminderRef.current === reminderIdentity) return
    dailyReminderRef.current = reminderIdentity

    const storageKey = `intec:recordatorio-pendientes:${normalizedRole}:${cedula || 'sesion'}`
    try {
      if (window.localStorage.getItem(storageKey) === today) return
      window.localStorage.setItem(storageKey, today)
    } catch {
      // El recordatorio sigue funcionando durante la sesión si el almacenamiento está bloqueado.
    }
    setDialogOpen(true)
  }, [cedula, loaded, normalizedRole, receivesDailyReminder, totalPending])

  useEffect(() => {
    if (!dialogOpen) return
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDialogOpen(false)
    }
    window.addEventListener('keydown', closeWithEscape)
    return () => window.removeEventListener('keydown', closeWithEscape)
  }, [dialogOpen])

  const evaluationCourses = useMemo<EvaluationPendingCourse[]>(() => (
    (personalEvaluationAlerts?.items || []).flatMap((item) => (
      item.pending_courses.map((course) => ({
        ...course,
        flow: item.flow,
        flowLabel: evaluationFlowLabel(item),
      }))
    ))
  ), [personalEvaluationAlerts])
  const evaluationRows = useMemo<EvaluationPendingRow[]>(() => {
    if (adminEvaluationAlerts) {
      return (adminEvaluationAlerts.items || []).map((item, index) => {
        const course = item.course
        const evaluator = item.evaluator_name?.trim() || (
          item.flow === 'academico_docente' ? 'Administración académica' : 'Responsable sin nombre'
        )
        const evaluatorIdentity = item.evaluator_cedula?.trim()
          || (item.evaluator_code ? `Código ${item.evaluator_code}` : 'Identificación institucional pendiente')
        const subject = course.materia?.trim() || `Materia ${course.codigo_materia}`
        const careerAndPeriod = [
          course.carrera?.trim(),
          item.periodo_detalle?.trim() || item.periodo,
        ].filter(Boolean).join(' · ')
        const target = course.docente?.trim() || (
          item.flow === 'auto_estudiante' ? 'Autoevaluación del estudiante' : item.flow_label
        )
        const subjectCode = course.codigo_materia_interno?.trim() || `Materia ${course.codigo_materia}`
        const section = `Paralelo ${course.paralelo?.trim() || '-'} · ${subjectCode}`
        const columns = [
          { label: item.flow_label, value: evaluator, detail: evaluatorIdentity },
          { label: 'Materia y período', value: subject, detail: careerAndPeriod || '-' },
          { label: item.flow === 'auto_estudiante' ? 'Actividad pendiente' : 'Debe evaluar a', value: target, detail: section },
        ]
        return {
          key: `${item.flow}:${item.evaluator_code || item.evaluator_cedula || 'administracion'}:${course.key || index}`,
          searchText: columns.flatMap((column) => [column.label, column.value, column.detail]).join(' ').toLocaleLowerCase('es'),
          columns,
        }
      })
    }

    return evaluationCourses.map((course) => {
      const columns = [
        {
          label: course.flowLabel,
          value: course.materia || 'Materia sin nombre',
          detail: course.carrera || 'Carrera no registrada',
        },
        {
          label: 'Período',
          value: course.detalle_periodo || String(course.codigo_periodo || '-'),
          detail: `Paralelo ${course.paralelo || '-'}`,
        },
        {
          label: 'Docente o tipo',
          value: course.docente || course.flowLabel,
          detail: course.codigo_materia_interno || `Materia ${course.codigo_materia}`,
        },
      ]
      return {
        key: `${course.flow}:${course.key}`,
        searchText: '',
        columns,
      }
    })
  }, [adminEvaluationAlerts, evaluationCourses])
  const normalizedEvaluationQuery = evaluationQuery.trim().toLocaleLowerCase('es')
  const filteredEvaluationRows = useMemo(
    () => normalizedEvaluationQuery
      ? evaluationRows.filter((row) => row.searchText.includes(normalizedEvaluationQuery))
      : evaluationRows,
    [evaluationRows, normalizedEvaluationQuery],
  )
  const adminPendingPeople = useMemo(() => {
    if (!adminEvaluationAlerts) return 0
    return new Set(
      adminEvaluationAlerts.items.map((item) => {
        const actorType = ['student', 'auto_estudiante'].includes(item.flow)
          ? 'estudiante'
          : ['auto_docente', 'par_docente'].includes(item.flow)
            ? 'docente'
            : 'administracion'
        return `${actorType}:${item.evaluator_cedula || item.evaluator_code || item.evaluator_name || 'pendiente'}`
      }),
    ).size
  }, [adminEvaluationAlerts])
  const evaluationPages = Math.max(Math.ceil(filteredEvaluationRows.length / PAGE_SIZE), 1)
  const currentEvaluationPage = Math.min(evaluationPage, evaluationPages)
  const visibleEvaluationRows = filteredEvaluationRows.slice(
    (currentEvaluationPage - 1) * PAGE_SIZE,
    currentEvaluationPage * PAGE_SIZE,
  )

  const moodleItems = moodleAlerts?.items || []
  const moodlePages = Math.max(Math.ceil(moodleItems.length / PAGE_SIZE), 1)
  const currentMoodlePage = Math.min(moodlePage, moodlePages)
  const visibleMoodleItems = moodleItems.slice(
    (currentMoodlePage - 1) * PAGE_SIZE,
    currentMoodlePage * PAGE_SIZE,
  )

  if (!canViewMoodle && !canViewTeacherEvaluation) return null
  if (!loaded && !hasErrors) return null
  if (totalPending <= 0 && !hasErrors) return null

  const sourceSummaries = [
    evaluationPending > 0
      ? isAdminEvaluationObserver
        ? `${formatCount(evaluationPending)} ${evaluationPending === 1 ? 'evaluación 360 pendiente' : 'evaluaciones 360 pendientes'}`
        : `${formatCount(evaluationPending)} ${evaluationPending === 1 ? 'actividad de evaluación docente' : 'actividades de evaluación docente'}`
      : '',
    moodlePending > 0
      ? `${formatCount(moodlePending)} ${moodlePending === 1 ? 'alerta de calificaciones Moodle' : 'alertas de calificaciones Moodle'}`
      : '',
  ].filter(Boolean)
  const title = totalPending > 0
    ? totalPending === 1
      ? '1 pendiente académico'
      : `${formatCount(totalPending)} pendientes académicos`
    : 'No se pudieron verificar todos los pendientes'
  const detail = totalPending > 0
    ? `${receivesDailyReminder ? 'Recordatorio diario: falta completar' : 'Pendientes por atender:'} ${sourceSummaries.join(' y ')}.`
    : 'Abra el centro de pendientes para revisar las fuentes que no respondieron.'
  const visibleDetail = hasErrors && totalPending > 0
    ? `${detail} Una fuente no pudo actualizarse en la revisión más reciente.`
    : detail

  const openEvaluation = () => {
    setDialogOpen(false)
    onOpenTeacherEvaluation()
  }
  const openMoodle = () => {
    setDialogOpen(false)
    onOpenMoodle()
  }

  return (
    <>
      <button
        type="button"
        className={`moodle-grade-alert-indicator unified-alert-indicator${totalPending <= 0 ? ' moodle-grade-alert-indicator--error' : ''}`}
        aria-label={`${title}. ${visibleDetail} Ver detalle de pendientes.`}
        onClick={() => setDialogOpen(true)}
      >
        <span className="moodle-grade-alert-indicator__count" aria-hidden="true">
          {totalPending <= 0 ? '!' : totalPending > 99 ? '99+' : totalPending}
        </span>
        <div className="moodle-grade-alert-indicator__copy" aria-live="polite">
          <strong>{title}</strong>
          <span>{visibleDetail}</span>
        </div>
        <span className="moodle-grade-alert-indicator__action" aria-hidden="true">
          Ver pendientes
        </span>
      </button>

      {dialogOpen ? (
        <div
          className="moodle-confirm-overlay unified-alert-center__overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setDialogOpen(false)
          }}
        >
          <section
            className="moodle-confirm-dialog unified-alert-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="unified-alert-center-title"
          >
            <header className="moodle-confirm-dialog__header unified-alert-center__header">
              <div>
                <span>{receivesDailyReminder ? 'Recordatorio diario' : 'Centro unificado'}</span>
                <h2 id="unified-alert-center-title">Pendientes académicos</h2>
                <p>El aviso continuará activo hasta completar cada actividad.</p>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary moodle-dialog-close"
                onClick={() => setDialogOpen(false)}
              >
                Cerrar
              </button>
            </header>

            <div className="moodle-confirm-dialog__body unified-alert-center__body">
              <div className="unified-alert-center__summary">
                {canViewTeacherEvaluation ? (
                  <div>
                    <span>{isAdminEvaluationObserver ? 'Evaluación 360' : 'Evaluación docente'}</span>
                    <strong>{formatCount(evaluationPending)}</strong>
                    <small>
                      {isAdminEvaluationObserver
                        ? `${formatCount(adminPendingPeople)} ${adminPendingPeople === 1 ? 'responsable identificado' : 'responsables identificados'}`
                        : evaluationPending === 1 ? 'actividad pendiente' : 'actividades pendientes'}
                    </small>
                  </div>
                ) : null}
                {canViewMoodle ? (
                  <div>
                    <span>Moodle y calificaciones</span>
                    <strong>{formatCount(moodlePending)}</strong>
                    <small>{moodlePending === 1 ? 'alerta por atender' : 'alertas por atender'}</small>
                  </div>
                ) : null}
              </div>

              {evaluationError || moodleError ? (
                <div className="unified-alert-center__errors" role="alert">
                  {evaluationError ? <p>{evaluationError}</p> : null}
                  {moodleError ? <p>{moodleError}</p> : null}
                </div>
              ) : null}

              {evaluationPending > 0 ? (
                <section className="unified-alert-center__section">
                  <header>
                    <div>
                      <span>{isAdminEvaluationObserver ? 'Evaluación 360' : 'Evaluación docente'}</span>
                      <h3>
                        {isAdminEvaluationObserver
                          ? 'Personas que todavía deben completar la evaluación'
                          : 'Cuestionarios que debe completar'}
                      </h3>
                    </div>
                    <button type="button" className="moodle-button moodle-button--primary" onClick={openEvaluation}>
                      {isAdminEvaluationObserver ? 'Ver avance 360' : 'Realizar evaluaciones'}
                    </button>
                  </header>
                  {isAdminEvaluationObserver ? (
                    <div className="unified-alert-center__filter">
                      <label>
                        <span>Buscar responsable pendiente</span>
                        <input
                          type="search"
                          value={evaluationQuery}
                          placeholder="Nombre, cédula, materia, carrera o docente"
                          onChange={(event) => {
                            setEvaluationQuery(event.target.value)
                            setEvaluationPage(1)
                          }}
                        />
                      </label>
                      <div>
                        <span>Período analizado</span>
                        <strong>{adminEvaluationAlerts?.periodo_detalle || adminEvaluationAlerts?.periodo || '-'}</strong>
                        <small>
                          {formatCount(filteredEvaluationRows.length)} de {formatCount(evaluationRows.length)} registro(s) visible(s)
                        </small>
                      </div>
                    </div>
                  ) : null}
                  <div className="unified-alert-center__list">
                    {visibleEvaluationRows.map((row) => (
                      <article className="unified-alert-center__row" key={row.key}>
                        {row.columns.map((column, index) => (
                          <div key={`${row.key}:column:${index}`}>
                            <span>{column.label}</span>
                            <strong>{column.value}</strong>
                            <small>{column.detail}</small>
                          </div>
                        ))}
                      </article>
                    ))}
                    {filteredEvaluationRows.length === 0 ? (
                      <div className="unified-alert-center__list-empty">
                        No se encontraron pendientes con el criterio indicado.
                      </div>
                    ) : null}
                  </div>
                  <Pager page={currentEvaluationPage} totalPages={evaluationPages} onChange={setEvaluationPage} />
                </section>
              ) : null}

              {moodlePending > 0 ? (
                <section className="unified-alert-center__section">
                  <header>
                    <div>
                      <span>Moodle y calificaciones</span>
                      <h3>Registros que requieren atención</h3>
                    </div>
                    <button type="button" className="moodle-button moodle-button--primary" onClick={openMoodle}>
                      Revisar calificaciones
                    </button>
                  </header>
                  <div className="unified-alert-center__list">
                    {visibleMoodleItems.map((item) => (
                      <article className="unified-alert-center__row" key={item.id}>
                        <div>
                          <span>{moodleKindLabel(item)}</span>
                          <strong>{item.student || 'Estudiante sin identificar'}</strong>
                          <small>{item.identity || item.email || '-'}</small>
                        </div>
                        <div>
                          <span>Materia y período</span>
                          <strong>{item.matter || item.course || 'Curso sin nombre'}</strong>
                          <small>{item.period || `Período ${item.period_code}`}</small>
                        </div>
                        <div>
                          <span>Hace falta</span>
                          <strong>
                            {item.missing_components.length > 0
                              ? item.missing_components.map(moodleComponentLabel).join(', ')
                              : item.message}
                          </strong>
                          <small>{item.missing_sources.length > 0 ? `Fuente: ${item.missing_sources.join(' / ')}` : item.status}</small>
                        </div>
                      </article>
                    ))}
                  </div>
                  <Pager page={currentMoodlePage} totalPages={moodlePages} onChange={setMoodlePage} />
                </section>
              ) : null}

              {totalPending <= 0 ? (
                <div className="unified-alert-center__empty">
                  No existen pendientes confirmados. Revise los avisos de conexión mostrados arriba.
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
