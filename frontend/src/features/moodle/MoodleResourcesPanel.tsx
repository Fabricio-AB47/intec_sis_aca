import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react'

import {
  downloadMoodleCourseResourceFile,
  fetchMoodleCourseResources,
  fetchMoodleCourses,
  moodleCourseResourceFileUrl,
  updateMoodleSectionName,
  updateMoodleSectionVisibility,
} from '../../lib/api'
import type {
  MoodleCourse,
  MoodleCourseContent,
  MoodleCourseLink,
  MoodleCourseModule,
  MoodleCourseResourcesResponse,
  MoodleCourseSection,
  MoodleCoursesResponse,
} from '../../types/app'

type MoodleResourcesPanelProps = {
  initialCourseId?: number
}

type ResourceSelection = {
  section: MoodleCourseSection
  module: MoodleCourseModule
}

type IndexedFile = {
  content: MoodleCourseContent
  fileIndex: number | null
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudieron consultar los recursos del curso.'
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function formatUnixDate(value: number): string {
  if (!value) return 'Sin registro'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value * 1000))
}

function formatIsoDate(value: string): string {
  if (!value) return 'Sin registro'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Sin registro'
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function formatFileSize(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return 'Tamaño no informado'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  const digits = unitIndex === 0 || size >= 100 ? 0 : size >= 10 ? 1 : 2
  return `${new Intl.NumberFormat('es-EC', {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(size)} ${units[unitIndex]}`
}

function normalizedSearch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-EC')
    .trim()
}

const moduleLabels: Record<string, string> = {
  assign: 'Tarea',
  book: 'Libro',
  choice: 'Consulta',
  data: 'Base de datos',
  feedback: 'Encuesta',
  file: 'Archivo',
  folder: 'Carpeta',
  forum: 'Foro',
  glossary: 'Glosario',
  h5pactivity: 'Contenido interactivo',
  imscp: 'Paquete de contenido',
  label: 'Etiqueta',
  lesson: 'Lección',
  lti: 'Herramienta externa',
  page: 'Página',
  quiz: 'Cuestionario',
  resource: 'Recurso',
  scorm: 'Paquete SCORM',
  survey: 'Encuesta',
  url: 'Enlace',
  wiki: 'Wiki',
  workshop: 'Taller',
}

function moduleLabel(module: MoodleCourseModule): string {
  const code = module.modname.trim().toLowerCase()
  return moduleLabels[code] || module.modplural || module.modname || 'Recurso'
}

function courseLabel(course: MoodleCourse): string {
  const name = course.displayname || course.fullname || course.shortname || `Curso ${course.id}`
  return `${name} · ${course.shortname || `ID ${course.id}`}`
}

function indexedFiles(module: MoodleCourseModule): IndexedFile[] {
  let fileIndex = 0
  return module.contents
    .filter((content) => Boolean(content.filename))
    .map((content) => {
      if (!content.fileurl) return { content, fileIndex: null }
      const indexed = { content, fileIndex }
      fileIndex += 1
      return indexed
    })
}

function moduleLinks(module: MoodleCourseModule): MoodleCourseLink[] {
  return Array.isArray(module.links) ? module.links : []
}

function moduleMatches(module: MoodleCourseModule, query: string): boolean {
  const searchable = [
    module.name,
    module.modname,
    module.modplural,
    module.description,
    module.availabilityinfo,
    ...module.dates.flatMap((date) => [date.label, date.dataid]),
    ...module.contents.flatMap((content) => [
      content.filename,
      content.filepath,
      content.mimetype,
      content.author,
      content.repositorytype,
    ]),
    ...moduleLinks(module).flatMap((link) => [
      link.name,
      link.provider,
      link.domain,
      link.url,
    ]),
  ]
  return normalizedSearch(searchable.join(' ')).includes(query)
}

function previewKind(content: MoodleCourseContent): 'pdf' | 'image' | 'video' | 'audio' | 'none' {
  const mime = content.mimetype.toLowerCase()
  const name = content.filename.toLowerCase()
  if (mime === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  return 'none'
}

export function MoodleResourcesPanel({ initialCourseId = 0 }: MoodleResourcesPanelProps) {
  const [coursesData, setCoursesData] = useState<MoodleCoursesResponse | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [courseSearch, setCourseSearch] = useState('')
  const [selectedCourseId, setSelectedCourseId] = useState(initialCourseId)
  const catalogRequest = useRef(0)

  const [resourcesData, setResourcesData] = useState<MoodleCourseResourcesResponse | null>(null)
  const [resourcesLoading, setResourcesLoading] = useState(false)
  const [resourcesError, setResourcesError] = useState('')
  const [contentSearch, setContentSearch] = useState('')
  const [selectedResource, setSelectedResource] = useState<ResourceSelection | null>(null)
  const [previewFile, setPreviewFile] = useState<IndexedFile | null>(null)
  const [downloadingFileKey, setDownloadingFileKey] = useState('')
  const [downloadNoticeVisible, setDownloadNoticeVisible] = useState(false)
  const downloadNoticeTimer = useRef<number | null>(null)
  const [managedSection, setManagedSection] = useState<MoodleCourseSection | null>(null)
  const [sectionName, setSectionName] = useState('')
  const [sectionSaving, setSectionSaving] = useState(false)
  const [sectionActionMessage, setSectionActionMessage] = useState('')
  const [sectionActionError, setSectionActionError] = useState('')

  const loadCatalog = useCallback(async (search: string, refresh = false) => {
    const requestId = catalogRequest.current + 1
    catalogRequest.current = requestId
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const response = await fetchMoodleCourses({
        page: 1,
        pageSize: 200,
        search,
        visibility: 'all',
        refresh,
      })
      if (requestId !== catalogRequest.current) return
      setCoursesData(response)
      setSelectedCourseId((current) => current || response.items[0]?.id || 0)
    } catch (error) {
      if (requestId === catalogRequest.current) setCatalogError(errorMessage(error))
    } finally {
      if (requestId === catalogRequest.current) setCatalogLoading(false)
    }
  }, [])

  const loadResources = useCallback(async (courseId: number, refresh = false) => {
    if (!courseId) return
    setResourcesLoading(true)
    setResourcesError('')
    try {
      setResourcesData(await fetchMoodleCourseResources(courseId, refresh))
      setContentSearch('')
    } catch (error) {
      setResourcesData(null)
      setResourcesError(errorMessage(error))
    } finally {
      setResourcesLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(
      () => void loadCatalog(courseSearch.trim()),
      courseSearch.trim() ? 300 : 0,
    )
    return () => window.clearTimeout(timeoutId)
  }, [courseSearch, loadCatalog])

  useEffect(() => {
    if (initialCourseId > 0) setSelectedCourseId(initialCourseId)
  }, [initialCourseId])

  useEffect(() => {
    if (selectedCourseId > 0) void loadResources(selectedCourseId)
  }, [loadResources, selectedCourseId])

  useEffect(() => () => {
    if (downloadNoticeTimer.current !== null) {
      window.clearTimeout(downloadNoticeTimer.current)
    }
  }, [])

  useEffect(() => {
    if (!selectedResource && !managedSection) return undefined
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (previewFile) setPreviewFile(null)
      else if (selectedResource) setSelectedResource(null)
      else {
        setManagedSection(null)
        setSectionName('')
        setSectionActionMessage('')
        setSectionActionError('')
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [managedSection, previewFile, selectedResource])

  const courseOptions = useMemo(() => {
    const items = [...(coursesData?.items || [])]
    if (resourcesData?.course && !items.some((course) => course.id === resourcesData.course.id)) {
      items.unshift(resourcesData.course)
    }
    return items
  }, [coursesData, resourcesData])

  const filteredSections = useMemo(() => {
    if (!resourcesData) return []
    const query = normalizedSearch(contentSearch)
    if (!query) return resourcesData.sections
    return resourcesData.sections.flatMap((section) => {
      const sectionMatch = normalizedSearch(
        `${section.section} ${section.name} ${section.summary}`,
      ).includes(query)
      const modules = sectionMatch
        ? section.modules
        : section.modules.filter((module) => moduleMatches(module, query))
      if (!sectionMatch && modules.length === 0) return []
      return [{ ...section, modules }]
    })
  }, [contentSearch, resourcesData])

  const filteredModules = useMemo(
    () => filteredSections.reduce((total, section) => total + section.modules.length, 0),
    [filteredSections],
  )

  const selectedFiles = useMemo(
    () => (selectedResource ? indexedFiles(selectedResource.module) : []),
    [selectedResource],
  )

  const selectedLinks = useMemo(
    () => (selectedResource ? moduleLinks(selectedResource.module) : []),
    [selectedResource],
  )

  const previewUrl = useMemo(() => {
    if (!selectedResource || previewFile?.fileIndex === null || previewFile?.fileIndex === undefined) {
      return ''
    }
    return moodleCourseResourceFileUrl(
      selectedCourseId,
      selectedResource.module.id,
      previewFile.fileIndex,
      'inline',
    )
  }, [previewFile, selectedCourseId, selectedResource])

  const showDownloadFailure = useCallback(() => {
    if (downloadNoticeTimer.current !== null) {
      window.clearTimeout(downloadNoticeTimer.current)
    }
    setDownloadNoticeVisible(true)
    downloadNoticeTimer.current = window.setTimeout(() => {
      setDownloadNoticeVisible(false)
      downloadNoticeTimer.current = null
    }, 3000)
  }, [])

  const downloadResourceFile = async (moduleId: number, file: IndexedFile) => {
    if (file.fileIndex === null || downloadingFileKey) {
      showDownloadFailure()
      return
    }

    const fileKey = `${moduleId}-${file.fileIndex}`
    setDownloadingFileKey(fileKey)
    try {
      const blob = await downloadMoodleCourseResourceFile(
        selectedCourseId,
        moduleId,
        file.fileIndex,
      )
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = file.content.filename || 'recurso-moodle'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    } catch {
      showDownloadFailure()
    } finally {
      setDownloadingFileKey('')
    }
  }

  const submitCatalog = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void loadCatalog(courseSearch.trim())
  }

  const openResource = (section: MoodleCourseSection, module: MoodleCourseModule) => {
    setPreviewFile(null)
    setSelectedResource({ section, module })
  }

  const openSectionManager = (section: MoodleCourseSection) => {
    setSectionName(section.name)
    setSectionActionMessage('')
    setSectionActionError('')
    setManagedSection(section)
  }

  const closeSectionManager = () => {
    if (sectionSaving) return
    setManagedSection(null)
    setSectionName('')
    setSectionActionMessage('')
    setSectionActionError('')
  }

  const updateSection = async (section: MoodleCourseSection, visible: boolean) => {
    if (!selectedCourseId || sectionSaving) return
    setSectionSaving(true)
    setSectionActionError('')
    setSectionActionMessage('')
    try {
      const response = await updateMoodleSectionVisibility(
        selectedCourseId,
        section.id,
        visible,
      )
      setManagedSection(response.section)
      setSectionName(response.section.name)
      setSectionActionMessage(response.message)
      await loadResources(selectedCourseId, true)
    } catch (error) {
      setSectionActionError(errorMessage(error))
    } finally {
      setSectionSaving(false)
    }
  }

  const saveSectionName = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!selectedCourseId || !managedSection || sectionSaving) return
    const cleanName = sectionName.trim()
    if (!cleanName) {
      setSectionActionError('Ingrese el nombre de la sección.')
      return
    }

    setSectionSaving(true)
    setSectionActionError('')
    setSectionActionMessage('')
    try {
      const response = await updateMoodleSectionName(
        selectedCourseId,
        managedSection.id,
        cleanName,
      )
      setManagedSection(response.section)
      setSectionName(response.section.name)
      setSectionActionMessage(response.message)
      await loadResources(selectedCourseId, true)
    } catch (error) {
      setSectionActionError(errorMessage(error))
    } finally {
      setSectionSaving(false)
    }
  }

  return (
    <div className="moodle-section">
      <div className="moodle-section__heading">
        <div>
          <span>Contenido académico</span>
          <h2>Recursos por curso</h2>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={!selectedCourseId || resourcesLoading}
          onClick={() => void loadResources(selectedCourseId, true)}
        >
          {resourcesLoading ? 'Actualizando...' : 'Actualizar contenido'}
        </button>
      </div>

      <form className="moodle-resource-picker" onSubmit={submitCatalog}>
        <label>
          <span>Buscar curso</span>
          <input
            type="search"
            value={courseSearch}
            onChange={(event) => setCourseSearch(event.target.value)}
            placeholder="Escriba parte del nombre, código o categoría"
          />
        </label>
        <button type="submit" className="moodle-button moodle-button--primary" disabled={catalogLoading}>
          {catalogLoading ? 'Buscando...' : 'Buscar cursos'}
        </button>
        <label className="moodle-resource-picker__course">
          <span>Curso seleccionado</span>
          <select
            value={selectedCourseId || ''}
            disabled={catalogLoading || courseOptions.length === 0}
            onChange={(event) => setSelectedCourseId(Number(event.target.value))}
          >
            {courseOptions.length === 0 && <option value="">No existen cursos para seleccionar</option>}
            {courseOptions.map((course) => (
              <option key={course.id} value={course.id}>{courseLabel(course)}</option>
            ))}
          </select>
        </label>
      </form>

      {catalogError && <div className="moodle-alert moodle-alert--error">{catalogError}</div>}
      {resourcesError && <div className="moodle-alert moodle-alert--error">{resourcesError}</div>}
      {!resourcesData && resourcesLoading && !resourcesError && (
        <div className="moodle-empty">Consultando secciones, actividades y archivos del curso...</div>
      )}
      {!resourcesData && !resourcesLoading && !resourcesError && coursesData?.items.length === 0 && (
        <div className="moodle-empty">No existen cursos con el criterio indicado.</div>
      )}

      {resourcesData && (
        <div className="moodle-resource-content">
          <div className="moodle-resource-course">
            <div>
              <span>Curso</span>
              <h3>{resourcesData.course.displayname || resourcesData.course.fullname}</h3>
              <p>
                {resourcesData.course.shortname || `ID ${resourcesData.course.id}`}
                {' · '}
                {resourcesData.course.categoryname || 'Sin categoría'}
              </p>
            </div>
            <div>
              <span>Última consulta</span>
              <strong>{formatIsoDate(resourcesData.source.fetched_at)}</strong>
              <small>{resourcesData.source.cached ? 'Caché vigente' : 'Información actualizada'}</small>
            </div>
          </div>

          <div className="moodle-resource-summary" aria-label="Resumen de recursos del curso">
            <div><span>Secciones</span><strong>{formatNumber(resourcesData.totals.sections)}</strong></div>
            <div><span>Actividades y recursos</span><strong>{formatNumber(resourcesData.totals.modules)}</strong></div>
            <div><span>Archivos</span><strong>{formatNumber(resourcesData.totals.files)}</strong></div>
            <div><span>Enlaces externos</span><strong>{formatNumber(resourcesData.totals.links || 0)}</strong></div>
            <div><span>Elementos visibles</span><strong>{formatNumber(resourcesData.totals.visible_modules)}</strong></div>
          </div>

          <div className="moodle-resource-search">
            <label>
              <span>Buscar dentro del curso</span>
              <input
                type="search"
                value={contentSearch}
                onChange={(event) => setContentSearch(event.target.value)}
                placeholder="Nombre de sección, actividad, documento, proveedor o enlace"
              />
            </label>
            <div>
              <strong>{formatNumber(filteredModules)}</strong>
              <span>elemento(s) encontrado(s)</span>
            </div>
            {contentSearch && (
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                onClick={() => setContentSearch('')}
              >
                Limpiar búsqueda
              </button>
            )}
          </div>

          <div className="moodle-course-sections">
            {filteredSections.map((section) => (
              <section className="moodle-course-section" key={`${section.id}-${section.section}`}>
                <header>
                  <div>
                    <span>Sección {section.section}</span>
                    <h3>{section.name}</h3>
                    {section.summary && <p>{section.summary}</p>}
                  </div>
                  <div className="moodle-course-section__actions">
                    <div className="moodle-course-section__meta">
                      <strong>{formatNumber(section.modules.length)} elemento(s)</strong>
                      <span className={`moodle-badge ${section.visible && section.uservisible ? 'moodle-badge--success' : 'moodle-badge--warning'}`}>
                        {section.visible && section.uservisible ? 'Visible' : 'Oculta'}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="moodle-button moodle-button--secondary"
                      onClick={() => openSectionManager(section)}
                    >
                      Administrar sección
                    </button>
                  </div>
                </header>

                {section.modules.length === 0 ? (
                  <div className="moodle-course-section__empty">Esta sección no contiene actividades ni recursos.</div>
                ) : (
                  <div className="moodle-resource-modules">
                    {section.modules.map((module) => {
                      const files = indexedFiles(module)
                      const links = moduleLinks(module)
                      return (
                        <article className="moodle-resource-module" key={module.id}>
                          <div className="moodle-resource-module__header">
                            <div>
                              <span>{moduleLabel(module)}</span>
                              <h4>{module.name}</h4>
                            </div>
                            <span className={`moodle-badge ${module.visible && module.uservisible ? 'moodle-badge--success' : 'moodle-badge--warning'}`}>
                              {module.visible && module.uservisible ? 'Disponible' : 'Restringido'}
                            </span>
                          </div>

                          {module.description && <p className="moodle-resource-module__description">{module.description}</p>}
                          {module.availabilityinfo && (
                            <p className="moodle-resource-module__availability">
                              <strong>Disponibilidad:</strong> {module.availabilityinfo}
                            </p>
                          )}

                          {files.length > 0 && (
                            <div className="moodle-resource-file-summary">
                              <strong>{formatNumber(files.length)} archivo(s)</strong>
                              <span>{files.slice(0, 3).map(({ content }) => content.filename).join(' · ')}</span>
                            </div>
                          )}

                          {links.length > 0 && (
                            <div className="moodle-resource-link-summary">
                              <strong>{formatNumber(links.length)} enlace(s) externo(s)</strong>
                              <span>
                                {[...new Set(links.map((link) => link.provider))].slice(0, 3).join(' · ')}
                              </span>
                            </div>
                          )}

                          <div className="moodle-resource-module__actions">
                            <button
                              type="button"
                              className="moodle-button moodle-button--secondary"
                              onClick={() => openResource(section, module)}
                            >
                              Ver información
                            </button>
                            {module.url && !module.noviewlink && (
                              <a href={module.url} target="_blank" rel="noreferrer">Abrir en Moodle</a>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </section>
            ))}
            {filteredSections.length === 0 && (
              <div className="moodle-empty">
                No se encontraron secciones, actividades, documentos ni enlaces con el texto indicado.
              </div>
            )}
          </div>
        </div>
      )}

      {managedSection && (
        <div className="moodle-confirm-overlay" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) closeSectionManager()
        }}>
          <section className="moodle-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="moodle-section-dialog-title">
            <header className="moodle-confirm-dialog__header">
              <div>
                <span>Edición desde Recursos · Sección {managedSection.section}</span>
                <h2 id="moodle-section-dialog-title">Editar sección</h2>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={sectionSaving}
                onClick={closeSectionManager}
              >
                Cerrar
              </button>
            </header>
            <div className="moodle-confirm-dialog__body">
              <p>
                Actualice el nombre y controle la visibilidad de esta sección sin salir del apartado de Recursos.
              </p>
              <form className="moodle-section-editor" onSubmit={saveSectionName}>
                <label htmlFor="moodle-section-name">Nombre de la sección</label>
                <div className="moodle-section-editor__row">
                  <input
                    id="moodle-section-name"
                    type="text"
                    value={sectionName}
                    maxLength={1333}
                    disabled={!managedSection.can_update_name || sectionSaving}
                    onChange={(event) => setSectionName(event.target.value)}
                  />
                  <button
                    type="submit"
                    className="moodle-button moodle-button--primary"
                    disabled={
                      !managedSection.can_update_name
                      || sectionSaving
                      || !sectionName.trim()
                      || sectionName.trim() === managedSection.name
                    }
                  >
                    {sectionSaving ? 'Guardando...' : 'Guardar nombre'}
                  </button>
                </div>
                {managedSection.summary && (
                  <div className="moodle-section-editor__summary">
                    <strong>Resumen sincronizado desde Moodle</strong>
                    <p>{managedSection.summary}</p>
                  </div>
                )}
              </form>
              {sectionActionError && <div className="moodle-alert moodle-alert--error">{sectionActionError}</div>}
              {sectionActionMessage && <div className="moodle-alert moodle-alert--success">{sectionActionMessage}</div>}
              <dl className="moodle-confirm-dialog__details">
                <div><dt>Número</dt><dd>{managedSection.section}</dd></div>
                <div><dt>Estado</dt><dd>{managedSection.visible ? 'Visible' : 'Oculta'}</dd></div>
                <div><dt>Actividades</dt><dd>{formatNumber(managedSection.modules.length)}</dd></div>
                <div>
                  <dt>Controles</dt>
                  <dd>
                    Nombre: {managedSection.can_update_name ? 'editable' : 'bloqueado'} · Visibilidad:{' '}
                    {managedSection.can_update_visibility ? 'editable' : 'protegida'}
                  </dd>
                </div>
              </dl>
            </div>
            <footer className="moodle-confirm-dialog__actions">
              <button
                type="button"
                className={`moodle-button ${managedSection.visible ? 'moodle-button--danger' : 'moodle-button--success'}`}
                disabled={!managedSection.can_update_visibility || sectionSaving}
                onClick={() => void updateSection(managedSection, !managedSection.visible)}
              >
                {sectionSaving
                  ? 'Guardando...'
                  : managedSection.visible
                    ? 'Ocultar sección'
                    : 'Mostrar sección'}
              </button>
            </footer>
          </section>
        </div>
      )}

      {selectedResource && (
        <div className="moodle-confirm-overlay" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target && !previewFile) setSelectedResource(null)
        }}>
          <section className="moodle-resource-dialog" role="dialog" aria-modal="true" aria-labelledby="moodle-resource-dialog-title">
            <header className="moodle-resource-dialog__header">
              <div>
                <span>{moduleLabel(selectedResource.module)} · {selectedResource.section.name}</span>
                <h2 id="moodle-resource-dialog-title">{selectedResource.module.name}</h2>
              </div>
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                onClick={() => {
                  setPreviewFile(null)
                  setSelectedResource(null)
                }}
              >
                Cerrar
              </button>
            </header>

            <div className="moodle-resource-dialog__body">
              <dl className="moodle-resource-detail-grid">
                <div><dt>Tipo</dt><dd>{moduleLabel(selectedResource.module)}</dd></div>
                <div><dt>Estado</dt><dd>{selectedResource.module.visible && selectedResource.module.uservisible ? 'Disponible' : 'Restringido'}</dd></div>
                <div><dt>Archivos</dt><dd>{formatNumber(selectedFiles.length)}</dd></div>
                <div><dt>Enlaces</dt><dd>{formatNumber(selectedLinks.length)}</dd></div>
                <div><dt>Sección</dt><dd>{selectedResource.section.name}</dd></div>
              </dl>

              {selectedResource.module.description && (
                <div className="moodle-resource-information">
                  <h3>Información</h3>
                  <p>{selectedResource.module.description}</p>
                </div>
              )}

              {selectedResource.module.dates.length > 0 && (
                <dl className="moodle-resource-dates moodle-resource-dates--dialog">
                  {selectedResource.module.dates.map((date, index) => (
                    <div key={`${selectedResource.module.id}-${date.dataid || date.label}-${index}`}>
                      <dt>{date.label || 'Fecha'}</dt>
                      <dd>{formatUnixDate(date.timestamp)}</dd>
                    </div>
                  ))}
                </dl>
              )}

              <div className="moodle-resource-dialog__files">
                <h3>Documentos y archivos</h3>
                {selectedFiles.length === 0 ? (
                  <p>Esta actividad no contiene archivos descargables.</p>
                ) : (
                  selectedFiles.map(({ content, fileIndex }) => (
                    <div key={`${content.filename}-${content.filepath}-${content.sortorder}`}>
                      <div>
                        <strong>{content.filename}</strong>
                        <span>
                          {formatFileSize(content.filesize)}
                          {content.mimetype ? ` · ${content.mimetype}` : ''}
                          {content.author ? ` · ${content.author}` : ''}
                        </span>
                      </div>
                      <div className="moodle-resource-dialog__file-actions">
                        <button
                          type="button"
                          className="moodle-button moodle-button--secondary"
                          disabled={fileIndex === null || previewKind(content) === 'none'}
                          onClick={() => setPreviewFile({ content, fileIndex })}
                        >
                          Vista previa
                        </button>
                        {fileIndex === null ? (
                          <span className="moodle-resource-link--disabled">No disponible</span>
                        ) : (
                          <button
                            type="button"
                            className="moodle-button moodle-button--primary moodle-button-link"
                            disabled={downloadingFileKey === `${selectedResource.module.id}-${fileIndex}`}
                            onClick={() => void downloadResourceFile(
                              selectedResource.module.id,
                              { content, fileIndex },
                            )}
                          >
                            {downloadingFileKey === `${selectedResource.module.id}-${fileIndex}`
                              ? 'Descargando...'
                              : 'Descargar'}
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {selectedLinks.length > 0 && (
                <div className="moodle-resource-dialog__links">
                  <h3>Enlaces externos</h3>
                  {selectedLinks.map((link) => (
                    <div key={link.url}>
                      <div>
                        <strong>{link.name}</strong>
                        <span>
                          {link.provider}
                          {link.domain ? ` · ${link.domain}` : ''}
                        </span>
                      </div>
                      <a
                        className="moodle-button moodle-button--secondary moodle-button-link"
                        href={link.url}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        Abrir enlace
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <footer className="moodle-resource-dialog__footer">
              {selectedResource.module.url && !selectedResource.module.noviewlink && (
                <a
                  className="moodle-button moodle-button--secondary moodle-button-link"
                  href={selectedResource.module.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Abrir actividad en Moodle
                </a>
              )}
            </footer>
          </section>
        </div>
      )}

      {selectedResource && previewFile && previewUrl && (
        <div className="moodle-confirm-overlay moodle-preview-overlay" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setPreviewFile(null)
        }}>
          <section className="moodle-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="moodle-preview-title">
            <header className="moodle-resource-dialog__header">
              <div>
                <span>Vista previa del documento</span>
                <h2 id="moodle-preview-title">{previewFile.content.filename}</h2>
              </div>
              <button type="button" className="moodle-button moodle-button--secondary" onClick={() => setPreviewFile(null)}>
                Cerrar
              </button>
            </header>
            <div className="moodle-preview-dialog__content">
              {previewKind(previewFile.content) === 'pdf' && (
                <iframe src={previewUrl} title={`Vista previa de ${previewFile.content.filename}`} />
              )}
              {previewKind(previewFile.content) === 'image' && (
                <img src={previewUrl} alt={`Vista previa de ${previewFile.content.filename}`} />
              )}
              {previewKind(previewFile.content) === 'video' && (
                <video src={previewUrl} controls preload="metadata">
                  Su navegador no permite reproducir este video.
                </video>
              )}
              {previewKind(previewFile.content) === 'audio' && (
                <audio src={previewUrl} controls preload="metadata">
                  Su navegador no permite reproducir este audio.
                </audio>
              )}
            </div>
            <footer className="moodle-resource-dialog__footer">
              <button
                type="button"
                className="moodle-button moodle-button--primary moodle-button-link"
                disabled={downloadingFileKey === `${selectedResource.module.id}-${previewFile.fileIndex}`}
                onClick={() => void downloadResourceFile(
                  selectedResource.module.id,
                  previewFile,
                )}
              >
                {downloadingFileKey === `${selectedResource.module.id}-${previewFile.fileIndex}`
                  ? 'Descargando...'
                  : 'Descargar archivo'}
              </button>
            </footer>
          </section>
        </div>
      )}

      {downloadNoticeVisible && (
        <div className="moodle-download-notice-overlay" role="presentation">
          <section
            className="moodle-download-notice"
            role="alertdialog"
            aria-modal="true"
            aria-live="assertive"
            aria-label="Descarga no disponible"
          >
            <span>Descarga de recurso</span>
            <h2>No es posible la descarga</h2>
            <div className="moodle-download-notice__timer" aria-hidden="true" />
          </section>
        </div>
      )}
    </div>
  )
}
