import { useEffect, useMemo, useState } from 'react'

import {
  downloadTeacherEvaluationGradesPdf,
  fetchTeacherEvaluationAdminPending,
  fetchTeacherEvaluationAdminPeriods,
  fetchTeacherEvaluationGradedTeachers,
} from '../../lib/api'
import type {
  TeacherEvaluationAdminPendingResponse,
  TeacherEvaluationAdminPeriod,
  TeacherEvaluationFlow,
  TeacherEvaluationGradedTeacher,
} from '../../types/app'

type TeacherEvaluationAdminViewProps = {
  displayName?: string
  mode?: 'progress' | 'reports' | 'all'
}

const FLOW_OPTIONS: Array<{ value: TeacherEvaluationFlow | 'all'; label: string }> = [
  { value: 'all', label: 'Todos' },
  { value: 'student', label: 'Estudiante a docente' },
  { value: 'auto_estudiante', label: 'Autoevaluación estudiantil' },
  { value: 'auto_docente', label: 'Autoevaluación docente' },
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
  const [flow, setFlow] = useState<TeacherEvaluationFlow | 'all'>('all')
  const [data, setData] = useState<TeacherEvaluationAdminPendingResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
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

  async function loadPending(selectedPeriod = periodo, selectedFlow = flow) {
    if (!selectedPeriod) {
      setError('Selecciona un periodo.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await fetchTeacherEvaluationAdminPending(selectedPeriod, selectedFlow)
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo consultar pendientes.')
    } finally {
      setLoading(false)
    }
  }

  async function loadGradedTeachers(selectedPeriod = periodo) {
    if (!selectedPeriod) {
      setGradedTeachers([])
      setSelectedTeacher('')
      return
    }
    try {
      const response = await fetchTeacherEvaluationGradedTeachers(selectedPeriod)
      setGradedTeachers(response.items || [])
      setSelectedTeacher((current) =>
        current && (response.items || []).some((item) => item.codigo_doc === current) ? current : '',
      )
    } catch {
      setGradedTeachers([])
      setSelectedTeacher('')
    }
  }

  async function downloadPdf(mode: 'all' | 'teacher') {
    if (!periodo) {
      setError('Selecciona un periodo.')
      return
    }
    if (mode === 'teacher' && !selectedTeacher) {
      setError('Selecciona un docente.')
      return
    }
    setPdfLoading(true)
    setError('')
    try {
      const blob = await downloadTeacherEvaluationGradesPdf(periodo, mode === 'teacher' ? selectedTeacher : '')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = mode === 'teacher'
        ? `calificacion_docente_${periodo}_${selectedTeacher}.pdf`
        : `calificacion_docente_${periodo}_todos.pdf`
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

  useEffect(() => {
    if (periodo) {
      if (showProgress) {
        void loadPending(periodo, flow)
      }
      if (showReports) {
        void loadGradedTeachers(periodo)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, flow, showProgress, showReports])

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

      <section className="teacher-evaluation__panel teacher-evaluation__search-panel">
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
              <select value={flow} onChange={(event) => setFlow(event.target.value as TeacherEvaluationFlow | 'all')} disabled={loading}>
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
              <select value={selectedTeacher} onChange={(event) => setSelectedTeacher(event.target.value)} disabled={pdfLoading || gradedTeachers.length === 0}>
                <option value="">Docente calificado</option>
                {gradedTeachers.map((teacher) => (
                  <option key={teacher.codigo_doc} value={teacher.codigo_doc}>
                    {teacher.docente || `Docente ${teacher.codigo_doc}`}
                  </option>
                ))}
              </select>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => void downloadPdf('teacher')} disabled={pdfLoading || !periodo || !selectedTeacher}>
                {pdfLoading ? 'Generando...' : 'PDF docente'}
              </button>
              <button type="button" className="teacher-evaluation__secondary" onClick={() => void downloadPdf('all')} disabled={pdfLoading || !periodo}>
                {pdfLoading ? 'Generando...' : 'PDF masivo'}
              </button>
            </>
          ) : null}
        </div>
        {error ? <div className="teacher-evaluation__message teacher-evaluation__message--error">{error}</div> : null}
      </section>

      {showProgress && data ? (
        <section className="teacher-evaluation__panel teacher-evaluation__panel--compact">
          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Periodo</th>
                  <th>Evaluación</th>
                  <th>Avance</th>
                  <th>Ponderación</th>
                  <th>Esperadas</th>
                  <th>Completadas</th>
                  <th>Pendientes</th>
                </tr>
              </thead>
              <tbody>
                {data.summary.map((item) => (
                  <tr key={`avance-${item.flow}`}>
                    <td>{data.periodo_detalle || data.periodo}</td>
                    <td>{item.flow_label}</td>
                    <td>{Number(item.progress_percent || 0).toFixed(2)}%</td>
                    <td>{Number(item.ponderacion || 0).toFixed(2)}%</td>
                    <td>{item.expected}</td>
                    <td>{item.completed}</td>
                    <td>{item.pending}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>{data.periodo_detalle || data.periodo}</td>
                  <td>Total</td>
                  <td>{totals.expected ? Number((totals.completed / totals.expected) * 100).toFixed(2) : '0.00'}%</td>
                  <td>-</td>
                  <td>{totals.expected}</td>
                  <td>{totals.completed}</td>
                  <td>{totals.pending}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      ) : null}

      {showReports ? (
        <section className="teacher-evaluation__panel teacher-evaluation__panel--compact">
          <div className="teacher-evaluation__summary-actions">
            <span className="teacher-evaluation__summary-pill">Docentes calificados: {gradedTeachers.length}</span>
            <span className="teacher-evaluation__summary-pill">Periodo: {periodo || '-'}</span>
          </div>

          <div className="matricula-table-wrap">
            <table className="matricula-table">
              <thead>
                <tr>
                  <th>Docente</th>
                  <th>Cédula</th>
                  <th>Registros</th>
                  <th>Promedio final</th>
                  <th>Selección</th>
                </tr>
              </thead>
              <tbody>
                {gradedTeachers.map((teacher) => (
                  <tr key={teacher.codigo_doc}>
                    <td>{teacher.docente || `Docente ${teacher.codigo_doc}`}</td>
                    <td>{teacher.cedula_doc || '-'}</td>
                    <td>{teacher.total_registros}</td>
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
        </section>
      ) : null}
    </main>
  )
}
