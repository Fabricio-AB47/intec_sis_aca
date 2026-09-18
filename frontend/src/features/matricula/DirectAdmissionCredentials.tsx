import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, FileDown, RefreshCw, UserRoundPlus } from 'lucide-react'

import { downloadCredentialHistoryReport, downloadDirectAdmissionReceipt, fetchDirectAdmissionCredentials, provisionDirectAdmissionCredentials } from '../../lib/api'
import type { DirectAdmissionCredentialNames, DirectAdmissionCredentialState, DirectAdmissionRecord } from '../../types/app'
import { proposedCredentialNames } from './credentialNames'

export function CredentialNameFields({ names, disabled, onChange }: Readonly<{
  names: DirectAdmissionCredentialNames; disabled?: boolean; onChange: (names: DirectAdmissionCredentialNames) => void
}>) {
  return <div className="direct-admission-grid">{([
    ['primer_nombre', 'Primer nombre Office 365'], ['segundo_nombre', 'Segundo nombre Office 365'],
    ['primer_apellido', 'Primer apellido Office 365'], ['segundo_apellido', 'Segundo apellido Office 365'],
  ] as const).map(([key, label]) => <label key={key}><span>{label}{key.startsWith('primer_') ? ' *' : ''}</span><input value={names[key]} disabled={disabled} required={key.startsWith('primer_')} maxLength={70} onChange={(event) => onChange({ ...names, [key]: event.target.value })} /></label>)}</div>
}

function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'No se pudo completar el aprovisionamiento.' }

export function DirectAdmissionCredentials({ record, role, automatic, onAutomaticDone }: Readonly<{
  record: DirectAdmissionRecord; role: string; automatic: boolean; onAutomaticDone: () => void
}>) {
  const [state, setState] = useState<DirectAdmissionCredentialState | null>(null)
  const [names, setNames] = useState(record.credenciales || proposedCredentialNames(record.datos_credenciales?.nombres || '', record.datos_credenciales?.apellidos || ''))
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const operation = useRef(false)
  const autoStarted = useRef(false)

  useEffect(() => {
    mounted.current = true
    let cancelled = false
    if (role === 'ADMINISTRADOR') fetchDirectAdmissionCredentials(record.solicitud_id).then((data) => {
      if (cancelled) return
      setState(data)
      if (data.datos_persona) setNames(data.datos_persona)
      else if (data.datos_credenciales) setNames(proposedCredentialNames(data.datos_credenciales.nombres, data.datos_credenciales.apellidos))
    }).catch((requestError) => { if (!cancelled) setError(errorMessage(requestError)) }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; mounted.current = false }
  }, [record.solicitud_id, role])

  const provision = useCallback(async (person: DirectAdmissionCredentialNames) => {
    if (operation.current) return
    operation.current = true
    setBusy(true); setError('')
    try {
      const response = await provisionDirectAdmissionCredentials(record.solicitud_id, person)
      if (mounted.current) setState(response)
    } catch (requestError) { if (mounted.current) setError(errorMessage(requestError)) }
    finally {
      operation.current = false
      if (mounted.current) { setBusy(false); onAutomaticDone() }
    }
  }, [record.solicitud_id, onAutomaticDone])

  useEffect(() => {
    if (!automatic || loading || error || autoStarted.current || !record.credenciales) return
    autoStarted.current = true
    void provision(record.credenciales)
  }, [automatic, loading, error, record.credenciales, provision])

  async function refresh() {
    if (operation.current) return
    operation.current = true; setBusy(true); setError('')
    try { const response = await fetchDirectAdmissionCredentials(record.solicitud_id); if (mounted.current) setState(response) }
    catch (requestError) { if (mounted.current) setError(errorMessage(requestError)) }
    finally { operation.current = false; if (mounted.current) setBusy(false) }
  }

  async function download() {
    if (!state?.reporte_credencial_id || operation.current) return
    operation.current = true; setBusy(true); setError('')
    try {
      const blob = await downloadCredentialHistoryReport(state.reporte_credencial_id)
      const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = `credenciales_${record.identificacion}.xlsx`; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) { if (mounted.current) setError(errorMessage(requestError)) }
    finally { operation.current = false; if (mounted.current) setBusy(false) }
  }

  async function downloadReceipt() {
    if (operation.current) return
    operation.current = true; setBusy(true); setError('')
    try {
      const blob = await downloadDirectAdmissionReceipt(record.solicitud_id)
      const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = `comprobante_matricula_${record.identificacion}.pdf`; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (requestError) { if (mounted.current) setError(errorMessage(requestError)) }
    finally { operation.current = false; if (mounted.current) setBusy(false) }
  }

  if (role !== 'ADMINISTRADOR') return null
  return <section className="direct-admission-credentials" aria-label="Credenciales del estudiante">
    <div className="direct-admission-excel-toolbar"><h3>Office 365 y Moodle · {record.nombre_estudiante}</h3><button type="button" className="secondary-action" disabled={busy || loading} onClick={() => void refresh()}><RefreshCw size={16} />Consultar estado</button></div>
    {loading ? <p role="status">Consultando credenciales...</p> : <>
      <p role="status" className={`direct-admission-alert ${state?.estado_general === 'COMPLETO' ? 'direct-admission-alert--success' : ''}`}>{busy ? 'Procesando credenciales...' : state?.estado_general || 'PENDIENTE'}{state?.correo_institucional ? ` · ${state.correo_institucional}` : ''}</p>
      <dl className="direct-admission-credential-status"><div><dt>Office 365</dt><dd>{state?.estado_graph || '-'}</dd></div><div><dt>Licencia educativa</dt><dd>{state?.estado_licencia || '-'}</dd></div><div><dt>Moodle</dt><dd>{state?.estado_moodle || '-'}</dd></div><div><dt>CorreosEstudIntec</dt><dd>{state?.estado_correo_academico || 'PENDIENTE'}</dd></div></dl>
      <CredentialNameFields names={names} disabled={busy || state?.estado_general === 'COMPLETO'} onChange={setNames} />
      {state?.observacion ? <p className="direct-admission-alert">{state.observacion}</p> : null}
      {state?.errores?.length ? <ul className="direct-admission-excel-error">{state.errores.map((issue, index) => <li key={index}>{issue}</li>)}</ul> : null}
      <div className="direct-admission-excel-toolbar"><button type="button" className="primary-action" disabled={busy || !names.primer_nombre.trim() || !names.primer_apellido.trim()} onClick={() => void provision(names)}><UserRoundPlus size={16} />{busy ? 'Procesando...' : state?.estado_general === 'COMPLETO' ? 'Verificar cuentas' : 'Crear / verificar credenciales'}</button><div className="direct-admission-excel-buttons"><button type="button" className="secondary-action" disabled={busy} onClick={() => void downloadReceipt()}><FileDown size={16} />Descargar comprobante PDF</button>{state?.reporte_credencial_id ? <button type="button" className="secondary-action" disabled={busy} onClick={() => void download()}><Download size={16} />Descargar credenciales</button> : null}</div></div>
    </>}
    {error ? <p role="alert" className="direct-admission-alert direct-admission-alert--error">{error}</p> : null}
  </section>
}
