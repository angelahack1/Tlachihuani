// Tlachihuani — Angela López Mendoza · XAIHT
using System.Security.Principal;
using System.Text.Json;
using Tlachihuani.Contracts;
using Tlachihuani.Core;

namespace Tlachihuani.Windows;

public sealed record Installation(Guid InstallationId, string ServicePath, string OperatorSid)
{
    public static string ManifestPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "XAIHT", "Tlachihuani", "installation.json");
    public string PipeName => $"XAIHT.Tlachihuani.v1.{InstallationId:N}";

    public static Installation Load()
    {
        if (!File.Exists(ManifestPath))
            throw new LifecycleException("not_installed", "Tlachihuani has no installation manifest. Install the published application first.");
        using var file = File.OpenRead(ManifestPath);
        if (file.Length > 4096) throw new LifecycleException("invalid_installation", "Installation manifest is too large.");
        var value = JsonSerializer.Deserialize<Installation>(file, Protocol.Json)
            ?? throw new LifecycleException("invalid_installation", "Installation manifest is empty.");
        if (value.InstallationId == Guid.Empty || !Path.IsPathFullyQualified(value.ServicePath)
            || !string.Equals(Path.GetFileName(value.ServicePath), "Tlachihuani.Service.exe", StringComparison.OrdinalIgnoreCase))
            throw new LifecycleException("invalid_installation", "Invalid installation identity or service executable.");
        _ = new SecurityIdentifier(value.OperatorSid);
        return value;
    }

    public static string DevelopmentPipe(Guid id) => $"XAIHT.Tlachihuani.Development.v1.{id:N}";
}
