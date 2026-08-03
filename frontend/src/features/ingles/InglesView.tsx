import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  createEnglishUploadSession,
  englishExamFileUrl,
  fetchEnglishStudentExam,
  fetchEnglishSubmissions,
  finalizeEnglishUpload,
  gradeEnglishSubmission,
  uploadEnglishFileChunks,
} from '../../lib/api'
import type {
  EnglishExam,
  EnglishExamComponent,
  EnglishExamFile,
  EnglishSubmissionsResponse,
} from '../../types/app'

type InglesViewProps = {
  displayName: string
  role: string
}

const MAX_FILE_BYTES = 1024 * 1024 * 1024
const ACCEPTED_VIDEOS = 'video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm'
const VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.mkv', '.webm'])

function normalizedRole(value: string) {
  return value.trim().toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

function isAcceptedVideo(file: File) {
  const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0] || ''
  const contentType = file.type.toLowerCase()
  return VIDEO_EXTENSIONS.has(extension)
    && (!contentType || contentType === 'application/octet-stream' || contentType.startsWith('video/'))
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
    timeStyle: 'medium',
    timeZone: 'America/Guayaquil',
  }).format(date)
}

function secondsUntil(deadline: string | null, now: number) {
  if (!deadline) return 0
  const target = new Date(deadline).getTime()
  return Number.isFinite(target) ? Math.max(0, Math.ceil((target - now) / 1000)) : 0
}

function countdown(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
}

function resultClass(result: string) {
  if (result === 'APROBADO') return 'english-badge english-badge--ok'
  if (result === 'REPROBADO') return 'english-badge english-badge--danger'
  return 'english-badge english-badge--pending'
}

function sortedComponents(exam: EnglishExam) {
  return [...exam.components].sort((left, right) => left.number - right.number)
}

function componentProgressLabel(component: EnglishExamComponent) {
  if (component.grade !== null) return `Calificado: ${component.grade.toFixed(2)} / 10`
  if (component.file) return 'Video entregado'
  return 'Pendiente de entrega'
}

function FileActions({
  file,
  viewLabel = 'Ver video',
}: Readonly<{ file: EnglishExamFile | null; viewLabel?: string }>) {
  if (!file) return <span className="english-muted">Sin video</span>
  return (
    <div className="english-file-actions">
      <a className="ghost-button" href={englishExamFileUrl(file.upload_id, 'open')} target="_blank" rel="noreferrer">{viewLabel}</a>
      <a className="ghost-button" href={englishExamFileUrl(file.upload_id, 'download')}>Descargar</a>
    </div>
  )
}

function StudentEnglishExam({ displayName }: Readonly<{ displayName: string }>) {
  const [exam, setExam] = useState<EnglishExam | null>(null)
  const [selectedComponentCode, setSelectedComponentCode] = useState('P1')
  const [selectedFiles, setSelectedFiles] = useState<Record<string, File | null>>({})
  const [loading, setLoading] = useState(true)
  const [uploadingCode, setUploadingCode] = useState('')
  const [progressByCode, setProgressByCode] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [now, setNow] = useState(Date.now())
  const [fileInputKeys, setFileInputKeys] = useState<Record<string, number>>({})

  const loadExam = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setExam(await fetchEnglishStudentExam())
    } catch (requestError) {
      setExam(null)
      setError(errorMessage(requestError, 'No se pudo validar la matrícula de Inglés.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadExam()
  }, [loadExam])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const components = useMemo(() => exam ? sortedComponents(exam) : [], [exam])
  const selectedComponent = useMemo(
    () => components.find((component) => component.code === selectedComponentCode) || components[0] || null,
    [components, selectedComponentCode],
  )

  useEffect(() => {
    if (components.length > 0 && !components.some((component) => component.code === selectedComponentCode)) {
      setSelectedComponentCode(components[0].code)
    }
  }, [components, selectedComponentCode])

  function selectFile(componentCode: string, file: File | null) {
    setError('')
    setMessage('')
    if (!file) {
      setSelectedFiles((current) => ({ ...current, [componentCode]: null }))
      return
    }
    if (!isAcceptedVideo(file)) {
      setSelectedFiles((current) => ({ ...current, [componentCode]: null }))
      setFileInputKeys((current) => ({ ...current, [componentCode]: (current[componentCode] || 0) + 1 }))
      setError('Seleccione un video en formato MP4, MOV, MKV o WEBM.')
      return
    }
    if (file.size > (exam?.max_file_bytes || MAX_FILE_BYTES)) {
      setSelectedFiles((current) => ({ ...current, [componentCode]: null }))
      setFileInputKeys((current) => ({ ...current, [componentCode]: (current[componentCode] || 0) + 1 }))
      setError('El video supera el límite máximo de 1 GB.')
      return
    }
    setSelectedFiles((current) => ({ ...current, [componentCode]: file }))
  }

  async function uploadFile(component: EnglishExamComponent) {
    const selectedFile = selectedFiles[component.code]
    const remaining = secondsUntil(component.edit_deadline, now)
    const canReplace = Boolean(component.file && component.grade === null && remaining > 0)
    const canUpload = component.grade === null && (!component.file || canReplace)
    if (!selectedFile || !canUpload) return

    setUploadingCode(component.code)
    setProgressByCode((current) => ({ ...current, [component.code]: 0 }))
    setError('')
    setMessage('')
    try {
      const session = await createEnglishUploadSession(selectedFile, component.code)
      if (!session.upload_url) throw new Error('Microsoft Graph no devolvió una sesión válida de carga.')
      await uploadEnglishFileChunks(session.upload_url, selectedFile, session.chunk_size, (progress) => {
        setProgressByCode((current) => ({ ...current, [component.code]: progress }))
      })
      const updatedExam = await finalizeEnglishUpload(session.upload_id)
      const updatedComponent = updatedExam.components.find((item) => item.code === component.code)
      setExam(updatedExam)
      setSelectedFiles((current) => ({ ...current, [component.code]: null }))
      setFileInputKeys((current) => ({ ...current, [component.code]: (current[component.code] || 0) + 1 }))
      setProgressByCode((current) => ({ ...current, [component.code]: 100 }))
      const nextPending = sortedComponents(updatedExam).find((item) => item.code !== component.code && !item.file)
      if (nextPending) setSelectedComponentCode(nextPending.code)
      setMessage(updatedComponent?.file?.version === 1
        ? `${component.label} entregado. Dispone de 15 minutos para reemplazarlo.`
        : `${component.label} reemplazado sin extender el plazo original.`)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo completar la carga del video.'))
      await loadExam()
    } finally {
      setUploadingCode('')
    }
  }

  if (loading) return <section className="student-card english-loading">Validando matrícula de Inglés...</section>

  if (!exam) {
    return (
      <>
        {error ? <div className="english-alert english-alert--error" role="alert">{error}</div> : null}
        <section className="student-card english-enrollment-lock">
          <span className="english-badge english-badge--locked">Carga no habilitada</span>
          <h3>No existe una matrícula vigente de Inglés A2+ - INTERMEDIATE</h3>
          <p>La carga de P1, P2 y P3 se habilita únicamente cuando el estudiante consta matriculado en esa asignatura y período.</p>
        </section>
      </>
    )
  }

  const component = selectedComponent
  const remaining = component ? secondsUntil(component.edit_deadline, now) : 0
  const canReplace = Boolean(component?.file && component.grade === null && remaining > 0)
  const canUpload = Boolean(component && component.grade === null && (!component.file || canReplace))
  const selectedFile = component ? selectedFiles[component.code] : null
  const uploading = Boolean(component && uploadingCode === component.code)
  const progress = component ? progressByCode[component.code] || 0 : 0

  return (
    <>
      {error ? <div className="english-alert english-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="english-alert english-alert--success" role="status">{message}</div> : null}

      <section className="english-summary" aria-label="Resumen de matrícula de Inglés">
        <div><span>Estudiante</span><strong>{exam.student.name || displayName}</strong><small>{exam.student.identification}</small></div>
        <div><span>Carrera</span><strong>{exam.student.career || 'Sin carrera registrada'}</strong><small>Matrícula académica principal</small></div>
        <div><span>Matrícula de Inglés</span><strong>{exam.enrollment.subject}</strong><small>{exam.enrollment.period}{exam.enrollment.parallel ? ` · Paralelo ${exam.enrollment.parallel}` : ''}</small></div>
        <div><span>Avance</span><strong>{exam.submitted_components} / {exam.required_components} parciales</strong><small>{exam.grade === null ? 'Calificación final pendiente' : `Promedio ${exam.grade.toFixed(2)} / 10`}</small></div>
      </section>

      <section className="student-card english-student-panel">
        <div className="card-head english-card-head">
          <div>
            <span>Entrega estudiantil</span>
            <h3>Evidencias por parcial</h3>
            <p>Cada video se registra como examen del mismo parcial en el período matriculado.</p>
          </div>
          <span className={resultClass(exam.result)}>{exam.result}</span>
        </div>

        <div className="english-partial-selector">
          <label htmlFor="english-student-partial">
            <span>Parcial a cargar</span>
            <select
              id="english-student-partial"
              value={component?.code || ''}
              disabled={Boolean(uploadingCode)}
              onChange={(event) => setSelectedComponentCode(event.target.value)}
            >
              {components.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label} · {componentProgressLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <div className="english-partial-selector-status">
            <span>Avance de entregas</span>
            <strong>{exam.submitted_components} de {exam.required_components}</strong>
            <small>{component ? componentProgressLabel(component) : 'Sin parcial disponible'}</small>
          </div>
        </div>

        {component ? (
          <article className="english-partial-card english-partial-card--single">
            <header>
              <div><span>{component.code}</span><h4>{component.label}</h4></div>
              <i className={resultClass(component.result)}>{component.result}</i>
            </header>

            {component.file ? (
              <div className="english-partial-file">
                <div><strong>{component.file.name}</strong><small>v{component.file.version} · {fileSize(component.file.size)} · {dateTime(component.file.uploaded_at)}</small></div>
                <FileActions file={component.file} />
              </div>
            ) : <p className="english-empty-copy">Sin evidencia entregada para {component.label.toLowerCase()}.</p>}

            {component.grade !== null ? (
              <div className="english-partial-grade">
                <span>Nota del examen</span><strong>{component.grade.toFixed(2)} / 10</strong>
                <small>{component.evaluator || 'Docente evaluador'}{component.observation ? ` · ${component.observation}` : ''}</small>
              </div>
            ) : null}

            {canUpload ? (
              <div className="english-partial-upload english-partial-upload--single">
                <label htmlFor={`english-file-${component.code}`}>
                  <span>{component.file ? `Reemplazar video de ${component.label}` : `Video de ${component.label}`}</span>
                  <input
                    key={fileInputKeys[component.code] || 0}
                    id={`english-file-${component.code}`}
                    type="file"
                    accept={ACCEPTED_VIDEOS}
                    disabled={Boolean(uploadingCode)}
                    onChange={(event) => selectFile(component.code, event.target.files?.[0] || null)}
                  />
                </label>
                <small>{selectedFile ? `${selectedFile.name} · ${fileSize(selectedFile.size)}` : 'Video MP4, MOV, MKV o WEBM. Máximo 1 GB.'}</small>
                <button type="button" className="primary-action" onClick={() => void uploadFile(component)} disabled={!selectedFile || Boolean(uploadingCode)}>
                  {uploading ? `Subiendo ${progress}%` : component.file ? 'Reemplazar video' : `Entregar ${component.label}`}
                </button>
                {uploading ? <div className="english-upload-progress"><span style={{ width: `${progress}%` }} /></div> : null}
              </div>
            ) : null}

            {component.file && component.grade === null ? (
              <p className="english-window-note">
                {remaining > 0 ? `Edición disponible: ${countdown(remaining)}` : 'Entrega cerrada y disponible para revisión docente.'}
              </p>
            ) : null}
          </article>
        ) : null}

        {exam.grade !== null ? (
          <div className={`english-grade-result ${exam.result === 'APROBADO' ? 'is-approved' : 'is-failed'}`}>
            <div><span>Promedio final</span><strong>{exam.grade.toFixed(2)} / 10</strong></div>
            <div><span>Resultado</span><strong>{exam.result}</strong></div>
            <div><span>Docente evaluador</span><strong>{exam.evaluator || '-'}</strong></div>
            <p>{exam.observation || 'Sin observaciones.'}</p>
          </div>
        ) : null}
      </section>
    </>
  )
}

function ReviewerEnglishExams() {
  const [data, setData] = useState<EnglishSubmissionsResponse | null>(null)
  const [search, setSearch] = useState('')
  const [state, setState] = useState('TODOS')
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selected, setSelected] = useState<EnglishExam | null>(null)
  const [selectedComponentCode, setSelectedComponentCode] = useState('')
  const [grade, setGrade] = useState('')
  const [observation, setObservation] = useState('')
  const [now, setNow] = useState(Date.now())

  const loadSubmissions = useCallback(async (currentSearch: string, currentState: string, periodCode = '') => {
    setLoading(true)
    setError('')
    try {
      const response = await fetchEnglishSubmissions({ search: currentSearch, state: currentState, periodCode })
      setData(response)
      setSelectedPeriod(response.selected_period_code)
      setSelected((current) => current
        ? response.items.find((item) => item.exam_id === current.exam_id) || null
        : null)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudieron consultar las entregas de Inglés.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSubmissions('', 'TODOS', '')
  }, [loadSubmissions])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const selectedComponent = useMemo(
    () => selected?.components.find((component) => component.code === selectedComponentCode) || null,
    [selected, selectedComponentCode],
  )
  const selectedRemaining = secondsUntil(selectedComponent?.edit_deadline || null, now)
  const numericGrade = Number(grade.replace(',', '.'))
  const weightedExamContribution = Number.isFinite(numericGrade) && numericGrade >= 0 && numericGrade <= 10
    ? numericGrade * 0.4
    : null
  const counters = useMemo(() => ({
    enrolled: data?.enrolled || 0,
    total: data?.total || 0,
    pending: data?.pending || 0,
    approved: data?.approved || 0,
    failed: data?.failed || 0,
  }), [data])

  function submitFilters(event: FormEvent) {
    event.preventDefault()
    void loadSubmissions(search, state, selectedPeriod)
  }

  function selectComponent(component: EnglishExamComponent) {
    setSelectedComponentCode(component.code)
    setGrade(component.grade === null ? '' : String(component.grade))
    setObservation(component.observation || '')
  }

  function openGrade(exam: EnglishExam) {
    const component = sortedComponents(exam).find((item) => item.file && item.grade === null)
      || sortedComponents(exam).find((item) => item.file)
      || sortedComponents(exam)[0]
    setSelected(exam)
    if (component) selectComponent(component)
    setError('')
    setMessage('')
  }

  async function saveGrade(event: FormEvent) {
    event.preventDefault()
    if (!selected || selected.exam_id === null || !selectedComponent) return
    const numericGrade = Number(grade.replace(',', '.'))
    if (!Number.isFinite(numericGrade) || numericGrade < 0 || numericGrade > 10) {
      setError('La calificación debe estar entre 0 y 10.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await gradeEnglishSubmission(selected.exam_id, {
        grade: numericGrade,
        observation,
        period_code: selectedPeriod,
        component_code: selectedComponent.code,
      })
      setSelected(updated)
      const nextComponent = sortedComponents(updated).find((item) => item.file && item.grade === null)
      if (nextComponent) selectComponent(nextComponent)
      setMessage(
        `${selectedComponent.label}: examen registrado para ${updated.student.name} con ${numericGrade.toFixed(2)} / 10 `
        + `(40%; aporte ${Number(numericGrade * 0.4).toFixed(2)} / 4 al parcial).`,
      )
      await loadSubmissions(search, state, selectedPeriod)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo registrar la calificación.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      {error ? <div className="english-alert english-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="english-alert english-alert--success" role="status">{message}</div> : null}

      <section className="english-review-summary">
        <div><span>Matriculados</span><strong>{counters.enrolled}</strong></div>
        <div><span>Con entregas</span><strong>{counters.total}</strong></div>
        <div><span>Pendientes</span><strong>{counters.pending}</strong></div>
        <div><span>Aprobados</span><strong>{counters.approved}</strong></div>
        <div><span>Reprobados</span><strong>{counters.failed}</strong></div>
      </section>

      <section className="student-card english-review-panel">
        <div className="card-head">
          <div><span>Revisión docente</span><h3>Entregas por período de Inglés</h3></div>
          <span>{data?.reviewer.name || ''}</span>
        </div>
        <form className="english-review-filters" onSubmit={submitFilters}>
          <label>
            <span>Período de Inglés</span>
            <select
              value={selectedPeriod}
              disabled={loading || (data?.periods.length || 0) === 0}
              onChange={(event) => {
                const periodCode = event.target.value
                setSelectedPeriod(periodCode)
                setSelected(null)
                void loadSubmissions(search, state, periodCode)
              }}
            >
              {(data?.periods.length || 0) === 0 ? <option value="">Sin períodos disponibles</option> : null}
              {(data?.periods || []).map((period) => (
                <option key={period.code} value={period.code}>{period.label} · {period.student_count} estudiante(s)</option>
              ))}
            </select>
          </label>
          <label><span>Buscar estudiante</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre, cédula o código" /></label>
          <label>
            <span>Estado</span>
            <select value={state} onChange={(event) => setState(event.target.value)}>
              <option value="TODOS">Todos</option>
              <option value="PENDIENTE">Pendientes</option>
              <option value="APROBADO">Aprobados</option>
              <option value="REPROBADO">Reprobados</option>
            </select>
          </label>
          <button type="submit" className="primary-action" disabled={loading || !selectedPeriod}>{loading ? 'Consultando...' : 'Actualizar'}</button>
        </form>

        <div className="english-table-wrap">
          <table className="english-table">
            <thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Matrícula de Inglés</th><th>Entregas</th><th>Notas</th><th>Promedio</th><th>Acción</th></tr></thead>
            <tbody>
              {!loading && (data?.items.length || 0) === 0 ? <tr><td colSpan={8} className="english-table-empty">No existen estudiantes matriculados con los filtros seleccionados.</td></tr> : null}
              {(data?.items || []).map((exam) => (
                <tr key={exam.exam_id ?? `enrollment-${exam.enrollment.enrollment_id}`}>
                  <td><strong>{exam.student.name}</strong><small>Código {exam.student.code}</small></td>
                  <td>{exam.student.identification}</td>
                  <td><strong>{exam.student.career || '-'}</strong></td>
                  <td><strong>{exam.enrollment.subject}</strong><small>{exam.enrollment.period}{exam.enrollment.parallel ? ` · ${exam.enrollment.parallel}` : ''}</small></td>
                  <td><strong>{exam.submitted_components} / {exam.required_components}</strong><small>{exam.components.filter((item) => item.file).map((item) => item.code).join(', ') || 'Sin videos'}</small></td>
                  <td><strong>{exam.graded_components} / {exam.required_components}</strong><small>{exam.components.filter((item) => item.grade !== null).map((item) => `${item.code}: ${item.grade?.toFixed(2)}`).join(' · ') || 'Sin calificar'}</small></td>
                  <td>{exam.grade === null ? '-' : <><strong>{exam.grade.toFixed(2)} / 10</strong><small><span className={resultClass(exam.result)}>{exam.result}</span></small></>}</td>
                  <td>
                    <button
                      type="button"
                      className="primary-action"
                      onClick={() => openGrade(exam)}
                      disabled={exam.exam_id === null || exam.submitted_components === 0}
                    >
                      {exam.submitted_components > 0 ? 'Ver entrega' : 'Sin entrega'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <div className="english-modal-backdrop" role="presentation">
          <section className="english-grade-modal" role="dialog" aria-modal="true" aria-labelledby="english-grade-title">
            <header>
              <div><span>Entrega y calificación de Inglés</span><h3 id="english-grade-title">{selected.student.name}</h3><p>{selected.student.identification} · {selected.enrollment.period}</p></div>
              <button type="button" className="ghost-button" onClick={() => setSelected(null)} disabled={saving}>Cerrar</button>
            </header>

            <div className="english-component-tabs" role="tablist" aria-label="Parciales de Inglés">
              {sortedComponents(selected).map((component) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={component.code === selectedComponentCode}
                  className={component.code === selectedComponentCode ? 'is-active' : ''}
                  key={component.code}
                  onClick={() => selectComponent(component)}
                >
                  <span>{component.code}</span><strong>{component.label}</strong><small>{component.file ? component.result : 'Sin entrega'}</small>
                </button>
              ))}
            </div>

            {selectedComponent ? (
              <>
                <div className="english-modal-file">
                  <div><span>Video de {selectedComponent.label}</span><strong>{selectedComponent.file?.name || 'Sin video entregado'}</strong><small>{selectedComponent.file ? fileSize(selectedComponent.file.size) : '-'}</small></div>
                  <FileActions file={selectedComponent.file} viewLabel="Ver entrega" />
                </div>
                {selectedRemaining > 0 ? (
                  <div className="english-alert english-alert--warning">El estudiante aún puede reemplazar este video durante {countdown(selectedRemaining)}.</div>
                ) : selectedComponent.file ? (
                  <form className="english-grade-form" onSubmit={saveGrade}>
                    <label>
                      <span>Examen (40%) de {selectedComponent.label}</span>
                      <input type="number" min="0" max="10" step="0.01" required value={grade} onChange={(event) => setGrade(event.target.value)} />
                      <small>Ingrese una nota de 0 a 10. Se guarda en {selectedComponent.code}Examen de CARRERAXESTUD.</small>
                    </label>
                    <label><span>Observación</span><textarea rows={4} maxLength={1500} value={observation} onChange={(event) => setObservation(event.target.value)} placeholder="Retroalimentación para el estudiante" /></label>
                    <div className="english-grade-weight-summary" aria-live="polite">
                      <div><span>Nota del examen</span><strong>{weightedExamContribution === null ? '-' : `${numericGrade.toFixed(2)} / 10`}</strong></div>
                      <div><span>Aporte al parcial (40%)</span><strong>{weightedExamContribution === null ? '-' : `${weightedExamContribution.toFixed(2)} / 4`}</strong></div>
                      <div><span>Destino académico</span><strong>{selectedComponent.code}Examen</strong></div>
                    </div>
                    <div className="english-grade-actions">
                      <button type="button" className="ghost-button" onClick={() => setSelected(null)} disabled={saving}>Cancelar</button>
                      <button type="submit" className="primary-action" disabled={saving}>{saving ? 'Guardando...' : 'Guardar examen (40%)'}</button>
                    </div>
                  </form>
                ) : <div className="english-alert english-alert--warning">El estudiante todavía no ha entregado el video de este parcial.</div>}
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  )
}

export function InglesView({ displayName, role }: Readonly<InglesViewProps>) {
  const isStudent = normalizedRole(role) === 'ESTUDIANTE'
  return (
    <section className="english-page">
      <header className="student-topbar english-hero">
        <div>
          <p className="eyebrow">Inglés</p>
          <h2>{isStudent ? 'Evaluación de Inglés' : 'Calificación de Inglés'}</h2>
          <p className="report-description">
            {isStudent
              ? 'Entregue la evidencia de P1, P2 y P3 del período en el que se encuentra matriculado.'
              : 'Revise cada parcial y registre su nota de examen de 0 a 10 en la matrícula académica.'}
          </p>
        </div>
        <div className="student-user-pill"><div><strong>{displayName}</strong><span>{isStudent ? 'Portal estudiante' : 'Revisión docente'}</span></div></div>
      </header>
      {isStudent ? <StudentEnglishExam displayName={displayName} /> : <ReviewerEnglishExams />}
    </section>
  )
}
