using Microsoft.Extensions.Logging;
using Titulacion.Application;

namespace Titulacion.Infrastructure;

public sealed class AuditoriaService(ILogger<AuditoriaService> logger) : IAuditoriaService
{
    public Task RegistrarAsync(string accion, string entidad, string detalle, string usuario, CancellationToken cancellationToken)
    {
        logger.LogInformation("Auditoria titulacion: {Accion} {Entidad} {Detalle} {Usuario}", accion, entidad, detalle, usuario);
        return Task.CompletedTask;
    }
}
