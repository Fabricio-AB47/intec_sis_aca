import { useCallback, useEffect, useState } from 'react'

import { downloadFechaGradoTemplate, fetchFechaGradoVerification, importFechaGradoExcel, saveFechaGrado } from '../../lib/api'
import type { FechaGradoVerificationRow } from '../../types/app'

type FechaGradoViewProps = {
  displayName: string
  role?: string
}

function formatNumber(value?: number): string {
  return new Intl.NumberFormat('es-EC').format(value ?? 0)
}

function valueOrDash(value?: string | number | null): string {
  const text = String(value ?? '').trim()
  return text || '-'
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
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [importing, setImporting] = useState(false)
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

  async function uploadExcel() {
    if (!excelFile) {
      setError('Selecciona un archivo Excel para importar.')
      return
    }
    setImporting(true)
    setError('')
    setMessage('')
    try {
      const response = await importFechaGradoExcel(excelFile)
      if (!response.ok) {
        const details = response.errores?.slice(0, 6).map((item) => `Fila ${item.fila}: ${item.error}`).join(' | ')
        setError(details || 'El Excel contiene errores de validación.')
        return
      }
      const noEncontrados = response.no_encontrados?.length || 0
      setSummary({
        procesados: response.procesados,
        actualizados: response.actualizados,
        noEncontrados,
      })
      setMessage(response.resumen || `Procesados: ${response.procesados}. Actualizados: ${response.actualizados}. No encontrados: ${noEncontrados}.`)
      if (noEncontrados) {
        const details = response.no_encontrados?.slice(0, 6).map((item) => `Fila ${item.fila}: ${item.cedula}`).join(' | ')
        setError(`Cédulas no encontradas en DATOS_ESTUD: ${details}`)
      }
      setExcelFile(null)
      await loadVerification(page)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo importar el Excel')
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
          <p className="eyebrow">Matricula</p>
          <h1>Fecha de grado</h1>
          <span>Carga masiva por DATOS_ESTUD usando cédula, fecha de grado, emisión SENESCYT y refrendación.</span>
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
          <small>Filas válidas del Excel</small>
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
            <h3>Carga por Excel</h3>
            <span>cedula + fecha_grado + fecha_emision_senescyt + cod_refrendacion</span>
          </div>

          <div className="fecha-grado-import-only">
            <button type="button" className="primary-action" onClick={() => void downloadTemplate()} disabled={downloading}>
              {downloading ? 'Descargando...' : 'Descargar plantilla Excel'}
            </button>

            <label>
              <span>Archivo Excel</span>
              <input
                type="file"
                accept=".xlsx,.xlsm"
                onChange={(event) => setExcelFile(event.target.files?.[0] || null)}
              />
            </label>

            <button type="button" className="primary-action" onClick={() => void uploadExcel()} disabled={importing || !excelFile}>
              {importing ? 'Validando...' : 'Cargar Excel'}
            </button>
          </div>

          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
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
          </div>

          <div className="matricula-table-wrap fecha-grado-table-wrap">
            <table className="matricula-table fecha-grado-table fecha-grado-verification-table">
              <colgroup>
                <col className="fecha-grado-verification-col-name" />
                <col className="fecha-grado-verification-col-id" />
                <col className="fecha-grado-verification-col-state" />
                <col className="fecha-grado-verification-col-date" />
                <col className="fecha-grado-verification-col-date" />
                <col className="fecha-grado-verification-col-id" />
              </colgroup>
              <thead>
                <tr>
                  <th>Nombres</th>
                  <th>Cédula</th>
                  <th>Estado</th>
                  <th>Fecha de grado</th>
                  <th>Emisión SENESCYT</th>
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
                    <td>{valueOrDash(row.cod_refrendacion)}</td>
                  </tr>
                ))}
                {verificationRows.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No hay registros para el estado seleccionado.</td>
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
                <span>Fecha de grado</span>
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
                <span>Código de refrendación</span>
                <input
                  type="text"
                  maxLength={50}
                  value={editValues.cod_refrendacion}
                  onChange={(event) => setEditValues((current) => ({ ...current, cod_refrendacion: event.target.value.slice(0, 50) }))}
                />
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
