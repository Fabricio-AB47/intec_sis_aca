import { useEffect, useMemo, useState } from 'react'

import {
  fetchAcademicEnrollmentCatalog,
  fetchAcademicTeacherEnrollments,
  fetchAcademicTeacherParallels,
  fetchAcademicTeacherParallelStudents,
  fetchAcademicTeacherUniqueSubjects,
  saveAcademicTeacherUniqueEnrollment,
  searchAcademicEnrollmentTeachers,
} from '../../lib/api'
import type {
  AcademicPeriodOption,
  AcademicTeacherEnrollment,
  AcademicTeacherParallelOption,
  AcademicTeacherOption,
  AcademicTeacherStudentItem,
  AcademicTeacherUniqueSubjectOption,
} from '../../types/app'

type MatriculaDocenteViewProps = {
  displayName: string
}

type ConfirmDialogState = {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  resolve: (confirmed: boolean) => void
}

function toNumber(value: string, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function valueOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function handleError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function uniqueTeachers(items: AcademicTeacherOption[]): AcademicTeacherOption[] {
  const seen = new Set<string>()
  return items.filter((teacher) => {
    if (!teacher.codigo_doc || seen.has(teacher.codigo_doc)) {
      return false
    }
    seen.add(teacher.codigo_doc)
    return true
  })
}

function subjectCareerCodes(subject: AcademicTeacherUniqueSubjectOption | null): string[] {
  return (subject?.carreras || []).map((career) => career.cod_anio_basica).filter(Boolean)
}

function subjectCareerNames(subject: AcademicTeacherUniqueSubjectOption | null): string {
  return (subject?.carreras || []).map((career) => career.nombre_carrera || career.cod_anio_basica).filter(Boolean).join(', ')
}

function subjectLevels(subject: AcademicTeacherUniqueSubjectOption | null): string[] {
  const levels = subject?.niveles?.length ? subject.niveles : subject?.semestre ? [subject.semestre] : []
  return [...new Set(levels.map((level) => String(level)).filter(Boolean))].sort((left, right) => toNumber(left) - toNumber(right))
}

export function MatriculaDocenteView({ displayName }: Readonly<MatriculaDocenteViewProps>) {
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [periods, setPeriods] = useState<AcademicPeriodOption[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState('')

  const [teacherQuery, setTeacherQuery] = useState('')
  const [validateTeacherUser, setValidateTeacherUser] = useState(true)
  const [teacherSearchLoading, setTeacherSearchLoading] = useState(false)
  const [teacherSearchError, setTeacherSearchError] = useState('')
  const [teacherOptions, setTeacherOptions] = useState<AcademicTeacherOption[]>([])
  const [selectedTeacherCode, setSelectedTeacherCode] = useState('')
  const [selectedTeacherRecord, setSelectedTeacherRecord] = useState<AcademicTeacherOption | null>(null)
  const [pendingTeacherCode, setPendingTeacherCode] = useState('')
  const [teacherSelectorOpen, setTeacherSelectorOpen] = useState(false)

  const [subjectQuery, setSubjectQuery] = useState('')
  const [subjectOptions, setSubjectOptions] = useState<AcademicTeacherUniqueSubjectOption[]>([])
  const [subjectLoading, setSubjectLoading] = useState(false)
  const [subjectError, setSubjectError] = useState('')
  const [selectedSubject, setSelectedSubject] = useState<AcademicTeacherUniqueSubjectOption | null>(null)
  const [selectedSubjectLevel, setSelectedSubjectLevel] = useState('')

  const [parallel, setParallel] = useState('')
  const [parallelOptions, setParallelOptions] = useState<AcademicTeacherParallelOption[]>([])
  const [parallelOptionsLoading, setParallelOptionsLoading] = useState(false)
  const [parallelOptionsError, setParallelOptionsError] = useState('')
  const [teacherJourney, setTeacherJourney] = useState('1')

  const [teacherEnrollments, setTeacherEnrollments] = useState<AcademicTeacherEnrollment[]>([])
  const [teacherEnrollmentsLoading, setTeacherEnrollmentsLoading] = useState(false)
  const [teacherActionError, setTeacherActionError] = useState('')
  const [teacherActionMessage, setTeacherActionMessage] = useState('')
  const [teacherSaveLoading, setTeacherSaveLoading] = useState(false)

  const [teacherStudents, setTeacherStudents] = useState<AcademicTeacherStudentItem[]>([])
  const [teacherStudentsLoading, setTeacherStudentsLoading] = useState(false)
  const [teacherStudentsError, setTeacherStudentsError] = useState('')
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null)

  const selectedPeriodName = periods.find((period) => period.codigo_periodo === selectedPeriod)?.detalle_periodo || ''
  const selectedTeacher =
    selectedTeacherRecord?.codigo_doc === selectedTeacherCode
      ? selectedTeacherRecord
      : teacherOptions.find((teacher) => teacher.codigo_doc === selectedTeacherCode)
  const selectedSubjectCode = selectedSubject?.cod_materia || ''
  const selectedSubjectLevels = useMemo(() => subjectLevels(selectedSubject), [selectedSubject])
  const selectedCareerCodes = useMemo(() => subjectCareerCodes(selectedSubject), [selectedSubject])
  const selectedCareerNames = useMemo(() => subjectCareerNames(selectedSubject), [selectedSubject])
  const selectedParallelOption = parallelOptions.find((item) => item.paralelo === parallel)
  const enrollmentSummary = useMemo(() => {
    const teacherCodes = new Set(teacherEnrollments.map((item) => item.codigo_doc).filter(Boolean))
    const subjectCodes = new Set(teacherEnrollments.map((item) => item.codigo_materia).filter(Boolean))
    return {
      docentes: teacherCodes.size,
      materias: subjectCodes.size,
      registros: teacherEnrollments.length,
    }
  }, [teacherEnrollments])

  useEffect(() => {
    let cancelled = false

    async function loadCatalog() {
      setCatalogLoading(true)
      setCatalogError('')
      try {
        const payload = await fetchAcademicEnrollmentCatalog()
        if (cancelled) return
        setPeriods(payload.periodos || [])
      } catch (error) {
        if (!cancelled) {
          setCatalogError(handleError(error, 'Error consultando catalogo academico'))
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
    setSelectedSubject(null)
    setSelectedSubjectLevel('')
    setSubjectQuery('')
    setParallel('')
    setParallelOptions([])
    setTeacherEnrollments([])
    setTeacherStudents([])
    setTeacherActionError('')
    setTeacherActionMessage('')
    if (selectedPeriod) {
      void loadSubjectOptions('', selectedPeriod)
    } else {
      setSubjectOptions([])
    }
  }, [selectedPeriod])

  useEffect(() => {
    if (!selectedPeriod) {
      clearParallelOptions()
      return
    }
    void loadParallelOptions()
  }, [selectedPeriod, selectedSubjectCode, selectedCareerCodes.join('|'), selectedSubjectLevel])

  useEffect(() => {
    if (!selectedPeriod || !selectedSubjectCode) {
      setTeacherEnrollments([])
      return
    }
    void loadTeacherEnrollments()
  }, [selectedPeriod, selectedSubjectCode, selectedCareerCodes.join('|'), selectedSubjectLevel, parallel])

  useEffect(() => {
    if (!selectedPeriod || !selectedSubjectCode || !parallel) {
      setTeacherStudents([])
      setTeacherStudentsError('')
      return
    }
    void loadTeacherStudents()
  }, [selectedPeriod, selectedSubjectCode, selectedCareerCodes.join('|'), selectedSubjectLevel, parallel])

  function teacherLabel(teacher: AcademicTeacherOption): string {
    const name = teacher.descripcion || teacher.login || teacher.codigo_doc
    return `${name}${teacher.cedula ? ` - ${teacher.cedula}` : ''}`
  }

  function clearTeacherMessages() {
    setTeacherActionError('')
    setTeacherActionMessage('')
  }

  function clearParallelOptions() {
    setParallel('')
    setParallelOptions([])
    setParallelOptionsError('')
  }

  function clearSelectedTeacher() {
    setSelectedTeacherCode('')
    setSelectedTeacherRecord(null)
    setPendingTeacherCode('')
    setTeacherQuery('')
    setTeacherStudents([])
    setTeacherStudentsError('')
    clearTeacherMessages()
  }

  function selectTeacher(code: string) {
    setSelectedTeacherCode(code)
    setPendingTeacherCode(code)
    const teacher = teacherOptions.find((item) => item.codigo_doc === code)
    if (teacher) {
      setSelectedTeacherRecord(teacher)
      setTeacherQuery(teacherLabel(teacher))
    }
    setTeacherStudents([])
    setTeacherStudentsError('')
    clearTeacherMessages()
  }

  function openTeacherSelector() {
    setPendingTeacherCode(selectedTeacherCode)
    setTeacherQuery('')
    setTeacherSelectorOpen(true)
    void loadTeacherOptions('', validateTeacherUser)
  }

  function confirmTeacherSelection() {
    if (!pendingTeacherCode) {
      setTeacherSearchError('Marca un docente para continuar.')
      return
    }
    selectTeacher(pendingTeacherCode)
    setTeacherSelectorOpen(false)
  }

  function selectSubject(subject: AcademicTeacherUniqueSubjectOption) {
    setSelectedSubject(subject)
    setSelectedSubjectLevel(subjectLevels(subject)[0] || '')
    setSubjectQuery(`${subject.nombre_materia} - ${subject.cod_materia}`)
    setParallelOptionsError('')
    setTeacherEnrollments([])
    setTeacherStudents([])
    clearTeacherMessages()
  }

  function clearSelectedSubject() {
    setSelectedSubject(null)
    setSelectedSubjectLevel('')
    setSubjectQuery('')
    clearParallelOptions()
    setTeacherEnrollments([])
    setTeacherStudents([])
    clearTeacherMessages()
  }

  function requestConfirm(title: string, message: string) {
    return new Promise<boolean>((resolve) => {
      setConfirmDialog({
        title,
        message,
        confirmLabel: 'Aceptar',
        cancelLabel: 'Cancelar',
        resolve,
      })
    })
  }

  function closeConfirmDialog(confirmed: boolean) {
    if (!confirmDialog) return
    confirmDialog.resolve(confirmed)
    setConfirmDialog(null)
  }

  async function loadTeacherOptions(queryValue: string = teacherQuery, validarUsuario: boolean = validateTeacherUser) {
    const query = queryValue.trim()
    if (query.length === 1) {
      setTeacherSearchError('Ingresa al menos 2 caracteres para filtrar docente.')
      return
    }
    setTeacherSearchLoading(true)
    setTeacherSearchError('')
    setTeacherActionMessage('')
    try {
      const payload = await searchAcademicEnrollmentTeachers(query, query ? 200 : 1000, validarUsuario)
      const items = uniqueTeachers(payload.items || [])
      setTeacherOptions(items)
      setPendingTeacherCode((current) => (items.some((teacher) => teacher.codigo_doc === current) ? current : ''))
      if (items.length === 0) {
        setTeacherSearchError(query ? 'No se encontraron docentes para la busqueda.' : 'No hay docentes para listar.')
      }
    } catch (error) {
      setTeacherSearchError(handleError(error, 'Error buscando docentes'))
      setTeacherOptions([])
      setPendingTeacherCode('')
    } finally {
      setTeacherSearchLoading(false)
    }
  }

  async function searchTeachers() {
    await loadTeacherOptions()
  }

  async function loadSubjectOptions(queryValue: string = subjectQuery, periodCode: string = selectedPeriod) {
    if (!periodCode) {
      setSubjectError('Selecciona primero el periodo.')
      return
    }
    setSubjectLoading(true)
    setSubjectError('')
    try {
      const payload = await fetchAcademicTeacherUniqueSubjects({
        codigoPeriodo: periodCode,
        buscar: queryValue.trim(),
        limite: 150,
      })
      const items = payload.items || []
      setSubjectOptions(items)
      if (items.length === 0) {
        setSubjectError(queryValue.trim() ? 'No hay materias para ese filtro.' : 'No hay materias matriculadas en el periodo seleccionado.')
      }
    } catch (error) {
      setSubjectOptions([])
      setSubjectError(handleError(error, 'Error consultando materias unicas'))
    } finally {
      setSubjectLoading(false)
    }
  }

  async function loadParallelOptions() {
    if (!selectedPeriod) {
      clearParallelOptions()
      return
    }
    setParallelOptionsLoading(true)
    setParallelOptionsError('')
    try {
      const payload = await fetchAcademicTeacherParallels(selectedCareerCodes, selectedPeriod, selectedSubjectCode, selectedSubjectLevel)
      const items = (payload.items || []).sort((left, right) => String(left.paralelo).localeCompare(String(right.paralelo)))
      setParallelOptions(items)
      setParallel((current) => (items.some((item) => item.paralelo === current) ? current : items[0]?.paralelo || ''))
    } catch (error) {
      setParallelOptions([])
      setParallel('')
      setParallelOptionsError(handleError(error, 'Error consultando paralelos matriculados'))
    } finally {
      setParallelOptionsLoading(false)
    }
  }

  async function loadTeacherEnrollments() {
    if (!selectedPeriod || !selectedSubjectCode) {
      setTeacherEnrollments([])
      return
    }
    setTeacherEnrollmentsLoading(true)
    setTeacherActionError('')
    try {
      const payload = await fetchAcademicTeacherEnrollments(
        selectedCareerCodes,
        selectedPeriod,
        selectedSubjectCode,
        parallel.trim().toUpperCase() || '',
        selectedSubjectLevel
      )
      setTeacherEnrollments(payload.items || [])
    } catch (error) {
      setTeacherActionError(handleError(error, 'Error consultando docentes matriculados'))
      setTeacherEnrollments([])
    } finally {
      setTeacherEnrollmentsLoading(false)
    }
  }

  async function loadTeacherStudents() {
    if (!selectedPeriod || !selectedSubjectCode || !parallel) {
      setTeacherStudents([])
      setTeacherStudentsError('Selecciona periodo, materia y paralelo para ver estudiantes.')
      return
    }
    setTeacherStudentsLoading(true)
    setTeacherStudentsError('')
    try {
      const payload = await fetchAcademicTeacherParallelStudents(
        selectedPeriod,
        selectedSubjectCode,
        parallel.trim().toUpperCase(),
        selectedCareerCodes,
        selectedSubjectLevel
      )
      setTeacherStudents(payload.items || [])
    } catch (error) {
      setTeacherStudents([])
      setTeacherStudentsError(handleError(error, 'Error consultando estudiantes del paralelo'))
    } finally {
      setTeacherStudentsLoading(false)
    }
  }

  async function saveTeacherEnrollment() {
    if (!selectedTeacherCode || !selectedPeriod || !selectedSubjectCode) {
      setTeacherActionError('Selecciona docente, periodo y materia unica.')
      return
    }
    if (!parallel.trim()) {
      setTeacherActionError('Selecciona un paralelo con estudiantes matriculados.')
      return
    }
    const confirmed = await requestConfirm(
      'Matricular docente',
      `Matricular ${selectedTeacher?.descripcion || selectedTeacher?.login || selectedTeacherCode} en ${selectedSubject?.nombre_materia || selectedSubjectCode}, periodo ${selectedPeriodName || selectedPeriod}, paralelo ${parallel}?`
    )
    if (!confirmed) return

    setTeacherSaveLoading(true)
    setTeacherActionError('')
    setTeacherActionMessage('')
    try {
      const response = await saveAcademicTeacherUniqueEnrollment({
        codigo_doc: Number(selectedTeacherCode),
        cod_materia: selectedSubjectCode,
        codigo_periodo: Number(selectedPeriod),
        paralelo: parallel.trim().toUpperCase(),
        semestre: selectedSubjectLevel ? Number(selectedSubjectLevel) : null,
        cod_jornada: toNumber(teacherJourney, 1),
        estado_moodle_doc: 0,
      })
      const inserted = response.inserted_count ?? (response.action === 'INSERTADA' ? 1 : 0)
      const existing = response.existing_count ?? (response.action === 'EXISTENTE' ? 1 : 0)
      const linked = response.students_linked ?? 0
      if (response.ok === false || response.already_exists || response.action === 'EXISTENTE') {
        setTeacherActionError(
          `${response.message || 'La matricula docente ya existe.'} Estudiantes vinculados: ${linked}.`
        )
      } else {
        setTeacherActionMessage(
          `Matricula docente guardada. Insertadas ${inserted}, existentes ${existing}, estudiantes vinculados ${linked}.`
        )
      }
      await loadTeacherEnrollments()
      await loadTeacherStudents()
    } catch (error) {
      setTeacherActionError(handleError(error, 'Error guardando matricula docente'))
    } finally {
      setTeacherSaveLoading(false)
    }
  }

  return (
    <div className="student-dashboard">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Matricula Docente</p>
          <h1>Matricula docente</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Registros</span>
          <strong>{teacherEnrollments.length} docentes</strong>
        </div>
      </header>

      <section className="student-grid student-grid--content matricula-docente-grid">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Parametros</span>
              <h2>{selectedSubject?.nombre_materia || 'Selecciona periodo, materia y paralelo'}</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadTeacherEnrollments()}
                disabled={teacherEnrollmentsLoading || !selectedPeriod || !selectedSubjectCode}
              >
                {teacherEnrollmentsLoading ? 'Cargando...' : 'Actualizar'}
              </button>
              <button
                type="button"
                className="primary-action"
                onClick={saveTeacherEnrollment}
                disabled={teacherSaveLoading || !selectedTeacherCode || !selectedPeriod || !selectedSubjectCode || !parallel}
              >
                {teacherSaveLoading ? 'Guardando...' : 'Matricular docente'}
              </button>
            </div>
          </div>

          {catalogError ? <p className="form-error">{catalogError}</p> : null}
          {subjectError ? <p className="form-error">{subjectError}</p> : null}
          {parallelOptionsError ? <p className="form-error">{parallelOptionsError}</p> : null}
          {teacherActionError ? <p className="form-error">{teacherActionError}</p> : null}
          {teacherActionMessage ? <p className="form-success">{teacherActionMessage}</p> : null}
          {!selectedTeacherCode ? <p className="form-success">Selecciona primero el docente para habilitar la matriculacion.</p> : null}

          <div className="matricula-docente-main-selector">
            <div className="matricula-docente-loaded">
              <div>
                <span>Docente seleccionado</span>
                <strong>{selectedTeacher ? teacherLabel(selectedTeacher) : 'Sin docente seleccionado'}</strong>
              </div>
              <label className="matricula-acad-check matricula-docente-user-check">
                <input
                  type="checkbox"
                  checked={validateTeacherUser}
                  onChange={(event) => {
                    setValidateTeacherUser(event.target.checked)
                    setTeacherOptions([])
                    clearSelectedTeacher()
                  }}
                />
                Validar con usuario
              </label>
            </div>
            <div className="matricula-acad-actions matricula-docente-school-actions">
              <button type="button" className="primary-action" onClick={openTeacherSelector}>
                Seleccionar docente
              </button>
              <button type="button" className="ghost-button" onClick={clearSelectedTeacher} disabled={!selectedTeacherCode && !teacherQuery}>
                Limpiar docente
              </button>
            </div>
            {teacherSearchError ? <p className="form-error">{teacherSearchError}</p> : null}
          </div>

          <div className="matricula-acad-form">
            <label>
              <span>Periodo</span>
              <select
                value={selectedPeriod}
                disabled={catalogLoading}
                onChange={(event) => setSelectedPeriod(event.target.value)}
              >
                <option value="">Seleccionar</option>
                {periods.map((period) => (
                  <option key={period.codigo_periodo} value={period.codigo_periodo}>
                    {period.detalle_periodo} {period.anio ? `(${period.anio})` : ''} - {period.total_matriculados ?? 0}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Paralelo</span>
              <select
                value={parallel}
                disabled={parallelOptionsLoading || !selectedPeriod}
                onChange={(event) => setParallel(event.target.value)}
              >
                <option value="">{parallelOptionsLoading ? 'Cargando...' : 'Seleccionar'}</option>
                {parallelOptions.map((item) => (
                  <option key={item.paralelo} value={item.paralelo}>
                    {item.paralelo} - {item.total_estudiantes ?? 0} estudiante(s)
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Jornada</span>
              <input type="number" min="0" value={teacherJourney} onChange={(event) => setTeacherJourney(event.target.value)} />
            </label>
            <label>
              <span>Nivel materia</span>
              <select
                value={selectedSubjectLevel}
                disabled={!selectedSubject || selectedSubjectLevels.length <= 1}
                onChange={(event) => {
                  setSelectedSubjectLevel(event.target.value)
                  setTeacherStudents([])
                  setTeacherEnrollments([])
                  clearTeacherMessages()
                }}
              >
                <option value="">{selectedSubject ? 'Seleccionar' : 'Selecciona materia'}</option>
                {selectedSubjectLevels.map((level) => (
                  <option key={level} value={level}>
                    Nivel {level}
                  </option>
                ))}
              </select>
            </label>
            <div className="matricula-acad-career-picker matricula-docente-subject-picker">
              <span>Materia unica</span>
              {!selectedPeriod ? <p>Selecciona primero el periodo para buscar materias matriculadas.</p> : null}
              <div className="matricula-docente-selector-controls">
                <label>
                  <span>Buscar materia</span>
                  <input
                    value={subjectQuery}
                    placeholder="Codigo comun, codigo interno o nombre"
                    disabled={!selectedPeriod}
                    onChange={(event) => setSubjectQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        void loadSubjectOptions()
                      }
                    }}
                  />
                </label>
                <button type="button" className="ghost-button" onClick={() => void loadSubjectOptions()} disabled={!selectedPeriod || subjectLoading}>
                  {subjectLoading ? 'Buscando...' : 'Buscar'}
                </button>
                <button type="button" className="ghost-button" onClick={clearSelectedSubject} disabled={!selectedSubject}>
                  Limpiar
                </button>
              </div>
              {selectedSubject ? (
                <div className="matricula-acad-preview matricula-docente-teacher-detail">
                  <div>
                    <span>Materia seleccionada</span>
                    <strong>{selectedSubject.nombre_materia}</strong>
                  </div>
                  <div>
                    <span>Codigo comun</span>
                    <strong>{selectedSubject.cod_materia}</strong>
                  </div>
                  <div>
                    <span>Nivel</span>
                    <strong>{selectedSubjectLevel ? `Nivel ${selectedSubjectLevel}` : valueOrDash(selectedSubject.semestre)}</strong>
                  </div>
                  <div>
                    <span>Carreras vinculadas</span>
                    <strong>{selectedCareerNames || '-'}</strong>
                  </div>
                  <div>
                    <span>Estudiantes del periodo</span>
                    <strong>{selectedSubject.total_estudiantes ?? 0}</strong>
                  </div>
                </div>
              ) : null}
              <div className="matricula-acad-career-options">
                {subjectOptions.map((subject) => {
                  const active = selectedSubject?.cod_materia === subject.cod_materia
                  return (
                    <button
                      key={subject.cod_materia}
                      type="button"
                      className={`matricula-acad-career-option ${active ? 'matricula-acad-career-option--active matricula-acad-career-option--focus' : ''}`}
                      disabled={!selectedPeriod}
                      onClick={() => selectSubject(subject)}
                    >
                      <input type="checkbox" checked={active} readOnly tabIndex={-1} />
                      <strong>{subject.nombre_materia}</strong>
                      <small>
                        {subject.cod_materia} - Nivel {valueOrDash(subject.semestre)} - {subject.total_estudiantes ?? 0} estudiante(s)
                      </small>
                      <small>{subjectCareerNames(subject) || 'Sin carrera vinculada'}</small>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="matricula-acad-context">
            <span>{selectedPeriodName || 'Periodo pendiente'}</span>
            <span>{selectedSubject?.nombre_materia || 'Materia pendiente'}</span>
            <span>Nivel {selectedSubjectLevel || 'pendiente'}</span>
            <span>{selectedCareerCodes.length} carrera(s) vinculada(s)</span>
            <span>
              Paralelo {parallel.trim().toUpperCase() || 'pendiente'}: {selectedParallelOption?.total_estudiantes ?? 0} estudiante(s)
            </span>
          </div>
        </article>

        <aside className="student-card matricula-panel">
          <div className="section-title">
            <div>
              <span>Docente</span>
              <h2>{selectedTeacher?.descripcion || selectedTeacher?.login || 'Sin docente'}</h2>
            </div>
          </div>

          {selectedTeacher ? (
            <div className="matricula-acad-preview matricula-docente-teacher-detail">
              <div>
                <span>Cedula</span>
                <strong>{selectedTeacher.cedula || '-'}</strong>
              </div>
              <div>
                <span>Correo</span>
                <strong>{selectedTeacher.correo || selectedTeacher.correo_personal || '-'}</strong>
              </div>
              <div>
                <span>Telefono</span>
                <strong>{selectedTeacher.movil || selectedTeacher.telefono || '-'}</strong>
              </div>
              <div>
                <span>Tipo</span>
                <strong>{selectedTeacher.tipo_docente || selectedTeacher.tipo_usuario || '-'}</strong>
              </div>
              <div>
                <span>Unidad</span>
                <strong>{selectedTeacher.unidad_academica || '-'}</strong>
              </div>
              <div>
                <span>Asignaciones</span>
                <strong>{selectedTeacher.total_matriculas_docente ?? 0}</strong>
              </div>
            </div>
          ) : null}
          {!selectedTeacher ? <p className="form-success">Usa el boton Seleccionar docente para buscar y marcar un unico docente.</p> : null}
        </aside>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Listado</span>
              <h2>Docentes matriculados</h2>
            </div>
            <div className="matricula-acad-preview matricula-docente-summary">
              <div>
                <span>Docentes</span>
                <strong>{enrollmentSummary.docentes}</strong>
              </div>
              <div>
                <span>Materias</span>
                <strong>{enrollmentSummary.materias}</strong>
              </div>
              <div>
                <span>Registros</span>
                <strong>{enrollmentSummary.registros}</strong>
              </div>
            </div>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Docente</th>
                  <th>Contacto</th>
                  <th>Tipo</th>
                  <th>Materia</th>
                  <th>Carrera</th>
                  <th>Periodo</th>
                  <th>Paralelo</th>
                  <th>Jornada</th>
                </tr>
              </thead>
              <tbody>
                {teacherEnrollmentsLoading ? (
                  <tr>
                    <td colSpan={8}>Cargando docentes...</td>
                  </tr>
                ) : null}
                {!teacherEnrollmentsLoading && teacherEnrollments.length === 0 ? (
                  <tr>
                    <td colSpan={8}>Sin docentes matriculados para los filtros seleccionados.</td>
                  </tr>
                ) : null}
                {teacherEnrollments.map((item) => (
                  <tr key={`${item.codigo_doc}-${item.codigo_periodo}-${item.codigo_materia}-${item.paralelo}-${item.cod_jornada}`}>
                    <td>
                      <strong>{item.descripcion || item.login || item.codigo_doc}</strong>
                      <span>{item.cedula || '-'}</span>
                    </td>
                    <td>
                      <strong>{item.correo || item.login || '-'}</strong>
                      <span>{item.movil || item.telefono || '-'}</span>
                    </td>
                    <td>{item.tipo_docente || item.tipo_usuario || '-'}</td>
                    <td>{item.nombre_materia || item.codigo_materia || '-'}</td>
                    <td>{item.nombre_carrera || item.cod_anio_basica || '-'}</td>
                    <td>{item.detalle_periodo || item.codigo_periodo || '-'}</td>
                    <td>{item.paralelo || '-'}</td>
                    <td>{valueOrDash(item.cod_jornada)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="student-grid student-grid--content">
        <article className="student-card student-card--wide matricula-panel">
          <div className="section-title">
            <div>
              <span>Estudiantes</span>
              <h2>Estudiantes del paralelo seleccionado</h2>
            </div>
            <div className="matricula-acad-title-actions">
              <span>{teacherStudentsLoading ? 'Cargando...' : `${teacherStudents.length} registro(s)`}</span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadTeacherStudents()}
                disabled={!selectedPeriod || !selectedSubjectCode || !parallel || teacherStudentsLoading}
              >
                {teacherStudentsLoading ? 'Actualizando...' : 'Actualizar estudiantes'}
              </button>
            </div>
          </div>
          {teacherStudentsError ? <p className="form-error">{teacherStudentsError}</p> : null}
          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Estudiante</th>
                  <th>Cedula</th>
                  <th>Carrera</th>
                  <th>Periodo</th>
                  <th>Materia</th>
                  <th>Paralelo</th>
                  <th>Matricula</th>
                  <th>Promedio</th>
                </tr>
              </thead>
              <tbody>
                {teacherStudentsLoading ? (
                  <tr>
                    <td colSpan={8}>Cargando estudiantes...</td>
                  </tr>
                ) : null}
                {!teacherStudentsLoading && teacherStudents.length === 0 ? (
                  <tr>
                    <td colSpan={8}>Sin estudiantes matriculados para ese periodo, materia y paralelo.</td>
                  </tr>
                ) : null}
                {teacherStudents.map((student) => (
                  <tr key={`${student.codigo_periodo}-${student.codigo_estud}-${student.codigo_materia}-${student.paralelo}`}>
                    <td>
                      <strong>{student.nombre_estudiante || student.codigo_estud}</strong>
                      <span>{student.correo_intec || student.correo_personal || '-'}</span>
                    </td>
                    <td>{student.cedula || '-'}</td>
                    <td>{student.nombre_carrera || student.cod_anio_basica || '-'}</td>
                    <td>{student.detalle_periodo || student.codigo_periodo || '-'}</td>
                    <td>{student.nombre_materia || student.codigo_materia || '-'}</td>
                    <td>{student.paralelo || '-'}</td>
                    <td>{student.num_matricula || '-'}</td>
                    <td>{valueOrDash(student.promedio_final)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {teacherSelectorOpen ? (
        <div className="matricula-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="teacher-selector-title">
          <article className="matricula-modal matricula-docente-selector-modal">
            <div className="matricula-modal-head">
              <div className="matricula-modal-title">
                <span>Docente</span>
                <h3 id="teacher-selector-title">Seleccionar docente</h3>
              </div>
              <button type="button" className="matricula-modal-close" onClick={() => setTeacherSelectorOpen(false)}>
                Cerrar
              </button>
            </div>

            <div className="matricula-docente-selector-controls">
              <label>
                <span>Buscar docente</span>
                <input
                  value={teacherQuery}
                  placeholder="Cedula, correo o nombre"
                  onChange={(event) => setTeacherQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void searchTeachers()
                    }
                  }}
                />
              </label>
              <label className="matricula-acad-check matricula-docente-user-check">
                <input
                  type="checkbox"
                  checked={validateTeacherUser}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setValidateTeacherUser(checked)
                    setPendingTeacherCode('')
                    void loadTeacherOptions(teacherQuery, checked)
                  }}
                />
                Validar con usuario
              </label>
              <button type="button" className="ghost-button" onClick={() => void searchTeachers()} disabled={teacherSearchLoading}>
                {teacherSearchLoading ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {teacherSearchError ? <p className="form-error">{teacherSearchError}</p> : null}

            <div className="matricula-docente-selector-summary">
              <strong>Listado completo de docentes existentes</strong>
              <span>{teacherSearchLoading ? 'Cargando docentes...' : `${teacherOptions.length} docente(s) cargado(s)`}</span>
            </div>

            <div className="matricula-docente-selector-list">
              {teacherOptions.length === 0 && !teacherSearchLoading ? (
                <div className="matricula-docente-selector-empty">
                  <strong>Sin resultados</strong>
                  <span>No hay docentes para los filtros aplicados.</span>
                </div>
              ) : null}
              {teacherOptions.map((teacher) => {
                const checked = pendingTeacherCode === teacher.codigo_doc
                return (
                  <button
                    key={teacher.codigo_doc}
                    type="button"
                    className={`matricula-acad-teacher-option ${checked ? 'matricula-acad-teacher-option--active' : ''}`}
                    onClick={() => setPendingTeacherCode(checked ? '' : teacher.codigo_doc)}
                  >
                    <label className="matricula-docente-check-row" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => setPendingTeacherCode(checked ? '' : teacher.codigo_doc)}
                      />
                      <strong>{teacher.descripcion || teacher.login || teacher.codigo_doc}</strong>
                    </label>
                    <span>{teacher.cedula || 'Sin cedula'} - {teacher.correo || teacher.login || 'Sin correo'}</span>
                    <span>
                      {teacher.tipo_docente || teacher.tipo_usuario || 'Docente'} - {teacher.total_carreras_docente ?? 0} carrera(s) -{' '}
                      {teacher.total_materias_docente ?? 0} materia(s)
                    </span>
                    <span>{teacher.usuario_validado ? 'Usuario validado' : 'Sin usuario vinculado'}</span>
                  </button>
                )
              })}
            </div>

            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setTeacherSelectorOpen(false)}>
                Cancelar
              </button>
              <button type="button" className="primary-action" onClick={confirmTeacherSelection} disabled={!pendingTeacherCode}>
                Seleccionar docente
              </button>
            </div>
          </article>
        </div>
      ) : null}

      {confirmDialog ? (
        <div className="matricula-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="matricula-docente-confirm-title">
          <div className="matricula-confirm-modal">
            <div>
              <span>Confirmacion</span>
              <h2 id="matricula-docente-confirm-title">{confirmDialog.title}</h2>
              <p>{confirmDialog.message}</p>
            </div>
            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => closeConfirmDialog(false)}>
                {confirmDialog.cancelLabel}
              </button>
              <button type="button" className="primary-action" onClick={() => closeConfirmDialog(true)} autoFocus>
                {confirmDialog.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
