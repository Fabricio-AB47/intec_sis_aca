import { useEffect, useState } from 'react'

import { fetchTeacherComplianceFormat, updateTeacherComplianceFormat } from '../../lib/api'
import type { TeacherComplianceReportFormat } from '../../types/app'

type TeacherComplianceFormatViewProps = {
  displayName: string
}

const emptyFormat: TeacherComplianceReportFormat = {
  title: '',
  pea_heading: '',
  pea_instruction: '',
  syllabus_update_heading: '',
  syllabus_update_default: '',
  virtual_classroom_heading: '',
  virtual_classroom_intro: '',
  resources: [],
  teams_heading: '',
  attendance_heading: '',
  grades_heading: '',
  grades_instruction: '',
  annexes_heading: '',
  annexes_intro: '',
  annexes: [],
  closing: '',
  signature_label: '',
  signature_role: '',
}

function listToText(values: string[]) {
  return values.join('\n')
}

function textToList(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function TeacherComplianceFormatView({ displayName }: Readonly<TeacherComplianceFormatViewProps>) {
  const [format, setFormat] = useState<TeacherComplianceReportFormat>(emptyFormat)
  const [resourcesText, setResourcesText] = useState('')
  const [annexesText, setAnnexesText] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  function updateField(field: keyof TeacherComplianceReportFormat, value: string) {
    setFormat((current) => ({ ...current, [field]: value }))
  }

  async function loadFormat() {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const payload = await fetchTeacherComplianceFormat()
      setFormat(payload)
      setResourcesText(listToText(payload.resources || []))
      setAnnexesText(listToText(payload.annexes || []))
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar el formato docente')
    } finally {
      setLoading(false)
    }
  }

  async function saveFormat() {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await updateTeacherComplianceFormat({
        ...format,
        resources: textToList(resourcesText),
        annexes: textToList(annexesText),
      })
      setFormat(payload)
      setResourcesText(listToText(payload.resources || []))
      setAnnexesText(listToText(payload.annexes || []))
      setMessage('Formato de cumplimiento docente actualizado.')
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo guardar el formato docente')
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    void loadFormat()
  }, [])

  return (
    <div className="student-dashboard portal-page">
      <header className="student-hero">
        <div>
          <p className="eyebrow">Administración</p>
          <h1>Formato informe docente</h1>
          <p>{displayName}</p>
        </div>
        <div className="student-user-pill">
          <span>Documento</span>
          <strong>Cumplimiento</strong>
          <small>Portal docente</small>
        </div>
      </header>

      <section className="student-card student-card--wide teacher-format-card">
        <div className="section-title">
          <div>
            <span>Parámetros editables</span>
            <h2>Plantilla de reporte académico</h2>
          </div>
          <button type="button" className="ghost-button" onClick={loadFormat} disabled={loading || saving}>
            {loading ? 'Cargando...' : 'Recargar'}
          </button>
        </div>

        {error ? <p className="form-error">{error}</p> : null}
        {message ? <p className="form-success">{message}</p> : null}

        <div className="teacher-format-grid">
          <label>
            <span>Título principal</span>
            <input value={format.title} onChange={(event) => updateField('title', event.target.value)} />
          </label>
          <label>
            <span>Cierre</span>
            <input value={format.closing} onChange={(event) => updateField('closing', event.target.value)} />
          </label>
          <label>
            <span>Etiqueta de firma</span>
            <input value={format.signature_label} onChange={(event) => updateField('signature_label', event.target.value)} />
          </label>
          <label>
            <span>Rol de firma</span>
            <input value={format.signature_role} onChange={(event) => updateField('signature_role', event.target.value)} />
          </label>
        </div>

        <div className="teacher-format-grid teacher-format-grid--wide">
          <label>
            <span>Título PEA y sílabo</span>
            <input value={format.pea_heading} onChange={(event) => updateField('pea_heading', event.target.value)} />
          </label>
          <label>
            <span>Texto PEA y sílabo</span>
            <textarea value={format.pea_instruction} onChange={(event) => updateField('pea_instruction', event.target.value)} />
          </label>
          <label>
            <span>Título actualización sílabo</span>
            <input value={format.syllabus_update_heading} onChange={(event) => updateField('syllabus_update_heading', event.target.value)} />
          </label>
          <label>
            <span>Texto por defecto actualización</span>
            <textarea value={format.syllabus_update_default} onChange={(event) => updateField('syllabus_update_default', event.target.value)} />
          </label>
          <label>
            <span>Título aula virtual</span>
            <input value={format.virtual_classroom_heading} onChange={(event) => updateField('virtual_classroom_heading', event.target.value)} />
          </label>
          <label>
            <span>Introducción aula virtual</span>
            <textarea value={format.virtual_classroom_intro} onChange={(event) => updateField('virtual_classroom_intro', event.target.value)} />
          </label>
          <label>
            <span>Recursos requeridos, uno por línea</span>
            <textarea value={resourcesText} onChange={(event) => setResourcesText(event.target.value)} />
          </label>
          <label>
            <span>Título TEAMS</span>
            <input value={format.teams_heading} onChange={(event) => updateField('teams_heading', event.target.value)} />
          </label>
          <label>
            <span>Título asistencias</span>
            <input value={format.attendance_heading} onChange={(event) => updateField('attendance_heading', event.target.value)} />
          </label>
          <label>
            <span>Título reporte de notas</span>
            <input value={format.grades_heading} onChange={(event) => updateField('grades_heading', event.target.value)} />
          </label>
          <label>
            <span>Texto reporte de notas</span>
            <textarea value={format.grades_instruction} onChange={(event) => updateField('grades_instruction', event.target.value)} />
          </label>
          <label>
            <span>Título anexos</span>
            <input value={format.annexes_heading} onChange={(event) => updateField('annexes_heading', event.target.value)} />
          </label>
          <label>
            <span>Introducción anexos</span>
            <textarea value={format.annexes_intro} onChange={(event) => updateField('annexes_intro', event.target.value)} />
          </label>
          <label>
            <span>Anexos requeridos, uno por línea</span>
            <textarea value={annexesText} onChange={(event) => setAnnexesText(event.target.value)} />
          </label>
        </div>

        <div className="teacher-format-actions">
          <button type="button" className="primary-action" onClick={saveFormat} disabled={saving || loading}>
            {saving ? 'Guardando...' : 'Guardar formato'}
          </button>
        </div>
      </section>
    </div>
  )
}
