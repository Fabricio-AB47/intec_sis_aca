import { useEffect, useState, type FormEvent } from 'react'

import {
  analyzeInstitutionalEmailWorkbook,
  applyInstitutionalEmailWorkbook,
  downloadInstitutionalEmailTemplate,
  fetchInstitutionalEmailStudents,
  updateInstitutionalEmailStudent,
} from '../../lib/api'
import type {
  InstitutionalEmailAnalysisResponse,
  InstitutionalEmailStudent,
  InstitutionalEmailStudentsResponse,
} from '../../types/app'

type ActualizarCorreoIntecViewProps = {
  displayName: string
}

type InstitutionalEmailSection = 'bulk' | 'individual'

const PAGE_SIZE = 25
const EMAIL_PATTERN = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@intec\.edu\.ec$/i

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function valueOrDash(value: string | null | undefined): string {
  return value?.trim() || '-'
}

function passwordStatus(student: InstitutionalEmailStudent): { label: string; tone: string } {
  return student.password_configurada
    ? { label: 'Configurada', tone: 'ready' }
    : { label: 'Sin contraseña', tone: 'warning' }
}

function registrationStatus(student: InstitutionalEmailStudent): { label: string; tone: string } {
  if (!student.tiene_registro) return { label: 'Sin registro', tone: 'pending' }
  if (!student.sincronizado) return { label: 'Pendiente de sincronizar', tone: 'warning' }
  return { label: 'Sincronizado', tone: 'ready' }
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function ActualizarCorreoIntecView({ displayName }: Readonly<ActualizarCorreoIntecViewProps>) {
  const [data, setData] = useState<InstitutionalEmailStudentsResponse>({
    rows: [],
    total: 0,
    page: 1,
    page_size: PAGE_SIZE,
    cedula: '',
  })
  const [cedulaInput, setCedulaInput] = useState('')
  const [appliedCedula, setAppliedCedula] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [activeSection, setActiveSection] = useState<InstitutionalEmailSection>('bulk')

  const [selectedStudent, setSelectedStudent] = useState<InstitutionalEmailStudent | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [savingStudent, setSavingStudent] = useState(false)

  const [workbook, setWorkbook] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<InstitutionalEmailAnalysisResponse | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [confirmApply, setConfirmApply] = useState(false)
  const [fileInputKey, setFileInputKey] = useState(0)

  const pageCount = Math.max(1, Math.ceil(data.total / data.page_size))

  async function loadStudents(cedula = appliedCedula, page = data.page) {
    setLoading(true)
    setError('')
    try {
      const response = await fetchInstitutionalEmailStudents({ cedula, page, pageSize: PAGE_SIZE })
      setData(response)
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo consultar el listado de estudiantes.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchInstitutionalEmailStudents({ page: 1, pageSize: PAGE_SIZE })
      .then((response) => {
        if (active) setData(response)
      })
      .catch((apiError: unknown) => {
        if (active) setError(errorMessage(apiError, 'No se pudo consultar el listado de estudiantes.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!message) return undefined
    const timeoutId = window.setTimeout(() => setMessage(''), 3000)
    return () => window.clearTimeout(timeoutId)
  }, [message])

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    const cedula = cedulaInput.trim()
    if (cedula && !/^\d{10}$/.test(cedula)) {
      setError('La cédula debe contener exactamente 10 dígitos.')
      return
    }
    setAppliedCedula(cedula)
    await loadStudents(cedula, 1)
  }

  async function clearSearch() {
    setCedulaInput('')
    setAppliedCedula('')
    setMessage('')
    await loadStudents('', 1)
  }

  async function changePage(nextPage: number) {
    const target = Math.min(Math.max(nextPage, 1), pageCount)
    if (target === data.page || loading) return
    await loadStudents(appliedCedula, target)
  }

  function openStudent(student: InstitutionalEmailStudent) {
    setSelectedStudent(student)
    setEmail(student.correo_intec || '')
    setPassword('')
    setShowPassword(false)
    setError('')
    setMessage('')
  }

  function closeStudent() {
    if (savingStudent) return
    setSelectedStudent(null)
    setEmail('')
    setPassword('')
    setShowPassword(false)
  }

  async function saveStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedStudent) return
    const normalizedEmail = email.trim().toLowerCase()
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError('El correo debe pertenecer al dominio @intec.edu.ec.')
      return
    }
    if (password.length < 6 || password.length > 20 || password !== password.trim()) {
      setError('La contraseña debe tener entre 6 y 20 caracteres y no incluir espacios al inicio o final.')
      return
    }

    setSavingStudent(true)
    setError('')
    setMessage('')
    try {
      const response = await updateInstitutionalEmailStudent(selectedStudent.cedula, {
        correo_intec: normalizedEmail,
        password,
      })
      setMessage(response.message)
      setSelectedStudent(null)
      setEmail('')
      setPassword('')
      setShowPassword(false)
      await loadStudents(appliedCedula, data.page)
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo actualizar el correo institucional.'))
    } finally {
      setSavingStudent(false)
    }
  }

  async function downloadTemplate() {
    setDownloading(true)
    setError('')
    setMessage('')
    try {
      const blob = await downloadInstitutionalEmailTemplate()
      saveBlob(blob, 'actualizacion_correo_intec.xlsx')
      setMessage('Plantilla generada con el listado actual de estudiantes.')
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo descargar la plantilla Excel.'))
    } finally {
      setDownloading(false)
    }
  }

  async function analyzeWorkbook() {
    if (!workbook) {
      setError('Selecciona el archivo Excel que deseas comparar.')
      return
    }
    setAnalyzing(true)
    setError('')
    setMessage('')
    setAnalysis(null)
    try {
      const response = await analyzeInstitutionalEmailWorkbook(workbook)
      setAnalysis(response)
      setMessage(
        response.summary.errores
          ? `Análisis finalizado con ${response.summary.errores} fila(s) por corregir.`
          : `${response.summary.validos} fila(s) listas para actualizar.`,
      )
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo analizar el archivo Excel.'))
    } finally {
      setAnalyzing(false)
    }
  }

  async function applyWorkbook() {
    if (!workbook || !analysis || analysis.summary.validos === 0 || analysis.summary.errores > 0) return
    setApplying(true)
    setError('')
    setMessage('')
    try {
      const response = await applyInstitutionalEmailWorkbook(workbook)
      setMessage(response.message)
      setAnalysis(null)
      setWorkbook(null)
      setConfirmApply(false)
      setFileInputKey((current) => current + 1)
      await loadStudents(appliedCedula, data.page)
    } catch (apiError) {
      setError(errorMessage(apiError, 'No se pudo aplicar la actualización masiva.'))
      setConfirmApply(false)
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="institutional-email-page">
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Actualizaciones</p>
          <h2>Actualización de correo INTEC</h2>
          <p className="report-description">
            Administra el correo institucional estudiantil y sincroniza CorreosEstudIntec con DATOS_ESTUD.
          </p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Correo institucional</span>
            </div>
          </div>
        </div>
      </header>

      <nav className="institutional-email-submenu" role="tablist" aria-label="Actualización de correo institucional">
        <button
          className={activeSection === 'bulk' ? 'is-active' : ''}
          type="button"
          role="tab"
          aria-selected={activeSection === 'bulk'}
          aria-controls="institutional-email-bulk-panel"
          onClick={() => setActiveSection('bulk')}
        >
          <strong>Carga masiva</strong>
          <span>Plantilla, validación y actualización por Excel</span>
        </button>
        <button
          className={activeSection === 'individual' ? 'is-active' : ''}
          type="button"
          role="tab"
          aria-selected={activeSection === 'individual'}
          aria-controls="institutional-email-individual-panel"
          onClick={() => setActiveSection('individual')}
        >
          <strong>Actualización individual</strong>
          <span>Consulta y edición por número de cédula</span>
        </button>
      </nav>

      {error ? <p className="form-error" role="alert">{error}</p> : null}

      {activeSection === 'individual' ? (
      <section
        id="institutional-email-individual-panel"
        className="student-card institutional-email-search-card"
        role="tabpanel"
      >
        <div className="card-head">
          <div>
            <p className="eyebrow">Consulta</p>
            <h3>Estudiantes y correo institucional</h3>
          </div>
          <span>{loading ? 'Consultando...' : `${data.total} registro(s)`}</span>
        </div>
        <form className="institutional-email-search" onSubmit={submitSearch}>
          <label>
            <span>Número de cédula</span>
            <input
              value={cedulaInput}
              inputMode="numeric"
              maxLength={10}
              placeholder="10 dígitos"
              onChange={(event) => setCedulaInput(event.target.value.replace(/\D/g, '').slice(0, 10))}
            />
          </label>
          <button className="primary-action" type="submit" disabled={loading}>
            {loading ? 'Consultando...' : 'Buscar'}
          </button>
          <button className="ghost-button" type="button" onClick={() => void clearSearch()} disabled={loading || (!cedulaInput && !appliedCedula)}>
            Limpiar
          </button>
        </form>

        <div className="matricula-table-wrap institutional-email-table-wrap">
          <table className="matricula-table institutional-email-table">
            <thead>
              <tr>
                <th>Estudiante</th>
                <th>Cédula</th>
                <th>Carrera</th>
                <th>Correo INTEC</th>
                <th>Contraseña INTEC</th>
                <th>Registro</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              {!loading && data.rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="institutional-email-empty">No existen estudiantes para la consulta indicada.</td>
                </tr>
              ) : null}
              {data.rows.map((student) => {
                const password = passwordStatus(student)
                const registration = registrationStatus(student)
                return (
                  <tr key={`${student.codigo_estud}-${student.cedula}`}>
                    <td><strong>{student.estudiante}</strong><small>Código {student.codigo_estud}</small></td>
                    <td>{student.cedula}</td>
                    <td>{valueOrDash(student.carrera)}</td>
                    <td className="institutional-email-address">{valueOrDash(student.correo_intec)}</td>
                    <td><span className={`institutional-email-badge institutional-email-badge--${password.tone}`}>{password.label}</span></td>
                    <td><span className={`institutional-email-badge institutional-email-badge--${registration.tone}`}>{registration.label}</span></td>
                    <td><button className="ghost-button" type="button" onClick={() => openStudent(student)}>Actualizar</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="institutional-email-pagination">
          <span>{data.total ? `${(data.page - 1) * data.page_size + 1}-${Math.min(data.page * data.page_size, data.total)} de ${data.total}` : '0 registros'}</span>
          <div>
            <button className="ghost-button" type="button" onClick={() => void changePage(1)} disabled={loading || data.page <= 1}>Primero</button>
            <button className="ghost-button" type="button" onClick={() => void changePage(data.page - 1)} disabled={loading || data.page <= 1}>Anterior</button>
            <strong>Página {data.page} / {pageCount}</strong>
            <button className="ghost-button" type="button" onClick={() => void changePage(data.page + 1)} disabled={loading || data.page >= pageCount}>Siguiente</button>
            <button className="ghost-button" type="button" onClick={() => void changePage(pageCount)} disabled={loading || data.page >= pageCount}>Último</button>
          </div>
        </div>
      </section>
      ) : null}

      {activeSection === 'bulk' ? (
      <section
        id="institutional-email-bulk-panel"
        className="student-card institutional-email-bulk-card"
        role="tabpanel"
      >
        <div className="card-head">
          <div>
            <p className="eyebrow">Actualización masiva</p>
            <h3>Comparación por Excel</h3>
          </div>
          <span>Identificación únicamente por cédula</span>
        </div>
        <p className="institutional-email-bulk-guide">
          La plantilla contiene la cédula, el correo nuevo y la contraseña nueva. El código único del estudiante se obtiene y valida automáticamente en DATOS_ESTUD antes de actualizar.
        </p>
        <div className="institutional-email-bulk-actions">
          <div className="institutional-email-action-control">
            <span>Plantilla de comparación</span>
            <button className="ghost-button" type="button" onClick={() => void downloadTemplate()} disabled={downloading}>
              {downloading ? 'Generando...' : 'Descargar plantilla Excel'}
            </button>
          </div>
          <label className="institutional-email-file">
            <span>Archivo de actualización</span>
            <input
              key={fileInputKey}
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => {
                setWorkbook(event.target.files?.[0] || null)
                setAnalysis(null)
                setMessage('')
                setError('')
              }}
            />
          </label>
          <div className="institutional-email-action-control">
            <span>Validación del archivo</span>
            <button className="primary-action" type="button" onClick={() => void analyzeWorkbook()} disabled={!workbook || analyzing || applying}>
              {analyzing ? 'Analizando...' : 'Analizar archivo'}
            </button>
          </div>
        </div>

        {analysis ? (
          <>
            <div className="institutional-email-analysis-summary">
              <span>Total <strong>{analysis.summary.total}</strong></span>
              <span>Válidas <strong>{analysis.summary.validos}</strong></span>
              <span>Errores <strong>{analysis.summary.errores}</strong></span>
              <button
                className="primary-action"
                type="button"
                disabled={analysis.summary.validos === 0 || analysis.summary.errores > 0 || applying}
                onClick={() => setConfirmApply(true)}
              >
                Aplicar actualización
              </button>
            </div>
            <div className="matricula-table-wrap institutional-email-preview-wrap">
              <table className="matricula-table institutional-email-preview-table">
                <thead>
                  <tr>
                    <th>Fila</th>
                    <th>Cédula</th>
                    <th>Estudiante</th>
                    <th>Correo actual</th>
                    <th>Correo nuevo</th>
                    <th>Contraseña</th>
                    <th>Estado</th>
                    <th>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.rows.map((row) => (
                    <tr key={`${row.row}-${row.cedula}`}>
                      <td>{row.row}</td>
                      <td>{row.cedula}</td>
                      <td>{valueOrDash(row.estudiante)}</td>
                      <td className="institutional-email-address">{valueOrDash(row.correo_actual)}</td>
                      <td className="institutional-email-address">{valueOrDash(row.correo_nuevo)}</td>
                      <td>{row.password_informada ? 'Informada' : 'Faltante'}</td>
                      <td><span className={`institutional-email-badge institutional-email-badge--${row.estado === 'VALIDO' ? 'ready' : 'error'}`}>{row.estado}</span></td>
                      <td>{row.detalle}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>
      ) : null}

      {selectedStudent ? (
        <div className="institutional-email-modal-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeStudent()
        }}>
          <section className="institutional-email-modal" role="dialog" aria-modal="true" aria-labelledby="institutional-email-edit-title">
            <header>
              <div>
                <p className="eyebrow">Actualización individual</p>
                <h3 id="institutional-email-edit-title">{selectedStudent.estudiante}</h3>
              </div>
              <button className="ghost-button" type="button" onClick={closeStudent} disabled={savingStudent}>Cerrar</button>
            </header>
            <div className="institutional-email-student-summary">
              <span><small>Cédula</small><strong>{selectedStudent.cedula}</strong></span>
              <span><small>Código</small><strong>{selectedStudent.codigo_estud}</strong></span>
              <span><small>Carrera</small><strong>{valueOrDash(selectedStudent.carrera)}</strong></span>
              <span><small>Correo actual</small><strong>{valueOrDash(selectedStudent.correo_intec)}</strong></span>
            </div>
            <form className="institutional-email-edit-form" onSubmit={saveStudent}>
              <label>
                <span>Correo INTEC</span>
                <input type="email" maxLength={100} value={email} placeholder="usuario@intec.edu.ec" onChange={(event) => setEmail(event.target.value)} required />
              </label>
              <label>
                <span>Nueva contraseña</span>
                <div className="institutional-email-password-field">
                  <input type={showPassword ? 'text' : 'password'} minLength={6} maxLength={20} value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} required />
                  <button className="ghost-button" type="button" onClick={() => setShowPassword((current) => !current)}>{showPassword ? 'Ocultar' : 'Mostrar'}</button>
                </div>
              </label>
              <p className="institutional-email-security-note">La contraseña actual no se consulta ni se muestra. Al guardar será reemplazada en ambas tablas.</p>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
              <div className="institutional-email-modal-actions">
                <button className="ghost-button" type="button" onClick={closeStudent} disabled={savingStudent}>Cancelar</button>
                <button className="primary-action" type="submit" disabled={savingStudent}>{savingStudent ? 'Guardando...' : 'Guardar actualización'}</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {confirmApply && analysis ? (
        <div className="institutional-email-modal-overlay" role="presentation">
          <section className="institutional-email-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="institutional-email-confirm-title">
            <p className="eyebrow">Confirmación</p>
            <h3 id="institutional-email-confirm-title">Aplicar actualización masiva</h3>
            <p>Se reemplazarán el correo institucional y la contraseña de {analysis.summary.validos} estudiante(s) en CorreosEstudIntec y DATOS_ESTUD.</p>
            <div className="institutional-email-modal-actions">
              <button className="ghost-button" type="button" onClick={() => setConfirmApply(false)} disabled={applying}>Cancelar</button>
              <button className="primary-action" type="button" onClick={() => void applyWorkbook()} disabled={applying}>{applying ? 'Aplicando...' : 'Confirmar actualización'}</button>
            </div>
          </section>
        </div>
      ) : null}

      {message ? (
        <div className="institutional-email-notification-overlay" role="presentation">
          <section className="institutional-email-notification" role="status" aria-live="polite" aria-atomic="true">
            <span className="institutional-email-notification__mark" aria-hidden="true">✓</span>
            <div>
              <p className="eyebrow">Proceso completado</p>
              <h3>{message}</h3>
              <small>Esta ventana se cerrará automáticamente.</small>
            </div>
            <span className="institutional-email-notification__timer" aria-hidden="true" />
          </section>
        </div>
      ) : null}
    </div>
  )
}
