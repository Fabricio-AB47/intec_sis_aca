using Microsoft.AspNetCore.Http;

namespace Titulacion.Contracts;

public sealed class PagedResult<T>
{
    public IReadOnlyList<T> Items { get; init; } = Array.Empty<T>();
    public int Total { get; init; }
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 50;
}

public sealed class DashboardResumenDto
{
    public int EstudiantesAptos { get; init; }
    public int EstudiantesHabilitados { get; init; }
    public int ExamenesComplexivosProgramados { get; init; }
    public int DefensasProgramadas { get; init; }
    public int ActasGeneradas { get; init; }
    public int TitulosRegistradosCargados { get; init; }
    public int TitulosIntecCargados { get; init; }
    public int ExpedientesConDocumentosPendientes { get; init; }
    public int CalificacionesPendientes { get; init; }
}

public sealed class EstudianteAptoDto
{
    public string Cedula { get; set; } = string.Empty;
    public int? CodigoEstud { get; set; }
    public string Nombres { get; set; } = string.Empty;
    public string Carrera { get; set; } = string.Empty;
    public string CodigoCarrera { get; set; } = string.Empty;
    public string Periodo { get; set; } = string.Empty;
    public bool CumpleTituloBachiller { get; set; }
    public bool CumpleInglesA2 { get; set; }
    public bool CumplePracticas { get; set; }
    public bool CumpleVinculacion { get; set; }
    public bool CumpleMalla { get; set; }
    public bool NoAdeudaFinanciero { get; set; }
    public bool AptoSustentacion { get; set; }
    public decimal? NotaAsignaturas { get; set; }
    public decimal? Equivalencia80 { get; set; }
    public bool PuedeHabilitar { get; set; }
    public string MotivoNoApto { get; set; } = string.Empty;
    public string Estado { get; set; } = string.Empty;
    public string MecanismoSugerido { get; set; } = string.Empty;
}

public sealed class EstudianteAptoFiltro
{
    public string? Carrera { get; init; }
    public string? Periodo { get; init; }
    public string? Cedula { get; init; }
    public string? Nombres { get; init; }
    public string? Estado { get; init; }
    public string? MecanismoSugerido { get; init; }
    public bool? CumplePracticas { get; init; }
    public bool? CumpleVinculacion { get; init; }
    public bool? Financiero { get; init; }
    public bool? Malla { get; init; }
    public bool? Ingles { get; init; }
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 50;
}

public sealed class SincronizacionEstudiantesDto
{
    public int EstudiantesAptos { get; init; }
    public int EstudiantesPendientes { get; init; }
    public string Mensaje { get; init; } = string.Empty;
}

public sealed class HabilitarEstudianteRequest
{
    public string Cedula { get; set; } = string.Empty;
    public string MecanismoCodigo { get; set; } = string.Empty;
    public string? Tema { get; set; }
    public DateOnly? FechaProgramada { get; set; }
    public TimeOnly? HoraInicio { get; set; }
    public TimeOnly? HoraFin { get; set; }
    public string? Modalidad { get; set; }
    public long? GrupoTitulacionId { get; set; }
    public string? Observacion { get; set; }
}

public sealed class HabilitacionDto
{
    public long HabilitacionId { get; init; }
    public long? ExpedienteId { get; init; }
    public string NumeroIdentificacion { get; init; } = string.Empty;
    public int? CodigoEstud { get; init; }
    public string Carrera { get; init; } = string.Empty;
    public string CodigoCarrera { get; init; } = string.Empty;
    public string CodigoPeriodo { get; init; } = string.Empty;
    public string MecanismoCodigo { get; init; } = string.Empty;
    public string EstadoCodigo { get; init; } = string.Empty;
    public DateTime FechaHabilitacion { get; init; }
    public string UsuarioHabilitacion { get; init; } = string.Empty;
    public string? Observacion { get; init; }
}

public sealed class GrupoTitulacionDto
{
    public long GrupoTitulacionId { get; init; }
    public string CodigoGrupo { get; init; } = string.Empty;
    public string NombreGrupo { get; init; } = string.Empty;
    public string MecanismoCodigo { get; init; } = string.Empty;
    public string? Tema { get; init; }
    public string? Carrera { get; init; }
    public string? CodigoCarrera { get; init; }
    public DateOnly? FechaProgramada { get; init; }
    public TimeOnly? HoraInicio { get; init; }
    public TimeOnly? HoraFin { get; init; }
    public string? AulaOLink { get; init; }
    public string? Modalidad { get; init; }
    public string EstadoCodigo { get; init; } = string.Empty;
    public int MaximoIntegrantes { get; init; }
    public int TotalIntegrantes { get; init; }
    public IReadOnlyList<GrupoEstudianteDto> Estudiantes { get; set; } = Array.Empty<GrupoEstudianteDto>();
    public IReadOnlyList<ResponsableAsignadoDto> Responsables { get; set; } = Array.Empty<ResponsableAsignadoDto>();
}

public sealed class GrupoEstudianteDto
{
    public long GrupoTitulacionEstudianteId { get; init; }
    public long ExpedienteId { get; init; }
    public string NumeroIdentificacion { get; init; } = string.Empty;
    public int? CodigoEstud { get; init; }
    public int? OrdenIntegrante { get; init; }
    public bool EsPrincipal { get; init; }
    public string EstadoCodigo { get; init; } = string.Empty;
}

public class CrearGrupoComplexivoRequest
{
    public string? CodigoGrupo { get; set; }
    public string? Tema { get; set; }
    public string? Carrera { get; set; }
    public string? CodigoCarrera { get; set; }
    public DateOnly? FechaProgramada { get; set; }
    public TimeOnly? HoraInicio { get; set; }
    public TimeOnly? HoraFin { get; set; }
    public string? AulaOLink { get; set; }
    public string? Modalidad { get; set; }
}

public sealed class CrearGrupoComplexivoTeamsRequest : CrearGrupoComplexivoRequest
{
    public long ResponsableComplexivoId { get; set; }
    public List<long> EvaluadoresIds { get; set; } = new();
    public string? OrganizadorTeams { get; set; }
    public List<string> CorreosAsistentes { get; set; } = new();
    public string? Observacion { get; set; }
}

public sealed class GrupoComplexivoTeamsDto
{
    public GrupoTitulacionDto Grupo { get; init; } = new();
    public IReadOnlyList<ResponsableAsignadoDto> Responsables { get; init; } = Array.Empty<ResponsableAsignadoDto>();
    public bool TeamsCreado { get; init; }
    public string? TeamsJoinUrl { get; init; }
    public string? TeamsWebLink { get; init; }
    public string? TeamsEventId { get; init; }
}

public sealed class TeamsCalendarEventRequest
{
    public string Subject { get; set; } = string.Empty;
    public string? BodyHtml { get; set; }
    public DateOnly Fecha { get; set; }
    public TimeOnly HoraInicio { get; set; }
    public TimeOnly HoraFin { get; set; }
    public string? OrganizerUser { get; set; }
    public List<string> AttendeeEmails { get; set; } = new();
}

public sealed class TeamsCalendarEventDto
{
    public string EventId { get; init; } = string.Empty;
    public string? WebLink { get; init; }
    public string? JoinUrl { get; init; }
}

public sealed class CrearDefensaGradoRequest : CrearGrupoComplexivoRequest
{
    public long ExpedienteId1 { get; set; }
    public long? ExpedienteId2 { get; set; }
}

public sealed class AgregarEstudianteGrupoRequest
{
    public string Cedula { get; set; } = string.Empty;
    public long? ExpedienteId { get; set; }
    public int? OrdenIntegrante { get; set; }
}

public sealed class ActualizarProgramacionGrupoRequest
{
    public DateOnly FechaProgramada { get; set; }
    public TimeOnly? HoraInicio { get; set; }
    public TimeOnly? HoraFin { get; set; }
    public string? AulaOLink { get; set; }
    public string? Modalidad { get; set; }
}

public sealed class ResponsableTitulacionDto
{
    public long ResponsableTitulacionId { get; init; }
    public string? Cedula { get; init; }
    public string Nombres { get; init; } = string.Empty;
    public string? Correo { get; init; }
    public string? Cargo { get; init; }
    public string RolCodigo { get; init; } = string.Empty;
    public bool Activo { get; init; }
}

public sealed class UpsertResponsableTitulacionRequest
{
    public string? Cedula { get; set; }
    public string Nombres { get; set; } = string.Empty;
    public string? Correo { get; set; }
    public string? Cargo { get; set; }
    public string RolCodigo { get; set; } = string.Empty;
}

public sealed class ResponsableAsignadoDto
{
    public long AsignacionId { get; init; }
    public long GrupoTitulacionId { get; init; }
    public long? ExpedienteId { get; init; }
    public long ResponsableTitulacionId { get; init; }
    public string Nombres { get; init; } = string.Empty;
    public string RolCodigo { get; init; } = string.Empty;
    public int? Orden { get; init; }
    public bool EsTribunal { get; init; }
}

public sealed class AsignarTribunalDefensaRequest
{
    public long GrupoTitulacionId { get; set; }
    public long PresidenteTribunalId { get; set; }
    public long Vocal1Id { get; set; }
    public long Vocal2Id { get; set; }
    public long? TutorId { get; set; }
    public string? Observacion { get; set; }
}

public sealed class AsignarResponsableComplexivoRequest
{
    public long GrupoTitulacionId { get; set; }
    public long ResponsableComplexivoId { get; set; }
    public List<long> EvaluadoresIds { get; set; } = new();
    public string? Observacion { get; set; }
}

public sealed class RegistrarCalificacionEvaluadorRequest
{
    public long ExpedienteId { get; set; }
    public long GrupoTitulacionId { get; set; }
    public long ResponsableTitulacionId { get; set; }
    public int EvaluadorNumero { get; set; }
    public decimal? NotaTrabajoEscrito { get; set; }
    public decimal? NotaDefensaOral { get; set; }
    public decimal? NotaExamenComplexivo { get; set; }
    public string? Observacion { get; set; }
    public bool CerrarCalificacion { get; set; }
}

public sealed class CalificacionEvaluadorDto
{
    public long CalificacionEvaluadorId { get; init; }
    public long ExpedienteId { get; init; }
    public long GrupoTitulacionId { get; init; }
    public long? ResponsableTitulacionId { get; init; }
    public int EvaluadorNumero { get; init; }
    public decimal? NotaTrabajoEscrito { get; init; }
    public decimal? NotaDefensaOral { get; init; }
    public decimal? NotaExamenComplexivo { get; init; }
    public decimal? NotaTitulacionSobre20 { get; init; }
    public bool Cerrado { get; init; }
    public string? Observacion { get; init; }
}

public sealed class CalificacionConsolidadaDto
{
    public long CalificacionConsolidadaId { get; init; }
    public long ExpedienteId { get; init; }
    public string NumeroIdentificacion { get; init; } = string.Empty;
    public decimal? NotaAsignaturas { get; init; }
    public decimal? EquivalenciaAsignaturas80 { get; init; }
    public decimal? PromedioTrabajoEscrito { get; init; }
    public decimal? PromedioDefensaOral { get; init; }
    public decimal? PromedioExamenComplexivo { get; init; }
    public decimal? NotaTitulacionSobre20 { get; init; }
    public decimal? EquivalenciaTitulacion20 { get; init; }
    public decimal? NotaFinalGrado { get; init; }
    public bool EvaluadoresCompletos { get; init; }
    public bool Aprobado { get; init; }
}

public sealed class UploadDocumentoTitulacionRequest
{
    public long? ExpedienteId { get; set; }
    public long? GrupoTitulacionId { get; set; }
    public string? Cedula { get; set; }
    public string TipoDocumentoCodigo { get; set; } = string.Empty;
    public IFormFile? Archivo { get; set; }
    public string? RutaNubeManual { get; set; }
    public bool EsFirmadoElectronicamente { get; set; }
    public string? Observacion { get; set; }
    public string? CodigoRegistroSenescyt { get; set; }
    public DateOnly? FechaRegistroSenescyt { get; set; }
    public string? NumeroTituloIntec { get; set; }
    public DateOnly? FechaEmisionTitulo { get; set; }
    public string? CodigoVerificacionQr { get; set; }
}

public class DocumentoTitulacionDto
{
    public long DocumentoId { get; init; }
    public long? ExpedienteId { get; init; }
    public long? GrupoTitulacionId { get; init; }
    public string? NumeroIdentificacion { get; init; }
    public string TipoDocumentoCodigo { get; init; } = string.Empty;
    public string NombreArchivo { get; init; } = string.Empty;
    public string? RutaNube { get; init; }
    public string? UrlPublica { get; init; }
    public string EstadoCodigo { get; init; } = string.Empty;
    public bool EsFirmadoElectronicamente { get; init; }
    public string? Observacion { get; init; }
    public int? Version { get; init; }
    public string? CodigoRegistroSenescyt { get; init; }
    public DateOnly? FechaRegistroSenescyt { get; init; }
    public string? NumeroTituloIntec { get; init; }
    public DateOnly? FechaEmisionTitulo { get; init; }
    public string? CodigoVerificacionQr { get; init; }
    public DateTime? FechaCarga { get; init; }
    public string? UsuarioCarga { get; init; }
}

public sealed class GenerarActaGradoRequest
{
    public string? NumeroActa { get; set; }
    public DateOnly FechaActa { get; set; } = DateOnly.FromDateTime(DateTime.Today);
    public TimeOnly? HoraActa { get; set; }
    public string Ciudad { get; set; } = "Quito";
    public string? Escuela { get; set; }
    public string? AutoridadAcademica { get; set; }
    public string? CoordinadorAcademico { get; set; }
    public string? DocenteEvaluador { get; set; }
    public string NombreInstitucion { get; set; } = "Instituto Superior Tecnologico INTEC";
}

public sealed class ActaGradoDto
{
    public long ActaGradoId { get; init; }
    public long ExpedienteId { get; init; }
    public string NumeroActa { get; init; } = string.Empty;
    public string NumeroIdentificacion { get; init; } = string.Empty;
    public string NombresEstudiante { get; init; } = string.Empty;
    public string? Carrera { get; init; }
    public string? Escuela { get; init; }
    public string? MecanismoCodigo { get; init; }
    public string? TituloOtorgado { get; init; }
    public DateOnly? FechaActa { get; init; }
    public TimeOnly? HoraActa { get; init; }
    public string? Ciudad { get; init; }
    public decimal? NotaFinalGrado { get; init; }
    public string? RutaActaPdf { get; init; }
    public string EstadoCodigo { get; init; } = string.Empty;
    public string? NombreInstitucion { get; init; }
    public string? TextoVariableActa { get; init; }
    public bool Activo { get; init; } = true;
    public string? MotivoAnulacion { get; init; }
}

public sealed class TituloTitulacionDto : DocumentoTitulacionDto
{
    public string? NombresEstudiante { get; init; }
    public string? Carrera { get; init; }
    public string? NumeroActa { get; init; }
    public string? NumeroActaGrado { get; init; }
}

public sealed class FileDownloadDto
{
    public string FileName { get; init; } = string.Empty;
    public string ContentType { get; init; } = "application/pdf";
    public byte[] Content { get; init; } = Array.Empty<byte>();
}

public sealed class FirmaActaDto
{
    public string Nombre { get; set; } = string.Empty;
    public string Cargo { get; set; } = string.Empty;
}

public sealed class ActaGradoPdfDto
{
    public string NumeroActa { get; set; } = string.Empty;
    public string Escuela { get; set; } = string.Empty;
    public string Ciudad { get; set; } = string.Empty;
    public DateOnly FechaActa { get; set; }
    public TimeOnly HoraActa { get; set; }
    public string NombreInstitucion { get; set; } = "Instituto Superior Tecnologico INTEC";
    public string Carrera { get; set; } = string.Empty;
    public string Modalidad { get; set; } = string.Empty;
    public string NombreEstudiante { get; set; } = string.Empty;
    public string Cedula { get; set; } = string.Empty;
    public string MecanismoTitulacion { get; set; } = string.Empty;
    public string TituloOtorgado { get; set; } = string.Empty;
    public decimal NotaAsignaturas { get; set; }
    public decimal EquivalenciaAsignaturas80 { get; set; }
    public decimal NotaProcesoTitulacion { get; set; }
    public decimal EquivalenciaTitulacion20 { get; set; }
    public decimal NotaFinalGrado { get; set; }
    public string AutoridadAcademica { get; set; } = string.Empty;
    public string CoordinadorAcademico { get; set; } = string.Empty;
    public string DocenteEvaluador { get; set; } = string.Empty;
    public List<FirmaActaDto> Firmas { get; set; } = new();
    public string TextoVariable { get; set; } = string.Empty;
}

public sealed class DocumentoTitulacionHistorialDto
{
    public long HistorialId { get; init; }
    public long DocumentoTitulacionId { get; init; }
    public long? ExpedienteId { get; init; }
    public string TipoDocumentoCodigo { get; init; } = string.Empty;
    public int? Version { get; init; }
    public string? EstadoCodigo { get; init; }
    public string Accion { get; init; } = string.Empty;
    public string? Observacion { get; init; }
    public string? NombreArchivo { get; init; }
    public string? RutaNube { get; init; }
    public string? UrlPublica { get; init; }
    public string UsuarioAccion { get; init; } = string.Empty;
    public DateTime FechaAccion { get; init; }
}

public sealed class AnularActaRequest
{
    public string Motivo { get; set; } = string.Empty;
}
