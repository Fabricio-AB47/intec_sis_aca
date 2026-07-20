using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Application;

public sealed class DashboardTitulacionService(ITitulacionRepository repository) : IDashboardTitulacionService
{
    public Task<DashboardResumenDto> GetResumenAsync(CancellationToken cancellationToken) =>
        repository.GetDashboardAsync(cancellationToken);
}

public sealed class EstudianteAptoService(ITitulacionRepository repository) : IEstudianteAptoService
{
    public Task<PagedResult<EstudianteAptoDto>> GetAsync(EstudianteAptoFiltro filtro, CancellationToken cancellationToken) =>
        repository.GetEstudiantesAptosAsync(filtro, cancellationToken);

    public Task<EstudianteAptoDto?> GetByCedulaAsync(string cedula, CancellationToken cancellationToken) =>
        repository.GetEstudianteAptoByCedulaAsync(cedula, cancellationToken);

    public Task<SincronizacionEstudiantesDto> SincronizarAsync(CancellationToken cancellationToken) =>
        repository.SincronizarEstudiantesAsync(cancellationToken);
}

public sealed class HabilitacionTitulacionService(
    ITitulacionRepository repository,
    IAuditoriaService auditoria) : IHabilitacionTitulacionService
{
    public async Task<HabilitacionDto> HabilitarAsync(HabilitarEstudianteRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (!MecanismosTitulacion.EsValido(request.MecanismoCodigo))
        {
            throw new TitulacionException(TitulacionErrorCodes.MecanismoInvalido, "El mecanismo de titulacion no es valido.");
        }

        var estudiante = await repository.GetEstudianteAptoByCedulaAsync(request.Cedula, cancellationToken);
        if (estudiante is null || !estudiante.PuedeHabilitar)
        {
            throw new TitulacionException(TitulacionErrorCodes.EstudianteNoApto, estudiante?.MotivoNoApto ?? "El estudiante no cumple todos los requisitos.");
        }

        var habilitacion = await repository.HabilitarEstudianteAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("HABILITAR_ESTUDIANTE", "tit.HabilitacionTitulacion", request.Cedula, usuario, cancellationToken);
        return habilitacion;
    }

    public Task<IReadOnlyList<HabilitacionDto>> GetAsync(CancellationToken cancellationToken) =>
        repository.GetHabilitacionesAsync(cancellationToken);

    public Task<HabilitacionDto?> GetByIdAsync(long id, CancellationToken cancellationToken) =>
        repository.GetHabilitacionAsync(id, cancellationToken);

    public async Task AnularAsync(long id, string usuario, CancellationToken cancellationToken)
    {
        await repository.AnularHabilitacionAsync(id, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ANULAR_HABILITACION", "tit.HabilitacionTitulacion", id.ToString(), usuario, cancellationToken);
    }
}

public sealed class GrupoTitulacionService(ITitulacionRepository repository, IAuditoriaService auditoria, ITeamsCalendarService teamsCalendar) : IGrupoTitulacionService
{
    public async Task<GrupoTitulacionDto> CrearComplexivoAsync(CrearGrupoComplexivoRequest request, string usuario, CancellationToken cancellationToken)
    {
        var grupo = await repository.CrearGrupoComplexivoAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CREAR_GRUPO_COMPLEXIVO", "tit.GrupoTitulacion", grupo.GrupoTitulacionId.ToString(), usuario, cancellationToken);
        return grupo;
    }

    public async Task<GrupoComplexivoTeamsDto> CrearComplexivoConTeamsAsync(CrearGrupoComplexivoTeamsRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (request.ResponsableComplexivoId <= 0)
        {
            throw new TitulacionException(TitulacionErrorCodes.ResponsableComplexivoObligatorio, "Debe seleccionar responsable del examen complexivo.");
        }

        if (request.EvaluadoresIds.Count is > 0 and < 3)
        {
            throw new TitulacionException(TitulacionErrorCodes.FaltanTresEvaluadores, "Debe asignar minimo 3 evaluadores cuando se envian evaluadores.");
        }

        if (request.FechaProgramada is not { } fecha || request.HoraInicio is not { } horaInicio)
        {
            throw new TitulacionException("PROGRAMACION_TEAMS_INCOMPLETA", "Debe indicar fecha y hora de inicio para crear el calendario de Teams.");
        }

        var horaFin = request.HoraFin ?? horaInicio.AddHours(2);
        if (horaFin <= horaInicio)
        {
            throw new TitulacionException("PROGRAMACION_TEAMS_INVALIDA", "La hora fin debe ser mayor que la hora inicio.");
        }

        var modalidad = string.IsNullOrWhiteSpace(request.Modalidad) ? "VIRTUAL" : request.Modalidad.Trim();
        var codigoGrupo = string.IsNullOrWhiteSpace(request.CodigoGrupo) ? "Grupo complexivo" : request.CodigoGrupo.Trim();
        var tema = string.IsNullOrWhiteSpace(request.Tema) ? "Examen complexivo" : request.Tema.Trim();
        var attendees = request.CorreosAsistentes
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Select(x => x.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        var teamsEvent = await teamsCalendar.CreateTeamsEventAsync(new TeamsCalendarEventRequest
        {
            Subject = $"Examen complexivo INTEC - {codigoGrupo}",
            BodyHtml = $"<p>{System.Net.WebUtility.HtmlEncode(tema)}</p><p>Responsable asignado desde el Portal de Titulacion INTEC.</p>",
            Fecha = fecha,
            HoraInicio = horaInicio,
            HoraFin = horaFin,
            OrganizerUser = request.OrganizadorTeams,
            AttendeeEmails = attendees
        }, cancellationToken);

        var joinUrl = !string.IsNullOrWhiteSpace(teamsEvent.JoinUrl) ? teamsEvent.JoinUrl : teamsEvent.WebLink;
        if (string.IsNullOrWhiteSpace(joinUrl))
        {
            throw new TitulacionException(TitulacionErrorCodes.TeamsEventoNoCreado, "Microsoft Graph creo el evento, pero no devolvio enlace de reunion Teams.", 502);
        }

        request.Modalidad = modalidad;
        request.HoraFin = horaFin;
        request.AulaOLink = joinUrl;

        var grupo = await repository.CrearGrupoComplexivoAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CREAR_GRUPO_COMPLEXIVO_TEAMS", "tit.GrupoTitulacion", grupo.GrupoTitulacionId.ToString(), usuario, cancellationToken);

        await repository.AsignarResponsableComplexivoAsync(grupo.GrupoTitulacionId, new AsignarResponsableComplexivoRequest
        {
            GrupoTitulacionId = grupo.GrupoTitulacionId,
            ResponsableComplexivoId = request.ResponsableComplexivoId,
            EvaluadoresIds = request.EvaluadoresIds,
            Observacion = request.Observacion
        }, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ASIGNAR_RESPONSABLE_COMPLEXIVO_TEAMS", "resp.AsignacionResponsableTitulacion", grupo.GrupoTitulacionId.ToString(), usuario, cancellationToken);

        await repository.ActualizarProgramacionGrupoAsync(grupo.GrupoTitulacionId, new ActualizarProgramacionGrupoRequest
        {
            FechaProgramada = fecha,
            HoraInicio = horaInicio,
            HoraFin = horaFin,
            AulaOLink = joinUrl,
            Modalidad = modalidad
        }, usuario, cancellationToken);
        await auditoria.RegistrarAsync("GUARDAR_ENLACE_TEAMS_COMPLEXIVO", "tit.ProgramacionTitulacion", grupo.GrupoTitulacionId.ToString(), usuario, cancellationToken);

        var actualizado = await repository.GetGrupoAsync(grupo.GrupoTitulacionId, cancellationToken)
            ?? throw new TitulacionException("GRUPO_NO_ENCONTRADO", "No existe el grupo de titulacion.", 404);
        var responsables = await repository.GetResponsablesAsignadosAsync(grupo.GrupoTitulacionId, cancellationToken);
        actualizado.Responsables = responsables;

        return new GrupoComplexivoTeamsDto
        {
            Grupo = actualizado,
            Responsables = responsables,
            TeamsCreado = true,
            TeamsJoinUrl = joinUrl,
            TeamsWebLink = teamsEvent.WebLink,
            TeamsEventId = teamsEvent.EventId
        };
    }

    public async Task<GrupoTitulacionDto> CrearDefensaAsync(CrearDefensaGradoRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (request.ExpedienteId2 is not null && request.ExpedienteId1 == request.ExpedienteId2)
        {
            throw new TitulacionException(TitulacionErrorCodes.DefensaMaximoDosEstudiantes, "La defensa no puede repetir el mismo expediente.");
        }

        var grupo = await repository.CrearDefensaGradoAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CREAR_DEFENSA_GRADO", "tit.GrupoTitulacion", grupo.GrupoTitulacionId.ToString(), usuario, cancellationToken);
        return grupo;
    }

    public Task<IReadOnlyList<GrupoTitulacionDto>> GetAsync(string? mecanismo, CancellationToken cancellationToken) =>
        repository.GetGruposAsync(mecanismo, cancellationToken);

    public Task<GrupoTitulacionDto?> GetByIdAsync(long id, CancellationToken cancellationToken) =>
        repository.GetGrupoAsync(id, cancellationToken);

    public async Task<GrupoTitulacionDto> AgregarEstudianteAsync(long grupoId, AgregarEstudianteGrupoRequest request, string usuario, CancellationToken cancellationToken)
    {
        await repository.AgregarEstudianteGrupoAsync(grupoId, request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("AGREGAR_ESTUDIANTE_GRUPO", "tit.GrupoTitulacionEstudiante", $"{grupoId}:{request.Cedula}", usuario, cancellationToken);
        return await repository.GetGrupoAsync(grupoId, cancellationToken)
            ?? throw new TitulacionException("GRUPO_NO_ENCONTRADO", "No existe el grupo de titulacion.", 404);
    }

    public async Task EliminarEstudianteAsync(long grupoId, string cedula, string usuario, CancellationToken cancellationToken)
    {
        await repository.EliminarEstudianteGrupoAsync(grupoId, cedula, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ELIMINAR_ESTUDIANTE_GRUPO", "tit.GrupoTitulacionEstudiante", $"{grupoId}:{cedula}", usuario, cancellationToken);
    }

    public async Task<GrupoTitulacionDto> ActualizarProgramacionAsync(long grupoId, ActualizarProgramacionGrupoRequest request, string usuario, CancellationToken cancellationToken)
    {
        await repository.ActualizarProgramacionGrupoAsync(grupoId, request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ACTUALIZAR_PROGRAMACION_GRUPO", "tit.GrupoTitulacion", grupoId.ToString(), usuario, cancellationToken);
        return await repository.GetGrupoAsync(grupoId, cancellationToken)
            ?? throw new TitulacionException("GRUPO_NO_ENCONTRADO", "No existe el grupo de titulacion.", 404);
    }
}

public sealed class ResponsableTitulacionService(ITitulacionRepository repository, IAuditoriaService auditoria) : IResponsableTitulacionService
{
    public Task<IReadOnlyList<ResponsableTitulacionDto>> GetAsync(string? rolCodigo, CancellationToken cancellationToken) =>
        repository.GetResponsablesAsync(rolCodigo, cancellationToken);

    public async Task<ResponsableTitulacionDto> CreateAsync(UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        var responsable = await repository.CreateResponsableAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CREAR_RESPONSABLE", "resp.ResponsableTitulacion", responsable.ResponsableTitulacionId.ToString(), usuario, cancellationToken);
        return responsable;
    }

    public async Task<ResponsableTitulacionDto> UpdateAsync(long id, UpsertResponsableTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        var responsable = await repository.UpdateResponsableAsync(id, request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ACTUALIZAR_RESPONSABLE", "resp.ResponsableTitulacion", id.ToString(), usuario, cancellationToken);
        return responsable;
    }

    public async Task DeleteAsync(long id, string usuario, CancellationToken cancellationToken)
    {
        await repository.DeleteResponsableAsync(id, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ELIMINAR_RESPONSABLE", "resp.ResponsableTitulacion", id.ToString(), usuario, cancellationToken);
    }

    public async Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarResponsableComplexivoAsync(long grupoId, AsignarResponsableComplexivoRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (request.ResponsableComplexivoId <= 0)
        {
            throw new TitulacionException(TitulacionErrorCodes.ResponsableComplexivoObligatorio, "Debe seleccionar responsable del examen complexivo.");
        }

        if (request.EvaluadoresIds.Count is > 0 and < 3)
        {
            throw new TitulacionException(TitulacionErrorCodes.FaltanTresEvaluadores, "Debe asignar minimo 3 evaluadores.");
        }

        await repository.AsignarResponsableComplexivoAsync(grupoId, request, usuario, cancellationToken);
        return await repository.GetResponsablesAsignadosAsync(grupoId, cancellationToken);
    }

    public async Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarTribunalDefensaAsync(long grupoId, AsignarTribunalDefensaRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (request.PresidenteTribunalId <= 0 || request.Vocal1Id <= 0 || request.Vocal2Id <= 0)
        {
            throw new TitulacionException(TitulacionErrorCodes.TribunalIncompleto, "La defensa requiere presidente, vocal 1 y vocal 2.");
        }

        await repository.AsignarTribunalDefensaAsync(grupoId, request, usuario, cancellationToken);
        return await repository.GetResponsablesAsignadosAsync(grupoId, cancellationToken);
    }

    public Task<IReadOnlyList<ResponsableAsignadoDto>> GetAsignadosAsync(long grupoId, CancellationToken cancellationToken) =>
        repository.GetResponsablesAsignadosAsync(grupoId, cancellationToken);
}

public sealed class CalificacionTitulacionService(ITitulacionRepository repository, IAuditoriaService auditoria) : ICalificacionTitulacionService
{
    public Task<IReadOnlyList<CalificacionEvaluadorDto>> GetEvaluadoresAsync(long expedienteId, CancellationToken cancellationToken) =>
        repository.GetCalificacionesEvaluadorAsync(expedienteId, cancellationToken);

    public async Task<CalificacionConsolidadaDto?> RegistrarEvaluadorAsync(long expedienteId, RegistrarCalificacionEvaluadorRequest request, string usuario, CancellationToken cancellationToken)
    {
        if (expedienteId != request.ExpedienteId)
        {
            throw new TitulacionException("EXPEDIENTE_INCONSISTENTE", "El expediente de la ruta no coincide con el request.");
        }

        ValidarNota(request.NotaTrabajoEscrito);
        ValidarNota(request.NotaDefensaOral);
        ValidarNota(request.NotaExamenComplexivo);

        var result = await repository.RegistrarCalificacionEvaluadorAsync(request, usuario, cancellationToken);
        await auditoria.RegistrarAsync("REGISTRAR_CALIFICACION", "eval.CalificacionEvaluador", $"{request.ExpedienteId}:{request.EvaluadorNumero}", usuario, cancellationToken);
        return result;
    }

    public Task<CalificacionConsolidadaDto?> ConsolidarAsync(long expedienteId, long grupoId, string usuario, CancellationToken cancellationToken) =>
        repository.ConsolidarCalificacionAsync(expedienteId, grupoId, usuario, cancellationToken);

    public Task<CalificacionConsolidadaDto?> GetConsolidadoAsync(long expedienteId, CancellationToken cancellationToken) =>
        repository.GetConsolidadoAsync(expedienteId, cancellationToken);

    public async Task ReabrirAsync(long calificacionId, string usuario, CancellationToken cancellationToken)
    {
        await repository.ReabrirCalificacionAsync(calificacionId, usuario, cancellationToken);
        await auditoria.RegistrarAsync("REABRIR_CALIFICACION", "eval.CalificacionEvaluador", calificacionId.ToString(), usuario, cancellationToken);
    }

    private static void ValidarNota(decimal? nota)
    {
        if (nota is < 0 or > 10)
        {
            throw new TitulacionException(TitulacionErrorCodes.NotasIncompletas, "Las notas deben estar entre 0 y 10.");
        }
    }
}

public sealed class DocumentoTitulacionService(
    ITitulacionRepository repository,
    IStorageService storage,
    IAuditoriaService auditoria) : IDocumentoTitulacionService
{
    public async Task<DocumentoTitulacionDto> UploadAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        var storedFile = await StoreAsync(storage, request, "documentos", cancellationToken);
        var documento = await repository.InsertDocumentoAsync(request, storedFile, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CARGAR_DOCUMENTO", "doc.DocumentoTitulacion", documento.DocumentoId.ToString(), usuario, cancellationToken);
        return documento;
    }

    public Task<IReadOnlyList<DocumentoTitulacionDto>> GetByExpedienteAsync(long expedienteId, CancellationToken cancellationToken) =>
        repository.GetDocumentosByExpedienteAsync(expedienteId, cancellationToken);

    public Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetHistorialAsync(long documentoId, CancellationToken cancellationToken) =>
        repository.GetDocumentoHistorialAsync(documentoId, cancellationToken);

    public async Task ValidarAsync(long documentoId, string usuario, CancellationToken cancellationToken)
    {
        await repository.ValidarDocumentoAsync(documentoId, usuario, cancellationToken);
        await auditoria.RegistrarAsync("VALIDAR_DOCUMENTO", "doc.DocumentoTitulacion", documentoId.ToString(), usuario, cancellationToken);
    }

    public async Task ObservarAsync(long documentoId, string observacion, string usuario, CancellationToken cancellationToken)
    {
        await repository.ObservarDocumentoAsync(documentoId, observacion, usuario, cancellationToken);
        await auditoria.RegistrarAsync("OBSERVAR_DOCUMENTO", "doc.DocumentoTitulacion", documentoId.ToString(), usuario, cancellationToken);
    }

    internal static async Task<StoredFile> StoreAsync(IStorageService storage, UploadDocumentoTitulacionRequest request, string folder, CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(request.RutaNubeManual))
        {
            var fileName = Path.GetFileName(request.RutaNubeManual);
            return new StoredFile(fileName, request.Archivo?.ContentType ?? "application/octet-stream", request.RutaNubeManual, request.RutaNubeManual, Array.Empty<byte>());
        }

        if (request.Archivo is null || request.Archivo.Length == 0)
        {
            throw new TitulacionException("ARCHIVO_REQUERIDO", "Debe enviar un archivo o una ruta manual.");
        }

        await using var stream = request.Archivo.OpenReadStream();
        return await storage.SaveAsync(stream, request.Archivo.FileName, request.Archivo.ContentType, folder, cancellationToken);
    }
}

public sealed class ActaGradoService(
    ITitulacionRepository repository,
    IStorageService storage,
    IPdfActaGradoService pdfActa,
    IAuditoriaService auditoria) : IActaGradoService
{
    public async Task<ActaGradoDto> GenerarAsync(long expedienteId, GenerarActaGradoRequest request, string usuario, CancellationToken cancellationToken)
    {
        var numeroActa = string.IsNullOrWhiteSpace(request.NumeroActa)
            ? await repository.GenerarNumeroActaAsync(expedienteId, request, cancellationToken)
            : request.NumeroActa.Trim();
        request.NumeroActa = numeroActa;

        var pdfDto = await repository.BuildActaPdfDtoAsync(expedienteId, request, numeroActa, cancellationToken);
        var pdf = await pdfActa.GenerateAsync(pdfDto, cancellationToken);
        await using var stream = new MemoryStream(pdf);
        var stored = await storage.SaveAsync(stream, $"acta-{expedienteId}-{DateTime.UtcNow:yyyyMMddHHmmss}.pdf", "application/pdf", "actas", cancellationToken);
        var acta = await repository.GenerarActaAsync(expedienteId, request, stored, pdfDto, usuario, cancellationToken);
        await auditoria.RegistrarAsync("GENERAR_ACTA", "tit.ActaGrado", acta.ActaGradoId.ToString(), usuario, cancellationToken);
        return acta;
    }

    public Task<ActaGradoDto?> GetByExpedienteAsync(long expedienteId, CancellationToken cancellationToken) =>
        repository.GetActaByExpedienteAsync(expedienteId, cancellationToken);

    public Task<IReadOnlyList<ActaGradoDto>> GetAsync(CancellationToken cancellationToken) =>
        repository.GetActasAsync(cancellationToken);

    public async Task<FileDownloadDto> GetPdfAsync(long actaId, CancellationToken cancellationToken)
    {
        var acta = await repository.GetActaByIdAsync(actaId, cancellationToken)
            ?? throw new TitulacionException("ACTA_NO_ENCONTRADA", "No existe el acta solicitada.", 404);

        if (string.IsNullOrWhiteSpace(acta.RutaActaPdf))
        {
            throw new TitulacionException("ACTA_SIN_PDF", "El acta no tiene PDF registrado.", 404);
        }

        var content = await storage.ReadAsync(acta.RutaActaPdf, cancellationToken);
        return new FileDownloadDto
        {
            FileName = $"{acta.NumeroActa}.pdf",
            ContentType = "application/pdf",
            Content = content
        };
    }

    public async Task<DocumentoTitulacionDto> UploadFirmadaAsync(long actaId, UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        var acta = await repository.GetActaByIdAsync(actaId, cancellationToken)
            ?? throw new TitulacionException("ACTA_NO_ENCONTRADA", "No existe el acta solicitada.", 404);

        request.ExpedienteId = acta.ExpedienteId;
        request.Cedula = acta.NumeroIdentificacion;
        request.TipoDocumentoCodigo = "ACTA_GRADO_FIRMADA";
        request.EsFirmadoElectronicamente = true;

        var stored = await DocumentoTitulacionService.StoreAsync(storage, request, "actas-firmadas", cancellationToken);
        var documento = await repository.InsertDocumentoAsync(request, stored, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CARGAR_ACTA_FIRMADA", "doc.DocumentoTitulacion", documento.DocumentoId.ToString(), usuario, cancellationToken);
        return documento;
    }

    public async Task AnularAsync(long actaId, string motivo, string usuario, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(motivo))
        {
            throw new TitulacionException("MOTIVO_REQUERIDO", "Debe indicar el motivo de anulacion.");
        }

        await repository.AnularActaAsync(actaId, motivo, usuario, cancellationToken);
        await auditoria.RegistrarAsync("ANULAR_ACTA", "tit.ActaGrado", actaId.ToString(), usuario, cancellationToken);
    }
}

public sealed class TituloService(
    ITitulacionRepository repository,
    IStorageService storage,
    IAuditoriaService auditoria) : ITituloService
{
    public async Task<DocumentoTitulacionDto> UploadTituloRegistradoAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        request.TipoDocumentoCodigo = "TITULO_REGISTRO_SENESCYT";
        var stored = await DocumentoTitulacionService.StoreAsync(storage, request, "titulos-registrados", cancellationToken);
        var documento = await repository.CargarTituloRegistradoAsync(request, stored, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CARGAR_TITULO_REGISTRADO", "doc.DocumentoTitulacion", documento.DocumentoId.ToString(), usuario, cancellationToken);
        return documento;
    }

    public async Task<DocumentoTitulacionDto> UploadTituloIntecAsync(UploadDocumentoTitulacionRequest request, string usuario, CancellationToken cancellationToken)
    {
        request.TipoDocumentoCodigo = "TITULO_INTEC";
        var stored = await DocumentoTitulacionService.StoreAsync(storage, request, "titulos-intec", cancellationToken);
        var documento = await repository.CargarTituloIntecAsync(request, stored, usuario, cancellationToken);
        await auditoria.RegistrarAsync("CARGAR_TITULO_INTEC", "doc.DocumentoTitulacion", documento.DocumentoId.ToString(), usuario, cancellationToken);
        return documento;
    }

    public Task<IReadOnlyList<TituloTitulacionDto>> GetAsync(string? search, CancellationToken cancellationToken) =>
        repository.GetTitulosAsync(search, cancellationToken);

    public Task<IReadOnlyList<TituloTitulacionDto>> GetByCedulaAsync(string cedula, CancellationToken cancellationToken) =>
        repository.GetTitulosAsync(cedula, cancellationToken);
}
