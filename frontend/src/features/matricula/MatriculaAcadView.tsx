import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  balanceAcademicEnrollmentParallels,
  fetchAcademicEnrollmentCareers,
  fetchAcademicEnrollmentCohort,
  fetchAcademicEnrollmentCatalog,
  fetchAcademicEnrollmentDetail,
  fetchAcademicEnrollmentPensum,
  previewAcademicEnrollment,
  previewBulkAcademicEnrollment,
  saveAcademicEnrollment,
  saveBulkAcademicEnrollment,
} from '../../lib/api'
import type {
  AcademicBulkEnrollmentPayload,
  AcademicBulkEnrollmentPreviewResponse,
  AcademicCareerOption,
  AcademicEnrollmentCohortResponse,
  AcademicEnrollmentCohortStudent,
  AcademicEnrollmentDetailResponse,
  AcademicEnrollmentPayload,
  AcademicEnrollmentPreviewResponse,
  AcademicEnrollmentSubject,
  AcademicEnrollmentStudent,
  AcademicPeriodOption,
  MatriculaTipo,
  PreinscriptionProcessOption,
} from '../../types/app'

type MatriculaAcadViewProps = {
  displayName: string
}

type ConfirmDialogState = {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  resolve: (confirmed: boolean) => void
}

type BulkPlanGroup = {
  key: string
  careerCode: string
  careerName: string
  levelLabel: string
  sourceLevel: number
  targetLevel: number
  requiredCurrentSubjects: number
  subjectCodes: string[]
  studentCodes: string[]
}

type BulkPreviewItem = NonNullable<AcademicBulkEnrollmentPreviewResponse['items']>[number]

function bulkStudentKey(student: AcademicEnrollmentCohortStudent): string {
  return [
    student.codigo_estud || '',
    student.cod_anio_basica || '',
    student.codigo_periodo || '',
    student.paralelo || '',
    student.num_grupo ?? '',
  ].join('|')
}

function toNumber(value: string, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function valueOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function escapeHtml(value: string | number | null | undefined): string {
  return valueOrDash(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeFilename(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
}

function formatBulkPreviewStatus(item: BulkPreviewItem, ready: boolean): string {
  if (ready) return 'Listo'
  const status = String(item.estado || '').toUpperCase()
  if (status.includes('YA_MATRICULADO')) return 'Ya matriculado'
  if (status.includes('SIN_MATERIAS')) return 'Sin materias'
  if (status.includes('PRERREQUISITO')) return 'Sin prerrequisito'
  if (status.includes('BLOQUEADO')) return 'Bloqueado'
  if (item.motivo) return 'No matriculado'
  return item.estado ? String(item.estado).replace(/_/g, ' ') : 'Sin cambio'
}

function formatBulkBlockSubject(subject: NonNullable<BulkPreviewItem['materias_bloqueadas']>[number]): string {
  const previous = subject.materias_previas?.length ? `Previa: ${subject.materias_previas.join(', ')}` : 'Sin materia previa registrada'
  return `${valueOrDash(subject.codigo_materia)} - ${valueOrDash(subject.motivo)} (${previous})`
}

function downloadTextFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function mergeCohortResponses(responses: AcademicEnrollmentCohortResponse[]): AcademicEnrollmentCohortResponse {
  const itemMap = new Map<string, AcademicEnrollmentCohortStudent>()
  for (const response of responses) {
    for (const student of response.items || []) {
      const key = `${student.codigo_estud}-${student.cod_anio_basica || ''}-${student.codigo_periodo || ''}-${student.paralelo || ''}`
      itemMap.set(key, student)
    }
  }

  const items = [...itemMap.values()].sort((left, right) =>
    `${left.nombre_carrera || ''}${left.paralelo || ''}${left.nombre_estudiante}`.localeCompare(
      `${right.nombre_carrera || ''}${right.paralelo || ''}${right.nombre_estudiante}`
    )
  )
  const careerBalance = new Map<string, { cod_anio_basica?: string; nombre_carrera?: string; total_estudiantes: number }>()
  const parallelBalance = new Map<string, { paralelo?: string; total_estudiantes: number; total_materias: number }>()
  const levelBalance = new Map<string, { nivel?: string; total_estudiantes: number; total_materias: number }>()

  for (const student of items) {
    const careerKey = student.cod_anio_basica || student.nombre_carrera || 'SIN CARRERA'
    const careerBucket = careerBalance.get(careerKey) || {
      cod_anio_basica: student.cod_anio_basica,
      nombre_carrera: student.nombre_carrera || 'SIN CARRERA',
      total_estudiantes: 0,
    }
    careerBucket.total_estudiantes += 1
    careerBalance.set(careerKey, careerBucket)

    const parallelKey = student.paralelo || 'SIN PARALELO'
    const parallelBucket = parallelBalance.get(parallelKey) || {
      paralelo: parallelKey,
      total_estudiantes: 0,
      total_materias: 0,
    }
    parallelBucket.total_estudiantes += 1
    parallelBucket.total_materias += student.materias_actuales || 0
    parallelBalance.set(parallelKey, parallelBucket)

    const levelKey = String(student.nivel_actual || 'SIN NIVEL')
    const levelBucket = levelBalance.get(levelKey) || {
      nivel: levelKey,
      total_estudiantes: 0,
      total_materias: 0,
    }
    levelBucket.total_estudiantes += 1
    levelBucket.total_materias += student.materias_actuales || 0
    levelBalance.set(levelKey, levelBucket)
  }

  return {
    total: items.length,
    items,
    paralelos: [...parallelBalance.values()].sort((left, right) => String(left.paralelo).localeCompare(String(right.paralelo))),
    balance: {
      por_carrera: [...careerBalance.values()].sort((left, right) => String(left.nombre_carrera).localeCompare(String(right.nombre_carrera))),
      por_paralelo: [...parallelBalance.values()].sort((left, right) => String(left.paralelo).localeCompare(String(right.paralelo))),
      por_nivel: [...levelBalance.values()].sort((left, right) => String(left.nivel).localeCompare(String(right.nivel))),
    },
  }
}

function normalizeCohortStudent(student: AcademicEnrollmentCohortStudent): AcademicEnrollmentStudent {
  return {
    codigo_estud: student.codigo_estud,
    cedula: student.cedula,
    cedula_normalizada: student.cedula_normalizada,
    nombre_estudiante: student.nombre_estudiante,
    estado_codigo: student.estado_codigo,
    correo_personal: student.correo_personal,
    correo_intec: student.correo_intec,
    carrera_actual: student.nombre_carrera,
    cod_anio_basica_actual: student.cod_anio_basica,
    periodo_actual: student.codigo_periodo,
    detalle_periodo_actual: student.detalle_periodo,
    materias_actuales: student.materias_actuales,
  }
}

export function MatriculaAcadView({ displayName }: Readonly<MatriculaAcadViewProps>) {
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [careers, setCareers] = useState<AcademicCareerOption[]>([])
  const [periodCareers, setPeriodCareers] = useState<AcademicCareerOption[]>([])
  const [periodCareersLoading, setPeriodCareersLoading] = useState(false)
  const [periodCareersError, setPeriodCareersError] = useState('')
  const [periods, setPeriods] = useState<AcademicPeriodOption[]>([])
  const [journeys, setJourneys] = useState<PreinscriptionProcessOption[]>([])
  const [cohortLoading, setCohortLoading] = useState(false)
  const [cohortError, setCohortError] = useState('')
  const [cohort, setCohort] = useState<AcademicEnrollmentCohortResponse | null>(null)
  const [selectedStudent, setSelectedStudent] = useState<AcademicEnrollmentStudent | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detail, setDetail] = useState<AcademicEnrollmentDetailResponse | null>(null)
  const [careerPensum, setCareerPensum] = useState<AcademicEnrollmentSubject[]>([])
  const [pensumLoading, setPensumLoading] = useState(false)
  const [pensumError, setPensumError] = useState('')
  const [selectedCareer, setSelectedCareer] = useState('')
  const [selectedCareerCodes, setSelectedCareerCodes] = useState<string[]>([])
  const [careerPensums, setCareerPensums] = useState<Record<string, AcademicEnrollmentSubject[]>>({})
  const [sourcePeriod, setSourcePeriod] = useState('')
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [selectedParallelFilter, setSelectedParallelFilter] = useState('')
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([])
  const [selectedSubjectsByCareer, setSelectedSubjectsByCareer] = useState<Record<string, string[]>>({})
  const [bulkScope, setBulkScope] = useState<'TOTAL' | 'PARCIAL'>('PARCIAL')
  const [selectedBulkStudentKeys, setSelectedBulkStudentKeys] = useState<string[]>([])
  const [semesterFilter, setSemesterFilter] = useState('ALL')
  const [parallel, setParallel] = useState('A')
  const [groupNumber, setGroupNumber] = useState('1')
  const [enrollmentType, setEnrollmentType] = useState<MatriculaTipo>('R')
  const [controlMatricula, setControlMatricula] = useState('1')
  const [selectedJourney, setSelectedJourney] = useState('1')
  const [inscripValue, setInscripValue] = useState('0')
  const [matriValue, setMatriValue] = useState('0')
  const [totalValue, setTotalValue] = useState('0')
  const [paymentDate, setPaymentDate] = useState('')
  const [removeUnselected, setRemoveUnselected] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [bulkPreviewLoading, setBulkPreviewLoading] = useState(false)
  const [bulkSaveLoading, setBulkSaveLoading] = useState(false)
  const [parallelBalanceLoading, setParallelBalanceLoading] = useState(false)
  const [balanceActionError, setBalanceActionError] = useState('')
  const [balanceActionMessage, setBalanceActionMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [preview, setPreview] = useState<AcademicEnrollmentPreviewResponse | null>(null)
  const [bulkPreview, setBulkPreview] = useState<AcademicBulkEnrollmentPreviewResponse | null>(null)
  const [bulkPreviewModalOpen, setBulkPreviewModalOpen] = useState(false)
  const [bulkBlockDetail, setBulkBlockDetail] = useState<BulkPreviewItem | null>(null)
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null)
  const [fichaStudent, setFichaStudent] = useState<AcademicEnrollmentStudent | null>(null)
  const [fichaDetail, setFichaDetail] = useState<AcademicEnrollmentDetailResponse | null>(null)
  const [fichaLoading, setFichaLoading] = useState(false)
  const [fichaError, setFichaError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      setCatalogError('')
      try {
        const payload = await fetchAcademicEnrollmentCatalog()
        if (cancelled) return
        setCareers(payload.carreras || [])
        setPeriods(payload.periodos || [])
        setJourneys(payload.jornadas || [])
        setSelectedJourney((current) => {
          if (current && payload.jornadas?.some((journey) => journey.value === current)) return current
          return payload.jornadas?.[0]?.value || current || '1'
        })
      } catch (error) {
        if (cancelled) return
        setCatalogError(handleError(error, 'Error consultando catalogo academico'))
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

  useEffect(() => {
    let cancelled = false

    async function loadPensum() {
      if (!selectedCareer) {
        setCareerPensum([])
        setPensumError('')
        return
      }
      setPensumLoading(true)
      setPensumError('')
      try {
        const payload = await fetchAcademicEnrollmentPensum(selectedCareer)
        if (cancelled) return
        setCareerPensum(payload.items || [])
        setCareerPensums((current) => ({ ...current, [selectedCareer]: payload.items || [] }))
      } catch (error) {
        if (cancelled) return
        setCareerPensum([])
        setPensumError(handleError(error, 'Error consultando pensum de la carrera'))
      } finally {
        if (!cancelled) {
          setPensumLoading(false)
        }
      }
    }

    void loadPensum()

    return () => {
      cancelled = true
    }
  }, [selectedCareer])

  useEffect(() => {
    const loadedKeys = new Set((cohort?.items || []).map((student) => bulkStudentKey(student)))
    setSelectedBulkStudentKeys((current) => current.filter((key) => loadedKeys.has(key)))
  }, [cohort])

  useEffect(() => {
    let cancelled = false

    async function loadSelectedCareerPensums() {
      const missing = selectedCareerCodes.filter((code) => !careerPensums[code])
      if (missing.length === 0) return
      try {
        const entries = await Promise.all(
          missing.map(async (code) => {
            const payload = await fetchAcademicEnrollmentPensum(code)
            return [code, payload.items || []] as const
          })
        )
        if (cancelled) return
        setCareerPensums((current) => {
          const next = { ...current }
          for (const [code, items] of entries) {
            next[code] = items
          }
          return next
        })
      } catch (error) {
        if (!cancelled) {
          setPensumError(handleError(error, 'Error consultando pensum de las carreras seleccionadas'))
        }
      }
    }

    void loadSelectedCareerPensums()

    return () => {
      cancelled = true
    }
  }, [careerPensums, selectedCareerCodes])

  const careerOptions = sourcePeriod ? periodCareers : careers
  const careerLookup = useMemo(() => {
    const values = new Map<string, AcademicCareerOption>()
    for (const career of careers) {
      values.set(career.cod_anio_basica, career)
    }
    for (const career of periodCareers) {
      values.set(career.cod_anio_basica, career)
    }
    return values
  }, [careers, periodCareers])
  const selectedCareerName =
    careerLookup.get(selectedCareer)?.nombre_basica || ''
  const selectedCareerNames = selectedCareerCodes
    .map((code) => careerLookup.get(code)?.nombre_basica)
    .filter(Boolean)
    .join(', ')
  const sourcePeriodName =
    periods.find((period) => period.codigo_periodo === sourcePeriod)?.detalle_periodo || ''
  const selectedPeriodName =
    periods.find((period) => period.codigo_periodo === selectedPeriod)?.detalle_periodo || ''
  const selectedJourneyName =
    journeys.find((journey) => journey.value === selectedJourney)?.label || selectedJourney
  const fichaResolvedStudent = fichaDetail?.student || fichaStudent
  const fichaCabeceras = fichaDetail?.cabeceras || []
  const fichaMateriasActuales = fichaDetail?.materias_actuales || []

  const currentSubjectCodes = useMemo(
    () => new Set((detail?.materias_actuales || []).map((subject) => subject.codigo_materia)),
    [detail]
  )
  const pensumSubjects = detail?.pensum?.length ? detail.pensum : careerPensums[selectedCareer] || careerPensum

  const semesters = useMemo(() => {
    const values = new Set<string>()
    for (const subject of pensumSubjects) {
      if (subject.semestre !== null && subject.semestre !== undefined) {
        values.add(String(subject.semestre))
      }
    }
    return [...values].sort((left, right) => Number(left) - Number(right))
  }, [pensumSubjects])

  const filteredPensum = useMemo(() => {
    const subjects = pensumSubjects
    if (semesterFilter === 'ALL') return subjects
    return subjects.filter((subject) => String(subject.semestre ?? '') === semesterFilter)
  }, [pensumSubjects, semesterFilter])

  const selectedSubjectSet = useMemo(() => new Set(selectedSubjects), [selectedSubjects])
  const cohortStudents = useMemo(() => cohort?.items || [], [cohort?.items])
  const fichaCohortStudent = fichaStudent
    ? cohortStudents.find((student) => student.codigo_estud === fichaStudent.codigo_estud)
    : null
  const parallelOptions = cohort?.paralelos || []
  const bulkCareerCodes = useMemo(
    () => (selectedCareerCodes.length ? selectedCareerCodes : selectedCareer ? [selectedCareer] : []),
    [selectedCareer, selectedCareerCodes],
  )
  const selectedCareerSet = useMemo(() => new Set(bulkCareerCodes), [bulkCareerCodes])
  const selectedBulkStudentSet = useMemo(() => new Set(selectedBulkStudentKeys), [selectedBulkStudentKeys])
  const bulkStudentCount = bulkScope === 'TOTAL' ? cohortStudents.length : selectedBulkStudentKeys.length
  const selectedBulkKey = selectedBulkStudentKeys.join('|')
  const promotionSourceStudents = useMemo(
    () =>
      (bulkScope === 'PARCIAL'
        ? cohortStudents.filter((student) => selectedBulkStudentSet.has(bulkStudentKey(student)))
        : cohortStudents
      ).filter((student) => bulkCareerCodes.length === 0 || selectedCareerSet.has(student.cod_anio_basica || '')),
    [bulkCareerCodes.length, bulkScope, cohortStudents, selectedBulkStudentSet, selectedCareerSet]
  )
  const promotionCurrentLevels = useMemo(() => {
    const values = new Set<number>()
    for (const student of promotionSourceStudents) {
      const level = Number(student.nivel_actual)
      if (Number.isFinite(level) && level > 0) {
        values.add(level)
      }
    }
    return [...values].sort((left, right) => left - right)
  }, [promotionSourceStudents])
  const createPromotionPlanGroups = useCallback((pensumMap: Record<string, AcademicEnrollmentSubject[]>) => {
    const groups = new Map<string, BulkPlanGroup>()
    for (const student of promotionSourceStudents) {
      const careerCode = student.cod_anio_basica || ''
      if (!careerCode) continue
      const level = Number(student.nivel_actual)
      if (!Number.isFinite(level) || level <= 0) continue
      const careerSubjects = pensumMap[careerCode] || []
      const currentLevelSubjects = careerSubjects
        .filter((subject) => Number(subject.semestre) === level)
        .map((subject) => subject.codigo_materia)
        .filter(Boolean)
      const requiredCurrentSubjects = new Set(currentLevelSubjects).size
      if (requiredCurrentSubjects === 0) continue
      const targetLevel = level + 1
      const subjectCodes = careerSubjects
        .filter((subject) => Number(subject.semestre) === targetLevel)
        .map((subject) => subject.codigo_materia)
        .filter(Boolean)
      const normalizedSubjects = [...new Set(subjectCodes)].sort((left, right) => Number(left) - Number(right))
      if (normalizedSubjects.length === 0) continue
      const levelLabel = `Nivel ${targetLevel}`
      const key = `${careerCode}|${levelLabel}|${normalizedSubjects.join(',')}`
      const group = groups.get(key) || {
        key,
        careerCode,
        careerName: careerLookup.get(careerCode)?.nombre_basica || student.nombre_carrera || careerCode,
        levelLabel,
        sourceLevel: level,
        targetLevel,
        requiredCurrentSubjects,
        subjectCodes: normalizedSubjects,
        studentCodes: [],
      }
      group.studentCodes.push(student.codigo_estud)
      groups.set(key, group)
    }
    return [...groups.values()].sort((left, right) =>
      `${left.careerName}${left.levelLabel}`.localeCompare(`${right.careerName}${right.levelLabel}`)
    )
  }, [careerLookup, promotionSourceStudents])

  const promotionPlanGroups = useMemo(() => createPromotionPlanGroups(careerPensums), [careerPensums, createPromotionPlanGroups])
  const autoSubjectMap = useMemo(() => {
    const next: Record<string, string[]> = {}
    for (const group of promotionPlanGroups) {
      const current = new Set(next[group.careerCode] || [])
      for (const code of group.subjectCodes) {
        current.add(code)
      }
      next[group.careerCode] = [...current].sort((left, right) => Number(left) - Number(right))
    }
    return next
  }, [promotionPlanGroups])
  const promotionLevelText =
    promotionSourceStudents.length === 0
      ? 'Sin estudiantes'
      : promotionCurrentLevels.length === 0
        ? 'Sin nivel'
        : promotionCurrentLevels.length > 1
          ? `${promotionCurrentLevels.length} niveles`
          : promotionCurrentLevels[0] >= 4
            ? 'Nivel 4'
            : `Nivel ${promotionCurrentLevels[0] + 1}`
  const promotionMessage =
    promotionSourceStudents.length === 0
      ? ''
      : promotionPlanGroups.length === 0
        ? 'No hay promocion habilitada: revisa que existan materias configuradas en el nivel inmediato superior.'
        : `Plan automatico: ${promotionPlanGroups.length} grupo(s), ${promotionPlanGroups.reduce((total, group) => total + group.studentCodes.length, 0)} estudiante(s), ${promotionPlanGroups.reduce((total, group) => total + group.subjectCodes.length, 0)} materia(s) destino.`
  const englishCareerCode =
    selectedCareerCodes.find((code) => {
      const careerName = careerLookup.get(code)?.nombre_basica || ''
      return code === '12' || careerName.toUpperCase().includes('INGL')
    }) ||
    (selectedCareer === '12' || selectedCareerName.toUpperCase().includes('INGL') ? selectedCareer : '')
  const canBalanceParallels = Boolean(englishCareerCode && sourcePeriod)
  const previewBlockedByPeriod = (preview?.summary?.bloqueadas_por_periodo ?? 0) > 0
  const bulkPreviewReadyStudents = (bulkPreview?.items || []).filter((item) => (item.insertar || 0) > 0)
  const canSaveBulkEnrollment = Boolean(bulkPreview && (bulkPreview.summary?.insertar ?? 0) > 0)
  const canDownloadBulkValidation = Boolean(bulkPreview?.items?.length)

  function closeBulkPreviewModal() {
    setBulkBlockDetail(null)
    setBulkPreviewModalOpen(false)
  }

  function downloadBulkValidationDocument() {
    const rows = bulkPreview?.items || []
    if (rows.length === 0) {
      setActionError('Genera primero la vista previa masiva para descargar la validacion.')
      return
    }

    const generatedAt = new Date()
    const readyRows = rows.filter((item) => (item.insertar || 0) > 0)
    const blockedRows = rows.length - readyRows.length
    const careerLabel = selectedCareerNames || selectedCareerName || 'Carreras seleccionadas'
    const sourcePeriodLabel = sourcePeriodName || sourcePeriod || '-'
    const targetPeriodLabel = selectedPeriodName || selectedPeriod || '-'
    const generatedAtLabel = generatedAt.toLocaleString('es-EC')

    const bodyRows = rows
      .map((item, index) => {
        const ready = (item.insertar || 0) > 0
        const alreadyExists = !ready && ((item.existentes || 0) > 0 || /existe|matriculad/i.test(`${item.estado || ''} ${item.motivo || ''}`))
        const status = ready ? 'MATRICULADO / LISTO' : alreadyExists ? 'NO MATRICULADO - YA EXISTE' : 'NO MATRICULADO'
        const subjects = item.materias_insertar?.length
          ? item.materias_insertar
              .map((subject) => `${valueOrDash(subject.codigo_materia)} - ${valueOrDash(subject.nombre_materia)}`)
              .join('; ')
          : '-'
        const blockedSubjects = item.materias_bloqueadas?.length
          ? item.materias_bloqueadas
              .map((subject) => {
                const previous = subject.materias_previas?.length ? ` Previas: ${subject.materias_previas.join(', ')}` : ''
                return `${valueOrDash(subject.codigo_materia)} - ${valueOrDash(subject.motivo)}${previous}`
              })
              .join('; ')
          : '-'

        return `
          <tr>
            <td>${index + 1}</td>
            <td>${escapeHtml(status)}</td>
            <td>${escapeHtml(item.codigo_estud)}</td>
            <td>${escapeHtml(item.cedula)}</td>
            <td>${escapeHtml(item.nombre_estudiante)}</td>
            <td>${escapeHtml(item.carrera || item.cod_anio_basica)}</td>
            <td>${escapeHtml(sourcePeriodLabel)}</td>
            <td>${escapeHtml(targetPeriodLabel)}</td>
            <td>${escapeHtml(item.nivel_origen)}</td>
            <td>${escapeHtml(item.nivel_destino)}</td>
            <td>${escapeHtml(item.paralelo)}</td>
            <td>${escapeHtml(item.num_grupo)}</td>
            <td>${escapeHtml(item.insertar || 0)}</td>
            <td>${escapeHtml(item.existentes || 0)}</td>
            <td>${escapeHtml(item.bloqueadas_por_prerrequisito || 0)}</td>
            <td>${escapeHtml(item.bloqueadas_por_num_matricula || 0)}</td>
            <td>${escapeHtml(subjects)}</td>
            <td>${escapeHtml(blockedSubjects)}</td>
            <td>${escapeHtml(item.motivo || item.cabecera || item.estado || '-')}</td>
          </tr>
        `
      })
      .join('')

    const html = `<!doctype html>
      <html>
        <head>
          <meta charset="utf-8" />
          <style>
            body { font-family: Arial, sans-serif; color: #1b2340; }
            h1 { font-size: 20px; margin: 0 0 8px; }
            h2 { font-size: 15px; margin: 18px 0 8px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #9aa6bf; padding: 6px; font-size: 12px; vertical-align: top; }
            th { background: #eaf3f6; font-weight: 700; }
            .meta td:first-child { width: 190px; font-weight: 700; background: #f2f6f8; }
          </style>
        </head>
        <body>
          <h1>VALIDACION DE MATRICULA ACADEMICA</h1>
          <table class="meta">
            <tr><td>Fecha de generacion</td><td>${escapeHtml(generatedAtLabel)}</td></tr>
            <tr><td>Periodo inscrito</td><td>${escapeHtml(sourcePeriodLabel)}</td></tr>
            <tr><td>Periodo matricula</td><td>${escapeHtml(targetPeriodLabel)}</td></tr>
            <tr><td>Carrera(s)</td><td>${escapeHtml(careerLabel)}</td></tr>
            <tr><td>Total revisados</td><td>${rows.length}</td></tr>
            <tr><td>Matriculados/listos</td><td>${readyRows.length}</td></tr>
            <tr><td>No matriculados</td><td>${blockedRows}</td></tr>
          </table>

          <h2>Detalle de validacion</h2>
          <table>
            <thead>
              <tr>
                <th>No.</th>
                <th>Resultado</th>
                <th>Codigo estudiante</th>
                <th>Cedula</th>
                <th>Estudiante</th>
                <th>Carrera</th>
                <th>Periodo inscrito</th>
                <th>Periodo matricula</th>
                <th>Nivel origen</th>
                <th>Nivel destino</th>
                <th>Paralelo</th>
                <th>Grupo</th>
                <th>Insertar</th>
                <th>Existentes</th>
                <th>Bloq. prerrequisito</th>
                <th>Bloq. matricula</th>
                <th>Materias a matricular</th>
                <th>Materias bloqueadas</th>
                <th>Observacion</th>
              </tr>
            </thead>
            <tbody>${bodyRows}</tbody>
          </table>
        </body>
      </html>`

    const filenamePeriod = sanitizeFilename(targetPeriodLabel) || 'periodo'
    downloadTextFile(
      html,
      `validacion-matricula-academica-${filenamePeriod}.xls`,
      'application/vnd.ms-excel;charset=utf-8'
    )
    setActionError('')
    setActionMessage('Documento de validacion descargado.')
  }

  async function loadCohort(
    periodCode: string = sourcePeriod,
    careerCode: string | string[] = selectedCareerCodes.length ? selectedCareerCodes : selectedCareer,
    parallelFilter: string = selectedParallelFilter
  ) {
    if (!periodCode) {
      setCohortError('Selecciona un periodo para cargar estudiantes.')
      return
    }
    setCohortLoading(true)
    setCohortError('')
    setBalanceActionError('')
    setActionMessage('')
    setBulkPreview(null)
    try {
      const careerCodes = Array.isArray(careerCode) ? careerCode.filter(Boolean) : careerCode ? [careerCode] : []
      const payload =
        careerCodes.length > 1
          ? mergeCohortResponses(
              await Promise.all(
                careerCodes.map((code) => fetchAcademicEnrollmentCohort(periodCode, code, parallelFilter))
              )
            )
          : await fetchAcademicEnrollmentCohort(periodCode, careerCodes[0] || '', parallelFilter)
      setCohort(payload)
    } catch (error) {
      setCohortError(handleError(error, 'Error consultando estudiantes por periodo'))
      setCohort(null)
    } finally {
      setCohortLoading(false)
    }
  }

  async function loadCareersForPeriod(periodCode: string) {
    setPeriodCareersLoading(true)
    setPeriodCareersError('')
    try {
      const payload = await fetchAcademicEnrollmentCareers(periodCode)
      const items = payload.items || []
      setPeriodCareers(items)
      return items
    } catch (error) {
      setPeriodCareers([])
      setPeriodCareersError(handleError(error, 'Error consultando carreras del periodo inscrito'))
      return []
    } finally {
      setPeriodCareersLoading(false)
    }
  }

  async function changeSourcePeriod(periodCode: string) {
    setSourcePeriod(periodCode)
    setSelectedParallelFilter('')
    setSelectedBulkStudentKeys([])
    setSelectedStudent(null)
    setDetail(null)
    setSelectedSubjects([])
    setPreview(null)
    setBulkPreview(null)
    setActionMessage('')
    setActionError('')
    if (!periodCode) {
      setPeriodCareers([])
      setPeriodCareersError('')
      setSelectedCareer('')
      setSelectedCareerCodes([])
      setCohort(null)
      return
    }

    const nextCareers = await loadCareersForPeriod(periodCode)
    const availableCodes = new Set(nextCareers.map((career) => career.cod_anio_basica))
    const nextSelectedCareers = selectedCareerCodes.filter((code) => availableCodes.has(code))
    if (nextSelectedCareers.length === 0 && nextCareers.length === 1) {
      nextSelectedCareers.push(nextCareers[0].cod_anio_basica)
    }
    const nextCareer = nextSelectedCareers.includes(selectedCareer) ? selectedCareer : nextSelectedCareers[0] || ''
    setSelectedCareerCodes(nextSelectedCareers)
    if (nextCareer !== selectedCareer) {
      setSelectedCareer(nextCareer)
    }
    await loadCohort(periodCode, nextSelectedCareers, '')
  }

  async function selectCareerButton(careerCode: string) {
    const exists = selectedCareerCodes.includes(careerCode)
    const isActive = selectedCareer === careerCode
    const nextCareerCodes = exists && isActive
      ? selectedCareerCodes.filter((code) => code !== careerCode)
      : exists
        ? selectedCareerCodes
        : [...selectedCareerCodes, careerCode]
    const nextCareer = exists && isActive ? nextCareerCodes[0] || '' : careerCode
    setSelectedCareerCodes(nextCareerCodes)
    setSelectedCareer(nextCareer)
    setSelectedSubjects(selectedSubjectsByCareer[nextCareer] || [])
    setSelectedParallelFilter('')
    setSelectedBulkStudentKeys([])
    setSelectedStudent(null)
    setDetail(null)
    setPreview(null)
    setBulkPreview(null)
    if (sourcePeriod) {
      await loadCohort(sourcePeriod, nextCareerCodes, '')
    }
  }

  async function selectAllCareers() {
    const codes = careerOptions.map((career) => career.cod_anio_basica).filter(Boolean)
    setSelectedCareerCodes(codes)
    setSelectedCareer(codes[0] || '')
    setSelectedSubjects(codes[0] ? selectedSubjectsByCareer[codes[0]] || [] : [])
    setSelectedParallelFilter('')
    setSelectedBulkStudentKeys([])
    setSelectedStudent(null)
    setDetail(null)
    setPreview(null)
    setBulkPreview(null)
    if (sourcePeriod) {
      await loadCohort(sourcePeriod, codes, '')
    }
  }

  async function clearCareerSelection() {
    setSelectedCareerCodes([])
    setSelectedCareer('')
    setSelectedSubjects([])
    setSelectedParallelFilter('')
    setSelectedBulkStudentKeys([])
    setSelectedStudent(null)
    setDetail(null)
    setPreview(null)
    setBulkPreview(null)
    if (sourcePeriod) {
      await loadCohort(sourcePeriod, [], '')
    }
  }

  useEffect(() => {
    if (!sourcePeriod || promotionSourceStudents.length === 0) return
    setPreview(null)
    setBulkPreview(null)
    setSelectedSubjectsByCareer(autoSubjectMap)
    setSelectedSubjects(selectedCareer ? autoSubjectMap[selectedCareer] || [] : [])
    setSemesterFilter('ALL')
  }, [
    autoSubjectMap,
    selectedCareer,
    sourcePeriod,
    selectedPeriod,
    bulkScope,
    selectedBulkKey,
    promotionSourceStudents.length,
  ])

  async function loadStudentDetail(
    student: AcademicEnrollmentStudent,
    careerCode: string = selectedCareer,
    periodCode: string = selectedPeriod
  ) {
    setDetailLoading(true)
    setDetailError('')
    setActionError('')
    setActionMessage('')
    setPreview(null)
    try {
      const payload = await fetchAcademicEnrollmentDetail(student.codigo_estud, careerCode, periodCode)
      setDetail(payload)
      const resolvedCareer = careerCode || payload.selected?.cod_anio_basica || student.cod_anio_basica_actual || ''
      const resolvedPeriod = periodCode || payload.selected?.codigo_periodo || student.periodo_actual || ''
      setSelectedCareer(resolvedCareer)
      if (resolvedCareer) {
        setSelectedCareerCodes((current) => (current.includes(resolvedCareer) ? current : [...current, resolvedCareer]))
      }
      setSelectedPeriod(resolvedPeriod)
      const currentCodes = (payload.materias_actuales || []).map((subject) => subject.codigo_materia)
      setSelectedSubjects(currentCodes)
      if (resolvedCareer) {
        setSelectedSubjectsByCareer((current) => ({ ...current, [resolvedCareer]: currentCodes }))
      }
      setSemesterFilter('ALL')
      setParallel('A')
      setGroupNumber('1')
      setEnrollmentType('R')
      setInscripValue('0')
      setMatriValue('0')
      setTotalValue('0')
      setControlMatricula('1')
      setSelectedJourney((current) => (journeys.some((journey) => journey.value === current) ? current : journeys[0]?.value || '1'))
      setPaymentDate('')
      const currentSubject = payload.materias_actuales?.[0]
      if (currentSubject?.paralelo) setParallel(currentSubject.paralelo)
      if (currentSubject?.num_grupo !== null && currentSubject?.num_grupo !== undefined) {
        setGroupNumber(String(currentSubject.num_grupo))
      }
      if (currentSubject?.tipo_matricula === 'R' || currentSubject?.tipo_matricula === 'H' || currentSubject?.tipo_matricula === 'E') {
        setEnrollmentType(currentSubject.tipo_matricula)
      }
      const cabecera = payload.cabeceras?.find(
        (item) => item.cod_anio_basica === resolvedCareer && item.codigo_periodo === resolvedPeriod
      )
      if (cabecera) {
        setInscripValue(String(cabecera.inscrip_valor ?? 0))
        setMatriValue(String(cabecera.matri_valor ?? 0))
        setTotalValue(String(cabecera.valor ?? 0))
        setControlMatricula(String(cabecera.control_matricula ?? 1))
        if (cabecera.cod_jornada !== null && cabecera.cod_jornada !== undefined) {
          setSelectedJourney(String(cabecera.cod_jornada))
        }
        setPaymentDate(cabecera.fecha_pago || '')
      }
    } catch (error) {
      setDetailError(handleError(error, 'Error consultando detalle de matricula'))
      setDetail(null)
      setSelectedSubjects([])
    } finally {
      setDetailLoading(false)
    }
  }

  async function selectCohortStudent(student: AcademicEnrollmentCohortStudent) {
    const normalizedStudent = normalizeCohortStudent(student)
    setSelectedStudent(normalizedStudent)
    setParallel(student.paralelo && student.paralelo !== 'SIN PARALELO' ? student.paralelo : 'A')
    setGroupNumber(String(student.num_grupo ?? 1))
    if (student.tipo_matricula === 'R' || student.tipo_matricula === 'H' || student.tipo_matricula === 'E') {
      setEnrollmentType(student.tipo_matricula)
    }
    const detailCareer = student.cod_anio_basica || selectedCareer
    const detailPeriod = selectedPeriod || student.codigo_periodo || sourcePeriod
    if (!selectedPeriod && detailPeriod) {
      setSelectedPeriod(detailPeriod)
    }
    await loadStudentDetail(normalizedStudent, detailCareer, detailPeriod)
    setParallel(student.paralelo && student.paralelo !== 'SIN PARALELO' ? student.paralelo : 'A')
  }

  async function openStudentFicha(student: AcademicEnrollmentCohortStudent) {
    const normalizedStudent = normalizeCohortStudent(student)
    const detailCareer = student.cod_anio_basica || selectedCareer
    const detailPeriod = selectedPeriod || student.codigo_periodo || sourcePeriod
    setFichaStudent(normalizedStudent)
    setFichaDetail(null)
    setFichaError('')
    setFichaLoading(true)
    try {
      const payload = await fetchAcademicEnrollmentDetail(normalizedStudent.codigo_estud, detailCareer, detailPeriod)
      setFichaDetail(payload)
    } catch (error) {
      setFichaError(handleError(error, 'Error consultando la ficha del estudiante'))
    } finally {
      setFichaLoading(false)
    }
  }

  function closeStudentFicha() {
    setFichaStudent(null)
    setFichaDetail(null)
    setFichaError('')
  }

  function buildPayload(): AcademicEnrollmentPayload | null {
    if (!selectedStudent || !selectedCareer || !selectedPeriod) {
      setActionError('Selecciona estudiante, carrera y periodo de matricula.')
      return null
    }
    if (selectedSubjects.length === 0) {
      setActionError('Selecciona al menos una materia.')
      return null
    }

    return {
      codigo_estud: Number(selectedStudent.codigo_estud),
      cod_anio_basica: Number(selectedCareer),
      codigo_periodo: Number(selectedPeriod),
      materia_codes: selectedSubjects.map((code) => Number(code)),
      paralelo: parallel.trim().toUpperCase() || 'A',
      num_grupo: toNumber(groupNumber, 1),
      tipo_matricula: enrollmentType,
      control_matricula: toNumber(controlMatricula, 1),
      cod_jornada: toNumber(selectedJourney, 1),
      inscrip_valor: toNumber(inscripValue),
      matri_valor: toNumber(matriValue),
      valor: toNumber(totalValue),
      fecha_pago: paymentDate || null,
      remove_unselected: removeUnselected,
    }
  }

  async function getPensumMapForCareers(careerCodes: string[]) {
    const missing = careerCodes.filter((code) => !careerPensums[code])
    if (missing.length === 0) return careerPensums
    const entries = await Promise.all(
      missing.map(async (code) => {
        const payload = await fetchAcademicEnrollmentPensum(code)
        return [code, payload.items || []] as const
      })
    )
    const next = { ...careerPensums }
    for (const [code, items] of entries) {
      next[code] = items
    }
    setCareerPensums(next)
    return next
  }

  async function buildBulkPayloads(): Promise<{ payloads: AcademicBulkEnrollmentPayload[]; groups: BulkPlanGroup[] } | null> {
    const careerCodes = selectedCareerCodes.length ? selectedCareerCodes : selectedCareer ? [selectedCareer] : []
    if (careerCodes.length === 0 || !sourcePeriod || !selectedPeriod) {
      setActionError('Selecciona una o varias carreras, periodo inscrito y periodo de matricula.')
      return null
    }
    if (cohortStudents.length === 0) {
      setActionError('Carga la lista de estudiantes del periodo inscrito antes de matricular masivamente.')
      return null
    }
    if (bulkScope === 'PARCIAL' && selectedBulkStudentKeys.length === 0) {
      setActionError('Selecciona al menos un estudiante para la matriculacion parcial.')
      return null
    }

    const pensumMap = await getPensumMapForCareers(careerCodes)
    const groups = createPromotionPlanGroups(pensumMap)
    if (groups.length === 0) {
      setActionError('No hay estudiantes habilitados para matricular: revisa niveles, pensum o reprobadas de nivel 4.')
      return null
    }

    return {
      groups,
      payloads: groups.map((group) => ({
        cod_anio_basica: Number(group.careerCode),
        source_codigo_periodo: Number(sourcePeriod),
        target_codigo_periodo: Number(selectedPeriod),
        materia_codes: group.subjectCodes.map((code) => Number(code)),
        student_codes: group.studentCodes.map((code) => Number(code)),
        paralelo_filter: selectedParallelFilter || null,
        paralelo_default: parallel.trim().toUpperCase() || 'A',
        num_grupo_default: toNumber(groupNumber, 1),
        tipo_matricula: enrollmentType,
        control_matricula: toNumber(controlMatricula, 1),
        cod_jornada: toNumber(selectedJourney, 1),
        inscrip_valor: toNumber(inscripValue),
        matri_valor: toNumber(matriValue),
        valor: toNumber(totalValue),
        fecha_pago: paymentDate || null,
        remove_unselected: false,
      })),
    }
  }

  async function runPreview() {
    const payload = buildPayload()
    if (!payload) return
    setPreviewLoading(true)
    setActionError('')
    setActionMessage('')
    try {
      const response = await previewAcademicEnrollment(payload)
      setPreview(response)
    } catch (error) {
      setActionError(handleError(error, 'Error generando vista previa'))
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
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

  async function saveEnrollment() {
    const payload = buildPayload()
    if (!payload) return
    const confirmed = await requestConfirm(
      'Guardar matricula',
      'Guardar los cambios de matricula academica seleccionados?'
    )
    if (!confirmed) return

    setSaveLoading(true)
    setActionError('')
    setActionMessage('')
    try {
      const response = await saveAcademicEnrollment(payload)
      const blockedByPeriod = response.blocked_by_period ?? 0
      const changedRows = (response.inserted ?? 0) + (response.updated ?? 0) + (response.removed ?? 0)
      const resultMessage = `${response.message || 'Matricula guardada.'} Insertadas ${response.inserted ?? 0}, bloqueadas por periodo ${blockedByPeriod}, existentes sin cambio ${response.existing_skipped ?? 0}, removidas ${response.removed ?? 0}.`
      if (blockedByPeriod > 0 && changedRows === 0) {
        setActionError(resultMessage)
      } else {
        setActionMessage(resultMessage)
      }
      setPreview(response.preview || null)
      await loadStudentDetail(selectedStudent!, selectedCareer, selectedPeriod)
      if (sourcePeriod) {
        await loadCohort(sourcePeriod, selectedCareer, selectedParallelFilter)
      }
    } catch (error) {
      setActionError(handleError(error, 'Error guardando matricula academica'))
    } finally {
      setSaveLoading(false)
    }
  }

  async function runBulkPreview() {
    const plan = await buildBulkPayloads()
    if (!plan) return
    setBulkPreviewLoading(true)
    setActionError('')
    setActionMessage('')
    try {
      const responses = await Promise.all(plan.payloads.map((payload) => previewBulkAcademicEnrollment(payload)))
      const summary = responses.reduce(
        (acc, response) => {
          acc.estudiantes_origen += response.summary?.estudiantes_origen ?? 0
          acc.materias_seleccionadas += response.summary?.materias_seleccionadas ?? 0
          acc.cabeceras_crear += response.summary?.cabeceras_crear ?? 0
          acc.cabeceras_actualizar += response.summary?.cabeceras_actualizar ?? 0
          acc.cabeceras_existentes += response.summary?.cabeceras_existentes ?? 0
          acc.insertar += response.summary?.insertar ?? 0
          acc.actualizar += response.summary?.actualizar ?? 0
          acc.existentes += response.summary?.existentes ?? 0
          acc.remover += response.summary?.remover ?? 0
          acc.bloqueadas_por_notas += response.summary?.bloqueadas_por_notas ?? 0
          acc.bloqueadas_por_prerrequisito += response.summary?.bloqueadas_por_prerrequisito ?? 0
          acc.bloqueadas_por_num_matricula += response.summary?.bloqueadas_por_num_matricula ?? 0
          acc.estudiantes_ya_matriculados += response.summary?.estudiantes_ya_matriculados ?? 0
          acc.estudiantes_sin_materias_habilitadas += response.summary?.estudiantes_sin_materias_habilitadas ?? 0
          acc.ya_auditadas += response.summary?.ya_auditadas ?? 0
          return acc
        },
        {
          estudiantes_origen: 0,
          materias_seleccionadas: 0,
          cabeceras_crear: 0,
          cabeceras_actualizar: 0,
          cabeceras_existentes: 0,
          insertar: 0,
          actualizar: 0,
          existentes: 0,
          remover: 0,
          bloqueadas_por_notas: 0,
          bloqueadas_por_prerrequisito: 0,
          bloqueadas_por_num_matricula: 0,
          estudiantes_ya_matriculados: 0,
          estudiantes_sin_materias_habilitadas: 0,
          ya_auditadas: 0,
        }
      )
      setBulkPreview({
        criteria: plan.payloads[0],
        summary,
        items: responses.flatMap((response) => response.items || []),
      })
      setBulkBlockDetail(null)
      setBulkPreviewModalOpen(true)
    } catch (error) {
      setActionError(handleError(error, 'Error generando vista previa masiva'))
      setBulkPreview(null)
      closeBulkPreviewModal()
    } finally {
      setBulkPreviewLoading(false)
    }
  }

  async function saveBulkEnrollment() {
    if (!canSaveBulkEnrollment) {
      setActionError('Genera una vista previa masiva con estudiantes listos antes de matricular.')
      return
    }
    const plan = await buildBulkPayloads()
    if (!plan) return
    const confirmed = await requestConfirm(
      'Matricula masiva',
      `Matricular ${bulkScope === 'TOTAL' ? 'total' : 'parcialmente'} ${bulkStudentCount} estudiante(s) en ${new Set(plan.groups.map((group) => group.careerCode)).size} carrera(s) y ${plan.groups.length} grupo(s) de nivel hacia ${selectedPeriodName || 'el periodo destino'}?`
    )
    if (!confirmed) return

    setBulkSaveLoading(true)
    setActionError('')
    setActionMessage('')
    try {
      const responses = []
      for (const payload of plan.payloads) {
        responses.push(await saveBulkAcademicEnrollment(payload))
      }
      const summary = responses.reduce(
        (acc, response) => {
          acc.estudiantes_procesados += response.summary?.estudiantes_procesados ?? 0
          acc.inserted += response.summary?.inserted ?? 0
          acc.updated += response.summary?.updated ?? 0
          acc.existing_skipped += response.summary?.existing_skipped ?? 0
          acc.removed += response.summary?.removed ?? 0
          acc.blocked_by_grades += response.summary?.blocked_by_grades ?? 0
          acc.blocked_by_prerequisite += response.summary?.blocked_by_prerequisite ?? 0
          acc.blocked_by_repetition += response.summary?.blocked_by_repetition ?? 0
          acc.skipped_students += response.summary?.skipped_students ?? 0
          acc.already_audited += response.summary?.already_audited ?? 0
          acc.already_enrolled_students += response.summary?.already_enrolled_students ?? 0
          return acc
        },
        {
          estudiantes_procesados: 0,
          inserted: 0,
          updated: 0,
          existing_skipped: 0,
          removed: 0,
          blocked_by_grades: 0,
          blocked_by_prerequisite: 0,
          blocked_by_repetition: 0,
          skipped_students: 0,
          already_audited: 0,
          already_enrolled_students: 0,
        }
      )
      const auditIds = responses
        .map((response) => response.audit_id)
        .filter((auditId): auditId is number => typeof auditId === 'number')
      setActionMessage(
        `Matriculacion masiva guardada${auditIds.length ? `, auditoria ${auditIds.join(', ')}` : ''}. Grupos ${plan.groups.length}, estudiantes procesados ${summary.estudiantes_procesados}, insertadas ${summary.inserted}, ya matriculados ${summary.already_enrolled_students}, existentes sin cambio ${summary.existing_skipped}, ya auditadas ${summary.already_audited}, bloqueadas por matricula ${summary.blocked_by_repetition}.`
      )
      setBulkPreview({
        criteria: plan.payloads[0],
        summary: responses.reduce(
          (acc, response) => {
            acc.estudiantes_origen += response.preview?.summary?.estudiantes_origen ?? 0
            acc.materias_seleccionadas += response.preview?.summary?.materias_seleccionadas ?? 0
            acc.cabeceras_crear += response.preview?.summary?.cabeceras_crear ?? 0
            acc.cabeceras_actualizar += response.preview?.summary?.cabeceras_actualizar ?? 0
            acc.cabeceras_existentes += response.preview?.summary?.cabeceras_existentes ?? 0
            acc.insertar += response.preview?.summary?.insertar ?? 0
            acc.actualizar += response.preview?.summary?.actualizar ?? 0
            acc.existentes += response.preview?.summary?.existentes ?? 0
            acc.remover += response.preview?.summary?.remover ?? 0
            acc.bloqueadas_por_notas += response.preview?.summary?.bloqueadas_por_notas ?? 0
            acc.bloqueadas_por_prerrequisito += response.preview?.summary?.bloqueadas_por_prerrequisito ?? 0
            acc.bloqueadas_por_num_matricula += response.preview?.summary?.bloqueadas_por_num_matricula ?? 0
            acc.estudiantes_ya_matriculados += response.preview?.summary?.estudiantes_ya_matriculados ?? 0
            acc.estudiantes_sin_materias_habilitadas += response.preview?.summary?.estudiantes_sin_materias_habilitadas ?? 0
            acc.ya_auditadas += response.preview?.summary?.ya_auditadas ?? 0
            return acc
          },
          {
            estudiantes_origen: 0,
            materias_seleccionadas: 0,
            cabeceras_crear: 0,
            cabeceras_actualizar: 0,
            cabeceras_existentes: 0,
            insertar: 0,
            actualizar: 0,
            existentes: 0,
            remover: 0,
            bloqueadas_por_notas: 0,
            bloqueadas_por_prerrequisito: 0,
            bloqueadas_por_num_matricula: 0,
            estudiantes_ya_matriculados: 0,
            estudiantes_sin_materias_habilitadas: 0,
            ya_auditadas: 0,
          }
        ),
        items: responses.flatMap((response) => response.preview?.items || []),
      })
      setBulkBlockDetail(null)
      setBulkPreviewModalOpen(true)
      await loadCohort(sourcePeriod, selectedCareerCodes, selectedParallelFilter)
      if (selectedStudent && selectedPeriod) {
        await loadStudentDetail(selectedStudent, selectedCareer, selectedPeriod)
      }
    } catch (error) {
      setActionError(handleError(error, 'Error guardando matriculacion masiva'))
    } finally {
      setBulkSaveLoading(false)
    }
  }

  function toggleSubject(code: string) {
    setPreview(null)
    setBulkPreview(null)
    setSelectedSubjects((current) => {
      const next = current.includes(code) ? current.filter((item) => item !== code) : [...current, code]
      if (selectedCareer) {
        setSelectedSubjectsByCareer((byCareer) => ({ ...byCareer, [selectedCareer]: next }))
      }
      return next
    })
  }

  function toggleBulkStudent(key: string) {
    setBulkPreview(null)
    setBulkScope('PARCIAL')
    setSelectedBulkStudentKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
    )
  }

  function selectAllBulkStudents() {
    setBulkPreview(null)
    setBulkScope('PARCIAL')
    setSelectedBulkStudentKeys(cohortStudents.map((student) => bulkStudentKey(student)))
  }

  function clearBulkStudents() {
    setBulkPreview(null)
    setBulkScope('PARCIAL')
    setSelectedBulkStudentKeys([])
  }

  async function runParallelBalance() {
    if (!englishCareerCode || !sourcePeriod) {
      setBalanceActionError('Selecciona Ingles y el periodo de estudiantes para balancear paralelos.')
      return
    }
    const confirmed = await requestConfirm(
      'Balancear paralelos',
      'Balancear Ingles usando los paralelos de las otras carreras del periodo y redistribuir ABS entre PBS? Esta accion actualiza CARRERAXESTUD.'
    )
    if (!confirmed) return

    setParallelBalanceLoading(true)
    setBalanceActionError('')
    setBalanceActionMessage('')
    try {
      const response = await balanceAcademicEnrollmentParallels({
        cod_anio_basica: Number(englishCareerCode),
        codigo_periodo: Number(sourcePeriod),
      })
      setBalanceActionMessage(
        `${response.message || 'Balance aplicado.'} Estudiantes ${response.total_estudiantes ?? 0}, actualizados ${response.updated_students ?? 0}, filas ${response.updated_rows ?? 0}.`
      )
      setSelectedParallelFilter('')
      await loadCohort(sourcePeriod, selectedCareerCodes, '')
      if (selectedStudent && selectedPeriod) {
        await loadStudentDetail(selectedStudent, selectedCareer, selectedPeriod)
      }
    } catch (error) {
      setBalanceActionError(handleError(error, 'Error balanceando paralelos'))
    } finally {
      setParallelBalanceLoading(false)
    }
  }

  return (
    <div className="student-dashboard">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Matricula Acad</p>
          <h1>Matricula academica</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Cohorte</span>
          <strong>{cohort?.total ?? 0} estudiantes</strong>
        </div>
      </header>

      <section className="student-grid student-grid--content matricula-acad-grid">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Parametros</span>
              <h2>{selectedStudent?.nombre_estudiante || 'Sin estudiante seleccionado'}</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadCohort()}
                disabled={cohortLoading || !sourcePeriod}
              >
                {cohortLoading ? 'Cargando...' : 'Cargar lista'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => selectedStudent && void loadStudentDetail(selectedStudent, selectedCareer, selectedPeriod)}
                disabled={!selectedStudent || detailLoading}
              >
                {detailLoading ? 'Cargando...' : 'Actualizar'}
              </button>
            </div>
          </div>

          {catalogError ? <p className="form-error">{catalogError}</p> : null}
          {periodCareersError ? <p className="form-error">{periodCareersError}</p> : null}
          {detailError ? <p className="form-error">{detailError}</p> : null}

          <div className="matricula-acad-form">
            <label>
              <span>Periodo inscrito</span>
              <select
                value={sourcePeriod}
                disabled={catalogLoading}
                onChange={(event) => {
                  void changeSourcePeriod(event.target.value)
                }}
              >
                <option value="">Seleccionar</option>
                {periods.map((period) => (
                  <option key={period.codigo_periodo} value={period.codigo_periodo}>
                    {period.detalle_periodo} {period.anio ? `(${period.anio})` : ''} · {period.total_matriculados ?? 0}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Periodo matricula</span>
              <select
                value={selectedPeriod}
                disabled={catalogLoading}
                onChange={(event) => {
                  const value = event.target.value
                  setSelectedPeriod(value)
                  setBulkPreview(null)
                  if (selectedStudent) void loadStudentDetail(selectedStudent, selectedCareer, value)
                }}
              >
                <option value="">Seleccionar</option>
                {periods.map((period) => (
                  <option key={period.codigo_periodo} value={period.codigo_periodo}>
                    {period.detalle_periodo} {period.anio ? `(${period.anio})` : ''} · {period.total_matriculados ?? 0}
                  </option>
                ))}
              </select>
            </label>
            <div className="matricula-acad-career-picker">
              <span>Carrera</span>
              {periodCareersLoading ? <p>Cargando carreras del periodo...</p> : null}
              {!sourcePeriod ? <p>Selecciona primero el periodo inscrito.</p> : null}
              {sourcePeriod && !periodCareersLoading && careerOptions.length === 0 ? (
                <p>No hay carreras matriculadas en el periodo inscrito.</p>
              ) : null}
              <div className="matricula-acad-inline-actions">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    void selectAllCareers()
                  }}
                  disabled={!sourcePeriod || careerOptions.length === 0}
                >
                  Seleccionar todas las carreras
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    void clearCareerSelection()
                  }}
                  disabled={selectedCareerCodes.length === 0}
                >
                  Limpiar carreras
                </button>
              </div>
              <div className="matricula-acad-career-options">
                {careerOptions.map((career) => {
                  const checked = selectedCareerCodes.includes(career.cod_anio_basica)
                  const active = selectedCareer === career.cod_anio_basica
                  return (
                    <button
                      key={career.cod_anio_basica}
                      type="button"
                      className={`matricula-acad-career-option ${checked ? 'matricula-acad-career-option--active' : ''} ${active ? 'matricula-acad-career-option--focus' : ''}`}
                      disabled={!sourcePeriod || periodCareersLoading}
                      onClick={() => {
                        void selectCareerButton(career.cod_anio_basica)
                      }}
                    >
                      <input type="checkbox" checked={checked} readOnly tabIndex={-1} />
                      <strong>{career.nombre_basica}</strong>
                      <small>{career.total_matriculados ?? 0} estudiante(s)</small>
                    </button>
                  )
                })}
              </div>
            </div>
            <label>
              <span>Filtro paralelo</span>
              <select
                value={selectedParallelFilter}
                disabled={!sourcePeriod}
                onChange={(event) => {
                  const value = event.target.value
                  setSelectedParallelFilter(value)
                  setSelectedBulkStudentKeys([])
                  setBulkPreview(null)
                  if (sourcePeriod) void loadCohort(sourcePeriod, selectedCareerCodes, value)
                }}
              >
                <option value="">Todos</option>
                {parallelOptions.map((item) => (
                  <option key={item.paralelo || 'SIN PARALELO'} value={item.paralelo || ''}>
                    {item.paralelo || 'SIN PARALELO'} ({item.total_estudiantes})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Alcance masiva</span>
              <select
                value={bulkScope}
                onChange={(event) => {
                  setBulkScope(event.target.value as 'TOTAL' | 'PARCIAL')
                  setBulkPreview(null)
                }}
              >
                <option value="PARCIAL">Seleccionar estudiantes</option>
                <option value="TOTAL">Todos los cargados</option>
              </select>
            </label>
            <label>
              <span>Seleccionados</span>
              <input value={String(bulkStudentCount)} disabled readOnly />
            </label>
            <label>
              <span>Nivel promocion</span>
              <input value={promotionLevelText} disabled readOnly />
            </label>
            <label>
              <span>Tipo</span>
              <select value={enrollmentType} onChange={(event) => setEnrollmentType(event.target.value as MatriculaTipo)}>
                <option value="R">Regular</option>
                <option value="H">Homologacion</option>
              </select>
            </label>
            <label>
              <span>Jornada</span>
              <select value={selectedJourney} onChange={(event) => setSelectedJourney(event.target.value)} disabled={catalogLoading}>
                {journeys.length === 0 ? <option value={selectedJourney || '1'}>Jornada {selectedJourney || '1'}</option> : null}
                {journeys.map((journey) => (
                  <option key={journey.value} value={journey.value}>
                    {journey.label || `Jornada ${journey.value}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Paralelo</span>
              <input value={parallel} maxLength={4} onChange={(event) => setParallel(event.target.value)} />
            </label>
            <label>
              <span>Grupo</span>
              <input type="number" min="0" value={groupNumber} onChange={(event) => setGroupNumber(event.target.value)} />
            </label>
            <label>
              <span>Control</span>
              <input
                type="number"
                min="0"
                value={controlMatricula}
                onChange={(event) => setControlMatricula(event.target.value)}
              />
            </label>
            <label>
              <span>Inscripcion</span>
              <input type="number" min="0" step="0.01" value={inscripValue} onChange={(event) => setInscripValue(event.target.value)} />
            </label>
            <label>
              <span>Matricula</span>
              <input type="number" min="0" step="0.01" value={matriValue} onChange={(event) => setMatriValue(event.target.value)} />
            </label>
            <label>
              <span>Valor</span>
              <input type="number" min="0" step="0.01" value={totalValue} onChange={(event) => setTotalValue(event.target.value)} />
            </label>
            <label>
              <span>Fecha pago</span>
              <input type="date" value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} />
            </label>
          </div>

          <div className="matricula-acad-context">
            <span>{selectedCareerNames || selectedCareerName || 'Carrera pendiente'}</span>
            <span>Inscrito: {sourcePeriodName || 'Periodo pendiente'}</span>
            <span>Matricula: {selectedPeriodName || 'Periodo pendiente'}</span>
            <span>Jornada: {selectedJourneyName || 'Pendiente'}</span>
            <span>{sourcePeriod ? `${careerOptions.length} carrera(s) del periodo inscrito` : 'Carreras pendientes'}</span>
            <span>{promotionMessage || 'Nivel promocion pendiente'}</span>
            <label className="matricula-acad-check">
              <input
                type="checkbox"
                checked={removeUnselected}
                onChange={(event) => setRemoveUnselected(event.target.checked)}
              />
              Remover no seleccionadas
            </label>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide matricula-panel matricula-acad-students-panel">
          <div className="section-title">
            <div>
              <span>Estudiantes</span>
              <h2>Estudiantes del periodo</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <button type="button" className="ghost-button" onClick={selectAllBulkStudents} disabled={cohortStudents.length === 0}>
                Seleccionar todos
              </button>
              <button type="button" className="ghost-button" onClick={clearBulkStudents} disabled={selectedBulkStudentKeys.length === 0}>
                Limpiar
              </button>
              <span>{bulkStudentCount} seleccionado(s)</span>
              <span>{cohortLoading ? 'Cargando...' : `${cohortStudents.length} registro(s)`}</span>
            </div>
          </div>
          {cohortError ? <p className="form-error">{cohortError}</p> : null}
          <div className="matricula-acad-list matricula-acad-list--grid">
            {cohortStudents.map((student) => {
              const studentKey = bulkStudentKey(student)
              const checked = selectedBulkStudentSet.has(studentKey)
              const active =
                selectedStudent?.codigo_estud === student.codigo_estud &&
                selectedStudent.cod_anio_basica_actual === student.cod_anio_basica
              return (
                <article
                  key={`${student.codigo_estud}-${student.cod_anio_basica}-${student.codigo_periodo}-${student.paralelo || 'NA'}`}
                  role="button"
                  tabIndex={0}
                  className={`matricula-acad-student ${active ? 'matricula-acad-student--active' : ''} ${checked ? 'matricula-acad-student--bulk-selected' : ''}`}
                  onClick={() => toggleBulkStudent(studentKey)}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      toggleBulkStudent(studentKey)
                    }
                  }}
                >
                  <div className="matricula-acad-student-head">
                    <label className="matricula-acad-student-check" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleBulkStudent(studentKey)}
                      />
                      Seleccionar
                    </label>
                    <button
                      type="button"
                      className="matricula-acad-student-open"
                      onClick={(event) => {
                        event.stopPropagation()
                        void openStudentFicha(student)
                      }}
                    >
                      Ver ficha
                    </button>
                  </div>
                  <strong>{student.nombre_estudiante}</strong>
                  <span>{student.cedula_normalizada || student.cedula || student.codigo_estud}</span>
                  <small>
                    {student.nombre_carrera || 'Sin carrera'} · {student.paralelo || 'Sin paralelo'} · Nivel{' '}
                    {valueOrDash(student.nivel_actual)} · PromedioFinal {'>='} 7 {student.aprobadas_nivel_actual ?? 0}/
                    {student.materias_nivel_actual || '-'}
                  </small>
                </article>
              )
            })}
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content matricula-acad-balance-grid">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Balance</span>
              <h2>Distribucion por paralelo</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <button
                type="button"
                className="primary-action"
                onClick={runParallelBalance}
                disabled={parallelBalanceLoading || !canBalanceParallels}
              >
                {parallelBalanceLoading ? 'Balanceando...' : 'Balancear paralelos'}
              </button>
            </div>
          </div>
          {balanceActionError ? <p className="form-error">{balanceActionError}</p> : null}
          {balanceActionMessage ? <p className="form-success">{balanceActionMessage}</p> : null}
          <div className="matricula-acad-balance">
            {(cohort?.balance?.por_paralelo || []).map((item) => (
              <div key={item.paralelo || 'SIN PARALELO'}>
                <span>{item.paralelo || 'SIN PARALELO'}</span>
                <strong>{item.total_estudiantes}</strong>
                <small>{item.total_materias ?? 0} materia(s)</small>
              </div>
            ))}
          </div>
        </article>
        <article className="student-card matricula-panel">
          <div className="section-title">
            <div>
              <span>Niveles</span>
              <h2>Distribucion</h2>
            </div>
          </div>
          <div className="matricula-acad-balance matricula-acad-balance--compact">
            {(cohort?.balance?.por_nivel || []).map((item) => (
              <div key={item.nivel || 'SIN NIVEL'}>
                <span>Nivel {item.nivel || '-'}</span>
                <strong>{item.total_estudiantes}</strong>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content matricula-acad-workspace">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Pensum</span>
              <h2>Materias por carrera</h2>
            </div>
            <select value={semesterFilter} onChange={(event) => setSemesterFilter(event.target.value)}>
              <option value="ALL">Todos los niveles</option>
              {semesters.map((semester) => (
                <option key={semester} value={semester}>
                  Nivel {semester}
                </option>
              ))}
            </select>
          </div>
          {pensumLoading ? <p className="form-success">Cargando pensum...</p> : null}
          {pensumError ? <p className="form-error">{pensumError}</p> : null}
          {promotionPlanGroups.length > 0 ? (
            <div className="matricula-acad-plan">
              {promotionPlanGroups.map((group) => (
                <div key={group.key}>
                  <strong>{group.careerName}</strong>
                  <span>
                    Desde nivel {group.sourceLevel} hacia {group.levelLabel} · {group.studentCodes.length} estudiante(s) · {group.subjectCodes.length} materia(s)
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Codigo</th>
                  <th>Materia</th>
                  <th>Nivel</th>
                  <th>Creditos</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {filteredPensum.map((subject) => {
                  const selected = selectedSubjectSet.has(subject.codigo_materia)
                  const current = currentSubjectCodes.has(subject.codigo_materia)
                  return (
                    <tr key={subject.codigo_materia}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleSubject(subject.codigo_materia)}
                        />
                      </td>
                      <td>{subject.codigo_materia}</td>
                      <td>{subject.nombre_materia}</td>
                      <td>{valueOrDash(subject.semestre)}</td>
                      <td>{valueOrDash(subject.creditos)}</td>
                      <td>{current ? 'Matriculada' : selected ? 'Seleccionada' : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="student-card matricula-panel">
          <div className="section-title">
            <div>
              <span>Vista previa</span>
              <h2>Cambios</h2>
            </div>
          </div>

          <div className="matricula-acad-actions">
            <button type="button" className="ghost-button" onClick={runPreview} disabled={previewLoading || !selectedStudent}>
              {previewLoading ? 'Validando...' : 'Vista previa'}
            </button>
            <button
              type="button"
              className="primary-action"
              onClick={saveEnrollment}
              disabled={saveLoading || !selectedStudent || previewBlockedByPeriod}
            >
              {saveLoading ? 'Guardando...' : 'Guardar'}
            </button>
          </div>

          <div className="matricula-acad-bulk-block matricula-acad-bulk-card">
            <div className="section-title">
              <div>
                <span>Masiva</span>
                <h2>Matricular carrera</h2>
              </div>
            </div>
            <div className="matricula-acad-bulk-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={runBulkPreview}
                disabled={bulkPreviewLoading || bulkStudentCount === 0}
              >
                {bulkPreviewLoading ? 'Validando...' : 'Vista previa masiva'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={saveBulkEnrollment}
                disabled={bulkSaveLoading || bulkStudentCount === 0 || !canSaveBulkEnrollment}
              >
                {bulkSaveLoading ? 'Matriculando...' : 'Matricular carrera'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={downloadBulkValidationDocument}
                disabled={!canDownloadBulkValidation}
              >
                Descargar validacion
              </button>
            </div>
            {!bulkPreview ? (
              <p className="matricula-acad-hint">Genera primero la vista previa masiva para validar estudiantes y materias.</p>
            ) : null}
          </div>

          {actionError ? <p className="form-error">{actionError}</p> : null}
          {actionMessage ? <p className="form-success">{actionMessage}</p> : null}
          {previewBlockedByPeriod ? (
            <p className="form-error">
              El estudiante ya tiene matricula registrada en la carrera y periodo destino. No se puede crear otra
              matricula academica para la misma carrera y periodo.
            </p>
          ) : null}

          <div className="matricula-acad-preview">
            <div>
              <span>Cabecera</span>
              <strong>{preview?.cabecera?.accion || '-'}</strong>
            </div>
            <div>
              <span>Insertar</span>
              <strong>{preview?.summary?.insertar ?? 0}</strong>
            </div>
            <div>
              <span>Actualizar</span>
              <strong>{preview?.summary?.actualizar ?? 0}</strong>
            </div>
            <div>
              <span>Existentes</span>
              <strong>{preview?.summary?.existentes ?? 0}</strong>
            </div>
            <div>
              <span>Remover</span>
              <strong>{preview?.summary?.remover ?? 0}</strong>
            </div>
            <div>
              <span>Bloq. periodo</span>
              <strong>{preview?.summary?.bloqueadas_por_periodo ?? 0}</strong>
            </div>
          </div>

          {bulkPreview ? (
            <div className="matricula-acad-preview matricula-acad-preview--bulk-summary">
              <div>
                <span>Estudiantes</span>
                <strong>{bulkPreview.summary?.estudiantes_origen ?? 0}</strong>
              </div>
              <div>
                <span>Cabeceras crear</span>
                <strong>{bulkPreview.summary?.cabeceras_crear ?? 0}</strong>
              </div>
              <div>
                <span>Cabeceras existentes</span>
                <strong>{bulkPreview.summary?.cabeceras_existentes ?? 0}</strong>
              </div>
              <div>
                <span>Insertar</span>
                <strong>{bulkPreview.summary?.insertar ?? 0}</strong>
              </div>
              <div>
                <span>Actualizar</span>
                <strong>{bulkPreview.summary?.actualizar ?? 0}</strong>
              </div>
              <div>
                <span>Existentes</span>
                <strong>{bulkPreview.summary?.existentes ?? 0}</strong>
              </div>
              <div>
                <span>Bloq. prerreq.</span>
                <strong>{bulkPreview.summary?.bloqueadas_por_prerrequisito ?? 0}</strong>
              </div>
            <div>
              <span>Bloq. matricula</span>
              <strong>{bulkPreview.summary?.bloqueadas_por_num_matricula ?? 0}</strong>
            </div>
            <div>
              <span>Ya matriculados</span>
              <strong>{bulkPreview.summary?.estudiantes_ya_matriculados ?? 0}</strong>
            </div>
            <div>
              <span>Ya auditadas</span>
              <strong>{bulkPreview.summary?.ya_auditadas ?? 0}</strong>
              </div>
              <div>
                <span>Sin materias</span>
                <strong>{bulkPreview.summary?.estudiantes_sin_materias_habilitadas ?? 0}</strong>
              </div>
            </div>
          ) : null}

          {bulkPreview ? (
            <div className="matricula-acad-bulk-preview matricula-acad-bulk-preview--compact">
              <div className="matricula-acad-bulk-preview-head">
                <div>
                  <span>Revision masiva</span>
                  <strong>{bulkPreviewReadyStudents.length} estudiante(s) listos</strong>
                </div>
                <small>{(bulkPreview.items || []).length} candidato(s) revisado(s)</small>
              </div>
              <button type="button" className="ghost-button" onClick={() => setBulkPreviewModalOpen(true)}>
                Abrir revision completa
              </button>
            </div>
          ) : null}

          <div className="matricula-acad-preview-list">
            {(preview?.items || []).slice(0, 12).map((item) => (
              <div key={`${item.accion}-${item.codigo_materia}`}>
                <strong>{item.accion}</strong>
                <span>{item.nombre_materia || item.codigo_materia}</span>
              </div>
            ))}
          </div>
        </aside>
      </section>
      {bulkPreviewModalOpen && bulkPreview ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="matricula-bulk-preview-title">
          <article className="matricula-modal matricula-acad-bulk-modal">
            <div className="matricula-modal-head matricula-acad-bulk-modal-head">
              <div className="matricula-modal-title matricula-acad-bulk-modal-title">
                <span>Vista previa masiva</span>
                <h3 id="matricula-bulk-preview-title">Validacion de matricula academica</h3>
                <small>{selectedCareerNames || selectedCareerName || 'Carreras seleccionadas'}</small>
              </div>
              <div className="matricula-modal-actions">
                <button type="button" className="ghost-button" onClick={downloadBulkValidationDocument}>
                  Descargar validacion
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={saveBulkEnrollment}
                  disabled={bulkSaveLoading || bulkStudentCount === 0 || !canSaveBulkEnrollment}
                >
                  {bulkSaveLoading ? 'Matriculando...' : 'Matricular carrera'}
                </button>
                <button type="button" className="matricula-modal-close" onClick={closeBulkPreviewModal}>
                  Cerrar
                </button>
              </div>
            </div>

            <div className="matricula-acad-bulk-modal-summary">
              <div>
                <span>Periodo inscrito</span>
                <strong>{sourcePeriodName || sourcePeriod || '-'}</strong>
              </div>
              <div>
                <span>Periodo matricula</span>
                <strong>{selectedPeriodName || selectedPeriod || '-'}</strong>
              </div>
              <div>
                <span>Candidatos revisados</span>
                <strong>{(bulkPreview.items || []).length}</strong>
              </div>
              <div>
                <span>Listos para matricular</span>
                <strong>{bulkPreviewReadyStudents.length}</strong>
              </div>
              <div>
                <span>No matriculados</span>
                <strong>{Math.max((bulkPreview.items || []).length - bulkPreviewReadyStudents.length, 0)}</strong>
              </div>
            </div>

            {actionError ? <p className="form-error">{actionError}</p> : null}
            {actionMessage ? <p className="form-success">{actionMessage}</p> : null}

            <div className="matricula-acad-bulk-preview">
              <div className="matricula-acad-bulk-preview-head">
                <div>
                  <span>Detalle de validacion</span>
                  <strong>{bulkPreviewReadyStudents.length} estudiante(s) listos</strong>
                </div>
                <small>{(bulkPreview.items || []).length} candidato(s) revisado(s)</small>
              </div>
              <div className="matricula-table-wrap matricula-acad-bulk-preview-table">
                <table className="matricula-table matricula-acad-bulk-table">
                  <thead>
                    <tr>
                      <th>Estado</th>
                      <th>Estudiante</th>
                      <th>Carrera</th>
                      <th>Nivel</th>
                      <th>Materias a matricular</th>
                      <th>Observacion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(bulkPreview.items || []).map((item, index) => {
                      const ready = (item.insertar || 0) > 0
                      const statusLabel = formatBulkPreviewStatus(item, ready)
                      return (
                        <tr key={`${item.codigo_estud}-${item.cod_anio_basica}-${item.nivel_destino}-${item.estado}-${index}`}>
                          <td>
                            {ready ? (
                              <span className="matricula-status-pill matricula-status-pill--ready">{statusLabel}</span>
                            ) : (
                              <button
                                type="button"
                                className="matricula-status-pill matricula-status-pill--blocked matricula-status-button"
                                onClick={() => setBulkBlockDetail(item)}
                              >
                                {statusLabel}
                              </button>
                            )}
                          </td>
                          <td>
                            <strong>{item.nombre_estudiante || '-'}</strong>
                            <small>{item.cedula || item.codigo_estud || '-'}</small>
                          </td>
                          <td>{item.carrera || item.cod_anio_basica || '-'}</td>
                          <td>
                            {valueOrDash(item.nivel_origen)} hacia {valueOrDash(item.nivel_destino)}
                          </td>
                          <td>
                            {item.materias_insertar?.length ? (
                              <div className="matricula-acad-subject-chips">
                                {item.materias_insertar.map((subject) => (
                                  <span key={`${item.codigo_estud}-${subject.codigo_materia}`}>
                                    {subject.nombre_materia || subject.codigo_materia}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              '-'
                            )}
                          </td>
                          <td>{item.motivo || item.cabecera || '-'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </article>
          {bulkBlockDetail ? (
            <div
              className="matricula-modal-overlay matricula-modal-overlay--nested"
              role="dialog"
              aria-modal="true"
              aria-labelledby="matricula-bulk-block-title"
            >
              <article className="matricula-modal matricula-block-detail-modal">
                <div className="matricula-modal-head">
                  <div className="matricula-modal-title matricula-block-detail-title">
                    <span>Detalle de bloqueo</span>
                    <h3 id="matricula-bulk-block-title">{bulkBlockDetail.nombre_estudiante || 'Estudiante bloqueado'}</h3>
                  </div>
                  <button type="button" className="matricula-modal-close" onClick={() => setBulkBlockDetail(null)}>
                    Cerrar
                  </button>
                </div>

                <div className="matricula-block-detail-summary">
                  <div>
                    <span>Estado</span>
                    <strong>{formatBulkPreviewStatus(bulkBlockDetail, false)}</strong>
                  </div>
                  <div>
                    <span>Cedula</span>
                    <strong>{bulkBlockDetail.cedula || bulkBlockDetail.codigo_estud || '-'}</strong>
                  </div>
                  <div>
                    <span>Carrera</span>
                    <strong>{bulkBlockDetail.carrera || bulkBlockDetail.cod_anio_basica || '-'}</strong>
                  </div>
                  <div>
                    <span>Nivel</span>
                    <strong>
                      {valueOrDash(bulkBlockDetail.nivel_origen)} hacia {valueOrDash(bulkBlockDetail.nivel_destino)}
                    </strong>
                  </div>
                </div>

                <section className="matricula-block-detail-section">
                  <h4>Motivo principal</h4>
                  <p>{bulkBlockDetail.motivo || bulkBlockDetail.cabecera || 'No hay una observacion registrada para esta validacion.'}</p>
                </section>

                <section className="matricula-block-detail-section">
                  <div className="matricula-block-detail-section-head">
                    <h4>Materias bloqueadas</h4>
                    <span>{bulkBlockDetail.materias_bloqueadas?.length || 0}</span>
                  </div>
                  {bulkBlockDetail.materias_bloqueadas?.length ? (
                    <div className="matricula-table-wrap matricula-block-detail-table">
                      <table className="matricula-table">
                        <thead>
                          <tr>
                            <th>Materia</th>
                            <th>Motivo</th>
                            <th>Previas faltantes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {bulkBlockDetail.materias_bloqueadas.map((subject, index) => (
                            <tr key={`${bulkBlockDetail.codigo_estud}-${subject.codigo_materia}-${index}`} title={formatBulkBlockSubject(subject)}>
                              <td>{valueOrDash(subject.codigo_materia)}</td>
                              <td>{subject.motivo || '-'}</td>
                              <td>{subject.materias_previas?.length ? subject.materias_previas.join(', ') : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p>No hay materias bloqueadas detalladas para este registro.</p>
                  )}
                </section>

                <section className="matricula-block-detail-section">
                  <div className="matricula-block-detail-section-head">
                    <h4>Materias a matricular</h4>
                    <span>{bulkBlockDetail.materias_insertar?.length || 0}</span>
                  </div>
                  {bulkBlockDetail.materias_insertar?.length ? (
                    <div className="matricula-acad-subject-chips">
                      {bulkBlockDetail.materias_insertar.map((subject) => (
                        <span key={`${bulkBlockDetail.codigo_estud}-insertar-${subject.codigo_materia}`}>
                          {subject.nombre_materia || subject.codigo_materia}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p>No hay materias habilitadas para matricular.</p>
                  )}
                </section>

                <div className="matricula-block-detail-counts">
                  <div>
                    <span>Insertar</span>
                    <strong>{bulkBlockDetail.insertar || 0}</strong>
                  </div>
                  <div>
                    <span>Existentes</span>
                    <strong>{bulkBlockDetail.existentes || 0}</strong>
                  </div>
                  <div>
                    <span>Prerrequisito</span>
                    <strong>{bulkBlockDetail.bloqueadas_por_prerrequisito || 0}</strong>
                  </div>
                  <div>
                    <span>Num. matricula</span>
                    <strong>{bulkBlockDetail.bloqueadas_por_num_matricula || 0}</strong>
                  </div>
                  <div>
                    <span>Auditadas</span>
                    <strong>{bulkBlockDetail.ya_auditadas || 0}</strong>
                  </div>
                </div>
              </article>
            </div>
          ) : null}
        </div>
      ) : null}
      {fichaStudent ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="matricula-ficha-title">
          <article className="matricula-modal matricula-acad-ficha-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>Ficha estudiante</span>
                <h3 id="matricula-ficha-title">{fichaResolvedStudent?.nombre_estudiante || fichaStudent.nombre_estudiante}</h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={closeStudentFicha}>
                Cerrar
              </button>
            </div>

            {fichaLoading ? <p>Cargando ficha del estudiante...</p> : null}
            {fichaError ? <p className="form-error">{fichaError}</p> : null}

            <div className="matricula-acad-ficha-summary">
              <div>
                <span>Codigo</span>
                <strong>{fichaResolvedStudent?.codigo_estud || fichaStudent.codigo_estud}</strong>
              </div>
              <div>
                <span>Cedula</span>
                <strong>{fichaResolvedStudent?.cedula_normalizada || fichaResolvedStudent?.cedula || fichaStudent.cedula_normalizada || '-'}</strong>
              </div>
              <div>
                <span>Correo personal</span>
                <strong>{fichaResolvedStudent?.correo_personal || '-'}</strong>
              </div>
              <div>
                <span>Correo INTEC</span>
                <strong>{fichaResolvedStudent?.correo_intec || '-'}</strong>
              </div>
              <div>
                <span>Carrera actual</span>
                <strong>{fichaResolvedStudent?.carrera_actual || '-'}</strong>
              </div>
              <div>
                <span>Periodo actual</span>
                <strong>{fichaResolvedStudent?.detalle_periodo_actual || fichaResolvedStudent?.periodo_actual || '-'}</strong>
              </div>
            </div>

            <div className="matricula-acad-ficha-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={!fichaCohortStudent || detailLoading}
                onClick={() => {
                  if (!fichaCohortStudent) return
                  void (async () => {
                    await selectCohortStudent(fichaCohortStudent)
                    closeStudentFicha()
                  })()
                }}
              >
                Usar en formulario
              </button>
            </div>

            <section className="matricula-acad-ficha-section">
              <div className="section-title">
                <div>
                  <span>Cabecera</span>
                  <h2>Matriculas registradas</h2>
                </div>
                <span>{fichaCabeceras.length} registro(s)</span>
              </div>
              {fichaCabeceras.length === 0 ? (
                <p className="empty-block">No hay cabeceras de matricula para mostrar.</p>
              ) : (
                <div className="matricula-acad-ficha-card-list">
                  {fichaCabeceras.map((cabecera) => (
                    <article
                      className="matricula-acad-ficha-card"
                      key={`${cabecera.codigo_estud}-${cabecera.cod_anio_basica}-${cabecera.codigo_periodo}`}
                    >
                      <div className="matricula-acad-ficha-card-head">
                        <div>
                          <span>Carrera</span>
                          <strong>{cabecera.carrera || cabecera.cod_anio_basica}</strong>
                        </div>
                        <em>{cabecera.periodo || cabecera.codigo_periodo}</em>
                      </div>
                      <div className="matricula-acad-ficha-card-grid">
                        <div>
                          <span>Num. matricula</span>
                          <strong>{valueOrDash(cabecera.num_matricula)}</strong>
                        </div>
                        <div>
                          <span>Fecha pago</span>
                          <strong>{valueOrDash(cabecera.fecha_pago)}</strong>
                        </div>
                        <div>
                          <span>Valor</span>
                          <strong>{valueOrDash(cabecera.valor)}</strong>
                        </div>
                        <div>
                          <span>Control</span>
                          <strong>{valueOrDash(cabecera.control_matricula)}</strong>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="matricula-acad-ficha-section">
              <div className="section-title">
                <div>
                  <span>Materias</span>
                  <h2>Materias actuales</h2>
                </div>
                <span>{fichaMateriasActuales.length} materia(s)</span>
              </div>
              <div className="matricula-table-wrap">
                <table className="matricula-table">
                  <thead>
                    <tr>
                      <th>Nivel</th>
                      <th>Codigo</th>
                      <th>Materia</th>
                      <th>Creditos</th>
                      <th>Paralelo</th>
                      <th>Tipo</th>
                      <th>Notas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fichaMateriasActuales.length === 0 ? (
                      <tr>
                        <td colSpan={7}>No hay materias actuales para mostrar.</td>
                      </tr>
                    ) : (
                      fichaMateriasActuales.map((subject) => (
                        <tr key={`${subject.codigo_materia}-${subject.paralelo || 'NA'}-${subject.num_matricula || 'NA'}`}>
                          <td>{valueOrDash(subject.semestre)}</td>
                          <td>
                            <strong>{subject.cod_materia || subject.codigo_materia}</strong>
                            <br />
                            <span>{subject.codigo_materia}</span>
                          </td>
                          <td>{subject.nombre_materia}</td>
                          <td>{valueOrDash(subject.creditos)}</td>
                          <td>{valueOrDash(subject.paralelo)}</td>
                          <td>{valueOrDash(subject.tipo_matricula)}</td>
                          <td>{subject.tiene_notas ? 'Con notas' : 'Sin notas'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </article>
        </div>
      ) : null}
      {confirmDialog ? (
        <div className="matricula-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="matricula-confirm-title">
          <div className="matricula-confirm-modal">
            <div>
              <span>Confirmacion</span>
              <h2 id="matricula-confirm-title">{confirmDialog.title}</h2>
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
