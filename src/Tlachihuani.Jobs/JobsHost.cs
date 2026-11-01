using System.IO.Pipes;
using System.Security.Principal;
using System.Text.Json.Nodes;
using Tlachihuani.Contracts;
using Tlachihuani.Windows;

namespace Tlachihuani.Jobs;

internal sealed class JobsHost(JobsSettings settings, ILogger<JobsHost> log) : BackgroundService
{
    // Each registered provider owns its own supervision loop, process handles and stop policy.
    private readonly Dictionary<string, IJobProvider> providers = new(StringComparer.Ordinal) { ["torrenter"] = new TorrenterProvider(settings, log) };

    protected override async Task ExecuteAsync(CancellationToken token)
    {
        Directory.CreateDirectory(settings.State);
        // Exclusive data owner even in console mode.
        using var owned = new FileStream(Path.Combine(settings.State, "jobs.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        var listeners = new List<NamedPipeServerStream>();
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(token);
        try
        {
            for (int i = 0; i < 4; i++) listeners.Add(LocalPipe.CreateServer(settings.Pipe, settings.Operator, i == 0));
            var tasks = listeners.Select(pipe => Listen(pipe, stop.Token)).Concat(providers.Values.Select(provider => provider.RunAsync(stop.Token))).ToArray();
            await Task.WhenAny(tasks);
            stop.Cancel();
            await Task.WhenAll(tasks);
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        finally
        {
            foreach (var pipe in listeners) pipe.Dispose();
            await Task.WhenAll(providers.Values.Select(provider => provider.Halt()));
        }
    }
    private async Task Listen(NamedPipeServerStream pipe, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            await pipe.WaitForConnectionAsync(token);
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(TimeSpan.FromSeconds(20));
            try
            {
                var req = await Protocol.ReadAsync<JsonObject>(pipe, deadline.Token);
                string? sid = null;
                string? proposedRoot = (string?)req["delivery_root"];
                string? proposedFallback = (string?)req["fallback_root"];
                bool requestedFallback = proposedFallback is not null || req.ContainsKey("fallback_error");
                req.Remove("fallback_root");
                req.Remove("fallback_error");
                req.Remove("delivery_root");
                req.Remove("delivery_error");
                pipe.RunAsClient(() =>
                {
                    using var client = WindowsIdentity.GetCurrent(true);
                    sid = client?.User?.Value;
                });
                if (sid is null) throw new UnauthorizedAccessException();
                if ((string?)req["op"] == "issue")
                {
                    try
                    {
                        req["delivery_root"] = DownloadDelivery.Validate(proposedRoot, sid, (string?)req["profile"] ?? "");
                    }
                    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
                    {
                        // Authentication remains usable to diagnose/retry a disconnected or
                        // read-only Downloads folder. Never report delivery as successful.
                        req["delivery_error"] = "Cannot prepare Windows Downloads: " + ex.Message;
                    }
                    if (requestedFallback)
                    {
                        try { req["fallback_root"] = DownloadDelivery.Validate(proposedFallback, sid, (string?)req["profile"] ?? "", fallback: true); }
                        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
                        { req["fallback_error"] = "Cannot prepare content_generated: " + ex.Message; }
                    }
                }
                JsonObject reply;
                if ((string?)req["op"] == "catalog")
                {
                    var entries = new JsonArray();
                    foreach (var item in providers.Values) entries.Add(await item.CommandAsync(new() { ["op"] = "status" }, sid, deadline.Token));
                    reply = new() { ["protocol_major"] = 2, ["providers"] = entries };
                }
                else if (providers.TryGetValue((string?)req["provider"] ?? "torrenter", out var provider))
                {
                    reply = await provider.CommandAsync(req, sid, deadline.Token);
                }
                else reply = new() { ["code"] = 404, ["body"] = new JsonObject { ["error"] = "Unknown provider." } };
                await Protocol.WriteAsync(pipe, reply, deadline.Token);
                await pipe.ReadExactlyAsync(new byte[1], deadline.Token);
            }
            catch (Exception ex) when (!token.IsCancellationRequested)
            {
                log.LogDebug("Native request ended: {Type}", ex.GetType().Name);
            }
            finally { pipe.Disconnect(); }
        }
    }
}

internal interface IJobProvider
{
    string Id { get; }
    Task RunAsync(CancellationToken token);
    Task Halt();
    Task<JsonObject> CommandAsync(JsonObject request, string operatorSid, CancellationToken token);
}
