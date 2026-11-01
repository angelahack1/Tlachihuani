// Tlachihuani — Angela López Mendoza · XAIHT
namespace Tlachihuani.Tray;

internal sealed partial class ServicesForm
{
    private readonly Label hostState = Studio.Label("Checking Jobs…", Studio.Small);
    private readonly Label engineState = Studio.Label("Engine · checking", Studio.Small);
    private readonly Label webState = Studio.Label("Web · checking", Studio.Small);
    private readonly Label impactLine = Studio.Label("", Studio.Small, Studio.Muted);
    private readonly StudioButton runtimeTab = new("Runtime", ButtonTone.Tab), accessTab = new("Access", ButtonTone.Tab);
    private readonly Dictionary<string, StudioButton> buttons = new();
    private readonly Control runtime, access;

    public ServicesForm(Icon icon) : base(icon, "Tlachihuani · Services", "Tlachihuani   /   Service control", "Services", new(778, 500), new(668, 466))
    {
        var layout = Studio.Grid([-1], [38, 8, -1]);
        var switcher = Studio.Actions(runtimeTab, accessTab);
        switcher.AccessibleName = "Service views"; layout.Controls.Add(switcher, 0, 0);
        var pages = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty };
        runtime = BuildRuntime(); access = BuildAccess(); pages.Controls.Add(runtime); pages.Controls.Add(access);
        layout.Controls.Add(pages, 0, 2); BodyArea.Controls.Add(layout);
        runtimeTab.Click += (_, _) => ShowView(false); accessTab.Click += (_, _) => ShowView(true);
        foreach (var tab in new[] { runtimeTab, accessTab }) tab.KeyDown += (_, e) =>
        {
            if (e.KeyCode is not (Keys.Left or Keys.Right)) return;
            bool showAccess = runtimeTab.Selected; ShowView(showAccess);
            (showAccess ? accessTab : runtimeTab).Focus(); e.Handled = true;
        };
        ShowView(false);
        var close = Command("Close", Close); Commands.Controls.Add(close);
        Commands.Controls.Add(Command("Refresh", () => _ = Run())); CancelButton = close;
        UpdateActions();
        timer.Tick += async (_, _) => await Run();
        Shown += async (_, _) => { timer.Start(); await Run(); };
        FormClosed += (_, _) => { timer.Stop(); closing.Cancel(); };
    }

    private void ShowView(bool showAccess)
    {
        runtime.Visible = !showAccess; access.Visible = showAccess;
        runtimeTab.SelectTab(!showAccess); accessTab.SelectTab(showAccess);
        runtimeTab.AccessibleDescription = showAccess ? "Show service runtime" : "Selected view";
        accessTab.AccessibleDescription = showAccess ? "Selected view" : "Show access controls";
    }
    private StudioButton ActionButton(string caption, Func<Task> action, ButtonTone tone = ButtonTone.Secondary)
    {
        var button = Command(caption, () => _ = Run(action), tone); buttons.Add(caption, button); return button;
    }
    private static Control CommandRow(string title, Label detail, params Control[] actions)
    {
        var labels = Studio.Grid([-1], [-1, 24, 23, -1]);
        labels.Controls.Add(Studio.Label(title, Studio.Strong, Studio.Text), 0, 1); labels.Controls.Add(detail, 0, 2);
        var row = Studio.Grid([-1, actions.Sum(x => x.Width + x.Margin.Horizontal)], [-1]);
        row.Controls.Add(labels, 0, 0);
        var strip = Studio.Actions(actions); strip.Dock = DockStyle.None; strip.Anchor = AnchorStyles.Right;
        strip.AutoSize = true; strip.Margin = Padding.Empty; row.Controls.Add(strip, 1, 0);
        return row;
    }
    private Control BuildRuntime()
    {
        var page = Studio.Grid([-1], [68, 10, -1]);
        var jobs = CommandRow("Jobs host", hostState, ActionButton("Start Jobs", () => HostAction("start")),
            ActionButton("Stop Jobs", () => HostAction("stop")));
        page.Controls.Add(Studio.Card(jobs, new Padding(14, 8, 6, 8)), 0, 0);
        var provider = Studio.Grid([-1], [24, -1, 1, -1, 24]);
        provider.Controls.Add(Studio.Label("TORRENTER", Studio.Caption, Studio.AccentHover), 0, 0);
        provider.Controls.Add(CommandRow("Torrent engine", engineState, ActionButton("Start provider", () => Provider("start")),
            ActionButton("Stop provider", () => Provider("stop")), ActionButton("Restart provider", () => Provider("restart"))), 0, 1);
        provider.Controls.Add(new Panel { Dock = DockStyle.Fill, BackColor = Studio.Hairline, Margin = Padding.Empty }, 0, 2);
        provider.Controls.Add(CommandRow("REST workspace", webState, ActionButton("Restart web", () => Call(new() { ["op"] = "restart-web" })),
            ActionButton("Open workspace", OpenWorkspace, ButtonTone.Primary)), 0, 3);
        provider.Controls.Add(impactLine, 0, 4);
        page.Controls.Add(Studio.Card(provider, new Padding(14, 6, 6, 6)), 0, 2);
        return page;
    }
    private Control BuildAccess()
    {
        var page = Studio.Grid([-1], [-1, 8, -1, 8, -1]);
        page.Controls.Add(Studio.Card(CommandRow("Tlamatini account", Studio.Label("The workspace uses your current login.", Studio.Small, Studio.Muted),
            ActionButton("Open downloads", OpenWorkspace)), new Padding(14, 6, 6, 6)), 0, 0);
        page.Controls.Add(Studio.Card(CommandRow("API credentials", Studio.Label("Account access and permissions", Studio.Small, Studio.Muted),
            ActionButton("Issue API credential", Issue), ActionButton("Revoke access", Revoke, ButtonTone.Danger)), new Padding(14, 6, 6, 6)), 0, 2);
        page.Controls.Add(Studio.Card(CommandRow("File erasure", Studio.Label("Review the exact files before approving removal.", Studio.Small, Studio.Muted),
            ActionButton("Review erasure", ReviewDeletion)), new Padding(14, 6, 6, 6)), 0, 4);
        return page;
    }
    private void PaintState()
    {
        hostState.Text = $"Tlachihuani.Jobs   /   {StatusForm.Pretty(host)}";
        hostState.ForeColor = host == "running" ? Studio.AccentHover : Studio.Muted;
        engineState.Text = $"Engine · {(engine ? "ready" : "offline")}"; engineState.ForeColor = engine ? Studio.AccentHover : Studio.Muted;
        webState.Text = $"Web · {(web ? "ready" : "offline")}   /   127.0.0.1:12064"; webState.ForeColor = web ? Studio.AccentHover : Studio.Muted;
        impactLine.Text = impact.Length > 0 ? impact : host == "stopped" ? "Start Jobs to bring its providers online." :
            host == "not_installed" ? "Install the Jobs host to manage Torrenter." : "Transfer counts unavailable.";
    }
}
