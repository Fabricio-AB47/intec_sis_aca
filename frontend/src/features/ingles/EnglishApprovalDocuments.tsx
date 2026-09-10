import { useCallback, useState } from 'react'

import {
  fetchEnglishApprovalStatus,
  reviewEnglishApprovalDocument,
} from '../../lib/api'
import type {
  DocumentExpedientContext,
  EnglishApprovalStatus,
} from '../../types/app'
import { ExpedientesDocumentalesView } from '../expedientes/ExpedientesDocumentalesView'

const DOCUMENT_TYPE_CODES = [
  'CERTIFICADO_APROBACION_INGLES',
  'ACTA_CALIFICACIONES_INGLES',
  'EVIDENCIA_EXAMEN_INGLES',
]

type EnglishApprovalDocumentsProps = {
  displayName: string
  role: string
  initialIdentification?: string
  onClose?: () => void
  onStatusChange?: (status: EnglishApprovalStatus) => void
}

function normalizedRole(value: string) {
  return value.trim().toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

function dateTime(value: string | null) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'America/Guayaquil',
  }).format(parsed)
}

function statusLabel(status: string) {
  const normalized = normalizedRole(status).replace(/_/g, ' ')
  return normalized.charAt(0) + normalized.slice(1).toLowerCase()
}

export function EnglishApprovalDocuments({
  displayName,
  role,
  initialIdentification = '',
  onClose,
  onStatusChange,
}: Readonly<EnglishApprovalDocumentsProps>) {
  const canReview = ['ADMINISTRADOR', 'ACADEMICO', 'SECRETARIA'].includes(normalizedRole(role))
  const [selectedIdentification, setSelectedIdentification] = useState(initialIdentification.trim())
  const [status, setStatus] = useState<EnglishApprovalStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(Boolean(initialIdentification.trim()))
  const [reviewingId, setReviewingId] = useState<number | null>(null)
  const [observations, setObservations] = useState<Record<number, string>>({})
  const [reloadVersion, setReloadVersion] = useState(0)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadStatus = useCallback(async (identification: string) => {
    const normalized = identification.trim()
    if (!normalized) {
      setStatus(null)
      setLoadingStatus(false)
      return
    }
    setLoadingStatus(true)
    setError('')
    try {
      const result = await fetchEnglishApprovalStatus(normalized)
      setStatus(result)
      onStatusChange?.(result)
    } catch (requestError) {
      setStatus(null)
      setError(errorMessage(requestError, 'No se pudo consultar la aprobación documental de Inglés.'))
    } finally {
      setLoadingStatus(false)
    }
  }, [onStatusChange])

  const handleContextChange = useCallback((context: DocumentExpedientContext | null) => {
    const identification = context?.student.identification || ''
    setSelectedIdentification(identification)
    if (identification) {
      void loadStatus(identification)
    } else {
      setStatus(null)
      setLoadingStatus(false)
    }
  }, [loadStatus])

  async function reviewDocument(documentGraphId: number, approved: boolean) {
    if (!selectedIdentification) return
    const observation = observations[documentGraphId]?.trim() || ''
    if (!approved && !observation) {
      setError('Ingrese la observación antes de marcar el documento como observado.')
      return
    }
    setReviewingId(documentGraphId)
    setError('')
    setMessage('')
    try {
      const response = await reviewEnglishApprovalDocument({
        identification: selectedIdentification,
        documentGraphId,
        approved,
        observation,
      })
      setStatus(response.status)
      setMessage(response.message)
      setObservations((current) => ({ ...current, [documentGraphId]: '' }))
      setReloadVersion((current) => current + 1)
      onStatusChange?.(response.status)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo guardar la revisión documental.'))
    } finally {
      setReviewingId(null)
    }
  }

  return (
    <section className="english-approval-documents">
      <ExpedientesDocumentalesView
        key={`${selectedIdentification || 'search'}-${reloadVersion}`}
        displayName={displayName}
        role={role}
        initialIdentification={selectedIdentification || initialIdentification}
        moduleFilter={['INGLES']}
        documentTypeFilter={DOCUMENT_TYPE_CODES}
        embedded
        embeddedTitle="Documentación de aprobación de Inglés"
        embeddedDescription="Cargue los tres respaldos obligatorios en PDF y conserve su revisión institucional."
        showStudentSearch={!initialIdentification.trim()}
        onContextChange={handleContextChange}
        onClose={onClose}
      />

      {loadingStatus ? <div className="english-approval-loading">Consultando cumplimiento de Inglés...</div> : null}
      {error ? <div className="document-expedient-alert document-expedient-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="document-expedient-alert document-expedient-alert--success" role="status">{message}</div> : null}

      {status && !loadingStatus ? (
        <section className="english-approval-review">
          <header className="english-approval-review__header">
            <div>
              <span>Validación institucional</span>
              <h3>Revisión de los tres documentos</h3>
              <p>{status.message}</p>
            </div>
            <div className={`english-approval-overall english-approval-overall--${status.approved ? 'ok' : 'pending'}`}>
              <strong>{status.approved ? 'A2+ aprobado' : statusLabel(status.status)}</strong>
              <small>{status.validated_count} de {status.required_count} documentos validados</small>
            </div>
          </header>

          <div className="english-approval-grade">
            <span>Calificación A2+</span>
            <strong>{status.grade.final_grade === null ? 'Sin nota final' : `${status.grade.final_grade.toLocaleString('es-EC')} / 10`}</strong>
            <small>{status.grade.approved ? 'Nota aprobada' : 'Pendiente de aprobación académica'}</small>
          </div>

          <div className="english-approval-requirements">
            {status.documents.map((document) => (
              <article key={document.code} className={document.validated ? 'is-validated' : document.observed ? 'is-observed' : ''}>
                <div className="english-approval-requirement__content">
                  <span>{document.name}</span>
                  <strong>{document.filename || 'Documento pendiente de carga'}</strong>
                  <small>
                    {document.uploaded
                      ? `${statusLabel(document.status)} · versión ${document.version || 1} · ${dateTime(document.uploaded_at)}`
                      : 'Debe cargarse en formato PDF.'}
                  </small>
                  {document.reviewed_by ? (
                    <small>Revisado por {document.reviewed_by} · {dateTime(document.reviewed_at)}</small>
                  ) : null}
                  {document.observation ? <p>{document.observation}</p> : null}
                </div>
                <div className="english-approval-requirement__review">
                  {canReview && document.uploaded ? (
                    <>
                      <label>
                        <span>Observación de revisión</span>
                        <input
                          value={observations[document.document_graph_id || 0] || ''}
                          onChange={(event) => setObservations((current) => ({
                            ...current,
                            [document.document_graph_id || 0]: event.target.value,
                          }))}
                          placeholder="Motivo, corrección o nota de validación"
                          disabled={reviewingId === document.document_graph_id}
                        />
                      </label>
                      <div>
                        <button
                          type="button"
                          className="secondary-action"
                          disabled={reviewingId !== null || document.validated}
                          onClick={() => void reviewDocument(document.document_graph_id || 0, true)}
                        >
                          Validar
                        </button>
                        <button
                          type="button"
                          className="danger-action"
                          disabled={reviewingId !== null}
                          onClick={() => void reviewDocument(document.document_graph_id || 0, false)}
                        >
                          Observar
                        </button>
                      </div>
                    </>
                  ) : (
                    <span className={`document-expedient-status ${document.validated ? 'document-expedient-status--ok' : 'document-expedient-status--pending'}`}>
                      {statusLabel(document.status)}
                    </span>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  )
}
