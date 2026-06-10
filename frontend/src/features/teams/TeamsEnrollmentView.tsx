import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  executeIndividualTeamEnrollment,
  fetchTeamEnrollmentFilterOptions,
  fetchTeamEnrollmentGroupStudents,
  previewIndividualTeamEnrollment,
  searchIndividualTeamEnrollmentStudents,
  searchTeamEnrollmentGroups,
} from '../../lib/api'
import type {
  GraphTeam,
  TeamCreateAndEnrollPayload,
  TeamEnrollmentGroup,
  TeamEnrollmentGroupIdentity,
  TeamEnrollmentMateriaOption,
  TeamEnrollmentParallelOption,
  TeamEnrollmentPeriodOption,
  TeamEnrollmentStudent,
  TeamIndividualEnrollmentStudent,
  TeamMassEnrollmentResponse,
} from '../../types/app'

type TeamsEnrollmentViewProps = {
  displayName: string
  catalogLoading: boolean
  catalogMessage: string
  catalogError: string
  createLoading: boolean
  createMessage: string
  createError: string
  catalogTeams: GraphTeam[]
  selectedTeam: GraphTeam | null
  createDisplayName: string
  createCourses: string
  createTeachers: string
  createVisibility: string
  teamsTeamId: string
  onLoadCatalog: () => void
  onSelectTeam: (index: number) => void
  onTeamIdFromCatalog: (teamId: string) => void
  onCreateDisplayNameChange: (value: string) => void
  onCreateCoursesChange: (value: string) => void
  onCreateTeachersChange: (value: string) => void
  onCreateVisibilityChange: (value: string) => void
  onCreateAndEnroll: (options?: Partial<TeamCreateAndEnrollPayload>) => void
}

type CourseAcademicScope = {
  materiaQuery: string
  paralelo: string
}

function periodOptionLabel(option: TeamEnrollmentPeriodOption): string {
  return String(option.detalle_periodo || option.periodo_nombre || option.codigo_periodo || '').trim()
}

function materiaOptionLabel(option: TeamEnrollmentMateriaOption): string {
  return String(option.nombre_materia || option.materia_base_key || '').trim()
}

function parallelOptionLabel(option: TeamEnrollmentParallelOption): string {
  const name = String(option.paralelo_nombre || '').trim()
  const code = String(option.paralelo || '').trim()
  if (name && name !== code) return `${name} (${code})`
  return name || code
}

function groupParallelLabel(group: Pick<TeamEnrollmentGroup, 'paralelo' | 'paralelo_nombre'>): string {
  return String(group.paralelo_nombre || group.paralelo || '').trim()
}

function groupCareerLabel(group: Pick<TeamEnrollmentGroup, 'nombre_carrera' | 'nombre_materia' | 'cod_anio_basica'>): string {
  return String(group.nombre_carrera || group.nombre_materia || group.cod_anio_basica || '').trim()
}

function groupSelectionKey(group: Pick<TeamEnrollmentGroup, 'codigo_periodo' | 'cod_anio_basica' | 'paralelo' | 'materia_base_key'>): string {
  return [
    group.codigo_periodo || '',
    group.cod_anio_basica || '',
    group.paralelo || '',
    group.materia_base_key || '',
  ].join('|')
}

function parseCourseAcademicScope(team: GraphTeam | null): CourseAcademicScope {
  const displayName = String(team?.displayName || '').trim()
  const mailName = String(team?.mail || '').split('@')[0] || ''
  const source = displayName || mailName
  const withoutTeacher = source.replace(/\s*-\s*Docente:.*$/i, '').replace(/\s+Docente:.*$/i, '').trim()
  const withoutPrefix = withoutTeacher.replace(/^\s*R\d+\s*[-–]\s*/i, '').trim()
  const matches = [...withoutPrefix.matchAll(/\b(ABS|PBS\d+|PB\d+|G\d+)\b/gi)]
  const lastMatch = matches[matches.length - 1]
  const paralelo = lastMatch?.[1]?.toUpperCase() || ''
  const materiaSource =
    lastMatch && lastMatch.index !== undefined ? withoutPrefix.slice(0, lastMatch.index) : withoutPrefix
  const materiaQuery = materiaSource.replace(/[-–\s]+$/g, '').trim()

  if (materiaQuery || paralelo) {
    return { materiaQuery, paralelo }
  }

  const mailParallel = mailName.match(/(?:^|-)(ABS|PBS\d+|PB\d+|G\d+)(?:-|$)/i)
  return {
    materiaQuery: '',
    paralelo: mailParallel?.[1]?.toUpperCase() || '',
  }
}

export function TeamsEnrollmentView({
  displayName,
  catalogLoading,
  catalogMessage,
  catalogError,
  createLoading,
  createMessage,
  createError,
  catalogTeams,
  selectedTeam,
  createDisplayName,
  createCourses,
  createTeachers,
  createVisibility,
  teamsTeamId,
  onLoadCatalog,
  onSelectTeam,
  onTeamIdFromCatalog,
  onCreateDisplayNameChange,
  onCreateCoursesChange,
  onCreateTeachersChange,
  onCreateVisibilityChange,
  onCreateAndEnroll,
}: Readonly<TeamsEnrollmentViewProps>) {
  const [selectedPeriods, setSelectedPeriods] = useState<string[]>([])
  const [availablePeriods, setAvailablePeriods] = useState<TeamEnrollmentPeriodOption[]>([])
  const [availableParallels, setAvailableParallels] = useState<TeamEnrollmentParallelOption[]>([])
  const [availableMaterias, setAvailableMaterias] = useState<TeamEnrollmentMateriaOption[]>([])
  const [maxPeriods, setMaxPeriods] = useState(2)
  const [filterOptionsLoading, setFilterOptionsLoading] = useState(false)
  const [filterOptionsError, setFilterOptionsError] = useState('')
  const [searchCarrera] = useState('')
  const [selectedParallels, setSelectedParallels] = useState<string[]>([])
  const [selectedMateriaKeys, setSelectedMateriaKeys] = useState<string[]>([])
  const [materiaOptionQuery, setMateriaOptionQuery] = useState('')
  const [searchAnio, setSearchAnio] = useState('')
  const [searchLimit, setSearchLimit] = useState('100')
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [groupsError, setGroupsError] = useState('')
  const [groupsMessage, setGroupsMessage] = useState('')
  const [groups, setGroups] = useState<TeamEnrollmentGroup[]>([])
  const [selectedGroup, setSelectedGroup] = useState<TeamEnrollmentGroup | null>(null)
  const [selectedGroups, setSelectedGroups] = useState<TeamEnrollmentGroup[]>([])
  const [checkedGroupKeys, setCheckedGroupKeys] = useState<string[]>([])
  const [studentsLoading, setStudentsLoading] = useState(false)
  const [studentsError, setStudentsError] = useState('')
  const [students, setStudents] = useState<TeamEnrollmentStudent[]>([])
  const [selectedStudentCodes, setSelectedStudentCodes] = useState<string[]>([])
  const [isIndividualModalOpen, setIsIndividualModalOpen] = useState(false)
  const [individualTeamFilter, setIndividualTeamFilter] = useState('')
  const [individualTeamId, setIndividualTeamId] = useState('')
  const [individualPeriod, setIndividualPeriod] = useState('')
  const [individualStudentQuery, setIndividualStudentQuery] = useState('')
  const [individualStudents, setIndividualStudents] = useState<TeamIndividualEnrollmentStudent[]>([])
  const [selectedIndividualStudentCodes, setSelectedIndividualStudentCodes] = useState<string[]>([])
  const [individualSearchLoading, setIndividualSearchLoading] = useState(false)
  const [individualActionLoading, setIndividualActionLoading] = useState(false)
  const [individualMessage, setIndividualMessage] = useState('')
  const [individualError, setIndividualError] = useState('')
  const [individualResult, setIndividualResult] = useState<TeamMassEnrollmentResponse | null>(null)
  const [catalogRequested, setCatalogRequested] = useState(false)
  const [individualAutoSearchKey, setIndividualAutoSearchKey] = useState('')

  const toErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof ApiError) return error.message
    if (error instanceof Error) return error.message
    return 'No se pudo completar la operacion de matriculacion en Teams.'
  }, [])

  const selectedTeamValue = useMemo(() => {
    const manualTeamId = teamsTeamId.trim()
    if (manualTeamId) return manualTeamId
    if (selectedTeam?.id) return String(selectedTeam.id)
    return ''
  }, [selectedTeam, teamsTeamId])

  const selectedStudentSet = useMemo(() => new Set(selectedStudentCodes), [selectedStudentCodes])
  const selectedIndividualStudentSet = useMemo(
    () => new Set(selectedIndividualStudentCodes),
    [selectedIndividualStudentCodes]
  )
  const selectedMateriaSet = useMemo(() => new Set(selectedMateriaKeys), [selectedMateriaKeys])
  const periodOptionsByCode = useMemo(
    () => new Map(availablePeriods.map((item) => [item.codigo_periodo, item])),
    [availablePeriods]
  )
  const materiaOptionsByKey = useMemo(
    () => new Map(availableMaterias.map((item) => [item.materia_base_key, item])),
    [availableMaterias]
  )

  const selectedPeriodSummary = useMemo(
    () =>
      selectedPeriods.map((codigoPeriodo) => {
        const option = periodOptionsByCode.get(codigoPeriodo)
        if (!option) return codigoPeriodo
        return `${periodOptionLabel(option)} (${option.codigo_periodo})`
      }),
    [periodOptionsByCode, selectedPeriods]
  )

  const selectedMateriaSummary = useMemo(
    () =>
      selectedMateriaKeys.map((materiaBaseKey) => {
        const option = materiaOptionsByKey.get(materiaBaseKey)
        if (!option) return materiaBaseKey
        return `${materiaOptionLabel(option)} (${materiaBaseKey})`
      }),
    [materiaOptionsByKey, selectedMateriaKeys]
  )

  const selectedParallelSet = useMemo(() => new Set(selectedParallels), [selectedParallels])
  const selectedParallelSummary = useMemo(
    () =>
      selectedParallels.map((parallelCode) => {
        const option = availableParallels.find((item) => item.paralelo === parallelCode)
        if (!option) return parallelCode
        return parallelOptionLabel(option)
      }),
    [availableParallels, selectedParallels]
  )

  const selectedGroupScopeLabel = useMemo(() => {
    if (selectedGroups.length > 1) return `${selectedGroups.length} grupos combinados`
    return selectedGroup?.suggested_team_name || 'Sin grupo seleccionado'
  }, [selectedGroup, selectedGroups])
  const selectedGroupKeySet = useMemo(
    () => new Set(selectedGroups.map((group) => groupSelectionKey(group))),
    [selectedGroups],
  )
  const checkedGroupKeySet = useMemo(() => new Set(checkedGroupKeys), [checkedGroupKeys])
  const checkedGroups = useMemo(
    () => groups.filter((group) => checkedGroupKeySet.has(groupSelectionKey(group))),
    [checkedGroupKeySet, groups],
  )

  const filteredMateriaOptions = useMemo(() => {
    const query = materiaOptionQuery.trim().toLowerCase()
    if (!query) {
      return availableMaterias
    }

    return availableMaterias.filter((item) =>
      [item.nombre_materia, item.codigo_materia_referencia, item.materia_base_key]
        .join(' ')
        .toLowerCase()
        .includes(query)
    )
  }, [availableMaterias, materiaOptionQuery])

  const filteredIndividualTeams = useMemo(() => {
    const query = individualTeamFilter.trim().toLowerCase()
    const teams = catalogTeams.map((team, index) => ({ team, index }))
    if (!query) return teams

    return teams.filter(({ team }) =>
      [team.displayName, team.mail, team.id, team.description]
        .join(' ')
        .toLowerCase()
        .includes(query)
    )
  }, [catalogTeams, individualTeamFilter])

  const individualSelectedTeamLabel = useMemo(() => {
    const team = catalogTeams.find((item) => String(item.id || '').trim() === individualTeamId)
    return team?.displayName || individualTeamId || 'Sin equipo seleccionado'
  }, [catalogTeams, individualTeamId])

  const individualSelectedTeam = useMemo(
    () => catalogTeams.find((item) => String(item.id || '').trim() === individualTeamId) || null,
    [catalogTeams, individualTeamId]
  )
  const individualCourseScope = useMemo(
    () => parseCourseAcademicScope(individualSelectedTeam),
    [individualSelectedTeam]
  )

  const individualCanEnroll = Boolean(
    selectedIndividualStudentCodes.length > 0 &&
      individualResult &&
      (individualResult.ready_count ?? 0) > 0 &&
      individualResult.items?.some((item) => item.status === 'ready')
  )

  useEffect(() => {
    if (createVisibility !== 'educationClass') {
      onCreateVisibilityChange('educationClass')
    }
  }, [createVisibility, onCreateVisibilityChange])

  useEffect(() => {
    if (catalogRequested || catalogLoading || catalogTeams.length > 0) {
      return
    }

    setCatalogRequested(true)
    onLoadCatalog()
  }, [catalogLoading, catalogRequested, catalogTeams.length, onLoadCatalog])

  useEffect(() => {
    let cancelled = false

    const loadFilterOptions = async () => {
      setFilterOptionsLoading(true)
      setFilterOptionsError('')

      try {
        const payload = await fetchTeamEnrollmentFilterOptions({
          codigo_periodos: selectedPeriods,
          cod_anio_basica: searchCarrera.trim() || null,
          paralelos: selectedParallels,
          anio_periodo: searchAnio.trim() ? Number(searchAnio) : null,
        })

        if (cancelled) return

        const nextPeriods = payload.periodos || []
        const nextParallels = payload.paralelos || []
        const nextMaterias = payload.materias || []

        setAvailablePeriods(nextPeriods)
        setAvailableParallels(nextParallels)
        setAvailableMaterias(nextMaterias)
        setMaxPeriods(payload.max_periods ?? 2)

        setSelectedPeriods((current) => {
          const filtered = current.filter((codigoPeriodo) =>
            nextPeriods.some((item) => item.codigo_periodo === codigoPeriodo)
          )
          return filtered.length === current.length ? current : filtered
        })
        setSelectedMateriaKeys((current) => {
          const filtered = current.filter((materiaBaseKey) =>
            nextMaterias.some((item) => item.materia_base_key === materiaBaseKey)
          )
          return filtered.length === current.length ? current : filtered
        })
        setSelectedParallels((current) => {
          const filtered = current.filter((paralelo) => nextParallels.some((item) => item.paralelo === paralelo))
          return filtered.length === current.length ? current : filtered
        })
      } catch (error) {
        if (cancelled) return

        setFilterOptionsError(toErrorMessage(error))
        setAvailableParallels([])
        setAvailableMaterias([])
      } finally {
        if (!cancelled) {
          setFilterOptionsLoading(false)
        }
      }
    }

    void loadFilterOptions()

    return () => {
      cancelled = true
    }
  }, [searchAnio, searchCarrera, selectedParallels, selectedPeriods, toErrorMessage])

  const buildGroupIdentity = (group: TeamEnrollmentGroup): TeamEnrollmentGroupIdentity => ({
    codigo_periodo: String(group.codigo_periodo || ''),
    cod_anio_basica: String(group.cod_anio_basica || ''),
    paralelo: String(group.paralelo || ''),
    materia_base_key: String(group.materia_base_key || ''),
    anio_periodo: group.anio_periodo ?? null,
  })

  const openIndividualEnrollmentModal = () => {
    setIsIndividualModalOpen(true)
    setIndividualTeamFilter('')
    setIndividualTeamId(selectedTeamValue)
    setIndividualPeriod(selectedPeriods[0] || availablePeriods[0]?.codigo_periodo || '')
    setIndividualStudentQuery('')
    setIndividualStudents([])
    setSelectedIndividualStudentCodes([])
    setIndividualMessage('')
    setIndividualError('')
    setIndividualResult(null)
    setIndividualAutoSearchKey('')

    if (catalogTeams.length === 0) {
      onLoadCatalog()
    }
  }

  const handleIndividualTeamSelect = (team: GraphTeam, index: number) => {
    const teamId = String(team.id || '').trim()
    const courseScope = parseCourseAcademicScope(team)
    setIndividualTeamId(teamId)
    setIndividualStudents([])
    setSelectedIndividualStudentCodes([])
    setIndividualResult(null)
    setIndividualAutoSearchKey('')
    setIndividualMessage(
      teamId
        ? `Curso seleccionado: ${team.displayName || teamId}${
            courseScope.materiaQuery || courseScope.paralelo
              ? ` | Materia: ${courseScope.materiaQuery || 'N/D'} | Paralelo: ${courseScope.paralelo || 'N/D'}`
              : ''
          }`
        : ''
    )
    setIndividualError('')
    onSelectTeam(index)
    if (teamId) {
      onTeamIdFromCatalog(teamId)
    }
    if (teamId && individualPeriod) {
      void searchIndividualStudent({ codigoPeriodo: individualPeriod, query: '', courseScope, teamId })
    }
  }

  const searchIndividualStudent = useCallback(async (
    options?: { codigoPeriodo?: string; query?: string; courseScope?: CourseAcademicScope; teamId?: string }
  ) => {
    const activeTeamId = (options?.teamId ?? individualTeamId).trim()
    if (!activeTeamId) {
      setIndividualError('Selecciona un curso antes de buscar el estudiante.')
      setIndividualMessage('')
      setIndividualStudents([])
      return
    }

    const codigoPeriodo = (options?.codigoPeriodo ?? individualPeriod).trim()
    const query = (options?.query ?? individualStudentQuery).trim()
    const courseScope = options?.courseScope ?? individualCourseScope

    if (!codigoPeriodo) {
      setIndividualError('Selecciona un periodo para buscar el estudiante.')
      setIndividualMessage('')
      setIndividualStudents([])
      return
    }

    setIndividualSearchLoading(true)
    setIndividualError('')
    setIndividualMessage('')
    setIndividualResult(null)

    try {
      const payload = await searchIndividualTeamEnrollmentStudents({
        codigo_periodo: codigoPeriodo,
        query,
        materia_query: courseScope.materiaQuery || null,
        paralelo: courseScope.paralelo || null,
        limit: query ? 25 : 100,
      })
      setIndividualStudents(payload.items || [])
      setIndividualAutoSearchKey(
        `${activeTeamId}|${codigoPeriodo}|${query}|${courseScope.materiaQuery || ''}|${courseScope.paralelo || ''}`
      )
      setIndividualMessage(
        payload.message ||
          (query
            ? `Se encontraron ${payload.total ?? 0} estudiante(s).`
            : `Se cargaron ${payload.total ?? 0} estudiante(s) del periodo.`)
      )
    } catch (error) {
      setIndividualStudents([])
      setIndividualError(toErrorMessage(error))
    } finally {
      setIndividualSearchLoading(false)
    }
  }, [individualCourseScope, individualPeriod, individualStudentQuery, individualTeamId, toErrorMessage])

  useEffect(() => {
    if (!isIndividualModalOpen || !individualTeamId || individualPeriod || availablePeriods.length === 0) {
      return
    }

    setIndividualPeriod(availablePeriods[0].codigo_periodo)
    setIndividualAutoSearchKey('')
  }, [availablePeriods, individualPeriod, individualTeamId, isIndividualModalOpen])

  useEffect(() => {
    const query = individualStudentQuery.trim()
    const key = `${individualTeamId}|${individualPeriod}|${query}|${individualCourseScope.materiaQuery || ''}|${individualCourseScope.paralelo || ''}`

    if (
      !isIndividualModalOpen ||
      !individualTeamId ||
      !individualPeriod ||
      query ||
      individualSearchLoading ||
      individualAutoSearchKey === key
    ) {
      return
    }

    setIndividualAutoSearchKey(key)
    void searchIndividualStudent({ codigoPeriodo: individualPeriod, query: '' })
  }, [
    individualAutoSearchKey,
    individualCourseScope.materiaQuery,
    individualCourseScope.paralelo,
    individualPeriod,
    individualSearchLoading,
    individualStudentQuery,
    individualTeamId,
    isIndividualModalOpen,
    searchIndividualStudent,
  ])

  const buildIndividualEnrollmentPayload = () => {
    const selectedCodes = selectedIndividualStudentCodes.map((code) => code.trim()).filter(Boolean)
    if (selectedCodes.length === 0) return null

    const periodOption = availablePeriods.find((periodo) => periodo.codigo_periodo === individualPeriod.trim())
    const selectedStudent = selectedCodes
      .map((code) => individualStudents.find((student) => student.codigo_estud === code))
      .find(Boolean)

    return {
      team_id: individualTeamId.trim(),
      codigo_periodo: individualPeriod.trim(),
      codigo_estud: selectedCodes[0] || null,
      selected_student_codes: selectedCodes,
      materia_query: individualCourseScope.materiaQuery || null,
      paralelo: individualCourseScope.paralelo || null,
      anio_periodo: selectedStudent?.anio_periodo ?? periodOption?.anio_periodo ?? null,
    }
  }

  const runIndividualEnrollmentAction = async (mode: 'preview' | 'execute') => {
    if (!individualTeamId.trim()) {
      setIndividualError('Selecciona el equipo destino para validar la matricula.')
      setIndividualMessage('')
      return
    }

    const payload = buildIndividualEnrollmentPayload()
    if (!payload) {
      setIndividualError('Selecciona uno o mas estudiantes antes de validar.')
      setIndividualMessage('')
      return
    }

    setIndividualActionLoading(true)
    setIndividualError('')
    setIndividualMessage('')

    try {
      const result =
        mode === 'preview'
          ? await previewIndividualTeamEnrollment(payload)
          : await executeIndividualTeamEnrollment(payload)
      setIndividualResult(result)
      setIndividualMessage(
        result.message ||
          (mode === 'preview' ? 'Validacion individual completada.' : 'Matriculacion individual ejecutada.')
      )
    } catch (error) {
      setIndividualResult(null)
      setIndividualError(toErrorMessage(error))
    } finally {
      setIndividualActionLoading(false)
    }
  }

  const handleSelectedPeriodChange = (slotIndex: number, codigoPeriodo: string) => {
    setFilterOptionsError('')
    setSelectedPeriods((current) => {
      if (!codigoPeriodo) {
        return current.filter((_, index) => index !== slotIndex)
      }

      const duplicateIndex = current.findIndex((item, index) => item === codigoPeriodo && index !== slotIndex)
      if (duplicateIndex >= 0) {
        setFilterOptionsError('No puedes seleccionar el mismo periodo dos veces.')
        return current
      }

      const next = [...current]
      next[slotIndex] = codigoPeriodo
      return next.filter(Boolean).slice(0, maxPeriods)
    })
  }

  const toggleSelectedParallel = (parallelCode: string) => {
    setSelectedParallels((current) =>
      current.includes(parallelCode)
        ? current.filter((item) => item !== parallelCode)
        : [...current, parallelCode]
    )
  }

  const clearSelectedParallels = () => {
    setSelectedParallels([])
  }

  const toggleSelectedMateria = (materiaBaseKey: string) => {
    setSelectedMateriaKeys((current) =>
      current.includes(materiaBaseKey)
        ? current.filter((item) => item !== materiaBaseKey)
        : [...current, materiaBaseKey]
    )
  }

  const clearSelectedMaterias = () => {
    setSelectedMateriaKeys([])
  }

  const handleSearchGroups = async () => {
    if (selectedPeriods.length === 0) {
      setGroupsError('Debes seleccionar al menos un periodo para buscar estudiantes y materias.')
      setGroupsMessage('')
      setGroups([])
      setCheckedGroupKeys([])
      return
    }

    setGroupsLoading(true)
    setGroupsError('')
    setGroupsMessage('')
    setSelectedGroup(null)
    setSelectedGroups([])
    setCheckedGroupKeys([])
    setStudents([])
    setSelectedStudentCodes([])

    try {
      const payload = await searchTeamEnrollmentGroups({
        codigo_periodo: selectedPeriods[0] || null,
        codigo_periodos: selectedPeriods,
        cod_anio_basica: searchCarrera.trim() || null,
        paralelos: selectedParallels,
        materia_base_keys: selectedMateriaKeys,
        anio_periodo: searchAnio.trim() ? Number(searchAnio) : null,
        limit: searchLimit.trim() ? Number(searchLimit) : 100,
      })
      setGroups(payload.items || [])
      setGroupsMessage(`Se encontraron ${payload.total ?? 0} grupos para Teams.`)
    } catch (error) {
      setGroups([])
      setGroupsError(toErrorMessage(error))
    } finally {
      setGroupsLoading(false)
    }
  }

  const loadGroupStudents = async (groupsToLoad: TeamEnrollmentGroup[]) => {
    setStudentsLoading(true)
    setStudentsError('')

    try {
      const primaryGroup = groupsToLoad[0] || null
      if (!primaryGroup) {
        setStudents([])
        setSelectedStudentCodes([])
        setSelectedGroups([])
        setCheckedGroupKeys([])
        setSelectedGroup(null)
        return
      }

      const groupItems = groupsToLoad.map(buildGroupIdentity)
      const payload = await fetchTeamEnrollmentGroupStudents({
        ...groupItems[0],
        group_items: groupItems,
      })
      setSelectedGroups(groupsToLoad)
      setCheckedGroupKeys(groupsToLoad.map((group) => groupSelectionKey(group)))
      setSelectedGroup(payload.group || primaryGroup)
      setStudents(payload.items || [])
      setSelectedStudentCodes((payload.items || []).map((item) => item.codigo_estud))

      const suggestedName = payload.suggested_team_name || payload.group?.suggested_team_name || ''
      if (suggestedName) {
        onCreateDisplayNameChange(suggestedName)
      }
      if (payload.group?.nombre_materia) {
        onCreateCoursesChange(String(payload.group.nombre_materia))
      }
    } catch (error) {
      setStudents([])
      setSelectedStudentCodes([])
      setSelectedGroups([])
      setSelectedGroup(null)
      setStudentsError(toErrorMessage(error))
    } finally {
      setStudentsLoading(false)
    }
  }

  const toggleGroupCheck = (group: TeamEnrollmentGroup) => {
    const key = groupSelectionKey(group)
    setCheckedGroupKeys((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    )
  }

  const selectCheckedGroups = async () => {
    if (checkedGroups.length === 0) {
      setGroupsError('Marca uno o mas grupos antes de seleccionar.')
      return
    }

    setGroupsError('')
    await loadGroupStudents(checkedGroups)
  }

  const selectAllVisibleGroups = async () => {
    if (groups.length === 0) return

    setGroupsError('')
    setCheckedGroupKeys(groups.map((group) => groupSelectionKey(group)))
    await loadGroupStudents(groups)
  }

  const toggleStudent = (codigoEstud: string) => {
    setSelectedStudentCodes((current) =>
      current.includes(codigoEstud)
        ? current.filter((item) => item !== codigoEstud)
        : [...current, codigoEstud]
    )
  }

  const selectAllStudents = () => {
    setSelectedStudentCodes(students.map((item) => item.codigo_estud))
  }

  const clearSelectedStudents = () => {
    setSelectedStudentCodes([])
  }

  const setIndividualSelectionMessage = (count: number) => {
    setIndividualMessage(count > 0 ? `${count} estudiante(s) seleccionado(s).` : 'Sin estudiantes seleccionados.')
  }

  const toggleIndividualStudent = (codigoEstud: string) => {
    const normalizedCode = String(codigoEstud || '').trim()
    if (!normalizedCode) return

    setSelectedIndividualStudentCodes((current) => {
      const next = current.includes(normalizedCode)
        ? current.filter((item) => item !== normalizedCode)
        : [...current, normalizedCode]
      setIndividualSelectionMessage(next.length)
      return next
    })
    setIndividualResult(null)
    setIndividualError('')
  }

  const selectVisibleIndividualStudents = () => {
    const visibleCodes = individualStudents.map((student) => student.codigo_estud).filter(Boolean)
    if (visibleCodes.length === 0) return

    setSelectedIndividualStudentCodes((current) => {
      const next = Array.from(new Set([...current, ...visibleCodes]))
      setIndividualSelectionMessage(next.length)
      return next
    })
    setIndividualResult(null)
    setIndividualError('')
  }

  const clearSelectedIndividualStudents = () => {
    setSelectedIndividualStudentCodes([])
    setIndividualResult(null)
    setIndividualError('')
    setIndividualSelectionMessage(0)
  }

  const buildCreateAndEnrollOptions = (): Partial<TeamCreateAndEnrollPayload> | undefined => {
    if (!selectedGroup || selectedGroups.length === 0 || selectedStudentCodes.length === 0) {
      return undefined
    }

    const groupItems = selectedGroups.map(buildGroupIdentity)
    return {
      ...groupItems[0],
      group_items: groupItems,
      selected_student_codes: selectedStudentCodes,
    }
  }

  return (
    <>
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Microsoft Teams</p>
          <h2>Matricula Teams</h2>
          <p className="report-description">
            Busca grupos, revisa estudiantes y ejecuta matriculaciones en Teams con la misma simetria visual del modulo academico.
          </p>
        </div>

        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Matricula Teams</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-grid student-grid--content teams-page-grid">
        <article className="student-card student-card--wide teams-individual-entry-card">
          <div className="card-head">
            <h3>Matricula individual</h3>
            <span>{catalogTeams.length} aulas</span>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={openIndividualEnrollmentModal}>
              Matricula individual
            </button>
          </div>

          {catalogMessage ? <p className="teams-message">{catalogMessage}</p> : null}
          {catalogError ? <p className="teams-error">{catalogError}</p> : null}
        </article>
      </section>

      {isIndividualModalOpen ? (
        <div className="teams-modal-overlay">
          <article className="teams-modal teams-modal--individual">
            <div className="card-head">
              <h3>Matricula individual</h3>
              <span>{individualSelectedTeamLabel}</span>
            </div>

            <div className="teams-actions">
              <button type="button" onClick={() => setIsIndividualModalOpen(false)}>
                Cerrar
              </button>
              <button type="button" onClick={onLoadCatalog} disabled={catalogLoading}>
                {catalogLoading ? 'Consultando...' : 'Cargar cursos'}
              </button>
            </div>

            <div className="teams-modal-grid teams-modal-grid--individual">
              <section className="teams-course-picker">
                <div className="card-head card-head--inner">
                  <h3>Seleccionar curso</h3>
                  <span>{filteredIndividualTeams.length} cursos</span>
                </div>

                <div className="teams-selected-course">
                  <strong>{individualSelectedTeam?.displayName || 'Sin curso seleccionado'}</strong>
                  <span>{individualSelectedTeam?.mail || individualSelectedTeam?.id || 'Selecciona un curso para continuar'}</span>
                  {individualCourseScope.materiaQuery || individualCourseScope.paralelo ? (
                    <small>
                      Materia: {individualCourseScope.materiaQuery || 'N/D'} | Paralelo: {individualCourseScope.paralelo || 'N/D'}
                    </small>
                  ) : null}
                </div>

                <div className="teams-controls teams-controls--single">
                  <label>
                    <span>Buscar curso</span>
                    <input
                      value={individualTeamFilter}
                      onChange={(event) => setIndividualTeamFilter(event.target.value)}
                      placeholder="Nombre, correo o ID del curso"
                    />
                  </label>
                </div>

                <div className="teams-list-grid teams-list-grid--modal teams-list-grid--compact">
                  {filteredIndividualTeams.length > 0 ? (
                    filteredIndividualTeams.map(({ team, index }) => {
                      const teamId = String(team.id || '').trim()
                      return (
                        <button
                          key={team.id || `${team.displayName || 'team'}-${index}`}
                          type="button"
                          className={teamId === individualTeamId ? 'team-item team-item--active' : 'team-item'}
                          onClick={() => handleIndividualTeamSelect(team, index)}
                          disabled={!teamId}
                        >
                          <strong>{team.displayName || 'Sin nombre'}</strong>
                          <span>{team.mail || team.description || 'Sin detalle'}</span>
                          <small>{team.id}</small>
                        </button>
                      )
                    })
                  ) : (
                    <p className="empty-block">Carga el catalogo o ajusta el filtro para seleccionar el curso.</p>
                  )}
                </div>
              </section>

              <section className={individualTeamId ? 'teams-modal-info' : 'teams-modal-info teams-modal-info--disabled'}>
                <div className="card-head">
                  <h3>Buscar estudiante</h3>
                  <span>{individualTeamId ? `${individualStudents.length} resultado(s)` : 'Selecciona un curso'}</span>
                </div>

                {!individualTeamId ? (
                  <p className="empty-block">Selecciona un curso en la columna izquierda para activar la busqueda del estudiante.</p>
                ) : null}

                <div className="teams-search-layout">
                  <div className="teams-search-row teams-search-row--double">
                    <label className="teams-field-card teams-field-card--limit">
                      <span>Periodo</span>
                      <select
                        value={individualPeriod}
                        disabled={!individualTeamId}
                        onChange={(event) => {
                          const nextPeriod = event.target.value
                          setIndividualPeriod(nextPeriod)
                          setIndividualStudentQuery('')
                          setIndividualStudents([])
                          setSelectedIndividualStudentCodes([])
                          setIndividualResult(null)
                          setIndividualAutoSearchKey('')
                          setIndividualMessage('')
                          setIndividualError('')
                          if (nextPeriod) {
                            void searchIndividualStudent({ codigoPeriodo: nextPeriod, query: '' })
                          }
                        }}
                      >
                        <option value="">Selecciona un periodo</option>
                        {availablePeriods.map((periodo) => (
                          <option key={periodo.codigo_periodo} value={periodo.codigo_periodo}>
                            {periodOptionLabel(periodo)} | Codigo {periodo.codigo_periodo}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="teams-field-card teams-field-card--limit">
                      <span>Estudiante</span>
                      <input
                        value={individualStudentQuery}
                        disabled={!individualTeamId}
                        onChange={(event) => setIndividualStudentQuery(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault()
                            void searchIndividualStudent()
                          }
                        }}
                        placeholder="Filtra por codigo, nombre o correo"
                      />
                    </label>
                  </div>

                  <div className="teams-actions">
                    <button
                      type="button"
                      onClick={() => void searchIndividualStudent()}
                      disabled={
                        individualSearchLoading ||
                        !individualTeamId ||
                        !individualPeriod
                      }
                    >
                      {individualSearchLoading ? 'Buscando...' : 'Buscar estudiante'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void runIndividualEnrollmentAction('preview')}
                      disabled={
                        individualActionLoading ||
                        selectedIndividualStudentCodes.length === 0 ||
                        !individualTeamId.trim()
                      }
                    >
                      {individualActionLoading ? 'Validando...' : 'Validar existencia'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void runIndividualEnrollmentAction('execute')}
                      disabled={individualActionLoading || !individualCanEnroll}
                    >
                      {individualActionLoading ? 'Matriculando...' : 'Matricular seleccionados'}
                    </button>
                    <button
                      type="button"
                      onClick={selectVisibleIndividualStudents}
                      disabled={individualStudents.length === 0}
                    >
                      Seleccionar visibles
                    </button>
                    <button
                      type="button"
                      onClick={clearSelectedIndividualStudents}
                      disabled={selectedIndividualStudentCodes.length === 0}
                    >
                      Limpiar seleccion
                    </button>
                  </div>
                </div>

                {individualMessage ? <p className="teams-message">{individualMessage}</p> : null}
                {individualError ? <p className="teams-error">{individualError}</p> : null}
                {selectedIndividualStudentCodes.length > 0 ? (
                  <p className="teams-message">
                    {selectedIndividualStudentCodes.length} estudiante(s) seleccionado(s) para validar o matricular.
                  </p>
                ) : null}

                <div className="matricula-table-wrap">
                  <table className="matricula-table">
                    <thead>
                      <tr>
                        <th>Seleccionar</th>
                        <th>Codigo</th>
                        <th>Nombre</th>
                        <th>Correo INTEC</th>
                        <th>Materias</th>
                      </tr>
                    </thead>
                    <tbody>
                      {individualStudents.length > 0 ? (
                        individualStudents.map((student) => {
                          const selected = selectedIndividualStudentSet.has(student.codigo_estud)
                          return (
                            <tr key={`${student.codigo_periodo || individualPeriod}-${student.codigo_estud}`}>
                              <td>
                                <input
                                  type="checkbox"
                                  checked={selected}
                                  onChange={() => toggleIndividualStudent(student.codigo_estud)}
                                  aria-label={`Seleccionar ${student.nombre_estudiante || student.codigo_estud}`}
                                />
                              </td>
                              <td>{student.codigo_estud}</td>
                              <td>{student.nombre_estudiante || '-'}</td>
                              <td>{student.correo_intec || '-'}</td>
                              <td>{student.total_materias ?? 0}</td>
                            </tr>
                          )
                        })
                      ) : (
                        <tr>
                          <td colSpan={5}>
                            {individualPeriod
                              ? 'No hay estudiantes cargados para el periodo seleccionado.'
                              : 'Selecciona un periodo para cargar sus estudiantes.'}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {individualResult ? (
                  <>
                    <div className="teams-manual-stats">
                      <span>
                        <strong>{individualResult.ready_count ?? 0}</strong>
                        <small>Listo</small>
                      </span>
                      <span>
                        <strong>{individualResult.already_in_team_count ?? 0}</strong>
                        <small>Existente</small>
                      </span>
                      <span>
                        <strong>{individualResult.not_found_count ?? 0}</strong>
                        <small>No Graph</small>
                      </span>
                      <span>
                        <strong>{individualResult.invalid_email_count ?? 0}</strong>
                        <small>Correo</small>
                      </span>
                      <span>
                        <strong>{individualResult.enrolled_count ?? 0}</strong>
                        <small>Matriculado</small>
                      </span>
                    </div>

                    <div className="teams-data-list">
                      {(individualResult.items || []).map((item) => (
                        <article key={item.codigo_estud || item.correo_intec || item.graph_user_id || 'individual'}>
                          <strong>{item.nombre_estudiante || item.correo_intec || 'Estudiante'}</strong>
                          <span>{item.status_label || item.status || 'Sin estado'}</span>
                          <span>{item.graph_display_name || item.graph_user_principal_name || item.graph_mail || item.error || 'Sin detalle Graph'}</span>
                        </article>
                      ))}
                    </div>
                  </>
                ) : null}
              </section>
            </div>
          </article>
        </div>
      ) : null}

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Buscar grupos academicos</h3>
            <span>Periodo, carrera, paralelo y materia</span>
          </div>

          <p className="empty-block">
            El agrupamiento usa paralelo, Carrera, Periodo Academico y materia
            desde la malla academica por carrera para identificar materias equivalentes y sugerir el nombre del aula.
          </p>

          <div className="teams-search-layout">
            <div className="teams-search-row teams-search-row--single">
              <div className="teams-field teams-field-card">
                <span>Periodos desde base de datos (max. {maxPeriods})</span>
                {availablePeriods.length > 0 ? (
                  <div className="teams-period-combo-grid">
                    <label className="teams-period-select">
                      <span>Periodo 1</span>
                      <select
                        value={selectedPeriods[0] ?? ''}
                        onChange={(event) => handleSelectedPeriodChange(0, event.target.value)}
                      >
                        <option value="">Selecciona un periodo</option>
                        {availablePeriods.map((periodo) => (
                          <option key={periodo.codigo_periodo} value={periodo.codigo_periodo}>
                            {periodOptionLabel(periodo)} | Codigo {periodo.codigo_periodo}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="teams-period-select">
                      <span>Periodo 2</span>
                      <select
                        value={selectedPeriods[1] ?? ''}
                        disabled={!selectedPeriods[0]}
                        onChange={(event) => handleSelectedPeriodChange(1, event.target.value)}
                      >
                        <option value="">
                          {selectedPeriods[0] ? 'Selecciona un segundo periodo' : 'Selecciona el primer periodo'}
                        </option>
                        {availablePeriods
                          .filter(
                            (periodo) =>
                              periodo.codigo_periodo === (selectedPeriods[1] ?? '') ||
                              periodo.codigo_periodo !== (selectedPeriods[0] ?? '')
                          )
                          .map((periodo) => (
                            <option key={periodo.codigo_periodo} value={periodo.codigo_periodo}>
                              {periodOptionLabel(periodo)} | Codigo {periodo.codigo_periodo}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                ) : (
                  <p className="empty-block">No hay periodos disponibles en la base de datos.</p>
                )}
                <small className="teams-field-note">
                  Usa uno o dos periodos para cruzar materias y matriculas equivalentes en Teams.
                </small>
                {selectedPeriodSummary.length > 0 ? (
                  <div className="teams-inline-pills">
                    {selectedPeriodSummary.map((item) => (
                      <span key={item} className="teams-inline-pill">
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="teams-search-row teams-search-row--single">
              <div className="teams-field teams-field-card">
                <span>Paralelo desde base de datos</span>
                <div className="teams-multi-select teams-multi-select--compact">
                  {selectedPeriods.length === 0 ? (
                    <p className="empty-block">Selecciona uno o dos periodos para cargar los paralelos.</p>
                  ) : availableParallels.length > 0 ? (
                    availableParallels.map((paralelo) => {
                      const checked = selectedParallelSet.has(paralelo.paralelo)
                      return (
                        <label
                          key={paralelo.paralelo}
                          className={checked ? 'teams-option-card teams-option-card--active' : 'teams-option-card'}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSelectedParallel(paralelo.paralelo)}
                          />
                          <strong>{parallelOptionLabel(paralelo)}</strong>
                          <span>Paralelo {paralelo.paralelo}</span>
                        </label>
                      )
                    })
                  ) : (
                    <p className="empty-block">No hay paralelos disponibles con los filtros actuales.</p>
                  )}
                </div>
                <small className="teams-field-note">
                  {selectedPeriods.length > 0
                    ? `${availableParallels.length} paralelo(s) disponibles. Puedes seleccionar 1, 2 o mas paralelos.`
                    : 'Selecciona uno o dos periodos para cargar los paralelos.'}
                </small>
                <div className="teams-actions">
                  <button type="button" onClick={clearSelectedParallels} disabled={selectedParallels.length === 0}>
                    Limpiar paralelos
                  </button>
                </div>
                {selectedParallelSummary.length > 0 ? (
                  <div className="teams-inline-pills">
                    {selectedParallelSummary.map((item) => (
                      <span key={item} className="teams-inline-pill">
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="teams-search-row teams-search-row--single">
              <div className="teams-field teams-field-card">
                <span>Materias relacionadas por cod_materia</span>
                <input
                  value={materiaOptionQuery}
                  onChange={(event) => setMateriaOptionQuery(event.target.value)}
                  placeholder="Filtra materias por nombre, codigo o cod_materia"
                />
                <div className="teams-multi-select">
                  {selectedPeriods.length === 0 ? (
                    <p className="empty-block">Selecciona uno o dos periodos para cargar materias desde la base de datos.</p>
                  ) : filteredMateriaOptions.length > 0 ? (
                    filteredMateriaOptions.map((materia) => {
                      const checked = selectedMateriaSet.has(materia.materia_base_key)
                      return (
                        <label
                          key={materia.materia_base_key}
                          className={checked ? 'teams-option-card teams-option-card--active' : 'teams-option-card'}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSelectedMateria(materia.materia_base_key)}
                          />
                          <strong>{materiaOptionLabel(materia)}</strong>
                          <span>cod_materia {materia.materia_base_key}</span>
                          <small>
                            {materia.total_grupos ?? 0} grupos | {materia.total_estudiantes ?? 0} estudiantes
                          </small>
                        </label>
                      )
                    })
                  ) : (
                    <p className="empty-block">No hay materias disponibles con los filtros actuales.</p>
                  )}
                </div>
                <div className="teams-actions">
                  <button type="button" onClick={clearSelectedMaterias} disabled={selectedMateriaKeys.length === 0}>
                    Limpiar materias
                  </button>
                </div>
                {selectedMateriaSummary.length > 0 ? (
                  <div className="teams-inline-pills">
                    {selectedMateriaSummary.map((item) => (
                      <span key={item} className="teams-inline-pill">
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="teams-search-row teams-search-row--double">
              <label className="teams-field-card teams-field-card--limit">
                <span>Ano periodo</span>
                <input value={searchAnio} onChange={(event) => setSearchAnio(event.target.value)} placeholder="Ej: 2026" />
                <small className="teams-field-note">Opcional. Restringe la consulta a un ano lectivo puntual.</small>
              </label>

              <label className="teams-field-card teams-field-card--limit">
                <span>Limite</span>
                <input
                  value={searchLimit}
                  onChange={(event) => setSearchLimit(event.target.value)}
                  placeholder="100"
                  inputMode="numeric"
                />
                <small className="teams-field-note">Define el maximo de grupos que se muestran en la tabla de resultados.</small>
              </label>
            </div>
          </div>

          <div className="teams-actions">
            <button type="button" onClick={() => void handleSearchGroups()} disabled={groupsLoading || selectedPeriods.length === 0}>
              {groupsLoading ? 'Buscando...' : 'Buscar grupos'}
            </button>
          </div>

          {filterOptionsLoading ? <p className="teams-message">Cargando periodos, paralelos y materias desde la base de datos...</p> : null}
          {filterOptionsError ? <p className="teams-error">{filterOptionsError}</p> : null}
          {groupsMessage ? <p className="teams-message">{groupsMessage}</p> : null}
          {groupsError ? <p className="teams-error">{groupsError}</p> : null}

          {groups.length > 0 ? (
            <div className="teams-actions teams-group-selection-actions">
              <span>{checkedGroups.length} grupo(s) marcado(s)</span>
              <button
                type="button"
                onClick={() => void selectCheckedGroups()}
                disabled={checkedGroups.length === 0 || studentsLoading}
              >
                Seleccionar
              </button>
              <button
                type="button"
                onClick={() => void selectAllVisibleGroups()}
                disabled={studentsLoading}
              >
                Seleccionar todo
              </button>
            </div>
          ) : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th className="teams-selection-column">Sel.</th>
                  <th>Materia</th>
                  <th>Carrera</th>
                  <th>Paralelo</th>
                  <th>Periodo</th>
                  <th>Estudiantes</th>
                  <th>Con correo</th>
                </tr>
              </thead>
              <tbody>
                {groups.length > 0 ? (
                  groups.map((group) => {
                    const groupKey = groupSelectionKey(group)
                    const selected = selectedGroupKeySet.has(groupKey)
                    const checked = checkedGroupKeySet.has(groupKey)
                    return (
                      <tr
                        key={`${group.codigo_periodo}-${group.cod_anio_basica}-${group.paralelo}-${group.materia_base_key}`}
                        className={selected ? 'teams-enrollment-group-row--selected' : checked ? 'teams-enrollment-group-row--checked' : ''}
                      >
                        <td>
                          <label className="teams-group-check">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleGroupCheck(group)}
                              aria-label={`Marcar ${group.nombre_materia || group.materia_base_key || 'grupo'} ${groupCareerLabel(group) || ''}`}
                            />
                          </label>
                        </td>
                        <td>{group.nombre_materia || group.materia_base_key || '-'}</td>
                        <td>{groupCareerLabel(group) || '-'}</td>
                        <td>{groupParallelLabel(group) || '-'}</td>
                        <td>{group.detalle_periodo || group.codigo_periodo || '-'}</td>
                        <td>{group.total_estudiantes ?? 0}</td>
                        <td>{group.con_correo_intec ?? 0}</td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={7}>No hay grupos cargados. Ejecuta la busqueda con tus filtros.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Estudiantes del grupo</h3>
            <span>{selectedGroupScopeLabel}</span>
          </div>

          {selectedGroup ? (
            <>
              <p className="empty-block">
                Nombre sugerido del aula: <strong>{selectedGroup.suggested_team_name || 'N/D'}</strong>
              </p>
              {selectedGroups.length > 1 ? (
                <p className="teams-field-note">
                  Se combinaron {selectedGroups.length} grupos con el mismo cod_materia para preparar un solo Team.
                </p>
              ) : null}
              <div className="teams-actions">
                <button type="button" onClick={() => onCreateDisplayNameChange(selectedGroup.suggested_team_name || '')}>
                  Usar nombre sugerido
                </button>
                <button type="button" onClick={selectAllStudents} disabled={students.length === 0}>
                  Seleccionar todos
                </button>
                <button type="button" onClick={clearSelectedStudents} disabled={selectedStudentCodes.length === 0}>
                  Limpiar seleccion
                </button>
              </div>
            </>
          ) : (
            <p className="empty-block">Selecciona un grupo para ver y marcar estudiantes.</p>
          )}

          {studentsLoading ? <p className="teams-message">Cargando estudiantes del grupo...</p> : null}
          {studentsError ? <p className="teams-error">{studentsError}</p> : null}

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Sel.</th>
                  <th>Codigo</th>
                  <th>Nombre</th>
                  <th>Correo INTEC</th>
                  <th>Tipo</th>
                  <th>Periodo</th>
                  <th>Materia</th>
                </tr>
              </thead>
              <tbody>
                {students.length > 0 ? (
                  students.map((student) => (
                    <tr key={student.codigo_estud}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedStudentSet.has(student.codigo_estud)}
                          onChange={() => toggleStudent(student.codigo_estud)}
                        />
                      </td>
                      <td>{student.codigo_estud}</td>
                      <td>{student.nombre_estudiante || '-'}</td>
                      <td>{student.correo_intec || '-'}</td>
                      <td>{student.tipo_matricula || '-'}</td>
                      <td>{student.detalle_periodo || student.codigo_periodo || '-'}</td>
                      <td>{student.nombre_materia || student.codigo_materia || '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>No hay estudiantes cargados para el grupo seleccionado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide periodo-panel">
          <div className="card-head">
            <h3>Configuracion final</h3>
            <span>Creacion de aula y matriculacion manual</span>
          </div>

          <div className="teams-final-grid">
            <section className="teams-final-panel">
              <div className="card-head card-head--inner">
                <h3>Crear aula y asignar docentes</h3>
                <span>Operacion compuesta</span>
              </div>

              <p className="empty-block">
                El nombre del aula puede completarse desde la sugerencia generada por materia, carrera,
                paralelo y periodo. El equipo se crea como clase y, si ya marcaste estudiantes, se
                matriculan automaticamente al terminar la creacion.
              </p>

              <div className="teams-controls">
                <label>
                  <span>Nombre del aula</span>
                  <input
                    value={createDisplayName}
                    onChange={(event) => onCreateDisplayNameChange(event.target.value)}
                    placeholder="Ej: Contabilidad I - Carrera 14 - Paralelo A - 2026-1"
                  />
                </label>

                <label>
                  <span>Cursos</span>
                  <input
                    value={createCourses}
                    onChange={(event) => onCreateCoursesChange(event.target.value)}
                    placeholder="Ej: Contabilidad I"
                  />
                </label>

                <label>
                  <span>Docentes</span>
                  <input
                    value={createTeachers}
                    onChange={(event) => onCreateTeachersChange(event.target.value)}
                    placeholder="Ej: nombre.apellido@intec.edu.ec, nombre1.apellido1@intec.edu.ec"
                  />
                  <small className="teams-field-note">
                    Ingresa correo(s) con una separacion por coma. Los docentes se crean como propietarios del Team, aplica tambien para seguimiento
                    con rol de propietarios.
                  </small>
                </label>

                <label>
                  <span>Tipo de equipo</span>
                  <input value={createVisibility === 'educationClass' ? 'Clase (educationClass)' : createVisibility} readOnly />
                </label>
              </div>

              <div className="teams-actions">
                <button type="button" onClick={() => onCreateAndEnroll(buildCreateAndEnrollOptions())} disabled={createLoading}>
                  {createLoading
                    ? 'Creando...'
                    : selectedStudentCodes.length > 0
                      ? 'Crear aula y matricular seleccionados'
                      : 'Crear aula'}
                </button>
              </div>

              {createMessage ? <p className="teams-message">{createMessage}</p> : null}
              {createError ? <p className="teams-error">{createError}</p> : null}
            </section>

          </div>
        </article>
      </section>
    </>
  )
}
