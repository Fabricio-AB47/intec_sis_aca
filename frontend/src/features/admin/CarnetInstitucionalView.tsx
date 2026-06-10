import { useEffect, useMemo, useState } from 'react'

import {
  approveCarnetPhoto,
  downloadCarnetMePdf,
  downloadCarnetPersonaPdf,
  fetchCarnetMe,
  fetchCarnetPersonaPhoto,
  rejectCarnetPhoto,
  searchCarnetPersonas,
  uploadCarnetMePhoto,
  uploadCarnetPersonaPhoto,
} from '../../lib/api'
import type { CarnetPersona, CarnetPersonaTipo, CarnetPhotoStatus } from '../../types/app'

type CarnetInstitucionalViewProps = {
  displayName: string
  role?: string
}

const MANAGER_ROLES = new Set([
  'ADMINISTRADOR',
  'FINANCIERO',
  'BIENESTAR',
  'ACADEMICO',
  'ADMISIONES',
  'RECTOR',
  'VICERRECTOR',
  'SOPORTE',
])

const PERSON_TYPES: Array<CarnetPersonaTipo | 'TODOS'> = ['TODOS', 'ESTUDIANTE', 'DOCENTE', 'ADMINISTRATIVO']

function statusText(status?: string) {
  const value = (status || 'SIN_FOTO').toUpperCase()
  if (value === 'APROBADA') return 'Aprobada'
  if (value === 'PENDIENTE') return 'Pendiente'
  if (value === 'RECHAZADA') return 'Rechazada'
  if (value === 'CANCELADA') return 'Cancelada'
  if (value === 'VENCIDA') return 'Vencida'
  return 'Sin foto'
}

function statusTone(status?: string) {
  const value = (status || 'SIN_FOTO').toUpperCase()
  if (value === 'APROBADA') return 'credential-status credential-status--success'
  if (value === 'PENDIENTE') return 'credential-status credential-status--warning'
  if (value === 'RECHAZADA') return 'credential-status credential-status--danger'
  if (value === 'VENCIDA') return 'credential-status credential-status--danger'
  return 'credential-status'
}

function normalizePerson(person?: CarnetPersona | null) {
  if (!person) return null
  return {
    tipo: person.tipo_persona || '-',
    codigo: person.codigo_persona || '-',
    cedula: person.cedula || '-',
    nombre: person.nombre || '-',
    correo: person.correo || '-',
    fuente: person.fuente || '-',
  }
}

function photoUrl(status?: CarnetPhotoStatus | null) {
  const url = status?.foto_url || ''
  return url || ''
}

function formatBytes(value?: number | null) {
  if (!value) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function personKey(person: CarnetPersona) {
  return `${person.tipo_persona}-${person.codigo_persona}`
}

function carnetStatusRank(status?: string) {
  const value = (status || 'SIN_FOTO').toUpperCase()
  if (value === 'PENDIENTE') return 0
  if (value === 'RECHAZADA') return 1
  if (value === 'SIN_FOTO') return 2
  if (value === 'VENCIDA') return 3
  if (value === 'APROBADA') return 4
  return 5
}

function orderCarnetPeople(items: CarnetPersona[]) {
  return [...items].sort((left, right) => {
    const statusDiff = carnetStatusRank(left.foto?.estado) - carnetStatusRank(right.foto?.estado)
    if (statusDiff !== 0) return statusDiff
    return (left.nombre || '').localeCompare(right.nombre || '')
  })
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function carnetFilename(status?: CarnetPhotoStatus | null) {
  const person = status?.persona
  const code = person?.cedula || person?.codigo_persona || 'usuario'
  return `carnet-${person?.tipo_persona || 'intec'}-${code}.pdf`
}

export function CarnetInstitucionalView({ displayName, role = '' }: Readonly<CarnetInstitucionalViewProps>) {
  const normalizedRole = role.trim().toUpperCase()
  const canManage = MANAGER_ROLES.has(normalizedRole)
  const [myStatus, setMyStatus] = useState<CarnetPhotoStatus | null>(null)
  const [myLoading, setMyLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [personType, setPersonType] = useState<CarnetPersonaTipo | 'TODOS'>('TODOS')
  const [people, setPeople] = useState<CarnetPersona[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [selectedPerson, setSelectedPerson] = useState<CarnetPersona | null>(null)
  const [selectedStatus, setSelectedStatus] = useState<CarnetPhotoStatus | null>(null)
  const [uploading, setUploading] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const currentPerson = useMemo(() => normalizePerson(myStatus?.persona), [myStatus])
  const activePerson = useMemo(
    () => normalizePerson(selectedStatus?.persona || selectedPerson),
    [selectedPerson, selectedStatus]
  )
  const managerStats = useMemo(() => {
    const stats = {
      total: people.length,
      pending: 0,
      approved: 0,
      missing: 0,
      rejected: 0,
    }
    people.forEach((person) => {
      const status = (person.foto?.estado || 'SIN_FOTO').toUpperCase()
      if (status === 'PENDIENTE') stats.pending += 1
      else if (status === 'APROBADA') stats.approved += 1
      else if (status === 'RECHAZADA' || status === 'VENCIDA') stats.rejected += 1
      else stats.missing += 1
    })
    return stats
  }, [people])

  async function loadMyStatus() {
    setMyLoading(true)
    setError('')
    try {
      setMyStatus(await fetchCarnetMe())
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar el carnet.')
    } finally {
      setMyLoading(false)
    }
  }

  async function runSearch(nextQuery = query, nextType = personType) {
    if (!canManage) return
    setSearchLoading(true)
    setError('')
    try {
      const payload = await searchCarnetPersonas(nextQuery, nextType, 50)
      const orderedItems = orderCarnetPeople(payload.items || [])
      setPeople(orderedItems)
      if (!selectedPerson && (payload.items || []).length > 0) {
        const first = orderedItems[0] || null
        if (first) {
          setSelectedPerson(first)
          setSelectedStatus(first.foto || null)
        }
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar personas.')
      setPeople([])
    } finally {
      setSearchLoading(false)
    }
  }

  async function selectPerson(person: CarnetPersona) {
    setSelectedPerson(person)
    setSelectedStatus(person.foto || null)
    setError('')
    try {
      const status = await fetchCarnetPersonaPhoto(person.tipo_persona, person.codigo_persona)
      setSelectedStatus(status)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar la foto seleccionada.')
    }
  }

  async function handleUpload(file: File | null, target: 'me' | 'selected') {
    if (!file) return
    const status = target === 'me' ? myStatus : selectedStatus
    if (status?.puede_subir === false) {
      setError(status.mensaje_vigencia || 'La foto aprobada sigue vigente. No se puede cargar una nueva solicitud.')
      return
    }
    if (target === 'selected' && !selectedPerson) {
      setError('Selecciona una persona antes de subir una foto.')
      return
    }
    setUploading(true)
    setMessage('')
    setError('')
    try {
      const response =
        target === 'me'
          ? await uploadCarnetMePhoto(file)
          : await uploadCarnetPersonaPhoto(selectedPerson!.tipo_persona, selectedPerson!.codigo_persona, file)
      setMessage(response.message || 'Foto cargada correctamente.')
      if (target === 'me') {
        setMyStatus(response.foto || null)
      } else {
        setSelectedStatus(response.foto || null)
        void runSearch()
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo subir la foto.')
    } finally {
      setUploading(false)
    }
  }

  async function handleDownload(target: 'me' | 'selected') {
    if (target === 'selected' && !selectedPerson) {
      setError('Selecciona una persona antes de generar el carnet.')
      return
    }
    setDownloading(true)
    setMessage('')
    setError('')
    try {
      const blob =
        target === 'me'
          ? await downloadCarnetMePdf()
          : await downloadCarnetPersonaPdf(selectedPerson!.tipo_persona, selectedPerson!.codigo_persona)
      downloadBlob(blob, carnetFilename(target === 'me' ? myStatus : selectedStatus))
      setMessage('Carnet generado correctamente.')
      if (target === 'me') {
        void loadMyStatus()
      } else if (selectedPerson) {
        void selectPerson(selectedPerson)
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el carnet.')
    } finally {
      setDownloading(false)
    }
  }

  async function handleReview(action: 'approve' | 'reject') {
    const requestId = selectedStatus?.id_solicitud
    if (!requestId) {
      setError('No existe una solicitud pendiente para revisar.')
      return
    }
    setReviewing(true)
    setMessage('')
    setError('')
    try {
      const response =
        action === 'approve'
          ? await approveCarnetPhoto(requestId)
          : await rejectCarnetPhoto(requestId, 'Foto rechazada desde carnet institucional')
      setSelectedStatus(response.foto || null)
      setMessage(response.message || 'Revision actualizada.')
      void runSearch()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar la revision.')
    } finally {
      setReviewing(false)
    }
  }

  useEffect(() => {
    void loadMyStatus()
  }, [])

  useEffect(() => {
    if (canManage) {
      void runSearch('', 'TODOS')
    }
  }, [canManage])

  const myCanUpload = myStatus?.puede_subir !== false
  const selectedCanUpload = Boolean(selectedPerson) && selectedStatus?.puede_subir !== false
  const myCanDownload = Boolean(myStatus?.puede_descargar_carnet)
  const selectedCanDownload = Boolean(selectedPerson && selectedStatus?.puede_descargar_carnet)

  return (
    <section className="content-stack carnet-page">
      <article className="student-topbar carnet-hero">
        <div>
          <span className="eyebrow">{canManage ? 'Carnetizacion' : 'Carnet institucional'}</span>
          <h1>{canManage ? 'Aprobacion de carnet institucional' : 'Mi carnet institucional'}</h1>
          <p>
            {canManage
              ? 'Revisa solicitudes, aprueba o rechaza fotos y genera carnets para estudiantes, docentes y administrativos.'
              : 'Carga tu foto y revisa el estado de aprobacion para el carnet.'}
          </p>
        </div>
        <div className="carnet-hero__user">
          <span>{displayName || 'Usuario'}</span>
          <strong>{normalizedRole || 'INTEC'}</strong>
        </div>
      </article>

      {message ? <div className="success-message">{message}</div> : null}
      {error ? <div className="error-message">{error}</div> : null}

      <div className="carnet-grid">
        <article className="student-card carnet-panel">
          <div className="section-title section-title--inline">
            <div>
              <span className="eyebrow">Mi carnet</span>
              <h2>{currentPerson?.nombre || displayName || 'Usuario conectado'}</h2>
            </div>
            <span className={statusTone(myStatus?.estado)}>{statusText(myStatus?.estado)}</span>
          </div>

          <CarnetPhotoBlock status={myStatus} loading={myLoading} />

          <div className="carnet-meta-grid">
            <InfoTile label="Tipo" value={currentPerson?.tipo || normalizedRole || '-'} />
            <InfoTile label="Codigo" value={currentPerson?.codigo || '-'} />
            <InfoTile label="Cedula/Login" value={currentPerson?.cedula || '-'} />
            <InfoTile label="Correo" value={currentPerson?.correo || '-'} />
            <InfoTile label="Vigencia" value={myStatus?.fecha_vigencia_hasta || '-'} />
            <InfoTile label="Renovacion" value={`${myStatus?.meses_vigencia || (normalizedRole === 'ESTUDIANTE' ? 8 : 24)} meses`} />
          </div>

          {myStatus?.mensaje_vigencia ? <p className="carnet-validity-note">{myStatus.mensaje_vigencia}</p> : null}

          <div className="carnet-actions carnet-actions--stacked">
            <label className={`file-input-card ${uploading || !myCanUpload ? 'file-input-card--disabled' : ''}`}>
              <span>{myCanUpload ? 'Subir foto de carnet' : 'Foto vigente bloqueada'}</span>
              <small>
                {myCanUpload
                  ? 'JPG, PNG o WEBP hasta 8 MB. Queda pendiente de aprobacion.'
                  : 'La nueva solicitud se habilita al finalizar la vigencia.'}
              </small>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={uploading || !myCanUpload}
                onChange={(event) => {
                  const file = event.target.files?.[0] || null
                  void handleUpload(file, 'me')
                  event.currentTarget.value = ''
                }}
              />
            </label>
            <button
              type="button"
              className="primary-action"
              disabled={downloading || !myCanDownload}
              onClick={() => void handleDownload('me')}
            >
              {downloading ? 'Generando...' : 'Descargar carnet'}
            </button>
          </div>
        </article>

        {canManage ? (
          <article className="student-card carnet-panel carnet-manager">
            <div className="section-title section-title--inline">
              <div>
                <span className="eyebrow">Panel administrativo</span>
                <h2>Solicitudes de carnetizacion</h2>
              </div>
              <span className="credential-status">{people.length} resultado(s)</span>
            </div>

            <div className="carnet-manager-summary">
              <InfoTile label="Pendientes" value={String(managerStats.pending)} />
              <InfoTile label="Aprobadas" value={String(managerStats.approved)} />
              <InfoTile label="Sin foto" value={String(managerStats.missing)} />
              <InfoTile label="Rechazadas/vencidas" value={String(managerStats.rejected)} />
            </div>

            <form
              className="carnet-search"
              onSubmit={(event) => {
                event.preventDefault()
                void runSearch()
              }}
            >
              <label>
                Buscar por nombre, cedula, codigo o correo
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Ej. 1726240565, Gomez, docente@intec.edu.ec"
                />
              </label>
              <label>
                Tipo
                <select
                  value={personType}
                  onChange={(event) => {
                    const value = event.target.value as CarnetPersonaTipo | 'TODOS'
                    setPersonType(value)
                    void runSearch(query, value)
                  }}
                >
                  {PERSON_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type === 'TODOS' ? 'Todos' : type}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-action" disabled={searchLoading} type="submit">
                {searchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </form>

            <div className="carnet-workspace">
              <div className="carnet-results" aria-label="Resultados de busqueda">
                {people.length === 0 ? (
                  <p className="empty-state">No hay personas para mostrar.</p>
                ) : (
                  people.map((person) => {
                    const selected = selectedPerson && personKey(person) === personKey(selectedPerson)
                    const status = person.foto?.estado
                    return (
                      <button
                        type="button"
                        key={personKey(person)}
                        className={`carnet-person-card ${selected ? 'carnet-person-card--active' : ''}`}
                        onClick={() => void selectPerson(person)}
                      >
                        <span className={statusTone(status)}>{statusText(status)}</span>
                        <strong>{person.nombre || '-'}</strong>
                        <small>{person.cedula || person.codigo_persona || '-'}</small>
                        <em>{person.tipo_persona} · {person.fuente}</em>
                      </button>
                    )
                  })
                )}
              </div>

              <div className="carnet-selected">
                <div className="section-title section-title--inline">
                  <div>
                    <span className="eyebrow">Persona seleccionada</span>
                    <h3>{activePerson?.nombre || 'Sin seleccion'}</h3>
                  </div>
                  <span className={statusTone(selectedStatus?.estado)}>{statusText(selectedStatus?.estado)}</span>
                </div>

                <CarnetPhotoBlock status={selectedStatus} loading={false} />

                <div className="carnet-meta-grid carnet-meta-grid--compact">
                  <InfoTile label="Tipo" value={activePerson?.tipo || '-'} />
                  <InfoTile label="Codigo" value={activePerson?.codigo || '-'} />
                  <InfoTile label="Cedula/Login" value={activePerson?.cedula || '-'} />
                  <InfoTile label="Correo" value={activePerson?.correo || '-'} />
                  <InfoTile label="Fuente" value={activePerson?.fuente || '-'} />
                  <InfoTile label="Tamano" value={formatBytes(selectedStatus?.tamano_bytes)} />
                  <InfoTile label="Vigencia" value={selectedStatus?.fecha_vigencia_hasta || '-'} />
                  <InfoTile label="Emision" value={selectedStatus?.fecha_emision || '-'} />
                  <InfoTile label="Renovacion" value={`${selectedStatus?.meses_vigencia || '-'} meses`} />
                </div>

                {selectedStatus?.mensaje_vigencia ? (
                  <p className="carnet-validity-note">{selectedStatus.mensaje_vigencia}</p>
                ) : null}

                <div className="carnet-actions">
                  <label className={`ghost-button file-trigger ${uploading || !selectedCanUpload ? 'is-disabled' : ''}`}>
                    Subir foto
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      disabled={uploading || !selectedCanUpload}
                      onChange={(event) => {
                        const file = event.target.files?.[0] || null
                        void handleUpload(file, 'selected')
                        event.currentTarget.value = ''
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={downloading || !selectedCanDownload}
                    onClick={() => void handleDownload('selected')}
                  >
                    Generar carnet
                  </button>
                  <button
                    type="button"
                    className="primary-action"
                    disabled={reviewing || selectedStatus?.estado !== 'PENDIENTE'}
                    onClick={() => void handleReview('approve')}
                  >
                    Aprobar
                  </button>
                  <button
                    type="button"
                    className="danger-action"
                    disabled={reviewing || selectedStatus?.estado !== 'PENDIENTE'}
                    onClick={() => void handleReview('reject')}
                  >
                    Rechazar
                  </button>
                </div>
              </div>
            </div>
          </article>
        ) : null}
      </div>
    </section>
  )
}

function InfoTile({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="carnet-info-tile">
      <span>{label}</span>
      <strong>{value || '-'}</strong>
    </div>
  )
}

function CarnetPhotoBlock({ status, loading }: Readonly<{ status?: CarnetPhotoStatus | null; loading: boolean }>) {
  const imageUrl = photoUrl(status)

  return (
    <div className="carnet-photo-block">
      <div className="carnet-photo-preview">
        {loading ? (
          <span>Cargando...</span>
        ) : imageUrl ? (
          <img src={imageUrl} alt="Foto de carnet" />
        ) : (
          <span>Sin foto</span>
        )}
      </div>
      <div className="carnet-photo-copy">
        <span className={statusTone(status?.estado)}>{statusText(status?.estado)}</span>
        <strong>{status?.nombre_archivo || 'Foto no cargada'}</strong>
        <p>{status?.observacion || status?.mensaje || 'La foto se mostrara cuando exista una solicitud o aprobacion.'}</p>
        <small>
          Solicitud: {status?.fecha_solicitud || '-'} · Revision: {status?.fecha_revision || '-'}
        </small>
      </div>
    </div>
  )
}
