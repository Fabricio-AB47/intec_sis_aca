using Titulacion.Contracts;

namespace Titulacion.Application;

public interface IDashboardTitulacionService
{
    Task<DashboardResumenDto> GetResumenAsync(CancellationToken cancellationToken);
}

public interface IEstudianteAptoService
{
    Task<PagedResult<EstudianteAptoDto>> GetAsync(EstudianteAptoFiltro filtro, CancellationToken cancellationToken);
    Task<EstudianteAptoDto?> GetByCedulaAsync(string cedula, CancellationToken cancellationToken);
    Task<SincronizacionEstudiantesDto> SincronizarAsync(CancellationToken cancellationToken);
}

public interface IHabilitacionTitulacionService
{
    Task<HabilitacionDto> HabilitarAsync(HabilitarEstudianteRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<HabilitacionDto>> GetAsync(CancellationToken cancellationToken);
    Task<HabilitacionDto?> GetByIdAsync(long id, CancellationToken cancellationToken);
    Task AnularAsync(long id, string usuario, CancellationToken cancellationToken);
}

public interface IGrupoTitulacionService
{
    Task<GrupoTitulacionDto> CrearComplexivoAsync(CrearGrupoComplexivoRequest request, string usuario, CancellationToken cancellationToken);
    Task<GrupoComplexivoTeamsDto> CrearComplexivoConTeamsAsync(CrearGrupoComplexivoTeamsRequest request, string usuario, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto> CrearDefensaAsync(CrearDefensaGradoRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<GrupoTitulacionDto>> GetAsync(string? mecanismo, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto?> GetByIdAsync(long id, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto> AgregarEstudianteAsync(long grupoId, AgregarEstudianteGrupoRequest request, string usuario, CancellationToken cancellationToken);
    Task EliminarEstudianteAsync(long grupoId, string cedula, string usuario, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto> ActualizarProgramacionAsync(long grupoId, ActualizarProgramacionGrupoRequest request, string usuario, CancellationToken cancellationToken);
}

public interface IResponsableTitulacionService
{
    Task<IReadOnlyList<ResponsableTitulacionDto>> GetAsync(string? rolCodigo, CancellationToken cancellationToken);
    Task<ResponsableTitulacionDto> CreateAsync(UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task<ResponsableTitulacionDto> UpdateAsync(long id, UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task DeleteAsync(long id, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarResponsableComplexivoAsync(long grupoId, AsignarResponsableComplexivoRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarTribunalDefensaAsync(long grupoId, AsignarTribunalDefensaRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<ResponsableAsignadoDto>> GetAsignadosAsync(long grupoId, CancellationToken cancellationToken);
}

public interface ICalificacionTitulacionService
{
    Task<IReadOnlyList<CalificacionEvaluadorDto>> GetEvaluadoresAsync(long expedienteId, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> RegistrarEvaluadorAsync(long expedienteId, RegistrarCalificacionEvaluadorRequest request, string usuario, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> ConsolidarAsync(long expedienteId, long grupoId, string usuario, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> GetConsolidadoAsync(long expedienteId, CancellationToken cancellationToken);
    Task ReabrirAsync(long calificacionId, string usuario, CancellationToken cancellationToken);
}

public interface IDocumentoTitulacionService
{
    Task<DocumentoTitulacionDto> UploadAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<DocumentoTitulacionDto>> GetByExpedienteAsync(long expedienteId, CancellationToken cancellationToken);
    Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetHistorialAsync(long documentoId, CancellationToken cancellationToken);
    Task ValidarAsync(long documentoId, string usuario, CancellationToken cancellationToken);
    Task ObservarAsync(long documentoId, string observacion, string usuario, CancellationToken cancellationToken);
}

public interface IActaGradoService
{
    Task<ActaGradoDto> GenerarAsync(long expedienteId, GenerarActaGradoRequest request, string usuario, CancellationToken cancellationToken);
    Task<ActaGradoDto?> GetByExpedienteAsync(long expedienteId, CancellationToken cancellationToken);
    Task<IReadOnlyList<ActaGradoDto>> GetAsync(CancellationToken cancellationToken);
    Task<FileDownloadDto> GetPdfAsync(long actaId, CancellationToken cancellationToken);
    Task<DocumentoTitulacionDto> UploadFirmadaAsync(long actaId, UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task AnularAsync(long actaId, string motivo, string usuario, CancellationToken cancellationToken);
}

public interface ITituloService
{
    Task<DocumentoTitulacionDto> UploadTituloRegistradoAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task<DocumentoTitulacionDto> UploadTituloIntecAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<TituloTitulacionDto>> GetAsync(string? search, CancellationToken cancellationToken);
    Task<IReadOnlyList<TituloTitulacionDto>> GetByCedulaAsync(string cedula, CancellationToken cancellationToken);
}

public interface ITitulacionRepository
{
    Task<DashboardResumenDto> GetDashboardAsync(CancellationToken cancellationToken);
    Task<PagedResult<EstudianteAptoDto>> GetEstudiantesAptosAsync(EstudianteAptoFiltro filtro, CancellationToken cancellationToken);
    Task<EstudianteAptoDto?> GetEstudianteAptoByCedulaAsync(string cedula, CancellationToken cancellationToken);
    Task<SincronizacionEstudiantesDto> SincronizarEstudiantesAsync(CancellationToken cancellationToken);
    Task<HabilitacionDto> HabilitarEstudianteAsync(HabilitarEstudianteRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<HabilitacionDto>> GetHabilitacionesAsync(CancellationToken cancellationToken);
    Task<HabilitacionDto?> GetHabilitacionAsync(long id, CancellationToken cancellationToken);
    Task AnularHabilitacionAsync(long id, string usuario, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto> CrearGrupoComplexivoAsync(CrearGrupoComplexivoRequest request, string usuario, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto> CrearDefensaGradoAsync(CrearDefensaGradoRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<GrupoTitulacionDto>> GetGruposAsync(string? mecanismo, CancellationToken cancellationToken);
    Task<GrupoTitulacionDto?> GetGrupoAsync(long id, CancellationToken cancellationToken);
    Task AgregarEstudianteGrupoAsync(long grupoId, AgregarEstudianteGrupoRequest request, string usuario, CancellationToken cancellationToken);
    Task EliminarEstudianteGrupoAsync(long grupoId, string cedula, string usuario, CancellationToken cancellationToken);
    Task ActualizarProgramacionGrupoAsync(long grupoId, ActualizarProgramacionGrupoRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<ResponsableTitulacionDto>> GetResponsablesAsync(string? rolCodigo, CancellationToken cancellationToken);
    Task<ResponsableTitulacionDto> CreateResponsableAsync(UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task<ResponsableTitulacionDto> UpdateResponsableAsync(long id, UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken);
    Task DeleteResponsableAsync(long id, string usuario, CancellationToken cancellationToken);
    Task AsignarResponsableComplexivoAsync(long grupoId, AsignarResponsableComplexivoRequest request, string usuario, CancellationToken cancellationToken);
    Task AsignarTribunalDefensaAsync(long grupoId, AsignarTribunalDefensaRequest request, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<ResponsableAsignadoDto>> GetResponsablesAsignadosAsync(long grupoId, CancellationToken cancellationToken);
    Task<IReadOnlyList<CalificacionEvaluadorDto>> GetCalificacionesEvaluadorAsync(long expedienteId, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> RegistrarCalificacionEvaluadorAsync(RegistrarCalificacionEvaluadorRequest request, string usuario, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> ConsolidarCalificacionAsync(long expedienteId, long grupoId, string usuario, CancellationToken cancellationToken);
    Task<CalificacionConsolidadaDto?> GetConsolidadoAsync(long expedienteId, CancellationToken cancellationToken);
    Task ReabrirCalificacionAsync(long calificacionId, string usuario, CancellationToken cancellationToken);
    Task<DocumentoTitulacionDto> InsertDocumentoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<DocumentoTitulacionDto>> GetDocumentosByExpedienteAsync(long expedienteId, CancellationToken cancellationToken);
    Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetDocumentoHistorialAsync(long documentoId, CancellationToken cancellationToken);
    Task ValidarDocumentoAsync(long documentoId, string usuario, CancellationToken cancellationToken);
    Task ObservarDocumentoAsync(long documentoId, string observacion, string usuario, CancellationToken cancellationToken);
    Task<string> GenerarNumeroActaAsync(long expedienteId, GenerarActaGradoRequest request, CancellationToken cancellationToken);
    Task<ActaGradoPdfDto> BuildActaPdfDtoAsync(long expedienteId, GenerarActaGradoRequest request, string numeroActa, CancellationToken cancellationToken);
    Task<ActaGradoDto> GenerarActaAsync(long expedienteId, GenerarActaGradoRequest request, StoredFile actaPdf, ActaGradoPdfDto pdfDto, string usuario, CancellationToken cancellationToken);
    Task<ActaGradoDto?> GetActaByExpedienteAsync(long expedienteId, CancellationToken cancellationToken);
    Task<ActaGradoDto?> GetActaByIdAsync(long actaId, CancellationToken cancellationToken);
    Task<IReadOnlyList<ActaGradoDto>> GetActasAsync(CancellationToken cancellationToken);
    Task AnularActaAsync(long actaId, string motivo, string usuario, CancellationToken cancellationToken);
    Task<DocumentoTitulacionDto> CargarTituloRegistradoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken);
    Task<DocumentoTitulacionDto> CargarTituloIntecAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken);
    Task<IReadOnlyList<TituloTitulacionDto>> GetTitulosAsync(string? search, CancellationToken cancellationToken);
}

public interface IStorageService
{
    Task<StoredFile> SaveAsync(Stream content, string fileName, string contentType, string folder, CancellationToken cancellationToken);
    Task<byte[]> ReadAsync(string ruta, CancellationToken cancellationToken);
}

public interface IPdfActaGradoService
{
    Task<byte[]> GenerateAsync(ActaGradoPdfDto dto, CancellationToken cancellationToken);
}

public interface ITeamsCalendarService
{
    Task<TeamsCalendarEventDto> CreateTeamsEventAsync(TeamsCalendarEventRequest request, CancellationToken cancellationToken);
}

public interface IAuditoriaService
{
    Task RegistrarAsync(string accion, string entidad, string detalle, string usuario, CancellationToken cancellationToken);
}

public sealed record StoredFile(string FileName, string ContentType, string RutaNube, string UrlPublica, byte[] Hash);
