import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import {
  applyMoodleGrades,
  fetchMoodleGradeCatalog,
  fetchMoodleGradeCourseContext,
  fetchMoodleGradeHistory,
  previewMoodleGrades,
} from '../../lib/api'
import type {
  MoodleGradeCatalogResponse,
  MoodleGradeCourseOption,
  MoodleGradeChange,
  MoodleGradeHistoryResponse,
  MoodleGradePeriodOption,
  MoodleGradePreviewResponse,
} from '../../types/app'

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return 'No se pudo completar la migración de notas.'
  if (error.message.trim().toLocaleLowerCase('es-EC') === 'not found') {
    return 'No se encontró el servicio de validación del curso. Actualice la pantalla e inténtelo nuevamente.'
  }
  return error.message
}

function grade(value: number | null): string {
  return value === null
    ? 'Sin nota'
    : value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function numberLabel(value: number): string {
  return value.toLocaleString('es-EC', { maximumFractionDigits: 2 })
}

function componentMigrationRule(change: MoodleGradeChange): string {
  if (change.field.endsWith('Examen')) {
    return 'Cuestionario Moodle → examen teórico (40 %)'
  }
  if (change.field.endsWith('Tareas')) {
    return 'Tarea Moodle → tareas (30 %)'
  }
  if (change.field.endsWith('Proyectos')) {
    return 'La misma tarea Moodle → proyectos (30 %)'
  }
  if (change.field === 'teoriaHomo') {
    return 'Cuestionario Moodle → teoría de homologación (40 %)'
  }
  return 'Tarea Moodle → práctica de homologación (60 %)'
}

function activityTypeLabel(value: string): string {
  if (value === 'quiz') return 'Cuestionario'
  if (value === 'assign') return 'Tarea'
  return 'Actividad'
}

function moodleGradeTrace(change: MoodleGradeChange): string | null {
  if (change.moodle_raw_grade === null || change.moodle_raw_grade === undefined) return null
  if (change.moodle_grade_scale_source === 'institutional_decimal_shift_10') {
    return 'Se corrigió el desplazamiento decimal confirmado por la escala y el porcentaje de Moodle.'
  }
  if (change.moodle_grade_scale_source === 'gradeformatted_direct_10') {
    return 'Se conserva la calificación visible en Moodle sobre 10.'
  }
  const scale = change.moodle_grade_min !== null
    && change.moodle_grade_min !== undefined
    && change.moodle_grade_max !== null
    && change.moodle_grade_max !== undefined
    ? `escala ${numberLabel(change.moodle_grade_min)} a ${numberLabel(change.moodle_grade_max)}`
    : 'escala detectada por Moodle'
  return `Escala de origen: ${scale}. La calificación fue normalizada sobre 10.`
}

function dateTime(value: string | null): string {
  if (!value) return 'Sin registro'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? 'Sin registro'
    : new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'medium' }).format(parsed)
}

function normalizedSearch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-EC')
    .trim()
}

function courseMatches(course: MoodleGradeCourseOption, search: string): boolean {
  const tokens = normalizedSearch(search).split(/\s+/).filter(Boolean)
  if (!tokens.length) return true
  const searchableText = normalizedSearch([
    course.name,
    course.shortname,
    course.idnumber,
    course.matched_course_code,
    String(course.id),
  ].join(' '))
  return tokens.every((token) => searchableText.includes(token))
}

function courseOptionLabel(course: MoodleGradeCourseOption): string {
  const reference = course.matched_course_code || course.shortname || course.idnumber || `ID ${course.id}`
  return course.has_academic_match
    ? `${course.name} · ${reference}`
    : `${course.name} · ${reference} · Pendiente de validar por CorreoIntec`
}

function uniquePeriods(periods: MoodleGradePeriodOption[]): MoodleGradePeriodOption[] {
  const periodsByCode = new Map<number, MoodleGradePeriodOption>()
  periods.forEach((period) => {
    const current = periodsByCode.get(period.period_code)
    if (!current || Number(period.students ?? 0) > Number(current.students ?? 0)) {
      periodsByCode.set(period.period_code, period)
    }
  })
  return [...periodsByCode.values()].sort((left, right) => right.period_code - left.period_code)
}

function automaticPeriodCodes(course: MoodleGradeCourseOption | null | undefined): string[] {
  if (!course?.has_academic_match) return []

  const validPeriods = uniquePeriods(course.periods ?? []).filter(
    (period) => Number(period.students ?? 0) > 0,
  )
  if (!validPeriods.length) return []

  const recommendedCodes = course.recommended_period_codes?.length
    ? course.recommended_period_codes
    : course.recommended_period_code == null
      ? []
      : [course.recommended_period_code]
  const recommendedPeriods = recommendedCodes
    .map((code) => validPeriods.find((period) => period.period_code === Number(code)))
    .filter((period): period is MoodleGradePeriodOption => Boolean(period))
  if (!recommendedPeriods.length) return []

  const selectedType = recommendedPeriods[0].period_type
  return recommendedPeriods
    .filter((period) => period.period_type === selectedType)
    .slice(0, 3)
    .map((period) => String(period.period_code))
}

const STATUS_LABELS: Record<string, string> = {
  ready: 'Listo para aplicar',
  ready_override: 'Listo para reemplazar',
  unchanged: 'Sin cambios',
  source_unchanged: 'Sin cambio en Moodle',
  manual_conflict: 'Cambio manual protegido',
  stale_preview: 'Vista previa desactualizada',
  stale_enrollment: 'Matrícula modificada',
  already_graded: 'Nota existente protegida',
  not_enrolled: 'No matriculado en Moodle',
  missing_institutional_email: 'Sin correo institucional',
  ambiguous_user: 'Usuario ambiguo',
  without_grades: 'Sin notas Moodle',
  without_exam_grade: 'Sin exámenes válidos',
  ambiguous_grade: 'Nota Moodle ambigua',
  invalid_grade: 'Nota inválida',
}

const EMPTY_COURSES: MoodleGradeCourseOption[] = []

const COURSE_RESOLUTION_STAGES = [
  'Consultando los participantes del curso en Moodle',
  'Comparando los correos institucionales con CorreoIntec',
  'Vinculando codestud con el registro de DATOS_ESTUD',
  'Validando la asignatura, las matrículas y los períodos académicos',
]

const COURSE_RESOLUTION_PROGRESS = [20, 45, 70, 90]

function identityMatchLabel(method: string) {
  if (method === 'cedula_exacta') return 'Cédula exacta verificada'
  if (method === 'nombre_exacto_correo_un_caracter') {
    return 'Nombre completo exacto y diferencia de un carácter en el correo'
  }
  return 'Correo institucional exacto'
}

export function MoodleGradeSyncPanel() {
  const [catalog, setCatalog] = useState<MoodleGradeCatalogResponse | null>(null)
  const [history, setHistory] = useState<MoodleGradeHistoryResponse | null>(null)
  const [courseSearch, setCourseSearch] = useState('')
  const [courseId, setCourseId] = useState('')
  const [periodCodes, setPeriodCodes] = useState<string[]>([])
  const [periodToAdd, setPeriodToAdd] = useState('')
  const [preview, setPreview] = useState<MoodleGradePreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [resolvingCourse, setResolvingCourse] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [confirmApply, setConfirmApply] = useState(false)
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [resolutionStage, setResolutionStage] = useState(0)
  const courseResolutionId = useRef(0)
  const catalogCourses = catalog?.courses ?? EMPTY_COURSES
  const configuredMappings = catalog?.configured_mappings ?? []
  const previewChanges = preview?.changes ?? []
  const enrollmentWarnings = preview?.enrollment_warnings ?? []
  const historyItems = history?.items ?? []

  const selectedCourse = useMemo(
    () => catalogCourses.find((course) => course.id === Number(courseId)) ?? null,
    [catalogCourses, courseId],
  )
  const identityValidation = selectedCourse?.moodle_identity_validation
  const periodOptions = useMemo(
    () => uniquePeriods(selectedCourse?.periods ?? []),
    [selectedCourse],
  )
  const selectedPeriods = useMemo(
    () => periodCodes
      .map((code) => periodOptions.find((period) => period.period_code === Number(code)))
      .filter((period): period is MoodleGradePeriodOption => Boolean(period)),
    [periodCodes, periodOptions],
  )
  const selectedPeriodType = selectedPeriods[0]?.period_type ?? null
  const availablePeriods = useMemo(
    () => periodOptions.filter((period) => (
      !periodCodes.includes(String(period.period_code))
      && (!selectedPeriodType || period.period_type === selectedPeriodType)
    )),
    [periodCodes, periodOptions, selectedPeriodType],
  )
  const filteredCourses = useMemo(
    () => catalogCourses.filter((course) => courseMatches(course, courseSearch)),
    [catalogCourses, courseSearch],
  )
  const readyCount = previewChanges.filter(
    (item) => item.status === 'ready' || item.status === 'ready_override',
  ).length
  const correctedScaleCount = previewChanges.filter(
    (item) => item.moodle_grade_scale_source === 'institutional_decimal_shift_10',
  ).length

  const loadCatalog = async (refresh = false) => {
    setLoading(true)
    setError('')
    try {
      let result = await fetchMoodleGradeCatalog(refresh)
      const selectedCourseId = Number(courseId)
      let resolvedCourseId = 0
      if (selectedCourseId > 0 && result.courses.some((course) => course.id === selectedCourseId)) {
        const resolvedCourse = await fetchMoodleGradeCourseContext(selectedCourseId, refresh)
        resolvedCourseId = resolvedCourse.id
        result = {
          ...result,
          courses: result.courses.map((course) => (
            course.id === resolvedCourse.id ? resolvedCourse : course
          )),
        }
      }
      let currentCourse = result.courses.find((course) => course.id === Number(courseId))
        ?? result.courses.find((course) => course.has_academic_match)
        ?? result.courses[0]
      if (currentCourse && currentCourse.id !== resolvedCourseId) {
        const resolvedCourse = await fetchMoodleGradeCourseContext(currentCourse.id, refresh)
        result = {
          ...result,
          courses: result.courses.map((course) => (
            course.id === resolvedCourse.id ? resolvedCourse : course
          )),
        }
        currentCourse = resolvedCourse
      }
      setCatalog(result)
      const currentPeriodOptions = uniquePeriods(currentCourse?.periods ?? [])
      const preservedPeriods = periodCodes
        .map((code) => currentPeriodOptions.find(
          (period) => period.period_code === Number(code),
        ))
        .filter((period): period is MoodleGradePeriodOption => Boolean(period))
      const preservedType = preservedPeriods[0]?.period_type
      const compatiblePreservedPeriods = preservedPeriods
        .filter((period) => period.period_type === preservedType)
        .slice(0, 3)
      setCourseId(currentCourse ? String(currentCourse.id) : '')
      setPeriodCodes(
        compatiblePreservedPeriods.length
          ? compatiblePreservedPeriods.map((period) => String(period.period_code))
          : automaticPeriodCodes(currentCourse),
      )
      setPeriodToAdd('')
      setPreview(null)
      setHistory(await fetchMoodleGradeHistory())
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadCatalog()
    }, 0)
    // La carga inicial conserva la selección local en las actualizaciones posteriores.
    return () => window.clearTimeout(timeoutId)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!success) return undefined
    const timeoutId = window.setTimeout(() => setSuccess(''), 3000)
    return () => window.clearTimeout(timeoutId)
  }, [success])

  useEffect(() => {
    if (!resolvingCourse) return undefined
    const intervalId = window.setInterval(() => {
      setResolutionStage((current) => Math.min(current + 1, COURSE_RESOLUTION_STAGES.length - 1))
    }, 900)
    return () => window.clearInterval(intervalId)
  }, [resolvingCourse])

  const changeCourse = async (nextCourseId: string) => {
    const requestId = courseResolutionId.current + 1
    courseResolutionId.current = requestId
    setCourseId(nextCourseId)
    setPeriodCodes([])
    setPeriodToAdd('')
    setPreview(null)
    setConfirmApply(false)
    setError('')
    setSuccess('')
    setResolutionStage(0)
    if (!nextCourseId) {
      setResolvingCourse(false)
      return
    }

    setResolvingCourse(true)
    try {
      const resolvedCourse = await fetchMoodleGradeCourseContext(Number(nextCourseId))
      if (courseResolutionId.current !== requestId) return
      setCatalog((current) => current
        ? {
            ...current,
            courses: current.courses.map((course) => (
              course.id === resolvedCourse.id ? resolvedCourse : course
            )),
          }
        : current)
      setPeriodCodes(automaticPeriodCodes(resolvedCourse))
    } catch (requestError) {
      if (courseResolutionId.current === requestId) setError(errorMessage(requestError))
    } finally {
      if (courseResolutionId.current === requestId) setResolvingCourse(false)
    }
  }

  const changeCourseSearch = (value: string) => {
    courseResolutionId.current += 1
    setResolvingCourse(false)
    setCourseSearch(value)
    setCourseId('')
    setPeriodCodes([])
    setPeriodToAdd('')
    setPreview(null)
    setConfirmApply(false)
    setError('')
    setSuccess('')
  }

  const addPeriod = () => {
    if (!periodToAdd || periodCodes.length >= 3) return
    const period = periodOptions.find((item) => item.period_code === Number(periodToAdd))
    if (!period || periodCodes.includes(periodToAdd)) return
    if (selectedPeriodType && period.period_type !== selectedPeriodType) {
      setError('Seleccione únicamente períodos regulares o únicamente períodos de homologación.')
      return
    }
    setPeriodCodes((current) => [...current, periodToAdd])
    setPeriodToAdd('')
    setPreview(null)
    setConfirmApply(false)
    setError('')
    setSuccess('')
  }

  const removePeriod = (code: string) => {
    setPeriodCodes((current) => current.filter((item) => item !== code))
    setPeriodToAdd('')
    setPreview(null)
    setConfirmApply(false)
    setError('')
    setSuccess('')
  }

  const submitPreview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!courseId || !periodCodes.length) return
    setLoading(true)
    setError('')
    setSuccess('')
    setPreview(null)
    setConfirmApply(false)
    try {
      setPreview(
        await previewMoodleGrades(
          Number(courseId),
          periodCodes.map(Number),
          true,
          replaceExisting,
        ),
      )
    } catch (requestError) {
      setPreview(null)
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  const confirmSynchronization = async () => {
    if (!courseId || !periodCodes.length) return
    setApplying(true)
    setError('')
    setSuccess('')
    try {
      const result = await applyMoodleGrades(
        Number(courseId),
        periodCodes.map(Number),
        replaceExisting,
      )
      setPreview(result)
      setSuccess(result.message)
      setConfirmApply(false)
      try {
        setHistory(await fetchMoodleGradeHistory())
      } catch (historyError) {
        setError(
          `Las notas se migraron correctamente, pero no se pudo actualizar el historial: ${errorMessage(historyError)}`,
        )
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="moodle-section moodle-grade-sync">
      <div className="moodle-section__heading">
        <div>
          <span>Migración académica</span>
          <h2>Notas desde Moodle</h2>
          <p>
            Seleccione el curso Moodle y hasta tres períodos académicos del mismo tipo. La vista
            previa consolida sus estudiantes sin modificar calificaciones. Solo se consideran
            cuestionarios y tareas de la sección Evaluación; se migran cuando su nota cambia.
          </p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={loading}
          onClick={() => void loadCatalog(true)}
        >
          {loading ? 'Actualizando...' : 'Actualizar catálogo'}
        </button>
      </div>

      <div className="moodle-grade-rule">
        <strong>Regla activa de migración</strong>
        <span>
          <b>Regular:</b> cada cuestionario de Moodle se registra como Examen teórico 40 %.
          Cada tarea se registra como Examen práctico y su nota se duplica en Tareas 30 % y
          Proyectos 30 % del mismo parcial. Si existen dos o más cuestionarios o tareas en un
          parcial, se conserva únicamente la nota más alta normalizada sobre 10. Solo se toman
          actividades del bloque Evaluación y de sus secciones Primer, Segundo o Tercer parcial;
          simuladores y recuperación quedan excluidos.
          {' '}<b>Homologación:</b> el cuestionario se registra en Teoría 40 % y la tarea en
          Práctica 60 %.
        </span>
      </div>

      {catalog && (
        <div className={`moodle-alert ${
          catalog.change_detection_enabled && configuredMappings.length
            ? 'moodle-alert--success'
            : 'moodle-alert--warning'
        }`}>
          {catalog.change_detection_enabled && configuredMappings.length
            ? `Detección automática activa cada ${catalog.change_detection_interval_minutes} minuto(s) para ${configuredMappings.length} relación(es) autorizada(s).`
            : 'La selección manual se valida por CorreoIntec. Para la detección automática programada, habilite el proceso y guarde al menos una relación curso-período.'}
        </div>
      )}

      <form className="moodle-grade-controls" onSubmit={submitPreview}>
        <label className="moodle-grade-control moodle-grade-course-search">
          <span>Buscar curso Moodle</span>
          <input
            type="search"
            value={courseSearch}
            placeholder="Nombre, código, nombre corto o ID"
            autoComplete="off"
            onChange={(event) => changeCourseSearch(event.target.value)}
          />
          <small>
            {filteredCourses.length} de {catalog?.totals?.courses ?? catalogCourses.length} curso(s)
          </small>
        </label>
        <label className="moodle-grade-control moodle-grade-course-select">
          <span>Curso Moodle</span>
          <select
            value={courseId}
            disabled={loading || resolvingCourse}
            onChange={(event) => void changeCourse(event.target.value)}
          >
            <option value="">Seleccione un curso Moodle</option>
            {filteredCourses.map((course) => (
              <option key={course.id} value={course.id}>
                {courseOptionLabel(course)}
              </option>
            ))}
            {courseSearch.trim() && !filteredCourses.length && (
              <option value="" disabled>No existen cursos con ese criterio</option>
            )}
          </select>
          <small>
            {resolvingCourse
              ? 'Validando CorreoIntec y código único del estudiante...'
              : !selectedCourse
                ? 'Seleccione un curso para validar CorreoIntec y el código único del estudiante.'
              : selectedCourse.has_academic_match && selectedPeriods.length
                ? `${selectedCourse.matched_course_code} · ${selectedCourse.matched_students ?? 0} coincidencia(s) académica(s) · ${selectedPeriods.length} período(s) seleccionado(s) por estudiantes y materia.`
                : selectedCourse.resolution_reason || 'El curso no tiene períodos válidos con estudiantes activos.'}
          </small>
        </label>
        <div className="moodle-grade-control moodle-grade-period-selector">
          <span>Períodos académicos</span>
          <div className="moodle-grade-period-selector__add">
            <select
              value={periodToAdd}
              onChange={(event) => setPeriodToAdd(event.target.value)}
              disabled={resolvingCourse || !availablePeriods.length || periodCodes.length >= 3}
              aria-label="Período académico para agregar"
            >
              <option value="">
                {periodCodes.length >= 3
                  ? 'Límite de tres períodos alcanzado'
                  : 'Seleccione otro período de INTECBDD'}
              </option>
              {availablePeriods.map((period) => (
                <option key={period.period_code} value={period.period_code}>
                  {period.period_name || `Período ${period.period_code}`} · {period.students} estudiante(s)
                </option>
              ))}
            </select>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={resolvingCourse || !periodToAdd || periodCodes.length >= 3}
              onClick={addPeriod}
            >
              Agregar
            </button>
          </div>
          <div className="moodle-grade-period-selector__selected" aria-live="polite">
            {selectedPeriods.map((period) => (
              <div key={period.period_code} className="moodle-grade-period-chip">
                <span>
                  {period.period_name || `Período ${period.period_code}`} · {period.students} estudiante(s)
                </span>
                <button
                  type="button"
                  title={`Quitar ${period.period_name}`}
                  aria-label={`Quitar ${period.period_name}`}
                  onClick={() => removePeriod(String(period.period_code))}
                >
                  Quitar
                </button>
              </div>
            ))}
            {!selectedPeriods.length && <small>Los períodos se seleccionan al validar el curso.</small>}
          </div>
        </div>
        <div className="moodle-grade-control moodle-grade-preview-action">
          <span>Validación</span>
          <button
            type="submit"
            className="moodle-button moodle-button--primary"
            disabled={loading || resolvingCourse || !courseId || !periodCodes.length}
          >
            Previsualizar migración
          </button>
          <small>
            Compara el correo Moodle con CorreoIntec, ancla codestud, valida la asignatura en PENSUM y busca la matrícula en CARRERAXESTUD.
          </small>
        </div>
        <label className="moodle-grade-override">
          <input
            type="checkbox"
            checked={replaceExisting}
            onChange={(event) => {
              setReplaceExisting(event.target.checked)
              setPreview(null)
              setConfirmApply(false)
              setError('')
              setSuccess('')
            }}
          />
          <span>
            <strong>Permitir reemplazo manual de notas existentes</strong>
            <small>
              Requiere una nueva vista previa y confirmación. La operación queda registrada en auditoría.
            </small>
          </span>
        </label>
      </form>

      {identityValidation && (
        <div
          className={`moodle-grade-identity-check ${
            identityValidation.moodle_identity_conflicts
              || identityValidation.duplicate_moodle_emails
              ? 'has-conflicts'
              : ''
          }`}
          aria-label="Validación de identidades institucionales del curso"
        >
          <div>
            <span>Estudiantes Moodle</span>
            <strong>{identityValidation.moodle_student_users}</strong>
          </div>
          <div>
            <span>Identidades institucionales</span>
            <strong>{identityValidation.moodle_users_with_institutional_email}</strong>
          </div>
          <div>
            <span>Desde correo Moodle</span>
            <strong>{identityValidation.moodle_identity_from_email}</strong>
          </div>
          <div>
            <span>Desde usuario Moodle</span>
            <strong>{identityValidation.moodle_identity_from_username}</strong>
          </div>
          <div>
            <span>Sin correo institucional</span>
            <strong>{identityValidation.moodle_users_without_institutional_email}</strong>
          </div>
          <div>
            <span>Correos reconciliados</span>
            <strong>{identityValidation.moodle_registry_email_reconciled}</strong>
          </div>
          <div>
            <span>Conflictos bloqueados</span>
            <strong>
              {identityValidation.moodle_identity_conflicts
                + identityValidation.duplicate_moodle_emails
                + identityValidation.moodle_registry_reconciliation_conflicts}
            </strong>
          </div>
        </div>
      )}

      {!catalogCourses.length && !loading && (
        <div className="moodle-alert moodle-alert--warning">
          Moodle no devolvió cursos disponibles para la cuenta configurada.
        </div>
      )}
      {selectedCourse && !selectedCourse.has_academic_match && !resolvingCourse && (
        <div className="moodle-alert moodle-alert--warning">
          {selectedCourse.resolution_reason
            || 'No se encontró una matrícula activa en INTECBDD para los CorreosIntec del curso Moodle.'}
        </div>
      )}
      {error && <div className="moodle-alert moodle-alert--error">{error}</div>}
      {success && <div className="moodle-alert moodle-alert--success">{success}</div>}
      {replaceExisting && (
        <div className="moodle-alert moodle-alert--warning">
          Modo de reemplazo manual activo. Verifique el curso, el período y cada diferencia antes de migrar.
        </div>
      )}

      {preview && (
        <>
          <div className="moodle-grade-summary">
            <div><span>Matrículas INTECBDD</span><strong>{preview.course_validation.academic_enrollments}</strong></div>
            <div><span>Usuarios del curso</span><strong>{preview.course_validation.moodle_course_users}</strong></div>
            <div><span>Correos institucionales</span><strong>{preview.course_validation.moodle_users_with_institutional_email}</strong></div>
            <div><span>Validados por correo</span><strong>{preview.course_validation.matched_by_email}</strong></div>
            <div><span>Correos reconciliados</span><strong>{preview.course_validation.matched_by_reconciled_identity}</strong></div>
            <div><span>Aplicables</span><strong>{readyCount}</strong></div>
            <div><span>Advertencias</span><strong>{enrollmentWarnings.length}</strong></div>
            <div><span>Escalas corregidas</span><strong>{correctedScaleCount}</strong></div>
            <div><span>Períodos / tipo</span><strong>{preview.periods?.length ?? 0} · {preview.period?.type ?? 'Sin tipo'}</strong></div>
          </div>

          {preview.period.type === 'R' && (
            <div className="moodle-grade-selection-criteria" role="note">
              <strong>Criterio aplicado por cada parcial</strong>
              <span>Cuestionarios: se selecciona la nota más alta para examen teórico (40 %).</span>
              <span>Tareas: se selecciona la nota más alta y se replica en tareas (30 %) y proyectos (30 %).</span>
              <span>Las actividades de un parcial nunca se comparan con las de otro parcial.</span>
            </div>
          )}
          <p className="moodle-grade-rule-text">{preview.rule}</p>
          <div className="moodle-table-wrap">
            <table className="moodle-table moodle-grade-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Componente</th>
                  <th>Nota actual</th>
                  <th>Nota validada / 10</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {previewChanges.map((change) => (
                  <tr key={`${change.row_id}-${change.field}`}>
                    <td>
                      <strong>{change.student}</strong>
                      <small>INTECBDD: {change.email} · {change.email_source}</small>
                      <small>Moodle: {change.moodle_email} · {change.moodle_email_source}</small>
                      {change.registry_email_mismatch && (
                        <small className="moodle-grade-identity-note">
                          {identityMatchLabel(change.identity_match_method)}
                        </small>
                      )}
                    </td>
                    <td>{change.career}<small>{change.period}</small></td>
                    <td>
                      <strong className="moodle-grade-component-name">{change.component}</strong>
                      <span className="moodle-grade-component-rule">
                        {componentMigrationRule(change)}
                      </span>
                      {change.moodle_partial_label && (
                        <small>
                          Segmento: {change.moodle_partial_label}
                          {change.moodle_partial_source === 'segment'
                            ? ' · identificado por segmento Moodle'
                            : change.moodle_partial_source === 'label'
                              ? ' · identificado por etiqueta'
                              : ''}
                        </small>
                      )}
                      <small>Actividad seleccionada: {change.moodle_grade_item}</small>
                      {!!change.moodle_grade_candidates?.length && (
                        <ul className="moodle-grade-candidate-list">
                          {change.moodle_grade_candidates.map((candidate) => (
                            <li
                              key={`${change.row_id}-${change.field}-${candidate.item_id}`}
                              className={candidate.selected ? 'is-selected' : undefined}
                            >
                              <span>
                                {activityTypeLabel(candidate.activity_type)} · {candidate.item_name}
                              </span>
                              <strong>{grade(candidate.grade)}</strong>
                              {candidate.selected && <em>Mayor nota</em>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>{grade(change.current_grade)}</td>
                    <td className="moodle-grade-normalized">
                      <strong>{grade(change.incoming_grade)}</strong>
                      {change.moodle_grade_scale_source === 'institutional_decimal_shift_10' && (
                        <span className="moodle-badge moodle-badge--success">Escala corregida</span>
                      )}
                      {moodleGradeTrace(change) && <small>{moodleGradeTrace(change)}</small>}
                    </td>
                    <td>
                      <span className={`moodle-badge ${change.status === 'ready' || change.status === 'ready_override' ? 'moodle-badge--success' : 'moodle-badge--warning'}`}>
                        {STATUS_LABELS[change.status] ?? change.status}
                      </span>
                      <small>{change.reason}</small>
                    </td>
                  </tr>
                ))}
                {!previewChanges.length && (
                  <tr><td colSpan={6} className="moodle-table__empty">No existen cuestionarios o tareas válidas en la sección Evaluación.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {!!enrollmentWarnings.length && (
            <details className="moodle-grade-warnings">
              <summary>Revisar {enrollmentWarnings.length} advertencia(s) de matrícula</summary>
              <ul>
                {enrollmentWarnings.map((warning) => (
                  <li key={`${warning.student_code}-${warning.period_code}-${warning.status}`}>
                    <strong>{warning.student}:</strong> {warning.reason}
                    <small>
                      {warning.email
                        ? `INTECBDD: ${warning.email} · ${warning.email_source}`
                        : 'Sin correo institucional registrado'}
                      {warning.moodle_email && (
                        <> · Moodle: {warning.moodle_email} · {warning.moodle_email_source}</>
                      )}
                      {warning.registry_email_mismatch && (
                        <> · {identityMatchLabel(warning.identity_match_method)}</>
                      )}
                    </small>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="moodle-grade-actions">
            {!catalog?.apply_enabled && (
              <span>La migración está deshabilitada en la configuración del servidor.</span>
            )}
            <button
              type="button"
              className="moodle-button moodle-button--success"
              disabled={!preview.can_apply || readyCount === 0}
              onClick={() => setConfirmApply(true)}
            >
              Migrar {readyCount} nota(s)
            </button>
          </div>
        </>
      )}

      <details className="moodle-grade-history">
        <summary>Historial de migraciones</summary>
        <div className="moodle-table-wrap">
          <table className="moodle-table">
            <thead><tr><th>Fecha</th><th>Modo</th><th>Estado</th><th>Procesadas</th><th>Actualizadas</th><th>Errores</th><th>Usuario</th></tr></thead>
            <tbody>
              {historyItems.map((item) => (
                <tr key={item.id}>
                  <td>{dateTime(item.fecha_inicio)}</td>
                  <td>{item.modo_ejecucion}</td>
                  <td>{item.estado}</td>
                  <td>{item.notas_procesadas}</td>
                  <td>{item.notas_actualizadas}</td>
                  <td>{item.notas_error}</td>
                  <td>{item.usuario_id || 'Sistema'}</td>
                </tr>
              ))}
              {!historyItems.length && (
                <tr><td colSpan={7} className="moodle-table__empty">Todavía no existen migraciones registradas.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </details>

      {resolvingCourse && (
        <div className="moodle-confirm-overlay" role="presentation">
          <section
            className="moodle-confirm-dialog moodle-analysis-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-course-analysis-title"
            aria-describedby="moodle-course-analysis-description"
          >
            <header className="moodle-confirm-dialog__header moodle-analysis-dialog__header">
              <div>
                <span>Validación académica</span>
                <h2 id="moodle-course-analysis-title">Analizando el curso y sus estudiantes</h2>
              </div>
              <strong className="moodle-analysis-dialog__status">En curso</strong>
            </header>
            <div className="moodle-confirm-dialog__body moodle-analysis-dialog__body">
              <p id="moodle-course-analysis-description">
                {selectedCourse?.name
                  ? `Se está validando «${selectedCourse.name}» mediante CorreoIntec.`
                  : 'Se está validando el curso seleccionado mediante CorreoIntec.'}
              </p>
              <div className="moodle-analysis-progress">
                <div className="moodle-analysis-progress__summary">
                  <strong>Etapa {resolutionStage + 1} de {COURSE_RESOLUTION_STAGES.length}</strong>
                  <span>{COURSE_RESOLUTION_PROGRESS[resolutionStage]}%</span>
                </div>
                <div
                  className="moodle-analysis-progress__track"
                  role="progressbar"
                  aria-label="Avance de la validación del curso"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={COURSE_RESOLUTION_PROGRESS[resolutionStage]}
                >
                  <span style={{ width: `${COURSE_RESOLUTION_PROGRESS[resolutionStage]}%` }} />
                </div>
              </div>
              <ol className="moodle-analysis-steps" aria-live="polite">
                {COURSE_RESOLUTION_STAGES.map((stage, index) => {
                  const status = index < resolutionStage
                    ? 'complete'
                    : index === resolutionStage
                      ? 'active'
                      : 'pending'
                  return (
                    <li key={stage} className={`moodle-analysis-step moodle-analysis-step--${status}`}>
                      <span className="moodle-analysis-step__number">{index + 1}</span>
                      <span>
                        <strong>{stage}</strong>
                        <small>
                          {status === 'complete'
                            ? 'Etapa procesada'
                            : status === 'active'
                              ? 'Procesando información...'
                              : 'Pendiente'}
                        </small>
                      </span>
                    </li>
                  )
                })}
              </ol>
              <p className="moodle-analysis-dialog__note">
                Mantenga esta subpantalla abierta hasta que finalice la validación.
              </p>
            </div>
          </section>
        </div>
      )}

      {confirmApply && preview && (
        <div className="moodle-confirm-overlay" role="presentation">
          <section className="moodle-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="moodle-grade-confirm-title">
            <header className="moodle-confirm-dialog__header">
              <div><span>Confirmación</span><h2 id="moodle-grade-confirm-title">Migrar notas desde Moodle</h2></div>
            </header>
            <div className="moodle-confirm-dialog__body">
              <p>
                {replaceExisting
                  ? `Se reemplazarán ${readyCount} componente(s), incluso cuando ya exista una nota en INTECBDD. La operación quedará auditada.`
                  : `Se actualizarán ${readyCount} componente(s) sin reemplazar cambios manuales existentes.`}
              </p>
              <dl className="moodle-confirm-dialog__details">
                <div><dt>Curso Moodle</dt><dd>{selectedCourse?.name ?? preview.course.name}</dd></div>
                <div><dt>Código académico</dt><dd>{preview.course.code}</dd></div>
                <div>
                  <dt>Períodos INTECBDD</dt>
                  <dd>{preview.periods.map((period) => period.name).join(' · ')}</dd>
                </div>
                <div><dt>Tipo de matrícula</dt><dd>{preview.period.type}</dd></div>
              </dl>
              {applying && (
                <div className="moodle-alert moodle-alert--warning" role="status" aria-live="polite">
                  Consultando las calificaciones de Moodle y guardando {readyCount} componente(s). No cierre esta pantalla.
                </div>
              )}
              {!applying && error && (
                <div className="moodle-alert moodle-alert--error" role="alert">
                  {error}
                </div>
              )}
              <div className="moodle-confirm-dialog__actions">
                <button type="button" className="moodle-button moodle-button--secondary" disabled={applying} onClick={() => setConfirmApply(false)}>Cancelar</button>
                <button type="button" className="moodle-button moodle-button--success" disabled={applying} onClick={() => void confirmSynchronization()}>{applying ? 'Migrando...' : 'Confirmar migración'}</button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
