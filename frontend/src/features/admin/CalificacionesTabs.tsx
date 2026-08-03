type CalificacionesTabsProps = {
  active: 'asignaturas' | 'idiomas'
  onOpenSubjects?: () => void
  onOpenLanguages?: () => void
}

export function CalificacionesTabs({
  active,
  onOpenSubjects,
  onOpenLanguages,
}: Readonly<CalificacionesTabsProps>) {
  if (!onOpenSubjects && !onOpenLanguages) return null

  return (
    <nav className="grade-area-tabs" role="tablist" aria-label="Secciones de calificaciones">
      <button
        type="button"
        role="tab"
        className={active === 'asignaturas' ? 'is-active' : ''}
        aria-selected={active === 'asignaturas'}
        onClick={onOpenSubjects}
        disabled={!onOpenSubjects && active !== 'asignaturas'}
      >
        Notas por asignatura
      </button>
      <button
        type="button"
        role="tab"
        className={active === 'idiomas' ? 'is-active' : ''}
        aria-selected={active === 'idiomas'}
        onClick={onOpenLanguages}
        disabled={!onOpenLanguages && active !== 'idiomas'}
      >
        Idiomas
      </button>
    </nav>
  )
}
