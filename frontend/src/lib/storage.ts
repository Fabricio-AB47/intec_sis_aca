import type { Page } from '../types/app'

const PAGE_STORAGE_KEY = 'reporteria.active-page'

function isPage(value: string): value is Page {
  return (
    value === 'dashboard' ||
    value === 'teams' ||
    value === 'teams-matricula' ||
    value === 'matricula' ||
    value === 'matricula-acad' ||
    value === 'matricula-docente' ||
    value === 'estado-docente' ||
    value === 'senescyt-estudiantes' ||
    value === 'actualizar-datos-estudiante' ||
    value === 'preinscripcion' ||
    value === 'reporteria-carreras' ||
    value === 'reporteria-integral' ||
    value === 'reportes-individuales' ||
    value === 'gestion-sisacademico' ||
    value === 'periodo-academico' ||
    value === 'periodo-matriculados' ||
    value === 'ingreso-ventas' ||
    value === 'cruce-datos' ||
    value === 'validar-excel' ||
    value === 'rango-edades' ||
    value === 'certificados' ||
    value === 'renombrar-certificados' ||
    value === 'credenciales' ||
    value === 'correos-masivos' ||
    value === 'carnet-institucional' ||
    value === 'evaluacion-docente' ||
    value === 'portal-estudiante' ||
    value === 'portal-docente'
  )
}

export function readStoredPage(): Page {
  try {
    const raw = globalThis.localStorage.getItem(PAGE_STORAGE_KEY)
    return raw && isPage(raw) ? raw : 'dashboard'
  } catch {
    return 'dashboard'
  }
}

export function writeStoredPage(page: Page): void {
  try {
    globalThis.localStorage.setItem(PAGE_STORAGE_KEY, page)
  } catch {
    // Ignore storage errors and keep the app usable.
  }
}

export function clearStoredPage(): void {
  try {
    globalThis.localStorage.removeItem(PAGE_STORAGE_KEY)
  } catch {
    // Ignore storage errors and keep the app usable.
  }
}
