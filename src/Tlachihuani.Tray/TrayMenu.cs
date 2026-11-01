// Tlachihuani — Angela López Mendoza · XAIHT
using System.Diagnostics;
using System.Text.Json;
using Tlachihuani.Contracts;

namespace Tlachihuani.Tray;

internal sealed class TrayMenu : ContextMenuStrip
{
    // These are presentation choices, not permissions. To restore a shortcut, add
    // its flag to Shown (use | for several). None means the six legacy rows are
    // never created, focusable or announced. The panel, tooltip and CLI are independent.
    [Flags]
    private enum Extra { None = 0, TlamatiniLink = 1, ServiceState = 2, Refresh = 4, Start = 8, Stop = 16, Restart = 32 }
    private const Extra Shown = Extra.None;
    private readonly ToolStripMenuItem? state, start, stop, restart;
    private readonly ToolStripMenuItem startServices, stopServices, exitItem;

    internal TrayMenu(Action showPanel, Func<string, Task> run, Action exitTray)
    {
        Items.Add("Show panel", null, (_, _) => showPanel());

        // Link: used to show a disabled placeholder or open the validated loopback URL.
        // To repurpose the destination, change AddTlamatiniLink; if retiring it
        // permanently, remove that helper and ReadTlamatiniUrl together.
        if (Shown.HasFlag(Extra.TlamatiniLink)) AddTlamatiniLink();

        // State: "Stopped" was a read-only observation, not a stop command. If
        // retired, remove only this row and SetState; keep the independent tooltip.
        if (Shown.HasFlag(Extra.ServiceState))
        {
            state = new ToolStripMenuItem("Checking service…") { Enabled = false };
            Items.Add(state);
        }

        // Refresh requests one observation through the same dispatcher as the
        // panel's Refresh button and polling timer. Removing this shortcut must
        // not remove the "status" operation or turn off polling.
        ToolStripMenuItem Command(string caption, string operation) =>
            (ToolStripMenuItem)Items.Add(caption, null, (_, _) => _ = run(operation));
        startServices = Command("Start Services", "start-services");
        stopServices = Command("Stop Services", "stop-services");
        if (Shown.HasFlag(Extra.Refresh)) Command("Refresh status", "status");

        // Start: request SCM start when stopped. Stop: graceful SCM stop when
        // running or paused. Restart: ordered stop/start when running. Keep the
        // capability and busy checks in UpdateActions for any reactivated row.
        // To drop just one shortcut, remove its flag, field, binding and enable
        // check here; StatusForm and Control.exe still use the underlying operation.
        if (Shown.HasFlag(Extra.Start)) start = Command("Start", "start");
        if (Shown.HasFlag(Extra.Stop)) stop = Command("Stop", "stop");
        if (Shown.HasFlag(Extra.Restart)) restart = Command("Restart", "restart");
        if (Items.Count > 1) Items.Add(new ToolStripSeparator());
        exitItem = (ToolStripMenuItem)Items.Add(string.Empty, null, (_, _) => exitTray());
        UpdateActions(null, ready: false, stopped: false, busy: false);
    }

    internal void SetState(string text)
    {
        if (state is not null) state.Text = text;
    }

    internal void UpdateActions(ControlReply? reply, bool ready, bool stopped, bool busy)
    {
        var scm = reply?.Service?.ScmState;
        startServices.Enabled = !busy && !ready;
        stopServices.Enabled = !busy && !stopped;
        exitItem.Text = stopped && !busy ? "Exit tray" : "Exit tray (service keeps running)";
        if (start is not null) start.Enabled = !busy && reply?.Capabilities?.Start == true && scm == "stopped";
        if (stop is not null) stop.Enabled = !busy && reply?.Capabilities?.Stop == true && scm is "running" or "paused";
        if (restart is not null) restart.Enabled = !busy && reply?.Capabilities?.Restart == true && scm == "running";
    }

    private void AddTlamatiniLink()
    {
        var url = ReadTlamatiniUrl();
        var open = new ToolStripMenuItem(url is null ? "Tlamatini link not configured" : "Open in Tlamatini") { Enabled = url is not null };
        open.Click += (_, _) =>
        {
            if (url is null) return;
            try { Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true }); }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
            { ServiceDialogs.Notice(null, "Open Tlamatini", "Windows could not open the configured Tlamatini link."); }
        };
        Items.Add(open);
    }

    private static Uri? ReadTlamatiniUrl()
    {
        try
        {
            var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XAIHT", "Tlachihuani", "tray.json");
            if (!File.Exists(path) || new FileInfo(path).Length > 4096) return null;
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            return doc.RootElement.TryGetProperty("tlamatini_url", out var value) && Uri.TryCreate(value.GetString(), UriKind.Absolute, out var url)
                && url.Scheme is "http" or "https" && url.IsLoopback && url.UserInfo.Length == 0 ? url : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException) { return null; }
    }
}
