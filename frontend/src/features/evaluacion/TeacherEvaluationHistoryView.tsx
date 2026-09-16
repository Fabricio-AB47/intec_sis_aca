import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import {
  fetchHistoricalSelfEvaluationCatalog,
  fetchHistoricalSelfEvaluationHistory,
  generateHistoricalSelfEvaluations,
  previewHistoricalSelfEvaluations,
  TEACHER_EVALUATION_ALERT_INVALIDATED_EVENT,
} from '../../lib/api'
import type {
  HistoricalSelfEvaluationCatalog,
  HistoricalSelfEvaluationHistory,
  HistoricalSelfEvaluationPreview,
  HistoricalSelfEvaluationResult,
} from '../../types/app'

const PAGE_SIZE = 10

type GenerationProgress = {
  processed: number
  total: number
  created: number
  skipped: number
  offset: number
  token: string
  reason: string
}

function toggleCode(values: number[], code: number) {
  return values.includes(code) ? values.filter((value) => value !== code) : [...values, code]
}

function teachersForPeriods(catalog: HistoricalSelfEvaluationCatalog | null, periods: number[]) {
  const selected = new Set(periods)
  return (catalog?.teachers || []).filter((teacher) => teacher.periods.some((period) => selected.has(period)))
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Guayaquil' }).format(date)
}

export function TeacherEvaluationHistoryView({ navigation }: { navigation?: ReactNode }) {
  const [catalog, setCatalog] = useState<HistoricalSelfEvaluationCatalog | null>(null)
  const [periods, setPeriods] = useState<number[]>([])
  const [teachers, setTeachers] = useState<number[]>([])
  const [search, setSearch] = useState('')
  const [year, setYear] = useState('all')
  const [tab, setTab] = useState<'generate' | 'history'>('generate')
  const [preview, setPreview] = useState<HistoricalSelfEvaluationPreview | null>(null)
  const [result, setResult] = useState<HistoricalSelfEvaluationResult | null>(null)
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null)
  const [history, setHistory] = useState<HistoricalSelfEvaluationHistory | null>(null)
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [historyPage, setHistoryPage] = useState(0)
  const [activeItem, setActiveItem] = useState<HistoricalSelfEvaluationPreview['items'][number] | null>(null)
  const mounted = useRef(false)
  const generationInFlight = useRef(false)

  useEffect(() => {
    let cancelled = false
    mounted.current = true
    fetchHistoricalSelfEvaluationCatalog()
      .then((data) => { if (!cancelled) setCatalog(data) })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : 'No se pudieron cargar los períodos y docentes.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; mounted.current = false }
  }, [])

  const visiblePeriods = (catalog?.periods || []).filter((period) => year === 'all' || period.year === Number(year))
  const allTeachers = useMemo(() => teachersForPeriods(catalog, periods), [catalog, periods])
  const allTeachersSelected = allTeachers.length > 0 && allTeachers.every((teacher) => teachers.includes(teacher.codigo_doc))
  const visibleTeachers = useMemo(() => {
    const text = search.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    return allTeachers.filter((teacher) => `${teacher.docente} ${teacher.cedula_doc} ${teacher.codigo_doc}`.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().includes(text))
  }, [allTeachers, search])
  const teacherIdentities = new Map((catalog?.teachers || []).map((teacher) => [String(teacher.codigo_doc), teacher]))
  const periodNames = new Map((catalog?.periods || []).map((period) => [String(period.codigo_periodo), period.detalle_periodo]))
  const totalPages = Math.ceil((preview?.items.length || 0) / PAGE_SIZE)
  const historyPages = Math.ceil((history?.items.length || 0) / PAGE_SIZE)

  function invalidatePreview() {
    setPreview(null)
    setActiveItem(null)
    setResult(null)
    setGenerationProgress(null)
    setConfirmed(false)
    setError('')
  }

  function changePeriods(nextPeriods: number[]) {
    invalidatePreview()
    setPeriods(nextPeriods)
    const available = new Set(teachersForPeriods(catalog, nextPeriods).map((teacher) => teacher.codigo_doc))
    setTeachers((current) => current.filter((code) => available.has(code)))
  }

  async function loadHistory() {
    setBusy(true)
    setError('')
    try {
      setHistory(await fetchHistoricalSelfEvaluationHistory())
      setHistoryPage(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar el historial.')
    } finally {
      setBusy(false)
    }
  }

  async function handlePreview() {
    setBusy(true)
    invalidatePreview()
    try {
      setPreview(await previewHistoricalSelfEvaluations({ periods, teachers }))
      setPage(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo generar la vista previa.')
    } finally {
      setBusy(false)
    }
  }

  async function handleGenerate() {
    if (generationInFlight.current || !preview || !confirmed || reason.trim().length < 10) return
    generationInFlight.current = true
    setBusy(true)
    setError('')
    let progress = generationProgress || {
      processed: 0, total: preview.items.length, created: 0, skipped: 0,
      offset: 0, token: preview.preview_token, reason: reason.trim(),
    }
    setGenerationProgress(progress)
    try {
      while (mounted.current) {
        const response = await generateHistoricalSelfEvaluations(progress.token, progress.reason, progress.offset)
        const nextOffset = response.next_offset ?? null
        const processed = response.processed ?? progress.processed + response.created + response.skipped
        const total = response.total ?? progress.total
        if (total !== progress.total || processed > total || processed !== progress.offset + response.created + response.skipped
          || (nextOffset === null ? processed !== total : nextOffset !== processed || nextOffset <= progress.offset || !response.preview_token)) {
          throw new Error('El servidor no confirmó el avance del bloque. Reintente el proceso.')
        }
        progress = {
          ...progress,
          processed,
          total,
          created: progress.created + response.created,
          skipped: progress.skipped + response.skipped,
          offset: nextOffset ?? response.processed ?? progress.total,
          token: response.preview_token || progress.token,
        }
        if (!mounted.current) break
        setGenerationProgress(progress)
        if (nextOffset === null) {
          setResult({ ...response, created: progress.created, skipped: progress.skipped })
          setPreview(null)
          setActiveItem(null)
          setConfirmed(false)
          setHistory(null)
          break
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron guardar las autoevaluaciones.')
    } finally {
      generationInFlight.current = false
      if (progress.processed > 0) window.dispatchEvent(new Event(TEACHER_EVALUATION_ALERT_INVALIDATED_EVENT))
      if (mounted.current) setBusy(false)
    }
  }

  return (
    <main className="teacher-evaluation teacher-evaluation--compact teacher-evaluation-history">
      {navigation}
      <section className="teacher-evaluation__hero teacher-evaluation__hero--compact">
        <div>
          <p className="teacher-evaluation__eyebrow">Evaluación docente 360</p>
          <h1>Autoevaluaciones históricas</h1>
        </div>
        <span className="teacher-evaluation__summary-pill">2023 - 2025</span>
      </section>

      <div className="teacher-evaluation-history__tabs" role="tablist" aria-label="Autoevaluaciones históricas">
        <button role="tab" id="historical-generate-tab" aria-controls="historical-generate-panel" aria-selected={tab === 'generate'} onClick={() => setTab('generate')} disabled={busy}>Generación</button>
        <button role="tab" id="historical-history-tab" aria-controls="historical-history-panel" aria-selected={tab === 'history'} onClick={() => { setTab('history'); if (!history) void loadHistory() }} disabled={busy}>Historial</button>
      </div>

      {error ? <div role="alert" className="teacher-evaluation__message teacher-evaluation__message--error">{error}</div> : null}
      {result ? <div role="status" className="teacher-evaluation__message teacher-evaluation__message--success">{result.created} autoevaluaciones generadas · {result.skipped} existentes conservadas. Lote: {result.batch_id}</div> : null}
      {generationProgress ? (
        <section className="teacher-evaluation-history__generation-progress" role="status" aria-live="polite">
          <div><strong>{busy ? 'Generando autoevaluaciones' : generationProgress.processed >= generationProgress.total ? 'Generación completada' : 'Generación pendiente'}</strong><span>Procesadas {generationProgress.processed} / {generationProgress.total}</span></div>
          <progress aria-label="Avance de generación" max={generationProgress.total || 1} value={generationProgress.processed} />
          <small>{generationProgress.created} creadas · {generationProgress.skipped} existentes conservadas</small>
        </section>
      ) : null}

      {tab === 'generate' ? (
        <div id="historical-generate-panel" role="tabpanel" aria-labelledby="historical-generate-tab">
          <div className="teacher-evaluation-history__notice">Autoevaluaciones generadas administrativamente y vinculadas al docente por su cédula. Responsable y fecha real registrados; no son respuestas enviadas personalmente por el docente.</div>
          {loading ? <p role="status">Cargando períodos y docentes...</p> : !catalog ? <button className="teacher-evaluation__secondary" onClick={() => window.location.reload()}>Reintentar</button> : (
            <>
              <div className="teacher-evaluation-history__selectors">
                <section className="teacher-evaluation-history__selector">
                  <header><h2>Períodos <span>{periods.length}</span></h2><select aria-label="Año del período" value={year} onChange={(event) => setYear(event.target.value)} disabled={busy}><option value="all">Todos los años</option>{[2023, 2024, 2025].map((value) => <option key={value} value={value}>{value}</option>)}</select></header>
                  <div className="teacher-evaluation-history__selection-actions"><button disabled={busy || !visiblePeriods.length} onClick={() => changePeriods([...new Set([...periods, ...visiblePeriods.map((period) => period.codigo_periodo)])])}>Seleccionar visibles</button><button disabled={busy || !periods.length} onClick={() => changePeriods([])}>Limpiar</button></div>
                  <div className="teacher-evaluation-history__options">
                    {visiblePeriods.length ? visiblePeriods.map((period) => (
                      <label key={period.codigo_periodo}><input type="checkbox" checked={periods.includes(period.codigo_periodo)} disabled={busy} onChange={() => changePeriods(toggleCode(periods, period.codigo_periodo))} /><span><strong>{period.detalle_periodo}</strong><small>Código {period.codigo_periodo} · Inicio {period.year}</small></span></label>
                    )) : <p>No existen períodos para este año.</p>}
                  </div>
                </section>
                <section className="teacher-evaluation-history__selector">
                  <header><h2>Docentes activos <span>{teachers.length}/{allTeachers.length}</span></h2><input aria-label="Buscar docente" placeholder="Nombre, cédula o código" value={search} onChange={(event) => setSearch(event.target.value)} disabled={busy} /></header>
                  <div className="teacher-evaluation-history__selection-actions">
                    <button disabled={busy || !allTeachers.length || allTeachersSelected} onClick={() => { invalidatePreview(); setTeachers(allTeachers.map((teacher) => teacher.codigo_doc)) }}>Seleccionar todos</button>
                    {search.trim() ? <button disabled={busy || !visibleTeachers.length} onClick={() => { invalidatePreview(); setTeachers([...new Set([...teachers, ...visibleTeachers.map((teacher) => teacher.codigo_doc)])]) }}>Seleccionar visibles</button> : null}
                    <button disabled={busy || !teachers.length} onClick={() => { invalidatePreview(); setTeachers([]) }}>Limpiar</button>
                  </div>
                  <div className="teacher-evaluation-history__options">
                    {visibleTeachers.length ? visibleTeachers.map((teacher) => (
                      <label key={teacher.codigo_doc}><input type="checkbox" checked={teachers.includes(teacher.codigo_doc)} disabled={busy} onChange={() => { invalidatePreview(); setTeachers(toggleCode(teachers, teacher.codigo_doc)) }} /><span><strong>{teacher.docente}</strong><small>{teacher.cedula_doc} · Código {teacher.codigo_doc}</small></span></label>
                    )) : <p>{!periods.length ? 'Sin períodos seleccionados.' : !allTeachers.length ? 'No existen docentes activos con clases asignadas en estos períodos.' : 'No se encontraron docentes activos.'}</p>}
                  </div>
                </section>
              </div>
              <div className="teacher-evaluation-history__toolbar"><span>Resultado de autoevaluación: desde 9,00 y menor que 10,00 / 10</span><button className="teacher-evaluation__primary" disabled={busy || !periods.length || !teachers.length} onClick={() => void handlePreview()}>{busy ? 'Procesando...' : 'Generar vista previa'}</button></div>
            </>
          )}
          {preview ? (
            <section className="teacher-evaluation-history__preview">
              <header><h2>Vista previa</h2><span>{preview.pending} pendientes · {preview.existing} existentes</span></header>
              <p className="teacher-evaluation-history__instrument">Instrumento actual: {preview.instrument.Nombre || preview.instrument.Codigo || preview.instrument.Id_Instrumento} · Vigencia de la vista previa: {preview.expires_in_minutes} minutos.</p>
              <div className="teacher-evaluation-history__table-wrap"><table><thead><tr><th>Docente</th><th>Período</th><th>Materia y paralelo</th><th>Resultado / 10</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>
                {preview.items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((item) => (
                  <tr key={item.course.key}><td>{item.course.docente}<small>{item.course.cedula_docente}</small></td><td>{item.course.detalle_periodo}</td><td>{item.course.materia}<small>{item.course.codigo_materia_interno} · {item.course.paralelo || '-'} · {item.course.carrera}</small></td><td>{item.status === 'PENDIENTE' ? item.score_10.toFixed(2) : '-'}</td><td><span className={`teacher-evaluation-history__status${item.status === 'EXISTENTE' ? ' teacher-evaluation-history__status--existing' : ''}`}>{item.status === 'EXISTENTE' ? 'Se conserva' : 'Por generar'}</span></td><td><button className="teacher-evaluation__secondary" disabled={item.status === 'EXISTENTE'} onClick={() => setActiveItem(item)}>Respuestas</button></td></tr>
                ))}
              </tbody></table></div>
              <div className="teacher-evaluation-history__pagination"><span>Página {page + 1} de {totalPages}</span><button disabled={page === 0} onClick={() => setPage(page - 1)}>Anterior</button><button disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</button></div>
              {activeItem ? <section className="teacher-evaluation-history__answers"><header><h3>{activeItem.course.docente} · {activeItem.course.materia}</h3><button className="teacher-evaluation__secondary" onClick={() => setActiveItem(null)}>Cerrar respuestas</button></header><ol>{preview.questions.map((question) => <li key={question.id_pregunta}><span>{question.detalle_preg}</span><strong>{activeItem.answers.find((answer) => answer.id_pregunta === question.id_pregunta)?.puntaje} / 5</strong></li>)}</ol></section> : null}
              {preview.pending > 0 ? (
                <div className="teacher-evaluation-history__confirmation">
                  <label>
                    Motivo administrativo
                    <textarea
                      aria-label="Motivo administrativo"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      maxLength={250}
                      minLength={10}
                      disabled={busy || Boolean(generationProgress)}
                      rows={2}
                      required
                    />
                  </label>
                  <label className="teacher-evaluation-history__acknowledgment">
                    <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} disabled={busy || Boolean(generationProgress)} />
                    <span>Autorizo como administrador el registro masivo de {preview.pending} autoevaluaciones vinculadas a los docentes por cédula, identificadas como generación administrativa en los informes oficiales 360.</span>
                  </label>
                  <button className="teacher-evaluation__primary" disabled={busy || !confirmed || reason.trim().length < 10} onClick={() => void handleGenerate()}>
                    {busy ? 'Guardando...' : generationProgress ? 'Reintentar pendientes' : 'Confirmar y guardar'}
                  </button>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : (
        <section id="historical-history-panel" role="tabpanel" aria-labelledby="historical-history-tab" className="teacher-evaluation-history__preview">
          <header><h2>Registros generados</h2><button className="teacher-evaluation__secondary" disabled={busy} onClick={() => void loadHistory()}>{busy ? 'Consultando...' : 'Actualizar'}</button></header>
          <div className="teacher-evaluation-history__table-wrap"><table><thead><tr><th>Registro y lote</th><th>Docente vinculado</th><th>Período y materia</th><th>Resultado / 10</th><th>Origen</th><th>Responsable de generación y fecha</th><th>Motivo</th></tr></thead><tbody>
            {(history?.items || []).slice(historyPage * PAGE_SIZE, (historyPage + 1) * PAGE_SIZE).map((item) => <tr key={item.Id_Aplicacion}><td>#{item.Id_Aplicacion}<small>{item.batch_id}</small></td><td>{item.teacher_name || teacherIdentities.get(String(item.Cod_Docente_Evaluado))?.docente || `Docente ${item.Cod_Docente_Evaluado}`}<small>Cédula: {item.teacher_cedula || teacherIdentities.get(String(item.Cod_Docente_Evaluado))?.cedula_doc || 'No registrada'}</small></td><td>{periodNames.get(String(item.Cod_Periodo)) || item.Cod_Periodo}<small>Materia {item.Cod_Materia} · Paralelo {item.Paralelo || '-'}</small></td><td>{item.score_10.toFixed(2)}</td><td><span className="teacher-evaluation-history__status">Administrativo</span></td><td>{item.actor_name || item.actor_login}<small>{item.actor_login} · {formatDate(item.created_at)}</small></td><td>{item.reason}</td></tr>)}
            {!busy && !history?.items.length ? <tr><td colSpan={7}>No existen autoevaluaciones generadas administrativamente.</td></tr> : null}
          </tbody></table></div>
          {historyPages > 0 ? <div className="teacher-evaluation-history__pagination"><span>Últimos {history?.total} registros · Página {historyPage + 1} de {historyPages}</span><button disabled={historyPage === 0} onClick={() => setHistoryPage(historyPage - 1)}>Anterior</button><button disabled={historyPage + 1 >= historyPages} onClick={() => setHistoryPage(historyPage + 1)}>Siguiente</button></div> : null}
        </section>
      )}
    </main>
  )
}
