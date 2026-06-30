import { useEffect, useMemo, useState } from 'react'

import {
  downloadPortalTeacherComplianceReport,
  downloadPortalTeacherCourseReport,
  fetchPortalTeacherCourses,
  fetchPortalTeacherStudents,
  savePortalTeacherGrades,
} from '../../lib/api'
import type {
  PortalAcademicRecordItem,
  PortalTeacherCourse,
  PortalTeacherGradePayload,
} from '../../types/app'

type PortalDocenteViewProps = {
  displayName: string
  initialMode?: 'courses' | 'compliance'
}

type GradePartial = 'P1' | 'P2' | 'P3'
type CoursePeriodFilter = 'TODOS' | 'R' | 'H'

const GRADE_PARTIAL_OPTIONS: Array<{ value: GradePartial; label: string }> = [
  { value: 'P1', label: 'Primer parcial' },
  { value: 'P2', label: 'Segundo parcial' },
  { value: 'P3', label: 'Tercer parcial' },
]

const COMPLIANCE_EVIDENCE_OPTIONS = [
  { key: 'datos', label: 'Captura estudiantes matriculados' },
  { key: 'pea', label: 'Captura PEA y sílabo firmado' },
  { key: 'aula', label: 'Captura aula virtual y recursos' },
  { key: 'teams', label: 'Captura TEAMS y clases grabadas' },
  { key: 'asistencia', label: 'Captura de asistencias' },
  { key: 'notas', label: 'Captura reporte de notas firmado' },
] as const

type ComplianceEvidenceKey = (typeof COMPLIANCE_EVIDENCE_OPTIONS)[number]['key']

type GradeDraft = {
  teoria_homo: string
  practica_homo: string
  p1_tareas: string
  p1_proyectos: string
  p1_examen: string
  prom_p1: string
  p2_tareas: string
  p2_proyectos: string
  p2_examen: string
  prom_p2: string
  p3_tareas: string
  p3_proyectos: string
  p3_examen: string
  prom_p3: string
  promedio_final: string
  asistencia: string
  recuperacion: string
}

function courseKey(course: PortalTeacherCourse) {
  const periodos = course.codigo_periodos?.length ? course.codigo_periodos.join(',') : course.codigo_periodo
  return [
    periodos,
    course.cod_materia || course.codigo_materia,
    course.paralelo,
    course.cod_jornada,
  ].join('|')
}

function coursePeriodKind(course: PortalTeacherCourse): 'R' | 'H' {
  return isHomologation(course) ? 'H' : 'R'
}

function courseSubjectKey(course: PortalTeacherCourse) {
  const code = (course.cod_materia || course.codigo_materia || '').trim().toUpperCase()
  const name = (course.nombre_materia || '').trim().toUpperCase()
  return `${code}|${name}`
}

function courseSubjectLabel(course: PortalTeacherCourse) {
  const code = course.cod_materia || course.codigo_materia || ''
  return [course.nombre_materia || 'Materia sin nombre', code ? `(${code})` : ''].filter(Boolean).join(' ')
}

function courseJourneyLabel(course: PortalTeacherCourse) {
  return course.jornada || (course.cod_jornada ? `Jornada ${course.cod_jornada}` : 'Jornada pendiente')
}

function courseOptionLabel(course: PortalTeacherCourse) {
  const period = course.detalle_periodos || course.detalle_periodo || course.codigo_periodo || 'Sin período'
  const kind = coursePeriodKind(course) === 'H' ? 'HOMO' : 'REGULAR'
  return `${course.nombre_materia || course.codigo_materia || 'Materia'} - ${period} - Paralelo ${course.paralelo || '-'} - ${courseJourneyLabel(course)} - ${kind}`
}

function studentKey(item: PortalAcademicRecordItem) {
  return [
    item.codigo_estud,
    item.codigo_periodo,
    item.cod_anio_basica,
    item.codigo_materia,
    item.paralelo,
    item.num_matricula,
    item.num_grupo,
  ].join('|')
}

function draftFromItem(item: PortalAcademicRecordItem): GradeDraft {
  return {
    teoria_homo: item.teoria_homo?.toString() || '',
    practica_homo: item.practica_homo?.toString() || '',
    p1_tareas: item.p1_tareas?.toString() || '',
    p1_proyectos: item.p1_proyectos?.toString() || '',
    p1_examen: item.p1_examen?.toString() || '',
    prom_p1: item.prom_p1?.toString() || '',
    p2_tareas: item.p2_tareas?.toString() || '',
    p2_proyectos: item.p2_proyectos?.toString() || '',
    p2_examen: item.p2_examen?.toString() || '',
    prom_p2: item.prom_p2?.toString() || '',
    p3_tareas: item.p3_tareas?.toString() || '',
    p3_proyectos: item.p3_proyectos?.toString() || '',
    p3_examen: item.p3_examen?.toString() || '',
    prom_p3: item.prom_p3?.toString() || '',
    promedio_final: item.promedio_final?.toString() || '',
    asistencia: item.asistencia?.toString() || '',
    recuperacion: item.recuperacion?.toString() || '',
  }
}

function toNumberOrNull(value: string): number | null {
  const normalized = value.trim().replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function numberText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toFixed(2)
}

function hasFinalGrade(item: PortalAcademicRecordItem) {
  return item.promedio_final !== null && item.promedio_final !== undefined && Number.isFinite(Number(item.promedio_final))
}

function isHomologation(
  item?: { tipo_matricula?: string; detalle_periodo?: string; esquema_calificacion?: string; es_homologacion?: boolean } | null
) {
  if (item?.es_homologacion) return true
  const tipo = (item?.tipo_matricula || '').trim().toUpperCase()
  const text = `${item?.tipo_matricula || ''} ${item?.detalle_periodo || ''} ${item?.esquema_calificacion || ''}`.toUpperCase()
  return tipo === 'H' || text.includes('HOMO')
}

function weightedHomologationFinal(teoria: number | null, practica: number | null) {
  if (teoria === null || practica === null) return null
  return Number((teoria * 0.4 + practica * 0.6).toFixed(2))
}

function weightedPartial(tareas: number | null, proyectos: number | null, examen: number | null) {
  if (tareas === null || proyectos === null || examen === null) return null
  return Number((tareas * 0.3 + proyectos * 0.4 + examen * 0.3).toFixed(2))
}

function regularFinal(p1: number | null, p2: number | null, p3: number | null) {
  if (p1 === null || p2 === null || p3 === null) return null
  return Number(((p1 + p2 + p3) / 3).toFixed(2))
}

function regularAverages(draft: GradeDraft) {
  const promP1 = weightedPartial(
    toNumberOrNull(draft.p1_tareas),
    toNumberOrNull(draft.p1_proyectos),
    toNumberOrNull(draft.p1_examen)
  )
  const promP2 = weightedPartial(
    toNumberOrNull(draft.p2_tareas),
    toNumberOrNull(draft.p2_proyectos),
    toNumberOrNull(draft.p2_examen)
  )
  const promP3 = weightedPartial(
    toNumberOrNull(draft.p3_tareas),
    toNumberOrNull(draft.p3_proyectos),
    toNumberOrNull(draft.p3_examen)
  )
  return {
    promP1,
    promP2,
    promP3,
    final: regularFinal(promP1, promP2, promP3),
  }
}

function statusFromFinal(value: number | null) {
  if (value === null) return 'Pendiente'
  return value >= 7 ? 'Aprobado' : 'Reprobado'
}

function safeFilenamePart(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'reporte'
}

function hasGradeUpdates(payload: PortalTeacherGradePayload) {
  return [
    payload.teoria_homo,
    payload.practica_homo,
    payload.p1_tareas,
    payload.p1_proyectos,
    payload.p1_examen,
    payload.prom_p1,
    payload.p2_tareas,
    payload.p2_proyectos,
    payload.p2_examen,
    payload.prom_p2,
    payload.p3_tareas,
    payload.p3_proyectos,
    payload.p3_examen,
    payload.prom_p3,
    payload.promedio,
    payload.asistencia,
    payload.recuperacion,
    payload.promedio_final,
    payload.caprueba,
  ].some((value) => value !== null && value !== undefined && value !== '')
}

function evidencePayload(files: Record<ComplianceEvidenceKey, File[]>) {
  return COMPLIANCE_EVIDENCE_OPTIONS.flatMap((option) =>
    files[option.key].map((file) => ({
      label: `${option.label}: ${file.name}`,
      file,
    }))
  )
}

export function PortalDocenteView({ displayName, initialMode = 'courses' }: Readonly<PortalDocenteViewProps>) {
  const [courses, setCourses] = useState<PortalTeacherCourse[]>([])
  const [selectedCourseKey, setSelectedCourseKey] = useState('')
  const [periodFilter, setPeriodFilter] = useState<CoursePeriodFilter>('TODOS')
  const [subjectFilter, setSubjectFilter] = useState('')
  const [courseSearch, setCourseSearch] = useState('')
  const [targetCourseKey, setTargetCourseKey] = useState('')
  const [students, setStudents] = useState<PortalAcademicRecordItem[]>([])
  const [drafts, setDrafts] = useState<Record<string, GradeDraft>>({})
  const [gradePartial, setGradePartial] = useState<GradePartial>('P1')
  const [loadingCourses, setLoadingCourses] = useState(false)
  const [loadingStudents, setLoadingStudents] = useState(false)
  const [downloadingReport, setDownloadingReport] = useState(false)
  const [previewingReport, setPreviewingReport] = useState(false)
  const [reportPreviewUrl, setReportPreviewUrl] = useState('')
  const [downloadingComplianceReport, setDownloadingComplianceReport] = useState(false)
  const [previewingComplianceReport, setPreviewingComplianceReport] = useState(false)
  const [compliancePreviewUrl, setCompliancePreviewUrl] = useState('')
  const [complianceStartDate, setComplianceStartDate] = useState('')
  const [complianceEndDate, setComplianceEndDate] = useState('')
  const [compliancePhone, setCompliancePhone] = useState('')
  const [complianceUpdates, setComplianceUpdates] = useState('Sin cambios realizados.')
  const [complianceObservations, setComplianceObservations] = useState('')
  const [compliancePeriodCodes, setCompliancePeriodCodes] = useState<string[]>([])
  const [compliancePeriodToAdd, setCompliancePeriodToAdd] = useState('')
  const [complianceStudents, setComplianceStudents] = useState<PortalAcademicRecordItem[]>([])
  const [selectedComplianceStudentCodes, setSelectedComplianceStudentCodes] = useState<string[]>([])
  const [loadingComplianceStudents, setLoadingComplianceStudents] = useState(false)
  const [complianceEvidenceFiles, setComplianceEvidenceFiles] = useState<Record<ComplianceEvidenceKey, File[]>>({
    datos: [],
    pea: [],
    aula: [],
    teams: [],
    asistencia: [],
    notas: [],
  })
  const [savingKey, setSavingKey] = useState('')
  const [gradeScreenOpen, setGradeScreenOpen] = useState(initialMode === 'compliance' ? false : false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const selectedCourse = useMemo(
    () => courses.find((course) => courseKey(course) === selectedCourseKey) || null,
    [courses, selectedCourseKey]
  )
  const subjectOptions = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; count: number; regular: number; homo: number }>()
    for (const course of courses) {
      if (periodFilter !== 'TODOS' && coursePeriodKind(course) !== periodFilter) continue
      const key = courseSubjectKey(course)
      const current = grouped.get(key) || {
        key,
        label: courseSubjectLabel(course),
        count: 0,
        regular: 0,
        homo: 0,
      }
      current.count += 1
      if (coursePeriodKind(course) === 'H') {
        current.homo += 1
      } else {
        current.regular += 1
      }
      grouped.set(key, current)
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [courses, periodFilter])
  const filteredCourses = useMemo(() => {
    const query = courseSearch.trim().toUpperCase()
    return courses.filter((course) => {
      if (periodFilter !== 'TODOS' && coursePeriodKind(course) !== periodFilter) return false
      if (subjectFilter && courseSubjectKey(course) !== subjectFilter) return false
      if (!query) return true
      const searchable = [
        course.nombre_materia,
        course.cod_materia,
        course.codigo_materia,
        course.nombre_carrera,
        course.detalle_periodo,
        course.detalle_periodos,
        course.codigo_periodo,
        course.paralelo,
      ]
        .filter(Boolean)
        .join(' ')
        .toUpperCase()
      return searchable.includes(query)
    })
  }, [courseSearch, courses, periodFilter, subjectFilter])
  const filteredSummary = useMemo(() => {
    return filteredCourses.reduce(
      (summary, course) => {
        if (coursePeriodKind(course) === 'H') summary.homo += 1
        else summary.regular += 1
        summary.students += course.total_estudiantes || 0
        return summary
      },
      { regular: 0, homo: 0, students: 0 }
    )
  }, [filteredCourses])
  const complianceCourseOptions = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; course: PortalTeacherCourse; periods: number }>()
    for (const course of filteredCourses) {
      const key = [courseSubjectKey(course), (course.paralelo || '').trim().toUpperCase(), course.cod_jornada || ''].join('|')
      const periodCount = course.codigo_periodos?.length || (course.codigo_periodo ? 1 : 0)
      const current = grouped.get(key)
      if (current) {
        current.periods += periodCount
        continue
      }
      grouped.set(key, {
        key: courseKey(course),
        label: `${courseSubjectLabel(course)} - Paralelo ${course.paralelo || '-'} - ${courseJourneyLabel(course)}`,
        course,
        periods: periodCount,
      })
    }
    return Array.from(grouped.values()).sort((left, right) => left.label.localeCompare(right.label, 'es'))
  }, [filteredCourses])
  const targetCourse = useMemo(
    () => courses.find((item) => courseKey(item) === targetCourseKey) || complianceCourseOptions[0]?.course || filteredCourses[0] || null,
    [complianceCourseOptions, courses, filteredCourses, targetCourseKey]
  )
  const targetCoursePeriodOptions = useMemo(() => {
    if (!targetCourse) return []
    const selectedSubject = courseSubjectKey(targetCourse)
    const selectedParallel = (targetCourse.paralelo || '').trim().toUpperCase()
    const options = new Map<string, { code: string; label: string }>()
    for (const course of courses) {
      if (courseSubjectKey(course) !== selectedSubject) continue
      if ((course.paralelo || '').trim().toUpperCase() !== selectedParallel) continue
      const codes = course.codigo_periodos?.length
        ? course.codigo_periodos
        : course.codigo_periodo
          ? [course.codigo_periodo]
          : []
      const details = (course.detalle_periodos || course.detalle_periodo || '')
        .split('/')
        .map((item) => item.trim())
        .filter(Boolean)
      for (const [index, code] of codes.entries()) {
        if (!code || options.has(code)) continue
        options.set(code, {
          code,
          label: details[index] || course.detalle_periodo || code,
        })
      }
    }
    return Array.from(options.values()).sort((left, right) => right.label.localeCompare(left.label, 'es'))
  }, [courses, targetCourse])
  const availableCompliancePeriodOptions = useMemo(
    () => targetCoursePeriodOptions.filter((option) => !compliancePeriodCodes.includes(option.code)),
    [compliancePeriodCodes, targetCoursePeriodOptions]
  )
  const courseUsesHomologation = useMemo(
    () => students.some((item) => isHomologation(item)) || isHomologation(selectedCourse),
    [selectedCourse, students]
  )
  const gradeTableColumnCount = courseUsesHomologation ? 6 : gradePartial === 'P3' ? 10 : 8

  async function loadCourses() {
    setLoadingCourses(true)
    setError('')
    try {
      const payload = await fetchPortalTeacherCourses()
      const items = payload.items || []
      setCourses(items)
      const firstCourse = items[0]
      if (firstCourse) {
        setSelectedCourseKey(courseKey(firstCourse))
        setTargetCourseKey(courseKey(firstCourse))
        setGradeScreenOpen(false)
        setStudents([])
        setDrafts({})
      } else {
        setGradeScreenOpen(false)
        setTargetCourseKey('')
        setStudents([])
        setDrafts({})
      }
    } catch (apiError) {
      setCourses([])
      setStudents([])
      setDrafts({})
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron consultar las materias asignadas')
    } finally {
      setLoadingCourses(false)
    }
  }

  async function loadStudents(course: PortalTeacherCourse | null = selectedCourse) {
    const periodos = course?.codigo_periodos?.length ? course.codigo_periodos : course?.codigo_periodo ? [course.codigo_periodo] : []
    const subjectCode = course?.cod_materia || course?.codigo_materia || ''
    if (!periodos.length || !subjectCode || !course?.paralelo) {
      setStudents([])
      setDrafts({})
      return
    }
    setLoadingStudents(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchPortalTeacherStudents({
        codigoPeriodos: periodos,
        codigoMateria: subjectCode,
        paralelo: course.paralelo,
      })
      const items = payload.items || []
      setStudents(items)
      setDrafts(Object.fromEntries(items.map((item) => [studentKey(item), draftFromItem(item)])))
    } catch (apiError) {
      setStudents([])
      setDrafts({})
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron consultar los estudiantes del curso')
    } finally {
      setLoadingStudents(false)
    }
  }

  function selectCourse(course: PortalTeacherCourse) {
    setSelectedCourseKey(courseKey(course))
    setTargetCourseKey(courseKey(course))
    setGradePartial('P1')
    setGradeScreenOpen(true)
    void loadStudents(course)
  }

  function openTargetCourse() {
    if (targetCourse) {
      selectCourse(targetCourse)
    }
  }

  async function loadComplianceStudents(course: PortalTeacherCourse | null = targetCourse) {
    const subjectCode = course?.cod_materia || course?.codigo_materia || ''
    const periodos = compliancePeriodCodes.length
      ? compliancePeriodCodes
      : course?.codigo_periodos?.length
        ? course.codigo_periodos
        : course?.codigo_periodo
          ? [course.codigo_periodo]
          : []
    if (periodos.length > 4) {
      setError('Seleccione máximo 4 periodos para generar el informe.')
      return
    }
    if (!course || !periodos.length || !subjectCode || !course.paralelo) {
      setComplianceStudents([])
      setSelectedComplianceStudentCodes([])
      setError('Seleccione una materia con periodo y paralelo para cargar estudiantes del informe.')
      return
    }
    setLoadingComplianceStudents(true)
    setError('')
    setMessage('')
    try {
      const allItems: PortalAcademicRecordItem[] = []
      for (let index = 0; index < periodos.length; index += 2) {
        const chunk = periodos.slice(index, index + 2)
        const payload = await fetchPortalTeacherStudents({
          codigoPeriodos: chunk,
          codigoMateria: subjectCode,
          paralelo: course.paralelo,
        })
        allItems.push(...(payload.items || []))
      }
      const unique = new Map<string, PortalAcademicRecordItem>()
      for (const item of allItems) {
        unique.set(studentKey(item), item)
      }
      const items = Array.from(unique.values()).filter(hasFinalGrade).sort((left, right) =>
        (left.nombre_estudiante || '').localeCompare(right.nombre_estudiante || '', 'es', { sensitivity: 'base' })
      )
      setComplianceStudents(items)
      setSelectedComplianceStudentCodes(Array.from(new Set(items.map((item) => String(item.codigo_estud)).filter(Boolean))))
    } catch (apiError) {
      setComplianceStudents([])
      setSelectedComplianceStudentCodes([])
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron consultar estudiantes para el informe')
    } finally {
      setLoadingComplianceStudents(false)
    }
  }

  function clearCourseFilters() {
    setPeriodFilter('TODOS')
    setSubjectFilter('')
    setCourseSearch('')
    const firstCourse = courses[0]
    setTargetCourseKey(firstCourse ? courseKey(firstCourse) : '')
  }

  function backToCourses() {
    setGradeScreenOpen(false)
    setMessage('')
    setError('')
  }

  function updateDraft(item: PortalAcademicRecordItem, field: keyof GradeDraft, value: string) {
    const key = studentKey(item)
    setDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] || draftFromItem(item)),
        [field]: value,
      },
    }))
  }

  function buildGradePayload(item: PortalAcademicRecordItem) {
    const key = studentKey(item)
    const draft = drafts[key] || draftFromItem(item)
    const homo = isHomologation(item) || isHomologation(selectedCourse)
    const teoriaHomo = toNumberOrNull(draft.teoria_homo)
    const practicaHomo = toNumberOrNull(draft.practica_homo)
    const regular = regularAverages(draft)
    const promedioFinal = homo
      ? weightedHomologationFinal(teoriaHomo, practicaHomo)
      : regular.final
    const payload: PortalTeacherGradePayload = {
      codigo_estud: Number(item.codigo_estud),
      cod_anio_basica: Number(item.cod_anio_basica),
      codigo_periodo: Number(item.codigo_periodo),
      codigo_materia: Number(item.codigo_materia),
      paralelo: item.paralelo || '',
      num_matricula: item.num_matricula ? Number(item.num_matricula) : null,
      num_grupo: item.num_grupo ?? null,
      teoria_homo: homo ? teoriaHomo : null,
      practica_homo: homo ? practicaHomo : null,
      p1_tareas: homo ? null : toNumberOrNull(draft.p1_tareas),
      p1_proyectos: homo ? null : toNumberOrNull(draft.p1_proyectos),
      p1_examen: homo ? null : toNumberOrNull(draft.p1_examen),
      prom_p1: homo ? null : regular.promP1,
      p2_tareas: homo ? null : toNumberOrNull(draft.p2_tareas),
      p2_proyectos: homo ? null : toNumberOrNull(draft.p2_proyectos),
      p2_examen: homo ? null : toNumberOrNull(draft.p2_examen),
      prom_p2: homo ? null : regular.promP2,
      p3_tareas: homo ? null : toNumberOrNull(draft.p3_tareas),
      p3_proyectos: homo ? null : toNumberOrNull(draft.p3_proyectos),
      p3_examen: homo ? null : toNumberOrNull(draft.p3_examen),
      prom_p3: homo ? null : regular.promP3,
      promedio: promedioFinal,
      promedio_final: promedioFinal,
      asistencia: toNumberOrNull(draft.asistencia),
      recuperacion: toNumberOrNull(draft.recuperacion),
      caprueba: promedioFinal === null ? null : promedioFinal >= 7 ? 'A' : 'R',
    }
    return { payload, promedioFinal }
  }

  async function saveAllGrades() {
    if (students.length === 0) return
    setSavingKey('all')
    setError('')
    setMessage('')
    try {
      let saved = 0
      for (const item of students) {
        const { payload } = buildGradePayload(item)
        if (!hasGradeUpdates(payload)) continue
        await savePortalTeacherGrades(payload)
        saved += 1
      }
      setMessage(
        saved > 0
          ? `Calificaciones actualizadas para ${saved} estudiante(s).`
          : 'No hay calificaciones nuevas para guardar.'
      )
      await loadStudents(selectedCourse)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron guardar las notas')
    } finally {
      setSavingKey('')
    }
  }

  function reportRequestParams(course: PortalTeacherCourse | null = selectedCourse, selectedPeriodos: string[] = []) {
    if (!course) return
    const periodos = selectedPeriodos.length
      ? selectedPeriodos
      : course.codigo_periodos?.length
      ? course.codigo_periodos
      : course.codigo_periodo
        ? [course.codigo_periodo]
        : []
    const subjectCode = course.cod_materia || course.codigo_materia || ''
    if (!periodos.length || !subjectCode || !course.paralelo) {
      setError('Seleccione una materia con periodo y paralelo para descargar el reporte.')
      return
    }
    return {
      periodos,
      subjectCode,
      paralelo: course.paralelo,
    }
  }

  async function buildCourseReportBlob() {
    const params = reportRequestParams()
    if (!params) return null
    return downloadPortalTeacherCourseReport({
      codigoPeriodos: params.periodos,
      codigoMateria: params.subjectCode,
      paralelo: params.paralelo,
    })
  }

  async function buildComplianceReportBlob(course: PortalTeacherCourse | null = selectedCourse) {
    const params = reportRequestParams(course, compliancePeriodCodes)
    if (!params) return null
    if (params.periodos.length > 4) {
      setError('Seleccione máximo 4 periodos para generar el informe.')
      return null
    }
    if (complianceStudents.length === 0) {
      setError('Cargue los estudiantes de los periodos seleccionados antes de generar el informe.')
      return null
    }
    if (selectedComplianceStudentCodes.length === 0) {
      setError('Seleccione al menos un estudiante para anexar calificaciones al informe.')
      return null
    }
    if (complianceEvidenceFiles.notas.length === 0) {
      setError('Debe subir al menos una captura de pantalla del reporte de notas para complementar el documento.')
      return null
    }
    return downloadPortalTeacherComplianceReport({
      codigoPeriodos: params.periodos,
      codigoMateria: params.subjectCode,
      paralelo: params.paralelo,
      codigoEstudiantes: selectedComplianceStudentCodes,
      fechaInicio: complianceStartDate,
      fechaFin: complianceEndDate,
      telefono: compliancePhone,
      actualizaciones: complianceUpdates,
      observaciones: complianceObservations,
      evidencias: evidencePayload(complianceEvidenceFiles),
    })
  }

  async function previewCourseReport() {
    setPreviewingReport(true)
    setError('')
    try {
      const blob = await buildCourseReportBlob()
      if (!blob) return
      const url = window.URL.createObjectURL(blob)
      setReportPreviewUrl(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar la vista previa del reporte')
    } finally {
      setPreviewingReport(false)
    }
  }

  async function downloadCourseReport() {
    if (!selectedCourse) return
    const periodos = selectedCourse.codigo_periodos?.length
      ? selectedCourse.codigo_periodos
      : selectedCourse.codigo_periodo
        ? [selectedCourse.codigo_periodo]
        : []
    const subjectCode = selectedCourse.cod_materia || selectedCourse.codigo_materia || ''
    if (!periodos.length || !subjectCode || !selectedCourse.paralelo) {
      setError('Seleccione una materia con periodo y paralelo para descargar el reporte.')
      return
    }
    setDownloadingReport(true)
    setError('')
    try {
      const blob = await buildCourseReportBlob()
      if (!blob) return
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const subject = safeFilenamePart(selectedCourse.nombre_materia || subjectCode)
      const period = safeFilenamePart(selectedCourse.detalle_periodos || selectedCourse.detalle_periodo || periodos.join('-'))
      link.href = url
      link.download = `notas-docente-${subject}-${period}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el reporte de notas')
    } finally {
      setDownloadingReport(false)
    }
  }

  async function previewComplianceReport(course: PortalTeacherCourse | null = selectedCourse) {
    if (course) {
      setSelectedCourseKey(courseKey(course))
      setTargetCourseKey(courseKey(course))
    }
    setPreviewingComplianceReport(true)
    setError('')
    try {
      const blob = await buildComplianceReportBlob(course)
      if (!blob) return
      const url = window.URL.createObjectURL(blob)
      setCompliancePreviewUrl(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar la vista previa del informe de cumplimiento')
    } finally {
      setPreviewingComplianceReport(false)
    }
  }

  async function downloadComplianceReport(course: PortalTeacherCourse | null = selectedCourse) {
    if (!course) return
    setSelectedCourseKey(courseKey(course))
    setTargetCourseKey(courseKey(course))
    setDownloadingComplianceReport(true)
    setError('')
    try {
      const blob = await buildComplianceReportBlob(course)
      if (!blob) return
      const periodos = course.codigo_periodos?.length
        ? course.codigo_periodos
        : course.codigo_periodo
          ? [course.codigo_periodo]
          : []
      const subjectCode = course.cod_materia || course.codigo_materia || ''
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const subject = safeFilenamePart(course.nombre_materia || subjectCode)
      const period = safeFilenamePart(compliancePeriodCodes.join('-') || course.detalle_periodos || course.detalle_periodo || periodos.join('-'))
      link.href = url
      link.download = `cumplimiento-docente-${subject}-${period}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el informe de cumplimiento')
    } finally {
      setDownloadingComplianceReport(false)
    }
  }

  function closeReportPreview() {
    setReportPreviewUrl('')
  }

  function closeCompliancePreview() {
    setCompliancePreviewUrl('')
  }

  useEffect(() => {
    void loadCourses()
  }, [])

  useEffect(() => {
    if (!reportPreviewUrl) return
    return () => {
      window.URL.revokeObjectURL(reportPreviewUrl)
    }
  }, [reportPreviewUrl])

  useEffect(() => {
    if (!compliancePreviewUrl) return
    return () => {
      window.URL.revokeObjectURL(compliancePreviewUrl)
    }
  }, [compliancePreviewUrl])

  useEffect(() => {
    if (subjectFilter && !subjectOptions.some((option) => option.key === subjectFilter)) {
      setSubjectFilter('')
    }
  }, [subjectFilter, subjectOptions])

  useEffect(() => {
    if (filteredCourses.length === 0) {
      setTargetCourseKey('')
      return
    }
    if (!filteredCourses.some((course) => courseKey(course) === targetCourseKey)) {
      setTargetCourseKey(courseKey(filteredCourses[0]))
    }
  }, [filteredCourses, targetCourseKey])

  useEffect(() => {
    const codes = targetCoursePeriodOptions.map((option) => option.code)
    setCompliancePeriodCodes(codes.slice(0, 1))
    setCompliancePeriodToAdd(codes[1] || codes[0] || '')
    setComplianceStudents([])
    setSelectedComplianceStudentCodes([])
  }, [targetCoursePeriodOptions])

  useEffect(() => {
    if (availableCompliancePeriodOptions.some((option) => option.code === compliancePeriodToAdd)) return
    setCompliancePeriodToAdd(availableCompliancePeriodOptions[0]?.code || '')
  }, [availableCompliancePeriodOptions, compliancePeriodToAdd])

  return (
    <div className="student-dashboard portal-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Portal docente</p>
          <h1>{initialMode === 'compliance' ? 'Informe de cumplimiento docente' : 'Mis cursos y subida de notas'}</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Materias filtradas</span>
          <strong>{filteredCourses.length}</strong>
          <small>{courses.length} asignada(s)</small>
        </div>
      </header>

      <section className="student-grid student-grid--content portal-teacher-grid">
        {!gradeScreenOpen ? (
        <aside className="student-card portal-course-list portal-course-list--full">
          <div className="section-title">
            <div>
              <span>Materias asignadas</span>
              <h2>Seleccione curso</h2>
            </div>
            <button type="button" className="ghost-button" onClick={loadCourses} disabled={loadingCourses}>
              {loadingCourses ? 'Cargando...' : 'Actualizar'}
            </button>
          </div>

          <div className="portal-course-filters">
            <label>
              <span>Tipo de período</span>
              <select
                value={periodFilter}
                onChange={(event) => setPeriodFilter(event.target.value as CoursePeriodFilter)}
              >
                <option value="TODOS">Todos</option>
                <option value="R">Regular</option>
                <option value="H">Homologación</option>
              </select>
            </label>
            <label>
              <span>Materia</span>
              <select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}>
                <option value="">Todas las materias</option>
                {subjectOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label} - {option.count} curso(s)
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Buscar</span>
              <input
                type="search"
                value={courseSearch}
                onChange={(event) => setCourseSearch(event.target.value)}
                placeholder="Materia, carrera, período o paralelo"
              />
            </label>
          </div>

          {initialMode !== 'compliance' ? (
          <div className="portal-course-jump">
            <label>
              <span>Ir directamente a</span>
              <select
                value={targetCourseKey}
                onChange={(event) => setTargetCourseKey(event.target.value)}
                disabled={filteredCourses.length === 0}
              >
                {filteredCourses.map((course) => (
                  <option key={courseKey(course)} value={courseKey(course)}>
                    {courseOptionLabel(course)}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="primary-action" onClick={openTargetCourse} disabled={filteredCourses.length === 0}>
              Ir a materia
            </button>
            <button type="button" className="ghost-button" onClick={clearCourseFilters}>
              Limpiar filtros
            </button>
          </div>
          ) : null}

          {initialMode === 'compliance' ? (
          <div className="portal-compliance-launcher">
            <div className="section-title">
              <div>
                <span>Documento docente</span>
                <h2>Crear informe de cumplimiento</h2>
              </div>
              <strong>
                {targetCourse
                  ? `${targetCourse.nombre_materia || targetCourse.codigo_materia || 'Materia'} · Paralelo ${targetCourse.paralelo || '-'}`
                  : 'Seleccione una materia'}
              </strong>
            </div>
            <p>
              El documento se genera con el formato configurado por administración y toma docente, materia,
              carrera, periodo, paralelo, estudiantes y notas desde el sistema.
            </p>
            <div className="portal-compliance-panel portal-compliance-panel--launcher">
              <label className="portal-compliance-course-select">
                <span>Materia del informe</span>
                <select
                  value={targetCourseKey}
                  onChange={(event) => {
                    setTargetCourseKey(event.target.value)
                    setComplianceStudents([])
                    setSelectedComplianceStudentCodes([])
                  }}
                  disabled={complianceCourseOptions.length === 0}
                >
                  {complianceCourseOptions.map((option) => (
                    <option key={option.key} value={option.key}>
                      {option.label} - {option.periods} periodo(s)
                    </option>
                  ))}
                </select>
              </label>
              <fieldset className="portal-compliance-periods">
                <legend>Periodos del informe</legend>
                <div className="portal-compliance-period-picker">
                  <select
                    value={compliancePeriodToAdd}
                    onChange={(event) => setCompliancePeriodToAdd(event.target.value)}
                    disabled={availableCompliancePeriodOptions.length === 0 || compliancePeriodCodes.length >= 4}
                  >
                    <option value="">Seleccione periodo</option>
                    {availableCompliancePeriodOptions.map((option) => (
                      <option key={option.code} value={option.code}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => {
                      if (!compliancePeriodToAdd || compliancePeriodCodes.includes(compliancePeriodToAdd) || compliancePeriodCodes.length >= 4) return
                      const next = [...compliancePeriodCodes, compliancePeriodToAdd].slice(0, 4)
                      setCompliancePeriodCodes(next)
                      setCompliancePeriodToAdd(availableCompliancePeriodOptions.find((option) => option.code !== compliancePeriodToAdd)?.code || '')
                      setComplianceStudents([])
                      setSelectedComplianceStudentCodes([])
                    }}
                    disabled={!compliancePeriodToAdd || compliancePeriodCodes.length >= 4}
                  >
                    Agregar periodo
                  </button>
                </div>
                <div className="portal-compliance-selected-periods">
                  {compliancePeriodCodes.map((code) => {
                    const option = targetCoursePeriodOptions.find((item) => item.code === code)
                    return (
                      <span key={code}>
                        {option?.label || code}
                        <button
                          type="button"
                          onClick={() => {
                            const next = compliancePeriodCodes.filter((item) => item !== code)
                            setCompliancePeriodCodes(next)
                            setCompliancePeriodToAdd(code)
                            setComplianceStudents([])
                            setSelectedComplianceStudentCodes([])
                          }}
                          aria-label={`Quitar periodo ${option?.label || code}`}
                        >
                          x
                        </button>
                      </span>
                    )
                  })}
                </div>
                {targetCoursePeriodOptions.length === 0 ? (
                  <p>No hay periodos disponibles para esta materia.</p>
                ) : null}
              </fieldset>
              <div className="portal-compliance-period-note">
                Puede seleccionar hasta 4 periodos para cargar estudiantes y anexar calificaciones.
              </div>
              <label>
                <span>Fecha inicio</span>
                <input type="date" value={complianceStartDate} onChange={(event) => setComplianceStartDate(event.target.value)} />
              </label>
              <label>
                <span>Fecha fin</span>
                <input type="date" value={complianceEndDate} onChange={(event) => setComplianceEndDate(event.target.value)} />
              </label>
              <label>
                <span>Teléfono contacto</span>
                <input value={compliancePhone} onChange={(event) => setCompliancePhone(event.target.value)} placeholder="Ej. 09XXXXXXXX" />
              </label>
              <label>
                <span>Actualización del sílabo</span>
                <textarea value={complianceUpdates} onChange={(event) => setComplianceUpdates(event.target.value)} />
              </label>
              <label>
                <span>Observaciones TEAMS</span>
                <textarea value={complianceObservations} onChange={(event) => setComplianceObservations(event.target.value)} placeholder="Detalle opcional para el informe" />
              </label>
            </div>
            <div className="portal-compliance-evidence">
              <div className="section-title">
                <div>
                  <span>Capturas de pantalla</span>
                  <h2>Evidencias del informe</h2>
                </div>
                <strong>{evidencePayload(complianceEvidenceFiles).length} archivo(s)</strong>
              </div>
              <div className="portal-compliance-evidence-grid">
                {COMPLIANCE_EVIDENCE_OPTIONS.map((option) => (
                  <label key={option.key}>
                    <span>{option.label}{option.key === 'notas' ? ' *' : ''}</span>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={(event) => {
                        const selectedFiles = Array.from(event.target.files || [])
                        setComplianceEvidenceFiles((current) => ({
                          ...current,
                          [option.key]: [...current[option.key], ...selectedFiles],
                        }))
                        event.target.value = ''
                      }}
                    />
                    {complianceEvidenceFiles[option.key].length > 0 ? (
                      <ul className="portal-compliance-evidence-files">
                        {complianceEvidenceFiles[option.key].map((file, fileIndex) => (
                          <li key={`${file.name}-${file.lastModified}-${fileIndex}`}>
                            <small>{file.name}</small>
                            <button
                              type="button"
                              onClick={() => {
                                setComplianceEvidenceFiles((current) => ({
                                  ...current,
                                  [option.key]: current[option.key].filter((_, index) => index !== fileIndex),
                                }))
                              }}
                              aria-label={`Quitar ${file.name}`}
                            >
                              Quitar
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <small>Sin capturas seleccionadas</small>
                    )}
                  </label>
                ))}
              </div>
            </div>
            <div className="portal-compliance-students">
              <div className="section-title">
                <div>
                  <span>Estudiantes para anexo de notas</span>
                  <h2>{complianceStudents.length} calificado(s)</h2>
                </div>
                <div className="portal-compliance-actions">
                  <button type="button" className="ghost-button" onClick={() => void loadComplianceStudents(targetCourse)} disabled={loadingComplianceStudents || !targetCourse || compliancePeriodCodes.length === 0}>
                    {loadingComplianceStudents ? 'Cargando...' : 'Cargar estudiantes'}
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setSelectedComplianceStudentCodes(Array.from(new Set(complianceStudents.map((item) => String(item.codigo_estud)).filter(Boolean))))} disabled={complianceStudents.length === 0}>
                    Todos
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setSelectedComplianceStudentCodes([])} disabled={complianceStudents.length === 0}>
                    Ninguno
                  </button>
                </div>
              </div>
              {complianceStudents.length > 0 ? (
                <div className="excel-table-wrap portal-compliance-students-wrap">
                  <table className="matricula-table portal-compliance-students-table">
                    <thead>
                      <tr>
                        <th>Incluye</th>
                        <th>Estudiante</th>
                        <th>Cédula</th>
                        <th>Carrera</th>
                        <th>Periodo</th>
                        <th>Final</th>
                      </tr>
                    </thead>
                    <tbody>
                      {complianceStudents.map((item) => {
                        const code = String(item.codigo_estud)
                        return (
                          <tr key={studentKey(item)}>
                            <td>
                              <input
                                type="checkbox"
                                checked={selectedComplianceStudentCodes.includes(code)}
                                onChange={(event) => {
                                  setSelectedComplianceStudentCodes((current) =>
                                    event.target.checked
                                      ? Array.from(new Set([...current, code]))
                                      : current.filter((value) => value !== code)
                                  )
                                }}
                              />
                            </td>
                            <td>{item.nombre_estudiante || item.codigo_estud}</td>
                            <td>{item.cedula || '-'}</td>
                            <td>{item.nombre_carrera || '-'}</td>
                            <td>{item.detalle_periodo || item.codigo_periodo || '-'}</td>
                            <td>{numberText(item.promedio_final)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="form-success">Carga los estudiantes calificados para anexar sus notas al informe.</p>
              )}
            </div>
            <div className="portal-compliance-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => void previewComplianceReport(targetCourse)}
                disabled={previewingComplianceReport || !targetCourse}
              >
                {previewingComplianceReport ? 'Generando vista...' : 'Visualización previa'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void downloadComplianceReport(targetCourse)}
                disabled={downloadingComplianceReport || !targetCourse}
              >
                {downloadingComplianceReport ? 'Generando informe...' : 'Crear y descargar documento'}
              </button>
            </div>
            {error ? <p className="form-error">{error}</p> : null}
            {message ? <p className="form-success">{message}</p> : null}
          </div>
          ) : null}

          {initialMode !== 'compliance' ? (
            <>
              <div className="portal-course-filter-summary">
                <span>{filteredCourses.length} curso(s) visible(s)</span>
                <span>{filteredSummary.regular} regular(es)</span>
                <span>{filteredSummary.homo} homologación</span>
                <span>{filteredSummary.students} estudiante(s)</span>
              </div>

              <div className="portal-course-stack">
                {filteredCourses.map((course) => (
                  <button
                    key={courseKey(course)}
                    type="button"
                    className={`portal-course-button ${courseKey(course) === selectedCourseKey ? 'portal-course-button--active' : ''}`}
                    onClick={() => selectCourse(course)}
                  >
                    <strong>{course.nombre_materia || course.codigo_materia}</strong>
                    <span>{course.nombre_carrera || course.cod_anio_basicas?.join(', ') || '-'}</span>
                    <small>
                      {course.detalle_periodos || course.detalle_periodo || course.codigo_periodo} | Paralelo {course.paralelo || '-'} | {courseJourneyLabel(course)}
                    </small>
                    <small>
                      {course.es_homologacion ? 'HOMO independiente' : `${course.period_count || 1} periodo(s) regular(es)`}
                    </small>
                    <b>{course.total_estudiantes || 0} estudiante(s)</b>
                  </button>
                ))}
                {!loadingCourses && courses.length === 0 ? (
                  <p className="form-success">No hay materias asignadas para este docente.</p>
                ) : null}
                {!loadingCourses && courses.length > 0 && filteredCourses.length === 0 ? (
                  <p className="form-success">No hay cursos para los filtros seleccionados.</p>
                ) : null}
              </div>
            </>
          ) : null}
        </aside>
        ) : null}

        {gradeScreenOpen ? (
        <article className="student-card student-card--wide portal-grade-card portal-grade-card--screen">
          <div className="section-title">
            <div>
              <span>Notas del curso</span>
              <h2>{selectedCourse?.nombre_materia || 'Sin curso seleccionado'}</h2>
            </div>
            <div className="portal-grade-screen-actions">
              {!courseUsesHomologation ? (
                <label className="portal-grade-partial-filter">
                  <span>Filtrar parcial</span>
                  <select value={gradePartial} onChange={(event) => setGradePartial(event.target.value as GradePartial)}>
                    {GRADE_PARTIAL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <span className="portal-grade-partial-note">Ingreso general HOMO</span>
              )}
              <button type="button" className="ghost-button" onClick={backToCourses}>
                Volver a materias
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadStudents(selectedCourse)}
                disabled={loadingStudents || !selectedCourse}
              >
                {loadingStudents ? 'Consultando...' : 'Actualizar estudiantes'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void previewCourseReport()}
                disabled={previewingReport || !selectedCourse}
              >
                {previewingReport ? 'Generando vista...' : 'Vista previa PDF'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void downloadCourseReport()}
                disabled={downloadingReport || !selectedCourse}
              >
                {downloadingReport ? 'Generando PDF...' : 'Descargar PDF'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void saveAllGrades()}
                disabled={savingKey === 'all' || loadingStudents || students.length === 0}
              >
                {savingKey === 'all' ? 'Calificando...' : 'Calificar'}
              </button>
            </div>
          </div>

          {selectedCourse ? (
            <p className="portal-course-context">
              {selectedCourse.nombre_carrera} | {selectedCourse.detalle_periodos || selectedCourse.detalle_periodo} | Paralelo {selectedCourse.paralelo}
            </p>
          ) : null}
          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          <div className="excel-table-wrap portal-table-wrap">
            <table className="matricula-table portal-grade-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Cedula</th>
                  {courseUsesHomologation ? (
                    <>
                      <th>Teoria 40%</th>
                      <th>Practica 60%</th>
                      <th>Final</th>
                      <th>Estado</th>
                    </>
                  ) : (
                    <>
                      {gradePartial === 'P1' ? (
                        <>
                          <th>P1 tareas 30%</th>
                          <th>P1 proyectos 40%</th>
                          <th>P1 examen 30%</th>
                          <th>P1 prom.</th>
                        </>
                      ) : null}
                      {gradePartial === 'P2' ? (
                        <>
                          <th>P2 tareas 30%</th>
                          <th>P2 proyectos 40%</th>
                          <th>P2 examen 30%</th>
                          <th>P2 prom.</th>
                        </>
                      ) : null}
                      {gradePartial === 'P3' ? (
                        <>
                          <th>P3 tareas 30%</th>
                          <th>P3 proyectos 40%</th>
                          <th>P3 examen 30%</th>
                          <th>P3 prom.</th>
                          <th>Final</th>
                          <th>Estado</th>
                        </>
                      ) : null}
                      <th>Asistencia</th>
                      <th>Recup.</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {students.map((item) => {
                  const key = studentKey(item)
                  const draft = drafts[key] || draftFromItem(item)
                  const homo = courseUsesHomologation || isHomologation(item)
                  const teoriaHomo = toNumberOrNull(draft.teoria_homo)
                  const practicaHomo = toNumberOrNull(draft.practica_homo)
                  const calculatedHomoFinal = weightedHomologationFinal(teoriaHomo, practicaHomo)
                  const calculatedRegular = regularAverages(draft)
                  const finalValue = calculatedHomoFinal ?? calculatedRegular.final ?? item.promedio_final ?? null
                  const statusText = statusFromFinal(finalValue)
                  return (
                    <tr key={key}>
                      <td>
                        <strong>{item.nombre_estudiante || item.codigo_estud}</strong>
                        <small>{item.correo_intec || item.correo_personal || ''}</small>
                      </td>
                      <td>{item.cedula || '-'}</td>
                      {homo ? (
                        <>
                          <td>
                            <input
                              className="portal-grade-input"
                              value={draft.teoria_homo}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'teoria_homo', event.target.value)}
                              placeholder={numberText(item.teoria_homo)}
                            />
                          </td>
                          <td>
                            <input
                              className="portal-grade-input"
                              value={draft.practica_homo}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'practica_homo', event.target.value)}
                              placeholder={numberText(item.practica_homo)}
                            />
                          </td>
                        </>
                      ) : (
                        <>
                          {gradePartial === 'P1' ? (
                            <>
                              <td>
                                <input className="portal-grade-input" value={draft.p1_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_tareas', event.target.value)} placeholder={numberText(item.p1_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p1_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_proyectos', event.target.value)} placeholder={numberText(item.p1_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p1_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_examen', event.target.value)} placeholder={numberText(item.p1_examen)} />
                              </td>
                              <td>
                                <span className="portal-grade-calculated">{numberText(calculatedRegular.promP1 ?? item.prom_p1)}</span>
                              </td>
                            </>
                          ) : null}
                          {gradePartial === 'P2' ? (
                            <>
                              <td>
                                <input className="portal-grade-input" value={draft.p2_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_tareas', event.target.value)} placeholder={numberText(item.p2_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p2_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_proyectos', event.target.value)} placeholder={numberText(item.p2_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p2_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_examen', event.target.value)} placeholder={numberText(item.p2_examen)} />
                              </td>
                              <td>
                                <span className="portal-grade-calculated">{numberText(calculatedRegular.promP2 ?? item.prom_p2)}</span>
                              </td>
                            </>
                          ) : null}
                          {gradePartial === 'P3' ? (
                            <>
                              <td>
                                <input className="portal-grade-input" value={draft.p3_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_tareas', event.target.value)} placeholder={numberText(item.p3_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p3_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_proyectos', event.target.value)} placeholder={numberText(item.p3_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" value={draft.p3_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_examen', event.target.value)} placeholder={numberText(item.p3_examen)} />
                              </td>
                              <td>
                                <span className="portal-grade-calculated">{numberText(calculatedRegular.promP3 ?? item.prom_p3)}</span>
                              </td>
                            </>
                          ) : null}
                        </>
                      )}
                      {homo || gradePartial === 'P3' ? (
                        <td>
                          <span className="portal-grade-calculated portal-grade-calculated--final">{numberText(finalValue)}</span>
                        </td>
                      ) : null}
                      {homo || gradePartial === 'P3' ? (
                        <td>
                          <span className={finalValue === null ? 'portal-status portal-status--warning' : finalValue >= 7 ? 'portal-status portal-status--ok' : 'portal-status portal-status--danger'}>
                            {statusText}
                          </span>
                        </td>
                      ) : null}
                      {!homo ? (
                        <>
                          <td>
                            <input
                              className="portal-grade-input"
                              value={draft.asistencia}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'asistencia', event.target.value)}
                              placeholder={numberText(item.asistencia)}
                            />
                          </td>
                          <td>
                            <input
                              className="portal-grade-input"
                              value={draft.recuperacion}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'recuperacion', event.target.value)}
                              placeholder={numberText(item.recuperacion)}
                            />
                          </td>
                        </>
                      ) : null}
                    </tr>
                  )
                })}
                {!loadingStudents && students.length === 0 ? (
                  <tr>
                    <td colSpan={gradeTableColumnCount}>No hay estudiantes para el curso seleccionado.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
        ) : null}
      </section>

      {reportPreviewUrl ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-label="Vista previa del reporte docente">
          <article className="portal-report-preview-modal">
            <header>
              <div>
                <span>Vista previa</span>
                <h2>Reporte de notas docente</h2>
                <p>{selectedCourse?.nombre_materia || 'Materia seleccionada'}</p>
              </div>
              <div className="portal-report-preview-actions">
                <button type="button" className="ghost-button" onClick={() => void downloadCourseReport()} disabled={downloadingReport}>
                  {downloadingReport ? 'Descargando...' : 'Descargar PDF'}
                </button>
                <button type="button" className="primary-action" onClick={closeReportPreview}>
                  Cerrar
                </button>
              </div>
            </header>
            <iframe src={reportPreviewUrl} title="Vista previa del reporte de notas docente" />
          </article>
        </div>
      ) : null}

      {compliancePreviewUrl ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-label="Vista previa del informe de cumplimiento docente">
          <article className="portal-report-preview-modal">
            <header>
              <div>
                <span>Vista previa</span>
                <h2>Informe de cumplimiento docente</h2>
                <p>{selectedCourse?.nombre_materia || 'Materia seleccionada'}</p>
              </div>
              <div className="portal-report-preview-actions">
                <button type="button" className="ghost-button" onClick={() => void downloadComplianceReport()} disabled={downloadingComplianceReport}>
                  {downloadingComplianceReport ? 'Descargando...' : 'Descargar informe'}
                </button>
                <button type="button" className="primary-action" onClick={closeCompliancePreview}>
                  Cerrar
                </button>
              </div>
            </header>
            <iframe src={compliancePreviewUrl} title="Vista previa del informe de cumplimiento docente" />
          </article>
        </div>
      ) : null}
    </div>
  )
}
