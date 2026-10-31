// Tlachihuani — Angela López Mendoza · XAIHT
using System.Reflection;
using Tlachihuani.Client;
using Tlachihuani.Contracts;

namespace Tlachihuani.Tray;

internal sealed class TrayContext : ApplicationContext
{
    private readonly Controller controller = new();
    private readonly CancellationTokenSource closing = new();
    private readonly NotifyIcon tray;
    private readonly Icon icon;
    private readonly StatusForm form;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 3000 };
    private readonly TrayMenu menu;
    private bool busy;
    private bool resourcesDisposed;
    private ControlReply? last;

    internal TrayContext(bool show)
    {
        using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Tlachihuani.XT.ico")!;
        icon = new Icon(resource);
        form = new StatusForm(icon);
        form.Requested += operation => _ = RunAsync(operation);
        form.ExitRequested += ExitThread;
        menu = new TrayMenu(ShowPanel, RunAsync, ExitThread);
        tray = new NotifyIcon { Icon = icon, Text = "Tlachihuani — Checking", ContextMenuStrip = menu, Visible = true };
        // WinForms NotifyIcon handles Explorer's TaskbarCreated message and adds the icon again.
        tray.DoubleClick += (_, _) => ShowPanel();
        timer.Tick += (_, _) => _ = RunAsync("status"); timer.Start();
        if (show) ShowPanel();
        _ = RunAsync("status");
    }

    private void ShowPanel() { form.Show(); form.Activate(); }

    private async Task RunAsync(string operation)
    {
        if (busy || closing.IsCancellationRequested) return;
        busy = true;
        menu.UpdateActions(last, busy: true);
        if (last is not null) form.Render(last, busy: true);
        try
        {
            var token = closing.Token;
            // Native SCM queries must never block the Windows message pump.
            last = await Task.Run(() => controller.ExecuteAsync(operation, token));
            if (closing.IsCancellationRequested) return;
            if (operation != "status" && !last.Ok)
                MessageBox.Show(form, last.Error?.Message ?? "The operation failed.", "Tlachihuani", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            if (operation != "status" && last.Ok) last = await Task.Run(() => controller.ExecuteAsync("status", token));
            if (closing.IsCancellationRequested) return;
            var stateText = StatusForm.Pretty(last.Service?.ScmState ?? "unavailable");
            menu.SetState(stateText);
            tray.Text = "Tlachihuani — " + (last.Service?.ScmState == "running" && last.Service.Health != "healthy" ? "Health unavailable" : stateText);
        }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            if (!closing.IsCancellationRequested)
            {
                last = new(Protocol.Major, Guid.NewGuid(), false, operation, "failed", DateTimeOffset.UtcNow, "installed", null, null,
                    Error: new("internal_error", "The service status could not be refreshed. Try Refresh again."));
                menu.SetState("Unavailable"); tray.Text = "Tlachihuani — Unavailable";
            }
        }
        finally
        {
            busy = false;
            if (!closing.IsCancellationRequested && last is not null)
            {
                form.Render(last, busy: false);
                menu.UpdateActions(last, busy: false);
            }
        }
    }

    protected override void ExitThreadCore()
    {
        closing.Cancel(); timer.Stop(); tray.Visible = false; form.AllowExit = true; form.Close();
        base.ExitThreadCore();
    }
    protected override void Dispose(bool disposing)
    {
        // Application.Run disposes its context; the caller's using scope can dispose it again.
        if (disposing && !resourcesDisposed)
        {
            resourcesDisposed = true;
            closing.Cancel(); timer.Dispose(); tray.Dispose(); menu.Dispose(); form.Dispose(); icon.Dispose(); closing.Dispose();
        }
        base.Dispose(disposing);
    }
}
