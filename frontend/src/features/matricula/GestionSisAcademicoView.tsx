import { Fragment, useEffect, useMemo, useState } from 'react'

import {
  applyAcademicPeriodChange,
  createSisAcademicoRecord,
  fetchAcademicEnrollmentDetail,
  fetchAcademicPeriodChangeCatalog,
  fetchSisAcademicoCatalog,
  fetchSisAcademicoRecord,
  fetchSisAcademicoRows,
  previewAcademicPeriodChange,
  updateStudentStateWithDocument,
  updateSisAcademicoRecord,
} from '../../lib/api'
import type {
  AcademicEnrollmentDetailResponse,
  AcademicPeriodChangeCatalogResponse,
  AcademicPeriodChangePreviewResponse,
  AcademicPeriodOption,
  SisAcademicoField,
  SisAcademicoRow,
  SisAcademicoSection,
} from '../../types/app'

type GestionSisAcademicoViewProps = {
  displayName: string
  initialSectionKey?: string
  allowedSectionKeys?: string[]
  onSectionChange?: (sectionKey: string) => void
  onOpenMoodleUsers?: () => void
}

type FormValue = string | number | boolean | null | undefined
type OptionItem = { value: string; label: string }
type InlineEstadoValues = Record<string, { Estado?: string; Informacion?: string; Documento?: File | null }>
type HomoMateriaGroup = {
  key: string
  name: string
  codes: string[]
  labels: string[]
}

type ProcessShortcut = {
  key: string
  title: string
  description: string
  sections: string[]
}

type ProcessWithSections = ProcessShortcut & {
  availableSections: SisAcademicoSection[]
}

type OperationalFlowStep = {
  key: string
  number: string
  title: string
  description: string
  sections: string[]
}

const processShortcuts: ProcessShortcut[] = [
  {
    key: 'admision',
    title: 'Admisión',
    description: 'Preinscripción, aspirantes, asesores, factura y documentos de ingreso.',
    sections: ['preinscripciones', 'datos_factura'],
  },
  {
    key: 'matriculas',
    title: 'Matrículas',
    description: 'Cabecera, materias, pagos y control de matrícula.',
    sections: ['cabecera_matricula', 'matricula_materias', 'pagos_matricula'],
  },
  {
    key: 'notas',
    title: 'Notas',
    description: 'Notas por estudiante, carrera, materia, período y paralelo.',
    sections: ['matricula_materias', 'materias'],
  },
  {
    key: 'personas',
    title: 'Estudiante',
    description: 'Listado, ficha, documentos y datos académicos.',
    sections: ['actualizacion_estudiantes', 'estudiantes', 'registro_documentos_estudiante', 'seguimiento'],
  },
  {
    key: 'docencia',
    title: 'Docente',
    description: 'Ingreso de docentes, asignación de materias, cuestionarios, evaluación y estado Moodle.',
    sections: [
      'docentes',
      'actualizacion_est',
      'docente_materias',
      'numero_preguntas',
      'cuestionarios',
      'planes_foros',
      'preguntas_evaluacion',
      'evaluacion_resultados',
      'autoevaluacion_resultados',
      'fechas_autoevaluacion',
    ],
  },
  {
    key: 'administrativos',
    title: 'Usuarios',
    description: 'Registro de usuarios administrativos, perfiles y accesos del menú.',
    sections: ['usuarios', 'menu_usuarios', 'menu_general'],
  },
  {
    key: 'academico',
    title: 'Proceso académico',
    description: 'Carreras, materias, mallas, textos HOMO, paralelos, períodos, asistencia y aperturas.',
    sections: [
      'carreras',
      'materias',
      'mallas',
      'materia_homo_textof',
      'periodos',
      'fechas_notas',
      'fechas_autoevaluacion',
      'asistencia_estudiantes',
      'provincias',
      'paralelos',
      'dias_matricula',
      'horarios_matricula',
      'jornadas',
      'modalidades',
    ],
  },
  {
    key: 'migracion',
    title: 'Migración',
    description: 'Procesos controlados de cambio de modalidad y período académico.',
    sections: ['cambio_periodo_hr'],
  },
  {
    key: 'vinculacion',
    title: 'Seguimiento y prácticas',
    description: 'Observaciones, prácticas laborales, Servicio Comunitario y empresas.',
    sections: ['seguimiento', 'practicas', 'practicas_vinculacion', 'empresas'],
  },
  {
    key: 'educacion_continua',
    title: 'Educación continua',
    description: 'Cursos, cortes, participantes y control heredado de ofertas cortas.',
    sections: ['cursos_edu_continua', 'corte_curso', 'corte_curso_estudiante'],
  },
  {
    key: 'certificados',
    title: 'Certificados',
    description: 'Certificados generados y trazabilidad documental.',
    sections: ['certificados_generados'],
  },
  {
    key: 'documentacion',
    title: 'Documentación',
    description: 'Repositorio digital y documentos anexados al estudiante.',
    sections: ['repositorio', 'registro_documentos_estudiante'],
  },
  {
    key: 'talento_humano',
    title: 'Talento humano',
    description: 'Empleados, solicitudes y tareas de talento humano integradas en el sistema.',
    sections: ['talento_humano_empleados', 'talento_humano_solicitudes', 'talento_humano_tareas'],
  },
  {
    key: 'integraciones',
    title: 'Integraciones',
    description: 'Notas de Moodle, sincronizaciones y auditoría de Microsoft 365.',
    sections: ['moodle_notas', 'moodle_sincronizacion', 'microsoft365_audit'],
  },
]

const operationalFlowSteps: OperationalFlowStep[] = [
  {
    key: 'inscripcion',
    number: '01',
    title: 'Inscripción y admisión',
    description: 'Aspirante, asesor, datos de factura y documentos iniciales.',
    sections: ['preinscripciones', 'datos_factura', 'registro_documentos_estudiante'],
  },
  {
    key: 'datos',
    number: '02',
    title: 'Datos del estudiante',
    description: 'Ficha, actualización de datos y estado del estudiante.',
    sections: ['estudiantes', 'actualizacion_estudiantes', 'seguimiento'],
  },
  {
    key: 'matricula',
    number: '03',
    title: 'Matrícula académica',
    description: 'Cabecera, materias matriculadas, pagos y convenio.',
    sections: ['cabecera_matricula', 'matricula_materias', 'pagos_matricula'],
  },
  {
    key: 'docencia',
    number: '04',
    title: 'Docencia y períodos',
    description: 'Docentes, asignaciones, paralelos, jornadas y períodos.',
    sections: ['docentes', 'docente_materias', 'paralelos', 'periodos', 'jornadas'],
  },
  {
    key: 'cursado',
    number: '05',
    title: 'Cursado, asistencia y notas',
    description: 'Notas, aperturas, asistencia y seguimiento académico.',
    sections: ['matricula_materias', 'fechas_notas', 'asistencia_estudiantes', 'moodle_notas'],
  },
  {
    key: 'practicas',
    number: '06',
    title: 'Prácticas y vinculación',
    description: 'Prácticas preprofesionales, vinculación con la sociedad y empresas.',
    sections: ['practicas', 'practicas_vinculacion', 'empresas', 'seguimiento'],
  },
  {
    key: 'certificados',
    number: '07',
    title: 'Certificados y documentos',
    description: 'Certificados, repositorio y documentos históricos.',
    sections: ['certificados_generados', 'repositorio', 'registro_documentos_estudiante'],
  },
  {
    key: 'titulacion',
    number: '08',
    title: 'Titulación y cierre',
    description: 'Base documental para grado, SENESCYT, título institucional y trazabilidad final.',
    sections: ['certificados_generados', 'repositorio', 'matricula_materias', 'practicas_vinculacion'],
  },
]

function valueLabel(value: FormValue): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  return String(value)
}

function gradeLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function fieldOptions(field: SisAcademicoField, value: FormValue) {
  const options = field.options || []
  const currentValue = inputValue(value)
  if (!currentValue || options.some((option) => String(option.value) === currentValue)) {
    return options
  }
  return [{ value: currentValue, label: `${currentValue} (valor actual)` }, ...options]
}

function displayValue(field: SisAcademicoField, value: FormValue): string {
  const currentValue = inputValue(value)
  const option = field.options?.find((item) => String(item.value) === currentValue)
  return option?.label || valueLabel(value)
}

function inputValue(value: FormValue): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function recordKey(row: SisAcademicoRow): string {
  return String(row._record_key || '')
}

function coerceFieldValue(field: SisAcademicoField, value: string | boolean): FormValue {
  const type = field.type || 'text'
  if (type === 'bool') return Boolean(value)
  if (value === '') return ''
  if (type === 'number' || type === 'decimal') return Number(value)
  return String(value)
}

function materiaNameFromOption(label?: string): string {
  if (!label) return ''
  const parts = label.split(' - ')
  const withoutCode = (parts.length > 1 ? parts.slice(1).join(' - ') : label).trim()
  return withoutCode.replace(/\s*\([^)]*\)\s*$/, '').trim()
}

function normalizeSearchText(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase()
}

function uniqueOptionsByValue(options: OptionItem[]): OptionItem[] {
  const seen = new Set<string>()
  return options.filter((option) => {
    const value = String(option.value)
    if (!value || seen.has(value)) return false
    seen.add(value)
    return true
  })
}

function formatSpanishDate(value: string): string {
  const [yearText, monthText, dayText] = value.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const months = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
  ]
  if (!year || !month || !day || !months[month - 1]) return ''
  return `${day} de ${months[month - 1]} del ${year}`
}

function formatSpanishDateRange(start: string, end: string): string {
  const startText = formatSpanishDate(start)
  const endText = formatSpanishDate(end)
  if (!startText || !endText) return ''
  return `${startText} al ${endText}`
}

function periodOptionLabel(period?: AcademicPeriodOption): string {
  if (!period) return ''
  const dates = [period.fecha_inicio, period.fecha_fin].filter(Boolean).join(' / ')
  return `${period.detalle_periodo || period.codigo_periodo}${dates ? ` (${dates})` : ''} - ${period.codigo_periodo}`
}

function emptyValues(fields: SisAcademicoField[]): Record<string, FormValue> {
  return fields.reduce<Record<string, FormValue>>((acc, field) => {
    acc[field.name] = field.type === 'bool' ? false : ''
    return acc
  }, {})
}

function todayIsoDate(): string {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function valueOrDash(value: unknown): string {
  const normalized = String(value ?? '').trim()
  return normalized || '-'
}

function maskedStudentDocument(value: unknown): string {
  const normalized = String(value ?? '').replace(/\s+/g, '').trim()
  if (!normalized) return '-'
  const visible = normalized.slice(-4)
  return normalized.length > 4 ? `**** ${visible}` : visible
}

function formatAcademicGrade(value?: number | null): string {
  if (value === null || value === undefined) return '-'
  return value.toLocaleString('es-EC', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function shouldRenderSelect(sectionKey: string, field: SisAcademicoField, options: OptionItem[]): boolean {
  if (options.length === 0) return false
  if (['login', 'password', 'nombres', 'email', 'cedula'].includes(field.name)) {
    return false
  }
  if (sectionKey === 'usuarios' && field.name === 'fecha_ingreso') return false
  return true
}

export function GestionSisAcademicoView({
  displayName,
  initialSectionKey = '',
  allowedSectionKeys,
  onSectionChange,
  onOpenMoodleUsers,
}: Readonly<GestionSisAcademicoViewProps>) {
  const allowedSectionSignature = [...(allowedSectionKeys || [])].sort().join('|')
  const [sections, setSections] = useState<SisAcademicoSection[]>([])
  const [selectedSectionKey, setSelectedSectionKey] = useState('')
  const [appliedInitialSection, setAppliedInitialSection] = useState('')
  const [selectedProcessKey, setSelectedProcessKey] = useState(processShortcuts[0]?.key || '')
  const [query, setQuery] = useState('')
  const [estadoPeriodFilter, setEstadoPeriodFilter] = useState('')
  const [docenteEstadoFilter, setDocenteEstadoFilter] = useState('')
  const [rows, setRows] = useState<SisAcademicoRow[]>([])
  const [selectedRecordKey, setSelectedRecordKey] = useState('')
  const [formValues, setFormValues] = useState<Record<string, FormValue>>({})
  const [mode, setMode] = useState<'edit' | 'create'>('edit')
  const [tableFilter, setTableFilter] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [studentAcademicHistory, setStudentAcademicHistory] = useState<AcademicEnrollmentDetailResponse | null>(null)
  const [studentAcademicHistoryLoading, setStudentAcademicHistoryLoading] = useState(false)
  const [studentAcademicHistoryError, setStudentAcademicHistoryError] = useState('')
  const [studentProfileEditing, setStudentProfileEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [inlineSavingKey, setInlineSavingKey] = useState('')
  const [inlineEstadoValues, setInlineEstadoValues] = useState<InlineEstadoValues>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [homoBulkPeriodo, setHomoBulkPeriodo] = useState('')
  const [homoBulkFechaInicio, setHomoBulkFechaInicio] = useState('')
  const [homoBulkFechaFin, setHomoBulkFechaFin] = useState('')
  const [homoBulkUrl, setHomoBulkUrl] = useState('')
  const [homoBulkSearch, setHomoBulkSearch] = useState('')
  const [homoBulkMateriaCodes, setHomoBulkMateriaCodes] = useState<string[]>([])
  const [homoMateriaSelectorOpen, setHomoMateriaSelectorOpen] = useState(false)
  const [homoMateriaNameSearch, setHomoMateriaNameSearch] = useState('')
  const [homoBulkSaving, setHomoBulkSaving] = useState(false)
  const [periodChangeCatalog, setPeriodChangeCatalog] = useState<AcademicPeriodChangeCatalogResponse | null>(null)
  const [periodChangeEstado, setPeriodChangeEstado] = useState('')
  const [periodChangeStudentQuery, setPeriodChangeStudentQuery] = useState('')
  const [periodChangeSelectedCedulas, setPeriodChangeSelectedCedulas] = useState<string[]>([])
  const [periodChangePreview, setPeriodChangePreview] = useState<AcademicPeriodChangePreviewResponse | null>(null)
  const [periodChangeLoading, setPeriodChangeLoading] = useState(false)
  const [periodChangeSaving, setPeriodChangeSaving] = useState(false)

  const selectedSection = useMemo(
    () => sections.find((section) => section.key === selectedSectionKey) || null,
    [sections, selectedSectionKey],
  )
  const processMenu = useMemo(
    () =>
      processShortcuts
        .map((process) => ({
          ...process,
          availableSections: process.sections
            .map((sectionKey) => sections.find((section) => section.key === sectionKey))
            .filter((section): section is SisAcademicoSection => Boolean(section))
            .sort((left, right) => left.title.localeCompare(right.title, 'es', { sensitivity: 'base' })),
        }))
        .filter((process) => process.availableSections.length > 0),
    [sections],
  )
  const operationalFlow = useMemo(
    () =>
      operationalFlowSteps
        .map((step) => ({
          ...step,
          availableSections: step.sections
            .map((sectionKey) => sections.find((section) => section.key === sectionKey))
            .filter((section): section is SisAcademicoSection => Boolean(section)),
        }))
        .filter((step) => step.availableSections.length > 0),
    [sections],
  )
  const selectedProcess = useMemo(
    () =>
      processMenu.find((process) => process.key === selectedProcessKey)
      || processMenu.find((process) => process.sections.includes(selectedSectionKey))
      || processMenu[0]
      || null,
    [processMenu, selectedProcessKey, selectedSectionKey],
  )
  const listFields = useMemo(() => selectedSection?.list_fields || [], [selectedSection?.list_fields])
  const editableFields = selectedSection?.editable_fields || []
  const createFields = selectedSection?.create_fields || []
  const currentFields = mode === 'create' ? createFields : editableFields
  const canCreate = createFields.length > 0
  const isOperationalMenuSection = selectedSectionKey === 'menu_general' || selectedSectionKey === 'menu_usuarios'
  const isEstadoInlineSection = selectedSectionKey === 'actualizacion_est' || selectedSectionKey === 'actualizacion_estudiantes'
  const isDocenteEstadoSection = selectedSectionKey === 'actualizacion_est'
  const isStudentEstadoSection = selectedSectionKey === 'actualizacion_estudiantes'
  const estadoInlineField = selectedSection?.editable_fields?.find((field) => field.name === 'Estado')
  const docenteEstadoOptions = useMemo(
    () => {
      const filteredOptions = (estadoInlineField?.options || []).filter((option) =>
        ['A', 'P'].includes(String(option.value).trim().toUpperCase()),
      )
      return filteredOptions.length > 0
        ? filteredOptions
        : [
            { value: 'A', label: 'A - Activo' },
            { value: 'P', label: 'P - Inactivo' },
          ]
    },
    [estadoInlineField],
  )
  const estadoPeriodField = selectedSection?.list_fields?.find((field) => field.name === 'codigo_periodo')
  const tableFields = isEstadoInlineSection ? listFields.filter((field) => field.name !== 'estado_nombre') : listFields
  const hasIndexColumn = !isEstadoInlineSection
  const tableColSpan = tableFields.length + 1 + (hasIndexColumn ? 1 : 0) + (isEstadoInlineSection ? 1 : 0) + (isStudentEstadoSection ? 1 : 0) + (isDocenteEstadoSection ? 1 : 0)
  const isStudentProfileSection = selectedSectionKey === 'estudiantes'
  const isUserAdministrationSection = selectedSectionKey === 'usuarios'
  const academicHistory = studentAcademicHistory?.historial_academico || []
  const studentProfileName = valueOrDash(
    studentAcademicHistory?.student?.nombre_estudiante
    ?? formValues.Apellidos_nombre
    ?? formValues.apellidos_nombre,
  )
  const studentProfileDocument = maskedStudentDocument(
    studentAcademicHistory?.student?.cedula
    ?? formValues.Cedula_Est
    ?? formValues.cedula,
  )
  const isMateriaHomoTextSection = selectedSection?.key === 'materia_homo_textof'
  const isPeriodChangeSection = selectedSection?.key === 'cambio_periodo_hr'
  const homoMateriaOptions = useMemo(
    (): OptionItem[] => uniqueOptionsByValue(selectedSection?.create_fields?.find((field) => field.name === 'cod_materia')?.options || []),
    [selectedSection],
  )
  const homoPeriodoOptions = useMemo(
    (): OptionItem[] => selectedSection?.create_fields?.find((field) => field.name === 'cod_periodo')?.options || [],
    [selectedSection],
  )
  const homoTextofecha = useMemo(
    () => formatSpanishDateRange(homoBulkFechaInicio, homoBulkFechaFin),
    [homoBulkFechaFin, homoBulkFechaInicio],
  )
  const filteredHomoMateriaOptions = useMemo(() => {
    const needle = homoBulkSearch.trim().toLowerCase()
    if (!needle) return homoMateriaOptions
    return homoMateriaOptions.filter((option) =>
      `${option.value} ${option.label}`.toLowerCase().includes(needle),
    )
  }, [homoBulkSearch, homoMateriaOptions])
  const selectedHomoMateriaOptions = useMemo(
    () =>
      homoBulkMateriaCodes.map((code) => ({
        code,
        option: homoMateriaOptions.find((option) => String(option.value) === code),
      })),
    [homoBulkMateriaCodes, homoMateriaOptions],
  )
  const homoSearchResults = useMemo(
    () => (homoBulkSearch.trim() ? filteredHomoMateriaOptions.slice(0, 30) : []),
    [filteredHomoMateriaOptions, homoBulkSearch],
  )
  const homoMateriaGroups = useMemo((): HomoMateriaGroup[] => {
    const groups = new Map<string, HomoMateriaGroup>()
    for (const option of homoMateriaOptions) {
      const code = String(option.value)
      const name = materiaNameFromOption(option.label) || option.label || code
      const key = normalizeSearchText(name)
      const current = groups.get(key) || { key, name, codes: [], labels: [] }
      if (!current.codes.includes(code)) {
        current.codes.push(code)
        current.labels.push(option.label)
      }
      groups.set(key, current)
    }
    return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name))
  }, [homoMateriaOptions])
  const filteredHomoMateriaGroups = useMemo(() => {
    const needle = normalizeSearchText(homoMateriaNameSearch)
    const source = needle
      ? homoMateriaGroups.filter((group) =>
          normalizeSearchText(`${group.name} ${group.codes.join(' ')} ${group.labels.join(' ')}`).includes(needle),
        )
      : homoMateriaGroups
    return source.slice(0, 80)
  }, [homoMateriaGroups, homoMateriaNameSearch])
  const selectedHomoMateriaGroupCount = useMemo(
    () => homoMateriaGroups.filter((group) => group.codes.some((code) => homoBulkMateriaCodes.includes(code))).length,
    [homoBulkMateriaCodes, homoMateriaGroups],
  )
  const filteredPeriodChangeStudents = useMemo(() => {
    const estado = periodChangeEstado.trim().toUpperCase()
    const needle = periodChangeStudentQuery.trim().toLowerCase()
    return (periodChangeCatalog?.students || [])
      .filter((student) => {
        const matchesEstado = !estado || estado === 'TODOS' || String(student.estado_codigo || '').trim().toUpperCase() === estado
        const text = `${student.codigo_estud || ''} ${student.cedula || ''} ${student.estudiante || ''} ${student.carrera || ''}`.toLowerCase()
        const matchesText = !needle || text.includes(needle)
        return matchesEstado && matchesText
      })
  }, [periodChangeCatalog, periodChangeEstado, periodChangeStudentQuery])
  const periodChangeVisibleCedulas = useMemo(
    () =>
      Array.from(
        new Set(
          filteredPeriodChangeStudents
            .map((student) => String(student.cedula_normalizada || student.cedula || '').trim())
            .filter(Boolean),
        ),
      ),
    [filteredPeriodChangeStudents],
  )
  const periodChangeSelectedSet = useMemo(
    () => new Set(periodChangeSelectedCedulas.map((cedula) => cedula.trim()).filter(Boolean)),
    [periodChangeSelectedCedulas],
  )
  const selectedPeriodChangeStudents = useMemo(
    () =>
      (periodChangeCatalog?.students || []).filter((student) =>
        periodChangeSelectedSet.has(String(student.cedula_normalizada || student.cedula || '').trim()),
      ),
    [periodChangeCatalog, periodChangeSelectedSet],
  )
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    const estado = docenteEstadoFilter.trim().toUpperCase()
    return rows.filter((row) => {
      const matchesTable = !needle || listFields.some((field) =>
        displayValue(field, row[field.name]).toLowerCase().includes(needle),
      )
      const matchesTeacherState = !isDocenteEstadoSection
        || !estado
        || String(row.Estado || '').trim().toUpperCase() === estado
      return matchesTable && matchesTeacherState
    })
  }, [docenteEstadoFilter, isDocenteEstadoSection, listFields, rows, tableFilter])
  const totalOperationalSections = useMemo(
    () => processMenu.reduce((total, process) => total + process.availableSections.length, 0),
    [processMenu],
  )
  const workflowTitle = isOperationalMenuSection
    ? selectedSectionKey === 'menu_usuarios'
      ? 'Accesos operativos del sistema'
      : 'Mapa operativo del sistema'
    : selectedSection?.title || 'Seleccione una opción del menú'
  const workflowCategory = isOperationalMenuSection
    ? 'Procesos integrados'
    : selectedProcess?.title || selectedSection?.category || 'Gestión operativa'
  const workflowTable = isOperationalMenuSection
    ? 'Backend y frontend integrados'
    : selectedSection?.table || 'Sin tabla'
  const workflowRows = isOperationalMenuSection ? totalOperationalSections : rows.length
  const workflowRowsLabel = isOperationalMenuSection ? `${workflowRows} módulo(s)` : `${workflowRows} registro(s)`
  const workflowMode = isOperationalMenuSection ? 'Navegación funcional' : canCreate ? 'Permite crear' : 'Solo edición'

  function processKeyForSection(sectionKey: string) {
    return processShortcuts.find((process) => process.sections.includes(sectionKey))?.key || processShortcuts[0]?.key || ''
  }

  async function loadRows(sectionKey = selectedSectionKey, nextQuery = query, nextPeriodo = estadoPeriodFilter) {
    if (!sectionKey) return
    setError('')
    setMessage('')
    if (sectionKey === 'cambio_periodo_hr' || sectionKey === 'menu_general' || sectionKey === 'menu_usuarios') {
      setRows([])
      setInlineEstadoValues({})
      setSelectedRecordKey('')
      setFormValues({})
      setStudentAcademicHistory(null)
      setStudentAcademicHistoryError('')
      setStudentProfileEditing(false)
      setMode('edit')
      return
    }
    setListLoading(true)
    try {
      const payload = await fetchSisAcademicoRows(sectionKey, nextQuery.trim(), {
        periodo: sectionKey === 'actualizacion_estudiantes' ? nextPeriodo : '',
      })
      setRows(payload.rows || [])
      setInlineEstadoValues({})
      setSelectedRecordKey('')
      setFormValues({})
      setStudentAcademicHistory(null)
      setStudentAcademicHistoryError('')
      setStudentProfileEditing(false)
      setMode('edit')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar la seccion')
      setRows([])
    } finally {
      setListLoading(false)
    }
  }

  async function openRecord(sectionKey: string, nextRecordKey: string) {
    if (!nextRecordKey) return
    setError('')
    setMessage('')
    setDetailLoading(true)
    setStudentAcademicHistory(null)
    setStudentAcademicHistoryError('')
    setStudentProfileEditing(false)
    setMode('edit')
    try {
      const payload = await fetchSisAcademicoRecord(sectionKey, nextRecordKey)
      setSelectedRecordKey(nextRecordKey)
      setFormValues(payload.record || {})
      if (sectionKey === 'estudiantes') {
        const studentCode = String(
          payload.record?.codigo_estud
          ?? payload.record?.CodigoEstud
          ?? payload.record?.Codigo_Estud
          ?? '',
        ).trim()
        if (studentCode) {
          setStudentAcademicHistoryLoading(true)
          try {
            const academicDetail = await fetchAcademicEnrollmentDetail(studentCode)
            setStudentAcademicHistory(academicDetail)
          } catch (academicError) {
            setStudentAcademicHistoryError(
              academicError instanceof Error
                ? academicError.message
                : 'No se pudo consultar la trayectoria académica del estudiante.',
            )
          } finally {
            setStudentAcademicHistoryLoading(false)
          }
        } else {
          setStudentAcademicHistoryError('El registro no contiene el código académico necesario para consultar la trayectoria.')
        }
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el registro')
      setSelectedRecordKey('')
      setFormValues({})
    } finally {
      setDetailLoading(false)
    }
  }

  async function saveRecord() {
    if (!selectedSection) return
    const savedRecordKey = selectedRecordKey
    const returnToStudentProfile = isStudentProfileSection && mode !== 'create' && Boolean(savedRecordKey)
    setError('')
    setMessage('')
    setSaving(true)
    try {
      const valuesToSave =
        mode === 'create' && selectedSection.key === 'usuarios'
          ? {
              ...formValues,
              fecha_ingreso: inputValue(formValues.fecha_ingreso) || todayIsoDate(),
            }
          : formValues
      const payload =
        mode === 'create'
          ? await createSisAcademicoRecord(selectedSection.key, valuesToSave)
          : await updateSisAcademicoRecord(selectedSection.key, selectedRecordKey, valuesToSave)
      const successMessage = payload.message || 'Cambios guardados'
      await loadRows(selectedSection.key)
      if (returnToStudentProfile) {
        await openRecord(selectedSection.key, savedRecordKey)
      }
      setMessage(successMessage)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar')
    } finally {
      setSaving(false)
    }
  }

  function inlineEstadoValue(row: SisAcademicoRow, fieldName: 'Estado' | 'Informacion') {
    const key = recordKey(row)
    const localValue = inlineEstadoValues[key]?.[fieldName]
    if (localValue !== undefined) return localValue
    return inputValue(row[fieldName])
  }

  function updateInlineEstado(row: SisAcademicoRow, values: { Estado?: string; Informacion?: string; Documento?: File | null }) {
    const key = recordKey(row)
    setInlineEstadoValues((current) => ({
      ...current,
      [key]: {
        Estado: current[key]?.Estado ?? inputValue(row.Estado),
        Informacion: current[key]?.Informacion ?? inputValue(row.Informacion),
        ...values,
      },
    }))
  }

  async function saveInlineEstado(row: SisAcademicoRow) {
    if (!selectedSection || !isEstadoInlineSection) return
    const key = recordKey(row)
    const estado = inlineEstadoValue(row, 'Estado').trim()
    const informacion = inlineEstadoValue(row, 'Informacion').trim()
    const documento = inlineEstadoValues[key]?.Documento || null
    if (!estado) {
      setError('Seleccione un estado antes de guardar.')
      return
    }
    if (isStudentEstadoSection && informacion.length < 5) {
      setError('Describe el motivo del cambio de estado.')
      return
    }
    if (isStudentEstadoSection && !documento) {
      setError('Adjunte el documento que respalda el cambio de estado.')
      return
    }
    setError('')
    setMessage('')
    setInlineSavingKey(key)
    try {
      const payload = isStudentEstadoSection && documento
        ? await updateStudentStateWithDocument(key, estado, informacion, documento)
        : await updateSisAcademicoRecord(selectedSection.key, key, {
            Estado: estado,
            Informacion: informacion,
          })
      setMessage(payload.message || 'Estado actualizado')
      await loadRows(selectedSection.key)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar el estado')
    } finally {
      setInlineSavingKey('')
    }
  }

  function startCreate() {
    if (!selectedSection) return
    setMode('create')
    setSelectedRecordKey('')
    setStudentProfileEditing(false)
    setStudentAcademicHistory(null)
    setStudentAcademicHistoryError('')
    setFormValues({
      ...emptyValues(createFields),
      ...(selectedSection.key === 'usuarios'
        ? {
            login: '',
            password: '',
            nombres: '',
            fecha_ingreso: todayIsoDate(),
            estado: 'A',
            email: '',
            cedula: '',
          }
        : {}),
    })
    setMessage('')
    setError('')
  }

  function openSection(sectionKey: string, processKey?: string) {
    if (onSectionChange) {
      onSectionChange(sectionKey)
      return
    }
    setSelectedSectionKey(sectionKey)
    setSelectedProcessKey(processKey || processKeyForSection(sectionKey))
    setQuery('')
    setEstadoPeriodFilter('')
    setDocenteEstadoFilter('')
    setTableFilter('')
    setSelectedRecordKey('')
    setFormValues({})
    setStudentProfileEditing(false)
    setMode('edit')
    void loadRows(sectionKey, '', '')
  }

  function toggleHomoMateria(code: string) {
    setHomoBulkMateriaCodes((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    )
  }

  function selectVisibleHomoMaterias() {
    const visibleCodes = filteredHomoMateriaOptions.map((option) => String(option.value))
    setHomoBulkMateriaCodes((current) => Array.from(new Set([...current, ...visibleCodes])))
  }

  function toggleHomoMateriaGroup(group: HomoMateriaGroup) {
    const allSelected = group.codes.every((code) => homoBulkMateriaCodes.includes(code))
    setHomoBulkMateriaCodes((current) => {
      const next = new Set(current)
      if (allSelected) {
        group.codes.forEach((code) => next.delete(code))
      } else {
        group.codes.forEach((code) => next.add(code))
      }
      return Array.from(next)
    })
    setHomoBulkSearch('')
    setError('')
    setMessage(
      allSelected
        ? `${group.name}: materia retirada de la selección.`
        : `${group.name}: ${group.codes.length} código(s) relacionados agregados.`,
    )
  }

  function clearHomoMaterias() {
    setHomoBulkMateriaCodes([])
  }

  async function saveHomoBulk() {
    if (!selectedSection || selectedSection.key !== 'materia_homo_textof') return
    setError('')
    setMessage('')

    if (!homoBulkPeriodo) {
      setError('Seleccione el período HOMO correspondiente.')
      return
    }
    if (!homoTextofecha) {
      setError('Seleccione fecha de inicio y fecha de fin para generar el texto de fecha.')
      return
    }
    if (homoBulkMateriaCodes.length === 0) {
      setError('Seleccione al menos una materia para guardar.')
      return
    }

    setHomoBulkSaving(true)
    try {
      let created = 0
      let updated = 0
      const uniqueCodes = Array.from(new Set(homoBulkMateriaCodes))
      for (const code of uniqueCodes) {
        const option = homoMateriaOptions.find((item) => item.value === code)
        const result = await createSisAcademicoRecord(selectedSection.key, {
          cod_materia: code,
          cod_periodo: Number(homoBulkPeriodo),
          materia: materiaNameFromOption(option?.label) || code,
          textofecha: homoTextofecha,
          url: homoBulkUrl.trim(),
        })
        if (result.action === 'updated') {
          updated += 1
        } else {
          created += 1
        }
      }
      setHomoBulkMateriaCodes([])
      await loadRows(selectedSection.key)
      setMessage(`Textos HOMO procesados: ${uniqueCodes.length}. Nuevos: ${created}. Actualizados: ${updated}.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar la selección HOMO')
    } finally {
      setHomoBulkSaving(false)
    }
  }

  function togglePeriodChangeStudent(cedulaValue?: string) {
    const cedula = String(cedulaValue || '').trim()
    if (!cedula) return
    setPeriodChangePreview(null)
    setPeriodChangeSelectedCedulas((current) =>
      current.includes(cedula) ? current.filter((item) => item !== cedula) : [...current, cedula],
    )
  }

  function selectVisiblePeriodChangeStudents() {
    setPeriodChangePreview(null)
    setPeriodChangeSelectedCedulas(periodChangeVisibleCedulas)
  }

  function clearPeriodChangeStudentSelection() {
    setPeriodChangePreview(null)
    setPeriodChangeSelectedCedulas([])
  }

  function periodChangePayload() {
    if (!periodChangeEstado) {
      setError('Seleccione el estado de estudiantes que deseas revisar.')
      return null
    }
    return {
      estado_codigo: periodChangeEstado,
      student_query: periodChangeStudentQuery.trim() || null,
      student_cedulas: periodChangeSelectedCedulas,
      exception_cedulas: [],
      solo_graduados: false,
    }
  }

  async function loadPeriodChangeCatalog() {
    setPeriodChangeLoading(true)
    setError('')
    try {
      const payload = await fetchAcademicPeriodChangeCatalog()
      setPeriodChangeCatalog(payload)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el catálogo de períodos H/R')
    } finally {
      setPeriodChangeLoading(false)
    }
  }

  async function previewPeriodChange() {
    const payload = periodChangePayload()
    if (!payload) return
    setPeriodChangeLoading(true)
    setError('')
    setMessage('')
    try {
      const preview = await previewAcademicPeriodChange(payload)
      setPeriodChangePreview(preview)
      setMessage(
        `Análisis generado: ${preview.summary?.migrar || 0} registro(s) listos en ${preview.summary?.periodos_regulares || 0} período(s) regular(es).`,
      )
    } catch (apiError) {
      setPeriodChangePreview(null)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar la vista previa H/R')
    } finally {
      setPeriodChangeLoading(false)
    }
  }

  async function applyPeriodChange() {
    const payload = periodChangePayload()
    if (!payload) return
    const pending = periodChangePreview?.summary?.migrar || 0
    if (!pending) {
      setError('Genere una vista previa con registros listos antes de aplicar el cambio.')
      return
    }
    if (!window.confirm(`Se cambiarán ${pending} registro(s) de matrícula HOMO a matrícula regular. ¿Desea continuar?`)) {
      return
    }
    setPeriodChangeSaving(true)
    setError('')
    setMessage('')
    try {
      const result = await applyAcademicPeriodChange(payload)
      setMessage(
        `${result.message || 'Migración aplicada.'} Actualizados: ${result.summary?.registros_actualizados || 0}. Cabeceras nuevas: ${result.summary?.cabeceras_insertadas || 0}.`,
      )
      setPeriodChangePreview(result.preview || null)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo aplicar el cambio H/R')
    } finally {
      setPeriodChangeSaving(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      try {
        const payload = await fetchSisAcademicoCatalog()
        if (cancelled) return
        const allowedSectionSet = new Set(allowedSectionSignature ? allowedSectionSignature.split('|') : [])
        const nextSections = allowedSectionSet.size
          ? (payload.sections || []).filter((section) => allowedSectionSet.has(section.key))
          : payload.sections || []
        setSections(nextSections)
        const requestedSection = nextSections.find((section) => section.key === initialSectionKey)?.key || ''
        const firstSection = requestedSection || nextSections[0]?.key || ''
        setSelectedSectionKey(firstSection)
        if (firstSection) {
          setSelectedProcessKey(processKeyForSection(firstSection))
        }
        if (firstSection && !['cambio_periodo_hr', 'menu_general', 'menu_usuarios'].includes(firstSection)) {
          const rowsPayload = await fetchSisAcademicoRows(firstSection, '')
          if (!cancelled) setRows(rowsPayload.rows || [])
        } else if (!cancelled) {
          setRows([])
        }
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar la gestión operativa.')
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
  }, [allowedSectionSignature, initialSectionKey])

  useEffect(() => {
    if (!initialSectionKey || initialSectionKey === appliedInitialSection) return
    const exists = sections.some((section) => section.key === initialSectionKey)
    if (!exists) return
    setAppliedInitialSection(initialSectionKey)
    setSelectedSectionKey(initialSectionKey)
    setSelectedProcessKey(processShortcuts.find((process) => process.sections.includes(initialSectionKey))?.key || processShortcuts[0]?.key || '')
    setQuery('')
    setEstadoPeriodFilter('')
    setDocenteEstadoFilter('')
    setTableFilter('')
    setSelectedRecordKey('')
    setFormValues({})
    setStudentAcademicHistory(null)
    setStudentAcademicHistoryError('')
    setStudentProfileEditing(false)
    setMode('edit')
    if (['cambio_periodo_hr', 'menu_general', 'menu_usuarios'].includes(initialSectionKey)) {
      setRows([])
      return
    }
    let cancelled = false
    setListLoading(true)
    void fetchSisAcademicoRows(initialSectionKey, '').then((payload) => {
      if (!cancelled) setRows(payload.rows || [])
    }).catch((apiError) => {
      if (!cancelled) setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar la seccion')
    }).finally(() => {
      if (!cancelled) setListLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [appliedInitialSection, initialSectionKey, sections])

  useEffect(() => {
    if (!isPeriodChangeSection || periodChangeCatalog) return
    void loadPeriodChangeCatalog()
  }, [isPeriodChangeSection, periodChangeCatalog])

  function openOperationalSection(sectionKey: string, processKey: string) {
    openSection(sectionKey, processKey)
  }

  function renderOperationalMenu(processes: ProcessWithSections[]) {
    const isAccessMode = selectedSectionKey === 'menu_usuarios'
    return (
      <div className="gestion-sis-operational-menu">
        <div className="gestion-sis-flow-map">
          <div className="gestion-sis-flow-map__head">
            <div>
              <span>Flujo académico completo</span>
              <strong>De inscripción a titulación</strong>
            </div>
            <p>
              Esta ruta conserva el orden operativo institucional y abre los módulos necesarios para cada etapa. Use las
              acciones de cada paso para revisar datos históricos o continuar el proceso.
            </p>
          </div>
          <div className="gestion-sis-flow-steps">
            {operationalFlow.map((step) => (
              <article key={step.key} className="gestion-sis-flow-step">
                <span className="gestion-sis-flow-step__number">{step.number}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.description}</p>
                </div>
                <div className="gestion-sis-flow-step__actions">
                  {step.availableSections.slice(0, 4).map((section) => (
                    <button
                      key={`${step.key}-${section.key}`}
                      type="button"
                      onClick={() => openOperationalSection(section.key, processKeyForSection(section.key))}
                    >
                      {section.title}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="gestion-sis-process-overview">
          <div className="gestion-sis-process-overview__head">
            <div>
              <span>{isAccessMode ? 'Accesos funcionales' : 'Integración funcional'}</span>
              <strong>{isAccessMode ? 'Procesos habilitados por perfil operativo' : 'Procesos disponibles del sistema académico'}</strong>
            </div>
            <p>
              {isAccessMode
                ? 'Esta vista reemplaza la tabla técnica MENU_USUARIOS. Use los accesos funcionales para entrar a cada módulo y gestione usuarios desde Registrar usuarios cuando corresponda.'
                : 'Esta vista reemplaza el menú técnico heredado. Cada bloque abre una función real del nuevo sistema: admisión, matrícula, notas, docentes, certificados, titulación, reportes y mantenimiento controlado.'}
            </p>
          </div>

          <div className="gestion-sis-process-cards">
            {processes.map((process) => (
              <button
                key={process.key}
                type="button"
                className={`gestion-sis-process-card${selectedProcessKey === process.key ? ' gestion-sis-process-card--active' : ''}`}
                onClick={() => {
                  setSelectedProcessKey(process.key)
                  const firstSection = process.availableSections[0]
                  if (firstSection) openOperationalSection(firstSection.key, process.key)
                }}
              >
                <span className="gestion-sis-process-card__count">{process.availableSections.length}</span>
                <strong>{process.title}</strong>
                <span>{process.description}</span>
                <small>Abrir proceso</small>
              </button>
            ))}
          </div>
        </div>

        {processes.map((process) => (
          <section key={`operational-${process.key}`} className="gestion-sis-module-strip">
            <div className="gestion-sis-module-strip__head">
              <div>
                <span>{process.title}</span>
                <strong>{process.description}</strong>
              </div>
              <em>{process.availableSections.length} módulo(s)</em>
            </div>
            <div className="gestion-sis-module-tabs gestion-sis-module-tabs--grid">
              {process.availableSections.map((section) => (
                <button
                  key={`${process.key}-${section.key}`}
                  type="button"
                  className={selectedSectionKey === section.key ? 'gestion-sis-module--active' : ''}
                  onClick={() => openOperationalSection(section.key, process.key)}
                >
                  <strong>{section.title}</strong>
                  <span>{section.category || section.table || 'Módulo operativo'}</span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    )
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Operativo</p>
          <h1>Gestión por procesos</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Módulos editables</span>
            </div>
          </div>
        </div>
      </header>

      <section className="gestion-sis-workflow" aria-label="Ruta operativa actual">
        <div className="gestion-sis-workflow__route">
          <span>Módulo actual</span>
          <strong>{workflowTitle}</strong>
        </div>
        <div className="gestion-sis-workflow__meta">
          <span>{workflowCategory}</span>
          <span>{workflowTable}</span>
          <span>{workflowRowsLabel}</span>
          <span>{workflowMode}</span>
        </div>
      </section>

      <section className="student-grid student-grid--content gestion-sis-grid gestion-sis-grid--single">
        <article className="student-card student-card--wide gestion-sis-list">
          <div className="card-head">
            <h3>{isOperationalMenuSection ? 'Procesos funcionales del sistema' : selectedSection?.title || 'Seleccione un módulo'}</h3>
            <span>{catalogLoading ? 'Cargando...' : isOperationalMenuSection ? 'Sistema académico integrado' : selectedSection?.category || 'Módulo'}</span>
          </div>

          {isOperationalMenuSection ? renderOperationalMenu(processMenu) : null}

          {isUserAdministrationSection && onOpenMoodleUsers ? (
            <section className="gestion-sis-moodle-users" aria-label="Control de cuentas de Moodle">
              <div>
                <span>Control de acceso virtual</span>
                <strong>Activar o inactivar una cuenta de Moodle</strong>
                <p>
                  Busque la cuenta por correo institucional. Antes de cambiar su estado, el sistema valida que el
                  correo exista en CorreosEstudIntec y corresponda a un estudiante registrado.
                </p>
              </div>
              <button type="button" className="primary-action" onClick={onOpenMoodleUsers}>
                Administrar cuentas Moodle
              </button>
            </section>
          ) : null}

          {isMateriaHomoTextSection ? (
            <div className="gestion-sis-homo-bulk">
              <div className="gestion-sis-homo-bulk__head">
                <div>
                  <strong>Ingreso masivo de textos HOMO</strong>
                  <span>Seleccione el período, el rango de fechas y todas las materias necesarias antes de guardar.</span>
                </div>
                <em>{homoBulkMateriaCodes.length} materia(s) seleccionada(s)</em>
              </div>

              <div className="matricula-acad-form gestion-sis-homo-bulk__form">
                <label>
                  <span>Período HOMO</span>
                  <select value={homoBulkPeriodo} onChange={(event) => setHomoBulkPeriodo(event.target.value)}>
                    <option value="">Seleccione período</option>
                    {homoPeriodoOptions.map((option) => (
                      <option key={`homo-periodo-${option.value}`} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Fecha inicio</span>
                  <input
                    type="date"
                    value={homoBulkFechaInicio}
                    onChange={(event) => setHomoBulkFechaInicio(event.target.value)}
                  />
                </label>
                <label>
                  <span>Fecha fin</span>
                  <input
                    type="date"
                    value={homoBulkFechaFin}
                    onChange={(event) => setHomoBulkFechaFin(event.target.value)}
                  />
                </label>
                <label>
                  <span>URL opcional</span>
                  <input value={homoBulkUrl} onChange={(event) => setHomoBulkUrl(event.target.value)} placeholder="Enlace o ruta del documento" />
                </label>
                <label className="gestion-sis-field--wide">
                  <span>Texto fecha generado</span>
                  <input value={homoTextofecha || '20 de mayo del 2024 al 16 de junio del 2024'} readOnly />
                </label>
                <div className="gestion-sis-homo-picker gestion-sis-field--wide">
                  <span>Código materia</span>
                  <div>
                    <strong>
                      {selectedHomoMateriaOptions.length > 0
                        ? `${selectedHomoMateriaOptions.length} código(s) de materia seleccionados`
                        : 'Sin materia seleccionada'}
                    </strong>
                    <button type="button" className="primary-action" onClick={() => setHomoMateriaSelectorOpen(true)}>
                      Seleccione la materia
                    </button>
                  </div>
                  <small>
                    Busque por nombre de materia. Al seleccionar se agregan todos los códigos relacionados para las carreras donde exista.
                  </small>
                </div>
                <label className="gestion-sis-field--wide">
                  <span>Búsqueda manual por código único</span>
                  <input
                    value={homoBulkSearch}
                    onChange={(event) => setHomoBulkSearch(event.target.value)}
                    placeholder="Opcional: buscar por código único, código interno o nombre"
                  />
                </label>
              </div>

              <div className="gestion-sis-homo-bulk__finder">
                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Resultados de búsqueda</strong>
                  <span>{homoSearchResults.length} resultado(s) visibles</span>
                </div>
                {homoSearchResults.length > 0 ? (
                  <div className="gestion-sis-homo-bulk__results">
                    {homoSearchResults.map((option) => {
                      const code = String(option.value)
                      const active = homoBulkMateriaCodes.includes(code)
                      return (
                        <button
                          key={`homo-result-${code}`}
                          type="button"
                          className={`gestion-sis-homo-bulk__result${active ? ' gestion-sis-homo-bulk__result--active' : ''}`}
                          onClick={() => toggleHomoMateria(code)}
                        >
                          <span>
                            <strong>{materiaNameFromOption(option.label) || option.label}</strong>
                            <small>Código único: {code}</small>
                          </span>
                          <em>{active ? 'Seleccionada' : 'Agregar'}</em>
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <p className="gestion-sis-homo-bulk__empty">
                    {homoBulkSearch.trim() ? 'No hay materias con ese criterio.' : 'Escriba un código o nombre para seleccionar materias.'}
                  </p>
                )}
              </div>

              <div className="gestion-sis-homo-bulk__toolbar">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={selectVisibleHomoMaterias}
                  disabled={!homoBulkSearch.trim() || filteredHomoMateriaOptions.length === 0}
                >
                  Seleccionar todo filtrado
                </button>
                <button type="button" className="ghost-button" onClick={clearHomoMaterias} disabled={homoBulkMateriaCodes.length === 0}>
                  Limpiar selección
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={() => void saveHomoBulk()}
                  disabled={homoBulkSaving || homoBulkMateriaCodes.length === 0}
                >
                  {homoBulkSaving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>

              <div className="gestion-sis-homo-bulk__materias">
                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Materias seleccionadas</strong>
                  <span>{selectedHomoMateriaOptions.length} materia(s) para guardar</span>
                </div>
                {selectedHomoMateriaOptions.length > 0 ? (
                  <div className="gestion-sis-homo-bulk__selected-list">
                    {selectedHomoMateriaOptions.map(({ code, option }) => {
                      const label = option?.label || code
                    return (
                      <button
                        key={`homo-selected-${code}`}
                        type="button"
                        className="gestion-sis-homo-bulk__selected"
                        onClick={() => toggleHomoMateria(code)}
                      >
                        <span>
                          <strong>{materiaNameFromOption(label) || label}</strong>
                          <small>{code}</small>
                        </span>
                        <em>Quitar</em>
                      </button>
                    )
                    })}
                  </div>
                ) : (
                  <p className="gestion-sis-homo-bulk__empty">Todavía no hay materias seleccionadas.</p>
                )}
              </div>
            </div>
          ) : null}

          {homoMateriaSelectorOpen ? (
            <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="homo-materia-selector-title">
              <article className="matricula-modal gestion-sis-homo-selector-modal">
                <div className="matricula-modal-head">
                  <div className="matricula-modal-title">
                    <span>Materia HOMO</span>
                    <h3 id="homo-materia-selector-title">Seleccione la materia</h3>
                  </div>
                  <button type="button" className="matricula-modal-close" onClick={() => setHomoMateriaSelectorOpen(false)}>
                    Cerrar
                  </button>
                </div>

                <div className="matricula-acad-form gestion-sis-homo-selector-search">
                  <label>
                    <span>Buscar por nombre de materia</span>
                    <input
                      value={homoMateriaNameSearch}
                      onChange={(event) => setHomoMateriaNameSearch(event.target.value)}
                      placeholder="Ejemplo: Base de Datos, Programacion, Seguridad"
                      autoFocus
                    />
                  </label>
                </div>

                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Materias encontradas</strong>
                  <span>{filteredHomoMateriaGroups.length} materia(s)</span>
                </div>

                <div className="gestion-sis-homo-name-list">
                  {filteredHomoMateriaGroups.length > 0 ? (
                    filteredHomoMateriaGroups.map((group) => {
                      const selectedCount = group.codes.filter((code) => homoBulkMateriaCodes.includes(code)).length
                      const allSelected = selectedCount === group.codes.length
                      return (
                        <button
                          key={`homo-group-${group.key}`}
                          type="button"
                          className={`gestion-sis-homo-name-option${selectedCount > 0 ? ' gestion-sis-homo-name-option--active' : ''}`}
                          aria-pressed={selectedCount > 0}
                          onClick={() => toggleHomoMateriaGroup(group)}
                        >
                          <span>
                            <strong>{group.name}</strong>
                            <small>{group.codes.length} código(s) relacionados: {group.codes.join(', ')}</small>
                          </span>
                          <em>
                            {allSelected
                              ? 'Seleccionada'
                              : selectedCount > 0
                                ? `${selectedCount}/${group.codes.length} agregado(s)`
                                : 'Seleccionar materia'}
                          </em>
                        </button>
                      )
                    })
                  ) : (
                    <p className="gestion-sis-homo-bulk__empty">No hay materias con ese nombre.</p>
                  )}
                </div>

                <div className="gestion-sis-homo-selector-footer">
                  <span>
                    {selectedHomoMateriaGroupCount} materia(s), {homoBulkMateriaCodes.length} código(s) seleccionados
                  </span>
                  <div>
                    <button type="button" className="ghost-button" onClick={clearHomoMaterias} disabled={homoBulkMateriaCodes.length === 0}>
                      Limpiar selección
                    </button>
                    <button type="button" className="primary-action" onClick={() => setHomoMateriaSelectorOpen(false)}>
                      Listo
                    </button>
                  </div>
                </div>
              </article>
            </div>
          ) : null}

          {message ? <p className="teams-message">{message}</p> : null}
          {error ? <p className="teams-error">{error}</p> : null}

          {isOperationalMenuSection ? null : isPeriodChangeSection ? (
            <div className="gestion-sis-homo-bulk gestion-sis-period-change">
              <div className="gestion-sis-homo-bulk__head">
                <div>
                  <strong>Migración matrícula H a R</strong>
                  <span>
                    Seleccione un estado, revise el listado de estudiantes y ejecute el análisis. El sistema calcula los
                    períodos regulares según las fechas HOMO, distribuye las materias en bloques de 6 y conserva el promedio final.
                  </span>
                </div>
                <em>{periodChangePreview?.summary?.migrar || 0} registro(s) listos</em>
              </div>

              <div className="matricula-acad-form gestion-sis-homo-bulk__form">
                <label>
                  <span>Estado</span>
                  <select
                    value={periodChangeEstado}
                    onChange={(event) => {
                      setPeriodChangeEstado(event.target.value)
                      setPeriodChangeSelectedCedulas([])
                      setPeriodChangePreview(null)
                    }}
                  >
                    <option value="">Seleccione estado</option>
                    {(periodChangeCatalog?.estados || []).map((estado) => (
                      <option key={`period-change-state-${estado.value}`} value={estado.value}>
                        {estado.label} ({estado.total || 0})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Buscar estudiante</span>
                  <input
                    value={periodChangeStudentQuery}
                    onChange={(event) => {
                      setPeriodChangeStudentQuery(event.target.value)
                      setPeriodChangeSelectedCedulas([])
                      setPeriodChangePreview(null)
                    }}
                    placeholder="Cédula, código, nombre o carrera"
                  />
                </label>
                <div className="gestion-sis-period-change__hint">
                  <strong>Flujo automático por fechas</strong>
                  <span>
                    El estado elegido carga estudiantes con matrículas HOMO. La vista previa calcula los períodos R
                    posibles y muestra duplicados, bloqueos y notas a migrar antes de guardar.
                  </span>
                </div>
              </div>

              <div className="gestion-sis-period-change__students">
                <div className="gestion-sis-homo-bulk__head">
                  <div>
                    <strong>Estudiantes encontrados</strong>
                    <span>
                      Seleccione uno o varios estudiantes para analizar solo esos registros. Si no selecciona ninguno,
                      el análisis se ejecuta sobre todo el listado filtrado.
                    </span>
                  </div>
                  <em>
                    {periodChangeSelectedCedulas.length > 0
                      ? `${periodChangeSelectedCedulas.length} seleccionado(s)`
                      : `${filteredPeriodChangeStudents.length} visible(s)`}
                  </em>
                </div>
                <div className="gestion-sis-period-change__student-actions">
                  <button type="button" className="ghost-button" onClick={selectVisiblePeriodChangeStudents} disabled={periodChangeVisibleCedulas.length === 0}>
                    Seleccionar visibles
                  </button>
                  <button type="button" className="ghost-button" onClick={clearPeriodChangeStudentSelection} disabled={periodChangeSelectedCedulas.length === 0}>
                    Limpiar selección
                  </button>
                  <span>
                    {selectedPeriodChangeStudents.length > 0
                      ? `${selectedPeriodChangeStudents.length} estudiante(s) iran al analisis`
                      : 'Sin selección manual'}
                  </span>
                </div>
                <div className="gestion-sis-period-change__student-grid">
                  {filteredPeriodChangeStudents.length > 0 ? (
                    filteredPeriodChangeStudents.map((student) => {
                      const cedulaKey = String(student.cedula_normalizada || student.cedula || '').trim()
                      const selected = periodChangeSelectedSet.has(cedulaKey)
                      return (
                        <article
                          key={`period-change-student-${student.codigo_estud}-${student.cod_anio_basica}`}
                          className={selected ? 'is-selected' : ''}
                        >
                          <label>
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => togglePeriodChangeStudent(cedulaKey)}
                            />
                            <span>
                              <strong>{student.estudiante || '-'}</strong>
                              <small>{student.cedula || '-'} · {student.carrera || '-'}</small>
                            </span>
                          </label>
                          <span>{student.estado_nombre || student.estado_codigo || '-'}</span>
                          <small>
                            {student.total_periodos_homo || 0} período(s) HOMO · {student.total_materias_homo || 0} materia(s)
                          </small>
                          <small>
                            Fechas HOMO: {student.primera_fecha_homo || '-'} a {student.ultima_fecha_homo || '-'}
                          </small>
                        </article>
                      )
                    })
                  ) : (
                    <p className="gestion-sis-homo-bulk__empty">Seleccione un estado o ajuste la búsqueda para ver estudiantes.</p>
                  )}
                </div>
              </div>

              <div className="gestion-sis-homo-bulk__toolbar">
                <button type="button" className="ghost-button" onClick={() => void loadPeriodChangeCatalog()} disabled={periodChangeLoading}>
                  {periodChangeLoading ? 'Actualizando...' : 'Actualizar estudiantes'}
                </button>
                <button type="button" className="ghost-button" onClick={() => void previewPeriodChange()} disabled={!periodChangeEstado || periodChangeLoading}>
                  Analizar migración
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={() => void applyPeriodChange()}
                  disabled={!periodChangeEstado || periodChangeSaving || (periodChangePreview?.summary?.migrar || 0) === 0}
                >
                  {periodChangeSaving ? 'Migrando...' : 'Migrar matrícula H a R'}
                </button>
              </div>

              {periodChangePreview ? (
                <>
                  <div className="gestion-sis-period-change__summary">
                    <article>
                      <span>Estado</span>
                      <strong>
                        {periodChangeCatalog?.estados?.find((estado) => estado.value === periodChangeEstado)?.label || periodChangeEstado || '-'}
                      </strong>
                      <small>
                        {periodChangeSelectedCedulas.length > 0
                          ? `${periodChangeSelectedCedulas.length} cédula(s) seleccionada(s)`
                          : periodChangePreview.summary?.student_filter
                            ? `Filtro: ${periodChangePreview.summary.student_filter}`
                            : 'Todo el estado seleccionado'}
                      </small>
                    </article>
                    <article>
                      <span>Períodos HOMO</span>
                      <strong>{periodChangePreview.summary?.periodos_homo_origen || 0}</strong>
                      <small>Detectados por matrícula</small>
                    </article>
                    <article>
                      <span>Ruta regular</span>
                      <strong>{periodChangePreview.summary?.periodos_regulares || periodChangePreview.target_periods?.length || 0} período(s)</strong>
                      <small>
                        {(periodChangePreview.target_periods || [periodChangePreview.target_period])
                          .filter(Boolean)
                          .map((period) => periodOptionLabel(period))
                          .join(' | ') || '-'}
                      </small>
                      <small>Sugerida por fechas de homologación</small>
                    </article>
                    <article>
                      <span>Estudiantes</span>
                      <strong>{periodChangePreview.summary?.estudiantes_origen || 0}</strong>
                    </article>
                    <article>
                      <span>Migran</span>
                      <strong>{periodChangePreview.summary?.migrar || 0}</strong>
                    </article>
                    <article>
                      <span>Duplicados</span>
                      <strong>{periodChangePreview.summary?.duplicados_destino || 0}</strong>
                    </article>
                    <article>
                      <span>Sin período</span>
                      <strong>{periodChangePreview.summary?.sin_periodo_destino || 0}</strong>
                    </article>
                  </div>

                  <div className="matricula-table-wrap gestion-sis-table-wrap excel-table-wrap">
                    <table className="matricula-table gestion-sis-table">
                      <thead>
                        <tr>
                          <th>Estudiante</th>
                          <th>Carrera / materia</th>
                          <th>Origen</th>
                          <th>Destino</th>
                          <th>Bloque</th>
                          <th>Notas que migran</th>
                          <th>Acción</th>
                          <th>Motivo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(periodChangePreview.items || []).length > 0 ? (
                          (periodChangePreview.items || []).map((item) => (
                            <tr key={`period-change-${item.row_id || `${item.codigo_estud}-${item.codigo_materia}`}`}>
                              <td>
                                <strong>{item.estudiante || '-'}</strong>
                                <small>{item.cedula || '-'}</small>
                              </td>
                              <td>
                                <strong>{item.carrera || '-'}</strong>
                                <small>{item.materia || item.codigo_materia || '-'}</small>
                              </td>
                              <td>{item.source_periodo || item.source_codigo_periodo || '-'}</td>
                              <td>{item.target_periodo || item.target_codigo_periodo || '-'}</td>
                              <td>{item.bloque_regular ? `Período ${item.bloque_regular}` : '-'}</td>
                              <td>
                                <strong>Final {gradeLabel(item.nota_migrada ?? item.promedio_final)}</strong>
                                <small>
                                  HOMO T/P: {gradeLabel(item.teoria_homo)} / {gradeLabel(item.practica_homo)}
                                </small>
                                <small>
                                  Regular P1/P2/P3: {gradeLabel(item.prom_p1)} / {gradeLabel(item.prom_p2)} / {gradeLabel(item.prom_p3)}
                                </small>
                              </td>
                              <td>
                                <span className={`gestion-sis-period-change__state ${item.accion === 'MIGRAR' ? 'is-ready' : 'is-blocked'}`}>
                                  {item.accion === 'MIGRAR'
                                    ? 'Migrar'
                                    : item.accion === 'EXCEPCION'
                                      ? 'Excepción'
                                      : item.accion === 'DUPLICADO_DESTINO'
                                        ? 'Ya existe'
                                        : item.accion === 'SIN_PERIODO_DESTINO'
                                          ? 'Sin período'
                                        : item.accion || '-'}
                                </span>
                              </td>
                              <td>{item.motivo || '-'}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={8}>No hay registros para revisar.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <p className="gestion-sis-homo-bulk__empty">
                  Ejecuta la vista previa para ver estudiantes, materias, duplicados y excepciones antes de migrar.
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="matricula-acad-form gestion-sis-filters">
                <label>
                  <span>{isEstadoInlineSection ? 'Buscar nombre o correo' : 'Buscar'}</span>
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={isEstadoInlineSection ? 'Nombre, correo, cédula o código' : 'Código, cédula, nombre o correo'}
                  />
                </label>
                {isStudentEstadoSection ? (
                  <label>
                    <span>Período</span>
                    <select value={estadoPeriodFilter} onChange={(event) => setEstadoPeriodFilter(event.target.value)}>
                      <option value="">-- Todos --</option>
                      {(estadoPeriodField?.options || []).map((option) => (
                        <option key={`estado-periodo-${option.value}`} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {isDocenteEstadoSection ? (
                  <label>
                    <span>Estado docente</span>
                    <select
                      value={docenteEstadoFilter}
                      onChange={(event) => setDocenteEstadoFilter(event.target.value)}
                    >
                      <option value="">Todos los docentes</option>
                      <option value="A">Activos</option>
                      <option value="P">Inactivos</option>
                    </select>
                  </label>
                ) : null}
              </div>

              <div className="teams-actions">
                <button type="button" onClick={() => void loadRows()} disabled={!selectedSection || listLoading}>
                  {listLoading ? 'Consultando...' : isEstadoInlineSection ? 'Filtrar' : 'Consultar'}
                </button>
                {canCreate ? (
                  <button type="button" onClick={startCreate} disabled={!selectedSection}>
                    Nuevo
                  </button>
                ) : null}
              </div>

              <div className="excel-toolbar gestion-sis-excel-toolbar">
                {!isEstadoInlineSection ? (
                  <label>
                    <span>Filtrar tabla</span>
                    <input
                      value={tableFilter}
                      onChange={(event) => setTableFilter(event.target.value)}
                      placeholder="Buscar solo en los datos mostrados"
                    />
                  </label>
                ) : null}
                <div>
                  <strong>{visibleRows.length}</strong>
                  <span>de {rows.length} registro(s)</span>
                </div>
                <small>
                  {isStudentEstadoSection
                    ? 'Cada cambio requiere motivo y documento de respaldo.'
                    : isEstadoInlineSection
                      ? 'Edita estado y descripción directamente en la fila.'
                      : 'Doble clic en una fila para editar'}
                </small>
              </div>

              <div className="matricula-table-wrap gestion-sis-table-wrap excel-table-wrap">
                <table className="matricula-table gestion-sis-table">
                  <thead>
                    <tr>
                      {hasIndexColumn ? <th>#</th> : null}
                      {tableFields.map((field) => (
                        <Fragment key={field.name}>
                          <th>{field.label}</th>
                          {isEstadoInlineSection && field.name === 'Estado' ? <th>Descripción</th> : null}
                          {isStudentEstadoSection && field.name === 'Estado' ? <th>Documento de respaldo</th> : null}
                        </Fragment>
                      ))}
                      <th>{isEstadoInlineSection ? 'Guardar' : isStudentProfileSection ? 'Ficha' : 'Editar'}</th>
                      {isDocenteEstadoSection ? <th>Observar</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.length > 0 ? (
                      visibleRows.map((row, rowIndex) => (
                        <tr
                          key={recordKey(row)}
                          className={selectedRecordKey === recordKey(row) ? 'excel-row--active' : ''}
                          onDoubleClick={isEstadoInlineSection ? undefined : () => void openRecord(selectedSectionKey, recordKey(row))}
                        >
                          {hasIndexColumn ? <td>{rowIndex + 1}</td> : null}
                          {tableFields.map((field) => {
                            if (isEstadoInlineSection && field.name === 'Estado') {
                              const options = isDocenteEstadoSection
                                ? docenteEstadoOptions
                                : estadoInlineField
                                  ? fieldOptions(estadoInlineField, row.Estado)
                                  : []
                              const estadoValue = inlineEstadoValue(row, 'Estado')
                              const selectValue = isDocenteEstadoSection && !['A', 'P'].includes(estadoValue.trim().toUpperCase())
                                ? ''
                                : estadoValue
                              return (
                                <Fragment key={`${recordKey(row)}-${field.name}`}>
                                  <td>
                                    <select
                                      className="gestion-sis-inline-select"
                                      value={selectValue}
                                      onChange={(event) => updateInlineEstado(row, { Estado: event.target.value })}
                                    >
                                      <option value="">Seleccione estado</option>
                                      {options.map((option) => (
                                        <option key={`${recordKey(row)}-estado-${option.value}`} value={option.value}>
                                          {option.label}
                                        </option>
                                      ))}
                                    </select>
                                  </td>
                                  <td>
                                    <input
                                      className="gestion-sis-inline-input"
                                      value={inlineEstadoValue(row, 'Informacion')}
                                      onChange={(event) => updateInlineEstado(row, { Informacion: event.target.value })}
                                      placeholder="Descripción u observación"
                                    />
                                  </td>
                                  {isStudentEstadoSection ? (
                                    <td>
                                      <label className="gestion-sis-state-document">
                                        <span>{inlineEstadoValues[recordKey(row)]?.Documento?.name || 'Seleccionar archivo'}</span>
                                        <input
                                          type="file"
                                          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                                          onChange={(event) => updateInlineEstado(row, { Documento: event.target.files?.[0] || null })}
                                        />
                                      </label>
                                      {row.DocumentoEstado ? (
                                        <a
                                          className="gestion-sis-state-document__current"
                                          href={String(row.DocumentoEstado)}
                                          target="_blank"
                                          rel="noreferrer"
                                        >
                                          Ver último respaldo
                                        </a>
                                      ) : null}
                                    </td>
                                  ) : null}
                                </Fragment>
                              )
                            }
                            return <td key={`${recordKey(row)}-${field.name}`}>{displayValue(field, row[field.name])}</td>
                          })}
                          <td>
                            {isEstadoInlineSection ? (
                              <button
                                type="button"
                                className="reporteria-row-action"
                                onClick={() => void saveInlineEstado(row)}
                                disabled={inlineSavingKey === recordKey(row)}
                              >
                                {inlineSavingKey === recordKey(row) ? 'Guardando...' : 'Guardar'}
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="reporteria-row-action"
                                onClick={() => void openRecord(selectedSectionKey, recordKey(row))}
                              >
                                {isStudentProfileSection ? 'Ver ficha' : 'Actualizar'}
                              </button>
                            )}
                          </td>
                          {isDocenteEstadoSection ? (
                            <td>
                              <button
                                type="button"
                                className="reporteria-row-action"
                                onClick={() => void openRecord(selectedSectionKey, recordKey(row))}
                              >
                                Observar
                              </button>
                            </td>
                          ) : null}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={tableColSpan}>{listLoading ? 'Consultando...' : 'Sin registros para mostrar.'}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </article>
      </section>

      {(mode === 'create' || selectedRecordKey) && selectedSection ? (
        <div className="matricula-modal-overlay">
          <article className={`matricula-modal gestion-sis-modal${isStudentProfileSection && mode !== 'create' ? ' gestion-sis-student-modal' : ''}`}>
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>
                  {isDocenteEstadoSection && mode !== 'create'
                    ? `Observar: ${formValues.apellidos_nombre || selectedSection.title}`
                    : isStudentProfileSection && mode !== 'create'
                      ? studentProfileEditing
                        ? `Actualizar estudiante: ${studentProfileName}`
                        : `Ficha estudiantil: ${studentProfileName}`
                    : mode === 'create'
                      ? `Nuevo registro: ${selectedSection.title}`
                      : `Editar: ${selectedSection.title}`}
                </h3>
                <span>
                  {detailLoading
                    ? 'Cargando registro...'
                    : isStudentProfileSection && mode !== 'create'
                      ? studentProfileEditing
                        ? 'Actualización de datos'
                        : 'Consulta académica'
                      : selectedSection.table}
                </span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedRecordKey('')
                  setFormValues({})
                  setStudentAcademicHistory(null)
                  setStudentAcademicHistoryError('')
                  setStudentProfileEditing(false)
                  setMode('edit')
                }}
              >
                Cerrar
              </button>
            </div>

            {isDocenteEstadoSection && mode !== 'create' ? (
              <>
                <div className="gestion-sis-observe-grid">
                  {(selectedSection.detail_fields || []).map((field) => (
                    <article key={field.name}>
                      <span>{field.label}</span>
                      <strong>{displayValue(field, formValues[field.name]) || '-'}</strong>
                    </article>
                  ))}
                </div>

                <div className="gestion-sis-observe-edit">
                  <div className="gestion-sis-form-helper">
                    <strong>Modificar estado del docente</strong>
                    <span>Actualice el estado y la descripción del usuario vinculado sin salir de esta subpantalla.</span>
                  </div>
                  <div className="matricula-acad-form gestion-sis-edit-form">
                    <label>
                      <span>Estado docente *</span>
                      <select
                        value={
                          ['A', 'P'].includes(inputValue(formValues.Estado).trim().toUpperCase())
                            ? inputValue(formValues.Estado)
                            : ''
                        }
                        onChange={(event) =>
                          setFormValues((current) => ({
                            ...current,
                            Estado: event.target.value,
                          }))
                        }
                      >
                        <option value="">Seleccione estado</option>
                        {docenteEstadoOptions.map((option) => (
                          <option key={`modal-docente-estado-${option.value}`} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="gestion-sis-field--wide">
                      <span>Descripción</span>
                      <textarea
                        value={inputValue(formValues.Informacion)}
                        onChange={(event) =>
                          setFormValues((current) => ({
                            ...current,
                            Informacion: event.target.value,
                          }))
                        }
                        placeholder="Descripción u observación"
                      />
                    </label>
                  </div>
                </div>
              </>
            ) : (
              <>
                {isStudentProfileSection && mode !== 'create' && !studentProfileEditing ? (
                  <section className="gestion-sis-student-summary" aria-label="Datos básicos del estudiante">
                    <article>
                      <span>Nombre del estudiante</span>
                      <strong>{studentProfileName}</strong>
                    </article>
                    <article>
                      <span>Número de cédula</span>
                      <strong>{studentProfileDocument}</strong>
                      <small>Documento protegido: se muestran únicamente los últimos 4 dígitos.</small>
                    </article>
                  </section>
                ) : (
                  <>
                    <div className="gestion-sis-form-helper">
                      <strong>
                        {mode === 'create'
                          ? 'Nuevo registro'
                          : isStudentProfileSection
                            ? 'Actualizar información del estudiante'
                            : 'Edicion del registro'}
                      </strong>
                      <span>
                        {isStudentProfileSection && mode !== 'create'
                          ? 'Complete los campos necesarios y guarde para regresar a la ficha estudiantil.'
                          : 'Complete los campos requeridos y guarda los cambios para actualizar la tabla.'}
                      </span>
                    </div>

                    <div className="matricula-acad-form gestion-sis-edit-form">
                      {currentFields.map((field) => {
                    if (mode === 'create' && selectedSection.key === 'usuarios' && field.name === 'fecha_ingreso') {
                      return null
                    }
                    const forceTextInput =
                      ['login', 'password', 'nombres', 'email', 'cedula'].includes(field.name) ||
                      (selectedSection.key === 'usuarios' && field.name === 'fecha_ingreso')
                    const options = forceTextInput ? [] : fieldOptions(field, formValues[field.name])
                    const renderSelect = shouldRenderSelect(selectedSection.key, field, options)
                    return (
                      <label key={field.name} className={field.type === 'textarea' ? 'gestion-sis-field--wide' : ''}>
                        <span>
                          {field.label}
                          {field.required ? ' *' : ''}
                        </span>
                        {renderSelect ? (
                          <select
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                                ...(selectedSection.key === 'materia_homo_textof' && field.name === 'cod_materia'
                                  ? {
                                      materia: materiaNameFromOption(
                                        options.find((option) => String(option.value) === event.target.value)?.label,
                                      ) || current.materia,
                                    }
                                  : {}),
                              }))
                            }
                          >
                            {field.required ? null : <option value="">Sin asignar</option>}
                            {options.map((option) => (
                              <option key={`${field.name}-${option.value}`} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : field.type === 'textarea' ? (
                          <textarea
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                              }))
                            }
                          />
                        ) : field.type === 'bool' ? (
                          <select
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value === 'true'),
                              }))
                            }
                          >
                            <option value="true">Sí</option>
                            <option value="false">No</option>
                          </select>
                        ) : (
                          <input
                            type={
                              field.name === 'password'
                                ? 'password'
                                : field.name === 'fecha_ingreso' || field.type === 'date'
                                  ? 'date'
                                  : field.type === 'number' || field.type === 'decimal'
                                    ? 'number'
                                    : 'text'
                            }
                            step={field.type === 'decimal' ? '0.01' : undefined}
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                              }))
                            }
                          />
                        )}
                      </label>
                    )
                      })}
                    </div>
                  </>
                )}

                {isStudentProfileSection && mode !== 'create' && !studentProfileEditing ? (
                  <section className="gestion-sis-student-history">
                    <div className="section-title">
                      <div>
                        <span>Trayectoria académica</span>
                        <h2>Períodos cursados y materias</h2>
                      </div>
                      <span>{academicHistory.length} período(s)</span>
                    </div>

                    {studentAcademicHistoryLoading ? (
                      <p className="empty-block">Consultando matrículas y materias cursadas...</p>
                    ) : studentAcademicHistoryError ? (
                      <div className="status-message status-message--error">{studentAcademicHistoryError}</div>
                    ) : academicHistory.length === 0 ? (
                      <p className="empty-block">No hay períodos ni materias registradas en CABECERA_MATRICULA y CARRERAXESTUD.</p>
                    ) : (
                      <div className="matricula-acad-history">
                        {academicHistory.map((period, index) => (
                          <details
                            className="matricula-acad-history-period"
                            open={index === 0 ? true : undefined}
                            key={`${period.codigo_periodo}-${period.cod_anio_basica}`}
                          >
                            <summary>
                              <div>
                                <strong>{period.periodo || period.codigo_periodo}</strong>
                                <span>{period.carrera || period.cod_anio_basica}</span>
                              </div>
                              <div className="matricula-acad-history-summary-meta">
                                <span>{valueOrDash(period.tipo_periodo)}</span>
                                <em>{period.total_materias || 0} materia(s)</em>
                              </div>
                            </summary>
                            <div className="matricula-acad-history-meta">
                              <div>
                                <span>Código de período</span>
                                <strong>{period.codigo_periodo}</strong>
                              </div>
                              <div>
                                <span>Fechas</span>
                                <strong>{valueOrDash(period.fecha_inicio)} a {valueOrDash(period.fecha_fin)}</strong>
                              </div>
                              <div>
                                <span>Num. matrícula</span>
                                <strong>{valueOrDash(period.num_matricula)}</strong>
                              </div>
                              <div>
                                <span>Jornada</span>
                                <strong>{valueOrDash(period.jornada)}</strong>
                              </div>
                            </div>
                            <div className="matricula-table-wrap matricula-acad-history-table">
                              <table className="matricula-table">
                                <thead>
                                  <tr>
                                    <th>Nivel</th>
                                    <th>Código</th>
                                    <th>Materia cursada</th>
                                    <th>Paralelo</th>
                                    <th>Tipo</th>
                                    <th>Nota final</th>
                                    <th>Resultado</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(period.materias || []).length === 0 ? (
                                    <tr>
                                      <td colSpan={7}>La matrícula no tiene materias asociadas en CARRERAXESTUD.</td>
                                    </tr>
                                  ) : (
                                    (period.materias || []).map((subject) => (
                                      <tr key={`${period.codigo_periodo}-${period.cod_anio_basica}-${subject.codigo_materia}`}>
                                        <td>{valueOrDash(subject.semestre)}</td>
                                        <td><strong>{subject.cod_materia || subject.codigo_materia}</strong></td>
                                        <td>{subject.nombre_materia}</td>
                                        <td>{valueOrDash(subject.paralelo)}</td>
                                        <td>{valueOrDash(subject.tipo_matricula)}</td>
                                        <td>{formatAcademicGrade(subject.promedio_final)}</td>
                                        <td>
                                          <span
                                            className={`status-pill ${
                                              subject.estado === 'Aprobada'
                                                ? 'is-ok'
                                                : subject.estado === 'Reprobada'
                                                  ? 'is-warning'
                                                  : 'is-muted'
                                            }`}
                                          >
                                            {subject.estado || 'Sin calificar'}
                                          </span>
                                        </td>
                                      </tr>
                                    ))
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </details>
                        ))}
                      </div>
                    )}
                  </section>
                ) : null}
              </>
            )}

            <div className="teams-actions gestion-sis-modal-actions">
              {isStudentProfileSection && mode !== 'create' ? (
                studentProfileEditing ? (
                  <>
                    <button
                      type="button"
                      className="gestion-sis-modal-actions__secondary"
                      onClick={() => void openRecord(selectedSection.key, selectedRecordKey)}
                      disabled={saving || detailLoading}
                    >
                      Volver a ficha
                    </button>
                    <button type="button" onClick={() => void saveRecord()} disabled={saving || detailLoading}>
                      {saving ? 'Guardando...' : 'Guardar cambios'}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setStudentProfileEditing(true)}
                    disabled={detailLoading}
                  >
                    Actualizar
                  </button>
                )
              ) : (
                <button type="button" onClick={() => void saveRecord()} disabled={saving || detailLoading}>
                  {saving ? 'Guardando...' : isDocenteEstadoSection && mode !== 'create' ? 'Guardar estado' : 'Guardar cambios'}
                </button>
              )}
            </div>
          </article>
        </div>
      ) : null}
    </>
  )
}
