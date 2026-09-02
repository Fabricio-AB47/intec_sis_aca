import { lazy, Suspense, useState, type ComponentType, type ReactNode } from 'react'

import './App.css'
import { StudentLayout } from './components/StudentLayout'
import { LoginView } from './features/auth/LoginView'
import { ProfileSelectionView } from './features/auth/ProfileSelectionView'
import { SessionStatusView } from './features/auth/SessionStatusView'
import { TeacherEvaluationView } from './features/evaluacion/TeacherEvaluationView'
import { useReporteriaApp } from './hooks/useReporteriaApp'
import { screenPermissionAllowsCode, screenPermissionAllowsPage, screenPermissionForView } from './lib/screenAccess'
import type { AcademicEnrollmentMode, MoodleSection, PreinscriptionStage } from './types/app'

const lazyView = <T,>(loader: () => Promise<T>, name: keyof T) =>
  lazy(async () => ({ default: (await loader())[name] as ComponentType<Record<string, unknown>> }))

const AsignacionPantallasView = lazyView(() => import('./features/admin/AsignacionPantallasView'), 'AsignacionPantallasView')
const NotasPorAsignaturaView = lazyView(() => import('./features/admin/NotasPorAsignaturaView'), 'NotasPorAsignaturaView')
const CarnetInstitucionalView = lazyView(() => import('./features/admin/CarnetInstitucionalView'), 'CarnetInstitucionalView')
const CredentialGeneratorView = lazyView(() => import('./features/admin/CredentialGeneratorView'), 'CredentialGeneratorView')
const MassEmailView = lazyView(() => import('./features/admin/MassEmailView'), 'MassEmailView')
const TeacherComplianceFormatView = lazyView(() => import('./features/admin/TeacherComplianceFormatView'), 'TeacherComplianceFormatView')
const CruceDatosView = lazyView(() => import('./features/cruce/CruceDatosView'), 'CruceDatosView')
const ExcelValidationView = lazyView(() => import('./features/cruce/ExcelValidationView'), 'ExcelValidationView')
const DashboardView = lazyView(() => import('./features/dashboard/DashboardView'), 'DashboardView')
const SistemaAcademicoView = lazyView(() => import('./features/academico/SistemaAcademicoView'), 'SistemaAcademicoView')
const TeacherEvaluationAdminView = lazyView(() => import('./features/evaluacion/TeacherEvaluationAdminView'), 'TeacherEvaluationAdminView')
const ExpedientesDocumentalesView = lazyView(() => import('./features/expedientes/ExpedientesDocumentalesView'), 'ExpedientesDocumentalesView')
const InglesView = lazyView(() => import('./features/ingles/InglesView'), 'InglesView')
const ActualizarDatosEstudianteView = lazyView(() => import('./features/matricula/ActualizarDatosEstudianteView'), 'ActualizarDatosEstudianteView')
const ActualizarCorreoIntecView = lazyView(() => import('./features/matricula/ActualizarCorreoIntecView'), 'ActualizarCorreoIntecView')
const CertificateRenamerView = lazyView(() => import('./features/matricula/CertificateRenamerView'), 'CertificateRenamerView')
const CertificadosView = lazyView(() => import('./features/matricula/CertificadosView'), 'CertificadosView')
const EstadoDocenteView = lazyView(() => import('./features/matricula/EstadoDocenteView'), 'EstadoDocenteView')
const GestionSisAcademicoView = lazyView(() => import('./features/matricula/GestionSisAcademicoView'), 'GestionSisAcademicoView')
const FechaGradoView = lazyView(() => import('./features/matricula/FechaGradoView'), 'FechaGradoView')
const IngresoVentasView = lazyView(() => import('./features/matricula/IngresoVentasView'), 'IngresoVentasView')
const MatriculaAcadView = lazyView(() => import('./features/matricula/MatriculaAcadView'), 'MatriculaAcadView')
const MatriculaDocenteView = lazyView(() => import('./features/matricula/MatriculaDocenteView'), 'MatriculaDocenteView')
const MatriculaExcelCertificadosView = lazyView(() => import('./features/matricula/MatriculaExcelCertificadosView'), 'MatriculaExcelCertificadosView')
const MatriculaView = lazyView(() => import('./features/matricula/MatriculaView'), 'MatriculaView')
const PeriodoAcademicoView = lazyView(() => import('./features/matricula/PeriodoAcademicoView'), 'PeriodoAcademicoView')
const PeriodoMatriculadosView = lazyView(() => import('./features/matricula/PeriodoMatriculadosView'), 'PeriodoMatriculadosView')
const PreinscripcionView = lazyView(() => import('./features/matricula/PreinscripcionView'), 'PreinscripcionView')
const RangoEdadesView = lazyView(() => import('./features/matricula/RangoEdadesView'), 'RangoEdadesView')
const ReporteriaCarrerasView = lazyView(() => import('./features/matricula/ReporteriaCarrerasView'), 'ReporteriaCarrerasView')
const ReporteriaIntegralView = lazyView(() => import('./features/matricula/ReporteriaIntegralView'), 'ReporteriaIntegralView')
const ReportesIndividualesView = lazyView(() => import('./features/matricula/ReportesIndividualesView'), 'ReportesIndividualesView')
const SenescytEstudiantesView = lazyView(() => import('./features/matricula/SenescytEstudiantesView'), 'SenescytEstudiantesView')
const TitulosRegistradosView = lazyView(() => import('./features/matricula/TitulosRegistradosView'), 'TitulosRegistradosView')
const TitulacionView = lazyView(() => import('./features/matricula/TitulacionView'), 'TitulacionView')
const PortalDocenteView = lazyView(() => import('./features/portal/PortalDocenteView'), 'PortalDocenteView')
const PortalDocentePlanificacionView = lazyView(() => import('./features/portal/PortalDocentePlanificacionView'), 'PortalDocentePlanificacionView')
const PortalDocenteContratosView = lazyView(() => import('./features/portal/PortalDocenteContratosView'), 'PortalDocenteContratosView')
const PortalEstudianteView = lazyView(() => import('./features/portal/PortalEstudianteView'), 'PortalEstudianteView')
const PracticasInstitucionalesView = lazyView(() => import('./features/practicas/PracticasInstitucionalesView'), 'PracticasInstitucionalesView')
const CareerChangeRequestsView = lazyView(
  () => import('./features/solicitudes/CareerChangeRequestsView'),
  'CareerChangeRequestsView',
)
const ModalityChangeRequestsView = lazyView(
  () => import('./features/solicitudes/ModalityChangeRequestsView'),
  'ModalityChangeRequestsView',
)
const TeamsEnrollmentView = lazyView(() => import('./features/teams/TeamsEnrollmentView'), 'TeamsEnrollmentView')
const TeamsView = lazyView(() => import('./features/teams/TeamsView'), 'TeamsView')
const HistoricoIntegracionesView = lazyView(
  () => import('./features/integraciones/HistoricoIntegracionesView'),
  'HistoricoIntegracionesView',
)
const MoodleTeamsEnrollmentView = lazyView(
  () => import('./features/integraciones/MoodleTeamsEnrollmentView'),
  'MoodleTeamsEnrollmentView',
)
const InformeCumplimientoView = lazyView(
  () => import('./features/admin/InformeCumplimientoView'),
  'InformeCumplimientoView',
)
const MoodleView = lazyView(() => import('./features/moodle/MoodleView'), 'MoodleView')

const academicEnrollmentModes: AcademicEnrollmentMode[] = ['individual', 'masiva', 'prerrequisitos']
const moodleSections: MoodleSection[] = [
  'alerts',
  'courses',
  'evaluation-dates',
  'resources',
  'grades',
  'status',
  'users',
]
const preinscriptionStages: PreinscriptionStage[] = [
  'registro',
  'inscritos',
  'becas',
  'gestion-becas',
  'becados',
  'contratos-becas',
  'seguimiento',
  'cabecera',
  'materias',
  'documentos',
]

function assignedChildren<T extends string>(
  permissions: string[] | null,
  parent: string,
  options: readonly T[],
): T[] {
  const assigned = new Set(permissions || [])
  return options.filter((option) => assigned.has(`${parent}/${option}`))
}

function assignedDynamicChildren(permissions: string[] | null, parent: string): string[] {
  const prefix = `${parent}/`
  return (permissions || [])
    .filter((permission) => permission.startsWith(prefix))
    .map((permission) => permission.slice(prefix.length))
    .filter(Boolean)
}

function isAdministratorRole(role?: string): boolean {
  const normalized = role
    ?.trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') || ''

  return normalized === '1'
    || normalized === 'ADMIN'
    || normalized === 'ADMINISTRACION'
    || normalized.includes('ADMINISTRADOR')
}

function App() {
  const app = useReporteriaApp()
  const [publicTeacherEvaluation, setPublicTeacherEvaluation] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const requestedPage = params.get('open_page') || params.get('public')
    return requestedPage === 'evaluacion-docente' || window.location.pathname.includes('evaluacion-docente')
  })
  const allowedAcademicEnrollmentModes = assignedChildren(
    app.screenAccessPages,
    'matricula-acad',
    academicEnrollmentModes,
  )
  const allowedPreinscriptionStages = assignedChildren(
    app.screenAccessPages,
    'preinscripcion',
    preinscriptionStages,
  )
  const allowedMoodleSections = assignedChildren(
    app.screenAccessPages,
    'moodle',
    moodleSections,
  )
  const allowedSisAcademicoSections = assignedDynamicChildren(app.screenAccessPages, 'gestion-sisacademico')
  const canOpenMoodleUsers = isAdministratorRole(app.session?.rol)
    || screenPermissionAllowsCode(app.screenAccessPages, 'moodle/users')

  if (app.bootstrapping) {
    return <SessionStatusView message="Validando sesión activa..." />
  }

  if (!app.session && publicTeacherEvaluation) {
    return (
      <TeacherEvaluationView
        displayName="Formulario público"
        publicMode
        onBackToLogin={() => setPublicTeacherEvaluation(false)}
      />
    )
  }

  if (app.session && app.profileSelectionPending) {
    return (
      <ProfileSelectionView
        session={app.session}
        loading={app.profileSelectionLoading}
        error={app.profileSelectionError}
        onSelect={(role) => {
          void app.selectAccessProfile(role)
        }}
        onLogout={() => {
          void app.logout()
        }}
      />
    )
  }

  if (app.session && (app.screenAccessLoading || app.screenAccessPages === null)) {
    return <SessionStatusView message="Cargando navegación autorizada..." />
  }

  if (app.session && app.screenAccessPages?.length === 0) {
    return (
      <SessionStatusView
        message="No se pudo habilitar la navegación"
        detail={app.screenAccessError || 'El tipo de usuario no tiene pantallas activas asignadas.'}
        onRetry={app.refreshScreenAccess}
        onLogout={() => {
          void app.logout()
        }}
      />
    )
  }

  if (app.session) {
    let pageContent: ReactNode
    const activePermission = screenPermissionForView(app.activePage, {
      matriculaAcadMode: app.matriculaAcadMode,
      moodleSection: app.activeMoodleSection,
      preinscriptionStage: app.preinscriptionActiveStage,
      sisAcademicoSection: app.sisAcademicoSectionKey,
      reportKey: app.legacyReportKey,
      registeredTitleType: app.titulosRegistradosTipo,
    })
    const activePermissionAllowed = screenPermissionAllowsCode(app.screenAccessPages, activePermission)

    if (!activePermissionAllowed) {
      pageContent = (
        <SessionStatusView
          message="Validando acceso a la pantalla..."
          detail={app.screenAccessError || 'La opción solicitada no está asignada al perfil autenticado.'}
        />
      )
    } else if (app.activePage === 'dashboard') {
      pageContent = (
        <DashboardView
          displayName={app.displayName}
          error={app.dashboardMatriculaError}
          data={app.dashboardMatricula}
          role={app.session.rol}
        />
      )
    } else if (app.activePage === 'sistema-academico') {
      pageContent = (
        <SistemaAcademicoView
          displayName={app.displayName}
          role={app.session.rol}
          data={app.dashboardMatricula}
          error={app.dashboardMatriculaError}
          onOpenAdmissions={() => app.openPreinscripcionStage('registro')}
          onOpenFinance={() => app.openGestionSisAcademicoPage('cabecera_matricula')}
          onOpenEnrollment={() => app.openPreinscripcionStage('materias')}
          onOpenRecords={() => app.openGestionSisAcademicoPage('matricula_materias')}
          onOpenFaculty={app.openMatriculaDocentePage}
          onOpenPractices={app.openPracticasInstitucionalesPage}
          onOpenGraduation={app.openTitulacionPage}
          onOpenReports={app.openReporteriaIntegralPage}
          onOpenCatalogs={() => app.openGestionSisAcademicoPage('periodos')}
        />
      )
    } else if (app.activePage === 'matricula') {
      pageContent = (
        <MatriculaView
          displayName={app.displayName}
          loadingSummary={app.matriculaSummaryLoading}
          loadingList={app.matriculaListLoading}
          summaryError={app.matriculaSummaryError}
          listError={app.matriculaListError}
          summaryItems={app.matriculaSummary}
          updatedAt={app.matriculaSummaryUpdatedAt}
          totalsByEstado={app.matriculaTotalsByEstado}
          selectedTipo={app.matriculaTipo}
          selectedEstado={app.matriculaEstado}
          students={app.matriculaStudents}
          onLoadSummary={app.loadMatriculaSummary}
          onSelectTipo={app.selectMatriculaTipo}
          onSelectEstado={app.selectMatriculaEstado}
          onSelectEstadoGlobal={app.selectMatriculaEstadoGlobal}
          onSelectTotalRh={app.selectMatriculaTotalRh}
        />
      )
    } else if (app.activePage === 'matricula-acad') {
      pageContent = (
        <MatriculaAcadView
          displayName={app.displayName}
          initialMode={app.matriculaAcadMode}
          onModeChange={app.openMatriculaAcadPage}
          allowedModes={allowedAcademicEnrollmentModes}
        />
      )
    } else if (app.activePage === 'matricula-docente') {
      pageContent = <MatriculaDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'solicitudes-cambio-carrera') {
      pageContent = <CareerChangeRequestsView displayName={app.displayName} role={app.session.rol} />
    } else if (app.activePage === 'solicitudes-cambio-modalidad') {
      pageContent = <ModalityChangeRequestsView displayName={app.displayName} role={app.session.rol} />
    } else if (app.activePage === 'estado-docente') {
      pageContent = <EstadoDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'senescyt-estudiantes') {
      pageContent = <SenescytEstudiantesView displayName={app.displayName} />
    } else if (app.activePage === 'actualizar-datos-estudiante') {
      pageContent = <ActualizarDatosEstudianteView displayName={app.displayName} />
    } else if (app.activePage === 'actualizar-correo-intec') {
      pageContent = <ActualizarCorreoIntecView displayName={app.displayName} />
    } else if (app.activePage === 'preinscripcion') {
      pageContent = (
        <PreinscripcionView
          displayName={app.displayName}
          role={app.session.rol}
          activeStage={app.preinscriptionActiveStage}
          onStageChange={app.openPreinscripcionStage}
          allowedStages={allowedPreinscriptionStages}
        />
      )
    } else if (app.activePage === 'reporteria-carreras') {
      pageContent = (
        <ReporteriaCarrerasView
          displayName={app.displayName}
          loading={app.matriculaCareerStateLoading}
          error={app.matriculaCareerStateError}
          report={app.matriculaCareerStateReport}
          onLoad={app.loadMatriculaCareerStateReport}
        />
      )
    } else if (app.activePage === 'reporteria-integral') {
      pageContent = <ReporteriaIntegralView displayName={app.displayName} role={app.session.rol} initialReportKey={app.legacyReportKey} />
    } else if (app.activePage === 'reportes-individuales') {
      pageContent = <ReportesIndividualesView displayName={app.displayName} role={app.session.rol} initialReportKey={app.legacyReportKey} />
    } else if (app.activePage === 'admin-notas-asignatura') {
      pageContent = (
        <NotasPorAsignaturaView
          displayName={app.displayName}
          role={app.session.rol}
          onOpenLanguages={screenPermissionAllowsPage(app.screenAccessPages, 'ingles') ? app.openInglesPage : undefined}
        />
      )
    } else if (app.activePage === 'asignacion-pantallas') {
      pageContent = <AsignacionPantallasView displayName={app.displayName} />
    } else if (app.activePage === 'gestion-sisacademico') {
      pageContent = (
        <GestionSisAcademicoView
          displayName={app.displayName}
          initialSectionKey={app.sisAcademicoSectionKey}
          allowedSectionKeys={allowedSisAcademicoSections}
          onSectionChange={app.openGestionSisAcademicoPage}
          onOpenMoodleUsers={canOpenMoodleUsers
            ? () => app.openMoodlePage('users')
            : undefined}
        />
      )
    } else if (app.activePage === 'periodo-academico') {
      pageContent = (
        <PeriodoAcademicoView
          displayName={app.displayName}
          loading={app.matriculaPeriodSummaryLoading}
          loadingStudents={app.matriculaListLoading}
          error={app.matriculaPeriodSummaryError}
          studentsError={app.matriculaListError}
          periodSummaryItems={app.matriculaPeriodSummary}
          yearSummaryItems={app.matriculaYearSummary}
          students={app.matriculaStudents}
          onLoadSummary={app.loadAcademicMatriculaSummary}
          onSelectYear={app.selectPeriodoAcademicoYear}
        />
      )
    } else if (app.activePage === 'periodo-matriculados') {
      pageContent = (
        <PeriodoMatriculadosView
          displayName={app.displayName}
          loading={app.matriculaMovementSummaryLoading}
          loadingStudents={app.matriculaListLoading}
          error={app.matriculaMovementSummaryError}
          studentsError={app.matriculaListError}
          periodSummaryItems={app.matriculaMovementSummary}
          yearSummaryItems={app.matriculaMovementYearSummary}
          students={app.matriculaStudents}
          onLoadSummary={app.loadMovementMatriculaSummary}
          onSelectYear={app.selectPeriodoMatriculadosYear}
        />
      )
    } else if (app.activePage === 'ingreso-ventas') {
      pageContent = (
        <IngresoVentasView
          displayName={app.displayName}
          loading={app.ingresoVentasLoading}
          error={app.ingresoVentasError}
          data={app.ingresoVentas}
          onLoad={app.loadIngresoVentas}
        />
      )
    } else if (app.activePage === 'cruce-datos') {
      pageContent = (
        <CruceDatosView
          displayName={app.displayName}
          loading={app.cruceDatosLoading}
          downloadLoading={app.cruceDatosDownloadLoading}
          error={app.cruceDatosError}
          data={app.cruceDatos}
          onLoad={app.loadCruceDatos}
          onDownload={app.downloadCruceDatosExcel}
        />
      )
    } else if (app.activePage === 'validar-excel') {
      pageContent = <ExcelValidationView displayName={app.displayName} />
    } else if (app.activePage === 'rango-edades') {
      pageContent = <RangoEdadesView displayName={app.displayName} />
    } else if (app.activePage === 'fecha-grado') {
      pageContent = <FechaGradoView displayName={app.displayName} role={app.session.rol} />
    } else if (app.activePage === 'titulacion') {
      pageContent = (
        <TitulacionView
          displayName={app.displayName}
          role={app.session.rol}
          section="verificacion"
          onOpenProcesoTitulacion={app.openTitulacionProcesoPage}
        />
      )
    } else if (app.activePage === 'titulacion-proceso') {
      pageContent = <TitulacionView displayName={app.displayName} role={app.session.rol} section="proceso" />
    } else if (app.activePage === 'titulacion-responsables') {
      pageContent = <TitulacionView displayName={app.displayName} role={app.session.rol} section="responsables" />
    } else if (app.activePage === 'titulos-registrados') {
      pageContent = (
        <TitulosRegistradosView
          key={app.titulosRegistradosTipo || 'todos'}
          displayName={app.displayName}
          role={app.session.rol}
          initialTipo={app.titulosRegistradosTipo}
        />
      )
    } else if (app.activePage === 'certificados') {
      pageContent = <CertificadosView displayName={app.displayName} />
    } else if (app.activePage === 'matricula-excel-certificados') {
      pageContent = <MatriculaExcelCertificadosView displayName={app.displayName} />
    } else if (app.activePage === 'renombrar-certificados') {
      pageContent = <CertificateRenamerView displayName={app.displayName} />
    } else if (app.activePage === 'credenciales') {
      pageContent = <CredentialGeneratorView displayName={app.displayName} />
    } else if (app.activePage === 'correos-masivos') {
      pageContent = <MassEmailView displayName={app.displayName} />
    } else if (app.activePage === 'carnet-institucional') {
      pageContent = <CarnetInstitucionalView displayName={app.displayName} role={app.session.rol} />
    } else if (app.activePage === 'evaluacion-docente') {
      pageContent = (
        <TeacherEvaluationView
          displayName={app.displayName}
          defaultCedula={app.session.cedula || ''}
        />
      )
    } else if (app.activePage === 'evaluacion-docente-admin' || app.activePage === 'evaluacion-docente-avance') {
      pageContent = <TeacherEvaluationAdminView displayName={app.displayName} mode="progress" />
    } else if (app.activePage === 'evaluacion-docente-reportes') {
      pageContent = <TeacherEvaluationAdminView displayName={app.displayName} mode="reports" />
    } else if (
      app.activePage === 'portal-estudiante'
      || app.activePage === 'portal-estudiante-malla-curricular'
      || app.activePage === 'portal-estudiante-malla-academica'
      || app.activePage === 'portal-estudiante-calificaciones'
    ) {
      pageContent = (
        <PortalEstudianteView
          displayName={app.displayName}
          activeSection={app.portalStudentSection}
          allowedSections={[
            ...(screenPermissionAllowsPage(app.screenAccessPages, 'portal-estudiante') ? ['dashboard' as const] : []),
            ...(screenPermissionAllowsPage(app.screenAccessPages, 'portal-estudiante-malla-curricular') ? ['curricular' as const] : []),
            ...(screenPermissionAllowsPage(app.screenAccessPages, 'portal-estudiante-malla-academica') ? ['academica' as const] : []),
            ...(screenPermissionAllowsPage(app.screenAccessPages, 'portal-estudiante-calificaciones') ? ['notas' as const] : []),
          ]}
          onSectionChange={app.openPortalEstudiantePage}
        />
      )
    } else if (app.activePage === 'ingles') {
      pageContent = (
        <InglesView
          displayName={app.displayName}
          role={app.session.rol}
          onOpenSubjectGrades={screenPermissionAllowsPage(app.screenAccessPages, 'admin-notas-asignatura') ? app.openAdminNotasAsignaturaPage : undefined}
        />
      )
    } else if (app.activePage === 'expedientes-documentales') {
      pageContent = <ExpedientesDocumentalesView displayName={app.displayName} role={app.session.rol} />
    } else if (app.activePage === 'portal-docente') {
      pageContent = <PortalDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'portal-docente-informe') {
      pageContent = <PortalDocenteView displayName={app.displayName} initialMode="compliance" />
    } else if (app.activePage === 'portal-docente-planificacion') {
      pageContent = <PortalDocentePlanificacionView displayName={app.displayName} />
    } else if (app.activePage === 'portal-docente-contratos') {
      pageContent = <PortalDocenteContratosView displayName={app.displayName} />
    } else if (app.activePage === 'formato-informe-docente') {
      pageContent = <TeacherComplianceFormatView displayName={app.displayName} />
    } else if (app.activePage === 'practicas-institucionales') {
      pageContent = (
        <PracticasInstitucionalesView
          key={app.practicasNavigationKey}
          displayName={app.displayName}
          role={app.session.rol}
          codigoEstud={app.session.codigo_estud}
          initialProcess={app.practicasProcess}
          onProcessChange={app.openPracticasInstitucionalesPage}
        />
      )
    } else if (app.activePage === 'teams-matricula') {
      pageContent = (
        <TeamsEnrollmentView
          displayName={app.displayName}
          catalogLoading={app.catalogLoading}
          catalogMessage={app.catalogMessage}
          catalogError={app.catalogError}
          createLoading={app.createLoading}
          createMessage={app.createMessage}
          createError={app.createError}
          catalogTeams={app.catalogTeams}
          selectedTeam={app.selectedTeam}
          createDisplayName={app.createDisplayName}
          createCourses={app.createCourses}
          createTeachers={app.createTeachers}
          createVisibility={app.createVisibility}
          teamsTeamId={app.teamsTeamId}
          onLoadCatalog={app.loadCatalog}
          onSelectTeam={app.setSelectedTeamIndex}
          onTeamIdFromCatalog={app.setTeamsTeamId}
          onCreateDisplayNameChange={app.setCreateDisplayName}
          onCreateCoursesChange={app.setCreateCourses}
          onCreateTeachersChange={app.setCreateTeachers}
          onCreateVisibilityChange={app.setCreateVisibility}
          onCreateAndEnroll={app.createAndEnroll}
        />
      )
    } else if (app.activePage === 'moodle-teams') {
      pageContent = <MoodleTeamsEnrollmentView displayName={app.displayName} />
    } else if (app.activePage === 'teams') {
      pageContent = (
        <TeamsView
          displayName={app.displayName}
          catalogLoading={app.catalogLoading}
          catalogMessage={app.catalogMessage}
          catalogError={app.catalogError}
          catalogTeams={app.catalogTeams}
          selectedTeamIndex={app.selectedTeamIndex}
          selectedTeam={app.selectedTeam}
          onLoadCatalog={app.loadCatalog}
          onSelectTeam={app.setSelectedTeamIndex}
          onTeamIdFromCatalog={app.setTeamsTeamId}
        />
      )
    } else if (app.activePage === 'historico-integraciones') {
      pageContent = <HistoricoIntegracionesView displayName={app.displayName} />
    } else if (app.activePage === 'informe-cumplimiento') {
      pageContent = <InformeCumplimientoView displayName={app.displayName} />
    } else if (app.activePage === 'moodle') {
      pageContent = (
        <MoodleView
          displayName={app.displayName}
          activeSection={app.activeMoodleSection}
          availableSections={allowedMoodleSections}
          onSectionChange={app.openMoodlePage}
        />
      )
    } else {
      pageContent = (
        <SessionStatusView
          message="Pantalla no disponible"
          detail="La opción solicitada no forma parte de la navegación activa."
        />
      )
    }

    return (
      <main className="app app--dashboard">
        <StudentLayout
          activePage={app.activePage}
          activeSisAcademicoSection={app.sisAcademicoSectionKey}
          activeLegacyReport={app.legacyReportKey}
          activePortalStudentSection={app.portalStudentSection}
          activePreinscriptionStage={app.preinscriptionActiveStage}
          activeMatriculaAcadMode={app.matriculaAcadMode}
          activeMoodleSection={app.activeMoodleSection}
          activePracticasProcess={app.practicasProcess}
          role={app.session.rol}
          screenAccessPages={app.screenAccessPages}
          displayName={app.displayName}
          cedula={app.session.cedula || ''}
          onOpenDashboard={app.openDashboard}
          onOpenSistemaAcademico={app.openSistemaAcademicoPage}
          onOpenPortalEstudiante={app.openPortalEstudiantePage}
          onOpenIngles={app.openInglesPage}
          onOpenExpedientesDocumentales={app.openExpedientesDocumentalesPage}
          onOpenPortalDocente={app.openPortalDocentePage}
          onOpenPortalDocenteInforme={app.openPortalDocenteInformePage}
          onOpenPortalDocentePlanificacion={app.openPortalDocentePlanificacionPage}
          onOpenPortalDocenteContratos={app.openPortalDocenteContratosPage}
          onOpenTeams={app.openTeamsPage}
          onOpenTeamsMatricula={app.openTeamsMatriculaPage}
          onOpenMoodleTeams={app.openMoodleTeamsPage}
          onOpenHistoricoIntegraciones={app.openHistoricoIntegracionesPage}
          onOpenInformeCumplimiento={app.openInformeCumplimientoPage}
          onOpenMoodle={app.openMoodlePage}
          onOpenMatricula={app.openMatriculaPage}
          onOpenMatriculaAcad={app.openMatriculaAcadPage}
          onOpenMatriculaDocente={app.openMatriculaDocentePage}
          onOpenCareerChangeRequests={app.openCareerChangeRequestsPage}
          onOpenModalityChangeRequests={app.openModalityChangeRequestsPage}
          onOpenEstadoDocente={app.openEstadoDocentePage}
          onOpenSenescytEstudiantes={app.openSenescytEstudiantesPage}
          onOpenActualizarDatosEstudiante={app.openActualizarDatosEstudiantePage}
          onOpenActualizarCorreoIntec={app.openActualizarCorreoIntecPage}
          onOpenPreinscripcion={app.openPreinscripcionStage}
          onOpenReporteriaCarreras={app.openReporteriaCarrerasPage}
          onOpenReporteriaIntegral={app.openReporteriaIntegralPage}
          onOpenReportesIndividuales={app.openReportesIndividualesPage}
          onOpenAdminNotasAsignatura={app.openAdminNotasAsignaturaPage}
          onOpenGestionSisAcademico={app.openGestionSisAcademicoPage}
          onOpenAsignacionPantallas={app.openAsignacionPantallasPage}
          onOpenPeriodoAcademico={app.openPeriodoAcademicoPage}
          onOpenPeriodoMatriculados={app.openPeriodoMatriculadosPage}
          onOpenIngresoVentas={app.openIngresoVentasPage}
          onOpenCruceDatos={app.openCruceDatosPage}
          onOpenValidarExcel={app.openValidarExcelPage}
          onOpenRangoEdades={app.openRangoEdadesPage}
          onOpenFechaGrado={app.openFechaGradoPage}
          onOpenTitulacion={app.openTitulacionPage}
          onOpenTitulacionProceso={app.openTitulacionProcesoPage}
          onOpenTitulacionResponsables={app.openTitulacionResponsablesPage}
          onOpenTitulosRegistrados={app.openTitulosRegistradosPage}
          onOpenCertificados={app.openCertificadosPage}
          onOpenMatriculaExcelCertificados={app.openMatriculaExcelCertificadosPage}
          onOpenCertificateRenamer={app.openCertificateRenamerPage}
          onOpenCredentialGenerator={app.openCredentialGeneratorPage}
          onOpenMassEmail={app.openMassEmailPage}
          onOpenCarnetInstitucional={app.openCarnetInstitucionalPage}
          onOpenTeacherEvaluation={app.openTeacherEvaluationPage}
          onOpenTeacherEvaluationAdmin={app.openTeacherEvaluationAdminPage}
          onOpenTeacherEvaluationProgress={app.openTeacherEvaluationProgressPage}
          onOpenTeacherEvaluationReports={app.openTeacherEvaluationReportsPage}
          onOpenTeacherComplianceFormat={app.openTeacherComplianceFormatPage}
          onOpenPracticasInstitucionales={app.openPracticasInstitucionalesPage}
          onLogout={() => {
            void app.logout()
          }}
        >
          <Suspense fallback={<SessionStatusView message="Cargando módulo..." />}>{pageContent}</Suspense>
        </StudentLayout>
      </main>
    )
  }

  return (
    <LoginView
      login={app.login}
      password={app.password}
      showPassword={app.showPassword}
      loading={app.loading}
      error={app.error}
      onLoginChange={app.setLogin}
      onPasswordChange={app.setPassword}
      onTogglePassword={() => app.setShowPassword((value) => !value)}
      onSubmit={app.onSubmit}
      onOpenTeacherEvaluation={() => setPublicTeacherEvaluation(true)}
    />
  )
}

export default App
