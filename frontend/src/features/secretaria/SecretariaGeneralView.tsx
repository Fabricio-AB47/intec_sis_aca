import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import {
  documentExpedientFileUrl,
  ensureSecretariaCase,
  fetchSecretariaCandidates,
  fetchSecretariaDashboard,
  reviewSecretariaRequirement,
  syncSecretariaCase,
  updateSecretariaHomologationClassification,
} from '../../lib/api'
import type {
  SecretariaCandidate,
  SecretariaCandidatesResponse,
  SecretariaCaseDetailResponse,
  SecretariaDashboardResponse,
  SecretariaHomologationClassification,
  SecretariaObservation,
  SecretariaRequirement,
  SecretariaStage,
} from '../../types/app'
import { ExpedientesDocumentalesView } from '../expedientes/ExpedientesDocumentalesView'
import './SecretariaGeneralView.css'


type SecretariaGeneralViewProps = {
  displayName: string
  role: string
}

type SecretariaListView = SecretariaStage | 'FALTANTES'

const LIST_VIEW_COPY: Record<SecretariaListView, { title: string; empty: string }> = {
  TODOS: {
    title: 'Todos los candidatos',
    empty: 'No hay estudiantes que coincidan con los filtros.',
  },
  PROXIMO: {
    title: 'Próximos a graduarse',
    empty: 'No hay estudiantes próximos a graduarse con los filtros actuales.',
  },
  EGRESADO: {
    title: 'Estudiantes egresados',
    empty: 'No hay estudiantes egresados con los filtros actuales.',
  },
  GRADUADO: {
    title: 'Estudiantes graduados',
    empty: 'No hay estudiantes graduados con los filtros actuales.',
  },
  FALTANTES: {
    title: 'Estudiantes con documentos faltantes',
    empty: 'No existen estudiantes con documentos faltantes en expedientes abiertos.',
  },
}

const EMPTY_PAGE: SecretariaCandidatesResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
  total_pages: 1,
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    APROBADO: 'Aprobado',
    EGRESADO: 'Egresado',
    EN_REVISION: 'En revisión',
    EN_VALIDACION: 'En validación',
    FALTANTE: 'Faltante',
    GRADUADO: 'Graduado',
    OBSERVADO: 'Observado',
    PRESENTE: 'Presentado',
    PROXIMO: 'Próximo a graduarse',
    RECHAZADO: 'Rechazado',
    VALIDADO: 'Validado',
  }
  return labels[value] || value.replaceAll('_', ' ').toLowerCase()
}

const PENDING_REQUIREMENT_STATES = new Set(['FALTANTE', 'PRESENTE', 'EN_REVISION', 'OBSERVADO', 'RECHAZADO'])

const HOMOLOGATION_CLASSIFICATIONS: Array<{
  value: SecretariaHomologationClassification
  label: string
  detail: string
}> = [
  {
    value: 'INTERNA_ART81',
    label: 'Artículo 81 · Homologación interna',
    detail: 'Proceso realizado entre carreras o programas internos de INTEC.',
  },
  {
    value: 'EXTERNA_ART82',
    label: 'Artículo 82 · Menos de 10 años',
    detail: 'Estudios provenientes de otra institución con una antigüedad menor a 10 años.',
  },
  {
    value: 'EXTERNA_ART83',
    label: 'Artículo 83 · Más de 10 años',
    detail: 'Estudios provenientes de otra institución con una antigüedad mayor a 10 años.',
  },
]

function statusTone(value: string) {
  if (['APROBADO', 'GRADUADO', 'VALIDADO'].includes(value)) return 'ok'
  if (['OBSERVADO', 'RECHAZADO'].includes(value)) return 'danger'
  if (['FALTANTE', 'PROXIMO'].includes(value)) return 'warning'
  return 'info'
}

function percent(value: number) {
  return `${Math.max(0, Math.min(100, Number(value) || 0)).toLocaleString('es-EC', { maximumFractionDigits: 1 })}%`
}

function integer(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('es-EC')
    : '-'
}

function decimal(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '-'
}

function quantityLabel(value: number, singular: string, plural: string) {
  return `${integer(value)} ${value === 1 ? singular : plural}`
}

function enrollmentTypeLabel(value: 'R' | 'H') {
  return value === 'H' ? 'Homologación' : 'Regular'
}

function dateTime(value: string | null) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed)
}

function fileSize(value: number | null) {
  if (!value) return ''
  if (value < 1024 * 1024) return `${(value / 1024).toLocaleString('es-EC', { maximumFractionDigits: 1 })} KB`
  return `${(value / (1024 * 1024)).toLocaleString('es-EC', { maximumFractionDigits: 1 })} MB`
}

function ProgressBar({ value, label }: Readonly<{ value: number; label: string }>) {
  const normalized = Math.max(0, Math.min(100, Number(value) || 0))
  return (
    <div className="secretaria-progress" aria-label={`${label}: ${percent(normalized)}`}>
      <div className="secretaria-progress__label"><span>{label}</span><strong>{percent(normalized)}</strong></div>
      <div className="secretaria-progress__track"><span style={{ width: `${normalized}%` }} /></div>
    </div>
  )
}

function CandidateTable({
  data,
  loading,
  busyCode,
  emptyMessage,
  onOpen,
}: Readonly<{
  data: SecretariaCandidatesResponse
  loading: boolean
  busyCode: number | null
  emptyMessage: string
  onOpen: (candidate: SecretariaCandidate) => void
}>) {
  return (
    <div className="secretaria-table-wrap" aria-busy={loading}>
      <table className="secretaria-table">
        <thead>
          <tr>
            <th>Estudiante</th>
            <th>Carrera y período</th>
            <th>Etapa</th>
            <th>Avance académico</th>
            <th>Expediente</th>
            <th>Acción</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((candidate) => (
            <tr key={candidate.codigo_estud}>
              <td>
                <strong>{candidate.apellidos_nombres}</strong>
                <small>{candidate.numero_identificacion} · Código {candidate.codigo_estud}</small>
              </td>
              <td>
                <span>{candidate.nombre_carrera || 'Carrera sin descripción'}</span>
                <small>
                  {candidate.nombre_periodo || candidate.codigo_periodo || 'Período no registrado'} ·{' '}
                  Matrícula {enrollmentTypeLabel(candidate.tipo_matricula)}
                </small>
              </td>
              <td><span className={`secretaria-status secretaria-status--${statusTone(candidate.etapa_academica)}`}>{statusLabel(candidate.etapa_academica)}</span></td>
              <td>
                <strong>{integer(candidate.materias_aprobadas)} de {integer(candidate.materias_pensum)} materias</strong>
                <small>{percent(candidate.porcentaje_malla)} · Promedio: {decimal(candidate.promedio_aprobadas)}</small>
              </td>
              <td>
                {candidate.secretaria ? (
                  <>
                    <span className={`secretaria-status secretaria-status--${statusTone(candidate.secretaria.status)}`}>{statusLabel(candidate.secretaria.status)}</span>
                    <small>{quantityLabel(candidate.secretaria.missing, 'documento faltante', 'documentos faltantes')} · {percent(candidate.secretaria.progress)}</small>
                  </>
                ) : <span className="secretaria-muted">Sin abrir</span>}
              </td>
              <td>
                <button
                  type="button"
                  className="secretaria-button secretaria-button--secondary"
                  onClick={() => onOpen(candidate)}
                  disabled={loading || busyCode !== null}
                >
                  {busyCode === candidate.codigo_estud ? 'Abriendo...' : candidate.secretaria ? 'Revisar' : 'Abrir expediente'}
                </button>
              </td>
            </tr>
          ))}
          {!loading && data.items.length === 0 ? (
            <tr><td className="secretaria-empty" colSpan={6}>{emptyMessage}</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function DashboardMetric({
  view,
  activeView,
  label,
  value,
  description,
  onSelect,
}: Readonly<{
  view: SecretariaListView
  activeView: SecretariaListView
  label: string
  value: number | null | undefined
  description: string
  onSelect: (view: SecretariaListView) => void
}>) {
  const selected = view === activeView
  return (
    <button
      type="button"
      className={`secretaria-metric${selected ? ' secretaria-metric--active' : ''}`}
      role="tab"
      aria-selected={selected}
      aria-controls="secretaria-candidate-panel"
      onClick={() => onSelect(view)}
    >
      <span>{label}</span>
      <strong>{integer(value)}</strong>
      <small>{description}</small>
    </button>
  )
}

function PendingRequirement({
  requirement,
  observation,
}: Readonly<{
  requirement: SecretariaRequirement
  observation?: SecretariaObservation
}>) {
  const hasEvidence = Boolean(requirement.documento_presentado_id)
  const fallbackMessage = requirement.estado === 'FALTANTE'
    ? 'El documento obligatorio todavía no ha sido presentado.'
    : 'El documento requiere revisión o corrección antes de completar el expediente.'
  return (
    <article className="secretaria-pending-item">
      <div className="secretaria-pending-item__heading">
        <span className={`secretaria-status secretaria-status--${statusTone(requirement.estado)}`}>{statusLabel(requirement.estado)}</span>
        <strong>{requirement.tipo_documento}</strong>
      </div>
      <p>{requirement.instruccion}</p>
      <div className="secretaria-pending-item__reason">
        <span>Detalle pendiente</span>
        <strong>{observation?.observacion || requirement.observacion || fallbackMessage}</strong>
        {observation ? <small>{observation.usuario} · {dateTime(observation.fecha)}</small> : null}
      </div>
      {hasEvidence ? (
        <div className="secretaria-evidence">
          <div>
            <strong>{requirement.nombre_archivo || 'Evidencia institucional'}</strong>
            <small>
              Cargado por {requirement.usuario_carga || 'responsable no identificado'} ·{' '}
              {requirement.sistema_origen} {fileSize(requirement.tamano_bytes)} · {dateTime(requirement.fecha_documento)}
            </small>
          </div>
          {requirement.documento_graph_id ? (
            <a
              className="secretaria-button secretaria-button--link"
              href={documentExpedientFileUrl(requirement.documento_graph_id, 'open')}
              target="_blank"
              rel="noreferrer"
            >Abrir documento</a>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function RequirementRow({
  requirement,
  note,
  busy,
  onNoteChange,
  onReview,
}: Readonly<{
  requirement: SecretariaRequirement
  note: string
  busy: boolean
  onNoteChange: (value: string) => void
  onReview: (state: 'VALIDADO' | 'OBSERVADO') => void
}>) {
  const hasEvidence = Boolean(requirement.documento_presentado_id)
  return (
    <article className="secretaria-requirement">
      <div className="secretaria-requirement__document">
        <div className="secretaria-requirement__heading">
          <span className={`secretaria-status secretaria-status--${statusTone(requirement.estado)}`}>{statusLabel(requirement.estado)}</span>
          <strong>{requirement.tipo_documento}</strong>
        </div>
        <p>{requirement.instruccion}</p>
        {hasEvidence ? (
          <div className="secretaria-evidence">
            <div>
              <strong>{requirement.nombre_archivo || 'Evidencia institucional'}</strong>
              <small>
                Cargado por {requirement.usuario_carga || 'responsable no identificado'} ·{' '}
                {requirement.sistema_origen} {fileSize(requirement.tamano_bytes)} · {dateTime(requirement.fecha_documento)}
              </small>
            </div>
            {requirement.documento_graph_id ? (
              <a
                className="secretaria-button secretaria-button--link"
                href={documentExpedientFileUrl(requirement.documento_graph_id, 'open')}
                target="_blank"
                rel="noreferrer"
              >Abrir documento</a>
            ) : null}
          </div>
        ) : <p className="secretaria-missing-note">No se encontró ningún documento relacionado en las fuentes institucionales.</p>}
      </div>
      <div className="secretaria-requirement__review">
        <label htmlFor={`secretaria-note-${requirement.requisito_id}`}>Observación de revisión</label>
        <textarea
          id={`secretaria-note-${requirement.requisito_id}`}
          value={note}
          onChange={(event) => onNoteChange(event.target.value)}
          placeholder="Detalle la corrección requerida o el criterio aplicado"
          maxLength={1000}
          rows={3}
          disabled={busy}
        />
        <div className="secretaria-review-actions">
          <button
            type="button"
            className="secretaria-button secretaria-button--approve"
            onClick={() => onReview('VALIDADO')}
            disabled={busy || !hasEvidence}
            title={!hasEvidence ? 'Debe existir una evidencia antes de validar.' : undefined}
          >Validar</button>
          <button
            type="button"
            className="secretaria-button secretaria-button--observe"
            onClick={() => onReview('OBSERVADO')}
            disabled={busy || note.trim().length < 3}
          >Observar</button>
        </div>
      </div>
    </article>
  )
}

export function SecretariaGeneralView({ displayName, role }: Readonly<SecretariaGeneralViewProps>) {
  const [dashboard, setDashboard] = useState<SecretariaDashboardResponse | null>(null)
  const [candidates, setCandidates] = useState<SecretariaCandidatesResponse>(EMPTY_PAGE)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [listView, setListView] = useState<SecretariaListView>('TODOS')
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<SecretariaCaseDetailResponse | null>(null)
  const [pendingScreen, setPendingScreen] = useState(false)
  const [documentsScreen, setDocumentsScreen] = useState(false)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [busyCode, setBusyCode] = useState<number | null>(null)
  const [busyRequirement, setBusyRequirement] = useState<number | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [savingClassification, setSavingClassification] = useState(false)
  const [classificationDraft, setClassificationDraft] = useState<SecretariaHomologationClassification | ''>('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const workspaceRef = useRef<HTMLElement | null>(null)
  const activeStage: SecretariaStage = listView === 'FALTANTES' ? 'TODOS' : listView
  const activeViewCopy = LIST_VIEW_COPY[listView]
  const pendingRequirements = detail?.requirements.filter((requirement) => (
    requirement.es_obligatorio && PENDING_REQUIREMENT_STATES.has(requirement.estado)
  )) || []
  const missingRequirements = pendingRequirements.filter((requirement) => requirement.estado === 'FALTANTE').length
  const reviewRequirements = pendingRequirements.filter((requirement) => ['PRESENTE', 'EN_REVISION'].includes(requirement.estado)).length
  const observedRequirements = pendingRequirements.filter((requirement) => ['OBSERVADO', 'RECHAZADO'].includes(requirement.estado)).length
  const classificationPending = detail?.case.enrollment_type === 'H' && !detail.case.homologation_classification
  const totalPending = pendingRequirements.length + (classificationPending ? 1 : 0)

  useEffect(() => {
    setClassificationDraft(detail?.case.homologation_classification || '')
  }, [detail?.case.case_id, detail?.case.homologation_classification])

  const loadCandidates = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchSecretariaCandidates({
        search,
        stage: activeStage,
        onlyMissingDocuments: listView === 'FALTANTES',
        page,
        pageSize: 25,
      })
      setCandidates(result)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudieron cargar los candidatos.'))
    } finally {
      setLoading(false)
    }
  }, [activeStage, listView, page, search])

  const loadDashboard = useCallback(async () => {
    try {
      setDashboard(await fetchSecretariaDashboard())
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo cargar el resumen de Secretaría General.'))
    }
  }, [])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  useEffect(() => {
    void loadCandidates()
  }, [loadCandidates])

  async function openCandidate(candidate: SecretariaCandidate) {
    setBusyCode(candidate.codigo_estud)
    setError('')
    setMessage('')
    try {
      const result = await ensureSecretariaCase(candidate.codigo_estud)
      setDetail(result)
      setPendingScreen(false)
      setNotes(Object.fromEntries(result.requirements.map((item) => [item.requisito_id, item.observacion || ''])))
      setMessage(result.created ? 'Expediente abierto y conciliado correctamente.' : 'Expediente actualizado con las fuentes institucionales.')
      await loadDashboard()
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo abrir el expediente.'))
    } finally {
      setBusyCode(null)
    }
  }

  async function synchronize() {
    if (!detail) return
    setSyncing(true)
    setError('')
    setMessage('')
    try {
      const result = await syncSecretariaCase(detail.case.case_id)
      setDetail(result)
      setNotes(Object.fromEntries(result.requirements.map((item) => [item.requisito_id, item.observacion || ''])))
      const synchronized = result.sync?.synchronized ?? 0
      setMessage(`Conciliación terminada: ${quantityLabel(synchronized, 'evidencia relacionada', 'evidencias relacionadas')}.`)
      await loadDashboard()
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo sincronizar el expediente.'))
    } finally {
      setSyncing(false)
    }
  }

  async function review(requirement: SecretariaRequirement, nextState: 'VALIDADO' | 'OBSERVADO') {
    if (!detail) return
    const note = notes[requirement.requisito_id]?.trim() || ''
    setBusyRequirement(requirement.requisito_id)
    setError('')
    setMessage('')
    try {
      const result = await reviewSecretariaRequirement(detail.case.case_id, requirement.requisito_id, {
        estado: nextState,
        observacion: note,
        documento_presentado_id: requirement.documento_presentado_id,
      })
      setDetail(result)
      setNotes(Object.fromEntries(result.requirements.map((item) => [item.requisito_id, item.observacion || ''])))
      setMessage(nextState === 'VALIDADO' ? 'Documento validado.' : 'Observación registrada en el expediente.')
      await loadDashboard()
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo guardar la revisión.'))
    } finally {
      setBusyRequirement(null)
    }
  }

  async function saveHomologationClassification() {
    if (!detail || !classificationDraft) {
      setError('Seleccione el tipo de homologación antes de guardar.')
      return
    }
    setSavingClassification(true)
    setError('')
    setMessage('')
    try {
      const result = await updateSecretariaHomologationClassification(
        detail.case.case_id,
        classificationDraft,
      )
      setDetail(result)
      setNotes(Object.fromEntries(result.requirements.map((item) => [item.requisito_id, item.observacion || ''])))
      setMessage('Clasificación de homologación guardada y requisitos actualizados.')
      await loadDashboard()
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo guardar la clasificación de homologación.'))
    } finally {
      setSavingClassification(false)
    }
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setSearch(searchInput.trim())
  }

  function selectListView(nextView: SecretariaListView) {
    setListView(nextView)
    setPage(1)
    setError('')
    setMessage('')
    window.requestAnimationFrame(() => {
      workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  if (detail && documentsScreen) {
    return (
      <section className="secretaria-page">
        <ExpedientesDocumentalesView
          displayName={displayName}
          role={role}
          initialIdentification={detail.case.numero_identificacion}
          moduleFilter={['SECRETARIA']}
          documentTypeFilter={detail.requirements.map((requirement) => requirement.tipo_documento_codigo)}
          embedded
          embeddedTitle="Documentos de Secretaría General"
          embeddedDescription="Cargue los documentos oficiales del estudiante. Cada archivo conserva la fecha y el usuario responsable de la carga."
          onClose={() => {
            setDocumentsScreen(false)
            void synchronize()
          }}
        />
      </section>
    )
  }

  if (detail && pendingScreen) {
    return (
      <section className="secretaria-page">
        <header className="secretaria-hero secretaria-hero--detail">
          <div>
            <span className="secretaria-eyebrow">Secretaría General · {detail.case.case_code}</span>
            <h1>Pendientes del expediente</h1>
            <p>{detail.case.apellidos_nombres} · {detail.case.numero_identificacion} · Código {detail.case.codigo_estud}</p>
          </div>
          <div className="secretaria-hero__actions">
            <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => setPendingScreen(false)}>Volver al expediente</button>
            <button type="button" className="secretaria-button secretaria-button--primary" onClick={() => setDocumentsScreen(true)}>Gestionar documentos</button>
          </div>
        </header>

        {error ? <div className="secretaria-alert secretaria-alert--error" role="alert">{error}</div> : null}
        {message ? <div className="secretaria-alert secretaria-alert--success" role="status">{message}</div> : null}

        <div className="secretaria-pending-summary">
          <div><span>Total pendiente</span><strong>{integer(totalPending)}</strong><small>Requisitos obligatorios sin validar</small></div>
          <div><span>Falta cargar</span><strong>{integer(missingRequirements)}</strong><small>Sin evidencia relacionada</small></div>
          <div><span>Por revisar</span><strong>{integer(reviewRequirements)}</strong><small>Con evidencia presentada</small></div>
          <div><span>Observados</span><strong>{integer(observedRequirements)}</strong><small>Requieren corrección</small></div>
        </div>

        <section className="secretaria-pending-panel">
          <div className="secretaria-section-heading">
            <div>
              <span className="secretaria-eyebrow">Lista de pendientes</span>
              <h2>Documentos por completar</h2>
              <p>{quantityLabel(totalPending, 'requisito pendiente', 'requisitos pendientes')} en este expediente.</p>
            </div>
          </div>
          <div className="secretaria-pending-list">
            {classificationPending ? (
              <article className="secretaria-pending-item">
                <div className="secretaria-pending-item__heading">
                  <span className="secretaria-status secretaria-status--warning">Faltante</span>
                  <strong>Clasificación normativa de homologación</strong>
                </div>
                <p>Seleccione si corresponde al artículo 81, 82 o 83 para habilitar el respaldo aplicable.</p>
                <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => setPendingScreen(false)}>
                  Clasificar expediente
                </button>
              </article>
            ) : null}
            {pendingRequirements.map((requirement) => (
              <PendingRequirement
                key={requirement.requisito_id}
                requirement={requirement}
                observation={detail.observations.find((item) => item.requisito_id === requirement.requisito_id)}
              />
            ))}
            {totalPending === 0 ? (
              <div className="secretaria-pending-empty"><strong>Expediente sin pendientes</strong><span>Todos los requisitos obligatorios se encuentran validados.</span></div>
            ) : null}
          </div>
        </section>
      </section>
    )
  }

  if (detail) {
    return (
      <section className="secretaria-page">
        <header className="secretaria-hero secretaria-hero--detail">
          <div>
            <span className="secretaria-eyebrow">Secretaría General · {detail.case.case_code}</span>
            <h1>{detail.case.apellidos_nombres}</h1>
            <p>{detail.case.numero_identificacion} · Código {detail.case.codigo_estud} · {detail.case.nombre_carrera}</p>
          </div>
          <div className="secretaria-hero__actions">
            <button
              type="button"
              className="secretaria-button secretaria-button--pending"
              onClick={() => setPendingScreen(true)}
              disabled={totalPending === 0}
            >
              <span>Pendientes</span>
              <strong>{integer(totalPending)}</strong>
            </button>
            <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => { setPendingScreen(false); setDetail(null); setMessage(''); void loadCandidates() }}>Volver al listado</button>
            <button type="button" className="secretaria-button secretaria-button--primary" onClick={() => void synchronize()} disabled={syncing}>{syncing ? 'Actualizando...' : 'Actualizar evidencias'}</button>
          </div>
        </header>

        {error ? <div className="secretaria-alert secretaria-alert--error" role="alert">{error}</div> : null}
        {message ? <div className="secretaria-alert secretaria-alert--success" role="status">{message}</div> : null}

        <div className="secretaria-detail-summary">
          <div>
            <span className={`secretaria-status secretaria-status--${statusTone(detail.case.stage)}`}>{statusLabel(detail.case.stage)}</span>
            <strong>{integer(detail.case.approved_subjects)} de {integer(detail.case.required_subjects)} materias aprobadas</strong>
            <small>
              {detail.case.nombre_periodo || 'Sin período de referencia'} · Matrícula{' '}
              {enrollmentTypeLabel(detail.case.enrollment_type)} · Promedio: {decimal(detail.case.average)}
            </small>
          </div>
          <ProgressBar value={detail.case.academic_progress} label="Avance académico" />
          <ProgressBar value={detail.case.document_progress} label="Cumplimiento documental" />
          <div className="secretaria-detail-summary__counts">
            <strong>{integer(detail.case.validated_documents)}/{integer(detail.case.required_documents)}</strong>
            <small>{detail.case.validated_documents === 1 ? 'documento validado' : 'documentos validados'}</small>
            <span>
              {quantityLabel(detail.case.missing_documents, 'documento faltante', 'documentos faltantes')} ·{' '}
              {quantityLabel(detail.case.observed_documents, 'documento observado', 'documentos observados')}
            </span>
          </div>
        </div>

        {detail.case.enrollment_type === 'H' ? (
          <section className={`secretaria-homologation${classificationPending ? ' secretaria-homologation--pending' : ''}`}>
            <div>
              <span className="secretaria-eyebrow">Regla documental de homologación</span>
              <h2>Clasificación por artículo</h2>
              <p>La clasificación habilita únicamente el respaldo normativo que corresponde al expediente.</p>
            </div>
            <label htmlFor="secretaria-homologation-classification">
              <span>Condición de homologación</span>
              <select
                id="secretaria-homologation-classification"
                value={classificationDraft}
                onChange={(event) => setClassificationDraft(event.target.value as SecretariaHomologationClassification | '')}
                disabled={savingClassification}
              >
                <option value="">Seleccione una condición</option>
                {HOMOLOGATION_CLASSIFICATIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <small>{HOMOLOGATION_CLASSIFICATIONS.find((option) => option.value === classificationDraft)?.detail || 'Pendiente de clasificación por Secretaría.'}</small>
            </label>
            <button
              type="button"
              className="secretaria-button secretaria-button--primary"
              onClick={() => void saveHomologationClassification()}
              disabled={!classificationDraft || savingClassification || classificationDraft === detail.case.homologation_classification}
            >
              {savingClassification ? 'Guardando...' : 'Guardar clasificación'}
            </button>
          </section>
        ) : null}

        <div className="secretaria-section-heading">
          <div>
            <span className="secretaria-eyebrow">Lista de verificación documental</span>
            <h2>Validación del expediente</h2>
            <p>Cada validación conserva la evidencia, el responsable, la fecha y la observación en el registro de auditoría.</p>
          </div>
          <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => setDocumentsScreen(true)}>Gestionar documentos</button>
        </div>

        <div className="secretaria-requirements">
          {detail.requirements.map((requirement) => (
            <RequirementRow
              key={requirement.requisito_id}
              requirement={requirement}
              note={notes[requirement.requisito_id] || ''}
              busy={busyRequirement === requirement.requisito_id}
              onNoteChange={(value) => setNotes((current) => ({ ...current, [requirement.requisito_id]: value }))}
              onReview={(stateValue) => void review(requirement, stateValue)}
            />
          ))}
        </div>

      </section>
    )
  }

  return (
    <section className="secretaria-page">
      <header className="secretaria-hero">
        <div>
          <span className="secretaria-eyebrow">Secretaría General</span>
          <h1>Verificación de expedientes de grado</h1>
          <p>Control documental de estudiantes próximos a graduarse, egresados y graduados.</p>
        </div>
        <aside><strong>{displayName}</strong><span>Revisión institucional</span></aside>
      </header>

      <div className="secretaria-metrics" role="tablist" aria-label="Detalle de indicadores de Secretaría General">
        <DashboardMetric view="TODOS" activeView={listView} label="Candidatos" value={dashboard?.candidates.total} description="Registrados en INTECBDD" onSelect={selectListView} />
        <DashboardMetric view="PROXIMO" activeView={listView} label="Próximos a graduarse" value={dashboard?.candidates.proximos} description="De 20 a 23 materias aprobadas" onSelect={selectListView} />
        <DashboardMetric view="EGRESADO" activeView={listView} label="Egresados" value={dashboard?.candidates.egresados} description="Con la malla curricular completa" onSelect={selectListView} />
        <DashboardMetric view="GRADUADO" activeView={listView} label="Graduados" value={dashboard?.candidates.graduados} description="Con estado académico o fecha de grado" onSelect={selectListView} />
        <DashboardMetric
          view="FALTANTES"
          activeView={listView}
          label="Documentos faltantes"
          value={dashboard?.cases.documentos_faltantes}
          description={dashboard ? quantityLabel(dashboard.cases.estudiantes_con_faltantes, 'estudiante pendiente', 'estudiantes pendientes') : 'En expedientes abiertos'}
          onSelect={selectListView}
        />
      </div>

      {error ? <div className="secretaria-alert secretaria-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="secretaria-alert secretaria-alert--success" role="status">{message}</div> : null}

      <section id="secretaria-candidate-panel" ref={workspaceRef} className="secretaria-workspace" role="tabpanel">
        <div className="secretaria-section-heading">
          <div>
            <span className="secretaria-eyebrow">Detalle del indicador</span>
            <h2>{activeViewCopy.title}</h2>
            <p>{quantityLabel(candidates.total, 'registro encontrado', 'registros encontrados')} con los filtros actuales.</p>
          </div>
        </div>
        <form className="secretaria-filters" onSubmit={submitSearch}>
          <label>
            <span>Buscar estudiante</span>
            <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Nombres y apellidos, cédula, código o carrera" maxLength={120} />
          </label>
          <label>
            <span>Vista de estudiantes</span>
            <select value={listView} onChange={(event) => selectListView(event.target.value as SecretariaListView)}>
              <option value="TODOS">Todas</option>
              <option value="PROXIMO">Próximos a graduarse</option>
              <option value="EGRESADO">Egresados</option>
              <option value="GRADUADO">Graduados</option>
              <option value="FALTANTES">Con documentos faltantes</option>
            </select>
          </label>
          <button type="submit" className="secretaria-button secretaria-button--primary" disabled={loading}>{loading ? 'Consultando...' : 'Buscar'}</button>
        </form>

        <CandidateTable
          data={candidates}
          loading={loading}
          busyCode={busyCode}
          emptyMessage={activeViewCopy.empty}
          onOpen={(candidate) => void openCandidate(candidate)}
        />
        <div className="secretaria-pagination">
          <span>Página {candidates.page} de {candidates.total_pages}</span>
          <div>
            <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={loading || page <= 1}>Anterior</button>
            <button type="button" className="secretaria-button secretaria-button--secondary" onClick={() => setPage((current) => Math.min(candidates.total_pages, current + 1))} disabled={loading || page >= candidates.total_pages}>Siguiente</button>
          </div>
        </div>
      </section>
    </section>
  )
}
