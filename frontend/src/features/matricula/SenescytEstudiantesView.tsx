import { useEffect, useMemo, useState } from 'react'

import {
  downloadSenescytAuditWorkbook,
  fetchSenescytAuditReport,
  fetchSenescytCatalog,
} from '../../lib/api'
import type {
  SenescytAuditResponse,
  SenescytAuditRow,
  SenescytCatalogCareer,
  SenescytCatalogResponse,
  SenescytExportMode,
  SenescytTarget,
} from '../../types/app'

type SenescytEstudiantesViewProps = {
  displayName: string
}

const TARGET_LABELS: Record<SenescytTarget, string> = {
  estudiantes: 'Estudiantes',
  docentes: 'Docentes',
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function formatPercent(value?: number): string {
  return `${new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(value ?? 0)}%`
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function SenescytEstudiantesView({ displayName }: Readonly<SenescytEstudiantesViewProps>) {
  const [catalog, setCatalog] = useState<SenescytCatalogResponse | null>(null)
  const [target, setTarget] = useState<SenescytTarget>('estudiantes')
  const [selectedCareers, setSelectedCareers] = useState<string[]>([])
  const [report, setReport] = useState<SenescytAuditResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [downloading, setDownloading] = useState('')
  const [error, setError] = useState('')
  const [careerSearch, setCareerSearch] = useState('')
  const [careerPickerOpen, setCareerPickerOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [detailRow, setDetailRow] = useState<SenescytAuditRow | null>(null)

  const summary = report?.summary
  const rows = report?.rows || []
  const careers = useMemo(() => {
    const items = catalog?.careers || []
    const seen = new Set<string>()
    return items.filter((item: SenescytCatalogCareer) => {
      const name = item.nombre_carrera?.trim()
      if (!name || seen.has(name)) return false
      seen.add(name)
      return true
    })
  }, [catalog])
  const filteredCareers = useMemo(() => {
    const query = careerSearch.trim().toLowerCase()
    if (!query) return careers
    return careers.filter((item) => item.nombre_carrera.toLowerCase().includes(query))
  }, [careers, careerSearch])
  const selectedCareerSet = useMemo(() => new Set(selectedCareers), [selectedCareers])
  const selectedCareerLabel = selectedCareers.length ? `${selectedCareers.length} carrera(s) seleccionada(s)` : 'Todas las carreras'
  const selectedCareerPreview = selectedCareers.length
    ? selectedCareers.slice(0, 3).join(', ')
    : 'Se consultarán todas las carreras disponibles'
  const selectedCareerOverflow = Math.max(selectedCareers.length - 3, 0)
  const selectedCareerDisplay = `${selectedCareerPreview}${selectedCareerOverflow ? ` y ${selectedCareerOverflow} más` : ''}`

  async function loadCatalog() {
    setCatalogLoading(true)
    try {
      setCatalog(await fetchSenescytCatalog())
    } catch (requestError) {
      setError(handleError(requestError, 'No se pudo cargar el catálogo de carreras.'))
    } finally {
      setCatalogLoading(false)
    }
  }

  async function loadReport(nextTarget = target, nextCareers = selectedCareers) {
    setLoading(true)
    setError('')
    try {
      setReport(await fetchSenescytAuditReport(nextTarget, nextCareers))
    } catch (requestError) {
      setError(handleError(requestError, 'No se pudo generar el reporte SENESCYT.'))
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  function toggleCareer(careerName: string) {
    setSelectedCareers((current) => {
      if (current.includes(careerName)) {
        return current.filter((item) => item !== careerName)
      }
      return [...current, careerName]
    })
  }

  function selectAllCareers() {
    setSelectedCareers(careers.map((item) => item.nombre_carrera).filter(Boolean))
  }

  function selectFilteredCareers() {
    setSelectedCareers(filteredCareers.map((item) => item.nombre_carrera).filter(Boolean))
  }

  function clearCareers() {
    setSelectedCareers([])
  }

  function closePreview() {
    setPreviewOpen(false)
    setDetailRow(null)
  }

  async function download(targetToDownload: SenescytTarget, mode: SenescytExportMode) {
    const key = `${targetToDownload}-${mode}`
    setDownloading(key)
    setError('')
    try {
      const blob = await downloadSenescytAuditWorkbook(targetToDownload, mode, selectedCareers)
      const suffix = selectedCareers.length
        ? `${selectedCareers.length}-carreras`
        : 'todas-las-carreras'
      saveBlob(blob, `senescyt-${targetToDownload}-${mode}-${suffix}.zip`)
    } catch (requestError) {
      setError(handleError(requestError, 'No se pudo descargar el ZIP SENESCYT.'))
    } finally {
      setDownloading('')
    }
  }

  useEffect(() => {
    void loadCatalog()
  }, [])

  useEffect(() => {
    void loadReport(target, selectedCareers)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target])

  useEffect(() => {
    setCareerPickerOpen(false)
  }, [target])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">SENESCYT</p>
          <h1>Datos SENESCYT</h1>
          <p className="report-description">
            Reportes regulatorios de estudiantes y docentes activos por carrera, con control de campos vacíos y descarga en ZIP.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Reportes SENESCYT</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-card senescyt-control-panel">
        <div className="senescyt-filter-head">
          <div>
            <p className="eyebrow">Filtros</p>
            <h3>Seleccione el reporte</h3>
          </div>
          <div className="senescyt-filter-summary">
            <span>{TARGET_LABELS[target]}</span>
            <strong>{selectedCareerLabel}</strong>
          </div>
        </div>

        <div className="senescyt-filter-layout">
          <label className="senescyt-target-control">
            Tipo de información
            <select
              value={target}
              onChange={(event) => setTarget(event.target.value as SenescytTarget)}
            >
              <option value="estudiantes">Estudiantes</option>
              <option value="docentes">Docentes</option>
            </select>
          </label>

          <div className="senescyt-career-picker">
            <div className="senescyt-career-picker__head">
              <label>Carreras</label>
              <span>{filteredCareers.length} visible(s)</span>
            </div>

            <div className="senescyt-career-combo-row">
              <button
                type="button"
                className="senescyt-career-combobox"
                aria-expanded={careerPickerOpen}
                onClick={() => setCareerPickerOpen((isOpen) => !isOpen)}
              >
                <span>Seleccionar carreras</span>
                <strong>{selectedCareerLabel}</strong>
                <small>{selectedCareerDisplay}</small>
              </button>
              <button
                type="button"
                className="senescyt-career-select-all"
                onClick={selectAllCareers}
                disabled={catalogLoading || careers.length === 0}
              >
                Seleccionar todas
              </button>
            </div>

            {careerPickerOpen ? (
              <div className="senescyt-career-dropdown">
                <div className="senescyt-career-toolbar">
                  <label>
                    Buscar carrera
                    <input
                      value={careerSearch}
                      onChange={(event) => setCareerSearch(event.target.value)}
                      placeholder="Nombre de carrera"
                    />
                  </label>
                  <div className="senescyt-career-picker__actions">
                    <button type="button" onClick={selectFilteredCareers} disabled={catalogLoading || filteredCareers.length === 0}>
                      Seleccionar visibles
                    </button>
                    <button type="button" onClick={clearCareers} disabled={selectedCareers.length === 0}>
                      Limpiar
                    </button>
                  </div>
                </div>

                <div className="senescyt-career-picker__list" aria-label="Selección múltiple de carreras">
                  {filteredCareers.map((item) => {
                    const name = item.nombre_carrera
                    const isSelected = selectedCareerSet.has(name)
                    return (
                      <label key={`${item.codigo_carrera}-${name}`} className={`senescyt-career-check${isSelected ? ' is-selected' : ''}`}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleCareer(name)}
                        />
                        <span>{name}</span>
                      </label>
                    )
                  })}
                  {filteredCareers.length === 0 ? <p>{catalogLoading ? 'Cargando carreras...' : 'No hay carreras disponibles.'}</p> : null}
                </div>
              </div>
            ) : null}

            {selectedCareers.length ? (
              <div className="senescyt-selected-careers" aria-label="Carreras seleccionadas">
                {selectedCareers.map((career) => (
                  <span key={career} className="senescyt-career-chip">
                    {career}
                    <button type="button" aria-label={`Quitar ${career}`} onClick={() => toggleCareer(career)}>
                      x
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="senescyt-selected-careers-empty">Sin selección específica: se incluirán todas las carreras.</p>
            )}
          </div>

          <button type="button" className="senescyt-query-button" onClick={() => void loadReport()} disabled={loading}>
            {loading ? 'Procesando...' : 'Consultar'}
          </button>
        </div>
      </section>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="student-grid student-grid--stats matricula-stats-grid">
        <article className="student-card student-card--stat">
          <p>Registros</p>
          <h2>{formatNumber(summary?.total_registros)}</h2>
          <small>{TARGET_LABELS[target]} activos</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Avance de llenado</p>
          <h2>{formatPercent(summary?.porcentaje_lleno)}</h2>
          <small>{formatNumber(summary?.campos_llenos)} de {formatNumber(summary?.campos_totales)}</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Campos faltantes</p>
          <h2>{formatNumber(summary?.campos_pendientes)}</h2>
          <small>{formatNumber(summary?.registros_con_pendientes)} registro(s) incompleto(s)</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Carreras</p>
          <h2>{formatNumber(summary?.total_carreras)}</h2>
          <small>{selectedCareers.length ? selectedCareerLabel : 'Todas'}</small>
        </article>
      </section>

      <section className="senescyt-action-row" aria-label="Descargas y vista previa SENESCYT">
        <article className="student-card student-card--wide senescyt-download-card senescyt-action-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Descargas ZIP</p>
              <h3>Generación por carrera y faltantes</h3>
              <p className="report-description">
                Cada ZIP contiene un Excel por carrera. Los faltantes incluyen lista sin duplicidad y detalle de campos pendientes.
              </p>
            </div>
            <span>{report?.generated_at ? `Actualizado ${report.generated_at}` : 'Sin consulta'}</span>
          </div>

          <div className="senescyt-download-actions">
            <button
              type="button"
              className="senescyt-action-button senescyt-action-button--primary"
              onClick={() => void download(target, 'completo')}
              disabled={downloading === `${target}-completo`}
            >
              {downloading === `${target}-completo`
                ? 'Generando...'
                : `Archivo ${TARGET_LABELS[target].toLowerCase()} por carrera`}
            </button>
            <button
              type="button"
              className="senescyt-action-button senescyt-action-button--secondary"
              onClick={() => void download(target, 'faltantes')}
              disabled={downloading === `${target}-faltantes`}
            >
              {downloading === `${target}-faltantes`
                ? 'Generando...'
                : `Faltantes ${TARGET_LABELS[target].toLowerCase()} global/carreras`}
            </button>
          </div>
        </article>

        <article className="student-card student-card--wide senescyt-report-card senescyt-preview-launcher senescyt-action-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Vista previa</p>
              <h3>{TARGET_LABELS[target]} con campos pendientes</h3>
              <p className="report-description">
                Abra la subpantalla para revisar registros, campos faltantes y detalle individual.
              </p>
            </div>
            <div className="senescyt-preview-launcher__actions">
              <span>{formatNumber(rows.length)} visible(s)</span>
              <button
                type="button"
                className="senescyt-action-button senescyt-action-button--primary"
                onClick={() => setPreviewOpen(true)}
              >
                Vista previa
              </button>
            </div>
          </div>
        </article>
      </section>

      {previewOpen ? (
        <div className="senescyt-modal-backdrop senescyt-preview-backdrop" role="presentation">
          <section
            className="senescyt-modal senescyt-preview-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="senescyt-preview-title"
          >
            <div className="senescyt-modal__header">
              <div>
                <p className="eyebrow">Vista previa</p>
                <h3 id="senescyt-preview-title">{TARGET_LABELS[target]} con campos pendientes</h3>
                <p className="report-description">
                  Revise los registros antes de descargar el ZIP o completar la información pendiente.
                </p>
              </div>
              <button type="button" className="senescyt-modal__close" onClick={closePreview}>
                Cerrar
              </button>
            </div>

            <div className="senescyt-modal__body">
              <div className="matricula-table-wrap">
                <table className="matricula-table senescyt-table senescyt-preview-table">
                  <thead>
                    <tr>
                      <th>Ver</th>
                      <th>Identificación</th>
                      <th>Nombre</th>
                      <th>Correo</th>
                      <th>Teléfono</th>
                      <th>Carrera</th>
                      <th>% avance</th>
                      <th>Pendientes</th>
                      <th>Campos faltantes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${row.identificacion}-${row.codigo}-${row.nombre_carrera}-${index}`}>
                        <td>
                          <button
                            type="button"
                            className="senescyt-icon-button"
                            title="Ver detalle"
                            aria-label={`Ver detalle de ${row.nombre || row.identificacion || 'registro'}`}
                            onClick={() => setDetailRow(row)}
                          >
                            <svg
                              aria-hidden="true"
                              viewBox="0 0 24 24"
                              width="18"
                              height="18"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          </button>
                        </td>
                        <td>
                          <strong>{row.identificacion || '-'}</strong>
                          <small>
                            Código {row.codigo || '-'} - {row.documento?.tipo_actual_label || 'Sin tipo'}
                            {row.documento?.valido === false ? ' - revisar documento' : ''}
                          </small>
                        </td>
                        <td>{row.nombre || '-'}</td>
                        <td>{row.correo || '-'}</td>
                        <td>{row.telefono || '-'}</td>
                        <td>{row.nombre_carrera || '-'}</td>
                        <td>{formatPercent(row.porcentaje_lleno)}</td>
                        <td>{formatNumber(row.campos_pendientes)}</td>
                        <td>{(row.campos_faltantes || []).slice(0, 8).join(', ') || 'Completo'}</td>
                      </tr>
                    ))}
                    {rows.length === 0 ? (
                      <tr>
                        <td colSpan={9}>No hay registros para mostrar. Pulse Consultar o cambie los filtros.</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {detailRow ? (
        <div className="senescyt-modal-backdrop senescyt-modal-backdrop--stacked" role="presentation">
          <section
            className="senescyt-modal senescyt-detail-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="senescyt-detail-title"
          >
            <div className="senescyt-modal__header">
              <div>
                <p className="eyebrow">Detalle del registro</p>
                <h3 id="senescyt-detail-title">{detailRow.nombre || 'Registro SENESCYT'}</h3>
              </div>
              <button type="button" className="senescyt-modal__close" onClick={() => setDetailRow(null)}>
                Cerrar
              </button>
            </div>

            <div className="senescyt-modal__body">
              <div className="senescyt-detail-grid">
                <div className="senescyt-detail-field">
                  <span>Identificación</span>
                  <strong>{detailRow.identificacion || '-'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Código</span>
                  <strong>{detailRow.codigo || '-'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Tipo documento</span>
                  <strong>{detailRow.documento?.tipo_actual_label || 'Sin tipo'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Validación</span>
                  <strong>{detailRow.documento?.valido === false ? 'Revisar documento' : 'Validado'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Correo</span>
                  <strong>{detailRow.correo || '-'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Teléfono</span>
                  <strong>{detailRow.telefono || '-'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Carrera</span>
                  <strong>{detailRow.nombre_carrera || '-'}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Avance</span>
                  <strong>{formatPercent(detailRow.porcentaje_lleno)}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Campos llenos</span>
                  <strong>{formatNumber(detailRow.campos_llenos)} de {formatNumber(detailRow.campos_totales)}</strong>
                </div>
                <div className="senescyt-detail-field">
                  <span>Pendientes</span>
                  <strong>{formatNumber(detailRow.campos_pendientes)}</strong>
                </div>
              </div>

              <div className="senescyt-detail-block">
                <h4>Campos faltantes</h4>
                <div className="senescyt-missing-chips">
                  {detailRow.campos_faltantes?.length ? (
                    detailRow.campos_faltantes.map((field) => <span key={field}>{field}</span>)
                  ) : (
                    <strong className="senescyt-ok-pill">Completo</strong>
                  )}
                </div>
              </div>

              {detailRow.fields ? (
                <div className="senescyt-detail-block">
                  <h4>Valores registrados</h4>
                  <div className="senescyt-detail-values">
                    {Object.entries(detailRow.fields).map(([field, value]) => (
                      <div key={field} className="senescyt-detail-field">
                        <span>{field}</span>
                        <strong>{value === null || value === undefined || value === '' ? '-' : String(value)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
