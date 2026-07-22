import { useEffect, useState, type ReactNode } from 'react'

import type { Page, PortalStudentSection, PreinscriptionStage } from '../types/app'

type StudentLayoutProps = {
  activePage: Page
  activeSisAcademicoSection?: string
  activeLegacyReport?: string
  activePortalStudentSection?: PortalStudentSection
  activePreinscriptionStage?: PreinscriptionStage
  role?: string
  displayName?: string
  cedula?: string
  onOpenDashboard: () => void
  onOpenPortalEstudiante: (section?: PortalStudentSection) => void
  onOpenPortalDocente: () => void
  onOpenPortalDocenteInforme: () => void
  onOpenPortalDocentePlanificacion: () => void
  onOpenPortalDocenteContratos: () => void
  onOpenTeams: () => void
  onOpenTeamsMatricula: () => void
  onOpenMatricula: () => void
  onOpenMatriculaAcad: () => void
  onOpenMatriculaDocente: () => void
  onOpenEstadoDocente: () => void
  onOpenSenescytEstudiantes: () => void
  onOpenActualizarDatosEstudiante: () => void
  onOpenPreinscripcion: (stage?: PreinscriptionStage) => void
  onOpenReporteriaCarreras: () => void
  onOpenReporteriaIntegral: (reportKey?: string) => void
  onOpenReportesIndividuales: (reportKey?: string) => void
  onOpenGestionSisAcademico: (sectionKey?: string) => void
  onOpenSisAcademicoV1: () => void
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
  onOpenTeacherEvaluationProgress: () => void
  onOpenTeacherEvaluationReports: () => void
  onOpenTeacherComplianceFormat: () => void
  onOpenPracticasInstitucionales: () => void
  onLogout: () => void
  children: ReactNode
}

type NavItem = {
  label: string
  description?: string
  page?: Page
  sectionKey?: string
  reportKey?: string
  portalSection?: PortalStudentSection
  preinscriptionStage?: PreinscriptionStage
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
  '1': { initials: 'AD', title: 'Administracion' },
  ADMINISTRADOR: { initials: 'AD', title: 'Administracion' },
  ADMINISTRACION: { initials: 'AD', title: 'Administracion' },
  ADMINISTRACIÓN: { initials: 'AD', title: 'Administracion' },
  ADMIN: { initials: 'AD', title: 'Administracion' },
  FINANCIERO: { initials: 'FI', title: 'Financiero' },
  BIENESTAR: { initials: 'BI', title: 'Bienestar' },
  ACADEMICO: { initials: 'AC', title: 'Academico' },
  ADMISIONES: { initials: 'AM', title: 'Admisiones' },
  RECTOR: { initials: 'RC', title: 'Rectoria' },
  VICERRECTOR: { initials: 'VR', title: 'Vicerrectoria' },
  SOPORTE: { initials: 'TI', title: 'Tecnologia' },
  INVITADO_SOP: { initials: 'IS', title: 'Invitado soporte' },
  SECRETARIA: { initials: 'SE', title: 'Secretaria' },
  DOCENTE: { initials: 'DC', title: 'Docente' },
  ESTUDIANTE: { initials: 'ES', title: 'Estudiante' },
  TECNOLOGIA: { initials: 'TI', title: 'Tecnologia' },
  TI: { initials: 'TI', title: 'Tecnologia' },
}

const administratorRoles = new Set(['1', 'ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN'])
const academicRoles = new Set(['ACADEMICO', 'BIENESTAR'])
const dashboardOnlyRoles = new Set(['RECTOR', 'VICERRECTOR'])
const technicalGlobalRoles = new Set(['ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN', 'SOPORTE'])
const financialPages = new Set<Page>(['dashboard', 'preinscripcion', 'ingreso-ventas', 'gestion-sisacademico', 'sisacademico-v1', 'reporteria-integral', 'carnet-institucional'])
const academicPages = new Set<Page>([
  'dashboard',
  'matricula',
  'matricula-acad',
  'matricula-docente',
  'estado-docente',
  'actualizar-datos-estudiante',
  'reportes-individuales',
  'gestion-sisacademico',
  'sisacademico-v1',
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
  'practicas-institucionales',
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
])
const financialSisSections = new Set(['cabecera_matricula', 'pagos_matricula', 'datos_factura'])
const academicReportKeys = new Set(['notas_carrera_materia', 'evaluacion_docente', 'genero_docentes'])
const financialReportKeys = new Set(['provincia', 'genero', 'carrera', 'periodo', 'graduados_2025'])
const admissionsPages = new Set<Page>(['dashboard', 'preinscripcion', 'gestion-sisacademico', 'sisacademico-v1'])
const admissionsSisSections = new Set(['preinscripciones', 'estudiantes', 'cabecera_matricula', 'pagos_matricula', 'datos_factura'])
const secretaryPages = new Set<Page>(['practicas-institucionales', 'fecha-grado', 'senescyt-estudiantes', 'titulacion', 'titulacion-proceso', 'titulacion-responsables', 'titulos-registrados'])

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

function customPagesForRole(role: string): Set<Page> | null {
  try {
    const raw = window.localStorage.getItem('intec:user-type-screen-access:v1')
    if (!raw) return null
    const assignments = JSON.parse(raw) as Partial<Record<string, Page[]>>
    const pages = assignments[normalizeRoleKey(role)]
    return Array.isArray(pages) ? new Set(pages) : null
  } catch {
    return null
  }
}

function navItemAllowedForRole(role: string, item: NavItem) {
  const normalizedRole = normalizeRoleKey(role)
  const customPages = customPagesForRole(normalizedRole)
  const isTeacherCorePage = normalizedRole === 'DOCENTE' && (
    item.page === 'portal-docente'
    || item.page === 'portal-docente-informe'
    || item.page === 'portal-docente-planificacion'
    || item.page === 'portal-docente-contratos'
  )
  const allowedByCustomConfig = isTeacherCorePage || !item.page || item.page === 'asignacion-pantallas' || !customPages || customPages.has(item.page)
  if (!allowedByCustomConfig) return false
  if (normalizedRole === 'ESTUDIANTE') return item.page === 'portal-estudiante' || item.page === 'evaluacion-docente' || item.page === 'practicas-institucionales' || item.page === 'carnet-institucional'
  if (normalizedRole === 'DOCENTE') return item.page === 'portal-docente' || item.page === 'portal-docente-informe' || item.page === 'portal-docente-planificacion' || item.page === 'portal-docente-contratos' || item.page === 'carnet-institucional'
  if (normalizedRole === 'ADMISIONES') {
    if (!item.page || !admissionsPages.has(item.page)) return false
    if (item.sectionKey && !admissionsSisSections.has(item.sectionKey)) return false
    return true
  }
  if (normalizedRole === 'SECRETARIA') {
    return Boolean(item.page && secretaryPages.has(item.page))
  }
  if (dashboardOnlyRoles.has(normalizedRole)) return item.page === 'dashboard'
  if (academicRoles.has(normalizedRole)) {
    if (!item.page || !academicPages.has(item.page)) return false
    if (item.sectionKey && !academicSisSections.has(item.sectionKey)) return false
    if (item.reportKey && !academicReportKeys.has(item.reportKey)) return false
    return true
  }
  if (normalizedRole === 'FINANCIERO') {
    if (!item.page || !financialPages.has(item.page)) return false
    if (item.sectionKey && !financialSisSections.has(item.sectionKey)) return false
    if (item.reportKey && !financialReportKeys.has(item.reportKey)) return false
    return true
  }
  if (technicalGlobalRoles.has(normalizedRole)) return item.page !== 'portal-estudiante' && item.page !== 'portal-docente' && item.page !== 'portal-docente-informe' && item.page !== 'portal-docente-planificacion' && item.page !== 'portal-docente-contratos'
  return item.page === 'dashboard'
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

function sortNavItems(items: NavItem[]) {
  return [...items].sort((left, right) => {
    const categoryCompare = (left.category || '').localeCompare(right.category || '', 'es', { sensitivity: 'base' })
    if (categoryCompare !== 0) return categoryCompare
    return left.label.localeCompare(right.label, 'es', { sensitivity: 'base' })
  })
}

function sortNavGroups(groups: NavGroup[]) {
  const order: Record<string, number> = {
    inicio: 0,
    'flujo-academico': 5,
    'actualizacion-estados': 10,
    administracion: 20,
    desempeno: 25,
    'admision-matriculas': 30,
    becas: 32,
    migracion: 35,
    carnetizacion: 50,
    certificados: 60,
    'datos-senecyt': 70,
    'portal-docente': 80,
    'portal-estudiante': 90,
    integraciones: 100,
    catalogos: 110,
    reporteria: 120,
    'reportes-rh': 121,
    vinculacion: 130,
  }

  return [...groups].sort((left, right) => {
    const leftOrder = order[left.key] ?? 999
    const rightOrder = order[right.key] ?? 999
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return left.title.localeCompare(right.title, 'es', { sensitivity: 'base' })
  })
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
    becas: 'briefcase',
    'admision-proceso': 'admission',
    migracion: 'matricula',
    certificados: 'certificate',
    'portal-estudiante': 'student',
    'portal-docente': 'teacher',
    administracion: 'users',
    desempeno: 'academic',
    carnetizacion: 'id-card',
    vinculacion: 'briefcase',
    catalogos: 'catalog',
    reporteria: 'report',
    'datos-senecyt': 'report',
    integraciones: 'integration',
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
  role = '',
  displayName = '',
  cedula = '',
  onOpenDashboard,
  onOpenPortalEstudiante,
  onOpenPortalDocente,
  onOpenPortalDocenteInforme,
  onOpenPortalDocentePlanificacion,
  onOpenPortalDocenteContratos,
  onOpenTeams,
  onOpenTeamsMatricula,
  onOpenMatriculaAcad,
  onOpenMatriculaDocente,
  onOpenEstadoDocente,
  onOpenSenescytEstudiantes,
  onOpenActualizarDatosEstudiante,
  onOpenPreinscripcion,
  onOpenReporteriaIntegral,
  onOpenReportesIndividuales,
  onOpenGestionSisAcademico,
  onOpenSisAcademicoV1,
  onOpenAsignacionPantallas,
  onOpenPeriodoAcademico,
  onOpenIngresoVentas,
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
  onOpenTeacherEvaluationProgress,
  onOpenTeacherEvaluationReports,
  onOpenTeacherComplianceFormat,
  onOpenPracticasInstitucionales,
  onLogout,
  children,
}: Readonly<StudentLayoutProps>) {
  const normalizedRole = role.trim().toUpperCase()
  const isAdministrator = isAdministratorRole(normalizedRole)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobileViewport, setIsMobileViewport] = useState(false)
  const [openMenuGroups, setOpenMenuGroups] = useState<Set<string>>(() => new Set())
  const [, setAccessConfigVersion] = useState(0)

  useEffect(() => {
    const coarsePointerQuery = window.matchMedia('(pointer: coarse)')

    const syncMobileState = () => {
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth
      const isMobile = viewportWidth <= 767 || (coarsePointerQuery.matches && viewportWidth <= 1180)
      setIsMobileViewport(isMobile)
      if (!isMobile) {
        setMobileMenuOpen(false)
      }
    }

    syncMobileState()
    coarsePointerQuery.addEventListener('change', syncMobileState)
    window.addEventListener('resize', syncMobileState)

    return () => {
      coarsePointerQuery.removeEventListener('change', syncMobileState)
      window.removeEventListener('resize', syncMobileState)
    }
  }, [])

  useEffect(() => {
    const refreshAccessConfig = () => setAccessConfigVersion((current) => current + 1)
    window.addEventListener('intec-screen-access-updated', refreshAccessConfig)
    window.addEventListener('storage', refreshAccessConfig)
    return () => {
      window.removeEventListener('intec-screen-access-updated', refreshAccessConfig)
      window.removeEventListener('storage', refreshAccessConfig)
    }
  }, [])

  const preinscriptionFlowItems: NavItem[] = [
    {
      label: 'Inscripcion',
      description: 'Registrar nuevo aspirante.',
      page: 'preinscripcion',
      preinscriptionStage: 'registro',
      category: 'Ingreso',
      action: () => onOpenPreinscripcion('registro'),
    },
    {
      label: 'Inscritos',
      description: 'Buscar y seleccionar estudiantes inscritos.',
      page: 'preinscripcion',
      preinscriptionStage: 'inscritos',
      category: 'Ingreso',
      action: () => onOpenPreinscripcion('inscritos'),
    },
    {
      label: 'Cabecera matrícula',
      description: 'Generar matrícula en cabecera, pago y convenio.',
      page: 'preinscripcion',
      preinscriptionStage: 'cabecera',
      category: 'Matrícula',
      action: () => onOpenPreinscripcion('cabecera'),
    },
    {
      label: 'Documentos',
      description: 'Cargar documentos del estudiante.',
      page: 'preinscripcion',
      preinscriptionStage: 'documentos',
      category: 'Matrícula',
      action: () => onOpenPreinscripcion('documentos'),
    },
    {
      label: 'Matricular primer nivel',
      description: 'Matricular materias del primer nivel.',
      page: 'preinscripcion',
      preinscriptionStage: 'materias',
      category: 'Matrícula',
      action: () => onOpenPreinscripcion('materias'),
    },
    {
      label: 'Seguimiento',
      description: 'Contacto, avance y cierre.',
      page: 'preinscripcion',
      preinscriptionStage: 'seguimiento',
      category: 'Cierre',
      action: () => onOpenPreinscripcion('seguimiento'),
    },
  ]
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
    ],
  }
  const salesPreinscriptionFlowItems: NavItem[] = [
    {
      label: 'Paso 1: Inscribir',
      description: 'Registrar al estudiante o seleccionarlo desde inscritos.',
      page: 'preinscripcion',
      preinscriptionStage: 'registro',
      category: 'Proceso regular',
      action: () => onOpenPreinscripcion('registro'),
    },
    {
      label: 'Paso 2: Matricular y documentar',
      description: 'Generar cabecera, convenio de pago y subir documentos.',
      page: 'preinscripcion',
      preinscriptionStage: 'documentos',
      category: 'Proceso regular',
      action: () => onOpenPreinscripcion('documentos'),
    },
  ]

  const academicLifecycleItems: NavItem[] = [
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
      label: '3. Matrícula académica',
      description: 'Registrar cabecera, materias, pagos y convenio de matrícula.',
      page: 'matricula-acad',
      category: 'Flujo académico',
      action: onOpenMatriculaAcad,
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
      label: '7. Certificados y grado',
      description: 'Emitir certificados, revisar fecha de grado y respaldos documentales.',
      page: 'certificados',
      category: 'Flujo académico',
      action: onOpenCertificados,
    },
    {
      label: '8. Titulación',
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
        {
          label: 'SisAcademicoV1',
          description: 'Mapa de clonación, tablas V1, módulos y accesos migrados.',
          page: 'sisacademico-v1',
          action: onOpenSisAcademicoV1,
        },
      ],
    },
    {
      key: 'actualizacion-estados',
      title: 'Actualizacion de estados',
      summary: 'Docentes y estudiantes',
      items: [
        {
          label: 'Estado docente',
          description: 'Activa o inactiva docentes validando DATOSDOCENTE y USUARIOS.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_est',
          action: () => onOpenGestionSisAcademico('actualizacion_est'),
        },
        {
          label: 'Estado estudiante',
          description: 'Activa o inactiva estudiantes desde DATOS_ESTUD usando ESTADO.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_estudiantes',
          action: () => onOpenGestionSisAcademico('actualizacion_estudiantes'),
        },
      ],
    },
    {
      key: 'admision-matriculas',
      title: 'Admision y matriculas',
      summary: 'Aspirantes, matricula y pagos',
      items: [
        ...preinscriptionFlowItems,
        {
          label: 'Aspirantes y asesores',
          description: 'Gestion directa de inscripciones.',
          category: 'Consulta directa',
          page: 'gestion-sisacademico',
          sectionKey: 'preinscripciones',
          action: () => onOpenGestionSisAcademico('preinscripciones'),
        },
        {
          label: 'Datos de factura',
          description: 'Datos tributarios vinculados a la inscripcion y matricula.',
          page: 'gestion-sisacademico',
          sectionKey: 'datos_factura',
          action: () => onOpenGestionSisAcademico('datos_factura'),
        },
        { label: 'Matricula academica', description: 'Flujo academico actual de matricula.', page: 'matricula-acad', action: onOpenMatriculaAcad },
        {
          label: 'Cabecera matricula y pagos',
          description: 'Valores, documentos, jornada y control de matricula.',
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
    ...(isAdministratorRole(normalizedRole) ? [scholarshipMenuGroup] : []),
    {
      key: 'migracion',
      title: 'Migracion',
      summary: 'Cambio de periodo H a R',
      items: [
        {
          label: 'Migracion H a R',
          description: 'Migrar matriculas de homologacion hacia periodo regular.',
          page: 'gestion-sisacademico',
          sectionKey: 'cambio_periodo_hr',
          action: () => onOpenGestionSisAcademico('cambio_periodo_hr'),
        },
      ],
    },
    {
      key: 'certificados',
      title: 'Certificados',
      summary: 'Promocion y matricula',
      items: [
        {
          label: 'Certificados',
          description: 'Generar y revisar certificados institucionales.',
          page: 'certificados',
          action: onOpenCertificados,
        },
        {
          label: 'Fecha de grado',
          description: 'Registrar fecha de grado por periodo y carrera.',
          page: 'fecha-grado',
          action: onOpenFechaGrado,
        },
        {
          label: 'Matrícula en Excel',
          description: 'Generar certificados de matrícula desde plantilla Excel.',
          page: 'matricula-excel-certificados',
          action: onOpenMatriculaExcelCertificados,
        },
        {
          label: 'Renombrar certificados',
          description: 'Leer cedula en PDF y renombrar por estudiante.',
          page: 'renombrar-certificados',
          action: onOpenCertificateRenamer,
        },
        {
          label: 'Historial de certificados',
          description: 'Certificados generados en SisAcademicoV1 y su estado.',
          page: 'gestion-sisacademico',
          sectionKey: 'certificados_generados',
          action: () => onOpenGestionSisAcademico('certificados_generados'),
        },
        {
          label: 'Credenciales de curso',
          description: 'Credenciales temporales, Graph y envio por correo.',
          page: 'gestion-sisacademico',
          sectionKey: 'credenciales_curso',
          action: () => onOpenGestionSisAcademico('credenciales_curso'),
        },
      ],
    },
    {
      key: 'educacion-continua',
      title: 'Educacion continua',
      summary: 'Cursos, cortes y participantes',
      items: [
        {
          label: 'Cursos',
          description: 'Cursos de educacion continua conservados del sistema anterior.',
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
      summary: 'SENESCYT e INTEC',
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
          action: () => onOpenTitulosRegistrados('senescyt'),
        },
        {
          label: 'Títulos INTEC',
          description: 'Carpetas y documentos institucionales INTEC.',
          page: 'titulos-registrados',
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
          description: 'Genera Excel por carrera y faltantes para estudiantes y docentes.',
          page: 'senescyt-estudiantes',
          action: onOpenSenescytEstudiantes,
        },
      ],
    },
    {
      key: 'portal-estudiante',
      title: 'Estudiante',
      summary: 'Ficha, matricula, notas, correos y seguimiento',
      items: [
        {
          label: 'Ficha del estudiante',
          description: 'Listado y ficha academica del estudiante.',
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
          label: 'Correos institucionales',
          description: 'Correos INTEC, claves y estado de envio.',
          page: 'gestion-sisacademico',
          sectionKey: 'correos',
          action: () => onOpenGestionSisAcademico('correos'),
        },
        {
          label: 'Materias y notas',
          description: 'Materias matriculadas, paralelos y calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'matricula_materias',
          action: () => onOpenGestionSisAcademico('matricula_materias'),
        },
        {
          label: 'Notas por carrera y periodo',
          description: 'Reporte filtrado por carrera y periodo.',
          page: 'reportes-individuales',
          reportKey: 'notas_carrera_materia',
          action: () => onOpenReportesIndividuales('notas_carrera_materia'),
        },
        {
          label: 'Evaluacion docente',
          description: 'Cuestionario por materia, periodo y docente asignado.',
          page: 'evaluacion-docente',
          action: onOpenTeacherEvaluation,
        },
        {
          label: 'Seguimiento academico',
          description: 'Observaciones y acompanamiento por materia.',
          page: 'gestion-sisacademico',
          sectionKey: 'seguimiento',
          action: () => onOpenGestionSisAcademico('seguimiento'),
        },
        { label: 'Actualizar datos', description: 'Actualizacion de datos personales de estudiantes y docentes.', page: 'actualizar-datos-estudiante', action: onOpenActualizarDatosEstudiante },
        {
          label: 'Actualizacion estado estudiante',
          description: 'Actualiza el estado academico usando el catalogo ESTADO.',
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
        { label: 'Matriculacion docente', description: 'Proceso de matriculacion/asignacion docente.', page: 'matricula-docente', action: onOpenMatriculaDocente },
        {
          label: 'Materias asignadas',
          description: 'Relacion docente, materia, periodo, paralelo y jornada.',
          page: 'gestion-sisacademico',
          sectionKey: 'docente_materias',
          action: () => onOpenGestionSisAcademico('docente_materias'),
        },
        {
          label: 'Actualizacion estado docente',
          description: 'Valida DATOSDOCENTE y USUARIOS para activar o inactivar docentes.',
          page: 'gestion-sisacademico',
          sectionKey: 'actualizacion_est',
          action: () => onOpenGestionSisAcademico('actualizacion_est'),
        },
        {
          label: 'Control de cuestionarios',
          description: 'Numero de preguntas, intentos y tiempo por materia.',
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
          label: 'Preguntas de evaluacion',
          description: 'Banco de preguntas para evaluacion, pares y autoevaluacion.',
          page: 'gestion-sisacademico',
          sectionKey: 'preguntas_evaluacion',
          action: () => onOpenGestionSisAcademico('preguntas_evaluacion'),
        },
        {
          label: 'Planes, cuestionarios y foros',
          description: 'Recursos, enlaces y fechas por materia y periodo.',
          page: 'gestion-sisacademico',
          sectionKey: 'planes_foros',
          action: () => onOpenGestionSisAcademico('planes_foros'),
        },
        { label: 'Estado docente', description: 'Revision y control del estado docente.', page: 'estado-docente', action: onOpenEstadoDocente },
        {
          label: 'Evaluacion docente',
          description: 'Resultados y reportes de evaluacion docente.',
          page: 'reportes-individuales',
          reportKey: 'evaluacion_docente',
          action: () => onOpenReportesIndividuales('evaluacion_docente'),
        },
        {
          label: 'Resultados de evaluacion',
          description: 'Registro directo de respuestas y puntajes por periodo.',
          page: 'gestion-sisacademico',
          sectionKey: 'evaluacion_resultados',
          action: () => onOpenGestionSisAcademico('evaluacion_resultados'),
        },
        {
          label: 'Resultados de autoevaluacion',
          description: 'Puntajes y comentarios de autoevaluacion docente.',
          page: 'gestion-sisacademico',
          sectionKey: 'autoevaluacion_resultados',
          action: () => onOpenGestionSisAcademico('autoevaluacion_resultados'),
        },
        {
          label: 'Apertura de autoevaluacion',
          description: 'Fechas de habilitacion para autoevaluacion docente.',
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
          description: 'Pendientes por periodo y PDF de calificación docente.',
          page: 'evaluacion-docente-reportes',
          action: onOpenTeacherEvaluationReports,
        },
      ],
    },
    {
      key: 'administracion',
      title: 'Administracion y accesos',
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
          description: 'Mapa funcional de accesos por perfil y módulos disponibles.',
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
        {
          label: 'Mapa operativo',
          description: 'Acceso funcional a los procesos clonados desde SisAcademicoV1.',
          page: 'gestion-sisacademico',
          sectionKey: 'menu_general',
          action: () => onOpenGestionSisAcademico('menu_general'),
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
          description: 'Ficha base de empleados del modulo RRHH.',
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
      key: 'integraciones-v1',
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
          label: 'Sincronizacion Moodle',
          description: 'Historial de procesos de sincronizacion de calificaciones.',
          page: 'gestion-sisacademico',
          sectionKey: 'moodle_sincronizacion',
          action: () => onOpenGestionSisAcademico('moodle_sincronizacion'),
        },
        {
          label: 'Auditoria Microsoft 365',
          description: 'Acciones, estados y errores de servicios Microsoft 365.',
          page: 'gestion-sisacademico',
          sectionKey: 'microsoft365_audit',
          action: () => onOpenGestionSisAcademico('microsoft365_audit'),
        },
      ],
    },
    {
      key: 'carnetizacion',
      title: 'Carnetizacion',
      summary: 'Aprobacion, renovacion y emision de carnets',
      items: [
        {
          label: 'Aprobacion de carnet',
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
      items: [
        {
          label: 'Módulo institucional',
          description: 'Crear expedientes PPF/VIN y designar responsables.',
          page: 'practicas-institucionales',
          action: onOpenPracticasInstitucionales,
        },
        {
          label: 'Practicas profesionales',
          description: 'Registro de practicas, horas, docente y empresa.',
          page: 'gestion-sisacademico',
          sectionKey: 'practicas',
          action: () => onOpenGestionSisAcademico('practicas'),
        },
        {
          label: 'Vinculación con la sociedad',
          description: 'Proyectos de vinculación con la sociedad, horas, docente y evidencias.',
          page: 'gestion-sisacademico',
          sectionKey: 'practicas_vinculacion',
          action: () => onOpenGestionSisAcademico('practicas_vinculacion'),
        },
        {
          label: 'Empresas',
          description: 'Empresas usadas en practicas profesionales.',
          page: 'gestion-sisacademico',
          sectionKey: 'empresas',
          action: () => onOpenGestionSisAcademico('empresas'),
        },
      ],
    },
    {
      key: 'catalogos',
      title: 'Proceso academico',
      summary: 'Carreras, materias, periodos, paralelos y mallas',
      items: [
        {
          label: 'Carreras',
          description: 'Oferta academica y estado de carrera.',
          page: 'gestion-sisacademico',
          sectionKey: 'carreras',
          action: () => onOpenGestionSisAcademico('carreras'),
        },
        {
          label: 'Materias y pensum',
          description: 'Materias, creditos, niveles y malla.',
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
          description: 'Texto, URL y periodo por codigo de materia homologada.',
          page: 'gestion-sisacademico',
          sectionKey: 'materia_homo_textof',
          action: () => onOpenGestionSisAcademico('materia_homo_textof'),
        },
        {
          label: 'Paralelos',
          description: 'Catalogo y mantenimiento academico de paralelos.',
          page: 'gestion-sisacademico',
          sectionKey: 'paralelos',
          action: () => onOpenGestionSisAcademico('paralelos'),
        },
        { label: 'Periodos academicos', description: 'Resumen de periodos y estudiantes.', page: 'periodo-academico', action: onOpenPeriodoAcademico },
        {
          label: 'Periodos del sistema',
          description: 'Mantenimiento directo de PERIODO.',
          page: 'gestion-sisacademico',
          sectionKey: 'periodos',
          action: () => onOpenGestionSisAcademico('periodos'),
        },
        {
          label: 'Provincias',
          description: 'Catalogo territorial para inscripciones y estudiantes.',
          page: 'gestion-sisacademico',
          sectionKey: 'provincias',
          action: () => onOpenGestionSisAcademico('provincias'),
        },
        {
          label: 'Apertura de notas',
          description: 'Fechas para ingreso de notas por parcial y periodo.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_notas',
          action: () => onOpenGestionSisAcademico('fechas_notas'),
        },
        {
          label: 'Apertura de autoevaluacion',
          description: 'Fechas vigentes para autoevaluacion por periodo.',
          page: 'gestion-sisacademico',
          sectionKey: 'fechas_autoevaluacion',
          action: () => onOpenGestionSisAcademico('fechas_autoevaluacion'),
        },
        {
          label: 'Asistencia estudiantes',
          description: 'Registro por estudiante, materia, periodo y paralelo.',
          page: 'gestion-sisacademico',
          sectionKey: 'asistencia_estudiantes',
          action: () => onOpenGestionSisAcademico('asistencia_estudiantes'),
        },
        {
          label: 'Jornadas',
          description: 'Jornadas y relacion con modalidad.',
          page: 'gestion-sisacademico',
          sectionKey: 'jornadas',
          action: () => onOpenGestionSisAcademico('jornadas'),
        },
        {
          label: 'Dias de matricula',
          description: 'Catalogo legacy de dias para el proceso de matricula.',
          page: 'gestion-sisacademico',
          sectionKey: 'dias_matricula',
          action: () => onOpenGestionSisAcademico('dias_matricula'),
        },
        {
          label: 'Horarios de matricula',
          description: 'Catalogo legacy de horarios para matricula.',
          page: 'gestion-sisacademico',
          sectionKey: 'horarios_matricula',
          action: () => onOpenGestionSisAcademico('horarios_matricula'),
        },
        {
          label: 'Modalidades',
          description: 'Modalidades de matricula.',
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
        ...(isAdministrator
          ? [{
              label: 'Credenciales Office 365',
              description: 'Crear usuarios por curso mediante Microsoft Graph.',
              page: 'credenciales' as Page,
              action: onOpenCredentialGenerator,
            }]
          : []),
        {
          label: 'Correos masivos',
          description: 'Enviar mensajes con adjuntos por cedula mediante Microsoft Graph.',
          page: 'correos-masivos' as Page,
          action: onOpenMassEmail,
        },
        { label: 'Movimientos Teams', description: 'Gestion de equipos y movimientos.', page: 'teams', action: onOpenTeams },
        { label: 'Matricula Teams', description: 'Creacion y matricula de equipos.', page: 'teams-matricula', action: onOpenTeamsMatricula },
      ],
    },
  ]

  const admissionsMenuGroups: NavGroup[] = [
    {
      key: 'inicio',
      title: 'Inicio',
      summary: 'Ventas personales',
      items: [
        {
          label: 'Dashboard',
          description: 'Inscripciones y estados de tus ventas.',
          page: 'dashboard',
          action: onOpenDashboard,
        },
        {
          label: 'SisAcademicoV1',
          description: 'Módulos, tablas y accesos compatibles del sistema anterior.',
          page: 'sisacademico-v1',
          action: onOpenSisAcademicoV1,
        },
      ],
    },
    {
      key: 'admision-proceso',
      title: 'Admisiones',
      summary: 'Inscripcion, matricula y estudiantes',
      items: [
        ...salesPreinscriptionFlowItems,
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
          description: 'Datos tributarios registrados durante la inscripcion.',
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
    {
      key: 'certificados',
      title: 'Certificados',
      summary: 'Promocion y matricula',
      items: [
        {
          label: 'Certificados',
          description: 'Generar y revisar certificados institucionales.',
          page: 'certificados',
          action: onOpenCertificados,
        },
        {
          label: 'Fecha de grado',
          description: 'Registrar fecha de grado por periodo y carrera.',
          page: 'fecha-grado',
          action: onOpenFechaGrado,
        },
        {
          label: 'Matrícula en Excel',
          description: 'Generar certificados de matrícula desde plantilla Excel.',
          page: 'matricula-excel-certificados',
          action: onOpenMatriculaExcelCertificados,
        },
        {
          label: 'Renombrar certificados',
          description: 'Leer cedula en PDF y renombrar por estudiante.',
          page: 'renombrar-certificados',
          action: onOpenCertificateRenamer,
        },
      ],
    },
    {
      key: 'admision-integraciones',
      title: 'Integraciones',
      summary: 'Correo y servicios Microsoft',
      items: [
        {
          label: 'Correos masivos',
          description: 'Enviar mensajes con adjuntos por cedula.',
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
      title: 'Control de matricula',
      summary: 'Pago, convenio y valores',
      items: [
        {
          label: 'Pago y convenio',
          description: 'Validar cabecera, valores y convenio de matricula.',
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
        {
          label: 'SisAcademicoV1',
          description: 'Clonación funcional de módulos académicos y administrativos.',
          page: 'sisacademico-v1',
          action: onOpenSisAcademicoV1,
        },
      ],
    },
    ...(
      normalizedRole === 'BIENESTAR'
        ? [scholarshipMenuGroup]
        : []
    ),
    {
      key: 'admision-matriculas',
      title: 'Control de matrícula',
      summary: 'Matrícula, estudiantes y notas',
      items: [
        { label: 'Matrícula académica', description: 'Control y registro académico de matrícula.', page: 'matricula-acad', action: onOpenMatriculaAcad },
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
        { label: 'Periodos académicos', description: 'Periodos, estudiantes y estado académico.', page: 'periodo-academico', action: onOpenPeriodoAcademico },
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
        { label: 'Matriculación docente', description: 'Asignación docente por materia, periodo y paralelo.', page: 'matricula-docente', action: onOpenMatriculaDocente },
        {
          label: 'Materias asignadas',
          description: 'Relación docente, materia, periodo, paralelo y jornada.',
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
          label: 'Reporte de notas',
          description: 'Reporte por carrera, materia, periodo y estudiante.',
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
          description: 'Avance por periodo y ponderación de evaluación docente.',
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
      summary: 'Carreras, materias y periodos',
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
          label: 'Periodos del sistema',
          description: 'Mantenimiento directo de periodos académicos.',
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
      summary: 'Repositorio y certificados',
      items: [
        {
          label: 'Repositorio digital',
          description: 'Documentos bibliográficos y enlaces por carrera.',
          page: 'gestion-sisacademico',
          sectionKey: 'repositorio',
          action: () => onOpenGestionSisAcademico('repositorio'),
        },
        {
          label: 'Historial de certificados',
          description: 'Certificados generados y códigos de verificación.',
          page: 'gestion-sisacademico',
          sectionKey: 'certificados_generados',
          action: () => onOpenGestionSisAcademico('certificados_generados'),
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
      items: [
        {
          label: 'Módulo institucional',
          description: 'Matricular estudiantes y asignar responsable de prácticas.',
          page: 'practicas-institucionales',
          action: onOpenPracticasInstitucionales,
        },
      ],
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
      key: 'vinculacion',
      title: 'Prácticas institucionales',
      summary: 'Preprofesionales y vinculación con la sociedad',
      items: [
        {
          label: 'Prácticas y vinculación con la sociedad',
          description: 'Observar expedientes, estudiantes, responsables y avance documental.',
          page: 'practicas-institucionales',
          action: onOpenPracticasInstitucionales,
        },
      ],
    },
    {
      key: 'certificados',
      title: 'Graduados',
      summary: 'Fechas y registro académico',
      items: [
        {
          label: 'Fechas de graduados',
          description: 'Actualizar fecha de grado, emisión SENESCYT y código de refrendación.',
          page: 'fecha-grado',
          action: onOpenFechaGrado,
        },
      ],
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
      summary: 'SENESCYT e INTEC',
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
          action: () => onOpenTitulosRegistrados('senescyt'),
        },
        {
          label: 'Títulos INTEC',
          description: 'Consultar carpetas y documentos institucionales INTEC.',
          page: 'titulos-registrados',
          action: () => onOpenTitulosRegistrados('intec'),
        },
      ],
    },
  ]

  const studentMenuGroups: NavGroup[] = [
    {
      key: 'portal-estudiante',
      title: 'Estudiante',
      summary: 'Dashboard, mallas y calificaciones',
      items: [
        {
          label: 'Dashboard academico',
          description: 'Inicio con avance, cumplimiento y accesos rapidos.',
          page: 'portal-estudiante',
          portalSection: 'dashboard',
          action: () => onOpenPortalEstudiante('dashboard'),
        },
        {
          label: 'Malla curricular',
          description: 'Materias a cursar, codigos, niveles y creditos.',
          page: 'portal-estudiante',
          portalSection: 'curricular',
          action: () => onOpenPortalEstudiante('curricular'),
        },
        {
          label: 'Malla academica',
          description: 'Materias aprobadas, pendientes y avance por promedio.',
          page: 'portal-estudiante',
          portalSection: 'academica',
          action: () => onOpenPortalEstudiante('academica'),
        },
        {
          label: 'Calificaciones por periodo',
          description: 'Revision de notas filtrada por periodo academico.',
          page: 'portal-estudiante',
          portalSection: 'notas',
          action: () => onOpenPortalEstudiante('notas'),
        },
        {
          label: 'Evaluacion docente',
          description: 'Evalua al docente segun tus materias matriculadas.',
          page: 'evaluacion-docente',
          action: onOpenTeacherEvaluation,
        },
        {
          label: 'Prácticas institucionales',
          description: 'Crear y revisar prácticas preprofesionales o vinculación.',
          page: 'practicas-institucionales',
          action: onOpenPracticasInstitucionales,
        },
        {
          label: 'Carnet institucional',
          description: 'Subir foto y revisar estado de aprobacion.',
          page: 'carnet-institucional',
          action: onOpenCarnetInstitucional,
        },
      ],
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
        {
          label: 'Carnet institucional',
          description: 'Subir foto y revisar estado de aprobacion.',
          page: 'carnet-institucional',
          action: onOpenCarnetInstitucional,
        },
      ],
    },
  ]

  const baseMenuGroups =
    normalizedRole === 'ESTUDIANTE'
      ? studentMenuGroups
      : normalizedRole === 'DOCENTE'
        ? teacherMenuGroups
        : normalizedRole === 'ADMISIONES'
          ? admissionsMenuGroups
          : normalizedRole === 'SECRETARIA'
            ? secretaryMenuGroups
            : academicRoles.has(normalizedRole)
              ? academicMenuGroups
              : dashboardOnlyRoles.has(normalizedRole)
                ? executiveMenuGroups
                : normalizedRole === 'FINANCIERO'
                  ? financialMenuGroups
                  : adminMenuGroups

  const menuGroups = baseMenuGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => navItemAllowedForRole(normalizedRole, item)),
    }))
    .filter((group) => group.items.length > 0)

  const visibleMenuGroups = sortNavGroups(menuGroups)
  const fallbackBrandTitle = titleFromRole(normalizedRole || 'INTEC')
  const brand = roleBrandMap[normalizedRole] ?? {
    initials: initialsFromTitle(fallbackBrandTitle),
    title: fallbackBrandTitle,
  }
  const brandTitle = normalizedRole === 'ESTUDIANTE' && displayName.trim() ? displayName.trim() : brand.title
  const brandSubtitle = normalizedRole === 'ESTUDIANTE' && cedula.trim() ? `Cedula ${cedula.trim()}` : ''

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
    if (item.sectionKey) {
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
        aria-label="Menu lateral"
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
            <span className="student-mobile-menu-button__label">{mobileMenuOpen ? 'Cerrar' : 'Menu'}</span>
          </button>
        </div>

        <div className="student-sidebar__panel" id="student-mobile-nav">
          <nav className="student-nav" aria-label="Menu principal">
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
          aria-label="Cerrar menu"
          onClick={() => setMobileMenuOpen(false)}
        />
      ) : null}

      <section className="student-main">
        {children}
      </section>
    </div>
  )
}
