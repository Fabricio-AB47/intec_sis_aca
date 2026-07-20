using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using System.Data;

namespace Titulacion.Infrastructure;

public interface ISqlConnectionFactory
{
    Task<IDbConnection> OpenAsync(CancellationToken cancellationToken);
}

public sealed class SqlConnectionFactory(
    IConfiguration configuration,
    IOptions<TitulacionConnectionOptions> options) : ISqlConnectionFactory
{
    public async Task<IDbConnection> OpenAsync(CancellationToken cancellationToken)
    {
        var connectionString = configuration.GetConnectionString(options.Value.ConnectionStringName)
            ?? configuration.GetConnectionString("DefaultConnection");

        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new InvalidOperationException($"No existe ConnectionStrings:{options.Value.ConnectionStringName}.");
        }

        var connection = new SqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        return connection;
    }
}
