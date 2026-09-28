import { useEffect, useRef, useState } from 'react'
import { Eye, X } from 'lucide-react'
import type { ValidationStudent } from './enrollmentValidationTypes'

export function MoodleEnrollmentStudentResults({ students, selectedCourses = false }: { students: ValidationStudent[]; selectedCourses?: boolean }) {
  const [detail, setDetail] = useState<ValidationStudent | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (detail && dialog.current && !dialog.current.open) dialog.current.showModal()
  }, [detail])

  return <>
    <div className="enrollment-check__table-wrap"><table aria-label="Matrículas por estudiante"><thead><tr>
      <th>Estudiante</th><th>Carrera y período académico</th><th>Materias matriculadas</th><th>{selectedCourses ? 'Aulas seleccionadas con matrícula' : 'Aulas activas Moodle'}</th><th>Revisión</th><th>Detalle</th>
    </tr></thead><tbody>{students.map(student => <tr key={student.student_code}>
      <td data-label="Estudiante"><strong>{student.student}</strong><small>{student.document} · {student.student_code}</small><small>{student.email}</small></td>
      <td data-label="Carrera y período académico"><strong>{student.academic_career}</strong><small>{student.period} · {student.period_code}</small></td>
      <td data-label="Materias matriculadas"><strong>{student.academic_subjects.length} materia(s)</strong>
        {selectedCourses && <small>{student.evaluated_subjects || 0} dentro de la selección</small>}
        {student.academic_subjects.slice(0, 3).map((item, index) => <small key={index}>{item.subject} · {item.subject_code}</small>)}
        {student.academic_subjects.length > 3 && <small>+ {student.academic_subjects.length - 3} materia(s)</small>}</td>
      <td data-label={selectedCourses ? 'Aulas seleccionadas con matrícula' : 'Aulas activas Moodle'}><strong>{student.moodle_courses.length} aula(s)</strong>
        {student.moodle_courses.slice(0, 3).map(item => <small key={item.course_id}>{item.course}</small>)}
        {student.moodle_courses.length > 3 && <small>+ {student.moodle_courses.length - 3} aula(s)</small>}</td>
      <td data-label="Revisión"><span className={`enrollment-check__badge ${!student.findings && (!selectedCourses || student.evaluated_subjects) ? 'is-match' : ''}`}>{selectedCourses && !student.findings && !student.evaluated_subjects ? 'Fuera de la selección' : `${student.findings} pendiente(s)`}</span>
        {student.query_error && <small>{student.query_error}</small>}</td>
      <td data-label="Detalle"><button type="button" title="Ver matrícula y aulas" aria-label={`Ver matrícula y aulas de ${student.student}`} onClick={() => setDetail(student)}><Eye size={18} /></button></td>
    </tr>)}{!students.length && <tr><td colSpan={6}>No hay estudiantes para este filtro.</td></tr>}</tbody></table></div>
    {detail && <dialog ref={dialog} className="enrollment-check__dialog enrollment-check__student-dialog" aria-labelledby="enrollment-student-title"
      onCancel={event => { event.preventDefault(); setDetail(null) }}>
      <header className="enrollment-check__header"><h3 id="enrollment-student-title">{detail.student}</h3>
        <button onClick={() => setDetail(null)} aria-label="Cerrar matrícula y aulas" title="Cerrar"><X size={18} /></button></header>
      <dl>{[['Identificación', detail.document], ['Correo institucional', detail.email], ['Carrera académica', `${detail.academic_career} · ${detail.career_code}`],
        ['Período de matrícula', `${detail.period} · ${detail.period_code}`]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {detail.query_error && <p className="enrollment-check__warning" role="alert">{detail.query_error}</p>}
      <h3>Materias matriculadas en el sistema académico</h3>
      <div className="enrollment-check__table-wrap"><table aria-label="Materias académicas del estudiante"><thead><tr>
        <th>Semestre</th><th>Materia / código único</th><th>Paralelo</th><th>Relación con Moodle</th>
      </tr></thead><tbody>{detail.academic_subjects.map((item, index) => <tr key={index}>
        <td data-label="Semestre">{item.semester || '-'}</td><td data-label="Materia / código único">{item.subject}<small>{item.subject_code || 'Sin código único'}</small></td>
        <td data-label="Paralelo">{item.parallel || '-'}</td><td data-label="Relación con Moodle">{item.in_scope === false ? 'Fuera de la selección' : item.linked ? 'Materia encontrada en aula activa' : 'Pendiente de verificación'}</td>
      </tr>)}{!detail.academic_subjects.length && <tr><td colSpan={4}>Cabecera de matrícula registrada, sin materias asignadas en esta carrera y período.</td></tr>}</tbody></table></div>
      <h3>{selectedCourses ? 'Aulas seleccionadas con matrícula en Moodle' : 'Aulas activas visibles en Moodle'}</h3>
      <div className="enrollment-check__table-wrap"><table aria-label="Cursos Moodle del estudiante"><thead><tr>
        <th>Resultado</th><th>Aula / código Moodle</th><th>Materia y carrera del pénsum</th><th>Matrículas académicas relacionadas</th><th>Observación</th>
      </tr></thead><tbody>{detail.moodle_courses.map(item => <tr key={item.course_id}>
        <td data-label="Resultado">{item.status_label}</td>
        <td data-label="Aula / código Moodle">{item.course}<small>{item.moodle_code}</small><small>ID: {item.moodle_idnumber || '-'}</small></td>
        <td data-label="Materia y carrera del pénsum">{item.subject}<small>{item.subject_code}</small><small>{item.subject_careers}</small></td>
        <td data-label="Matrículas académicas relacionadas">{item.enrollment_periods || 'Sin matrícula relacionada'}<small>{item.period_relation}</small></td>
        <td data-label="Observación">{item.reason}<small>{item.code_match} · {item.code_match_detail}</small></td>
      </tr>)}{!detail.moodle_courses.length && <tr><td colSpan={5}>{detail.query_error || (selectedCourses ? 'No se confirmó matrícula en las aulas seleccionadas. Revise el detalle por materia.' : 'No se devolvieron aulas activas visibles para esta cuenta.')}</td></tr>}</tbody></table></div>
    </dialog>}
  </>
}
