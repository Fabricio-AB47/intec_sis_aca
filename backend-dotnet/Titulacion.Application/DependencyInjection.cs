using Microsoft.Extensions.DependencyInjection;

namespace Titulacion.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddTitulacionApplication(this IServiceCollection services)
    {
        services.AddScoped<IDashboardTitulacionService, DashboardTitulacionService>();
        services.AddScoped<IEstudianteAptoService, EstudianteAptoService>();
        services.AddScoped<IHabilitacionTitulacionService, HabilitacionTitulacionService>();
        services.AddScoped<IGrupoTitulacionService, GrupoTitulacionService>();
        services.AddScoped<IResponsableTitulacionService, ResponsableTitulacionService>();
        services.AddScoped<ICalificacionTitulacionService, CalificacionTitulacionService>();
        services.AddScoped<IDocumentoTitulacionService, DocumentoTitulacionService>();
        services.AddScoped<IActaGradoService, ActaGradoService>();
        services.AddScoped<ITituloService, TituloService>();
        return services;
    }
}
