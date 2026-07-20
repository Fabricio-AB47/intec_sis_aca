using Microsoft.Extensions.Options;
using System.Security.Cryptography;
using Titulacion.Application;

namespace Titulacion.Infrastructure;

public sealed class LocalStorageService(IOptions<TitulacionStorageOptions> options) : IStorageService
{
    public async Task<StoredFile> SaveAsync(Stream content, string fileName, string contentType, string folder, CancellationToken cancellationToken)
    {
        var safeFolder = Sanitize(folder);
        var safeName = $"{Path.GetFileNameWithoutExtension(fileName)}-{Guid.NewGuid():N}{Path.GetExtension(fileName)}";
        safeName = Sanitize(safeName);
        var root = Path.GetFullPath(options.Value.RootPath);
        var targetFolder = Path.GetFullPath(Path.Combine(root, safeFolder));

        if (!targetFolder.StartsWith(root, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Ruta de almacenamiento invalida.");
        }

        Directory.CreateDirectory(targetFolder);
        var absolutePath = Path.Combine(targetFolder, safeName);

        await using (var file = File.Create(absolutePath))
        {
            await content.CopyToAsync(file, cancellationToken);
        }

        var bytes = await File.ReadAllBytesAsync(absolutePath, cancellationToken);
        var hash = SHA256.HashData(bytes);
        var relativePath = Path.Combine(safeFolder, safeName).Replace('\\', '/');
        var publicUrl = $"{options.Value.PublicBaseUrl.TrimEnd('/')}/{relativePath}";

        return new StoredFile(safeName, contentType, relativePath, publicUrl, hash);
    }

    public Task<byte[]> ReadAsync(string ruta, CancellationToken cancellationToken)
    {
        var root = Path.GetFullPath(options.Value.RootPath);
        var fullPath = Path.GetFullPath(Path.Combine(root, ruta.Replace('/', Path.DirectorySeparatorChar)));

        if (!fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !File.Exists(fullPath))
        {
            throw new FileNotFoundException("No se encontro el archivo solicitado.", ruta);
        }

        return File.ReadAllBytesAsync(fullPath, cancellationToken);
    }

    private static string Sanitize(string value)
    {
        foreach (var invalid in Path.GetInvalidFileNameChars())
        {
            value = value.Replace(invalid, '-');
        }

        return value.Trim().Replace(' ', '-');
    }
}
