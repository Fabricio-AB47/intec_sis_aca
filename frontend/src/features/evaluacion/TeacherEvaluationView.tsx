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

type TeacherRoleFlow = Exclude<TeacherEvaluationFlow, 'student'>

type TeacherEvaluationViewProps = {
  publicMode?: boolean
  displayName?: string
  defaultCedula?: string
  onBackToLogin?: () => void
}

const FLOW_COPY: Record<
  TeacherEvaluationFlow,
  { eyebrow: string; title: string; description: string; empty: string; action: string }
> = {
  student: {
    eyebrow: 'Estudiante',
    title: 'Evaluación al docente',
    description: 'Evalúa al docente de cada materia matriculada.',
    empty: 'No se encontraron materias con docente asignado para esta cédula.',
    action: 'Evaluar docente',
  },
  auto_docente: {
    eyebrow: 'Docente',
    title: 'Autoevaluación docente',
    description: 'Registra la autoevaluación de tus materias asignadas.',
    empty: 'No se encontraron materias asignadas para esta cédula.',
    action: 'Autoevaluar',
  },
  par_docente: {
    eyebrow: 'Docente',
    title: 'Evaluación par docente',
    description: 'Evalúa docentes pares vinculados a tus materias.',
    empty: 'No se encontraron docentes pares disponibles para esta cédula.',
    action: 'Evaluar par',
  },
}

function normalizeCedula(value: string) {
  return value.replace(/\D/g, '').slice(0, 13)
}

function isTeacherFlow(flow: TeacherEvaluationFlow | null): flow is TeacherRoleFlow {
  return flow === 'auto_docente' || flow === 'par_docente'
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
    .replace(/^\s*(?:\d+|[ivxlcdm]+)\s*[\).\-\u2013:]?\s*/iu, '')
    .trim()
}

function getScoreOptions(question: TeacherEvaluationQuestion) {
  const rawMin = Number(question.puntaje_min)
  const rawMax = Number(question.puntaje_max)
  const min = Number.isFinite(rawMin) && rawMin > 0 ? Math.max(1, Math.floor(rawMin)) : 1
  const max = Number.isFinite(rawMax) && rawMax >= min ? Math.min(10, Math.floor(rawMax)) : 10
  return Array.from({ length: max - min + 1 }, (_, index) => min + index)
}

function coursesForFlow(identity: TeacherEvaluationIdentityResponse | null, flow: TeacherEvaluationFlow | null) {
  if (!identity || !flow) return []
  if (flow === 'student') return identity.student_courses || []
  if (flow === 'auto_docente') return identity.auto_courses || []
  return identity.peer_courses || []
}

function flowCount(identity: TeacherEvaluationIdentityResponse | null, flow: TeacherEvaluationFlow) {
  return coursesForFlow(identity, flow).length
}

function courseTitle(course: TeacherEvaluationCourse) {
  return course.materia || `Materia ${course.codigo_materia}`
}

function coursePersonLabel(flow: TeacherEvaluationFlow | null, course: TeacherEvaluationCourse, identity: TeacherEvaluationIdentityResponse | null) {
  if (flow === 'auto_docente') return identity?.teacher?.docente || course.docente || 'Docente'
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

  async function activateFlow(nextFlow: TeacherEvaluationFlow, data = identity) {
    setError(null)
    setSuccess(null)
    setQuestionLoading(true)
    setSelectedCourse(null)
    setAnswers({})
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
      setError('Ingrese un número de cédula para buscar la evaluación.')
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

    try {
      const data = await fetchTeacherEvaluationIdentity(cleanCedula)
      const hasStudent = Boolean(data.student)
      const hasTeacher = Boolean(data.teacher)

      if (!hasStudent && !hasTeacher) {
        setError('No se encontró un estudiante o docente con esa cédula.')
        return
      }

      setIdentity(data)

      if (hasStudent && !hasTeacher) {
        await activateFlow('student', data)
        setShowCoursesModal(true)
        return
      }

      if (hasStudent && hasTeacher) {
        setSuccess('La cédula pertenece a estudiante y docente. Seleccione el tipo de evaluación que desea realizar.')
        setShowFlowModal(true)
        return
      }

      setSuccess('Docente identificado. Seleccione autoevaluación o evaluación par docente.')
      setShowFlowModal(true)
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
        : await saveTeacherEvaluation(payload)
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
    if (identity?.student) options.push('student')
    if (identity?.teacher) {
      options.push('auto_docente')
      options.push('par_docente')
    }
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
                <strong>{currentCourses.length} curso(s)</strong>
                <button type="button" className="teacher-evaluation__secondary" onClick={() => setShowCoursesModal(false)}>
                  Cerrar
                </button>
              </div>
            </header>

            <div className="teacher-evaluation__modal-body">
              {currentCourses.length > 0 ? (
                <div className="teacher-evaluation__course-grid">
                  {currentCourses.map((course) => {
                    const done = isEvaluated(course)
                    return (
                      <button
                        key={getCourseKey(course)}
                        type="button"
                        className={`teacher-evaluation__course-card ${done ? 'is-done' : ''}`}
                        onClick={() => openCourse(course)}
                        disabled={done}
                      >
                        <h3>{courseTitle(course)}</h3>
                        <strong>{coursePersonLabel(flow, course, identity)}</strong>
                        <p>{courseMeta(course)}</p>
                        <span className={`teacher-evaluation__badge ${done ? 'is-done' : ''}`}>
                          {done ? 'Evaluación registrada' : 'Pendiente de evaluación'}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="teacher-evaluation__empty">{currentCopy.empty}</div>
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
                          <option value="">Puntaje</option>
                          {getScoreOptions(question).map((score) => (
                            <option key={score} value={score}>
                              {score}
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
