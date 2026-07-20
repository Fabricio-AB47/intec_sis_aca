using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/estudiantes-aptos")]
public sealed class EstudiantesAptosController(IEstudianteAptoService service) : TitulacionControllerBase
{
    [HttpGet]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public Task<PagedResult<EstudianteAptoDto>> Get([FromQuery] EstudianteAptoFiltro filtro, CancellationToken cancellationToken) =>
        service.GetAsync(filtro, cancellationToken);

    [HttpGet("{cedula}")]
    [Authorize(Roles = TitulacionRoles.ConsultaAcademica)]
    public async Task<ActionResult<EstudianteAptoDto>> GetByCedula(string cedula, CancellationToken cancellationToken)
    {
        var estudiante = await service.GetByCedulaAsync(cedula, cancellationToken);
        return estudiante is null ? NotFound() : Ok(estudiante);
    }

    [HttpPost("sincronizar")]
    [Authorize(Roles = TitulacionRoles.AdminOCoordinador)]
    public Task<SincronizacionEstudiantesDto> Sincronizar(CancellationToken cancellationToken) =>
        service.SincronizarAsync(cancellationToken);
}
