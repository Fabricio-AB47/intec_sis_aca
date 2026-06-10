import { useMemo, useState } from 'react'

import { downloadSenescytStudentReport, fetchSenescytStudentReport } from '../../lib/api'
import type { SenescytStudentReportResponse } from '../../types/app'

type SenescytEstudiantesViewProps = {
  displayName: string
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

function isVisibleCareerName(careerName?: string): boolean {
  const normalized = (careerName || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toUpperCase()
  return Boolean(normalized) && !normalized.startsWith('SIN CARRERA')
}

export function SenescytEstudiantesView({ displayName }: Readonly<SenescytEstudiantesViewProps>) {
  const [data, setData] = useState<SenescytStudentReportResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedCareerName, setSelectedCareerName] = useState('')

  const summary = data?.summary
  const careers = data?.careers || []
  const warnings = data?.warnings || []

  const visibleCareers = useMemo(
    () => careers.filter((career) => isVisibleCareerName(career.nombre_carrera)),
    [careers],
  )
  const topCareers = useMemo(
    () => [...visibleCareers].sort((left, right) => right.total_estudiantes - left.total_estudiantes),
    [visibleCareers],
  )
  const selectedCareer = topCareers.find((career) => career.nombre_carrera === selectedCareerName)
  const selectedStudents = selectedCareer?.students_missing || []

  async function loadReport() {
    setLoading(true)
    setError('')
    try {
      const payload = await fetchSenescytStudentReport()
      setData(payload)
      setSelectedCareerName((current) => {
        if (payload.careers?.some((career) => career.nombre_carrera === current && isVisibleCareerName(career.nombre_carrera))) {
          return current
        }
        return ''
      })
    } catch (requestError) {
      setError(handleError(requestError, 'Error generando resumen SENECYT'))
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  async function downloadReport() {
    setDownloadLoading(true)
    setError('')
    try {
      const blob = await downloadSenescytStudentReport()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `senescyt-estudiantes-${new Date().toISOString().slice(0, 10)}.zip`
      document.body.append(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(handleError(requestError, 'Error descargando Excel SENECYT'))
    } finally {
      setDownloadLoading(false)
    }
  }

  function selectCareer(careerName: string) {
    if (isVisibleCareerName(careerName)) {
      setSelectedCareerName(careerName)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">SENECYT</p>
          <h1>Datos Estudiante SENECYT</h1>
          <p className="report-description">
            Reporte de estudiantes activos segun el tablero de matricula, con estructura SENECYT exportable por carrera.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Reporte SENECYT</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats matricula-stats-grid">
        <article className="student-card student-card--stat">
          <p>Total reporte</p>
          <h2>{formatNumber(summary?.total_reporte)}</h2>
          <small>Exportables</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Activos DATOS_ESTUD</p>
          <h2>{formatNumber(summary?.total_activos_datos_estud)}</h2>
          <small>{summary?.coincide_activos ? 'Coincide' : 'Revisar diferencia'}</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Carreras</p>
          <h2>{formatNumber(summary?.total_carreras)}</h2>
          <small>Archivos Excel</small>
        </article>
        <article className="student-card student-card--stat">
          <p>Campos llenos</p>
          <h2>{formatPercent(summary?.porcentaje_lleno)}</h2>
          <small>{formatNumber(summary?.total_columnas)} campos del Excel SENECYT</small>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide senescyt-report-card">
          <div className="card-head">
            <h3>Resumen por carrera</h3>
            <span>{loading ? 'Procesando...' : `${formatNumber(topCareers.length)} carrera(s)`}</span>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void loadReport()} disabled={loading}>
              {loading ? 'Procesando...' : 'Procesar reporte'}
            </button>
            <button type="button" onClick={() => void downloadReport()} disabled={loading || downloadLoading || !data}>
              {downloadLoading ? 'Generando Excel...' : 'Descargar Excel por carrera'}
            </button>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
          {warnings.map((warning) => (
            <p key={warning} className="form-success">{warning}</p>
          ))}

          <div className="matricula-table-wrap">
            <table className="matricula-table senescyt-table">
              <thead>
                <tr>
                  <th>Carrera</th>
                  <th>Estudiantes</th>
                  <th>Estudiantes incompletos</th>
                  <th>Campos pendientes</th>
                  <th>Campos llenos</th>
                  <th>Total campos</th>
                  <th>% lleno</th>
                </tr>
              </thead>
              <tbody>
                {topCareers.map((career) => (
                  <tr
                    key={career.nombre_carrera}
                    className={`senescyt-table-row-button ${career.nombre_carrera === selectedCareerName ? 'senescyt-table-row--active' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectCareer(career.nombre_carrera)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        selectCareer(career.nombre_carrera)
                      }
                    }}
                  >
                    <td>
                      <button
                        type="button"
                        className="senescyt-career-button"
                        onClick={(event) => {
                          event.stopPropagation()
                          selectCareer(career.nombre_carrera)
                        }}
                      >
                        {career.nombre_carrera}
                      </button>
                    </td>
                    <td>{formatNumber(career.total_estudiantes)}</td>
                    <td>{formatNumber(career.estudiantes_con_pendientes)}</td>
                    <td>{formatNumber(career.campos_pendientes)}</td>
                    <td>{formatNumber(career.campos_llenos)}</td>
                    <td>{formatNumber(career.campos_totales)}</td>
                    <td>{formatPercent(career.porcentaje_lleno)}</td>
                  </tr>
                ))}
                {topCareers.length === 0 ? (
                  <tr>
                    <td colSpan={7}>Procesa el reporte para ver las carreras exportables.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {selectedCareer ? (
        <div className="senescyt-modal-backdrop" role="presentation" onClick={() => setSelectedCareerName('')}>
          <section
            className="student-card senescyt-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="senescyt-career-detail-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="card-head">
              <div>
                <p className="eyebrow">Verificacion SENECYT</p>
                <h3 id="senescyt-career-detail-title">{selectedCareer.nombre_carrera}</h3>
              </div>
              <button type="button" className="senescyt-modal-close" onClick={() => setSelectedCareerName('')}>
                Cerrar
              </button>
            </div>

            <div className="matricula-acad-preview">
              <div>
                <span>Estudiantes</span>
                <strong>{formatNumber(selectedCareer.total_estudiantes)}</strong>
              </div>
              <div>
                <span>Incompletos</span>
                <strong>{formatNumber(selectedCareer.estudiantes_con_pendientes)}</strong>
              </div>
              <div>
                <span>Campos pendientes</span>
                <strong>{formatNumber(selectedCareer.campos_pendientes)}</strong>
              </div>
              <div>
                <span>% lleno</span>
                <strong>{formatPercent(selectedCareer.porcentaje_lleno)}</strong>
              </div>
            </div>

            <div className="matricula-table-wrap">
              <table className="matricula-table senescyt-detail-table">
                <thead>
                  <tr>
                    <th>Estudiante</th>
                    <th>Cedula</th>
                    <th>Campos pendientes</th>
                    <th>% lleno</th>
                    <th>Campos faltantes</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedStudents.map((student) => (
                    <tr key={`${student.numero_identificacion}-${student.estudiante}`}>
                      <td>{student.estudiante}</td>
                      <td>{student.numero_identificacion || 'Sin cedula'}</td>
                      <td>{formatNumber(student.campos_pendientes)}</td>
                      <td>{formatPercent(student.porcentaje_lleno)}</td>
                      <td>{student.campos_faltantes.join(', ')}</td>
                    </tr>
                  ))}
                  {selectedStudents.length === 0 ? (
                    <tr>
                      <td colSpan={5}>Esta carrera no tiene estudiantes con campos pendientes.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
