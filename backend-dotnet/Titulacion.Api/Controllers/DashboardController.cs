using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/dashboard")]
public sealed class DashboardController(IDashboardTitulacionService service) : TitulacionControllerBase
{
    [HttpGet("resumen")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    [ProducesResponseType(typeof(DashboardResumenDto), StatusCodes.Status200OK)]
    public Task<DashboardResumenDto> GetResumen(CancellationToken cancellationToken) =>
        service.GetResumenAsync(cancellationToken);
}
