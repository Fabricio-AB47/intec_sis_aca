import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  confirmEnglishDelivery,
  createEnglishUploadSession,
  englishExamFileUrl,
  fetchEnglishStudentExam,
  fetchEnglishSubmissions,
  finalizeEnglishUpload,
  publishEnglishRubricGrade,
  saveEnglishRubricDraft,
  uploadEnglishFileChunks,
} from '../../lib/api'
import type {
  EnglishExam,
  EnglishExamComponent,
  EnglishExamFile,
  EnglishSubmissionsResponse,
} from '../../types/app'
import { CalificacionesTabs } from '../admin/CalificacionesTabs'

type InglesViewProps = {
  displayName: string
  role: string
  onOpenSubjectGrades?: () => void
}

const MIN_FILE_BYTES = 50 * 1024 * 1024
const MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
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
  if (component.confirmed) return 'Entrega definitiva confirmada'
  if (component.file) return 'Cargado · pendiente de confirmar'
  if (!component.activity_open) return component.activity_status === 'AUN_NO_INICIA' ? 'Actividad no iniciada' : 'Plazo finalizado'
  return 'Pendiente de entrega'
}

type RubricForm = {
  language_mastery: string
  fluency_pronunciation: string
  content_coherence: string
  instruction_compliance: string
}

const EMPTY_RUBRIC: RubricForm = {
  language_mastery: '',
  fluency_pronunciation: '',
  content_coherence: '',
  instruction_compliance: '',
}

const RUBRIC_FIELDS: Array<{ key: keyof RubricForm; label: string; weight: number }> = [
  { key: 'language_mastery', label: 'Dominio del idioma', weight: 30 },
  { key: 'fluency_pronunciation', label: 'Fluidez y pronunciación', weight: 30 },
  { key: 'content_coherence', label: 'Contenido y coherencia', weight: 25 },
  { key: 'instruction_compliance', label: 'Cumplimiento de instrucciones', weight: 15 },
]

function rubricNumbers(rubric: RubricForm) {
  const values = RUBRIC_FIELDS.map(({ key }) => Number(rubric[key].replace(',', '.')))
  if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 10)) return null
  return Object.fromEntries(RUBRIC_FIELDS.map(({ key }, index) => [key, values[index]])) as Record<keyof RubricForm, number>
}

function rubricGrade(rubric: RubricForm) {
  const values = rubricNumbers(rubric)
  if (!values) return null
  return RUBRIC_FIELDS.reduce((total, field) => total + (values[field.key] * field.weight / 100), 0)
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
      setError(errorMessage(requestError, 'No se pudo validar la matrícula en la Escuela de Idiomas.'))
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
    if (file.size < (exam?.min_file_bytes || MIN_FILE_BYTES)) {
      setSelectedFiles((current) => ({ ...current, [componentCode]: null }))
      setFileInputKeys((current) => ({ ...current, [componentCode]: (current[componentCode] || 0) + 1 }))
      setError('El video debe tener al menos 50 MB.')
      return
    }
    if (file.size > (exam?.max_file_bytes || MAX_FILE_BYTES)) {
      setSelectedFiles((current) => ({ ...current, [componentCode]: null }))
      setFileInputKeys((current) => ({ ...current, [componentCode]: (current[componentCode] || 0) + 1 }))
      setError('El video supera el límite máximo de 2 GB.')
      return
    }
    setSelectedFiles((current) => ({ ...current, [componentCode]: file }))
  }

  async function uploadFile(component: EnglishExamComponent) {
    const selectedFile = selectedFiles[component.code]
    const remaining = secondsUntil(component.edit_deadline, now)
    const canReplace = Boolean(component.file && !component.confirmed && component.grade === null && remaining > 0)
    const canUpload = component.activity_open && component.grade === null && !component.confirmed && (!component.file || canReplace)
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
      setMessage(updatedComponent?.file?.version === 1
        ? `${component.label} cargado y validado. Revise la vista previa y confirme la entrega definitiva.`
        : `${component.label} reemplazado. Revise el video y confirme la entrega definitiva.`)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo completar la carga del video.'))
      await loadExam()
    } finally {
      setUploadingCode('')
    }
  }

  async function confirmDelivery(component: EnglishExamComponent) {
    if (!component.file || !component.can_confirm || component.confirmed) return
    setUploadingCode(component.code)
    setError('')
    setMessage('')
    try {
      const updatedExam = await confirmEnglishDelivery(component.file.upload_id, component.code)
      setExam(updatedExam)
      const nextPending = sortedComponents(updatedExam).find((item) => !item.confirmed)
      if (nextPending) setSelectedComponentCode(nextPending.code)
      setMessage(`${component.label} confirmado como entrega definitiva. Ya no admite reemplazo ni eliminación.`)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo confirmar la entrega definitiva.'))
      await loadExam()
    } finally {
      setUploadingCode('')
    }
  }

  if (loading) return <section className="student-card english-loading">Validando matrícula de la Escuela de Idiomas...</section>

  if (!exam) {
    return (
      <>
        {error ? <div className="english-alert english-alert--error" role="alert">{error}</div> : null}
        <section className="student-card english-enrollment-lock">
          <span className="english-badge english-badge--locked">Carga no habilitada</span>
          <h3>No existe una matrícula vigente en la Escuela de Idiomas</h3>
          <p>La carga de P1, P2 y P3 se habilita únicamente cuando el estudiante consta matriculado en una asignatura de Idiomas y en un período activo.</p>
        </section>
      </>
    )
  }

  const component = selectedComponent
  const remaining = component ? secondsUntil(component.edit_deadline, now) : 0
  const canReplace = Boolean(component?.file && !component.confirmed && component.grade === null && remaining > 0)
  const canUpload = Boolean(component && component.activity_open && component.grade === null && !component.confirmed && (!component.file || canReplace))
  const selectedFile = component ? selectedFiles[component.code] : null
  const uploading = Boolean(component && uploadingCode === component.code)
  const progress = component ? progressByCode[component.code] || 0 : 0

  return (
    <>
      {error ? <div className="english-alert english-alert--error" role="alert">{error}</div> : null}
      {message ? <div className="english-alert english-alert--success" role="status">{message}</div> : null}

      <section className="english-summary" aria-label="Resumen de matrícula de la Escuela de Idiomas">
        <div><span>Estudiante</span><strong>{exam.student.name || displayName}</strong><small>{exam.student.identification}</small></div>
        <div><span>Carrera</span><strong>{exam.student.career || 'Sin carrera registrada'}</strong><small>Matrícula académica principal</small></div>
        <div><span>Matrícula de Idiomas</span><strong>{exam.enrollment.subject}</strong><small>{exam.enrollment.period}{exam.enrollment.parallel ? ` · Paralelo ${exam.enrollment.parallel}` : ''}</small></div>
        <div><span>Avance</span><strong>{exam.submitted_components} / {exam.required_components} parciales</strong><small>{exam.grade === null ? 'Calificación final pendiente' : `Promedio ${exam.grade.toFixed(2)} / 10`}</small></div>
      </section>

      <section className="student-card english-student-panel">
        <div className="card-head english-card-head">
          <div>
            <span>Entrega estudiantil</span>
            <h3>Evidencias por parcial</h3>
            <p>Cargue un video de 50 MB a 2 GB, revise la vista previa y confirme la entrega definitiva antes del cierre.</p>
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
              <>
                <div className="english-partial-file">
                  <div>
                    <strong>{component.file.name}</strong>
                    <small>v{component.file.version} · {fileSize(component.file.size)} · {dateTime(component.file.uploaded_at)}</small>
                    <span className={component.confirmed ? 'english-badge english-badge--ok' : 'english-badge english-badge--pending'}>
                      {component.confirmed ? 'Entrega definitiva' : 'Pendiente de confirmación'}
                    </span>
                  </div>
                  <FileActions file={component.file} />
                </div>
                {!component.confirmed ? (
                  <video className="english-video-preview" controls preload="metadata" src={englishExamFileUrl(component.file.upload_id, 'download')}>
                    Su navegador no puede reproducir este video.
                  </video>
                ) : null}
              </>
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
                <small>{selectedFile ? `${selectedFile.name} · ${fileSize(selectedFile.size)}` : 'Video MP4, MOV, MKV o WEBM. Entre 50 MB y 2 GB.'}</small>
                <button type="button" className="primary-action" onClick={() => void uploadFile(component)} disabled={!selectedFile || Boolean(uploadingCode)}>
                  {uploading ? `Subiendo ${progress}%` : component.file ? 'Reemplazar carga temporal' : `Cargar ${component.label}`}
                </button>
                {uploading ? <div className="english-upload-progress"><span style={{ width: `${progress}%` }} /></div> : null}
              </div>
            ) : null}

            {component.file && !component.confirmed ? (
              <div className="english-confirm-delivery">
                <div>
                  <strong>Confirme únicamente después de revisar el video.</strong>
                  <span>La confirmación bloquea definitivamente el reemplazo y notifica al docente.</span>
                </div>
                <button
                  type="button"
                  className="primary-action"
                  disabled={!component.can_confirm || Boolean(uploadingCode)}
                  onClick={() => void confirmDelivery(component)}
                >
                  {uploadingCode === component.code ? 'Confirmando...' : 'Confirmar entrega definitiva'}
                </button>
              </div>
            ) : null}

            {component.file && !component.confirmed && component.grade === null ? (
              <p className="english-window-note">
                {remaining > 0 ? `Reemplazo disponible durante ${countdown(remaining)}.` : 'El plazo de reemplazo terminó; todavía debe confirmar la carga actual.'}
              </p>
            ) : null}

            <div className="english-activity-window">
              <span>Inicio: <strong>{dateTime(component.activity_start)}</strong></span>
              <span>Cierre: <strong>{dateTime(component.activity_deadline)}</strong></span>
              <span>Estado: <strong>{component.activity_open ? 'Actividad abierta' : component.activity_status === 'AUN_NO_INICIA' ? 'Aún no inicia' : 'Plazo finalizado'}</strong></span>
            </div>
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
  const [selectedSubject, setSelectedSubject] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selected, setSelected] = useState<EnglishExam | null>(null)
  const [selectedComponentCode, setSelectedComponentCode] = useState('')
  const [rubric, setRubric] = useState<RubricForm>(EMPTY_RUBRIC)
  const [observation, setObservation] = useState('')

  const loadSubmissions = useCallback(async (
    currentSearch: string,
    currentState: string,
    periodCode = '',
    subjectCode = '',
    silent = false,
  ) => {
    if (!silent) setLoading(true)
    setError('')
    try {
      const response = await fetchEnglishSubmissions({
        search: currentSearch,
        state: currentState,
        periodCode,
        subjectCode,
      })
      setData(response)
      setSelectedPeriod(response.selected_period_code)
      setSelectedSubject(response.selected_subject_code)
      setSelected((current) => current
        ? response.items.find((item) => item.exam_id === current.exam_id) || null
        : null)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudieron consultar las entregas de la Escuela de Idiomas.'))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSubmissions('', 'TODOS', '', '')
  }, [loadSubmissions])

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== 'visible') return
      void loadSubmissions(search, state, selectedPeriod, selectedSubject, true)
    }
    const timer = window.setInterval(refresh, 30_000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [loadSubmissions, search, selectedPeriod, selectedSubject, state])

  const selectedComponent = useMemo(
    () => selected?.components.find((component) => component.code === selectedComponentCode) || null,
    [selected, selectedComponentCode],
  )
  const calculatedRubricGrade = rubricGrade(rubric)
  const counters = useMemo(() => ({
    enrolled: data?.enrolled || 0,
    total: data?.total || 0,
    pending: data?.pending || 0,
    approved: data?.approved || 0,
    failed: data?.failed || 0,
  }), [data])

  function submitFilters(event: FormEvent) {
    event.preventDefault()
    void loadSubmissions(search, state, selectedPeriod, selectedSubject)
  }

  function selectComponent(component: EnglishExamComponent) {
    setSelectedComponentCode(component.code)
    const source = component.draft_rubric
    setRubric(source ? {
      language_mastery: String(source.language_mastery),
      fluency_pronunciation: String(source.fluency_pronunciation),
      content_coherence: String(source.content_coherence),
      instruction_compliance: String(source.instruction_compliance),
    } : component.grade !== null ? {
      language_mastery: String(component.grade),
      fluency_pronunciation: String(component.grade),
      content_coherence: String(component.grade),
      instruction_compliance: String(component.grade),
    } : EMPTY_RUBRIC)
    setObservation(component.draft_observation || component.observation || '')
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

  async function saveDraft(event: FormEvent) {
    event.preventDefault()
    if (!selected || selected.exam_id === null || !selectedComponent) return
    const values = rubricNumbers(rubric)
    if (!values) {
      setError('Todos los criterios de la rúbrica deben tener una calificación entre 0 y 10.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await saveEnglishRubricDraft(selected.exam_id, {
        ...values,
        observation,
        period_code: selectedPeriod,
        component_code: selectedComponent.code,
      })
      setSelected(updated)
      const updatedComponent = updated.components.find((item) => item.code === selectedComponent.code)
      if (updatedComponent) selectComponent(updatedComponent)
      setMessage(`${selectedComponent.label}: borrador de rúbrica guardado sin publicar la nota.`)
      await loadSubmissions(search, state, selectedPeriod, selectedSubject)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo guardar el borrador de la rúbrica.'))
    } finally {
      setSaving(false)
    }
  }

  async function publishGrade() {
    if (!selected || selected.exam_id === null || !selectedComponent || selectedComponent.review_state !== 'BORRADOR_DOCENTE') return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await publishEnglishRubricGrade(selected.exam_id, {
        period_code: selectedPeriod,
        component_code: selectedComponent.code,
      })
      setSelected(updated)
      const nextComponent = sortedComponents(updated).find((item) => item.confirmed && item.grade === null)
      if (nextComponent) selectComponent(nextComponent)
      else {
        const published = updated.components.find((item) => item.code === selectedComponent.code)
        if (published) selectComponent(published)
      }
      setMessage(`${selectedComponent.label}: calificación publicada y registrada en la matrícula académica.`)
      await loadSubmissions(search, state, selectedPeriod, selectedSubject)
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo publicar la calificación.'))
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
          <div><span>Revisión docente</span><h3>Matrícula y entregas por asignatura de Idiomas</h3></div>
          <span>{data?.reviewer.name || ''}</span>
        </div>
        <form className="english-review-filters" onSubmit={submitFilters}>
          <label>
            <span>Período de Idiomas</span>
            <select
              value={selectedPeriod}
              disabled={loading || (data?.periods.length || 0) === 0}
              onChange={(event) => {
                const periodCode = event.target.value
                setSelectedPeriod(periodCode)
                setSelectedSubject('')
                setSelected(null)
                void loadSubmissions(search, state, periodCode, '')
              }}
            >
              {(data?.periods.length || 0) === 0 ? <option value="">Sin períodos disponibles</option> : null}
              {(data?.periods || []).map((period) => (
                <option key={period.code} value={period.code}>{period.label} · {period.student_count} estudiante(s)</option>
              ))}
            </select>
          </label>
          <label>
            <span>Asignatura de Idiomas</span>
            <select
              value={selectedSubject}
              disabled={loading || (data?.subjects.length || 0) === 0}
              onChange={(event) => {
                const subjectCode = event.target.value
                setSelectedSubject(subjectCode)
                setSelected(null)
                void loadSubmissions(search, state, selectedPeriod, subjectCode)
              }}
            >
              {(data?.subjects.length || 0) === 0 ? <option value="">Sin asignaturas disponibles</option> : null}
              {(data?.subjects || []).map((subject) => (
                <option key={subject.code} value={subject.code}>{subject.label} · {subject.student_count} estudiante(s)</option>
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
          <button type="submit" className="primary-action" disabled={loading || !selectedPeriod || !selectedSubject}>{loading ? 'Consultando...' : 'Actualizar'}</button>
        </form>

        <div className="english-table-wrap">
          <table className="english-table">
            <thead><tr><th>Estudiante</th><th>Cédula</th><th>Carrera</th><th>Matrícula de Idiomas</th><th>Entregas</th><th>Notas</th><th>Promedio</th><th>Acción</th></tr></thead>
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
              <div><span>Entrega y calificación de Idiomas</span><h3 id="english-grade-title">{selected.student.name}</h3><p>{selected.student.identification} · {selected.enrollment.period}</p></div>
              <button type="button" className="ghost-button" onClick={() => setSelected(null)} disabled={saving}>Cerrar</button>
            </header>

            <div className="english-component-tabs" role="tablist" aria-label="Parciales de Idiomas">
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
                {selectedComponent.file ? (
                  <>
                    <video
                      className="english-review-video"
                      controls
                      preload="metadata"
                      src={englishExamFileUrl(selectedComponent.file.upload_id, 'download')}
                    >
                      Su navegador no puede reproducir este video.
                    </video>
                    <form className="english-grade-form" onSubmit={saveDraft}>
                      <fieldset className="english-rubric" disabled={saving || selectedComponent.review_state === 'PUBLICADO'}>
                        <legend>Rúbrica de evaluación · nota máxima 10</legend>
                        {RUBRIC_FIELDS.map((field) => (
                          <label key={field.key}>
                            <span>{field.label} ({field.weight}%)</span>
                            <input
                              type="number"
                              min="0"
                              max="10"
                              step="0.01"
                              required
                              value={rubric[field.key]}
                              onChange={(event) => setRubric((current) => ({ ...current, [field.key]: event.target.value }))}
                            />
                          </label>
                        ))}
                      </fieldset>
                      <label>
                        <span>Observación y retroalimentación</span>
                        <textarea
                          rows={4}
                          maxLength={1500}
                          disabled={saving || selectedComponent.review_state === 'PUBLICADO'}
                          value={observation}
                          onChange={(event) => setObservation(event.target.value)}
                          placeholder="Observaciones para el estudiante"
                        />
                      </label>
                      <div className="english-grade-weight-summary" aria-live="polite">
                        <div><span>Resultado de rúbrica</span><strong>{calculatedRubricGrade === null ? '-' : `${calculatedRubricGrade.toFixed(2)} / 10`}</strong></div>
                        <div><span>Aporte al parcial (40%)</span><strong>{calculatedRubricGrade === null ? '-' : `${(calculatedRubricGrade * 0.4).toFixed(2)} / 4`}</strong></div>
                        <div><span>Estado</span><strong>{selectedComponent.review_state === 'PUBLICADO' ? 'Publicada' : selectedComponent.review_state === 'BORRADOR_DOCENTE' ? 'Borrador guardado' : 'Pendiente de revisión'}</strong></div>
                        <div><span>Destino académico</span><strong>{selectedComponent.code}Examen</strong></div>
                      </div>
                      {selectedComponent.review_state === 'PUBLICADO' ? (
                        <div className="english-alert english-alert--success">Calificación publicada y bloqueada el {dateTime(selectedComponent.published_at)}.</div>
                      ) : null}
                      <div className="english-grade-actions">
                        <button type="button" className="ghost-button" onClick={() => setSelected(null)} disabled={saving}>Cancelar</button>
                        <button type="submit" className="ghost-button" disabled={saving || calculatedRubricGrade === null || selectedComponent.review_state === 'PUBLICADO'}>
                          {saving ? 'Guardando...' : 'Guardar borrador'}
                        </button>
                        <button
                          type="button"
                          className="primary-action"
                          disabled={saving || selectedComponent.review_state !== 'BORRADOR_DOCENTE'}
                          onClick={() => void publishGrade()}
                        >
                          {saving ? 'Procesando...' : 'Publicar calificación'}
                        </button>
                      </div>
                    </form>
                  </>
                ) : <div className="english-alert english-alert--warning">El estudiante todavía no ha entregado el video de este parcial.</div>}
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  )
}

export function InglesView({ displayName, role, onOpenSubjectGrades }: Readonly<InglesViewProps>) {
  const isStudent = normalizedRole(role) === 'ESTUDIANTE'
  return (
    <section className="english-page">
      <header className="student-topbar english-hero">
        <div>
          <p className="eyebrow">Escuela de Idiomas</p>
          <h2>{isStudent ? 'Evaluación de idiomas' : 'Calificaciones de idiomas'}</h2>
          <p className="report-description">
            {isStudent
              ? 'Entregue los videos de P1, P2 y P3 únicamente para la asignatura y el período en que se encuentra matriculado.'
              : 'Revise estudiantes con matrícula vigente y registre la nota de examen de cada parcial, de 0 a 10.'}
          </p>
        </div>
        <div className="student-user-pill"><div><strong>{displayName}</strong><span>{isStudent ? 'Portal estudiante' : 'Revisión docente'}</span></div></div>
      </header>
      {!isStudent && onOpenSubjectGrades ? (
        <CalificacionesTabs active="idiomas" onOpenSubjects={onOpenSubjectGrades} />
      ) : null}
      {isStudent ? <StudentEnglishExam displayName={displayName} /> : <ReviewerEnglishExams />}
    </section>
  )
}
