import { useEffect, useEffectEvent, useMemo, useState } from 'react'

import {
  downloadLegacyReportWorkbook,
  fetchActiveLegacyGradeStudents,
  fetchLegacyReport,
  fetchLegacyReportsCatalog,
  fetchLegacyStudentGrades,
  updateLegacyStudentGrade,
} from '../../lib/api'
import {
  calculateHomologationGradeWithRecovery,
  calculateRegularGradeWithRecovery,
  constrainDecimalInput,
  parseBoundedDecimal,
} from '../../lib/gradeCalculation'
import type {
  LegacyActiveGradeStudent,
  LegacyReportOption,
  LegacyReportDefinition,
  LegacyReportFilters,
  LegacyReportKey,
  LegacyReportResponse,
  LegacyReportRow,
} from '../../types/app'

type ReporteriaIntegralViewProps = {
  displayName: string
  role?: string
  heading?: string
  eyebrow?: string
  individualMode?: boolean
  initialReportKey?: string
}

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

type GradeStudentSummary = {
  key: string
  studentCode: string
  label: string
  cedula: string
  carrera: string
  careerFilter: string
  enrollmentType: string
  total: number
  approved: number
  failed: number
  pending: number
}

type GradeStudentAccumulator = Omit<GradeStudentSummary, 'carrera'> & {
  careers: Set<string>
}

const gradeStudentPageSize = 12

const regularGradeSections = [
  { title: 'Parcial 1', task: 'p1_tareas', project: 'p1_proyectos', exam: 'p1_examen' },
  { title: 'Parcial 2', task: 'p2_tareas', project: 'p2_proyectos', exam: 'p2_examen' },
  { title: 'Parcial 3', task: 'p3_tareas', project: 'p3_proyectos', exam: 'p3_examen' },
] as const

const defaultReports: LegacyReportDefinition[] = [
  {
    key: 'notas_carrera_materia',
    title: 'Calificaciones de estudiantes',
    category: 'Académico',
    description: 'El padrón activo se carga completo; filtre por nombre y revise materias, calificaciones y docente responsable.',
    source_tables: ['CARRERAXESTUD', 'DATOS_ESTUD', 'CARRERAS', 'PENSUM', 'PERIODO', 'CARRERAXDOCENTE', 'DATOSDOCENTE'],
    filters: ['buscar'],
  },
  {
    key: 'provincia',
    title: 'Provincia',
    category: 'Reportería R/H',
    description: 'Totales por provincia separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'Provincias'],
    filters: ['anio', 'estado', 'buscar', 'limite'],
  },
  {
    key: 'provincia_genero',
    title: 'Provincia por género',
    category: 'Reportería R/H',
    description: 'Consolidado por provincia y género separado en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias', 'Sexo'],
    filters: ['anio', 'estado', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'provincia_carrera',
    title: 'Provincia por carreras',
    category: 'Reportería R/H',
    description: 'Consolidado por provincia y carrera separado en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias'],
    filters: ['anio', 'estado', 'carrera', 'buscar', 'limite'],
  },
  {
    key: 'carrera',
    title: 'Carrera',
    category: 'Reportería R/H',
    description: 'Totales por carrera separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS'],
    filters: ['anio', 'estado', 'carrera', 'buscar', 'limite'],
  },
  {
    key: 'graduados_2025',
    title: 'Graduados',
    category: 'Reportería R/H',
    description: 'Listado de graduados por año, provincia, carrera y género.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Provincias', 'ESTADO'],
    filters: ['anio', 'estado', 'carrera', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'genero',
    title: 'Género',
    category: 'Reportería R/H',
    description: 'Distribución por género separada en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'Sexo'],
    filters: ['anio', 'estado', 'genero', 'buscar', 'limite'],
  },
  {
    key: 'genero_docentes',
    title: 'Género de docentes',
    category: 'Docencia',
    description: 'Distribución de docentes por género y estado actual.',
    source_tables: ['DATOSDOCENTE', 'USUARIOS', 'Sexo'],
    filters: ['estado', 'genero', 'buscar', 'limite'],
    estado_options: [
      { value: 'A', label: 'Activo' },
      { value: 'P', label: 'Inactivo' },
    ],
  },
  {
    key: 'periodo',
    title: 'Período',
    category: 'Reportería R/H',
    description: 'Totales por período separados en Regular y Homologación.',
    source_tables: ['DATOS_ESTUD', 'CARRERAXESTUD', 'PERIODO', 'CARRERAS', 'Sexo'],
    filters: ['anio', 'estado', 'carrera', 'genero', 'buscar', 'limite'],
  },
]

const fallbackYearOptions: LegacyReportOption[] = [
  { value: '', label: 'Todos' },
  { value: '2026', label: '2026' },
  { value: '2025', label: '2025' },
  { value: '2024', label: '2024' },
  { value: '2023', label: '2023' },
]
const studentEstadoOptions: LegacyReportOption[] = [
  { value: '', label: 'Todos los estados' },
  { value: 'A', label: 'Activo' },
  { value: 'G', label: 'Graduado' },
  { value: 'P', label: 'Inactivo' },
  { value: 'R', label: 'Retirado' },
]
const genderOptions = [
  { value: '', label: 'Todos los géneros' },
  { value: 'Masculino', label: 'Masculino' },
  { value: 'Femenino', label: 'Femenino' },
]

function defaultEstadoForReport(reportKey: LegacyReportKey): string {
  return reportKey === 'graduados_2025' ? 'G' : ''
}

const ageRangeOrder = ['Menor de 18', '18 a 29', '30 a 40', '41 a 50', '51 a 60', '61 o más', 'Sin fecha']

type AgeRangeSummary = {
  range: string
  total: number
  scholarship: number
  withoutScholarship: number
  scholarshipPercentTotal: number
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function formatCell(value: LegacyReportRow[string]): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (typeof value === 'number') return new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(value)
  return String(value)
}

function columnLabel(column: string): string {
  const labels: Record<string, string> = {
    anio: 'Año',
    periodo: 'Período',
    periodo_codigo: 'Código período',
    genero: 'Género',
    cedula: 'Cédula',
    activos: 'Activos',
    inactivos: 'Inactivos',
    sin_estado: 'Sin estado',
  }
  if (labels[column]) return labels[column]
  return column
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (value) => value.toUpperCase())
}

function cellNumber(value: LegacyReportRow[string]): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const parsed = Number(String(value ?? '').replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

function rowText(row: LegacyReportRow, key: string): string {
  return String(row[key] ?? '').trim()
}

function normalizedSearchText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es')
    .trim()
}

function gradeStudentKey(row: LegacyReportRow): string {
  return rowText(row, 'estudiante_codigo') || rowText(row, 'cedula') || rowText(row, 'estudiante')
}

function gradeSubjectKey(row: LegacyReportRow): string {
  return [
    gradeStudentKey(row),
    rowText(row, 'carrera_codigo'),
    rowText(row, 'periodo_codigo'),
    rowText(row, 'materia_codigo'),
    rowText(row, 'paralelo'),
    rowText(row, 'num_matricula'),
    rowText(row, 'num_grupo'),
  ].join('|')
}

function gradeDraftValue(value: LegacyReportRow[string]): string {
  if (value === null || value === undefined || value === '') return ''
  const parsed = Number(String(value).replace(',', '.'))
  return Number.isFinite(parsed) ? String(parsed) : ''
}

function gradeDraftFromRow(row: LegacyReportRow): GradeDraft {
  return {
    teoria_homo: gradeDraftValue(row.teoria_homo),
    practica_homo: gradeDraftValue(row.practica_homo),
    p1_tareas: gradeDraftValue(row.p1_tareas),
    p1_proyectos: gradeDraftValue(row.p1_proyectos),
    p1_examen: gradeDraftValue(row.p1_examen),
    p2_tareas: gradeDraftValue(row.p2_tareas),
    p2_proyectos: gradeDraftValue(row.p2_proyectos),
    p2_examen: gradeDraftValue(row.p2_examen),
    p3_tareas: gradeDraftValue(row.p3_tareas),
    p3_proyectos: gradeDraftValue(row.p3_proyectos),
    p3_examen: gradeDraftValue(row.p3_examen),
    asistencia: gradeDraftValue(row.asistencia),
    recuperacion: gradeDraftValue(row.recuperacion),
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

function draftFinal(row: LegacyReportRow, draft: GradeDraft): number | null {
  if (isHomologationRow(row)) {
    const theory = nullableGrade(draft.teoria_homo)
    const practice = nullableGrade(draft.practica_homo)
    return calculateHomologationGradeWithRecovery(
      theory,
      practice,
      nullableGrade(draft.recuperacion),
    ).final
  }
  return draftRegularCalculation(draft).final
}

function requiredGradeIdentifier(row: LegacyReportRow, key: string): number | null {
  if (row[key] === null || row[key] === undefined || row[key] === '') return null
  const value = Number(row[key])
  return Number.isInteger(value) ? value : null
}

function canUpdateGradeRow(row: LegacyReportRow): boolean {
  return ['estudiante_codigo', 'carrera_codigo', 'periodo_codigo', 'materia_codigo', 'num_matricula', 'num_grupo']
    .every((key) => requiredGradeIdentifier(row, key) !== null) && Boolean(rowText(row, 'paralelo'))
}

function gradeValue(value: LegacyReportRow[string]): string {
  if (value === null || value === undefined || value === '') return '-'
  const numericValue = typeof value === 'number' ? value : Number(String(value).replace(',', '.'))
  if (Number.isFinite(numericValue)) {
    return new Intl.NumberFormat('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(numericValue)
  }
  return String(value)
}

function isHomologationRow(row?: LegacyReportRow | null): boolean {
  if (!row) return false
  return [row.esquema, row.tipo_matricula, row.periodo]
    .map((value) => String(value ?? '').trim().toUpperCase())
    .some((value) => value === 'H' || value.includes('HOMO'))
}

function isTotalColumn(column: string): boolean {
  const normalized = column.toLowerCase()
  if (normalized.includes('codigo') || normalized.includes('cedula') || normalized === 'anio') return false
  return (
    normalized === 'regular' ||
    normalized === 'homologacion' ||
    normalized === 'activos' ||
    normalized === 'inactivos' ||
    normalized === 'sin_estado' ||
    normalized === 'total' ||
    normalized === 'cantidad' ||
    normalized === 'graduados' ||
    normalized.startsWith('total_') ||
    normalized.endsWith('_total') ||
    normalized.includes('total_estudiantes')
  )
}

function ageRangeSortValue(range: string): number {
  const index = ageRangeOrder.indexOf(range)
  return index >= 0 ? index : ageRangeOrder.length
}

function downloadBlob(blob: Blob, reportKey: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `reporteria-integral-${reportKey}-${new Date().toISOString().slice(0, 10)}.xlsx`
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function ReporteriaIntegralView({
  displayName,
  role = '',
  heading = 'Reportes operativos',
  eyebrow = 'Reporteria',
  individualMode = false,
  initialReportKey = '',
}: Readonly<ReporteriaIntegralViewProps>) {
  const [reports, setReports] = useState<LegacyReportDefinition[]>(defaultReports)
  const [periodOptions, setPeriodOptions] = useState<LegacyReportOption[]>([])
  const [careerOptions, setCareerOptions] = useState<LegacyReportOption[]>([])
  const [yearOptions, setYearOptions] = useState<LegacyReportOption[]>(fallbackYearOptions)
  const [reportKey, setReportKey] = useState<LegacyReportKey>(
    (initialReportKey as LegacyReportKey) || 'provincia_genero',
  )
  const [appliedInitialReport, setAppliedInitialReport] = useState('')
  const [anio, setAnio] = useState('')
  const [periodos, setPeriodos] = useState<string[]>([])
  const [carrera, setCarrera] = useState('')
  const [estado, setEstado] = useState(defaultEstadoForReport((initialReportKey as LegacyReportKey) || 'provincia_genero'))
  const [genero, setGenero] = useState('')
  const [buscar, setBuscar] = useState('')
  const [limit, setLimit] = useState(500)
  const [loading, setLoading] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState<LegacyReportResponse | null>(null)
  const [tableFilter, setTableFilter] = useState('')
  const [selectedGradeStudentKey, setSelectedGradeStudentKey] = useState('')
  const [gradeSubjectModalOpen, setGradeSubjectModalOpen] = useState(false)
  const [selectedGradeSubjectKey, setSelectedGradeSubjectKey] = useState('')
  const [gradeStudentPage, setGradeStudentPage] = useState(1)
  const [gradeEditing, setGradeEditing] = useState(false)
  const [gradeDraft, setGradeDraft] = useState<GradeDraft | null>(null)
  const [gradeSaving, setGradeSaving] = useState(false)
  const [gradeSaveError, setGradeSaveError] = useState('')
  const [gradeSaveMessage, setGradeSaveMessage] = useState('')
  const [activeGradeStudents, setActiveGradeStudents] = useState<LegacyActiveGradeStudent[]>([])
  const [studentGradeRows, setStudentGradeRows] = useState<LegacyReportRow[]>([])
  const [gradeDetailLoading, setGradeDetailLoading] = useState(false)
  const [gradeDetailError, setGradeDetailError] = useState('')

  const selectedReport = useMemo(
    () => reports.find((report) => report.key === reportKey) || reports[0],
    [reportKey, reports],
  )
  const directReportMode = Boolean(initialReportKey)
  const enabledFilters = useMemo(
    () => reportKey === 'notas_carrera_materia'
      ? new Set(['buscar'])
      : new Set(selectedReport?.filters?.length ? selectedReport.filters : ['anio', 'carrera', 'genero', 'buscar', 'limite']),
    [reportKey, selectedReport],
  )
  const columns = useMemo(() => data?.columns || [], [data?.columns])
  const rows = useMemo(() => data?.rows || [], [data?.rows])
  const isGradesReport = reportKey === 'notas_carrera_materia'
  const ageRangeSummary = useMemo((): AgeRangeSummary[] => {
    if (reportKey !== 'becas_edades') return []
    const summary = new Map<string, AgeRangeSummary>()
    for (const row of rows) {
      const range = String(row.rango_edad || 'Sin fecha')
      const current =
        summary.get(range) ||
        {
          range,
          total: 0,
          scholarship: 0,
          withoutScholarship: 0,
          scholarshipPercentTotal: 0,
        }
      const scholarshipName = String(row.tipo_beca || '').trim()
      const hasScholarship = scholarshipName !== '' && scholarshipName.toLowerCase() !== 'sin beca'
      current.total += 1
      if (hasScholarship) {
        current.scholarship += 1
        current.scholarshipPercentTotal += cellNumber(row.porcentaje_beca)
      } else {
        current.withoutScholarship += 1
      }
      summary.set(range, current)
    }
    return Array.from(summary.values()).sort((left, right) => ageRangeSortValue(left.range) - ageRangeSortValue(right.range))
  }, [reportKey, rows])
  const ageRangeMaxTotal = useMemo(
    () => Math.max(1, ...ageRangeSummary.map((item) => item.total)),
    [ageRangeSummary],
  )
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      columns.some((column) => formatCell(row[column]).toLowerCase().includes(needle)),
    )
  }, [columns, rows, tableFilter])
  const gradeStudents = useMemo((): GradeStudentSummary[] => {
    const grouped = new Map<string, GradeStudentAccumulator>()

    for (const student of activeGradeStudents) {
      const studentCode = String(student.estudiante_codigo || '').trim()
      const cedula = String(student.cedula || '').trim()
      const label = String(student.estudiante || '').trim() || 'Estudiante sin nombre'
      const careerFilter = String(student.carrera || '').trim()
      const enrollmentType = String(student.tipo_matricula || '').trim().toUpperCase()
      const key = String(student.registro_clave || '').trim()
        || [studentCode || cedula || normalizedSearchText(label), normalizedSearchText(careerFilter), enrollmentType].join('|')
      if (!key) continue

      const taggedCareer = careerFilter && enrollmentType
        ? `${careerFilter} (${enrollmentType})`
        : careerFilter
      const current = grouped.get(key)

      if (current) {
        if (taggedCareer) current.careers.add(taggedCareer)
        current.total += Number(student.total_materias || 0)
        current.approved += Number(student.aprobadas || 0)
        current.failed += Number(student.reprobadas || 0)
        current.pending += Number(student.pendientes || 0)
        continue
      }

      grouped.set(key, {
        key,
        studentCode,
        label,
        cedula,
        careers: new Set(taggedCareer ? [taggedCareer] : []),
        careerFilter,
        enrollmentType,
        total: Number(student.total_materias || 0),
        approved: Number(student.aprobadas || 0),
        failed: Number(student.reprobadas || 0),
        pending: Number(student.pendientes || 0),
      })
    }

    return Array.from(grouped.values())
      .map(({ careers, ...student }) => ({ ...student, carrera: Array.from(careers).join(' / ') }))
      .sort((left, right) => left.label.localeCompare(right.label, 'es'))
  }, [activeGradeStudents])
  const visibleGradeStudents = useMemo(() => {
    const needle = normalizedSearchText(buscar)
    if (!needle) return gradeStudents
    return gradeStudents.filter((student) => normalizedSearchText(student.label).includes(needle))
  }, [buscar, gradeStudents])
  const gradeStudentPageCount = Math.max(1, Math.ceil(visibleGradeStudents.length / gradeStudentPageSize))
  const pagedGradeStudents = useMemo(() => {
    const safePage = Math.min(gradeStudentPage, gradeStudentPageCount)
    const start = (safePage - 1) * gradeStudentPageSize
    return visibleGradeStudents.slice(start, start + gradeStudentPageSize)
  }, [gradeStudentPage, gradeStudentPageCount, visibleGradeStudents])
  const selectedGradeStudent = useMemo(
    () => gradeStudents.find((student) => student.key === selectedGradeStudentKey) || null,
    [gradeStudents, selectedGradeStudentKey],
  )
  const selectedStudentSubjects = useMemo(() => {
    if (!selectedGradeStudentKey) return []
    return [...studentGradeRows]
      .sort((left, right) =>
        `${rowText(left, 'semestre').padStart(2, '0')} ${rowText(left, 'materia')}`.localeCompare(
          `${rowText(right, 'semestre').padStart(2, '0')} ${rowText(right, 'materia')}`,
          'es',
        ),
      )
  }, [studentGradeRows, selectedGradeStudentKey])
  const selectedGradeSubject = useMemo(
    () =>
      selectedStudentSubjects.find((row) => {
        return gradeSubjectKey(row) === selectedGradeSubjectKey
      }) || selectedStudentSubjects[0] || null,
    [selectedGradeSubjectKey, selectedStudentSubjects],
  )
  const canEditGrades = ['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA'].includes(role.trim().toUpperCase())
  const gradePreviewCalculation = selectedGradeSubject && gradeDraft && !isHomologationRow(selectedGradeSubject)
    ? draftRegularCalculation(gradeDraft)
    : null
  const gradePreviewFinal = selectedGradeSubject && gradeDraft ? draftFinal(selectedGradeSubject, gradeDraft) : null
  const totalsRow = useMemo(() => {
    if (!visibleRows.length || !columns.length) return null
    const totals: Record<string, number> = {}
    let hasTotals = false

    for (const column of columns) {
      if (!isTotalColumn(column)) continue
      const columnTotal = visibleRows.reduce((sum, row) => sum + cellNumber(row[column]), 0)
      totals[column] = columnTotal
      hasTotals = true
    }

    return hasTotals ? totals : null
  }, [columns, visibleRows])
  const totalSummaryItems = useMemo(
    () =>
      totalsRow
        ? columns
            .filter((column) => isTotalColumn(column))
            .map((column) => ({
              key: column,
              label: columnLabel(column),
              value: totalsRow[column] ?? 0,
            }))
        : [],
    [columns, totalsRow],
  )
  const sourceTables = selectedReport?.source_tables || []
  const estadoOptions = selectedReport?.estado_options?.length ? selectedReport.estado_options : studentEstadoOptions
  const estadoLabel = estadoOptions.find((option) => option.value === estado)?.label || estado
  const selectedPeriodLabels = useMemo(
    () =>
      periodos.map((value) => periodOptions.find((option) => option.value === value)?.label || value),
    [periodOptions, periodos],
  )
  const activeFilters = [
    enabledFilters.has('anio') ? `Año ${anio || 'Todos'}` : '',
    enabledFilters.has('periodo') && periodos.length === 1 ? `Período ${selectedPeriodLabels[0]}` : '',
    enabledFilters.has('periodo') && periodos.length > 1 ? `${periodos.length} períodos seleccionados` : '',
    enabledFilters.has('carrera') && carrera ? `Carrera ${careerOptions.find((option) => option.value === carrera)?.label || carrera}` : '',
    enabledFilters.has('estado') && estado ? `Estado ${estadoLabel}` : '',
    enabledFilters.has('genero') ? `Género ${genero || 'Todos'}` : '',
    enabledFilters.has('buscar') && buscar ? `Búsqueda "${buscar}"` : '',
  ].filter(Boolean)

  function filtersForReport(nextReportKey: LegacyReportKey) {
    if (nextReportKey === 'notas_carrera_materia') return new Set(['buscar'])
    const report = reports.find((item) => item.key === nextReportKey) || selectedReport
    return new Set(report?.filters?.length ? report.filters : ['anio', 'carrera', 'genero', 'buscar', 'limite'])
  }

  function filters(nextReportKey: LegacyReportKey = reportKey, nextEstado: string = estado): LegacyReportFilters {
    const nextEnabledFilters = filtersForReport(nextReportKey)
    return {
      reportKey: nextReportKey,
      anio: nextEnabledFilters.has('anio') ? anio.trim() : '',
      periodo: nextEnabledFilters.has('periodo') && periodos.length === 1 ? periodos[0] : '',
      periodos: nextEnabledFilters.has('periodo') ? periodos : [],
      carrera: nextEnabledFilters.has('carrera') ? carrera.trim() : '',
      estado: nextEnabledFilters.has('estado') ? nextEstado.trim() : '',
      genero: nextEnabledFilters.has('genero') ? genero.trim() : '',
      buscar: nextEnabledFilters.has('buscar') ? buscar.trim() : '',
      limit: nextReportKey === 'notas_carrera_materia' ? 10000 : limit,
    }
  }

  function validateFiltersForReport(nextReportKey: LegacyReportKey) {
    if (nextReportKey === 'estud_per_c_m' && periodos.length === 0) {
      return 'Seleccione un período para consultar estudiantes, carreras y materias matriculadas.'
    }
    return ''
  }

  function togglePeriod(value: string) {
    if (reportKey === 'notas_carrera_materia') {
      setPeriodos((current) => (current.includes(value) ? [] : [value]))
      setSelectedGradeStudentKey('')
      setSelectedGradeSubjectKey('')
      setGradeStudentPage(1)
      return
    }
    setPeriodos((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    )
  }

  function selectAllPeriods() {
    setPeriodos(periodOptions.map((option) => option.value))
  }

  async function loadActiveGradeStudents(silent = false) {
    if (!silent) setLoading(true)
    setError('')
    try {
      const payload = await fetchActiveLegacyGradeStudents()
      setActiveGradeStudents(payload.items || [])
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el padrón de estudiantes activos')
      if (!silent) setActiveGradeStudents([])
    } finally {
      if (!silent) setLoading(false)
    }
  }

  async function openGradeStudent(student: GradeStudentSummary) {
    setSelectedGradeStudentKey(student.key)
    setSelectedGradeSubjectKey('')
    setStudentGradeRows([])
    setGradeEditing(false)
    setGradeDraft(null)
    setGradeSaveError('')
    setGradeSaveMessage('')
    setGradeDetailError('')
    setGradeSubjectModalOpen(true)
    setGradeDetailLoading(true)
    try {
      if (!student.studentCode) throw new Error('No se encontró el código académico del estudiante')
      const payload = await fetchLegacyStudentGrades(student.studentCode, student.careerFilter, student.enrollmentType)
      const subjects = payload.rows || []
      setStudentGradeRows(subjects)
      setSelectedGradeSubjectKey(subjects.length ? gradeSubjectKey(subjects[0]) : '')
    } catch (apiError) {
      setGradeDetailError(apiError instanceof Error ? apiError.message : 'No se pudieron cargar las calificaciones del estudiante')
    } finally {
      setGradeDetailLoading(false)
    }
  }

  function selectGradeSubject(row: LegacyReportRow) {
    setSelectedGradeSubjectKey(gradeSubjectKey(row))
    setGradeEditing(false)
    setGradeDraft(null)
    setGradeSaveError('')
    setGradeSaveMessage('')
  }

  function startGradeEditing() {
    if (!selectedGradeSubject || !canUpdateGradeRow(selectedGradeSubject)) return
    setGradeDraft(gradeDraftFromRow(selectedGradeSubject))
    setGradeEditing(true)
    setGradeSaveError('')
    setGradeSaveMessage('')
  }

  function updateGradeDraft(field: keyof GradeDraft, value: string) {
    const constrained = constrainDecimalInput(value, field === 'asistencia' ? 100 : 10)
    if (constrained === null) return
    setGradeDraft((current) => current ? { ...current, [field]: constrained } : current)
  }

  async function saveSelectedGrade() {
    if (!selectedGradeSubject || !gradeDraft) return
    const identifiers = {
      codigo_estud: requiredGradeIdentifier(selectedGradeSubject, 'estudiante_codigo'),
      cod_anio_basica: requiredGradeIdentifier(selectedGradeSubject, 'carrera_codigo'),
      codigo_periodo: requiredGradeIdentifier(selectedGradeSubject, 'periodo_codigo'),
      codigo_materia: requiredGradeIdentifier(selectedGradeSubject, 'materia_codigo'),
      num_matricula: requiredGradeIdentifier(selectedGradeSubject, 'num_matricula'),
      num_grupo: requiredGradeIdentifier(selectedGradeSubject, 'num_grupo'),
    }
    if (Object.values(identifiers).some((value) => value === null) || !rowText(selectedGradeSubject, 'paralelo')) {
      setGradeSaveError('No se puede aislar esta matrícula. Actualice la consulta y vuelva a seleccionar la materia.')
      return
    }

    setGradeSaving(true)
    setGradeSaveError('')
    setGradeSaveMessage('')
    try {
      const response = await updateLegacyStudentGrade({
        codigo_estud: identifiers.codigo_estud!,
        cod_anio_basica: identifiers.cod_anio_basica!,
        codigo_periodo: identifiers.codigo_periodo!,
        codigo_materia: identifiers.codigo_materia!,
        paralelo: rowText(selectedGradeSubject, 'paralelo'),
        num_matricula: identifiers.num_matricula!,
        num_grupo: identifiers.num_grupo!,
        es_homologacion: isHomologationRow(selectedGradeSubject),
        teoria_homo: parseBoundedDecimal(gradeDraft.teoria_homo, 10, 'La nota teórica'),
        practica_homo: parseBoundedDecimal(gradeDraft.practica_homo, 10, 'La nota práctica'),
        p1_tareas: parseBoundedDecimal(gradeDraft.p1_tareas, 10, 'Tareas del parcial 1'),
        p1_proyectos: parseBoundedDecimal(gradeDraft.p1_proyectos, 10, 'Proyectos del parcial 1'),
        p1_examen: parseBoundedDecimal(gradeDraft.p1_examen, 10, 'Examen del parcial 1'),
        p2_tareas: parseBoundedDecimal(gradeDraft.p2_tareas, 10, 'Tareas del parcial 2'),
        p2_proyectos: parseBoundedDecimal(gradeDraft.p2_proyectos, 10, 'Proyectos del parcial 2'),
        p2_examen: parseBoundedDecimal(gradeDraft.p2_examen, 10, 'Examen del parcial 2'),
        p3_tareas: parseBoundedDecimal(gradeDraft.p3_tareas, 10, 'Tareas del parcial 3'),
        p3_proyectos: parseBoundedDecimal(gradeDraft.p3_proyectos, 10, 'Proyectos del parcial 3'),
        p3_examen: parseBoundedDecimal(gradeDraft.p3_examen, 10, 'Examen del parcial 3'),
        asistencia: parseBoundedDecimal(gradeDraft.asistencia, 100, 'La asistencia'),
        recuperacion: parseBoundedDecimal(gradeDraft.recuperacion, 10, 'La recuperación'),
      })
      if (!selectedGradeStudent?.studentCode) throw new Error('No se encontró el código académico del estudiante')
      const refreshed = await fetchLegacyStudentGrades(
        selectedGradeStudent.studentCode,
        selectedGradeStudent.careerFilter,
        selectedGradeStudent.enrollmentType,
      )
      setStudentGradeRows(refreshed.rows || [])
      await loadActiveGradeStudents(true)
      setGradeEditing(false)
      setGradeDraft(null)
      setGradeSaveMessage(response.message || 'Calificaciones actualizadas correctamente.')
    } catch (apiError) {
      setGradeSaveError(apiError instanceof Error ? apiError.message : 'No se pudieron actualizar las calificaciones')
    } finally {
      setGradeSaving(false)
    }
  }

  async function loadReport(nextReportKey: LegacyReportKey = reportKey, nextEstado: string = estado) {
    setError('')
    if (nextReportKey === 'notas_carrera_materia') {
      await loadActiveGradeStudents()
      setSelectedGradeStudentKey('')
      setSelectedGradeSubjectKey('')
      setStudentGradeRows([])
      setGradeSubjectModalOpen(false)
      setGradeStudentPage(1)
      return
    }
    const validationMessage = validateFiltersForReport(nextReportKey)
    if (validationMessage) {
      setData(null)
      setError(validationMessage)
      return
    }
    setLoading(true)
    try {
      const payload = await fetchLegacyReport(filters(nextReportKey, nextEstado))
      setData(payload)
      setSelectedGradeStudentKey('')
      setSelectedGradeSubjectKey('')
      setGradeSubjectModalOpen(false)
      setGradeStudentPage(1)
      setTableFilter('')
      setGradeEditing(false)
      setGradeDraft(null)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Error generando el reporte integral')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const loadReportEffect = useEffectEvent(loadReport)
  const filtersEffect = useEffectEvent(filters)

  async function exportReport() {
    setError('')
    const validationMessage = validateFiltersForReport(reportKey)
    if (validationMessage) {
      setError(validationMessage)
      return
    }
    setDownloadLoading(true)
    try {
      const blob = await downloadLegacyReportWorkbook({
        ...filters(),
        limit: isGradesReport ? 10000 : Math.max(limit, 5000),
      })
      downloadBlob(blob, reportKey)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Error exportando el reporte integral')
    } finally {
      setDownloadLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      try {
        const payload = await fetchLegacyReportsCatalog()
        if (cancelled) return
        if (payload.reports?.length) {
          setReports(payload.reports)
        }
        setPeriodOptions(payload.periodos || [])
        setCareerOptions(payload.carreras || [])
        const catalogYears = (payload.anios || [])
          .filter((option) => option.value)
          .map((option) => ({ value: option.value, label: option.label || option.value }))
        setYearOptions(catalogYears.length ? [{ value: '', label: 'Todos' }, ...catalogYears] : fallbackYearOptions)
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'Error cargando catálogo integral')
        }
      } finally {
        if (!cancelled) {
          setCatalogLoading(false)
        }
      }
    }

    void loadCatalog()
    void loadReportEffect()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!initialReportKey || initialReportKey === appliedInitialReport) return
    const exists = reports.some((report) => report.key === initialReportKey)
    if (!exists) return
    const nextReportKey = initialReportKey as LegacyReportKey
    setAppliedInitialReport(initialReportKey)
    setReportKey(nextReportKey)
    setAnio('')
    const nextEstado = defaultEstadoForReport(nextReportKey)
    setEstado(nextEstado)
    setGenero('')
    setData(null)
    void loadReportEffect(nextReportKey, nextEstado)
  }, [appliedInitialReport, initialReportKey, reports])

  useEffect(() => {
    if (reportKey === 'estud_per_c_m' && periodos.length === 0) return

    const refreshReport = async () => {
      try {
        if (reportKey === 'notas_carrera_materia') {
          const payload = await fetchActiveLegacyGradeStudents()
          setActiveGradeStudents(payload.items || [])
        } else {
          const payload = await fetchLegacyReport(filtersEffect())
          setData(payload)
        }
        setError('')
      } catch {
        // La consulta manual conserva el mensaje detallado; la actualización silenciosa reintentará después.
      }
    }
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') void refreshReport()
    }

    const intervalId = window.setInterval(() => void refreshReport(), 30000)
    window.addEventListener('focus', refreshOnVisible)
    document.addEventListener('visibilitychange', refreshOnVisible)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshOnVisible)
      document.removeEventListener('visibilitychange', refreshOnVisible)
    }
  }, [anio, buscar, carrera, estado, genero, limit, periodos, reportKey])

  useEffect(() => {
    if (!selectedGradeStudentKey && gradeStudents.length === 1) {
      setSelectedGradeStudentKey(gradeStudents[0].key)
    }
    if (selectedGradeStudentKey && !gradeStudents.some((student) => student.key === selectedGradeStudentKey)) {
      setSelectedGradeStudentKey('')
      setSelectedGradeSubjectKey('')
    }
  }, [gradeStudents, selectedGradeStudentKey])

  useEffect(() => {
    if (!selectedGradeSubjectKey && selectedStudentSubjects.length === 1) {
      const row = selectedStudentSubjects[0]
      setSelectedGradeSubjectKey(gradeSubjectKey(row))
    }
    if (
      selectedGradeSubjectKey &&
      !selectedStudentSubjects.some((row) => gradeSubjectKey(row) === selectedGradeSubjectKey)
    ) {
      setSelectedGradeSubjectKey('')
    }
  }, [selectedGradeSubjectKey, selectedStudentSubjects])

  useEffect(() => {
    setGradeStudentPage(1)
  }, [buscar])

  useEffect(() => {
    if (gradeStudentPage > gradeStudentPageCount) setGradeStudentPage(gradeStudentPageCount)
  }, [gradeStudentPage, gradeStudentPageCount])

  useEffect(() => {
    if (reportKey !== 'graduados_2025') return
    const timeout = window.setTimeout(() => {
      void loadReportEffect('graduados_2025', estado)
    }, 250)

    return () => window.clearTimeout(timeout)
  }, [reportKey, anio, carrera, genero, estado])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{heading}</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Reporteria</span>
            </div>
          </div>
        </div>
      </header>

      <section className={`student-grid student-grid--content reporteria-integral-grid ${directReportMode ? 'reporteria-integral-grid--single' : ''}`}>
        <article className="student-card student-card--wide reporteria-integral-panel">
          <div className="card-head">
            <h3>Consulta y exportacion</h3>
            <span>{catalogLoading ? 'Cargando catálogo...' : selectedReport?.category || 'Reporte'}</span>
          </div>

          {individualMode && !directReportMode ? (
            <div className="reporteria-individual-list">
              {reports.map((report) => (
                <button
                  key={report.key}
                  type="button"
                  className={report.key === reportKey ? 'reporteria-individual-list__item reporteria-individual-list__item--active' : 'reporteria-individual-list__item'}
                  onClick={() => {
                    setReportKey(report.key)
                    setAnio('')
                    const nextEstado = defaultEstadoForReport(report.key)
                    setEstado(nextEstado)
                    setGenero('')
                    setBuscar('')
                    if (report.key === 'notas_carrera_materia') {
                      setPeriodos([])
                      setCarrera('')
                    }
                    setData(null)
                    void loadReport(report.key, nextEstado)
                  }}
                >
                  <strong>{report.title}</strong>
                  <span>{report.category || 'Reporte'}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className={`matricula-acad-form reporteria-integral-form ${directReportMode ? 'reporteria-integral-form--direct' : ''}`}>
            {!directReportMode ? (
              <label>
                <span>Consulta</span>
                <select
                  value={reportKey}
                  onChange={(event) => {
                    const nextReportKey = event.target.value as LegacyReportKey
                    const nextEstado = defaultEstadoForReport(nextReportKey)
                    setReportKey(nextReportKey)
                    setAnio('')
                    setEstado(nextEstado)
                    setGenero('')
                    setBuscar('')
                    if (nextReportKey === 'notas_carrera_materia') {
                      setPeriodos([])
                      setCarrera('')
                      setData(null)
                    }
                    void loadReport(nextReportKey, nextEstado)
                  }}
                >
                  {reports.map((report) => (
                    <option key={report.key} value={report.key}>
                      {report.title}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('anio') ? (
              <label className="reporteria-year-filter">
                <span>Año</span>
                <select value={anio} onChange={(event) => setAnio(event.target.value)}>
                  {yearOptions.map((option) => (
                    <option key={option.value || 'todos'} value={option.value}>
                      {option.label || option.value || 'Todos'}
                    </option>
                  ))}
                </select>
                <small>{anio ? `Año seleccionado: ${anio}` : 'Año seleccionado: Todos'}</small>
              </label>
            ) : null}
            {enabledFilters.has('periodo') ? (
              <label>
                <span>Período</span>
                {isGradesReport && periodOptions.length > 0 ? (
                  <select
                    value={periodos[0] || ''}
                    onChange={(event) => {
                      setPeriodos(event.target.value ? [event.target.value] : [])
                      setSelectedGradeStudentKey('')
                      setSelectedGradeSubjectKey('')
                      setGradeSubjectModalOpen(false)
                    }}
                  >
                    <option value="">Seleccione un período</option>
                    {periodOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                ) : periodOptions.length > 0 ? (
                  <div className="report-period-picker">
                    <div className="report-period-toolbar">
                      <strong>{periodos.length ? `${periodos.length} seleccionado(s)` : isGradesReport ? 'Seleccione un período' : 'Todos los períodos'}</strong>
                      {!isGradesReport ? (
                        <button type="button" onClick={selectAllPeriods}>
                          Seleccionar todos
                        </button>
                      ) : null}
                      <button type="button" onClick={() => setPeriodos([])}>
                        Limpiar
                      </button>
                    </div>
                    <div className="report-period-options">
                      {periodOptions.map((option) => (
                        <label key={option.value} className="report-period-option">
                          <input
                            type="checkbox"
                            checked={periodos.includes(option.value)}
                            onChange={() => togglePeriod(option.value)}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : (
                  <textarea
                    value={periodos.join('\n')}
                    onChange={(event) =>
                      setPeriodos(event.target.value.split(/[\n,]+/).map((value) => value.trim()).filter(Boolean))
                    }
                    placeholder="Códigos de período, uno por línea"
                  />
                )}
              </label>
            ) : null}
            {enabledFilters.has('carrera') ? (
              <label>
                <span>Carrera</span>
                {careerOptions.length > 0 ? (
                  <select value={carrera} onChange={(event) => setCarrera(event.target.value)}>
                    <option value="">Todas las carreras</option>
                    {careerOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input value={carrera} onChange={(event) => setCarrera(event.target.value)} placeholder="Código carrera" />
                )}
              </label>
            ) : null}
            {enabledFilters.has('estado') ? (
              <label>
                <span>Estado</span>
                <select value={estado} onChange={(event) => setEstado(event.target.value)}>
                  <option value="">Todos</option>
                  {estadoOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('genero') ? (
              <label>
                <span>Género</span>
                <select value={genero} onChange={(event) => setGenero(event.target.value)}>
                  {genderOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {enabledFilters.has('buscar') ? (
              <label>
                <span>{isGradesReport ? 'Nombre del estudiante' : 'Buscar'}</span>
                <input
                  value={buscar}
                  onChange={(event) => setBuscar(event.target.value)}
                  placeholder={
                    reportKey === 'notas_carrera_materia'
                      ? 'Escriba el nombre o apellido del estudiante'
                      : reportKey === 'genero_docentes'
                        ? 'Docente, cédula o correo'
                        : 'Cédula, estudiante, provincia, carrera o período'
                  }
                />
              </label>
            ) : null}
            {enabledFilters.has('limite') && !isGradesReport ? (
              <label>
                <span>Límite</span>
                <input
                  type="number"
                  min={1}
                  max={10000}
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value) || 500)}
                />
              </label>
            ) : null}
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void loadReport()} disabled={loading}>
              {loading ? 'Consultando...' : isGradesReport ? 'Actualizar listado' : 'Consultar'}
            </button>
            {!isGradesReport ? (
              <button type="button" onClick={() => void exportReport()} disabled={downloadLoading || loading}>
                {downloadLoading ? 'Exportando...' : 'Exportar Excel'}
              </button>
            ) : null}
          </div>

          {!directReportMode && selectedReport?.description ? <p className="reporteria-integral-description">{selectedReport.description}</p> : null}
          {!directReportMode && activeFilters.length > 0 ? <p className="teams-message">{activeFilters.join(' / ')}</p> : null}
          {data?.source && !isGradesReport ? <p className="teams-message">Fuente actual: {data.source}</p> : null}
          {error ? <p className="teams-error">{error}</p> : null}

          {reportKey === 'becas_edades' && ageRangeSummary.length > 0 ? (
            <div className="reporteria-age-chart" aria-label="Comparativo por rangos de edad">
              <div className="reporteria-age-chart__head">
                <div>
                  <strong>Comparativo por rangos de edad</strong>
                  <span>{formatNumber(rows.length)} estudiante(s) con edad calculada o pendiente</span>
                </div>
                <small>Barras por total, con lectura de becados y sin beca</small>
              </div>
              <div className="reporteria-age-chart__rows">
                {ageRangeSummary.map((item) => {
                  const width = `${Math.max((item.total / ageRangeMaxTotal) * 100, 4)}%`
                  const averageScholarship = item.scholarship > 0 ? item.scholarshipPercentTotal / item.scholarship : 0
                  return (
                    <div key={item.range} className="reporteria-age-chart__row">
                      <div className="reporteria-age-chart__label">
                        <strong>{item.range}</strong>
                        <span>{formatNumber(item.total)} estudiante(s)</span>
                      </div>
                      <div className="reporteria-age-chart__bar" aria-hidden="true">
                        <span style={{ width }} />
                      </div>
                      <div className="reporteria-age-chart__meta">
                        <span>Becados {formatNumber(item.scholarship)}</span>
                        <span>Sin beca {formatNumber(item.withoutScholarship)}</span>
                        <span>Prom. beca {averageScholarship.toFixed(1)}%</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}

          {!directReportMode && !isGradesReport ? (
            <div className="reporteria-integral-source-list">
              {sourceTables.map((source) => (
                <span key={source}>{source}</span>
              ))}
            </div>
          ) : null}

          {isGradesReport ? (
            <div className="reporteria-grade-students">
              <div className="excel-toolbar reporteria-grade-students__toolbar">
                <div>
                  <strong>{buscar.trim() ? `Filtro por nombre: ${buscar.trim()}` : 'Todos los estudiantes activos'}</strong>
                  <span>El filtro se aplica inmediatamente sobre el padrón cargado.</span>
                </div>
              </div>

              <div className="matricula-table-wrap reporteria-grade-students__table-wrap">
                <table className="matricula-table reporteria-grade-students__table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Estudiante</th>
                      <th>Cédula</th>
                      <th>Carrera activa</th>
                      <th>Materias</th>
                      <th>Estado de calificaciones</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedGradeStudents.length > 0 ? (
                      pagedGradeStudents.map((student, index) => (
                        <tr key={student.key}>
                          <td>{((Math.min(gradeStudentPage, gradeStudentPageCount) - 1) * gradeStudentPageSize) + index + 1}</td>
                          <td><strong>{student.label}</strong></td>
                          <td>{student.cedula || '-'}</td>
                          <td>{student.carrera || '-'}</td>
                          <td>{student.total}</td>
                          <td>
                            <div className="reporteria-grade-status-summary">
                              <span className="reporteria-grade-status-summary--approved">{student.approved} aprobada(s)</span>
                              <span className="reporteria-grade-status-summary--failed">{student.failed} reprobada(s)</span>
                              <span>{student.pending} pendiente(s)</span>
                            </div>
                          </td>
                          <td>
                            <button type="button" className="ghost-button" onClick={() => void openGradeStudent(student)} disabled={gradeDetailLoading || !student.studentCode}>
                              {gradeDetailLoading && selectedGradeStudentKey === student.key ? 'Cargando...' : 'Ver notas'}
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7}>
                          {loading
                            ? 'Consultando estudiantes...'
                            : buscar.trim()
                              ? 'No se encontraron estudiantes con ese nombre.'
                              : 'No existen estudiantes activos disponibles.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="reporteria-grade-students__pagination">
                <span>
                  Página {Math.min(gradeStudentPage, gradeStudentPageCount)} de {gradeStudentPageCount}
                </span>
                <div>
                  <button type="button" className="ghost-button" onClick={() => setGradeStudentPage(1)} disabled={gradeStudentPage <= 1}>
                    Primero
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setGradeStudentPage((page) => Math.max(1, page - 1))} disabled={gradeStudentPage <= 1}>
                    Anterior
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setGradeStudentPage((page) => Math.min(gradeStudentPageCount, page + 1))} disabled={gradeStudentPage >= gradeStudentPageCount}>
                    Siguiente
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setGradeStudentPage(gradeStudentPageCount)} disabled={gradeStudentPage >= gradeStudentPageCount}>
                    Último
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <>
          <div className="reporteria-total-summary" aria-label="Totales del resultado filtrado">
            <div className="reporteria-total-summary__lead">
              <span>Total del resultado</span>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <small>{visibleRows.length === 1 ? 'fila filtrada' : 'filas filtradas'}</small>
            </div>
            {totalSummaryItems.length > 0 ? (
              <div className="reporteria-total-summary__items">
                {totalSummaryItems.map((item) => (
                  <div key={item.key} className="reporteria-total-summary__item">
                    <span>{item.label}</span>
                    <strong>{formatCell(item.value)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <small className="reporteria-total-summary__empty">
                El resultado actual no tiene columnas numericas para totalizar.
              </small>
            )}
          </div>

          <div className="excel-toolbar">
            <label>
              <span>Filtrar tabla</span>
              <input
                value={tableFilter}
                onChange={(event) => setTableFilter(event.target.value)}
                placeholder="Buscar dentro del resultado"
              />
            </label>
            <div>
              <strong>{formatNumber(visibleRows.length)}</strong>
              <span>de {formatNumber(rows.length)} fila(s)</span>
            </div>
            <small>{formatNumber(columns.length)} columna(s) visibles</small>
          </div>

          <div className="matricula-table-wrap reporteria-integral-table-wrap excel-table-wrap">
            <table className="matricula-table reporteria-integral-table">
              <thead>
                <tr>
                  <th>#</th>
                  {columns.length > 0 ? (
                    columns.map((column) => <th key={column}>{columnLabel(column)}</th>)
                  ) : (
                    <th>Reporte</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? (
                  visibleRows.map((row, rowIndex) => (
                    <tr key={`legacy-report-row-${rowIndex}`}>
                      <td>{rowIndex + 1}</td>
                      {columns.map((column) => (
                        <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>
                      ))}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={Math.max(columns.length + 1, 2)}>
                      {loading ? 'Consultando información...' : 'Sin datos para los filtros seleccionados.'}
                    </td>
                  </tr>
                )}
              </tbody>
              {totalsRow ? (
                <tfoot>
                  <tr>
                    <td>Total</td>
                    {columns.map((column) => (
                      <td key={`total-${column}`} className={isTotalColumn(column) ? 'reporteria-total-cell' : undefined}>
                        {isTotalColumn(column) ? formatCell(totalsRow[column] ?? 0) : ''}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
            </>
          )}
        </article>

      </section>

      {isGradesReport && gradeSubjectModalOpen ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="grade-subject-modal-title">
          <article className="matricula-modal reporteria-grade-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>{selectedGradeStudent?.cedula || 'Sin cédula'}</span>
                <h3 id="grade-subject-modal-title">{selectedGradeStudent?.label || 'Materias del estudiante'}</h3>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setGradeSubjectModalOpen(false)
                  setGradeEditing(false)
                  setGradeDraft(null)
                  setGradeSaveError('')
                  setGradeSaveMessage('')
                  setGradeDetailError('')
                  setStudentGradeRows([])
                }}
              >
                Cerrar
              </button>
            </div>

            <div className="reporteria-grade-modal__grid">
              <aside className="reporteria-grade-modal__subjects" aria-label="Materias del estudiante">
                {gradeDetailLoading ? (
                  <p>Consultando materias y calificaciones...</p>
                ) : gradeDetailError ? (
                  <p className="teams-error">{gradeDetailError}</p>
                ) : selectedStudentSubjects.length > 0 ? (
                  selectedStudentSubjects.map((row) => {
                    const subjectKey = gradeSubjectKey(row)
                    return (
                      <button
                        key={subjectKey}
                        type="button"
                        className={subjectKey === selectedGradeSubjectKey ? 'reporteria-grade-subject reporteria-grade-subject--active' : 'reporteria-grade-subject'}
                        onClick={() => selectGradeSubject(row)}
                      >
                        <strong>{rowText(row, 'materia') || 'Materia sin nombre'}</strong>
                        <span>{rowText(row, 'periodo') || 'Período sin identificar'}</span>
                        <span>{rowText(row, 'materia_codigo_texto') || rowText(row, 'materia_codigo')} · Paralelo {rowText(row, 'paralelo') || '-'}</span>
                        <small>{isHomologationRow(row) ? 'Homologación' : 'Regular'} · Final {gradeValue(row.promedio_final)}</small>
                      </button>
                    )
                  })
                ) : (
                  <p>No hay materias para el estudiante seleccionado.</p>
                )}
              </aside>

              <section className="reporteria-grade-modal__detail">
                {selectedGradeSubject ? (
                  <>
                    <div className="reporteria-grade-detail__head">
                      <div>
                        <span>{rowText(selectedGradeSubject, 'periodo') || 'Período sin identificar'} · {isHomologationRow(selectedGradeSubject) ? 'Esquema homologación' : 'Esquema regular'}</span>
                        <h4>{rowText(selectedGradeSubject, 'materia') || 'Materia seleccionada'}</h4>
                      </div>
                      <div className="reporteria-grade-detail__actions">
                        <strong>{rowText(selectedGradeSubject, 'carrera') || '-'}</strong>
                        {canEditGrades && !gradeEditing ? (
                          <button
                            type="button"
                            className="primary-action"
                            onClick={startGradeEditing}
                            disabled={!canUpdateGradeRow(selectedGradeSubject)}
                          >
                            Modificar calificaciones
                          </button>
                        ) : null}
                      </div>
                    </div>

                    <div className="reporteria-grade-observation">
                      <span>Docente responsable</span>
                      <p>{rowText(selectedGradeSubject, 'docente_responsable') || 'Sin docente asignado'}</p>
                    </div>

                    {gradeEditing && gradeDraft ? (
                      <form
                        className="reporteria-grade-editor"
                        onSubmit={(event) => {
                          event.preventDefault()
                          void saveSelectedGrade()
                        }}
                      >
                        {isHomologationRow(selectedGradeSubject) ? (
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
                                  <strong>{gradeValue(gradePreviewCalculation?.partials[sectionIndex] ?? null)}</strong>
                                </div>
                              </fieldset>
                            ))}
                          </div>
                        )}

                        <div className="reporteria-grade-editor__common">
                          <label>
                            <span>Asistencia (%)</span>
                            <input type="number" min={0} max={100} step="0.01" value={gradeDraft.asistencia} onChange={(event) => updateGradeDraft('asistencia', event.target.value)} />
                          </label>
                          <label>
                            <span>Recuperación</span>
                            <input type="number" min={0} max={10} step="0.01" value={gradeDraft.recuperacion} onChange={(event) => updateGradeDraft('recuperacion', event.target.value)} />
                            <small className="reporteria-grade-editor__help">
                              {isHomologationRow(selectedGradeSubject)
                                ? 'Se registra en el único parcial y reemplaza una sola nota mínima entre teoría y práctica.'
                                : 'Se registra en el tercer parcial, reemplaza una sola nota puntual mínima y recalcula el promedio.'}
                            </small>
                          </label>
                          <div className="reporteria-grade-editor__final">
                            <span>Promedio final</span>
                            <strong>{gradeValue(gradePreviewFinal)}</strong>
                            <small>
                              {gradePreviewFinal === null ? 'Pendiente' : gradePreviewFinal >= 7 ? 'Aprobado' : 'Reprobado'}
                            </small>
                          </div>
                        </div>

                        {gradeSaveError ? <p className="teams-error">{gradeSaveError}</p> : null}
                        <div className="reporteria-grade-editor__actions">
                          <button type="button" className="ghost-button" onClick={() => { setGradeEditing(false); setGradeDraft(null); setGradeSaveError('') }} disabled={gradeSaving}>
                            Cancelar
                          </button>
                          <button type="submit" className="primary-action" disabled={gradeSaving}>
                            {gradeSaving ? 'Guardando...' : 'Guardar calificaciones'}
                          </button>
                        </div>
                      </form>
                    ) : (
                      <>
                        {isHomologationRow(selectedGradeSubject) ? (
                          <div className="reporteria-grade-cards reporteria-grade-cards--homo">
                            <div><span>Teoría</span><strong>{gradeValue(selectedGradeSubject.teoria_homo)}</strong></div>
                            <div><span>Práctica</span><strong>{gradeValue(selectedGradeSubject.practica_homo)}</strong></div>
                            <div><span>Recuperación</span><strong>{gradeValue(selectedGradeSubject.recuperacion)}</strong></div>
                            <div><span>Promedio final</span><strong>{gradeValue(selectedGradeSubject.promedio_final)}</strong></div>
                            <div><span>Condición</span><strong>{formatCell(selectedGradeSubject.condicion)}</strong></div>
                          </div>
                        ) : (
                          <div className="reporteria-grade-periods">
                            {[
                              ['Parcial 1', 'p1_tareas', 'p1_proyectos', 'p1_examen', 'promedio_p1'],
                              ['Parcial 2', 'p2_tareas', 'p2_proyectos', 'p2_examen', 'promedio_p2'],
                              ['Parcial 3', 'p3_tareas', 'p3_proyectos', 'p3_examen', 'promedio_p3'],
                            ].map(([title, taskKey, projectKey, examKey, averageKey]) => (
                              <div key={title} className="reporteria-grade-period">
                                <strong>{title}</strong>
                                <span>Tareas <b>{gradeValue(selectedGradeSubject[taskKey])}</b></span>
                                <span>Proyectos <b>{gradeValue(selectedGradeSubject[projectKey])}</b></span>
                                <span>Examen <b>{gradeValue(selectedGradeSubject[examKey])}</b></span>
                                <span>Promedio <b>{gradeValue(selectedGradeSubject[averageKey])}</b></span>
                              </div>
                            ))}
                            <div className="reporteria-grade-cards">
                              <div><span>Asistencia</span><strong>{gradeValue(selectedGradeSubject.asistencia)}</strong></div>
                              <div><span>Recuperación</span><strong>{gradeValue(selectedGradeSubject.recuperacion)}</strong></div>
                              <div><span>Promedio final</span><strong>{gradeValue(selectedGradeSubject.promedio_final)}</strong></div>
                              <div><span>Condición</span><strong>{formatCell(selectedGradeSubject.condicion)}</strong></div>
                            </div>
                          </div>
                        )}

                        <div className="reporteria-grade-observation">
                          <span>Observaciones</span>
                          <p>{formatCell(selectedGradeSubject.observaciones)}</p>
                        </div>
                      </>
                    )}

                    {gradeSaveMessage ? <p className="teams-message">{gradeSaveMessage}</p> : null}
                    {canEditGrades && !canUpdateGradeRow(selectedGradeSubject) ? (
                      <p className="teams-error">Esta fila no contiene una clave completa de matrícula y se mantiene en modo consulta.</p>
                    ) : null}
                  </>
                ) : (
                  <p>Seleccione una materia para ver sus calificaciones.</p>
                )}
              </section>
            </div>
          </article>
        </div>
      ) : null}
    </>
  )
}
