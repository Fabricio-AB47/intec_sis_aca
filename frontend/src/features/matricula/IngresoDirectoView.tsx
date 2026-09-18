import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ClipboardCheck, FileText, Plus, RefreshCw, Save, X } from 'lucide-react'

import {
  fetchDirectAdmissionCatalog, fetchDirectAdmissionHistory, fetchDirectAdmissionPensum,
  previewDirectAdmission, saveDirectAdmission,
} from '../../lib/api'
import type {
  AcademicEnrollmentPreviewResponse, AcademicEnrollmentSubject, DirectAdmissionCatalog,
  DirectAdmissionPayload, DirectAdmissionRecord, DirectAdmissionStudent,
  DirectAdmissionCredentialNames,
} from '../../types/app'
import { ExpedientesDocumentalesView } from '../expedientes/ExpedientesDocumentalesView'
import { IngresoDirectoExcel } from './IngresoDirectoExcel'
import { CredentialNameFields, DirectAdmissionCredentials } from './DirectAdmissionCredentials'
import { proposedCredentialNames } from './credentialNames'
import './IngresoDirectoView.css'

type StudentForm = Record<keyof DirectAdmissionStudent, string>
type View = 'ingreso' | 'excel' | 'historial' | 'documentos'
const DOCUMENT_MODULES = ['SECRETARIA', 'FACTURACION']
const initialStudent: StudentForm = {
  identificacion: '', tipo_documento: '1', nombres: '', apellidos: '', correo: '', correo_intec: '',
  telefono: '', movil: '', fecha_nacimiento: '', sexo: '', estado_civil: '', etnia: '',
  pais_nacionalidad: '', provincia_nacimiento: '', canton_nacimiento: '', pais_residencia: '',
  provincia_residencia: '', canton_residencia: '', direccion: '', colegio: '', titulo_bachiller: '',
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudo completar la operación.'
}

export function IngresoDirectoView({ displayName, role }: Readonly<{ displayName: string; role: string }>) {
  const [view, setView] = useState<View>('ingreso')
  const [catalog, setCatalog] = useState<DirectAdmissionCatalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [student, setStudent] = useState<StudentForm>({ ...initialStudent })
  const [career, setCareer] = useState('')
  const [period, setPeriod] = useState('')
  const [level, setLevel] = useState('')
  const [journey, setJourney] = useState('')
  const [parallel, setParallel] = useState('A')
  const [group, setGroup] = useState('1')
  const [enrollmentType, setEnrollmentType] = useState<'R' | 'H' | 'E'>('R')
  const [amounts, setAmounts] = useState({ inscription: '0', enrollment: '0', total: '0', paymentDate: '' })
  const [pensum, setPensum] = useState<AcademicEnrollmentSubject[]>([])
  const [pensumLoading, setPensumLoading] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [exception, setException] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [confirmation, setConfirmation] = useState<{ payload: DirectAdmissionPayload; preview: AcademicEnrollmentPreviewResponse } | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [success, setSuccess] = useState('')
  const [currentStudent, setCurrentStudent] = useState<DirectAdmissionRecord | null>(null)
  const [history, setHistory] = useState<DirectAdmissionRecord[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')
  const [excelBusy, setExcelBusy] = useState(false)
  const [createCredentials, setCreateCredentials] = useState(false)
  const [credentialNamesOverride, setCredentialNamesOverride] = useState<DirectAdmissionCredentialNames | null>(null)
  const [automaticRequest, setAutomaticRequest] = useState<string | null>(null)
  const onAutomaticDone = useCallback(() => setAutomaticRequest(null), [])
  const requestId = useRef(crypto.randomUUID())
  const previewBusy = useRef(false)
  const saveBusy = useRef(false)
  const mounted = useRef(true)
  const closeButton = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    mounted.current = true
    let cancelled = false
    fetchDirectAdmissionCatalog().then((data) => {
      if (cancelled) return
      setCatalog(data)
      setJourney(data.jornadas?.[0]?.value || '')
    }).catch((requestError) => {
      if (!cancelled) setError(message(requestError))
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true; mounted.current = false }
  }, [])

  useEffect(() => {
    if (!career) return
    let cancelled = false
    fetchDirectAdmissionPensum(career).then((data) => {
      if (cancelled) return
      const subjects = data.items || []
      setPensum(subjects)
      const levels = subjects.map((subject) => Number(subject.semestre)).filter((value) => value >= 1)
      setLevel(levels.length ? String(Math.min(...levels)) : '')
    }).catch((requestError) => {
      if (!cancelled) setError(message(requestError))
    }).finally(() => {
      if (!cancelled) setPensumLoading(false)
    })
    return () => { cancelled = true }
  }, [career])

  useEffect(() => {
    if (!confirmation) return
    if (dialog.current && !dialog.current.open) dialog.current.showModal()
    closeButton.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [confirmation])

  const levels = useMemo(() => [...new Set(pensum.map((subject) => Number(subject.semestre)).filter((value) => value >= 1))].sort((a, b) => a - b), [pensum])
  const subjects = pensum.filter((subject) => Number(subject.semestre) === Number(level))
  const visibleHistory = history.filter((record) => `${record.nombre_estudiante} ${record.identificacion} ${record.carrera} ${record.periodo}`.toLocaleLowerCase('es-EC').includes(historyQuery.toLocaleLowerCase('es-EC')))
  const credentialNames = credentialNamesOverride || proposedCredentialNames(student.nombres, student.apellidos)

  function updateStudent(field: keyof StudentForm, value: string) {
    if (field === 'nombres' || field === 'apellidos') setCredentialNamesOverride(null)
    setStudent((previous) => {
      const next = { ...previous, [field]: value }
      if (field === 'pais_nacionalidad') { next.provincia_nacimiento = ''; next.canton_nacimiento = '' }
      if (field === 'provincia_nacimiento') next.canton_nacimiento = ''
      if (field === 'pais_residencia') { next.provincia_residencia = ''; next.canton_residencia = '' }
      if (field === 'provincia_residencia') next.canton_residencia = ''
      return next
    })
    setError('')
  }

  function input(field: keyof StudentForm, label: string, maxLength: number, required = false, type = 'text') {
    return <label><span>{label}{required ? ' *' : ''}</span><input
      value={student[field]} onChange={(event) => updateStudent(field, event.target.value)}
      type={type} maxLength={maxLength} required={required}
      max={type === 'date' ? new Date().toISOString().slice(0, 10) : undefined}
    /></label>
  }

  function select(field: keyof StudentForm, label: string, catalogKey: string, required = false, parent?: keyof StudentForm) {
    const options = (catalog?.datos_catalogos[catalogKey] || []).filter((option) => (
      (!parent || (student[parent] && Number(option.parent_value) === Number(student[parent])))
      && (field !== 'tipo_documento' || [1, 2, 3].includes(Number(option.value)))
    ))
    return <label><span>{label}{required ? ' *' : ''}</span><select value={student[field]}
      onChange={(event) => updateStudent(field, event.target.value)} required={required} disabled={Boolean(parent && !student[parent])}>
      <option value="">Seleccione</option>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select></label>
  }

  async function loadHistory() {
    if (historyLoading) return
    setHistoryLoading(true)
    setError('')
    try {
      const response = await fetchDirectAdmissionHistory()
      if (mounted.current) setHistory(response.items)
    } catch (requestError) {
      if (mounted.current) setError(message(requestError))
    } finally {
      if (mounted.current) setHistoryLoading(false)
    }
  }

  function enrollmentPayload(): DirectAdmissionPayload['matricula'] {
    return {
      cod_anio_basica: Number(career), codigo_periodo: Number(period), nivel: Number(level),
      materia_codes: [...selected], paralelo: parallel, num_grupo: Number(group), tipo_matricula: enrollmentType,
      cod_jornada: Number(journey), inscrip_valor: Number(amounts.inscription), matri_valor: Number(amounts.enrollment),
      valor: Number(amounts.total), fecha_pago: amounts.paymentDate || null,
      prerequisite_exception_codes: exception ? [...selected] : [],
      prerequisite_exception_reason: exception ? reason : null,
    }
  }

  async function previewAdmission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (view === 'excel') return
    if (previewBusy.current || saveBusy.current || confirmation) return
    if (selected.length === 0) { setError('Seleccione al menos una materia del nivel.'); return }
    const payload: DirectAdmissionPayload = {
      solicitud_id: requestId.current,
      estudiante: {
        ...student, tipo_documento: Number(student.tipo_documento), sexo: Number(student.sexo),
        estado_civil: Number(student.estado_civil), etnia: Number(student.etnia),
        provincia_residencia: student.provincia_residencia ? Number(student.provincia_residencia) : null,
        fecha_nacimiento: student.fecha_nacimiento || null,
      },
      matricula: enrollmentPayload(),
      ...(createCredentials ? { credenciales: credentialNames } : {}),
    }
    previewBusy.current = true
    setPreviewLoading(true)
    setError('')
    try {
      const preview = await previewDirectAdmission(payload)
      if (mounted.current && requestId.current === payload.solicitud_id) { setConfirmation({ payload, preview }); setSaveError('') }
    } catch (requestError) {
      if (mounted.current) setError(message(requestError))
    } finally {
      previewBusy.current = false
      if (mounted.current) setPreviewLoading(false)
    }
  }

  async function saveAdmission() {
    if (!confirmation || saveBusy.current) return
    saveBusy.current = true
    setSaving(true)
    setSaveError('')
    try {
      const response = await saveDirectAdmission(confirmation.payload)
      if (!mounted.current) return
      setCurrentStudent(response)
      setAutomaticRequest(response.credenciales ? response.solicitud_id : null)
      setSuccess(`${response.message} Código ${response.codigo_estud} · ${response.matricula.inserted || 0} materia(s) · Nivel ${response.nivel}.`)
      setConfirmation(null)
      setView('documentos')
    } catch (requestError) {
      if (mounted.current) setSaveError(message(requestError))
    } finally {
      saveBusy.current = false
      if (mounted.current) setSaving(false)
    }
  }

  function newAdmission() {
    requestId.current = crypto.randomUUID()
    setStudent({ ...initialStudent }); setCareer(''); setPeriod(''); setLevel(''); setPensum([])
    setPensumLoading(false); setSelected([]); setParallel('A'); setGroup('1'); setEnrollmentType('R')
    setException(false); setReason(''); setAmounts({ inscription: '0', enrollment: '0', total: '0', paymentDate: '' })
    setCurrentStudent(null); setSuccess(''); setError(''); setView('ingreso')
    setCreateCredentials(false); setCredentialNamesOverride(null); setAutomaticRequest(null)
  }

  const blocked = Number(confirmation?.preview.summary?.bloqueadas_por_prerrequisito || 0) > 0
  return (
    <section className="direct-admission">
      <div inert={Boolean(confirmation)}>
        <header className="direct-admission-header">
          <div><p className="eyebrow">Matrícula</p><h2>ingreso_intec</h2></div>
          <span>{displayName}</span>
        </header>
        <nav className="direct-admission-tabs" aria-label="Ingreso y documentación">
          <button type="button" disabled={excelBusy} aria-current={view === 'ingreso' ? 'page' : undefined} onClick={() => setView('ingreso')}>Datos y matrícula</button>
          <button type="button" disabled={excelBusy} aria-current={view === 'excel' ? 'page' : undefined} onClick={() => setView('excel')}>Ingreso desde Excel</button>
          <button type="button" disabled={excelBusy} aria-current={view === 'historial' ? 'page' : undefined} onClick={() => { setView('historial'); void loadHistory() }}>Ingresos registrados</button>
          <button type="button" aria-current={view === 'documentos' ? 'page' : undefined} disabled={!currentStudent || excelBusy} onClick={() => setView('documentos')}>Documentación</button>
          {currentStudent ? <button type="button" disabled={excelBusy} className="secondary-action direct-admission-new" onClick={newAdmission}><Plus size={16} />Nuevo ingreso</button> : null}
        </nav>
        {error ? <p className="direct-admission-alert direct-admission-alert--error" role="alert">{error}</p> : null}
        {success ? <p className="direct-admission-alert direct-admission-alert--success" role="status">{success}</p> : null}
        {loading ? <p role="status">Cargando catálogos...</p> : null}

        {(view === 'excel' || (view === 'ingreso' && !currentStudent)) && !loading ? (
          <form onSubmit={previewAdmission}>
            {view === 'ingreso' ? <><fieldset disabled={previewLoading || !catalog}>
              <legend>Datos del estudiante</legend>
              <div className="direct-admission-grid">
                {select('tipo_documento', 'Tipo de documento', 'tipodocumento', true)}
                {input('identificacion', 'Identificación', 10, true)}
                {input('apellidos', 'Apellidos', 70, true)}
                {input('nombres', 'Nombres', 70, true)}
                {input('correo', 'Correo personal', 80, true, 'email')}
                {input('correo_intec', 'Correo institucional', 100, false, 'email')}
                {input('telefono', 'Teléfono', 30, false, 'tel')}
                {input('movil', 'Celular', 15, false, 'tel')}
                {input('fecha_nacimiento', 'Fecha de nacimiento', 10, false, 'date')}
                {select('sexo', 'Sexo', 'Sexo', true)}
                {select('estado_civil', 'Estado civil', 'EstadoCivil', true)}
                {select('etnia', 'Etnia', 'Etnia', true)}
              </div>
            </fieldset>
            <fieldset disabled={previewLoading || !catalog}>
              <legend>Residencia y formación</legend>
              <div className="direct-admission-grid">
                {select('pais_nacionalidad', 'País de nacionalidad', 'paisNacionalidadId')}
                {select('provincia_nacimiento', 'Provincia de nacimiento', 'provinciaNacimeintoId', false, 'pais_nacionalidad')}
                {select('canton_nacimiento', 'Cantón de nacimiento', 'cantonNacimeintoId', false, 'provincia_nacimiento')}
                {select('pais_residencia', 'País de residencia', 'paisResidenciaId')}
                {select('provincia_residencia', 'Provincia de residencia', 'codprov', false, 'pais_residencia')}
                {select('canton_residencia', 'Cantón de residencia', 'Canton', false, 'provincia_residencia')}
                {input('direccion', 'Dirección', 150)}
                {input('colegio', 'Colegio', 100)}
                {input('titulo_bachiller', 'Título de bachiller', 100)}
              </div>
            </fieldset>
            {role === 'ADMINISTRADOR' ? <fieldset disabled={previewLoading}><legend>Credenciales institucionales</legend>
              <label className="direct-admission-check"><input type="checkbox" checked={createCredentials} onChange={(event) => setCreateCredentials(event.target.checked)} /><span>Crear / verificar Office 365 y Moodle después de matricular</span></label>
              {createCredentials ? <div className="direct-admission-credential-fields"><CredentialNameFields names={credentialNames} onChange={setCredentialNamesOverride} /></div> : null}
            </fieldset> : null}
            </> : null}
            <fieldset disabled={previewLoading || !catalog || excelBusy}>
              <legend>Matrícula académica</legend>
              <div className="direct-admission-grid">
                <label><span>Carrera *</span><select value={career} required onChange={(event) => {
                  setCareer(event.target.value); setPensum([]); setSelected([]); setLevel('')
                  setPensumLoading(Boolean(event.target.value)); setError(''); setException(false); setReason('')
                }}><option value="">Seleccione</option>{catalog?.carreras?.map((item) => <option key={item.cod_anio_basica} value={item.cod_anio_basica}>{item.nombre_basica}</option>)}</select></label>
                <label><span>Período *</span><select value={period} required onChange={(event) => {
                  setPeriod(event.target.value)
                  const type = catalog?.periodos?.find((item) => item.codigo_periodo === event.target.value)?.tipo_matricula
                  if (type === 'R' || type === 'H' || type === 'E') setEnrollmentType(type)
                }}><option value="">Seleccione</option>{catalog?.periodos?.map((item) => <option key={item.codigo_periodo} value={item.codigo_periodo}>{item.detalle_periodo}</option>)}</select></label>
                <label><span>Nivel *</span><select value={level} required disabled={pensumLoading || !levels.length} onChange={(event) => {
                  setLevel(event.target.value); setSelected([]); setException(false); setReason('')
                }}><option value="">Seleccione</option>{levels.map((item) => <option key={item} value={item}>Nivel {item}</option>)}</select></label>
                <label><span>Tipo de matrícula *</span><select value={enrollmentType} onChange={(event) => setEnrollmentType(event.target.value as 'R' | 'H' | 'E')}><option value="R">Regular</option><option value="H">Homologación</option><option value="E">Especial</option></select></label>
                <label><span>Jornada *</span><select value={journey} required onChange={(event) => setJourney(event.target.value)}><option value="">Seleccione</option>{catalog?.jornadas?.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                <label><span>Paralelo *</span><input value={parallel} required maxLength={4} onChange={(event) => setParallel(event.target.value.toUpperCase())} /></label>
                <label><span>Grupo *</span><input type="number" min="1" step="1" value={group} required onChange={(event) => setGroup(event.target.value)} /></label>
                <label><span>Fecha de pago</span><input type="date" value={amounts.paymentDate} onChange={(event) => setAmounts({ ...amounts, paymentDate: event.target.value })} /></label>
                {(['inscription', 'enrollment', 'total'] as const).map((key) => <label key={key}><span>{key === 'inscription' ? 'Inscripción ($)' : key === 'enrollment' ? 'Matrícula ($)' : 'Valor ($)'}</span><input type="number" min="0" step="0.01" required value={amounts[key]} onChange={(event) => setAmounts({ ...amounts, [key]: event.target.value })} /></label>)}
              </div>
              <div className="direct-admission-subject-header">
                <h3>Materias del nivel {level || '-'} <small>{selected.length} seleccionada(s)</small></h3>
                <button type="button" className="secondary-action" disabled={!subjects.length || pensumLoading} onClick={() => setSelected(subjects.map((item) => Number(item.codigo_materia)))}>Seleccionar nivel</button>
              </div>
              {pensumLoading ? <p role="status">Cargando pensum...</p> : (
                <div className="direct-admission-table-wrap"><table><thead><tr><th>Seleccionar</th><th>Código único</th><th>Materia</th><th>Nivel</th><th>Créditos</th></tr></thead><tbody>
                  {subjects.map((item) => <tr key={item.codigo_materia}><td><input type="checkbox" aria-label={`Matricular ${item.nombre_materia}`} checked={selected.includes(Number(item.codigo_materia))} onChange={(event) => {
                    const code = Number(item.codigo_materia)
                    setSelected((previous) => event.target.checked ? [...previous, code] : previous.filter((value) => value !== code))
                  }} /></td><td>{item.cod_materia || item.codigo_materia}</td><td>{item.nombre_materia}</td><td>{item.semestre}</td><td>{item.creditos}</td></tr>)}
                  {!subjects.length ? <tr><td colSpan={5}>{career ? 'No hay materias disponibles para este nivel.' : 'Seleccione una carrera.'}</td></tr> : null}
                </tbody></table></div>
              )}
              {Number(level) > 1 ? <div className="direct-admission-exception">
                <label className="direct-admission-check"><input type="checkbox" checked={exception} onChange={(event) => setException(event.target.checked)} /><span>Autorizar excepción de prerrequisitos</span></label>
                {exception ? <label><span>Justificación *</span><textarea value={reason} required minLength={10} maxLength={1000} onChange={(event) => setReason(event.target.value)} /></label> : null}
              </div> : null}
            </fieldset>
            {view === 'ingreso' ? <footer className="direct-admission-actions"><button type="submit" className="primary-action" disabled={previewLoading || pensumLoading || !selected.length || !catalog}><ClipboardCheck size={16} />{previewLoading ? 'Validando...' : 'Validar matrícula'}</button></footer> : null}
          </form>
        ) : view === 'ingreso' && currentStudent ? <p className="direct-admission-alert">{currentStudent.nombre_estudiante} · Código {currentStudent.codigo_estud} · Nivel {currentStudent.nivel}</p> : null}

        {!loading && catalog ? <IngresoDirectoExcel career={career} role={role}
          careerName={catalog.carreras?.find((item) => item.cod_anio_basica === career)?.nombre_basica || ''}
          periodName={catalog.periodos?.find((item) => item.codigo_periodo === period)?.detalle_periodo || ''}
          enrollment={career && period && level && journey && parallel && Number(group) >= 1 && selected.length && !pensumLoading && (!exception || reason.trim().length >= 10) ? enrollmentPayload() : null}
          visible={view === 'excel'} onBusy={setExcelBusy}
          onDocuments={(record) => { setCurrentStudent(record); setSuccess(''); setView('documentos') }}
        /> : null}

        {view === 'historial' ? <section className="direct-admission-history">
          <div className="direct-admission-history-toolbar"><label><span>Buscar ingreso</span><input value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Estudiante, identificación, carrera o período" /></label><button type="button" className="secondary-action" disabled={historyLoading} onClick={() => void loadHistory()}><RefreshCw size={16} />Actualizar</button></div>
          {historyLoading ? <p role="status">Consultando ingresos...</p> : <div className="direct-admission-table-wrap"><table><thead><tr><th>Estudiante</th><th>Carrera</th><th>Período</th><th>Nivel</th><th>Registrado por</th><th>Documentación</th></tr></thead><tbody>
            {visibleHistory.map((record) => <tr key={record.solicitud_id}><td><strong>{record.nombre_estudiante}</strong><small>{record.identificacion} · Código {record.codigo_estud}</small></td><td>{record.carrera}</td><td>{record.periodo}</td><td>{record.nivel}</td><td>{record.registrado_por}<small>{record.fecha_registro ? new Date(`${record.fecha_registro}Z`).toLocaleString('es-EC') : ''}</small></td><td><button type="button" className="secondary-action" onClick={() => { setCurrentStudent(record); setSuccess(''); setView('documentos') }}><FileText size={16} />Documentos</button></td></tr>)}
            {!visibleHistory.length ? <tr><td colSpan={6}>No existen ingresos registrados con este criterio.</td></tr> : null}
          </tbody></table></div>}
        </section> : null}
        {view === 'documentos' && currentStudent ? <><DirectAdmissionCredentials key={`credenciales-${currentStudent.solicitud_id}`} record={currentStudent} role={role}
          automatic={automaticRequest === currentStudent.solicitud_id} onAutomaticDone={onAutomaticDone} />
        <ExpedientesDocumentalesView
          key={currentStudent.codigo_estud} displayName={displayName} role={role}
          initialIdentification={currentStudent.identificacion} moduleFilter={DOCUMENT_MODULES}
          embedded embeddedTitle="Documentación del estudiante" embeddedDescription="" showStudentSearch={false}
        /></> : null}
      </div>

      {confirmation ? <dialog ref={dialog} className="direct-admission-overlay" aria-modal="true" aria-labelledby="direct-admission-confirm-title" onCancel={(event) => {
        event.preventDefault()
        if (!saveBusy.current) setConfirmation(null)
      }} onKeyDown={(event) => {
        if (event.key === 'Escape' && !saveBusy.current) setConfirmation(null)
        if (event.key === 'Tab') {
          const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
          const first = buttons[0]; const last = buttons[buttons.length - 1]
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
          if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
        }
      }}><section className="direct-admission-modal">
        <header><h3 id="direct-admission-confirm-title">Confirmar ingreso y matrícula</h3><button ref={closeButton} type="button" className="secondary-action" title="Cerrar" aria-label="Cerrar" disabled={saving} onClick={() => setConfirmation(null)}><X size={18} /></button></header>
        <div className="direct-admission-modal-body">
          <strong>{confirmation.payload.estudiante.apellidos} {confirmation.payload.estudiante.nombres}</strong>
          {confirmation.preview.estudiante ? <p className="direct-admission-alert">{confirmation.preview.estudiante.accion === 'EXISTENTE'
            ? `Estudiante existente · Código ${confirmation.preview.estudiante.codigo_estud}` : 'Nuevo estudiante'}</p> : null}
          <p>{confirmation.payload.estudiante.identificacion} · Nivel {confirmation.payload.matricula.nivel} · Paralelo {confirmation.payload.matricula.paralelo}</p>
          <p>{catalog?.carreras?.find((item) => Number(item.cod_anio_basica) === confirmation.payload.matricula.cod_anio_basica)?.nombre_basica}</p>
          <p>{catalog?.periodos?.find((item) => Number(item.codigo_periodo) === confirmation.payload.matricula.codigo_periodo)?.detalle_periodo}</p>
          <ul>{confirmation.preview.items?.map((item) => <li key={item.codigo_materia}><span>{item.nombre_materia}</span><small>{item.motivo || item.accion}</small></li>)}</ul>
          {confirmation.payload.credenciales ? <p>Office 365 y Moodle: {confirmation.payload.credenciales.primer_nombre} {confirmation.payload.credenciales.segundo_nombre} · {confirmation.payload.credenciales.primer_apellido} {confirmation.payload.credenciales.segundo_apellido}</p> : null}
          {blocked ? <p className="direct-admission-alert direct-admission-alert--error" role="alert">Hay prerrequisitos pendientes. Revise las materias o justifique una excepción.</p> : null}
          {saveError ? <p className="direct-admission-alert direct-admission-alert--error" role="alert">{saveError}</p> : null}
        </div>
        <footer><button type="button" className="secondary-action" disabled={saving} onClick={() => setConfirmation(null)}>Volver</button><button type="button" className="primary-action" disabled={saving || blocked} onClick={() => void saveAdmission()}><Save size={16} />{saving ? 'Guardando...' : 'Registrar y matricular'}</button></footer>
      </section></dialog> : null}
    </section>
  )
}
