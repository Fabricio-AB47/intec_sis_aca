import { useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  fetchModernizedLegacyReportsCatalog,
  fetchSisAcademicoV1Artifacts,
  fetchSisAcademicoV1Modules,
} from '../../lib/api'
import type {
  ModernizedLegacyReport,
  ModernizedLegacyReportsCatalogResponse,
  SisAcademicoV1Artifact,
  SisAcademicoV1ArtifactsResponse,
  SisAcademicoV1Module,
  SisAcademicoV1ModulesResponse,
} from '../../types/app'

type SisAcademicoV1CloneViewProps = {
  displayName: string
  onOpenSection: (sectionKey?: string) => void
}

type HubTab = 'modulos' | 'total' | 'reportes' | 'plan'

function coverageLabel(value: string): string {
  if (value === 'base') return 'Base migrada'
  if (value === 'partial') return 'Parcial'
  if (value === 'pending') return 'Pendiente'
  if (value === 'excluded') return 'No migrable'
  if (value === 'modernizado') return 'Modernizado'
  if (value === 'pendiente') return 'Pendiente'
  return value || 'Sin estado'
}

function coverageClass(value: string): string {
  if (value === 'base' || value === 'modernizado') return 'status-pill is-ok'
  if (value === 'partial') return 'status-pill is-warning'
  if (value === 'excluded') return 'status-pill is-muted'
  return 'status-pill'
}

function moduleSearchText(module: SisAcademicoV1Module): string {
  return [
    module.title,
    module.description,
    module.coverage,
    module.notes,
    ...module.tables,
    ...module.source_paths,
    ...module.modern_sections,
    ...module.modern_routes,
  ].join(' ').toLowerCase()
}

function modernReportSearchText(report: ModernizedLegacyReport): string {
  return [
    report.title,
    report.category,
    report.modern_equivalent,
    report.migration_status,
    report.notes,
    ...report.legacy_rpt,
    ...report.legacy_pages,
    ...report.source_tables,
    ...report.legacy_filters,
    ...report.modern_format,
  ].join(' ').toLowerCase()
}

function artifactSearchText(artifact: SisAcademicoV1Artifact): string {
  return [
    artifact.path,
    artifact.file_name,
    artifact.extension,
    artifact.module_key,
    artifact.module_title,
    artifact.coverage,
  ].join(' ').toLowerCase()
}

function sectionLabel(section: string): string {
  return section
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function SisAcademicoV1CloneView({ displayName, onOpenSection }: Readonly<SisAcademicoV1CloneViewProps>) {
  const [data, setData] = useState<SisAcademicoV1ModulesResponse | null>(null)
  const [artifactData, setArtifactData] = useState<SisAcademicoV1ArtifactsResponse | null>(null)
  const [modernReportsData, setModernReportsData] = useState<ModernizedLegacyReportsCatalogResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<HubTab>('modulos')
  const [query, setQuery] = useState('')
  const [coverage, setCoverage] = useState('todos')
  const [artifactQuery, setArtifactQuery] = useState('')
  const [artifactCoverage, setArtifactCoverage] = useState('todos')
  const [artifactExtension, setArtifactExtension] = useState('todos')
  const [reportQuery, setReportQuery] = useState('')
  const [reportStatus, setReportStatus] = useState('todos')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [modulesPayload, artifactsPayload, reportsPayload] = await Promise.all([
        fetchSisAcademicoV1Modules(),
        fetchSisAcademicoV1Artifacts(),
        fetchModernizedLegacyReportsCatalog(),
      ])
      setData(modulesPayload)
      setArtifactData(artifactsPayload)
      setModernReportsData(reportsPayload)
    } catch (apiError) {
      setError(apiError instanceof ApiError ? apiError.message : 'No se pudo cargar el mapa de SisAcademicoV1.')
      setData(null)
      setArtifactData(null)
      setModernReportsData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const modules = useMemo(() => {
    const cleaned = query.trim().toLowerCase()
    return (data?.modules || []).filter((module) => {
      const matchesCoverage = coverage === 'todos' || module.coverage === coverage
      const matchesQuery = !cleaned || moduleSearchText(module).includes(cleaned)
      return matchesCoverage && matchesQuery
    })
  }, [coverage, data, query])

  const modernReports = useMemo(() => {
    const cleaned = reportQuery.trim().toLowerCase()
    return (modernReportsData?.reports || []).filter((report) => {
      const matchesStatus = reportStatus === 'todos' || report.migration_status === reportStatus
      const matchesQuery = !cleaned || modernReportSearchText(report).includes(cleaned)
      return matchesStatus && matchesQuery
    })
  }, [modernReportsData, reportQuery, reportStatus])

  const artifacts = useMemo(() => {
    const cleaned = artifactQuery.trim().toLowerCase()
    return (artifactData?.artifacts || []).filter((artifact) => {
      const matchesCoverage = artifactCoverage === 'todos' || artifact.coverage === artifactCoverage
      const matchesExtension = artifactExtension === 'todos' || artifact.extension === artifactExtension
      const matchesQuery = !cleaned || artifactSearchText(artifact).includes(cleaned)
      return matchesCoverage && matchesExtension && matchesQuery
    })
  }, [artifactCoverage, artifactData, artifactExtension, artifactQuery])

  const artifactExtensions = useMemo(() => {
    return Object.keys(artifactData?.totals.by_extension || {}).sort()
  }, [artifactData])

  const shortcuts = useMemo(() => {
    const sectionMap = new Map<string, { section: string; modules: string[] }>()
    for (const module of data?.modules || []) {
      for (const section of module.available_sections) {
        const current = sectionMap.get(section) || { section, modules: [] }
        current.modules.push(module.title)
        sectionMap.set(section, current)
      }
    }
    return Array.from(sectionMap.values()).sort((left, right) => left.section.localeCompare(right.section))
  }, [data])

  const planSteps = [
    {
      title: '1. Base compatible',
      detail: 'Vistas sisv1 sobre INTECBDD para consultar datos heredados sin tocar la base principal.',
      state: 'Hecho',
    },
    {
      title: '2. Módulos operativos',
      detail: 'Cada pantalla V1 se conecta a una sección moderna existente o a una ruta nueva del backend.',
      state: 'En avance',
    },
    {
      title: '3. Reportes modernizados',
      detail: 'Los reportes heredados se reemplazan por PDF/Excel/HTML generados con consultas parametrizadas.',
      state: 'En avance',
    },
    {
      title: '4. Procesos guiados',
      detail: 'Admisión, matrícula, académico, docente, prácticas y titulación quedan separados por flujo.',
      state: 'Siguiente',
    },
  ]

  return (
    <section className="content-section content-section--wide">
      <div className="section-heading">
        <span>SisAcademicoV1</span>
        <h1>Clonación funcional</h1>
        <p>
          {displayName} · Mapa de módulos heredados integrado al backend y frontend moderno sin modificar la
          estructura existente de INTECBDD.
        </p>
      </div>

      <div className="panel-card panel-card--wide sisv1-hub-card">
        <div className="panel-card__header">
          <div>
            <span className="eyebrow">Estrategia</span>
            <h2>Unificar sin perder información</h2>
            <p className="muted-text">{data?.strategy || 'Clonación progresiva por módulos.'}</p>
          </div>
          <div className="summary-pills">
            <span>{data?.totals.modules || 0} módulos</span>
            <span>{data?.totals.base || 0} base</span>
            <span>{data?.totals.partial || 0} parcial</span>
            <span>{data?.database || 'INTECBDD'}</span>
          </div>
        </div>

        <div className="sisv1-hub-nav" role="tablist" aria-label="Navegación de clonación SisAcademicoV1">
          <button className={activeTab === 'modulos' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('modulos')}>
            Módulos clonados
          </button>
          <button className={activeTab === 'total' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('total')}>
            Clon total
          </button>
          <button className={activeTab === 'reportes' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('reportes')}>
            Reportes modernizados
          </button>
          <button className={activeTab === 'plan' ? 'is-active' : ''} type="button" onClick={() => setActiveTab('plan')}>
            Plan de cierre
          </button>
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        <div className="sisv1-quick-grid">
          <div className="sisv1-quick-card">
            <span>Módulos V1</span>
            <strong>{data?.totals.modules || 0}</strong>
            <small>{(data?.totals.base || 0) + (data?.totals.partial || 0)} con ruta moderna</small>
          </div>
          <div className="sisv1-quick-card">
            <span>Accesos directos</span>
            <strong>{shortcuts.length}</strong>
            <small>Secciones disponibles en el sistema actual</small>
          </div>
          <div className="sisv1-quick-card">
            <span>Artefactos V1</span>
            <strong>{artifactData?.totals.artifacts || 0}</strong>
            <small>pantallas, code-behind y reportes clasificados</small>
          </div>
          <div className="sisv1-quick-card">
            <span>Reportes modernos</span>
            <strong>{modernReportsData?.totals.total || 0}</strong>
            <small>{modernReportsData?.totals.pendiente || 0} pendientes de reconstruir</small>
          </div>
          <div className="sisv1-quick-card">
            <span>Base conectada</span>
            <strong>{data?.database || 'INTECBDD'}</strong>
            <small>Sin reemplazar tablas existentes</small>
          </div>
        </div>

        {activeTab === 'modulos' && (
          <div className="sisv1-tab-panel">
            <div className="sisv1-shortcuts">
              <div>
                <span className="eyebrow">Navegación rápida</span>
                <h3>Entrar directo a una función clonada</h3>
              </div>
              <div className="sisv1-shortcut-list">
                {shortcuts.map((shortcut) => (
                  <button className="sisv1-shortcut" type="button" key={shortcut.section} onClick={() => onOpenSection(shortcut.section)}>
                    <strong>{sectionLabel(shortcut.section)}</strong>
                    <span>{shortcut.modules.slice(0, 2).join(' · ')}</span>
                  </button>
                ))}
                {!loading && shortcuts.length === 0 && (
                  <span className="muted-text">Todavía no hay accesos directos disponibles.</span>
                )}
              </div>
            </div>

            <div className="toolbar-grid toolbar-grid--compact">
              <label>
                Buscar módulo
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Módulo, tabla, página V1 o ruta moderna"
                />
              </label>
              <label>
                Estado
                <select value={coverage} onChange={(event) => setCoverage(event.target.value)}>
                  <option value="todos">Todos</option>
                  <option value="base">Base migrada</option>
                  <option value="partial">Parcial</option>
                  <option value="pending">Pendiente</option>
                  <option value="excluded">No migrable</option>
                </select>
              </label>
              <button className="btn btn-secondary" type="button" onClick={() => void load()} disabled={loading}>
                {loading ? 'Cargando...' : 'Actualizar'}
              </button>
            </div>

            <div className="sisv1-module-grid">
              {modules.map((module) => (
                <article className="sisv1-module-card" key={module.key}>
                  <div className="sisv1-module-card__head">
                    <div>
                      <span className="eyebrow">{module.key}</span>
                      <h3>{module.title}</h3>
                    </div>
                    <span className={coverageClass(module.coverage)}>{coverageLabel(module.coverage)}</span>
                  </div>
                  <p>{module.description}</p>

                  <div className="sisv1-module-card__meta">
                    <div>
                      <strong>Tablas</strong>
                      <span>{module.tables.join(', ')}</span>
                    </div>
                    <div>
                      <strong>Origen V1</strong>
                      <span>{module.source_paths.join(', ')}</span>
                    </div>
                    <div>
                      <strong>Backend moderno</strong>
                      <span>{module.modern_routes.join(', ')}</span>
                    </div>
                  </div>

                  <div className="sisv1-module-card__actions">
                    {module.available_sections.length > 0 ? (
                      module.available_sections.map((section) => (
                        <button className="btn btn-secondary" type="button" key={section} onClick={() => onOpenSection(section)}>
                          Abrir {sectionLabel(section)}
                        </button>
                      ))
                    ) : (
                      <span className="muted-text">Sin sección administrable todavía</span>
                    )}
                  </div>

                  <p className="sisv1-module-card__note">{module.notes}</p>
                </article>
              ))}
            </div>

            {!loading && modules.length === 0 && (
              <div className="empty-state">No existen módulos con los filtros actuales.</div>
            )}
          </div>
        )}

        {activeTab === 'total' && (
          <div className="sisv1-tab-panel">
            <div className="panel-card__header sisv1-inner-header">
              <div>
                <span className="eyebrow">Clon total</span>
                <h2>Inventario completo de SisAcademicoV1</h2>
                <p className="muted-text">
                  {artifactData?.strategy ||
                    'Cada archivo funcional del proyecto anterior se clasifica contra el modulo moderno correspondiente.'}
                </p>
              </div>
              <div className="summary-pills">
                <span>{artifactData?.totals.artifacts || 0} artefactos</span>
                <span>{artifactData?.totals.by_extension.aspx || 0} pantallas</span>
                <span>{artifactData?.totals.by_extension.vb || 0} code-behind</span>
                <span>{artifactData?.totals.by_extension.rpt || 0} reportes</span>
              </div>
            </div>

            <div className="toolbar-grid toolbar-grid--compact">
              <label>
                Buscar archivo
                <input
                  value={artifactQuery}
                  onChange={(event) => setArtifactQuery(event.target.value)}
                  placeholder="Archivo, carpeta, modulo o estado"
                />
              </label>
              <label>
                Estado
                <select value={artifactCoverage} onChange={(event) => setArtifactCoverage(event.target.value)}>
                  <option value="todos">Todos</option>
                  <option value="base">Base migrada</option>
                  <option value="partial">Parcial</option>
                  <option value="pending">Pendiente</option>
                  <option value="excluded">No migrable</option>
                </select>
              </label>
              <label>
                Tipo
                <select value={artifactExtension} onChange={(event) => setArtifactExtension(event.target.value)}>
                  <option value="todos">Todos</option>
                  {artifactExtensions.map((extension) => (
                    <option value={extension} key={extension}>
                      {extension.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
              <button className="btn btn-secondary" type="button" onClick={() => void load()} disabled={loading}>
                {loading ? 'Cargando...' : 'Actualizar'}
              </button>
            </div>

            <div className="matricula-table-wrap sisv1-artifact-table-wrap">
              <table className="matricula-table sisv1-artifact-table">
                <thead>
                  <tr>
                    <th>Archivo V1</th>
                    <th>Tipo</th>
                    <th>Módulo moderno</th>
                    <th>Estado</th>
                    <th>Tamaño</th>
                  </tr>
                </thead>
                <tbody>
                  {artifacts.map((artifact) => (
                    <tr key={`${artifact.path}-${artifact.extension}`}>
                      <td>
                        <strong>{artifact.file_name}</strong>
                        <small>{artifact.path}</small>
                      </td>
                      <td>{artifact.extension.toUpperCase()}</td>
                      <td>
                        <strong>{artifact.module_title}</strong>
                        <small>{artifact.module_key}</small>
                      </td>
                      <td>
                        <span className={coverageClass(artifact.coverage)}>{coverageLabel(artifact.coverage)}</span>
                      </td>
                      <td>{Math.max(1, Math.round(artifact.size_bytes / 1024))} KB</td>
                    </tr>
                  ))}
                  {!loading && artifacts.length === 0 && (
                    <tr>
                      <td colSpan={5}>No existen archivos con los filtros actuales.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'reportes' && (
          <div className="sisv1-tab-panel">
            <div className="panel-card__header sisv1-inner-header">
              <div>
                <span className="eyebrow">Reporter&iacute;a moderna</span>
                <h2>Reportes heredados reconstruidos</h2>
                <p className="muted-text">
                  {modernReportsData?.strategy ||
                    'Los reportes heredados se reconstruyen con consultas parametrizadas y generación PDF/Excel/HTML desde backend.'}
                </p>
              </div>
              <div className="summary-pills">
                <span>{modernReportsData?.totals.total || 0} reportes</span>
                <span>{modernReportsData?.totals.modernizado || 0} modernizados</span>
                <span>{modernReportsData?.totals.base || 0} base</span>
                <span>{modernReportsData?.totals.pendiente || 0} pendientes</span>
              </div>
            </div>

            <div className="toolbar-grid toolbar-grid--compact">
              <label>
                Buscar reporte
                <input
                  value={reportQuery}
                  onChange={(event) => setReportQuery(event.target.value)}
                  placeholder="Reporte, tabla, pantalla V1 o salida moderna"
                />
              </label>
              <label>
                Estado
                <select value={reportStatus} onChange={(event) => setReportStatus(event.target.value)}>
                  <option value="todos">Todos</option>
                  <option value="modernizado">Modernizado</option>
                  <option value="base">Base</option>
                  <option value="pendiente">Pendiente</option>
                </select>
              </label>
              <button className="btn btn-secondary" type="button" onClick={() => void load()} disabled={loading}>
                {loading ? 'Cargando...' : 'Actualizar'}
              </button>
            </div>

            <div className="matricula-table-wrap sisv1-crystal-table-wrap">
              <table className="matricula-table sisv1-crystal-table">
                <thead>
                  <tr>
                    <th>Reporte</th>
                    <th>Referencia V1</th>
                    <th>Fuentes</th>
                    <th>Filtros</th>
                    <th>Salida moderna</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {modernReports.map((report) => (
                    <tr key={report.key}>
                      <td>
                        <strong>{report.title}</strong>
                        <small>{report.category}</small>
                      </td>
                      <td>
                        <span>{report.legacy_rpt.join(', ')}</span>
                        <small>{report.legacy_pages.join(', ')}</small>
                      </td>
                      <td>{report.source_tables.join(', ')}</td>
                      <td>{report.legacy_filters.join(', ')}</td>
                      <td>
                        <strong>{report.modern_equivalent}</strong>
                        <small>{report.modern_format.join(' / ')}</small>
                      </td>
                      <td>
                        <span className={coverageClass(report.migration_status)}>
                          {coverageLabel(report.migration_status)}
                        </span>
                        <small>{report.notes}</small>
                      </td>
                    </tr>
                  ))}
                  {!loading && modernReports.length === 0 && (
                    <tr>
                      <td colSpan={6}>No existen reportes modernizados con los filtros actuales.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'plan' && (
          <div className="sisv1-tab-panel">
            <div className="sisv1-plan-grid">
              {planSteps.map((step) => (
                <article className="sisv1-plan-card" key={step.title}>
                  <span className="status-pill is-ok">{step.state}</span>
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                </article>
              ))}
            </div>

            <div className="matricula-table-wrap sisv1-crystal-table-wrap">
              <table className="matricula-table">
                <thead>
                  <tr>
                    <th>Frente</th>
                    <th>Qué se mantiene de V1</th>
                    <th>Cómo se navega ahora</th>
                    <th>Resultado esperado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Académico</td>
                    <td>Carreras, mallas, materias, periodos, notas y matrícula.</td>
                    <td>Menús separados por catálogo, matrícula y calificaciones.</td>
                    <td>Menos pantallas mezcladas y consulta directa por estudiante/carrera.</td>
                  </tr>
                  <tr>
                    <td>Docente</td>
                    <td>Docentes, asignaciones, evaluación y autoevaluación.</td>
                    <td>Se conserva como parche sobre la base principal.</td>
                    <td>Sin dañar el flujo docente existente.</td>
                  </tr>
                  <tr>
                    <td>Reportería</td>
                    <td>Reportes heredados con filtros históricos.</td>
                    <td>Catálogo único de reportes y salida PDF/Excel desde backend.</td>
                    <td>Reportes reproducibles sin depender de Crystal Reports.</td>
                  </tr>
                  <tr>
                    <td>Procesos</td>
                    <td>Admisión, matrícula, prácticas, titulación y certificados.</td>
                    <td>Flujos guiados por estado y responsables.</td>
                    <td>Operación más simple y con menos duplicidad.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
