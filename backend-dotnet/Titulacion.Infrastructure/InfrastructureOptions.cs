namespace Titulacion.Infrastructure;

public sealed class TitulacionStorageOptions
{
    public string RootPath { get; set; } = "storage/titulacion";
    public string PublicBaseUrl { get; set; } = "/files/titulacion";
}

public sealed class TitulacionConnectionOptions
{
    public string ConnectionStringName { get; set; } = "Titulacion";
}

public sealed class TitulacionTeamsOptions
{
    public string? TenantId { get; set; }
    public string? ClientId { get; set; }
    public string? ClientSecret { get; set; }
    public string? OrganizerUser { get; set; }
    public string TimeZone { get; set; } = "SA Pacific Standard Time";
}
