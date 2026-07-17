import { EstadoVisual } from '../models/titulacion.models';

export function estadoVisual(estado?: string | null): EstadoVisual {
  const value = (estado || '').toUpperCase();
  if (['VALIDADO', 'APROBADO', 'ACTA_GENERADA', 'TITULO_INTEC_CARGADO', 'TITULO_REGISTRADO', 'OK'].includes(value)) return 'ok';
  if (['PENDIENTE', 'PROGRAMADO', 'HABILITADO', 'CARGADO'].includes(value)) return 'info';
  if (['OBSERVADO', 'DOCUMENTOS_PENDIENTES'].includes(value)) return 'warn';
  if (['ANULADO', 'RECHAZADO', 'NO_APTO'].includes(value)) return 'error';
  return 'muted';
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
