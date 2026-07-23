import { useCallback, useEffect, useState, type SyntheticEvent } from 'react'

import {
  ApiError,
  createClassroom,
  downloadExcelSqlCrossWorkbook,
  fetchDashboardMatricula,
  fetchExcelSqlCross,
  fetchIngresoVentas,
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
import type {
  ExcelSqlCrossResponse,
  DashboardMatriculaResponse,
  GraphTeam,
  IngresoVentasResponse,
  MatriculaCareerStateSummaryResponse,
  MatriculaPeriodSummaryItem,
  MatriculaStudentItem,
  MatriculaSummaryItem,
  MatriculaTipo,
  TeamCreateAndEnrollPayload,
  MatriculaYearSummaryItem,
  Page,
  PreinscriptionStage,
  PortalStudentSection,
  UserSession,
} from '../types/app'
import { useInactivityLogout } from './useInactivityLogout'

const INACTIVITY_TIMEOUT_MS = 20 * 60 * 1000
const ADMISSIONS_ALLOWED_PAGES: Page[] = [
  'dashboard',
  'sistema-academico',
  'preinscripcion',
  'gestion-sisacademico',
  'sisacademico-v1',
]
const ACADEMIC_ALLOWED_PAGES = new Set<Page>([
  'dashboard',
  'sistema-academico',
  'preinscripcion',
  'matricula',
  'matricula-acad',
  'matricula-docente',
  'estado-docente',
  'actualizar-datos-estudiante',
  'reportes-individuales',
  'reporteria-integral',
  'gestion-sisacademico',
  'sisacademico-v1',
  'asignacion-pantallas',
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
const FINANCIAL_ALLOWED_PAGES = new Set<Page>([
  'dashboard',
  'sistema-academico',
  'preinscripcion',
  'ingreso-ventas',
  'gestion-sisacademico',
  'sisacademico-v1',
  'reporteria-integral',
  'carnet-institucional',
])
const SECRETARIA_ALLOWED_PAGES = new Set<Page>([
  'sistema-academico',
  'practicas-institucionales',
  'fecha-grado',
  'senescyt-estudiantes',
  'titulacion',
  'titulacion-proceso',
  'titulacion-responsables',
  'titulos-registrados',
])
const DASHBOARD_ONLY_ROLES = new Set(['RECTOR', 'VICERRECTOR'])
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
const ADMISSIONS_ALLOWED_SIS_SECTIONS = new Set([
  'preinscripciones',
  'estudiantes',
  'cabecera_matricula',
  'pagos_matricula',
  'datos_factura',
])
const FINANCIAL_ALLOWED_SIS_SECTIONS = new Set([
  'cabecera_matricula',
  'pagos_matricula',
  'datos_factura',
])

type ApiErrorOptions = {
  expireOnUnauthorized?: boolean
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function defaultPageForRole(role?: string): Page {
  const normalizedRole = role?.trim().toUpperCase()
  if (normalizedRole === 'ESTUDIANTE') return 'portal-estudiante'
  if (normalizedRole === 'DOCENTE') return 'portal-docente'
  if (normalizedRole === 'ADMISIONES') return 'dashboard'
  if (normalizedRole === 'FINANCIERO') return 'preinscripcion'
  if (normalizedRole === 'SECRETARIA') return 'practicas-institucionales'
  if (DASHBOARD_ONLY_ROLES.has(normalizedRole || '')) return 'dashboard'
  return 'dashboard'
}

function pageAllowedForRole(role: string | undefined, page: Page): boolean {
  const normalizedRole = role?.trim().toUpperCase()
  if (normalizedRole === 'ESTUDIANTE') {
    return page === 'portal-estudiante' || page === 'carnet-institucional' || page === 'evaluacion-docente' || page === 'practicas-institucionales'
  }
  if (normalizedRole === 'DOCENTE') return page === 'portal-docente' || page === 'portal-docente-informe' || page === 'portal-docente-planificacion' || page === 'portal-docente-contratos' || page === 'carnet-institucional'
  if (normalizedRole === 'ADMISIONES') return ADMISSIONS_ALLOWED_PAGES.includes(page)
  if (normalizedRole === 'SECRETARIA') return SECRETARIA_ALLOWED_PAGES.has(page)
  if (DASHBOARD_ONLY_ROLES.has(normalizedRole || '')) return page === 'dashboard'
  if (normalizedRole === 'ACADEMICO' || normalizedRole === 'BIENESTAR') return ACADEMIC_ALLOWED_PAGES.has(page)
  if (normalizedRole === 'FINANCIERO') return FINANCIAL_ALLOWED_PAGES.has(page)
  if (page === 'credenciales') return normalizedRole === 'ADMINISTRADOR'
  if (page === 'correos-masivos') return MASS_EMAIL_ALLOWED_ROLES.has(normalizedRole || '')
  if (page === 'carnet-institucional') return Boolean(normalizedRole)
  if (TECHNICAL_GLOBAL_ROLES.has(normalizedRole || '')) return page !== 'portal-estudiante' && page !== 'portal-docente' && page !== 'portal-docente-informe' && page !== 'portal-docente-planificacion' && page !== 'portal-docente-contratos'
  return page === 'dashboard'
}

function admissionsSection(sectionKey: string | null): string {
  const requestedSection = sectionKey || ''
  return ADMISSIONS_ALLOWED_SIS_SECTIONS.has(requestedSection) ? requestedSection : 'preinscripciones'
}

function financialSection(sectionKey: string | null): string {
  const requestedSection = sectionKey || ''
  return FINANCIAL_ALLOWED_SIS_SECTIONS.has(requestedSection) ? requestedSection : 'cabecera_matricula'
}

function preinscriptionStage(stage: string | null): PreinscriptionStage {
  const value = stage || ''
  return ['registro', 'inscritos', 'cabecera', 'documentos', 'materias', 'seguimiento'].includes(value)
    ? value as PreinscriptionStage
    : 'registro'
}

export function useReporteriaApp() {
  const [bootstrapping, setBootstrapping] = useState(true)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState<UserSession | null>(null)
  const [profileSelectionPending, setProfileSelectionPending] = useState(false)
  const [profileSelectionLoading, setProfileSelectionLoading] = useState(false)
  const [profileSelectionError, setProfileSelectionError] = useState('')
  const [activePage, setActivePage] = useState<Page>(() => readStoredPage())
  const [sisAcademicoSectionKey, setSisAcademicoSectionKey] = useState('')
  const [legacyReportKey, setLegacyReportKey] = useState('')
  const [portalStudentSection, setPortalStudentSection] = useState<PortalStudentSection>('dashboard')
  const [preinscriptionActiveStage, setPreinscriptionActiveStage] = useState<PreinscriptionStage>('registro')
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

  const resetWorkspace = useCallback(() => {
    setActivePage('dashboard')
    setSisAcademicoSectionKey('')
    setLegacyReportKey('')
    setPortalStudentSection('dashboard')
    setPreinscriptionActiveStage('registro')
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
          return apiError.message || 'Credenciales invalidas. Verifica usuario y contrasena.'
        }

        resetAfterLogout('Sesion expirada. Vuelve a iniciar sesion.')
        return 'Sesion expirada. Vuelve a iniciar sesion.'
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
          setError(handleApiError(apiError, 'No se pudo cerrar la sesion actual'))
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
          setActivePage((currentPage) =>
            pageAllowedForRole(currentSession.rol, currentPage) ? currentPage : defaultPageForRole(currentSession.rol)
          )
        }
        if (!currentSession) {
          resetWorkspace()
        }
      } catch (apiError) {
        if (cancelled) return
        setError(handleApiError(apiError, 'No se pudo validar la sesion actual'))
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
    if (!session) return
    if (session.rol === 'ESTUDIANTE') {
      if (
        activePage !== 'portal-estudiante'
        && activePage !== 'carnet-institucional'
        && activePage !== 'evaluacion-docente'
        && activePage !== 'practicas-institucionales'
      ) {
        setActivePage('portal-estudiante')
        setPortalStudentSection('dashboard')
      }
      return
    }
    if (session.rol === 'DOCENTE') {
      if (activePage !== 'portal-docente' && activePage !== 'portal-docente-informe' && activePage !== 'portal-docente-planificacion' && activePage !== 'portal-docente-contratos' && activePage !== 'carnet-institucional') {
        setActivePage('portal-docente')
      }
      return
    }
    const url = new URL(globalThis.location.href)
    const openPage = url.searchParams.get('open_page')
    if (session.rol === 'ADMISIONES') {
      if (openPage === 'gestion-sisacademico') {
        setSisAcademicoSectionKey(admissionsSection(url.searchParams.get('sis_section')))
        setActivePage('gestion-sisacademico')
      } else if (openPage && pageAllowedForRole(session.rol, openPage as Page)) {
        setSisAcademicoSectionKey('')
        setActivePage(openPage as Page)
      } else if (!openPage && pageAllowedForRole(session.rol, activePage)) {
        setSisAcademicoSectionKey('')
      } else {
        setSisAcademicoSectionKey('')
        setPreinscriptionActiveStage(preinscriptionStage(url.searchParams.get('preinscripcion_stage')))
        setActivePage(defaultPageForRole(session.rol))
      }
      return
    }
    if (session.rol === 'FINANCIERO') {
      if (openPage === 'gestion-sisacademico') {
        setSisAcademicoSectionKey(financialSection(url.searchParams.get('sis_section')))
        setActivePage('gestion-sisacademico')
      } else if (openPage === 'preinscripcion') {
        setSisAcademicoSectionKey('')
        setPreinscriptionActiveStage(preinscriptionStage(url.searchParams.get('preinscripcion_stage')))
        setActivePage('preinscripcion')
      } else if (openPage && pageAllowedForRole(session.rol, openPage as Page)) {
        setActivePage(openPage as Page)
      } else if (!pageAllowedForRole(session.rol, activePage)) {
        setActivePage(defaultPageForRole(session.rol))
      }
      return
    }
    if (openPage === 'teams') {
      setActivePage('teams')
    } else if (openPage === 'teams-matricula') {
      setActivePage('teams-matricula')
    } else if (openPage === 'periodo-academico') {
      setActivePage('periodo-academico')
    } else if (openPage === 'matricula-acad') {
      setActivePage('matricula-acad')
    } else if (openPage === 'matricula-docente') {
      setActivePage('matricula-docente')
    } else if (openPage === 'evaluacion-docente-admin') {
      setActivePage('evaluacion-docente-avance')
    } else if (openPage === 'evaluacion-docente-avance') {
      setActivePage('evaluacion-docente-avance')
    } else if (openPage === 'evaluacion-docente-reportes') {
      setActivePage('evaluacion-docente-reportes')
    } else if (openPage === 'formato-informe-docente') {
      setActivePage('formato-informe-docente')
    } else if (openPage === 'practicas-institucionales' && pageAllowedForRole(session.rol, 'practicas-institucionales')) {
      setActivePage('practicas-institucionales')
    } else if (openPage === 'estado-docente') {
      setActivePage('estado-docente')
    } else if (openPage === 'senescyt-estudiantes' && pageAllowedForRole(session.rol, 'senescyt-estudiantes')) {
      setActivePage('senescyt-estudiantes')
    } else if (openPage === 'fecha-grado' && pageAllowedForRole(session.rol, 'fecha-grado')) {
      setActivePage('fecha-grado')
    } else if (openPage === 'titulacion' && pageAllowedForRole(session.rol, 'titulacion')) {
      setActivePage('titulacion')
    } else if (openPage === 'titulacion-proceso' && pageAllowedForRole(session.rol, 'titulacion-proceso')) {
      setActivePage('titulacion-proceso')
    } else if (openPage === 'titulacion-responsables' && pageAllowedForRole(session.rol, 'titulacion-responsables')) {
      setActivePage('titulacion-responsables')
    } else if (openPage === 'titulos-registrados' && pageAllowedForRole(session.rol, 'titulos-registrados')) {
      setActivePage('titulos-registrados')
    } else if (openPage === 'preinscripcion') {
      setPreinscriptionActiveStage(preinscriptionStage(url.searchParams.get('preinscripcion_stage')))
      setActivePage('preinscripcion')
    } else if (openPage === 'reporteria-carreras') {
      setActivePage('reporteria-carreras')
    } else if (openPage === 'reporteria-integral') {
      setLegacyReportKey(url.searchParams.get('report_key') || '')
      setActivePage('reporteria-integral')
    } else if (openPage === 'reportes-individuales') {
      setLegacyReportKey(url.searchParams.get('report_key') || '')
      setActivePage('reportes-individuales')
    } else if (openPage === 'sisacademico-v1' && pageAllowedForRole(session.rol, 'sisacademico-v1')) {
      setSisAcademicoSectionKey('')
      setLegacyReportKey('')
      setActivePage('sisacademico-v1')
    } else if (openPage === 'asignacion-pantallas' && pageAllowedForRole(session.rol, 'asignacion-pantallas')) {
      setActivePage('asignacion-pantallas')
    } else if (openPage === 'gestion-sisacademico') {
      setSisAcademicoSectionKey(url.searchParams.get('sis_section') || '')
      setActivePage('gestion-sisacademico')
    } else if (openPage === 'periodo-matriculados') {
      setActivePage('periodo-matriculados')
    } else if (openPage === 'ingreso-ventas') {
      setActivePage('ingreso-ventas')
    } else if (openPage === 'cruce-datos') {
      setActivePage('cruce-datos')
    } else if (openPage === 'validar-excel') {
      setActivePage('validar-excel')
    } else if (openPage === 'rango-edades') {
      setActivePage('rango-edades')
    } else if (openPage === 'certificados') {
      setActivePage('certificados')
    } else if (openPage === 'matricula-excel-certificados') {
      setActivePage('matricula-excel-certificados')
    } else if (openPage === 'renombrar-certificados') {
      setActivePage('renombrar-certificados')
    } else if (openPage === 'credenciales' && session.rol === 'ADMINISTRADOR') {
      setActivePage('credenciales')
    } else if (openPage === 'correos-masivos' && pageAllowedForRole(session.rol, 'correos-masivos')) {
      setActivePage('correos-masivos')
    } else if (openPage === 'carnet-institucional' && pageAllowedForRole(session.rol, 'carnet-institucional')) {
      setActivePage('carnet-institucional')
    } else if (openPage === 'evaluacion-docente' && pageAllowedForRole(session.rol, 'evaluacion-docente')) {
      setActivePage('evaluacion-docente')
    } else if (!openPage && !pageAllowedForRole(session.rol, activePage)) {
      setActivePage(defaultPageForRole(session.rol))
    }
  }, [activePage, session])

  useEffect(() => {
    if (!session) return
    if (!pageAllowedForRole(session.rol, activePage)) {
      setActivePage(defaultPageForRole(session.rol))
      setSisAcademicoSectionKey('')
      setLegacyReportKey('')
    }
  }, [activePage, session])

  useEffect(() => {
    if (session) {
      writeStoredPage(activePage)
    } else {
      clearStoredPage()
    }
  }, [activePage, session])

  useInactivityLogout(Boolean(session), INACTIVITY_TIMEOUT_MS, () => {
    void performLogout('Sesion cerrada por inactividad. Vuelve a iniciar sesion.')
  })

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()

    const normalizedLogin = login.trim()
    if (!normalizedLogin || !password) {
      setError('Ingresa tu usuario o correo y contrasena.')
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
      setMatriculaPeriodSummaryError(handleApiError(apiError, 'Error inesperado consultando resumen por periodo'))
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
      setMatriculaMovementSummaryError(handleApiError(apiError, 'Error inesperado consultando movimiento de matricula'))
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
      setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando estudiantes por periodo academico'))
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
      setMatriculaListError(handleApiError(apiError, 'Error inesperado consultando estudiantes por periodo matriculados'))
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
      setCatalogMessage('Catalogo de aulas obtenido correctamente.')
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
    setActivePage('dashboard')
    if (!dashboardMatricula && !dashboardMatriculaLoading) {
      void loadDashboardMatricula()
    }
  }
  const openPortalEstudiantePage = (section: PortalStudentSection = 'dashboard') => {
    setPortalStudentSection(section)
    setActivePage('portal-estudiante')
  }
  const openPortalDocentePage = () => {
    setActivePage('portal-docente')
  }
  const openPortalDocenteInformePage = () => {
    setActivePage('portal-docente-informe')
  }
  const openSistemaAcademicoPage = () => {
    setActivePage('sistema-academico')
    if (!dashboardMatricula && !dashboardMatriculaLoading) {
      void loadDashboardMatricula()
    }
  }
  const openPortalDocentePlanificacionPage = () => {
    setActivePage('portal-docente-planificacion')
  }
  const openPortalDocenteContratosPage = () => {
    setActivePage('portal-docente-contratos')
  }
  const openTeacherEvaluationPage = () => {
    setActivePage('evaluacion-docente')
  }
  const openTeacherEvaluationAdminPage = () => {
    setActivePage('evaluacion-docente-avance')
  }
  const openTeacherEvaluationProgressPage = () => {
    setActivePage('evaluacion-docente-avance')
  }
  const openTeacherEvaluationReportsPage = () => {
    setActivePage('evaluacion-docente-reportes')
  }
  const openTeacherComplianceFormatPage = () => {
    setActivePage('formato-informe-docente')
  }
  const openTeamsPage = () => setActivePage('teams')
  const openTeamsMatriculaPage = () => {
    setActivePage('teams-matricula')
    if (catalogTeams.length === 0 && !catalogLoading) {
      void loadCatalog()
    }
  }
  const openMatriculaPage = async () => {
    setActivePage('matricula')
    await loadAcademicMatriculaSummary()
  }
  const openMatriculaAcadPage = () => {
    setActivePage('matricula-acad')
  }
  const openMatriculaDocentePage = () => {
    setActivePage('matricula-docente')
  }
  const openEstadoDocentePage = () => {
    setActivePage('estado-docente')
  }
  const openSenescytEstudiantesPage = () => {
    setActivePage('senescyt-estudiantes')
  }
  const openActualizarDatosEstudiantePage = () => {
    setActivePage('actualizar-datos-estudiante')
  }
  const openPreinscripcionPage = () => {
    setPreinscriptionActiveStage('registro')
    setActivePage('preinscripcion')
  }
  const openPreinscripcionStage = (stage: PreinscriptionStage = 'registro') => {
    setPreinscriptionActiveStage(stage)
    setActivePage('preinscripcion')
  }
  const openReporteriaCarrerasPage = async () => {
    setActivePage('reporteria-carreras')
    await loadMatriculaCareerStateReport()
  }
  const openReporteriaIntegralPage = (reportKey?: string) => {
    setLegacyReportKey(reportKey || '')
    setActivePage('reporteria-integral')
  }
  const openReportesIndividualesPage = (reportKey?: string) => {
    setLegacyReportKey(reportKey || '')
    setActivePage('reportes-individuales')
  }
  const openGestionSisAcademicoPage = (sectionKey?: string) => {
    setSisAcademicoSectionKey(sectionKey || '')
    setActivePage('gestion-sisacademico')
  }
  const openSisAcademicoV1Page = () => {
    setSisAcademicoSectionKey('')
    setLegacyReportKey('')
    setActivePage('sisacademico-v1')
  }
  const openAsignacionPantallasPage = () => {
    setActivePage('asignacion-pantallas')
  }
  const openPeriodoAcademicoPage = async () => {
    setActivePage('periodo-academico')
    await loadAcademicMatriculaSummary()
  }
  const openPeriodoMatriculadosPage = async () => {
    setActivePage('periodo-matriculados')
    await loadMovementMatriculaSummary()
  }
  const openIngresoVentasPage = async () => {
    setActivePage('ingreso-ventas')
    if (!ingresoVentas && !ingresoVentasLoading) {
      await loadIngresoVentas()
    }
  }
  const openCruceDatosPage = async () => {
    setActivePage('cruce-datos')
    if (!cruceDatos && !cruceDatosLoading) {
      await loadCruceDatos()
    }
  }
  const openValidarExcelPage = () => {
    setActivePage('validar-excel')
  }
  const openRangoEdadesPage = () => {
    setActivePage('rango-edades')
  }
  const openFechaGradoPage = () => {
    setActivePage('fecha-grado')
  }
  const openTitulosRegistradosPage = (tipo = '') => {
    setTitulosRegistradosTipo(tipo)
    setActivePage('titulos-registrados')
  }
  const openTitulacionPage = () => {
    setActivePage('titulacion')
  }

  const openTitulacionProcesoPage = () => {
    setActivePage('titulacion-proceso')
  }
  const openTitulacionResponsablesPage = () => {
    setActivePage('titulacion-responsables')
  }
  const openCertificadosPage = () => {
    setActivePage('certificados')
  }
  const openMatriculaExcelCertificadosPage = () => {
    setActivePage('matricula-excel-certificados')
  }
  const openCertificateRenamerPage = () => {
    setActivePage('renombrar-certificados')
  }
  const openCredentialGeneratorPage = () => {
    setActivePage('credenciales')
  }
  const openMassEmailPage = () => {
    setActivePage('correos-masivos')
  }
  const openCarnetInstitucionalPage = () => {
    setActivePage('carnet-institucional')
  }
  const openPracticasInstitucionalesPage = () => {
    setActivePage('practicas-institucionales')
  }

  const displayName = session?.nombres?.trim() || session?.login || ''
  const selectedTeam = selectedTeamIndex === null ? null : catalogTeams[selectedTeamIndex]

  return {
    bootstrapping,
    login,
    password,
    showPassword,
    loading,
    error,
    session,
    profileSelectionPending,
    profileSelectionLoading,
    profileSelectionError,
    activePage,
    sisAcademicoSectionKey,
    legacyReportKey,
    portalStudentSection,
    preinscriptionActiveStage,
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
    setLogin,
    setPassword,
    setShowPassword,
    onSubmit,
    selectAccessProfile,
    openDashboard,
    openSistemaAcademicoPage,
    openPortalEstudiantePage,
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
    openTeamsMatriculaPage,
    openMatriculaPage,
    openMatriculaAcadPage,
    openMatriculaDocentePage,
    openEstadoDocentePage,
    openSenescytEstudiantesPage,
    openActualizarDatosEstudiantePage,
    openPreinscripcionPage,
    openPreinscripcionStage,
    setPreinscriptionActiveStage,
    openReporteriaCarrerasPage,
    openReporteriaIntegralPage,
    openReportesIndividualesPage,
    openGestionSisAcademicoPage,
    openSisAcademicoV1Page,
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
