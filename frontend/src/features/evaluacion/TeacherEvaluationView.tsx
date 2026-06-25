import { type FormEvent, useMemo, useState } from 'react'
import {
  fetchTeacherEvaluationIdentity,
  fetchTeacherEvaluationQuestions,
  saveTeacherEvaluation,
  saveTeacherRoleEvaluation,
} from '../../lib/api'
import type {
  TeacherEvaluationCourse,
  TeacherEvaluationFlow,
  TeacherEvaluationIdentityResponse,
  TeacherEvaluationQuestion,
} from '../../types/app'

type TeacherRoleFlow = Exclude<TeacherEvaluationFlow, 'student' | 'auto_estudiante'>

type TeacherEvaluationViewProps = {
  publicMode?: boolean
  displayName?: string
  defaultCedula?: string
  onBackToLogin?: () => void
}

type ScoreOption = {
  value: number
  label: string
}

const FLOW_COPY: Record<
  TeacherEvaluationFlow,
  { eyebrow: string; title: string; description: string; empty: string; action: string }
> = {
  student: {
    eyebrow: 'Estudiante',
    title: 'Evaluación al docente',
    description: 'Evalúa una sola vez cada materia activa del periodo, aunque esté relacionada con varias carreras.',
    empty: 'No se encontraron materias con docente asignado para esta cédula.',
    action: 'Evaluar docente',
  },
  auto_estudiante: {
    eyebrow: 'Estudiante',
    title: 'Autoevaluación estudiantil',
    description: 'Registra tu autoevaluación una sola vez por materia del periodo.',
    empty: 'No se encontraron materias disponibles para autoevaluación estudiantil.',
    action: 'Autoevaluar',
  },
  auto_docente: {
    eyebrow: 'Docente',
    title: 'Autoevaluación docente',
    description: 'Registra la autoevaluación una sola vez por materia activa del periodo.',
    empty: 'No se encontraron materias asignadas para esta cédula.',
    action: 'Autoevaluar',
  },
  par_docente: {
    eyebrow: 'Docente',
    title: 'Evaluación par docente',
    description: 'Evalúa una sola vez por materia del periodo, consolidando carreras relacionadas.',
    empty: 'No se encontraron docentes pares disponibles para esta cédula.',
    action: 'Evaluar par',
  },
  academico_docente: {
    eyebrow: 'Administrativo',
    title: 'Evaluación administrativa docente',
    description: 'Evalúa una sola vez por materia del periodo desde la autoridad activa registrada en USUARIO_SIS.',
    empty: 'No se encontraron docentes asignados para evaluación administrativa.',
    action: 'Evaluar docente',
  },
}

function normalizeCedula(value: string) {
  return value.replace(/\D/g, '').slice(0, 10)
}

function isTeacherFlow(flow: TeacherEvaluationFlow | null): flow is TeacherRoleFlow {
  return flow === 'auto_docente' || flow === 'par_docente' || flow === 'academico_docente'
}

function isEvaluated(course: TeacherEvaluationCourse) {
  return Boolean(course.evaluado || (course.respuestas_registradas ?? 0) > 0)
}

function getCourseKey(course: TeacherEvaluationCourse) {
  return (
    course.key ||
    [
      course.codigo_periodo,
      course.codigo_materia,
      course.codigo_docente_eval,
      course.cod_anio_basica ?? '',
      course.paralelo ?? '',
      course.jornada ?? course.cod_jornada ?? '',
    ].join('|')
  )
}

function getQuestionCategory(question: TeacherEvaluationQuestion) {
  return (
    question.dimension_global_nombre ||
    question.dimension_nombre ||
    question.nombre_dimension ||
    question.categoria ||
    question.categoria_pregunta ||
    question.tipo_label ||
    'Evaluación'
  )
}

function getQuestionText(question: TeacherEvaluationQuestion) {
  return (question.detalle_preg || '')
    .replace(
      /^\s*(?:(?:pregunta|item|ítem|indicador)\s*)?(?:(?:\d+(?:\.\d+)*)\s*(?:[\).\-\u2013\u2014:]|\s)+|(?:[ivxlcdm]+)\s*[\).\-\u2013\u2014:]+)/iu,
      '',
    )
    .trim()
}

function getScoreOptions(question: TeacherEvaluationQuestion): ScoreOption[] {
  if (question.escala_likert?.length) {
    return question.escala_likert
      .map((option) => {
        const value = Number(option.valor)
        const label = option.texto || `${option.valor} - ${option.etiqueta}`
        return Number.isFinite(value) ? { value, label } : null
      })
      .filter((option): option is ScoreOption => Boolean(option))
  }

  const rawMin = Number(question.puntaje_min)
  const rawMax = Number(question.puntaje_max)
  const min = Number.isFinite(rawMin) && rawMin > 0 ? Math.max(1, Math.floor(rawMin)) : 1
  const max = Number.isFinite(rawMax) && rawMax >= min ? Math.min(10, Math.floor(rawMax)) : 5
  const likertLabels: Record<number, string> = {
    1: 'Nunca',
    2: 'Rara vez',
    3: 'A veces',
    4: 'Casi siempre',
    5: 'Siempre',
  }
  return Array.from({ length: max - min + 1 }, (_, index) => {
    const value = min + index
    const label = min === 1 && max === 5 ? `${value} - ${likertLabels[value] || value}` : String(value)
    return { value, label }
  })
}

function coursesForFlow(identity: TeacherEvaluationIdentityResponse | null, flow: TeacherEvaluationFlow | null) {
  if (!identity || !flow) return []
  if (flow === 'student') return identity.student_courses || []
  if (flow === 'auto_estudiante') return identity.auto_student_courses || []
  if (flow === 'auto_docente') return identity.auto_courses || []
  if (flow === 'par_docente') return identity.peer_courses || []
  return identity.authority_courses || []
}

function flowCount(identity: TeacherEvaluationIdentityResponse | null, flow: TeacherEvaluationFlow) {
  return coursesForFlow(identity, flow).length
}

function courseTitle(course: TeacherEvaluationCourse) {
  return course.materia || `Materia ${course.codigo_materia}`
}

function coursePersonLabel(flow: TeacherEvaluationFlow | null, course: TeacherEvaluationCourse, identity: TeacherEvaluationIdentityResponse | null) {
  if (flow === 'auto_docente') return identity?.teacher?.docente || course.docente || 'Docente'
  if (flow === 'auto_estudiante') return identity?.student?.estudiante || 'Estudiante'
  if (flow === 'academico_docente') return course.docente || 'Docente'
  return course.docente || 'Docente por asignar'
}

function courseMeta(course: TeacherEvaluationCourse) {
  const pieces = [
    course.detalle_periodo,
    course.carrera,
    course.paralelo ? `Paralelo ${course.paralelo}` : null,
  ].filter(Boolean)
  return pieces.join(' · ')
}

export function TeacherEvaluationView({ publicMode = false, displayName, defaultCedula, onBackToLogin }: TeacherEvaluationViewProps) {
  void publicMode
  void displayName
  void onBackToLogin

  const [cedula, setCedula] = useState(defaultCedula ? normalizeCedula(defaultCedula) : '')
  const [identity, setIdentity] = useState<TeacherEvaluationIdentityResponse | null>(null)
  const [flow, setFlow] = useState<TeacherEvaluationFlow | null>(null)
  const [questions, setQuestions] = useState<TeacherEvaluationQuestion[]>([])
  const [selectedCourse, setSelectedCourse] = useState<TeacherEvaluationCourse | null>(null)
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [showFlowModal, setShowFlowModal] = useState(false)
  const [showCoursesModal, setShowCoursesModal] = useState(false)
  const [detailCourse, setDetailCourse] = useState<TeacherEvaluationCourse | null>(null)
  const [coursePeriodFilter, setCoursePeriodFilter] = useState('')
  const [courseTeacherFilter, setCourseTeacherFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [questionLoading, setQuestionLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const orderedQuestions = useMemo(
    () =>
      [...questions].sort((a, b) => {
        const orderA = Number.isFinite(Number(a.orden)) ? Number(a.orden) : Number(a.no_pregunta)
        const orderB = Number.isFinite(Number(b.orden)) ? Number(b.orden) : Number(b.no_pregunta)
        return orderA - orderB || a.id_pregunta - b.id_pregunta
      }),
    [questions],
  )

  const groupedQuestions = useMemo(() => {
    const map = new Map<string, TeacherEvaluationQuestion[]>()
    orderedQuestions.forEach((question) => {
      const category = getQuestionCategory(question)
      const items = map.get(category) || []
      items.push(question)
      map.set(category, items)
    })
    return Array.from(map.entries()).map(([category, items]) => ({ category, items }))
  }, [orderedQuestions])

  const currentCourses = useMemo(() => coursesForFlow(identity, flow), [identity, flow])
  const currentCopy = flow ? FLOW_COPY[flow] : null
  const answeredCount = orderedQuestions.filter((question) => answers[question.id_pregunta]).length
  const scoreLegend = useMemo(
    () => (orderedQuestions[0] ? getScoreOptions(orderedQuestions[0]) : []),
    [orderedQuestions],
  )
  const coursePeriodOptions = useMemo(() => {
    const map = new Map<string, string>()
    currentCourses.forEach((course) => {
      const value = String(course.codigo_periodo || '')
      if (value) map.set(value, course.detalle_periodo || value)
    })
    return Array.from(map.entries()).map(([value, label]) => ({ value, label }))
  }, [currentCourses])
  const courseTeacherOptions = useMemo(() => {
    const map = new Map<string, string>()
    currentCourses.forEach((course) => {
      const value = String(course.codigo_docente_eval || '')
      if (value) map.set(value, course.docente || `Docente ${value}`)
    })
    return Array.from(map.entries()).map(([value, label]) => ({ value, label }))
  }, [currentCourses])
  const filteredCourses = useMemo(
    () =>
      currentCourses.filter((course) => {
        const periodMatches = !coursePeriodFilter || String(course.codigo_periodo || '') === coursePeriodFilter
        const teacherMatches = !courseTeacherFilter || String(course.codigo_docente_eval || '') === courseTeacherFilter
        return periodMatches && teacherMatches
      }),
    [coursePeriodFilter, courseTeacherFilter, currentCourses],
  )

  async function activateFlow(nextFlow: TeacherEvaluationFlow, data = identity) {
    setError(null)
    setSuccess(null)
    setQuestionLoading(true)
    setSelectedCourse(null)
    setAnswers({})
    setCoursePeriodFilter('')
    setCourseTeacherFilter('')
    try {
      const questionResponse = await fetchTeacherEvaluationQuestions(nextFlow)
      setQuestions(questionResponse.items || [])
      setFlow(nextFlow)
      const totalCourses = coursesForFlow(data, nextFlow).length
      if (totalCourses === 0) {
        setSuccess(null)
        setError(FLOW_COPY[nextFlow].empty)
      } else if ((questionResponse.items || []).length === 0) {
        setError('No existen preguntas activas para este tipo de evaluación.')
      } else {
        setSuccess(`${FLOW_COPY[nextFlow].title}: ${totalCourses} materia(s) disponible(s).`)
      }
    } catch (err) {
      setFlow(null)
      setQuestions([])
      setError(err instanceof Error ? err.message : 'No se pudo cargar el instrumento de evaluación.')
    } finally {
      setQuestionLoading(false)
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanCedula = normalizeCedula(cedula)
    if (!cleanCedula) {
      setError('Ingrese su número de cédula para buscar la evaluación.')
      return
    }
    if (cleanCedula.length < 10) {
      setError('Ingrese un número de cédula válido de 10 dígitos.')
      return
    }

    setCedula(cleanCedula)
    setLoading(true)
    setError(null)
    setSuccess(null)
    setIdentity(null)
    setFlow(null)
    setQuestions([])
    setSelectedCourse(null)
    setAnswers({})
    setShowFlowModal(false)
    setShowCoursesModal(false)
    setDetailCourse(null)
    setCoursePeriodFilter('')
    setCourseTeacherFilter('')

    try {
      const data = await fetchTeacherEvaluationIdentity(cleanCedula)
      const hasStudent = Boolean(data.student)
      const hasTeacher = Boolean(data.teacher)
      const hasAuthority = Boolean(data.authority)

      if (!hasStudent && !hasTeacher && !hasAuthority) {
        setError('No se encontró un estudiante, docente o usuario académico activo con esa cédula.')
        return
      }

      setIdentity(data)

      const availableOptions: TeacherEvaluationFlow[] = []
      if (hasStudent) {
        availableOptions.push('student', 'auto_estudiante')
      }
      if (hasTeacher) {
        availableOptions.push('auto_docente', 'par_docente')
      }
      if (hasAuthority) {
        availableOptions.push('academico_docente')
      }

      if (availableOptions.length === 1) {
        await activateFlow(availableOptions[0], data)
        setShowCoursesModal(true)
        return
      }

      if (availableOptions.length > 1) {
        setSuccess('Seleccione el tipo de evaluación que desea realizar.')
        setShowFlowModal(true)
        return
      }

      setError('No hay procesos de evaluación disponibles para esta cédula.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar la evaluación docente.')
    } finally {
      setLoading(false)
    }
  }

  function openCourse(course: TeacherEvaluationCourse) {
    if (!flow) return
    if (isEvaluated(course)) {
      setError('Esta evaluación ya fue registrada para la materia seleccionada.')
      return
    }
    if (flow === 'student' && Number(course.codigo_docente_eval || 0) <= 0) {
      setError('Esta materia tiene nota, pero no tiene docente asignado para registrar la evaluación.')
      return
    }
    if (orderedQuestions.length === 0) {
      setError('No existen preguntas activas para este tipo de evaluación.')
      return
    }
    setSelectedCourse(course)
    setShowCoursesModal(false)
    setAnswers({})
    setError(null)
  }

  async function handleFlowSelection(nextFlow: TeacherEvaluationFlow) {
    await activateFlow(nextFlow)
    setShowFlowModal(false)
    setShowCoursesModal(true)
  }

  function closeEvaluationModal() {
    setSelectedCourse(null)
    setAnswers({})
  }

  function openCourseDetail(course: TeacherEvaluationCourse) {
    setDetailCourse(course)
  }

  async function handleSubmitEvaluation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedCourse || !flow) return

    const missing = orderedQuestions.filter((question) => !answers[question.id_pregunta])
    if (missing.length > 0) {
      setError(`Complete todas las preguntas antes de enviar. Faltan ${missing.length}.`)
      return
    }

    setSaving(true)
    setError(null)
    setSuccess(null)

    const payload = {
      cedula: normalizeCedula(cedula),
      codigo_periodo: Number(selectedCourse.codigo_periodo),
      codigo_materia: Number(selectedCourse.codigo_materia),
      codigo_docente_eval: Number(selectedCourse.codigo_docente_eval),
      paralelo: selectedCourse.paralelo || '',
      jornada:
        selectedCourse.jornada ||
        (selectedCourse.cod_jornada === null || selectedCourse.cod_jornada === undefined
          ? null
          : String(selectedCourse.cod_jornada)),
      answers: orderedQuestions.map((question) => ({
        id_pregunta: Number(question.id_pregunta),
        no_pregunta: Number(question.no_pregunta),
        tipo_preg: Number(question.tipo_preg || question.id_dimension || 0),
        detalle_preg: question.detalle_preg,
        puntaje: Number(answers[question.id_pregunta]),
      })),
    }

    try {
      const response = isTeacherFlow(flow)
        ? await saveTeacherRoleEvaluation({ ...payload, flow })
        : await saveTeacherEvaluation({ ...payload, flow })
      const refreshed = await fetchTeacherEvaluationIdentity(normalizeCedula(cedula))
      setIdentity(refreshed)
      setSelectedCourse(null)
      setAnswers({})
      setShowCoursesModal(true)
      setSuccess(response.message || 'Evaluación registrada correctamente.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar la evaluación.')
    } finally {
      setSaving(false)
    }
  }

  const roleOptions = useMemo(() => {
    const options: TeacherEvaluationFlow[] = []
    if (identity?.student) {
      options.push('student')
      options.push('auto_estudiante')
    }
    if (identity?.teacher) {
      options.push('auto_docente')
      options.push('par_docente')
    }
    if (identity?.authority) options.push('academico_docente')
    return options
  }, [identity])

  return (
    <main className="teacher-evaluation teacher-evaluation--compact">
      <section className="teacher-evaluation__hero teacher-evaluation__hero--compact">
        <div>
          <p className="teacher-evaluation__eyebrow">Evaluación docente</p>
          <h1>Evaluación docente</h1>
          <p>Ingrese su número de cédula para realizar la evaluación docente.</p>
        </div>
      </section>

      <section className="teacher-evaluation__panel teacher-evaluation__search-panel">
        <form onSubmit={handleSearch}>
          <label className="teacher-evaluation__label" htmlFor="teacher-evaluation-cedula">
            Ingrese su número de cédula para realizar la evaluación docente
          </label>
          <div className="teacher-evaluation__lookup-row">
            <input
              id="teacher-evaluation-cedula"
              value={cedula}
              onChange={(event) => setCedula(normalizeCedula(event.target.value))}
              placeholder="Ej. 1726240565"
              inputMode="numeric"
              autoComplete="off"
              maxLength={10}
            />
            <button type="submit" className="teacher-evaluation__primary" disabled={loading || questionLoading}>
              {loading ? 'Buscando...' : 'Buscar evaluación'}
            </button>
          </div>
        </form>

        {error ? <div className="teacher-evaluation__message teacher-evaluation__message--error">{error}</div> : null}
        {success ? <div className="teacher-evaluation__message teacher-evaluation__message--success">{success}</div> : null}
      </section>

      {identity ? (
        <section className="teacher-evaluation__panel teacher-evaluation__panel--compact teacher-evaluation__identity-panel">
          <div className="teacher-evaluation__profile-grid">
            {identity.student ? (
              <>
                <div className="teacher-evaluation__profile-card">
                  <span>Estudiante</span>
                  <strong>{identity.student.estudiante}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Cédula</span>
                  <strong>{identity.student.cedula}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Correo INTEC</span>
                  <strong>{identity.student.correo_intec || '-'}</strong>
                </div>
              </>
            ) : null}

            {identity.teacher ? (
              <>
                <div className="teacher-evaluation__profile-card">
                  <span>Docente</span>
                  <strong>{identity.teacher.docente}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Cédula</span>
                  <strong>{identity.teacher.cedula}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Usuario / correo</span>
                  <strong>{identity.teacher.usuario || identity.teacher.correo_intec || '-'}</strong>
                </div>
              </>
            ) : null}

            {identity.authority ? (
              <>
                <div className="teacher-evaluation__profile-card">
                  <span>Administrativo</span>
                  <strong>{identity.authority.autoridad || identity.authority.nombres}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Usuario</span>
                  <strong>{identity.authority.login || '-'}</strong>
                </div>
                <div className="teacher-evaluation__profile-card">
                  <span>Coordinación</span>
                  <strong>{identity.authority.coordcarrera || '-'}</strong>
                </div>
              </>
            ) : null}
          </div>

          <div className="teacher-evaluation__summary-actions">
            <span className="teacher-evaluation__summary-pill">
              {roleOptions.length} proceso(s) · {roleOptions.reduce((total, option) => total + flowCount(identity, option), 0)} materia(s)
            </span>
            {roleOptions.length > 1 ? (
              <button
                type="button"
                className="teacher-evaluation__secondary"
                onClick={() => setShowFlowModal(true)}
                disabled={questionLoading}
              >
                Seleccionar evaluación
              </button>
            ) : null}
            {flow && currentCopy ? (
              <button
                type="button"
                className="teacher-evaluation__primary"
                onClick={() => setShowCoursesModal(true)}
                disabled={questionLoading}
              >
                Ver {currentCourses.length} materia(s)
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {showFlowModal && identity ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section
            className="teacher-evaluation__modal teacher-evaluation__modal--selector"
            role="dialog"
            aria-modal="true"
            aria-labelledby="teacher-evaluation-flow-title"
          >
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Tipo de evaluación</p>
                <h2 id="teacher-evaluation-flow-title">Seleccione el proceso</h2>
                <p>Elija la evaluación que corresponde a la cédula ingresada.</p>
              </div>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => setShowFlowModal(false)}>
                Cerrar
              </button>
            </header>

            <div className="teacher-evaluation__modal-body">
              {roleOptions.length > 0 ? (
                <div className="teacher-evaluation__role-grid">
                  {roleOptions.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={`teacher-evaluation__mode-card ${flow === option ? 'is-active' : ''}`}
                      onClick={() => void handleFlowSelection(option)}
                      disabled={questionLoading}
                    >
                      <span>{FLOW_COPY[option].eyebrow}</span>
                      <h3>{FLOW_COPY[option].title}</h3>
                      <p>{FLOW_COPY[option].description}</p>
                      <strong>{flowCount(identity, option)} materia(s)</strong>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="teacher-evaluation__empty">No hay evaluaciones disponibles para esta cédula.</div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {showCoursesModal && flow && currentCopy ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section
            className="teacher-evaluation__modal teacher-evaluation__modal--selector"
            role="dialog"
            aria-modal="true"
            aria-labelledby="teacher-evaluation-courses-title"
          >
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">{currentCopy.eyebrow}</p>
                <h2 id="teacher-evaluation-courses-title">{currentCopy.title}</h2>
                <p>{currentCopy.description}</p>
              </div>
              <div className="teacher-evaluation__modal-header-actions">
                <strong>{filteredCourses.length}/{currentCourses.length} curso(s)</strong>
                <button type="button" className="teacher-evaluation__secondary" onClick={() => setShowCoursesModal(false)}>
                  Cerrar
                </button>
              </div>
            </header>

            <div className="teacher-evaluation__modal-body">
              {currentCourses.length > 0 ? (
                <>
                  <div className="teacher-evaluation__course-filters">
                    <select value={coursePeriodFilter} onChange={(event) => setCoursePeriodFilter(event.target.value)}>
                      <option value="">Todos los periodos</option>
                      {coursePeriodOptions.map((period) => (
                        <option key={period.value} value={period.value}>
                          {period.label}
                        </option>
                      ))}
                    </select>
                    {flow === 'academico_docente' ? (
                      <select value={courseTeacherFilter} onChange={(event) => setCourseTeacherFilter(event.target.value)}>
                        <option value="">Todos los docentes</option>
                        {courseTeacherOptions.map((teacher) => (
                          <option key={teacher.value} value={teacher.value}>
                            {teacher.label}
                          </option>
                        ))}
                      </select>
                    ) : null}
                  </div>

                  <div className="teacher-evaluation__course-grid">
                    {filteredCourses.map((course) => {
                      const done = isEvaluated(course)
                      return (
                        <article
                          key={getCourseKey(course)}
                          className={`teacher-evaluation__course-card ${done ? 'is-done' : ''}`}
                        >
                          <div className="teacher-evaluation__course-card-head">
                            <h3>{courseTitle(course)}</h3>
                            <button
                              type="button"
                              className="teacher-evaluation__icon-button"
                              onClick={() => openCourseDetail(course)}
                              aria-label="Ver carreras vinculadas"
                              title="Ver carreras vinculadas"
                            >
                              i
                            </button>
                          </div>
                          <strong>{coursePersonLabel(flow, course, identity)}</strong>
                          <p>{courseMeta(course)}</p>
                          <div className="teacher-evaluation__course-card-actions">
                            <span className={`teacher-evaluation__badge ${done ? 'is-done' : ''}`}>
                              {done ? 'Evaluación registrada' : 'Pendiente de evaluación'}
                            </span>
                            <button
                              type="button"
                              className="teacher-evaluation__course-action"
                              onClick={() => openCourse(course)}
                              disabled={done}
                            >
                              {done ? 'Registrada' : 'Evaluar materia'}
                            </button>
                          </div>
                        </article>
                      )
                    })}
                  </div>

                  {filteredCourses.length === 0 ? (
                    <div className="teacher-evaluation__empty">No hay materias para los filtros seleccionados.</div>
                  ) : null}
                </>
              ) : (
                <div className="teacher-evaluation__empty">{currentCopy.empty}</div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {detailCourse ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section
            className="teacher-evaluation__modal teacher-evaluation__modal--selector"
            role="dialog"
            aria-modal="true"
            aria-labelledby="teacher-evaluation-detail-title"
          >
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Materia consolidada</p>
                <h2 id="teacher-evaluation-detail-title">{courseTitle(detailCourse)}</h2>
                <p>
                  Periodo {detailCourse.detalle_periodo || detailCourse.codigo_periodo} · Código materia {detailCourse.codigo_materia}
                </p>
                {detailCourse.codigo_materia_interno ? (
                  <p>Código único académico: {detailCourse.codigo_materia_interno}</p>
                ) : null}
              </div>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => setDetailCourse(null)}>
                Cerrar
              </button>
            </header>

            <div className="teacher-evaluation__modal-body">
              {(detailCourse.componentes_relacionados || []).length > 0 ? (
                <div className="teacher-evaluation__linked-list">
                  {(detailCourse.componentes_relacionados || []).map((item, index) => (
                    <article
                      className="teacher-evaluation__linked-item"
                      key={`${item.cod_anio_basica || index}-${item.paralelo || ''}-${item.cedula_docente || ''}`}
                    >
                      <div className="teacher-evaluation__linked-career">
                        <span>Carrera</span>
                        <strong>{item.carrera || '-'}</strong>
                      </div>
                      <div>
                        <span>Materia</span>
                        <strong>{item.materia || detailCourse.materia || '-'}</strong>
                      </div>
                      <div>
                        <span>Código único</span>
                        <strong>{item.codigo_materia_interno || detailCourse.codigo_materia_interno || '-'}</strong>
                      </div>
                      <div>
                        <span>Paralelo</span>
                        <strong>{item.paralelo || '-'}</strong>
                      </div>
                      <div className="teacher-evaluation__linked-teacher">
                        <span>Docente</span>
                        <strong>{item.docente || '-'}</strong>
                      </div>
                      <div>
                        <span>Jornada</span>
                        <strong>{item.jornada || '-'}</strong>
                      </div>
                      <div>
                        <span>ID vinculado</span>
                        <strong>{item.codigo_materia || '-'}</strong>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="teacher-evaluation__empty">No hay carreras vinculadas adicionales para esta materia.</div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {selectedCourse && flow ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section
            className="teacher-evaluation__modal teacher-evaluation__modal--questionnaire"
            role="dialog"
            aria-modal="true"
            aria-labelledby="teacher-evaluation-questionnaire-title"
          >
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">{FLOW_COPY[flow].title}</p>
                <h2 id="teacher-evaluation-questionnaire-title">{courseTitle(selectedCourse)}</h2>
                <p>{coursePersonLabel(flow, selectedCourse, identity)}</p>
                <p>{courseMeta(selectedCourse)}</p>
              </div>
              <div className="teacher-evaluation__modal-header-actions">
                <strong>
                  {answeredCount}/{orderedQuestions.length}
                </strong>
                <button type="button" className="teacher-evaluation__secondary" onClick={closeEvaluationModal} disabled={saving}>
                  Cerrar
                </button>
              </div>
            </header>

            <form onSubmit={handleSubmitEvaluation}>
              <div className="teacher-evaluation__modal-body">
                {scoreLegend.length ? (
                  <section className="teacher-evaluation__scale" aria-label="Escala de calificación">
                    <div>
                      <p className="teacher-evaluation__scale-label">Escala de calificación 360</p>
                      <strong>Seleccione una opción en cada pregunta.</strong>
                    </div>
                    <div className="teacher-evaluation__scale-options">
                      {scoreLegend.map((score) => (
                        <span key={score.value}>{score.label}</span>
                      ))}
                    </div>
                  </section>
                ) : null}

                {groupedQuestions.map((group) => (
                  <section className="teacher-evaluation__question-section" key={group.category}>
                    <h3>{group.category}</h3>
                    {group.items.map((question) => (
                      <div className="teacher-evaluation__question-row" key={question.id_pregunta}>
                        <p>{getQuestionText(question)}</p>
                        <select
                          value={answers[question.id_pregunta] ?? ''}
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [question.id_pregunta]: Number(event.target.value),
                            }))
                          }
                          required
                        >
                          <option value="">Seleccione escala</option>
                          {getScoreOptions(question).map((score) => (
                            <option key={score.value} value={score.value}>
                              {score.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </section>
                ))}
              </div>

              <footer className="teacher-evaluation__modal-actions">
                <button
                  type="button"
                  className="teacher-evaluation__ghost"
                  onClick={closeEvaluationModal}
                  disabled={saving}
                >
                  Cerrar
                </button>
                <button type="submit" className="teacher-evaluation__primary" disabled={saving}>
                  {saving ? 'Guardando...' : 'Enviar evaluación'}
                </button>
              </footer>
            </form>
          </section>
        </div>
      ) : null}
    </main>
  )
}
