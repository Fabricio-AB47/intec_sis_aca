using Titulacion.Contracts;

namespace Titulacion.Tests;

public sealed class EndpointAuthorizationMetadataTests
{
    [Theory]
    [InlineData("HabilitacionesController.cs", "[Authorize(Roles = TitulacionRoles.AdminOCoordinador)]")]
    [InlineData("ResponsablesController.cs", "[Authorize(Roles = TitulacionRoles.Coordinador)]")]
    [InlineData("CalificacionesController.cs", "[Authorize(Roles = TitulacionRoles.Evaluador)]")]
    [InlineData("ActasController.cs", "[Authorize(Roles = TitulacionRoles.GeneracionActas)]")]
    [InlineData("TitulosController.cs", "[Authorize(Roles = TitulacionRoles.AdminOSecretaria)]")]
    [InlineData("DocumentosController.cs", "[Authorize(Roles = TitulacionRoles.GestionDocumental)]")]
    public void Endpoint_sensible_declara_roles_requeridos(string controllerFile, string expectedAttribute)
    {
        var source = ReadController(controllerFile);

        Assert.Contains(expectedAttribute, source);
    }

    [Fact]
    public void Roles_formales_del_prompt_estan_definidos_en_contracts()
    {
        var roles = new[]
        {
            TitulacionRoles.Admin,
            TitulacionRoles.Secretaria,
            TitulacionRoles.Coordinador,
            TitulacionRoles.Evaluador,
            TitulacionRoles.Autoridad,
            TitulacionRoles.Consulta
        };

        Assert.Equal(new[]
        {
            "ADMIN_TITULACION",
            "SECRETARIA_TITULACION",
            "COORDINADOR_ACADEMICO",
            "EVALUADOR_TITULACION",
            "AUTORIDAD_ACADEMICA",
            "CONSULTA_TITULACION"
        }, roles);
    }

    [Theory]
    [InlineData("DashboardController.cs", "[HttpGet(\"resumen\")]")]
    [InlineData("EstudiantesAptosController.cs", "[HttpPost(\"sincronizar\")]")]
    [InlineData("HabilitacionesController.cs", "[HttpPut(\"{id:long}/anular\")]")]
    [InlineData("GruposController.cs", "[HttpPost(\"complexivo\")]")]
    [InlineData("GruposController.cs", "[HttpPost(\"defensa-grado\")]")]
    [InlineData("ResponsablesController.cs", "[HttpPost(\"grupos/{grupoId:long}/tribunal-defensa\")]")]
    [InlineData("CalificacionesController.cs", "[HttpPut(\"~/api/titulacion/calificaciones/{id:long}/reabrir\")]")]
    [InlineData("DocumentosController.cs", "[HttpPost(\"documentos/upload\")]")]
    [InlineData("TitulosController.cs", "[HttpPost(\"registro/upload\")]")]
    [InlineData("TitulosController.cs", "[HttpPost(\"intec/upload\")]")]
    [InlineData("ActasController.cs", "[HttpPost(\"actas/{actaId:long}/firmada/upload\")]")]
    [InlineData("ActasController.cs", "[HttpPut(\"actas/{actaId:long}/anular\")]")]
    public void Endpoints_requeridos_declaran_ruta_esperada(string controllerFile, string expectedRoute)
    {
        var source = ReadController(controllerFile);

        Assert.Contains(expectedRoute, source);
    }

    private static string ReadController(string controllerFile)
    {
        var root = FindRepoRoot(AppContext.BaseDirectory);
        var path = Path.Combine(root, "backend-dotnet", "Titulacion.Api", "Controllers", controllerFile);
        return File.ReadAllText(path);
    }

    private static string FindRepoRoot(string start)
    {
        var directory = new DirectoryInfo(start);
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, "backend-dotnet")) &&
                Directory.Exists(Path.Combine(directory.FullName, "frontend-angular")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("No se encontro la raiz del repositorio.");
    }
}
