import { useEffect, useMemo, useState } from 'react'

import {
  assignPracticasEnrollmentResponsable,
  downloadPracticasCartaCompromiso,
  enrollPracticasStudents,
  fetchPracticasCatalog,
  fetchPracticasElegibles,
  fetchPracticasExpedientes,
  fetchPracticasPeriodoDesignaciones,
  fetchPracticasPeriodos,
  fetchPracticasResponsableAvance,
  fetchPracticasReviewDetail,
  fetchPracticasStudent,
  reviewPracticasExpediente,
  searchPracticasActiveTeachers,
  uploadPracticasAutorizacion,
} from '../../lib/api'
import type {
  AcademicTeacherOption,
  PracticasCatalogResponse,
  PracticasExpedienteItem,
  PracticasEligibilityItem,
  PracticasProcessCode,
  PracticasPeriodoDesignacionItem,
  PracticasPeriodoItem,
  PracticasReviewDecision,
  PracticasReviewDetailResponse,
  PracticasResponsableProgressResponse,
  PracticasStudentResponse,
} from '../../types/app'
import { ExpedientesDocumentalesView } from '../expedientes/ExpedientesDocumentalesView'
import { PracticasSeguimientoPanel } from './PracticasSeguimientoPanel'

type PracticasInstitucionalesViewProps = {
  displayName: string
  role?: string
  codigoEstud?: number
  initialProcess?: PracticasProcessCode
  onProcessChange?: (process: PracticasProcessCode) => void
}

type PracticasWorkspace = 'gestion' | 'seguimiento' | 'catalogos'

const PROCESS_OPTIONS: Array<{ code: PracticasProcessCode; label: string; short: string; description: string }> = [
  {
    code: 'PPF',
    label: 'Prácticas laborales/preprofesionales',
    short: 'Prácticas preprofesionales',
    description: 'Inscripción institucional, plan de trabajo, horas, documentos y cierre.',
  },
  {
    code: 'VIN',
    label: 'Vinculación con la sociedad',
    short: 'Vinculación con la sociedad',
    description: 'Proyecto, beneficiarios, actividades, indicadores y evidencias.',
  },
]

function eligibilityKey(item: PracticasEligibilityItem) {
  return `${item.codigo_estud}|${item.CodigoCarrera || ''}|${item.CodigoPeriodo || ''}`
}

function canRegisterInstitutionalEnrollment(item: PracticasEligibilityItem) {
  return Boolean(item.PuedeInscribirse ?? item.PuedeMatricular)
}

function valueOrDash(value: unknown) {
  const text = value === null || value === undefined ? '' : String(value).trim()
  return text || '-'
}

function processLabel(code: string | undefined) {
  return PROCESS_OPTIONS.find((item) => item.code === code)?.label || code || '-'
}

function statusClass(value: string | null | undefined) {
  const normalized = (value || '').toLowerCase()
  if (normalized.includes('aprob') || normalized.includes('valid') || normalized.includes('cerr')) return 'portal-status portal-status--ok'
  if (normalized.includes('observ') || normalized.includes('pend')) return 'portal-status portal-status--warning'
  if (normalized.includes('anul') || normalized.includes('rech')) return 'portal-status portal-status--danger'
  return 'portal-status'
}

function percentValue(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0
  return Math.max(0, Math.min(100, numeric))
}

function periodLabel(periodo: PracticasPeriodoItem) {
  return [
    valueOrDash(periodo.CodigoPeriodo),
    valueOrDash(periodo.NombrePeriodo),
    periodo.EstadoPeriodo ? `Estado ${periodo.EstadoPeriodo}` : '',
    periodo.TipoMatricula ? `Tipo ${periodo.TipoMatricula}` : '',
    periodo.Anio ? `Año ${periodo.Anio}` : '',
  ].filter(Boolean).join(' · ')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function dateInputValue(value: unknown) {
  const match = String(value ?? '').trim().match(/^\d{4}-\d{2}-\d{2}/)
  return match?.[0] || ''
}

function ecuadorDateValue() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Guayaquil',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}

function uploadWindowLabel(start: unknown, end: unknown) {
  const from = dateInputValue(start)
  const to = dateInputValue(end)
  return from && to ? `${from} al ${to}` : 'Plazo pendiente de configuración'
}

function isUploadWindowOpen(start: unknown, end: unknown) {
  const from = dateInputValue(start)
  const to = dateInputValue(end)
  if (!from || !to) return false
  const today = ecuadorDateValue()
  return today >= from && today <= to
}

export function PracticasInstitucionalesView({
  displayName,
  role = '',
  codigoEstud,
  initialProcess = 'PPF',
  onProcessChange,
}: Readonly<PracticasInstitucionalesViewProps>) {
  const normalizedRole = role.trim().toUpperCase()
  const isAdmin = !['ESTUDIANTE', 'DOCENTE'].includes(normalizedRole)
  const isResponsible = normalizedRole === 'DOCENTE'
  const isStudent = normalizedRole === 'ESTUDIANTE'
  const [selectedProcess, setSelectedProcess] = useState<PracticasProcessCode>(initialProcess)
  const [activeWorkspace, setActiveWorkspace] = useState<PracticasWorkspace>(isAdmin ? 'gestion' : 'seguimiento')
  const [catalog, setCatalog] = useState<PracticasCatalogResponse | null>(null)
  const [studentData, setStudentData] = useState<PracticasStudentResponse | null>(null)
  const [responsableProgress, setResponsableProgress] = useState<PracticasResponsableProgressResponse | null>(null)
  const [expedientes, setExpedientes] = useState<PracticasExpedienteItem[]>([])
  const [adminElegibles, setAdminElegibles] = useState<PracticasEligibilityItem[]>([])
  const [periodos, setPeriodos] = useState<PracticasPeriodoItem[]>([])
  const [periodDesignations, setPeriodDesignations] = useState<PracticasPeriodoDesignacionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [eligibilitySearch, setEligibilitySearch] = useState('')
  const [teacherSearch, setTeacherSearch] = useState('')
  const [teacherOptions, setTeacherOptions] = useState<AcademicTeacherOption[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [selectedSourcePeriod, setSelectedSourcePeriod] = useState('')
  const [uploadStartDate, setUploadStartDate] = useState('')
  const [uploadEndDate, setUploadEndDate] = useState('')
  const [selectedStudents, setSelectedStudents] = useState<string[]>([])
  const [selectedEnrollmentIds, setSelectedEnrollmentIds] = useState<number[]>([])
  const [documentExpedient, setDocumentExpedient] = useState<{
    identification: string
    process: PracticasProcessCode
  } | null>(null)
  const [reviewDetail, setReviewDetail] = useState<PracticasReviewDetailResponse | null>(null)
  const [reviewHours, setReviewHours] = useState('')
  const [reviewCorroborated, setReviewCorroborated] = useState(false)
  const [reviewObservation, setReviewObservation] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewError, setReviewError] = useState('')
  const [responsableForm, setResponsableForm] = useState({
    nombre_responsable: '',
    cedula_responsable: '',
    correo_responsable: '',
    codigo_docente: '',
    rol_responsable: 'RESPONSABLE',
  })

  const sourcePeriodDetail = periodos.find((periodo) => String(periodo.CodigoPeriodo) === selectedSourcePeriod)
  const targetPeriodDetail = periodos.find((periodo) => String(periodo.CodigoPeriodo) === selectedPeriod)

  const periodEnrollments = useMemo(
    () => expedientes.filter((item) => (
      item.TipoProcesoCodigo === selectedProcess
      && String(item.CodigoPeriodo || '') === selectedPeriod
    )),
    [expedientes, selectedPeriod, selectedProcess],
  )

  const filteredStudentExpedientes = useMemo(
    () => (studentData?.expedientes || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [selectedProcess, studentData]
  )

  const adminReviewItems = useMemo(
    () => (responsableProgress?.items || []).filter((item) => (
      item.TipoProcesoCodigo === selectedProcess
      && String(item.CodigoPeriodo || '') === selectedPeriod
    )),
    [responsableProgress, selectedPeriod, selectedProcess],
  )

  const adminReviewSummary = useMemo(() => {
    const required = adminReviewItems.reduce(
      (total, item) => total + Number(item.DocumentosRequeridos || 0),
      0,
    )
    const loaded = adminReviewItems.reduce(
      (total, item) => total + Number(item.TotalDocumentos || 0),
      0,
    )
    const validated = adminReviewItems.reduce(
      (total, item) => total + Number(item.DocumentosValidados || 0),
      0,
    )
    return {
      expedientes: adminReviewItems.length,
      documentos_cargados: loaded,
      documentos_validados: validated,
      documentos_pendientes: Math.max(required - validated, 0),
      avance: required ? (validated / required) * 100 : 0,
    }
  }, [adminReviewItems])

  const processDocuments = useMemo(
    () => (catalog?.documents || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [catalog, selectedProcess]
  )

  const processResponsibles = useMemo(
    () => (catalog?.responsibles || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [catalog, selectedProcess]
  )

  const workspaceOptions: Array<{ code: PracticasWorkspace; label: string; description: string }> = isAdmin
    ? [
        {
          code: 'gestion',
          label: 'Inscripción y responsables',
          description: 'Inscribir estudiantes para cumplimiento, definir plazos y asignar el docente responsable.',
        },
        {
          code: 'seguimiento',
          label: 'Seguimiento, calificación y cierre',
          description: selectedProcess === 'VIN'
            ? 'Controlar proyecto, actividades, indicadores, revisión, calificación y cierre.'
            : 'Controlar plan, bitácora, documentos, revisión, calificación y cierre.',
        },
        {
          code: 'catalogos',
          label: selectedProcess === 'VIN' ? 'Proyectos y convenios' : 'Entidades y convenios',
          description: selectedProcess === 'VIN'
            ? 'Administrar entidades, convenios y proyectos activos de vinculación.'
            : 'Administrar empresas receptoras y convenios vigentes.',
        },
      ]
    : isResponsible
      ? [
          {
            code: 'seguimiento',
            label: 'Seguimiento y calificación',
            description: 'Revisar plan, evidencias y horas; habilitar y registrar la calificación final.',
          },
          {
            code: 'gestion',
            label: 'Revisión documental previa',
            description: 'Corroborar documentos y horas antes de la calificación final del seguimiento.',
          },
        ]
      : [
          {
            code: 'seguimiento',
            label: 'Mi seguimiento y resultado',
            description: 'Consultar requisitos, enviar a revisión y revisar la calificación final.',
          },
          {
            code: 'gestion',
            label: 'Mi cumplimiento documental',
            description: 'Consultar el porcentaje, los plazos y los documentos cargados por el docente responsable.',
          },
        ]

  async function loadCatalog() {
    const payload = await fetchPracticasCatalog()
    setCatalog(payload)
  }

  async function loadStudent() {
    if (isAdmin || isResponsible) return
    const payload = await fetchPracticasStudent(codigoEstud)
    setStudentData(payload)
  }

  async function loadAdmin() {
    const payload = await fetchPracticasExpedientes({ tipo_proceso: selectedProcess, search: '', limit: 500 })
    setExpedientes(payload.items || [])
  }

  async function loadAdminEligibility() {
    if (!isAdmin) return
    const payload = await fetchPracticasElegibles({
      tipo_proceso: selectedProcess,
      search: eligibilitySearch,
      codigo_periodo: selectedSourcePeriod,
      limit: 500,
    })
    setAdminElegibles(payload.items || [])
  }

  async function loadPeriodDesignations() {
    if (!isAdmin) return
    const [periodPayload, designationPayload] = await Promise.all([
      fetchPracticasPeriodos(selectedProcess),
      fetchPracticasPeriodoDesignaciones(selectedProcess),
    ])
    setPeriodos(periodPayload.items || [])
    setPeriodDesignations(designationPayload.items || [])
    const initialPeriodCode = selectedPeriod || String(periodPayload.items?.[0]?.CodigoPeriodo || '')
    if (!selectedPeriod && initialPeriodCode) {
      setSelectedPeriod(initialPeriodCode)
    }
    const initialPeriod = periodPayload.items?.find(
      (item) => String(item.CodigoPeriodo || '') === initialPeriodCode,
    )
    if (initialPeriod) {
      setUploadStartDate((current) => current || dateInputValue(initialPeriod.FechaInicio))
      setUploadEndDate((current) => current || dateInputValue(initialPeriod.FechaFin))
    }
    if (!selectedSourcePeriod && periodPayload.items?.length) {
      setSelectedSourcePeriod(String(periodPayload.items[0].CodigoPeriodo || ''))
    }
  }

  async function loadResponsibleProgress() {
    if (!isResponsible && !isAdmin) return
    const payload = await fetchPracticasResponsableAvance(selectedProcess)
    setResponsableProgress(payload)
  }

  async function openReview(expedienteId: number) {
    setReviewLoading(true)
    setReviewError('')
    setError('')
    setMessage('')
    try {
      const payload = await fetchPracticasReviewDetail(expedienteId)
      const currentHours = Math.max(
        Number(payload.HorasReconocidas || 0),
        Number(payload.HorasAsistenciaValidadas || 0),
      )
      setReviewDetail(payload)
      setReviewHours(currentHours > 0 ? String(currentHours) : '')
      setReviewCorroborated(false)
      setReviewObservation('')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el expediente para revisión.')
    } finally {
      setReviewLoading(false)
    }
  }

  function closeReview() {
    if (reviewLoading) return
    setReviewDetail(null)
    setReviewHours('')
    setReviewCorroborated(false)
    setReviewObservation('')
    setReviewError('')
  }

  async function submitReview(decision: PracticasReviewDecision) {
    if (!reviewDetail) return
    const hours = Number(reviewHours.replace(',', '.'))
    const observation = reviewObservation.trim()
    if (!Number.isFinite(hours) || hours < 0) {
      setReviewError('Ingrese una cantidad válida de horas verificadas.')
      return
    }
    if ((decision === 'OBSERVAR' || decision === 'RECHAZAR') && !observation) {
      setReviewError('Registre el motivo de la observación o del rechazo.')
      return
    }
    if (decision === 'APROBAR') {
      if (!reviewDetail.DocumentosCompletos) {
        setReviewError('No se puede finalizar la revisión mientras existan documentos obligatorios pendientes.')
        return
      }
      if (hours < Number(reviewDetail.HorasRequeridas || 0)) {
        setReviewError(`Debe corroborar al menos ${reviewDetail.HorasRequeridas} horas.`)
        return
      }
      if (!reviewCorroborated) {
        setReviewError('Confirme que revisó los documentos y las horas del estudiante.')
        return
      }
    }

    setReviewLoading(true)
    setReviewError('')
    setError('')
    setMessage('')
    try {
      const response = await reviewPracticasExpediente(reviewDetail.ExpedienteId, {
        tipo_proceso_codigo: reviewDetail.TipoProcesoCodigo,
        decision,
        horas_verificadas: hours,
        documentos_corroborados: reviewCorroborated,
        observacion: observation || null,
      })
      const titulationMessage = response.titulacion?.sincronizado
        ? ' El requisito ya se refleja en Titulación.'
        : response.titulacion?.motivo
          ? ` ${response.titulacion.motivo}`
          : ''
      setMessage(`${response.message}${titulationMessage}`)
      setReviewDetail(null)
      setReviewHours('')
      setReviewCorroborated(false)
      setReviewObservation('')
      await loadResponsibleProgress()
      if (isAdmin) await loadAdmin()
    } catch (apiError) {
      setReviewError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la revisión docente.')
    } finally {
      setReviewLoading(false)
    }
  }

  async function searchTeachers() {
    if (!teacherSearch.trim()) {
      setError('Ingrese nombre, cédula o código del docente.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await searchPracticasActiveTeachers(teacherSearch, 20)
      setTeacherOptions(payload.items || [])
      if (!(payload.items || []).length) setMessage('No se encontraron docentes con ese nombre, cédula o código.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar docentes.')
    } finally {
      setLoading(false)
    }
  }

  function selectTeacher(teacher: AcademicTeacherOption) {
    setResponsableForm((current) => ({
      ...current,
      nombre_responsable: teacher.descripcion || teacher.login || '',
      cedula_responsable: teacher.cedula || '',
      correo_responsable: teacher.correo || teacher.correo_personal || '',
      codigo_docente: teacher.codigo_doc || '',
      rol_responsable: 'RESPONSABLE',
    }))
    setTeacherSearch(`${teacher.descripcion || teacher.login || ''} ${teacher.cedula || ''}`.trim())
    setTeacherOptions([])
  }

  function toggleStudent(key: string) {
    const student = adminElegibles.find((item) => eligibilityKey(item) === key)
    if (student && !canRegisterInstitutionalEnrollment(student)) {
      setError('El estudiante no cumple tercer semestre. Suba una autorización para habilitarlo.')
      return
    }
    setSelectedStudents((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ))
  }

  function toggleAllStudents() {
    const keys = adminElegibles
      .filter(canRegisterInstitutionalEnrollment)
      .map(eligibilityKey)
      .filter(Boolean)
    setSelectedStudents((current) => (
      keys.length > 0 && keys.every((key) => current.includes(key)) ? [] : keys
    ))
  }

  function toggleEnrollment(expedienteId: number) {
    setSelectedEnrollmentIds((current) => (
      current.includes(expedienteId)
        ? current.filter((item) => item !== expedienteId)
        : [...current, expedienteId]
    ))
  }

  function toggleAllEnrollments() {
    const ids = periodEnrollments.map((item) => Number(item.ExpedienteId)).filter(Boolean)
    setSelectedEnrollmentIds((current) => (
      ids.length > 0 && ids.every((id) => current.includes(id)) ? [] : ids
    ))
  }

  async function uploadAutorizacion(student: PracticasEligibilityItem, file: File | null) {
    if (!file) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await uploadPracticasAutorizacion({
        tipo_proceso_codigo: selectedProcess,
        codigo_estud: Number(student.codigo_estud),
        codigo_periodo: String(student.CodigoPeriodo || selectedSourcePeriod),
        file,
      })
      setMessage(String(response.message || 'Autorización cargada correctamente.'))
      await loadAdminEligibility()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo subir la autorización.')
    } finally {
      setSaving(false)
    }
  }

  async function loadAll() {
    setError('')
    setMessage('')
    setLoading(true)
    try {
      await loadCatalog()
      if (!isAdmin && !isResponsible) await loadStudent()
      if (isAdmin) {
        await loadAdmin()
        await loadPeriodDesignations()
      }
      if (isResponsible || isAdmin) await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar prácticas institucionales.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProcess])

  async function saveEnrollment() {
    if (!selectedSourcePeriod) {
      setError('Seleccione el período académico del estudiante para cargar la lista.')
      return
    }
    if (!selectedPeriod) {
      setError('Seleccione el período institucional donde se controlará el cumplimiento.')
      return
    }
    if (!selectedStudents.length) {
      setError('Seleccione al menos un estudiante para inscribir en el proceso institucional.')
      return
    }
    if (!uploadStartDate || !uploadEndDate) {
      setError('Defina la fecha de inicio y la fecha de cierre para la carga documental.')
      return
    }
    if (uploadEndDate < uploadStartDate) {
      setError('La fecha de cierre documental no puede ser anterior a la fecha de inicio.')
      return
    }

    const selectedItems = adminElegibles.filter((item) => selectedStudents.includes(eligibilityKey(item)))
    if (selectedItems.length !== selectedStudents.length) {
      setError('La selección de estudiantes cambió. Cargue nuevamente la lista antes de registrar la inscripción.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await enrollPracticasStudents({
        tipo_proceso_codigo: selectedProcess,
        codigo_periodo: selectedPeriod,
        fecha_inicio_carga: uploadStartDate,
        fecha_fin_carga: uploadEndDate,
        estudiantes: selectedItems.map((item) => ({
          codigo_estud: Number(item.codigo_estud),
          codigo_carrera: String(item.CodigoCarrera || ''),
          codigo_periodo_origen: String(item.CodigoPeriodo || ''),
        })),
        observacion: `Inscripción institucional de cumplimiento en ${processLabel(selectedProcess)}.`,
      })
      setSelectedStudents([])
      setMessage(String(response.message || 'Las inscripciones institucionales fueron registradas correctamente.'))
      await loadAdmin()
      await loadAdminEligibility()
      await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la inscripción institucional de prácticas.')
    } finally {
      setSaving(false)
    }
  }

  async function saveResponsable() {
    if (!selectedPeriod) {
      setError('Seleccione el período institucional de las inscripciones.')
      return
    }
    if (!responsableForm.codigo_docente.trim() || !responsableForm.nombre_responsable.trim()) {
      setError('Seleccione un docente del buscador para asignarlo como responsable.')
      return
    }
    if (!selectedEnrollmentIds.length) {
      setError('Seleccione al menos una inscripción antes de asignar al responsable.')
      return
    }
    const availableIds = new Set(periodEnrollments.map((item) => Number(item.ExpedienteId)))
    if (selectedEnrollmentIds.some((id) => !availableIds.has(id))) {
      setError('La lista de inscripciones cambió. Actualice la información y vuelva a seleccionar.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await assignPracticasEnrollmentResponsable({
        tipo_proceso_codigo: selectedProcess,
        codigo_periodo: selectedPeriod,
        nombre_responsable: responsableForm.nombre_responsable.trim(),
        cedula_responsable: responsableForm.cedula_responsable.trim() || null,
        correo_responsable: responsableForm.correo_responsable.trim() || null,
        codigo_docente: responsableForm.codigo_docente.trim(),
        rol_responsable: 'RESPONSABLE',
        expediente_ids: selectedEnrollmentIds,
      })
      setResponsableForm({
        nombre_responsable: '',
        cedula_responsable: '',
        correo_responsable: '',
        codigo_docente: '',
        rol_responsable: 'RESPONSABLE',
      })
      setTeacherSearch('')
      setSelectedEnrollmentIds([])
      setMessage(String(response.message || 'El responsable fue asignado correctamente.'))
      await loadCatalog()
      await loadAdmin()
      await loadPeriodDesignations()
      await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar el responsable.')
    } finally {
      setSaving(false)
    }
  }

  async function downloadCarta(item: PracticasExpedienteItem) {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const blob = await downloadPracticasCartaCompromiso(item.ExpedienteId)
      downloadBlob(blob, `carta-compromiso-${item.CodigoExpediente || item.ExpedienteId}.pdf`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la carta compromiso.')
    } finally {
      setSaving(false)
    }
  }

  function openDocumentExpedient(item: PracticasExpedienteItem) {
    const identification = String(item.Cedula_Est || '').trim()
    if (!identification) {
      setError('El expediente no tiene una cédula estudiantil válida para abrir la carpeta documental.')
      return
    }
    setError('')
    setMessage('')
    setDocumentExpedient({
      identification,
      process: item.TipoProcesoCodigo === 'VIN' ? 'VIN' : 'PPF',
    })
  }

  function openOperationalDocuments(identification: string) {
    const normalized = identification.trim()
    if (!normalized) {
      setError('El expediente no tiene una cédula estudiantil válida para abrir la carpeta documental.')
      return
    }
    setError('')
    setMessage('')
    setDocumentExpedient({ identification: normalized, process: selectedProcess })
  }

  function closeDocumentExpedient() {
    setDocumentExpedient(null)
    if (isResponsible) {
      void loadResponsibleProgress()
    } else if (isAdmin) {
      void loadAdmin()
      void loadResponsibleProgress()
    } else {
      void loadStudent()
    }
  }

  function selectProcess(process: PracticasProcessCode) {
    if (process === selectedProcess) return
    setSelectedProcess(process)
    setActiveWorkspace(isAdmin ? 'gestion' : 'seguimiento')
    setSelectedPeriod('')
    setSelectedSourcePeriod('')
    setUploadStartDate('')
    setUploadEndDate('')
    setSelectedStudents([])
    setSelectedEnrollmentIds([])
    setAdminElegibles([])
    closeReview()
    onProcessChange?.(process)
  }

  return (
    <section className={`portal-student-page practicas-page${isStudent ? ' practicas-page--student' : ''}`}>
      <header className="portal-student-hero practicas-hero">
        <div className="practicas-hero__copy">
          <small>Prácticas institucionales</small>
          <h1>{processLabel(selectedProcess)}</h1>
          <p>
            {displayName} · {selectedProcess === 'VIN'
              ? 'Inscripción institucional, proyecto, actividades, indicadores, evidencias y cierre.'
              : 'Inscripción institucional, plan, horas, documentos, evaluación y cierre.'}
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}

      <div className="practicas-overview-layout">
        <nav className="practicas-process-selector" aria-label="Procesos de prácticas institucionales">
          {PROCESS_OPTIONS.map((item) => (
            <button
              key={item.code}
              type="button"
              className={selectedProcess === item.code ? 'is-active' : ''}
              aria-pressed={selectedProcess === item.code}
              onClick={() => selectProcess(item.code)}
            >
              <span>{item.code}</span>
              <strong>{item.short}</strong>
              <small>{item.description}</small>
            </button>
          ))}
        </nav>

        <section className="portal-dashboard-overview practicas-summary">
          <article>
            <span>Proceso</span>
            <strong>{processLabel(selectedProcess)}</strong>
            <p>{selectedProcess === 'PPF' ? 'Carta compromiso, certificados, asistencia, actividades y evaluación.' : 'Anexo 1, Anexo 2, evidencias y certificado.'}</p>
          </article>
          <article>
            <span>Documentos</span>
            <strong>{processDocuments.length}</strong>
            <p>{processDocuments.filter((item) => item.EsObligatorio).length} obligatorio(s)</p>
          </article>
          <article>
            <span>Responsables</span>
            <strong>{processResponsibles.length}</strong>
            <p>Activos para {processLabel(selectedProcess)}</p>
          </article>
        </section>
      </div>

      <div className="practicas-navigation-layout">
        <aside className="practicas-enrollment-boundary" aria-label="Alcance de la inscripción institucional">
          <div>
            <strong>Inscripción institucional de cumplimiento</strong>
            <span>Se registra únicamente en el módulo de prácticas.</span>
          </div>
          <div>
            <strong>Matrícula académica sin cambios</strong>
            <span>Carrera, estudiante y período se consultan como referencia de solo lectura.</span>
          </div>
        </aside>

        <nav className="practicas-workspace-tabs" aria-label={`Apartados de ${processLabel(selectedProcess)}`}>
          {workspaceOptions.map((item) => (
            <button
              key={item.code}
              type="button"
              className={activeWorkspace === item.code ? 'is-active' : ''}
              aria-pressed={activeWorkspace === item.code}
              onClick={() => setActiveWorkspace(item.code)}
            >
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </button>
          ))}
        </nav>
      </div>

      {activeWorkspace !== 'gestion' ? (
        <PracticasSeguimientoPanel
          process={selectedProcess}
          role={role}
          mode={activeWorkspace === 'catalogos' ? 'catalogos' : 'seguimiento'}
          onOpenDocuments={openOperationalDocuments}
        />
      ) : null}

      {activeWorkspace === 'gestion' ? (isResponsible ? (
        <section className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <span>Responsable</span>
            <strong>Corroboración y aprobación de {processLabel(selectedProcess).toLowerCase()}</strong>
          </div>

          <section className="practicas-progress-card">
            <div className="practicas-progress-head">
              <div>
                <span>Avance general</span>
                <strong>{percentValue(responsableProgress?.summary?.avance).toFixed(2)}%</strong>
              </div>
              <button type="button" className="secondary-action" onClick={loadResponsibleProgress} disabled={loading || saving}>
                Actualizar avance
              </button>
            </div>
            <div className="practicas-progress-bar" aria-label="Avance general">
              <span style={{ width: `${percentValue(responsableProgress?.summary?.avance)}%` }} />
            </div>
            <div className="practicas-progress-metrics">
              <span><b>{responsableProgress?.summary?.expedientes || 0}</b> expediente(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_cargados || 0}</b> cargado(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_validados || 0}</b> validado(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_pendientes || 0}</b> pendiente(s)</span>
            </div>
          </section>

          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Plazo documental</th>
                  <th>Estado</th>
                  <th>Horas</th>
                  <th>Documentos</th>
                  <th>Avance</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {responsableProgress?.items?.length ? responsableProgress.items.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</td>
                    <td>
                      <strong>{valueOrDash(item.Apellidos_nombre)}</strong>
                      <small>{valueOrDash(item.Cedula_Est)}</small>
                    </td>
                    <td>{valueOrDash(item.Carrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td className="practicas-upload-window">
                      <strong>{uploadWindowLabel(item.FechaInicioCarga, item.FechaFinCarga)}</strong>
                      <small>{isUploadWindowOpen(item.FechaInicioCarga, item.FechaFinCarga) ? 'Carga habilitada' : 'Carga cerrada'}</small>
                    </td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>
                      <strong>{Number(item.HorasReconocidas || 0).toFixed(2)} / {Number(item.HorasRequeridas || (selectedProcess === 'PPF' ? 240 : 60)).toFixed(0)}</strong>
                      <small>Horas corroboradas</small>
                    </td>
                    <td>
                      <strong>{item.TotalDocumentos || 0} / {item.DocumentosRequeridos || 0}</strong>
                      <small>{item.DocumentosValidados || 0} validado(s)</small>
                    </td>
                    <td>
                      <div className="practicas-mini-progress">
                        <span style={{ width: `${percentValue(item.Avance)}%` }} />
                      </div>
                      <small>{percentValue(item.Avance).toFixed(2)}%</small>
                    </td>
                    <td>
                      <div className="practicas-row-actions">
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => void openReview(item.ExpedienteId)}
                          disabled={reviewLoading || saving}
                        >
                          Revisar
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => openDocumentExpedient(item)}
                          disabled={saving || !String(item.Cedula_Est || '').trim()}
                        >
                          Cargar documentos
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={10}>No existen expedientes asignados al responsable para este proceso.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : !isAdmin ? (
        <section className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <span>Estudiante</span>
            <strong>Mis prácticas asignadas</strong>
          </div>
          <p className="portal-muted">
            Administración registra tu inscripción institucional y el docente responsable asignado carga la documentación. Aquí puedes consultar el cumplimiento, revisar cada archivo y descargar tu carta compromiso sin modificar la matrícula académica.
          </p>

          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Proceso</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Plazo documental</th>
                  <th>Cumplimiento documental</th>
                  <th>Estado</th>
                  <th>Responsable</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredStudentExpedientes.length ? filteredStudentExpedientes.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</td>
                    <td>{processLabel(String(item.TipoProcesoCodigo))}</td>
                    <td>{valueOrDash(item.Carrera || item.CodigoCarrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td className="practicas-upload-window">
                      <strong>{uploadWindowLabel(item.FechaInicioCarga, item.FechaFinCarga)}</strong>
                      <small>{isUploadWindowOpen(item.FechaInicioCarga, item.FechaFinCarga) ? 'Plazo vigente' : 'Plazo finalizado'}</small>
                    </td>
                    <td>
                      <div className="practicas-document-progress">
                        <div>
                          <strong>{percentValue(item.AvanceDocumental).toFixed(0)}%</strong>
                          <small>{item.DocumentosCargados || 0} de {item.DocumentosRequeridos || 0}</small>
                        </div>
                        <div
                          className="practicas-mini-progress"
                          role="progressbar"
                          aria-label="Cumplimiento documental"
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={percentValue(item.AvanceDocumental)}
                        >
                          <span style={{ width: `${percentValue(item.AvanceDocumental)}%` }} />
                        </div>
                        <small>{item.DocumentosPendientes ? `${item.DocumentosPendientes} pendiente(s)` : 'Documentación completa'}</small>
                      </div>
                    </td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>{valueOrDash(item.DocenteTutor || item.NombreResponsable)}</td>
                    <td>
                      <div className="practicas-row-actions">
                        <button type="button" className="secondary-action" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                          Ver documentos
                        </button>
                        {item.TipoProcesoCodigo === 'PPF' ? (
                          <button type="button" className="secondary-action" onClick={() => void downloadCarta(item)} disabled={saving}>
                            Descargar carta
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={9}>No existen expedientes asignados para este proceso.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="student-card student-card--wide matricula-panel practicas-admin-card">
          <div className="section-title">
            <span>Administrador</span>
            <strong>Flujo institucional de {processLabel(selectedProcess).toLowerCase()}</strong>
          </div>

          <p className="portal-muted">
            Primero registre la inscripción institucional y luego asigne el responsable. Solo ese docente podrá cargar la documentación; el estudiante consultará su porcentaje de cumplimiento sin alterar materias ni matrícula académica.
          </p>

          <div className="practicas-workflow" aria-label="Etapas del proceso">
            <article className="practicas-workflow-step is-current">
              <span>1</span>
              <div><strong>Inscripción</strong><small>Registrar estudiantes para el control de cumplimiento.</small></div>
            </article>
            <article className="practicas-workflow-step">
              <span>2</span>
              <div><strong>Responsable</strong><small>Asignar quién revisará cada inscripción.</small></div>
            </article>
            <article className="practicas-workflow-step">
              <span>3</span>
              <div><strong>Documentación</strong><small>Carga del expediente estudiantil.</small></div>
            </article>
            <article className="practicas-workflow-step">
              <span>4</span>
              <div><strong>Cumplimiento</strong><small>Revisión y aprobación del responsable.</small></div>
            </article>
          </div>

          <section className="practicas-stage practicas-stage--enrollment">
            <header className="practicas-stage__header">
              <span>1</span>
              <div>
                <strong>Inscripción institucional de estudiantes</strong>
                <small>Seleccione la referencia académica y el período en el que se controlará la práctica.</small>
              </div>
            </header>

          <div className="matricula-acad-form practicas-form practicas-responsable-form">
            <label>
              <span>Período académico de referencia ({periodos.length} período(s))</span>
              <select
                value={selectedSourcePeriod}
                onChange={(event) => {
                  setSelectedSourcePeriod(event.target.value)
                  setSelectedStudents([])
                  setAdminElegibles([])
                }}
              >
                <option value="">Seleccione período origen</option>
                {periodos.map((periodo) => (
                  <option key={`source-${periodo.CodigoPeriodo}`} value={periodo.CodigoPeriodo}>
                    {periodLabel(periodo)} · {periodo.TotalEstudiantes || 0} estudiante(s)
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Período institucional del proceso ({periodos.length} período(s))</span>
              <select
                value={selectedPeriod}
                onChange={(event) => {
                  const periodCode = event.target.value
                  const period = periodos.find((item) => String(item.CodigoPeriodo) === periodCode)
                  setSelectedPeriod(periodCode)
                  setUploadStartDate(dateInputValue(period?.FechaInicio))
                  setUploadEndDate(dateInputValue(period?.FechaFin))
                  setSelectedStudents([])
                  setSelectedEnrollmentIds([])
                }}
              >
                <option value="">Seleccione período destino</option>
                {periodos.map((periodo) => (
                  <option key={`target-${periodo.CodigoPeriodo}`} value={periodo.CodigoPeriodo}>
                    {periodLabel(periodo)}
                  </option>
                ))}
              </select>
            </label>
            <div className="practicas-period-detail">
              <strong>Período origen</strong>
              <span>{sourcePeriodDetail ? periodLabel(sourcePeriodDetail) : 'Seleccione período origen'}</span>
              <small>
                Fechas: {valueOrDash(sourcePeriodDetail?.FechaInicio)} a {valueOrDash(sourcePeriodDetail?.FechaFin)} ·
                Registro: {valueOrDash(sourcePeriodDetail?.DetalleRegistro)} ·
                Estado académico: {valueOrDash(sourcePeriodDetail?.EstadoEducativo)} ·
                Estudiantes: {sourcePeriodDetail?.TotalEstudiantes || 0}
              </small>
            </div>
            <div className="practicas-period-detail">
              <strong>Período destino</strong>
              <span>{targetPeriodDetail ? periodLabel(targetPeriodDetail) : 'Seleccione período destino'}</span>
              <small>
                Fechas: {valueOrDash(targetPeriodDetail?.FechaInicio)} a {valueOrDash(targetPeriodDetail?.FechaFin)} ·
                Registro: {valueOrDash(targetPeriodDetail?.DetalleRegistro)} ·
                Estado académico: {valueOrDash(targetPeriodDetail?.EstadoEducativo)} ·
                Nota aprobar: {valueOrDash(targetPeriodDetail?.NotaAprobar)}
              </small>
            </div>
            <div className="practicas-upload-window-form">
              <label>
                <span>Inicio de carga documental</span>
                <input
                  type="date"
                  value={uploadStartDate}
                  max={uploadEndDate || undefined}
                  onChange={(event) => setUploadStartDate(event.target.value)}
                  required
                />
              </label>
              <label>
                <span>Cierre de carga documental</span>
                <input
                  type="date"
                  value={uploadEndDate}
                  min={uploadStartDate || undefined}
                  onChange={(event) => setUploadEndDate(event.target.value)}
                  required
                />
              </label>
              <p>
                Este plazo se aplica a la carga de documentos de todas las inscripciones seleccionadas.
                La descarga de formatos permanece disponible.
              </p>
            </div>
            <label className="practicas-form__search">
              <span>Filtrar estudiantes del período</span>
              <input
                value={eligibilitySearch}
                onChange={(event) => setEligibilitySearch(event.target.value)}
                placeholder="Nombre, cédula, carrera o período"
              />
            </label>
          </div>

          <div className="practicas-student-picker">
            <div className="practicas-picker-head">
              <strong>Estudiantes a inscribir para cumplimiento</strong>
              <button type="button" className="secondary-action" onClick={loadAdminEligibility} disabled={loading || !selectedSourcePeriod}>
                Cargar estudiantes
              </button>
              <button type="button" className="ghost-button" onClick={toggleAllStudents} disabled={!adminElegibles.length}>
                {adminElegibles.filter(canRegisterInstitutionalEnrollment).length > 0
                  && adminElegibles.filter(canRegisterInstitutionalEnrollment).every((item) => selectedStudents.includes(eligibilityKey(item)))
                  ? 'Quitar todos'
                  : 'Seleccionar habilitados'}
              </button>
            </div>
            <p>{selectedStudents.length} de {adminElegibles.length} estudiante(s) seleccionados desde la referencia académica para el período institucional.</p>
            <div className="practicas-student-list">
              {adminElegibles.length ? adminElegibles.map((student) => {
                const key = eligibilityKey(student)
                const canEnroll = canRegisterInstitutionalEnrollment(student)
                const hasAuthorization = Boolean(student.TieneAutorizacion || student.AutorizacionId)
                return (
                  <label key={`${student.codigo_estud}-${student.CodigoCarrera}-${student.CodigoPeriodo}`} className={canEnroll ? '' : 'practicas-student-list__blocked'}>
                    <input
                      type="checkbox"
                      checked={selectedStudents.includes(key)}
                      disabled={!canEnroll}
                      onChange={() => toggleStudent(key)}
                    />
                    <span>
                      <b>{valueOrDash(student.Apellidos_nombre)}</b>
                      <small>Cédula: {valueOrDash(student.Cedula_Est)}</small>
                      <small>Carrera: {valueOrDash(student.Carrera)}</small>
                      <small>Período origen: {valueOrDash(student.NombrePeriodo || student.CodigoPeriodo)}</small>
                      <small>Semestre detectado: {valueOrDash(student.SemestreMaximo)}</small>
                      <small>Estado: {canEnroll ? (student.EsElegible ? 'Cumple tercer semestre' : 'Habilitado con autorización') : valueOrDash(student.MotivoElegibilidad || 'No cumple tercer semestre')}</small>
                      {hasAuthorization ? (
                        <small>Autorización: {valueOrDash(student.AutorizacionArchivo || student.AutorizacionId)}</small>
                      ) : null}
                    </span>
                    {!canEnroll ? (
                      <label className="ghost-button practicas-upload-button practicas-authorization-button">
                        Subir autorización
                        <input
                          type="file"
                          accept="application/pdf,.pdf,image/png,image/jpeg,.png,.jpg,.jpeg"
                          onChange={(event) => {
                            void uploadAutorizacion(student, event.target.files?.[0] || null)
                            event.currentTarget.value = ''
                          }}
                          disabled={saving}
                        />
                      </label>
                    ) : null}
                  </label>
                )
              }) : (
                <span className="portal-muted">Seleccione un período y cargue los estudiantes elegibles.</span>
              )}
            </div>
          </div>

          <div className="practicas-stage__actions">
            <button type="button" className="primary-action" onClick={saveEnrollment} disabled={saving || !selectedStudents.length}>
              {saving ? 'Registrando inscripción...' : `Inscribir ${selectedStudents.length || ''} estudiante(s)`}
            </button>
          </div>
          </section>

          <section className="practicas-stage practicas-stage--responsible">
            <header className="practicas-stage__header">
              <span>2</span>
              <div>
                <strong>Asignación del responsable</strong>
                <small>Solo se muestran estudiantes previamente inscritos en el proceso y período seleccionado.</small>
              </div>
            </header>

            <div className="matricula-acad-form practicas-form practicas-responsable-form">
              <label>
                <span>Período de las inscripciones</span>
                <select
                  value={selectedPeriod}
                  onChange={(event) => {
                    setSelectedPeriod(event.target.value)
                    setSelectedEnrollmentIds([])
                  }}
                >
                  <option value="">Seleccione un período</option>
                  {periodos.map((periodo) => (
                    <option key={`responsible-${periodo.CodigoPeriodo}`} value={periodo.CodigoPeriodo}>
                      {periodLabel(periodo)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Buscar docente responsable</span>
                <input
                  value={teacherSearch}
                  onChange={(event) => setTeacherSearch(event.target.value)}
                  placeholder="Nombre, cédula o código docente"
                />
              </label>
              <button type="button" className="secondary-action" onClick={searchTeachers} disabled={loading || !selectedPeriod}>
                Buscar docente
              </button>
              <label>
                <span>Docente seleccionado</span>
                <input value={responsableForm.nombre_responsable} readOnly placeholder="Seleccione un docente del listado" />
              </label>
              <label>
                <span>Cédula</span>
                <input value={responsableForm.cedula_responsable} readOnly placeholder="-" />
              </label>
              <label>
                <span>Código docente</span>
                <input value={responsableForm.codigo_docente} readOnly placeholder="-" />
              </label>
            </div>

            {teacherOptions.length ? (
              <div className="practicas-teacher-results">
                {teacherOptions.map((teacher) => (
                  <button key={`${teacher.codigo_doc}-${teacher.cedula || ''}`} type="button" onClick={() => selectTeacher(teacher)}>
                    <strong>{valueOrDash(teacher.descripcion || teacher.login)}</strong>
                    <span>{valueOrDash(teacher.cedula)} · Código {valueOrDash(teacher.codigo_doc)} · {valueOrDash(teacher.correo || teacher.correo_personal)}</span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="practicas-student-picker practicas-enrollment-picker">
              <div className="practicas-picker-head">
                <strong>Inscripciones disponibles para asignación</strong>
                <button type="button" className="secondary-action" onClick={loadAdmin} disabled={loading || !selectedPeriod}>
                  Actualizar inscripciones
                </button>
                <button type="button" className="ghost-button" onClick={toggleAllEnrollments} disabled={!periodEnrollments.length}>
                  {periodEnrollments.length > 0 && periodEnrollments.every((item) => selectedEnrollmentIds.includes(Number(item.ExpedienteId)))
                    ? 'Quitar todas'
                    : 'Seleccionar todas'}
                </button>
              </div>
              <p>{selectedEnrollmentIds.length} de {periodEnrollments.length} inscripción(es) seleccionada(s).</p>
              <div className="practicas-student-list">
                {periodEnrollments.length ? periodEnrollments.map((item) => (
                  <label key={`enrollment-${item.ExpedienteId}`}>
                    <input
                      type="checkbox"
                      checked={selectedEnrollmentIds.includes(Number(item.ExpedienteId))}
                      onChange={() => toggleEnrollment(Number(item.ExpedienteId))}
                    />
                    <span>
                      <b>{valueOrDash(item.Apellidos_nombre)}</b>
                      <small>Cédula: {valueOrDash(item.Cedula_Est)}</small>
                      <small>Carrera: {valueOrDash(item.Carrera || item.CodigoCarrera)}</small>
                      <small>Expediente: {valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</small>
                      <small>Responsable actual: {valueOrDash(item.DocenteTutor || item.NombreResponsable)}</small>
                    </span>
                  </label>
                )) : (
                  <span className="portal-muted">No hay inscripciones en este período. Complete primero la etapa 1.</span>
                )}
              </div>
            </div>

            <div className="practicas-stage__actions">
              <button
                type="button"
                className="primary-action"
                onClick={saveResponsable}
                disabled={saving || !selectedEnrollmentIds.length || !responsableForm.codigo_docente}
              >
                {saving ? 'Asignando...' : `Asignar responsable a ${selectedEnrollmentIds.length || ''} inscripción(es)`}
              </button>
            </div>

          <div className="practicas-period-designations">
              <strong>Responsables vigentes por período</strong>
            {periodDesignations.length ? periodDesignations.map((item) => (
              <div key={item.DesignacionId}>
                <span>{valueOrDash(item.CodigoPeriodo)}</span>
                <b>{valueOrDash(item.NombreResponsable)}</b>
                <small>Origen {valueOrDash(item.CodigoPeriodoOrigen || item.PeriodoOrigen)} · Destino {valueOrDash(item.CodigoPeriodo)} · Código docente {valueOrDash(item.CodigoDocente)} · {valueOrDash(item.RolResponsable)} · Cumple: {item.CumpleRequisitos ? 'Sí' : 'No'}</small>
              </div>
            )) : (
              <p>No hay designaciones activas para este proceso.</p>
            )}
          </div>
          </section>

          <section className="practicas-stage practicas-stage--documents">
            <header className="practicas-stage__header">
              <span>3</span>
              <div>
                <strong>Carga de información y expediente</strong>
                <small>El docente responsable carga los documentos requeridos; administración y estudiante conservan acceso de consulta.</small>
              </div>
            </header>
          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Plazo documental</th>
                  <th>Estado</th>
                  <th>Responsable</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {periodEnrollments.length ? periodEnrollments.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente)}</td>
                    <td>
                      <strong>{valueOrDash(item.Apellidos_nombre)}</strong>
                      <small>{valueOrDash(item.Cedula_Est)}</small>
                    </td>
                    <td>{valueOrDash(item.Carrera || item.CodigoCarrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td className="practicas-upload-window">
                      <strong>{uploadWindowLabel(item.FechaInicioCarga, item.FechaFinCarga)}</strong>
                      <small>{isUploadWindowOpen(item.FechaInicioCarga, item.FechaFinCarga) ? 'Carga habilitada' : 'Carga cerrada'}</small>
                    </td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>{valueOrDash(item.DocenteTutor || item.NombreResponsable)}</td>
                    <td>
                      <button type="button" className="secondary-action" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                        Expediente
                      </button>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8}>No existen expedientes para el filtro seleccionado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </section>

          <section className="practicas-stage practicas-stage--review">
            <header className="practicas-stage__header">
              <span>4</span>
              <div>
                <strong>Verificación de cumplimiento</strong>
                <small>El responsable corroborará documentos, horas y requisitos antes de aprobar u observar el expediente.</small>
              </div>
              <button type="button" className="secondary-action" onClick={loadResponsibleProgress} disabled={loading || saving}>
                Actualizar cumplimiento
              </button>
            </header>

            <section className="practicas-progress-card">
              <div className="practicas-progress-head">
                <div>
                  <span>Avance del período seleccionado</span>
                  <strong>{percentValue(adminReviewSummary.avance).toFixed(2)}%</strong>
                </div>
              </div>
              <div className="practicas-progress-bar" aria-label="Avance del período seleccionado">
                <span style={{ width: `${percentValue(adminReviewSummary.avance)}%` }} />
              </div>
              <div className="practicas-progress-metrics">
                <span><b>{adminReviewSummary.expedientes}</b> expediente(s)</span>
                <span><b>{adminReviewSummary.documentos_cargados}</b> cargado(s)</span>
                <span><b>{adminReviewSummary.documentos_validados}</b> validado(s)</span>
                <span><b>{adminReviewSummary.documentos_pendientes}</b> pendiente(s)</span>
              </div>
            </section>

            <div className="matricula-table-wrap excel-table-wrap">
              <table className="matricula-table practicas-table">
                <thead>
                  <tr>
                    <th>Expediente</th>
                    <th>Estudiante</th>
                    <th>Carrera</th>
                    <th>Período</th>
                    <th>Plazo documental</th>
                    <th>Estado</th>
                    <th>Horas</th>
                    <th>Documentos</th>
                    <th>Avance</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {adminReviewItems.length ? adminReviewItems.map((item) => (
                    <tr key={`review-${item.ExpedienteId}`}>
                      <td>{valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</td>
                      <td>
                        <strong>{valueOrDash(item.Apellidos_nombre)}</strong>
                        <small>{valueOrDash(item.Cedula_Est)}</small>
                      </td>
                      <td>{valueOrDash(item.Carrera)}</td>
                      <td>{valueOrDash(item.CodigoPeriodo)}</td>
                      <td className="practicas-upload-window">
                        <strong>{uploadWindowLabel(item.FechaInicioCarga, item.FechaFinCarga)}</strong>
                        <small>{isUploadWindowOpen(item.FechaInicioCarga, item.FechaFinCarga) ? 'Carga habilitada' : 'Carga cerrada'}</small>
                      </td>
                      <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                      <td>
                        <strong>{Number(item.HorasReconocidas || 0).toFixed(2)} / {Number(item.HorasRequeridas || (selectedProcess === 'PPF' ? 240 : 60)).toFixed(0)}</strong>
                        <small>Horas corroboradas</small>
                      </td>
                      <td>
                        <strong>{item.TotalDocumentos || 0} / {item.DocumentosRequeridos || 0}</strong>
                        <small>{item.DocumentosValidados || 0} validado(s)</small>
                      </td>
                      <td>
                        <div className="practicas-mini-progress">
                          <span style={{ width: `${percentValue(item.Avance)}%` }} />
                        </div>
                        <small>{percentValue(item.Avance).toFixed(2)}%</small>
                      </td>
                      <td>
                        <div className="practicas-row-actions">
                          <button
                            type="button"
                            className="secondary-action"
                            onClick={() => void openReview(item.ExpedienteId)}
                            disabled={reviewLoading || saving}
                          >
                            Revisar
                          </button>
                          <button type="button" className="ghost-button" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                            Expediente
                          </button>
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={10}>
                        {selectedPeriod
                          ? 'No existen inscripciones de este proceso en el período seleccionado.'
                          : 'Seleccione un período para revisar el cumplimiento.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      )) : null}

      {reviewDetail ? (
        <div className="practicas-expedient-overlay" role="presentation">
          <section className="practicas-review-dialog" role="dialog" aria-modal="true" aria-labelledby="practicas-review-title">
            <header className="practicas-review-dialog__header">
              <div>
                <span>Revisión documental previa</span>
                <h2 id="practicas-review-title">{valueOrDash(reviewDetail.Apellidos_nombre)}</h2>
                <p>
                  {processLabel(reviewDetail.TipoProcesoCodigo)} · {valueOrDash(reviewDetail.Carrera)} ·
                  período {valueOrDash(reviewDetail.Periodo || reviewDetail.CodigoPeriodo)}
                </p>
              </div>
              <button type="button" className="secondary-action" onClick={closeReview} disabled={reviewLoading}>
                Cerrar
              </button>
            </header>

            <div className="practicas-review-summary">
              <article>
                <span>Expediente</span>
                <strong>{valueOrDash(reviewDetail.CodigoExpediente || reviewDetail.ExpedienteId)}</strong>
              </article>
              <article>
                <span>Estado</span>
                <strong className={statusClass(reviewDetail.EstadoCodigo)}>{valueOrDash(reviewDetail.EstadoExpediente || reviewDetail.EstadoCodigo)}</strong>
              </article>
              <article>
                <span>Horas requeridas</span>
                <strong>{Number(reviewDetail.HorasRequeridas || 0).toFixed(0)}</strong>
              </article>
              <article>
                <span>Documentos</span>
                <strong>{reviewDetail.DocumentosDetalle.filter((item) => item.Cargado).length} / {reviewDetail.DocumentosDetalle.length}</strong>
              </article>
              <article className="practicas-upload-window">
                <span>Plazo documental</span>
                <strong>{uploadWindowLabel(reviewDetail.FechaInicioCarga, reviewDetail.FechaFinCarga)}</strong>
                <small>{isUploadWindowOpen(reviewDetail.FechaInicioCarga, reviewDetail.FechaFinCarga) ? 'Carga habilitada' : 'Carga cerrada'}</small>
              </article>
            </div>

            <section className="practicas-review-documents">
              <div className="section-title section-title--inline">
                <span>Corroboración</span>
                <strong>Documentos obligatorios</strong>
              </div>
              <div className="practicas-review-documents__list">
                {reviewDetail.DocumentosDetalle.map((document) => (
                  <article key={document.Codigo} className={document.Cargado ? 'is-loaded' : 'is-missing'}>
                    <div>
                      <strong>{valueOrDash(document.Nombre || document.Codigo)}</strong>
                      <small>{valueOrDash(document.NombreArchivo || 'Sin archivo cargado')}</small>
                    </div>
                    <span className={statusClass(document.Validado ? 'VALIDADO' : document.Cargado ? 'PENDIENTE' : 'RECHAZADO')}>
                      {document.Validado ? 'Validado' : document.Cargado ? 'Por corroborar' : 'Pendiente'}
                    </span>
                    {document.UrlArchivo ? (
                      <a className="ghost-button" href={document.UrlArchivo} target="_blank" rel="noreferrer">
                        Ver
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>

            <div className="practicas-review-form">
              <label>
                <span>Horas verificadas</span>
                <input
                  type="number"
                  min="0"
                  max="10000"
                  step="0.5"
                  value={reviewHours}
                  onChange={(event) => setReviewHours(event.target.value)}
                  disabled={reviewLoading}
                  placeholder={`Mínimo ${reviewDetail.HorasRequeridas}`}
                />
                <small>Se registran como horas reconocidas y de asistencia validadas.</small>
              </label>
              <label>
                <span>Observación o justificación</span>
                <textarea
                  value={reviewObservation}
                  onChange={(event) => setReviewObservation(event.target.value)}
                  disabled={reviewLoading}
                  rows={4}
                  placeholder="Obligatoria cuando se solicitan correcciones."
                />
              </label>
              <label className="practicas-review-corroboration">
                <input
                  type="checkbox"
                  checked={reviewCorroborated}
                  onChange={(event) => setReviewCorroborated(event.target.checked)}
                  disabled={reviewLoading}
                />
                <span>Confirmo que revisé los documentos, las horas y la correspondencia del estudiante, carrera y período.</span>
              </label>
            </div>

            {reviewError ? <p className="form-error practicas-review-error">{reviewError}</p> : null}
            <footer className="practicas-review-actions">
              <button type="button" className="ghost-button" onClick={() => void submitReview('OBSERVAR')} disabled={reviewLoading}>
                Observar
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void submitReview('APROBAR')}
                disabled={
                  reviewLoading
                  || !reviewDetail.PuedeAprobar
                  || !reviewDetail.DocumentosCompletos
                  || !reviewCorroborated
                  || Number(reviewHours.replace(',', '.')) < Number(reviewDetail.HorasRequeridas || 0)
                }
              >
                {reviewLoading ? 'Guardando...' : 'Finalizar revisión y habilitar calificación'}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {documentExpedient ? (
        <div className="practicas-expedient-overlay" role="presentation">
          <div className="practicas-expedient-dialog" role="dialog" aria-modal="true" aria-label="Expediente documental de prácticas">
            <ExpedientesDocumentalesView
              displayName={displayName}
              role={role}
              initialIdentification={documentExpedient.identification}
              moduleFilter={[documentExpedient.process === 'PPF' ? 'PRACTICAS' : 'VINCULACION']}
              embedded
              onClose={closeDocumentExpedient}
            />
          </div>
        </div>
      ) : null}
    </section>
  )
}
