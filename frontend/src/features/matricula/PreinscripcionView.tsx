import { useEffect, useMemo, useState } from 'react'

import {
  approvePreinscriptionCarnetPhoto,
  createPreinscription,
  fetchAcademicEnrollmentDetail,
  fetchAcademicEnrollmentPensum,
  fetchPreinscriptionCarnetPhoto,
  fetchPreinscriptionCatalog,
  fetchPreinscriptions,
  previewAcademicEnrollment,
  rejectPreinscriptionCarnetPhoto,
  registerPreinscriptionCabecera,
  revertPreinscriptionProcess,
  saveAcademicEnrollment,
  updatePreinscriptionDocuments,
  updatePreinscriptionFollowup,
  uploadPreinscriptionCarnetPhoto,
  uploadPreinscriptionDocument,
  validatePreinscriptionCedula,
} from '../../lib/api'
import type {
  AcademicEnrollmentDetailResponse,
  AcademicEnrollmentPayload,
  AcademicEnrollmentPreviewResponse,
  AcademicEnrollmentSubject,
  MatriculaTipo,
  PreinscriptionCabeceraPayload,
  PreinscriptionCatalogResponse,
  PreinscriptionCreatePayload,
  PreinscriptionDocumentsPayload,
  PreinscriptionFollowupPayload,
  PreinscriptionItem,
  PreinscriptionListResponse,
  PreinscriptionPhotoStatus,
  PreinscriptionStage,
} from '../../types/app'

type PreinscripcionViewProps = {
  displayName: string
  role?: string
  activeStage: PreinscriptionStage
  onStageChange: (stage: PreinscriptionStage) => void
}

type DocumentFilter = 'ALL' | 'PENDIENTES' | 'COMPLETOS' | 'CON_CABECERA' | 'SIN_CABECERA'

const documentFilters: Array<{ value: DocumentFilter; label: string }> = [
  { value: 'ALL', label: 'Todos' },
  { value: 'PENDIENTES', label: 'Docs pendientes' },
  { value: 'COMPLETOS', label: 'Docs completos' },
  { value: 'CON_CABECERA', label: 'Con pago' },
  { value: 'SIN_CABECERA', label: 'Sin pago' },
]

type IntegratedPreinscriptionService = {
  key: 'datos' | 'carnet' | 'finanzas' | 'homologacion' | 'paso-1' | 'paso-2'
  title: string
  description: string
  requirement: string
  stage: PreinscriptionStage
  actionLabel: string
  tables: string[]
  ready?: boolean
}

const integratedPreinscriptionServices: IntegratedPreinscriptionService[] = [
  {
    key: 'datos',
    title: 'Datos y curriculum',
    description: 'Actualizacion de datos, historial, hoja de vida y soportes del estudiante.',
    requirement: 'Requiere estudiante creado',
    stage: 'inscritos',
    actionLabel: 'Ver estudiante',
    tables: ['ESTUDIANTE_ACTUALIZACION_DATOS', 'ESTUDIANTE_CURRICULUM', 'ESTUDIANTE_CV_ITEM'],
  },
  {
    key: 'carnet',
    title: 'Carnetizacion',
    description: 'Foto, validacion administrativa, solicitud y emision del carnet institucional.',
    requirement: 'Requiere documentos base',
    stage: 'documentos',
    actionLabel: 'Gestionar documentos',
    tables: ['ESTUDIANTE_IMAGEN', 'ESTUDIANTE_FOTO_CARNET_SOLICITUD', 'CARNET_SOLICITUD', 'CARNET_ESTUDIANTE'],
  },
  {
    key: 'finanzas',
    title: 'Finanzas y estado de cuenta',
    description: 'Rubros, obligaciones, pagos, comprobantes y saldos por estudiante.',
    requirement: 'Requiere pago/convenio',
    stage: 'cabecera',
    actionLabel: 'Cabecera matricula',
    tables: ['FIN_RUBRO', 'FIN_OBLIGACION', 'FIN_PAGO', 'FIN_PAGO_APLICACION'],
  },
  {
    key: 'homologacion',
    title: 'Matricula inicial',
    description: 'Matricula de materias del primer nivel para cerrar el proceso de admisiones.',
    requirement: 'Requiere estudiante creado',
    stage: 'materias',
    actionLabel: 'Matricular primer nivel',
    tables: ['CARRERAXESTUD', 'MATERIASXESTUD', 'MATERIA', 'PENSUM'],
  },
]

const academicEnrollmentRoles = new Set(['ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN', 'SOPORTE', 'ACADEMICO', 'BIENESTAR', 'ADMISIONES'])

function normalizeRoleKey(role?: string) {
  return String(role || '')
    .trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function boolLabel(value?: boolean): string {
  return value ? 'Si' : 'No'
}

function photoStatusLabel(status?: string): string {
  const normalized = String(status || 'SIN_FOTO').toUpperCase()
  if (normalized === 'APROBADA') return 'Aprobada'
  if (normalized === 'PENDIENTE') return 'Pendiente de aprobacion'
  if (normalized === 'RECHAZADA') return 'Rechazada'
  if (normalized === 'CANCELADA') return 'Cancelada'
  return 'Sin foto'
}

function photoStatusClass(status?: string): string {
  const normalized = String(status || 'SIN_FOTO').toLowerCase()
  return `preinscripcion-photo__status--${normalized.replace(/[^a-z0-9_-]+/g, '-')}`
}

function toNumber(value: string, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('es-EC', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function documentPayloadFromItem(item: PreinscriptionItem | null): PreinscriptionDocumentsPayload {
  return {
    urlcedula: item?.documentos?.urlcedula || '',
    urltitulo: item?.documentos?.urltitulo || '',
    urldeposito: item?.documentos?.urldeposito || '',
    urlconvenio: item?.documentos?.urlconvenio || '',
  }
}

function documentStatus(item: PreinscriptionItem): string {
  const total = item.documentos?.total_cargados ?? 0
  const required = item.documentos?.total_requeridos ?? 3
  return `${total}/${required}`
}

export function PreinscripcionView({ displayName, role = '', activeStage, onStageChange }: Readonly<PreinscripcionViewProps>) {
  const [catalog, setCatalog] = useState<PreinscriptionCatalogResponse | null>(null)
  const [catalogError, setCatalogError] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [selectedCareer, setSelectedCareer] = useState('')
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>('ALL')
  const [tableFilter, setTableFilter] = useState('')
  const [data, setData] = useState<PreinscriptionListResponse | null>(null)
  const [selectedItem, setSelectedItem] = useState<PreinscriptionItem | null>(null)
  const [documents, setDocuments] = useState<PreinscriptionDocumentsPayload>(() => documentPayloadFromItem(null))
  const [cabeceraValues, setCabeceraValues] = useState({
    fecha_pago: '',
    valor: '0',
    inscrip_valor: '0',
    matri_valor: '0',
    costo_semestre: '0',
    semestres_convenio: '1',
    control_matricula: '1',
    num_cuotas: '1',
    tipo_beca: '',
    porcentaje_beca: '0',
    descuento: '0',
    num_pago: '1',
    detalle_pago: 'Convenio de pago',
    no_deposito: '',
    banco: '',
  })
  const [cabeceraLoading, setCabeceraLoading] = useState(false)
  const [cabeceraError, setCabeceraError] = useState('')
  const [cabeceraMessage, setCabeceraMessage] = useState('')
  const [revertLoading, setRevertLoading] = useState(false)
  const [revertError, setRevertError] = useState('')
  const [followupValues, setFollowupValues] = useState<PreinscriptionFollowupPayload>({
    contacte: '',
    hora: '',
    observacion_contacto: '',
    observacion_ingreso: '',
    cod_lecontacto: '',
    cod_desea_ingresar: '',
    cod_como_conoce: '',
    coddescconve: '',
    coddescconvevalor: '',
    coddescdeptransf: '',
    nom_representante: '',
    num_representante: '',
    prematricula: false,
    proceso_finalizado: false,
    control_ingreso: false,
    correo_enviado: false,
    asignado: false,
  })
  const [followupLoading, setFollowupLoading] = useState(false)
  const [followupError, setFollowupError] = useState('')
  const [followupMessage, setFollowupMessage] = useState('')
  const [followupSearch, setFollowupSearch] = useState('')
  const [followupSearchLoading, setFollowupSearchLoading] = useState(false)
  const [followupSearchError, setFollowupSearchError] = useState('')
  const [followupSearchResults, setFollowupSearchResults] = useState<PreinscriptionItem[]>([])
  const [studentSelectorOpen, setStudentSelectorOpen] = useState(false)
  const [pendingStudentNum, setPendingStudentNum] = useState('')
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [uploadingField, setUploadingField] = useState<string | null>(null)
  const [photoStatus, setPhotoStatus] = useState<PreinscriptionPhotoStatus | null>(null)
  const [photoLoading, setPhotoLoading] = useState(false)
  const [photoError, setPhotoError] = useState('')
  const [photoMessage, setPhotoMessage] = useState('')
  const [studentScreenOpen, setStudentScreenOpen] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState('')
  const [createMessage, setCreateMessage] = useState('')
  const [cedulaValidationLoading, setCedulaValidationLoading] = useState(false)
  const [cedulaValidation, setCedulaValidation] = useState<{
    cedula: string
    exists: boolean
    message: string
  } | null>(null)
  const [createValues, setCreateValues] = useState<PreinscriptionCreatePayload>({
    apellidos_nombre: '',
    nombres: '',
    apellidos: '',
    cedula: '',
    codprov: '',
    codperiodo: '',
    codcarrera: '',
    correo: '',
    telefono: '',
    codmodalida: 1,
    codjornada: 0,
  })
  const [enrollmentPensum, setEnrollmentPensum] = useState<AcademicEnrollmentSubject[]>([])
  const [enrollmentDetail, setEnrollmentDetail] = useState<AcademicEnrollmentDetailResponse | null>(null)
  const [enrollmentSubjectCodes, setEnrollmentSubjectCodes] = useState<string[]>([])
  const [enrollmentLoading, setEnrollmentLoading] = useState(false)
  const [enrollmentError, setEnrollmentError] = useState('')
  const [enrollmentMessage, setEnrollmentMessage] = useState('')
  const [enrollmentPreview, setEnrollmentPreview] = useState<AcademicEnrollmentPreviewResponse | null>(null)
  const [enrollmentPreviewLoading, setEnrollmentPreviewLoading] = useState(false)
  const [enrollmentSaveLoading, setEnrollmentSaveLoading] = useState(false)
  const [enrollmentParallel, setEnrollmentParallel] = useState('A')
  const [enrollmentGroup, setEnrollmentGroup] = useState('1')
  const [enrollmentType, setEnrollmentType] = useState<MatriculaTipo>('R')
  const [enrollmentControl, setEnrollmentControl] = useState('1')
  const [enrollmentFinalizeProcess, setEnrollmentFinalizeProcess] = useState(true)

  const rows = data?.items || []
  const totals = data?.totals || {}
  const normalizedRole = normalizeRoleKey(role)
  const isAdmissionsRole = normalizedRole === 'ADMISIONES'
  const canManageAcademicEnrollment = academicEnrollmentRoles.has(normalizedRole)
  const userRecordCount = totals.usuario_actual ?? totals.mis_registros ?? data?.total ?? 0
  const hasCabecera = Boolean(selectedItem?.en_cabecera_matricula)
  const codigoDocumentacion = selectedItem?.cabecera?.numcodigo || selectedItem?.cabecera?.num_matricula || ''
  const selectedStudentCode = selectedItem?.datos_codigo_estud || selectedItem?.cabecera?.codigo_estud || selectedItem?.codestu || ''
  const selectedStudentName = selectedItem?.apellidos_nombre || [selectedItem?.apellido1, selectedItem?.apellido2, selectedItem?.nombre1, selectedItem?.nombre2].filter(Boolean).join(' ')
  const selectedStudentCedula = selectedItem?.cedula || ''
  const convenioUrl = selectedItem?.documentos?.urlconvenio || ''
  const selectedEnrollmentCareer = selectedItem?.codcarrera || selectedItem?.cabecera?.cod_anio_basica || ''
  const selectedEnrollmentPeriod = selectedItem?.codperiodo || selectedItem?.cabecera?.codigo_periodo || ''
  const integratedServices = useMemo(
    () =>
      integratedPreinscriptionServices
        .filter((service) => service.stage !== 'materias' || canManageAcademicEnrollment)
        .map((service) => {
        const ready =
          service.key === 'finanzas'
            ? hasCabecera
            : service.key === 'carnet'
              ? Boolean(selectedStudentCode && photoStatus?.estado === 'APROBADA')
              : Boolean(selectedStudentCode)
        return { ...service, ready }
      }),
    [canManageAcademicEnrollment, hasCabecera, photoStatus?.estado, selectedStudentCode],
  )
  const admissionProcessServices = useMemo<IntegratedPreinscriptionService[]>(
    () => [
      {
        key: 'paso-1',
        title: 'Paso 1: Inscribir',
        description: selectedItem
          ? 'Estudiante seleccionado para continuar con la matricula.'
          : 'Registra al estudiante o seleccionalo desde inscritos.',
        requirement: selectedItem ? 'Estudiante seleccionado' : 'Requiere registrar o seleccionar estudiante',
        stage: selectedItem ? 'inscritos' : 'registro',
        actionLabel: selectedItem ? 'Ver inscritos' : 'Registrar inscripcion',
        tables: ['PREINSCRIPCION'],
        ready: Boolean(selectedItem),
      },
      {
        key: 'paso-2',
        title: 'Paso 2: Matricular, generar convenio y subir documentacion',
        description: 'Genera la cabecera de matricula, emite el convenio de pago y carga cedula, titulo, deposito, convenio y foto de carnet.',
        requirement: hasCabecera ? 'Matricula/convenio registrados' : 'Requiere estudiante inscrito del paso 1',
        stage: 'documentos',
        actionLabel: 'Matricular y documentar',
        tables: ['CABECERA_MATRICULA', 'DATOS_FACTURA', 'PREINSCRIPCION_DOCUMENTOS', 'ESTUDIANTE_IMAGEN'],
        ready: selectedItem
          ? (selectedItem.documentos?.total_cargados ?? 0) >= (selectedItem.documentos?.total_requeridos ?? 3)
          : false,
      },
    ],
    [hasCabecera, selectedItem],
  )
  const displayedIntegratedServices = isAdmissionsRole ? admissionProcessServices : integratedServices
  const integratedReadyCount = displayedIntegratedServices.filter((service) => service.ready).length

  useEffect(() => {
    if (isAdmissionsRole && activeStage === 'seguimiento') {
      onStageChange('inscritos')
      return
    }
    if (activeStage === 'materias' && !canManageAcademicEnrollment) {
      onStageChange('cabecera')
    }
  }, [activeStage, canManageAcademicEnrollment, isAdmissionsRole, onStageChange])

  const periodName =
    catalog?.periodos?.find((period) => period.codigo_periodo === selectedPeriod)?.detalle_periodo || ''
  const careerName =
    catalog?.carreras?.find((career) => career.cod_anio_basica === selectedCareer)?.nombre_basica || ''
  const createModalidadCode = String(createValues.codmodalida ?? '')
  const createJornadaCode = String(createValues.codjornada ?? '')
  const jornadaOptions = useMemo(() => {
    const options = catalog?.jornadas || []
    if (!createModalidadCode) return options
    return options.filter((option) => !option.modalidad || option.modalidad === createModalidadCode)
  }, [catalog?.jornadas, createModalidadCode])
  const createFullName =
    `${createValues.apellidos || ''} ${createValues.nombres || ''}`.trim() ||
    createValues.apellidos_nombre.trim()
  const createCedulaClean = createValues.cedula.replace(/\D+/g, '')
  const cedulaAlreadyRegistered =
    createCedulaClean.length === 10 &&
    cedulaValidation?.cedula === createCedulaClean &&
    cedulaValidation.exists
  const paymentCareerCode = activeStage === 'registro' ? createValues.codcarrera || '' : selectedEnrollmentCareer || createValues.codcarrera || ''
  const paymentModalityCode = activeStage === 'registro'
    ? createModalidadCode
    : String(selectedItem?.codmodalida || createModalidadCode || '')
  const paymentCareer = useMemo(
    () => (catalog?.carreras || []).find((career) => career.cod_anio_basica === paymentCareerCode),
    [catalog?.carreras, paymentCareerCode],
  )
  const paymentIsVirtual = useMemo(() => {
    const label = (catalog?.modalidades || []).find((option) => option.value === paymentModalityCode)?.label || ''
    const normalized = `${paymentModalityCode} ${label}`.toLowerCase()
    return normalized.includes('linea') || normalized.includes('línea') || normalized.includes('virtual') || normalized.includes('online')
  }, [catalog?.modalidades, paymentModalityCode])

  function selectedSemesterCount(value: string) {
    if (value === 'TODOS') return Math.min(Math.max(paymentCareer?.semestres_disponibles || 4, 1), 4)
    return Math.min(Math.max(Math.round(toNumber(value, 1)), 1), 4)
  }

  function pensumCostForSemesters(count: number) {
    const costs = paymentCareer?.costos_semestres || []
    if (!costs.length) return 0
    return costs
      .filter((item) => (item.semestre || 0) >= 1 && (item.semestre || 0) <= count)
      .reduce((total, item) => total + Number(paymentIsVirtual ? item.virtual || item.presencial || 0 : item.presencial || 0), 0)
  }

  const selectedDocuments = useMemo(
    (): Array<{ key: keyof PreinscriptionDocumentsPayload; label: string; value: string }> => [
      { key: 'urlcedula', label: 'Cedula identidad', value: documents.urlcedula || '' },
      { key: 'urltitulo', label: 'Titulo bachiller', value: documents.urltitulo || '' },
      { key: 'urldeposito', label: 'Deposito/transferencia', value: documents.urldeposito || '' },
      { key: 'urlconvenio', label: 'Convenio INTEC', value: documents.urlconvenio || '' },
    ],
    [documents],
  )
  const paymentPlanPreview = useMemo(() => {
    const selectedSemesters = selectedSemesterCount(cabeceraValues.semestres_convenio)
    const pensumTotal = pensumCostForSemesters(selectedSemesters)
    const enteredSemesterCost = Math.max(toNumber(cabeceraValues.costo_semestre), 0)
    const composedSemesterCost = Math.max(toNumber(cabeceraValues.inscrip_valor) + toNumber(cabeceraValues.matri_valor), 0)
    const fallbackSemesterCost = enteredSemesterCost > 0 ? enteredSemesterCost : composedSemesterCost > 0 ? composedSemesterCost : Math.max(toNumber(cabeceraValues.valor), 0)
    const total = Number((pensumTotal > 0 ? pensumTotal : fallbackSemesterCost * selectedSemesters).toFixed(2))
    const baseSemesterCost = Number((selectedSemesters > 0 ? total / selectedSemesters : fallbackSemesterCost).toFixed(2))
    const porcentajeBeca = Math.min(Math.max(toNumber(cabeceraValues.porcentaje_beca), 0), 100)
    const beca = Number((total * porcentajeBeca / 100).toFixed(2))
    const descuento = Math.max(toNumber(cabeceraValues.descuento), 0)
    const saldo = Math.max(Number((total - beca - descuento).toFixed(2)), 0)
    const cuotas = Math.max(Math.round(toNumber(cabeceraValues.num_cuotas, 1)), 1)
    const cuota = Number((saldo / cuotas).toFixed(2))
    return { total, porcentajeBeca, beca, descuento, saldo, cuotas, cuota, selectedSemesters, baseSemesterCost }
  }, [cabeceraValues, paymentCareer, paymentIsVirtual])
  const scholarshipOptions = catalog?.becas || []
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((item) =>
      [
        item.apellidos_nombre,
        item.cedula,
        item.codestu,
        item.correo,
        item.telefono,
        item.carrera,
        item.periodo,
        item.cabecera?.numcodigo,
        item.cabecera?.num_matricula,
      ]
        .map((value) => String(value ?? '').toLowerCase())
        .some((value) => value.includes(needle)),
    )
  }, [rows, tableFilter])
  const filteredDiscountValues = useMemo(() => {
    const options = catalog?.descuentos_valores || []
    if (!followupValues.coddescconve) return options
    return options.filter((option) => !option.parent || option.parent === followupValues.coddescconve)
  }, [catalog?.descuentos_valores, followupValues.coddescconve])
  const currentEnrollmentCodes = useMemo(
    () => new Set((enrollmentDetail?.materias_actuales || []).map((subject) => subject.codigo_materia)),
    [enrollmentDetail?.materias_actuales],
  )
  const selectedEnrollmentSubjects = useMemo(
    () => enrollmentPensum.filter((subject) => enrollmentSubjectCodes.includes(subject.codigo_materia)),
    [enrollmentPensum, enrollmentSubjectCodes],
  )
  const enrollmentSemesterGroups = useMemo(() => {
    const groups = new Map<string, AcademicEnrollmentSubject[]>()
    for (const subject of enrollmentPensum) {
      const key = subject.semestre ? `Nivel ${subject.semestre}` : 'Sin nivel'
      groups.set(key, [...(groups.get(key) || []), subject])
    }
    return [...groups.entries()]
  }, [enrollmentPensum])

  async function loadCatalog() {
    setCatalogError('')
    try {
      const payload = await fetchPreinscriptionCatalog()
      setCatalog(payload)
      setCreateValues((current) => {
        const firstModalidad = payload.modalidades?.[0]?.value || ''
        const currentModalidad = String(current.codmodalida ?? '')
        const nextModalidad = payload.modalidades?.some((option) => option.value === currentModalidad)
          ? currentModalidad
          : firstModalidad
        const firstJornada =
          payload.jornadas?.find((option) => !nextModalidad || option.modalidad === nextModalidad)?.value ||
          payload.jornadas?.[0]?.value ||
          ''
        const currentJornada = String(current.codjornada ?? '')
        const nextJornada = payload.jornadas?.some((option) => option.value === currentJornada) ? currentJornada : firstJornada
        return {
          ...current,
          codprov: current.codprov || payload.provincias?.[0]?.codprov || '',
          codperiodo: current.codperiodo || payload.periodos?.[0]?.codigo_periodo || '',
          codcarrera: current.codcarrera || payload.carreras?.[0]?.cod_anio_basica || '',
          codmodalida: toNumber(nextModalidad, 1),
          codjornada: toNumber(nextJornada, 0),
        }
      })
    } catch (requestError) {
      setCatalogError(requestError instanceof Error ? requestError.message : 'Error consultando catalogo')
    }
  }

  async function loadRows() {
    setLoading(true)
    setError('')
    setSaveMessage('')
    try {
      const payload = await fetchPreinscriptions({
        query: query.trim(),
        codigoPeriodo: selectedPeriod,
        codAnioBasica: selectedCareer,
        documentos: documentFilter,
        limit: 1000,
      })
      setData(payload)
      setSelectedItem((current) => {
        if (!current) return payload.items?.[0] || null
        return payload.items?.find((item) => item.num === current.num) || payload.items?.[0] || null
      })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Error consultando inscripciones')
      setData(null)
      setSelectedItem(null)
    } finally {
      setLoading(false)
    }
  }

  async function loadEnrollmentData() {
    if (!selectedItem?.num) {
      setEnrollmentPensum([])
      setEnrollmentDetail(null)
      setEnrollmentSubjectCodes([])
      setEnrollmentError('Selecciona un estudiante antes de matricular el primer nivel.')
      return
    }
    if (!selectedEnrollmentCareer || !selectedEnrollmentPeriod) {
      setEnrollmentPensum([])
      setEnrollmentDetail(null)
      setEnrollmentSubjectCodes([])
      setEnrollmentError('La inscripción seleccionada no tiene carrera o periodo definido.')
      return
    }

    setEnrollmentLoading(true)
    setEnrollmentError('')
    setEnrollmentMessage('')
    setEnrollmentPreview(null)
    try {
      const pensumPayload = await fetchAcademicEnrollmentPensum(selectedEnrollmentCareer)
      const fullPensumItems = pensumPayload.items || []
      const firstSemester = fullPensumItems
        .map((subject) => subject.semestre)
        .filter((value): value is number => value !== null && value !== undefined)
        .sort((left, right) => left - right)[0]
      const pensumItems = firstSemester === undefined
        ? fullPensumItems
        : fullPensumItems.filter((subject) => subject.semestre === firstSemester)
      const allowedSubjectCodes = new Set(pensumItems.map((subject) => subject.codigo_materia))
      setEnrollmentPensum(pensumItems)

      let detailPayload: AcademicEnrollmentDetailResponse | null = null
      if (selectedStudentCode) {
        try {
          detailPayload = await fetchAcademicEnrollmentDetail(
            selectedStudentCode,
            selectedEnrollmentCareer,
            selectedEnrollmentPeriod,
          )
          setEnrollmentDetail(detailPayload)
        } catch (detailError) {
          setEnrollmentDetail(null)
          setEnrollmentError(
            detailError instanceof Error
              ? detailError.message
              : 'No se pudo validar el estudiante en DATOS_ESTUD para matricular materias.',
          )
        }
      }

      const currentCodes = (detailPayload?.materias_actuales || [])
        .map((subject) => subject.codigo_materia)
        .filter((code) => allowedSubjectCodes.has(code))
      if (currentCodes.length > 0) {
        setEnrollmentSubjectCodes(currentCodes)
        const firstCurrent = (detailPayload?.materias_actuales || []).find((subject) => allowedSubjectCodes.has(subject.codigo_materia))
        if (firstCurrent?.paralelo) setEnrollmentParallel(firstCurrent.paralelo)
        if (firstCurrent?.num_grupo !== null && firstCurrent?.num_grupo !== undefined) {
          setEnrollmentGroup(String(firstCurrent.num_grupo))
        }
        if (firstCurrent?.tipo_matricula === 'R' || firstCurrent?.tipo_matricula === 'H' || firstCurrent?.tipo_matricula === 'E') {
          setEnrollmentType(firstCurrent.tipo_matricula)
        }
        if (firstCurrent?.control_matricula !== null && firstCurrent?.control_matricula !== undefined) {
          setEnrollmentControl(String(firstCurrent.control_matricula))
        }
      } else {
        setEnrollmentSubjectCodes(pensumItems.map((subject) => subject.codigo_materia))
      }
    } catch (requestError) {
      setEnrollmentPensum([])
      setEnrollmentDetail(null)
      setEnrollmentSubjectCodes([])
      setEnrollmentError(requestError instanceof Error ? requestError.message : 'Error consultando pensum para matricula')
    } finally {
      setEnrollmentLoading(false)
    }
  }

  useEffect(() => {
    void loadCatalog()
  }, [])

  useEffect(() => {
    const savedTotal = Number(selectedItem?.cabecera?.valor ?? 0)
    const savedBeca = Number(selectedItem?.cabecera?.beca ?? 0)
    const savedDescuento = Number(selectedItem?.cabecera?.descuento ?? 0)
    const savedCuota = Number(selectedItem?.cabecera?.cuota1 ?? 0)
    const savedSaldo = Math.max(savedTotal - savedBeca - savedDescuento, 0)
    const savedCuotas = savedCuota > 0 && savedSaldo > 0 ? Math.max(Math.round(savedSaldo / savedCuota), 1) : 1
    const savedPorcentajeBeca =
      selectedItem?.cabecera?.porcentaje_beca ?? (savedTotal > 0 ? Number(((savedBeca / savedTotal) * 100).toFixed(2)) : 0)
    setDocuments(documentPayloadFromItem(selectedItem))
    setCabeceraValues({
      fecha_pago: selectedItem?.cabecera?.fecha_pago?.slice(0, 10) || '',
      valor: String(selectedItem?.cabecera?.valor ?? 0),
      inscrip_valor: String(selectedItem?.cabecera?.inscrip_valor ?? 0),
      matri_valor: String(selectedItem?.cabecera?.matri_valor ?? 0),
      costo_semestre: String(selectedItem?.cabecera?.costo_semestre ?? selectedItem?.cabecera?.valor ?? 0),
      semestres_convenio: String(selectedItem?.cabecera?.semestres_convenio ?? 1),
      control_matricula: String(selectedItem?.cabecera?.control_matricula ?? 1),
      num_cuotas: String(savedCuotas),
      tipo_beca: selectedItem?.cabecera?.tipo_beca || '',
      porcentaje_beca: String(savedPorcentajeBeca),
      descuento: String(selectedItem?.cabecera?.descuento ?? 0),
      num_pago: String(selectedItem?.cabecera?.num_pago ?? 1),
      detalle_pago: selectedItem?.cabecera?.detalle_pago || 'Convenio de pago',
      no_deposito: selectedItem?.cabecera?.no_deposito || '',
      banco: selectedItem?.cabecera?.banco || '',
    })
    setFollowupValues({
      contacte: selectedItem?.contacte || '',
      hora: selectedItem?.hora || '',
      observacion_contacto: selectedItem?.observacion_contacto || '',
      observacion_ingreso: selectedItem?.observacion_ingreso || '',
      cod_lecontacto: selectedItem?.cod_lecontacto || '',
      cod_desea_ingresar: selectedItem?.cod_desea_ingresar || '',
      cod_como_conoce: selectedItem?.cod_como_conoce || '',
      coddescconve: selectedItem?.coddescconve || '',
      coddescconvevalor: selectedItem?.coddescconvevalor ? String(selectedItem.coddescconvevalor) : '',
      coddescdeptransf: selectedItem?.coddescdeptransf || '',
      nom_representante: selectedItem?.nom_representante || '',
      num_representante: selectedItem?.num_representante || '',
      prematricula: Boolean(selectedItem?.prematricula),
      proceso_finalizado: Boolean(selectedItem?.proceso_finalizado),
      control_ingreso: Boolean(selectedItem?.control_ingreso),
      correo_enviado: Boolean(selectedItem?.correo_enviado),
      asignado: Boolean(selectedItem?.asignado),
    })
    setCabeceraError('')
    setCabeceraMessage('')
    setFollowupError('')
    setFollowupMessage('')
    setSaveError('')
    setSaveMessage('')
    setPhotoError('')
    setPhotoMessage('')
    if (selectedItem?.num && selectedItem.en_cabecera_matricula) {
      void loadCarnetPhotoStatus(selectedItem.num)
    } else {
      setPhotoStatus(null)
    }
  }, [selectedItem])

  useEffect(() => {
    if (activeStage === 'materias') {
      void loadEnrollmentData()
    }
  }, [activeStage, selectedItem?.num])

  useEffect(() => {
    if (createCedulaClean.length < 10) {
      setCedulaValidation(null)
      setCedulaValidationLoading(false)
      return
    }

    let cancelled = false
    const timer = window.setTimeout(() => {
      setCedulaValidationLoading(true)
      validatePreinscriptionCedula(createCedulaClean, createValues.codperiodo || '')
        .then((response) => {
          if (cancelled) return
          const exists = Boolean(response.exists)
          setCedulaValidation({
            cedula: createCedulaClean,
            exists,
            message: exists ? response.message || 'estudiante inscrito' : '',
          })
        })
        .catch(() => {
          if (!cancelled) {
            setCedulaValidation(null)
          }
        })
        .finally(() => {
          if (!cancelled) {
            setCedulaValidationLoading(false)
          }
        })
    }, 300)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [createCedulaClean, createValues.codperiodo])

  function replaceSelectedItem(nextItem: PreinscriptionItem) {
    setSelectedItem(nextItem)
    setData((current) => {
      if (!current) return current
      return {
        ...current,
        items: (current.items || []).map((item) => (item.num === nextItem.num ? nextItem : item)),
      }
    })
  }

  async function revertSelectedProcess(item: PreinscriptionItem | null = selectedItem) {
    if (!item?.num) {
      setRevertError('Selecciona una inscripción para revertir.')
      return
    }
    const studentLabel = item.apellidos_nombre || item.cedula || item.num
    const confirmed = window.confirm(
      `Se eliminara la inscripcion, cabecera, materias, documentos vinculados y datos de factura del proceso de ${studentLabel}. Esta accion no se puede deshacer.`
    )
    if (!confirmed) return

    setRevertLoading(true)
    setRevertError('')
    try {
      await revertPreinscriptionProcess(item.num)
      setData((current) => {
        if (!current) return current
        const nextItems = (current.items || []).filter((row) => row.num !== item.num)
        return {
          ...current,
          total: Math.max((current.total || nextItems.length + 1) - 1, 0),
          items: nextItems,
        }
      })
      setSelectedItem(null)
      setStudentScreenOpen(false)
      setSaveMessage('Proceso revertido correctamente.')
    } catch (requestError) {
      setRevertError(requestError instanceof Error ? requestError.message : 'Error revirtiendo el proceso')
    } finally {
      setRevertLoading(false)
    }
  }

  async function registerCabecera() {
    if (!selectedItem?.num) {
      setCabeceraError('Selecciona una inscripción.')
      return
    }
    setCabeceraLoading(true)
    setCabeceraError('')
    setCabeceraMessage('')
    try {
      const payload: PreinscriptionCabeceraPayload = {
        fecha_pago: cabeceraValues.fecha_pago || null,
        valor: paymentPlanPreview.total,
        inscrip_valor: toNumber(cabeceraValues.inscrip_valor),
        matri_valor: toNumber(cabeceraValues.matri_valor),
        costo_semestre: paymentPlanPreview.baseSemesterCost,
        semestres_convenio: cabeceraValues.semestres_convenio,
        control_matricula: toNumber(cabeceraValues.control_matricula, 1),
        num_cuotas: Math.max(Math.round(toNumber(cabeceraValues.num_cuotas, 1)), 1),
        tipo_beca: cabeceraValues.tipo_beca || '',
        porcentaje_beca: Math.min(Math.max(toNumber(cabeceraValues.porcentaje_beca), 0), 100),
        descuento: toNumber(cabeceraValues.descuento),
        num_pago: Math.max(Math.round(toNumber(cabeceraValues.num_pago, 1)), 1),
        detalle_pago: cabeceraValues.detalle_pago || 'Convenio de pago',
        no_deposito: cabeceraValues.no_deposito || '',
        banco: cabeceraValues.banco || '',
      }
      const response = await registerPreinscriptionCabecera(selectedItem.num, payload)
      if (response.item) {
        replaceSelectedItem(response.item)
      }
      setCabeceraMessage(
        `${response.message || 'Matricula y convenio registrados.'} Codigo documentacion ${response.codigo_documentacion || response.num_matricula || '-'}.`
      )
    } catch (requestError) {
      setCabeceraError(requestError instanceof Error ? requestError.message : 'Error registrando matricula y convenio de pago')
    } finally {
      setCabeceraLoading(false)
    }
  }

  function applyScholarshipSelection(value: string) {
    const selected = scholarshipOptions.find((option) => option.value === value)
    setCabeceraValues((current) => ({
      ...current,
      tipo_beca: value,
      porcentaje_beca: selected?.amount !== null && selected?.amount !== undefined ? String(selected.amount) : value ? current.porcentaje_beca : '0',
    }))
  }

  function renderScholarshipSelector() {
    return (
      <label>
        <span>Tipo de beca</span>
        <select value={cabeceraValues.tipo_beca} onChange={(event) => applyScholarshipSelection(event.target.value)}>
          <option value="">Sin beca</option>
          {scholarshipOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}{option.detail ? ` (${option.detail})` : ''}
            </option>
          ))}
        </select>
      </label>
    )
  }

  function renderPaymentScopeSelector() {
    return (
      <>
        <label>
          <span>Semestres del convenio</span>
          <select
            value={cabeceraValues.semestres_convenio}
            onChange={(event) => setCabeceraValues((current) => ({ ...current, semestres_convenio: event.target.value }))}
          >
            <option value="1">1 semestre</option>
            <option value="2">2 semestres</option>
            <option value="3">3 semestres</option>
            <option value="TODOS">Todos los semestres</option>
          </select>
        </label>
        <label>
          <span>Costo desde pensum</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={paymentPlanPreview.baseSemesterCost}
            readOnly
          />
        </label>
      </>
    )
  }

  async function saveFollowup() {
    if (!selectedItem?.num) {
      setFollowupError('Selecciona una inscripción.')
      return
    }
    setFollowupLoading(true)
    setFollowupError('')
    setFollowupMessage('')
    try {
      const response = await updatePreinscriptionFollowup(selectedItem.num, followupValues)
      if (response.item) {
        replaceSelectedItem(response.item)
      }
      setFollowupMessage(response.message || 'Seguimiento actualizado.')
    } catch (requestError) {
      setFollowupError(requestError instanceof Error ? requestError.message : 'Error actualizando seguimiento')
    } finally {
      setFollowupLoading(false)
    }
  }

  async function saveDocuments() {
    if (!selectedItem?.num) {
      setSaveError('Selecciona una inscripción con identificador num.')
      return
    }
    if (!hasCabecera) {
      setSaveError('Primero registra la cabecera de matricula para generar el codigo de documentacion.')
      return
    }
    setSaveLoading(true)
    setSaveError('')
    setSaveMessage('')
    try {
      const response = await updatePreinscriptionDocuments(selectedItem.num, documents)
      const nextItem = response.item || selectedItem
      replaceSelectedItem(nextItem)
      setSaveMessage(
        `${response.message || 'Documentos actualizados.'} ${
          response.en_cabecera_matricula ? 'Cabecera de matricula vinculada.' : 'Sin cabecera de matricula vinculada.'
        }`
      )
    } catch (requestError) {
      setSaveError(requestError instanceof Error ? requestError.message : 'Error actualizando documentos')
    } finally {
      setSaveLoading(false)
    }
  }

  async function uploadDocument(field: string, file?: File | null) {
    if (!file || !selectedItem?.num) return
    if (!hasCabecera) {
      setSaveError('Primero registra la matricula/cabecera y genera el convenio de pago para habilitar documentacion.')
      return
    }
    setUploadingField(field)
    setSaveError('')
    setSaveMessage('')
    try {
      const response = await uploadPreinscriptionDocument(selectedItem.num, field, file)
      if (response.item) {
        replaceSelectedItem(response.item)
        setDocuments(documentPayloadFromItem(response.item))
      }
      setSaveMessage(
        `${response.message || 'Documento subido.'} Codigo documentacion ${response.codigo_documentacion || codigoDocumentacion || '-'}.`
      )
    } catch (requestError) {
      setSaveError(requestError instanceof Error ? requestError.message : 'Error subiendo documento')
    } finally {
      setUploadingField(null)
    }
  }

  async function loadCarnetPhotoStatus(num = selectedItem?.num || '') {
    if (!num) {
      setPhotoStatus(null)
      return
    }
    setPhotoLoading(true)
    setPhotoError('')
    try {
      const response = await fetchPreinscriptionCarnetPhoto(num)
      setPhotoStatus(response.foto || null)
    } catch (requestError) {
      setPhotoStatus(null)
      setPhotoError(requestError instanceof Error ? requestError.message : 'Error consultando foto de carnet')
    } finally {
      setPhotoLoading(false)
    }
  }

  async function uploadCarnetPhoto(file?: File | null) {
    if (!file || !selectedItem?.num) return
    if (!hasCabecera) {
      setPhotoError('Primero registra la cabecera de matricula para crear el estudiante.')
      return
    }
    setPhotoLoading(true)
    setPhotoError('')
    setPhotoMessage('')
    try {
      const response = await uploadPreinscriptionCarnetPhoto(selectedItem.num, file)
      setPhotoStatus(response.foto || null)
      setPhotoMessage(response.message || 'Foto cargada para aprobacion previa.')
    } catch (requestError) {
      setPhotoError(requestError instanceof Error ? requestError.message : 'Error subiendo foto de carnet')
    } finally {
      setPhotoLoading(false)
    }
  }

  async function approveCarnetPhoto() {
    if (!selectedItem?.num || !photoStatus?.id_solicitud_foto) return
    setPhotoLoading(true)
    setPhotoError('')
    setPhotoMessage('')
    try {
      const response = await approvePreinscriptionCarnetPhoto(selectedItem.num, photoStatus.id_solicitud_foto)
      setPhotoStatus(response.foto || null)
      setPhotoMessage(response.message || 'Foto aprobada.')
    } catch (requestError) {
      setPhotoError(requestError instanceof Error ? requestError.message : 'Error aprobando foto de carnet')
    } finally {
      setPhotoLoading(false)
    }
  }

  async function rejectCarnetPhoto() {
    if (!selectedItem?.num || !photoStatus?.id_solicitud_foto) return
    const observacion = window.prompt('Indica el motivo del rechazo para que el estudiante suba una nueva imagen:', '')
    if (observacion === null) return
    setPhotoLoading(true)
    setPhotoError('')
    setPhotoMessage('')
    try {
      const response = await rejectPreinscriptionCarnetPhoto(selectedItem.num, photoStatus.id_solicitud_foto, observacion)
      setPhotoStatus(response.foto || null)
      setPhotoMessage(response.message || 'Foto rechazada.')
    } catch (requestError) {
      setPhotoError(requestError instanceof Error ? requestError.message : 'Error rechazando foto de carnet')
    } finally {
      setPhotoLoading(false)
    }
  }

  function buildEnrollmentPayload(): AcademicEnrollmentPayload | null {
    const allowedCodes = new Set(enrollmentPensum.map((subject) => subject.codigo_materia))
    const validSubjectCodes = enrollmentSubjectCodes.filter((code) => allowedCodes.has(code))
    if (!selectedItem?.num) {
      setEnrollmentError('Selecciona un estudiante para continuar con la matrícula del primer nivel.')
      return null
    }
    if (!selectedStudentCode || !selectedEnrollmentCareer || !selectedEnrollmentPeriod) {
      setEnrollmentError('Faltan código de estudiante, carrera o periodo para matricular el primer nivel.')
      return null
    }
    if (validSubjectCodes.length === 0) {
      setEnrollmentError('Selecciona al menos una materia de primer nivel para matricular.')
      return null
    }

    return {
      codigo_estud: toNumber(selectedStudentCode),
      cod_anio_basica: toNumber(selectedEnrollmentCareer),
      codigo_periodo: toNumber(selectedEnrollmentPeriod),
      materia_codes: validSubjectCodes.map((code) => toNumber(code)).filter(Boolean),
      paralelo: (enrollmentParallel.trim().toUpperCase() || 'A').slice(0, 4),
      num_grupo: toNumber(enrollmentGroup, 1),
      tipo_matricula: enrollmentType,
      control_matricula: toNumber(enrollmentControl, 1),
      cod_jornada: toNumber(String(selectedItem.codjornada ?? createValues.codjornada ?? 1), 1),
      inscrip_valor: toNumber(String(selectedItem.cabecera?.inscrip_valor ?? cabeceraValues.inscrip_valor ?? 0)),
      matri_valor: toNumber(String(selectedItem.cabecera?.matri_valor ?? cabeceraValues.matri_valor ?? 0)),
      valor: toNumber(String(selectedItem.cabecera?.valor ?? cabeceraValues.valor ?? 0)),
      fecha_pago: selectedItem.cabecera?.fecha_pago?.slice(0, 10) || cabeceraValues.fecha_pago || null,
      remove_unselected: false,
    }
  }

  async function previewEnrollmentSubjects() {
    const payload = buildEnrollmentPayload()
    if (!payload) return
    setEnrollmentPreviewLoading(true)
    setEnrollmentError('')
    setEnrollmentMessage('')
    try {
      const response = await previewAcademicEnrollment(payload)
      setEnrollmentPreview(response)
    } catch (requestError) {
      setEnrollmentError(requestError instanceof Error ? requestError.message : 'Error generando vista previa de materias')
    } finally {
      setEnrollmentPreviewLoading(false)
    }
  }

  async function saveEnrollmentSubjects() {
    const payload = buildEnrollmentPayload()
    if (!payload) return
    setEnrollmentSaveLoading(true)
    setEnrollmentError('')
    setEnrollmentMessage('')
    try {
      const response = await saveAcademicEnrollment(payload)
      let processMessage = ''
      if (enrollmentFinalizeProcess && selectedItem?.num) {
        try {
          const nextFollowup = {
            ...followupValues,
            proceso_finalizado: true,
            control_ingreso: true,
          }
          const followupResponse = await updatePreinscriptionFollowup(selectedItem.num, nextFollowup)
          setFollowupValues(nextFollowup)
          if (followupResponse.item) {
            replaceSelectedItem(followupResponse.item)
          }
          processMessage = ' Proceso finalizado con matrícula inicial registrada.'
        } catch (followupError) {
          processMessage = ` No se pudo actualizar el estado del proceso: ${
            followupError instanceof Error ? followupError.message : 'error desconocido'
          }.`
        }
      }
      await loadEnrollmentData()
      setEnrollmentPreview(response.preview || null)
      setEnrollmentMessage(
        `${response.message || 'Matricula de materias guardada.'} Insertadas ${response.inserted ?? 0}, actualizadas ${
          response.updated ?? 0
        }.${processMessage}`,
      )
    } catch (requestError) {
      setEnrollmentError(requestError instanceof Error ? requestError.message : 'Error guardando matricula de materias')
    } finally {
      setEnrollmentSaveLoading(false)
    }
  }

  async function validateCreateCedula(cedula: string): Promise<boolean> {
    if (cedula.length !== 10) {
      setCedulaValidation(null)
      return false
    }
    setCedulaValidationLoading(true)
    try {
      const response = await validatePreinscriptionCedula(cedula, createValues.codperiodo || '')
      const exists = Boolean(response.exists)
      setCedulaValidation({
        cedula,
        exists,
        message: exists ? response.message || 'estudiante inscrito' : '',
      })
      return exists
    } catch {
      setCedulaValidation(null)
      return false
    } finally {
      setCedulaValidationLoading(false)
    }
  }

  async function registerPreinscription() {
    const fullName = createFullName.trim()
    if (!fullName) {
      setCreateError('Ingresa nombres y apellidos del estudiante.')
      return
    }
    if (createCedulaClean.length !== 10) {
      setCreateError('Ingresa un numero de cedula de 10 digitos.')
      return
    }
    if (
      (cedulaValidation?.cedula === createCedulaClean && cedulaValidation.exists) ||
      (cedulaValidation?.cedula !== createCedulaClean && (await validateCreateCedula(createCedulaClean)))
    ) {
      setCreateError('estudiante inscrito')
      return
    }
    if (!createValues.correo?.trim()) {
      setCreateError('Ingresa el correo del estudiante.')
      return
    }
    if (!createValues.telefono?.trim()) {
      setCreateError('Ingresa el telefono del estudiante.')
      return
    }
    if (!createValues.codprov) {
      setCreateError('Selecciona la provincia.')
      return
    }
    if (!createValues.codperiodo || !createValues.codcarrera) {
      setCreateError('Selecciona periodo y carrera para registrar la inscripción.')
      return
    }
    if (!createValues.codmodalida || !createValues.codjornada) {
      setCreateError('Selecciona modalidad y jornada.')
      return
    }

    setCreateLoading(true)
    setCreateError('')
    setCreateMessage('')
    try {
      const response = await createPreinscription({
        ...createValues,
        cedula: createCedulaClean,
        apellidos_nombre: fullName,
        apellidos: createValues.apellidos?.trim(),
        nombres: createValues.nombres?.trim(),
        codmodalida: toNumber(String(createValues.codmodalida), 1),
        codjornada: toNumber(String(createValues.codjornada), 0),
      })
      if (response.item) {
        setSelectedItem(response.item)
        setDocuments(documentPayloadFromItem(response.item))
        setData((current) => {
          const nextItems = [response.item!, ...(current?.items || []).filter((item) => item.num !== response.item!.num)]
          return {
            ...(current || {}),
            total: nextItems.length,
            items: nextItems,
          }
        })
      }
      setCreateValues((current) => ({
        ...current,
        apellidos_nombre: '',
        nombres: '',
        apellidos: '',
        cedula: '',
        correo: '',
        telefono: '',
      }))
      onStageChange('documentos')
      setCreateMessage(
        `${response.message || 'Inscripción registrada.'} Continua con matricula, convenio de pago y documentacion.`
      )
    } catch (requestError) {
      setCreateError(requestError instanceof Error ? requestError.message : 'Error registrando inscripcion')
    } finally {
      setCreateLoading(false)
    }
  }

  async function openPreinscriptionStage(nextStage: PreinscriptionStage) {
    if (nextStage === 'materias' && !canManageAcademicEnrollment) {
      onStageChange('cabecera')
      return
    }
    onStageChange(nextStage)
    if (nextStage !== 'registro' && !data) {
      await loadRows()
    }
    if (nextStage === 'materias') {
      await loadEnrollmentData()
    }
  }

  async function toggleInscritosList() {
    await openPreinscriptionStage(activeStage === 'inscritos' ? 'registro' : 'inscritos')
  }

  function selectStudent(item: PreinscriptionItem) {
    setSelectedItem(item)
  }

  async function loadFollowupStudentOptions(queryValue = followupSearch, allowEmpty = false) {
    const term = queryValue.trim()
    setFollowupSearchError('')
    setFollowupSearchResults([])

    if (!allowEmpty && term.length < 2) {
      setFollowupSearchError('Ingresa al menos 2 caracteres para buscar por nombre, cedula o correo.')
      return
    }

    setFollowupSearchLoading(true)
    try {
      const payload = await fetchPreinscriptions({
        query: term,
        documentos: 'ALL',
        limit: term ? 200 : 100,
      })
      const items = payload.items || []
      setFollowupSearchResults(items)
      setPendingStudentNum((current) => {
        if (items.some((item) => item.num === current)) return current
        if (selectedItem?.num && items.some((item) => item.num === selectedItem.num)) return selectedItem.num
        return ''
      })
      if (!items.length) {
        setFollowupSearchError(term ? 'No se encontraron estudiantes con ese dato.' : 'No hay estudiantes para listar.')
      }
    } catch (requestError) {
      setFollowupSearchError(requestError instanceof Error ? requestError.message : 'Error buscando estudiantes')
      setPendingStudentNum('')
    } finally {
      setFollowupSearchLoading(false)
    }
  }

  async function searchFollowupApplicants() {
    await loadFollowupStudentOptions(followupSearch, false)
  }

  function openFollowupStudentSelector() {
    setPendingStudentNum(selectedItem?.num || '')
    setFollowupSearch('')
    setStudentSelectorOpen(true)
    void loadFollowupStudentOptions('', true)
  }

  function confirmFollowupStudentSelection() {
    if (!pendingStudentNum) {
      setFollowupSearchError('Marca un estudiante para continuar.')
      return
    }
    const selected = followupSearchResults.find((item) => item.num === pendingStudentNum)
    if (!selected) {
      setFollowupSearchError('No se encontro el estudiante seleccionado en la lista cargada.')
      return
    }
    selectFollowupApplicant(selected)
    setStudentSelectorOpen(false)
  }

  function selectFollowupApplicant(item: PreinscriptionItem) {
    selectStudent(item)
    setPendingStudentNum(item.num)
    setFollowupSearch(item.apellidos_nombre || item.cedula || '')
    setFollowupSearchResults([])
    setFollowupSearchError('')
  }

  function markSingleFollowupStudent(item: PreinscriptionItem) {
    setPendingStudentNum(item.num)
    setFollowupSearchError('')
  }

  function openStudentScreen(item: PreinscriptionItem) {
    setSelectedItem(item)
    setStudentScreenOpen(true)
  }

  return (
    <div className="student-dashboard">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Admisiones</p>
          <h1>Inscripcion y matricula</h1>
          <div className="student-user-pill preinscripcion-advisor-pill">
            <span>Asesor</span>
            <strong>{displayName || 'Usuario actual'}</strong>
          </div>
        </div>
        <div className="student-user-pill">
          <span>Mis registros</span>
          <strong>{userRecordCount}</strong>
        </div>
      </header>

      {selectedItem ? (
        <section className="preinscripcion-current">
          <div>
            <span>Estudiante seleccionado</span>
            <strong>{selectedItem.apellidos_nombre || selectedItem.cedula || 'Sin nombre'}</strong>
          </div>
          <div>
            <span>Cabecera matricula</span>
            <strong>{hasCabecera ? 'Vinculada' : 'Pendiente'}</strong>
          </div>
          <div>
            <span>Documentos</span>
            <strong>{documentStatus(selectedItem)}</strong>
          </div>
          <button type="button" className="ghost-button" onClick={() => setStudentScreenOpen(true)}>
            Ficha completa
          </button>
          {!isAdmissionsRole ? (
            <button
              type="button"
              className="danger-action"
              onClick={() => void revertSelectedProcess()}
              disabled={revertLoading}
            >
              {revertLoading ? 'Revirtiendo...' : 'Revertir proceso'}
            </button>
          ) : null}
        </section>
      ) : null}
      {revertError ? <p className="form-error">{revertError}</p> : null}

      <section className="preinscripcion-integrated">
        <div className="preinscripcion-integrated__head">
          <div>
            <span>Proceso regular</span>
            <h2>{isAdmissionsRole ? 'Paso 1 inscribir, paso 2 matricular y documentar' : 'Inscripcion, cabecera, documentos y primer nivel'}</h2>
          </div>
          <strong>
            {integratedReadyCount} de {displayedIntegratedServices.length} {isAdmissionsRole ? 'paso(s) completado(s)' : 'modulo(s) disponibles'}
          </strong>
        </div>
        <div className="preinscripcion-integrated__summary">
          <div>
            <span>Estudiante</span>
            <strong>{selectedStudentName || 'Seleccione un estudiante'}</strong>
          </div>
          <div>
            <span>Cedula</span>
            <strong>{selectedStudentCedula || '-'}</strong>
          </div>
          <div>
            <span>Documentos</span>
            <strong>{selectedItem ? documentStatus(selectedItem) : '-'}</strong>
          </div>
          <div>
            <span>Cabecera matricula</span>
            <strong>{hasCabecera ? 'Vinculado' : 'Pendiente'}</strong>
          </div>
        </div>
        <div className="preinscripcion-integrated__grid">
          {displayedIntegratedServices.map((service) => (
            <article
              key={service.key}
              className={`preinscripcion-integrated__card ${
                service.ready ? 'preinscripcion-integrated__card--ready' : 'preinscripcion-integrated__card--pending'
              }`}
            >
              <div className="preinscripcion-integrated__card-head">
                <span>{service.ready ? 'Disponible' : 'Pendiente'}</span>
                <strong>{service.title}</strong>
              </div>
              <p>{service.description}</p>
              <small>{service.requirement}</small>
              <div className="preinscripcion-integrated__tables">
                {service.tables.map((table) => (
                  <em key={table}>{table}</em>
                ))}
              </div>
              <button
                type="button"
                className="ghost-button preinscripcion-integrated__button"
                onClick={() => void openPreinscriptionStage(service.stage)}
              >
                {service.actionLabel}
              </button>
            </article>
          ))}
        </div>
      </section>

      {activeStage === 'registro' ? (
      <section className="student-grid student-grid--content preinscripcion-grid">
        <article className="student-card student-card--wide matricula-panel preinscripcion-register-card">
          <div className="section-title">
            <div>
              <span>Registro</span>
              <h2>Paso 1: inscribir estudiante</h2>
            </div>
            <button type="button" className="ghost-button" onClick={() => void toggleInscritosList()} disabled={loading}>
              Ver inscritos
            </button>
          </div>

          <div className="preinscripcion-form-intro">
            <strong>Formulario de inscripcion</strong>
            <span>Registre la inscripcion; al guardar continua con matricula, convenio de pago y documentacion.</span>
          </div>

          <div className="preinscripcion-beca-panel">
            <div>
              <span>Convenio y beca</span>
              <strong>{paymentPlanPreview.selectedSemesters} semestre(s) · {formatMoney(paymentPlanPreview.total)}</strong>
              <small>Selecciona el alcance del convenio y la beca cargada desde la tabla Becas.</small>
            </div>
            {renderPaymentScopeSelector()}
            {renderScholarshipSelector()}
            <label>
              <span>% beca</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={cabeceraValues.porcentaje_beca}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, porcentaje_beca: event.target.value }))}
              />
            </label>
          </div>

          <div className="matricula-acad-form preinscripcion-register-form">
            <label>
              <span>Periodo</span>
              <select value={createValues.codperiodo || ''} onChange={(event) => setCreateValues((current) => ({ ...current, codperiodo: event.target.value }))}>
                <option value="">- Seleccione -</option>
                {(catalog?.periodos || []).map((period) => (
                  <option key={period.codigo_periodo} value={period.codigo_periodo}>
                    {period.detalle_periodo || period.codigo_periodo}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Carrera</span>
              <select value={createValues.codcarrera || ''} onChange={(event) => setCreateValues((current) => ({ ...current, codcarrera: event.target.value }))}>
                <option value="">- Seleccione -</option>
                {(catalog?.carreras || []).map((career) => (
                  <option key={career.cod_anio_basica} value={career.cod_anio_basica}>
                    {career.nombre_basica}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Cedula</span>
              <input
                value={createValues.cedula}
                maxLength={10}
                placeholder="Cedula *"
                onChange={(event) =>
                  setCreateValues((current) => ({ ...current, cedula: event.target.value.replace(/\D+/g, '').slice(0, 10) }))
                }
              />
              {cedulaValidationLoading ? (
                <small className="preinscripcion-field-hint">Validando cedula...</small>
              ) : cedulaAlreadyRegistered ? (
                <small className="preinscripcion-field-error">{cedulaValidation?.message || 'estudiante inscrito'}</small>
              ) : null}
            </label>
            <label>
              <span>Nombres</span>
              <input
                value={createValues.nombres || ''}
                placeholder="Nombres *"
                onChange={(event) => setCreateValues((current) => ({ ...current, nombres: event.target.value }))}
              />
            </label>
            <label>
              <span>Apellidos</span>
              <input
                value={createValues.apellidos || ''}
                placeholder="Apellidos *"
                onChange={(event) => setCreateValues((current) => ({ ...current, apellidos: event.target.value }))}
              />
            </label>
            <label>
              <span>Correo</span>
              <input
                value={createValues.correo || ''}
                placeholder="Correo *"
                onChange={(event) => setCreateValues((current) => ({ ...current, correo: event.target.value }))}
              />
            </label>
            <label>
              <span>Telefono</span>
              <input
                value={createValues.telefono || ''}
                placeholder="Telefono *"
                onChange={(event) => setCreateValues((current) => ({ ...current, telefono: event.target.value }))}
              />
            </label>
            <label>
              <span>Provincia</span>
              <select value={createValues.codprov} onChange={(event) => setCreateValues((current) => ({ ...current, codprov: event.target.value }))}>
                <option value="">- Seleccione -</option>
                {(catalog?.provincias || []).map((province) => (
                  <option key={province.codprov} value={province.codprov}>
                    {province.descripcion}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Modalidad</span>
              <select
                value={createModalidadCode}
                onChange={(event) => {
                  const nextModalidad = event.target.value
                  const nextJornada =
                    (catalog?.jornadas || []).find((option) => !option.modalidad || option.modalidad === nextModalidad)?.value || ''
                  setCreateValues((current) => ({
                    ...current,
                    codmodalida: toNumber(nextModalidad, 0),
                    codjornada: toNumber(nextJornada, 0),
                  }))
                }}
              >
                <option value="">- Seleccione -</option>
                {(catalog?.modalidades || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Jornada</span>
              <select value={createJornadaCode} onChange={(event) => setCreateValues((current) => ({ ...current, codjornada: toNumber(event.target.value, 0) }))}>
                <option value="">- Seleccione -</option>
                {jornadaOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="matricula-acad-actions">
            <button
              type="button"
              className="primary-action"
              onClick={() => void registerPreinscription()}
              disabled={createLoading || cedulaValidationLoading || cedulaAlreadyRegistered}
            >
              {createLoading ? 'Registrando...' : 'Registrar'}
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => void openPreinscriptionStage('inscritos')}
              disabled={loading}
            >
              Ver inscritos
            </button>
          </div>
          {createError ? <p className="form-error">{createError}</p> : null}
          {createMessage ? <p className="form-success">{createMessage}</p> : null}
        </article>

      </section>
      ) : null}

      {activeStage !== 'registro' ? (
      <>
      <section className="student-grid student-grid--content preinscripcion-grid">
        {activeStage === 'inscritos' ? (
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Filtros</span>
              <h2>Estudiantes inscritos</h2>
            </div>
            <button type="button" className="ghost-button" onClick={() => void loadRows()} disabled={loading}>
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
          </div>
          {catalogError ? <p className="form-error">{catalogError}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
          <div className="matricula-acad-form">
            <label>
              <span>Buscar</span>
              <input
                value={query}
                placeholder="Cedula, nombre, correo o codigo"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void loadRows()
                  }
                }}
              />
            </label>
            <label>
              <span>Periodo</span>
              <select value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)}>
                <option value="">Todos</option>
                {(catalog?.periodos || []).map((period) => (
                  <option key={period.codigo_periodo} value={period.codigo_periodo}>
                    {period.detalle_periodo || period.codigo_periodo} ({period.total_preinscripciones ?? 0})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Carrera</span>
              <select value={selectedCareer} onChange={(event) => setSelectedCareer(event.target.value)}>
                <option value="">Todas</option>
                {(catalog?.carreras || []).map((career) => (
                  <option key={career.cod_anio_basica} value={career.cod_anio_basica}>
                    {career.nombre_basica} ({career.total_preinscripciones ?? 0})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Estado</span>
              <select value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value as DocumentFilter)}>
                {documentFilters.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Periodo actual</span>
              <input value={periodName || 'Todos'} disabled readOnly />
            </label>
            <label>
              <span>Carrera actual</span>
              <input value={careerName || 'Todas'} disabled readOnly />
            </label>
          </div>

          <div className="matricula-acad-preview preinscripcion-summary">
            <div>
              <span>Total</span>
              <strong>{totals.total ?? 0}</strong>
            </div>
            <div>
              <span>Con cabecera</span>
              <strong>{totals.con_cabecera ?? 0}</strong>
            </div>
            <div>
              <span>Docs completos</span>
              <strong>{totals.documentos_completos ?? 0}</strong>
            </div>
            <div>
              <span>Docs pendientes</span>
              <strong>{totals.documentos_pendientes ?? 0}</strong>
            </div>
          </div>
        </article>
        ) : null}

        {activeStage === 'seguimiento' ? (
        <article className="student-card matricula-panel preinscripcion-action-card">
          <div className="section-title">
            <div>
              <span>Seguimiento</span>
              <h2>Contacto y avance del estudiante</h2>
            </div>
          </div>
          <div className="preinscripcion-followup-search preinscripcion-followup-search--selector">
            <div>
              <span>Estudiante para seguimiento</span>
              <strong>{selectedItem ? valueOrDash(selectedItem.apellidos_nombre) : 'Sin estudiante seleccionado'}</strong>
              <small>
                {selectedItem
                  ? `${valueOrDash(selectedItem.cedula)} · ${valueOrDash(selectedItem.correo)} · ${valueOrDash(selectedItem.carrera)}`
                  : 'Busca por nombre, cedula o correo para cargar el seguimiento.'}
              </small>
            </div>
            <div className="preinscripcion-followup-search__actions">
              <button type="button" className="primary-action" onClick={openFollowupStudentSelector}>
                Buscar estudiante
              </button>
              {selectedItem ? (
                <button type="button" className="ghost-button" onClick={() => setStudentScreenOpen(true)}>
                  Ver ficha
                </button>
              ) : null}
            </div>
          </div>
          {!selectedItem ? (
            <p className="form-error">Selecciona un estudiante en Inscritos antes de registrar seguimiento.</p>
          ) : null}
          <div className="preinscripcion-detail preinscripcion-detail--wide">
            <div>
              <span>Estudiante</span>
              <strong>{valueOrDash(selectedItem?.apellidos_nombre)}</strong>
            </div>
            <div>
              <span>Cedula</span>
              <strong>{valueOrDash(selectedItem?.cedula)}</strong>
            </div>
            <div>
              <span>Telefono</span>
              <strong>{valueOrDash(selectedItem?.telefono)}</strong>
            </div>
            <div>
              <span>Correo</span>
              <strong>{valueOrDash(selectedItem?.correo)}</strong>
            </div>
          </div>
          <div className="preinscripcion-followup-form">
            <label>
              <span>Contacto realizado</span>
              <input
                value={followupValues.contacte}
                placeholder="Telefono, WhatsApp, correo, presencial"
                onChange={(event) => setFollowupValues((current) => ({ ...current, contacte: event.target.value }))}
              />
            </label>
            <label>
              <span>Hora / detalle corto</span>
              <input
                value={followupValues.hora}
                placeholder="Hora o siguiente llamada"
                onChange={(event) => setFollowupValues((current) => ({ ...current, hora: event.target.value }))}
              />
            </label>
            <label>
              <span>Medio de contacto</span>
              <select
                value={followupValues.cod_lecontacto}
                onChange={(event) => setFollowupValues((current) => ({ ...current, cod_lecontacto: event.target.value }))}
              >
                <option value="">Seleccionar</option>
                {(catalog?.le_contactos || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Desea ingresar</span>
              <select
                value={followupValues.cod_desea_ingresar}
                onChange={(event) => setFollowupValues((current) => ({ ...current, cod_desea_ingresar: event.target.value }))}
              >
                <option value="">Sin definir</option>
                {(catalog?.desea_ingresar || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Como conocio</span>
              <select
                value={followupValues.cod_como_conoce}
                onChange={(event) => setFollowupValues((current) => ({ ...current, cod_como_conoce: event.target.value }))}
              >
                <option value="">Sin definir</option>
                {(catalog?.como_conoce || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Convenio / beca</span>
              <select
                value={followupValues.coddescconve}
                onChange={(event) =>
                  setFollowupValues((current) => ({
                    ...current,
                    coddescconve: event.target.value,
                    coddescconvevalor: '',
                  }))
                }
              >
                <option value="">No aplica</option>
                {(catalog?.descuentos_convenio || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}{option.detail ? ` (${option.detail})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Valor convenio</span>
              <select
                value={followupValues.coddescconvevalor}
                onChange={(event) => setFollowupValues((current) => ({ ...current, coddescconvevalor: event.target.value }))}
              >
                <option value="">No aplica</option>
                {filteredDiscountValues.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.amount != null ? `$${option.amount.toFixed(2)}` : option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Desc. deposito/transf.</span>
              <select
                value={followupValues.coddescdeptransf}
                onChange={(event) => setFollowupValues((current) => ({ ...current, coddescdeptransf: event.target.value }))}
              >
                <option value="">No aplica</option>
                {(catalog?.descuentos_deposito || []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.amount != null ? `$${option.amount.toFixed(2)}` : option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Representante</span>
              <input
                value={followupValues.nom_representante}
                placeholder="Nombre del representante"
                onChange={(event) => setFollowupValues((current) => ({ ...current, nom_representante: event.target.value }))}
              />
            </label>
            <label>
              <span>Telefono representante</span>
              <input
                value={followupValues.num_representante}
                maxLength={10}
                placeholder="Telefono"
                onChange={(event) =>
                  setFollowupValues((current) => ({ ...current, num_representante: event.target.value.replace(/\D+/g, '').slice(0, 10) }))
                }
              />
            </label>
            <label className="preinscripcion-followup-form__wide">
              <span>Observacion de contacto</span>
              <textarea
                value={followupValues.observacion_contacto}
                placeholder="Resultado del contacto con el estudiante"
                onChange={(event) => setFollowupValues((current) => ({ ...current, observacion_contacto: event.target.value }))}
              />
            </label>
            <label className="preinscripcion-followup-form__wide">
              <span>Observacion de ingreso</span>
              <textarea
                value={followupValues.observacion_ingreso}
                placeholder="Notas internas del proceso de ingreso"
                onChange={(event) => setFollowupValues((current) => ({ ...current, observacion_ingreso: event.target.value }))}
              />
            </label>
          </div>
          <div className="preinscripcion-followup-checks">
            {[
              ['prematricula', 'Matricula inicial'],
              ['asignado', 'Asignado'],
              ['correo_enviado', 'Correo enviado'],
              ['control_ingreso', 'Control ingreso'],
              ['proceso_finalizado', 'Proceso finalizado'],
            ].map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={Boolean(followupValues[key as keyof PreinscriptionFollowupPayload])}
                  onChange={(event) =>
                    setFollowupValues((current) => ({
                      ...current,
                      [key]: event.target.checked,
                    }))
                  }
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          {followupError ? <p className="form-error">{followupError}</p> : null}
          {followupMessage ? <p className="form-success">{followupMessage}</p> : null}
          <button
            type="button"
            className="primary-action"
            onClick={() => void saveFollowup()}
            disabled={followupLoading || !selectedItem?.num}
          >
            {followupLoading ? 'Guardando...' : 'Guardar seguimiento'}
          </button>
        </article>
        ) : null}

        {activeStage === 'cabecera' ? (
        <article className="student-card matricula-panel preinscripcion-action-card">
          <div className="section-title">
            <div>
              <span>Cabecera matricula</span>
              <h2>{hasCabecera ? 'Cabecera vinculada' : 'Primer paso de matricula'}</h2>
            </div>
          </div>
          {!selectedItem ? (
            <p className="form-error">Selecciona o registra un estudiante antes de guardar la cabecera de matricula.</p>
          ) : null}
          <div className="matricula-acad-preview">
            <div>
              <span>Estudiante</span>
              <strong>{valueOrDash(selectedStudentName)}</strong>
            </div>
            <div>
              <span>Cedula</span>
              <strong>{valueOrDash(selectedStudentCedula)}</strong>
            </div>
            <div>
              <span>Codigo estudiante</span>
              <strong>{valueOrDash(selectedStudentCode)}</strong>
            </div>
            <div>
              <span>Codigo doc.</span>
              <strong>{valueOrDash(codigoDocumentacion)}</strong>
            </div>
            <div>
              <span>Periodo</span>
              <strong>{valueOrDash(selectedItem?.cabecera?.codigo_periodo || selectedItem?.codperiodo)}</strong>
            </div>
            <div>
              <span>Total a pagar</span>
              <strong>{formatMoney(paymentPlanPreview.total)}</strong>
            </div>
            <div>
              <span>Alcance</span>
              <strong>{paymentPlanPreview.selectedSemesters} semestre(s)</strong>
            </div>
            <div>
              <span>Costo semestre</span>
              <strong>{formatMoney(paymentPlanPreview.baseSemesterCost)}</strong>
            </div>
            <div>
              <span>Beca</span>
              <strong>{formatMoney(paymentPlanPreview.beca)} ({formatMoney(paymentPlanPreview.porcentajeBeca)}%)</strong>
            </div>
            <div>
              <span>Saldo convenio</span>
              <strong>{formatMoney(paymentPlanPreview.saldo)}</strong>
            </div>
            <div>
              <span>Cuotas</span>
              <strong>{paymentPlanPreview.cuotas} x {formatMoney(paymentPlanPreview.cuota)}</strong>
            </div>
            <div className={convenioUrl ? 'preinscripcion-carta-card preinscripcion-carta-card--ready' : 'preinscripcion-carta-card'}>
              <span>Carta PDF</span>
              <strong>{convenioUrl ? 'Convenio generado' : 'Pendiente de generar'}</strong>
              <small>Documento listo para firma, respaldo y carga en documentos.</small>
              {convenioUrl ? (
                <a className="preinscripcion-carta-button" href={convenioUrl} target="_blank" rel="noreferrer" download>
                  Descargar convenio PDF
                </a>
              ) : (
                <em>Guarda el pago para generar la carta automaticamente.</em>
              )}
            </div>
          </div>
          <div className="preinscripcion-cabecera-form">
            <label>
              <span>No. pago</span>
              <input
                type="number"
                min="1"
                step="1"
                value={cabeceraValues.num_pago}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, num_pago: event.target.value }))}
              />
            </label>
            <label>
              <span>Fecha de pago</span>
              <input
                type="date"
                value={cabeceraValues.fecha_pago}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, fecha_pago: event.target.value }))}
              />
            </label>
            <label className="preinscripcion-followup-form__wide">
              <span>Detalle del pago/convenio</span>
              <textarea
                value={cabeceraValues.detalle_pago}
                placeholder="Ej. Primer pago de inscripcion y convenio de cuotas"
                onChange={(event) => setCabeceraValues((current) => ({ ...current, detalle_pago: event.target.value }))}
              />
            </label>
            <label>
              <span>Inscripcion</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={cabeceraValues.inscrip_valor}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, inscrip_valor: event.target.value }))}
              />
            </label>
            <label>
              <span>Matricula</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={cabeceraValues.matri_valor}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, matri_valor: event.target.value }))}
              />
            </label>
            <label>
              <span>Valor total calculado</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={paymentPlanPreview.total}
                readOnly
              />
            </label>
            <label>
              <span>No. deposito/ref.</span>
              <input
                value={cabeceraValues.no_deposito}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, no_deposito: event.target.value }))}
              />
            </label>
            <label>
              <span>Banco</span>
              <input
                value={cabeceraValues.banco}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, banco: event.target.value }))}
              />
            </label>
            {renderPaymentScopeSelector()}
            {renderScholarshipSelector()}
            <label>
              <span>% beca</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={cabeceraValues.porcentaje_beca}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, porcentaje_beca: event.target.value }))}
              />
            </label>
            <label>
              <span>Descuento</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={cabeceraValues.descuento}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, descuento: event.target.value }))}
              />
            </label>
            <label>
              <span>Cuotas convenio</span>
              <input
                type="number"
                min="1"
                step="1"
                value={cabeceraValues.num_cuotas}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, num_cuotas: event.target.value }))}
              />
            </label>
            <label>
              <span>Control</span>
              <input
                type="number"
                min="0"
                value={cabeceraValues.control_matricula}
                onChange={(event) => setCabeceraValues((current) => ({ ...current, control_matricula: event.target.value }))}
              />
            </label>
          </div>
          {cabeceraError ? <p className="form-error">{cabeceraError}</p> : null}
          {cabeceraMessage ? <p className="form-success">{cabeceraMessage}</p> : null}
          <button
            type="button"
            className="primary-action"
            onClick={registerCabecera}
            disabled={cabeceraLoading || !selectedItem?.num}
          >
            {cabeceraLoading ? 'Guardando...' : hasCabecera ? 'Actualizar matricula/convenio' : 'Matricular y generar convenio'}
          </button>
        </article>
        ) : null}

        {activeStage === 'materias' && canManageAcademicEnrollment ? (
        <article className="student-card matricula-panel preinscripcion-action-card">
          <div className="section-title">
            <div>
              <span>Matriculacion</span>
              <h2>Matricula inicial de primer nivel</h2>
            </div>
            <button type="button" className="ghost-button" onClick={() => void loadEnrollmentData()} disabled={enrollmentLoading || !selectedItem?.num}>
              {enrollmentLoading ? 'Cargando...' : 'Actualizar primer nivel'}
            </button>
          </div>
          {!selectedItem ? (
            <p className="form-error">Selecciona un estudiante en Inscritos antes de matricular el primer nivel.</p>
          ) : null}
          <div className="preinscripcion-detail preinscripcion-detail--wide">
            <div>
              <span>Estudiante</span>
              <strong>{valueOrDash(selectedItem?.apellidos_nombre)}</strong>
            </div>
            <div>
              <span>Codigo estudiante</span>
              <strong>{valueOrDash(selectedStudentCode)}</strong>
            </div>
            <div>
              <span>Carrera</span>
              <strong>{valueOrDash(selectedItem?.carrera || selectedEnrollmentCareer)}</strong>
            </div>
            <div>
              <span>Periodo</span>
              <strong>{valueOrDash(selectedItem?.periodo || selectedEnrollmentPeriod)}</strong>
            </div>
          </div>
          {hasCabecera ? null : (
            <p className="form-error">Primero registra la matricula/cabecera y genera el convenio para conservar valores y codigo de documentacion.</p>
          )}
          {enrollmentError ? <p className="form-error">{enrollmentError}</p> : null}
          {enrollmentMessage ? <p className="form-success">{enrollmentMessage}</p> : null}
          <p className="form-success">Admisiones solo permite matricular materias del primer nivel para este proceso inicial.</p>

          <div className="matricula-acad-form preinscripcion-enrollment-form">
            <label>
              <span>Grupo</span>
              <input
                type="number"
                min="0"
                value={enrollmentGroup}
                onChange={(event) => setEnrollmentGroup(event.target.value)}
              />
            </label>
            <label>
              <span>Tipo matricula</span>
              <select value={enrollmentType} onChange={(event) => setEnrollmentType(event.target.value as MatriculaTipo)}>
                <option value="R">Regular</option>
                <option value="H">Homologacion</option>
                <option value="E">Especial</option>
              </select>
            </label>
            <label>
              <span>Control matricula</span>
              <input
                type="number"
                min="0"
                value={enrollmentControl}
                onChange={(event) => setEnrollmentControl(event.target.value)}
              />
            </label>
          </div>

          <div className="preinscripcion-subject-toolbar">
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setEnrollmentSubjectCodes(enrollmentPensum.map((subject) => subject.codigo_materia))
              }}
              disabled={enrollmentPensum.length === 0}
            >
              Seleccionar primer nivel
            </button>
            <button type="button" className="ghost-button" onClick={() => setEnrollmentSubjectCodes([])} disabled={enrollmentSubjectCodes.length === 0}>
              Limpiar
            </button>
            <span>
              {selectedEnrollmentSubjects.length} de {enrollmentPensum.length} materia(s)
            </span>
          </div>

          <div className="matricula-table-wrap excel-table-wrap preinscripcion-subject-table">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Nivel</th>
                  <th>Codigo</th>
                  <th>Materia</th>
                  <th>Creditos</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {enrollmentPensum.length > 0 ? enrollmentSemesterGroups.flatMap(([groupLabel, subjects]) =>
                  subjects.map((subject) => {
                    const checked = enrollmentSubjectCodes.includes(subject.codigo_materia)
                    const current = currentEnrollmentCodes.has(subject.codigo_materia)
                    return (
                      <tr key={`${groupLabel}-${subject.codigo_materia}`} className={checked ? 'preinscripcion-row--active' : ''}>
                        <td>
                          <label className="preinscripcion-subject-check">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) =>
                                setEnrollmentSubjectCodes((currentCodes) =>
                                  event.target.checked
                                    ? [...new Set([...currentCodes, subject.codigo_materia])]
                                    : currentCodes.filter((code) => code !== subject.codigo_materia),
                                )
                              }
                            />
                          </label>
                        </td>
                        <td>{groupLabel}</td>
                        <td>{valueOrDash(subject.cod_materia || subject.codigo_materia)}</td>
                        <td>
                          <strong>{valueOrDash(subject.nombre_materia)}</strong>
                        </td>
                        <td>{valueOrDash(subject.creditos)}</td>
                        <td>{current ? 'Ya matriculada' : checked ? 'Por matricular' : '-'}</td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={6}>{enrollmentLoading ? 'Consultando pensum...' : 'Sin materias para mostrar.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <label className="preinscripcion-finish-check">
            <input
              type="checkbox"
              checked={enrollmentFinalizeProcess}
              onChange={(event) => setEnrollmentFinalizeProcess(event.target.checked)}
            />
            <span>Finalizar proceso al guardar la matricula inicial</span>
          </label>

          <div className="matricula-acad-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={() => void previewEnrollmentSubjects()}
              disabled={enrollmentPreviewLoading || !selectedItem?.num || enrollmentSubjectCodes.length === 0}
            >
              {enrollmentPreviewLoading ? 'Validando...' : 'Vista previa'}
            </button>
            <button
              type="button"
              className="primary-action"
              onClick={() => void saveEnrollmentSubjects()}
              disabled={enrollmentSaveLoading || !selectedItem?.num || enrollmentSubjectCodes.length === 0}
            >
              {enrollmentSaveLoading ? 'Guardando...' : 'Guardar matricula inicial'}
            </button>
          </div>

          {enrollmentPreview ? (
            <div className="matricula-acad-preview preinscripcion-summary">
              <div>
                <span>Seleccionadas</span>
                <strong>{enrollmentPreview.summary?.seleccionadas ?? selectedEnrollmentSubjects.length}</strong>
              </div>
              <div>
                <span>Insertar</span>
                <strong>{enrollmentPreview.summary?.insertar ?? 0}</strong>
              </div>
              <div>
                <span>Actualizar</span>
                <strong>{enrollmentPreview.summary?.actualizar ?? 0}</strong>
              </div>
              <div>
                <span>Bloqueadas</span>
                <strong>{enrollmentPreview.summary?.bloqueadas_por_notas ?? 0}</strong>
              </div>
            </div>
          ) : null}
        </article>
        ) : null}
      </section>

      <section className="student-grid student-grid--content preinscripcion-grid">
        {activeStage === 'inscritos' ? (
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Listado</span>
              <h2>Inscripciones</h2>
            </div>
          <div className="preinscripcion-title-actions">
              {selectedItem ? (
                <button type="button" className="ghost-button" onClick={() => setStudentScreenOpen(true)}>
                  Ver estudiante
                </button>
              ) : null}
              <span>{loading ? 'Cargando...' : `${visibleRows.length} de ${rows.length} registro(s)`}</span>
            </div>
          </div>
          <div className="excel-toolbar preinscripcion-excel-toolbar">
            <label>
              <span>Filtrar tabla</span>
              <input
                value={tableFilter}
                onChange={(event) => setTableFilter(event.target.value)}
                placeholder="Nombre, cedula, correo, carrera o codigo"
              />
            </label>
            <div>
              <strong>{visibleRows.length}</strong>
              <span>estudiante(s) visibles</span>
            </div>
            <small>Selecciona una fila y continua con Cabecera matricula, Documentos o Matricular primer nivel</small>
          </div>
          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Sel.</th>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Periodo</th>
                  <th>Cabecera</th>
                  <th>Codigo doc.</th>
                  <th>Docs</th>
                  <th>Ingreso</th>
                  <th>Accion</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? visibleRows.map((item, rowIndex) => {
                  const selected = selectedItem?.num === item.num
                  return (
                    <tr
                      key={`${item.num}-${item.codestu}-${item.codperiodo}`}
                      className={selected ? 'preinscripcion-row--active' : ''}
                      onClick={() => selectStudent(item)}
                      onDoubleClick={() => openStudentScreen(item)}
                    >
                      <td>{rowIndex + 1}</td>
                      <td>
                        <span className={`preinscripcion-select-mark ${selected ? 'preinscripcion-select-mark--active' : ''}`}>
                          {selected ? 'OK' : ''}
                        </span>
                      </td>
                      <td>
                        <strong>{valueOrDash(item.apellidos_nombre)}</strong>
                        <small>{valueOrDash(item.cedula || item.codestu)}</small>
                      </td>
                      <td>
                        <span>{valueOrDash(item.carrera)}</span>
                        <small>{valueOrDash(item.codcarrera)}</small>
                      </td>
                      <td>
                        <span>{valueOrDash(item.periodo)}</span>
                        <small>{valueOrDash(item.codperiodo)}</small>
                      </td>
                      <td>{item.en_cabecera_matricula ? 'Si' : 'No'}</td>
                      <td>{valueOrDash(item.cabecera?.numcodigo || item.cabecera?.num_matricula)}</td>
                      <td>{documentStatus(item)}</td>
                      <td>{valueOrDash(item.fecha_ingreso)}</td>
                      <td>
                        <div className="preinscripcion-row-actions">
                          {!isAdmissionsRole ? (
                            <button
                              type="button"
                              className="ghost-button preinscripcion-row-button"
                              onClick={(event) => {
                                event.stopPropagation()
                                selectStudent(item)
                                onStageChange('seguimiento')
                              }}
                            >
                              Seguimiento
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="ghost-button preinscripcion-row-button"
                            onClick={(event) => {
                              event.stopPropagation()
                              selectStudent(item)
                              onStageChange('cabecera')
                            }}
                          >
                            Cabecera
                          </button>
                          <button
                            type="button"
                            className="ghost-button preinscripcion-row-button"
                            onClick={(event) => {
                              event.stopPropagation()
                              selectStudent(item)
                              onStageChange('materias')
                            }}
                          >
                            Primer nivel
                          </button>
                          <button
                            type="button"
                            className="ghost-button preinscripcion-row-button"
                            onClick={(event) => {
                              event.stopPropagation()
                              selectStudent(item)
                              onStageChange('documentos')
                            }}
                          >
                            Documentos
                          </button>
                          {!isAdmissionsRole ? (
                            <button
                              type="button"
                              className="danger-action preinscripcion-row-button"
                              onClick={(event) => {
                                event.stopPropagation()
                                void revertSelectedProcess(item)
                              }}
                              disabled={revertLoading}
                            >
                              Revertir
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )
                }) : (
                  <tr>
                    <td colSpan={10}>{loading ? 'Consultando...' : 'Sin inscripciones para mostrar.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
        ) : null}

        {activeStage === 'documentos' ? (
        <article className="student-card matricula-panel preinscripcion-action-card">
          <div className="section-title">
            <div>
              <span>Paso 2</span>
              <h2>{hasCabecera ? `Matricula y convenio ${codigoDocumentacion}` : 'Matricular y generar convenio de pago'}</h2>
            </div>
          </div>
          {!selectedItem ? (
            <p className="form-error">Selecciona un estudiante en Inscritos antes de cargar documentos.</p>
          ) : null}
          <div className="preinscripcion-detail">
            <div>
              <span>Cedula</span>
              <strong>{valueOrDash(selectedItem?.cedula)}</strong>
            </div>
            <div>
              <span>Correo</span>
              <strong>{valueOrDash(selectedItem?.correo)}</strong>
            </div>
            <div>
              <span>Proceso finalizado</span>
              <strong>{boolLabel(selectedItem?.proceso_finalizado)}</strong>
            </div>
          </div>
          {!hasCabecera ? (
            <p className="form-error">Primero registra la matricula/cabecera para generar el convenio de pago y habilitar la documentacion.</p>
          ) : null}

          <div className="preinscripcion-step-stack">
            <section className="preinscripcion-step-part">
              <div className="preinscripcion-step-part__head">
                <div>
                  <span>Parte 2.1</span>
                  <strong>Elaborar convenio de pago</strong>
                </div>
                <em>{hasCabecera ? 'Convenio generado' : 'Pendiente de generar'}</em>
              </div>
              <div className="matricula-acad-preview">
                <div>
                  <span>Total convenio</span>
                  <strong>{formatMoney(paymentPlanPreview.total)}</strong>
                </div>
                <div>
                  <span>Alcance</span>
                  <strong>{paymentPlanPreview.selectedSemesters} semestre(s)</strong>
                </div>
                <div>
                  <span>Saldo convenio</span>
                  <strong>{formatMoney(paymentPlanPreview.saldo)}</strong>
                </div>
                <div>
                  <span>Cuotas</span>
                  <strong>{paymentPlanPreview.cuotas} x {formatMoney(paymentPlanPreview.cuota)}</strong>
                </div>
                <div>
                  <span>Beca</span>
                  <strong>{formatMoney(paymentPlanPreview.beca)} ({formatMoney(paymentPlanPreview.porcentajeBeca)}%)</strong>
                </div>
              </div>
              <div className="preinscripcion-cabecera-form">
                <label>
                  <span>No. pago</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={cabeceraValues.num_pago}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, num_pago: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Fecha de pago</span>
                  <input
                    type="date"
                    value={cabeceraValues.fecha_pago}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, fecha_pago: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Cuotas convenio</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={cabeceraValues.num_cuotas}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, num_cuotas: event.target.value }))}
                  />
                </label>
                {renderPaymentScopeSelector()}
                {renderScholarshipSelector()}
                <label>
                  <span>% beca</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={cabeceraValues.porcentaje_beca}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, porcentaje_beca: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Inscripcion</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={cabeceraValues.inscrip_valor}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, inscrip_valor: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Matricula</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={cabeceraValues.matri_valor}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, matri_valor: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Valor total calculado</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={paymentPlanPreview.total}
                    readOnly
                  />
                </label>
                <label>
                  <span>Descuento</span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={cabeceraValues.descuento}
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, descuento: event.target.value }))}
                  />
                </label>
                <label className="preinscripcion-followup-form__wide">
                  <span>Detalle para el convenio</span>
                  <textarea
                    value={cabeceraValues.detalle_pago}
                    placeholder="Ej. Convenio de pago por aranceles"
                    onChange={(event) => setCabeceraValues((current) => ({ ...current, detalle_pago: event.target.value }))}
                  />
                </label>
              </div>
              {cabeceraError ? <p className="form-error">{cabeceraError}</p> : null}
              {cabeceraMessage ? <p className="form-success">{cabeceraMessage}</p> : null}
              <button
                type="button"
                className="primary-action"
                onClick={registerCabecera}
                disabled={cabeceraLoading || !selectedItem?.num}
              >
                {cabeceraLoading ? 'Generando...' : hasCabecera ? 'Actualizar convenio PDF' : 'Crear matricula y generar convenio PDF'}
              </button>
            </section>

            <section className="preinscripcion-step-part">
              <div className="preinscripcion-step-part__head">
                <div>
                  <span>Parte 2.2</span>
                  <strong>Enviar convenio al estudiante para firma</strong>
                </div>
                <em>{convenioUrl ? 'Listo para enviar' : 'Esperando PDF'}</em>
              </div>
              <p>
                Descarga el convenio generado y envialo al estudiante para que lo firme y confirme el compromiso de pago
                de las cuotas registradas.
              </p>
              {convenioUrl ? (
                <a className="ghost-button" href={convenioUrl} target="_blank" rel="noreferrer" download>
                  Descargar convenio PDF
                </a>
              ) : (
                <small>Genera primero la matricula/convenio para habilitar la descarga.</small>
              )}
            </section>
          </div>

          <div className="preinscripcion-convenio-card">
            <div>
              <span>Parte 2.3 · Documentacion y convenio firmado</span>
              <strong>{paymentPlanPreview.cuotas} cuota(s) de {formatMoney(paymentPlanPreview.cuota)}</strong>
              <small>
                Sube los respaldos del estudiante y el convenio firmado cuando lo devuelva.
              </small>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={registerCabecera}
              disabled={cabeceraLoading || !selectedItem?.num}
            >
              {cabeceraLoading ? 'Generando...' : hasCabecera ? 'Actualizar convenio' : 'Matricular y generar convenio'}
            </button>
            {convenioUrl ? (
              <a className="ghost-button" href={convenioUrl} target="_blank" rel="noreferrer" download>
                Descargar carta PDF
              </a>
            ) : null}
          </div>

          <div className="preinscripcion-photo">
            <div className="preinscripcion-photo__main">
              <div className="preinscripcion-photo__preview">
                {photoStatus?.foto_url ? (
                  <img src={photoStatus.foto_url} alt="Foto de carnet cargada" />
                ) : (
                  <span>Sin imagen</span>
                )}
              </div>
              <div className="preinscripcion-photo__content">
                <div className="preinscripcion-photo__title">
                  <div>
                    <span>Foto de carnet</span>
                    <strong>Requiere aprobacion previa</strong>
                  </div>
                  <em className={`preinscripcion-photo__status ${photoStatusClass(photoStatus?.estado)}`}>
                    {photoLoading ? 'Procesando...' : photoStatusLabel(photoStatus?.estado)}
                  </em>
                </div>
                <p>
                  La imagen subida queda como solicitud pendiente. Solo una foto aprobada podra usarse para emitir el
                  carnet del estudiante.
                </p>
                {photoStatus?.observacion_admin ? <small>{photoStatus.observacion_admin}</small> : null}
                <div className="preinscripcion-photo__actions">
                  <label className="ghost-button preinscripcion-photo__upload">
                    <span>{photoStatus?.estado === 'PENDIENTE' ? 'Reemplazar foto' : 'Subir foto'}</span>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      disabled={!hasCabecera || photoLoading}
                      onChange={(event) => {
                        void uploadCarnetPhoto(event.target.files?.[0])
                        event.currentTarget.value = ''
                      }}
                    />
                  </label>
                  {photoStatus?.foto_url ? (
                    <a className="ghost-button" href={photoStatus.foto_url} target="_blank" rel="noreferrer">
                      Abrir foto
                    </a>
                  ) : null}
                  {photoStatus?.estado === 'PENDIENTE' && photoStatus.id_solicitud_foto ? (
                    <>
                      <button type="button" className="primary-action" onClick={() => void approveCarnetPhoto()} disabled={photoLoading}>
                        Aprobar foto
                      </button>
                      <button type="button" className="danger-action" onClick={() => void rejectCarnetPhoto()} disabled={photoLoading}>
                        Rechazar
                      </button>
                    </>
                  ) : null}
                </div>
                {!hasCabecera ? <small>Primero registra la cabecera de matricula para habilitar la carga.</small> : null}
                {photoError ? <p className="form-error">{photoError}</p> : null}
                {photoMessage ? <p className="form-success">{photoMessage}</p> : null}
              </div>
            </div>
          </div>

          <div className="preinscripcion-doc-form">
            {selectedDocuments.map((document) => (
              <label key={document.key}>
                <span>{document.label}</span>
                <input
                  value={document.value}
                  placeholder="URL o ruta del documento"
                  disabled={!hasCabecera}
                  onChange={(event) => setDocuments((current) => ({ ...current, [document.key]: event.target.value }))}
                />
                <input
                  type="file"
                  disabled={!hasCabecera || uploadingField === document.key}
                  onChange={(event) => {
                    void uploadDocument(document.key, event.target.files?.[0])
                    event.currentTarget.value = ''
                  }}
                />
                {uploadingField === document.key ? <small>Subiendo...</small> : null}
                {document.value ? (
                  <a href={document.value} target="_blank" rel="noreferrer">
                    Abrir documento
                  </a>
                ) : null}
              </label>
            ))}
          </div>

          {saveError ? <p className="form-error">{saveError}</p> : null}
          {saveMessage ? <p className="form-success">{saveMessage}</p> : null}
          <button
            type="button"
            className="primary-action"
            onClick={saveDocuments}
            disabled={saveLoading || !selectedItem?.num || !hasCabecera}
          >
            {saveLoading ? 'Guardando...' : 'Guardar documentos'}
          </button>
        </article>
        ) : null}
      </section>
      </>
      ) : null}

      {studentSelectorOpen ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="student-selector-title">
          <article className="matricula-modal matricula-docente-selector-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>Estudiante</span>
                <h3 id="student-selector-title">Seleccionar estudiante</h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setStudentSelectorOpen(false)}>
                Cerrar
              </button>
            </div>

            <div className="matricula-docente-selector-controls preinscripcion-student-selector-controls">
              <label>
                <span>Buscar estudiante</span>
                <input
                  value={followupSearch}
                  placeholder="Cedula, correo o nombre"
                  onChange={(event) => setFollowupSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void searchFollowupApplicants()
                    }
                  }}
                />
              </label>
              <button type="button" className="ghost-button" onClick={() => void searchFollowupApplicants()} disabled={followupSearchLoading}>
                {followupSearchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {followupSearchError ? <p className="form-error">{followupSearchError}</p> : null}

            <div className="matricula-docente-selector-summary">
              <strong>Listado de estudiantes disponibles</strong>
              <span>{followupSearchLoading ? 'Cargando estudiantes...' : `${followupSearchResults.length} estudiante(s) cargado(s)`}</span>
            </div>

            <div className="matricula-docente-selector-list">
              {followupSearchResults.length === 0 && !followupSearchLoading ? (
                <div className="matricula-docente-selector-empty">
                  <strong>Sin resultados</strong>
                  <span>No hay estudiantes para los filtros aplicados.</span>
                </div>
              ) : null}
              {followupSearchResults.map((item) => {
                const checked = pendingStudentNum === item.num
                return (
                  <button
                    key={`${item.num}-${item.codestu}-${item.cedula}`}
                    type="button"
                    className={`matricula-acad-teacher-option ${checked ? 'matricula-acad-teacher-option--active' : ''}`}
                    aria-pressed={checked}
                    onClick={() => markSingleFollowupStudent(item)}
                  >
                    <label className="matricula-docente-check-row" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="radio"
                        name="preinscripcion-student-selector"
                        checked={checked}
                        onChange={() => markSingleFollowupStudent(item)}
                      />
                      <strong>{item.apellidos_nombre || item.cedula || item.codestu || 'Estudiante'}</strong>
                    </label>
                    <span>{valueOrDash(item.cedula)} - {valueOrDash(item.correo)}</span>
                    <span>{valueOrDash(item.periodo)} - {valueOrDash(item.carrera)}</span>
                    <span>
                      {item.en_cabecera_matricula ? 'Con pago/convenio' : 'Sin pago/convenio'} - Documentos {documentStatus(item)}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setStudentSelectorOpen(false)}>
                Cancelar
              </button>
              <button type="button" className="primary-action" onClick={confirmFollowupStudentSelection} disabled={!pendingStudentNum}>
                Seleccionar estudiante
              </button>
            </div>
          </article>
        </div>
      ) : null}

      {studentScreenOpen && selectedItem ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="preinscripcion-student-title">
          <article className="matricula-modal preinscripcion-student-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>Estudiante seleccionado</span>
                <h3 id="preinscripcion-student-title">{selectedItem.apellidos_nombre || 'Sin nombre'}</h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setStudentScreenOpen(false)}>
                Cerrar
              </button>
            </div>

            <div className="preinscripcion-student-screen">
              <section className="preinscripcion-student-panel">
                <div className="section-title">
                  <div>
                    <span>Datos</span>
                    <h2>Inscripcion</h2>
                  </div>
                  <span className={hasCabecera ? 'preinscripcion-status preinscripcion-status--ok' : 'preinscripcion-status'}>
                    {hasCabecera ? 'Con cabecera' : 'Sin cabecera'}
                  </span>
                </div>
                <div className="preinscripcion-detail preinscripcion-detail--wide">
                  <div>
                    <span>Cedula</span>
                    <strong>{valueOrDash(selectedItem.cedula)}</strong>
                  </div>
                  <div>
                    <span>Codigo estudiante</span>
                    <strong>{valueOrDash(selectedItem.datos_codigo_estud || selectedItem.codestu)}</strong>
                  </div>
                  <div>
                    <span>Correo</span>
                    <strong>{valueOrDash(selectedItem.correo)}</strong>
                  </div>
                  <div>
                    <span>Telefono</span>
                    <strong>{valueOrDash(selectedItem.telefono)}</strong>
                  </div>
                  <div>
                    <span>Carrera</span>
                    <strong>{valueOrDash(selectedItem.carrera || selectedItem.codcarrera)}</strong>
                  </div>
                  <div>
                    <span>Periodo</span>
                    <strong>{valueOrDash(selectedItem.periodo || selectedItem.codperiodo)}</strong>
                  </div>
                  <div>
                    <span>Proceso finalizado</span>
                    <strong>{boolLabel(selectedItem.proceso_finalizado)}</strong>
                  </div>
                </div>
              </section>

              <section className="preinscripcion-student-panel">
                <div className="section-title">
                  <div>
                    <span>Paso 2</span>
                    <h2>Matricula y convenio de pago</h2>
                  </div>
                  <strong>{valueOrDash(codigoDocumentacion)}</strong>
                </div>
                <div className="matricula-acad-preview">
                  <div>
                    <span>Total convenio</span>
                    <strong>{formatMoney(paymentPlanPreview.total)}</strong>
                  </div>
                  <div>
                    <span>Alcance</span>
                    <strong>{paymentPlanPreview.selectedSemesters} semestre(s)</strong>
                  </div>
                  <div>
                    <span>Beca</span>
                    <strong>{formatMoney(paymentPlanPreview.beca)} ({formatMoney(paymentPlanPreview.porcentajeBeca)}%)</strong>
                  </div>
                  <div>
                    <span>Saldo convenio</span>
                    <strong>{formatMoney(paymentPlanPreview.saldo)}</strong>
                  </div>
                  <div>
                    <span>Cuotas</span>
                    <strong>{paymentPlanPreview.cuotas} x {formatMoney(paymentPlanPreview.cuota)}</strong>
                  </div>
                </div>
                <div className="preinscripcion-cabecera-form">
                  <label>
                    <span>No. pago</span>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={cabeceraValues.num_pago}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, num_pago: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Fecha de pago</span>
                    <input
                      type="date"
                      value={cabeceraValues.fecha_pago}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, fecha_pago: event.target.value }))}
                    />
                  </label>
                  <label className="preinscripcion-followup-form__wide">
                    <span>Detalle del pago/convenio</span>
                    <textarea
                      value={cabeceraValues.detalle_pago}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, detalle_pago: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Inscripcion</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={cabeceraValues.inscrip_valor}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, inscrip_valor: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Matricula</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={cabeceraValues.matri_valor}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, matri_valor: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Valor total calculado</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={paymentPlanPreview.total}
                      readOnly
                    />
                  </label>
                  <label>
                    <span>No. deposito/ref.</span>
                    <input
                      value={cabeceraValues.no_deposito}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, no_deposito: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Banco</span>
                    <input
                      value={cabeceraValues.banco}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, banco: event.target.value }))}
                    />
                  </label>
                  {renderPaymentScopeSelector()}
                  {renderScholarshipSelector()}
                  <label>
                    <span>% beca</span>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={cabeceraValues.porcentaje_beca}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, porcentaje_beca: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Descuento</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={cabeceraValues.descuento}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, descuento: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Cuotas convenio</span>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={cabeceraValues.num_cuotas}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, num_cuotas: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Control</span>
                    <input
                      type="number"
                      min="0"
                      value={cabeceraValues.control_matricula}
                      onChange={(event) => setCabeceraValues((current) => ({ ...current, control_matricula: event.target.value }))}
                    />
                  </label>
                </div>
                {cabeceraError ? <p className="form-error">{cabeceraError}</p> : null}
                {cabeceraMessage ? <p className="form-success">{cabeceraMessage}</p> : null}
                <button
                  type="button"
                  className="primary-action"
                  onClick={registerCabecera}
                  disabled={cabeceraLoading || !selectedItem.num}
                >
                  {cabeceraLoading ? 'Guardando...' : hasCabecera ? 'Actualizar cabecera' : 'Guardar cabecera y generar convenio'}
                </button>
              </section>

              <section className="preinscripcion-student-panel preinscripcion-student-panel--wide">
                <div className="section-title">
                  <div>
                    <span>Documentacion</span>
                    <h2>{hasCabecera ? `Codigo ${codigoDocumentacion}` : 'Pendiente de matricula/convenio'}</h2>
                  </div>
                </div>
                {!hasCabecera ? (
                  <p className="form-error">Registra la cabecera de matricula antes de subir documentos.</p>
                ) : null}
                <div className="preinscripcion-convenio-card">
                  <div>
                    <span>Convenio y beca</span>
                    <strong>{paymentPlanPreview.cuotas} cuota(s) de {formatMoney(paymentPlanPreview.cuota)}</strong>
                    <small>
                      Beca {formatMoney(paymentPlanPreview.beca)} ({formatMoney(paymentPlanPreview.porcentajeBeca)}%) - saldo {formatMoney(paymentPlanPreview.saldo)}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={registerCabecera}
                    disabled={cabeceraLoading || !selectedItem.num}
                  >
                    {cabeceraLoading ? 'Generando...' : hasCabecera ? 'Actualizar convenio' : 'Guardar pago y generar convenio'}
                  </button>
                  {convenioUrl ? (
                    <a className="ghost-button" href={convenioUrl} target="_blank" rel="noreferrer" download>
                      Descargar carta PDF
                    </a>
                  ) : null}
                </div>
                <div className="preinscripcion-doc-form preinscripcion-doc-form--grid">
                  {selectedDocuments.map((document) => (
                    <label key={`modal-${document.key}`}>
                      <span>{document.label}</span>
                      <input
                        value={document.value}
                        placeholder="URL o ruta del documento"
                        disabled={!hasCabecera}
                        onChange={(event) => setDocuments((current) => ({ ...current, [document.key]: event.target.value }))}
                      />
                      <input
                        type="file"
                        disabled={!hasCabecera || uploadingField === document.key}
                        onChange={(event) => {
                          void uploadDocument(document.key, event.target.files?.[0])
                          event.currentTarget.value = ''
                        }}
                      />
                      {uploadingField === document.key ? <small>Subiendo...</small> : null}
                      {document.value ? (
                        <a href={document.value} target="_blank" rel="noreferrer">
                          Abrir documento
                        </a>
                      ) : null}
                    </label>
                  ))}
                </div>
                {saveError ? <p className="form-error">{saveError}</p> : null}
                {saveMessage ? <p className="form-success">{saveMessage}</p> : null}
                <button
                  type="button"
                  className="primary-action"
                  onClick={saveDocuments}
                  disabled={saveLoading || !selectedItem.num || !hasCabecera}
                >
                  {saveLoading ? 'Guardando...' : 'Guardar documentos'}
                </button>
              </section>
            </div>
          </article>
        </div>
      ) : null}
    </div>
  )
}
