import { useCallback, useEffect, useState, type SyntheticEvent } from 'react'

import {
  ApiError,
  createClassroom,
  downloadExcelSqlCrossWorkbook,
  fetchDashboardMatricula,
  fetchExcelSqlCross,
  fetchIngresoVentas,
  fetchScreenAccessAssignments,
  fetchMatriculaCareerStateSummary,
  fetchMatriculaMovementSummary,
  fetchMatriculaPeriodSummary,
  enrollUserInTeam,
  fetchMatriculaList,
  fetchMatriculaSummary,
  fetchTeamsCatalog,
  getCurrentSession,
  loginRequest,
  logoutRequest,
  selectProfileRequest,
} from '../lib/api'
import { clearStoredPage, readStoredPage, writeStoredPage } from '../lib/storage'
import {
  firstPermissionForPage,
  permissionRootPage,
  screenPermissionAllowsCode,
  screenPermissionAllowsPage,
  screenPermissionForView,
} from '../lib/screenAccess'
import type {
  ExcelSqlCrossResponse,
  DashboardMatriculaResponse,
  AcademicEnrollmentMode,
  GraphTeam,
  IngresoVentasResponse,
  MatriculaCareerStateSummaryResponse,
  MatriculaPeriodSummaryItem,
  MatriculaStudentItem,
  MatriculaSummaryItem,
  MatriculaTipo,
  TeamCreateAndEnrollPayload,
  MatriculaYearSummaryItem,
  MoodleSection,
  Page,
  PreinscriptionStage,
  PortalStudentSection,
  PracticasProcessCode,
  ScreenPermissionCode,
  UserSession,
} from '../types/app'
import { useInactivityLogout } from './useInactivityLogout'

const INACTIVITY_TIMEOUT_MS = 20 * 60 * 1000
const SCREEN_ACCESS_SYNC_KEY = 'intec:screen-access-updated:v2'
const ADMIN_ONLY_PAGES = new Set<Page>(['sistema-academico', 'asignacion-pantallas'])
const ADMISSIONS_ALLOWED_PAGES: Page[] = [
  'dashboard',
  'preinscripcion',
  'gestion-sisacademico',
]
const ACADEMIC_ALLOWED_PAGES = new Set<Page>([
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
  'practicas-institucionales',
  'ingles',
  'expedientes-documentales',
])
const FINANCIAL_ALLOWED_PAGES = new Set<Page>([
  'dashboard',
  'preinscripcion',
  'ingreso-ventas',
  'gestion-sisacademico',
  'reporteria-integral',
  'carnet-institucional',
])
const SECRETARIA_ALLOWED_PAGES = new Set<Page>([
  'solicitudes-cambio-carrera',
  'solicitudes-cambio-modalidad',
  'practicas-institucionales',
  'fecha-grado',
  'senescyt-estudiantes',
  'titulacion',
  'titulacion-proceso',
  'titulacion-responsables',
  'titulos-registrados',
  'expedientes-documentales',
])
const DASHBOARD_ONLY_ROLES = new Set(['RECTOR', 'VICERRECTOR'])
const ADMINISTRATOR_ROLE_ALIASES = new Set(['1', 'ADMIN', 'ADMINISTRADOR', 'ADMINISTRACION'])
const TECHNICAL_GLOBAL_ROLES = new Set(['ADMINISTRADOR', 'SOPORTE'])
const MASS_EMAIL_ALLOWED_ROLES = new Set([
  'ADMINISTRADOR',
  'ACADEMICO',
  'ADMISIONES',
  'BIENESTAR',
  'FINANCIERO',
  'RECTOR',
  'VICERRECTOR',
  'SOPORTE',
])
const STUDENT_PORTAL_PAGE_BY_SECTION: Record<PortalStudentSection, Page> = {
  dashboard: 'portal-estudiante',
  curricular: 'portal-estudiante-malla-curricular',
  academica: 'portal-estudiante-malla-academica',
  notas: 'portal-estudiante-calificaciones',
}
const STUDENT_PORTAL_PAGES = new Set<Page>(Object.values(STUDENT_PORTAL_PAGE_BY_SECTION))

type ApiErrorOptions = {
  expireOnUnauthorized?: boolean
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizedRoleKey(role?: string): string {
  const normalized = role
    ?.trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') || ''
  return ADMINISTRATOR_ROLE_ALIASES.has(normalized) ? 'ADMINISTRADOR' : normalized
}

function defaultPageForRole(role?: string, assignedPages: ScreenPermissionCode[] | null = null): Page {
  const normalizedRole = normalizedRoleKey(role)
  const eligibleAssignedPages = assignedPages
  let preferredPage: Page = 'dashboard'
  if (normalizedRole === 'ESTUDIANTE') preferredPage = 'portal-estudiante'
  else if (normalizedRole === 'DOCENTE') preferredPage = 'portal-docente'
  else if (normalizedRole === 'FINANCIERO') preferredPage = 'preinscripcion'
  else if (normalizedRole === 'SECRETARIA') preferredPage = 'practicas-institucionales'

  if (
    eligibleAssignedPages !== null
    && eligibleAssignedPages.length > 0
    && !screenPermissionAllowsPage(eligibleAssignedPages, preferredPage)
  ) {
    return permissionRootPage(eligibleAssignedPages[0])
  }
  return preferredPage
}

function pageAllowedForRole(
  role: string | undefined,
  page: Page,
  assignedPages: ScreenPermissionCode[] | null = null,
): boolean {
  const normalizedRole = normalizedRoleKey(role)
  if (assignedPages !== null) return screenPermissionAllowsPage(assignedPages, page)
  if (ADMIN_ONLY_PAGES.has(page) && normalizedRole !== 'ADMINISTRADOR') return false
  if (page === 'expedientes-documentales' && !['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA'].includes(normalizedRole)) return false
  if (normalizedRole === 'ESTUDIANTE') {
    return STUDENT_PORTAL_PAGES.has(page) || page === 'ingles' || page === 'carnet-institucional' || page === 'evaluacion-docente' || page === 'practicas-institucionales'
  }
  if (normalizedRole === 'DOCENTE') return page === 'portal-docente' || page === 'ingles' || page === 'portal-docente-informe' || page === 'portal-docente-planificacion' || page === 'portal-docente-contratos' || page === 'practicas-institucionales' || page === 'carnet-institucional'
  if (normalizedRole === 'ADMISIONES') return ADMISSIONS_ALLOWED_PAGES.includes(page)
  if (normalizedRole === 'SECRETARIA') return SECRETARIA_ALLOWED_PAGES.has(page)
  if (DASHBOARD_ONLY_ROLES.has(normalizedRole || '')) return page === 'dashboard'
  if (normalizedRole === 'ACADEMICO' || normalizedRole === 'BIENESTAR') return ACADEMIC_ALLOWED_PAGES.has(page)
  if (normalizedRole === 'FINANCIERO') return FINANCIAL_ALLOWED_PAGES.has(page)
  if (page === 'credenciales') return normalizedRole === 'ADMINISTRADOR'
  if (page === 'correos-masivos') return MASS_EMAIL_ALLOWED_ROLES.has(normalizedRole || '')
  if (page === 'carnet-institucional') return Boolean(normalizedRole)
  if (TECHNICAL_GLOBAL_ROLES.has(normalizedRole || '')) return !STUDENT_PORTAL_PAGES.has(page) && page !== 'portal-docente' && page !== 'portal-docente-informe' && page !== 'portal-docente-planificacion' && page !== 'portal-docente-contratos'
  return page === 'dashboard'
}

function studentSectionForPage(page: Page): PortalStudentSection | null {
  if (page === 'portal-estudiante') return 'dashboard'
  if (page === 'portal-estudiante-malla-curricular') return 'curricular'
  if (page === 'portal-estudiante-malla-academica') return 'academica'
  if (page === 'portal-estudiante-calificaciones') return 'notas'
  return null
}

function preinscriptionStage(stage: string | null): PreinscriptionStage {
  const value = stage || ''
  return [
    'registro', 'inscritos', 'cabecera', 'documentos', 'materias',
    'seguimiento', 'gestion-becas', 'becas', 'becados', 'contratos-becas',
  ].includes(value)
    ? value as PreinscriptionStage
    : 'registro'
}

function enrollmentMode(value: string | null): AcademicEnrollmentMode {
  return ['individual', 'masiva', 'prerrequisitos'].includes(value || '')
    ? value as AcademicEnrollmentMode
    : 'individual'
}

function moodleSection(value: string | null): MoodleSection {
  return ['alerts', 'status', 'users', 'courses', 'resources', 'evaluation-dates', 'grades'].includes(value || '')
    ? value as MoodleSection
    : 'status'
}

function requestedPermissionFromUrl(
  url: URL,
  permissions: readonly ScreenPermissionCode[],
): ScreenPermissionCode | null {
  const requestedPage = url.searchParams.get('open_page') as Page | null
  if (!requestedPage) return null

  let requestedPermission: ScreenPermissionCode = requestedPage
  if (requestedPage === 'preinscripcion') {
    requestedPermission = `${requestedPage}/${preinscriptionStage(url.searchParams.get('preinscripcion_stage'))}`
  } else if (requestedPage === 'matricula-acad') {
    requestedPermission = `${requestedPage}/${enrollmentMode(url.searchParams.get('matricula_mode'))}`
  } else if (requestedPage === 'moodle') {
    requestedPermission = `${requestedPage}/${moodleSection(url.searchParams.get('moodle_section'))}`
  } else if (requestedPage === 'gestion-sisacademico') {
    const section = url.searchParams.get('sis_section') || ''
    if (section === 'correos') {
      return screenPermissionAllowsCode(permissions, 'actualizar-correo-intec')
        ? 'actualizar-correo-intec'
        : firstPermissionForPage(permissions, 'actualizar-correo-intec')
    }
    requestedPermission = section ? `${requestedPage}/${section}` : requestedPage
  } else if (requestedPage === 'reporteria-integral' || requestedPage === 'reportes-individuales') {
    const report = url.searchParams.get('report_key') || ''
    requestedPermission = report ? `${requestedPage}/${report}` : requestedPage
  } else if (requestedPage === 'titulos-registrados') {
    const requestedType = url.searchParams.get('title_type') || 'senescyt'
    requestedPermission = `${requestedPage}/${requestedType === 'intec' ? 'institucional' : requestedType}`
  }

  return screenPermissionAllowsCode(permissions, requestedPermission)
    ? requestedPermission
    : firstPermissionForPage(permissions, requestedPage)
}

export function useReporteriaApp() {
  const [bootstrapping, setBootstrapping] = useState(true)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState<UserSession | null>(null)
  const [screenAccessPages, setScreenAccessPages] = useState<ScreenPermissionCode[] | null>(null)
  const [screenAccessLoading, setScreenAccessLoading] = useState(false)
  const [screenAccessError, setScreenAccessError] = useState('')
  const [screenAccessRevision, setScreenAccessRevision] = useState(0)
  const [profileSelectionPending, setProfileSelectionPending] = useState(false)
  const [profileSelectionLoading, setProfileSelectionLoading] = useState(false)
  const [profileSelectionError, setProfileSelectionError] = useState('')
  const [activePage, setActivePage] = useState<Page>(() => readStoredPage())
  const [matriculaAcadMode, setMatriculaAcadMode] = useState<AcademicEnrollmentMode>('individual')
  const [sisAcademicoSectionKey, setSisAcademicoSectionKey] = useState('')
  const [legacyReportKey, setLegacyReportKey] = useState('')
  const [portalStudentSection, setPortalStudentSection] = useState<PortalStudentSection>('dashboard')
  const [preinscriptionActiveStage, setPreinscriptionActiveStage] = useState<PreinscriptionStage>('registro')
  const [activeMoodleSection, setActiveMoodleSection] = useState<MoodleSection>('status')
  const [practicasProcess, setPracticasProcess] = useState<PracticasProcessCode>('PPF')
  const [practicasNavigationKey, setPracticasNavigationKey] = useState(0)
  const [titulosRegistradosTipo, setTitulosRegistradosTipo] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [dashboardMatriculaLoading, setDashboardMatriculaLoading] = useState(false)
  const [catalogMessage, setCatalogMessage] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [dashboardMatriculaError, setDashboardMatriculaError] = useState('')
  const [dashboardMatricula, setDashboardMatricula] = useState<DashboardMatriculaResponse | null>(null)
  const [matriculaSummaryLoading, setMatriculaSummaryLoading] = useState(false)
  const [matriculaPeriodSummaryLoading, setMatriculaPeriodSummaryLoading] = useState(false)
  const [matriculaMovementSummaryLoading, setMatriculaMovementSummaryLoading] = useState(false)
  const [matriculaCareerStateLoading, setMatriculaCareerStateLoading] = useState(false)
  const [matriculaListLoading, setMatriculaListLoading] = useState(false)
  const [matriculaSummaryError, setMatriculaSummaryError] = useState('')
  const [matriculaPeriodSummaryError, setMatriculaPeriodSummaryError] = useState('')
  const [matriculaMovementSummaryError, setMatriculaMovementSummaryError] = useState('')
  const [matriculaCareerStateError, setMatriculaCareerStateError] = useState('')
  const [matriculaListError, setMatriculaListError] = useState('')
  const [matriculaSummary, setMatriculaSummary] = useState<MatriculaSummaryItem[]>([])
  const [matriculaSummaryUpdatedAt, setMatriculaSummaryUpdatedAt] = useState('')
  const [matriculaPeriodSummary, setMatriculaPeriodSummary] = useState<MatriculaPeriodSummaryItem[]>([])
  const [matriculaYearSummary, setMatriculaYearSummary] = useState<MatriculaYearSummaryItem[]>([])
  const [matriculaMovementSummary, setMatriculaMovementSummary] = useState<MatriculaPeriodSummaryItem[]>([])
  const [matriculaMovementYearSummary, setMatriculaMovementYearSummary] = useState<MatriculaYearSummaryItem[]>([])
  const [matriculaCareerStateReport, setMatriculaCareerStateReport] = useState<MatriculaCareerStateSummaryResponse | null>(null)
  const [matriculaTotalsByEstado, setMatriculaTotalsByEstado] = useState<Record<string, number>>({})
  const [matriculaStudents, setMatriculaStudents] = useState<MatriculaStudentItem[]>([])
  const [matriculaTipo, setMatriculaTipo] = useState<MatriculaTipo>('R')
  const [matriculaEstado, setMatriculaEstado] = useState('')
  const [ingresoVentasLoading, setIngresoVentasLoading] = useState(false)
  const [ingresoVentasError, setIngresoVentasError] = useState('')
  const [ingresoVentas, setIngresoVentas] = useState<IngresoVentasResponse | null>(null)
  const [cruceDatosLoading, setCruceDatosLoading] = useState(false)
  const [cruceDatosDownloadLoading, setCruceDatosDownloadLoading] = useState(false)
  const [cruceDatosError, setCruceDatosError] = useState('')
  const [cruceDatos, setCruceDatos] = useState<ExcelSqlCrossResponse | null>(null)
  const [createLoading, setCreateLoading] = useState(false)
  const [createMessage, setCreateMessage] = useState('')
  const [createError, setCreateError] = useState('')
  const [catalogTeams, setCatalogTeams] = useState<GraphTeam[]>([])
  const [createDisplayName, setCreateDisplayName] = useState('')
  const [createCourses, setCreateCourses] = useState('')
  const [createTeachers, setCreateTeachers] = useState('')
  const [createVisibility, setCreateVisibility] = useState('educationClass')
  const [teamsUserId, setTeamsUserId] = useState('')
  const [teamsTeamId, setTeamsTeamId] = useState('')
  const [enrollLoading, setEnrollLoading] = useState(false)
  const [selectedTeamIndex, setSelectedTeamIndex] = useState<number | null>(null)

  const applyScreenPermission = useCallback((permission: ScreenPermissionCode) => {
    const [root, child = ''] = permission.split('/', 2)
    const page = root as Page

    setSisAcademicoSectionKey(page === 'gestion-sisacademico' ? child : '')
    setLegacyReportKey(
      page === 'reporteria-integral' || page === 'reportes-individuales' ? child : '',
    )
    if (page === 'preinscripcion' && child) {
      setPreinscriptionActiveStage(preinscriptionStage(child))
    }
    if (page === 'matricula-acad' && child) {
      setMatriculaAcadMode(enrollmentMode(child))
    }
    if (page === 'moodle') {
      setActiveMoodleSection(moodleSection(child))
    }
    if (page === 'titulos-registrados' && child) {
      setTitulosRegistradosTipo(child === 'institucional' ? 'intec' : child)
    }
    const studentSection = studentSectionForPage(page)
    if (studentSection) setPortalStudentSection(studentSection)
    setActivePage(page)
  }, [])

  const activateAssignedScreen = useCallback((permission: ScreenPermissionCode) => {
    if (screenAccessPages === null) return false
    const root = permissionRootPage(permission)
    const resolvedPermission = screenPermissionAllowsCode(screenAccessPages, permission)
      ? permission
      : permission.includes('/')
        ? null
        : firstPermissionForPage(screenAccessPages, root)
    if (!resolvedPermission) {
      setScreenAccessError('La pantalla solicitada no está asignada al perfil autenticado.')
      return false
    }
    setScreenAccessError('')
    applyScreenPermission(resolvedPermission)
    return true
  }, [applyScreenPermission, screenAccessPages])

  const resetWorkspace = useCallback(() => {
    setActivePage('dashboard')
    setMatriculaAcadMode('individual')
    setSisAcademicoSectionKey('')
    setLegacyReportKey('')
    setPortalStudentSection('dashboard')
    setPreinscriptionActiveStage('registro')
    setActiveMoodleSection('status')
    setTitulosRegistradosTipo('')
    setCatalogLoading(false)
    setDashboardMatriculaLoading(false)
    setCatalogMessage('')
    setCatalogError('')
    setDashboardMatriculaError('')
    setDashboardMatricula(null)
    setMatriculaSummaryLoading(false)
    setMatriculaPeriodSummaryLoading(false)
    setMatriculaMovementSummaryLoading(false)
    setMatriculaCareerStateLoading(false)
    setMatriculaListLoading(false)
    setMatriculaSummaryError('')
    setMatriculaPeriodSummaryError('')
    setMatriculaMovementSummaryError('')
    setMatriculaCareerStateError('')
    setMatriculaListError('')
    setMatriculaSummary([])
    setMatriculaPeriodSummary([])
    setMatriculaYearSummary([])
    setMatriculaMovementSummary([])
    setMatriculaMovementYearSummary([])
    setMatriculaCareerStateReport(null)
    setMatriculaTotalsByEstado({})
    setMatriculaStudents([])
    setMatriculaTipo('R')
    setMatriculaEstado('')
    setIngresoVentasLoading(false)
    setIngresoVentasError('')
    setIngresoVentas(null)
    setCruceDatosLoading(false)
    setCruceDatosDownloadLoading(false)
    setCruceDatosError('')
    setCruceDatos(null)
    setCatalogTeams([])
    setCreateLoading(false)
    setCreateMessage('')
    setCreateError('')
    setCreateDisplayName('')
    setCreateCourses('')
    setCreateTeachers('')
    setCreateVisibility('educationClass')
    setTeamsUserId('')
    setTeamsTeamId('')
    setSelectedTeamIndex(null)
    setProfileSelectionPending(false)
    setProfileSelectionLoading(false)
    setProfileSelectionError('')
    clearStoredPage()
  }, [])

  const resetAfterLogout = useCallback(
    (logoutMessage: string = '') => {
      setSession(null)
      setPassword('')
      setShowPassword(false)
      setError(logoutMessage)
      resetWorkspace()
    },
    [resetWorkspace]
  )

  const handleApiError = useCallback(
    (apiError: unknown, fallbackMessage: string, options: ApiErrorOptions = {}) => {
      if (apiError instanceof ApiError && apiError.status === 401) {
        if (options.expireOnUnauthorized === false) {
          return apiError.message || 'Credenciales inválidas. Verifique el usuario y la contraseña.'
        }

        resetAfterLogout('Sesión expirada. Vuelva a iniciar sesión.')
        return 'Sesión expirada. Vuelva a iniciar sesión.'
      }

      return apiError instanceof Error ? apiError.message : fallbackMessage
    },
    [resetAfterLogout]
  )

  const performLogout = useCallback(
    async (logoutMessage: string = '') => {
      try {
        await logoutRequest()
      } catch (apiError) {
        if (!(apiError instanceof ApiError && apiError.status === 401)) {
          setError(handleApiError(apiError, 'No se pudo cerrar la sesión actual.'))
        }
      } finally {
        resetAfterLogout(logoutMessage)
      }
    },
    [handleApiError, resetAfterLogout]
  )

  useEffect(() => {
    let cancelled = false

    const bootstrapSession = async () => {
      setBootstrapping(true)
      try {
        const currentSession = await getCurrentSession()
        if (cancelled) return

        setSession(currentSession)
        if (currentSession) {
          const isStudentSession = normalizedRoleKey(currentSession.rol) === 'ESTUDIANTE'
          setActivePage((currentPage) => {
            if (isStudentSession) return defaultPageForRole(currentSession.rol)
            return pageAllowedForRole(currentSession.rol, currentPage)
              ? currentPage
              : defaultPageForRole(currentSession.rol)
          })
          if (isStudentSession) setPortalStudentSection('dashboard')
        }
        if (!currentSession) {
          resetWorkspace()
        }
      } catch (apiError) {
        if (cancelled) return
        setError(handleApiError(apiError, 'No se pudo validar la sesión actual.'))
      } finally {
        if (!cancelled) {
          setBootstrapping(false)
        }
      }
    }

    void bootstrapSession()

    return () => {
      cancelled = true
    }
  }, [handleApiError, resetWorkspace])

  useEffect(() => {
    if (!session) {
      setScreenAccessPages(null)
      setScreenAccessLoading(false)
      setScreenAccessError('')
      return
    }

    let cancelled = false
    const syncAccess = async (initialLoad = false, refresh = false) => {
      if (initialLoad) {
        setScreenAccessPages(null)
        setScreenAccessLoading(true)
        setScreenAccessError('')
      }
      try {
        const response = await fetchScreenAccessAssignments(false, { refresh })
        if (cancelled) return
        const roleAccess = response.roles.find((item) => item.value === normalizedRoleKey(session.rol))
        if (!roleAccess) {
          throw new Error('El perfil autenticado no tiene una matriz de pantallas registrada.')
        }
        setScreenAccessPages(roleAccess.pages)
        setScreenAccessError('')
      } catch (apiError) {
        if (!cancelled) {
          setScreenAccessPages((current) => current ?? [])
          setScreenAccessError(
            apiError instanceof ApiError
              ? apiError.message
              : apiError instanceof Error
                ? apiError.message
                : 'No se pudo cargar la navegación asignada al tipo de usuario.',
          )
        }
      } finally {
        if (!cancelled && initialLoad) setScreenAccessLoading(false)
      }
    }

    const handleAccessUpdate = () => void syncAccess(false, true)
    const handleStorageUpdate = (event: StorageEvent) => {
      if (event.key === SCREEN_ACCESS_SYNC_KEY) void syncAccess(false, true)
    }
    const handleWindowFocus = () => void syncAccess(false, true)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') void syncAccess(false, true)
    }
    void syncAccess(true, true)
    const refreshInterval = window.setInterval(() => void syncAccess(false, true), 60_000)
    window.addEventListener('intec-screen-access-updated', handleAccessUpdate)
    window.addEventListener('storage', handleStorageUpdate)
    window.addEventListener('focus', handleWindowFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      cancelled = true
      window.clearInterval(refreshInterval)
      window.removeEventListener('intec-screen-access-updated', handleAccessUpdate)
      window.removeEventListener('storage', handleStorageUpdate)
      window.removeEventListener('focus', handleWindowFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [screenAccessRevision, session])

  useEffect(() => {
    if (!session || screenAccessPages === null) return
    const url = new URL(globalThis.location.href)
    const requestedPermission = requestedPermissionFromUrl(url, screenAccessPages)
    if (url.searchParams.has('open_page')) {
      for (const parameter of [
        'open_page', 'sis_section', 'preinscripcion_stage', 'matricula_mode',
        'moodle_section', 'report_key', 'title_type',
      ]) {
        url.searchParams.delete(parameter)
      }
      globalThis.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
    }

    const currentPermission = screenPermissionForView(activePage, {
      matriculaAcadMode,
      moodleSection: activeMoodleSection,
      preinscriptionStage: preinscriptionActiveStage,
      sisAcademicoSection: sisAcademicoSectionKey,
      reportKey: legacyReportKey,
      registeredTitleType: titulosRegistradosTipo,
    })
    if (requestedPermission) {
      if (requestedPermission !== currentPermission) applyScreenPermission(requestedPermission)
      return
    }
    if (screenPermissionAllowsCode(screenAccessPages, currentPermission)) return

    const preferredRoot = defaultPageForRole(session.rol, screenAccessPages)
    const fallbackPermission = firstPermissionForPage(screenAccessPages, preferredRoot) || screenAccessPages[0]
    if (fallbackPermission) {
      applyScreenPermission(fallbackPermission)
    } else {
      setScreenAccessError('El perfil autenticado no tiene pantallas asignadas.')
    }
  }, [
    activePage,
    activeMoodleSection,
    applyScreenPermission,
    legacyReportKey,
    matriculaAcadMode,
    preinscriptionActiveStage,
    screenAccessPages,
    session,
    sisAcademicoSectionKey,
    titulosRegistradosTipo,
  ])

  useEffect(() => {
    const section = studentSectionForPage(activePage)
    if (section) setPortalStudentSection(section)
  }, [activePage])

  useEffect(() => {
    if (session) {
      writeStoredPage(activePage)
    } else {
      clearStoredPage()
    }
  }, [activePage, session])

  useInactivityLogout(Boolean(session), INACTIVITY_TIMEOUT_MS, () => {
    void performLogout('Sesión cerrada por inactividad. Vuelva a iniciar sesión.')
  })

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()

    const normalizedLogin = login.trim()
    if (!normalizedLogin || !password) {
      setError('Ingrese su usuario o correo y contraseña.')
      return
    }

    setError('')
    setLoading(true)

    try {
      const authenticatedSession = await loginRequest(normalizedLogin, password)
      setSession(authenticatedSession)
      setProfileSelectionPending(true)
      setProfileSelectionError('')
      setPassword('')
      setSisAcademicoSectionKey('')
      setLegacyReportKey('')
      setPreinscriptionActiveStage('registro')
      setActivePage(defaultPageForRole(authenticatedSession.rol))
    } catch (apiError) {
      setError(handleApiError(apiError, 'Error inesperado en el login', { expireOnUnauthorized: false }))
    } finally {
      setLoading(false)
    }
  }

  const selectAccessProfile = async (role: string) => {
    setProfileSelectionLoading(true)
    setProfileSelectionError('')
    try {
      const selectedSession = await selectProfileRequest(role)
      setScreenAccessPages(null)
      setScreenAccessError('')
      setSession(selectedSession)
      setActivePage(defaultPageForRole(selectedSession.rol))
      setSisAcademicoSectionKey('')
      setLegacyReportKey('')
      setPortalStudentSection('dashboard')
      setProfileSelectionPending(false)
    } catch (apiError) {
      setProfileSelectionError(handleApiError(apiError, 'No se pudo abrir el perfil seleccionado'))
    } finally {
      setProfileSelectionLoading(false)
    }
  }

  const loadMatriculaListWithFilters = useCallback(
    async (tipo: MatriculaTipo, estado: string, limit: number = 500) => {
      setMatriculaListError('')
      setMatriculaListLoading(true)

      try {
        const payload = await fetchMatriculaList(tipo, estado, limit, null, undefined, 'CNE')
        setMatriculaStudents(payload.items || [])
      } catch (apiError) {
        setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando listado'))
        setMatriculaStudents([])
      } finally {
        setMatriculaListLoading(false)
      }
    },
    [handleApiError]
  )

  const loadDashboardMatricula = useCallback(async () => {
    setDashboardMatriculaError('')
    setDashboardMatriculaLoading(true)

    try {
      const payload = await fetchDashboardMatricula()
      setDashboardMatricula(payload)
    } catch (apiError) {
      setDashboardMatriculaError(handleApiError(apiError, 'Error inesperado consultando dashboard'))
      setDashboardMatricula(null)
    } finally {
      setDashboardMatriculaLoading(false)
    }
  }, [handleApiError])

  const loadAcademicMatriculaSummary = useCallback(async () => {
    setMatriculaSummaryError('')
    setMatriculaPeriodSummaryError('')
    setMatriculaSummaryLoading(true)
    setMatriculaPeriodSummaryLoading(true)

    try {
      const summaryPayload = await fetchMatriculaSummary()
      setMatriculaSummary(summaryPayload.items || [])
      setMatriculaTotalsByEstado(summaryPayload.totals_by_estado || {})
      setMatriculaSummaryUpdatedAt(summaryPayload.consultado_en || new Date().toISOString())
    } catch (apiError) {
      setMatriculaSummaryError(handleApiError(apiError, 'Error inesperado consultando resumen'))
      setMatriculaSummary([])
      setMatriculaTotalsByEstado({})
      setMatriculaStudents([])
    } finally {
      setMatriculaSummaryLoading(false)
    }

    try {
      const academicPeriodPayload = await fetchMatriculaPeriodSummary()
      setMatriculaPeriodSummary(academicPeriodPayload.items || [])
      setMatriculaYearSummary(academicPeriodPayload.years || [])
      setMatriculaEstado('')
      setMatriculaStudents([])
    } catch (apiError) {
      setMatriculaPeriodSummaryError(handleApiError(apiError, 'Error inesperado al consultar el resumen por período.'))
      setMatriculaPeriodSummary([])
      setMatriculaYearSummary([])
    } finally {
      setMatriculaPeriodSummaryLoading(false)
    }
  }, [handleApiError])

  const refreshMatriculaCneSummary = useCallback(async () => {
    try {
      const summaryPayload = await fetchMatriculaSummary()
      setMatriculaSummary(summaryPayload.items || [])
      setMatriculaTotalsByEstado(summaryPayload.totals_by_estado || {})
      setMatriculaSummaryUpdatedAt(summaryPayload.consultado_en || new Date().toISOString())
      setMatriculaSummaryError('')
    } catch (apiError) {
      setMatriculaSummaryError(handleApiError(apiError, 'No se pudo actualizar el resumen CNE'))
    }
  }, [handleApiError])

  const loadMovementMatriculaSummary = useCallback(async () => {
    setMatriculaMovementSummaryError('')
    setMatriculaMovementSummaryLoading(true)

    try {
      const movementPayload = await fetchMatriculaMovementSummary()
      setMatriculaMovementSummary(movementPayload.items || [])
      setMatriculaMovementYearSummary(movementPayload.years || [])
    } catch (apiError) {
      setMatriculaMovementSummaryError(handleApiError(apiError, 'Error inesperado al consultar el movimiento de matrícula.'))
      setMatriculaMovementSummary([])
      setMatriculaMovementYearSummary([])
    } finally {
      setMatriculaMovementSummaryLoading(false)
    }
  }, [handleApiError])

  const loadMatriculaCareerStateReport = useCallback(async () => {
    setMatriculaCareerStateError('')
    setMatriculaCareerStateLoading(true)

    try {
      const payload = await fetchMatriculaCareerStateSummary()
      setMatriculaCareerStateReport(payload)
    } catch (apiError) {
      setMatriculaCareerStateError(handleApiError(apiError, 'Error inesperado consultando reporteria por carrera'))
      setMatriculaCareerStateReport(null)
    } finally {
      setMatriculaCareerStateLoading(false)
    }
  }, [handleApiError])

  const selectMatriculaTipo = async (tipo: MatriculaTipo) => {
    setMatriculaTipo(tipo)
    setMatriculaEstado('')
    setMatriculaStudents([])
  }

  const selectMatriculaEstado = async (estado: string) => {
    setMatriculaEstado(estado)
    await loadMatriculaListWithFilters(matriculaTipo, estado)
  }

  const selectMatriculaEstadoGlobal = async (estado: string) => {
    setMatriculaEstado(estado)
    setMatriculaListError('')
    setMatriculaListLoading(true)

    try {
      const payload = await fetchMatriculaList('ALL', estado, 2000, null, undefined, 'CNE')
      setMatriculaStudents(payload.items || [])
    } catch (apiError) {
      setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando listado global'))
      setMatriculaStudents([])
    } finally {
      setMatriculaListLoading(false)
    }
  }

  const selectMatriculaEstadoRh = async (estado: string) => {
    setMatriculaEstado(estado)
    setMatriculaListError('')
    setMatriculaListLoading(true)

    try {
      const payload = await fetchMatriculaList('RH', estado, 2000, null, undefined, 'CNE')
      setMatriculaStudents(payload.items || [])
    } catch (apiError) {
      setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando listado R + H'))
      setMatriculaStudents([])
    } finally {
      setMatriculaListLoading(false)
    }
  }

  const selectMatriculaTotalRh = async () => {
    setMatriculaEstado('')
    setMatriculaListError('')
    setMatriculaListLoading(true)

    try {
      const payload = await fetchMatriculaList('ALL', '', 10000, null, undefined, 'CNE')
      setMatriculaStudents(payload.items || [])
    } catch (apiError) {
      setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando reporte unificado'))
      setMatriculaStudents([])
    } finally {
      setMatriculaListLoading(false)
    }
  }

  const selectPeriodoAcademicoYear = async (anio: number | null) => {
    setMatriculaEstado('')
    setMatriculaListError('')
    setMatriculaListLoading(true)

    try {
      const payload = await fetchMatriculaList('ALL', '', 10000, anio, 'PRIMERA')
      setMatriculaStudents(payload.items || [])
    } catch (apiError) {
      setMatriculaListError(handleApiError(apiError, 'Error inesperado al consultar estudiantes por período académico.'))
      setMatriculaStudents([])
    } finally {
      setMatriculaListLoading(false)
    }
  }

  const selectPeriodoMatriculadosYear = async (anio: number | null) => {
    setMatriculaEstado('')
    setMatriculaListError('')
    setMatriculaListLoading(true)

    try {
      const payload = await fetchMatriculaList('ALL', '', 10000, anio, 'PRIMERA')
      setMatriculaStudents(payload.items || [])
    } catch (apiError) {
      setMatriculaListError(handleApiError(apiError, 'Error inesperado al consultar estudiantes matriculados por período.'))
      setMatriculaStudents([])
    } finally {
      setMatriculaListLoading(false)
    }
  }

  const loadCruceDatos = useCallback(async () => {
    setCruceDatosError('')
    setCruceDatosLoading(true)

    try {
      const payload = await fetchExcelSqlCross()
      setCruceDatos(payload)
    } catch (apiError) {
      setCruceDatosError(handleApiError(apiError, 'Error inesperado procesando cruce de datos'))
      setCruceDatos(null)
    } finally {
      setCruceDatosLoading(false)
    }
  }, [handleApiError])

  const loadIngresoVentas = useCallback(async () => {
    setIngresoVentasError('')
    setIngresoVentasLoading(true)

    try {
      const payload = await fetchIngresoVentas()
      setIngresoVentas(payload)
    } catch (apiError) {
      setIngresoVentasError(handleApiError(apiError, 'Error inesperado consultando ingreso por ventas'))
      setIngresoVentas(null)
    } finally {
      setIngresoVentasLoading(false)
    }
  }, [handleApiError])

  const downloadCruceDatosExcel = useCallback(async () => {
    setCruceDatosError('')
    setCruceDatosDownloadLoading(true)

    try {
      const blob = await downloadExcelSqlCrossWorkbook()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `cruce-datos-${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.append(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (apiError) {
      setCruceDatosError(handleApiError(apiError, 'Error inesperado descargando Excel del cruce'))
    } finally {
      setCruceDatosDownloadLoading(false)
    }
  }, [handleApiError])

  useEffect(() => {
    if (!session || activePage !== 'dashboard') return

    const refreshDashboard = () => {
      if (!dashboardMatriculaLoading) {
        void loadDashboardMatricula()
      }
    }

    refreshDashboard()
    const intervalId = window.setInterval(refreshDashboard, 30000)
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshDashboard()
      }
    }
    window.addEventListener('focus', refreshDashboard)
    document.addEventListener('visibilitychange', refreshOnVisible)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshDashboard)
      document.removeEventListener('visibilitychange', refreshOnVisible)
    }
  }, [activePage, dashboardMatriculaLoading, loadDashboardMatricula, session])

  useEffect(() => {
    if (!session || activePage !== 'matricula') return

    const refreshSummary = () => {
      void refreshMatriculaCneSummary()
    }
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') refreshSummary()
    }

    refreshSummary()
    const intervalId = window.setInterval(refreshSummary, 30000)
    window.addEventListener('focus', refreshSummary)
    document.addEventListener('visibilitychange', refreshOnVisible)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshSummary)
      document.removeEventListener('visibilitychange', refreshOnVisible)
    }
  }, [activePage, refreshMatriculaCneSummary, session])

  useEffect(() => {
    if (session && activePage === 'cruce-datos' && !cruceDatos && !cruceDatosLoading) {
      void loadCruceDatos()
    }
  }, [activePage, cruceDatos, cruceDatosLoading, loadCruceDatos, session])

  useEffect(() => {
    if (session && activePage === 'ingreso-ventas' && !ingresoVentas && !ingresoVentasLoading) {
      void loadIngresoVentas()
    }
  }, [activePage, ingresoVentas, ingresoVentasLoading, loadIngresoVentas, session])

  useEffect(() => {
    if (!session || activePage !== 'reporteria-carreras') return

    const refreshReport = () => {
      void loadMatriculaCareerStateReport()
    }
    const refreshOnVisible = () => {
      if (document.visibilityState === 'visible') refreshReport()
    }

    refreshReport()
    const intervalId = window.setInterval(refreshReport, 30000)
    window.addEventListener('focus', refreshReport)
    document.addEventListener('visibilitychange', refreshOnVisible)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshReport)
      document.removeEventListener('visibilitychange', refreshOnVisible)
    }
  }, [activePage, loadMatriculaCareerStateReport, session])

  const loadCatalog = async () => {
    setCatalogError('')
    setCatalogMessage('')
    setCatalogLoading(true)

    try {
      const payload = await fetchTeamsCatalog()
      const teams = payload.value || []
      setCatalogTeams(teams)
      setSelectedTeamIndex(teams.length > 0 ? 0 : null)
      setTeamsTeamId(teams[0]?.id || '')
      setCatalogMessage('Catálogo de aulas obtenido correctamente.')
    } catch (apiError) {
      setCatalogError(handleApiError(apiError, 'Error inesperado consultando Teams'))
      setCatalogTeams([])
    } finally {
      setCatalogLoading(false)
    }
  }

  const enrollInTeam = async () => {
    const userId = teamsUserId.trim()
    const teamId = teamsTeamId.trim()

    if (!userId || !teamId) {
      setCatalogError('Para matricular debes indicar user_id y team_id.')
      return
    }

    setCatalogError('')
    setCatalogMessage('')
    setEnrollLoading(true)

    try {
      const payload = await enrollUserInTeam(userId, teamId)
      setCatalogMessage(payload.message || 'Matriculacion realizada correctamente.')
    } catch (apiError) {
      setCatalogError(handleApiError(apiError, 'Error inesperado en matriculacion'))
    } finally {
      setEnrollLoading(false)
    }
  }

  const createAndEnroll = async (options?: Partial<TeamCreateAndEnrollPayload>) => {
    const displayName = createDisplayName.trim()
    const courses = splitCsv(createCourses)
    const teacherUserIds = splitCsv(createTeachers)

    if (!displayName || courses.length === 0 || teacherUserIds.length === 0) {
      setCreateError('Debes indicar nombre del aula, cursos y docentes para crear el aula.')
      return
    }

    setCreateError('')
    setCreateMessage('')
    setCreateLoading(true)

    try {
      const payload = await createClassroom({
        display_name: displayName,
        courses,
        teacher_user_ids: teacherUserIds,
        visibility: 'educationClass',
        ...options,
      })
      setCreateMessage(payload.message || 'Aula tipo clase creada correctamente y lista para usar.')
      setTeamsTeamId(payload.team_id || '')
    } catch (apiError) {
      setCreateError(handleApiError(apiError, 'Error inesperado creando el aula'))
    } finally {
      setCreateLoading(false)
    }
  }

  const openDashboard = () => {
    if (!activateAssignedScreen('dashboard')) return
    if (!dashboardMatricula && !dashboardMatriculaLoading) {
      void loadDashboardMatricula()
    }
  }
  const openPortalEstudiantePage = (section: PortalStudentSection = 'dashboard') => {
    activateAssignedScreen(STUDENT_PORTAL_PAGE_BY_SECTION[section])
  }
  const openPortalDocentePage = () => {
    activateAssignedScreen('portal-docente')
  }
  const openPortalDocenteInformePage = () => {
    activateAssignedScreen('portal-docente-informe')
  }
  const openInglesPage = () => {
    activateAssignedScreen('ingles')
  }
  const openExpedientesDocumentalesPage = () => {
    activateAssignedScreen('expedientes-documentales')
  }
  const openSistemaAcademicoPage = () => {
    if (!activateAssignedScreen('sistema-academico')) return
    if (!dashboardMatricula && !dashboardMatriculaLoading) {
      void loadDashboardMatricula()
    }
  }
  const openPortalDocentePlanificacionPage = () => {
    activateAssignedScreen('portal-docente-planificacion')
  }
  const openPortalDocenteContratosPage = () => {
    activateAssignedScreen('portal-docente-contratos')
  }
  const openTeacherEvaluationPage = () => {
    activateAssignedScreen('evaluacion-docente')
  }
  const openTeacherEvaluationAdminPage = () => {
    activateAssignedScreen('evaluacion-docente-admin')
  }
  const openTeacherEvaluationProgressPage = () => {
    activateAssignedScreen('evaluacion-docente-avance')
  }
  const openTeacherEvaluationReportsPage = () => {
    activateAssignedScreen('evaluacion-docente-reportes')
  }
  const openTeacherComplianceFormatPage = () => {
    activateAssignedScreen('formato-informe-docente')
  }
  const openTeamsPage = () => activateAssignedScreen('teams')
  const openHistoricoIntegracionesPage = () => activateAssignedScreen('historico-integraciones')
  const openInformeCumplimientoPage = () => activateAssignedScreen('informe-cumplimiento')
  const openMoodlePage = (section: MoodleSection = 'status') => {
    const permission = `moodle/${section}` as ScreenPermissionCode
    if (normalizedRoleKey(session?.rol) === 'ADMINISTRADOR') {
      setScreenAccessError('')
      applyScreenPermission(permission)
      return
    }
    activateAssignedScreen(permission)
  }
  const openTeamsMatriculaPage = () => {
    if (!activateAssignedScreen('teams-matricula')) return
    if (catalogTeams.length === 0 && !catalogLoading) {
      void loadCatalog()
    }
  }
  const openMoodleTeamsPage = () => activateAssignedScreen('moodle-teams')
  const openMatriculaPage = async () => {
    if (!activateAssignedScreen('matricula')) return
    await loadAcademicMatriculaSummary()
  }
  const openMatriculaAcadPage = (mode: AcademicEnrollmentMode = 'individual') => {
    activateAssignedScreen(`matricula-acad/${mode}`)
  }
  const openMatriculaDocentePage = () => {
    activateAssignedScreen('matricula-docente')
  }
  const openCareerChangeRequestsPage = () => {
    activateAssignedScreen('solicitudes-cambio-carrera')
  }
  const openModalityChangeRequestsPage = () => {
    activateAssignedScreen('solicitudes-cambio-modalidad')
  }
  const openEstadoDocentePage = () => {
    activateAssignedScreen('estado-docente')
  }
  const openSenescytEstudiantesPage = () => {
    activateAssignedScreen('senescyt-estudiantes')
  }
  const openActualizarDatosEstudiantePage = () => {
    activateAssignedScreen('actualizar-datos-estudiante')
  }
  const openActualizarCorreoIntecPage = () => {
    activateAssignedScreen('actualizar-correo-intec')
  }
  const openPreinscripcionPage = () => {
    activateAssignedScreen('preinscripcion/registro')
  }
  const openPreinscripcionStage = (stage: PreinscriptionStage = 'registro') => {
    activateAssignedScreen(`preinscripcion/${stage}`)
  }
  const openReporteriaCarrerasPage = async () => {
    if (!activateAssignedScreen('reporteria-carreras')) return
    await loadMatriculaCareerStateReport()
  }
  const openReporteriaIntegralPage = (reportKey?: string) => {
    activateAssignedScreen(reportKey ? `reporteria-integral/${reportKey}` : 'reporteria-integral')
  }
  const openReportesIndividualesPage = (reportKey?: string) => {
    activateAssignedScreen(reportKey ? `reportes-individuales/${reportKey}` : 'reportes-individuales')
  }
  const openAdminNotasAsignaturaPage = () => {
    activateAssignedScreen('admin-notas-asignatura')
  }
  const openGestionSisAcademicoPage = (sectionKey?: string) => {
    if (sectionKey === 'correos') {
      activateAssignedScreen('actualizar-correo-intec')
      return
    }
    activateAssignedScreen(sectionKey ? `gestion-sisacademico/${sectionKey}` : 'gestion-sisacademico')
  }
  const openAsignacionPantallasPage = () => {
    activateAssignedScreen('asignacion-pantallas')
  }
  const openPeriodoAcademicoPage = async () => {
    if (!activateAssignedScreen('periodo-academico')) return
    await loadAcademicMatriculaSummary()
  }
  const openPeriodoMatriculadosPage = async () => {
    if (!activateAssignedScreen('periodo-matriculados')) return
    await loadMovementMatriculaSummary()
  }
  const openIngresoVentasPage = async () => {
    if (!activateAssignedScreen('ingreso-ventas')) return
    if (!ingresoVentas && !ingresoVentasLoading) {
      await loadIngresoVentas()
    }
  }
  const openCruceDatosPage = async () => {
    if (!activateAssignedScreen('cruce-datos')) return
    if (!cruceDatos && !cruceDatosLoading) {
      await loadCruceDatos()
    }
  }
  const openValidarExcelPage = () => {
    activateAssignedScreen('validar-excel')
  }
  const openRangoEdadesPage = () => {
    activateAssignedScreen('rango-edades')
  }
  const openFechaGradoPage = () => {
    activateAssignedScreen('fecha-grado')
  }
  const openTitulosRegistradosPage = (tipo = '') => {
    const titleType = tipo === 'intec' ? 'institucional' : tipo || 'senescyt'
    activateAssignedScreen(`titulos-registrados/${titleType}`)
  }
  const openTitulacionPage = () => {
    activateAssignedScreen('titulacion')
  }

  const openTitulacionProcesoPage = () => {
    activateAssignedScreen('titulacion-proceso')
  }
  const openTitulacionResponsablesPage = () => {
    activateAssignedScreen('titulacion-responsables')
  }
  const openCertificadosPage = () => {
    activateAssignedScreen('certificados')
  }
  const openMatriculaExcelCertificadosPage = () => {
    activateAssignedScreen('matricula-excel-certificados')
  }
  const openCertificateRenamerPage = () => {
    activateAssignedScreen('renombrar-certificados')
  }
  const openCredentialGeneratorPage = () => {
    activateAssignedScreen('credenciales')
  }
  const openMassEmailPage = () => {
    activateAssignedScreen('correos-masivos')
  }
  const openCarnetInstitucionalPage = () => {
    activateAssignedScreen('carnet-institucional')
  }
  const openPracticasInstitucionalesPage = (process: PracticasProcessCode = 'PPF') => {
    setPracticasProcess(process)
    setPracticasNavigationKey((current) => current + 1)
    activateAssignedScreen('practicas-institucionales')
  }

  const displayName = session?.nombres?.trim() || session?.login || ''
  const selectedTeam = selectedTeamIndex === null ? null : catalogTeams[selectedTeamIndex]
  const refreshScreenAccess = useCallback(() => {
    setScreenAccessRevision((current) => current + 1)
  }, [])

  return {
    bootstrapping,
    login,
    password,
    showPassword,
    loading,
    error,
    session,
    screenAccessPages,
    screenAccessLoading,
    screenAccessError,
    refreshScreenAccess,
    profileSelectionPending,
    profileSelectionLoading,
    profileSelectionError,
    activePage,
    sisAcademicoSectionKey,
    legacyReportKey,
    portalStudentSection,
    preinscriptionActiveStage,
    activeMoodleSection,
    practicasProcess,
    practicasNavigationKey,
    titulosRegistradosTipo,
    displayName,
    dashboardMatriculaLoading,
    dashboardMatriculaError,
    dashboardMatricula,
    catalogLoading,
    catalogMessage,
    catalogError,
    matriculaSummaryLoading,
    matriculaPeriodSummaryLoading,
    matriculaMovementSummaryLoading,
    matriculaCareerStateLoading,
    matriculaListLoading,
    matriculaSummaryError,
    matriculaPeriodSummaryError,
    matriculaMovementSummaryError,
    matriculaCareerStateError,
    matriculaListError,
    matriculaSummary,
    matriculaSummaryUpdatedAt,
    matriculaPeriodSummary,
    matriculaYearSummary,
    matriculaMovementSummary,
    matriculaMovementYearSummary,
    matriculaCareerStateReport,
    matriculaTotalsByEstado,
    matriculaStudents,
    matriculaTipo,
    matriculaEstado,
    ingresoVentasLoading,
    ingresoVentasError,
    ingresoVentas,
    cruceDatosLoading,
    cruceDatosDownloadLoading,
    cruceDatosError,
    cruceDatos,
    createLoading,
    createMessage,
    createError,
    catalogTeams,
    createDisplayName,
    createCourses,
    createTeachers,
    createVisibility,
    teamsUserId,
    teamsTeamId,
    enrollLoading,
    selectedTeamIndex,
    selectedTeam,
    matriculaAcadMode,
    setLogin,
    setPassword,
    setShowPassword,
    onSubmit,
    selectAccessProfile,
    openDashboard,
    openSistemaAcademicoPage,
    openPortalEstudiantePage,
    openInglesPage,
    openExpedientesDocumentalesPage,
    setPortalStudentSection,
    openPortalDocentePage,
    openPortalDocenteInformePage,
    openPortalDocentePlanificacionPage,
    openPortalDocenteContratosPage,
    openTeacherEvaluationPage,
    openTeacherEvaluationAdminPage,
    openTeacherEvaluationProgressPage,
    openTeacherEvaluationReportsPage,
    openTeacherComplianceFormatPage,
    openTeamsPage,
    openHistoricoIntegracionesPage,
    openInformeCumplimientoPage,
    openMoodlePage,
    openTeamsMatriculaPage,
    openMoodleTeamsPage,
    openMatriculaPage,
    openMatriculaAcadPage,
    openMatriculaDocentePage,
    openCareerChangeRequestsPage,
    openModalityChangeRequestsPage,
    openEstadoDocentePage,
    openSenescytEstudiantesPage,
    openActualizarDatosEstudiantePage,
    openActualizarCorreoIntecPage,
    openPreinscripcionPage,
    openPreinscripcionStage,
    openReporteriaCarrerasPage,
    openReporteriaIntegralPage,
    openReportesIndividualesPage,
    openAdminNotasAsignaturaPage,
    openGestionSisAcademicoPage,
    openAsignacionPantallasPage,
    openPeriodoAcademicoPage,
    openPeriodoMatriculadosPage,
    openIngresoVentasPage,
    openCruceDatosPage,
    openValidarExcelPage,
    openRangoEdadesPage,
    openFechaGradoPage,
    openTitulacionPage,
    openTitulacionProcesoPage,
    openTitulacionResponsablesPage,
    openTitulosRegistradosPage,
    openCertificadosPage,
    openMatriculaExcelCertificadosPage,
    openCertificateRenamerPage,
    openCredentialGeneratorPage,
    openMassEmailPage,
    openCarnetInstitucionalPage,
    openPracticasInstitucionalesPage,
    loadMatriculaSummary: loadAcademicMatriculaSummary,
    loadDashboardMatricula,
    loadAcademicMatriculaSummary,
    loadMovementMatriculaSummary,
    loadMatriculaCareerStateReport,
    loadIngresoVentas,
    loadCruceDatos,
    downloadCruceDatosExcel,
    selectMatriculaTipo,
    selectMatriculaEstado,
    loadCatalog,
    selectMatriculaEstadoGlobal,
    selectMatriculaEstadoRh,
    selectMatriculaTotalRh,
    selectPeriodoAcademicoYear,
    selectPeriodoMatriculadosYear,
    enrollInTeam,
    createAndEnroll,
    setSelectedTeamIndex,
    setTeamsTeamId,
    setTeamsUserId,
    setCreateDisplayName,
    setCreateCourses,
    setCreateTeachers,
    setCreateVisibility,
    logout: performLogout,
  }
}
