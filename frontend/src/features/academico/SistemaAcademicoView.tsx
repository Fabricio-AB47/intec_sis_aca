import { useEffect, useRef, useState } from 'react'
import { ArrowRight, RefreshCw, Settings } from 'lucide-react'
import { fetchAcademicSystemIntegrationStatus } from '../../lib/api'
import { screenPermissionAllowsCode, screenPermissionAllowsPage } from '../../lib/screenAccess'
import type { AcademicSystemIntegrationResponse, DashboardMatriculaResponse, ScreenPermissionCode } from '../../types/app'
import './AcademicWorkCenter.css'

type SistemaAcademicoViewProps = {
  displayName: string
  permissions: readonly ScreenPermissionCode[]
  data: DashboardMatriculaResponse | null
  error?: string
  onOpenAdmissions: () => void
  onOpenFinance: () => void
  onOpenEnrollment: () => void
  onOpenRecords: () => void
  onOpenFaculty: () => void
  onOpenPractices: () => void
  onOpenGraduation: () => void
  onOpenReports: () => void
  onOpenCatalogs: () => void
}
type AcademicArea = {
  key: string
  phase: 'entry' | 'academic' | 'completion' | 'control'
  title: string
  owner: string
  record: string
  permission: ScreenPermissionCode
  action: () => void
}

function metric(value: number | null | undefined, failed: boolean): string {
  if (failed || value === null || value === undefined || !Number.isFinite(value)) return 'No disponible'
  return value.toLocaleString('es-EC')
}

export function SistemaAcademicoView({
  displayName, permissions, data, error = '', onOpenAdmissions, onOpenFinance,
  onOpenEnrollment, onOpenRecords, onOpenFaculty, onOpenPractices, onOpenGraduation,
  onOpenReports, onOpenCatalogs,
}: Readonly<SistemaAcademicoViewProps>) {
  const [activePhase, setActivePhase] = useState<'all' | AcademicArea['phase']>('all')
  const [integration, setIntegration] = useState<AcademicSystemIntegrationResponse | null>(null)
  const [integrationError, setIntegrationError] = useState('')
  const [integrationLoading, setIntegrationLoading] = useState(false)
  const requestRef = useRef<AbortController | null>(null)
  const checkedRef = useRef(false)
  useEffect(() => () => requestRef.current?.abort(), [])

  async function checkIntegration() {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    checkedRef.current = true
    setIntegrationLoading(true)
    setIntegrationError('')
    setIntegration(null)
    try {
      const payload = await fetchAcademicSystemIntegrationStatus(controller.signal)
      if (!controller.signal.aborted) setIntegration(payload)
    } catch {
      if (!controller.signal.aborted) setIntegrationError('No se pudo verificar la disponibilidad de las fuentes institucionales.')
    } finally {
      if (!controller.signal.aborted) setIntegrationLoading(false)
    }
  }

  const areas: AcademicArea[] = [
    { key: 'admission', phase: 'entry', title: 'Admisión e inscripción', owner: 'Admisiones', record: 'Aspirantes y documentos de ingreso', permission: 'preinscripcion/registro', action: onOpenAdmissions },
    { key: 'finance', phase: 'entry', title: 'Financiamiento estudiantil', owner: 'Financiero', record: 'Cabecera de matrícula y pagos', permission: 'gestion-sisacademico/cabecera_matricula', action: onOpenFinance },
    { key: 'enrollment', phase: 'entry', title: 'Matrícula académica', owner: 'Secretaría académica', record: 'Carrera, período, paralelo y materias', permission: 'preinscripcion/materias', action: onOpenEnrollment },
    { key: 'records', phase: 'academic', title: 'Materias y calificaciones', owner: 'Coordinación académica', record: 'Matrículas y notas registradas', permission: 'gestion-sisacademico/matricula_materias', action: onOpenRecords },
    { key: 'faculty', phase: 'academic', title: 'Asignación docente', owner: 'Coordinación académica', record: 'Docentes y materias por período', permission: 'matricula-docente', action: onOpenFaculty },
    { key: 'practices', phase: 'completion', title: 'Prácticas y vinculación', owner: 'Prácticas', record: 'Horas, documentos y certificados', permission: 'practicas-institucionales', action: onOpenPractices },
    { key: 'graduation', phase: 'completion', title: 'Egreso y titulación', owner: 'Unidad de titulación', record: 'Revisión de requisitos académicos', permission: 'titulacion', action: onOpenGraduation },
    { key: 'analytics', phase: 'control', title: 'Reportes institucionales', owner: 'Dirección y control', record: 'Reportes por carrera, período y población', permission: 'reporteria-integral', action: onOpenReports },
  ]
  const canOpen = (area: AcademicArea) => area.key === 'analytics'
    ? screenPermissionAllowsPage(permissions, 'reporteria-integral')
    : screenPermissionAllowsCode(permissions, area.permission)
  const phases: Array<{ key: 'all' | AcademicArea['phase']; label: string }> = [
    { key: 'all', label: 'Todos' }, { key: 'entry', label: 'Ingreso' },
    { key: 'academic', label: 'Formación' }, { key: 'completion', label: 'Culminación' }, { key: 'control', label: 'Control' },
  ]
  const visibleAreas = areas.filter((area) => activePhase === 'all' || area.phase === activePhase)
  const graduated = data?.states ? data.states.find((item) => item.estado_codigo === 'G')?.total_estudiantes ?? 0 : undefined
  const metrics: Array<{ label: string; value: number | undefined }> = [
    { label: 'Estudiantes registrados', value: data?.total_estudiantes },
    { label: 'Activos regulares', value: data?.active_regular_students },
    { label: 'Activos de homologación', value: data?.active_homologation_students },
    { label: 'Graduados', value: graduated },
  ]

  return <section className="academic-system-page academic-work-center">
    <header className="academic-system-hero">
      <div><h1>Sistema académico</h1><p>{displayName}</p></div>
      <button type="button" className="ghost-button" onClick={onOpenCatalogs} disabled={!screenPermissionAllowsCode(permissions, 'gestion-sisacademico/periodos')}><Settings size={16} />Configuración académica</button>
    </header>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <section className="academic-system-summary" aria-label="Resumen académico" aria-busy={!data && !error}>
      {metrics.map(({ label, value }) => <div key={label}><span>{label}</span><strong>{!data && !error ? 'Consultando...' : metric(value, Boolean(error))}</strong></div>)}
    </section>

    <section className="academic-lifecycle" aria-label="Procesos académicos">
      <div className="academic-lifecycle__heading"><h2>Procesos académicos</h2><span>{visibleAreas.filter(canOpen).length} accesos habilitados</span></div>
      <div className="academic-lifecycle__filters" role="group" aria-label="Filtrar procesos académicos">
        {phases.map((phase) => <button type="button" key={phase.key} aria-pressed={activePhase === phase.key} onClick={() => setActivePhase(phase.key)}>{phase.label}</button>)}
      </div>
      <div className="academic-lifecycle__header" aria-hidden="true"><span>Proceso</span><span>Responsable</span><span>Registro</span><span>Acción</span></div>
      {visibleAreas.map((area) => <div className="academic-lifecycle__row" key={area.key}>
        <strong>{area.title}</strong><span>{area.owner}</span><span>{area.record}</span>
        <button type="button" className="ghost-button" disabled={!canOpen(area)} aria-label={`Abrir ${area.title}`} onClick={area.action}>{canOpen(area) ? 'Abrir' : 'Sin acceso'}<ArrowRight size={16} /></button>
      </div>)}
    </section>

    <details className="academic-integration" onToggle={(event) => { if (event.currentTarget.open && !checkedRef.current) void checkIntegration() }}>
      <summary>Disponibilidad de fuentes institucionales</summary>
      <div className="academic-lifecycle__heading"><h2>Conexiones</h2><button className="ghost-button" disabled={integrationLoading} onClick={() => void checkIntegration()}><RefreshCw size={16} />Verificar conexiones</button></div>
      <div aria-live="polite" aria-busy={integrationLoading}>
        {integrationLoading ? <p className="academic-integration__empty">Consultando fuentes...</p> : null}
        {integrationError ? <p className="form-error" role="alert">{integrationError}</p> : null}
        {integration ? <>
          <p className="academic-integration__empty">{integration.summary.available} de {integration.summary.total} fuentes disponibles · Consultado: {new Date(integration.generated_at).toLocaleString('es-EC')}</p>
          <div className="academic-integration__header" aria-hidden="true"><span>Base de datos</span><span>Responsabilidad</span><span>Relación</span><span>Estado</span></div>
          {integration.databases.map((database) => <div className="academic-integration__row" key={database.key}>
            <strong>{database.name}</strong><span>{database.role}</span><span>{database.relation}</span>
            <b className={`database-status database-status--${database.status.toLowerCase()}`}>{database.available ? 'Disponible' : database.status === 'PARTIAL' ? 'Instalación parcial' : !database.configured ? 'No configurada' : 'No disponible'}</b>
          </div>)}
        </> : null}
      </div>
    </details>
  </section>
}
