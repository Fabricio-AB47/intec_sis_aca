import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react'
import { loadAdministrativeSource, type PendingPage, type QueueSource } from './academicPendingSources'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'No fue posible consultar esta fuente.'
}

export function AdministrativePendingDetails({ source, refreshToken, onOpenModule }: {
  source: QueueSource; refreshToken: number; onOpenModule: () => void
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState({ query: '', page: 1, revision: 0 })
  const [result, setResult] = useState<PendingPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      try {
        const payload = await loadAdministrativeSource(source.key, filter.query, filter.page, controller.signal)
        if (!controller.signal.aborted) setResult(payload)
      } catch (cause: unknown) {
        if (!controller.signal.aborted) { setError(message(cause)); setResult(null) }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    queueMicrotask(() => { if (!controller.signal.aborted) void load() })
    return () => controller.abort()
  }, [source.key, filter, refreshToken])

  function search(event: FormEvent) {
    event.preventDefault()
    changePage(1, query.trim())
  }
  function changePage(page: number, nextQuery = filter.query) {
    setLoading(true)
    setError('')
    setResult(null)
    setFilter((previous) => ({ query: nextQuery, page, revision: previous.revision + 1 }))
  }

  return <section className="unified-alert-center__section administrative-pending-details" aria-label={source.title}>
    <header>
      <h3>{source.title}</h3>
      <button type="button" className="ghost-button" onClick={onOpenModule}>Abrir {source.key === 'secretaria' ? 'Secretaría General' : 'solicitudes'}<ArrowRight size={16} /></button>
    </header>
    <form onSubmit={search} className="academic-pending-search">
      <label>Buscar estudiante<input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={120} placeholder="Nombre, identificación o código" /></label>
      <button type="submit" className="ghost-button" disabled={loading}><Search size={16} />Buscar</button>
    </form>
    <div aria-live="polite" aria-busy={loading}>
      {loading ? <p>Consultando pendientes...</p> : null}
      {error ? <div role="alert"><p className="form-error">{error}</p><button className="ghost-button" onClick={() => changePage(filter.page)}><RefreshCw size={16} />Reintentar</button></div> : null}
      {result ? <>
        <p>{result.total.toLocaleString('es-EC')} {source.unit}{filter.query ? ' en esta búsqueda' : ''}</p>
        <div className="academic-pending-table">
          <table><thead><tr><th>Estudiante</th><th>Carrera</th><th>Período</th><th>Pendiente</th></tr></thead>
            <tbody>{result.items.map((item) => <tr key={item.id}>
              <td><strong>{item.student}</strong><small>{item.identification} · {source.key === 'secretaria' ? 'Código' : 'Solicitud'} {item.id}</small></td>
              <td>{item.career || 'Sin carrera registrada'}</td><td>{item.period || 'Sin período registrado'}</td><td>{item.pending}</td>
            </tr>)}{result.items.length === 0 ? <tr><td colSpan={4}>No hay pendientes con estos criterios.</td></tr> : null}</tbody>
          </table>
        </div>
        <nav aria-label="Páginas de pendientes" className="academic-pending-pagination">
          <button className="ghost-button academic-icon-button" aria-label="Página anterior" title="Página anterior" disabled={loading || result.page <= 1} onClick={() => changePage(result.page - 1)}><ChevronLeft size={18} /></button>
          <span>Página {result.page} de {result.pages}</span>
          <button className="ghost-button academic-icon-button" aria-label="Página siguiente" title="Página siguiente" disabled={loading || result.page >= result.pages} onClick={() => changePage(result.page + 1)}><ChevronRight size={18} /></button>
        </nav>
      </> : null}
    </div>
  </section>
}
