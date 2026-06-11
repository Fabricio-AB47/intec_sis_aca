import { useEffect, useMemo, useState } from 'react'

import {
  downloadSenescytAuditWorkbook,
  fetchSenescytAuditReport,
  fetchSenescytCatalog,
} from '../../lib/api'
import type {
  SenescytAuditResponse,
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

  const summary = report?.summary
  const rows = report?.rows || []
  const missingFields = report?.missing_fields || []
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
  const selectedCareerPreview = selectedCareers.slice(0, 5)
  const selectedCareerOverflow = Math.max(selectedCareers.length - selectedCareerPreview.length, 0)

  async function loadCatalog() {
    setCatalogLoading(true)
    try {
      setCatalog(await fetchSenescytCatalog())
    } catch (requestError) {
      setError(handleError(requestError, 'No se pudo cargar el catalogo de carreras.'))
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

  async function download(targetToDownload: SenescytTarget, mode: SenescytExportMode) {
    const key = `${targetToDownload}-${mode}`
    setDownloading(key)
    setError('')
    try {
      const blob = await downloadSenescytAuditWorkbook(targetToDownload, mode, selectedCareers)
      const suffix = selectedCareers.length
        ? `${selectedCareers.length}-carreras`
        : 'todas-las-carreras'
      saveBlob(blob, `senescyt-${targetToDownload}-${mode}-${suffix}.xlsx`)
    } catch (requestError) {
      setError(handleError(requestError, 'No se pudo descargar el Excel SENESCYT.'))
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

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">SENESCYT</p>
          <h1>Datos SENESCYT</h1>
          <p className="report-description">
            Reportes regulatorios de estudiantes y docentes por carrera, con control de campos vacíos y descarga en Excel.
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
            Tipo de informacion
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
              <div>
                <label>Carreras</label>
                <strong>{selectedCareerLabel}</strong>
              </div>
              <span>{filteredCareers.length} visible(s)</span>
            </div>

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
                <button type="button" onClick={selectAllCareers} disabled={catalogLoading || careers.length === 0}>
                  Todas
                </button>
                <button type="button" onClick={clearCareers} disabled={selectedCareers.length === 0}>
                  Limpiar
                </button>
              </div>
            </div>

            <div className="senescyt-career-picker__list" aria-label="Seleccion multiple de carreras">
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

            {selectedCareers.length ? (
              <div className="senescyt-selected-careers">
                {selectedCareerPreview.map((career) => (
                  <span key={career}>{career}</span>
                ))}
                {selectedCareerOverflow ? <span>+{selectedCareerOverflow} mas</span> : null}
              </div>
            ) : null}
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
          <small>{TARGET_LABELS[target]}</small>
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

      <section className="student-card student-card--wide senescyt-download-card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Descargas Excel</p>
            <h3>Generación por carrera y faltantes</h3>
            <p className="report-description">
              Los archivos de faltantes incluyen lista global sin duplicidad, hojas por carrera y detalle de campos pendientes.
            </p>
          </div>
          <span>{report?.generated_at ? `Actualizado ${report.generated_at}` : 'Sin consulta'}</span>
        </div>

        <div className="senescyt-download-actions">
          <button
            type="button"
            onClick={() => void download(target, 'completo')}
            disabled={downloading === `${target}-completo`}
          >
            {downloading === `${target}-completo`
              ? 'Generando...'
              : `Archivo ${TARGET_LABELS[target].toLowerCase()} por carrera`}
          </button>
          <button
            type="button"
            onClick={() => void download(target, 'faltantes')}
            disabled={downloading === `${target}-faltantes`}
          >
            {downloading === `${target}-faltantes`
              ? 'Generando...'
              : `Faltantes ${TARGET_LABELS[target].toLowerCase()} global/carreras`}
          </button>
        </div>
      </section>

      <section className="student-grid student-grid--content senescyt-audit-grid">
        <article className="student-card student-card--wide senescyt-report-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Vista previa</p>
              <h3>{TARGET_LABELS[target]} con campos pendientes</h3>
            </div>
            <span>{formatNumber(rows.length)} visible(s)</span>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table senescyt-table">
              <thead>
                <tr>
                  <th>Identificacion</th>
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
                {rows.map((row) => (
                  <tr key={`${row.identificacion}-${row.codigo}-${row.nombre_carrera}`}>
                    <td>
                      <strong>{row.identificacion || '-'}</strong>
                      <small>Codigo {row.codigo || '-'}</small>
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
                    <td colSpan={8}>No hay registros para mostrar. Pulse Consultar o cambie los filtros.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        <article className="student-card senescyt-side-card">
          <div className="card-head">
            <h3>Campos mas faltantes</h3>
            <span>{formatNumber(missingFields.length)}</span>
          </div>
          <div className="senescyt-missing-list">
            {missingFields.slice(0, 12).map((field) => (
              <div key={field.campo}>
                <span>{field.campo}</span>
                <strong>{formatNumber(field.pendientes)}</strong>
                <small>{formatPercent(field.porcentaje_lleno)} de avance</small>
              </div>
            ))}
            {missingFields.length === 0 ? <p>No hay campos pendientes detectados.</p> : null}
          </div>
        </article>
      </section>
    </>
  )
}
