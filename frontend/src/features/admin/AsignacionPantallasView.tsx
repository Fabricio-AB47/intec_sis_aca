import { useMemo, useState } from 'react'

import type { Page, Role } from '../../types/app'

type ScreenOption = {
  page: Page
  label: string
  description: string
  group: string
}

const STORAGE_KEY = 'intec:user-type-screen-access:v1'

const roleOptions: Array<{ value: Role; label: string; description: string }> = [
  { value: 'ADMINISTRADOR', label: 'Administrador', description: 'Acceso total y configuración.' },
  { value: 'ACADEMICO', label: 'Académico', description: 'Matrícula, estudiantes, notas y titulación.' },
  { value: 'ADMISIONES', label: 'Admisiones', description: 'Inscripción, aspirantes y matrícula inicial.' },
  { value: 'FINANCIERO', label: 'Financiero', description: 'Pagos, convenios e ingresos.' },
  { value: 'SECRETARIA', label: 'Secretaría', description: 'Prácticas, grado, titulación y registros.' },
  { value: 'DOCENTE', label: 'Docente', description: 'Portal docente y documentos propios.' },
  { value: 'ESTUDIANTE', label: 'Estudiante', description: 'Portal estudiante, evaluación y prácticas.' },
  { value: 'SOPORTE', label: 'Soporte', description: 'Soporte técnico y operación extendida.' },
  { value: 'RECTOR', label: 'Rector', description: 'Consulta ejecutiva.' },
  { value: 'VICERRECTOR', label: 'Vicerrector', description: 'Consulta ejecutiva y seguimiento.' },
]

const screens: ScreenOption[] = [
  { page: 'dashboard', label: 'Dashboard', description: 'Indicadores generales.', group: 'Inicio' },
  { page: 'sistema-academico', label: 'Sistema académico', description: 'Ciclo institucional integrado.', group: 'Inicio' },
  { page: 'preinscripcion', label: 'Preinscripción', description: 'Registro de aspirantes y documentos.', group: 'Admisión' },
  { page: 'actualizar-datos-estudiante', label: 'Actualizar datos', description: 'Datos de estudiantes y docentes.', group: 'Personas' },
  { page: 'matricula-acad', label: 'Matrícula académica', description: 'Cabecera, materias y control académico.', group: 'Matrícula' },
  { page: 'matricula-docente', label: 'Matrícula docente', description: 'Asignación docente por materia.', group: 'Docencia' },
  { page: 'gestion-sisacademico', label: 'Gestión SisAcademicoV1', description: 'Módulos clonados y tablas operativas.', group: 'Operativo' },
  { page: 'sisacademico-v1', label: 'Mapa SisAcademicoV1', description: 'Inventario y clonación funcional.', group: 'Operativo' },
  { page: 'periodo-academico', label: 'Periodo académico', description: 'Resumen por periodo y estudiantes.', group: 'Académico' },
  { page: 'reporteria-integral', label: 'Reportería integral', description: 'Reportes modernos reemplazando Crystal.', group: 'Reportes' },
  { page: 'reportes-individuales', label: 'Reportes individuales', description: 'Notas y reportes por estudiante.', group: 'Reportes' },
  { page: 'certificados', label: 'Certificados', description: 'Emisión y consulta de certificados.', group: 'Documentos' },
  { page: 'fecha-grado', label: 'Fecha de grado', description: 'Registro de grado por carrera y periodo.', group: 'Titulación' },
  { page: 'practicas-institucionales', label: 'Prácticas institucionales', description: 'Prácticas y vinculación con la sociedad.', group: 'Prácticas' },
  { page: 'titulacion', label: 'Verificación de titulación', description: 'Requisitos previos y modalidad.', group: 'Titulación' },
  { page: 'titulacion-proceso', label: 'Proceso de titulación', description: 'Complexivo, defensa, fechas y enlaces.', group: 'Titulación' },
  { page: 'titulacion-responsables', label: 'Registro de responsables', description: 'Tribunal y responsables de complexivo.', group: 'Titulación' },
  { page: 'titulos-registrados', label: 'Títulos registrados', description: 'SENESCYT e INTEC.', group: 'Titulación' },
  { page: 'senescyt-estudiantes', label: 'SENESCYT estudiantes', description: 'Reportes regulatorios.', group: 'Reportes' },
  { page: 'correos-masivos', label: 'Correos masivos', description: 'Envíos institucionales.', group: 'Comunicación' },
  { page: 'carnet-institucional', label: 'Carnet institucional', description: 'Foto y carnet de usuarios.', group: 'Comunicación' },
  { page: 'portal-estudiante', label: 'Portal estudiante', description: 'Malla, notas y estado del estudiante.', group: 'Portales' },
  { page: 'portal-docente', label: 'Portal docente', description: 'Cursos, notas e informes docentes.', group: 'Portales' },
  { page: 'portal-docente-informe', label: 'Informe docente', description: 'Informe de cumplimiento docente.', group: 'Portales' },
  { page: 'portal-docente-planificacion', label: 'Sílabo y PEA', description: 'Planificación académica docente.', group: 'Portales' },
  { page: 'portal-docente-contratos', label: 'Contrato docente', description: 'Condiciones contractuales y carga asignada.', group: 'Portales' },
  { page: 'evaluacion-docente', label: 'Evaluación docente', description: 'Formulario de evaluación.', group: 'Evaluación' },
  { page: 'evaluacion-docente-avance', label: 'Avance evaluación', description: 'Seguimiento de evaluación docente.', group: 'Evaluación' },
  { page: 'evaluacion-docente-reportes', label: 'Reportes evaluación', description: 'PDF y reportes de evaluación.', group: 'Evaluación' },
]

const defaultAccess: Partial<Record<Role, Page[]>> = {
  ADMINISTRADOR: screens.map((screen) => screen.page),
  SOPORTE: screens.map((screen) => screen.page).filter((page) => page !== 'portal-estudiante' && page !== 'portal-docente'),
  ACADEMICO: [
    'dashboard',
    'sistema-academico',
    'matricula-acad',
    'matricula-docente',
    'actualizar-datos-estudiante',
    'gestion-sisacademico',
    'sisacademico-v1',
    'reportes-individuales',
    'certificados',
    'fecha-grado',
    'practicas-institucionales',
    'titulacion',
    'titulacion-proceso',
    'titulacion-responsables',
  ],
  ADMISIONES: ['dashboard', 'sistema-academico', 'preinscripcion', 'gestion-sisacademico', 'sisacademico-v1'],
  FINANCIERO: ['dashboard', 'sistema-academico', 'preinscripcion', 'gestion-sisacademico', 'ingreso-ventas' as Page, 'reporteria-integral'],
  SECRETARIA: ['sistema-academico', 'practicas-institucionales', 'fecha-grado', 'senescyt-estudiantes', 'titulacion', 'titulacion-proceso', 'titulacion-responsables', 'titulos-registrados'],
  DOCENTE: ['portal-docente', 'portal-docente-informe', 'portal-docente-planificacion', 'portal-docente-contratos', 'carnet-institucional'],
  ESTUDIANTE: ['portal-estudiante', 'evaluacion-docente', 'practicas-institucionales', 'carnet-institucional'],
  RECTOR: ['dashboard'],
  VICERRECTOR: ['dashboard'],
}

function loadAssignments(): Partial<Record<Role, Page[]>> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveAssignments(assignments: Partial<Record<Role, Page[]>>) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(assignments))
  window.dispatchEvent(new CustomEvent('intec-screen-access-updated'))
}

export function AsignacionPantallasView({ displayName }: Readonly<{ displayName: string }>) {
  const [selectedRole, setSelectedRole] = useState<Role | null>(null)
  const [assignments, setAssignments] = useState<Partial<Record<Role, Page[]>>>(() => loadAssignments())
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  const activeRole = selectedRole || 'ACADEMICO'
  const selectedPages = assignments[activeRole] || defaultAccess[activeRole] || []
  const selectedSet = new Set(selectedPages)
  const groupedScreens = useMemo(() => {
    const groups = new Map<string, ScreenOption[]>()
    screens.forEach((screen) => {
      groups.set(screen.group, [...(groups.get(screen.group) || []), screen])
    })
    return Array.from(groups.entries())
  }, [])
  const filteredRoles = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return roleOptions
    return roleOptions.filter((role) =>
      `${role.label} ${role.value} ${role.description}`.toLowerCase().includes(needle),
    )
  }, [query])

  const selectedRoleMeta = roleOptions.find((role) => role.value === activeRole)

  function togglePage(page: Page) {
    if (!selectedRole) return
    setAssignments((current) => {
      const currentPages = new Set(current[selectedRole] || defaultAccess[selectedRole] || [])
      if (currentPages.has(page)) currentPages.delete(page)
      else currentPages.add(page)
      return { ...current, [selectedRole]: Array.from(currentPages) }
    })
    setMessage('')
  }

  function applyPreset() {
    if (!selectedRole) return
    setAssignments((current) => ({ ...current, [selectedRole]: defaultAccess[selectedRole] || [] }))
    setMessage('Se cargó la configuración recomendada para el tipo de usuario.')
  }

  function clearRole() {
    if (!selectedRole) return
    setAssignments((current) => ({ ...current, [selectedRole]: [] }))
    setMessage('Se desmarcaron todas las pantallas del tipo de usuario.')
  }

  function save() {
    saveAssignments(assignments)
    setMessage(`Pantallas guardadas para ${selectedRoleMeta?.label || selectedRole}.`)
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Administración</p>
          <h1>Asignación de pantallas</h1>
          <p>{displayName} · Defina qué pantallas puede utilizar cada tipo de usuario.</p>
        </div>
      </header>

      <div className="titulacion-simple-tabs senescyt-update-tabs" role="tablist" aria-label="Asignación de accesos">
        <button type="button" className="is-active">Tipos de usuario</button>
        <button type="button" disabled>Pantallas asignadas</button>
      </div>

      <section className="student-grid student-grid--content senescyt-update-grid">
        <article className="student-card senescyt-update-search">
          <div className="card-head">
            <h3>Seleccionar tipo de usuario</h3>
            <span>{filteredRoles.length} resultado(s)</span>
          </div>

          <form
            className="senescyt-update-search-form"
            onSubmit={(event) => {
              event.preventDefault()
            }}
          >
            <label>
              Buscar perfil
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Administrador, académico, docente..." />
            </label>
            <button type="button" onClick={() => setQuery('')}>Limpiar</button>
          </form>

          {message ? <p className="form-success">{message}</p> : null}

          <div className="senescyt-student-list">
            {filteredRoles.map((role) => {
              const configuredPages = assignments[role.value] || defaultAccess[role.value] || []
              return (
            <button
              key={role.value}
              type="button"
                  className={`senescyt-student-option ${selectedRole === role.value ? 'senescyt-student-option--active' : ''}`}
              onClick={() => {
                setSelectedRole(role.value)
                setMessage('')
              }}
            >
              <strong>{role.label}</strong>
              <span>{role.description}</span>
                  <small>{configuredPages.length} pantalla(s) asignada(s) · Abrir subpantalla</small>
            </button>
              )
            })}
          </div>
        </article>
      </section>

      {selectedRole ? (
        <div className="senescyt-update-subscreen-backdrop" role="presentation">
          <section className="senescyt-update-subscreen screen-access-subscreen" role="dialog" aria-modal="true" aria-label="Subpantalla de asignación de pantallas">
            <div className="senescyt-update-subscreen__head">
              <div>
                <span>Asignación por tipo de usuario</span>
                <h2>{selectedRoleMeta?.label || selectedRole}</h2>
              </div>
              <div className="senescyt-update-subscreen__actions">
                <span>{selectedPages.length} pantalla(s)</span>
                <button type="button" onClick={() => setSelectedRole(null)}>Cerrar</button>
              </div>
            </div>

            <div className="matricula-acad-preview senescyt-update-summary">
              <div>
                <span>Perfil</span>
                <strong>{selectedRole}</strong>
              </div>
              <div>
                <span>Descripción</span>
                <strong>{selectedRoleMeta?.description || '-'}</strong>
              </div>
              <div>
                <span>Pantallas</span>
                <strong>{selectedPages.length} / {screens.length}</strong>
              </div>
              <div>
                <span>Modo</span>
                <strong>{assignments[selectedRole] ? 'Personalizado' : 'Recomendado'}</strong>
              </div>
            </div>

          <div className="screen-access-actions">
            <button type="button" onClick={applyPreset}>Cargar recomendado</button>
            <button type="button" onClick={clearRole}>Limpiar selección</button>
            <button type="button" className="primary-action" onClick={save}>Guardar asignación</button>
          </div>

          {message ? <div className="status-message status-message--success">{message}</div> : null}

          <div className="screen-access-groups">
            {groupedScreens.map(([group, items]) => (
              <section key={group} className="screen-access-group">
                <h4>{group}</h4>
                <div className="screen-access-grid">
                  {items.map((screen) => (
                    <label key={screen.page} className={selectedSet.has(screen.page) ? 'screen-access-item screen-access-item--checked' : 'screen-access-item'}>
                      <input
                        type="checkbox"
                        checked={selectedSet.has(screen.page)}
                        onChange={() => togglePage(screen.page)}
                      />
                      <span>
                        <strong>{screen.label}</strong>
                        <small>{screen.description}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </section>
            ))}
          </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
