import { useEffect, useState } from 'react'
import { fetchAcademicSystemIntegrationStatus } from '../../lib/api'
import type {
  AcademicSystemDatabaseStatus,
  AcademicSystemDomainStatus,
  AcademicSystemIntegrationResponse,
  DashboardMatriculaResponse,
} from '../../types/app'

type SistemaAcademicoViewProps = {
  displayName: string
  role?: string
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
  number: string
  title: string
  owner: string
  record: string
  result: string
  actionLabel: string
  roles: string[]
  action: () => void
}

const administratorRoles = new Set(['ADMINISTRADOR', 'ADMINISTRACION', 'ADMIN', 'SOPORTE'])

function normalizeRole(role?: string): string {
  return String(role || '')
    .trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function valueOrZero(value?: number | null): number {
  return Number.isFinite(Number(value)) ? Number(value) : 0
}

export function SistemaAcademicoView({
  displayName,
  role = '',
  data,
  error = '',
  onOpenAdmissions,
  onOpenFinance,
  onOpenEnrollment,
  onOpenRecords,
  onOpenFaculty,
  onOpenPractices,
  onOpenGraduation,
  onOpenReports,
  onOpenCatalogs,
}: Readonly<SistemaAcademicoViewProps>) {
  const [activePhase, setActivePhase] = useState<'all' | AcademicArea['phase']>('all')
  const [integration, setIntegration] = useState<AcademicSystemIntegrationResponse | null>(null)
  const [integrationError, setIntegrationError] = useState('')
  const [integrationLoading, setIntegrationLoading] = useState(true)
  const normalizedRole = normalizeRole(role)
  const totalStudents = valueOrZero(data?.total_estudiantes)
  const activeStudents = valueOrZero(data?.active_regular_homologation_students)
  const regularStudents = valueOrZero(data?.active_regular_students)
  const homologationStudents = valueOrZero(data?.active_homologation_students)
  const admissionStudents = valueOrZero(data?.admissions?.total_ingresados)
  const enrolledAdmissions = valueOrZero(data?.admissions?.ingresaron_cabecera_matricula)
  const graduatedStudents = valueOrZero(data?.states?.find((item) => item.estado_codigo === 'G')?.total_estudiantes)
  const activePercent = totalStudents > 0 ? Math.round((activeStudents / totalStudents) * 100) : 0

  useEffect(() => {
    let active = true
    fetchAcademicSystemIntegrationStatus()
      .then((payload) => {
        if (active) setIntegration(payload)
      })
      .catch(() => {
        if (active) {
          setIntegration(null)
          setIntegrationError('No se pudo verificar la disponibilidad de las bases institucionales.')
        }
      })
      .finally(() => {
        if (active) setIntegrationLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const areas: AcademicArea[] = [
    {
      key: 'admission',
      phase: 'entry',
      number: '01',
      title: 'Admisión e inscripción',
      owner: 'Admisiones y bienestar',
      record: 'Aspirante, beca, requisitos y documentos',
      result: 'Admisión validada',
      actionLabel: 'Abrir admisión',
      roles: ['ADMISIONES', 'BIENESTAR'],
      action: onOpenAdmissions,
    },
    {
      key: 'finance',
      phase: 'entry',
      number: '02',
      title: 'Financiamiento estudiantil',
      owner: 'Financiero',
      record: 'Arancel, matrícula, convenio, pagos y cartera',
      result: 'Condición financiera definida',
      actionLabel: 'Abrir finanzas',
      roles: ['FINANCIERO', 'ADMISIONES'],
      action: onOpenFinance,
    },
    {
      key: 'enrollment',
      phase: 'entry',
      number: '03',
      title: 'Matrícula académica',
      owner: 'Secretaría académica',
      record: 'Carrera, periodo, paralelo y materias',
      result: 'Matrícula académica activa',
      actionLabel: 'Abrir matrícula',
      roles: ['ACADEMICO', 'ADMISIONES'],
      action: onOpenEnrollment,
    },
    {
      key: 'records',
      phase: 'academic',
      number: '04',
      title: 'Expediente y avance académico',
      owner: 'Coordinación académica',
      record: 'Malla, asistencia, calificaciones y promoción',
      result: 'Avance académico consolidado',
      actionLabel: 'Abrir expediente',
      roles: ['ACADEMICO', 'BIENESTAR'],
      action: onOpenRecords,
    },
    {
      key: 'faculty',
      phase: 'academic',
      number: '05',
      title: 'Gestión docente',
      owner: 'Coordinación académica',
      record: 'Carga, planificación, evaluación y cumplimiento',
      result: 'Ejecución docente controlada',
      actionLabel: 'Abrir docencia',
      roles: ['ACADEMICO'],
      action: onOpenFaculty,
    },
    {
      key: 'practices',
      phase: 'completion',
      number: '06',
      title: 'Prácticas y vinculación',
      owner: 'Secretaría y vinculación',
      record: 'Expedientes, horas, documentos y certificados',
      result: 'Cumplimiento reconocido',
      actionLabel: 'Abrir prácticas',
      roles: ['ACADEMICO', 'BIENESTAR', 'SECRETARIA'],
      action: onOpenPractices,
    },
    {
      key: 'graduation',
      phase: 'completion',
      number: '07',
      title: 'Egreso y titulación',
      owner: 'Unidad de titulación',
      record: 'Requisitos, modalidad, tribunal, acta y títulos',
      result: 'Egreso y titulación registrados',
      actionLabel: 'Abrir titulación',
      roles: ['ACADEMICO', 'SECRETARIA'],
      action: onOpenGraduation,
    },
    {
      key: 'analytics',
      phase: 'control',
      number: '08',
      title: 'Reportes institucionales',
      owner: 'Dirección y control',
      record: 'Indicadores, certificados y reportes regulatorios',
      result: 'Información institucional trazable',
      actionLabel: 'Abrir reportes',
      roles: ['ACADEMICO', 'FINANCIERO', 'BIENESTAR'],
      action: onOpenReports,
    },
  ]

  const canOpen = (area: AcademicArea) => administratorRoles.has(normalizedRole) || area.roles.includes(normalizedRole)
  const databasesByKey = new Map((integration?.databases || []).map((database) => [database.key, database]))
  const domainsByKey = new Map((integration?.domains || []).map((domain) => [domain.key, domain]))

  const domainLabel = (domain?: AcademicSystemDomainStatus): string => {
    if (!domain || integrationLoading) return 'Verificando fuentes'
    if (domain.status === 'READY') return 'Integración disponible'
    if (domain.status === 'PARTIAL') return `Integración parcial (${domain.available_sources}/${domain.total_sources})`
    return 'Fuentes no disponibles'
  }

  const databaseLabel = (database: AcademicSystemDatabaseStatus): string => {
    if (database.available) return 'Disponible'
    if (database.status === 'PARTIAL') return 'Instalación parcial'
    if (!database.configured) return 'No configurada'
    return 'No disponible'
  }

  const phaseOptions: Array<{ key: 'all' | AcademicArea['phase']; label: string; detail: string }> = [
    { key: 'all', label: 'Todo el ciclo', detail: '8 procesos' },
    { key: 'entry', label: 'Ingreso', detail: 'Admisión, finanzas y matrícula' },
    { key: 'academic', label: 'Formación', detail: 'Expediente y docencia' },
    { key: 'completion', label: 'Culminación', detail: 'Prácticas y titulación' },
    { key: 'control', label: 'Control', detail: 'Reportes institucionales' },
  ]
  const visibleAreas = activePhase === 'all' ? areas : areas.filter((area) => area.phase === activePhase)

  const phaseIntegrationStatus = (phase: AcademicArea['phase']): string => {
    const phaseAreas = areas.filter((area) => area.phase === phase)
    const statuses = phaseAreas.map((area) => domainsByKey.get(area.key)?.status)
    if (statuses.length > 0 && statuses.every((status) => status === 'READY')) return 'Disponible'
    if (statuses.some((status) => status === 'READY' || status === 'PARTIAL')) return 'Parcial'
    return integrationLoading ? 'Verificando' : 'No disponible'
  }

  return (
    <section className="academic-system-page">
      <header className="academic-system-hero">
        <div>
          <p className="eyebrow">Gestión institucional</p>
          <h1>Sistema académico</h1>
          <p>{displayName} · Ciclo completo del estudiante con información institucional consolidada.</p>
        </div>
        <button type="button" className="ghost-button" onClick={onOpenCatalogs} disabled={!administratorRoles.has(normalizedRole) && normalizedRole !== 'ACADEMICO'}>
          Configuración académica
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="academic-system-summary" aria-label="Resumen académico">
        <div>
          <span>Estudiantes registrados</span>
          <strong>{totalStudents.toLocaleString('es-EC')}</strong>
          <small>Base académica institucional</small>
        </div>
        <div>
          <span>Activos R/H</span>
          <strong>{activeStudents.toLocaleString('es-EC')}</strong>
          <small>{activePercent}% del total registrado</small>
        </div>
        <div>
          <span>Regular / Homologación</span>
          <strong>{regularStudents.toLocaleString('es-EC')} / {homologationStudents.toLocaleString('es-EC')}</strong>
          <small>Matrículas activas por tipo</small>
        </div>
        <div>
          <span>Ingreso / Matrícula</span>
          <strong>{admissionStudents.toLocaleString('es-EC')} / {enrolledAdmissions.toLocaleString('es-EC')}</strong>
          <small>Conversión desde admisiones</small>
        </div>
        <div>
          <span>Graduados</span>
          <strong>{graduatedStudents.toLocaleString('es-EC')}</strong>
          <small>Estado académico vigente</small>
        </div>
      </section>

      <section className="academic-process-map" aria-label="Macroprocesos académicos">
        <div className="academic-process-map__heading">
          <div>
            <span>Ruta institucional</span>
            <h2>Procesos académicos</h2>
          </div>
          <strong>De admisión a titulación</strong>
        </div>
        <div className="academic-process-map__rail">
          {phaseOptions.filter((option) => option.key !== 'all').map((option, index) => (
            <button
              type="button"
              key={option.key}
              className={activePhase === option.key ? 'is-active' : ''}
              onClick={() => setActivePhase(option.key)}
            >
              <b>{String(index + 1).padStart(2, '0')}</b>
              <span>
                <strong>{option.label}</strong>
                <small>{option.detail}</small>
              </span>
              <em>{phaseIntegrationStatus(option.key as AcademicArea['phase'])}</em>
            </button>
          ))}
        </div>
      </section>

      <section className="academic-lifecycle">
        <div className="academic-lifecycle__heading">
          <div>
            <span>Operación</span>
            <h2>Ciclo de vida académico</h2>
          </div>
          <strong>{visibleAreas.filter(canOpen).length} de {visibleAreas.length} procesos habilitados</strong>
        </div>

        <div className="academic-lifecycle__filters" role="tablist" aria-label="Filtrar procesos académicos">
          {phaseOptions.map((option) => (
            <button
              type="button"
              role="tab"
              aria-selected={activePhase === option.key}
              className={activePhase === option.key ? 'is-active' : ''}
              key={option.key}
              onClick={() => setActivePhase(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="academic-lifecycle__header" aria-hidden="true">
          <span>Etapa</span>
          <span>Responsable</span>
          <span>Registro central</span>
          <span>Acción</span>
        </div>
        <div className="academic-lifecycle__rows">
          {visibleAreas.map((area) => {
            const allowed = canOpen(area)
            return (
              <div className="academic-lifecycle__row" key={area.key}>
                <div className="academic-lifecycle__name">
                  <b>{area.number}</b>
                  <strong>{area.title}</strong>
                </div>
                <span>{area.owner}</span>
                <span className="academic-lifecycle__record">
                  {area.record}
                  <b>{area.result}</b>
                  <small className={`integration-state integration-state--${String(domainsByKey.get(area.key)?.status || 'checking').toLowerCase()}`}>
                    {domainLabel(domainsByKey.get(area.key))}
                  </small>
                </span>
                <button type="button" className="ghost-button" onClick={area.action} disabled={!allowed}>
                  {allowed ? area.actionLabel : 'Sin acceso'}
                </button>
              </div>
            )
          })}
        </div>
      </section>

      <section className="academic-system-controls">
        <div>
          <span>Identidad única</span>
          <strong>Estudiante, docente y administrativo</strong>
        </div>
        <div>
          <span>Expediente continuo</span>
          <strong>Admisión hasta titulación</strong>
        </div>
        <div>
          <span>Fuentes institucionales</span>
          <strong>
            {integrationLoading
              ? 'Verificando INTECBDD y complementos'
              : `${integration?.summary.available || 0} de ${integration?.summary.total || 0} disponibles`}
          </strong>
        </div>
        <div>
          <span>Permisos</span>
          <strong>Acceso condicionado por perfil</strong>
        </div>
      </section>

      <section className="academic-integration">
        <div className="academic-lifecycle__heading">
          <div>
            <span>Arquitectura de datos</span>
            <h2>INTECBDD y bases complementarias</h2>
          </div>
          <strong>
            {integrationLoading ? 'Consultando' : `${integration?.summary.available || 0} fuentes en línea`}
          </strong>
        </div>

        {integrationError ? <p className="form-error">{integrationError}</p> : null}
        <div className="academic-integration__header" aria-hidden="true">
          <span>Base de datos</span>
          <span>Responsabilidad</span>
          <span>Relación con INTECBDD</span>
          <span>Estado</span>
        </div>
        <div className="academic-integration__rows" aria-live="polite">
          {integrationLoading ? (
            <p className="academic-integration__empty">Verificando conexiones institucionales...</p>
          ) : (integration?.databases || []).map((database) => (
            <div className="academic-integration__row" key={database.key}>
              <div>
                <strong>{database.name}</strong>
                <small>
                  {database.primary
                    ? 'Base principal'
                    : database.kind === 'contract'
                      ? 'Contrato de integración'
                      : 'Base complementaria'}
                </small>
              </div>
              <span>{database.role}</span>
              <span>{database.relation}</span>
              <b className={`database-status database-status--${database.status.toLowerCase()}`}>
                {databaseLabel(database)}
              </b>
            </div>
          ))}
        </div>
        {!integrationLoading && databasesByKey.get('academic')?.available === false ? (
          <p className="form-error">INTECBDD no está disponible. Los procesos transaccionales deben permanecer bloqueados hasta restablecer la fuente maestra.</p>
        ) : null}
      </section>
    </section>
  )
}
