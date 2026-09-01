import { useCallback, useEffect, useState, type FormEvent } from 'react'

import {
  createDocumentExpedientUploadSession,
  documentExpedientFileUrl,
  fetchDocumentExpedientContext,
  finalizeDocumentExpedientUpload,
  prepareDocumentExpedient,
  searchDocumentExpedientStudents,
  uploadGraphFileChunks,
} from '../../lib/api'
import type {
  DocumentExpedientContext,
  DocumentExpedientModule,
  DocumentExpedientStudentSearchItem,
} from '../../types/app'
import './ExpedientesDocumentalesView.css'

type ExpedientesDocumentalesViewProps = {
  displayName: string
  role: string
  initialIdentification?: string
  moduleFilter?: string[]
  embedded?: boolean
  onClose?: () => void
}

type ExpedientSectionProps = {
  identification: string
  maxFileBytes: number
  module: DocumentExpedientModule
  onReload: () => Promise<void>
}

const MAX_FILE_BYTES = 1024 * 1024 * 1024
const ACCEPTED_FILES = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,.jpg,.jpeg,.png,.webp,.mp3,.wav,.m4a,.mp4,.mov,.mkv,.webm,.xml'
const REVIEW_ROLES = new Set(['ADMINISTRADOR', 'ACADEMICO', 'BIENESTAR', 'SECRETARIA', 'FINANCIERO'])
const INVOICE_FILE_RULES: Record<string, { accept: string; extension: string }> = {
  FACTURA_XML: { accept: '.xml,application/xml,text/xml', extension: '.xml' },
  RIDE_FACTURA: { accept: '.pdf,application/pdf', extension: '.pdf' },
}

function normalizedRole(value: string) {
  return value
    .trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

function fileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / (1024 ** index)
  return `${value.toLocaleString('es-EC', { maximumFractionDigits: index > 1 ? 2 : 0 })} ${units[index]}`
}

function dateTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'America/Guayaquil',
  }).format(date)
}

function statusClass(status: string) {
  const value = normalizedRole(status)
  if (['CARGADO', 'APROBADO', 'CERRADO', 'FINALIZADO', 'VALIDADO'].includes(value)) {
    return 'document-expedient-status document-expedient-status--ok'
  }
  if (['ERROR', 'RECHAZADO', 'ANULADO'].includes(value)) {
    return 'document-expedient-status document-expedient-status--danger'
  }
  return 'document-expedient-status document-expedient-status--pending'
}

function acceptedFiles(moduleCode: string, documentType: string) {
  if (moduleCode === 'FACTURACION') return INVOICE_FILE_RULES[documentType]?.accept || ''
  return ACCEPTED_FILES
}

function ExpedientSection({
  identification,
  maxFileBytes,
  module,
  onReload,
}: Readonly<ExpedientSectionProps>) {
  const defaultDocumentType = module.document_types[0]?.code || ''
  const [documentType, setDocumentType] = useState(defaultDocumentType)
  const [file, setFile] = useState<File | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [preparing, setPreparing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [folderUrl, setFolderUrl] = useState('')

  useEffect(() => {
    setDocumentType(defaultDocumentType)
    setFile(null)
    setFileInputKey((value) => value + 1)
    setProgress(0)
    setError('')
    setMessage('')
    setFolderUrl('')
  }, [defaultDocumentType, module.origin_id])

  async function prepareFolder() {
    if (!module.origin_id || !['PRACTICAS', 'VINCULACION'].includes(module.module_code)) return
    setPreparing(true)
    setError('')
    setMessage('')
    try {
      const result = await prepareDocumentExpedient({
        identification,
        moduleCode: module.module_code,
        originId: module.origin_id,
      })
      await onReload()
      setFolderUrl(result.web_url || '')
      setMessage(result.message || 'Expediente documental preparado correctamente.')
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo preparar el expediente documental.'))
    } finally {
      setPreparing(false)
    }
  }

  function selectFile(selected: File | null) {
    setError('')
    setMessage('')
    if (!selected) {
      setFile(null)
      return
    }
    if (selected.size > maxFileBytes) {
      setFile(null)
      setFileInputKey((value) => value + 1)
      setError(`El archivo supera el límite de ${fileSize(maxFileBytes)}.`)
      return
    }
    const invoiceRule = module.module_code === 'FACTURACION'
      ? INVOICE_FILE_RULES[documentType]
      : undefined
    if (invoiceRule && !selected.name.toLowerCase().endsWith(invoiceRule.extension)) {
      setFile(null)
      setFileInputKey((value) => value + 1)
      setError(`El tipo documental seleccionado requiere un archivo ${invoiceRule.extension.toUpperCase()}.`)
      return
    }
    setFile(selected)
  }

  function changeDocumentType(value: string) {
    setDocumentType(value)
    setFile(null)
    setFileInputKey((current) => current + 1)
    setError('')
    setMessage('')
  }

  async function uploadDocument() {
    if (!file || !documentType || !module.origin_id || !module.upload_enabled) return
    setUploading(true)
    setProgress(0)
    setError('')
    setMessage('')
    try {
      const session = await createDocumentExpedientUploadSession({
        identification,
        moduleCode: module.module_code,
        originId: module.origin_id,
        documentTypeCode: documentType,
        file,
      })
      await uploadGraphFileChunks(session.upload_url, file, session.chunk_size, setProgress)
      const result = await finalizeDocumentExpedientUpload(session.upload_id)
      setFile(null)
      setFileInputKey((value) => value + 1)
      setProgress(100)
      await onReload()
      setMessage(result.message || 'Documento relacionado correctamente.')
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo completar la carga documental.'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="document-expedient-module">
      <header className="document-expedient-module__header">
        <div>
          <span>{module.module_code}</span>
          <h3>{module.module_name}</h3>
          <p>{module.expedient_code || 'El proceso todavía no tiene un expediente abierto.'}</p>
        </div>
        <div className="document-expedient-module__state">
          <span className={statusClass(module.status)}>{module.status || 'SIN ESTADO'}</span>
          <small>{module.documents.length} documento(s)</small>
        </div>
      </header>

      {module.origin_id && ['PRACTICAS', 'VINCULACION'].includes(module.module_code) ? (
        <div className="document-expedient-folder-actions">
          <div>
            <strong>Carpeta documental del proceso</strong>
            <small>Se reutiliza la carpeta del estudiante identificada por su cédula; no se crean duplicados.</small>
          </div>
          <div className="document-expedient-actions">
            {folderUrl ? <a className="ghost-button" href={folderUrl} target="_blank" rel="noreferrer">Abrir carpeta</a> : null}
            <button type="button" className="secondary-action" onClick={() => void prepareFolder()} disabled={preparing || uploading}>
              {preparing ? 'Preparando...' : 'Generar expediente documental'}
            </button>
          </div>
        </div>
      ) : null}

      <div className="document-expedient-table-wrap">
        <table className="document-expedient-table">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Tipo</th>
              <th>Versión y estado</th>
              <th>Tamaño y fecha</th>
              <th>Registrado por</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {module.documents.length === 0 ? (
              <tr>
                <td colSpan={6} className="document-expedient-table__empty">
                  No existen documentos registrados en este expediente.
                </td>
              </tr>
            ) : module.documents.map((document) => (
              <tr key={document.document_graph_id}>
                <td><strong>{document.name}</strong><small>ID Graph {document.document_graph_id}</small></td>
                <td>{document.document_type_code || '-'}</td>
                <td><strong>Version {document.version}</strong><small>{document.status || '-'}</small></td>
                <td><strong>{fileSize(document.size)}</strong><small>{dateTime(document.uploaded_at)}</small></td>
                <td>{document.uploaded_by || '-'}</td>
                <td>
                  <div className="document-expedient-actions">
                    <a
                      className="ghost-button"
                      href={documentExpedientFileUrl(document.document_graph_id, 'open')}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ver
                    </a>
                    <a className="ghost-button" href={documentExpedientFileUrl(document.document_graph_id, 'download')}>
                      Descargar
                    </a>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {module.upload_enabled ? (
        <div className="document-expedient-upload">
          <label>
            <span>Tipo de documento</span>
            <select value={documentType} onChange={(event) => changeDocumentType(event.target.value)} disabled={uploading}>
              {module.document_types.map((type) => <option key={type.code} value={type.code}>{type.name}</option>)}
            </select>
          </label>
          <label>
            <span>Archivo</span>
            <input
              key={fileInputKey}
              type="file"
              accept={acceptedFiles(module.module_code, documentType)}
              disabled={uploading}
              onChange={(event) => selectFile(event.target.files?.[0] || null)}
            />
            <small>{file ? `${file.name} · ${fileSize(file.size)}` : `Máximo ${fileSize(maxFileBytes)}`}</small>
          </label>
          <button
            type="button"
            className="primary-action"
            disabled={!file || !documentType || uploading}
            onClick={() => void uploadDocument()}
          >
            {uploading ? `Subiendo ${progress}%` : 'Subir documento'}
          </button>
          {uploading ? <div className="document-expedient-progress"><span style={{ width: `${progress}%` }} /></div> : null}
        </div>
      ) : (
        <p className="document-expedient-note">{module.upload_message || 'La carga no está habilitada para este expediente.'}</p>
      )}

      {error ? <div className="document-expedient-alert document-expedient-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="document-expedient-alert document-expedient-alert--success" role="status">{message}</div> : null}
    </section>
  )
}

export function ExpedientesDocumentalesView({
  displayName,
  role,
  initialIdentification = '',
  moduleFilter = [],
  embedded = false,
  onClose,
}: Readonly<ExpedientesDocumentalesViewProps>) {
  const isReviewer = REVIEW_ROLES.has(normalizedRole(role))
  const [context, setContext] = useState<DocumentExpedientContext | null>(null)
  const [selectedIdentification, setSelectedIdentification] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocumentExpedientStudentSearchItem[]>([])
  const [loading, setLoading] = useState(Boolean(initialIdentification.trim()) || !isReviewer)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')

  const loadContext = useCallback(async (identification: string) => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchDocumentExpedientContext(identification)
      setContext(data)
      setSelectedIdentification(data.student.identification)
    } catch (requestError) {
      setContext(null)
      setError(errorMessage(requestError, 'No se pudo consultar el expediente documental.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (initialIdentification.trim()) {
      void loadContext(initialIdentification)
    } else if (!isReviewer) {
      void loadContext('')
    }
  }, [initialIdentification, isReviewer, loadContext])

  async function searchStudents(event: FormEvent) {
    event.preventDefault()
    const term = query.trim()
    if (term.length < 2) {
      setError('Ingrese al menos dos caracteres del nombre, cédula o código.')
      return
    }
    setSearching(true)
    setError('')
    try {
      const response = await searchDocumentExpedientStudents(term)
      setResults(response.items)
      if (response.items.length === 0) setError('No se encontraron estudiantes con ese criterio.')
    } catch (requestError) {
      setResults([])
      setError(errorMessage(requestError, 'No se pudo buscar estudiantes.'))
    } finally {
      setSearching(false)
    }
  }

  async function selectStudent(student: DocumentExpedientStudentSearchItem) {
    setResults([])
    setQuery(`${student.name} · ${student.identification}`)
    await loadContext(student.identification)
  }

  return (
    <section className={`document-expedients-page${embedded ? ' document-expedients-page--embedded' : ''}`}>
      <header className={embedded ? 'document-expedient-embedded-header' : 'student-topbar document-expedients-hero'}>
        <div>
          <p className="eyebrow">{embedded ? 'Expediente del proceso' : 'Documentos'}</p>
          <h2>{embedded ? 'Documentos de prácticas y vinculación' : 'Expedientes documentales'}</h2>
          <p className="report-description">
            {embedded
              ? 'Cree la carpeta y gestione los documentos del proceso con trazabilidad en Microsoft 365.'
              : 'Archivos de Inglés, titulación, prácticas, vinculación y facturas XML/RIDE con trazabilidad en Microsoft 365.'}
          </p>
        </div>
        {embedded ? (
          <button type="button" className="secondary-action" onClick={onClose}>Cerrar</button>
        ) : (
          <div className="student-user-pill"><div><strong>{displayName}</strong><span>{isReviewer ? 'Gestión documental' : 'Portal estudiante'}</span></div></div>
        )}
      </header>

      {isReviewer && !embedded ? (
        <section className="document-expedient-search">
          <form onSubmit={searchStudents}>
            <label>
              <span>Buscar estudiante</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Nombre, cédula o código estudiantil"
              />
            </label>
            <button type="submit" className="primary-action" disabled={searching}>
              {searching ? 'Buscando...' : 'Buscar'}
            </button>
          </form>
          {results.length > 0 ? (
            <div className="document-expedient-search__results">
              {results.map((student) => (
                <button key={`${student.code}-${student.identification}`} type="button" onClick={() => void selectStudent(student)}>
                  <span><strong>{student.name}</strong><small>{student.identification} · Código {student.code}</small></span>
                  <i>{student.status || 'Sin estado'}</i>
                </button>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {error ? <div className="document-expedient-alert document-expedient-alert--error" role="alert">{error}</div> : null}
      {loading ? <section className="student-card document-expedient-loading">Consultando expedientes...</section> : null}

      {context && !loading ? (
        <>
          <section className="document-expedient-student-summary">
            <div><span>Estudiante</span><strong>{context.student.name}</strong><small>Código {context.student.code}</small></div>
            <div><span>Cédula</span><strong>{context.student.identification}</strong><small>{context.student.email || 'Sin correo registrado'}</small></div>
            <div><span>Carrera</span><strong>{context.student.career || 'Sin carrera registrada'}</strong><small>{context.student.period_code || 'Sin período registrado'}</small></div>
            <div><span>Registro documental</span><strong>{context.total_documents} documento(s)</strong><small>{context.total_expedients} expediente(s) abierto(s)</small></div>
          </section>

          <div className="document-expedient-modules">
            {context.expedients
              .filter((module) => moduleFilter.length === 0 || moduleFilter.includes(module.module_code))
              .map((module) => (
              <ExpedientSection
                key={`${module.module_code}-${module.origin_id || 'sin-expediente'}`}
                identification={selectedIdentification}
                maxFileBytes={context.max_file_bytes || MAX_FILE_BYTES}
                module={module}
                onReload={() => loadContext(selectedIdentification)}
              />
            ))}
          </div>
        </>
      ) : null}

      {isReviewer && !context && !loading && !embedded ? (
        <section className="document-expedient-empty">
          <strong>Seleccione un estudiante</strong>
          <span>Busque por nombre, cédula o código para consultar y gestionar sus expedientes.</span>
        </section>
      ) : null}
    </section>
  )
}
