import { useEffect, useMemo, useState } from 'react'

import {
  applyMoodleCourseCloning,
  fetchMoodleCourseCloningCatalog,
  previewMoodleCourseCloning,
} from '../../lib/api'
import type {
  MoodleCourseCloningApplyResponse,
  MoodleCourseCloningCatalogResponse,
  MoodleCourseCloningPayload,
  MoodleCourseCloningPreviewResponse,
  MoodleCourseOfferType,
} from '../../types/app'

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudo completar el proceso de clonación en Moodle.'
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((left, right) => (
    left.localeCompare(right, 'es', { sensitivity: 'base' })
  ))
}

function statusLabel(status: string): string {
  return {
    POR_CREAR: 'Por crear',
    POR_CLONAR: 'Por clonar',
    EXISTENTE: 'Existente',
    CONFLICTO: 'Conflicto',
    CREADO: 'Creado',
    CREADO_CON_ADVERTENCIA: 'Creado con advertencia',
    OMITIDO: 'Omitido',
    ERROR: 'Error',
  }[status] ?? status
}

function statusClass(status: string): string {
  if (status === 'CREADO' || status === 'EXISTENTE') return 'is-success'
  if (status === 'CONFLICTO' || status === 'ERROR') return 'is-error'
  if (status === 'CREADO_CON_ADVERTENCIA') return 'is-warning'
  return 'is-pending'
}

export function MoodleCourseCloningPanel() {
  const [catalog, setCatalog] = useState<MoodleCourseCloningCatalogResponse | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [offerType, setOfferType] = useState<MoodleCourseOfferType>('REGULAR')
  const [area, setArea] = useState('')
  const [career, setCareer] = useState('')
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [periodName, setPeriodName] = useState('R30')
  const [openingAt, setOpeningAt] = useState('')
  const [closingAt, setClosingAt] = useState('')
  const [parallel, setParallel] = useState('')
  const [preview, setPreview] = useState<MoodleCourseCloningPreviewResponse | null>(null)
  const [previewPayload, setPreviewPayload] = useState<MoodleCourseCloningPayload | null>(null)
  const [result, setResult] = useState<MoodleCourseCloningApplyResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [error, setError] = useState('')

  const loadCatalog = async () => {
    setCatalogLoading(true)
    setError('')
    try {
      const response = await fetchMoodleCourseCloningCatalog()
      const availableIds = new Set(response.templates.map((item) => item.course_id))
      setCatalog(response)
      setSelectedIds((current) => current.filter((courseId) => availableIds.has(courseId)))
      setPreview(null)
      setPreviewPayload(null)
      setConfirmOpen(false)
    } catch (requestError) {
      setCatalog(null)
      setError(errorMessage(requestError))
    } finally {
      setCatalogLoading(false)
    }
  }

  useEffect(() => {
    void loadCatalog()
  }, [])

  const resetReview = () => {
    setPreview(null)
    setPreviewPayload(null)
    setResult(null)
    setConfirmOpen(false)
    setError('')
  }

  const templatesByType = useMemo(
    () => (catalog?.templates ?? []).filter((item) => item.offer_type === offerType),
    [catalog, offerType],
  )
  const areas = useMemo(
    () => uniqueSorted(templatesByType.map((item) => item.area)),
    [templatesByType],
  )
  const careers = useMemo(
    () => uniqueSorted(
      templatesByType
        .filter((item) => !area || item.area === area)
        .map((item) => item.career),
    ),
    [area, templatesByType],
  )
  const filteredTemplates = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('es')
    return templatesByType.filter((item) => {
      if (area && item.area !== area) return false
      if (career && item.career !== career) return false
      if (!query) return true
      return [item.subject_name, item.shortname, item.idnumber, item.source_path]
        .join(' ')
        .toLocaleLowerCase('es')
        .includes(query)
    })
  }, [area, career, search, templatesByType])
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const selectedRoutes = useMemo(() => uniqueSorted(
    templatesByType
      .filter((item) => selectedSet.has(item.course_id))
      .map((item) => item.category_route.join(' / ')),
  ), [selectedSet, templatesByType])
  const destinationBranch = selectedRoutes.length === 1
    ? selectedRoutes[0]
    : selectedRoutes.length > 1
      ? `${selectedRoutes.length} ramas seleccionadas`
      : 'Área / Carrera'
  const derivedYear = openingAt ? new Date(`${openingAt}:00`).getFullYear() : 0

  const changeOfferType = (nextType: MoodleCourseOfferType) => {
    setOfferType(nextType)
    setArea('')
    setCareer('')
    setSelectedIds([])
    setPeriodName(nextType === 'REGULAR' ? 'R30' : 'H1')
    resetReview()
  }

  const toggleTemplate = (courseId: number) => {
    setSelectedIds((current) => current.includes(courseId)
      ? current.filter((id) => id !== courseId)
      : current.length < 50 ? [...current, courseId] : current)
    resetReview()
  }

  const selectVisible = () => {
    setSelectedIds((current) => [
      ...new Set([...current, ...filteredTemplates.map((item) => item.course_id)]),
    ].slice(0, 50))
    resetReview()
  }

  const buildPayload = (): MoodleCourseCloningPayload | null => {
    if (selectedIds.length === 0) {
      setError('Seleccione al menos una materia de las plantillas base.')
      return null
    }
    if (!periodName.trim()) {
      setError('Ingrese el período o subcategoría, por ejemplo R30 o H1.')
      return null
    }
    if (!openingAt) {
      setError('Ingrese la fecha de inicio; de ella se obtiene el año de la oferta.')
      return null
    }
    if (closingAt && new Date(closingAt).getTime() <= new Date(openingAt).getTime()) {
      setError('La fecha final debe ser posterior a la fecha inicial.')
      return null
    }
    return {
      template_course_ids: selectedIds,
      offer_type: offerType,
      period_name: periodName.trim(),
      opening_at: openingAt,
      closing_at: closingAt || null,
      parallel: parallel.trim(),
    }
  }

  const reviewPlan = async () => {
    const payload = buildPayload()
    if (!payload) return
    setPreviewLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await previewMoodleCourseCloning(payload)
      setPreview(response)
      setPreviewPayload(payload)
    } catch (requestError) {
      setPreview(null)
      setPreviewPayload(null)
      setError(errorMessage(requestError))
    } finally {
      setPreviewLoading(false)
    }
  }

  const applyPlan = async () => {
    if (!previewPayload || !preview?.ready) return
    setApplying(true)
    setError('')
    try {
      const response = await applyMoodleCourseCloning(previewPayload)
      setResult(response)
      setPreview(null)
      setPreviewPayload(null)
      setConfirmOpen(false)
      await loadCatalog()
    } catch (requestError) {
      setError(errorMessage(requestError))
      setConfirmOpen(false)
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="moodle-section moodle-course-cloning">
      <div className="moodle-section__heading">
        <div>
          <span>Oferta académica</span>
          <h2>Copiar cursos desde plantillas base</h2>
          <p>Cree el año, las ramas Regular y Homologación, el período y sus materias en una sola operación.</p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={catalogLoading || previewLoading || applying}
          onClick={() => void loadCatalog()}
        >
          {catalogLoading ? 'Actualizando...' : 'Actualizar plantillas'}
        </button>
      </div>

      {error && <div className="moodle-alert moodle-alert--error" role="alert">{error}</div>}

      {catalog && !catalog.capability.enabled && (
        <div className="moodle-alert moodle-alert--warning" role="status">
          <strong>Clonación en modo de consulta.</strong> {catalog.capability.reason}
        </div>
      )}
      {catalog && !catalog.catalog_ready && (
        <div className="moodle-alert moodle-alert--warning" role="status">
          {catalog.catalog_reason}
        </div>
      )}

      <section className="moodle-cloning-step" aria-labelledby="cloning-source-title">
        <div className="moodle-cloning-step__heading">
          <div>
            <span>Paso 1</span>
            <h3 id="cloning-source-title">Seleccionar plantillas</h3>
          </div>
          <strong>{selectedIds.length} seleccionada(s)</strong>
        </div>

        <div className="moodle-cloning-type" aria-label="Tipo de oferta">
          <button
            type="button"
            className={offerType === 'REGULAR' ? 'is-active' : ''}
            onClick={() => changeOfferType('REGULAR')}
          >
            Regular
            <small>{catalog?.summary.regular ?? 0} plantilla(s)</small>
          </button>
          <button
            type="button"
            className={offerType === 'HOMOLOGACION' ? 'is-active' : ''}
            onClick={() => changeOfferType('HOMOLOGACION')}
          >
            Homologación
            <small>{catalog?.summary.homologation ?? 0} plantilla(s)</small>
          </button>
        </div>

        <div className="moodle-cloning-filters">
          <label>
            <span>Área</span>
            <select
              value={area}
              onChange={(event) => {
                setArea(event.target.value)
                setCareer('')
                resetReview()
              }}
            >
              <option value="">Todas</option>
              {areas.map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
          </label>
          <label>
            <span>Carrera</span>
            <select
              value={career}
              disabled={careers.length === 0}
              onChange={(event) => {
                setCareer(event.target.value)
                resetReview()
              }}
            >
              <option value="">Todas</option>
              {careers.map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
          </label>
          <label>
            <span>Buscar materia</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Nombre, código o ruta"
            />
          </label>
          <div className="moodle-cloning-filter-actions">
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={filteredTemplates.length === 0 || applying}
              onClick={selectVisible}
            >
              Seleccionar visibles
            </button>
            <button
              type="button"
              className="moodle-button moodle-button--secondary"
              disabled={selectedIds.length === 0 || applying}
              onClick={() => {
                setSelectedIds([])
                resetReview()
              }}
            >
              Limpiar
            </button>
          </div>
        </div>

        <div className="moodle-cloning-template-list" aria-live="polite">
          {filteredTemplates.map((template) => (
            <label
              className={selectedSet.has(template.course_id) ? 'is-selected' : ''}
              key={template.course_id}
            >
              <input
                type="checkbox"
                checked={selectedSet.has(template.course_id)}
                disabled={applying}
                onChange={() => toggleTemplate(template.course_id)}
              />
              <span>
                <strong>{template.subject_name}</strong>
                <small>Nombre corto: {template.shortname || 'Sin configurar'}</small>
                <small>Número ID: {template.idnumber || 'Sin configurar'}</small>
              </span>
              <span>
                <b>{template.career || template.area}</b>
                <small>{template.source_path}</small>
              </span>
            </label>
          ))}
          {!catalogLoading && filteredTemplates.length === 0 && (
            <div className="moodle-empty">No hay plantillas que coincidan con los filtros.</div>
          )}
          {catalogLoading && (
            <div className="moodle-empty">Consultando categorías y plantillas de Moodle...</div>
          )}
        </div>
      </section>

      <section className="moodle-cloning-step" aria-labelledby="cloning-destination-title">
        <div className="moodle-cloning-step__heading">
          <div>
            <span>Paso 2</span>
            <h3 id="cloning-destination-title">Definir año y período</h3>
          </div>
          <strong>{derivedYear || 'Año según inicio'}</strong>
        </div>
        <div className="moodle-cloning-destination-fields">
          <label>
            <span>Subcategoría del período</span>
            <input
              value={periodName}
              maxLength={40}
              onChange={(event) => {
                setPeriodName(event.target.value.toUpperCase())
                resetReview()
              }}
              placeholder={offerType === 'REGULAR' ? 'R30' : 'H1'}
            />
            <small>{offerType === 'REGULAR' ? 'Ejemplo: R30' : 'Ejemplo: H1; se agregará el año automáticamente'}</small>
          </label>
          <label>
            <span>Inicio del curso</span>
            <input
              type="datetime-local"
              value={openingAt}
              onChange={(event) => {
                setOpeningAt(event.target.value)
                resetReview()
              }}
            />
            <small>El año de esta fecha crea la categoría correspondiente.</small>
          </label>
          <label>
            <span>Fin del curso</span>
            <input
              type="datetime-local"
              value={closingAt}
              min={openingAt || undefined}
              onChange={(event) => {
                setClosingAt(event.target.value)
                resetReview()
              }}
            />
            <small>Opcional; debe ser posterior al inicio.</small>
          </label>
          <label>
            <span>Paralelo</span>
            <input
              value={parallel}
              maxLength={20}
              onChange={(event) => {
                setParallel(event.target.value.toUpperCase())
                resetReview()
              }}
              placeholder="Opcional"
            />
            <small>Se añade al nombre cuando existen cursos paralelos.</small>
          </label>
        </div>
        <div className="moodle-cloning-route-example">
          <span>Ruta prevista</span>
          <strong>
            OFERTA_ACADEMICA / {destinationBranch} / {derivedYear || 'AÑO'} / {offerType} / {periodName || 'PERÍODO'}
          </strong>
        </div>
      </section>

      <div className="moodle-cloning-actions">
        <span>Los cursos nuevos quedarán ocultos y sin usuarios matriculados.</span>
        <button
          type="button"
          className="moodle-button moodle-button--primary"
          disabled={catalogLoading || previewLoading || applying || !catalog?.catalog_ready}
          onClick={() => void reviewPlan()}
        >
          {previewLoading ? 'Preparando vista previa...' : 'Previsualizar clonación'}
        </button>
      </div>

      {preview && (
        <section className="moodle-cloning-review" aria-labelledby="cloning-review-title">
          <div className="moodle-cloning-step__heading">
            <div>
              <span>Paso 3</span>
              <h3 id="cloning-review-title">Revisar antes de clonar</h3>
            </div>
            <span className={`moodle-cloning-status ${preview.ready ? 'is-success' : 'is-error'}`}>
              {preview.ready ? 'Listo para aplicar' : 'Requiere corrección'}
            </span>
          </div>
          <div className="moodle-cloning-summary">
            <div><span>Materias</span><strong>{preview.summary.selected}</strong></div>
            <div><span>Por clonar</span><strong>{preview.summary.to_clone}</strong></div>
            <div><span>Categorías nuevas</span><strong>{preview.summary.categories_to_create}</strong></div>
            <div><span>Existentes</span><strong>{preview.summary.existing}</strong></div>
            <div><span>Conflictos</span><strong>{preview.summary.course_conflicts + preview.summary.category_conflicts}</strong></div>
          </div>

          <div className="moodle-cloning-review-grid">
            <div>
              <h4>Categorías</h4>
              <div className="moodle-cloning-plan-list">
                {preview.categories.map((item) => (
                  <div key={item.idnumber}>
                    <span className={`moodle-cloning-status ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                    <strong>{item.path}</strong>
                    {item.conflict && <small>{item.conflict}</small>}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4>Cursos</h4>
              <div className="moodle-cloning-plan-list">
                {preview.courses.map((item) => (
                  <div key={item.template_course_id}>
                    <span className={`moodle-cloning-status ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                    <strong>{item.fullname}</strong>
                    <small>Nombre corto: {item.shortname}</small>
                    <small>Número ID: {item.idnumber}</small>
                    <small>{item.destination_path}</small>
                    {item.conflict && <small>{item.conflict}</small>}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="moodle-cloning-actions">
            <span>{preview.period_name} · inicio {new Date(preview.opening_at).toLocaleString('es-EC')}</span>
            <button
              type="button"
              className="moodle-button moodle-button--primary"
              disabled={!preview.ready || !preview.capability.enabled || applying}
              onClick={() => setConfirmOpen(true)}
            >
              Confirmar clonación
            </button>
          </div>
        </section>
      )}

      {result && (
        <section className="moodle-cloning-result" aria-live="polite">
          <div className="moodle-cloning-step__heading">
            <div>
              <span>Resultado</span>
              <h3>{result.message}</h3>
            </div>
            <span className={`moodle-cloning-status ${result.ok ? 'is-success' : 'is-warning'}`}>
              {result.ok ? 'Completado' : 'Completado con novedades'}
            </span>
          </div>
          <div className="moodle-cloning-plan-list">
            {result.courses.map((item) => (
              <div key={`${item.template_course_id}-${item.status}`}>
                <span className={`moodle-cloning-status ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                <strong>{item.fullname}</strong>
                <small>Nombre corto: {item.shortname}</small>
                <small>Número ID: {item.idnumber}</small>
                <small>{item.message}</small>
              </div>
            ))}
          </div>
        </section>
      )}

      {confirmOpen && preview && (
        <div
          className="moodle-confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !applying) setConfirmOpen(false)
          }}
        >
          <div className="moodle-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="cloning-confirm-title">
            <div className="moodle-confirm-dialog__header">
              <div>
                <span>Confirmación</span>
                <h2 id="cloning-confirm-title">Clonar {preview.summary.to_clone} curso(s)</h2>
              </div>
            </div>
            <div className="moodle-confirm-dialog__body">
              <p>
                Se crearán las categorías faltantes y los cursos quedarán ocultos. Las matrículas,
                usuarios, roles e historiales de la plantilla no se copiarán.
              </p>
            </div>
            <div className="moodle-confirm-dialog__actions">
              <button
                type="button"
                className="moodle-button moodle-button--secondary"
                disabled={applying}
                onClick={() => setConfirmOpen(false)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="moodle-button moodle-button--primary"
                disabled={applying}
                onClick={() => void applyPlan()}
              >
                {applying ? 'Clonando cursos...' : 'Crear oferta académica'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
