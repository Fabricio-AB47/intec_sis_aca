import { useEffect, useMemo, useState } from 'react'

import {
  createAcademicPrerequisiteRule,
  deleteAcademicPrerequisiteRule,
  fetchAcademicEnrollmentCatalog,
  fetchAcademicEnrollmentPensum,
  fetchAcademicPrerequisiteRules,
  updateAcademicPrerequisiteRule,
} from '../../lib/api'
import type {
  AcademicCareerOption,
  AcademicEnrollmentSubject,
  AcademicPrerequisiteRule,
  AcademicPrerequisiteRulePayload,
} from '../../types/app'

type Props = {
  displayName: string
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function subjectLabel(subject: AcademicEnrollmentSubject): string {
  const code = subject.cod_materia || subject.codigo_materia
  const level = subject.semestre ? `Nivel ${subject.semestre}` : 'Sin nivel'
  return `${code} · ${subject.nombre_materia} · ${level}`
}

function payloadForRule(rule: AcademicPrerequisiteRule, active: boolean): AcademicPrerequisiteRulePayload {
  return {
    cod_anio_basica: Number(rule.cod_anio_basica),
    codigo_materia_previa: Number(rule.codigo_materia_previa),
    codigo_materia_consecutiva: Number(rule.codigo_materia_consecutiva),
    bloqueada_por_reprobacion: active,
  }
}

export function PrerequisitosMateriasView({ displayName }: Readonly<Props>) {
  const [careers, setCareers] = useState<AcademicCareerOption[]>([])
  const [careerCode, setCareerCode] = useState('')
  const [subjects, setSubjects] = useState<AcademicEnrollmentSubject[]>([])
  const [rules, setRules] = useState<AcademicPrerequisiteRule[]>([])
  const [previousCode, setPreviousCode] = useState('')
  const [nextCode, setNextCode] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [deleteRule, setDeleteRule] = useState<AcademicPrerequisiteRule | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadCatalog() {
      setLoading(true)
      setError('')
      try {
        const response = await fetchAcademicEnrollmentCatalog()
        if (cancelled) return
        const items = response.carreras || []
        setCareers(items)
        setCareerCode((current) => current || items[0]?.cod_anio_basica || '')
      } catch (requestError) {
        if (!cancelled) setError(errorMessage(requestError, 'No se pudo cargar el catálogo de carreras.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadCatalog()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!careerCode) {
      setSubjects([])
      setRules([])
      return
    }
    let cancelled = false
    async function loadWorkspace() {
      setLoading(true)
      setError('')
      try {
        const [pensumResponse, rulesResponse] = await Promise.all([
          fetchAcademicEnrollmentPensum(careerCode),
          fetchAcademicPrerequisiteRules(careerCode),
        ])
        if (cancelled) return
        setSubjects(pensumResponse.items || [])
        setRules(rulesResponse.items || [])
      } catch (requestError) {
        if (!cancelled) setError(errorMessage(requestError, 'No se pudieron cargar los prerrequisitos.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadWorkspace()
    return () => { cancelled = true }
  }, [careerCode])

  const selectedCareer = careers.find((career) => career.cod_anio_basica === careerCode)
  const visibleRules = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('es')
    if (!normalized) return rules
    return rules.filter((rule) => [
      rule.cod_materia_previa,
      rule.nombre_materia_previa,
      rule.cod_materia_consecutiva,
      rule.nombre_materia_consecutiva,
    ].some((value) => String(value || '').toLocaleLowerCase('es').includes(normalized)))
  }, [query, rules])
  const activeCount = rules.filter((rule) => rule.bloqueada_por_reprobacion).length

  async function reloadRules(): Promise<void> {
    if (!careerCode) return
    const response = await fetchAcademicPrerequisiteRules(careerCode)
    setRules(response.items || [])
  }

  async function createRule(): Promise<void> {
    if (!careerCode || !previousCode || !nextCode) {
      setError('Seleccione la carrera, la materia previa y la materia que será habilitada.')
      return
    }
    if (previousCode === nextCode) {
      setError('La materia previa y la materia habilitada deben ser diferentes.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await createAcademicPrerequisiteRule({
        cod_anio_basica: Number(careerCode),
        codigo_materia_previa: Number(previousCode),
        codigo_materia_consecutiva: Number(nextCode),
        bloqueada_por_reprobacion: true,
      })
      await reloadRules()
      setPreviousCode('')
      setNextCode('')
      setMessage(response.message || 'Prerrequisito creado correctamente.')
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo crear el prerrequisito.'))
    } finally {
      setSaving(false)
    }
  }

  async function toggleRule(rule: AcademicPrerequisiteRule): Promise<void> {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await updateAcademicPrerequisiteRule(
        rule.id,
        payloadForRule(rule, !rule.bloqueada_por_reprobacion),
      )
      await reloadRules()
      setMessage(response.message || 'Prerrequisito actualizado correctamente.')
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo actualizar el prerrequisito.'))
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete(): Promise<void> {
    if (!deleteRule) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await deleteAcademicPrerequisiteRule(deleteRule.id)
      setDeleteRule(null)
      await reloadRules()
      setMessage(response.message || 'Prerrequisito eliminado correctamente.')
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo eliminar el prerrequisito.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="report-page prerequisite-management-page">
      <header className="report-header">
        <div>
          <span>MATRICULACIÓN</span>
          <h1>Prerrequisitos de materias</h1>
          <p>Defina qué materia debe aprobarse antes de habilitar la siguiente dentro de cada carrera.</p>
        </div>
        <div className="report-user-card">
          <strong>{displayName}</strong>
          <span>Control académico</span>
        </div>
      </header>

      <section className="student-card student-card--wide prerequisite-rule-form">
        <div className="student-card-heading">
          <div><span>Nueva relación</span><h2>Crear prerrequisito</h2></div>
          <small>Relación académica por carrera</small>
        </div>
        <div className="prerequisite-form-grid">
          <label>
            Carrera
            <select value={careerCode} onChange={(event) => { setCareerCode(event.target.value); setPreviousCode(''); setNextCode(''); setMessage('') }}>
              <option value="">Seleccione una carrera</option>
              {careers.map((career) => (
                <option key={career.cod_anio_basica} value={career.cod_anio_basica}>{career.nombre_basica}</option>
              ))}
            </select>
          </label>
          <label>
            Materia que debe aprobar
            <select value={previousCode} onChange={(event) => setPreviousCode(event.target.value)} disabled={!careerCode || loading}>
              <option value="">Seleccione la materia previa</option>
              {subjects.map((subject) => (
                <option key={subject.codigo_materia} value={subject.codigo_materia}>{subjectLabel(subject)}</option>
              ))}
            </select>
          </label>
          <label>
            Materia que se habilita
            <select value={nextCode} onChange={(event) => setNextCode(event.target.value)} disabled={!careerCode || loading}>
              <option value="">Seleccione la materia consecutiva</option>
              {subjects.map((subject) => (
                <option key={subject.codigo_materia} value={subject.codigo_materia}>{subjectLabel(subject)}</option>
              ))}
            </select>
          </label>
          <button type="button" className="primary-action" onClick={() => void createRule()} disabled={saving || loading}>
            {saving ? 'Guardando...' : 'Crear prerrequisito'}
          </button>
        </div>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}
      {message ? <div className="inline-success">{message}</div> : null}

      <section className="student-card student-card--wide prerequisite-rule-list">
        <div className="student-card-heading">
          <div><span>Catálogo</span><h2>{selectedCareer?.nombre_basica || 'Relaciones configuradas'}</h2></div>
          <small>{activeCount} activa(s) · {rules.length} total</small>
        </div>
        <label className="prerequisite-search">
          Buscar materia
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Código o nombre de la materia" />
        </label>
        <div className="matricula-table-wrap">
          <table className="matricula-table prerequisite-rules-table">
            <thead>
              <tr>
                <th>Materia previa</th>
                <th>Habilita</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {visibleRules.map((rule) => (
                <tr key={rule.id} className={rule.es_autorreferencia ? 'prerequisite-rule--invalid' : ''}>
                  <td>
                    <strong>{rule.cod_materia_previa || rule.codigo_materia_previa} · {rule.nombre_materia_previa || 'Materia no encontrada'}</strong>
                    <small>Nivel {rule.semestre_materia_previa || '-'}</small>
                  </td>
                  <td>
                    <strong>{rule.cod_materia_consecutiva || rule.codigo_materia_consecutiva} · {rule.nombre_materia_consecutiva || 'Materia no encontrada'}</strong>
                    <small>Nivel {rule.semestre_materia_consecutiva || '-'}</small>
                  </td>
                  <td>
                    <span className={`prerequisite-status prerequisite-status--${rule.bloqueada_por_reprobacion ? 'active' : 'inactive'}`}>
                      {rule.es_autorreferencia ? 'Revisar relación' : rule.bloqueada_por_reprobacion ? 'Activa' : 'Inactiva'}
                    </span>
                  </td>
                  <td>
                    <div className="prerequisite-row-actions">
                      <button type="button" className="ghost-button" onClick={() => void toggleRule(rule)} disabled={saving}>
                        {rule.bloqueada_por_reprobacion ? 'Desactivar' : 'Activar'}
                      </button>
                      <button type="button" className="ghost-button" onClick={() => setDeleteRule(rule)} disabled={saving}>Eliminar</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && !visibleRules.length ? <tr><td colSpan={4}>No existen prerrequisitos con los filtros actuales.</td></tr> : null}
              {loading ? <tr><td colSpan={4}>Cargando prerrequisitos...</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      {deleteRule ? (
        <div className="matricula-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="delete-prerequisite-title">
          <div className="matricula-confirm-modal">
            <div>
              <span>Confirmación</span>
              <h2 id="delete-prerequisite-title">Eliminar prerrequisito</h2>
              <p>Se eliminará la relación entre {deleteRule.nombre_materia_previa} y {deleteRule.nombre_materia_consecutiva}.</p>
            </div>
            <div className="matricula-confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setDeleteRule(null)} disabled={saving}>Cancelar</button>
              <button type="button" className="primary-action" onClick={() => void confirmDelete()} disabled={saving}>
                {saving ? 'Eliminando...' : 'Eliminar relación'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
