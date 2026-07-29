import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  fetchAdminGradeTeacherCourses,
  fetchAdminGradeTeachers,
  fetchAdminGradeTeacherStudents,
  updateLegacyStudentGrade,
} from '../../lib/api'
import { calculateRegularGradeWithRecovery, constrainDecimalInput, parseBoundedDecimal } from '../../lib/gradeCalculation'
import type {
  AdminGradeStudent,
  AdminGradeTeacher,
  PortalTeacherCourse,
} from '../../types/app'

type NotasPorAsignaturaViewProps = {
  displayName: string
  role: string
}

type SubjectGroup = {
  key: string
  code: string
  name: string
  careerCodes: string[]
  careerNames: string[]
  levels: number[]
  courses: PortalTeacherCourse[]
}

type PeriodGroup = {
  key: string
  code: string
  detail: string
  type: GradePeriodType
  careerNames: string[]
  courses: PortalTeacherCourse[]
  totalStudents: number
}

type GradeFlowStep = 'TEACHER' | 'SUBJECT' | 'COURSE' | 'STUDENTS'
type GradePeriodType = 'R' | 'H'

type GradeDraft = {
  teoria_homo: string
  practica_homo: string
  p1_tareas: string
  p1_proyectos: string
  p1_examen: string
  p2_tareas: string
  p2_proyectos: string
  p2_examen: string
  p3_tareas: string
  p3_proyectos: string
  p3_examen: string
  asistencia: string
  recuperacion: string
}

const regularGradeSections = [
  { title: 'Parcial 1', task: 'p1_tareas', project: 'p1_proyectos', exam: 'p1_examen' },
  { title: 'Parcial 2', task: 'p2_tareas', project: 'p2_proyectos', exam: 'p2_examen' },
  { title: 'Parcial 3', task: 'p3_tareas', project: 'p3_proyectos', exam: 'p3_examen' },
] as const

const TEACHERS_PER_PAGE = 10
const STUDENTS_PER_PAGE = 25

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function courseKey(course: PortalTeacherCourse): string {
  return [
    course.cod_anio_basica,
    course.cod_materia || course.codigo_materia,
    course.codigo_periodo,
    course.paralelo,
    course.cod_jornada ?? '',
  ].join('|')
}

function periodKey(course: PortalTeacherCourse): string {
  return String(course.codigo_periodo || '').trim()
}

function coursePeriodType(course: PortalTeacherCourse): GradePeriodType {
  const periodText = `${course.tipo_periodo || ''} ${course.detalle_periodo || ''}`.trim().toUpperCase()
  return course.es_homologacion || periodText === 'H' || periodText.includes('HOMO') ? 'H' : 'R'
}

function periodTypeLabel(type: GradePeriodType | null): string {
  if (type === 'H') return 'Homologación'
  if (type === 'R') return 'Regular'
  return 'Sin modalidad seleccionada'
}

function score(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function gradeDetail(student: AdminGradeStudent): string {
  if (student.es_homologacion) {
    return `Teoría ${score(student.teoria_homo)} · Práctica ${score(student.practica_homo)}`
  }
  return `P1 ${score(student.prom_p1)} · P2 ${score(student.prom_p2)} · P3 ${score(student.prom_p3)}`
}

function registrationLabel(value?: string): string {
  if (value === 'COMPLETA') return 'Completa'
  if (value === 'EN_PROCESO') return 'En proceso'
  return 'Falta calificar'
}

function resultLabel(value?: string): string {
  if (value === 'APROBADO') return 'Aprobado'
  if (value === 'REPROBADO') return 'Reprobado'
  return 'Pendiente'
}

function gradeDraftValue(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? '' : String(value)
}

function gradeDraftFromStudent(student: AdminGradeStudent): GradeDraft {
  return {
    teoria_homo: gradeDraftValue(student.teoria_homo),
    practica_homo: gradeDraftValue(student.practica_homo),
    p1_tareas: gradeDraftValue(student.p1_tareas),
    p1_proyectos: gradeDraftValue(student.p1_proyectos),
    p1_examen: gradeDraftValue(student.p1_examen),
    p2_tareas: gradeDraftValue(student.p2_tareas),
    p2_proyectos: gradeDraftValue(student.p2_proyectos),
    p2_examen: gradeDraftValue(student.p2_examen),
    p3_tareas: gradeDraftValue(student.p3_tareas),
    p3_proyectos: gradeDraftValue(student.p3_proyectos),
    p3_examen: gradeDraftValue(student.p3_examen),
    asistencia: gradeDraftValue(student.asistencia),
    recuperacion: gradeDraftValue(student.recuperacion),
  }
}

function nullableGrade(value: string): number | null {
  const normalized = value.trim().replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function draftRegularCalculation(draft: GradeDraft) {
  return calculateRegularGradeWithRecovery(
    regularGradeSections.map((section) => [
      nullableGrade(draft[section.task]),
      nullableGrade(draft[section.project]),
      nullableGrade(draft[section.exam]),
    ]),
    nullableGrade(draft.recuperacion),
  )
}

function draftFinal(student: AdminGradeStudent, draft: GradeDraft): number | null {
  if (student.es_homologacion) {
    const theory = nullableGrade(draft.teoria_homo)
    const practice = nullableGrade(draft.practica_homo)
    if (theory === null || practice === null) return null
    return Math.round(((theory * 0.4) + (practice * 0.6)) * 100) / 100
  }
  return draftRegularCalculation(draft).final
}

function integerValue(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : null
}

function canUpdateStudentGrade(student: AdminGradeStudent): boolean {
  return [
    student.codigo_estud,
    student.cod_anio_basica,
    student.codigo_periodo,
    student.codigo_materia,
    student.num_matricula,
    student.num_grupo,
  ].every((value) => integerValue(value) !== null) && Boolean(student.paralelo?.trim())
}

function normalizedAccessRole(role: string): string {
  return role.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase()
}

export function NotasPorAsignaturaView({ displayName, role }: Readonly<NotasPorAsignaturaViewProps>) {
  const [teachers, setTeachers] = useState<AdminGradeTeacher[]>([])
  const [courses, setCourses] = useState<PortalTeacherCourse[]>([])
  const [students, setStudents] = useState<AdminGradeStudent[]>([])
  const [summary, setSummary] = useState({ completas: 0, en_proceso: 0, sin_calificar: 0, aprobados: 0, reprobados: 0 })
  const [teacherSearch, setTeacherSearch] = useState('')
  const [teacherState, setTeacherState] = useState('')
  const [studentSearch, setStudentSearch] = useState('')
  const [gradeFilter, setGradeFilter] = useState('PENDIENTES')
  const [selectedTeacher, setSelectedTeacher] = useState<AdminGradeTeacher | null>(null)
  const [selectedSubjectKey, setSelectedSubjectKey] = useState('')
  const [selectedPeriodKeys, setSelectedPeriodKeys] = useState<string[]>([])
  const [periodToAddKey, setPeriodToAddKey] = useState('')
  const [teacherPage, setTeacherPage] = useState(1)
  const [studentPage, setStudentPage] = useState(1)
  const [loadingTeachers, setLoadingTeachers] = useState(false)
  const [loadingCourses, setLoadingCourses] = useState(false)
  const [loadingStudents, setLoadingStudents] = useState(false)
  const [activeStep, setActiveStep] = useState<GradeFlowStep>('TEACHER')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editingStudent, setEditingStudent] = useState<AdminGradeStudent | null>(null)
  const [gradeDraft, setGradeDraft] = useState<GradeDraft | null>(null)
  const [gradeSaving, setGradeSaving] = useState(false)
  const [gradeSaveError, setGradeSaveError] = useState('')

  const subjects = useMemo<SubjectGroup[]>(() => {
    const grouped = new Map<string, SubjectGroup>()
    for (const course of courses) {
      if (Number(course.total_estudiantes || 0) <= 0) continue
      const careerCode = String(course.cod_anio_basica || '')
      const careerName = course.nombre_carrera || 'Carrera no informada'
      const code = String(course.cod_materia || course.codigo_materia || '').trim()
      const key = code.toLocaleUpperCase('es')
      if (!key) continue
      const current = grouped.get(key)
      if (current) {
        if (!current.courses.some((item) => courseKey(item) === courseKey(course))) {
          current.courses.push(course)
        }
        if (careerCode && !current.careerCodes.includes(careerCode)) current.careerCodes.push(careerCode)
        if (careerName && !current.careerNames.includes(careerName)) current.careerNames.push(careerName)
        if (course.semestre && !current.levels.includes(course.semestre)) current.levels.push(course.semestre)
      } else {
        grouped.set(key, {
          key,
          code,
          name: course.nombre_materia || `Asignatura ${code}`,
          careerCodes: careerCode ? [careerCode] : [],
          careerNames: careerName ? [careerName] : [],
          levels: course.semestre ? [course.semestre] : [],
          courses: [course],
        })
      }
    }
    return Array.from(grouped.values())
      .map((subject) => ({
        ...subject,
        careerNames: [...subject.careerNames].sort((left, right) => left.localeCompare(right, 'es', { sensitivity: 'base' })),
        levels: [...subject.levels].sort((left, right) => left - right),
        courses: [...subject.courses].sort((left, right) =>
          `${left.nombre_carrera} ${left.detalle_periodo} ${left.paralelo}`.localeCompare(
            `${right.nombre_carrera} ${right.detalle_periodo} ${right.paralelo}`,
            'es',
            { sensitivity: 'base' },
          ),
        ),
      }))
      .sort((left, right) => `${left.name} ${left.code}`.localeCompare(`${right.name} ${right.code}`, 'es', { sensitivity: 'base' }))
  }, [courses])

  const selectedSubject = subjects.find((subject) => subject.key === selectedSubjectKey) || null
  const periodGroups = useMemo<PeriodGroup[]>(() => {
    const grouped = new Map<string, PeriodGroup>()
    for (const course of selectedSubject?.courses || []) {
      const key = periodKey(course)
      if (!key) continue
      const careerName = course.nombre_carrera || 'Carrera no informada'
      const current = grouped.get(key)
      if (current) {
        if (!current.courses.some((item) => courseKey(item) === courseKey(course))) {
          current.courses.push(course)
          current.totalStudents += Number(course.total_estudiantes || 0)
        }
        if (!current.careerNames.includes(careerName)) current.careerNames.push(careerName)
        continue
      }
      grouped.set(key, {
        key,
        code: key,
        detail: course.detalle_periodo || key,
        type: coursePeriodType(course),
        careerNames: [careerName],
        courses: [course],
        totalStudents: Number(course.total_estudiantes || 0),
      })
    }
    return Array.from(grouped.values())
      .map((period) => ({
        ...period,
        careerNames: [...period.careerNames].sort((left, right) => left.localeCompare(right, 'es', { sensitivity: 'base' })),
        courses: [...period.courses].sort((left, right) =>
          `${left.nombre_carrera} ${left.paralelo} ${left.jornada}`.localeCompare(
            `${right.nombre_carrera} ${right.paralelo} ${right.jornada}`,
            'es',
            { sensitivity: 'base' },
          ),
        ),
      }))
      .sort((left, right) => left.detail.localeCompare(right.detail, 'es', { sensitivity: 'base' }))
  }, [selectedSubject])
  const selectedPeriods = useMemo(
    () => selectedPeriodKeys
      .map((key) => periodGroups.find((period) => period.key === key) || null)
      .filter((period): period is PeriodGroup => period !== null),
    [periodGroups, selectedPeriodKeys],
  )
  const selectedCourses = useMemo(
    () => selectedPeriods
      .map((period) => period.courses[0] || null)
      .filter((course): course is PortalTeacherCourse => course !== null),
    [selectedPeriods],
  )
  const selectedPeriodType = selectedPeriods[0]?.type || null
  const normalizedRole = normalizedAccessRole(role)
  const canEditGrades = ['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA'].includes(normalizedRole)
  const gradePreviewCalculation = editingStudent && gradeDraft && !editingStudent.es_homologacion
    ? draftRegularCalculation(gradeDraft)
    : null
  const gradePreviewFinal = editingStudent && gradeDraft ? draftFinal(editingStudent, gradeDraft) : null

  const filteredStudents = useMemo(() => {
    const normalizedSearch = studentSearch.trim().toLocaleLowerCase('es')
    return students.filter((student) => {
      const matchesSearch = !normalizedSearch || [
        student.nombre_estudiante,
        student.cedula,
        student.codigo_estud,
        student.nombre_carrera,
        student.detalle_periodo,
        student.codigo_periodo,
      ]
        .some((value) => String(value || '').toLocaleLowerCase('es').includes(normalizedSearch))
      if (!matchesSearch) return false
      if (gradeFilter === 'PENDIENTES') return student.estado_registro !== 'COMPLETA'
      if (gradeFilter === 'COMPLETAS') return student.estado_registro === 'COMPLETA'
      if (gradeFilter === 'APROBADOS') return student.estado_nota === 'APROBADO'
      if (gradeFilter === 'REPROBADOS') return student.estado_nota === 'REPROBADO'
      return true
    })
  }, [gradeFilter, studentSearch, students])

  const teacherPages = Math.max(1, Math.ceil(teachers.length / TEACHERS_PER_PAGE))
  const visibleTeachers = teachers.slice((teacherPage - 1) * TEACHERS_PER_PAGE, teacherPage * TEACHERS_PER_PAGE)
  const studentPages = Math.max(1, Math.ceil(filteredStudents.length / STUDENTS_PER_PAGE))
  const visibleStudents = filteredStudents.slice((studentPage - 1) * STUDENTS_PER_PAGE, studentPage * STUDENTS_PER_PAGE)

  const loadTeachers = useCallback(async (search: string, state: string) => {
    setLoadingTeachers(true)
    setError('')
    try {
      const payload = await fetchAdminGradeTeachers({ buscar: search.trim(), estado: state, limit: 1000 })
      setTeachers(payload.items || [])
      setTeacherPage(1)
      setSelectedTeacher((current) =>
        current ? (payload.items || []).find((teacher) => teacher.codigo_doc === current.codigo_doc) || null : null,
      )
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo consultar el listado de docentes.'))
    } finally {
      setLoadingTeachers(false)
    }
  }, [])

  useEffect(() => {
    void loadTeachers('', '')
  }, [loadTeachers])

  useEffect(() => {
    setStudentPage(1)
  }, [gradeFilter, studentSearch])

  useEffect(() => {
    if (!editingStudent) return undefined
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !gradeSaving) {
        setEditingStudent(null)
        setGradeDraft(null)
        setGradeSaveError('')
      }
    }
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [editingStudent, gradeSaving])

  async function selectTeacher(teacher: AdminGradeTeacher) {
    setNotice('')
    setSelectedTeacher(teacher)
    setCourses([])
    setStudents([])
    setSelectedSubjectKey('')
    setSelectedPeriodKeys([])
    setPeriodToAddKey('')
    setActiveStep('TEACHER')
    setLoadingCourses(true)
    setError('')
    try {
      const payload = await fetchAdminGradeTeacherCourses(teacher.codigo_doc)
      const availableCourses = (payload.items || []).filter((course) => Number(course.total_estudiantes || 0) > 0)
      setCourses(availableCourses)
      setActiveStep('SUBJECT')
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudieron consultar las asignaturas del docente.'))
    } finally {
      setLoadingCourses(false)
    }
  }

  function chooseSubject(key: string) {
    setNotice('')
    setSelectedSubjectKey(key)
    setSelectedPeriodKeys([])
    setPeriodToAddKey('')
    setStudents([])
    setSummary({ completas: 0, en_proceso: 0, sin_calificar: 0, aprobados: 0, reprobados: 0 })
  }

  function resetStudentResults() {
    setStudents([])
    setStudentPage(1)
    setSummary({ completas: 0, en_proceso: 0, sin_calificar: 0, aprobados: 0, reprobados: 0 })
  }

  function addPeriod() {
    const period = periodGroups.find((item) => item.key === periodToAddKey)
    if (!period || selectedPeriodKeys.includes(periodToAddKey)) return
    if (selectedPeriodKeys.length >= 3) {
      setError('Solo puede seleccionar hasta 3 períodos.')
      return
    }
    if (selectedPeriodType && period.type !== selectedPeriodType) {
      setError('No puede mezclar períodos regulares y de homologación en la misma consulta.')
      return
    }
    setSelectedPeriodKeys((current) => [...current, periodToAddKey])
    setPeriodToAddKey('')
    setError('')
    setNotice('')
    resetStudentResults()
  }

  function removePeriod(key: string) {
    setSelectedPeriodKeys((current) => current.filter((item) => item !== key))
    setPeriodToAddKey('')
    setError('')
    setNotice('')
    resetStudentResults()
  }

  async function loadCourseStudents() {
    resetStudentResults()
    if (!selectedTeacher || selectedCourses.length === 0) return
    const invalidCourse = selectedCourses.some((course) => (
      !course.codigo_periodo
      || !course.cod_anio_basica
      || !course.codigo_materia
      || !course.paralelo
    ))
    if (invalidCourse) {
      setError('Uno de los períodos seleccionados no tiene completa la información del curso.')
      return
    }
    setLoadingStudents(true)
    setError('')
    try {
      const payload = await fetchAdminGradeTeacherStudents({
        codigoDoc: selectedTeacher.codigo_doc,
        courses: selectedCourses.map((course) => ({
          codigo_periodo: Number(course.codigo_periodo),
          cod_anio_basica: Number(course.cod_anio_basica),
          cod_jornada: course.cod_jornada,
          codigo_materia: course.codigo_materia || course.cod_materia || '',
          paralelo: course.paralelo || '',
        })),
      })
      const courseStudents = payload.items || []
      if (courseStudents.length === 0) {
        setError('Los períodos seleccionados no tienen estudiantes matriculados para esta asignatura.')
        return
      }
      setStudents(courseStudents)
      setSummary(payload.summary || { completas: 0, en_proceso: 0, sin_calificar: 0, aprobados: 0, reprobados: 0 })
      setActiveStep('STUDENTS')
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudieron consultar los estudiantes del curso.'))
    } finally {
      setLoadingStudents(false)
    }
  }

  function openGradeEditor(student: AdminGradeStudent) {
    if (!canEditGrades || !canUpdateStudentGrade(student)) return
    setEditingStudent(student)
    setGradeDraft(gradeDraftFromStudent(student))
    setGradeSaveError('')
    setNotice('')
  }

  function closeGradeEditor() {
    if (gradeSaving) return
    setEditingStudent(null)
    setGradeDraft(null)
    setGradeSaveError('')
  }

  function updateGradeDraft(field: keyof GradeDraft, value: string) {
    const constrained = constrainDecimalInput(value, field === 'asistencia' ? 100 : 10)
    if (constrained === null) return
    setGradeDraft((current) => current ? { ...current, [field]: constrained } : current)
  }

  async function saveStudentGrade() {
    if (!editingStudent || !gradeDraft) return
    const identifiers = {
      codigo_estud: integerValue(editingStudent.codigo_estud),
      cod_anio_basica: integerValue(editingStudent.cod_anio_basica),
      codigo_periodo: integerValue(editingStudent.codigo_periodo),
      codigo_materia: integerValue(editingStudent.codigo_materia),
      num_matricula: integerValue(editingStudent.num_matricula),
      num_grupo: integerValue(editingStudent.num_grupo),
    }
    if (Object.values(identifiers).some((value) => value === null) || !editingStudent.paralelo?.trim()) {
      setGradeSaveError('No se puede aislar esta matrícula. Actualice la consulta y vuelva a intentarlo.')
      return
    }

    setGradeSaving(true)
    setGradeSaveError('')
    try {
      const isHomologation = Boolean(editingStudent.es_homologacion)
      const response = await updateLegacyStudentGrade({
        codigo_estud: identifiers.codigo_estud!,
        cod_anio_basica: identifiers.cod_anio_basica!,
        codigo_periodo: identifiers.codigo_periodo!,
        codigo_materia: identifiers.codigo_materia!,
        paralelo: editingStudent.paralelo.trim(),
        num_matricula: identifiers.num_matricula!,
        num_grupo: identifiers.num_grupo!,
        es_homologacion: isHomologation,
        teoria_homo: isHomologation ? parseBoundedDecimal(gradeDraft.teoria_homo, 10, 'La nota teórica') : null,
        practica_homo: isHomologation ? parseBoundedDecimal(gradeDraft.practica_homo, 10, 'La nota práctica') : null,
        p1_tareas: isHomologation ? null : parseBoundedDecimal(gradeDraft.p1_tareas, 10, 'Tareas del parcial 1'),
        p1_proyectos: isHomologation ? null : parseBoundedDecimal(gradeDraft.p1_proyectos, 10, 'Proyectos del parcial 1'),
        p1_examen: isHomologation ? null : parseBoundedDecimal(gradeDraft.p1_examen, 10, 'Examen del parcial 1'),
        p2_tareas: isHomologation ? null : parseBoundedDecimal(gradeDraft.p2_tareas, 10, 'Tareas del parcial 2'),
        p2_proyectos: isHomologation ? null : parseBoundedDecimal(gradeDraft.p2_proyectos, 10, 'Proyectos del parcial 2'),
        p2_examen: isHomologation ? null : parseBoundedDecimal(gradeDraft.p2_examen, 10, 'Examen del parcial 2'),
        p3_tareas: isHomologation ? null : parseBoundedDecimal(gradeDraft.p3_tareas, 10, 'Tareas del parcial 3'),
        p3_proyectos: isHomologation ? null : parseBoundedDecimal(gradeDraft.p3_proyectos, 10, 'Proyectos del parcial 3'),
        p3_examen: isHomologation ? null : parseBoundedDecimal(gradeDraft.p3_examen, 10, 'Examen del parcial 3'),
        asistencia: parseBoundedDecimal(gradeDraft.asistencia, 100, 'La asistencia'),
        recuperacion: isHomologation ? null : parseBoundedDecimal(gradeDraft.recuperacion, 10, 'La recuperación'),
      })
      setEditingStudent(null)
      setGradeDraft(null)
      await loadCourseStudents()
      setNotice(response.message || 'Calificaciones actualizadas correctamente.')
    } catch (apiError) {
      setGradeSaveError(errorMessage(apiError, 'No se pudieron actualizar las calificaciones.'))
    } finally {
      setGradeSaving(false)
    }
  }

  function submitTeacherSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void loadTeachers(teacherSearch, teacherState)
  }

  const profileLabel = normalizedRole === 'ACADEMICO'
    ? 'Perfil académico'
    : normalizedRole === 'BIENESTAR'
      ? 'Perfil Bienestar'
      : 'Consulta administrativa'

  return (
    <div className="admin-grades-page">
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Calificaciones</p>
          <h2>Notas por asignatura</h2>
          <p className="report-description">
            Consulte al docente y la asignatura; luego seleccione hasta tres períodos regulares o hasta tres de homologación.
          </p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>{profileLabel}</span>
            </div>
          </div>
        </div>
      </header>

      {error && <div className="admin-grades-alert" role="alert">{error}</div>}
      {notice && <div className="admin-grades-notice" role="status">{notice}</div>}

      <section className="admin-grades-steps" aria-label="Flujo de consulta">
        <button
          type="button"
          className={activeStep === 'TEACHER' ? 'is-active' : selectedTeacher ? 'is-complete' : ''}
          onClick={() => setActiveStep('TEACHER')}
          aria-current={activeStep === 'TEACHER' ? 'step' : undefined}
        >
          <b>1</b><span>Docente</span>
        </button>
        <button
          type="button"
          className={activeStep === 'SUBJECT' ? 'is-active' : selectedSubject ? 'is-complete' : ''}
          onClick={() => setActiveStep('SUBJECT')}
          disabled={!selectedTeacher}
          aria-current={activeStep === 'SUBJECT' ? 'step' : undefined}
        >
          <b>2</b><span>Asignatura</span>
        </button>
        <button
          type="button"
          className={activeStep === 'COURSE' ? 'is-active' : selectedPeriods.length > 0 ? 'is-complete' : ''}
          onClick={() => setActiveStep('COURSE')}
          disabled={!selectedSubject}
          aria-current={activeStep === 'COURSE' ? 'step' : undefined}
        >
          <b>3</b><span>Período y carrera</span>
        </button>
        <button
          type="button"
          className={activeStep === 'STUDENTS' ? 'is-active' : ''}
          onClick={() => setActiveStep('STUDENTS')}
          disabled={selectedPeriods.length === 0 || students.length === 0}
          aria-current={activeStep === 'STUDENTS' ? 'step' : undefined}
        >
          <b>4</b><span>Estudiantes y notas</span>
        </button>
      </section>

      {activeStep === 'TEACHER' && (
        <section className="student-card admin-grades-section">
        <div className="card-head">
          <h3>1. Seleccionar docente</h3>
          <span>{loadingTeachers ? 'Consultando...' : `${teachers.length} docente(s) con asignaciones`}</span>
        </div>
        <form className="admin-grades-toolbar" onSubmit={submitTeacherSearch}>
          <label>
            <span>Buscar docente</span>
            <input
              value={teacherSearch}
              onChange={(event) => setTeacherSearch(event.target.value)}
              placeholder="Nombre, cédula, correo o código"
            />
          </label>
          <label>
            <span>Estado</span>
            <select value={teacherState} onChange={(event) => setTeacherState(event.target.value)}>
              <option value="">Todos</option>
              <option value="A">Activos</option>
              <option value="P">Inactivos</option>
              <option value="SIN_USUARIO">Sin usuario vinculado</option>
            </select>
          </label>
          <button type="submit" className="primary-action" disabled={loadingTeachers}>
            {loadingTeachers ? 'Buscando...' : 'Buscar'}
          </button>
        </form>

        <div className="admin-grades-table-wrap">
          <table className="admin-grades-table admin-grades-teachers-table">
            <thead>
              <tr>
                <th>Docente</th>
                <th>Cédula</th>
                <th>Correo</th>
                <th>Asignaturas</th>
                <th>Períodos</th>
                <th>Estado</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {visibleTeachers.map((teacher) => (
                <tr key={teacher.codigo_doc} className={selectedTeacher?.codigo_doc === teacher.codigo_doc ? 'is-selected' : ''}>
                  <td><strong>{teacher.docente}</strong><small>Código {teacher.codigo_doc}</small></td>
                  <td>{teacher.cedula || '-'}</td>
                  <td>{teacher.correo || '-'}</td>
                  <td>{teacher.total_asignaturas}</td>
                  <td>{teacher.total_periodos}</td>
                  <td><span className={`admin-grades-badge ${teacher.estado === 'A' ? 'is-ok' : 'is-muted'}`}>{teacher.estado_nombre || teacher.estado || 'Sin estado'}</span></td>
                  <td><button type="button" className="ghost-button" onClick={() => void selectTeacher(teacher)}>Seleccionar</button></td>
                </tr>
              ))}
              {!loadingTeachers && visibleTeachers.length === 0 && (
                <tr><td colSpan={7} className="admin-grades-empty">No se encontraron docentes con asignaciones.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="admin-grades-pagination">
          <span>Página {teacherPage} de {teacherPages}</span>
          <div>
            <button type="button" className="ghost-button" onClick={() => setTeacherPage((page) => Math.max(1, page - 1))} disabled={teacherPage === 1}>Anterior</button>
            <button type="button" className="ghost-button" onClick={() => setTeacherPage((page) => Math.min(teacherPages, page + 1))} disabled={teacherPage === teacherPages}>Siguiente</button>
          </div>
        </div>
        </section>
      )}

      {activeStep === 'SUBJECT' && (
        <section className="student-card admin-grades-section admin-grades-subscreen">
          <div className="card-head">
            <h3>2. Seleccionar asignatura</h3>
            <span>{selectedTeacher?.docente}</span>
          </div>
          <div className="admin-grades-course-selectors admin-grades-course-selectors--single">
            <label>
              <span>Asignatura impartida con estudiantes</span>
              <select value={selectedSubjectKey} onChange={(event) => chooseSubject(event.target.value)} disabled={loadingCourses}>
                <option value="">{loadingCourses ? 'Cargando asignaturas...' : 'Seleccione una asignatura'}</option>
                {subjects.map((subject) => (
                  <option key={subject.key} value={subject.key}>
                    {subject.code} · {subject.name} · {subject.careerNames.length} {subject.careerNames.length === 1 ? 'carrera' : 'carreras'}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selectedSubject && (
            <div className="admin-grades-subject-summary" aria-label="Información de la asignatura seleccionada">
              <div><span>Código único</span><strong>{selectedSubject.code}</strong></div>
              <div><span>Asignatura</span><strong>{selectedSubject.name}</strong></div>
              <div>
                <span>Carreras relacionadas</span>
                <strong>{selectedSubject.careerNames.join(' / ') || 'No informadas'}</strong>
                <small>Códigos: {selectedSubject.careerCodes.join(', ') || 'No informados'}</small>
              </div>
              <div><span>Niveles</span><strong>{selectedSubject.levels.length ? selectedSubject.levels.join(', ') : 'No informado'}</strong></div>
            </div>
          )}
          {!loadingCourses && subjects.length === 0 && (
            <p className="admin-grades-guidance">Este docente no tiene asignaturas con estudiantes matriculados.</p>
          )}
          <div className="admin-grades-flow-actions">
            <button type="button" className="ghost-button" onClick={() => setActiveStep('TEACHER')}>Volver a docentes</button>
            <button type="button" className="primary-action" onClick={() => setActiveStep('COURSE')} disabled={!selectedSubject}>Continuar al período</button>
          </div>
        </section>
      )}

      {activeStep === 'COURSE' && (
        <section className="student-card admin-grades-section admin-grades-subscreen">
          <div className="card-head">
            <h3>3. Seleccionar período y carrera</h3>
            <span>{selectedSubject ? `${selectedSubject.code} · ${selectedSubject.name}` : 'Seleccione una asignatura'}</span>
          </div>
          <div className="admin-grades-period-rule" role="status">
            <div>
              <span>Modalidad de la selección</span>
              <strong>{periodTypeLabel(selectedPeriodType)}</strong>
            </div>
            <div>
              <span>Períodos seleccionados</span>
              <strong>{selectedPeriods.length} / 3</strong>
            </div>
            <p>Cada código de período se agrega una sola vez e incluye todas sus carreras. Puede elegir hasta tres códigos distintos del mismo tipo.</p>
          </div>
          <div className="admin-grades-course-selectors admin-grades-period-picker">
            <label>
              <span>Agregar un período diferente</span>
              <select
                value={periodToAddKey}
                onChange={(event) => setPeriodToAddKey(event.target.value)}
                disabled={!selectedSubject || selectedPeriods.length >= 3}
              >
                <option value="">
                  {selectedPeriods.length >= 3 ? 'Límite de 3 períodos alcanzado' : 'Seleccione un período diferente'}
                </option>
                {periodGroups.map((period) => (
                  <option
                    key={period.key}
                    value={period.key}
                    disabled={
                      selectedPeriodKeys.includes(period.key)
                      || Boolean(selectedPeriodType && period.type !== selectedPeriodType)
                    }
                  >
                    [{periodTypeLabel(period.type)}] {period.detail} · {period.careerNames.length} {period.careerNames.length === 1 ? 'carrera' : 'carreras'} · {period.totalStudents} estudiante(s)
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="ghost-button"
              onClick={addPeriod}
              disabled={!periodToAddKey || selectedPeriods.length >= 3}
            >
              Agregar período
            </button>
          </div>
          {selectedPeriods.length > 0 && (
            <div className="admin-grades-selected-periods" aria-label="Períodos seleccionados">
              <div className="admin-grades-selected-periods__head">
                <strong>Selección para consultar</strong>
                <span>{periodTypeLabel(selectedPeriodType)}</span>
              </div>
              <ul>
                {selectedPeriods.map((period, index) => (
                  <li key={period.key}>
                    <span className="admin-grades-period-index">{index + 1}</span>
                    <div>
                      <strong>{period.detail}</strong>
                      <small>
                        {period.careerNames.join(' / ')} · {period.courses.length} {period.courses.length === 1 ? 'curso' : 'cursos'} · {period.totalStudents} estudiante(s)
                      </small>
                    </div>
                    <span className="admin-grades-type">{period.type}</span>
                    <button type="button" className="ghost-button" onClick={() => removePeriod(period.key)}>
                      Quitar
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="admin-grades-flow-actions">
            <button type="button" className="ghost-button" onClick={() => setActiveStep('SUBJECT')}>Volver a asignatura</button>
            <button
              type="button"
              className="primary-action"
              onClick={() => void loadCourseStudents()}
              disabled={selectedPeriods.length === 0 || loadingStudents}
            >
              {loadingStudents ? 'Consultando...' : 'Ver estudiantes y notas'}
            </button>
          </div>
        </section>
      )}

      {activeStep === 'STUDENTS' && (
        <section className="student-card admin-grades-section admin-grades-subscreen">
          <div className="card-head">
          <h3>4. Estudiantes y estado de calificación</h3>
          <span>
            {selectedPeriods.length > 0
              ? `${selectedSubject?.code} · ${selectedSubject?.name} · ${selectedPeriods.length} período(s) · ${periodTypeLabel(selectedPeriodType)}`
              : 'Seleccione al menos un período'}
          </span>
          </div>

          <div className="admin-grades-flow-actions admin-grades-flow-actions--compact">
            <button type="button" className="ghost-button" onClick={() => setActiveStep('COURSE')}>Cambiar períodos o carreras</button>
            <button type="button" className="ghost-button" onClick={() => setActiveStep('TEACHER')}>Cambiar docente</button>
          </div>

        <div className="admin-grades-summary">
          <div><span>Estudiantes</span><strong>{students.length}</strong></div>
          <div><span>Notas completas</span><strong>{summary.completas}</strong></div>
          <div><span>En proceso</span><strong>{summary.en_proceso}</strong></div>
          <div><span>Sin calificar</span><strong>{summary.sin_calificar}</strong></div>
          <div><span>Aprobados</span><strong>{summary.aprobados}</strong></div>
          <div><span>Reprobados</span><strong>{summary.reprobados}</strong></div>
        </div>

        <div className="admin-grades-toolbar admin-grades-toolbar--students">
          <label>
            <span>Buscar estudiante</span>
            <input value={studentSearch} onChange={(event) => setStudentSearch(event.target.value)} placeholder="Nombre, cédula, código, carrera o período" disabled={selectedPeriods.length === 0} />
          </label>
          <label>
            <span>Mostrar</span>
            <select value={gradeFilter} onChange={(event) => setGradeFilter(event.target.value)} disabled={selectedPeriods.length === 0}>
              <option value="PENDIENTES">Faltan calificaciones</option>
              <option value="TODOS">Todos</option>
              <option value="COMPLETAS">Notas completas</option>
              <option value="APROBADOS">Aprobados</option>
              <option value="REPROBADOS">Reprobados</option>
            </select>
          </label>
          <button type="button" className="ghost-button" onClick={() => void loadCourseStudents()} disabled={selectedPeriods.length === 0 || loadingStudents}>
            {loadingStudents ? 'Actualizando...' : 'Actualizar'}
          </button>
        </div>

        <div className="admin-grades-table-wrap">
          <table className="admin-grades-table admin-grades-students-table">
            <thead>
              <tr>
                <th>Estudiante</th>
                <th>Cédula</th>
                <th>Carrera</th>
                <th>Período</th>
                <th>Tipo</th>
                <th>Notas registradas</th>
                <th>Promedio final</th>
                <th>Resultado</th>
                <th>Registro</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {visibleStudents.map((student) => (
                <tr key={`${student.codigo_estud}-${student.codigo_periodo || ''}-${student.cod_anio_basica || ''}-${student.num_matricula || ''}-${student.num_grupo || ''}`}>
                  <td><strong>{student.nombre_estudiante || 'Sin nombre'}</strong><small>Código {student.codigo_estud || '-'}</small></td>
                  <td>{student.cedula || '-'}</td>
                  <td><strong>{student.nombre_carrera || 'No informada'}</strong><small>Código {student.cod_anio_basica || '-'}</small></td>
                  <td><strong>{student.detalle_periodo || student.codigo_periodo || '-'}</strong><small>Código {student.codigo_periodo || '-'}</small></td>
                  <td><span className="admin-grades-type">{student.es_homologacion ? 'H' : 'R'}</span></td>
                  <td>{gradeDetail(student)}</td>
                  <td><strong>{score(student.promedio_final)}</strong><small>Mínima 7,00</small></td>
                  <td><span className={`admin-grades-badge ${student.estado_nota === 'APROBADO' ? 'is-ok' : student.estado_nota === 'REPROBADO' ? 'is-danger' : 'is-warning'}`}>{resultLabel(student.estado_nota)}</span></td>
                  <td><span className={`admin-grades-badge ${student.estado_registro === 'COMPLETA' ? 'is-ok' : student.estado_registro === 'EN_PROCESO' ? 'is-warning' : 'is-danger'}`}>{registrationLabel(student.estado_registro)}</span></td>
                  <td>
                    {canEditGrades ? (
                      <button
                        type="button"
                        className="ghost-button admin-grades-row-action"
                        onClick={() => openGradeEditor(student)}
                        disabled={!canUpdateStudentGrade(student)}
                        title={canUpdateStudentGrade(student) ? 'Modificar o registrar las calificaciones de este estudiante' : 'La matrícula no contiene una clave completa'}
                      >
                        Actualizar
                      </button>
                    ) : (
                      <span className="admin-grades-readonly">Solo consulta</span>
                    )}
                  </td>
                </tr>
              ))}
              {!loadingStudents && selectedPeriods.length > 0 && visibleStudents.length === 0 && (
                <tr><td colSpan={10} className="admin-grades-empty">No existen estudiantes para el filtro seleccionado.</td></tr>
              )}
              {selectedPeriods.length === 0 && (
                <tr><td colSpan={10} className="admin-grades-empty">Seleccione docente, asignatura y hasta tres períodos para cargar las calificaciones.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="admin-grades-pagination">
          <span>{filteredStudents.length} resultado(s) · Página {studentPage} de {studentPages}</span>
          <div>
            <button type="button" className="ghost-button" onClick={() => setStudentPage((page) => Math.max(1, page - 1))} disabled={studentPage === 1}>Anterior</button>
            <button type="button" className="ghost-button" onClick={() => setStudentPage((page) => Math.min(studentPages, page + 1))} disabled={studentPage === studentPages}>Siguiente</button>
          </div>
        </div>
        </section>
      )}

      {editingStudent && gradeDraft && (
        <div className="matricula-modal-overlay" role="presentation" onClick={closeGradeEditor}>
          <article
            className="matricula-modal admin-grades-edit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-grade-edit-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3 id="admin-grade-edit-title">Actualizar calificaciones</h3>
                <span>{editingStudent.nombre_estudiante || 'Estudiante sin nombre'}</span>
              </div>
              <button type="button" className="matricula-modal-close" onClick={closeGradeEditor} disabled={gradeSaving}>Cerrar</button>
            </div>

            <div className="admin-grades-edit-summary">
              <div><span>Estudiante</span><strong>{editingStudent.nombre_estudiante || '-'}</strong><small>{editingStudent.cedula || `Código ${editingStudent.codigo_estud || '-'}`}</small></div>
              <div><span>Asignatura</span><strong>{editingStudent.nombre_materia || selectedSubject?.name || '-'}</strong><small>Código {editingStudent.cod_materia || editingStudent.codigo_materia || '-'}</small></div>
              <div><span>Período y carrera</span><strong>{editingStudent.detalle_periodo || editingStudent.codigo_periodo || '-'}</strong><small>{editingStudent.nombre_carrera || 'Carrera no informada'}</small></div>
              <div><span>Tipo</span><strong>{editingStudent.es_homologacion ? 'Homologación' : 'Regular'}</strong><small>Nota mínima 7,00</small></div>
            </div>

            <form
              className="reporteria-grade-editor admin-grades-edit-form"
              onSubmit={(event) => {
                event.preventDefault()
                void saveStudentGrade()
              }}
            >
              {editingStudent.es_homologacion ? (
                <div className="reporteria-grade-editor__homo">
                  <label>
                    <span>Teoría (40%)</span>
                    <input type="number" min={0} max={10} step="0.01" value={gradeDraft.teoria_homo} onChange={(event) => updateGradeDraft('teoria_homo', event.target.value)} />
                  </label>
                  <label>
                    <span>Práctica (60%)</span>
                    <input type="number" min={0} max={10} step="0.01" value={gradeDraft.practica_homo} onChange={(event) => updateGradeDraft('practica_homo', event.target.value)} />
                  </label>
                </div>
              ) : (
                <div className="reporteria-grade-editor__periods">
                  {regularGradeSections.map((section, sectionIndex) => (
                    <fieldset key={section.title}>
                      <legend>{section.title}</legend>
                      <label>
                        <span>Tareas (30%)</span>
                        <input type="number" min={0} max={10} step="0.01" value={gradeDraft[section.task]} onChange={(event) => updateGradeDraft(section.task, event.target.value)} />
                      </label>
                      <label>
                        <span>Proyectos (30%)</span>
                        <input type="number" min={0} max={10} step="0.01" value={gradeDraft[section.project]} onChange={(event) => updateGradeDraft(section.project, event.target.value)} />
                      </label>
                      <label>
                        <span>Examen (40%)</span>
                        <input type="number" min={0} max={10} step="0.01" value={gradeDraft[section.exam]} onChange={(event) => updateGradeDraft(section.exam, event.target.value)} />
                      </label>
                      <div className="reporteria-grade-editor__calculated">
                        <span>Promedio calculado</span>
                        <strong>{score(gradePreviewCalculation?.partials[sectionIndex] ?? null)}</strong>
                      </div>
                    </fieldset>
                  ))}
                </div>
              )}

              <div className={`reporteria-grade-editor__common ${editingStudent.es_homologacion ? 'admin-grades-edit-common--homo' : ''}`}>
                <label>
                  <span>Asistencia (%)</span>
                  <input type="number" min={0} max={100} step="0.01" value={gradeDraft.asistencia} onChange={(event) => updateGradeDraft('asistencia', event.target.value)} />
                </label>
                {!editingStudent.es_homologacion && (
                  <label>
                    <span>Recuperación</span>
                    <input type="number" min={0} max={10} step="0.01" value={gradeDraft.recuperacion} onChange={(event) => updateGradeDraft('recuperacion', event.target.value)} />
                    <small className="reporteria-grade-editor__help">Reemplaza una sola nota puntual mínima entre los tres parciales y luego recalcula el promedio.</small>
                  </label>
                )}
                <div className="reporteria-grade-editor__final">
                  <span>Promedio final</span>
                  <strong>{score(gradePreviewFinal)}</strong>
                  <small>{gradePreviewFinal === null ? 'Pendiente' : gradePreviewFinal >= 7 ? 'Aprobado' : 'Reprobado'}</small>
                </div>
              </div>

              {gradeSaveError && <p className="admin-grades-alert" role="alert">{gradeSaveError}</p>}
              <div className="reporteria-grade-editor__actions">
                <button type="button" className="ghost-button" onClick={closeGradeEditor} disabled={gradeSaving}>Cancelar</button>
                <button type="submit" className="primary-action" disabled={gradeSaving}>
                  {gradeSaving ? 'Guardando...' : 'Guardar calificaciones'}
                </button>
              </div>
            </form>
          </article>
        </div>
      )}
    </div>
  )
}
