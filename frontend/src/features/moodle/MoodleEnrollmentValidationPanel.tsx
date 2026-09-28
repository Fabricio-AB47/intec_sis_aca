import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CheckCheck, ChevronLeft, ChevronRight, Eye, FileSpreadsheet, FileText, LoaderCircle, RefreshCw, X } from 'lucide-react'
import { downloadEnrollmentValidation, fetchAcademicEnrollmentValidation, fetchEnrollmentValidationCatalog, startAcademicEnrollmentValidation } from '../../lib/api'
import type { AcademicValidationJob, ValidationCatalog, ValidationReport, ValidationRow } from './enrollmentValidationTypes'
import { MoodleEnrollmentStudentResults } from './MoodleEnrollmentStudentResults'
import './MoodleEnrollmentValidation.css'

const PAGE_SIZE = 25
const DEFAULT_PARALLEL = '*'
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es-EC')
const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la validación.'

export function MoodleEnrollmentValidationPanel() {
  const [catalog, setCatalog] = useState<ValidationCatalog | null>(null)
  const [period, setPeriod] = useState('')
  const [career, setCareer] = useState('')
  const [progress, setProgress] = useState<AcademicValidationJob | null>(null)
  const [resultView, setResultView] = useState<'students' | 'subjects'>('students')
  const [query, setQuery] = useState('')
  const [coursePage, setCoursePage] = useState(0)
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [report, setReport] = useState<ValidationReport | null>(null)
  const [busy, setBusy] = useState<'catalog' | 'validation' | 'xlsx' | 'pdf' | ''>('catalog')
  const [error, setError] = useState('')
  const [rowQuery, setRowQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [rowPage, setRowPage] = useState(0)
  const [detail, setDetail] = useState<ValidationRow | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const request = useRef<AbortController | null>(null)
  const filters = useRef({ period: '', career: '' })
  const alive = useRef(true)
  const count = Object.keys(selected).length
  const careers = (catalog?.careers || []).filter(item => item.period_codes.includes(Number(period)))
  const showsStudents = report?.mode === 'academic' && resultView === 'students'
  const courses = useMemo(() => (catalog?.courses || []).filter(c => normalize(`${c.fullname} ${c.shortname} ${c.category}`).includes(normalize(query))), [catalog, query])
  const visibleCourses = courses.slice(coursePage * PAGE_SIZE, (coursePage + 1) * PAGE_SIZE)
  const rows = useMemo(() => (report?.rows || []).filter(row => (status === 'all' || (status === 'findings'
    ? !['COINCIDE', 'INACTIVO', 'MATERIA_MATRICULADA', 'ANTECEDENTE_ACADEMICO'].includes(row.status) : row.status === status))
    && normalize(Object.values(row).join(' ')).includes(normalize(rowQuery))), [report, rowQuery, status])
  const students = useMemo(() => (report?.students || []).filter(student =>
    (status === 'all' || (status === 'findings' ? student.findings > 0 : student.rows.some(row => row.status === status)))
    && normalize(JSON.stringify(student)).includes(normalize(rowQuery))), [report, rowQuery, status])

  const loadCatalog = useCallback(async () => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setBusy('catalog'); setError(''); setReport(null); setProgress(null); setDetail(null)
    try {
      const result = await fetchEnrollmentValidationCatalog(controller.signal)
      if (!controller.signal.aborted) {
        setCatalog(result)
        setSelected(current => Object.fromEntries(Object.entries(current).filter(([id]) => result.courses.some(c => c.id === Number(id)))))
        const { period, career } = filters.current
        if (period && !result.periods.some(item => item.code === Number(period))) {
          filters.current = { period: '', career: '' }
          setPeriod(''); setCareer(''); setSelected({})
        } else if (career && !result.careers.some(item => item.code === Number(career) && item.period_codes.includes(Number(period)))) {
          filters.current = { period, career: '' }
          setCareer(''); setSelected({})
        }
        setCoursePage(0)
      }
    } catch (caught) {
      if (!controller.signal.aborted) setError(message(caught))
    } finally {
      if (!controller.signal.aborted) setBusy('')
    }
  }, [])

  useEffect(() => {
    alive.current = true
    const timer = window.setTimeout(() => void loadCatalog(), 0)
    return () => { alive.current = false; window.clearTimeout(timer); request.current?.abort() }
  }, [loadCatalog])
  useEffect(() => {
    if (detail && dialog.current && !dialog.current.open) dialog.current.showModal()
  }, [detail])

  function updateSelection(next: Record<number, string>) {
    setSelected(next); setReport(null); setProgress(null); setDetail(null); setError('')
  }

  function changePeriod(value: string) {
    filters.current = { period: value, career: '' }
    setPeriod(value); setCareer(''); updateSelection({})
  }

  function changeCareer(value: string) {
    filters.current.career = value
    setCareer(value); updateSelection({})
  }

  async function validate() {
    if (!period || !career || !count || count > (catalog?.max_courses || 100) || Object.values(selected).some(value => !value) || busy) return
    const controller = new AbortController()
    request.current = controller
    setBusy('validation'); setError(''); setReport(null); setProgress(null)
    try {
      let job = await startAcademicEnrollmentValidation({ period_code: Number(period), career_code: Number(career),
        courses: Object.entries(selected).map(([id, parallel]) => ({ id: Number(id), parallel })) }, controller.signal)
      while (!controller.signal.aborted && job.status === 'running') {
        setProgress(job)
        await new Promise(resolve => window.setTimeout(resolve, 1000))
        if (controller.signal.aborted) return
        job = await fetchAcademicEnrollmentValidation(job.job_id, controller.signal)
      }
      if (controller.signal.aborted) return
      setProgress(job)
      if (job.status === 'error' || !job.report) throw new Error(job.error || 'No se pudo completar la validación.')
      const result = job.report
      setResultView('students')
      if (!controller.signal.aborted) { setReport(result); setRowPage(0); setStatus('all'); setRowQuery('') }
    } catch (caught) {
      if (!controller.signal.aborted) setError(message(caught))
    } finally {
      if (!controller.signal.aborted) setBusy('')
    }
  }

  async function download(format: 'xlsx' | 'pdf') {
    if (!report || busy) return
    setBusy(format); setError('')
    try {
      const blob = await downloadEnrollmentValidation(report.report_id, format)
      if (!alive.current) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = `validacion_matriculas_${report.period.code}.${format}`
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (caught) {
      if (alive.current) setError(message(caught))
    } finally {
      if (alive.current) setBusy('')
    }
  }

  function pager(page: number, total: number, onPage: (value: number) => void, label: string) {
    return <nav className="enrollment-check__pager" aria-label={label}>
      <span>{total} registro(s) · Página {page + 1} de {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
      <button type="button" disabled={!!busy || page === 0} onClick={() => onPage(page - 1)} title={`Anterior: ${label}`} aria-label={`Anterior: ${label}`}><ChevronLeft size={18} /></button>
      <button type="button" disabled={!!busy || (page + 1) * PAGE_SIZE >= total} onClick={() => onPage(page + 1)} title={`Siguiente: ${label}`} aria-label={`Siguiente: ${label}`}><ChevronRight size={18} /></button>
    </nav>
  }

  return <section className="enrollment-check" aria-label="Validación de matrículas">
    <header className="enrollment-check__header"><h2>Validación de matrículas</h2>
      <button type="button" onClick={() => void loadCatalog()} disabled={!!busy}><RefreshCw size={17} />Actualizar catálogo</button>
    </header>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy && <p role="status" className="enrollment-check__loading"><LoaderCircle size={18} />{busy === 'catalog' ? 'Cargando períodos y cursos...' : busy === 'validation' ? 'Validando matrículas...' : 'Preparando reporte...'}</p>}
    {progress && busy === 'validation' && <div className="enrollment-check__progress"><progress aria-label="Avance de validación" value={progress.processed} max={progress.total || 1} /><span>{progress.processed} de {progress.total} {progress.unit === 'courses' ? 'curso(s)' : 'estudiante(s)'} revisados</span></div>}
    <div className="enrollment-check__filters">
      <label>Período académico<select value={period} disabled={!!busy} onChange={e => changePeriod(e.target.value)}>
        <option value="">Seleccione un período</option>
        {catalog?.periods.map(p => <option key={p.code} value={p.code}>{p.name} · {p.code}</option>)}
      </select></label>
      <label>Carrera matriculada<select value={career} disabled={!!busy || !period} onChange={event => changeCareer(event.target.value)}>
        <option value="">Seleccione una carrera</option>{careers.map(item => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
      </select></label>
    </div>
    <div className="enrollment-check__filters">
      <label>Buscar curso<input type="search" value={query} onChange={e => { setQuery(e.target.value); setCoursePage(0) }} disabled={!!busy} /></label>
      <button type="button" disabled={!!busy || !career || !visibleCourses.length || count >= (catalog?.max_courses || 100)} onClick={() => {
        const next = { ...selected }
        for (const c of visibleCourses) {
          if (Object.keys(next).length >= (catalog?.max_courses || 100)) break
          if (!(c.id in next)) next[c.id] = DEFAULT_PARALLEL
        }
        updateSelection(next)
      }}><CheckCheck size={17} />Seleccionar visibles</button>
      <button type="button" disabled={!!busy || !count} onClick={() => updateSelection({})}><X size={17} />Limpiar selección</button>
    </div>
    <div className="enrollment-check__table-wrap"><table aria-label="Cursos Moodle para validar"><thead><tr><th>Seleccionar</th><th>Curso Moodle</th><th>Código Moodle</th><th>Paralelo</th></tr></thead>
      <tbody>{visibleCourses.map(course => <tr key={course.id}>
        <td data-label="Seleccionar"><input type="checkbox" aria-label={`Seleccionar ${course.fullname}`} checked={course.id in selected} disabled={!!busy || !career || (!(course.id in selected) && count >= (catalog?.max_courses || 100))}
          onChange={e => { const next = { ...selected }; if (e.target.checked) next[course.id] = DEFAULT_PARALLEL; else delete next[course.id]; updateSelection(next) }} /></td>
        <td data-label="Curso Moodle"><strong>{course.fullname}</strong><small>{course.category}</small></td><td data-label="Código Moodle">{course.shortname}</td>
        <td data-label="Paralelo"><select aria-label={`Paralelo de ${course.fullname}`} value={selected[course.id] ?? DEFAULT_PARALLEL} disabled={!!busy || !(course.id in selected)}
          onChange={e => updateSelection({ ...selected, [course.id]: e.target.value })}>
          <option value="">Seleccione</option><option value="*">Todos los paralelos</option>
          {catalog?.parallels.map(p => <option key={p} value={p}>{p}</option>)}
        </select></td>
      </tr>)}{!visibleCourses.length && !busy && <tr><td colSpan={4}>No se encontraron cursos.</td></tr>}</tbody></table></div>
    {pager(coursePage, courses.length, setCoursePage, 'Cursos')}
    <div className="enrollment-check__actions"><strong>{count} curso(s) seleccionado(s) · Estudiantes activos</strong>
      <button className="enrollment-check__primary" type="button" disabled={!!busy || !period || !career || !count || count > (catalog?.max_courses || 100) || Object.values(selected).some(value => !value)} onClick={() => void validate()}><CheckCheck size={18} />Validar matrículas</button></div>
    {report && <section aria-label="Resultado de validación" className="enrollment-check__result">
      <header className="enrollment-check__header"><div><h3>{report.career?.name || 'Resultado'} · {report.period.name}</h3><small>{new Date(report.generated_at).toLocaleString('es-EC')} · {report.scope.length} aula(s){report.students ? ` · ${report.students.length} estudiante(s)` : ''}</small></div>
        <div className="enrollment-check__downloads"><button disabled={!!busy} onClick={() => void download('xlsx')}><FileSpreadsheet size={17} />Excel completo</button><button disabled={!!busy} onClick={() => void download('pdf')}><FileText size={17} />PDF completo</button></div>
      </header>
      {report.warnings.map(w => <p key={w} className="enrollment-check__warning" role="alert">{w}</p>)}
      <div className="enrollment-check__summary">{[['Coincidencias', report.summary.matches], ['Hallazgos', report.summary.findings], ['Inactivos excluidos', report.summary.inactive], ['Con antecedentes de carrera', report.summary.career_history]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      {report.mode === 'academic' && <div className="enrollment-check__modes" role="tablist" aria-label="Vista de resultados">
        <button role="tab" aria-selected={showsStudents} onClick={() => { setResultView('students'); setRowPage(0) }}>Estudiantes</button>
        <button role="tab" aria-selected={!showsStudents} onClick={() => { setResultView('subjects'); setRowPage(0) }}>Detalle por materia</button>
      </div>}
      <div className="enrollment-check__filters">
        <label>Buscar estudiante o materia<input type="search" value={rowQuery} onChange={e => { setRowQuery(e.target.value); setRowPage(0) }} /></label>
        <label>Resultado<select value={status} onChange={e => { setStatus(e.target.value); setRowPage(0) }}><option value="all">Todos</option><option value="findings">Solo hallazgos</option>
          {[...new Map(report.rows.map(r => [r.status, r.status_label])).entries()].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
      </div>
      {showsStudents ? <MoodleEnrollmentStudentResults students={students.slice(rowPage * PAGE_SIZE, (rowPage + 1) * PAGE_SIZE)} selectedCourses={report.course_selection} /> : <div className="enrollment-check__table-wrap"><table><thead><tr><th>Resultado</th><th>Estudiante</th><th>Materia / aula</th><th>Carrera / paralelo</th><th>Observación</th><th>Detalle</th></tr></thead>
        <tbody>{rows.slice(rowPage * PAGE_SIZE, (rowPage + 1) * PAGE_SIZE).map((row, index) => <tr key={`${row.course_id}-${row.student_code}-${index}`}>
          <td data-label="Resultado"><span className={`enrollment-check__badge ${row.status === 'COINCIDE' ? 'is-match' : row.status === 'INACTIVO' ? 'is-inactive' : ''}`}>{row.status_label}</span></td>
          <td data-label="Estudiante"><strong>{row.student || 'Sin estudiante identificado'}</strong><small>{row.document} · {row.student_code}</small></td>
          <td data-label="Materia / aula">{row.course}<small>{row.subject_code}</small><small>{row.code_match}</small></td><td data-label="Carrera / paralelo">{row.academic_career || row.period_careers || 'Sin matrícula en el período'}<small>Académico: {row.academic_parallel || '-'} · Moodle: {row.moodle_parallel}</small></td>
          <td data-label="Observación">{row.reason}{(row.previous_careers || row.career_changes) && <small>Antecedentes de otra carrera</small>}</td>
          <td data-label="Detalle"><button type="button" title="Ver detalle" aria-label={`Ver detalle de ${row.student || row.course}`} onClick={() => setDetail(row)}><Eye size={18} /></button></td>
        </tr>)}{!rows.length && <tr><td colSpan={6}>No hay registros para este filtro.</td></tr>}</tbody></table></div>
      }
      {pager(rowPage, showsStudents ? students.length : rows.length, setRowPage, 'Resultados')}
    </section>}
    {detail && <dialog ref={dialog} className="enrollment-check__dialog" onCancel={e => { e.preventDefault(); setDetail(null) }} aria-labelledby="enrollment-detail-title">
      <header className="enrollment-check__header"><h3 id="enrollment-detail-title">{detail.student || detail.course}</h3><button onClick={() => setDetail(null)} title="Cerrar detalle" aria-label="Cerrar detalle"><X size={18} /></button></header>
      <dl>{[
        ['Resultado', detail.status_label], ['Identificación', detail.document], ['Código estudiante', detail.student_code],
        ['Correo académico', detail.email], ['Correo Moodle', detail.moodle_email], ['Usuario Moodle', detail.moodle_user_id],
        ['Período', `${detail.period} (${detail.period_code})`], ['Aula Moodle', `${detail.course} (${detail.course_id})`],
        ['Código Moodle', detail.moodle_code], ['Código único materia', detail.subject_code], ['Carrera de matrícula', detail.academic_career],
        ['Número ID curso Moodle', detail.moodle_idnumber], ['Comparación del código', detail.code_match],
        ['Criterio de comparación', detail.code_match_detail], ['Códigos PENSUM considerados', detail.code_candidates],
        ...(report?.mode === 'academic' ? [['Carreras de la materia', detail.subject_careers], ['Matrículas relacionadas', detail.enrollment_periods], ['Período del aula', detail.period_relation]] : []),
        ['Carreras del período', detail.period_careers], ['Paralelo académico', detail.academic_parallel], ['Paralelo consultado', detail.moodle_parallel],
        ['Otras carreras históricas', detail.previous_careers], ['Cambios de carrera aplicados', detail.career_changes], ['Observación', detail.reason],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || '-'}</dd></div>)}</dl>
    </dialog>}
  </section>
}
