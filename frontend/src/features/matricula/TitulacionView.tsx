import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  addTitulacionTribunal,
  createTitulacionExpediente,
  fetchTitulacionAptos,
  fetchTitulacionExpediente,
  fetchTitulacionMallaCalificaciones,
  fetchTitulacionProgramacion,
  generateTitulacionActa,
  generateTitulacion,
  gradeTitulacionDefensa,
  gradeTitulacionExamen,
  programTitulacionDefensa,
  programTitulacionExamen,
  registerTitulacionIntec,
  registerTitulacionSenescyt,
  saveTitulacionNotas,
  saveTitulacionDefensaTema,
  selectTitulacionMecanismo,
  syncTitulacionPracticas,
  uploadTitulacionDocumento,
} from '../../lib/api'
import type {
  TitulacionAptoItem,
  TitulacionAptosResponse,
  TitulacionMallaCalificacionesResponse,
  TitulacionMecanismoCodigo,
  TitulacionProgramacionItem,
  TitulacionProgramacionResponse,
  TitulacionResponse,
} from '../../types/app'

type TitulacionViewProps = {
  displayName: string
  role: string
  section?: 'verificacion' | 'proceso' | 'responsables'
  onOpenProcesoTitulacion?: () => void
}

type AptosSortKey = 'name' | 'id' | 'career' | 'careerProgress' | 'english' | 'practices' | 'vinculacion'
type SortDirection = 'asc' | 'desc'

const DOCUMENT_TYPES = [
  { value: 'APTITUD_LEGAL', label: 'Aptitud legal' },
  { value: 'RUBRICA_TITULACION', label: 'Rúbrica unidad de titulación' },
  { value: 'ACTA_GRADO', label: 'Acta de grado' },
  { value: 'TITULO_SENESCYT', label: 'Título SENESCYT' },
  { value: 'TITULO_INTEC', label: 'Título INTEC' },
  { value: 'EVIDENCIA_EXAMEN_COMPLEXIVO', label: 'Evidencia examen complexivo' },
  { value: 'ACTA_EXAMEN_COMPLEXIVO', label: 'Acta examen complexivo' },
  { value: 'TRABAJO_FINAL_DEFENSA', label: 'Trabajo final defensa' },
  { value: 'INFORME_TUTOR_DEFENSA', label: 'Informe tutor defensa' },
  { value: 'ACTA_DEFENSA_GRADO', label: 'Acta defensa de grado' },
  { value: 'PRESENTACION_DEFENSA', label: 'Presentación defensa' },
]

const HORAS_REQUERIDAS_PRACTICAS = 240
const HORAS_REQUERIDAS_VINCULACION = 60
const MATERIAS_REQUERIDAS_TITULACION = 24

function boolValue(value: unknown) {
  return value === true || value === 1 || value === '1'
}

function numberText(value: unknown) {
  if (value === null || value === undefined || value === '') return '0'
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('es-EC', { maximumFractionDigits: 2 }) : String(value)
}

function percentValue(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return Math.max(0, Math.min(100, Math.round(number)))
}

function textValue(value: unknown) {
  return value === null || value === undefined || value === '' ? 'No registrado' : String(value)
}

function gradeText(value: unknown) {
  return value === null || value === undefined || value === '' ? '-' : numberText(value)
}

function gradeType(value: TitulacionMallaCalificacionesResponse['items'][number]) {
  const type = String(value.tipo_calculo || value.tipo_matricula || value.tipo_periodo || '').trim().toUpperCase()
  return type === 'H' ? 'H' : 'R'
}

function gradeKey(value: TitulacionMallaCalificacionesResponse['items'][number]) {
  return `${value.codigo_materia || 'materia'}-${value.codigo_periodo || 'pendiente'}`
}

function gradeDetailGroups(grade: TitulacionMallaCalificacionesResponse['items'][number]) {
  const type = gradeType(grade)
  const groups = [
    {
      title: 'Registro académico',
      items: [
        ['Matrícula', textValue(grade.num_matricula)],
        ['Paralelo', textValue(grade.paralelo)],
        ['Grupo', textValue(grade.num_grupo)],
        ['Periodo', textValue(grade.nombre_periodo || grade.codigo_periodo)],
      ],
    },
  ]
  if (type === 'R') {
    groups.push(
      {
        title: 'Parcial 1',
        items: [
          ['Tareas', gradeText(grade.p1_tareas)],
          ['Proyectos', gradeText(grade.p1_proyectos)],
          ['Examen', gradeText(grade.p1_examen)],
          ['Promedio P1', gradeText(grade.prom_p1)],
        ],
      },
      {
        title: 'Parcial 2',
        items: [
          ['Tareas', gradeText(grade.p2_tareas)],
          ['Proyectos', gradeText(grade.p2_proyectos)],
          ['Examen', gradeText(grade.p2_examen)],
          ['Promedio P2', gradeText(grade.prom_p2)],
        ],
      },
      {
        title: 'Parcial 3',
        items: [
          ['Tareas', gradeText(grade.p3_tareas)],
          ['Proyectos', gradeText(grade.p3_proyectos)],
          ['Examen', gradeText(grade.p3_examen)],
          ['Promedio P3', gradeText(grade.prom_p3)],
        ],
      },
    )
  } else {
    groups.push({
      title: 'Homologación',
      items: [
        ['Teórico', gradeText(grade.teoria_homo)],
        ['Práctico', gradeText(grade.practica_homo)],
      ],
    })
  }
  groups.push({
    title: 'Resultado',
    items: [
      ['Promedio', gradeText(grade.promedio)],
      ['Asistencia', gradeText(grade.asistencia)],
      ['Recuperación', gradeText(grade.recuperacion)],
      ['Promedio aux.', gradeText(grade.promedio_aux)],
      ['Promedio final', gradeText(grade.promedio_final_registrado)],
      ['Final calculado', gradeText(grade.nota_final)],
      ['Nota mínima', gradeText(grade.nota_aprobar)],
      ['Estado', textValue(grade.estado)],
    ],
  })
  return groups
}

function normalizeTime(value: unknown) {
  const text = String(value || '').slice(0, 5)
  return /^\d{2}:\d{2}$/.test(text) ? text : '09:00'
}

function teamsCalendarLink(item: TitulacionProgramacionItem) {
  const date = String(item.FechaProgramada || '').slice(0, 10)
  const time = normalizeTime(item.HoraProgramada)
  const start = date ? new Date(`${date}T${time}:00`) : new Date()
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  const title = `${textValue(item.MecanismoNombre)} - ${textValue(item.ApellidosNombres)}`
  const body = [
    `Proceso: ${textValue(item.MecanismoNombre)}`,
    `Estudiante: ${textValue(item.ApellidosNombres)}`,
    `Cédula: ${textValue(item.NumeroIdentificacion)}`,
    `Carrera: ${textValue(item.NombreCarrera)}`,
    item.TemaTrabajo ? `Tema: ${item.TemaTrabajo}` : '',
    item.Responsables ? `Responsables/tribunal: ${item.Responsables}` : '',
  ].filter(Boolean).join('\n')
  const params = new URLSearchParams({
    path: '/calendar/action/compose',
    rru: 'addevent',
    subject: title,
    body,
    location: String(item.Lugar || 'Microsoft Teams'),
    startdt: start.toISOString(),
    enddt: end.toISOString(),
    online: 'true',
  })
  return `https://outlook.office.com/calendar/0/deeplink/compose?${params.toString()}`
}

function defenseTopicSuggestions(career: unknown) {
  const name = String(career || 'la carrera').trim()
  return [
    `Diseño de una propuesta de mejora aplicada a ${name}`,
    `Implementación de un modelo de gestión para optimizar procesos en ${name}`,
    `Análisis de factibilidad de una solución técnica para ${name}`,
    `Evaluación de impacto de herramientas digitales en ${name}`,
  ]
}

export function TitulacionView({ displayName, role, section = 'verificacion', onOpenProcesoTitulacion }: TitulacionViewProps) {
  const [cedula, setCedula] = useState('')
  const [mainSection, setMainSection] = useState<'verificacion' | 'proceso' | 'responsables'>(section)
  const [activeArea, setActiveArea] = useState<'verificacion' | 'calificaciones' | 'documentos' | 'generacion'>('verificacion')
  const [data, setData] = useState<TitulacionResponse | null>(null)
  const [aptosData, setAptosData] = useState<TitulacionAptosResponse | null>(null)
  const [aptosLoading, setAptosLoading] = useState(false)
  const [programacionData, setProgramacionData] = useState<TitulacionProgramacionResponse | null>(null)
  const [programacionLoading, setProgramacionLoading] = useState(false)
  const [programacionSearch, setProgramacionSearch] = useState('')
  const [programacionFilter, setProgramacionFilter] = useState<'TODOS' | TitulacionMecanismoCodigo>('TODOS')
  const aptosRequestRef = useRef<Promise<void> | null>(null)
  const [aptosPage, setAptosPage] = useState(1)
  const [aptosSort, setAptosSort] = useState<{ key: AptosSortKey; direction: SortDirection }>({ key: 'name', direction: 'asc' })
  const [reviewItem, setReviewItem] = useState<TitulacionAptoItem | null>(null)
  const [mallaDetail, setMallaDetail] = useState<{
    item: TitulacionAptoItem
    data: TitulacionMallaCalificacionesResponse | null
    loading: boolean
    error: string
  } | null>(null)
  const [expandedRegularGrade, setExpandedRegularGrade] = useState<string | null>(null)
  const [reviewMechanism, setReviewMechanism] = useState<TitulacionMecanismoCodigo>('EXAMEN_COMPLEXIVO')
  const [reviewChecks, setReviewChecks] = useState({
    cedula_validada: true,
    titulo_bachiller_cumple: true,
    ingles_a2_cumple: false,
    no_adeuda_financiero: false,
    apto_sustentacion: false,
    rubrica_titulacion_cumple: false,
  })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [notaTitulacion, setNotaTitulacion] = useState('')
  const [promedioAsignaturas, setPromedioAsignaturas] = useState('')
  const [checks, setChecks] = useState({
    cedula_validada: true,
    titulo_bachiller_cumple: true,
    ingles_a2_cumple: false,
    no_adeuda_financiero: false,
    apto_sustentacion: false,
    rubrica_titulacion_cumple: false,
  })
  const [documentType, setDocumentType] = useState('APTITUD_LEGAL')
  const [documentFile, setDocumentFile] = useState<File | null>(null)
  const [documentObservation, setDocumentObservation] = useState('')
  const [mechanismCode, setMechanismCode] = useState<TitulacionMecanismoCodigo>('EXAMEN_COMPLEXIVO')
  const [programacion, setProgramacion] = useState({
    fecha_programada: '',
    hora_programada: '',
    modalidad: 'PRESENCIAL',
    lugar: '',
    enlace_virtual: '',
  })
  const [tribunal, setTribunal] = useState({
    rol_tribunal: 'JURADO',
    materia_asignada: '',
    nombre_miembro: '',
    cedula_miembro: '',
    correo_miembro: '',
    orden_firma: '',
  })
  const [examen, setExamen] = useState({
    nota_examen: '',
    codigo_examen: '',
    tipo_examen: '',
    observacion: '',
  })
  const [defensa, setDefensa] = useState({
    tema_trabajo: '',
    linea_investigacion: '',
    tutor: '',
    lector_oponente: '',
    nota_trabajo_escrito: '',
    nota_defensa_oral: '',
    observacion: '',
  })
  const [acta, setActa] = useState({
    numero_acta_grado: '',
    fecha_acta: '',
    hora_acta: '',
    ciudad: 'Quito',
    escuela: '',
    autoridad_academica: '',
    docente_evaluador: '',
    coordinador_academico: '',
    ruta_acta_pdf: '',
  })
  const [senescyt, setSenescyt] = useState({
    codigo_registro_senescyt: '',
    fecha_registro: '',
    ruta_documento_nube: '',
  })
  const [intec, setIntec] = useState({
    numero_titulo: '',
    fecha_emision: '',
    codigo_verificacion: '',
    ruta_documento_nube: '',
  })

  const expediente = data?.expediente
  const academic = data?.academic
  const prevalidation = data?.prevalidation
  const mechanism = data?.mechanism
  const generation = data?.generation
  const mechanismValidation = mechanism?.prevalidation
  const canEdit = ['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA', 'SOPORTE'].includes(role)
  const puedeTitularse = boolValue(prevalidation?.PuedeTitularse)
  const mecanismoAprobado = boolValue(mechanismValidation?.MecanismoAprobado)
  const requisitoMalla = boolValue(academic?.malla_finalizada) || boolValue(expediente?.MallaCurricularCumple)
  const requisitoIngles = checks.ingles_a2_cumple || boolValue(expediente?.InglesA2Cumple)
  const requisitoPracticas = boolValue(expediente?.PracticasPreprofesionalesCumple)
  const requisitoVinculacion = boolValue(expediente?.VinculacionCumple)
  const requisitosInicialesCumplidos = requisitoMalla && requisitoIngles && requisitoPracticas && requisitoVinculacion
  const mallaPercent = percentValue(academic?.porcentaje_malla ?? ((Number(academic?.materias_aprobadas || 0) / MATERIAS_REQUERIDAS_TITULACION) * 100))
  const practicasPercent = percentValue((Number(expediente?.TotalHorasPracticasPreprofesionales || 0) / HORAS_REQUERIDAS_PRACTICAS) * 100)
  const vinculacionPercent = percentValue((Number(expediente?.TotalHorasVinculacion || 0) / HORAS_REQUERIDAS_VINCULACION) * 100)
  const aptosPageSize = 8
  const aptosSearchText = cedula.trim().toLowerCase()
  const filteredAptosItems = useMemo(() => {
    const items = aptosData?.items || []
    if (!aptosSearchText) return items
    const document = aptosSearchText.replace(/\D+/g, '')
    return items.filter((item) => {
      const name = String(item.ApellidosNombres || '').toLowerCase()
      const id = String(item.NumeroIdentificacion || '').toLowerCase()
      const idDigits = id.replace(/\D+/g, '')
      const career = String(item.NombreCarrera || '').toLowerCase()
      return (
        name.includes(aptosSearchText)
        || id.includes(aptosSearchText)
        || career.includes(aptosSearchText)
        || (document.length > 0 && idDigits.includes(document))
      )
    })
  }, [aptosData, aptosSearchText])
  const sortedAptosItems = useMemo(() => {
    const valueForSort = (item: TitulacionAptoItem) => {
      switch (aptosSort.key) {
        case 'name':
          return String(item.ApellidosNombres || '').trim().toLowerCase()
        case 'id':
          return String(item.NumeroIdentificacion || '').replace(/\D+/g, '')
        case 'career':
          return String(item.NombreCarrera || '').trim().toLowerCase()
        case 'careerProgress':
          return Number(item.MateriasAprobadas || 0)
        case 'english':
          return item.CumpleInglesA2Avanzado ? 1 : 0
        case 'practices':
          return Number(item.TotalHorasPracticasPreprofesionales || 0)
        case 'vinculacion':
          return Number(item.TotalHorasVinculacion || 0)
        default:
          return ''
      }
    }

    return [...filteredAptosItems].sort((left, right) => {
      const leftValue = valueForSort(left)
      const rightValue = valueForSort(right)
      let result = 0
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        result = leftValue - rightValue
      } else {
        result = String(leftValue).localeCompare(String(rightValue), 'es', { numeric: true, sensitivity: 'base' })
      }
      return aptosSort.direction === 'asc' ? result : -result
    })
  }, [aptosSort, filteredAptosItems])
  const aptosTotalPages = Math.max(1, Math.ceil(sortedAptosItems.length / aptosPageSize))
  const currentAptosPage = Math.min(aptosPage, aptosTotalPages)
  const paginatedAptosItems = sortedAptosItems.slice((currentAptosPage - 1) * aptosPageSize, currentAptosPage * aptosPageSize)
  const programacionItems = programacionData?.items || []
  const procesoTotal = programacionData?.total || 0
  const procesoComplexivoTotal = programacionData?.complexivo || 0
  const procesoDefensaTotal = programacionData?.defensa || 0

  function changeAptosSort(key: AptosSortKey) {
    setAptosSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }))
    setAptosPage(1)
  }

  function sortLabel(key: AptosSortKey) {
    if (aptosSort.key !== key) return 'Ordenar'
    return aptosSort.direction === 'asc' ? 'Asc' : 'Desc'
  }

  async function openMallaDetail(item: TitulacionAptoItem) {
    setMallaDetail({ item, data: null, loading: true, error: '' })
    try {
      const detail = await fetchTitulacionMallaCalificaciones(item.NumeroIdentificacion, item.CodAnioBasica)
      setMallaDetail({ item, data: detail, loading: false, error: '' })
    } catch (exc) {
      setMallaDetail({
        item,
        data: null,
        loading: false,
        error: exc instanceof Error ? exc.message : 'No se pudo consultar la malla del estudiante.',
      })
    }
  }

  const pendingMessage = useMemo(() => {
    if (!prevalidation) return ''
    return String(prevalidation.Mensaje || prevalidation.PendientesGeneracion || '')
  }, [prevalidation])

  const prerequisiteRows: Array<{
    label: string
    detail: string
    ok: boolean
    fixed?: boolean
    key?: keyof typeof checks
  }> = [
    {
      label: 'Malla académica completa',
      detail: `${numberText(academic?.materias_aprobadas)} / ${numberText(academic?.total_materias)} materias`,
      ok: requisitoMalla,
      fixed: true,
    },
    {
      label: 'Inglés A2+ - INTERMEDIATE',
      detail: 'Marcar cuando el requisito esté validado',
      ok: requisitoIngles,
      key: 'ingles_a2_cumple',
    },
    {
      label: 'Prácticas preprofesionales',
      detail: `${numberText(expediente?.TotalHorasPracticasPreprofesionales)} horas reconocidas`,
      ok: requisitoPracticas,
      fixed: true,
    },
    {
      label: 'Vinculación con la sociedad',
      detail: `${numberText(expediente?.TotalHorasVinculacion)} horas reconocidas`,
      ok: requisitoVinculacion,
      fixed: true,
    },
  ]

  const progressRows = [
    {
      area: 'Malla de la carrera',
      requerido: `${MATERIAS_REQUERIDAS_TITULACION} materias aprobadas`,
      actual: `${numberText(academic?.materias_aprobadas)} / ${MATERIAS_REQUERIDAS_TITULACION}`,
      percent: mallaPercent,
      ok: Number(academic?.materias_aprobadas || 0) >= MATERIAS_REQUERIDAS_TITULACION,
    },
    {
      area: 'Inglés',
      requerido: 'A2+ - INTERMEDIATE validado',
      actual: requisitoIngles ? 'Validado' : 'Pendiente',
      percent: requisitoIngles ? 100 : 0,
      ok: requisitoIngles,
    },
    {
      area: 'Prácticas preprofesionales',
      requerido: `${HORAS_REQUERIDAS_PRACTICAS} horas`,
      actual: `${numberText(expediente?.TotalHorasPracticasPreprofesionales)} / ${HORAS_REQUERIDAS_PRACTICAS} horas`,
      percent: practicasPercent,
      ok: requisitoPracticas,
    },
    {
      area: 'Vinculación con la sociedad',
      requerido: `${HORAS_REQUERIDAS_VINCULACION} horas`,
      actual: `${numberText(expediente?.TotalHorasVinculacion)} / ${HORAS_REQUERIDAS_VINCULACION} horas`,
      percent: vinculacionPercent,
      ok: requisitoVinculacion,
    },
  ]

  useEffect(() => {
    if (!data) return
    if (academic?.promedio_asignaturas !== undefined && academic.promedio_asignaturas !== null) {
      setPromedioAsignaturas(String(academic.promedio_asignaturas))
    } else if (expediente?.PromedioAsignaturas !== undefined && expediente.PromedioAsignaturas !== null) {
      setPromedioAsignaturas(String(expediente.PromedioAsignaturas))
    }
    if (expediente?.NotaProcesoTitulacion20 !== undefined && expediente.NotaProcesoTitulacion20 !== null) {
      setNotaTitulacion(String(Number(expediente.NotaProcesoTitulacion20) / 0.2))
    }
    if (expediente) {
      const selectedMechanism = String(mechanism?.selected?.MecanismoCodigo || expediente.MecanismoCodigo || '')
      if (selectedMechanism === 'EXAMEN_COMPLEXIVO' || selectedMechanism === 'DEFENSA_GRADO') {
        setMechanismCode(selectedMechanism)
      }
      setChecks({
        cedula_validada: boolValue(expediente.CedulaValidada),
        titulo_bachiller_cumple: boolValue(expediente.TituloBachillerCumple),
        ingles_a2_cumple: boolValue(expediente.InglesA2Cumple),
        no_adeuda_financiero: boolValue(expediente.NoAdeudaFinanciero),
        apto_sustentacion: boolValue(expediente.AptoSustentacion),
        rubrica_titulacion_cumple: boolValue(expediente.RubricaTitulacionCumple),
      })
    }
    if (mechanism?.programacion) {
      setProgramacion({
        fecha_programada: String(mechanism.programacion.FechaProgramada || '').slice(0, 10),
        hora_programada: String(mechanism.programacion.HoraProgramada || '').slice(0, 5),
        modalidad: String(mechanism.programacion.Modalidad || 'PRESENCIAL'),
        lugar: String(mechanism.programacion.Lugar || ''),
        enlace_virtual: String(mechanism.programacion.EnlaceVirtual || ''),
      })
    }
    if (mechanism?.examen) {
      setExamen({
        nota_examen: mechanism.examen.NotaExamen === null || mechanism.examen.NotaExamen === undefined ? '' : String(mechanism.examen.NotaExamen),
        codigo_examen: String(mechanism.examen.CodigoExamen || ''),
        tipo_examen: String(mechanism.examen.TipoExamen || ''),
        observacion: String(mechanism.examen.Observacion || ''),
      })
    }
    if (mechanism?.defensa) {
      setDefensa({
        tema_trabajo: String(mechanism.defensa.TemaTrabajo || ''),
        linea_investigacion: String(mechanism.defensa.LineaInvestigacion || ''),
        tutor: String(mechanism.defensa.Tutor || ''),
        lector_oponente: String(mechanism.defensa.LectorOponente || ''),
        nota_trabajo_escrito: mechanism.defensa.NotaTrabajoEscrito === null || mechanism.defensa.NotaTrabajoEscrito === undefined ? '' : String(mechanism.defensa.NotaTrabajoEscrito),
        nota_defensa_oral: mechanism.defensa.NotaDefensaOral === null || mechanism.defensa.NotaDefensaOral === undefined ? '' : String(mechanism.defensa.NotaDefensaOral),
        observacion: String(mechanism.defensa.Observacion || ''),
      })
    }
    if (expediente || generation?.acta) {
      setActa({
        numero_acta_grado: String(generation?.acta?.NumeroActaGrado || expediente?.NumeroActaGrado || ''),
        fecha_acta: String(generation?.acta?.FechaActa || expediente?.FechaActaGrado || '').slice(0, 10),
        hora_acta: String(generation?.acta?.HoraActa || '').slice(0, 5),
        ciudad: String(generation?.acta?.Ciudad || 'Quito'),
        escuela: String(generation?.acta?.Escuela || ''),
        autoridad_academica: String(generation?.acta?.AutoridadAcademica || ''),
        docente_evaluador: String(generation?.acta?.DocenteEvaluador || ''),
        coordinador_academico: String(generation?.acta?.CoordinadorAcademico || ''),
        ruta_acta_pdf: String(generation?.acta?.RutaActaPDF || ''),
      })
    }
    if (generation?.senescyt) {
      setSenescyt({
        codigo_registro_senescyt: String(generation.senescyt.CodigoRegistroSenescyt || ''),
        fecha_registro: String(generation.senescyt.FechaRegistro || '').slice(0, 10),
        ruta_documento_nube: String(generation.senescyt.RutaDocumentoNube || ''),
      })
    }
    if (generation?.intec) {
      setIntec({
        numero_titulo: String(generation.intec.NumeroTitulo || ''),
        fecha_emision: String(generation.intec.FechaEmision || '').slice(0, 10),
        codigo_verificacion: String(generation.intec.CodigoVerificacion || ''),
        ruta_documento_nube: String(generation.intec.RutaDocumentoNube || ''),
      })
    }
  }, [data])

  useEffect(() => {
    if (mainSection === 'verificacion' && data && !requisitosInicialesCumplidos && activeArea !== 'verificacion') {
      setActiveArea('verificacion')
    }
  }, [activeArea, data, mainSection, requisitosInicialesCumplidos])

  useEffect(() => {
    if (activeArea === 'documentos' || activeArea === 'generacion') {
      setActiveArea('verificacion')
    }
  }, [activeArea])

  useEffect(() => {
    setDocumentType(mechanismCode === 'DEFENSA_GRADO' ? 'TRABAJO_FINAL_DEFENSA' : 'EVIDENCIA_EXAMEN_COMPLEXIVO')
    setTribunal((current) => ({
      ...current,
      rol_tribunal: mechanismCode === 'DEFENSA_GRADO' ? 'JURADO' : 'RESPONSABLE',
    }))
  }, [mechanismCode])

  async function runAction(action: () => Promise<TitulacionResponse>, success: string) {
    setLoading(true)
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await action()
      setData(response)
      setMessage(response.message || success)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo completar la operación')
    } finally {
      setLoading(false)
      setSaving(false)
    }
  }

  async function search() {
    const clean = cedula.trim()
    setAptosPage(1)
    if (clean && /\D/.test(clean)) {
      setError('')
      setMessage('Filtro aplicado por nombre o carrera.')
      return
    }
    if (clean.length < 5) {
      setError('')
      setMessage('Filtro aplicado en la tabla.')
      return
    }
    await runAction(() => fetchTitulacionExpediente(clean), 'Consulta realizada.')
  }

  const loadAptos = useCallback(async () => {
    if (aptosRequestRef.current) {
      return aptosRequestRef.current
    }

    const request = (async () => {
      setAptosLoading(true)
      setError('')
      try {
        const response = await fetchTitulacionAptos({ limit: 1000 })
        setAptosData(response)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo verificar estudiantes aptos.')
      } finally {
        setAptosLoading(false)
        aptosRequestRef.current = null
      }
    })()

    aptosRequestRef.current = request
    return request
  }, [])

  const loadProgramacion = useCallback(async () => {
    setProgramacionLoading(true)
    setError('')
    try {
      const response = await fetchTitulacionProgramacion({
        limit: 500,
        search: programacionSearch.trim() || undefined,
        mecanismo: programacionFilter === 'TODOS' ? undefined : programacionFilter,
      })
      setProgramacionData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cargar el proceso de titulación.')
    } finally {
      setProgramacionLoading(false)
    }
  }, [programacionFilter, programacionSearch])

  useEffect(() => {
    void loadAptos()
  }, [loadAptos])

  useEffect(() => {
    setMainSection(section)
    if (section === 'proceso' || section === 'responsables') {
      setActiveArea('calificaciones')
    } else {
      setActiveArea('verificacion')
    }
    if (section === 'responsables' && programacionFilter === 'TODOS') {
      setProgramacionFilter('EXAMEN_COMPLEXIVO')
    }
  }, [section])

  useEffect(() => {
    if (mainSection === 'proceso' || mainSection === 'responsables') {
      void loadProgramacion()
    }
  }, [loadProgramacion, mainSection])

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void loadAptos()
      }
    }
    window.addEventListener('focus', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.removeEventListener('focus', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [loadAptos])

  useEffect(() => {
    setAptosPage(1)
  }, [aptosSearchText])

  useEffect(() => {
    if (!reviewItem) return
    setReviewChecks({
      cedula_validada: true,
      titulo_bachiller_cumple: true,
      ingles_a2_cumple: boolValue(reviewItem.CumpleInglesA2Avanzado),
      no_adeuda_financiero: false,
      apto_sustentacion: false,
      rubrica_titulacion_cumple: false,
    })
  }, [reviewItem])

  async function openProgramacionItem(item: TitulacionProgramacionItem) {
    const id = String(item.NumeroIdentificacion || '').trim()
    if (!id) {
      setError('El registro no tiene número de identificación.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const response = await fetchTitulacionExpediente(id)
      setCedula(id)
      setData(response)
      if (item.MecanismoCodigo === 'DEFENSA_GRADO' || item.MecanismoCodigo === 'EXAMEN_COMPLEXIVO') {
        setMechanismCode(item.MecanismoCodigo)
      }
      setProgramacion({
        fecha_programada: String(item.FechaProgramada || '').slice(0, 10),
        hora_programada: String(item.HoraProgramada || '').slice(0, 5),
        modalidad: String(item.Modalidad || 'PRESENCIAL'),
        lugar: String(item.Lugar || ''),
        enlace_virtual: String(item.EnlaceVirtual || ''),
      })
      if (item.MecanismoCodigo === 'DEFENSA_GRADO') {
        setDefensa((current) => ({
          ...current,
          tema_trabajo: String(item.TemaTrabajo || current.tema_trabajo || ''),
          linea_investigacion: String(item.LineaInvestigacion || current.linea_investigacion || ''),
          tutor: String(item.Tutor || current.tutor || ''),
          lector_oponente: String(item.LectorOponente || current.lector_oponente || ''),
        }))
      } else {
        setExamen((current) => ({
          ...current,
          codigo_examen: String(item.CodigoExamen || current.codigo_examen || ''),
          tipo_examen: String(item.TipoExamen || current.tipo_examen || ''),
        }))
      }
      setMainSection((current) => (current === 'responsables' ? 'responsables' : 'proceso'))
      setActiveArea('calificaciones')
      setMessage(mainSection === 'responsables' ? 'Estudiante cargado para registrar responsables.' : 'Proceso de titulación cargado.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo abrir el proceso seleccionado.')
    } finally {
      setLoading(false)
    }
  }

  async function proceedFromReview() {
    if (!reviewItem?.NumeroIdentificacion) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      let expedienteId = reviewItem.ExpedienteId ? Number(reviewItem.ExpedienteId) : null
      let response: TitulacionResponse | null = null
      if (!expedienteId) {
        response = await createTitulacionExpediente({
          numero_identificacion: String(reviewItem.NumeroIdentificacion),
          cod_anio_basica: reviewItem.CodAnioBasica || null,
          codigo_periodo: reviewItem.CodigoPeriodo || null,
          titulo_otorgado: null,
        })
        expedienteId = response.expediente?.ExpedienteId || null
      }
      if (!expedienteId) throw new Error('No se pudo crear o localizar el expediente.')
      await saveTitulacionNotas({
        expediente_id: expedienteId,
        promedio_asignaturas: Number(reviewItem.PromedioAsignaturas || 0) || null,
        nota_proceso_titulacion: null,
        ...reviewChecks,
      })
      response = await selectTitulacionMecanismo({
        expediente_id: expedienteId,
        mecanismo_codigo: reviewMechanism,
      })
      setCedula(String(reviewItem.NumeroIdentificacion))
      setData(response)
      setActiveArea('calificaciones')
      setReviewItem(null)
      setMessage('Estudiante enviado a egresamiento. Continúe con la calificación del mecanismo seleccionado.')
      await loadAptos()
      await loadProgramacion()
      onOpenProcesoTitulacion?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo dar paso al proceso.')
    } finally {
      setSaving(false)
    }
  }

  async function saveNotes() {
    if (!expediente) return
    await runAction(
      () => saveTitulacionNotas({
        expediente_id: expediente.ExpedienteId,
        promedio_asignaturas: promedioAsignaturas ? Number(promedioAsignaturas) : null,
        nota_proceso_titulacion: notaTitulacion ? Number(notaTitulacion) : null,
        ...checks,
      }),
      'Notas guardadas.',
    )
  }

  async function syncPractices() {
    if (!expediente) return
    await runAction(() => syncTitulacionPracticas(expediente.ExpedienteId), 'Prácticas sincronizadas.')
  }

  async function saveVerification() {
    if (!expediente) return
    await runAction(
      () => saveTitulacionNotas({
        expediente_id: expediente.ExpedienteId,
        promedio_asignaturas: promedioAsignaturas ? Number(promedioAsignaturas) : null,
        nota_proceso_titulacion: notaTitulacion ? Number(notaTitulacion) : null,
        ...checks,
      }),
      'Verificación guardada.',
    )
  }

  async function selectMechanism() {
    if (!expediente) return
    await runAction(
      () => selectTitulacionMecanismo({
        expediente_id: expediente.ExpedienteId,
        mecanismo_codigo: mechanismCode,
      }),
      'Mecanismo seleccionado.',
    )
    await loadProgramacion()
  }

  async function programMechanism() {
    if (!expediente || !programacion.fecha_programada) {
      setError('Ingresa la fecha de programación.')
      return
    }
    const payload = {
      expediente_id: expediente.ExpedienteId,
      fecha_programada: programacion.fecha_programada,
      hora_programada: programacion.hora_programada || null,
      lugar: programacion.lugar || null,
      modalidad: programacion.modalidad || null,
      enlace_virtual: programacion.enlace_virtual || null,
    }
    await runAction(
      () => mechanismCode === 'EXAMEN_COMPLEXIVO'
        ? programTitulacionExamen(payload)
        : programTitulacionDefensa(payload),
      'Programación guardada.',
    )
    await loadProgramacion()
  }

  async function saveTribunal() {
    if (!expediente || !tribunal.nombre_miembro.trim()) {
      setError('Ingresa el nombre del miembro del tribunal.')
      return
    }
    const rolBase = tribunal.rol_tribunal || (mechanismCode === 'EXAMEN_COMPLEXIVO' ? 'RESPONSABLE' : 'JURADO')
    const rolConMateria = tribunal.materia_asignada.trim()
      ? `${rolBase}: ${tribunal.materia_asignada.trim()}`
      : rolBase
    await runAction(
      () => addTitulacionTribunal({
        expediente_id: expediente.ExpedienteId,
        mecanismo_codigo: mechanismCode,
        rol_tribunal: rolConMateria,
        nombre_miembro: tribunal.nombre_miembro,
        cedula_miembro: tribunal.cedula_miembro || null,
        correo_miembro: tribunal.correo_miembro || null,
        orden_firma: tribunal.orden_firma ? Number(tribunal.orden_firma) : null,
      }),
      'Tribunal registrado.',
    )
    setTribunal({ rol_tribunal: mechanismCode === 'EXAMEN_COMPLEXIVO' ? 'RESPONSABLE' : 'JURADO', materia_asignada: '', nombre_miembro: '', cedula_miembro: '', correo_miembro: '', orden_firma: '' })
    await loadProgramacion()
  }

  async function gradeExam() {
    if (!expediente || !examen.nota_examen) {
      setError('Ingresa la nota del examen complexivo.')
      return
    }
    await runAction(
      () => gradeTitulacionExamen({
        expediente_id: expediente.ExpedienteId,
        nota_examen: Number(examen.nota_examen),
        codigo_examen: examen.codigo_examen || null,
        tipo_examen: examen.tipo_examen || null,
        observacion: examen.observacion || null,
      }),
      'Examen complexivo calificado.',
    )
    await loadProgramacion()
  }

  async function saveDefenseTopic() {
    if (!expediente || !defensa.tema_trabajo.trim()) {
      setError('Ingresa el tema del trabajo de defensa.')
      return
    }
    await runAction(
      () => saveTitulacionDefensaTema({
        expediente_id: expediente.ExpedienteId,
        tema_trabajo: defensa.tema_trabajo,
        linea_investigacion: defensa.linea_investigacion || null,
        tutor: defensa.tutor || null,
        lector_oponente: defensa.lector_oponente || null,
      }),
      'Tema de defensa guardado.',
    )
    await loadProgramacion()
  }

  async function gradeDefense() {
    if (!expediente || !defensa.nota_trabajo_escrito || !defensa.nota_defensa_oral) {
      setError('Ingresa las dos notas de defensa.')
      return
    }
    await runAction(
      () => gradeTitulacionDefensa({
        expediente_id: expediente.ExpedienteId,
        nota_trabajo_escrito: Number(defensa.nota_trabajo_escrito),
        nota_defensa_oral: Number(defensa.nota_defensa_oral),
        observacion: defensa.observacion || null,
      }),
      'Defensa de grado calificada.',
    )
    await loadProgramacion()
  }

  async function uploadDocument() {
    if (!expediente || !documentFile) {
      setError('Selecciona un expediente y un archivo.')
      return
    }
    await runAction(
      () => uploadTitulacionDocumento({
        expediente_id: expediente.ExpedienteId,
        tipo_documento_codigo: documentType,
        observacion: documentObservation,
        file: documentFile,
      }),
      'Documento cargado.',
    )
    setDocumentFile(null)
    setDocumentObservation('')
    await loadProgramacion()
  }

  async function generate() {
    if (!expediente) return
    await runAction(() => generateTitulacion(expediente.ExpedienteId), 'Titulación generada.')
  }

  async function generateActa() {
    if (!expediente || !acta.fecha_acta) {
      setError('Ingresa la fecha del acta de grado.')
      return
    }
    await runAction(
      () => generateTitulacionActa({
        expediente_id: expediente.ExpedienteId,
        numero_acta_grado: acta.numero_acta_grado || null,
        fecha_acta: acta.fecha_acta,
        hora_acta: acta.hora_acta || null,
        ciudad: acta.ciudad || null,
        escuela: acta.escuela || null,
        autoridad_academica: acta.autoridad_academica || null,
        docente_evaluador: acta.docente_evaluador || null,
        coordinador_academico: acta.coordinador_academico || null,
        ruta_acta_pdf: acta.ruta_acta_pdf || null,
      }),
      'Acta registrada.',
    )
    await loadProgramacion()
  }

  async function registerSenescyt() {
    const numeroActa = acta.numero_acta_grado || expediente?.NumeroActaGrado || ''
    if (!numeroActa || !senescyt.codigo_registro_senescyt || !senescyt.fecha_registro) {
      setError('Ingresa número de acta, código SENESCYT y fecha de registro.')
      return
    }
    await runAction(
      () => registerTitulacionSenescyt({
        numero_acta_grado: numeroActa,
        codigo_registro_senescyt: senescyt.codigo_registro_senescyt,
        fecha_registro: senescyt.fecha_registro,
        ruta_documento_nube: senescyt.ruta_documento_nube || null,
      }),
      'Título SENESCYT registrado.',
    )
  }

  async function registerIntec() {
    const numeroActa = acta.numero_acta_grado || expediente?.NumeroActaGrado || ''
    if (!numeroActa || !intec.numero_titulo || !intec.fecha_emision) {
      setError('Ingresa número de acta, número de título INTEC y fecha de emisión.')
      return
    }
    await runAction(
      () => registerTitulacionIntec({
        numero_acta_grado: numeroActa,
        numero_titulo: intec.numero_titulo,
        fecha_emision: intec.fecha_emision,
        codigo_verificacion: intec.codigo_verificacion || null,
        ruta_documento_nube: intec.ruta_documento_nube || null,
      }),
      'Título INTEC registrado.',
    )
  }

  const mallaGrades = mallaDetail?.data?.items || []
  const showHomologationGrades = mallaGrades.some((grade) => gradeType(grade) === 'H')
  const mallaGradesColSpan = 7 + (showHomologationGrades ? 2 : 0)
  const mechanismName = mechanismCode === 'DEFENSA_GRADO' ? 'Defensa de grado' : 'Examen complexivo'
  const currentCalendarItem: TitulacionProgramacionItem | null = expediente ? {
    ExpedienteId: expediente.ExpedienteId,
    NumeroIdentificacion: String(expediente.NumeroIdentificacion || academic?.numero_identificacion || cedula || ''),
    ApellidosNombres: String(expediente.ApellidosNombres || academic?.apellidos_nombres || ''),
    NombreCarrera: String(expediente.NombreCarrera || academic?.nombre_carrera || ''),
    EstadoExpediente: String(expediente.EstadoExpediente || ''),
    MecanismoCodigo: mechanismCode,
    MecanismoNombre: mechanismName,
    FechaProgramada: programacion.fecha_programada,
    HoraProgramada: programacion.hora_programada,
    Lugar: programacion.lugar,
    Modalidad: programacion.modalidad,
    EnlaceVirtual: programacion.enlace_virtual,
    TemaTrabajo: defensa.tema_trabajo,
    CodigoExamen: examen.codigo_examen,
    TipoExamen: examen.tipo_examen,
    Tutor: defensa.tutor,
    LectorOponente: defensa.lector_oponente,
    Responsables: (mechanism?.tribunal || []).map((member) => `${String(member.RolTribunal || 'MIEMBRO')}: ${String(member.NombreMiembro || '')}`).join('; '),
  } : null
  const currentTeamsLink = currentCalendarItem ? teamsCalendarLink(currentCalendarItem) : '#'
  const topicSuggestions = defenseTopicSuggestions(expediente?.NombreCarrera || academic?.nombre_carrera)
  const responsablesRegistrados = mechanism?.tribunal || []
  const responsablesPanel = (
    <article className="student-card student-card--wide titulacion-responsables-panel">
      <div className="card-head">
        <div>
          <span>Registro de responsables</span>
          <h3>{data ? (mechanismCode === 'EXAMEN_COMPLEXIVO' ? 'Supervisores del examen complexivo' : 'Tribunal de defensa de grado') : 'Tribunal y supervisores'}</h3>
        </div>
        <span>{data ? `${responsablesRegistrados.length} registrado(s)` : 'Seleccione un proceso'}</span>
      </div>

      {data ? (
        <div className="titulacion-responsables-layout">
          <div className="titulacion-responsables-form">
            <div className="section-kicker">Asignar responsable</div>
            <div className="titulacion-mechanism-grid">
              <label>
                <span>Rol</span>
                <select value={tribunal.rol_tribunal} onChange={(event) => setTribunal((current) => ({ ...current, rol_tribunal: event.target.value }))}>
                  {mechanismCode === 'EXAMEN_COMPLEXIVO' ? (
                    <>
                      <option value="RESPONSABLE">Responsable</option>
                      <option value="JURADO">Jurado</option>
                      <option value="COORDINADOR">Coordinador</option>
                      <option value="EVALUADOR">Evaluador</option>
                    </>
                  ) : (
                    <>
                      <option value="PRESIDENTE">Presidente</option>
                      <option value="JURADO">Jurado</option>
                      <option value="TUTOR">Tutor</option>
                      <option value="LECTOR_OPONENTE">Lector / oponente</option>
                      <option value="SECRETARIO">Secretario</option>
                    </>
                  )}
                </select>
              </label>
              <label>
                <span>Materia / área a cargo</span>
                <input value={tribunal.materia_asignada} onChange={(event) => setTribunal((current) => ({ ...current, materia_asignada: event.target.value }))} placeholder="Ej. Redes, programación, investigación" />
              </label>
              <label>
                <span>Nombre</span>
                <input value={tribunal.nombre_miembro} onChange={(event) => setTribunal((current) => ({ ...current, nombre_miembro: event.target.value }))} />
              </label>
              <label>
                <span>Cédula</span>
                <input value={tribunal.cedula_miembro} onChange={(event) => setTribunal((current) => ({ ...current, cedula_miembro: event.target.value }))} />
              </label>
              <label>
                <span>Correo</span>
                <input value={tribunal.correo_miembro} onChange={(event) => setTribunal((current) => ({ ...current, correo_miembro: event.target.value }))} />
              </label>
              <label>
                <span>Orden firma</span>
                <input type="number" min="1" value={tribunal.orden_firma} onChange={(event) => setTribunal((current) => ({ ...current, orden_firma: event.target.value }))} />
              </label>
              <button type="button" className="secondary-action" onClick={() => void saveTribunal()} disabled={!expediente || saving || !canEdit}>
                Registrar responsable
              </button>
            </div>
          </div>
          <div className="titulacion-responsables-list">
            <div className="section-kicker">Integrantes registrados</div>
            {responsablesRegistrados.length ? (
              <div className="matricula-table-wrap titulacion-responsables-table">
                <table>
                  <thead>
                    <tr>
                      <th>Rol / área</th>
                      <th>Nombre</th>
                      <th>Cédula</th>
                      <th>Correo</th>
                      <th>Orden</th>
                    </tr>
                  </thead>
                  <tbody>
                    {responsablesRegistrados.map((member) => (
                      <tr key={String(member.TribunalTitulacionId)}>
                        <td>{textValue(member.RolTribunal)}</td>
                        <td>{textValue(member.NombreMiembro)}</td>
                        <td>{textValue(member.CedulaMiembro)}</td>
                        <td>{textValue(member.CorreoMiembro)}</td>
                        <td>{textValue(member.OrdenFirma)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="titulacion-empty-state">
                {mechanismCode === 'EXAMEN_COMPLEXIVO'
                  ? 'Sin responsables asignados para supervisar el examen complexivo.'
                  : 'Sin integrantes asignados al tribunal de defensa.'}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="titulacion-empty-state titulacion-empty-state--large">
          Abra un estudiante desde la tabla de complexivo y defensa para asignar tribunal o responsables.
        </div>
      )}
    </article>
  )

  return (
    <main className="student-page titulacion-page">
      <section className="student-hero titulacion-hero">
        <div>
          <span>Titulación</span>
          <h1>{mainSection === 'responsables' ? 'Registro de responsables' : mainSection === 'proceso' ? 'Proceso de titulación' : 'Verificación y modalidad'}</h1>
          <p>
            {mainSection === 'responsables'
              ? `${displayName} · Asignación individual de tribunal de defensa y responsables de examen complexivo.`
              : mainSection === 'proceso'
              ? `${displayName} · Programación, responsables, tribunal, enlaces y calificaciones de complexivo o defensa de grado.`
              : `${displayName} · Primero valide malla, inglés, prácticas preprofesionales y vinculación con la sociedad.`}
          </p>
        </div>
      </section>

      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      <div hidden={mainSection !== 'verificacion'}>
      <section className="student-grid student-grid--content titulacion-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <span>Consulta general</span>
              <h3>Buscar estudiante por nombre o cédula</h3>
            </div>
          </div>
          <div className="matricula-acad-form titulacion-search-form">
            <label>
              <span>Nombre o cédula</span>
              <input value={cedula} onChange={(event) => setCedula(event.target.value)} placeholder="Nombre, apellido o número de cédula" />
            </label>
            <button type="button" className="secondary-action titulacion-search-button" onClick={() => void search()} disabled={loading}>
              Buscar
            </button>
            <button type="button" className="secondary-action titulacion-refresh-button" onClick={() => void loadAptos()} disabled={aptosLoading}>
              {aptosLoading ? 'Actualizando' : 'Actualizar datos'}
            </button>
          </div>
        </article>
      </section>

      <article className="student-card student-card--wide titulacion-progress-card" hidden={!data}>
        <div className="card-head">
          <div>
            <span>Avance de requisitos</span>
            <h3>Estado para iniciar titulación</h3>
          </div>
          <span>{data ? (requisitosInicialesCumplidos ? 'Completo' : 'Pendiente') : 'Sin consulta'}</span>
        </div>
        <div className="matricula-table-wrap titulacion-progress-table">
          <table>
            <thead>
              <tr>
                <th>Requisito</th>
                <th>Debe cumplir</th>
                <th>Avance</th>
                <th>Porcentaje</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {progressRows.map((row) => (
                <tr key={row.area}>
                  <td>{row.area}</td>
                  <td>{row.requerido}</td>
                  <td>{row.actual}</td>
                  <td>
                    <div className="titulacion-progress-meter">
                      <span style={{ width: `${row.percent}%` }} />
                    </div>
                    <strong>{row.percent}%</strong>
                  </td>
                  <td>
                    <span className={row.ok ? 'status-pill is-ok' : 'status-pill is-warning'}>
                      {row.ok ? 'Cumple' : 'Pendiente'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <section className="student-grid student-grid--content titulacion-grid">
        <article className="student-card student-card--wide titulacion-active-students-card">
          <div className="titulacion-pagination titulacion-pagination--top">
            <span>
              {filteredAptosItems.length === 0
                ? '0 estudiantes'
                : `${((currentAptosPage - 1) * aptosPageSize) + 1}-${Math.min(currentAptosPage * aptosPageSize, filteredAptosItems.length)} de ${filteredAptosItems.length} estudiantes`}
            </span>
            <div>
              <button type="button" className="secondary-action" onClick={() => setAptosPage(1)} disabled={currentAptosPage === 1}>
                Primero
              </button>
              <button type="button" className="secondary-action" onClick={() => setAptosPage((page) => Math.max(1, page - 1))} disabled={currentAptosPage === 1}>
                Anterior
              </button>
              <strong>Página {currentAptosPage} / {aptosTotalPages}</strong>
              <button type="button" className="secondary-action" onClick={() => setAptosPage((page) => Math.min(aptosTotalPages, page + 1))} disabled={currentAptosPage === aptosTotalPages}>
                Siguiente
              </button>
              <button type="button" className="secondary-action" onClick={() => setAptosPage(aptosTotalPages)} disabled={currentAptosPage === aptosTotalPages}>
                Último
              </button>
            </div>
          </div>
          <div className="matricula-table-wrap titulacion-aptos-table">
            <table>
              <colgroup>
                <col className="titulacion-col-name" />
                <col className="titulacion-col-id" />
                <col className="titulacion-col-career" />
                <col className="titulacion-col-progress" />
                <col className="titulacion-col-english" />
                <col className="titulacion-col-hours" />
                <col className="titulacion-col-hours" />
                <col className="titulacion-col-action" />
              </colgroup>
              <thead>
                <tr>
                  <th aria-sort={aptosSort.key === 'name' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('name')}>
                      <span>Nombre estudiante</span>
                      <small>{sortLabel('name')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'id' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('id')}>
                      <span>Número de cédula</span>
                      <small>{sortLabel('id')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'career' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('career')}>
                      <span>Carrera</span>
                      <small>{sortLabel('career')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'careerProgress' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('careerProgress')}>
                      <span>Avance carrera</span>
                      <small>{sortLabel('careerProgress')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'english' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('english')}>
                      <span>Inglés A2+ - INTERMEDIATE</span>
                      <small>{sortLabel('english')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'practices' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('practices')}>
                      <span>Prácticas profesionales</span>
                      <small>{sortLabel('practices')}</small>
                    </button>
                  </th>
                  <th aria-sort={aptosSort.key === 'vinculacion' ? (aptosSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" className="titulacion-sort-button" onClick={() => changeAptosSort('vinculacion')}>
                      <span>Vinculación con la sociedad</span>
                      <small>{sortLabel('vinculacion')}</small>
                    </button>
                  </th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {paginatedAptosItems.map((item) => {
                  const itemMallaPercent = percentValue((Number(item.MateriasAprobadas || 0) / MATERIAS_REQUERIDAS_TITULACION) * 100)
                  const itemInglesPercent = item.CumpleInglesA2Avanzado ? 100 : 0
                  const itemPracticasPercent = percentValue((Number(item.TotalHorasPracticasPreprofesionales || 0) / HORAS_REQUERIDAS_PRACTICAS) * 100)
                  const itemVinculacionPercent = percentValue((Number(item.TotalHorasVinculacion || 0) / HORAS_REQUERIDAS_VINCULACION) * 100)
                  return (
                    <tr key={`${item.NumeroIdentificacion}-${item.CodAnioBasica}-${item.CodigoPeriodo}`}>
                      <td>{textValue(item.ApellidosNombres)}</td>
                      <td>{textValue(item.NumeroIdentificacion)}</td>
                      <td>{textValue(item.NombreCarrera)}</td>
                      <td>
                        <div className="titulacion-mini-progress">
                          <span style={{ width: `${itemMallaPercent}%` }} />
                        </div>
                        <strong>{numberText(item.MateriasAprobadas)} / {MATERIAS_REQUERIDAS_TITULACION} materias · {itemMallaPercent}%</strong>
                      </td>
                      <td>
                        <div className="titulacion-mini-progress">
                          <span style={{ width: `${itemInglesPercent}%` }} />
                        </div>
                        <strong>{item.CumpleInglesA2Avanzado ? 'A2+ - INTERMEDIATE validado' : 'Pendiente'} · {itemInglesPercent}%</strong>
                      </td>
                      <td>
                        <div className="titulacion-mini-progress">
                          <span style={{ width: `${itemPracticasPercent}%` }} />
                        </div>
                        <strong>{numberText(item.TotalHorasPracticasPreprofesionales)} / {HORAS_REQUERIDAS_PRACTICAS} horas · {itemPracticasPercent}%</strong>
                      </td>
                      <td>
                        <div className="titulacion-mini-progress">
                          <span style={{ width: `${itemVinculacionPercent}%` }} />
                        </div>
                        <strong>{numberText(item.TotalHorasVinculacion)} / {HORAS_REQUERIDAS_VINCULACION} horas · {itemVinculacionPercent}%</strong>
                      </td>
                      <td>
                        <button type="button" className="secondary-action titulacion-review-button" onClick={() => {
                          setReviewItem(item)
                          setReviewMechanism('EXAMEN_COMPLEXIVO')
                        }}>
                          Ver
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {!filteredAptosItems.length ? (
                  <tr>
                    <td colSpan={8}>{aptosLoading ? 'Cargando estudiantes activos...' : 'Sin estudiantes activos para mostrar con el filtro actual.'}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="titulacion-pagination">
            <span>
              {filteredAptosItems.length === 0
                ? '0 estudiantes'
                : `${((currentAptosPage - 1) * aptosPageSize) + 1}-${Math.min(currentAptosPage * aptosPageSize, filteredAptosItems.length)} de ${filteredAptosItems.length} estudiantes`}
            </span>
            <div>
              <button type="button" className="secondary-action" onClick={() => setAptosPage(1)} disabled={currentAptosPage === 1}>
                Primero
              </button>
              <button type="button" className="secondary-action" onClick={() => setAptosPage((page) => Math.max(1, page - 1))} disabled={currentAptosPage === 1}>
                Anterior
              </button>
              <strong>Página {currentAptosPage} / {aptosTotalPages}</strong>
              <button type="button" className="secondary-action" onClick={() => setAptosPage((page) => Math.min(aptosTotalPages, page + 1))} disabled={currentAptosPage === aptosTotalPages}>
                Siguiente
              </button>
              <button type="button" className="secondary-action" onClick={() => setAptosPage(aptosTotalPages)} disabled={currentAptosPage === aptosTotalPages}>
                Último
              </button>
            </div>
          </div>
        </article>
      </section>
      </div>

      <div hidden={mainSection !== 'proceso' && mainSection !== 'responsables'}>
        <section className="student-grid student-grid--content titulacion-grid">
          <article className="student-card student-card--wide titulacion-programacion-card">
            <div className="card-head">
              <div>
                <span>{mainSection === 'responsables' ? 'Seleccionar proceso' : 'Programación'}</span>
                <h3>{mainSection === 'responsables' ? 'Estudiantes en proceso para asignar responsables' : 'Complexivo y defensa de grado'}</h3>
              </div>
              <div className="titulacion-programacion-kpis">
                <span><strong>{procesoTotal}</strong> procesos</span>
                <span><strong>{procesoComplexivoTotal}</strong> complexivo</span>
                <span><strong>{procesoDefensaTotal}</strong> defensa</span>
              </div>
            </div>
            {mainSection === 'responsables' ? (
              <div className="titulacion-process-toggle" role="group" aria-label="Tipo de proceso para responsables">
                <button
                  type="button"
                  className={programacionFilter === 'EXAMEN_COMPLEXIVO' ? 'is-active' : ''}
                  onClick={() => setProgramacionFilter('EXAMEN_COMPLEXIVO')}
                >
                  Examen complexivo
                </button>
                <button
                  type="button"
                  className={programacionFilter === 'DEFENSA_GRADO' ? 'is-active' : ''}
                  onClick={() => setProgramacionFilter('DEFENSA_GRADO')}
                >
                  Defensa de grado
                </button>
              </div>
            ) : null}
            <div className="titulacion-programacion-filters">
              <label>
                <span>Buscar</span>
                <input
                  value={programacionSearch}
                  onChange={(event) => setProgramacionSearch(event.target.value)}
                  placeholder="Estudiante, cédula, carrera o acta"
                />
              </label>
              <label>
                <span>Proceso</span>
                <select value={programacionFilter} onChange={(event) => setProgramacionFilter(event.target.value as typeof programacionFilter)}>
                  {mainSection !== 'responsables' ? <option value="TODOS">Todos</option> : null}
                  <option value="EXAMEN_COMPLEXIVO">Examen complexivo</option>
                  <option value="DEFENSA_GRADO">Defensa de grado</option>
                </select>
              </label>
              <button type="button" className="secondary-action" onClick={() => void loadProgramacion()} disabled={programacionLoading}>
                {programacionLoading ? 'Actualizando' : 'Actualizar'}
              </button>
            </div>
            <div className="matricula-table-wrap titulacion-programacion-table">
              <table>
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cédula</th>
                    <th>Carrera</th>
                    <th>Proceso</th>
                    <th>Tema / código</th>
                    <th>Fecha</th>
                    <th>Responsables</th>
                    <th>Enlace</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {programacionItems.map((item) => (
                    <tr key={`${item.ExpedienteId}-${item.MecanismoCodigo || 'proceso'}`}>
                      <td>{textValue(item.ApellidosNombres)}</td>
                      <td>{textValue(item.NumeroIdentificacion)}</td>
                      <td>{textValue(item.NombreCarrera)}</td>
                      <td>{textValue(item.MecanismoNombre)}</td>
                      <td>{textValue(item.TemaTrabajo || item.CodigoExamen || item.TipoExamen)}</td>
                      <td>{item.FechaProgramada ? `${String(item.FechaProgramada).slice(0, 10)} ${String(item.HoraProgramada || '').slice(0, 5)}` : 'Pendiente'}</td>
                      <td>{textValue(item.Responsables || item.Tutor || item.LectorOponente)}</td>
                      <td>
                        <a className="secondary-action" href={teamsCalendarLink(item)} target="_blank" rel="noreferrer">
                          Teams
                        </a>
                      </td>
                      <td>
                        <button type="button" className="primary-action" onClick={() => void openProgramacionItem(item)}>
                          Abrir
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!programacionItems.length ? (
                    <tr>
                      <td colSpan={9}>
                        {programacionLoading
                          ? 'Cargando procesos...'
                          : mainSection === 'responsables'
                            ? `No existen estudiantes con dar paso en ${programacionFilter === 'DEFENSA_GRADO' ? 'defensa de grado' : 'examen complexivo'}.`
                            : 'No existen estudiantes en complexivo o defensa con los filtros actuales.'}
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </article>
          {mainSection === 'responsables' ? responsablesPanel : null}
        </section>
      </div>

      {mainSection === 'proceso' && data ? (
        <>
          <section className="student-grid student-grid--stats titulacion-stats">
            <article className="student-stat-card">
              <span>Malla</span>
              <strong>{academic?.malla_finalizada ? 'Finalizada' : 'Pendiente'}</strong>
              <small>{numberText(academic?.materias_aprobadas)} / {numberText(academic?.total_materias)} materias</small>
            </article>
            <article className="student-stat-card">
              <span>Promedio académico</span>
              <strong>{numberText(academic?.promedio_asignaturas || expediente?.PromedioAsignaturas)}</strong>
              <small>{numberText(academic?.porcentaje_malla)}% de avance</small>
            </article>
            <article className="student-stat-card">
              <span>Prácticas</span>
              <strong>{boolValue(expediente?.PracticasPreprofesionalesCumple) ? 'Cumple' : 'Pendiente'}</strong>
              <small>{numberText(expediente?.TotalHorasPracticasPreprofesionales)} horas</small>
            </article>
            <article className="student-stat-card">
              <span>Vinculación con la sociedad</span>
              <strong>{boolValue(expediente?.VinculacionCumple) ? 'Cumple' : 'Pendiente'}</strong>
              <small>{numberText(expediente?.TotalHorasVinculacion)} horas</small>
            </article>
          </section>

          <section className="student-grid student-grid--content titulacion-grid">
            <article className="student-card" hidden={activeArea !== 'verificacion'}>
              <div className="card-head">
                <div>
                  <span>Primera página</span>
                  <h3>Verificación para iniciar titulación</h3>
                </div>
                <span>{requisitosInicialesCumplidos ? 'Puede continuar' : 'No puede continuar'}</span>
              </div>
              <div className="titulacion-prereq-list">
                {prerequisiteRows.map((item) => (
                  <div key={item.label} className={item.ok ? 'is-ok' : 'is-warning'}>
                    <strong>{item.ok ? 'Cumple' : 'Pendiente'}</strong>
                    <span>{item.label}</span>
                    <small>{item.detail}</small>
                    {item.key ? (() => {
                      const checkKey = item.key
                      return (
                        <label>
                          <input
                            type="checkbox"
                            checked={checks[checkKey]}
                            onChange={(event) => setChecks((current) => ({ ...current, [checkKey]: event.target.checked }))}
                            disabled={!canEdit || !expediente}
                          />
                          Validado
                        </label>
                      )
                    })() : null}
                  </div>
                ))}
              </div>
              <div className="titulacion-action-row">
                <button type="button" className="secondary-action" onClick={() => void syncPractices()} disabled={!expediente || saving}>
                  Sincronizar prácticas y vinculación con la sociedad
                </button>
                <button type="button" className="primary-action" onClick={() => void saveVerification()} disabled={!expediente || saving || !canEdit}>
                  Guardar verificación
                </button>
              </div>
              <div className="titulacion-checklist">
                {[
                  ['Cédula validada', 'cedula_validada'],
                  ['Título bachiller', 'titulo_bachiller_cumple'],
                  ['No adeuda financiero', 'no_adeuda_financiero'],
                  ['Apto sustentación', 'apto_sustentacion'],
                  ['Rúbrica titulación', 'rubrica_titulacion_cumple'],
                ].map(([label, key]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={checks[key as keyof typeof checks]}
                      onChange={(event) => setChecks((current) => ({ ...current, [key]: event.target.checked }))}
                      disabled={!canEdit || !expediente}
                    />
                    <span>{label}</span>
                  </label>
                ))}
                <div className="titulacion-fixed-check">
                  <strong>{academic?.malla_finalizada ? 'OK' : 'Pendiente'}</strong>
                  <span>Malla académica finalizada</span>
                </div>
                <div className="titulacion-fixed-check">
                  <strong>{boolValue(expediente?.PracticasPreprofesionalesCumple) && boolValue(expediente?.VinculacionCumple) ? 'OK' : 'Pendiente'}</strong>
                  <span>Prácticas y vinculación con la sociedad</span>
                </div>
              </div>
            </article>

            <article className="student-card" hidden={activeArea !== 'calificaciones'}>
              <div className="card-head">
                <div>
                  <span>Notas</span>
                  <h3>Calificación general</h3>
                </div>
              </div>
              <div className="matricula-acad-form matricula-acad-form--compact titulacion-notes-form">
                <label>
                  <span>Promedio asignaturas</span>
                  <input type="number" min="0" max="10" step="0.01" value={promedioAsignaturas} onChange={(event) => setPromedioAsignaturas(event.target.value)} />
                </label>
                <label>
                  <span>Nota proceso titulación</span>
                  <input type="number" min="0" max="10" step="0.01" value={notaTitulacion} onChange={(event) => setNotaTitulacion(event.target.value)} />
                </label>
                <div className="titulacion-final-grade">
                  <span>Nota final grado</span>
                  <strong>{numberText(expediente?.NotaFinalGrado)}</strong>
                </div>
                <button type="button" className="primary-action" onClick={() => void saveNotes()} disabled={!expediente || saving || !canEdit}>
                  Guardar notas
                </button>
              </div>
            </article>

            <article className="student-card student-card--wide titulacion-mechanism-card" hidden={activeArea !== 'calificaciones'}>
              <div className="card-head">
                <div>
                  <span>Segundo paso</span>
                  <h3>Proceso de titulación</h3>
                </div>
                <span>{String(mechanismValidation?.MensajeMecanismo || 'Pendiente de selección')}</span>
              </div>

              <div className="titulacion-process-summary">
                <div>
                  <span>Opción seleccionada</span>
                  <strong>{mechanismName}</strong>
                </div>
                <div>
                  <span>Estado</span>
                  <strong>{mecanismoAprobado ? 'Aprobado' : textValue(expediente?.EstadoExpediente)}</strong>
                </div>
                <div>
                  <span>Fecha asignada</span>
                  <strong>{programacion.fecha_programada ? `${programacion.fecha_programada} ${programacion.hora_programada || ''}` : 'Pendiente'}</strong>
                </div>
                <div>
                  <span>Enlace para el proceso</span>
                  <a className="secondary-action" href={currentTeamsLink} target="_blank" rel="noreferrer" aria-disabled={!expediente}>
                    Generar Teams
                  </a>
                </div>
              </div>

              <div className="titulacion-mechanism-grid">
                <label>
                  <span>Mecanismo de titulación</span>
                  <select value={mechanismCode} onChange={(event) => setMechanismCode(event.target.value as TitulacionMecanismoCodigo)} disabled={!canEdit || !expediente}>
                    <option value="EXAMEN_COMPLEXIVO">Examen complexivo</option>
                    <option value="DEFENSA_GRADO">Defensa de grado</option>
                  </select>
                </label>
                <button type="button" className="secondary-action" onClick={() => void selectMechanism()} disabled={!expediente || saving || !canEdit}>
                  Seleccionar
                </button>
                <label>
                  <span>Fecha</span>
                  <input type="date" value={programacion.fecha_programada} onChange={(event) => setProgramacion((current) => ({ ...current, fecha_programada: event.target.value }))} />
                </label>
                <label>
                  <span>Hora</span>
                  <input type="time" value={programacion.hora_programada} onChange={(event) => setProgramacion((current) => ({ ...current, hora_programada: event.target.value }))} />
                </label>
                <label>
                  <span>Modalidad</span>
                  <select value={programacion.modalidad} onChange={(event) => setProgramacion((current) => ({ ...current, modalidad: event.target.value }))}>
                    <option value="PRESENCIAL">Presencial</option>
                    <option value="VIRTUAL">Virtual</option>
                    <option value="HIBRIDA">Híbrida</option>
                  </select>
                </label>
                <label>
                  <span>Lugar</span>
                  <input value={programacion.lugar} onChange={(event) => setProgramacion((current) => ({ ...current, lugar: event.target.value }))} placeholder="Aula, auditorio o sede" />
                </label>
                <label className="titulacion-span-2">
                  <span>Enlace virtual</span>
                  <input value={programacion.enlace_virtual} onChange={(event) => setProgramacion((current) => ({ ...current, enlace_virtual: event.target.value }))} placeholder="Opcional" />
                </label>
                <button type="button" className="primary-action" onClick={() => void programMechanism()} disabled={!expediente || saving || !canEdit}>
                  Programar
                </button>
              </div>

              <div className="titulacion-subpanel titulacion-process-setup-panel">
                <div className="card-head">
                  <div>
                    <span>Nuevo apartado</span>
                    <h3>{mechanismCode === 'DEFENSA_GRADO' ? 'Tema de defensa de grado' : 'Configuración del examen complexivo'}</h3>
                  </div>
                </div>
                <div className="titulacion-mechanism-grid">
                  {mechanismCode === 'DEFENSA_GRADO' ? (
                    <>
                      <div className="titulacion-topic-suggestions titulacion-span-2">
                        <span>Temas sugeridos</span>
                        <div>
                          {topicSuggestions.map((topic) => (
                            <button
                              key={topic}
                              type="button"
                              className="secondary-action"
                              onClick={() => setDefensa((current) => ({ ...current, tema_trabajo: topic }))}
                            >
                              {topic}
                            </button>
                          ))}
                        </div>
                      </div>
                      <label className="titulacion-span-2">
                        <span>Tema de defensa</span>
                        <input value={defensa.tema_trabajo} onChange={(event) => setDefensa((current) => ({ ...current, tema_trabajo: event.target.value }))} placeholder="Tema del trabajo desarrollado" />
                      </label>
                      <label>
                        <span>Línea de investigación</span>
                        <input value={defensa.linea_investigacion} onChange={(event) => setDefensa((current) => ({ ...current, linea_investigacion: event.target.value }))} />
                      </label>
                      <label>
                        <span>Tutor</span>
                        <input value={defensa.tutor} onChange={(event) => setDefensa((current) => ({ ...current, tutor: event.target.value }))} />
                      </label>
                      <label>
                        <span>Lector / oponente</span>
                        <input value={defensa.lector_oponente} onChange={(event) => setDefensa((current) => ({ ...current, lector_oponente: event.target.value }))} />
                      </label>
                      <button type="button" className="secondary-action" onClick={() => void saveDefenseTopic()} disabled={!expediente || saving || !canEdit}>
                        Guardar tema
                      </button>
                    </>
                  ) : (
                    <>
                      <label>
                        <span>Código examen</span>
                        <input value={examen.codigo_examen} onChange={(event) => setExamen((current) => ({ ...current, codigo_examen: event.target.value }))} placeholder="Código o banco de examen" />
                      </label>
                      <label>
                        <span>Tipo / materia central</span>
                        <input value={examen.tipo_examen} onChange={(event) => setExamen((current) => ({ ...current, tipo_examen: event.target.value }))} placeholder="Materia, área o tipo de examen" />
                      </label>
                      <label className="titulacion-span-2">
                        <span>Indicaciones del examen</span>
                        <input value={examen.observacion} onChange={(event) => setExamen((current) => ({ ...current, observacion: event.target.value }))} placeholder="Observación para el jurado o responsable" />
                      </label>
                      <div className="titulacion-info-note titulacion-span-2">
                        Esta configuración se conserva en pantalla y se registra formalmente al guardar la nota del examen complexivo.
                      </div>
                    </>
                  )}
                </div>
              </div>

              {mechanismCode === 'EXAMEN_COMPLEXIVO' ? (
                <div className="titulacion-subpanel">
                  <div className="card-head">
                    <div>
                      <span>Examen complexivo</span>
                      <h3>Calificación</h3>
                    </div>
                  </div>
                  <div className="titulacion-mechanism-grid">
                    <label>
                      <span>Nota examen</span>
                      <input type="number" min="0" max="10" step="0.01" value={examen.nota_examen} onChange={(event) => setExamen((current) => ({ ...current, nota_examen: event.target.value }))} />
                    </label>
                    <div className="titulacion-final-grade">
                      <span>Código / tipo</span>
                      <strong>{textValue([examen.codigo_examen, examen.tipo_examen].filter(Boolean).join(' · '))}</strong>
                    </div>
                    <button type="button" className="primary-action" onClick={() => void gradeExam()} disabled={!expediente || saving || !canEdit}>
                      Registrar nota
                    </button>
                  </div>
                </div>
              ) : (
                <div className="titulacion-subpanel">
                  <div className="card-head">
                    <div>
                      <span>Defensa de grado</span>
                      <h3>Tema y calificación</h3>
                    </div>
                  </div>
                  <div className="titulacion-mechanism-grid">
                    <div className="titulacion-final-grade titulacion-span-2">
                      <span>Tema registrado</span>
                      <strong>{textValue(defensa.tema_trabajo)}</strong>
                    </div>
                    <label>
                      <span>Nota documento desarrollado</span>
                      <input type="number" min="0" max="10" step="0.01" value={defensa.nota_trabajo_escrito} onChange={(event) => setDefensa((current) => ({ ...current, nota_trabajo_escrito: event.target.value }))} />
                    </label>
                    <label>
                      <span>Nota defensa oral</span>
                      <input type="number" min="0" max="10" step="0.01" value={defensa.nota_defensa_oral} onChange={(event) => setDefensa((current) => ({ ...current, nota_defensa_oral: event.target.value }))} />
                    </label>
                    <div className="titulacion-final-grade">
                      <span>Nota final defensa</span>
                      <strong>
                        {defensa.nota_trabajo_escrito && defensa.nota_defensa_oral
                          ? numberText((Number(defensa.nota_trabajo_escrito) + Number(defensa.nota_defensa_oral)) / 2)
                          : 'Pendiente'}
                      </strong>
                    </div>
                    <label className="titulacion-span-2">
                      <span>Observación</span>
                      <input value={defensa.observacion} onChange={(event) => setDefensa((current) => ({ ...current, observacion: event.target.value }))} />
                    </label>
                    <button type="button" className="primary-action" onClick={() => void gradeDefense()} disabled={!expediente || saving || !canEdit}>
                      Registrar calificación
                    </button>
                  </div>
                </div>
              )}

              <div className="titulacion-subpanel">
                <div className="card-head">
                  <div>
                    <span>Documento del proceso</span>
                    <h3>{mechanismCode === 'DEFENSA_GRADO' ? 'Trabajo desarrollado para defensa' : 'Evidencia del examen complexivo'}</h3>
                  </div>
                </div>
                <div className="titulacion-mechanism-grid">
                  <label>
                    <span>Tipo documento</span>
                    <select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                      {mechanismCode === 'DEFENSA_GRADO' ? (
                        <>
                          <option value="TRABAJO_FINAL_DEFENSA">Trabajo final defensa</option>
                          <option value="INFORME_TUTOR_DEFENSA">Informe tutor defensa</option>
                          <option value="PRESENTACION_DEFENSA">Presentación defensa</option>
                          <option value="ACTA_DEFENSA_GRADO">Acta defensa de grado</option>
                        </>
                      ) : (
                        <>
                          <option value="EVIDENCIA_EXAMEN_COMPLEXIVO">Evidencia examen complexivo</option>
                          <option value="ACTA_EXAMEN_COMPLEXIVO">Acta examen complexivo</option>
                        </>
                      )}
                    </select>
                  </label>
                  <label className="titulacion-span-2">
                    <span>Archivo</span>
                    <input type="file" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} />
                  </label>
                  <label className="titulacion-span-2">
                    <span>Observación</span>
                    <input value={documentObservation} onChange={(event) => setDocumentObservation(event.target.value)} placeholder="Opcional" />
                  </label>
                  <button type="button" className="secondary-action" onClick={() => void uploadDocument()} disabled={!expediente || !documentFile || saving || !canEdit}>
                    Cargar documento
                  </button>
                </div>
              </div>

              <div className="titulacion-subpanel titulacion-acta-inline">
                <div className="card-head">
                  <div>
                    <span>Acta correspondiente</span>
                    <h3>Generar acta del proceso</h3>
                  </div>
                  <span>{textValue(expediente?.NumeroActaGrado || acta.numero_acta_grado)}</span>
                </div>
                <div className="titulacion-mechanism-grid">
                  <label className="titulacion-span-2">
                    <span>Número de acta / grado</span>
                    <input value={acta.numero_acta_grado} onChange={(event) => setActa((current) => ({ ...current, numero_acta_grado: event.target.value }))} placeholder="INTEC-VGA-EBSG-Q-A-20251204-01" />
                  </label>
                  <label>
                    <span>Fecha acta</span>
                    <input type="date" value={acta.fecha_acta} onChange={(event) => setActa((current) => ({ ...current, fecha_acta: event.target.value }))} />
                  </label>
                  <label>
                    <span>Hora acta</span>
                    <input type="time" value={acta.hora_acta} onChange={(event) => setActa((current) => ({ ...current, hora_acta: event.target.value }))} />
                  </label>
                  <label>
                    <span>Ciudad</span>
                    <input value={acta.ciudad} onChange={(event) => setActa((current) => ({ ...current, ciudad: event.target.value }))} />
                  </label>
                  <label>
                    <span>Escuela</span>
                    <input value={acta.escuela} onChange={(event) => setActa((current) => ({ ...current, escuela: event.target.value }))} />
                  </label>
                  <label>
                    <span>Autoridad académica</span>
                    <input value={acta.autoridad_academica} onChange={(event) => setActa((current) => ({ ...current, autoridad_academica: event.target.value }))} />
                  </label>
                  <label>
                    <span>Docente evaluador</span>
                    <input value={acta.docente_evaluador} onChange={(event) => setActa((current) => ({ ...current, docente_evaluador: event.target.value }))} />
                  </label>
                  <label>
                    <span>Coordinador académico</span>
                    <input value={acta.coordinador_academico} onChange={(event) => setActa((current) => ({ ...current, coordinador_academico: event.target.value }))} />
                  </label>
                  <label className="titulacion-span-2">
                    <span>Ruta PDF acta</span>
                    <input value={acta.ruta_acta_pdf} onChange={(event) => setActa((current) => ({ ...current, ruta_acta_pdf: event.target.value }))} placeholder="Ruta local o nube" />
                  </label>
                  <button type="button" className="primary-action" onClick={() => void generateActa()} disabled={!expediente || saving || !canEdit}>
                    Generar acta
                  </button>
                </div>
              </div>
            </article>

            <article className="student-card student-card--wide" hidden={activeArea !== 'documentos'}>
              <div className="card-head">
                <div>
                  <span>Documentos</span>
                  <h3>Carga y consulta documental</h3>
                </div>
              </div>
              <div className="matricula-acad-form titulacion-doc-form">
                <label>
                  <span>Tipo</span>
                  <select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                    {DOCUMENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
                <label>
                  <span>Archivo</span>
                  <input type="file" onChange={(event) => setDocumentFile(event.target.files?.[0] || null)} />
                </label>
                <label>
                  <span>Observación</span>
                  <input value={documentObservation} onChange={(event) => setDocumentObservation(event.target.value)} placeholder="Opcional" />
                </label>
                <button type="button" className="primary-action" onClick={() => void uploadDocument()} disabled={!expediente || !documentFile || saving || !canEdit}>
                  Cargar documento
                </button>
              </div>
              <div className="matricula-table-wrap titulacion-doc-table">
                <table className="matricula-table">
                  <thead>
                    <tr>
                      <th>Tipo</th>
                      <th>Archivo</th>
                      <th>Estado</th>
                      <th>Fecha</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.documents || []).map((doc) => (
                      <tr key={doc.DocumentoId}>
                        <td>{doc.TipoDocumentoCodigo}</td>
                        <td>{doc.NombreArchivo}</td>
                        <td>{doc.EstadoDocumento}</td>
                        <td>{doc.FechaCarga ? new Date(doc.FechaCarga).toLocaleDateString('es-EC') : 'No registrado'}</td>
                        <td>{doc.RutaNube ? <a href={doc.RutaNube} target="_blank" rel="noreferrer">Abrir</a> : 'Sin ruta'}</td>
                      </tr>
                    ))}
                    {(!data.documents || data.documents.length === 0) ? (
                      <tr><td colSpan={5}>Sin documentos cargados.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="student-card student-card--wide titulacion-generation-card" hidden={activeArea !== 'generacion'}>
              <div className="card-head">
                <div>
                  <span>Generación documental</span>
                  <h3>Acta, SENESCYT y título INTEC</h3>
                </div>
                <span>{textValue(expediente?.NumeroRefrendacion)}</span>
              </div>

              <div className="titulacion-generation-summary">
                <div>
                  <span>Número de acta / grado</span>
                  <strong>{textValue(expediente?.NumeroActaGrado || acta.numero_acta_grado)}</strong>
                </div>
                <div>
                  <span>Número de refrendación</span>
                  <strong>{textValue(expediente?.NumeroRefrendacion)}</strong>
                </div>
                <div>
                  <span>Registro SENESCYT</span>
                  <strong>{textValue(generation?.senescyt?.CodigoRegistroSenescyt)}</strong>
                </div>
                <div>
                  <span>Título INTEC</span>
                  <strong>{textValue(generation?.intec?.NumeroTitulo)}</strong>
                </div>
              </div>

              <div className="titulacion-subpanel">
                <div className="card-head">
                  <div>
                    <span>Acta de grado</span>
                    <h3>Generar / registrar acta</h3>
                  </div>
                </div>
                <div className="titulacion-mechanism-grid">
                  <label className="titulacion-span-2">
                    <span>Número de acta</span>
                    <input value={acta.numero_acta_grado} onChange={(event) => setActa((current) => ({ ...current, numero_acta_grado: event.target.value }))} placeholder="INTEC-VGA-EBSG-Q-A-20251204-01" />
                  </label>
                  <label>
                    <span>Fecha acta</span>
                    <input type="date" value={acta.fecha_acta} onChange={(event) => setActa((current) => ({ ...current, fecha_acta: event.target.value }))} />
                  </label>
                  <label>
                    <span>Hora acta</span>
                    <input type="time" value={acta.hora_acta} onChange={(event) => setActa((current) => ({ ...current, hora_acta: event.target.value }))} />
                  </label>
                  <label>
                    <span>Ciudad</span>
                    <input value={acta.ciudad} onChange={(event) => setActa((current) => ({ ...current, ciudad: event.target.value }))} />
                  </label>
                  <label>
                    <span>Escuela</span>
                    <input value={acta.escuela} onChange={(event) => setActa((current) => ({ ...current, escuela: event.target.value }))} />
                  </label>
                  <label>
                    <span>Autoridad académica</span>
                    <input value={acta.autoridad_academica} onChange={(event) => setActa((current) => ({ ...current, autoridad_academica: event.target.value }))} />
                  </label>
                  <label>
                    <span>Docente evaluador</span>
                    <input value={acta.docente_evaluador} onChange={(event) => setActa((current) => ({ ...current, docente_evaluador: event.target.value }))} />
                  </label>
                  <label>
                    <span>Coordinador académico</span>
                    <input value={acta.coordinador_academico} onChange={(event) => setActa((current) => ({ ...current, coordinador_academico: event.target.value }))} />
                  </label>
                  <label className="titulacion-span-2">
                    <span>Ruta PDF acta</span>
                    <input value={acta.ruta_acta_pdf} onChange={(event) => setActa((current) => ({ ...current, ruta_acta_pdf: event.target.value }))} placeholder="Ruta local o nube" />
                  </label>
                  <button type="button" className="primary-action" onClick={() => void generateActa()} disabled={!expediente || saving || !canEdit}>
                    Generar acta
                  </button>
                </div>
              </div>

              <div className="titulacion-subpanel">
                <div className="card-head">
                  <div>
                    <span>SENESCYT</span>
                    <h3>Registro externo</h3>
                  </div>
                </div>
                <div className="titulacion-mechanism-grid">
                  <label>
                    <span>Código registro</span>
                    <input value={senescyt.codigo_registro_senescyt} onChange={(event) => setSenescyt((current) => ({ ...current, codigo_registro_senescyt: event.target.value }))} />
                  </label>
                  <label>
                    <span>Fecha registro</span>
                    <input type="date" value={senescyt.fecha_registro} onChange={(event) => setSenescyt((current) => ({ ...current, fecha_registro: event.target.value }))} />
                  </label>
                  <label className="titulacion-span-2">
                    <span>Ruta documento</span>
                    <input value={senescyt.ruta_documento_nube} onChange={(event) => setSenescyt((current) => ({ ...current, ruta_documento_nube: event.target.value }))} />
                  </label>
                  <button type="button" className="secondary-action" onClick={() => void registerSenescyt()} disabled={!expediente || saving || !canEdit}>
                    Registrar SENESCYT
                  </button>
                </div>
              </div>

              <div className="titulacion-subpanel">
                <div className="card-head">
                  <div>
                    <span>INTEC</span>
                    <h3>Título institucional</h3>
                  </div>
                </div>
                <div className="titulacion-mechanism-grid">
                  <label>
                    <span>Número título</span>
                    <input value={intec.numero_titulo} onChange={(event) => setIntec((current) => ({ ...current, numero_titulo: event.target.value }))} />
                  </label>
                  <label>
                    <span>Fecha emisión</span>
                    <input type="date" value={intec.fecha_emision} onChange={(event) => setIntec((current) => ({ ...current, fecha_emision: event.target.value }))} />
                  </label>
                  <label>
                    <span>Código verificación</span>
                    <input value={intec.codigo_verificacion} onChange={(event) => setIntec((current) => ({ ...current, codigo_verificacion: event.target.value }))} />
                  </label>
                  <label className="titulacion-span-2">
                    <span>Ruta documento</span>
                    <input value={intec.ruta_documento_nube} onChange={(event) => setIntec((current) => ({ ...current, ruta_documento_nube: event.target.value }))} />
                  </label>
                  <button type="button" className="secondary-action" onClick={() => void registerIntec()} disabled={!expediente || saving || !canEdit}>
                    Registrar título INTEC
                  </button>
                </div>
              </div>
            </article>

            <article className="student-card student-card--wide titulacion-prevalidation" hidden>
              <div className="card-head">
                <div>
                  <span>Prevalidación</span>
                  <h3>{puedeTitularse ? 'Expediente apto' : 'Expediente pendiente'}</h3>
                </div>
                <span>{textValue(expediente?.EstadoExpediente)}</span>
              </div>
              <p>{pendingMessage || 'Ejecuta la validación para revisar parámetros.'}</p>
              <div className="teams-actions">
                <button type="button" className="secondary-action" onClick={() => void syncPractices()} disabled={!expediente || saving}>
                  Sincronizar prácticas
                </button>
                <button type="button" className="primary-action" onClick={() => void generate()} disabled={!expediente || saving || !canEdit}>
                  Generar titulación
                </button>
              </div>
            </article>
          </section>
        </>
      ) : null}
      {reviewItem ? (
        <div className="titulacion-modal-backdrop" role="presentation" onClick={() => setReviewItem(null)}>
          <section className="titulacion-review-modal" role="dialog" aria-modal="true" aria-label="Revisión de estudiante" onClick={(event) => event.stopPropagation()}>
            <div className="card-head">
              <div>
                <span>Revisión</span>
                <h3>{textValue(reviewItem.ApellidosNombres)}</h3>
              </div>
              <button type="button" className="secondary-action" onClick={() => setReviewItem(null)}>Cerrar</button>
            </div>
            <div className="titulacion-review-summary">
              <div><span>Cédula</span><strong>{textValue(reviewItem.NumeroIdentificacion)}</strong></div>
              <div><span>Carrera</span><strong>{textValue(reviewItem.NombreCarrera)}</strong></div>
              <div><span>Periodo</span><strong>{textValue(reviewItem.CodigoPeriodo)}</strong></div>
              <div><span>Estado</span><strong>{reviewItem.AptoTitulacion ? 'Apto' : 'Pendiente'}</strong></div>
            </div>
            <div className="matricula-table-wrap titulacion-progress-table">
              <table>
                <thead>
                  <tr>
                    <th>Requisito</th>
                    <th>Avance</th>
                    <th>Porcentaje</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Malla', `${numberText(reviewItem.MateriasAprobadas)} / ${MATERIAS_REQUERIDAS_TITULACION}`, percentValue((Number(reviewItem.MateriasAprobadas || 0) / MATERIAS_REQUERIDAS_TITULACION) * 100), reviewItem.CumpleMalla24],
                    ['Inglés A2+ - INTERMEDIATE', reviewChecks.ingles_a2_cumple ? 'Validado por administración' : 'Pendiente', reviewChecks.ingles_a2_cumple ? 100 : 0, reviewChecks.ingles_a2_cumple],
                    ['Prácticas preprofesionales', `${numberText(reviewItem.TotalHorasPracticasPreprofesionales)} / 240 horas`, percentValue((Number(reviewItem.TotalHorasPracticasPreprofesionales || 0) / 240) * 100), reviewItem.CumplePracticasPreprofesionales],
                    ['Vinculación con la sociedad', `${numberText(reviewItem.TotalHorasVinculacion)} / ${HORAS_REQUERIDAS_VINCULACION} horas`, percentValue((Number(reviewItem.TotalHorasVinculacion || 0) / HORAS_REQUERIDAS_VINCULACION) * 100), reviewItem.CumpleVinculacion],
                  ].map(([label, current, percent, ok]) => (
                    <tr key={String(label)}>
                      <td>{String(label)}</td>
                      <td>{String(current)}</td>
                      <td>
                        {String(label) === 'Malla' ? (
                          <button type="button" className="titulacion-progress-meter titulacion-progress-meter--button" onClick={() => void openMallaDetail(reviewItem)}>
                            <span style={{ width: `${Number(percent)}%` }} />
                          </button>
                        ) : (
                          <div className="titulacion-progress-meter">
                            <span style={{ width: `${Number(percent)}%` }} />
                          </div>
                        )}
                        <strong>{Number(percent)}%</strong>
                      </td>
                      <td><span className={ok ? 'status-pill is-ok' : 'status-pill is-warning'}>{ok ? 'Cumple' : 'Pendiente'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="titulacion-review-edit">
              <strong>Editar verificación</strong>
              {[
                ['Cédula validada', 'cedula_validada'],
                ['Título bachiller', 'titulo_bachiller_cumple'],
                ['Inglés A2+ - INTERMEDIATE', 'ingles_a2_cumple'],
                ['No adeuda financiero', 'no_adeuda_financiero'],
                ['Apto sustentación', 'apto_sustentacion'],
                ['Rúbrica titulación', 'rubrica_titulacion_cumple'],
              ].map(([label, key]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={reviewChecks[key as keyof typeof reviewChecks]}
                    onChange={(event) => setReviewChecks((current) => ({ ...current, [key]: event.target.checked }))}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <div className="titulacion-review-actions">
              <label>
                <span>Proceso a rendir</span>
                <select value={reviewMechanism} onChange={(event) => setReviewMechanism(event.target.value as TitulacionMecanismoCodigo)}>
                  <option value="EXAMEN_COMPLEXIVO">Examen complexivo</option>
                  <option value="DEFENSA_GRADO">Defensa de grado</option>
                </select>
              </label>
              <button
                type="button"
                className="primary-action"
                onClick={() => void proceedFromReview()}
                disabled={saving || !reviewItem.CumpleMalla24 || !reviewChecks.ingles_a2_cumple || !reviewItem.CumplePracticasPreprofesionales || !reviewItem.CumpleVinculacion}
              >
                Dar paso
              </button>
            </div>
            {(!reviewItem.CumpleMalla24 || !reviewChecks.ingles_a2_cumple || !reviewItem.CumplePracticasPreprofesionales || !reviewItem.CumpleVinculacion) ? (
              <p className="form-error">
                No se puede dar paso hasta cumplir malla, inglés A2+ - INTERMEDIATE, prácticas profesionales y vinculación con la sociedad.
              </p>
            ) : null}
          </section>
        </div>
      ) : null}
      {mallaDetail ? (
        <div className="titulacion-modal-backdrop titulacion-modal-backdrop--stacked" role="presentation" onClick={() => setMallaDetail(null)}>
          <section className="titulacion-review-modal titulacion-grades-modal" role="dialog" aria-modal="true" aria-label="Calificaciones de malla" onClick={(event) => event.stopPropagation()}>
            <div className="card-head">
              <div>
                <span>Malla académica</span>
                <h3>{textValue(mallaDetail.item.ApellidosNombres)}</h3>
              </div>
              <button type="button" className="secondary-action" onClick={() => setMallaDetail(null)}>Cerrar</button>
            </div>
            <div className="titulacion-review-summary">
              <div><span>Cédula</span><strong>{textValue(mallaDetail.item.NumeroIdentificacion)}</strong></div>
              <div><span>Carrera</span><strong>{textValue(mallaDetail.item.NombreCarrera)}</strong></div>
              <div><span>Aprobadas</span><strong>{numberText(mallaDetail.data?.summary?.materias_aprobadas)} / {numberText(mallaDetail.data?.summary?.materias_requeridas || MATERIAS_REQUERIDAS_TITULACION)}</strong></div>
              <div><span>Avance</span><strong>{numberText(mallaDetail.data?.summary?.porcentaje_malla)}%</strong></div>
            </div>
            {mallaDetail.loading ? (
              <p className="form-success">Consultando calificaciones...</p>
            ) : null}
            {mallaDetail.error ? (
              <p className="form-error">{mallaDetail.error}</p>
            ) : null}
            {!mallaDetail.loading && !mallaDetail.error ? (
              <div className="matricula-table-wrap titulacion-grades-table">
                <table>
                  <thead>
                    <tr>
                      <th>Materia</th>
                      <th>Nivel</th>
                      <th>Periodo</th>
                      <th>Tipo</th>
                      <th>Parciales</th>
                      {showHomologationGrades ? (
                        <>
                          <th>Teórico</th>
                          <th>Práctico</th>
                        </>
                      ) : null}
                      <th>Final</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mallaGrades.map((grade) => {
                      const type = gradeType(grade)
                      const rowKey = gradeKey(grade)
                      const expanded = expandedRegularGrade === rowKey
                      return (
                        <Fragment key={rowKey}>
                          <tr>
                            <td>
                              <strong>{textValue(grade.nombre_materia)}</strong>
                              <span>{textValue(grade.codigo_materia)}</span>
                            </td>
                            <td>{textValue(grade.semestre)}</td>
                            <td>{textValue(grade.nombre_periodo || grade.codigo_periodo)}</td>
                            <td>
                              <strong>{type}</strong>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="secondary-action titulacion-grade-toggle"
                                onClick={() => setExpandedRegularGrade(expanded ? null : rowKey)}
                              >
                                {expanded ? 'Ocultar detalle' : 'Ver detalle'}
                              </button>
                            </td>
                            {showHomologationGrades ? (
                              <>
                                <td>{type === 'H' ? gradeText(grade.teoria_homo) : '-'}</td>
                                <td>{type === 'H' ? gradeText(grade.practica_homo) : '-'}</td>
                              </>
                            ) : null}
                            <td>{gradeText(grade.nota_final ?? grade.promedio_final_registrado)}</td>
                            <td>
                              <span className={boolValue(grade.aprobada) ? 'status-pill is-ok' : 'status-pill is-warning'}>
                                {textValue(grade.estado)}
                              </span>
                            </td>
                          </tr>
                          {expanded ? (
                            <tr className="titulacion-grade-detail-row">
                              <td colSpan={mallaGradesColSpan}>
                                <div className="titulacion-grade-detail">
                                  {gradeDetailGroups(grade).map((group) => (
                                    <section key={group.title}>
                                      <h4>{group.title}</h4>
                                      {group.items.map(([label, value]) => (
                                        <span key={label}><strong>{label}</strong>{value}</span>
                                      ))}
                                    </section>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      )
                    })}
                    {!mallaGrades.length ? (
                      <tr>
                        <td colSpan={mallaGradesColSpan}>No se encontraron materias para esta malla.</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  )
}
