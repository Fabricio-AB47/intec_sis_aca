import { useEffect, useMemo, useState } from 'react'

import {
  createPracticasOperationsActivity,
  createPracticasOperationsAgreement,
  createPracticasOperationsEntity,
  createPracticasOperationsProject,
  downloadPracticasOperationsReport,
  fetchPracticasOperationsAudit,
  fetchPracticasOperationsCatalog,
  fetchPracticasOperationsDashboard,
  fetchPracticasOperationsDetail,
  fetchPracticasOperationsNotifications,
  fetchPracticasOperationsReconciliations,
  readPracticasOperationsNotification,
  reopenPracticasOperationsRecord,
  retryPracticasOperationsReconciliation,
  reviewPracticasOperationsActivity,
  reviewPracticasOperationsVinculationProduct,
  savePracticasOperationsActorEvaluation,
  savePracticasOperationsClosure,
  savePracticasOperationsConfiguration,
  savePracticasOperationsEvaluation,
  savePracticasOperationsIndicator,
  savePracticasOperationsPlan,
  savePracticasOperationsVinculationProduct,
  savePracticasOperationsVinculationResult,
} from '../../lib/api'
import type {
  PracticasOperationsAuditItem,
  PracticasOperationsCatalogResponse,
  PracticasOperationsDashboardItem,
  PracticasOperationsDashboardResponse,
  PracticasOperationsDetailResponse,
  PracticasOperationsNotification,
  PracticasOperationsReconciliation,
  PracticasProcessCode,
} from '../../types/app'

type Props = {
  process: PracticasProcessCode
  role: string
  mode?: 'seguimiento' | 'catalogos'
  onOpenDocuments: (identification: string) => void
}

type PlanForm = {
  entidad_id: string
  convenio_id: string
  proyecto_id: string
  tutor_externo_nombre: string
  tutor_externo_correo: string
  tutor_externo_telefono: string
  objetivo_general: string
  resultados_aprendizaje: string
  actividades_planificadas: string
  fecha_inicio: string
  fecha_fin: string
  horas_planificadas: string
}

const EMPTY_CATALOG: PracticasOperationsCatalogResponse = {
  entidades: [],
  convenios: [],
  proyectos: [],
  configuraciones: [],
  almacenamiento: {
    base_datos: 'INTEC_PRACTICAS_PREPROFESIONALES',
    esquema_operativo: 'ops',
    tabla_calificacion: 'ops.evaluacion_practica',
    fuente_academica: 'INTECBDD (solo lectura)',
  },
}

function textValue(value: unknown) {
  return value === null || value === undefined ? '' : String(value).trim()
}

function dateValue(value: unknown) {
  return textValue(value).slice(0, 10)
}

function todayValue() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Guayaquil',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function dateTimeLabel(value: unknown) {
  const raw = textValue(value)
  if (!raw) return 'Sin fecha'
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return new Intl.DateTimeFormat('es-EC', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function numberValue(value: string) {
  const numeric = Number(value.replace(',', '.'))
  return Number.isFinite(numeric) ? numeric : 0
}

function percentage(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0
  return Math.max(0, Math.min(100, numeric))
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function requirementClass(status: string) {
  if (status === 'COMPLETO') return 'is-complete'
  if (status === 'EN_REVISION') return 'is-review'
  return 'is-pending'
}

function semaphoreLabel(item: PracticasOperationsDashboardItem) {
  if (item.Semaforo === 'ROJO') return 'Requiere atención inmediata'
  if (item.Semaforo === 'AMARILLO') return 'Tiene actividades pendientes'
  return 'Proceso al día'
}

function enrollmentStatusLabel(value: unknown) {
  const status = textValue(value).toUpperCase()
  const labels: Record<string, string> = {
    INSCRITO: 'Inscrito',
    EN_PROCESO: 'En proceso',
    EN_REVISION: 'En revisión',
    CUMPLIDO: 'Cumplido',
    NO_CUMPLIDO: 'No cumplido',
    ANULADO: 'Anulado',
  }
  return labels[status] || 'Inscripción pendiente'
}

function evaluationStageLabel(value: unknown) {
  const status = textValue(value).toUpperCase()
  const labels: Record<string, string> = {
    PENDIENTE_REVISION: 'Pendiente de envío o corrección',
    EN_REVISION: 'En revisión',
    PENDIENTE_CALIFICACION: 'A la espera de calificación',
    CALIFICADA: 'Calificada',
  }
  return labels[status] || 'Pendiente de envío a revisión'
}

function evaluationResultLabel(value: unknown) {
  const result = textValue(value).toUpperCase()
  if (result === 'APROBADO') return 'Aprobado'
  if (result === 'REPROBADO') return 'Reprobado'
  return 'Pendiente'
}

function emptyPlan(hours: number): PlanForm {
  return {
    entidad_id: '',
    convenio_id: '',
    proyecto_id: '',
    tutor_externo_nombre: '',
    tutor_externo_correo: '',
    tutor_externo_telefono: '',
    objetivo_general: '',
    resultados_aprendizaje: '',
    actividades_planificadas: '',
    fecha_inicio: '',
    fecha_fin: '',
    horas_planificadas: String(hours),
  }
}

export function PracticasSeguimientoPanel({ process, role, mode = 'seguimiento', onOpenDocuments }: Readonly<Props>) {
  const normalizedRole = role.trim().toUpperCase()
  const isAdmin = !['ESTUDIANTE', 'DOCENTE'].includes(normalizedRole)
  const isStudent = normalizedRole === 'ESTUDIANTE'
  const canUploadDocuments = normalizedRole === 'DOCENTE'
  const canOpenDocuments = Boolean(normalizedRole)
  const catalogOnly = mode === 'catalogos'
  const [dashboard, setDashboard] = useState<PracticasOperationsDashboardResponse | null>(null)
  const [catalog, setCatalog] = useState<PracticasOperationsCatalogResponse>(EMPTY_CATALOG)
  const [notifications, setNotifications] = useState<PracticasOperationsNotification[]>([])
  const [reconciliations, setReconciliations] = useState<PracticasOperationsReconciliation[]>([])
  const [auditItems, setAuditItems] = useState<PracticasOperationsAuditItem[]>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<PracticasOperationsDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [planForm, setPlanForm] = useState<PlanForm>(() => emptyPlan(240))
  const [activityForm, setActivityForm] = useState({
    fecha_actividad: todayValue(),
    descripcion: '',
    horas: '',
    hora_inicio: '',
    hora_fin: '',
    descanso_minutos: '0',
    modalidad: 'PRESENCIAL',
    lugar: '',
    evidencia_url: '',
    evidencia_nombre: '',
  })
  const [reviewActivityId, setReviewActivityId] = useState<number | null>(null)
  const [reviewObservation, setReviewObservation] = useState('')
  const [indicatorForm, setIndicatorForm] = useState({
    indicador_id: '',
    nombre: '',
    unidad_medida: '',
    meta: '',
    resultado: '',
    evidencia_url: '',
    observacion: '',
  })
  const [closureForm, setClosureForm] = useState({
    supervision_realizada: false,
    evaluacion_entidad: '',
    informe_final_validado: false,
    acta_aceptacion_validada: false,
    certificado_emitido: false,
    observacion: '',
  })
  const [evaluationForm, setEvaluationForm] = useState({
    calificacion: '',
    observacion: '',
  })
  const [actorEvaluationForm, setActorEvaluationForm] = useState({
    rol_evaluador: process === 'PPF' ? 'DOCENTE_ACADEMICO' : 'DOCENTE_ACADEMICO',
    calificacion: '',
    evaluador_nombre: '',
    evaluador_correo: '',
    observacion: '',
    evidencia_url: '',
  })
  const [vinculationResultForm, setVinculationResultForm] = useState({
    beneficiarios_reales: '',
    resumen_impacto: '',
    observacion: '',
    evidencia_url: '',
  })
  const [vinculationProductForm, setVinculationProductForm] = useState({
    producto_id: '',
    nombre: '',
    descripcion: '',
    cantidad: '',
    unidad_medida: '',
    evidencia_url: '',
  })
  const [productReviewId, setProductReviewId] = useState<number | null>(null)
  const [productReviewObservation, setProductReviewObservation] = useState('')
  const [reopenForm, setReopenForm] = useState({ motivo: '', confirmar_reversion_titulacion: false })
  const [configurationForm, setConfigurationForm] = useState({
    horas_requeridas: process === 'PPF' ? '240' : '60',
    documentos_requeridos: process === 'PPF' ? '5' : '4',
    nota_minima_aprobacion: '7',
    requiere_evaluacion_docente: true,
    requiere_evaluacion_tutor: process === 'PPF',
    requiere_autoevaluacion: false,
    requiere_resultado_vinculacion: process === 'VIN',
    peso_docente: process === 'PPF' ? '60' : '100',
    peso_tutor: process === 'PPF' ? '40' : '0',
    peso_autoevaluacion: '0',
  })
  const [entityForm, setEntityForm] = useState({
    nombre: '',
    ruc: '',
    tipo_entidad: '',
    sector_economico: '',
    contacto_nombre: '',
    contacto_correo: '',
    contacto_telefono: '',
  })
  const [agreementForm, setAgreementForm] = useState({
    entidad_id: '',
    codigo_convenio: '',
    objeto: '',
    fecha_inicio: '',
    fecha_fin: '',
    archivo_url: '',
  })
  const [projectForm, setProjectForm] = useState({
    entidad_id: '',
    convenio_id: '',
    codigo_proyecto: '',
    nombre: '',
    linea_intervencion: '',
    poblacion_objetivo: '',
    beneficiarios_previstos: '',
    objetivo_general: '',
    fecha_inicio: '',
    fecha_fin: '',
  })

  const activeEntities = useMemo(
    () => catalog.entidades.filter((item) => item.activo !== false),
    [catalog.entidades],
  )
  const activeAgreements = useMemo(
    () => catalog.convenios.filter((item) => item.activo !== false && item.tipo_proceso_codigo === process),
    [catalog.convenios, process],
  )
  const activeProjects = useMemo(
    () => catalog.proyectos.filter((item) => item.activo !== false),
    [catalog.proyectos],
  )
  const selectedDashboardItem = useMemo(
    () => dashboard?.items.find((item) => item.ExpedienteId === selectedId) || null,
    [dashboard?.items, selectedId],
  )
  const defaultConfiguration = useMemo(
    () => catalog.configuraciones.find((item) => (
      item.tipo_proceso_codigo === process
      && !item.codigo_carrera
      && !item.nivel
      && !item.codigo_periodo
    )) || null,
    [catalog.configuraciones, process],
  )
  const planAllowsActivities = ['APROBADO', 'EN_EJECUCION'].includes(detail?.plan?.estado || '')
  const processClosed = Boolean(detail?.cierre?.fecha_cierre)
  const evaluationState = detail?.evaluacion?.estado || 'PENDIENTE_REVISION'
  const evaluationResult = detail?.evaluacion?.resultado || 'PENDIENTE'
  const minimumGrade = Number(detail?.configuracion?.nota_minima_aprobacion || defaultConfiguration?.nota_minima_aprobacion || 7)
  const calculatedGrade = detail?.calculo_calificacion?.calificacion_calculada
  const actionableReconciliations = useMemo(
    () => reconciliations.filter((item) => item.estado !== 'COMPLETADO'),
    [reconciliations],
  )

  function clearFeedback() {
    setError('')
    setMessage('')
  }

  async function loadOverview(preferredId?: number | null) {
    setLoading(true)
    clearFeedback()
    try {
      const [dashboardPayload, catalogPayload, notificationPayload, reconciliationPayload] = await Promise.all([
        fetchPracticasOperationsDashboard(process),
        fetchPracticasOperationsCatalog(),
        fetchPracticasOperationsNotifications(process),
        isAdmin
          ? fetchPracticasOperationsReconciliations()
          : Promise.resolve({ total: 0, items: [] as PracticasOperationsReconciliation[] }),
      ])
      setDashboard(dashboardPayload)
      setCatalog(catalogPayload)
      setNotifications(notificationPayload.items || [])
      setReconciliations(
        (reconciliationPayload.items || []).filter((item) => item.tipo_proceso_codigo === process),
      )
      const availableIds = new Set((dashboardPayload.items || []).map((item) => item.ExpedienteId))
      const nextId = preferredId && availableIds.has(preferredId)
        ? preferredId
        : dashboardPayload.items?.[0]?.ExpedienteId || null
      setSelectedId(nextId)
      if (!nextId) setDetail(null)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar el seguimiento operativo.')
    } finally {
      setLoading(false)
    }
  }

  async function loadDetail(expedienteId: number) {
    setDetailLoading(true)
    clearFeedback()
    try {
      const payload = await fetchPracticasOperationsDetail(expedienteId)
      setDetail(payload)
      const requiredHours = Number(payload.resumen.horas_requeridas || (process === 'PPF' ? 240 : 60))
      const plan = payload.plan
      setPlanForm({
        entidad_id: plan?.entidad_id ? String(plan.entidad_id) : '',
        convenio_id: plan?.convenio_id ? String(plan.convenio_id) : '',
        proyecto_id: plan?.proyecto_id ? String(plan.proyecto_id) : '',
        tutor_externo_nombre: textValue(plan?.tutor_externo_nombre),
        tutor_externo_correo: textValue(plan?.tutor_externo_correo),
        tutor_externo_telefono: textValue(plan?.tutor_externo_telefono),
        objetivo_general: textValue(plan?.objetivo_general),
        resultados_aprendizaje: textValue(plan?.resultados_aprendizaje),
        actividades_planificadas: textValue(plan?.actividades_planificadas),
        fecha_inicio: dateValue(plan?.fecha_inicio),
        fecha_fin: dateValue(plan?.fecha_fin),
        horas_planificadas: String(plan?.horas_planificadas || requiredHours),
      })
      setClosureForm({
        supervision_realizada: Boolean(payload.cierre?.supervision_realizada),
        evaluacion_entidad: payload.evaluacion?.calificacion === null || payload.evaluacion?.calificacion === undefined
          ? payload.cierre?.evaluacion_entidad === null || payload.cierre?.evaluacion_entidad === undefined
            ? ''
            : String(payload.cierre.evaluacion_entidad)
          : String(payload.evaluacion.calificacion),
        informe_final_validado: Boolean(payload.cierre?.informe_final_validado),
        acta_aceptacion_validada: Boolean(payload.cierre?.acta_aceptacion_validada),
        certificado_emitido: Boolean(payload.cierre?.certificado_emitido),
        observacion: textValue(payload.cierre?.observacion),
      })
      setEvaluationForm({
        calificacion: payload.evaluacion?.calificacion === null || payload.evaluacion?.calificacion === undefined
          ? payload.calculo_calificacion.calificacion_calculada === null || payload.calculo_calificacion.calificacion_calculada === undefined
            ? ''
            : String(payload.calculo_calificacion.calificacion_calculada)
          : String(payload.evaluacion.calificacion),
        observacion: '',
      })
      setVinculationResultForm({
        beneficiarios_reales: payload.resultado_vinculacion ? String(payload.resultado_vinculacion.beneficiarios_reales) : '',
        resumen_impacto: textValue(payload.resultado_vinculacion?.resumen_impacto),
        observacion: textValue(payload.resultado_vinculacion?.observacion),
        evidencia_url: textValue(payload.resultado_vinculacion?.evidencia_url),
      })
    } catch (apiError) {
      setDetail(null)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo abrir el expediente operativo.')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    setSelectedId(null)
    setDetail(null)
    setPlanForm(emptyPlan(process === 'PPF' ? 240 : 60))
    setEvaluationForm({ calificacion: '', observacion: '' })
    setActorEvaluationForm({
      rol_evaluador: isStudent ? 'AUTOEVALUACION' : 'DOCENTE_ACADEMICO',
      calificacion: '',
      evaluador_nombre: '',
      evaluador_correo: '',
      observacion: '',
      evidencia_url: '',
    })
    setVinculationProductForm({ producto_id: '', nombre: '', descripcion: '', cantidad: '', unidad_medida: '', evidencia_url: '' })
    setReopenForm({ motivo: '', confirmar_reversion_titulacion: false })
    void loadOverview(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [process])

  useEffect(() => {
    if (!defaultConfiguration) return
    setConfigurationForm({
      horas_requeridas: String(defaultConfiguration.horas_requeridas),
      documentos_requeridos: String(defaultConfiguration.documentos_requeridos),
      nota_minima_aprobacion: String(defaultConfiguration.nota_minima_aprobacion),
      requiere_evaluacion_docente: Boolean(defaultConfiguration.requiere_evaluacion_docente),
      requiere_evaluacion_tutor: Boolean(defaultConfiguration.requiere_evaluacion_tutor),
      requiere_autoevaluacion: Boolean(defaultConfiguration.requiere_autoevaluacion),
      requiere_resultado_vinculacion: Boolean(defaultConfiguration.requiere_resultado_vinculacion),
      peso_docente: String(defaultConfiguration.peso_docente),
      peso_tutor: String(defaultConfiguration.peso_tutor),
      peso_autoevaluacion: String(defaultConfiguration.peso_autoevaluacion),
    })
  }, [defaultConfiguration])

  useEffect(() => {
    setIndicatorForm({ indicador_id: '', nombre: '', unidad_medida: '', meta: '', resultado: '', evidencia_url: '', observacion: '' })
    if (selectedId) void loadDetail(selectedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  async function refreshSelected(successMessage?: string) {
    if (!selectedId) return
    await Promise.all([loadDetail(selectedId), loadOverview(selectedId)])
    if (successMessage) setMessage(successMessage)
  }

  async function submitPlan(state: 'BORRADOR' | 'APROBADO') {
    if (!selectedId) return
    if (process === 'PPF' && (!planForm.entidad_id || !planForm.convenio_id)) {
      setError('Seleccione la entidad receptora y un convenio vigente para las prácticas.')
      return
    }
    if (process === 'VIN' && !planForm.proyecto_id) {
      setError('Seleccione el proyecto de vinculación.')
      return
    }
    if (!planForm.fecha_inicio || !planForm.fecha_fin || planForm.fecha_fin < planForm.fecha_inicio) {
      setError('Defina un rango de fechas válido para el plan.')
      return
    }
    if (numberValue(planForm.horas_planificadas) <= 0) {
      setError('Las horas planificadas deben ser mayores a cero.')
      return
    }
    if (state === 'APROBADO') {
      const requiredHours = Number(detail?.resumen.horas_requeridas || (process === 'PPF' ? 240 : 60))
      if (!planForm.objetivo_general.trim() || !planForm.actividades_planificadas.trim()) {
        setError('Complete el objetivo general y las actividades antes de aprobar el plan.')
        return
      }
      if (process === 'PPF' && !planForm.tutor_externo_nombre.trim()) {
        setError('Registre el tutor externo antes de aprobar el plan.')
        return
      }
      if (numberValue(planForm.horas_planificadas) < requiredHours) {
        setError(`El plan debe contemplar al menos ${requiredHours} horas.`)
        return
      }
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsPlan(selectedId, {
        entidad_id: planForm.entidad_id ? Number(planForm.entidad_id) : null,
        convenio_id: planForm.convenio_id ? Number(planForm.convenio_id) : null,
        proyecto_id: planForm.proyecto_id ? Number(planForm.proyecto_id) : null,
        tutor_externo_nombre: planForm.tutor_externo_nombre.trim() || null,
        tutor_externo_correo: planForm.tutor_externo_correo.trim() || null,
        tutor_externo_telefono: planForm.tutor_externo_telefono.trim() || null,
        objetivo_general: planForm.objetivo_general.trim() || null,
        resultados_aprendizaje: planForm.resultados_aprendizaje.trim() || null,
        actividades_planificadas: planForm.actividades_planificadas.trim() || null,
        fecha_inicio: planForm.fecha_inicio,
        fecha_fin: planForm.fecha_fin,
        horas_planificadas: numberValue(planForm.horas_planificadas),
        estado: state,
      })
      await refreshSelected(textValue(response.message) || 'Plan guardado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el plan.')
    } finally {
      setSaving(false)
    }
  }

  async function submitActivity() {
    if (!selectedId) return
    const hasStart = Boolean(activityForm.hora_inicio)
    const hasEnd = Boolean(activityForm.hora_fin)
    if (hasStart !== hasEnd) {
      setError('Registre la hora de inicio y la hora de fin de la jornada.')
      return
    }
    if (!activityForm.descripcion.trim() || (!hasStart && numberValue(activityForm.horas) <= 0)) {
      setError('Registre la fecha, descripción y las horas o la jornada de la actividad.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await createPracticasOperationsActivity(selectedId, {
        fecha_actividad: activityForm.fecha_actividad,
        descripcion: activityForm.descripcion.trim(),
        horas: hasStart ? null : numberValue(activityForm.horas),
        hora_inicio: activityForm.hora_inicio || null,
        hora_fin: activityForm.hora_fin || null,
        descanso_minutos: numberValue(activityForm.descanso_minutos),
        modalidad: activityForm.modalidad as 'PRESENCIAL' | 'VIRTUAL' | 'HIBRIDA',
        lugar: activityForm.lugar.trim() || null,
        evidencia_url: activityForm.evidencia_url.trim() || null,
        evidencia_nombre: activityForm.evidencia_nombre.trim() || null,
      })
      setActivityForm({
        fecha_actividad: todayValue(),
        descripcion: '',
        horas: '',
        hora_inicio: '',
        hora_fin: '',
        descanso_minutos: '0',
        modalidad: 'PRESENCIAL',
        lugar: '',
        evidencia_url: '',
        evidencia_nombre: '',
      })
      await refreshSelected(textValue(response.message) || 'Actividad registrada correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la actividad.')
    } finally {
      setSaving(false)
    }
  }

  async function submitActivityReview(
    activityId: number,
    state: 'VALIDADO' | 'OBSERVADO' | 'RECHAZADO',
  ) {
    if (state !== 'VALIDADO' && !reviewObservation.trim()) {
      setError('Registre la observación que debe corregir el estudiante.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await reviewPracticasOperationsActivity(activityId, {
        estado_revision: state,
        observacion_revision: reviewObservation.trim() || null,
      })
      setReviewActivityId(null)
      setReviewObservation('')
      await refreshSelected(textValue(response.message) || 'Actividad revisada correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo revisar la actividad.')
    } finally {
      setSaving(false)
    }
  }

  async function submitIndicator() {
    if (!selectedId) return
    if (!indicatorForm.nombre.trim() || !indicatorForm.unidad_medida.trim() || !indicatorForm.meta.trim()) {
      setError('Complete el nombre, la unidad de medida y la meta del indicador.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsIndicator(selectedId, {
        indicador_id: indicatorForm.indicador_id ? Number(indicatorForm.indicador_id) : null,
        nombre: indicatorForm.nombre.trim(),
        unidad_medida: indicatorForm.unidad_medida.trim(),
        meta: numberValue(indicatorForm.meta),
        resultado: indicatorForm.resultado.trim() ? numberValue(indicatorForm.resultado) : null,
        evidencia_url: indicatorForm.evidencia_url.trim() || null,
        observacion: indicatorForm.observacion.trim() || null,
      })
      setIndicatorForm({ indicador_id: '', nombre: '', unidad_medida: '', meta: '', resultado: '', evidencia_url: '', observacion: '' })
      await refreshSelected(textValue(response.message) || 'Indicador guardado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el indicador.')
    } finally {
      setSaving(false)
    }
  }

  async function submitActorEvaluation() {
    if (!selectedId || !actorEvaluationForm.calificacion.trim()) {
      setError('Ingrese una calificación sobre 10 para la evaluación seleccionada.')
      return
    }
    const grade = numberValue(actorEvaluationForm.calificacion)
    if (grade < 0 || grade > 10) {
      setError('La evaluación debe encontrarse entre 0 y 10.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsActorEvaluation(
        selectedId,
        actorEvaluationForm.rol_evaluador as 'DOCENTE_ACADEMICO' | 'TUTOR_EMPRESARIAL' | 'AUTOEVALUACION',
        {
          calificacion: grade,
          evaluador_nombre: actorEvaluationForm.evaluador_nombre.trim() || null,
          evaluador_correo: actorEvaluationForm.evaluador_correo.trim() || null,
          observacion: actorEvaluationForm.observacion.trim() || null,
          evidencia_url: actorEvaluationForm.evidencia_url.trim() || null,
        },
      )
      setActorEvaluationForm((current) => ({
        ...current,
        calificacion: '',
        evaluador_nombre: '',
        evaluador_correo: '',
        observacion: '',
        evidencia_url: '',
      }))
      await refreshSelected(textValue(response.message) || 'Evaluación registrada correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la evaluación.')
    } finally {
      setSaving(false)
    }
  }

  async function submitVinculationResult(validateResult: boolean) {
    if (!selectedId || !vinculationResultForm.beneficiarios_reales.trim() || vinculationResultForm.resumen_impacto.trim().length < 10) {
      setError('Registre los beneficiarios reales y un resumen del impacto alcanzado.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsVinculationResult(selectedId, {
        beneficiarios_reales: numberValue(vinculationResultForm.beneficiarios_reales),
        resumen_impacto: vinculationResultForm.resumen_impacto.trim(),
        observacion: vinculationResultForm.observacion.trim() || null,
        evidencia_url: vinculationResultForm.evidencia_url.trim() || null,
        validar: validateResult,
      })
      await refreshSelected(textValue(response.message) || 'Resultados guardados correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron guardar los resultados de vinculación.')
    } finally {
      setSaving(false)
    }
  }

  async function submitVinculationProduct() {
    if (!selectedId || !vinculationProductForm.nombre.trim() || !vinculationProductForm.unidad_medida.trim() || !vinculationProductForm.cantidad.trim()) {
      setError('Complete el nombre, la cantidad y la unidad del producto entregado.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsVinculationProduct(selectedId, {
        producto_id: vinculationProductForm.producto_id ? Number(vinculationProductForm.producto_id) : null,
        nombre: vinculationProductForm.nombre.trim(),
        descripcion: vinculationProductForm.descripcion.trim() || null,
        cantidad: numberValue(vinculationProductForm.cantidad),
        unidad_medida: vinculationProductForm.unidad_medida.trim(),
        evidencia_url: vinculationProductForm.evidencia_url.trim() || null,
      })
      setVinculationProductForm({ producto_id: '', nombre: '', descripcion: '', cantidad: '', unidad_medida: '', evidencia_url: '' })
      await refreshSelected(textValue(response.message) || 'Producto guardado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el producto de vinculación.')
    } finally {
      setSaving(false)
    }
  }

  async function submitVinculationProductReview(
    productId: number,
    state: 'VALIDADO' | 'OBSERVADO' | 'RECHAZADO',
  ) {
    if (state !== 'VALIDADO' && !productReviewObservation.trim()) {
      setError('Registre la observación para devolver o rechazar el producto.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await reviewPracticasOperationsVinculationProduct(productId, {
        estado_revision: state,
        observacion_revision: productReviewObservation.trim() || null,
      })
      setProductReviewId(null)
      setProductReviewObservation('')
      await refreshSelected(textValue(response.message) || 'Producto revisado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo revisar el producto.')
    } finally {
      setSaving(false)
    }
  }

  async function saveConfiguration() {
    const weights = [
      configurationForm.requiere_evaluacion_docente ? numberValue(configurationForm.peso_docente) : 0,
      configurationForm.requiere_evaluacion_tutor ? numberValue(configurationForm.peso_tutor) : 0,
      configurationForm.requiere_autoevaluacion ? numberValue(configurationForm.peso_autoevaluacion) : 0,
    ]
    if (numberValue(configurationForm.horas_requeridas) <= 0 || numberValue(configurationForm.nota_minima_aprobacion) < 0) {
      setError('Revise las horas requeridas y la nota mínima.')
      return
    }
    if (Math.abs(weights.reduce((total, value) => total + value, 0) - 100) > 0.01) {
      setError('Los pesos de las evaluaciones obligatorias deben sumar 100%.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsConfiguration({
        tipo_proceso_codigo: process,
        horas_requeridas: numberValue(configurationForm.horas_requeridas),
        documentos_requeridos: numberValue(configurationForm.documentos_requeridos),
        nota_minima_aprobacion: numberValue(configurationForm.nota_minima_aprobacion),
        requiere_evaluacion_docente: configurationForm.requiere_evaluacion_docente,
        requiere_evaluacion_tutor: configurationForm.requiere_evaluacion_tutor,
        requiere_autoevaluacion: configurationForm.requiere_autoevaluacion,
        requiere_resultado_vinculacion: process === 'VIN' && configurationForm.requiere_resultado_vinculacion,
        peso_docente: configurationForm.requiere_evaluacion_docente ? numberValue(configurationForm.peso_docente) : 0,
        peso_tutor: configurationForm.requiere_evaluacion_tutor ? numberValue(configurationForm.peso_tutor) : 0,
        peso_autoevaluacion: configurationForm.requiere_autoevaluacion ? numberValue(configurationForm.peso_autoevaluacion) : 0,
      })
      const updatedCatalog = await fetchPracticasOperationsCatalog()
      setCatalog(updatedCatalog)
      if (selectedId) await loadDetail(selectedId)
      setMessage(textValue(response.message) || 'Reglas del proceso actualizadas.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudieron guardar las reglas del proceso.')
    } finally {
      setSaving(false)
    }
  }

  async function reopenRecord() {
    if (!selectedId || reopenForm.motivo.trim().length < 10) {
      setError('Registre un motivo de al menos 10 caracteres para reabrir el expediente.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await reopenPracticasOperationsRecord(selectedId, {
        motivo: reopenForm.motivo.trim(),
        confirmar_reversion_titulacion: reopenForm.confirmar_reversion_titulacion,
      })
      setReopenForm({ motivo: '', confirmar_reversion_titulacion: false })
      await refreshSelected(textValue(response.message) || 'Expediente reabierto correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo reabrir el expediente.')
    } finally {
      setSaving(false)
    }
  }

  async function submitEvaluation(
    action: 'ENVIAR_REVISION' | 'DEVOLVER' | 'HABILITAR_CALIFICACION' | 'CALIFICAR',
  ) {
    if (!selectedId) return
    const observation = evaluationForm.observacion.trim()
    if (action === 'DEVOLVER' && !observation) {
      setError('Detalle la corrección que debe realizar el estudiante.')
      return
    }
    if (
      action === 'CALIFICAR'
      && (calculatedGrade === null || calculatedGrade === undefined)
      && !evaluationForm.calificacion.trim()
    ) {
      setError('Ingrese la calificación final sobre 10.')
      return
    }
    const grade = action === 'CALIFICAR'
      ? calculatedGrade ?? numberValue(evaluationForm.calificacion)
      : null
    if (action === 'CALIFICAR' && grade !== null && (grade < 0 || grade > 10)) {
      setError('La calificación debe encontrarse entre 0 y 10.')
      return
    }
    if (action === 'CALIFICAR' && grade !== null && grade < minimumGrade && !observation) {
      setError('Registre una observación que justifique la reprobación.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsEvaluation(selectedId, {
        accion: action,
        calificacion: grade,
        observacion: observation || null,
      })
      setEvaluationForm((current) => ({ ...current, observacion: '' }))
      await refreshSelected(textValue(response.message) || 'Estado de evaluación actualizado.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar la revisión y calificación.')
    } finally {
      setSaving(false)
    }
  }

  async function submitClosure(closeProcess: boolean) {
    if (!selectedId) return
    setSaving(true)
    clearFeedback()
    try {
      const response = await savePracticasOperationsClosure(selectedId, {
        supervision_realizada: closureForm.supervision_realizada,
        evaluacion_entidad: closureForm.evaluacion_entidad ? numberValue(closureForm.evaluacion_entidad) : null,
        informe_final_validado: closureForm.informe_final_validado,
        acta_aceptacion_validada: closureForm.acta_aceptacion_validada,
        certificado_emitido: closureForm.certificado_emitido,
        observacion: closureForm.observacion.trim() || null,
        cerrar: closeProcess,
      })
      await refreshSelected(textValue(response.message) || 'Seguimiento de cierre actualizado.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar el cierre.')
    } finally {
      setSaving(false)
    }
  }

  async function markNotification(notificationId: number) {
    try {
      await readPracticasOperationsNotification(notificationId)
      setNotifications((current) => current.map((item) => (
        item.notificacion_id === notificationId ? { ...item, leida: true } : item
      )))
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo actualizar la notificación.')
    }
  }

  async function retryReconciliation(reconciliationId: number) {
    setSaving(true)
    clearFeedback()
    try {
      const response = await retryPracticasOperationsReconciliation(reconciliationId)
      await loadOverview(selectedId)
      if (selectedId) await loadDetail(selectedId)
      setMessage(response.ok ? 'La conciliación con Titulación se completó correctamente.' : 'La conciliación sigue pendiente; revise el detalle técnico.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo reintentar la conciliación.')
    } finally {
      setSaving(false)
    }
  }

  async function loadAudit() {
    if (!isAdmin || auditLoading) return
    setAuditLoading(true)
    try {
      const response = await fetchPracticasOperationsAudit(100)
      setAuditItems(response.items || [])
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo cargar la auditoría operativa.')
    } finally {
      setAuditLoading(false)
    }
  }

  async function exportReport(format: 'xlsx' | 'pdf') {
    setSaving(true)
    clearFeedback()
    try {
      const blob = await downloadPracticasOperationsReport(process, format)
      downloadBlob(blob, `seguimiento-${process.toLowerCase()}.${format}`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo generar el reporte.')
    } finally {
      setSaving(false)
    }
  }

  async function saveEntity() {
    if (!entityForm.nombre.trim()) {
      setError('Ingrese el nombre de la entidad receptora.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await createPracticasOperationsEntity({
        nombre: entityForm.nombre.trim(),
        ruc: entityForm.ruc.trim() || null,
        tipo_entidad: entityForm.tipo_entidad.trim() || null,
        sector_economico: entityForm.sector_economico.trim() || null,
        contacto_nombre: entityForm.contacto_nombre.trim() || null,
        contacto_correo: entityForm.contacto_correo.trim() || null,
        contacto_telefono: entityForm.contacto_telefono.trim() || null,
      })
      setEntityForm({ nombre: '', ruc: '', tipo_entidad: '', sector_economico: '', contacto_nombre: '', contacto_correo: '', contacto_telefono: '' })
      setCatalog(await fetchPracticasOperationsCatalog())
      setMessage(textValue(response.message) || 'Entidad registrada correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar la entidad.')
    } finally {
      setSaving(false)
    }
  }

  async function saveAgreement() {
    if (!agreementForm.entidad_id || !agreementForm.codigo_convenio.trim() || !agreementForm.fecha_inicio || !agreementForm.fecha_fin) {
      setError('Complete entidad, código y vigencia del convenio.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await createPracticasOperationsAgreement({
        entidad_id: Number(agreementForm.entidad_id),
        tipo_proceso_codigo: process,
        codigo_convenio: agreementForm.codigo_convenio.trim(),
        objeto: agreementForm.objeto.trim() || null,
        fecha_inicio: agreementForm.fecha_inicio,
        fecha_fin: agreementForm.fecha_fin,
        archivo_url: agreementForm.archivo_url.trim() || null,
      })
      setAgreementForm({ entidad_id: '', codigo_convenio: '', objeto: '', fecha_inicio: '', fecha_fin: '', archivo_url: '' })
      setCatalog(await fetchPracticasOperationsCatalog())
      setMessage(textValue(response.message) || 'Convenio registrado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar el convenio.')
    } finally {
      setSaving(false)
    }
  }

  async function saveProject() {
    if (!projectForm.codigo_proyecto.trim() || !projectForm.nombre.trim() || !projectForm.linea_intervencion.trim() || !projectForm.fecha_inicio || !projectForm.fecha_fin) {
      setError('Complete código, nombre, línea y vigencia del proyecto.')
      return
    }
    setSaving(true)
    clearFeedback()
    try {
      const response = await createPracticasOperationsProject({
        entidad_id: projectForm.entidad_id ? Number(projectForm.entidad_id) : null,
        convenio_id: projectForm.convenio_id ? Number(projectForm.convenio_id) : null,
        codigo_proyecto: projectForm.codigo_proyecto.trim(),
        nombre: projectForm.nombre.trim(),
        linea_intervencion: projectForm.linea_intervencion.trim(),
        poblacion_objetivo: projectForm.poblacion_objetivo.trim() || null,
        beneficiarios_previstos: projectForm.beneficiarios_previstos ? numberValue(projectForm.beneficiarios_previstos) : null,
        objetivo_general: projectForm.objetivo_general.trim() || null,
        fecha_inicio: projectForm.fecha_inicio,
        fecha_fin: projectForm.fecha_fin,
      })
      setProjectForm({ entidad_id: '', convenio_id: '', codigo_proyecto: '', nombre: '', linea_intervencion: '', poblacion_objetivo: '', beneficiarios_previstos: '', objetivo_general: '', fecha_inicio: '', fecha_fin: '' })
      setCatalog(await fetchPracticasOperationsCatalog())
      setMessage(textValue(response.message) || 'Proyecto registrado correctamente.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo registrar el proyecto.')
    } finally {
      setSaving(false)
    }
  }

  const summary = dashboard?.summary
  const documentProgress = percentage(detail?.resumen.avance_documental_porcentaje)
  const processProgress = percentage(detail?.resumen.avance_porcentaje)
  const displayedProgress = isStudent ? documentProgress : processProgress

  return (
    <section className={`student-card student-card--wide practicas-ops${catalogOnly ? ' is-catalog-mode' : ' is-followup-mode'}`}>
      <header className="practicas-ops__header">
        <div>
          <span>{catalogOnly ? 'Configuración institucional' : 'Seguimiento integral'}</span>
          <h2>
            {catalogOnly
              ? process === 'PPF' ? 'Entidades y convenios de prácticas' : 'Proyectos y convenios de vinculación'
              : process === 'PPF' ? 'Proceso de prácticas preprofesionales' : 'Proceso de vinculación con la sociedad'}
          </h2>
          <p>
            {catalogOnly
              ? 'Mantenga disponibles las entidades, los convenios vigentes y los proyectos que se asignarán a cada plan.'
              : isStudent
              ? 'Consulta tu cumplimiento documental, registra tus actividades y revisa las observaciones del responsable.'
              : 'Administra el plan, revisa evidencias, habilita la calificación y registra el resultado final del proceso.'}
          </p>
        </div>
        <div className="practicas-ops__actions">
          {!isStudent && !catalogOnly ? (
            <>
              <button type="button" className="ghost-button" onClick={() => void exportReport('xlsx')} disabled={saving}>Excel</button>
              <button type="button" className="ghost-button" onClick={() => void exportReport('pdf')} disabled={saving}>PDF</button>
            </>
          ) : null}
          <button type="button" className="secondary-action" onClick={() => void loadOverview(selectedId)} disabled={loading || saving}>
            {loading ? 'Actualizando...' : catalogOnly ? 'Actualizar catálogos' : 'Actualizar seguimiento'}
          </button>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}

      <div className="practicas-ops__metrics">
        <article><span>Inscripciones</span><strong>{summary?.total || 0}</strong><small>Expedientes visibles</small></article>
        <article><span>En revisión</span><strong>{summary?.en_revision || 0}</strong><small>Expedientes enviados</small></article>
        <article><span>Esperan calificación</span><strong>{summary?.pendientes_calificacion || 0}</strong><small>Revisión finalizada</small></article>
        <article><span>Aprobados</span><strong>{summary?.aprobados || 0}</strong><small>Nota mínima {minimumGrade.toFixed(2)}</small></article>
        <article><span>Reprobados</span><strong>{summary?.reprobados || 0}</strong><small>No habilitan Titulación</small></article>
        <article><span>Cerrados</span><strong>{summary?.cerrados || 0}</strong><small>Proceso finalizado</small></article>
      </div>

      {notifications.length ? (
        <details className="practicas-ops__notifications">
          <summary>{notifications.filter((item) => !item.leida).length} alerta(s) pendiente(s)</summary>
          <div>
            {notifications.slice(0, 20).map((item) => (
              <button
                type="button"
                key={item.notificacion_id}
                className={item.leida ? 'is-read' : ''}
                onClick={() => {
                  if (item.expediente_id) setSelectedId(item.expediente_id)
                  if (!item.leida) void markNotification(item.notificacion_id)
                }}
              >
                <span>{item.nivel}</span>
                <strong>{item.titulo}</strong>
                <small>{item.mensaje}</small>
              </button>
            ))}
          </div>
        </details>
      ) : null}

      {isAdmin && actionableReconciliations.length ? (
        <details className="practicas-ops__reconciliations">
          <summary>{actionableReconciliations.length} conciliación(es) pendiente(s) con Titulación</summary>
          <div>
            {actionableReconciliations.map((item) => (
              <article key={item.conciliacion_id}>
                <div>
                  <span>{item.estado}</span>
                  <strong>Expediente {item.expediente_id}</strong>
                  <small>{item.ultimo_error || `Intentos realizados: ${item.intentos}`}</small>
                  <small>Último intento: {dateTimeLabel(item.fecha_ultimo_intento)}</small>
                </div>
                <div className="practicas-ops__form-actions">
                  <button type="button" className="ghost-button" onClick={() => setSelectedId(item.expediente_id)} disabled={saving}>Revisar expediente</button>
                  <button type="button" className="secondary-action" onClick={() => void retryReconciliation(item.conciliacion_id)} disabled={saving}>Reintentar</button>
                </div>
              </article>
            ))}
          </div>
        </details>
      ) : null}

      <div className="practicas-ops__workspace">
        <aside className="practicas-ops__list" aria-label="Inscripciones del proceso">
          <header>
            <strong>{isStudent ? 'Mis inscripciones' : 'Inscripciones para seguimiento'}</strong>
            <span>{dashboard?.items.length || 0}</span>
          </header>
          {dashboard?.items.length ? dashboard.items.map((item) => (
            <button
              type="button"
              key={item.ExpedienteId}
              className={selectedId === item.ExpedienteId ? 'is-selected' : ''}
              onClick={() => setSelectedId(item.ExpedienteId)}
            >
              <span className={`practicas-semaphore is-${(item.Semaforo || 'AMARILLO').toLowerCase()}`} aria-hidden="true" />
              <span>
                <strong>{textValue(item.Estudiante) || textValue(item.CodigoExpediente) || `Expediente ${item.ExpedienteId}`}</strong>
                <small>{textValue(item.Carrera) || 'Carrera pendiente'} · {textValue(item.Periodo || item.CodigoPeriodo)}</small>
                <small>Inscripción: {enrollmentStatusLabel(item.EstadoInscripcion)}</small>
                <small>
                  Evaluación: {evaluationStageLabel(item.EstadoEvaluacion)}
                  {item.ResultadoEvaluacion && item.ResultadoEvaluacion !== 'PENDIENTE'
                    ? ` · ${evaluationResultLabel(item.ResultadoEvaluacion)} · ${Number(item.CalificacionFinal || 0).toFixed(2)}/10`
                    : ''}
                </small>
                <small>
                  Documentación: {item.DocumentosCargados || 0}/{item.DocumentosRequeridos || 0}
                  {' · '}{percentage(item.AvanceDocumental).toFixed(0)}%
                </small>
                <small>{semaphoreLabel(item)}</small>
              </span>
            </button>
          )) : (
            <p>No existen inscripciones para este proceso. Administración debe registrar primero al estudiante.</p>
          )}
        </aside>

        <main className="practicas-ops__detail">
          {detailLoading ? <p className="practicas-ops__empty">Cargando expediente...</p> : null}
          {!detailLoading && !detail ? (
            <p className="practicas-ops__empty">Seleccione una inscripción para revisar el proceso.</p>
          ) : null}
          {!detailLoading && detail ? (
            <>
              <header className="practicas-ops__detail-header">
                <div>
                  <span>{textValue(selectedDashboardItem?.CodigoExpediente) || `Expediente ${selectedId}`}</span>
                  <h3>{textValue(selectedDashboardItem?.Estudiante) || 'Seguimiento del estudiante'}</h3>
                  <p>{textValue(selectedDashboardItem?.Carrera)} · {textValue(selectedDashboardItem?.Periodo || selectedDashboardItem?.CodigoPeriodo)}</p>
                </div>
                {canOpenDocuments ? (
                  <button
                    type="button"
                    className="secondary-action"
                    onClick={() => onOpenDocuments(textValue(selectedDashboardItem?.Cedula))}
                    disabled={!textValue(selectedDashboardItem?.Cedula)}
                  >
                    {canUploadDocuments ? 'Cargar documentos' : 'Consultar documentos'}
                  </button>
                ) : null}
              </header>

              <section className="practicas-ops__progress" aria-label={isStudent ? 'Cumplimiento documental' : 'Avance del proceso'}>
                <div>
                  <span>{isStudent ? 'Cumplimiento documental' : 'Avance de requisitos'}</span>
                  <strong>{displayedProgress.toFixed(0)}%</strong>
                </div>
                <div
                  className="practicas-progress-bar"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={displayedProgress}
                >
                  <span style={{ width: `${displayedProgress}%` }} />
                </div>
                <small>
                  {isStudent
                    ? `${detail.resumen.documentos_cargados} de ${detail.resumen.documentos_requeridos} documentos obligatorios cargados por el responsable`
                    : `${detail.resumen.requisitos_completos} de ${detail.resumen.requisitos_totales} etapas completas`}
                </small>
              </section>

              <dl className="practicas-ops__context">
                <div><dt>Inscripción institucional</dt><dd>{enrollmentStatusLabel(selectedDashboardItem?.EstadoInscripcion)}</dd></div>
                <div><dt>Períodos vinculados</dt><dd>Institucional: {textValue(selectedDashboardItem?.CodigoPeriodoInstitucional) || 'Pendiente'} · Referencia académica: {textValue(selectedDashboardItem?.CodigoPeriodoAcademicoOrigen) || 'Pendiente'}</dd></div>
                <div><dt>Responsable académico</dt><dd>{textValue(detail.responsable?.NombreResponsable) || 'Pendiente de asignación'}</dd></div>
                <div><dt>Correo del responsable</dt><dd>{textValue(detail.responsable?.CorreoResponsable) || 'Pendiente'}</dd></div>
                <div><dt>Plazo del proceso</dt><dd>{dateValue(selectedDashboardItem?.FechaInicio) || 'Sin inicio'} al {dateValue(selectedDashboardItem?.FechaFin) || 'sin cierre'}</dd></div>
                <div><dt>Horas requeridas</dt><dd>{Number(detail.resumen.horas_requeridas || 0).toFixed(0)} horas</dd></div>
                <div><dt>Base operativa</dt><dd>{detail.almacenamiento.base_datos}</dd></div>
              </dl>

              <section className="practicas-ops__section">
                <header><span>Ruta del estudiante</span><h3>Qué necesitas completar</h3></header>
                <ol className="practicas-requirements">
                  {detail.requisitos.map((item, index) => (
                    <li key={item.codigo} className={requirementClass(item.estado)}>
                      <span>{index + 1}</span>
                      <div><strong>{item.titulo}</strong><small>{item.detalle}</small></div>
                      <b>{item.estado === 'COMPLETO' ? 'Completo' : item.estado === 'EN_REVISION' ? 'En revisión' : 'Pendiente'}</b>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="practicas-ops__section">
                <header>
                  <span>Plan operativo</span>
                  <h3>{detail.permisos.puede_editar_plan ? 'Definición y aprobación del plan' : 'Plan asignado por el responsable'}</h3>
                </header>
                {detail.permisos.puede_editar_plan && !processClosed ? (
                  <div className="practicas-ops__form-grid">
                    {process === 'PPF' ? (
                      <label><span>Entidad receptora</span><select value={planForm.entidad_id} onChange={(event) => setPlanForm((current) => ({ ...current, entidad_id: event.target.value, convenio_id: '' }))}><option value="">Seleccionar entidad</option>{activeEntities.map((item) => <option key={item.entidad_id} value={item.entidad_id}>{item.nombre}</option>)}</select></label>
                    ) : (
                      <label><span>Proyecto de vinculación</span><select value={planForm.proyecto_id} onChange={(event) => setPlanForm((current) => ({ ...current, proyecto_id: event.target.value }))}><option value="">Seleccionar proyecto</option>{activeProjects.map((item) => <option key={item.proyecto_id} value={item.proyecto_id}>{item.codigo_proyecto} · {item.nombre}</option>)}</select></label>
                    )}
                    <label><span>Convenio vigente</span><select value={planForm.convenio_id} onChange={(event) => setPlanForm((current) => ({ ...current, convenio_id: event.target.value }))}><option value="">Sin convenio asociado</option>{activeAgreements.filter((item) => !planForm.entidad_id || String(item.entidad_id) === planForm.entidad_id).map((item) => <option key={item.convenio_id} value={item.convenio_id}>{item.codigo_convenio} · {item.entidad_nombre}</option>)}</select></label>
                    <label><span>Tutor externo</span><input value={planForm.tutor_externo_nombre} onChange={(event) => setPlanForm((current) => ({ ...current, tutor_externo_nombre: event.target.value }))} /></label>
                    <label><span>Correo del tutor</span><input type="email" value={planForm.tutor_externo_correo} onChange={(event) => setPlanForm((current) => ({ ...current, tutor_externo_correo: event.target.value }))} /></label>
                    <label><span>Teléfono del tutor</span><input value={planForm.tutor_externo_telefono} onChange={(event) => setPlanForm((current) => ({ ...current, tutor_externo_telefono: event.target.value }))} /></label>
                    <label><span>Horas planificadas</span><input type="number" min="1" max="10000" step="0.5" value={planForm.horas_planificadas} onChange={(event) => setPlanForm((current) => ({ ...current, horas_planificadas: event.target.value }))} /></label>
                    <label><span>Fecha de inicio</span><input type="date" value={planForm.fecha_inicio} onChange={(event) => setPlanForm((current) => ({ ...current, fecha_inicio: event.target.value }))} /></label>
                    <label><span>Fecha de fin</span><input type="date" value={planForm.fecha_fin} onChange={(event) => setPlanForm((current) => ({ ...current, fecha_fin: event.target.value }))} /></label>
                    <label className="is-wide"><span>Objetivo general</span><textarea rows={3} value={planForm.objetivo_general} onChange={(event) => setPlanForm((current) => ({ ...current, objetivo_general: event.target.value }))} /></label>
                    <label className="is-wide"><span>Resultados de aprendizaje</span><textarea rows={3} value={planForm.resultados_aprendizaje} onChange={(event) => setPlanForm((current) => ({ ...current, resultados_aprendizaje: event.target.value }))} /></label>
                    <label className="is-wide"><span>Actividades planificadas</span><textarea rows={4} value={planForm.actividades_planificadas} onChange={(event) => setPlanForm((current) => ({ ...current, actividades_planificadas: event.target.value }))} /></label>
                    <div className="practicas-ops__form-actions is-wide">
                      <button type="button" className="ghost-button" onClick={() => void submitPlan('BORRADOR')} disabled={saving}>Guardar borrador</button>
                      <button type="button" className="primary-action" onClick={() => void submitPlan('APROBADO')} disabled={saving}>Aprobar plan</button>
                    </div>
                  </div>
                ) : detail.plan ? (
                  <dl className="practicas-ops__plan-summary">
                    <div><dt>Estado</dt><dd>{detail.plan.estado || 'Pendiente'}</dd></div>
                    <div><dt>Entidad o proyecto</dt><dd>{activeEntities.find((item) => item.entidad_id === detail.plan?.entidad_id)?.nombre || activeProjects.find((item) => item.proyecto_id === detail.plan?.proyecto_id)?.nombre || 'Pendiente'}</dd></div>
                    <div><dt>Tutor externo</dt><dd>{detail.plan.tutor_externo_nombre || 'Pendiente'}</dd></div>
                    <div><dt>Contacto del tutor</dt><dd>{detail.plan.tutor_externo_correo || detail.plan.tutor_externo_telefono || 'Pendiente'}</dd></div>
                    <div><dt>Período</dt><dd>{dateValue(detail.plan.fecha_inicio)} al {dateValue(detail.plan.fecha_fin)}</dd></div>
                    <div><dt>Horas</dt><dd>{detail.plan.horas_planificadas || detail.resumen.horas_requeridas}</dd></div>
                    <div className="is-wide"><dt>Objetivo</dt><dd>{detail.plan.objetivo_general || 'El responsable aún no ha detallado el objetivo.'}</dd></div>
                    <div className="is-wide"><dt>Resultados esperados</dt><dd>{detail.plan.resultados_aprendizaje || 'El responsable aún no ha detallado los resultados.'}</dd></div>
                    <div className="is-wide"><dt>Actividades</dt><dd>{detail.plan.actividades_planificadas || 'El responsable aún no ha detallado las actividades.'}</dd></div>
                  </dl>
                ) : <p className="practicas-ops__notice">El responsable debe crear y aprobar el plan antes de que puedas registrar actividades.</p>}
              </section>

              <section className="practicas-ops__section">
                <header><span>Bitácora</span><h3>Actividades y horas de práctica</h3></header>
                <div className="practicas-ops__hour-summary">
                  <strong>{Number(detail.resumen.horas_validadas || 0).toFixed(1)} / {Number(detail.resumen.horas_requeridas || 0).toFixed(0)} horas validadas</strong>
                  <span>{Number(detail.resumen.horas_registradas || 0).toFixed(1)} registradas · {detail.resumen.pendientes || 0} pendiente(s) de revisión</span>
                </div>
                {detail.permisos.puede_registrar_actividad ? (
                  <div className="practicas-ops__activity-form">
                    <label><span>Fecha</span><input type="date" value={activityForm.fecha_actividad} onChange={(event) => setActivityForm((current) => ({ ...current, fecha_actividad: event.target.value }))} disabled={!planAllowsActivities || saving} /></label>
                    <label><span>Modalidad</span><select value={activityForm.modalidad} onChange={(event) => setActivityForm((current) => ({ ...current, modalidad: event.target.value }))} disabled={!planAllowsActivities || saving}><option value="PRESENCIAL">Presencial</option><option value="VIRTUAL">Virtual</option><option value="HIBRIDA">Híbrida</option></select></label>
                    <label><span>Hora de inicio</span><input type="time" value={activityForm.hora_inicio} onChange={(event) => setActivityForm((current) => ({ ...current, hora_inicio: event.target.value }))} disabled={!planAllowsActivities || saving} /></label>
                    <label><span>Hora de fin</span><input type="time" value={activityForm.hora_fin} onChange={(event) => setActivityForm((current) => ({ ...current, hora_fin: event.target.value }))} disabled={!planAllowsActivities || saving} /></label>
                    <label><span>Descanso (minutos)</span><input type="number" min="0" max="600" step="5" value={activityForm.descanso_minutos} onChange={(event) => setActivityForm((current) => ({ ...current, descanso_minutos: event.target.value }))} disabled={!planAllowsActivities || saving || !activityForm.hora_inicio} /></label>
                    <label><span>Horas manuales</span><input type="number" min="0.25" max="24" step="0.25" value={activityForm.horas} onChange={(event) => setActivityForm((current) => ({ ...current, horas: event.target.value }))} disabled={!planAllowsActivities || saving || Boolean(activityForm.hora_inicio)} placeholder={activityForm.hora_inicio ? 'Calculadas por jornada' : 'Ej. 8'} /></label>
                    <label className="is-wide"><span>Lugar o área</span><input maxLength={300} value={activityForm.lugar} onChange={(event) => setActivityForm((current) => ({ ...current, lugar: event.target.value }))} disabled={!planAllowsActivities || saving} /></label>
                    <label className="is-wide"><span>Actividad realizada</span><textarea rows={3} value={activityForm.descripcion} onChange={(event) => setActivityForm((current) => ({ ...current, descripcion: event.target.value }))} disabled={!planAllowsActivities || saving} /></label>
                    <label><span>Nombre de evidencia</span><input value={activityForm.evidencia_nombre} onChange={(event) => setActivityForm((current) => ({ ...current, evidencia_nombre: event.target.value }))} disabled={!planAllowsActivities || saving} placeholder="Ej. Informe semanal 1" /></label>
                    <label><span>Enlace de evidencia</span><input type="url" value={activityForm.evidencia_url} onChange={(event) => setActivityForm((current) => ({ ...current, evidencia_url: event.target.value }))} disabled={!planAllowsActivities || saving} placeholder="https://" /></label>
                    <div className="practicas-ops__form-actions is-wide">
                      <button type="button" className="primary-action" onClick={() => void submitActivity()} disabled={!planAllowsActivities || saving}>Registrar actividad</button>
                    </div>
                    {!planAllowsActivities ? <p className="practicas-ops__notice is-wide">La bitácora se habilitará cuando el responsable apruebe el plan.</p> : null}
                  </div>
                ) : null}
                <div className="practicas-activity-list">
                  {detail.actividades.length ? detail.actividades.map((activity) => (
                    <article key={activity.actividad_id}>
                      <div className="practicas-activity-list__date"><strong>{dateValue(activity.fecha_actividad)}</strong><span>{Number(activity.horas).toFixed(2)} h</span></div>
                      <div><strong>{activity.descripcion}</strong><small>{activity.hora_inicio && activity.hora_fin ? `${textValue(activity.hora_inicio).slice(0, 5)} a ${textValue(activity.hora_fin).slice(0, 5)} · ${activity.descanso_minutos || 0} min. de descanso` : 'Horas declaradas manualmente'}{activity.modalidad ? ` · ${activity.modalidad.toLowerCase()}` : ''}{activity.lugar ? ` · ${activity.lugar}` : ''}</small><small>{activity.evidencia_nombre || 'Sin evidencia vinculada'}</small>{activity.observacion_revision ? <p>{activity.observacion_revision}</p> : null}</div>
                      <div className="practicas-activity-list__state"><span className={requirementClass(activity.estado_revision === 'VALIDADO' ? 'COMPLETO' : activity.estado_revision === 'PENDIENTE' ? 'EN_REVISION' : 'PENDIENTE')}>{activity.estado_revision}</span>{activity.evidencia_url ? <a href={activity.evidencia_url} target="_blank" rel="noreferrer">Ver evidencia</a> : null}</div>
                      {detail.permisos.puede_revisar_actividad && !processClosed && activity.estado_revision !== 'VALIDADO' ? (
                        <div className="practicas-activity-list__actions">
                          {reviewActivityId === activity.actividad_id ? (
                            <>
                              <textarea rows={2} value={reviewObservation} onChange={(event) => setReviewObservation(event.target.value)} placeholder="Observación para el estudiante" />
                              <button type="button" className="ghost-button" onClick={() => void submitActivityReview(activity.actividad_id, 'OBSERVADO')} disabled={saving}>Observar</button>
                              <button type="button" className="ghost-button" onClick={() => void submitActivityReview(activity.actividad_id, 'RECHAZADO')} disabled={saving}>Rechazar</button>
                              <button type="button" className="secondary-action" onClick={() => { setReviewActivityId(null); setReviewObservation('') }} disabled={saving}>Cancelar</button>
                            </>
                          ) : (
                            <>
                              <button type="button" className="primary-action" onClick={() => void submitActivityReview(activity.actividad_id, 'VALIDADO')} disabled={saving}>Validar</button>
                              <button type="button" className="ghost-button" onClick={() => setReviewActivityId(activity.actividad_id)} disabled={saving}>Devolver</button>
                            </>
                          )}
                        </div>
                      ) : null}
                    </article>
                  )) : <p className="practicas-ops__empty">Todavía no existen actividades registradas.</p>}
                </div>
              </section>

              {process === 'VIN' ? (
                <section className="practicas-ops__section">
                  <header><span>Resultados</span><h3>Metas e indicadores de vinculación</h3></header>
                  <div className="practicas-indicator-list">
                    {detail.indicadores.length ? detail.indicadores.map((indicator) => (
                      <article key={indicator.indicador_id}>
                        <div>
                          <strong>{indicator.nombre}</strong>
                          <small>{indicator.unidad_medida}</small>
                        </div>
                        <div><span>Meta</span><strong>{Number(indicator.meta || 0).toFixed(2)}</strong></div>
                        <div><span>Resultado</span><strong>{indicator.resultado === null || indicator.resultado === undefined ? 'Pendiente' : Number(indicator.resultado).toFixed(2)}</strong></div>
                        {indicator.evidencia_url ? <a href={indicator.evidencia_url} target="_blank" rel="noreferrer">Ver evidencia</a> : <span>Sin evidencia</span>}
                        {detail.permisos.puede_editar_plan && !processClosed ? (
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => setIndicatorForm({
                              indicador_id: String(indicator.indicador_id),
                              nombre: indicator.nombre,
                              unidad_medida: indicator.unidad_medida,
                              meta: String(indicator.meta),
                              resultado: indicator.resultado === null || indicator.resultado === undefined ? '' : String(indicator.resultado),
                              evidencia_url: indicator.evidencia_url || '',
                              observacion: indicator.observacion || '',
                            })}
                            disabled={saving}
                          >
                            Editar
                          </button>
                        ) : null}
                      </article>
                    )) : <p className="practicas-ops__empty">El responsable aún no ha registrado metas para este expediente.</p>}
                  </div>
                  {detail.permisos.puede_editar_plan && !processClosed ? (
                    <div className="practicas-ops__form-grid practicas-indicator-form">
                      <label><span>Indicador</span><input maxLength={300} value={indicatorForm.nombre} onChange={(event) => setIndicatorForm((current) => ({ ...current, nombre: event.target.value }))} /></label>
                      <label><span>Unidad de medida</span><input maxLength={80} value={indicatorForm.unidad_medida} onChange={(event) => setIndicatorForm((current) => ({ ...current, unidad_medida: event.target.value }))} placeholder="Ej. personas" /></label>
                      <label><span>Meta</span><input type="number" min="0" step="0.01" value={indicatorForm.meta} onChange={(event) => setIndicatorForm((current) => ({ ...current, meta: event.target.value }))} /></label>
                      <label><span>Resultado alcanzado</span><input type="number" min="0" step="0.01" value={indicatorForm.resultado} onChange={(event) => setIndicatorForm((current) => ({ ...current, resultado: event.target.value }))} /></label>
                      <label className="is-wide"><span>Enlace de evidencia</span><input type="url" maxLength={1000} value={indicatorForm.evidencia_url} onChange={(event) => setIndicatorForm((current) => ({ ...current, evidencia_url: event.target.value }))} placeholder="https://" /></label>
                      <label className="is-wide"><span>Observación</span><textarea rows={2} maxLength={1000} value={indicatorForm.observacion} onChange={(event) => setIndicatorForm((current) => ({ ...current, observacion: event.target.value }))} /></label>
                      <div className="practicas-ops__form-actions is-wide">
                        {indicatorForm.indicador_id ? <button type="button" className="ghost-button" onClick={() => setIndicatorForm({ indicador_id: '', nombre: '', unidad_medida: '', meta: '', resultado: '', evidencia_url: '', observacion: '' })} disabled={saving}>Cancelar edición</button> : null}
                        <button type="button" className="primary-action" onClick={() => void submitIndicator()} disabled={saving}>{indicatorForm.indicador_id ? 'Actualizar indicador' : 'Agregar indicador'}</button>
                      </div>
                    </div>
                  ) : null}

                  <div className="practicas-vin-results">
                    <header><span>Impacto</span><h4>Beneficiarios y resultado alcanzado</h4></header>
                    {detail.resultado_vinculacion ? (
                      <p className={`practicas-ops__notice is-${detail.resultado_vinculacion.estado.toLowerCase()}`}>
                        <strong>{detail.resultado_vinculacion.beneficiarios_reales} beneficiario(s) reales · {detail.resultado_vinculacion.estado}</strong><br />
                        {detail.resultado_vinculacion.resumen_impacto}
                      </p>
                    ) : null}
                    {detail.permisos.puede_registrar_resultado && !processClosed ? (
                      <div className="practicas-ops__form-grid">
                        <label><span>Beneficiarios reales</span><input type="number" min="0" value={vinculationResultForm.beneficiarios_reales} onChange={(event) => setVinculationResultForm((current) => ({ ...current, beneficiarios_reales: event.target.value }))} /></label>
                        <label><span>Enlace de evidencia</span><input type="url" maxLength={1000} value={vinculationResultForm.evidencia_url} onChange={(event) => setVinculationResultForm((current) => ({ ...current, evidencia_url: event.target.value }))} placeholder="https://" /></label>
                        <label className="is-wide"><span>Resumen del impacto</span><textarea rows={4} maxLength={10000} value={vinculationResultForm.resumen_impacto} onChange={(event) => setVinculationResultForm((current) => ({ ...current, resumen_impacto: event.target.value }))} /></label>
                        <label className="is-wide"><span>Observación</span><textarea rows={2} maxLength={1500} value={vinculationResultForm.observacion} onChange={(event) => setVinculationResultForm((current) => ({ ...current, observacion: event.target.value }))} /></label>
                        <div className="practicas-ops__form-actions is-wide">
                          <button type="button" className="ghost-button" onClick={() => void submitVinculationResult(false)} disabled={saving}>Guardar resultado</button>
                          {!isStudent ? <button type="button" className="primary-action" onClick={() => void submitVinculationResult(true)} disabled={saving}>Validar resultado</button> : null}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="practicas-vin-products">
                    <header><span>Entregables</span><h4>Productos de vinculación</h4></header>
                    <div className="practicas-product-list">
                      {detail.productos_vinculacion.length ? detail.productos_vinculacion.map((product) => (
                        <article key={product.producto_id}>
                          <div><strong>{product.nombre}</strong><small>{Number(product.cantidad).toFixed(2)} {product.unidad_medida}</small><p>{product.descripcion || 'Sin descripción adicional.'}</p>{product.observacion_revision ? <p>{product.observacion_revision}</p> : null}</div>
                          <div className="practicas-activity-list__state"><span className={requirementClass(product.estado_revision === 'VALIDADO' ? 'COMPLETO' : product.estado_revision === 'PENDIENTE' ? 'EN_REVISION' : 'PENDIENTE')}>{product.estado_revision}</span>{product.evidencia_url ? <a href={product.evidencia_url} target="_blank" rel="noreferrer">Ver evidencia</a> : null}</div>
                          {!processClosed && detail.permisos.puede_registrar_resultado && (product.estado_revision !== 'VALIDADO' || !isStudent) ? <button type="button" className="ghost-button" onClick={() => setVinculationProductForm({ producto_id: String(product.producto_id), nombre: product.nombre, descripcion: product.descripcion || '', cantidad: String(product.cantidad), unidad_medida: product.unidad_medida, evidencia_url: product.evidencia_url || '' })} disabled={saving}>Editar</button> : null}
                          {!processClosed && detail.permisos.puede_revisar_actividad && product.estado_revision !== 'VALIDADO' ? (
                            <div className="practicas-activity-list__actions">
                              {productReviewId === product.producto_id ? <><textarea rows={2} value={productReviewObservation} onChange={(event) => setProductReviewObservation(event.target.value)} placeholder="Observación del responsable" /><button type="button" className="ghost-button" onClick={() => void submitVinculationProductReview(product.producto_id, 'OBSERVADO')} disabled={saving}>Observar</button><button type="button" className="ghost-button" onClick={() => void submitVinculationProductReview(product.producto_id, 'RECHAZADO')} disabled={saving}>Rechazar</button></> : <><button type="button" className="primary-action" onClick={() => void submitVinculationProductReview(product.producto_id, 'VALIDADO')} disabled={saving}>Validar</button><button type="button" className="ghost-button" onClick={() => setProductReviewId(product.producto_id)} disabled={saving}>Devolver</button></>}
                            </div>
                          ) : null}
                        </article>
                      )) : <p className="practicas-ops__empty">No existen productos registrados.</p>}
                    </div>
                    {detail.permisos.puede_registrar_resultado && !processClosed ? (
                      <div className="practicas-ops__form-grid practicas-product-form">
                        <label><span>Producto</span><input maxLength={300} value={vinculationProductForm.nombre} onChange={(event) => setVinculationProductForm((current) => ({ ...current, nombre: event.target.value }))} /></label>
                        <label><span>Cantidad</span><input type="number" min="0" step="0.01" value={vinculationProductForm.cantidad} onChange={(event) => setVinculationProductForm((current) => ({ ...current, cantidad: event.target.value }))} /></label>
                        <label><span>Unidad de medida</span><input maxLength={80} value={vinculationProductForm.unidad_medida} onChange={(event) => setVinculationProductForm((current) => ({ ...current, unidad_medida: event.target.value }))} /></label>
                        <label><span>Enlace de evidencia</span><input type="url" maxLength={1000} value={vinculationProductForm.evidencia_url} onChange={(event) => setVinculationProductForm((current) => ({ ...current, evidencia_url: event.target.value }))} /></label>
                        <label className="is-wide"><span>Descripción</span><textarea rows={3} maxLength={1500} value={vinculationProductForm.descripcion} onChange={(event) => setVinculationProductForm((current) => ({ ...current, descripcion: event.target.value }))} /></label>
                        <div className="practicas-ops__form-actions is-wide">
                          {vinculationProductForm.producto_id ? <button type="button" className="ghost-button" onClick={() => setVinculationProductForm({ producto_id: '', nombre: '', descripcion: '', cantidad: '', unidad_medida: '', evidencia_url: '' })} disabled={saving}>Cancelar edición</button> : null}
                          <button type="button" className="primary-action" onClick={() => void submitVinculationProduct()} disabled={saving}>{vinculationProductForm.producto_id ? 'Actualizar producto' : 'Agregar producto'}</button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </section>
              ) : null}

              <section className="practicas-ops__section">
                <header><span>Expediente</span><h3>Documentos obligatorios</h3></header>
                <div className="practicas-document-checklist">
                  {detail.documentos.map((document) => (
                    <article key={document.Codigo} className={document.Validado ? 'is-complete' : document.Cargado ? 'is-review' : 'is-pending'}>
                      <span>{document.Validado ? 'Listo' : document.Cargado ? 'Revisión' : 'Pendiente'}</span>
                      <div><strong>{document.Nombre || document.Codigo}</strong><small>{document.NombreArchivo || 'Archivo no cargado'}</small></div>
                      {document.UrlArchivo || document.RutaArchivo ? <a href={document.UrlArchivo || document.RutaArchivo || '#'} target="_blank" rel="noreferrer">Ver</a> : null}
                    </article>
                  ))}
                </div>
                {canOpenDocuments ? (
                  <div className="practicas-ops__form-actions">
                    <button type="button" className="secondary-action" onClick={() => onOpenDocuments(textValue(selectedDashboardItem?.Cedula))} disabled={!textValue(selectedDashboardItem?.Cedula)}>
                      {canUploadDocuments ? 'Cargar o revisar documentos' : 'Consultar documentos'}
                    </button>
                  </div>
                ) : null}
              </section>

              <section className="practicas-ops__section practicas-evaluation-section">
                <header><span>Evaluación</span><h3>Revisión y calificación final</h3></header>
                <div className="practicas-actor-evaluations">
                  <div className="practicas-actor-evaluations__list">
                    {detail.evaluaciones_actores.length ? detail.evaluaciones_actores.map((item) => (
                      <article key={item.evaluacion_actor_id}>
                        <span>{item.rol_evaluador === 'DOCENTE_ACADEMICO' ? 'Docente académico' : item.rol_evaluador === 'TUTOR_EMPRESARIAL' ? 'Tutor empresarial' : 'Autoevaluación'}</span>
                        <strong>{Number(item.calificacion).toFixed(2)} / 10</strong>
                        <small>Peso {Number(item.peso).toFixed(0)}% · {item.estado}</small>
                        <small>{item.evaluador_nombre || 'Evaluador identificado por sesión'}</small>
                      </article>
                    )) : <p className="practicas-ops__empty">Aún no se registran evaluaciones de los actores del proceso.</p>}
                  </div>
                  {detail.permisos.puede_registrar_evaluacion_actor && !processClosed && !['PENDIENTE_CALIFICACION', 'CALIFICADA'].includes(evaluationState) ? (
                    <div className="practicas-ops__form-grid practicas-actor-form">
                      <label><span>Tipo de evaluación</span><select value={actorEvaluationForm.rol_evaluador} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, rol_evaluador: event.target.value }))} disabled={isStudent}><option value={isStudent ? 'AUTOEVALUACION' : 'DOCENTE_ACADEMICO'}>{isStudent ? 'Autoevaluación del estudiante' : 'Docente académico'}</option>{!isStudent && process === 'PPF' ? <option value="TUTOR_EMPRESARIAL">Tutor empresarial</option> : null}</select></label>
                      <label><span>Calificación sobre 10</span><input type="number" min="0" max="10" step="0.01" value={actorEvaluationForm.calificacion} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, calificacion: event.target.value }))} /></label>
                      {actorEvaluationForm.rol_evaluador === 'TUTOR_EMPRESARIAL' ? <><label><span>Nombre del tutor</span><input maxLength={250} value={actorEvaluationForm.evaluador_nombre} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, evaluador_nombre: event.target.value }))} /></label><label><span>Correo del tutor</span><input type="email" maxLength={250} value={actorEvaluationForm.evaluador_correo} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, evaluador_correo: event.target.value }))} /></label></> : null}
                      <label className="is-wide"><span>Observación</span><textarea rows={3} maxLength={1500} value={actorEvaluationForm.observacion} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, observacion: event.target.value }))} /></label>
                      <label className="is-wide"><span>Enlace de respaldo</span><input type="url" maxLength={1000} value={actorEvaluationForm.evidencia_url} onChange={(event) => setActorEvaluationForm((current) => ({ ...current, evidencia_url: event.target.value }))} placeholder="https://" /></label>
                      <div className="practicas-ops__form-actions is-wide"><button type="button" className="primary-action" onClick={() => void submitActorEvaluation()} disabled={saving}>Guardar evaluación</button></div>
                    </div>
                  ) : null}
                  <p className="practicas-grade-calculation">
                    <span>Calificación ponderada</span>
                    <strong>{calculatedGrade === null || calculatedGrade === undefined ? 'Pendiente' : `${Number(calculatedGrade).toFixed(2)} / 10`}</strong>
                    <small>{detail.calculo_calificacion.roles_faltantes.length ? `Falta: ${detail.calculo_calificacion.roles_faltantes.join(', ')}` : 'Cálculo listo con las evaluaciones obligatorias registradas.'}</small>
                  </p>
                </div>
                <dl className={`practicas-evaluation-summary is-${evaluationResult.toLowerCase()}`}>
                  <div><dt>Etapa actual</dt><dd>{evaluationStageLabel(evaluationState)}</dd></div>
                  <div><dt>Resultado</dt><dd>{evaluationResultLabel(evaluationResult)}</dd></div>
                  <div><dt>Calificación</dt><dd>{detail.evaluacion?.calificacion === null || detail.evaluacion?.calificacion === undefined ? 'Pendiente' : `${Number(detail.evaluacion.calificacion).toFixed(2)} / 10`}</dd></div>
                  <div><dt>Nota mínima</dt><dd>{minimumGrade.toFixed(2)} / 10</dd></div>
                </dl>
                <p className="practicas-ops__storage-note">La calificación y su historial se guardan en {detail.almacenamiento.base_datos}.{detail.almacenamiento.tabla_calificacion}.</p>

                {detail.evaluacion?.observacion_revision ? (
                  <p className="practicas-ops__notice"><strong>Observación de revisión:</strong> {detail.evaluacion.observacion_revision}</p>
                ) : null}
                {detail.evaluacion?.observacion_calificacion ? (
                  <p className="practicas-ops__notice"><strong>Observación de calificación:</strong> {detail.evaluacion.observacion_calificacion}</p>
                ) : null}

                {!processClosed && evaluationState === 'PENDIENTE_REVISION' && detail.permisos.puede_enviar_revision ? (
                  <div className="practicas-evaluation-actions">
                    <label><span>Comentario para la revisión</span><textarea rows={3} maxLength={1500} value={evaluationForm.observacion} onChange={(event) => setEvaluationForm((current) => ({ ...current, observacion: event.target.value }))} placeholder="Detalle opcional para el responsable" /></label>
                    <button type="button" className="primary-action" onClick={() => void submitEvaluation('ENVIAR_REVISION')} disabled={saving}>Enviar expediente a revisión</button>
                  </div>
                ) : null}

                {!processClosed && evaluationState === 'EN_REVISION' && detail.permisos.puede_calificar ? (
                  <div className="practicas-evaluation-actions">
                    <label><span>Observación de revisión</span><textarea rows={3} maxLength={1500} value={evaluationForm.observacion} onChange={(event) => setEvaluationForm((current) => ({ ...current, observacion: event.target.value }))} placeholder="Registre correcciones o el cierre de la revisión" /></label>
                    <div className="practicas-ops__form-actions">
                      <button type="button" className="ghost-button" onClick={() => void submitEvaluation('DEVOLVER')} disabled={saving}>Devolver para corrección</button>
                      <button type="button" className="primary-action" onClick={() => void submitEvaluation('HABILITAR_CALIFICACION')} disabled={saving}>Finalizar revisión y esperar calificación</button>
                    </div>
                  </div>
                ) : null}

                {!processClosed && evaluationState === 'PENDIENTE_CALIFICACION' && detail.permisos.puede_calificar ? (
                  <div className="practicas-evaluation-actions">
                    <div className="practicas-evaluation-grade">
                      <label><span>Calificación final sobre 10</span><input type="number" min="0" max="10" step="0.01" value={evaluationForm.calificacion} onChange={(event) => setEvaluationForm((current) => ({ ...current, calificacion: event.target.value }))} readOnly={detail.calculo_calificacion.usa_evaluaciones_actores} /></label>
                      <div><span>Resultado calculado</span><strong>{evaluationForm.calificacion.trim() ? (numberValue(evaluationForm.calificacion) >= minimumGrade ? 'Aprobado' : 'Reprobado') : 'Pendiente'}</strong></div>
                    </div>
                    <label><span>Observación de calificación</span><textarea rows={3} maxLength={1500} value={evaluationForm.observacion} onChange={(event) => setEvaluationForm((current) => ({ ...current, observacion: event.target.value }))} placeholder={`Obligatoria cuando la calificación es menor a ${minimumGrade.toFixed(2)}`} /></label>
                    <div className="practicas-ops__form-actions">
                      <button type="button" className="ghost-button" onClick={() => void submitEvaluation('DEVOLVER')} disabled={saving}>Devolver a revisión</button>
                      <button type="button" className="primary-action" onClick={() => void submitEvaluation('CALIFICAR')} disabled={saving || !evaluationForm.calificacion.trim()}>Registrar calificación</button>
                    </div>
                  </div>
                ) : null}

                {evaluationState === 'EN_REVISION' && !detail.permisos.puede_calificar ? <p className="practicas-ops__notice">El responsable está revisando el expediente.</p> : null}
                {evaluationState === 'PENDIENTE_CALIFICACION' && !detail.permisos.puede_calificar ? <p className="practicas-ops__notice">La revisión concluyó. El expediente está a la espera de la calificación del responsable.</p> : null}
                {evaluationState === 'CALIFICADA' ? (
                  <p className={`practicas-evaluation-result is-${evaluationResult.toLowerCase()}`}>
                    <strong>{evaluationResultLabel(evaluationResult)}</strong>
                    <span>{evaluationResult === 'APROBADO' ? 'El proceso puede avanzar al cierre y conciliación con Titulación.' : 'El proceso no cumple el requisito y no será enviado a Titulación.'}</span>
                  </p>
                ) : null}
              </section>

              {detail.permisos.puede_cerrar ? (
                <section className="practicas-ops__section">
                  <header><span>Cierre</span><h3>Confirmación y resultado del proceso</h3></header>
                  <div className="practicas-ops__closure">
                    <label><input type="checkbox" checked={closureForm.supervision_realizada} onChange={(event) => setClosureForm((current) => ({ ...current, supervision_realizada: event.target.checked }))} disabled={saving || processClosed} /><span>Supervisión realizada</span></label>
                    <label><input type="checkbox" checked={closureForm.informe_final_validado} onChange={(event) => setClosureForm((current) => ({ ...current, informe_final_validado: event.target.checked }))} disabled={saving || processClosed} /><span>Informe final validado</span></label>
                    <label><input type="checkbox" checked={closureForm.acta_aceptacion_validada} onChange={(event) => setClosureForm((current) => ({ ...current, acta_aceptacion_validada: event.target.checked }))} disabled={saving || processClosed} /><span>Acta de aceptación validada</span></label>
                    <label><input type="checkbox" checked={closureForm.certificado_emitido} onChange={(event) => setClosureForm((current) => ({ ...current, certificado_emitido: event.target.checked }))} disabled={saving || processClosed || evaluationResult === 'REPROBADO'} /><span>{evaluationResult === 'REPROBADO' ? 'Certificado no aplicable por reprobación' : 'Certificado emitido'}</span></label>
                    <label><span>Calificación final</span><input type="number" value={closureForm.evaluacion_entidad} disabled /></label>
                    <label className="is-wide"><span>Observación de cierre</span><textarea rows={3} value={closureForm.observacion} onChange={(event) => setClosureForm((current) => ({ ...current, observacion: event.target.value }))} disabled={saving || processClosed} /></label>
                    <div className="practicas-ops__form-actions is-wide">
                      <button type="button" className="ghost-button" onClick={() => void submitClosure(false)} disabled={saving || processClosed}>Guardar seguimiento</button>
                      <button type="button" className="primary-action" onClick={() => void submitClosure(true)} disabled={saving || Boolean(detail.cierre?.fecha_cierre) || evaluationState !== 'CALIFICADA'}>
                        {detail.cierre?.fecha_cierre ? 'Proceso cerrado' : evaluationState !== 'CALIFICADA' ? 'Esperando calificación' : evaluationResult === 'APROBADO' ? 'Cerrar aprobado y conciliar' : 'Cerrar proceso reprobado'}
                      </button>
                    </div>
                  </div>
                </section>
              ) : null}

              {detail.historial_calificacion.length ? (
                <details className="practicas-ops__history">
                  <summary>Historial de revisión y calificación ({detail.historial_calificacion.length})</summary>
                  <div>
                    {detail.historial_calificacion.map((item) => (
                      <article key={item.historial_id}>
                        <span>{item.accion}</span>
                        <div><strong>{item.estado} · {item.resultado}</strong><small>{item.calificacion === null || item.calificacion === undefined ? 'Sin calificación' : `${Number(item.calificacion).toFixed(2)} / 10`} · {item.origen_calificacion || 'Transición de revisión'}</small></div>
                        <div><strong>{item.usuario}</strong><small>{dateTimeLabel(item.fecha)}</small></div>
                      </article>
                    ))}
                  </div>
                </details>
              ) : null}

              {detail.permisos.puede_reabrir && processClosed ? (
                <section className="practicas-ops__section practicas-reopen-section">
                  <header><span>Corrección controlada</span><h3>Reabrir expediente cerrado</h3></header>
                  <p className="practicas-ops__notice">La calificación vigente se retirará del proceso, pero conservará su versión completa en el historial de la base complementaria.</p>
                  <label><span>Motivo de reapertura</span><textarea rows={3} maxLength={1500} value={reopenForm.motivo} onChange={(event) => setReopenForm((current) => ({ ...current, motivo: event.target.value }))} /></label>
                  <label className="practicas-reopen-confirm"><input type="checkbox" checked={reopenForm.confirmar_reversion_titulacion} onChange={(event) => setReopenForm((current) => ({ ...current, confirmar_reversion_titulacion: event.target.checked }))} /><span>Confirmo que se revisará la conciliación previa con Titulación cuando corresponda.</span></label>
                  <div className="practicas-ops__form-actions"><button type="button" className="danger-action" onClick={() => void reopenRecord()} disabled={saving || reopenForm.motivo.trim().length < 10}>Reabrir expediente</button></div>
                </section>
              ) : null}
            </>
          ) : null}
        </main>
      </div>

      {isAdmin ? (
        <details className="practicas-ops__catalog" open={catalogOnly}>
          <summary>Catálogos y convenios del proceso</summary>
          <div className="practicas-ops__catalog-grid">
            <section className="practicas-config-section">
              <header><span>Reglas generales</span><h3>Requisitos y cálculo de calificación</h3></header>
              <p className="practicas-ops__storage-note">Persistencia: {catalog.almacenamiento.base_datos}.{catalog.almacenamiento.tabla_calificacion}</p>
              <label><span>Horas requeridas</span><input type="number" min="1" max="10000" step="1" value={configurationForm.horas_requeridas} onChange={(event) => setConfigurationForm((current) => ({ ...current, horas_requeridas: event.target.value }))} /></label>
              <label><span>Documentos obligatorios del flujo</span><input type="number" value={configurationForm.documentos_requeridos} readOnly aria-readonly="true" /></label>
              <label><span>Nota mínima sobre 10</span><input type="number" min="0" max="10" step="0.01" value={configurationForm.nota_minima_aprobacion} onChange={(event) => setConfigurationForm((current) => ({ ...current, nota_minima_aprobacion: event.target.value }))} /></label>
              <div className="practicas-config-checks">
                <label><input type="checkbox" checked={configurationForm.requiere_evaluacion_docente} onChange={(event) => setConfigurationForm((current) => ({ ...current, requiere_evaluacion_docente: event.target.checked, peso_docente: event.target.checked ? Number(current.peso_docente) > 0 ? current.peso_docente : '100' : '0' }))} /><span>Evaluación docente</span></label>
                <label><input type="checkbox" checked={configurationForm.requiere_evaluacion_tutor} onChange={(event) => setConfigurationForm((current) => ({ ...current, requiere_evaluacion_tutor: event.target.checked, peso_tutor: event.target.checked ? Number(current.peso_tutor) > 0 ? current.peso_tutor : '40' : '0' }))} /><span>Evaluación del tutor</span></label>
                <label><input type="checkbox" checked={configurationForm.requiere_autoevaluacion} onChange={(event) => setConfigurationForm((current) => ({ ...current, requiere_autoevaluacion: event.target.checked, peso_autoevaluacion: event.target.checked ? Number(current.peso_autoevaluacion) > 0 ? current.peso_autoevaluacion : '10' : '0' }))} /><span>Autoevaluación</span></label>
                {process === 'VIN' ? <label><input type="checkbox" checked={configurationForm.requiere_resultado_vinculacion} onChange={(event) => setConfigurationForm((current) => ({ ...current, requiere_resultado_vinculacion: event.target.checked }))} /><span>Impacto y productos validados</span></label> : null}
              </div>
              <label><span>Peso docente (%)</span><input type="number" min="0" max="100" step="1" value={configurationForm.peso_docente} onChange={(event) => setConfigurationForm((current) => ({ ...current, peso_docente: event.target.value }))} disabled={!configurationForm.requiere_evaluacion_docente} /></label>
              <label><span>Peso tutor (%)</span><input type="number" min="0" max="100" step="1" value={configurationForm.peso_tutor} onChange={(event) => setConfigurationForm((current) => ({ ...current, peso_tutor: event.target.value }))} disabled={!configurationForm.requiere_evaluacion_tutor} /></label>
              <label><span>Peso autoevaluación (%)</span><input type="number" min="0" max="100" step="1" value={configurationForm.peso_autoevaluacion} onChange={(event) => setConfigurationForm((current) => ({ ...current, peso_autoevaluacion: event.target.value }))} disabled={!configurationForm.requiere_autoevaluacion} /></label>
              <button type="button" className="primary-action" onClick={() => void saveConfiguration()} disabled={saving}>Guardar reglas</button>
            </section>
            <section>
              <header><span>Catálogo</span><h3>Nueva entidad receptora</h3></header>
              <label><span>Nombre</span><input value={entityForm.nombre} onChange={(event) => setEntityForm((current) => ({ ...current, nombre: event.target.value }))} /></label>
              <label><span>RUC</span><input value={entityForm.ruc} onChange={(event) => setEntityForm((current) => ({ ...current, ruc: event.target.value }))} /></label>
              <label><span>Tipo de entidad</span><input value={entityForm.tipo_entidad} onChange={(event) => setEntityForm((current) => ({ ...current, tipo_entidad: event.target.value }))} /></label>
              <label><span>Sector económico</span><input value={entityForm.sector_economico} onChange={(event) => setEntityForm((current) => ({ ...current, sector_economico: event.target.value }))} /></label>
              <label><span>Contacto</span><input value={entityForm.contacto_nombre} onChange={(event) => setEntityForm((current) => ({ ...current, contacto_nombre: event.target.value }))} /></label>
              <label><span>Correo</span><input type="email" value={entityForm.contacto_correo} onChange={(event) => setEntityForm((current) => ({ ...current, contacto_correo: event.target.value }))} /></label>
              <label><span>Teléfono</span><input value={entityForm.contacto_telefono} onChange={(event) => setEntityForm((current) => ({ ...current, contacto_telefono: event.target.value }))} /></label>
              <button type="button" className="primary-action" onClick={() => void saveEntity()} disabled={saving}>Registrar entidad</button>
            </section>
            <section>
              <header><span>Vigencia</span><h3>Nuevo convenio</h3></header>
              <label><span>Entidad</span><select value={agreementForm.entidad_id} onChange={(event) => setAgreementForm((current) => ({ ...current, entidad_id: event.target.value }))}><option value="">Seleccionar</option>{activeEntities.map((item) => <option key={item.entidad_id} value={item.entidad_id}>{item.nombre}</option>)}</select></label>
              <label><span>Código</span><input value={agreementForm.codigo_convenio} onChange={(event) => setAgreementForm((current) => ({ ...current, codigo_convenio: event.target.value }))} /></label>
              <label><span>Inicio</span><input type="date" value={agreementForm.fecha_inicio} onChange={(event) => setAgreementForm((current) => ({ ...current, fecha_inicio: event.target.value }))} /></label>
              <label><span>Fin</span><input type="date" value={agreementForm.fecha_fin} onChange={(event) => setAgreementForm((current) => ({ ...current, fecha_fin: event.target.value }))} /></label>
              <label><span>Objeto</span><textarea rows={3} value={agreementForm.objeto} onChange={(event) => setAgreementForm((current) => ({ ...current, objeto: event.target.value }))} /></label>
              <label><span>Enlace del convenio</span><input type="url" value={agreementForm.archivo_url} onChange={(event) => setAgreementForm((current) => ({ ...current, archivo_url: event.target.value }))} /></label>
              <button type="button" className="primary-action" onClick={() => void saveAgreement()} disabled={saving}>Registrar convenio</button>
            </section>
            {process === 'VIN' ? (
              <section>
                <header><span>Vinculación</span><h3>Nuevo proyecto</h3></header>
                <label><span>Código</span><input value={projectForm.codigo_proyecto} onChange={(event) => setProjectForm((current) => ({ ...current, codigo_proyecto: event.target.value }))} /></label>
                <label><span>Nombre</span><input value={projectForm.nombre} onChange={(event) => setProjectForm((current) => ({ ...current, nombre: event.target.value }))} /></label>
                <label><span>Línea de intervención</span><input value={projectForm.linea_intervencion} onChange={(event) => setProjectForm((current) => ({ ...current, linea_intervencion: event.target.value }))} /></label>
                <label><span>Entidad</span><select value={projectForm.entidad_id} onChange={(event) => setProjectForm((current) => ({ ...current, entidad_id: event.target.value }))}><option value="">Sin entidad</option>{activeEntities.map((item) => <option key={item.entidad_id} value={item.entidad_id}>{item.nombre}</option>)}</select></label>
                <label><span>Convenio</span><select value={projectForm.convenio_id} onChange={(event) => setProjectForm((current) => ({ ...current, convenio_id: event.target.value }))}><option value="">Sin convenio</option>{activeAgreements.map((item) => <option key={item.convenio_id} value={item.convenio_id}>{item.codigo_convenio}</option>)}</select></label>
                <label><span>Población objetivo</span><input value={projectForm.poblacion_objetivo} onChange={(event) => setProjectForm((current) => ({ ...current, poblacion_objetivo: event.target.value }))} /></label>
                <label><span>Beneficiarios previstos</span><input type="number" min="0" value={projectForm.beneficiarios_previstos} onChange={(event) => setProjectForm((current) => ({ ...current, beneficiarios_previstos: event.target.value }))} /></label>
                <label><span>Inicio</span><input type="date" value={projectForm.fecha_inicio} onChange={(event) => setProjectForm((current) => ({ ...current, fecha_inicio: event.target.value }))} /></label>
                <label><span>Fin</span><input type="date" value={projectForm.fecha_fin} onChange={(event) => setProjectForm((current) => ({ ...current, fecha_fin: event.target.value }))} /></label>
                <label><span>Objetivo general</span><textarea rows={3} value={projectForm.objetivo_general} onChange={(event) => setProjectForm((current) => ({ ...current, objetivo_general: event.target.value }))} /></label>
                <button type="button" className="primary-action" onClick={() => void saveProject()} disabled={saving}>Registrar proyecto</button>
              </section>
            ) : null}
          </div>
        </details>
      ) : null}

      {isAdmin ? (
        <details
          className="practicas-ops__audit"
          onToggle={(event) => {
            if (event.currentTarget.open && !auditItems.length) void loadAudit()
          }}
        >
          <summary>Auditoría de movimientos</summary>
          {auditLoading ? <p className="practicas-ops__empty">Cargando movimientos...</p> : (
            <div className="practicas-ops__audit-list">
              {auditItems.length ? auditItems.map((item) => (
                <article key={item.auditoria_id}>
                  <span>{item.accion}</span>
                  <div><strong>{item.entidad}</strong><small>{item.detalle || `Registro ${item.entidad_id || ''}`}</small></div>
                  <div><strong>{item.usuario}</strong><small>{dateTimeLabel(item.fecha)}</small></div>
                </article>
              )) : <p className="practicas-ops__empty">No existen movimientos operativos registrados.</p>}
            </div>
          )}
        </details>
      ) : null}
    </section>
  )
}
