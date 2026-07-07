using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Titulacion.Api.Controllers;

[ApiController]
[Authorize]
public abstract class TitulacionControllerBase : ControllerBase
{
    protected string UsuarioActual => User.Identity?.Name ?? User.FindFirst("sub")?.Value ?? "SISTEMA_API";
}
