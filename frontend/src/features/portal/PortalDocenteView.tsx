import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  downloadPortalTeacherComplianceReport,
  downloadPortalTeacherCourseReport,
  downloadPortalTeacherStudentGradeReport,
  fetchMyTeamRecordings,
  fetchMyTeamsCatalog,
  fetchPortalTeacherCourses,
  fetchPortalTeacherSubjectStudents,
  fetchPortalTeacherStudents,
  savePortalTeacherGrades,
  signPortalTeacherComplianceReport,
} from '../../lib/api'
import { calculateRegularGradeWithRecovery, constrainDecimalInput, parseBoundedDecimal } from '../../lib/gradeCalculation'
import type {
  GraphTeam,
  PortalAcademicRecordItem,
  PortalTeacherCourse,
  PortalTeacherGradePayload,
  TeacherComplianceTeamsRecording,
  TeamRecording,
} from '../../types/app'

type PortalDocenteViewProps = {
  displayName: string
  initialMode?: 'courses' | 'compliance'
}

type GradePartial = 'P1' | 'P2' | 'P3'
type CoursePeriodFilter = 'TODOS' | 'R' | 'H'
type GradePeriodOption = {
  code: string
  label: string
}

const GRADE_PARTIAL_OPTIONS: Array<{ value: GradePartial; label: string }> = [
  { value: 'P1', label: 'Primer parcial' },
  { value: 'P2', label: 'Segundo parcial' },
  { value: 'P3', label: 'Tercer parcial' },
]

const COMPLIANCE_EVIDENCE_OPTIONS = [
  { key: 'pea', label: 'Captura PEA y sílabo firmado' },
  { key: 'aula', label: 'Captura aula virtual y recursos' },
  { key: 'teams', label: 'TEAMS y clases grabadas' },
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
  const subjectCode = (course.cod_materia || course.codigo_materia || '').trim().toUpperCase()
  if (course.grade_group_key) {
    return `BLOQUE|${subjectCode}|${course.grade_group_key}`
  }
  if (course.asignaciones?.length) {
    return `MATERIA|${subjectCode}`
  }
  const periodos = course.codigo_periodos?.length ? course.codigo_periodos.join(',') : course.codigo_periodo
  return [
    course.cod_anio_basica,
    periodos,
    course.cod_materia || course.codigo_materia,
    course.paralelo,
    course.cod_jornada,
  ].join('|')
}

function coursePeriodKind(course: PortalTeacherCourse): 'R' | 'H' {
  return isHomologation(course) ? 'H' : 'R'
}

function courseAssignments(course: PortalTeacherCourse | null | undefined) {
  if (!course) return []
  return course.asignaciones?.length ? course.asignaciones : [course]
}

function courseHasPeriodKind(course: PortalTeacherCourse, kind: Exclude<CoursePeriodFilter, 'TODOS'>) {
  if (kind === 'R' && course.tiene_regular !== undefined) return course.tiene_regular
  if (kind === 'H' && course.tiene_homologacion !== undefined) return course.tiene_homologacion
  return courseAssignments(course).some((assignment) => coursePeriodKind(assignment) === kind)
}

function teacherGradePeriodOptions(course: PortalTeacherCourse | null | undefined, kind: 'R' | 'H') {
  const options = new Map<string, GradePeriodOption>()
  for (const assignment of courseAssignments(course).filter((item) => coursePeriodKind(item) === kind)) {
    const codes = assignment.codigo_periodos?.length
      ? assignment.codigo_periodos
      : assignment.codigo_periodo
        ? [assignment.codigo_periodo]
        : []
    const labels = (assignment.detalle_periodos || assignment.detalle_periodo || '')
      .split(/\s+\/\s+/)
      .map((item) => item.trim())
      .filter(Boolean)
    for (const [index, code] of codes.entries()) {
      const normalizedCode = String(code || '').trim()
      if (!normalizedCode || options.has(normalizedCode)) continue
      options.set(normalizedCode, {
        code: normalizedCode,
        label: labels[index] || assignment.detalle_periodo || normalizedCode,
      })
    }
  }
  return Array.from(options.values()).sort((left, right) => {
    const numericDifference = Number(right.code) - Number(left.code)
    if (Number.isFinite(numericDifference) && numericDifference !== 0) return numericDifference
    return right.label.localeCompare(left.label, 'es', { sensitivity: 'base' })
  })
}

function defaultTeacherGradePeriods(course: PortalTeacherCourse | null | undefined, kind: 'R' | 'H') {
  return teacherGradePeriodOptions(course, kind).slice(0, kind === 'R' ? 2 : 1).map((option) => option.code)
}

function assignmentForSelectedPeriods(assignment: PortalTeacherCourse, selectedCodes: string[]) {
  if (selectedCodes.length === 0) return assignment
  const codes = assignment.codigo_periodos?.length
    ? assignment.codigo_periodos
    : assignment.codigo_periodo
      ? [assignment.codigo_periodo]
      : []
  const labels = (assignment.detalle_periodos || assignment.detalle_periodo || '')
    .split(/\s+\/\s+/)
    .map((item) => item.trim())
  const selected = codes
    .map((code, index) => ({ code: String(code || '').trim(), label: labels[index] || assignment.detalle_periodo || code }))
    .filter((item) => item.code && selectedCodes.includes(item.code))
  if (selected.length === 0) return null
  return {
    ...assignment,
    codigo_periodo: selected[0].code,
    codigo_periodos: selected.map((item) => item.code),
    detalle_periodo: selected.map((item) => item.label).join(' / '),
    detalle_periodos: selected.map((item) => item.label).join(' / '),
    period_count: selected.length,
  }
}

function teacherGradeCourseGroups(courses: PortalTeacherCourse[]) {
  const groups: PortalTeacherCourse[] = []
  for (const subject of courses) {
    const exactScopes = subject.alcances_periodo?.length
      ? subject.alcances_periodo
      : courseAssignments(subject)

    for (const kind of ['R', 'H'] as const) {
      const periodOptions = teacherGradePeriodOptions(
        { ...subject, asignaciones: exactScopes },
        kind
      )
      const blockSize = kind === 'R' ? 2 : 1
      for (let index = 0; index < periodOptions.length; index += blockSize) {
        const blockOptions = periodOptions.slice(index, index + blockSize)
        const periodCodes = blockOptions.map((option) => option.code)
        const scopes = exactScopes.flatMap((scope) => {
          if (coursePeriodKind(scope) !== kind) return []
          const scoped = assignmentForSelectedPeriods(scope, periodCodes)
          return scoped ? [scoped] : []
        })
        if (scopes.length === 0) continue

        const careerCodes = Array.from(new Set(scopes.flatMap((scope) =>
          scope.cod_anio_basicas?.length ? scope.cod_anio_basicas : scope.cod_anio_basica ? [scope.cod_anio_basica] : []
        )))
        const careerNames = Array.from(new Set(scopes.map((scope) => scope.nombre_carrera).filter(Boolean)))
        const internalCodes = Array.from(new Set(scopes.flatMap((scope) => scope.codigo_materias || [])))
        const parallels = Array.from(new Set(scopes.map((scope) => scope.paralelo).filter(Boolean)))
        const journeys = Array.from(new Set(scopes.map((scope) => scope.jornada).filter(Boolean)))
        const journeyCodes = Array.from(new Set(scopes.map((scope) => scope.cod_jornada).filter((value) => value !== null && value !== undefined)))
        const periodLabels = blockOptions.map((option) => option.label)

        groups.push({
          ...subject,
          grade_group_key: `${kind}|${periodCodes.join(',')}`,
          codigo_periodo: periodCodes[0] || '',
          codigo_periodos: periodCodes,
          detalle_periodo: periodLabels.join(' / '),
          detalle_periodos: periodLabels.join(' / '),
          periodo_orden: Math.max(...periodCodes.map((code) => Number(code) || 0)),
          period_count: periodCodes.length,
          tipo_periodo: kind,
          es_homologacion: kind === 'H',
          tiene_regular: kind === 'R',
          tiene_homologacion: kind === 'H',
          regular_count: kind === 'R' ? scopes.length : 0,
          homologation_count: kind === 'H' ? scopes.length : 0,
          asignaciones: scopes,
          alcances_periodo: scopes,
          assignment_count: scopes.length,
          cod_anio_basica: careerCodes.length === 1 ? careerCodes[0] : '',
          cod_anio_basicas: careerCodes,
          nombre_carrera: careerNames.length <= 2 ? careerNames.join(' / ') : `${careerNames.length} carreras`,
          codigo_materias: internalCodes,
          paralelo: parallels.length === 1 ? parallels[0] : 'Varios',
          jornada: journeys.length === 1 ? journeys[0] : 'Varias jornadas',
          cod_jornada: journeyCodes.length === 1 ? journeyCodes[0] : null,
          total_estudiantes: scopes.reduce((total, scope) => total + (scope.total_estudiantes || 0), 0),
        })
      }
    }
  }

  return groups.sort((left, right) => {
    const subjectOrder = (left.nombre_materia || '').localeCompare(right.nombre_materia || '', 'es', { sensitivity: 'base' })
    if (subjectOrder !== 0) return subjectOrder
    const codeOrder = (left.cod_materia || left.codigo_materia || '').localeCompare(
      right.cod_materia || right.codigo_materia || '',
      'es',
      { sensitivity: 'base' }
    )
    if (codeOrder !== 0) return codeOrder
    return (right.periodo_orden || 0) - (left.periodo_orden || 0)
  })
}

function preferredCoursePeriodKind(course: PortalTeacherCourse, filter: CoursePeriodFilter): 'R' | 'H' {
  if (filter !== 'TODOS' && courseHasPeriodKind(course, filter)) return filter
  return courseHasPeriodKind(course, 'R') ? 'R' : 'H'
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
  if (course.asignaciones?.length) {
    const kinds = [courseHasPeriodKind(course, 'R') ? 'REGULAR' : '', courseHasPeriodKind(course, 'H') ? 'HOMO' : '']
      .filter(Boolean)
      .join(' + ')
    const period = course.detalle_periodos || course.detalle_periodo || course.codigo_periodo || 'Sin período'
    return `${courseSubjectLabel(course)} - ${period} - ${course.cod_anio_basicas?.length || 1} carrera(s) - ${kinds}`
  }
  const period = course.detalle_periodos || course.detalle_periodo || course.codigo_periodo || 'Sin período'
  const kind = coursePeriodKind(course) === 'H' ? 'HOMO' : 'REGULAR'
  const career = course.nombre_carrera || `Carrera ${course.cod_anio_basica || '-'}`
  return `${course.nombre_materia || course.codigo_materia || 'Materia'} - ${career} - ${period} - Paralelo ${course.paralelo || '-'} - ${courseJourneyLabel(course)} - ${kind}`
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

function uniqueStudents(items: PortalAcademicRecordItem[]) {
  const grouped = new Map<string, PortalAcademicRecordItem>()
  for (const item of items) {
    const key = studentKey(item)
    if (!key) continue
    grouped.set(key, item)
  }
  return Array.from(grouped.values()).sort((left, right) => {
    const careerOrder = (left.nombre_carrera || '').localeCompare(right.nombre_carrera || '', 'es', { sensitivity: 'base' })
    if (careerOrder !== 0) return careerOrder
    const periodOrder = Number(right.codigo_periodo || 0) - Number(left.codigo_periodo || 0)
    if (periodOrder !== 0) return periodOrder
    return (left.nombre_estudiante || '').localeCompare(right.nombre_estudiante || '', 'es', { sensitivity: 'base' })
  })
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

function regularAverages(draft: GradeDraft) {
  const calculation = calculateRegularGradeWithRecovery(
    [
      [toNumberOrNull(draft.p1_tareas), toNumberOrNull(draft.p1_proyectos), toNumberOrNull(draft.p1_examen)],
      [toNumberOrNull(draft.p2_tareas), toNumberOrNull(draft.p2_proyectos), toNumberOrNull(draft.p2_examen)],
      [toNumberOrNull(draft.p3_tareas), toNumberOrNull(draft.p3_proyectos), toNumberOrNull(draft.p3_examen)],
    ],
    toNumberOrNull(draft.recuperacion),
  )
  return {
    promP1: calculation.partials[0],
    promP2: calculation.partials[1],
    promP3: calculation.partials[2],
    final: calculation.final,
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

function normalizeTeamText(value: unknown) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, ' ')
    .trim()
}

function teamCourseMatchScore(team: GraphTeam, course: PortalTeacherCourse, periodCodes: string[]) {
  const searchable = normalizeTeamText([team.displayName, team.description, team.mail].filter(Boolean).join(' '))
  const subjectName = normalizeTeamText(course.nombre_materia)
  const subjectCode = normalizeTeamText(course.cod_materia || course.codigo_materia)
  const careerName = normalizeTeamText(course.nombre_carrera)
  const parallel = normalizeTeamText(course.paralelo)
  let score = 0

  if (subjectCode.length >= 3 && searchable.includes(subjectCode)) score += 120
  if (subjectName.length >= 5 && searchable.includes(subjectName)) score += 100
  const subjectTokens = subjectName
    .split(' ')
    .filter((token) => token.length >= 4 && !['PARA', 'CON', 'DELA'].includes(token))
  score += subjectTokens.filter((token) => searchable.includes(token)).length * 12
  if (careerName.length >= 5 && searchable.includes(careerName)) score += 10
  if (parallel && searchable.includes(`PARALELO ${parallel}`)) score += 18
  score += periodCodes.filter((code) => {
    const normalizedCode = normalizeTeamText(code)
    return normalizedCode.length >= 3 && searchable.includes(normalizedCode)
  }).length * 20
  return score
}

function recordingKey(recording: TeamRecording) {
  return String(
    recording.id ||
      recording.webUrl ||
      `${recording.name || 'grabacion'}|${recording.callStartTime || recording.recordingStartTime || recording.startTime || ''}`
  )
}

function dateLabelToIso(value?: string) {
  const label = String(value || '').trim()
  const match = label.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/)
  if (!match) return ''
  return `${match[3]}-${match[2].padStart(2, '0')}-${match[1].padStart(2, '0')}`
}

function recordingIsoDate(recording: TeamRecording) {
  const localDate = dateLabelToIso(
    recording.callDateLabel || recording.recordingDateLabel || recording.startDateLabel || recording.fileCreatedDateLabel
  )
  if (localDate) return localDate
  const source =
    recording.callStartTime ||
    recording.recordingStartTime ||
    recording.startTime ||
    recording.fileCreatedAt ||
    recording.uploadedAt ||
    recording.modifiedAt
  const match = String(source || '').match(/^(\d{4}-\d{2}-\d{2})/)
  return match?.[1] || ''
}

function recordingDateLabel(recording: TeamRecording) {
  return (
    recording.callDateLabel ||
    recording.recordingDateLabel ||
    recording.startDateLabel ||
    recording.fileCreatedDateLabel ||
    recording.uploadedDateLabel ||
    'No disponible'
  )
}

function teamsRecordingPayload(
  team: GraphTeam | null,
  recordings: TeamRecording[]
): TeacherComplianceTeamsRecording[] {
  if (!team?.id) return []
  return recordings.slice(0, 50).map((recording) => ({
    team_id: team.id || '',
    team_name: team.displayName || 'Equipo de Teams',
    recording_id: recordingKey(recording),
    name: recording.name || 'Grabación de clase',
    date: recordingDateLabel(recording),
    start_hour:
      recording.callStartHourLabel ||
      recording.recordingStartHourLabel ||
      recording.startHourLabel ||
      recording.fileCreatedHourLabel ||
      'No disponible',
    end_hour:
      recording.callEndHourLabel || recording.recordingEndHourLabel || recording.endHourLabel || 'No disponible',
    call_duration:
      recording.callDurationClock ||
      recording.callDurationLabel ||
      recording.calculatedDurationClock ||
      recording.calculatedDurationLabel ||
      'No disponible',
    recording_duration:
      recording.recordingDurationClock ||
      recording.durationClock ||
      recording.recordingDurationLabel ||
      recording.durationLabel ||
      'No disponible',
    modified_by: recording.lastModifiedByName || recording.createdByName || 'No disponible',
    web_url: recording.webUrl || '',
    source: 'Microsoft Graph',
  }))
}

export function PortalDocenteView({ displayName, initialMode = 'courses' }: Readonly<PortalDocenteViewProps>) {
  const [courses, setCourses] = useState<PortalTeacherCourse[]>([])
  const [selectedCourseKey, setSelectedCourseKey] = useState('')
  const [periodFilter, setPeriodFilter] = useState<CoursePeriodFilter>('TODOS')
  const [gradePeriodKind, setGradePeriodKind] = useState<'R' | 'H'>('R')
  const [selectedGradePeriodCodes, setSelectedGradePeriodCodes] = useState<string[]>([])
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
  const [downloadingSecretaryReport, setDownloadingSecretaryReport] = useState(false)
  const [previewingSecretaryReport, setPreviewingSecretaryReport] = useState(false)
  const [secretaryReportPreviewUrl, setSecretaryReportPreviewUrl] = useState('')
  const [downloadingComplianceReport, setDownloadingComplianceReport] = useState(false)
  const [signingComplianceReport, setSigningComplianceReport] = useState(false)
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
    pea: [],
    aula: [],
    teams: [],
    asistencia: [],
    notas: [],
  })
  const [complianceTeams, setComplianceTeams] = useState<GraphTeam[]>([])
  const [selectedComplianceTeamId, setSelectedComplianceTeamId] = useState('')
  const [complianceRecordings, setComplianceRecordings] = useState<TeamRecording[]>([])
  const [selectedComplianceRecordingKeys, setSelectedComplianceRecordingKeys] = useState<string[]>([])
  const [loadingComplianceTeams, setLoadingComplianceTeams] = useState(false)
  const [loadingComplianceRecordings, setLoadingComplianceRecordings] = useState(false)
  const [complianceTeamsError, setComplianceTeamsError] = useState('')
  const [complianceTeamsRefreshToken, setComplianceTeamsRefreshToken] = useState(0)
  const [complianceRecordingsRefreshToken, setComplianceRecordingsRefreshToken] = useState(0)
  const [signingCertificate, setSigningCertificate] = useState<File | null>(null)
  const [signingCertificateInputKey, setSigningCertificateInputKey] = useState(0)
  const [signingPassword, setSigningPassword] = useState('')
  const [showSigningPassword, setShowSigningPassword] = useState(false)
  const [signingReason, setSigningReason] = useState('Informe de cumplimiento docente')
  const [signingLocation, setSigningLocation] = useState('Quito, Ecuador')
  const [signingContact, setSigningContact] = useState('')
  const [signingConsent, setSigningConsent] = useState(false)
  const [savingKey, setSavingKey] = useState('')
  const [gradeScreenOpen, setGradeScreenOpen] = useState(initialMode === 'compliance' ? false : false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const gradeCourseGroups = useMemo(() => teacherGradeCourseGroups(courses), [courses])
  const exactCourses = useMemo(
    () => courses.flatMap((course) => course.alcances_periodo?.length ? course.alcances_periodo : courseAssignments(course)),
    [courses]
  )
  const selectedCourse = useMemo(
    () =>
      gradeCourseGroups.find((course) => courseKey(course) === selectedCourseKey) ||
      exactCourses.find((course) => courseKey(course) === selectedCourseKey) ||
      courses.find((course) => courseKey(course) === selectedCourseKey) ||
      null,
    [courses, exactCourses, gradeCourseGroups, selectedCourseKey]
  )
  const gradePeriodOptions = useMemo(
    () => teacherGradePeriodOptions(selectedCourse, gradePeriodKind),
    [gradePeriodKind, selectedCourse]
  )
  const selectedGradeAssignments = useMemo(
    () =>
      courseAssignments(selectedCourse).flatMap((assignment) => {
        if (coursePeriodKind(assignment) !== gradePeriodKind) return []
        const scopedAssignment = assignmentForSelectedPeriods(assignment, selectedGradePeriodCodes)
        return scopedAssignment ? [scopedAssignment] : []
      }),
    [gradePeriodKind, selectedCourse, selectedGradePeriodCodes]
  )
  const reportCourse = selectedGradeAssignments[0] || selectedCourse
  const subjectOptions = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; count: number; regular: number; homo: number }>()
    for (const course of gradeCourseGroups) {
      if (periodFilter !== 'TODOS' && !courseHasPeriodKind(course, periodFilter)) continue
      const key = courseSubjectKey(course)
      const regular = coursePeriodKind(course) === 'R' ? 1 : 0
      const homo = coursePeriodKind(course) === 'H' ? 1 : 0
      const current = grouped.get(key) || {
        key,
        label: courseSubjectLabel(course),
        count: 0,
        regular: 0,
        homo: 0,
      }
      current.count += 1
      current.regular += regular
      current.homo += homo
      grouped.set(key, current)
    }
    return Array.from(grouped.values()).sort((a, b) => a.label.localeCompare(b.label, 'es'))
  }, [gradeCourseGroups, periodFilter])
  const filteredCourses = useMemo(() => {
    const query = courseSearch.trim().toUpperCase()
    return gradeCourseGroups.filter((course) => {
      if (periodFilter !== 'TODOS' && !courseHasPeriodKind(course, periodFilter)) return false
      if (subjectFilter && courseSubjectKey(course) !== subjectFilter) return false
      if (!query) return true
      const searchable = [course, ...courseAssignments(course)]
        .flatMap((item) => [
          item.nombre_materia,
          item.cod_materia,
          item.codigo_materia,
          item.nombre_carrera,
          item.detalle_periodo,
          item.detalle_periodos,
          item.codigo_periodo,
          item.paralelo,
        ])
        .filter(Boolean)
        .join(' ')
        .toUpperCase()
      return searchable.includes(query)
    })
  }, [courseSearch, gradeCourseGroups, periodFilter, subjectFilter])
  const filteredSummary = useMemo(() => {
    return filteredCourses.reduce(
      (summary, course) => {
        summary.regular += coursePeriodKind(course) === 'R' ? 1 : 0
        summary.homo += coursePeriodKind(course) === 'H' ? 1 : 0
        summary.students += course.total_estudiantes || 0
        return summary
      },
      { regular: 0, homo: 0, students: 0 }
    )
  }, [filteredCourses])
  const totalAssignments = exactCourses.length
  const filteredExactCourses = useMemo(() => {
    const query = courseSearch.trim().toUpperCase()
    return exactCourses.filter((course) => {
      if (periodFilter !== 'TODOS' && coursePeriodKind(course) !== periodFilter) return false
      if (subjectFilter && courseSubjectKey(course) !== subjectFilter) return false
      if (!query) return true
      return [
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
        .includes(query)
    })
  }, [courseSearch, exactCourses, periodFilter, subjectFilter])
  const complianceCourseOptions = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; course: PortalTeacherCourse; periods: number }>()
    for (const course of filteredExactCourses) {
      const key = [
        (course.cod_anio_basica || '').trim(),
        courseSubjectKey(course),
        (course.paralelo || '').trim().toUpperCase(),
        course.cod_jornada || '',
      ].join('|')
      const periodCount = course.codigo_periodos?.length || (course.codigo_periodo ? 1 : 0)
      const current = grouped.get(key)
      if (current) {
        current.periods += periodCount
        continue
      }
      grouped.set(key, {
        key: courseKey(course),
        label: `${courseSubjectLabel(course)} - ${course.nombre_carrera || `Carrera ${course.cod_anio_basica || '-'}`} - Paralelo ${course.paralelo || '-'} - ${courseJourneyLabel(course)}`,
        course,
        periods: periodCount,
      })
    }
    return Array.from(grouped.values()).sort((left, right) => left.label.localeCompare(right.label, 'es'))
  }, [filteredExactCourses])
  const targetCourse = useMemo(
    () =>
      exactCourses.find((item) => courseKey(item) === targetCourseKey) ||
      gradeCourseGroups.find((item) => courseKey(item) === targetCourseKey) ||
      courses.find((item) => courseKey(item) === targetCourseKey) ||
      complianceCourseOptions[0]?.course ||
      filteredCourses[0] ||
      null,
    [complianceCourseOptions, courses, exactCourses, filteredCourses, gradeCourseGroups, targetCourseKey]
  )
  const targetCoursePeriodOptions = useMemo(() => {
    if (!targetCourse) return []
    const selectedCareer = (targetCourse.cod_anio_basica || '').trim()
    const selectedSubject = courseSubjectKey(targetCourse)
    const selectedParallel = (targetCourse.paralelo || '').trim().toUpperCase()
    const selectedJourney = targetCourse.cod_jornada ?? null
    const options = new Map<string, { code: string; label: string }>()
    for (const course of exactCourses) {
      if ((course.cod_anio_basica || '').trim() !== selectedCareer) continue
      if (courseSubjectKey(course) !== selectedSubject) continue
      if ((course.paralelo || '').trim().toUpperCase() !== selectedParallel) continue
      if ((course.cod_jornada ?? null) !== selectedJourney) continue
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
  }, [exactCourses, targetCourse])
  const availableCompliancePeriodOptions = useMemo(
    () => targetCoursePeriodOptions.filter((option) => !compliancePeriodCodes.includes(option.code)),
    [compliancePeriodCodes, targetCoursePeriodOptions]
  )
  const selectedComplianceTeam = useMemo(
    () => complianceTeams.find((team) => team.id === selectedComplianceTeamId) || null,
    [complianceTeams, selectedComplianceTeamId]
  )
  const filteredComplianceRecordings = useMemo(
    () =>
      complianceRecordings.filter((recording) => {
        if (!complianceStartDate && !complianceEndDate) return true
        const recordingDate = recordingIsoDate(recording)
        if (!recordingDate) return false
        if (complianceStartDate && recordingDate < complianceStartDate) return false
        if (complianceEndDate && recordingDate > complianceEndDate) return false
        return true
      }),
    [complianceEndDate, complianceRecordings, complianceStartDate]
  )
  const selectedComplianceRecordings = useMemo(
    () =>
      filteredComplianceRecordings.filter((recording) =>
        selectedComplianceRecordingKeys.includes(recordingKey(recording))
      ),
    [filteredComplianceRecordings, selectedComplianceRecordingKeys]
  )
  const complianceTeamsReportPayload = useMemo(
    () => teamsRecordingPayload(selectedComplianceTeam, selectedComplianceRecordings),
    [selectedComplianceRecordings, selectedComplianceTeam]
  )
  const courseUsesHomologation = gradePeriodKind === 'H'
  const gradeTableColumnCount = (courseUsesHomologation ? 6 : gradePartial === 'P3' ? 10 : 8) + 2

  const loadCourses = useCallback(async () => {
    setLoadingCourses(true)
    setError('')
    try {
      const payload = await fetchPortalTeacherCourses()
      const items = payload.items || []
      setCourses(items)
      const firstSubject = items[0]
      const firstGradeCourse = teacherGradeCourseGroups(items)[0]
      const firstCourse = initialMode === 'compliance' ? firstSubject : firstGradeCourse
      if (firstCourse) {
        const firstKind = preferredCoursePeriodKind(firstCourse, 'TODOS')
        setSelectedCourseKey(courseKey(firstCourse))
        setGradePeriodKind(firstKind)
        setSelectedGradePeriodCodes(defaultTeacherGradePeriods(firstCourse, firstKind))
        const firstTarget = initialMode === 'compliance'
          ? firstSubject?.alcances_periodo?.[0] || courseAssignments(firstSubject)[0] || firstSubject || firstCourse
          : firstGradeCourse
        setTargetCourseKey(courseKey(firstTarget))
        setGradeScreenOpen(false)
        setStudents([])
        setDrafts({})
      } else {
        setGradeScreenOpen(false)
        setTargetCourseKey('')
        setSelectedGradePeriodCodes([])
        setStudents([])
        setDrafts({})
      }
    } catch (apiError) {
      setCourses([])
      setSelectedGradePeriodCodes([])
      setStudents([])
      setDrafts({})
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron consultar las materias asignadas')
    } finally {
      setLoadingCourses(false)
    }
  }, [initialMode])

  async function loadStudents(
    course: PortalTeacherCourse | null = selectedCourse,
    kind: 'R' | 'H' = gradePeriodKind,
    periodCodes: string[] = selectedGradePeriodCodes,
  ) {
    const subjectCode = course?.cod_materia || course?.codigo_materia || ''
    if (!subjectCode) {
      setStudents([])
      setDrafts({})
      return
    }
    const availableCodes = new Set(teacherGradePeriodOptions(course, kind).map((option) => option.code))
    const selectedCodes = Array.from(
      new Set(periodCodes.map((code) => String(code || '').trim()).filter((code) => availableCodes.has(code)))
    ).slice(0, kind === 'R' ? 2 : 1)
    if (selectedCodes.length === 0) {
      setStudents([])
      setDrafts({})
      setError(
        kind === 'R'
          ? 'Seleccione uno o máximo dos períodos regulares.'
          : 'Seleccione un período de homologación.'
      )
      return
    }
    setSelectedGradePeriodCodes(selectedCodes)
    setLoadingStudents(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchPortalTeacherSubjectStudents({
        codigoMateria: subjectCode,
        tipoPeriodo: kind,
        codigoPeriodos: selectedCodes,
      })
      const items = uniqueStudents(payload.items || [])
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
    const kind = preferredCoursePeriodKind(course, periodFilter)
    const periodCodes = defaultTeacherGradePeriods(course, kind)
    setSelectedCourseKey(courseKey(course))
    setTargetCourseKey(courseKey(course))
    setGradePeriodKind(kind)
    setSelectedGradePeriodCodes(periodCodes)
    setGradePartial('P1')
    setGradeScreenOpen(true)
    void loadStudents(course, kind, periodCodes)
  }

  function selectGradePeriod(code: string) {
    if (!selectedCourse || loadingStudents) return
    let nextCodes: string[]
    if (gradePeriodKind === 'H') {
      nextCodes = [code]
    } else if (selectedGradePeriodCodes.includes(code)) {
      if (selectedGradePeriodCodes.length === 1) return
      nextCodes = selectedGradePeriodCodes.filter((selectedCode) => selectedCode !== code)
    } else {
      if (selectedGradePeriodCodes.length >= 2) {
        setError('Solo puede unir hasta dos períodos regulares distintos.')
        return
      }
      nextCodes = [...selectedGradePeriodCodes, code]
    }
    setError('')
    setSelectedGradePeriodCodes(nextCodes)
    void loadStudents(selectedCourse, gradePeriodKind, nextCodes)
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
          codAnioBasica: course.cod_anio_basica,
          codigoMateria: subjectCode,
          paralelo: course.paralelo,
          codJornada: course.cod_jornada ?? null,
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
    const firstCourse = initialMode === 'compliance' ? exactCourses[0] : gradeCourseGroups[0]
    setTargetCourseKey(firstCourse ? courseKey(firstCourse) : '')
  }

  function backToCourses() {
    setGradeScreenOpen(false)
    setMessage('')
    setError('')
  }

  function updateDraft(item: PortalAcademicRecordItem, field: keyof GradeDraft, value: string) {
    const constrained = constrainDecimalInput(value, field === 'asistencia' ? 100 : 10)
    if (constrained === null) return
    const key = studentKey(item)
    setDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] || draftFromItem(item)),
        [field]: constrained,
      },
    }))
  }

  function buildGradePayload(item: PortalAcademicRecordItem) {
    const key = studentKey(item)
    const draft = drafts[key] || draftFromItem(item)
    const homo = isHomologation(item) || isHomologation(selectedCourse)
    const teoriaHomo = parseBoundedDecimal(draft.teoria_homo, 10, 'La nota teórica')
    const practicaHomo = parseBoundedDecimal(draft.practica_homo, 10, 'La nota práctica')
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
      p1_tareas: homo ? null : parseBoundedDecimal(draft.p1_tareas, 10, 'Tareas del parcial 1'),
      p1_proyectos: homo ? null : parseBoundedDecimal(draft.p1_proyectos, 10, 'Proyectos del parcial 1'),
      p1_examen: homo ? null : parseBoundedDecimal(draft.p1_examen, 10, 'Examen del parcial 1'),
      prom_p1: homo ? null : regular.promP1,
      p2_tareas: homo ? null : parseBoundedDecimal(draft.p2_tareas, 10, 'Tareas del parcial 2'),
      p2_proyectos: homo ? null : parseBoundedDecimal(draft.p2_proyectos, 10, 'Proyectos del parcial 2'),
      p2_examen: homo ? null : parseBoundedDecimal(draft.p2_examen, 10, 'Examen del parcial 2'),
      prom_p2: homo ? null : regular.promP2,
      p3_tareas: homo ? null : parseBoundedDecimal(draft.p3_tareas, 10, 'Tareas del parcial 3'),
      p3_proyectos: homo ? null : parseBoundedDecimal(draft.p3_proyectos, 10, 'Proyectos del parcial 3'),
      p3_examen: homo ? null : parseBoundedDecimal(draft.p3_examen, 10, 'Examen del parcial 3'),
      prom_p3: homo ? null : regular.promP3,
      promedio: promedioFinal,
      promedio_final: promedioFinal,
      asistencia: parseBoundedDecimal(draft.asistencia, 100, 'La asistencia'),
      recuperacion: homo ? null : parseBoundedDecimal(draft.recuperacion, 10, 'La recuperación'),
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
      await loadStudents(selectedCourse, gradePeriodKind, selectedGradePeriodCodes)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron guardar las notas')
    } finally {
      setSavingKey('')
    }
  }

  function reportRequestParams(course: PortalTeacherCourse | null = reportCourse, selectedPeriodos: string[] = []) {
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
      codAnioBasica: course.cod_anio_basica || '',
      paralelo: course.paralelo,
      codJornada: course.cod_jornada ?? null,
    }
  }

  async function buildCourseReportBlob() {
    const params = reportRequestParams()
    if (!params) return null
    return downloadPortalTeacherCourseReport({
      codigoPeriodos: params.periodos,
      codAnioBasica: params.codAnioBasica,
      codigoMateria: params.subjectCode,
      paralelo: params.paralelo,
      codJornada: params.codJornada,
    })
  }

  async function buildSecretaryReportBlob() {
    const params = reportRequestParams()
    if (!params) return null
    return downloadPortalTeacherStudentGradeReport({
      codigoPeriodos: params.periodos,
      codAnioBasica: params.codAnioBasica,
      codigoMateria: params.subjectCode,
      paralelo: params.paralelo,
      codJornada: params.codJornada,
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
      codAnioBasica: params.codAnioBasica,
      codigoMateria: params.subjectCode,
      paralelo: params.paralelo,
      codJornada: params.codJornada,
      codigoEstudiantes: selectedComplianceStudentCodes,
      fechaInicio: complianceStartDate,
      fechaFin: complianceEndDate,
      telefono: compliancePhone,
      actualizaciones: complianceUpdates,
      observaciones: complianceObservations,
      grabacionesTeams: complianceTeamsReportPayload,
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
    if (!reportCourse) return
    const periodos = reportCourse.codigo_periodos?.length
      ? reportCourse.codigo_periodos
      : reportCourse.codigo_periodo
        ? [reportCourse.codigo_periodo]
        : []
    const subjectCode = reportCourse.cod_materia || reportCourse.codigo_materia || ''
    if (!periodos.length || !subjectCode || !reportCourse.paralelo) {
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
      const subject = safeFilenamePart(reportCourse.nombre_materia || subjectCode)
      const period = safeFilenamePart(reportCourse.detalle_periodos || reportCourse.detalle_periodo || periodos.join('-'))
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

  async function previewSecretaryReport() {
    setPreviewingSecretaryReport(true)
    setError('')
    try {
      const blob = await buildSecretaryReportBlob()
      if (!blob) return
      const url = window.URL.createObjectURL(blob)
      setSecretaryReportPreviewUrl(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar la vista previa del formato Secretaría')
    } finally {
      setPreviewingSecretaryReport(false)
    }
  }

  async function downloadSecretaryReport() {
    if (!reportCourse) return
    setDownloadingSecretaryReport(true)
    setError('')
    try {
      const blob = await buildSecretaryReportBlob()
      if (!blob) return
      const periodos = reportCourse.codigo_periodos?.length
        ? reportCourse.codigo_periodos
        : reportCourse.codigo_periodo
          ? [reportCourse.codigo_periodo]
          : []
      const subjectCode = reportCourse.cod_materia || reportCourse.codigo_materia || ''
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const subject = safeFilenamePart(reportCourse.nombre_materia || subjectCode)
      const period = safeFilenamePart(reportCourse.detalle_periodos || reportCourse.detalle_periodo || periodos.join('-'))
      link.href = url
      link.download = `reporte-notas-secretaria-${subject}-${period}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el formato Secretaría')
    } finally {
      setDownloadingSecretaryReport(false)
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

  function clearSigningCredentials() {
    setSigningCertificate(null)
    setSigningPassword('')
    setShowSigningPassword(false)
    setSigningCertificateInputKey((current) => current + 1)
  }

  async function signComplianceReport(course: PortalTeacherCourse | null = selectedCourse) {
    if (!course) return
    const params = reportRequestParams(course, compliancePeriodCodes)
    if (!params) return
    if (params.periodos.length > 4) {
      setError('Seleccione máximo 4 periodos para generar el informe.')
      return
    }
    if (complianceStudents.length === 0 || selectedComplianceStudentCodes.length === 0) {
      setError('Cargue y seleccione al menos un estudiante para anexar calificaciones al informe.')
      return
    }
    if (complianceEvidenceFiles.notas.length === 0) {
      setError('Debe subir al menos una captura del reporte de notas antes de firmar.')
      return
    }
    if (!signingCertificate || !signingPassword) {
      setError('Seleccione el archivo .p12 e ingrese su contraseña.')
      return
    }
    if (!signingConsent) {
      setError('Confirme que es titular del certificado y que aprueba el contenido del informe.')
      return
    }

    setSelectedCourseKey(courseKey(course))
    setTargetCourseKey(courseKey(course))
    setSigningComplianceReport(true)
    setError('')
    setMessage('')
    try {
      const blob = await signPortalTeacherComplianceReport({
        codigoPeriodos: params.periodos,
        codAnioBasica: params.codAnioBasica,
        codigoMateria: params.subjectCode,
        paralelo: params.paralelo,
        codJornada: params.codJornada,
        codigoEstudiantes: selectedComplianceStudentCodes,
        fechaInicio: complianceStartDate,
        fechaFin: complianceEndDate,
        telefono: compliancePhone,
        actualizaciones: complianceUpdates,
        observaciones: complianceObservations,
        grabacionesTeams: complianceTeamsReportPayload,
        evidencias: evidencePayload(complianceEvidenceFiles),
        certificado: signingCertificate,
        contrasenaCertificado: signingPassword,
        firmaMotivo: signingReason,
        firmaUbicacion: signingLocation,
        firmaContacto: signingContact,
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const subject = safeFilenamePart(course.nombre_materia || params.subjectCode)
      const period = safeFilenamePart(compliancePeriodCodes.join('-') || course.detalle_periodos || course.detalle_periodo || params.periodos.join('-'))
      link.href = url
      link.download = `cumplimiento-docente-${subject}-${period}-firmado.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setSigningConsent(false)
      setMessage('Informe firmado y descargado. El certificado y la contraseña fueron descartados de esta pantalla.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo firmar electrónicamente el informe')
    } finally {
      clearSigningCredentials()
      setSigningComplianceReport(false)
    }
  }

  function closeReportPreview() {
    setReportPreviewUrl('')
  }

  function closeSecretaryReportPreview() {
    setSecretaryReportPreviewUrl('')
  }

  function closeCompliancePreview() {
    setCompliancePreviewUrl('')
  }

  useEffect(() => {
    void loadCourses()
  }, [loadCourses])

  useEffect(() => {
    if (!reportPreviewUrl) return
    return () => {
      window.URL.revokeObjectURL(reportPreviewUrl)
    }
  }, [reportPreviewUrl])

  useEffect(() => {
    if (!secretaryReportPreviewUrl) return
    return () => {
      window.URL.revokeObjectURL(secretaryReportPreviewUrl)
    }
  }, [secretaryReportPreviewUrl])

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
    const targetPool = initialMode === 'compliance' ? filteredExactCourses : filteredCourses
    if (targetPool.length === 0) {
      setTargetCourseKey('')
      return
    }
    if (!targetPool.some((course) => courseKey(course) === targetCourseKey)) {
      setTargetCourseKey(courseKey(targetPool[0]))
    }
  }, [filteredCourses, filteredExactCourses, initialMode, targetCourseKey])

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

  useEffect(() => {
    if (initialMode !== 'compliance' || !targetCourse) {
      setComplianceTeams([])
      setSelectedComplianceTeamId('')
      setComplianceRecordings([])
      setSelectedComplianceRecordingKeys([])
      return
    }
    let cancelled = false
    setLoadingComplianceTeams(true)
    setComplianceTeamsError('')
    setSelectedComplianceTeamId('')
    setComplianceRecordings([])
    setSelectedComplianceRecordingKeys([])

    void fetchMyTeamsCatalog()
      .then((payload) => {
        if (cancelled) return
        const periodCodes = targetCourse.codigo_periodos?.length
          ? targetCourse.codigo_periodos
          : targetCourse.codigo_periodo
            ? [targetCourse.codigo_periodo]
            : []
        const ranked = (payload.value || [])
          .filter((team) => Boolean(team.id))
          .map((team) => ({ team, score: teamCourseMatchScore(team, targetCourse, periodCodes) }))
          .sort((left, right) => right.score - left.score || String(left.team.displayName || '').localeCompare(String(right.team.displayName || ''), 'es'))
        const teams = ranked.map((item) => item.team)
        const bestMatch = ranked[0]
        setComplianceTeams(teams)
        setSelectedComplianceTeamId(
          bestMatch && (bestMatch.score >= 24 || ranked.length === 1) ? bestMatch.team.id || '' : ''
        )
        if (teams.length === 0) {
          setComplianceTeamsError('La cuenta docente no pertenece a ningún equipo de Teams.')
        } else if (!bestMatch || bestMatch.score < 24) {
          setComplianceTeamsError('Seleccione el equipo correspondiente; no se encontró una coincidencia segura con la materia.')
        }
      })
      .catch((apiError) => {
        if (cancelled) return
        setComplianceTeams([])
        setComplianceTeamsError(
          apiError instanceof Error ? apiError.message : 'No se pudieron consultar los equipos del docente'
        )
      })
      .finally(() => {
        if (!cancelled) setLoadingComplianceTeams(false)
      })
    return () => {
      cancelled = true
    }
  }, [complianceTeamsRefreshToken, initialMode, targetCourse])

  useEffect(() => {
    if (initialMode !== 'compliance' || !selectedComplianceTeamId) {
      setComplianceRecordings([])
      setSelectedComplianceRecordingKeys([])
      return
    }
    let cancelled = false
    setLoadingComplianceRecordings(true)
    setComplianceTeamsError('')
    void fetchMyTeamRecordings(selectedComplianceTeamId)
      .then((payload) => {
        if (cancelled) return
        const items = (payload.value || []).slice(0, 50)
        setComplianceRecordings(items)
        setSelectedComplianceRecordingKeys(items.map(recordingKey))
        if (items.length === 0) {
          setComplianceTeamsError('Microsoft Graph no encontró grabaciones en el equipo seleccionado.')
        }
      })
      .catch((apiError) => {
        if (cancelled) return
        setComplianceRecordings([])
        setSelectedComplianceRecordingKeys([])
        setComplianceTeamsError(
          apiError instanceof Error ? apiError.message : 'No se pudieron consultar las grabaciones del equipo'
        )
      })
      .finally(() => {
        if (!cancelled) setLoadingComplianceRecordings(false)
      })
    return () => {
      cancelled = true
    }
  }, [complianceRecordingsRefreshToken, initialMode, selectedComplianceTeamId])

  return (
    <div className="student-dashboard portal-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Portal docente</p>
          <h1>{initialMode === 'compliance' ? 'Informe de cumplimiento docente' : 'Mis cursos y subida de notas'}</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Bloques por período</span>
          <strong>{filteredCourses.length}</strong>
          <small>{totalAssignments} alcance(s) exacto(s)</small>
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
                    {option.label} - {option.count} bloque(s)
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
            <ol className="portal-compliance-steps" aria-label="Puntos del informe docente">
              <li><span>1</span><div><strong>Datos del informe</strong><small>Materia, periodos y fechas</small></div></li>
              <li><span>2</span><div><strong>Evidencias</strong><small>PEA, aula, TEAMS, asistencia y notas</small></div></li>
              <li><span>3</span><div><strong>Estudiantes</strong><small>Selección para el anexo de calificaciones</small></div></li>
              <li><span>4</span><div><strong>Firma electrónica</strong><small>Certificado temporal del docente</small></div></li>
            </ol>
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
                  <span>Evidencias documentales</span>
                  <h2>Evidencias del informe</h2>
                </div>
                <strong>
                  {evidencePayload(complianceEvidenceFiles).length + complianceTeamsReportPayload.length} evidencia(s)
                </strong>
              </div>
              <div className="portal-compliance-evidence-grid">
                {COMPLIANCE_EVIDENCE_OPTIONS.map((option, optionIndex) => (
                  <div
                    className={`portal-compliance-evidence-item${option.key === 'teams' ? ' portal-compliance-evidence-item--teams' : ''}`}
                    key={option.key}
                  >
                    <span className="portal-compliance-evidence-title"><b>{optionIndex + 1}</b>{option.label}{option.key === 'notas' ? ' *' : ''}</span>
                    {option.key === 'teams' ? (
                      <div className="portal-compliance-teams">
                        <div className="portal-compliance-teams-toolbar">
                          <label>
                            <span>Equipo asociado</span>
                            <select
                              value={selectedComplianceTeamId}
                              onChange={(event) => setSelectedComplianceTeamId(event.target.value)}
                              disabled={loadingComplianceTeams || complianceTeams.length === 0}
                            >
                              <option value="">Seleccione un equipo</option>
                              {complianceTeams.map((team) => (
                                <option key={team.id} value={team.id}>
                                  {team.displayName || team.id}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => setComplianceTeamsRefreshToken((current) => current + 1)}
                            disabled={loadingComplianceTeams}
                          >
                            {loadingComplianceTeams ? 'Buscando equipos...' : 'Buscar equipo'}
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => setComplianceRecordingsRefreshToken((current) => current + 1)}
                            disabled={!selectedComplianceTeamId || loadingComplianceRecordings}
                          >
                            {loadingComplianceRecordings ? 'Consultando...' : 'Actualizar grabaciones'}
                          </button>
                        </div>
                        {complianceTeamsError ? (
                          <p className="portal-compliance-teams-alert">{complianceTeamsError}</p>
                        ) : null}
                        {selectedComplianceTeam ? (
                          <div className="portal-compliance-teams-summary">
                            <div>
                              <span>Microsoft Graph</span>
                              <strong>{selectedComplianceTeam.displayName || 'Equipo seleccionado'}</strong>
                            </div>
                            <div>
                              <span>Encontradas</span>
                              <strong>{filteredComplianceRecordings.length}</strong>
                            </div>
                            <div>
                              <span>Incluidas</span>
                              <strong>{selectedComplianceRecordings.length}</strong>
                            </div>
                            <div className="portal-compliance-teams-selection-actions">
                              <button
                                type="button"
                                className="ghost-button"
                                onClick={() =>
                                  setSelectedComplianceRecordingKeys((current) =>
                                    Array.from(new Set([...current, ...filteredComplianceRecordings.map(recordingKey)]))
                                  )
                                }
                                disabled={filteredComplianceRecordings.length === 0}
                              >
                                Todas
                              </button>
                              <button
                                type="button"
                                className="ghost-button"
                                onClick={() => {
                                  const visibleKeys = new Set(filteredComplianceRecordings.map(recordingKey))
                                  setSelectedComplianceRecordingKeys((current) =>
                                    current.filter((key) => !visibleKeys.has(key))
                                  )
                                }}
                                disabled={filteredComplianceRecordings.length === 0}
                              >
                                Ninguna
                              </button>
                            </div>
                          </div>
                        ) : null}
                        {loadingComplianceRecordings ? (
                          <div className="portal-compliance-teams-empty">Consultando SharePoint, OneDrive y reuniones de Teams...</div>
                        ) : filteredComplianceRecordings.length > 0 ? (
                          <div className="excel-table-wrap portal-compliance-teams-table-wrap">
                            <table className="matricula-table portal-compliance-teams-table">
                              <thead>
                                <tr>
                                  <th>Incluye</th>
                                  <th>Fecha</th>
                                  <th>Grabación</th>
                                  <th>Inicio</th>
                                  <th>Fin</th>
                                  <th>Duración llamada</th>
                                  <th>Duración grabación</th>
                                  <th>Modificado por</th>
                                  <th>Enlace</th>
                                </tr>
                              </thead>
                              <tbody>
                                {filteredComplianceRecordings.map((recording) => {
                                  const key = recordingKey(recording)
                                  return (
                                    <tr key={key}>
                                      <td>
                                        <input
                                          type="checkbox"
                                          checked={selectedComplianceRecordingKeys.includes(key)}
                                          onChange={(event) =>
                                            setSelectedComplianceRecordingKeys((current) =>
                                              event.target.checked
                                                ? Array.from(new Set([...current, key]))
                                                : current.filter((value) => value !== key)
                                            )
                                          }
                                        />
                                      </td>
                                      <td>{recordingDateLabel(recording)}</td>
                                      <td>{recording.name || 'Grabación de clase'}</td>
                                      <td>{recording.callStartHourLabel || recording.recordingStartHourLabel || 'N/D'}</td>
                                      <td>{recording.callEndHourLabel || recording.recordingEndHourLabel || 'N/D'}</td>
                                      <td>{recording.callDurationClock || recording.callDurationLabel || 'N/D'}</td>
                                      <td>{recording.recordingDurationClock || recording.durationClock || recording.recordingDurationLabel || 'N/D'}</td>
                                      <td>{recording.lastModifiedByName || recording.createdByName || 'N/D'}</td>
                                      <td>
                                        {recording.webUrl ? (
                                          <a href={recording.webUrl} target="_blank" rel="noreferrer">Abrir</a>
                                        ) : 'N/D'}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        ) : selectedComplianceTeamId ? (
                          <div className="portal-compliance-teams-empty">Sin grabaciones para el rango de fechas seleccionado.</div>
                        ) : null}
                        <details className="portal-compliance-teams-fallback">
                          <summary>Agregar captura manual</summary>
                          <input
                            type="file"
                            accept="image/*"
                            multiple
                            onChange={(event) => {
                              const selectedFiles = Array.from(event.target.files || [])
                              setComplianceEvidenceFiles((current) => ({
                                ...current,
                                teams: [...current.teams, ...selectedFiles],
                              }))
                              event.target.value = ''
                            }}
                          />
                        </details>
                      </div>
                    ) : (
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
                    )}
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
                      <small>{option.key === 'teams' && complianceTeamsReportPayload.length > 0 ? 'Evidencia automática lista' : 'Sin capturas seleccionadas'}</small>
                    )}
                  </div>
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
            <section className="portal-signature-panel" aria-labelledby="portal-signature-title">
              <div className="section-title">
                <div>
                  <span>Firma electrónica</span>
                  <h2 id="portal-signature-title">Firmar informe con certificado .p12</h2>
                </div>
                <strong>Uso único por solicitud</strong>
              </div>
              <p>
                El certificado y la contraseña se utilizan únicamente para firmar este PDF. Al finalizar el intento,
                deberá seleccionarlos nuevamente para otra firma.
              </p>
              <div className="portal-signature-grid">
                <label className="portal-signature-certificate">
                  <span>Archivo de certificado</span>
                  <input
                    key={signingCertificateInputKey}
                    type="file"
                    accept=".p12,.pfx,application/x-pkcs12"
                    onChange={(event) => setSigningCertificate(event.target.files?.[0] || null)}
                  />
                  <small>{signingCertificate ? signingCertificate.name : 'Seleccione un archivo .p12 o .pfx de máximo 2 MB'}</small>
                </label>
                <label>
                  <span>Contraseña del certificado</span>
                  <div className="portal-signature-password">
                    <input
                      type={showSigningPassword ? 'text' : 'password'}
                      value={signingPassword}
                      onChange={(event) => setSigningPassword(event.target.value)}
                      autoComplete="new-password"
                      placeholder="Contraseña del archivo .p12"
                    />
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => setShowSigningPassword((current) => !current)}
                      aria-pressed={showSigningPassword}
                    >
                      {showSigningPassword ? 'Ocultar' : 'Mostrar'}
                    </button>
                  </div>
                </label>
                <label>
                  <span>Motivo de la firma</span>
                  <input value={signingReason} onChange={(event) => setSigningReason(event.target.value)} maxLength={200} />
                </label>
                <label>
                  <span>Ubicación</span>
                  <input value={signingLocation} onChange={(event) => setSigningLocation(event.target.value)} maxLength={120} />
                </label>
                <label>
                  <span>Contacto del firmante</span>
                  <input
                    value={signingContact}
                    onChange={(event) => setSigningContact(event.target.value)}
                    maxLength={200}
                    placeholder="Correo institucional (opcional)"
                  />
                </label>
              </div>
              <label className="portal-signature-consent">
                <input
                  type="checkbox"
                  checked={signingConsent}
                  onChange={(event) => setSigningConsent(event.target.checked)}
                />
                <span>Confirmo que soy titular del certificado y apruebo el contenido definitivo del informe.</span>
              </label>
              <div className="portal-signature-actions">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={clearSigningCredentials}
                  disabled={!signingCertificate && !signingPassword}
                >
                  Limpiar certificado
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={() => void signComplianceReport(targetCourse)}
                  disabled={signingComplianceReport || !targetCourse || !signingCertificate || !signingPassword || !signingConsent}
                >
                  {signingComplianceReport ? 'Firmando PDF...' : 'Firmar y descargar PDF'}
                </button>
              </div>
            </section>
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
                className="ghost-button"
                onClick={() => void downloadComplianceReport(targetCourse)}
                disabled={downloadingComplianceReport || !targetCourse}
              >
                {downloadingComplianceReport ? 'Generando informe...' : 'Descargar PDF sin firma'}
              </button>
            </div>
            {error ? <p className="form-error">{error}</p> : null}
            {message ? <p className="form-success">{message}</p> : null}
          </div>
          ) : null}

          {initialMode !== 'compliance' ? (
            <>
              <div className="portal-course-filter-summary">
                <span>{filteredCourses.length} bloque(s) por período</span>
                <span>{filteredSummary.regular} bloque(s) regular(es)</span>
                <span>{filteredSummary.homo} bloque(s) de homologación</span>
                <span>{filteredSummary.students} matrícula(s)</span>
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
                    <span>Código único: {course.cod_materia || course.codigo_materia || '-'}</span>
                    <small>{course.detalle_periodos || course.detalle_periodo || 'Período no informado'}</small>
                    <small>
                      {course.cod_anio_basicas?.length || 0} carrera(s) | {course.period_count || 0} período(s) | {course.assignment_count || courseAssignments(course).length} alcance(s)
                    </small>
                    <small>
                      {courseHasPeriodKind(course, 'R') ? 'Regular' : ''}
                      {courseHasPeriodKind(course, 'R') && courseHasPeriodKind(course, 'H') ? ' + ' : ''}
                      {courseHasPeriodKind(course, 'H') ? 'Homologación' : ''}
                    </small>
                    <b>{course.total_estudiantes || 0} matrícula(s)</b>
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
              {selectedCourse && courseHasPeriodKind(selectedCourse, 'R') && courseHasPeriodKind(selectedCourse, 'H') ? (
                <label className="portal-grade-partial-filter">
                  <span>Tipo de período</span>
                  <select
                    value={gradePeriodKind}
                    onChange={(event) => {
                      const kind = event.target.value as 'R' | 'H'
                      const periodCodes = defaultTeacherGradePeriods(selectedCourse, kind)
                      setGradePeriodKind(kind)
                      setSelectedGradePeriodCodes(periodCodes)
                      setGradePartial('P1')
                      void loadStudents(selectedCourse, kind, periodCodes)
                    }}
                  >
                    <option value="R">Regular</option>
                    <option value="H">Homologación</option>
                  </select>
                </label>
              ) : null}
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
                onClick={() => void loadStudents(selectedCourse, gradePeriodKind, selectedGradePeriodCodes)}
                disabled={loadingStudents || !selectedCourse}
              >
                {loadingStudents ? 'Consultando...' : 'Actualizar estudiantes'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void previewCourseReport()}
                disabled={previewingReport || !reportCourse}
              >
                {previewingReport ? 'Generando vista...' : 'Vista previa PDF'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void downloadCourseReport()}
                disabled={downloadingReport || !reportCourse}
              >
                {downloadingReport ? 'Generando PDF...' : 'Descargar PDF'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void previewSecretaryReport()}
                disabled={previewingSecretaryReport || !reportCourse}
              >
                {previewingSecretaryReport ? 'Generando vista...' : 'Vista formato Secretaría'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void downloadSecretaryReport()}
                disabled={downloadingSecretaryReport || !reportCourse}
              >
                {downloadingSecretaryReport ? 'Generando...' : 'Descargar formato Secretaría'}
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
            <section className="portal-grade-period-selector" aria-label="Períodos de calificación">
              <div className="portal-grade-period-copy">
                <strong>Período(s) a calificar</strong>
                <span>
                  {gradePeriodKind === 'R'
                    ? 'Seleccione uno o máximo dos períodos regulares distintos.'
                    : 'La homologación se consulta en un período independiente.'}
                </span>
              </div>
              <div className="portal-grade-period-options">
                {gradePeriodOptions.map((option) => {
                  const selected = selectedGradePeriodCodes.includes(option.code)
                  return (
                    <label
                      key={`${gradePeriodKind}-${option.code}`}
                      className={`portal-grade-period-option ${selected ? 'portal-grade-period-option--active' : ''}`}
                    >
                      <input
                        type={gradePeriodKind === 'H' ? 'radio' : 'checkbox'}
                        name={gradePeriodKind === 'H' ? 'teacher-homologation-period' : undefined}
                        checked={selected}
                        disabled={loadingStudents}
                        onChange={() => selectGradePeriod(option.code)}
                      />
                      <span>{option.label}</span>
                      <small>Código {option.code}</small>
                    </label>
                  )
                })}
              </div>
            </section>
          ) : null}

          {selectedCourse ? (
            <p className="portal-course-context">
              Código único {selectedCourse.cod_materia || selectedCourse.codigo_materia} | {selectedGradePeriodCodes.length} período(s) seleccionado(s) | {selectedGradeAssignments.length} asignación(es) {gradePeriodKind === 'H' ? 'de homologación' : 'regulares'}
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
                  <th>Carrera</th>
                  <th>Periodo</th>
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
                          <th>P1 proyectos 30%</th>
                          <th>P1 examen 40%</th>
                          <th>P1 prom.</th>
                        </>
                      ) : null}
                      {gradePartial === 'P2' ? (
                        <>
                          <th>P2 tareas 30%</th>
                          <th>P2 proyectos 30%</th>
                          <th>P2 examen 40%</th>
                          <th>P2 prom.</th>
                        </>
                      ) : null}
                      {gradePartial === 'P3' ? (
                        <>
                          <th>P3 tareas 30%</th>
                          <th>P3 proyectos 30%</th>
                          <th>P3 examen 40%</th>
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
                  const homo = courseUsesHomologation
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
                      <td>
                        <strong>{item.nombre_carrera || item.cod_anio_basica || '-'}</strong>
                        <small>Paralelo {item.paralelo || '-'}</small>
                      </td>
                      <td>
                        <strong>{item.detalle_periodo || item.codigo_periodo || '-'}</strong>
                        <small>Código {item.codigo_periodo || '-'}</small>
                      </td>
                      {homo ? (
                        <>
                          <td>
                            <input
                              className="portal-grade-input"
                              type="number"
                              min={0}
                              max={10}
                              step="0.01"
                              value={draft.teoria_homo}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'teoria_homo', event.target.value)}
                              placeholder={numberText(item.teoria_homo)}
                            />
                          </td>
                          <td>
                            <input
                              className="portal-grade-input"
                              type="number"
                              min={0}
                              max={10}
                              step="0.01"
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
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p1_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_tareas', event.target.value)} placeholder={numberText(item.p1_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p1_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_proyectos', event.target.value)} placeholder={numberText(item.p1_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p1_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p1_examen', event.target.value)} placeholder={numberText(item.p1_examen)} />
                              </td>
                              <td>
                                <span className="portal-grade-calculated">{numberText(calculatedRegular.promP1 ?? item.prom_p1)}</span>
                              </td>
                            </>
                          ) : null}
                          {gradePartial === 'P2' ? (
                            <>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p2_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_tareas', event.target.value)} placeholder={numberText(item.p2_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p2_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_proyectos', event.target.value)} placeholder={numberText(item.p2_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p2_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p2_examen', event.target.value)} placeholder={numberText(item.p2_examen)} />
                              </td>
                              <td>
                                <span className="portal-grade-calculated">{numberText(calculatedRegular.promP2 ?? item.prom_p2)}</span>
                              </td>
                            </>
                          ) : null}
                          {gradePartial === 'P3' ? (
                            <>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p3_tareas} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_tareas', event.target.value)} placeholder={numberText(item.p3_tareas)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p3_proyectos} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_proyectos', event.target.value)} placeholder={numberText(item.p3_proyectos)} />
                              </td>
                              <td>
                                <input className="portal-grade-input" type="number" min={0} max={10} step="0.01" value={draft.p3_examen} inputMode="decimal" onChange={(event) => updateDraft(item, 'p3_examen', event.target.value)} placeholder={numberText(item.p3_examen)} />
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
                              type="number"
                              min={0}
                              max={100}
                              step="0.01"
                              value={draft.asistencia}
                              inputMode="decimal"
                              onChange={(event) => updateDraft(item, 'asistencia', event.target.value)}
                              placeholder={numberText(item.asistencia)}
                            />
                          </td>
                          <td>
                            <input
                              className="portal-grade-input"
                              type="number"
                              min={0}
                              max={10}
                              step="0.01"
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

      {secretaryReportPreviewUrl ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-label="Vista previa del reporte de notas formato Secretaría">
          <article className="portal-report-preview-modal">
            <header>
              <div>
                <span>Vista previa</span>
                <h2>Reporte de notas formato Secretaría</h2>
                <p>{selectedCourse?.nombre_materia || 'Materia seleccionada'}</p>
              </div>
              <div className="portal-report-preview-actions">
                <button type="button" className="ghost-button" onClick={() => void downloadSecretaryReport()} disabled={downloadingSecretaryReport}>
                  {downloadingSecretaryReport ? 'Descargando...' : 'Descargar formato'}
                </button>
                <button type="button" className="primary-action" onClick={closeSecretaryReportPreview}>
                  Cerrar
                </button>
              </div>
            </header>
            <iframe src={secretaryReportPreviewUrl} title="Vista previa del reporte de notas formato Secretaría" />
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
