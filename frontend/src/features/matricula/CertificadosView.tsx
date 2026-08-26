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

function normalizeSearch(value: string | number | null | undefined): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-EC')
    .trim()
}

export function CertificadosView({ displayName }: Readonly<CertificadosViewProps>) {
  const [catalog, setCatalog] = useState<CertificadosCatalogResponse | null>(null)
  const [periodo, setPeriodo] = useState('')
  const [busqueda, setBusqueda] = useState('')
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

  const visibleStudents = useMemo(() => {
    const term = normalizeSearch(busqueda)
    if (!term) return students
    return students.filter((student) =>
      [student.nombres, student.codestud, student.carrera, student.num_matricula].some((value) =>
        normalizeSearch(value).includes(term),
      ),
    )
  }, [busqueda, students])

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
    () => visibleStudents.filter((student) => Boolean(certificateSelectionKey(student) && (periodo || student.codigo_periodo_matricula || '') && student.puede_generar_matricula)),
    [periodo, visibleStudents],
  )
  const selectablePromocionStudents = useMemo(
    () => visibleStudents.filter((student) => Boolean(certificateSelectionKey(student) && (periodo || student.codigo_periodo_matricula || '') && student.puede_generar_promocion)),
    [periodo, visibleStudents],
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
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el módulo de certificados')
    } finally {
      setCatalogLoading(false)
    }
  }

  async function searchStudents() {
    setError('')
    setMessage('')
    if (!periodo) {
      setError('Seleccione un período académico para cargar sus estudiantes matriculados.')
      return
    }
    setSearchLoading(true)
    setExpandedCode('')
    try {
      const payload = await fetchCertificadosStudents({
        periodo,
        limit: 1000,
      })
      const items = payload.items || []
      setStudents(items)
      setSelectedMatriculaCodes(new Set())
      setSelectedPromocionCodes(new Set())
      setMessage(`${payload.total || 0} estudiante(s) matriculado(s) en el período seleccionado.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar estudiantes')
      setStudents([])
      setSelectedMatriculaCodes(new Set())
      setSelectedPromocionCodes(new Set())
    } finally {
      setSearchLoading(false)
    }
  }

  function changePeriod(nextPeriod: string) {
    setPeriodo(nextPeriod)
    setBusqueda('')
    setStudents([])
    setSelectedMatriculaCodes(new Set())
    setSelectedPromocionCodes(new Set())
    setExpandedCode('')
    setMessage('')
    setError('')
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
    if (!periodo) {
      setError('Seleccione el período académico antes de generar certificados.')
      return
    }
    if (selectedCodes.size === 0) {
      setError(`Selecciona al menos un estudiante habilitado para ${tipo === 'matricula' ? 'matrícula' : 'promoción'}.`)
      return
    }

    setGeneratingZip(true)
    try {
      const payload = {
        tipo_certificado: tipo,
        periodo,
        proximo_periodo: periodo,
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
    if (!periodo) {
      setError('Seleccione el período académico antes de generar certificados.')
      return
    }
    if (selectedCodes.size === 0) {
      setError(`Selecciona al menos un estudiante habilitado para ${tipo === 'matricula' ? 'matrícula' : 'promoción'}.`)
      return
    }

    setGeneratingMassivePdf(true)
    try {
      const blob = await downloadCertificadosPdf({
        tipo_certificado: tipo,
        periodo,
        proximo_periodo: periodo,
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
      setError('Seleccione período y estudiante para ver el certificado.')
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
        proximoPeriodo: periodo,
        codAnioBasica: student.cod_anio_basica,
        periodoMatricula: student.codigo_periodo_matricula,
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
          <p className="eyebrow">Académico</p>
          <h1>Certificados por período</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Generación automática por período</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content certificados-grid">
        <article className="student-card student-card--wide certificados-period-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Paso 1</p>
              <h3>Seleccionar el período académico</h3>
            </div>
            <span>{catalogLoading ? 'Cargando catálogo...' : `${periodos.length} período(s)`}</span>
          </div>

          <div className="certificados-format-note">
            <strong>Generación desde el sistema:</strong>
            <span>
              El período seleccionado determina los estudiantes matriculados. Luego podrá generar, por separado, certificados
              de matrícula o de promoción. Este proceso no utiliza archivos de Excel.
            </span>
          </div>

          <div className="certificados-period-search">
            <label>
              <span>Período académico</span>
              <select value={periodo} onChange={(event) => changePeriod(event.target.value)}>
                <option value="">Seleccione un período</option>
                {periodos.map((item) => (
                  <option key={`periodo-${item.cod_periodo}`} value={item.cod_periodo}>
                    {item.detalle_periodo}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => void searchStudents()} disabled={searchLoading || catalogLoading || !periodo}>
              {searchLoading ? 'Cargando matrículas...' : 'Cargar estudiantes matriculados'}
            </button>
          </div>

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </article>
      </section>

      <section className="certificados-overview">
        <article>
          <span>Período seleccionado</span>
          <strong>{periodLabel(selectedBasePeriod)}</strong>
          <small>{dateRangeLabel(selectedBasePeriod) || 'Pendiente de selección'}</small>
        </article>
        <article>
          <span>Estudiantes matriculados</span>
          <strong>{students.length}</strong>
          <small>{busqueda ? `${visibleStudents.length} visible(s) por el filtro` : 'Una fila por matrícula encontrada'}</small>
        </article>
        <article>
          <span>Tipo de certificado</span>
          <strong>{activeCertificateTitle}</strong>
          <small>{activeSelectedCount} estudiante(s) seleccionado(s)</small>
        </article>
      </section>

      <section className="student-grid student-grid--content certificados-grid">
        <article className="student-card student-card--wide certificados-results-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Pasos 2 y 3</p>
              <h3>Elegir certificado y estudiantes</h3>
            </div>
            <span>
              {visibleStudents.length} visible(s) | {reprobadasTotal} materia(s) reprobada(s)
            </span>
          </div>

          <div className="certificados-type-selector certificados-type-selector--compact" role="tablist" aria-label="Tipo de certificado">
            <button
              type="button"
              className={activeCertificateType === 'matricula' ? 'is-active' : ''}
              onClick={() => setActiveCertificateType('matricula')}
              role="tab"
              aria-selected={activeCertificateType === 'matricula'}
            >
              <span>Tipo de certificado</span>
              <strong>Matrícula</strong>
              <small>{selectedMatriculaCount} seleccionado(s)</small>
            </button>
            <button
              type="button"
              className={activeCertificateType === 'promocion' ? 'is-active' : ''}
              onClick={() => setActiveCertificateType('promocion')}
              role="tab"
              aria-selected={activeCertificateType === 'promocion'}
            >
              <span>Tipo de certificado</span>
              <strong>Promoción</strong>
              <small>{selectedPromocionCount} seleccionado(s)</small>
            </button>
          </div>

          <label className="certificados-table-filter">
            <span>Filtrar estudiantes del período</span>
            <input
              value={busqueda}
              onChange={(event) => setBusqueda(event.target.value)}
              placeholder="Nombre, código, carrera o número de matrícula"
              disabled={students.length === 0}
            />
          </label>

          <div className="certificados-selection-strip">
            <label>
              <input
                type="checkbox"
                checked={activeSelectableStudents.length > 0 && activeSelectedCount === activeSelectableStudents.length}
                onChange={() => toggleAll(activeCertificateType)}
                disabled={activeSelectableStudents.length === 0}
              />
              <span>Seleccionar estudiantes habilitados para {activeCertificateLabel}</span>
            </label>
            <strong>
              {activeSelectedCount} seleccionado(s) | {activeSelectableStudents.length} habilitado(s)
            </strong>
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
                {generatingZip ? 'Generando ZIP...' : 'Descargar certificados individuales'}
              </button>
              <button
                type="button"
                onClick={() => void generateMassivePdf(activeCertificateType)}
                disabled={generatingMassivePdf || activeSelectedCount === 0}
              >
                {generatingMassivePdf ? 'Generando PDF...' : 'Descargar PDF consolidado'}
              </button>
            </div>
          </div>

          <div className="matricula-table-wrap excel-table-wrap certificados-table-wrap">
            <table className="matricula-table certificados-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Código</th>
                  <th>Estudiante</th>
                  <th>Cabecera matrícula</th>
                  <th>Correos</th>
                  <th>Estado</th>
                  <th>Reprobadas</th>
                  <th>Certificados</th>
                </tr>
              </thead>
              <tbody>
                {visibleStudents.length > 0 ? (
                  visibleStudents.map((student) => {
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
                            {!hasPeriod ? <small>Seleccione período o consulte una cédula con cabecera de matrícula</small> : null}
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
                    <td colSpan={8}>
                      {searchLoading
                        ? 'Cargando estudiantes matriculados...'
                        : !periodo
                          ? 'Seleccione un período académico para iniciar la consulta.'
                          : students.length === 0
                            ? 'No existen estudiantes activos matriculados en el período seleccionado.'
                            : 'No existen coincidencias con el filtro ingresado.'}
                    </td>
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
