using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Tests;

internal sealed class FakeTitulacionRepository : ITitulacionRepository
{
    public EstudianteAptoDto? EstudianteApto { get; set; }
    public HabilitacionDto Habilitacion { get; set; } = new()
    {
        HabilitacionId = 10,
        ExpedienteId = 20,
        NumeroIdentificacion = "0102030405",
        Carrera = "Software",
        CodigoCarrera = "SW",
        CodigoPeriodo = "2026A",
        MecanismoCodigo = "EXAMEN_COMPLEXIVO",
        EstadoCodigo = "ACTIVO",
        FechaHabilitacion = DateTime.UtcNow,
        UsuarioHabilitacion = "qa"
    };
    public CalificacionConsolidadaDto Consolidado { get; set; } = new()
    {
        CalificacionConsolidadaId = 1,
        ExpedienteId = 20,
        NumeroIdentificacion = "0102030405",
        EvaluadoresCompletos = true,
        Aprobado = true,
        NotaFinalGrado = 9.53m
    };
    public DocumentoTitulacionDto Documento { get; set; } = new()
    {
        DocumentoId = 1,
        ExpedienteId = 20,
        NumeroIdentificacion = "0102030405",
        TipoDocumentoCodigo = "ACTA_GRADO",
        NombreArchivo = "acta.pdf",
        RutaNube = "storage/acta.pdf",
        UrlPublica = "/files/acta.pdf",
        EstadoCodigo = "CARGADO",
        EsFirmadoElectronicamente = false
    };
    public ActaGradoDto Acta { get; set; } = new()
    {
        ActaGradoId = 7,
        ExpedienteId = 20,
        NumeroActa = "INTEC-VGA-SW-Q-A-20260707-01",
        NumeroIdentificacion = "0102030405",
        NombresEstudiante = "Ada Lovelace",
        Carrera = "Software",
        EstadoCodigo = "GENERADA",
        RutaActaPdf = "storage/acta.pdf"
    };
    public string NumeroActaGenerado { get; set; } = "INTEC-VGA-SW-Q-A-20260707-01";
    public UploadDocumentoTitulacionRequest? UltimoDocumentoRequest { get; private set; }
    public StoredFile? UltimoStoredFile { get; private set; }
    public GenerarActaGradoRequest? UltimaActaRequest { get; private set; }
    public ActualizarProgramacionGrupoRequest? UltimaProgramacionRequest { get; private set; }
    public AsignarResponsableComplexivoRequest? UltimaAsignacionComplexivoRequest { get; private set; }
    public bool HabilitarFueLlamado { get; private set; }
    public bool AsignarTribunalFueLlamado { get; private set; }
    public bool AsignarComplexivoFueLlamado { get; private set; }
    public long? CalificacionReabiertaId { get; private set; }

    public Task<DashboardResumenDto> GetDashboardAsync(CancellationToken cancellationToken) =>
        Task.FromResult(new DashboardResumenDto { EstudiantesAptos = 3, ActasGeneradas = 1 });

    public Task<PagedResult<EstudianteAptoDto>> GetEstudiantesAptosAsync(EstudianteAptoFiltro filtro, CancellationToken cancellationToken) =>
        Task.FromResult(new PagedResult<EstudianteAptoDto>
        {
            Items = EstudianteApto is null ? Array.Empty<EstudianteAptoDto>() : new[] { EstudianteApto },
            Total = EstudianteApto is null ? 0 : 1,
            Page = filtro.Page,
            PageSize = filtro.PageSize
        });

    public Task<EstudianteAptoDto?> GetEstudianteAptoByCedulaAsync(string cedula, CancellationToken cancellationToken) =>
        Task.FromResult(EstudianteApto);

    public Task<SincronizacionEstudiantesDto> SincronizarEstudiantesAsync(CancellationToken cancellationToken) =>
        Task.FromResult(new SincronizacionEstudiantesDto { EstudiantesAptos = 1, EstudiantesPendientes = 0, Mensaje = "OK" });

    public Task<HabilitacionDto> HabilitarEstudianteAsync(HabilitarEstudianteRequest request, string usuario, CancellationToken cancellationToken)
    {
        HabilitarFueLlamado = true;
        return Task.FromResult(Habilitacion);
    }

    public Task<IReadOnlyList<HabilitacionDto>> GetHabilitacionesAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<HabilitacionDto>>(new[] { Habilitacion });

    public Task<HabilitacionDto?> GetHabilitacionAsync(long id, CancellationToken cancellationToken) =>
        Task.FromResult<HabilitacionDto?>(Habilitacion);

    public Task AnularHabilitacionAsync(long id, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<GrupoTitulacionDto> CrearGrupoComplexivoAsync(CrearGrupoComplexivoRequest request, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult(Grupo("EXAMEN_COMPLEXIVO", request.AulaOLink, request.FechaProgramada, request.HoraInicio, request.HoraFin, request.Modalidad));

    public Task<GrupoTitulacionDto> CrearDefensaGradoAsync(CrearDefensaGradoRequest request, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult(Grupo("DEFENSA_GRADO"));

    public Task<IReadOnlyList<GrupoTitulacionDto>> GetGruposAsync(string? mecanismo, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<GrupoTitulacionDto>>(new[] { Grupo(mecanismo ?? "EXAMEN_COMPLEXIVO") });

    public Task<GrupoTitulacionDto?> GetGrupoAsync(long id, CancellationToken cancellationToken) =>
        Task.FromResult<GrupoTitulacionDto?>(Grupo("EXAMEN_COMPLEXIVO", UltimaProgramacionRequest?.AulaOLink, UltimaProgramacionRequest?.FechaProgramada, UltimaProgramacionRequest?.HoraInicio, UltimaProgramacionRequest?.HoraFin, UltimaProgramacionRequest?.Modalidad));

    public Task AgregarEstudianteGrupoAsync(long grupoId, AgregarEstudianteGrupoRequest request, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;
    public Task EliminarEstudianteGrupoAsync(long grupoId, string cedula, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;
    public Task ActualizarProgramacionGrupoAsync(long grupoId, ActualizarProgramacionGrupoRequest request, string usuario, CancellationToken cancellationToken)
    {
        UltimaProgramacionRequest = request;
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<ResponsableTitulacionDto>> GetResponsablesAsync(string? rolCodigo, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<ResponsableTitulacionDto>>(Array.Empty<ResponsableTitulacionDto>());

    public Task<ResponsableTitulacionDto> CreateResponsableAsync(UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult(new ResponsableTitulacionDto { ResponsableTitulacionId = 1, Nombres = request.Nombres, RolCodigo = request.RolCodigo, Activo = true });

    public Task<ResponsableTitulacionDto> UpdateResponsableAsync(long id, UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult(new ResponsableTitulacionDto { ResponsableTitulacionId = id, Nombres = request.Nombres, RolCodigo = request.RolCodigo, Activo = true });

    public Task DeleteResponsableAsync(long id, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task AsignarResponsableComplexivoAsync(long grupoId, AsignarResponsableComplexivoRequest request, string usuario, CancellationToken cancellationToken)
    {
        AsignarComplexivoFueLlamado = true;
        UltimaAsignacionComplexivoRequest = request;
        return Task.CompletedTask;
    }

    public Task AsignarTribunalDefensaAsync(long grupoId, AsignarTribunalDefensaRequest request, string usuario, CancellationToken cancellationToken)
    {
        AsignarTribunalFueLlamado = true;
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<ResponsableAsignadoDto>> GetResponsablesAsignadosAsync(long grupoId, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<ResponsableAsignadoDto>>(Array.Empty<ResponsableAsignadoDto>());

    public Task<IReadOnlyList<CalificacionEvaluadorDto>> GetCalificacionesEvaluadorAsync(long expedienteId, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<CalificacionEvaluadorDto>>(Array.Empty<CalificacionEvaluadorDto>());

    public Task<CalificacionConsolidadaDto?> RegistrarCalificacionEvaluadorAsync(RegistrarCalificacionEvaluadorRequest request, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult<CalificacionConsolidadaDto?>(Consolidado);

    public Task<CalificacionConsolidadaDto?> ConsolidarCalificacionAsync(long expedienteId, long grupoId, string usuario, CancellationToken cancellationToken) =>
        Task.FromResult<CalificacionConsolidadaDto?>(Consolidado);

    public Task<CalificacionConsolidadaDto?> GetConsolidadoAsync(long expedienteId, CancellationToken cancellationToken) =>
        Task.FromResult<CalificacionConsolidadaDto?>(Consolidado);

    public Task ReabrirCalificacionAsync(long calificacionId, string usuario, CancellationToken cancellationToken)
    {
        CalificacionReabiertaId = calificacionId;
        return Task.CompletedTask;
    }

    public Task<DocumentoTitulacionDto> InsertDocumentoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        UltimoDocumentoRequest = request;
        UltimoStoredFile = storedFile;
        return Task.FromResult(Documento.WithType(request.TipoDocumentoCodigo, storedFile));
    }

    public Task<IReadOnlyList<DocumentoTitulacionDto>> GetDocumentosByExpedienteAsync(long expedienteId, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<DocumentoTitulacionDto>>(new[] { Documento });

    public Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetDocumentoHistorialAsync(long documentoId, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<DocumentoTitulacionHistorialDto>>(Array.Empty<DocumentoTitulacionHistorialDto>());

    public Task ValidarDocumentoAsync(long documentoId, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;
    public Task ObservarDocumentoAsync(long documentoId, string observacion, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<string> GenerarNumeroActaAsync(long expedienteId, GenerarActaGradoRequest request, CancellationToken cancellationToken) =>
        Task.FromResult(NumeroActaGenerado);

    public Task<ActaGradoPdfDto> BuildActaPdfDtoAsync(long expedienteId, GenerarActaGradoRequest request, string numeroActa, CancellationToken cancellationToken) =>
        Task.FromResult(new ActaGradoPdfDto
        {
            NumeroActa = numeroActa,
            Escuela = request.Escuela ?? "Escuela",
            Ciudad = request.Ciudad,
            FechaActa = request.FechaActa,
            HoraActa = request.HoraActa ?? new TimeOnly(9, 0),
            NombreInstitucion = request.NombreInstitucion,
            Carrera = "Software",
            Modalidad = "PRESENCIAL",
            NombreEstudiante = "Ada Lovelace",
            Cedula = "0102030405",
            MecanismoTitulacion = "EXAMEN_COMPLEXIVO",
            TituloOtorgado = "Tecnologo Superior",
            NotaAsignaturas = 9.47m,
            EquivalenciaAsignaturas80 = 7.576m,
            NotaProcesoTitulacion = 19.50m,
            EquivalenciaTitulacion20 = 1.950m,
            NotaFinalGrado = 9.53m,
            TextoVariable = "Acta de prueba"
        });

    public Task<ActaGradoDto> GenerarActaAsync(long expedienteId, GenerarActaGradoRequest request, StoredFile actaPdf, ActaGradoPdfDto pdfDto, string usuario, CancellationToken cancellationToken)
    {
        UltimaActaRequest = request;
        UltimoStoredFile = actaPdf;
        return Task.FromResult(Acta);
    }

    public Task<ActaGradoDto?> GetActaByExpedienteAsync(long expedienteId, CancellationToken cancellationToken) =>
        Task.FromResult<ActaGradoDto?>(Acta);

    public Task<ActaGradoDto?> GetActaByIdAsync(long actaId, CancellationToken cancellationToken) =>
        Task.FromResult<ActaGradoDto?>(Acta);

    public Task<IReadOnlyList<ActaGradoDto>> GetActasAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<ActaGradoDto>>(new[] { Acta });

    public Task AnularActaAsync(long actaId, string motivo, string usuario, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<DocumentoTitulacionDto> CargarTituloRegistradoAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        UltimoDocumentoRequest = request;
        UltimoStoredFile = storedFile;
        return Task.FromResult(Documento.WithType("TITULO_REGISTRO_SENESCYT", storedFile));
    }

    public Task<DocumentoTitulacionDto> CargarTituloIntecAsync(UploadDocumentoTitulacionRequest request, StoredFile storedFile, string usuario, CancellationToken cancellationToken)
    {
        UltimoDocumentoRequest = request;
        UltimoStoredFile = storedFile;
        return Task.FromResult(Documento.WithType("TITULO_INTEC", storedFile));
    }

    public Task<IReadOnlyList<TituloTitulacionDto>> GetTitulosAsync(string? search, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<TituloTitulacionDto>>(Array.Empty<TituloTitulacionDto>());

    private static GrupoTitulacionDto Grupo(
        string mecanismo,
        string? aulaOLink = null,
        DateOnly? fechaProgramada = null,
        TimeOnly? horaInicio = null,
        TimeOnly? horaFin = null,
        string? modalidad = null) => new()
    {
        GrupoTitulacionId = 1,
        CodigoGrupo = "G-1",
        NombreGrupo = "Grupo QA",
        MecanismoCodigo = mecanismo,
        FechaProgramada = fechaProgramada,
        HoraInicio = horaInicio,
        HoraFin = horaFin,
        AulaOLink = aulaOLink,
        Modalidad = modalidad,
        EstadoCodigo = "PROGRAMADO",
        MaximoIntegrantes = mecanismo == "DEFENSA_GRADO" ? 2 : 40,
        TotalIntegrantes = 1
    };
}

internal sealed class RecordingAuditoriaService : IAuditoriaService
{
    public List<string> Acciones { get; } = new();

    public Task RegistrarAsync(string accion, string entidad, string detalle, string usuario, CancellationToken cancellationToken)
    {
        Acciones.Add($"{accion}:{entidad}:{detalle}:{usuario}");
        return Task.CompletedTask;
    }
}

internal sealed class MemoryStorageService : IStorageService
{
    public byte[] ContentToRead { get; set; } = "%PDF-1.4 QA"u8.ToArray();
    public List<StoredFile> SavedFiles { get; } = new();

    public async Task<StoredFile> SaveAsync(Stream content, string fileName, string contentType, string folder, CancellationToken cancellationToken)
    {
        await using var buffer = new MemoryStream();
        await content.CopyToAsync(buffer, cancellationToken);
        var stored = new StoredFile(fileName, contentType, $"{folder}/{fileName}", $"/files/{folder}/{fileName}", buffer.ToArray());
        SavedFiles.Add(stored);
        return stored;
    }

    public Task<byte[]> ReadAsync(string ruta, CancellationToken cancellationToken) =>
        Task.FromResult(ContentToRead);
}

internal sealed class StaticPdfActaService : IPdfActaGradoService
{
    public ActaGradoPdfDto? LastDto { get; private set; }

    public Task<byte[]> GenerateAsync(ActaGradoPdfDto dto, CancellationToken cancellationToken)
    {
        LastDto = dto;
        return Task.FromResult("%PDF-1.4\nActa QA"u8.ToArray());
    }
}

internal sealed class FakeTeamsCalendarService : ITeamsCalendarService
{
    public TeamsCalendarEventRequest? LastRequest { get; private set; }
    public TeamsCalendarEventDto Result { get; set; } = new()
    {
        EventId = "event-qa",
        WebLink = "https://outlook.office.com/calendar/event-qa",
        JoinUrl = "https://teams.microsoft.com/l/meetup-join/qa"
    };

    public Task<TeamsCalendarEventDto> CreateTeamsEventAsync(TeamsCalendarEventRequest request, CancellationToken cancellationToken)
    {
        LastRequest = request;
        return Task.FromResult(Result);
    }
}

internal static class DocumentoTitulacionDtoExtensions
{
    public static DocumentoTitulacionDto WithType(this DocumentoTitulacionDto source, string tipo, StoredFile storedFile) => new()
    {
        DocumentoId = source.DocumentoId,
        ExpedienteId = source.ExpedienteId,
        GrupoTitulacionId = source.GrupoTitulacionId,
        NumeroIdentificacion = source.NumeroIdentificacion,
        TipoDocumentoCodigo = tipo,
        NombreArchivo = storedFile.FileName,
        RutaNube = storedFile.RutaNube,
        UrlPublica = storedFile.UrlPublica,
        EstadoCodigo = source.EstadoCodigo,
        EsFirmadoElectronicamente = source.EsFirmadoElectronicamente,
        Observacion = source.Observacion,
        Version = source.Version,
        CodigoRegistroSenescyt = source.CodigoRegistroSenescyt,
        FechaRegistroSenescyt = source.FechaRegistroSenescyt,
        NumeroTituloIntec = source.NumeroTituloIntec,
        FechaEmisionTitulo = source.FechaEmisionTitulo,
        CodigoVerificacionQr = source.CodigoVerificacionQr,
        FechaCarga = source.FechaCarga,
        UsuarioCarga = source.UsuarioCarga
    };
}
