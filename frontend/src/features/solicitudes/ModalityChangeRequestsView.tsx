import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import {
  applyModalityChangeRequest,
  createModalityChangeRequest,
  decideModalityChangeRequest,
  fetchModalityChangeCatalog,
  fetchModalityChangeRequestDetail,
  fetchModalityChangeRequests,
  previewModalityChange,
} from '../../lib/api'
import type {
  ModalityChangeCatalogResponse,
  ModalityChangeCatalogStudent,
  ModalityChangePreviewResponse,
  ModalityChangeRequestDetail,
  ModalityChangeRequestItem,
} from '../../types/app'
import './CareerChangeRequestsView.css'
import './ModalityChangeRequestsView.css'

type ModalityChangeRequestsViewProps = {
  displayName: string
  role: string
}

type ViewTab = 'NUEVA' | 'HISTORIAL'

const EMPTY_CATALOG: ModalityChangeCatalogResponse = {
  students: [],
  careers: [],
  modalities: [],
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

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('es-EC')
}

function stateLabel(state: string): string {
  const labels: Record<string, string> = {
    PENDIENTE: 'Pendiente',
    APROBADA: 'Aprobada, pendiente de aplicar',
    RECHAZADA: 'Rechazada',
    APLICADA: 'Aplicada',
    EXISTENTE: 'Ya matriculada',
    MATRICULADA: 'Matriculada',
    MATRICULAR: 'Por matricular',
    MIGRAR: 'Migrar por código',
    MIGRADA: 'Migrada',
  }
  return labels[state] || state
}

function periodTypeLabel(type: string): string {
  return type === 'R' ? 'Regular' : 'Homologación'
}

function gradeLabel(value: number | null | undefined): string {
  return value == null ? 'Sin nota' : value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 3 })
}

const MAX_SUPPORTING_FILES = 10
const MAX_SUPPORTING_FILE_BYTES = 20 * 1024 * 1024
const MAX_SUPPORTING_TOTAL_BYTES = 100 * 1024 * 1024

function formatFileSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function fileFingerprint(file: File): string {
  return `${file.name.toLocaleLowerCase()}|${file.size}|${file.lastModified}`
}

export function ModalityChangeRequestsView({
  displayName,
  role,
}: Readonly<ModalityChangeRequestsViewProps>) {
  const canReview = ['ADMINISTRADOR', 'ACADEMICO'].includes(normalizeRole(role))
  const [tab, setTab] = useState<ViewTab>('NUEVA')
  const [catalog, setCatalog] = useState<ModalityChangeCatalogResponse>(EMPTY_CATALOG)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [studentQuery, setStudentQuery] = useState('')
  const [studentSearchLoading, setStudentSearchLoading] = useState(false)
  const [selectedStudent, setSelectedStudent] = useState<ModalityChangeCatalogStudent | null>(null)
  const [targetCareerCode, setTargetCareerCode] = useState('')
  const [homologationPeriodCode, setHomologationPeriodCode] = useState('')
  const [preview, setPreview] = useState<ModalityChangePreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [motive, setMotive] = useState('')
  const [supportFiles, setSupportFiles] = useState<File[]>([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [saving, setSaving] = useState(false)

  const [requests, setRequests] = useState<ModalityChangeRequestItem[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')
  const [historyState, setHistoryState] = useState('TODOS')
  const [detail, setDetail] = useState<ModalityChangeRequestDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [reviewObservation, setReviewObservation] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [requestsError, setRequestsError] = useState('')
  const [actionError, setActionError] = useState('')
  const [success, setSuccess] = useState('')

  const regularPeriods = useMemo(
    () => catalog.periods.filter((period) => period.tipo === 'R'),
    [catalog.periods],
  )
  const homologationPeriods = useMemo(
    () => catalog.periods.filter((period) => period.tipo === 'H'),
    [catalog.periods],
  )

  const loadCatalog = useCallback(async (query = '') => {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      setCatalog(await fetchModalityChangeCatalog(query))
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
      const response = await fetchModalityChangeRequests({
        query: historyQuery,
        state: historyState,
        limit: 200,
      })
      setRequests(response.items)
    } catch (apiError) {
      setRequestsError(errorMessage(apiError, 'No se pudo cargar el historial.'))
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
    const timeout = window.setTimeout(() => setSuccess(''), 3500)
    return () => window.clearTimeout(timeout)
  }, [success])

  function resetPreview() {
    setPreview(null)
    setActionError('')
  }

  async function searchStudent() {
    const query = studentQuery.trim()
    if (query.length < 2) {
      setActionError('Ingrese al menos dos caracteres del nombre, cédula o código.')
      return
    }
    setStudentSearchLoading(true)
    setActionError('')
    try {
      const response = await fetchModalityChangeCatalog(query)
      setCatalog(response)
      setCatalogError('')
      if (response.students.length === 0) setActionError('No se encontraron estudiantes.')
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo buscar el estudiante.'))
    } finally {
      setStudentSearchLoading(false)
    }
  }

  function chooseStudent(student: ModalityChangeCatalogStudent) {
    setSelectedStudent(student)
    setTargetCareerCode(student.carrera ? String(student.carrera) : '')
    setHomologationPeriodCode('')
    resetPreview()
  }

  async function analyzeEnrollment() {
    if (!selectedStudent || !targetCareerCode || !homologationPeriodCode) {
      setActionError('Seleccione estudiante, carrera y período destino.')
      return
    }
    setPreviewLoading(true)
    setActionError('')
    try {
      setPreview(await previewModalityChange({
        codigo_estud: selectedStudent.codigo_estud,
        carrera_destino: Number(targetCareerCode),
        codigo_periodo_homologacion: Number(homologationPeriodCode),
      }))
    } catch (apiError) {
      setPreview(null)
      setActionError(errorMessage(apiError, 'No se pudo preparar la matrícula del período seleccionado.'))
    } finally {
      setPreviewLoading(false)
    }
  }

  function chooseSupportFiles(fileList: FileList | null) {
    setActionError('')
    const incomingFiles = Array.from(fileList || [])
    if (!incomingFiles.length) return

    const invalidFile = incomingFiles.find(
      (file) => file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf'),
    )
    if (invalidFile) {
      setFileInputKey((current) => current + 1)
      setActionError(`El archivo ${invalidFile.name} debe estar en formato PDF.`)
      return
    }
    const oversizedFile = incomingFiles.find((file) => file.size > MAX_SUPPORTING_FILE_BYTES)
    if (oversizedFile) {
      setFileInputKey((current) => current + 1)
      setActionError(`El archivo ${oversizedFile.name} supera el límite de 20 MB.`)
      return
    }

    const fingerprints = new Set(supportFiles.map(fileFingerprint))
    let repeatedFile: File | undefined
    for (const file of incomingFiles) {
      const fingerprint = fileFingerprint(file)
      if (fingerprints.has(fingerprint)) {
        repeatedFile = file
        break
      }
      fingerprints.add(fingerprint)
    }
    if (repeatedFile) {
      setFileInputKey((current) => current + 1)
      setActionError(`El archivo ${repeatedFile.name} ya está seleccionado.`)
      return
    }

    const nextFiles = [...supportFiles, ...incomingFiles]
    if (nextFiles.length > MAX_SUPPORTING_FILES) {
      setFileInputKey((current) => current + 1)
      setActionError(`Puede adjuntar hasta ${MAX_SUPPORTING_FILES} documentos PDF.`)
      return
    }
    if (nextFiles.reduce((total, file) => total + file.size, 0) > MAX_SUPPORTING_TOTAL_BYTES) {
      setFileInputKey((current) => current + 1)
      setActionError('La carga completa de documentos no puede superar 100 MB.')
      return
    }
    setSupportFiles(nextFiles)
    setFileInputKey((current) => current + 1)
  }

  function removeSupportFile(index: number) {
    setSupportFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))
    setActionError('')
  }

  async function submitRequest(event: FormEvent) {
    event.preventDefault()
    if (!selectedStudent || !targetCareerCode || !homologationPeriodCode || !preview) {
      setActionError('Analice la matrícula antes de registrar la solicitud.')
      return
    }
    if (motive.trim().length < 10) {
      setActionError('Registre un motivo de al menos 10 caracteres.')
      return
    }
    if (!supportFiles.length) {
      setActionError('Adjunte al menos un documento PDF de respaldo.')
      return
    }
    const formData = new FormData()
    formData.append('codigo_estud', String(selectedStudent.codigo_estud))
    formData.append('carrera_destino', targetCareerCode)
    formData.append('codigo_periodo_homologacion', homologationPeriodCode)
    formData.append('motivo', motive.trim())
    supportFiles.forEach((file) => formData.append('archivos', file))

    setSaving(true)
    setActionError('')
    try {
      const response = await createModalityChangeRequest(formData)
      setSuccess(response.message)
      setSelectedStudent(null)
      setStudentQuery('')
      setTargetCareerCode('')
      setHomologationPeriodCode('')
      setPreview(null)
      setMotive('')
      setSupportFiles([])
      setFileInputKey((current) => current + 1)
      setTab('HISTORIAL')
      await loadRequests()
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo registrar la solicitud.'))
    } finally {
      setSaving(false)
    }
  }

  async function openDetail(item: ModalityChangeRequestItem) {
    setDetailLoading(true)
    setActionError('')
    try {
      const response = await fetchModalityChangeRequestDetail(item.id)
      setDetail(response)
      setReviewObservation(response.observacion_revision || '')
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo abrir la solicitud.'))
    } finally {
      setDetailLoading(false)
    }
  }

  async function reloadDetail(requestId: number) {
    setDetail(await fetchModalityChangeRequestDetail(requestId))
    await loadRequests()
  }

  async function registerDecision(decision: 'APROBADA' | 'RECHAZADA') {
    if (!detail) return
    if (decision === 'RECHAZADA' && reviewObservation.trim().length < 5) {
      setActionError('Registre el motivo del rechazo.')
      return
    }
    setActionLoading(true)
    setActionError('')
    try {
      const response = await decideModalityChangeRequest(
        detail.id,
        decision,
        reviewObservation.trim(),
      )
      setSuccess(response.message)
      await reloadDetail(detail.id)
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo registrar la decisión.'))
      try {
        await reloadDetail(detail.id)
      } catch {
        // Se conserva el error de la operación principal.
      }
    } finally {
      setActionLoading(false)
    }
  }

  async function retryApplication() {
    if (!detail) return
    setActionLoading(true)
    setActionError('')
    try {
      const response = await applyModalityChangeRequest(detail.id)
      setSuccess(response.message)
      await reloadDetail(detail.id)
    } catch (apiError) {
      setActionError(errorMessage(apiError, 'No se pudo aplicar el cambio de modalidad.'))
    } finally {
      setActionLoading(false)
    }
  }

  function changeTab(nextTab: ViewTab) {
    setTab(nextTab)
    setActionError('')
  }

  return (
    <main className="career-change-page modality-change-page">
      <header className="career-change-hero">
        <div>
          <span className="career-change-eyebrow">SOLICITUDES</span>
          <h1>Cambio de modalidad</h1>
        </div>
        <aside>
          <strong>{displayName}</strong>
          <span>{canReview ? 'Revisión académica' : 'Registro de solicitudes'}</span>
        </aside>
      </header>

      <nav className="career-change-tabs" aria-label="Apartados de cambio de modalidad">
        <button type="button" className={tab === 'NUEVA' ? 'is-active' : ''} onClick={() => changeTab('NUEVA')}>
          Nueva solicitud
        </button>
        <button type="button" className={tab === 'HISTORIAL' ? 'is-active' : ''} onClick={() => changeTab('HISTORIAL')}>
          Historial y revisión
        </button>
      </nav>

      {actionError ? <div className="career-change-alert career-change-alert--error">{actionError}</div> : null}
      {tab === 'NUEVA' && catalogError ? <div className="career-change-alert career-change-alert--error">{catalogError}</div> : null}
      {tab === 'HISTORIAL' && requestsError ? <div className="career-change-alert career-change-alert--error">{requestsError}</div> : null}
      {success ? <div className="career-change-toast" role="status">{success}</div> : null}

      {tab === 'NUEVA' ? (
        <form className="career-change-workflow" onSubmit={submitRequest}>
          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>1</span>
              <div><h2>Estudiante</h2><p>Nombre, cédula o código institucional.</p></div>
            </div>
            <div className="career-change-search-row">
              <label>
                Buscar estudiante
                <input type="search" value={studentQuery} onChange={(event) => setStudentQuery(event.target.value)} placeholder="Nombre, cédula o código" />
              </label>
              <button type="button" className="career-change-button career-change-button--primary" onClick={searchStudent} disabled={studentSearchLoading}>
                {studentSearchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {catalog.students.length > 0 ? (
              <div className="career-change-student-results">
                {catalog.students.map((student) => (
                  <button type="button" key={student.codigo_estud} className={selectedStudent?.codigo_estud === student.codigo_estud ? 'is-selected' : ''} onClick={() => chooseStudent(student)}>
                    <strong>{student.estudiante}</strong>
                    <span>{student.cedula} · Código {student.codigo_estud}</span>
                    <span>{student.carrera_nombre || 'Sin carrera'} · {student.modalidad_nombre || 'Modalidad no registrada'}{student.jornada_nombre ? ` · ${student.jornada_nombre}` : ''}</span>
                    {student.periodo_nombre ? <span>{student.periodo_nombre} · {periodTypeLabel(student.tipo_periodo || '')}</span> : null}
                  </button>
                ))}
              </div>
            ) : null}

            {selectedStudent ? (
              <div className="career-change-selected-student">
                <div><span>Estudiante</span><strong>{selectedStudent.estudiante}</strong></div>
                <div><span>Carrera actual</span><strong>{selectedStudent.carrera_nombre}</strong></div>
                <div><span>Modalidad heredada</span><strong>{selectedStudent.modalidad_nombre || 'No registrada'}</strong></div>
                <div><span>Jornada heredada</span><strong>{selectedStudent.jornada_nombre || 'No registrada'}</strong></div>
                <div><span>Período actual</span><strong>{selectedStudent.periodo_nombre || 'No registrado'}</strong></div>
                <div><span>Estado</span><strong>{selectedStudent.estado || '-'}</strong></div>
              </div>
            ) : null}
          </section>

          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>2</span>
              <div><h2>Destino</h2><p>Carrera y período para la nueva matrícula.</p></div>
            </div>
            <div className="career-change-fields modality-change-destination">
              <label>
                Carrera
                <select value={targetCareerCode} onChange={(event) => { setTargetCareerCode(event.target.value); resetPreview() }} disabled={!selectedStudent || catalogLoading}>
                  <option value="">Seleccione una carrera</option>
                  {catalog.careers.map((career) => <option key={career.codigo} value={career.codigo}>{career.nombre}</option>)}
                </select>
              </label>
              <label>
                Período
                <select value={homologationPeriodCode} onChange={(event) => { setHomologationPeriodCode(event.target.value); resetPreview() }} disabled={!selectedStudent || catalogLoading}>
                  <option value="">Seleccione un período</option>
                  {regularPeriods.length ? (
                    <optgroup label="Períodos regulares">
                      {regularPeriods.map((period) => <option key={period.codigo} value={period.codigo}>{period.nombre}</option>)}
                    </optgroup>
                  ) : null}
                  {homologationPeriods.length ? (
                    <optgroup label="Períodos de homologación">
                      {homologationPeriods.map((period) => <option key={period.codigo} value={period.codigo}>{period.nombre}</option>)}
                    </optgroup>
                  ) : null}
                </select>
              </label>
              <button type="button" className="career-change-button career-change-button--primary" onClick={analyzeEnrollment} disabled={!selectedStudent || !targetCareerCode || !homologationPeriodCode || previewLoading}>
                {previewLoading ? 'Analizando...' : 'Preparar matrícula'}
              </button>
            </div>
          </section>

          {preview ? (
            <section className="career-change-section">
              <div className="career-change-section__heading">
                <span>3</span>
                <div><h2>Migración y matrícula única</h2><p>{periodTypeLabel(preview.source_period.tipo)} · {preview.source_period.nombre} → {periodTypeLabel(preview.homologation_period.tipo)} · {preview.homologation_period.nombre}</p></div>
              </div>
              <div className="career-change-summary">
                <div><span>Materias origen</span><strong>{preview.summary.materias_origen}</strong></div>
                <div><span>Notas por migrar</span><strong>{preview.summary.materias_a_migrar}</strong></div>
                <div><span>Materias destino</span><strong>{preview.summary.materias_pensum}</strong></div>
                <div><span>Nuevas sin nota</span><strong>{preview.summary.materias_por_matricular}</strong></div>
                <div><span>Ya existentes</span><strong>{preview.summary.materias_existentes}</strong></div>
                <div><span>Cabeceras nuevas</span><strong>{preview.summary.cabeceras_a_crear}</strong></div>
              </div>
              {preview.summary.materias_origen_sin_coincidencia > 0 ? (
                <div className="career-change-alert career-change-alert--warning">
                  {preview.summary.materias_origen_sin_coincidencia} registro(s) de origen no tienen el mismo código único en el pénsum destino. Permanecerán íntegros en el respaldo de auditoría.
                </div>
              ) : null}
              <div className="career-change-table-wrap modality-change-subjects">
                <table>
                  <thead><tr><th>Nivel</th><th>Código único</th><th>Materia</th><th>Nota origen</th><th>Créditos</th><th>Acción</th></tr></thead>
                  <tbody>
                    {preview.subjects.map((subject) => (
                      <tr key={subject.codigo_materia}>
                        <td>{subject.nivel ?? '-'}</td>
                        <td>{subject.codigo_comun || subject.codigo_materia}</td>
                        <td><strong>{subject.nombre}</strong></td>
                        <td>{gradeLabel(subject.nota_origen)}</td>
                        <td>{subject.creditos}</td>
                        <td><span className={`career-change-state career-change-state--${subject.estado.toLowerCase()}`}>{stateLabel(subject.estado)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <section className="career-change-section">
            <div className="career-change-section__heading">
              <span>4</span>
              <div><h2>Solicitud y respaldos</h2><p>Documentos asociados al expediente institucional del estudiante.</p></div>
            </div>
            <div className="career-change-fields career-change-fields--support">
              <label>
                Motivo
                <textarea value={motive} onChange={(event) => setMotive(event.target.value)} maxLength={1000} rows={4} placeholder="Detalle el motivo del cambio de modalidad" />
              </label>
              <div className="modality-change-upload">
                <label>
                  Documentos de respaldo (PDF)
                  <input key={fileInputKey} type="file" accept="application/pdf,.pdf" multiple onChange={(event) => chooseSupportFiles(event.target.files)} />
                  <small>
                    {supportFiles.length
                      ? `${supportFiles.length} de ${MAX_SUPPORTING_FILES} archivo(s) · ${formatFileSize(supportFiles.reduce((total, file) => total + file.size, 0))} en total`
                      : `Al menos 1 y hasta ${MAX_SUPPORTING_FILES} PDF. Máximo 20 MB por archivo y 100 MB en total.`}
                  </small>
                </label>
                {supportFiles.length ? (
                  <ul className="modality-change-file-list" aria-label="Documentos seleccionados">
                    {supportFiles.map((file, index) => (
                      <li key={fileFingerprint(file)}>
                        <span className="modality-change-file-order" aria-hidden="true">{index + 1}</span>
                        <span className="modality-change-file-details">
                          <strong title={file.name}>{file.name}</strong>
                          <small>PDF · {formatFileSize(file.size)}</small>
                        </span>
                        <button type="button" onClick={() => removeSupportFile(index)} aria-label={`Quitar ${file.name}`} title="Quitar archivo">&times;</button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
            <div className="career-change-submit-row">
              <span>{preview ? `${preview.summary.materias_a_migrar} materia(s) migradas por código y ${preview.summary.materias_pensum} en destino` : 'Vista previa pendiente'}</span>
              <button type="submit" className="career-change-button career-change-button--primary" disabled={saving || !preview}>
                {saving ? 'Registrando...' : 'Registrar solicitud'}
              </button>
            </div>
          </section>
        </form>
      ) : (
        <section className="career-change-section career-change-history">
          <div className="career-change-section__heading">
            <span>H</span>
            <div><h2>Historial de solicitudes</h2><p>{requests.length} registro(s) con los filtros actuales.</p></div>
          </div>
          <div className="career-change-history-controls">
            <label>Buscar<input type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Estudiante, cédula o solicitud" /></label>
            <label>
              Estado
              <select value={historyState} onChange={(event) => setHistoryState(event.target.value)}>
                <option value="TODOS">Todos</option>
                {catalog.states.map((state) => <option key={state} value={state}>{stateLabel(state)}</option>)}
              </select>
            </label>
            <button type="button" className="career-change-button" onClick={() => void loadRequests()} disabled={requestsLoading}>{requestsLoading ? 'Actualizando...' : 'Actualizar'}</button>
          </div>
          <div className="career-change-table-wrap">
            <table>
              <thead><tr><th>Solicitud</th><th>Estudiante</th><th>Carrera</th><th>Modalidad</th><th>Período</th><th>Materias</th><th>Estado</th><th>Acción</th></tr></thead>
              <tbody>
                {requestsLoading ? <tr><td colSpan={8} className="career-change-empty">Consultando solicitudes...</td></tr> : requests.length ? requests.map((item) => (
                  <tr key={item.id}>
                    <td><strong>#{item.id}</strong><small>{formatDate(item.fecha_creacion)}</small></td>
                    <td><strong>{item.estudiante}</strong><small>{item.cedula} · Código {item.codigo_estud}</small></td>
                    <td><span>{item.carrera_origen_nombre}</span><strong>{item.carrera_destino_nombre}</strong></td>
                    <td><span>{item.modalidad_origen_nombre || 'No registrada'}</span><strong>{item.modalidad_destino_nombre}</strong></td>
                    <td><span>{item.periodo_origen_nombre || 'Origen no registrado'}</span><strong>{item.periodo_homologacion_nombre}</strong><small>{periodTypeLabel(item.tipo_periodo_destino)}</small></td>
                    <td>{item.total_materias_pensum}</td>
                    <td><span className={`career-change-state career-change-state--${item.estado.toLowerCase()}`}>{stateLabel(item.estado)}</span></td>
                    <td><button type="button" className="career-change-button" onClick={() => void openDetail(item)}>Revisar</button></td>
                  </tr>
                )) : <tr><td colSpan={8} className="career-change-empty">No existen solicitudes con los filtros actuales.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {detailLoading ? <div className="career-change-loading-overlay" role="status">Abriendo solicitud...</div> : null}

      {detail ? (
        <div className="career-change-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !actionLoading) setDetail(null) }}>
          <section className="career-change-modal" role="dialog" aria-modal="true" aria-labelledby="modality-change-detail-title">
            <header>
              <div>
                <span>DETALLE DE SOLICITUD #{detail.id}</span>
                <h2 id="modality-change-detail-title">{detail.estudiante}</h2>
                <p>{detail.cedula} · Código {detail.codigo_estud}</p>
              </div>
              <button type="button" className="career-change-button" onClick={() => setDetail(null)} disabled={actionLoading}>Cerrar</button>
            </header>
            <div className="career-change-modal__body">
              <div className="career-change-detail-grid">
                <div><span>Carrera</span><strong>{detail.carrera_origen_nombre}</strong><small>Destino: {detail.carrera_destino_nombre}</small></div>
                <div><span>Modalidad</span><strong>{detail.modalidad_origen_nombre || 'No registrada'}</strong><small>Destino: {detail.modalidad_destino_nombre}</small></div>
                <div><span>Período origen</span><strong>{detail.periodo_origen_nombre || 'No registrado'}</strong><small>{detail.tipo_periodo_origen ? periodTypeLabel(detail.tipo_periodo_origen) : '-'}</small></div>
                <div><span>Período destino</span><strong>{detail.periodo_homologacion_nombre}</strong><small>{periodTypeLabel(detail.tipo_periodo_destino)}</small></div>
                <div><span>Estado</span><strong className={`career-change-state career-change-state--${detail.estado.toLowerCase()}`}>{stateLabel(detail.estado)}</strong></div>
                <div><span>Registrada por</span><strong>{detail.creado_por}</strong><small>{formatDate(detail.fecha_creacion)}</small></div>
                <div><span>Resultado</span><strong>{detail.materias_migradas} migradas</strong><small>{detail.materias_matriculadas} nuevas · {detail.materias_existentes} existentes</small></div>
              </div>

              <section className="career-change-detail-block">
                <div className="modality-change-document-heading">
                  <h3>Motivo y respaldos</h3>
                  <span>{detail.archivos?.length || (detail.archivo_url ? 1 : 0)} documento(s)</span>
                </div>
                <small>{detail.archivo_en_expediente ? 'Documentos guardados en el expediente del estudiante.' : 'Documentos pendientes de expediente.'}</small>
                <div className="modality-change-document-actions">
                  {(detail.archivos?.length
                    ? detail.archivos
                    : detail.archivo_url
                      ? [{ orden: 1, nombre_original: detail.archivo_nombre, archivo_url: detail.archivo_url, estado: detail.estado_expediente || '' }]
                      : []
                  ).map((document) => document.archivo_url ? (
                    <a key={`${document.orden}-${document.nombre_original}`} className="career-change-button" href={document.archivo_url} target="_blank" rel="noreferrer">
                      PDF {document.orden}: {document.nombre_original || 'Documento de respaldo'}
                    </a>
                  ) : (
                    <span key={`${document.orden}-${document.nombre_original}`} className="modality-change-document-pending">
                      PDF {document.orden}: {document.nombre_original || 'Documento pendiente'} ({document.estado || 'PENDIENTE'})
                    </span>
                  ))}
                </div>
                <p>{detail.motivo}</p>
              </section>

              {detail.respaldo_id ? (
                <section className="career-change-detail-block">
                  <h3>Respaldo y auditoría del movimiento</h3>
                  <div className="career-change-detail-grid">
                    <div><span>Respaldo</span><strong>#{detail.respaldo_id}</strong><small>{detail.respaldo_cabeceras} cabecera(s) · {detail.respaldo_materias} materia(s)</small></div>
                    <div><span>Auditoría</span><strong>{detail.auditoria_id ? `#${detail.auditoria_id}` : 'Pendiente'}</strong><small>{formatDate(detail.fecha_respaldo)}</small></div>
                    <div><span>Origen retirado</span><strong>{detail.materias_origen_retiradas} materia(s)</strong><small>{detail.cabeceras_origen_retiradas} cabecera(s)</small></div>
                    <div><span>Integridad</span><strong>{detail.respaldo_hash.slice(0, 16) || '-'}</strong><small>SHA-256 del respaldo completo</small></div>
                  </div>
                </section>
              ) : null}

              <section className="career-change-detail-block">
                <h3>Materias aprobadas para la migración</h3>
                <div className="career-change-table-wrap modality-change-subjects">
                  <table>
                    <thead><tr><th>Nivel</th><th>Código único</th><th>Materia</th><th>Nota origen</th><th>Créditos</th><th>Estado</th></tr></thead>
                    <tbody>{detail.subjects.map((subject) => (
                      <tr key={subject.codigo_materia}>
                        <td>{subject.nivel ?? '-'}</td><td>{subject.codigo_comun || subject.codigo_materia}</td><td><strong>{subject.nombre}</strong></td><td>{gradeLabel(subject.nota_origen)}</td><td>{subject.creditos}</td>
                        <td><span className={`career-change-state career-change-state--${subject.estado.toLowerCase()}`}>{stateLabel(subject.estado)}</span><small>{subject.observacion || '-'}</small></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </section>

              {detail.observacion_revision ? <section className="career-change-detail-block"><h3>Observación de revisión</h3><p>{detail.observacion_revision}</p></section> : null}

              {canReview && detail.estado === 'PENDIENTE' ? (
                <section className="career-change-review-box">
                  <label>Observación de revisión<textarea value={reviewObservation} onChange={(event) => setReviewObservation(event.target.value)} rows={3} maxLength={1000} placeholder="Obligatoria para rechazar" /></label>
                  <div>
                    <button type="button" className="career-change-button career-change-button--danger" onClick={() => void registerDecision('RECHAZADA')} disabled={actionLoading}>Rechazar</button>
                    <button type="button" className="career-change-button career-change-button--primary" onClick={() => void registerDecision('APROBADA')} disabled={actionLoading}>{actionLoading ? 'Procesando...' : 'Aprobar y migrar'}</button>
                  </div>
                </section>
              ) : null}

              {canReview && detail.estado === 'APROBADA' ? (
                <section className="career-change-apply-box">
                  <div><strong>Aplicación pendiente</strong><span>El reintento verifica el respaldo, las notas y la matrícula destino sin duplicar registros.</span></div>
                  <button type="button" className="career-change-button career-change-button--primary" onClick={() => void retryApplication()} disabled={actionLoading}>{actionLoading ? 'Aplicando...' : 'Reintentar aplicación'}</button>
                </section>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </main>
  )
}
