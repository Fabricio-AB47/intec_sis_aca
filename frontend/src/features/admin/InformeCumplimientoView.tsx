import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import {
  fetchComplianceDocuments,
  type ComplianceDocumentsQuery,
  uploadComplianceInvoiceBackups,
} from '../../lib/api'
import type {
  ComplianceDocumentItem,
  ComplianceDocumentsResponse,
  ComplianceDocumentType,
} from '../../types/app'

type InformeCumplimientoViewProps = {
  displayName: string
}

const EMPTY_RESPONSE: ComplianceDocumentsResponse = {
  items: [],
  page: 1,
  page_size: 25,
  total: 0,
  total_pages: 1,
  has_previous: false,
  has_next: false,
  summary: {
    documents: 0,
    packages: 0,
    teachers: 0,
  },
}

const MAX_INVOICE_XML_BYTES = 20 * 1024 * 1024
const MAX_RIDE_PDF_BYTES = 50 * 1024 * 1024

const DOCUMENT_TYPES: Array<{ value: '' | ComplianceDocumentType; label: string }> = [
  { value: '', label: 'Todos los documentos' },
  { value: 'INFORME', label: 'Informe de cumplimiento' },
  { value: 'NOTAS', label: 'Reporte de notas' },
  { value: 'CONTRATO', label: 'Contrato docente' },
  { value: 'PAQUETE', label: 'Paquete ZIP' },
  { value: 'FACTURA_XML', label: 'Factura XML' },
  { value: 'RIDE', label: 'RIDE de factura' },
  { value: 'CARPETA', label: 'Carpeta histórica' },
  { value: 'OTRO', label: 'Otros documentos' },
]

const DOCUMENT_LABELS: Record<ComplianceDocumentType, string> = {
  INFORME: 'Informe',
  NOTAS: 'Notas',
  CONTRATO: 'Contrato',
  PAQUETE: 'Paquete ZIP',
  FACTURA_XML: 'Factura XML',
  RIDE: 'RIDE',
  CARPETA: 'Carpeta',
  OTRO: 'Otro',
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatDate(value?: string | null): string {
  if (!value) return 'Sin fecha'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudieron consultar los documentos de cumplimiento docente.'
}

function teacherLabel(item: ComplianceDocumentItem): string {
  return item.nombre_docente?.trim() || 'Docente sin identificar'
}

function subjectLabel(item: ComplianceDocumentItem): string {
  return item.nombre_materia?.trim() || 'Asignatura sin identificar'
}

export function InformeCumplimientoView({ displayName }: InformeCumplimientoViewProps) {
  const [data, setData] = useState<ComplianceDocumentsResponse>(EMPTY_RESPONSE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [documentType, setDocumentType] = useState<'' | ComplianceDocumentType>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [invoiceTarget, setInvoiceTarget] = useState<ComplianceDocumentItem | null>(null)
  const [selectedInvoiceEventId, setSelectedInvoiceEventId] = useState<number | ''>('')
  const [invoiceXml, setInvoiceXml] = useState<File | null>(null)
  const [ridePdf, setRidePdf] = useState<File | null>(null)
  const [uploadingInvoice, setUploadingInvoice] = useState(false)
  const [invoiceError, setInvoiceError] = useState('')
  const [invoiceSuccess, setInvoiceSuccess] = useState('')
  const invoiceFormRef = useRef<HTMLFormElement>(null)
  const [appliedQuery, setAppliedQuery] = useState<ComplianceDocumentsQuery>({
    page: 1,
    pageSize: 25,
  })

  const invoiceTargets = useMemo(() => {
    const targets = new Map<number, ComplianceDocumentItem>()
    data.items.forEach((item) => {
      const current = targets.get(item.event_id)
      if (!current || item.tipo_documento === 'INFORME') {
        targets.set(item.event_id, item)
      }
    })
    return Array.from(targets.values())
  }, [data.items])

  const selectedInvoiceTarget = useMemo(
    () => (
      invoiceTargets.find((item) => item.event_id === selectedInvoiceEventId)
      || invoiceTargets[0]
      || null
    ),
    [invoiceTargets, selectedInvoiceEventId],
  )

  const loadDocuments = useCallback(async (query: ComplianceDocumentsQuery) => {
    setLoading(true)
    setError('')
    try {
      setData(await fetchComplianceDocuments(query))
    } catch (apiError) {
      setError(errorMessage(apiError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // La consulta remota debe repetirse cuando cambian filtros o paginación.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDocuments(appliedQuery)
  }, [appliedQuery, loadDocuments])

  useEffect(() => {
    if (!invoiceTarget) return undefined
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !uploadingInvoice) setInvoiceTarget(null)
    }
    document.addEventListener('keydown', closeWithEscape)
    return () => document.removeEventListener('keydown', closeWithEscape)
  }, [invoiceTarget, uploadingInvoice])

  const applyFilters = (event?: FormEvent) => {
    event?.preventDefault()
    setAppliedQuery({
      page: 1,
      pageSize: 25,
      search: search.trim(),
      documentType,
      dateFrom,
      dateTo,
    })
  }

  const clearFilters = () => {
    setSearch('')
    setDocumentType('')
    setDateFrom('')
    setDateTo('')
    setAppliedQuery({ page: 1, pageSize: 25 })
  }

  const changePage = (page: number) => {
    setAppliedQuery((current) => ({ ...current, page }))
  }

  const openInvoiceUpload = (item: ComplianceDocumentItem) => {
    setInvoiceTarget(item)
    setInvoiceXml(null)
    setRidePdf(null)
    setInvoiceError('')
    setInvoiceSuccess('')
  }

  const closeInvoiceUpload = () => {
    if (uploadingInvoice) return
    setInvoiceTarget(null)
    setInvoiceError('')
    setInvoiceSuccess('')
    invoiceFormRef.current?.reset()
  }

  const submitInvoiceBackups = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!invoiceTarget || !invoiceXml || !ridePdf) {
      setInvoiceError('Seleccione la factura XML y el RIDE en PDF antes de guardar.')
      return
    }
    if (!invoiceXml.name.toLowerCase().endsWith('.xml')) {
      setInvoiceError('La factura electrónica debe estar en formato XML.')
      return
    }
    if (!ridePdf.name.toLowerCase().endsWith('.pdf')) {
      setInvoiceError('El RIDE debe estar en formato PDF.')
      return
    }
    if (invoiceXml.size === 0) {
      setInvoiceError('La factura XML seleccionada está vacía.')
      return
    }
    if (ridePdf.size === 0) {
      setInvoiceError('El RIDE seleccionado está vacío.')
      return
    }
    if (invoiceXml.size > MAX_INVOICE_XML_BYTES) {
      setInvoiceError('La factura XML supera el límite de 20 MB.')
      return
    }
    if (ridePdf.size > MAX_RIDE_PDF_BYTES) {
      setInvoiceError('El RIDE supera el límite de 50 MB.')
      return
    }

    setUploadingInvoice(true)
    setInvoiceError('')
    setInvoiceSuccess('')
    try {
      const result = await uploadComplianceInvoiceBackups(
        invoiceTarget.event_id,
        invoiceXml,
        ridePdf,
      )
      setInvoiceSuccess(result.message)
      setInvoiceXml(null)
      setRidePdf(null)
      invoiceFormRef.current?.reset()
      await loadDocuments(appliedQuery)
    } catch (apiError) {
      setInvoiceError(errorMessage(apiError))
    } finally {
      setUploadingInvoice(false)
    }
  }

  const invoiceActionRows = new Set(
    data.items.filter(
      (item, index, items) => items.findIndex((candidate) => candidate.event_id === item.event_id) === index,
    ).map((item) => item.id),
  )

  return (
    <main className="integration-history-page compliance-documents-page">
      <header className="integration-history-hero">
        <div>
          <span>ADMINISTRACIÓN</span>
          <h1>Informe de cumplimiento</h1>
          <p>
            Consulte los informes, reportes de notas, contratos y paquetes firmados que se encuentran
            archivados en Microsoft 365, y anexe la factura XML junto con su RIDE al mismo expediente.
          </p>
        </div>
        <div className="integration-history-user">
          <strong>{displayName}</strong>
          <span>Revisión documental</span>
        </div>
      </header>

      <section
        className="integration-history-summary compliance-documents-summary"
        aria-label="Resumen de documentos"
      >
        <article>
          <span>Documentos disponibles</span>
          <strong>{loading ? '...' : formatNumber(data.summary.documents)}</strong>
        </article>
        <article>
          <span>Expedientes archivados</span>
          <strong>{loading ? '...' : formatNumber(data.summary.packages)}</strong>
        </article>
        <article>
          <span>Docentes registrados</span>
          <strong>{loading ? '...' : formatNumber(data.summary.teachers)}</strong>
        </article>
      </section>

      <section className="compliance-invoice-entry" aria-labelledby="compliance-invoice-entry-title">
        <div className="compliance-invoice-entry__intro">
          <span>RESPALDOS DE FACTURACIÓN</span>
          <h2 id="compliance-invoice-entry-title">Agregar factura XML y RIDE</h2>
          <p>
            Seleccione el expediente docente. Los dos archivos se guardarán juntos en su carpeta
            <strong> DOCENTES</strong>, sin reemplazar el informe, las notas ni el contrato existentes.
          </p>
        </div>
        <label className="compliance-invoice-entry__target">
          <span>Expediente del informe de cumplimiento</span>
          <select
            value={selectedInvoiceTarget?.event_id || ''}
            disabled={loading || invoiceTargets.length === 0}
            onChange={(event) => setSelectedInvoiceEventId(Number(event.target.value))}
          >
            {invoiceTargets.length === 0 ? (
              <option value="">No hay expedientes disponibles</option>
            ) : null}
            {invoiceTargets.map((item) => (
              <option key={item.event_id} value={item.event_id}>
                #{item.event_id} · {teacherLabel(item)} · {subjectLabel(item)}
                {item.periodos.length ? ` · ${item.periodos.join(' / ')}` : ''}
              </option>
            ))}
          </select>
          <small>
            {selectedInvoiceTarget?.ruta_carpeta
              ? `Destino: ${selectedInvoiceTarget.ruta_carpeta}`
              : 'Primero debe existir un informe firmado y archivado para el docente.'}
          </small>
        </label>
        <button
          className="integration-history-primary compliance-invoice-entry__action"
          type="button"
          disabled={loading || !selectedInvoiceTarget}
          onClick={() => {
            if (selectedInvoiceTarget) openInvoiceUpload(selectedInvoiceTarget)
          }}
        >
          Agregar XML y RIDE
        </button>
      </section>

      <section className="integration-history-workspace">
        <header className="integration-history-section-head">
          <div>
            <span>DOCUMENTOS DOCENTES</span>
            <h2>Archivos disponibles</h2>
          </div>
          <button type="button" disabled={loading} onClick={() => void loadDocuments(appliedQuery)}>
            Actualizar
          </button>
        </header>

        <form
          className="integration-history-filters compliance-documents-filters"
          onSubmit={applyFilters}
        >
          <label>
            <span>Buscar</span>
            <input
              type="search"
              value={search}
              placeholder="Docente, cédula, asignatura, período o archivo"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            <span>Tipo de documento</span>
            <select
              value={documentType}
              onChange={(event) => setDocumentType(event.target.value as '' | ComplianceDocumentType)}
            >
              {DOCUMENT_TYPES.map((option) => (
                <option key={option.value || 'all'} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Desde</span>
            <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            <span>Hasta</span>
            <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
          <div className="integration-history-filter-actions">
            <button className="integration-history-primary" type="submit" disabled={loading}>
              Consultar
            </button>
            <button type="button" disabled={loading} onClick={clearFilters}>
              Limpiar
            </button>
          </div>
        </form>

        {error ? (
          <p className="integration-history-alert integration-history-alert--error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="integration-history-table-wrap">
          <table className="integration-history-table compliance-documents-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Docente</th>
                <th>Asignatura y período</th>
                <th>Documento</th>
                <th>Tipo</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {!loading && data.items.length === 0 ? (
                <tr>
                  <td className="integration-history-empty" colSpan={6}>
                    No existen documentos disponibles con los filtros seleccionados.
                  </td>
                </tr>
              ) : null}
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{formatDate(item.fecha_ecuador || item.fecha_utc)}</strong>
                    <small>Archivo #{item.event_id}</small>
                  </td>
                  <td>
                    <strong>{teacherLabel(item)}</strong>
                    <small>
                      {item.cedula_docente || 'Sin cédula'}
                      {item.codigo_docente ? ` · Código ${item.codigo_docente}` : ''}
                    </small>
                  </td>
                  <td>
                    <strong>{subjectLabel(item)}</strong>
                    <small>
                      {item.codigo_materia || 'Sin código'}
                      {item.paralelo ? ` · Paralelo ${item.paralelo}` : ''}
                      {item.jornada ? ` · ${item.jornada}` : ''}
                    </small>
                    <small>{item.periodos.length ? item.periodos.join(' · ') : 'Sin período registrado'}</small>
                  </td>
                  <td>
                    <strong>{item.nombre_documento}</strong>
                    <small>{item.ruta_carpeta || 'Microsoft 365'}</small>
                  </td>
                  <td>
                    <span className={`integration-history-badge compliance-document-type compliance-document-type--${item.tipo_documento.toLowerCase()}`}>
                      {DOCUMENT_LABELS[item.tipo_documento]}
                    </span>
                  </td>
                  <td>
                    <div className="compliance-documents-actions">
                      {item.url_documento ? (
                        <a
                          className="compliance-documents-link compliance-documents-link--primary"
                          href={item.url_documento}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {item.tipo_documento === 'CARPETA' ? 'Abrir carpeta' : 'Abrir documento'}
                        </a>
                      ) : (
                        <span className="compliance-documents-unavailable">Sin enlace</span>
                      )}
                      {item.url_carpeta && item.url_carpeta !== item.url_documento ? (
                        <a
                          className="compliance-documents-link"
                          href={item.url_carpeta}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Ver carpeta
                        </a>
                      ) : null}
                      {invoiceActionRows.has(item.id) ? (
                        <button
                          className="compliance-documents-upload"
                          type="button"
                          onClick={() => openInvoiceUpload(item)}
                        >
                          Agregar XML y RIDE
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading ? <div className="integration-history-loading">Consultando documentos...</div> : null}
        </div>

        <div className="integration-history-pagination" aria-label="Paginación de documentos">
          <strong>{formatNumber(data.total)} documento(s)</strong>
          <div>
            <button type="button" disabled={loading || data.page <= 1} onClick={() => changePage(1)}>
              Primero
            </button>
            <button
              type="button"
              disabled={loading || data.page <= 1}
              onClick={() => changePage(data.page - 1)}
            >
              Anterior
            </button>
            <span>Página {data.page} de {Math.max(data.total_pages, 1)}</span>
            <button
              type="button"
              disabled={loading || data.page >= data.total_pages}
              onClick={() => changePage(data.page + 1)}
            >
              Siguiente
            </button>
            <button
              type="button"
              disabled={loading || data.page >= data.total_pages}
              onClick={() => changePage(data.total_pages)}
            >
              Último
            </button>
          </div>
        </div>
      </section>

      {invoiceTarget ? (
        <div
          className="integration-history-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeInvoiceUpload()
          }}
        >
          <form
            ref={invoiceFormRef}
            className="integration-history-modal compliance-invoice-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="compliance-invoice-title"
            onSubmit={submitInvoiceBackups}
          >
            <header>
              <div>
                <span>RESPALDOS DE FACTURACIÓN</span>
                <h2 id="compliance-invoice-title">Factura XML y RIDE</h2>
              </div>
              <button type="button" disabled={uploadingInvoice} onClick={closeInvoiceUpload}>
                Cerrar
              </button>
            </header>

            <div className="compliance-invoice-modal__body">
              <div className="compliance-invoice-context">
                <div>
                  <span>Docente</span>
                  <strong>{teacherLabel(invoiceTarget)}</strong>
                  <small>{invoiceTarget.cedula_docente || 'Sin cédula registrada'}</small>
                </div>
                <div>
                  <span>Asignatura</span>
                  <strong>{subjectLabel(invoiceTarget)}</strong>
                  <small>{invoiceTarget.periodos.join(' · ') || 'Sin período registrado'}</small>
                </div>
                <div>
                  <span>Carpeta de destino</span>
                  <strong>Expediente archivado #{invoiceTarget.event_id}</strong>
                  <small>{invoiceTarget.ruta_carpeta || 'Microsoft 365'}</small>
                </div>
              </div>

              <p className="compliance-invoice-help">
                Seleccione los dos respaldos de la misma factura. El sistema los guardará juntos en
                la carpeta <strong>DOCENTES</strong> del informe de cumplimiento y conservará los
                documentos existentes.
              </p>

              <div className="compliance-invoice-files">
                <label>
                  <span>Factura electrónica XML</span>
                  <input
                    type="file"
                    accept=".xml,application/xml,text/xml"
                    disabled={uploadingInvoice}
                    required
                    onChange={(event) => {
                      setInvoiceXml(event.target.files?.[0] || null)
                      setInvoiceError('')
                      setInvoiceSuccess('')
                    }}
                  />
                  <small>{invoiceXml?.name || 'Seleccione el comprobante XML. Máximo 20 MB.'}</small>
                </label>
                <label>
                  <span>RIDE en PDF</span>
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    disabled={uploadingInvoice}
                    required
                    onChange={(event) => {
                      setRidePdf(event.target.files?.[0] || null)
                      setInvoiceError('')
                      setInvoiceSuccess('')
                    }}
                  />
                  <small>{ridePdf?.name || 'Seleccione la representación RIDE. Máximo 50 MB.'}</small>
                </label>
              </div>

              {invoiceError ? (
                <p className="integration-history-alert integration-history-alert--error" role="alert">
                  {invoiceError}
                </p>
              ) : null}
              {invoiceSuccess ? (
                <p className="integration-history-alert integration-history-alert--success" role="status">
                  {invoiceSuccess}
                </p>
              ) : null}

              <footer className="compliance-invoice-modal__actions">
                <button type="button" disabled={uploadingInvoice} onClick={closeInvoiceUpload}>
                  Cancelar
                </button>
                <button
                  className="integration-history-primary"
                  type="submit"
                  disabled={uploadingInvoice || !invoiceXml || !ridePdf}
                >
                  {uploadingInvoice ? 'Guardando respaldos...' : 'Guardar XML y RIDE'}
                </button>
              </footer>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  )
}
