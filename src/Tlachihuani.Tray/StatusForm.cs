// Tlachihuani — Angela López Mendoza · XAIHT
using Tlachihuani.Contracts;

namespace Tlachihuani.Tray;

internal sealed class StatusForm : Form
{
    private readonly Label state = TextLabel("Checking service…", 21, true);
    private readonly Label health = TextLabel("Waiting for a fresh observation", 11);
    private readonly Label details = TextLabel("", 10);
    private readonly Label note = TextLabel("", 10);
    private readonly Label observed = TextLabel("", 9);
    private readonly Button start = ActionButton("Start");
    private readonly Button stop = ActionButton("Stop");
    private readonly Button restart = ActionButton("Restart");
    internal event Action<string>? Requested;
    internal event Action? ExitRequested;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    internal bool AllowExit { get; set; }

    public StatusForm(Icon icon)
    {
        Text = "Tlachihuani"; Icon = icon;
        BackColor = ColorTranslator.FromHtml("#4a4f5c"); ForeColor = ColorTranslator.FromHtml("#f0f1f7");
        Font = new Font("Segoe UI", 10); AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(600, 430); MinimumSize = new Size(560, 450); StartPosition = FormStartPosition.CenterScreen;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(24), ColumnCount = 1, RowCount = 7 };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 56));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 49));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 71));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        var heading = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        heading.Controls.Add(new PictureBox { Image = icon.ToBitmap(), SizeMode = PictureBoxSizeMode.Zoom, Size = new Size(38, 38), Margin = new Padding(0, 0, 12, 0) });
        var title = TextLabel("Tlachihuani · Windows service", 15, true);
        title.Dock = DockStyle.None; title.Size = new Size(450, 38);
        heading.Controls.Add(title);
        layout.Controls.Add(heading); layout.Controls.Add(state); layout.Controls.Add(health); layout.Controls.Add(details); layout.Controls.Add(note);
        var observationRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Margin = Padding.Empty };
        observationRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); observationRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        var exit = new LinkLabel { Text = "Exit tray", AccessibleName = "Exit tray; service keeps running", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleRight, LinkColor = ColorTranslator.FromHtml("#55bbaa") };
        exit.LinkClicked += (_, _) => ExitRequested?.Invoke(); observationRow.Controls.Add(observed); observationRow.Controls.Add(exit); layout.Controls.Add(observationRow);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false };
        var refresh = ActionButton("Refresh"); var close = ActionButton("Close");
        refresh.Click += (_, _) => Requested?.Invoke("status");
        start.Click += (_, _) => Requested?.Invoke("start"); stop.Click += (_, _) => Requested?.Invoke("stop"); restart.Click += (_, _) => Requested?.Invoke("restart"); close.Click += (_, _) => Hide();
        buttons.Controls.AddRange([refresh, start, stop, restart, close]); layout.Controls.Add(buttons); Controls.Add(layout);
        CancelButton = close;
        FormClosing += (_, e) => { if (!AllowExit && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
    }

    internal void Render(ControlReply result, bool busy)
    {
        var service = result.Service;
        state.Text = Pretty(service?.ScmState ?? "unavailable");
        health.Text = service?.Health == "healthy" ? "Healthy · heartbeat received" : service?.ScmState switch
        {
            "not_installed" => "Waiting for service installation", "stopped" => "No heartbeat while the service is stopped", "start_pending" => "Waiting for the service to become ready", "stop_pending" => "The service is shutting down", _ => "Health unavailable"
        };
        state.ForeColor = service?.Health == "healthy" ? ColorTranslator.FromHtml("#55bbaa") : ForeColor;
        details.Text = $"Version  {service?.Version ?? "—"}       Process  {service?.Pid?.ToString() ?? "—"}\nUptime  {(service?.UptimeSeconds is double seconds ? TimeSpan.FromSeconds(seconds).ToString(@"d\.hh\:mm\:ss") : "—")}";
        note.Text = result.Error?.Message ?? (service?.ScmState == "not_installed" ? "Install Tlachihuani to enable service controls. The tray will remain available." : "Closing this window or exiting the tray leaves the service unchanged.");
        observed.Text = $"Observed {result.ObservedAtUtc.ToLocalTime():HH:mm:ss}" + (busy ? " · Working…" : "");
        start.Enabled = !busy && result.Capabilities?.Start == true && service?.ScmState == "stopped";
        stop.Enabled = !busy && result.Capabilities?.Stop == true && service?.ScmState is "running" or "paused";
        restart.Enabled = !busy && result.Capabilities?.Restart == true && service?.ScmState == "running";
    }

    internal static string Pretty(string value) => value switch
    {
        "not_installed" => "Not installed", "stopped" => "Stopped", "running" => "Running", "start_pending" => "Starting…", "stop_pending" => "Stopping…", "paused" => "Paused", _ => "Unavailable"
    };
    private static Label TextLabel(string text, float size, bool bold = false) => new() { Text = text, AutoSize = false, Dock = DockStyle.Fill, Font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular), TextAlign = ContentAlignment.MiddleLeft, AutoEllipsis = true };
    private static Button ActionButton(string text) => new() { Text = text, AccessibleName = text + " Tlachihuani", Width = 92, Height = 34, FlatStyle = FlatStyle.Flat, BackColor = ColorTranslator.FromHtml("#444853"), ForeColor = ColorTranslator.FromHtml("#f0f1f7"), Margin = new Padding(0, 3, 8, 0) };
}
