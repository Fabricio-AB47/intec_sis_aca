import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  fetchAcademicEnrollmentCatalog,
  fetchAcademicTeacherEnrollments,
  fetchAcademicTeacherParallels,
  fetchAcademicTeacherParallelStudents,
  fetchAcademicTeacherUniqueSubjects,
  saveAcademicTeacherMultiSubjectEnrollment,
  searchAcademicEnrollmentTeachers,
} from '../../lib/api'
import type {
  AcademicPeriodOption,
  AcademicTeacherEnrollment,
  AcademicTeacherParallelOption,
  AcademicTeacherOption,
  AcademicTeacherStudentItem,
  AcademicTeacherUniqueSubjectOption,
} from '../../types/app'

type MatriculaDocenteViewProps = {
  displayName: string
}

type TeacherEnrollmentMode = 'MASIVA' | 'INDIVIDUAL'

type TeacherStudentWithSubject = AcademicTeacherStudentItem & {
  selected_subject_code: string
  selected_subject_name: string
  selected_subject_codes?: string[]
  selected_subject_names?: string[]
}

type ConfirmDialogState = {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  resolve: (confirmed: boolean) => void
}

function toNumber(value: string, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function valueOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function isActiveTeacher(teacher: AcademicTeacherOption): boolean {
  return String(teacher.estado || '').trim().toUpperCase() === 'A'
}

function teacherIdentityKey(teacher: AcademicTeacherOption): string {
  const document = String(teacher.cedula || '')
    .trim()
    .toLocaleLowerCase('es')
    .replace(/[^a-z0-9]/g, '')
  if (document) return `document:${document}`

  const email = String(teacher.correo || teacher.login || '')
    .trim()
    .toLocaleLowerCase('es')
  return email ? `email:${email}` : `code:${teacher.codigo_doc}`
}

function uniqueTeachers(items: AcademicTeacherOption[]): AcademicTeacherOption[] {
  const seen = new Set<string>()
  return items.filter((teacher) => {
    const identity = teacherIdentityKey(teacher)
    if (!isActiveTeacher(teacher) || !teacher.codigo_doc || seen.has(identity)) {
      return false
    }
    seen.add(identity)
    return true
  })
}

function subjectCareerCodes(subject: AcademicTeacherUniqueSubjectOption | null): string[] {
  return (subject?.carreras || []).map((career) => career.cod_anio_basica).filter(Boolean)
}

function subjectCareerNames(subject: AcademicTeacherUniqueSubjectOption | null): string {
  return (subject?.carreras || []).map((career) => career.nombre_carrera || career.cod_anio_basica).filter(Boolean).join(', ')
}

function subjectLevels(subject: AcademicTeacherUniqueSubjectOption | null): string[] {
  const levels = subject?.niveles?.length ? subject.niveles : subject?.semestre ? [subject.semestre] : []
  return [...new Set(levels.map((level) => String(level)).filter(Boolean))].sort((left, right) => toNumber(left) - toNumber(right))
}

export function MatriculaDocenteView({ displayName }: Readonly<MatriculaDocenteViewProps>) {
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [periods, setPeriods] = useState<AcademicPeriodOption[]>([])
  const [journeyOptions, setJourneyOptions] = useState<Array<{ value: string; label: string }>>([
    { value: '1', label: 'Matutina' },
    { value: '2', label: 'Nocturna' },
  ])
  const [catalogParallelOptions, setCatalogParallelOptions] = useState<AcademicTeacherParallelOption[]>([])
  const [subjectLevelOptions, setSubjectLevelOptions] = useState<string[]>(['1', '2', '3', '4'])
  const [selectedPeriods, setSelectedPeriods] = useState<string[]>([])
  const [periodCandidate, setPeriodCandidate] = useState('')

  const [teacherQuery, setTeacherQuery] = useState('')
  const [teacherSearchLoading, setTeacherSearchLoading] = useState(false)
  const [teacherSearchError, setTeacherSearchError] = useState('')
  const [teacherOptions, setTeacherOptions] = useState<AcademicTeacherOption[]>([])
  const [selectedTeacherCode, setSelectedTeacherCode] = useState('')
  const [selectedTeacherRecord, setSelectedTeacherRecord] = useState<AcademicTeacherOption | null>(null)
  const [pendingTeacherCode, setPendingTeacherCode] = useState('')
  const [teacherSelectorOpen, setTeacherSelectorOpen] = useState(false)

  const [subjectQuery, setSubjectQuery] = useState('')
  const [subjectOptions, setSubjectOptions] = useState<AcademicTeacherUniqueSubjectOption[]>([])
  const [subjectLoading, setSubjectLoading] = useState(false)
  const [subjectError, setSubjectError] = useState('')
  const [selectedSubjects, setSelectedSubjects] = useState<AcademicTeacherUniqueSubjectOption[]>([])
  const [selectedSubjectLevel, setSelectedSubjectLevel] = useState('')

  const [parallel, setParallel] = useState('')
  const [parallelOptions, setParallelOptions] = useState<AcademicTeacherParallelOption[]>([])
  const [parallelOptionsLoading, setParallelOptionsLoading] = useState(false)
  const [parallelOptionsError, setParallelOptionsError] = useState('')
  const [teacherJourney, setTeacherJourney] = useState('1')

  const [teacherEnrollments, setTeacherEnrollments] = useState<AcademicTeacherEnrollment[]>([])
  const [teacherEnrollmentsLoading, setTeacherEnrollmentsLoading] = useState(false)
  const [teacherActionError, setTeacherActionError] = useState('')
  const [teacherActionMessage, setTeacherActionMessage] = useState('')
  const [teacherSaveLoading, setTeacherSaveLoading] = useState(false)

  const [teacherStudents, setTeacherStudents] = useState<TeacherStudentWithSubject[]>([])
  const [teacherStudentsLoading, setTeacherStudentsLoading] = useState(false)
  const [teacherStudentsError, setTeacherStudentsError] = useState('')
  const [teacherEnrollmentMode, setTeacherEnrollmentMode] = useState<TeacherEnrollmentMode>('MASIVA')
  const [selectedStudentCodes, setSelectedStudentCodes] = useState<string[]>([])
  const [teacherStudentQuery, setTeacherStudentQuery] = useState('')
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null)

  const selectedPeriod = selectedPeriods[0] || ''
  const selectedPeriodsKey = selectedPeriods.join('|')
  const selectedPeriodNames = selectedPeriods.map((code) => {
    const period = periods.find((item) => item.codigo_periodo === code)
    return period?.detalle_periodo || code
  })
  const selectedTeacher =
    selectedTeacherRecord?.codigo_doc === selectedTeacherCode
      ? selectedTeacherRecord
      : teacherOptions.find((teacher) => teacher.codigo_doc === selectedTeacherCode)
  const selectedSubjectCodes = useMemo(() => selectedSubjects.map((subject) => subject.cod_materia), [selectedSubjects])
  const selectedSubjectsKey = selectedSubjectCodes.join('|')
  const selectedSubjectNames = useMemo(
    () => selectedSubjects.map((subject) => subject.nombre_materia || subject.cod_materia).join(', '),
    [selectedSubjects]
  )
  const selectedCareerCodes = useMemo(
    () => [...new Set(selectedSubjects.flatMap((subject) => subjectCareerCodes(subject)))],
    [selectedSubjects]
  )
  const selectedCareerCodesKey = selectedCareerCodes.join('|')
  const selectedCareerNames = useMemo(
    () =>
      [...new Set(selectedSubjects.flatMap((subject) => subjectCareerNames(subject).split(', ')).filter(Boolean))].join(', '),
    [selectedSubjects]
  )
  const selectedParallelOption = parallelOptions.find((item) => item.paralelo === parallel)
  const enrollmentSummary = useMemo(() => {
    const teacherCodes = new Set(teacherEnrollments.map((item) => item.codigo_doc).filter(Boolean))
    const subjectCodes = new Set(teacherEnrollments.map((item) => item.codigo_materia).filter(Boolean))
    return {
      docentes: teacherCodes.size,
      materias: subjectCodes.size,
      registros: teacherEnrollments.length,
    }
  }, [teacherEnrollments])
  const uniqueTeacherStudents = useMemo(() => {
    const studentsByCode = new Map<string, TeacherStudentWithSubject>()
    teacherStudents.forEach((student) => {
      const key = `${student.codigo_periodo}:${student.codigo_estud}`
      const existing = studentsByCode.get(key)
      if (student.codigo_estud && !existing) {
        studentsByCode.set(key, {
          ...student,
          selected_subject_codes: [student.selected_subject_code],
          selected_subject_names: [student.selected_subject_name],
        })
      } else if (existing) {
        existing.selected_subject_codes = [
          ...new Set([...(existing.selected_subject_codes || []), student.selected_subject_code]),
        ]
        existing.selected_subject_names = [
          ...new Set([...(existing.selected_subject_names || []), student.selected_subject_name]),
        ]
      }
    })
    return [...studentsByCode.values()]
  }, [teacherStudents])
  const filteredTeacherStudents = useMemo(() => {
    const query = teacherStudentQuery.trim().toLocaleLowerCase('es')
    if (!query) return uniqueTeacherStudents
    return uniqueTeacherStudents.filter((student) =>
      [
        student.nombre_estudiante,
        student.cedula,
        student.codigo_estud,
        student.nombre_carrera,
        student.correo_intec,
      ].some((value) => String(value || '').toLocaleLowerCase('es').includes(query))
    )
  }, [teacherStudentQuery, uniqueTeacherStudents])
  const selectedStudentCodeSet = useMemo(() => new Set(selectedStudentCodes), [selectedStudentCodes])
  const allVisibleStudentsSelected =
    filteredTeacherStudents.length > 0 &&
    filteredTeacherStudents.every((student) => selectedStudentCodeSet.has(`${student.codigo_periodo}:${student.codigo_estud}`))

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      setCatalogError('')
      try {
        const payload = await fetchAcademicEnrollmentCatalog()
        if (cancelled) return
        setPeriods(payload.periodos || [])
        const journeys = (payload.jornadas || [])
          .filter((item) => ['1', '2'].includes(String(item.value)))
          .map((item) => ({
            value: String(item.value),
            label: String(item.value) === '1' ? 'Matutina' : 'Nocturna',
          }))
        setJourneyOptions(journeys)
        setTeacherJourney((current) => (journeys.some((item) => item.value === current) ? current : journeys[0]?.value || '1'))
        setCatalogParallelOptions(payload.paralelos || [])
        const levels = [...new Set((payload.niveles_materia || []).filter((level) => level >= 1 && level <= 4))]
          .sort((left, right) => left - right)
          .map(String)
        setSubjectLevelOptions(levels.length ? levels : ['1', '2', '3', '4'])
      } catch (error) {
        if (!cancelled) {
          setCatalogError(handleError(error, 'Error consultando catálogo académico'))
        }
      } finally {
        if (!cancelled) {
          setCatalogLoading(false)
        }
      }
    }

    void loadCatalog()

    return () => {
      cancelled = true
    }
  }, [])

  function teacherLabel(teacher: AcademicTeacherOption): string {
    const name = teacher.descripcion || teacher.login || teacher.codigo_doc
    return `${name}${teacher.cedula ? ` - ${teacher.cedula}` : ''}`
  }

  function clearTeacherMessages() {
    setTeacherActionError('')
    setTeacherActionMessage('')
  }

  function changeTeacherEnrollmentMode(mode: TeacherEnrollmentMode) {
    setTeacherEnrollmentMode(mode)
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    clearTeacherMessages()
  }

  function studentSelectionKey(student: AcademicTeacherStudentItem): string {
    return `${student.codigo_periodo}:${student.codigo_estud}`
  }

  function toggleStudentSelection(student: AcademicTeacherStudentItem) {
    const selectionKey = studentSelectionKey(student)
    setSelectedStudentCodes((current) =>
      current.includes(selectionKey) ? current.filter((code) => code !== selectionKey) : [...current, selectionKey]
    )
    clearTeacherMessages()
  }

  function selectVisibleStudents() {
    const visibleCodes = filteredTeacherStudents.map(studentSelectionKey)
    setSelectedStudentCodes((current) => [...new Set([...current, ...visibleCodes])])
    clearTeacherMessages()
  }

  function clearStudentSelection() {
    setSelectedStudentCodes([])
    clearTeacherMessages()
  }

  function addSelectedPeriod() {
    if (!periodCandidate || selectedPeriods.includes(periodCandidate)) return
    if (selectedPeriods.length >= 3) {
      setTeacherActionError('Puede seleccionar como máximo tres períodos distintos.')
      return
    }
    setSelectedPeriods((current) => [...current, periodCandidate])
    setPeriodCandidate('')
    clearTeacherMessages()
  }

  function removeSelectedPeriod(periodCode: string) {
    setSelectedPeriods((current) => current.filter((code) => code !== periodCode))
    setSelectedStudentCodes((current) => current.filter((key) => !key.startsWith(`${periodCode}:`)))
    clearTeacherMessages()
  }

  function clearParallelOptions() {
    setParallel('')
    setParallelOptions([])
    setParallelOptionsError('')
  }

  function clearSelectedTeacher() {
    setSelectedTeacherCode('')
    setSelectedTeacherRecord(null)
    setPendingTeacherCode('')
    setTeacherQuery('')
    setTeacherStudents([])
    setTeacherStudentsError('')
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    clearTeacherMessages()
  }

  function selectTeacher(code: string) {
    setSelectedTeacherCode(code)
    setPendingTeacherCode(code)
    const teacher = teacherOptions.find((item) => item.codigo_doc === code)
    if (teacher) {
      setSelectedTeacherRecord(teacher)
      setTeacherQuery(teacherLabel(teacher))
    }
    setTeacherStudents([])
    setTeacherStudentsError('')
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    clearTeacherMessages()
  }

  function openTeacherSelector() {
    setPendingTeacherCode(selectedTeacherCode)
    setTeacherQuery('')
    setTeacherSelectorOpen(true)
    void loadTeacherOptions('')
  }

  function confirmTeacherSelection() {
    if (!pendingTeacherCode) {
      setTeacherSearchError('Marca un docente para continuar.')
      return
    }
    selectTeacher(pendingTeacherCode)
    setTeacherSelectorOpen(false)
  }

  function toggleSubject(subject: AcademicTeacherUniqueSubjectOption) {
    const alreadySelected = selectedSubjectCodes.includes(subject.cod_materia)
    if (!alreadySelected && selectedSubjects.length >= 3) {
      setSubjectError('Puede seleccionar como máximo tres materias.')
      return
    }
    setSelectedSubjects((current) =>
      alreadySelected
        ? current.filter((item) => item.cod_materia !== subject.cod_materia)
        : [...current, subject]
    )
    const levels = subjectLevels(subject)
    setSelectedSubjectLevel((current) => (current && levels.includes(current) ? current : levels[0] || current))
    setSubjectError('')
    setParallelOptionsError('')
    setTeacherEnrollments([])
    setTeacherStudents([])
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    clearTeacherMessages()
  }

  function clearSelectedSubjects() {
    setSelectedSubjects([])
    setSubjectQuery('')
    clearParallelOptions()
    setTeacherEnrollments([])
    setTeacherStudents([])
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    clearTeacherMessages()
  }

  function requestConfirm(title: string, message: string) {
    return new Promise<boolean>((resolve) => {
      setConfirmDialog({
        title,
        message,
        confirmLabel: 'Aceptar',
        cancelLabel: 'Cancelar',
        resolve,
      })
    })
  }

  function closeConfirmDialog(confirmed: boolean) {
    if (!confirmDialog) return
    confirmDialog.resolve(confirmed)
    setConfirmDialog(null)
  }

  async function loadTeacherOptions(queryValue: string = teacherQuery) {
    const query = queryValue.trim()
    if (query.length === 1) {
      setTeacherSearchError('Ingrese al menos 2 caracteres para filtrar docente.')
      return
    }
    setTeacherSearchLoading(true)
    setTeacherSearchError('')
    setTeacherActionMessage('')
    try {
      const payload = await searchAcademicEnrollmentTeachers(query, query ? 200 : 1000, true)
      const items = uniqueTeachers(payload.items || [])
      setTeacherOptions(items)
      setPendingTeacherCode((current) => (items.some((teacher) => teacher.codigo_doc === current) ? current : ''))
      if (items.length === 0) {
        setTeacherSearchError(query ? 'No se encontraron docentes para la búsqueda.' : 'No hay docentes para listar.')
      }
    } catch (error) {
      setTeacherSearchError(handleError(error, 'Error buscando docentes'))
      setTeacherOptions([])
      setPendingTeacherCode('')
    } finally {
      setTeacherSearchLoading(false)
    }
  }

  async function searchTeachers() {
    await loadTeacherOptions()
  }

  const loadSubjectOptions = useCallback(async (queryValue: string, periodCode: string, subjectLevel: string) => {
    if (!periodCode) {
      setSubjectError('Seleccione primero el período.')
      return
    }
    setSubjectLoading(true)
    setSubjectError('')
    try {
      const payload = await fetchAcademicTeacherUniqueSubjects({
        codigoPeriodo: periodCode,
        buscar: queryValue.trim(),
        semestre: subjectLevel,
        limite: 150,
      })
      const items = payload.items || []
      setSubjectOptions(items)
      if (items.length === 0) {
        setSubjectError(queryValue.trim() ? 'No hay materias para ese filtro.' : 'No hay materias matriculadas en el período seleccionado.')
      }
    } catch (error) {
      setSubjectOptions([])
      setSubjectError(handleError(error, 'Error consultando materias únicas'))
    } finally {
      setSubjectLoading(false)
    }
  }, [])

  const loadParallelOptions = useCallback(async () => {
    if (!selectedPeriod || selectedSubjects.length === 0) {
      setParallel('')
      setParallelOptions([])
      setParallelOptionsError('')
      return
    }
    setParallelOptionsLoading(true)
    setParallelOptionsError('')
    try {
      const payloads = await Promise.all(
        selectedSubjects.map((subject) =>
          fetchAcademicTeacherParallels(
            subjectCareerCodes(subject),
            selectedPeriod,
            subject.cod_materia,
            selectedSubjectLevel
          )
        )
      )
      const optionsByParallel = new Map(
        catalogParallelOptions.map((item) => [String(item.paralelo).trim().toUpperCase(), item])
      )
      for (const item of payloads.flatMap((payload) => payload.items || [])) {
        const key = String(item.paralelo).trim().toUpperCase()
        const existing = optionsByParallel.get(key)
        optionsByParallel.set(key, {
          ...existing,
          ...item,
          total_estudiantes: Math.max(existing?.total_estudiantes || 0, item.total_estudiantes || 0),
          total_materias: (existing?.total_materias || 0) + (item.total_materias || 0),
        })
      }
      const items = [...optionsByParallel.values()].sort((left, right) =>
        String(left.paralelo).localeCompare(String(right.paralelo))
      )
      setParallelOptions(items)
      setParallel((current) => (items.some((item) => item.paralelo === current) ? current : items[0]?.paralelo || ''))
    } catch (error) {
      setParallelOptions([])
      setParallel('')
      setParallelOptionsError(handleError(error, 'Error consultando paralelos matriculados'))
    } finally {
      setParallelOptionsLoading(false)
    }
  }, [catalogParallelOptions, selectedPeriod, selectedSubjectLevel, selectedSubjects])

  const loadTeacherEnrollments = useCallback(async () => {
    if (selectedPeriods.length === 0 || selectedSubjects.length === 0) {
      setTeacherEnrollments([])
      return
    }
    setTeacherEnrollmentsLoading(true)
    setTeacherActionError('')
    try {
      const payloads = await Promise.all(
        selectedSubjects.flatMap((subject) =>
          selectedPeriods.map((periodCode) =>
            fetchAcademicTeacherEnrollments(
              subjectCareerCodes(subject),
              periodCode,
              subject.cod_materia,
              parallel.trim().toUpperCase() || '',
              selectedSubjectLevel
            )
          )
        )
      )
      setTeacherEnrollments(
        payloads
          .flatMap((payload) => payload.items || [])
          .filter(isActiveTeacher)
      )
    } catch (error) {
      setTeacherActionError(handleError(error, 'Error consultando docentes matriculados'))
      setTeacherEnrollments([])
    } finally {
      setTeacherEnrollmentsLoading(false)
    }
  }, [parallel, selectedPeriods, selectedSubjectLevel, selectedSubjects])

  const loadTeacherStudents = useCallback(async () => {
    if (selectedPeriods.length === 0 || selectedSubjects.length === 0 || !parallel) {
      setTeacherStudents([])
      setTeacherStudentsError('Seleccione período, entre una y tres materias, y paralelo para ver estudiantes.')
      return
    }
    setTeacherStudentsLoading(true)
    setTeacherStudentsError('')
    try {
      const payloads = await Promise.all(
        selectedSubjects.map(async (subject) => {
          const payload = await fetchAcademicTeacherParallelStudents(
            selectedPeriods,
            subject.cod_materia,
            parallel.trim().toUpperCase(),
            subjectCareerCodes(subject),
            selectedSubjectLevel
          )
          return (payload.items || []).map((student) => ({
            ...student,
            selected_subject_code: subject.cod_materia,
            selected_subject_name: subject.nombre_materia || subject.cod_materia,
          }))
        })
      )
      const items = payloads.flat()
      setTeacherStudents(items)
      const availableCodes = new Set(items.map((student) => `${student.codigo_periodo}:${student.codigo_estud}`))
      setSelectedStudentCodes((current) => current.filter((code) => availableCodes.has(code)))
    } catch (error) {
      setTeacherStudents([])
      setTeacherStudentsError(handleError(error, 'Error consultando estudiantes del paralelo'))
    } finally {
      setTeacherStudentsLoading(false)
    }
  }, [parallel, selectedPeriods, selectedSubjectLevel, selectedSubjects])

  useEffect(() => {
    setSelectedSubjects([])
    setSelectedSubjectLevel('')
    setSubjectQuery('')
    setParallel('')
    setParallelOptions([])
    setTeacherEnrollments([])
    setTeacherStudents([])
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
    setTeacherActionError('')
    setTeacherActionMessage('')
    if (selectedPeriod) {
      void loadSubjectOptions('', selectedPeriod, '')
    } else {
      setSubjectOptions([])
    }
  }, [loadSubjectOptions, selectedPeriod])

  useEffect(() => {
    if (!selectedPeriod || selectedSubjects.length === 0) {
      setParallel('')
      setParallelOptions([])
      setParallelOptionsError('')
      return
    }
    void loadParallelOptions()
  }, [loadParallelOptions, selectedCareerCodesKey, selectedPeriod, selectedSubjects.length, selectedSubjectsKey, selectedSubjectLevel])

  useEffect(() => {
    if (!selectedPeriod || selectedSubjects.length === 0) {
      setTeacherEnrollments([])
      return
    }
    void loadTeacherEnrollments()
  }, [loadTeacherEnrollments, parallel, selectedCareerCodesKey, selectedPeriod, selectedPeriodsKey, selectedSubjects.length, selectedSubjectsKey, selectedSubjectLevel])

  useEffect(() => {
    if (!selectedPeriod || selectedSubjects.length === 0 || !parallel) {
      setTeacherStudents([])
      setTeacherStudentsError('')
      return
    }
    void loadTeacherStudents()
  }, [loadTeacherStudents, parallel, selectedCareerCodesKey, selectedPeriod, selectedPeriodsKey, selectedSubjects.length, selectedSubjectsKey, selectedSubjectLevel])

  useEffect(() => {
    setSelectedStudentCodes([])
    setTeacherStudentQuery('')
  }, [parallel, selectedCareerCodesKey, selectedPeriod, selectedPeriodsKey, selectedSubjectsKey, selectedSubjectLevel])

  async function saveTeacherEnrollment() {
    if (!selectedTeacherCode || selectedPeriods.length === 0 || selectedSubjects.length === 0) {
      setTeacherActionError('Seleccione docente, entre uno y tres períodos, y entre una y tres materias.')
      return
    }
    if (!parallel.trim()) {
      setTeacherActionError('Seleccione un paralelo con estudiantes matriculados.')
      return
    }
    if (teacherEnrollmentMode === 'INDIVIDUAL' && selectedStudentCodes.length === 0) {
      setTeacherActionError('Seleccione al menos un estudiante para la matrícula docente individual.')
      return
    }
    const subjectsWithoutStudents: string[] = []
    const subjectPayloads = selectedSubjects.map((subject) => {
      const subjectRows = teacherStudents.filter((student) => student.selected_subject_code === subject.cod_materia)
      const periodos = selectedPeriods.flatMap((periodCode) => {
        const periodRows = subjectRows.filter((student) => student.codigo_periodo === periodCode)
        if (periodRows.length === 0) return []
        const studentCodes =
          teacherEnrollmentMode === 'INDIVIDUAL'
            ? [
                ...new Set(
                  periodRows
                    .filter((student) => selectedStudentCodeSet.has(studentSelectionKey(student)))
                    .map((student) => Number(student.codigo_estud))
                    .filter((code) => Number.isFinite(code) && code > 0)
                ),
              ]
            : []
        if (teacherEnrollmentMode === 'INDIVIDUAL' && studentCodes.length === 0) return []
        return [
          {
            codigo_periodo: Number(periodCode),
            paralelo: parallel.trim().toUpperCase(),
            codigos_estudiantes: studentCodes,
          },
        ]
      })
      if (periodos.length === 0) {
        subjectsWithoutStudents.push(subject.nombre_materia || subject.cod_materia)
      }
      return {
        cod_materia: subject.cod_materia,
        periodos,
        semestre: selectedSubjectLevel ? Number(selectedSubjectLevel) : null,
      }
    })
    if (subjectsWithoutStudents.length > 0) {
      setTeacherActionError(
        teacherEnrollmentMode === 'INDIVIDUAL'
          ? `Seleccione estudiantes matriculados en cada materia: ${subjectsWithoutStudents.join(', ')}.`
          : `No existen estudiantes para guardar en: ${subjectsWithoutStudents.join(', ')}.`
      )
      return
    }
    const assignmentDescription =
      teacherEnrollmentMode === 'INDIVIDUAL'
        ? `${selectedStudentCodes.length} matrícula(s) estudiantil(es) seleccionada(s)`
        : `todos los ${uniqueTeacherStudents.length} registro(s) estudiantil(es) de los períodos`
    const confirmed = await requestConfirm(
      teacherEnrollmentMode === 'INDIVIDUAL' ? 'Asignar estudiantes' : 'Matrícula docente masiva',
      `¿Desea asignar ${assignmentDescription} a ${selectedTeacher?.descripcion || selectedTeacher?.login || selectedTeacherCode} en ${selectedSubjects.length} materia(s): ${selectedSubjectNames}, para ${selectedPeriodNames.join(', ')}, paralelo ${parallel}?`
    )
    if (!confirmed) return

    setTeacherSaveLoading(true)
    setTeacherActionError('')
    setTeacherActionMessage('')
    try {
      const response = await saveAcademicTeacherMultiSubjectEnrollment({
        codigo_doc: Number(selectedTeacherCode),
        materias: subjectPayloads,
        cod_jornada: toNumber(teacherJourney, 1),
        estado_moodle_doc: 0,
        modo_asignacion: teacherEnrollmentMode,
      })
      const inserted = response.inserted_count ?? (response.action === 'INSERTADA' ? 1 : 0)
      const existing = response.existing_count ?? (response.action === 'EXISTENTE' ? 1 : 0)
      const linked = response.students_linked ?? 0
      if (response.ok === false) {
        setTeacherActionError(
          `${response.message || 'La matrícula docente ya existe.'} Estudiantes vinculados: ${linked}.`
        )
      } else {
        setTeacherActionMessage(
          teacherEnrollmentMode === 'INDIVIDUAL'
            ? `Asignación individual guardada para ${selectedSubjects.length} materia(s). ${linked} vínculo(s) de estudiantes procesado(s).`
            : `Matrícula docente masiva guardada para ${selectedSubjects.length} materia(s). Insertadas: ${inserted}; existentes: ${existing}; vínculos procesados: ${linked}.`
        )
      }
      if (teacherEnrollmentMode === 'INDIVIDUAL' && response.ok !== false) {
        setSelectedStudentCodes([])
      }
      await loadTeacherEnrollments()
      await loadTeacherStudents()
    } catch (error) {
      setTeacherActionError(handleError(error, 'Error guardando matrícula docente'))
    } finally {
      setTeacherSaveLoading(false)
    }
  }

  return (
    <div className="student-dashboard">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Matrícula Docente</p>
          <h1>Matrícula docente</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Registros</span>
          <strong>{teacherEnrollments.length} docentes</strong>
        </div>
      </header>

      <section className="student-grid student-grid--content matricula-docente-grid">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Parametros</span>
              <h2>{selectedSubjectNames || 'Seleccione período, materias y paralelo'}</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadTeacherEnrollments()}
                disabled={teacherEnrollmentsLoading || !selectedPeriod || selectedSubjects.length === 0}
              >
                {teacherEnrollmentsLoading ? 'Cargando...' : 'Actualizar'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={saveTeacherEnrollment}
                disabled={
                  teacherSaveLoading ||
                  !selectedTeacherCode ||
                  !selectedPeriod ||
                  selectedSubjects.length === 0 ||
                  !parallel ||
                  uniqueTeacherStudents.length === 0 ||
                  (teacherEnrollmentMode === 'INDIVIDUAL' && selectedStudentCodes.length === 0)
                }
              >
                {teacherSaveLoading
                  ? 'Guardando...'
                  : teacherEnrollmentMode === 'INDIVIDUAL'
                    ? `Asignar ${selectedStudentCodes.length || ''} estudiante(s)`
                    : 'Matricular curso completo'}
              </button>
            </div>
          </div>

          {catalogError ? <p className="form-error">{catalogError}</p> : null}
          {subjectError ? <p className="form-error">{subjectError}</p> : null}
          {parallelOptionsError ? <p className="form-error">{parallelOptionsError}</p> : null}
          {teacherActionError ? <p className="form-error">{teacherActionError}</p> : null}
          {teacherActionMessage ? <p className="form-success">{teacherActionMessage}</p> : null}
          {!selectedTeacherCode ? <p className="form-success">Seleccione primero el docente para habilitar la matriculación.</p> : null}

          <div className="matricula-docente-main-selector">
            <div className="matricula-docente-loaded">
              <div>
                <span>Docente seleccionado</span>
                <strong>{selectedTeacher ? teacherLabel(selectedTeacher) : 'Sin docente seleccionado'}</strong>
              </div>
              <div className="matricula-docente-active-rule">
                <span>Validación obligatoria</span>
                <strong>Usuario activo (A)</strong>
              </div>
            </div>
            <div className="matricula-acad-actions matricula-docente-school-actions">
              <button type="button" className="primary-action" onClick={openTeacherSelector}>
                Seleccionar docente
              </button>
              <button type="button" className="ghost-button" onClick={clearSelectedTeacher} disabled={!selectedTeacherCode && !teacherQuery}>
                Limpiar docente
              </button>
            </div>
            {teacherSearchError ? <p className="form-error">{teacherSearchError}</p> : null}
          </div>

          <div className="matricula-docente-mode" role="group" aria-label="Modalidad de matrícula docente">
            <button
              type="button"
              className={teacherEnrollmentMode === 'MASIVA' ? 'matricula-docente-mode__option is-active' : 'matricula-docente-mode__option'}
              aria-pressed={teacherEnrollmentMode === 'MASIVA'}
              onClick={() => changeTeacherEnrollmentMode('MASIVA')}
            >
              <strong>Matrícula masiva</strong>
              <span>Asigna al docente todos los estudiantes del curso seleccionado.</span>
            </button>
            <button
              type="button"
              className={teacherEnrollmentMode === 'INDIVIDUAL' ? 'matricula-docente-mode__option is-active' : 'matricula-docente-mode__option'}
              aria-pressed={teacherEnrollmentMode === 'INDIVIDUAL'}
              onClick={() => changeTeacherEnrollmentMode('INDIVIDUAL')}
            >
              <strong>Matrícula individual</strong>
              <span>Permite buscar y seleccionar uno o varios estudiantes.</span>
            </button>
          </div>

          <div className="matricula-acad-form">
            <div className="matricula-docente-period-selector">
              <div className="matricula-docente-period-controls">
                <label>
                  <span>Períodos (máximo 3)</span>
                  <select
                    value={periodCandidate}
                    disabled={catalogLoading || selectedPeriods.length >= 3}
                    onChange={(event) => setPeriodCandidate(event.target.value)}
                  >
                    <option value="">Seleccionar período</option>
                    {periods
                      .filter((period) => !selectedPeriods.includes(period.codigo_periodo))
                      .map((period) => (
                        <option key={period.codigo_periodo} value={period.codigo_periodo}>
                          {period.detalle_periodo} {period.anio ? `(${period.anio})` : ''} - {period.total_matriculados ?? 0}
                        </option>
                      ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={!periodCandidate || selectedPeriods.length >= 3}
                  onClick={addSelectedPeriod}
                >
                  Agregar período
                </button>
              </div>
              <div className="matricula-docente-period-list" aria-live="polite">
                {selectedPeriods.length === 0 ? <span>Seleccione entre uno y tres períodos distintos.</span> : null}
                {selectedPeriods.map((periodCode, index) => {
                  const period = periods.find((item) => item.codigo_periodo === periodCode)
                  return (
                    <div key={periodCode}>
                      <span>{index + 1}</span>
                      <strong>{period?.detalle_periodo || periodCode}</strong>
                      <button type="button" className="ghost-button" onClick={() => removeSelectedPeriod(periodCode)}>
                        Quitar
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
            <label>
              <span>Paralelo</span>
              <select
                value={parallel}
                disabled={parallelOptionsLoading || !selectedPeriod}
                onChange={(event) => setParallel(event.target.value)}
              >
                <option value="">{parallelOptionsLoading ? 'Cargando...' : 'Seleccionar'}</option>
                {parallelOptions.map((item) => (
                  <option key={item.paralelo} value={item.paralelo}>
                    {item.paralelo} - {item.total_estudiantes ? `${item.total_estudiantes} estudiante(s)` : 'sin estudiantes'}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Jornada</span>
              <select
                value={teacherJourney}
                disabled={catalogLoading}
                onChange={(event) => setTeacherJourney(event.target.value)}
              >
                {journeyOptions.map((journey) => (
                  <option key={journey.value} value={journey.value}>
                    {journey.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Nivel materia</span>
              <select
                value={selectedSubjectLevel}
                disabled={!selectedPeriod || catalogLoading}
                onChange={(event) => {
                  const level = event.target.value
                  setSelectedSubjectLevel(level)
                  setSelectedSubjects([])
                  setSubjectQuery('')
                  setSubjectOptions([])
                  setParallel('')
                  setParallelOptions([])
                  setTeacherStudents([])
                  setTeacherEnrollments([])
                  clearTeacherMessages()
                  if (selectedPeriod) {
                    void loadSubjectOptions('', selectedPeriod, level)
                  }
                }}
              >
                <option value="">Seleccionar nivel</option>
                {subjectLevelOptions.map((level) => (
                  <option key={level} value={level}>
                    Nivel {level}
                  </option>
                ))}
              </select>
            </label>
            <div className="matricula-acad-career-picker matricula-docente-subject-picker">
              <span>Materias (máximo 3)</span>
              {!selectedPeriod ? <p>Seleccione primero el período para buscar materias matriculadas.</p> : null}
              <div className="matricula-docente-selector-controls">
                <label>
                  <span>Buscar materia</span>
                  <input
                    value={subjectQuery}
                    placeholder="Código comun, código interno o nombre"
                    disabled={!selectedPeriod}
                    onChange={(event) => setSubjectQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        void loadSubjectOptions(subjectQuery, selectedPeriod, selectedSubjectLevel)
                      }
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => void loadSubjectOptions(subjectQuery, selectedPeriod, selectedSubjectLevel)}
                  disabled={!selectedPeriod || subjectLoading}
                >
                  {subjectLoading ? 'Buscando...' : 'Buscar'}
                </button>
                <button type="button" className="ghost-button" onClick={clearSelectedSubjects} disabled={selectedSubjects.length === 0}>
                  Limpiar
                </button>
              </div>
              {selectedSubjects.length > 0 ? (
                <div className="matricula-acad-preview matricula-docente-teacher-detail">
                  <div>
                    <span>Materias seleccionadas</span>
                    <strong>{selectedSubjects.length} de 3</strong>
                  </div>
                  <div>
                    <span>Nombres</span>
                    <strong>{selectedSubjectNames}</strong>
                  </div>
                  <div>
                    <span>Códigos comunes</span>
                    <strong>{selectedSubjectCodes.join(', ')}</strong>
                  </div>
                  <div>
                    <span>Nivel</span>
                    <strong>{selectedSubjectLevel ? `Nivel ${selectedSubjectLevel}` : '-'}</strong>
                  </div>
                  <div>
                    <span>Carreras vinculadas</span>
                    <strong>{selectedCareerNames || '-'}</strong>
                  </div>
                  <div>
                    <span>Matrículas identificadas</span>
                    <strong>{selectedSubjects.reduce((total, subject) => total + (subject.total_estudiantes || 0), 0)}</strong>
                  </div>
                </div>
              ) : null}
              <div className="matricula-acad-career-options">
                {subjectOptions.map((subject) => {
                  const active = selectedSubjectCodes.includes(subject.cod_materia)
                  const selectionLimitReached = selectedSubjects.length >= 3 && !active
                  return (
                    <button
                      key={subject.cod_materia}
                      type="button"
                      className={`matricula-acad-career-option ${active ? 'matricula-acad-career-option--active matricula-acad-career-option--focus' : ''}`}
                      disabled={!selectedPeriod || selectionLimitReached}
                      aria-pressed={active}
                      title={selectionLimitReached ? 'Puede seleccionar como máximo tres materias.' : undefined}
                      onClick={() => toggleSubject(subject)}
                    >
                      <input type="checkbox" checked={active} readOnly tabIndex={-1} />
                      <strong>{subject.nombre_materia}</strong>
                      <small>
                        {subject.cod_materia} - Nivel {valueOrDash(subject.semestre)} - {subject.total_estudiantes ?? 0} estudiante(s)
                      </small>
                      <small>{subjectCareerNames(subject) || 'Sin carrera vinculada'}</small>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="matricula-acad-context">
            <span>{selectedPeriods.length ? `${selectedPeriods.length} período(s)` : 'Período pendiente'}</span>
            <span>{selectedSubjects.length ? `${selectedSubjects.length} materia(s)` : 'Materias pendientes'}</span>
            <span>Nivel {selectedSubjectLevel || 'pendiente'}</span>
            <span>{selectedCareerCodes.length} carrera(s) vinculada(s)</span>
            <span>
              Paralelo {parallel.trim().toUpperCase() || 'pendiente'}: {selectedParallelOption?.total_estudiantes ?? 0} estudiante(s)
            </span>
          </div>
        </article>

        <aside className="student-card matricula-panel">
          <div className="section-title">
            <div>
              <span>Docente</span>
              <h2>{selectedTeacher?.descripcion || selectedTeacher?.login || 'Sin docente'}</h2>
            </div>
          </div>

          {selectedTeacher ? (
            <div className="matricula-acad-preview matricula-docente-teacher-detail">
              <div>
                <span>Cédula</span>
                <strong>{selectedTeacher.cedula || '-'}</strong>
              </div>
              <div>
                <span>Correo</span>
                <strong>{selectedTeacher.correo || selectedTeacher.correo_personal || '-'}</strong>
              </div>
              <div>
                <span>Teléfono</span>
                <strong>{selectedTeacher.movil || selectedTeacher.telefono || '-'}</strong>
              </div>
              <div>
                <span>Tipo</span>
                <strong>{selectedTeacher.tipo_docente || selectedTeacher.tipo_usuario || '-'}</strong>
              </div>
              <div>
                <span>Unidad</span>
                <strong>{selectedTeacher.unidad_academica || '-'}</strong>
              </div>
              <div>
                <span>Asignaciones</span>
                <strong>{selectedTeacher.total_matriculas_docente ?? 0}</strong>
              </div>
            </div>
          ) : null}
          {!selectedTeacher ? <p className="form-success">Use el botón «Seleccionar docente» para buscar y marcar un único docente.</p> : null}
        </aside>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Listado</span>
              <h2>Docentes matriculados</h2>
            </div>
            <div className="matricula-acad-preview matricula-docente-summary">
              <div>
                <span>Docentes</span>
                <strong>{enrollmentSummary.docentes}</strong>
              </div>
              <div>
                <span>Materias</span>
                <strong>{enrollmentSummary.materias}</strong>
              </div>
              <div>
                <span>Registros</span>
                <strong>{enrollmentSummary.registros}</strong>
              </div>
            </div>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Docente</th>
                  <th>Contacto</th>
                  <th>Tipo</th>
                  <th>Materia</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Paralelo</th>
                  <th>Jornada</th>
                </tr>
              </thead>
              <tbody>
                {teacherEnrollmentsLoading ? (
                  <tr>
                    <td colSpan={8}>Cargando docentes...</td>
                  </tr>
                ) : null}
                {!teacherEnrollmentsLoading && teacherEnrollments.length === 0 ? (
                  <tr>
                    <td colSpan={8}>Sin docentes matriculados para los filtros seleccionados.</td>
                  </tr>
                ) : null}
                {teacherEnrollments.map((item) => (
                  <tr key={`${item.codigo_doc}-${item.codigo_periodo}-${item.codigo_materia}-${item.paralelo}-${item.cod_jornada}`}>
                    <td>
                      <strong>{item.descripcion || item.login || item.codigo_doc}</strong>
                      <span>{item.cedula || '-'}</span>
                    </td>
                    <td>
                      <strong>{item.correo || item.login || '-'}</strong>
                      <span>{item.movil || item.telefono || '-'}</span>
                    </td>
                    <td>{item.tipo_docente || item.tipo_usuario || '-'}</td>
                    <td>{item.nombre_materia || item.codigo_materia || '-'}</td>
                    <td>{item.nombre_carrera || item.cod_anio_basica || '-'}</td>
                    <td>{item.detalle_periodo || item.codigo_periodo || '-'}</td>
                    <td>{item.paralelo || '-'}</td>
                    <td>{valueOrDash(item.cod_jornada)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>{teacherEnrollmentMode === 'INDIVIDUAL' ? 'Selección individual' : 'Curso completo'}</span>
              <h2>
                {teacherEnrollmentMode === 'INDIVIDUAL'
                  ? 'Seleccionar estudiantes para el docente'
                  : 'Estudiantes incluidos en la matrícula masiva'}
              </h2>
            </div>
            <div className="matricula-acad-title-actions">
              <span>{teacherStudentsLoading ? 'Cargando...' : `${uniqueTeacherStudents.length} estudiante(s)`}</span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadTeacherStudents()}
                disabled={!selectedPeriod || selectedSubjects.length === 0 || !parallel || teacherStudentsLoading}
              >
                {teacherStudentsLoading ? 'Actualizando...' : 'Actualizar estudiantes'}
              </button>
            </div>
          </div>
          {teacherStudentsError ? <p className="form-error">{teacherStudentsError}</p> : null}
          <div className="matricula-docente-student-toolbar">
            <label>
              <span>Buscar estudiante</span>
              <input
                value={teacherStudentQuery}
                placeholder="Nombre, cédula, código, correo o carrera"
                onChange={(event) => setTeacherStudentQuery(event.target.value)}
              />
            </label>
            {teacherEnrollmentMode === 'INDIVIDUAL' ? (
              <div className="matricula-docente-student-actions">
                <div className="matricula-docente-selection-count">
                  <span>Seleccionados</span>
                  <strong>{selectedStudentCodes.length}</strong>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={allVisibleStudentsSelected ? clearStudentSelection : selectVisibleStudents}
                  disabled={filteredTeacherStudents.length === 0}
                >
                  {allVisibleStudentsSelected ? 'Limpiar selección' : 'Seleccionar visibles'}
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={saveTeacherEnrollment}
                  disabled={teacherSaveLoading || selectedStudentCodes.length === 0 || !selectedTeacherCode}
                >
                  {teacherSaveLoading ? 'Guardando...' : 'Asignar seleccionados'}
                </button>
              </div>
            ) : (
              <p className="matricula-docente-mass-note">
                Al guardar se asignaran los {uniqueTeacherStudents.length} estudiantes mostrados para este curso.
              </p>
            )}
          </div>
          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  {teacherEnrollmentMode === 'INDIVIDUAL' ? <th className="matricula-docente-select-column">Seleccionar</th> : null}
                  <th>Estudiante</th>
                  <th>Cédula</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Materia</th>
                  <th>Paralelo</th>
                  <th>Matrícula</th>
                  <th>Promedio</th>
                  <th>Asignación actual</th>
                </tr>
              </thead>
              <tbody>
                {teacherStudentsLoading ? (
                  <tr>
                    <td colSpan={teacherEnrollmentMode === 'INDIVIDUAL' ? 10 : 9}>Cargando estudiantes...</td>
                  </tr>
                ) : null}
                {!teacherStudentsLoading && filteredTeacherStudents.length === 0 ? (
                  <tr>
                    <td colSpan={teacherEnrollmentMode === 'INDIVIDUAL' ? 10 : 9}>
                      {teacherStudentQuery.trim()
                        ? 'No hay estudiantes que coincidan con la búsqueda.'
                        : 'Sin estudiantes matriculados para ese período, materia y paralelo.'}
                    </td>
                  </tr>
                ) : null}
                {filteredTeacherStudents.map((student) => (
                  <tr
                    key={`${student.codigo_periodo}-${student.codigo_estud}-${student.codigo_materia}-${student.paralelo}`}
                    className={selectedStudentCodeSet.has(studentSelectionKey(student)) ? 'matricula-docente-student-row--selected' : ''}
                  >
                    {teacherEnrollmentMode === 'INDIVIDUAL' ? (
                      <td className="matricula-docente-select-column">
                        <input
                          type="checkbox"
                          checked={selectedStudentCodeSet.has(studentSelectionKey(student))}
                          aria-label={`Seleccionar ${student.nombre_estudiante || student.codigo_estud}`}
                          onChange={() => toggleStudentSelection(student)}
                        />
                      </td>
                    ) : null}
                    <td>
                      <strong>{student.nombre_estudiante || student.codigo_estud}</strong>
                      <span>{student.correo_intec || student.correo_personal || '-'}</span>
                    </td>
                    <td>{student.cedula || '-'}</td>
                    <td>{student.nombre_carrera || student.cod_anio_basica || '-'}</td>
                    <td>{student.detalle_periodo || student.codigo_periodo || '-'}</td>
                    <td>{student.selected_subject_names?.join(', ') || student.nombre_materia || student.codigo_materia || '-'}</td>
                    <td>{student.paralelo || '-'}</td>
                    <td>{student.num_matricula || '-'}</td>
                    <td>{valueOrDash(student.promedio_final)}</td>
                    <td>
                      <strong>{student.docente_asignado || student.codigo_docente_asignado || 'Sin asignar'}</strong>
                      {student.codigo_docente_asignado === selectedTeacherCode ? <span>Docente seleccionado</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {teacherSelectorOpen ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="teacher-selector-title">
          <article className="matricula-modal matricula-docente-selector-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>Docente</span>
                <h3 id="teacher-selector-title">Seleccionar docente</h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setTeacherSelectorOpen(false)}>
                Cerrar
              </button>
            </div>

            <div className="matricula-docente-selector-controls">
              <label>
                <span>Buscar docente</span>
                <input
                  value={teacherQuery}
                  placeholder="Cédula, correo o nombre"
                  onChange={(event) => setTeacherQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void searchTeachers()
                    }
                  }}
                />
              </label>
              <div className="matricula-docente-active-rule">
                <span>Filtro</span>
                <strong>Solo usuarios activos (A)</strong>
              </div>
              <button type="button" className="ghost-button" onClick={() => void searchTeachers()} disabled={teacherSearchLoading}>
                {teacherSearchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {teacherSearchError ? <p className="form-error">{teacherSearchError}</p> : null}

            <div className="matricula-docente-selector-summary">
              <strong>Listado completo de docentes existentes</strong>
              <span>{teacherSearchLoading ? 'Cargando docentes...' : `${teacherOptions.length} docente(s) cargado(s)`}</span>
            </div>

            <div className="matricula-docente-selector-list">
              {teacherOptions.length === 0 && !teacherSearchLoading ? (
                <div className="matricula-docente-selector-empty">
                  <strong>Sin resultados</strong>
                  <span>No hay docentes para los filtros aplicados.</span>
                </div>
              ) : null}
              {teacherOptions.map((teacher) => {
                const checked = pendingTeacherCode === teacher.codigo_doc
                return (
                  <button
                    key={teacher.codigo_doc}
                    type="button"
                    className={`matricula-acad-teacher-option ${checked ? 'matricula-acad-teacher-option--active' : ''}`}
                    onClick={() => setPendingTeacherCode(checked ? '' : teacher.codigo_doc)}
                  >
                    <label className="matricula-docente-check-row" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => setPendingTeacherCode(checked ? '' : teacher.codigo_doc)}
                      />
                      <strong>{teacher.descripcion || teacher.login || teacher.codigo_doc}</strong>
                    </label>
                    <span>{teacher.cedula || 'Sin cédula'} - {teacher.correo || teacher.login || 'Sin correo'}</span>
                    <span>
                      {teacher.tipo_docente || teacher.tipo_usuario || 'Docente'} - {teacher.total_carreras_docente ?? 0} carrera(s) -{' '}
                      {teacher.total_materias_docente ?? 0} materia(s)
                    </span>
                    <span>{teacher.usuario_validado ? 'Usuario validado' : 'Sin usuario vinculado'}</span>
                  </button>
                )
              })}
            </div>

            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setTeacherSelectorOpen(false)}>
                Cancelar
              </button>
              <button type="button" className="primary-action" onClick={confirmTeacherSelection} disabled={!pendingTeacherCode}>
                Seleccionar docente
              </button>
            </div>
          </article>
        </div>
      ) : null}

      {confirmDialog ? (
        <div className="matricula-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="matricula-docente-confirm-title">
          <div className="matricula-confirm-modal">
            <div>
              <span>Confirmación</span>
              <h2 id="matricula-docente-confirm-title">{confirmDialog.title}</h2>
              <p>{confirmDialog.message}</p>
            </div>
            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => closeConfirmDialog(false)}>
                {confirmDialog.cancelLabel}
              </button>
              <button type="button" className="primary-action" onClick={() => closeConfirmDialog(true)} autoFocus>
                {confirmDialog.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
