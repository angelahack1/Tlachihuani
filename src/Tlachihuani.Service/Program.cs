// Tlachihuani — Angela López Mendoza · XAIHT
using System.Security.Principal;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.Extensions.Logging;
using Tlachihuani.Contracts;
using Tlachihuani.Core;
using Tlachihuani.Service;
using Tlachihuani.Windows;

try
{
    var isService = WindowsServiceHelpers.IsWindowsService();
    Guid installationId;
    string pipeName;
    string operatorSid;
    int? runForSeconds = null;
    if (!isService)
    {
        if (args.Length is not (3 or 5) || args[0] != "--console" || args[1] != "--development-id" || !Guid.TryParse(args[2], out installationId) || installationId == Guid.Empty)
        {
            Console.Error.WriteLine("Use SCM for the installed service. For visible development: Tlachihuani.Service.exe --console --development-id <guid>");
            return 2;
        }
        pipeName = Installation.DevelopmentPipe(installationId);
        operatorSid = WindowsIdentity.GetCurrent().User!.Value;
        if (args.Length == 5)
        {
            if (args[3] != "--run-for-seconds" || !int.TryParse(args[4], out var seconds) || seconds is < 5 or > 120)
                throw new ArgumentException("Console-only --run-for-seconds must be between 5 and 120.");
            runForSeconds = seconds;
        }
    }
    else
    {
        if (args.Length != 0) throw new InvalidOperationException("The installed service does not accept command-line overrides.");
        var installation = Installation.Load();
        if (!string.Equals(Path.GetFullPath(Environment.ProcessPath!), Path.GetFullPath(installation.ServicePath), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The service image does not match the installation manifest.");
        OperatorProcessAccess.AllowIdentityCheck(installation.OperatorSid);
        installationId = installation.InstallationId; pipeName = installation.PipeName; operatorSid = installation.OperatorSid;
    }
    var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings { Args = [], ContentRootPath = AppContext.BaseDirectory });
    builder.Services.AddWindowsService(options => options.ServiceName = Protocol.ServiceName);
    builder.Logging.ClearProviders();
    if (!isService) builder.Logging.AddSimpleConsole(options => { options.SingleLine = true; options.TimestampFormat = "HH:mm:ss "; });
    else builder.Logging.AddEventLog(options => { options.SourceName = ".NET Runtime"; options.LogName = "Application"; });
    builder.Services.Configure<HostOptions>(options => options.ShutdownTimeout = TimeSpan.FromSeconds(10));
    builder.Services.AddSingleton(new HealthState());
    builder.Services.AddSingleton(new PipeSettings(pipeName, operatorSid, installationId));
    builder.Services.AddHostedService<ServiceWorker>();
    using var host = builder.Build();
    using var consoleDeadline = new CancellationTokenSource();
    if (runForSeconds is int duration) consoleDeadline.CancelAfter(TimeSpan.FromSeconds(duration));
    await host.RunAsync(consoleDeadline.Token);
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Tlachihuani startup failed: {ex.Message}");
    return 1;
}
