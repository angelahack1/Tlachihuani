using System.Text.Json;
using System.Security;
using Microsoft.Win32;
using Tlachihuani.Windows;

namespace Tlachihuani.Jobs;

internal static class WorkspaceControllers
{
    private static readonly HttpClient Client = new(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
        { Timeout = TimeSpan.FromSeconds(2) };

    internal static async Task<IResult> Available()
    {
        var editions = await Task.WhenAll(Locate("Tlamatini", 8000), Locate("Tlamatini-Spanish", 8052));
        return Results.Json(editions.Where(app => app != null));
    }

    private static async Task<object?> Locate(string name, int fallbackPort)
    {
        try
        {
            string? location = null;
            try
            {
                var sid = JobsInstallation.Load().OperatorSid;
                using var key = Registry.Users.OpenSubKey($@"{sid}\Software\XAIHT\{name}");
                location = key?.GetValue("InstallLocation") as string;
            }
            // A virtual service account may not be able to read the operator's
            // registry hive. The edition can still be running on its usual port.
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException
                                       or InvalidOperationException) { }
            location ??= Path.Combine(Path.GetPathRoot(Environment.SystemDirectory)!, name);
            var port = fallbackPort;
            try
            {
                var config = new FileInfo(Path.Combine(location, "config.json"));
                if (config.Exists && config.Length <= 1048576)
                {
                    using var json = JsonDocument.Parse(await File.ReadAllBytesAsync(config.FullName));
                    if (json.RootElement.TryGetProperty("django_port", out var value) &&
                        int.TryParse(value.ToString(), out var configured) && configured is > 0 and <= 65535) port = configured;
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or SecurityException
                                       or JsonException or ArgumentException) { }
            if (port == 12064) return null;
            var url = $"http://127.0.0.1:{port}/agent/torrenter/workspace/";
            using var probe = await Client.GetAsync(url + "session/", HttpCompletionOption.ResponseHeadersRead);
            return probe.StatusCode == System.Net.HttpStatusCode.Unauthorized &&
                probe.Headers.TryGetValues("X-Torrenter-Controller", out var markers) && markers.Contains("1")
                ? new { name, url } : null;
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or IOException
                                   or UnauthorizedAccessException or JsonException) { return null; }
    }
}
