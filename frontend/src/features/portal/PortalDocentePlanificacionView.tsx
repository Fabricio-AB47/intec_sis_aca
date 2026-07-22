import { useEffect, useMemo, useState } from 'react'

import { ApiError, downloadPortalAcademicPlanningPdf, fetchPortalTeacherCourses, previewPortalAcademicPlanningPdf, signPortalAcademicPlanningPdf } from '../../lib/api'
import type {
  PortalAcademicPlanningPayload,
  PortalAcademicPlanningTopic,
  PortalAcademicPlanningUnit,
  PortalTeacherCourse,
} from '../../types/app'

type Props = { displayName: string }
type Draft = Omit<PortalAcademicPlanningPayload, 'document_type' | 'codigo_periodos' | 'codigo_materia' | 'paralelo' | 'cod_anio_basica' | 'cod_jornada'>
type PlanningDocumentType = 'pea' | 'silabo'

const MISION_INTEC = 'Somos una institución de educación superior, enfocada en docencia de calidad, gestión transparente, investigación y vinculación, para formar profesionales con conducta ética y capacidad innovadora, en respuesta a las necesidades productivas del país.'
const PLANNING_MODULES = [
  'Datos generales', 'Propósito', 'Alineamiento', 'Contenidos',
  'Metodología', 'Evaluación', 'Bibliografía', 'Firma electrónica',
] as const
const PLANNING_DOCUMENTS: Array<{ value: PlanningDocumentType; label: string; description: string; format: string }> = [
  { value: 'pea', label: 'PEA', description: 'Programa de estudios de la asignatura', format: 'Formato vertical' },
  { value: 'silabo', label: 'Sílabo', description: 'Plan detallado de contenidos y actividades', format: 'Formato horizontal' },
]

function newTopic(week = 1): PortalAcademicPlanningTopic {
  return {
    tema: '', semana: week, horas_docencia: 3, horas_practica: 1, horas_autonomo: 2,
    actividad_docencia: '', actividad_practica: '', actividad_autonoma: '', evaluacion: '',
  }
}

function newUnit(index = 1): PortalAcademicPlanningUnit {
  return { nombre: `Unidad ${index}`, resultado_aprendizaje: '', temas: [newTopic(index)] }
}

function initialDraft(): Draft {
  return {
    nivel: '', unidad_curricular: '', campo_formacion: '', modalidad: 'Presencial / En línea',
    prerrequisitos: '', correquisitos: '', horario_clases: '', horario_tutorias: '', descripcion: '',
    objetivo_general: '', resultados_aprendizaje: '', mision_intec: MISION_INTEC, mision_escuela: '',
    mision_carrera: '', unidades: [newUnit(1)], estrategias_metodologicas: '', formacion_ciudadana: '',
    sostenibilidad: '', recursos_didacticos: '', evaluacion_tareas: 30, evaluacion_individual: 15,
    evaluacion_colaborativo: 15, evaluacion_acumulativa: 40, bibliografia_basica: '',
    bibliografia_complementaria: '', proyecto_tema: '', proyecto_tiempo: 'Un semestre',
    proyecto_objetivo: '', proyecto_contexto: '', version: '001', fecha_elaboracion: new Date().toISOString().slice(0, 10),
  }
}

function draftWithPensumData(course: PortalTeacherCourse, base: Draft): Draft {
  const semester = Number(course.semestre)
  return {
    ...base,
    nivel: Number.isFinite(semester) && semester > 0 ? `${semester}.º semestre` : '',
    unidad_curricular: course.unidad_curricular || '',
  }
}

function keyOf(course: PortalTeacherCourse) {
  return [course.codigo_periodos?.join(','), course.cod_anio_basica, course.codigo_materia, course.paralelo, course.cod_jornada].join('|')
}

function courseLabel(course: PortalTeacherCourse) {
  return `${course.nombre_materia || course.cod_materia || 'Materia'} · ${course.nombre_carrera || 'Carrera'} · ${course.detalle_periodos || course.detalle_periodo || 'Periodo'} · Paralelo ${course.paralelo || '-'}`
}

function planningStorageKey(course: PortalTeacherCourse) {
  return `portal.teacher.planning.${keyOf(course)}`
}

function safeName(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase() || 'asignatura'
}

export function PortalDocentePlanificacionView({ displayName }: Readonly<Props>) {
  const [courses, setCourses] = useState<PortalTeacherCourse[]>([])
  const [selectedKey, setSelectedKey] = useState('')
  const [draft, setDraft] = useState<Draft>(initialDraft)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState<'pea' | 'silabo' | null>(null)
  const [previewing, setPreviewing] = useState<'pea' | 'silabo' | null>(null)
  const [previewType, setPreviewType] = useState<'pea' | 'silabo' | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [activeModule, setActiveModule] = useState(0)
  const [selectedDocument, setSelectedDocument] = useState<PlanningDocumentType>('pea')
  const [signing, setSigning] = useState<'pea' | 'silabo' | null>(null)
  const [certificate, setCertificate] = useState<File | null>(null)
  const [certificatePassword, setCertificatePassword] = useState('')
  const [signatureReason, setSignatureReason] = useState('Planificación académica docente')
  const [signatureLocation, setSignatureLocation] = useState('Quito')
  const [signatureContact, setSignatureContact] = useState('')
  const [certificateInputKey, setCertificateInputKey] = useState(0)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const selectedCourse = useMemo(() => courses.find((course) => keyOf(course) === selectedKey) || null, [courses, selectedKey])
  const totalHours = useMemo(() => draft.unidades.reduce((total, unit) => total + unit.temas.reduce(
    (subtotal, topic) => subtotal + topic.horas_docencia + topic.horas_practica + topic.horas_autonomo, 0,
  ), 0), [draft.unidades])
  const evaluationTotal = draft.evaluacion_tareas + draft.evaluacion_individual + draft.evaluacion_colaborativo + draft.evaluacion_acumulativa
  const moduleCompletion = useMemo(() => [
    Boolean(selectedCourse && draft.nivel.trim() && draft.unidad_curricular.trim() && draft.modalidad.trim()),
    Boolean(draft.descripcion.trim() && draft.objetivo_general.trim() && draft.resultados_aprendizaje.trim()),
    Boolean(draft.mision_intec.trim() && draft.mision_escuela.trim() && draft.mision_carrera.trim()),
    draft.unidades.some((unit) => unit.nombre.trim() && unit.temas.some((topic) => topic.tema.trim())),
    Boolean(draft.estrategias_metodologicas.trim() && draft.recursos_didacticos.trim()),
    evaluationTotal === 100,
    Boolean(draft.bibliografia_basica.trim() && draft.proyecto_tema.trim()),
    certificate !== null,
  ], [certificate, draft, evaluationTotal, selectedCourse])
  const completedModules = moduleCompletion.filter(Boolean).length
  const completionPercent = Math.round((completedModules / PLANNING_MODULES.length) * 100)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const response = await fetchPortalTeacherCourses()
        const items = response.items || []
        setCourses(items)
        setSelectedKey(items[0] ? keyOf(items[0]) : '')
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : 'No se pudieron cargar las materias asignadas')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  useEffect(() => {
    if (!selectedCourse) return
    try {
      const saved = globalThis.localStorage.getItem(planningStorageKey(selectedCourse))
      const storedDraft = saved ? { ...initialDraft(), ...JSON.parse(saved) } : initialDraft()
      setDraft(draftWithPensumData(selectedCourse, storedDraft))
    } catch {
      setDraft(draftWithPensumData(selectedCourse, initialDraft()))
    }
    setMessage('')
    setError('')
    setActiveModule(0)
  }, [selectedCourse])

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const setField = <K extends keyof Draft>(field: K, value: Draft[K]) => setDraft((current) => ({ ...current, [field]: value }))

  const updateUnit = (unitIndex: number, patch: Partial<PortalAcademicPlanningUnit>) => {
    setDraft((current) => ({
      ...current,
      unidades: current.unidades.map((unit, index) => index === unitIndex ? { ...unit, ...patch } : unit),
    }))
  }

  const updateTopic = (unitIndex: number, topicIndex: number, patch: Partial<PortalAcademicPlanningTopic>) => {
    const unit = draft.unidades[unitIndex]
    updateUnit(unitIndex, { temas: unit.temas.map((topic, index) => index === topicIndex ? { ...topic, ...patch } : topic) })
  }

  const persistPlanning = () => {
    if (!selectedCourse) return
    globalThis.localStorage.setItem(planningStorageKey(selectedCourse), JSON.stringify(draft))
  }

  const buildPayload = (documentType: 'pea' | 'silabo', allowIncomplete = false): PortalAcademicPlanningPayload | null => {
    if (!selectedCourse) return null
    if (!allowIncomplete && evaluationTotal !== 100) {
      setError('Los porcentajes de evaluación deben sumar 100%.')
      return null
    }
    if (!allowIncomplete && !draft.unidades.some((unit) => unit.temas.some((topic) => topic.tema.trim()))) {
      setError('Registre al menos un tema de la asignatura.')
      return null
    }
    const periodCodes = (selectedCourse.codigo_periodos?.length ? selectedCourse.codigo_periodos : [selectedCourse.codigo_periodo])
      .map(Number).filter(Number.isFinite)
    return {
      ...draft,
      document_type: documentType,
      codigo_periodos: periodCodes,
      codigo_materia: selectedCourse.cod_materia || selectedCourse.codigo_materia || '',
      paralelo: selectedCourse.paralelo || '',
      cod_anio_basica: Number(selectedCourse.cod_anio_basica) || null,
      cod_jornada: selectedCourse.cod_jornada ?? null,
      unidades: draft.unidades.map((unit, index) => ({
        ...unit,
        nombre: unit.nombre.trim() || `Unidad ${index + 1}`,
        temas: unit.temas.filter((topic) => topic.tema.trim()),
      })),
    }
  }

  const closePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    setPreviewType(null)
  }

  const previewDocument = async (documentType: 'pea' | 'silabo') => {
    const payload = buildPayload(documentType, true)
    if (!payload) return
    setPreviewing(documentType)
    setError('')
    try {
      const blob = await previewPortalAcademicPlanningPdf(payload)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(URL.createObjectURL(blob))
      setPreviewType(documentType)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo preparar la vista previa')
    } finally {
      setPreviewing(null)
    }
  }

  const generate = async (documentType: 'pea' | 'silabo') => {
    const payload = buildPayload(documentType)
    if (!payload || !selectedCourse) return
    setGenerating(documentType)
    setError('')
    try {
      const blob = await downloadPortalAcademicPlanningPdf(payload)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${documentType}-${safeName(selectedCourse.nombre_materia || selectedCourse.cod_materia || 'asignatura')}.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
      persistPlanning()
      setMessage(`${documentType === 'pea' ? 'PEA' : 'Sílabo'} generado correctamente.`)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo generar el documento')
    } finally {
      setGenerating(null)
    }
  }

  const signDocument = async (documentType: 'pea' | 'silabo') => {
    const payload = buildPayload(documentType)
    if (!payload || !selectedCourse) return
    if (!certificate || !certificatePassword.trim()) {
      setError('Seleccione el archivo .p12 o .pfx e ingrese su contraseña.')
      return
    }
    setSigning(documentType)
    setError('')
    try {
      const blob = await signPortalAcademicPlanningPdf({
        payload,
        certificado: certificate,
        contrasenaCertificado: certificatePassword,
        firmaMotivo: signatureReason,
        firmaUbicacion: signatureLocation,
        firmaContacto: signatureContact,
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${documentType}-${safeName(selectedCourse.nombre_materia || selectedCourse.cod_materia || 'asignatura')}-firmado.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
      persistPlanning()
      setMessage(`${documentType === 'pea' ? 'PEA' : 'Sílabo'} firmado electrónicamente.`)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo firmar el documento')
    } finally {
      setCertificate(null)
      setCertificatePassword('')
      setCertificateInputKey((value) => value + 1)
      setSigning(null)
    }
  }

  return (
    <div className="student-dashboard portal-page planning-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Portal docente</p>
          <h1>Planificación académica</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Coordinador académico</span>
          <strong>Roberto Castro</strong>
          <small>Revisión institucional</small>
        </div>
      </header>

      <form className="planning-form" onSubmit={(event) => event.preventDefault()}>
        <section className="planning-section planning-section--course">
          <div className="section-title">
            <div><span>Asignatura</span><h2>Materia y documento</h2></div>
            <div className="planning-course-summary">
              <strong>{totalHours} horas planificadas</strong>
              <span>{completedModules} de {PLANNING_MODULES.length} puntos completos</span>
            </div>
          </div>
          <div className="planning-document-picker" role="radiogroup" aria-label="Documento que desea crear">
            {PLANNING_DOCUMENTS.map((document) => (
              <button
                type="button"
                role="radio"
                aria-checked={selectedDocument === document.value}
                className={selectedDocument === document.value ? 'planning-document-option planning-document-option--active' : 'planning-document-option'}
                key={document.value}
                onClick={() => setSelectedDocument(document.value)}
              >
                <span>{document.label}</span>
                <strong>{document.description}</strong>
                <small>{document.format}</small>
              </button>
            ))}
          </div>
          <label className="planning-course-select">
            <span>Materia asignada</span>
            <select value={selectedKey} onChange={(event) => setSelectedKey(event.target.value)} disabled={loading || courses.length === 0}>
              {courses.map((course) => <option key={keyOf(course)} value={keyOf(course)}>{courseLabel(course)}</option>)}
            </select>
          </label>
          <div className="planning-actions">
            <button type="button" className="ghost-button" onClick={() => void previewDocument(selectedDocument)} disabled={!selectedCourse || previewing !== null}>{previewing === selectedDocument ? 'Preparando...' : `Vista previa ${selectedDocument === 'pea' ? 'PEA' : 'Sílabo'}`}</button>
            <button type="button" className="primary-action" onClick={() => void generate(selectedDocument)} disabled={!selectedCourse || generating !== null}>{generating === selectedDocument ? 'Generando...' : `Generar ${selectedDocument === 'pea' ? 'PEA' : 'Sílabo'} PDF`}</button>
          </div>
          {message ? <p className="planning-message planning-message--ok">{message}</p> : null}
          {error ? <p className="planning-message planning-message--error">{error}</p> : null}
        </section>

        <nav className="planning-module-nav" aria-label="Módulos de planificación">
          {PLANNING_MODULES.map((module, index) => (
            <button
              type="button"
              key={module}
              className={`${activeModule === index ? 'planning-module-button planning-module-button--active' : 'planning-module-button'}${moduleCompletion[index] ? ' planning-module-button--complete' : ''}`}
              onClick={() => setActiveModule(index)}
            >
              <span className="planning-module-index">{index + 1}</span>
              <span className="planning-module-copy"><strong>{module}</strong><small>{moduleCompletion[index] ? 'Completo' : 'Pendiente'}</small></span>
            </button>
          ))}
        </nav>

        <div className="planning-progress" aria-label={`Avance del documento ${completionPercent}%`}>
          <div><span>Avance de contenido</span><strong>{completionPercent}%</strong></div>
          <progress max="100" value={completionPercent}>{completionPercent}%</progress>
        </div>

        <section className="planning-section" hidden={activeModule !== 0}>
          <div className="section-title"><div><span>Datos generales</span><h2>Información académica</h2></div></div>
          <div className="planning-fields planning-fields--four">
            <label><span>Nivel (semestre)</span><input value={draft.nivel || 'Sin semestre configurado'} readOnly aria-readonly="true" /></label>
            <label><span>Unidad curricular (PENSUM)</span><input value={draft.unidad_curricular || 'Sin unidad configurada'} readOnly aria-readonly="true" /></label>
            <label><span>Campo de formación</span><input value={draft.campo_formacion} onChange={(e) => setField('campo_formacion', e.target.value)} /></label>
            <label><span>Modalidad</span><input value={draft.modalidad} onChange={(e) => setField('modalidad', e.target.value)} /></label>
            <label><span>Prerrequisitos</span><input value={draft.prerrequisitos} onChange={(e) => setField('prerrequisitos', e.target.value)} /></label>
            <label><span>Correquisitos</span><input value={draft.correquisitos} onChange={(e) => setField('correquisitos', e.target.value)} /></label>
            <label><span>Horario de clases</span><input value={draft.horario_clases} onChange={(e) => setField('horario_clases', e.target.value)} /></label>
            <label><span>Horario de tutorías</span><input value={draft.horario_tutorias} onChange={(e) => setField('horario_tutorias', e.target.value)} /></label>
            <label><span>Versión</span><input value={draft.version} onChange={(e) => setField('version', e.target.value)} /></label>
            <label><span>Fecha de elaboración</span><input type="date" value={draft.fecha_elaboracion} onChange={(e) => setField('fecha_elaboracion', e.target.value)} /></label>
          </div>
        </section>

        <section className="planning-section" hidden={activeModule !== 1}>
          <div className="section-title"><div><span>Propósito</span><h2>Descripción y resultados</h2></div></div>
          <div className="planning-fields">
            <label><span>Descripción de la asignatura</span><textarea value={draft.descripcion} onChange={(e) => setField('descripcion', e.target.value)} /></label>
            <label><span>Objetivo general</span><textarea value={draft.objetivo_general} onChange={(e) => setField('objetivo_general', e.target.value)} /></label>
            <label className="planning-span-two"><span>Resultados de aprendizaje y aporte al perfil profesional</span><textarea value={draft.resultados_aprendizaje} onChange={(e) => setField('resultados_aprendizaje', e.target.value)} /></label>
          </div>
        </section>

        <section className="planning-section" hidden={activeModule !== 2}>
          <div className="section-title"><div><span>Alineamiento</span><h2>Misiones institucionales</h2></div></div>
          <div className="planning-fields planning-fields--three">
            <label><span>Misión INTEC</span><textarea value={draft.mision_intec} onChange={(e) => setField('mision_intec', e.target.value)} /></label>
            <label><span>Misión Escuela</span><textarea value={draft.mision_escuela} onChange={(e) => setField('mision_escuela', e.target.value)} /></label>
            <label><span>Misión Carrera</span><textarea value={draft.mision_carrera} onChange={(e) => setField('mision_carrera', e.target.value)} /></label>
          </div>
        </section>

        <section className="planning-section planning-section--units" hidden={activeModule !== 3}>
          <div className="section-title">
            <div><span>Contenidos</span><h2>Unidades y temas</h2></div>
            <button type="button" className="ghost-button" onClick={() => setField('unidades', [...draft.unidades, newUnit(draft.unidades.length + 1)])}>Agregar unidad</button>
          </div>
          {draft.unidades.map((unit, unitIndex) => (
            <div className="planning-unit" key={`unit-${unitIndex}`}>
              <div className="planning-unit-header">
                <strong>Unidad {unitIndex + 1}</strong>
                {draft.unidades.length > 1 ? <button type="button" className="text-button" onClick={() => setField('unidades', draft.unidades.filter((_, index) => index !== unitIndex))}>Eliminar unidad</button> : null}
              </div>
              <div className="planning-fields">
                <label><span>Nombre de la unidad</span><input value={unit.nombre} onChange={(e) => updateUnit(unitIndex, { nombre: e.target.value })} /></label>
                <label><span>Resultado de aprendizaje</span><textarea value={unit.resultado_aprendizaje} onChange={(e) => updateUnit(unitIndex, { resultado_aprendizaje: e.target.value })} /></label>
              </div>
              <div className="planning-topic-table-wrap">
                <table className="planning-topic-table">
                  <thead><tr><th>Tema</th><th>Semana</th><th>Doc.</th><th>Prác.</th><th>Aut.</th><th>Actividad docente</th><th>Actividad práctica</th><th>Trabajo autónomo</th><th>Evaluación</th><th>Acción</th></tr></thead>
                  <tbody>
                    {unit.temas.map((topic, topicIndex) => (
                      <tr key={`topic-${unitIndex}-${topicIndex}`}>
                        <td><textarea value={topic.tema} onChange={(e) => updateTopic(unitIndex, topicIndex, { tema: e.target.value })} /></td>
                        <td><input type="number" min="1" value={topic.semana} onChange={(e) => updateTopic(unitIndex, topicIndex, { semana: Number(e.target.value) })} /></td>
                        <td><input type="number" min="0" value={topic.horas_docencia} onChange={(e) => updateTopic(unitIndex, topicIndex, { horas_docencia: Number(e.target.value) })} /></td>
                        <td><input type="number" min="0" value={topic.horas_practica} onChange={(e) => updateTopic(unitIndex, topicIndex, { horas_practica: Number(e.target.value) })} /></td>
                        <td><input type="number" min="0" value={topic.horas_autonomo} onChange={(e) => updateTopic(unitIndex, topicIndex, { horas_autonomo: Number(e.target.value) })} /></td>
                        <td><textarea value={topic.actividad_docencia} onChange={(e) => updateTopic(unitIndex, topicIndex, { actividad_docencia: e.target.value })} /></td>
                        <td><textarea value={topic.actividad_practica} onChange={(e) => updateTopic(unitIndex, topicIndex, { actividad_practica: e.target.value })} /></td>
                        <td><textarea value={topic.actividad_autonoma} onChange={(e) => updateTopic(unitIndex, topicIndex, { actividad_autonoma: e.target.value })} /></td>
                        <td><textarea value={topic.evaluacion} onChange={(e) => updateTopic(unitIndex, topicIndex, { evaluacion: e.target.value })} /></td>
                        <td><button type="button" className="text-button" disabled={unit.temas.length === 1} onClick={() => updateUnit(unitIndex, { temas: unit.temas.filter((_, index) => index !== topicIndex) })}>Quitar</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" className="ghost-button" onClick={() => updateUnit(unitIndex, { temas: [...unit.temas, newTopic(unit.temas.length + 1)] })}>Agregar tema</button>
            </div>
          ))}
        </section>

        <section className="planning-section" hidden={activeModule !== 4}>
          <div className="section-title"><div><span>Aplicación</span><h2>Metodología, formación y recursos</h2></div></div>
          <div className="planning-fields planning-fields--three">
            <label><span>Estrategias metodológicas</span><textarea value={draft.estrategias_metodologicas} onChange={(e) => setField('estrategias_metodologicas', e.target.value)} /></label>
            <label><span>Formación ciudadana</span><textarea value={draft.formacion_ciudadana} onChange={(e) => setField('formacion_ciudadana', e.target.value)} /></label>
            <label><span>Educación ambiental y sostenibilidad</span><textarea value={draft.sostenibilidad} onChange={(e) => setField('sostenibilidad', e.target.value)} /></label>
            <label className="planning-span-three"><span>Recursos didácticos</span><textarea value={draft.recursos_didacticos} onChange={(e) => setField('recursos_didacticos', e.target.value)} /></label>
          </div>
        </section>

        <section className="planning-section" hidden={activeModule !== 5}>
          <div className="section-title"><div><span>Evaluación</span><h2>Distribución porcentual</h2></div><strong className={evaluationTotal === 100 ? 'planning-total-ok' : 'planning-total-error'}>{evaluationTotal}%</strong></div>
          <div className="planning-fields planning-fields--four">
            <label><span>Tareas</span><input type="number" min="0" max="100" value={draft.evaluacion_tareas} onChange={(e) => setField('evaluacion_tareas', Number(e.target.value))} /></label>
            <label><span>Trabajo individual</span><input type="number" min="0" max="100" value={draft.evaluacion_individual} onChange={(e) => setField('evaluacion_individual', Number(e.target.value))} /></label>
            <label><span>Trabajo colaborativo</span><input type="number" min="0" max="100" value={draft.evaluacion_colaborativo} onChange={(e) => setField('evaluacion_colaborativo', Number(e.target.value))} /></label>
            <label><span>Evaluación acumulativa</span><input type="number" min="0" max="100" value={draft.evaluacion_acumulativa} onChange={(e) => setField('evaluacion_acumulativa', Number(e.target.value))} /></label>
          </div>
        </section>

        <section className="planning-section" hidden={activeModule !== 6}>
          <div className="section-title"><div><span>Fuentes y proyecto</span><h2>Bibliografía y aplicación práctica</h2></div></div>
          <div className="planning-fields">
            <label><span>Bibliografía básica</span><textarea value={draft.bibliografia_basica} onChange={(e) => setField('bibliografia_basica', e.target.value)} /></label>
            <label><span>Bibliografía complementaria</span><textarea value={draft.bibliografia_complementaria} onChange={(e) => setField('bibliografia_complementaria', e.target.value)} /></label>
            <label><span>Tema del proyecto</span><input value={draft.proyecto_tema} onChange={(e) => setField('proyecto_tema', e.target.value)} /></label>
            <label><span>Tiempo</span><input value={draft.proyecto_tiempo} onChange={(e) => setField('proyecto_tiempo', e.target.value)} /></label>
            <label><span>Objetivo del proyecto</span><textarea value={draft.proyecto_objetivo} onChange={(e) => setField('proyecto_objetivo', e.target.value)} /></label>
            <label><span>Contexto de aplicación</span><textarea value={draft.proyecto_contexto} onChange={(e) => setField('proyecto_contexto', e.target.value)} /></label>
          </div>
        </section>

        <section className="planning-section planning-signature-section" hidden={activeModule !== 7}>
          <div className="section-title">
            <div><span>Firma electrónica</span><h2>Firmar en “Elaborado por”</h2></div>
            <strong>Roberto Castro · Coordinador Académico</strong>
          </div>
          <div className="planning-signer-card">
            <span>Docente responsable del documento</span>
            <strong>{displayName}</strong>
            <small>El certificado seleccionado debe pertenecer a este docente. Su nombre constará en la firma electrónica y en el bloque “Elaborado por”.</small>
          </div>
          <div className="planning-fields planning-fields--four">
            <label>
              <span>Certificado .p12 o .pfx</span>
              <input key={certificateInputKey} type="file" accept=".p12,.pfx,application/x-pkcs12" onChange={(event) => setCertificate(event.target.files?.[0] || null)} />
            </label>
            <label><span>Contraseña del certificado</span><input type="password" autoComplete="new-password" value={certificatePassword} onChange={(event) => setCertificatePassword(event.target.value)} /></label>
            <label><span>Motivo</span><input value={signatureReason} onChange={(event) => setSignatureReason(event.target.value)} /></label>
            <label><span>Ubicación</span><input value={signatureLocation} onChange={(event) => setSignatureLocation(event.target.value)} /></label>
            <label className="planning-span-two"><span>Contacto</span><input value={signatureContact} onChange={(event) => setSignatureContact(event.target.value)} placeholder="Correo institucional" /></label>
          </div>
          <div className="planning-signature-status">
            <span>{certificate ? certificate.name : 'Sin certificado seleccionado'}</span>
            <span>El archivo y la contraseña se descartan al terminar cada intento.</span>
          </div>
          <div className="planning-actions">
            <button type="button" className="primary-action" onClick={() => void signDocument(selectedDocument)} disabled={!selectedCourse || signing !== null || generating !== null}>{signing === selectedDocument ? 'Firmando...' : `Firmar ${selectedDocument === 'pea' ? 'PEA' : 'Sílabo'}`}</button>
          </div>
        </section>

        <footer className="planning-footer-actions">
          <button type="button" className="ghost-button" onClick={() => setActiveModule((current) => Math.max(0, current - 1))} disabled={activeModule === 0}>Anterior</button>
          <strong>Módulo {activeModule + 1} de {PLANNING_MODULES.length}</strong>
          <button type="button" className="ghost-button" onClick={() => setActiveModule((current) => Math.min(PLANNING_MODULES.length - 1, current + 1))} disabled={activeModule === PLANNING_MODULES.length - 1}>Siguiente</button>
          <button type="button" className="ghost-button" onClick={() => void previewDocument(selectedDocument)} disabled={!selectedCourse || previewing !== null}>Vista previa {selectedDocument === 'pea' ? 'PEA' : 'Sílabo'}</button>
          <button type="button" className="primary-action" onClick={() => void generate(selectedDocument)} disabled={!selectedCourse || generating !== null}>Generar {selectedDocument === 'pea' ? 'PEA' : 'Sílabo'}</button>
        </footer>
      </form>

      {previewUrl && previewType ? (
        <div className="portal-report-preview-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closePreview()
        }}>
          <section className="portal-report-preview-modal planning-preview-modal" role="dialog" aria-modal="true" aria-labelledby="planning-preview-title">
            <header>
              <div>
                <span>Vista previa</span>
                <h2 id="planning-preview-title">{previewType === 'pea' ? 'PEA' : 'Sílabo'} · {selectedCourse?.nombre_materia || selectedCourse?.cod_materia}</h2>
                <p>Documento elaborado por {displayName}</p>
              </div>
              <div className="portal-report-preview-actions">
                <button type="button" className="ghost-button" onClick={() => {
                  closePreview()
                  setActiveModule(7)
                }}>Ir a firma electrónica</button>
                <button type="button" className="primary-action" onClick={closePreview}>Cerrar</button>
              </div>
            </header>
            <iframe src={previewUrl} title={`Vista previa del ${previewType === 'pea' ? 'PEA' : 'Sílabo'}`} />
          </section>
        </div>
      ) : null}
    </div>
  )
}
