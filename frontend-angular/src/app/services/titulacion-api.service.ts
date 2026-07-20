import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ActaGrado,
  AsignarResponsableComplexivoRequest,
  AsignarTribunalDefensaRequest,
  CalificacionConsolidada,
  CalificacionEvaluador,
  CrearDefensaGradoRequest,
  CrearGrupoComplexivoRequest,
  CrearGrupoComplexivoTeamsRequest,
  DashboardResumen,
  DocumentoTitulacionHistorial,
  DocumentoTitulacion,
  EstudianteApto,
  EstudiantesAptosFiltro,
  GrupoComplexivoTeams,
  GenerarActaRequest,
  GrupoTitulacion,
  Habilitacion,
  HabilitarEstudianteRequest,
  PagedResult,
  RegistrarCalificacionEvaluadorRequest,
  ResponsableAsignado,
  ResponsableTitulacion,
  TituloTitulacion,
  UpsertResponsableRequest
} from '../models/titulacion.models';

function paramsFrom(source: object): HttpParams {
  let params = new HttpParams();
  Object.entries(source as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params = params.set(key, String(value));
    }
  });
  return params;
}

@Injectable({ providedIn: 'root' })
export class TitulacionDashboardService {
  private readonly http = inject(HttpClient);
  getResumen(): Observable<DashboardResumen> {
    return this.http.get<DashboardResumen>('/api/titulacion/dashboard/resumen');
  }
}

@Injectable({ providedIn: 'root' })
export class EstudiantesAptosService {
  private readonly http = inject(HttpClient);
  get(filtro: EstudiantesAptosFiltro = {}): Observable<PagedResult<EstudianteApto>> {
    return this.http.get<PagedResult<EstudianteApto>>('/api/titulacion/estudiantes-aptos', {
      params: paramsFrom(filtro)
    });
  }
  getByCedula(cedula: string): Observable<EstudianteApto> {
    return this.http.get<EstudianteApto>(`/api/titulacion/estudiantes-aptos/${cedula}`);
  }
  sincronizar(): Observable<{ estudiantesAptos: number; estudiantesPendientes: number; mensaje: string }> {
    return this.http.post<{ estudiantesAptos: number; estudiantesPendientes: number; mensaje: string }>(
      '/api/titulacion/estudiantes-aptos/sincronizar',
      {}
    );
  }
}

@Injectable({ providedIn: 'root' })
export class HabilitacionTitulacionService {
  private readonly http = inject(HttpClient);
  habilitar(request: HabilitarEstudianteRequest): Observable<Habilitacion> {
    return this.http.post<Habilitacion>('/api/titulacion/habilitaciones', request);
  }
  get(): Observable<Habilitacion[]> {
    return this.http.get<Habilitacion[]>('/api/titulacion/habilitaciones');
  }
  getById(id: number): Observable<Habilitacion> {
    return this.http.get<Habilitacion>(`/api/titulacion/habilitaciones/${id}`);
  }
  anular(id: number): Observable<void> {
    return this.http.put<void>(`/api/titulacion/habilitaciones/${id}/anular`, {});
  }
}

@Injectable({ providedIn: 'root' })
export class GrupoTitulacionService {
  private readonly http = inject(HttpClient);
  crearComplexivo(request: CrearGrupoComplexivoRequest): Observable<GrupoTitulacion> {
    return this.http.post<GrupoTitulacion>('/api/titulacion/grupos/complexivo', request);
  }
  crearComplexivoTeams(request: CrearGrupoComplexivoTeamsRequest): Observable<GrupoComplexivoTeams> {
    return this.http.post<GrupoComplexivoTeams>('/api/titulacion/grupos/complexivo/teams', request);
  }
  crearDefensa(request: CrearDefensaGradoRequest): Observable<GrupoTitulacion> {
    return this.http.post<GrupoTitulacion>('/api/titulacion/grupos/defensa-grado', request);
  }
  get(mecanismo?: string): Observable<GrupoTitulacion[]> {
    return this.http.get<GrupoTitulacion[]>('/api/titulacion/grupos', {
      params: paramsFrom({ mecanismo })
    });
  }
  getById(id: number): Observable<GrupoTitulacion> {
    return this.http.get<GrupoTitulacion>(`/api/titulacion/grupos/${id}`);
  }
  agregarEstudiante(id: number, request: { cedula: string; expedienteId?: number | null; ordenIntegrante?: number | null }): Observable<GrupoTitulacion> {
    return this.http.post<GrupoTitulacion>(`/api/titulacion/grupos/${id}/estudiantes`, request);
  }
  eliminarEstudiante(id: number, cedula: string): Observable<void> {
    return this.http.delete<void>(`/api/titulacion/grupos/${id}/estudiantes/${cedula}`);
  }
  actualizarProgramacion(id: number, request: CrearGrupoComplexivoRequest): Observable<GrupoTitulacion> {
    return this.http.put<GrupoTitulacion>(`/api/titulacion/grupos/${id}/programacion`, request);
  }
}

@Injectable({ providedIn: 'root' })
export class ResponsablesTitulacionService {
  private readonly http = inject(HttpClient);
  get(rolCodigo?: string): Observable<ResponsableTitulacion[]> {
    return this.http.get<ResponsableTitulacion[]>('/api/titulacion/responsables', {
      params: paramsFrom({ rolCodigo })
    });
  }
  crear(request: UpsertResponsableRequest): Observable<ResponsableTitulacion> {
    return this.http.post<ResponsableTitulacion>('/api/titulacion/responsables', request);
  }
  actualizar(id: number, request: UpsertResponsableRequest): Observable<ResponsableTitulacion> {
    return this.http.put<ResponsableTitulacion>(`/api/titulacion/responsables/${id}`, request);
  }
  inactivar(id: number): Observable<void> {
    return this.http.delete<void>(`/api/titulacion/responsables/${id}`);
  }
  asignarComplexivo(grupoId: number, request: AsignarResponsableComplexivoRequest): Observable<ResponsableAsignado[]> {
    return this.http.post<ResponsableAsignado[]>(`/api/titulacion/grupos/${grupoId}/responsable-complexivo`, request);
  }
  asignarTribunal(grupoId: number, request: AsignarTribunalDefensaRequest): Observable<ResponsableAsignado[]> {
    return this.http.post<ResponsableAsignado[]>(`/api/titulacion/grupos/${grupoId}/tribunal-defensa`, request);
  }
  getAsignados(grupoId: number): Observable<ResponsableAsignado[]> {
    return this.http.get<ResponsableAsignado[]>(`/api/titulacion/grupos/${grupoId}/responsables`);
  }
}

@Injectable({ providedIn: 'root' })
export class CalificacionesTitulacionService {
  private readonly http = inject(HttpClient);
  getEvaluadores(expedienteId: number): Observable<CalificacionEvaluador[]> {
    return this.http.get<CalificacionEvaluador[]>(`/api/titulacion/expedientes/${expedienteId}/calificaciones`);
  }
  registrarEvaluador(expedienteId: number, request: RegistrarCalificacionEvaluadorRequest): Observable<CalificacionConsolidada> {
    return this.http.post<CalificacionConsolidada>(`/api/titulacion/expedientes/${expedienteId}/calificaciones/evaluador`, request);
  }
  consolidar(expedienteId: number, grupoId: number): Observable<CalificacionConsolidada> {
    return this.http.post<CalificacionConsolidada>(`/api/titulacion/expedientes/${expedienteId}/calificaciones/consolidar`, null, {
      params: paramsFrom({ grupoId })
    });
  }
  getConsolidado(expedienteId: number): Observable<CalificacionConsolidada> {
    return this.http.get<CalificacionConsolidada>(`/api/titulacion/expedientes/${expedienteId}/calificaciones/consolidado`);
  }
}

@Injectable({ providedIn: 'root' })
export class DocumentosTitulacionService {
  private readonly http = inject(HttpClient);
  upload(data: FormData): Observable<DocumentoTitulacion> {
    return this.http.post<DocumentoTitulacion>('/api/titulacion/documentos/upload', data);
  }
  getByExpediente(expedienteId: number): Observable<DocumentoTitulacion[]> {
    return this.http.get<DocumentoTitulacion[]>(`/api/titulacion/expedientes/${expedienteId}/documentos`);
  }
  getHistorial(documentoId: number): Observable<DocumentoTitulacionHistorial[]> {
    return this.http.get<DocumentoTitulacionHistorial[]>(`/api/titulacion/documentos/${documentoId}/historial`);
  }
  validar(documentoId: number): Observable<void> {
    return this.http.put<void>(`/api/titulacion/documentos/${documentoId}/validar`, {});
  }
  observar(documentoId: number, observacion: string): Observable<void> {
    return this.http.put<void>(`/api/titulacion/documentos/${documentoId}/observar`, JSON.stringify(observacion), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

@Injectable({ providedIn: 'root' })
export class TitulosTitulacionService {
  private readonly http = inject(HttpClient);
  uploadRegistro(data: FormData): Observable<DocumentoTitulacion> {
    return this.http.post<DocumentoTitulacion>('/api/titulacion/titulos/registro/upload', data);
  }
  uploadIntec(data: FormData): Observable<DocumentoTitulacion> {
    return this.http.post<DocumentoTitulacion>('/api/titulacion/titulos/intec/upload', data);
  }
  get(search?: string): Observable<TituloTitulacion[]> {
    return this.http.get<TituloTitulacion[]>('/api/titulacion/titulos', {
      params: paramsFrom({ search })
    });
  }
  getByCedula(cedula: string): Observable<TituloTitulacion[]> {
    return this.http.get<TituloTitulacion[]>(`/api/titulacion/titulos/${cedula}`);
  }
}

@Injectable({ providedIn: 'root' })
export class ActasGradoService {
  private readonly http = inject(HttpClient);
  generar(expedienteId: number, request: GenerarActaRequest): Observable<ActaGrado> {
    return this.http.post<ActaGrado>(`/api/titulacion/expedientes/${expedienteId}/acta/generar`, request);
  }
  getByExpediente(expedienteId: number): Observable<ActaGrado> {
    return this.http.get<ActaGrado>(`/api/titulacion/expedientes/${expedienteId}/acta`);
  }
  get(): Observable<ActaGrado[]> {
    return this.http.get<ActaGrado[]>('/api/titulacion/actas');
  }
  descargarPdf(actaId: number): Observable<Blob> {
    return this.http.get(`/api/titulacion/actas/${actaId}/pdf`, { responseType: 'blob' });
  }
  anular(actaId: number, motivo: string): Observable<void> {
    return this.http.put<void>(`/api/titulacion/actas/${actaId}/anular`, { motivo });
  }
}

@Injectable({ providedIn: 'root' })
export class ReportesTitulacionService {
  exportarCsv(filename: string, rows: Record<string, unknown>[]): void {
    const headers = Object.keys(rows[0] ?? {});
    const body = rows.map((row) => headers.map((key) => JSON.stringify(row[key] ?? '')).join(','));
    const blob = new Blob([[headers.join(','), ...body].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
}
