// Tlachihuani — Angela López Mendoza · XAIHT
using System.Buffers.Binary;
using System.IO.Pipes;
using System.Diagnostics;
using Tlachihuani.Client;
using Tlachihuani.Contracts;
using Tlachihuani.Core;
using Tlachihuani.Windows;

if (args is ["--tray-layout", var directory, var mode]) return TrayLayoutChecks.Run(directory, mode);
if (args is ["--downloads-access"]) return DownloadAccessChecks.Run();

var passed = 0;
async Task Check(string name, Func<Task> body) { await body(); Console.WriteLine($"PASS {name}"); passed++; }
void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
async Task Reject<T>(Func<Task> body) where T : Exception { try { await body(); } catch (T) { return; } throw new InvalidOperationException($"Expected {typeof(T).Name}"); }
Request RequestFor(string operation) => new(1, 0, Guid.NewGuid(), operation);

try
{
    await Check("XT exit label follows service state and keeps the exit action", () =>
    {
        int exits = 0;
        using var menu = new Tlachihuani.Tray.TrayMenu(() => { }, _ => Task.CompletedTask, () => exits++);
        var exit = menu.Items[menu.Items.Count - 1];
        const string warning = "Exit tray (service keeps running)";
        Require(exit.Text == warning, "Unobserved services must retain the warning");
        foreach (var (ready, stopped, busy, label) in new[]
        {
            (false, true, false, "Exit tray"), (false, true, true, warning),
            (false, false, false, warning), (true, false, false, warning), (false, true, false, "Exit tray")
        })
        {
            menu.UpdateActions(null, ready, stopped, busy);
            Require(exit.Text == label, $"Unexpected exit label: {exit.Text}");
        }
        exit.PerformClick();
        Require(exits == 1, "Exit command lost its handler");
        return Task.CompletedTask;
    });
    await Check("Oversized and zero-length frames are rejected before allocation", async () =>
    {
        foreach (var size in new[] { 0, 65537, int.MaxValue, -1 })
        {
            var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, size);
            await Reject<ProtocolException>(() => Protocol.ReadAsync<Request>(new MemoryStream(header), default));
        }
    });
    await Check("Truncated frame and malformed UTF-8 fail", async () =>
    {
        await Reject<EndOfStreamException>(() => Protocol.ReadAsync<Request>(new MemoryStream([5, 0, 0, 0, 123]), default));
        await Reject<ProtocolException>(() => Protocol.ReadAsync<Request>(new MemoryStream([2, 0, 0, 0, 0xc3, 0x28]), default));
    });
    await Check("Unknown operations, protocol versions and unbounded cursors fail", async () =>
    {
        foreach (var request in new[] { RequestFor("execute"), RequestFor("status") with { ProtocolMajor = 2 }, RequestFor("events") with { Limit = 101 }, RequestFor("events") with { Cursor = -1 }, RequestFor("status") with { RequestId = Guid.Empty } })
            await Reject<ProtocolException>(() => { Protocol.Validate(request); return Task.CompletedTask; });
    });
    await Check("Bounded events expose expired cursors and a fresh instance per service boot", () =>
    {
        var first = new HealthState(); var second = new HealthState(); var installation = Guid.NewGuid();
        for (var i = 0; i < 300; i++) first.AddEvent("test", "bounded event");
        var page = first.Answer(RequestFor("events") with { Cursor = 1, Limit = 100 }, installation);
        Require(page.CursorExpired && page.Events?.Count == 100 && page.Events[0].Sequence == 45 && page.NextCursor == 144, "Event retention/cursor wrong");
        Require(page.Service!.InstanceId != second.Answer(RequestFor("status"), installation).Service!.InstanceId, "Boot IDs reused");
        return Task.CompletedTask;
    });
    await Check("Start and Stop are idempotent; Restart observes stop before start", async () =>
    {
        var backend = new FakeBackend(); var lifecycle = new Lifecycle(backend);
        await lifecycle.ExecuteAsync("start", TimeSpan.FromSeconds(1), default);
        await lifecycle.ExecuteAsync("start", TimeSpan.FromSeconds(1), default);
        Require(backend.Actions.SequenceEqual(["start"]), "Start repeated");
        await lifecycle.ExecuteAsync("restart", TimeSpan.FromSeconds(1), default);
        Require(backend.Actions.SequenceEqual(["start", "stop", "start"]), "Restart ordering");
        await lifecycle.ExecuteAsync("stop", TimeSpan.FromSeconds(1), default); await lifecycle.ExecuteAsync("stop", TimeSpan.FromSeconds(1), default);
        Require(backend.Actions.Count == 4 && backend.State == "stopped", "Stop repeated");
    });
    await Check("A missing service is never installed; a hung stop times out without killing", async () =>
    {
        var absent = new FakeBackend { State = "not_installed" };
        await Reject<LifecycleException>(() => new Lifecycle(absent).ExecuteAsync("start", TimeSpan.FromSeconds(1), default));
        Require(absent.Actions.Count == 0, "Missing service mutated");
        var hung = new FakeBackend { State = "running", HangStop = true };
        await Reject<LifecycleException>(() => new Lifecycle(hung).ExecuteAsync("stop", TimeSpan.FromMilliseconds(250), default));
        Require(hung.Actions.SequenceEqual(["stop"]) && hung.State == "stop_pending", "Unexpected termination");
    });
    await Check("Stop reconciles a failed pending start without issuing a second control", async () =>
    {
        var backend = new FakeBackend { State = "start_pending", FailPendingStart = true };
        var status = await new Lifecycle(backend).ExecuteAsync("stop", TimeSpan.FromSeconds(1), default);
        Require(status.State == "stopped" && backend.Actions.Count == 0, "Failed startup was not reconciled");
    });
    await Check("Local pipe works with bounded framing and verifies server executable", async () =>
    {
        var id = Guid.NewGuid(); var sid = System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
        using var server = LocalPipe.CreateServer(Installation.DevelopmentPipe(id), sid, true);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var serving = Task.Run(async () =>
        {
            await server.WaitForConnectionAsync(deadline.Token);
            var request = await Protocol.ReadAsync<Request>(server, deadline.Token);
            var health = new HealthState(); health.Pulse();
            await Protocol.WriteAsync(server, health.Answer(request, id), deadline.Token);
        });
        var result = await new Controller(new(id, Environment.ProcessId, Environment.ProcessPath!)).ExecuteAsync("status", deadline.Token);
        await serving;
        Require(result.Ok && result.Mode == "development" && result.Service?.Health == "healthy" && result.Service.ScmState == "not_applicable", "Pipe observation failed: " + result.Error);
    });
    await Check("A pipe process with the wrong executable is refused", async () =>
    {
        var id = Guid.NewGuid(); var sid = System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
        using var server = LocalPipe.CreateServer(Installation.DevelopmentPipe(id), sid, true);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var waiting = server.WaitForConnectionAsync(deadline.Token);
        var result = await new Controller(new(id, Environment.ProcessId, @"C:\not-the-service.exe")).ExecuteAsync("status", deadline.Token);
        await waiting;
        Require(!result.Ok && result.Error?.Code == "identity_changed", "Impersonating server accepted");
    });
    if (args.Length == 2 && args[0] == "--service-exe")
    {
        await Check("Real console host: ready, concurrent IPC, heartbeat and graceful shutdown", async () =>
        {
            var id = Guid.NewGuid();
            var info = new ProcessStartInfo(Path.GetFullPath(args[1])) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            info.ArgumentList.Add("--console"); info.ArgumentList.Add("--development-id"); info.ArgumentList.Add(id.ToString()); info.ArgumentList.Add("--run-for-seconds"); info.ArgumentList.Add("12");
            using var host = new Process { StartInfo = info };
            host.OutputDataReceived += (_, e) => { if (e.Data is not null) Console.WriteLine("SERVICE " + e.Data); };
            host.ErrorDataReceived += (_, e) => { if (e.Data is not null) Console.WriteLine("SERVICE ERROR " + e.Data); };
            host.Start(); host.BeginOutputReadLine(); host.BeginErrorReadLine();
            try
            {
                var client = new Controller(new(id, host.Id, info.FileName));
                var first = await client.ExecuteAsync("status");
                Require(first.Ok && first.Service?.Health == "healthy", "Real host failed: " + first.Error);
                Require(first.Service!.Version == typeof(HealthState).Assembly.GetName().Version!.ToString(3), "Service reported a stale product version");
                // A client may exit during a status request (including when it cannot verify
                // the server). Breaking one pipe must leave this same host serving other clients.
                using (var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3)))
                using (var abandoned = await LocalPipe.ConnectAsync(Installation.DevelopmentPipe(id), deadline.Token))
                    await abandoned.WriteAsync(new byte[] { 4, 0, 0, 0, 123 }, deadline.Token);
                var batch = await Task.WhenAll(Enumerable.Range(0, 32).Select(_ => client.ExecuteAsync("status")));
                Require(batch.All(reply => reply.Ok), "Concurrent clients failed: " + string.Join("; ", batch.Where(reply => !reply.Ok).Select(reply => reply.Error)));
                await Task.Delay(2200);
                var second = await client.ExecuteAsync("status");
                Require(second.Ok && first.Service!.InstanceId == second.Service!.InstanceId && first.Service.LastHeartbeatUtc < second.Service.LastHeartbeatUtc, "Heartbeat not advancing");
                var events = await client.ExecuteAsync("events");
                Require(events.Ok && events.Events?.Any(e => e.Kind == "ready") == true, "Ready event absent");
                Require(events.NextCursor > 0, "Event cursor omitted by controller");
                using (var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3)))
                using (var pipe = await LocalPipe.ConnectAsync(Installation.DevelopmentPipe(id), deadline.Token))
                {
                    var incompatible = RequestFor("status") with { ProtocolMajor = 99 };
                    await Protocol.WriteAsync(pipe, incompatible, deadline.Token);
                    var refused = await Protocol.ReadAsync<Reply>(pipe, deadline.Token);
                    await pipe.WriteAsync(new byte[] { 0x06 }, deadline.Token);
                    Require(!refused.Ok && refused.RequestId == incompatible.RequestId && refused.Error?.Code == "incompatible_protocol", "Protocol mismatch did not return a correlated error");
                }
                Require(!(await client.ExecuteAsync("stop")).Ok, "Development mutation accepted");
                using var exitDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                await host.WaitForExitAsync(exitDeadline.Token);
                Require(host.ExitCode == 0, "Graceful console host exit failed");
                var gone = await client.ExecuteAsync("status");
                Require(!gone.Ok, "Exited service still appears live");
            }
            finally
            {
                if (!host.HasExited) { host.Kill(); await host.WaitForExitAsync(); Console.WriteLine("FAIL cleanup: owned test host required termination"); }
            }
        });
    }
    else if (args.Length == 3 && Guid.TryParse(args[0], out var liveId) && int.TryParse(args[1], out var livePid))
    {
        await Check("Actual service host: heartbeat, events, and independent instance identity", async () =>
        {
            var controller = new Controller(new(liveId, livePid, args[2]));
            var first = await controller.ExecuteAsync("status"); await Task.Delay(2200);
            var second = await controller.ExecuteAsync("status"); var events = await controller.ExecuteAsync("events");
            Require(first.Ok && second.Ok && second.Service?.Health == "healthy", "Service unhealthy: " + first.Error);
            Require(first.Service!.InstanceId == second.Service!.InstanceId && first.Service.LastHeartbeatUtc < second.Service.LastHeartbeatUtc, "Heartbeat not advancing");
            Require(events.Ok && events.Events?.Any(e => e.Kind == "ready") == true, "Ready event absent");
            var refused = await controller.ExecuteAsync("stop"); Require(!refused.Ok, "Development mode exposed lifecycle mutation");
        });
    }
    Console.WriteLine($"RESULT: {passed} checks passed."); return 0;
}
catch (Exception ex) { Console.Error.WriteLine(ex); Console.Error.WriteLine($"RESULT: failed after {passed} checks."); return 1; }

sealed class FakeBackend : IServiceBackend
{
    public string State = "stopped";
    public bool HangStop;
    public bool FailPendingStart;
    private int queryCount;
    public List<string> Actions { get; } = [];
    public NativeStatus Query()
    {
        if (FailPendingStart && ++queryCount > 1) State = "stopped";
        return new(State);
    }
    public void Start() { Actions.Add("start"); State = "running"; }
    public void Stop() { Actions.Add("stop"); State = HangStop ? "stop_pending" : "stopped"; }
}
