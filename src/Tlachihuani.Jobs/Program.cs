// Tlachihuani — Angela López Mendoza · XAIHT
using System.Security.Principal;
using Microsoft.Extensions.Hosting.WindowsServices;
using Tlachihuani.Windows;
using Tlachihuani.Jobs;

if (args.FirstOrDefault() == "--console" && OperatingSystem.IsWindows())
    DevelopmentConsole.AttachParent();

if (args is ["--web", var portText] && int.TryParse(portText, out int httpPort))
{
    if (await Console.In.ReadLineAsync() != "START") return 2;
    await WebFacade.RunAsync(httpPort);
    return 0;
}
if (args is ["--control"] or ["--dev-control", _, _])
{
    try
    {
        string pipe; int pid; string image;
        if (args.Length == 3 && Guid.TryParseExact(args[1], "N", out var devId) && int.TryParse(args[2], out pid))
        { pipe = "XAIHT.Jobs.Dev." + devId.ToString("N"); image = Environment.ProcessPath!; }
        else if (args.Length == 1)
        { var project = JobsInstallation.Load(); var scm = ScmBackend.ForJobs(); scm.ValidateJobsInstallation(); pid = scm.Query().Pid; pipe = JobsEndpoint.Pipe(project); image = JobsInstallation.Image; }
        else return 2;
        var request = System.Text.Json.Nodes.JsonNode.Parse(Console.ReadLine() ?? "")!.AsObject();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        Console.WriteLine((await JobsEndpoint.CallAsync(pipe, pid, image, request, timeout.Token)).ToJsonString());
        return 0;
    }
    catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
}
bool installed = WindowsServiceHelpers.IsWindowsService();
JobsSettings settings;
if (installed && args.Length == 0)
{
    var installation = JobsInstallation.Load();
    string expected = JobsInstallation.Image;
    if (!string.Equals(Environment.ProcessPath, expected, StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Jobs service image differs from the installation.");
    OperatorProcessAccess.AllowIdentityCheck(installation.OperatorSid);
    settings = new(JobsEndpoint.Pipe(installation), installation.OperatorSid,
        Path.Combine(JobsInstallation.Root, "state"), 12064, false);
}
else if (!installed && args is ["--console", var directory, var id, var port] &&
    Guid.TryParseExact(id, "N", out _) && int.TryParse(port, out int devPort) && devPort is >= 1024 and <= 65535)
{
    settings = new("XAIHT.Jobs.Dev." + id, WindowsIdentity.GetCurrent().User!.Value,
        Path.GetFullPath(directory), devPort, true);
}
else
{
    Console.Error.WriteLine("Run through SCM, or --console <isolated state directory> <32-digit guid> <port>.");
    return 2;
}
var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings { Args = [], ContentRootPath = AppContext.BaseDirectory });
builder.Services.AddWindowsService(o => o.ServiceName = JobsEndpoint.ServiceName);
builder.Logging.ClearProviders();
if (installed) builder.Logging.AddEventLog(o => o.SourceName = ".NET Runtime");
else builder.Logging.AddSimpleConsole(o => o.SingleLine = true);
builder.Services.AddSingleton(settings);
builder.Services.AddHostedService<JobsHost>();
using var host = builder.Build();
await host.RunAsync();
return 0;

namespace Tlachihuani.Jobs
{
    internal static class DevelopmentConsole
    {
        [System.Runtime.InteropServices.DllImport("kernel32.dll")]
        private static extern bool AttachConsole(uint processId);
        internal static void AttachParent() => AttachConsole(uint.MaxValue);
    }

    internal sealed record JobsSettings(string Pipe, string Operator, string State, int Port, bool Development);
}
