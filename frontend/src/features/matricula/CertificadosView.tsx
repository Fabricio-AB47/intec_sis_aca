import { Fragment, useEffect, useMemo, useState } from 'react'

import {
  downloadCertificadosPdf,
  downloadCertificadosZip,
  fetchCertificadosCatalog,
  fetchCertificadosStudents,
  previewCertificadoPdf,
} from '../../lib/api'
import type { CertificadosCatalogResponse, CertificadosPeriodOption, CertificadosStudent } from '../../types/app'

type CertificadosViewProps = {
  displayName: string
}

type CertificadoTipo = 'matricula' | 'promocion'
type MatriculaScope = 'ultima' | 'todas'

function valueOrDash(value: string | number | null | undefined): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function periodLabel(period?: CertificadosPeriodOption | null): string {
  if (!period) return '-'
  return period.detalle_periodo || period.cod_periodo || '-'
}

function dateRangeLabel(period?: CertificadosPeriodOption | null): string {
  if (!period) return ''
  const start = period.fecha_inicio || ''
  const end = period.fecha_fin || ''
  if (!start && !end) return ''
  return [start ? `Inicio ${start}` : '', end ? `Fin ${end}` : ''].filter(Boolean).join(' | ')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function certificateSelectionKey(student: CertificadosStudent): string {
  return student.certificado_ref || student.codestud
}

export function CertificadosView({ displayName }: Readonly<CertificadosViewProps>) {
  const [catalog, setCatalog] = useState<CertificadosCatalogResponse | null>(null)
  const [tipoBeca, setTipoBeca] = useState('')
  const [periodo, setPeriodo] = useState('')
  const [proximoPeriodo, setProximoPeriodo] = useState('')
  const [semestre, setSemestre] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [cedulas, setCedulas] = useState('')
  const [matriculaScope, setMatriculaScope] = useState<MatriculaScope>('todas')
  const [students, setStudents] = useState<CertificadosStudent[]>([])
  const [activeCertificateType, setActiveCertificateType] = useState<CertificadoTipo>('matricula')
  const [selectedMatriculaCodes, setSelectedMatriculaCodes] = useState<Set<string>>(new Set())
  const [selectedPromocionCodes, setSelectedPromocionCodes] = useState<Set<string>>(new Set())
  const [expandedCode, setExpandedCode] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [searchLoading, setSearchLoading] = useState(false)
  const [generatingZip, setGeneratingZip] = useState(false)
  const [generatingMassivePdf, setGeneratingMassivePdf] = useState(false)
  const [previewingKey, setPreviewingKey] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const periodos = useMemo(() => catalog?.periodos || [], [catalog?.periodos])
  const selectedBasePeriod = useMemo(
    () => periodos.find((item) => item.cod_periodo === periodo) || null,
    [periodo, periodos],
  )
  const selectedMatriculaPeriod = useMemo(
    () => periodos.find((item) => item.cod_periodo === proximoPeriodo) || selectedBasePeriod,
    [periodos, proximoPeriodo, selectedBasePeriod],
  )
  function generationPeriodFor(student: CertificadosStudent): string {
    return periodo || student.codigo_periodo_matricula || ''
  }

  function canGenerateMatricula(student: CertificadosStudent): boolean {
    return Boolean(certificateSelectionKey(student) && generationPeriodFor(student) && student.puede_generar_matricula)
  }

  function canGeneratePromocion(student: CertificadosStudent): boolean {
    return Boolean(certificateSelectionKey(student) && generationPeriodFor(student) && student.puede_generar_promocion)
  }

  function matriculaBlockReason(student: CertificadosStudent): string {
    return student.motivo_bloqueo_matricula || 'No existe cabecera de matrícula para generar el certificado.'
  }

  const selectableMatriculaStudents = useMemo(
    () => students.filter((student) => Boolean(certificateSelectionKey(student) && (periodo || student.codigo_periodo_matricula || '') && student.puede_generar_matricula)),
    [periodo, students],
  )
  const selectablePromocionStudents = useMemo(
    () => students.filter((student) => Boolean(certificateSelectionKey(student) && (periodo || student.codigo_periodo_matricula || '') && student.puede_generar_promocion)),
    [periodo, students],
  )
  const selectedMatriculaCount = selectedMatriculaCodes.size
  const selectedPromocionCount = selectedPromocionCodes.size
  const activeSelectableStudents =
    activeCertificateType === 'matricula' ? selectableMatriculaStudents : selectablePromocionStudents
  const activeSelectedCodes = activeCertificateType === 'matricula' ? selectedMatriculaCodes : selectedPromocionCodes
  const activeSelectedCount = activeCertificateType === 'matricula' ? selectedMatriculaCount : selectedPromocionCount
  const activeCertificateLabel = activeCertificateType === 'matricula' ? 'matrícula' : 'promoción'
  const activeCertificateTitle =
    activeCertificateType === 'matricula' ? 'Certificado de matrícula' : 'Certificado de promoción'
  const activeCertificateSource =
    activeCertificateType === 'matricula' ? 'Desde CABECERA_MATRICULA' : 'Reporte académico'
  const reprobadasTotal = useMemo(
    () => students.reduce((total, student) => total + (student.reprobadas_count || 0), 0),
    [students],
  )

  async function loadCatalog() {
    setCatalogLoading(true)
    setError('')
    try {
      const payload = await fetchCertificadosCatalog()
      setCatalog(payload)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el modulo de certificados')
    } finally {
      setCatalogLoading(false)
    }
  }

  async function searchStudents() {
    setError('')
    setMessage('')
    setSearchLoading(true)
    setExpandedCode('')
    try {
      const payload = await fetchCertificadosStudents({
        tipoBeca,
        periodo,
        busqueda,
        cedulas,
        matriculaScope,
        semestre,
        limit: 1000,
      })
      const items = payload.items || []
      const shouldAutoSelect = cedulas.trim().length > 0
      setStudents(items)
      setSelectedMatriculaCodes(shouldAutoSelect ? new Set(items.filter(canGenerateMatricula).map(certificateSelectionKey)) : new Set())
      setSelectedPromocionCodes(shouldAutoSelect ? new Set(items.filter(canGeneratePromocion).map(certificateSelectionKey)) : new Set())
      setMessage(`${payload.total || 0} registro(s) encontrados.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar estudiantes')
      setStudents([])
      setSelectedMatriculaCodes(new Set())
      setSelectedPromocionCodes(new Set())
    } finally {
      setSearchLoading(false)
    }
  }

  function toggleStudent(tipo: CertificadoTipo, code: string) {
    const updateSelection = tipo === 'matricula' ? setSelectedMatriculaCodes : setSelectedPromocionCodes
    updateSelection((current) => {
      const next = new Set(current)
      if (next.has(code)) {
        next.delete(code)
      } else {
        next.add(code)
      }
      return next
    })
  }

  function toggleAll(tipo: CertificadoTipo) {
    const selectableCodes =
      tipo === 'matricula'
        ? selectableMatriculaStudents.map((student) => certificateSelectionKey(student))
        : selectablePromocionStudents.map((student) => certificateSelectionKey(student))
    const selectedCodes = tipo === 'matricula' ? selectedMatriculaCodes : selectedPromocionCodes
    const updateSelection = tipo === 'matricula' ? setSelectedMatriculaCodes : setSelectedPromocionCodes
    const allSelected = selectableCodes.length > 0 && selectableCodes.every((code) => selectedCodes.has(code))
    updateSelection(allSelected ? new Set() : new Set(selectableCodes))
  }

  async function generateZip(tipo: CertificadoTipo) {
    setError('')
    setMessage('')
    const selectedCodes = tipo === 'matricula' ? selectedMatriculaCodes : selectedPromocionCodes
    const selectedWithoutPeriod = Array.from(selectedCodes).filter((code) => !periodo && !code.split('|')[2])
    if (selectedCodes.size === 0) {
      setError(`Selecciona al menos un estudiante habilitado para ${tipo === 'matricula' ? 'matrícula' : 'promoción'}.`)
      return
    }
    if (selectedWithoutPeriod.length > 0) {
      setError('Selecciona periodo base o consulta estudiantes que tengan cabecera de matrícula con periodo.')
      return
    }

    setGeneratingZip(true)
    try {
      const payload = {
        tipo_beca: tipoBeca,
        tipo_certificado: tipo,
        periodo,
        proximo_periodo: proximoPeriodo,
        semestre: semestre ? Number(semestre) : null,
        estudiantes: Array.from(selectedCodes),
      }
      const blob = await downloadCertificadosZip(payload)
      downloadBlob(blob, `certificados-${tipo}-individuales-${new Date().toISOString().slice(0, 10)}.zip`)
      setMessage(`ZIP individual de ${tipo === 'matricula' ? 'matrícula' : 'promoción'} generado con ${selectedCodes.size} certificado(s).`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el ZIP')
    } finally {
      setGeneratingZip(false)
    }
  }

  async function generateMassivePdf(tipo: CertificadoTipo) {
    setError('')
    setMessage('')
    const selectedCodes = tipo === 'matricula' ? selectedMatriculaCodes : selectedPromocionCodes
    const selectedWithoutPeriod = Array.from(selectedCodes).filter((code) => !periodo && !code.split('|')[2])
    if (selectedCodes.size === 0) {
      setError(`Selecciona al menos un estudiante habilitado para ${tipo === 'matricula' ? 'matrícula' : 'promoción'}.`)
      return
    }
    if (selectedWithoutPeriod.length > 0) {
      setError('Selecciona periodo base o consulta estudiantes que tengan cabecera de matrícula con periodo.')
      return
    }

    setGeneratingMassivePdf(true)
    try {
      const blob = await downloadCertificadosPdf({
        tipo_beca: tipoBeca,
        tipo_certificado: tipo,
        periodo,
        proximo_periodo: proximoPeriodo,
        semestre: semestre ? Number(semestre) : null,
        estudiantes: Array.from(selectedCodes),
      })
      downloadBlob(blob, `certificados-${tipo}-masivo-${new Date().toISOString().slice(0, 10)}.pdf`)
      setMessage(`PDF masivo de ${tipo === 'matricula' ? 'matrícula' : 'promoción'} generado con ${selectedCodes.size} certificado(s).`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el PDF masivo')
    } finally {
      setGeneratingMassivePdf(false)
    }
  }

  async function previewCertificate(student: CertificadosStudent, tipo: CertificadoTipo) {
    setError('')
    setMessage('')
    const code = student.codestud
    const previewPeriod = generationPeriodFor(student)
    if (!previewPeriod || !code) {
      setError('Selecciona periodo y estudiante para ver el certificado.')
      return
    }
    if (tipo === 'matricula' && !canGenerateMatricula(student)) {
      setError(matriculaBlockReason(student))
      return
    }
    if (tipo === 'promocion' && !canGeneratePromocion(student)) {
      setError('No se puede generar el certificado de promoción: el estudiante tiene materias reprobadas.')
      return
    }

    const previewWindow = window.open('', '_blank')
    const previewKey = `${certificateSelectionKey(student)}-${tipo}`
    setPreviewingKey(previewKey)
    try {
      const blob = await previewCertificadoPdf({
        codestud: code,
        periodo: previewPeriod,
        proximoPeriodo,
        codAnioBasica: student.cod_anio_basica,
        periodoMatricula: student.codigo_periodo_matricula,
        semestre,
        tipo,
      })
      const url = URL.createObjectURL(blob)
      if (previewWindow) {
        previewWindow.location.href = url
      } else {
        downloadBlob(blob, `certificado-${tipo}-${code}.pdf`)
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (apiError) {
      previewWindow?.close()
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir la vista previa')
    } finally {
      setPreviewingKey('')
    }
  }

  useEffect(() => {
    void loadCatalog()
  }, [])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Academico</p>
          <h1>Certificados</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Promocion y matricula</span>
            </div>
          </div>
        </div>
      </header>

      <section className="certificados-overview">
        <article>
          <span>Periodo base</span>
          <strong>{periodLabel(selectedBasePeriod)}</strong>
          <small>{dateRangeLabel(selectedBasePeriod) || 'Pendiente de seleccion'}</small>
        </article>
        <article>
          <span>Periodo de matricula</span>
          <strong>{periodLabel(selectedMatriculaPeriod)}</strong>
          <small>{dateRangeLabel(selectedMatriculaPeriod) || 'Usa el periodo base si queda vacio'}</small>
        </article>
        <article>
          <span>Selección activa</span>
          <strong>{activeSelectedCount}</strong>
          <small>
            {activeCertificateLabel}: {activeSelectableStudents.length} habilitado(s)
          </small>
        </article>
      </section>

      <section className="student-grid student-grid--content certificados-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Filtros</h3>
            <span>{catalogLoading ? 'Cargando catalogo...' : `${periodos.length} periodo(s)`}</span>
          </div>

          <div className="certificados-format-note">
            <strong>Formatos disponibles:</strong>
            <span>
              matrícula descarga un solo PDF con los certificados seleccionados. Gastronomía usa matrícula $100.00 y arancel
              $1000.00; las demás carreras conservan sus valores configurados.
            </span>
          </div>

          <div className="matricula-acad-form certificados-form">
            <label>
              <span>Tipo de beca</span>
              <select value={tipoBeca} onChange={(event) => setTipoBeca(event.target.value)}>
                <option value="">Todos</option>
                {(catalog?.becas || []).map((beca) => (
                  <option key={beca} value={beca}>
                    {beca}
                  </option>
                ))}
                <option value="Sin beca">Sin beca</option>
              </select>
            </label>
            <label>
              <span>Periodo base</span>
              <select value={periodo} onChange={(event) => setPeriodo(event.target.value)}>
                <option value="">Seleccione periodo</option>
                {periodos.map((item) => (
                  <option key={`periodo-${item.cod_periodo}`} value={item.cod_periodo}>
                    {item.detalle_periodo}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Periodo de matricula</span>
              <select value={proximoPeriodo} onChange={(event) => setProximoPeriodo(event.target.value)}>
                <option value="">Usar periodo base</option>
                {periodos.map((item) => (
                  <option key={`proximo-${item.cod_periodo}`} value={item.cod_periodo}>
                    {item.detalle_periodo}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Semestre</span>
              <select value={semestre} onChange={(event) => setSemestre(event.target.value)}>
                <option value="">Calcular automaticamente</option>
                {(catalog?.semestres || []).map((item) => (
                  <option key={`semestre-${item.value}`} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="certificados-field--wide">
              <span>Buscar estudiante</span>
              <input
                value={busqueda}
                onChange={(event) => setBusqueda(event.target.value)}
                placeholder="Nombre, codigo o cedula de estudiante"
              />
            </label>
            <label className="certificados-field--wide">
              <span>Cedulas</span>
              <textarea
                value={cedulas}
                onChange={(event) => setCedulas(event.target.value)}
                placeholder="Ingresa una o varias cedulas, separadas por enter, coma o espacio"
                rows={3}
              />
            </label>
            <label>
              <span>Matrículas</span>
              <select value={matriculaScope} onChange={(event) => setMatriculaScope(event.target.value as MatriculaScope)}>
                <option value="todas">Todas las matrículas</option>
                <option value="ultima">Última matrícula</option>
              </select>
            </label>
          </div>

          <div className="teams-actions certificados-actions">
            <button type="button" onClick={() => void searchStudents()} disabled={searchLoading || catalogLoading}>
              {searchLoading ? 'Consultando...' : 'Consultar estudiantes'}
            </button>
            <button type="button" onClick={() => toggleAll(activeCertificateType)} disabled={activeSelectableStudents.length === 0}>
              {activeSelectedCount > 0 && activeSelectedCount === activeSelectableStudents.length
                ? `Quitar ${activeCertificateLabel}`
                : `Seleccionar ${activeCertificateLabel}`}
            </button>
          </div>

          <div className="certificados-type-selector" role="tablist" aria-label="Tipo de certificado">
            <button
              type="button"
              className={activeCertificateType === 'matricula' ? 'is-active' : ''}
              onClick={() => setActiveCertificateType('matricula')}
              role="tab"
              aria-selected={activeCertificateType === 'matricula'}
            >
              <span>Certificado de matrícula</span>
              <strong>{selectedMatriculaCount} seleccionado(s)</strong>
              <small>Desde CABECERA_MATRICULA</small>
            </button>
            <button
              type="button"
              className={activeCertificateType === 'promocion' ? 'is-active' : ''}
              onClick={() => setActiveCertificateType('promocion')}
              role="tab"
              aria-selected={activeCertificateType === 'promocion'}
            >
              <span>Certificado de promoción</span>
              <strong>{selectedPromocionCount} seleccionado(s)</strong>
              <small>Reporte académico</small>
            </button>
          </div>

          <div className="certificados-active-panel">
            <div>
              <span>{activeCertificateTitle}</span>
              <strong>{activeSelectedCount} seleccionado(s)</strong>
              <small>{activeCertificateSource}</small>
            </div>
            <div className="certificados-active-panel__actions">
              <button
                type="button"
                onClick={() => void generateZip(activeCertificateType)}
                disabled={generatingZip || activeSelectedCount === 0}
              >
                {generatingZip ? 'Generando ZIP...' : 'Generar ZIP individuales'}
              </button>
              <button
                type="button"
                onClick={() => void generateMassivePdf(activeCertificateType)}
                disabled={generatingMassivePdf || activeSelectedCount === 0}
              >
                {generatingMassivePdf ? 'Generando PDF...' : 'Generar PDF masivo'}
              </button>
            </div>
          </div>

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </article>

        <article className="student-card student-card--wide certificados-results-card">
          <div className="card-head">
            <h3>Estudiantes</h3>
            <span>
              {students.length} resultado(s) | {reprobadasTotal} reprobada(s)
            </span>
          </div>

          <div className="certificados-selection-strip">
            <label>
              <input
                type="checkbox"
                checked={activeSelectableStudents.length > 0 && activeSelectedCount === activeSelectableStudents.length}
                onChange={() => toggleAll(activeCertificateType)}
                disabled={activeSelectableStudents.length === 0}
              />
              <span>Seleccionar {activeCertificateLabel} habilitada</span>
            </label>
            <strong>
              {activeSelectedCount} seleccionado(s) | {activeSelectableStudents.length} habilitado(s)
            </strong>
          </div>

          <div className="matricula-table-wrap excel-table-wrap certificados-table-wrap">
            <table className="matricula-table certificados-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Codigo</th>
                  <th>Estudiante</th>
                  <th>Cabecera matrícula</th>
                  <th>Correos</th>
                  <th>Estado</th>
                  <th>Reprobadas</th>
                  <th>Certificados</th>
                </tr>
              </thead>
              <tbody>
                {students.length > 0 ? (
                  students.map((student) => {
                    const code = student.codestud
                    const selectionKey = certificateSelectionKey(student)
                    const details = student.reprobadas_detalle || []
                    const matriculaDisabled = !canGenerateMatricula(student)
                    const promocionDisabled = !canGeneratePromocion(student)
                    const activeDisabled = activeCertificateType === 'matricula' ? matriculaDisabled : promocionDisabled
                    const activePreviewKey = `${selectionKey}-${activeCertificateType}`
                    const hasPeriod = Boolean(generationPeriodFor(student))
                    return (
                      <Fragment key={`cert-fragment-${selectionKey || student.nombres}`}>
                        <tr key={`cert-row-${selectionKey || student.nombres}`}>
                          <td>
                            <input
                              type="checkbox"
                              checked={activeSelectedCodes.has(selectionKey)}
                              disabled={activeDisabled}
                              onChange={() => toggleStudent(activeCertificateType, selectionKey)}
                            />
                          </td>
                          <td>{valueOrDash(code)}</td>
                          <td>
                            <strong>{valueOrDash(student.nombres)}</strong>
                            {!hasPeriod ? <small>Selecciona periodo o consulta una cédula con cabecera de matrícula</small> : null}
                            {activeCertificateType === 'promocion' && hasPeriod && details.length > 0 ? (
                              <small>Promoción bloqueada por materias reprobadas</small>
                            ) : null}
                            {hasPeriod && details.length === 0 && !student.codigo_periodo_matricula ? (
                              <small>Sin cabecera de matrícula para generar</small>
                            ) : null}
                            {activeCertificateType === 'matricula' && matriculaDisabled ? (
                              <small>{matriculaBlockReason(student)}</small>
                            ) : null}
                          </td>
                          <td>
                            <span>{valueOrDash(student.carrera)}</span>
                            <small>
                              {valueOrDash(student.periodo_matricula || student.codigo_periodo_matricula)} | Matr.{' '}
                              {valueOrDash(student.num_matricula)}
                            </small>
                          </td>
                          <td>
                            <span>{valueOrDash(student.correo_intec)}</span>
                            <small>{valueOrDash(student.correo_personal)}</small>
                          </td>
                          <td>{valueOrDash(student.estado)}</td>
                          <td>
                            <button
                              type="button"
                              className={details.length > 0 ? 'certificados-badge certificados-badge--warn' : 'certificados-badge'}
                              onClick={() => setExpandedCode(expandedCode === code ? '' : code)}
                              disabled={details.length === 0}
                            >
                              {student.reprobadas_count || 0}
                            </button>
                          </td>
                          <td>
                            <div className="certificados-preview-actions">
                              <button
                                type="button"
                                className="reporteria-row-action"
                                onClick={() => void previewCertificate(student, activeCertificateType)}
                                disabled={activeDisabled || !code || previewingKey === activePreviewKey}
                              >
                                {previewingKey === activePreviewKey
                                  ? 'Abriendo...'
                                  : activeCertificateType === 'matricula'
                                    ? 'Matrícula'
                                    : 'Promoción'}
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedCode === code ? (
                          <tr key={`cert-detail-${selectionKey || student.nombres}`} className="certificados-detail-row">
                            <td colSpan={8}>
                              <div className="certificados-detail-list">
                                {details.map((detail, index) => (
                                  <span key={`${code}-rep-${detail.codigo_materia || index}`}>
                                    <strong>{valueOrDash(detail.cod_materia || detail.codigo_materia)}</strong>
                                    <em>{valueOrDash(detail.nombre)}</em>
                                    <small>Nota {valueOrDash(detail.promedioFinal)}</small>
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={8}>{searchLoading ? 'Consultando...' : 'Usa los filtros para consultar estudiantes.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </>
  )
}
