import { useEffect, useMemo, useState } from 'react'

import {
  createTitulosRegistradosFolder,
  deleteTituloRegistrado,
  fetchTitulosRegistrados,
  fetchTitulosRegistradosFolders,
  searchTitulosRegistradosStudents,
  uploadTituloRegistrado,
  uploadTitulosSenescytMasivo,
} from '../../lib/api'
import type { TituloRegistradoItem, TituloRegistradoTipo } from '../../types/app'

type TitulosRegistradosViewProps = {
  displayName: string
  role: string
  initialTipo?: string
}

const defaultForm = {
  tipo: 'senescyt' as TituloRegistradoTipo,
  modelo: '',
  estudiante: '',
  cedula: '',
  carrera: '',
  observacion: '',
}

type FolderOption = { id?: string; name: string; web_url?: string }
type StudentOption = { codigo_estud?: string; cedula: string; estudiante: string; carrera?: string; estado?: string }

function normalizeTipo(value?: string): TituloRegistradoTipo | '' {
  if (value === 'senescyt' || value === 'intec') return value
  return ''
}

function getModuleCopy(tipo: TituloRegistradoTipo | '') {
  if (tipo === 'senescyt') {
    return {
      title: 'Títulos registrados SENESCYT',
      description: 'Registro documental independiente en OneDrive: TITULACION GESTION DOCUMENTAL / TITULOS REGISTRADOS SENESCYT.',
      folderHint: 'OneDrive: TITULOS REGISTRADOS SENESCYT',
      folderLabel: 'Carpeta SENESCYT destino',
      empty: 'No existen títulos SENESCYT registrados para el filtro seleccionado.',
      metric: 'Títulos SENESCYT',
    }
  }
  if (tipo === 'intec') {
    return {
      title: 'Titulación',
      description: 'Registro documental independiente en OneDrive: TITULACION GESTION DOCUMENTAL / TITULOS INTEC.',
      folderHint: 'OneDrive: TITULOS INTEC',
      folderLabel: 'Carpeta INTEC destino',
      empty: 'No existen títulos INTEC registrados para el filtro seleccionado.',
      metric: 'Títulos INTEC',
    }
  }
  return {
    title: 'Títulos registrados',
    description: 'Registro documental en OneDrive: TITULACION GESTION DOCUMENTAL.',
    folderHint: 'OneDrive: TITULOS REGISTRADOS SENESCYT / TITULOS INTEC',
    folderLabel: 'Carpeta destino',
    empty: 'No existen títulos registrados para el filtro seleccionado.',
    metric: 'Archivos registrados',
  }
}

function formatSize(value?: number): string {
  const bytes = Number(value || 0)
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function formatDate(value?: string): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('es-EC', { dateStyle: 'medium', timeStyle: 'short' })
}

function resolveUploadUrl(value: string): string {
  if (!value) return '#'
  if (value.startsWith('http')) return value
  return value
}

export function TitulosRegistradosView({ displayName, role, initialTipo = '' }: Readonly<TitulosRegistradosViewProps>) {
  const isAdmin = role === 'ADMINISTRADOR'
  const fixedTipo = normalizeTipo(initialTipo)
  const moduleCopy = useMemo(() => getModuleCopy(fixedTipo), [fixedTipo])
  const [items, setItems] = useState<TituloRegistradoItem[]>([])
  const [totals, setTotals] = useState({ total: 0, senescyt: 0, intec: 0 })
  const [tipoFilter, setTipoFilter] = useState(fixedTipo)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [bulkSaving, setBulkSaving] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [bulkFiles, setBulkFiles] = useState<File[]>([])
  const [form, setForm] = useState({
    ...defaultForm,
    tipo: (fixedTipo || 'senescyt') as TituloRegistradoTipo,
  })
  const [folders, setFolders] = useState<FolderOption[]>([])
  const [folderLoading, setFolderLoading] = useState(false)
  const [folderError, setFolderError] = useState('')
  const [newFolderName, setNewFolderName] = useState('')
  const [studentQuery, setStudentQuery] = useState('')
  const [studentResults, setStudentResults] = useState<StudentOption[]>([])
  const [studentLoading, setStudentLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const filteredLabel = useMemo(() => {
    const currentTipo = fixedTipo || tipoFilter
    if (currentTipo === 'senescyt') return 'SENESCYT'
    if (currentTipo === 'intec') return 'INTEC'
    return 'Todos'
  }, [fixedTipo, tipoFilter])
  const activeTipo = (fixedTipo || form.tipo) as TituloRegistradoTipo

  async function loadTitles(nextTipo = fixedTipo || tipoFilter, nextSearch = search) {
    setLoading(true)
    setError('')
    try {
      const response = await fetchTitulosRegistrados({ tipo: nextTipo, search: nextSearch })
      setItems(response.items || [])
      setTotals(response.totals || { total: 0, senescyt: 0, intec: 0 })
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar títulos registrados')
    } finally {
      setLoading(false)
    }
  }

  async function loadFolders(tipo = fixedTipo || form.tipo) {
    setFolderLoading(true)
    setFolderError('')
    try {
      const response = await fetchTitulosRegistradosFolders(tipo)
      setFolders(response.items || [])
    } catch (apiError) {
      setFolders([])
      setFolderError(apiError instanceof Error ? apiError.message : 'No se pudo cargar carpetas de OneDrive')
    } finally {
      setFolderLoading(false)
    }
  }

  async function createFolder() {
    if (!newFolderName.trim()) {
      setError('Ingresa el nombre de la carpeta.')
      return
    }
    setError('')
    setMessage('')
    try {
      const activeTipo = fixedTipo || form.tipo
      const response = await createTitulosRegistradosFolder({ tipo: activeTipo, nombre: newFolderName.trim() })
      setMessage(response.message || 'Carpeta creada')
      setForm((current) => ({ ...current, modelo: response.item?.name || newFolderName.trim() }))
      setNewFolderName('')
      await loadFolders(activeTipo)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo crear la carpeta')
    }
  }

  async function searchStudents() {
    if (studentQuery.trim().length < 2) {
      setError('Ingresa al menos 2 caracteres para buscar estudiante.')
      return
    }
    setStudentLoading(true)
    setError('')
    try {
      const response = await searchTitulosRegistradosStudents(studentQuery.trim())
      setStudentResults(response.items || [])
      if ((response.items || []).length === 0) {
        setMessage('No se encontraron estudiantes para el criterio ingresado.')
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar el estudiante')
    } finally {
      setStudentLoading(false)
    }
  }

  function selectStudent(item: StudentOption) {
    setForm((current) => ({
      ...current,
      estudiante: item.estudiante || current.estudiante,
      cedula: item.cedula || current.cedula,
      carrera: item.carrera || current.carrera,
    }))
    setStudentQuery(`${item.cedula} · ${item.estudiante}`)
    setStudentResults([])
  }

  async function saveTitle() {
    if (!isAdmin) return
    if (!form.modelo.trim()) {
      setError('Ingresa el modelo del título.')
      return
    }
    if (!file) {
      setError('Selecciona el archivo del título.')
      return
    }
    if ((fixedTipo || form.tipo) === 'senescyt' && (!form.estudiante.trim() || !form.cedula.trim())) {
      setError('Selecciona el estudiante para asociar el título SENESCYT.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const activeTipo = (fixedTipo || form.tipo) as TituloRegistradoTipo
      const response = await uploadTituloRegistrado({ ...form, tipo: activeTipo, file })
      setMessage(response.message || 'Título registrado correctamente')
      setForm({
        ...defaultForm,
        tipo: activeTipo,
      })
      setFile(null)
      setStudentQuery('')
      setStudentResults([])
      await loadTitles(activeTipo)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar el título')
    } finally {
      setSaving(false)
    }
  }

  async function saveBulkSenescyt() {
    if (!isAdmin) return
    if (activeTipo !== 'senescyt') {
      setError('La carga masiva por identificación aplica únicamente para títulos SENESCYT.')
      return
    }
    if (!form.modelo.trim()) {
      setError('Selecciona o crea la carpeta SENESCYT donde se almacenarán los documentos.')
      return
    }
    if (bulkFiles.length === 0) {
      setError('Selecciona uno o varios PDFs SENESCYT para procesar.')
      return
    }
    setBulkSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await uploadTitulosSenescytMasivo({
        modelo: form.modelo,
        observacion: form.observacion,
        files: bulkFiles,
      })
      const results = response.results || []
      const failed = results.filter((item) => String(item.estado || '').startsWith('ERROR') || ['OMITIDO', 'NO_ENCONTRADO', 'SIN_IDENTIFICACION', 'SIN_REGISTROS'].includes(String(item.estado || ''))).length
      setMessage(`${response.message || 'Carga masiva finalizada'} Archivos con observación: ${failed}.`)
      setBulkFiles([])
      await loadTitles('senescyt')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo realizar la carga masiva SENESCYT')
    } finally {
      setBulkSaving(false)
    }
  }

  async function removeTitle(item: TituloRegistradoItem) {
    if (!isAdmin) return
    const confirmed = window.confirm(`Eliminar el título ${item.filename || item.modelo}?`)
    if (!confirmed) return
    setError('')
    setMessage('')
    try {
      const response = await deleteTituloRegistrado(item.id)
      setMessage(response.message || 'Título eliminado')
      await loadTitles()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo eliminar el título')
    }
  }

  useEffect(() => {
    void loadTitles()
    void loadFolders()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!fixedTipo) {
      void loadFolders(form.tipo)
      setForm((current) => ({ ...current, modelo: '' }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.tipo, fixedTipo])

  useEffect(() => {
    if (!message && !error) return undefined
    const timeout = window.setTimeout(() => {
      setMessage('')
      setError('')
    }, 180000)
    return () => window.clearTimeout(timeout)
  }, [message, error])

  function closeStatusModal() {
    setMessage('')
    setError('')
  }

  return (
    <main className="student-page titulos-registrados-page">
      {(message || error) ? (
        <div className="status-modal-backdrop" role="presentation">
          <section
            className={`status-modal ${error ? 'status-modal--error' : 'status-modal--success'}`}
            role="alertdialog"
            aria-live="assertive"
            aria-labelledby="titulos-status-title"
          >
            <div>
              <span>{error ? 'Atención' : 'Proceso completado'}</span>
              <h2 id="titulos-status-title">{error ? 'No se pudo completar la acción' : 'Acción realizada correctamente'}</h2>
              <p>{error || message}</p>
              <small>Este mensaje se cerrará automáticamente en 3 minutos.</small>
            </div>
            <button type="button" onClick={closeStatusModal} aria-label="Cerrar mensaje">
              Cerrar
            </button>
          </section>
        </div>
      ) : null}

      <section className="student-hero">
        <div>
          <p>TÍTULOS</p>
          <h1>{moduleCopy.title}</h1>
          <span>{moduleCopy.description}</span>
        </div>
        <aside>
          <strong>{displayName}</strong>
          <span>{isAdmin ? 'Administrador' : 'Consulta'}</span>
        </aside>
      </section>

      <section className="student-grid student-grid--stats">
        <article className="student-stat-card">
          <span>{fixedTipo ? moduleCopy.metric : 'Total'}</span>
          <strong>{fixedTipo === 'senescyt' ? totals.senescyt : fixedTipo === 'intec' ? totals.intec : totals.total}</strong>
          <small>{fixedTipo ? 'Registros del módulo' : 'Archivos registrados'}</small>
        </article>
        <article className="student-stat-card">
          <span>{fixedTipo ? 'Carpetas' : 'SENESCYT'}</span>
          <strong>{fixedTipo ? folders.length : totals.senescyt}</strong>
          <small>{fixedTipo ? 'Carpetas de destino' : 'Títulos registrados por SENESCYT'}</small>
        </article>
        <article className="student-stat-card">
          <span>{fixedTipo ? 'Tipo' : 'INTEC'}</span>
          <strong>{fixedTipo ? filteredLabel : totals.intec}</strong>
          <small>{fixedTipo ? moduleCopy.folderHint : 'Títulos internos por modelo'}</small>
        </article>
      </section>

      {isAdmin ? (
        <section className="student-grid student-grid--content">
          <article className="student-card student-card--wide">
            <div className="card-head">
              <h3>Registrar título</h3>
              <span>{moduleCopy.folderHint}</span>
            </div>
            <div className="matricula-acad-form titulos-registrados-form">
              {!fixedTipo ? (
                <label>
                  <span>Tipo de título</span>
                  <select
                    value={form.tipo}
                    onChange={(event) => setForm((current) => ({ ...current, tipo: event.target.value as TituloRegistradoTipo }))}
                  >
                    <option value="senescyt">Títulos registrados por SENESCYT</option>
                    <option value="intec">Títulos INTEC</option>
                  </select>
                </label>
              ) : null}
              <label>
                <span>{moduleCopy.folderLabel}</span>
                <select
                  value={form.modelo}
                  onChange={(event) => setForm((current) => ({ ...current, modelo: event.target.value }))}
                  disabled={folderLoading}
                >
                  <option value="">{folderLoading ? 'Cargando carpetas...' : 'Selecciona carpeta'}</option>
                  {folders.map((folder) => (
                    <option key={folder.id || folder.name} value={folder.name}>
                      {folder.name}
                    </option>
                  ))}
                </select>
                {folderError ? <small className="field-warning">{folderError}</small> : null}
              </label>
              <label className="gestion-sis-field--wide">
                <span>Crear carpeta si no existe</span>
                <div className="inline-field-action">
                  <input value={newFolderName} onChange={(event) => setNewFolderName(event.target.value)} placeholder="Nombre de nueva carpeta" />
                  <button type="button" className="ghost-button" onClick={() => void createFolder()}>
                    Crear
                  </button>
                </div>
              </label>
              <label className="gestion-sis-field--wide">
                <span>Buscar estudiante</span>
                <div className="inline-field-action">
                  <input value={studentQuery} onChange={(event) => setStudentQuery(event.target.value)} placeholder="Nombre o cédula del estudiante" />
                  <button type="button" className="ghost-button" onClick={() => void searchStudents()} disabled={studentLoading}>
                    {studentLoading ? 'Buscando...' : 'Buscar'}
                  </button>
                </div>
                {studentResults.length ? (
                  <div className="inline-search-results">
                    {studentResults.map((student) => (
                      <button
                        key={`${student.codigo_estud || student.cedula}-${student.estudiante}`}
                        type="button"
                        onClick={() => selectStudent(student)}
                      >
                        <strong>{student.estudiante}</strong>
                        <span>{student.cedula} · {student.carrera || 'Sin carrera'}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </label>
              <label>
                <span>Estudiante</span>
                <input value={form.estudiante} onChange={(event) => setForm((current) => ({ ...current, estudiante: event.target.value }))} placeholder="Nombre del estudiante" />
              </label>
              <label>
                <span>Cédula</span>
                <input value={form.cedula} onChange={(event) => setForm((current) => ({ ...current, cedula: event.target.value }))} placeholder="Número de cédula" />
              </label>
              <label>
                <span>Carrera</span>
                <input value={form.carrera} onChange={(event) => setForm((current) => ({ ...current, carrera: event.target.value }))} placeholder="Carrera" />
              </label>
              <label>
                <span>Archivo</span>
                <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" onChange={(event) => setFile(event.target.files?.[0] || null)} />
              </label>
              <label className="gestion-sis-field--wide">
                <span>Observación</span>
                <textarea value={form.observacion} onChange={(event) => setForm((current) => ({ ...current, observacion: event.target.value }))} />
              </label>
            </div>
            <div className="teams-actions">
              <button type="button" onClick={() => void saveTitle()} disabled={saving}>
                {saving ? 'Guardando...' : 'Registrar título'}
              </button>
            </div>
            {activeTipo === 'senescyt' ? (
              <div className="titulos-bulk-panel">
                <div>
                  <span>Carga masiva SENESCYT</span>
                  <h4>Subir PDFs por número de identificación</h4>
                  <p>
                    El sistema analiza cada nómina, extrae la cédula, busca el estudiante en DATOS_ESTUD,
                    renombra el archivo y lo sube a la carpeta seleccionada.
                  </p>
                </div>
                <label>
                  <span>PDFs SENESCYT</span>
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    multiple
                    onChange={(event) => setBulkFiles(Array.from(event.target.files || []))}
                  />
                  <small>{bulkFiles.length ? `${bulkFiles.length} archivo(s) seleccionado(s)` : 'Sin archivos seleccionados'}</small>
                </label>
                <button type="button" className="primary-action" onClick={() => void saveBulkSenescyt()} disabled={bulkSaving}>
                  {bulkSaving ? 'Procesando...' : 'Procesar y subir masivo'}
                </button>
              </div>
            ) : null}
          </article>
        </section>
      ) : null}

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Consulta de títulos</h3>
            <span>{loading ? 'Cargando...' : `${items.length} registro(s) · ${filteredLabel}`}</span>
          </div>
          <div className="fecha-grado-verification-bar">
            {!fixedTipo ? (
              <label>
                <span>Tipo</span>
                <select
                  value={tipoFilter}
                  onChange={(event) => {
                    setTipoFilter(normalizeTipo(event.target.value))
                  }}
                >
                  <option value="">Todos</option>
                  <option value="senescyt">SENESCYT</option>
                  <option value="intec">INTEC</option>
                </select>
              </label>
            ) : null}
            <label>
              <span>Buscar</span>
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Estudiante, cédula, carrera, modelo o archivo" />
            </label>
            <button type="button" className="primary-action fecha-grado-refresh-button" onClick={() => void loadTitles()} disabled={loading}>
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  {!fixedTipo ? <th>Tipo</th> : null}
                  <th>Modelo</th>
                  <th>Estudiante</th>
                  <th>Cédula</th>
                  <th>Carrera</th>
                  <th>Archivo</th>
                  <th>Registro</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={fixedTipo ? 7 : 8}>{moduleCopy.empty}</td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr key={item.id}>
                      {!fixedTipo ? <td>{item.tipo_nombre}</td> : null}
                      <td>{item.modelo || '-'}</td>
                      <td>{item.estudiante || '-'}</td>
                      <td>{item.cedula || '-'}</td>
                      <td>{item.carrera || '-'}</td>
                      <td>
                        <strong>{item.filename}</strong>
                        <br />
                        <small>{formatSize(item.size)} · {item.storage === 'onedrive' ? 'OneDrive' : 'Local'}</small>
                      </td>
                      <td>
                        {formatDate(item.created_at)}
                        <br />
                        <small>{item.created_by || '-'}</small>
                      </td>
                      <td>
                        <div className="table-actions">
                          <a className="ghost-button" href={resolveUploadUrl(item.url)} target="_blank" rel="noreferrer">
                            Descargar
                          </a>
                          {isAdmin ? (
                            <button type="button" className="ghost-button" onClick={() => void removeTitle(item)}>
                              Eliminar
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </main>
  )
}
