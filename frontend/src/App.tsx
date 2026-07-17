import { useState, type ReactNode } from 'react'

import './App.css'
import { StudentLayout } from './components/StudentLayout'
import { CarnetInstitucionalView } from './features/admin/CarnetInstitucionalView'
import { CredentialGeneratorView } from './features/admin/CredentialGeneratorView'
import { MassEmailView } from './features/admin/MassEmailView'
import { TeacherComplianceFormatView } from './features/admin/TeacherComplianceFormatView'
import { LoginView } from './features/auth/LoginView'
import { SessionStatusView } from './features/auth/SessionStatusView'
import { CruceDatosView } from './features/cruce/CruceDatosView'
import { ExcelValidationView } from './features/cruce/ExcelValidationView'
import { DashboardView } from './features/dashboard/DashboardView'
import { TeacherEvaluationAdminView } from './features/evaluacion/TeacherEvaluationAdminView'
import { TeacherEvaluationView } from './features/evaluacion/TeacherEvaluationView'
import { ActualizarDatosEstudianteView } from './features/matricula/ActualizarDatosEstudianteView'
import { CertificateRenamerView } from './features/matricula/CertificateRenamerView'
import { CertificadosView } from './features/matricula/CertificadosView'
import { EstadoDocenteView } from './features/matricula/EstadoDocenteView'
import { GestionSisAcademicoView } from './features/matricula/GestionSisAcademicoView'
import { FechaGradoView } from './features/matricula/FechaGradoView'
import { IngresoVentasView } from './features/matricula/IngresoVentasView'
import { MatriculaAcadView } from './features/matricula/MatriculaAcadView'
import { MatriculaDocenteView } from './features/matricula/MatriculaDocenteView'
import { MatriculaExcelCertificadosView } from './features/matricula/MatriculaExcelCertificadosView'
import { MatriculaView } from './features/matricula/MatriculaView'
import { PeriodoAcademicoView } from './features/matricula/PeriodoAcademicoView'
import { PeriodoMatriculadosView } from './features/matricula/PeriodoMatriculadosView'
import { PreinscripcionView } from './features/matricula/PreinscripcionView'
import { RangoEdadesView } from './features/matricula/RangoEdadesView'
import { ReporteriaCarrerasView } from './features/matricula/ReporteriaCarrerasView'
import { ReporteriaIntegralView } from './features/matricula/ReporteriaIntegralView'
import { ReportesIndividualesView } from './features/matricula/ReportesIndividualesView'
import { SenescytEstudiantesView } from './features/matricula/SenescytEstudiantesView'
import { TitulosRegistradosView } from './features/matricula/TitulosRegistradosView'
import { TitulacionView } from './features/matricula/TitulacionView'
import { PortalDocenteView } from './features/portal/PortalDocenteView'
import { PortalEstudianteView } from './features/portal/PortalEstudianteView'
import { PracticasInstitucionalesView } from './features/practicas/PracticasInstitucionalesView'
import { TeamsEnrollmentView } from './features/teams/TeamsEnrollmentView'
import { TeamsView } from './features/teams/TeamsView'
import { useReporteriaApp } from './hooks/useReporteriaApp'

function App() {
  const app = useReporteriaApp()
  const [publicTeacherEvaluation, setPublicTeacherEvaluation] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const requestedPage = params.get('open_page') || params.get('public')
    return requestedPage === 'evaluacion-docente' || window.location.pathname.includes('evaluacion-docente')
  })

  if (app.bootstrapping) {
    return <SessionStatusView message="Validando sesion activa..." />
  }

  if (!app.session && publicTeacherEvaluation) {
    return (
      <TeacherEvaluationView
        displayName="Formulario publico"
        publicMode
        onBackToLogin={() => setPublicTeacherEvaluation(false)}
      />
    )
  }

  if (app.session) {
    let pageContent: ReactNode

    if (app.activePage === 'dashboard') {
      pageContent = (
        <DashboardView
          displayName={app.displayName}
          error={app.dashboardMatriculaError}
          data={app.dashboardMatricula}
          role={app.session.rol}
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
      pageContent = <MatriculaAcadView displayName={app.displayName} />
    } else if (app.activePage === 'matricula-docente') {
      pageContent = <MatriculaDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'estado-docente') {
      pageContent = <EstadoDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'senescyt-estudiantes') {
      pageContent = <SenescytEstudiantesView displayName={app.displayName} />
    } else if (app.activePage === 'actualizar-datos-estudiante') {
      pageContent = <ActualizarDatosEstudianteView displayName={app.displayName} />
    } else if (app.activePage === 'preinscripcion') {
      pageContent = (
        <PreinscripcionView
          displayName={app.displayName}
          role={app.session.rol}
          activeStage={app.preinscriptionActiveStage}
          onStageChange={app.setPreinscriptionActiveStage}
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
      pageContent = <ReporteriaIntegralView displayName={app.displayName} initialReportKey={app.legacyReportKey} />
    } else if (app.activePage === 'reportes-individuales') {
      pageContent = <ReportesIndividualesView displayName={app.displayName} initialReportKey={app.legacyReportKey} />
    } else if (app.activePage === 'gestion-sisacademico') {
      pageContent = <GestionSisAcademicoView displayName={app.displayName} initialSectionKey={app.sisAcademicoSectionKey} />
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
    } else if (app.activePage === 'portal-estudiante') {
      pageContent = (
        <PortalEstudianteView
          displayName={app.displayName}
          activeSection={app.portalStudentSection}
          onSectionChange={app.setPortalStudentSection}
        />
      )
    } else if (app.activePage === 'portal-docente') {
      pageContent = <PortalDocenteView displayName={app.displayName} />
    } else if (app.activePage === 'portal-docente-informe') {
      pageContent = <PortalDocenteView displayName={app.displayName} initialMode="compliance" />
    } else if (app.activePage === 'formato-informe-docente') {
      pageContent = <TeacherComplianceFormatView displayName={app.displayName} />
    } else if (app.activePage === 'practicas-institucionales') {
      pageContent = (
        <PracticasInstitucionalesView
          displayName={app.displayName}
          role={app.session.rol}
          codigoEstud={app.session.codigo_estud}
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
    } else {
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
    }

    return (
      <main className="app app--dashboard">
        <StudentLayout
          activePage={app.activePage}
          activeSisAcademicoSection={app.sisAcademicoSectionKey}
          activeLegacyReport={app.legacyReportKey}
          activePortalStudentSection={app.portalStudentSection}
          activePreinscriptionStage={app.preinscriptionActiveStage}
          role={app.session.rol}
          displayName={app.displayName}
          cedula={app.session.cedula || ''}
          onOpenDashboard={app.openDashboard}
          onOpenPortalEstudiante={app.openPortalEstudiantePage}
          onOpenPortalDocente={app.openPortalDocentePage}
          onOpenPortalDocenteInforme={app.openPortalDocenteInformePage}
          onOpenTeams={app.openTeamsPage}
          onOpenTeamsMatricula={app.openTeamsMatriculaPage}
          onOpenMatricula={app.openMatriculaPage}
          onOpenMatriculaAcad={app.openMatriculaAcadPage}
          onOpenMatriculaDocente={app.openMatriculaDocentePage}
          onOpenEstadoDocente={app.openEstadoDocentePage}
          onOpenSenescytEstudiantes={app.openSenescytEstudiantesPage}
          onOpenActualizarDatosEstudiante={app.openActualizarDatosEstudiantePage}
          onOpenPreinscripcion={app.openPreinscripcionStage}
          onOpenReporteriaCarreras={app.openReporteriaCarrerasPage}
          onOpenReporteriaIntegral={app.openReporteriaIntegralPage}
          onOpenReportesIndividuales={app.openReportesIndividualesPage}
          onOpenGestionSisAcademico={app.openGestionSisAcademicoPage}
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
          onOpenTeacherEvaluationProgress={app.openTeacherEvaluationProgressPage}
          onOpenTeacherEvaluationReports={app.openTeacherEvaluationReportsPage}
          onOpenTeacherComplianceFormat={app.openTeacherComplianceFormatPage}
          onOpenPracticasInstitucionales={app.openPracticasInstitucionalesPage}
          onLogout={() => {
            void app.logout()
          }}
        >
          {pageContent}
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
