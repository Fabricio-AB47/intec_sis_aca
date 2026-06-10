import { useMemo, useState, type ChangeEvent } from 'react'

import { analyzeMassEmailExcel, resolveMassEmailRecipients, searchMassEmailUsers, sendMassEmail } from '../../lib/api'
import type { MassEmailExcelResponse, MassEmailExcelRow, MassEmailRecipient, MassEmailSendResponse } from '../../types/app'

type MassEmailViewProps = {
  displayName: string
}

const defaultBody = `Estimado/a,

Adjunto información institucional enviada por INTEC.

Saludos,
INTEC`
const intecLogoPath = '/Intec-Logowithslogangray.svg'
const massEmailTemplatePath = '/plantillas/plantilla_envio_masivo_correos.xlsx'
const institutionName = 'Instituto Superior Tecnológico de Técnicas Empresariales y del Conocimiento INTEC'

function parseEmails(value: string) {
  const seen = new Set<string>()
  return value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter((item) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(item))
    .filter((email) => {
      const key = email.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function countCedulas(value: string) {
  return value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean).length
}

function countEmails(value: string) {
  return parseEmails(value).length
}

function valueOrDash(value: unknown) {
  const text = String(value ?? '').trim()
  return text || '-'
}

function normalizeText(value: unknown) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function normalizeCedula(value: unknown) {
  return String(value ?? '').replace(/\D/g, '')
}

function extractCedulaFromFilename(fileName: string) {
  const matches = Array.from(fileName.matchAll(/(?:^|\D)(\d{10})(?=\D|$)/g))
  return matches[0]?.[1] || ''
}

function fileSizeLabel(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(2)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function recipientLabel(recipient: MassEmailRecipient) {
  return `${valueOrDash(recipient.nombres || recipient.email)} - ${valueOrDash(recipient.cedula)}`
}

function joinSpanishList(values: string[]) {
  if (values.length <= 1) return values[0] || ''
  if (values.length === 2) return `${values[0]} y ${values[1]}`
  return `${values.slice(0, -1).join(', ')} y ${values[values.length - 1]}`
}

function findRecipientByCedula(cedula: string, recipients: MassEmailRecipient[]) {
  const normalizedCedula = normalizeCedula(cedula)
  if (!normalizedCedula) return undefined
  return recipients.find((recipient) => normalizeCedula(recipient.cedula) === normalizedCedula)
}

function findRecipientByFilename(fileName: string, recipients: MassEmailRecipient[]) {
  const detectedCedula = extractCedulaFromFilename(fileName)
  const cedulaMatch = findRecipientByCedula(detectedCedula, recipients)
  if (cedulaMatch) return cedulaMatch

  const normalizedName = normalizeText(fileName)
  return recipients.find((recipient) => {
    const cedula = normalizeCedula(recipient.cedula)
    if (cedula && normalizedName.includes(cedula)) return true

    const tokens = normalizeText(recipient.nombres)
      .split(/\s+/)
      .filter((token) => token.length >= 4)
    if (tokens.length < 2) return false
    return tokens.filter((token) => normalizedName.includes(token)).length >= 2
  })
}

function filterRecipientsByText(recipients: MassEmailRecipient[], searchText: string) {
  const query = normalizeText(searchText)
  if (!query) return recipients
  return recipients.filter((recipient) =>
    [
      recipient.cedula,
      recipient.nombres,
      recipient.email,
      recipient.codigo,
      recipient.login,
      recipient.tipo_usuario,
    ]
      .map(normalizeText)
      .some((value) => value.includes(query)),
  )
}

function excelCedulas(rows: MassEmailExcelRow[]) {
  return Array.from(
    new Set(rows.map((row) => normalizeCedula(row.cedula)).filter((cedula) => cedula.length >= 10)),
  )
}

function matchExcelRowByFilename(fileName: string, rows: MassEmailExcelRow[]) {
  const normalizedFile = normalizeText(fileName)
  const fileCedula = extractCedulaFromFilename(fileName)
  if (fileCedula) {
    const byCedula = rows.find((row) => normalizeCedula(row.cedula) === fileCedula)
    if (byCedula) return byCedula
  }

  return rows.find((row) => {
    const cedula = normalizeCedula(row.cedula)
    if (cedula && normalizedFile.includes(cedula)) return true

    const documentTokens = [row.documento, row.referencia]
      .map(normalizeText)
      .filter((value) => value.length >= 4)
    if (documentTokens.some((value) => normalizedFile.includes(value))) return true

    const nameTokens = normalizeText(row.nombre_excel)
      .split(/\s+/)
      .filter((token) => token.length >= 4)
    return nameTokens.length >= 2 && nameTokens.filter((token) => normalizedFile.includes(token)).length >= 2
  })
}

export function MassEmailView({ displayName }: Readonly<MassEmailViewProps>) {
  const [cedulasText, setCedulasText] = useState('')
  const [includeIntec, setIncludeIntec] = useState(true)
  const [includePersonal, setIncludePersonal] = useState(true)
  const [includeDocentes, setIncludeDocentes] = useState(true)
  const [includeAdministrativos, setIncludeAdministrativos] = useState(true)
  const [manualEmails, setManualEmails] = useState('')
  const [ccInput, setCcInput] = useState('')
  const [ccList, setCcList] = useState<string[]>([])
  const [ccSearch, setCcSearch] = useState('')
  const [ccSearchResults, setCcSearchResults] = useState<MassEmailRecipient[]>([])
  const [ccSearchLoading, setCcSearchLoading] = useState(false)
  const [matchAttachmentsByCedula, setMatchAttachmentsByCedula] = useState(true)
  const [sendMode, setSendMode] = useState<'individual' | 'single'>('individual')
  const [subject, setSubject] = useState('Comunicación institucional INTEC')
  const [body, setBody] = useState(defaultBody)
  const [studentFiles, setStudentFiles] = useState<File[]>([])
  const [commonFiles, setCommonFiles] = useState<File[]>([])
  const [studentFileAssignments, setStudentFileAssignments] = useState<Record<string, string>>({})
  const [assignmentSearch, setAssignmentSearch] = useState('')
  const [assignmentStatusFilter, setAssignmentStatusFilter] = useState<'all' | 'assigned' | 'pending'>('all')
  const [assignmentSearchLoading, setAssignmentSearchLoading] = useState(false)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [excelAnalysis, setExcelAnalysis] = useState<MassEmailExcelResponse | null>(null)
  const [excelLoading, setExcelLoading] = useState(false)
  const [excelSearch, setExcelSearch] = useState('')
  const [recipients, setRecipients] = useState<MassEmailRecipient[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [userSearch, setUserSearch] = useState('')
  const [userSearchResults, setUserSearchResults] = useState<MassEmailRecipient[]>([])
  const [userSearchLoading, setUserSearchLoading] = useState(false)
  const [notFound, setNotFound] = useState<string[]>([])
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({})
  const [graphSender, setGraphSender] = useState('')
  const [sendResults, setSendResults] = useState<MassEmailRecipient[]>([])
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [activePhase, setActivePhase] = useState<1 | 2 | 3>(1)
  const [selectedModalOpen, setSelectedModalOpen] = useState(false)
  const [previewModalOpen, setPreviewModalOpen] = useState(false)

  const cedulaCount = useMemo(() => countCedulas(cedulasText), [cedulasText])
  const manualEmailCount = useMemo(() => countEmails(manualEmails), [manualEmails])
  const manualEmailList = useMemo(() => parseEmails(manualEmails), [manualEmails])
  const selectedRecipients = useMemo(
    () => recipients.filter((recipient) => selectedIds.has(recipient.id)),
    [recipients, selectedIds],
  )
  const recipientAssignmentOptions = useMemo(() => {
    const next = new Map<string, MassEmailRecipient>()
    const base = selectedRecipients.length ? selectedRecipients : recipients
    base.forEach((recipient) => {
      const cedula = String(recipient.cedula || '').trim()
      if (cedula && !next.has(cedula)) next.set(cedula, recipient)
    })
    return Array.from(next.values()).sort((a, b) =>
      valueOrDash(a.nombres || a.email).localeCompare(valueOrDash(b.nombres || b.email)),
    )
  }, [recipients, selectedRecipients])
  const filteredAssignmentOptions = useMemo(
    () => filterRecipientsByText(recipientAssignmentOptions, assignmentSearch),
    [assignmentSearch, recipientAssignmentOptions],
  )
  const resultById = useMemo(() => {
    const next = new Map<string, MassEmailRecipient>()
    sendResults.forEach((result) => next.set(result.id, result))
    return next
  }, [sendResults])
  const totalAttachmentCount = studentFiles.length + commonFiles.length
  const excelRows = excelAnalysis?.rows || []
  const excelSummary = excelAnalysis?.summary || {}
  const excelCedulaList = useMemo(() => excelCedulas(excelRows), [excelRows])
  const filteredExcelRows = useMemo(() => {
    const query = normalizeText(excelSearch)
    if (!query) return excelRows.slice(0, 80)
    return excelRows
      .filter((row) =>
        [
          row.cedula,
          row.nombre_excel,
          row.correo_excel,
          row.documento,
          row.carrera,
          row.periodo,
          row.referencia,
          row.estado,
          row.motivo,
        ]
          .map(normalizeText)
          .some((value) => value.includes(query)),
      )
      .slice(0, 80)
  }, [excelRows, excelSearch])
  const studentFileRows = useMemo(
    () =>
      studentFiles.map((file, index) => {
        const detectedCedula = extractCedulaFromFilename(file.name)
        const assignedCedula = assignedCedulaForFile(file)
        const assignedRecipient = findRecipientByCedula(assignedCedula, recipientAssignmentOptions)
        const autoMatch = findRecipientByFilename(file.name, recipientAssignmentOptions)
        return {
          file,
          index,
          detectedCedula,
          assignedCedula,
          assignedRecipient,
          autoMatch,
          status: assignedRecipient ? 'assigned' : 'pending',
        }
      }),
    [excelRows, recipientAssignmentOptions, studentFileAssignments, studentFiles],
  )
  const assignedStudentFileCount = useMemo(
    () => studentFileRows.filter((row) => row.assignedRecipient).length,
    [studentFileRows],
  )
  const filteredStudentFileRows = useMemo(() => {
    const query = normalizeText(assignmentSearch)
    return studentFileRows.filter((row) => {
      if (assignmentStatusFilter === 'assigned' && !row.assignedRecipient) return false
      if (assignmentStatusFilter === 'pending' && row.assignedRecipient) return false
      if (!query) return true
      return [
        row.file.name,
        row.detectedCedula,
        row.assignedCedula,
        row.assignedRecipient?.nombres,
        row.assignedRecipient?.cedula,
        row.assignedRecipient?.email,
      ]
        .map(normalizeText)
        .some((value) => value.includes(query))
    })
  }, [assignmentSearch, assignmentStatusFilter, studentFileRows])

  function assignedCedulaForFile(file: File) {
    const manual = studentFileAssignments[file.name]
    if (manual) return manual
    const excelMatch = matchExcelRowByFilename(file.name, excelRows)
    if (excelMatch?.cedula) return excelMatch.cedula
    return findRecipientByFilename(file.name, recipientAssignmentOptions)?.cedula || ''
  }

  function buildAttachmentAssignments() {
    const assignments: Record<string, string> = {}
    studentFiles.forEach((file) => {
      const cedula = assignedCedulaForFile(file)
      if (cedula) assignments[file.name] = cedula
    })
    return assignments
  }

  function applyExcelAssignmentsToFiles(files: File[], rows: MassEmailExcelRow[]) {
    if (!files.length || !rows.length) return
    setStudentFileAssignments((current) => {
      const next = { ...current }
      files.forEach((file) => {
        if (next[file.name]) return
        const match = matchExcelRowByFilename(file.name, rows)
        if (match?.cedula) next[file.name] = match.cedula
      })
      return next
    })
  }

  async function executeExcelAnalysis() {
    setError('')
    setMessage('')
    setSendResults([])

    if (!excelFile) {
      setError('Selecciona un Excel para analizar.')
      return
    }

    setExcelLoading(true)
    try {
      const payload = await analyzeMassEmailExcel(excelFile, {
        includeIntec,
        includePersonal,
        includeDocentes,
        includeAdministrativos,
      })
      setExcelAnalysis(payload)
      setGraphSender(payload.graph_mail_sender || graphSender)
      const items = payload.items || []
      if (items.length) {
        mergeRecipients(items)
        updateAssignmentsFromRecipients(studentFiles, [...recipientAssignmentOptions, ...items])
      }
      applyExcelAssignmentsToFiles(studentFiles, payload.rows || [])
      setMessage(
        `Excel analizado: ${payload.summary?.total || 0} fila(s), ${payload.summary?.listos || 0} lista(s) para envío.`,
      )
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo analizar el Excel.')
    } finally {
      setExcelLoading(false)
    }
  }

  function useExcelCedulasInSearch() {
    if (!excelCedulaList.length) {
      setError('El Excel no tiene cédulas válidas para cargar.')
      return
    }
    setCedulasText(excelCedulaList.join('\n'))
    setError('')
    setMessage(`${excelCedulaList.length} cédula(s) del Excel cargada(s) en el buscador.`)
  }

  function addExcelRecipients() {
    const items = excelAnalysis?.items || []
    if (!items.length) {
      setError('El Excel no tiene destinatarios encontrados para agregar.')
      return
    }
    mergeRecipients(items)
    updateAssignmentsFromRecipients(studentFiles, [...recipientAssignmentOptions, ...items])
    applyExcelAssignmentsToFiles(studentFiles, excelRows)
    setError('')
    setMessage(`${items.length} destinatario(s) del Excel agregado(s) al envío.`)
  }

  function clearExcelAnalysis() {
    setExcelFile(null)
    setExcelAnalysis(null)
    setExcelSearch('')
  }

  async function resolveRecipients() {
    setError('')
    setMessage('')
    setSendResults([])

    if (!cedulasText.trim()) {
      setError('Ingresa al menos una cédula para buscar destinatarios.')
      return
    }

    setLoading(true)
    try {
      const payload = await resolveMassEmailRecipients({
        cedulas: cedulasText,
        include_intec: includeIntec,
        include_personal: includePersonal,
        include_docentes: includeDocentes,
        include_administrativos: includeAdministrativos,
      })
      const items = payload.items || []
      setRecipients(items)
      setSelectedIds(new Set(items.map((item) => item.id)))
      setNotFound(payload.not_found || [])
      setSourceCounts(payload.sources || {})
      setGraphSender(payload.graph_mail_sender || '')
      setMessage(`${items.length} destinatario(s) encontrado(s).`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo resolver destinatarios.')
    } finally {
      setLoading(false)
    }
  }

  function mergeRecipients(items: MassEmailRecipient[]) {
    if (!items.length) return
    setRecipients((current) => {
      const seen = new Set(current.map((recipient) => recipient.id))
      const next = [...current]
      items.forEach((item) => {
        if (!seen.has(item.id)) {
          seen.add(item.id)
          next.push(item)
        }
      })
      return next
    })
    setSelectedIds((current) => {
      const next = new Set(current)
      items.forEach((item) => next.add(item.id))
      return next
    })
  }

  async function executeUserSearch() {
    setError('')
    setMessage('')
    setSendResults([])

    const query = userSearch.trim()
    if (query.length < 2) {
      setError('Ingresa al menos 2 caracteres para buscar usuarios.')
      return
    }

    setUserSearchLoading(true)
    try {
      const payload = await searchMassEmailUsers(query, 50)
      setUserSearchResults(payload.items || [])
      setGraphSender(payload.graph_mail_sender || graphSender)
      setMessage(`${payload.items?.length || 0} usuario(s) encontrado(s) por búsqueda.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar usuarios.')
    } finally {
      setUserSearchLoading(false)
    }
  }

  async function executeCcSearch() {
    setError('')
    setMessage('')
    const query = ccSearch.trim()
    if (query.length < 2) {
      setError('Ingresa al menos 2 caracteres para buscar usuarios en copia.')
      return
    }

    setCcSearchLoading(true)
    try {
      const payload = await searchMassEmailUsers(query, 30)
      setCcSearchResults(payload.items || [])
      setGraphSender(payload.graph_mail_sender || graphSender)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar usuarios en copia.')
    } finally {
      setCcSearchLoading(false)
    }
  }

  function updateAssignmentsFromRecipients(files: File[], availableRecipients: MassEmailRecipient[]) {
    if (!files.length || !availableRecipients.length) return
    setStudentFileAssignments((current) => {
      const next = { ...current }
      files.forEach((file) => {
        if (next[file.name]) return
        const inferred = findRecipientByFilename(file.name, availableRecipients)
        if (inferred?.cedula) next[file.name] = inferred.cedula
      })
      return next
    })
  }

  async function resolveRecipientsFromStudentFiles(files: File[]) {
    const detectedCedulas = Array.from(
      new Set(files.map((file) => extractCedulaFromFilename(file.name)).filter(Boolean)),
    )
    const missingCedulas = detectedCedulas.filter((cedula) => !findRecipientByCedula(cedula, recipientAssignmentOptions))
    if (!missingCedulas.length) return

    setAssignmentSearchLoading(true)
    try {
      const payload = await resolveMassEmailRecipients({
        cedulas: missingCedulas.join('\n'),
        include_intec: includeIntec,
        include_personal: includePersonal,
        include_docentes: includeDocentes,
        include_administrativos: includeAdministrativos,
      })
      const found = payload.items || []
      if (found.length) {
        mergeRecipients(found)
        updateAssignmentsFromRecipients(files, [...recipientAssignmentOptions, ...found])
      }
      setMessage(
        found.length
          ? `${found.length} destinatario(s) detectado(s) automáticamente desde los documentos.`
          : 'Los documentos tienen cédula, pero no se encontraron destinatarios con esas cédulas.',
      )
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo resolver destinatarios desde documentos.')
    } finally {
      setAssignmentSearchLoading(false)
    }
  }

  async function executeAssignmentSearch() {
    const query = assignmentSearch.trim()
    if (query.length < 2) {
      setError('Ingresa al menos 2 caracteres para buscar estudiantes en la asignación.')
      return
    }

    setError('')
    setAssignmentSearchLoading(true)
    try {
      const payload = await searchMassEmailUsers(query, 80)
      const found = payload.items || []
      mergeRecipients(found)
      updateAssignmentsFromRecipients(studentFiles, [...recipientAssignmentOptions, ...found])
      setMessage(`${found.length} usuario(s) agregado(s) al selector de documentos.`)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo buscar estudiantes para asignar documentos.')
    } finally {
      setAssignmentSearchLoading(false)
    }
  }

  function addCcEmails(emails: string[]) {
    if (!emails.length) return
    setCcList((current) => {
      const seen = new Set(current.map((email) => email.toLowerCase()))
      const next = [...current]
      emails.forEach((email) => {
        const key = email.toLowerCase()
        if (!seen.has(key)) {
          seen.add(key)
          next.push(email)
        }
      })
      return next
    })
  }

  function addCcFromInput() {
    const emails = parseEmails(ccInput)
    if (!emails.length) {
      setError('Ingresa al menos un correo válido para copia.')
      return
    }
    addCcEmails(emails)
    setCcInput('')
    setError('')
  }

  function removeCcEmail(email: string) {
    setCcList((current) => current.filter((item) => item.toLowerCase() !== email.toLowerCase()))
  }

  function updateStudentFiles(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || [])
    if (!selectedFiles.length) return
    setStudentFiles((current) => [...current, ...selectedFiles])
    applyExcelAssignmentsToFiles(selectedFiles, excelRows)
    updateAssignmentsFromRecipients(selectedFiles, recipientAssignmentOptions)
    void resolveRecipientsFromStudentFiles(selectedFiles)
    event.currentTarget.value = ''
  }

  function updateCommonFiles(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || [])
    if (!selectedFiles.length) return
    setCommonFiles((current) => [...current, ...selectedFiles])
    event.currentTarget.value = ''
  }

  function removeStudentFile(index: number) {
    const fileToRemove = studentFiles[index]
    const remaining = studentFiles.filter((_, fileIndex) => fileIndex !== index)
    setStudentFiles(remaining)
    if (!remaining.some((file) => file.name === fileToRemove?.name)) {
      setStudentFileAssignments((current) => {
        const next = { ...current }
        delete next[fileToRemove.name]
        return next
      })
    }
  }

  function removeCommonFile(index: number) {
    setCommonFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))
  }

  function updateStudentFileAssignment(fileName: string, cedula: string) {
    setStudentFileAssignments((current) => {
      const next = { ...current }
      if (cedula) {
        next[fileName] = cedula
      } else {
        delete next[fileName]
      }
      return next
    })
  }

  function toggleRecipient(recipientId: string) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(recipientId)) {
        next.delete(recipientId)
      } else {
        next.add(recipientId)
      }
      return next
    })
  }

  function removeSelectedRecipient(recipientId: string) {
    setSelectedIds((current) => {
      const next = new Set(current)
      next.delete(recipientId)
      return next
    })
  }

  function removeManualEmail(email: string) {
    const target = email.toLowerCase()
    setManualEmails((current) => parseEmails(current).filter((item) => item.toLowerCase() !== target).join('\n'))
  }

  function selectAllRecipients() {
    setSelectedIds(new Set(recipients.map((recipient) => recipient.id)))
  }

  function clearSelection() {
    setSelectedIds(new Set())
  }

  function getMissingSendRequirements() {
    const missing: string[] = []
    if (!subject.trim()) missing.push('el asunto')
    if (!body.trim()) missing.push('el mensaje')
    if (!selectedRecipients.length && !manualEmailCount) missing.push('al menos un destinatario')
    return missing
  }

  function validateReadyToReview() {
    const missing = getMissingSendRequirements()
    if (!missing.length) {
      setError('')
      return true
    }
    setMessage('')
    setError(`Para continuar falta ${joinSpanishList(missing)}.`)
    return false
  }

  function goToReview() {
    if (!validateReadyToReview()) return
    setActivePhase(3)
  }

  async function executeSend() {
    setError('')
    setMessage('')
    setSendResults([])

    if (!validateReadyToReview()) return

    setSending(true)
    try {
      const payload: MassEmailSendResponse = await sendMassEmail({
        subject,
        body,
        recipients: selectedRecipients,
        manualEmails,
        ccEmails: ccList.join(';'),
        matchAttachmentsByCedula,
        sendMode,
        commonFiles,
        studentFiles,
        attachmentAssignments: buildAttachmentAssignments(),
      })
      setSendResults(payload.recipients || [])
      const skipped = payload.skipped_attachments || 0
      if (payload.failed) {
        const firstError = (payload.recipients || []).find((recipient) => recipient.error)?.error
        setError(
          `Envío parcial: ${payload.sent || 0} enviado(s), ${payload.failed} error(es).${
            firstError ? ` Detalle: ${firstError}` : ''
          }`,
        )
      } else if (payload.send_mode === 'single') {
        setMessage(`Se envió 1 correo único a ${selectedRecipients.length + manualEmailCount} destinatario(s).`)
      } else {
        setMessage(`${payload.sent || 0} correo(s) enviado(s) correctamente.`)
      }
      if (skipped) {
        setMessage((current) => `${current || 'Envío procesado.'} ${skipped} adjunto(s) de estudiante sin asignación fueron omitidos.`)
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo enviar el correo masivo.')
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Integraciones</p>
          <h1>Correos masivos</h1>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Envío por Graph</span>
            </div>
          </div>
        </div>
      </header>

      <section className="credential-overview mass-email-overview">
        <article>
          <span>Cédulas ingresadas</span>
          <strong>{cedulaCount}</strong>
          <small>Separadas por salto, coma o punto y coma</small>
        </article>
        <article>
          <span>Destinatarios seleccionados</span>
          <strong>{selectedRecipients.length + manualEmailCount}</strong>
          <small>{recipients.length} encontrado(s) | {manualEmailCount} manual(es)</small>
        </article>
        <article>
          <span>Adjuntos</span>
          <strong>{totalAttachmentCount}</strong>
          <small>{ccList.length} copia(s) | {sendMode === 'single' ? 'correo único' : 'individual'}</small>
        </article>
      </section>

      <section className="mass-email-simple-steps" aria-label="Flujo de correos masivos">
        <button
          type="button"
          className={`mass-email-phase-card${activePhase === 1 ? ' is-active' : ''}`}
          onClick={() => setActivePhase(1)}
        >
          <b>1</b>
          <div>
            <strong>Destinatarios</strong>
            <span>{selectedRecipients.length + manualEmailCount} seleccionado(s)</span>
          </div>
        </button>
        <button
          type="button"
          className={`mass-email-phase-card${activePhase === 2 ? ' is-active' : ''}`}
          onClick={() => setActivePhase(2)}
        >
          <b>2</b>
          <div>
            <strong>Mensaje y adjuntos</strong>
            <span>{totalAttachmentCount} archivo(s) preparados</span>
          </div>
        </button>
        <button
          type="button"
          className={`mass-email-phase-card${activePhase === 3 ? ' is-active' : ''}`}
          onClick={goToReview}
        >
          <b>3</b>
          <div>
            <strong>Revisión y envío</strong>
            <span>{sendMode === 'single' ? 'Correo único' : 'Correos individuales'}</span>
          </div>
        </button>
      </section>

      {error || message ? (
        <section className="mass-email-global-status" aria-live="polite">
          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-success">{message}</p> : null}
        </section>
      ) : null}

      <section className="mass-email-grid">
        {activePhase === 1 ? (
        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <span className="mass-email-step-label">Paso 1</span>
              <h3>Destinatarios</h3>
              <p>Ingresa cédulas, busca correos y selecciona quién recibirá el mensaje.</p>
            </div>
            <span>{loading ? 'Consultando...' : `${recipients.length} destinatario(s)`}</span>
          </div>

          <div className="mass-email-search">
            <label>
              <span>Cédulas</span>
              <textarea
                value={cedulasText}
                rows={8}
                onChange={(event) => setCedulasText(event.target.value)}
                placeholder="Ej. 1712345678&#10;0102030405&#10;..."
              />
            </label>
            <div className="mass-email-toolbar">
              <button type="button" className="ghost-button" onClick={() => void resolveRecipients()} disabled={loading}>
                {loading ? 'Buscando...' : 'Buscar correos'}
              </button>
              <button type="button" className="ghost-button" onClick={selectAllRecipients} disabled={!recipients.length}>
                Seleccionar todos
              </button>
              <button type="button" className="ghost-button" onClick={clearSelection} disabled={!recipients.length}>
                Limpiar selección
              </button>
            </div>

            <details className="mass-email-simple-details">
              <summary>Fuentes de búsqueda</summary>
              <div className="mass-email-options">
                <label className="credential-send-toggle">
                  <input type="checkbox" checked={includeIntec} onChange={(event) => setIncludeIntec(event.target.checked)} />
                  <span>Correos INTEC estudiantes</span>
                </label>
                <label className="credential-send-toggle">
                  <input type="checkbox" checked={includePersonal} onChange={(event) => setIncludePersonal(event.target.checked)} />
                  <span>Correos personales estudiantes</span>
                </label>
                <label className="credential-send-toggle">
                  <input type="checkbox" checked={includeDocentes} onChange={(event) => setIncludeDocentes(event.target.checked)} />
                  <span>Docentes</span>
                </label>
                <label className="credential-send-toggle">
                  <input
                    type="checkbox"
                    checked={includeAdministrativos}
                    onChange={(event) => setIncludeAdministrativos(event.target.checked)}
                  />
                  <span>Usuarios y administrativos</span>
                </label>
              </div>
            </details>

            <button
              type="button"
              className="ghost-button"
              onClick={() => setSelectedModalOpen(true)}
              disabled={!selectedRecipients.length && !manualEmailCount}
            >
              Ver involucrados seleccionados
            </button>
          </div>

          <details className="mass-email-simple-details" open>
            <summary>Importar desde Excel</summary>
            <section className="mass-email-excel-panel">
            <div className="mass-email-attachment-header">
              <div>
                <strong>Excel para envío masivo</strong>
                <span>
                  Carga una lista con cédula, nombre, correo, documento o referencia. La cédula valida a quién se enviará y ayuda a asociar PDFs.
                </span>
              </div>
              <div className="mass-email-document-stats">
                <span>{excelSummary.total || 0} fila(s)</span>
                <span>{excelSummary.listos || 0} lista(s)</span>
                <span>{excelSummary.sin_correo || 0} sin correo</span>
              </div>
            </div>

            <div className="mass-email-template-callout">
              <div>
                <strong>Plantilla disponible</strong>
                <span>Cédula, nombre, correo, documento, carrera, periodo y referencia.</span>
              </div>
              <a className="ghost-button" href={massEmailTemplatePath} download>
                Descargar plantilla
              </a>
            </div>

            <div className="mass-email-excel-actions">
              <label className="mass-email-file-input">
                <span>Subir Excel de destinatarios</span>
                <input
                  type="file"
                  accept=".xlsx,.xlsm"
                  onChange={(event) => {
                    setExcelFile(event.target.files?.[0] || null)
                    setExcelAnalysis(null)
                    event.currentTarget.value = ''
                  }}
                />
              </label>
              <div className="mass-email-excel-selected">
                <strong>{excelFile?.name || 'Sin Excel seleccionado'}</strong>
                <span>{excelFile ? fileSizeLabel(excelFile.size) : 'Formato permitido: .xlsx o .xlsm'}</span>
              </div>
              <button type="button" className="ghost-button" onClick={() => void executeExcelAnalysis()} disabled={excelLoading}>
                {excelLoading ? 'Analizando...' : 'Analizar Excel'}
              </button>
              <button type="button" className="ghost-button" onClick={useExcelCedulasInSearch} disabled={!excelCedulaList.length}>
                Usar cédulas
              </button>
              <button type="button" className="ghost-button" onClick={addExcelRecipients} disabled={!excelAnalysis?.items?.length}>
                Agregar encontrados
              </button>
              <button type="button" className="ghost-button" onClick={clearExcelAnalysis} disabled={!excelFile && !excelAnalysis}>
                Limpiar Excel
              </button>
            </div>

            {excelAnalysis ? (
              <>
                <div className="mass-email-excel-summary">
                  <article>
                    <span>Cédulas únicas</span>
                    <strong>{excelSummary.cedulas_unicas || 0}</strong>
                  </article>
                  <article>
                    <span>Destinatarios</span>
                    <strong>{excelSummary.destinatarios || 0}</strong>
                  </article>
                  <article>
                    <span>Documentos referenciados</span>
                    <strong>{excelSummary.filas_con_documento || 0}</strong>
                  </article>
                  <article>
                    <span>Sin cédula</span>
                    <strong>{excelSummary.sin_cedula || 0}</strong>
                  </article>
                  <article>
                    <span>Cédulas duplicadas</span>
                    <strong>{excelSummary.cedulas_duplicadas || 0}</strong>
                  </article>
                </div>

                <div className="mass-email-excel-filter">
                  <label>
                    <span>Filtrar filas del Excel</span>
                    <input
                      value={excelSearch}
                      onChange={(event) => setExcelSearch(event.target.value)}
                      placeholder="Cédula, estudiante, documento, carrera o estado"
                    />
                  </label>
                  <span>{filteredExcelRows.length} visible(s) de {excelRows.length}</span>
                </div>

                <div className="mass-email-excel-list">
                  {filteredExcelRows.map((row) => (
                    <article className={`mass-email-excel-row mass-email-excel-row--${normalizeText(row.estado)}`} key={`${row.excel_row}-${row.cedula}-${row.nombre_excel}`}>
                      <div>
                        <span>Fila {row.excel_row}</span>
                        <strong>{valueOrDash(row.cedula)}</strong>
                      </div>
                      <div>
                        <span>Estudiante</span>
                        <strong>{valueOrDash(row.nombre_excel)}</strong>
                        {row.correo_excel ? <small>{row.correo_excel}</small> : null}
                      </div>
                      <div>
                        <span>Documento / referencia</span>
                        <strong>{valueOrDash(row.documento || row.referencia)}</strong>
                        <small>{valueOrDash(row.carrera || row.periodo)}</small>
                      </div>
                      <div>
                        <span>Validación</span>
                        <strong>{valueOrDash(row.destinatarios)} destinatario(s)</strong>
                        <small>{valueOrDash(row.motivo)}</small>
                      </div>
                      <div>
                        <span className={`credential-status credential-status--${normalizeText(row.estado)}`}>
                          {valueOrDash(row.estado)}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="credential-muted">Al analizar el Excel se guardará la lista en esta pantalla para validar cédulas y asociar documentos por estudiante.</p>
            )}
            </section>
          </details>

          <details className="mass-email-simple-details">
            <summary>Buscar usuario manualmente</summary>
            <div className="mass-email-user-search">
            <div className="mass-email-user-search__bar">
              <label>
                <span>Buscar usuarios</span>
                <small>Consulta estudiantes, docentes, usuarios y administrativos.</small>
                <input
                  value={userSearch}
                  onChange={(event) => setUserSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void executeUserSearch()
                    }
                  }}
                  placeholder="Cédula, nombre, correo o login"
                />
              </label>
              <button
                type="button"
                className="primary-action mass-email-user-search__button"
                onClick={() => void executeUserSearch()}
                disabled={userSearchLoading}
              >
                {userSearchLoading ? 'Buscando...' : 'Buscar usuarios'}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => mergeRecipients(userSearchResults)}
                disabled={!userSearchResults.length}
              >
                Agregar visibles
              </button>
            </div>

            {userSearchResults.length ? (
              <>
                <div className="mass-email-user-search__summary">
                  <strong>{userSearchResults.length} resultado(s)</strong>
                  <span>Selecciona uno o agrega todos los visibles.</span>
                </div>
                <div className="mass-email-search-results">
                  {userSearchResults.map((recipient) => {
                    const alreadyAdded = recipients.some((item) => item.id === recipient.id)
                    return (
                      <div className="mass-email-user-option" key={recipient.id}>
                        <div>
                          <strong>{valueOrDash(recipient.nombres || recipient.email)}</strong>
                          <span>{recipient.email}</span>
                          <small>{valueOrDash(recipient.cedula)} | {valueOrDash(recipient.source_table)}</small>
                        </div>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => mergeRecipients([recipient])}
                          disabled={alreadyAdded}
                        >
                          {alreadyAdded ? 'Agregado' : 'Agregar'}
                        </button>
                      </div>
                    )
                  })}
                </div>
              </>
            ) : null}
            </div>
          </details>

          {notFound.length ? (
            <div className="mass-email-notfound">
              <strong>Cédulas sin correo encontrado</strong>
              <span>{notFound.join(', ')}</span>
            </div>
          ) : null}

          {Object.keys(sourceCounts).length ? (
            <div className="credential-help">
              <strong>Fuentes detectadas:</strong>
              {Object.entries(sourceCounts).map(([source, count]) => (
              <span key={source}>{source}: {count}</span>
              ))}
            </div>
          ) : null}

          <div className="mass-email-phase-footer">
            <button type="button" className="ghost-button" onClick={() => setSelectedModalOpen(true)} disabled={!selectedRecipients.length && !manualEmailCount}>
              Revisar seleccionados
            </button>
            <button type="button" className="primary-action" onClick={() => setActivePhase(2)}>
              Continuar al mensaje
            </button>
          </div>
        </article>
        ) : null}

        {activePhase === 2 ? (
        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <span className="mass-email-step-label">Paso 2</span>
              <h3>Mensaje y adjuntos</h3>
              <p>Prepara el contenido. Las copias, vista previa y documentos se abren solo cuando los necesites.</p>
            </div>
            <span>{totalAttachmentCount} archivo(s)</span>
          </div>

          <button type="button" className="mass-email-preview-launch" onClick={() => setPreviewModalOpen(true)}>
            <div>
              <strong>Vista previa institucional</strong>
              <span>Abre una subpantalla para revisar el correo con logo, colores y mensaje.</span>
            </div>
            <b>Ver</b>
          </button>

          <div className="matricula-acad-form mass-email-compose">
            <label>
              <span>Asunto</span>
              <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Asunto del correo" />
            </label>
            <div className="credential-field--wide mass-email-mode-selector">
              <button
                type="button"
                className={sendMode === 'individual' ? 'is-active' : ''}
                onClick={() => setSendMode('individual')}
              >
                <strong>Individual masivo</strong>
                <span>Un correo por destinatario. Usa documentos personalizados por cédula y adjuntos comunes.</span>
              </button>
              <button
                type="button"
                className={sendMode === 'single' ? 'is-active' : ''}
                onClick={() => {
                  setSendMode('single')
                  setMatchAttachmentsByCedula(true)
                }}
              >
                <strong>Un solo correo</strong>
                <span>Un mensaje con destinatarios en CCO. Solo adjunta documentos comunes.</span>
              </button>
            </div>

            <details className="credential-field--wide mass-email-simple-details">
              <summary>Correos en copia</summary>
              <div className="mass-email-copy-panel">
              <div className="card-head">
                <h3>Usuarios en copia</h3>
                <span>{ccList.length} correo(s)</span>
              </div>
              <div className="mass-email-copy-entry">
                <label>
                  <span>Agregar correo de copia</span>
                  <input
                    value={ccInput}
                    onChange={(event) => setCcInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        addCcFromInput()
                      }
                    }}
                    placeholder="correo@intec.edu.ec"
                  />
                </label>
                <button type="button" className="ghost-button" onClick={addCcFromInput}>
                  Agregar copia
                </button>
              </div>
              <div className="mass-email-copy-entry">
                <label>
                  <span>Buscar usuario para copia</span>
                  <input
                    value={ccSearch}
                    onChange={(event) => setCcSearch(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        void executeCcSearch()
                      }
                    }}
                    placeholder="Nombre, cédula, login o correo"
                  />
                </label>
                <button type="button" className="ghost-button" onClick={() => void executeCcSearch()} disabled={ccSearchLoading}>
                  {ccSearchLoading ? 'Buscando...' : 'Buscar copia'}
                </button>
              </div>
              {ccSearchResults.length ? (
                <div className="mass-email-copy-results">
                  {ccSearchResults.map((recipient) => (
                    <button
                      key={recipient.id}
                      type="button"
                      className="ghost-button"
                      onClick={() => addCcEmails([recipient.email])}
                    >
                      {valueOrDash(recipient.nombres || recipient.email)}
                      <span>{recipient.email}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              {ccList.length ? (
                <div className="mass-email-copy-list">
                  {ccList.map((email) => (
                    <span className="mass-email-copy-chip" key={email}>
                      {email}
                      <button type="button" onClick={() => removeCcEmail(email)} aria-label={`Quitar ${email}`}>
                        x
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="credential-muted">Sin usuarios en copia. Se puede agregar antes de enviar individual o grupal.</p>
              )}
              </div>
            </details>

            <label className="credential-field--wide">
              <span>Correos manuales</span>
              <textarea
                value={manualEmails}
                rows={4}
                onChange={(event) => setManualEmails(event.target.value)}
                placeholder="correo1@dominio.com&#10;correo2@dominio.com"
              />
            </label>
            <label className="credential-field--wide">
              <span>Mensaje editable</span>
              <textarea value={body} rows={8} onChange={(event) => setBody(event.target.value)} />
            </label>

            <details className="credential-field--wide mass-email-simple-details mass-email-simple-details--wide" open>
              <summary>Adjuntos y documentos</summary>
              <div className="mass-email-attachments-grid">
                <section className="mass-email-attachment-box mass-email-attachment-box--documents">
                <div className="mass-email-attachment-header">
                  <div>
                    <strong>Documentos por estudiante</strong>
                    <span>Primero se detecta la cédula del nombre del PDF; si existe en la base se asigna automáticamente.</span>
                  </div>
                  <div className="mass-email-document-stats">
                    <span>{studentFiles.length} documento(s)</span>
                    <span>{assignedStudentFileCount} asignado(s)</span>
                    <span>{Math.max(studentFiles.length - assignedStudentFileCount, 0)} pendiente(s)</span>
                  </div>
                </div>

                <div className="mass-email-document-toolbar">
                  <label className="mass-email-file-input">
                  <span>Subir documentos individuales</span>
                  <input type="file" multiple onChange={updateStudentFiles} />
                </label>
                  <label>
                    <span>Buscar estudiante o documento</span>
                    <input
                      value={assignmentSearch}
                      onChange={(event) => setAssignmentSearch(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault()
                          void executeAssignmentSearch()
                        }
                      }}
                      placeholder="Cédula, nombre, correo o nombre del archivo"
                    />
                  </label>
                  <label>
                    <span>Estado</span>
                    <select
                      value={assignmentStatusFilter}
                      onChange={(event) => setAssignmentStatusFilter(event.target.value as 'all' | 'assigned' | 'pending')}
                    >
                      <option value="all">Todos</option>
                      <option value="assigned">Asignados</option>
                      <option value="pending">Pendientes</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => void executeAssignmentSearch()}
                    disabled={assignmentSearchLoading}
                  >
                    {assignmentSearchLoading ? 'Buscando...' : 'Buscar y agregar'}
                  </button>
                </div>

                {studentFiles.length ? (
                  <div className="mass-email-assignment-list mass-email-assignment-list--table">
                    <div className="mass-email-file-row mass-email-file-row--head">
                      <span>Archivo</span>
                      <span>Cédula detectada</span>
                      <span>Estudiante asignado</span>
                      <span>Selección manual</span>
                      <span>Estado</span>
                      <span>Acción</span>
                    </div>
                    {filteredStudentFileRows.length ? (
                      filteredStudentFileRows.map((row) => {
                        const selectOptions =
                          row.assignedRecipient &&
                          !filteredAssignmentOptions.some((recipient) => normalizeCedula(recipient.cedula) === normalizeCedula(row.assignedCedula))
                            ? [row.assignedRecipient, ...filteredAssignmentOptions]
                            : filteredAssignmentOptions
                        return (
                          <div
                            className={`mass-email-file-row mass-email-file-row--${row.status}`}
                            key={`${row.file.name}-${row.file.size}-${row.file.lastModified}-${row.index}`}
                          >
                            <div className="mass-email-file-name">
                              <strong>{row.file.name}</strong>
                              <span>{fileSizeLabel(row.file.size)}</span>
                            </div>
                            <div>
                              <strong>{row.detectedCedula || '-'}</strong>
                              <small>{row.detectedCedula ? 'Desde nombre del archivo' : 'No detectada en nombre'}</small>
                            </div>
                            <div className="mass-email-file-recipient">
                              {row.assignedRecipient ? (
                                <>
                                  <strong>{valueOrDash(row.assignedRecipient.nombres || row.assignedRecipient.email)}</strong>
                                  <span>{row.assignedRecipient.email}</span>
                                  <small>{valueOrDash(row.assignedRecipient.cedula)} | {valueOrDash(row.assignedRecipient.source_table)}</small>
                                </>
                              ) : (
                                <>
                                  <strong>Sin asignar</strong>
                                  <span>Busca o selecciona el estudiante antes de enviar.</span>
                                  {row.detectedCedula ? <small>Cédula detectada pendiente de cargar en destinatarios.</small> : null}
                                </>
                              )}
                              {row.autoMatch && !row.assignedRecipient ? (
                                <small>Coincidencia sugerida: {recipientLabel(row.autoMatch)}</small>
                              ) : null}
                            </div>
                            <div className="mass-email-file-assignment">
                              <select
                                value={row.assignedCedula}
                                onChange={(event) => updateStudentFileAssignment(row.file.name, event.target.value)}
                              >
                                <option value="">Sin asignar</option>
                                {selectOptions.map((recipient) => (
                                  <option value={recipient.cedula} key={recipient.cedula}>
                                    {recipientLabel(recipient)}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <span
                                className={
                                  row.assignedRecipient
                                    ? 'credential-status credential-status--enviado'
                                    : 'credential-status credential-status--pendiente'
                                }
                              >
                                {row.assignedRecipient ? 'Asignado' : 'Pendiente'}
                              </span>
                            </div>
                            <div>
                              <button type="button" className="ghost-button" onClick={() => removeStudentFile(row.index)}>
                                Quitar
                              </button>
                            </div>
                          </div>
                        )
                      })
                    ) : (
                      <div className="mass-email-file-row mass-email-file-row--empty">
                        No hay documentos que coincidan con el filtro actual.
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="credential-muted">No hay documentos individuales cargados.</p>
                )}
                </section>

                <section className="mass-email-attachment-box">
                <div>
                  <strong>Documentos comunes para todos</strong>
                  <span>Estos archivos se adjuntan a todos los destinatarios seleccionados.</span>
                </div>
                <label className="mass-email-file-input">
                  <span>Subir documentos masivos</span>
                  <input type="file" multiple onChange={updateCommonFiles} />
                </label>
                {commonFiles.length ? (
                  <div className="mass-email-file-list">
                    {commonFiles.map((file, index) => (
                      <div key={`${file.name}-${file.size}-${file.lastModified}-${index}`}>
                        <div>
                          <strong>{file.name}</strong>
                          <span>{fileSizeLabel(file.size)}</span>
                        </div>
                        <button type="button" className="ghost-button" onClick={() => removeCommonFile(index)}>
                          Quitar
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="credential-muted">No hay documentos comunes cargados.</p>
                )}
                </section>
              </div>
            </details>

            <label className="credential-field--wide credential-send-toggle">
              <input
                type="checkbox"
                checked={matchAttachmentsByCedula}
                disabled={sendMode === 'single'}
                onChange={(event) => setMatchAttachmentsByCedula(event.target.checked)}
              />
              <span>
                Detectar cédula en el nombre o texto del PDF para asignar documentos individuales
                {sendMode === 'single' ? ' (los documentos personales se excluyen del correo único)' : ''}
              </span>
            </label>
          </div>

          <div className="credential-help">
            <strong>{sendMode === 'single' ? 'Envío en un solo correo:' : 'Envío independiente:'}</strong>
            {sendMode === 'single' ? (
              <>
                <span>Los destinatarios van en CCO y reciben el mismo contenido.</span>
                <span>Solo se envían documentos comunes para no compartir archivos personales.</span>
              </>
            ) : (
              <>
                <span>Cada usuario seleccionado recibe su propio correo.</span>
                <span>Los documentos por estudiante se envían solo al destinatario con cédula asignada o detectada.</span>
              </>
            )}
          </div>

          <div className="mass-email-phase-footer">
            <button type="button" className="ghost-button" onClick={() => setActivePhase(1)}>
              Volver a destinatarios
            </button>
            <button type="button" className="primary-action" onClick={goToReview}>
              Continuar a revisión
            </button>
          </div>
        </article>
        ) : null}

        {activePhase === 3 ? (
        <article className="student-card student-card--wide">
          <div className="card-head">
            <div>
              <span className="mass-email-step-label">Paso 3</span>
              <h3>Revisión y envío</h3>
              <p>Verifica destinatarios, documentos y modo de envío antes de confirmar.</p>
            </div>
            <div className="mass-email-review-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => setSelectedModalOpen(true)}
                disabled={!selectedRecipients.length && !manualEmailCount}
              >
                Ver involucrados
              </button>
              <button type="button" className="ghost-button" onClick={selectAllRecipients} disabled={!recipients.length}>
                Seleccionar todos
              </button>
              <button type="button" className="ghost-button" onClick={clearSelection} disabled={!recipients.length}>
                Limpiar
              </button>
              <button type="button" className="primary-action" onClick={() => void executeSend()} disabled={sending}>
                {sending ? 'Enviando...' : 'Enviar correos'}
              </button>
            </div>
          </div>

          <div className="mass-email-review-strip">
            <article>
              <span>Seleccionados</span>
              <strong>{selectedRecipients.length}</strong>
            </article>
            <article>
              <span>Manuales</span>
              <strong>{manualEmailCount}</strong>
            </article>
            <article>
              <span>Adjuntos</span>
              <strong>{totalAttachmentCount}</strong>
            </article>
            <article>
              <span>Modo</span>
              <strong>{sendMode === 'single' ? 'Único' : 'Individual'}</strong>
            </article>
          </div>

          {recipients.length ? (
            <div className="mass-email-recipient-cards">
              {recipients.map((recipient) => {
                const result = resultById.get(recipient.id)
                const isSelected = selectedIds.has(recipient.id)
                return (
                  <article
                    className={`mass-email-recipient-card${isSelected ? ' is-selected' : ''}`}
                    key={recipient.id}
                  >
                    <label className="mass-email-recipient-select">
                      <input type="checkbox" checked={isSelected} onChange={() => toggleRecipient(recipient.id)} />
                      <span>{isSelected ? 'Seleccionado' : 'Seleccionar'}</span>
                    </label>

                    <div className="mass-email-recipient-main">
                      <div>
                        <strong>{valueOrDash(recipient.nombres)}</strong>
                        <span>{valueOrDash(recipient.email)}</span>
                      </div>
                      <span className="credential-status">{valueOrDash(recipient.tipo_usuario || recipient.email_tipo)}</span>
                    </div>

                    <dl className="mass-email-recipient-meta">
                      <div>
                        <dt>Cédula</dt>
                        <dd>{valueOrDash(recipient.cedula)}</dd>
                      </div>
                      <div>
                        <dt>Código / login</dt>
                        <dd>{valueOrDash(recipient.codigo || recipient.login)}</dd>
                      </div>
                      <div>
                        <dt>Fuente</dt>
                        <dd>{valueOrDash(recipient.source_table)}</dd>
                      </div>
                      <div>
                        <dt>Estado envío</dt>
                        <dd>
                          {result ? (
                            <span className={`credential-status credential-status--${String(result.status || '').toLowerCase()}`}>
                              {valueOrDash(result.status)}
                            </span>
                          ) : (
                            <span className="credential-status credential-status--pendiente">Pendiente</span>
                          )}
                        </dd>
                      </div>
                    </dl>

                    {result ? (
                      <div className="mass-email-recipient-result">
                        {typeof result.attachment_count === 'number' ? <span>{result.attachment_count} adjunto(s)</span> : null}
                        {result.error ? <span>{result.error}</span> : null}
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          ) : (
            <div className="mass-email-recipient-empty">
              <strong>Sin destinatarios cargados</strong>
              <span>Busca por cédula o agrega usuarios desde la búsqueda para preparar el envío.</span>
            </div>
          )}

          <div className="mass-email-phase-footer">
            <button type="button" className="ghost-button" onClick={() => setActivePhase(2)}>
              Volver a mensaje
            </button>
            <button type="button" className="primary-action" onClick={() => void executeSend()} disabled={sending}>
              {sending ? 'Enviando...' : 'Enviar correos'}
            </button>
          </div>
        </article>
        ) : null}
      </section>

      {selectedModalOpen ? (
        <div className="mass-email-selected-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="mass-email-selected-title">
          <section className="mass-email-selected-modal">
            <header className="mass-email-selected-modal__head">
              <div>
                <span>Involucrados seleccionados</span>
                <h2 id="mass-email-selected-title">Destinatarios del envío</h2>
              </div>
              <button type="button" className="primary-action" onClick={() => setSelectedModalOpen(false)}>
                Cerrar
              </button>
            </header>

            <div className="mass-email-selected-modal__summary">
              <article>
                <span>Usuarios seleccionados</span>
                <strong>{selectedRecipients.length}</strong>
              </article>
              <article>
                <span>Correos manuales</span>
                <strong>{manualEmailList.length}</strong>
              </article>
              <article>
                <span>Total a enviar</span>
                <strong>{selectedRecipients.length + manualEmailList.length}</strong>
              </article>
            </div>

            <div className="mass-email-selected-modal__actions">
              <button type="button" className="ghost-button" onClick={selectAllRecipients} disabled={!recipients.length}>
                Seleccionar todos los encontrados
              </button>
              <button type="button" className="ghost-button" onClick={clearSelection} disabled={!selectedRecipients.length}>
                Quitar todos los seleccionados
              </button>
            </div>

            {selectedRecipients.length || manualEmailList.length ? (
              <div className="mass-email-selected-list">
                {selectedRecipients.map((recipient) => (
                  <article className="mass-email-selected-item" key={recipient.id}>
                    <div>
                      <strong>{valueOrDash(recipient.nombres || recipient.email)}</strong>
                      <span>{valueOrDash(recipient.email)}</span>
                      <small>{valueOrDash(recipient.cedula)} | {valueOrDash(recipient.tipo_usuario || recipient.email_tipo)} | {valueOrDash(recipient.source_table)}</small>
                    </div>
                    <button type="button" className="ghost-button" onClick={() => removeSelectedRecipient(recipient.id)}>
                      Quitar
                    </button>
                  </article>
                ))}
                {manualEmailList.map((email) => (
                  <article className="mass-email-selected-item mass-email-selected-item--manual" key={email}>
                    <div>
                      <strong>{email}</strong>
                      <span>Correo ingresado manualmente</span>
                      <small>No proviene de una tabla del sistema.</small>
                    </div>
                    <button type="button" className="ghost-button" onClick={() => removeManualEmail(email)}>
                      Quitar
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="mass-email-recipient-empty">
                <strong>Sin involucrados seleccionados</strong>
                <span>Busca destinatarios o agrega correos manuales antes de continuar.</span>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {previewModalOpen ? (
        <div className="mass-email-selected-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="mass-email-preview-title">
          <section className="mass-email-selected-modal mass-email-preview-modal">
            <header className="mass-email-selected-modal__head">
              <div>
                <span>Vista previa institucional</span>
                <h2 id="mass-email-preview-title">Correo a enviar</h2>
              </div>
              <button type="button" className="primary-action" onClick={() => setPreviewModalOpen(false)}>
                Cerrar
              </button>
            </header>

            <div className="mass-email-mail-preview mass-email-mail-preview--modal">
              <div className="mass-email-mail-preview__bar" />
              <div className="mass-email-mail-preview__header">
                <img src={intecLogoPath} alt="INTEC" />
                <span>Comunicación institucional</span>
              </div>
              <div className="mass-email-mail-preview__body">
                <strong>{subject.trim() || 'Asunto del correo'}</strong>
                {(body.trim() || defaultBody)
                  .split(/\n\s*\n/)
                  .filter(Boolean)
                  .slice(0, 8)
                  .map((paragraph, index) => (
                    <p key={`${paragraph}-${index}`}>
                      {paragraph.split('\n').map((line, lineIndex) => (
                        <span key={`${line}-${lineIndex}`}>
                          {line}
                          {lineIndex < paragraph.split('\n').length - 1 ? <br /> : null}
                        </span>
                      ))}
                    </p>
                  ))}
              </div>
              <div className="mass-email-mail-preview__footer">{institutionName}</div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
