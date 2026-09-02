import { useEffect, useState, type ReactNode } from 'react'

import type {
  AcademicEnrollmentMode,
  MoodleSection,
  Page,
  PortalStudentSection,
  PracticasProcessCode,
  PreinscriptionStage,
  ScreenPermissionCode,
} from '../types/app'
import { MoodleGradeAlertIndicator } from '../features/moodle/MoodleGradeAlertIndicator'

type StudentLayoutProps = {
  activePage: Page
  activeSisAcademicoSection?: string
  activeLegacyReport?: string
  activePortalStudentSection?: PortalStudentSection
  activePreinscriptionStage?: PreinscriptionStage
  activeMatriculaAcadMode?: AcademicEnrollmentMode
  activeMoodleSection?: MoodleSection
  activePracticasProcess?: PracticasProcessCode
  role?: string
  screenAccessPages?: ScreenPermissionCode[] | null
  displayName?: string
  cedula?: string
  onOpenDashboard: () => void
  onOpenSistemaAcademico: () => void
  onOpenPortalEstudiante: (section?: PortalStudentSection) => void
  onOpenIngles: () => void
  onOpenExpedientesDocumentales: () => void
  onOpenPortalDocente: () => void
  onOpenPortalDocenteInforme: () => void
  onOpenPortalDocentePlanificacion: () => void
  onOpenPortalDocenteContratos: () => void
  onOpenTeams: () => void
  onOpenTeamsMatricula: () => void
  onOpenMoodleTeams: () => void
  onOpenHistoricoIntegraciones: () => void
  onOpenInformeCumplimiento: () => void
  onOpenMoodle: (section?: MoodleSection) => void
  onOpenMatricula: () => void
  onOpenMatriculaAcad: (mode?: AcademicEnrollmentMode) => void
  onOpenMatriculaDocente: () => void
  onOpenCareerChangeRequests: () => void
  onOpenModalityChangeRequests: () => void
  onOpenEstadoDocente: () => void
  onOpenSenescytEstudiantes: () => void
  onOpenActualizarDatosEstudiante: () => void
  onOpenActualizarCorreoIntec: () => void
  onOpenPreinscripcion: (stage?: PreinscriptionStage) => void
  onOpenReporteriaCarreras: () => void
  onOpenReporteriaIntegral: (reportKey?: string) => void
  onOpenReportesIndividuales: (reportKey?: string) => void
  onOpenAdminNotasAsignatura: () => void
  onOpenGestionSisAcademico: (sectionKey?: string) => void
  onOpenAsignacionPantallas: () => void
  onOpenPeriodoAcademico: () => void
  onOpenPeriodoMatriculados: () => void
  onOpenIngresoVentas: () => void
  onOpenCruceDatos: () => void
  onOpenValidarExcel: () => void
  onOpenRangoEdades: () => void
  onOpenFechaGrado: () => void
  onOpenTitulacion: () => void
  onOpenTitulacionProceso: () => void
  onOpenTitulacionResponsables: () => void
  onOpenTitulosRegistrados: (tipo?: string) => void
  onOpenCertificados: () => void
  onOpenMatriculaExcelCertificados: () => void
  onOpenCertificateRenamer: () => void
  onOpenCredentialGenerator: () => void
  onOpenMassEmail: () => void
  onOpenCarnetInstitucional: () => void
  onOpenTeacherEvaluation: () => void
  onOpenTeacherEvaluationAdmin: () => void
  onOpenTeacherEvaluationProgress: () => void
  onOpenTeacherEvaluationReports: () => void
  onOpenTeacherComplianceFormat: () => void
  onOpenPracticasInstitucionales: (process?: PracticasProcessCode) => void
  onLogout: () => void
  children: ReactNode
}

type NavItem = {
  label: string
  description?: string
  page?: Page
  accessCode?: ScreenPermissionCode
  sectionKey?: string
  reportKey?: string
  portalSection?: PortalStudentSection
  preinscriptionStage?: PreinscriptionStage
  moodleSection?: MoodleSection
  practicasProcess?: PracticasProcessCode
  category?: string
  action: () => void
}

type NavGroup = {
  key: string
  title: string
  summary: string
  items: NavItem[]
}

const roleBrandMap: Record<string, { initials: string; title: string }> = {
  '1': { initials: 'AD', title: 'Administración' },
  ADMINISTRADOR: { initials: 'AD', title: 'Administración' },
  ADMINISTRACION: { initials: 'AD', title: 'Administración' },
  ADMINISTRACIÓN: { initials: 'AD', title: 'Administración' },
  ADMIN: { initials: 'AD', title: 'Administración' },
  FINANCIERO: { initials: 'FI', title: 'Financiero' },
  BIENESTAR: { initials: 'BI', title: 'Bienestar' },
  ACADEMICO: { initials: 'AC', title: 'Académico' },
  ADMISIONES: { initials: 'AM', title: 'Admisiones' },
  RECTOR: { initials: 'RC', title: 'Rectoria' },
  VICERRECTOR: { initials: 'VR', title: 'Vicerrectoria' },
  SOPORTE: { initials: 'TI', title: 'Tecnología' },
  INVITADO_SOP: { initials: 'IS', title: 'Invitado soporte' },
  SECRETARIA: { initials: 'SE', title: 'Secretaría' },
  DOCENTE: { initials: 'DC', title: 'Docente' },
  ESTUDIANTE: { initials: 'ES', title: 'Estudiante' },
  TECNOLOGIA: { initials: 'TI', title: 'Tecnologia' },
  TI: { initials: 'TI', title: 'Tecnologia' },
}

const administratorRoles = new Set(['1', 'ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN'])
const administratorOnlyPages = new Set<Page>(['sistema-academico', 'asignacion-pantallas'])
const academicRoles = new Set(['ACADEMICO', 'BIENESTAR'])
const dashboardOnlyRoles = new Set(['RECTOR', 'VICERRECTOR'])
const technicalGlobalRoles = new Set(['ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN', 'SOPORTE'])
const studentPortalPages = new Set<Page>([
  'portal-estudiante',
  'portal-estudiante-malla-curricular',
  'portal-estudiante-malla-academica',
  'portal-estudiante-calificaciones',
])
const financialPages = new Set<Page>(['dashboard', 'preinscripcion', 'ingreso-ventas', 'gestion-sisacademico', 'reporteria-integral', 'carnet-institucional'])
const academicPages = new Set<Page>([
  'dashboard',
  'preinscripcion',
  'matricula',
  'matricula-acad',
  'matricula-docente',
  'solicitudes-cambio-carrera',
  'solicitudes-cambio-modalidad',
  'estado-docente',
  'actualizar-datos-estudiante',
  'actualizar-correo-intec',
  'reportes-individuales',
  'admin-notas-asignatura',
  'reporteria-integral',
  'gestion-sisacademico',
  'periodo-academico',
  'periodo-matriculados',
  'rango-edades',
  'certificados',
  'fecha-grado',
  'titulacion',
  'titulacion-proceso',
  'titulacion-responsables',
  'matricula-excel-certificados',
  'renombrar-certificados',
  'carnet-institucional',
  'evaluacion-docente-avance',
  'evaluacion-docente-reportes',
  'formato-informe-docente',
  'informe-cumplimiento',
  'practicas-institucionales',
  'ingles',
  'expedientes-documentales',
])
const academicSisSections = new Set([
  'estudiantes',
  'registro_documentos_estudiante',
  'correos',
  'matricula_materias',
  'seguimiento',
  'actualizacion_estudiantes',
  'docentes',
  'docente_materias',
  'actualizacion_est',
  'preguntas_evaluacion',
  'evaluacion_resultados',
  'autoevaluacion_resultados',
  'fechas_autoevaluacion',
  'carreras',
  'materias',
  'mallas',
  'paralelos',
  'periodos',
  'fechas_notas',
  'asistencia_estudiantes',
  'jornadas',
  'modalidades',
  'practicas',
  'practicas_vinculacion',
  'empresas',
  'certificados_generados',
])
const financialSisSections = new Set(['cabecera_matricula', 'pagos_matricula', 'datos_factura'])
const academicReportKeys = new Set(['notas_carrera_materia', 'evaluacion_docente', 'genero_docentes'])
const financialReportKeys = new Set(['provincia', 'genero', 'carrera', 'periodo', 'graduados_2025'])
const admissionsPages = new Set<Page>(['dashboard', 'preinscripcion', 'gestion-sisacademico'])
const admissionsSisSections = new Set(['preinscripciones', 'estudiantes', 'cabecera_matricula', 'pagos_matricula', 'datos_factura'])
const secretaryPages = new Set<Page>(['solicitudes-cambio-carrera', 'solicitudes-cambio-modalidad', 'practicas-institucionales', 'fecha-grado', 'senescyt-estudiantes', 'titulacion', 'titulacion-proceso', 'titulacion-responsables', 'titulos-registrados', 'expedientes-documentales', 'informe-cumplimiento'])

function normalizeRoleKey(role: string) {
  return role
    .trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function isAdministratorRole(role: string) {
  return administratorRoles.has(normalizeRoleKey(role))
}

function navItemAllowedForRole(role: string, item: NavItem) {
  const normalizedRole = normalizeRoleKey(role)
  const isAdministrator = isAdministratorRole(normalizedRole)

  if (item.page && administratorOnlyPages.has(item.page) && !isAdministrator) return false
  if (item.page === 'expedientes-documentales' && !['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA', 'FINANCIERO'].includes(normalizedRole)) return false

  if (normalizedRole === 'ESTUDIANTE') return Boolean(item.page && studentPortalPages.has(item.page)) || item.page === 'ingles' || item.page === 'evaluacion-docente' || item.page === 'practicas-institucionales' || item.page === 'carnet-institucional'
  if (normalizedRole === 'DOCENTE') return item.page === 'portal-docente' || item.page === 'ingles' || item.page === 'portal-docente-informe' || item.page === 'portal-docente-planificacion' || item.page === 'portal-docente-contratos' || item.page === 'practicas-institucionales' || item.page === 'carnet-institucional' || item.moodleSection === 'alerts'
  if (normalizedRole === 'ADMISIONES') {
    if (!item.page || !admissionsPages.has(item.page)) return false
    if (item.page === 'gestion-sisacademico' && item.sectionKey && !admissionsSisSections.has(item.sectionKey)) return false
    return true
  }
  if (normalizedRole === 'SECRETARIA') {
    return Boolean(item.page && secretaryPages.has(item.page))
  }
  if (dashboardOnlyRoles.has(normalizedRole)) return item.page === 'dashboard'
  if (academicRoles.has(normalizedRole)) {
    if (item.moodleSection === 'alerts') return true
    if (!item.page || !academicPages.has(item.page)) return false
    if (item.page === 'gestion-sisacademico' && item.sectionKey && !academicSisSections.has(item.sectionKey)) return false
    if (item.reportKey && !academicReportKeys.has(item.reportKey)) return false
    return true
  }
  if (normalizedRole === 'FINANCIERO') {
    if (!item.page || !financialPages.has(item.page)) return false
    if (item.page === 'gestion-sisacademico' && item.sectionKey && !financialSisSections.has(item.sectionKey)) return false
    if (item.reportKey && !financialReportKeys.has(item.reportKey)) return false
    return true
  }
  if (isAdministrator || technicalGlobalRoles.has(normalizedRole)) return (!item.page || !studentPortalPages.has(item.page)) && item.page !== 'portal-docente' && item.page !== 'portal-docente-informe' && item.page !== 'portal-docente-planificacion' && item.page !== 'portal-docente-contratos'
  return item.page === 'dashboard'
}

function navItemAccessCode(item: NavItem): ScreenPermissionCode {
  if (item.accessCode) return item.accessCode
  if (!item.page) return ''
  if (item.moodleSection) return `${item.page}/${item.moodleSection}`
  if (item.sectionKey) return `${item.page}/${item.sectionKey}`
  if (item.reportKey) return `${item.page}/${item.reportKey}`
  if (item.preinscriptionStage) return `${item.page}/${item.preinscriptionStage}`
  return item.page
}

function navItemIdentity(item: NavItem) {
  const accessCode = navItemAccessCode(item)
  if (accessCode) {
    return item.practicasProcess
      ? `access:${accessCode}:process:${item.practicasProcess}`
      : `access:${accessCode}`
  }
  return [
    item.portalSection || '',
    item.label,
  ].join('|')
}

function mergeNavigationGroups(groups: NavGroup[]) {
  const merged = new Map<string, NavGroup>()
  const seenItems = new Set<string>()

  groups.forEach((group) => {
    const availableItems = group.items.filter((item) => {
      const identity = navItemIdentity(item)
      if (seenItems.has(identity)) return false
      seenItems.add(identity)
      return true
    })
    if (availableItems.length === 0) return

    const existing = merged.get(group.key)
    if (existing) {
      existing.items.push(...availableItems)
      return
    }
    merged.set(group.key, { ...group, items: [...availableItems] })
  })

  return [...merged.values()]
}

function buildAssignedMenuGroups(
  roleGroups: NavGroup[],
  catalogGroups: NavGroup[],
  assignedPages: ScreenPermissionCode[],
) {
  const assignedSet = new Set(assignedPages)
  const permissionsRepresentedByRole = new Set(
    roleGroups.flatMap((group) => group.items.map(navItemAccessCode).filter(Boolean)),
  )
  const permissionsMissingFromRole = new Set(
    assignedPages.filter((page) => !permissionsRepresentedByRole.has(page)),
  )

  const assignedRoleGroups = roleGroups.flatMap((group) => {
    const items = group.items.filter((item) => assignedSet.has(navItemAccessCode(item)))
    return items.length > 0 ? [{ ...group, items }] : []
  })
  const assignedFallbackGroups = catalogGroups.flatMap((group) => {
    const items = group.items.filter((item) => permissionsMissingFromRole.has(navItemAccessCode(item)))
    return items.length > 0 ? [{ ...group, items }] : []
  })

  return mergeNavigationGroups([...assignedRoleGroups, ...assignedFallbackGroups])
}

function titleFromRole(role: string) {
  return role
    .toLowerCase()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function initialsFromTitle(title: string) {
  const initials = title
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return initials || 'IN'
}

function compareNavigationLabels(left: string, right: string) {
  return left.localeCompare(right, 'es-EC', {
    sensitivity: 'base',
    numeric: true,
  })
}

function sortNavItems(items: NavItem[]) {
  return [...items].sort((left, right) => {
    const categoryCompare = compareNavigationLabels(left.category || '', right.category || '')
    if (categoryCompare !== 0) return categoryCompare
    return compareNavigationLabels(left.label, right.label)
  })
}

function sortNavGroups(groups: NavGroup[]) {
  return [...groups].sort((left, right) => compareNavigationLabels(left.title, right.title))
}

type GroupIconName =
  | 'home'
  | 'status'
  | 'admission'
  | 'certificate'
  | 'student'
  | 'teacher'
  | 'users'
  | 'id-card'
  | 'briefcase'
  | 'catalog'
  | 'report'
  | 'integration'
  | 'academic'
  | 'matricula'

function groupIconName(groupKey: string): GroupIconName {
  const iconMap: Record<string, GroupIconName> = {
    inicio: 'home',
    'actualizacion-estados': 'status',
    'admision-matriculas': 'matricula',
    matriculacion: 'matricula',
    admisiones: 'admission',
    becas: 'briefcase',
    'admision-consultas': 'admission',
    migracion: 'matricula',
    certificados: 'certificate',
    'dashboard-estudiante': 'home',
    'portal-estudiante': 'student',
    'malla-estudiante': 'catalog',
    'practicas-estudiante': 'briefcase',
    idiomas: 'academic',
    'expedientes-documentales': 'certificate',
    'portal-docente': 'teacher',
    administracion: 'users',
    desempeno: 'academic',
    carnetizacion: 'id-card',
    vinculacion: 'briefcase',
    catalogos: 'catalog',
    reporteria: 'report',
    calificaciones: 'academic',
    'datos-senecyt': 'report',
    auditoria: 'report',
    solicitudes: 'academic',
    integraciones: 'integration',
    moodle: 'integration',
    'admision-integraciones': 'integration',
    'admision-control': 'matricula',
  }

  return iconMap[groupKey] || 'academic'
}

function GroupIcon({ name }: { name: GroupIconName }) {
  switch (name) {
    case 'home':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V21h14V9.5" />
          <path d="M9 21v-6h6v6" />
        </svg>
      )
    case 'status':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7h10a5 5 0 0 1 5 5v1" />
          <path d="m16 4 3 3-3 3" />
          <path d="M20 17H10a5 5 0 0 1-5-5v-1" />
          <path d="m8 20-3-3 3-3" />
        </svg>
      )
    case 'admission':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
          <path d="M3 21a6 6 0 0 1 12 0" />
          <path d="M19 8v8" />
          <path d="M15 12h8" />
        </svg>
      )
    case 'matricula':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5h16v14H4z" />
          <path d="M8 9h8" />
          <path d="M8 13h5" />
          <path d="m15 17 1.7 1.7L21 14.5" />
        </svg>
      )
    case 'certificate':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 3h8l4 4v14H6z" />
          <path d="M14 3v5h5" />
          <path d="m9 15 2 2 4-5" />
        </svg>
      )
    case 'student':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m3 8 9-4 9 4-9 4-9-4Z" />
          <path d="M7 10.5V15c0 1.7 2.2 3 5 3s5-1.3 5-3v-4.5" />
          <path d="M20 9v5" />
        </svg>
      )
    case 'teacher':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5h16v10H4z" />
          <path d="M8 21h8" />
          <path d="M12 15v6" />
          <path d="M8 9h8" />
        </svg>
      )
    case 'users':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M16 11a4 4 0 1 0-8 0" />
          <path d="M5 21a7 7 0 0 1 14 0" />
          <path d="M18 7a3 3 0 0 1 3 3" />
          <path d="M3 10a3 3 0 0 1 3-3" />
        </svg>
      )
    case 'id-card':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5h16v14H4z" />
          <path d="M9 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
          <path d="M6.5 16a3 3 0 0 1 5 0" />
          <path d="M14 10h4" />
          <path d="M14 14h4" />
        </svg>
      )
    case 'briefcase':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 7V5h6v2" />
          <path d="M4 7h16v12H4z" />
          <path d="M4 12h16" />
          <path d="M10 12v2h4v-2" />
        </svg>
      )
    case 'catalog':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H20v17H7.5A3.5 3.5 0 0 0 4 22Z" />
          <path d="M4 5.5V22" />
          <path d="M8 7h8" />
          <path d="M8 11h7" />
        </svg>
      )
    case 'report':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 19V5" />
          <path d="M5 19h15" />
          <path d="M9 16v-5" />
          <path d="M13 16V8" />
          <path d="M17 16v-3" />
        </svg>
      )
    case 'integration':
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 8h8v8H8z" />
          <path d="M12 2v6" />
          <path d="M12 16v6" />
          <path d="M2 12h6" />
          <path d="M16 12h6" />
        </svg>
      )
    case 'academic':
    default:
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 19V6l8-3 8 3v13" />
          <path d="M8 19v-7h8v7" />
          <path d="M3 21h18" />
        </svg>
      )
  }
}

export function StudentLayout({
  activePage,
  activeSisAcademicoSection = '',
  activeLegacyReport = '',
  activePortalStudentSection = 'dashboard',
  activePreinscriptionStage = 'registro',
  activeMatriculaAcadMode = 'individual',
  activeMoodleSection = 'status',
  activePracticasProcess = 'PPF',
  role = '',
  screenAccessPages = null,
  displayName = '',
  cedula = '',
  onOpenDashboard,
  onOpenSistemaAcademico,
  onOpenPortalEstudiante,
  onOpenIngles,
  onOpenExpedientesDocumentales,
  onOpenPortalDocente,
  onOpenPortalDocenteInforme,
  onOpenPortalDocentePlanificacion,
  onOpenPortalDocenteContratos,
  onOpenTeams,
  onOpenTeamsMatricula,
  onOpenMoodleTeams,
  onOpenHistoricoIntegraciones,
  onOpenInformeCumplimiento,
  onOpenMoodle,
  onOpenMatricula,
  onOpenMatriculaAcad,
  onOpenMatriculaDocente,
  onOpenCareerChangeRequests,
  onOpenModalityChangeRequests,
  onOpenEstadoDocente,
  onOpenSenescytEstudiantes,
  onOpenActualizarDatosEstudiante,
  onOpenActualizarCorreoIntec,
  onOpenPreinscripcion,
  onOpenReporteriaCarreras,
  onOpenReporteriaIntegral,
  onOpenReportesIndividuales,
  onOpenAdminNotasAsignatura,
  onOpenGestionSisAcademico,
  onOpenAsignacionPantallas,
  onOpenPeriodoAcademico,
  onOpenPeriodoMatriculados,
  onOpenIngresoVentas,
  onOpenCruceDatos,
  onOpenValidarExcel,
  onOpenRangoEdades,
  onOpenFechaGrado,
  onOpenTitulacion,
  onOpenTitulacionProceso,
  onOpenTitulacionResponsables,
  onOpenTitulosRegistrados,
  onOpenCertificados,
  onOpenMatriculaExcelCertificados,
  onOpenCertificateRenamer,
  onOpenCredentialGenerator,
  onOpenMassEmail,
  onOpenCarnetInstitucional,
  onOpenTeacherEvaluation,
  onOpenTeacherEvaluationAdmin,
  onOpenTeacherEvaluationProgress,
  onOpenTeacherEvaluationReports,
  onOpenTeacherComplianceFormat,
  onOpenPracticasInstitucionales,
  onLogout,
  children,
}: Readonly<StudentLayoutProps>) {
  const normalizedRole = normalizeRoleKey(role)
  const isAdministrator = isAdministratorRole(normalizedRole)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobileViewport, setIsMobileViewport] = useState(false)
  const [openMenuGroups, setOpenMenuGroups] = useState<Set<string>>(
    () => new Set([normalizedRole === 'ESTUDIANTE' ? 'dashboard-estudiante' : 'solicitudes']),
  )

  useEffect(() => {
    const syncMobileState = () => {
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth
      const isMobile = viewportWidth <= 1180
      setIsMobileViewport(isMobile)
      if (!isMobile) {
        setMobileMenuOpen(false)
      }
    }

    syncMobileState()
    window.addEventListener('resize', syncMobileState)

    return () => {
      window.removeEventListener('resize', syncMobileState)
    }
  }, [])

  useEffect(() => {
    if (!mobileMenuOpen) return undefined

    const previousOverflow = document.body.style.overflow
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileMenuOpen(false)
    }

    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeWithEscape)

    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeWithEscape)
    }
  }, [mobileMenuOpen])

  const preinscriptionFlowItems: NavItem[] = [
    {
      label: 'Inscripción',
      description: 'Registrar los datos iniciales de un nuevo aspirante.',
      page: 'preinscripcion',
      preinscriptionStage: 'registro',
      category: '1. Inscripción',
      action: () => onOpenPreinscripcion('registro'),
    },
    {
      label: 'Estudiantes inscritos',
      description: 'Buscar y seleccionar aspirantes registrados para continuar el proceso.',
      page: 'preinscripcion',
      preinscriptionStage: 'inscritos',
      category: '1. Inscripción',
      action: () => onOpenPreinscripcion('inscritos'),
    },
    {
      label: 'Subida de documentos',
      description: 'Cargar y validar los documentos requeridos del estudiante.',
      page: 'preinscripcion',
      preinscriptionStage: 'documentos',
      category: '2. Documentación',
      action: () => onOpenPreinscripcion('documentos'),
    },
    {
      label: 'Seguimiento del estudiante',
      description: 'Registrar contactos, avance, novedades y cierre de la admisión.',
      page: 'preinscripcion',
      preinscriptionStage: 'seguimiento',
      category: '3. Seguimiento',
      action: () => onOpenPreinscripcion('seguimiento'),
    },
    {
      label: 'Preparar primera matrícula',
      description: 'Generar la cabecera, los valores, el pago y el convenio de matrícula.',
      page: 'preinscripcion',
      preinscriptionStage: 'cabecera',
      category: '4. Primera matrícula',
      action: () => onOpenPreinscripcion('cabecera'),
    },
    {
      label: 'Primera matrícula',
      description: 'Matricular las materias habilitadas del primer nivel.',
      page: 'preinscripcion',
      preinscriptionStage: 'materias',
      category: '4. Primera matrícula',
      action: () => onOpenPreinscripcion('materias'),
    },
  ]
  const practicesInstitutionalMenuItems: NavItem[] = [
    {
      label: 'Prácticas laborales / preprofesionales',
      description: 'Inscripción institucional, responsable, plan, horas, documentos y cierre.',
      page: 'practicas-institucionales',
      practicasProcess: 'PPF',
      action: () => onOpenPracticasInstitucionales('PPF'),
    },
    {
      label: 'Vinculación con la sociedad',
      description: 'Inscripción institucional, proyecto, actividades, indicadores, evidencias y cierre.',
      page: 'practicas-institucionales',
      practicasProcess: 'VIN',
      action: () => onOpenPracticasInstitucionales('VIN'),
    },
  ]

  const admissionsMenuGroup: NavGroup = {
    key: 'admisiones',
    title: 'Admisiones',
    summary: 'Inscripción, documentos, seguimiento y primera matrícula',
    items: preinscriptionFlowItems,
  }
  const salesPreinscriptionFlowItems = preinscriptionFlowItems.filter((item) =>
    item.preinscriptionStage === 'registro' || item.preinscriptionStage === 'documentos',
  )
  const auditMenuGroup: NavGroup = {
    key: 'auditoria',
    title: 'Auditoría',
    summary: 'Trazabilidad de cambios y documentos',
    items: [
      {
        label: 'Movimientos',
        description: 'Consultar inserciones, actualizaciones, eliminaciones e informes docentes.',
        page: 'historico-integraciones',
        action: onOpenHistoricoIntegraciones,
      },
    ],
  }
  const updatesMenuGroup: NavGroup = {
    key: 'actualizacion-estados',
    title: 'Actualización',
    summary: 'Datos, correo, estados y grado',
    items: [
      {
        label: 'Actualización de datos',
        description: 'Actualizar información personal de estudiantes y docentes.',
        page: 'actualizar-datos-estudiante',
        action: onOpenActualizarDatosEstudiante,
      },
      {
        label: 'Correo INTEC',
        description: 'Consultar y actualizar correo institucional y credenciales estudiantiles.',
        page: 'actualizar-correo-intec',
        action: onOpenActualizarCorreoIntec,
      },
      {
        label: 'Estado docente',
        description: 'Activar o inactivar docentes validando DATOSDOCENTE y USUARIOS.',
        page: 'gestion-sisacademico',
        sectionKey: 'actualizacion_est',
        action: () => onOpenGestionSisAcademico('actualizacion_est'),
      },
      {
        label: 'Estado estudiante',
        description: 'Activar o inactivar estudiantes desde DATOS_ESTUD usando ESTADO.',
        page: 'gestion-sisacademico',
        sectionKey: 'actualizacion_estudiantes',
        action: () => onOpenGestionSisAcademico('actualizacion_estudiantes'),
      },
      {
        label: 'Fecha de grado',
        description: 'Actualizar fecha de grado, emisión SENESCYT y código de refrendación.',
        page: 'fecha-grado',
        action: onOpenFechaGrado,
      },
    ],
  }
  const enrollmentMenuGroup: NavGroup = {
    key: 'matriculacion',
    title: 'Matrícula',
    summary: 'Estudiantes, docentes y configuración académica',
    items: [
      {
        label: 'Consulta de matrícula',
        description: 'Consultar la información general de matrícula.',
        page: 'matricula',
        action: onOpenMatricula,
      },
      {
        label: 'Matrícula individual',
        description: 'Buscar por nombre, cédula o código y matricular materias.',
        page: 'matricula-acad',
        sectionKey: 'individual',
        action: () => onOpenMatriculaAcad('individual'),
      },
      {
        label: 'Matrícula masiva',
        description: 'Matricular una cohorte completa en un período destino.',
        page: 'matricula-acad',
        sectionKey: 'masiva',
        action: () => onOpenMatriculaAcad('masiva'),
      },
      {
        label: 'Matrícula docente',
        description: 'Asignar docentes activos a materias, períodos y estudiantes.',
        page: 'matricula-docente',
        action: onOpenMatriculaDocente,
      },
      {
        label: 'Prerrequisitos de materias',
        description: 'Crear y administrar las relaciones entre materias.',
        page: 'matricula-acad',
        sectionKey: 'prerrequisitos',
        action: () => onOpenMatriculaAcad('prerrequisitos'),
      },
      {
        label: 'Matriculados por período',
        description: 'Revisar estudiantes matriculados por período académico.',
        page: 'periodo-matriculados',
        action: onOpenPeriodoMatriculados,
      },
    ],
  }
  const requestsMenuGroup: NavGroup = {
    key: 'solicitudes',
    title: 'Solicitudes',
    summary: 'Trámites y decisiones académicas',
    items: [
      {
        label: 'Cambio de carrera',
        description: 'Comparar equivalencias, adjuntar el respaldo y gestionar el cambio de carrera.',
        page: 'solicitudes-cambio-carrera',
        action: onOpenCareerChangeRequests,
      },
      {
        label: 'Cambio de modalidad',
        description: 'Seleccionar carrera, modalidad y período destino en una sola matrícula.',
        page: 'solicitudes-cambio-modalidad',
        action: onOpenModalityChangeRequests,
      },
    ],
  }
  const scholarshipMenuGroup: NavGroup = {
    key: 'becas',
    title: 'Becas',
    summary: 'Configuración, aprobación y beneficiarios',
    items: [
      {
        label: 'Gestión de becas',
        description: 'Configurar tipos, porcentajes y disponibilidad en inscripción.',
        page: 'preinscripcion',
        preinscriptionStage: 'gestion-becas',
        action: () => onOpenPreinscripcion('gestion-becas'),
      },
      {
        label: 'Aprobaciones pendientes',
        description: 'Revisar solicitudes de beca superiores al 15%.',
        page: 'preinscripcion',
        preinscriptionStage: 'becas',
        action: () => onOpenPreinscripcion('becas'),
      },
      {
        label: 'Listado de becados',
        description: 'Consultar estudiantes con becas aprobadas y sus porcentajes.',
        page: 'preinscripcion',
        preinscriptionStage: 'becados',
        action: () => onOpenPreinscripcion('becados'),
      },
      {
        label: 'Contratos de beca',
        description: 'Seleccionar beneficiarios activos y generar sus contratos.',
        page: 'preinscripcion',
        preinscriptionStage: 'contratos-becas',
        action: () => onOpenPreinscripcion('contratos-becas'),
      },
    ],
  }
  const certificateMenuGroup: NavGroup = {
    key: 'certificados',
    title: 'Certificados',
    summary: 'Generación, historial y archivos',
    items: [
      {
        label: 'Matrícula y promoción por período',
        description: 'Seleccionar un período y generar ambos tipos de certificado desde las matrículas registradas.',
        page: 'certificados',
        action: onOpenCertificados,
      },
      {
        label: 'Historial de certificados',
        description: 'Consultar los certificados generados automáticamente y su estado.',
        page: 'gestion-sisacademico',
        sectionKey: 'certificados_generados',
        action: () => onOpenGestionSisAcademico('certificados_generados'),
      },
      {
        label: 'Certificados desde Excel',
        description: 'Generar certificados de matrícula desde una plantilla Excel.',
        page: 'matricula-excel-certificados',
        action: onOpenMatriculaExcelCertificados,
      },
      {
        label: 'Renombrar certificados',
        description: 'Leer la cédula en cada PDF y renombrarlo con los datos del estudiante.',
        page: 'renombrar-certificados',
        action: onOpenCertificateRenamer,
      },
    ],
  }
  const academicLifecycleItems: NavItem[] = [
    {
      label: 'Sistema académico',
      description: 'Centro operativo del ciclo completo del estudiante.',
      page: 'sistema-academico',
      category: 'Vista general',
      action: onOpenSistemaAcademico,
    },
    {
      label: '1. Inscripción y admisión',
      description: 'Registrar aspirante, revisar datos de factura y documentos de ingreso.',
      page: 'preinscripcion',
      preinscriptionStage: 'registro',
      category: 'Flujo académico',
      action: () => onOpenPreinscripcion('registro'),
    },
    {
      label: '2. Actualización de datos',
      description: 'Actualizar datos de estudiantes y docentes antes de matrícula o continuidad.',
      page: 'actualizar-datos-estudiante',
      category: 'Flujo académico',
      action: onOpenActualizarDatosEstudiante,
    },
    {
      label: '3. Matriculación de estudiantes',
      description: 'Registrar la cabecera y las materias de cada matrícula.',
      page: 'matricula-acad',
      sectionKey: 'individual',
      category: 'Flujo académico',
      action: () => onOpenMatriculaAcad('individual'),
    },
    {
      label: '4. Cursado y notas',
      description: 'Revisar materias matriculadas, notas, asistencia y seguimiento académico.',
      page: 'gestion-sisacademico',
      sectionKey: 'matricula_materias',
      category: 'Flujo académico',
      action: () => onOpenGestionSisAcademico('matricula_materias'),
    },
    {
      label: '5. Docencia y evaluación',
      description: 'Asignar docentes, revisar evaluación docente y cumplimiento académico.',
      page: 'matricula-docente',
      category: 'Flujo académico',
      action: onOpenMatriculaDocente,
    },
    {
      label: '6. Prácticas y vinculación',
      description: 'Gestionar prácticas preprofesionales y vinculación con la sociedad.',
      page: 'practicas-institucionales',
      category: 'Flujo académico',
      action: onOpenPracticasInstitucionales,
    },
    {
      label: '7. Titulación',
      description: 'Verificar requisitos, definir modalidad, responsables, acta y registro final.',
      page: 'titulacion',
      category: 'Flujo académico',
      action: onOpenTitulacion,
    },
  ]

  const adminMenuGroups: NavGroup[] = [
    {
      key: 'flujo-academico',
      title: 'Flujo académico',
      summary: 'Inscripción a titulación',
      items: academicLifecycleItems,
    },
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Vista general',
      items: [
        { label: 'Dashboard', description: 'Indicadores principales del sistema.', page: 'dashboard', action: onOpenDashboard },
      ],
    },
    {
      key: 'matriculacion',
      title: 'Matrícula',
      summary: 'Estudiantes, matrícula académica y pagos',
      items: [
        {
          label: 'Aspirantes y asesores',
          description: 'Gestión directa de inscripciones.',
          category: 'Consulta directa',
          page: 'gestion-sisacademico',
          sectionKey: 'preinscripciones',
          action: () => onOpenGestionSisAcademico('preinscripciones'),
        },
        {
          label: 'Datos de factura',
          description: 'Datos tributarios vinculados a la inscripción y matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'datos_factura',
          action: () => onOpenGestionSisAcademico('datos_factura'),
        },
        {
          label: 'Matrícula individual',
          description: 'Buscar y matricular las materias de un estudiante.',
          page: 'matricula-acad',
          sectionKey: 'individual',
          action: () => onOpenMatriculaAcad('individual'),
        },
        {
          label: 'Cabecera de matrícula y pagos',
          description: 'Valores, documentos, jornada y control de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'cabecera_matricula',
          action: () => onOpenGestionSisAcademico('cabecera_matricula'),
        },
        {
          label: 'Materias matriculadas y notas',
          description: 'Materias, paralelos y calificaciones del estudiante.',
          page: 'gestion-sisacademico',
          sectionKey: 'matricula_materias',
          action: () => onOpenGestionSisAcademico('matricula_materias'),
        },
        {
          label: 'Pagos y valores',
          description: 'Registro editable de pagos, descuentos y valores.',
          page: 'gestion-sisacademico',
          sectionKey: 'pagos_matricula',
          action: () => onOpenGestionSisAcademico('pagos_matricula'),
        },
      ],
    },
    {
      key: 'calificaciones',
      title: 'Calificaciones',
      summary: 'Estudiantes y docentes responsables',
      items: [
        {
          label: 'Notas por asignatura',
          description: 'Seleccione docente, asignatura y período para revisar estudiantes y calificaciones pendientes.',
          page: 'admin-notas-asignatura',
          action: onOpenAdminNotasAsignatura,
        },
        {
          label: 'Consulta por estudiante',
          description: 'Buscar el historial de notas por estudiante, cédula, materia o docente responsable.',
          page: 'reportes-individuales',
          reportKey: 'notas_carrera_materia',
          action: () => onOpenReportesIndividuales('notas_carrera_materia'),
        },
        {
          label: 'Idiomas',
          description: 'Revisar matrículas, entregas por parcial y calificaciones de la Escuela de Idiomas.',
          page: 'ingles',
          action: onOpenIngles,
        },
      ],
    },
    ...(isAdministratorRole(normalizedRole) ? [scholarshipMenuGroup] : []),
    {
      key: 'migracion',
      title: 'Migración',
      summary: 'Cambio de período H a R',
      items: [
        {
          label: 'Migración H a R',
          description: 'Migrar matrículas de homologación hacia un período regular.',
          page: 'gestion-sisacademico',
          sectionKey: 'cambio_periodo_hr',
          action: () => onOpenGestionSisAcademico('cambio_periodo_hr'),
        },
      ],
    },
    certificateMenuGroup,
    {
      key: 'educacion-continua',
      title: 'Educación continua',
      summary: 'Cursos, cortes y participantes',
      items: [
        {
          label: 'Cursos',
          description: 'Cursos de educación continua conservados del sistema anterior.',
          page: 'gestion-sisacademico',
          sectionKey: 'cursos_edu_continua',
          action: () => onOpenGestionSisAcademico('cursos_edu_continua'),
        },
        {
          label: 'Cortes de curso',
          description: 'Fechas, cupos, horas y estado de cortes.',
          page: 'gestion-sisacademico',
          sectionKey: 'corte_curso',
          action: () => onOpenGestionSisAcademico('corte_curso'),
        },
        {
          label: 'Estudiantes por corte',
          description: 'Participantes asociados a cada corte.',
          page: 'gestion-sisacademico',
          sectionKey: 'corte_curso_estudiante',
          action: () => onOpenGestionSisAcademico('corte_curso_estudiante'),
        },
      ],
    },
    {
      key: 'titulacion',
      title: 'Titulación',
      summary: 'Titulación',
      items: [
        {
          label: 'Verificación y modalidad',
          description: 'Validar malla, prácticas, vinculación, aptitud legal y notas.',
          page: 'titulacion',
          action: onOpenTitulacion,
        },
        {
          label: 'Proceso de titulación',
          description: 'Programar complexivo o defensa de grado, responsables, tribunal y enlace Teams.',
          page: 'titulacion-proceso',
          action: onOpenTitulacionProceso,
        },
        {
          label: 'Registro de responsables',
          description: 'Asignar tribunal de defensa y supervisores de examen complexivo.',
          page: 'titulacion-responsables',
          action: onOpenTitulacionResponsables,
        },
        {
          label: 'Títulos registrados SENESCYT',
          description: 'Carpetas y documentos registrados por SENESCYT.',
          page: 'titulos-registrados',
          accessCode: 'titulos-registrados/senescyt',
          action: () => onOpenTitulosRegistrados('senescyt'),
        },
        {
          label: 'Titulación',
          description: 'Carpetas y documentos institucionales INTEC.',
          page: 'titulos-registrados',
          accessCode: 'titulos-registrados/institucional',
          action: () => onOpenTitulosRegistrados('intec'),
        },
      ],
    },
    {
      key: 'datos-senecyt',
      title: 'Datos SENECYT',
      summary: 'Estudiantes, docentes y faltantes',
      items: [
        {
          label: 'Reportes SENECYT',
          description: 'Genere Excel por carrera y faltantes para estudiantes y docentes.',
          page: 'senescyt-estudiantes',
          action: onOpenSenescytEstudiantes,
        },
      ],
    },
    {
      key: 'portal-estudiante',
      title: 'Estudiante',
      summary: 'Ficha, matrícula, notas, correos y seguimiento',
      items: [
        {
          label: 'Ficha del estudiante',
          description: 'Listado y ficha académica del estudiante.',
          page: 'gestion-sisacademico',
          sectionKey: 'estudiantes',
          action: () => onOpenGestionSisAcademico('estudiantes'),
        },
        {
          label: 'Documentos del estudiante',
          description: 'Archivos y observaciones anexadas a la ficha.',
          page: 'gestion-sisacademico',
          sectionKey: 'registro_documentos_estudiante',
          action: () => onOpenGestionSisAcademico('registro_documentos_estudiante'),
        },
        {
          label: 'Materias y notas',
          description: 'Materias matriculadas, paralelos y calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'matricula_materias',
          action: () => onOpenGestionSisAcademico('matricula_materias'),
        },
        {
          label: 'Notas por carrera y período',
          description: 'Reporte filtrado por carrera y período.',
          page: 'reportes-individuales',
          reportKey: 'notas_carrera_materia',
          action: () => onOpenReportesIndividuales('notas_carrera_materia'),
        },
        {
          label: 'Evaluación docente',
          description: 'Cuestionario por materia, período y docente asignado.',
          page: 'evaluacion-docente',
          action: onOpenTeacherEvaluation,
        },
        {
          label: 'Seguimiento académico',
          description: 'Observaciones y acompañamiento por materia.',
          page: 'gestion-sisacademico',
          sectionKey: 'seguimiento',
          action: () => onOpenGestionSisAcademico('seguimiento'),
        },
        { label: 'Actualizar datos', description: 'Actualización de datos personales de estudiantes y docentes.', page: 'actualizar-datos-estudiante', action: onOpenActualizarDatosEstudiante },
        {
          label: 'Actualización del estado del estudiante',
          description: 'Actualice el estado académico mediante el catálogo ESTADO.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_estudiantes',
          action: () => onOpenGestionSisAcademico('actualizacion_estudiantes'),
        },
      ],
    },
    {
      key: 'portal-docente',
      title: 'Docente',
      summary: 'Docentes, asignaciones, materias y estado',
      items: [
        {
          label: 'Ficha docente',
          description: 'Ficha docente y datos laborales.',
          page: 'gestion-sisacademico',
          sectionKey: 'docentes',
          action: () => onOpenGestionSisAcademico('docentes'),
        },
        {
          label: 'Materias asignadas',
          description: 'Relación entre docente, materia, período, paralelo y jornada.',
          page: 'gestion-sisacademico',
          sectionKey: 'docente_materias',
          action: () => onOpenGestionSisAcademico('docente_materias'),
        },
        {
          label: 'Actualización del estado del docente',
          description: 'Valide DATOSDOCENTE y USUARIOS para activar o inactivar docentes.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_est',
          action: () => onOpenGestionSisAcademico('actualizacion_est'),
        },
        {
          label: 'Control de cuestionarios',
          description: 'Número de preguntas, intentos y tiempo por materia.',
          page: 'gestion-sisacademico',
          sectionKey: 'numero_preguntas',
          action: () => onOpenGestionSisAcademico('numero_preguntas'),
        },
        {
          label: 'Banco de preguntas',
          description: 'Preguntas, respuestas y explicacion por unidad.',
          page: 'gestion-sisacademico',
          sectionKey: 'cuestionarios',
          action: () => onOpenGestionSisAcademico('cuestionarios'),
        },
        {
          label: 'Preguntas de evaluación',
          description: 'Banco de preguntas para evaluación, pares y autoevaluación.',
          page: 'gestion-sisacademico',
          sectionKey: 'preguntas_evaluacion',
          action: () => onOpenGestionSisAcademico('preguntas_evaluacion'),
        },
        {
          label: 'Planes, cuestionarios y foros',
          description: 'Recursos, enlaces y fechas por materia y período.',
          page: 'gestion-sisacademico',
          sectionKey: 'planes_foros',
          action: () => onOpenGestionSisAcademico('planes_foros'),
        },
        { label: 'Estado docente', description: 'Revisión y control del estado docente.', page: 'estado-docente', action: onOpenEstadoDocente },
        {
          label: 'Evaluación docente',
          description: 'Resultados y reportes de evaluación docente.',
          page: 'reportes-individuales',
          reportKey: 'evaluacion_docente',
          action: () => onOpenReportesIndividuales('evaluacion_docente'),
        },
        {
          label: 'Resultados de evaluación',
          description: 'Registro directo de respuestas y puntajes por período.',
          page: 'gestion-sisacademico',
          sectionKey: 'evaluacion_resultados',
          action: () => onOpenGestionSisAcademico('evaluacion_resultados'),
        },
        {
          label: 'Resultados de autoevaluación',
          description: 'Puntajes y comentarios de autoevaluación docente.',
          page: 'gestion-sisacademico',
          sectionKey: 'autoevaluacion_resultados',
          action: () => onOpenGestionSisAcademico('autoevaluacion_resultados'),
        },
        {
          label: 'Apertura de autoevaluación',
          description: 'Fechas de habilitación para autoevaluación docente.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_autoevaluacion',
          action: () => onOpenGestionSisAcademico('fechas_autoevaluacion'),
        },
        {
          label: 'Formato informe docente',
          description: 'Textos, recursos y anexos del reporte de cumplimiento.',
          page: 'formato-informe-docente',
          action: onOpenTeacherComplianceFormat,
        },
        {
          label: 'Informe de cumplimiento',
          description: 'Revisar informes, notas, contratos y paquetes firmados archivados.',
          page: 'informe-cumplimiento',
          action: onOpenInformeCumplimiento,
        },
      ],
    },
    {
      key: 'desempeno',
      title: 'Desempeño',
      summary: 'Evaluación, calificación y documentos',
      items: [
        {
          label: 'Avance y ponderación',
          description: 'Porcentaje de avance y peso de cada evaluación.',
          page: 'evaluacion-docente-avance',
          action: onOpenTeacherEvaluationProgress,
        },
        {
          label: 'Generar documento de evaluación',
          description: 'Pendientes por período y PDF de calificación docente.',
          page: 'evaluacion-docente-reportes',
          action: onOpenTeacherEvaluationReports,
        },
      ],
    },
    {
      key: 'administracion',
      title: 'Administración y accesos',
      summary: 'Administrativos, usuarios, permisos y menu',
      items: [
        {
          label: 'Registrar usuarios',
          description: 'Crear y mantener usuarios administrativos en USUARIO_SIS.',
          page: 'gestion-sisacademico',
          sectionKey: 'usuarios',
          action: () => onOpenGestionSisAcademico('usuarios'),
        },
        {
          label: 'Accesos operativos',
          description: 'Accesos por perfil y navegación a los módulos disponibles.',
          page: 'gestion-sisacademico',
          sectionKey: 'menu_usuarios',
          action: () => onOpenGestionSisAcademico('menu_usuarios'),
        },
        {
          label: 'Asignar pantallas',
          description: 'Seleccionar pantallas disponibles por tipo de usuario.',
          page: 'asignacion-pantallas',
          action: onOpenAsignacionPantallas,
        },
      ],
    },
    {
      key: 'talento-humano',
      title: 'Talento humano',
      summary: 'Empleados, solicitudes y tareas RRHH',
      items: [
        {
          label: 'Empleados',
          description: 'Ficha base de empleados del módulo de RR. HH.',
          page: 'gestion-sisacademico',
          sectionKey: 'talento_humano_empleados',
          action: () => onOpenGestionSisAcademico('talento_humano_empleados'),
        },
        {
          label: 'Solicitudes RRHH',
          description: 'Permisos, vacaciones, validaciones y firmas.',
          page: 'gestion-sisacademico',
          sectionKey: 'talento_humano_solicitudes',
          action: () => onOpenGestionSisAcademico('talento_humano_solicitudes'),
        },
        {
          label: 'Tareas RRHH',
          description: 'Tareas, prioridad, delegaciones y cierre.',
          page: 'gestion-sisacademico',
          sectionKey: 'talento_humano_tareas',
          action: () => onOpenGestionSisAcademico('talento_humano_tareas'),
        },
      ],
    },
    {
      key: 'grupo-integraciones-v1',
      title: 'Integraciones V1',
      summary: 'Moodle y Microsoft 365',
      items: [
        {
          label: 'Notas Moodle',
          description: 'Notas sincronizadas por estudiante, materia y componente.',
          page: 'gestion-sisacademico',
          sectionKey: 'moodle_notas',
          action: () => onOpenGestionSisAcademico('moodle_notas'),
        },
        {
          label: 'Sincronización Moodle',
          description: 'Historial de procesos de sincronización de calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'moodle_sincronizacion',
          action: () => onOpenGestionSisAcademico('moodle_sincronizacion'),
        },
        {
          label: 'Auditoría de Microsoft 365',
          description: 'Acciones, estados y errores de servicios Microsoft 365.',
          page: 'gestion-sisacademico',
          sectionKey: 'microsoft365_audit',
          action: () => onOpenGestionSisAcademico('microsoft365_audit'),
        },
      ],
    },
    {
      key: 'carnetizacion',
      title: 'Carnetización',
      summary: 'Aprobación, renovación y emisión de carnés',
      items: [
        {
          label: 'Aprobación de carnet',
          description: 'Revisar fotos pendientes, aprobar, rechazar y generar carnets.',
          page: 'carnet-institucional',
          action: onOpenCarnetInstitucional,
        },
      ],
    },
    {
      key: 'vinculacion',
      title: 'Prácticas institucionales',
      summary: 'Preprofesionales y vinculación',
      items: practicesInstitutionalMenuItems,
    },
    {
      key: 'catalogos',
      title: 'Proceso académico',
      summary: 'Carreras, materias, períodos, paralelos y mallas',
      items: [
        {
          label: 'Carreras',
          description: 'Oferta académica y estado de la carrera.',
          page: 'gestion-sisacademico',
          sectionKey: 'carreras',
          action: () => onOpenGestionSisAcademico('carreras'),
        },
        {
          label: 'Materias y pensum',
          description: 'Materias, créditos, niveles y malla.',
          page: 'gestion-sisacademico',
          sectionKey: 'materias',
          action: () => onOpenGestionSisAcademico('materias'),
        },
        {
          label: 'Mallas',
          description: 'Mallas por carrera y estado.',
          page: 'gestion-sisacademico',
          sectionKey: 'mallas',
          action: () => onOpenGestionSisAcademico('mallas'),
        },
        {
          label: 'Textos materias HOMO',
          description: 'Texto, URL y período por código de materia homologada.',
          page: 'gestion-sisacademico',
          sectionKey: 'materia_homo_textof',
          action: () => onOpenGestionSisAcademico('materia_homo_textof'),
        },
        {
          label: 'Paralelos',
          description: 'Catálogo y mantenimiento académico de paralelos.',
          page: 'gestion-sisacademico',
          sectionKey: 'paralelos',
          action: () => onOpenGestionSisAcademico('paralelos'),
        },
        { label: 'Períodos académicos', description: 'Resumen de períodos y estudiantes.', page: 'periodo-academico', action: onOpenPeriodoAcademico },
        {
          label: 'Períodos del sistema',
          description: 'Mantenimiento directo de períodos académicos.',
          page: 'gestion-sisacademico',
          sectionKey: 'periodos',
          action: () => onOpenGestionSisAcademico('periodos'),
        },
        {
          label: 'Provincias',
          description: 'Catálogo territorial para inscripciones y estudiantes.',
          page: 'gestion-sisacademico',
          sectionKey: 'provincias',
          action: () => onOpenGestionSisAcademico('provincias'),
        },
        {
          label: 'Apertura de notas',
          description: 'Fechas para el ingreso de notas por parcial y período.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_notas',
          action: () => onOpenGestionSisAcademico('fechas_notas'),
        },
        {
          label: 'Apertura de autoevaluación',
          description: 'Fechas vigentes para la autoevaluación por período.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_autoevaluacion',
          action: () => onOpenGestionSisAcademico('fechas_autoevaluacion'),
        },
        {
          label: 'Asistencia estudiantes',
          description: 'Registro por estudiante, materia, período y paralelo.',
          page: 'gestion-sisacademico',
          sectionKey: 'asistencia_estudiantes',
          action: () => onOpenGestionSisAcademico('asistencia_estudiantes'),
        },
        {
          label: 'Jornadas',
          description: 'Jornadas y relación con modalidad.',
          page: 'gestion-sisacademico',
          sectionKey: 'jornadas',
          action: () => onOpenGestionSisAcademico('jornadas'),
        },
        {
          label: 'Días de matrícula',
          description: 'Catálogo heredado de días para el proceso de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'dias_matricula',
          action: () => onOpenGestionSisAcademico('dias_matricula'),
        },
        {
          label: 'Horarios de matrícula',
          description: 'Catálogo heredado de horarios para matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'horarios_matricula',
          action: () => onOpenGestionSisAcademico('horarios_matricula'),
        },
        {
          label: 'Modalidades',
          description: 'Modalidades de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'modalidades',
          action: () => onOpenGestionSisAcademico('modalidades'),
        },
      ],
    },
    {
      key: 'reporteria',
      title: 'Reportes y control',
      summary: 'Edades y género docente',
      items: [
        {
          label: 'Rango de edades',
          description: 'Edades calculadas, becas y porcentaje exportable.',
          page: 'rango-edades',
          action: onOpenRangoEdades,
        },
        {
          label: 'Género de docentes',
          description: 'Distribución de docentes por género y estado activo o inactivo.',
          page: 'reporteria-integral',
          reportKey: 'genero_docentes',
          action: () => onOpenReporteriaIntegral('genero_docentes'),
        },
      ],
    },
    {
      key: 'reportes-rh',
      title: 'Reportes R/H',
      summary: 'Provincia, género, carrera y período',
      items: [
        {
          label: 'Provincia',
          description: 'Totales por provincia separados en Regular y Homologación.',
          page: 'reporteria-integral',
          reportKey: 'provincia',
          action: () => onOpenReporteriaIntegral('provincia'),
        },
        {
          label: 'Género',
          description: 'Totales por género separados en Regular y Homologación.',
          page: 'reporteria-integral',
          reportKey: 'genero',
          action: () => onOpenReporteriaIntegral('genero'),
        },
        {
          label: 'Carrera',
          description: 'Totales por carrera separados en Regular y Homologación.',
          page: 'reporteria-integral',
          reportKey: 'carrera',
          action: () => onOpenReporteriaIntegral('carrera'),
        },
        {
          label: 'Período',
          description: 'Totales por período separados en Regular y Homologación.',
          page: 'reporteria-integral',
          reportKey: 'periodo',
          action: () => onOpenReporteriaIntegral('periodo'),
        },
        {
          label: 'Graduados',
          description: 'Listado de graduados por año, carrera, género y provincia.',
          page: 'reporteria-integral',
          reportKey: 'graduados_2025',
          action: () => onOpenReporteriaIntegral('graduados_2025'),
        },
      ],
    },
    {
      key: 'integraciones',
      title: 'Integraciones',
      summary: 'Teams, Office 365 y servicios externos',
      items: [
        {
          label: 'Credenciales Office 365',
          description: 'Crear usuarios por curso mediante Microsoft Graph.',
          page: 'credenciales' as Page,
          action: onOpenCredentialGenerator,
        },
        {
          label: 'Correos masivos',
          description: 'Enviar mensajes con adjuntos por cédula mediante Microsoft Graph.',
          page: 'correos-masivos' as Page,
          action: onOpenMassEmail,
        },
        { label: 'Matrícula en Teams', description: 'Creación y matrícula de equipos.', page: 'teams-matricula', action: onOpenTeamsMatricula },
        {
          label: 'Matrícula Moodle-Teams',
          description: 'Crear aulas de Teams con docentes y estudiantes de Moodle.',
          page: 'moodle-teams',
          action: onOpenMoodleTeams,
        },
        { label: 'Movimientos Teams', description: 'Gestión de equipos y movimientos.', page: 'teams', action: onOpenTeams },
      ],
    },
  ]

  const moodleMenuGroup: NavGroup = {
    key: 'moodle',
    title: 'Moodle',
    summary: 'Cursos, recursos, notas, estado y usuarios',
    items: [
      {
        label: 'Alertas de calificación',
        description: 'Pendientes de Moodle según el alcance del perfil.',
        page: 'moodle',
        moodleSection: 'alerts',
        action: () => onOpenMoodle('alerts'),
      },
      {
        label: 'Cursos',
        description: 'Consultar los cursos publicados en Moodle.',
        page: 'moodle',
        moodleSection: 'courses',
        action: () => onOpenMoodle('courses'),
      },
      {
        label: 'Estado de la integración',
        description: 'Validar la conectividad y configuración autorizada.',
        page: 'moodle',
        moodleSection: 'status',
        action: () => onOpenMoodle('status'),
      },
      {
        label: 'Fechas de evaluaciones',
        description: 'Editar apertura, entrega y cierre de tareas y cuestionarios.',
        page: 'moodle',
        moodleSection: 'evaluation-dates',
        action: () => onOpenMoodle('evaluation-dates'),
      },
      {
        label: 'Recursos por curso',
        description: 'Consultar secciones, actividades, enlaces y archivos de cada curso.',
        page: 'moodle',
        moodleSection: 'resources',
        action: () => onOpenMoodle('resources'),
      },
      {
        label: 'Sincronización de notas',
        description: 'Previsualizar y migrar exámenes prácticos desde Moodle.',
        page: 'moodle',
        moodleSection: 'grades',
        action: () => onOpenMoodle('grades'),
      },
      {
        label: 'Usuarios',
        description: 'Consultar, activar o inactivar cuentas validadas.',
        page: 'moodle',
        moodleSection: 'users',
        action: () => onOpenMoodle('users'),
      },
    ],
  }

  const admissionsMenuGroups: NavGroup[] = [
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Ventas personales',
      items: [
        {
          label: 'Sistema académico',
          description: 'Ciclo institucional y accesos habilitados para admisiones.',
          page: 'sistema-academico',
          action: onOpenSistemaAcademico,
        },
        {
          label: 'Dashboard',
          description: 'Inscripciones y estados de sus ventas.',
          page: 'dashboard',
          action: onOpenDashboard,
        },
      ],
    },
    admissionsMenuGroup,
    {
      key: 'admision-consultas',
      title: 'Consultas de admisión',
      summary: 'Inscripciones, facturación y estudiantes',
      items: [
        {
          label: 'Inscripciones registradas',
          description: 'Revisar, buscar y seleccionar estudiantes inscritos.',
          category: 'Consulta directa',
          page: 'gestion-sisacademico',
          sectionKey: 'preinscripciones',
          action: () => onOpenGestionSisAcademico('preinscripciones'),
        },
        {
          label: 'Datos de factura',
          description: 'Datos tributarios registrados durante la inscripción.',
          page: 'gestion-sisacademico',
          sectionKey: 'datos_factura',
          action: () => onOpenGestionSisAcademico('datos_factura'),
        },
        {
          label: 'Listado de estudiantes',
          description: 'Consultar estudiantes registrados y datos de contacto.',
          page: 'gestion-sisacademico',
          sectionKey: 'estudiantes',
          action: () => onOpenGestionSisAcademico('estudiantes'),
        },
      ],
    },
    certificateMenuGroup,
    {
      key: 'admision-integraciones',
      title: 'Integraciones',
      summary: 'Correo y servicios Microsoft',
      items: [
        {
          label: 'Correos masivos',
          description: 'Enviar mensajes con adjuntos por cédula.',
          page: 'correos-masivos' as Page,
          action: onOpenMassEmail,
        },
        {
          label: 'Carnet institucional',
          description: 'Foto de carnet para estudiantes, docentes y administrativos.',
          page: 'carnet-institucional' as Page,
          action: onOpenCarnetInstitucional,
        },
      ],
    },
    {
      key: 'admision-control',
      title: 'Control de matrícula',
      summary: 'Pago, convenio y valores',
      items: [
        {
          label: 'Pago y convenio',
          description: 'Validar la cabecera, los valores y el convenio de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'cabecera_matricula',
          action: () => onOpenGestionSisAcademico('cabecera_matricula'),
        },
        {
          label: 'Pagos registrados',
          description: 'Revisar pagos, descuentos y valores vinculados.',
          page: 'gestion-sisacademico',
          sectionKey: 'pagos_matricula',
          action: () => onOpenGestionSisAcademico('pagos_matricula'),
        },
      ],
    },
  ]
  const academicMenuGroups: NavGroup[] = [
    {
      key: 'flujo-academico',
      title: 'Flujo académico',
      summary: 'Inscripción a titulación',
      items: academicLifecycleItems,
    },
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Indicadores académicos',
      items: [
        { label: 'Dashboard', description: 'Estudiantes activos, inactivos e indicadores generales.', page: 'dashboard', action: onOpenDashboard },
      ],
    },
    ...(
      normalizedRole === 'BIENESTAR'
        ? [scholarshipMenuGroup]
        : []
    ),
    {
      key: 'calificaciones',
      title: 'Calificaciones',
      summary: 'Notas por docente y asignatura',
      items: [
        {
          label: 'Notas por asignatura',
          description: 'Seleccione docente, asignatura, carrera y período para revisar estudiantes y notas.',
          page: 'admin-notas-asignatura',
          action: onOpenAdminNotasAsignatura,
        },
        {
          label: 'Consulta por estudiante',
          description: 'Historial de notas por estudiante, materia, período y docente responsable.',
          page: 'reportes-individuales',
          reportKey: 'notas_carrera_materia',
          action: () => onOpenReportesIndividuales('notas_carrera_materia'),
        },
        {
          label: 'Idiomas',
          description: 'Matrículas, evidencias por parcial y notas de la Escuela de Idiomas.',
          page: 'ingles',
          action: onOpenIngles,
        },
      ],
    },
    {
      key: 'matriculacion',
      title: 'Matrícula',
      summary: 'Matrícula, estudiantes y notas',
      items: [
        {
          label: 'Matrícula individual',
          description: 'Control de cabecera y materias de un estudiante.',
          page: 'matricula-acad',
          sectionKey: 'individual',
          action: () => onOpenMatriculaAcad('individual'),
        },
        {
          label: 'Materias y notas',
          description: 'Materias matriculadas, paralelos, notas y actualización de calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'matricula_materias',
          action: () => onOpenGestionSisAcademico('matricula_materias'),
        },
        {
          label: 'Apertura de notas',
          description: 'Fechas de habilitación para ingreso y actualización de notas.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_notas',
          action: () => onOpenGestionSisAcademico('fechas_notas'),
        },
        { label: 'Períodos académicos', description: 'Períodos, estudiantes y estado académico.', page: 'periodo-academico', action: onOpenPeriodoAcademico },
      ],
    },
    {
      key: 'portal-estudiante',
      title: 'Estudiantes',
      summary: 'Listado, ficha e información académica',
      items: [
        {
          label: 'Listado de estudiantes',
          description: 'Consulta de estudiantes, datos personales y ficha académica.',
          page: 'gestion-sisacademico',
          sectionKey: 'estudiantes',
          action: () => onOpenGestionSisAcademico('estudiantes'),
        },
        {
          label: 'Documentos del estudiante',
          description: 'Documentos, respaldos y observaciones de la ficha.',
          page: 'gestion-sisacademico',
          sectionKey: 'registro_documentos_estudiante',
          action: () => onOpenGestionSisAcademico('registro_documentos_estudiante'),
        },
        {
          label: 'Actualizar datos',
          description: 'Actualización de información personal de estudiantes y docentes.',
          page: 'actualizar-datos-estudiante',
          action: onOpenActualizarDatosEstudiante,
        },
        {
          label: 'Estado estudiante',
          description: 'Activar, inactivar o revisar estado académico del estudiante.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_estudiantes',
          action: () => onOpenGestionSisAcademico('actualizacion_estudiantes'),
        },
        {
          label: 'Seguimiento académico',
          description: 'Observaciones y acompañamiento académico por estudiante.',
          page: 'gestion-sisacademico',
          sectionKey: 'seguimiento',
          action: () => onOpenGestionSisAcademico('seguimiento'),
        },
      ],
    },
    {
      key: 'portal-docente',
      title: 'Docentes',
      summary: 'Registro, asignación e información docente',
      items: [
        {
          label: 'Registro de docentes',
          description: 'Ficha docente, datos laborales e información académica.',
          page: 'gestion-sisacademico',
          sectionKey: 'docentes',
          action: () => onOpenGestionSisAcademico('docentes'),
        },
        {
          label: 'Materias asignadas',
          description: 'Relación docente, materia, período, paralelo y jornada.',
          page: 'gestion-sisacademico',
          sectionKey: 'docente_materias',
          action: () => onOpenGestionSisAcademico('docente_materias'),
        },
        {
          label: 'Estado docente',
          description: 'Activar, inactivar y actualizar información docente.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_est',
          action: () => onOpenGestionSisAcademico('actualizacion_est'),
        },
      ],
    },
    {
      key: 'reporteria',
      title: 'Reportes académicos',
      summary: 'Notas y desempeño',
      items: [
        {
          label: 'Calificaciones de estudiantes',
          description: 'Notas por estudiante, materia, período y docente responsable.',
          page: 'reportes-individuales',
          reportKey: 'notas_carrera_materia',
          action: () => onOpenReportesIndividuales('notas_carrera_materia'),
        },
        {
          label: 'Género de docentes',
          description: 'Distribución de docentes por género y estado activo o inactivo.',
          page: 'reporteria-integral',
          reportKey: 'genero_docentes',
          action: () => onOpenReporteriaIntegral('genero_docentes'),
        },
        {
          label: 'Avance y ponderación',
          description: 'Avance por período y ponderación de la evaluación docente.',
          page: 'evaluacion-docente-avance',
          action: onOpenTeacherEvaluationProgress,
        },
        {
          label: 'Documentos de evaluación',
          description: 'Generar documentos PDF de evaluación docente.',
          page: 'evaluacion-docente-reportes',
          action: onOpenTeacherEvaluationReports,
        },
      ],
    },
    {
      key: 'catalogos',
      title: 'Catálogos académicos',
      summary: 'Carreras, materias y períodos',
      items: [
        {
          label: 'Carreras',
          description: 'Oferta académica y estado de carrera.',
          page: 'gestion-sisacademico',
          sectionKey: 'carreras',
          action: () => onOpenGestionSisAcademico('carreras'),
        },
        {
          label: 'Materias y pensum',
          description: 'Materias, créditos, niveles y malla.',
          page: 'gestion-sisacademico',
          sectionKey: 'materias',
          action: () => onOpenGestionSisAcademico('materias'),
        },
        {
          label: 'Mallas',
          description: 'Mallas por carrera y estado.',
          page: 'gestion-sisacademico',
          sectionKey: 'mallas',
          action: () => onOpenGestionSisAcademico('mallas'),
        },
        {
          label: 'Paralelos',
          description: 'Catálogo y mantenimiento académico de paralelos.',
          page: 'gestion-sisacademico',
          sectionKey: 'paralelos',
          action: () => onOpenGestionSisAcademico('paralelos'),
        },
        {
          label: 'Períodos del sistema',
          description: 'Mantenimiento directo de períodos académicos.',
          page: 'gestion-sisacademico',
          sectionKey: 'periodos',
          action: () => onOpenGestionSisAcademico('periodos'),
        },
      ],
    },
    {
      key: 'educacion-continua',
      title: 'Educación continua',
      summary: 'Cursos, cortes y estudiantes',
      items: [
        {
          label: 'Cursos',
          description: 'Cursos de educación continua del sistema anterior.',
          page: 'gestion-sisacademico',
          sectionKey: 'cursos_edu_continua',
          action: () => onOpenGestionSisAcademico('cursos_edu_continua'),
        },
        {
          label: 'Cortes de curso',
          description: 'Fechas, cupos, horas y estado de los cortes.',
          page: 'gestion-sisacademico',
          sectionKey: 'corte_curso',
          action: () => onOpenGestionSisAcademico('corte_curso'),
        },
        {
          label: 'Estudiantes por corte',
          description: 'Participantes inscritos en cada corte.',
          page: 'gestion-sisacademico',
          sectionKey: 'corte_curso_estudiante',
          action: () => onOpenGestionSisAcademico('corte_curso_estudiante'),
        },
      ],
    },
    {
      key: 'documentacion-academica',
      title: 'Documentación',
      summary: 'Repositorio digital',
      items: [
        {
          label: 'Repositorio digital',
          description: 'Documentos bibliográficos y enlaces por carrera.',
          page: 'gestion-sisacademico',
          sectionKey: 'repositorio',
          action: () => onOpenGestionSisAcademico('repositorio'),
        },
      ],
    },
    {
      key: 'integraciones-academicas',
      title: 'Integraciones académicas',
      summary: 'Moodle y Microsoft 365',
      items: [
        {
          label: 'Notas Moodle',
          description: 'Notas sincronizadas por estudiante, materia y componente.',
          page: 'gestion-sisacademico',
          sectionKey: 'moodle_notas',
          action: () => onOpenGestionSisAcademico('moodle_notas'),
        },
        {
          label: 'Sincronización Moodle',
          description: 'Historial de procesos de sincronización de calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'moodle_sincronizacion',
          action: () => onOpenGestionSisAcademico('moodle_sincronizacion'),
        },
        {
          label: 'Auditoría Microsoft 365',
          description: 'Acciones y errores de servicios Microsoft 365.',
          page: 'gestion-sisacademico',
          sectionKey: 'microsoft365_audit',
          action: () => onOpenGestionSisAcademico('microsoft365_audit'),
        },
      ],
    },
    {
      key: 'vinculacion',
      title: 'Prácticas institucionales',
      summary: 'Preprofesionales y vinculación con la sociedad',
      items: practicesInstitutionalMenuItems,
    },
    {
      key: 'titulacion',
      title: 'Titulación',
      summary: 'Requisitos y promedio final',
      items: [
        {
          label: 'Verificación y modalidad',
          description: 'Validar malla, prácticas, vinculación con la sociedad, aptitud legal y notas.',
          page: 'titulacion',
          action: onOpenTitulacion,
        },
        {
          label: 'Proceso de titulación',
          description: 'Programar complexivo o defensa de grado, responsables, tribunal y enlace Teams.',
          page: 'titulacion-proceso',
          action: onOpenTitulacionProceso,
        },
        {
          label: 'Registro de responsables',
          description: 'Asignar tribunal y supervisores del proceso de titulación.',
          page: 'titulacion-responsables',
          action: onOpenTitulacionResponsables,
        },
      ],
    },
  ]

  const executiveMenuGroups: NavGroup[] = [
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Control institucional',
      items: [
        { label: 'Dashboard', description: 'Estudiantes activos, inactivos e indicadores generales.', page: 'dashboard', action: onOpenDashboard },
      ],
    },
  ]

  const financialMenuGroups: NavGroup[] = [
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Indicadores financieros',
      items: [
        { label: 'Sistema académico', description: 'Ciclo institucional y operación financiera.', page: 'sistema-academico', action: onOpenSistemaAcademico },
        { label: 'Dashboard', description: 'Indicadores principales del sistema.', page: 'dashboard', action: onOpenDashboard },
      ],
    },
    {
      key: 'ventas-inscripcion',
      title: 'Ventas e inscripción',
      summary: 'Inscripción, beca, convenio y cabecera',
      items: [
        ...salesPreinscriptionFlowItems,
      ],
    },
    {
      key: 'admision-matriculas',
      title: 'Finanzas',
      summary: 'Pagos, valores e ingresos',
      items: [
        {
          label: 'Pagos y valores',
          description: 'Registro de pagos, descuentos y valores de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'pagos_matricula',
          action: () => onOpenGestionSisAcademico('pagos_matricula'),
        },
        {
          label: 'Cabecera matrícula',
          description: 'Valores y control financiero de matrícula.',
          page: 'gestion-sisacademico',
          sectionKey: 'cabecera_matricula',
          action: () => onOpenGestionSisAcademico('cabecera_matricula'),
        },
        { label: 'Ingreso ventas', description: 'Reporte de ingresos y ventas.', page: 'ingreso-ventas', action: onOpenIngresoVentas },
      ],
    },
  ]

  const secretaryMenuGroups: NavGroup[] = [
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Ciclo institucional',
      items: [
        { label: 'Sistema académico', description: 'Prácticas, egreso y titulación.', page: 'sistema-academico', action: onOpenSistemaAcademico },
      ],
    },
    {
      key: 'vinculacion',
      title: 'Prácticas institucionales',
      summary: 'Preprofesionales y vinculación con la sociedad',
      items: practicesInstitutionalMenuItems,
    },
    {
      key: 'datos-senecyt',
      title: 'Datos SENESCYT',
      summary: 'Consulta académica',
      items: [
        {
          label: 'Reportes SENESCYT',
          description: 'Consultar información registrada y reportes SENESCYT de estudiantes.',
          page: 'senescyt-estudiantes',
          action: onOpenSenescytEstudiantes,
        },
      ],
    },
    {
      key: 'titulacion',
      title: 'Titulación',
      summary: 'Titulación',
      items: [
        {
          label: 'Verificación y modalidad',
          description: 'Validar requisitos, notas y documentos de titulación.',
          page: 'titulacion',
          action: onOpenTitulacion,
        },
        {
          label: 'Proceso de titulación',
          description: 'Programar complexivo o defensa de grado, responsables, tribunal y enlace Teams.',
          page: 'titulacion-proceso',
          action: onOpenTitulacionProceso,
        },
        {
          label: 'Registro de responsables',
          description: 'Asignar tribunal de defensa y supervisores de complexivo.',
          page: 'titulacion-responsables',
          action: onOpenTitulacionResponsables,
        },
        {
          label: 'Títulos registrados SENESCYT',
          description: 'Consultar carpetas y documentos registrados por SENESCYT.',
          page: 'titulos-registrados',
          accessCode: 'titulos-registrados/senescyt',
          action: () => onOpenTitulosRegistrados('senescyt'),
        },
        {
          label: 'Titulación',
          description: 'Consultar carpetas y documentos institucionales INTEC.',
          page: 'titulos-registrados',
          accessCode: 'titulos-registrados/institucional',
          action: () => onOpenTitulosRegistrados('intec'),
        },
      ],
    },
  ]

  const studentMenuGroups: NavGroup[] = [
    {
      key: 'dashboard-estudiante',
      title: 'Dashboard',
      summary: 'Inicio y avance académico',
      items: [
        {
          label: 'Panel académico',
          description: 'Inicio con avance, cumplimiento y accesos rápidos.',
          page: 'portal-estudiante',
          portalSection: 'dashboard',
          action: () => onOpenPortalEstudiante('dashboard'),
        },
      ],
    },
    {
      key: 'portal-estudiante',
      title: 'Estudiante',
      summary: 'Calificaciones, evaluación y servicios',
      items: [
        {
          label: 'Calificaciones por período',
          description: 'Revisión de notas filtrada por período académico.',
          page: 'portal-estudiante-calificaciones',
          portalSection: 'notas',
          action: () => onOpenPortalEstudiante('notas'),
        },
        {
          label: 'Evaluación docente',
          description: 'Evalúe al docente según sus materias matriculadas.',
          page: 'evaluacion-docente',
          action: onOpenTeacherEvaluation,
        },
        {
          label: 'Carnet institucional',
          description: 'Subir foto y revisar estado de aprobación.',
          page: 'carnet-institucional',
          action: onOpenCarnetInstitucional,
        },
      ],
    },
    {
      key: 'malla-estudiante',
      title: 'Malla',
      summary: 'Plan curricular y avance académico',
      items: [
        {
          label: 'Malla académica',
          description: 'Materias aprobadas, pendientes y avance por promedio.',
          page: 'portal-estudiante-malla-academica',
          portalSection: 'academica',
          action: () => onOpenPortalEstudiante('academica'),
        },
        {
          label: 'Malla curricular',
          description: 'Materias por cursar, códigos, niveles y créditos.',
          page: 'portal-estudiante-malla-curricular',
          portalSection: 'curricular',
          action: () => onOpenPortalEstudiante('curricular'),
        },
      ],
    },
    {
      key: 'practicas-estudiante',
      title: 'Prácticas',
      summary: 'Laborales, preprofesionales y vinculación',
      items: practicesInstitutionalMenuItems,
    },
  ]

  const teacherMenuGroups: NavGroup[] = [
    {
      key: 'portal-docente',
      title: 'Docente',
      summary: 'Cursos y subida de notas',
      items: [
        {
          label: 'Mis cursos y notas',
          description: 'Estudiantes por materia asignada y registro de calificaciones.',
          page: 'portal-docente',
          action: onOpenPortalDocente,
        },
        {
          label: 'Crear informe docente',
          description: 'Generar el documento de cumplimiento con el formato institucional.',
          page: 'portal-docente-informe',
          action: onOpenPortalDocenteInforme,
        },
        {
          label: 'Crear Sílabo y PEA',
          description: 'Planificación por unidades, temas, horas, evaluación y bibliografía.',
          page: 'portal-docente-planificacion',
          action: onOpenPortalDocentePlanificacion,
        },
        {
          label: 'Contrato docente',
          description: 'Consultar vigencia, condiciones y materias contratadas.',
          page: 'portal-docente-contratos',
          action: onOpenPortalDocenteContratos,
        },
        ...practicesInstitutionalMenuItems,
        {
          label: 'Carnet institucional',
          description: 'Subir foto y revisar estado de aprobación.',
          page: 'carnet-institucional',
          action: onOpenCarnetInstitucional,
        },
      ],
    },
  ]

  const englishMenuGroup: NavGroup = {
    key: 'idiomas',
    title: 'Escuela de Idiomas',
    summary: normalizedRole === 'ESTUDIANTE' ? 'Evidencias por parcial' : 'Entregas y calificaciones',
    items: [
      {
        label: normalizedRole === 'ESTUDIANTE' ? 'Evaluación de idiomas' : 'Calificaciones de idiomas',
        description: normalizedRole === 'ESTUDIANTE'
          ? 'Subir el video de cada parcial cuando exista una matrícula vigente de la asignatura.'
          : 'Consultar únicamente estudiantes matriculados, revisar videos y calificar cada parcial.',
        page: 'ingles',
        action: onOpenIngles,
      },
    ],
  }

  const documentExpedientsMenuGroup: NavGroup = {
    key: 'expedientes-documentales',
    title: 'Expedientes',
    summary: 'Documentos académicos y facturación',
    items: [
      {
        label: 'Expedientes documentales',
        description: normalizedRole === 'ESTUDIANTE'
          ? 'Consultar documentos y cargar evidencias habilitadas de sus procesos.'
          : 'Buscar estudiantes y gestionar documentos, facturas XML y RIDE en Microsoft 365.',
        page: 'expedientes-documentales',
        action: onOpenExpedientesDocumentales,
      },
    ],
  }

  const assignableUtilitiesMenuGroup: NavGroup = {
    key: 'herramientas-asignables',
    title: 'Herramientas asignadas',
    summary: 'Consultas y controles autorizados',
    items: [
      {
        label: 'Reportería por carreras',
        description: 'Consultar indicadores y reportes agrupados por carrera.',
        page: 'reporteria-carreras',
        action: onOpenReporteriaCarreras,
      },
      {
        label: 'Administrar evaluación docente',
        description: 'Configurar y administrar el proceso de evaluación docente.',
        page: 'evaluacion-docente-admin',
        action: onOpenTeacherEvaluationAdmin,
      },
      {
        label: 'Cruce de datos',
        description: 'Comparar y validar información académica entre fuentes.',
        page: 'cruce-datos',
        action: onOpenCruceDatos,
      },
      {
        label: 'Validar Excel',
        description: 'Validar archivos Excel antes de procesar su información.',
        page: 'validar-excel',
        action: onOpenValidarExcel,
      },
    ],
  }

  const roleMenuGroups = normalizedRole === 'ESTUDIANTE'
    ? [...studentMenuGroups, englishMenuGroup]
    : normalizedRole === 'DOCENTE'
      ? [englishMenuGroup, ...teacherMenuGroups, moodleMenuGroup]
      : normalizedRole === 'ADMISIONES'
        ? admissionsMenuGroups
          : normalizedRole === 'SECRETARIA'
          ? [requestsMenuGroup, updatesMenuGroup, ...secretaryMenuGroups, documentExpedientsMenuGroup]
          : academicRoles.has(normalizedRole)
            ? [admissionsMenuGroup, requestsMenuGroup, updatesMenuGroup, enrollmentMenuGroup, certificateMenuGroup, ...academicMenuGroups, moodleMenuGroup, documentExpedientsMenuGroup]
            : dashboardOnlyRoles.has(normalizedRole)
              ? executiveMenuGroups
              : normalizedRole === 'FINANCIERO'
                ? financialMenuGroups
                : [admissionsMenuGroup, auditMenuGroup, requestsMenuGroup, updatesMenuGroup, enrollmentMenuGroup, ...adminMenuGroups, moodleMenuGroup, assignableUtilitiesMenuGroup, documentExpedientsMenuGroup]

  const roleScopedMenuGroups = roleMenuGroups
    .filter((group) => isAdministrator || group.key !== 'flujo-academico')

  const navigationCatalogGroups = [
    admissionsMenuGroup,
    auditMenuGroup,
    certificateMenuGroup,
    requestsMenuGroup,
    ...roleScopedMenuGroups,
    ...adminMenuGroups,
    ...admissionsMenuGroups,
    ...academicMenuGroups,
    ...executiveMenuGroups,
    ...financialMenuGroups,
    ...secretaryMenuGroups,
    ...studentMenuGroups,
    ...teacherMenuGroups,
    moodleMenuGroup,
    updatesMenuGroup,
    enrollmentMenuGroup,
    scholarshipMenuGroup,
    assignableUtilitiesMenuGroup,
    englishMenuGroup,
    documentExpedientsMenuGroup,
  ]

  const menuGroups = screenAccessPages === null
    ? mergeNavigationGroups(
        roleScopedMenuGroups
          .map((group) => ({
          ...group,
          items: group.items.filter((item) => navItemAllowedForRole(normalizedRole, item)),
          }))
          .filter((group) => group.items.length > 0),
      )
    : buildAssignedMenuGroups(roleScopedMenuGroups, navigationCatalogGroups, screenAccessPages)

  const visibleMenuGroups = sortNavGroups(menuGroups)
  const fallbackBrandTitle = titleFromRole(normalizedRole || 'INTEC')
  const brand = roleBrandMap[normalizedRole] ?? {
    initials: initialsFromTitle(fallbackBrandTitle),
    title: fallbackBrandTitle,
  }
  const brandTitle = normalizedRole === 'ESTUDIANTE' && displayName.trim() ? displayName.trim() : brand.title
  const brandSubtitle = normalizedRole === 'ESTUDIANTE' && cedula.trim() ? `Cédula ${cedula.trim()}` : ''

  function openPage(action: () => void) {
    action()
    setMobileMenuOpen(false)
  }

  function toggleGroup(groupKey: string) {
    setOpenMenuGroups((current) => {
      const next = new Set(current)
      if (next.has(groupKey)) {
        next.delete(groupKey)
      } else {
        next.add(groupKey)
      }
      return next
    })
  }

  function groupHasActivePage(group: NavGroup) {
    return group.items.some((item) => itemIsActive(item))
  }

  function itemIsActive(item: NavItem) {
    if (item.page !== activePage) return false
    if (item.practicasProcess) {
      return item.practicasProcess === activePracticasProcess
    }
    if (item.moodleSection) {
      return item.moodleSection === activeMoodleSection
    }
    if (item.sectionKey) {
      if (item.page === 'matricula-acad') {
        return item.sectionKey === activeMatriculaAcadMode
      }
      return item.sectionKey === activeSisAcademicoSection
    }
    if (item.reportKey) {
      return item.reportKey === activeLegacyReport
    }
    if (item.portalSection) {
      return item.portalSection === activePortalStudentSection
    }
    if (item.preinscriptionStage) {
      return item.preinscriptionStage === activePreinscriptionStage
    }
    if (item.page === 'gestion-sisacademico' && activeSisAcademicoSection) return false
    if ((item.page === 'reporteria-integral' || item.page === 'reportes-individuales') && activeLegacyReport) return false
    return true
  }

  function groupIsOpen(group: NavGroup) {
    return openMenuGroups.has(group.key)
  }

  return (
    <div className={`student-shell ${isMobileViewport ? 'student-shell--mobile-view' : ''}`}>
      <aside
        className={`student-sidebar ${isMobileViewport ? 'student-sidebar--mobile' : ''} ${mobileMenuOpen ? 'student-sidebar--open' : ''}`}
        aria-label="Menú lateral"
      >
        <div className="student-sidebar__head">
          <div className="student-brand">
            <div className="student-brand__logo">{brand.initials}</div>
            {!isMobileViewport || mobileMenuOpen ? (
              <div>
                <strong>{brandTitle}</strong>
                {brandSubtitle ? <span>{brandSubtitle}</span> : null}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            className="student-mobile-menu-button"
            aria-controls="student-mobile-nav"
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? 'Cerrar menú principal' : 'Abrir menú principal'}
            onClick={() => setMobileMenuOpen((value) => !value)}
          >
            <span className="student-mobile-menu-button__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                {mobileMenuOpen ? (
                  <>
                    <path d="M6 6l12 12" />
                    <path d="M18 6 6 18" />
                  </>
                ) : (
                  <>
                    <path d="M4 7h16" />
                    <path d="M4 12h16" />
                    <path d="M4 17h16" />
                  </>
                )}
              </svg>
            </span>
            <span className="student-mobile-menu-button__label">{mobileMenuOpen ? 'Cerrar' : 'Menú'}</span>
          </button>
        </div>

        <div className="student-sidebar__panel" id="student-mobile-nav">
          <nav className="student-nav" aria-label="Menú principal">
            {visibleMenuGroups.map((group) => {
              const isOpen = groupIsOpen(group)
              const isActive = groupHasActivePage(group)
              const sortedItems = sortNavItems(group.items)
              return (
                <div key={group.key} className="student-nav__section">
                  <button
                    type="button"
                    className={`student-nav__group-button ${isActive ? 'student-nav__group-button--active' : ''}`}
                    aria-expanded={isOpen}
                    onClick={() => toggleGroup(group.key)}
                  >
                    <span className="student-nav__group-icon" aria-hidden="true">
                      <GroupIcon name={groupIconName(group.key)} />
                    </span>
                    <span className="student-nav__group-copy">
                      <strong>{group.title}</strong>
                      <small>{group.summary}</small>
                    </span>
                    <span className="student-nav__group-meta" aria-hidden="true">
                      {group.items.length}
                      <b>{isOpen ? '-' : '+'}</b>
                    </span>
                  </button>

                  {isOpen ? (
                    <div className="student-nav__submenu">
                      {sortedItems.map((item, index) => {
                        const previousCategory = sortedItems[index - 1]?.category || ''
                        const currentCategory = item.category || ''
                        return (
                          <div key={`${group.key}-${item.label}`} className="student-nav__submenu-row">
                            {currentCategory && currentCategory !== previousCategory ? (
                              <span className="student-nav__submenu-title">{currentCategory}</span>
                            ) : null}
                            <button
                              type="button"
                              className={`student-nav__item ${itemIsActive(item) ? 'student-nav__item--active' : ''}`}
                              data-screen-page={item.page}
                              onClick={() => openPage(item.action)}
                            >
                              <strong>{item.label}</strong>
                              {item.description ? <span>{item.description}</span> : null}
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </nav>

          <button
            className="logout-button"
            onClick={() => {
              setMobileMenuOpen(false)
              onLogout()
            }}
          >
            <span className="logout-button__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M10 17l5-5-5-5" />
                <path d="M15 12H3" />
                <path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7" />
              </svg>
            </span>
            <span>Cerrar sesión</span>
          </button>
        </div>
      </aside>

      {mobileMenuOpen ? (
        <button
          type="button"
          className="student-mobile-menu-backdrop"
          aria-label="Cerrar menú"
          onClick={() => setMobileMenuOpen(false)}
        />
      ) : null}

      <section className="student-main">
        {['ADMINISTRADOR', 'ACADEMICO', 'DOCENTE'].includes(normalizedRole)
          && screenAccessPages?.includes('moodle/alerts')
          && !(activePage === 'moodle' && activeMoodleSection === 'alerts') ? (
            <MoodleGradeAlertIndicator
              role={normalizedRole}
              onOpen={() => onOpenMoodle('alerts')}
            />
          ) : null}
        {children}
      </section>
    </div>
  )
}
