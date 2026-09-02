import { useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  fetchMoodleCourses,
  fetchMoodleEditableContent,
  updateMoodleEditableContent,
} from '../../lib/api'
import type {
  MoodleCourse,
  MoodleEditableContentResponse,
  MoodleEditableContentType,
} from '../../types/app'

type EditableTarget = {
  key: string
  targetType: MoodleEditableContentType
  targetId: number
  sectionId: number
  sectionName: string
  label: string
  name: string
  html: string
  visible: boolean
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudo completar la operación en Moodle.'
}

function courseLabel(course: MoodleCourse): string {
  const code = course.shortname || course.idnumber
  return code ? `${course.fullname} · ${code}` : course.fullname
}

function previewDocument(html: string): string {
  return `<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; media-src https:; style-src 'unsafe-inline'; font-src https: data:;">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body { margin: 0; padding: 20px; color: #14213d; background: #fff; font: 16px/1.55 Arial, sans-serif; overflow-wrap: anywhere; }
      img, video, iframe, table { max-width: 100%; }
      table { border-collapse: collapse; }
      td, th { border: 1px solid #cbd5df; padding: 8px; }
      a { color: #006d7a; }
    </style>
  </head>
  <body>${html || '<p>El contenido está vacío.</p>'}</body>
</html>`
}

export function MoodleContentEditorPanel() {
  const [courses, setCourses] = useState<MoodleCourse[]>([])
  const [courseSearch, setCourseSearch] = useState('')
  const [selectedCourseId, setSelectedCourseId] = useState(0)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [contentLoading, setContentLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [content, setContent] = useState<MoodleEditableContentResponse | null>(null)
  const [selectedTargetKey, setSelectedTargetKey] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftHtml, setDraftHtml] = useState('')
  const [editorMode, setEditorMode] = useState<'html' | 'preview'>('html')

  const targets = useMemo<EditableTarget[]>(() => {
    if (!content) return []
    return content.sections.flatMap((section) => [
      {
        key: `section:${section.target_id}`,
        targetType: 'section' as const,
        targetId: section.target_id,
        sectionId: section.target_id,
        sectionName: section.display_name,
        label: `Resumen de ${section.display_name}`,
        name: section.name,
        html: section.html,
        visible: section.visible,
      },
      ...section.items.map((item) => ({
        key: `${item.target_type}:${item.target_id}`,
        targetType: item.target_type,
        targetId: item.target_id,
        sectionId: section.target_id,
        sectionName: section.display_name,
        label: `${item.target_type === 'label' ? 'Etiqueta' : 'Página'}: ${item.name}`,
        name: item.name,
        html: item.html,
        visible: item.visible,
      })),
    ])
  }, [content])

  const selectedTarget = useMemo(
    () => targets.find((target) => target.key === selectedTargetKey) ?? null,
    [selectedTargetKey, targets],
  )

  const isDirty = Boolean(
    selectedTarget
      && (selectedTarget.name !== draftName || selectedTarget.html !== draftHtml),
  )

  const loadCatalog = async (refresh = false) => {
    setCatalogLoading(true)
    setError('')
    try {
      const response = await fetchMoodleCourses({
        page: 1,
        pageSize: 200,
        search: courseSearch,
        visibility: 'all',
        refresh,
      })
      setCourses(response.items)
      if (selectedCourseId && !response.items.some((course) => course.id === selectedCourseId)) {
        setSelectedCourseId(0)
        setContent(null)
        setSelectedTargetKey('')
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setCatalogLoading(false)
    }
  }

  const loadContent = async (refresh = false, preferredTargetKey = '') => {
    if (!selectedCourseId) return
    setContentLoading(true)
    setError('')
    setSuccess('')
    try {
      const response = await fetchMoodleEditableContent(selectedCourseId, refresh)
      setContent(response)
      const availableKeys = response.sections.flatMap((section) => [
        `section:${section.target_id}`,
        ...section.items.map((item) => `${item.target_type}:${item.target_id}`),
      ])
      setSelectedTargetKey(
        preferredTargetKey && availableKeys.includes(preferredTargetKey)
          ? preferredTargetKey
          : availableKeys[0] ?? '',
      )
    } catch (requestError) {
      setContent(null)
      setSelectedTargetKey('')
      setError(errorMessage(requestError))
    } finally {
      setContentLoading(false)
    }
  }

  useEffect(() => {
    void loadCatalog()
    // El catálogo inicial se consulta una sola vez; las búsquedas se ejecutan bajo demanda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedTarget) {
      setDraftName('')
      setDraftHtml('')
      return
    }
    setDraftName(selectedTarget.name)
    setDraftHtml(selectedTarget.html)
    setEditorMode('html')
  }, [selectedTarget])

  useEffect(() => {
    if (!success) return undefined
    const timeout = window.setTimeout(() => setSuccess(''), 3000)
    return () => window.clearTimeout(timeout)
  }, [success])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    void loadCatalog(false)
  }

  const chooseTarget = (target: EditableTarget) => {
    if (target.key === selectedTargetKey) return
    if (isDirty && !window.confirm('Hay cambios sin guardar. ¿Desea cambiar de contenido?')) return
    setSelectedTargetKey(target.key)
  }

  const resetDraft = () => {
    if (!selectedTarget) return
    setDraftName(selectedTarget.name)
    setDraftHtml(selectedTarget.html)
    setError('')
  }

  const saveDraft = async () => {
    if (!selectedTarget || !selectedCourseId || !isDirty) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const result = await updateMoodleEditableContent(
        selectedCourseId,
        selectedTarget.targetType,
        selectedTarget.targetId,
        { name: draftName.trim(), html: draftHtml },
      )
      await loadContent(true, selectedTarget.key)
      setSuccess(result.message || 'El contenido se actualizó correctamente en Moodle.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="moodle-section moodle-content-editor">
      <div className="moodle-section__heading">
        <div>
          <span>Edición controlada</span>
          <h2>Contenido HTML del curso</h2>
          <p>
            Edite los resúmenes, etiquetas y páginas de Información general y Material académico.
          </p>
        </div>
        <button
          type="button"
          className="moodle-button moodle-button--secondary"
          disabled={catalogLoading}
          onClick={() => void loadCatalog(true)}
        >
          {catalogLoading ? 'Actualizando...' : 'Actualizar catálogo'}
        </button>
      </div>

      {error && <div className="moodle-alert moodle-alert--error" role="alert">{error}</div>}
      {success && <div className="moodle-alert moodle-alert--success" role="status">{success}</div>}

      <form className="moodle-content-editor__course" onSubmit={submitSearch}>
        <label>
          <span>Buscar curso</span>
          <input
            type="search"
            value={courseSearch}
            maxLength={256}
            placeholder="Nombre, nombre corto, código o ID"
            onChange={(event) => setCourseSearch(event.target.value)}
          />
        </label>
        <button type="submit" className="moodle-button moodle-button--secondary" disabled={catalogLoading}>
          Buscar
        </button>
        <label className="moodle-content-editor__course-select">
          <span>Curso Moodle</span>
          <select
            value={selectedCourseId || ''}
            disabled={catalogLoading}
            onChange={(event) => {
              const nextCourseId = Number(event.target.value) || 0
              setSelectedCourseId(nextCourseId)
              setContent(null)
              setSelectedTargetKey('')
            }}
          >
            <option value="">Seleccione un curso</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>{courseLabel(course)}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="moodle-button moodle-button--primary"
          disabled={!selectedCourseId || contentLoading}
          onClick={() => void loadContent(true)}
        >
          {contentLoading ? 'Cargando...' : 'Cargar contenido'}
        </button>
      </form>

      {content && (
        <>
          {!content.editor.enabled && (
            <div className="moodle-alert moodle-alert--warning">
              {content.editor.reason || 'La edición HTML no está habilitada para este servicio.'}
            </div>
          )}

          <div className="moodle-content-editor__summary">
            <strong>{content.course.fullname}</strong>
            <span>{content.totals.sections} sección(es) · {content.totals.items} recurso(s) editable(s)</span>
          </div>

          {targets.length === 0 ? (
            <div className="moodle-empty">
              El curso no contiene secciones editables de Información general o Material académico.
            </div>
          ) : (
            <div className="moodle-content-editor__workspace">
              <aside className="moodle-content-editor__targets" aria-label="Contenidos editables">
                {content.sections.map((section) => {
                  const sectionTargets = targets.filter((target) => target.sectionId === section.target_id)
                  return (
                    <section key={section.target_id}>
                      <h3>{section.display_name}</h3>
                      {sectionTargets.map((target) => (
                        <button
                          key={target.key}
                          type="button"
                          className={target.key === selectedTargetKey ? 'is-active' : ''}
                          onClick={() => chooseTarget(target)}
                        >
                          <span>{target.label}</span>
                          <small>{target.visible ? 'Visible' : 'Oculto'}</small>
                        </button>
                      ))}
                    </section>
                  )
                })}
              </aside>

              {selectedTarget && (
                <div className="moodle-content-editor__form">
                  <div className="moodle-content-editor__form-heading">
                    <div>
                      <span>{selectedTarget.sectionName}</span>
                      <h3>{selectedTarget.label}</h3>
                    </div>
                    <div className="moodle-content-editor__modes" role="tablist" aria-label="Vista del contenido">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={editorMode === 'html'}
                        className={editorMode === 'html' ? 'is-active' : ''}
                        onClick={() => setEditorMode('html')}
                      >
                        Código HTML
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={editorMode === 'preview'}
                        className={editorMode === 'preview' ? 'is-active' : ''}
                        onClick={() => setEditorMode('preview')}
                      >
                        Vista previa
                      </button>
                    </div>
                  </div>

                  <label>
                    <span>Título</span>
                    <input
                      type="text"
                      value={draftName}
                      maxLength={selectedTarget.targetType === 'section' ? 1333 : 255}
                      disabled={!content.editor.enabled || saving}
                      onChange={(event) => setDraftName(event.target.value)}
                    />
                  </label>

                  {editorMode === 'html' ? (
                    <label>
                      <span>Contenido HTML</span>
                      <textarea
                        className="moodle-content-editor__textarea"
                        value={draftHtml}
                        maxLength={1_000_000}
                        spellCheck={false}
                        disabled={!content.editor.enabled || saving}
                        onChange={(event) => setDraftHtml(event.target.value)}
                      />
                      <small>{new Intl.NumberFormat('es-EC').format(draftHtml.length)} de 1.000.000 caracteres</small>
                    </label>
                  ) : (
                    <iframe
                      className="moodle-content-editor__preview"
                      title="Vista previa del contenido de Moodle"
                      sandbox=""
                      srcDoc={previewDocument(draftHtml)}
                    />
                  )}

                  <div className="moodle-content-editor__actions">
                    <button
                      type="button"
                      className="moodle-button moodle-button--secondary"
                      disabled={!isDirty || saving}
                      onClick={resetDraft}
                    >
                      Deshacer cambios
                    </button>
                    <button
                      type="button"
                      className="moodle-button moodle-button--primary"
                      disabled={!content.editor.enabled || !isDirty || saving || !draftName.trim()}
                      onClick={() => void saveDraft()}
                    >
                      {saving ? 'Guardando...' : 'Guardar en Moodle'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
