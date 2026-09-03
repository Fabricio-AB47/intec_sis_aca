import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  analyzeCredentialProvisionWorkbook,
  downloadCredentialHistoryReport,
  downloadCredentialProvisionReport,
  downloadCredentialProvisionTemplate,
  fetchCredentialProvisionConfig,
  fetchCredentialProvisionHistory,
  provisionCredentials,
} from '../../lib/api'
import type {
  CredentialAnalysisResponse,
  CredentialHistoryRow,
  CredentialPersonType,
  CredentialProvisionConfig,
  CredentialProvisionPerson,
  CredentialProvisionResponse,
  CredentialProvisionResultRow,
} from '../../types/app'

type CredentialGeneratorViewProps = {
  displayName: string
}

type CredentialSection = 'bulk' | 'individual' | 'history'

const AUDIENCE_LABELS: Record<CredentialPersonType, { singular: string; plural: string; license: string }> = {
  ESTUDIANTE: { singular: 'estudiante', plural: 'estudiantes', license: 'estudiantil' },
  PROFESOR: { singular: 'profesor', plural: 'profesores', license: 'para profesores' },
}

const EMPTY_PERSON: CredentialProvisionPerson = {
  primer_nombre: '',
  segundo_nombre: '',
  primer_apellido: '',
  segundo_apellido: '',
  cedula: '',
}

function valueOrDash(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '-'
}

function normalizedToken(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}

function baseEmail(person: CredentialProvisionPerson, domain: string) {
  const firstName = normalizedToken(person.primer_nombre)
  const firstSurname = normalizedToken(person.primer_apellido)
  return firstName && firstSurname ? `${firstName}.${firstSurname}@${domain}` : '-'
}

function previewPassword(person: CredentialProvisionPerson, year: number) {
  const firstName = normalizedToken(person.primer_nombre)
  const firstSurname = normalizedToken(person.primer_apellido)
  const cedula = person.cedula.replace(/\D/g, '')
  if (!firstName || !firstSurname || cedula.length < 4) return '-'
  const surname = `${firstSurname.slice(0, 1).toUpperCase()}${firstSurname.slice(1)}`
  return `${firstName.slice(0, 1).toUpperCase()}${surname}${cedula.slice(-4)}@${year}`
}

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    ASIGNADA: 'Asignada',
    ASIGNADA_ESTUDIANTE: 'Asignada a estudiante',
    ASIGNADA_PROFESOR: 'Asignada a profesor',
    COMPLETO: 'Completo',
    COMPLETO_CON_ADVERTENCIA: 'Completo con advertencia',
    CONFLICTO_GRAPH: 'Conflicto Microsoft',
    CONFLICTO_MOODLE: 'Conflicto Moodle',
    CREADO_GRAPH: 'Creado',
    CREADO_MOODLE: 'Creado',
    ERROR: 'Error',
    ERROR_GRAPH: 'Error Microsoft',
    ERROR_LICENCIA: 'Error de licencia',
    ERROR_LICENCIA_ESTUDIANTE: 'Error licencia estudiante',
    ERROR_LICENCIA_PROFESOR: 'Error licencia profesor',
    ERROR_MOODLE: 'Error Moodle',
    ERROR_VALIDACION: 'Error de validación',
    EXISTENTE_GRAPH: 'Existente',
    EXISTENTE_MOODLE: 'Existente',
    EXISTENTE_OTRO_CORREO: 'Existe con otro correo',
    NO_CONFIGURADA: 'No configurada',
    NO_CONFIGURADO: 'No configurado',
    NO_PROCESADO: 'No procesado',
    OMITIDA: 'Omitida',
    PARCIAL: 'Parcial',
    SIN_CUPOS_ESTUDIANTE: 'Sin cupos de estudiante',
    SIN_CUPOS_PROFESOR: 'Sin cupos de profesor',
    VALIDO: 'Válido',
    YA_ASIGNADA: 'Ya asignada',
    YA_ASIGNADA_ESTUDIANTE: 'Ya asignada a estudiante',
    YA_ASIGNADA_PROFESOR: 'Ya asignada a profesor',
  }
  return labels[value] || value.replaceAll('_', ' ').toLowerCase()
}

function statusTone(value: string) {
  if (/ADVERTENCIA|PARCIAL|NO_CONFIGURAD|OMITIDA|OTRO_CORREO|SIN_CUPOS/.test(value)) return 'warning'
  if (/^(COMPLETO|CREADO_|EXISTENTE_(GRAPH|MOODLE)|ASIGNADA|YA_ASIGNADA|VALIDO)/.test(value)) return 'success'
  if (/ERROR|CONFLICTO|NO_PROCESADO/.test(value)) return 'danger'
  return 'neutral'
}

function rowDetail(row: CredentialProvisionResultRow) {
  return [row.error_graph, row.error_licencia, row.error_moodle, ...(row.errores || [])]
    .filter(Boolean)
    .join(' · ')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-EC')
}

export function CredentialGeneratorView({ displayName }: Readonly<CredentialGeneratorViewProps>) {
  const [personType, setPersonType] = useState<CredentialPersonType>('ESTUDIANTE')
  const [activeSection, setActiveSection] = useState<CredentialSection>('bulk')
  const [config, setConfig] = useState<CredentialProvisionConfig | null>(null)
  const [historyByType, setHistoryByType] = useState<Record<CredentialPersonType, CredentialHistoryRow[]>>({
    ESTUDIANTE: [],
    PROFESOR: [],
  })
  const [historyLoadedByType, setHistoryLoadedByType] = useState<Record<CredentialPersonType, boolean>>({
    ESTUDIANTE: false,
    PROFESOR: false,
  })
  const [historyLoadingType, setHistoryLoadingType] = useState<CredentialPersonType | null>(null)
  const [workbook, setWorkbook] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<CredentialAnalysisResponse | null>(null)
  const [person, setPerson] = useState<CredentialProvisionPerson>(EMPTY_PERSON)
  const [result, setResult] = useState<CredentialProvisionResponse | null>(null)
  const [showPasswords, setShowPasswords] = useState(false)
  const [reportDownloaded, setReportDownloaded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [historyDownloadingId, setHistoryDownloadingId] = useState<number | null>(null)
  const [showProcessInfo, setShowProcessInfo] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const configuration = await fetchCredentialProvisionConfig()
      setConfig(configuration)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el módulo de credenciales.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  const loadHistory = useCallback(async (type: CredentialPersonType, silent = false) => {
    if (!silent) setHistoryLoadingType(type)
    try {
      const response = await fetchCredentialProvisionHistory(100, type)
      setHistoryByType((current) => ({ ...current, [type]: response.rows || [] }))
      setHistoryLoadedByType((current) => ({ ...current, [type]: true }))
    } catch (apiError) {
      setHistoryLoadedByType((current) => ({ ...current, [type]: true }))
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el historial de credenciales.')
    } finally {
      if (!silent) setHistoryLoadingType(null)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    if (
      activeSection === 'history'
      && !historyLoadedByType[personType]
      && historyLoadingType !== personType
    ) {
      void loadHistory(personType)
    }
  }, [activeSection, historyLoadedByType, historyLoadingType, loadHistory, personType])

  useEffect(() => {
    if (!showProcessInfo) return

    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowProcessInfo(false)
    }
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [showProcessInfo])

  const validAnalysisRows = useMemo(
    () => analysis?.rows.filter((row) => row.estado === 'VALIDO') || [],
    [analysis],
  )

  const individualEmail = baseEmail(person, config?.domain || 'intec.edu.ec')
  const individualPassword = previewPassword(person, config?.year || new Date().getFullYear())
  const audience = AUDIENCE_LABELS[personType]
  const selectedLicense = config?.licenses?.[personType]
  const history = historyByType[personType]

  function selectPersonType(nextType: CredentialPersonType) {
    if (nextType === personType) return
    setPersonType(nextType)
    setActiveSection('bulk')
    setWorkbook(null)
    setAnalysis(null)
    setPerson(EMPTY_PERSON)
    setResult(null)
    setShowPasswords(false)
    setReportDownloaded(false)
    setError('')
    setMessage('')
  }

  function selectSection(section: CredentialSection) {
    setActiveSection(section)
    setError('')
    setMessage('')
  }

  function updatePerson(field: keyof CredentialProvisionPerson, value: string) {
    setPerson((current) => ({ ...current, [field]: field === 'cedula' ? value.replace(/\D/g, '').slice(0, 10) : value }))
    setError('')
  }

  async function downloadTemplate() {
    setDownloading(true)
    setError('')
    try {
      const blob = await downloadCredentialProvisionTemplate(personType)
      downloadBlob(blob, `plantilla_credenciales_${audience.plural}_microsoft_moodle.xlsx`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la plantilla.')
    } finally {
      setDownloading(false)
    }
  }

  async function analyzeWorkbook() {
    if (!workbook) {
      setError('Seleccione el archivo Excel que desea analizar.')
      return
    }
    setAnalyzing(true)
    setError('')
    setMessage('')
    setResult(null)
    try {
      const response = await analyzeCredentialProvisionWorkbook(workbook)
      setAnalysis(response)
      setMessage(`${response.summary.validos} de ${response.summary.total} fila(s) están listas para crear.`)
    } catch (apiError) {
      setAnalysis(null)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo analizar el archivo Excel.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function executeProvision(mode: 'INDIVIDUAL' | 'EXCEL', users: CredentialProvisionPerson[]) {
    if (!selectedLicense?.configured) {
      setError(selectedLicense?.detail || `La licencia Office 365 A1 ${audience.license} no está disponible.`)
      return
    }
    setProcessing(true)
    setError('')
    setMessage('')
    setResult(null)
    setReportDownloaded(false)
    setShowPasswords(false)
    try {
      const response = await provisionCredentials({ tipo_persona: personType, modo: mode, usuarios: users })
      setResult(response)
      setMessage(response.message)
      if (mode === 'INDIVIDUAL' && response.summary.fallidos === 0) setPerson(EMPTY_PERSON)
      await loadData(true)
      setHistoryLoadedByType((current) => ({ ...current, [personType]: false }))
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo completar la creación de credenciales.')
    } finally {
      setProcessing(false)
    }
  }

  function createFromExcel() {
    const users = validAnalysisRows.map((row) => ({
      primer_nombre: row.primer_nombre,
      segundo_nombre: row.segundo_nombre,
      primer_apellido: row.primer_apellido,
      segundo_apellido: row.segundo_apellido,
      cedula: row.cedula,
      fila_origen: row.fila_origen,
    }))
    if (!users.length) {
      setError('El archivo no contiene filas válidas para procesar.')
      return
    }
    void executeProvision('EXCEL', users)
  }

  function createIndividual() {
    if (!person.primer_nombre.trim() || !person.primer_apellido.trim() || !/^\d{10}$/.test(person.cedula)) {
      setError('Complete el primer nombre, primer apellido y una cédula de 10 dígitos.')
      return
    }
    void executeProvision('INDIVIDUAL', [{ ...person, fila_origen: 1 }])
  }

  async function downloadReport() {
    if (!result?.report_id || reportDownloaded) return
    setDownloading(true)
    setError('')
    try {
      const blob = await downloadCredentialProvisionReport(result.report_id)
      const suffix = result.rows.length === 1 ? result.rows[0].cedula : result.batch_id.slice(0, 8)
      downloadBlob(blob, `reporte_credenciales_${audience.plural}_${suffix}.xlsx`)
      setReportDownloaded(true)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el reporte.')
    } finally {
      setDownloading(false)
    }
  }

  async function downloadHistoryReport(row: CredentialHistoryRow) {
    if (!row.reporte_disponible || historyDownloadingId !== null) return
    setHistoryDownloadingId(row.id)
    setError('')
    setMessage('')
    try {
      const blob = await downloadCredentialHistoryReport(row.id)
      downloadBlob(blob, `credencial_${row.tipo_persona.toLowerCase()}_${row.cedula}.xlsx`)
      setMessage(`Documento histórico descargado para ${row.nombres}.`)
      await loadHistory(personType, true)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la credencial histórica.')
    } finally {
      setHistoryDownloadingId(null)
    }
  }

  return (
    <div className="credential-provision-page">
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Integraciones</p>
          <h1>Credenciales Microsoft 365 y Moodle</h1>
          <p className="credential-page-summary">Creación institucional con contraseña permanente para estudiantes y profesores.</p>
        </div>
        <div className="student-topbar__right">
          <button
            type="button"
            className="ghost-button credential-process-info-button"
            aria-haspopup="dialog"
            aria-expanded={showProcessInfo}
            onClick={() => setShowProcessInfo(true)}
          >
            Información del proceso
          </button>
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Acceso administrador</span>
            </div>
          </div>
        </div>
      </header>

      <nav className="credential-audience-tabs" role="tablist" aria-label="Tipo de usuario para crear credenciales">
        <button
          type="button"
          role="tab"
          aria-selected={personType === 'ESTUDIANTE'}
          className={personType === 'ESTUDIANTE' ? 'is-active' : ''}
          onClick={() => selectPersonType('ESTUDIANTE')}
          disabled={processing || analyzing}
        >
          <span>Estudiantes</span>
          <small>Office 365 A1 para estudiantes</small>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={personType === 'PROFESOR'}
          className={personType === 'PROFESOR' ? 'is-active' : ''}
          onClick={() => selectPersonType('PROFESOR')}
          disabled={processing || analyzing}
        >
          <span>Profesores</span>
          <small>Office 365 A1 para profesores</small>
        </button>
      </nav>

      <nav className="credential-mode-tabs" role="tablist" aria-label={`Opciones para ${audience.plural}`}>
        <button
          type="button"
          role="tab"
          aria-selected={activeSection === 'bulk'}
          className={activeSection === 'bulk' ? 'is-active' : ''}
          onClick={() => selectSection('bulk')}
        >
          Carga masiva
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeSection === 'individual'}
          className={activeSection === 'individual' ? 'is-active' : ''}
          onClick={() => selectSection('individual')}
        >
          Creación individual
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeSection === 'history'}
          className={activeSection === 'history' ? 'is-active' : ''}
          onClick={() => selectSection('history')}
        >
          Historial
        </button>
      </nav>

      {error ? <p className="form-error credential-page-message" role="alert">{error}</p> : null}
      {message ? <p className="form-success credential-page-message" role="status">{message}</p> : null}

      {activeSection === 'bulk' ? (
        <section className="student-card credential-workspace" role="tabpanel">
          <div className="card-head credential-workspace-head">
            <div>
              <p className="eyebrow">Excel</p>
              <h2>Carga masiva de {audience.plural}</h2>
            </div>
            <button type="button" className="ghost-button" onClick={() => void downloadTemplate()} disabled={downloading}>
              Descargar plantilla
            </button>
          </div>

          <div className="credential-upload-row">
            <label className="credential-file-control">
              <span>Archivo Excel</span>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => {
                  setWorkbook(event.target.files?.[0] || null)
                  setAnalysis(null)
                  setResult(null)
                  setError('')
                }}
              />
              <small>{workbook ? workbook.name : 'Ningún archivo seleccionado'}</small>
            </label>
            <button type="button" className="primary-action" onClick={() => void analyzeWorkbook()} disabled={!workbook || analyzing || processing}>
              {analyzing ? 'Analizando...' : 'Analizar archivo'}
            </button>
          </div>

          {analysis ? (
            <>
              <div className="credential-analysis-summary">
                <span><strong>{analysis.summary.total}</strong>Total</span>
                <span className="is-success"><strong>{analysis.summary.validos}</strong>Válidas</span>
                <span className={analysis.summary.errores ? 'is-danger' : ''}><strong>{analysis.summary.errores}</strong>Con errores</span>
                <button type="button" className="primary-action" onClick={createFromExcel} disabled={!validAnalysisRows.length || processing || !selectedLicense?.configured}>
                  {processing ? 'Procesando cuentas...' : `Crear ${validAnalysisRows.length} cuenta(s) con licencia ${audience.license}`}
                </button>
              </div>
              <div className="portal-table-wrap credential-provision-table-wrap credential-analysis-table-wrap">
                <table className="portal-record-table credential-provision-table credential-analysis-table" aria-label="Resultado de validación del archivo">
                  <thead>
                    <tr>
                      <th>Fila</th>
                      <th>Persona</th>
                      <th>Cédula</th>
                      <th>Correo propuesto</th>
                      <th>Validación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.rows.map((row) => (
                      <tr
                        key={`${row.fila_origen}-${row.cedula}`}
                        className={row.estado === 'VALIDO' ? 'is-valid' : 'has-errors'}
                      >
                        <td data-label="Fila">{row.fila_origen}</td>
                        <td data-label="Persona">
                          <strong>{[row.primer_nombre, row.segundo_nombre, row.primer_apellido, row.segundo_apellido].filter(Boolean).join(' ')}</strong>
                        </td>
                        <td data-label="Cédula">{valueOrDash(row.cedula)}</td>
                        <td data-label="Correo propuesto" className="credential-email-cell">{valueOrDash(row.correo_propuesto)}</td>
                        <td data-label="Validación">
                          <span className={`credential-status credential-status--${statusTone(row.estado)}`}>{statusLabel(row.estado)}</span>
                          {row.errores.length ? <small className="credential-row-error">{row.errores.join(' · ')}</small> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      {activeSection === 'individual' ? (
        <section className="student-card credential-workspace" role="tabpanel">
          <div className="card-head">
            <div>
              <p className="eyebrow">Registro único</p>
              <h2>Crear credencial de {audience.singular}</h2>
            </div>
          </div>
          <div className="credential-individual-layout">
            <div className="credential-individual-form">
              <label>
                <span>Primer nombre</span>
                <input value={person.primer_nombre} onChange={(event) => updatePerson('primer_nombre', event.target.value)} maxLength={120} />
              </label>
              <label>
                <span>Segundo nombre</span>
                <input value={person.segundo_nombre} onChange={(event) => updatePerson('segundo_nombre', event.target.value)} maxLength={120} />
              </label>
              <label>
                <span>Primer apellido</span>
                <input value={person.primer_apellido} onChange={(event) => updatePerson('primer_apellido', event.target.value)} maxLength={120} />
              </label>
              <label>
                <span>Segundo apellido</span>
                <input value={person.segundo_apellido} onChange={(event) => updatePerson('segundo_apellido', event.target.value)} maxLength={120} />
              </label>
              <label className="credential-field-full">
                <span>Cédula</span>
                <input value={person.cedula} onChange={(event) => updatePerson('cedula', event.target.value)} inputMode="numeric" maxLength={10} />
              </label>
            </div>
            <aside className="credential-preview" aria-label="Vista previa de la credencial">
              <p className="eyebrow">Vista previa</p>
              <dl>
                <div>
                  <dt>Correo base</dt>
                  <dd>{individualEmail}</dd>
                </div>
                <div>
                  <dt>Contraseña permanente</dt>
                  <dd>{individualPassword}</dd>
                </div>
                <div>
                  <dt>Duplicados</dt>
                  <dd>Inicial del segundo apellido y numeración consecutiva</dd>
                </div>
              </dl>
            </aside>
          </div>
          <div className="credential-actions">
            <button type="button" className="ghost-button" onClick={() => setPerson(EMPTY_PERSON)} disabled={processing}>Limpiar</button>
            <button type="button" className="primary-action" onClick={createIndividual} disabled={processing || !selectedLicense?.configured}>
              {processing ? 'Creando identidad...' : `Crear con licencia ${audience.license} y Moodle`}
            </button>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="student-card credential-result-panel" aria-live="polite">
          <div className="card-head credential-result-head">
            <div>
              <p className="eyebrow">Resultado</p>
              <h2>Lote {result.batch_id.slice(0, 8)}</h2>
            </div>
            <div className="credential-result-actions">
              <label className="credential-password-toggle">
                <input type="checkbox" checked={showPasswords} onChange={(event) => setShowPasswords(event.target.checked)} />
                <span>Mostrar contraseñas</span>
              </label>
              <button type="button" className="primary-action" onClick={() => void downloadReport()} disabled={downloading || reportDownloaded}>
                {reportDownloaded ? 'Reporte descargado' : downloading ? 'Descargando...' : 'Descargar credenciales'}
              </button>
            </div>
          </div>
          <div className="credential-result-summary">
            <span><strong>{result.summary.total}</strong>Procesadas</span>
            <span className="is-success"><strong>{result.summary.completos}</strong>Completas</span>
            <span><strong>{result.summary.parciales}</strong>Parciales</span>
            <span className={result.summary.fallidos ? 'is-danger' : ''}><strong>{result.summary.fallidos}</strong>Fallidas</span>
          </div>
          <div className="portal-table-wrap credential-provision-table-wrap">
            <table className="portal-record-table credential-result-table">
              <thead>
                <tr>
                  <th>Persona</th>
                  <th>Correo Microsoft 365</th>
                  <th>Contraseña permanente</th>
                  <th>Microsoft</th>
                  <th>Licencia {audience.singular}</th>
                  <th>Moodle</th>
                  <th>Resultado</th>
                  <th>Observación</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={`${row.fila_origen}-${row.cedula}`}>
                    <td><strong>{[row.primer_nombre, row.segundo_nombre, row.primer_apellido, row.segundo_apellido].filter(Boolean).join(' ')}</strong><small>{row.cedula}</small></td>
                    <td className="credential-email-cell">{valueOrDash(row.correo_institucional)}</td>
                    <td className="credential-password-cell">{row.clave_permanente ? (showPasswords ? row.clave_permanente : '••••••••••••') : 'Cuenta existente'}</td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_graph)}`}>{statusLabel(row.estado_graph)}</span></td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_licencia)}`}>{statusLabel(row.estado_licencia)}</span></td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_moodle)}`}>{statusLabel(row.estado_moodle)}</span></td>
                    <td>
                      <span className={`credential-status credential-status--${statusTone(row.estado_general)}`}>{statusLabel(row.estado_general)}</span>
                      {rowDetail(row) ? <small className="credential-row-error">{rowDetail(row)}</small> : null}
                    </td>
                    <td className="credential-observation-cell">{row.observacion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="credential-report-expiry">
            La descarga inicial está disponible durante {result.report_expires_minutes} minutos. Después puede recuperarla desde Historial.
          </p>
        </section>
      ) : null}

      {activeSection === 'history' ? (
        <section className="student-card credential-workspace" role="tabpanel">
          <div className="card-head">
            <div>
              <p className="eyebrow">Auditoría</p>
              <h2>Historial de {audience.plural}</h2>
            </div>
            <span>{historyLoadingType === personType ? 'Consultando...' : `${history.length} registro(s)`}</span>
          </div>
          <div className="portal-table-wrap credential-provision-table-wrap">
            <table className="portal-record-table credential-history-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Modo</th>
                  <th>Persona</th>
                  <th>Correo</th>
                  <th>Microsoft</th>
                  <th>Licencia {audience.singular}</th>
                  <th>Moodle</th>
                  <th>Resultado</th>
                  <th>Observación</th>
                  <th>Responsable</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {history.length ? history.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDate(row.fecha_creacion)}</td>
                    <td>{row.modo === 'EXCEL' ? 'Carga masiva' : 'Individual'}</td>
                    <td><strong>{row.nombres}</strong><small>{row.cedula}</small></td>
                    <td className="credential-email-cell">{valueOrDash(row.correo_institucional)}</td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_graph)}`}>{statusLabel(row.estado_graph)}</span></td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_licencia)}`}>{statusLabel(row.estado_licencia)}</span></td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_moodle)}`}>{statusLabel(row.estado_moodle)}</span></td>
                    <td><span className={`credential-status credential-status--${statusTone(row.estado_general)}`}>{statusLabel(row.estado_general)}</span></td>
                    <td className="credential-observation-cell">
                      {row.observacion}
                      {row.numero_descargas > 0 ? (
                        <small>
                          {row.numero_descargas} descarga(s)
                          {row.fecha_ultima_descarga ? ` · Última: ${formatDate(row.fecha_ultima_descarga)}` : ''}
                          {row.usuario_ultima_descarga ? ` · Por: ${row.usuario_ultima_descarga}` : ''}
                        </small>
                      ) : null}
                    </td>
                    <td>{valueOrDash(row.usuario_creacion)}</td>
                    <td>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!row.reporte_disponible || historyDownloadingId !== null}
                        title={row.reporte_disponible ? 'Descargar correo y contraseña permanente' : row.observacion}
                        onClick={() => void downloadHistoryReport(row)}
                      >
                        {historyDownloadingId === row.id
                          ? 'Descargando...'
                          : row.reporte_disponible
                            ? 'Descargar'
                            : 'Sin archivo'}
                      </button>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={11}>
                      {historyLoadingType === personType
                        ? 'Consultando aprovisionamientos...'
                        : 'No existen aprovisionamientos registrados.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {showProcessInfo ? (
        <div
          className="credential-process-info-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowProcessInfo(false)
          }}
        >
          <section
            className="credential-process-info-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="credential-process-info-title"
          >
            <header className="credential-process-info-head">
              <div>
                <p className="eyebrow">Configuración</p>
                <h2 id="credential-process-info-title">Información del proceso</h2>
                <p>Estado técnico para la creación de credenciales de {audience.plural}.</p>
              </div>
              <button
                type="button"
                className="credential-process-info-close"
                aria-label="Cerrar información del proceso"
                title="Cerrar"
                autoFocus
                onClick={() => setShowProcessInfo(false)}
              >
                ×
              </button>
            </header>

            <dl className="credential-process-details">
              <div>
                <dt>Dominio institucional</dt>
                <dd>@{config?.domain || 'intec.edu.ec'}</dd>
                <small>Año de contraseña: {config?.year || new Date().getFullYear()}</small>
              </div>
              <div>
                <dt>Microsoft 365 · {personType === 'PROFESOR' ? 'Profesor' : 'Estudiante'}</dt>
                <dd>{loading ? 'Consultando...' : selectedLicense?.configured ? 'Office 365 A1' : 'No disponible'}</dd>
                <small>
                  {loading
                    ? `Validando licencia ${audience.license}`
                    : selectedLicense?.configured
                      ? `${selectedLicense.name} · ${selectedLicense.available_units.toLocaleString('es-EC')} disponible(s)`
                      : selectedLicense?.detail || `Sin cupos o licencia ${audience.license} no contratada`}
                </small>
              </div>
              <div>
                <dt>Moodle</dt>
                <dd>{loading ? 'Consultando...' : config?.moodle_configured ? 'Disponible' : 'Pendiente'}</dd>
                <small>{loading ? 'Validando servicio web' : config?.moodle_url || 'Sin conexión configurada'}</small>
              </div>
              <div>
                <dt>Identidades registradas</dt>
                <dd>{loading ? '...' : config?.identity_count || 0}</dd>
                <small>Máximo {config?.max_users || 300} por archivo</small>
              </div>
            </dl>

            <footer className="credential-process-info-actions">
              <button type="button" className="primary-action" onClick={() => setShowProcessInfo(false)}>
                Cerrar
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  )
}
