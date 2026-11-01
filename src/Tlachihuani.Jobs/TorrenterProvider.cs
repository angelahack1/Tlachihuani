using System.Text.Json.Nodes;

namespace Tlachihuani.Jobs;

internal sealed class TorrenterProvider(JobsSettings settings, ILogger log) : IJobProvider
{
    public string Id => "torrenter";
    private readonly WorkerChannel worker = new();
    private readonly SemaphoreSlim lifecycle = new(1, 1);
    private CancellationTokenSource? webStop;
    private Task? webTask;
    private volatile bool webReady;
    private volatile bool enabled;
    private string Disabled => Path.Combine(settings.State, "torrenter.disabled");

    public async Task RunAsync(CancellationToken token)
    {
        enabled = !File.Exists(Disabled);
        while (!token.IsCancellationRequested)
        {
            await lifecycle.WaitAsync(token);
            try
            {
                if (enabled && !worker.Running) worker.Start(settings);
                if (enabled && (webTask is null || webTask.IsCompleted))
                {
                    webStop?.Dispose();
                    webStop = CancellationTokenSource.CreateLinkedTokenSource(token);
                    webTask = PumpWeb(webStop.Token);
                }
            }
            catch (Exception ex) { log.LogError("Provider start failed: {Message}", ex.Message); }
            finally { lifecycle.Release(); }
            await Task.Delay(2000, token);
        }
    }
    public async Task Halt()
    {
        await StopWeb();
        worker.Dispose();
    }
    private async Task StopWeb()
    {
        if (webStop is not null) await webStop.CancelAsync();
        if (webTask is not null) await webTask;
        webTask = null;
        webStop?.Dispose(); webStop = null;
    }
    private async Task PumpWeb(CancellationToken token)
    {
        try
        {
            using var web = WorkerChannel.Spawn(Environment.ProcessPath!, ["--web", settings.Port.ToString()]);
            try
            {
                if (await web.StandardOutput.ReadLineAsync(token) != "READY") throw new IOException("Web did not bind its port.");
                webReady = true;
                while (await web.StandardOutput.ReadLineAsync(token) is string line)
                {
                    var req = JsonNode.Parse(line)!.AsObject();
                    // Only Windows-authenticated native clients may enter the admin channel.
                    req.Remove("admin"); req.Remove("owner");
                    var reply = await worker.Request(req, token);
                    await web.StandardInput.WriteLineAsync(reply.ToJsonString().AsMemory(), token);
                }
            }
            finally
            {
                webReady = false;
                web.StandardInput.Close();
                if (!web.WaitForExit(1500)) web.Kill(true);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception ex) { log.LogWarning("Web facade unavailable: {Message}", ex.Message); }
    }
    public async Task<JsonObject> CommandAsync(JsonObject req, string sid, CancellationToken token)
    {
        var op = (string?)req["op"];
        await lifecycle.WaitAsync(token);
        JsonObject reply;
        try
        {
            if (op is "stop" or "restart")
            {
                if (op == "stop") File.WriteAllText(Disabled, "stopped");
                enabled = false;
                await Halt();
            }
            if (op is "start" or "restart") { File.Delete(Disabled); enabled = true; }
            if (op == "restart-web" && enabled) await StopWeb();
            if (op is "status" or "start" or "stop" or "restart" or "restart-web")
            {
                reply = new()
                {
                    ["provider"] = Id,
                    ["enabled"] = enabled,
                    ["engine"] = worker.Running,
                    ["web"] = webReady,
                    ["port"] = settings.Port
                };
                if (op == "status" && worker.Running)
                {
                    try
                    {
                        var impact = await worker.Request(new() { ["admin"] = true, ["op"] = "impact", ["owner"] = sid }, token);
                        reply["impact"] = impact["body"]?.DeepClone();
                    }
                    catch (IOException) { reply["engine"] = false; }
                }
            }
            else if (op is "issue" or "approve-delete" or "pending-deletions" or "deletion-details" or "revoke")
            {
                req["admin"] = true; req["owner"] = sid;
                reply = await worker.Request(req, token);
            }
            else reply = new() { ["error"] = "Unknown provider operation." };
        }
        finally { lifecycle.Release(); }
        return reply;
    }
}
