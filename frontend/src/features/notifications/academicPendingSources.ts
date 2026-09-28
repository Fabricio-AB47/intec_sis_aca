import { fetchAcademicPendingRequests, fetchSecretariaCandidates } from '../../lib/api'
import type { ScreenPermissionCode } from '../../types/app'

export type AdministrativeSource = 'secretaria' | 'career' | 'modality'
export type PendingItem = {
  id: number
  student: string
  identification: string
  career: string
  period: string
  pending: string
}
export type PendingPage = { total: number; page: number; pages: number; items: PendingItem[] }
export type QueueSource = { key: AdministrativeSource; title: string; unit: string; permission: ScreenPermissionCode }

export const ADMINISTRATIVE_SOURCES: QueueSource[] = [
  { key: 'secretaria', title: 'Documentación de Secretaría', unit: 'estudiantes con documentos faltantes', permission: 'secretaria-general' },
  { key: 'career', title: 'Cambio de carrera', unit: 'solicitudes pendientes de revisión o aplicación', permission: 'solicitudes-cambio-carrera' },
  { key: 'modality', title: 'Cambio de modalidad', unit: 'solicitudes pendientes de revisión o aplicación', permission: 'solicitudes-cambio-modalidad' },
]

export async function loadAdministrativeSource(source: AdministrativeSource, query: string, page: number, signal: AbortSignal): Promise<PendingPage> {
  if (source === 'secretaria') {
    const result = await fetchSecretariaCandidates({ search: query, page, pageSize: 10, onlyMissingDocuments: true, signal })
    if (!Array.isArray(result.items) || !Number.isInteger(result.total)) throw new Error('Respuesta documental incompleta.')
    return { total: result.total, page: result.page, pages: result.total_pages, items: result.items.map((item) => ({
      id: item.codigo_estud, student: item.apellidos_nombres, identification: item.numero_identificacion,
      career: item.nombre_carrera, period: item.nombre_periodo,
      pending: `${item.secretaria?.missing ?? 'Sin verificar'} documentos faltantes`,
    })) }
  }
  const result = await fetchAcademicPendingRequests(source, { query, page, pageSize: 10, signal })
  if (!Array.isArray(result.items) || !Number.isInteger(result.total)) throw new Error('Respuesta de solicitudes incompleta.')
  return { total: result.total, page: result.page, pages: result.total_pages, items: result.items.map((item) => ({
    id: item.id, student: item.student, identification: item.identification, career: item.career,
    period: item.period, pending: item.state === 'APROBADA' ? 'Aprobada; falta aplicar' : 'Falta revisar',
  })) }
}
