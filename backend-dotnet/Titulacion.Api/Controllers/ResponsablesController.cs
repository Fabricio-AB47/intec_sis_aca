using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion")]
public sealed class ResponsablesController(IResponsableTitulacionService service) : TitulacionControllerBase
{
    [HttpGet("responsables")]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public Task<IReadOnlyList<ResponsableTitulacionDto>> Get([FromQuery] string? rolCodigo, CancellationToken cancellationToken) =>
        service.GetAsync(rolCodigo, cancellationToken);

    [HttpPost("responsables")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<ResponsableTitulacionDto> Create([FromBody] UpsertResponsableTitulacionRequest request, CancellationToken cancellationToken) =>
        service.CreateAsync(request, UsuarioActual, cancellationToken);

    [HttpPut("responsables/{id:long}")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<ResponsableTitulacionDto> Update(long id, [FromBody] UpsertResponsableTitulacionRequest request, CancellationToken cancellationToken) =>
        service.UpdateAsync(id, request, UsuarioActual, cancellationToken);

    [HttpDelete("responsables/{id:long}")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public async Task<IActionResult> Delete(long id, CancellationToken cancellationToken)
    {
        await service.DeleteAsync(id, UsuarioActual, cancellationToken);
        return NoContent();
    }

    [HttpPost("grupos/{grupoId:long}/responsable-complexivo")]
    [Authorize(Roles = TitulacionRoles.Coordinador)]
    public Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarComplexivo(long grupoId, [FromBody] AsignarResponsableComplexivoRequest request, CancellationToken cancellationToken) =>
        service.AsignarResponsableComplexivoAsync(grupoId, request, UsuarioActual, cancellationToken);

    [HttpPost("grupos/{grupoId:long}/tribunal-defensa")]
    [Authorize(Roles = TitulacionRoles.Coordinador)]
    public Task<IReadOnlyList<ResponsableAsignadoDto>> AsignarTribunal(long grupoId, [FromBody] AsignarTribunalDefensaRequest request, CancellationToken cancellationToken) =>
        service.AsignarTribunalDefensaAsync(grupoId, request, UsuarioActual, cancellationToken);

    [HttpGet("grupos/{grupoId:long}/responsables")]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public Task<IReadOnlyList<ResponsableAsignadoDto>> GetAsignados(long grupoId, CancellationToken cancellationToken) =>
        service.GetAsignadosAsync(grupoId, cancellationToken);
}
