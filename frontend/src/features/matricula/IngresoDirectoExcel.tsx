import { useEffect, useRef, useState } from 'react'
import { ClipboardCheck, Download, FileDown, FileText, Pause, Play, Save } from 'lucide-react'

import { analyzeDirectAdmissionExcel, downloadDirectAdmissionTemplate, downloadDirectAdmissionReceipts, saveDirectAdmission, provisionDirectAdmissionCredentials } from '../../lib/api'
import type { DirectAdmissionCredentialState, DirectAdmissionExcelResponse, DirectAdmissionPayload, DirectAdmissionRecord, DirectAdmissionSaveResponse } from '../../types/app'

type Props = {
  role: string
  career: string
  careerName: string
  periodName: string
  enrollment: DirectAdmissionPayload['matricula'] | null
  visible: boolean
  onBusy: (busy: boolean) => void
  onDocuments: (record: DirectAdmissionRecord) => void
}
type Result = { record?: DirectAdmissionSaveResponse; error?: string; credentials?: DirectAdmissionCredentialState; credentialError?: string }

function completed(result: Result | undefined, payload: DirectAdmissionPayload | null) {
  return Boolean(result?.record && (!payload?.credenciales || result.credentials?.estado_general === 'COMPLETO'))
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'No se pudo completar la operación.'
}

export function IngresoDirectoExcel({ role, career, careerName, periodName, enrollment, visible, onBusy, onDocuments }: Readonly<Props>) {
  const [file, setFile] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<{ signature: string; data: DirectAdmissionExcelResponse } | null>(null)
  const [selectedRows, setSelectedRows] = useState<number[]>([])
  const [results, setResults] = useState<Record<string, Result>>({})
  const [busy, setBusy] = useState<'download' | 'receipts' | 'analyze' | 'save' | null>(null)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [paused, setPaused] = useState(false)
  const [progress, setProgress] = useState({ processed: 0, total: 0 })
  const [createCredentials, setCreateCredentials] = useState(false)
  const busyRef = useRef(false)
  const pauseRequested = useRef(false)
  const mounted = useRef(true)
  const dialog = useRef<HTMLDialogElement>(null)
  const signature = JSON.stringify({ enrollment, createCredentials })
  const current = analysis?.signature === signature ? analysis.data : null
  const selectable = current?.items.filter((row) => row.payload && !completed(results[row.payload.solicitud_id], row.payload)) || []
  const chosen = selectable.filter((row) => selectedRows.includes(row.fila))
  const created = current?.items.filter((row) => row.payload && results[row.payload.solicitud_id]?.record).length || 0
  const failures = current?.items.filter((row) => row.payload && (results[row.payload.solicitud_id]?.error || results[row.payload.solicitud_id]?.credentialError || (results[row.payload.solicitud_id]?.credentials && results[row.payload.solicitud_id].credentials?.estado_general !== 'COMPLETO'))).length || 0
  const credentialCompleted = current?.items.filter((row) => row.payload && results[row.payload.solicitud_id]?.credentials?.estado_general === 'COMPLETO').length || 0

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; pauseRequested.current = true }
  }, [])

  useEffect(() => {
    if (!busy) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [busy])

  useEffect(() => {
    if (confirming) dialog.current?.showModal()
  }, [confirming])

  function start(operation: 'download' | 'receipts' | 'analyze' | 'save') {
    if (busyRef.current) return false
    busyRef.current = true
    setBusy(operation)
    setError('')
    onBusy(true)
    return true
  }

  function finish() {
    busyRef.current = false
    if (mounted.current) { setBusy(null); onBusy(false) }
  }

  async function download() {
    if (!career || !start('download')) return
    try {
      const blob = await downloadDirectAdmissionTemplate(career)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `ingreso_intec_carrera_${career}.xlsx`
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) {
      if (mounted.current) setError(errorMessage(requestError))
    } finally { finish() }
  }

  async function analyze() {
    if (!file || !enrollment || !start('analyze')) return
    setAnalysis(null)
    setSelectedRows([])
    setResults({})
    setPaused(false)
    setProgress({ processed: 0, total: 0 })
    try {
      const data = await analyzeDirectAdmissionExcel(file, enrollment, createCredentials)
      if (mounted.current) setAnalysis({ signature, data })
    } catch (requestError) {
      if (mounted.current) setError(errorMessage(requestError))
    } finally { finish() }
  }

  async function downloadReceipts() {
    const records = current?.items.flatMap((row) => {
      const record = row.payload ? results[row.payload.solicitud_id]?.record : undefined
      return record ? [record.solicitud_id] : []
    }) || []
    if (!records.length || !start('receipts')) return
    try {
      const blob = await downloadDirectAdmissionReceipts(records)
      const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = 'comprobantes_matricula.pdf'; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) { if (mounted.current) setError(errorMessage(requestError)) }
    finally { finish() }
  }

  async function save() {
    if (!chosen.length || !start('save')) return
    const rows = [...chosen]
    setConfirming(false)
    setPaused(false)
    setProgress({ processed: 0, total: rows.length })
    pauseRequested.current = false
    try {
      for (const row of rows) {
        if (pauseRequested.current || !mounted.current) break
        const payload = row.payload!
        try {
          let record = results[payload.solicitud_id]?.record
          if (!record) {
            record = await saveDirectAdmission(payload)
            if (mounted.current) setResults((previous) => ({ ...previous, [payload.solicitud_id]: { record } }))
          }
          if (payload.credenciales) {
            try {
              const credentials = await provisionDirectAdmissionCredentials(payload.solicitud_id, payload.credenciales)
              if (mounted.current) setResults((previous) => ({ ...previous, [payload.solicitud_id]: { record, credentials } }))
            } catch (requestError) {
              if (mounted.current) setResults((previous) => ({ ...previous, [payload.solicitud_id]: { record, credentialError: errorMessage(requestError) } }))
            }
          }
        } catch (requestError) {
          if (mounted.current) setResults((previous) => ({ ...previous, [payload.solicitud_id]: { error: errorMessage(requestError) } }))
        } finally {
          if (mounted.current) setProgress((previous) => ({ ...previous, processed: previous.processed + 1 }))
        }
      }
      if (mounted.current) setPaused(pauseRequested.current)
    } finally { finish() }
  }

  return <section hidden={!visible} className="direct-admission-excel" aria-label="Ingreso desde Excel">
    <div className="direct-admission-excel-toolbar">
      <div><h3>Plantilla Excel · {careerName || 'Carrera sin seleccionar'}</h3></div>
      <button type="button" className="secondary-action" disabled={!career || Boolean(busy)} onClick={() => void download()}><Download size={16} />{busy === 'download' ? 'Descargando...' : 'Descargar plantilla'}</button>
    </div>
    {role === 'ADMINISTRADOR' ? <label className="direct-admission-check"><input type="checkbox" disabled={Boolean(busy)} checked={createCredentials} onChange={(event) => setCreateCredentials(event.target.checked)} /><span>Crear / verificar Office 365 y Moodle por cada estudiante ingresado</span></label> : null}
    <div className="direct-admission-excel-toolbar">
      <label><span>Estudiantes (.xlsx)</span><input type="file" accept=".xlsx" disabled={Boolean(busy)} onChange={(event) => {
        const next = event.target.files?.[0] || null
        setAnalysis(null); setResults({}); setSelectedRows([]); setError(''); setPaused(false); setProgress({ processed: 0, total: 0 })
        if (next && (next.size > 12 * 1024 * 1024 || !next.name.toLowerCase().endsWith('.xlsx'))) {
          setFile(null); setError('Seleccione un archivo .xlsx de hasta 12 MB.'); event.target.value = ''; return
        }
        setFile(next)
      }} /></label>
      <button type="button" className="secondary-action" disabled={!file || !enrollment || Boolean(busy)} onClick={() => void analyze()}><ClipboardCheck size={16} />{busy === 'analyze' ? 'Validando archivo...' : 'Validar Excel'}</button>
    </div>
    {error ? <p className="direct-admission-alert direct-admission-alert--error" role="alert">{error}</p> : null}
    {current ? <>
      <div className="direct-admission-excel-summary" role="status"><strong>{current.total} estudiante(s)</strong><span>{current.validos} válido(s)</span><span>{current.invalidos} con errores</span><span>{created} registrado(s)</span><span>{failures} proceso(s) con novedades</span>{createCredentials ? <span>{credentialCompleted} credencial(es) completa(s)</span> : null}</div>
      {progress.total ? <div className="direct-admission-excel-progress" role="status"><span>{busy === 'save' ? 'Procesando' : paused ? 'Proceso pausado' : 'Proceso finalizado'} · {progress.processed} de {progress.total}</span><progress aria-label="Avance del ingreso desde Excel" value={progress.processed} max={progress.total} /></div> : null}
      <div className="direct-admission-excel-toolbar">
        <span>{chosen.length} estudiante(s) seleccionado(s)</span>
        <div className="direct-admission-excel-buttons">
          {role === 'ADMINISTRADOR' ? <button type="button" className="secondary-action" disabled={Boolean(busy) || !created} onClick={() => void downloadReceipts()}><FileDown size={16} />{busy === 'receipts' ? 'Generando PDF...' : 'Descargar comprobantes PDF'}</button> : null}
          <button type="button" className="secondary-action" disabled={Boolean(busy) || !selectable.length} onClick={() => setSelectedRows(selectable.map((row) => row.fila))}>Seleccionar válidos</button>
          <button type="button" className="secondary-action" disabled={Boolean(busy) || !selectedRows.length} onClick={() => setSelectedRows([])}>Limpiar selección</button>
        </div>
      </div>
      <div className="direct-admission-table-wrap"><table><thead><tr><th>Seleccionar</th><th>Fila</th><th>Estudiante</th><th>Estado / observaciones</th>{createCredentials ? <th>Office 365 / Moodle</th> : null}<th>Documentación</th></tr></thead><tbody>
        {current.items.map((row) => {
          const result = row.payload ? results[row.payload.solicitud_id] : undefined
          return <tr key={row.fila}>
            <td><input type="checkbox" aria-label={`Ingresar fila ${row.fila}`} checked={Boolean(!completed(result, row.payload) && selectedRows.includes(row.fila))} disabled={!row.payload || completed(result, row.payload) || Boolean(busy)} onChange={(event) => setSelectedRows((previous) => event.target.checked ? [...previous, row.fila] : previous.filter((value) => value !== row.fila))} /></td>
            <td>{row.fila}</td><td><strong>{row.nombre_estudiante}</strong><small>{row.identificacion}</small>{row.correo ? <small>{row.correo}</small> : null}{row.estudiante_existente != null ? <small>{row.estudiante_existente ? `Estudiante existente · Código ${row.codigo_estud_existente}` : 'Nuevo estudiante'}</small> : null}{row.payload?.credenciales ? <small>Office 365: {row.payload.credenciales.primer_nombre} / {row.payload.credenciales.primer_apellido}</small> : null}</td>
            <td>{result?.record ? <span className="direct-admission-excel-ok">{result.record.estudiante_existente ? 'Existente verificado' : 'Registrado'} · Código {result.record.codigo_estud}</span> : result?.error ? <span className="direct-admission-excel-error">{result.error}</span> : row.errores.length ? <ul>{row.errores.map((issue, index) => <li key={index}>{issue}</li>)}</ul> : 'Válido, pendiente de ingreso'}</td>
            {createCredentials ? <td>{result?.credentialError ? <span className="direct-admission-excel-error">{result.credentialError}</span> : result?.credentials ? <><strong>{result.credentials.estado_general}</strong><small>{result.credentials.correo_institucional}</small><small>Office 365: {result.credentials.estado_graph} · Licencia: {result.credentials.estado_licencia} · Moodle: {result.credentials.estado_moodle}</small>{result.credentials.errores?.map((issue, index) => <small className="direct-admission-excel-error" key={index}>{issue}</small>)}</> : 'Pendiente'}</td> : null}
            <td>{result?.record ? <button type="button" className="secondary-action" disabled={Boolean(busy)} onClick={() => onDocuments(result.record!)}><FileText size={16} />Documentos</button> : '-'}</td>
          </tr>
        })}
      </tbody></table></div>
      <footer className="direct-admission-actions">
        {busy === 'save' ? <button type="button" className="secondary-action" onClick={() => { pauseRequested.current = true; setPaused(true) }} disabled={paused}><Pause size={16} />{paused ? 'Pausa solicitada...' : 'Pausar después del estudiante actual'}</button> : <button type="button" className="primary-action" disabled={!chosen.length || Boolean(busy)} onClick={() => setConfirming(true)}>{paused ? <Play size={16} /> : <Save size={16} />}{paused ? 'Continuar seleccionados' : failures ? 'Reintentar seleccionados' : 'Ingresar seleccionados'}</button>}
      </footer>
    </> : null}
    {confirming ? <dialog ref={dialog} className="direct-admission-overlay" aria-labelledby="direct-admission-excel-confirm" onCancel={(event) => { event.preventDefault(); setConfirming(false) }}>
      <section className="direct-admission-modal"><header><h3 id="direct-admission-excel-confirm">Confirmar ingreso desde Excel</h3></header><div className="direct-admission-modal-body">
        <strong>{chosen.length} estudiante(s) · {careerName}</strong><p>{periodName}</p><p>Nivel {enrollment?.nivel} · Paralelo {enrollment?.paralelo} · {enrollment?.materia_codes.length} materia(s) por estudiante</p>
        {createCredentials ? <p>Incluye creación o verificación de cuentas Office 365, licencia educativa y usuario Moodle.</p> : null}
        <ul>{chosen.map((row) => <li key={row.fila}>{row.nombre_estudiante}<small>{row.identificacion} · Fila {row.fila}</small></li>)}</ul>
      </div><footer><button type="button" className="secondary-action" onClick={() => setConfirming(false)}>Volver</button><button type="button" className="primary-action" onClick={() => void save()}><Save size={16} />Confirmar ingresos</button></footer></section>
    </dialog> : null}
  </section>
}
