import { useEffect, useState, type FormEvent } from 'react'

import {
  fetchMoodleCourses,
  fetchMoodleStatus,
  fetchMoodleUsers,
  updateMoodleUserStatus,
} from '../../lib/api'
import type {
  MoodleCoursesResponse,
  MoodlePagination,
  MoodleSection,
  MoodleStatusResponse,
  MoodleUser,
  MoodleUsersResponse,
} from '../../types/app'
import { MoodleResourcesPanel } from './MoodleResourcesPanel'
import { MoodleEvaluationDatesPanel } from './MoodleEvaluationDatesPanel'
import { MoodleGradeSyncPanel } from './MoodleGradeSyncPanel'
import { MoodleGradeAlertsPanel } from './MoodleGradeAlertsPanel'

type MoodleViewProps = {
  displayName: string
  activeSection: MoodleSection
  availableSections: readonly MoodleSection[]
  onSectionChange: (section: MoodleSection) => void
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudo completar la consulta de Moodle.'
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatUnixDate(value: number): string {
  if (!value) return 'Sin registro'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value * 1000))
}

function formatIsoDate(value: string): string {
  if (!value) return 'Sin registro'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Sin registro'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function PaginationControls({
  pagination,
  disabled,
  onPage,
}: {
  pagination: MoodlePagination
  disabled: boolean
  onPage: (page: number) => void
}) {
  const currentPage = pagination.total_pages === 0 ? 1 : pagination.page
  const totalPages = Math.max(pagination.total_pages, 1)

  return (
    <div className="moodle-pagination" aria-label="Paginación">
      <span>
        Página {currentPage} de {totalPages}
      </span>
      <div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={disabled || !pagination.has_previous}
          onClick={() => onPage(pagination.page - 1)}
        >
          Anterior
        </button>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={disabled || !pagination.has_next}
          onClick={() => onPage(pagination.page + 1)}
        >
          Siguiente
        </button>
      </div>
    </div>
  )
}

export function MoodleView({
  displayName,
  activeSection,
  availableSections,
  onSectionChange,
}: MoodleViewProps) {
  const activeTab = activeSection
  const [statusData, setStatusData] = useState<MoodleStatusResponse | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState('')

  const [usersData, setUsersData] = useState<MoodleUsersResponse | null>(null)
  const [usersLoading, setUsersLoading] = useState(false)
  const [usersError, setUsersError] = useState('')
  const [usersSuccess, setUsersSuccess] = useState('')
  const [userMode, setUserMode] = useState<'status' | 'directory'>('status')
  const [userEmail, setUserEmail] = useState('')
  const [userState, setUserState] = useState<'all' | 'active' | 'suspended' | 'unconfirmed'>('all')
  const [userPageSize, setUserPageSize] = useState(50)
  const [pendingStatusChange, setPendingStatusChange] = useState<{
    user: MoodleUser
    active: boolean
  } | null>(null)
  const [statusChangeLoading, setStatusChangeLoading] = useState(false)

  const [coursesData, setCoursesData] = useState<MoodleCoursesResponse | null>(null)
  const [coursesLoading, setCoursesLoading] = useState(false)
  const [coursesError, setCoursesError] = useState('')
  const [courseSearch, setCourseSearch] = useState('')
  const [courseVisibility, setCourseVisibility] = useState<'all' | 'visible' | 'hidden'>('all')
  const [courseCategory, setCourseCategory] = useState('')
  const [coursePageSize, setCoursePageSize] = useState(50)
  const [resourceCourseId, setResourceCourseId] = useState(0)

  const loadStatus = async () => {
    setStatusLoading(true)
    setStatusError('')
    try {
      setStatusData(await fetchMoodleStatus())
    } catch (error) {
      setStatusData(null)
      setStatusError(errorMessage(error))
    } finally {
      setStatusLoading(false)
    }
  }

  const loadUsers = async (page = 1, refresh = false) => {
    setUsersLoading(true)
    setUsersError('')
    setUsersSuccess('')
    try {
      setUsersData(await fetchMoodleUsers({
        page,
        pageSize: userPageSize,
        email: userEmail,
        state: userState,
        refresh,
      }))
    } catch (error) {
      setUsersError(errorMessage(error))
    } finally {
      setUsersLoading(false)
    }
  }

  const loadCourses = async (page = 1, refresh = false) => {
    setCoursesLoading(true)
    setCoursesError('')
    try {
      const categoryId = courseCategory.trim() === '' ? null : Number(courseCategory)
      setCoursesData(await fetchMoodleCourses({
        page,
        pageSize: coursePageSize,
        search: courseSearch,
        visibility: courseVisibility,
        categoryId: typeof categoryId === 'number' && Number.isFinite(categoryId) ? categoryId : null,
        refresh,
      }))
    } catch (error) {
      setCoursesError(errorMessage(error))
    } finally {
      setCoursesLoading(false)
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (activeSection === 'status' && !statusData && !statusLoading) void loadStatus()
      if (activeSection === 'users') {
        if (!statusData && !statusLoading) void loadStatus()
        if (userMode === 'directory' && !usersData && !usersLoading) void loadUsers()
      }
      if (activeSection === 'courses' && !coursesData && !coursesLoading) void loadCourses()
    }, 0)

    return () => window.clearTimeout(timeoutId)
    // La sección es controlada por la navegación y cada consulta conserva sus filtros locales.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, userMode])

  useEffect(() => {
    if (!usersSuccess) return undefined
    const timeoutId = window.setTimeout(() => setUsersSuccess(''), 3000)
    return () => window.clearTimeout(timeoutId)
  }, [usersSuccess])

  const selectTab = (tab: MoodleSection) => {
    onSectionChange(tab)
  }

  const submitUsers = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (userMode === 'status' && !userEmail.trim()) {
      setUsersError('Ingrese el correo electrónico de la cuenta que desea administrar.')
      setUsersSuccess('')
      setUsersData(null)
      return
    }
    void loadUsers(1)
  }

  const selectUserMode = (mode: 'status' | 'directory') => {
    setUserMode(mode)
    setUsersError('')
    setUsersSuccess('')
    setUsersData(null)
  }

  const submitCourses = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void loadCourses(1)
  }

  const confirmStatusChange = async () => {
    if (!pendingStatusChange) return

    setStatusChangeLoading(true)
    setUsersError('')
    setUsersSuccess('')
    try {
      const result = await updateMoodleUserStatus(
        pendingStatusChange.user.id,
        pendingStatusChange.active,
      )
      setUsersData((current) => current
        ? {
          ...current,
          items: current.items.map((user) => user.id === result.user.id ? result.user : user),
        }
        : current)
      setUsersSuccess(
        `${result.message} Correo validado en INTECBDD: ${result.institutional_validation.correo_intec}.`,
      )
      setPendingStatusChange(null)
    } catch (error) {
      setUsersError(errorMessage(error))
    } finally {
      setStatusChangeLoading(false)
    }
  }

  const requiredFunctions = statusData?.required_functions ?? []
  const missingRequiredFunctions = statusData?.missing_required_functions ?? []
  const statusFunctionAvailable = !missingRequiredFunctions.includes('core_user_update_users')
  const canManageUserStatus = Boolean(
    statusData?.user_status_updates_enabled && statusFunctionAvailable,
  )

  return (
    <section className="moodle-page">
      <header className="moodle-header">
        <div>
          <span className="moodle-eyebrow">Integración académica</span>
          <h1>Moodle</h1>
          <p>Consulte cursos, recursos académicos, estado del servicio y usuarios disponibles.</p>
        </div>
        <div className="moodle-operator">
          <strong>{displayName || 'Usuario administrativo'}</strong>
          <span>
            {activeTab === 'users'
              ? 'Consulta y control de cuentas'
              : activeTab === 'alerts'
                ? 'Seguimiento de calificaciones'
                : activeTab === 'evaluation-dates'
                  ? 'Programación de evaluaciones'
                : 'Consulta administrativa'}
          </span>
        </div>
      </header>

      <nav className="moodle-tabs" aria-label="Secciones de Moodle">
        {availableSections.includes('alerts') && (
          <button
            type="button"
            className={activeTab === 'alerts' ? 'is-active' : ''}
            onClick={() => selectTab('alerts')}
          >
            Alertas de calificación
          </button>
        )}
        {availableSections.includes('courses') && (
          <button
            type="button"
            className={activeTab === 'courses' ? 'is-active' : ''}
            onClick={() => selectTab('courses')}
          >
            Cursos
          </button>
        )}
        {availableSections.includes('status') && (
          <button
            type="button"
            className={activeTab === 'status' ? 'is-active' : ''}
            onClick={() => selectTab('status')}
          >
            Estado
          </button>
        )}
        {availableSections.includes('evaluation-dates') && (
          <button
            type="button"
            className={activeTab === 'evaluation-dates' ? 'is-active' : ''}
            onClick={() => selectTab('evaluation-dates')}
          >
            Fechas de evaluaciones
          </button>
        )}
        {availableSections.includes('resources') && (
          <button
            type="button"
            className={activeTab === 'resources' ? 'is-active' : ''}
            onClick={() => selectTab('resources')}
          >
            Recursos por curso
          </button>
        )}
        {availableSections.includes('grades') && (
          <button
            type="button"
            className={activeTab === 'grades' ? 'is-active' : ''}
            onClick={() => selectTab('grades')}
          >
            Migración de notas
          </button>
        )}
        {availableSections.includes('users') && (
          <button
            type="button"
            className={activeTab === 'users' ? 'is-active' : ''}
            onClick={() => selectTab('users')}
          >
            Usuarios
          </button>
        )}
      </nav>

      {activeTab === 'alerts' && <MoodleGradeAlertsPanel />}

      {activeTab === 'status' && (
        <div className="moodle-section">
          <div className="moodle-section__heading">
            <div>
              <span>Conectividad</span>
              <h2>Estado de la integración</h2>
            </div>
            <button
              type="button"
              className="moodle-button moodle-button--primary"
              disabled={statusLoading}
              onClick={() => void loadStatus()}
            >
              {statusLoading ? 'Consultando...' : 'Actualizar estado'}
            </button>
          </div>

          {statusError && <div className="moodle-alert moodle-alert--error">{statusError}</div>}
          {!statusData && !statusError && statusLoading && (
            <div className="moodle-empty">Consultando la configuración autorizada de Moodle...</div>
          )}

          {statusData && (
            <>
              <div className="moodle-status-grid">
                <div>
                  <span>Servicio</span>
                  <strong>{statusData.reachable ? 'Disponible' : 'No disponible'}</strong>
                </div>
                <div>
                  <span>Configuración</span>
                  <strong>{statusData.configured ? 'Completa' : 'Pendiente'}</strong>
                </div>
                <div>
                  <span>Funciones publicadas</span>
                  <strong>{formatNumber(statusData.functions_count)}</strong>
                </div>
                <div>
                  <span>Administrador del sitio</span>
                  <strong>{statusData.user_is_site_admin ? 'Sí' : 'No'}</strong>
                </div>
              </div>

              <div className="moodle-detail-grid">
                <div><span>Sitio</span><strong>{statusData.site_name || 'Sin nombre'}</strong></div>
                <div><span>Dirección</span><strong>{statusData.site_url || 'No informada'}</strong></div>
                <div><span>Usuario técnico</span><strong>{statusData.moodle_username || 'No informado'}</strong></div>
                <div><span>Versión</span><strong>{statusData.moodle_release || statusData.moodle_version || 'No informada'}</strong></div>
              </div>

              <div className="moodle-functions">
                <h3>Funciones requeridas</h3>
                {requiredFunctions.map((functionName) => {
                  const missing = missingRequiredFunctions.includes(functionName)
                  return (
                    <div key={functionName}>
                      <code>{functionName}</code>
                      <span className={`moodle-badge ${missing ? 'moodle-badge--danger' : 'moodle-badge--success'}`}>
                        {missing ? 'No disponible' : 'Disponible'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'users' && (
        <div className="moodle-section">
          <div className="moodle-section__heading">
            <div>
              <span>Control de cuentas</span>
              <h2>Usuarios de Moodle</h2>
            </div>
            {userMode === 'directory' && (
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={usersLoading}
                onClick={() => void loadUsers(usersData?.pagination.page ?? 1, true)}
              >
                Actualizar directorio
              </button>
            )}
          </div>

          <div className="moodle-user-modes" role="tablist" aria-label="Modo de gestión de usuarios">
            <button
              type="button"
              role="tab"
              aria-selected={userMode === 'status'}
              className={userMode === 'status' ? 'is-active' : ''}
              onClick={() => selectUserMode('status')}
            >
              Activar o inactivar
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={userMode === 'directory'}
              className={userMode === 'directory' ? 'is-active' : ''}
              onClick={() => selectUserMode('directory')}
            >
              Directorio completo
            </button>
          </div>

          {userMode === 'status' ? (
            <>
              <form className="moodle-account-search" onSubmit={submitUsers}>
                <label>
                  <span>Correo electrónico institucional</span>
                  <input
                    type="email"
                    inputMode="email"
                    autoComplete="off"
                    value={userEmail}
                    onChange={(event) => setUserEmail(event.target.value)}
                    placeholder="estudiante@intec.edu.ec"
                    required
                  />
                </label>
                <button type="submit" className="moodle-button moodle-button--primary" disabled={usersLoading}>
                  {usersLoading ? 'Buscando...' : 'Buscar cuenta'}
                </button>
              </form>
              <div className="moodle-account-notice">
                <strong>Validación institucional obligatoria</strong>
                <span>
                  El sistema comprueba el correo en CorreosEstudIntec y su relación con DATOS_ESTUD antes de
                  activar o inactivar la cuenta en Moodle.
                </span>
              </div>
            </>
          ) : (
            <form className="moodle-filters moodle-filters--users" onSubmit={submitUsers}>
              <label>
                <span>Correo electrónico</span>
                <input
                  type="search"
                  inputMode="email"
                  value={userEmail}
                  onChange={(event) => setUserEmail(event.target.value)}
                  placeholder="Filtrar por correo electrónico"
                />
              </label>
              <label>
                <span>Estado</span>
                <select value={userState} onChange={(event) => setUserState(event.target.value as typeof userState)}>
                  <option value="all">Todos</option>
                  <option value="active">Activos</option>
                  <option value="suspended">Inactivos</option>
                  <option value="unconfirmed">No confirmados</option>
                </select>
              </label>
              <label>
                <span>Registros</span>
                <select value={userPageSize} onChange={(event) => setUserPageSize(Number(event.target.value))}>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
              </label>
              <button type="submit" className="moodle-button moodle-button--primary" disabled={usersLoading}>
                {usersLoading ? 'Consultando...' : 'Consultar'}
              </button>
            </form>
          )}

          {usersError && <div className="moodle-alert moodle-alert--error">{usersError}</div>}
          {statusData && !canManageUserStatus && (
            <div className="moodle-alert moodle-alert--warning">
              La consulta está disponible, pero el control de estado requiere habilitar la operación y publicar
              <code>core_user_update_users</code> en el servicio de Moodle.
            </div>
          )}
          {usersData && userMode === 'status' && (
            <div className="moodle-account-results" aria-live="polite">
              <div className="moodle-results-summary">
                <strong>{formatNumber(usersData.pagination.total_items)} cuenta(s) encontrada(s)</strong>
                <span>{usersData.source.cached ? 'Caché vigente' : 'Consulta actualizada'}</span>
              </div>
              {usersData.items.map((user) => (
                <article className="moodle-account-row" key={user.id}>
                  <div className="moodle-account-row__identity">
                    <span>Cuenta Moodle</span>
                    <strong>{user.fullname || user.username || 'Sin nombre'}</strong>
                    <small>{user.email || 'Sin correo institucional'}</small>
                  </div>
                  <div className="moodle-account-row__detail">
                    <span>Usuario</span>
                    <strong>{user.username || 'Sin usuario'}</strong>
                    <small>ID Moodle {user.id}</small>
                  </div>
                  <div className="moodle-account-row__detail">
                    <span>Identificación</span>
                    <strong>{user.idnumber || 'Sin registro'}</strong>
                    <small>{user.institution || 'Institución no informada'}</small>
                  </div>
                  <div className="moodle-account-row__state">
                    <span>Estado actual</span>
                    <span className={`moodle-badge moodle-badge--${user.status.toLowerCase().replace('_', '-')}`}>
                      {user.status === 'NO_CONFIRMADO'
                        ? 'No confirmado'
                        : user.suspended
                          ? 'Inactivo'
                          : 'Activo'}
                    </span>
                  </div>
                  <div className="moodle-account-row__action">
                    {user.status === 'NO_CONFIRMADO' ? (
                      <span className="moodle-user-action__unavailable">Cambio no disponible</span>
                    ) : (
                      <button
                        type="button"
                        className={`moodle-button ${user.suspended ? 'moodle-button--success' : 'moodle-button--danger'}`}
                        disabled={!canManageUserStatus || statusChangeLoading}
                        title={!canManageUserStatus ? 'El control de estado no está habilitado.' : undefined}
                        onClick={() => {
                          setUsersError('')
                          setUsersSuccess('')
                          setPendingStatusChange({ user, active: user.suspended })
                        }}
                      >
                        {user.suspended ? 'Activar cuenta' : 'Inactivar cuenta'}
                      </button>
                    )}
                  </div>
                </article>
              ))}
              {usersData.items.length === 0 && (
                <div className="moodle-empty">No se encontró una cuenta de Moodle con ese correo.</div>
              )}
            </div>
          )}

          {usersData && userMode === 'directory' && (
            <>
              <div className="moodle-results-summary">
                <strong>{formatNumber(usersData.pagination.total_items)} usuario(s)</strong>
                <span>
                  {usersData.source.cached ? 'Caché vigente' : 'Consulta actualizada'} · {formatIsoDate(usersData.source.fetched_at)}
                </span>
              </div>
              <div className="moodle-table-wrap">
                <table className="moodle-table">
                  <thead>
                    <tr>
                      <th>Usuario</th>
                      <th>Nombre</th>
                      <th>Correo</th>
                      <th>Identificación</th>
                      <th>Institución y unidad</th>
                      <th>Autenticación</th>
                      <th>Último acceso</th>
                      <th>Estado</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersData.items.map((user) => (
                      <tr key={user.id}>
                        <td><strong>{user.username || 'Sin usuario'}</strong><small>ID {user.id}</small></td>
                        <td>{user.fullname || 'Sin nombre'}</td>
                        <td>{user.email || 'Sin correo'}</td>
                        <td>{user.idnumber || 'Sin registro'}</td>
                        <td><strong>{user.institution || 'Sin institución'}</strong><small>{user.department || 'Sin unidad'}</small></td>
                        <td>{user.auth || 'No informada'}</td>
                        <td>{formatUnixDate(user.lastaccess)}</td>
                        <td>
                          <span className={`moodle-badge moodle-badge--${user.status.toLowerCase().replace('_', '-')}`}>
                            {user.status === 'NO_CONFIRMADO'
                              ? 'No confirmado'
                              : user.suspended
                                ? 'Inactivo'
                                : 'Activo'}
                          </span>
                        </td>
                        <td>
                          {user.status === 'NO_CONFIRMADO' ? (
                            <span className="moodle-user-action__unavailable">No disponible</span>
                          ) : (
                            <button
                              type="button"
                              className={`moodle-button moodle-user-action ${user.suspended ? 'moodle-button--success' : 'moodle-button--danger'}`}
                              disabled={!canManageUserStatus || statusChangeLoading}
                              title={!canManageUserStatus ? 'El control de estado no está habilitado.' : undefined}
                              onClick={() => {
                                setUsersError('')
                                setUsersSuccess('')
                                setPendingStatusChange({ user, active: user.suspended })
                              }}
                            >
                              {user.suspended ? 'Activar' : 'Inactivar'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {usersData.items.length === 0 && (
                      <tr><td colSpan={9} className="moodle-table__empty">No existen usuarios con los filtros actuales.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <PaginationControls
                pagination={usersData.pagination}
                disabled={usersLoading}
                onPage={(page) => void loadUsers(page)}
              />
            </>
          )}
        </div>
      )}

      {activeTab === 'courses' && (
        <div className="moodle-section">
          <div className="moodle-section__heading">
            <div>
              <span>Oferta virtual</span>
              <h2>Cursos de Moodle</h2>
            </div>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={coursesLoading}
              onClick={() => void loadCourses(coursesData?.pagination.page ?? 1, true)}
            >
              Actualizar catálogo
            </button>
          </div>

          <form className="moodle-filters moodle-filters--courses" onSubmit={submitCourses}>
            <label>
              <span>Buscar</span>
              <input
                value={courseSearch}
                onChange={(event) => setCourseSearch(event.target.value)}
                placeholder="Curso, nombre corto, código o categoría"
              />
            </label>
            <label>
              <span>Visibilidad</span>
              <select value={courseVisibility} onChange={(event) => setCourseVisibility(event.target.value as typeof courseVisibility)}>
                <option value="all">Todos</option>
                <option value="visible">Visibles</option>
                <option value="hidden">Ocultos</option>
              </select>
            </label>
            <label>
              <span>Categoría</span>
              <input
                type="number"
                min="0"
                value={courseCategory}
                onChange={(event) => setCourseCategory(event.target.value)}
                placeholder="ID opcional"
              />
            </label>
            <label>
              <span>Registros</span>
              <select value={coursePageSize} onChange={(event) => setCoursePageSize(Number(event.target.value))}>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </select>
            </label>
            <button type="submit" className="moodle-button moodle-button--primary" disabled={coursesLoading}>
              {coursesLoading ? 'Consultando...' : 'Consultar'}
            </button>
          </form>

          {coursesError && <div className="moodle-alert moodle-alert--error">{coursesError}</div>}
          {coursesData && (
            <>
              <div className="moodle-results-summary">
                <strong>{formatNumber(coursesData.pagination.total_items)} curso(s)</strong>
                <span>
                  {coursesData.source.cached ? 'Caché vigente' : 'Consulta actualizada'} · {formatIsoDate(coursesData.source.fetched_at)}
                </span>
              </div>
              <div className="moodle-table-wrap">
                <table className="moodle-table moodle-table--courses">
                  <thead>
                    <tr>
                      <th>Curso</th>
                      <th>Nombre corto y código</th>
                      <th>Categoría</th>
                      <th>Visibilidad</th>
                      <th>Inicio y fin</th>
                      <th>Finalización</th>
                      <th>Última modificación</th>
                      {availableSections.includes('resources') && <th>Acción</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {coursesData.items.map((course) => (
                      <tr key={course.id}>
                        <td>
                          <strong>{course.displayname || course.fullname || 'Curso sin nombre'}</strong>
                          <small>{course.summary || 'Sin resumen'}</small>
                        </td>
                        <td><strong>{course.shortname || 'Sin nombre corto'}</strong><small>{course.idnumber || `ID ${course.id}`}</small></td>
                        <td><strong>{course.categoryname || 'Sin categoría'}</strong><small>ID {course.categoryid}</small></td>
                        <td><span className={`moodle-badge ${course.visible ? 'moodle-badge--success' : 'moodle-badge--warning'}`}>{course.visible ? 'Visible' : 'Oculto'}</span></td>
                        <td><strong>{formatUnixDate(course.startdate)}</strong><small>{formatUnixDate(course.enddate)}</small></td>
                        <td>{course.enablecompletion ? 'Habilitada' : 'No habilitada'}</td>
                        <td>{formatUnixDate(course.timemodified)}</td>
                        {availableSections.includes('resources') && (
                          <td>
                            <button
                              type="button"
                              className="moodle-button moodle-button--secondary"
                              onClick={() => {
                                setResourceCourseId(course.id)
                                selectTab('resources')
                              }}
                            >
                              Ver recursos
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                    {coursesData.items.length === 0 && (
                      <tr>
                        <td
                          colSpan={availableSections.includes('resources') ? 8 : 7}
                          className="moodle-table__empty"
                        >
                          No existen cursos con los filtros actuales.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <PaginationControls
                pagination={coursesData.pagination}
                disabled={coursesLoading}
                onPage={(page) => void loadCourses(page)}
              />
            </>
          )}
        </div>
      )}

      {activeTab === 'resources' && (
        <MoodleResourcesPanel initialCourseId={resourceCourseId} />
      )}

      {activeTab === 'evaluation-dates' && <MoodleEvaluationDatesPanel />}

      {activeTab === 'grades' && <MoodleGradeSyncPanel />}

      {usersSuccess && (
        <div className="institutional-email-notification-overlay" role="presentation">
          <section
            className="institutional-email-notification"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="institutional-email-notification__mark" aria-hidden="true">✓</span>
            <div>
              <p className="eyebrow">Proceso completado</p>
              <h3>{usersSuccess}</h3>
              <small>Esta ventana se cerrará automáticamente en 3 segundos.</small>
            </div>
            <span className="institutional-email-notification__timer" aria-hidden="true" />
          </section>
        </div>
      )}

      {pendingStatusChange && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !statusChangeLoading) setPendingStatusChange(null)
          }}
        >
          <div
            className="moodle-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-status-dialog-title"
          >
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Control de cuenta</span>
                <h2 id="moodle-status-dialog-title">
                  {pendingStatusChange.active ? 'Activar usuario' : 'Inactivar usuario'}
                </h2>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={statusChangeLoading}
                onClick={() => setPendingStatusChange(null)}
              >
                Cerrar
              </button>
            </div>

            <div className="moodle-confirm-dialog__body">
              <p>
                Confirme el cambio de estado para la cuenta seleccionada. Antes de aplicarlo, el sistema validará
                que el correo institucional exista en <strong>INTECBDD</strong>.
              </p>
              <dl className="moodle-confirm-dialog__details">
                <div><dt>Usuario</dt><dd>{pendingStatusChange.user.fullname || pendingStatusChange.user.username}</dd></div>
                <div><dt>Correo</dt><dd>{pendingStatusChange.user.email || 'Sin correo registrado'}</dd></div>
                <div><dt>Estado actual</dt><dd>{pendingStatusChange.user.suspended ? 'Suspendido' : 'Activo'}</dd></div>
                <div><dt>Nuevo estado</dt><dd>{pendingStatusChange.active ? 'Activo' : 'Suspendido'}</dd></div>
              </dl>
            </div>

            <div className="moodle-confirm-dialog__actions">
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={statusChangeLoading}
                onClick={() => setPendingStatusChange(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className={`moodle-button ${pendingStatusChange.active ? 'moodle-button--success' : 'moodle-button--danger'}`}
                disabled={statusChangeLoading}
                onClick={() => void confirmStatusChange()}
              >
                {statusChangeLoading
                  ? 'Procesando...'
                  : pendingStatusChange.active
                    ? 'Confirmar activación'
                    : 'Confirmar inactivación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
