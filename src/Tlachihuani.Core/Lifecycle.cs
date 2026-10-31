// Tlachihuani — Angela López Mendoza · XAIHT
namespace Tlachihuani.Core;

public sealed record NativeStatus(string State, int Pid = 0, int NativeExitCode = 0);

public interface IServiceBackend
{
    NativeStatus Query();
    void Start();
    void Stop();
}

public sealed class LifecycleException(string code, string message) : Exception(message)
{
    public string Code { get; } = code;
}

public sealed class Lifecycle(IServiceBackend backend)
{
    // The caller owns the installation-wide mutation lock for the entire operation.
    public async Task<NativeStatus> ExecuteAsync(string action, TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (action is not ("start" or "stop" or "restart"))
            throw new LifecycleException("invalid_request", "Unknown lifecycle action.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(timeout);
        try
        {
            if (action is "stop" or "restart") await StopAsync(deadline.Token);
            if (action is "start" or "restart") await StartAsync(deadline.Token);
            return backend.Query();
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new LifecycleException("timeout", "The service did not reach the requested state before the deadline. Refresh its status; no force termination was attempted.");
        }
    }

    private NativeStatus Installed()
    {
        var state = backend.Query();
        if (state.State == "not_installed")
            throw new LifecycleException("not_installed", "Tlachihuani is not installed. Start never installs a service.");
        return state;
    }

    private async Task StartAsync(CancellationToken token)
    {
        var current = Installed();
        if (current.State == "stop_pending") current = await WaitAsync("stopped", token);
        if (current.State == "running") return;
        if (current.State == "stopped") backend.Start();
        else if (current.State != "start_pending")
            throw new LifecycleException("busy", $"Cannot start while SCM reports {current.State}.");
        await WaitAsync("running", token);
    }

    private async Task StopAsync(CancellationToken token)
    {
        var current = Installed();
        if (current.State == "stopped") return;
        while (current.State == "start_pending")
        {
            await Task.Delay(200, token);
            current = Installed();
        }
        // Startup can fail and leave the service stopped while a Stop request waits.
        if (current.State == "stopped") return;
        if (current.State is "running" or "paused") backend.Stop();
        else if (current.State != "stop_pending")
            throw new LifecycleException("busy", $"Cannot stop while SCM reports {current.State}.");
        await WaitAsync("stopped", token);
    }

    private async Task<NativeStatus> WaitAsync(string target, CancellationToken token)
    {
        while (true)
        {
            token.ThrowIfCancellationRequested();
            var current = Installed();
            if (current.State == target) return current;
            if (target == "running" && current.State == "stopped")
                throw new LifecycleException("start_failed", $"The service stopped before reaching Running (Windows error {current.NativeExitCode}).");
            await Task.Delay(200, token);
        }
    }
}
