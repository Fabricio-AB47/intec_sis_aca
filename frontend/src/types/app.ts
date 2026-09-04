export type Role =
  | 'ADMINISTRADOR'
  | 'FINANCIERO'
  | 'BIENESTAR'
  | 'ACADEMICO'
  | 'ADMISIONES'
  | 'RECTOR'
  | 'VICERRECTOR'
  | 'SOPORTE'
  | 'INVITADO_SOP'
  | 'SECRETARIA'
  | 'DOCENTE'
  | 'ESTUDIANTE'

export type UserProfile = {
  login: string
  nombres?: string
  email?: string
  id_usuario?: number
  rol: Role
  codigo_estud?: number
  codigo_doc?: number
  cedula?: string
  origen?: string
}

export type UserSession = UserProfile & {
  perfiles?: UserProfile[]
}

export type ScreenPermissionCode = string

export type ScreenAccessScreen = {
  page: ScreenPermissionCode
  label: string
  description: string
  group: string
  parent_page?: Page | ''
  kind?: 'screen' | 'flow'
}

export type ScreenAccessRole = {
  value: Role
  label: string
  description: string
  pages: ScreenPermissionCode[]
  default_pages: ScreenPermissionCode[]
  configured: boolean
  protected: boolean
  updated_at?: string | null
  updated_by?: string | null
}

export type ScreenAccessResponse = {
  source: string
  synchronized_at: string
  current_role: Role
  screens: ScreenAccessScreen[]
  roles: ScreenAccessRole[]
}

export type Page =
  | 'dashboard'
  | 'sistema-academico'
  | 'teams'
  | 'teams-matricula'
  | 'moodle-teams'
  | 'historico-integraciones'
  | 'informe-cumplimiento'
  | 'moodle'
  | 'matricula'
  | 'matricula-acad'
  | 'matricula-docente'
  | 'solicitudes-cambio-carrera'
  | 'solicitudes-cambio-modalidad'
  | 'estado-docente'
  | 'senescyt-estudiantes'
  | 'actualizar-datos-estudiante'
  | 'actualizar-correo-intec'
  | 'preinscripcion'
  | 'reporteria-carreras'
  | 'reporteria-integral'
  | 'reportes-individuales'
  | 'admin-notas-asignatura'
  | 'asignacion-pantallas'
  | 'gestion-sisacademico'
  | 'periodo-academico'
  | 'periodo-matriculados'
  | 'ingreso-ventas'
  | 'cruce-datos'
  | 'validar-excel'
  | 'actualizar-malla-carrera'
  | 'rango-edades'
  | 'fecha-grado'
  | 'titulacion'
  | 'titulacion-proceso'
  | 'titulacion-responsables'
  | 'titulos-registrados'
  | 'certificados'
  | 'matricula-excel-certificados'
  | 'renombrar-certificados'
  | 'credenciales'
  | 'correos-masivos'
  | 'carnet-institucional'
  | 'evaluacion-docente'
  | 'evaluacion-docente-admin'
  | 'evaluacion-docente-avance'
  | 'evaluacion-docente-reportes'
  | 'portal-estudiante'
  | 'portal-estudiante-malla-curricular'
  | 'portal-estudiante-malla-academica'
  | 'portal-estudiante-calificaciones'
  | 'ingles'
  | 'expedientes-documentales'
  | 'portal-docente'
  | 'portal-docente-informe'
  | 'portal-docente-planificacion'
  | 'portal-docente-contratos'
  | 'formato-informe-docente'
  | 'practicas-institucionales'

export type CareerChangeCatalogStudent = {
  codigo_estud: number
  cedula: string
  estudiante: string
  estado: string
  carrera: number | null
  carrera_nombre: string
}

export type CareerChangeCareer = {
  codigo: number
  nombre: string
}

export type CareerChangePeriod = {
  codigo: number
  nombre: string
  fecha_inicio?: string | null
  fecha_fin?: string | null
}

export type CareerChangeCatalogResponse = {
  students: CareerChangeCatalogStudent[]
  careers: CareerChangeCareer[]
  periods: CareerChangePeriod[]
  states: string[]
}

export type CareerChangeSubject = {
  codigo_materia: number
  codigo_comun: string
  nombre: string
  nivel: number | null
  creditos: number
}

export type CareerChangeSourceSubject = CareerChangeSubject & {
  carrera: number | null
  periodo: number | null
  periodo_nombre: string
  nota_final: number | null
}

export type CareerChangeMatch = {
  source: CareerChangeSourceSubject
  target: CareerChangeSubject
  tipo_coincidencia: 'CODIGO_EXACTO' | 'NOMBRE_EXACTO' | 'NOMBRE_SIMILAR'
  similitud: number
  seleccion_recomendada: boolean
}

export type CareerChangeFailedMatch = CareerChangeMatch & {
  accion: 'REPETIR'
}

export type CareerChangePreviewResponse = {
  student: {
    codigo_estud: number
    cedula: string
    estudiante: string
    estado: string
    carrera_origen: number
    carrera_origen_nombre: string
    periodo_origen: number | null
  }
  target_career: CareerChangeCareer
  matches: CareerChangeMatch[]
  failed_matches: CareerChangeFailedMatch[]
  unmatched_targets: CareerChangeSubject[]
  unused_approved_sources: Array<CareerChangeSubject & {
    nota_final: number | null
    periodo: number | null
    periodo_nombre: string
  }>
  summary: {
    aprobadas_origen: number
    reprobadas_origen: number
    equivalencias_exactas: number
    equivalencias_similares: number
    materias_destino_sin_equivalencia: number
    materias_por_repetir: number
  }
}

export type CareerChangeRequestItem = {
  id: number
  codigo_estud: number
  cedula: string
  estudiante: string
  carrera_origen: number
  carrera_origen_nombre: string
  carrera_destino: number
  carrera_destino_nombre: string
  codigo_periodo_destino: number
  periodo_destino_nombre: string
  estado: 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'APLICADA'
  motivo: string
  archivo_nombre: string
  archivo_url: string
  expediente_documento_id?: number | null
  archivo_en_expediente?: boolean
  estado_expediente?: string
  creado_por: string
  fecha_creacion: string | null
  revisado_por: string
  fecha_revision: string | null
  observacion_revision: string
  aplicado_por: string
  fecha_aplicacion: string | null
  equivalencias: number
  materias_por_repetir: number
  respaldo_estado: '' | 'DISPONIBLE' | 'RESTAURADO'
  respaldo_cabeceras: number
  respaldo_materias: number
  fecha_respaldo: string | null
  restauraciones: number
  fecha_ultima_restauracion: string | null
  auditoria_id: number | null
  auditoria_hash: string
}

export type CareerChangeStoredEquivalence = {
  id: number
  materia_origen: number
  codigo_comun_origen: string
  nombre_materia_origen: string
  periodo_origen: number | null
  periodo_origen_nombre: string
  nota_final: number | null
  materia_destino: number
  codigo_comun_destino: string
  nombre_materia_destino: string
  nivel_destino: number | null
  creditos_destino: number | null
  tipo_coincidencia: string
  similitud: number
  seleccionada: boolean
  repetir: boolean
}

export type CareerChangeRequestDetail = CareerChangeRequestItem & {
  equivalences: CareerChangeStoredEquivalence[]
}

export type CareerChangeRequestsResponse = {
  total: number
  items: CareerChangeRequestItem[]
}

export type CareerChangeActionResponse = {
  ok: boolean
  message: string
  estado: string
  id?: number
  equivalencias_seleccionadas?: number
  materias_por_repetir?: number
  inserted?: number
  existing_skipped?: number
  respaldo_cabeceras?: number
  respaldo_materias?: number
  source_headers_archived?: number
  source_subjects_archived?: number
  cabeceras_restauradas?: number
  materias_restauradas?: number
  existentes_omitidos?: number
  auditoria_id?: number
  repeated?: number
}

export type ModalityChangeCatalogStudent = {
  codigo_estud: number
  cedula: string
  estudiante: string
  estado: string
  carrera: number | null
  carrera_nombre: string
  modalidad: number | null
  modalidad_nombre: string
  jornada_codigo?: number | null
  jornada_nombre?: string
  periodo?: number | null
  periodo_nombre?: string
  tipo_periodo?: 'R' | 'H' | ''
}

export type ModalityChangeOption = {
  codigo: number
  nombre: string
  jornada_codigo: number
  jornada_nombre: string
}

export type ModalityChangePeriod = CareerChangePeriod & {
  estado: string
  tipo: 'R' | 'H'
}

export type ModalityChangeCatalogResponse = {
  students: ModalityChangeCatalogStudent[]
  careers: CareerChangeCareer[]
  modalities: ModalityChangeOption[]
  periods: ModalityChangePeriod[]
  states: string[]
}

export type ModalityChangeSubject = CareerChangeSubject & {
  estado: 'MIGRAR' | 'MIGRADA' | 'MATRICULAR' | 'REPETIR' | 'PENDIENTE' | 'EXISTENTE' | 'MATRICULADA'
  num_matricula: number | null
  materia_origen?: number | null
  codigo_comun_origen?: string
  nota_origen?: number | null
  tiene_notas_origen?: boolean
  requiere_repeticion?: boolean
  observacion?: string
  id?: number
}

export type ModalityChangePreviewResponse = {
  student: ModalityChangeCatalogStudent & { periodo: number | null; correo?: string }
  target_career: CareerChangeCareer
  target_modality: ModalityChangeOption
  source_period: ModalityChangePeriod
  homologation_period: ModalityChangePeriod
  subjects: ModalityChangeSubject[]
  unmatched_source_subjects: Array<{
    codigo_materia: number | null
    codigo_comun: string
    nombre: string
    nota_final: number | null
    tiene_notas: boolean
  }>
  summary: {
    materias_pensum: number
    materias_origen: number
    materias_a_migrar: number
    materias_por_matricular: number
    materias_por_repetir: number
    materias_existentes: number
    materias_origen_sin_coincidencia: number
    cabecera_existente: boolean
    cabeceras_a_crear: number
  }
}

export type ModalityChangeRequestItem = {
  id: number
  codigo_estud: number
  cedula: string
  estudiante: string
  carrera_origen: number
  carrera_origen_nombre: string
  carrera_destino: number
  carrera_destino_nombre: string
  modalidad_origen: number | null
  modalidad_origen_nombre: string
  codigo_periodo_origen: number | null
  periodo_origen_nombre: string
  tipo_periodo_origen: 'R' | 'H' | ''
  modalidad_destino: number
  modalidad_destino_nombre: string
  codigo_periodo_homologacion: number
  periodo_homologacion_nombre: string
  tipo_periodo_destino: 'R' | 'H'
  estado: 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'APLICADA'
  motivo: string
  archivo_nombre: string
  archivo_url: string
  expediente_documento_id?: number | null
  archivo_en_expediente?: boolean
  estado_expediente?: string
  archivos?: ModalityChangeDocument[]
  total_archivos?: number
  total_materias_pensum: number
  materias_matriculadas: number
  materias_existentes: number
  materias_migradas: number
  materias_origen_retiradas: number
  cabeceras_origen_retiradas: number
  cabecera_creada: boolean | null
  respaldo_id: number | null
  respaldo_cabeceras: number
  respaldo_materias: number
  respaldo_hash: string
  fecha_respaldo: string | null
  auditoria_id: number | null
  auditoria_hash: string
  creado_por: string
  fecha_creacion: string | null
  revisado_por: string
  fecha_revision: string | null
  observacion_revision: string
  aplicado_por: string
  fecha_aplicacion: string | null
}

export type ModalityChangeDocument = {
  id: number | null
  orden: number
  nombre_original: string
  nombre: string
  archivo_url: string
  expediente_documento_id: number | null
  estado: string
  tamano: number
  sha256: string
  fecha_carga: string | null
}

export type ModalityChangeRequestDetail = ModalityChangeRequestItem & {
  subjects: ModalityChangeSubject[]
}

export type ModalityChangeRequestsResponse = {
  total: number
  items: ModalityChangeRequestItem[]
}

export type ModalityChangeActionResponse = {
  ok: boolean
  message: string
  estado: string
  id?: number
  archivos_cargados?: number
  materias_pensum?: number
  cabeceras_a_crear?: number
  cabeceras_creadas?: number
  materias_matriculadas?: number
  materias_existentes?: number
  materias_migradas?: number
  materias_repetidas?: number
  materias_origen_retiradas?: number
  cabeceras_origen_retiradas?: number
  respaldo_id?: number
  auditoria_id?: number
}

export type IntegrationHistoryPage<T> = {
  items: T[]
  page: number
  page_size: number
  total: number
  total_pages: number
  has_previous: boolean
  has_next: boolean
}

export type IntegrationDatabaseEvent = {
  id: number
  fecha_utc: string
  fecha_ecuador: string
  base_datos: string
  esquema: string
  objeto: string
  operacion: 'INSERT' | 'UPDATE' | 'DELETE'
  cantidad_filas: number
  muestra_limitada: boolean
  usuario: string
  rol?: string | null
  origen?: string | null
  solicitud?: string | null
  metodo?: string | null
  ruta?: string | null
}

export type IntegrationTeacherReportEvent = {
  id: number
  fecha_utc: string
  fecha_ecuador: string
  etapa: 'GENERADO' | 'FIRMADO' | 'ARCHIVADO' | 'ERROR'
  estado: 'EXITOSO' | 'ERROR'
  tipo_documento: string
  codigo_docente?: string | null
  cedula_docente?: string | null
  nombre_docente?: string | null
  codigo_materia?: string | null
  nombre_materia?: string | null
  paralelo?: string | null
  nombre_archivo?: string | null
  ruta_documento?: string | null
  cantidad_estudiantes?: number | null
  usuario: string
  rol?: string | null
  solicitud?: string | null
  detalle?: string | null
}

export type IntegrationHistorySummary = {
  changes_last_24_hours: {
    inserts: number
    updates: number
    deletes: number
    total: number
  }
  teacher_reports_last_30_days: {
    total: number
    generated: number
    signed: number
    archived: number
    errors: number
  }
  coverage: {
    installed: number
    pending: number
    total: number
  }
  databases: string[]
}

export type IntegrationHistoryDetail = {
  kind: 'database' | 'teacher-report'
  event: Record<string, unknown>
}

export type ComplianceDocumentType =
  | 'INFORME'
  | 'NOTAS'
  | 'CONTRATO'
  | 'PAQUETE'
  | 'FACTURA_XML'
  | 'RIDE'
  | 'CARPETA'
  | 'OTRO'

export type ComplianceDocumentItem = {
  id: string
  event_id: number
  fecha_utc: string
  fecha_ecuador: string
  codigo_docente?: string | null
  cedula_docente?: string | null
  nombre_docente?: string | null
  codigo_materia?: string | null
  nombre_materia?: string | null
  periodos: string[]
  paralelo?: string | null
  jornada?: string | null
  ruta_carpeta?: string | null
  url_carpeta?: string | null
  detalle?: string | null
  documento_id?: string | null
  nombre_documento: string
  tipo_documento: ComplianceDocumentType
  url_documento?: string | null
}

export type ComplianceDocumentsResponse = IntegrationHistoryPage<ComplianceDocumentItem> & {
  summary: {
    documents: number
    packages: number
    teachers: number
  }
}

export type ComplianceInvoiceBackupUploadResponse = {
  message: string
  event_id: number
  backup_id: string
  folder_path: string
  folder_url?: string | null
  documents: Array<{
    id?: string | null
    nombre: string
    nombre_original: string
    url?: string | null
    tipo_documento: 'FACTURA_XML' | 'RIDE'
    content_type: string
    tamano_bytes: number
    respaldo_factura_id: string
  }>
}

export type MoodleStatusResponse = {
  enabled: boolean
  configured: boolean
  reachable: boolean
  site_name: string
  site_url: string
  moodle_username: string
  moodle_user_id: number
  moodle_release: string
  moodle_version: string
  user_is_site_admin: boolean
  user_status_updates_enabled: boolean
  section_updates_enabled: boolean
  evaluation_date_updates_enabled: boolean
  evaluation_date_update_function: string
  evaluation_date_update_function_available: boolean
  evaluation_date_update_reason: string
  functions_count: number
  required_functions: string[]
  missing_required_functions: string[]
}

export type MoodlePagination = {
  page: number
  page_size: number
  total_items: number
  total_pages: number
  has_previous: boolean
  has_next: boolean
}

export type MoodleSource = {
  cached: boolean
  fetched_at: string
  moodle_function: string
}

export type MoodleUser = {
  id: number
  username: string
  firstname: string
  lastname: string
  fullname: string
  email: string
  idnumber: string
  institution: string
  department: string
  auth: string
  suspended: boolean
  confirmed: boolean
  firstaccess: number
  lastaccess: number
  profileimageurlsmall: string
  status: 'ACTIVO' | 'SUSPENDIDO' | 'NO_CONFIRMADO'
}

export type MoodleCourse = {
  id: number
  fullname: string
  displayname: string
  shortname: string
  idnumber: string
  categoryid: number
  categoryname: string
  summary: string
  format: string
  visible: boolean
  startdate: number
  enddate: number
  enablecompletion: boolean
  timecreated: number
  timemodified: number
}

export type MoodlePagedResponse<T> = {
  items: T[]
  pagination: MoodlePagination
  source: MoodleSource
}

export type MoodleUsersResponse = MoodlePagedResponse<MoodleUser>
export type MoodleCoursesResponse = MoodlePagedResponse<MoodleCourse>

export type MoodleCourseContent = {
  type: string
  filename: string
  filepath: string
  filesize: number
  fileurl: string
  timecreated: number
  timemodified: number
  sortorder: number
  userid: number
  author: string
  license: string
  mimetype: string
  isexternalfile: boolean
  repositorytype: string
}

export type MoodleCourseDate = {
  label: string
  timestamp: number
  dataid: string
}

export type MoodleCourseCompletion = {
  state: number
  timecompleted: number
  overrideby: number
  valueused: boolean
  hascompletion: boolean
  uservisible: boolean
}

export type MoodleCourseLink = {
  name: string
  url: string
  provider: string
  domain: string
}

export type MoodleCourseModule = {
  id: number
  url: string
  name: string
  instance: number
  contextid: number
  visible: boolean
  uservisible: boolean
  visibleoncoursepage: boolean
  availabilityinfo: string
  description: string
  modicon: string
  modname: string
  modplural: string
  indent: number
  noviewlink: boolean
  completion: number
  completiondata: MoodleCourseCompletion
  dates: MoodleCourseDate[]
  links: MoodleCourseLink[]
  contents: MoodleCourseContent[]
  planning_document_types?: Array<'pea' | 'silabo'>
}

export type MoodleCourseSection = {
  id: number
  section: number
  name: string
  summary: string
  visible: boolean
  uservisible: boolean
  edit_url: string
  can_update_visibility: boolean
  can_update_name: boolean
  modules: MoodleCourseModule[]
}

export type MoodleCourseResourcesResponse = {
  course: MoodleCourse
  sections: MoodleCourseSection[]
  totals: {
    sections: number
    modules: number
    files: number
    links: number
    visible_modules: number
  }
  source: MoodleSource
  section_management: {
    name_updates_enabled: boolean
    visibility_updates_enabled: boolean
    full_edit_in_moodle: boolean
  }
}

export type MoodleEditableContentType = 'section' | 'label' | 'page'

export type MoodleEditableContentItem = {
  target_type: Exclude<MoodleEditableContentType, 'section'>
  target_id: number
  cmid?: number
  name: string
  html: string
  visible: boolean
}

export type MoodleEditableContentSection = {
  target_id: number
  section_number?: number
  display_name: string
  name: string
  html: string
  visible: boolean
  items: MoodleEditableContentItem[]
}

export type MoodleEditableContentResponse = {
  course: MoodleCourse
  sections: MoodleEditableContentSection[]
  totals: {
    sections: number
    items: number
  }
  source: MoodleSource
  editor: {
    enabled: boolean
    reason: string
  }
}

export type MoodleEditableContentUpdateResponse = {
  ok: boolean
  changed: boolean
  message: string
}

export type MoodleEvaluationDates = {
  allowsubmissionsfromdate: number
  duedate: number
  cutoffdate: number
  timeopen: number
  timeclose: number
}

export type MoodleEvaluationActivity = {
  cmid: number
  instance: number
  modname: 'assign' | 'quiz'
  type_label: string
  name: string
  url: string
  section_id: number
  section_number: number
  section_name: string
  visible: boolean
  uservisible: boolean
  scope: 'simuladores' | 'evaluaciones' | 'sin_clasificar'
  scope_label: string
  partial: number
  partial_label: string
  programmable: boolean
  dates: MoodleEvaluationDates
}

export type MoodleEvaluationDateManagement = {
  enabled: boolean
  configured: boolean
  function: string
  function_available: boolean
  reason: string
}

export type MoodleCourseEvaluationsResponse = {
  course: MoodleCourse
  activities: MoodleEvaluationActivity[]
  totals: {
    activities: number
    assignments: number
    quizzes: number
    with_dates: number
    programmable: number
    unclassified: number
    simulators: number
    evaluations: number
  }
  source: MoodleSource
  date_management: MoodleEvaluationDateManagement
}

export type MoodleEvaluationDateUpdate = {
  cmid: number
  modname: 'assign' | 'quiz'
  instance: number
  allowsubmissionsfromdate?: number
  duedate?: number
  cutoffdate?: number
  timeopen?: number
  timeclose?: number
}

export type MoodleEvaluationDatesUpdateResponse = {
  ok: boolean
  changed: boolean
  message: string
  updated_count: number
  activities: MoodleEvaluationActivity[]
  audit_records: number
}

export type MoodleGradePeriodOption = {
  period_code: number
  period_name: string
  period_type: 'R' | 'H'
  course_code: string
  matter: string
  career: string
  career_count?: number
  students: number
}

export type MoodleInstitutionalIdentityValidation = {
  moodle_student_users: number
  moodle_users_with_institutional_email: number
  moodle_identity_from_email: number
  moodle_identity_from_username: number
  moodle_identity_conflicts: number
  moodle_users_without_institutional_email: number
  duplicate_moodle_emails: number
  unique_moodle_institutional_emails: number
  moodle_registry_email_reconciled: number
  moodle_registry_reconciliation_conflicts: number
}

export type MoodleGradeCourseOption = {
  id: number
  name: string
  shortname: string
  idnumber: string
  matched_course_code: string
  matched_course_codes?: string[]
  has_academic_match: boolean
  recommended_period_code?: number | null
  recommended_period_codes?: number[]
  identity_key?: 'CorreoIntec'
  identity_relation?: string
  match_method?:
    | 'codigo_pensum_y_correointec'
    | 'asignatura_pensum_y_correointec'
    | 'codigo_y_correointec'
    | 'asignatura_y_correointec'
    | ''
  matched_students?: number
  moodle_users?: number
  moodle_users_with_email?: number
  moodle_identity_validation?: MoodleInstitutionalIdentityValidation
  resolution_reason?: string
  periods: MoodleGradePeriodOption[]
}

export type MoodleGradeCatalogResponse = {
  enabled: boolean
  apply_enabled: boolean
  nightly_enabled: boolean
  change_detection_enabled: boolean
  change_detection_interval_minutes: number
  configured_mappings: Array<{ course_id: number; period_code: number }>
  totals: {
    courses: number
    matched: number
    unmatched: number
  }
  courses: MoodleGradeCourseOption[]
}

export type MoodleGradeChange = {
  student_code: number
  student: string
  identity: string
  email: string
  email_source: string
  moodle_email: string
  moodle_email_source: string
  identity_match_method: string
  registry_email_mismatch: boolean
  moodle_user_id: number
  course_enrollment_validated: boolean
  career: string
  matter: string
  period: string
  period_code: number
  type: 'R' | 'H'
  row_id: number
  field:
    | 'P1Tareas'
    | 'P1Proyectos'
    | 'P1Examen'
    | 'P2Tareas'
    | 'P2Proyectos'
    | 'P2Examen'
    | 'P3Tareas'
    | 'P3Proyectos'
    | 'P3Examen'
    | 'teoriaHomo'
    | 'practicahomo'
  component: string
  current_grade: number | null
  incoming_grade: number
  previous_synced_grade: number | null
  moodle_grade_item: string
  moodle_grade_item_count?: number
  moodle_grade_items?: string[]
  moodle_grade_candidates?: Array<{
    item_id: number
    item_name: string
    grade: number
    activity_type: 'quiz' | 'assign' | string
    selected: boolean
  }>
  moodle_grade_selection?: 'single_grade' | 'highest_grade'
  moodle_partial_label?: string
  moodle_partial_segment?: string
  moodle_partial_source?: 'segment' | 'label' | 'section' | 'metadata' | 'label_metadata' | 'activity' | 'section_inheritance' | 'section_order'
  moodle_raw_grade?: number | null
  moodle_grade_min?: number | null
  moodle_grade_max?: number | null
  moodle_grade_raw_source?: string
  moodle_grade_scale_source?: string
  duplicated_generic_grade: boolean
  duplicated_component_grade?: boolean
  status: string
  reason: string
}

export type MoodleGradeEnrollmentWarning = {
  student_code: number
  student: string
  identity: string
  email: string
  email_source: string
  moodle_email: string
  moodle_email_source: string
  identity_match_method: string
  registry_email_mismatch: boolean
  moodle_user_id: number
  course_enrollment_validated: boolean
  career: string
  matter: string
  period: string
  period_code: number
  type: 'R' | 'H'
  malla_code?: number
  matter_code?: number
  parallel?: string
  status: string
  reason: string
}

export type MoodleGradeAlertKind = 'SIN_CALIFICAR' | 'REVISAR' | 'DATOS'
export type MoodleGradeAlertSeverity = 'alert' | 'warning'

export type MoodleGradeAlertComponent = {
  field: MoodleGradeChange['field']
  component: string
  academic_grade: number | null
  academic_registered: boolean
  moodle_grade: number | null
  moodle_registered: boolean
  previous_synced_grade: number | null
  moodle_grade_item_id: number
  moodle_grade_item: string
  moodle_grade_item_count: number
  moodle_grade_items: string[]
  moodle_grade_selection: string
  moodle_raw_grade: number | null
  moodle_grade_min: number | null
  moodle_grade_max: number | null
  moodle_grade_raw_source: string
  moodle_grade_scale_source: string
  status: string
  reason: string
}

export type MoodleGradeAlertItem = {
  id: string
  kind: MoodleGradeAlertKind
  severity: MoodleGradeAlertSeverity
  status: string
  student_code: number
  student: string
  identity: string
  email: string
  email_source: string
  moodle_email: string
  moodle_user_id: number
  course_enrollment_validated: boolean
  teacher_codes: number[]
  teacher: string
  teacher_assignments: Array<{
    teacher_code: number
    teacher: string
  }>
  course_id: number
  course: string
  course_code: string
  malla_code: number
  matter_code: number
  matter: string
  career: string
  period_code: number
  period: string
  type: 'R' | 'H' | string
  parallel: string
  record_id: number
  enrollment_number: number
  group_number: number
  recovery_grade: number | null
  final_grade: number | null
  approval: string
  missing_components: string[]
  academic_missing_components: string[]
  moodle_missing_components: string[]
  missing_sources: string[]
  message: string
  component_details: MoodleGradeAlertComponent[]
  moodle_checked: boolean
  moodle_error: string
  moodle_courses: Array<{
    course_id: number
    course: string
    course_code: string
  }>
}

export type MoodleGradeAlertSummary = {
  total: number
  ungraded: number
  review: number
  data_issues: number
  courses: number
  students: number
  teachers: number
  assignments: number
  errors: number
  missing_intecbdd: number
  missing_moodle: number
  missing_both: number
  regular: number
  homologation: number
}

export type MoodleGradeAlertResponse = {
  scope: 'DOCENTE' | 'INSTITUCIONAL'
  role: string
  generated_at: string
  cached: boolean
  summary: MoodleGradeAlertSummary
  validation: MoodleGradeCourseValidation
  items: MoodleGradeAlertItem[]
  errors: Array<{
    course_id: number
    period_codes: number[]
    message: string
  }>
}

export type MoodleGradeCourseValidation = {
  selected_periods: number
  academic_enrollments: number
  moodle_course_users: number
  matched_by_email: number
  matched_by_registry: number
  matched_by_data_fallback: number
  matched_by_reconciled_identity: number
  missing_institutional_email: number
  not_enrolled_in_course: number
  ambiguous_users: number
  moodle_student_users: number
  moodle_users_with_institutional_email: number
  moodle_identity_from_email: number
  moodle_identity_from_username: number
  moodle_identity_conflicts: number
  moodle_users_without_institutional_email: number
  duplicate_moodle_emails: number
  unique_moodle_institutional_emails: number
  moodle_registry_email_reconciled: number
  moodle_registry_reconciliation_conflicts: number
}

export type MoodleGradePreviewResponse = {
  course: { id: number; name: string; code: string }
  period: { code: number; name: string; type: 'R' | 'H' }
  periods: Array<{ code: number; name: string; type: 'R' | 'H' }>
  selected_period_codes: number[]
  rule: string
  generated_at: string
  replace_existing: boolean
  counts: Record<string, number>
  course_validation: MoodleGradeCourseValidation
  changes: MoodleGradeChange[]
  enrollment_warnings: MoodleGradeEnrollmentWarning[]
  can_apply: boolean
}

export type MoodleGradeApplyResponse = MoodleGradePreviewResponse & {
  applied: number
  runtime_conflicts?: MoodleGradeChange[]
  message: string
}

export type MoodleGradeHistoryItem = {
  id: number
  fecha_inicio: string
  fecha_fin: string | null
  duracion_segundos: number | null
  periodo: number
  modo_ejecucion: string
  estado: string
  notas_procesadas: number
  notas_actualizadas: number
  notas_insertadas: number
  notas_error: number
  mensaje: string
  usuario_id: string
}

export type MoodleGradeHistoryResponse = {
  items: MoodleGradeHistoryItem[]
  total: number
}

export type PortalTeacherComplianceMoodleCourse = MoodleCourse & {
  match_score: number
  match_reasons: string[]
  subject_code_similarity: number
  student_email_matches: number
  student_email_total: number
  student_email_coverage: number
  validated_by_email: boolean
}

export type PortalTeacherComplianceGradeStudent = {
  codigo_estud: number | null
  cedula: string
  nombre_estudiante: string
  correo_intec: string
  nombre_carrera: string
  detalle_periodo: string
  promedio_final: number | null
}

export type PortalTeacherComplianceGradeValidation = {
  passing_grade: number
  failed_threshold_percent: number
  justification_min_length: number
  total_records: number
  graded_records: number
  missing_academic_count: number
  failed_count: number
  failed_percentage: number
  requires_justification: boolean
  can_generate: boolean
  blockers: string[]
  missing_academic_students: PortalTeacherComplianceGradeStudent[]
  failed_students: PortalTeacherComplianceGradeStudent[]
  students_without_email: PortalTeacherComplianceGradeStudent[]
  moodle: {
    checked: boolean
    course_id: number | null
    course_name: string
    error: string
    verified_students: number
    not_enrolled_students: PortalTeacherComplianceGradeStudent[]
    missing_grade_students: PortalTeacherComplianceGradeStudent[]
    discrepancies: Array<PortalTeacherComplianceGradeStudent & {
      nota_moodle: number
      notas_intec: number[]
    }>
  }
}

export type PortalTeacherComplianceMoodleResourcesResponse = {
  matched: boolean
  academic: {
    nombre_materia: string
    cod_materia: string
    codigo_materia: string
    nombre_carrera: string
    detalle_periodo: string
    paralelo: string
  }
  candidates: PortalTeacherComplianceMoodleCourse[]
  selected_course_id: number | null
  resources: MoodleCourseResourcesResponse | null
  student_email_validation: {
    mode: 'moodle_enrollment' | 'institutional_email_missing'
    email_source: string
    requested_students: number
    students_with_email: number
    students_without_registry_email: number
    matched_students: number
    unmatched_students: number
  }
  grade_validation: PortalTeacherComplianceGradeValidation
}

export type TeacherComplianceMoodleResource = {
  course_id: number
  course_name: string
  section_id: number
  section_name: string
  module_id: number
  name: string
  module_type: string
  visible: boolean
  file_count: number
  file_names: string[]
  planning_document_types: Array<'pea' | 'silabo'>
  web_url: string
  source: 'Moodle'
}

export type MoodleSectionUpdateResponse = {
  ok: boolean
  changed: boolean
  message: string
  section: MoodleCourseSection
  audit_recorded: boolean
}

export type MoodleSectionNameUpdateResponse = MoodleSectionUpdateResponse
export type MoodleSectionVisibilityUpdateResponse = MoodleSectionUpdateResponse

export type MoodleInstitutionalEmailValidation = {
  validated: boolean
  codigo_estud: number
  estudiante: string
  correo_intec: string
}

export type MoodleUserStatusUpdateResponse = {
  ok: boolean
  changed: boolean
  message: string
  user: MoodleUser
  institutional_validation: MoodleInstitutionalEmailValidation
  audit_recorded: boolean
}

export type EnglishExamFile = {
  upload_id: string
  name: string
  content_type: string
  size: number
  version: number
  uploaded_at: string | null
  web_url: string
  delivery_state: string
  confirmed: boolean
  confirmed_at: string | null
  integrity_validated: boolean
  integrity_hash: string
}

export type EnglishRubric = {
  language_mastery: number
  fluency_pronunciation: number
  content_coherence: number
  instruction_compliance: number
}

export type EnglishExamStudent = {
  code: number
  identification: string
  name: string
  career: string
  career_code: string
  period_code: string
}

export type EnglishExamComponent = {
  component_id: number
  code: 'P1' | 'P2' | 'P3' | string
  number: number
  label: string
  evaluation_type: string
  grade: number | null
  result: 'APROBADO' | 'REPROBADO' | 'PENDIENTE' | string
  status: string
  observation: string
  evaluator: string
  graded_at: string | null
  file: EnglishExamFile | null
  delivery_state: string
  confirmed: boolean
  can_confirm: boolean
  can_edit: boolean
  edit_deadline: string | null
  seconds_remaining: number
  activity_start: string | null
  activity_deadline: string | null
  activity_instructions: string
  activity_open: boolean
  activity_status: string
  review_state: string
  draft_grade: number | null
  draft_observation: string
  draft_rubric: EnglishRubric | null
  drafted_at: string | null
  drafted_by: string
  published_at: string | null
  published_by: string
  notification_state: string
  reopen_count: number
  last_reopened_at: string | null
  last_reopen_reason: string
  last_reopened_by: string
}

export type EnglishEnrollment = {
  enabled: boolean
  enrollment_id: number
  english_career_code: string
  english_career: string
  subject_code: string
  subject: string
  period_code: string
  period: string
  parallel: string
}

export type EnglishExam = {
  exam_id: number | null
  expedient_id: number | null
  level: string
  enrollment_type: 'R' | 'H' | string
  scheme: string
  status: string
  grade: number | null
  result: 'APROBADO' | 'REPROBADO' | 'PENDIENTE' | string
  passing_grade: number
  observation: string
  evaluator: string
  graded_at: string | null
  file: EnglishExamFile | null
  components: EnglishExamComponent[]
  required_components: number
  submitted_components: number
  staged_components: number
  graded_components: number
  can_edit: boolean
  edit_deadline: string | null
  seconds_remaining: number
  edit_window_minutes: number
  min_file_bytes: number
  max_file_bytes: number
  enrollment: EnglishEnrollment
  student: EnglishExamStudent
}

export type EnglishUploadSessionResponse = {
  upload_id: string
  upload_url: string
  expires_at: string
  chunk_size: number
  min_file_bytes: number
  max_file_bytes: number
  version: number
  component_code: string
}

export type EnglishSubmissionsResponse = {
  items: EnglishExam[]
  enrolled: number
  total: number
  pending: number
  approved: number
  failed: number
  periods: Array<{
    code: string
    name: string
    label: string
    student_count: number
  }>
  selected_period_code: string
  subjects: Array<{
    code: string
    name: string
    label: string
    student_count: number
  }>
  selected_subject_code: string
  reviewer: { name: string; role: string }
}

export type EnglishActivitySchedule = {
  code: 'P1' | 'P2' | 'P3' | string
  number: number
  label: string
  instructions: string
  activity_start: string | null
  activity_deadline: string | null
  activity_open: boolean
  activity_status: string
  configured: boolean
  updated_at: string | null
  updated_by: string
}

export type EnglishActivitySchedulesResponse = {
  periods: Array<{
    code: string
    name: string
    label: string
    student_count: number
  }>
  selected_period_code: string
  subjects: Array<{
    code: string
    name: string
    label: string
    student_count: number
  }>
  selected_subject_code: string
  components: EnglishActivitySchedule[]
  affected_students: number
  administrator: { name: string }
  updated_components?: number
  skipped_published?: number
}

export type DocumentExpedientStudent = {
  code: number
  identification: string
  name: string
  email: string
  career_code: string
  career: string
  period_code: string
  status: string
}

export type DocumentExpedientStudentSearchItem = {
  code: number
  identification: string
  name: string
  status: string
}

export type DocumentExpedientStudentSearchResponse = {
  items: DocumentExpedientStudentSearchItem[]
  total: number
}

export type DocumentExpedientType = {
  code: string
  name: string
}

export type DocumentExpedientFile = {
  document_graph_id: number
  document_type_code: string
  domain_document_id: string
  name: string
  content_type: string
  size: number
  version: number
  status: string
  uploaded_at: string | null
  uploaded_by: string
}

export type DocumentExpedientModule = {
  module_code: 'INGLES' | 'TITULACION' | 'PRACTICAS' | 'VINCULACION' | string
  module_name: string
  origin_id: string
  domain_expedient_id: number | null
  expedient_code: string
  status: string
  document_types: DocumentExpedientType[]
  documents: DocumentExpedientFile[]
  upload_enabled: boolean
  upload_message: string
}

export type DocumentExpedientContext = {
  student: DocumentExpedientStudent
  expedients: DocumentExpedientModule[]
  total_expedients: number
  total_documents: number
  max_file_bytes: number
}

export type DocumentExpedientUploadSessionResponse = {
  upload_id: string
  upload_url: string
  expires_at: string
  chunk_size: number
  max_file_bytes: number
}

export type DocumentExpedientFinalizeResponse = {
  ok: boolean
  document_graph_id: number
  domain_document_id: number
  version: number
  message: string
}

export type DocumentExpedientPrepareResponse = {
  ok: boolean
  expedient_graph_id: number
  folder_path: string
  folder_item_id: string
  web_url: string
  student_folder_reused: boolean
  message: string
}

export type PortalStudentSection = 'dashboard' | 'curricular' | 'academica' | 'notas'
export type MoodleSection =
  | 'alerts'
  | 'status'
  | 'users'
  | 'courses'
  | 'resources'
  | 'evaluation-dates'
  | 'grades'
export type PreinscriptionStage = 'registro' | 'inscritos' | 'becas' | 'gestion-becas' | 'becados' | 'contratos-becas' | 'seguimiento' | 'cabecera' | 'materias' | 'documentos'
export type MatriculaTipo = 'R' | 'H' | 'E'

export type TeacherEvaluationFlow = 'student' | 'auto_estudiante' | 'auto_docente' | 'par_docente' | 'academico_docente'

export type PracticasProcessCode = 'PPF' | 'VIN'

export type TituloRegistradoTipo = 'senescyt' | 'intec'

export type TituloRegistradoItem = {
  id: string
  tipo: TituloRegistradoTipo | string
  tipo_nombre: string
  modelo: string
  estudiante: string
  cedula: string
  carrera: string
  observacion: string
  filename: string
  content_type: string
  size: number
  url: string
  storage?: string
  titulacion_status?: string
  titulacion_expediente_id?: number | null
  titulacion_message?: string
  created_at: string
  created_by: string
}

export type TitulosRegistradosResponse = {
  items: TituloRegistradoItem[]
  totals: {
    total: number
    senescyt: number
    intec: number
  }
  modelos: Array<{ value: TituloRegistradoTipo | string; label: string }>
}

export type TituloRegistradoSaveResponse = {
  ok: boolean
  message: string
  item?: TituloRegistradoItem
  items?: TituloRegistradoItem[]
  affected_rows?: number
  batch_id?: string
  results?: Array<Record<string, unknown>>
}

export type SisAcademicoV1Module = {
  key: string
  title: string
  description: string
  source_paths: string[]
  tables: string[]
  modern_sections: string[]
  available_sections: string[]
  missing_sections: string[]
  modern_routes: string[]
  coverage: 'base' | 'partial' | 'pending' | 'excluded' | string
  notes: string
}

export type SisAcademicoV1Artifact = {
  path: string
  file_name: string
  extension: string
  size_bytes: number
  module_key: string
  module_title: string
  coverage: 'base' | 'partial' | 'pending' | 'excluded' | string
  artifact_type: string
}

export type SisAcademicoV1ModulesResponse = {
  project: string
  strategy: string
  database: string
  compat_schema: string
  totals: {
    modules: number
    base: number
    partial: number
    pending: number
    excluded?: number
  }
  modules: SisAcademicoV1Module[]
}

export type SisAcademicoV1ArtifactsResponse = {
  project: string
  root: string
  strategy: string
  totals: {
    artifacts: number
    by_extension: Record<string, number>
    by_coverage: Record<string, number>
    by_module: Record<string, number>
  }
  artifacts: SisAcademicoV1Artifact[]
}

export type TitulacionAcademicStatus = {
  found: boolean
  message?: string
  codigo_estud?: number | null
  numero_identificacion?: string
  apellidos_nombres?: string
  cod_anio_basica?: string
  nombre_carrera?: string
  codigo_periodo?: string
  nombre_periodo?: string
  titulo_bachiller?: string
  total_materias?: number
  materias_pensum?: number
  materias_cursadas?: number
  materias_aprobadas?: number
  materias_pendientes?: number
  promedio_asignaturas?: number | null
  porcentaje_malla?: number
  malla_finalizada?: boolean
}

export type TitulacionExpediente = {
  ExpedienteId: number
  CodigoEstud?: number | null
  NumeroIdentificacion: string
  ApellidosNombres?: string | null
  CarreraRefId?: number | null
  CodAnioBasica?: string | null
  NombreCarrera?: string | null
  CodigoPeriodo?: string | null
  TituloOtorgado?: string | null
  MecanismoCodigoRaw?: string | null
  MecanismoTitulacionId?: number | null
  MecanismoCodigo?: string | null
  MecanismoNombre?: string | null
  NumeroActaGrado?: string | null
  NumeroRefrendacion?: string | null
  FechaActaGrado?: string | null
  FechaRefrendacion?: string | null
  CedulaValidada?: boolean | number
  TituloBachillerCumple?: boolean | number
  InglesA2Cumple?: boolean | number
  MallaCurricularCumple?: boolean | number
  NoAdeudaFinanciero?: boolean | number
  AptoSustentacion?: boolean | number
  PracticasPreprofesionalesCumple?: boolean | number
  VinculacionCumple?: boolean | number
  RubricaTitulacionCumple?: boolean | number
  PromedioAsignaturas?: number | null
  NotaPromedioAsignaturas80?: number | null
  NotaProcesoTitulacion20?: number | null
  NotaFinalGrado?: number | null
  EstadoExpediente?: string | null
  TotalHorasPracticasPreprofesionales?: number | null
  TotalHorasVinculacion?: number | null
  CumplePracticasPreprofesionales?: boolean | number | null
  CumpleVinculacion?: boolean | number | null
  FechaSincronizacionPracticas?: string | null
}

export type TitulacionDocument = {
  DocumentoId: number
  ExpedienteId: number
  TipoDocumentoCodigo: string
  FormatoCargaCodigo?: string | null
  NombreArchivo?: string | null
  RutaNube?: string | null
  EsFirmadoElectronico?: boolean | number
  FechaDocumento?: string | null
  EstadoDocumento?: string | null
  VersionDocumento?: number | null
  UsuarioCarga?: string | null
  FechaCarga?: string | null
  Observacion?: string | null
  Activo?: boolean | number
}

export type TitulacionPrevalidation = Record<string, string | number | boolean | null | undefined>

export type TitulacionMecanismoCodigo = 'EXAMEN_COMPLEXIVO' | 'DEFENSA_GRADO'

export type TitulacionMechanism = {
  selected?: Record<string, string | number | boolean | null | undefined> | null
  prevalidation?: Record<string, string | number | boolean | null | undefined> | null
  programacion?: Record<string, string | number | boolean | null | undefined> | null
  examen?: Record<string, string | number | boolean | null | undefined> | null
  defensa?: Record<string, string | number | boolean | null | undefined> | null
  tribunal?: Array<Record<string, string | number | boolean | null | undefined>>
}

export type TitulacionGeneration = {
  acta?: Record<string, string | number | boolean | null | undefined> | null
  senescyt?: Record<string, string | number | boolean | null | undefined> | null
  intec?: Record<string, string | number | boolean | null | undefined> | null
}

export type TitulacionResponse = {
  ok?: boolean
  message?: string
  academic: TitulacionAcademicStatus
  expediente?: TitulacionExpediente | null
  documents: TitulacionDocument[]
  mechanism?: TitulacionMechanism | null
  generation?: TitulacionGeneration | null
  prevalidation?: TitulacionPrevalidation | null
}

export type TitulacionAptoItem = {
  ExpedienteId?: number | null
  CodigoEstud?: number | null
  NumeroIdentificacion: string
  ApellidosNombres?: string | null
  CodAnioBasica?: string | null
  NombreCarrera?: string | null
  CodigoPeriodo?: string | null
  EstadoExpediente?: string | null
  TotalMaterias?: number
  MateriasAprobadas?: number
  CumpleMalla24?: boolean
  CumpleInglesA2Avanzado?: boolean
  CumplePracticasPreprofesionales?: boolean
  CumpleVinculacion?: boolean
  AptoTitulacion?: boolean
  Pendientes?: string[]
  PromedioAsignaturas?: number | null
  TotalHorasPracticasPreprofesionales?: number | null
  TotalHorasVinculacion?: number | null
}

export type TitulacionAptosResponse = {
  items: TitulacionAptoItem[]
  total: number
  aptos: number
  pendientes: number
  criteria?: {
    materias_requeridas?: number
    ingles?: string
    practicas?: string
  }
}

export type TitulacionProgramacionItem = {
  ExpedienteId: number
  NumeroIdentificacion?: string | null
  ApellidosNombres?: string | null
  NombreCarrera?: string | null
  CodAnioBasica?: string | null
  CodigoPeriodo?: string | null
  EstadoExpediente?: string | null
  MecanismoCodigo?: TitulacionMecanismoCodigo | string | null
  MecanismoNombre?: string | null
  ProgramacionTitulacionId?: number | null
  FechaProgramada?: string | null
  HoraProgramada?: string | null
  Lugar?: string | null
  Modalidad?: string | null
  EnlaceVirtual?: string | null
  EstadoProgramacion?: string | null
  TemaTrabajo?: string | null
  LineaInvestigacion?: string | null
  Tutor?: string | null
  LectorOponente?: string | null
  CodigoExamen?: string | null
  TipoExamen?: string | null
  TotalMiembrosTribunal?: number | null
  Responsables?: string | null
}

export type TitulacionProgramacionResponse = {
  items: TitulacionProgramacionItem[]
  total: number
  complexivo: number
  defensa: number
}

export type TitulacionMallaCalificacion = {
  row_id?: number | null
  codigo_materia?: string | null
  nombre_materia?: string | null
  semestre?: number | null
  creditos?: number | null
  orden?: number | null
  codigo_periodo?: string | null
  nombre_periodo?: string | null
  num_matricula?: string | null
  paralelo?: string | null
  num_grupo?: number | null
  tipo_matricula?: string | null
  tipo_periodo?: string | null
  tipo_calculo?: 'R' | 'H' | string | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  prom_p1?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  prom_p2?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  prom_p3?: number | null
  teoria_homo?: number | null
  practica_homo?: number | null
  promedio?: number | null
  asistencia?: number | null
  recuperacion?: number | null
  promedio_final_registrado?: number | null
  promedio_aux?: number | null
  nota_final?: number | null
  formula_nota?: string | null
  nota_aprobar?: number | null
  aprobada?: boolean | number
  estado?: string | null
}

export type TitulacionMallaCalificacionesResponse = {
  found: boolean
  message?: string
  academic?: TitulacionAcademicStatus
  items: TitulacionMallaCalificacion[]
  summary?: {
    materias_requeridas?: number
    materias_pensum?: number
    total_materias?: number
    materias_aprobadas?: number
    materias_pendientes?: number
    porcentaje_malla?: number
  }
}

export type TitulacionExpedientePayload = {
  numero_identificacion: string
  cod_anio_basica?: string | null
  codigo_periodo?: string | null
  titulo_otorgado?: string | null
}

export type TitulacionNotasPayload = {
  expediente_id: number
  promedio_asignaturas?: number | null
  nota_proceso_titulacion?: number | null
  cedula_validada: boolean
  titulo_bachiller_cumple: boolean
  ingles_a2_cumple: boolean
  no_adeuda_financiero: boolean
  apto_sustentacion: boolean
  rubrica_titulacion_cumple: boolean
}

export type TitulacionMecanismoPayload = {
  expediente_id: number
  mecanismo_codigo: TitulacionMecanismoCodigo
}

export type TitulacionProgramacionPayload = {
  expediente_id: number
  fecha_programada: string
  hora_programada?: string | null
  lugar?: string | null
  modalidad?: string | null
  enlace_virtual?: string | null
}

export type TitulacionTribunalPayload = {
  expediente_id: number
  mecanismo_codigo: TitulacionMecanismoCodigo
  rol_tribunal: string
  nombre_miembro: string
  cedula_miembro?: string | null
  correo_miembro?: string | null
  orden_firma?: number | null
}

export type ExamenComplexivoCalificacionPayload = {
  expediente_id: number
  nota_examen: number
  codigo_examen?: string | null
  tipo_examen?: string | null
  observacion?: string | null
}

export type DefensaTemaPayload = {
  expediente_id: number
  tema_trabajo: string
  linea_investigacion?: string | null
  tutor?: string | null
  lector_oponente?: string | null
}

export type DefensaCalificacionPayload = {
  expediente_id: number
  nota_trabajo_escrito: number
  nota_defensa_oral: number
  observacion?: string | null
}

export type ActaGradoPayload = {
  expediente_id: number
  fecha_acta: string
  hora_acta?: string | null
  numero_acta_grado?: string | null
  ciudad?: string | null
  escuela?: string | null
  autoridad_academica?: string | null
  docente_evaluador?: string | null
  coordinador_academico?: string | null
  ruta_acta_pdf?: string | null
}

export type TituloSenescytPayload = {
  numero_acta_grado: string
  codigo_registro_senescyt: string
  fecha_registro: string
  ruta_documento_nube?: string | null
}

export type TituloIntecPayload = {
  numero_acta_grado: string
  numero_titulo: string
  fecha_emision: string
  codigo_verificacion?: string | null
  ruta_documento_nube?: string | null
}

export type PracticasCatalogItem = {
  TipoProcesoId?: number
  Codigo: PracticasProcessCode | string
  Nombre: string
  Descripcion?: string | null
  Activo?: boolean
}

export type PracticasDocumentItem = {
  TipoDocumentoId: number
  TipoProcesoCodigo: PracticasProcessCode | string
  Codigo: string
  Nombre: string
  EsObligatorio: boolean
  Orden: number
}

export type PracticasResponsableItem = {
  ResponsableProcesoId: number
  TipoProcesoCodigo: PracticasProcessCode | string
  NombreResponsable: string
  CedulaResponsable?: string | null
  CorreoResponsable?: string | null
  RolResponsable?: string | null
  CodigoDocente?: string | null
  FechaInicio?: string | null
  FechaFin?: string | null
  Activo?: boolean
}

export type PracticasExpedienteItem = {
  ExpedienteId: number
  CodigoExpediente?: string | null
  TipoProcesoCodigo: PracticasProcessCode | string
  TipoProceso?: string | null
  CodigoEstud: number
  Cedula_Est?: string | null
  Apellidos_nombre?: string | null
  CodigoCarrera?: string | null
  Carrera?: string | null
  CodigoPeriodo?: string | null
  FechaInicioCarga?: string | null
  FechaFinCarga?: string | null
  CodigoDocenteTutor?: string | null
  DocenteTutor?: string | null
  SemestreDetectado?: number | null
  EstadoCodigo?: string | null
  EstadoExpediente?: string | null
  ResponsableProcesoId?: number | null
  NombreResponsable?: string | null
  CorreoResponsable?: string | null
  CartaCompromisoDocumentoId?: number | null
  CartaCompromisoEstadoCodigo?: string | null
  CartaCompromisoEstado?: string | null
  CartaCompromisoArchivo?: string | null
  CartaCompromisoUrl?: string | null
  CartaCompromisoFecha?: string | null
  CartaCompromisoFirmado?: boolean | null
  CartaCompromisoValidado?: boolean | null
  CertificadoDocumentoId?: number | null
  CertificadoEstadoCodigo?: string | null
  CertificadoEstado?: string | null
  CertificadoArchivo?: string | null
  CertificadoUrl?: string | null
  CertificadoFecha?: string | null
  CertificadoFirmado?: boolean | null
  CertificadoValidado?: boolean | null
  DocumentosRequeridos?: number
  DocumentosCargados?: number
  DocumentosValidados?: number
  DocumentosPendientes?: number
  DocumentosDetalle?: PracticasReviewDocumentItem[]
  AvanceDocumental?: number
  AvanceValidacionDocumental?: number
  Finalizado?: boolean
  Activo?: boolean
  FechaCreacion?: string | null
}

export type PracticasEligibilityItem = {
  codigo_estud: number
  Cedula_Est?: string | null
  Apellidos_nombre?: string | null
  CodigoCarrera?: string | null
  Carrera?: string | null
  CodigoPeriodo?: string | null
  NombrePeriodo?: string | null
  TipoProcesoCodigo?: PracticasProcessCode | string
  TipoProceso?: string | null
  SemestreMaximo?: number | null
  EsElegible?: boolean
  MotivoElegibilidad?: string | null
  TieneAutorizacion?: boolean | number | null
  AutorizacionId?: number | null
  AutorizacionArchivo?: string | null
  AutorizacionUrl?: string | null
  AutorizacionFecha?: string | null
  PuedeInscribirse?: boolean | number | null
  /** @deprecated Compatibilidad con respuestas anteriores. */
  PuedeMatricular?: boolean | number | null
}

export type PracticasCatalogResponse = {
  processes: PracticasCatalogItem[]
  documents: PracticasDocumentItem[]
  responsibles: PracticasResponsableItem[]
  defaults: Array<{ codigo: PracticasProcessCode; nombre: string }>
}

export type PracticasStudentResponse = {
  codigo_estud: number
  eligibility: PracticasEligibilityItem[]
  expedientes: PracticasExpedienteItem[]
}

export type PracticasElegiblesResponse = {
  items: PracticasEligibilityItem[]
  total: number
}

export type PracticasPeriodoItem = {
  CodigoPeriodo: string
  NombrePeriodo?: string | null
  DetalleRegistro?: string | null
  PeriodoCorto?: string | null
  TotalEstudiantes?: number
  EstadoPeriodo?: string | null
  OrdenPeriodo?: number | string | null
  NotaAprobar?: number | string | null
  TipoMatricula?: string | null
  FechaInicio?: string | null
  FechaFin?: string | null
  Anio?: number | string | null
  EstadoEducativo?: string | null
}

export type PracticasPeriodosResponse = {
  items: PracticasPeriodoItem[]
  total: number
}

export type PracticasPeriodoDesignacionItem = {
  DesignacionId: number
  TipoProcesoCodigo: PracticasProcessCode | string
  CodigoPeriodo: string
  CodigoPeriodoOrigen?: string | null
  CodigoDocente: string
  CedulaResponsable?: string | null
  NombreResponsable: string
  CorreoResponsable?: string | null
  RolResponsable?: string | null
  CumpleRequisitos?: boolean
  Activo?: boolean
  Observacion?: string | null
  PeriodoOrigen?: string | null
  FechaRegistro?: string | null
}

export type PracticasPeriodoDesignacionesResponse = {
  items: PracticasPeriodoDesignacionItem[]
  total: number
}

export type PracticasExpedientesResponse = {
  items: PracticasExpedienteItem[]
  total: number
}

export type PracticasResponsableProgressItem = PracticasExpedienteItem & {
  TotalDocumentos?: number
  DocumentosFirmados?: number
  DocumentosValidados?: number
  DocumentosPendientes?: number
  DocumentosRequeridos?: number
  DocumentosDetalle?: PracticasReviewDocumentItem[]
  EstadoCodigo?: string | null
  HorasRequeridas?: number | null
  HorasReconocidas?: number | null
  HorasAsistenciaValidadas?: number | null
  PuedeValidarDocumentos?: boolean | number | null
  PuedeAprobar?: boolean | number | null
  ListoParaAprobar?: boolean
  Avance?: number
}

export type PracticasResponsableProgressResponse = {
  summary: {
    tipo_proceso?: string
    expedientes?: number
    avance?: number
    avance_documental?: number
    documentos_requeridos?: number
    documentos_cargados?: number
    documentos_validados?: number
    documentos_pendientes?: number
  }
  items: PracticasResponsableProgressItem[]
}

export type PracticasReviewDocumentItem = {
  TipoDocumentoId?: number | null
  Codigo: string
  Nombre?: string | null
  DocumentoId?: number | null
  NombreArchivo?: string | null
  RutaArchivo?: string | null
  UrlArchivo?: string | null
  EstadoCodigo?: string | null
  EstadoNombre?: string | null
  Cargado?: boolean
  Validado?: boolean
  FechaValidacion?: string | null
}

export type PracticasReviewDetailResponse = {
  ExpedienteId: number
  CodigoExpediente?: string | null
  CodigoEstud?: number | null
  Cedula_Est?: string | null
  Apellidos_nombre?: string | null
  CodigoCarrera?: string | null
  Carrera?: string | null
  CodigoPeriodo?: string | null
  Periodo?: string | null
  FechaInicioCarga?: string | null
  FechaFinCarga?: string | null
  TipoProcesoCodigo: PracticasProcessCode
  TipoProceso?: string | null
  EstadoCodigo?: string | null
  EstadoExpediente?: string | null
  HorasRequeridas: number
  HorasReconocidas: number
  HorasAsistenciaValidadas?: number
  DocumentosDetalle: PracticasReviewDocumentItem[]
  DocumentosFaltantes: string[]
  DocumentosCompletos: boolean
  ListoParaAprobar: boolean
  PuedeAprobar: boolean
  Responsable?: Record<string, unknown> | null
  UltimaRevision?: Record<string, unknown> | null
}

export type PracticasReviewDecision = 'APROBAR' | 'OBSERVAR' | 'RECHAZAR'

export type PracticasReviewResponse = {
  ok: boolean
  message: string
  decision: PracticasReviewDecision
  estado: string
  responsable?: Record<string, unknown> | null
  titulacion?: {
    sincronizado?: boolean
    pendiente?: boolean
    motivo?: string
    expedientes_titulacion?: number
  }
}

export type PracticasOperationsEntity = {
  entidad_id: number
  nombre: string
  ruc?: string | null
  tipo_entidad?: string | null
  sector_economico?: string | null
  direccion?: string | null
  contacto_nombre?: string | null
  contacto_correo?: string | null
  contacto_telefono?: string | null
  activo?: boolean
}

export type PracticasOperationsAgreement = {
  convenio_id: number
  entidad_id: number
  tipo_proceso_codigo: PracticasProcessCode
  codigo_convenio: string
  objeto?: string | null
  fecha_inicio: string
  fecha_fin: string
  estado: string
  archivo_url?: string | null
  activo?: boolean
  entidad_nombre?: string | null
}

export type PracticasOperationsProject = {
  proyecto_id: number
  entidad_id?: number | null
  convenio_id?: number | null
  codigo_proyecto: string
  nombre: string
  linea_intervencion: string
  poblacion_objetivo?: string | null
  beneficiarios_previstos?: number | null
  objetivo_general?: string | null
  fecha_inicio: string
  fecha_fin: string
  estado: string
  activo?: boolean
  entidad_nombre?: string | null
  codigo_convenio?: string | null
}

export type PracticasOperationsConfiguration = {
  configuracion_id?: number | null
  tipo_proceso_codigo: PracticasProcessCode
  codigo_carrera?: string | null
  nivel?: string | null
  codigo_periodo?: string | null
  horas_requeridas: number
  documentos_requeridos: number
  nota_minima_aprobacion: number
  requiere_evaluacion_docente: boolean
  requiere_evaluacion_tutor: boolean
  requiere_autoevaluacion: boolean
  requiere_resultado_vinculacion: boolean
  peso_docente: number
  peso_tutor: number
  peso_autoevaluacion: number
  activo?: boolean
}

export type PracticasOperationsCatalogResponse = {
  entidades: PracticasOperationsEntity[]
  convenios: PracticasOperationsAgreement[]
  proyectos: PracticasOperationsProject[]
  configuraciones: PracticasOperationsConfiguration[]
  almacenamiento: {
    base_datos: string
    esquema_operativo: string
    tabla_calificacion: string
    fuente_academica: string
  }
}

export type PracticasOperationsDashboardItem = {
  ExpedienteId: number
  CodigoExpediente?: string | null
  CodigoEstud?: number | null
  Cedula?: string | null
  Estudiante?: string | null
  CodigoCarrera?: string | null
  Carrera?: string | null
  CodigoPeriodo?: string | null
  Periodo?: string | null
  FechaInicio?: string | null
  FechaFin?: string | null
  HorasRequeridas?: number
  HorasReconocidas?: number
  EstadoCodigo?: string | null
  Estado?: string | null
  InscripcionId?: number | null
  EstadoInscripcion?: 'INSCRITO' | 'EN_PROCESO' | 'EN_REVISION' | 'CUMPLIDO' | 'NO_CUMPLIDO' | 'ANULADO'
  CodigoPeriodoAcademicoOrigen?: string | null
  CodigoPeriodoInstitucional?: string | null
  EsMatriculaAcademica?: boolean
  EvaluacionId?: number | null
  EstadoEvaluacion?: 'PENDIENTE_REVISION' | 'EN_REVISION' | 'PENDIENTE_CALIFICACION' | 'CALIFICADA'
  CalificacionFinal?: number | null
  NotaMinimaAprobacion?: number
  ResultadoEvaluacion?: 'PENDIENTE' | 'APROBADO' | 'REPROBADO'
  FechaEnvioRevision?: string | null
  FechaRevisionEvaluacion?: string | null
  FechaCalificacion?: string | null
  PlanId?: number | null
  EstadoPlan?: string | null
  EntidadId?: number | null
  ConvenioId?: number | null
  ProyectoId?: number | null
  HorasRegistradas?: number
  HorasValidadas?: number
  Actividades?: number
  DocumentosCargados?: number
  DocumentosValidados?: number
  DocumentosRequeridos?: number
  AvanceDocumental?: number
  AvanceValidacionDocumental?: number
  NombreResponsable?: string | null
  CierreId?: number | null
  FechaCierre?: string | null
  TipoProcesoCodigo?: PracticasProcessCode
  Semaforo?: 'VERDE' | 'AMARILLO' | 'ROJO'
  DiasRestantes?: number | null
}

export type PracticasOperationsDashboardResponse = {
  tipo_proceso: PracticasProcessCode
  summary: {
    total: number
    verdes: number
    amarillos: number
    rojos: number
    con_plan: number
    cerrados: number
    en_revision: number
    pendientes_calificacion: number
    aprobados: number
    reprobados: number
    horas_registradas: number
    horas_validadas: number
  }
  items: PracticasOperationsDashboardItem[]
}

export type PracticasOperationsPlan = {
  plan_id: number
  expediente_id: number
  tipo_proceso_codigo: PracticasProcessCode
  entidad_id?: number | null
  convenio_id?: number | null
  proyecto_id?: number | null
  tutor_externo_nombre?: string | null
  tutor_externo_correo?: string | null
  tutor_externo_telefono?: string | null
  objetivo_general?: string | null
  resultados_aprendizaje?: string | null
  actividades_planificadas?: string | null
  fecha_inicio?: string | null
  fecha_fin?: string | null
  horas_planificadas?: number
  estado?: 'BORRADOR' | 'APROBADO' | 'EN_EJECUCION' | 'FINALIZADO'
}

export type PracticasOperationsActivity = {
  actividad_id: number
  expediente_id: number
  fecha_actividad: string
  descripcion: string
  horas: number
  hora_inicio?: string | null
  hora_fin?: string | null
  descanso_minutos?: number
  modalidad?: 'PRESENCIAL' | 'VIRTUAL' | 'HIBRIDA' | null
  lugar?: string | null
  origen_horas?: 'MANUAL' | 'JORNADA_CALCULADA'
  evidencia_url?: string | null
  evidencia_nombre?: string | null
  estado_revision: 'PENDIENTE' | 'VALIDADO' | 'OBSERVADO' | 'RECHAZADO'
  observacion_revision?: string | null
  revisado_por?: string | null
  fecha_revision?: string | null
}

export type PracticasOperationsIndicator = {
  indicador_id: number
  expediente_id: number
  nombre: string
  unidad_medida: string
  meta: number
  resultado?: number | null
  evidencia_url?: string | null
  observacion?: string | null
  usuario_registro?: string | null
  fecha_registro?: string | null
}

export type PracticasOperationsClosure = {
  cierre_id: number
  expediente_id: number
  supervision_realizada?: boolean
  evaluacion_entidad?: number | null
  informe_final_validado?: boolean
  acta_aceptacion_validada?: boolean
  certificado_emitido?: boolean
  observacion?: string | null
  fecha_cierre?: string | null
  cerrado_por?: string | null
}

export type PracticasOperationsEvaluation = {
  evaluacion_id: number
  expediente_id: number
  estado: 'PENDIENTE_REVISION' | 'EN_REVISION' | 'PENDIENTE_CALIFICACION' | 'CALIFICADA'
  calificacion?: number | null
  nota_minima_aprobacion: number
  resultado: 'PENDIENTE' | 'APROBADO' | 'REPROBADO'
  origen_calificacion?: 'MANUAL_RESPONSABLE' | 'PROMEDIO_PONDERADO_ACTORES' | 'MIGRACION_LEGACY' | null
  detalle_calculo?: string | null
  observacion_revision?: string | null
  observacion_calificacion?: string | null
  enviado_por?: string | null
  fecha_envio_revision?: string | null
  revisado_por?: string | null
  fecha_revision?: string | null
  calificado_por?: string | null
  fecha_calificacion?: string | null
}

export type PracticasOperationsActorEvaluation = {
  evaluacion_actor_id: number
  expediente_id: number
  rol_evaluador: 'DOCENTE_ACADEMICO' | 'TUTOR_EMPRESARIAL' | 'AUTOEVALUACION'
  calificacion: number
  peso: number
  evaluador_nombre?: string | null
  evaluador_correo?: string | null
  observacion?: string | null
  evidencia_url?: string | null
  estado: 'REGISTRADA' | 'VALIDADA' | 'OBSERVADA'
  fecha_validacion?: string | null
}

export type PracticasOperationsGradeCalculation = {
  calificacion_calculada?: number | null
  roles_faltantes: Array<'DOCENTE_ACADEMICO' | 'TUTOR_EMPRESARIAL' | 'AUTOEVALUACION'>
  componentes: Array<{
    rol_evaluador: 'DOCENTE_ACADEMICO' | 'TUTOR_EMPRESARIAL' | 'AUTOEVALUACION'
    calificacion: number
    peso: number
  }>
  usa_evaluaciones_actores: boolean
}

export type PracticasOperationsVinculationResult = {
  resultado_vinculacion_id: number
  expediente_id: number
  beneficiarios_reales: number
  resumen_impacto: string
  observacion?: string | null
  evidencia_url?: string | null
  estado: 'REGISTRADO' | 'VALIDADO' | 'OBSERVADO'
  validado_por?: string | null
  fecha_validacion?: string | null
}

export type PracticasOperationsVinculationProduct = {
  producto_id: number
  expediente_id: number
  nombre: string
  descripcion?: string | null
  cantidad: number
  unidad_medida: string
  evidencia_url?: string | null
  estado_revision: 'PENDIENTE' | 'VALIDADO' | 'OBSERVADO' | 'RECHAZADO'
  observacion_revision?: string | null
}

export type PracticasOperationsGradeHistory = {
  historial_id: number
  evaluacion_id: number
  expediente_id: number
  accion: string
  estado: string
  calificacion?: number | null
  nota_minima_aprobacion: number
  resultado: string
  origen_calificacion?: string | null
  detalle_calculo?: string | null
  observacion?: string | null
  usuario: string
  fecha: string
}

export type PracticasOperationsReopening = {
  reapertura_id: number
  expediente_id: number
  evaluacion_id?: number | null
  estado_anterior?: string | null
  resultado_anterior?: string | null
  calificacion_anterior?: number | null
  motivo: string
  requiere_reversion_titulacion: boolean
  usuario: string
  fecha: string
}

export type PracticasOperationsRequirement = {
  codigo: string
  titulo: string
  detalle: string
  estado: 'COMPLETO' | 'EN_REVISION' | 'PENDIENTE'
  completo: boolean
}

export type PracticasOperationsDetailResponse = {
  expediente: Record<string, unknown>
  tipo_proceso_codigo: PracticasProcessCode
  responsable?: Record<string, unknown> | null
  plan?: PracticasOperationsPlan | null
  actividades: PracticasOperationsActivity[]
  indicadores: PracticasOperationsIndicator[]
  resultado_vinculacion?: PracticasOperationsVinculationResult | null
  productos_vinculacion: PracticasOperationsVinculationProduct[]
  evaluaciones_actores: PracticasOperationsActorEvaluation[]
  calculo_calificacion: PracticasOperationsGradeCalculation
  evaluacion?: PracticasOperationsEvaluation | null
  historial_calificacion: PracticasOperationsGradeHistory[]
  reaperturas: PracticasOperationsReopening[]
  cierre?: PracticasOperationsClosure | null
  documentos: PracticasReviewDocumentItem[]
  conciliacion_titulacion?: Record<string, unknown> | null
  requisitos: PracticasOperationsRequirement[]
  configuracion: PracticasOperationsConfiguration
  almacenamiento: {
    base_datos: string
    tabla_calificacion: string
    tabla_historial: string
  }
  resumen: {
    horas_registradas: number
    horas_validadas: number
    actividades: number
    pendientes: number
    horas_requeridas: number
    documentos_requeridos: number
    documentos_cargados: number
    documentos_validados: number
    documentos_pendientes: number
    avance_documental_porcentaje: number
    avance_validacion_documental_porcentaje: number
    avance_porcentaje: number
    requisitos_completos: number
    requisitos_totales: number
  }
  permisos: {
    puede_editar_plan: boolean
    puede_registrar_actividad: boolean
    puede_revisar_actividad: boolean
    puede_enviar_revision: boolean
    puede_calificar: boolean
    puede_cerrar: boolean
    puede_registrar_evaluacion_actor: boolean
    puede_registrar_resultado: boolean
    puede_reabrir: boolean
  }
}

export type PracticasOperationsNotification = {
  notificacion_id: number
  expediente_id?: number | null
  tipo_proceso_codigo?: PracticasProcessCode | null
  destinatario_login?: string | null
  destinatario_rol: string
  nivel: 'INFORMATIVA' | 'ADVERTENCIA' | 'CRITICA'
  titulo: string
  mensaje: string
  leida: boolean
  fecha_registro?: string | null
}

export type PracticasOperationsNotificationsResponse = {
  generated: number
  unread: number
  items: PracticasOperationsNotification[]
}

export type PracticasOperationsReconciliation = {
  conciliacion_id: number
  expediente_id: number
  tipo_proceso_codigo: PracticasProcessCode
  estado: 'PENDIENTE' | 'PROCESANDO' | 'COMPLETADO' | 'ERROR'
  intentos: number
  proximo_intento?: string | null
  ultimo_error?: string | null
  fecha_solicitud?: string | null
  fecha_ultimo_intento?: string | null
  fecha_completado?: string | null
}

export type PracticasOperationsReconciliationsResponse = {
  total: number
  items: PracticasOperationsReconciliation[]
}

export type PracticasOperationsAuditItem = {
  auditoria_id: number
  modulo: string
  entidad: string
  entidad_id?: string | null
  accion: string
  detalle?: string | null
  usuario: string
  fecha: string
}

export type PracticasOperationsAuditResponse = {
  total: number
  items: PracticasOperationsAuditItem[]
}

export type TeacherEvaluationQuestion = {
  id_pregunta: number
  id_dimension?: number | null
  no_pregunta: number
  tipo_preg: number
  tipo_preg_codigo?: string | null
  tipo_label?: string | null
  categoria?: string | null
  categoria_pregunta?: string | null
  categoria_codigo?: string | null
  dimension_codigo?: string | null
  dimension_global_nombre?: string | null
  dimension_nombre?: string | null
  nombre_dimension?: string | null
  instrumento_codigo?: string | null
  instrumento_nombre?: string | null
  tipo_evaluacion_codigo?: string | null
  tipo_evaluacion_nombre?: string | null
  detalle_preg: string
  peso_pregunta?: number | null
  puntaje_min?: number | null
  puntaje_max?: number | null
  escala_likert?: Array<{
    valor: number
    etiqueta: string
    texto?: string
  }>
  orden?: number | null
  control?: string | number | null
  comentario_coord?: string | null
}

export type TeacherEvaluationCourse = {
  key: string
  codigo_periodo: number
  detalle_periodo?: string | null
  orden_periodo?: number | null
  cod_anio_basica?: number | string | null
  carrera?: string | null
  codigo_materia: number
  codigo_materia_interno?: string | null
  materia?: string | null
  nivel?: number | string | null
  paralelo?: string | null
  tipo_matricula?: string | null
  codigo_docente_eval: number
  docente?: string | null
  cedula_docente?: string | null
  cod_jornada?: string | number | null
  jornada?: string | null
  respuestas_registradas?: number
  evaluado?: boolean
  carreras_relacionadas?: string[]
  paralelos_relacionados?: string[]
  docentes_relacionados?: string[]
  codigos_materia_relacionados?: number[]
  componentes_relacionados?: Array<{
    periodo?: string | number | null
    codigo_periodo?: number | string | null
    codigo_materia?: number | string | null
    codigo_materia_interno?: string | null
    materia?: string | null
    carrera?: string | null
    cod_anio_basica?: number | string | null
    paralelo?: string | null
    docente?: string | null
    cedula_docente?: string | null
    jornada?: string | null
  }>
}

export type TeacherEvaluationStudent = {
  codigo_estud: number
  cedula: string
  estudiante: string
  correo_personal?: string | null
  correo_intec?: string | null
}

export type TeacherEvaluationStudentResponse = {
  student: TeacherEvaluationStudent
  courses: TeacherEvaluationCourse[]
  total: number
}

export type TeacherEvaluationTeacher = {
  codigo_doc: number
  cedula: string
  docente: string
  correo_personal?: string | null
  correo_intec?: string | null
  usuario?: string | null
}

export type TeacherEvaluationAuthority = {
  codigo_autoridad: number
  id_autoridad_eval360?: number | null
  id_usuarios?: number | string | null
  cedula: string
  login?: string | null
  nombres: string
  autoridad?: string | null
  email?: string | null
  coordcarrera?: string | number | null
  cod_carrera_autoridad?: string | number | null
  cargo?: string | null
  tipousuario?: string | null
  tp_us?: string | null
  estado?: string | null
}

export type TeacherEvaluationTeacherResponse = {
  teacher: TeacherEvaluationTeacher
  auto_courses: TeacherEvaluationCourse[]
  peer_courses: TeacherEvaluationCourse[]
  total_auto: number
  total_peer: number
}


export type TeacherEvaluationIdentityResponse = {
  cedula: string
  roles: Array<'student' | 'teacher' | 'authority'>
  access_token: string
  access_token_expires_minutes: number
  student: TeacherEvaluationStudentResponse['student'] | null
  teacher: TeacherEvaluationTeacherResponse['teacher'] | null
  authority?: TeacherEvaluationAuthority | null
  student_courses: TeacherEvaluationCourse[]
  auto_student_courses?: TeacherEvaluationCourse[]
  auto_courses: TeacherEvaluationCourse[]
  peer_courses: TeacherEvaluationCourse[]
  authority_courses?: TeacherEvaluationCourse[]
  advertencias?: string[]
}

export type TeacherEvaluationQuestionsResponse = {
  flow?: TeacherEvaluationFlow
  instrument?: Record<string, unknown>
  items: TeacherEvaluationQuestion[]
  total: number
}

export type TeacherEvaluationSubmitPayload = {
  flow?: Extract<TeacherEvaluationFlow, 'student' | 'auto_estudiante'>
  cedula: string
  codigo_periodo: number
  codigo_materia: number
  codigo_docente_eval: number
  paralelo: string
  jornada?: string | null
  answers: Array<{
    id_pregunta: number
    no_pregunta: number
    tipo_preg: number
    detalle_preg?: string | null
    puntaje: number
  }>
}

export type TeacherEvaluationSubmitResponse = {
  saved: number
  average: number
  message: string
  student?: TeacherEvaluationStudent
  teacher?: TeacherEvaluationTeacher
  authority?: TeacherEvaluationAuthority
  course: TeacherEvaluationCourse
}

export type TeacherRoleEvaluationSubmitPayload = Omit<TeacherEvaluationSubmitPayload, 'flow'> & {
  flow: Exclude<TeacherEvaluationFlow, 'student' | 'auto_estudiante'>
}

export type TeacherEvaluationAdminPeriod = {
  codigo_periodo: string
  detalle_periodo: string
}

export type TeacherEvaluationAdminPeriodsResponse = {
  items: TeacherEvaluationAdminPeriod[]
  total: number
}

export type TeacherEvaluationAdminSummaryItem = {
  flow: TeacherEvaluationFlow
  flow_label: string
  expected: number
  completed: number
  pending: number
  progress_percent?: number
  ponderacion?: number
}

export type TeacherEvaluationAdminPendingItem = {
  flow: TeacherEvaluationFlow
  flow_label: string
  evaluator_code?: number | null
  evaluator_name?: string | null
  evaluator_cedula?: string | null
  periodo: string
  periodo_detalle: string
  estado: 'PENDIENTE' | string
  course: TeacherEvaluationCourse
}

export type TeacherEvaluationTeacherProgressItem = {
  flow: TeacherEvaluationFlow | 'all'
  flow_label: string
  codigo_doc: string
  docente: string
  cedula_doc?: string | null
  codigo_periodo: string
  periodo_detalle?: string | null
  codigo_materia: string
  codigo_materia_interno?: string | null
  materia: string
  carrera?: string | null
  paralelo?: string | null
  expected: number
  completed: number
  pending: number
  progress_percent: number
  ponderacion?: number
  ponderacion_aplicada?: number
  completed_evaluators?: Array<{
    codigo?: string
    nombre?: string
    cedula?: string
  }>
  pending_evaluators?: Array<{
    codigo?: string
    nombre?: string
    cedula?: string
  }>
}

export type TeacherEvaluationProgressDetailItem = {
  flow: TeacherEvaluationFlow | 'all'
  flow_label: string
  categoria: string
  promedio: number
  promedio_ajustado?: number
  ponderacion: number
  ponderacion_tipo?: number
  aporte: number
  cobertura?: number
  esperadas?: number
  evaluaciones: number
  respuestas: number
}

export type TeacherEvaluationProgressDetailResponse = {
  periodo: string
  periodo_detalle: string
  flow: TeacherEvaluationFlow | 'all'
  codigo_docente: string
  codigo_materia: string
  paralelo?: string | null
  docente: string
  cedula_doc?: string | null
  materia: string
  carrera?: string | null
  items: TeacherEvaluationProgressDetailItem[]
  total: number
}

export type TeacherEvaluationProgressParticipantItem = {
  flow: TeacherEvaluationFlow
  flow_label: string
  estado: string
  evaluator_code: number
  evaluator_name: string
  evaluator_cedula?: string | null
  can_view_grades: boolean
  completed_count: number
}

export type TeacherEvaluationProgressParticipantsResponse = {
  periodo: string
  periodo_detalle: string
  codigo_docente: string
  codigo_materia: string
  docente: string
  materia: string
  flow: TeacherEvaluationFlow | 'all'
  estado: 'completadas' | 'pendientes'
  items: TeacherEvaluationProgressParticipantItem[]
  total: number
}

export type TeacherEvaluationAdminPendingResponse = {
  periodo: string
  periodo_detalle: string
  flow: TeacherEvaluationFlow | 'all'
  summary: TeacherEvaluationAdminSummaryItem[]
  teacher_progress?: TeacherEvaluationTeacherProgressItem[]
  items: TeacherEvaluationAdminPendingItem[]
  total: number
}

export type TeacherEvaluationGradedTeacher = {
  codigo_doc: string
  docente: string
  cedula_doc?: string | null
  total_registros: number
  total_evaluaciones?: number
  total_respuestas?: number
  promedio_final: number
  flow?: TeacherEvaluationFlow | 'all'
  flow_label?: string | null
}

export type TeacherEvaluationGradedTeachersResponse = {
  periodo: string
  periodo_detalle: string
  flow?: TeacherEvaluationFlow | 'all'
  flow_label?: string
  items: TeacherEvaluationGradedTeacher[]
  total: number
}

export type TeacherEvaluationGradedSubject = {
  codigo_docente: string
  docente: string
  codigo_materia: string
  materia: string
  carrera: string
  paralelo?: string | null
  jornada?: string | null
  estudiantes_esperados: number
  estudiantes_completaron: number
  cobertura_estudiantes: number
  promedio_estudiantes?: number
  promedio_par_docente?: number
  promedio_autoridad?: number
  promedio_autoevaluacion?: number
  puntaje_final: number
}

export type TeacherEvaluationGradedSubjectsResponse = {
  periodo: string
  periodo_detalle: string
  codigo_docente: string
  flow?: TeacherEvaluationFlow | 'all'
  items: TeacherEvaluationGradedSubject[]
  total: number
}

export type TeacherEvaluationStudentProgressMetric = {
  ponderacion: number
  esperadas?: number
  completadas: number
  pendientes: number
  avance_percent: number
}

export type TeacherEvaluationStudentProgressItem = {
  codigo_estud: number
  cedula: string
  estudiante: string
  carreras?: string | null
  materias_evaluables: number
  materias_autoevaluables?: number
  evaluacion_docente: TeacherEvaluationStudentProgressMetric
  autoevaluacion_estudiante: TeacherEvaluationStudentProgressMetric
  avance_total_percent: number
}

export type TeacherEvaluationAutoStudentListItem = {
  codigo_estud: number
  cedula: string
  estudiante: string
  carreras?: string | null
  materias_evaluables: number
  esperadas: number
  completadas: number
  pendientes: number
  avance_percent: number
  estado: string
  materias?: Array<{
    codigo_materia: string | number
    codigo_materia_interno?: string | null
    materia: string
    carrera?: string | null
    paralelo?: string | null
    estado: string
    respuestas?: number
    promedio?: number | null
    nota_100?: number | null
    fecha_envio?: string | null
  }>
}

export type TeacherEvaluationAutoStudentListResponse = {
  periodo: string
  estado: string
  items: TeacherEvaluationAutoStudentListItem[]
  total: number
}

export type TeacherEvaluationStudentGradeItem = {
  codigo_materia: string | number
  materia: string
  carrera: string
  paralelo?: string | null
  promedio_final: number
}

export type TeacherEvaluationStudentGradesResponse = {
  periodo: string
  codigo_estud: number
  cedula: string
  estudiante: string
  items: TeacherEvaluationStudentGradeItem[]
  total: number
}

export type TeacherEvaluationStudentProgressResponse = {
  periodo: string
  periodo_detalle: string
  summary: {
    estudiantes: number
    materias_evaluables: number
    evaluacion_docente: TeacherEvaluationStudentProgressMetric
    autoevaluacion_estudiante: TeacherEvaluationStudentProgressMetric
  }
  items: TeacherEvaluationStudentProgressItem[]
  total: number
}

export type GraphTeam = {
  id?: string
  displayName?: string
  description?: string
  mail?: string
  visibility?: string
  webUrl?: string
  [key: string]: unknown
}

export type MatriculaSummaryItem = {
  tipo_matricula: MatriculaTipo
  estado_codigo: string
  estado_nombre: string
  total_estudiantes: number
}

export type MatriculaStudentItem = {
  punto_matricula?: string
  tipo_matricula: string
  estado_codigo: string
  estado_nombre: string
  codigo_estud: string
  cedula?: string
  nombre_estudiante: string
  nombre_carrera?: string
  correo_intec?: string
  correo_personal?: string
  periodo?: string
  detalle_periodo?: string
  anio_periodo?: number | null
  fecha_inicio_periodo?: string | null
}

export type DashboardMatriculaTrendItem = {
  anio: number
  mes: number
  fecha_inicio: string
  periodo_mes: string
  mes_nombre: string
  total_estudiantes: number
}

export type DashboardMatriculaStateItem = {
  estado_codigo: string
  estado_nombre: string
  total_estudiantes: number
}

export type DashboardMatriculaActiveTypeItem = {
  tipo_matricula: string
  total_estudiantes: number
}

export type DashboardMatriculaResponse = {
  dashboard_type?: 'matricula' | 'admisiones' | string
  trend?: DashboardMatriculaTrendItem[]
  states?: DashboardMatriculaStateItem[]
  active_by_type?: DashboardMatriculaActiveTypeItem[]
  active_regular_students?: number
  active_homologation_students?: number
  active_regular_homologation_students?: number
  total_estudiantes?: number
  consultado_en?: string
  admissions?: {
    total_ingresados?: number
    activos_desde_admision?: number
    inactivos_desde_admision?: number
    graduados_desde_admision?: number
    retirados_desde_admision?: number
    ingresaron_cabecera_matricula?: number
    pendientes_matricula?: number
    sin_estado_desde_admision?: number
    pendientes_o_no_activos?: number
    activos_sistema?: number
    total_con_codigo?: number
    total_con_cedula?: number
    vista_global_por_sin_registros?: boolean
    codigo_asesor?: string
    usuario_consultado?: string
    mensaje_vista?: string
    por_usuario_periodo?: Array<{
      codigo_periodo?: string
      detalle_periodo?: string
      anio_periodo?: number | null
      usuario_id?: string
      usuario_nombre?: string
      usuario_login?: string
      tipo_usuario?: string
      total_ingresados?: number
      ingresaron_carreraxestud?: number
      ingresaron_cabecera_matricula?: number
      pendientes_matricula?: number
      activos?: number
      inactivos?: number
      graduados?: number
      retirados?: number
      sin_estado?: number
    }>
  }
  criteria?: {
    fecha?: string
    excluidos?: string[]
    fuente?: string
  }
  detail?: string
}

export type DashboardMatriculaTrendStudentsResponse = {
  items?: MatriculaStudentItem[]
  total?: number
  anio?: number
  mes?: number
  detail?: string
}

export type AdmissionsDashboardStudentItem = {
  codestu?: string
  codigo_estud?: string
  cedula?: string
  nombre_estudiante?: string
  correo?: string
  telefono?: string
  codigo_periodo?: string
  detalle_periodo?: string
  tipo_matricula?: string
  anio_periodo?: number | null
  codcarrera?: string
  carrera?: string
  fecha_ingreso?: string
  codasesor?: string
  usuario_id?: string
  usuario_nombre?: string
  usuario_login?: string
  estado_codigo?: string
  estado_nombre?: string
  tiene_cabecera_matricula?: boolean
  num_matricula?: string
}

export type AdmissionsDashboardStudentsResponse = {
  items?: AdmissionsDashboardStudentItem[]
  total?: number
  estado?: string
  codigo_periodo?: string
  codigo_asesor?: string
  detail?: string
}

export type TeamsCatalogResponse = {
  value?: GraphTeam[]
  count?: number
  detail?: string
}

export type TeamParticipant = {
  id?: string
  displayName?: string
  mail?: string
  userPrincipalName?: string
  isOwner?: boolean
  isMember?: boolean
  role?: 'owner' | 'member' | 'owner_member'
  roleLabel?: string
}

export type TeamCourse = {
  id?: string
  displayName?: string
  description?: string
  membershipType?: string
  webUrl?: string
}

export type TeamRecording = {
  id?: string
  name?: string
  webUrl?: string
  startTime?: string
  endTime?: string
  startDateLabel?: string
  endDateLabel?: string
  startHourLabel?: string
  endHourLabel?: string
  durationSeconds?: number
  durationLabel?: string
  durationClock?: string
  durationHours?: number
  durationMinutes?: number
  durationRemainingSeconds?: number
  durationSource?: 'GRAPH_MEDIA_METADATA' | 'NOT_AVAILABLE' | string
  durationStatus?: 'VERIFIED_GRAPH_MEDIA' | 'NOT_AVAILABLE' | string
  timestampSource?: 'DRIVE_ITEM_FILE_LIFECYCLE' | string
  recordingTimeStatus?: 'NOT_PROVIDED_BY_DRIVE_ITEM' | string
  recordingTimeSource?: 'GRAPH_CALL_RECORDING' | 'GRAPH_CALL_RECORD' | string
  recordingTimeMatchSeconds?: number
  recordingTimeMatchStatus?: 'HIGH_CONFIDENCE' | string
  calculatedDurationSeconds?: number
  calculatedDurationLabel?: string
  calculatedDurationClock?: string
  callStartTime?: string
  callEndTime?: string
  callDateLabel?: string
  callStartHourLabel?: string
  callEndHourLabel?: string
  callDurationSeconds?: number
  callDurationLabel?: string
  callDurationClock?: string
  callDurationSource?: 'GRAPH_CALL_RECORD' | 'NOT_AVAILABLE' | string
  recordingStartTime?: string
  recordingEndTime?: string
  recordingDateLabel?: string
  recordingStartHourLabel?: string
  recordingEndHourLabel?: string
  recordingDurationSeconds?: number
  recordingDurationLabel?: string
  recordingDurationClock?: string
  recordingDurationSource?: 'GRAPH_MEDIA_METADATA' | 'GRAPH_CALL_RECORDING' | 'NOT_AVAILABLE' | string
  meetingId?: string
  callId?: string
  estimatedDurationSeconds?: number
  estimatedDurationLabel?: string
  estimatedDurationClock?: string
  estimatedDurationSource?: 'START_END_INTERVAL' | 'NOT_AVAILABLE' | string
  durationDifferenceSeconds?: number
  durationDifferenceLabel?: string
  durationsConsistent?: boolean | null
  uploadedAt?: string
  uploadedDateLabel?: string
  uploadedHourLabel?: string
  fileCreatedAt?: string
  fileCreatedDateLabel?: string
  fileCreatedHourLabel?: string
  modifiedAt?: string
  modifiedDateTimeLabel?: string
  lastModifiedDateTime?: string
  size?: number
  sizeBytes?: number
  sizeLabel?: string
  fileExtension?: string
  mimeType?: string
  metadataStatus?: 'COMPLETA' | 'INCOMPLETA' | string
  warnings?: string[]
  timeZone?: string
  storageSource?: 'TEAM_SHAREPOINT' | 'CHANNEL_SHAREPOINT' | 'OWNER_ONEDRIVE' | string
  sourceLabel?: string
  driveId?: string
  driveName?: string
  driveType?: string
  driveWebUrl?: string
  channelId?: string
  channelName?: string
  ownerId?: string
  ownerName?: string
  parentPath?: string
  siteId?: string
  listId?: string
  listItemId?: string
  createdByName?: string
  lastModifiedByName?: string
  eTag?: string
}

export type TeacherComplianceTeamsRecording = {
  team_id: string
  team_name: string
  recording_id: string
  name: string
  date: string
  start_hour: string
  end_hour: string
  call_duration: string
  recording_duration: string
  modified_by: string
  web_url: string
  source: 'Microsoft Graph'
}

export type TeamRecordingSummary = {
  totalDurationSeconds?: number
  totalDurationLabel?: string
  totalDurationClock?: string
  knownDurationCount?: number
  unknownDurationCount?: number
  totalEstimatedDurationSeconds?: number
  totalEstimatedDurationLabel?: string
  totalEstimatedDurationClock?: string
  completeMetadataCount?: number
  incompleteMetadataCount?: number
  comparedDurationCount?: number
  consistentDurationCount?: number
  differentDurationCount?: number
}

export type TeamRecordingDiscovery = {
  sourcesScanned?: number
  sourcesSucceeded?: number
  sourcesFailed?: number
  sourceCounts?: {
    TEAM_SHAREPOINT?: number
    CHANNEL_SHAREPOINT?: number
    OWNER_ONEDRIVE?: number
    [key: string]: number | undefined
  }
  warnings?: string[]
  cacheHit?: boolean
  queryElapsedMs?: number
  cacheTtlSeconds?: number
  timeSourcesScanned?: number
  timeSourcesSucceeded?: number
  timeSourcesFailed?: number
  verifiedTimeCount?: number
}

export type TeamAttendance = {
  id?: string
  topic?: string
  start?: string
  end?: string
  startLabel?: string
  endLabel?: string
  totalAttendees?: number
  timeZone?: string
}

export type TeamMessage = {
  id?: string
  etag?: string
  replyToId?: string | null
  parentMessageId?: string | null
  rootMessageId?: string | null
  isReply?: boolean
  threadSubject?: string
  threadCreatedDateTime?: string
  channelId?: string
  channelName?: string
  messageType?: string
  importance?: string
  locale?: string
  webUrl?: string
  createdDateTime?: string
  createdDateTimeUtc?: string
  createdDateTimeEcuador?: string
  lastModifiedDateTime?: string
  lastModifiedDateTimeEcuador?: string
  deletedDateTime?: string | null
  createdDateLabel?: string
  createdHourLabel?: string
  createdDateTimeLabel?: string
  subject?: string
  summary?: string
  from?: string
  eventDetail?: {
    type?: string | null
    text?: string | null
    raw?: Record<string, unknown>
  } | null
  eventDetailType?: string | null
  eventDetailText?: string | null
  bodyContentType?: string
  bodyText?: string
  bodyPreview?: string
  attachmentsCount?: number
  attachments?: Array<{
    id?: string
    name?: string
    contentType?: string
    contentUrl?: string
  }>
  reactionsCount?: number
  reactions?: Array<{
    reactionType?: string
    createdDateTime?: string
    userDisplayName?: string
    userId?: string
  }>
  replyCount?: number
  isRecordingRelated?: boolean
  activityType?: string
  activityLabel?: string
  timeZone?: string
}

export type TeamCallStatus = {
  is_in_call: boolean
  active_meeting?: {
    id?: string
    topic?: string
    start?: string
    end?: string
    startLabel?: string
    endLabel?: string
    source?: string
    channelId?: string
    channelName?: string
    joinWebUrl?: string
    timeZone?: string
  } | null
  participant_count?: number
  attendee_count?: number
  in_call_participants?: Array<{
    name?: string
    address?: string
    response?: string
    time?: string
  }>
  missing_count?: number
  missing_participants?: Array<{
    id?: string
    displayName?: string
    mail?: string
    userPrincipalName?: string
  }>
  note?: string
  timeZone?: string
}

export type TeamInviteMissingResponse = {
  ok?: boolean
  message?: string
  invited_count?: number
  detail?: string
  request_type?: string
  join_web_url?: string
  channel_id?: string
  missing_participants?: Array<{
    id?: string
    displayName?: string
    mail?: string
    userPrincipalName?: string
  }>
  needs_microsoft_connect?: boolean
  connect_url?: string
}

export type TeamCollectionResponse<T> = {
  value?: T[]
  count?: number
  note?: string
  detail?: string
  summary?: TeamRecordingSummary
  discovery?: TeamRecordingDiscovery
}

export type MatriculaSummaryResponse = {
  items?: MatriculaSummaryItem[]
  totals_by_tipo?: Record<string, number>
  totals_by_estado?: Record<string, number>
  consultado_en?: string
  detail?: string
}

export type MatriculaCareerStateSummaryItem = {
  escuela: string
  cod_anio_basica: string
  nombre_carrera: string
  tipo_matricula: MatriculaTipo
  estado_codigo: string
  estado_nombre: string
  total_estudiantes: number
}

export type MatriculaCareerStateSummaryResponse = {
  items?: MatriculaCareerStateSummaryItem[]
  totals_by_tipo?: Record<string, number>
  totals_by_estado?: Record<string, number>
  total_general?: number
  total_escuelas?: number
  total_carreras?: number
  fuente?: string
  consultado_en?: string
  detail?: string
}

export type MatriculaCareerStateStudentsResponse = {
  items?: Array<MatriculaStudentItem & {
    escuela?: string
    cod_anio_basica?: string
  }>
  total?: number
  criteria?: {
    cod_anio_basica?: string
    nombre_carrera?: string | null
    escuela?: string | null
    estado_codigo?: string | null
    tipo_matricula?: string | null
  }
  detail?: string
}

export type MatriculaPeriodSummaryItem = {
  estado_codigo?: string
  estado_nombre?: string
  punto_matricula?: 'PRIMERA' | 'ULTIMA'
  tipo_matricula: MatriculaTipo
  anio_periodo?: number | null
  codigo_periodo: string
  detalle_periodo: string
  total_estudiantes: number
  activos: number
  inactivos: number
  retirados: number
  graduados: number
}

export type MatriculaYearSummaryItem = {
  anio_periodo?: number | null
  fecha_inicio_min?: string | null
  fecha_fin_max?: string | null
  total_estudiantes: number
  acumulado_estudiantes?: number
  primeras?: number
  ultimas?: number
  activos: number
  inactivos: number
  retirados: number
  graduados: number
}

export type MatriculaPeriodSummaryResponse = {
  items?: MatriculaPeriodSummaryItem[]
  years?: MatriculaYearSummaryItem[]
  total?: number
  detail?: string
}

export type MatriculaListResponse = {
  total?: number
  anio_periodo?: number | null
  items?: MatriculaStudentItem[]
  detail?: string
}

export type IngresoVentasSummaryItem = {
  usuario_key: string
  usuario_id?: string
  codasesor?: string
  usuario_login?: string
  usuario_nombre: string
  usuario_estado?: string
  total_preinscripciones: number
  total_matriculados: number
  sin_matricula: number
  activos: number
  graduados: number
  inactivos: number
  retirados: number
  regular_r: number
  homologacion_h: number
  prematricula: number
  proceso_finalizado: number
  control_ingreso: number
}

export type IngresoVentasRow = {
  codestu: string
  cedula_preinscripcion?: string
  nombre_preinscripcion?: string
  correo_preinscripcion?: string
  telefono?: string
  codperiodo_preinscripcion?: string
  periodo_preinscripcion?: string
  anio_preinscripcion?: number | null
  codcarrera_preinscripcion?: string
  carrera_preinscripcion?: string
  codasesor?: string
  usuario_preinscripcion?: string
  fecha_preinscripcion?: string
  prematricula?: boolean
  proceso_finalizado?: boolean
  control_ingreso?: boolean
  usuario_id?: string
  usuario_login?: string
  usuario_nombre?: string
  usuario_estado?: string
  existe_datos_estud?: boolean
  existe_carreraxestud?: boolean
  origen_matricula?: string
  codigo_estud_matricula?: string
  cedula_matricula?: string
  nombre_matricula?: string
  estado_codigo_matricula?: string
  estado_nombre_matricula?: string
  tipo_matricula?: string
  codcarrera_matricula?: string
  carrera_matricula?: string
  periodo_matricula?: string
  detalle_periodo_matricula?: string
  anio_periodo_matricula?: number | null
  matricula_validada?: boolean
  estado_cruce?: string
  nombre_final?: string
  cedula_final?: string
  carrera_final?: string
  periodo_final?: string
  anio_final?: number | null
}

export type IngresoVentasResponse = {
  generated_at?: string
  total?: number
  totals?: {
    total_preinscripciones?: number
    total_matriculados?: number
    sin_matricula?: number
    asesores?: number
    total_datos_estud?: number
    total_carreraxestud?: number
    total_base_porcentaje?: number
    activos?: number
    graduados?: number
    inactivos?: number
    retirados?: number
    regular_r?: number
    homologacion_h?: number
  }
  summary?: IngresoVentasSummaryItem[]
  items?: IngresoVentasRow[]
  datos_estud_items?: IngresoVentasRow[]
  criteria?: {
    fuente?: string
    join_usuario?: string
    join_estudiante?: string
  }
  detail?: string
}

export type LegacyReportKey =
  | 'provincia'
  | 'provincia_genero'
  | 'provincia_carrera'
  | 'carrera'
  | 'graduados_2025'
  | 'genero'
  | 'genero_docentes'
  | 'periodo'
  | 'matriculados'
  | 'becas_edades'
  | 'preinscritos'
  | 'docentes'
  | 'documentos'
  | 'seguimiento'
  | 'practicas'
  | 'evaluacion_docente'
  | 'moodle_notas'
  | 'notas_carrera_materia'
  | 'estud_per_c_m'
  | 'correos_intec'
  | 'microsoft_audit'
  | 'pagos_matricula'

export type LegacyReportOption = {
  value: string
  label: string
}

export type LegacyReportDefinition = {
  key: LegacyReportKey
  title: string
  description?: string
  category?: string
  source_tables?: string[]
  filters?: string[]
  estado_options?: LegacyReportOption[]
}

export type LegacyFunctionalInventoryItem = {
  module: string
  legacy_sources?: string[]
  capabilities?: string[]
}

export type LegacyReportsCatalogResponse = {
  reports?: LegacyReportDefinition[]
  functional_inventory?: LegacyFunctionalInventoryItem[]
  periodos?: LegacyReportOption[]
  carreras?: LegacyReportOption[]
  anios?: LegacyReportOption[]
  detail?: string
}

export type ModernizedLegacyReport = {
  key: string
  title: string
  category: string
  legacy_rpt: string[]
  legacy_pages: string[]
  source_tables: string[]
  legacy_filters: string[]
  modern_equivalent: string
  modern_format: string[]
  migration_status: 'modernizado' | 'base' | 'pendiente' | string
  notes: string
  engine?: string
  source_engine?: string
  target_engine?: string
  replacement_rule?: string
  deprecated?: boolean
  replacement_endpoint?: string
}

export type ModernizedLegacyReportsCatalogResponse = {
  project: string
  source_engine: string
  target_engine: string
  strategy: string
  totals: {
    total: number
    modernizado: number
    base: number
    pendiente: number
  }
  reports: ModernizedLegacyReport[]
}

export type LegacyCrystalReport = ModernizedLegacyReport
export type LegacyCrystalCatalogResponse = ModernizedLegacyReportsCatalogResponse

export type LegacyReportFilters = {
  reportKey?: LegacyReportKey
  periodo?: string
  periodos?: string[] | string
  carrera?: string
  estado?: string
  anio?: string
  genero?: string
  buscar?: string
  limit?: number
}

export type LegacyReportRow = Record<string, string | number | boolean | null | undefined>

export type LegacyActiveGradeStudent = {
  registro_clave: string
  estudiante_codigo: string
  cedula?: string
  estudiante: string
  carrera?: string
  tipo_matricula?: 'R' | 'H' | string
  estado_codigo: string
  matriculas_activas?: number
  total_materias: number
  aprobadas: number
  reprobadas: number
  pendientes: number
}

export type LegacyActiveGradeStudentsResponse = {
  generated_at?: string
  source?: string
  columns?: string[]
  items?: LegacyActiveGradeStudent[]
  total?: number
  total_matriculas_activas?: number
  criteria?: Record<string, string | number | null | undefined>
  detail?: string
}

export type LegacyGradeUpdatePayload = {
  codigo_estud: number
  cod_anio_basica: number
  codigo_periodo: number
  codigo_materia: number
  paralelo: string
  num_matricula: number
  num_grupo: number
  es_homologacion: boolean
  teoria_homo?: number | null
  practica_homo?: number | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  asistencia?: number | null
  recuperacion?: number | null
}

export type LegacyGradeUpdateResponse = {
  ok?: boolean
  message?: string
  affected_rows?: number
  promedio_p1?: number | null
  promedio_p2?: number | null
  promedio_p3?: number | null
  promedio_final?: number | null
  condicion?: string
  detail?: string
}

export type LegacyReportResponse = {
  generated_at?: string
  source?: string
  report?: LegacyReportDefinition
  columns?: string[]
  rows?: LegacyReportRow[]
  total?: number
  criteria?: Record<string, string | number | null | undefined>
  detail?: string
}

export type SisAcademicoFieldOption = {
  value: string
  label: string
}

export type SisAcademicoField = {
  name: string
  label: string
  type?: string
  required?: boolean
  readonly?: boolean
  options?: SisAcademicoFieldOption[]
}

export type SisAcademicoSection = {
  key: string
  title: string
  category: string
  description?: string
  table?: string
  key_fields?: string[]
  list_fields?: SisAcademicoField[]
  detail_fields?: SisAcademicoField[]
  editable_fields?: SisAcademicoField[]
  create_fields?: SisAcademicoField[]
}

export type SisAcademicoRow = Record<string, string | number | boolean | null | undefined>

export type SisAcademicoCatalogResponse = {
  sections?: SisAcademicoSection[]
  categories?: string[]
  detail?: string
}

export type SisAcademicoListResponse = {
  section?: SisAcademicoSection
  rows?: SisAcademicoRow[]
  total?: number
  page?: number
  page_size?: number
  total_pages?: number
  has_previous?: boolean
  has_next?: boolean
  generated_at?: string
  detail?: string
}

export type SisAcademicoRecordResponse = {
  section?: SisAcademicoSection
  record?: SisAcademicoRow
  detail?: string
}

export type SisAcademicoSaveResponse = {
  ok?: boolean
  message?: string
  affected_rows?: number
  action?: string
  detail?: string
}

export type CertificadosPeriodOption = {
  cod_periodo: string
  detalle_periodo: string
  fecha_inicio?: string | null
  fecha_fin?: string | null
  orden?: number | null
}

export type CertificadosSemesterOption = {
  value: string
  label: string
}

export type CertificadosCatalogResponse = {
  becas?: string[]
  periodos?: CertificadosPeriodOption[]
  semestres?: CertificadosSemesterOption[]
  detail?: string
}

export type FechaGradoPeriodOption = {
  codigo_periodo: string
  detalle_periodo?: string
  fecha_inicio?: string
  fecha_fin?: string
  anio?: number | null
}

export type FechaGradoCareerOption = {
  codigo_carrera: string
  nombre_carrera: string
  total_estudiantes?: number
}

export type FechaGradoCatalogResponse = {
  periodos?: FechaGradoPeriodOption[]
  carreras?: FechaGradoCareerOption[]
}

export type FechaGradoStudent = {
  codigo_estud: string
  cedula?: string
  nombres: string
  codigo_carrera?: string
  carrera?: string
  codigo_periodo?: string
  periodo?: string
  fecha_grado?: string
  fecha_emision_senescyt?: string
  cod_refrendacion?: string
  cod_registro?: string
  nomina?: string
}

export type FechaGradoStudentsResponse = {
  items?: FechaGradoStudent[]
  total?: number
  periodo?: string
  carrera?: string
}

export type FechaGradoSavePayload = {
  items: Array<{
    codigo_estud: string
    fecha_grado?: string | null
    fecha_emision_senescyt?: string | null
    cod_refrendacion?: string | null
    cod_registro?: string | null
    nomina?: string | null
  }>
}

export type FechaGradoSaveResponse = {
  ok: boolean
  actualizados: number
}

export type FechaGradoImportResponse = {
  ok: boolean
  actualizados: number
  origen?: 'PDF' | 'EXCEL' | string
  puede_importar?: boolean
  procesados?: number
  filas_detectadas?: number
  encontrados?: number
  nuevos?: number
  cambios?: number
  sin_cambios?: number
  nominas_compartidas?: number
  hoja?: string
  fila_encabezado?: number
  archivos_detectados?: number
  archivos_procesados?: number
  archivos_sin_registros?: string[]
  advertencias?: string[]
  archivos_detalle?: Array<{
    archivo?: string
    registros_detectados?: number
    registros_validos?: number
    metodo_extraccion?: string
  }>
  vista_previa_limitada?: boolean
  errores?: Array<{
    fila?: number
    archivo?: string
    cedula?: string
    identificacion?: string
    error?: string
  }>
  no_encontrados?: Array<{
    fila?: number
    archivo?: string
    cedula?: string
    identificacion?: string
    error?: string
  }>
  vista_previa?: Array<{
    fila?: number
    registro_documento?: number
    archivo?: string
    metodo_extraccion?: string
    cedula?: string
    identificacion?: string
    codigo_estud?: string
    nombres?: string
    fecha_grado?: string
    fecha_emision_senescyt?: string
    cod_registro?: string
    nomina?: string
    estado?: 'NUEVO' | 'ACTUALIZAR' | 'SIN_CAMBIOS' | 'NO_ENCONTRADO' | 'DUPLICADO_EN_BASE' | string
    campos_modificados?: string[]
    valores_actuales?: {
      fecha_grado?: string
      fecha_emision_senescyt?: string
      cod_registro?: string
      nomina?: string
    }
  }>
  nominas_compartidas_detalle?: Array<{
    nomina?: string
    fecha_emision_senescyt?: string
    estudiantes?: number
    identificaciones?: string[]
  }>
  actualizados_detalle?: Array<{
    fila?: number
    archivo?: string
    cedula?: string
    codigo_estud?: string
    fecha_grado?: string
    fecha_emision_senescyt?: string
    cod_registro?: string
    nomina?: string
    registros?: number
  }>
  resumen?: string
  detail?: string
}

export type FechaGradoVerificationRow = {
  codigo_estud: string
  cedula?: string
  nombres: string
  estado_codigo?: string
  estado_nombre?: string
  estado_raw?: string
  fecha_grado?: string
  fecha_emision_senescyt?: string
  cod_refrendacion?: string
  cod_registro?: string
  nomina?: string
}

export type FechaGradoVerificationResponse = {
  items?: FechaGradoVerificationRow[]
  total?: number
  page?: number
  page_size?: number
  total_pages?: number
  con_fecha?: number
  sin_fecha?: number
  con_senescyt?: number
  sin_senescyt?: number
  estado?: string
}

export type CertificadosReprobada = {
  codigo_materia?: string
  cod_materia?: string
  nombre?: string
  promedioFinal?: number | null
  caprueba?: string
  controlAprueba?: string
}

export type CertificadosStudent = {
  codestud: string
  certificado_ref?: string
  nombres: string
  correo_personal?: string
  correo_intec?: string
  estado?: string
  cod_anio_basica?: string
  carrera?: string
  codigo_periodo_matricula?: string
  periodo_matricula?: string
  num_matricula?: string
  reprobadas_count?: number
  reprobadas_detalle?: CertificadosReprobada[]
  puede_generar?: boolean
  puede_generar_matricula?: boolean
  puede_generar_promocion?: boolean
  motivo_bloqueo_matricula?: string
  motivo_bloqueo?: string
}

export type CertificadosStudentsResponse = {
  items?: CertificadosStudent[]
  total?: number
  generated_at?: string
  criteria?: Record<string, string | number | null | undefined>
  detail?: string
}

export type CertificateRenameItem = {
  original_name: string
  new_name?: string
  cedula?: string
  nombres?: string
  codigo_estud?: string
  carrera?: string
  periodo?: string
  status?: 'LISTO' | 'RENOMBRADO_DOCUMENTO' | 'SIN_CEDULA' | 'CEDULA_NO_ENCONTRADA' | 'NO_PDF' | string
  detail?: string
}

export type CertificateRenameResponse = {
  items?: CertificateRenameItem[]
  summary?: {
    total?: number
    ready?: number
    without_cedula?: number
    not_found?: number
    not_pdf?: number
  }
  generated_at?: string
  detail?: string
}

export type CertificateRenameLocalSaveResponse = CertificateRenameResponse & {
  local_dir?: string
  report?: string
  saved?: number
}

export type CertificadosGeneratePayload = {
  tipo_beca?: string
  tipo_certificado?: 'ambos' | 'matricula' | 'promocion'
  periodo: string
  proximo_periodo?: string
  semestre?: number | null
  estudiantes: string[]
}

export type CredentialProvisionPerson = {
  primer_nombre: string
  segundo_nombre: string
  primer_apellido: string
  segundo_apellido: string
  cedula: string
  fila_origen?: number | null
}

export type CredentialPersonType = 'ESTUDIANTE' | 'PROFESOR'

export type CredentialLicenseConfig = {
  person_type: CredentialPersonType
  configured: boolean
  name: string
  sku_part_number: string
  status: 'DISPONIBLE' | 'SIN_CUPOS' | 'NO_DISPONIBLE' | string
  available_units: number
  detail?: string
}

export type CredentialProvisionConfig = {
  domain: string
  year: number
  graph_configured: boolean
  license_configured: boolean
  license_type: 'ESTUDIANTE' | string
  license_name: string
  license_sku_part_number: string
  license_status: 'DISPONIBLE' | 'SIN_CUPOS' | 'NO_DISPONIBLE' | string
  license_available_units: number
  license_detail?: string
  licenses: Record<CredentialPersonType, CredentialLicenseConfig>
  moodle_configured: boolean
  moodle_url: string
  identity_count: number
  max_users: number
  report_ttl_minutes: number
  detail?: string
}

export type CredentialAnalysisRow = CredentialProvisionPerson & {
  correo_propuesto: string
  estado: 'VALIDO' | 'ERROR' | string
  errores: string[]
}

export type CredentialAnalysisResponse = {
  rows: CredentialAnalysisRow[]
  summary: {
    total: number
    validos: number
    errores: number
  }
  filename: string
  detail?: string
}

export type CredentialProvisionResultRow = CredentialProvisionPerson & {
  tipo_persona: CredentialPersonType
  correo_institucional: string
  clave_permanente: string
  graph_user_id?: string
  estado_graph: string
  error_graph?: string
  estado_licencia: string
  error_licencia?: string
  licencia_nombre?: string
  licencia_sku_part_number?: string
  moodle_user_id?: number | null
  moodle_username?: string
  estado_moodle: string
  error_moodle?: string
  estado_general: string
  errores?: string[]
  clave_emitida: boolean
  observacion: string
}

export type CredentialProvisionResponse = {
  ok: boolean
  batch_id: string
  tipo_persona?: CredentialPersonType
  rows: CredentialProvisionResultRow[]
  summary: {
    total: number
    completos: number
    parciales: number
    fallidos: number
  }
  report_id: string
  report_expires_minutes: number
  message: string
  detail?: string
}

export type CredentialProvisionPayload = {
  tipo_persona: CredentialPersonType
  modo: 'INDIVIDUAL' | 'EXCEL'
  usuarios: CredentialProvisionPerson[]
}

export type CredentialHistoryRow = {
  id: number
  batch_id: string
  tipo_persona: CredentialPersonType
  modo: 'INDIVIDUAL' | 'EXCEL' | string
  fila_origen?: number | null
  cedula: string
  nombres: string
  correo_institucional: string
  estado_graph: string
  estado_licencia: string
  estado_moodle: string
  estado_general: string
  clave_emitida: boolean
  reporte_disponible: boolean
  observacion: string
  numero_descargas: number
  fecha_ultima_descarga?: string | null
  usuario_ultima_descarga?: string
  usuario_creacion: string
  fecha_creacion?: string | null
}

export type CredentialHistoryResponse = {
  rows: CredentialHistoryRow[]
  count: number
  detail?: string
}

export type MassEmailRecipient = {
  id: string
  cedula: string
  email: string
  nombres?: string | null
  codigo?: string | null
  login?: string | null
  tipo_usuario?: string | null
  email_tipo?: string | null
  source_table?: string | null
  attachment_count?: number
  status?: string
  error?: string
}

export type MassEmailResolvePayload = {
  cedulas: string | string[]
  include_personal?: boolean
  include_intec?: boolean
  include_docentes?: boolean
  include_administrativos?: boolean
}

export type MassEmailResolveResponse = {
  cedulas?: string[]
  items?: MassEmailRecipient[]
  total?: number
  not_found?: string[]
  sources?: Record<string, number>
  graph_mail_sender?: string | null
  detail?: string
}

export type MassEmailSearchResponse = {
  query?: string
  items?: MassEmailRecipient[]
  total?: number
  graph_mail_sender?: string | null
  detail?: string
}

export type MassEmailExcelRow = {
  excel_row: number
  cedula?: string
  nombre_excel?: string
  correo_excel?: string
  documento?: string
  carrera?: string
  periodo?: string
  referencia?: string
  estado?: 'LISTO' | 'SIN_CEDULA' | 'SIN_CORREO' | string
  motivo?: string
  destinatarios?: number
  raw?: Record<string, string | number | boolean | null | undefined>
}

export type MassEmailExcelResponse = {
  filename?: string
  sheet?: string
  columns?: string[]
  detected_columns?: Record<string, string | null | undefined>
  rows?: MassEmailExcelRow[]
  items?: MassEmailRecipient[]
  not_found?: string[]
  sources?: Record<string, number>
  summary?: {
    total?: number
    con_cedula?: number
    listos?: number
    sin_correo?: number
    sin_cedula?: number
    cedulas_unicas?: number
    cedulas_duplicadas?: number
    filas_con_documento?: number
    filas_con_correo_excel?: number
    destinatarios?: number
  }
  warnings?: string[]
  graph_mail_sender?: string | null
  detail?: string
}

export type MassEmailSendResponse = {
  ok?: boolean
  sent?: number
  failed?: number
  skipped?: number
  skipped_attachments?: number
  attachment_count?: number
  send_mode?: 'individual' | 'single' | string
  recipients?: MassEmailRecipient[]
  message?: string
  detail?: string
}

export type PreinscriptionPeriodOption = {
  codigo_periodo: string
  detalle_periodo: string
  estado?: string
  periodo?: string
  anio?: number | null
  total_preinscripciones?: number
}

export type PreinscriptionCareerOption = {
  cod_anio_basica: string
  nombre_basica: string
  estado?: string
  abrevia?: string
  tipo_escuela?: string
  semestres_disponibles?: number
  costo_presencial_total?: number
  costo_virtual_total?: number
  costo_presencial_semestre?: number
  costo_virtual_semestre?: number
  costos_semestres?: Array<{
    semestre?: number
    presencial?: number
    virtual?: number
  }>
  total_preinscripciones?: number
}

export type PreinscriptionProvinceOption = {
  codprov: string
  descripcion: string
}

export type PreinscriptionProcessOption = {
  value: string
  label: string
  detail?: string
  amount?: number | null
  variable?: boolean
  min_amount?: number | null
  max_amount?: number | null
  parent?: string
  modalidad?: string
}

export type PreinscriptionDocuments = {
  urlcedula?: string
  urltitulo?: string
  urldeposito?: string
  urlconvenio?: string
  total_requeridos?: number
  total_cargados?: number
  completos?: boolean
}

export type PreinscriptionPhotoStatus = {
  existe?: boolean
  id_solicitud_foto?: string
  codigo_estud?: string
  cedula?: string
  id_imagen?: string
  estado?: 'SIN_FOTO' | 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'CANCELADA' | string
  foto_url?: string
  nombre_original?: string
  mime_type?: string
  tamanio_bytes?: number | null
  es_principal?: boolean
  observacion_estudiante?: string
  observacion_admin?: string
  usuario_solicita?: string
  fecha_solicitud?: string
  usuario_revisa?: string
  fecha_revision?: string
  mensaje?: string
}

export type PreinscriptionCabecera = {
  codigo_estud?: string
  cod_anio_basica?: string
  codigo_periodo?: string
  num_matricula?: string
  numcodigo?: string
  fecha_pago?: string
  valor?: number | null
  inscrip_valor?: number | null
  matri_valor?: number | null
  costo_semestre?: number | null
  semestres_convenio?: string | number | null
  cuota1?: number | null
  beca?: number | null
  descuento?: number | null
  tipo_beca?: string
  porcentaje_beca?: number | null
  num_pago?: number | null
  detalle_pago?: string
  no_deposito?: string
  banco?: string
  valor_registrado?: number | null
  control_matricula?: number | null
}

export type PreinscriptionItem = {
  num: string
  codestu?: string
  datos_codigo_estud?: string
  cedula?: string
  apellidos_nombre?: string
  codperiodo?: string
  periodo?: string
  correo?: string
  telefono?: string
  usuario?: string
  fecha_ingreso?: string
  codprov?: string
  codcarrera?: string
  carrera?: string
  codmodalida?: string
  codjornada?: number | null
  contacte?: string
  hora?: string
  codasesor?: string
  observacion_contacto?: string
  observacion_ingreso?: string
  cod_lecontacto?: string
  cod_desea_ingresar?: string
  prematricula?: boolean
  cod_como_conoce?: string
  coddescconve?: string
  coddescconvevalor?: number | null
  coddescdeptransf?: string
  correo_enviado?: boolean
  asignado?: boolean
  nombre1?: string
  nombre2?: string
  apellido1?: string
  apellido2?: string
  proceso_finalizado?: boolean
  control_ingreso?: boolean
  nom_representante?: string
  num_representante?: string
  documentos?: PreinscriptionDocuments
  en_cabecera_matricula?: boolean
  cabecera?: PreinscriptionCabecera
}

export type PreinscriptionCatalogResponse = {
  periodos?: PreinscriptionPeriodOption[]
  carreras?: PreinscriptionCareerOption[]
  provincias?: PreinscriptionProvinceOption[]
  modalidades?: PreinscriptionProcessOption[]
  jornadas?: PreinscriptionProcessOption[]
  le_contactos?: PreinscriptionProcessOption[]
  desea_ingresar?: PreinscriptionProcessOption[]
  como_conoce?: PreinscriptionProcessOption[]
  descuentos_convenio?: PreinscriptionProcessOption[]
  descuentos_valores?: PreinscriptionProcessOption[]
  descuentos_deposito?: PreinscriptionProcessOption[]
  becas?: PreinscriptionProcessOption[]
  detail?: string
}

export type PreinscriptionListResponse = {
  total?: number
  items?: PreinscriptionItem[]
  totals?: {
    total?: number
    con_cabecera?: number
    sin_cabecera?: number
    documentos_completos?: number
    documentos_pendientes?: number
    mis_registros?: number
    usuario_actual?: number
  }
  criteria?: Record<string, string>
  detail?: string
}

export type PreinscriptionDocumentsPayload = {
  urlcedula: string
  urltitulo: string
  urldeposito: string
  urlconvenio: string
}

export type PreinscriptionFollowupPayload = {
  contacte: string
  hora: string
  observacion_contacto: string
  observacion_ingreso: string
  cod_lecontacto: string
  cod_desea_ingresar: string
  cod_como_conoce: string
  coddescconve: string
  coddescconvevalor: string
  coddescdeptransf: string
  nom_representante: string
  num_representante: string
  prematricula: boolean
  proceso_finalizado: boolean
  control_ingreso: boolean
  correo_enviado: boolean
  asignado: boolean
}

export type PreinscriptionCreatePayload = {
  apellidos_nombre: string
  nombres?: string
  apellidos?: string
  cedula: string
  codprov: string
  codperiodo?: string
  codcarrera?: string
  correo?: string
  telefono?: string
  codmodalida?: number
  codjornada?: number
  tipo_beca?: string
  porcentaje_beca?: number
  valor_beca?: number
  motivo_beca?: string
  semestres_convenio?: string | number
}

export type PreinscriptionCreateResponse = {
  ok?: boolean
  message?: string
  item?: PreinscriptionItem
  asesor?: {
    codigo?: string
    usuario?: string
  }
  finanzas?: {
    ok?: boolean
    cuenta_estudiante_id?: number | null
    beca_id?: number | null
    beca_estado?: string
    requiere_aprobacion?: boolean
    puede_continuar?: boolean
    porcentaje_beca?: number
    detail?: string
  }
  detail?: string
}

export type AcademicSystemDatabaseStatus = {
  key: string
  name: string
  role: string
  domains: string[]
  relation: string
  primary: boolean
  kind: 'database' | 'contract' | string
  configured: boolean
  available: boolean
  status: 'ONLINE' | 'PARTIAL' | 'OFFLINE' | 'NOT_CONFIGURED' | string
}

export type AcademicSystemDomainStatus = {
  key: string
  status: 'READY' | 'PARTIAL' | 'UNAVAILABLE' | string
  source_keys: string[]
  available_sources: number
  total_sources: number
}

export type AcademicSystemIntegrationResponse = {
  generated_at: string
  primary_database: string
  databases: AcademicSystemDatabaseStatus[]
  domains: AcademicSystemDomainStatus[]
  summary: {
    total: number
    configured: number
    available: number
    degraded: number
  }
}

export type PreinscriptionScholarshipStatus = {
  ok?: boolean
  message?: string
  beca_id?: number | null
  tipo_beca?: string
  porcentaje_beca?: number
  valor_beca?: number
  estado?: string
  requiere_aprobacion?: boolean
  puede_continuar?: boolean
  fecha_solicitud?: string
  fecha_aprobacion?: string
  usuario_aprobacion?: string
  detail?: string
}

export type PreinscriptionScholarshipApprovalItem = {
  beca_id: number
  codigo_estud: string
  cedula: string
  estudiante: string
  codigo_carrera: string
  carrera: string
  codigo_periodo: string
  periodo: string
  tipo_beca: string
  porcentaje_beca: number
  valor_beca: number
  motivo: string
  fecha_solicitud: string
  estado: string
}

export type PreinscriptionScholarshipApprovalListResponse = {
  ok?: boolean
  items: PreinscriptionScholarshipApprovalItem[]
  total: number
  threshold: number
  detail?: string
}

export type ScholarshipBeneficiaryItem = PreinscriptionScholarshipApprovalItem & {
  fecha_aprobacion: string
  usuario_aprobacion: string
}

export type ScholarshipBeneficiaryListResponse = {
  ok?: boolean
  items: ScholarshipBeneficiaryItem[]
  total: number
  valor_total: number
  porcentaje_promedio: number
  detail?: string
}

export type ScholarshipConfigurationItem = {
  id: number
  codigo: string
  nombre: string
  es_variable: boolean
  porcentaje: number | null
  porcentaje_minimo: number | null
  porcentaje_maximo: number | null
  protegida: boolean
  activo: boolean
  fecha_actualizacion?: string
  usuario_actualizacion?: string
}

export type ScholarshipConfigurationPayload = {
  codigo?: string
  nombre: string
  es_variable: boolean
  porcentaje?: number | null
  porcentaje_minimo?: number | null
  porcentaje_maximo?: number | null
  activo: boolean
}

export type ScholarshipConfigurationListResponse = {
  ok?: boolean
  items: ScholarshipConfigurationItem[]
  total: number
  detail?: string
}

export type ScholarshipConfigurationSaveResponse = {
  ok?: boolean
  message?: string
  item?: ScholarshipConfigurationItem
  detail?: string
}

export type PreinscriptionCedulaValidationResponse = {
  exists?: boolean
  message?: string
  item?: Partial<PreinscriptionItem>
  detail?: string
}

export type PreinscriptionDocumentsSaveResponse = {
  ok?: boolean
  message?: string
  item?: PreinscriptionItem
  en_cabecera_matricula?: boolean
  codigo_documentacion?: string
  detail?: string
}

export type PreinscriptionFollowupSaveResponse = {
  ok?: boolean
  message?: string
  item?: PreinscriptionItem
  detail?: string
}

export type PreinscriptionCabeceraPayload = {
  fecha_pago?: string | null
  valor: number
  inscrip_valor: number
  matri_valor: number
  costo_semestre?: number
  semestres_convenio?: string | number
  control_matricula: number
  num_cuotas: number
  tipo_beca?: string
  porcentaje_beca: number
  descuento: number
  num_pago: number
  detalle_pago: string
  no_deposito: string
  banco: string
}

export type PreinscriptionCabeceraSaveResponse = {
  ok?: boolean
  message?: string
  action?: string
  item?: PreinscriptionItem
  cabecera?: PreinscriptionCabecera
  num_matricula?: string
  codigo_documentacion?: string
  convenio_url?: string
  detail?: string
}

export type PreinscriptionDocumentUploadResponse = {
  ok?: boolean
  message?: string
  field?: string
  url?: string
  item?: PreinscriptionItem
  codigo_documentacion?: string
  detail?: string
}

export type PreinscriptionPhotoResponse = {
  ok?: boolean
  message?: string
  foto?: PreinscriptionPhotoStatus
  detail?: string
}

export type CarnetPersonaTipo = 'ESTUDIANTE' | 'DOCENTE' | 'ADMINISTRATIVO'

export type CarnetPersona = {
  tipo_persona: CarnetPersonaTipo | string
  codigo_persona: string
  cedula?: string
  nombre?: string
  correo?: string
  fuente?: string
  foto?: CarnetPhotoStatus
}

export type CarnetPhotoStatus = {
  persona?: CarnetPersona
  id_solicitud?: string
  id_imagen?: string
  estado?: 'SIN_FOTO' | 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'CANCELADA' | 'VENCIDA' | string
  estado_revision?: string
  mensaje?: string
  mensaje_vigencia?: string
  observacion?: string
  foto_url?: string
  nombre_archivo?: string
  mime_type?: string
  tamano_bytes?: number | null
  es_principal?: boolean
  puede_subir?: boolean
  puede_descargar_carnet?: boolean
  meses_vigencia?: number | null
  carnet_emitido?: boolean
  fecha_solicitud?: string
  fecha_revision?: string
  fecha_vigencia_hasta?: string
  fecha_emision?: string
  fecha_creacion?: string
}

export type CarnetSearchResponse = {
  total?: number
  items?: CarnetPersona[]
  detail?: string
}

export type CarnetPhotoResponse = {
  ok?: boolean
  message?: string
  foto?: CarnetPhotoStatus
  detail?: string
}

export type PreinscriptionRevertResponse = {
  ok?: boolean
  message?: string
  deleted?: Record<string, number>
  detail?: string
}

export type AcademicCareerOption = {
  cod_anio_basica: string
  nombre_basica: string
  estado?: string
  abrevia?: string
  tipo_escuela?: string
  total_matriculados?: number
}

export type AcademicPeriodOption = {
  codigo_periodo: string
  detalle_periodo: string
  estado?: string
  periodo?: string
  anio?: number | null
  fecha_inicio?: string
  fecha_fin?: string
  tipo_matricula?: string
  total_matriculados?: number
}

export type AcademicEnrollmentTypeOption = {
  value: MatriculaTipo
  label: string
}

export type AcademicEnrollmentMode = 'individual' | 'masiva' | 'prerrequisitos'

export type AcademicPrerequisiteRule = {
  id: number
  cod_anio_basica: string
  nombre_carrera?: string
  codigo_materia_previa: string
  cod_materia_previa?: string
  nombre_materia_previa?: string
  semestre_materia_previa?: number | null
  codigo_materia_consecutiva: string
  cod_materia_consecutiva?: string
  nombre_materia_consecutiva?: string
  semestre_materia_consecutiva?: number | null
  bloqueada_por_reprobacion: boolean
  es_autorreferencia?: boolean
}

export type AcademicPrerequisiteRulePayload = {
  cod_anio_basica: number
  codigo_materia_previa: number
  codigo_materia_consecutiva: number
  bloqueada_por_reprobacion: boolean
}

export type AcademicPrerequisiteRulesResponse = {
  total?: number
  active?: number
  items?: AcademicPrerequisiteRule[]
  detail?: string
}

export type AcademicPrerequisiteRuleSaveResponse = {
  ok?: boolean
  message?: string
  item?: AcademicPrerequisiteRule
  detail?: string
}

export type AcademicEnrollmentCatalogResponse = {
  carreras?: AcademicCareerOption[]
  periodos?: AcademicPeriodOption[]
  jornadas?: PreinscriptionProcessOption[]
  paralelos?: AcademicTeacherParallelOption[]
  niveles_materia?: number[]
  tipos_matricula?: AcademicEnrollmentTypeOption[]
  detail?: string
}

export type AcademicEnrollmentCareersResponse = {
  total?: number
  items?: AcademicCareerOption[]
  detail?: string
}

export type AcademicEnrollmentStudent = {
  codigo_estud: string
  cedula?: string
  cedula_normalizada?: string
  nombre_estudiante: string
  estado_codigo?: string
  correo_personal?: string
  correo_intec?: string
  carrera_actual?: string
  cod_anio_basica_actual?: string
  periodo_actual?: string
  detalle_periodo_actual?: string
  materias_actuales?: number
}

export type AcademicEnrollmentCohortStudent = AcademicEnrollmentStudent & {
  cod_anio_basica?: string
  nombre_carrera?: string
  codigo_periodo?: string
  detalle_periodo?: string
  num_matricula?: string
  paralelo?: string
  num_grupo?: number | null
  tipo_matricula?: string
  nivel_actual?: number | null
  aprobadas_nivel_actual?: number
  materias_nivel_actual?: number
  habilitado_promocion?: boolean
  materias?: Array<{
    codigo_materia?: string
    nombre_materia?: string
    semestre?: number | null
    nota?: number | null
    aprobada?: boolean | null
  }>
  materias_reprobadas?: Array<{
    codigo_materia?: string
    nombre_materia?: string
    semestre?: number | null
    nota?: number | null
  }>
}

export type AcademicEnrollmentBalanceItem = {
  cod_anio_basica?: string
  nombre_carrera?: string
  paralelo?: string
  nivel?: string
  total_estudiantes: number
  total_materias?: number
}

export type AcademicEnrollmentCohortResponse = {
  total?: number
  criteria?: {
    codigo_periodo?: string
    cod_anio_basica?: string
    paralelo?: string
  }
  items?: AcademicEnrollmentCohortStudent[]
  paralelos?: AcademicEnrollmentBalanceItem[]
  balance?: {
    por_carrera?: AcademicEnrollmentBalanceItem[]
    por_paralelo?: AcademicEnrollmentBalanceItem[]
    por_nivel?: AcademicEnrollmentBalanceItem[]
  }
  detail?: string
}

export type AcademicEnrollmentCabecera = {
  codigo_estud: string
  cod_anio_basica: string
  codigo_periodo: string
  num_matricula?: string
  fecha_pago?: string
  valor?: number | null
  inscrip_valor?: number | null
  matri_valor?: number | null
  jornada?: string
  cod_jornada?: number | null
  control_matricula?: number | null
  carrera?: string
  periodo?: string
  fecha_inicio_periodo?: string
  fecha_fin_periodo?: string
  tipo_periodo?: string
}

export type AcademicEnrollmentSubject = {
  codigo_materia: string
  cod_materia?: string
  nombre_materia: string
  semestre?: number | null
  creditos?: number | null
  orden?: number | null
  num_malla?: number | null
  horas?: number | null
  tipo_materia?: string
  accion?: string
  materias_previas?: string[]
  materias_previas_codigos?: number[]
  motivo?: string
}

export type AcademicEnrollmentCurrentSubject = AcademicEnrollmentSubject & {
  paralelo?: string
  num_grupo?: number | null
  num_matricula?: string
  fecha_matricula?: string
  tipo_matricula?: string
  control_matricula?: number | null
  tiene_notas?: boolean
}

export type AcademicEnrollmentHistorySubject = AcademicEnrollmentCurrentSubject & {
  promedio_final?: number | null
  recuperacion?: number | null
  asistencia?: number | null
  estado?: string
}

export type AcademicEnrollmentHistoryPeriod = {
  codigo_periodo: string
  periodo?: string
  fecha_inicio?: string
  fecha_fin?: string
  tipo_periodo?: string
  cod_anio_basica: string
  carrera?: string
  num_matricula?: string
  jornada?: string
  total_materias?: number
  materias?: AcademicEnrollmentHistorySubject[]
}

export type AcademicEnrollmentStudentSearchResponse = {
  total?: number
  items?: AcademicEnrollmentStudent[]
  detail?: string
}

export type AcademicEnrollmentDetailResponse = {
  student?: AcademicEnrollmentStudent
  selected?: {
    cod_anio_basica?: string
    codigo_periodo?: string
  }
  cabeceras?: AcademicEnrollmentCabecera[]
  pensum?: AcademicEnrollmentSubject[]
  materias_actuales?: AcademicEnrollmentCurrentSubject[]
  historial_academico?: AcademicEnrollmentHistoryPeriod[]
  detail?: string
}

export type AcademicEnrollmentPensumResponse = {
  total?: number
  items?: AcademicEnrollmentSubject[]
  detail?: string
}

export type AcademicTeacherOption = {
  codigo_doc: string
  cedula?: string
  login?: string
  tipo_usuario?: string
  estado?: string
  descripcion?: string
  correo?: string
  correo_personal?: string
  telefono?: string
  movil?: string
  perfil?: string
  tipo_docente?: string
  unidad_academica?: string
  nivel_formacion?: string
  tercer_nivel?: string
  cuarto_nivel?: string
  total_matriculas_docente?: number
  total_carreras_docente?: number
  total_materias_docente?: number
  ultimo_periodo_docente?: number | null
  usuario_validado?: boolean
}

export type AcademicTeacherEnrollment = AcademicTeacherOption & {
  cod_anio_basica?: string
  codigo_materia?: string
  paralelo?: string
  codigo_periodo?: string
  cod_jornada?: number | null
  estado_moodle_doc?: number | null
  nombre_materia?: string
  nombre_carrera?: string
  detalle_periodo?: string
}

export type AcademicTeacherSearchResponse = {
  total?: number
  items?: AcademicTeacherOption[]
  detail?: string
}

export type AcademicTeacherEnrollmentsResponse = {
  total?: number
  items?: AcademicTeacherEnrollment[]
  detail?: string
}

export type AcademicTeacherParallelOption = {
  paralelo: string
  total_estudiantes?: number
  total_materias?: number
}

export type AcademicTeacherParallelOptionsResponse = {
  total?: number
  items?: AcademicTeacherParallelOption[]
  detail?: string
}

export type AcademicTeacherUniqueSubjectOption = {
  cod_materia: string
  nombre_materia: string
  semestre?: number | null
  niveles?: number[]
  creditos?: number | null
  codigo_materias?: string[]
  carreras?: Array<{
    cod_anio_basica: string
    nombre_carrera: string
  }>
  total_estudiantes?: number
}

export type AcademicTeacherUniqueSubjectsResponse = {
  total?: number
  items?: AcademicTeacherUniqueSubjectOption[]
  detail?: string
}

export type AcademicTeacherStudentItem = {
  codigo_estud: string
  cedula?: string
  nombre_estudiante: string
  estado_codigo?: string
  correo_personal?: string
  correo_intec?: string
  cod_anio_basica?: string
  nombre_carrera?: string
  codigo_periodo?: string
  detalle_periodo?: string
  codigo_materia?: string
  nombre_materia?: string
  paralelo?: string
  num_matricula?: string
  tipo_matricula?: string
  promedio_final?: number | null
  codigo_docente_asignado?: string
  docente_asignado?: string
}

export type AcademicTeacherStudentsResponse = {
  total?: number
  items?: AcademicTeacherStudentItem[]
  detail?: string
}

export type PortalStudentProfile = {
  codigo_estud?: string
  cedula?: string
  nombre_estudiante?: string
  correo_personal?: string
  correo_intec?: string
  estado_codigo?: string
}

export type PortalAcademicRecordItem = {
  codigo_estud?: string
  cod_anio_basica?: string
  nombre_carrera?: string
  codigo_periodo?: string
  detalle_periodo?: string
  anio_periodo?: number | null
  codigo_materia?: string
  cod_materia?: string
  nombre_materia?: string
  semestre?: number | null
  creditos?: number | null
  horas?: number | null
  orden?: number | null
  num_malla?: number | null
  paralelo?: string
  num_grupo?: number | null
  num_matricula?: string
  fecha_matricula?: string
  tipo_matricula?: string
  es_homologacion?: boolean
  esquema_calificacion?: string
  teoria_homo?: number | null
  practica_homo?: number | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  prom_p1?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  prom_p2?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  prom_p3?: number | null
  promedio?: number | null
  asistencia?: number | null
  recuperacion?: number | null
  promedio_final?: number | null
  nota_aprobar?: number | null
  aprobada?: boolean
  estado_academico?: string
  observaciones?: string
  seguimiento?: string
  cedula?: string
  nombre_estudiante?: string
  correo_personal?: string
  correo_intec?: string
  correo_intec_registro?: string
  correo_intec_validado?: boolean
}

export type PortalAcademicSummary = {
  total_materias?: number
  aprobadas?: number
  reprobadas?: number
  en_curso?: number
  creditos_aprobados?: number
  promedio_general?: number | null
  cumplimiento_academico?: number
}

export type PortalCurriculumSummary = {
  total_materias?: number
  aprobadas?: number
  faltantes?: number
  en_curso?: number
  reprobadas?: number
  creditos_totales?: number
  creditos_aprobados?: number
  porcentaje_avance?: number
}

export type PortalCurriculumItem = {
  cod_anio_basica?: string
  nombre_carrera?: string
  codigo_materia?: string
  cod_materia?: string
  nombre_materia?: string
  semestre?: number | null
  creditos?: number | null
  horas?: number | null
  orden?: number | null
  num_malla?: number | null
  unidad_organiza?: string
  estado_materia?: string
}

export type PortalAcademicGridItem = PortalCurriculumItem & {
  estado_academico?: string
  aprobada?: boolean
  faltante?: boolean
  intentos?: number
  ultimo_periodo?: string
  codigo_periodo?: string
  paralelo?: string
  tipo_matricula?: string
  es_homologacion?: boolean
  esquema_calificacion?: string
  teoria_homo?: number | null
  practica_homo?: number | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  prom_p1?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  prom_p2?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  prom_p3?: number | null
  promedio_final?: number | null
  nota_aprobar?: number | null
}

export type PortalPracticeRequirement = {
  code?: string
  label?: string
  required_hours?: number
  completed_hours?: number
  percent?: number
  status?: string
}

export type PortalStudentPayment = {
  codigo_periodo?: string
  periodo?: string
  cod_anio_basica?: string
  carrera?: string
  num_matricula?: string
  codigo_documentacion?: string
  fecha_pago?: string
  total?: number
  inscripcion?: number
  matricula?: number
  beca?: number
  descuento?: number
  saldo?: number
  cuota?: number
  cuotas?: number
  convenio_url?: string
  pago_num?: number | null
  pago_detalle?: string
  pago_fecha?: string
  pago_valor?: number
  pago_referencia?: string
  pago_banco?: string
}

export type PortalStudentRecordResponse = {
  student?: PortalStudentProfile
  summary?: PortalAcademicSummary
  curriculum_summary?: PortalCurriculumSummary
  curriculum?: PortalCurriculumItem[]
  academic_grid?: PortalAcademicGridItem[]
  practice_requirements?: PortalPracticeRequirement[]
  payments?: PortalStudentPayment[]
  total?: number
  items?: PortalAcademicRecordItem[]
  detail?: string
}

export type PortalTeacherProfile = {
  codigo_doc?: string
  cedula?: string
  docente?: string
  correo?: string
  correo_personal?: string
  telefono?: string
  movil?: string
  tipo_docente?: string
  perfil?: string
}

export type PortalTeacherProfileResponse = {
  teacher?: PortalTeacherProfile
  detail?: string
}

export type PortalTeacherCourse = {
  codigo_doc?: string
  cod_anio_basica?: string
  cod_anio_basicas?: string[]
  nombre_carrera?: string
  codigo_materia?: string
  codigo_materias?: string[]
  cod_materia?: string
  nombre_materia?: string
  codigo_periodo?: string
  codigo_periodos?: string[]
  detalle_periodo?: string
  detalle_periodos?: string
  tipo_periodo?: string
  es_homologacion?: boolean
  fecha_inicio?: string
  fecha_fin?: string
  paralelo?: string
  cod_jornada?: number | null
  jornada?: string
  semestre?: number | null
  unidad_curricular?: string
  periodo_orden?: number
  period_count?: number
  assignment_count?: number
  regular_count?: number
  homologation_count?: number
  tiene_regular?: boolean
  tiene_homologacion?: boolean
  total_estudiantes?: number
  estado_moodle_doc?: boolean
  asignaciones?: PortalTeacherCourse[]
  alcances_periodo?: PortalTeacherCourse[]
  grade_group_key?: string
}

export type PortalTeacherCoursesResponse = {
  total?: number
  items?: PortalTeacherCourse[]
  detail?: string
}

export type AdminGradeTeacher = {
  codigo_doc: string
  cedula?: string
  docente: string
  correo?: string
  estado?: string
  estado_nombre?: string
  total_asignaciones: number
  total_asignaturas: number
  total_periodos: number
}

export type AdminGradeTeachersResponse = {
  total: number
  items: AdminGradeTeacher[]
}

export type AdminGradeStudent = PortalAcademicRecordItem & {
  estado_nota?: 'APROBADO' | 'REPROBADO' | 'PENDIENTE' | string
  estado_registro?: 'COMPLETA' | 'EN_PROCESO' | 'SIN_CALIFICAR' | string
}

export type AdminGradeCourseSelection = {
  codigo_periodo: number
  cod_anio_basica: number
  codigo_materia: string
  paralelo: string
  cod_jornada?: number | null
}

export type AdminGradeStudentsResponse = {
  total: number
  items: AdminGradeStudent[]
  periodos_seleccionados?: number
  tipo_seleccion?: 'R' | 'H'
  summary: {
    completas: number
    en_proceso: number
    sin_calificar: number
    aprobados: number
    reprobados: number
  }
}

export type PortalTeacherContractClass = {
  clase_id: number
  codigo_carrera?: string
  nombre_carrera?: string
  codigo_materia?: string
  nombre_materia?: string
  codigo_periodo?: string
  paralelo?: string
  jornada?: string
  horas_planificadas?: number
  horas_ejecutadas?: number
  valor_hora?: number
  valor_total_planificado?: number
  estado?: string
  observacion?: string
}

export type PortalTeacherContract = {
  contrato_id: number
  numero_contrato?: string
  tipo_codigo?: string
  tipo_nombre?: string
  estado_codigo?: string
  estado_nombre?: string
  codigo_periodo?: string
  fecha_inicio?: string
  fecha_fin?: string
  valor_hora_clase?: number
  valor_mensual?: number | null
  valor_total_contrato?: number | null
  responsable_contratacion?: string
  observacion?: string
  ruta_contrato_firmado?: string
  modalidad_academica?: 'REGULAR' | 'HOMOLOGACION' | string
  tiene_documento_original?: boolean
  nombre_documento_original?: string
  fecha_documento_original?: string
  tiene_documento_firmado?: boolean
  nombre_documento_firmado?: string
  fecha_documento_firmado?: string
  clases: PortalTeacherContractClass[]
}

export type PortalTeacherContractsResponse = {
  teacher?: {
    docente_id?: number
    cedula?: string
    nombre?: string
    correo?: string
    tipo_docente?: string
    relacion_laboral?: string
    tiempo_dedicacion?: string
  }
  contracts: PortalTeacherContract[]
  detail?: string
}

export type PortalTeacherContractDocumentSaveResponse = {
  ok: boolean
  contrato_id: number
  message: string
}

export type PortalTeacherContractAnalysis = {
  ok: boolean
  nombre_archivo: string
  docente_coincide: boolean
  numero_contrato?: string
  cedula?: string
  codigo_materia?: string
  modalidad_academica?: 'REGULAR' | 'HOMOLOGACION'
  fecha_inicio?: string
  fecha_fin?: string
  valor_total?: number | null
  campos_detectados: string[]
  advertencias: string[]
}

export type PortalAcademicPlanningTopic = {
  tema: string
  semana: number
  horas_docencia: number
  horas_practica: number
  horas_autonomo: number
  actividad_docencia: string
  actividad_practica: string
  actividad_autonoma: string
  evaluacion: string
}

export type PortalAcademicPlanningUnit = {
  nombre: string
  resultado_aprendizaje: string
  temas: PortalAcademicPlanningTopic[]
}

export type PortalAcademicPlanningPayload = {
  document_type: 'pea' | 'silabo'
  codigo_periodos: number[]
  codigo_materia: string
  paralelo: string
  cod_anio_basica?: number | null
  cod_jornada?: number | null
  nivel: string
  unidad_curricular: string
  campo_formacion: string
  modalidad: string
  prerrequisitos: string
  correquisitos: string
  horario_clases: string
  horario_tutorias: string
  descripcion: string
  objetivo_general: string
  resultados_aprendizaje: string
  mision_intec: string
  mision_escuela: string
  mision_carrera: string
  unidades: PortalAcademicPlanningUnit[]
  estrategias_metodologicas: string
  formacion_ciudadana: string
  sostenibilidad: string
  recursos_didacticos: string
  evaluacion_tareas: number
  evaluacion_individual: number
  evaluacion_colaborativo: number
  evaluacion_acumulativa: number
  bibliografia_basica: string
  bibliografia_complementaria: string
  proyecto_tema: string
  proyecto_tiempo: string
  proyecto_objetivo: string
  proyecto_contexto: string
  version: string
  fecha_elaboracion: string
}

export type PortalTeacherStudentsResponse = {
  total?: number
  items?: PortalAcademicRecordItem[]
  codigo_materia?: string
  tipo_periodo?: 'R' | 'H'
  codigo_periodos?: number[]
  asignaciones_consultadas?: number
  detail?: string
}

export type PortalTeacherGradePayload = {
  codigo_estud: number
  cod_anio_basica: number
  codigo_periodo: number
  codigo_materia: number
  paralelo: string
  num_matricula?: number | null
  num_grupo?: number | null
  teoria_homo?: number | null
  practica_homo?: number | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  prom_p1?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  prom_p2?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  prom_p3?: number | null
  promedio?: number | null
  asistencia?: number | null
  recuperacion?: number | null
  promedio_final?: number | null
  caprueba?: string | null
}

export type PortalTeacherGradeSaveResponse = {
  ok?: boolean
  message?: string
  affected_rows?: number
  detail?: string
}

export type TeacherComplianceReportFormat = {
  title: string
  pea_heading: string
  pea_instruction: string
  syllabus_update_heading: string
  syllabus_update_default: string
  virtual_classroom_heading: string
  virtual_classroom_intro: string
  resources: string[]
  teams_heading: string
  attendance_heading: string
  grades_heading: string
  grades_instruction: string
  annexes_heading: string
  annexes_intro: string
  annexes: string[]
  closing: string
  signature_label: string
  signature_role: string
}

export type AcademicTeacherEnrollmentPayload = {
  codigo_doc: number
  cod_anio_basica: number
  codigo_materia: number
  codigo_periodo: number
  paralelo: string
  cod_jornada: number
  estado_moodle_doc: number
}

export type AcademicTeacherUniqueEnrollmentPayload = {
  codigo_doc: number
  cod_materia: string
  codigo_periodo: number
  paralelo: string
  semestre?: number | null
  cod_jornada: number
  estado_moodle_doc: number
  modo_asignacion?: 'MASIVA' | 'INDIVIDUAL'
  codigos_estudiantes?: number[]
}

export type AcademicTeacherPeriodEnrollmentPayload = {
  codigo_periodo: number
  paralelo: string
  codigos_estudiantes?: number[]
}

export type AcademicTeacherMultiEnrollmentPayload = {
  codigo_doc: number
  cod_materia: string
  periodos: AcademicTeacherPeriodEnrollmentPayload[]
  semestre?: number | null
  cod_jornada: number
  estado_moodle_doc: number
  modo_asignacion?: 'MASIVA' | 'INDIVIDUAL'
}

export type AcademicTeacherSubjectEnrollmentPayload = {
  cod_materia: string
  periodos: AcademicTeacherPeriodEnrollmentPayload[]
  semestre?: number | null
}

export type AcademicTeacherMultiSubjectEnrollmentPayload = {
  codigo_doc: number
  materias: AcademicTeacherSubjectEnrollmentPayload[]
  cod_jornada: number
  estado_moodle_doc: number
  modo_asignacion?: 'MASIVA' | 'INDIVIDUAL'
}

export type AcademicTeacherEnrollmentSaveResponse = {
  ok?: boolean
  message?: string
  action?: string
  inserted_count?: number
  updated_count?: number
  existing_count?: number
  duplicate_count?: number
  students_linked?: number
  students_requested?: number
  modo_asignacion?: 'MASIVA' | 'INDIVIDUAL'
  already_exists?: boolean
  docente?: AcademicTeacherOption
  assignments?: Array<{
    cod_anio_basica?: string
    codigo_materia?: string
    nombre_materia?: string
    nombre_carrera?: string
    codigo_periodo?: string
    paralelo?: string
    students_linked?: number
  }>
  period_results?: Array<{
    codigo_periodo?: string
    paralelo?: string
    inserted_count?: number
    updated_count?: number
    existing_count?: number
    students_linked?: number
  }>
  subject_results?: Array<{
    cod_materia?: string
    semestre?: number | null
    period_results?: Array<{
      codigo_periodo?: string
      paralelo?: string
      inserted_count?: number
      updated_count?: number
      existing_count?: number
      students_linked?: number
    }>
  }>
  criteria?:
    | AcademicTeacherEnrollmentPayload
    | AcademicTeacherUniqueEnrollmentPayload
    | AcademicTeacherMultiEnrollmentPayload
    | AcademicTeacherMultiSubjectEnrollmentPayload
  detail?: string
}

export type ScholarshipContractCandidateItem = ScholarshipBeneficiaryItem & {
  contratos_generados: number
  ultimo_contrato_id: number
  ultima_generacion: string
}

export type ScholarshipContractPeriodOption = {
  codigo_periodo: string
  periodo: string
  total: number
}

export type ScholarshipContractCandidateListResponse = {
  ok?: boolean
  items: ScholarshipContractCandidateItem[]
  total: number
  tipos_beca: string[]
  periodos: ScholarshipContractPeriodOption[]
  criteria?: {
    query?: string
    tipo_beca?: string
    codigo_periodo?: string
    estado_estudiante?: string
  }
  detail?: string
}

export type ScholarshipContractFormat = 'INSTITUCIONAL' | 'PROGRAMA'

export type ScholarshipContractProjectionItem = {
  rubro: string
  periodicidad: string
}

export type ScholarshipContractClause = {
  titulo: string
  contenido: string
}

export type ScholarshipContractTemplate = {
  titulo_contrato: string
  fecha_contrato: string | null
  ciudad: string
  resolucion: string
  rector_tratamiento: string
  rector_nombre: string
  rector_titulo: string
  correo_notificaciones: string
  programa: string
  pais: string
  institucion_educacion: string
  auspiciante: string
  nivel_estudios: string
  fecha_inicio_estudios: string | null
  fecha_fin_estudios: string | null
  fecha_inicio_financiamiento: string | null
  fecha_fin_financiamiento: string | null
  duracion_estudios: string
  duracion_financiamiento: string
  periodo_pago: string
  proyeccion: ScholarshipContractProjectionItem[]
  introduccion_institucional?: string
  clausulas_institucionales?: ScholarshipContractClause[]
  introduccion_programa?: string
  clausulas_programa?: ScholarshipContractClause[]
  titulo_tabla_datos: string
  titulo_tabla_proyeccion: string
  firma_rector_tratamiento: string
  firma_rector_nombre: string
  firma_rector_titulo: string
  firma_rector_etiqueta: string
  firma_becario_tratamiento: string
  firma_becario_etiqueta: string
  color_cabecera_tabla: string
  color_celda_etiqueta: string
  color_cabecera_interior: string
  color_celda_valor: string
  color_borde_tabla: string
}

export type ScholarshipContractHistoryItem = {
  contrato_id: number
  beca_id: number
  origen: string
  codigo_estud: string
  cedula: string
  estudiante: string
  codigo_carrera: string
  carrera: string
  codigo_periodo: string
  periodo: string
  tipo_beca: string
  porcentaje_beca: number
  valor_beca: number
  numero_contrato: string
  fecha_contrato: string
  formato_contrato: ScholarshipContractFormat
  plantilla: Partial<ScholarshipContractTemplate>
  nombre_archivo: string
  hash_sha256: string
  estado: string
  usuario_generacion: string
  fecha_generacion: string
  expediente_documento_id: number | null
  expediente_url: string
  nombre_archivo_firmado: string
  hash_firmado: string
  estado_expediente: string
  usuario_carga_expediente: string
  fecha_carga_expediente: string
}

export type ScholarshipContractHistoryResponse = {
  ok?: boolean
  items: ScholarshipContractHistoryItem[]
  total: number
  detail?: string
}

export type ScholarshipContractUploadResponse = {
  ok?: boolean
  contrato_id: number
  numero_contrato: string
  expediente_documento_id: number
  expediente_url: string
  nombre_archivo: string
  estado_expediente: string
  detail?: string
}

export type AcademicTeacherStateOption = {
  codigo: string
  nombre: string
}

export type AcademicTeacherStateItem = AcademicTeacherOption & {
  codigo_usuario?: string
  estado_nombre?: string
  fecha_ingreso_ies?: string
  relacion_laboral?: string
  tiempo_dedicacion?: string
}

export type AcademicTeacherStateCatalogResponse = {
  total?: number
  items?: AcademicTeacherStateOption[]
  detail?: string
}

export type AcademicTeacherStateSearchResponse = {
  total?: number
  items?: AcademicTeacherStateItem[]
  detail?: string
}

export type AcademicTeacherStateUpdatePayload = {
  codigo_doc?: number | null
  codigo_usuario?: number | null
  estado_codigo: string
}

export type AcademicTeacherStateUpdateResponse = {
  ok?: boolean
  message?: string
  estado?: AcademicTeacherStateOption
  docente?: AcademicTeacherStateItem
  detail?: string
}

export type AcademicEnrollmentPayload = {
  codigo_estud: number
  cod_anio_basica: number
  codigo_periodo: number
  materia_codes: number[]
  paralelo: string
  num_grupo: number
  tipo_matricula: MatriculaTipo
  control_matricula: number
  cod_jornada: number
  inscrip_valor: number
  matri_valor: number
  valor: number
  fecha_pago?: string | null
  remove_unselected: boolean
  prerequisite_exception_codes?: number[]
  prerequisite_exception_reason?: string | null
}

export type AcademicEnrollmentPreviewResponse = {
  criteria?: AcademicEnrollmentPayload
  cabecera?: {
    accion?: string
    existe?: boolean
  }
  summary?: {
    seleccionadas?: number
    insertar?: number
    actualizar?: number
    existentes?: number
    remover?: number
    bloqueadas_por_notas?: number
    bloqueadas_por_periodo?: number
    bloqueadas_por_prerrequisito?: number
    excepciones_prerrequisito?: number
  }
  items?: AcademicEnrollmentSubject[]
  detail?: string
}

export type AcademicEnrollmentSaveResponse = {
  ok?: boolean
  message?: string
  num_matricula?: string
  inserted?: number
  updated?: number
  existing_skipped?: number
  removed?: number
  blocked_by_grades?: number
  blocked_by_repetition?: number
  blocked_by_period?: number
  blocked_by_prerequisite?: number
  prerequisite_exceptions?: number
  subject_results?: Array<{
    codigo_materia?: number
    nombre_materia?: string
    num_matricula?: number
    accion?: string
    fue_matriculado?: boolean
    observacion?: string
  }>
  preview?: AcademicEnrollmentPreviewResponse
  detail?: string
}

export type AcademicBulkEnrollmentPayload = {
  cod_anio_basica: number
  source_codigo_periodo: number
  target_codigo_periodo: number
  materia_codes: number[]
  student_codes: number[]
  paralelo_filter?: string | null
  paralelo_default: string
  num_grupo_default: number
  tipo_matricula: MatriculaTipo
  control_matricula: number
  cod_jornada: number
  inscrip_valor: number
  matri_valor: number
  valor: number
  fecha_pago?: string | null
  remove_unselected: boolean
}

export type AcademicBulkEnrollmentPreviewResponse = {
  criteria?: AcademicBulkEnrollmentPayload
  summary?: {
    estudiantes_origen?: number
    materias_seleccionadas?: number
    cabeceras_crear?: number
    cabeceras_actualizar?: number
    cabeceras_existentes?: number
    insertar?: number
    actualizar?: number
    existentes?: number
    remover?: number
    bloqueadas_por_notas?: number
    bloqueadas_por_prerrequisito?: number
    bloqueadas_por_num_matricula?: number
    estudiantes_ya_matriculados?: number
    estudiantes_sin_materias_habilitadas?: number
    ya_auditadas?: number
  }
  items?: Array<{
    codigo_estud?: string
    cedula?: string
    nombre_estudiante?: string
    cod_anio_basica?: string
    carrera?: string
    paralelo?: string
    num_grupo?: number
    nivel_origen?: number | null
    nivel_destino?: number | null
    estado?: string
    motivo?: string
    cabecera?: string
    insertar?: number
    actualizar?: number
    existentes?: number
    remover?: number
    bloqueadas_por_prerrequisito?: number
    bloqueadas_por_num_matricula?: number
    ya_auditadas?: number
    materias_insertar?: Array<{
      codigo_materia?: string
      nombre_materia?: string
      semestre?: number | null
      creditos?: number | null
    }>
    materias_bloqueadas?: Array<{
      codigo_materia?: string
      materias_previas?: string[]
      motivo?: string
    }>
  }>
  detail?: string
}

export type AcademicBulkEnrollmentSaveResponse = {
  ok?: boolean
  message?: string
  audit_id?: number | null
  summary?: {
    estudiantes_procesados?: number
    inserted?: number
    updated?: number
    removed?: number
    blocked_by_grades?: number
    blocked_by_prerequisite?: number
    blocked_by_repetition?: number
    skipped_students?: number
    already_audited?: number
    already_enrolled_students?: number
    existing_skipped?: number
  }
  items?: Array<{
    codigo_estud?: string
    nombre_estudiante?: string
    paralelo?: string
    num_matricula?: string
    inserted?: number
    updated?: number
    existing_skipped?: number
    blocked_by_prerequisite?: number
    blocked_by_repetition?: number
    already_audited?: number
    already_enrolled?: boolean
  }>
  preview?: AcademicBulkEnrollmentPreviewResponse
  detail?: string
}

export type AcademicPeriodChangePayload = {
  source_codigo_periodo?: number | null
  target_codigo_periodo?: number | null
  estado_codigo?: string | null
  student_query?: string | null
  student_cedulas?: string[]
  exception_cedulas: string[]
  solo_graduados?: boolean
}

export type AcademicPeriodChangeStateOption = {
  value?: string
  label?: string
  total?: number
}

export type AcademicPeriodChangeStudentOption = {
  codigo_estud?: string
  cedula?: string
  cedula_normalizada?: string
  estudiante?: string
  estado_codigo?: string
  estado_nombre?: string
  cod_anio_basica?: string
  carrera?: string
  total_periodos_homo?: number
  total_materias_homo?: number
  primera_fecha_homo?: string
  ultima_fecha_homo?: string
}

export type AcademicPeriodChangeCatalogResponse = {
  periodos_homo?: AcademicPeriodOption[]
  periodos_regulares?: AcademicPeriodOption[]
  estados?: AcademicPeriodChangeStateOption[]
  students?: AcademicPeriodChangeStudentOption[]
  detail?: string
}

export type AcademicPeriodChangePreviewItem = {
  row_id?: number
  codigo_estud?: string
  cedula?: string
  estudiante?: string
  estado_estudiante?: string
  cod_anio_basica?: string
  carrera?: string
  codigo_materia?: string
  materia?: string
  nivel?: number | null
  source_codigo_periodo?: string
  source_periodo?: string
  target_codigo_periodo?: string
  target_periodo?: string
  bloque_regular?: number | null
  num_matricula?: string
  paralelo?: string
  num_grupo?: number | null
  tipo_actual?: string
  teoria_homo?: number | null
  practica_homo?: number | null
  p1_tareas?: number | null
  p1_proyectos?: number | null
  p1_examen?: number | null
  prom_p1?: number | null
  p2_tareas?: number | null
  p2_proyectos?: number | null
  p2_examen?: number | null
  prom_p2?: number | null
  p3_tareas?: number | null
  p3_proyectos?: number | null
  p3_examen?: number | null
  prom_p3?: number | null
  promedio?: number | null
  asistencia?: number | null
  recuperacion?: number | null
  promedio_final?: number | null
  promedio_aux?: number | null
  nota_migrada?: number | null
  mantiene_notas?: boolean
  existe_cabecera_destino?: boolean
  accion?: string
  motivo?: string
}

export type AcademicPeriodChangePreviewResponse = {
  source_period?: AcademicPeriodOption
  target_period?: AcademicPeriodOption
  target_periods?: AcademicPeriodOption[]
  auto_target?: boolean
  exception_cedulas?: string[]
  summary?: {
    registros_origen?: number
    estudiantes_origen?: number
    migrar?: number
    excepciones?: number
    duplicados_destino?: number
    sin_periodo_destino?: number
    cabeceras_referenciadas?: number
    periodos_regulares?: number
    solo_graduados?: boolean
    periodos_homo_origen?: number
    estado_codigo?: string
    student_filter?: string
  }
  students?: AcademicPeriodChangeStudentOption[]
  items?: AcademicPeriodChangePreviewItem[]
  detail?: string
}

export type AcademicPeriodChangeApplyResponse = {
  ok?: boolean
  message?: string
  summary?: {
    cabeceras_insertadas?: number
    registros_actualizados?: number
    registros_omitidos?: number
  }
  preview?: AcademicPeriodChangePreviewResponse
  detail?: string
}

export type AcademicParallelBalancePayload = {
  cod_anio_basica: number
  codigo_periodo: number
}

export type AcademicParallelBalanceResponse = {
  ok?: boolean
  message?: string
  codigo_periodo?: string
  cod_anio_basica?: string
  carrera?: string
  total_estudiantes?: number
  total_paralelos?: number
  updated_students?: number
  updated_rows?: number
  before?: AcademicEnrollmentBalanceItem[]
  source?: AcademicEnrollmentBalanceItem[]
  after?: AcademicEnrollmentBalanceItem[]
  detail?: string
}

export type ExcelSqlCrossSummary = {
  total_registro?: number
  total_moodle?: number
  total_tablas?: number
  total_sql_activos?: number
  datos_estud_activos?: number
  activos_con_cxe_o_cabecera?: number
  activos_con_carrera_no_ingles?: number
  activos_sin_cxe_cabecera?: number
  activos_excluidos_ingles_o_sin_carrera?: number
  activos_esperados?: number
  diferencia_activos_esperados?: number
  filas_principales_tablas?: number
  entidades_cruzadas?: number
  cruzadas?: number
  no_cruzadas?: number
  en_todos?: number
  balance_moodle?: number
  balance_tablas?: number
  moodle_tablas?: number
  solo_balance?: number
  solo_moodle?: number
  solo_tablas?: number
  total_con_carreraxestud?: number
  total_sin_carreraxestud?: number
  total_con_pensum?: number
  total_sin_pensum?: number
  sql_en_ambas?: number
  sql_solo_carreraxestud?: number
  sql_solo_cabecera_matricula?: number
  duplicados_codigo_sql?: number
  duplicados_cedula_sql?: number
  correos_intec_encontrados?: number
  correos_intec_no_encontrados?: number
  correos_intec_usados?: number
  correos_intec_ignorados?: number
  datos_estud_prevalece?: number
  correos_nombre_coincide?: number
  correos_personal_coincide?: number
  correos_personal_no_coincide?: number
  correos_intec_coincide?: number
  correos_intec_no_coincide?: number
  correos_periodo_coincide?: number
  correos_moodle_email_coincide?: number
  correos_moodle_email_no_coincide?: number
  datos_estud_prevalece_correo_personal?: number
  datos_estud_prevalece_correo_intec?: number
  datos_estud_prevalece_periodo?: number
  datos_estud_prevalece_estado?: number
}

export type ExcelSqlCrossRow = {
  fuente_principal?: string
  nombre_validado?: string
  clave_normalizada?: string
  estado_cruce?: string
  resultado_cruce?: string
  origen_no_cruzado?: string
  en_balance?: boolean
  en_moodle?: boolean
  en_tablas?: boolean
  balance?: {
    razon_social?: string
    nombre_comercial?: string
    identificacion?: string
    identificacion_raw?: string
    correo?: string
    balance?: string
    credito?: string
    canal?: string
    ciudad?: string
    direccion?: string
    registros?: number
  }
  moodle?: {
    nombre?: string
    email?: string
    username?: string
    idnumber?: string
    deleted?: string
    suspended?: string
    registros?: number
    duplicados_eliminados?: number
  }
  tablas?: {
    codigo_estud?: string
    cedula?: string
    nombre?: string
    correo?: string
    correointec?: string
    nombre_final?: string
    correo_final?: string
    correointec_final?: string
    estado_final?: string
    periodo_final?: string
    estado?: string
    estado_nombre?: string
    cod_anio_basica?: string
    nombre_basica?: string
    carrera_estado?: string
    carrera_abrevia?: string
    tp_escuela?: string
    codigo_periodo?: string
    fecha_pago?: string
    valor_matricula?: string
    inscrip_valor?: string
    matri_valor?: string
    beca?: string
    descuento?: string
    jornada_matricula?: string
    control_matricula?: string
    periodo_nombre?: string
    detalle_periodo?: string
    tipo_matricula_periodo?: string
    anio_periodo?: string
    estado_periodo?: string
    periodo_fecha_inicio?: string
    periodo_fecha_fin?: string
    origen_tablas_sql?: string
    en_carreraxestud?: boolean
    en_cabecera_matricula?: boolean
    periodos_vinculados?: string
    codigo_materia?: string
    num_matricula?: string
    cabecera_num_matricula?: string
    paralelo?: string
    num_grupo?: string
    promedio?: string
    asistencia?: string
    recuperacion?: string
    promedio_final?: string
    caprueba?: string
    num_creditos?: string
    fecha_matricula?: string
    num_folio?: string
    tipo_matricula_cxe?: string
    promedio_aux?: string
    control_aprueba?: string
    control_matricula_cxe?: string
    estado_moodle?: string
    cxe_num_migracion?: string
    cxe_tipo_curso_migra?: string
    cxe_num?: string
    nivel_semestre?: string
    pensum_unidad_organiza?: string
    pensum_nomb_materia?: string
    pensum_semestre?: string
    pensum_creditos?: string
    pensum_orden?: string
    pensum_num_malla?: string
    pensum_cod_materia?: string
    pensum_horas?: string
    pensum_valor_hora?: string
    pensum_valor_hora_virtual?: string
    pensum_combinar_materia?: string
    pensum_ver_reporte?: string
    pensum_secuencia_materia?: string
    pensum_tipo_materia?: string
    correos_intec_encontrado?: boolean
    correos_intec_usado?: boolean
    correos_intec_ignorado?: boolean
    datos_estud_prevalece?: boolean
    correos_codestud?: string
    correos_nombres?: string
    correos_correo_personal?: string
    correos_correo_intec?: string
    correos_fecha?: string
    correos_periodo?: string
    correos_correo_enviado?: string
    correos_estado?: string
    correos_descripcion?: string
    correos_ult_acceso_moodle?: string
    correos_num_migracion?: string
    correos_tipo_curso_migra?: string
    correos_nombre_coincide?: string
    correos_personal_coincide?: string
    correos_intec_coincide?: string
    correos_periodo_coincide?: string
    correos_estado_coincide?: string
    correos_moodle_email_coincide?: string
    registros?: number
  }
}

export type ExcelSqlCrossResponse = {
  generated_at?: string
  criteria?: {
    limit?: number
    db_limit?: number
    validacion?: string
  }
  files?: {
    registro?: string
    data_moodle?: string
  }
  sql_tables?: string[]
  summary?: ExcelSqlCrossSummary
  rows?: ExcelSqlCrossRow[]
  warnings?: string[]
  detail?: string
}

export type ExcelValidationSummary = {
  total?: number
  encontrados?: number
  parciales?: number
  no_encontrados?: number
  sin_identificador?: number
  duplicados_excel?: number
  en_datos_estud?: number
  en_correos_intec?: number
  en_preinscripcion?: number
  con_matricula?: number
}

export type ExcelValidationRow = {
  row_number?: number
  status?: 'ENCONTRADO' | 'PARCIAL' | 'NO_ENCONTRADO' | 'SIN_IDENTIFICADOR' | string
  match_field?: string
  excel?: {
    codigo?: string
    cedula?: string
    correo?: string
    correo_intec?: string
    nombre?: string
  }
  exists?: {
    datos_estud?: boolean
    correos_intec?: boolean
    preinscripcion?: boolean
    matricula?: boolean
  }
  db?: {
    codigo_estud?: string
    cedula?: string
    estudiante?: string
    estado?: string
    correo?: string
    correo_intec?: string
    tipo_beca?: string
    porcentaje_beca?: number | string | null
    periodo?: string
    periodo_codigo?: string
    carrera?: string
    carrera_codigo?: string
    materias_matriculadas?: number | string | null
  }
  raw?: Record<string, string | number | boolean | null | undefined>
}

export type ExcelValidationResponse = {
  generated_at?: string
  filename?: string
  sheet?: string
  columns?: string[]
  detected_columns?: Record<string, string | null | undefined>
  summary?: ExcelValidationSummary
  rows?: ExcelValidationRow[]
  warnings?: string[]
  detail?: string
}

export type CurriculumProposal = {
  field: string
  learning_outcomes: string
  minimum_contents: string
}

export type CurriculumPeaUnit = {
  number: number
  name: string
  learning_outcome: string
}

export type CurriculumPeaDocument = {
  index: number
  filename: string
  document_type: 'PEA' | 'SILABO' | string
  method: 'TEXTO' | 'OCR' | 'TEXTO+OCR' | 'ERROR' | string
  page_count: number
  course_code: string
  subject_name: string
  career_name: string
  field: string
  learning_outcomes: string
  minimum_contents: string
  units: CurriculumPeaUnit[]
  confidence: number
  warnings: string[]
}

export type CurriculumAnalysisRow = {
  row_number: number
  subject_name: string
  period: string
  curricular_unit: string
  current: CurriculumProposal
  document_index: number | null
  document_indices: number[]
  source_file: string
  source_files: string[]
  match_score: number
  match_type: string
  status: string
  apply_recommended: boolean
  proposal: CurriculumProposal
  warnings: string[]
}

export type CurriculumAnalysisResponse = {
  workbook: {
    filename: string
    career_name: string
    source_sheet: string
    target_sheet: string
    target_exists: boolean
    target_will_be_created: boolean
    header_row: number
    subject_count: number
    period_count: number
    warnings: string[]
  }
  ocr_available: boolean
  documents: CurriculumPeaDocument[]
  rows: CurriculumAnalysisRow[]
  unmatched_documents: CurriculumPeaDocument[]
  summary: {
    subjects: number
    documents: number
    ready: number
    requires_review: number
    without_pea: number
    existing_data: number
    unmatched_documents: number
  }
}

export type CurriculumGenerateUpdate = {
  row_number: number
  subject_name: string
  period: string
  apply: boolean
  status: string
  source_file: string
  proposal: CurriculumProposal
}

export type AgeRangeCatalogResponse = {
  becas?: string[]
  rangos?: Array<{ value: string, label: string }>
  estados?: Array<{ value: string, label: string }>
  detail?: string
}

export type AgeRangeRow = {
  estudiante_codigo?: string
  cedula?: string
  estudiante?: string
  correo_personal?: string | null
  correo_intec?: string | null
  telefono?: string | null
  celular?: string | null
  estado_codigo?: string
  estado?: string
  fecha_nacimiento?: string | null
  fecha_calculo?: string | null
  edad?: number | null
  rango_edad?: string
  tipo_beca?: string
  porcentaje_beca?: number | string | null
  periodo_codigo?: string
  periodo?: string
  carrera_codigo?: string
  carrera?: string
}

export type AgeRangeBucket = {
  rango_edad: string
  orden?: number
  total: number
  con_beca: number
  sin_beca: number
  porcentaje_beca_total?: number
  promedio_beca?: number
}

export type AgeRangeSummary = {
  total?: number
  edad_calculada?: number
  sin_fecha?: number
  con_beca?: number
  sin_beca?: number
  rangos?: AgeRangeBucket[]
}

export type AgeRangeFilters = {
  periodo?: string
  carrera?: string
  estado?: string
  tipo_beca?: string
  buscar?: string
  rango_edad?: string
  limit?: number
}

export type AgeRangeResponse = {
  generated_at?: string
  fecha_calculo?: string
  columns?: string[]
  rows?: AgeRangeRow[]
  ranges?: AgeRangeBucket[]
  summary?: AgeRangeSummary
  criteria?: Record<string, string | number | null | undefined>
  detail?: string
}

export type SenescytStudentMissingDetail = {
  estudiante: string
  numero_identificacion: string
  campos_llenos: number
  campos_pendientes: number
  campos_totales: number
  porcentaje_lleno: number
  campos_faltantes: string[]
}

export type SenescytCareerSummary = {
  nombre_carrera: string
  total_estudiantes: number
  campos_llenos: number
  campos_totales: number
  campos_pendientes?: number
  estudiantes_con_pendientes?: number
  porcentaje_lleno: number
  students_missing?: SenescytStudentMissingDetail[]
}

export type SenescytMissingField = {
  campo: string
  llenos: number
  pendientes: number
  porcentaje_lleno: number
}

export type SenescytStudentReportResponse = {
  generated_at?: string
  summary?: {
    total_reporte?: number
    total_activos_sistema?: number
    total_activos_datos_estud?: number
    coincide_activos?: boolean
    total_carreras?: number
    total_columnas?: number
    campos_llenos?: number
    campos_totales?: number
    porcentaje_lleno?: number
  }
  careers?: SenescytCareerSummary[]
  missing_fields?: SenescytMissingField[]
  warnings?: string[]
  criteria?: Record<string, string>
  detail?: string
}

export type SenescytStudentDataSearchItem = {
  codigo_estud: string
  estudiante: string
  numero_identificacion: string
  nombre_carrera: string
  campos_llenos: number
  campos_pendientes: number
  campos_totales: number
  porcentaje_lleno: number
  campos_faltantes: string[]
}

export type SenescytStudentDataSearchResponse = {
  rows?: SenescytStudentDataSearchItem[]
  total?: number
  limit?: number
  query?: string
  detail?: string
}

export type SenescytStudentDataDetailResponse = {
  ok?: boolean
  message?: string
  student?: SenescytStudentDataSearchItem
  fields?: Record<string, string | number | null>
  report_columns?: string[]
  datos_estud_fields?: Record<string, string | number | null>
  datos_estud_columns?: string[]
  updated_fields?: string[]
  affected_rows?: number
  detail?: string
}

export type LegacyDataUpdateTarget = 'estudiantes' | 'docentes'

export type LegacyDataUpdatePerson = {
  id: string
  codigo: string
  nombre: string
  cedula: string
  tipo: 'estudiante' | 'docente'
  carrera?: string | null
  correo?: string | null
  campos_llenos: number
  campos_pendientes: number
  campos_totales: number
  porcentaje_lleno: number
  campos_faltantes: string[]
}

export type LegacyDataUpdateSearchResponse = {
  rows?: LegacyDataUpdatePerson[]
  total?: number
  limit?: number
  query?: string
  target?: LegacyDataUpdateTarget
  detail?: string
}

export type LegacyDataUpdateDetailResponse = {
  ok?: boolean
  message?: string
  person?: LegacyDataUpdatePerson
  fields?: Record<string, string | number | null>
  columns?: string[]
  catalogs?: Record<string, Array<{ value: string; label: string }>>
  target?: LegacyDataUpdateTarget
  updated_fields?: string[]
  affected_rows?: number
  detail?: string
}

export type InstitutionalEmailStudent = {
  codigo_estud: number
  cedula: string
  estudiante: string
  carrera?: string | null
  estado?: string | null
  correo_personal?: string | null
  correo_intec_datos?: string | null
  correo_intec_registro?: string | null
  correo_intec?: string | null
  tiene_registro: boolean
  password_configurada: boolean
  sincronizado: boolean
}

export type InstitutionalEmailStudentsResponse = {
  rows: InstitutionalEmailStudent[]
  total: number
  page: number
  page_size: number
  cedula: string
}

export type InstitutionalEmailAnalysisRow = {
  row: number
  cedula: string
  codigo_estud?: number | null
  estudiante?: string
  correo_actual?: string | null
  correo_nuevo: string
  password_informada: boolean
  estado: 'VALIDO' | 'ERROR'
  detalle: string
}

export type InstitutionalEmailAnalysisResponse = {
  rows: InstitutionalEmailAnalysisRow[]
  summary: {
    total: number
    validos: number
    errores: number
  }
}

export type InstitutionalEmailApplyResponse = {
  ok: boolean
  actualizados: number
  message: string
}

export type InstitutionalEmailUpdateResponse = {
  ok: boolean
  message: string
  cedula: string
  correo_intec: string
}

export type SenescytTarget = 'estudiantes' | 'docentes'
export type SenescytExportMode = 'completo' | 'faltantes'

export type SenescytCatalogCareer = {
  codigo_carrera?: string
  nombre_carrera: string
}

export type SenescytCatalogResponse = {
  careers?: SenescytCatalogCareer[]
  targets?: SenescytTarget[]
  export_modes?: SenescytExportMode[]
  detail?: string
}

export type SenescytAuditSummary = {
  total_registros?: number
  total_carreras?: number
  total_columnas?: number
  campos_llenos?: number
  campos_totales?: number
  campos_pendientes?: number
  porcentaje_lleno?: number
  registros_con_pendientes?: number
}

export type SenescytAuditCareer = {
  nombre_carrera: string
  total_registros: number
  campos_llenos: number
  campos_totales: number
  campos_pendientes: number
  registros_con_pendientes: number
  porcentaje_lleno: number
}

export type SenescytAuditRow = {
  codigo?: string
  identificacion?: string
  nombre?: string
  nombre_carrera?: string
  correo?: string
  telefono?: string
  documento?: {
    tipo_actual_label?: string
    valido?: boolean
  }
  campos_llenos?: number
  campos_pendientes?: number
  campos_totales?: number
  porcentaje_lleno?: number
  campos_faltantes?: string[]
  fields?: Record<string, string | number | null>
}

export type SenescytAuditField = {
  campo: string
  llenos: number
  pendientes: number
  porcentaje_lleno: number
}

export type SenescytAuditResponse = {
  generated_at?: string
  target?: SenescytTarget
  career_filter?: string[] | null
  summary?: SenescytAuditSummary
  careers?: SenescytAuditCareer[]
  rows?: SenescytAuditRow[]
  missing_fields?: SenescytAuditField[]
  report_columns?: string[]
  detail?: string
}

export type TeamsActionResponse = {
  ok?: boolean
  message?: string
  detail?: string
  team_id?: string
  user_id?: string
  teacher_count?: number
  course_count?: number
  selected_group_count?: number
  selected_requested_count?: number
  selected_found_count?: number
  processed_count?: number
  failed_count?: number
  enrolled_count?: number
}

export type TeamMassEnrollmentRequestPayload = {
  team_id: string
  tipo_matricula?: MatriculaTipo | 'ALL' | null
  estado_codigo?: 'A' | 'P' | 'R' | 'G' | '' | null
  anio_periodo?: number | null
  punto_matricula?: 'PRIMERA' | 'ULTIMA' | 'BOTH'
  codigo_periodo?: string | null
  codigo_estud?: string | null
  selected_student_codes?: string[]
  materia_query?: string | null
  paralelo?: string | null
  limit?: number
}

export type TeamMassEnrollmentCandidate = {
  codigo_estud: string
  cedula?: string
  nombre_estudiante?: string
  nombre_carrera?: string
  correo_intec?: string
  correo_personal?: string
  punto_matricula?: string
  tipo_matricula?: string
  estado_codigo?: string
  estado_nombre?: string
  anio_periodo?: number | null
  codigo_periodo?: string
  detalle_periodo?: string
  graph_user_id?: string | null
  graph_display_name?: string | null
  graph_mail?: string | null
  graph_user_principal_name?: string | null
  status?: string
  status_label?: string
  error?: string
}

export type TeamEnrollmentGroup = {
  cod_anio_basica?: string
  nombre_carrera?: string | null
  codigo_periodo?: string
  anio_periodo?: number | null
  detalle_periodo?: string | null
  periodo_nombre?: string | null
  paralelo?: string
  paralelo_nombre?: string | null
  materia_base_key?: string
  codigo_materia_referencia?: string
  nombre_materia?: string | null
  total_estudiantes?: number
  con_correo_intec?: number
  sin_correo_intec?: number
  suggested_team_name?: string
}

export type TeamEnrollmentStudent = {
  codigo_estud: string
  nombre_estudiante?: string | null
  correo_intec?: string | null
  correo_personal?: string | null
  estado_correo?: string | null
  descripcion_correo?: string | null
  tipo_matricula?: string | null
  cod_anio_basica?: string
  nombre_carrera?: string | null
  codigo_periodo?: string
  anio_periodo?: number | null
  detalle_periodo?: string | null
  periodo_nombre?: string | null
  paralelo?: string
  paralelo_nombre?: string | null
  materia_base_key?: string
  codigo_materia?: string
  nombre_materia?: string | null
  num_grupo?: string
}

export type TeamIndividualEnrollmentStudent = TeamEnrollmentStudent & {
  total_materias?: number
}

export type TeamEnrollmentPeriodOption = {
  codigo_periodo: string
  anio_periodo?: number | null
  detalle_periodo?: string | null
  periodo_nombre?: string | null
}

export type TeamEnrollmentMateriaOption = {
  materia_base_key: string
  codigo_materia_referencia?: string
  nombre_materia?: string | null
  total_grupos?: number
  total_estudiantes?: number
}

export type TeamEnrollmentParallelOption = {
  paralelo: string
  paralelo_nombre?: string | null
}

export type TeamEnrollmentFilterOptionsPayload = {
  codigo_periodos?: string[]
  cod_anio_basica?: string | null
  paralelo?: string | null
  paralelos?: string[]
  anio_periodo?: number | null
}

export type TeamEnrollmentGroupSearchPayload = {
  codigo_periodo?: string | null
  codigo_periodos?: string[]
  cod_anio_basica?: string | null
  paralelo?: string | null
  paralelos?: string[]
  materia_query?: string | null
  materia_base_keys?: string[]
  tipo_matricula?: MatriculaTipo | 'ALL' | null
  anio_periodo?: number | null
  limit?: number
}

export type TeamEnrollmentGroupIdentity = {
  codigo_periodo: string
  cod_anio_basica: string
  paralelo: string
  materia_base_key: string
  anio_periodo?: number | null
}

export type TeamEnrollmentGroupStudentsPayload = Partial<TeamEnrollmentGroupIdentity> & {
  group_items?: TeamEnrollmentGroupIdentity[]
}

export type TeamEnrollmentSelectionPayload = Partial<TeamEnrollmentGroupIdentity> & {
  group_items?: TeamEnrollmentGroupIdentity[]
  team_id: string
  selected_student_codes: string[]
}

export type TeamManualEmailEnrollmentPayload = {
  team_id: string
  emails: string[]
}

export type TeamIndividualStudentSearchPayload = {
  codigo_periodo: string
  query: string
  materia_query?: string | null
  paralelo?: string | null
  anio_periodo?: number | null
  limit?: number
}

export type TeamIndividualEnrollmentPayload = {
  team_id: string
  codigo_periodo: string
  codigo_estud?: string | null
  selected_student_codes?: string[]
  materia_query?: string | null
  paralelo?: string | null
  anio_periodo?: number | null
}

export type TeamCreateAndEnrollPayload = {
  display_name: string
  courses: string[]
  teacher_user_ids: string[]
  visibility?: string
  description?: string
  selected_student_codes?: string[]
  group_items?: TeamEnrollmentGroupIdentity[]
  codigo_periodo?: string | null
  cod_anio_basica?: string | null
  paralelo?: string | null
  materia_base_key?: string | null
  anio_periodo?: number | null
}

export type TeamEnrollmentGroupSearchResponse = {
  criteria?: TeamEnrollmentGroupSearchPayload
  total?: number
  items?: TeamEnrollmentGroup[]
  detail?: string
}

export type TeamEnrollmentFilterOptionsResponse = {
  criteria?: TeamEnrollmentFilterOptionsPayload
  max_periods?: number
  periodos?: TeamEnrollmentPeriodOption[]
  paralelos?: TeamEnrollmentParallelOption[]
  materias?: TeamEnrollmentMateriaOption[]
  detail?: string
}

export type TeamEnrollmentGroupStudentsResponse = {
  group?: TeamEnrollmentGroup
  suggested_team_name?: string
  selected_group_count?: number
  total?: number
  items?: TeamEnrollmentStudent[]
  detail?: string
}

export type TeamIndividualStudentSearchResponse = {
  criteria?: TeamIndividualStudentSearchPayload
  total?: number
  items?: TeamIndividualEnrollmentStudent[]
  message?: string
  detail?: string
}

export type TeamMassEnrollmentResponse = {
  ok?: boolean
  message?: string
  detail?: string
  team_id?: string
  team_display_name?: string
  criteria?: TeamMassEnrollmentRequestPayload
  total_candidates?: number
  ready_count?: number
  already_in_team_count?: number
  not_found_count?: number
  invalid_email_count?: number
  error_count?: number
  enrolled_count?: number
  processed_count?: number
  failed_count?: number
  group?: TeamEnrollmentGroup
  suggested_team_name?: string
  selected_group_count?: number
  selected_requested_count?: number
  selected_found_count?: number
  source?: string
  manual_email_count?: number
  items?: TeamMassEnrollmentCandidate[]
}

export type MoodleTeamsParticipantRole = 'administrator' | 'teacher' | 'student' | 'ignored'

export type MoodleTeamsParticipant = {
  moodle_user_id: number
  full_name: string
  email: string
  moodle_username: string
  moodle_roles: string[]
  role: MoodleTeamsParticipantRole
  fixed_administrator: boolean
  graph_user_id?: string | null
  graph_display_name?: string | null
  graph_mail?: string | null
  graph_user_principal_name?: string | null
  graph_account_enabled?: boolean | null
  graph_user_type?: string | null
  status: string
  status_label: string
  reason?: string
  error?: string
}

export type MoodleTeamsPreviewResponse = {
  course: {
    id: number
    fullname: string
    shortname: string
    idnumber: string
  }
  team: {
    id?: string | null
    display_name: string
    exists: boolean
    web_url?: string | null
    creation_action: 'create' | 'synchronize'
    template: 'educationClass'
  }
  owners: MoodleTeamsParticipant[]
  students: MoodleTeamsParticipant[]
  ignored: MoodleTeamsParticipant[]
  summary: {
    moodle_user_count: number
    moodle_teacher_count: number
    owner_count: number
    student_count: number
    student_ready_count: number
    student_existing_count: number
    student_unresolved_count: number
    ignored_count: number
    selected_student_count?: number
    selected_ready_count?: number
    selected_existing_count?: number
  }
  fixed_administrator: string
  warnings: string[]
  blocking_reasons: string[]
  can_execute: boolean
}

export type MoodleTeamsEnrollmentResponse = {
  ok: boolean
  message: string
  course: MoodleTeamsPreviewResponse['course']
  team: MoodleTeamsPreviewResponse['team'] & {
    already_existed?: boolean
    created_new?: boolean
  }
  owners: MoodleTeamsParticipant[]
  creation?: TeamsActionResponse & Record<string, unknown>
  enrollment?: TeamMassEnrollmentResponse
  warnings: string[]
}
