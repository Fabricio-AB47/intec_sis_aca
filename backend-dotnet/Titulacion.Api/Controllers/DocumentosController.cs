using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion")]
public sealed class DocumentosController(IDocumentoTitulacionService service) : TitulacionControllerBase
{
    [HttpPost("documentos/upload")]
    [Consumes("multipart/form-data")]
    [Authorize(Roles = TitulacionRoles.GestionDocumental)]
    public Task<DocumentoTitulacionDto> Upload([FromForm] UploadDocumentoTitulacionRequest request, CancellationToken cancellationToken) =>
        service.UploadAsync(request, UsuarioActual, cancellationToken);

    [HttpGet("expedientes/{expedienteId:long}/documentos")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<IReadOnlyList<DocumentoTitulacionDto>> GetByExpediente(long expedienteId, CancellationToken cancellationToken) =>
        service.GetByExpedienteAsync(expedienteId, cancellationToken);

    [HttpGet("documentos/{documentoId:long}/historial")]
    [Authorize(Roles = TitulacionRoles.GestionDocumental)]
    public Task<IReadOnlyList<DocumentoTitulacionHistorialDto>> GetHistorial(long documentoId, CancellationToken cancellationToken) =>
        service.GetHistorialAsync(documentoId, cancellationToken);

    [HttpPut("documentos/{documentoId:long}/validar")]
    [Authorize(Roles = TitulacionRoles.GestionDocumental)]
    public async Task<IActionResult> Validar(long documentoId, CancellationToken cancellationToken)
    {
        await service.ValidarAsync(documentoId, UsuarioActual, cancellationToken);
        return NoContent();
    }

    [HttpPut("documentos/{documentoId:long}/observar")]
    [Authorize(Roles = TitulacionRoles.GestionDocumental)]
    public async Task<IActionResult> Observar(long documentoId, [FromBody] string observacion, CancellationToken cancellationToken)
    {
        await service.ObservarAsync(documentoId, observacion, UsuarioActual, cancellationToken);
        return NoContent();
    }
}
