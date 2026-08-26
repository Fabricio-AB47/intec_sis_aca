import { useEffect, useMemo, useState } from 'react'

import {
  analyzePortalTeacherContract,
  ApiError,
  fetchPortalTeacherContractDocument,
  fetchPortalTeacherContracts,
  fetchPortalTeacherCourses,
  signPortalTeacherContract,
  uploadPortalTeacherContract,
} from '../../lib/api'
import type {
  PortalTeacherContract,
  PortalTeacherContractAnalysis,
  PortalTeacherContractsResponse,
  PortalTeacherCourse,
} from '../../types/app'

type Props = { displayName: string }

type ContractCourseOption = {
  key: string
  label: string
  codAnioBasica: string
  codigoPeriodo: string
  codigoMateria: string
  codigoMateriaComun: string
  paralelo: string
  codJornada: number | null
  modalidad: 'REGULAR' | 'HOMOLOGACION'
  fechaInicio: string
  fechaFin: string
}

type UploadDraft = {
  numeroContrato: string
  fechaInicio: string
  fechaFin: string
  horasPlanificadas: string
  valorHora: string
  valorTotal: string
  responsableContratacion: string
  observacion: string
}

const money = new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' })

function formatMoney(value?: number | null) {
  return value == null ? 'No registrado' : money.format(value)
}

function formatDate(value?: string) {
  if (!value) return 'No registrada'
  const date = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('es-EC')
}

function textOrPending(value?: string) {
  return value?.trim() || 'No registrado'
}

function isHomologation(course: PortalTeacherCourse) {
  if (course.es_homologacion !== undefined) return course.es_homologacion
  return /homo|homolog|(^|\W)h($|\W)/i.test(`${course.tipo_periodo || ''} ${course.detalle_periodo || ''}`)
}

function exactCourseScopes(courses: PortalTeacherCourse[]): ContractCourseOption[] {
  const options = new Map<string, ContractCourseOption>()
  for (const groupedCourse of courses) {
    const scopes = groupedCourse.alcances_periodo?.length
      ? groupedCourse.alcances_periodo
      : groupedCourse.asignaciones?.length
        ? groupedCourse.asignaciones
        : [groupedCourse]

    for (const scope of scopes) {
      const periodCodes = scope.codigo_periodos?.length
        ? scope.codigo_periodos
        : scope.codigo_periodo
          ? [scope.codigo_periodo]
          : []
      const periodLabels = (scope.detalle_periodos || scope.detalle_periodo || '')
        .split(/\s+\/\s+/)
        .map((item) => item.trim())
        .filter(Boolean)
      const codAnioBasica = String(scope.cod_anio_basica || groupedCourse.cod_anio_basica || '').trim()
      const codigoMateria = String(
        scope.codigo_materias?.[0]
          || scope.codigo_materia
          || groupedCourse.codigo_materias?.[0]
          || groupedCourse.codigo_materia
          || scope.cod_materia
          || groupedCourse.cod_materia
          || '',
      ).trim()
      const codigoMateriaComun = String(
        scope.cod_materia
          || groupedCourse.cod_materia
          || scope.codigo_materia
          || groupedCourse.codigo_materia
          || codigoMateria,
      ).trim()
      const paralelo = String(scope.paralelo || groupedCourse.paralelo || '').trim()
      if (!codAnioBasica || !codigoMateria || !paralelo) continue

      periodCodes.forEach((periodCode, index) => {
        const codigoPeriodo = String(periodCode || '').trim()
        if (!codigoPeriodo) return
        const modalidad = isHomologation(scope) ? 'HOMOLOGACION' : 'REGULAR'
        const codJornada = scope.cod_jornada ?? groupedCourse.cod_jornada ?? null
        const key = [codAnioBasica, codigoPeriodo, codigoMateria, paralelo, codJornada ?? ''].join('|')
        if (options.has(key)) return
        options.set(key, {
          key,
          codAnioBasica,
          codigoPeriodo,
          codigoMateria,
          codigoMateriaComun,
          paralelo,
          codJornada,
          modalidad,
          fechaInicio: String(scope.fecha_inicio || groupedCourse.fecha_inicio || '').slice(0, 10),
          fechaFin: String(scope.fecha_fin || groupedCourse.fecha_fin || '').slice(0, 10),
          label: [
            modalidad === 'HOMOLOGACION' ? 'Homologación' : 'Regular',
            scope.nombre_materia || groupedCourse.nombre_materia || codigoMateria,
            scope.nombre_carrera || groupedCourse.nombre_carrera || `Carrera ${codAnioBasica}`,
            periodLabels[index] || scope.detalle_periodo || groupedCourse.detalle_periodo || codigoPeriodo,
            `Paralelo ${paralelo}`,
          ].join(' · '),
        })
      })
    }
  }
  return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label, 'es'))
}

function normalizedCode(value?: string | null) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/gi, '').toUpperCase()
}

function courseMatchesAnalysis(course: ContractCourseOption | null, analysis: PortalTeacherContractAnalysis | null) {
  if (!course || !analysis) return false
  if (analysis.modalidad_academica && course.modalidad !== analysis.modalidad_academica) return false
  const detectedCode = normalizedCode(analysis.codigo_materia)
  if (!detectedCode) return true
  return [course.codigoMateriaComun, course.codigoMateria].some((value) => normalizedCode(value) === detectedCode)
}

function initialUploadDraft(displayName: string): UploadDraft {
  return {
    numeroContrato: '',
    fechaInicio: '',
    fechaFin: '',
    horasPlanificadas: '0',
    valorHora: '0',
    valorTotal: '0',
    responsableContratacion: displayName,
    observacion: '',
  }
}

function safeFilePart(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase()
}

export function PortalDocenteContratosView({ displayName }: Readonly<Props>) {
  const [data, setData] = useState<PortalTeacherContractsResponse | null>(null)
  const [courses, setCourses] = useState<PortalTeacherCourse[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [operation, setOperation] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadDraft, setUploadDraft] = useState<UploadDraft>(() => initialUploadDraft(displayName))
  const [uploadCourseKey, setUploadCourseKey] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadFileKey, setUploadFileKey] = useState(0)
  const [uploadPreviewUrl, setUploadPreviewUrl] = useState('')
  const [uploadAnalysis, setUploadAnalysis] = useState<PortalTeacherContractAnalysis | null>(null)

  const [documentPreviewUrl, setDocumentPreviewUrl] = useState('')
  const [documentPreviewTitle, setDocumentPreviewTitle] = useState('')

  const [signOpen, setSignOpen] = useState(false)
  const [signPreviewUrl, setSignPreviewUrl] = useState('')
  const [certificate, setCertificate] = useState<File | null>(null)
  const [certificateKey, setCertificateKey] = useState(0)
  const [certificatePassword, setCertificatePassword] = useState('')
  const [showCertificatePassword, setShowCertificatePassword] = useState(false)
  const [signatureReason, setSignatureReason] = useState('Aceptación y firma de contrato docente')
  const [signatureLocation, setSignatureLocation] = useState('Quito, Ecuador')
  const [signatureContact, setSignatureContact] = useState('')
  const [signatureConsent, setSignatureConsent] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [contractsResponse, coursesResponse] = await Promise.all([
        fetchPortalTeacherContracts(),
        fetchPortalTeacherCourses(),
      ])
      setData(contractsResponse)
      setCourses(coursesResponse.items || [])
      setSignatureContact((current) => current || contractsResponse.teacher?.correo || '')
      setSelectedId((current) => contractsResponse.contracts.some((item) => item.contrato_id === current)
        ? current
        : contractsResponse.contracts[0]?.contrato_id ?? null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo cargar la información contractual')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  useEffect(() => () => {
    if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl)
  }, [uploadPreviewUrl])

  useEffect(() => () => {
    if (documentPreviewUrl) URL.revokeObjectURL(documentPreviewUrl)
  }, [documentPreviewUrl])

  useEffect(() => () => {
    if (signPreviewUrl) URL.revokeObjectURL(signPreviewUrl)
  }, [signPreviewUrl])

  const courseOptions = useMemo(() => exactCourseScopes(courses), [courses])
  const selectedUploadCourse = useMemo(
    () => courseOptions.find((item) => item.key === uploadCourseKey) || courseOptions[0] || null,
    [courseOptions, uploadCourseKey],
  )
  const selected = useMemo<PortalTeacherContract | null>(() => (
    data?.contracts.find((item) => item.contrato_id === selectedId) || null
  ), [data, selectedId])

  const totals = useMemo(() => {
    const classes = selected?.clases || []
    return {
      planned: classes.reduce((sum, item) => sum + Number(item.horas_planificadas || 0), 0),
      executed: classes.reduce((sum, item) => sum + Number(item.horas_ejecutadas || 0), 0),
      value: classes.reduce((sum, item) => sum + Number(item.valor_total_planificado || 0), 0),
    }
  }, [selected])

  const clearUploadFile = () => {
    if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl)
    setUploadPreviewUrl('')
    setUploadFile(null)
    setUploadAnalysis(null)
    setUploadFileKey((value) => value + 1)
  }

  const closeUpload = () => {
    if (operation === 'upload' || operation === 'analyze-contract') return
    clearUploadFile()
    setUploadOpen(false)
    setUploadDraft(initialUploadDraft(data?.teacher?.nombre || displayName))
  }

  const openUpload = () => {
    setError('')
    setMessage('')
    const firstCourse = courseOptions[0]
    setUploadDraft({
      ...initialUploadDraft(data?.teacher?.nombre || displayName),
      fechaInicio: firstCourse?.fechaInicio || '',
      fechaFin: firstCourse?.fechaFin || '',
    })
    setUploadCourseKey(firstCourse?.key || '')
    clearUploadFile()
    setUploadOpen(true)
  }

  const selectUploadCourse = (key: string) => {
    const course = courseOptions.find((item) => item.key === key)
    setUploadCourseKey(key)
    setUploadDraft((current) => ({
      ...current,
      fechaInicio: uploadAnalysis?.fecha_inicio || course?.fechaInicio || current.fechaInicio,
      fechaFin: uploadAnalysis?.fecha_fin || course?.fechaFin || current.fechaFin,
    }))
  }

  const selectUploadFile = async (file: File | null) => {
    if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl)
    setUploadFile(file)
    setUploadPreviewUrl(file ? URL.createObjectURL(file) : '')
    setUploadAnalysis(null)
    setError('')
    if (!file) return

    setOperation('analyze-contract')
    try {
      const analysis = await analyzePortalTeacherContract(file)
      const matchingCourse = courseOptions.find((course) => courseMatchesAnalysis(course, analysis))
        || courseOptions.find((course) => !analysis.modalidad_academica || course.modalidad === analysis.modalidad_academica)
        || courseOptions[0]
      setUploadAnalysis(analysis)
      if (matchingCourse) setUploadCourseKey(matchingCourse.key)
      setUploadDraft((current) => ({
        ...current,
        numeroContrato: analysis.numero_contrato || current.numeroContrato,
        fechaInicio: analysis.fecha_inicio || matchingCourse?.fechaInicio || current.fechaInicio,
        fechaFin: analysis.fecha_fin || matchingCourse?.fechaFin || current.fechaFin,
        valorTotal: analysis.valor_total != null ? String(analysis.valor_total) : current.valorTotal,
      }))
      if (analysis.codigo_materia && !courseOptions.some((course) => courseMatchesAnalysis(course, analysis))) {
        setError(`El contrato corresponde a ${analysis.codigo_materia}, pero no se encontró ese curso entre las asignaciones del docente.`)
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo analizar el contrato PDF')
    } finally {
      setOperation('')
    }
  }

  const submitUpload = async () => {
    if (!selectedUploadCourse) {
      setError('El docente no tiene una asignación académica válida para vincular el contrato.')
      return
    }
    if (!uploadFile) {
      setError('Seleccione el contrato en formato PDF.')
      return
    }
    if (!uploadAnalysis) {
      setError('Espere a que el sistema analice y valide el contrato seleccionado.')
      return
    }
    if (!courseMatchesAnalysis(selectedUploadCourse, uploadAnalysis)) {
      setError('El curso seleccionado no coincide con la materia o modalidad reconocida en el contrato.')
      return
    }
    if (!uploadDraft.numeroContrato.trim() || !uploadDraft.fechaInicio || !uploadDraft.fechaFin) {
      setError('Registre el número y las fechas del contrato.')
      return
    }
    setOperation('upload')
    setError('')
    setMessage('')
    try {
      const response = await uploadPortalTeacherContract({
        numeroContrato: uploadDraft.numeroContrato.trim(),
        codAnioBasica: selectedUploadCourse.codAnioBasica,
        codigoPeriodo: selectedUploadCourse.codigoPeriodo,
        codigoMateria: selectedUploadCourse.codigoMateria,
        paralelo: selectedUploadCourse.paralelo,
        codJornada: selectedUploadCourse.codJornada,
        modalidadAcademica: selectedUploadCourse.modalidad,
        fechaInicio: uploadDraft.fechaInicio,
        fechaFin: uploadDraft.fechaFin,
        horasPlanificadas: Number(uploadDraft.horasPlanificadas) || 0,
        valorHora: Number(uploadDraft.valorHora) || 0,
        valorTotal: Number(uploadDraft.valorTotal) || 0,
        responsableContratacion: uploadDraft.responsableContratacion.trim(),
        observacion: uploadDraft.observacion.trim(),
        contrato: uploadFile,
      })
      clearUploadFile()
      setUploadOpen(false)
      await load()
      setSelectedId(response.contrato_id)
      setMessage(response.message)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo adjuntar el contrato docente')
    } finally {
      setOperation('')
    }
  }

  const closeDocumentPreview = () => {
    if (documentPreviewUrl) URL.revokeObjectURL(documentPreviewUrl)
    setDocumentPreviewUrl('')
    setDocumentPreviewTitle('')
  }

  const previewContract = async (contract: PortalTeacherContract) => {
    setOperation(`preview-${contract.contrato_id}`)
    setError('')
    try {
      const blob = await fetchPortalTeacherContractDocument(contract.contrato_id)
      if (documentPreviewUrl) URL.revokeObjectURL(documentPreviewUrl)
      setDocumentPreviewUrl(URL.createObjectURL(blob))
      setDocumentPreviewTitle(contract.numero_contrato || `Contrato ${contract.contrato_id}`)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo abrir el contrato')
    } finally {
      setOperation('')
    }
  }

  const downloadContract = async (contract: PortalTeacherContract) => {
    setOperation(`download-${contract.contrato_id}`)
    setError('')
    try {
      const blob = await fetchPortalTeacherContractDocument(contract.contrato_id, { download: true })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `contrato-${safeFilePart(contract.numero_contrato || String(contract.contrato_id))}${contract.tiene_documento_firmado ? '-firmado' : ''}.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo descargar el contrato')
    } finally {
      setOperation('')
    }
  }

  const clearSignatureSecrets = () => {
    setCertificate(null)
    setCertificatePassword('')
    setShowCertificatePassword(false)
    setSignatureConsent(false)
    setCertificateKey((value) => value + 1)
  }

  const closeSign = () => {
    if (operation === 'sign') return
    if (signPreviewUrl) URL.revokeObjectURL(signPreviewUrl)
    setSignPreviewUrl('')
    clearSignatureSecrets()
    setSignOpen(false)
  }

  const openSign = async (contract: PortalTeacherContract) => {
    if (!contract.tiene_documento_original || contract.tiene_documento_firmado) return
    setSelectedId(contract.contrato_id)
    setSignOpen(true)
    setOperation('sign-preview')
    setError('')
    try {
      const blob = await fetchPortalTeacherContractDocument(contract.contrato_id, { version: 'original' })
      if (signPreviewUrl) URL.revokeObjectURL(signPreviewUrl)
      setSignPreviewUrl(URL.createObjectURL(blob))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo preparar el contrato para firma')
      setSignOpen(false)
    } finally {
      setOperation('')
    }
  }

  const signContract = async () => {
    if (!selected || !certificate || !certificatePassword.trim() || !signatureConsent) {
      setError('Seleccione el certificado, ingrese la contraseña y confirme la autorización de firma.')
      return
    }
    setOperation('sign')
    setError('')
    setMessage('')
    try {
      const blob = await signPortalTeacherContract({
        contractId: selected.contrato_id,
        certificado: certificate,
        contrasenaCertificado: certificatePassword,
        firmaMotivo: signatureReason.trim(),
        firmaUbicacion: signatureLocation.trim(),
        firmaContacto: signatureContact.trim(),
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `contrato-${safeFilePart(selected.numero_contrato || String(selected.contrato_id))}-firmado-docente.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
      if (signPreviewUrl) URL.revokeObjectURL(signPreviewUrl)
      setSignPreviewUrl('')
      clearSignatureSecrets()
      setSignOpen(false)
      await load()
      setSelectedId(selected.contrato_id)
      setMessage('Contrato firmado electrónicamente y registrado como versión vigente.')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'No se pudo firmar el contrato')
      clearSignatureSecrets()
    } finally {
      setOperation('')
    }
  }

  return (
    <div className="student-dashboard portal-page teacher-contract-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Portal docente</p>
          <h1>Contratos docentes</h1>
          <p>{data?.teacher?.nombre || displayName}</p>
        </div>
        <div className="contract-hero-actions">
          <button type="button" className="primary-action" onClick={openUpload} disabled={loading || courseOptions.length === 0}>
            Adjuntar contrato
          </button>
          <button type="button" className="ghost-button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
        </div>
      </header>

      {error ? <p className="contract-notice contract-notice--error">{error}</p> : null}
      {message ? <p className="contract-notice contract-notice--success">{message}</p> : null}
      {!loading && courseOptions.length === 0 ? (
        <p className="contract-notice contract-notice--warning">
          No existen cursos asignados al docente autenticado. El contrato solo puede vincularse a una asignación académica real.
        </p>
      ) : null}
      {!loading && !error && data?.contracts.length === 0 ? (
        <section className="contract-empty">
          <span>Sin contrato registrado</span>
          <h2>Adjunte el contrato regular o de homologación</h2>
          <p>Seleccione primero uno de sus cursos. El sistema validará docente, materia, carrera, período, paralelo y modalidad antes de guardar el PDF.</p>
          <button type="button" className="primary-action" onClick={openUpload} disabled={courseOptions.length === 0}>
            Adjuntar primer contrato
          </button>
        </section>
      ) : null}

      {selected ? (
        <>
          <section className="contract-toolbar">
            <label>
              <span>Contrato a consultar</span>
              <select value={selected.contrato_id} onChange={(event) => setSelectedId(Number(event.target.value))}>
                {data?.contracts.map((contract) => (
                  <option key={contract.contrato_id} value={contract.contrato_id}>
                    {textOrPending(contract.numero_contrato)} · {contract.modalidad_academica === 'HOMOLOGACION' ? 'Homologación' : 'Regular'} · {textOrPending(contract.codigo_periodo)}
                  </option>
                ))}
              </select>
            </label>
            <div className="contract-status" data-status={selected.estado_codigo?.toLowerCase() || 'pendiente'}>
              <span>Estado contractual</span>
              <strong>{textOrPending(selected.estado_nombre)}</strong>
            </div>
          </section>

          <section className="contract-document-actions" aria-label="Documento contractual">
            <div>
              <span>{selected.tiene_documento_firmado ? 'Contrato firmado electrónicamente' : 'Contrato pendiente de firma docente'}</span>
              <strong>{selected.nombre_documento_firmado || selected.nombre_documento_original || 'Documento no adjuntado'}</strong>
              <small>
                {selected.tiene_documento_firmado
                  ? `Firma registrada: ${formatDate(selected.fecha_documento_firmado)}`
                  : `Carga registrada: ${formatDate(selected.fecha_documento_original)}`}
              </small>
            </div>
            <div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void previewContract(selected)}
                disabled={!selected.tiene_documento_original || operation === `preview-${selected.contrato_id}`}
              >
                {operation === `preview-${selected.contrato_id}` ? 'Abriendo...' : 'Vista previa'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void downloadContract(selected)}
                disabled={!selected.tiene_documento_original || operation === `download-${selected.contrato_id}`}
              >
                {operation === `download-${selected.contrato_id}` ? 'Descargando...' : 'Descargar'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={() => void openSign(selected)}
                disabled={!selected.tiene_documento_original || selected.tiene_documento_firmado || Boolean(operation)}
              >
                {selected.tiene_documento_firmado ? 'Firma registrada' : 'Firmar contrato'}
              </button>
            </div>
          </section>

          <section className="contract-summary" aria-label="Resumen del contrato">
            <div><span>Materias</span><strong>{selected.clases.length}</strong></div>
            <div><span>Horas planificadas</span><strong>{totals.planned}</strong></div>
            <div><span>Horas ejecutadas</span><strong>{totals.executed}</strong></div>
            <div><span>Total de carga</span><strong>{formatMoney(totals.value)}</strong></div>
          </section>

          <section className="contract-point">
            <header><span>1</span><div><small>Identificación</small><h2>Datos del contrato y docente</h2></div></header>
            <dl className="contract-data-grid">
              <div><dt>Número de contrato</dt><dd>{textOrPending(selected.numero_contrato)}</dd></div>
              <div><dt>Modalidad académica</dt><dd>{selected.modalidad_academica === 'HOMOLOGACION' ? 'Homologación' : 'Regular'}</dd></div>
              <div><dt>Tipo de contrato</dt><dd>{textOrPending(selected.tipo_nombre)}</dd></div>
              <div><dt>Cédula</dt><dd>{textOrPending(data?.teacher?.cedula)}</dd></div>
              <div><dt>Correo institucional</dt><dd>{textOrPending(data?.teacher?.correo)}</dd></div>
              <div><dt>Relación laboral</dt><dd>{textOrPending(data?.teacher?.relacion_laboral)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>2</span><div><small>Vigencia</small><h2>Período y fechas</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Período académico</dt><dd>{textOrPending(selected.codigo_periodo)}</dd></div>
              <div><dt>Fecha de inicio</dt><dd>{formatDate(selected.fecha_inicio)}</dd></div>
              <div><dt>Fecha de finalización</dt><dd>{formatDate(selected.fecha_fin)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>3</span><div><small>Condiciones</small><h2>Valores económicos registrados</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Valor por hora</dt><dd>{formatMoney(selected.valor_hora_clase)}</dd></div>
              <div><dt>Valor mensual</dt><dd>{formatMoney(selected.valor_mensual)}</dd></div>
              <div><dt>Valor total del contrato</dt><dd>{formatMoney(selected.valor_total_contrato)}</dd></div>
            </dl>
          </section>

          <section className="contract-point">
            <header><span>4</span><div><small>Respaldo</small><h2>Responsable, observación y firma</h2></div></header>
            <dl className="contract-data-grid contract-data-grid--three">
              <div><dt>Responsable de contratación</dt><dd>{textOrPending(selected.responsable_contratacion)}</dd></div>
              <div><dt>Observación</dt><dd>{textOrPending(selected.observacion)}</dd></div>
              <div><dt>Firma docente</dt><dd>{selected.tiene_documento_firmado ? 'Registrada electrónicamente' : 'Pendiente'}</dd></div>
            </dl>
          </section>

          <section className="contract-point contract-point--classes">
            <header><span>5</span><div><small>Carga académica</small><h2>Materias incluidas en el contrato</h2></div></header>
            <div className="contract-table-wrap">
              <table className="contract-table">
                <thead><tr><th>Materia</th><th>Carrera</th><th>Período</th><th>Paralelo</th><th>Jornada</th><th>Horas</th><th>Ejecutadas</th><th>Valor hora</th><th>Estado</th></tr></thead>
                <tbody>
                  {selected.clases.length ? selected.clases.map((item) => (
                    <tr key={item.clase_id}>
                      <td><strong>{textOrPending(item.nombre_materia)}</strong><small>{textOrPending(item.codigo_materia)}</small></td>
                      <td>{textOrPending(item.nombre_carrera)}</td>
                      <td>{textOrPending(item.codigo_periodo)}</td>
                      <td>{textOrPending(item.paralelo)}</td>
                      <td>{textOrPending(item.jornada)}</td>
                      <td>{item.horas_planificadas ?? 0}</td>
                      <td>{item.horas_ejecutadas ?? 0}</td>
                      <td>{formatMoney(item.valor_hora)}</td>
                      <td><span className="contract-class-status">{textOrPending(item.estado)}</span></td>
                    </tr>
                  )) : <tr><td colSpan={9} className="contract-table-empty">Este contrato no tiene materias asociadas.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}

      {uploadOpen ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-labelledby="contract-upload-title">
          <article className="contract-document-modal contract-document-modal--upload">
            <header>
              <div>
                <span>Contrato docente</span>
                <h2 id="contract-upload-title">Adjuntar contrato regular u homologado</h2>
                <p>Cargue el contrato para reconocer automáticamente materia, modalidad, número y fechas.</p>
              </div>
              <button type="button" className="ghost-button" onClick={closeUpload} disabled={operation === 'upload' || operation === 'analyze-contract'}>Cerrar</button>
            </header>
            <div className="contract-document-modal-body">
              <form className="contract-upload-form" onSubmit={(event) => { event.preventDefault(); void submitUpload() }}>
                <label className="contract-form-wide">
                  <span>Docente del contrato</span>
                  <input value={data?.teacher?.nombre || displayName} readOnly />
                </label>
                <label className="contract-form-wide contract-file-picker">
                  <span>Contrato PDF</span>
                  <input
                    key={uploadFileKey}
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={(event) => { void selectUploadFile(event.target.files?.[0] || null) }}
                    disabled={operation === 'upload' || operation === 'analyze-contract'}
                    required
                  />
                  <small>
                    {operation === 'analyze-contract'
                      ? 'Analizando el documento y validando al docente...'
                      : uploadFile
                        ? `${uploadFile.name} · ${(uploadFile.size / 1024 / 1024).toFixed(2)} MB`
                        : 'Seleccione el contrato institucional en PDF. El archivo aún no se almacena.'}
                  </small>
                </label>
                {uploadAnalysis ? (
                  <section
                    className="contract-analysis-card contract-form-wide"
                    data-valid={courseMatchesAnalysis(selectedUploadCourse, uploadAnalysis) ? 'true' : 'false'}
                    aria-live="polite"
                  >
                    <header>
                      <div>
                        <span>Análisis del contrato</span>
                        <strong>{courseMatchesAnalysis(selectedUploadCourse, uploadAnalysis) ? 'Documento validado' : 'Requiere seleccionar el curso correcto'}</strong>
                      </div>
                      <small>{uploadAnalysis.campos_detectados.length} dato(s) reconocido(s)</small>
                    </header>
                    <dl>
                      <div><dt>Contrato</dt><dd>{uploadAnalysis.numero_contrato || 'No reconocido'}</dd></div>
                      <div><dt>Cédula</dt><dd>{uploadAnalysis.cedula || 'No reconocida'}</dd></div>
                      <div><dt>Materia</dt><dd>{uploadAnalysis.codigo_materia || 'No reconocida'}</dd></div>
                      <div><dt>Modalidad</dt><dd>{uploadAnalysis.modalidad_academica === 'HOMOLOGACION' ? 'Homologación' : 'Regular'}</dd></div>
                      <div><dt>Inicio</dt><dd>{formatDate(uploadAnalysis.fecha_inicio)}</dd></div>
                      <div><dt>Finalización</dt><dd>{formatDate(uploadAnalysis.fecha_fin)}</dd></div>
                    </dl>
                    {uploadAnalysis.advertencias.length ? <p>{uploadAnalysis.advertencias.join(' ')}</p> : null}
                  </section>
                ) : null}
                <label className="contract-form-wide">
                  <span>Curso asignado al docente</span>
                  <select value={selectedUploadCourse?.key || ''} onChange={(event) => selectUploadCourse(event.target.value)} required>
                    {courseOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
                  </select>
                  <small>La asignación debe coincidir con la materia y modalidad declaradas en el PDF.</small>
                </label>
                <label>
                  <span>Modalidad</span>
                  <input value={selectedUploadCourse?.modalidad === 'HOMOLOGACION' ? 'Homologación' : 'Regular'} readOnly />
                </label>
                <label>
                  <span>Número de contrato</span>
                  <input value={uploadDraft.numeroContrato} onChange={(event) => setUploadDraft((current) => ({ ...current, numeroContrato: event.target.value }))} maxLength={100} readOnly={Boolean(uploadAnalysis?.numero_contrato)} required />
                </label>
                <label>
                  <span>Fecha de inicio</span>
                  <input type="date" value={uploadDraft.fechaInicio} onChange={(event) => setUploadDraft((current) => ({ ...current, fechaInicio: event.target.value }))} readOnly={Boolean(uploadAnalysis?.fecha_inicio)} required />
                </label>
                <label>
                  <span>Fecha de finalización</span>
                  <input type="date" value={uploadDraft.fechaFin} onChange={(event) => setUploadDraft((current) => ({ ...current, fechaFin: event.target.value }))} readOnly={Boolean(uploadAnalysis?.fecha_fin)} required />
                </label>
                <label>
                  <span>Horas planificadas</span>
                  <input type="number" min="0" step="0.01" value={uploadDraft.horasPlanificadas} onChange={(event) => setUploadDraft((current) => ({ ...current, horasPlanificadas: event.target.value }))} />
                  <small>Use 0 para tomar las horas registradas en PENSUM.</small>
                </label>
                <label>
                  <span>Valor por hora</span>
                  <input type="number" min="0" step="0.01" value={uploadDraft.valorHora} onChange={(event) => setUploadDraft((current) => ({ ...current, valorHora: event.target.value }))} />
                </label>
                <label>
                  <span>Valor total</span>
                  <input type="number" min="0" step="0.01" value={uploadDraft.valorTotal} onChange={(event) => setUploadDraft((current) => ({ ...current, valorTotal: event.target.value }))} readOnly={uploadAnalysis?.valor_total != null} />
                </label>
                <label>
                  <span>Responsable de contratación</span>
                  <input value={uploadDraft.responsableContratacion} onChange={(event) => setUploadDraft((current) => ({ ...current, responsableContratacion: event.target.value }))} maxLength={200} />
                </label>
                <label className="contract-form-wide">
                  <span>Observación</span>
                  <textarea value={uploadDraft.observacion} onChange={(event) => setUploadDraft((current) => ({ ...current, observacion: event.target.value }))} maxLength={1000} rows={3} />
                </label>
                <div className="contract-form-actions contract-form-wide">
                  <button type="button" className="ghost-button" onClick={closeUpload} disabled={operation === 'upload' || operation === 'analyze-contract'}>Cancelar</button>
                  <button
                    type="submit"
                    className="primary-action"
                    disabled={Boolean(operation) || !uploadFile || !uploadAnalysis || !courseMatchesAnalysis(selectedUploadCourse, uploadAnalysis)}
                  >
                    {operation === 'upload' ? 'Guardando...' : 'Guardar contrato'}
                  </button>
                </div>
              </form>
              <div className="contract-local-preview">
                <span>Vista previa del PDF seleccionado</span>
                {uploadPreviewUrl
                  ? <iframe src={uploadPreviewUrl} title="Vista previa del contrato seleccionado" />
                  : <p>Seleccione el PDF para verificar el contrato antes de registrarlo.</p>}
              </div>
            </div>
          </article>
        </div>
      ) : null}

      {documentPreviewUrl ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-label="Vista previa del contrato docente">
          <article className="portal-report-preview-modal contract-document-preview-modal">
            <header>
              <div><span>Contrato docente</span><h2>{documentPreviewTitle}</h2><p>Versión vigente registrada en el sistema.</p></div>
              <button type="button" className="ghost-button" onClick={closeDocumentPreview}>Cerrar</button>
            </header>
            <iframe src={documentPreviewUrl} title={`Contrato ${documentPreviewTitle}`} />
          </article>
        </div>
      ) : null}

      {signOpen && selected ? (
        <div className="portal-report-preview-overlay" role="dialog" aria-modal="true" aria-labelledby="contract-sign-title">
          <article className="contract-document-modal contract-document-modal--sign">
            <header>
              <div>
                <span>Firma electrónica</span>
                <h2 id="contract-sign-title">Firmar contrato {textOrPending(selected.numero_contrato)}</h2>
                <p>Revise el documento completo antes de aplicar su certificado.</p>
              </div>
              <button type="button" className="ghost-button" onClick={closeSign} disabled={operation === 'sign'}>Cerrar</button>
            </header>
            <div className="contract-sign-layout">
              <div className="contract-sign-preview">
                {signPreviewUrl
                  ? <iframe src={signPreviewUrl} title="Contrato original antes de firma" />
                  : <p>{operation === 'sign-preview' ? 'Preparando contrato...' : 'No se pudo cargar la vista previa.'}</p>}
              </div>
              <form className="contract-sign-form" onSubmit={(event) => { event.preventDefault(); void signContract() }}>
                <div className="contract-sign-warning">
                  La firma se añade de forma incremental sobre el PDF original para conservar las firmas previas del contrato.
                </div>
                <label>
                  <span>Certificado del docente</span>
                  <input key={certificateKey} type="file" accept=".p12,.pfx,application/x-pkcs12" onChange={(event) => setCertificate(event.target.files?.[0] || null)} required />
                  <small>{certificate?.name || 'Archivo .p12 o .pfx de máximo 2 MB'}</small>
                </label>
                <label>
                  <span>Contraseña del certificado</span>
                  <div className="contract-password-field">
                    <input type={showCertificatePassword ? 'text' : 'password'} value={certificatePassword} onChange={(event) => setCertificatePassword(event.target.value)} autoComplete="new-password" required />
                    <button type="button" className="ghost-button" onClick={() => setShowCertificatePassword((current) => !current)}>
                      {showCertificatePassword ? 'Ocultar' : 'Mostrar'}
                    </button>
                  </div>
                </label>
                <label>
                  <span>Motivo</span>
                  <input value={signatureReason} onChange={(event) => setSignatureReason(event.target.value)} maxLength={200} />
                </label>
                <label>
                  <span>Ubicación</span>
                  <input value={signatureLocation} onChange={(event) => setSignatureLocation(event.target.value)} maxLength={120} />
                </label>
                <label>
                  <span>Contacto</span>
                  <input value={signatureContact} onChange={(event) => setSignatureContact(event.target.value)} maxLength={200} />
                </label>
                <label className="contract-sign-consent">
                  <input type="checkbox" checked={signatureConsent} onChange={(event) => setSignatureConsent(event.target.checked)} />
                  <span>Confirmo que soy titular del certificado y apruebo el contenido definitivo del contrato.</span>
                </label>
                <div className="contract-form-actions">
                  <button type="button" className="ghost-button" onClick={clearSignatureSecrets} disabled={operation === 'sign'}>Limpiar certificado</button>
                  <button type="submit" className="primary-action" disabled={operation === 'sign' || !certificate || !certificatePassword.trim() || !signatureConsent}>
                    {operation === 'sign' ? 'Firmando...' : 'Firmar y descargar'}
                  </button>
                </div>
                <small className="contract-ephemeral-note">El archivo .p12 y la contraseña no se guardan. Deben seleccionarse nuevamente para otra firma.</small>
              </form>
            </div>
          </article>
        </div>
      ) : null}
    </div>
  )
}
