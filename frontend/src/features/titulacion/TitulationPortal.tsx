import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, Plus, Save, X } from 'lucide-react'
import { titulationPortalRequest as request } from '../../lib/api'
import type { GrupoTitulacion, ResponsableTitulacion } from './portalTypes'
import './TitulationPortal.css'

type Row = Record<string, unknown>
type Tab = 'dashboard' | 'aptos' | 'habilitaciones' | 'grupos' | 'complexivo' | 'defensa' | 'responsables' | 'calificaciones' | 'documentos' | 'titulos' | 'actas' | 'reportes'
type Field = { key: string; label: string; type?: 'number' | 'date' | 'time' | 'email' | 'checkbox' | 'file' | 'textarea'; required?: boolean; options?: [string, string][]; max?: number; min?: number; step?: string }
type Values = Record<string, string | boolean | File>
type Command = { title: string; fields: Field[]; initial?: Row; method?: string; path: string | ((values: Row) => string); multipart?: boolean; transform?: (values: Row) => Row | string; afterSave?: () => void }
const TABS: [Tab, string][] = [['dashboard', 'Resumen'], ['aptos', 'Estudiantes aptos'], ['habilitaciones', 'Habilitaciones'], ['grupos', 'Grupos'], ['complexivo', 'Complexivo'], ['defensa', 'Defensa'], ['responsables', 'Responsables'], ['calificaciones', 'Calificaciones'], ['documentos', 'Documentos'], ['titulos', 'Títulos'], ['actas', 'Actas'], ['reportes', 'Reportes']]
const field = (key: string, label: string, type?: Field['type'], required = false): Field => ({ key, label, type, required })
const mechanism: Field = { key: 'mecanismoCodigo', label: 'Mecanismo', required: true, options: [['EXAMEN_COMPLEXIVO', 'Examen complexivo'], ['DEFENSA_GRADO', 'Defensa de grado']] }
const modality: Field = { key: 'modalidad', label: 'Modalidad', options: [['PRESENCIAL', 'Presencial'], ['VIRTUAL', 'Virtual'], ['HIBRIDA', 'Híbrida']] }
const schedule = [field('fechaProgramada', 'Fecha programada', 'date'), field('horaInicio', 'Hora de inicio', 'time'), field('horaFin', 'Hora de fin', 'time'), modality, field('aulaOLink', 'Aula o enlace')]
const groupFields = [field('codigoGrupo', 'Código del grupo', undefined, true), field('tema', 'Tema', undefined, true), field('carrera', 'Carrera'), field('codigoCarrera', 'Código de carrera'), ...schedule]
const observation = field('observacion', 'Observación', 'textarea')
const fileFields = [field('archivo', 'Archivo', 'file'), field('rutaNubeManual', 'Ruta en la nube'), field('esFirmadoElectronicamente', 'Firmado electrónicamente', 'checkbox'), observation]
const docTypes = ['APTITUD_LEGAL', 'PROGRAMACION_EXAMEN', 'EVIDENCIA_EXAMEN_COMPLEXIVO', 'RUBRICA_EVALUADORES', 'RUBRICA_TRABAJO_ESCRITO', 'RUBRICA_DEFENSA_ORAL', 'TRABAJO_FINAL_GRADO', 'ACTA_DEFENSA', 'ACTA_GRADO', 'ACTA_GRADO_FIRMADA', 'CERTIFICADO_PRACTICAS', 'CERTIFICADO_VINCULACION']
const display = (value: unknown): string => value == null || value === '' ? '-' : typeof value === 'boolean' ? value ? 'Sí' : 'No' : Array.isArray(value) ? value.map(display).join(', ') : typeof value === 'object' ? Object.entries(value).map(([k, v]) => `${label(k)}: ${display(v)}`).join('; ') : String(value)
const label = (key: string) => key.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ').replace(/^./, char => char.toUpperCase())
const asRows = (data: unknown): Row[] => Array.isArray(data) ? data as Row[] : data && typeof data === 'object' && Array.isArray((data as Row).items) ? (data as { items: Row[] }).items : []
const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la operación.'
const sameIds = (values: unknown[]) => { const ids = values.filter(value => value != null && value !== ''); if (new Set(ids).size !== ids.length) throw new Error('No se pueden repetir responsables o evaluadores.'); return ids }

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function documentUrl(row: Row): string | null {
  const value = row.urlPublica || row.rutaNube
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null
  } catch { return null }
}

function DataTable({ rows, columns, actions }: { rows: Row[]; columns?: string[]; actions?: (row: Row) => React.ReactNode }) {
  const keys = columns || [...new Set(rows.flatMap(row => Object.keys(row)))]
  return <div className="titulation-portal__table"><table><thead><tr>{keys.map(key => <th key={key}>{label(key)}</th>)}{actions && <th>Acciones</th>}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{keys.map(key => <td key={key}>{key === 'nombreArchivo' && documentUrl(row) ? <a href={documentUrl(row)!} target="_blank" rel="noopener noreferrer">{display(row[key])}</a> : display(row[key])}</td>)}{actions && <td><div className="titulation-portal__actions">{actions(row)}</div></td>}</tr>)}</tbody></table>{!rows.length && <p>No existen registros para esta consulta.</p>}</div>
}

function CommandDialog({ command, close, saved }: { command: Command; close: () => void; saved: (data: unknown) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [values, setValues] = useState<Values>(() => Object.fromEntries(command.fields.map(f => [f.key, f.type === 'checkbox' ? Boolean(command.initial?.[f.key]) : String(command.initial?.[f.key] ?? '')])))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  useEffect(() => { dialog.current?.showModal() }, [])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      let data: Row = { ...command.initial }
      for (const f of command.fields) {
        const value = values[f.key]
        data[f.key] = f.type === 'number' ? value === '' ? null : Number(value) : f.type === 'time' && value ? `${String(value).slice(0, 5)}:00` : value === '' ? null : value
      }
      const path = typeof command.path === 'function' ? command.path(data) : command.path
      const transformed = command.transform ? command.transform(data) : data
      let body: FormData | string
      if (command.multipart) {
        if (!data.archivo && !data.rutaNubeManual) throw new Error('Seleccione un archivo o indique una ruta en la nube.')
        if (data.archivo instanceof File && data.archivo.size > 30 * 1024 * 1024) throw new Error('El archivo no debe superar 30 MB.')
        const form = new FormData()
        data = transformed as Row
        for (const [key, value] of Object.entries(data)) if (value != null && value !== '') form.append(key, value instanceof File ? value : String(value))
        body = form
      } else body = JSON.stringify(transformed)
      const result = await request<unknown>(path, { method: command.method || 'POST', body, headers: command.multipart ? undefined : { 'Content-Type': 'application/json' } })
      command.afterSave?.()
      saved(result)
      close()
    } catch (error) { setError(message(error)) }
    finally { lock.current = false; setBusy(false) }
  }
  return <dialog ref={dialog} aria-label={command.title} className="titulation-portal__dialog" onCancel={event => { if (busy) event.preventDefault(); else close() }}>
    <form onSubmit={event => void submit(event)}><header><h2>{command.title}</h2><button type="button" aria-label="Cerrar" title="Cerrar" disabled={busy} onClick={close}><X size={18} /></button></header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <fieldset disabled={busy} className="titulation-portal__fields">{command.fields.map(f => <label key={f.key}><span>{f.label}</span>{f.options ? <select aria-label={f.label} required={f.required} value={String(values[f.key])} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))}><option value="">Seleccione</option>{f.options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select> : f.type === 'textarea' ? <textarea aria-label={f.label} required={f.required} value={String(values[f.key])} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))} /> : f.type === 'file' ? <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg" onChange={e => setValues(v => ({ ...v, [f.key]: e.target.files?.[0] || '' }))} /> : f.type === 'checkbox' ? <input type="checkbox" checked={Boolean(values[f.key])} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.checked }))} /> : <input type={f.type || 'text'} required={f.required} min={f.min ?? (f.type === 'number' ? 1 : undefined)} max={f.max} step={f.step} value={String(values[f.key])} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))} />}</label>)}</fieldset>
      <footer><button className="secondary-action" type="button" disabled={busy} onClick={close}>Cancelar</button><button className="primary-action" type="submit" disabled={busy}><Save size={16} />{busy ? 'Guardando...' : 'Guardar'}</button></footer>
    </form>
  </dialog>
}

const groupColumns = ['codigoGrupo', 'tema', 'carrera', 'fechaProgramada', 'horaInicio', 'horaFin', 'modalidad', 'aulaOLink', 'totalIntegrantes', 'estadoCodigo']
const columns: Partial<Record<Tab, string[]>> = {
  aptos: ['cedula', 'nombres', 'carrera', 'periodo', 'cumpleTituloBachiller', 'cumpleInglesA2', 'cumplePracticas', 'cumpleVinculacion', 'cumpleMalla', 'noAdeudaFinanciero', 'puedeHabilitar', 'motivoNoApto'],
  habilitaciones: ['habilitacionId', 'expedienteId', 'numeroIdentificacion', 'carrera', 'codigoPeriodo', 'mecanismoCodigo', 'estadoCodigo', 'usuarioHabilitacion'],
  grupos: groupColumns, complexivo: groupColumns, defensa: groupColumns, calificaciones: groupColumns,
  responsables: ['responsableTitulacionId', 'nombres', 'cedula', 'correo', 'cargo', 'rolCodigo', 'activo'],
  documentos: ['documentoId', 'tipoDocumentoCodigo', 'nombreArchivo', 'version', 'estadoCodigo', 'fechaCarga', 'usuarioCarga', 'observacion'],
  titulos: ['expedienteId', 'numeroIdentificacion', 'nombresEstudiante', 'tipoDocumentoCodigo', 'nombreArchivo', 'codigoRegistroSenescyt', 'numeroTituloIntec', 'estadoCodigo'],
  actas: ['expedienteId', 'numeroActa', 'numeroIdentificacion', 'nombresEstudiante', 'carrera', 'fechaActa', 'notaFinalGrado', 'estadoCodigo'],
}

export function TitulationPortal() {
  const [status, setStatus] = useState<{ configured: boolean; roles: string[] } | null>(null)
  const [tab, setTab] = useState<Tab>('dashboard')
  const [data, setData] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('')
  const [academicDraft, setAcademicDraft] = useState({ carrera: '', periodo: '', estado: '' })
  const [academicFilter, setAcademicFilter] = useState({ carrera: '', periodo: '', estado: '' })
  const [page, setPage] = useState(1)
  const [command, setCommand] = useState<Command | null>(null)
  const [detail, setDetail] = useState<unknown>(null)
  const [responsibles, setResponsibles] = useState<ResponsableTitulacion[]>([])
  const [group, setGroup] = useState<GrupoTitulacion | null>(null)
  const actionLock = useRef(false)
  const roles = status?.roles || []
  const admin = roles.includes('ADMIN_TITULACION')
  const manage = admin || roles.includes('COORDINADOR_ACADEMICO')
  const documents = manage || roles.includes('SECRETARIA_TITULACION')
  const titles = admin || roles.includes('SECRETARIA_TITULACION')
  const grade = roles.includes('EVALUADOR_TITULACION')
  const actas = admin || roles.includes('AUTORIDAD_ACADEMICA')
  const refresh = useCallback(() => setRevision(value => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    request<{ configured: boolean; roles: string[] }>('status', { signal: controller.signal }).then(setStatus).catch(error => { if (!controller.signal.aborted) setError(message(error)) })
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    if (!status?.configured) return
    const controller = new AbortController()
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(academicFilter)) if (value.trim()) params.set(key, value.trim())
    let path = ''
    if (tab === 'dashboard') path = 'dashboard/resumen'
    else if (tab === 'aptos') { params.set('page', String(page)); params.set('pageSize', '25'); if (filter) params.set(/^\d+$/.test(filter) ? 'cedula' : 'nombres', filter); path = `estudiantes-aptos?${params}` }
    else if (tab === 'complexivo' || tab === 'defensa') path = `grupos?mecanismo=${tab === 'complexivo' ? 'EXAMEN_COMPLEXIVO' : 'DEFENSA_GRADO'}`
    else if (tab === 'calificaciones') path = 'grupos'
    else if (tab === 'documentos') path = /^\d+$/.test(filter) ? `expedientes/${filter}/documentos` : ''
    else if (tab === 'titulos') path = `titulos?search=${encodeURIComponent(filter)}`
    else if (tab !== 'reportes') path = tab
    // Abort and discard late reads when changing students or sections.
    if (!path) return
    request<unknown>(path, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setData(value); setBusy(false) } }).catch(error => { if (!controller.signal.aborted) { setError(message(error)); setBusy(false) } })
    return () => controller.abort()
  }, [tab, filter, page, revision, status?.configured, academicFilter])

  useEffect(() => {
    if (!status?.configured || !manage) return
    const controller = new AbortController()
    request<ResponsableTitulacion[]>('responsables', { signal: controller.signal }).then(setResponsibles).catch(() => {})
    return () => controller.abort()
  }, [status?.configured, manage, revision])

  async function run(action: () => Promise<unknown>, success = '') {
    if (actionLock.current) return
    actionLock.current = true; setBusy(true); setError('')
    try { const result = await action(); if (success) { setNotice(success); refresh() } else setDetail(result) }
    catch (error) { setError(message(error)) }
    finally { actionLock.current = false; setBusy(false) }
  }
  function selectTab(next: Tab) { setTab(next); setData(null); setDetail(null); setGroup(null); setQuery(''); setFilter(''); setPage(1); setError(''); setNotice(''); setBusy(!['documentos', 'reportes'].includes(next)) }
  function chooseResponsible(key: string, title: string, required = true): Field {
    const options = responsibles.filter(r => r.activo).map(r => [String(r.responsableTitulacionId), `${r.nombres} (${r.rolCodigo})`] as [string, string])
    return { key, label: title, type: 'number', required, options: options.length ? options : undefined }
  }
  function createGroup(defense = false, teams = false) {
    const fields = [...groupFields]
    if (defense) fields.push(field('expedienteId1', 'Primer expediente', 'number', true), field('expedienteId2', 'Segundo expediente', 'number'))
    if (teams) fields.push(chooseResponsible('responsableComplexivoId', 'Responsable'), ...[1, 2, 3].map(n => chooseResponsible(`evaluador${n}`, `Evaluador ${n}`, false)), field('correosAsistentes', 'Correos de asistentes', 'textarea'), observation)
    setCommand({ title: defense ? 'Crear defensa' : teams ? 'Crear complexivo y reunión Teams' : 'Crear grupo complexivo', fields, initial: { modalidad: teams ? 'VIRTUAL' : 'PRESENCIAL' }, path: `grupos/${defense ? 'defensa-grado' : teams ? 'complexivo/teams' : 'complexivo'}`, transform: values => {
      if (values.horaInicio && values.horaFin && String(values.horaInicio) >= String(values.horaFin)) throw new Error('La hora final debe ser posterior a la inicial.')
      if (defense) sameIds([values.expedienteId1, values.expedienteId2])
      if (!teams) return values
      const { evaluador1, evaluador2, evaluador3, correosAsistentes, ...rest } = values
      const evaluadoresIds = sameIds([evaluador1, evaluador2, evaluador3])
      if (evaluadoresIds.length !== 0 && evaluadoresIds.length !== 3) throw new Error('Seleccione los tres evaluadores o deje todos pendientes.')
      const emails = [...new Set(String(correosAsistentes || '').split(/[;,\s]+/).filter(Boolean))]
      if (emails.some(email => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))) throw new Error('Revise los correos de asistentes.')
      return { ...rest, evaluadoresIds, correosAsistentes: emails }
    } })
  }
  function responsibleForm(row?: Row) {
    setCommand({ title: row ? 'Editar responsable' : 'Nuevo responsable', fields: [field('cedula', 'Cédula'), field('nombres', 'Nombres', undefined, true), field('correo', 'Correo', 'email'), field('cargo', 'Cargo'), field('rolCodigo', 'Código del rol', undefined, true)], initial: row, method: row ? 'PUT' : 'POST', path: row ? `responsables/${row.responsableTitulacionId}` : 'responsables' })
  }
  function uploadTitle(type: 'registro' | 'intec') {
    setCommand({ title: type === 'registro' ? 'Cargar título SENESCYT' : 'Cargar título INTEC', multipart: true, path: `titulos/${type}/upload`, initial: { tipoDocumentoCodigo: type === 'registro' ? 'TITULO_REGISTRO_SENESCYT' : 'TITULO_INTEC' }, fields: [field('expedienteId', 'Expediente', 'number', true), field('cedula', 'Cédula'), ...(type === 'registro' ? [field('codigoRegistroSenescyt', 'Código de registro', undefined, true), field('fechaRegistroSenescyt', 'Fecha de registro', 'date', true)] : [field('numeroTituloIntec', 'Número de título', undefined, true), field('fechaEmisionTitulo', 'Fecha de emisión', 'date', true)]), field('codigoVerificacionQr', 'Código QR'), ...fileFields] })
  }
  function uploadDocument(initial: Row = {}) {
    setCommand({ title: 'Cargar documento', multipart: true, path: 'documentos/upload', initial: { expedienteId: Number(filter) || undefined, tipoDocumentoCodigo: 'APTITUD_LEGAL', ...initial }, fields: [field('expedienteId', 'Expediente', 'number', true), { key: 'tipoDocumentoCodigo', label: 'Tipo de documento', required: true, options: docTypes.map(type => [type, label(type)]) }, ...fileFields], afterSave: () => { if (tab === 'documentos') refresh() } })
  }
  function generateActa() {
    setCommand({ title: 'Generar acta individual', path: values => `expedientes/${values.expedienteId}/acta/generar`, fields: [field('expedienteId', 'Expediente', 'number', true), field('numeroActa', 'Número de acta'), field('fechaActa', 'Fecha del acta', 'date', true), field('horaActa', 'Hora del acta', 'time'), field('ciudad', 'Ciudad', undefined, true), field('escuela', 'Escuela'), field('autoridadAcademica', 'Autoridad académica'), field('coordinadorAcademico', 'Coordinador académico'), field('docenteEvaluador', 'Docente evaluador'), field('nombreInstitucion', 'Institución')], initial: { ciudad: 'Quito', nombreInstitucion: 'Instituto Superior Tecnológico INTEC' } })
  }
  function assignGroup(row: GrupoTitulacion) {
    const defense = row.mecanismoCodigo === 'DEFENSA_GRADO'
    const keys = defense ? ['presidenteTribunalId', 'vocal1Id', 'vocal2Id'] : ['evaluador1', 'evaluador2', 'evaluador3']
    setCommand({ title: defense ? 'Asignar tribunal' : 'Asignar responsable y evaluadores', path: `grupos/${row.grupoTitulacionId}/${defense ? 'tribunal-defensa' : 'responsable-complexivo'}`, initial: { grupoTitulacionId: row.grupoTitulacionId }, fields: [...(defense ? [] : [chooseResponsible('responsableComplexivoId', 'Responsable complexivo')]), ...keys.map(key => chooseResponsible(key, label(key))), ...(defense ? [chooseResponsible('tutorId', 'Tutor', false)] : []), observation], transform: values => {
      sameIds(keys.map(key => values[key]))
      if (defense) return values
      const { evaluador1, evaluador2, evaluador3, ...rest } = values
      return { ...rest, evaluadoresIds: [evaluador1, evaluador2, evaluador3] }
    } })
  }
  function evaluateStudent(row: Row) {
    if (!group) return
    const defense = group.mecanismoCodigo === 'DEFENSA_GRADO'
    const scores = defense ? ['notaTrabajoEscrito', 'notaDefensaOral'] : ['notaExamenComplexivo', 'notaDefensaOral']
    setCommand({ title: `Calificar ${row.numeroIdentificacion}`, path: `expedientes/${row.expedienteId}/calificaciones/evaluador`, initial: { expedienteId: row.expedienteId, grupoTitulacionId: group.grupoTitulacionId, cerrarCalificacion: true }, fields: [chooseResponsible('responsableTitulacionId', 'Evaluador'), { ...field('evaluadorNumero', 'Número de evaluador', 'number', true), min: 1, max: 3 }, ...scores.map(key => ({ ...field(key, label(key), 'number', key !== 'notaDefensaOral' || defense), min: 0, max: 10, step: '0.01' })), field('cerrarCalificacion', 'Cerrar calificación', 'checkbox'), observation] })
  }
  const rows = asRows(data)
  function actions(row: Row) {
    if (tab === 'aptos') return manage && <button disabled={!row.puedeHabilitar} className="secondary-action" onClick={() => setCommand({ title: `Habilitar ${display(row.nombres)}`, path: 'habilitaciones', initial: { cedula: row.cedula, mecanismoCodigo: 'EXAMEN_COMPLEXIVO', modalidad: 'PRESENCIAL' }, fields: [mechanism, field('tema', 'Tema'), ...schedule, field('grupoTitulacionId', 'Grupo existente', 'number'), observation] })}>Habilitar</button>
    if (tab === 'habilitaciones') return manage && row.estadoCodigo !== 'ANULADO' && <button className="danger-button" onClick={() => setCommand({ title: `Anular habilitación ${row.habilitacionId}`, path: `habilitaciones/${row.habilitacionId}/anular`, method: 'PUT', fields: [] })}>Anular</button>
    if (['grupos', 'complexivo', 'defensa', 'calificaciones'].includes(tab)) return <>
      <button className="secondary-action" disabled={busy} onClick={() => void run(async () => { const result = await request<GrupoTitulacion>(`grupos/${row.grupoTitulacionId}`); setGroup(result); return null })}>Ver integrantes</button>
      {manage && <><button className="secondary-action" onClick={() => setCommand({ title: `Programar ${row.codigoGrupo}`, fields: schedule, initial: row, path: `grupos/${row.grupoTitulacionId}/programacion`, method: 'PUT' })}>Programar</button><button className="secondary-action" onClick={() => assignGroup(row as unknown as GrupoTitulacion)}>Asignar responsables</button></>}
    </>
    if (tab === 'responsables') return manage && <><button className="secondary-action" onClick={() => responsibleForm(row)}>Editar</button><button className="danger-button" disabled={!row.activo} onClick={() => setCommand({ title: `Inactivar ${row.nombres}`, path: `responsables/${row.responsableTitulacionId}`, method: 'DELETE', fields: [] })}>Inactivar</button></>
    if (tab === 'documentos') return documents && <><button className="secondary-action" onClick={() => setCommand({ title: `Validar ${row.nombreArchivo}`, path: `documentos/${row.documentoId}/validar`, method: 'PUT', fields: [] })}>Validar</button><button className="secondary-action" onClick={() => setCommand({ title: `Observar ${row.nombreArchivo}`, path: `documentos/${row.documentoId}/observar`, method: 'PUT', fields: [{ ...observation, required: true }], transform: value => String(value.observacion) })}>Observar</button><button className="secondary-action" disabled={busy} onClick={() => void run(() => request(`documentos/${row.documentoId}/historial`))}>Historial</button></>
    if (tab === 'actas') return <><button className="secondary-action" disabled={busy} onClick={() => void run(async () => { download(await request<Blob>(`actas/${row.actaGradoId}/pdf`, { responseType: 'blob' }), `acta-${row.actaGradoId}.pdf`); return null })}><Download size={16} />PDF</button>{documents && <button className="secondary-action" onClick={() => uploadDocument({ expedienteId: row.expedienteId, tipoDocumentoCodigo: 'ACTA_GRADO_FIRMADA', esFirmadoElectronicamente: true })}>Cargar firmada</button>}{actas && <button className="danger-button" disabled={row.activo === false} onClick={() => setCommand({ title: `Anular acta ${row.numeroActa}`, path: `actas/${row.actaGradoId}/anular`, method: 'PUT', fields: [field('motivo', 'Motivo de anulación', 'textarea', true)] })}>Anular</button>}</>
    return null
  }
  async function exportReport(kind: 'aptos' | 'grupos' | 'actas') {
    await run(async () => {
      const report: Row[] = []
      if (kind === 'aptos') {
        for (let current = 1; ; current++) {
          const result = await request<{ items: Row[]; total: number; pageSize: number }>(`estudiantes-aptos?page=${current}&pageSize=100`)
          report.push(...result.items)
          if (report.length >= result.total || !result.items.length) break
        }
      } else report.push(...await request<Row[]>(kind))
      const keys = [...new Set(report.flatMap(row => Object.keys(row)))]
      const cell = (value: unknown) => { let text = display(value); if (/^[\s]*[=+@-]/.test(text)) text = `'${text}`; return `"${text.replace(/"/g, '""')}"` }
      download(new Blob(['\uFEFF', [keys.map(cell).join(','), ...report.map(row => keys.map(key => cell(row[key])).join(','))].join('\r\n')], { type: 'text/csv;charset=utf-8' }), `titulacion-${kind}.csv`)
      return null
    })
  }
  return <section className="titulation-portal" aria-label="Gestión integral de titulación">
    <header className="titulation-portal__head"><h1>Gestión integral de titulación</h1><button className="secondary-action" disabled={busy} onClick={() => { setError(''); refresh() }}><RefreshCw size={16} />Actualizar</button></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!status && !error && <p role="status">Conectando con titulación...</p>}
    {status && !status.configured && <p role="status" className="form-error">El servicio de titulación necesita configurar su conexión en el servidor. Los expedientes individuales continúan disponibles.</p>}
    {status?.configured && <>
      <div className="titulation-portal__tabs" role="tablist" aria-label="Secciones de titulación">{TABS.map(([key, text]) => <button key={key} role="tab" aria-selected={tab === key} disabled={actionLock.current} onClick={() => selectTab(key)}>{text}</button>)}</div>
      {notice && <p className="form-success" role="status">{notice}</p>}
      <div className="titulation-portal__toolbar">
        {['aptos', 'titulos', 'documentos'].includes(tab) && <form onSubmit={event => { event.preventDefault(); setData(null); setError(''); setPage(1); setFilter(query.trim()); setAcademicFilter(academicDraft); setBusy(true); refresh() }}><label><span>{tab === 'documentos' ? 'Número de expediente' : 'Buscar por nombre o cédula'}</span><input type={tab === 'documentos' ? 'number' : 'search'} min={1} required={tab === 'documentos'} value={query} onChange={event => setQuery(event.target.value)} /></label>{tab === 'aptos' && (['carrera', 'periodo', 'estado'] as const).map(key => <label key={key}><span>{key === 'periodo' ? 'Período' : label(key)}</span><input value={academicDraft[key]} onChange={event => setAcademicDraft(value => ({ ...value, [key]: event.target.value }))} /></label>)}<button className="secondary-action" disabled={busy}>Buscar</button></form>}
        {tab === 'aptos' && manage && <button className="secondary-action" disabled={busy} onClick={() => setCommand({ title: 'Sincronizar requisitos', fields: [], path: 'estudiantes-aptos/sincronizar' })}><RefreshCw size={16} />Sincronizar</button>}
        {['grupos', 'complexivo', 'defensa'].includes(tab) && manage && <button className="primary-action" onClick={() => createGroup(tab === 'defensa')}><Plus size={16} />Nuevo grupo</button>}
        {tab === 'complexivo' && manage && <button className="secondary-action" onClick={() => createGroup(false, true)}><Plus size={16} />Crear con Teams</button>}
        {tab === 'responsables' && manage && <button className="primary-action" onClick={() => responsibleForm()}><Plus size={16} />Nuevo responsable</button>}
        {tab === 'documentos' && documents && <button className="primary-action" onClick={() => uploadDocument()}><Plus size={16} />Cargar documento</button>}
        {tab === 'titulos' && titles && <><button className="primary-action" onClick={() => uploadTitle('registro')}><Plus size={16} />Título SENESCYT</button><button className="secondary-action" onClick={() => uploadTitle('intec')}><Plus size={16} />Título INTEC</button></>}
        {tab === 'actas' && actas && <button className="primary-action" onClick={generateActa}><Plus size={16} />Generar acta</button>}
      </div>
      {busy && <p role="status">Consultando...</p>}
      {tab === 'dashboard' && data != null && <dl className="titulation-portal__summary">{Object.entries(data as Row).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{display(value)}</dd></div>)}</dl>}
      {tab === 'reportes' && <div className="titulation-portal__actions">{(['aptos', 'grupos', 'actas'] as const).map(kind => <button key={kind} className="secondary-action" disabled={busy} onClick={() => void exportReport(kind)}><Download size={16} />{`Exportar ${kind} CSV`}</button>)}</div>}
      {!['dashboard', 'reportes'].includes(tab) && data != null && <DataTable rows={rows} columns={columns[tab]} actions={actions} />}
      {tab === 'aptos' && data != null && <div className="titulation-portal__actions"><button className="secondary-action" disabled={page === 1 || busy} onClick={() => { setData(null); setBusy(true); setPage(value => value - 1) }}>Anterior</button><span>Página {page} · {display((data as Row).total)} registros</span><button className="secondary-action" disabled={page * 25 >= Number((data as Row).total) || busy} onClick={() => { setData(null); setBusy(true); setPage(value => value + 1) }}>Siguiente</button></div>}
      {group && <section className="titulation-portal__group"><header><h2>{group.codigoGrupo} · Integrantes</h2><button className="secondary-action" disabled={busy} onClick={() => setGroup(null)}>Cerrar detalle</button></header>{manage && <button className="secondary-action" onClick={() => setCommand({ title: 'Agregar estudiante al grupo', fields: [field('cedula', 'Cédula', undefined, true), field('expedienteId', 'Expediente', 'number')], path: `grupos/${group.grupoTitulacionId}/estudiantes`, afterSave: () => setGroup(null) })}><Plus size={16} />Agregar estudiante</button>}
        <DataTable rows={(group.estudiantes || []) as unknown as Row[]} columns={['numeroIdentificacion', 'expedienteId', 'estadoCodigo']} actions={row => <>
          <button className="secondary-action" disabled={busy} onClick={() => void run(() => request(`expedientes/${row.expedienteId}/calificaciones`))}>Ver notas</button>
          <button className="secondary-action" disabled={busy} onClick={() => void run(() => request(`expedientes/${row.expedienteId}/calificaciones/consolidado`))}>Ver consolidado</button>
          {grade && <button className="secondary-action" onClick={() => evaluateStudent(row)}>Calificar</button>}
          {manage && <><button className="secondary-action" onClick={() => setCommand({ title: 'Consolidar calificaciones', fields: [], path: `expedientes/${row.expedienteId}/calificaciones/consolidar?grupoId=${group.grupoTitulacionId}` })}>Consolidar</button><button className="danger-button" onClick={() => setCommand({ title: `Retirar ${row.numeroIdentificacion} del grupo`, fields: [], path: `grupos/${group.grupoTitulacionId}/estudiantes/${encodeURIComponent(String(row.numeroIdentificacion))}`, method: 'DELETE', afterSave: () => setGroup(null) })}>Retirar</button></>}
        </>} />
        <h3>Responsables asignados</h3><DataTable rows={(group.responsables || []) as unknown as Row[]} columns={['nombres', 'rolCodigo', 'orden', 'esTribunal']} />
      </section>}
      {detail != null && <section className="titulation-portal__detail"><header><h2>Detalle del resultado</h2><button className="secondary-action" onClick={() => setDetail(null)}>Cerrar detalle</button></header>{Array.isArray(detail) ? <DataTable rows={asRows(detail)} /> : <dl>{Object.entries(detail as Row).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{display(value)}</dd></div>)}</dl>}</section>}
    </>}
    {command && <CommandDialog command={command} close={() => setCommand(null)} saved={result => { setNotice('Operación completada correctamente.'); setDetail(result); refresh() }} />}
  </section>
}
