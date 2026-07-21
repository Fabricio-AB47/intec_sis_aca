import { useEffect, useMemo, useState } from 'react'

import {
  downloadMatriculaExcelTemplate,
  fetchCertificadosCatalog,
  generateMatriculaPdfFromExcel,
} from '../../lib/api'
import type { CertificadosCatalogResponse, CertificadosPeriodOption } from '../../types/app'

type MatriculaExcelCertificadosViewProps = {
  displayName: string
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

function periodLabel(period?: CertificadosPeriodOption | null): string {
  if (!period) return 'Seleccione periodo'
  return period.detalle_periodo || period.cod_periodo || 'Seleccione periodo'
}

function dateRangeLabel(period?: CertificadosPeriodOption | null): string {
  if (!period) return 'Pendiente'
  const start = period.fecha_inicio || ''
  const end = period.fecha_fin || ''
  if (!start && !end) return 'Sin fechas registradas'
  return [start ? `Inicio ${start}` : '', end ? `Fin ${end}` : ''].filter(Boolean).join(' | ')
}

export function MatriculaExcelCertificadosView({ displayName }: Readonly<MatriculaExcelCertificadosViewProps>) {
  const [catalog, setCatalog] = useState<CertificadosCatalogResponse | null>(null)
  const [periodo, setPeriodo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [templateLoading, setTemplateLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const periodos = useMemo(() => catalog?.periodos || [], [catalog?.periodos])
  const selectedPeriod = useMemo(
    () => periodos.find((item) => item.cod_periodo === periodo) || null,
    [periodo, periodos],
  )

  async function loadCatalog() {
    setCatalogLoading(true)
    setError('')
    try {
      setCatalog(await fetchCertificadosCatalog())
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el catalogo de periodos')
    } finally {
      setCatalogLoading(false)
    }
  }

  async function downloadTemplate() {
    setError('')
    setMessage('')
    setTemplateLoading(true)
    try {
      const blob = await downloadMatriculaExcelTemplate()
      downloadBlob(blob, 'plantilla_matricula_certificados_v3.xlsx')
      setMessage('Plantilla descargada.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la plantilla')
    } finally {
      setTemplateLoading(false)
    }
  }

  async function generatePdf() {
    setError('')
    setMessage('')
    if (!periodo) {
      setError('Selecciona el periodo antes de subir el documento.')
      return
    }
    if (!file) {
      setError('Selecciona un archivo Excel con estudiantes.')
      return
    }

    setGenerating(true)
    try {
      const blob = await generateMatriculaPdfFromExcel(periodo, file)
      downloadBlob(blob, `certificados-matricula-${periodo}-${new Date().toISOString().slice(0, 10)}.pdf`)
      setMessage('PDF de certificados de matricula generado.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el PDF')
    } finally {
      setGenerating(false)
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
          <h1>Matrícula en Excel</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Certificados por carga masiva</span>
            </div>
          </div>
        </div>
      </header>

      <section className="certificados-overview">
        <article>
          <span>Periodo seleccionado</span>
          <strong>{periodLabel(selectedPeriod)}</strong>
          <small>{dateRangeLabel(selectedPeriod)}</small>
        </article>
        <article>
          <span>Plantilla</span>
          <strong>nombres, cédula, carrera, semestre</strong>
          <small>Carreras sin Educación Continua ni Inglés</small>
        </article>
        <article>
          <span>Salida</span>
          <strong>PDF masivo</strong>
          <small>Un certificado de matrícula por fila válida</small>
        </article>
      </section>

      <section className="student-grid student-grid--content certificados-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Generar certificados</h3>
            <span>{catalogLoading ? 'Cargando periodos...' : `${periodos.length} periodo(s)`}</span>
          </div>

          <div className="certificados-format-note">
            <strong>Formato del Excel:</strong>
            <span>
              La plantilla usa nombres y apellidos, número de cédula, carrera y semestre. La carrera se selecciona desde
              una hoja de carreras permitidas, excluyendo Educación Continua e Inglés. Los costos no se editan en el Excel:
              se calculan automáticamente por carrera y Gastronomía conserva su valor diferenciado.
            </span>
          </div>

          <div className="matricula-acad-form certificados-form">
            <label>
              <span>Periodo académico</span>
              <select
                value={periodo}
                onChange={(event) => {
                  setPeriodo(event.target.value)
                  setFile(null)
                }}
                disabled={catalogLoading}
              >
                <option value="">Seleccione periodo</option>
                {periodos.map((item) => (
                  <option key={`periodo-excel-${item.cod_periodo}`} value={item.cod_periodo}>
                    {item.detalle_periodo}
                  </option>
                ))}
              </select>
            </label>
            <label className="certificados-field--wide">
              <span>Archivo Excel</span>
              <input
                key={periodo || 'sin-periodo'}
                type="file"
                accept=".xlsx,.xlsm"
                disabled={!periodo}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>

          <div className="teams-actions certificados-actions">
            <button type="button" onClick={() => void downloadTemplate()} disabled={templateLoading}>
              {templateLoading ? 'Descargando...' : 'Descargar plantilla'}
            </button>
            <button type="button" onClick={() => void generatePdf()} disabled={generating || !periodo || !file}>
              {generating ? 'Generando...' : 'Generar PDF'}
            </button>
          </div>

          {file ? (
            <div className="certificados-active-panel">
              <div>
                <span>Archivo listo</span>
                <strong>{file.name}</strong>
                <small>{Math.max(1, Math.round(file.size / 1024))} KB</small>
              </div>
            </div>
          ) : null}

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </article>
      </section>
    </>
  )
}
