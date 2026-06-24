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
  | 'DOCENTE'
  | 'ESTUDIANTE'

export type UserSession = {
  login: string
  nombres?: string
  email?: string
  id_usuario?: number
  rol: Role
  codigo_estud?: number
  codigo_doc?: number
  cedula?: string
}

export type Page =
  | 'dashboard'
  | 'teams'
  | 'teams-matricula'
  | 'matricula'
  | 'matricula-acad'
  | 'matricula-docente'
  | 'estado-docente'
  | 'senescyt-estudiantes'
  | 'actualizar-datos-estudiante'
  | 'preinscripcion'
  | 'reporteria-carreras'
  | 'reporteria-integral'
  | 'reportes-individuales'
  | 'gestion-sisacademico'
  | 'periodo-academico'
  | 'periodo-matriculados'
  | 'ingreso-ventas'
  | 'cruce-datos'
  | 'validar-excel'
  | 'rango-edades'
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
  | 'portal-docente'
export type PortalStudentSection = 'dashboard' | 'curricular' | 'academica' | 'notas'
export type PreinscriptionStage = 'registro' | 'inscritos' | 'seguimiento' | 'cabecera' | 'materias' | 'documentos'
export type MatriculaTipo = 'R' | 'H' | 'E'

export type TeacherEvaluationFlow = 'student' | 'auto_estudiante' | 'auto_docente' | 'par_docente' | 'academico_docente'

export type TeacherEvaluationQuestion = {
  id_pregunta: number
  id_dimension?: number | null
  no_pregunta: number
  tipo_preg: number
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

export type TeacherEvaluationAdminPendingResponse = {
  periodo: string
  periodo_detalle: string
  flow: TeacherEvaluationFlow | 'all'
  summary: TeacherEvaluationAdminSummaryItem[]
  items: TeacherEvaluationAdminPendingItem[]
  total: number
}

export type TeacherEvaluationGradedTeacher = {
  codigo_doc: string
  docente: string
  cedula_doc?: string | null
  total_registros: number
  promedio_final: number
}

export type TeacherEvaluationGradedTeachersResponse = {
  periodo: string
  periodo_detalle: string
  items: TeacherEvaluationGradedTeacher[]
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
  evaluacion_docente: TeacherEvaluationStudentProgressMetric
  autoevaluacion_estudiante: TeacherEvaluationStudentProgressMetric
  avance_total_percent: number
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
  trend?: DashboardMatriculaTrendItem[]
  states?: DashboardMatriculaStateItem[]
  active_by_type?: DashboardMatriculaActiveTypeItem[]
  active_regular_students?: number
  active_homologation_students?: number
  active_regular_homologation_students?: number
  total_estudiantes?: number
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
  lastModifiedDateTime?: string
  size?: number
  timeZone?: string
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
}

export type MatriculaSummaryResponse = {
  items?: MatriculaSummaryItem[]
  totals_by_tipo?: Record<string, number>
  totals_by_estado?: Record<string, number>
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

export type LegacyReportResponse = {
  generated_at?: string
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

export type CredentialCourse = {
  cod_curso: string
  curso: string
  estado?: string | null
  fecha_inicio?: string | null
  fecha_final?: string | null
  source?: string | null
  codigo_materia?: string | null
  cod_materia?: string | null
  carrera?: string | null
  semestre?: string | null
}

export type CredentialCatalogResponse = {
  courses: CredentialCourse[]
  default_message: string
  default_link: string
  graph_user_domain?: string | null
  graph_mail_sender?: string | null
  detail?: string
}

export type CredentialRow = {
  id?: number
  cod_curso?: string
  curso?: string
  primer_nombre: string
  segundo_nombre?: string
  primer_apellido: string
  segundo_apellido?: string
  cedula: string
  correo_electronico: string
  usuario_generado?: string
  clave_temporal?: string
  graph_user_id?: string
  graph_user_principal_name?: string
  graph_mail_sender?: string
  estado_graph?: string
  error_graph?: string
  correo_enviado?: boolean
  estado_envio?: string
  error_envio?: string
  fecha_creacion?: string | null
  fecha_graph?: string | null
  fecha_envio?: string | null
}

export type CredentialBulkPayload = {
  cod_curso: string
  curso: string
  mensaje: string
  link: string
  enviar_correo: boolean
  usuarios: CredentialRow[]
}

export type CredentialListResponse = {
  rows: CredentialRow[]
  count: number
  detail?: string
}

export type CredentialBulkResponse = {
  ok?: boolean
  created?: number
  updated?: number
  graph_created?: number
  graph_updated?: number
  graph_failed?: number
  sent?: number
  failed?: number
  rows?: CredentialRow[]
  message?: string
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
  cuota1?: number | null
  beca?: number | null
  descuento?: number | null
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
}

export type PreinscriptionCreateResponse = {
  ok?: boolean
  message?: string
  item?: PreinscriptionItem
  asesor?: {
    codigo?: string
    usuario?: string
  }
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
  control_matricula: number
  num_cuotas: number
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

export type AcademicEnrollmentCatalogResponse = {
  carreras?: AcademicCareerOption[]
  periodos?: AcademicPeriodOption[]
  jornadas?: PreinscriptionProcessOption[]
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

export type PortalStudentRecordResponse = {
  student?: PortalStudentProfile
  summary?: PortalAcademicSummary
  curriculum_summary?: PortalCurriculumSummary
  curriculum?: PortalCurriculumItem[]
  academic_grid?: PortalAcademicGridItem[]
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
  tipo_docente?: string
  perfil?: string
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
  paralelo?: string
  cod_jornada?: number | null
  jornada?: string
  period_count?: number
  total_estudiantes?: number
  estado_moodle_doc?: boolean
}

export type PortalTeacherCoursesResponse = {
  total?: number
  items?: PortalTeacherCourse[]
  detail?: string
}

export type PortalTeacherStudentsResponse = {
  total?: number
  items?: PortalAcademicRecordItem[]
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
  already_exists?: boolean
  docente?: AcademicTeacherOption
  assignments?: Array<{
    cod_anio_basica?: string
    codigo_materia?: string
    nombre_materia?: string
    nombre_carrera?: string
  }>
  criteria?: AcademicTeacherEnrollmentPayload | AcademicTeacherUniqueEnrollmentPayload
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
  updated_fields?: string[]
  affected_rows?: number
  detail?: string
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
