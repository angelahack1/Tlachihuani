// Tlachihuani — Angela López Mendoza · XAIHT
using System.Diagnostics;
using System.Text.Json.Nodes;
using Tlachihuani.Core;
using Tlachihuani.Windows;

namespace Tlachihuani.Tray;

internal sealed partial class ServicesForm : StudioForm
{
    private readonly CancellationTokenSource closing = new();
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 4000 };
    private readonly SemaphoreSlim gate = new(1);
    private bool changing;
    private string impact = "";
    private bool enabled, engine, web, catalogAvailable;
    private string host = "unknown";

    private async Task Run(Func<Task>? action = null)
    {
        if (changing || closing.IsCancellationRequested) return;
        var token = closing.Token;
        if (action is null && !gate.Wait(0)) return;
        if (action is not null)
        {
            changing = true; UpdateActions();
            try { await gate.WaitAsync(token); } catch (OperationCanceledException) { return; }
        }
        try
        {
            if (action is not null) await action();
            if (!token.IsCancellationRequested) await RefreshState();
        }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            if (!token.IsCancellationRequested)
            {
                if (action is not null) ServiceDialogs.Notice(this, "Service action failed", ex.Message);
                else { enabled = engine = web = catalogAvailable = false; PaintState(); impactLine.Text = "Service status could not be refreshed."; }
            }
        }
        finally
        {
            gate.Release();
            if (action is not null) changing = false;
            if (!token.IsCancellationRequested) UpdateActions();
        }
    }
    private async Task<JsonObject> Call(JsonObject request)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(closing.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(8));
        return await Task.Run(() => JobsEndpoint.CallInstalledAsync(request, timeout.Token), timeout.Token);
    }
    private async Task RefreshState()
    {
        host = "unavailable";
        var scm = await Task.Run(() => ScmBackend.ForJobs().Query(), closing.Token);
        if (closing.IsCancellationRequested) return;
        host = scm.State; enabled = engine = web = catalogAvailable = false; impact = "";
        if (host == "running")
        {
            var catalog = await Call(new() { ["op"] = "catalog" });
            if (closing.IsCancellationRequested) return;
            var result = catalog["providers"]!.AsArray().First(item => (string?)item?["provider"] == "torrenter")!;
            catalogAvailable = true;
            enabled = (bool?)result["enabled"] == true; engine = (bool?)result["engine"] == true; web = (bool?)result["web"] == true;
            if (result["impact"] is JsonObject counts) impact = $"{counts["active"]} active transfers across {counts["records"]} records.";
        }
        PaintState(); FooterNote.Text = $"Observed {DateTime.Now:HH:mm:ss}";
    }

    private void UpdateActions()
    {
        bool running = host == "running", idle = !changing;
        buttons["Start Jobs"].Enabled = idle && host == "stopped"; buttons["Stop Jobs"].Enabled = idle && running;
        buttons["Start provider"].Enabled = idle && running && catalogAvailable && !enabled;
        buttons["Stop provider"].Enabled = buttons["Restart provider"].Enabled = buttons["Restart web"].Enabled = idle && running && enabled;
        buttons["Open downloads"].Enabled = buttons["Open workspace"].Enabled = idle && web;
        foreach (string key in new[] { "Review erasure", "Issue API credential", "Revoke access" })
            buttons[key].Enabled = idle && engine;
    }
    private async Task HostAction(string op)
    {
        if(op=="stop"&&!ServiceDialogs.Confirm(this, "Stop the Jobs host?", "Active transfers will be checkpointed. " + impact, "Stop Jobs"))return;
        await Task.Run(async()=>{var scm=ScmBackend.ForJobs();scm.ValidateJobsInstallation();await new Lifecycle(scm).ExecuteAsync(op,TimeSpan.FromSeconds(30),closing.Token);});
    }
    private async Task Provider(string op)
    {
        if(op!="start"&&!ServiceDialogs.Confirm(this, op == "stop" ? "Stop Torrenter?" : "Restart Torrenter?", "Active transfers will be checkpointed. " + impact, op == "stop" ? "Stop provider" : "Restart provider"))return;
        await Call(new(){["op"]=op});
    }
    private async Task OpenWorkspace()
    {
        var current=await Call(new(){["op"]="status"});
        if((bool?)current["web"]!=true)throw new InvalidOperationException("The workspace is offline.");
        Process.Start(new ProcessStartInfo("http://127.0.0.1:12064/"){UseShellExecute=true});
    }
    private async Task Revoke()
    {
        if (ServiceDialogs.Confirm(this, "Revoke account access?", "This revokes all REST sessions and enrolled gateways for your Windows account.", "Revoke access"))
            await Call(new() { ["op"] = "revoke" });
    }
    private async Task Issue()
    {
        var request = ServiceDialogs.RequestCredential(this);
        if (request is null) return;
        var result = await Call(new() { ["op"] = "issue", ["profile"] = request.Value.Account, ["scope"] = request.Value.Scope });
        if (!closing.IsCancellationRequested) ServiceDialogs.ShowCredential(this, (string?)result["access_token"] ?? throw new InvalidDataException("No credential was returned."));
    }
    private async Task ReviewDeletion()
    {
        var pending = await Call(new() { ["op"] = "pending-deletions" });
        if (closing.IsCancellationRequested) return;
        var items = pending["items"]!.AsArray();
        if (items.Count == 0) { ServiceDialogs.Notice(this, "File erasure", "There are no pending file-erasure requests."); return; }
        foreach (var item in items)
        {
            var preview = await Call(new() { ["op"] = "deletion-details", ["preview_id"] = (string?)item!["preview_id"] });
            if (closing.IsCancellationRequested) return;
            if (ServiceDialogs.ReviewFiles(this, preview))
                await Call(new() { ["op"] = "approve-delete", ["preview_id"] = (string?)item["preview_id"], ["manifest_digest"] = (string?)preview["manifest_digest"] });
        }
    }
    protected override void Dispose(bool disposing){if(disposing){timer.Dispose();closing.Dispose();}base.Dispose(disposing);}
}
