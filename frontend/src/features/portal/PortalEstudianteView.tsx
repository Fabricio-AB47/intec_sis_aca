import { Fragment, useEffect, useMemo, useState } from 'react'

import {
  downloadPortalStudentPdf,
  fetchPortalStudentRecord,
} from '../../lib/api'
import type {
  PortalAcademicGridItem,
  PortalAcademicRecordItem,
  PortalCurriculumItem,
  PortalStudentSection,
  PortalStudentRecordResponse,
} from '../../types/app'

type PortalEstudianteViewProps = {
  displayName: string
  activeSection: PortalStudentSection
  onSectionChange: (section: PortalStudentSection) => void
}

function numberText(value: number | null | undefined, decimals: number = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toFixed(decimals)
}

function integerText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  return String(Math.round(value))
}

function statusClass(value: string | undefined) {
  const normalized = (value || '').toLowerCase()
  if (normalized.includes('aprob')) return 'portal-status portal-status--ok'
  if (normalized.includes('reprob')) return 'portal-status portal-status--danger'
  if (normalized.includes('pend')) return 'portal-status portal-status--warning'
  return 'portal-status'
}

function isHomologationValue(item: { tipo_matricula?: string; detalle_periodo?: string; esquema_calificacion?: string; es_homologacion?: boolean }) {
  if (item.es_homologacion) return true
  const tipo = (item.tipo_matricula || '').trim().toUpperCase()
  const text = `${item.tipo_matricula || ''} ${item.detalle_periodo || ''} ${item.esquema_calificacion || ''}`.toUpperCase()
  return tipo === 'H' || text.includes('HOMO')
}

function isHomologation(item: PortalAcademicRecordItem) {
  return isHomologationValue(item)
}

function curriculumCode(item: PortalCurriculumItem | PortalAcademicGridItem | PortalAcademicRecordItem) {
  return item.cod_materia || item.codigo_materia || '-'
}

function inferredHours(item: PortalCurriculumItem | PortalAcademicGridItem | PortalAcademicRecordItem) {
  if (item.horas !== null && item.horas !== undefined && !Number.isNaN(item.horas)) return item.horas
  if (item.creditos !== null && item.creditos !== undefined && !Number.isNaN(item.creditos)) return item.creditos * 36
  return null
}

function inferredMalla(item: PortalCurriculumItem | PortalAcademicGridItem | PortalAcademicRecordItem) {
  if (item.num_malla !== null && item.num_malla !== undefined && !Number.isNaN(item.num_malla)) return item.num_malla
  const code = item.cod_materia || ''
  const match = code.match(/(?:^|-)20\d{2}(?=-|$)/)
  return match ? Number(match[0].replace('-', '')) : null
}

function normalizeSubjectKey(value: string | undefined) {
  return (value || '').trim().toUpperCase()
}

function subjectKeys(item: PortalCurriculumItem | PortalAcademicGridItem | PortalAcademicRecordItem) {
  return [
    normalizeSubjectKey(item.codigo_materia),
    normalizeSubjectKey(item.cod_materia),
    normalizeSubjectKey(item.nombre_materia),
  ].filter(Boolean)
}

function academicSortValue(item: PortalCurriculumItem | PortalAcademicGridItem) {
  return [
    item.semestre ?? 999,
    item.orden ?? 9999,
    Number(item.codigo_materia || 999999),
    item.nombre_materia || '',
  ] as const
}

export function PortalEstudianteView({ displayName, activeSection, onSectionChange }: Readonly<PortalEstudianteViewProps>) {
  const [approvedOnly, setApprovedOnly] = useState(false)
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set())
  const [loading, setLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [error, setError] = useState('')
  const [record, setRecord] = useState<PortalStudentRecordResponse | null>(null)

  const items = useMemo(() => record?.items || [], [record])
  const periodOptions = useMemo(() => {
    const periods = new Map<string, string>()
    for (const item of items) {
      const code = item.codigo_periodo || item.detalle_periodo || ''
      if (!code) continue
      periods.set(code, item.detalle_periodo || item.codigo_periodo || code)
    }
    return Array.from(periods, ([code, label]) => ({ code, label }))
  }, [items])
  const filteredItems = useMemo(
    () => selectedPeriod
      ? items.filter((item) => item.codigo_periodo === selectedPeriod || item.detalle_periodo === selectedPeriod)
      : [],
    [items, selectedPeriod]
  )
  const selectedPeriodIsHomologation = useMemo(
    () => filteredItems.length > 0 && filteredItems.every((item) => isHomologation(item)),
    [filteredItems]
  )
  const curriculum = useMemo(() => record?.curriculum || [], [record])
  const curriculumRows = useMemo<PortalCurriculumItem[]>(() => {
    if (curriculum.length > 0) return curriculum

    const subjects = new Map<string, PortalCurriculumItem>()
    for (const item of items) {
      const key = item.codigo_materia || item.cod_materia || item.nombre_materia || ''
      if (!key || subjects.has(key)) continue
      subjects.set(key, {
        cod_anio_basica: item.cod_anio_basica,
        nombre_carrera: item.nombre_carrera,
        codigo_materia: item.codigo_materia,
        cod_materia: item.cod_materia,
        nombre_materia: item.nombre_materia,
        semestre: item.semestre,
        creditos: item.creditos,
        horas: item.horas ?? null,
        orden: item.orden ?? null,
        num_malla: item.num_malla ?? null,
        unidad_organiza: '',
        estado_materia: 'Desde matricula',
      })
    }

    return Array.from(subjects.values()).sort((left, right) => {
      const leftLevel = left.semestre ?? 999
      const rightLevel = right.semestre ?? 999
      if (leftLevel !== rightLevel) return leftLevel - rightLevel
      return (left.nombre_materia || '').localeCompare(right.nombre_materia || '')
    })
  }, [curriculum, items])
  const academicGrid = useMemo(() => record?.academic_grid || [], [record])
  const academicRows = useMemo<PortalAcademicGridItem[]>(() => {
    if (academicGrid.length > 0) {
      return [...academicGrid].sort((left, right) => {
        const leftSort = academicSortValue(left)
        const rightSort = academicSortValue(right)
        return leftSort[0] - rightSort[0] || leftSort[1] - rightSort[1] || leftSort[2] - rightSort[2] || leftSort[3].localeCompare(rightSort[3])
      })
    }

    const recordsBySubject = new Map<string, PortalAcademicRecordItem[]>()
    for (const item of items) {
      for (const key of subjectKeys(item)) {
        const list = recordsBySubject.get(key) || []
        list.push(item)
        recordsBySubject.set(key, list)
      }
    }

    return curriculumRows.map((subject) => {
      const attempts = new Map<string, PortalAcademicRecordItem>()
      for (const key of subjectKeys(subject)) {
        for (const item of recordsBySubject.get(key) || []) {
          attempts.set(recordRowKey(item, attempts.size), item)
        }
      }
      const attemptList = Array.from(attempts.values())
      const bestAttempt = attemptList
        .sort((left, right) => {
          const leftFinal = left.promedio_final ?? -1
          const rightFinal = right.promedio_final ?? -1
          const leftApproved = leftFinal >= 7 ? 1 : 0
          const rightApproved = rightFinal >= 7 ? 1 : 0
          return rightApproved - leftApproved || rightFinal - leftFinal
        })[0]
      const status = bestAttempt ? statusFromFinal(bestAttempt) : 'Pendiente'

      return {
        ...subject,
        estado_academico: status,
        aprobada: status === 'Aprobada',
        faltante: status !== 'Aprobada',
        intentos: attemptList.length,
        ultimo_periodo: bestAttempt?.detalle_periodo || '',
        codigo_periodo: bestAttempt?.codigo_periodo || '',
        paralelo: bestAttempt?.paralelo || '',
        tipo_matricula: bestAttempt?.tipo_matricula || '',
        es_homologacion: bestAttempt ? isHomologation(bestAttempt) : false,
        esquema_calificacion: bestAttempt?.esquema_calificacion || (bestAttempt && isHomologation(bestAttempt) ? 'HOMOLOGACION' : 'REGULAR'),
        teoria_homo: bestAttempt?.teoria_homo ?? null,
        practica_homo: bestAttempt?.practica_homo ?? null,
        p1_tareas: bestAttempt?.p1_tareas ?? null,
        p1_proyectos: bestAttempt?.p1_proyectos ?? null,
        p1_examen: bestAttempt?.p1_examen ?? null,
        prom_p1: bestAttempt?.prom_p1 ?? null,
        p2_tareas: bestAttempt?.p2_tareas ?? null,
        p2_proyectos: bestAttempt?.p2_proyectos ?? null,
        p2_examen: bestAttempt?.p2_examen ?? null,
        prom_p2: bestAttempt?.prom_p2 ?? null,
        p3_tareas: bestAttempt?.p3_tareas ?? null,
        p3_proyectos: bestAttempt?.p3_proyectos ?? null,
        p3_examen: bestAttempt?.p3_examen ?? null,
        prom_p3: bestAttempt?.prom_p3 ?? null,
        promedio_final: bestAttempt?.promedio_final ?? 0,
        nota_aprobar: bestAttempt?.nota_aprobar ?? 7,
      }
    }).sort((left, right) => {
      const leftSort = academicSortValue(left)
      const rightSort = academicSortValue(right)
      return leftSort[0] - rightSort[0] || leftSort[1] - rightSort[1] || leftSort[2] - rightSort[2] || leftSort[3].localeCompare(rightSort[3])
    })
  }, [academicGrid, curriculumRows, items])
  const summary = record?.summary
  const student = record?.student
  const careerName = academicRows[0]?.nombre_carrera || curriculumRows[0]?.nombre_carrera || items[0]?.nombre_carrera || '-'
  const recordTotal = summary?.total_materias ?? items.length
  const academicMetrics = useMemo(() => {
    const rows = academicRows.length > 0 ? academicRows : []
    const total = rows.length || curriculumRows.length || recordTotal
    let approved = 0
    let failed = 0
    let inProgress = 0
    let approvedCreditTotal = 0
    let creditTotal = 0
    let finalSum = 0
    let finalCount = 0

    for (const row of rows) {
      const credits = row.creditos || 0
      creditTotal += credits
      const final = row.promedio_final
      const hasFinal = final !== null
        && final !== undefined
        && !Number.isNaN(final)
        && ((row.intentos ?? 0) > 0 || row.estado_academico !== 'Pendiente')

      if (hasFinal) {
        finalSum += final
        finalCount += 1
        if (final >= 7) {
          approved += 1
          approvedCreditTotal += credits
        } else {
          failed += 1
        }
      } else if (row.estado_academico === 'En curso') {
        inProgress += 1
      }
    }

    if (rows.length === 0) {
      return {
        total,
        approved: summary?.aprobadas ?? 0,
        failed: summary?.reprobadas ?? 0,
        inProgress: summary?.en_curso ?? 0,
        pending: Math.max(total - (summary?.aprobadas ?? 0) - (summary?.reprobadas ?? 0) - (summary?.en_curso ?? 0), 0),
        approvedCredits: summary?.creditos_aprobados,
        totalCredits: undefined,
        promedioGeneral: summary?.promedio_general,
      }
    }

    return {
      total,
      approved,
      failed,
      inProgress,
      pending: Math.max(total - approved - failed - inProgress, 0),
      approvedCredits: approvedCreditTotal,
      totalCredits: creditTotal,
      promedioGeneral: finalCount > 0 ? finalSum / finalCount : summary?.promedio_general,
    }
  }, [academicRows, curriculumRows.length, recordTotal, summary])
  const totalSubjects = academicMetrics.total
  const approvedSubjects = academicMetrics.approved
  const inProgressSubjects = academicMetrics.inProgress
  const failedSubjects = academicMetrics.failed
  const pendingSubjects = academicMetrics.pending
  const missingSubjects = Math.max(totalSubjects - approvedSubjects, 0)
  const progress = totalSubjects > 0 ? (approvedSubjects / totalSubjects) * 100 : 0
  const approvedCredits = academicMetrics.approvedCredits
  const totalCredits = academicMetrics.totalCredits
  const promedioGeneral = academicMetrics.promedioGeneral

  async function loadRecord(nextApprovedOnly: boolean = approvedOnly) {
    setLoading(true)
    setError('')
    try {
      const payload = await fetchPortalStudentRecord(nextApprovedOnly)
      setRecord(payload)
    } catch (apiError) {
      setRecord(null)
      setError(apiError instanceof Error ? apiError.message : 'No se pudo consultar las calificaciones')
    } finally {
      setLoading(false)
    }
  }

  async function downloadSelectedPeriod() {
    if (!selectedPeriod) return
    setDownloadLoading(true)
    setError('')
    try {
      const blob = await downloadPortalStudentPdf('calificaciones', selectedPeriod)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const periodName = selectedPeriod.replace(/[^a-z0-9_-]+/gi, '-')
      link.href = url
      link.download = `calificaciones-${student?.codigo_estud || 'estudiante'}-${periodName}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar las calificaciones')
    } finally {
      setDownloadLoading(false)
    }
  }

  async function downloadAcademicMap() {
    setDownloadLoading(true)
    setError('')
    try {
      const blob = await downloadPortalStudentPdf('academica')
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `malla-academica-${student?.codigo_estud || 'estudiante'}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'No se pudo descargar la malla academica')
    } finally {
      setDownloadLoading(false)
    }
  }

  useEffect(() => {
    void loadRecord(false)
  }, [])

  useEffect(() => {
    if (periodOptions.length === 0) {
      setSelectedPeriod('')
      return
    }
    if (selectedPeriod && !periodOptions.some((period) => period.code === selectedPeriod)) {
      setSelectedPeriod('')
    }
  }, [periodOptions, selectedPeriod])

  useEffect(() => {
    setExpandedRows(new Set())
  }, [selectedPeriod, approvedOnly])

  function toggleApprovedOnly() {
    const nextValue = !approvedOnly
    setApprovedOnly(nextValue)
    void loadRecord(nextValue)
  }

  function renderActionCard(section: PortalStudentSection, icon: string, title: string, subtitle: string, value: string) {
    return (
      <button
        type="button"
        className={activeSection === section ? 'portal-nav-card portal-nav-card--active' : 'portal-nav-card'}
        onClick={() => onSectionChange(section)}
      >
        <span className="portal-nav-card__icon" aria-hidden="true">{icon}</span>
        <span>
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
        <em>{value}</em>
      </button>
    )
  }

  function recordRowKey(item: PortalAcademicRecordItem, index: number) {
    return [
      item.codigo_periodo,
      item.cod_anio_basica,
      item.codigo_materia,
      item.paralelo,
      item.num_matricula,
      item.num_grupo,
      index,
    ].join('|')
  }

  function toggleExpandedRow(rowKey: string) {
    setExpandedRows((current) => {
      const next = new Set(current)
      if (next.has(rowKey)) {
        next.delete(rowKey)
      } else {
        next.add(rowKey)
      }
      return next
    })
  }

  function statusFromFinal(item: PortalAcademicRecordItem) {
    if (item.promedio_final === null || item.promedio_final === undefined || Number.isNaN(item.promedio_final)) return 'En curso'
    return item.promedio_final >= 7 ? 'Aprobada' : 'Reprobada'
  }

  function partialBadge(value: number | null | undefined) {
    if (value === null || value === undefined || Number.isNaN(value)) return <span className="portal-partial-status">Sin nota</span>
    return (
      <span className={value >= 7 ? 'portal-partial-status portal-partial-status--ok' : 'portal-partial-status portal-partial-status--danger'}>
        {value >= 7 ? 'Aprobado' : 'Reprobado'}
      </span>
    )
  }

  function detailValue(label: string, value: number | null | undefined) {
    return (
      <span>
        <small>{label}</small>
        <strong>{numberText(value)}</strong>
      </span>
    )
  }

  function renderGradeDetail(item: PortalAcademicRecordItem) {
    if (isHomologation(item)) {
      return (
        <div className="portal-grade-detail-grid portal-grade-detail-grid--homo">
          <article>
            <h3>Homologacion</h3>
            <div>
              {detailValue('Teoria', item.teoria_homo)}
              {detailValue('Practica', item.practica_homo)}
              {detailValue('Promedio final', item.promedio_final)}
            </div>
            {partialBadge(item.promedio_final)}
          </article>
        </div>
      )
    }

    return (
      <div className="portal-grade-detail-grid">
        <article>
          <h3>Primer parcial</h3>
          <div>
            {detailValue('Tareas', item.p1_tareas)}
            {detailValue('Proyectos', item.p1_proyectos)}
            {detailValue('Examen', item.p1_examen)}
            {detailValue('Promedio', item.prom_p1)}
          </div>
          {partialBadge(item.prom_p1)}
        </article>
        <article>
          <h3>Segundo parcial</h3>
          <div>
            {detailValue('Tareas', item.p2_tareas)}
            {detailValue('Proyectos', item.p2_proyectos)}
            {detailValue('Examen', item.p2_examen)}
            {detailValue('Promedio', item.prom_p2)}
          </div>
          {partialBadge(item.prom_p2)}
        </article>
        <article>
          <h3>Tercer parcial</h3>
          <div>
            {detailValue('Tareas', item.p3_tareas)}
            {detailValue('Proyectos', item.p3_proyectos)}
            {detailValue('Examen', item.p3_examen)}
            {detailValue('Promedio', item.prom_p3)}
          </div>
          {partialBadge(item.prom_p3)}
        </article>
      </div>
    )
  }

  function renderAcademicOverview() {
    return (
      <>
        <div className="portal-dashboard-overview">
          <article className="portal-dashboard-main">
            <span>Avance general</span>
            <strong>{numberText(progress, 1)}%</strong>
            <div className="portal-progress-bar portal-progress-bar--wide">
              <i style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }} />
            </div>
            <p>{approvedSubjects} de {totalSubjects} materias aprobadas en la malla.</p>
          </article>
          <article className="portal-dashboard-info">
            <span>Promedio general</span>
            <strong>{numberText(promedioGeneral)}</strong>
            <p>Calculado con materias que ya tienen nota final.</p>
          </article>
          <article className="portal-dashboard-info">
            <span>Creditos</span>
            <strong>{numberText(approvedCredits, 1)} / {numberText(totalCredits, 1)}</strong>
            <p>Aprobados frente al total de la malla.</p>
          </article>
        </div>

        <div className="portal-dashboard-breakdown portal-dashboard-breakdown--detailed">
          <div>
            <span>Malla curricular</span>
            <strong>{totalSubjects}</strong>
            <small>Materias a cursar</small>
          </div>
          <div>
            <span>Aprobadas</span>
            <strong>{approvedSubjects}</strong>
            <small>{numberText(progress, 1)}% cumplimiento</small>
          </div>
          <div>
            <span>En curso</span>
            <strong>{inProgressSubjects}</strong>
            <small>Materias matriculadas sin cierre final</small>
          </div>
          <div>
            <span>Reprobadas</span>
            <strong>{failedSubjects}</strong>
            <small>Menor a 7/10</small>
          </div>
          <div>
            <span>Pendientes</span>
            <strong>{pendingSubjects}</strong>
            <small>No cursadas o sin registro</small>
          </div>
        </div>
      </>
    )
  }

  return (
    <div className="student-dashboard portal-page portal-student-page">
      <header className="student-hero portal-student-hero">
        <div>
          <p className="eyebrow">Portal estudiante</p>
          <h1>Panel academico del estudiante</h1>
          <p>{student?.nombre_estudiante || displayName}</p>
          <small>{careerName}</small>
        </div>
        <div className="portal-progress-card" aria-label="Avance de carrera">
          <span>Avance de carrera</span>
          <strong>{numberText(progress, 1)}%</strong>
          <div className="portal-progress-bar">
            <i style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }} />
          </div>
          <small>{approvedSubjects} de {totalSubjects} materias aprobadas</small>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}
      {loading ? <p className="form-success">Consultando informacion academica...</p> : null}

      {activeSection === 'dashboard' ? (
        <section className="student-card portal-record-card">
          <div className="section-title">
            <div>
              <span>Dashboard academico</span>
              <h2>Avance por malla</h2>
            </div>
          </div>

          {renderAcademicOverview()}

          <div className="portal-dashboard-shortcuts">
            <div>
              <span>Accesos rapidos</span>
              <strong>Consultas disponibles</strong>
            </div>
            <section className="portal-nav-grid portal-nav-grid--dashboard" aria-label="Opciones academicas del estudiante">
              {renderActionCard('curricular', 'MC', 'Malla curricular', 'Materias, codigos, niveles y creditos.', integerText(totalSubjects))}
              {renderActionCard('academica', 'MA', 'Malla academica', 'Aprobadas, pendientes y notas finales.', integerText(missingSubjects))}
              {renderActionCard('notas', 'NT', 'Calificaciones', 'Matriculas, parciales y HOMO.', integerText(summary?.total_materias))}
            </section>
          </div>
        </section>
      ) : null}

      {activeSection === 'curricular' ? (
        <section className="student-card portal-record-card">
          <div className="section-title">
            <div>
              <span>Malla curricular</span>
              <h2>Materias a cursar</h2>
              <small className="portal-section-subtitle">Carrera: {careerName}</small>
            </div>
            <span>{curriculumRows.length} materia(s)</span>
          </div>
          <div className="excel-table-wrap portal-table-wrap portal-table-wrap--tall">
            <table className="matricula-table portal-curriculum-table">
              <thead>
                <tr>
                  <th>Nivel</th>
                  <th>Codigo materia</th>
                  <th>Codigo interno</th>
                  <th>Materia</th>
                  <th>Creditos</th>
                  <th>Horas</th>
                  <th>Malla</th>
                </tr>
              </thead>
              <tbody>
                {curriculumRows.map((item, index) => (
                  <tr key={`${item.codigo_materia}-${index}`}>
                    <td>{item.semestre ?? '-'}</td>
                    <td><strong>{curriculumCode(item)}</strong></td>
                    <td>{item.codigo_materia || '-'}</td>
                    <td>{item.nombre_materia || '-'}</td>
                    <td>{numberText(item.creditos)}</td>
                    <td>{numberText(inferredHours(item), 0)}</td>
                    <td>{inferredMalla(item) ?? '-'}</td>
                  </tr>
                ))}
                {!loading && curriculumRows.length === 0 ? (
                  <tr>
                    <td colSpan={7}>No hay materias de malla curricular para mostrar.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeSection === 'academica' ? (
        <section className="student-card portal-record-card">
          <div className="section-title">
            <div>
              <span>Malla academica</span>
              <h2>Malla y calificaciones consolidadas</h2>
              <small className="portal-section-subtitle">Carrera: {careerName}</small>
            </div>
            <div className="portal-actions">
              <span>{numberText(progress, 1)}% avance</span>
              <button type="button" className="primary-action" onClick={downloadAcademicMap} disabled={loading || downloadLoading}>
                {downloadLoading ? 'Descargando...' : 'Descargar PDF'}
              </button>
            </div>
          </div>
          <div className="excel-table-wrap portal-table-wrap portal-table-wrap--tall portal-table-wrap--no-scroll">
            <table className="matricula-table portal-academic-map-table">
              <thead>
                <tr>
                  <th>Nivel</th>
                  <th>Codigo materia</th>
                  <th>Materia</th>
                  <th>Creditos</th>
                  <th>Esquema</th>
                  <th>HOMO</th>
                  <th>Prom. 1</th>
                  <th>Prom. 2</th>
                  <th>Prom. 3</th>
                  <th>Final</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {academicRows.map((item, index) => {
                  const homo = isHomologationValue(item)
                  return (
                  <tr key={`${item.codigo_materia}-${index}`}>
                    <td>{item.semestre ?? '-'}</td>
                    <td>
                      <strong>{curriculumCode(item)}</strong>
                      {item.codigo_materia ? <small>{item.codigo_materia}</small> : null}
                    </td>
                    <td>{item.nombre_materia || '-'}</td>
                    <td>{numberText(item.creditos)}</td>
                    <td>{item.esquema_calificacion || (homo ? 'HOMOLOGACION' : 'REGULAR')}</td>
                    <td>{homo ? `T: ${numberText(item.teoria_homo)} / P: ${numberText(item.practica_homo)}` : '-'}</td>
                    <td>{homo ? '-' : numberText(item.prom_p1)}</td>
                    <td>{homo ? '-' : numberText(item.prom_p2)}</td>
                    <td>{homo ? '-' : numberText(item.prom_p3)}</td>
                    <td>{item.estado_academico === 'Pendiente' ? '0' : numberText(item.promedio_final)}</td>
                    <td><span className={statusClass(item.estado_academico)}>{item.estado_academico || '-'}</span></td>
                  </tr>
                  )
                })}
                {!loading && academicRows.length === 0 ? (
                  <tr>
                    <td colSpan={11}>No hay malla academica para mostrar.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeSection === 'notas' ? (
        <section className="student-card portal-record-card">
          <div className="section-title">
            <div>
              <span>Calificaciones - solo lectura</span>
              <h2>{selectedPeriod ? periodOptions.find((period) => period.code === selectedPeriod)?.label : 'Seleccione un periodo'}</h2>
              <small className="portal-section-subtitle">Carrera: {careerName}</small>
            </div>
            <div className="portal-actions">
              <label className="portal-period-filter">
                <span>Periodo</span>
                <select value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)} disabled={loading}>
                  <option value="">Seleccione un periodo</option>
                  {periodOptions.map((period) => (
                    <option key={period.code} value={period.code}>{period.label}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="ghost-button" onClick={toggleApprovedOnly} disabled={loading}>
                {approvedOnly ? 'Ver todo' : 'Solo aprobadas'}
              </button>
              <button type="button" className="primary-action" onClick={downloadSelectedPeriod} disabled={loading || downloadLoading || !selectedPeriod}>
                {downloadLoading ? 'Descargando...' : 'Descargar PDF'}
              </button>
            </div>
          </div>

          <div className="excel-table-wrap portal-table-wrap portal-table-wrap--tall portal-table-wrap--no-scroll">
            <table className={selectedPeriodIsHomologation ? 'matricula-table portal-record-table portal-record-table--homo' : 'matricula-table portal-record-table'}>
              <thead>
                {selectedPeriodIsHomologation ? (
                  <tr>
                    <th>Detalle</th>
                    <th>Periodo</th>
                    <th>Nivel</th>
                    <th>Materia</th>
                    <th>Esquema</th>
                    <th>Final</th>
                    <th>Estado</th>
                  </tr>
                ) : (
                  <tr>
                    <th>Detalle</th>
                    <th>Periodo</th>
                    <th>Nivel</th>
                    <th>Materia</th>
                    <th>Esquema</th>
                    <th>Prom. 1</th>
                    <th>Prom. 2</th>
                    <th>Prom. 3</th>
                    <th>Final</th>
                    <th>Estado</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {filteredItems.map((item: PortalAcademicRecordItem, index) => {
                  const rowKey = recordRowKey(item, index)
                  const isExpanded = expandedRows.has(rowKey)
                  const rowStatus = statusFromFinal(item)
                  const rowIsHomologation = isHomologation(item)
                  return (
                    <Fragment key={rowKey}>
                      <tr>
                        <td>
                          <button
                            type="button"
                            className={isExpanded ? 'portal-play-button portal-play-button--open' : 'portal-play-button'}
                            onClick={() => toggleExpandedRow(rowKey)}
                            aria-label={isExpanded ? 'Ocultar detalle de parciales' : 'Ver detalle de parciales'}
                          >
                            <span aria-hidden="true">▶</span>
                          </button>
                        </td>
                        <td>{item.detalle_periodo || item.codigo_periodo}</td>
                        <td>{item.semestre ?? '-'}</td>
                        <td>
                          <strong>{item.nombre_materia || item.codigo_materia}</strong>
                          {item.cod_materia ? <small>{item.cod_materia}</small> : null}
                        </td>
                        <td>{item.esquema_calificacion || (rowIsHomologation ? 'HOMOLOGACION' : 'REGULAR')}</td>
                        {!selectedPeriodIsHomologation ? (
                          <>
                            <td>{rowIsHomologation ? '-' : numberText(item.prom_p1)}</td>
                            <td>{rowIsHomologation ? '-' : numberText(item.prom_p2)}</td>
                            <td>{rowIsHomologation ? '-' : numberText(item.prom_p3)}</td>
                          </>
                        ) : null}
                        <td>{numberText(item.promedio_final)}</td>
                        <td><span className={statusClass(rowStatus)}>{rowStatus}</span></td>
                      </tr>
                      {isExpanded ? (
                        <tr className="portal-record-detail-row">
                          <td colSpan={selectedPeriodIsHomologation ? 7 : 10}>{renderGradeDetail(item)}</td>
                        </tr>
                      ) : null}
                    </Fragment>
                  )
                })}
                {!loading && selectedPeriod && filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={selectedPeriodIsHomologation ? 7 : 10}>No hay materias para mostrar en el periodo seleccionado.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}
