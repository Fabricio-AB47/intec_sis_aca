import { useEffect, useMemo, useState } from 'react'

import {
  createPracticasExpediente,
  downloadPracticasCartaCompromiso,
  fetchPracticasCatalog,
  fetchPracticasElegibles,
  fetchPracticasExpedientes,
  fetchPracticasPeriodoDesignaciones,
  fetchPracticasPeriodos,
  fetchPracticasResponsableAvance,
  fetchPracticasReviewDetail,
  fetchPracticasStudent,
  reviewPracticasExpediente,
  savePracticasPeriodoDesignacion,
  searchAcademicEnrollmentTeachers,
  uploadPracticasAutorizacion,
  uploadPracticasCartaCompromiso,
  uploadPracticasCertificado,
} from '../../lib/api'
import type {
  AcademicTeacherOption,
  PracticasCatalogResponse,
  PracticasExpedienteItem,
  PracticasEligibilityItem,
  PracticasProcessCode,
  PracticasPeriodoDesignacionItem,
  PracticasPeriodoItem,
  PracticasReviewDecision,
  PracticasReviewDetailResponse,
  PracticasResponsableProgressResponse,
  PracticasStudentResponse,
} from '../../types/app'
import { ExpedientesDocumentalesView } from '../expedientes/ExpedientesDocumentalesView'

type PracticasInstitucionalesViewProps = {
  displayName: string
  role?: string
  codigoEstud?: number
}

const PROCESS_OPTIONS: Array<{ code: PracticasProcessCode; label: string; short: string }> = [
  { code: 'PPF', label: 'Prácticas preprofesionales', short: 'Preprofesionales' },
  { code: 'VIN', label: 'Vinculación con la sociedad', short: 'Vinculación con la sociedad' },
]

function valueOrDash(value: unknown) {
  const text = value === null || value === undefined ? '' : String(value).trim()
  return text || '-'
}

function processLabel(code: string | undefined) {
  return PROCESS_OPTIONS.find((item) => item.code === code)?.label || code || '-'
}

function statusClass(value: string | null | undefined) {
  const normalized = (value || '').toLowerCase()
  if (normalized.includes('aprob') || normalized.includes('valid') || normalized.includes('cerr')) return 'portal-status portal-status--ok'
  if (normalized.includes('observ') || normalized.includes('pend')) return 'portal-status portal-status--warning'
  if (normalized.includes('anul') || normalized.includes('rech')) return 'portal-status portal-status--danger'
  return 'portal-status'
}

function percentValue(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0
  return Math.max(0, Math.min(100, numeric))
}

function periodLabel(periodo: PracticasPeriodoItem) {
  return [
    valueOrDash(periodo.CodigoPeriodo),
    valueOrDash(periodo.NombrePeriodo),
    periodo.EstadoPeriodo ? `Estado ${periodo.EstadoPeriodo}` : '',
    periodo.TipoMatricula ? `Tipo ${periodo.TipoMatricula}` : '',
    periodo.Anio ? `Año ${periodo.Anio}` : '',
  ].filter(Boolean).join(' · ')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function PracticasInstitucionalesView({
  displayName,
  role = '',
  codigoEstud,
}: Readonly<PracticasInstitucionalesViewProps>) {
  const [mode, setMode] = useState<'student' | 'admin' | 'responsable'>('student')
  const [selectedProcess, setSelectedProcess] = useState<PracticasProcessCode>('PPF')
  const [catalog, setCatalog] = useState<PracticasCatalogResponse | null>(null)
  const [studentData, setStudentData] = useState<PracticasStudentResponse | null>(null)
  const [responsableProgress, setResponsableProgress] = useState<PracticasResponsableProgressResponse | null>(null)
  const [expedientes, setExpedientes] = useState<PracticasExpedienteItem[]>([])
  const [adminElegibles, setAdminElegibles] = useState<PracticasEligibilityItem[]>([])
  const [periodos, setPeriodos] = useState<PracticasPeriodoItem[]>([])
  const [periodDesignations, setPeriodDesignations] = useState<PracticasPeriodoDesignacionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [eligibilitySearch, setEligibilitySearch] = useState('')
  const [teacherSearch, setTeacherSearch] = useState('')
  const [teacherOptions, setTeacherOptions] = useState<AcademicTeacherOption[]>([])
  const [selectedEligibility, setSelectedEligibility] = useState('')
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [selectedSourcePeriod, setSelectedSourcePeriod] = useState('')
  const [selectedStudents, setSelectedStudents] = useState<number[]>([])
  const [documentExpedient, setDocumentExpedient] = useState<{
    identification: string
    process: PracticasProcessCode
  } | null>(null)
  const [reviewDetail, setReviewDetail] = useState<PracticasReviewDetailResponse | null>(null)
  const [reviewHours, setReviewHours] = useState('')
  const [reviewCorroborated, setReviewCorroborated] = useState(false)
  const [reviewObservation, setReviewObservation] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewError, setReviewError] = useState('')
  const [responsableForm, setResponsableForm] = useState({
    nombre_responsable: '',
    cedula_responsable: '',
    correo_responsable: '',
    codigo_docente: '',
    rol_responsable: 'RESPONSABLE',
  })

  const isAdmin = !['ESTUDIANTE', 'DOCENTE'].includes(role.trim().toUpperCase())
  const isResponsible = role.trim().toUpperCase() === 'DOCENTE'

  const filteredEligibility = useMemo(
    () => (studentData?.eligibility || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [selectedProcess, studentData]
  )

  const eligibilityOptions = isAdmin ? adminElegibles : filteredEligibility
  const sourcePeriodDetail = periodos.find((periodo) => String(periodo.CodigoPeriodo) === selectedSourcePeriod)
  const targetPeriodDetail = periodos.find((periodo) => String(periodo.CodigoPeriodo) === selectedPeriod)

  const filteredStudentExpedientes = useMemo(
    () => (studentData?.expedientes || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [selectedProcess, studentData]
  )

  const visibleStudentExpedientes = isAdmin ? expedientes : filteredStudentExpedientes

  const processDocuments = useMemo(
    () => (catalog?.documents || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [catalog, selectedProcess]
  )

  const processResponsibles = useMemo(
    () => (catalog?.responsibles || []).filter((item) => item.TipoProcesoCodigo === selectedProcess),
    [catalog, selectedProcess]
  )

  async function loadCatalog() {
    const payload = await fetchPracticasCatalog()
    setCatalog(payload)
  }

  async function loadStudent() {
    if (isAdmin && !codigoEstud) {
      setStudentData({ codigo_estud: 0, eligibility: [], expedientes: [] })
      setSelectedEligibility('')
      return
    }
    const payload = await fetchPracticasStudent(codigoEstud)
    setStudentData(payload)
    const first = payload.eligibility.find((item) => item.TipoProcesoCodigo === selectedProcess)
    setSelectedEligibility(first ? `${first.CodigoCarrera || ''}|${first.CodigoPeriodo || ''}` : '')
  }

  async function loadAdmin() {
    const payload = await fetchPracticasExpedientes({ tipo_proceso: selectedProcess, search: '', limit: 200 })
    setExpedientes(payload.items || [])
  }

  async function loadAdminEligibility() {
    if (!isAdmin) return
    const payload = await fetchPracticasElegibles({
      tipo_proceso: selectedProcess,
      search: eligibilitySearch,
      codigo_periodo: selectedSourcePeriod,
      limit: 500,
    })
    setAdminElegibles(payload.items || [])
  }

  async function loadPeriodDesignations() {
    if (!isAdmin) return
    const [periodPayload, designationPayload] = await Promise.all([
      fetchPracticasPeriodos(selectedProcess),
      fetchPracticasPeriodoDesignaciones(selectedProcess),
    ])
    setPeriodos(periodPayload.items || [])
    setPeriodDesignations(designationPayload.items || [])
    if (!selectedPeriod && periodPayload.items?.length) {
      setSelectedPeriod(String(periodPayload.items[0].CodigoPeriodo || ''))
    }
    if (!selectedSourcePeriod && periodPayload.items?.length) {
      setSelectedSourcePeriod(String(periodPayload.items[0].CodigoPeriodo || ''))
    }
  }

  async function loadResponsibleProgress() {
    if (!isResponsible && !isAdmin) return
    const payload = await fetchPracticasResponsableAvance(selectedProcess)
    setResponsableProgress(payload)
  }

  async function openReview(expedienteId: number) {
    setReviewLoading(true)
    setReviewError('')
    setError('')
    setMessage('')
    try {
      const payload = await fetchPracticasReviewDetail(expedienteId)
      const currentHours = Math.max(
        Number(payload.HorasReconocidas || 0),
        Number(payload.HorasAsistenciaValidadas || 0),
      )
      setReviewDetail(payload)
      setReviewHours(currentHours > 0 ? String(currentHours) : '')
      setReviewCorroborated(false)
      setReviewObservation('')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el expediente para revisión.')
    } finally {
      setReviewLoading(false)
    }
  }

  function closeReview() {
    if (reviewLoading) return
    setReviewDetail(null)
    setReviewHours('')
    setReviewCorroborated(false)
    setReviewObservation('')
    setReviewError('')
  }

  async function submitReview(decision: PracticasReviewDecision) {
    if (!reviewDetail) return
    const hours = Number(reviewHours.replace(',', '.'))
    const observation = reviewObservation.trim()
    if (!Number.isFinite(hours) || hours < 0) {
      setReviewError('Ingrese una cantidad válida de horas verificadas.')
      return
    }
    if ((decision === 'OBSERVAR' || decision === 'RECHAZAR') && !observation) {
      setReviewError('Registre el motivo de la observación o del rechazo.')
      return
    }
    if (decision === 'APROBAR') {
      if (!reviewDetail.DocumentosCompletos) {
        setReviewError('No se puede aprobar mientras existan documentos obligatorios pendientes.')
        return
      }
      if (hours < Number(reviewDetail.HorasRequeridas || 0)) {
        setReviewError(`Debe corroborar al menos ${reviewDetail.HorasRequeridas} horas.`)
        return
      }
      if (!reviewCorroborated) {
        setReviewError('Confirme que revisó los documentos y las horas del estudiante.')
        return
      }
    }

    setReviewLoading(true)
    setReviewError('')
    setError('')
    setMessage('')
    try {
      const response = await reviewPracticasExpediente(reviewDetail.ExpedienteId, {
        tipo_proceso_codigo: reviewDetail.TipoProcesoCodigo,
        decision,
        horas_verificadas: hours,
        documentos_corroborados: reviewCorroborated,
        observacion: observation || null,
      })
      const titulationMessage = response.titulacion?.sincronizado
        ? ' El requisito ya se refleja en Titulación.'
        : response.titulacion?.motivo
          ? ` ${response.titulacion.motivo}`
          : ''
      setMessage(`${response.message}${titulationMessage}`)
      setReviewDetail(null)
      setReviewHours('')
      setReviewCorroborated(false)
      setReviewObservation('')
      await loadResponsibleProgress()
      if (isAdmin) await loadAdmin()
    } catch (apiError) {
      setReviewError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la revisión docente.')
    } finally {
      setReviewLoading(false)
    }
  }

  async function searchTeachers() {
    if (!teacherSearch.trim()) {
      setError('Ingrese nombre, cédula o código del docente.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await searchAcademicEnrollmentTeachers(teacherSearch, 20, false)
      setTeacherOptions(payload.items || [])
      if (!(payload.items || []).length) setMessage('No se encontraron docentes con ese nombre, cédula o código.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar docentes.')
    } finally {
      setLoading(false)
    }
  }

  function selectTeacher(teacher: AcademicTeacherOption) {
    setResponsableForm((current) => ({
      ...current,
      nombre_responsable: teacher.descripcion || teacher.login || '',
      cedula_responsable: teacher.cedula || '',
      correo_responsable: teacher.correo || teacher.correo_personal || '',
      codigo_docente: teacher.codigo_doc || '',
      rol_responsable: 'RESPONSABLE',
    }))
    setTeacherSearch(`${teacher.descripcion || teacher.login || ''} ${teacher.cedula || ''}`.trim())
    setTeacherOptions([])
  }

  function toggleStudent(code: number) {
    const student = adminElegibles.find((item) => Number(item.codigo_estud) === code)
    if (student && !student.PuedeMatricular) {
      setError('El estudiante no cumple tercer semestre. Suba una autorización para habilitarlo.')
      return
    }
    setSelectedStudents((current) => (
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code]
    ))
  }

  function toggleAllStudents() {
    const codes = adminElegibles
      .filter((item) => Boolean(item.PuedeMatricular))
      .map((item) => Number(item.codigo_estud))
      .filter(Boolean)
    setSelectedStudents((current) => current.length === codes.length ? [] : codes)
  }

  async function uploadAutorizacion(student: PracticasEligibilityItem, file: File | null) {
    if (!file) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await uploadPracticasAutorizacion({
        tipo_proceso_codigo: selectedProcess,
        codigo_estud: Number(student.codigo_estud),
        codigo_periodo: String(student.CodigoPeriodo || selectedSourcePeriod),
        file,
      })
      setMessage(String(response.message || 'Autorización cargada correctamente.'))
      await loadAdminEligibility()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo subir la autorización.')
    } finally {
      setSaving(false)
    }
  }

  async function loadAll() {
    setError('')
    setMessage('')
    setLoading(true)
    try {
      await loadCatalog()
      if (!isResponsible) await loadStudent()
      if (isAdmin) {
        await loadAdmin()
        await loadPeriodDesignations()
      }
      if (isResponsible || isAdmin) await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar prácticas institucionales.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProcess])

  async function createExpediente() {
    const [codigoEstudValue, codigoCarrera, codigoPeriodo] = selectedEligibility.split('|')
    if (!codigoEstudValue || (!codigoCarrera && !codigoPeriodo)) {
      setError('Seleccione un estudiante, carrera y período elegible.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await createPracticasExpediente({
        tipo_proceso_codigo: selectedProcess,
        codigo_estud: Number(codigoEstudValue) || codigoEstud || null,
        codigo_carrera: codigoCarrera || null,
        codigo_periodo: codigoPeriodo || null,
        observacion: `Creado desde módulo de ${processLabel(selectedProcess)}`,
      })
      setMessage(String(response.Mensaje || response.message || 'Expediente creado correctamente.'))
      await loadStudent()
      if (isAdmin) {
        await loadAdmin()
        await loadAdminEligibility()
      }
      if (isResponsible || isAdmin) await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo crear el expediente.')
    } finally {
      setSaving(false)
    }
  }

  async function saveResponsable() {
    if (!selectedSourcePeriod) {
      setError('Seleccione el período académico del estudiante para cargar la lista.')
      return
    }
    if (!selectedPeriod) {
      setError('Seleccione el nuevo período de prácticas donde se va a matricular.')
      return
    }
    if (!responsableForm.codigo_docente.trim()) {
      setError('Seleccione un docente del buscador para registrar la designación.')
      return
    }
    if (!selectedStudents.length) {
      setError('Seleccione los estudiantes que estarán a cargo del docente.')
      return
    }
    if (!responsableForm.nombre_responsable.trim()) {
      setError('Ingrese el nombre del responsable.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await savePracticasPeriodoDesignacion({
        tipo_proceso_codigo: selectedProcess,
        codigo_periodo: selectedPeriod,
        codigo_periodo_origen: selectedSourcePeriod,
        nombre_responsable: responsableForm.nombre_responsable.trim(),
        cedula_responsable: responsableForm.cedula_responsable.trim() || null,
        correo_responsable: responsableForm.correo_responsable.trim() || null,
        codigo_docente: responsableForm.codigo_docente.trim(),
        rol_responsable: 'RESPONSABLE',
        estudiantes: selectedStudents,
      })
      setResponsableForm({
        nombre_responsable: '',
        cedula_responsable: '',
        correo_responsable: '',
        codigo_docente: '',
        rol_responsable: 'RESPONSABLE',
      })
      setTeacherSearch('')
      setSelectedStudents([])
      setMessage(String(response.message || 'Matrícula por período registrada en prácticas correctamente.'))
      await loadCatalog()
      await loadAdmin()
      await loadStudent()
      await loadPeriodDesignations()
      await loadResponsibleProgress()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar el responsable.')
    } finally {
      setSaving(false)
    }
  }

  async function downloadCarta(item: PracticasExpedienteItem) {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const blob = await downloadPracticasCartaCompromiso(item.ExpedienteId)
      downloadBlob(blob, `carta-compromiso-${item.CodigoExpediente || item.ExpedienteId}.pdf`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la carta compromiso.')
    } finally {
      setSaving(false)
    }
  }

  async function uploadCarta(item: PracticasExpedienteItem, file: File | null) {
    if (!file) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await uploadPracticasCartaCompromiso(item.ExpedienteId, file)
      setMessage('Carta compromiso subida correctamente.')
      await loadStudent()
      if (isAdmin) await loadAdmin()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo subir la carta compromiso.')
    } finally {
      setSaving(false)
    }
  }

  async function uploadCertificado(item: PracticasExpedienteItem, file: File | null) {
    if (!file) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await uploadPracticasCertificado(item.ExpedienteId, file)
      setMessage('Certificado subido correctamente.')
      await loadStudent()
      if (isAdmin) await loadAdmin()
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo subir el certificado.')
    } finally {
      setSaving(false)
    }
  }

  function openDocumentExpedient(item: PracticasExpedienteItem) {
    const identification = String(item.Cedula_Est || '').trim()
    if (!identification) {
      setError('El expediente no tiene una cédula estudiantil válida para abrir la carpeta documental.')
      return
    }
    setError('')
    setMessage('')
    setDocumentExpedient({
      identification,
      process: item.TipoProcesoCodigo === 'VIN' ? 'VIN' : 'PPF',
    })
  }

  return (
    <section className="portal-student-page practicas-page">
      <header className="portal-student-hero practicas-hero">
        <small>Prácticas institucionales</small>
        <h1>Preprofesionales y vinculación con la sociedad</h1>
        <p>{displayName} · Expedientes asignados, carta compromiso y designación administrativa.</p>
      </header>

      <div className="portal-dashboard-overview practicas-controls">
        <div className="teacher-evaluation__flow-actions practicas-process-tabs">
          {PROCESS_OPTIONS.map((item) => (
            <button
              key={item.code}
              type="button"
              className={selectedProcess === item.code ? 'primary-action' : 'ghost-button'}
              onClick={() => {
                setSelectedProcess(item.code)
                setSelectedStudents([])
                setAdminElegibles([])
                closeReview()
              }}
            >
              {item.short}
            </button>
          ))}
        </div>
        {isAdmin ? (
          <div className="teacher-evaluation__flow-actions practicas-process-tabs">
            <button type="button" className={mode === 'student' ? 'primary-action' : 'ghost-button'} onClick={() => setMode('student')}>
              Estudiantes
            </button>
            <button type="button" className={mode === 'responsable' ? 'primary-action' : 'ghost-button'} onClick={() => setMode('responsable')}>
              Avance responsable
            </button>
            <button type="button" className={mode === 'admin' ? 'primary-action' : 'ghost-button'} onClick={() => setMode('admin')}>
              Designación
            </button>
          </div>
        ) : null}
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}

      <section className="portal-dashboard-overview practicas-summary">
        <article>
          <span>Proceso</span>
          <strong>{processLabel(selectedProcess)}</strong>
          <p>{selectedProcess === 'PPF' ? 'Carta compromiso, certificados, asistencia, actividades y evaluación.' : 'Anexo 1, Anexo 2, evidencias y certificado.'}</p>
        </article>
        <article>
          <span>Documentos</span>
          <strong>{processDocuments.length}</strong>
          <p>{processDocuments.filter((item) => item.EsObligatorio).length} obligatorio(s)</p>
        </article>
        <article>
          <span>Responsables</span>
          <strong>{processResponsibles.length}</strong>
          <p>Activos para {processLabel(selectedProcess)}</p>
        </article>
      </section>

      {mode === 'responsable' || isResponsible ? (
        <section className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <span>Responsable</span>
            <strong>Corroboración y aprobación de {processLabel(selectedProcess).toLowerCase()}</strong>
          </div>

          <section className="practicas-progress-card">
            <div className="practicas-progress-head">
              <div>
                <span>Avance general</span>
                <strong>{percentValue(responsableProgress?.summary?.avance).toFixed(2)}%</strong>
              </div>
              <button type="button" className="secondary-action" onClick={loadResponsibleProgress} disabled={loading || saving}>
                Actualizar avance
              </button>
            </div>
            <div className="practicas-progress-bar" aria-label="Avance general">
              <span style={{ width: `${percentValue(responsableProgress?.summary?.avance)}%` }} />
            </div>
            <div className="practicas-progress-metrics">
              <span><b>{responsableProgress?.summary?.expedientes || 0}</b> expediente(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_cargados || 0}</b> cargado(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_validados || 0}</b> validado(s)</span>
              <span><b>{responsableProgress?.summary?.documentos_pendientes || 0}</b> pendiente(s)</span>
            </div>
          </section>

          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Estado</th>
                  <th>Horas</th>
                  <th>Documentos</th>
                  <th>Avance</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {responsableProgress?.items?.length ? responsableProgress.items.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</td>
                    <td>
                      <strong>{valueOrDash(item.Apellidos_nombre)}</strong>
                      <small>{valueOrDash(item.Cedula_Est)}</small>
                    </td>
                    <td>{valueOrDash(item.Carrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>
                      <strong>{Number(item.HorasReconocidas || 0).toFixed(2)} / {Number(item.HorasRequeridas || (selectedProcess === 'PPF' ? 240 : 60)).toFixed(0)}</strong>
                      <small>Horas corroboradas</small>
                    </td>
                    <td>
                      <strong>{item.TotalDocumentos || 0} / {item.DocumentosRequeridos || 0}</strong>
                      <small>{item.DocumentosValidados || 0} validado(s)</small>
                    </td>
                    <td>
                      <div className="practicas-mini-progress">
                        <span style={{ width: `${percentValue(item.Avance)}%` }} />
                      </div>
                      <small>{percentValue(item.Avance).toFixed(2)}%</small>
                    </td>
                    <td>
                      <div className="practicas-row-actions">
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => void openReview(item.ExpedienteId)}
                          disabled={reviewLoading || saving}
                        >
                          Revisar
                        </button>
                        <button type="button" className="ghost-button" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                          Expediente
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={9}>No existen expedientes asignados al responsable para este proceso.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : mode === 'student' ? (
        <section className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <span>Estudiante</span>
            <strong>{isAdmin ? 'Matrícula administrativa' : 'Mis prácticas asignadas'}</strong>
          </div>
          {isAdmin ? (
            <div className="matricula-acad-form practicas-form">
              <label>
                <span>Buscar estudiante</span>
                <input
                  value={eligibilitySearch}
                  onChange={(event) => setEligibilitySearch(event.target.value)}
                  placeholder="Nombre, cédula, carrera o período"
                />
              </label>
              <button type="button" className="secondary-action" onClick={loadAdminEligibility} disabled={loading}>
                Buscar elegibles
              </button>
              <label>
                <span>Estudiante, carrera y período</span>
                <select value={selectedEligibility} onChange={(event) => setSelectedEligibility(event.target.value)}>
                  <option value="">Seleccione una opción</option>
                  {eligibilityOptions.map((item) => {
                    const key = `${item.codigo_estud || ''}|${item.CodigoCarrera || ''}|${item.CodigoPeriodo || ''}`
                    return (
                      <option key={key} value={key} disabled={!item.EsElegible}>
                        {valueOrDash(item.Apellidos_nombre)} · {valueOrDash(item.Cedula_Est)} · {valueOrDash(item.Carrera)} · {valueOrDash(item.NombrePeriodo || item.CodigoPeriodo)} · Semestre {valueOrDash(item.SemestreMaximo)}
                        {item.EsElegible ? '' : ' · no elegible'}
                      </option>
                    )
                  })}
                </select>
              </label>
              <button type="button" className="primary-action" onClick={createExpediente} disabled={saving || loading}>
                {saving ? 'Guardando...' : `Matricular en ${processLabel(selectedProcess)}`}
              </button>
            </div>
          ) : (
            <p className="portal-muted">
              La matrícula de prácticas y vinculación con la sociedad la realiza administración. Desde aquí puedes descargar y subir la carta compromiso cuando tengas un expediente asignado.
            </p>
          )}

          <div className="matricula-table-wrap excel-table-wrap">
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Proceso</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Estado</th>
                  <th>Responsable</th>
                  <th>Carta compromiso</th>
                  <th>Certificado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visibleStudentExpedientes.length ? visibleStudentExpedientes.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente || item.ExpedienteId)}</td>
                    <td>{processLabel(String(item.TipoProcesoCodigo))}</td>
                    <td>{valueOrDash(item.Carrera || item.CodigoCarrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>{valueOrDash(item.DocenteTutor || item.NombreResponsable)}</td>
                    <td>
                      {item.TipoProcesoCodigo === 'PPF' ? (
                        <span className={statusClass(item.CartaCompromisoEstadoCodigo)}>
                          {valueOrDash(item.CartaCompromisoEstado || (item.CartaCompromisoDocumentoId ? 'Cargada' : 'Pendiente'))}
                        </span>
                      ) : 'No aplica'}
                    </td>
                    <td>
                      {item.TipoProcesoCodigo === 'PPF' ? (
                        <span className={statusClass(item.CertificadoEstadoCodigo)}>
                          {valueOrDash(item.CertificadoEstado || (item.CertificadoDocumentoId ? 'Cargado' : 'Pendiente'))}
                        </span>
                      ) : 'No aplica'}
                    </td>
                    <td>
                      <div className="practicas-row-actions">
                        <button type="button" className="secondary-action" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                          Expediente
                        </button>
                        {item.TipoProcesoCodigo === 'PPF' ? (
                          <>
                          <button type="button" className="secondary-action" onClick={() => void downloadCarta(item)} disabled={saving}>
                            Descargar carta
                          </button>
                          <label className="ghost-button practicas-upload-button">
                            Subir firmada
                            <input
                              type="file"
                              accept="application/pdf,.pdf"
                              onChange={(event) => {
                                void uploadCarta(item, event.target.files?.[0] || null)
                                event.currentTarget.value = ''
                              }}
                              disabled={saving}
                            />
                          </label>
                          <label className="ghost-button practicas-upload-button">
                            Subir certificado
                            <input
                              type="file"
                              accept="application/pdf,.pdf,image/png,image/jpeg,.png,.jpg,.jpeg"
                              onChange={(event) => {
                                void uploadCertificado(item, event.target.files?.[0] || null)
                                event.currentTarget.value = ''
                              }}
                              disabled={saving}
                            />
                          </label>
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={9}>No existen expedientes asignados para este proceso.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="student-card student-card--wide matricula-panel practicas-admin-card">
          <div className="section-title">
            <span>Administrador</span>
            <strong>Matricular estudiantes por período</strong>
          </div>

          <p className="portal-muted">
            Seleccione primero el período académico donde está el estudiante, luego el nuevo período de prácticas donde quedará matriculado. Todo se guarda únicamente en la base de prácticas.
          </p>

          <div className="matricula-acad-form practicas-form practicas-responsable-form">
            <label>
              <span>Período académico del estudiante ({periodos.length} período(s))</span>
              <select
                value={selectedSourcePeriod}
                onChange={(event) => {
                  setSelectedSourcePeriod(event.target.value)
                  setSelectedStudents([])
                  setAdminElegibles([])
                }}
              >
                <option value="">Seleccione período origen</option>
                {periodos.map((periodo) => (
                  <option key={`source-${periodo.CodigoPeriodo}`} value={periodo.CodigoPeriodo}>
                    {periodLabel(periodo)} · {periodo.TotalEstudiantes || 0} estudiante(s)
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Nuevo período de prácticas ({periodos.length} período(s))</span>
              <select
                value={selectedPeriod}
                onChange={(event) => {
                  setSelectedPeriod(event.target.value)
                  setSelectedStudents([])
                }}
              >
                <option value="">Seleccione período destino</option>
                {periodos.map((periodo) => (
                  <option key={`target-${periodo.CodigoPeriodo}`} value={periodo.CodigoPeriodo}>
                    {periodLabel(periodo)}
                  </option>
                ))}
              </select>
            </label>
            <div className="practicas-period-detail">
              <strong>Período origen</strong>
              <span>{sourcePeriodDetail ? periodLabel(sourcePeriodDetail) : 'Seleccione período origen'}</span>
              <small>
                Fechas: {valueOrDash(sourcePeriodDetail?.FechaInicio)} a {valueOrDash(sourcePeriodDetail?.FechaFin)} ·
                Registro: {valueOrDash(sourcePeriodDetail?.DetalleRegistro)} ·
                Estado académico: {valueOrDash(sourcePeriodDetail?.EstadoEducativo)} ·
                Estudiantes: {sourcePeriodDetail?.TotalEstudiantes || 0}
              </small>
            </div>
            <div className="practicas-period-detail">
              <strong>Período destino</strong>
              <span>{targetPeriodDetail ? periodLabel(targetPeriodDetail) : 'Seleccione período destino'}</span>
              <small>
                Fechas: {valueOrDash(targetPeriodDetail?.FechaInicio)} a {valueOrDash(targetPeriodDetail?.FechaFin)} ·
                Registro: {valueOrDash(targetPeriodDetail?.DetalleRegistro)} ·
                Estado académico: {valueOrDash(targetPeriodDetail?.EstadoEducativo)} ·
                Nota aprobar: {valueOrDash(targetPeriodDetail?.NotaAprobar)}
              </small>
            </div>
            <label>
              <span>Buscar docente responsable</span>
              <input value={teacherSearch} onChange={(event) => setTeacherSearch(event.target.value)} placeholder="Nombre, cédula o código docente" />
            </label>
            <button type="button" className="secondary-action" onClick={searchTeachers} disabled={loading}>
              Buscar docente
            </button>
            <label>
              <span>Docente seleccionado</span>
              <input value={responsableForm.nombre_responsable} readOnly placeholder="Seleccione un docente del listado" />
            </label>
            <label>
              <span>Cédula</span>
              <input value={responsableForm.cedula_responsable} readOnly />
            </label>
            <label>
              <span>Código docente</span>
              <input value={responsableForm.codigo_docente} readOnly />
            </label>
            <label>
              <span>Rol</span>
              <input value="Responsable" readOnly />
            </label>
            <button type="button" className="primary-action" onClick={saveResponsable} disabled={saving}>
              Matricular estudiantes y asignar docente
            </button>
          </div>
          {teacherOptions.length ? (
            <div className="practicas-teacher-results">
              {teacherOptions.map((teacher) => (
                <button key={`${teacher.codigo_doc}-${teacher.cedula || ''}`} type="button" onClick={() => selectTeacher(teacher)}>
                  <strong>{valueOrDash(teacher.descripcion || teacher.login)}</strong>
                  <span>{valueOrDash(teacher.cedula)} · Código {valueOrDash(teacher.codigo_doc)} · {valueOrDash(teacher.correo || teacher.correo_personal)}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className="practicas-student-picker">
            <div className="practicas-picker-head">
              <strong>Estudiantes a matricular en el período</strong>
              <button type="button" className="secondary-action" onClick={loadAdminEligibility} disabled={loading || !selectedSourcePeriod}>
                Cargar estudiantes
              </button>
              <button type="button" className="ghost-button" onClick={toggleAllStudents} disabled={!adminElegibles.length}>
                {selectedStudents.length === adminElegibles.length && adminElegibles.length ? 'Quitar todos' : 'Seleccionar todos'}
              </button>
            </div>
            <p>{selectedStudents.length} de {adminElegibles.length} estudiante(s) del período origen seleccionados para matricular en el período destino.</p>
            <div className="practicas-student-list">
              {adminElegibles.length ? adminElegibles.map((student) => {
                const code = Number(student.codigo_estud)
                const canEnroll = Boolean(student.PuedeMatricular)
                const hasAuthorization = Boolean(student.TieneAutorizacion || student.AutorizacionId)
                return (
                  <label key={`${student.codigo_estud}-${student.CodigoCarrera}-${student.CodigoPeriodo}`} className={canEnroll ? '' : 'practicas-student-list__blocked'}>
                    <input
                      type="checkbox"
                      checked={selectedStudents.includes(code)}
                      disabled={!canEnroll}
                      onChange={() => toggleStudent(code)}
                    />
                    <span>
                      <b>{valueOrDash(student.Apellidos_nombre)}</b>
                      <small>Cédula: {valueOrDash(student.Cedula_Est)}</small>
                      <small>Carrera: {valueOrDash(student.Carrera)}</small>
                      <small>Período origen: {valueOrDash(student.NombrePeriodo || student.CodigoPeriodo)}</small>
                      <small>Semestre detectado: {valueOrDash(student.SemestreMaximo)}</small>
                      <small>Estado: {canEnroll ? (student.EsElegible ? 'Cumple tercer semestre' : 'Habilitado con autorización') : valueOrDash(student.MotivoElegibilidad || 'No cumple tercer semestre')}</small>
                      {hasAuthorization ? (
                        <small>Autorización: {valueOrDash(student.AutorizacionArchivo || student.AutorizacionId)}</small>
                      ) : null}
                    </span>
                    {!canEnroll ? (
                      <label className="ghost-button practicas-upload-button practicas-authorization-button">
                        Subir autorización
                        <input
                          type="file"
                          accept="application/pdf,.pdf,image/png,image/jpeg,.png,.jpg,.jpeg"
                          onChange={(event) => {
                            void uploadAutorizacion(student, event.target.files?.[0] || null)
                            event.currentTarget.value = ''
                          }}
                          disabled={saving}
                        />
                      </label>
                    ) : null}
                  </label>
                )
              }) : (
                <span className="portal-muted">Seleccione un período y cargue los estudiantes elegibles.</span>
              )}
            </div>
          </div>

          <div className="practicas-period-designations">
              <strong>Matrículas activas por período</strong>
            {periodDesignations.length ? periodDesignations.map((item) => (
              <div key={item.DesignacionId}>
                <span>{valueOrDash(item.CodigoPeriodo)}</span>
                <b>{valueOrDash(item.NombreResponsable)}</b>
                <small>Origen {valueOrDash(item.CodigoPeriodoOrigen || item.PeriodoOrigen)} · Destino {valueOrDash(item.CodigoPeriodo)} · Código docente {valueOrDash(item.CodigoDocente)} · {valueOrDash(item.RolResponsable)} · Cumple: {item.CumpleRequisitos ? 'Sí' : 'No'}</small>
              </div>
            )) : (
              <p>No hay designaciones activas para este proceso.</p>
            )}
          </div>

          <div className="matricula-table-wrap excel-table-wrap">
            <div className="section-title section-title--inline">
              <span>Control</span>
              <strong>Expedientes generados por matrícula</strong>
            </div>
            <table className="matricula-table practicas-table">
              <thead>
                <tr>
                  <th>Expediente</th>
                  <th>Estudiante</th>
                  <th>Carrera</th>
                  <th>Período</th>
                  <th>Estado</th>
                  <th>Responsable</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {expedientes.length ? expedientes.map((item) => (
                  <tr key={item.ExpedienteId}>
                    <td>{valueOrDash(item.CodigoExpediente)}</td>
                    <td>
                      <strong>{valueOrDash(item.Apellidos_nombre)}</strong>
                      <small>{valueOrDash(item.Cedula_Est)}</small>
                    </td>
                    <td>{valueOrDash(item.Carrera || item.CodigoCarrera)}</td>
                    <td>{valueOrDash(item.CodigoPeriodo)}</td>
                    <td><span className={statusClass(item.EstadoCodigo)}>{valueOrDash(item.EstadoExpediente || item.EstadoCodigo)}</span></td>
                    <td>{valueOrDash(item.DocenteTutor || item.NombreResponsable)}</td>
                    <td>
                      <button type="button" className="secondary-action" onClick={() => openDocumentExpedient(item)} disabled={saving}>
                        Expediente
                      </button>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7}>No existen expedientes para el filtro seleccionado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {reviewDetail ? (
        <div className="practicas-expedient-overlay" role="presentation">
          <section className="practicas-review-dialog" role="dialog" aria-modal="true" aria-labelledby="practicas-review-title">
            <header className="practicas-review-dialog__header">
              <div>
                <span>Revisión docente</span>
                <h2 id="practicas-review-title">{valueOrDash(reviewDetail.Apellidos_nombre)}</h2>
                <p>
                  {processLabel(reviewDetail.TipoProcesoCodigo)} · {valueOrDash(reviewDetail.Carrera)} ·
                  período {valueOrDash(reviewDetail.Periodo || reviewDetail.CodigoPeriodo)}
                </p>
              </div>
              <button type="button" className="secondary-action" onClick={closeReview} disabled={reviewLoading}>
                Cerrar
              </button>
            </header>

            <div className="practicas-review-summary">
              <article>
                <span>Expediente</span>
                <strong>{valueOrDash(reviewDetail.CodigoExpediente || reviewDetail.ExpedienteId)}</strong>
              </article>
              <article>
                <span>Estado</span>
                <strong className={statusClass(reviewDetail.EstadoCodigo)}>{valueOrDash(reviewDetail.EstadoExpediente || reviewDetail.EstadoCodigo)}</strong>
              </article>
              <article>
                <span>Horas requeridas</span>
                <strong>{Number(reviewDetail.HorasRequeridas || 0).toFixed(0)}</strong>
              </article>
              <article>
                <span>Documentos</span>
                <strong>{reviewDetail.DocumentosDetalle.filter((item) => item.Cargado).length} / {reviewDetail.DocumentosDetalle.length}</strong>
              </article>
            </div>

            <section className="practicas-review-documents">
              <div className="section-title section-title--inline">
                <span>Corroboración</span>
                <strong>Documentos obligatorios</strong>
              </div>
              <div className="practicas-review-documents__list">
                {reviewDetail.DocumentosDetalle.map((document) => (
                  <article key={document.Codigo} className={document.Cargado ? 'is-loaded' : 'is-missing'}>
                    <div>
                      <strong>{valueOrDash(document.Nombre || document.Codigo)}</strong>
                      <small>{valueOrDash(document.NombreArchivo || 'Sin archivo cargado')}</small>
                    </div>
                    <span className={statusClass(document.Validado ? 'VALIDADO' : document.Cargado ? 'PENDIENTE' : 'RECHAZADO')}>
                      {document.Validado ? 'Validado' : document.Cargado ? 'Por corroborar' : 'Pendiente'}
                    </span>
                    {document.UrlArchivo ? (
                      <a className="ghost-button" href={document.UrlArchivo} target="_blank" rel="noreferrer">
                        Ver
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>

            <div className="practicas-review-form">
              <label>
                <span>Horas verificadas</span>
                <input
                  type="number"
                  min="0"
                  max="10000"
                  step="0.5"
                  value={reviewHours}
                  onChange={(event) => setReviewHours(event.target.value)}
                  disabled={reviewLoading}
                  placeholder={`Mínimo ${reviewDetail.HorasRequeridas}`}
                />
                <small>Se registran como horas reconocidas y de asistencia validadas.</small>
              </label>
              <label>
                <span>Observación o justificación</span>
                <textarea
                  value={reviewObservation}
                  onChange={(event) => setReviewObservation(event.target.value)}
                  disabled={reviewLoading}
                  rows={4}
                  placeholder="Obligatoria al observar o rechazar."
                />
              </label>
              <label className="practicas-review-corroboration">
                <input
                  type="checkbox"
                  checked={reviewCorroborated}
                  onChange={(event) => setReviewCorroborated(event.target.checked)}
                  disabled={reviewLoading}
                />
                <span>Confirmo que revisé los documentos, las horas y la correspondencia del estudiante, carrera y período.</span>
              </label>
            </div>

            {reviewError ? <p className="form-error practicas-review-error">{reviewError}</p> : null}
            <footer className="practicas-review-actions">
              <button type="button" className="ghost-button" onClick={() => void submitReview('OBSERVAR')} disabled={reviewLoading}>
                Observar
              </button>
              <button
                type="button"
                className="secondary-action practicas-review-reject"
                onClick={() => void submitReview('RECHAZAR')}
                disabled={reviewLoading || !reviewDetail.PuedeAprobar}
              >
                Rechazar
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void submitReview('APROBAR')}
                disabled={
                  reviewLoading
                  || !reviewDetail.PuedeAprobar
                  || !reviewDetail.DocumentosCompletos
                  || !reviewCorroborated
                  || Number(reviewHours.replace(',', '.')) < Number(reviewDetail.HorasRequeridas || 0)
                }
              >
                {reviewLoading ? 'Guardando...' : 'Aprobar y habilitar Titulación'}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {documentExpedient ? (
        <div className="practicas-expedient-overlay" role="presentation">
          <div className="practicas-expedient-dialog" role="dialog" aria-modal="true" aria-label="Expediente documental de prácticas">
            <ExpedientesDocumentalesView
              displayName={displayName}
              role={role}
              initialIdentification={documentExpedient.identification}
              moduleFilter={[documentExpedient.process === 'PPF' ? 'PRACTICAS' : 'VINCULACION']}
              embedded
              onClose={() => setDocumentExpedient(null)}
            />
          </div>
        </div>
      ) : null}
    </section>
  )
}
