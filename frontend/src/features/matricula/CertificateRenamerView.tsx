import { useEffect, useMemo, useState, type ChangeEvent } from 'react'

import {
  analyzeCertificateRenameFiles,
  downloadCertificateRenameTar,
  downloadCertificateRenameZip,
  saveCertificateRenameLocal,
} from '../../lib/api'
import type { CertificateRenameItem, CertificateRenameResponse } from '../../types/app'

type CertificateRenamerViewProps = {
  displayName: string
}

type AnalysisProgressItem = {
  id: string
  name: string
  size: number
  progress: number
  stage: string
  status?: string
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

function fileSizeLabel(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(2)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function valueOrDash(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '-'
}

function statusLabel(status?: string) {
  if (status === 'LISTO') return 'Listo'
  if (status === 'RENOMBRADO_DOCUMENTO') return 'Renombrado con documento'
  if (status === 'SIN_CEDULA') return 'Sin cedula'
  if (status === 'CEDULA_NO_ENCONTRADA') return 'Cedula sin registro'
  if (status === 'NO_PDF') return 'No PDF'
  return valueOrDash(status)
}

function statusClass(status?: string) {
  const normalized = String(status || '').toLowerCase().replaceAll('_', '-')
  return `credential-status credential-status--${normalized || 'pendiente'}`
}

function progressIdFromFile(file: File, index: number) {
  return `${file.name}-${file.size}-${file.lastModified}-${index}`
}

function progressStage(progress: number) {
  if (progress >= 100) return 'Finalizado'
  if (progress >= 76) return 'Generando nombre final'
  if (progress >= 54) return 'Validando cedula en base'
  if (progress >= 30) return 'Buscando cedula en PDF'
  if (progress >= 12) return 'Extrayendo texto'
  return 'Preparando archivo'
}

function boundedStepProgress(total: number, start: number, end: number) {
  if (total <= start) return 0
  if (total >= end) return 100
  return Math.round(((total - start) / (end - start)) * 100)
}

function compactCertificateName(item: CertificateRenameItem) {
  const cedula = valueOrDash(item.cedula)
  const nombres = valueOrDash(item.nombres)

  if (cedula !== '-' && nombres !== '-') {
    return `CERTIFICADO_MATRICULA - ${cedula} - ${nombres}`
  }

  const finalName = valueOrDash(item.new_name)
  if (finalName === '-') return finalName

  return finalName.replace(/\.pdf$/i, '').split(' - ').slice(0, 3).join(' - ')
}

export function CertificateRenamerView({ displayName }: Readonly<CertificateRenamerViewProps>) {
  const [files, setFiles] = useState<File[]>([])
  const [analysis, setAnalysis] = useState<CertificateRenameResponse | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgressItem[]>([])
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadingTar, setDownloadingTar] = useState(false)
  const [savingLocal, setSavingLocal] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const summary = analysis?.summary || {}
  const pdfCount = useMemo(() => files.filter((file) => file.name.toLowerCase().endsWith('.pdf')).length, [files])
  const zipCount = useMemo(() => files.filter((file) => file.name.toLowerCase().endsWith('.zip')).length, [files])
  const totalSize = useMemo(() => files.reduce((total, file) => total + file.size, 0), [files])
  const items = analysis?.items || []
  const readyCount = summary.ready || items.filter((item) => item.status === 'LISTO').length
  const issueCount =
    (summary.without_cedula || 0) +
      (summary.not_found || 0) +
      (summary.not_pdf || 0) ||
    items.filter((item) => item.status !== 'LISTO' && item.status !== 'RENOMBRADO_DOCUMENTO').length
  const overallProgress = analysisProgress.length
    ? Math.round(analysisProgress.reduce((total, item) => total + item.progress, 0) / analysisProgress.length)
    : items.length
      ? 100
      : 0
  const processSteps = [
    {
      label: 'Preparacion',
      detail: 'Carga y orden de documentos.',
      progress: boundedStepProgress(overallProgress, 0, 16),
    },
    {
      label: 'Lectura PDF',
      detail: 'Extraccion de texto y busqueda de cedula.',
      progress: boundedStepProgress(overallProgress, 16, 46),
    },
    {
      label: 'Validacion SQL',
      detail: 'Cruce con DATOS_ESTUD y matriculas.',
      progress: boundedStepProgress(overallProgress, 46, 76),
    },
    {
      label: 'Nombre final',
      detail: 'Generacion del archivo renombrado.',
      progress: boundedStepProgress(overallProgress, 76, 100),
    },
  ]

  useEffect(() => {
    if (!loading || !analysisProgress.length) return undefined

    const timer = window.setInterval(() => {
      setAnalysisProgress((current) =>
        current.map((item, index) => {
          if (item.progress >= 100) return item
          const increment = Math.max(2, 9 - Math.min(index, 5))
          const progress = Math.min(92, item.progress + increment)
          return {
            ...item,
            progress,
            stage: progressStage(progress),
          }
        }),
      )
    }, 520)

    return () => window.clearInterval(timer)
  }, [analysisProgress.length, loading])

  function updateFiles(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || [])
    if (!selectedFiles.length) return
    setFiles((current) => [...current, ...selectedFiles])
    setAnalysis(null)
    setAnalysisProgress([])
    setError('')
    setMessage('')
    event.currentTarget.value = ''
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))
    setAnalysis(null)
    setAnalysisProgress([])
    setError('')
    setMessage('')
  }

  function clearFiles() {
    setFiles([])
    setAnalysis(null)
    setAnalysisProgress([])
    setError('')
    setMessage('')
  }

  async function analyzeFiles() {
    setError('')
    setMessage('')

    if (!files.length) {
      setError('Sube uno o mas PDF o un ZIP con PDFs de certificado matricula para analizar.')
      return
    }

    setLoading(true)
    setAnalysisProgress(
      files.map((file, index) => ({
        id: progressIdFromFile(file, index),
        name: file.name,
        size: file.size,
        progress: index === 0 ? 8 : 3,
        stage: index === 0 ? 'Preparando archivo' : 'En cola',
      })),
    )
    try {
      const payload = await analyzeCertificateRenameFiles(files)
      setAnalysis(payload)
      setAnalysisProgress(
        payload.items?.length
          ? payload.items.map((item, index) => ({
              id: `${item.original_name}-${item.cedula || index}`,
              name: item.original_name,
              size: 0,
              progress: 100,
              stage:
                item.status === 'LISTO'
                  ? 'Renombrado con datos de la base'
                  : item.status === 'RENOMBRADO_DOCUMENTO'
                    ? 'Renombrado con datos del documento'
                    : statusLabel(item.status),
              status: item.status,
            }))
          : files.map((file, index) => ({
              id: progressIdFromFile(file, index),
              name: file.name,
              size: file.size,
              progress: 100,
              stage: 'Finalizado sin registros visibles',
              status: 'PENDIENTE',
            })),
      )
      setMessage(`${payload.summary?.total || 0} archivo(s) analizado(s).`)
    } catch (apiError) {
      setAnalysisProgress((current) =>
        current.map((item) => ({
          ...item,
          progress: 100,
          stage: 'Error durante el analisis',
          status: 'ERROR',
        })),
      )
      setError(apiError instanceof Error ? apiError.message : 'No se pudo analizar los PDF.')
    } finally {
      setLoading(false)
    }
  }

  async function downloadRenamedZip() {
    setError('')
    setMessage('')

    if (!files.length) {
      setError('Sube uno o mas PDF o un ZIP con PDFs antes de descargar.')
      return
    }

    setDownloading(true)
    try {
      const blob = await downloadCertificateRenameZip(files)
      downloadBlob(blob, `certificados-matricula-renombrados-${new Date().toISOString().slice(0, 10)}.zip`)
      setMessage('ZIP sin compresion generado con los documentos renombrados y el reporte CSV.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el ZIP.')
    } finally {
      setDownloading(false)
    }
  }

  async function downloadRenamedTar() {
    setError('')
    setMessage('')

    if (!files.length) {
      setError('Sube uno o mas PDF o un ZIP con PDFs antes de descargar.')
      return
    }

    setDownloadingTar(true)
    try {
      const blob = await downloadCertificateRenameTar(files)
      downloadBlob(blob, `certificados-matricula-renombrados-${new Date().toISOString().slice(0, 10)}.tar`)
      setMessage('Archivo TAR generado con los documentos renombrados y el reporte CSV.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar el archivo alternativo.')
    } finally {
      setDownloadingTar(false)
    }
  }

  async function saveLocalFolder() {
    setError('')
    setMessage('')

    if (!files.length) {
      setError('Sube uno o mas PDF o un ZIP con PDFs antes de guardar.')
      return
    }

    setSavingLocal(true)
    try {
      const payload = await saveCertificateRenameLocal(files)
      setAnalysis(payload)
      setMessage(`${payload.saved || 0} archivo(s) guardado(s) en: ${payload.local_dir || 'carpeta local'}`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el lote en carpeta local.')
    } finally {
      setSavingLocal(false)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Certificados</p>
          <h1>Renombrar certificados de matricula</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Lectura de cedula en PDF</span>
            </div>
          </div>
        </div>
      </header>

      <section className="credential-overview certificate-renamer-overview">
        <article>
          <span>Archivos cargados</span>
          <strong>{files.length}</strong>
          <small>{pdfCount} PDF | {zipCount} ZIP</small>
        </article>
        <article>
          <span>Listos para renombrar</span>
          <strong>{summary.ready || 0}</strong>
          <small>Con cedula y estudiante encontrado</small>
        </article>
        <article>
          <span>Incidencias</span>
          <strong>{(summary.without_cedula || 0) + (summary.not_found || 0) + (summary.not_pdf || 0)}</strong>
          <small>{fileSizeLabel(totalSize)}</small>
        </article>
      </section>

      <section className="certificate-renamer-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <h3>Cargar lote de certificados</h3>
              <p>Sube PDFs sueltos o un ZIP con PDFs. El sistema extrae cada PDF, detecta la cedula y valida el estudiante.</p>
            </div>
            <span>{loading ? 'Analizando...' : `${files.length} archivo(s)`}</span>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}

          <div className="certificate-renamer-upload">
            <label>
              <span>PDF o ZIP de certificados matricula</span>
              <input type="file" accept="application/pdf,.pdf,application/zip,.zip" multiple onChange={updateFiles} />
            </label>
            <div className="credential-actions">
              <button type="button" className="ghost-button" onClick={() => void analyzeFiles()} disabled={loading || !files.length}>
                {loading ? 'Analizando...' : 'Analizar documentos'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void downloadRenamedZip()}
                disabled={downloading || !files.length}
              >
                {downloading ? 'Generando...' : 'Descargar ZIP sin compresion'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void downloadRenamedTar()}
                disabled={downloadingTar || !files.length}
              >
                {downloadingTar ? 'Generando...' : 'Descargar alternativa TAR'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void saveLocalFolder()}
                disabled={savingLocal || !files.length}
              >
                {savingLocal ? 'Guardando...' : 'Guardar en carpeta local'}
              </button>
              <button type="button" className="ghost-button" onClick={clearFiles} disabled={!files.length}>
                Limpiar
              </button>
            </div>
          </div>

          {files.length ? (
            <div className="certificate-renamer-files">
              {files.map((file, index) => (
                <div key={`${file.name}-${file.size}-${file.lastModified}-${index}`}>
                  <div>
                    <strong>{file.name}</strong>
                    <span>{fileSizeLabel(file.size)}</span>
                  </div>
                  <button type="button" className="ghost-button" onClick={() => removeFile(index)}>
                    Quitar
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </article>

        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <h3>Resultado del análisis</h3>
              <p>Revisa el nombre final antes de descargar el lote.</p>
            </div>
            <span>{items.length} registro(s)</span>
          </div>

          {analysisProgress.length || loading ? (
            <section className="certificate-renamer-progress-panel" aria-live="polite">
              <div className="certificate-renamer-progress-head">
                <div>
                  <strong>Avance del análisis</strong>
                  <span>
                    {loading
                      ? 'Procesando documentos, extrayendo cédula y validando contra la base.'
                      : 'Análisis finalizado. Revisa los documentos listos y los que requieren validación.'}
                  </span>
                </div>
                <b>{overallProgress}%</b>
              </div>
              <div className="certificate-renamer-progress-bar">
                <span style={{ width: `${overallProgress}%` }} />
              </div>
              <div className="certificate-renamer-steps">
                {processSteps.map((step) => (
                  <article key={step.label} className="certificate-renamer-step">
                    <div>
                      <strong>{step.label}</strong>
                      <span>{step.detail}</span>
                    </div>
                    <b>{step.progress}%</b>
                    <em>
                      <span style={{ width: `${step.progress}%` }} />
                    </em>
                  </article>
                ))}
              </div>
              <div className="certificate-renamer-progress-files">
                {analysisProgress.map((item) => (
                  <article key={item.id} className="certificate-renamer-progress-file">
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.size ? fileSizeLabel(item.size) : statusLabel(item.status)}</span>
                    </div>
                    <div>
                      <small>{item.stage}</small>
                      <b>{item.progress}%</b>
                    </div>
                    <em>
                      <span style={{ width: `${item.progress}%` }} />
                    </em>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <div className="certificate-renamer-result-summary">
            <article>
              <span>Validados</span>
              <strong>{readyCount}</strong>
            </article>
            <article>
              <span>Con revision</span>
              <strong>{issueCount}</strong>
            </article>
            <article>
              <span>Total analizado</span>
              <strong>{items.length}</strong>
            </article>
          </div>

          {items.length ? (
            <div className="certificate-renamer-analysis-list">
              {items.map((item: CertificateRenameItem, index) => (
                <article className="certificate-renamer-analysis-card" key={`${item.original_name}-${item.cedula}-${index}`}>
                  <header>
                    <div>
                      <span>Certificado</span>
                      <strong className="certificate-renamer-certificate-name">{compactCertificateName(item)}</strong>
                      <small>{valueOrDash(item.detail)}</small>
                    </div>
                    <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
                  </header>
                  <div className="certificate-renamer-analysis-grid certificate-renamer-analysis-grid--compact">
                    <div>
                      <span>Cédula</span>
                      <strong>{valueOrDash(item.cedula)}</strong>
                    </div>
                    <div>
                      <span>Estudiante</span>
                      <strong>{valueOrDash(item.nombres)}</strong>
                      <small>Codigo {valueOrDash(item.codigo_estud)}</small>
                    </div>
                    <div>
                      <span>Carrera / periodo</span>
                      <strong>{valueOrDash(item.carrera)}</strong>
                      <small>{valueOrDash(item.periodo)}</small>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="certificate-renamer-empty">
              <strong>Sin analisis cargado</strong>
              <span>Sube PDFs o un ZIP y pulsa Analizar documentos para ver cedula, estudiante y nombre final.</span>
            </div>
          )}
        </article>
      </section>
    </>
  )
}
