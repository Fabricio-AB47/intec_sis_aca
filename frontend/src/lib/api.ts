import type {
  AdminGradeCourseSelection,
  AdminGradeStudentsResponse,
  AdminGradeTeachersResponse,
  CareerChangeActionResponse,
  CareerChangeCatalogResponse,
  CareerChangePreviewResponse,
  CareerChangeRequestDetail,
  CareerChangeRequestsResponse,
  AcademicEnrollmentCareersResponse,
  AcademicEnrollmentCatalogResponse,
  AcademicEnrollmentCohortResponse,
  AcademicEnrollmentDetailResponse,
  AcademicEnrollmentPensumResponse,
  AcademicBulkEnrollmentPayload,
  AcademicBulkEnrollmentPreviewResponse,
  AcademicBulkEnrollmentSaveResponse,
  AcademicPeriodChangeApplyResponse,
  AcademicPeriodChangeCatalogResponse,
  AcademicPeriodChangePayload,
  AcademicPeriodChangePreviewResponse,
  AcademicPrerequisiteRulePayload,
  AcademicPrerequisiteRulesResponse,
  AcademicPrerequisiteRuleSaveResponse,
  AcademicParallelBalancePayload,
  AcademicParallelBalanceResponse,
  AcademicEnrollmentPayload,
  AcademicEnrollmentPreviewResponse,
  AcademicEnrollmentSaveResponse,
  AcademicEnrollmentStudentSearchResponse,
  AcademicTeacherEnrollmentPayload,
  AcademicTeacherEnrollmentsResponse,
  AcademicTeacherEnrollmentSaveResponse,
  AcademicTeacherParallelOptionsResponse,
  AcademicTeacherSearchResponse,
  AcademicTeacherStateCatalogResponse,
  AcademicTeacherStateSearchResponse,
  AcademicTeacherStateUpdatePayload,
  AcademicTeacherStateUpdateResponse,
  AcademicTeacherStudentsResponse,
  AcademicTeacherMultiEnrollmentPayload,
  AcademicTeacherMultiSubjectEnrollmentPayload,
  AcademicTeacherUniqueEnrollmentPayload,
  AcademicTeacherUniqueSubjectsResponse,
  AgeRangeCatalogResponse,
  AgeRangeFilters,
  AgeRangeResponse,
  CertificadosCatalogResponse,
  CertificadosGeneratePayload,
  CarnetPersonaTipo,
  CarnetPhotoResponse,
  CarnetPhotoStatus,
  CarnetSearchResponse,
  CertificateRenameLocalSaveResponse,
  CertificateRenameResponse,
  CertificadosStudentsResponse,
  CredentialBulkPayload,
  CredentialBulkResponse,
  CredentialCatalogResponse,
  CredentialListResponse,
  AdmissionsDashboardStudentsResponse,
  ActaGradoPayload,
  AcademicSystemIntegrationResponse,
  DashboardMatriculaResponse,
  DashboardMatriculaTrendStudentsResponse,
  DocumentExpedientContext,
  DocumentExpedientFinalizeResponse,
  DocumentExpedientPrepareResponse,
  DocumentExpedientStudentSearchResponse,
  DocumentExpedientUploadSessionResponse,
  ExcelSqlCrossResponse,
  ExcelValidationResponse,
  EnglishActivitySchedulesResponse,
  EnglishExam,
  EnglishSubmissionsResponse,
  EnglishUploadSessionResponse,
  FechaGradoCatalogResponse,
  FechaGradoImportResponse,
  FechaGradoSavePayload,
  FechaGradoSaveResponse,
  FechaGradoStudentsResponse,
  FechaGradoVerificationResponse,
  IngresoVentasResponse,
  InstitutionalEmailAnalysisResponse,
  InstitutionalEmailApplyResponse,
  InstitutionalEmailStudentsResponse,
  InstitutionalEmailUpdateResponse,
  ComplianceInvoiceBackupUploadResponse,
  ComplianceDocumentsResponse,
  ComplianceDocumentType,
  IntegrationDatabaseEvent,
  IntegrationHistoryDetail,
  IntegrationHistoryPage,
  IntegrationHistorySummary,
  IntegrationTeacherReportEvent,
  LegacyCrystalCatalogResponse,
  LegacyDataUpdateDetailResponse,
  LegacyDataUpdateSearchResponse,
  LegacyDataUpdateTarget,
  LegacyActiveGradeStudentsResponse,
  LegacyGradeUpdatePayload,
  LegacyGradeUpdateResponse,
  LegacyReportFilters,
  LegacyReportsCatalogResponse,
  LegacyReportResponse,
  ModernizedLegacyReportsCatalogResponse,
  MoodleCourseEvaluationsResponse,
  MoodleCourseResourcesResponse,
  MoodleCoursesResponse,
  MoodleEvaluationDateUpdate,
  MoodleEvaluationDatesUpdateResponse,
  MoodleGradeApplyResponse,
  MoodleGradeAlertResponse,
  MoodleGradeCatalogResponse,
  MoodleGradeCourseOption,
  MoodleGradeHistoryResponse,
  MoodleGradePreviewResponse,
  MoodleSectionNameUpdateResponse,
  MoodleSectionVisibilityUpdateResponse,
  MoodleStatusResponse,
  MoodleTeamsEnrollmentResponse,
  MoodleTeamsPreviewResponse,
  MoodleUserStatusUpdateResponse,
  MoodleUsersResponse,
  MassEmailRecipient,
  MassEmailExcelResponse,
  MassEmailResolvePayload,
  MassEmailResolveResponse,
  MassEmailSearchResponse,
  MassEmailSendResponse,
  MatriculaCareerStateStudentsResponse,
  MatriculaCareerStateSummaryResponse,
  MatriculaListResponse,
  MatriculaPeriodSummaryResponse,
  MatriculaSummaryResponse,
  MatriculaTipo,
  PortalAcademicPlanningPayload,
  PortalStudentRecordResponse,
  PortalTeacherComplianceMoodleResourcesResponse,
  PortalTeacherCoursesResponse,
  PortalTeacherContractAnalysis,
  PortalTeacherContractDocumentSaveResponse,
  PortalTeacherContractsResponse,
  PortalTeacherGradePayload,
  PortalTeacherGradeSaveResponse,
  PortalTeacherProfileResponse,
  PortalTeacherStudentsResponse,
  PracticasCatalogResponse,
  PracticasElegiblesResponse,
  PracticasExpedientesResponse,
  PracticasPeriodoDesignacionesResponse,
  PracticasPeriodosResponse,
  PracticasProcessCode,
  PracticasReviewDecision,
  PracticasReviewDetailResponse,
  PracticasReviewResponse,
  PracticasResponsableProgressResponse,
  PracticasStudentResponse,
  PreinscriptionCabeceraPayload,
  PreinscriptionCabeceraSaveResponse,
  PreinscriptionCatalogResponse,
  PreinscriptionCedulaValidationResponse,
  PreinscriptionCreatePayload,
  PreinscriptionCreateResponse,
  PreinscriptionDocumentUploadResponse,
  PreinscriptionDocumentsPayload,
  PreinscriptionDocumentsSaveResponse,
  PreinscriptionFollowupPayload,
  PreinscriptionFollowupSaveResponse,
  PreinscriptionListResponse,
  PreinscriptionPhotoResponse,
  PreinscriptionRevertResponse,
  PreinscriptionScholarshipApprovalListResponse,
  PreinscriptionScholarshipStatus,
  SenescytAuditResponse,
  SenescytCatalogResponse,
  SenescytExportMode,
  SenescytStudentDataDetailResponse,
  SenescytStudentDataSearchResponse,
  SenescytStudentReportResponse,
  SenescytTarget,
  ScholarshipConfigurationListResponse,
  ScholarshipConfigurationPayload,
  ScholarshipConfigurationSaveResponse,
  ScholarshipBeneficiaryListResponse,
  ScholarshipContractCandidateListResponse,
  ScholarshipContractFormat,
  ScholarshipContractHistoryResponse,
  ScholarshipContractTemplate,
  ScholarshipContractUploadResponse,
  ScreenAccessResponse,
  ScreenAccessRole,
  SisAcademicoCatalogResponse,
  SisAcademicoListResponse,
  SisAcademicoRecordResponse,
  SisAcademicoSaveResponse,
  SisAcademicoV1ArtifactsResponse,
  SisAcademicoV1ModulesResponse,
  TeamCallStatus,
  TeamAttendance,
  TeamCollectionResponse,
  TeamCourse,
  TeamCreateAndEnrollPayload,
  TeamEnrollmentFilterOptionsPayload,
  TeamEnrollmentFilterOptionsResponse,
  TeamEnrollmentGroupSearchPayload,
  TeamEnrollmentGroupSearchResponse,
  TeamEnrollmentGroupStudentsPayload,
  TeamEnrollmentGroupStudentsResponse,
  TeamIndividualEnrollmentPayload,
  TeamIndividualStudentSearchPayload,
  TeamIndividualStudentSearchResponse,
  TeamManualEmailEnrollmentPayload,
  TeamEnrollmentSelectionPayload,
  TeamInviteMissingResponse,
  TeamMassEnrollmentRequestPayload,
  TeamMassEnrollmentResponse,
  TeamMessage,
  TeamParticipant,
  TeamRecording,
  TeamsActionResponse,
  TeamsCatalogResponse,
  TeacherEvaluationFlow,
  TeacherEvaluationAdminPendingResponse,
  TeacherEvaluationAdminPeriodsResponse,
  TeacherEvaluationAutoStudentListResponse,
  TeacherEvaluationProgressDetailResponse,
  TeacherEvaluationProgressParticipantsResponse,
  TeacherEvaluationStudentGradesResponse,
  TeacherEvaluationGradedTeachersResponse,
  TeacherEvaluationGradedSubjectsResponse,
  TeacherEvaluationStudentProgressResponse,
  TeacherEvaluationIdentityResponse,
  TeacherEvaluationQuestionsResponse,
  TeacherEvaluationStudentResponse,
  TeacherEvaluationTeacherResponse,
  TeacherRoleEvaluationSubmitPayload,
  TeacherEvaluationSubmitPayload,
  TeacherEvaluationSubmitResponse,
  TeacherComplianceReportFormat,
  TeacherComplianceMoodleResource,
  TeacherComplianceTeamsRecording,
  DefensaCalificacionPayload,
  DefensaTemaPayload,
  ExamenComplexivoCalificacionPayload,
  TitulacionAptosResponse,
  TitulacionExpedientePayload,
  TitulacionMecanismoPayload,
  TitulacionMallaCalificacionesResponse,
  TitulacionProgramacionResponse,
  TitulacionNotasPayload,
  TitulacionProgramacionPayload,
  TitulacionResponse,
  TitulacionTribunalPayload,
  TituloIntecPayload,
  TituloRegistradoSaveResponse,
  TituloSenescytPayload,
  TituloRegistradoTipo,
  TitulosRegistradosResponse,
  UserSession,
} from '../types/app'

type JsonBody =
  | Record<string, unknown>
  | Array<unknown>
  | string
  | number
  | boolean
  | null
  | undefined

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: BodyInit | JsonBody
  responseType?: 'json' | 'blob'
  onResponse?: (response: Response) => void
}

type ErrorPayload = {
  detail?: string
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

function resolveApiPath(path: string): string {
  if (!API_BASE_URL || !path.startsWith('/')) return path
  return `${API_BASE_URL}${path}`
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function isBodyInit(value: RequestOptions['body']): value is BodyInit {
  return (
    typeof value === 'string' ||
    value instanceof FormData ||
    value instanceof URLSearchParams ||
    value instanceof Blob ||
    value instanceof ArrayBuffer ||
    ArrayBuffer.isView(value)
  )
}

async function readResponsePayload(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null

  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers, credentials, responseType, onResponse, ...rest } = options
  const resolvedHeaders = new Headers(headers)
  const resolvedBody =
    body === undefined || body === null || isBodyInit(body) ? body : JSON.stringify(body)

  if (
    body !== undefined &&
    body !== null &&
    !isBodyInit(body) &&
    !resolvedHeaders.has('Content-Type')
  ) {
    resolvedHeaders.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(resolveApiPath(path), {
      credentials: credentials ?? 'include',
      headers: resolvedHeaders,
      body: resolvedBody,
      ...rest,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(
      'No se pudo conectar con el servidor. Verifique que el backend esté activo e intente nuevamente.',
      0,
    )
  }
  onResponse?.(response)

  const payload = responseType === 'blob' && response.ok ? await response.blob() : await readResponsePayload(response)

  if (!response.ok) {
    const rawDetail: unknown = typeof payload === 'string'
      ? payload
      : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    const detail =
      typeof rawDetail === 'string'
        ? rawDetail
        : Array.isArray(rawDetail)
          ? rawDetail
            .map((item) => typeof item === 'string' ? item : JSON.stringify(item))
            .join('; ')
          : JSON.stringify(rawDetail)
    throw new ApiError(detail, response.status)
  }

  return payload as T
}

const MOODLE_GRADE_ALERT_CACHE_MS = 30_000
export const MOODLE_GRADE_ALERT_INVALIDATED_EVENT = 'moodle-grade-alerts:invalidate'
let moodleGradeAlertCache: {
  expiresAt: number
  value: MoodleGradeAlertResponse
} | null = null
let moodleGradeAlertRequest: Promise<MoodleGradeAlertResponse> | null = null
let moodleGradeAlertGeneration = 0

function clearMoodleGradeAlertCache() {
  moodleGradeAlertGeneration += 1
  moodleGradeAlertCache = null
  moodleGradeAlertRequest = null
}

export function invalidateMoodleGradeAlertCache() {
  clearMoodleGradeAlertCache()
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(MOODLE_GRADE_ALERT_INVALIDATED_EVENT))
  }
}

let currentSessionRequest: Promise<UserSession | null> | null = null
const screenAccessRequests = new Map<boolean, Promise<ScreenAccessResponse>>()
const SCREEN_ACCESS_CACHE_MS = 30_000
const SCREEN_ACCESS_TIMEOUT_MS = 45_000
const screenAccessCache = new Map<boolean, { expiresAt: number; value: ScreenAccessResponse }>()

function clearAuthReadRequests() {
  currentSessionRequest = null
  screenAccessRequests.clear()
  screenAccessCache.clear()
}

export async function loginRequest(login: string, password: string): Promise<UserSession> {
  clearMoodleGradeAlertCache()
  clearAuthReadRequests()
  const session = await request<UserSession>('/api/auth/login', {
    method: 'POST',
    body: { login, password },
  })
  clearAuthReadRequests()
  return session
}

export async function selectProfileRequest(role: string): Promise<UserSession> {
  clearMoodleGradeAlertCache()
  clearAuthReadRequests()
  const session = await request<UserSession>('/api/auth/select-profile', {
    method: 'POST',
    body: { rol: role },
  })
  clearAuthReadRequests()
  return session
}

export async function getCurrentSession(): Promise<UserSession | null> {
  if (!currentSessionRequest) {
    const pending = (async () => {
      try {
        return await request<UserSession>('/api/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null
        }
        throw error
      }
    })()
    currentSessionRequest = pending
    pending.then(
      () => {
        if (currentSessionRequest === pending) currentSessionRequest = null
      },
      () => {
        if (currentSessionRequest === pending) currentSessionRequest = null
      },
    )
  }
  return currentSessionRequest
}

function screenAccessRequest(includeAll: boolean): Promise<ScreenAccessResponse> {
  const cached = screenAccessCache.get(includeAll)
  if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.value)
  if (cached) screenAccessCache.delete(includeAll)

  const activeRequest = screenAccessRequests.get(includeAll)
  if (activeRequest) return activeRequest

  const pending = (async () => {
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(() => controller.abort(), SCREEN_ACCESS_TIMEOUT_MS)
    try {
      const response = await request<ScreenAccessResponse>(
        `/api/auth/screen-access?include_all=${includeAll ? 'true' : 'false'}`,
        { signal: controller.signal },
      )
      screenAccessCache.set(includeAll, {
        expiresAt: Date.now() + SCREEN_ACCESS_CACHE_MS,
        value: response,
      })
      return response
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError(
          'La validación de pantallas agotó el tiempo de espera. Intente nuevamente.',
          408,
        )
      }
      throw error
    } finally {
      globalThis.clearTimeout(timeout)
    }
  })()
  screenAccessRequests.set(includeAll, pending)
  pending.then(
    () => {
      if (screenAccessRequests.get(includeAll) === pending) screenAccessRequests.delete(includeAll)
    },
    () => {
      if (screenAccessRequests.get(includeAll) === pending) screenAccessRequests.delete(includeAll)
    },
  )
  return pending
}

export async function logoutRequest(): Promise<void> {
  clearMoodleGradeAlertCache()
  clearAuthReadRequests()
  try {
    await request<void>('/api/auth/logout', { method: 'POST' })
  } finally {
    clearAuthReadRequests()
  }
}

export async function fetchScreenAccessAssignments(includeAll = false): Promise<ScreenAccessResponse> {
  return screenAccessRequest(includeAll)
}

export async function updateScreenAccessAssignment(role: string, pages: string[]): Promise<ScreenAccessRole> {
  clearAuthReadRequests()
  try {
    return await request<ScreenAccessRole>(`/api/auth/screen-access/${encodeURIComponent(role)}`, {
      method: 'PUT',
      body: { pages },
    })
  } finally {
    clearAuthReadRequests()
  }
}

export type IntegrationHistoryQuery = {
  page?: number
  pageSize?: number
  search?: string
  dateFrom?: string
  dateTo?: string
  operation?: '' | 'INSERT' | 'UPDATE' | 'DELETE'
  database?: string
  stage?: '' | 'GENERADO' | 'FIRMADO' | 'ARCHIVADO' | 'ERROR'
  status?: '' | 'EXITOSO' | 'ERROR'
}

function buildIntegrationHistoryParams(query: IntegrationHistoryQuery): URLSearchParams {
  const params = new URLSearchParams({
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 25),
  })
  if (query.search?.trim()) params.set('search', query.search.trim())
  if (query.dateFrom) params.set('date_from', `${query.dateFrom}T00:00:00`)
  if (query.dateTo) params.set('date_to', `${query.dateTo}T23:59:59.999`)
  return params
}

export async function fetchIntegrationHistorySummary(): Promise<IntegrationHistorySummary> {
  return request<IntegrationHistorySummary>('/api/integrations/history/summary', { cache: 'no-store' })
}

export async function fetchIntegrationDatabaseEvents(
  query: IntegrationHistoryQuery = {},
): Promise<IntegrationHistoryPage<IntegrationDatabaseEvent>> {
  const params = buildIntegrationHistoryParams(query)
  if (query.operation) params.set('operation', query.operation)
  if (query.database?.trim()) params.set('database', query.database.trim())
  return request<IntegrationHistoryPage<IntegrationDatabaseEvent>>(
    `/api/integrations/history/database-events?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function fetchIntegrationTeacherReportEvents(
  query: IntegrationHistoryQuery = {},
): Promise<IntegrationHistoryPage<IntegrationTeacherReportEvent>> {
  const params = buildIntegrationHistoryParams(query)
  if (query.stage) params.set('stage', query.stage)
  if (query.status) params.set('status', query.status)
  return request<IntegrationHistoryPage<IntegrationTeacherReportEvent>>(
    `/api/integrations/history/teacher-reports?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function fetchIntegrationHistoryDetail(
  kind: 'database' | 'teacher-report',
  eventId: number,
): Promise<IntegrationHistoryDetail> {
  return request<IntegrationHistoryDetail>(
    `/api/integrations/history/detail/${kind}/${eventId}`,
    { cache: 'no-store' },
  )
}

export type ComplianceDocumentsQuery = {
  page?: number
  pageSize?: number
  search?: string
  dateFrom?: string
  dateTo?: string
  documentType?: '' | ComplianceDocumentType
}

export async function fetchComplianceDocuments(
  query: ComplianceDocumentsQuery = {},
): Promise<ComplianceDocumentsResponse> {
  const params = buildIntegrationHistoryParams(query)
  if (query.documentType) params.set('document_type', query.documentType)
  return request<ComplianceDocumentsResponse>(
    `/api/integrations/history/compliance-documents?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function uploadComplianceInvoiceBackups(
  eventId: number,
  facturaXml: File,
  ridePdf: File,
): Promise<ComplianceInvoiceBackupUploadResponse> {
  const formData = new FormData()
  formData.append('factura_xml', facturaXml)
  formData.append('ride_pdf', ridePdf)
  return request<ComplianceInvoiceBackupUploadResponse>(
    `/api/integrations/history/compliance-documents/${eventId}/invoice-backups`,
    {
      method: 'POST',
      body: formData,
    },
  )
}

export type MoodleUsersQuery = {
  page?: number
  pageSize?: number
  email?: string
  state?: 'all' | 'active' | 'suspended' | 'unconfirmed'
  refresh?: boolean
}

export type MoodleCoursesQuery = {
  page?: number
  pageSize?: number
  search?: string
  visibility?: 'all' | 'visible' | 'hidden'
  categoryId?: number | null
  refresh?: boolean
}

export async function fetchMoodleStatus(): Promise<MoodleStatusResponse> {
  const response = await request<Partial<MoodleStatusResponse>>('/api/moodle/status', {
    cache: 'no-store',
  })

  return {
    enabled: Boolean(response.enabled),
    configured: Boolean(response.configured),
    reachable: Boolean(response.reachable),
    site_name: response.site_name ?? '',
    site_url: response.site_url ?? '',
    moodle_username: response.moodle_username ?? '',
    moodle_user_id: Number(response.moodle_user_id ?? 0),
    moodle_release: response.moodle_release ?? '',
    moodle_version: response.moodle_version ?? '',
    user_is_site_admin: Boolean(response.user_is_site_admin),
    user_status_updates_enabled: Boolean(response.user_status_updates_enabled),
    section_updates_enabled: Boolean(response.section_updates_enabled),
    evaluation_date_updates_enabled: Boolean(response.evaluation_date_updates_enabled),
    evaluation_date_update_function: response.evaluation_date_update_function ?? '',
    evaluation_date_update_function_available: Boolean(response.evaluation_date_update_function_available),
    evaluation_date_update_reason: response.evaluation_date_update_reason ?? '',
    functions_count: Number(response.functions_count ?? 0),
    required_functions: Array.isArray(response.required_functions)
      ? response.required_functions
      : [],
    missing_required_functions: Array.isArray(response.missing_required_functions)
      ? response.missing_required_functions
      : [],
  }
}

export async function fetchMoodleUsers(query: MoodleUsersQuery = {}): Promise<MoodleUsersResponse> {
  const params = new URLSearchParams({
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 50),
    state: query.state ?? 'all',
    refresh: query.refresh ? 'true' : 'false',
  })
  if (query.email?.trim()) params.set('email', query.email.trim())
  return request<MoodleUsersResponse>(`/api/moodle/users?${params.toString()}`, { cache: 'no-store' })
}

export async function updateMoodleUserStatus(
  userId: number,
  active: boolean,
): Promise<MoodleUserStatusUpdateResponse> {
  return request<MoodleUserStatusUpdateResponse>(`/api/moodle/users/${userId}/status`, {
    method: 'PATCH',
    body: { active },
  })
}

export async function fetchMoodleCourses(query: MoodleCoursesQuery = {}): Promise<MoodleCoursesResponse> {
  const params = new URLSearchParams({
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 50),
    visibility: query.visibility ?? 'all',
    refresh: query.refresh ? 'true' : 'false',
  })
  if (query.search?.trim()) params.set('search', query.search.trim())
  if (query.categoryId !== null && query.categoryId !== undefined) {
    params.set('category_id', String(query.categoryId))
  }
  return request<MoodleCoursesResponse>(`/api/moodle/courses?${params.toString()}`, { cache: 'no-store' })
}

export async function fetchMoodleCourseResources(
  courseId: number,
  refresh = false,
): Promise<MoodleCourseResourcesResponse> {
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  return request<MoodleCourseResourcesResponse>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/resources?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function fetchMoodleGradeCatalog(
  refresh = false,
): Promise<MoodleGradeCatalogResponse> {
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  const response = await request<Partial<MoodleGradeCatalogResponse>>(
    `/api/moodle/grades/catalog?${params.toString()}`,
    { cache: 'no-store' },
  )
  const courses = Array.isArray(response.courses)
    ? response.courses.map((course) => ({
        ...course,
        periods: Array.isArray(course.periods) ? course.periods : [],
      }))
    : []
  const matched = courses.filter((course) => course.has_academic_match).length

  return {
    enabled: Boolean(response.enabled),
    apply_enabled: Boolean(response.apply_enabled),
    nightly_enabled: Boolean(response.nightly_enabled),
    change_detection_enabled: Boolean(response.change_detection_enabled),
    change_detection_interval_minutes: Number(response.change_detection_interval_minutes ?? 0),
    configured_mappings: Array.isArray(response.configured_mappings)
      ? response.configured_mappings
      : [],
    totals: {
      courses: Number(response.totals?.courses ?? courses.length),
      matched: Number(response.totals?.matched ?? matched),
      unmatched: Number(response.totals?.unmatched ?? Math.max(courses.length - matched, 0)),
    },
    courses,
  }
}

export async function fetchMoodleGradeAlerts(
  refresh = false,
): Promise<MoodleGradeAlertResponse> {
  if (!refresh && moodleGradeAlertCache && moodleGradeAlertCache.expiresAt > Date.now()) {
    return moodleGradeAlertCache.value
  }
  if (!refresh && moodleGradeAlertRequest) return moodleGradeAlertRequest

  if (refresh) clearMoodleGradeAlertCache()
  const requestGeneration = moodleGradeAlertGeneration
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  const pendingRequest = request<MoodleGradeAlertResponse>(
    `/api/moodle/grades/alerts?${params.toString()}`,
    { cache: 'no-store' },
  )
  moodleGradeAlertRequest = pendingRequest
  try {
    const response = await pendingRequest
    const normalizedResponse: MoodleGradeAlertResponse = {
      ...response,
      summary: {
        total: Number(response.summary?.total ?? 0),
        ungraded: Number(response.summary?.ungraded ?? 0),
        review: Number(response.summary?.review ?? 0),
        data_issues: Number(response.summary?.data_issues ?? 0),
        courses: Number(response.summary?.courses ?? 0),
        students: Number(response.summary?.students ?? 0),
        teachers: Number(response.summary?.teachers ?? 0),
        assignments: Number(response.summary?.assignments ?? 0),
        errors: Number(response.summary?.errors ?? 0),
        missing_intecbdd: Number(response.summary?.missing_intecbdd ?? 0),
        missing_moodle: Number(response.summary?.missing_moodle ?? 0),
        missing_both: Number(response.summary?.missing_both ?? 0),
        regular: Number(response.summary?.regular ?? 0),
        homologation: Number(response.summary?.homologation ?? 0),
      },
      validation: {
        selected_periods: Number(response.validation?.selected_periods ?? 0),
        academic_enrollments: Number(response.validation?.academic_enrollments ?? 0),
        moodle_course_users: Number(response.validation?.moodle_course_users ?? 0),
        matched_by_email: Number(response.validation?.matched_by_email ?? 0),
        matched_by_registry: Number(response.validation?.matched_by_registry ?? 0),
        matched_by_data_fallback: Number(response.validation?.matched_by_data_fallback ?? 0),
        missing_institutional_email: Number(response.validation?.missing_institutional_email ?? 0),
        not_enrolled_in_course: Number(response.validation?.not_enrolled_in_course ?? 0),
        ambiguous_users: Number(response.validation?.ambiguous_users ?? 0),
      },
      items: (response.items ?? []).map((item) => ({
        ...item,
        teacher_codes: item.teacher_codes ?? [],
        teacher_assignments: item.teacher_assignments ?? [],
        missing_components: item.missing_components ?? [],
        academic_missing_components: item.academic_missing_components ?? [],
        moodle_missing_components: item.moodle_missing_components ?? [],
        missing_sources: item.missing_sources ?? [],
        component_details: (item.component_details ?? []).map((component) => ({
          ...component,
          moodle_grade_items: component.moodle_grade_items ?? [],
        })),
        moodle_courses: item.moodle_courses ?? [],
        moodle_checked: item.moodle_checked ?? true,
        moodle_error: item.moodle_error ?? '',
      })),
      errors: response.errors ?? [],
    }
    if (requestGeneration === moodleGradeAlertGeneration) {
      moodleGradeAlertCache = {
        expiresAt: Date.now() + MOODLE_GRADE_ALERT_CACHE_MS,
        value: normalizedResponse,
      }
    }
    return normalizedResponse
  } finally {
    if (moodleGradeAlertRequest === pendingRequest) moodleGradeAlertRequest = null
  }
}

export async function fetchMoodleGradeCourseContext(
  courseId: number,
  refresh = false,
): Promise<MoodleGradeCourseOption> {
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  const response = await request<Partial<MoodleGradeCourseOption>>(
    `/api/moodle/grades/courses/${encodeURIComponent(String(courseId))}/context?${params.toString()}`,
    { cache: 'no-store' },
  )

  return {
    id: Number(response.id ?? courseId),
    name: String(response.name ?? `Curso Moodle ${courseId}`),
    shortname: String(response.shortname ?? ''),
    idnumber: String(response.idnumber ?? ''),
    matched_course_code: String(response.matched_course_code ?? ''),
    matched_course_codes: Array.isArray(response.matched_course_codes)
      ? response.matched_course_codes.map(String)
      : [],
    has_academic_match: Boolean(response.has_academic_match),
    recommended_period_code: response.recommended_period_code == null
      ? null
      : Number(response.recommended_period_code),
    recommended_period_codes: Array.isArray(response.recommended_period_codes)
      ? response.recommended_period_codes.map(Number).filter((value) => Number.isFinite(value))
      : [],
    identity_key: response.identity_key === 'CorreoIntec' ? 'CorreoIntec' : undefined,
    identity_relation: String(response.identity_relation ?? ''),
    match_method: response.match_method ?? '',
    matched_students: Number(response.matched_students ?? 0),
    moodle_users: Number(response.moodle_users ?? 0),
    moodle_users_with_email: Number(response.moodle_users_with_email ?? 0),
    resolution_reason: String(response.resolution_reason ?? ''),
    periods: Array.isArray(response.periods) ? response.periods : [],
  }
}

function normalizeMoodleGradePreview(
  response: Partial<MoodleGradePreviewResponse>,
  courseId: number,
  periodCodes: number[],
): MoodleGradePreviewResponse {
  const fallbackPeriodCode = periodCodes[0] ?? 0
  const period = response.period ?? {
    code: fallbackPeriodCode,
    name: fallbackPeriodCode ? `Período ${fallbackPeriodCode}` : 'Sin período',
    type: 'R',
  }
  const periods = Array.isArray(response.periods) && response.periods.length
    ? response.periods
    : [period]
  const validation = response.course_validation

  return {
    course: response.course ?? { id: courseId, name: 'Curso Moodle', code: '' },
    period,
    periods,
    selected_period_codes: Array.isArray(response.selected_period_codes)
      ? response.selected_period_codes
      : periods.map((item) => item.code),
    rule: response.rule ?? '',
    generated_at: response.generated_at ?? '',
    replace_existing: Boolean(response.replace_existing),
    counts: response.counts ?? {},
    course_validation: {
      selected_periods: Number(validation?.selected_periods ?? periods.length),
      academic_enrollments: Number(validation?.academic_enrollments ?? 0),
      moodle_course_users: Number(validation?.moodle_course_users ?? 0),
      matched_by_email: Number(validation?.matched_by_email ?? 0),
      matched_by_registry: Number(validation?.matched_by_registry ?? 0),
      matched_by_data_fallback: Number(validation?.matched_by_data_fallback ?? 0),
      missing_institutional_email: Number(validation?.missing_institutional_email ?? 0),
      not_enrolled_in_course: Number(validation?.not_enrolled_in_course ?? 0),
      ambiguous_users: Number(validation?.ambiguous_users ?? 0),
    },
    changes: Array.isArray(response.changes) ? response.changes : [],
    enrollment_warnings: Array.isArray(response.enrollment_warnings)
      ? response.enrollment_warnings
      : [],
    can_apply: Boolean(response.can_apply),
  }
}

export async function previewMoodleGrades(
  courseId: number,
  periodCodes: number[],
  refresh = false,
  replaceExisting = false,
): Promise<MoodleGradePreviewResponse> {
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  const response = await request<Partial<MoodleGradePreviewResponse>>(
    `/api/moodle/grades/preview?${params.toString()}`,
    {
      method: 'POST',
      body: {
        course_id: courseId,
        period_codes: periodCodes,
        replace_existing: replaceExisting,
      },
    },
  )
  return normalizeMoodleGradePreview(response, courseId, periodCodes)
}

export async function applyMoodleGrades(
  courseId: number,
  periodCodes: number[],
  replaceExisting = false,
): Promise<MoodleGradeApplyResponse> {
  const response = await request<Partial<MoodleGradeApplyResponse>>('/api/moodle/grades/apply', {
    method: 'POST',
    body: {
      course_id: courseId,
      period_codes: periodCodes,
      replace_existing: replaceExisting,
    },
  })
  invalidateMoodleGradeAlertCache()
  return {
    ...normalizeMoodleGradePreview(response, courseId, periodCodes),
    applied: Number(response.applied ?? 0),
    runtime_conflicts: Array.isArray(response.runtime_conflicts)
      ? response.runtime_conflicts
      : [],
    message: response.message ?? 'La migración finalizó correctamente.',
  }
}

export async function fetchMoodleGradeHistory(
  limit = 50,
): Promise<MoodleGradeHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  const response = await request<Partial<MoodleGradeHistoryResponse>>(
    `/api/moodle/grades/history?${params.toString()}`,
    { cache: 'no-store' },
  )

  return {
    items: Array.isArray(response.items) ? response.items : [],
    total: Number(response.total ?? response.items?.length ?? 0),
  }
}

export type PortalTeacherComplianceMoodleQuery = {
  codigoPeriodos: string[]
  codigoEstudiantes?: string[]
  codigoMateria: string
  paralelo: string
  codAnioBasica?: string
  moodleCourseId?: number | null
  refresh?: boolean
}

export async function fetchPortalTeacherComplianceMoodleResources(
  query: PortalTeacherComplianceMoodleQuery,
): Promise<PortalTeacherComplianceMoodleResourcesResponse> {
  const params = new URLSearchParams()
  for (const codigoPeriodo of query.codigoPeriodos) {
    params.append('codigo_periodo', codigoPeriodo)
  }
  for (const codigoEstudiante of query.codigoEstudiantes || []) {
    params.append('codigo_estudiante', codigoEstudiante)
  }
  params.set('codigo_materia', query.codigoMateria)
  params.set('paralelo', query.paralelo)
  if (query.codAnioBasica?.trim()) params.set('cod_anio_basica', query.codAnioBasica.trim())
  if (query.moodleCourseId) params.set('moodle_course_id', String(query.moodleCourseId))
  if (query.refresh) params.set('refresh', 'true')
  return request<PortalTeacherComplianceMoodleResourcesResponse>(
    `/api/portal/teacher/compliance-moodle-resources?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function updateMoodleSectionVisibility(
  courseId: number,
  sectionId: number,
  visible: boolean,
): Promise<MoodleSectionVisibilityUpdateResponse> {
  return request<MoodleSectionVisibilityUpdateResponse>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/sections/${encodeURIComponent(String(sectionId))}/visibility`,
    {
      method: 'PATCH',
      body: { visible },
    },
  )
}

export async function updateMoodleSectionName(
  courseId: number,
  sectionId: number,
  name: string,
): Promise<MoodleSectionNameUpdateResponse> {
  return request<MoodleSectionNameUpdateResponse>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/sections/${encodeURIComponent(String(sectionId))}/name`,
    {
      method: 'PATCH',
      body: { name },
    },
  )
}

export function moodleCourseResourceFileUrl(
  courseId: number,
  moduleId: number,
  fileIndex: number,
  disposition: 'inline' | 'attachment' = 'inline',
): string {
  const params = new URLSearchParams({ disposition })
  return resolveApiPath(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/modules/${encodeURIComponent(String(moduleId))}/files/${encodeURIComponent(String(fileIndex))}?${params.toString()}`,
  )
}

export async function downloadMoodleCourseResourceFile(
  courseId: number,
  moduleId: number,
  fileIndex: number,
): Promise<Blob> {
  const blob = await request<Blob>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/modules/${encodeURIComponent(String(moduleId))}/files/${encodeURIComponent(String(fileIndex))}?disposition=attachment`,
    { responseType: 'blob' },
  )
  if (blob.size === 0) {
    throw new ApiError('El recurso no contiene datos descargables.', 502)
  }
  return blob
}

export async function fetchCarnetMe(): Promise<CarnetPhotoStatus> {
  return request<CarnetPhotoStatus>('/api/carnet/me')
}

export async function searchCarnetPersonas(
  query = '',
  tipo: CarnetPersonaTipo | 'TODOS' = 'TODOS',
  limit = 30
): Promise<CarnetSearchResponse> {
  const params = new URLSearchParams({
    q: query,
    tipo,
    limit: String(limit),
  })
  return request<CarnetSearchResponse>(`/api/carnet/personas?${params.toString()}`)
}

export async function fetchCarnetPersonaPhoto(
  tipoPersona: CarnetPersonaTipo | string,
  codigoPersona: string
): Promise<CarnetPhotoStatus> {
  return request<CarnetPhotoStatus>(
    `/api/carnet/personas/${encodeURIComponent(tipoPersona)}/${encodeURIComponent(codigoPersona)}/foto`
  )
}

export async function uploadCarnetMePhoto(file: File): Promise<CarnetPhotoResponse> {
  const formData = new FormData()
  formData.set('file', file)
  return request<CarnetPhotoResponse>('/api/carnet/me/foto', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadCarnetPersonaPhoto(
  tipoPersona: CarnetPersonaTipo | string,
  codigoPersona: string,
  file: File
): Promise<CarnetPhotoResponse> {
  const formData = new FormData()
  formData.set('file', file)
  return request<CarnetPhotoResponse>(
    `/api/carnet/personas/${encodeURIComponent(tipoPersona)}/${encodeURIComponent(codigoPersona)}/foto`,
    {
      method: 'POST',
      body: formData,
    }
  )
}

export async function downloadCarnetMePdf(): Promise<Blob> {
  return request<Blob>('/api/carnet/me/pdf', { responseType: 'blob' })
}

export async function downloadCarnetPersonaPdf(
  tipoPersona: CarnetPersonaTipo | string,
  codigoPersona: string
): Promise<Blob> {
  return request<Blob>(
    `/api/carnet/personas/${encodeURIComponent(tipoPersona)}/${encodeURIComponent(codigoPersona)}/pdf`,
    { responseType: 'blob' }
  )
}

export async function approveCarnetPhoto(requestId: string): Promise<CarnetPhotoResponse> {
  return request<CarnetPhotoResponse>(`/api/carnet/solicitudes/${encodeURIComponent(requestId)}/aprobar`, {
    method: 'POST',
  })
}

export async function rejectCarnetPhoto(requestId: string, observacion = ''): Promise<CarnetPhotoResponse> {
  return request<CarnetPhotoResponse>(`/api/carnet/solicitudes/${encodeURIComponent(requestId)}/rechazar`, {
    method: 'POST',
    body: { observacion },
  })
}

export async function fetchTeamsCatalog(): Promise<TeamsCatalogResponse> {
  return request<TeamsCatalogResponse>('/api/teams/catalog')
}

export async function fetchMyTeamsCatalog(): Promise<TeamsCatalogResponse> {
  return request<TeamsCatalogResponse>('/api/teams/mine/catalog')
}

export async function fetchTeamParticipants(teamId: string): Promise<TeamCollectionResponse<TeamParticipant>> {
  return request<TeamCollectionResponse<TeamParticipant>>(
    `/api/teams/${encodeURIComponent(teamId)}/participants`
  )
}

export async function fetchTeamCourses(teamId: string): Promise<TeamCollectionResponse<TeamCourse>> {
  return request<TeamCollectionResponse<TeamCourse>>(
    `/api/teams/${encodeURIComponent(teamId)}/courses`
  )
}

export async function fetchTeamRecordings(
  teamId: string,
  forceRefresh = false
): Promise<TeamCollectionResponse<TeamRecording>> {
  return request<TeamCollectionResponse<TeamRecording>>(
    `/api/teams/${encodeURIComponent(teamId)}/recordings?force_refresh=${forceRefresh}`
  )
}

export async function fetchInstitutionalEmailStudents(params: {
  cedula?: string
  page?: number
  pageSize?: number
} = {}): Promise<InstitutionalEmailStudentsResponse> {
  const search = new URLSearchParams({
    cedula: params.cedula || '',
    page: String(params.page || 1),
    page_size: String(params.pageSize || 25),
  })
  return request<InstitutionalEmailStudentsResponse>(`/api/institutional-email/students?${search.toString()}`)
}

export async function downloadInstitutionalEmailTemplate(): Promise<Blob> {
  return request<Blob>('/api/institutional-email/template', { responseType: 'blob' })
}

export async function analyzeInstitutionalEmailWorkbook(file: File): Promise<InstitutionalEmailAnalysisResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<InstitutionalEmailAnalysisResponse>('/api/institutional-email/analyze', {
    method: 'POST',
    body: formData,
  })
}

export async function applyInstitutionalEmailWorkbook(file: File): Promise<InstitutionalEmailApplyResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<InstitutionalEmailApplyResponse>('/api/institutional-email/apply', {
    method: 'POST',
    body: formData,
  })
}

export async function updateInstitutionalEmailStudent(
  cedula: string,
  payload: { correo_intec: string; password: string },
): Promise<InstitutionalEmailUpdateResponse> {
  return request<InstitutionalEmailUpdateResponse>(`/api/institutional-email/students/${encodeURIComponent(cedula)}`, {
    method: 'PUT',
    body: payload,
  })
}

export async function fetchMyTeamRecordings(
  teamId: string,
  forceRefresh = false
): Promise<TeamCollectionResponse<TeamRecording>> {
  return request<TeamCollectionResponse<TeamRecording>>(
    `/api/teams/mine/${encodeURIComponent(teamId)}/recordings?force_refresh=${forceRefresh}`
  )
}

export async function fetchTeamAttendance(teamId: string): Promise<TeamCollectionResponse<TeamAttendance>> {
  return request<TeamCollectionResponse<TeamAttendance>>(
    `/api/teams/${encodeURIComponent(teamId)}/attendance`
  )
}

export async function fetchTeamMessages(teamId: string): Promise<TeamCollectionResponse<TeamMessage>> {
  return request<TeamCollectionResponse<TeamMessage>>(
    `/api/teams/${encodeURIComponent(teamId)}/messages`
  )
}

export async function fetchTeamStatus(teamId: string): Promise<TeamCallStatus> {
  return request<TeamCallStatus>(`/api/teams/${encodeURIComponent(teamId)}/status`)
}

export async function inviteMissingParticipants(teamId: string): Promise<TeamInviteMissingResponse> {
  return request<TeamInviteMissingResponse>(`/api/teams/${encodeURIComponent(teamId)}/call/invite-missing`, {
    method: 'POST',
  })
}

export async function enrollUserInTeam(userId: string, teamId: string): Promise<TeamsActionResponse> {
  return request<TeamsActionResponse>('/api/teams/enroll', {
    method: 'POST',
    body: { user_id: userId, team_id: teamId },
  })
}

export async function createClassroom(payload: TeamCreateAndEnrollPayload): Promise<TeamsActionResponse> {
  return request<TeamsActionResponse>('/api/teams/create-and-enroll', {
    method: 'POST',
    body: payload,
  })
}

export async function previewMoodleTeamsEnrollment(
  courseId: number,
  refresh = false,
  teamDisplayName?: string,
): Promise<MoodleTeamsPreviewResponse> {
  return request<MoodleTeamsPreviewResponse>('/api/teams/moodle-course/preview', {
    method: 'POST',
    body: {
      course_id: courseId,
      refresh,
      team_display_name: teamDisplayName?.trim() || undefined,
    },
  })
}

export async function enrollMoodleCourseInTeams(
  courseId: number,
  selectedMoodleUserIds: number[],
  teamDisplayName: string,
): Promise<MoodleTeamsEnrollmentResponse> {
  return request<MoodleTeamsEnrollmentResponse>('/api/teams/moodle-course/enroll', {
    method: 'POST',
    body: {
      course_id: courseId,
      refresh: true,
      selected_moodle_user_ids: selectedMoodleUserIds,
      team_display_name: teamDisplayName.trim(),
    },
  })
}

export async function previewTeamMassEnrollment(
  payload: TeamMassEnrollmentRequestPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/mass-enrollment/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function executeTeamMassEnrollment(
  payload: TeamMassEnrollmentRequestPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/mass-enrollment/execute', {
    method: 'POST',
    body: payload,
  })
}

export async function searchTeamEnrollmentGroups(
  payload: TeamEnrollmentGroupSearchPayload
): Promise<TeamEnrollmentGroupSearchResponse> {
  return request<TeamEnrollmentGroupSearchResponse>('/api/teams/enrollment/search-groups', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchTeamEnrollmentFilterOptions(
  payload: TeamEnrollmentFilterOptionsPayload
): Promise<TeamEnrollmentFilterOptionsResponse> {
  return request<TeamEnrollmentFilterOptionsResponse>('/api/teams/enrollment/filter-options', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchTeamEnrollmentGroupStudents(
  payload: TeamEnrollmentGroupStudentsPayload
): Promise<TeamEnrollmentGroupStudentsResponse> {
  return request<TeamEnrollmentGroupStudentsResponse>('/api/teams/enrollment/group-students', {
    method: 'POST',
    body: payload,
  })
}

export async function previewSelectedTeamEnrollment(
  payload: TeamEnrollmentSelectionPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/selected/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function executeSelectedTeamEnrollment(
  payload: TeamEnrollmentSelectionPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/selected/execute', {
    method: 'POST',
    body: payload,
  })
}

export async function searchIndividualTeamEnrollmentStudents(
  payload: TeamIndividualStudentSearchPayload
): Promise<TeamIndividualStudentSearchResponse> {
  return request<TeamIndividualStudentSearchResponse>('/api/teams/enrollment/individual/search-students', {
    method: 'POST',
    body: payload,
  })
}

export async function previewIndividualTeamEnrollment(
  payload: TeamIndividualEnrollmentPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/individual/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function executeIndividualTeamEnrollment(
  payload: TeamIndividualEnrollmentPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/individual/execute', {
    method: 'POST',
    body: payload,
  })
}

export async function previewManualTeamEnrollment(
  payload: TeamManualEmailEnrollmentPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/manual/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function executeManualTeamEnrollment(
  payload: TeamManualEmailEnrollmentPayload
): Promise<TeamMassEnrollmentResponse> {
  return request<TeamMassEnrollmentResponse>('/api/teams/enrollment/manual/execute', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchMatriculaSummary(): Promise<MatriculaSummaryResponse> {
  return request<MatriculaSummaryResponse>('/api/students/matricula-summary', { cache: 'no-store' })
}

export async function fetchDashboardMatricula(): Promise<DashboardMatriculaResponse> {
  return request<DashboardMatriculaResponse>('/api/students/dashboard-matricula', { cache: 'no-store' })
}

export async function fetchAcademicSystemIntegrationStatus(): Promise<AcademicSystemIntegrationResponse> {
  return request<AcademicSystemIntegrationResponse>('/api/academic-system/integration-status', { cache: 'no-store' })
}

export async function fetchDashboardMatriculaTrendStudents(
  anio: number,
  mes: number,
  limit: number = 10000
): Promise<DashboardMatriculaTrendStudentsResponse> {
  const params = new URLSearchParams({
    anio: String(anio),
    mes: String(mes),
    limit: String(limit),
  })
  return request<DashboardMatriculaTrendStudentsResponse>(
    `/api/students/dashboard-matricula/students?${params.toString()}`
  )
}

export async function fetchDashboardAdmissionsStudents(params: {
  estado?: string
  codigo_periodo?: string
  limit?: number
}): Promise<AdmissionsDashboardStudentsResponse> {
  const query = new URLSearchParams({
    estado: params.estado || 'ALL',
    limit: String(params.limit ?? 10000),
  })
  if (params.codigo_periodo) query.set('codigo_periodo', params.codigo_periodo)
  return request<AdmissionsDashboardStudentsResponse>(
    `/api/students/dashboard-matricula/admisiones-students?${query.toString()}`
  )
}

export async function fetchMatriculaCareerStateSummary(): Promise<MatriculaCareerStateSummaryResponse> {
  return request<MatriculaCareerStateSummaryResponse>('/api/students/matricula-career-state-summary', {
    cache: 'no-store',
  })
}

export async function fetchMatriculaCareerStateStudents(params: {
  cod_anio_basica?: string
  nombre_carrera?: string
  escuela?: string
  estado_codigo?: string
  tipo_matricula?: string
}): Promise<MatriculaCareerStateStudentsResponse> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value)
  }
  return request<MatriculaCareerStateStudentsResponse>(
    `/api/students/matricula-career-state-students?${query.toString()}`,
    { cache: 'no-store' }
  )
}

export async function fetchMatriculaPeriodSummary(): Promise<MatriculaPeriodSummaryResponse> {
  return request<MatriculaPeriodSummaryResponse>('/api/students/matricula-period-summary')
}

export async function fetchMatriculaMovementSummary(): Promise<MatriculaPeriodSummaryResponse> {
  return request<MatriculaPeriodSummaryResponse>('/api/students/matricula-movement-summary')
}

export async function fetchMatriculaList(
  tipo: MatriculaTipo | 'ALL' | 'RH',
  estado: string,
  limit: number,
  anioPeriodo?: number | null,
  puntoMatricula?: 'PRIMERA' | 'ULTIMA' | 'BOTH',
  fuente?: 'CNE'
): Promise<MatriculaListResponse> {
  const params = new URLSearchParams({ limit: String(limit) })

  if (tipo !== 'ALL') {
    params.set('tipo_matricula', tipo)
  }

  if (estado) {
    params.set('estado_codigo', estado)
  }

  if (anioPeriodo !== undefined && anioPeriodo !== null) {
    params.set('anio_periodo', String(anioPeriodo))
  }

  if (puntoMatricula) {
    params.set('punto_matricula', puntoMatricula)
  }

  if (fuente) {
    params.set('fuente', fuente)
  }

  return request<MatriculaListResponse>(
    `/api/students/matricula-list?${params.toString()}`,
    fuente ? { cache: 'no-store' } : {}
  )
}

export async function fetchIngresoVentas(limit: number = 5000): Promise<IngresoVentasResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  return request<IngresoVentasResponse>(`/api/students/ingreso-ventas?${params.toString()}`)
}

function buildLegacyReportParams(filters: LegacyReportFilters = {}): URLSearchParams {
  const params = new URLSearchParams({
    report_key: filters.reportKey || 'matriculados',
    limit: String(filters.limit ?? 500),
  })

  if (filters.periodo) {
    params.set('periodo', filters.periodo)
  }
  if (filters.carrera) {
    params.set('carrera', filters.carrera)
  }
  if (filters.estado) {
    params.set('estado', filters.estado)
  }
  if (filters.anio) {
    params.set('anio', filters.anio)
  }
  if (filters.genero) {
    params.set('genero', filters.genero)
  }
  if (filters.buscar) {
    params.set('buscar', filters.buscar)
  }

  return params
}

export async function fetchLegacyReportsCatalog(): Promise<LegacyReportsCatalogResponse> {
  return request<LegacyReportsCatalogResponse>('/api/students/reporteria-integral/catalog')
}

export async function fetchModernizedLegacyReportsCatalog(): Promise<ModernizedLegacyReportsCatalogResponse> {
  return request<ModernizedLegacyReportsCatalogResponse>('/api/students/reporteria-integral/modern-catalog')
}

export async function fetchLegacyCrystalReportsCatalog(): Promise<LegacyCrystalCatalogResponse> {
  return fetchModernizedLegacyReportsCatalog()
}

export async function fetchLegacyReport(filters: LegacyReportFilters = {}): Promise<LegacyReportResponse> {
  const params = buildLegacyReportParams(filters)
  return request<LegacyReportResponse>(`/api/students/reporteria-integral?${params.toString()}`, {
    cache: 'no-store',
  })
}

export async function fetchActiveLegacyGradeStudents(): Promise<LegacyActiveGradeStudentsResponse> {
  return request<LegacyActiveGradeStudentsResponse>('/api/students/reporteria-integral/active-grade-students', {
    cache: 'no-store',
  })
}

export async function fetchLegacyStudentGrades(
  codigoEstud: string,
  carrera?: string,
  tipoMatricula?: string,
): Promise<LegacyReportResponse> {
  const params = new URLSearchParams()
  if (carrera) params.set('carrera', carrera)
  if (tipoMatricula) params.set('tipo_matricula', tipoMatricula)
  const query = params.toString()
  return request<LegacyReportResponse>(
    `/api/students/reporteria-integral/active-grade-students/${encodeURIComponent(codigoEstud)}/grades${query ? `?${query}` : ''}`,
    { cache: 'no-store' },
  )
}

export async function updateLegacyStudentGrade(
  payload: LegacyGradeUpdatePayload,
): Promise<LegacyGradeUpdateResponse> {
  return request<LegacyGradeUpdateResponse>('/api/students/reporteria-integral/grades', {
    method: 'PUT',
    body: payload,
  })
}

export async function downloadLegacyReportWorkbook(filters: LegacyReportFilters = {}): Promise<Blob> {
  const params = buildLegacyReportParams({ ...filters, limit: filters.limit ?? 5000 })
  const response = await fetch(`/api/students/reporteria-integral/export?${params.toString()}`, {
    credentials: 'include',
    cache: 'no-store',
  })
  const contentType = response.headers.get('Content-Type') || ''

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  if (!contentType.includes('spreadsheet') && !contentType.includes('octet-stream')) {
    const payload = await readResponsePayload(response)
    throw new ApiError(typeof payload === 'string' ? payload : 'Respuesta inválida al descargar el archivo de Excel.', response.status)
  }

  return response.blob()
}

export async function fetchSisAcademicoCatalog(): Promise<SisAcademicoCatalogResponse> {
  return request<SisAcademicoCatalogResponse>('/api/students/sisacademico/catalog')
}

export async function fetchSisAcademicoV1Modules(): Promise<SisAcademicoV1ModulesResponse> {
  return request<SisAcademicoV1ModulesResponse>('/api/students/sisacademico/legacy-v1/modules')
}

export async function fetchSisAcademicoV1Artifacts(): Promise<SisAcademicoV1ArtifactsResponse> {
  return request<SisAcademicoV1ArtifactsResponse>('/api/students/sisacademico/legacy-v1/artifacts')
}

export async function fetchSisAcademicoRows(
  sectionKey: string,
  query: string = '',
  options: { limit?: number; periodo?: string } = {}
): Promise<SisAcademicoListResponse> {
  const params = new URLSearchParams()
  if (typeof options.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0) {
    params.set('limit', String(options.limit))
  }
  if (options.periodo) {
    params.set('periodo', options.periodo)
  }
  if (query) {
    params.set('query', query)
  }
  const queryString = params.toString()
  return request<SisAcademicoListResponse>(
    `/api/students/sisacademico/${encodeURIComponent(sectionKey)}${queryString ? `?${queryString}` : ''}`
  )
}

export async function fetchSisAcademicoRecord(
  sectionKey: string,
  recordKey: string
): Promise<SisAcademicoRecordResponse> {
  return request<SisAcademicoRecordResponse>(
    `/api/students/sisacademico/${encodeURIComponent(sectionKey)}/${encodeURIComponent(recordKey)}`
  )
}

export async function updateSisAcademicoRecord(
  sectionKey: string,
  recordKey: string,
  values: Record<string, unknown>
): Promise<SisAcademicoSaveResponse> {
  return request<SisAcademicoSaveResponse>(
    `/api/students/sisacademico/${encodeURIComponent(sectionKey)}/${encodeURIComponent(recordKey)}`,
    {
      method: 'PUT',
      body: { values },
    }
  )
}

export async function createSisAcademicoRecord(
  sectionKey: string,
  values: Record<string, unknown>
): Promise<SisAcademicoSaveResponse> {
  return request<SisAcademicoSaveResponse>(`/api/students/sisacademico/${encodeURIComponent(sectionKey)}`, {
    method: 'POST',
    body: { values },
  })
}

export async function fetchCertificadosCatalog(): Promise<CertificadosCatalogResponse> {
  return request<CertificadosCatalogResponse>('/api/certificados/catalog')
}

export async function fetchFechaGradoCatalog(periodo = ''): Promise<FechaGradoCatalogResponse> {
  const params = new URLSearchParams()
  if (periodo) params.set('periodo', periodo)
  const query = params.toString()
  return request<FechaGradoCatalogResponse>(`/api/students/fecha-grado/catalog${query ? `?${query}` : ''}`)
}

export async function fetchFechaGradoStudents(filters: {
  periodo: string
  carrera?: string
  busqueda?: string
  limit?: number
}): Promise<FechaGradoStudentsResponse> {
  const params = new URLSearchParams({ periodo: filters.periodo })
  if (filters.carrera) params.set('carrera', filters.carrera)
  if (filters.busqueda) params.set('busqueda', filters.busqueda)
  if (filters.limit) params.set('limit', String(filters.limit))
  return request<FechaGradoStudentsResponse>(`/api/students/fecha-grado/estudiantes?${params.toString()}`)
}

export async function saveFechaGrado(payload: FechaGradoSavePayload): Promise<FechaGradoSaveResponse> {
  return request<FechaGradoSaveResponse>('/api/students/fecha-grado/guardar', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function downloadFechaGradoTemplate(): Promise<Blob> {
  return request<Blob>('/api/students/fecha-grado/plantilla', {
    responseType: 'blob',
  })
}

export async function importFechaGradoExcel(file: File): Promise<FechaGradoImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<FechaGradoImportResponse>('/api/students/fecha-grado/importar', {
    method: 'POST',
    body: formData,
  })
}

export async function analyzeFechaGradoExcel(file: File): Promise<FechaGradoImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<FechaGradoImportResponse>('/api/students/fecha-grado/senescyt/analizar', {
    method: 'POST',
    body: formData,
  })
}

export async function analyzeFechaGradoPdfs(files: File[]): Promise<FechaGradoImportResponse> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  return request<FechaGradoImportResponse>('/api/students/fecha-grado/senescyt/pdf/analizar', {
    method: 'POST',
    body: formData,
  })
}

export async function importFechaGradoPdfs(files: File[]): Promise<FechaGradoImportResponse> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  return request<FechaGradoImportResponse>('/api/students/fecha-grado/senescyt/pdf/importar', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchFechaGradoVerification(filters: {
  estado?: string
  page?: number
  pageSize?: number
}): Promise<FechaGradoVerificationResponse> {
  const params = new URLSearchParams()
  if (filters.estado) params.set('estado', filters.estado)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.pageSize) params.set('page_size', String(filters.pageSize))
  const query = params.toString()
  return request<FechaGradoVerificationResponse>(`/api/students/fecha-grado/verificacion${query ? `?${query}` : ''}`)
}

export async function fetchCertificadosStudents(filters: {
  tipoBeca?: string
  periodo?: string
  busqueda?: string
  cedulas?: string
  matriculaScope?: string
  semestre?: string
  limit?: number
}): Promise<CertificadosStudentsResponse> {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 500) })
  if (filters.tipoBeca) params.set('tipo_beca', filters.tipoBeca)
  if (filters.periodo) params.set('periodo', filters.periodo)
  if (filters.busqueda) params.set('busqueda', filters.busqueda)
  if (filters.cedulas) params.set('cedulas', filters.cedulas)
  if (filters.matriculaScope) params.set('matricula_scope', filters.matriculaScope)
  if (filters.semestre) params.set('semestre', filters.semestre)
  return request<CertificadosStudentsResponse>(`/api/certificados/estudiantes?${params.toString()}`)
}

export async function downloadCertificadosZip(payload: CertificadosGeneratePayload): Promise<Blob> {
  const response = await fetch('/api/certificados/generar', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadCertificadosPdf(payload: CertificadosGeneratePayload): Promise<Blob> {
  const response = await fetch('/api/certificados/generar-pdf', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadCertificadosExcel(payload: CertificadosGeneratePayload): Promise<Blob> {
  const response = await fetch('/api/certificados/exportar-excel', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadMatriculaExcelTemplate(): Promise<Blob> {
  const response = await fetch(`/api/certificados/matricula-excel/plantilla?v=${Date.now()}`, {
    credentials: 'include',
    cache: 'no-store',
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function generateMatriculaPdfFromExcel(periodo: string, file: File): Promise<Blob> {
  const formData = new FormData()
  formData.set('periodo', periodo)
  formData.set('file', file)

  const response = await fetch('/api/certificados/matricula-excel/generar', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function previewCertificadoPdf(params: {
  codestud: string
  periodo: string
  proximoPeriodo?: string
  codAnioBasica?: string
  periodoMatricula?: string
  semestre?: string
  tipo?: 'matricula' | 'promocion'
}): Promise<Blob> {
  const query = new URLSearchParams({
    periodo: params.periodo,
    tipo: params.tipo || 'matricula',
  })
  if (params.proximoPeriodo) query.set('proximo_periodo', params.proximoPeriodo)
  if (params.codAnioBasica) query.set('cod_anio_basica', params.codAnioBasica)
  if (params.periodoMatricula) query.set('periodo_matricula', params.periodoMatricula)
  if (params.semestre) query.set('semestre', params.semestre)

  const response = await fetch(`/api/certificados/${encodeURIComponent(params.codestud)}/preview?${query.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function analyzeCertificateRenameFiles(files: File[]): Promise<CertificateRenameResponse> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  return request<CertificateRenameResponse>('/api/certificados/renombrar/analizar', {
    method: 'POST',
    body: formData,
  })
}

export async function downloadCertificateRenameZip(files: File[]): Promise<Blob> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  const response = await fetch('/api/certificados/renombrar/descargar', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadCertificateRenameTar(files: File[]): Promise<Blob> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  const response = await fetch('/api/certificados/renombrar/descargar-tar', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function saveCertificateRenameLocal(files: File[]): Promise<CertificateRenameLocalSaveResponse> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  return request<CertificateRenameLocalSaveResponse>('/api/certificados/renombrar/guardar-local', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchCredentialCatalog(): Promise<CredentialCatalogResponse> {
  return request<CredentialCatalogResponse>('/api/admin/credenciales/catalog')
}

export async function fetchCredentialRows(codCurso = '', limit = 100): Promise<CredentialListResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (codCurso) params.set('cod_curso', codCurso)
  return request<CredentialListResponse>(`/api/admin/credenciales?${params.toString()}`)
}

export async function saveCredentialBulk(payload: CredentialBulkPayload): Promise<CredentialBulkResponse> {
  return request<CredentialBulkResponse>('/api/admin/credenciales/bulk', {
    method: 'POST',
    body: payload,
  })
}

export async function resolveMassEmailRecipients(
  payload: MassEmailResolvePayload
): Promise<MassEmailResolveResponse> {
  return request<MassEmailResolveResponse>('/api/admin/correos-masivos/resolver', {
    method: 'POST',
    body: payload,
  })
}

export async function searchMassEmailUsers(query: string, limit = 50): Promise<MassEmailSearchResponse> {
  const params = new URLSearchParams({
    query,
    limit: String(limit),
  })
  return request<MassEmailSearchResponse>(`/api/admin/correos-masivos/buscar-usuarios?${params.toString()}`)
}

export async function analyzeMassEmailExcel(
  file: File,
  options: {
    includePersonal?: boolean
    includeIntec?: boolean
    includeDocentes?: boolean
    includeAdministrativos?: boolean
  } = {}
): Promise<MassEmailExcelResponse> {
  const formData = new FormData()
  formData.set('file', file)
  formData.set('include_personal', options.includePersonal === false ? 'false' : 'true')
  formData.set('include_intec', options.includeIntec === false ? 'false' : 'true')
  formData.set('include_docentes', options.includeDocentes === false ? 'false' : 'true')
  formData.set('include_administrativos', options.includeAdministrativos === false ? 'false' : 'true')

  return request<MassEmailExcelResponse>('/api/admin/correos-masivos/excel/analizar', {
    method: 'POST',
    body: formData,
  })
}

export async function sendMassEmail(payload: {
  subject: string
  body: string
  recipients: MassEmailRecipient[]
  manualEmails?: string
  ccEmails?: string
  matchAttachmentsByCedula?: boolean
  sendMode?: 'individual' | 'single'
  files?: File[]
  commonFiles?: File[]
  studentFiles?: File[]
  attachmentAssignments?: Record<string, string>
}): Promise<MassEmailSendResponse> {
  const formData = new FormData()
  formData.set('subject', payload.subject)
  formData.set('body', payload.body)
  formData.set('recipients_json', JSON.stringify(payload.recipients))
  formData.set('manual_emails', payload.manualEmails || '')
  formData.set('cc_emails', payload.ccEmails || '')
  formData.set('match_attachments_by_cedula', payload.matchAttachmentsByCedula ? 'true' : 'false')
  formData.set('send_mode', payload.sendMode || 'individual')
  formData.set('attachment_assignments_json', JSON.stringify(payload.attachmentAssignments || {}))
  ;(payload.files || []).forEach((file) => formData.append('files', file))
  ;(payload.commonFiles || []).forEach((file) => formData.append('common_files', file))
  ;(payload.studentFiles || []).forEach((file) => formData.append('student_files', file))

  return request<MassEmailSendResponse>('/api/admin/correos-masivos/enviar', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchPreinscriptionCatalog(): Promise<PreinscriptionCatalogResponse> {
  return request<PreinscriptionCatalogResponse>('/api/students/preinscripcion/catalog')
}

export async function fetchPreinscriptions(
  filters: {
    query?: string
    codigoPeriodo?: string
    codAnioBasica?: string
    documentos?: string
    limit?: number
  } = {}
): Promise<PreinscriptionListResponse> {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 500) })
  if (filters.query) {
    params.set('query', filters.query)
  }
  if (filters.codigoPeriodo) {
    params.set('codigo_periodo', filters.codigoPeriodo)
  }
  if (filters.codAnioBasica) {
    params.set('cod_anio_basica', filters.codAnioBasica)
  }
  if (filters.documentos) {
    params.set('documentos', filters.documentos)
  }
  return request<PreinscriptionListResponse>(`/api/students/preinscripcion?${params.toString()}`)
}

export async function createPreinscription(
  payload: PreinscriptionCreatePayload
): Promise<PreinscriptionCreateResponse> {
  return request<PreinscriptionCreateResponse>('/api/students/preinscripcion', {
    method: 'POST',
    body: payload,
  })
}

export async function validatePreinscriptionCedula(
  cedula: string,
  codigoPeriodo = ''
): Promise<PreinscriptionCedulaValidationResponse> {
  const params = new URLSearchParams({ cedula })
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  return request<PreinscriptionCedulaValidationResponse>(
    `/api/students/preinscripcion/validar-cedula?${params.toString()}`
  )
}

export async function updatePreinscriptionDocuments(
  num: string,
  payload: PreinscriptionDocumentsPayload
): Promise<PreinscriptionDocumentsSaveResponse> {
  return request<PreinscriptionDocumentsSaveResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/documentos`,
    {
      method: 'PUT',
      body: payload,
    }
  )
}

export async function updatePreinscriptionFollowup(
  num: string,
  payload: PreinscriptionFollowupPayload
): Promise<PreinscriptionFollowupSaveResponse> {
  return request<PreinscriptionFollowupSaveResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/seguimiento`,
    {
      method: 'PUT',
      body: payload,
    }
  )
}

export async function registerPreinscriptionCabecera(
  num: string,
  payload: PreinscriptionCabeceraPayload
): Promise<PreinscriptionCabeceraSaveResponse> {
  return request<PreinscriptionCabeceraSaveResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/cabecera`,
    {
      method: 'POST',
      body: payload,
    }
  )
}

export async function fetchPreinscriptionScholarshipStatus(
  num: string
): Promise<PreinscriptionScholarshipStatus> {
  return request<PreinscriptionScholarshipStatus>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/beca`
  )
}

export async function approvePreinscriptionScholarship(
  num: string
): Promise<PreinscriptionScholarshipStatus> {
  return request<PreinscriptionScholarshipStatus>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/beca/aprobar`,
    { method: 'POST' }
  )
}

export async function fetchPendingPreinscriptionScholarships(
  query = ''
): Promise<PreinscriptionScholarshipApprovalListResponse> {
  const params = new URLSearchParams({ limit: '1000' })
  if (query.trim()) params.set('query', query.trim())
  return request<PreinscriptionScholarshipApprovalListResponse>(
    `/api/students/preinscripcion/becas/pendientes?${params.toString()}`
  )
}

export async function fetchScholarshipBeneficiaries(
  query = ''
): Promise<ScholarshipBeneficiaryListResponse> {
  const params = new URLSearchParams({ limit: '1000' })
  if (query.trim()) params.set('query', query.trim())
  return request<ScholarshipBeneficiaryListResponse>(
    `/api/students/preinscripcion/becas/beneficiarios?${params.toString()}`
  )
}

export async function fetchMoodleCourseEvaluations(
  courseId: number,
  refresh = false,
): Promise<MoodleCourseEvaluationsResponse> {
  const params = new URLSearchParams({ refresh: refresh ? 'true' : 'false' })
  return request<MoodleCourseEvaluationsResponse>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/evaluations?${params.toString()}`,
    { cache: 'no-store' },
  )
}

export async function updateMoodleCourseEvaluationDates(
  courseId: number,
  updates: MoodleEvaluationDateUpdate[],
): Promise<MoodleEvaluationDatesUpdateResponse> {
  return request<MoodleEvaluationDatesUpdateResponse>(
    `/api/moodle/courses/${encodeURIComponent(String(courseId))}/evaluation-dates`,
    {
      method: 'PATCH',
      body: { updates },
    },
  )
}

export async function fetchScholarshipContractCandidates(
  query = '',
  scholarshipType = '',
  academicPeriod = ''
): Promise<ScholarshipContractCandidateListResponse> {
  const params = new URLSearchParams()
  if (query.trim()) params.set('query', query.trim())
  if (scholarshipType.trim()) params.set('tipo_beca', scholarshipType.trim())
  if (academicPeriod.trim()) params.set('codigo_periodo', academicPeriod.trim())
  return request<ScholarshipContractCandidateListResponse>(
    `/api/students/preinscripcion/becas/contratos/candidatos?${params.toString()}`
  )
}

export async function fetchScholarshipContractTemplate(): Promise<ScholarshipContractTemplate> {
  return request<ScholarshipContractTemplate>(
    '/api/students/preinscripcion/becas/contratos/plantilla'
  )
}

export async function generateScholarshipContracts(
  becaIds: number[],
  academicPeriod: string,
  contractFormat: ScholarshipContractFormat,
  template: ScholarshipContractTemplate,
): Promise<Blob> {
  return request<Blob>('/api/students/preinscripcion/becas/contratos/generar', {
    method: 'POST',
    body: {
      beca_ids: becaIds,
      codigo_periodo: academicPeriod,
      formato_contrato: contractFormat,
      plantilla: template,
    },
    responseType: 'blob',
  })
}

export async function fetchScholarshipContractHistory(
  query = ''
): Promise<ScholarshipContractHistoryResponse> {
  const params = new URLSearchParams({ limit: '500' })
  if (query.trim()) params.set('query', query.trim())
  return request<ScholarshipContractHistoryResponse>(
    `/api/students/preinscripcion/becas/contratos/historial?${params.toString()}`
  )
}

export async function downloadScholarshipContract(contractId: number): Promise<Blob> {
  return request<Blob>(
    `/api/students/preinscripcion/becas/contratos/${encodeURIComponent(String(contractId))}/descargar`,
    { responseType: 'blob' }
  )
}

export async function uploadScholarshipContractToExpedient(
  contractId: number,
  file: File
): Promise<ScholarshipContractUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<ScholarshipContractUploadResponse>(
    `/api/students/preinscripcion/becas/contratos/${encodeURIComponent(String(contractId))}/expediente`,
    { method: 'POST', body: formData }
  )
}

export async function approvePreinscriptionScholarshipById(
  becaId: number
): Promise<PreinscriptionScholarshipStatus> {
  return request<PreinscriptionScholarshipStatus>(
    `/api/students/preinscripcion/becas/${encodeURIComponent(String(becaId))}/aprobar`,
    { method: 'POST' }
  )
}

export async function fetchScholarshipConfigurations(): Promise<ScholarshipConfigurationListResponse> {
  return request<ScholarshipConfigurationListResponse>('/api/students/preinscripcion/becas/configuracion')
}

export async function createScholarshipConfiguration(
  payload: ScholarshipConfigurationPayload
): Promise<ScholarshipConfigurationSaveResponse> {
  return request<ScholarshipConfigurationSaveResponse>('/api/students/preinscripcion/becas/configuracion', {
    method: 'POST',
    body: payload,
  })
}

export async function updateScholarshipConfiguration(
  configurationId: number,
  payload: ScholarshipConfigurationPayload
): Promise<ScholarshipConfigurationSaveResponse> {
  return request<ScholarshipConfigurationSaveResponse>(
    `/api/students/preinscripcion/becas/configuracion/${encodeURIComponent(String(configurationId))}`,
    { method: 'PUT', body: payload }
  )
}

export async function uploadPreinscriptionDocument(
  num: string,
  field: string,
  file: File
): Promise<PreinscriptionDocumentUploadResponse> {
  const formData = new FormData()
  formData.set('file', file)
  return request<PreinscriptionDocumentUploadResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/documentos/${encodeURIComponent(field)}/upload`,
    {
      method: 'POST',
      body: formData,
    }
  )
}

export async function fetchPreinscriptionCarnetPhoto(num: string): Promise<PreinscriptionPhotoResponse> {
  return request<PreinscriptionPhotoResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/foto-carnet`
  )
}

export async function uploadPreinscriptionCarnetPhoto(
  num: string,
  file: File
): Promise<PreinscriptionPhotoResponse> {
  const formData = new FormData()
  formData.set('file', file)
  return request<PreinscriptionPhotoResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/foto-carnet/upload`,
    {
      method: 'POST',
      body: formData,
    }
  )
}

export async function approvePreinscriptionCarnetPhoto(
  num: string,
  requestId: string
): Promise<PreinscriptionPhotoResponse> {
  return request<PreinscriptionPhotoResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/foto-carnet/${encodeURIComponent(requestId)}/aprobar`,
    {
      method: 'POST',
    }
  )
}

export async function rejectPreinscriptionCarnetPhoto(
  num: string,
  requestId: string,
  observacion = ''
): Promise<PreinscriptionPhotoResponse> {
  return request<PreinscriptionPhotoResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/foto-carnet/${encodeURIComponent(requestId)}/rechazar`,
    {
      method: 'POST',
      body: { observacion },
    }
  )
}

export async function revertPreinscriptionProcess(num: string): Promise<PreinscriptionRevertResponse> {
  return request<PreinscriptionRevertResponse>(
    `/api/students/preinscripcion/${encodeURIComponent(num)}/revertir`,
    {
      method: 'DELETE',
    }
  )
}

export async function fetchAcademicEnrollmentCatalog(): Promise<AcademicEnrollmentCatalogResponse> {
  return request<AcademicEnrollmentCatalogResponse>('/api/students/matricula-acad/catalog')
}

export async function fetchAcademicEnrollmentCareers(
  codigoPeriodo: string = ''
): Promise<AcademicEnrollmentCareersResponse> {
  const params = new URLSearchParams()
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<AcademicEnrollmentCareersResponse>(`/api/students/matricula-acad/careers${suffix}`)
}

export async function searchAcademicEnrollmentStudents(
  query: string,
  limit: number = 20
): Promise<AcademicEnrollmentStudentSearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) })
  return request<AcademicEnrollmentStudentSearchResponse>(`/api/students/matricula-acad/students?${params.toString()}`)
}

export async function fetchAcademicEnrollmentCohort(
  codigoPeriodo: string,
  codAnioBasica: string = '',
  paralelo: string = ''
): Promise<AcademicEnrollmentCohortResponse> {
  const params = new URLSearchParams({ codigo_periodo: codigoPeriodo })
  if (codAnioBasica) {
    params.set('cod_anio_basica', codAnioBasica)
  }
  if (paralelo) {
    params.set('paralelo', paralelo)
  }
  return request<AcademicEnrollmentCohortResponse>(`/api/students/matricula-acad/cohort?${params.toString()}`)
}

export async function fetchAcademicEnrollmentDetail(
  codigoEstud: string,
  codAnioBasica?: string,
  codigoPeriodo?: string
): Promise<AcademicEnrollmentDetailResponse> {
  const params = new URLSearchParams()
  if (codAnioBasica) {
    params.set('cod_anio_basica', codAnioBasica)
  }
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<AcademicEnrollmentDetailResponse>(
    `/api/students/matricula-acad/students/${encodeURIComponent(codigoEstud)}${suffix}`
  )
}

export async function fetchAcademicEnrollmentPensum(
  codAnioBasica: string
): Promise<AcademicEnrollmentPensumResponse> {
  const params = new URLSearchParams({ cod_anio_basica: codAnioBasica })
  return request<AcademicEnrollmentPensumResponse>(`/api/students/matricula-acad/pensum?${params.toString()}`)
}

export async function fetchAcademicPrerequisiteRules(
  codAnioBasica?: string
): Promise<AcademicPrerequisiteRulesResponse> {
  const params = new URLSearchParams()
  if (codAnioBasica) params.set('cod_anio_basica', codAnioBasica)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<AcademicPrerequisiteRulesResponse>(`/api/students/matricula-acad/prerequisites${suffix}`)
}

export async function createAcademicPrerequisiteRule(
  payload: AcademicPrerequisiteRulePayload
): Promise<AcademicPrerequisiteRuleSaveResponse> {
  return request<AcademicPrerequisiteRuleSaveResponse>('/api/students/matricula-acad/prerequisites', {
    method: 'POST',
    body: payload,
  })
}

export async function updateAcademicPrerequisiteRule(
  ruleId: number,
  payload: AcademicPrerequisiteRulePayload
): Promise<AcademicPrerequisiteRuleSaveResponse> {
  return request<AcademicPrerequisiteRuleSaveResponse>(
    `/api/students/matricula-acad/prerequisites/${encodeURIComponent(String(ruleId))}`,
    { method: 'PUT', body: payload },
  )
}

export async function deleteAcademicPrerequisiteRule(
  ruleId: number
): Promise<AcademicPrerequisiteRuleSaveResponse> {
  return request<AcademicPrerequisiteRuleSaveResponse>(
    `/api/students/matricula-acad/prerequisites/${encodeURIComponent(String(ruleId))}`,
    { method: 'DELETE' },
  )
}

export async function previewAcademicEnrollment(
  payload: AcademicEnrollmentPayload
): Promise<AcademicEnrollmentPreviewResponse> {
  return request<AcademicEnrollmentPreviewResponse>('/api/students/matricula-acad/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function saveAcademicEnrollment(
  payload: AcademicEnrollmentPayload
): Promise<AcademicEnrollmentSaveResponse> {
  return request<AcademicEnrollmentSaveResponse>('/api/students/matricula-acad/save', {
    method: 'POST',
    body: payload,
  })
}

export async function previewBulkAcademicEnrollment(
  payload: AcademicBulkEnrollmentPayload
): Promise<AcademicBulkEnrollmentPreviewResponse> {
  return request<AcademicBulkEnrollmentPreviewResponse>('/api/students/matricula-acad/bulk/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function saveBulkAcademicEnrollment(
  payload: AcademicBulkEnrollmentPayload
): Promise<AcademicBulkEnrollmentSaveResponse> {
  return request<AcademicBulkEnrollmentSaveResponse>('/api/students/matricula-acad/bulk/save', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchAcademicPeriodChangeCatalog(): Promise<AcademicPeriodChangeCatalogResponse> {
  return request<AcademicPeriodChangeCatalogResponse>('/api/students/matricula-acad/period-change/catalog')
}

export async function previewAcademicPeriodChange(
  payload: AcademicPeriodChangePayload
): Promise<AcademicPeriodChangePreviewResponse> {
  return request<AcademicPeriodChangePreviewResponse>('/api/students/matricula-acad/period-change/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function applyAcademicPeriodChange(
  payload: AcademicPeriodChangePayload
): Promise<AcademicPeriodChangeApplyResponse> {
  return request<AcademicPeriodChangeApplyResponse>('/api/students/matricula-acad/period-change/apply', {
    method: 'POST',
    body: payload,
  })
}

export async function balanceAcademicEnrollmentParallels(
  payload: AcademicParallelBalancePayload
): Promise<AcademicParallelBalanceResponse> {
  return request<AcademicParallelBalanceResponse>('/api/students/matricula-acad/balance-paralelos', {
    method: 'POST',
    body: payload,
  })
}

export async function searchAcademicEnrollmentTeachers(
  query: string,
  limit: number = 20,
  validarUsuario: boolean = false
): Promise<AcademicTeacherSearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) })
  if (validarUsuario) {
    params.set('validar_usuario', 'true')
  }
  return request<AcademicTeacherSearchResponse>(`/api/students/matricula-acad/docentes?${params.toString()}`)
}

export async function fetchAcademicTeacherEnrollments(
  codAnioBasica: string | string[],
  codigoPeriodo: string,
  codigoMateria: string = '',
  paralelo: string = '',
  semestre: string = ''
): Promise<AcademicTeacherEnrollmentsResponse> {
  const params = new URLSearchParams({ codigo_periodo: codigoPeriodo })
  const careerCodes = Array.isArray(codAnioBasica) ? codAnioBasica : [codAnioBasica]
  for (const code of careerCodes.filter(Boolean)) {
    params.append('cod_anio_basica', code)
  }
  if (codigoMateria) {
    params.set('codigo_materia', codigoMateria)
  }
  if (paralelo) {
    params.set('paralelo', paralelo)
  }
  if (semestre) {
    params.set('semestre', semestre)
  }
  return request<AcademicTeacherEnrollmentsResponse>(`/api/students/matricula-acad/docentes/matriculas?${params.toString()}`)
}

export async function fetchAcademicTeacherParallels(
  codAnioBasica: string | string[],
  codigoPeriodo: string,
  codigoMateria: string = '',
  semestre: string = ''
): Promise<AcademicTeacherParallelOptionsResponse> {
  const params = new URLSearchParams({ codigo_periodo: codigoPeriodo })
  const careerCodes = Array.isArray(codAnioBasica) ? codAnioBasica : [codAnioBasica]
  for (const code of careerCodes.filter(Boolean)) {
    params.append('cod_anio_basica', code)
  }
  if (codigoMateria) {
    params.set('codigo_materia', codigoMateria)
  }
  if (semestre) {
    params.set('semestre', semestre)
  }
  return request<AcademicTeacherParallelOptionsResponse>(`/api/students/matricula-acad/docentes/paralelos?${params.toString()}`)
}

export async function fetchAcademicTeacherUniqueSubjects(params: {
  codigoPeriodo: string
  buscar?: string
  semestre?: string
  limite?: number
}): Promise<AcademicTeacherUniqueSubjectsResponse> {
  const query = new URLSearchParams({
    codigo_periodo: params.codigoPeriodo,
    limite: String(params.limite ?? 120),
  })
  if (params.buscar?.trim()) {
    query.set('buscar', params.buscar.trim())
  }
  if (params.semestre?.trim()) {
    query.set('semestre', params.semestre.trim())
  }
  return request<AcademicTeacherUniqueSubjectsResponse>(`/api/students/matricula-acad/docentes/materias-unicas?${query.toString()}`)
}

export async function fetchAcademicTeacherStudents(
  codigoDoc: string,
  codigoPeriodo: string | string[] = [],
  codAnioBasica: string | string[] = [],
  codigoMateria: string = '',
  paralelo: string = ''
): Promise<AcademicTeacherStudentsResponse> {
  const params = new URLSearchParams({ codigo_doc: codigoDoc })
  const periodCodes = Array.isArray(codigoPeriodo) ? codigoPeriodo : [codigoPeriodo]
  for (const code of periodCodes.filter(Boolean)) {
    params.append('codigo_periodo', code)
  }
  const careerCodes = Array.isArray(codAnioBasica) ? codAnioBasica : [codAnioBasica]
  for (const code of careerCodes.filter(Boolean)) {
    params.append('cod_anio_basica', code)
  }
  if (codigoMateria) {
    params.set('codigo_materia', codigoMateria)
  }
  if (paralelo) {
    params.set('paralelo', paralelo)
  }
  return request<AcademicTeacherStudentsResponse>(`/api/students/matricula-acad/docentes/estudiantes?${params.toString()}`)
}

export async function fetchAcademicTeacherParallelStudents(
  codigoPeriodo: string | string[],
  codigoMateria: string,
  paralelo: string,
  codAnioBasica: string | string[] = [],
  semestre: string = ''
): Promise<AcademicTeacherStudentsResponse> {
  const params = new URLSearchParams({ codigo_materia: codigoMateria, paralelo })
  const periodCodes = Array.isArray(codigoPeriodo) ? codigoPeriodo : [codigoPeriodo]
  for (const code of periodCodes.filter(Boolean)) {
    params.append('codigo_periodo', code)
  }
  const careerCodes = Array.isArray(codAnioBasica) ? codAnioBasica : [codAnioBasica]
  for (const code of careerCodes.filter(Boolean)) {
    params.append('cod_anio_basica', code)
  }
  if (semestre) {
    params.set('semestre', semestre)
  }
  return request<AcademicTeacherStudentsResponse>(`/api/students/matricula-acad/docentes/estudiantes-paralelo?${params.toString()}`)
}

export async function fetchPortalStudentRecord(approvedOnly: boolean = false): Promise<PortalStudentRecordResponse> {
  const params = new URLSearchParams()
  if (approvedOnly) {
    params.set('approved_only', 'true')
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<PortalStudentRecordResponse>(`/api/portal/student/record${suffix}`)
}

export async function downloadPortalStudentRecord(approvedOnly: boolean = false, codigoPeriodo: string = ''): Promise<Blob> {
  const params = new URLSearchParams()
  if (approvedOnly) {
    params.set('approved_only', 'true')
  }
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(`/api/portal/student/record/export${suffix}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadPortalStudentPdf(
  tipo: 'academica' | 'calificaciones',
  codigoPeriodo: string = ''
): Promise<Blob> {
  const params = new URLSearchParams({ tipo })
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  const response = await fetch(`/api/portal/student/record/export-pdf?${params.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function updateStudentStateWithDocument(
  recordKey: string,
  estado: string,
  detalle: string,
  documento: File
): Promise<SisAcademicoSaveResponse> {
  const formData = new FormData()
  formData.append('estado', estado)
  formData.append('detalle', detalle)
  formData.append('documento', documento)
  return request<SisAcademicoSaveResponse>(
    `/api/students/sisacademico/actualizacion_estudiantes/${encodeURIComponent(recordKey)}/cambio-estado-documentado`,
    {
      method: 'POST',
      body: formData,
    }
  )
}

export async function downloadPortalStudentSecretaryPdf(
  codigoPeriodo: string = '',
  tipo: 'calificaciones' | 'malla' = 'calificaciones',
): Promise<Blob> {
  const params = new URLSearchParams({ tipo })
  if (codigoPeriodo) {
    params.set('codigo_periodo', codigoPeriodo)
  }
  const response = await fetch(`/api/portal/student/record/export-secretaria-pdf?${params.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function fetchPortalTeacherCourses(): Promise<PortalTeacherCoursesResponse> {
  return request<PortalTeacherCoursesResponse>('/api/portal/teacher/courses')
}

export async function fetchPortalTeacherProfile(): Promise<PortalTeacherProfileResponse> {
  return request<PortalTeacherProfileResponse>('/api/portal/teacher/me', { cache: 'no-store' })
}

export async function fetchAdminGradeTeachers(params: {
  buscar?: string
  estado?: string
  limit?: number
} = {}): Promise<AdminGradeTeachersResponse> {
  const query = new URLSearchParams()
  if (params.buscar) query.set('buscar', params.buscar)
  if (params.estado) query.set('estado', params.estado)
  query.set('limit', String(params.limit ?? 1000))
  return request<AdminGradeTeachersResponse>(`/api/portal/admin/grades/teachers?${query.toString()}`, {
    cache: 'no-store',
  })
}

export async function fetchAdminGradeTeacherCourses(codigoDoc: string): Promise<PortalTeacherCoursesResponse> {
  return request<PortalTeacherCoursesResponse>(
    `/api/portal/admin/grades/teachers/${encodeURIComponent(codigoDoc)}/courses`,
    { cache: 'no-store' },
  )
}

export async function fetchAdminGradeTeacherStudents(params: {
  codigoDoc: string
  courses: AdminGradeCourseSelection[]
}): Promise<AdminGradeStudentsResponse> {
  return request<AdminGradeStudentsResponse>(
    `/api/portal/admin/grades/teachers/${encodeURIComponent(params.codigoDoc)}/students`,
    {
      method: 'POST',
      body: { courses: params.courses },
      cache: 'no-store',
    },
  )
}

export async function fetchPortalTeacherContracts(): Promise<PortalTeacherContractsResponse> {
  return request<PortalTeacherContractsResponse>('/api/portal/teacher/contracts', { cache: 'no-store' })
}

export async function analyzePortalTeacherContract(contrato: File): Promise<PortalTeacherContractAnalysis> {
  const formData = new FormData()
  formData.append('contrato', contrato)
  return request<PortalTeacherContractAnalysis>('/api/portal/teacher/contracts/analyze-document', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadPortalTeacherContract(params: {
  numeroContrato: string
  codAnioBasica: string
  codigoPeriodo: string
  codigoMateria: string
  paralelo: string
  codJornada?: number | null
  modalidadAcademica: 'REGULAR' | 'HOMOLOGACION'
  fechaInicio: string
  fechaFin: string
  horasPlanificadas: number
  valorHora: number
  valorTotal: number
  responsableContratacion?: string
  observacion?: string
  contrato: File
}): Promise<PortalTeacherContractDocumentSaveResponse> {
  const formData = new FormData()
  formData.append('numero_contrato', params.numeroContrato)
  formData.append('cod_anio_basica', params.codAnioBasica)
  formData.append('codigo_periodo', params.codigoPeriodo)
  formData.append('codigo_materia', params.codigoMateria)
  formData.append('paralelo', params.paralelo)
  if (params.codJornada != null) formData.append('cod_jornada', String(params.codJornada))
  formData.append('modalidad_academica', params.modalidadAcademica)
  formData.append('fecha_inicio', params.fechaInicio)
  formData.append('fecha_fin', params.fechaFin)
  formData.append('horas_planificadas', String(params.horasPlanificadas))
  formData.append('valor_hora', String(params.valorHora))
  formData.append('valor_total', String(params.valorTotal))
  formData.append('responsable_contratacion', params.responsableContratacion || '')
  formData.append('observacion', params.observacion || '')
  formData.append('contrato', params.contrato)
  return request<PortalTeacherContractDocumentSaveResponse>('/api/portal/teacher/contracts/document', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchPortalTeacherContractDocument(
  contractId: number,
  options: { version?: 'current' | 'original' | 'signed'; download?: boolean } = {},
): Promise<Blob> {
  const query = new URLSearchParams()
  query.set('version', options.version || 'current')
  if (options.download) query.set('download', 'true')
  return request<Blob>(`/api/portal/teacher/contracts/${contractId}/document?${query.toString()}`, {
    responseType: 'blob',
    cache: 'no-store',
  })
}

export async function signPortalTeacherContract(params: {
  contractId: number
  certificado: File
  contrasenaCertificado: string
  firmaMotivo: string
  firmaUbicacion: string
  firmaContacto?: string
}): Promise<Blob> {
  const formData = new FormData()
  formData.append('certificado', params.certificado)
  formData.append('contrasena_certificado', params.contrasenaCertificado)
  formData.append('firma_motivo', params.firmaMotivo)
  formData.append('firma_ubicacion', params.firmaUbicacion)
  formData.append('firma_contacto', params.firmaContacto || '')
  return request<Blob>(`/api/portal/teacher/contracts/${params.contractId}/sign`, {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function signPortalTeacherUploadedContract(params: {
  contrato: File
  certificado: File
  contrasenaCertificado: string
  firmaMotivo: string
  firmaUbicacion: string
  firmaContacto?: string
}): Promise<Blob> {
  const formData = new FormData()
  formData.append('contrato', params.contrato)
  formData.append('certificado', params.certificado)
  formData.append('contrasena_certificado', params.contrasenaCertificado)
  formData.append('firma_motivo', params.firmaMotivo)
  formData.append('firma_ubicacion', params.firmaUbicacion)
  formData.append('firma_contacto', params.firmaContacto || '')
  return request<Blob>('/api/portal/teacher/contracts/sign-uploaded', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function downloadPortalAcademicPlanningPdf(
  payload: PortalAcademicPlanningPayload,
): Promise<Blob> {
  return request<Blob>('/api/portal/teacher/academic-planning-pdf', {
    method: 'POST',
    body: payload,
    responseType: 'blob',
  })
}

export async function previewPortalAcademicPlanningPdf(
  payload: PortalAcademicPlanningPayload,
): Promise<Blob> {
  return request<Blob>('/api/portal/teacher/academic-planning-pdf?preview=true', {
    method: 'POST',
    body: payload,
    responseType: 'blob',
  })
}

export async function signPortalAcademicPlanningPdf(params: {
  payload: PortalAcademicPlanningPayload
  certificado: File
  contrasenaCertificado: string
  firmaMotivo: string
  firmaUbicacion: string
  firmaContacto?: string
}): Promise<Blob> {
  const formData = new FormData()
  formData.append('payload_json', JSON.stringify(params.payload))
  formData.append('certificado', params.certificado)
  formData.append('contrasena_certificado', params.contrasenaCertificado)
  formData.append('firma_motivo', params.firmaMotivo)
  formData.append('firma_ubicacion', params.firmaUbicacion)
  if (params.firmaContacto) formData.append('firma_contacto', params.firmaContacto)
  return request<Blob>('/api/portal/teacher/academic-planning-sign', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function fetchPortalTeacherStudents(params: {
  codigoPeriodo?: string
  codigoPeriodos?: string[]
  codAnioBasica?: string
  codJornada?: number | null
  codigoMateria: string
  paralelo: string
  buscar?: string
}): Promise<PortalTeacherStudentsResponse> {
  const query = new URLSearchParams({
    codigo_materia: params.codigoMateria,
    paralelo: params.paralelo,
  })
  if (params.codAnioBasica) {
    query.set('cod_anio_basica', params.codAnioBasica)
  }
  if (params.codJornada !== null && params.codJornada !== undefined) {
    query.set('cod_jornada', String(params.codJornada))
  }
  if (params.buscar?.trim()) {
    query.set('buscar', params.buscar.trim())
  }
  const periodos = params.codigoPeriodos?.length ? params.codigoPeriodos : params.codigoPeriodo ? [params.codigoPeriodo] : []
  for (const codigoPeriodo of periodos) {
    query.append('codigo_periodo', codigoPeriodo)
  }
  return request<PortalTeacherStudentsResponse>(`/api/portal/teacher/course-students?${query.toString()}`)
}

export async function fetchPortalTeacherSubjectStudents(params: {
  codigoMateria: string
  tipoPeriodo: 'R' | 'H'
  codigoPeriodos: string[]
}): Promise<PortalTeacherStudentsResponse> {
  const query = new URLSearchParams({
    codigo_materia: params.codigoMateria,
    tipo_periodo: params.tipoPeriodo,
  })
  for (const codigoPeriodo of params.codigoPeriodos) {
    query.append('codigo_periodo', codigoPeriodo)
  }
  return request<PortalTeacherStudentsResponse>(`/api/portal/teacher/subject-students?${query.toString()}`, {
    cache: 'no-store',
  })
}

export async function savePortalTeacherGrades(
  payload: PortalTeacherGradePayload
): Promise<PortalTeacherGradeSaveResponse> {
  return request<PortalTeacherGradeSaveResponse>('/api/portal/teacher/grades', {
    method: 'PUT',
    body: payload,
  })
}

export async function downloadPortalTeacherCourseReport(params: {
  codigoPeriodo?: string
  codigoPeriodos?: string[]
  codAnioBasica?: string
  codJornada?: number | null
  codigoMateria: string
  paralelo: string
}): Promise<Blob> {
  const query = new URLSearchParams({
    codigo_materia: params.codigoMateria,
    paralelo: params.paralelo,
  })
  if (params.codAnioBasica) {
    query.set('cod_anio_basica', params.codAnioBasica)
  }
  if (params.codJornada !== null && params.codJornada !== undefined) {
    query.set('cod_jornada', String(params.codJornada))
  }
  const periodos = params.codigoPeriodos?.length ? params.codigoPeriodos : params.codigoPeriodo ? [params.codigoPeriodo] : []
  for (const codigoPeriodo of periodos) {
    query.append('codigo_periodo', codigoPeriodo)
  }
  const response = await fetch(`/api/portal/teacher/course-report-pdf?${query.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function fetchTeacherComplianceFormat(): Promise<TeacherComplianceReportFormat> {
  return request<TeacherComplianceReportFormat>('/api/portal/admin/teacher-compliance-format')
}

export async function updateTeacherComplianceFormat(
  payload: TeacherComplianceReportFormat
): Promise<TeacherComplianceReportFormat> {
  return request<TeacherComplianceReportFormat>('/api/portal/admin/teacher-compliance-format', {
    method: 'PUT',
    body: payload,
  })
}

type TeacherComplianceReportParams = {
  codigoPeriodo?: string
  codigoPeriodos?: string[]
  codAnioBasica?: string
  codJornada?: number | null
  codigoMateria: string
  paralelo: string
  codigoEstudiantes?: Array<string | number>
  fechaInicio?: string
  fechaFin?: string
  telefono?: string
  actualizaciones?: string
  observaciones?: string
  justificacionReprobados?: string
  recursosMoodle?: TeacherComplianceMoodleResource[]
  grabacionesTeams?: TeacherComplianceTeamsRecording[]
  evidencias?: Array<{ label: string; file: File }>
  reporteNotasFirmado?: Blob
  reporteNotasFirmadoNombre?: string
}

function buildTeacherComplianceFormData(params: TeacherComplianceReportParams): FormData {
  const formData = new FormData()
  formData.append('codigo_materia', params.codigoMateria)
  formData.append('paralelo', params.paralelo)
  if (params.codAnioBasica) formData.append('cod_anio_basica', params.codAnioBasica)
  if (params.codJornada !== null && params.codJornada !== undefined) formData.append('cod_jornada', String(params.codJornada))
  if (params.fechaInicio) formData.append('fecha_inicio', params.fechaInicio)
  if (params.fechaFin) formData.append('fecha_fin', params.fechaFin)
  if (params.telefono) formData.append('telefono', params.telefono)
  if (params.actualizaciones) formData.append('actualizaciones', params.actualizaciones)
  if (params.observaciones) formData.append('observaciones', params.observaciones)
  if (params.justificacionReprobados) {
    formData.append('justificacion_reprobados', params.justificacionReprobados)
  }
  if (params.recursosMoodle?.length) {
    formData.append('moodle_resources_json', JSON.stringify(params.recursosMoodle))
  }
  if (params.grabacionesTeams?.length) {
    formData.append('teams_recordings_json', JSON.stringify(params.grabacionesTeams))
  }
  const periodos = params.codigoPeriodos?.length ? params.codigoPeriodos : params.codigoPeriodo ? [params.codigoPeriodo] : []
  for (const codigoPeriodo of periodos) {
    formData.append('codigo_periodo', codigoPeriodo)
  }
  for (const codigoEstud of params.codigoEstudiantes || []) {
    if (codigoEstud !== undefined && codigoEstud !== null && String(codigoEstud).trim()) {
      formData.append('codigo_estud', String(codigoEstud))
    }
  }
  for (const evidence of params.evidencias || []) {
    formData.append('evidencia_label', evidence.label)
    formData.append('evidencia', evidence.file)
  }
  if (params.reporteNotasFirmado) {
    formData.append(
      'reporte_notas_firmado',
      params.reporteNotasFirmado,
      params.reporteNotasFirmadoNombre || 'reporte-notas-secretaria-firmado.pdf'
    )
  }
  return formData
}

export async function downloadPortalTeacherComplianceReport(params: TeacherComplianceReportParams): Promise<Blob> {
  const formData = buildTeacherComplianceFormData(params)
  return request<Blob>('/api/portal/teacher/compliance-report-pdf', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function signPortalTeacherComplianceReport(
  params: TeacherComplianceReportParams & {
    certificado: File
    contrasenaCertificado: string
    firmaMotivo: string
    firmaUbicacion: string
    firmaContacto?: string
  }
): Promise<Blob> {
  const formData = buildTeacherComplianceFormData(params)
  formData.append('certificado', params.certificado)
  formData.append('contrasena_certificado', params.contrasenaCertificado)
  formData.append('firma_motivo', params.firmaMotivo)
  formData.append('firma_ubicacion', params.firmaUbicacion)
  if (params.firmaContacto) formData.append('firma_contacto', params.firmaContacto)
  return request<Blob>('/api/portal/teacher/compliance-report-sign', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function saveAcademicTeacherEnrollment(
  payload: AcademicTeacherEnrollmentPayload
): Promise<AcademicTeacherEnrollmentSaveResponse> {
  return request<AcademicTeacherEnrollmentSaveResponse>('/api/students/matricula-acad/docentes/matricula', {
    method: 'POST',
    body: payload,
  })
}

export async function saveAcademicTeacherUniqueEnrollment(
  payload: AcademicTeacherUniqueEnrollmentPayload
): Promise<AcademicTeacherEnrollmentSaveResponse> {
  return request<AcademicTeacherEnrollmentSaveResponse>('/api/students/matricula-acad/docentes/matricula/materia-unica', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchAcademicTeacherStateCatalog(): Promise<AcademicTeacherStateCatalogResponse> {
  return request<AcademicTeacherStateCatalogResponse>('/api/students/matricula-acad/docentes/estados/catalogo')
}

export async function fetchAcademicTeacherStates(
  query: string = '',
  estado: string = '',
  validarUsuario: boolean = false,
  limit: number = 50
): Promise<AcademicTeacherStateSearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) })
  if (estado) {
    params.set('estado', estado)
  }
  if (validarUsuario) {
    params.set('validar_usuario', 'true')
  }
  return request<AcademicTeacherStateSearchResponse>(`/api/students/matricula-acad/docentes/estados?${params.toString()}`)
}

export async function updateAcademicTeacherState(
  payload: AcademicTeacherStateUpdatePayload
): Promise<AcademicTeacherStateUpdateResponse> {
  return request<AcademicTeacherStateUpdateResponse>('/api/students/matricula-acad/docentes/estado', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchTeacherEvaluationIdentity(
  cedula: string,
): Promise<TeacherEvaluationIdentityResponse> {
  return request<TeacherEvaluationIdentityResponse>(
    `/api/evaluacion-docente/identity/${encodeURIComponent(cedula.trim())}`,
  )
}

export async function fetchTeacherEvaluationByCedula(
  cedula: string,
  accessToken: string,
): Promise<TeacherEvaluationStudentResponse> {
  return request<TeacherEvaluationStudentResponse>(
    `/api/evaluacion-docente/student/${encodeURIComponent(cedula.trim())}`,
    { headers: { 'X-Evaluation-Token': accessToken } },
  )
}

export async function saveAcademicTeacherMultiEnrollment(
  payload: AcademicTeacherMultiEnrollmentPayload
): Promise<AcademicTeacherEnrollmentSaveResponse> {
  return request<AcademicTeacherEnrollmentSaveResponse>(
    '/api/students/matricula-acad/docentes/matricula/materia-unica/multiple',
    {
      method: 'POST',
      body: payload,
    }
  )
}

export async function saveAcademicTeacherMultiSubjectEnrollment(
  payload: AcademicTeacherMultiSubjectEnrollmentPayload
): Promise<AcademicTeacherEnrollmentSaveResponse> {
  return request<AcademicTeacherEnrollmentSaveResponse>(
    '/api/students/matricula-acad/docentes/matricula/materias/multiple',
    {
      method: 'POST',
      body: payload,
    }
  )
}

export async function fetchTeacherEvaluationTeacherByCedula(
  cedula: string,
  accessToken: string,
): Promise<TeacherEvaluationTeacherResponse> {
  return request<TeacherEvaluationTeacherResponse>(
    `/api/evaluacion-docente/teacher/${encodeURIComponent(cedula.trim())}`,
    { headers: { 'X-Evaluation-Token': accessToken } },
  )
}

export async function fetchTeacherEvaluationQuestions(
  flow: TeacherEvaluationFlow = 'student'
): Promise<TeacherEvaluationQuestionsResponse> {
  const params = new URLSearchParams({ flow })
  return request<TeacherEvaluationQuestionsResponse>(`/api/evaluacion-docente/questions?${params.toString()}`)
}

export async function saveTeacherEvaluation(
  payload: TeacherEvaluationSubmitPayload,
  accessToken: string,
): Promise<TeacherEvaluationSubmitResponse> {
  return request<TeacherEvaluationSubmitResponse>('/api/evaluacion-docente/evaluate', {
    method: 'POST',
    body: payload,
    headers: { 'X-Evaluation-Token': accessToken },
  })
}

export async function saveTeacherRoleEvaluation(
  payload: TeacherRoleEvaluationSubmitPayload,
  accessToken: string,
): Promise<TeacherEvaluationSubmitResponse> {
  return request<TeacherEvaluationSubmitResponse>('/api/evaluacion-docente/teacher/evaluate', {
    method: 'POST',
    body: payload,
    headers: { 'X-Evaluation-Token': accessToken },
  })
}

export async function fetchTeacherEvaluationAdminPeriods(): Promise<TeacherEvaluationAdminPeriodsResponse> {
  return request<TeacherEvaluationAdminPeriodsResponse>('/api/evaluacion-docente/admin/periodos')
}

export async function fetchTeacherEvaluationAdminPending(
  periodo: string,
  flow: TeacherEvaluationFlow | 'all' = 'all',
  limit = 5000,
): Promise<TeacherEvaluationAdminPendingResponse> {
  const params = new URLSearchParams({ periodo, flow, limit: String(limit) })
  return request<TeacherEvaluationAdminPendingResponse>(`/api/evaluacion-docente/admin/pendientes?${params.toString()}`)
}

export async function fetchTeacherEvaluationProgressDetail(
  periodo: string,
  codigoDocente: string,
  codigoMateria: string,
  flow: TeacherEvaluationFlow | 'all' = 'all',
  paralelo: string = '',
): Promise<TeacherEvaluationProgressDetailResponse> {
  const params = new URLSearchParams({
    periodo,
    codigo_docente: codigoDocente,
    codigo_materia: codigoMateria,
    flow,
  })
  if (paralelo) params.set('paralelo', paralelo)
  return request<TeacherEvaluationProgressDetailResponse>(
    `/api/evaluacion-docente/admin/progreso-detalle?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationProgressParticipants(
  periodo: string,
  codigoDocente: string,
  codigoMateria: string,
  flow: TeacherEvaluationFlow | 'all',
  estado: 'completadas' | 'pendientes',
  paralelo: string = '',
  limit = 1500,
): Promise<TeacherEvaluationProgressParticipantsResponse> {
  const params = new URLSearchParams({
    periodo,
    codigo_docente: codigoDocente,
    codigo_materia: codigoMateria,
    flow,
    estado,
    limit: String(limit),
  })
  if (paralelo) params.set('paralelo', paralelo)
  return request<TeacherEvaluationProgressParticipantsResponse>(
    `/api/evaluacion-docente/admin/progreso-participantes?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationGradedTeachers(
  periodo: string,
  flow: TeacherEvaluationFlow | 'all' = 'all',
): Promise<TeacherEvaluationGradedTeachersResponse> {
  const params = new URLSearchParams({ periodo, flow })
  return request<TeacherEvaluationGradedTeachersResponse>(
    `/api/evaluacion-docente/admin/docentes-calificados?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationGradedSubjects(
  periodo: string,
  codigoDocente: string,
  flow: TeacherEvaluationFlow | 'all' = 'all',
): Promise<TeacherEvaluationGradedSubjectsResponse> {
  const params = new URLSearchParams({ periodo, codigo_docente: codigoDocente, flow })
  return request<TeacherEvaluationGradedSubjectsResponse>(
    `/api/evaluacion-docente/admin/docente-materias-calificadas?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationStudentProgress(
  periodo: string,
  limit = 1000,
): Promise<TeacherEvaluationStudentProgressResponse> {
  const params = new URLSearchParams({ periodo, limit: String(limit) })
  return request<TeacherEvaluationStudentProgressResponse>(
    `/api/evaluacion-docente/admin/avance-estudiantes?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationAutoStudents(
  periodo: string,
  estado: 'pendientes' | 'realizadas' | 'todos' = 'pendientes',
  limit = 500,
  codigoEstud?: number,
): Promise<TeacherEvaluationAutoStudentListResponse> {
  const params = new URLSearchParams({ periodo, estado, limit: String(limit) })
  if (codigoEstud) params.set('codigo_estud', String(codigoEstud))
  return request<TeacherEvaluationAutoStudentListResponse>(
    `/api/evaluacion-docente/admin/autoevaluacion-estudiantes?${params.toString()}`,
  )
}

export async function fetchTeacherEvaluationStudentGrades(
  periodo: string,
  codigoEstud: number,
): Promise<TeacherEvaluationStudentGradesResponse> {
  const params = new URLSearchParams({ periodo, codigo_estud: String(codigoEstud) })
  return request<TeacherEvaluationStudentGradesResponse>(
    `/api/evaluacion-docente/admin/estudiante-notas?${params.toString()}`,
  )
}

export async function downloadTeacherEvaluationGradesPdf(
  periodo: string,
  codigoDocente: string = '',
  flow: TeacherEvaluationFlow | 'all' = 'all',
  documentType: 'certificado' | 'consolidado' | 'resumen' | 'detalle' = 'certificado',
  subject?: { codigo_materia?: string; carrera?: string; paralelo?: string | null },
): Promise<Blob> {
  const params = new URLSearchParams({ periodo, flow, document_type: documentType })
  if (codigoDocente) params.set('codigo_docente', codigoDocente)
  if (subject?.codigo_materia) params.set('codigo_materia', subject.codigo_materia)
  if (subject?.carrera) params.set('carrera', subject.carrera)
  if (subject?.paralelo) params.set('paralelo', subject.paralelo)
  return request<Blob>(`/api/evaluacion-docente/admin/reporte-docentes.pdf?${params.toString()}`, {
    responseType: 'blob',
  })
}

export async function fetchExcelSqlCross(limit: number = 0, dbLimit: number = 0): Promise<ExcelSqlCrossResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    db_limit: String(dbLimit),
  })

  return request<ExcelSqlCrossResponse>(`/api/students/cruce-excel-moodle-tablas?${params.toString()}`)
}

export async function downloadExcelSqlCrossWorkbook(dbLimit: number = 0): Promise<Blob> {
  const params = new URLSearchParams({ db_limit: String(dbLimit) })
  const response = await fetch(`/api/students/cruce-excel-moodle-tablas/export?${params.toString()}`, {
    credentials: 'include',
  })
  const contentType = response.headers.get('Content-Type') || ''

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  if (!contentType.includes('spreadsheet') && !contentType.includes('octet-stream')) {
    const payload = await readResponsePayload(response)
    throw new ApiError(typeof payload === 'string' ? payload : 'Respuesta inválida al descargar el archivo de Excel.', response.status)
  }

  return response.blob()
}

export async function uploadExcelValidation(file: File): Promise<ExcelValidationResponse> {
  const formData = new FormData()
  formData.set('file', file)
  return request<ExcelValidationResponse>('/api/students/validar-excel', {
    method: 'POST',
    body: formData,
  })
}

function ageRangeParams(filters: AgeRangeFilters = {}): URLSearchParams {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 1000) })
  if (filters.periodo) params.set('periodo', filters.periodo)
  if (filters.carrera) params.set('carrera', filters.carrera)
  if (filters.estado) params.set('estado', filters.estado)
  if (filters.tipo_beca) params.set('tipo_beca', filters.tipo_beca)
  if (filters.buscar) params.set('buscar', filters.buscar)
  if (filters.rango_edad) params.set('rango_edad', filters.rango_edad)
  return params
}

export async function fetchAgeRangesCatalog(): Promise<AgeRangeCatalogResponse> {
  return request<AgeRangeCatalogResponse>('/api/students/rango-edades/catalog')
}

export async function fetchAgeRanges(filters: AgeRangeFilters = {}): Promise<AgeRangeResponse> {
  return request<AgeRangeResponse>(`/api/students/rango-edades?${ageRangeParams(filters).toString()}`)
}

export async function downloadAgeRangesWorkbook(filters: AgeRangeFilters = {}): Promise<Blob> {
  const response = await fetch(`/api/students/rango-edades/export?${ageRangeParams({ ...filters, limit: filters.limit ?? 10000 }).toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const errorPayload = await readResponsePayload(response)
    const detail =
      typeof errorPayload === 'string'
        ? errorPayload
        : (errorPayload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function fetchSenescytStudentReport(): Promise<SenescytStudentReportResponse> {
  return request<SenescytStudentReportResponse>('/api/students/senescyt/estudiantes')
}

export async function searchSenescytStudentData(query: string): Promise<SenescytStudentDataSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: '60' })
  return request<SenescytStudentDataSearchResponse>(`/api/students/senescyt/estudiantes/buscar?${params.toString()}`)
}

export async function fetchSenescytStudentData(codigoEstud: string): Promise<SenescytStudentDataDetailResponse> {
  return request<SenescytStudentDataDetailResponse>(
    `/api/students/senescyt/estudiantes/datos/${encodeURIComponent(codigoEstud)}`,
  )
}

export async function updateSenescytStudentData(
  codigoEstud: string,
  fields: Record<string, string | number | null>,
): Promise<SenescytStudentDataDetailResponse> {
  return request<SenescytStudentDataDetailResponse>(
    `/api/students/senescyt/estudiantes/datos/${encodeURIComponent(codigoEstud)}`,
    {
      method: 'PUT',
      body: { fields },
    },
  )
}

export async function searchLegacyDataUpdate(
  target: LegacyDataUpdateTarget,
  query: string,
): Promise<LegacyDataUpdateSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: '80' })
  return request<LegacyDataUpdateSearchResponse>(
    `/api/students/actualizacion-datos/${encodeURIComponent(target)}/buscar?${params.toString()}`,
  )
}

export async function fetchLegacyDataUpdateRecord(
  target: LegacyDataUpdateTarget,
  recordId: string,
): Promise<LegacyDataUpdateDetailResponse> {
  return request<LegacyDataUpdateDetailResponse>(
    `/api/students/actualizacion-datos/${encodeURIComponent(target)}/datos/${encodeURIComponent(recordId)}`,
  )
}

export async function updateLegacyDataUpdateRecord(
  target: LegacyDataUpdateTarget,
  recordId: string,
  fields: Record<string, string | number | null>,
): Promise<LegacyDataUpdateDetailResponse> {
  return request<LegacyDataUpdateDetailResponse>(
    `/api/students/actualizacion-datos/${encodeURIComponent(target)}/datos/${encodeURIComponent(recordId)}`,
    {
      method: 'PUT',
      body: { fields },
    },
  )
}

export async function downloadSenescytStudentReport(): Promise<Blob> {
  const response = await fetch('/api/students/senescyt/estudiantes/export', {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function fetchSenescytCatalog(): Promise<SenescytCatalogResponse> {
  return request<SenescytCatalogResponse>('/api/students/senescyt/catalogo')
}

export async function fetchSenescytAuditReport(
  target: SenescytTarget,
  careers?: string[],
): Promise<SenescytAuditResponse> {
  const params = new URLSearchParams({ target })
  careers?.filter(Boolean).forEach((career) => params.append('carrera', career))
  return request<SenescytAuditResponse>(`/api/students/senescyt/datos?${params.toString()}`)
}

export async function downloadSenescytAuditWorkbook(
  target: SenescytTarget,
  mode: SenescytExportMode,
  careers?: string[],
): Promise<Blob> {
  const params = new URLSearchParams({ target, mode })
  careers?.filter(Boolean).forEach((career) => params.append('carrera', career))
  const response = await fetch(`/api/students/senescyt/datos/export?${params.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function downloadPortalTeacherStudentGradeReport(params: {
  codigoPeriodo?: string
  codigoPeriodos?: string[]
  codAnioBasica?: string
  codJornada?: number | null
  codigoMateria: string
  paralelo: string
  codigoEstudiantes?: Array<string | number>
}): Promise<Blob> {
  const query = new URLSearchParams({
    codigo_materia: params.codigoMateria,
    paralelo: params.paralelo,
  })
  if (params.codAnioBasica) {
    query.set('cod_anio_basica', params.codAnioBasica)
  }
  if (params.codJornada !== null && params.codJornada !== undefined) {
    query.set('cod_jornada', String(params.codJornada))
  }
  const periodos = params.codigoPeriodos?.length ? params.codigoPeriodos : params.codigoPeriodo ? [params.codigoPeriodo] : []
  for (const codigoPeriodo of periodos) {
    query.append('codigo_periodo', codigoPeriodo)
  }
  for (const codigoEstud of params.codigoEstudiantes || []) {
    if (String(codigoEstud).trim()) query.append('codigo_estud', String(codigoEstud))
  }
  const response = await fetch(`/api/portal/teacher/student-grade-report-pdf?${query.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await readResponsePayload(response)
    const detail =
      typeof payload === 'string'
        ? payload
        : (payload as ErrorPayload | null)?.detail || `Error HTTP ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return response.blob()
}

export async function signPortalTeacherStudentGradeReport(params: {
  codigoPeriodo?: string
  codigoPeriodos?: string[]
  codAnioBasica?: string
  codJornada?: number | null
  codigoMateria: string
  paralelo: string
  codigoEstudiantes?: Array<string | number>
  certificado: File
  contrasenaCertificado: string
  firmaMotivo: string
  firmaUbicacion: string
  firmaContacto?: string
}): Promise<Blob> {
  const formData = new FormData()
  formData.append('codigo_materia', params.codigoMateria)
  formData.append('paralelo', params.paralelo)
  if (params.codAnioBasica) formData.append('cod_anio_basica', params.codAnioBasica)
  if (params.codJornada !== null && params.codJornada !== undefined) {
    formData.append('cod_jornada', String(params.codJornada))
  }
  const periodos = params.codigoPeriodos?.length ? params.codigoPeriodos : params.codigoPeriodo ? [params.codigoPeriodo] : []
  for (const codigoPeriodo of periodos) formData.append('codigo_periodo', codigoPeriodo)
  for (const codigoEstud of params.codigoEstudiantes || []) {
    if (String(codigoEstud).trim()) formData.append('codigo_estud', String(codigoEstud))
  }
  formData.append('certificado', params.certificado)
  formData.append('contrasena_certificado', params.contrasenaCertificado)
  formData.append('firma_motivo', params.firmaMotivo)
  formData.append('firma_ubicacion', params.firmaUbicacion)
  if (params.firmaContacto) formData.append('firma_contacto', params.firmaContacto)
  return request<Blob>('/api/portal/teacher/student-grade-report-sign', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
  })
}

export async function downloadPortalTeacherSignedDocumentsArchive(params: {
  informe: Blob
  informeNombre: string
  notas: Blob
  notasNombre: string
  contrato: Blob
  contratoNombre: string
  facturaXml?: File | null
  ridePdf?: File | null
  codigoMateria: string
  nombreMateria: string
  codigoPeriodos: string[]
}): Promise<{
  archive: Blob
  oneDriveSaved: boolean
  storedDocumentCount: number
  sameFolder: boolean
}> {
  const formData = new FormData()
  formData.append('informe', params.informe, params.informeNombre)
  formData.append('notas', params.notas, params.notasNombre)
  formData.append('contrato', params.contrato, params.contratoNombre)
  if (params.facturaXml) formData.append('factura_xml', params.facturaXml, params.facturaXml.name)
  if (params.ridePdf) formData.append('ride_pdf', params.ridePdf, params.ridePdf.name)
  formData.append('codigo_materia', params.codigoMateria)
  formData.append('nombre_materia', params.nombreMateria)
  for (const codigoPeriodo of params.codigoPeriodos) {
    formData.append('codigo_periodo', codigoPeriodo)
  }
  let oneDriveSaved = false
  let storedDocumentCount = 0
  let sameFolder = false
  let sameFolderHeaderPresent = false
  const archive = await request<Blob>('/api/portal/teacher/signed-documents-archive', {
    method: 'POST',
    body: formData,
    responseType: 'blob',
    onResponse: (response) => {
      oneDriveSaved = response.headers.get('X-OneDrive-Saved') === 'true'
      const sameFolderHeader = response.headers.get('X-OneDrive-Same-Folder')
      sameFolderHeaderPresent = sameFolderHeader !== null
      sameFolder = sameFolderHeader === 'true'
      const itemCount = Number.parseInt(response.headers.get('X-OneDrive-Item-Count') || '', 10)
      storedDocumentCount = Number.isFinite(itemCount) ? itemCount : 0
    },
  })
  if (!sameFolderHeaderPresent && oneDriveSaved && storedDocumentCount > 0) {
    // Compatibilidad con procesos backend anteriores que confirmaban la carga y
    // el conteo, pero todavía no publicaban el encabezado de carpeta compartida.
    sameFolder = true
  }
  return {
    archive,
    oneDriveSaved,
    storedDocumentCount,
    sameFolder,
  }
}

export async function fetchPracticasCatalog(): Promise<PracticasCatalogResponse> {
  return request<PracticasCatalogResponse>('/api/practicas/catalog')
}

export async function fetchPracticasStudent(codigoEstud?: number): Promise<PracticasStudentResponse> {
  const params = new URLSearchParams()
  if (codigoEstud) params.set('codigo_estud', String(codigoEstud))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<PracticasStudentResponse>(`/api/practicas/student/me${suffix}`)
}

export async function createPracticasExpediente(payload: {
  tipo_proceso_codigo: PracticasProcessCode
  codigo_estud?: number | null
  codigo_carrera?: string | null
  codigo_periodo?: string | null
  observacion?: string | null
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/practicas/student/expedientes', {
    method: 'POST',
    body: payload,
  })
}

export async function downloadPracticasCartaCompromiso(expedienteId: number): Promise<Blob> {
  return request<Blob>(`/api/practicas/student/expedientes/${expedienteId}/carta-compromiso.pdf`, {
    responseType: 'blob',
  })
}

export async function uploadPracticasCartaCompromiso(
  expedienteId: number,
  file: File,
): Promise<Record<string, unknown>> {
  const formData = new FormData()
  formData.set('file', file)
  return request<Record<string, unknown>>(`/api/practicas/student/expedientes/${expedienteId}/carta-compromiso`, {
    method: 'POST',
    body: formData,
  })
}

export async function uploadPracticasCertificado(
  expedienteId: number,
  file: File,
): Promise<Record<string, unknown>> {
  const formData = new FormData()
  formData.set('file', file)
  return request<Record<string, unknown>>(`/api/practicas/student/expedientes/${expedienteId}/certificado`, {
    method: 'POST',
    body: formData,
  })
}

export async function fetchPracticasExpedientes(filters: {
  tipo_proceso?: PracticasProcessCode | ''
  search?: string
  limit?: number
} = {}): Promise<PracticasExpedientesResponse> {
  const params = new URLSearchParams()
  if (filters.tipo_proceso) params.set('tipo_proceso', filters.tipo_proceso)
  if (filters.search) params.set('search', filters.search)
  if (filters.limit) params.set('limit', String(filters.limit))
  return request<PracticasExpedientesResponse>(`/api/practicas/admin/expedientes?${params.toString()}`)
}

export async function fetchPracticasElegibles(filters: {
  tipo_proceso?: PracticasProcessCode
  search?: string
  codigo_periodo?: string
  limit?: number
} = {}): Promise<PracticasElegiblesResponse> {
  const params = new URLSearchParams()
  if (filters.tipo_proceso) params.set('tipo_proceso', filters.tipo_proceso)
  if (filters.search) params.set('search', filters.search)
  if (filters.codigo_periodo) params.set('codigo_periodo', filters.codigo_periodo)
  if (filters.limit) params.set('limit', String(filters.limit))
  return request<PracticasElegiblesResponse>(`/api/practicas/admin/elegibles?${params.toString()}`)
}

export async function fetchPracticasPeriodos(
  tipoProceso: PracticasProcessCode = 'PPF',
): Promise<PracticasPeriodosResponse> {
  const params = new URLSearchParams({ tipo_proceso: tipoProceso })
  return request<PracticasPeriodosResponse>(`/api/practicas/admin/periodos?${params.toString()}`)
}

export async function fetchPracticasPeriodoDesignaciones(
  tipoProceso: PracticasProcessCode = 'PPF',
): Promise<PracticasPeriodoDesignacionesResponse> {
  const params = new URLSearchParams({ tipo_proceso: tipoProceso })
  return request<PracticasPeriodoDesignacionesResponse>(`/api/practicas/admin/designaciones-periodo?${params.toString()}`)
}

export async function savePracticasPeriodoDesignacion(payload: {
  tipo_proceso_codigo: PracticasProcessCode
  codigo_periodo: string
  codigo_periodo_origen?: string | null
  nombre_responsable: string
  rol_responsable?: string
  codigo_docente: string
  cedula_responsable?: string | null
  correo_responsable?: string | null
  estudiantes: number[]
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/practicas/admin/designaciones-periodo', {
    method: 'POST',
    body: payload,
  })
}

export async function uploadPracticasAutorizacion(payload: {
  tipo_proceso_codigo: PracticasProcessCode
  codigo_estud: number
  codigo_periodo: string
  file: File
}): Promise<Record<string, unknown>> {
  const formData = new FormData()
  formData.append('tipo_proceso_codigo', payload.tipo_proceso_codigo)
  formData.append('codigo_estud', String(payload.codigo_estud))
  formData.append('codigo_periodo', payload.codigo_periodo)
  formData.append('file', payload.file)
  return request<Record<string, unknown>>('/api/practicas/admin/autorizaciones', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchPracticasResponsableAvance(
  tipoProceso: PracticasProcessCode = 'PPF',
): Promise<PracticasResponsableProgressResponse> {
  const params = new URLSearchParams({ tipo_proceso: tipoProceso })
  return request<PracticasResponsableProgressResponse>(`/api/practicas/responsable/avance?${params.toString()}`)
}

export async function fetchPracticasReviewDetail(
  expedienteId: number,
): Promise<PracticasReviewDetailResponse> {
  return request<PracticasReviewDetailResponse>(`/api/practicas/responsable/expedientes/${expedienteId}`)
}

export async function reviewPracticasExpediente(
  expedienteId: number,
  payload: {
    tipo_proceso_codigo: PracticasProcessCode
    decision: PracticasReviewDecision
    horas_verificadas: number
    documentos_corroborados: boolean
    observacion?: string | null
  },
): Promise<PracticasReviewResponse> {
  return request<PracticasReviewResponse>(`/api/practicas/responsable/expedientes/${expedienteId}/revision`, {
    method: 'POST',
    body: payload,
  })
}

export async function createPracticasResponsable(payload: {
  tipo_proceso_codigo: PracticasProcessCode
  expediente_id?: number | null
  nombre_responsable: string
  rol_responsable?: string
  codigo_docente?: string | null
  cedula_responsable?: string | null
  correo_responsable?: string | null
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/practicas/admin/responsables', {
    method: 'POST',
    body: payload,
  })
}

export async function assignPracticasResponsable(
  expedienteId: number,
  responsableProcesoId: number,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/practicas/admin/expedientes/${expedienteId}/responsable`, {
    method: 'POST',
    body: { responsable_proceso_id: responsableProcesoId },
  })
}

export async function fetchTitulacionExpediente(numeroIdentificacion: string): Promise<TitulacionResponse> {
  const params = new URLSearchParams({ numero_identificacion: numeroIdentificacion })
  return request<TitulacionResponse>(`/api/titulacion/expediente?${params.toString()}`)
}

export async function fetchTitulacionAptos(filters: {
  search?: string
  limit?: number
} = {}): Promise<TitulacionAptosResponse> {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.limit) params.set('limit', String(filters.limit))
  const query = params.toString()
  return request<TitulacionAptosResponse>(`/api/titulacion/aptos${query ? `?${query}` : ''}`)
}

export async function fetchTitulacionMallaCalificaciones(
  numeroIdentificacion: string,
  codAnioBasica?: string | null,
): Promise<TitulacionMallaCalificacionesResponse> {
  const params = new URLSearchParams({ numero_identificacion: numeroIdentificacion })
  if (codAnioBasica) params.set('cod_anio_basica', codAnioBasica)
  return request<TitulacionMallaCalificacionesResponse>(`/api/titulacion/malla-calificaciones?${params.toString()}`)
}

export async function fetchTitulacionProgramacion(filters: {
  mecanismo?: string
  search?: string
  limit?: number
} = {}): Promise<TitulacionProgramacionResponse> {
  const params = new URLSearchParams()
  if (filters.mecanismo) params.set('mecanismo', filters.mecanismo)
  if (filters.search) params.set('search', filters.search)
  if (filters.limit) params.set('limit', String(filters.limit))
  const query = params.toString()
  return request<TitulacionProgramacionResponse>(`/api/titulacion/programacion${query ? `?${query}` : ''}`)
}

export async function createTitulacionExpediente(payload: TitulacionExpedientePayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/expediente', {
    method: 'POST',
    body: payload,
  })
}

export async function syncTitulacionPracticas(expedienteId: number): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/sincronizar-practicas', {
    method: 'POST',
    body: { expediente_id: expedienteId },
  })
}

export async function saveTitulacionNotas(payload: TitulacionNotasPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/notas', {
    method: 'POST',
    body: payload,
  })
}

export async function selectTitulacionMecanismo(payload: TitulacionMecanismoPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/mecanismo', {
    method: 'POST',
    body: payload,
  })
}

export async function programTitulacionExamen(payload: TitulacionProgramacionPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/examen-complexivo/programar', {
    method: 'POST',
    body: payload,
  })
}

export async function gradeTitulacionExamen(payload: ExamenComplexivoCalificacionPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/examen-complexivo/calificar', {
    method: 'POST',
    body: payload,
  })
}

export async function saveTitulacionDefensaTema(payload: DefensaTemaPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/defensa-grado/tema', {
    method: 'POST',
    body: payload,
  })
}

export async function programTitulacionDefensa(payload: TitulacionProgramacionPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/defensa-grado/programar', {
    method: 'POST',
    body: payload,
  })
}

export async function gradeTitulacionDefensa(payload: DefensaCalificacionPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/defensa-grado/calificar', {
    method: 'POST',
    body: payload,
  })
}

export async function addTitulacionTribunal(payload: TitulacionTribunalPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/tribunal', {
    method: 'POST',
    body: payload,
  })
}

export async function uploadTitulacionDocumento(payload: {
  expediente_id: number
  tipo_documento_codigo: string
  observacion?: string
  file: File
}): Promise<TitulacionResponse> {
  const formData = new FormData()
  formData.append('expediente_id', String(payload.expediente_id))
  formData.append('tipo_documento_codigo', payload.tipo_documento_codigo)
  formData.append('observacion', payload.observacion || '')
  formData.append('file', payload.file)
  return request<TitulacionResponse>('/api/titulacion/documentos', {
    method: 'POST',
    body: formData,
  })
}

export async function generateTitulacion(expedienteId: number): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/generar', {
    method: 'POST',
    body: { expediente_id: expedienteId },
  })
}

export async function generateTitulacionActa(payload: ActaGradoPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/acta-grado', {
    method: 'POST',
    body: payload,
  })
}

export async function registerTitulacionSenescyt(payload: TituloSenescytPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/titulo-senescyt', {
    method: 'POST',
    body: payload,
  })
}

export async function registerTitulacionIntec(payload: TituloIntecPayload): Promise<TitulacionResponse> {
  return request<TitulacionResponse>('/api/titulacion/titulo-intec', {
    method: 'POST',
    body: payload,
  })
}

export async function fetchTitulosRegistrados(filters: {
  tipo?: TituloRegistradoTipo | string
  search?: string
} = {}): Promise<TitulosRegistradosResponse> {
  const params = new URLSearchParams()
  if (filters.tipo) params.set('tipo', filters.tipo)
  if (filters.search) params.set('search', filters.search)
  const query = params.toString()
  return request<TitulosRegistradosResponse>(`/api/titulos-registrados${query ? `?${query}` : ''}`)
}

export async function fetchTitulosRegistradosFolders(tipo: TituloRegistradoTipo | string): Promise<{
  items: Array<{ id?: string; name: string; web_url?: string }>
  root: string
}> {
  const params = new URLSearchParams({ tipo })
  return request<{
    items: Array<{ id?: string; name: string; web_url?: string }>
    root: string
  }>(`/api/titulos-registrados/folders?${params.toString()}`)
}

export async function createTitulosRegistradosFolder(payload: {
  tipo: TituloRegistradoTipo | string
  nombre: string
}): Promise<{
  ok: boolean
  message: string
  item?: { id?: string; name?: string; web_url?: string }
}> {
  return request<{
    ok: boolean
    message: string
    item?: { id?: string; name?: string; web_url?: string }
  }>('/api/titulos-registrados/folders', {
    method: 'POST',
    body: payload,
  })
}

export async function searchTitulosRegistradosStudents(search: string): Promise<{
  items: Array<{ codigo_estud?: string; cedula: string; estudiante: string; carrera?: string; estado?: string }>
}> {
  const params = new URLSearchParams({ search })
  return request<{
    items: Array<{ codigo_estud?: string; cedula: string; estudiante: string; carrera?: string; estado?: string }>
  }>(`/api/titulos-registrados/students?${params.toString()}`)
}

export async function uploadTituloRegistrado(payload: {
  tipo: TituloRegistradoTipo | string
  modelo: string
  estudiante?: string
  cedula?: string
  carrera?: string
  observacion?: string
  file: File
}): Promise<TituloRegistradoSaveResponse> {
  const formData = new FormData()
  formData.append('tipo', payload.tipo)
  formData.append('modelo', payload.modelo)
  formData.append('estudiante', payload.estudiante || '')
  formData.append('cedula', payload.cedula || '')
  formData.append('carrera', payload.carrera || '')
  formData.append('observacion', payload.observacion || '')
  formData.append('file', payload.file)
  return request<TituloRegistradoSaveResponse>('/api/titulos-registrados', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadTitulosSenescytMasivo(payload: {
  modelo: string
  observacion?: string
  files: File[]
}): Promise<TituloRegistradoSaveResponse> {
  const formData = new FormData()
  formData.append('modelo', payload.modelo)
  formData.append('observacion', payload.observacion || '')
  payload.files.forEach((file) => {
    formData.append('files', file)
  })
  return request<TituloRegistradoSaveResponse>('/api/titulos-registrados/bulk-senescyt', {
    method: 'POST',
    body: formData,
  })
}

export async function deleteTituloRegistrado(itemId: string): Promise<TituloRegistradoSaveResponse> {
  return request<TituloRegistradoSaveResponse>(`/api/titulos-registrados/${encodeURIComponent(itemId)}`, {
    method: 'DELETE',
  })
}

export async function fetchEnglishStudentExam(): Promise<EnglishExam> {
  return request<EnglishExam>('/api/english/student', { cache: 'no-store' })
}

export async function createEnglishUploadSession(file: File, componentCode: string): Promise<EnglishUploadSessionResponse> {
  return request<EnglishUploadSessionResponse>('/api/english/student/upload-session', {
    method: 'POST',
    body: {
      filename: file.name,
      size: file.size,
      content_type: file.type || 'application/octet-stream',
      component_code: componentCode,
    },
  })
}

export async function uploadGraphFileChunks(
  uploadUrl: string,
  file: File,
  chunkSize: number,
  onProgress?: (percentage: number) => void,
): Promise<void> {
  type UploadStatus = {
    nextExpectedRanges?: string[]
    error?: { message?: string }
  }

  const nextOffset = (payload: UploadStatus | null, fallback: number) => {
    const range = payload?.nextExpectedRanges?.[0] || ''
    const match = /^(\d+)/.exec(range)
    if (!match) return fallback
    return Math.min(file.size, Math.max(0, Number(match[1])))
  }

  const sessionOffset = async () => {
    try {
      const response = await fetch(uploadUrl, { method: 'GET', credentials: 'omit' })
      if (!response.ok) return null
      const payload = await response.json() as UploadStatus
      return nextOffset(payload, file.size)
    } catch {
      return null
    }
  }

  const waitBeforeRetry = async (attempt: number, response: Response | null) => {
    const retryAfter = Number(response?.headers.get('Retry-After') || 0)
    const delay = retryAfter > 0
      ? Math.min(retryAfter * 1000, 15_000)
      : Math.min(750 * (2 ** (attempt - 1)), 8_000)
    await new Promise((resolve) => window.setTimeout(resolve, delay))
  }

  const uploadChunk = (
    chunk: Blob,
    chunkStart: number,
    endExclusive: number,
  ): Promise<Response> => new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', uploadUrl, true)
    request.withCredentials = false
    request.timeout = 10 * 60 * 1000
    request.setRequestHeader('Content-Range', `bytes ${chunkStart}-${endExclusive - 1}/${file.size}`)
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const sentBytes = Math.min(file.size, chunkStart + event.loaded)
      onProgress?.(Math.round((sentBytes / file.size) * 100))
    }
    request.onload = () => {
      const headers = new Headers()
      const retryAfter = request.getResponseHeader('Retry-After')
      const contentType = request.getResponseHeader('Content-Type')
      if (retryAfter) headers.set('Retry-After', retryAfter)
      if (contentType) headers.set('Content-Type', contentType)
      resolve(new Response(request.responseText || null, {
        status: request.status,
        statusText: request.statusText,
        headers,
      }))
    }
    request.onerror = () => reject(new Error('No se pudo conectar con Microsoft Graph durante la carga.'))
    request.ontimeout = () => reject(new Error('La carga agotó el tiempo de espera. Verifique su conexión e intente nuevamente.'))
    request.onabort = () => reject(new Error('La carga fue interrumpida.'))
    request.send(chunk)
  })

  let offset = await sessionOffset() ?? 0
  onProgress?.(Math.round((offset / file.size) * 100))
  while (offset < file.size) {
    const chunkStart = offset
    const endExclusive = Math.min(chunkStart + chunkSize, file.size)
    const chunk = file.slice(chunkStart, endExclusive)
    let response: Response | null = null
    let advanced = false

    for (let attempt = 1; attempt <= 6; attempt += 1) {
      try {
        response = await uploadChunk(chunk, chunkStart, endExclusive)
        if (response.ok) {
          let payload: UploadStatus | null = null
          try {
            payload = await response.json() as UploadStatus
          } catch {
            // La respuesta final de Graph puede no incluir JSON utilizable.
          }
          offset = response.status === 200 || response.status === 201
            ? file.size
            : nextOffset(payload, endExclusive)
          advanced = offset > chunkStart
          if (advanced) break
        }
      } catch {
        response = null
      }

      const recoveredOffset = await sessionOffset()
      if (recoveredOffset !== null && recoveredOffset > chunkStart) {
        offset = recoveredOffset
        advanced = true
        break
      }

      const transient = !response
        || response.status === 408
        || response.status === 416
        || response.status === 429
        || response.status >= 500
      if (!transient || attempt === 6) break
      await waitBeforeRetry(attempt, response)
    }

    if (!advanced) {
      let detail = 'Microsoft Graph rechazó una parte del archivo.'
      if (response) {
        try {
          const payload = await response.json() as UploadStatus
          detail = payload.error?.message || detail
        } catch {
          // Graph puede responder sin cuerpo en errores transitorios.
        }
      }
      throw new ApiError(detail, response?.status || 502)
    }

    onProgress?.(Math.round((offset / file.size) * 100))
  }
}

export async function uploadEnglishFileChunks(
  uploadUrl: string,
  file: File,
  chunkSize: number,
  onProgress?: (percentage: number) => void,
): Promise<void> {
  return uploadGraphFileChunks(uploadUrl, file, chunkSize, onProgress)
}

export async function finalizeEnglishUpload(uploadId: string): Promise<EnglishExam> {
  return request<EnglishExam>('/api/english/student/finalize', {
    method: 'POST',
    body: { upload_id: uploadId },
  })
}

export async function confirmEnglishDelivery(uploadId: string, componentCode: string): Promise<EnglishExam> {
  return request<EnglishExam>('/api/english/student/confirm', {
    method: 'POST',
    body: { upload_id: uploadId, component_code: componentCode },
  })
}

export async function fetchEnglishSubmissions(filters: {
  search?: string
  state?: string
  periodCode?: string
  subjectCode?: string
} = {}): Promise<EnglishSubmissionsResponse> {
  const params = new URLSearchParams()
  if (filters.search?.trim()) params.set('search', filters.search.trim())
  if (filters.state) params.set('state', filters.state)
  if (filters.periodCode?.trim()) params.set('period_code', filters.periodCode.trim())
  if (filters.subjectCode?.trim()) params.set('subject_code', filters.subjectCode.trim())
  return request<EnglishSubmissionsResponse>(`/api/english/submissions?${params.toString()}`, { cache: 'no-store' })
}

export async function fetchEnglishActivitySchedules(filters: {
  periodCode?: string
  subjectCode?: string
} = {}): Promise<EnglishActivitySchedulesResponse> {
  const params = new URLSearchParams()
  if (filters.periodCode?.trim()) params.set('period_code', filters.periodCode.trim())
  if (filters.subjectCode?.trim()) params.set('subject_code', filters.subjectCode.trim())
  return request<EnglishActivitySchedulesResponse>(`/api/english/activity-schedules?${params.toString()}`, {
    cache: 'no-store',
  })
}

export async function updateEnglishActivitySchedule(payload: {
  period_code: string
  subject_code: string
  component_code: string
  instructions: string
  activity_start: string
  activity_deadline: string
}): Promise<EnglishActivitySchedulesResponse> {
  return request<EnglishActivitySchedulesResponse>('/api/english/activity-schedules', {
    method: 'PUT',
    body: payload,
  })
}

export async function prepareEnglishSubmission(payload: {
  enrollment_id: number
  period_code: string
  subject_code: string
}): Promise<EnglishExam> {
  return request<EnglishExam>('/api/english/submissions/prepare', {
    method: 'POST',
    body: payload,
  })
}

export async function saveEnglishRubricDraft(
  examId: number,
  payload: {
    language_mastery: number
    fluency_pronunciation: number
    content_coherence: number
    instruction_compliance: number
    observation?: string
    period_code: string
    component_code: string
  },
): Promise<EnglishExam> {
  return request<EnglishExam>(`/api/english/submissions/${examId}/draft`, {
    method: 'PUT',
    body: payload,
  })
}

export async function publishEnglishRubricGrade(
  examId: number,
  payload: { period_code: string; component_code: string },
): Promise<EnglishExam> {
  return request<EnglishExam>(`/api/english/submissions/${examId}/publish`, {
    method: 'POST',
    body: payload,
  })
}

export async function updateEnglishActivity(
  examId: number,
  payload: {
    period_code: string
    component_code: string
    instructions: string
    activity_start: string
    activity_deadline: string
  },
): Promise<EnglishExam> {
  return request<EnglishExam>(`/api/english/submissions/${examId}/activity`, {
    method: 'PUT',
    body: payload,
  })
}

export async function reopenEnglishSubmission(
  examId: number,
  payload: {
    period_code: string
    component_code: string
    reason: string
    new_deadline: string
  },
): Promise<EnglishExam> {
  return request<EnglishExam>(`/api/english/submissions/${examId}/reopen`, {
    method: 'POST',
    body: payload,
  })
}

export function englishExamFileUrl(uploadId: string, action: 'open' | 'download'): string {
  return resolveApiPath(`/api/english/files/${encodeURIComponent(uploadId)}/${action}`)
}

export async function fetchDocumentExpedientContext(identification = ''): Promise<DocumentExpedientContext> {
  const params = new URLSearchParams()
  if (identification.trim()) params.set('identification', identification.trim())
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  return request<DocumentExpedientContext>(`/api/document-expedients/context${suffix}`)
}

export async function prepareDocumentExpedient(payload: {
  identification: string
  moduleCode: string
  originId: string
}): Promise<DocumentExpedientPrepareResponse> {
  return request<DocumentExpedientPrepareResponse>('/api/document-expedients/prepare', {
    method: 'POST',
    body: {
      identification: payload.identification,
      module_code: payload.moduleCode,
      origin_id: payload.originId,
    },
  })
}

export async function searchDocumentExpedientStudents(search: string): Promise<DocumentExpedientStudentSearchResponse> {
  const params = new URLSearchParams({ search: search.trim() })
  return request<DocumentExpedientStudentSearchResponse>(`/api/document-expedients/students?${params.toString()}`)
}

export async function createDocumentExpedientUploadSession(payload: {
  identification: string
  moduleCode: string
  originId: string
  documentTypeCode: string
  file: File
}): Promise<DocumentExpedientUploadSessionResponse> {
  return request<DocumentExpedientUploadSessionResponse>('/api/document-expedients/upload-session', {
    method: 'POST',
    body: {
      identification: payload.identification,
      module_code: payload.moduleCode,
      origin_id: payload.originId,
      document_type_code: payload.documentTypeCode,
      filename: payload.file.name,
      size: payload.file.size,
      content_type: payload.file.type || 'application/octet-stream',
    },
  })
}

export async function finalizeDocumentExpedientUpload(uploadId: string): Promise<DocumentExpedientFinalizeResponse> {
  return request<DocumentExpedientFinalizeResponse>('/api/document-expedients/finalize', {
    method: 'POST',
    body: { upload_id: uploadId },
  })
}

export function documentExpedientFileUrl(
  documentGraphId: number,
  action: 'open' | 'download',
): string {
  return resolveApiPath(`/api/document-expedients/files/${documentGraphId}/${action}`)
}

export async function fetchCareerChangeCatalog(query = ''): Promise<CareerChangeCatalogResponse> {
  const params = new URLSearchParams()
  if (query.trim()) params.set('query', query.trim())
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  return request<CareerChangeCatalogResponse>(`/api/requests/career-change/catalog${suffix}`)
}

export async function previewCareerChange(payload: {
  codigo_estud: number
  carrera_destino: number
}): Promise<CareerChangePreviewResponse> {
  return request<CareerChangePreviewResponse>('/api/requests/career-change/preview', {
    method: 'POST',
    body: payload,
  })
}

export async function createCareerChangeRequest(formData: FormData): Promise<CareerChangeActionResponse> {
  return request<CareerChangeActionResponse>('/api/requests/career-change', {
    method: 'POST',
    body: formData,
  })
}

export async function fetchCareerChangeRequests(params: {
  query?: string
  state?: string
  limit?: number
} = {}): Promise<CareerChangeRequestsResponse> {
  const query = new URLSearchParams()
  if (params.query?.trim()) query.set('query', params.query.trim())
  if (params.state?.trim()) query.set('state', params.state.trim())
  query.set('limit', String(params.limit ?? 100))
  return request<CareerChangeRequestsResponse>(`/api/requests/career-change?${query.toString()}`)
}

export async function fetchCareerChangeRequestDetail(requestId: number): Promise<CareerChangeRequestDetail> {
  return request<CareerChangeRequestDetail>(`/api/requests/career-change/${requestId}`)
}

export async function decideCareerChangeRequest(
  requestId: number,
  decision: 'APROBADA' | 'RECHAZADA',
  observacion: string,
): Promise<CareerChangeActionResponse> {
  return request<CareerChangeActionResponse>(`/api/requests/career-change/${requestId}/decision`, {
    method: 'POST',
    body: { decision, observacion },
  })
}

export async function applyCareerChangeRequest(requestId: number): Promise<CareerChangeActionResponse> {
  return request<CareerChangeActionResponse>(`/api/requests/career-change/${requestId}/apply`, {
    method: 'POST',
  })
}

export async function restoreCareerChangeBackup(requestId: number): Promise<CareerChangeActionResponse> {
  return request<CareerChangeActionResponse>(`/api/requests/career-change/${requestId}/restore`, {
    method: 'POST',
  })
}
