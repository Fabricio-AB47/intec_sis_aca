import { useCallback, useEffect, useState } from 'react'

import {
  analyzeFechaGradoExcel,
  analyzeFechaGradoPdfs,
  downloadFechaGradoTemplate,
  fetchFechaGradoVerification,
  importFechaGradoExcel,
  importFechaGradoPdfs,
  saveFechaGrado,
} from '../../lib/api'
import type { FechaGradoImportResponse, FechaGradoVerificationRow } from '../../types/app'

type FechaGradoViewProps = {
  displayName: string
  role?: string
}

type ImportMode = 'pdf' | 'excel'

type ImportIssue = {
  fila?: number
  archivo?: string
  cedula?: string
  identificacion?: string
  error?: string
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
}

function importIssueLabel(item: ImportIssue): string {
  const location = item.archivo
    ? `${item.archivo}${item.fila ? ` · registro ${item.fila}` : ''}`
    : `Fila ${valueOrDash(item.fila)}`
  const identification = item.identificacion || item.cedula
  return `${location}${identification ? ` · ${identification}` : ''}`
}

const statusOptions = [
  { value: '', label: 'Todos' },
  { value: 'A', label: 'Activo' },
  { value: 'E', label: 'Egresado' },
  { value: 'G', label: 'Graduado' },
  { value: 'P', label: 'Inactivo' },
  { value: 'R', label: 'Retirado' },
  { value: 'D', label: 'Educación Continua' },
  { value: 'SIN ESTADO', label: 'Sin estado' },
]

export function FechaGradoView({ displayName, role = '' }: Readonly<FechaGradoViewProps>) {
  const isSecretary = role === 'SECRETARIA'
  const visibleStatusOptions = isSecretary
    ? statusOptions.filter((option) => ['G', 'E'].includes(option.value))
    : statusOptions
  const [importMode, setImportMode] = useState<ImportMode>('pdf')
  const [pdfFiles, setPdfFiles] = useState<File[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [downloading, setDownloading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [analysis, setAnalysis] = useState<FechaGradoImportResponse | null>(null)
  const [verificationLoading, setVerificationLoading] = useState(false)
  const [verificationRows, setVerificationRows] = useState<FechaGradoVerificationRow[]>([])
  const [statusFilter, setStatusFilter] = useState(isSecretary ? 'G' : '')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [verificationSummary, setVerificationSummary] = useState<{
    total?: number
    totalPages?: number
    conFecha?: number
    sinFecha?: number
    conSenescyt?: number
    sinSenescyt?: number
  }>({})
  const [summary, setSummary] = useState<{
    procesados?: number
    actualizados?: number
    noEncontrados?: number
  }>({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [editingRow, setEditingRow] = useState<FechaGradoVerificationRow | null>(null)
  const [editValues, setEditValues] = useState({
    fecha_grado: '',
    fecha_emision_senescyt: '',
    cod_refrendacion: '',
    cod_registro: '',
    nomina: '',
  })
  const [savingRow, setSavingRow] = useState(false)

  async function downloadTemplate() {
    setDownloading(true)
    setError('')
    setMessage('')
    try {
      const blob = await downloadFechaGradoTemplate()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'plantilla-fecha-grado-senescyt-datos-estud.xlsx'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la plantilla Excel')
    } finally {
      setDownloading(false)
    }
  }

  function changeImportMode(nextMode: ImportMode) {
    if (nextMode === importMode) return
    setImportMode(nextMode)
    setPdfFiles([])
    setExcelFile(null)
    setAnalysis(null)
    setError('')
    setMessage('')
    setFileInputKey((current) => current + 1)
  }

  async function analyzeDocuments() {
    const hasSelection = importMode === 'pdf' ? pdfFiles.length > 0 : Boolean(excelFile)
    if (!hasSelection) {
      setError(importMode === 'pdf' ? 'Seleccione uno o más documentos PDF de SENESCYT.' : 'Seleccione el archivo Excel de SENESCYT.')
      return
    }
    setAnalyzing(true)
    setAnalysis(null)
    setError('')
    setMessage('')
    try {
      const response = importMode === 'pdf'
        ? await analyzeFechaGradoPdfs(pdfFiles)
        : await analyzeFechaGradoExcel(excelFile as File)
      setAnalysis(response)
      if (response.puede_importar) {
        setMessage('Documentación validada. Revise la vista previa y aplique la carga cuando confirme la información.')
      } else {
        const sourceErrors = response.errores?.slice(0, 4).map((item) => `${importIssueLabel(item)}: ${valueOrDash(item.error)}`) || []
        const missing = response.no_encontrados?.slice(0, 4).map((item) => `${importIssueLabel(item)}: no existe en DATOS_ESTUD`) || []
        setError([...sourceErrors, ...missing].join(' | ') || 'La documentación contiene observaciones que impiden aplicar la carga.')
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo analizar la documentación SENESCYT')
    } finally {
      setAnalyzing(false)
    }
  }

  async function applyDocuments() {
    const hasSelection = importMode === 'pdf' ? pdfFiles.length > 0 : Boolean(excelFile)
    if (!hasSelection || !analysis?.puede_importar) {
      setError('Primero analice la documentación y corrija todas las observaciones.')
      return
    }
    setImporting(true)
    setError('')
    setMessage('')
    try {
      const response = importMode === 'pdf'
        ? await importFechaGradoPdfs(pdfFiles)
        : await importFechaGradoExcel(excelFile as File)
      setAnalysis(response)
      if (!response.ok) {
        const details = response.errores?.slice(0, 6).map((item) => `${importIssueLabel(item)}: ${valueOrDash(item.error)}`).join(' | ')
        setError(details || response.resumen || 'La validación cambió y no fue posible aplicar la carga.')
        return
      }
      const noEncontrados = response.no_encontrados?.length || 0
      setSummary({ procesados: response.procesados, actualizados: response.actualizados, noEncontrados })
      setMessage(response.resumen || 'La información SENESCYT fue actualizada correctamente.')
      setPdfFiles([])
      setExcelFile(null)
      setAnalysis(null)
      setFileInputKey((current) => current + 1)
      await loadVerification(page)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo aplicar la carga SENESCYT')
    } finally {
      setImporting(false)
    }
  }

  const loadVerification = useCallback(async (targetPage: number) => {
    setVerificationLoading(true)
    try {
      const response = await fetchFechaGradoVerification({
        estado: statusFilter,
        page: targetPage,
        pageSize,
      })
      setVerificationRows(response.items || [])
      setVerificationSummary({
        total: response.total,
        totalPages: response.total_pages,
        conFecha: response.con_fecha,
        sinFecha: response.sin_fecha,
        conSenescyt: response.con_senescyt,
        sinSenescyt: response.sin_senescyt,
      })
      setPage(response.page || targetPage)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar la verificación de fecha de grado')
    } finally {
      setVerificationLoading(false)
    }
  }, [pageSize, statusFilter])

  function openEditModal(row: FechaGradoVerificationRow) {
    setEditingRow(row)
    setEditValues({
      fecha_grado: row.fecha_grado || '',
      fecha_emision_senescyt: row.fecha_emision_senescyt || '',
      cod_refrendacion: row.cod_refrendacion || '',
      cod_registro: row.cod_registro || '',
      nomina: row.nomina || '',
    })
    setError('')
    setMessage('')
  }

  async function saveEditModal() {
    if (!editingRow?.codigo_estud) return
    setSavingRow(true)
    setError('')
    setMessage('')
    try {
      const response = await saveFechaGrado({
        items: [
          {
            codigo_estud: editingRow.codigo_estud,
            fecha_grado: editValues.fecha_grado || null,
            fecha_emision_senescyt: editValues.fecha_emision_senescyt || null,
            cod_refrendacion: editValues.cod_refrendacion.trim() || null,
            cod_registro: editValues.cod_registro.trim() || null,
            nomina: editValues.nomina.trim() || null,
          },
        ],
      })
      setMessage(`Información actualizada correctamente. Registros actualizados: ${response.actualizados}.`)
      setEditingRow(null)
      await loadVerification(page)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar la información del estudiante')
    } finally {
      setSavingRow(false)
    }
  }

  useEffect(() => {
    void loadVerification(1)
  }, [loadVerification])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Matrícula</p>
          <h1>Fecha de grado</h1>
          <span>Valide el documento SENESCYT por identificación antes de actualizar DATOS_ESTUD.</span>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>DATOS_ESTUD</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--stats fecha-grado-stats">
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Procesados</p>
          <h2>{formatNumber(summary.procesados)}</h2>
          <small>Registros válidos analizados</small>
        </article>
        <article className="student-card student-card--stat matricula-stat-card">
          <p>Actualizados</p>
          <h2>{formatNumber(summary.actualizados)}</h2>
          <small>Registros DATOS_ESTUD</small>
        </article>
        <article className="student-card student-card--stat matricula-stat-card">
          <p>No encontrados</p>
          <h2>{formatNumber(summary.noEncontrados)}</h2>
          <small>Cédulas no ubicadas</small>
        </article>
      </section>

      <section className="student-grid student-grid--content fecha-grado-grid">
        <article className="student-card student-card--wide fecha-grado-panel">
          <div className="card-head">
            <div>
              <h3>Carga de documentos SENESCYT</h3>
              <span>Identificación + fecha de acta / grado + emisión + código de registro + nómina</span>
            </div>
            <span>La refrendación se cargará desde su documento independiente.</span>
          </div>

          <div className="fecha-grado-source-tabs" role="tablist" aria-label="Origen de documentos SENESCYT">
            <button
              type="button"
              role="tab"
              aria-selected={importMode === 'pdf'}
              className={importMode === 'pdf' ? 'is-active' : ''}
              onClick={() => changeImportMode('pdf')}
              disabled={analyzing || importing}
            >
              Documentos PDF
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={importMode === 'excel'}
              className={importMode === 'excel' ? 'is-active' : ''}
              onClick={() => changeImportMode('excel')}
              disabled={analyzing || importing}
            >
              Plantilla Excel
            </button>
          </div>

          <div className="fecha-grado-import-only">
            {importMode === 'pdf' ? (
              <>
                <div className="fecha-grado-upload-copy">
                  <strong>Nóminas oficiales en PDF</strong>
                  <small>Puede seleccionar hasta 100 documentos en una sola validación.</small>
                </div>

                <label>
                  <span>Documentos PDF</span>
                  <input
                    key={`pdf-${fileInputKey}`}
                    type="file"
                    accept=".pdf,application/pdf"
                    multiple
                    onChange={(event) => {
                      const selectedFiles = Array.from(event.target.files || [])
                      if (selectedFiles.length > 100) {
                        setPdfFiles(selectedFiles.slice(0, 100))
                        setError('Solo se permiten 100 documentos PDF por carga. Se conservaron los primeros 100.')
                      } else {
                        setPdfFiles(selectedFiles)
                        setError('')
                      }
                      setAnalysis(null)
                      setMessage('')
                    }}
                  />
                  <small>{pdfFiles.length ? `${formatNumber(pdfFiles.length)} documento(s) seleccionado(s)` : 'Sin documentos seleccionados'}</small>
                </label>
              </>
            ) : (
              <>
                <button type="button" className="primary-action" onClick={() => void downloadTemplate()} disabled={downloading}>
                  {downloading ? 'Descargando...' : 'Descargar plantilla Excel'}
                </button>

                <label>
                  <span>Archivo Excel</span>
                  <input
                    key={`excel-${fileInputKey}`}
                    type="file"
                    accept=".xlsx,.xlsm"
                    onChange={(event) => {
                      setExcelFile(event.target.files?.[0] || null)
                      setAnalysis(null)
                      setError('')
                      setMessage('')
                    }}
                  />
                </label>
              </>
            )}

            <button
              type="button"
              className="ghost-button"
              onClick={() => void analyzeDocuments()}
              disabled={analyzing || importing || (importMode === 'pdf' ? !pdfFiles.length : !excelFile)}
            >
              {analyzing ? 'Analizando...' : importMode === 'pdf' ? 'Analizar documentos' : 'Analizar archivo'}
            </button>

            <button type="button" className="primary-action" onClick={() => void applyDocuments()} disabled={importing || analyzing || !analysis?.puede_importar}>
              {importing ? 'Aplicando...' : 'Aplicar carga'}
            </button>
          </div>

          {importMode === 'pdf' && pdfFiles.length ? (
            <div className="fecha-grado-selected-files">
              <strong>Archivos preparados</strong>
              <div>
                {pdfFiles.slice(0, 6).map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}
                {pdfFiles.length > 6 ? <span>+ {formatNumber(pdfFiles.length - 6)} archivo(s) adicional(es)</span> : null}
              </div>
            </div>
          ) : null}

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}

          {analysis ? (
            <div className="fecha-grado-analysis">
              <div className="fecha-grado-page-summary fecha-grado-analysis__summary">
                <span>Filas: {formatNumber(analysis.filas_detectadas)}</span>
                <span>Encontrados: {formatNumber(analysis.encontrados)}</span>
                <span>Nuevos: {formatNumber(analysis.nuevos)}</span>
                <span>Con cambios: {formatNumber(analysis.cambios)}</span>
                <span>Sin cambios: {formatNumber(analysis.sin_cambios)}</span>
                <span>No encontrados: {formatNumber(analysis.no_encontrados?.length)}</span>
              </div>

              <div className="fecha-grado-analysis__head">
                <div>
                  <strong>Vista previa</strong>
                  {analysis.origen === 'PDF' ? (
                    <small>
                      {formatNumber(analysis.archivos_procesados)} PDF analizado(s) de {formatNumber(analysis.archivos_detectados)} seleccionado(s)
                    </small>
                  ) : (
                    <small>
                      Hoja {valueOrDash(analysis.hoja)} · encabezados en fila {formatNumber(analysis.fila_encabezado)}
                    </small>
                  )}
                </div>
                <span className={analysis.puede_importar ? 'senescyt-ok-pill' : 'senescyt-warning-pill'}>
                  {analysis.puede_importar ? 'Lista para aplicar' : 'Requiere corrección'}
                </span>
              </div>

              {analysis.nominas_compartidas ? (
                <p className="fecha-grado-analysis__note">
                  {formatNumber(analysis.nominas_compartidas)} nómina(s) agrupan a varios estudiantes. Esto es válido y no genera duplicidad.
                </p>
              ) : null}

              {analysis.advertencias?.length ? (
                <div className="fecha-grado-analysis__warnings">
                  <strong>Observaciones del análisis</strong>
                  <ul>
                    {analysis.advertencias.slice(0, 20).map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}
                  </ul>
                </div>
              ) : null}

              {analysis.errores?.length ? (
                <div className="fecha-grado-analysis__issues" role="alert">
                  <strong>Errores que debe corregir</strong>
                  <ul>
                    {analysis.errores.slice(0, 20).map((item, index) => (
                      <li key={`${item.archivo}-${item.fila}-${item.cedula}-${index}`}>
                        {importIssueLabel(item)}: {valueOrDash(item.error)}
                      </li>
                    ))}
                  </ul>
                  {analysis.errores.length > 20 ? <small>Se muestran los primeros 20 errores.</small> : null}
                </div>
              ) : null}

              {analysis.no_encontrados?.length ? (
                <div className="fecha-grado-analysis__issues" role="alert">
                  <strong>Cédulas no ubicadas en DATOS_ESTUD</strong>
                  <ul>
                    {analysis.no_encontrados.slice(0, 20).map((item, index) => (
                      <li key={`${item.archivo}-${item.fila}-${item.cedula}-${index}`}>
                        {importIssueLabel(item)}: no se encontró el estudiante
                      </li>
                    ))}
                  </ul>
                  {analysis.no_encontrados.length > 20 ? <small>Se muestran las primeras 20 cédulas no encontradas.</small> : null}
                </div>
              ) : null}

              <div className="matricula-table-wrap fecha-grado-analysis__table-wrap">
                <table className="matricula-table fecha-grado-analysis__table">
                  <thead>
                    <tr>
                      <th>Origen</th>
                      <th>Identificación</th>
                      <th>Estudiante</th>
                      <th>Fecha de acta / grado</th>
                      <th>Emisión SENESCYT</th>
                      <th>Código de registro</th>
                      <th>Nómina</th>
                      <th>Resultado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(analysis.vista_previa || []).map((row) => (
                      <tr key={`${row.archivo}-${row.fila}-${row.identificacion || row.cedula}`}>
                        <td>
                          <div className="fecha-grado-origin-cell">
                            <strong>{analysis.origen === 'PDF' ? valueOrDash(row.archivo) : 'Excel'}</strong>
                            <small>
                              {analysis.origen === 'PDF'
                                ? `Registro ${valueOrDash(row.registro_documento || row.fila)}${row.metodo_extraccion ? ` · ${row.metodo_extraccion.replaceAll('_', ' ')}` : ''}`
                                : `Fila ${valueOrDash(row.fila)}`}
                            </small>
                          </div>
                        </td>
                        <td>{valueOrDash(row.identificacion || row.cedula)}</td>
                        <td>
                          <div className="fecha-grado-student-cell">
                            <strong>{valueOrDash(row.nombres)}</strong>
                            <small>{row.codigo_estud ? `Código ${row.codigo_estud}` : 'Sin coincidencia'}</small>
                          </div>
                        </td>
                        <td>{valueOrDash(row.fecha_grado)}</td>
                        <td>{valueOrDash(row.fecha_emision_senescyt)}</td>
                        <td>{valueOrDash(row.cod_registro)}</td>
                        <td>{valueOrDash(row.nomina)}</td>
                        <td>
                          <strong className={`fecha-grado-analysis__status fecha-grado-analysis__status--${String(row.estado || '').toLowerCase()}`}>
                            {valueOrDash(row.estado).replaceAll('_', ' ')}
                          </strong>
                          {row.campos_modificados?.length ? <small>{row.campos_modificados.join(', ')}</small> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {analysis.vista_previa_limitada ? <small>La vista previa muestra los primeros 1.000 registros.</small> : null}
            </div>
          ) : null}
        </article>
      </section>

      <section className="student-grid student-grid--content fecha-grado-grid">
        <article className="student-card student-card--wide fecha-grado-panel">
          <div className="card-head">
            <h3>Verificación por estado</h3>
            <span>{verificationLoading ? 'Cargando...' : `${formatNumber(verificationSummary.total)} registro(s)`}</span>
          </div>

          <div className="fecha-grado-verification-bar">
            <label>
              <span>Estado</span>
              <select
                value={statusFilter}
                onChange={(event) => {
                  setPage(1)
                  setStatusFilter(event.target.value)
                }}
              >
                {visibleStatusOptions.map((option) => (
                  <option key={option.value || 'todos'} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Registros por página</span>
              <select
                value={pageSize}
                onChange={(event) => {
                  setPage(1)
                  setPageSize(Number(event.target.value))
                }}
              >
                {[10, 25, 50, 100, 200].map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="primary-action fecha-grado-refresh-button" onClick={() => void loadVerification(page)} disabled={verificationLoading}>
              {verificationLoading ? 'Actualizando información...' : 'Actualizar información'}
            </button>
          </div>

          <div className="fecha-grado-page-summary">
            <span>Total: {formatNumber(verificationSummary.total)}</span>
            <span>Con fecha: {formatNumber(verificationSummary.conFecha)}</span>
            <span>Sin fecha: {formatNumber(verificationSummary.sinFecha)}</span>
            <span>SENESCYT completo: {formatNumber(verificationSummary.conSenescyt)}</span>
            <span>SENESCYT pendiente: {formatNumber(verificationSummary.sinSenescyt)}</span>
          </div>

          <div className="matricula-table-wrap fecha-grado-table-wrap">
            <table className="matricula-table fecha-grado-table fecha-grado-verification-table">
              <colgroup>
                <col className="fecha-grado-verification-col-name" />
                <col className="fecha-grado-verification-col-id" />
                <col className="fecha-grado-verification-col-state" />
                <col className="fecha-grado-verification-col-date" />
                <col className="fecha-grado-verification-col-date" />
                <col className="fecha-grado-verification-col-code" />
                <col className="fecha-grado-verification-col-roster" />
                <col className="fecha-grado-verification-col-code" />
              </colgroup>
              <thead>
                <tr>
                  <th>Nombres</th>
                  <th>Cédula</th>
                  <th>Estado</th>
                  <th>Fecha de acta / grado</th>
                  <th>Emisión SENESCYT</th>
                  <th>Código de registro</th>
                  <th>Nómina</th>
                  <th>Cod. refrendación</th>
                </tr>
              </thead>
              <tbody>
                {verificationRows.map((row) => (
                  <tr key={`${row.codigo_estud}-${row.cedula || 'sin-cedula'}`}>
                    <td>
                      <div className="fecha-grado-student-cell fecha-grado-student-cell--action">
                        <div>
                          <strong>{valueOrDash(row.nombres)}</strong>
                          <small>Código {valueOrDash(row.codigo_estud)}</small>
                        </div>
                        <button type="button" className="fecha-grado-row-action" onClick={() => openEditModal(row)}>
                          Actualizar
                        </button>
                      </div>
                    </td>
                    <td>{valueOrDash(row.cedula)}</td>
                    <td>
                      <div className="fecha-grado-career-cell">
                        <span>{valueOrDash(row.estado_nombre)}</span>
                        <small>{valueOrDash(row.estado_codigo)}</small>
                      </div>
                    </td>
                    <td>{valueOrDash(row.fecha_grado)}</td>
                    <td>{valueOrDash(row.fecha_emision_senescyt)}</td>
                    <td>{valueOrDash(row.cod_registro)}</td>
                    <td>{valueOrDash(row.nomina)}</td>
                    <td>{valueOrDash(row.cod_refrendacion)}</td>
                  </tr>
                ))}
                {verificationRows.length === 0 ? (
                  <tr>
                    <td colSpan={8}>No hay registros para el estado seleccionado.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="fecha-grado-pagination">
            <button
              type="button"
              className="ghost-button"
              onClick={() => void loadVerification(Math.max(page - 1, 1))}
              disabled={verificationLoading || page <= 1}
            >
              Anterior
            </button>
            <span>
              Página {formatNumber(page)} de {formatNumber(verificationSummary.totalPages)}
            </span>
            <button
              type="button"
              className="ghost-button"
              onClick={() => void loadVerification(Math.min(page + 1, verificationSummary.totalPages || 1))}
              disabled={verificationLoading || page >= (verificationSummary.totalPages || 1)}
            >
              Siguiente
            </button>
          </div>
        </article>
      </section>

      {editingRow ? (
        <div className="fecha-grado-modal-backdrop">
          <section className="fecha-grado-modal" role="dialog" aria-modal="true" aria-labelledby="fecha-grado-modal-title">
            <div className="fecha-grado-modal__header">
              <div>
                <span>Actualizar información</span>
                <h3 id="fecha-grado-modal-title">{valueOrDash(editingRow.nombres)}</h3>
                <small>
                  Cédula {valueOrDash(editingRow.cedula)} · Código {valueOrDash(editingRow.codigo_estud)}
                </small>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingRow(null)} disabled={savingRow}>
                Cerrar
              </button>
            </div>

            <div className="fecha-grado-modal__body">
              <label>
                <span>Fecha de acta / grado</span>
                <input
                  type="date"
                  value={editValues.fecha_grado}
                  onChange={(event) => setEditValues((current) => ({ ...current, fecha_grado: event.target.value }))}
                />
              </label>
              <label>
                <span>Fecha emisión SENESCYT</span>
                <input
                  type="date"
                  value={editValues.fecha_emision_senescyt}
                  onChange={(event) => setEditValues((current) => ({ ...current, fecha_emision_senescyt: event.target.value }))}
                />
              </label>
              <label>
                <span>Código de registro SENESCYT</span>
                <input
                  type="text"
                  maxLength={50}
                  value={editValues.cod_registro}
                  onChange={(event) => setEditValues((current) => ({ ...current, cod_registro: event.target.value.slice(0, 50) }))}
                />
              </label>
              <label>
                <span>Nómina</span>
                <input
                  type="text"
                  maxLength={50}
                  value={editValues.nomina}
                  onChange={(event) => setEditValues((current) => ({ ...current, nomina: event.target.value.slice(0, 50) }))}
                />
              </label>
              <label className="fecha-grado-modal__field--wide">
                <span>Código de refrendación</span>
                <input
                  type="text"
                  maxLength={50}
                  value={editValues.cod_refrendacion}
                  onChange={(event) => setEditValues((current) => ({ ...current, cod_refrendacion: event.target.value.slice(0, 50) }))}
                />
                <small>Este dato corresponde al documento de refrendación y no se modifica con la carga SENESCYT.</small>
              </label>
            </div>

            <div className="fecha-grado-modal__actions">
              <button type="button" className="ghost-button" onClick={() => setEditingRow(null)} disabled={savingRow}>
                Cancelar
              </button>
              <button type="button" className="primary-action" onClick={() => void saveEditModal()} disabled={savingRow}>
                {savingRow ? 'Guardando...' : 'Guardar información'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
