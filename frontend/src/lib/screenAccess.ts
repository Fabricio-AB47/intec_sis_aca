import type {
  AcademicEnrollmentMode,
  Page,
  PreinscriptionStage,
  ScreenPermissionCode,
} from '../types/app'

export type ActiveScreenContext = {
  matriculaAcadMode?: AcademicEnrollmentMode
  preinscriptionStage?: PreinscriptionStage
  sisAcademicoSection?: string
  reportKey?: string
  registeredTitleType?: string
}

const FLOW_PARENT_PAGES = new Set<Page>([
  'preinscripcion',
  'matricula-acad',
  'gestion-sisacademico',
  'reporteria-integral',
  'reportes-individuales',
  'titulos-registrados',
])

export function screenPermissionAllowsPage(
  permissions: readonly ScreenPermissionCode[] | null | undefined,
  page: Page,
) {
  if (!permissions) return false
  return permissions.some((permission) => (
    permission === page || permission.startsWith(`${page}/`)
  ))
}

export function screenPermissionAllowsCode(
  permissions: readonly ScreenPermissionCode[] | null | undefined,
  permission: ScreenPermissionCode,
) {
  return Boolean(permission && permissions?.includes(permission))
}

export function firstPermissionForPage(
  permissions: readonly ScreenPermissionCode[] | null | undefined,
  page: Page,
) {
  if (!permissions) return null
  return permissions.find((permission) => (
    permission === page || permission.startsWith(`${page}/`)
  )) || null
}

export function screenPermissionForView(page: Page, context: ActiveScreenContext = {}) {
  if (page === 'preinscripcion') return `${page}/${context.preinscriptionStage || 'registro'}`
  if (page === 'matricula-acad') return `${page}/${context.matriculaAcadMode || 'individual'}`
  if (page === 'gestion-sisacademico') {
    return context.sisAcademicoSection ? `${page}/${context.sisAcademicoSection}` : page
  }
  if (page === 'reporteria-integral' || page === 'reportes-individuales') {
    return context.reportKey ? `${page}/${context.reportKey}` : page
  }
  if (page === 'titulos-registrados') {
    const type = context.registeredTitleType === 'intec'
      ? 'institucional'
      : context.registeredTitleType || 'senescyt'
    return `${page}/${type}`
  }
  return page
}

export function pageUsesFlowPermissions(page: Page) {
  return FLOW_PARENT_PAGES.has(page)
}

export function permissionRootPage(permission: ScreenPermissionCode): Page {
  return permission.split('/', 1)[0] as Page
}
