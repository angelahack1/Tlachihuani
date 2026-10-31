// Tlachihuani — Angela López Mendoza · XAIHT
using System.Text.Json.Nodes;
using System.Text.Json;
using System.Security.Principal;
using Tlachihuani.Contracts;

namespace Tlachihuani.Windows;

public sealed record JobsInstallation(Guid InstallationId, string OperatorSid)
{
    public static string Root => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "XAIHT", "Tlachihuani.Jobs");
    public static string Image => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "XAIHT", "Tlachihuani", "Jobs", "Tlachihuani.Jobs.exe");
    public static JobsInstallation Load()
    {
        using var file = File.OpenRead(Path.Combine(Root, "installation.json"));
        if (file.Length > 4096) throw new InvalidDataException("Invalid Jobs installation manifest.");
        var value = JsonSerializer.Deserialize<JobsInstallation>(file, Protocol.Json);
        if (value is null || value.InstallationId == Guid.Empty) throw new InvalidDataException("Invalid Jobs installation ID.");
        _ = new SecurityIdentifier(value.OperatorSid);
        return value;
    }
}

public static class JobsEndpoint
{
    public const string ServiceName = "Tlachihuani.Jobs";
    public static string Pipe(JobsInstallation install) => $"XAIHT.Tlachihuani.Jobs.v2.{install.InstallationId:N}";
    public static async Task<JsonObject> CallAsync(string pipeName, int pid, string image, JsonObject request, CancellationToken token)
    {
        using var pipe = await LocalPipe.ConnectAsync(pipeName, token);
        using var server = LocalPipe.VerifyServer(pipe, pid, image);
        await Protocol.WriteAsync(pipe, request, token);
        var reply = await Protocol.ReadAsync<JsonObject>(pipe, token);
        await pipe.WriteAsync(new byte[]{6}, token);
        return reply;
    }
}
