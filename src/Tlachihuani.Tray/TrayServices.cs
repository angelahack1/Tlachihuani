// Tlachihuani — Angela López Mendoza · XAIHT
using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json.Nodes;
using Tlachihuani.Client;
using Tlachihuani.Core;
using Tlachihuani.Windows;

namespace Tlachihuani.Tray;

internal sealed record JobsState(string State, bool ApiReady = false);

internal sealed class TrayServices(Controller primary)
{
    private readonly ScmBackend jobs = ScmBackend.ForJobs();
    private static readonly HttpClient http = new(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
    {
        MaxResponseContentBufferSize = 4096
    };

    internal async Task<JobsState> ObserveJobsAsync(CancellationToken token)
    {
        var state = jobs.Query().State;
        if (state != "running") return new(state);
        using var probe = CancellationTokenSource.CreateLinkedTokenSource(token);
        probe.CancelAfter(TimeSpan.FromSeconds(3));
        try
        {
            var provider = await JobsEndpoint.CallInstalledAsync(new() { ["op"] = "status" }, probe.Token);
            if ((bool?)provider["enabled"] != true || (bool?)provider["engine"] != true ||
                (bool?)provider["web"] != true || (int?)provider["port"] != 12064) return new(state);
            var bytes = await http.GetByteArrayAsync("http://127.0.0.1:12064/api/v1/health", probe.Token);
            var health = JsonNode.Parse(bytes);
            return new(state, (int?)health?["api_version"] == 1 && (string?)health?["engine"] == "ready");
        }
        catch (Exception ex) when (!token.IsCancellationRequested && ex is not OutOfMemoryException)
        {
            return new(state);
        }
    }

    internal async Task StartAsync(CancellationToken token)
    {
        await ChangePrimaryAsync("start", token);
        jobs.ValidateJobsInstallation();
        await new Lifecycle(jobs).ExecuteAsync("start", TimeSpan.FromSeconds(30), token);
        using var ready = CancellationTokenSource.CreateLinkedTokenSource(token);
        ready.CancelAfter(TimeSpan.FromSeconds(40));
        try
        {
            // Explicit Start also re-enables a provider previously stopped in the Services panel.
            await JobsEndpoint.CallInstalledAsync(new() { ["op"] = "start" }, ready.Token);
            while (!(await ObserveJobsAsync(ready.Token)).ApiReady) await Task.Delay(400, ready.Token);
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        {
            throw new TimeoutException("Jobs started, but Torrenter did not become ready on port 12064. Check the Services panel.");
        }
    }

    private async Task ChangePrimaryAsync(string action, CancellationToken token)
    {
        var reply = await primary.ExecuteAsync(action, token);
        if (!reply.Ok) throw new InvalidOperationException(reply.Error?.Message ?? $"Tlachihuani could not {action}.");
    }

    internal async Task StopAsync(CancellationToken token)
    {
        // Jobs checkpoints active transfers, then closes the kill-on-close Windows Job Object
        // containing its worker and web facade. Always also try the other independent service.
        var errors = new List<string>();
        foreach (var name in new[] { JobsEndpoint.ServiceName, Contracts.Protocol.ServiceName })
        {
            token.ThrowIfCancellationRequested();
            try { await StopHostAsync(name == JobsEndpoint.ServiceName, token); }
            catch (Exception ex) when (!token.IsCancellationRequested && ex is not OutOfMemoryException)
            { errors.Add($"{name}: {ex.Message}"); }
        }
        if (errors.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
    }

    private async Task StopHostAsync(bool stopJobs, CancellationToken token)
    {
        var scm = stopJobs ? jobs : new ScmBackend();
        var before = scm.Query();
        if (before.State is "stopped" or "not_installed") return;
        string expected;
        if (stopJobs)
        {
            scm.ValidateJobsInstallation();
            expected = JobsInstallation.Image;
        }
        else
        {
            var install = Installation.Load();
            scm.ValidateInstallation(install);
            expected = install.ServicePath;
        }
        using var host = ObserveHost(before.Pid, expected);
        if (stopJobs) await new Lifecycle(scm).ExecuteAsync("stop", TimeSpan.FromSeconds(40), token);
        else await ChangePrimaryAsync("stop", token);
        // SCM can report Stopped just before the executable exits. Keep the original identity
        // for observation only. Neither a process name nor a recycled PID is a kill target.
        using var exit = CancellationTokenSource.CreateLinkedTokenSource(token);
        exit.CancelAfter(TimeSpan.FromSeconds(12));
        try
        {
            while (host is not null ? !host.HasExited : PidPresent(before.Pid))
                await Task.Delay(100, exit.Token);
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        { throw new TimeoutException("Windows reported Stopped, but process exit could not be confirmed."); }
        if (scm.Query().State != "stopped") throw new InvalidOperationException("The service state changed during shutdown.");
    }

    private static ProcessIdentity? ObserveHost(int pid, string expected)
    {
        if (pid == 0) return null;
        ProcessIdentity identity;
        try { identity = ProcessIdentity.Open(pid); }
        catch (Win32Exception ex) when (ex.NativeErrorCode is 5 or 87) { return null; }
        if (string.Equals(identity.ImagePath, expected, StringComparison.OrdinalIgnoreCase)) return identity;
        identity.Dispose();
        throw new InvalidOperationException("The service process no longer matches the installation.");
    }

    private static bool PidPresent(int pid)
    {
        if (pid == 0) return false;
        try { using var process = Process.GetProcessById(pid); return true; }
        catch (ArgumentException) { return false; }
    }
}
