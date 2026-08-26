import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  fetchIntegrationDatabaseEvents,
  fetchIntegrationHistoryDetail,
  fetchIntegrationHistorySummary,
  fetchIntegrationTeacherReportEvents,
  type IntegrationHistoryQuery,
} from '../../lib/api'
import type {
  IntegrationDatabaseEvent,
  IntegrationHistoryDetail,
  IntegrationHistoryPage,
  IntegrationHistorySummary,
  IntegrationTeacherReportEvent,
} from '../../types/app'

type HistoryTab = 'database' | 'teacher-report'

type HistoricoIntegracionesViewProps = {
  displayName: string
}

const EMPTY_PAGE = {
  items: [],
  page: 1,
  page_size: 25,
  total: 0,
  total_pages: 1,
  has_previous: false,
  has_next: false,
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudo consultar el registro de auditoría.'
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatDate(value?: string | null): string {
  if (!value) return 'Sin registro'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date)
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Sin registro'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function Pagination({
  page,
  totalPages,
  total,
  loading,
  onPage,
}: {
  page: number
  totalPages: number
  total: number
  loading: boolean
  onPage: (page: number) => void
}) {
  return (
    <div className="integration-history-pagination" aria-label="Paginación de movimientos de auditoría">
      <strong>{formatNumber(total)} movimiento(s)</strong>
      <div>
        <button type="button" disabled={loading || page <= 1} onClick={() => onPage(1)}>
          Primero
        </button>
        <button type="button" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>
          Anterior
        </button>
        <span>Página {page} de {Math.max(totalPages, 1)}</span>
        <button type="button" disabled={loading || page >= totalPages} onClick={() => onPage(page + 1)}>
          Siguiente
        </button>
        <button type="button" disabled={loading || page >= totalPages} onClick={() => onPage(totalPages)}>
          Último
        </button>
      </div>
    </div>
  )
}

function DetailModal({
  detail,
  loading,
  error,
  onClose,
}: {
  detail: IntegrationHistoryDetail | null
  loading: boolean
  error: string
  onClose: () => void
}) {
  const entries = detail ? Object.entries(detail.event) : []
  const jsonKeys = new Set(['ColumnasAfectadas', 'ClavesAfectadas', 'DatosAntes', 'DatosDespues', 'PeriodosJson', 'MetadatosJson'])

  return (
    <div className="integration-history-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="integration-history-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="integration-history-detail-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span>Detalle auditable</span>
            <h2 id="integration-history-detail-title">
              {detail?.kind === 'database' ? 'Movimiento de base de datos' : 'Informe de cumplimiento docente'}
            </h2>
          </div>
          <button type="button" onClick={onClose}>Cerrar</button>
        </header>

        {loading ? <p className="integration-history-modal-state">Consultando detalle...</p> : null}
        {error ? <p className="integration-history-alert integration-history-alert--error">{error}</p> : null}
        {!loading && !error && detail ? (
          <div className="integration-history-detail-grid">
            {entries.map(([key, value]) => (
              <div
                className={jsonKeys.has(key) || typeof value === 'object' ? 'integration-history-detail-field integration-history-detail-field--wide' : 'integration-history-detail-field'}
                key={key}
              >
                <span>{key}</span>
                {jsonKeys.has(key) || typeof value === 'object' ? (
                  <pre>{displayValue(value)}</pre>
                ) : (
                  <strong>{displayValue(value)}</strong>
                )}
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  )
}

export function HistoricoIntegracionesView({ displayName }: HistoricoIntegracionesViewProps) {
  const [activeTab, setActiveTab] = useState<HistoryTab>('database')
  const [summary, setSummary] = useState<IntegrationHistorySummary | null>(null)
  const [databasePage, setDatabasePage] = useState<IntegrationHistoryPage<IntegrationDatabaseEvent>>(EMPTY_PAGE)
  const [reportPage, setReportPage] = useState<IntegrationHistoryPage<IntegrationTeacherReportEvent>>(EMPTY_PAGE)
  const [loading, setLoading] = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [operation, setOperation] = useState<IntegrationHistoryQuery['operation']>('')
  const [database, setDatabase] = useState('')
  const [stage, setStage] = useState<IntegrationHistoryQuery['stage']>('')
  const [status, setStatus] = useState<IntegrationHistoryQuery['status']>('')
  const [appliedQuery, setAppliedQuery] = useState<IntegrationHistoryQuery>({ page: 1, pageSize: 25 })
  const [detail, setDetail] = useState<IntegrationHistoryDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true)
    try {
      setSummary(await fetchIntegrationHistorySummary())
    } catch (apiError) {
      setError(errorMessage(apiError))
    } finally {
      setSummaryLoading(false)
    }
  }, [])

  const loadEvents = useCallback(async (tab: HistoryTab, query: IntegrationHistoryQuery) => {
    setLoading(true)
    setError('')
    try {
      if (tab === 'database') {
        setDatabasePage(await fetchIntegrationDatabaseEvents(query))
      } else {
        setReportPage(await fetchIntegrationTeacherReportEvents(query))
      }
    } catch (apiError) {
      setError(errorMessage(apiError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSummary()
  }, [loadSummary])

  useEffect(() => {
    void loadEvents(activeTab, appliedQuery)
  }, [activeTab, appliedQuery, loadEvents])

  const pageData = activeTab === 'database' ? databasePage : reportPage
  const availableDatabases = useMemo(() => summary?.databases ?? [], [summary])

  const applyFilters = (event?: FormEvent) => {
    event?.preventDefault()
    setAppliedQuery({
      page: 1,
      pageSize: 25,
      search: search.trim(),
      dateFrom,
      dateTo,
      operation: activeTab === 'database' ? operation : '',
      database: activeTab === 'database' ? database : '',
      stage: activeTab === 'teacher-report' ? stage : '',
      status: activeTab === 'teacher-report' ? status : '',
    })
  }

  const clearFilters = () => {
    setSearch('')
    setDateFrom('')
    setDateTo('')
    setOperation('')
    setDatabase('')
    setStage('')
    setStatus('')
    setAppliedQuery({ page: 1, pageSize: 25 })
  }

  const changeTab = (tab: HistoryTab) => {
    setActiveTab(tab)
    setAppliedQuery({ page: 1, pageSize: 25 })
  }

  const changePage = (page: number) => {
    setAppliedQuery((current) => ({ ...current, page }))
  }

  const refresh = () => {
    void loadSummary()
    void loadEvents(activeTab, appliedQuery)
  }

  const openDetail = async (kind: HistoryTab, eventId: number) => {
    setDetailOpen(true)
    setDetail(null)
    setDetailError('')
    setDetailLoading(true)
    try {
      setDetail(await fetchIntegrationHistoryDetail(kind, eventId))
    } catch (apiError) {
      setDetailError(errorMessage(apiError))
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <main className="integration-history-page">
      <header className="integration-history-hero">
        <div>
          <span>AUDITORÍA</span>
          <h1>Auditoría</h1>
          <p>Registro central de cambios en las bases de datos y del ciclo documental de los informes docentes.</p>
        </div>
        <div className="integration-history-user">
          <strong>{displayName}</strong>
          <span>Consulta de movimientos</span>
        </div>
      </header>

      <section className="integration-history-summary" aria-label="Resumen de auditoría">
        <article>
          <span>Inserciones · 24 horas</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.changes_last_24_hours.inserts ?? 0)}</strong>
        </article>
        <article>
          <span>Actualizaciones · 24 horas</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.changes_last_24_hours.updates ?? 0)}</strong>
        </article>
        <article>
          <span>Eliminaciones · 24 horas</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.changes_last_24_hours.deletes ?? 0)}</strong>
        </article>
        <article>
          <span>Informes generados · 30 días</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.teacher_reports_last_30_days.generated ?? 0)}</strong>
        </article>
        <article>
          <span>Informes firmados</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.teacher_reports_last_30_days.signed ?? 0)}</strong>
        </article>
        <article>
          <span>Informes archivados</span>
          <strong>{summaryLoading ? '...' : formatNumber(summary?.teacher_reports_last_30_days.archived ?? 0)}</strong>
        </article>
      </section>

      <nav className="integration-history-tabs" aria-label="Secciones de auditoría">
        <button
          type="button"
          className={activeTab === 'database' ? 'is-active' : ''}
          onClick={() => changeTab('database')}
        >
          Movimientos
        </button>
        <button
          type="button"
          className={activeTab === 'teacher-report' ? 'is-active' : ''}
          onClick={() => changeTab('teacher-report')}
        >
          Documentos docentes
        </button>
      </nav>

      <section className="integration-history-workspace">
        <div className="integration-history-section-head">
          <div>
            <span>{activeTab === 'database' ? 'AUDITORÍA DML' : 'CONTROL DOCUMENTAL'}</span>
            <h2>{activeTab === 'database' ? 'Inserciones, actualizaciones y eliminaciones' : 'Ciclo del informe de cumplimiento docente'}</h2>
          </div>
          <button type="button" onClick={refresh} disabled={loading || summaryLoading}>Actualizar</button>
        </div>

        <form className="integration-history-filters" onSubmit={applyFilters}>
          <label className="integration-history-search">
            <span>Buscar</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={activeTab === 'database' ? 'Tabla, usuario, ruta o solicitud' : 'Docente, cédula, materia o archivo'}
            />
          </label>
          {activeTab === 'database' ? (
            <>
              <label>
                <span>Base de datos</span>
                <select value={database} onChange={(event) => setDatabase(event.target.value)}>
                  <option value="">Todas</option>
                  {availableDatabases.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label>
                <span>Operación</span>
                <select value={operation} onChange={(event) => setOperation(event.target.value as IntegrationHistoryQuery['operation'])}>
                  <option value="">Todas</option>
                  <option value="INSERT">Inserción</option>
                  <option value="UPDATE">Actualización</option>
                  <option value="DELETE">Eliminación</option>
                </select>
              </label>
            </>
          ) : (
            <>
              <label>
                <span>Etapa</span>
                <select value={stage} onChange={(event) => setStage(event.target.value as IntegrationHistoryQuery['stage'])}>
                  <option value="">Todas</option>
                  <option value="GENERADO">Generado</option>
                  <option value="FIRMADO">Firmado</option>
                  <option value="ARCHIVADO">Archivado</option>
                  <option value="ERROR">Error</option>
                </select>
              </label>
              <label>
                <span>Resultado</span>
                <select value={status} onChange={(event) => setStatus(event.target.value as IntegrationHistoryQuery['status'])}>
                  <option value="">Todos</option>
                  <option value="EXITOSO">Exitoso</option>
                  <option value="ERROR">Error</option>
                </select>
              </label>
            </>
          )}
          <label>
            <span>Desde</span>
            <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            <span>Hasta</span>
            <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
          <div className="integration-history-filter-actions">
            <button type="submit" className="integration-history-primary" disabled={loading}>Consultar</button>
            <button type="button" onClick={clearFilters} disabled={loading}>Limpiar</button>
          </div>
        </form>

        {error ? <p className="integration-history-alert integration-history-alert--error">{error}</p> : null}

        <div className="integration-history-table-wrap">
          {activeTab === 'database' ? (
            <table className="integration-history-table">
              <thead>
                <tr>
                  <th>Fecha y hora</th>
                  <th>Base de datos</th>
                  <th>Objeto</th>
                  <th>Operación</th>
                  <th>Filas</th>
                  <th>Usuario</th>
                  <th>Solicitud</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {databasePage.items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDate(item.fecha_ecuador)}</td>
                    <td><strong>{item.base_datos}</strong></td>
                    <td>{item.esquema}.{item.objeto}</td>
                    <td><span className={`integration-history-badge integration-history-badge--${item.operacion.toLowerCase()}`}>{item.operacion}</span></td>
                    <td>{formatNumber(item.cantidad_filas)}</td>
                    <td>{item.usuario}<small>{item.rol || item.origen || ''}</small></td>
                    <td>{item.solicitud || 'Sin solicitud'}<small>{[item.metodo, item.ruta].filter(Boolean).join(' ')}</small></td>
                    <td><button type="button" onClick={() => void openDetail('database', item.id)}>Ver</button></td>
                  </tr>
                ))}
                {!loading && databasePage.items.length === 0 ? (
                  <tr><td colSpan={8} className="integration-history-empty">No existen movimientos con los filtros seleccionados.</td></tr>
                ) : null}
              </tbody>
            </table>
          ) : (
            <table className="integration-history-table integration-history-table--reports">
              <thead>
                <tr>
                  <th>Fecha y hora</th>
                  <th>Docente</th>
                  <th>Materia</th>
                  <th>Documento</th>
                  <th>Etapa</th>
                  <th>Resultado</th>
                  <th>Usuario</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {reportPage.items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDate(item.fecha_ecuador)}</td>
                    <td><strong>{item.nombre_docente || 'Sin nombre'}</strong><small>{item.cedula_docente || item.codigo_docente || ''}</small></td>
                    <td>{item.nombre_materia || 'Sin materia'}<small>{item.codigo_materia || ''}</small></td>
                    <td>{item.nombre_archivo || item.tipo_documento}<small>{item.ruta_documento || ''}</small></td>
                    <td><span className="integration-history-badge">{item.etapa}</span></td>
                    <td><span className={`integration-history-badge integration-history-badge--${item.estado === 'ERROR' ? 'delete' : 'success'}`}>{item.estado}</span></td>
                    <td>{item.usuario}<small>{item.rol || ''}</small></td>
                    <td><button type="button" onClick={() => void openDetail('teacher-report', item.id)}>Ver</button></td>
                  </tr>
                ))}
                {!loading && reportPage.items.length === 0 ? (
                  <tr><td colSpan={8} className="integration-history-empty">No existen informes con los filtros seleccionados.</td></tr>
                ) : null}
              </tbody>
            </table>
          )}
          {loading ? <div className="integration-history-loading">Consultando movimientos...</div> : null}
        </div>

        <Pagination
          page={pageData.page}
          totalPages={pageData.total_pages}
          total={pageData.total}
          loading={loading}
          onPage={changePage}
        />

        <footer className="integration-history-coverage">
          Cobertura DML: {formatNumber(summary?.coverage.installed ?? 0)} objeto(s) auditado(s)
          {summary?.coverage.pending ? ` · ${formatNumber(summary.coverage.pending)} pendiente(s)` : ''}.
        </footer>
      </section>

      {detailOpen ? (
        <DetailModal
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={() => setDetailOpen(false)}
        />
      ) : null}
    </main>
  )
}
