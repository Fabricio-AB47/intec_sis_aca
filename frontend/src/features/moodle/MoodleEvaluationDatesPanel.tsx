import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import {
  fetchMoodleCourseEvaluations,
  fetchMoodleCourses,
  updateMoodleCourseEvaluationDates,
} from '../../lib/api'
import type {
  MoodleCourse,
  MoodleCourseEvaluationsResponse,
  MoodleEvaluationActivity,
  MoodleEvaluationDateUpdate,
} from '../../types/app'

type EvaluationScope = 'simuladores' | 'evaluaciones'
type PartialNumber = 1 | 2 | 3
type ScheduleKey = `${EvaluationScope}-${PartialNumber}`

type ScheduleDraft = {
  enabled: boolean
  open: string
  close: string
}

type ScheduleMap = Record<ScheduleKey, ScheduleDraft>
type CourseActivitySelectionMap = Record<number, number[]>

type ScheduleBlock = {
  key: ScheduleKey
  scope: EvaluationScope
  scopeLabel: string
  partial: PartialNumber
  partialLabel: string
}

type CourseUpdatePlan = {
  course: MoodleCourse
  data: MoodleCourseEvaluationsResponse
  matchingActivities: number
  updates: MoodleEvaluationDateUpdate[]
}

const SCHEDULE_BLOCKS: ScheduleBlock[] = [
  { key: 'simuladores-1', scope: 'simuladores', scopeLabel: 'Simuladores', partial: 1, partialLabel: 'Parcial 1' },
  { key: 'simuladores-2', scope: 'simuladores', scopeLabel: 'Simuladores', partial: 2, partialLabel: 'Parcial 2' },
  { key: 'simuladores-3', scope: 'simuladores', scopeLabel: 'Simuladores', partial: 3, partialLabel: 'Parcial 3' },
  { key: 'evaluaciones-1', scope: 'evaluaciones', scopeLabel: 'Evaluaciones', partial: 1, partialLabel: 'Parcial 1' },
  { key: 'evaluaciones-2', scope: 'evaluaciones', scopeLabel: 'Evaluaciones', partial: 2, partialLabel: 'Parcial 2' },
  { key: 'evaluaciones-3', scope: 'evaluaciones', scopeLabel: 'Evaluaciones', partial: 3, partialLabel: 'Parcial 3' },
]

const EMPTY_SCHEDULES: ScheduleMap = {
  'simuladores-1': { enabled: false, open: '', close: '' },
  'simuladores-2': { enabled: false, open: '', close: '' },
  'simuladores-3': { enabled: false, open: '', close: '' },
  'evaluaciones-1': { enabled: false, open: '', close: '' },
  'evaluaciones-2': { enabled: false, open: '', close: '' },
  'evaluaciones-3': { enabled: false, open: '', close: '' },
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudo completar la operación de Moodle.'
}

function courseName(course: MoodleCourse): string {
  return course.fullname || course.displayname || course.shortname || `Curso ${course.id}`
}

function toLocalDateTime(timestamp: number): string {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function fromLocalDateTime(value: string): number {
  if (!value) return 0
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : Math.floor(timestamp / 1000)
}

function formatDate(timestamp: number): string {
  if (!timestamp) return 'Sin fecha'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp * 1000))
}

function activityScheduleKey(activity: MoodleEvaluationActivity): ScheduleKey | null {
  if (!activity.programmable || activity.partial < 1 || activity.partial > 3) return null
  if (activity.scope !== 'simuladores' && activity.scope !== 'evaluaciones') return null
  return `${activity.scope}-${activity.partial as PartialNumber}`
}

function courseBlockActivities(
  data: MoodleCourseEvaluationsResponse | undefined,
  key: ScheduleKey,
): MoodleEvaluationActivity[] {
  if (!data) return []
  return data.activities.filter((activity) => activityScheduleKey(activity) === key)
}

function ActivityGroupCheckbox({
  checked,
  indeterminate,
  disabled,
  label,
  onChange,
}: {
  checked: boolean
  indeterminate: boolean
  disabled: boolean
  label: string
  onChange: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate
  }, [indeterminate])

  return (
    <input
      ref={inputRef}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={onChange}
    />
  )
}

function activityCurrentRange(activity: MoodleEvaluationActivity): { open: number; close: number } {
  if (activity.modname === 'assign') {
    return {
      open: activity.dates.allowsubmissionsfromdate,
      close: activity.dates.duedate || activity.dates.cutoffdate,
    }
  }
  return {
    open: activity.dates.timeopen,
    close: activity.dates.timeclose,
  }
}

function scheduleUpdate(
  activity: MoodleEvaluationActivity,
  schedule: ScheduleDraft,
): MoodleEvaluationDateUpdate {
  const open = fromLocalDateTime(schedule.open)
  const close = fromLocalDateTime(schedule.close)
  if (activity.modname === 'assign') {
    return {
      cmid: activity.cmid,
      modname: activity.modname,
      instance: activity.instance,
      allowsubmissionsfromdate: open,
      duedate: close,
      cutoffdate: close,
    }
  }
  return {
    cmid: activity.cmid,
    modname: activity.modname,
    instance: activity.instance,
    timeopen: open,
    timeclose: close,
  }
}

function updateChangesActivity(
  activity: MoodleEvaluationActivity,
  update: MoodleEvaluationDateUpdate,
): boolean {
  if (activity.modname === 'assign') {
    return activity.dates.allowsubmissionsfromdate !== update.allowsubmissionsfromdate
      || activity.dates.duedate !== update.duedate
      || activity.dates.cutoffdate !== update.cutoffdate
  }
  return activity.dates.timeopen !== update.timeopen
    || activity.dates.timeclose !== update.timeclose
}

function deriveCommonSchedules(
  responses: MoodleCourseEvaluationsResponse[],
  current: ScheduleMap,
): ScheduleMap {
  const next = Object.fromEntries(
    SCHEDULE_BLOCKS.map((block) => {
      const existing = current[block.key]
      if (existing.enabled || existing.open || existing.close) return [block.key, existing]
      const activities = responses.flatMap((response) => response.activities).filter(
        (activity) => activityScheduleKey(activity) === block.key,
      )
      const ranges = activities.map(activityCurrentRange)
      const opens = new Set(ranges.map((range) => range.open).filter(Boolean))
      const closes = new Set(ranges.map((range) => range.close).filter(Boolean))
      return [
        block.key,
        {
          enabled: false,
          open: ranges.length > 0 && opens.size === 1 && ranges.every((range) => range.open)
            ? toLocalDateTime([...opens][0])
            : '',
          close: ranges.length > 0 && closes.size === 1 && ranges.every((range) => range.close)
            ? toLocalDateTime([...closes][0])
            : '',
        },
      ]
    }),
  )
  return next as ScheduleMap
}

function updatedResponse(
  current: MoodleCourseEvaluationsResponse,
  activities: MoodleEvaluationActivity[],
): MoodleCourseEvaluationsResponse {
  return {
    ...current,
    activities,
    totals: {
      ...current.totals,
      with_dates: activities.filter((activity) => Object.values(activity.dates).some(Boolean)).length,
    },
  }
}

export function MoodleEvaluationDatesPanel() {
  const [courseSearch, setCourseSearch] = useState('')
  const [courses, setCourses] = useState<MoodleCourse[]>([])
  const [coursesTotal, setCoursesTotal] = useState(0)
  const [selectedCourses, setSelectedCourses] = useState<MoodleCourse[]>([])
  const [courseData, setCourseData] = useState<Record<number, MoodleCourseEvaluationsResponse>>({})
  const [analysisErrors, setAnalysisErrors] = useState<Record<number, string>>({})
  const [schedules, setSchedules] = useState<ScheduleMap>(EMPTY_SCHEDULES)
  const [courseActivitySelections, setCourseActivitySelections] = useState<CourseActivitySelectionMap>({})
  const [courseSelectionOpen, setCourseSelectionOpen] = useState(false)
  const [activeSelectionCourseId, setActiveSelectionCourseId] = useState<number | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisProgress, setAnalysisProgress] = useState({ completed: 0, total: 0 })
  const [saving, setSaving] = useState(false)
  const [saveProgress, setSaveProgress] = useState({ completed: 0, total: 0 })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const loadCourses = async (refresh = false) => {
    setCatalogLoading(true)
    setError('')
    try {
      const response = await fetchMoodleCourses({
        page: 1,
        pageSize: 200,
        search: courseSearch,
        visibility: 'all',
        refresh,
      })
      setCourses(response.items)
      setCoursesTotal(response.pagination.total_items)
    } catch (requestError) {
      setCourses([])
      setCoursesTotal(0)
      setError(errorMessage(requestError))
    } finally {
      setCatalogLoading(false)
    }
  }

  useEffect(() => {
    void loadCourses()
    // El catálogo inicial se consulta una vez; la búsqueda posterior es explícita.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!success) return undefined
    const timeoutId = window.setTimeout(() => setSuccess(''), 3000)
    return () => window.clearTimeout(timeoutId)
  }, [success])

  const selectedIds = useMemo(
    () => new Set(selectedCourses.map((course) => course.id)),
    [selectedCourses],
  )

  const loadedResponses = useMemo(
    () => selectedCourses.map((course) => courseData[course.id]).filter(Boolean),
    [courseData, selectedCourses],
  )

  const blockCounts = useMemo(() => Object.fromEntries(
    SCHEDULE_BLOCKS.map((block) => [
      block.key,
      loadedResponses.reduce(
        (total, response) => total + response.activities.filter(
          (activity) => activityScheduleKey(activity) === block.key,
        ).length,
        0,
      ),
    ]),
  ) as Record<ScheduleKey, number>, [loadedResponses])

  const allSelectedAnalyzed = selectedCourses.length > 0
    && selectedCourses.every((course) => Boolean(courseData[course.id]))
    && selectedCourses.every((course) => !analysisErrors[course.id])

  const dateManagementEnabled = loadedResponses.length > 0
    && loadedResponses.every((response) => response.date_management.enabled)

  const activeSelectionCourse = selectedCourses.find(
    (course) => course.id === activeSelectionCourseId && Boolean(courseData[course.id]),
  ) ?? selectedCourses.find((course) => Boolean(courseData[course.id])) ?? null
  const activeSelectionData = activeSelectionCourse ? courseData[activeSelectionCourse.id] : undefined

  const updatePlans = useMemo<CourseUpdatePlan[]>(() => selectedCourses.flatMap((course) => {
    const data = courseData[course.id]
    if (!data) return []
    const selectedActivities = new Set(courseActivitySelections[course.id] ?? [])
    const matching = data.activities.filter((activity) => {
      const key = activityScheduleKey(activity)
      return key ? schedules[key].enabled && selectedActivities.has(activity.cmid) : false
    })
    const updates = matching
      .map((activity) => {
        const key = activityScheduleKey(activity)
        return key ? { activity, update: scheduleUpdate(activity, schedules[key]) } : null
      })
      .filter((item): item is { activity: MoodleEvaluationActivity; update: MoodleEvaluationDateUpdate } => Boolean(item))
      .filter(({ activity, update }) => updateChangesActivity(activity, update))
      .map(({ update }) => update)
    return [{ course, data, matchingActivities: matching.length, updates }]
  }), [courseActivitySelections, courseData, schedules, selectedCourses])

  const enabledBlocks = SCHEDULE_BLOCKS.filter((block) => schedules[block.key].enabled)
  const selectedBlocks = SCHEDULE_BLOCKS.filter((block) => schedules[block.key].enabled && updatePlans.some((plan) => {
    const selectedActivities = new Set(courseActivitySelections[plan.course.id] ?? [])
    return courseBlockActivities(plan.data, block.key).some((activity) => selectedActivities.has(activity.cmid))
  }))
  const selectedActivityCount = updatePlans.reduce((total, plan) => total + plan.matchingActivities, 0)
  const configuredCourseCount = updatePlans.filter((plan) => plan.matchingActivities > 0).length
  const changedActivities = updatePlans.reduce((total, plan) => total + plan.updates.length, 0)
  const coursesWithChanges = updatePlans.filter((plan) => plan.updates.length > 0)
  const activeSelectedActivityCount = activeSelectionData?.activities.filter((activity) => {
    const key = activityScheduleKey(activity)
    return key
      ? schedules[key].enabled && (courseActivitySelections[activeSelectionCourse?.id ?? 0] ?? []).includes(activity.cmid)
      : false
  }).length ?? 0

  const submitCourseSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void loadCourses(true)
  }

  const toggleCourse = (course: MoodleCourse) => {
    setSelectedCourses((current) => current.some((item) => item.id === course.id)
      ? current.filter((item) => item.id !== course.id)
      : [...current, course])
    setError('')
  }

  const selectVisibleCourses = () => {
    setSelectedCourses((current) => {
      const merged = new Map(current.map((course) => [course.id, course]))
      courses.forEach((course) => merged.set(course.id, course))
      return [...merged.values()]
    })
  }

  const clearSelection = () => {
    setSelectedCourses([])
    setCourseData({})
    setAnalysisErrors({})
    setSchedules(EMPTY_SCHEDULES)
    setCourseActivitySelections({})
    setCourseSelectionOpen(false)
    setActiveSelectionCourseId(null)
    setError('')
  }

  const analyzeCourses = async (refresh = true) => {
    if (selectedCourses.length === 0) {
      setError('Seleccione al menos un curso de Moodle para analizar sus parciales.')
      return
    }
    setAnalyzing(true)
    setError('')
    setAnalysisErrors({})
    setAnalysisProgress({ completed: 0, total: selectedCourses.length })
    const loaded: Record<number, MoodleCourseEvaluationsResponse> = {}
    const failures: Record<number, string> = {}
    const chunkSize = 5
    for (let index = 0; index < selectedCourses.length; index += chunkSize) {
      const chunk = selectedCourses.slice(index, index + chunkSize)
      const results = await Promise.all(chunk.map(async (course) => {
        try {
          return { course, data: await fetchMoodleCourseEvaluations(course.id, refresh) }
        } catch (requestError) {
          return { course, requestError }
        }
      }))
      results.forEach((result) => {
        if ('data' in result && result.data) loaded[result.course.id] = result.data
        else failures[result.course.id] = errorMessage(result.requestError)
      })
      setAnalysisProgress({
        completed: Math.min(index + chunk.length, selectedCourses.length),
        total: selectedCourses.length,
      })
    }
    setCourseData(loaded)
    setAnalysisErrors(failures)
    setSchedules((current) => deriveCommonSchedules(Object.values(loaded), current))
    setCourseActivitySelections((current) => Object.fromEntries(
      selectedCourses.flatMap((course) => {
        const data = loaded[course.id]
        if (!data) return []
        const availableActivityIds = new Set(
          data.activities.filter((activity) => Boolean(activityScheduleKey(activity))).map((activity) => activity.cmid),
        )
        return [[course.id, (current[course.id] ?? []).filter((cmid) => availableActivityIds.has(cmid))]]
      }),
    ))
    const firstAnalyzedCourse = selectedCourses.find((course) => Boolean(loaded[course.id]))
    if (firstAnalyzedCourse) {
      setActiveSelectionCourseId(firstAnalyzedCourse.id)
    }
    if (Object.keys(failures).length > 0) {
      setError(`No se pudieron analizar ${Object.keys(failures).length} curso(s). Revise el detalle antes de continuar.`)
    }
    setAnalyzing(false)
  }

  const updateSchedule = (key: ScheduleKey, change: Partial<ScheduleDraft>) => {
    setSchedules((current) => ({
      ...current,
      [key]: { ...current[key], ...change },
    }))
    if (change.enabled === false) {
      setCourseActivitySelections((current) => Object.fromEntries(
        Object.entries(current).map(([courseId, cmids]) => {
          const disabledActivityIds = new Set(
            courseBlockActivities(courseData[Number(courseId)], key).map((activity) => activity.cmid),
          )
          return [courseId, cmids.filter((cmid) => !disabledActivityIds.has(cmid))]
        }),
      ))
    }
    setError('')
  }

  const toggleCourseBlock = (courseId: number, key: ScheduleKey) => {
    const data = courseData[courseId]
    const blockActivities = courseBlockActivities(data, key)
    if (!data || !schedules[key].enabled || blockActivities.length === 0) return
    setCourseActivitySelections((current) => {
      const selected = new Set(current[courseId] ?? [])
      const allSelected = blockActivities.every((activity) => selected.has(activity.cmid))
      blockActivities.forEach((activity) => {
        if (allSelected) selected.delete(activity.cmid)
        else selected.add(activity.cmid)
      })
      return {
        ...current,
        [courseId]: data.activities
          .filter((activity) => Boolean(activityScheduleKey(activity)) && selected.has(activity.cmid))
          .map((activity) => activity.cmid),
      }
    })
    setError('')
  }

  const toggleCourseActivity = (courseId: number, cmid: number) => {
    const data = courseData[courseId]
    const activity = data?.activities.find((item) => item.cmid === cmid)
    const key = activity ? activityScheduleKey(activity) : null
    if (!data || !key || !schedules[key].enabled) return
    setCourseActivitySelections((current) => {
      const selected = new Set(current[courseId] ?? [])
      if (selected.has(cmid)) selected.delete(cmid)
      else selected.add(cmid)
      return {
        ...current,
        [courseId]: data.activities
          .filter((item) => Boolean(activityScheduleKey(item)) && selected.has(item.cmid))
          .map((item) => item.cmid),
      }
    })
    setError('')
  }

  const selectAvailableCourseActivities = (courseId: number) => {
    const data = courseData[courseId]
    const available = data?.activities.filter((activity) => {
      const key = activityScheduleKey(activity)
      return key ? schedules[key].enabled : false
    }).map((activity) => activity.cmid) ?? []
    setCourseActivitySelections((current) => ({ ...current, [courseId]: available }))
    setError('')
  }

  const clearCourseActivities = (courseId: number) => {
    setCourseActivitySelections((current) => ({ ...current, [courseId]: [] }))
    setError('')
  }

  const openCourseSelection = (courseId?: number) => {
    const firstAvailable = selectedCourses.find((course) => Boolean(courseData[course.id]))
    const requested = courseId ? selectedCourses.find(
      (course) => course.id === courseId && Boolean(courseData[course.id]),
    ) : null
    const course = requested ?? activeSelectionCourse ?? firstAvailable
    if (!course) {
      setError('Analice al menos una materia antes de seleccionar sus fechas.')
      return
    }
    setActiveSelectionCourseId(course.id)
    setCourseSelectionOpen(true)
    setError('')
  }

  const reviewChanges = () => {
    if (!allSelectedAnalyzed) {
      setError('Analice correctamente todos los cursos seleccionados antes de aplicar las fechas.')
      return
    }
    if (enabledBlocks.length === 0) {
      setError('Seleccione al menos un parcial de Simuladores o Evaluaciones.')
      return
    }
    for (const block of selectedBlocks) {
      const schedule = schedules[block.key]
      if (!schedule.open || !schedule.close) {
        setError(`${block.scopeLabel} · ${block.partialLabel}: ingrese la fecha de apertura y de cierre.`)
        return
      }
      if (fromLocalDateTime(schedule.open) >= fromLocalDateTime(schedule.close)) {
        setError(`${block.scopeLabel} · ${block.partialLabel}: la apertura debe ser anterior al cierre.`)
        return
      }
    }
    if (selectedActivityCount === 0) {
      setError('Abra la selección por materia y marque las actividades que deben recibir las nuevas fechas.')
      return
    }
    if (changedActivities === 0) {
      setError('Todas las actividades ya tienen las fechas indicadas; no existen cambios por aplicar.')
      return
    }
    setError('')
    setConfirmOpen(true)
  }

  const saveChanges = async () => {
    if (coursesWithChanges.length === 0) return
    setSaving(true)
    setError('')
    setSaveProgress({ completed: 0, total: coursesWithChanges.length })
    const failures: string[] = []
    const completedCourseIds: number[] = []
    let updatedCourses = 0
    let updatedActivities = 0
    for (let index = 0; index < coursesWithChanges.length; index += 1) {
      const plan = coursesWithChanges[index]
      try {
        const response = await updateMoodleCourseEvaluationDates(plan.course.id, plan.updates)
        setCourseData((current) => ({
          ...current,
          [plan.course.id]: updatedResponse(current[plan.course.id] ?? plan.data, response.activities),
        }))
        completedCourseIds.push(plan.course.id)
        updatedCourses += 1
        updatedActivities += response.updated_count
      } catch (requestError) {
        failures.push(`${courseName(plan.course)}: ${errorMessage(requestError)}`)
      }
      setSaveProgress({ completed: index + 1, total: coursesWithChanges.length })
    }
    setConfirmOpen(false)
    setSaving(false)
    if (completedCourseIds.length > 0) {
      const completed = new Set(completedCourseIds)
      setCourseActivitySelections((current) => Object.fromEntries(
        Object.entries(current).map(([courseId, cmids]) => [
          courseId,
          completed.has(Number(courseId)) ? [] : cmids,
        ]),
      ))
    }
    if (updatedActivities > 0) {
      setSuccess(`Se actualizaron ${updatedActivities} actividad(es) en ${updatedCourses} curso(s).`)
    }
    if (failures.length > 0) {
      setError(`La actualización quedó incompleta. ${failures.join(' | ')}`)
    }
  }

  return (
    <div className="moodle-section moodle-evaluation-dates">
      <div className="moodle-section__heading">
        <div>
          <span>Programación académica</span>
          <h2>Fechas comunes de Simuladores y Evaluaciones</h2>
          <p>Seleccione varios cursos, analice sus secciones y programe P1, P2 y P3 con fechas comunes.</p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={selectedCourses.length === 0 || analyzing || saving}
          onClick={() => void analyzeCourses(true)}
        >
          {analyzing ? 'Analizando...' : 'Actualizar análisis'}
        </button>
      </div>

      <section className="moodle-evaluation-course-selection" aria-labelledby="moodle-course-selection-title">
        <div className="moodle-evaluation-course-selection__heading">
          <div>
            <span>Paso 1</span>
            <h3 id="moodle-course-selection-title">Seleccionar cursos de Moodle</h3>
          </div>
          <strong>{selectedCourses.length} seleccionado(s)</strong>
        </div>
        <form className="moodle-evaluation-course-search" onSubmit={submitCourseSearch}>
          <label htmlFor="moodle-evaluation-course-search-input">Buscar curso</label>
          <input
            id="moodle-evaluation-course-search-input"
            type="search"
            value={courseSearch}
            aria-describedby="moodle-evaluation-course-search-summary"
            onChange={(event) => setCourseSearch(event.target.value)}
            placeholder="Nombre, nombre corto, código o ID"
          />
          <small id="moodle-evaluation-course-search-summary">
            {courses.length} visible(s) de {coursesTotal} curso(s)
          </small>
          <button type="submit" className="moodle-button moodle-button--secondary" disabled={catalogLoading || analyzing}>
            {catalogLoading ? 'Buscando...' : 'Buscar'}
          </button>
          <button type="button" className="moodle-button moodle-button--secondary" disabled={courses.length === 0 || analyzing} onClick={selectVisibleCourses}>
            Seleccionar visibles
          </button>
          <button type="button" className="moodle-button moodle-button--secondary" disabled={selectedCourses.length === 0 || analyzing} onClick={clearSelection}>
            Limpiar selección
          </button>
        </form>

        <div className="moodle-evaluation-course-list">
          {courses.map((course) => (
            <label className={selectedIds.has(course.id) ? 'is-selected' : ''} key={course.id}>
              <input
                type="checkbox"
                checked={selectedIds.has(course.id)}
                disabled={analyzing || saving}
                onChange={() => toggleCourse(course)}
              />
              <span>
                <strong>{courseName(course)}</strong>
                <small>{course.shortname || `ID ${course.id}`} · {course.categoryname || 'Sin categoría'}</small>
              </span>
            </label>
          ))}
          {!catalogLoading && courses.length === 0 && (
            <div className="moodle-empty">No existen cursos con el criterio actual.</div>
          )}
        </div>

        <div className="moodle-evaluation-selection-actions">
          <span>
            {analyzing
              ? `Analizando ${analysisProgress.completed} de ${analysisProgress.total} curso(s)...`
              : 'El análisis identifica automáticamente las actividades de cada parcial.'}
          </span>
          <button
            type="button"
            className="moodle-button moodle-button--primary"
            disabled={selectedCourses.length === 0 || analyzing || saving}
            onClick={() => void analyzeCourses(true)}
          >
            {analyzing ? 'Analizando cursos...' : 'Analizar cursos seleccionados'}
          </button>
        </div>
      </section>

      {error && <div className="moodle-alert moodle-alert--error" role="alert">{error}</div>}

      {loadedResponses.length > 0 && !dateManagementEnabled && (
        <div className="moodle-alert moodle-alert--warning">
          <strong>Consulta disponible en modo de solo lectura.</strong>{' '}
          {loadedResponses.find((response) => !response.date_management.enabled)?.date_management.reason}
        </div>
      )}

      {loadedResponses.length > 0 && (
        <>
          <section className="moodle-common-schedule" aria-labelledby="moodle-common-schedule-title">
            <div className="moodle-common-schedule__heading">
              <div>
                <span>Paso 2</span>
                <h3 id="moodle-common-schedule-title">Definir fechas comunes</h3>
              </div>
              <p>La fecha de cierre se aplica como entrega y cierre definitivo en las tareas.</p>
            </div>
            {(['simuladores', 'evaluaciones'] as EvaluationScope[]).map((scope) => (
              <div className="moodle-common-schedule__group" key={scope}>
                <h4>{scope === 'simuladores' ? 'Simuladores' : 'Evaluaciones'}</h4>
                <div className="moodle-common-schedule__rows">
                  {SCHEDULE_BLOCKS.filter((block) => block.scope === scope).map((block) => {
                    const schedule = schedules[block.key]
                    const count = blockCounts[block.key]
                    return (
                      <div className={schedule.enabled ? 'moodle-common-schedule__row is-enabled' : 'moodle-common-schedule__row'} key={block.key}>
                        <label className="moodle-common-schedule__toggle">
                          <input
                            type="checkbox"
                            checked={schedule.enabled}
                            disabled={!dateManagementEnabled || count === 0 || saving}
                            onChange={(event) => updateSchedule(block.key, { enabled: event.target.checked })}
                          />
                          <span>
                            <strong>{block.partialLabel}</strong>
                            <small>{count} actividad(es) identificada(s)</small>
                          </span>
                        </label>
                        <label>
                          <span>Apertura común</span>
                          <input
                            type="datetime-local"
                            value={schedule.open}
                            disabled={!schedule.enabled || saving}
                            onChange={(event) => updateSchedule(block.key, { open: event.target.value })}
                          />
                        </label>
                        <label>
                          <span>Cierre común</span>
                          <input
                            type="datetime-local"
                            value={schedule.close}
                            disabled={!schedule.enabled || saving}
                            onChange={(event) => updateSchedule(block.key, { close: event.target.value })}
                          />
                        </label>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </section>

          <section className="moodle-course-analysis" aria-labelledby="moodle-course-analysis-title">
            <div className="moodle-course-analysis__heading">
              <div>
                <span>Paso 3</span>
                <h3 id="moodle-course-analysis-title">Seleccionar cambios por materia</h3>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={!dateManagementEnabled || !allSelectedAnalyzed || enabledBlocks.length === 0 || saving}
                onClick={() => openCourseSelection()}
              >
                Configurar materias
              </button>
            </div>
            <div className="moodle-course-analysis__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Curso</th>
                    <th>Sim. P1</th>
                    <th>Sim. P2</th>
                    <th>Sim. P3</th>
                    <th>Eval. P1</th>
                    <th>Eval. P2</th>
                    <th>Eval. P3</th>
                    <th>Selección</th>
                    <th>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedCourses.map((course) => {
                    const response = courseData[course.id]
                    const counts = Object.fromEntries(SCHEDULE_BLOCKS.map((block) => [
                      block.key,
                      response?.activities.filter((activity) => activityScheduleKey(activity) === block.key).length ?? 0,
                    ])) as Record<ScheduleKey, number>
                    const programmableActivities = response?.activities.filter(
                      (activity) => Boolean(activityScheduleKey(activity)),
                    ) ?? []
                    const selectedActivityIds = new Set(courseActivitySelections[course.id] ?? [])
                    const selectedActivitiesForCourse = programmableActivities.filter((activity) => {
                      const key = activityScheduleKey(activity)
                      return key ? schedules[key].enabled && selectedActivityIds.has(activity.cmid) : false
                    })
                    return (
                      <tr key={course.id}>
                        <td><strong>{courseName(course)}</strong><small>{course.shortname || `ID ${course.id}`}</small></td>
                        {SCHEDULE_BLOCKS.map((block) => <td key={block.key}>{response ? counts[block.key] : '-'}</td>)}
                        <td>
                          {response ? (
                            <>
                              <strong>{selectedActivitiesForCourse.length} actividad(es)</strong>
                              <button
                                type="button"
                                className="moodle-table-action"
                                disabled={!dateManagementEnabled || enabledBlocks.length === 0 || saving}
                                onClick={() => openCourseSelection(course.id)}
                              >
                                Seleccionar
                              </button>
                            </>
                          ) : '-'}
                        </td>
                        <td>
                          {response ? (
                            <details>
                              <summary>Ver contenido</summary>
                              <div className="moodle-course-analysis__details">
                                {selectedActivitiesForCourse.map((activity) => (
                                  <div key={activity.cmid}>
                                    <strong>{activity.name}</strong>
                                    <span>{activity.scope_label} · {activity.partial_label}</span>
                                    <small>
                                      {formatDate(activityCurrentRange(activity).open)} → {formatDate(activityCurrentRange(activity).close)}
                                    </small>
                                  </div>
                                ))}
                                {selectedActivitiesForCourse.length === 0 && (
                                  <div className="moodle-course-analysis__empty">
                                    No existen actividades seleccionadas para actualizar en esta materia.
                                  </div>
                                )}
                              </div>
                            </details>
                          ) : (
                            <span className="moodle-badge moodle-badge--warning">
                              {analysisErrors[course.id] ? 'Error' : 'Pendiente'}
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="moodle-course-analysis__note">
              La selección considera exclusivamente las actividades de Simuladores y Evaluaciones de P1, P2 y P3.
            </p>
          </section>

          <div className="moodle-evaluation-actions">
            <span>
              {configuredCourseCount} materia(s), {selectedActivityCount} actividad(es) seleccionada(s) y {changedActivities} cambio(s) efectivo(s).
            </span>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={!dateManagementEnabled || !allSelectedAnalyzed || enabledBlocks.length === 0 || saving}
              onClick={() => openCourseSelection()}
            >
              Seleccionar por materia
            </button>
            <button
              type="button"
              className="moodle-button moodle-button--primary"
              disabled={!dateManagementEnabled || !allSelectedAnalyzed || changedActivities === 0 || saving}
              onClick={reviewChanges}
            >
              Revisar actualización
            </button>
          </div>
        </>
      )}

      {courseSelectionOpen && activeSelectionCourse && activeSelectionData && (
        <div
          className="moodle-confirm-overlay moodle-date-course-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !saving) setCourseSelectionOpen(false)
          }}
        >
          <section
            className="moodle-confirm-dialog moodle-date-course-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-course-date-selection-title"
          >
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Selección por materia</span>
                <h2 id="moodle-course-date-selection-title">Simuladores y Evaluaciones</h2>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={saving}
                onClick={() => setCourseSelectionOpen(false)}
              >
                Cerrar
              </button>
            </div>

            <div className="moodle-date-course-summary" aria-label="Resumen de selección">
              <div><span>Materias analizadas</span><strong>{loadedResponses.length}</strong></div>
              <div><span>Materias configuradas</span><strong>{configuredCourseCount}</strong></div>
              <div><span>Actividades seleccionadas</span><strong>{selectedActivityCount}</strong></div>
            </div>

            <div className="moodle-date-course-workspace">
              <nav className="moodle-date-course-nav" aria-label="Materias escogidas">
                {selectedCourses.filter((course) => Boolean(courseData[course.id])).map((course) => {
                  const selectedActivityIds = new Set(courseActivitySelections[course.id] ?? [])
                  const selectedCount = courseData[course.id].activities.filter((activity) => {
                    const key = activityScheduleKey(activity)
                    return key ? schedules[key].enabled && selectedActivityIds.has(activity.cmid) : false
                  }).length
                  return (
                    <button
                      type="button"
                      className={course.id === activeSelectionCourse.id ? 'is-active' : ''}
                      key={course.id}
                      onClick={() => setActiveSelectionCourseId(course.id)}
                    >
                      <span>
                        <strong>{courseName(course)}</strong>
                        <small>{course.shortname || `ID ${course.id}`}</small>
                      </span>
                      <b>{selectedCount}</b>
                    </button>
                  )
                })}
              </nav>

              <div className="moodle-date-course-detail">
                <header>
                  <div>
                    <span>Materia seleccionada</span>
                    <h3>{courseName(activeSelectionCourse)}</h3>
                    <small>{activeSelectionCourse.shortname || `ID ${activeSelectionCourse.id}`} · {activeSelectionCourse.categoryname || 'Sin categoría'}</small>
                  </div>
                  <div className="moodle-date-course-detail__actions">
                    <button
                      type="button"
                      className="moodle-button moodle-button--secondary"
                      disabled={saving || enabledBlocks.length === 0}
                      onClick={() => selectAvailableCourseActivities(activeSelectionCourse.id)}
                    >
                      Seleccionar todas
                    </button>
                    <button
                      type="button"
                      className="moodle-button moodle-button--secondary"
                      disabled={saving || activeSelectedActivityCount === 0}
                      onClick={() => clearCourseActivities(activeSelectionCourse.id)}
                    >
                      Limpiar materia
                    </button>
                  </div>
                </header>

                <div className="moodle-date-scope-grid">
                  {(['simuladores', 'evaluaciones'] as EvaluationScope[]).map((scope) => (
                    <section className="moodle-date-scope" key={scope}>
                      <h4>{scope === 'simuladores' ? 'Simuladores' : 'Evaluaciones'}</h4>
                      <div className="moodle-date-scope__partials">
                        {SCHEDULE_BLOCKS.filter((block) => block.scope === scope).map((block) => {
                          const activities = courseBlockActivities(activeSelectionData, block.key)
                          const selectedActivityIds = new Set(courseActivitySelections[activeSelectionCourse.id] ?? [])
                          const selectedActivities = activities.filter((activity) => selectedActivityIds.has(activity.cmid))
                          const available = schedules[block.key].enabled && activities.length > 0 && dateManagementEnabled
                          const allSelected = available && selectedActivities.length === activities.length
                          const partiallySelected = available
                            && selectedActivities.length > 0
                            && selectedActivities.length < activities.length
                          return (
                            <article
                              className={`moodle-date-partial${selectedActivities.length > 0 ? ' has-selection' : ''}${available ? '' : ' is-disabled'}`}
                              key={block.key}
                            >
                              <label className="moodle-date-partial__selector">
                                <ActivityGroupCheckbox
                                  checked={allSelected}
                                  indeterminate={partiallySelected}
                                  disabled={!available || saving}
                                  label={`Seleccionar todas las actividades de ${block.scopeLabel}, ${block.partialLabel}`}
                                  onChange={() => toggleCourseBlock(activeSelectionCourse.id, block.key)}
                                />
                                <span>
                                  <strong>{block.partialLabel}</strong>
                                  <small>{selectedActivities.length} de {activities.length} seleccionada(s)</small>
                                </span>
                                <em>
                                  {schedules[block.key].enabled
                                    ? `${formatDate(fromLocalDateTime(schedules[block.key].open))} → ${formatDate(fromLocalDateTime(schedules[block.key].close))}`
                                    : 'Fechas no habilitadas'}
                                </em>
                              </label>
                              <div className="moodle-date-activity-list">
                                {activities.map((activity) => {
                                  const selected = selectedActivityIds.has(activity.cmid)
                                  const currentRange = activityCurrentRange(activity)
                                  return (
                                    <label
                                      className={`moodle-date-activity${selected ? ' is-selected' : ''}${available ? '' : ' is-disabled'}`}
                                      key={activity.cmid}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={selected}
                                        disabled={!available || saving}
                                        onChange={() => toggleCourseActivity(activeSelectionCourse.id, activity.cmid)}
                                      />
                                      <span>
                                        <strong>{activity.name}</strong>
                                        <small>{activity.type_label} · {activity.section_name || block.partialLabel}</small>
                                      </span>
                                      <em>
                                        Fecha actual: {formatDate(currentRange.open)} → {formatDate(currentRange.close)}
                                      </em>
                                    </label>
                                  )
                                })}
                                {activities.length === 0 && (
                                  <p>No se identificaron actividades en este parcial.</p>
                                )}
                              </div>
                            </article>
                          )
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            </div>

            <div className="moodle-confirm-dialog__actions moodle-date-course-dialog__actions">
              <span>
                {activeSelectedActivityCount} actividad(es) en esta materia · {configuredCourseCount} de {loadedResponses.length} materia(s) configurada(s)
              </span>
              <button
                type="button"
                className="moodle-button moodle-button--primary"
                onClick={() => setCourseSelectionOpen(false)}
              >
                Confirmar selección
              </button>
            </div>
          </section>
        </div>
      )}

      {confirmOpen && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !saving) setConfirmOpen(false)
          }}
        >
          <section className="moodle-confirm-dialog moodle-evaluation-confirm" role="dialog" aria-modal="true" aria-labelledby="moodle-dates-title">
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Confirmación</span>
                <h2 id="moodle-dates-title">Aplicar fechas comunes en Moodle</h2>
              </div>
              <button type="button" className="moodle-button moodle-button--secondary" disabled={saving} onClick={() => setConfirmOpen(false)}>
                Cerrar
              </button>
            </div>
            <div className="moodle-confirm-dialog__body">
              <p>
                Se actualizarán <strong>{changedActivities} actividad(es)</strong> en{' '}
                <strong>{coursesWithChanges.length} curso(s)</strong>. La operación se registra en auditoría por cada actividad.
              </p>
              <div className="moodle-evaluation-review">
                {coursesWithChanges.map((plan) => {
                  const changedActivityIds = new Set(plan.updates.map((update) => update.cmid))
                  const changedCourseActivities = plan.data.activities.filter(
                    (activity) => changedActivityIds.has(activity.cmid),
                  )
                  return (
                    <div key={plan.course.id}>
                      <strong>{courseName(plan.course)}</strong>
                      <span>{changedCourseActivities.map(
                        (activity) => `${activity.scope_label} · ${activity.partial_label}: ${activity.name}`,
                      ).join(' | ')}</span>
                      <small>{plan.updates.length} actividad(es) con cambios efectivos</small>
                    </div>
                  )
                })}
              </div>
              {saving && (
                <div className="moodle-evaluation-save-progress" role="status">
                  Actualizando {saveProgress.completed} de {saveProgress.total} curso(s)...
                </div>
              )}
            </div>
            <div className="moodle-confirm-dialog__actions">
              <button type="button" className="moodle-button moodle-button--primary" disabled={saving} onClick={() => void saveChanges()}>
                {saving ? 'Aplicando fechas...' : 'Confirmar actualización'}
              </button>
            </div>
          </section>
        </div>
      )}

      {success && (
        <div className="institutional-email-notification-overlay" role="presentation">
          <section className="institutional-email-notification" role="status" aria-live="polite" aria-atomic="true">
            <span className="institutional-email-notification__mark" aria-hidden="true">✓</span>
            <div>
              <p className="eyebrow">Proceso completado</p>
              <h3>{success}</h3>
              <small>Esta ventana se cerrará automáticamente en 3 segundos.</small>
            </div>
            <span className="institutional-email-notification__timer" aria-hidden="true" />
          </section>
        </div>
      )}
    </div>
  )
}
