import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  fetchTeamStatus,
  fetchTeamAttendance,
  fetchTeamCourses,
  fetchTeamMessages,
  fetchTeamParticipants,
  fetchTeamRecordings,
  inviteMissingParticipants,
} from '../../lib/api'
import type {
  GraphTeam,
  TeamCallStatus,
  TeamAttendance,
  TeamCourse,
  TeamMessage,
  TeamParticipant,
  TeamRecording,
  TeamRecordingDiscovery,
  TeamRecordingSummary,
} from '../../types/app'

type TeamsViewProps = {
  displayName: string
  catalogLoading: boolean
  catalogMessage: string
  catalogError: string
  catalogTeams: GraphTeam[]
  selectedTeamIndex: number | null
  selectedTeam: GraphTeam | null
  onLoadCatalog: () => void
  onSelectTeam: (index: number) => void
  onTeamIdFromCatalog: (teamId: string) => void
}

type TeamInfoTab = 'status' | 'participants' | 'courses' | 'recordings' | 'attendance' | 'messages'
type InfoSummaryItem = { label: string; value: string | number }
type InfoMetaItem = { label: string; value?: string | number | null }
type MessageThread = { root: TeamMessage; replies: TeamMessage[] }
type AcademicTeamIdentity = {
  teamName: string
  mail: string
  mailAlias: string
  roundLabel: string
  academicYear: string
  subject: string
  parallel: string
  teacher: string
  schedule: string
  confidence: 'Alta' | 'Media' | 'Baja'
  warnings: string[]
}
type CourseChannelAnalysis = {
  course: TeamCourse
  isDefaultChannel: boolean
  subjectMatch: boolean
  parallelMatch: boolean
  related: boolean
  relationLabel: string
}

const ECUADOR_TIME_ZONE = 'America/Guayaquil'

const normalizeGraphDateInput = (value?: string | null): string | null => {
  if (!value) {
    return null
  }

  const text = value.trim()
  if (!text) return null

  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(text)
  return hasTimezone ? text : `${text}Z`
}

const formatInEcuador = (
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions
): string | null => {
  const normalized = normalizeGraphDateInput(value)
  if (!normalized) return null

  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return value || null
  }

  return new Intl.DateTimeFormat('es-EC', {
    timeZone: ECUADOR_TIME_ZONE,
    ...options,
  }).format(parsed)
}

const formatDateTimeInEcuador = (value?: string | null): string | null => {
  return formatInEcuador(value, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

const formatDateOnlyInEcuador = (value?: string | null): string | null => {
  return formatInEcuador(value, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

const formatTimeOnlyInEcuador = (value?: string | null): string | null => {
  return formatInEcuador(value, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

const formatDurationFromSeconds = (value: number): string => {
  if (!Number.isFinite(value) || value < 0) return 'N/D'

  const totalSeconds = Math.round(value)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${String(hours).padStart(2, '0')} h ${String(minutes).padStart(2, '0')} min ${String(seconds).padStart(2, '0')} s`
}

const timestampValue = (value?: string | null): number => {
  if (!value) return 0
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? 0 : parsed
}

const messageThreadKey = (message: TeamMessage): string => {
  return String(message.id || message.rootMessageId || message.threadSubject || message.createdDateTime || 'thread')
}

const messageGroupKey = (message: TeamMessage): string => {
  const channelKey = String(message.channelId || message.channelName || 'general').trim().toLowerCase()
  const dateKey =
    formatDateOnlyInEcuador(message.threadCreatedDateTime || message.createdDateTimeEcuador || message.createdDateTime) ||
    'sin-fecha'
  return `${channelKey}|${dateKey}`
}

const messageIdentityKey = (message: TeamMessage): string => {
  return [
    message.id,
    message.channelId,
    message.parentMessageId,
    message.rootMessageId,
    message.createdDateTime,
    message.subject,
    message.bodyText,
    message.bodyPreview,
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .join('|')
}

const normalizeForMatch = (value?: string | null): string => {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

const compactMatchText = (value?: string | null): string => normalizeForMatch(value).replace(/\s+/g, '')

const isInternalPublicationActivity = (message: TeamMessage): boolean => {
  if (message.isReply) return false

  const typeText = normalizeForMatch([message.eventDetailType, message.activityType, message.messageType].join(' '))
  const contentText = normalizeForMatch(
    [
      message.subject,
      message.threadSubject,
      message.eventDetailText,
      message.summary,
      message.bodyText,
      message.bodyPreview,
      message.activityLabel,
    ].join(' ')
  )

  if (typeText && /(recording|transcript|meeting|call|evento|grabacion)/.test(typeText)) {
    return true
  }

  const internalTerms = [
    'comenzo a grabar',
    'empezo a grabar',
    'grabacion detenida',
    'grabacion se ha guardado',
    'grabacion guardada',
    'reunion finalizada',
    'reunion en general finalizo',
    'recording started',
    'recording stopped',
    'recording saved',
    'meeting ended',
  ]

  return internalTerms.some((term) => contentText.includes(term))
}

const isPublicationRoot = (message: TeamMessage): boolean => {
  if (message.isReply) return false
  if ((message.replyCount || 0) > 0) return true
  if (isInternalPublicationActivity(message)) return false
  if (String(message.subject || '').trim()) return true
  return Boolean(String(message.bodyText || message.bodyPreview || message.summary || '').trim())
}

const sameMessageDay = (first: TeamMessage, second: TeamMessage): boolean => {
  const firstDate = formatDateOnlyInEcuador(first.createdDateTimeEcuador || first.createdDateTime)
  const secondDate = formatDateOnlyInEcuador(second.createdDateTimeEcuador || second.createdDateTime)
  return Boolean(firstDate && secondDate && firstDate === secondDate)
}

const findNearestMessageThread = (
  message: TeamMessage,
  threads: MessageThread[]
): MessageThread | null => {
  const messageTime = timestampValue(message.createdDateTime)
  const channelKey = String(message.channelId || message.channelName || '').trim()
  const candidates = threads
    .filter((thread) => {
      const rootChannelKey = String(thread.root.channelId || thread.root.channelName || '').trim()
      return (!channelKey || !rootChannelKey || channelKey === rootChannelKey) && sameMessageDay(message, thread.root)
    })
    .map((thread) => ({
      thread,
      distance: Math.abs(messageTime - timestampValue(thread.root.createdDateTime)),
    }))
    .sort((a, b) => a.distance - b.distance)

  return candidates[0]?.thread || null
}

const buildMessageThreads = (items: TeamMessage[]): MessageThread[] => {
  const orderedMessages = [...items].sort(
    (a, b) => timestampValue(a.createdDateTime) - timestampValue(b.createdDateTime)
  )
  const repliesByRoot = new Map<string, TeamMessage[]>()
  const consumedMessageKeys = new Set<string>()

  for (const reply of orderedMessages.filter((item) => item.isReply)) {
    const rootKey = String(reply.parentMessageId || reply.rootMessageId || '').trim()
    if (!rootKey) continue
    const replies = repliesByRoot.get(rootKey) || []
    replies.push(reply)
    repliesByRoot.set(rootKey, replies)
    consumedMessageKeys.add(messageIdentityKey(reply))
  }

  const rootCandidates = orderedMessages.filter((item) => !item.isReply)
  const rootsByGroup = new Map<string, TeamMessage[]>()
  for (const root of rootCandidates) {
    const groupKey = messageGroupKey(root)
    const groupRoots = rootsByGroup.get(groupKey) || []
    groupRoots.push(root)
    rootsByGroup.set(groupKey, groupRoots)
  }

  let rootMessages: TeamMessage[] = []
  for (const roots of rootsByGroup.values()) {
    const rootsWithReplies = roots.filter((root) => {
      const rootKey = String(root.id || root.rootMessageId || '').trim()
      return (root.replyCount || 0) > 0 || (rootKey ? (repliesByRoot.get(rootKey) || []).length > 0 : false)
    })
    rootMessages.push(...(rootsWithReplies.length > 0 ? rootsWithReplies : roots.filter(isPublicationRoot)))
  }

  if (rootMessages.length === 0) {
    rootMessages = rootCandidates
  }

  const threads = rootMessages.map((root) => {
    const rootKey = String(root.id || root.rootMessageId || '').trim()
    consumedMessageKeys.add(messageIdentityKey(root))
    return {
      root,
      replies: [...(repliesByRoot.get(rootKey) || [])],
    }
  })

  for (const message of orderedMessages) {
    const messageKey = messageIdentityKey(message)
    if (consumedMessageKeys.has(messageKey)) continue

    const targetThread = findNearestMessageThread(message, threads)
    if (targetThread) {
      targetThread.replies.push({
        ...message,
        isReply: true,
        parentMessageId: targetThread.root.id || targetThread.root.rootMessageId || null,
        rootMessageId: targetThread.root.id || targetThread.root.rootMessageId || message.rootMessageId,
        threadSubject: targetThread.root.subject || targetThread.root.threadSubject || message.threadSubject,
      })
      consumedMessageKeys.add(messageKey)
      continue
    }

    if (!message.isReply) {
      threads.push({ root: message, replies: [] })
      consumedMessageKeys.add(messageKey)
    }
  }

  return threads
    .map((thread) => ({
      root: thread.root,
      replies: thread.replies.sort(
        (a, b) => timestampValue(a.createdDateTime) - timestampValue(b.createdDateTime)
      ),
    }))
    .sort((a, b) => timestampValue(b.root.createdDateTime) - timestampValue(a.root.createdDateTime))
}

const extractAcademicIdentity = (team: GraphTeam | null): AcademicTeamIdentity => {
  const teamName = String(team?.displayName || '').trim()
  const mail = String(team?.mail || '').trim()
  const mailAlias = mail.split('@')[0] || ''
  const source = teamName || mailAlias
  const parts = source.split(/\s+-\s+/).map((item) => item.trim()).filter(Boolean)
  const withoutTeacher = source.replace(/\s*[-–]\s*Docente:.*$/i, '').trim()
  const withoutRound = withoutTeacher.replace(/^\s*R\d+\s*[-–]\s*/i, '').trim()
  const academicPart =
    parts.find((part) => !/^R\d+$/i.test(part) && !/^Docente:/i.test(part) && !/^De\s+/i.test(part)) ||
    withoutRound
  const parallelMatch = [...academicPart.matchAll(/\b(ABS|PBS\d+|PB\d+|G\d+)\b/gi)].pop()
  const parallel = parallelMatch?.[1]?.toUpperCase() || ''
  const subject =
    parallelMatch && parallelMatch.index !== undefined
      ? academicPart.slice(0, parallelMatch.index).replace(/[-–\s]+$/g, '').trim()
      : academicPart.trim()
  const teacherPart = parts.find((part) => /^Docente:/i.test(part))
  const schedulePart = parts.find((part) => /^De\s+/i.test(part) || /\b\d{1,2}h\d{2}\b/i.test(part))
  const roundLabel = source.match(/\bR\d+\b/i)?.[0]?.toUpperCase() || ''
  const academicYear = mailAlias.match(/\b20\d{2}\b/)?.[0] || source.match(/\b20\d{2}\b/)?.[0] || ''
  const teacher = String(teacherPart || '').replace(/^Docente:\s*/i, '').trim()
  const schedule = schedulePart || ''
  const warnings = [
    subject ? '' : 'Materia no detectada desde el nombre del Team.',
    parallel ? '' : 'Paralelo no detectado desde el nombre del Team.',
    teacher ? '' : 'Docente no detectado desde el nombre del Team.',
    schedule ? '' : 'Horario no detectado desde el nombre del Team.',
  ].filter(Boolean)
  const confidence = subject && parallel && (teacher || schedule) ? 'Alta' : subject && parallel ? 'Media' : 'Baja'

  return {
    teamName,
    mail,
    mailAlias,
    roundLabel,
    academicYear,
    subject,
    parallel,
    teacher,
    schedule,
    confidence,
    warnings,
  }
}

const analyzeCourseChannel = (course: TeamCourse, identity: AcademicTeamIdentity): CourseChannelAnalysis => {
  const channelName = String(course.displayName || '').trim()
  const channelText = normalizeForMatch([course.displayName, course.description, course.membershipType].join(' '))
  const compactChannelText = compactMatchText([course.displayName, course.description].join(' '))
  const subjectText = normalizeForMatch(identity.subject)
  const compactSubject = compactMatchText(identity.subject)
  const subjectTokens = subjectText.split(/\s+/).filter((token) => token.length >= 4)
  const matchedSubjectTokens = subjectTokens.filter((token) => channelText.includes(token)).length
  const subjectMatch = Boolean(
    subjectText &&
      (channelText.includes(subjectText) ||
        compactChannelText.includes(compactSubject) ||
        (subjectTokens.length > 0 && matchedSubjectTokens >= Math.min(2, subjectTokens.length)))
  )
  const parallelMatch = Boolean(identity.parallel && channelText.includes(identity.parallel.toLowerCase()))
  const isDefaultChannel = ['general', 'general del equipo'].includes(normalizeForMatch(channelName))
  const related = subjectMatch || parallelMatch
  const relationLabel =
    subjectMatch && parallelMatch
      ? 'Coincide materia y paralelo'
      : subjectMatch
        ? 'Coincide materia'
        : parallelMatch
          ? 'Coincide paralelo'
          : isDefaultChannel
            ? 'Canal base'
            : 'Sin coincidencia academica'

  return {
    course,
    isDefaultChannel,
    subjectMatch,
    parallelMatch,
    related,
    relationLabel,
  }
}

function InfoSummary({ items }: Readonly<{ items: InfoSummaryItem[] }>) {
  return (
    <div className="teams-info-summary">
      {items.map((item) => (
        <span key={item.label}>
          <strong>{item.value}</strong>
          <small>{item.label}</small>
        </span>
      ))}
    </div>
  )
}

function InfoMetaGrid({ items }: Readonly<{ items: InfoMetaItem[] }>) {
  return (
    <dl className="teams-meta-grid">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value || 'N/D'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function TeamsView({
  displayName,
  catalogLoading,
  catalogMessage,
  catalogError,
  catalogTeams,
  selectedTeamIndex,
  selectedTeam,
  onLoadCatalog,
  onSelectTeam,
  onTeamIdFromCatalog,
}: Readonly<TeamsViewProps>) {
  const redirectToMicrosoftConnect = useCallback((teamId: string, connectUrl?: string) => {
    const resolvedConnectUrl = connectUrl || `/api/auth/microsoft/connect?team_id=${encodeURIComponent(teamId)}`
    globalThis.location.href = resolvedConnectUrl
  }, [])

  const isMicrosoftConnectRequiredError = useCallback((error: unknown): error is ApiError => {
    return error instanceof ApiError && error.message.toLowerCase().includes('debes conectar microsoft')
  }, [])

  const [isTeamsModalOpen, setIsTeamsModalOpen] = useState(false)
  const [isTeamDetailScreenOpen, setIsTeamDetailScreenOpen] = useState(false)
  const [teamNameFilter, setTeamNameFilter] = useState('')
  const [modalTeamIndex, setModalTeamIndex] = useState<number | null>(null)
  const [activeInfoTab, setActiveInfoTab] = useState<TeamInfoTab>('participants')
  const [callStatus, setCallStatus] = useState<TeamCallStatus | null>(null)
  const [participants, setParticipants] = useState<TeamParticipant[]>([])
  const [courses, setCourses] = useState<TeamCourse[]>([])
  const [recordings, setRecordings] = useState<TeamRecording[]>([])
  const [recordingSummary, setRecordingSummary] = useState<TeamRecordingSummary | null>(null)
  const [recordingDiscovery, setRecordingDiscovery] = useState<TeamRecordingDiscovery | null>(null)
  const [attendance, setAttendance] = useState<TeamAttendance[]>([])
  const [messages, setMessages] = useState<TeamMessage[]>([])
  const [teamInfoLoading, setTeamInfoLoading] = useState(false)
  const [teamInfoError, setTeamInfoError] = useState('')
  const [teamInfoMessage, setTeamInfoMessage] = useState('')
  const [joinRequestUrl, setJoinRequestUrl] = useState('')
  const [joinRequestCount, setJoinRequestCount] = useState<number>(0)
  const [inviteLoading, setInviteLoading] = useState(false)
  const [attendanceNote, setAttendanceNote] = useState('')
  const [lastRefreshAt, setLastRefreshAt] = useState<string>('')
  const [openMessageThreadKeys, setOpenMessageThreadKeys] = useState<string[]>([])

  const toErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof ApiError) return error.message
    if (error instanceof Error) return error.message
    return 'No se pudo cargar la informacion del equipo seleccionado.'
  }, [])

  const filteredTeams = useMemo(() => {
    const normalizedFilter = teamNameFilter.trim().toLowerCase()
    if (!normalizedFilter) {
      return catalogTeams.map((team, index) => ({ team, index }))
    }

    return catalogTeams
      .map((team, index) => ({ team, index }))
      .filter(({ team }) => (team.displayName || '').toLowerCase().includes(normalizedFilter))
  }, [catalogTeams, teamNameFilter])

  const modalSelectedTeam =
    modalTeamIndex === null || modalTeamIndex < 0 || modalTeamIndex >= catalogTeams.length
      ? null
      : catalogTeams[modalTeamIndex]

  const academicIdentity = useMemo(
    () => extractAcademicIdentity(modalSelectedTeam),
    [modalSelectedTeam]
  )

  const courseChannelAnalyses = useMemo(
    () => courses.map((course) => analyzeCourseChannel(course, academicIdentity)),
    [academicIdentity, courses]
  )

  const relatedCourseChannels = useMemo(
    () => courseChannelAnalyses.filter((item) => item.related),
    [courseChannelAnalyses]
  )

  const courseAlignmentLabel = useMemo(() => {
    if (!academicIdentity.subject && !academicIdentity.parallel) return 'Sin identidad'
    if (courseChannelAnalyses.some((item) => item.subjectMatch && item.parallelMatch)) return 'Alta'
    if (relatedCourseChannels.length > 0) return 'Parcial'
    return 'No coincide'
  }, [academicIdentity.parallel, academicIdentity.subject, courseChannelAnalyses, relatedCourseChannels.length])

  const courseSummaryItems = useMemo<InfoSummaryItem[]>(
    () => [
      { label: 'Materia detectada', value: academicIdentity.subject || 'N/D' },
      { label: 'Paralelo', value: academicIdentity.parallel || 'N/D' },
      { label: 'Canales Teams', value: courses.length },
      { label: 'Coincidencia', value: courseAlignmentLabel },
    ],
    [academicIdentity.parallel, academicIdentity.subject, courseAlignmentLabel, courses.length]
  )

  const ownerParticipants = useMemo(
    () => participants.filter((item) => item.isOwner),
    [participants]
  )

  const memberParticipants = useMemo(
    () => participants.filter((item) => item.isMember),
    [participants]
  )

  const participantSummaryItems = useMemo<InfoSummaryItem[]>(
    () => [
      { label: 'Personas', value: participants.length },
      { label: 'Propietarios', value: ownerParticipants.length },
      { label: 'Miembros', value: memberParticipants.length },
      {
        label: 'Propietarios miembros',
        value: participants.filter((item) => item.isOwner && item.isMember).length,
      },
    ],
    [memberParticipants.length, ownerParticipants.length, participants]
  )

  const latestRecording = useMemo(
    () =>
      recordings.reduce<TeamRecording | null>((latest, current) => {
        const currentTime = timestampValue(current.fileCreatedAt || current.uploadedAt || current.lastModifiedDateTime)
        const latestTime = timestampValue(latest?.fileCreatedAt || latest?.uploadedAt || latest?.lastModifiedDateTime)
        return currentTime > latestTime ? current : latest
      }, null),
    [recordings]
  )

  const messageThreads = useMemo<MessageThread[]>(() => {
    return buildMessageThreads(messages)
  }, [messages])

  const messageGlobalSummaryItems = useMemo<InfoSummaryItem[]>(
    () => [{ label: 'Mensajes globales', value: messageThreads.length }],
    [messageThreads.length]
  )

  useEffect(() => {
    setOpenMessageThreadKeys((current) => {
      const availableKeys = new Set(messageThreads.map((thread) => messageThreadKey(thread.root)))
      const next = current.filter((key) => availableKeys.has(key))
      return next.length === current.length ? current : next
    })
  }, [messageThreads])

  const recordingSummaryItems = useMemo<InfoSummaryItem[]>(() => {
    const totalSeconds = recordings.reduce((total, item) => total + (item.durationSeconds || 0), 0)
    const knownDurations = recordings.filter((item) => Number.isFinite(item.durationSeconds)).length
    return [
      { label: 'Grabaciones', value: recordings.length },
      {
        label: 'Duración multimedia total',
        value: knownDurations > 0
          ? recordingSummary?.totalDurationLabel || formatDurationFromSeconds(totalSeconds)
          : 'Sin metadatos',
      },
      {
        label: 'Duración verificada',
        value: `${recordingSummary?.knownDurationCount ?? knownDurations} / ${recordings.length}`,
      },
      {
        label: 'Horarios verificados',
        value: `${recordingDiscovery?.verifiedTimeCount || 0} / ${recordings.length}`,
      },
      {
        label: 'Metadatos completos',
        value: `${recordingSummary?.completeMetadataCount ?? recordings.filter((item) => item.metadataStatus === 'COMPLETA').length} / ${recordings.length}`,
      },
      {
        label: 'Ubicaciones consultadas',
        value: `${recordingDiscovery?.sourcesSucceeded || 0} / ${recordingDiscovery?.sourcesScanned || 0}`,
      },
      {
        label: 'SharePoint / OneDrive',
        value: `${(recordingDiscovery?.sourceCounts?.TEAM_SHAREPOINT || 0) + (recordingDiscovery?.sourceCounts?.CHANNEL_SHAREPOINT || 0)} / ${recordingDiscovery?.sourceCounts?.OWNER_ONEDRIVE || 0}`,
      },
      {
        label: 'Tiempo de consulta',
        value: recordingDiscovery?.queryElapsedMs != null
          ? `${recordingDiscovery.queryElapsedMs} ms${recordingDiscovery.cacheHit ? ' · caché' : ''}`
          : 'N/D',
      },
      {
        label: 'Último archivo creado EC',
        value: latestRecording?.fileCreatedDateLabel || latestRecording?.uploadedDateLabel || formatDateTimeInEcuador(latestRecording?.fileCreatedAt || latestRecording?.uploadedAt) || 'N/D',
      },
      { label: 'Hora de creación EC', value: latestRecording?.fileCreatedHourLabel || latestRecording?.uploadedHourLabel || 'N/D' },
    ]
  }, [latestRecording, recordingDiscovery, recordingSummary, recordings])

  const loadTeamInfo = useCallback(async (teamId: string) => {
    setTeamInfoError('')
    setTeamInfoLoading(true)
    setAttendanceNote('')

    const [statusResult, participantsResult, coursesResult, recordingsResult, attendanceResult, messagesResult] =
      await Promise.allSettled([
        fetchTeamStatus(teamId),
        fetchTeamParticipants(teamId),
        fetchTeamCourses(teamId),
        fetchTeamRecordings(teamId),
        fetchTeamAttendance(teamId),
        fetchTeamMessages(teamId),
      ])

    if (statusResult.status === 'fulfilled') {
      setCallStatus(statusResult.value)
      if (statusResult.value.note) {
        setTeamInfoMessage((current) => current || statusResult.value.note || '')
      }
    } else {
      setCallStatus(null)
      setTeamInfoError(toErrorMessage(statusResult.reason))
    }

    if (participantsResult.status === 'fulfilled') {
      setParticipants(participantsResult.value.value || [])
    } else {
      setParticipants([])
      setTeamInfoError(toErrorMessage(participantsResult.reason))
    }

    if (coursesResult.status === 'fulfilled') {
      setCourses(coursesResult.value.value || [])
    } else {
      setCourses([])
      setTeamInfoError((current) => current || toErrorMessage(coursesResult.reason))
    }

    if (recordingsResult.status === 'fulfilled') {
      setRecordings(recordingsResult.value.value || [])
      setRecordingSummary(recordingsResult.value.summary || null)
      setRecordingDiscovery(recordingsResult.value.discovery || null)
    } else {
      setRecordings([])
      setRecordingSummary(null)
      setRecordingDiscovery(null)
      setTeamInfoError((current) => current || toErrorMessage(recordingsResult.reason))
    }

    if (attendanceResult.status === 'fulfilled') {
      setAttendance(attendanceResult.value.value || [])
      setAttendanceNote(attendanceResult.value.note || '')
    } else {
      setAttendance([])
      setAttendanceNote('')
      setTeamInfoError((current) => current || toErrorMessage(attendanceResult.reason))
    }

    if (messagesResult.status === 'fulfilled') {
      setMessages(messagesResult.value.value || [])
    } else {
      setMessages([])
      setTeamInfoError((current) => current || toErrorMessage(messagesResult.reason))
    }

    setLastRefreshAt(
      new Intl.DateTimeFormat('es-EC', {
        timeZone: ECUADOR_TIME_ZONE,
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      }).format(new Date())
    )
    setTeamInfoLoading(false)
  }, [toErrorMessage])

  useEffect(() => {
    const url = new URL(globalThis.location.href)
    const teamId = url.searchParams.get('auto_invite_team_id')
    const msConnected = url.searchParams.get('ms_connected')

    if (!teamId || msConnected !== '1') {
      return
    }

    const run = async () => {
      try {
        setIsTeamsModalOpen(true)
        setIsTeamDetailScreenOpen(true)
        setActiveInfoTab('status')
        setTeamInfoError('')
        setTeamInfoMessage('Ejecutando invitacion masiva automatica...')

        const result = await inviteMissingParticipants(teamId)
        if (result.needs_microsoft_connect) {
          redirectToMicrosoftConnect(teamId, result.connect_url)
          return
        }
        setTeamInfoMessage(result.message || 'Invitacion automatica completada.')
        await loadTeamInfo(teamId)
      } catch (error) {
        if (isMicrosoftConnectRequiredError(error)) {
          redirectToMicrosoftConnect(teamId)
          return
        }
        setTeamInfoError(toErrorMessage(error))
      } finally {
        url.searchParams.delete('ms_connected')
        url.searchParams.delete('auto_invite_team_id')
        url.searchParams.delete('open_page')
        globalThis.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
      }
    }

    void run()
  }, [isMicrosoftConnectRequiredError, loadTeamInfo, redirectToMicrosoftConnect, toErrorMessage])

  const handleInfoTabClick = (tab: TeamInfoTab) => {
    setActiveInfoTab(tab)
  }

  const closeTeamsModal = () => {
    setIsTeamsModalOpen(false)
    setIsTeamDetailScreenOpen(false)
  }

  const openTeamsModal = () => {
    const initialIndex = selectedTeamIndex ?? (catalogTeams.length > 0 ? 0 : null)
    setIsTeamsModalOpen(true)
    setIsTeamDetailScreenOpen(false)
    setTeamNameFilter('')
    setActiveInfoTab('status')
    setModalTeamIndex(initialIndex)
    setTeamInfoError('')
    setTeamInfoMessage('')
    setJoinRequestUrl('')
    setJoinRequestCount(0)
    setLastRefreshAt('')

    if (initialIndex !== null) {
      const team = catalogTeams[initialIndex]
      if (team?.id) {
        void loadTeamInfo(team.id)
      }
    }
  }

  const handlePickTeam = (index: number) => {
    const team = catalogTeams[index]
    setModalTeamIndex(index)
    setIsTeamDetailScreenOpen(true)
    setActiveInfoTab('status')
    setTeamInfoError('')
    setTeamInfoMessage('')
    setJoinRequestUrl('')
    setJoinRequestCount(0)
    onSelectTeam(index)
    if (team?.id) {
      onTeamIdFromCatalog(team.id)
      void loadTeamInfo(team.id)
    }
  }

  const refreshSelectedTeamInfo = () => {
    if (modalSelectedTeam?.id) {
      void loadTeamInfo(modalSelectedTeam.id)
    }
  }

  const toggleMessageThread = (threadKey: string) => {
    setOpenMessageThreadKeys((current) =>
      current.includes(threadKey)
        ? current.filter((item) => item !== threadKey)
        : [...current, threadKey]
    )
  }

  const handleInviteMissing = async () => {
    if (!modalSelectedTeam?.id) {
      setTeamInfoError('Selecciona un equipo para invitar participantes faltantes.')
      return
    }

    setInviteLoading(true)
    setTeamInfoError('')
    setTeamInfoMessage('')
    setJoinRequestUrl('')
    setJoinRequestCount(0)

    try {
      const result = await inviteMissingParticipants(modalSelectedTeam.id)
      setTeamInfoMessage(result.message || 'Invitacion procesada correctamente.')

      if (result.needs_microsoft_connect) {
        redirectToMicrosoftConnect(modalSelectedTeam.id, result.connect_url)
        return
      }

      if (result.request_type === 'join-call-request') {
        setJoinRequestUrl(result.join_web_url || '')
        setJoinRequestCount(result.missing_participants?.length || 0)
      }

      await loadTeamInfo(modalSelectedTeam.id)
    } catch (error) {
      if (isMicrosoftConnectRequiredError(error)) {
        redirectToMicrosoftConnect(modalSelectedTeam.id)
        return
      }
      setTeamInfoError(toErrorMessage(error))
    } finally {
      setInviteLoading(false)
    }
  }

  const renderPublicationReply = (item: TeamMessage) => {
    const ecuadorDateTime = item.createdDateTimeEcuador || item.createdDateTime
    const ecuadorHour = formatTimeOnlyInEcuador(ecuadorDateTime) || item.createdHourLabel || 'N/D'
    const replyText = String(item.bodyText || item.bodyPreview || item.summary || item.eventDetailText || '').trim()

    return (
      <div key={messageIdentityKey(item)} className="teams-thread-inline-reply">
        <strong>{item.from || 'Sin remitente'}</strong>
        <span>{ecuadorHour} EC</span>
        <p>{replyText || 'Sin contenido'}</p>
      </div>
    )
  }

  const renderMessageThreadPreview = (thread: MessageThread) => {
    const root = thread.root
    const threadKey = messageThreadKey(root)
    const isOpen = openMessageThreadKeys.includes(threadKey)
    const ecuadorDateTime = root.createdDateTimeEcuador || root.createdDateTime
    const ecuadorDate = formatDateOnlyInEcuador(ecuadorDateTime) || root.createdDateLabel || 'Sin fecha'
    const ecuadorHour = formatTimeOnlyInEcuador(ecuadorDateTime) || root.createdHourLabel || 'N/D'
    const visibleReplies = thread.replies.filter((reply) => !isInternalPublicationActivity(reply))
    const repliesToShow = isOpen ? visibleReplies : visibleReplies.slice(0, 1)
    const replyAuthors = Array.from(
      new Set(visibleReplies.map((reply) => String(reply.from || '').trim()).filter(Boolean))
    )
    const replyLabel =
      visibleReplies.length === 0
        ? ''
        : `Abrir ${visibleReplies.length} respuesta${visibleReplies.length === 1 ? '' : 's'}${
            replyAuthors[0] ? ` de ${replyAuthors[0]}` : ''
          }`
    const title = root.subject || root.threadSubject || 'Mensaje de canal'
    const rootText = [root.bodyText, root.summary, root.eventDetailText]
      .map((value) => String(value || '').trim())
      .find((value) => value && normalizeForMatch(value) !== normalizeForMatch(title))

    return (
      <article key={threadKey} className="teams-message-thread">
        <div className="teams-channel-post-card">
          <div className="teams-channel-post-card__meta">
            <strong>{root.from || 'Sin remitente'}</strong>
            <span>{ecuadorDate} | {ecuadorHour} EC</span>
            <small>{root.channelName || 'Sin canal'}</small>
          </div>
          <h4>{title}</h4>
          {rootText ? <p>{rootText}</p> : null}
          {replyLabel ? (
            <div className="teams-channel-post-card__actions">
              <button type="button" className="teams-thread-toggle" onClick={() => toggleMessageThread(threadKey)}>
                {isOpen && visibleReplies.length > 1 ? 'Ocultar respuestas' : replyLabel}
              </button>
            </div>
          ) : null}

          {repliesToShow.length > 0 ? (
            <div className="teams-thread-replies">
              {repliesToShow.map((reply) => renderPublicationReply(reply))}
            </div>
          ) : null}
        </div>
      </article>
    )
  }

  const renderInfoContent = () => {
    if (teamInfoLoading) {
      return <p className="teams-message">Cargando informacion del equipo...</p>
    }

    if (activeInfoTab === 'participants') {
      return (
        <div className="teams-activity-section">
          <InfoSummary items={participantSummaryItems} />

          <article className="teams-activity-card">
            <div className="teams-activity-card__head">
              <strong>Propietarios</strong>
              <span>{ownerParticipants.length}</span>
            </div>
            <div className="teams-data-list">
              {ownerParticipants.length > 0 ? (
                ownerParticipants.map((item) => (
                  <article key={`owner-${item.id || item.userPrincipalName || item.displayName}`}>
                    <strong>{item.displayName || 'Sin nombre'}</strong>
                    <span>{item.mail || item.userPrincipalName || 'Sin correo'}</span>
                    <span>{item.roleLabel || 'Propietario'}</span>
                  </article>
                ))
              ) : (
                <p className="empty-block">No hay propietarios disponibles.</p>
              )}
            </div>
          </article>

          <article className="teams-activity-card">
            <div className="teams-activity-card__head">
              <strong>Miembros</strong>
              <span>{memberParticipants.length}</span>
            </div>
            <div className="teams-data-list">
              {memberParticipants.length > 0 ? (
                memberParticipants.map((item) => (
                  <article key={`member-${item.id || item.userPrincipalName || item.displayName}`}>
                    <strong>{item.displayName || 'Sin nombre'}</strong>
                    <span>{item.mail || item.userPrincipalName || 'Sin correo'}</span>
                    <span>{item.roleLabel || 'Miembro'}</span>
                  </article>
                ))
              ) : (
                <p className="empty-block">No hay miembros disponibles.</p>
              )}
            </div>
          </article>
        </div>
      )
    }

    if (activeInfoTab === 'courses') {
      return (
        <div className="teams-activity-section">
          <InfoSummary items={courseSummaryItems} />

          <article className="teams-activity-card teams-course-insight">
            <div className="teams-activity-card__head">
              <strong>Identidad academica inferida</strong>
              <span>Precision {academicIdentity.confidence}</span>
            </div>
            <InfoMetaGrid
              items={[
                { label: 'Ronda', value: academicIdentity.roundLabel },
                { label: 'Anio', value: academicIdentity.academicYear },
                { label: 'Materia', value: academicIdentity.subject },
                { label: 'Paralelo', value: academicIdentity.parallel },
                { label: 'Docente', value: academicIdentity.teacher },
                { label: 'Horario', value: academicIdentity.schedule },
                { label: 'Alias Teams', value: academicIdentity.mailAlias },
              ]}
            />
            {academicIdentity.warnings.length > 0 ? (
              <div className="teams-warning-list">
                {academicIdentity.warnings.map((warning) => (
                  <span key={warning}>{warning}</span>
                ))}
              </div>
            ) : null}
          </article>

          <article className="teams-activity-card teams-course-insight">
            <div className="teams-activity-card__head">
              <strong>Contraste contra Microsoft Teams</strong>
              <span>{courseAlignmentLabel}</span>
            </div>
            <InfoMetaGrid
              items={[
                { label: 'Nombre del Team', value: academicIdentity.teamName },
                { label: 'Correo del grupo', value: academicIdentity.mail },
                { label: 'Descripcion Teams', value: modalSelectedTeam?.description as string | undefined },
                { label: 'Canales relacionados', value: relatedCourseChannels.length },
                { label: 'Canales no relacionados', value: Math.max(0, courses.length - relatedCourseChannels.length) },
              ]}
            />
          </article>

          <div className="teams-data-list teams-activity-list">
            {courseChannelAnalyses.length > 0 ? (
              courseChannelAnalyses.map((analysis) => {
                const item = analysis.course
                return (
                  <article key={item.id || item.displayName} className="teams-activity-card">
                    <div className="teams-activity-card__head">
                      <strong>{item.displayName || 'Canal sin nombre'}</strong>
                      <span>{analysis.relationLabel}</span>
                    </div>
                    <InfoMetaGrid
                      items={[
                        { label: 'Tipo Graph', value: item.membershipType || 'standard' },
                        { label: 'Descripcion', value: item.description || 'Sin descripcion' },
                        { label: 'Coincide materia', value: analysis.subjectMatch ? 'Si' : 'No' },
                        { label: 'Coincide paralelo', value: analysis.parallelMatch ? 'Si' : 'No' },
                        { label: 'Canal base', value: analysis.isDefaultChannel ? 'Si' : 'No' },
                      ]}
                    />
                    {item.webUrl ? (
                      <a href={item.webUrl} target="_blank" rel="noreferrer" className="teams-link-btn">
                        Abrir canal
                      </a>
                    ) : null}
                  </article>
                )
              })
            ) : (
              <p className="empty-block">No hay canales de Teams disponibles para contrastar.</p>
            )}
          </div>
        </div>
      )
    }

    if (activeInfoTab === 'recordings') {
      return (
        <div className="teams-activity-section">
          <InfoSummary items={recordingSummaryItems} />
          {recordingDiscovery?.warnings?.length ? (
            <div className="teams-recording-discovery" role="status">
              <strong>Ubicaciones no disponibles</strong>
              <span>
                Se conservaron los resultados obtenidos en las demás bibliotecas de SharePoint y OneDrive.
              </span>
              {recordingDiscovery.warnings.map((warning) => <span key={warning}>{warning}</span>)}
            </div>
          ) : null}
          <div className="teams-data-list teams-activity-list">
          {recordings.length > 0 ? (
            recordings.map((item) => (
              <article key={`${item.driveId || 'drive'}-${item.id || `${item.name}-${item.uploadedAt || item.startTime}`}`} className="teams-activity-card teams-recording-card">
                <div className="teams-activity-card__head">
                  <strong>{item.name || 'Grabacion sin nombre'}</strong>
                  <div className="teams-recording-card__badges">
                    <span className="teams-recording-source">
                      {item.storageSource === 'OWNER_ONEDRIVE' ? 'OneDrive' : 'SharePoint'}
                    </span>
                    <span className={item.metadataStatus === 'COMPLETA' ? 'teams-recording-status teams-recording-status--complete' : 'teams-recording-status teams-recording-status--warning'}>
                      {item.metadataStatus === 'COMPLETA' ? 'Metadatos completos' : 'Requiere revisión'}
                    </span>
                  </div>
                </div>
                <InfoMetaGrid
                  items={[
                    { label: 'Almacenamiento', value: item.sourceLabel || (item.storageSource === 'OWNER_ONEDRIVE' ? 'OneDrive del responsable' : 'SharePoint del equipo') },
                    { label: 'Biblioteca', value: item.driveName || item.driveType || 'Documentos' },
                    { label: 'Canal', value: item.channelName || 'No asociado a canal' },
                    { label: 'Propietario', value: item.ownerName || 'Equipo de Teams' },
                    { label: 'Ruta en Microsoft 365', value: item.parentPath || 'No informada por Graph' },
                    { label: 'Creado por', value: item.createdByName || 'No informado por Graph' },
                    { label: 'Modificado por', value: item.lastModifiedByName || 'No informado por Graph' },
                    { label: 'ID del sitio', value: item.siteId || 'N/D' },
                    { label: 'ID de lista / elemento', value: item.listId && item.listItemId ? `${item.listId} / ${item.listItemId}` : 'N/D' },
                    { label: 'Fecha de creación del archivo EC', value: item.fileCreatedDateLabel || item.uploadedDateLabel || formatDateOnlyInEcuador(item.fileCreatedAt || item.uploadedAt) },
                    { label: 'Hora de creación del archivo EC', value: item.fileCreatedHourLabel || item.uploadedHourLabel || formatTimeOnlyInEcuador(item.fileCreatedAt || item.uploadedAt) },
                    { label: 'Fecha de inicio de grabación EC', value: item.startDateLabel || formatDateOnlyInEcuador(item.startTime) || 'No disponible' },
                    { label: 'Hora de inicio de grabación EC', value: item.startHourLabel || formatTimeOnlyInEcuador(item.startTime) || 'No disponible' },
                    { label: 'Fecha de fin de grabación EC', value: item.endDateLabel || formatDateOnlyInEcuador(item.endTime) || 'No disponible' },
                    { label: 'Hora de fin de grabación EC', value: item.endHourLabel || formatTimeOnlyInEcuador(item.endTime) || 'No disponible' },
                    { label: 'Duración calculada', value: item.calculatedDurationLabel || 'No calculable' },
                    { label: 'Intervalo HH:MM:SS', value: item.calculatedDurationClock || 'N/D' },
                    { label: 'Duración multimedia', value: item.durationLabel || (item.durationSeconds != null ? formatDurationFromSeconds(item.durationSeconds) : 'No informada por Graph') },
                    { label: 'Multimedia HH:MM:SS', value: item.durationClock || 'N/D' },
                    { label: 'Estado de duración', value: item.durationStatus === 'VERIFIED_GRAPH_MEDIA' ? 'Verificada por Microsoft Graph' : 'No disponible' },
                    { label: 'Última modificación', value: item.modifiedDateTimeLabel || formatDateTimeInEcuador(item.modifiedAt || item.lastModifiedDateTime) },
                    { label: 'Tamaño', value: item.sizeLabel || (item.sizeBytes || item.size ? `${item.sizeBytes || item.size} bytes` : 'N/D') },
                    { label: 'Tipo de archivo', value: item.fileExtension || 'N/D' },
                    { label: 'Tipo MIME', value: item.mimeType || 'N/D' },
                    { label: 'Origen duración', value: item.durationSource === 'GRAPH_MEDIA_METADATA' ? 'Metadatos multimedia de Microsoft Graph' : item.durationSource === 'GRAPH_CALL_RECORDING' ? 'Intervalo de grabación de Microsoft Graph' : item.durationSource === 'GRAPH_CALL_RECORD' ? 'Intervalo del registro de llamada de Microsoft Graph' : 'No disponible' },
                    { label: 'Origen del horario', value: item.recordingTimeSource === 'GRAPH_CALL_RECORDING' ? 'Grabación de reunión en Microsoft Graph' : item.recordingTimeSource === 'GRAPH_CALL_RECORD' ? 'Registro de llamada en Microsoft Graph' : 'No disponible' },
                    { label: 'Validación del horario', value: item.recordingTimeStatus === 'VERIFIED_GRAPH_INTERVAL' ? 'Verificado' : 'Pendiente de metadatos Graph' },
                    { label: 'Fechas del archivo', value: 'Carga y modificación; no representan el horario de la reunión' },
                    { label: 'Zona horaria', value: item.timeZone || ECUADOR_TIME_ZONE },
                  ]}
                />
                {item.warnings?.length ? (
                  <div className="teams-recording-warnings" role="status">
                    {item.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                  </div>
                ) : null}
                {item.webUrl ? (
                  <div className="teams-actions">
                    <a href={item.webUrl} target="_blank" rel="noreferrer" className="teams-link-btn">
                      Abrir grabacion
                    </a>
                    {item.driveWebUrl && item.driveWebUrl !== item.webUrl ? (
                      <a href={item.driveWebUrl} target="_blank" rel="noreferrer" className="teams-link-btn teams-link-btn--secondary">
                        Abrir ubicacion
                      </a>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <p className="empty-block">No hay grabaciones encontradas.</p>
          )}
          </div>
        </div>
      )
    }

    if (activeInfoTab === 'status') {
      return (
        <div className="teams-data-list">
          <article>
            <strong>Estado del equipo</strong>
            <span>{callStatus?.is_in_call ? 'En llamada activa' : 'Sin llamada activa'}</span>
            <span>Participantes del equipo: {callStatus?.participant_count ?? participants.length}</span>
            <span>Detectados en llamada/evento: {callStatus?.attendee_count ?? 0}</span>
            <span>Pendientes por invitar: {callStatus?.missing_count ?? 0}</span>
            <span>Horario mostrado: {callStatus?.timeZone || ECUADOR_TIME_ZONE}</span>
            {callStatus?.note ? <span>{callStatus.note}</span> : null}
          </article>

          {callStatus?.active_meeting ? (
            <article>
              <strong>{callStatus.active_meeting.topic || 'Llamada activa'}</strong>
              <span>
                Inicio (EC): {callStatus.active_meeting.startLabel || formatDateTimeInEcuador(callStatus.active_meeting.start) || 'N/D'}
              </span>
              <span>
                Fin (EC): {callStatus.active_meeting.endLabel || formatDateTimeInEcuador(callStatus.active_meeting.end) || 'N/D'}
              </span>
              <span>Canal: {callStatus.active_meeting.channelName || callStatus.active_meeting.channelId || 'N/D'}</span>
              <span>Origen: {callStatus.active_meeting.source || 'N/D'}</span>
              {callStatus.active_meeting.joinWebUrl ? (
                <a
                  href={callStatus.active_meeting.joinWebUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="teams-link-btn"
                >
                  Unirse
                </a>
              ) : null}
            </article>
          ) : null}

          {callStatus?.in_call_participants && callStatus.in_call_participants.length > 0 ? (
            <article>
              <strong>Reunidos en la llamada</strong>
              {callStatus.in_call_participants.map((person, index) => (
                <span key={`${person.address || person.name || 'participant'}-${index}`}>
                  {person.name || person.address || 'Sin nombre'}
                  {person.response ? ` | estado: ${person.response}` : ''}
                </span>
              ))}
            </article>
          ) : null}

          <div className="teams-actions">
            <button type="button" onClick={() => void handleInviteMissing()} disabled={inviteLoading || !modalSelectedTeam?.id}>
              {inviteLoading ? 'Invitando...' : 'Invitacion masiva a faltantes'}
            </button>
          </div>

          {joinRequestUrl ? (
            <article>
              <strong>Solicitud de unirse generada</strong>
              <span>Faltantes detectados: {joinRequestCount}</span>
              <a href={joinRequestUrl} target="_blank" rel="noreferrer" className="teams-link-btn">
                Unirse a la llamada
              </a>
            </article>
          ) : null}
        </div>
      )
    }

    if (activeInfoTab === 'messages') {
      return (
        <div className="teams-activity-section teams-publication-feed">
          <InfoSummary items={messageGlobalSummaryItems} />
          <div className="teams-data-list teams-activity-list teams-message-list">
          {messageThreads.length > 0 ? (
            messageThreads.map((thread) => renderMessageThreadPreview(thread))
          ) : (
            <p className="empty-block">No hay mensajes disponibles.</p>
          )}
          </div>
        </div>
      )
    }

    return (
      <div className="teams-data-list">
        {attendanceNote ? <p className="teams-message">{attendanceNote}</p> : null}
        {attendance.length > 0 ? (
          attendance.map((item) => (
            <article key={item.id || item.topic}>
              <strong>{item.topic || 'Evento sin titulo'}</strong>
              <span>
                {item.startLabel || formatDateTimeInEcuador(item.start) || 'Sin inicio'} | invitados: {item.totalAttendees ?? 0}
              </span>
            </article>
          ))
        ) : (
          <p className="empty-block">No hay asistencias/eventos disponibles.</p>
        )}
      </div>
    )
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Microsoft Teams</p>
          <h2>Movimientos Teams</h2>
          <p className="report-description">
            Consulta global de aulas, detalles y actividad de Microsoft Teams con una distribucion simetrica.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Teams</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content teams-page-grid">
        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Catalogo de aulas de Teams</h3>
            <span>Consulta global desde Microsoft Graph</span>
          </div>

          <p className="empty-block">
            Carga todas las aulas disponibles en el tenant, sin depender del usuario actual.
          </p>

          <div className="teams-actions">
            <button type="button" onClick={onLoadCatalog} disabled={catalogLoading}>
              {catalogLoading ? 'Consultando...' : 'Cargar aulas de Teams'}
            </button>
          </div>

          {catalogMessage ? <p className="teams-message">{catalogMessage}</p> : null}
          {catalogError ? <p className="teams-error">{catalogError}</p> : null}
        </article>

        <article className="student-card teams-summary-card">
          <div className="card-head">
            <h3>Resumen</h3>
            <span>{catalogTeams.length} aulas</span>
          </div>

          <div className="teams-summary">
            <div>
              <strong>Total de aulas</strong>
              <p>{catalogTeams.length}</p>
            </div>
            <div>
              <strong>Equipo seleccionado</strong>
              <p>{selectedTeam?.displayName || selectedTeam?.id || 'Ninguno'}</p>
            </div>
            <div>
              <strong>Estado</strong>
              <p>{catalogLoading ? 'Cargando...' : 'Listo'}</p>
            </div>
          </div>
        </article>

        <article className="student-card student-card--wide">
          <div className="card-head">
            <h3>Lista de Teams</h3>
            <span>Haz clic para ver detalles</span>
          </div>

          <div className="teams-actions">
            <button
              type="button"
              onClick={openTeamsModal}
              disabled={catalogTeams.length === 0}
            >
              Ver equipos
            </button>
          </div>

          <p className="empty-block">
            Usa el boton Ver equipos para abrir la subpantalla, navegar por nombre y revisar
            detalles del Team.
          </p>
        </article>

        {isTeamsModalOpen ? (
          <div className="teams-modal-overlay">
            <article className={isTeamDetailScreenOpen ? 'teams-modal teams-modal--team-detail' : 'teams-modal'}>
              <div className="card-head">
                <h3>{isTeamDetailScreenOpen ? 'Informacion del Team' : 'Seleccionar equipo'}</h3>
                <span>
                  {isTeamDetailScreenOpen
                    ? modalSelectedTeam?.displayName || 'Sin equipo seleccionado'
                    : `${filteredTeams.length} resultados`}
                </span>
              </div>

              {!isTeamDetailScreenOpen ? (
                <>
                  <div className="teams-controls teams-controls--single">
                    <label>
                      <span>Filtrar por nombre del equipo</span>
                      <input
                        value={teamNameFilter}
                        onChange={(event) => setTeamNameFilter(event.target.value)}
                        placeholder="Escribe parte del nombre..."
                      />
                    </label>
                  </div>

                  <div className="teams-actions">
                    <button type="button" onClick={closeTeamsModal}>
                      Cerrar
                    </button>
                  </div>

                  <div className="teams-list-grid teams-list-grid--modal teams-list-grid--wide">
                    {filteredTeams.length > 0 ? (
                      filteredTeams.map(({ team, index }) => (
                        <button
                          key={team.id || `${team.displayName || 'team'}-${index}`}
                          type="button"
                          className={`team-item ${modalTeamIndex === index ? 'team-item--active' : ''}`}
                          onClick={() => handlePickTeam(index)}
                        >
                          <strong>{team.displayName || 'Sin nombre'}</strong>
                          <span>{team.mail || team.description || 'Sin descripcion'}</span>
                          <small>{team.id}</small>
                        </button>
                      ))
                    ) : (
                      <p className="empty-block">No hay equipos que coincidan con ese nombre.</p>
                    )}
                  </div>
                </>
              ) : (
                <section className="teams-modal-info teams-modal-info--detail">
                  <div className="card-head">
                    <h3>{modalSelectedTeam?.displayName || 'Sin equipo seleccionado'}</h3>
                    <span>{modalSelectedTeam?.id || ''}</span>
                  </div>

                  <div className="teams-actions">
                    <button type="button" onClick={() => setIsTeamDetailScreenOpen(false)}>
                      Volver a equipos
                    </button>
                    <button type="button" onClick={refreshSelectedTeamInfo} disabled={teamInfoLoading || !modalSelectedTeam?.id}>
                      {teamInfoLoading ? 'Actualizando...' : 'Actualizar informacion'}
                    </button>
                    <button type="button" onClick={closeTeamsModal}>
                      Cerrar
                    </button>
                  </div>

                  <div className="teams-team-profile">
                    <div>
                      <strong>{modalSelectedTeam?.displayName || 'Sin nombre'}</strong>
                      <span>{modalSelectedTeam?.mail || 'Sin correo del grupo'}</span>
                      <span>{modalSelectedTeam?.description || 'Sin descripcion registrada'}</span>
                      <small>ID: {modalSelectedTeam?.id || 'N/D'}</small>
                    </div>
                    {modalSelectedTeam?.webUrl ? (
                      <a href={modalSelectedTeam.webUrl} target="_blank" rel="noreferrer" className="teams-link-btn">
                        Abrir en Teams
                      </a>
                    ) : null}
                  </div>

                  <div className="teams-detail-stats">
                    <span>
                      <strong>{participants.length || callStatus?.participant_count || 0}</strong>
                      <small>Participantes</small>
                    </span>
                    <span>
                      <strong>{ownerParticipants.length}</strong>
                      <small>Propietarios</small>
                    </span>
                    <span>
                      <strong>{courses.length}</strong>
                      <small>Cursos</small>
                    </span>
                    <span>
                      <strong>{recordings.length}</strong>
                      <small>Grabaciones</small>
                    </span>
                    <span>
                      <strong>{attendance.length}</strong>
                      <small>Asistencias</small>
                    </span>
                    <span>
                      <strong>{messageThreads.length}</strong>
                      <small>Mensajes global</small>
                    </span>
                    <span>
                      <strong>{callStatus?.missing_count ?? 0}</strong>
                      <small>Faltantes</small>
                    </span>
                  </div>

                  <div className="teams-info-tabs">
                    <button
                      type="button"
                      className={activeInfoTab === 'status' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('status')}
                    >
                      Estado/Llamada
                    </button>
                    <button
                      type="button"
                      className={activeInfoTab === 'participants' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('participants')}
                    >
                      Participantes
                    </button>
                    <button
                      type="button"
                      className={activeInfoTab === 'courses' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('courses')}
                    >
                      Curso/Canales
                    </button>
                    <button
                      type="button"
                      className={activeInfoTab === 'recordings' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('recordings')}
                    >
                      Grabaciones
                    </button>
                    <button
                      type="button"
                      className={activeInfoTab === 'attendance' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('attendance')}
                    >
                      Asistencias
                    </button>
                    <button
                      type="button"
                      className={activeInfoTab === 'messages' ? 'teams-info-tabs__btn teams-info-tabs__btn--active' : 'teams-info-tabs__btn'}
                      onClick={() => handleInfoTabClick('messages')}
                    >
                      Mensajes
                    </button>
                  </div>

                  {teamInfoMessage ? <p className="teams-message">{teamInfoMessage}</p> : null}
                  {lastRefreshAt ? <p className="teams-message">Actualizado: {lastRefreshAt}</p> : null}
                  {teamInfoError ? <p className="teams-error">{teamInfoError}</p> : null}
                  {renderInfoContent()}
                </section>
              )}
            </article>
          </div>
        ) : null}
      </section>
    </>
  )
}
