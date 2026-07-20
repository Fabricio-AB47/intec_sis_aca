using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/expedientes/{expedienteId:long}/calificaciones")]
public sealed class CalificacionesController(ICalificacionTitulacionService service) : TitulacionControllerBase
{
    [HttpGet]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<IReadOnlyList<CalificacionEvaluadorDto>> Get(long expedienteId, CancellationToken cancellationToken) =>
        service.GetEvaluadoresAsync(expedienteId, cancellationToken);

    [HttpPost("evaluador")]
    [Authorize(Roles = TitulacionRoles.Evaluador)]
    public Task<CalificacionConsolidadaDto?> Registrar(long expedienteId, [FromBody] RegistrarCalificacionEvaluadorRequest request, CancellationToken cancellationToken) =>
        service.RegistrarEvaluadorAsync(expedienteId, request, UsuarioActual, cancellationToken);

    [HttpPost("consolidar")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<CalificacionConsolidadaDto?> Consolidar(long expedienteId, [FromQuery] long grupoId, CancellationToken cancellationToken) =>
        service.ConsolidarAsync(expedienteId, grupoId, UsuarioActual, cancellationToken);

    [HttpGet("consolidado")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<CalificacionConsolidadaDto?> GetConsolidado(long expedienteId, CancellationToken cancellationToken) =>
        service.GetConsolidadoAsync(expedienteId, cancellationToken);

    [HttpPut("~/api/titulacion/calificaciones/{id:long}/reabrir")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public async Task<IActionResult> Reabrir(long id, CancellationToken cancellationToken)
    {
        await service.ReabrirAsync(id, UsuarioActual, cancellationToken);
        return NoContent();
    }
}
