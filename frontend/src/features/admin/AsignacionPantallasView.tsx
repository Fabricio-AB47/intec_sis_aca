import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, fetchScreenAccessAssignments, updateScreenAccessAssignment } from '../../lib/api'
import type { Page, Role, ScreenAccessResponse, ScreenAccessRole } from '../../types/app'


type AccessTab = 'roles' | 'summary'
type AssignmentMap = Partial<Record<Role, Page[]>>

const LEGACY_STORAGE_KEY = 'intec:user-type-screen-access:v1'
const ADMIN_ONLY_PAGES = new Set<Page>(['sistema-academico'])

function assignmentMap(roles: ScreenAccessRole[]): AssignmentMap {
  return Object.fromEntries(roles.map((role) => [role.value, role.pages])) as AssignmentMap
}

function formatUpdate(value?: string | null) {
  if (!value) return 'Configuracion recomendada'
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
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
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
    ;(data?.screens || [])
      .filter((screen) => selectedRole === 'ADMINISTRADOR' || !ADMIN_ONLY_PAGES.has(screen.page))
      .forEach((screen) => {
      groups.set(screen.group, [...(groups.get(screen.group) || []), screen])
    })
    return Array.from(groups.entries())
  }, [data?.screens, selectedRole])

  const selectedRoleMeta = data?.roles.find((role) => role.value === selectedRole) || null
  const selectedPages = selectedRole ? assignments[selectedRole] || [] : []
  const selectedSet = new Set(selectedPages)

  function openRole(role: ScreenAccessRole) {
    setSelectedRole(role.value)
    setAssignments((current) => ({ ...current, [role.value]: current[role.value] || role.pages }))
    setMessage('')
    setError('')
  }

  function togglePage(page: Page) {
    if (!selectedRole || selectedRoleMeta?.protected) return
    setAssignments((current) => {
      const pages = new Set(current[selectedRole] || [])
      if (pages.has(page)) pages.delete(page)
      else pages.add(page)
      return { ...current, [selectedRole]: Array.from(pages) }
    })
    setMessage('')
  }

  function applyPreset() {
    if (!selectedRole || !selectedRoleMeta || selectedRoleMeta.protected) return
    setAssignments((current) => ({ ...current, [selectedRole]: selectedRoleMeta.default_pages }))
    setMessage('Se cargo la configuracion recomendada. Guarde para aplicarla a todos los usuarios del perfil.')
  }

  function clearRole() {
    if (!selectedRole || selectedRoleMeta?.protected) return
    setAssignments((current) => ({ ...current, [selectedRole]: [] }))
    setMessage('Se desmarcaron todas las pantallas. Guarde para confirmar el cambio.')
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
          <p>{displayName} · Los cambios se aplican a todos los usuarios del perfil administrativo.</p>
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
                    <small>{role.configured ? 'Personalizado' : 'Recomendado'}</small>
                  </span>
                  <span>{role.description}</span>
                  <span className="screen-access-role-card__footer">
                    <b>{pages.length} pantalla(s)</b>
                    <small>{role.updated_by ? `Por ${role.updated_by}` : 'Abrir subpantalla'}</small>
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
                    <td><strong>{role.label}</strong><small>{role.value}</small></td>
                    <td>{(assignments[role.value] || role.pages).length} de {data?.screens.length || 0} pantallas</td>
                    <td><span className={role.configured ? 'screen-access-badge is-custom' : 'screen-access-badge'}>{role.configured ? 'Personalizada' : 'Recomendada'}</span></td>
                    <td>{formatUpdate(role.updated_at)}</td>
                    <td>{role.updated_by || 'Sistema'}</td>
                    <td><button type="button" onClick={() => openRole(role)}>Ver</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedRole && selectedRoleMeta ? (
        <div className="senescyt-update-subscreen-backdrop" role="presentation">
          <section className="senescyt-update-subscreen screen-access-subscreen" role="dialog" aria-modal="true" aria-label="Subpantalla de asignacion de pantallas">
            <div className="senescyt-update-subscreen__head">
              <div>
                <span>Asignacion por tipo de usuario</span>
                <h2>{selectedRoleMeta.label}</h2>
              </div>
              <div className="senescyt-update-subscreen__actions">
                <span>{selectedPages.length} pantalla(s)</span>
                <button type="button" onClick={() => setSelectedRole(null)} disabled={saving}>Cerrar</button>
              </div>
            </div>

            <div className="matricula-acad-preview senescyt-update-summary">
              <div><span>Perfil</span><strong>{selectedRole}</strong></div>
              <div><span>Alcance</span><strong>{selectedPages.length} / {data?.screens.length || 0}</strong></div>
              <div><span>Configuracion</span><strong>{selectedRoleMeta.configured ? 'Personalizada' : 'Recomendada'}</strong></div>
              <div><span>Ultimo cambio</span><strong>{formatUpdate(selectedRoleMeta.updated_at)}</strong></div>
            </div>

            {selectedRoleMeta.protected ? (
              <div className="status-message status-message--info">El perfil Administrador conserva acceso total para evitar el bloqueo de la configuracion institucional.</div>
            ) : null}

            <div className="screen-access-actions">
              <button type="button" onClick={applyPreset} disabled={saving || selectedRoleMeta.protected}>Cargar recomendado</button>
              <button type="button" onClick={clearRole} disabled={saving || selectedRoleMeta.protected}>Limpiar seleccion</button>
              <button type="button" className="primary-action" onClick={() => void save()} disabled={saving || selectedPages.length === 0}>
                {saving ? 'Guardando...' : 'Guardar y sincronizar'}
              </button>
            </div>

            {selectedPages.length === 0 ? <div className="status-message status-message--info">Seleccione al menos una pantalla antes de guardar.</div> : null}
            {message ? <div className="status-message status-message--success">{message}</div> : null}
            {error ? <div className="status-message status-message--error">{error}</div> : null}

            <div className="screen-access-groups">
              {groupedScreens.map(([group, items]) => (
                <section key={group} className="screen-access-group">
                  <h4>{group}<span>{items.filter((screen) => selectedSet.has(screen.page)).length} / {items.length}</span></h4>
                  <div className="screen-access-grid">
                    {items.map((screen) => (
                      <label key={screen.page} className={selectedSet.has(screen.page) ? 'screen-access-item screen-access-item--checked' : 'screen-access-item'}>
                        <input
                          type="checkbox"
                          checked={selectedSet.has(screen.page)}
                          disabled={saving || selectedRoleMeta.protected}
                          onChange={() => togglePage(screen.page)}
                        />
                        <span><strong>{screen.label}</strong><small>{screen.description}</small></span>
                      </label>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
