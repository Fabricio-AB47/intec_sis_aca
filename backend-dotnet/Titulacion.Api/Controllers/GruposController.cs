using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/grupos")]
public sealed class GruposController(IGrupoTitulacionService service) : TitulacionControllerBase
{
    [HttpPost("complexivo")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<GrupoTitulacionDto> CrearComplexivo([FromBody] CrearGrupoComplexivoRequest request, CancellationToken cancellationToken) =>
        service.CrearComplexivoAsync(request, UsuarioActual, cancellationToken);

    [HttpPost("complexivo/teams")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<GrupoComplexivoTeamsDto> CrearComplexivoTeams([FromBody] CrearGrupoComplexivoTeamsRequest request, CancellationToken cancellationToken) =>
        service.CrearComplexivoConTeamsAsync(request, UsuarioActual, cancellationToken);

    [HttpPost("defensa-grado")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<GrupoTitulacionDto> CrearDefensa([FromBody] CrearDefensaGradoRequest request, CancellationToken cancellationToken) =>
        service.CrearDefensaAsync(request, UsuarioActual, cancellationToken);

    [HttpGet]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public Task<IReadOnlyList<GrupoTitulacionDto>> Get([FromQuery] string? mecanismo, CancellationToken cancellationToken) =>
        service.GetAsync(mecanismo, cancellationToken);

    [HttpGet("{id:long}")]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public async Task<ActionResult<GrupoTitulacionDto>> GetById(long id, CancellationToken cancellationToken)
    {
        var grupo = await service.GetByIdAsync(id, cancellationToken);
        return grupo is null ? NotFound() : Ok(grupo);
    }

    [HttpPost("{id:long}/estudiantes")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<GrupoTitulacionDto> AgregarEstudiante(long id, [FromBody] AgregarEstudianteGrupoRequest request, CancellationToken cancellationToken) =>
        service.AgregarEstudianteAsync(id, request, UsuarioActual, cancellationToken);

    [HttpDelete("{id:long}/estudiantes/{cedula}")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public async Task<IActionResult> EliminarEstudiante(long id, string cedula, CancellationToken cancellationToken)
    {
        await service.EliminarEstudianteAsync(id, cedula, UsuarioActual, cancellationToken);
        return NoContent();
    }

    [HttpPut("{id:long}/programacion")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<GrupoTitulacionDto> ActualizarProgramacion(long id, [FromBody] ActualizarProgramacionGrupoRequest request, CancellationToken cancellationToken) =>
        service.ActualizarProgramacionAsync(id, request, UsuarioActual, cancellationToken);
}
