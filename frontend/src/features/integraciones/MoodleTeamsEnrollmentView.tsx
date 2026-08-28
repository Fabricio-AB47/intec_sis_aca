import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  ApiError,
  enrollMoodleCourseInTeams,
  fetchMoodleCourses,
  previewMoodleTeamsEnrollment,
} from '../../lib/api'
import type {
  MoodleCourse,
  MoodleTeamsEnrollmentResponse,
  MoodleTeamsParticipant,
  MoodleTeamsPreviewResponse,
} from '../../types/app'

type MoodleTeamsEnrollmentViewProps = {
  displayName: string
}

type MoodleTeamsEnrollmentData = NonNullable<MoodleTeamsEnrollmentResponse['enrollment']>
type MoodleTeamsEnrollmentItem = NonNullable<MoodleTeamsEnrollmentData['items']>[number]
  & Partial<MoodleTeamsParticipant>

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return 'No se pudo completar la matrícula Moodle-Teams.'
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-EC').format(value)
}

function courseLabel(course: MoodleCourse): string {
  const name = course.fullname || course.displayname || course.shortname || `Curso ${course.id}`
  const code = course.shortname && course.shortname !== name ? ` · ${course.shortname}` : ''
  return `${name}${code}`
}

function participantStatusClass(status: string): string {
  if (['ready', 'needs_promotion'].includes(status)) return 'is-ready'
  if (['already_in_team', 'already_owner'].includes(status)) return 'is-existing'
  if (status === 'ignored') return 'is-ignored'
  return 'is-error'
}

function normalizeSearchValue(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLocaleLowerCase('es-EC')
}

function isSelectableStudent(participant: MoodleTeamsParticipant): boolean {
  return participant.moodle_user_id > 0 && ['ready', 'already_in_team'].includes(participant.status)
}

function participantMatchesQuery(participant: MoodleTeamsParticipant, query: string): boolean {
  const tokens = normalizeSearchValue(query).split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return true
  const searchable = normalizeSearchValue([
    participant.full_name,
    participant.email,
    participant.moodle_username,
    participant.moodle_user_id,
    participant.graph_display_name,
    participant.graph_mail,
    participant.graph_user_principal_name,
    ...participant.moodle_roles,
  ].join(' '))
  return tokens.every((token) => searchable.includes(token))
}

function enrollmentItemName(item: MoodleTeamsEnrollmentItem): string {
  return item.full_name || item.graph_display_name || item.nombre_estudiante || 'Usuario sin nombre'
}

function enrollmentItemEmail(item: MoodleTeamsEnrollmentItem): string {
  return item.email
    || item.correo_intec
    || item.graph_mail
    || item.graph_user_principal_name
    || 'Sin correo institucional'
}

function EnrollmentResultDetails({
  title,
  description,
  count,
  items,
  emptyMessage,
}: {
  title: string
  description: string
  count: number
  items: MoodleTeamsEnrollmentItem[]
  emptyMessage: string
}) {
  return (
    <details className="moodle-teams-result-detail">
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        <strong>{formatNumber(count)}</strong>
      </summary>
      <div className="moodle-teams-result-detail__body">
        {items.length > 0 ? (
          <div className="moodle-teams-result-detail__table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Correo institucional</th>
                  <th>Estado</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr key={`${item.moodle_user_id || item.codigo_estud || index}-${enrollmentItemEmail(item)}`}>
                    <td>{enrollmentItemName(item)}</td>
                    <td>{enrollmentItemEmail(item)}</td>
                    <td>{item.status_label || item.status || 'Sin estado'}</td>
                    <td>{item.error || item.reason || 'Sin novedades'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="moodle-teams-result-detail__empty">{emptyMessage}</p>
        )}
      </div>
    </details>
  )
}

function ParticipantTable({
  title,
  participants,
  emptyMessage,
  selectable = false,
  selectedIds,
  onToggle,
}: {
  title: string
  participants: MoodleTeamsParticipant[]
  emptyMessage: string
  selectable?: boolean
  selectedIds?: Set<number>
  onToggle?: (participant: MoodleTeamsParticipant) => void
}) {
  return (
    <section className="moodle-teams-participants" aria-labelledby={`moodle-teams-${title}`}>
      <div className="moodle-teams-section-head">
        <h3 id={`moodle-teams-${title}`}>{title}</h3>
        <strong>{formatNumber(participants.length)}</strong>
      </div>
      <div className="moodle-teams-table-wrap">
        <table className="moodle-teams-table">
          <thead>
            <tr>
              {selectable ? <th className="moodle-teams-select-column">Seleccionar</th> : null}
              <th>Nombre</th>
              <th>Correo institucional</th>
              <th>Rol Moodle</th>
              <th>Estado en Microsoft 365</th>
            </tr>
          </thead>
          <tbody>
            {participants.map((participant) => {
              const canSelect = selectable && isSelectableStudent(participant)
              const isSelected = Boolean(selectedIds?.has(participant.moodle_user_id))
              return (
              <tr
                key={`${participant.role}-${participant.moodle_user_id}-${participant.email}`}
                className={isSelected ? 'is-selected' : ''}
              >
                {selectable ? (
                  <td className="moodle-teams-select-column">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      disabled={!canSelect}
                      aria-label={`Seleccionar a ${participant.full_name || participant.email}`}
                      onChange={() => onToggle?.(participant)}
                    />
                  </td>
                ) : null}
                <td>
                  <strong>{participant.full_name || 'Sin nombre'}</strong>
                  {participant.moodle_username ? <small>Usuario Moodle: {participant.moodle_username}</small> : null}
                  {participant.fixed_administrator ? <small>Administrador fijo del aula</small> : null}
                </td>
                <td>{participant.email || 'Sin correo institucional'}</td>
                <td>{participant.moodle_roles.join(', ') || (participant.role === 'administrator' ? 'Administrador' : 'Sin rol')}</td>
                <td>
                  <span className={`moodle-teams-status ${participantStatusClass(participant.status)}`}>
                    {participant.status_label || participant.reason || 'Sin validar'}
                  </span>
                  {participant.error || participant.reason ? (
                    <small>{participant.error || participant.reason}</small>
                  ) : null}
                  {participant.graph_user_type ? (
                    <small>Tipo de cuenta: {participant.graph_user_type}</small>
                  ) : null}
                </td>
              </tr>
              )
            })}
            {participants.length === 0 ? (
              <tr>
                <td colSpan={selectable ? 5 : 4} className="moodle-teams-empty">{emptyMessage}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function MoodleTeamsEnrollmentView({ displayName }: MoodleTeamsEnrollmentViewProps) {
  const [query, setQuery] = useState('')
  const [courses, setCourses] = useState<MoodleCourse[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [preview, setPreview] = useState<MoodleTeamsPreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [studentQuery, setStudentQuery] = useState('')
  const [selectedStudentIds, setSelectedStudentIds] = useState<number[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [teamDisplayName, setTeamDisplayName] = useState('')
  const [enrollLoading, setEnrollLoading] = useState(false)
  const [result, setResult] = useState<MoodleTeamsEnrollmentResponse | null>(null)

  const loadCourses = useCallback(async (search = '', refresh = false) => {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const response = await fetchMoodleCourses({
        page: 1,
        pageSize: 100,
        search: search.trim(),
        visibility: 'all',
        refresh,
      })
      setCourses(response.items)
      setSelectedCourseId((current) => {
        if (current && response.items.some((course) => course.id === current)) return current
        return null
      })
    } catch (error) {
      setCatalogError(errorMessage(error))
    } finally {
      setCatalogLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCourses()
  }, [loadCourses])

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === selectedCourseId) || null,
    [courses, selectedCourseId],
  )

  const selectedStudentSet = useMemo(() => new Set(selectedStudentIds), [selectedStudentIds])
  const filteredStudents = useMemo(
    () => (preview?.students || []).filter((student) => participantMatchesQuery(student, studentQuery)),
    [preview, studentQuery],
  )
  const selectableVisibleStudentIds = useMemo(
    () => filteredStudents.filter(isSelectableStudent).map((student) => student.moodle_user_id),
    [filteredStudents],
  )
  const allVisibleStudentsSelected = selectableVisibleStudentIds.length > 0
    && selectableVisibleStudentIds.every((studentId) => selectedStudentSet.has(studentId))

  const applyPreview = useCallback((nextPreview: MoodleTeamsPreviewResponse) => {
    setPreview(nextPreview)
    setTeamDisplayName(nextPreview.team.display_name)
    setSelectedStudentIds(
      nextPreview.students.filter(isSelectableStudent).map((student) => student.moodle_user_id),
    )
    setStudentQuery('')
  }, [])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPreview(null)
    setSelectedStudentIds([])
    setResult(null)
    void loadCourses(query)
  }

  const handlePreview = async (refresh = false) => {
    if (!selectedCourseId) return
    setPreviewLoading(true)
    setPreviewError('')
    setResult(null)
    try {
      applyPreview(await previewMoodleTeamsEnrollment(selectedCourseId, refresh))
    } catch (error) {
      setPreview(null)
      setSelectedStudentIds([])
      setPreviewError(errorMessage(error))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleEnroll = async () => {
    const confirmedTeamName = teamDisplayName.trim()
    if (!selectedCourseId || !preview?.can_execute || selectedStudentIds.length === 0 || !confirmedTeamName) return
    setEnrollLoading(true)
    setPreviewError('')
    try {
      const response = await enrollMoodleCourseInTeams(
        selectedCourseId,
        selectedStudentIds,
        confirmedTeamName,
      )
      setResult(response)
      setConfirmOpen(false)
      applyPreview(await previewMoodleTeamsEnrollment(selectedCourseId, true, confirmedTeamName))
    } catch (error) {
      setPreviewError(errorMessage(error))
      setConfirmOpen(false)
    } finally {
      setEnrollLoading(false)
    }
  }

  const enrollment = result?.enrollment
  const enrollmentItems = useMemo(
    () => ((enrollment?.items || []) as MoodleTeamsEnrollmentItem[]),
    [enrollment],
  )
  const processedItems = useMemo(
    () => enrollmentItems.filter((item) => ['enrolled', 'error'].includes(String(item.status || ''))),
    [enrollmentItems],
  )
  const enrolledItems = useMemo(
    () => enrollmentItems.filter((item) => item.status === 'enrolled'),
    [enrollmentItems],
  )
  const failedItems = useMemo(
    () => enrollmentItems.filter((item) => [
      'error',
      'not_found',
      'invalid_email',
      'invalid_domain',
      'disabled_account',
      'identity_mismatch',
    ].includes(String(item.status || ''))),
    [enrollmentItems],
  )
  const existingItems = useMemo(
    () => enrollmentItems.filter((item) => item.status === 'already_in_team'),
    [enrollmentItems],
  )

  const toggleStudent = (participant: MoodleTeamsParticipant) => {
    if (!isSelectableStudent(participant)) return
    setSelectedStudentIds((current) => current.includes(participant.moodle_user_id)
      ? current.filter((studentId) => studentId !== participant.moodle_user_id)
      : [...current, participant.moodle_user_id])
  }

  const toggleVisibleStudents = () => {
    setSelectedStudentIds((current) => {
      const next = new Set(current)
      if (allVisibleStudentsSelected) {
        selectableVisibleStudentIds.forEach((studentId) => next.delete(studentId))
      } else {
        selectableVisibleStudentIds.forEach((studentId) => next.add(studentId))
      }
      return Array.from(next)
    })
  }

  return (
    <main className="moodle-teams-page">
      <header className="student-topbar">
        <div>
          <p className="eyebrow">Integraciones</p>
          <h1>Matrícula Moodle-Teams</h1>
          <p className="report-description">
            Cree un aula de clase en Teams con el nombre, los docentes y los estudiantes activos del curso Moodle.
            Si el aula ya fue creada, el proceso sincroniza sus participantes sin duplicarla.
          </p>
        </div>
        <div className="student-topbar__right">
          <div className="student-user-pill">
            <div>
              <strong>{displayName}</strong>
              <span>Integración académica</span>
            </div>
          </div>
        </div>
      </header>

      <section className="student-card student-card--wide moodle-teams-workflow">
        <div className="card-head">
          <div>
            <span className="moodle-teams-step">Paso 1</span>
            <h2>Seleccionar y validar el curso</h2>
          </div>
          <span>La vista previa no modifica Moodle ni Microsoft 365.</span>
        </div>

        <form className="moodle-teams-search" onSubmit={handleSearch}>
          <label>
            <span>Buscar curso Moodle</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Nombre, nombre corto, código o ID"
            />
          </label>
          <button type="submit" disabled={catalogLoading}>
            {catalogLoading ? 'Buscando...' : 'Buscar'}
          </button>
          <button type="button" disabled={catalogLoading} onClick={() => void loadCourses(query, true)}>
            Actualizar catálogo
          </button>
        </form>

        {catalogError ? <p className="teams-error" role="alert">{catalogError}</p> : null}

        <div className="moodle-teams-course-selector">
          <label>
            <span>Curso Moodle</span>
            <select
              value={selectedCourseId ?? ''}
              onChange={(event) => {
                const value = Number(event.target.value)
                setSelectedCourseId(Number.isFinite(value) && value > 0 ? value : null)
                setPreview(null)
                setSelectedStudentIds([])
                setTeamDisplayName('')
                setStudentQuery('')
                setResult(null)
                setPreviewError('')
              }}
              disabled={catalogLoading || courses.length === 0}
            >
              <option value="">Seleccione un curso Moodle</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>{courseLabel(course)}</option>
              ))}
            </select>
          </label>
          <div className="moodle-teams-course-count">
            <strong>{formatNumber(courses.length)}</strong>
            <span>curso(s) mostrado(s)</span>
          </div>
          <button
            type="button"
            className="moodle-teams-primary"
            disabled={!selectedCourseId || previewLoading}
            onClick={() => void handlePreview(true)}
          >
            {previewLoading ? 'Validando participantes...' : 'Validar curso y participantes'}
          </button>
        </div>
        {selectedCourse ? (
          <p className="moodle-teams-selection">
            <strong>Seleccionado:</strong> {courseLabel(selectedCourse)}
          </p>
        ) : null}
        {previewError ? <p className="teams-error" role="alert">{previewError}</p> : null}
      </section>

      {preview ? (
        <section className="moodle-teams-preview">
          <div className="moodle-teams-preview-head">
            <div>
              <span className="moodle-teams-step">Paso 2</span>
              <h2>Revisar la matrícula</h2>
              <p>El nombre se toma inicialmente del curso Moodle y puede ajustarse antes de confirmar.</p>
            </div>
            <div className={`moodle-teams-team-state ${preview.team.exists ? 'is-existing' : 'is-new'}`}>
              <span>{preview.team.exists ? 'Se sincronizará el aula existente' : 'Se creará una nueva aula de clase'}</span>
              <strong>{preview.team.display_name}</strong>
            </div>
          </div>

          <div className="moodle-teams-summary" aria-label="Resumen de participantes">
            <div><span>Usuarios Moodle</span><strong>{formatNumber(preview.summary.moodle_user_count)}</strong></div>
            <div><span>Docentes</span><strong>{formatNumber(preview.summary.moodle_teacher_count)}</strong></div>
            <div><span>Estudiantes</span><strong>{formatNumber(preview.summary.student_count)}</strong></div>
            <div><span>Listos</span><strong>{formatNumber(preview.summary.student_ready_count)}</strong></div>
            <div><span>Ya matriculados</span><strong>{formatNumber(preview.summary.student_existing_count)}</strong></div>
            <div><span>Por corregir</span><strong>{formatNumber(preview.summary.student_unresolved_count)}</strong></div>
          </div>

          {preview.blocking_reasons.length > 0 ? (
            <div className="moodle-teams-alert moodle-teams-alert--error" role="alert">
              <strong>No se puede ejecutar la matrícula.</strong>
              <ul>{preview.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </div>
          ) : null}
          {preview.warnings.length > 0 ? (
            <div className="moodle-teams-alert moodle-teams-alert--warning">
              <strong>Observaciones de validación</strong>
              <ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </div>
          ) : null}

          <ParticipantTable
            title="Propietarios del aula"
            participants={preview.owners}
            emptyMessage="No se identificaron propietarios para el aula."
          />
          <div className="moodle-teams-student-controls">
            <label>
              <span>Buscar estudiante del curso</span>
              <input
                type="search"
                value={studentQuery}
                onChange={(event) => setStudentQuery(event.target.value)}
                placeholder="Nombre, correo, usuario Moodle o ID"
              />
            </label>
            <div className="moodle-teams-selection-count" aria-live="polite">
              <strong>{formatNumber(selectedStudentIds.length)}</strong>
              <span>seleccionado(s)</span>
              <small>{formatNumber(filteredStudents.length)} visible(s)</small>
            </div>
            <button
              type="button"
              onClick={toggleVisibleStudents}
              disabled={selectableVisibleStudentIds.length === 0}
            >
              {allVisibleStudentsSelected ? 'Quitar visibles' : 'Seleccionar visibles'}
            </button>
            <button
              type="button"
              onClick={() => setSelectedStudentIds([])}
              disabled={selectedStudentIds.length === 0}
            >
              Limpiar selección
            </button>
          </div>
          <ParticipantTable
            title="Estudiantes del curso"
            participants={filteredStudents}
            emptyMessage={studentQuery
              ? 'No existen estudiantes que coincidan con la búsqueda.'
              : 'No se identificaron estudiantes activos en el curso.'}
            selectable
            selectedIds={selectedStudentSet}
            onToggle={toggleStudent}
          />

          {preview.ignored.length > 0 ? (
            <details className="moodle-teams-ignored">
              <summary>{formatNumber(preview.ignored.length)} usuario(s) ignorado(s)</summary>
              <ParticipantTable
                title="Usuarios ignorados"
                participants={preview.ignored}
                emptyMessage="No existen usuarios ignorados."
              />
            </details>
          ) : null}

          <div className="moodle-teams-final-actions">
            <button type="button" onClick={() => void handlePreview(true)} disabled={previewLoading || enrollLoading}>
              Volver a validar
            </button>
            <button
              type="button"
              className="moodle-teams-primary"
              disabled={!preview.can_execute || selectedStudentIds.length === 0 || previewLoading || enrollLoading}
              onClick={() => setConfirmOpen(true)}
            >
              {preview.team.exists ? 'Sincronizar aula de Teams' : 'Crear nueva aula de Teams'}
            </button>
          </div>
        </section>
      ) : null}

      {result ? (
        <div
          className="moodle-teams-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setResult(null)
          }}
        >
          <section
            className="moodle-teams-modal moodle-teams-result-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="moodle-teams-result-title"
            aria-describedby="moodle-teams-result-description"
          >
            <header className="moodle-teams-result-modal__head">
              <div>
                <p className="eyebrow">Proceso completado</p>
                <h2 id="moodle-teams-result-title">{result.message}</h2>
                <p id="moodle-teams-result-description">{result.team.display_name}</p>
              </div>
              <button type="button" onClick={() => setResult(null)}>Cerrar</button>
            </header>

            <div className="moodle-teams-result-summary" aria-label="Resumen de la matrícula">
              <div>
                <span>Procesados</span>
                <strong>{formatNumber(Number(enrollment?.processed_count || 0))}</strong>
              </div>
              <div>
                <span>Matriculados</span>
                <strong>{formatNumber(Number(enrollment?.enrolled_count || 0))}</strong>
              </div>
              <div className={Number(enrollment?.failed_count || 0) > 0 ? 'has-errors' : ''}>
                <span>Fallidos</span>
                <strong>{formatNumber(Number(enrollment?.failed_count || 0))}</strong>
              </div>
            </div>

            <div className="moodle-teams-result-details" aria-label="Opciones desplegables del resultado">
              <EnrollmentResultDetails
                title="Procesados"
                description="Registros enviados a Microsoft 365 durante esta operación."
                count={Number(enrollment?.processed_count || 0)}
                items={processedItems}
                emptyMessage="No existen registros procesados para mostrar."
              />
              <EnrollmentResultDetails
                title="Matriculados"
                description="Estudiantes incorporados correctamente al aula."
                count={Number(enrollment?.enrolled_count || 0)}
                items={enrolledItems}
                emptyMessage="No se matricularon estudiantes nuevos en esta operación."
              />
              <EnrollmentResultDetails
                title="Fallidos"
                description="Registros que requieren revisión o corrección."
                count={Number(enrollment?.failed_count || 0)}
                items={failedItems}
                emptyMessage="No se registraron fallos."
              />
              {existingItems.length > 0 ? (
                <EnrollmentResultDetails
                  title="Ya pertenecían al aula"
                  description="Cuentas verificadas que no necesitaron una nueva matrícula."
                  count={existingItems.length}
                  items={existingItems}
                  emptyMessage="No existen cuentas previamente matriculadas."
                />
              ) : null}
              {result.warnings.length > 0 ? (
                <details className="moodle-teams-result-detail">
                  <summary>
                    <span>
                      <strong>Advertencias</strong>
                      <small>Observaciones devueltas durante la integración.</small>
                    </span>
                    <strong>{formatNumber(result.warnings.length)}</strong>
                  </summary>
                  <ul className="moodle-teams-result-warnings">
                    {result.warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>

            {result.team.web_url ? (
              <a
                className="moodle-teams-result-link"
                href={result.team.web_url}
                target="_blank"
                rel="noreferrer"
              >
                Abrir aula de Teams
              </a>
            ) : null}
          </section>
        </div>
      ) : null}

      {confirmOpen && preview ? (
        <div className="moodle-teams-modal-backdrop" role="presentation">
          <section className="moodle-teams-modal" role="dialog" aria-modal="true" aria-labelledby="moodle-teams-confirm-title">
            <div>
              <p className="eyebrow">Confirmación</p>
              <h2 id="moodle-teams-confirm-title">Configurar el aula de Teams</h2>
              <p>
                Revise o cambie el nombre. Antes de matricular, el sistema verificará nuevamente si ya existe un aula con
                ese nombre y creará una clase privada únicamente cuando sea necesario.
              </p>
            </div>
            <label className="moodle-teams-name-field">
              <span>Nombre del aula de Teams</span>
              <input
                type="text"
                value={teamDisplayName}
                maxLength={256}
                autoFocus
                required
                aria-invalid={!teamDisplayName.trim()}
                onChange={(event) => setTeamDisplayName(event.target.value)}
              />
              <small>{teamDisplayName.trim().length} de 256 caracteres</small>
            </label>
            <dl>
              <div><dt>Acción</dt><dd>Crear o sincronizar por nombre</dd></div>
              <div><dt>Docentes propietarios</dt><dd>{formatNumber(preview.summary.moodle_teacher_count)}</dd></div>
              <div><dt>Administrador fijo</dt><dd>{preview.fixed_administrator}</dd></div>
              <div><dt>Estudiantes seleccionados</dt><dd>{formatNumber(selectedStudentIds.length)}</dd></div>
            </dl>
            <div className="moodle-teams-modal-actions">
              <button type="button" onClick={() => setConfirmOpen(false)} disabled={enrollLoading}>Cancelar</button>
              <button
                type="button"
                className="moodle-teams-primary"
                onClick={() => void handleEnroll()}
                disabled={enrollLoading || selectedStudentIds.length === 0 || !teamDisplayName.trim()}
              >
                {enrollLoading ? 'Verificando y matriculando...' : 'Confirmar aula y matrícula'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  )
}
