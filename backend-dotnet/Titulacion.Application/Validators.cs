using FluentValidation;
using Titulacion.Contracts;
using Titulacion.Domain;

namespace Titulacion.Application;

public sealed class HabilitarEstudianteRequestValidator : AbstractValidator<HabilitarEstudianteRequest>
{
    public HabilitarEstudianteRequestValidator()
    {
        RuleFor(x => x.Cedula).NotEmpty().MaximumLength(20);
        RuleFor(x => x.MecanismoCodigo)
            .NotEmpty()
            .Must(MecanismosTitulacion.EsValido)
            .WithErrorCode(TitulacionErrorCodes.MecanismoInvalido)
            .WithMessage("El mecanismo debe ser EXAMEN_COMPLEXIVO o DEFENSA_GRADO.");
        RuleFor(x => x.HoraFin)
            .GreaterThan(x => x.HoraInicio)
            .When(x => x.HoraInicio.HasValue && x.HoraFin.HasValue)
            .WithMessage("La hora fin debe ser mayor que la hora inicio.");
    }
}

public sealed class CrearDefensaGradoRequestValidator : AbstractValidator<CrearDefensaGradoRequest>
{
    public CrearDefensaGradoRequestValidator()
    {
        RuleFor(x => x.ExpedienteId1).GreaterThan(0);
        RuleFor(x => x.ExpedienteId2)
            .NotEqual(x => x.ExpedienteId1)
            .When(x => x.ExpedienteId2.HasValue)
            .WithErrorCode(TitulacionErrorCodes.DefensaMaximoDosEstudiantes);
    }
}

public sealed class CrearGrupoComplexivoTeamsRequestValidator : AbstractValidator<CrearGrupoComplexivoTeamsRequest>
{
    public CrearGrupoComplexivoTeamsRequestValidator()
    {
        RuleFor(x => x.ResponsableComplexivoId)
            .GreaterThan(0)
            .WithErrorCode(TitulacionErrorCodes.ResponsableComplexivoObligatorio);
        RuleFor(x => x.FechaProgramada).NotNull();
        RuleFor(x => x.HoraInicio).NotNull();
        RuleFor(x => x.HoraFin)
            .GreaterThan(x => x.HoraInicio)
            .When(x => x.HoraInicio.HasValue && x.HoraFin.HasValue)
            .WithMessage("La hora fin debe ser mayor que la hora inicio.");
        RuleFor(x => x.EvaluadoresIds)
            .Must(x => x.Count == 0 || x.Count >= 3)
            .WithErrorCode(TitulacionErrorCodes.FaltanTresEvaluadores)
            .WithMessage("Debe enviar minimo 3 evaluadores cuando se asignan evaluadores.");
        RuleForEach(x => x.CorreosAsistentes)
            .EmailAddress()
            .When(x => x.CorreosAsistentes.Count > 0);
        RuleFor(x => x.OrganizadorTeams)
            .EmailAddress()
            .When(x => !string.IsNullOrWhiteSpace(x.OrganizadorTeams));
    }
}

public sealed class AgregarEstudianteGrupoRequestValidator : AbstractValidator<AgregarEstudianteGrupoRequest>
{
    public AgregarEstudianteGrupoRequestValidator()
    {
        RuleFor(x => x.Cedula).NotEmpty().When(x => !x.ExpedienteId.HasValue);
        RuleFor(x => x.ExpedienteId).GreaterThan(0).When(x => x.ExpedienteId.HasValue);
    }
}

public sealed class UpsertResponsableTitulacionRequestValidator : AbstractValidator<UpsertResponsableTitulacionRequest>
{
    public UpsertResponsableTitulacionRequestValidator()
    {
        RuleFor(x => x.Nombres).NotEmpty().MaximumLength(250);
        RuleFor(x => x.RolCodigo).NotEmpty().MaximumLength(50);
        RuleFor(x => x.Correo).EmailAddress().When(x => !string.IsNullOrWhiteSpace(x.Correo));
    }
}

public sealed class AsignarTribunalDefensaRequestValidator : AbstractValidator<AsignarTribunalDefensaRequest>
{
    public AsignarTribunalDefensaRequestValidator()
    {
        RuleFor(x => x.GrupoTitulacionId).GreaterThan(0);
        RuleFor(x => x.PresidenteTribunalId).GreaterThan(0);
        RuleFor(x => x.Vocal1Id).GreaterThan(0);
        RuleFor(x => x.Vocal2Id).GreaterThan(0);
    }
}

public sealed class AsignarResponsableComplexivoRequestValidator : AbstractValidator<AsignarResponsableComplexivoRequest>
{
    public AsignarResponsableComplexivoRequestValidator()
    {
        RuleFor(x => x.GrupoTitulacionId).GreaterThan(0);
        RuleFor(x => x.ResponsableComplexivoId).GreaterThan(0).WithErrorCode(TitulacionErrorCodes.ResponsableComplexivoObligatorio);
        RuleFor(x => x.EvaluadoresIds)
            .Must(x => x.Count == 0 || x.Count >= 3)
            .WithErrorCode(TitulacionErrorCodes.FaltanTresEvaluadores)
            .WithMessage("Debe enviar minimo 3 evaluadores cuando se asignan evaluadores.");
    }
}

public sealed class RegistrarCalificacionEvaluadorRequestValidator : AbstractValidator<RegistrarCalificacionEvaluadorRequest>
{
    public RegistrarCalificacionEvaluadorRequestValidator()
    {
        RuleFor(x => x.ExpedienteId).GreaterThan(0);
        RuleFor(x => x.GrupoTitulacionId).GreaterThan(0);
        RuleFor(x => x.ResponsableTitulacionId).GreaterThan(0);
        RuleFor(x => x.EvaluadorNumero).InclusiveBetween(1, 3);
        RuleFor(x => x.NotaTrabajoEscrito).InclusiveBetween(0, 10).When(x => x.NotaTrabajoEscrito.HasValue);
        RuleFor(x => x.NotaDefensaOral).InclusiveBetween(0, 10).When(x => x.NotaDefensaOral.HasValue);
        RuleFor(x => x.NotaExamenComplexivo).InclusiveBetween(0, 10).When(x => x.NotaExamenComplexivo.HasValue);
        RuleFor(x => x)
            .Must(x => x.NotaExamenComplexivo.HasValue || x.NotaTrabajoEscrito.HasValue || x.NotaDefensaOral.HasValue)
            .WithErrorCode(TitulacionErrorCodes.NotasIncompletas)
            .WithMessage("Debe registrar al menos una nota.");
    }
}

public sealed class UploadDocumentoTitulacionRequestValidator : AbstractValidator<UploadDocumentoTitulacionRequest>
{
    public UploadDocumentoTitulacionRequestValidator()
    {
        RuleFor(x => x.TipoDocumentoCodigo).NotEmpty().MaximumLength(80);
        RuleFor(x => x)
            .Must(x => x.Archivo is not null || !string.IsNullOrWhiteSpace(x.RutaNubeManual))
            .WithMessage("Debe cargar un archivo o indicar una ruta manual.");
        RuleFor(x => x.CodigoRegistroSenescyt)
            .NotEmpty()
            .When(x => x.TipoDocumentoCodigo == "TITULO_REGISTRO_SENESCYT")
            .WithMessage("Debe indicar el codigo de registro SENESCYT.");
        RuleFor(x => x.FechaRegistroSenescyt)
            .NotNull()
            .When(x => x.TipoDocumentoCodigo == "TITULO_REGISTRO_SENESCYT")
            .WithMessage("Debe indicar la fecha de registro SENESCYT.");
        RuleFor(x => x.NumeroTituloIntec)
            .NotEmpty()
            .When(x => x.TipoDocumentoCodigo == "TITULO_INTEC")
            .WithMessage("Debe indicar el numero de titulo INTEC.");
        RuleFor(x => x.FechaEmisionTitulo)
            .NotNull()
            .When(x => x.TipoDocumentoCodigo == "TITULO_INTEC")
            .WithMessage("Debe indicar la fecha de emision del titulo INTEC.");
    }
}

public sealed class GenerarActaGradoRequestValidator : AbstractValidator<GenerarActaGradoRequest>
{
    public GenerarActaGradoRequestValidator()
    {
        RuleFor(x => x.FechaActa).NotEmpty();
        RuleFor(x => x.Ciudad).NotEmpty().MaximumLength(100);
    }
}
