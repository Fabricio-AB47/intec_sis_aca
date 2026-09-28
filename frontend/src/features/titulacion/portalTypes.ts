export type MecanismoTitulacion = 'EXAMEN_COMPLEXIVO' | 'DEFENSA_GRADO';
export type EstadoVisual = 'ok' | 'warn' | 'error' | 'info' | 'muted';

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface DashboardResumen {
  estudiantesAptos: number;
  estudiantesHabilitados: number;
  examenesComplexivosProgramados: number;
  defensasProgramadas: number;
  actasGeneradas: number;
  titulosRegistradosCargados: number;
  titulosIntecCargados: number;
  expedientesConDocumentosPendientes: number;
  calificacionesPendientes: number;
}

export interface EstudianteApto {
  cedula: string;
  codigoEstud?: number | null;
  nombres: string;
  carrera: string;
  codigoCarrera: string;
  periodo: string;
  cumpleTituloBachiller: boolean;
  cumpleInglesA2: boolean;
  cumplePracticas: boolean;
  cumpleVinculacion: boolean;
  cumpleMalla: boolean;
  noAdeudaFinanciero: boolean;
  aptoSustentacion: boolean;
  notaAsignaturas?: number | null;
  equivalencia80?: number | null;
  puedeHabilitar: boolean;
  motivoNoApto?: string | null;
  estado?: string | null;
  mecanismoSugerido?: string | null;
}

export interface EstudiantesAptosFiltro {
  carrera?: string;
  periodo?: string;
  cedula?: string;
  nombres?: string;
  estado?: string;
  mecanismoSugerido?: string;
  cumplePracticas?: boolean;
  cumpleVinculacion?: boolean;
  financiero?: boolean;
  malla?: boolean;
  ingles?: boolean;
  page?: number;
  pageSize?: number;
}

export interface HabilitarEstudianteRequest {
  cedula: string;
  mecanismoCodigo: MecanismoTitulacion;
  tema?: string | null;
  fechaProgramada?: string | null;
  horaInicio?: string | null;
  horaFin?: string | null;
  modalidad?: string | null;
  grupoTitulacionId?: number | null;
  observacion?: string | null;
}

export interface Habilitacion {
  habilitacionId: number;
  expedienteId?: number | null;
  numeroIdentificacion: string;
  codigoEstud?: number | null;
  carrera: string;
  codigoCarrera: string;
  codigoPeriodo: string;
  mecanismoCodigo: MecanismoTitulacion;
  estadoCodigo: string;
  fechaHabilitacion: string;
  usuarioHabilitacion: string;
  observacion?: string | null;
}

export interface GrupoTitulacion {
  grupoTitulacionId: number;
  codigoGrupo: string;
  nombreGrupo: string;
  mecanismoCodigo: MecanismoTitulacion;
  tema?: string | null;
  carrera?: string | null;
  codigoCarrera?: string | null;
  fechaProgramada?: string | null;
  horaInicio?: string | null;
  horaFin?: string | null;
  aulaOLink?: string | null;
  modalidad?: string | null;
  estadoCodigo: string;
  maximoIntegrantes: number;
  totalIntegrantes: number;
  estudiantes?: GrupoEstudiante[];
  responsables?: ResponsableAsignado[];
}

export interface GrupoEstudiante {
  grupoTitulacionEstudianteId: number;
  expedienteId: number;
  numeroIdentificacion: string;
  codigoEstud?: number | null;
  ordenIntegrante?: number | null;
  esPrincipal: boolean;
  estadoCodigo: string;
}

export interface CrearGrupoComplexivoRequest {
  codigoGrupo?: string | null;
  tema?: string | null;
  carrera?: string | null;
  codigoCarrera?: string | null;
  fechaProgramada?: string | null;
  horaInicio?: string | null;
  horaFin?: string | null;
  aulaOLink?: string | null;
  modalidad?: string | null;
}

export interface CrearGrupoComplexivoTeamsRequest extends CrearGrupoComplexivoRequest {
  responsableComplexivoId: number;
  evaluadoresIds?: number[];
  organizadorTeams?: string | null;
  correosAsistentes?: string[];
  observacion?: string | null;
}

export interface GrupoComplexivoTeams {
  grupo: GrupoTitulacion;
  responsables: ResponsableAsignado[];
  teamsCreado: boolean;
  teamsJoinUrl?: string | null;
  teamsWebLink?: string | null;
  teamsEventId?: string | null;
}

export interface CrearDefensaGradoRequest extends CrearGrupoComplexivoRequest {
  expedienteId1: number;
  expedienteId2?: number | null;
}

export interface ResponsableTitulacion {
  responsableTitulacionId: number;
  cedula?: string | null;
  nombres: string;
  correo?: string | null;
  cargo?: string | null;
  rolCodigo: string;
  activo: boolean;
}

export interface ResponsableAsignado {
  asignacionId: number;
  grupoTitulacionId: number;
  expedienteId?: number | null;
  responsableTitulacionId: number;
  nombres: string;
  rolCodigo: string;
  orden?: number | null;
  esTribunal: boolean;
}

export interface UpsertResponsableRequest {
  cedula?: string | null;
  nombres: string;
  correo?: string | null;
  cargo?: string | null;
  rolCodigo: string;
}

export interface AsignarTribunalDefensaRequest {
  grupoTitulacionId: number;
  presidenteTribunalId: number;
  vocal1Id: number;
  vocal2Id: number;
  tutorId?: number | null;
  observacion?: string | null;
}

export interface AsignarResponsableComplexivoRequest {
  grupoTitulacionId: number;
  responsableComplexivoId: number;
  evaluadoresIds: number[];
  observacion?: string | null;
}

export interface RegistrarCalificacionEvaluadorRequest {
  expedienteId: number;
  grupoTitulacionId: number;
  responsableTitulacionId: number;
  evaluadorNumero: 1 | 2 | 3;
  notaTrabajoEscrito?: number | null;
  notaDefensaOral?: number | null;
  notaExamenComplexivo?: number | null;
  observacion?: string | null;
  cerrarCalificacion: boolean;
}

export interface CalificacionEvaluador {
  calificacionEvaluadorId: number;
  expedienteId: number;
  grupoTitulacionId: number;
  responsableTitulacionId?: number | null;
  evaluadorNumero: number;
  notaTrabajoEscrito?: number | null;
  notaDefensaOral?: number | null;
  notaExamenComplexivo?: number | null;
  notaTitulacionSobre20?: number | null;
  cerrado: boolean;
  observacion?: string | null;
}

export interface CalificacionConsolidada {
  calificacionConsolidadaId: number;
  expedienteId: number;
  numeroIdentificacion: string;
  notaAsignaturas?: number | null;
  equivalenciaAsignaturas80?: number | null;
  promedioTrabajoEscrito?: number | null;
  promedioDefensaOral?: number | null;
  promedioExamenComplexivo?: number | null;
  notaTitulacionSobre20?: number | null;
  equivalenciaTitulacion20?: number | null;
  notaFinalGrado?: number | null;
  evaluadoresCompletos: boolean;
  aprobado: boolean;
}

export interface DocumentoTitulacion {
  documentoId: number;
  expedienteId?: number | null;
  grupoTitulacionId?: number | null;
  numeroIdentificacion?: string | null;
  tipoDocumentoCodigo: string;
  nombreArchivo: string;
  rutaNube?: string | null;
  urlPublica?: string | null;
  estadoCodigo: string;
  esFirmadoElectronicamente: boolean;
  observacion?: string | null;
  version?: number | null;
  codigoRegistroSenescyt?: string | null;
  fechaRegistroSenescyt?: string | null;
  numeroTituloIntec?: string | null;
  fechaEmisionTitulo?: string | null;
  codigoVerificacionQr?: string | null;
  fechaCarga?: string | null;
  usuarioCarga?: string | null;
}

export interface ActaGrado {
  actaGradoId: number;
  expedienteId: number;
  numeroActa: string;
  numeroIdentificacion: string;
  nombresEstudiante: string;
  carrera?: string | null;
  escuela?: string | null;
  mecanismoCodigo?: MecanismoTitulacion | null;
  tituloOtorgado?: string | null;
  fechaActa?: string | null;
  horaActa?: string | null;
  ciudad?: string | null;
  notaFinalGrado?: number | null;
  rutaActaPdf?: string | null;
  estadoCodigo: string;
  nombreInstitucion?: string | null;
  textoVariableActa?: string | null;
  activo?: boolean;
  motivoAnulacion?: string | null;
}

export interface GenerarActaRequest {
  numeroActa?: string | null;
  fechaActa: string;
  horaActa?: string | null;
  ciudad: string;
  escuela?: string | null;
  autoridadAcademica?: string | null;
  coordinadorAcademico?: string | null;
  docenteEvaluador?: string | null;
  nombreInstitucion?: string | null;
}

export interface TituloTitulacion extends DocumentoTitulacion {
  nombresEstudiante?: string | null;
  carrera?: string | null;
  numeroActa?: string | null;
  numeroActaGrado?: string | null;
}

export interface DocumentoTitulacionHistorial {
  historialId: number;
  documentoTitulacionId: number;
  expedienteId?: number | null;
  tipoDocumentoCodigo: string;
  version?: number | null;
  estadoCodigo?: string | null;
  accion: string;
  observacion?: string | null;
  nombreArchivo?: string | null;
  rutaNube?: string | null;
  urlPublica?: string | null;
  usuarioAccion: string;
  fechaAccion: string;
}
