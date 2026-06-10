import { Fragment, useEffect, useMemo, useState } from 'react'

import {
  createSisAcademicoRecord,
  fetchSisAcademicoCatalog,
  fetchSisAcademicoRecord,
  fetchSisAcademicoRows,
  updateSisAcademicoRecord,
} from '../../lib/api'
import type { SisAcademicoField, SisAcademicoRow, SisAcademicoSection } from '../../types/app'

type GestionSisAcademicoViewProps = {
  displayName: string
  initialSectionKey?: string
}

type FormValue = string | number | boolean | null | undefined
type OptionItem = { value: string; label: string }
type InlineEstadoValues = Record<string, { Estado?: string; Informacion?: string }>
type HomoMateriaGroup = {
  key: string
  name: string
  codes: string[]
  labels: string[]
}

type ProcessShortcut = {
  key: string
  title: string
  description: string
  sections: string[]
}

const processShortcuts: ProcessShortcut[] = [
  {
    key: 'admision',
    title: 'Admision',
    description: 'Preinscripcion, aspirantes, asesores, factura y documentos de ingreso.',
    sections: ['preinscripciones', 'datos_factura'],
  },
  {
    key: 'matriculas',
    title: 'Matriculas',
    description: 'Cabecera, materias, pagos y control de matricula.',
    sections: ['cabecera_matricula', 'matricula_materias', 'pagos_matricula'],
  },
  {
    key: 'notas',
    title: 'Notas',
    description: 'Notas por estudiante, carrera, materia, periodo y paralelo.',
    sections: ['matricula_materias', 'materias'],
  },
  {
    key: 'personas',
    title: 'Estudiante',
    description: 'Listado, ficha, documentos, correos institucionales y datos academicos.',
    sections: ['actualizacion_estudiantes', 'estudiantes', 'registro_documentos_estudiante', 'correos', 'seguimiento'],
  },
  {
    key: 'docencia',
    title: 'Docente',
    description: 'Ingreso de docentes, asignacion de materias, cuestionarios, evaluacion y estado Moodle.',
    sections: [
      'docentes',
      'actualizacion_est',
      'docente_materias',
      'numero_preguntas',
      'cuestionarios',
      'planes_foros',
      'preguntas_evaluacion',
      'evaluacion_resultados',
      'autoevaluacion_resultados',
      'fechas_autoevaluacion',
    ],
  },
  {
    key: 'administrativos',
    title: 'Administrativos',
    description: 'Usuarios administrativos, perfiles y accesos del menu.',
    sections: ['usuarios', 'menu_usuarios', 'menu_general'],
  },
  {
    key: 'academico',
    title: 'Proceso academico',
    description: 'Carreras, materias, mallas, textos HOMO, paralelos, periodos, asistencia y aperturas.',
    sections: [
      'carreras',
      'materias',
      'mallas',
      'materia_homo_textof',
      'periodos',
      'fechas_notas',
      'fechas_autoevaluacion',
      'asistencia_estudiantes',
      'provincias',
      'paralelos',
      'dias_matricula',
      'horarios_matricula',
      'jornadas',
      'modalidades',
    ],
  },
  {
    key: 'vinculacion',
    title: 'Seguimiento y practicas',
    description: 'Observaciones, practicas profesionales, vinculacion y empresas.',
    sections: ['seguimiento', 'practicas', 'practicas_vinculacion', 'empresas'],
  },
]

function valueLabel(value: FormValue): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'Si' : 'No'
  return String(value)
}

function fieldOptions(field: SisAcademicoField, value: FormValue) {
  const options = field.options || []
  const currentValue = inputValue(value)
  if (!currentValue || options.some((option) => String(option.value) === currentValue)) {
    return options
  }
  return [{ value: currentValue, label: `${currentValue} (valor actual)` }, ...options]
}

function displayValue(field: SisAcademicoField, value: FormValue): string {
  const currentValue = inputValue(value)
  const option = field.options?.find((item) => String(item.value) === currentValue)
  return option?.label || valueLabel(value)
}

function inputValue(value: FormValue): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function recordKey(row: SisAcademicoRow): string {
  return String(row._record_key || '')
}

function coerceFieldValue(field: SisAcademicoField, value: string | boolean): FormValue {
  const type = field.type || 'text'
  if (type === 'bool') return Boolean(value)
  if (value === '') return ''
  if (type === 'number' || type === 'decimal') return Number(value)
  return String(value)
}

function materiaNameFromOption(label?: string): string {
  if (!label) return ''
  const parts = label.split(' - ')
  const withoutCode = (parts.length > 1 ? parts.slice(1).join(' - ') : label).trim()
  return withoutCode.replace(/\s*\([^)]*\)\s*$/, '').trim()
}

function normalizeSearchText(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase()
}

function uniqueOptionsByValue(options: OptionItem[]): OptionItem[] {
  const seen = new Set<string>()
  return options.filter((option) => {
    const value = String(option.value)
    if (!value || seen.has(value)) return false
    seen.add(value)
    return true
  })
}

function formatSpanishDate(value: string): string {
  const [yearText, monthText, dayText] = value.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const months = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
  ]
  if (!year || !month || !day || !months[month - 1]) return ''
  return `${day} de ${months[month - 1]} del ${year}`
}

function formatSpanishDateRange(start: string, end: string): string {
  const startText = formatSpanishDate(start)
  const endText = formatSpanishDate(end)
  if (!startText || !endText) return ''
  return `${startText} al ${endText}`
}

function emptyValues(fields: SisAcademicoField[]): Record<string, FormValue> {
  return fields.reduce<Record<string, FormValue>>((acc, field) => {
    acc[field.name] = field.type === 'bool' ? false : ''
    return acc
  }, {})
}

export function GestionSisAcademicoView({ displayName, initialSectionKey = '' }: Readonly<GestionSisAcademicoViewProps>) {
  const [sections, setSections] = useState<SisAcademicoSection[]>([])
  const [selectedSectionKey, setSelectedSectionKey] = useState('')
  const [appliedInitialSection, setAppliedInitialSection] = useState('')
  const [selectedProcessKey, setSelectedProcessKey] = useState(processShortcuts[0]?.key || '')
  const [query, setQuery] = useState('')
  const [estadoPeriodFilter, setEstadoPeriodFilter] = useState('')
  const [rows, setRows] = useState<SisAcademicoRow[]>([])
  const [selectedRecordKey, setSelectedRecordKey] = useState('')
  const [formValues, setFormValues] = useState<Record<string, FormValue>>({})
  const [mode, setMode] = useState<'edit' | 'create'>('edit')
  const [tableFilter, setTableFilter] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [inlineSavingKey, setInlineSavingKey] = useState('')
  const [inlineEstadoValues, setInlineEstadoValues] = useState<InlineEstadoValues>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [homoBulkPeriodo, setHomoBulkPeriodo] = useState('')
  const [homoBulkFechaInicio, setHomoBulkFechaInicio] = useState('')
  const [homoBulkFechaFin, setHomoBulkFechaFin] = useState('')
  const [homoBulkUrl, setHomoBulkUrl] = useState('')
  const [homoBulkSearch, setHomoBulkSearch] = useState('')
  const [homoBulkMateriaCodes, setHomoBulkMateriaCodes] = useState<string[]>([])
  const [homoMateriaSelectorOpen, setHomoMateriaSelectorOpen] = useState(false)
  const [homoMateriaNameSearch, setHomoMateriaNameSearch] = useState('')
  const [homoBulkSaving, setHomoBulkSaving] = useState(false)

  const selectedSection = useMemo(
    () => sections.find((section) => section.key === selectedSectionKey) || null,
    [sections, selectedSectionKey],
  )
  const processMenu = useMemo(
    () =>
      processShortcuts
        .map((process) => ({
          ...process,
          availableSections: process.sections
            .map((sectionKey) => sections.find((section) => section.key === sectionKey))
            .filter((section): section is SisAcademicoSection => Boolean(section))
            .sort((left, right) => left.title.localeCompare(right.title, 'es', { sensitivity: 'base' })),
        }))
        .filter((process) => process.availableSections.length > 0),
    [sections],
  )
  const selectedProcess = useMemo(
    () =>
      processMenu.find((process) => process.key === selectedProcessKey)
      || processMenu.find((process) => process.sections.includes(selectedSectionKey))
      || processMenu[0]
      || null,
    [processMenu, selectedProcessKey, selectedSectionKey],
  )
  const listFields = selectedSection?.list_fields || []
  const editableFields = selectedSection?.editable_fields || []
  const createFields = selectedSection?.create_fields || []
  const currentFields = mode === 'create' ? createFields : editableFields
  const canCreate = createFields.length > 0
  const isEstadoInlineSection = selectedSectionKey === 'actualizacion_est' || selectedSectionKey === 'actualizacion_estudiantes'
  const isDocenteEstadoSection = selectedSectionKey === 'actualizacion_est'
  const isStudentEstadoSection = selectedSectionKey === 'actualizacion_estudiantes'
  const estadoInlineField = selectedSection?.editable_fields?.find((field) => field.name === 'Estado')
  const docenteEstadoOptions = useMemo(
    () =>
      (estadoInlineField?.options || []).filter((option) =>
        ['A', 'P'].includes(String(option.value).trim().toUpperCase()),
      ),
    [estadoInlineField],
  )
  const estadoPeriodField = selectedSection?.list_fields?.find((field) => field.name === 'codigo_periodo')
  const tableFields = isEstadoInlineSection ? listFields.filter((field) => field.name !== 'estado_nombre') : listFields
  const hasIndexColumn = !isEstadoInlineSection
  const tableColSpan = tableFields.length + 1 + (hasIndexColumn ? 1 : 0) + (isEstadoInlineSection ? 1 : 0) + (isDocenteEstadoSection ? 1 : 0)
  const isMateriaHomoTextSection = selectedSection?.key === 'materia_homo_textof'
  const homoMateriaOptions = useMemo(
    (): OptionItem[] => uniqueOptionsByValue(selectedSection?.create_fields?.find((field) => field.name === 'cod_materia')?.options || []),
    [selectedSection],
  )
  const homoPeriodoOptions = useMemo(
    (): OptionItem[] => selectedSection?.create_fields?.find((field) => field.name === 'cod_periodo')?.options || [],
    [selectedSection],
  )
  const homoTextofecha = useMemo(
    () => formatSpanishDateRange(homoBulkFechaInicio, homoBulkFechaFin),
    [homoBulkFechaFin, homoBulkFechaInicio],
  )
  const filteredHomoMateriaOptions = useMemo(() => {
    const needle = homoBulkSearch.trim().toLowerCase()
    if (!needle) return homoMateriaOptions
    return homoMateriaOptions.filter((option) =>
      `${option.value} ${option.label}`.toLowerCase().includes(needle),
    )
  }, [homoBulkSearch, homoMateriaOptions])
  const selectedHomoMateriaOptions = useMemo(
    () =>
      homoBulkMateriaCodes.map((code) => ({
        code,
        option: homoMateriaOptions.find((option) => String(option.value) === code),
      })),
    [homoBulkMateriaCodes, homoMateriaOptions],
  )
  const homoSearchResults = useMemo(
    () => (homoBulkSearch.trim() ? filteredHomoMateriaOptions.slice(0, 30) : []),
    [filteredHomoMateriaOptions, homoBulkSearch],
  )
  const homoMateriaGroups = useMemo((): HomoMateriaGroup[] => {
    const groups = new Map<string, HomoMateriaGroup>()
    for (const option of homoMateriaOptions) {
      const code = String(option.value)
      const name = materiaNameFromOption(option.label) || option.label || code
      const key = normalizeSearchText(name)
      const current = groups.get(key) || { key, name, codes: [], labels: [] }
      if (!current.codes.includes(code)) {
        current.codes.push(code)
        current.labels.push(option.label)
      }
      groups.set(key, current)
    }
    return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name))
  }, [homoMateriaOptions])
  const filteredHomoMateriaGroups = useMemo(() => {
    const needle = normalizeSearchText(homoMateriaNameSearch)
    const source = needle
      ? homoMateriaGroups.filter((group) =>
          normalizeSearchText(`${group.name} ${group.codes.join(' ')} ${group.labels.join(' ')}`).includes(needle),
        )
      : homoMateriaGroups
    return source.slice(0, 80)
  }, [homoMateriaGroups, homoMateriaNameSearch])
  const selectedHomoMateriaGroupCount = useMemo(
    () => homoMateriaGroups.filter((group) => group.codes.some((code) => homoBulkMateriaCodes.includes(code))).length,
    [homoBulkMateriaCodes, homoMateriaGroups],
  )
  const visibleRows = useMemo(() => {
    const needle = tableFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      listFields.some((field) => displayValue(field, row[field.name]).toLowerCase().includes(needle)),
    )
  }, [listFields, rows, tableFilter])

  function processKeyForSection(sectionKey: string) {
    return processShortcuts.find((process) => process.sections.includes(sectionKey))?.key || processShortcuts[0]?.key || ''
  }

  async function loadRows(sectionKey = selectedSectionKey, nextQuery = query, nextPeriodo = estadoPeriodFilter) {
    if (!sectionKey) return
    setError('')
    setMessage('')
    setListLoading(true)
    try {
      const payload = await fetchSisAcademicoRows(sectionKey, nextQuery.trim(), {
        periodo: sectionKey === 'actualizacion_estudiantes' ? nextPeriodo : '',
      })
      setRows(payload.rows || [])
      setInlineEstadoValues({})
      setSelectedRecordKey('')
      setFormValues({})
      setMode('edit')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar la seccion')
      setRows([])
    } finally {
      setListLoading(false)
    }
  }

  async function openRecord(sectionKey: string, nextRecordKey: string) {
    if (!nextRecordKey) return
    setError('')
    setMessage('')
    setDetailLoading(true)
    setMode('edit')
    try {
      const payload = await fetchSisAcademicoRecord(sectionKey, nextRecordKey)
      setSelectedRecordKey(nextRecordKey)
      setFormValues(payload.record || {})
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el registro')
      setSelectedRecordKey('')
      setFormValues({})
    } finally {
      setDetailLoading(false)
    }
  }

  async function saveRecord() {
    if (!selectedSection) return
    setError('')
    setMessage('')
    setSaving(true)
    try {
      const payload =
        mode === 'create'
          ? await createSisAcademicoRecord(selectedSection.key, formValues)
          : await updateSisAcademicoRecord(selectedSection.key, selectedRecordKey, formValues)
      setMessage(payload.message || 'Cambios guardados')
      await loadRows(selectedSection.key)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar')
    } finally {
      setSaving(false)
    }
  }

  function inlineEstadoValue(row: SisAcademicoRow, fieldName: 'Estado' | 'Informacion') {
    const key = recordKey(row)
    const localValue = inlineEstadoValues[key]?.[fieldName]
    if (localValue !== undefined) return localValue
    return inputValue(row[fieldName])
  }

  function updateInlineEstado(row: SisAcademicoRow, values: { Estado?: string; Informacion?: string }) {
    const key = recordKey(row)
    setInlineEstadoValues((current) => ({
      ...current,
      [key]: {
        Estado: current[key]?.Estado ?? inputValue(row.Estado),
        Informacion: current[key]?.Informacion ?? inputValue(row.Informacion),
        ...values,
      },
    }))
  }

  async function saveInlineEstado(row: SisAcademicoRow) {
    if (!selectedSection || !isEstadoInlineSection) return
    const key = recordKey(row)
    const estado = inlineEstadoValue(row, 'Estado').trim()
    const informacion = inlineEstadoValue(row, 'Informacion').trim()
    if (!estado) {
      setError('Selecciona un estado antes de guardar.')
      return
    }
    setError('')
    setMessage('')
    setInlineSavingKey(key)
    try {
      const payload = await updateSisAcademicoRecord(selectedSection.key, key, {
        Estado: estado,
        Informacion: informacion,
      })
      setMessage(payload.message || 'Estado actualizado')
      await loadRows(selectedSection.key)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar el estado')
    } finally {
      setInlineSavingKey('')
    }
  }

  function startCreate() {
    if (!selectedSection) return
    setMode('create')
    setSelectedRecordKey('')
    setFormValues(emptyValues(createFields))
    setMessage('')
    setError('')
  }

  function openSection(sectionKey: string, processKey?: string) {
    setSelectedSectionKey(sectionKey)
    setSelectedProcessKey(processKey || processKeyForSection(sectionKey))
    setQuery('')
    setEstadoPeriodFilter('')
    setTableFilter('')
    setSelectedRecordKey('')
    setFormValues({})
    setMode('edit')
    void loadRows(sectionKey, '', '')
  }

  function toggleHomoMateria(code: string) {
    setHomoBulkMateriaCodes((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    )
  }

  function selectVisibleHomoMaterias() {
    const visibleCodes = filteredHomoMateriaOptions.map((option) => String(option.value))
    setHomoBulkMateriaCodes((current) => Array.from(new Set([...current, ...visibleCodes])))
  }

  function toggleHomoMateriaGroup(group: HomoMateriaGroup) {
    const allSelected = group.codes.every((code) => homoBulkMateriaCodes.includes(code))
    setHomoBulkMateriaCodes((current) => {
      const next = new Set(current)
      if (allSelected) {
        group.codes.forEach((code) => next.delete(code))
      } else {
        group.codes.forEach((code) => next.add(code))
      }
      return Array.from(next)
    })
    setHomoBulkSearch('')
    setError('')
    setMessage(
      allSelected
        ? `${group.name}: materia retirada de la seleccion.`
        : `${group.name}: ${group.codes.length} codigo(s) relacionados agregados.`,
    )
  }

  function clearHomoMaterias() {
    setHomoBulkMateriaCodes([])
  }

  async function saveHomoBulk() {
    if (!selectedSection || selectedSection.key !== 'materia_homo_textof') return
    setError('')
    setMessage('')

    if (!homoBulkPeriodo) {
      setError('Selecciona el periodo HOMO correspondiente.')
      return
    }
    if (!homoTextofecha) {
      setError('Selecciona fecha de inicio y fecha de fin para generar el texto de fecha.')
      return
    }
    if (homoBulkMateriaCodes.length === 0) {
      setError('Selecciona al menos una materia para guardar.')
      return
    }

    setHomoBulkSaving(true)
    try {
      let created = 0
      let updated = 0
      const uniqueCodes = Array.from(new Set(homoBulkMateriaCodes))
      for (const code of uniqueCodes) {
        const option = homoMateriaOptions.find((item) => item.value === code)
        const result = await createSisAcademicoRecord(selectedSection.key, {
          cod_materia: code,
          cod_periodo: Number(homoBulkPeriodo),
          materia: materiaNameFromOption(option?.label) || code,
          textofecha: homoTextofecha,
          url: homoBulkUrl.trim(),
        })
        if (result.action === 'updated') {
          updated += 1
        } else {
          created += 1
        }
      }
      setHomoBulkMateriaCodes([])
      await loadRows(selectedSection.key)
      setMessage(`Textos HOMO procesados: ${uniqueCodes.length}. Nuevos: ${created}. Actualizados: ${updated}.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar la seleccion HOMO')
    } finally {
      setHomoBulkSaving(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      try {
        const payload = await fetchSisAcademicoCatalog()
        if (cancelled) return
        const nextSections = payload.sections || []
        setSections(nextSections)
        const requestedSection = nextSections.find((section) => section.key === initialSectionKey)?.key || ''
        const firstSection = requestedSection || nextSections[0]?.key || ''
        setSelectedSectionKey(firstSection)
        if (firstSection) {
          setSelectedProcessKey(processKeyForSection(firstSection))
        }
        if (firstSection) {
          const rowsPayload = await fetchSisAcademicoRows(firstSection, '')
          if (!cancelled) setRows(rowsPayload.rows || [])
        }
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar Gestion SisAcademico')
        }
      } finally {
        if (!cancelled) {
          setCatalogLoading(false)
        }
      }
    }

    void loadCatalog()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!initialSectionKey || initialSectionKey === appliedInitialSection) return
    const exists = sections.some((section) => section.key === initialSectionKey)
    if (!exists) return
    setAppliedInitialSection(initialSectionKey)
    openSection(initialSectionKey)
  }, [appliedInitialSection, initialSectionKey, sections])

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Operativo</p>
          <h1>Gestion por procesos</h1>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Modulos editables</span>
            </div>
          </div>
        </div>
      </header>

      <section className="gestion-sis-workflow" aria-label="Ruta operativa actual">
        <div className="gestion-sis-workflow__route">
          <span>Modulo actual</span>
          <strong>{selectedSection?.title || 'Selecciona una opcion del menu'}</strong>
        </div>
        <div className="gestion-sis-workflow__meta">
          <span>{selectedProcess?.title || selectedSection?.category || 'Gestion operativa'}</span>
          <span>{selectedSection?.table || 'Sin tabla'}</span>
          <span>{rows.length} registros</span>
          <span>{canCreate ? 'Permite crear' : 'Solo edicion'}</span>
        </div>
      </section>

      <section className="student-grid student-grid--content gestion-sis-grid gestion-sis-grid--single">
        <article className="student-card student-card--wide gestion-sis-list">
          <div className="card-head">
            <h3>{selectedSection?.title || 'Selecciona un modulo'}</h3>
            <span>{catalogLoading ? 'Cargando...' : selectedSection?.category || 'Modulo'}</span>
          </div>

          {isMateriaHomoTextSection ? (
            <div className="gestion-sis-homo-bulk">
              <div className="gestion-sis-homo-bulk__head">
                <div>
                  <strong>Ingreso masivo de textos HOMO</strong>
                  <span>Selecciona periodo, rango de fechas y todas las materias necesarias antes de guardar.</span>
                </div>
                <em>{homoBulkMateriaCodes.length} materia(s) seleccionada(s)</em>
              </div>

              <div className="matricula-acad-form gestion-sis-homo-bulk__form">
                <label>
                  <span>Periodo HOMO</span>
                  <select value={homoBulkPeriodo} onChange={(event) => setHomoBulkPeriodo(event.target.value)}>
                    <option value="">Seleccione periodo</option>
                    {homoPeriodoOptions.map((option) => (
                      <option key={`homo-periodo-${option.value}`} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Fecha inicio</span>
                  <input
                    type="date"
                    value={homoBulkFechaInicio}
                    onChange={(event) => setHomoBulkFechaInicio(event.target.value)}
                  />
                </label>
                <label>
                  <span>Fecha fin</span>
                  <input
                    type="date"
                    value={homoBulkFechaFin}
                    onChange={(event) => setHomoBulkFechaFin(event.target.value)}
                  />
                </label>
                <label>
                  <span>URL opcional</span>
                  <input value={homoBulkUrl} onChange={(event) => setHomoBulkUrl(event.target.value)} placeholder="Enlace o ruta del documento" />
                </label>
                <label className="gestion-sis-field--wide">
                  <span>Texto fecha generado</span>
                  <input value={homoTextofecha || '20 de mayo del 2024 al 16 de junio del 2024'} readOnly />
                </label>
                <div className="gestion-sis-homo-picker gestion-sis-field--wide">
                  <span>Codigo materia</span>
                  <div>
                    <strong>
                      {selectedHomoMateriaOptions.length > 0
                        ? `${selectedHomoMateriaOptions.length} codigo(s) de materia seleccionados`
                        : 'Sin materia seleccionada'}
                    </strong>
                    <button type="button" className="primary-action" onClick={() => setHomoMateriaSelectorOpen(true)}>
                      Seleccione la materia
                    </button>
                  </div>
                  <small>
                    Busca por nombre de materia. Al seleccionar se agregan todos los codigos relacionados para las carreras donde exista.
                  </small>
                </div>
                <label className="gestion-sis-field--wide">
                  <span>Busqueda manual por codigo unico</span>
                  <input
                    value={homoBulkSearch}
                    onChange={(event) => setHomoBulkSearch(event.target.value)}
                    placeholder="Opcional: buscar por codigo unico, codigo interno o nombre"
                  />
                </label>
              </div>

              <div className="gestion-sis-homo-bulk__finder">
                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Resultados de busqueda</strong>
                  <span>{homoSearchResults.length} resultado(s) visibles</span>
                </div>
                {homoSearchResults.length > 0 ? (
                  <div className="gestion-sis-homo-bulk__results">
                    {homoSearchResults.map((option) => {
                      const code = String(option.value)
                      const active = homoBulkMateriaCodes.includes(code)
                      return (
                        <button
                          key={`homo-result-${code}`}
                          type="button"
                          className={`gestion-sis-homo-bulk__result${active ? ' gestion-sis-homo-bulk__result--active' : ''}`}
                          onClick={() => toggleHomoMateria(code)}
                        >
                          <span>
                            <strong>{materiaNameFromOption(option.label) || option.label}</strong>
                            <small>Codigo unico: {code}</small>
                          </span>
                          <em>{active ? 'Seleccionada' : 'Agregar'}</em>
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <p className="gestion-sis-homo-bulk__empty">
                    {homoBulkSearch.trim() ? 'No hay materias con ese criterio.' : 'Escribe un codigo o nombre para seleccionar materias.'}
                  </p>
                )}
              </div>

              <div className="gestion-sis-homo-bulk__toolbar">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={selectVisibleHomoMaterias}
                  disabled={!homoBulkSearch.trim() || filteredHomoMateriaOptions.length === 0}
                >
                  Seleccionar todo filtrado
                </button>
                <button type="button" className="ghost-button" onClick={clearHomoMaterias} disabled={homoBulkMateriaCodes.length === 0}>
                  Limpiar seleccion
                </button>
                <button
                  type="button"
                  className="primary-action"
                  onClick={() => void saveHomoBulk()}
                  disabled={homoBulkSaving || homoBulkMateriaCodes.length === 0}
                >
                  {homoBulkSaving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>

              <div className="gestion-sis-homo-bulk__materias">
                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Materias seleccionadas</strong>
                  <span>{selectedHomoMateriaOptions.length} materia(s) para guardar</span>
                </div>
                {selectedHomoMateriaOptions.length > 0 ? (
                  <div className="gestion-sis-homo-bulk__selected-list">
                    {selectedHomoMateriaOptions.map(({ code, option }) => {
                      const label = option?.label || code
                    return (
                      <button
                        key={`homo-selected-${code}`}
                        type="button"
                        className="gestion-sis-homo-bulk__selected"
                        onClick={() => toggleHomoMateria(code)}
                      >
                        <span>
                          <strong>{materiaNameFromOption(label) || label}</strong>
                          <small>{code}</small>
                        </span>
                        <em>Quitar</em>
                      </button>
                    )
                    })}
                  </div>
                ) : (
                  <p className="gestion-sis-homo-bulk__empty">Todavia no hay materias seleccionadas.</p>
                )}
              </div>
            </div>
          ) : null}

          {homoMateriaSelectorOpen ? (
            <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="homo-materia-selector-title">
              <article className="matricula-modal gestion-sis-homo-selector-modal">
                <div className="matricula-modal-head">
                  <div className="matricula-modal-title">
                    <span>Materia HOMO</span>
                    <h3 id="homo-materia-selector-title">Seleccione la materia</h3>
                  </div>
                  <button type="button" className="matricula-modal-close" onClick={() => setHomoMateriaSelectorOpen(false)}>
                    Cerrar
                  </button>
                </div>

                <div className="matricula-acad-form gestion-sis-homo-selector-search">
                  <label>
                    <span>Buscar por nombre de materia</span>
                    <input
                      value={homoMateriaNameSearch}
                      onChange={(event) => setHomoMateriaNameSearch(event.target.value)}
                      placeholder="Ejemplo: Base de Datos, Programacion, Seguridad"
                      autoFocus
                    />
                  </label>
                </div>

                <div className="gestion-sis-homo-bulk__finder-head">
                  <strong>Materias encontradas</strong>
                  <span>{filteredHomoMateriaGroups.length} materia(s)</span>
                </div>

                <div className="gestion-sis-homo-name-list">
                  {filteredHomoMateriaGroups.length > 0 ? (
                    filteredHomoMateriaGroups.map((group) => {
                      const selectedCount = group.codes.filter((code) => homoBulkMateriaCodes.includes(code)).length
                      const allSelected = selectedCount === group.codes.length
                      return (
                        <button
                          key={`homo-group-${group.key}`}
                          type="button"
                          className={`gestion-sis-homo-name-option${selectedCount > 0 ? ' gestion-sis-homo-name-option--active' : ''}`}
                          aria-pressed={selectedCount > 0}
                          onClick={() => toggleHomoMateriaGroup(group)}
                        >
                          <span>
                            <strong>{group.name}</strong>
                            <small>{group.codes.length} codigo(s) relacionados: {group.codes.join(', ')}</small>
                          </span>
                          <em>
                            {allSelected
                              ? 'Seleccionada'
                              : selectedCount > 0
                                ? `${selectedCount}/${group.codes.length} agregado(s)`
                                : 'Seleccionar materia'}
                          </em>
                        </button>
                      )
                    })
                  ) : (
                    <p className="gestion-sis-homo-bulk__empty">No hay materias con ese nombre.</p>
                  )}
                </div>

                <div className="gestion-sis-homo-selector-footer">
                  <span>
                    {selectedHomoMateriaGroupCount} materia(s), {homoBulkMateriaCodes.length} codigo(s) seleccionados
                  </span>
                  <div>
                    <button type="button" className="ghost-button" onClick={clearHomoMaterias} disabled={homoBulkMateriaCodes.length === 0}>
                      Limpiar seleccion
                    </button>
                    <button type="button" className="primary-action" onClick={() => setHomoMateriaSelectorOpen(false)}>
                      Listo
                    </button>
                  </div>
                </div>
              </article>
            </div>
          ) : null}

          <div className="matricula-acad-form gestion-sis-filters">
            <label>
              <span>{isEstadoInlineSection ? 'Buscar nombre o correo' : 'Buscar'}</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={isEstadoInlineSection ? 'Nombre, correo, cedula o codigo' : 'Codigo, cedula, nombre o correo'}
              />
            </label>
            {isStudentEstadoSection ? (
              <label>
                <span>Período</span>
                <select value={estadoPeriodFilter} onChange={(event) => setEstadoPeriodFilter(event.target.value)}>
                  <option value="">-- Todos --</option>
                  {(estadoPeriodField?.options || []).map((option) => (
                    <option key={`estado-periodo-${option.value}`} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void loadRows()} disabled={!selectedSection || listLoading}>
              {listLoading ? 'Consultando...' : isEstadoInlineSection ? 'Filtrar' : 'Consultar'}
            </button>
            {canCreate ? (
              <button type="button" onClick={startCreate} disabled={!selectedSection}>
                Nuevo
              </button>
            ) : null}
          </div>

          <div className="excel-toolbar gestion-sis-excel-toolbar">
            {!isEstadoInlineSection ? (
              <label>
                <span>Filtrar tabla</span>
                <input
                  value={tableFilter}
                  onChange={(event) => setTableFilter(event.target.value)}
                  placeholder="Buscar solo en los datos mostrados"
                />
              </label>
            ) : null}
            <div>
              <strong>{visibleRows.length}</strong>
              <span>de {rows.length} registro(s)</span>
            </div>
            <small>{isEstadoInlineSection ? 'Edita estado y descripción directamente en la fila.' : 'Doble clic en una fila para editar'}</small>
          </div>

          {message ? <p className="teams-message">{message}</p> : null}
          {error ? <p className="teams-error">{error}</p> : null}

          <div className="matricula-table-wrap gestion-sis-table-wrap excel-table-wrap">
            <table className="matricula-table gestion-sis-table">
              <thead>
                <tr>
                  {hasIndexColumn ? <th>#</th> : null}
                  {tableFields.map((field) => (
                    <Fragment key={field.name}>
                      <th>{field.label}</th>
                      {isEstadoInlineSection && field.name === 'Estado' ? <th>Descripción</th> : null}
                    </Fragment>
                  ))}
                  <th>{isEstadoInlineSection ? 'Guardar' : 'Editar'}</th>
                  {isDocenteEstadoSection ? <th>Observar</th> : null}
                </tr>
              </thead>
              <tbody>
                {visibleRows.length > 0 ? (
                  visibleRows.map((row, rowIndex) => (
                    <tr
                      key={recordKey(row)}
                      className={selectedRecordKey === recordKey(row) ? 'excel-row--active' : ''}
                      onDoubleClick={isEstadoInlineSection ? undefined : () => void openRecord(selectedSectionKey, recordKey(row))}
                    >
                      {hasIndexColumn ? <td>{rowIndex + 1}</td> : null}
                      {tableFields.map((field) => {
                        if (isEstadoInlineSection && field.name === 'Estado') {
                          const options = isDocenteEstadoSection
                            ? docenteEstadoOptions
                            : estadoInlineField
                              ? fieldOptions(estadoInlineField, row.Estado)
                              : []
                          const estadoValue = inlineEstadoValue(row, 'Estado')
                          const selectValue = isDocenteEstadoSection && !['A', 'P'].includes(estadoValue.trim().toUpperCase())
                            ? ''
                            : estadoValue
                          return (
                            <Fragment key={`${recordKey(row)}-${field.name}`}>
                              <td>
                                <select
                                  className="gestion-sis-inline-select"
                                  value={selectValue}
                                  onChange={(event) => updateInlineEstado(row, { Estado: event.target.value })}
                                >
                                  <option value="">Seleccione estado</option>
                                  {options.map((option) => (
                                    <option key={`${recordKey(row)}-estado-${option.value}`} value={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </td>
                              <td>
                                <input
                                  className="gestion-sis-inline-input"
                                  value={inlineEstadoValue(row, 'Informacion')}
                                  onChange={(event) => updateInlineEstado(row, { Informacion: event.target.value })}
                                  placeholder="Descripción u observación"
                                />
                              </td>
                            </Fragment>
                          )
                        }
                        return <td key={`${recordKey(row)}-${field.name}`}>{displayValue(field, row[field.name])}</td>
                      })}
                      <td>
                        {isEstadoInlineSection ? (
                          <button
                            type="button"
                            className="reporteria-row-action"
                            onClick={() => void saveInlineEstado(row)}
                            disabled={inlineSavingKey === recordKey(row)}
                          >
                            {inlineSavingKey === recordKey(row) ? 'Guardando...' : 'Guardar'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="reporteria-row-action"
                            onClick={() => void openRecord(selectedSectionKey, recordKey(row))}
                          >
                            Abrir
                          </button>
                        )}
                      </td>
                      {isDocenteEstadoSection ? (
                        <td>
                          <button
                            type="button"
                            className="reporteria-row-action"
                            onClick={() => void openRecord(selectedSectionKey, recordKey(row))}
                          >
                            Observar
                          </button>
                        </td>
                      ) : null}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={tableColSpan}>{listLoading ? 'Consultando...' : 'Sin registros para mostrar.'}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {(mode === 'create' || selectedRecordKey) && selectedSection ? (
        <div className="matricula-modal-overlay">
          <article className="matricula-modal gestion-sis-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <h3>
                  {isDocenteEstadoSection && mode !== 'create'
                    ? `Observar: ${formValues.apellidos_nombre || selectedSection.title}`
                    : mode === 'create'
                      ? `Nuevo registro: ${selectedSection.title}`
                      : `Editar: ${selectedSection.title}`}
                </h3>
                <span>{detailLoading ? 'Cargando registro...' : selectedSection.table}</span>
              </div>
              <button
                type="button"
                className="matricula-modal-close"
                onClick={() => {
                  setSelectedRecordKey('')
                  setFormValues({})
                  setMode('edit')
                }}
              >
                Cerrar
              </button>
            </div>

            {isDocenteEstadoSection && mode !== 'create' ? (
              <>
                <div className="gestion-sis-observe-grid">
                  {(selectedSection.detail_fields || []).map((field) => (
                    <article key={field.name}>
                      <span>{field.label}</span>
                      <strong>{displayValue(field, formValues[field.name]) || '-'}</strong>
                    </article>
                  ))}
                </div>

                <div className="gestion-sis-observe-edit">
                  <div className="gestion-sis-form-helper">
                    <strong>Modificar estado del docente</strong>
                    <span>Actualiza el estado y la descripción del usuario vinculado sin salir de esta subpantalla.</span>
                  </div>
                  <div className="matricula-acad-form gestion-sis-edit-form">
                    <label>
                      <span>Estado docente *</span>
                      <select
                        value={
                          ['A', 'P'].includes(inputValue(formValues.Estado).trim().toUpperCase())
                            ? inputValue(formValues.Estado)
                            : ''
                        }
                        onChange={(event) =>
                          setFormValues((current) => ({
                            ...current,
                            Estado: event.target.value,
                          }))
                        }
                      >
                        <option value="">Seleccione estado</option>
                        {docenteEstadoOptions.map((option) => (
                          <option key={`modal-docente-estado-${option.value}`} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="gestion-sis-field--wide">
                      <span>Descripción</span>
                      <textarea
                        value={inputValue(formValues.Informacion)}
                        onChange={(event) =>
                          setFormValues((current) => ({
                            ...current,
                            Informacion: event.target.value,
                          }))
                        }
                        placeholder="Descripción u observación"
                      />
                    </label>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="gestion-sis-form-helper">
                  <strong>{mode === 'create' ? 'Nuevo registro' : 'Edicion del registro'}</strong>
                  <span>Completa los campos requeridos y guarda los cambios para actualizar la tabla.</span>
                </div>

                <div className="matricula-acad-form gestion-sis-edit-form">
                  {currentFields.map((field) => {
                    const options = fieldOptions(field, formValues[field.name])
                    return (
                      <label key={field.name} className={field.type === 'textarea' ? 'gestion-sis-field--wide' : ''}>
                        <span>
                          {field.label}
                          {field.required ? ' *' : ''}
                        </span>
                        {options.length > 0 ? (
                          <select
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                                ...(selectedSection.key === 'materia_homo_textof' && field.name === 'cod_materia'
                                  ? {
                                      materia: materiaNameFromOption(
                                        options.find((option) => String(option.value) === event.target.value)?.label,
                                      ) || current.materia,
                                    }
                                  : {}),
                              }))
                            }
                          >
                            {field.required ? null : <option value="">Sin asignar</option>}
                            {options.map((option) => (
                              <option key={`${field.name}-${option.value}`} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : field.type === 'textarea' ? (
                          <textarea
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                              }))
                            }
                          />
                        ) : field.type === 'bool' ? (
                          <select
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value === 'true'),
                              }))
                            }
                          >
                            <option value="true">Si</option>
                            <option value="false">No</option>
                          </select>
                        ) : (
                          <input
                            type={field.type === 'date' ? 'date' : field.type === 'number' || field.type === 'decimal' ? 'number' : 'text'}
                            step={field.type === 'decimal' ? '0.01' : undefined}
                            value={inputValue(formValues[field.name])}
                            onChange={(event) =>
                              setFormValues((current) => ({
                                ...current,
                                [field.name]: coerceFieldValue(field, event.target.value),
                              }))
                            }
                          />
                        )}
                      </label>
                    )
                  })}
                </div>
              </>
            )}

            <div className="teams-actions gestion-sis-modal-actions">
              <button type="button" onClick={() => void saveRecord()} disabled={saving || detailLoading}>
                {saving ? 'Guardando...' : isDocenteEstadoSection && mode !== 'create' ? 'Guardar estado' : 'Guardar cambios'}
              </button>
            </div>
          </article>
        </div>
      ) : null}
    </>
  )
}
