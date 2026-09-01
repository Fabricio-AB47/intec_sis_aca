import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import {
  applyCareerChangeRequest,
  createCareerChangeRequest,
  decideCareerChangeRequest,
  fetchCareerChangeCatalog,
  fetchCareerChangeRequestDetail,
  fetchCareerChangeRequests,
  previewCareerChange,
  restoreCareerChangeBackup,
} from '../../lib/api'
import type {
  CareerChangeCatalogResponse,
  CareerChangeCatalogStudent,
  CareerChangeMatch,
  CareerChangePreviewResponse,
  CareerChangeRequestDetail,
  CareerChangeRequestItem,
} from '../../types/app'
import './CareerChangeRequestsView.css'

type CareerChangeRequestsViewProps = {
  displayName: string
  role: string
}

type ViewTab = 'NUEVA' | 'HISTORIAL'

const EMPTY_CATALOG: CareerChangeCatalogResponse = {
  students: [],
  careers: [],
  periods: [],
  states: ['PENDIENTE', 'APROBADA', 'RECHAZADA', 'APLICADA'],
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function normalizeRole(role: string): string {
  return role
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toUpperCase()
}

function pairKey(match: CareerChangeMatch): string {
  return `${match.source.codigo_materia}:${match.target.codigo_materia}`
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatGrade(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-EC')
}

function matchLabel(type: CareerChangeMatch['tipo_coincidencia']): string {
  if (type === 'CODIGO_EXACTO') return 'Código exacto'
  if (type === 'NOMBRE_EXACTO') return 'Nombre exacto'
  return 'Nombre similar'
}

function stateLabel(state: string): string {
  const labels: Record<string, string> = {
    PENDIENTE: 'Pendiente',
    APROBADA: 'Aprobada',
    RECHAZADA: 'Rechazada',
    APLICADA: 'Aplicada',
  }
  return labels[state] || state
}

export function CareerChangeRequestsView({ displayName, role }: Readonly<CareerChangeRequestsViewProps>) {
  const canReview = ['ADMINISTRADOR', 'ACADEMICO'].includes(normalizeRole(role))
  const [tab, setTab] = useState<ViewTab>('NUEVA')
  const [catalog, setCatalog] = useState<CareerChangeCatalogResponse>(EMPTY_CATALOG)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [studentQuery, setStudentQuery] = useState('')
  const [studentSearchLoading, setStudentSearchLoading] = useState(false)
  const [selectedStudent, setSelectedStudent] = useState<CareerChangeCatalogStudent | null>(null)
  const [targetCareerCode, setTargetCareerCode] = useState('')
  const [targetPeriodCode, setTargetPeriodCode] = useState('')
  const [preview, setPreview] = useState<CareerChangePreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [selectedPairs, setSelectedPairs] = useState<Set<string>>(new Set())
  const [motive, setMotive] = useState('')
  const [supportFile, setSupportFile] = useState<File | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [saving, setSaving] = useState(false)

  const [requests, setRequests] = useState<CareerChangeRequestItem[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')
  const [historyState, setHistoryState] = useState('TODOS')
  const [detail, setDetail] = useState<CareerChangeRequestDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [reviewObservation, setReviewObservation] = useState('')
  const [restoreConfirmation, setRestoreConfirmation] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [requestsError, setRequestsError] = useState('')
  const [success, setSuccess] = useState('')

  const availableCareers = useMemo(
    () => catalog.careers.filter((career) => career.codigo !== selectedStudent?.carrera),
    [catalog.careers, selectedStudent?.carrera],
  )

  const selectedMatches = useMemo(
    () => preview?.matches.filter((match) => selectedPairs.has(pairKey(match))) ?? [],
    [preview, selectedPairs],
  )

  const loadCatalog = useCallback(async (query = '') => {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const response = await fetchCareerChangeCatalog(query)
      setCatalog(response)
    } catch (apiError) {
      setCatalogError(errorMessage(apiError, 'No se pudo cargar el catálogo académico.'))
    } finally {
      setCatalogLoading(false)
    }
  }, [])

  const loadRequests = useCallback(async () => {
    setRequestsLoading(true)
    setRequestsError('')
    try {
      const response = await fetchCareerChangeRequests({ query: historyQuery, state: historyState, limit: 200 })
      setRequests(response.items)
    } catch (apiError) {
      setRequestsError(errorMessage(apiError, 'No se pudo cargar el historial de solicitudes.'))
    } finally {
      setRequestsLoading(false)
    }
  }, [historyQuery, historyState])

  useEffect(() => {
    void loadCatalog()
    void loadRequests()
  }, [loadCatalog, loadRequests])

  useEffect(() => {
    if (!success) return undefined
    const timeout = window.setTimeout(() => setSuccess(''), 3000)
    return () => window.clearTimeout(timeout)
  }, [success])

  async function searchStudent() {
    const query = studentQuery.trim()
    if (query.length < 2) {
      setActionError('Ingrese al menos dos caracteres del nombre, la cédula o el código del estudiante.')
      return
    }
    setActionError('')
    setStudentSearchLoading(true)
    try {
      const response = await fetchCareerChangeCatalog(query)
      setCatalog(response)
      setCatalogError('')
      if (response.students.length === 0) {
        setActionError('No se encontraron estudiantes con el criterio indicado.')
      }
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo buscar el estudiante.'))
    } finally {
      setStudentSearchLoading(false)
    }
  }

  function chooseStudent(student: CareerChangeCatalogStudent) {
    setSelectedStudent(student)
    setTargetCareerCode('')
    setTargetPeriodCode('')
    setPreview(null)
    setSelectedPairs(new Set())
    setActionError('')
  }

  async function analyzeEquivalences() {
    if (!selectedStudent || !targetCareerCode) {
      setActionError('Seleccione el estudiante y la carrera de destino.')
      return
    }
    setActionError('')
    setPreviewLoading(true)
    try {
      const response = await previewCareerChange({
        codigo_estud: selectedStudent.codigo_estud,
        carrera_destino: Number(targetCareerCode),
      })
      setPreview(response)
      setSelectedPairs(
        new Set(response.matches.filter((match) => match.seleccion_recomendada).map((match) => pairKey(match))),
      )
    } catch (apiError) {
      setPreview(null)
      setSelectedPairs(new Set())
      setActionError(errorMessage(apiError, 'No se pudo analizar el historial académico.'))
    } finally {
      setPreviewLoading(false)
    }
  }

  function toggleMatch(match: CareerChangeMatch) {
    const key = pairKey(match)
    setSelectedPairs((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function chooseSupportFile(file: File | null) {
    setActionError('')
    if (!file) {
      setSupportFile(null)
      return
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setSupportFile(null)
      setFileInputKey((current) => current + 1)
      setActionError('El documento de respaldo debe estar en formato PDF.')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      setSupportFile(null)
      setFileInputKey((current) => current + 1)
      setActionError('El documento de respaldo no puede superar 20 MB.')
      return
    }
    setSupportFile(file)
  }

  async function submitRequest(event: FormEvent) {
    event.preventDefault()
    if (!selectedStudent || !targetCareerCode || !targetPeriodCode || !preview) {
      setActionError('Complete la selección académica y analice las equivalencias antes de registrar la solicitud.')
      return
    }
    if (motive.trim().length < 10) {
      setActionError('Registre un motivo de al menos 10 caracteres.')
      return
    }
    if (!supportFile) {
      setActionError('Adjunte el documento PDF que respalda la solicitud.')
      return
    }

    const formData = new FormData()
    formData.append('codigo_estud', String(selectedStudent.codigo_estud))
    formData.append('carrera_destino', targetCareerCode)
    formData.append('codigo_periodo_destino', targetPeriodCode)
    formData.append('motivo', motive.trim())
    formData.append(
      'equivalencias_json',
      JSON.stringify(
        selectedMatches.map((match) => ({
          source_codigo_materia: match.source.codigo_materia,
          target_codigo_materia: match.target.codigo_materia,
        })),
      ),
    )
    formData.append('archivo', supportFile)

    setSaving(true)
    setActionError('')
    try {
      const response = await createCareerChangeRequest(formData)
      setSuccess(response.message)
      setSelectedStudent(null)
      setStudentQuery('')
      setTargetCareerCode('')
      setTargetPeriodCode('')
      setPreview(null)
      setSelectedPairs(new Set())
      setMotive('')
      setSupportFile(null)
      setFileInputKey((current) => current + 1)
      changeTab('HISTORIAL')
      await loadRequests()
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo registrar la solicitud.'))
    } finally {
      setSaving(false)
    }
  }

  async function openDetail(item: CareerChangeRequestItem) {
    setDetailLoading(true)
    setActionError('')
    try {
      const response = await fetchCareerChangeRequestDetail(item.id)
      setDetail(response)
      setReviewObservation(response.observacion_revision || '')
      setRestoreConfirmation(false)
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo abrir la solicitud.'))
    } finally {
      setDetailLoading(false)
    }
  }

  async function registerDecision(decision: 'APROBADA' | 'RECHAZADA') {
    if (!detail) return
    if (decision === 'RECHAZADA' && reviewObservation.trim().length < 5) {
      setActionError('Registre el motivo del rechazo antes de continuar.')
      return
    }
    setActionLoading(true)
    setActionError('')
    try {
      const response = await decideCareerChangeRequest(detail.id, decision, reviewObservation.trim())
      setSuccess(response.message)
      const updated = await fetchCareerChangeRequestDetail(detail.id)
      setDetail(updated)
      await loadRequests()
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo registrar la decisión.'))
    } finally {
      setActionLoading(false)
    }
  }

  async function applyApprovedRequest() {
    if (!detail) return
    setActionLoading(true)
    setActionError('')
    try {
      const response = await applyCareerChangeRequest(detail.id)
      setSuccess(response.message)
      const updated = await fetchCareerChangeRequestDetail(detail.id)
      setDetail(updated)
      await loadRequests()
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo aplicar el cambio de carrera.'))
    } finally {
      setActionLoading(false)
    }
  }

  async function restorePreviousCareer() {
    if (!detail) return
    setActionLoading(true)
    setActionError('')
    try {
      const response = await restoreCareerChangeBackup(detail.id)
      setSuccess(response.message)
      setRestoreConfirmation(false)
      const updated = await fetchCareerChangeRequestDetail(detail.id)
      setDetail(updated)
      await loadRequests()
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo recuperar la carrera anterior.'))
    } finally {
      setActionLoading(false)
    }
  }

  function changeTab(nextTab: ViewTab) {
    setTab(nextTab)
    setActionError('')
  }

  function refreshHistory() {
    setActionError('')
    void loadRequests()
  }

  return (
    <main className="career-change-page">
      <header className="career-change-hero">
        <div>
          <span className="career-change-eyebrow">SOLICITUDES</span>
          <h1>Cambio de carrera</h1>
          <p>Gestión de equivalencias académicas y respaldo documental.</p>
        </div>
        <aside>
          <strong>{displayName}</strong>
          <span>{canReview ? 'Revisión académica' : 'Registro de solicitudes'}</span>
        </aside>
      </header>

      <nav className="career-change-tabs" aria-label="Apartados de cambio de carrera">
        <button type="button" className={tab === 'NUEVA' ? 'is-active' : ''} onClick={() => changeTab('NUEVA')}>
          Nueva solicitud
        </button>
        <button type="button" className={tab === 'HISTORIAL' ? 'is-active' : ''} onClick={() => changeTab('HISTORIAL')}>
          Historial y revisión
        </button>
      </nav>

      {actionError ? <div className="career-change-alert career-change-alert--error">{actionError}</div> : null}
      {tab === 'NUEVA' && catalogError ? (
        <div className="career-change-alert career-change-alert--error">{catalogError}</div>
      ) : null}
      {tab === 'HISTORIAL' && requestsError ? (
        <div className="career-change-alert career-change-alert--error">{requestsError}</div>
      ) : null}
      {success ? <div className="career-change-toast" role="status">{success}</div> : null}

      {tab === 'NUEVA' ? (
        <form className="career-change-workflow" onSubmit={submitRequest}>
          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>1</span>
              <div>
                <h2>Estudiante</h2>
                <p>Busque por nombre, cédula o código.</p>
              </div>
            </div>
            <div className="career-change-search-row">
              <label>
                Buscar estudiante
                <input
                  type="search"
                  value={studentQuery}
                  onChange={(event) => setStudentQuery(event.target.value)}
                  placeholder="Nombre, cédula o código"
                />
              </label>
              <button type="button" className="career-change-button career-change-button--primary" onClick={searchStudent} disabled={studentSearchLoading}>
                {studentSearchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {catalog.students.length > 0 ? (
              <div className="career-change-student-results">
                {catalog.students.map((student) => (
                  <button
                    type="button"
                    key={student.codigo_estud}
                    className={selectedStudent?.codigo_estud === student.codigo_estud ? 'is-selected' : ''}
                    onClick={() => chooseStudent(student)}
                  >
                    <strong>{student.estudiante}</strong>
                    <span>{student.cedula} · Código {student.codigo_estud}</span>
                    <span>{student.carrera_nombre || 'Sin carrera registrada'} · Estado {student.estado || '-'}</span>
                  </button>
                ))}
              </div>
            ) : null}

            {selectedStudent ? (
              <div className="career-change-selected-student">
                <div><span>Estudiante</span><strong>{selectedStudent.estudiante}</strong></div>
                <div><span>Cédula</span><strong>{selectedStudent.cedula}</strong></div>
                <div><span>Carrera actual</span><strong>{selectedStudent.carrera_nombre}</strong></div>
                <div><span>Estado</span><strong>{selectedStudent.estado || '-'}</strong></div>
              </div>
            ) : null}
          </section>

          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>2</span>
              <div>
                <h2>Destino académico</h2>
                <p>Seleccione la nueva carrera y el período de matrícula.</p>
              </div>
            </div>
            <div className="career-change-fields career-change-fields--destination">
              <label>
                Carrera de destino
                <select
                  value={targetCareerCode}
                  onChange={(event) => {
                    setTargetCareerCode(event.target.value)
                    setPreview(null)
                    setSelectedPairs(new Set())
                  }}
                  disabled={!selectedStudent || catalogLoading}
                >
                  <option value="">Seleccione una carrera</option>
                  {availableCareers.map((career) => <option key={career.codigo} value={career.codigo}>{career.nombre}</option>)}
                </select>
              </label>
              <label>
                Período de destino
                <select value={targetPeriodCode} onChange={(event) => setTargetPeriodCode(event.target.value)} disabled={!selectedStudent || catalogLoading}>
                  <option value="">Seleccione un período</option>
                  {catalog.periods.map((period) => <option key={period.codigo} value={period.codigo}>{period.nombre}</option>)}
                </select>
              </label>
              <button
                type="button"
                className="career-change-button career-change-button--primary"
                onClick={analyzeEquivalences}
                disabled={!selectedStudent || !targetCareerCode || previewLoading}
              >
                {previewLoading ? 'Analizando...' : 'Analizar equivalencias'}
              </button>
            </div>
          </section>

          {preview ? (
            <section className="career-change-section">
              <div className="career-change-section__heading">
                <span>3</span>
                <div>
                  <h2>Equivalencias propuestas</h2>
                  <p>Las coincidencias por similitud requieren selección manual.</p>
                </div>
              </div>
              <div className="career-change-summary">
                <div><span>Aprobadas en origen</span><strong>{formatNumber(preview.summary.aprobadas_origen)}</strong></div>
                <div><span>Coincidencias exactas</span><strong>{formatNumber(preview.summary.equivalencias_exactas)}</strong></div>
                <div><span>Coincidencias similares</span><strong>{formatNumber(preview.summary.equivalencias_similares)}</strong></div>
                <div><span>Sin equivalencia</span><strong>{formatNumber(preview.summary.materias_destino_sin_equivalencia)}</strong></div>
              </div>

              <div className="career-change-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Convalidar</th>
                      <th>Materia cursada</th>
                      <th>Nota</th>
                      <th>Materia destino</th>
                      <th>Coincidencia</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.matches.length ? preview.matches.map((match) => (
                      <tr key={pairKey(match)}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedPairs.has(pairKey(match))}
                            onChange={() => toggleMatch(match)}
                            aria-label={`Convalidar ${match.target.nombre}`}
                          />
                        </td>
                        <td>
                          <strong>{match.source.nombre}</strong>
                          <small>{match.source.codigo_comun || `Código ${match.source.codigo_materia}`} · {match.source.periodo_nombre || 'Período no registrado'}</small>
                        </td>
                        <td><strong>{formatGrade(match.source.nota_final)}</strong></td>
                        <td>
                          <strong>{match.target.nombre}</strong>
                          <small>{match.target.codigo_comun || `Código ${match.target.codigo_materia}`} · Nivel {match.target.nivel ?? '-'}</small>
                        </td>
                        <td>
                          <span className={`career-change-match career-change-match--${match.tipo_coincidencia.toLowerCase()}`}>
                            {matchLabel(match.tipo_coincidencia)}
                          </span>
                          <small>{Math.round(match.similitud * 100)} %</small>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={5} className="career-change-empty">No se encontraron equivalencias académicas.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {preview.unmatched_targets.length ? (
                <details className="career-change-unmatched">
                  <summary>{preview.unmatched_targets.length} materia(s) del pénsum destino sin equivalencia</summary>
                  <div>
                    {preview.unmatched_targets.map((subject) => (
                      <span key={subject.codigo_materia}>{subject.nombre} · Nivel {subject.nivel ?? '-'}</span>
                    ))}
                  </div>
                </details>
              ) : null}
            </section>
          ) : null}

          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>4</span>
              <div>
                <h2>Solicitud y respaldo</h2>
                <p>El documento PDF se conserva junto con la trazabilidad del trámite.</p>
              </div>
            </div>
            <div className="career-change-fields career-change-fields--support">
              <label>
                Motivo de la solicitud
                <textarea value={motive} onChange={(event) => setMotive(event.target.value)} maxLength={1000} rows={4} placeholder="Detalle el motivo del cambio de carrera" />
              </label>
              <label>
                Documento de respaldo (PDF)
                <input key={fileInputKey} type="file" accept="application/pdf,.pdf" onChange={(event) => chooseSupportFile(event.target.files?.[0] || null)} />
                <small>{supportFile ? `${supportFile.name} · ${(supportFile.size / 1024 / 1024).toFixed(2)} MB` : 'Archivo obligatorio. Máximo 20 MB.'}</small>
              </label>
            </div>
            <div className="career-change-submit-row">
              <span>{selectedMatches.length} equivalencia(s) seleccionada(s)</span>
              <button type="submit" className="career-change-button career-change-button--primary" disabled={saving || !preview || !targetPeriodCode}>
                {saving ? 'Registrando...' : 'Registrar solicitud'}
              </button>
            </div>
          </section>
        </form>
      ) : (
        <section className="career-change-section career-change-history">
          <div className="career-change-section__heading">
            <span>H</span>
            <div>
              <h2>Historial de solicitudes</h2>
              <p>{requests.length} registro(s) con los filtros actuales.</p>
            </div>
          </div>
          <div className="career-change-history-controls">
            <label>
              Buscar
              <input type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Estudiante, cédula o solicitud" />
            </label>
            <label>
              Estado
              <select value={historyState} onChange={(event) => setHistoryState(event.target.value)}>
                <option value="TODOS">Todos</option>
                {catalog.states.map((state) => <option key={state} value={state}>{stateLabel(state)}</option>)}
              </select>
            </label>
            <button type="button" className="career-change-button" onClick={refreshHistory} disabled={requestsLoading}>
              {requestsLoading ? 'Actualizando...' : 'Actualizar'}
            </button>
          </div>
          <div className="career-change-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Solicitud</th>
                  <th>Estudiante</th>
                  <th>Cambio solicitado</th>
                  <th>Período</th>
                  <th>Equivalencias</th>
                  <th>Estado</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {requestsLoading ? (
                  <tr><td colSpan={7} className="career-change-empty">Consultando solicitudes...</td></tr>
                ) : requests.length ? requests.map((item) => (
                  <tr key={item.id}>
                    <td><strong>#{item.id}</strong><small>{formatDate(item.fecha_creacion)}</small></td>
                    <td><strong>{item.estudiante}</strong><small>{item.cedula} · Código {item.codigo_estud}</small></td>
                    <td><span>{item.carrera_origen_nombre}</span><strong>{item.carrera_destino_nombre}</strong></td>
                    <td>{item.periodo_destino_nombre}</td>
                    <td>{item.equivalencias}</td>
                    <td><span className={`career-change-state career-change-state--${item.estado.toLowerCase()}`}>{stateLabel(item.estado)}</span></td>
                    <td><button type="button" className="career-change-button" onClick={() => openDetail(item)}>Revisar</button></td>
                  </tr>
                )) : (
                  <tr><td colSpan={7} className="career-change-empty">No existen solicitudes con los filtros actuales.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {detailLoading ? <div className="career-change-loading-overlay" role="status">Abriendo solicitud...</div> : null}

      {detail ? (
        <div className="career-change-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !actionLoading) setDetail(null)
        }}>
          <section className="career-change-modal" role="dialog" aria-modal="true" aria-labelledby="career-change-detail-title">
            <header>
              <div>
                <span>DETALLE DE SOLICITUD #{detail.id}</span>
                <h2 id="career-change-detail-title">{detail.estudiante}</h2>
                <p>{detail.cedula} · Código {detail.codigo_estud}</p>
              </div>
              <button type="button" className="career-change-button" onClick={() => setDetail(null)} disabled={actionLoading}>Cerrar</button>
            </header>

            <div className="career-change-modal__body">
              <div className="career-change-detail-grid">
                <div><span>Origen</span><strong>{detail.carrera_origen_nombre}</strong></div>
                <div><span>Destino</span><strong>{detail.carrera_destino_nombre}</strong></div>
                <div><span>Período destino</span><strong>{detail.periodo_destino_nombre}</strong></div>
                <div><span>Estado</span><strong className={`career-change-state career-change-state--${detail.estado.toLowerCase()}`}>{stateLabel(detail.estado)}</strong></div>
                <div><span>Registrada por</span><strong>{detail.creado_por}</strong><small>{formatDate(detail.fecha_creacion)}</small></div>
                <div><span>Revisada por</span><strong>{detail.revisado_por || '-'}</strong><small>{formatDate(detail.fecha_revision)}</small></div>
              </div>

              <section className="career-change-detail-block">
                <div>
                  <h3>Motivo y respaldo</h3>
                  {detail.archivo_url ? (
                    <a className="career-change-button" href={detail.archivo_url} target="_blank" rel="noreferrer">Abrir PDF</a>
                  ) : null}
                </div>
                <small>
                  {detail.archivo_en_expediente
                    ? 'Documento guardado en el expediente del estudiante.'
                    : 'Documento registrado antes de la integración con el expediente.'}
                </small>
                <p>{detail.motivo}</p>
              </section>

              <section className="career-change-detail-block">
                <h3>Equivalencias seleccionadas</h3>
                <div className="career-change-table-wrap">
                  <table>
                    <thead><tr><th>Materia cursada</th><th>Nota</th><th>Materia destino</th><th>Validación</th></tr></thead>
                    <tbody>
                      {detail.equivalences.filter((item) => item.seleccionada).length ? detail.equivalences.filter((item) => item.seleccionada).map((item) => (
                        <tr key={item.id}>
                          <td><strong>{item.nombre_materia_origen}</strong><small>{item.codigo_comun_origen || item.materia_origen}</small></td>
                          <td>{formatGrade(item.nota_final)}</td>
                          <td><strong>{item.nombre_materia_destino}</strong><small>Nivel {item.nivel_destino ?? '-'}</small></td>
                          <td>{item.tipo_coincidencia.replaceAll('_', ' ')} · {Math.round(item.similitud * 100)} %</td>
                        </tr>
                      )) : <tr><td colSpan={4} className="career-change-empty">La solicitud no incluye materias para convalidar.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>

              {detail.observacion_revision ? (
                <section className="career-change-detail-block"><h3>Observación de revisión</h3><p>{detail.observacion_revision}</p></section>
              ) : null}

              {canReview && detail.estado === 'PENDIENTE' ? (
                <section className="career-change-review-box">
                  <label>
                    Observación de revisión
                    <textarea value={reviewObservation} onChange={(event) => setReviewObservation(event.target.value)} rows={3} maxLength={1000} placeholder="Obligatoria para rechazar" />
                  </label>
                  <div>
                    <button type="button" className="career-change-button career-change-button--danger" onClick={() => registerDecision('RECHAZADA')} disabled={actionLoading}>Rechazar</button>
                    <button type="button" className="career-change-button career-change-button--primary" onClick={() => registerDecision('APROBADA')} disabled={actionLoading}>Aprobar</button>
                  </div>
                </section>
              ) : null}

              {canReview && detail.estado === 'APROBADA' ? (
                <section className="career-change-apply-box">
                  <div><strong>Aplicar cambio aprobado</strong><span>Se registrará la nueva carrera y se copiarán las equivalencias seleccionadas como materias convalidadas.</span></div>
                  <button type="button" className="career-change-button career-change-button--primary" onClick={applyApprovedRequest} disabled={actionLoading}>
                    {actionLoading ? 'Aplicando...' : 'Aplicar cambio de carrera'}
                  </button>
                </section>
              ) : null}

              {canReview && detail.estado === 'APLICADA' ? (
                <section className="career-change-backup-box">
                  <div className="career-change-backup-box__heading">
                    <div>
                      <strong>Respaldo de la carrera anterior</strong>
                      <span>
                        {detail.respaldo_estado
                          ? 'La trayectoria original está protegida y puede recuperarse sin reemplazar notas existentes.'
                          : 'Esta solicitud fue aplicada antes de habilitar el respaldo explícito.'}
                      </span>
                    </div>
                    {detail.respaldo_estado ? (
                      <span className={`career-change-state career-change-state--${detail.respaldo_estado.toLowerCase()}`}>
                        {detail.respaldo_estado === 'RESTAURADO' ? 'Recuperado' : 'Disponible'}
                      </span>
                    ) : null}
                  </div>

                  {detail.respaldo_estado ? (
                    <div className="career-change-backup-summary">
                      <div><span>Cabeceras</span><strong>{formatNumber(detail.respaldo_cabeceras)}</strong></div>
                      <div><span>Materias</span><strong>{formatNumber(detail.respaldo_materias)}</strong></div>
                      <div><span>Fecha del respaldo</span><strong>{formatDate(detail.fecha_respaldo)}</strong></div>
                      <div><span>Recuperaciones</span><strong>{formatNumber(detail.restauraciones)}</strong><small>{formatDate(detail.fecha_ultima_restauracion)}</small></div>
                    </div>
                  ) : null}

                  {!detail.respaldo_estado ? (
                    <button type="button" className="career-change-button career-change-button--primary" onClick={applyApprovedRequest} disabled={actionLoading}>
                      {actionLoading ? 'Generando respaldo...' : 'Generar respaldo de la carrera anterior'}
                    </button>
                  ) : restoreConfirmation ? (
                    <div className="career-change-restore-confirmation" role="alert">
                      <div>
                        <strong>¿Recuperar la trayectoria anterior?</strong>
                        <span>Se restaurarán únicamente cabeceras y materias faltantes. La carrera destino y las calificaciones actuales no se eliminarán ni sobrescribirán.</span>
                      </div>
                      <div>
                        <button type="button" className="career-change-button" onClick={() => setRestoreConfirmation(false)} disabled={actionLoading}>Cancelar</button>
                        <button type="button" className="career-change-button career-change-button--primary" onClick={restorePreviousCareer} disabled={actionLoading}>
                          {actionLoading ? 'Recuperando...' : 'Confirmar recuperación'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="career-change-button" onClick={() => setRestoreConfirmation(true)} disabled={actionLoading}>
                      Recuperar carrera anterior
                    </button>
                  )}
                  <small>Después de recuperar el historial, la carrera anterior podrá seleccionarse nuevamente desde Matrícula individual.</small>
                </section>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  )
}
