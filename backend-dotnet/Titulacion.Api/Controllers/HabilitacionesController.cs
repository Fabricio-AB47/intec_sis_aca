using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/habilitaciones")]
public sealed class HabilitacionesController(IHabilitacionTitulacionService service) : TitulacionControllerBase
{
    [HttpPost]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<HabilitacionDto> Habilitar([FromBody] HabilitarEstudianteRequest request, CancellationToken cancellationToken) =>
        service.HabilitarAsync(request, UsuarioActual, cancellationToken);

    [HttpGet]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public Task<IReadOnlyList<HabilitacionDto>> Get(CancellationToken cancellationToken) =>
        service.GetAsync(cancellationToken);

    [HttpGet("{id:long}")]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public async Task<ActionResult<HabilitacionDto>> GetById(long id, CancellationToken cancellationToken)
    {
        var habilitacion = await service.GetByIdAsync(id, cancellationToken);
        return habilitacion is null ? NotFound() : Ok(habilitacion);
    }

    [HttpPut("{id:long}/anular")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public async Task<IActionResult> Anular(long id, CancellationToken cancellationToken)
    {
        await service.AnularAsync(id, UsuarioActual, cancellationToken);
        return NoContent();
    }
}
