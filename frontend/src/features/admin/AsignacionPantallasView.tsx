import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, fetchScreenAccessAssignments, updateScreenAccessAssignment } from '../../lib/api'
import type { Role, ScreenAccessResponse, ScreenAccessRole, ScreenPermissionCode } from '../../types/app'


type AccessTab = 'roles' | 'summary'
type AssignmentMap = Partial<Record<Role, ScreenPermissionCode[]>>

const LEGACY_STORAGE_KEY = 'intec:user-type-screen-access:v1'
const SCREEN_ACCESS_SYNC_KEY = 'intec:screen-access-updated:v2'
const ADMIN_ONLY_PAGES = new Set<ScreenPermissionCode>(['sistema-academico', 'asignacion-pantallas'])
const ROLE_DENIED_PAGES: Partial<Record<Role, Set<ScreenPermissionCode>>> = {
  ESTUDIANTE: new Set<ScreenPermissionCode>(['expedientes-documentales']),
}

function isPageOrFlowOf(page: ScreenPermissionCode, parent: ScreenPermissionCode) {
  return page === parent || page.startsWith(`${parent}/`)
}

function screenAvailableForRole(role: Role | null, page: ScreenPermissionCode) {
  if (!role) return false
  if (role !== 'ADMINISTRADOR' && [...ADMIN_ONLY_PAGES].some((parent) => isPageOrFlowOf(page, parent))) return false
  return ![...(ROLE_DENIED_PAGES[role] || [])].some((parent) => isPageOrFlowOf(page, parent))
}

function assignmentMap(roles: ScreenAccessRole[]): AssignmentMap {
  return Object.fromEntries(roles.map((role) => [role.value, role.pages])) as AssignmentMap
}

function formatUpdate(value?: string | null) {
  if (!value) return 'Sin cambios registrados'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

export function AsignacionPantallasView({ displayName }: Readonly<{ displayName: string }>) {
  const [data, setData] = useState<ScreenAccessResponse | null>(null)
  const [assignments, setAssignments] = useState<AssignmentMap>({})
  const [selectedRole, setSelectedRole] = useState<Role | null>(null)
  const [activeTab, setActiveTab] = useState<AccessTab>('roles')
  const [query, setQuery] = useState('')
  const [screenQuery, setScreenQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [closeConfirmationOpen, setCloseConfirmationOpen] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadAssignments = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetchScreenAccessAssignments(true)
      setData(response)
      setAssignments(assignmentMap(response.roles))
    } catch (apiError) {
      setError(apiError instanceof ApiError ? apiError.message : 'No se pudo cargar la asignacion institucional de pantallas.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAssignments()
  }, [loadAssignments])

  const filteredRoles = useMemo(() => {
    const roles = data?.roles || []
    const needle = query.trim().toLocaleLowerCase('es')
    if (!needle) return roles
    return roles.filter((role) =>
      `${role.label} ${role.value} ${role.description}`.toLocaleLowerCase('es').includes(needle),
    )
  }, [data?.roles, query])

  const groupedScreens = useMemo(() => {
    const groups = new Map<string, NonNullable<ScreenAccessResponse['screens']>>()
    const needle = screenQuery.trim().toLocaleLowerCase('es')
    ;(data?.screens || [])
      .filter((screen) => screenAvailableForRole(selectedRole, screen.page))
      .filter((screen) => !needle || `${screen.label} ${screen.description} ${screen.group} ${screen.page}`.toLocaleLowerCase('es').includes(needle))
      .forEach((screen) => {
        groups.set(screen.group, [...(groups.get(screen.group) || []), screen])
      })
    return Array.from(groups.entries())
  }, [data?.screens, screenQuery, selectedRole])

  const selectedRoleMeta = data?.roles.find((role) => role.value === selectedRole) || null
  const selectedPages = selectedRole ? assignments[selectedRole] || [] : []
  const selectedSet = new Set(selectedPages)
  const visiblePages = groupedScreens.flatMap(([, items]) => items.map((screen) => screen.page))
  const assignedPages = new Set(selectedRoleMeta?.pages || [])
  const hasChanges = selectedPages.length !== assignedPages.size || selectedPages.some((page) => !assignedPages.has(page))
  const canSave = Boolean(
    selectedRoleMeta
    && !selectedRoleMeta.protected
    && (hasChanges || !selectedRoleMeta.configured),
  )

  function availableScreenCount(role: Role) {
    return (data?.screens || []).filter((screen) => screenAvailableForRole(role, screen.page)).length
  }

  function openRole(role: ScreenAccessRole) {
    setSelectedRole(role.value)
    setAssignments((current) => ({ ...current, [role.value]: current[role.value] || role.pages }))
    setCloseConfirmationOpen(false)
    setScreenQuery('')
    setMessage('')
    setError('')
  }

  function finishClosingRole() {
    setSelectedRole(null)
    setCloseConfirmationOpen(false)
    setScreenQuery('')
    setMessage('')
    setError('')
  }

  function closeRole() {
    if (hasChanges) {
      setCloseConfirmationOpen(true)
      return
    }
    finishClosingRole()
  }

  function closeRoleWithoutSaving() {
    if (selectedRole && selectedRoleMeta) {
      setAssignments((current) => ({ ...current, [selectedRole]: selectedRoleMeta.pages }))
    }
    finishClosingRole()
  }

  function togglePage(page: ScreenPermissionCode) {
    if (!selectedRole || selectedRoleMeta?.protected) return
    setAssignments((current) => {
      const pages = new Set(current[selectedRole] || [])
      if (pages.has(page)) pages.delete(page)
      else pages.add(page)
      return { ...current, [selectedRole]: Array.from(pages) }
    })
    setMessage('')
  }

  function discardChanges() {
    if (!selectedRole || !selectedRoleMeta || selectedRoleMeta.protected) return
    setAssignments((current) => ({ ...current, [selectedRole]: selectedRoleMeta.pages }))
    setMessage('')
    setError('')
  }

  async function save() {
    if (!selectedRole) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const savedRole = await updateScreenAccessAssignment(selectedRole, selectedPages)
      setData((current) => current ? {
        ...current,
        synchronized_at: new Date().toISOString(),
        roles: current.roles.map((role) => role.value === savedRole.value ? savedRole : role),
      } : current)
      setAssignments((current) => ({ ...current, [savedRole.value]: savedRole.pages }))
      window.localStorage.removeItem(LEGACY_STORAGE_KEY)
      window.localStorage.setItem(SCREEN_ACCESS_SYNC_KEY, JSON.stringify({
        role: savedRole.value,
        updatedAt: Date.now(),
      }))
      window.dispatchEvent(new CustomEvent('intec-screen-access-updated'))
      setMessage(`Asignacion sincronizada para ${savedRole.label}.`)
    } catch (apiError) {
      setError(apiError instanceof ApiError ? apiError.message : 'No se pudo guardar la asignacion de pantallas.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="screen-access-page">
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Administracion</p>
          <h1>Asignacion de pantallas</h1>
          <p>{displayName} · Configure las pantallas que utilizaran todos los usuarios de cada tipo.</p>
        </div>
        <div className="screen-access-source">
          <span>Fuente central</span>
          <strong>{data?.source || 'INTEC_INTEGRACION_CONTROL.cfg'}</strong>
          <small>{loading ? 'Sincronizando...' : `${data?.screens.length || 0} pantallas vigentes`}</small>
        </div>
      </header>

      <div className="titulacion-simple-tabs senescyt-update-tabs" role="tablist" aria-label="Asignacion de accesos">
        <button type="button" className={activeTab === 'roles' ? 'is-active' : ''} onClick={() => setActiveTab('roles')}>
          Tipos de usuario
        </button>
        <button type="button" className={activeTab === 'summary' ? 'is-active' : ''} onClick={() => setActiveTab('summary')}>
          Pantallas asignadas
        </button>
      </div>

      <section className="screen-access-workspace">
        <div className="screen-access-toolbar">
          <label>
            Buscar perfil
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Administrador, academico, bienestar..." />
          </label>
          <button type="button" onClick={() => setQuery('')} disabled={!query}>Limpiar</button>
          <button type="button" onClick={() => void loadAssignments()} disabled={loading}>
            {loading ? 'Sincronizando...' : 'Actualizar'}
          </button>
          <div className="screen-access-sync-copy">
            <strong>{filteredRoles.length} perfil(es)</strong>
            <span>Actualizacion: {formatUpdate(data?.synchronized_at)}</span>
          </div>
        </div>

        {error ? <div className="status-message status-message--error">{error}</div> : null}
        {message && !selectedRole ? <div className="status-message status-message--success">{message}</div> : null}

        {activeTab === 'roles' ? (
          <div className="screen-access-role-catalog" aria-live="polite">
            {loading && !data ? <p className="screen-access-empty">Cargando perfiles y pantallas institucionales...</p> : null}
            {!loading && filteredRoles.length === 0 ? <p className="screen-access-empty">No se encontraron tipos de usuario.</p> : null}
            {filteredRoles.map((role) => {
              const pages = assignments[role.value] || role.pages
              return (
                <button key={role.value} type="button" className="screen-access-role-card" onClick={() => openRole(role)}>
                  <span className="screen-access-role-card__head">
                    <strong>{role.label}</strong>
                    <small>{role.protected ? 'Protegido' : role.configured ? 'Asignacion guardada' : 'Sin asignar'}</small>
                  </span>
                  <span>{role.description}</span>
                  <span className="screen-access-role-card__footer">
                    <b>{pages.length} pantalla(s)</b>
                    <small>{role.protected ? 'Acceso institucional protegido' : role.updated_by ? `Por ${role.updated_by}` : 'Configurar pantallas'}</small>
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="screen-access-summary-table-wrap">
            <table className="screen-access-summary-table">
              <thead>
                <tr>
                  <th>Tipo de usuario</th>
                  <th>Alcance</th>
                  <th>Configuracion</th>
                  <th>Ultima actualizacion</th>
                  <th>Responsable</th>
                  <th>Accion</th>
                </tr>
              </thead>
              <tbody>
                {filteredRoles.map((role) => (
                  <tr key={role.value}>
                    <td data-label="Tipo de usuario"><strong>{role.label}</strong><small>{role.value}</small></td>
                    <td data-label="Alcance">{(assignments[role.value] || role.pages).length} de {availableScreenCount(role.value)} disponibles</td>
                    <td data-label="Configuracion"><span className={role.configured ? 'screen-access-badge is-custom' : 'screen-access-badge'}>{role.protected ? 'Protegida' : role.configured ? 'Guardada' : 'Sin asignar'}</span></td>
                    <td data-label="Ultima actualizacion">{formatUpdate(role.updated_at)}</td>
                    <td data-label="Responsable">{role.updated_by || 'Sistema'}</td>
                    <td data-label="Accion"><button type="button" onClick={() => openRole(role)}>{role.protected ? 'Ver acceso' : 'Asignar'}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedRole && selectedRoleMeta ? (
        <div className="senescyt-update-subscreen-backdrop screen-access-subscreen-backdrop" role="presentation">
          <section className="senescyt-update-subscreen screen-access-subscreen" role="dialog" aria-modal="true" aria-label="Subpantalla de asignacion de pantallas">
            <div className="senescyt-update-subscreen__head">
              <div>
                <span>Asignacion por tipo de usuario</span>
                <h2>{selectedRoleMeta.label}</h2>
              </div>
              <div className="senescyt-update-subscreen__actions">
                <span>{selectedPages.length} pantalla(s)</span>
                <button type="button" onClick={closeRole} disabled={saving}>Cerrar</button>
              </div>
            </div>

            <div className="screen-access-subscreen__body" tabIndex={0}>
              <div className="matricula-acad-preview senescyt-update-summary">
                <div><span>Perfil</span><strong>{selectedRole}</strong></div>
                <div><span>Alcance</span><strong>{selectedPages.length} / {availableScreenCount(selectedRole)}</strong></div>
                <div><span>Configuracion</span><strong>{selectedRoleMeta.protected ? 'Protegida' : selectedRoleMeta.configured ? 'Guardada' : 'Sin asignar'}</strong></div>
                <div><span>Ultimo cambio</span><strong>{formatUpdate(selectedRoleMeta.updated_at)}</strong></div>
              </div>

              {selectedRoleMeta.protected ? (
                <div className="status-message status-message--info">El perfil Administrador conserva acceso total para evitar el bloqueo de la configuracion institucional.</div>
              ) : null}

              <div className="screen-access-editor-toolbar">
                <label>
                  Buscar pantalla
                  <input
                    value={screenQuery}
                    onChange={(event) => setScreenQuery(event.target.value)}
                    placeholder="Nombre, grupo o funcion de la pantalla"
                  />
                </label>
                <div>
                  <strong>{visiblePages.length} visible(s)</strong>
                  <span>{selectedPages.length} asignada(s)</span>
                </div>
              </div>

              <div className="screen-access-actions">
                <div className="screen-access-actions__status" aria-live="polite">
                  <strong>{hasChanges ? 'Cambios pendientes' : 'Asignacion sincronizada'}</strong>
                  <span>Marque o desmarque cada pantalla y guarde una sola vez.</span>
                </div>
                <button type="button" onClick={discardChanges} disabled={saving || selectedRoleMeta.protected || !hasChanges}>Deshacer cambios</button>
                <button type="button" className="primary-action" onClick={() => void save()} disabled={saving || !canSave}>
                  {saving ? 'Guardando...' : 'Guardar cambios'}
                </button>
              </div>

              {selectedPages.length === 0 ? <div className="status-message status-message--info">Este perfil quedara sin acceso al sistema cuando guarde la asignacion.</div> : null}
              {message ? <div className="status-message status-message--success">{message}</div> : null}
              {error ? <div className="status-message status-message--error">{error}</div> : null}

              <div className="screen-access-groups">
                {groupedScreens.map(([group, items]) => (
                  <section key={group} className="screen-access-group">
                    <div className="screen-access-group__head">
                      <h4>{group}<span>{items.filter((screen) => selectedSet.has(screen.page)).length} / {items.length}</span></h4>
                    </div>
                    <div className="screen-access-grid">
                      {items.map((screen) => (
                        <label key={screen.page} className={selectedSet.has(screen.page) ? 'screen-access-item screen-access-item--checked' : 'screen-access-item'}>
                          <input
                            type="checkbox"
                            checked={selectedSet.has(screen.page)}
                            disabled={saving || selectedRoleMeta.protected}
                            onChange={() => togglePage(screen.page)}
                          />
                          <span>
                            <strong>{screen.label}</strong>
                            <small>{screen.description}</small>
                            <small className="screen-access-item__code">{screen.page}</small>
                          </span>
                        </label>
                      ))}
                    </div>
                  </section>
                ))}
                {groupedScreens.length === 0 ? (
                  <p className="screen-access-empty">No hay pantallas que coincidan con la busqueda.</p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {closeConfirmationOpen ? (
        <div
          className="screen-access-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setCloseConfirmationOpen(false)
          }}
        >
          <section
            className="screen-access-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="screen-access-confirm-title"
            aria-describedby="screen-access-confirm-description"
          >
            <header>
              <span>Cambios pendientes</span>
              <h2 id="screen-access-confirm-title">¿Cerrar esta asignación?</h2>
            </header>
            <p id="screen-access-confirm-description">
              Los cambios realizados para {selectedRoleMeta?.label || 'este perfil'} todavía no se han guardado.
            </p>
            <div className="screen-access-confirm-actions">
              <button type="button" onClick={() => setCloseConfirmationOpen(false)} autoFocus>
                Seguir editando
              </button>
              <button type="button" className="screen-access-confirm-discard" onClick={closeRoleWithoutSaving}>
                Cerrar sin guardar
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
