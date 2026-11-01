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

    // Older frozen Tlamatini controllers do not send their generated-content
    // path. They launch us from the install or its agent pool. Recognize that
    // layout locally; never derive a destination from a user name or a REST field.
    private static string? InstalledContentRoot(string? profile)
    {
        if (profile?.StartsWith("tlm-", StringComparison.Ordinal) != true || !Guid.TryParse(profile[4..], out _)) return null;
        for (var d = new DirectoryInfo(Environment.CurrentDirectory); d != null; d = d.Parent)
        {
            if (File.Exists(Path.Combine(d.FullName, "runtime-assets.json")) &&
                File.Exists(Path.Combine(d.FullName, "agents", "torrenter", "torrenter.py")) &&
                (File.Exists(Path.Combine(d.FullName, "Tlamatini.exe")) || File.Exists(Path.Combine(d.FullName, "Tlamatini-Spanish.exe"))))
                return Path.Combine(d.FullName, "content_generated");
        }
        return null;
    }
    public static async Task<JsonObject> CallInstalledAsync(JsonObject request, CancellationToken token)
    {
        var install = JobsInstallation.Load();
        var scm = ScmBackend.ForJobs();
        scm.ValidateJobsInstallation();
        var reply = await CallAsync(Pipe(install), scm.Query().Pid, JobsInstallation.Image, request, token);
        if (reply["code"] is JsonValue code && code.GetValue<int>() >= 400)
            throw new InvalidOperationException((string?)reply["body"]?["error"] ?? "Jobs refused the request.");
        return reply["body"]?.AsObject() ?? reply;
    }

    public static async Task<JsonObject> CallAsync(string pipeName, int pid, string image, JsonObject request, CancellationToken token)
    {
        using var pipe = await LocalPipe.ConnectAsync(pipeName, token);
        using var server = LocalPipe.VerifyServer(pipe, pid, image);
        if ((string?)request["op"] == "issue")
        {
            request.Remove("delivery_root");
            request.Remove("delivery_error");
            var contentRoot = (string?)request["application_content_root"] ?? InstalledContentRoot((string?)request["profile"]);
            request.Remove("application_content_root");
            request.Remove("fallback_root");
            request.Remove("fallback_error");
            try
            {
                using var user = WindowsIdentity.GetCurrent();
                request["delivery_root"] = DownloadDelivery.Prepare(user, (string?)request["profile"] ?? "",
                    pipeName.StartsWith("XAIHT.Jobs.Dev.", StringComparison.Ordinal));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
            { request["delivery_error"] = "Cannot prepare Windows Downloads: " + ex.Message; }
            if (contentRoot is not null)
            {
                try
                {
                    using var user = WindowsIdentity.GetCurrent();
                    request["fallback_root"] = DownloadDelivery.Prepare(user, (string?)request["profile"] ?? "",
                        pipeName.StartsWith("XAIHT.Jobs.Dev.", StringComparison.Ordinal), contentRoot);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or System.Runtime.InteropServices.COMException)
                { request["fallback_error"] = "Cannot prepare content_generated: " + ex.Message; }
            }
        }
        await Protocol.WriteAsync(pipe, request, token);
        var reply = await Protocol.ReadAsync<JsonObject>(pipe, token);
        await pipe.WriteAsync(new byte[]{6}, token);
        return reply;
    }
}
