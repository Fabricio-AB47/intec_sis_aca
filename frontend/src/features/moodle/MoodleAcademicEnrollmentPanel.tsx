import { useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  applyMoodleAcademicEnrollment,
  fetchMoodleAcademicEnrollmentCatalog,
  fetchMoodleCourses,
  previewMoodleAcademicEnrollment,
} from '../../lib/api'
import type {
  MoodleAcademicEnrollmentApplyResponse,
  MoodleAcademicEnrollmentCatalogResponse,
  MoodleAcademicEnrollmentPreviewResponse,
  MoodleCourse,
  MoodleCoursesResponse,
} from '../../types/app'

type AcademicDetailView =
  | 'ready'
  | 'existing'
  | 'blocked'
  | 'ignored'
  | 'first'
  | 'second'
  | 'third'
  | 'teachers'

const ACADEMIC_DETAIL_COPY: Record<AcademicDetailView, {
  eyebrow: string
  title: string
  empty: string
}> = {
  ready: {
    eyebrow: 'Validación de matrícula',
    title: 'Estudiantes por matricular',
    empty: 'No existen estudiantes listos para matricular.',
  },
  existing: {
    eyebrow: 'Control de duplicidad',
    title: 'Estudiantes ya matriculados',
    empty: 'No se encontraron matrículas existentes para esta selección.',
  },
  blocked: {
    eyebrow: 'Validación académica',
    title: 'Estudiantes bloqueados',
    empty: 'No existen estudiantes bloqueados.',
  },
  ignored: {
    eyebrow: 'Cuentas omitidas',
    title: 'Estudiantes ignorados',
    empty: 'No existen cuentas Moodle o registros académicos omitidos.',
  },
  first: {
    eyebrow: 'Número de matrícula',
    title: 'Primera matrícula',
    empty: 'No existen primeras matrículas en esta selección.',
  },
  second: {
    eyebrow: 'Número de matrícula',
    title: 'Segunda matrícula',
    empty: 'No existen segundas matrículas en esta selección.',
  },
  third: {
    eyebrow: 'Número de matrícula',
    title: 'Tercera matrícula',
    empty: 'No existen terceras matrículas en esta selección.',
  },
  teachers: {
    eyebrow: 'Asignación docente',
    title: 'Docentes validados',
    empty: 'No existen docentes validados para esta selección.',
  },
}

const IGNORED_STUDENT_STATUSES = new Set(['IGNORADO_MOODLE', 'IGNORADO_ACADEMICO'])

function matchesStudentDetail(
  student: MoodleAcademicEnrollmentPreviewResponse['courses'][number]['students'][number],
  detail: Exclude<AcademicDetailView, 'teachers'>,
): boolean {
  if (detail === 'ready') return student.status === 'LISTO'
  if (detail === 'existing') return student.status === 'EXISTENTE'
  if (detail === 'ignored') return IGNORED_STUDENT_STATUSES.has(student.status)
  if (detail === 'blocked') {
    return !['LISTO', 'EXISTENTE', ...IGNORED_STUDENT_STATUSES].includes(student.status)
  }
  const attempt = detail === 'first' ? 1 : detail === 'second' ? 2 : 3
  return student.status === 'LISTO' && student.enrollment_number === attempt
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudo completar la matrícula desde Moodle.'
}

function statusLabel(status: string): string {
  return {
    LISTO: 'Listo',
    EXISTENTE: 'Existente',
    COINCIDE: 'Validado',
    IGNORADO_MOODLE: 'Ignorado',
    IGNORADO_ACADEMICO: 'Inactivo omitido',
    NO_ENCONTRADO: 'No encontrado',
    CORREO_AMBIGUO: 'Correo ambiguo',
    CEDULA_AMBIGUA: 'Cédula ambigua',
    IDENTIDAD_CONFLICTIVA: 'Identidad conflictiva',
    INACTIVO_MOODLE: 'Inactivo en Moodle',
    INACTIVO_ACADEMICO: 'Inactivo en INTECBDD',
    MATERIA_NO_ENCONTRADA: 'Materia no encontrada',
    MATERIA_AMBIGUA: 'Materia ambigua',
    CARRERA_REQUERIDA: 'Carrera requerida',
    DUPLICADO_SELECCION: 'Duplicado en selección',
    PARALELO_INVALIDO: 'Paralelo inválido',
    PARALELO_CONFLICTIVO: 'Otro paralelo',
    PRERREQUISITO_PENDIENTE: 'Prerrequisito pendiente',
    LIMITE_MATRICULA: 'Límite de matrícula',
    BLOQUEADO_ACADEMICO: 'Bloqueado',
  }[status] ?? status
}

function statusClass(status: string): string {
  if (['LISTO', 'COINCIDE', 'MATRICULADO'].includes(status)) return 'is-success'
  if (['EXISTENTE', 'IGNORADO_MOODLE', 'IGNORADO_ACADEMICO'].includes(status)) return 'is-warning'
  return 'is-error'
}

function AcademicSummaryButton({
  label,
  value,
  onClick,
}: {
  label: string
  value: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="moodle-academic-summary__button"
      aria-haspopup="dialog"
      aria-label={`Ver detalle de ${label.toLocaleLowerCase('es')}: ${value}`}
      onClick={onClick}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <small>Ver detalle</small>
    </button>
  )
}

function courseCareerOptions(
  course: MoodleAcademicEnrollmentPreviewResponse['courses'][number],
) {
  return Array.from(new Map(
    course.subject_candidates.map((candidate) => [candidate.career_code, candidate]),
  ).values())
}

export function MoodleAcademicEnrollmentPanel() {
  const [catalog, setCatalog] = useState<MoodleAcademicEnrollmentCatalogResponse | null>(null)
  const [courses, setCourses] = useState<MoodleCoursesResponse | null>(null)
  const [selectedCourses, setSelectedCourses] = useState<MoodleCourse[]>([])
  const [search, setSearch] = useState('')
  const [periodCode, setPeriodCode] = useState('')
  const [jornadaCode, setJornadaCode] = useState('')
  const [preview, setPreview] = useState<MoodleAcademicEnrollmentPreviewResponse | null>(null)
  const [careers, setCareers] = useState<Record<number, number>>({})
  const [principals, setPrincipals] = useState<Record<number, number>>({})
  const [result, setResult] = useState<MoodleAcademicEnrollmentApplyResponse | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [coursesLoading, setCoursesLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [detailView, setDetailView] = useState<AcademicDetailView | null>(null)
  const [error, setError] = useState('')

  const selectedIds = useMemo(
    () => new Set(selectedCourses.map((course) => course.id)),
    [selectedCourses],
  )

  const detailStudents = useMemo(() => {
    if (!preview || !detailView || detailView === 'teachers') return []
    return preview.courses.flatMap((course) => course.students
      .filter((student) => matchesStudentDetail(student, detailView))
      .map((student) => ({ course, student })))
      .sort((left, right) => (
        left.course.course.name.localeCompare(right.course.course.name, 'es')
        || left.student.moodle_name.localeCompare(right.student.moodle_name, 'es')
      ))
  }, [detailView, preview])

  const detailTeachers = useMemo(() => {
    if (!preview || detailView !== 'teachers') return []
    return preview.courses.flatMap((course) => course.teachers
      .filter((teacher) => teacher.status === 'COINCIDE')
      .map((teacher) => ({ course, teacher })))
      .sort((left, right) => (
        left.course.course.name.localeCompare(right.course.course.name, 'es')
        || left.teacher.moodle_name.localeCompare(right.teacher.moodle_name, 'es')
      ))
  }, [detailView, preview])

  const resetReview = () => {
    setPreview(null)
    setPrincipals({})
    setResult(null)
    setConfirmOpen(false)
    setDetailView(null)
    setError('')
  }

  useEffect(() => {
    if (!detailView) return undefined
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDetailView(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [detailView])

  const loadCatalog = async () => {
    setCatalogLoading(true)
    setError('')
    try {
      const response = await fetchMoodleAcademicEnrollmentCatalog()
      setCatalog(response)
      setJornadaCode((current) => {
        if (current) return current
        const nocturna = response.jornadas.find((item) => item.name.toLocaleLowerCase('es').includes('noct'))
        return String(nocturna?.code ?? response.jornadas[0]?.code ?? '')
      })
    } catch (requestError) {
      setCatalog(null)
      setError(errorMessage(requestError))
    } finally {
      setCatalogLoading(false)
    }
  }

  const loadCourses = async (refresh = false) => {
    setCoursesLoading(true)
    setError('')
    try {
      setCourses(await fetchMoodleCourses({
        page: 1,
        pageSize: 100,
        search,
        visibility: 'all',
        refresh,
      }))
    } catch (requestError) {
      setCourses(null)
      setError(errorMessage(requestError))
    } finally {
      setCoursesLoading(false)
    }
  }

  useEffect(() => {
    void loadCatalog()
    void loadCourses()
    // La carga inicial conserva después los filtros y la selección local del operador.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void loadCourses()
  }

  const toggleCourse = (course: MoodleCourse) => {
    const maximum = catalog?.rules.max_courses ?? 25
    setSelectedCourses((current) => current.some((item) => item.id === course.id)
      ? current.filter((item) => item.id !== course.id)
      : current.length < maximum ? [...current, course] : current)
    resetReview()
  }

  const selectVisible = () => {
    const maximum = catalog?.rules.max_courses ?? 25
    setSelectedCourses((current) => {
      const indexed = new Map(current.map((course) => [course.id, course]))
      for (const course of courses?.items ?? []) indexed.set(course.id, course)
      return [...indexed.values()].slice(0, maximum)
    })
    resetReview()
  }

  const selectedCareerPayload = (): Record<number, number> => Object.fromEntries(
    selectedCourses
      .map((course) => [course.id, Number(careers[course.id])] as const)
      .filter((entry) => Number.isInteger(entry[1]) && entry[1] > 0),
  )

  const reviewEnrollment = async () => {
    const parsedPeriod = Number(periodCode)
    const parsedJornada = Number(jornadaCode)
    if (selectedCourses.length === 0) {
      setError('Seleccione al menos un curso Moodle.')
      return
    }
    if (!Number.isInteger(parsedPeriod) || parsedPeriod <= 0) {
      setError('Seleccione el período académico de destino.')
      return
    }
    if (!Number.isInteger(parsedJornada) || parsedJornada <= 0) {
      setError('Seleccione la jornada para la matrícula.')
      return
    }

    setPreviewLoading(true)
    setError('')
    setResult(null)
    setDetailView(null)
    try {
      const response = await previewMoodleAcademicEnrollment({
        course_ids: selectedCourses.map((course) => course.id),
        period_code: parsedPeriod,
        jornada_code: parsedJornada,
        career_by_course: selectedCareerPayload(),
      }, true)
      setPreview(response)
      setCareers((current) => {
        const next: Record<number, number> = {}
        for (const course of response.courses) {
          const available = new Set(course.subject_candidates.map((candidate) => candidate.career_code))
          const selected = course.selected_career_code ?? current[course.course.id]
          if (selected && available.has(selected)) next[course.course.id] = selected
        }
        return next
      })
      setPrincipals(Object.fromEntries(
        response.courses
          .filter((course) => course.suggested_principal_teacher_code)
          .map((course) => [course.course.id, Number(course.suggested_principal_teacher_code)]),
      ))
    } catch (requestError) {
      setPreview(null)
      setPrincipals({})
      setError(errorMessage(requestError))
    } finally {
      setPreviewLoading(false)
    }
  }

  const principalSelectionComplete = Boolean(preview?.courses.every((course) => (
    !course.requires_principal_teacher || Boolean(principals[course.course.id])
  )))
  const careerSelectionComplete = Boolean(preview?.courses.every((course) => (
    Boolean(course.selected_career_code)
    && careers[course.course.id] === course.selected_career_code
  )))
  const validationComplete = Boolean(
    preview?.can_apply && principalSelectionComplete && careerSelectionComplete,
  )

  const applyEnrollment = async () => {
    if (!validationComplete || !preview) return
    setApplying(true)
    setError('')
    try {
      const response = await applyMoodleAcademicEnrollment({
        course_ids: selectedCourses.map((course) => course.id),
        period_code: Number(periodCode),
        jornada_code: Number(jornadaCode),
        career_by_course: selectedCareerPayload(),
        principal_teacher_by_course: principals,
        preview_fingerprint: preview.fingerprint,
      })
      setResult(response)
      setPreview(null)
      setConfirmOpen(false)
      setDetailView(null)
    } catch (requestError) {
      setError(errorMessage(requestError))
      setConfirmOpen(false)
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="moodle-section moodle-academic-enrollment">
      <div className="moodle-section__heading">
        <div>
          <span>Integración Moodle - INTECBDD</span>
          <h2>Matrícula académica masiva</h2>
          <p>Seleccione el período y los cursos; la carrera y materia se validarán con el código único de PENSUM.</p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={catalogLoading || coursesLoading || previewLoading || applying}
          onClick={() => {
            void loadCatalog()
            void loadCourses(true)
          }}
        >
          {catalogLoading || coursesLoading ? 'Actualizando...' : 'Actualizar catálogos'}
        </button>
      </div>

      {error && <div className="moodle-alert moodle-alert--error" role="alert">{error}</div>}

      <section className="moodle-academic-step" aria-labelledby="moodle-academic-destination">
        <div className="moodle-academic-step__heading">
          <div>
            <span>Paso 1</span>
            <h3 id="moodle-academic-destination">Definir destino académico</h3>
          </div>
          <strong>{selectedCourses.length} curso(s) seleccionado(s)</strong>
        </div>
        <div className="moodle-academic-destination">
          <label>
            <span>Período académico</span>
            <select
              value={periodCode}
              disabled={catalogLoading || applying}
              onChange={(event) => {
                setPeriodCode(event.target.value)
                resetReview()
              }}
            >
              <option value="">Seleccione un período</option>
              {(catalog?.periods ?? []).map((period) => (
                <option value={period.code} key={period.code}>
                  {period.name} · {period.enrollment_type} · {period.state || 'Sin estado'}
                </option>
              ))}
            </select>
            <small>La matrícula se registrará únicamente en este período.</small>
          </label>
          <label>
            <span>Jornada</span>
            <select
              value={jornadaCode}
              disabled={catalogLoading || applying}
              onChange={(event) => {
                setJornadaCode(event.target.value)
                resetReview()
              }}
            >
              <option value="">Seleccione una jornada</option>
              {(catalog?.jornadas ?? []).map((jornada) => (
                <option value={jornada.code} key={jornada.code}>{jornada.name}</option>
              ))}
            </select>
            <small>Se utiliza para nuevas cabeceras y asignaciones docentes.</small>
          </label>
        </div>
      </section>

      <section className="moodle-academic-step" aria-labelledby="moodle-academic-courses">
        <div className="moodle-academic-step__heading">
          <div>
            <span>Paso 2</span>
            <h3 id="moodle-academic-courses">Seleccionar cursos Moodle</h3>
          </div>
          <div className="moodle-academic-selection-actions">
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={!courses?.items.length || applying}
              onClick={selectVisible}
            >
              Seleccionar visibles
            </button>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={selectedCourses.length === 0 || applying}
              onClick={() => {
                setSelectedCourses([])
                resetReview()
              }}
            >
              Limpiar selección
            </button>
          </div>
        </div>

        <form className="moodle-academic-course-search" onSubmit={submitSearch}>
          <label>
            <span>Buscar curso</span>
            <input
              type="search"
              maxLength={256}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Nombre completo, nombre corto o código"
            />
          </label>
          <button type="submit" className="moodle-button moodle-button--primary" disabled={coursesLoading}>
            {coursesLoading ? 'Consultando...' : 'Buscar'}
          </button>
        </form>

        <div className="moodle-academic-course-list" aria-live="polite">
          {(courses?.items ?? []).map((course) => (
            <label className={selectedIds.has(course.id) ? 'is-selected' : ''} key={course.id}>
              <input
                type="checkbox"
                checked={selectedIds.has(course.id)}
                disabled={applying}
                onChange={() => toggleCourse(course)}
              />
              <span>
                <strong>{course.displayname || course.fullname || 'Curso sin nombre'}</strong>
                <small>{course.shortname || 'Sin nombre corto'}</small>
              </span>
              <span>
                <b>{course.idnumber || `ID ${course.id}`}</b>
                <small>{course.categoryname || 'Sin categoría'}</small>
              </span>
            </label>
          ))}
          {!coursesLoading && (courses?.items.length ?? 0) === 0 && (
            <div className="moodle-empty">No se encontraron cursos con el filtro actual.</div>
          )}
          {coursesLoading && <div className="moodle-empty">Consultando cursos Moodle...</div>}
        </div>
      </section>

      <div className="moodle-academic-actions">
        <span>El paralelo se obtiene del último segmento del nombre, por ejemplo <strong>PBS1</strong>.</span>
        <button
          type="button"
          className="moodle-button moodle-button--primary"
          disabled={previewLoading || applying || selectedCourses.length === 0 || !periodCode || !jornadaCode}
          onClick={() => void reviewEnrollment()}
        >
          {previewLoading ? 'Validando matrícula...' : 'Previsualizar matrícula masiva'}
        </button>
      </div>

      {preview && (
        <section className="moodle-academic-review" aria-labelledby="moodle-academic-review">
          <div className="moodle-academic-step__heading">
            <div>
              <span>Paso 3</span>
              <h3 id="moodle-academic-review">Validación previa</h3>
            </div>
            <span className={`moodle-academic-status ${validationComplete ? 'is-success' : 'is-error'}`}>
              {validationComplete ? 'Validación completa' : 'Requiere corrección'}
            </span>
          </div>

          <div className="moodle-academic-summary">
            <div><span>Cursos listos</span><strong>{preview.summary.ready_courses}/{preview.summary.selected_courses}</strong></div>
            <AcademicSummaryButton label="Por matricular" value={preview.summary.ready_students} onClick={() => setDetailView('ready')} />
            <AcademicSummaryButton label="Ya matriculados" value={preview.summary.existing_students} onClick={() => setDetailView('existing')} />
            <AcademicSummaryButton label="Bloqueados" value={preview.summary.blocked_students} onClick={() => setDetailView('blocked')} />
            <AcademicSummaryButton label="Ignorados" value={preview.summary.ignored_users} onClick={() => setDetailView('ignored')} />
            <AcademicSummaryButton label="Primera matrícula" value={preview.summary.first_enrollments} onClick={() => setDetailView('first')} />
            <AcademicSummaryButton label="Segunda matrícula" value={preview.summary.second_enrollments} onClick={() => setDetailView('second')} />
            <AcademicSummaryButton label="Tercera matrícula" value={preview.summary.third_enrollments} onClick={() => setDetailView('third')} />
            <AcademicSummaryButton label="Docentes validados" value={preview.summary.matched_teachers} onClick={() => setDetailView('teachers')} />
          </div>

          <div className="moodle-academic-review-list">
            {preview.courses.map((course) => (
              <article className={course.ready ? 'is-ready' : 'is-blocked'} key={course.course.id}>
                <header>
                  <div>
                    <span className={`moodle-academic-status ${course.ready ? 'is-success' : 'is-error'}`}>
                      {course.ready ? 'Curso validado' : 'Curso bloqueado'}
                    </span>
                    <h4>{course.course.name}</h4>
                    <p>
                      Código {course.course_code || 'no identificado'} · Paralelo {course.parallel || 'no identificado'}
                    </p>
                  </div>
                  <div className="moodle-academic-course-counts">
                    <strong>{course.summary.ready_students + course.summary.existing_students}</strong>
                    <span>estudiante(s) aplicable(s)</span>
                  </div>
                </header>

                {course.errors.length > 0 && (
                  <div className="moodle-academic-errors">
                    {course.errors.map((message) => <span key={message}>{message}</span>)}
                  </div>
                )}
                {course.warnings.length > 0 && (
                  <div className="moodle-academic-warnings">
                    {course.warnings.map((message) => <span key={message}>{message}</span>)}
                  </div>
                )}

                <div className="moodle-academic-career-selection">
                  <label>
                    <span>Carrera académica del curso</span>
                    <select
                      value={careers[course.course.id] ?? course.selected_career_code ?? ''}
                      disabled={applying || previewLoading || course.subject_candidates.length === 0}
                      onChange={(event) => {
                        const value = Number(event.target.value)
                        setCareers((current) => {
                          const next = { ...current }
                          if (Number.isInteger(value) && value > 0) next[course.course.id] = value
                          else delete next[course.course.id]
                          return next
                        })
                        setResult(null)
                        setConfirmOpen(false)
                        setError('')
                      }}
                    >
                      <option value="">Seleccione una carrera</option>
                      {courseCareerOptions(course).map((candidate) => (
                        <option value={candidate.career_code} key={candidate.career_code}>
                          {candidate.career_name}
                        </option>
                      ))}
                    </select>
                    <small>
                      {course.course_code
                        ? `Código único ${course.course_code} en PENSUM.`
                        : 'El curso no tiene un código único reconocido.'}
                    </small>
                  </label>
                  <div>
                    <span>Relación validada</span>
                    <strong>
                      {course.selected_career_name || 'Pendiente de validar la carrera'}
                    </strong>
                    <small>
                      Período {preview.period.name} · Paralelo {course.parallel || 'pendiente'}
                    </small>
                  </div>
                </div>

                <div className="moodle-academic-contexts">
                  {course.academic_contexts.map((context) => (
                    <div key={`${context.career_code}-${context.subject_id}`}>
                      <span>Materia validada</span>
                      <strong>{context.subject_code} · {context.subject_name}</strong>
                      <small>{context.career_name} · {context.students} estudiante(s)</small>
                    </div>
                  ))}
                </div>

                <div className="moodle-academic-teachers">
                  <h5>Docentes del curso</h5>
                  {course.teachers.map((teacher) => (
                    <label
                      className={teacher.status === 'COINCIDE' ? 'is-valid' : 'is-invalid'}
                      key={teacher.moodle_user_id}
                    >
                      <input
                        type="radio"
                        name={`principal-${course.course.id}`}
                        checked={principals[course.course.id] === teacher.academic_code}
                        disabled={teacher.status !== 'COINCIDE' || applying}
                        onChange={() => {
                          if (!teacher.academic_code) return
                          setPrincipals((current) => ({ ...current, [course.course.id]: Number(teacher.academic_code) }))
                        }}
                      />
                      <span>
                        <strong>{teacher.academic_name || teacher.moodle_name}</strong>
                        <small>{teacher.moodle_email || 'Sin correo'} · {teacher.message}</small>
                      </span>
                      <span className={`moodle-academic-status ${statusClass(teacher.status)}`}>
                        {statusLabel(teacher.status)}
                      </span>
                    </label>
                  ))}
                  {course.teachers.length > 1 && (
                    <small>Seleccione el docente principal. Todos los docentes validados serán asignados al curso.</small>
                  )}
                </div>

                <details className="moodle-academic-students">
                  <summary>Revisar {course.students.length} estudiante(s)</summary>
                  <div className="moodle-table-wrap">
                    <table className="moodle-table">
                      <thead>
                        <tr>
                          <th>Estudiante Moodle</th>
                          <th>Correo / identificación</th>
                          <th>Registro académico</th>
                          <th>Materia y carrera</th>
                          <th>N.º matrícula</th>
                          <th>Validación</th>
                        </tr>
                      </thead>
                      <tbody>
                        {course.students.map((student) => (
                          <tr key={student.moodle_user_id}>
                            <td><strong>{student.moodle_name}</strong><small>ID {student.moodle_user_id}</small></td>
                            <td><strong>{student.moodle_email || 'Sin correo'}</strong><small>{student.moodle_idnumber || 'Sin identificación'}</small></td>
                            <td><strong>{student.academic_name || 'Sin coincidencia'}</strong><small>{student.student_code ? `Código ${student.student_code}` : student.match_source}</small></td>
                            <td><strong>{student.subject_name || 'Sin materia'}</strong><small>{student.career_name || 'Sin carrera'}</small></td>
                            <td>
                              <strong>{student.enrollment_number ? `${student.enrollment_number}.ª` : '-'}</strong>
                              <small>{student.status === 'EXISTENTE' ? 'Ya registrada' : 'Intento calculado'}</small>
                            </td>
                            <td>
                              <span className={`moodle-academic-status ${statusClass(student.status)}`}>
                                {statusLabel(student.status)}
                              </span>
                              <small>{student.message}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </article>
            ))}
          </div>

          {!principalSelectionComplete && (
            <div className="moodle-alert moodle-alert--warning" role="status">
              Seleccione un docente principal en cada curso que tenga más de un docente validado.
            </div>
          )}
          {!careerSelectionComplete && (
            <div className="moodle-alert moodle-alert--warning" role="status">
              Seleccione una carrera válida por curso y vuelva a ejecutar la validación previa.
            </div>
          )}
          <div className="moodle-academic-actions">
            <span>{preview.period.name} · {preview.jornada.name}</span>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={previewLoading || applying}
              onClick={() => void reviewEnrollment()}
            >
              {previewLoading ? 'Validando...' : 'Revalidar carrera y estudiantes'}
            </button>
            <button
              type="button"
              className="moodle-button moodle-button--primary"
              disabled={!validationComplete || applying}
              onClick={() => setConfirmOpen(true)}
            >
              Confirmar matrícula masiva
            </button>
          </div>
        </section>
      )}

      {detailView && preview && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setDetailView(null)
          }}
        >
          <section
            className="moodle-confirm-dialog moodle-academic-detail"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-academic-detail-title"
          >
            <header className="moodle-confirm-dialog__header">
              <div>
                <span>{ACADEMIC_DETAIL_COPY[detailView].eyebrow}</span>
                <h2 id="moodle-academic-detail-title">{ACADEMIC_DETAIL_COPY[detailView].title}</h2>
              </div>
              <button
                type="button"
                className="moodle-button moodle-dialog-close"
                aria-label={`Cerrar ${ACADEMIC_DETAIL_COPY[detailView].title.toLocaleLowerCase('es')}`}
                onClick={() => setDetailView(null)}
              >
                Cerrar
              </button>
            </header>

            <div className="moodle-confirm-dialog__body moodle-academic-detail__body">
              <div className="moodle-academic-detail__context">
                <div>
                  <span>Registros</span>
                  <strong>{detailView === 'teachers' ? detailTeachers.length : detailStudents.length}</strong>
                </div>
                <div>
                  <span>Período</span>
                  <strong>{preview.period.name}</strong>
                </div>
                <div>
                  <span>Jornada</span>
                  <strong>{preview.jornada.name}</strong>
                </div>
              </div>

              {detailView === 'teachers' && detailTeachers.length > 0 && (
                <div className="moodle-table-wrap">
                  <table className="moodle-table moodle-academic-detail__table">
                    <thead>
                      <tr>
                        <th>Docente</th>
                        <th>Curso Moodle</th>
                        <th>Identificación</th>
                        <th>Relación académica</th>
                        <th>Asignación</th>
                        <th>Validación</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailTeachers.map(({ course, teacher }) => (
                        <tr key={`${course.course.id}:${teacher.moodle_user_id}`}>
                          <td>
                            <strong>{teacher.academic_name || teacher.moodle_name}</strong>
                            <small>{teacher.academic_name && teacher.academic_name !== teacher.moodle_name ? `Moodle: ${teacher.moodle_name}` : `ID Moodle ${teacher.moodle_user_id}`}</small>
                          </td>
                          <td>
                            <strong>{course.course.name}</strong>
                            <small>Paralelo {course.parallel || 'sin identificar'}</small>
                          </td>
                          <td>
                            <strong>{teacher.moodle_email || 'Sin correo'}</strong>
                            <small>{teacher.moodle_idnumber || 'Sin identificación en Moodle'}</small>
                          </td>
                          <td>
                            <strong>{teacher.academic_code ? `Código ${teacher.academic_code}` : 'Sin código'}</strong>
                            <small>{course.academic_contexts.map((context) => context.subject_name).join(', ') || 'Sin materia relacionada'}</small>
                          </td>
                          <td>
                            <strong>{principals[course.course.id] === teacher.academic_code ? 'Principal' : 'Docente del curso'}</strong>
                            <small>{teacher.roles.join(', ') || 'Rol docente'}</small>
                          </td>
                          <td>
                            <span className={`moodle-academic-status ${statusClass(teacher.status)}`}>
                              {statusLabel(teacher.status)}
                            </span>
                            <small>{teacher.message}</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {detailView !== 'teachers' && detailStudents.length > 0 && (
                <div className="moodle-table-wrap">
                  <table className="moodle-table moodle-academic-detail__table">
                    <thead>
                      <tr>
                        <th>Estudiante</th>
                        <th>Curso Moodle</th>
                        <th>Correo / identificación</th>
                        <th>Materia y carrera</th>
                        <th>N.º matrícula</th>
                        <th>Validación</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailStudents.map(({ course, student }) => (
                        <tr key={`${course.course.id}:${student.moodle_user_id}`}>
                          <td>
                            <strong>{student.academic_name || student.moodle_name}</strong>
                            <small>{student.academic_name && student.academic_name !== student.moodle_name ? `Moodle: ${student.moodle_name}` : `ID Moodle ${student.moodle_user_id}`}</small>
                          </td>
                          <td>
                            <strong>{course.course.name}</strong>
                            <small>Paralelo {course.parallel || 'sin identificar'}</small>
                          </td>
                          <td>
                            <strong>{student.moodle_email || 'Sin correo'}</strong>
                            <small>{student.moodle_idnumber || 'Sin identificación en Moodle'}</small>
                          </td>
                          <td>
                            <strong>{student.subject_name || 'Sin materia relacionada'}</strong>
                            <small>{student.career_name || 'Sin carrera'}{student.student_code ? ` · Código ${student.student_code}` : ''}</small>
                          </td>
                          <td>
                            <strong>{student.enrollment_number ? `${student.enrollment_number}.ª` : '-'}</strong>
                            <small>{student.status === 'EXISTENTE' ? 'Ya registrada' : 'Intento calculado'}</small>
                          </td>
                          <td>
                            <span className={`moodle-academic-status ${statusClass(student.status)}`}>
                              {statusLabel(student.status)}
                            </span>
                            <small>{student.message}</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(detailView === 'teachers' ? detailTeachers.length : detailStudents.length) === 0 && (
                <div className="moodle-empty">{ACADEMIC_DETAIL_COPY[detailView].empty}</div>
              )}
            </div>
          </section>
        </div>
      )}

      {result && (
        <section className="moodle-academic-result" aria-live="polite">
          <div className="moodle-academic-step__heading">
            <div><span>Resultado</span><h3>{result.message}</h3></div>
            <span className="moodle-academic-status is-success">Completado</span>
          </div>
          <div className="moodle-academic-summary">
            <div><span>Cursos</span><strong>{result.summary.courses}</strong></div>
            <div><span>Matriculados</span><strong>{result.summary.students_inserted}</strong></div>
            <div><span>Existentes</span><strong>{result.summary.students_existing}</strong></div>
            <div><span>Omitidos</span><strong>{result.summary.students_skipped}</strong></div>
            <div><span>Primeras creadas</span><strong>{result.summary.first_enrollments}</strong></div>
            <div><span>Segundas creadas</span><strong>{result.summary.second_enrollments}</strong></div>
            <div><span>Terceras creadas</span><strong>{result.summary.third_enrollments}</strong></div>
            <div><span>Docencias nuevas</span><strong>{result.summary.teacher_assignments_inserted}</strong></div>
            <div><span>Vínculos docentes</span><strong>{result.summary.student_teacher_links}</strong></div>
          </div>
        </section>
      )}

      {confirmOpen && preview && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !applying) setConfirmOpen(false)
          }}
        >
          <div className="moodle-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="moodle-enrollment-confirm">
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Confirmación académica</span>
                <h2 id="moodle-enrollment-confirm">Matricular {preview.summary.ready_students} estudiante(s)</h2>
              </div>
            </div>
            <div className="moodle-confirm-dialog__body">
              <p>
                Se procesarán {preview.summary.selected_courses} curso(s) en <strong>{preview.period.name}</strong>.
                Las matrículas existentes se conservarán y todos los docentes validados serán asignados.
              </p>
              <p>
                Nuevas matrículas: <strong>{preview.summary.first_enrollments}</strong> primera(s),{' '}
                <strong>{preview.summary.second_enrollments}</strong> segunda(s) y{' '}
                <strong>{preview.summary.third_enrollments}</strong> tercera(s).
              </p>
            </div>
            <div className="moodle-confirm-dialog__actions">
              <button type="button" className="moodle-button moodle-button--secondary" disabled={applying} onClick={() => setConfirmOpen(false)}>
                Cancelar
              </button>
              <button type="button" className="moodle-button moodle-button--primary" disabled={applying} onClick={() => void applyEnrollment()}>
                {applying ? 'Matriculando...' : 'Ejecutar matrícula masiva'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
