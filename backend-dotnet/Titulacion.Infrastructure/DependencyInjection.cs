using Dapper;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Titulacion.Application;

namespace Titulacion.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddTitulacionInfrastructure(this IServiceCollection services, IConfiguration configuration)
    {
        SqlMapper.AddTypeHandler(new DateOnlyTypeHandler());
        SqlMapper.AddTypeHandler(new TimeOnlyTypeHandler());

        services.Configure<TitulacionStorageOptions>(configuration.GetSection("Titulacion:Storage"));
        services.Configure<TitulacionConnectionOptions>(configuration.GetSection("Titulacion:Connection"));
        services.Configure<TitulacionTeamsOptions>(configuration.GetSection("Titulacion:Teams"));

        services.AddScoped<ISqlConnectionFactory, SqlConnectionFactory>();
        services.AddScoped<ITitulacionRepository, DapperTitulacionRepository>();
        services.AddScoped<IStorageService, LocalStorageService>();
        services.AddScoped<IPdfActaGradoService, SimplePdfActaService>();
        services.AddScoped<IAuditoriaService, AuditoriaService>();
        services.AddHttpClient<ITeamsCalendarService, GraphTeamsCalendarService>();

        return services;
    }
}
