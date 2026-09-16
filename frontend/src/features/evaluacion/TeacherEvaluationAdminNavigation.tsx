import { screenPermissionAllowsPage } from '../../lib/screenAccess'
import type { Page, ScreenPermissionCode } from '../../types/app'

type TeacherEvaluationAdminNavigationProps = {
  activePage: Page
  permissions: ScreenPermissionCode[] | null
  onOpenProgress: () => void
  onOpenReports: () => void
  onOpenHistory: () => void
}

export function TeacherEvaluationAdminNavigation({
  activePage,
  permissions,
  onOpenProgress,
  onOpenReports,
  onOpenHistory,
}: TeacherEvaluationAdminNavigationProps) {
  const items = [
    { page: 'evaluacion-docente-avance' as const, label: 'Avance y ponderación', action: onOpenProgress },
    { page: 'evaluacion-docente-reportes' as const, label: 'Documentos de evaluación', action: onOpenReports },
    { page: 'evaluacion-docente-historicas' as const, label: 'Autoevaluaciones históricas', action: onOpenHistory },
  ].filter((item) => screenPermissionAllowsPage(permissions, item.page))
  const currentPage = activePage === 'evaluacion-docente-admin' ? 'evaluacion-docente-avance' : activePage

  if (!items.length) return null

  return (
    <nav className="teacher-evaluation-admin-navigation" aria-label="Apartados de Desempeño">
      <span>Desempeño</span>
      <div>
        {items.map((item) => (
          <button
            key={item.page}
            type="button"
            aria-current={currentPage === item.page ? 'page' : undefined}
            onClick={item.action}
          >
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
