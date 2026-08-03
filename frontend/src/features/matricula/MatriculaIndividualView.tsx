import { useEffect, useMemo, useState } from 'react'

import {
  fetchAcademicEnrollmentCatalog,
  fetchAcademicEnrollmentDetail,
  fetchAcademicEnrollmentPensum,
  previewAcademicEnrollment,
  saveAcademicEnrollment,
  searchAcademicEnrollmentStudents,
} from '../../lib/api'
import type {
  AcademicCareerOption,
  AcademicEnrollmentPayload,
  AcademicEnrollmentPreviewResponse,
  AcademicEnrollmentSubject,
  AcademicEnrollmentStudent,
  AcademicPeriodOption,
  MatriculaTipo,
  PreinscriptionProcessOption,
} from '../../types/app'

type MatriculaIndividualViewProps = {
  displayName: string
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function numberValue(value: string, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function subjectCode(subject: AcademicEnrollmentSubject): number {
  return Number(subject.codigo_materia)
}

function actionLabel(action?: string): string {
  const normalized = String(action || '').toUpperCase()
  if (normalized === 'INSERTAR') return 'Lista para matricular'
  if (normalized === 'EXISTENTE') return 'Ya matriculada'
  if (normalized === 'EXCEPCION_PRERREQUISITO') return 'Matrícula permitida'
  if (normalized === 'BLOQUEADA_PRERREQUISITO') return 'Prerrequisito pendiente'
  if (normalized === 'BLOQUEADA_NOTAS') return 'Bloqueada por notas'
  if (normalized === 'REMOVER') return 'Se retirará'
  return action ? action.replaceAll('_', ' ') : 'Pendiente de validación'
}

export function MatriculaIndividualView({
  displayName,
}: Readonly<MatriculaIndividualViewProps>) {
  const [careers, setCareers] = useState<AcademicCareerOption[]>([])
  const [periods, setPeriods] = useState<AcademicPeriodOption[]>([])
  const [journeys, setJourneys] = useState<PreinscriptionProcessOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')

  const [query, setQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [results, setResults] = useState<AcademicEnrollmentStudent[]>([])
  const [student, setStudent] = useState<AcademicEnrollmentStudent | null>(null)

  const [careerCode, setCareerCode] = useState('')
  const [periodCode, setPeriodCode] = useState('')
  const [pensum, setPensum] = useState<AcademicEnrollmentSubject[]>([])
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [workspaceError, setWorkspaceError] = useState('')
  const [selectedCodes, setSelectedCodes] = useState<number[]>([])
  const [semester, setSemester] = useState('ALL')

  const [parallel, setParallel] = useState('A')
  const [groupNumber, setGroupNumber] = useState('1')
  const [enrollmentType, setEnrollmentType] = useState<MatriculaTipo>('R')
  const [controlMatricula, setControlMatricula] = useState('1')
  const [journeyCode, setJourneyCode] = useState('1')
  const [inscriptionValue, setInscriptionValue] = useState('0')
  const [enrollmentValue, setEnrollmentValue] = useState('0')
  const [totalValue, setTotalValue] = useState('0')
  const [paymentDate, setPaymentDate] = useState('')

  const [preview, setPreview] = useState<AcademicEnrollmentPreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [exceptionCodes, setExceptionCodes] = useState<number[]>([])
  const [exceptionReason, setExceptionReason] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      setCatalogError('')
      try {
        const response = await fetchAcademicEnrollmentCatalog()
        if (cancelled) return
        setCareers(response.carreras || [])
        setPeriods(response.periodos || [])
        setJourneys(response.jornadas || [])
        setJourneyCode(response.jornadas?.[0]?.value || '1')
      } catch (error) {
        if (!cancelled) setCatalogError(errorMessage(error, 'No se pudo cargar el catálogo académico.'))
      } finally {
        if (!cancelled) setCatalogLoading(false)
      }
    }

    void loadCatalog()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!student || !careerCode || !periodCode) {
      setPensum([])
      setSelectedCodes([])
      return
    }

    let cancelled = false
    const studentCode = student.codigo_estud
    async function loadWorkspace() {
      setWorkspaceLoading(true)
      setWorkspaceError('')
      setPreview(null)
      setExceptionCodes([])
      try {
        const [detailResponse, pensumResponse] = await Promise.all([
          fetchAcademicEnrollmentDetail(studentCode, careerCode, periodCode),
          fetchAcademicEnrollmentPensum(careerCode),
        ])
        if (cancelled) return
        setPensum(pensumResponse.items || [])
        setSelectedCodes(
          (detailResponse.materias_actuales || [])
            .map((subject) => Number(subject.codigo_materia))
            .filter(Number.isFinite),
        )
        const currentHeader = (detailResponse.cabeceras || []).find(
          (item) => item.cod_anio_basica === careerCode && item.codigo_periodo === periodCode,
        )
        if (currentHeader) {
          setJourneyCode(String(currentHeader.cod_jornada || 1))
          setControlMatricula(String(currentHeader.control_matricula || 1))
          setInscriptionValue(String(currentHeader.inscrip_valor || 0))
          setEnrollmentValue(String(currentHeader.matri_valor || 0))
          setTotalValue(String(currentHeader.valor || 0))
          setPaymentDate(currentHeader.fecha_pago || '')
        }
      } catch (error) {
        if (!cancelled) setWorkspaceError(errorMessage(error, 'No se pudo cargar la matrícula del estudiante.'))
      } finally {
        if (!cancelled) setWorkspaceLoading(false)
      }
    }

    void loadWorkspace()
    return () => {
      cancelled = true
    }
  }, [careerCode, periodCode, student])

  const semesters = useMemo(
    () => [...new Set(pensum.map((subject) => subject.semestre).filter((value) => value !== null && value !== undefined))]
      .sort((left, right) => Number(left) - Number(right)),
    [pensum],
  )
  const visibleSubjects = useMemo(
    () => pensum.filter((subject) => semester === 'ALL' || String(subject.semestre) === semester),
    [pensum, semester],
  )
  const previewByCode = useMemo(
    () => new Map((preview?.items || []).map((item) => [Number(item.codigo_materia), item])),
    [preview],
  )
  const blockedPrerequisites = Number(preview?.summary?.bloqueadas_por_prerrequisito || 0)
  const selectedCareer = careers.find((career) => career.cod_anio_basica === careerCode)
  const selectedPeriod = periods.find((period) => period.codigo_periodo === periodCode)

  async function searchStudents() {
    const normalized = query.trim()
    if (normalized.length < 2) {
      setSearchError('Ingrese al menos dos caracteres del nombre, cédula o código.')
      setResults([])
      return
    }
    setSearchLoading(true)
    setSearchError('')
    try {
      const response = await searchAcademicEnrollmentStudents(normalized, 50)
      setResults(response.items || [])
      if (!(response.items || []).length) setSearchError('No se encontraron estudiantes con ese criterio.')
    } catch (error) {
      setSearchError(errorMessage(error, 'No se pudo buscar estudiantes.'))
      setResults([])
    } finally {
      setSearchLoading(false)
    }
  }

  function chooseStudent(selected: AcademicEnrollmentStudent) {
    const suggestedCareer = careers.some((career) => career.cod_anio_basica === selected.cod_anio_basica_actual)
      ? String(selected.cod_anio_basica_actual)
      : careers[0]?.cod_anio_basica || ''
    const suggestedPeriod = periods.some((period) => period.codigo_periodo === selected.periodo_actual)
      ? String(selected.periodo_actual)
      : periods[0]?.codigo_periodo || ''
    setStudent(selected)
    setCareerCode(suggestedCareer)
    setPeriodCode(suggestedPeriod)
    setResults([])
    setQuery(selected.nombre_estudiante)
    setSearchError('')
    setActionError('')
    setActionMessage('')
  }

  function toggleSubject(code: number) {
    setSelectedCodes((current) => (
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code].sort((left, right) => left - right)
    ))
    setExceptionCodes((current) => current.filter((item) => item !== code))
    setPreview(null)
    setActionMessage('')
  }

  function buildPayload(): AcademicEnrollmentPayload | null {
    if (!student || !careerCode || !periodCode) {
      setActionError('Seleccione estudiante, carrera y período.')
      return null
    }
    if (!selectedCodes.length) {
      setActionError('Seleccione al menos una materia.')
      return null
    }
    if (exceptionCodes.length > 0 && exceptionReason.trim().length < 10) {
      setActionError('El desbloqueo requiere una justificación de al menos 10 caracteres.')
      return null
    }
    return {
      codigo_estud: numberValue(student.codigo_estud),
      cod_anio_basica: numberValue(careerCode),
      codigo_periodo: numberValue(periodCode),
      materia_codes: selectedCodes,
      paralelo: parallel.trim().toUpperCase() || 'A',
      num_grupo: numberValue(groupNumber, 1),
      tipo_matricula: enrollmentType,
      control_matricula: numberValue(controlMatricula, 1),
      cod_jornada: numberValue(journeyCode, 1),
      inscrip_valor: numberValue(inscriptionValue),
      matri_valor: numberValue(enrollmentValue),
      valor: numberValue(totalValue),
      fecha_pago: paymentDate || null,
      remove_unselected: false,
      prerequisite_exception_codes: exceptionCodes,
      prerequisite_exception_reason: exceptionReason.trim() || null,
    }
  }

  async function validateEnrollment() {
    const payload = buildPayload()
    if (!payload) return
    setPreviewLoading(true)
    setActionError('')
    setActionMessage('')
    try {
      const response = await previewAcademicEnrollment(payload)
      setPreview(response)
      setActionMessage(
        Number(response.summary?.bloqueadas_por_prerrequisito || 0) > 0
          ? 'La validación encontró materias con prerrequisitos pendientes.'
          : 'Matrícula validada. Puede guardar los cambios.',
      )
    } catch (error) {
      setActionError(errorMessage(error, 'No se pudo validar la matrícula.'))
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  function authorizeException(code: number) {
    if (exceptionReason.trim().length < 10) {
      setActionError('Escriba primero una justificación de al menos 10 caracteres.')
      return
    }
    setExceptionCodes((current) => current.includes(code) ? current : [...current, code])
    setPreview(null)
    setActionError('')
    setActionMessage('Matrícula desbloqueada para esta materia. Vuelva a validar antes de guardar.')
  }

  async function saveEnrollment() {
    const payload = buildPayload()
    if (!payload) return
    setSaveLoading(true)
    setActionError('')
    try {
      const response = await saveAcademicEnrollment(payload)
      setConfirmOpen(false)
      setActionMessage(response.message || 'Matrícula guardada correctamente.')
      setPreview(response.preview || null)
      const refreshed = await fetchAcademicEnrollmentDetail(student!.codigo_estud, careerCode, periodCode)
      setSelectedCodes(
        (refreshed.materias_actuales || [])
          .map((subject) => Number(subject.codigo_materia))
          .filter(Number.isFinite),
      )
    } catch (error) {
      setActionError(errorMessage(error, 'No se pudo guardar la matrícula.'))
      setConfirmOpen(false)
    } finally {
      setSaveLoading(false)
    }
  }

  return (
    <div className="report-page matricula-individual-page">
      <header className="report-header matricula-individual-header">
        <div>
          <span>MATRICULACIÓN</span>
          <h1>Matrícula individual</h1>
          <p>Busque al estudiante por nombre, cédula o código y registre las materias de su período.</p>
        </div>
        <div className="report-user-card">
          <strong>{displayName}</strong>
          <span>Matrícula</span>
        </div>
      </header>

      {catalogError ? <div className="inline-error">{catalogError}</div> : null}

      <section className="student-card student-card--wide matricula-individual-search">
        <div className="student-card-heading">
          <div>
            <span>Paso 1</span>
            <h2>Buscar estudiante</h2>
          </div>
          <small>{student ? 'Estudiante seleccionado' : 'Nombre, cédula o código'}</small>
        </div>
        <div className="matricula-individual-searchbar">
          <label>
            Estudiante
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setSearchError('')
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void searchStudents()
              }}
              placeholder="Escriba nombre, apellido, cédula o código"
            />
          </label>
          <button type="button" className="primary-action" onClick={() => void searchStudents()} disabled={searchLoading}>
            {searchLoading ? 'Buscando...' : 'Buscar'}
          </button>
        </div>
        {searchError ? <div className="inline-error">{searchError}</div> : null}
        {results.length > 0 ? (
          <div className="matricula-student-results">
            {results.map((item) => (
              <button key={item.codigo_estud} type="button" onClick={() => chooseStudent(item)}>
                <span>
                  <strong>{item.nombre_estudiante}</strong>
                  <small>{item.cedula || 'Sin identificación'} · Código {item.codigo_estud}</small>
                </span>
                <span>
                  <strong>{item.carrera_actual || 'Sin carrera vigente'}</strong>
                  <small>{item.detalle_periodo_actual || 'Sin período vigente'}</small>
                </span>
                <b>Seleccionar</b>
              </button>
            ))}
          </div>
        ) : null}
      </section>

      {student ? (
        <>
          <section className="student-card student-card--wide matricula-individual-context">
            <div className="student-card-heading">
              <div>
                <span>Paso 2</span>
                <h2>Definir carrera y período</h2>
              </div>
              <small>{student.estado_codigo || 'Estado no informado'}</small>
            </div>
            <div className="matricula-student-summary">
              <div><span>Estudiante</span><strong>{student.nombre_estudiante}</strong></div>
              <div><span>Cédula</span><strong>{student.cedula || '-'}</strong></div>
              <div><span>Carrera actual</span><strong>{student.carrera_actual || '-'}</strong></div>
              <div><span>Período actual</span><strong>{student.detalle_periodo_actual || '-'}</strong></div>
            </div>
            <div className="matricula-individual-form-grid">
              <label>
                Carrera a matricular
                <select value={careerCode} onChange={(event) => setCareerCode(event.target.value)} disabled={catalogLoading}>
                  <option value="">Seleccione una carrera</option>
                  {careers.map((career) => (
                    <option key={career.cod_anio_basica} value={career.cod_anio_basica}>{career.nombre_basica}</option>
                  ))}
                </select>
              </label>
              <label>
                Período destino
                <select value={periodCode} onChange={(event) => setPeriodCode(event.target.value)} disabled={catalogLoading}>
                  <option value="">Seleccione un período</option>
                  {periods.map((period) => (
                    <option key={period.codigo_periodo} value={period.codigo_periodo}>{period.detalle_periodo}</option>
                  ))}
                </select>
              </label>
              <label>
                Paralelo
                <input value={parallel} maxLength={20} onChange={(event) => setParallel(event.target.value)} />
              </label>
              <label>
                Grupo
                <input type="number" min="1" value={groupNumber} onChange={(event) => setGroupNumber(event.target.value)} />
              </label>
              <label>
                Tipo de matrícula
                <select value={enrollmentType} onChange={(event) => setEnrollmentType(event.target.value as MatriculaTipo)}>
                  <option value="R">Regular</option>
                  <option value="H">Homologación</option>
                  <option value="E">Especial</option>
                </select>
              </label>
              <label>
                Jornada
                <select value={journeyCode} onChange={(event) => setJourneyCode(event.target.value)}>
                  {journeys.map((journey) => <option key={journey.value} value={journey.value}>{journey.label}</option>)}
                </select>
              </label>
              <label>
                Control de matrícula
                <input type="number" min="0" value={controlMatricula} onChange={(event) => setControlMatricula(event.target.value)} />
              </label>
              <label>
                Fecha de pago
                <input type="date" value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} />
              </label>
              <label>
                Inscripción
                <input type="number" min="0" step="0.01" value={inscriptionValue} onChange={(event) => setInscriptionValue(event.target.value)} />
              </label>
              <label>
                Matrícula
                <input type="number" min="0" step="0.01" value={enrollmentValue} onChange={(event) => setEnrollmentValue(event.target.value)} />
              </label>
              <label>
                Valor total
                <input type="number" min="0" step="0.01" value={totalValue} onChange={(event) => setTotalValue(event.target.value)} />
              </label>
            </div>
          </section>

          <section className="student-card student-card--wide matricula-individual-subjects">
            <div className="student-card-heading">
              <div>
                <span>Paso 3</span>
                <h2>Seleccionar materias</h2>
              </div>
              <small>{selectedCodes.length} seleccionada(s)</small>
            </div>
            <div className="matricula-subject-toolbar">
              <label>
                Nivel
                <select value={semester} onChange={(event) => setSemester(event.target.value)}>
                  <option value="ALL">Todos los niveles</option>
                  {semesters.map((value) => <option key={String(value)} value={String(value)}>Nivel {value}</option>)}
                </select>
              </label>
              <div>
                <button type="button" className="ghost-button" onClick={() => setSelectedCodes(pensum.map(subjectCode).filter(Number.isFinite))}>
                  Seleccionar pensum
                </button>
                <button type="button" className="ghost-button" onClick={() => { setSelectedCodes([]); setExceptionCodes([]); setPreview(null) }}>
                  Limpiar
                </button>
              </div>
            </div>
            {workspaceError ? <div className="inline-error">{workspaceError}</div> : null}
            {workspaceLoading ? <div className="empty-state">Cargando pensum y matrícula vigente...</div> : (
              <div className="matricula-table-wrap">
                <table className="matricula-table matricula-prerequisite-table">
                  <thead>
                    <tr>
                      <th>Seleccionar</th>
                      <th>Nivel</th>
                      <th>Código</th>
                      <th>Materia</th>
                      <th>Créditos</th>
                      <th>Validación</th>
                      <th>Control</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleSubjects.map((subject) => {
                      const code = subjectCode(subject)
                      const validation = previewByCode.get(code)
                      const action = String(validation?.accion || '')
                      const blocked = action === 'BLOQUEADA_PRERREQUISITO'
                      const excepted = action === 'EXCEPCION_PRERREQUISITO' || exceptionCodes.includes(code)
                      return (
                        <tr key={subject.codigo_materia} className={blocked ? 'matricula-subject-row--blocked' : excepted ? 'matricula-subject-row--excepted' : ''}>
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedCodes.includes(code)}
                              onChange={() => toggleSubject(code)}
                              aria-label={`Seleccionar ${subject.nombre_materia}`}
                            />
                          </td>
                          <td>{subject.semestre || '-'}</td>
                          <td><strong>{subject.cod_materia || subject.codigo_materia}</strong></td>
                          <td>{subject.nombre_materia}</td>
                          <td>{subject.creditos ?? '-'}</td>
                          <td>
                            <span className={`matricula-validation-badge matricula-validation-badge--${action.toLowerCase() || 'pending'}`}>
                              {actionLabel(action)}
                            </span>
                            {validation?.materias_previas?.length ? (
                              <small>Requiere: {validation.materias_previas.join(', ')}</small>
                            ) : null}
                          </td>
                          <td>
                            {blocked && !excepted ? (
                              <button type="button" className="ghost-button" onClick={() => authorizeException(code)}>
                                Permitir matrícula
                              </button>
                            ) : null}
                            {excepted ? (
                              <button type="button" className="ghost-button" onClick={() => { setExceptionCodes((current) => current.filter((item) => item !== code)); setPreview(null) }}>
                                Revocar permiso
                              </button>
                            ) : null}
                          </td>
                        </tr>
                      )
                    })}
                    {!visibleSubjects.length ? <tr><td colSpan={7}>No hay materias en el pensum seleccionado.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {blockedPrerequisites > 0 || exceptionCodes.length > 0 ? (
            <section className="student-card student-card--wide matricula-exception-panel">
              <div className="student-card-heading">
                <div><span>Autorización individual</span><h2>Desbloquear matrícula</h2></div>
                <small>{exceptionCodes.length} materia(s) permitida(s)</small>
              </div>
              <label>
                Motivo obligatorio
                <textarea
                  value={exceptionReason}
                  onChange={(event) => { setExceptionReason(event.target.value); setPreview(null) }}
                  rows={3}
                  maxLength={1000}
                  placeholder="Explique por qué se permite matricular la materia sin cumplir el prerrequisito."
                />
              </label>
              <p>El permiso se aplica solo a este estudiante y queda auditado con período, materia, usuario y fecha.</p>
            </section>
          ) : null}

          <section className="student-card student-card--wide matricula-individual-review">
            <div className="student-card-heading">
              <div><span>Paso 4</span><h2>Validar y guardar</h2></div>
              <small>{selectedCareer?.nombre_basica || '-'} · {selectedPeriod?.detalle_periodo || '-'}</small>
            </div>
            {preview ? (
              <div className="matricula-preview-summary">
                <div><span>Seleccionadas</span><strong>{preview.summary?.seleccionadas || 0}</strong></div>
                <div><span>Por insertar</span><strong>{preview.summary?.insertar || 0}</strong></div>
                <div><span>Existentes</span><strong>{preview.summary?.existentes || 0}</strong></div>
                <div><span>Bloqueadas</span><strong>{blockedPrerequisites}</strong></div>
                <div><span>Permisos</span><strong>{preview.summary?.excepciones_prerrequisito || 0}</strong></div>
              </div>
            ) : <p>Ejecute la validación para revisar duplicados, prerrequisitos y permisos antes de guardar.</p>}
            {actionError ? <div className="inline-error">{actionError}</div> : null}
            {actionMessage ? <div className="inline-success">{actionMessage}</div> : null}
            <div className="matricula-individual-actions">
              <button type="button" className="ghost-button" onClick={() => void validateEnrollment()} disabled={previewLoading || workspaceLoading}>
                {previewLoading ? 'Validando...' : 'Validar matrícula'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => setConfirmOpen(true)}
                disabled={!preview || blockedPrerequisites > 0 || saveLoading}
              >
                Guardar matrícula
              </button>
            </div>
          </section>
        </>
      ) : null}

      {confirmOpen ? (
        <div className="matricula-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-enrollment-title">
          <div className="matricula-confirm-modal">
            <div>
              <span>Confirmación</span>
              <h2 id="confirm-enrollment-title">Guardar matrícula</h2>
              <p>Se registrarán las materias validadas de {student?.nombre_estudiante}. Esta operación quedará asociada al usuario actual.</p>
            </div>
            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setConfirmOpen(false)} disabled={saveLoading}>Cancelar</button>
              <button type="button" className="primary-action" onClick={() => void saveEnrollment()} disabled={saveLoading}>
                {saveLoading ? 'Guardando...' : 'Confirmar matrícula'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
