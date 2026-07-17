using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion/titulos")]
public sealed class TitulosController(ITituloService service) : TitulacionControllerBase
{
    [HttpPost("registro/upload")]
    [Consumes("multipart/form-data")]
    [Authorize(Roles = TitulacionRoles.AdminOSecretaria)]
    public Task<DocumentoTitulacionDto> UploadRegistro([FromForm] UploadDocumentoTitulacionRequest request, CancellationToken cancellationToken) =>
        service.UploadTituloRegistradoAsync(request, UsuarioActual, cancellationToken);

    [HttpPost("intec/upload")]
    [Consumes("multipart/form-data")]
    [Authorize(Roles = TitulacionRoles.AdminOSecretaria)]
    public Task<DocumentoTitulacionDto> UploadIntec([FromForm] UploadDocumentoTitulacionRequest request, CancellationToken cancellationToken) =>
        service.UploadTituloIntecAsync(request, UsuarioActual, cancellationToken);

    [HttpGet]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<IReadOnlyList<TituloTitulacionDto>> Get([FromQuery] string? search, CancellationToken cancellationToken) =>
        service.GetAsync(search, cancellationToken);

    [HttpGet("{cedula}")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<IReadOnlyList<TituloTitulacionDto>> GetByCedula(string cedula, CancellationToken cancellationToken) =>
        service.GetByCedulaAsync(cedula, cancellationToken);
}
