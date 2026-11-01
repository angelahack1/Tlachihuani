// Tlachihuani — Angela López Mendoza · XAIHT
using Tlachihuani.Contracts;

namespace Tlachihuani.Tray;

internal sealed class StatusForm : StudioForm
{
    private readonly Label state = Studio.Label("Checking…", Studio.Heading, Studio.Text);
    private readonly Label health = Studio.Label("Waiting for the service", Studio.Regular);
    private readonly Label version = Studio.Label("—", Studio.Metric, Studio.Text);
    private readonly Label pid = Studio.Label("—", Studio.Metric, Studio.Text);
    private readonly Label uptime = Studio.Label("—", Studio.Metric, Studio.Text);
    private readonly Label api = Studio.Label("Checking…", Studio.Strong, Studio.Muted);
    private readonly Label note = Studio.Label("", Studio.Small, Studio.Muted);
    private readonly StudioButton start, stop, restart;
    internal event Action<string>? Requested;
    internal event Action? ExitRequested;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    internal bool AllowExit { get; set; }

    public StatusForm(Icon icon) : base(icon, "Tlachihuani", "XAIHT   /   Tlachihuani", "Service overview", new(706, 434), new(620, 420))
    {
        StartPosition = FormStartPosition.CenterScreen;
        var services = Command("Services…", () => { using var panel = new ServicesForm(icon); panel.ShowDialog(this); });
        services.AccessibleName = "Manage Tlachihuani services"; HeaderCommands.Controls.Add(services);

        var content = Studio.Grid([-1], [25, 65, 8, 66, 15, 36, -1]);
        content.Controls.Add(Studio.Label("PRIMARY SERVICE", Studio.Caption, Studio.Muted), 0, 0);
        var summary = Studio.Grid([-1.45f, -1], [-1]);
        var signal = Studio.Grid([-1], [0, -1]);
        signal.RowStyles[0].SizeType = SizeType.AutoSize;
        state.AutoSize = true; state.AutoEllipsis = false;
        signal.Controls.Add(state, 0, 0); signal.Controls.Add(health, 0, 1);
        summary.Controls.Add(signal, 0, 0);
        var endpoint = Studio.Grid([-1], [21, -1]);
        endpoint.Controls.Add(Studio.Label("TORRENTER API", Studio.Caption, Studio.Muted), 0, 0);
        endpoint.Controls.Add(api, 0, 1);
        summary.Controls.Add(Studio.Card(endpoint, new Padding(12, 5, 8, 6)), 1, 0);
        content.Controls.Add(summary, 0, 1);
        var metrics = Studio.Grid([-1, -1, -1], [-1]);
        void Metric(int column, string title, Label value)
        {
            var group = Studio.Grid([-1], [21, -1]); group.Controls.Add(Studio.Label(title, Studio.Caption, Studio.Muted), 0, 0);
            group.Controls.Add(value, 0, 1);
            var card = Studio.Card(group, new Padding(12, 5, 8, 6));
            card.Margin = new Padding(0, 0, column == 2 ? 0 : 8, 0); metrics.Controls.Add(card, column, 0);
        }
        Metric(0, "VERSION", version); Metric(1, "PROCESS ID", pid); Metric(2, "UPTIME", uptime);
        content.Controls.Add(metrics, 0, 3);
        start = Command("Start", () => Requested?.Invoke("start"), ButtonTone.Primary);
        stop = Command("Stop", () => Requested?.Invoke("stop"));
        restart = Command("Restart", () => Requested?.Invoke("restart"));
        start.Enabled = stop.Enabled = restart.Enabled = false;
        content.Controls.Add(Studio.Actions(start, stop, restart), 0, 5);
        content.Controls.Add(note, 0, 6); BodyArea.Controls.Add(content);
        var close = Command("Close", Hide);
        Commands.Controls.AddRange([close, Command("Refresh", () => Requested?.Invoke("status")), Command("Exit tray", () => ExitRequested?.Invoke())]);
        CancelButton = close;
        FormClosing += (_, e) => { if (!AllowExit && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
    }

    internal void Render(ControlReply result, JobsState? jobs, bool busy)
    {
        var service = result.Service;
        state.Text = Pretty(service?.ScmState ?? "unavailable");
        state.ForeColor = service?.Health == "healthy" ? Studio.AccentHover : Studio.Text;
        api.Text = jobs is null ? "Unknown" : jobs.ApiReady ? "Ready   ·   12064" : "Offline";
        api.ForeColor = jobs?.ApiReady == true ? Studio.AccentHover : Studio.Muted;
        health.Text = service?.Health == "healthy" ? "Healthy · heartbeat received" : service?.ScmState switch
        {
            "not_installed" => "Waiting for service installation", "stopped" => "No heartbeat while the service is stopped",
            "start_pending" => "Waiting for the service to become ready", "stop_pending" => "The service is shutting down", _ => "Health unavailable"
        };
        version.Text = service?.Version ?? "—"; pid.Text = service?.Pid?.ToString() ?? "—";
        uptime.Text = service?.UptimeSeconds is double seconds ? TimeSpan.FromSeconds(seconds).ToString(@"d\.hh\:mm\:ss") : "—";
        note.Text = result.Error?.Message ?? (service?.ScmState == "not_installed" ? "Install Tlachihuani to enable these controls." : "Use Services… to manage the Jobs host and Torrenter.");
        note.ForeColor = result.Error is null ? Studio.Muted : Studio.Danger;
        FooterNote.Text = busy ? "Working…" : $"Observed {result.ObservedAtUtc.ToLocalTime():HH:mm:ss}";
        start.Enabled = !busy && result.Capabilities?.Start == true && service?.ScmState == "stopped";
        stop.Enabled = !busy && result.Capabilities?.Stop == true && service?.ScmState is "running" or "paused";
        restart.Enabled = !busy && result.Capabilities?.Restart == true && service?.ScmState == "running";
    }

    internal static string Pretty(string value) => value switch
    {
        "not_installed" => "Not installed", "stopped" => "Stopped", "start_pending" => "Starting…", "running" => "Running",
        "stop_pending" => "Stopping…", "paused" => "Paused", _ => "Unavailable"
    };
}
