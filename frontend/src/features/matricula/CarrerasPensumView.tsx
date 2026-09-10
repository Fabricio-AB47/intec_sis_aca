import { useEffect, useMemo, useRef, useState } from 'react'

import {
  createSisAcademicoRecord,
  fetchSisAcademicoRecord,
  fetchSisAcademicoRows,
  updateSisAcademicoRecord,
} from '../../lib/api'
import type {
  SisAcademicoField,
  SisAcademicoRow,
  SisAcademicoSection,
} from '../../types/app'

type FormValue = string | number | boolean | null | undefined

type CarrerasPensumViewProps = {
  careerSection?: SisAcademicoSection
  subjectSection?: SisAcademicoSection
  onStatsChange?: (stats: { careers: number; subjects: number }) => void
}

type EditorState = {
  entity: 'career' | 'subject'
  mode: 'create' | 'edit'
  recordKey: string
  values: Record<string, FormValue>
}

const CAREER_PAGE_SIZE = 20
const SUBJECT_PAGE_SIZE = 25

function inputValue(value: FormValue): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function displayValue(value: FormValue): string {
  const normalized = inputValue(value).trim()
  return normalized || '-'
}

function compactValues(...values: FormValue[]): string {
  return values.map(displayValue).filter((value) => value !== '-').join(' · ')
}

function rowKey(row: SisAcademicoRow): string {
  return String(row._record_key || '')
}

function careerCode(row?: SisAcademicoRow | null): string {
  return inputValue(row?.Cod_AnioBasica).trim()
}

function normalizedFormValues(values: SisAcademicoRow): Record<string, FormValue> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value]),
  )
}

function coerceValue(field: SisAcademicoField, value: string): FormValue {
  if (value === '') return ''
  if (field.type === 'number' || field.type === 'decimal') return Number(value)
  if (field.type === 'bool') return value === 'true'
  return value
}

function emptyForm(fields: SisAcademicoField[]): Record<string, FormValue> {
  return fields.reduce<Record<string, FormValue>>((values, field) => {
    values[field.name] = field.type === 'bool' ? false : ''
    return values
  }, {})
}

function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize))
}

type PagerProps = {
  page: number
  total: number
  pageSize: number
  loading: boolean
  label: string
  onPageChange: (page: number) => void
}

function Pager({ page, total, pageSize, loading, label, onPageChange }: Readonly<PagerProps>) {
  const pages = pageCount(total, pageSize)
  return (
    <div className="career-pensum__pager" aria-label={`Paginación de ${label}`}>
      <span>{total} {label} · Página {page} de {pages}</span>
      <div>
        <button
          type="button"
          aria-label="Página anterior"
          title="Página anterior"
          disabled={loading || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <span aria-hidden="true">←</span>
        </button>
        <button
          type="button"
          aria-label="Página siguiente"
          title="Página siguiente"
          disabled={loading || page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </div>
  )
}

export function CarrerasPensumView({
  careerSection,
  subjectSection,
  onStatsChange,
}: Readonly<CarrerasPensumViewProps>) {
  const careerRequestRef = useRef(0)
  const subjectRequestRef = useRef(0)
  const [resolvedCareerSection, setResolvedCareerSection] = useState(careerSection)
  const [resolvedSubjectSection, setResolvedSubjectSection] = useState(subjectSection)
  const [careers, setCareers] = useState<SisAcademicoRow[]>([])
  const [careerQuery, setCareerQuery] = useState('')
  const [careerPage, setCareerPage] = useState(1)
  const [careerTotal, setCareerTotal] = useState(0)
  const [careersLoading, setCareersLoading] = useState(false)
  const [selectedCareer, setSelectedCareer] = useState<SisAcademicoRow | null>(null)
  const [subjects, setSubjects] = useState<SisAcademicoRow[]>([])
  const [subjectQuery, setSubjectQuery] = useState('')
  const [subjectPage, setSubjectPage] = useState(1)
  const [subjectTotal, setSubjectTotal] = useState(0)
  const [subjectsLoading, setSubjectsLoading] = useState(false)
  const [highlightedSubjectKey, setHighlightedSubjectKey] = useState('')
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [editorLoading, setEditorLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const selectedCareerCode = careerCode(selectedCareer)
  const editorSection = editor?.entity === 'career' ? resolvedCareerSection : resolvedSubjectSection
  const editorFields = useMemo(() => {
    if (!editor || !editorSection) return []
    const fields = editor.mode === 'create' ? editorSection.create_fields || [] : editorSection.editable_fields || []
    return editor.entity === 'subject'
      ? fields.filter((field) => field.name !== 'Cod_AnioBasica')
      : fields
  }, [editor, editorSection])

  useEffect(() => {
    setResolvedCareerSection((current) => current || careerSection)
  }, [careerSection])

  useEffect(() => {
    setResolvedSubjectSection((current) => current || subjectSection)
  }, [subjectSection])

  useEffect(() => {
    onStatsChange?.({ careers: careerTotal, subjects: subjectTotal })
  }, [careerTotal, onStatsChange, subjectTotal])

  async function loadSubjects(code: string, page = 1, query = subjectQuery) {
    if (!code) {
      setSubjects([])
      setSubjectTotal(0)
      setSubjectPage(1)
      return
    }
    const requestId = subjectRequestRef.current + 1
    subjectRequestRef.current = requestId
    setSubjectsLoading(true)
    setError('')
    try {
      const payload = await fetchSisAcademicoRows('materias', query.trim(), {
        careerCode: code,
        page,
        pageSize: SUBJECT_PAGE_SIZE,
      })
      if (requestId !== subjectRequestRef.current) return
      setResolvedSubjectSection(payload.section || subjectSection)
      setSubjects(payload.rows || [])
      setSubjectTotal(payload.total || 0)
      setSubjectPage(payload.page || page)
    } catch (apiError) {
      if (requestId !== subjectRequestRef.current) return
      setSubjects([])
      setSubjectTotal(0)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar el pensum de la carrera.')
    } finally {
      if (requestId === subjectRequestRef.current) setSubjectsLoading(false)
    }
  }

  async function loadCareers(page = 1, query = careerQuery, preferredCareerCode = '') {
    const requestId = careerRequestRef.current + 1
    careerRequestRef.current = requestId
    setCareersLoading(true)
    setError('')
    try {
      const payload = await fetchSisAcademicoRows('carreras', query.trim(), {
        page,
        pageSize: CAREER_PAGE_SIZE,
      })
      if (requestId !== careerRequestRef.current) return
      const nextCareers = payload.rows || []
      setResolvedCareerSection(payload.section || careerSection)
      setCareers(nextCareers)
      setCareerTotal(payload.total || 0)
      setCareerPage(payload.page || page)

      const preferredSelection = preferredCareerCode
        ? nextCareers.find((row) => careerCode(row) === preferredCareerCode)
        : undefined
      const currentKey = rowKey(selectedCareer || {})
      const refreshedSelection = nextCareers.find((row) => rowKey(row) === currentKey)
      if (preferredSelection) {
        setSelectedCareer(preferredSelection)
        setSubjectQuery('')
        setSubjects([])
        setSubjectTotal(0)
        setSubjectPage(1)
        setHighlightedSubjectKey('')
        void loadSubjects(careerCode(preferredSelection), 1, '')
      } else if (refreshedSelection) {
        setSelectedCareer(refreshedSelection)
      } else if (nextCareers[0]) {
        setSelectedCareer(nextCareers[0])
        setSubjectQuery('')
        setSubjects([])
        setSubjectTotal(0)
        setSubjectPage(1)
        setHighlightedSubjectKey('')
        void loadSubjects(careerCode(nextCareers[0]), 1, '')
      } else {
        setSelectedCareer(null)
        setSubjects([])
        setSubjectTotal(0)
        setSubjectPage(1)
      }
    } catch (apiError) {
      if (requestId !== careerRequestRef.current) return
      setCareers([])
      setCareerTotal(0)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar las carreras.')
    } finally {
      if (requestId === careerRequestRef.current) setCareersLoading(false)
    }
  }

  useEffect(() => {
    void loadCareers(1, '')
    return () => {
      careerRequestRef.current += 1
      subjectRequestRef.current += 1
    }
    // La carga inicial se controla dentro del componente para evitar consultas duplicadas del contenedor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectCareer(row: SisAcademicoRow) {
    const code = careerCode(row)
    if (!code) return
    setSelectedCareer(row)
    setSubjectQuery('')
    setSubjects([])
    setSubjectTotal(0)
    setSubjectPage(1)
    setHighlightedSubjectKey('')
    setMessage('')
    setError('')
    void loadSubjects(code, 1, '')
  }

  function startCreate(entity: 'career' | 'subject') {
    const section = entity === 'career' ? resolvedCareerSection : resolvedSubjectSection
    if (!section) return
    if (entity === 'subject' && !selectedCareerCode) {
      setError('Seleccione una carrera antes de crear una materia.')
      return
    }
    const fields = section.create_fields || []
    const subjectMallaOptions = entity === 'subject'
      ? fields.find((field) => field.name === 'NumMalla')?.options || []
      : []
    const initialMalla = subjectMallaOptions.length === 1
      ? Number(subjectMallaOptions[0].value)
      : ''
    setEditor({
      entity,
      mode: 'create',
      recordKey: '',
      values: {
        ...emptyForm(fields),
        ...(entity === 'career'
          ? { Estado: 'A' }
          : {
              Cod_AnioBasica: Number(selectedCareerCode),
              NumMalla: initialMalla,
              ValorHora: 0,
              ValorHoraVirtual: 0,
              verreporte: 1,
              SecuenciaMateria: '0',
              estado_mat: 'A',
            }),
      },
    })
    setMessage('')
    setError('')
  }

  async function startEdit(entity: 'career' | 'subject', row: SisAcademicoRow) {
    const key = rowKey(row)
    if (!key) return
    setEditor({ entity, mode: 'edit', recordKey: key, values: normalizedFormValues(row) })
    setEditorLoading(true)
    setMessage('')
    setError('')
    try {
      const payload = await fetchSisAcademicoRecord(entity === 'career' ? 'carreras' : 'materias', key)
      if (entity === 'career') setResolvedCareerSection(payload.section || careerSection)
      else setResolvedSubjectSection(payload.section || subjectSection)
      setEditor((current) => current?.recordKey === key
        ? { ...current, values: normalizedFormValues(payload.record || row) }
        : current)
    } catch (apiError) {
      setEditor(null)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el registro.')
    } finally {
      setEditorLoading(false)
    }
  }

  async function saveEditor() {
    if (!editor || !editorSection) return
    const missingField = editorFields.find(
      (field) => field.required && inputValue(editor.values[field.name]).trim() === '',
    )
    if (missingField) {
      setError(`Complete el campo requerido: ${missingField.label}.`)
      return
    }

    const sectionKey = editor.entity === 'career' ? 'carreras' : 'materias'
    const values = editor.entity === 'subject'
      ? { ...editor.values, Cod_AnioBasica: Number(selectedCareerCode) }
      : editor.values
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const result = editor.mode === 'create'
        ? await createSisAcademicoRecord(sectionKey, values)
        : await updateSisAcademicoRecord(sectionKey, editor.recordKey, values)
      if (editor.entity === 'career') {
        setEditor(null)
        if (editor.mode === 'create') {
          const createdCareerCode = inputValue(result.record?.Cod_AnioBasica ?? values.Cod_AnioBasica).trim()
          setCareerQuery(createdCareerCode)
          await loadCareers(1, createdCareerCode, createdCareerCode)
        } else if (selectedCareer && rowKey(selectedCareer) === editor.recordKey) {
          setSelectedCareer({ ...selectedCareer, ...editor.values })
          await loadCareers(careerPage)
        } else {
          await loadCareers(careerPage)
        }
      } else {
        setEditor(null)
        if (editor.mode === 'create') {
          const createdKey = inputValue(result.record_key ?? result.record?._record_key).trim()
          setSubjectQuery('')
          setHighlightedSubjectKey(createdKey)
          await loadSubjects(selectedCareerCode, 1, '')
        } else {
          await loadSubjects(selectedCareerCode, subjectPage)
        }
      }
      setMessage(result.message || 'Cambios guardados.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el registro.')
    } finally {
      setSaving(false)
    }
  }

  function renderField(field: SisAcademicoField) {
    if (!editor) return null
    const value = inputValue(editor.values[field.name])
    const options = field.options || []
    const isFreeCareerText = editor.entity === 'career' && ['Nombre_Basica', 'tp_escuela'].includes(field.name)
    const useSelect = !isFreeCareerText && options.length > 0
    const updateValue = (nextValue: string) => {
      setEditor((current) => current
        ? { ...current, values: { ...current.values, [field.name]: coerceValue(field, nextValue) } }
        : current)
    }

    return (
      <label key={field.name} className={field.type === 'textarea' ? 'career-pensum__field--wide' : ''}>
        <span>{field.label}{field.required ? ' *' : ''}</span>
        {useSelect ? (
          <select value={value} onChange={(event) => updateValue(event.target.value)}>
            <option value="">{field.required ? `Seleccione ${field.label.toLowerCase()}` : 'Sin asignar'}</option>
            {value && !options.some((option) => String(option.value) === value) ? (
              <option value={value}>{value} (valor actual)</option>
            ) : null}
            {options.map((option) => (
              <option key={`${field.name}-${option.value}`} value={option.value}>{option.label}</option>
            ))}
          </select>
        ) : field.type === 'textarea' ? (
          <textarea
            value={value}
            maxLength={field.max_length || undefined}
            onChange={(event) => updateValue(event.target.value)}
          />
        ) : (
          <input
            type={field.type === 'number' || field.type === 'decimal' ? 'number' : 'text'}
            step={
              field.type === 'decimal'
                ? ['ValorHora', 'ValorHoraVirtual'].includes(field.name) ? '0.00001' : '0.01'
                : undefined
            }
            maxLength={field.max_length || undefined}
            value={value}
            onChange={(event) => updateValue(event.target.value)}
          />
        )}
      </label>
    )
  }

  return (
    <div className="career-pensum">
      {message ? <p className="teams-message">{message}</p> : null}
      {!editor && error ? <p className="teams-error" role="alert">{error}</p> : null}

      <div className="career-pensum__layout">
        <aside className="career-pensum__careers" aria-label="Carreras académicas">
          <div className="career-pensum__section-head">
            <div>
              <span>Carreras</span>
              <strong>Catálogo académico</strong>
            </div>
            <button type="button" className="primary-action" onClick={() => startCreate('career')}>
              Nueva carrera
            </button>
          </div>

          <form
            className="career-pensum__search"
            onSubmit={(event) => {
              event.preventDefault()
              void loadCareers(1)
            }}
          >
            <label>
              <span>Buscar carrera</span>
              <input
                value={careerQuery}
                onChange={(event) => setCareerQuery(event.target.value)}
                placeholder="Nombre, código, abreviatura o escuela"
              />
            </label>
            <button type="submit" disabled={careersLoading}>{careersLoading ? 'Consultando...' : 'Buscar'}</button>
          </form>

          <div className="career-pensum__career-list">
            {careers.length > 0 ? careers.map((career) => {
              const active = rowKey(career) === rowKey(selectedCareer || {})
              return (
                <button
                  key={rowKey(career)}
                  type="button"
                  className={active ? 'is-active' : ''}
                  aria-pressed={active}
                  onClick={() => selectCareer(career)}
                >
                  <strong>{displayValue(career.Nombre_Basica)}</strong>
                  <span>{compactValues(`Código ${displayValue(career.Cod_AnioBasica)}`, career.tp_escuela)}</span>
                  <em>{displayValue(career.Estado)}</em>
                </button>
              )
            }) : (
              <p>{careersLoading ? 'Consultando carreras...' : 'No existen carreras para el criterio indicado.'}</p>
            )}
          </div>

          <Pager
            page={careerPage}
            total={careerTotal}
            pageSize={CAREER_PAGE_SIZE}
            loading={careersLoading}
            label="carrera(s)"
            onPageChange={(page) => void loadCareers(page)}
          />
        </aside>

        <section className="career-pensum__subjects" aria-label="Pensum relacionado con la carrera">
          {selectedCareer ? (
            <>
              <div className="career-pensum__career-head">
                <div>
                  <span>Carrera seleccionada</span>
                  <h3>{displayValue(selectedCareer.Nombre_Basica)}</h3>
                  <p>
                    {compactValues(`Código ${selectedCareerCode}`, selectedCareer.tp_escuela, selectedCareer.Abrevia)}
                  </p>
                </div>
                <div>
                  <button type="button" onClick={() => void startEdit('career', selectedCareer)}>Editar carrera</button>
                  <button
                    type="button"
                    className="primary-action"
                    onClick={() => startCreate('subject')}
                    disabled={subjectsLoading}
                  >
                    Nueva materia
                  </button>
                </div>
              </div>

              <div className="career-pensum__metrics">
                <div><span>Código de carrera</span><strong>{selectedCareerCode}</strong></div>
                <div><span>Tipo de escuela</span><strong>{displayValue(selectedCareer.tp_escuela)}</strong></div>
                <div><span>Estado</span><strong>{displayValue(selectedCareer.Estado)}</strong></div>
                <div><span>Materias del pensum</span><strong>{subjectTotal}</strong></div>
              </div>

              <form
                className="career-pensum__subject-toolbar"
                onSubmit={(event) => {
                  event.preventDefault()
                  void loadSubjects(selectedCareerCode, 1)
                }}
              >
                <label>
                  <span>Buscar en este pensum</span>
                  <input
                    value={subjectQuery}
                    onChange={(event) => setSubjectQuery(event.target.value)}
                    placeholder="Materia, código único, nivel o estado"
                  />
                </label>
                <button type="submit" disabled={subjectsLoading}>{subjectsLoading ? 'Consultando...' : 'Buscar'}</button>
              </form>

              <div className="matricula-table-wrap career-pensum__table-wrap">
                <table className="matricula-table career-pensum__table">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Código único</th>
                      <th>Materia</th>
                      <th>Unidad</th>
                      <th>Semestre</th>
                      <th>Créditos</th>
                      <th>Horas</th>
                      <th>Malla</th>
                      <th>Tipo</th>
                      <th>Estado</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subjects.length > 0 ? subjects.map((subject) => (
                      <tr
                        key={rowKey(subject)}
                        className={rowKey(subject) === highlightedSubjectKey ? 'career-pensum__row--created' : undefined}
                      >
                        <td>{displayValue(subject.codigo_materia)}</td>
                        <td><strong>{displayValue(subject.cod_materia)}</strong></td>
                        <td>{displayValue(subject.Nomb_Materia)}</td>
                        <td>{displayValue(subject.Unidad_Organiza)}</td>
                        <td>{displayValue(subject.Semestre)}</td>
                        <td>{displayValue(subject.Creditos)}</td>
                        <td>{displayValue(subject.Horas)}</td>
                        <td>{displayValue(subject.NumMalla)}</td>
                        <td>{displayValue(subject.tipomateria)}</td>
                        <td>{displayValue(subject.estado_mat)}</td>
                        <td>
                          <button type="button" className="reporteria-row-action" onClick={() => void startEdit('subject', subject)}>
                            Editar
                          </button>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={11}>{subjectsLoading ? 'Consultando materias...' : 'Esta carrera todavía no tiene materias registradas.'}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <Pager
                page={subjectPage}
                total={subjectTotal}
                pageSize={SUBJECT_PAGE_SIZE}
                loading={subjectsLoading}
                label="materia(s)"
                onPageChange={(page) => void loadSubjects(selectedCareerCode, page)}
              />
            </>
          ) : (
            <div className="career-pensum__empty">
              <strong>Seleccione una carrera</strong>
              <span>El pensum se cargará con las materias vinculadas por Cod_AnioBasica.</span>
            </div>
          )}
        </section>
      </div>

      {editor && editorSection ? (
        <div
          className="matricula-modal-overlay career-pensum__modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="career-pensum-editor-title"
        >
          <article className="matricula-modal gestion-sis-modal career-pensum__modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>{editor.entity === 'career' ? 'Carrera' : 'Pensum académico'}</span>
                <h3 id="career-pensum-editor-title">
                  {editor.mode === 'create'
                    ? editor.entity === 'career' ? 'Nueva carrera' : 'Nueva materia'
                    : editor.entity === 'career' ? 'Editar carrera' : 'Editar materia'}
                </h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setEditor(null)} disabled={saving}>
                Cerrar
              </button>
            </div>

            {editor.entity === 'subject' ? (
              <div className="career-pensum__relation">
                <span>Carrera relacionada</span>
                <strong>{displayValue(selectedCareer?.Nombre_Basica)}</strong>
                <em>Cod_AnioBasica {selectedCareerCode}</em>
              </div>
            ) : null}

            {error ? <p className="teams-error career-pensum__modal-error" role="alert">{error}</p> : null}

            <div className="matricula-acad-form career-pensum__form">
              {editorFields.map(renderField)}
            </div>

            <div className="teams-actions gestion-sis-modal-actions">
              <button type="button" className="gestion-sis-modal-actions__secondary" onClick={() => setEditor(null)} disabled={saving}>
                Cancelar
              </button>
              <button type="button" onClick={() => void saveEditor()} disabled={saving || editorLoading}>
                {saving
                  ? 'Guardando...'
                  : editorLoading
                    ? 'Cargando...'
                    : editor.mode === 'create'
                      ? editor.entity === 'career' ? 'Crear carrera' : 'Crear materia'
                      : 'Guardar cambios'}
              </button>
            </div>
          </article>
        </div>
      ) : null}
    </div>
  )
}
