import { useEffect, useMemo, useState } from 'react'

import {
  downloadTeacherEvaluationGradesPdf,
  fetchTeacherEvaluationAdminPending,
  fetchTeacherEvaluationAdminPeriods,
  fetchTeacherEvaluationAutoStudents,
  fetchTeacherEvaluationGradedSubjects,
  fetchTeacherEvaluationGradedTeachers,
  fetchTeacherEvaluationProgressDetail,
  fetchTeacherEvaluationProgressParticipants,
  fetchTeacherEvaluationStudentGrades,
  fetchTeacherEvaluationStudentProgress,
} from '../../lib/api'
import type {
  TeacherEvaluationAdminPendingResponse,
  TeacherEvaluationAdminPeriod,
  TeacherEvaluationAutoStudentListResponse,
  TeacherEvaluationFlow,
  TeacherEvaluationGradedSubject,
  TeacherEvaluationGradedTeacher,
  TeacherEvaluationProgressDetailResponse,
  TeacherEvaluationProgressParticipantsResponse,
  TeacherEvaluationStudentGradesResponse,
  TeacherEvaluationStudentProgressResponse,
  TeacherEvaluationTeacherProgressItem,
} from '../../types/app'

type TeacherEvaluationAdminViewProps = {
  displayName?: string
  mode?: 'progress' | 'reports' | 'all'
}

const FLOW_OPTIONS: Array<{ value: TeacherEvaluationFlow; label: string }> = [
  { value: 'student', label: 'Estudiante a docente' },
  { value: 'auto_estudiante', label: 'Autoevaluación estudiantil' },
  { value: 'auto_docente', label: 'Autoevaluación docente' },
  { value: 'par_docente', label: 'Evaluación par docente' },
  { value: 'academico_docente', label: 'Administrativa docente' },
]

const REPORT_FLOW_OPTIONS: Array<{ value: Exclude<TeacherEvaluationFlow, 'auto_estudiante'> | 'all'; label: string }> = [
  { value: 'all', label: 'Resultado final 360' },
  { value: 'student', label: 'Estudiante a docente' },
  { value: 'auto_docente', label: 'Autoevaluación docente' },
  { value: 'par_docente', label: 'Evaluación par docente' },
  { value: 'academico_docente', label: 'Administrativa docente' },
]

export function TeacherEvaluationAdminView({ displayName = '', mode = 'all' }: TeacherEvaluationAdminViewProps) {
  void displayName
  const showProgress = mode === 'progress' || mode === 'all'
  const showReports = mode === 'reports' || mode === 'all'

  const [periods, setPeriods] = useState<TeacherEvaluationAdminPeriod[]>([])
  const [gradedTeachers, setGradedTeachers] = useState<TeacherEvaluationGradedTeacher[]>([])
  const [periodo, setPeriodo] = useState('')
  const [selectedTeacher, setSelectedTeacher] = useState('')
  const [gradedSubjects, setGradedSubjects] = useState<TeacherEvaluationGradedSubject[]>([])
  const [selectedSubjectKey, setSelectedSubjectKey] = useState('')
  const [flow, setFlow] = useState<TeacherEvaluationFlow>('student')
  const [reportFlow, setReportFlow] = useState<Exclude<TeacherEvaluationFlow, 'auto_estudiante'> | 'all'>('all')
  const [data, setData] = useState<TeacherEvaluationAdminPendingResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<TeacherEvaluationProgressDetailResponse | null>(null)
  const [participants, setParticipants] = useState<TeacherEvaluationProgressParticipantsResponse | null>(null)
  const [studentGrades, setStudentGrades] = useState<TeacherEvaluationStudentGradesResponse | null>(null)
  const [studentProgress, setStudentProgress] = useState<TeacherEvaluationStudentProgressResponse | null>(null)
  const [autoStudentList, setAutoStudentList] = useState<TeacherEvaluationAutoStudentListResponse | null>(null)
  const [lastProgressUpdate, setLastProgressUpdate] = useState<Date | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadPeriods() {
      setCatalogLoading(true)
      setError('')
      try {
        const response = await fetchTeacherEvaluationAdminPeriods()
        if (cancelled) return
        setPeriods(response.items || [])
        const first = response.items?.[0]?.codigo_periodo || ''
        setPeriodo((current) => current || first)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'No se pudieron cargar los periodos.')
      } finally {
        if (!cancelled) setCatalogLoading(false)
      }
    }
    void loadPeriods()
    return () => {
      cancelled = true
    }
  }, [])

  async function loadPending(selectedPeriod = periodo, selectedFlow = flow, silent = false) {
    if (!selectedPeriod) {
      setError('Selecciona un periodo.')
      return
    }
    if (!silent) {
      setLoading(true)
      setError('')
    }
    try {
      const [response, studentResponse] = await Promise.all([
        fetchTeacherEvaluationAdminPending(selectedPeriod, selectedFlow),
        selectedFlow === 'auto_estudiante'
          ? fetchTeacherEvaluationStudentProgress(selectedPeriod, 2000)
          : Promise.resolve(null),
      ])
      setData(response)
      setStudentProgress(studentResponse)
      setLastProgressUpdate(new Date())
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : 'No se pudo consultar pendientes.')
        setData(null)
        setStudentProgress(null)
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }

  async function loadGradedTeachers(selectedPeriod = periodo, selectedFlow = reportFlow) {
    if (!selectedPeriod) {
      setGradedTeachers([])
      setSelectedTeacher('')
      return
    }
    try {
      const response = await fetchTeacherEvaluationGradedTeachers(selectedPeriod, selectedFlow)
      setGradedTeachers(response.items || [])
      setSelectedTeacher((current) =>
        current && (response.items || []).some((item) => item.codigo_doc === current) ? current : '',
      )
    } catch {
      setGradedTeachers([])
      setSelectedTeacher('')
      setGradedSubjects([])
      setSelectedSubjectKey('')
    }
  }

  async function loadGradedSubjects(
    selectedPeriod = periodo,
    teacherCode = selectedTeacher,
    selectedFlow = reportFlow,
  ) {
    if (!selectedPeriod || !teacherCode) {
      setGradedSubjects([])
      setSelectedSubjectKey('')
      return
    }
    try {
      const response = await fetchTeacherEvaluationGradedSubjects(selectedPeriod, teacherCode, selectedFlow)
      const subjects = response.items || []
      setGradedSubjects(subjects)
      setSelectedSubjectKey((current) =>
        current && subjects.some((item) => reportSubjectKey(item) === current)
          ? current
          : subjects[0]
            ? reportSubjectKey(subjects[0])
            : '',
      )
    } catch {
      setGradedSubjects([])
      setSelectedSubjectKey('')
    }
  }

  async function handlePdf(
    mode: 'all' | 'teacher',
    action: 'download' | 'preview',
    documentType: 'certificado' | 'resumen' | 'detalle' = 'certificado',
    subjectOverride?: TeacherEvaluationGradedSubject,
  ) {
    if (!periodo) {
      setError('Selecciona un periodo.')
      return
    }
    if (mode === 'teacher' && !selectedTeacher) {
      setError('Selecciona un docente.')
      return
    }
    const selectedSubject = subjectOverride || gradedSubjects.find((item) => reportSubjectKey(item) === selectedSubjectKey)
    if (mode === 'teacher' && !selectedSubject) {
      setError('Selecciona una materia del docente.')
      return
    }
    setPdfLoading(true)
    setError('')
    try {
      const blob = await downloadTeacherEvaluationGradesPdf(
        periodo,
        mode === 'teacher' ? selectedTeacher : '',
        reportFlow,
        documentType,
        mode === 'teacher' && selectedSubject
          ? {
            codigo_materia: selectedSubject.codigo_materia,
            carrera: selectedSubject.carrera,
            paralelo: selectedSubject.paralelo,
          }
          : undefined,
      )
      const url = URL.createObjectURL(blob)
      if (action === 'preview') {
        const opened = window.open(url, '_blank', 'noopener,noreferrer')
        if (!opened) {
          setError('No se pudo abrir la vista previa. Revisa si el navegador bloqueó ventanas emergentes.')
          URL.revokeObjectURL(url)
          return
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60000)
        return
      }
      const link = document.createElement('a')
      link.href = url
      link.download = mode === 'teacher'
        ? `${documentType}_evaluacion_${reportFlow}_${periodo}_${selectedTeacher}_${selectedSubject?.codigo_materia || 'materia'}.pdf`
        : `${documentType}_evaluacion_${reportFlow}_${periodo}_todos.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo descargar el PDF.')
    } finally {
      setPdfLoading(false)
    }
  }

  async function openProgressDetail(item: TeacherEvaluationTeacherProgressItem) {
    setDetailLoading(true)
    setError('')
    try {
      const response = await fetchTeacherEvaluationProgressDetail(
        item.codigo_periodo || periodo,
        item.codigo_doc,
        item.codigo_materia,
        item.flow,
      )
      setDetail(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar el detalle del grafico.')
    } finally {
      setDetailLoading(false)
    }
  }

  async function openStudentGrades(student: { codigo_estud: number }) {
    setDetailLoading(true)
    setError('')
    try {
      const response = await fetchTeacherEvaluationStudentGrades(periodo, student.codigo_estud)
      setStudentGrades(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar notas del estudiante.')
    } finally {
      setDetailLoading(false)
    }
  }

  async function openProgressParticipants(item: TeacherEvaluationTeacherProgressItem, estado: 'completadas' | 'pendientes') {
    setDetailLoading(true)
    setError('')
    try {
      const response = await fetchTeacherEvaluationProgressParticipants(
        item.codigo_periodo || periodo,
        item.codigo_doc,
        item.codigo_materia,
        item.flow,
        estado,
        1500,
      )
      setParticipants(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar el listado de evaluadores.')
    } finally {
      setDetailLoading(false)
    }
  }

  async function openAutoStudentList(estado: 'realizadas' | 'pendientes') {
    if (!periodo) {
      setError('Selecciona un periodo.')
      return
    }
    setDetailLoading(true)
    setError('')
    try {
      const response = await fetchTeacherEvaluationAutoStudents(periodo, estado, 2000)
      setAutoStudentList(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar estudiantes de autoevaluacion.')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    if (periodo) {
      if (showProgress) {
        void loadPending(periodo, flow)
      }
      if (showReports) {
        void loadGradedTeachers(periodo, reportFlow)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, flow, reportFlow, showProgress, showReports])

  useEffect(() => {
    if (!showProgress || !periodo) return undefined
    const interval = window.setInterval(() => {
      if (document.hidden) return
      void loadPending(periodo, flow, true)
    }, 10000)
    return () => window.clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showProgress, periodo, flow])

  useEffect(() => {
    if (showReports) {
      void loadGradedSubjects(periodo, selectedTeacher, reportFlow)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, selectedTeacher, reportFlow, showReports])

  const totals = useMemo(() => {
    const summary = data?.summary || []
    return summary.reduce(
      (acc, item) => ({
        expected: acc.expected + item.expected,
        completed: acc.completed + item.completed,
        pending: acc.pending + item.pending,
      }),
      { expected: 0, completed: 0, pending: 0 },
    )
  }, [data])

  const isStudentProgressFlow = showProgress && flow === 'auto_estudiante'
  const studentProgressTotals = studentProgress?.summary.autoevaluacion_estudiante
  const displayTotals = isStudentProgressFlow && studentProgressTotals
    ? {
      expected: studentProgressTotals.esperadas || 0,
      completed: studentProgressTotals.completadas || 0,
      pending: studentProgressTotals.pendientes || 0,
    }
    : totals

  const chartItems = detail?.items || []
  const chartSize = 560
  const chartCenter = chartSize / 2
  const chartRadius = 190
  const radarPoint = (value: number, index: number, total: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / Math.max(total, 1)
    const radius = (Math.max(0, Math.min(100, value)) / 100) * chartRadius
    return {
      x: chartCenter + Math.cos(angle) * radius,
      y: chartCenter + Math.sin(angle) * radius,
    }
  }
  const radarAxisPoint = (index: number, total: number, radius = chartRadius) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / Math.max(total, 1)
    return {
      x: chartCenter + Math.cos(angle) * radius,
      y: chartCenter + Math.sin(angle) * radius,
    }
  }
  const radarPolygon = (field: 'promedio' | 'promedio_ajustado') =>
    chartItems
      .map((item, index) => {
        const point = radarPoint(Number(item[field] ?? item.promedio ?? 0), index, chartItems.length)
        return `${point.x},${point.y}`
      })
      .join(' ')

  function reportSubjectKey(subject: TeacherEvaluationGradedSubject) {
    return [
      subject.codigo_materia || '',
      subject.carrera || '',
      subject.paralelo || '',
    ].join('|')
  }

  return (
    <main className="teacher-evaluation teacher-evaluation--compact">
      <section className="teacher-evaluation__hero teacher-evaluation__hero--compact">
        <div>
          <p className="teacher-evaluation__eyebrow">Administración</p>
          <h1>{showReports && !showProgress ? 'Documentos de evaluación' : 'Avance y ponderación'}</h1>
          <p>
            {showReports && !showProgress
              ? 'Generación por docente o masiva en base a la calificación del periodo. Quito - Ecuador. Conserva evaluaciones históricas registradas.'
              : 'Control por periodo y código único de materia; las carreras relacionadas se consolidan en una sola materia. Conserva evaluaciones históricas registradas.'}
          </p>
        </div>
      </section>

      <section className={`teacher-evaluation__panel teacher-evaluation__search-panel teacher-evaluation__admin-controls${showProgress ? ' teacher-evaluation__admin-controls--attached' : ''}`}>
        <div className="teacher-evaluation__lookup-row">
          <select value={periodo} onChange={(event) => setPeriodo(event.target.value)} disabled={catalogLoading || loading}>
            <option value="">Periodo</option>
            {periods.map((period) => (
              <option key={period.codigo_periodo} value={period.codigo_periodo}>
                {period.detalle_periodo || period.codigo_periodo}
              </option>
            ))}
          </select>
          {showProgress ? (
            <>
              <select value={flow} onChange={(event) => setFlow(event.target.value as TeacherEvaluationFlow)} disabled={loading}>
                {FLOW_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button type="button" className="teacher-evaluation__primary" onClick={() => void loadPending()} disabled={loading}>
                {loading ? 'Consultando...' : 'Consultar'}
              </button>
            </>
          ) : null}
          {showReports ? (
            <>
              <select
                value={reportFlow}
                onChange={(event) => setReportFlow(event.target.value as Exclude<TeacherEvaluationFlow, 'auto_estudiante'> | 'all')}
                disabled={pdfLoading}
              >
                {REPORT_FLOW_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select value={selectedTeacher} onChange={(event) => setSelectedTeacher(event.target.value)} disabled={pdfLoading || gradedTeachers.length === 0}>
                <option value="">Docente calificado</option>
                {gradedTeachers.map((teacher) => (
                  <option key={teacher.codigo_doc} value={teacher.codigo_doc}>
                    {teacher.docente || `Docente ${teacher.codigo_doc}`}
                  </option>
                ))}
              </select>
              <select value={selectedSubjectKey} onChange={(event) => setSelectedSubjectKey(event.target.value)} disabled={pdfLoading || gradedSubjects.length === 0}>
                <option value="">Materia y carrera</option>
                {gradedSubjects.map((subject) => (
                  <option key={reportSubjectKey(subject)} value={reportSubjectKey(subject)}>
                    {subject.materia || subject.codigo_materia} · {subject.carrera || 'Sin carrera'} · {subject.paralelo || '-'}
                  </option>
                ))}
              </select>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => void handlePdf('teacher', 'preview')} disabled={pdfLoading || !periodo || !selectedTeacher || !selectedSubjectKey}>
                {pdfLoading ? 'Generando...' : 'Vista previa'}
              </button>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => void handlePdf('teacher', 'download')} disabled={pdfLoading || !periodo || !selectedTeacher || !selectedSubjectKey}>
                {pdfLoading ? 'Generando...' : 'Descargar individual'}
              </button>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => void handlePdf('all', 'download')} disabled={pdfLoading || !periodo}>
                {pdfLoading ? 'Generando...' : 'Descarga masiva'}
              </button>
            </>
          ) : null}
        </div>
        {error ? <div className="teacher-evaluation__message teacher-evaluation__message--error">{error}</div> : null}
      </section>

      {showProgress && data ? (
        <section className="teacher-evaluation__panel teacher-evaluation__panel--compact">
          <div className="teacher-evaluation__progress-overview">
            <div className="teacher-evaluation__summary-actions teacher-evaluation__progress-summary">
              <span className="teacher-evaluation__summary-pill">
                {isStudentProgressFlow
                  ? `Estudiantes: ${studentProgress?.summary.estudiantes || studentProgress?.items.length || 0}`
                  : `Docente/materia: ${data.teacher_progress?.length || 0}`}
              </span>
              <span className="teacher-evaluation__summary-pill">Periodo: {data.periodo_detalle || data.periodo}</span>
              <span className="teacher-evaluation__summary-pill">
                Avance total: {displayTotals.expected ? Number((displayTotals.completed / displayTotals.expected) * 100).toFixed(2) : '0.00'}%
              </span>
              <span className="teacher-evaluation__summary-pill">Esperadas: {displayTotals.expected}</span>
              <span className="teacher-evaluation__summary-pill">
                Completadas:{' '}
                {isStudentProgressFlow ? (
                  <button
                    type="button"
                    className="teacher-evaluation__pill-button"
                    onClick={() => void openAutoStudentList('realizadas')}
                    disabled={detailLoading}
                  >
                    {displayTotals.completed}
                  </button>
                ) : displayTotals.completed}
              </span>
              <span className="teacher-evaluation__summary-pill">
                Pendientes:{' '}
                {isStudentProgressFlow ? (
                  <button
                    type="button"
                    className="teacher-evaluation__pill-button teacher-evaluation__pill-button--danger"
                    onClick={() => void openAutoStudentList('pendientes')}
                    disabled={detailLoading}
                  >
                    {displayTotals.pending}
                  </button>
                ) : displayTotals.pending}
              </span>
              <span className="teacher-evaluation__summary-pill">
                Actualizado: {lastProgressUpdate ? lastProgressUpdate.toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'}
              </span>
              <button
                type="button"
                className="teacher-evaluation__summary-pill teacher-evaluation__summary-pill--button"
                onClick={() => void loadPending()}
                disabled={loading}
              >
                Actualizar ahora
              </button>
            </div>
            <p className="teacher-evaluation__live-note">
              Actualización automática cada 10 segundos mientras esta pantalla permanezca abierta.
            </p>
            <div className="teacher-evaluation__flow-cards">
              {(data.summary || []).map((item) => (
                <article className="teacher-evaluation__flow-card" key={`flow-card-${item.flow}`}>
                  <div className="teacher-evaluation__flow-card-head">
                    <strong>{item.flow_label}</strong>
                    <span>{Number(item.progress_percent || 0).toFixed(2)}%</span>
                  </div>
                  <div className="teacher-evaluation__flow-card-grid">
                    <span>Ponderación <b>{Number(item.ponderacion || 0).toFixed(2)}%</b></span>
                    <span>Completadas <b>{item.completed}</b></span>
                    <span>Pendientes <b>{item.pending}</b></span>
                  </div>
                </article>
              ))}
            </div>
          </div>
          {isStudentProgressFlow ? (
            <>
              <div className="matricula-table-wrap teacher-evaluation__progress-table-wrap">
                <table className="matricula-table teacher-evaluation__student-progress-table">
                  <thead>
                    <tr>
                      <th>Estudiante</th>
                      <th>Cédula</th>
                      <th>Carrera</th>
                      <th>Materias</th>
                      <th>Avance</th>
                      <th>Ponderación</th>
                      <th>Esperadas</th>
                      <th>Completadas</th>
                      <th>Pendientes</th>
                      <th>Estado</th>
                      <th>Notas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(studentProgress?.items || []).map((item) => {
                      const metric = item.autoevaluacion_estudiante
                      const expectedCount = metric?.esperadas || 0
                      const completedCount = metric?.completadas || 0
                      const status = expectedCount > 0 && completedCount >= expectedCount
                        ? 'Realizada'
                        : completedCount > 0
                          ? 'En progreso'
                          : 'Pendiente'
                      return (
                        <tr key={`student-progress-${item.codigo_estud}`}>
                          <td>{item.estudiante || `Estudiante ${item.codigo_estud}`}</td>
                          <td>{item.cedula || '-'}</td>
                          <td>{item.carreras || '-'}</td>
                          <td>{item.materias_autoevaluables ?? item.materias_evaluables}</td>
                          <td>{Number(metric?.avance_percent || 0).toFixed(2)}%</td>
                          <td>{Number(metric?.ponderacion || 0).toFixed(2)}%</td>
                          <td>{metric?.esperadas || 0}</td>
                          <td>
                            <button
                              type="button"
                              className="teacher-evaluation__count-button"
                              onClick={() => void openAutoStudentList('realizadas')}
                              disabled={detailLoading || (metric?.completadas || 0) <= 0}
                            >
                              {metric?.completadas || 0}
                            </button>
                          </td>
                          <td>
                            <button
                              type="button"
                              className="teacher-evaluation__count-button"
                              onClick={() => void openAutoStudentList('pendientes')}
                              disabled={detailLoading || (metric?.pendientes || 0) <= 0}
                            >
                              {metric?.pendientes || 0}
                            </button>
                          </td>
                          <td>
                            <span className={`teacher-evaluation__status teacher-evaluation__status--${status === 'Realizada' ? 'done' : status === 'En progreso' ? 'progress' : 'pending'}`}>
                              {status}
                            </span>
                          </td>
                          <td>
                            <button
                              type="button"
                              className="teacher-evaluation__secondary teacher-evaluation__table-action"
                              onClick={() => void openStudentGrades(item)}
                              disabled={detailLoading}
                            >
                              Ver notas
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {(studentProgress?.items || []).length === 0 ? (
                <div className="teacher-evaluation__empty">No hay estudiantes con materias calificadas para el periodo seleccionado.</div>
              ) : null}
            </>
          ) : (
            <>
              <div className="matricula-table-wrap teacher-evaluation__progress-table-wrap">
                <table className="matricula-table teacher-evaluation__progress-table">
                  <thead>
                    <tr>
                      <th>Docente</th>
                      <th>Materia única</th>
                      <th>Paralelo</th>
                      <th>Evaluación</th>
                      <th>Avance</th>
                      <th>Ponderación</th>
                      <th>Cumplimiento</th>
                      <th>Esperadas</th>
                      <th>Completadas</th>
                      <th>Pendientes</th>
                      <th>Gráfico</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.teacher_progress || []).map((item) => (
                      <tr key={`${item.flow}-${item.codigo_doc}-${item.codigo_periodo}-${item.codigo_materia}-${item.paralelo || ''}`}>
                        <td>{item.docente || `Docente ${item.codigo_doc}`}</td>
                        <td>{item.materia || item.codigo_materia}</td>
                        <td>{item.paralelo || '-'}</td>
                        <td>{item.flow_label}</td>
                        <td>{Number(item.progress_percent || 0).toFixed(2)}%</td>
                        <td>{Number(item.ponderacion || 0).toFixed(2)}%</td>
                        <td>{Number(item.ponderacion_aplicada || 0).toFixed(2)}%</td>
                        <td>{item.expected}</td>
                        <td>
                          <button
                            type="button"
                            className="teacher-evaluation__count-button"
                            onClick={() => void openProgressParticipants(item, 'completadas')}
                            disabled={detailLoading || item.completed <= 0}
                          >
                            {item.completed}
                          </button>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="teacher-evaluation__count-button"
                            onClick={() => void openProgressParticipants(item, 'pendientes')}
                            disabled={detailLoading || item.pending <= 0}
                          >
                            {item.pending}
                          </button>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="teacher-evaluation__secondary teacher-evaluation__table-action"
                            onClick={() => void openProgressDetail(item)}
                            disabled={detailLoading}
                          >
                            Ver gráfico
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(data.teacher_progress || []).length === 0 ? (
                <div className="teacher-evaluation__empty">No hay docentes con materias evaluables para el periodo seleccionado.</div>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {showReports ? (
        <section className="teacher-evaluation__panel teacher-evaluation__panel--compact">
          <div className="teacher-evaluation__summary-actions">
            <span className="teacher-evaluation__summary-pill">Docentes calificados: {gradedTeachers.length}</span>
            <span className="teacher-evaluation__summary-pill">Periodo: {periodo || '-'}</span>
            <span className="teacher-evaluation__summary-pill">
              Evaluación: {REPORT_FLOW_OPTIONS.find((option) => option.value === reportFlow)?.label || 'Resultado final 360'}
            </span>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Docente</th>
                  <th>Cédula</th>
                  <th>Evaluación</th>
                  <th>Registros</th>
                  <th>Evaluaciones</th>
                  <th>Respuestas</th>
                  <th>Promedio final</th>
                  <th>Selección</th>
                </tr>
              </thead>
              <tbody>
                {gradedTeachers.map((teacher) => (
                  <tr key={teacher.codigo_doc}>
                    <td>{teacher.docente || `Docente ${teacher.codigo_doc}`}</td>
                    <td>{teacher.cedula_doc || '-'}</td>
                    <td>{teacher.flow_label || REPORT_FLOW_OPTIONS.find((option) => option.value === reportFlow)?.label || '-'}</td>
                    <td>{teacher.total_registros}</td>
                    <td>{teacher.total_evaluaciones ?? '-'}</td>
                    <td>{teacher.total_respuestas ?? '-'}</td>
                    <td>{Number(teacher.promedio_final || 0).toFixed(2)}</td>
                    <td>
                      <button
                        type="button"
                        className="teacher-evaluation__secondary"
                        onClick={() => setSelectedTeacher(teacher.codigo_doc)}
                      >
                        Seleccionar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {gradedTeachers.length === 0 ? <div className="teacher-evaluation__empty">No hay docentes calificados para el periodo seleccionado.</div> : null}
          {selectedTeacher ? (
            <div className="teacher-evaluation__report-subjects">
              <div className="teacher-evaluation__summary-actions">
                <span className="teacher-evaluation__summary-pill">Materias del docente: {gradedSubjects.length}</span>
                <span className="teacher-evaluation__summary-pill">
                  Docente: {gradedTeachers.find((teacher) => teacher.codigo_doc === selectedTeacher)?.docente || selectedTeacher}
                </span>
              </div>
              <div className="matricula-table-wrap">
                <table className="matricula-table teacher-evaluation__report-subjects-table">
                  <thead>
                    <tr>
                      <th>Materia</th>
                      <th>Carrera</th>
                      <th>Paralelo</th>
                      <th>Base estudiantes</th>
                      <th>Cobertura</th>
                      <th>Puntaje</th>
                      <th>Documento</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gradedSubjects.map((subject) => (
                      <tr key={reportSubjectKey(subject)}>
                        <td>{subject.materia || subject.codigo_materia}</td>
                        <td>{subject.carrera || '-'}</td>
                        <td>{subject.paralelo || '-'}</td>
                        <td>{subject.estudiantes_completaron}/{subject.estudiantes_esperados}</td>
                        <td>{Number(subject.cobertura_estudiantes || 0).toFixed(2)}%</td>
                        <td>{Number(subject.puntaje_final || 0).toFixed(2)}</td>
                        <td>
                          <div className="teacher-evaluation__inline-actions">
                            <button
                              type="button"
                              className="teacher-evaluation__secondary teacher-evaluation__table-action"
                              onClick={() => setSelectedSubjectKey(reportSubjectKey(subject))}
                              disabled={pdfLoading}
                            >
                              Seleccionar
                            </button>
                            <button
                              type="button"
                              className="teacher-evaluation__secondary teacher-evaluation__table-action"
                              onClick={() => void handlePdf('teacher', 'preview', 'certificado', subject)}
                              disabled={pdfLoading}
                            >
                              Vista previa
                            </button>
                            <button
                              type="button"
                              className="teacher-evaluation__secondary teacher-evaluation__table-action"
                              onClick={() => void handlePdf('teacher', 'download', 'certificado', subject)}
                              disabled={pdfLoading}
                            >
                              Descargar
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {gradedSubjects.length === 0 ? <div className="teacher-evaluation__empty">No hay materias calificadas para el docente seleccionado.</div> : null}
            </div>
          ) : null}
        </section>
      ) : null}

      {detail ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section className="teacher-evaluation__modal teacher-evaluation__modal--chart" role="dialog" aria-modal="true">
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Detalle por categoría</p>
                <h2>{detail.docente || `Docente ${detail.codigo_docente}`}</h2>
                <p>{detail.materia || detail.codigo_materia} · {detail.periodo_detalle || detail.periodo}</p>
              </div>
              <button type="button" className="teacher-evaluation__ghost" onClick={() => setDetail(null)}>
                Cerrar
              </button>
            </header>
            <div className="teacher-evaluation__modal-body">
              {chartItems.length > 0 ? (
                <>
                  <div className="teacher-evaluation__chart-wrap">
                    <svg className="teacher-evaluation__radar-chart" viewBox={`0 0 ${chartSize} ${chartSize}`} role="img" aria-label="Grafico radar por categoria">
                      {[20, 40, 60, 80, 100].map((tick) => (
                        <polygon
                          key={tick}
                          className="teacher-evaluation__radar-ring"
                          points={chartItems.map((_, index) => {
                            const point = radarAxisPoint(index, chartItems.length, (tick / 100) * chartRadius)
                            return `${point.x},${point.y}`
                          }).join(' ')}
                        />
                      ))}
                      {chartItems.map((item, index) => {
                        const axis = radarAxisPoint(index, chartItems.length)
                        const label = radarAxisPoint(index, chartItems.length, chartRadius + 34)
                        return (
                          <g key={`axis-${item.categoria}-${index}`}>
                            <line className="teacher-evaluation__radar-axis" x1={chartCenter} y1={chartCenter} x2={axis.x} y2={axis.y} />
                            <text className="teacher-evaluation__radar-label" x={label.x} y={label.y}>{item.categoria}</text>
                          </g>
                        )
                      })}
                      <polygon className="teacher-evaluation__radar-series teacher-evaluation__radar-series--raw" points={radarPolygon('promedio')} />
                      <polygon className="teacher-evaluation__radar-series teacher-evaluation__radar-series--weighted" points={radarPolygon('promedio_ajustado')} />
                      {chartItems.map((item, index) => {
                        const point = radarPoint(Number(item.promedio_ajustado ?? item.promedio ?? 0), index, chartItems.length)
                        return (
                          <g key={`point-${item.categoria}-${index}`} className="teacher-evaluation__radar-point">
                            <circle cx={point.x} cy={point.y} r="5" />
                            <text x={point.x} y={point.y - 10}>{Number(item.promedio_ajustado ?? item.promedio ?? 0).toFixed(1)}</text>
                          </g>
                        )
                      })}
                      <text className="teacher-evaluation__radar-tick" x={chartCenter + 4} y={chartCenter - chartRadius + 4}>100</text>
                      <text className="teacher-evaluation__radar-tick" x={chartCenter + 4} y={chartCenter - (chartRadius * 0.5)}>50</text>
                    </svg>
                    <div className="teacher-evaluation__chart-legend">
                      <span><i className="teacher-evaluation__legend-color teacher-evaluation__legend-color--raw" /> Promedio obtenido</span>
                      <span><i className="teacher-evaluation__legend-color teacher-evaluation__legend-color--weighted" /> Promedio ajustado por cobertura</span>
                    </div>
                  </div>
                  <div className="matricula-table-wrap">
                    <table className="matricula-table teacher-evaluation__chart-table">
                      <thead>
                        <tr>
                          <th>Categoría</th>
                          <th>Evaluación</th>
                          <th>Promedio</th>
                          <th>Pond. tipo</th>
                          <th>Ponderación</th>
                          <th>Cobertura</th>
                          <th>Aporte</th>
                          <th>Respuestas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {chartItems.map((item, index) => (
                          <tr key={`${item.flow}-${item.categoria}-${index}`}>
                            <td>{item.categoria}</td>
                            <td>{item.flow_label}</td>
                            <td>{Number(item.promedio || 0).toFixed(2)}</td>
                            <td>{Number(item.ponderacion_tipo || 0).toFixed(2)}%</td>
                            <td>{Number(item.ponderacion || 0).toFixed(2)}%</td>
                            <td>{Number(item.cobertura ?? 100).toFixed(2)}% ({item.evaluaciones}/{item.esperadas || item.evaluaciones})</td>
                            <td>{Number(item.aporte || 0).toFixed(2)}%</td>
                            <td>{item.respuestas}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="teacher-evaluation__empty">No existen resultados por categoría para esta materia.</div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {participants ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section className="teacher-evaluation__modal teacher-evaluation__modal--chart" role="dialog" aria-modal="true">
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Listado de evaluación</p>
                <h2>{participants.estado === 'completadas' ? 'Evaluaciones completadas' : 'Evaluaciones pendientes'}</h2>
                <p>{participants.docente} · {participants.materia} · {participants.total} registro(s)</p>
              </div>
              <button type="button" className="teacher-evaluation__ghost" onClick={() => setParticipants(null)}>
                Cerrar
              </button>
            </header>
            <div className="teacher-evaluation__modal-body">
              <div className="matricula-table-wrap">
                <table className="matricula-table teacher-evaluation__chart-table">
                  <thead>
                    <tr>
                      <th>Evaluador</th>
                      <th>Cédula</th>
                      <th>Evaluación</th>
                      <th>Estado</th>
                      <th>Calificaciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {participants.items.map((item, index) => (
                      <tr key={`${item.flow}-${item.evaluator_code}-${index}`}>
                        <td>{item.evaluator_name}</td>
                        <td>{item.evaluator_cedula || '-'}</td>
                        <td>{item.flow_label}</td>
                        <td>{item.estado}</td>
                        <td>
                          {item.can_view_grades ? (
                            <button
                              type="button"
                              className="teacher-evaluation__secondary teacher-evaluation__table-action"
                              onClick={() => void openStudentGrades({ codigo_estud: item.evaluator_code })}
                            >
                              Ver notas
                            </button>
                          ) : (
                            '-'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {participants.items.length === 0 ? <div className="teacher-evaluation__empty">No hay registros para mostrar.</div> : null}
            </div>
          </section>
        </div>
      ) : null}

      {autoStudentList ? (
        <div className="teacher-evaluation__modal-backdrop" role="presentation">
          <section className="teacher-evaluation__modal teacher-evaluation__modal--chart" role="dialog" aria-modal="true">
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Autoevaluación estudiantil</p>
                <h2>{autoStudentList.estado === 'realizadas' ? 'Estudiantes que completaron' : 'Estudiantes pendientes'}</h2>
                <p>Periodo {autoStudentList.periodo} · {autoStudentList.total} registro(s)</p>
              </div>
              <button type="button" className="teacher-evaluation__ghost" onClick={() => setAutoStudentList(null)}>
                Cerrar
              </button>
            </header>
            <div className="teacher-evaluation__modal-body">
              <div className="matricula-table-wrap">
                <table className="matricula-table teacher-evaluation__chart-table">
                  <thead>
                    <tr>
                      <th>Estudiante</th>
                      <th>Cédula</th>
                      <th>Carrera</th>
                      <th>Esperadas</th>
                      <th>Completadas</th>
                      <th>Pendientes</th>
                      <th>Avance</th>
                      <th>Notas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {autoStudentList.items.map((item) => (
                      <tr key={`auto-list-${item.codigo_estud}`}>
                        <td>{item.estudiante}</td>
                        <td>{item.cedula || '-'}</td>
                        <td>{item.carreras || '-'}</td>
                        <td>{item.esperadas}</td>
                        <td>{item.completadas}</td>
                        <td>{item.pendientes}</td>
                        <td>{Number(item.avance_percent || 0).toFixed(2)}%</td>
                        <td>
                          <button
                            type="button"
                            className="teacher-evaluation__secondary teacher-evaluation__table-action"
                            onClick={() => void openStudentGrades({ codigo_estud: item.codigo_estud })}
                            disabled={detailLoading}
                          >
                            Ver notas
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {autoStudentList.items.length === 0 ? <div className="teacher-evaluation__empty">No hay estudiantes para mostrar.</div> : null}
            </div>
          </section>
        </div>
      ) : null}

      {studentGrades ? (
        <div className="teacher-evaluation__modal-backdrop teacher-evaluation__modal-backdrop--nested" role="presentation">
          <section className="teacher-evaluation__modal teacher-evaluation__modal--nested" role="dialog" aria-modal="true">
            <header className="teacher-evaluation__modal-header">
              <div>
                <p className="teacher-evaluation__eyebrow">Notas del estudiante</p>
                <h2>{studentGrades.estudiante}</h2>
                <p>{studentGrades.cedula} · Periodo {studentGrades.periodo}</p>
              </div>
              <button type="button" className="teacher-evaluation__ghost" onClick={() => setStudentGrades(null)}>
                Cerrar
              </button>
            </header>
            <div className="teacher-evaluation__modal-body">
              <div className="matricula-table-wrap">
                <table className="matricula-table teacher-evaluation__chart-table">
                  <thead>
                    <tr>
                      <th>Materia</th>
                      <th>Carrera</th>
                      <th>Paralelo</th>
                      <th>Promedio final</th>
                    </tr>
                  </thead>
                  <tbody>
                    {studentGrades.items.map((item) => (
                      <tr key={`${item.codigo_materia}-${item.paralelo || ''}`}>
                        <td>{item.materia}</td>
                        <td>{item.carrera}</td>
                        <td>{item.paralelo || '-'}</td>
                        <td>{Number(item.promedio_final || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  )
}
