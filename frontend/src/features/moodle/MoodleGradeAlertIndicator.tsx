import { useEffect, useState } from 'react'

import {
  fetchMoodleGradeAlerts,
  MOODLE_GRADE_ALERT_INVALIDATED_EVENT,
} from '../../lib/api'
import type { MoodleGradeAlertResponse } from '../../types/app'

type MoodleGradeAlertIndicatorProps = {
  role: string
  onOpen: () => void
}

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

export function MoodleGradeAlertIndicator({ role, onOpen }: MoodleGradeAlertIndicatorProps) {
  const [data, setData] = useState<MoodleGradeAlertResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    const load = async (refresh = false) => {
      try {
        const response = await fetchMoodleGradeAlerts(refresh)
        if (active) {
          setData(response)
          setError('')
        }
      } catch {
        if (active) {
          setError('No se pudieron actualizar las alertas de calificación.')
        }
      }
    }

    void load()
    const refreshAlerts = () => void load(true)
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void load(false)
    }
    const intervalId = window.setInterval(refreshAlerts, REFRESH_INTERVAL_MS)
    window.addEventListener(MOODLE_GRADE_ALERT_INVALIDATED_EVENT, refreshAlerts)
    window.addEventListener('focus', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      active = false
      window.clearInterval(intervalId)
      window.removeEventListener(MOODLE_GRADE_ALERT_INVALIDATED_EVENT, refreshAlerts)
      window.removeEventListener('focus', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [role])

  if (!data && error) {
    return (
      <button
        type="button"
        className="moodle-grade-alert-indicator moodle-grade-alert-indicator--error"
        aria-label={`${error} Abrir alertas de calificación.`}
        onClick={onOpen}
      >
        <span className="moodle-grade-alert-indicator__count" aria-hidden="true">!</span>
        <div className="moodle-grade-alert-indicator__copy">
          <strong>{error}</strong>
          <span>Abra la bandeja para revisar la conexión con Moodle e INTECBDD.</span>
        </div>
        <span className="moodle-grade-alert-indicator__action" aria-hidden="true">
          Revisar conexión
        </span>
      </button>
    )
  }

  if (!data || data.summary.total === 0) return null

  const isTeacher = role.toUpperCase() === 'DOCENTE'
  const primaryCount = data.summary.total
  const title = isTeacher
    ? `${primaryCount} alerta(s) de calificación`
    : `${primaryCount} advertencia(s) académica(s)`
  const detail = isTeacher
    ? `${data.summary.students} estudiante(s): ${data.summary.ungraded} sin calificar y ${data.summary.review} por revisar en sus asignaciones.`
    : `${data.summary.students} estudiante(s) en ${data.summary.courses} curso(s): ${data.summary.missing_intecbdd} pendiente(s) en INTECBDD, ${data.summary.missing_moodle} en Moodle y ${data.summary.data_issues} con datos por corregir.`
  const visibleDetail = error
    ? `${detail} No fue posible confirmar la actualización más reciente.`
    : detail

  return (
    <button
      type="button"
      className="moodle-grade-alert-indicator"
      aria-label={`${title}. ${visibleDetail} Abrir alertas de calificación.`}
      onClick={onOpen}
    >
      <span className="moodle-grade-alert-indicator__count" aria-hidden="true">
        {primaryCount > 99 ? '99+' : primaryCount}
      </span>
      <div className="moodle-grade-alert-indicator__copy">
        <strong>{title}</strong>
        <span>{visibleDetail}</span>
      </div>
      <span className="moodle-grade-alert-indicator__action" aria-hidden="true">
        Revisar alertas
      </span>
    </button>
  )
}
