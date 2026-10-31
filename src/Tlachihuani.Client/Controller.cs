// Tlachihuani — Angela López Mendoza · XAIHT
using System.ComponentModel;
using Tlachihuani.Contracts;
using Tlachihuani.Core;
using Tlachihuani.Windows;

namespace Tlachihuani.Client;

public sealed record DevelopmentTarget(Guid Id, int Pid, string ServicePath);

public sealed class Controller(DevelopmentTarget? development = null)
{
    public async Task<ControlReply> ExecuteAsync(string operation, CancellationToken token = default, long cursor = 0)
    {
        var requestId = Guid.NewGuid();
        Installation? installation = null;
        ServiceStatus? observed = null;
        Capabilities? capabilities = null;
        var mode = development is null ? "installed" : "development";
        ControlReply Result(bool ok, string phase, ErrorInfo? error = null, IReadOnlyList<ServiceEvent>? events = null, long? nextCursor = null, bool cursorExpired = false) =>
            new(Protocol.Major, requestId, ok, operation, phase, DateTimeOffset.UtcNow, mode, installation?.InstallationId ?? development?.Id, observed, capabilities, error, events, nextCursor, cursorExpired);
        try
        {
            if (operation is not ("status" or "events" or "start" or "stop" or "restart"))
                throw new LifecycleException("invalid_request", "Supported commands: status, events, start, stop, restart. Force-stop is not implemented in this foundation.");
            if (cursor < 0) throw new LifecycleException("invalid_request", "Event cursor must be nonnegative.");
            NativeStatus native;
            if (development is null)
            {
                var scm = new ScmBackend();
                native = scm.Query();
                observed = ToStatus(native);
                if (native.State == "not_installed")
                {
                    capabilities = new(false, false, false, false, "Install Tlachihuani before controlling it.");
                    if (operation == "status") return Result(true, "succeeded");
                    throw new LifecycleException("not_installed", "Tlachihuani is not installed.");
                }
                installation = Installation.Load();
                scm.ValidateInstallation(installation);
                var allowed = scm.CanControl();
                capabilities = new(allowed, allowed, allowed, false, allowed ? "Force-stop requires the later consent helper." : "This Windows account lacks Start/Stop permission.");
                if (operation is "start" or "stop" or "restart")
                {
                    native = await LifecycleGate.RunAsync(installation, operation, token);
                    observed = ToStatus(native);
                    // SCM completion is sufficient; mutations never wait for a healthy pipe.
                    return Result(true, "succeeded");
                }
            }
            else
            {
                capabilities = new(false, false, false, false, "Console development mode supports status and events only; stop it with Ctrl+C.");
                native = new("not_applicable", development.Pid);
                observed = ToStatus(native);
                if (operation is not ("status" or "events"))
                    throw new LifecycleException("invalid_request", capabilities.Reason!);
            }

            if (native.Pid == 0 || native.State is not ("running" or "start_pending" or "not_applicable"))
            {
                if (operation == "events") throw new LifecycleException("unavailable", "Service events are available only while the service is running.");
                return Result(true, "succeeded");
            }
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(TimeSpan.FromSeconds(3));
            var id = installation?.InstallationId ?? development!.Id;
            var pipeName = installation?.PipeName ?? Installation.DevelopmentPipe(id);
            var path = installation?.ServicePath ?? development!.ServicePath;
            using var pipe = await LocalPipe.ConnectAsync(pipeName, deadline.Token);
            using var process = LocalPipe.VerifyServer(pipe, native.Pid, path);
            var request = new Request(Protocol.Major, Protocol.Minor, requestId, operation, cursor);
            await Protocol.WriteAsync(pipe, request, deadline.Token);
            var reply = await Protocol.ReadAsync<Reply>(pipe, deadline.Token);
            // Acknowledge receipt before the server disconnects/reuses this pipe instance.
            // DisconnectNamedPipe otherwise discards unread buffered bytes under concurrency.
            await pipe.WriteAsync(new byte[] { 0x06 }, deadline.Token);
            if (reply.ProtocolMajor != Protocol.Major) throw new ProtocolException("incompatible_protocol", "The service uses an incompatible protocol.");
            if (reply.RequestId != requestId || reply.InstallationId != id || process.HasExited)
                throw new LifecycleException("identity_changed", "The service identity changed during this observation.");
            if (development is null && new ScmBackend().Query().Pid != native.Pid)
                throw new LifecycleException("identity_changed", "SCM reports a different service process; refresh the status.");
            if (!reply.Ok) throw new ProtocolException(reply.Error?.Code ?? "unavailable", reply.Error?.Message ?? "The service refused the request.");
            if (reply.Service is null || reply.Service.Pid != native.Pid || reply.Service.InstanceId == Guid.Empty)
                throw new ProtocolException("invalid_response", "The service response is missing its identity.");
            var health = reply.Service;
            var heartbeatAge = DateTimeOffset.UtcNow - health.LastHeartbeatUtc;
            var healthName = heartbeatAge > TimeSpan.FromSeconds(6) || heartbeatAge < TimeSpan.FromSeconds(-5) ? "degraded" : health.Health;
            observed = new(Protocol.ServiceName, native.State, healthName, native.Pid, health.InstanceId, health.Version, Math.Round(health.UptimeSeconds, 2), health.LastHeartbeatUtc);
            return Result(true, "succeeded", events: reply.Events, nextCursor: reply.NextCursor, cursorExpired: reply.CursorExpired);
        }
        catch (Exception ex) when (ex is LifecycleException or ProtocolException or Win32Exception or IOException or OperationCanceledException or UnauthorizedAccessException or System.Text.Json.JsonException or ArgumentException)
        {
            var code = ex switch
            {
                LifecycleException value => value.Code,
                ProtocolException value => value.Code,
                Win32Exception { NativeErrorCode: 5 } => "access_denied",
                UnauthorizedAccessException => "access_denied",
                Win32Exception { NativeErrorCode: 1060 } => "not_installed",
                OperationCanceledException when token.IsCancellationRequested => "canceled",
                OperationCanceledException => "timeout",
                _ => "unavailable"
            };
            var message = ex is LifecycleException or ProtocolException ? ex.Message : code switch
            {
                "access_denied" => "This Windows account does not have the required permission.",
                "timeout" => "The service did not answer before the deadline. Its SCM state is shown separately.",
                "canceled" => "The operation was canceled.",
                _ => "Tlachihuani could not be reached or its installation could not be verified."
            };
            if (code is "identity_changed" or "incompatible_protocol") capabilities = new(false, false, false, false, message);
            return Result(false, code == "timeout" ? "timed_out" : code == "canceled" ? "canceled" : "failed", new(code, message, (ex as Win32Exception)?.NativeErrorCode));
        }
    }

    private static ServiceStatus ToStatus(NativeStatus status) => new(Protocol.ServiceName, status.State, "unknown", status.Pid == 0 ? null : status.Pid, null, null, null, null);
}
