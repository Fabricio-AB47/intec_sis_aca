using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using Titulacion.Application;
using Titulacion.Contracts;

namespace Titulacion.Api.Controllers;

[Route("api/titulacion")]
public sealed class ActasController(IActaGradoService service) : TitulacionControllerBase
{
    [HttpPost("expedientes/{expedienteId:long}/acta/generar")]
    [Authorize(Roles = TitulacionRoles.GeneracionActas)]
    public Task<ActaGradoDto> Generar(long expedienteId, [FromBody] GenerarActaGradoRequest request, CancellationToken cancellationToken) =>
        service.GenerarAsync(expedienteId, request, UsuarioActual, cancellationToken);

    [HttpGet("expedientes/{expedienteId:long}/acta")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public async Task<ActionResult<ActaGradoDto>> GetByExpediente(long expedienteId, CancellationToken cancellationToken)
    {
        var acta = await service.GetByExpedienteAsync(expedienteId, cancellationToken);
        return acta is null ? NotFound() : Ok(acta);
    }

    [HttpGet("actas")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public Task<IReadOnlyList<ActaGradoDto>> Get(CancellationToken cancellationToken) =>
        service.GetAsync(cancellationToken);

    [HttpGet("actas/{actaId:long}/pdf")]
    [Authorize(Roles = TitulacionRoles.Todos)]
    public async Task<IActionResult> GetPdf(long actaId, CancellationToken cancellationToken)
    {
        var file = await service.GetPdfAsync(actaId, cancellationToken);
        return File(file.Content, file.ContentType, file.FileName);
    }

    [HttpPost("actas/{actaId:long}/firmada/upload")]
    [Consumes("multipart/form-data")]
    [Authorize(Roles = TitulacionRoles.GestionDocumental)]
    public Task<DocumentoTitulacionDto> UploadFirmada(long actaId, [FromForm] UploadDocumentoTitulacionRequest request, CancellationToken cancellationToken) =>
        service.UploadFirmadaAsync(actaId, request, UsuarioActual, cancellationToken);

    [HttpPut("actas/{actaId:long}/anular")]
    [Authorize(Roles = TitulacionRoles.GeneracionActas)]
    public async Task<IActionResult> Anular(long actaId, [FromBody] AnularActaRequest request, CancellationToken cancellationToken)
    {
        await service.AnularAsync(actaId, request.Motivo, UsuarioActual, cancellationToken);
        return NoContent();
    }
}
