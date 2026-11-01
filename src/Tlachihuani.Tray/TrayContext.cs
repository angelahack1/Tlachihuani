// Tlachihuani — Angela López Mendoza · XAIHT
using System.Reflection;
using Tlachihuani.Client;
using Tlachihuani.Contracts;

namespace Tlachihuani.Tray;

internal sealed class TrayContext : ApplicationContext
{
    private readonly Controller controller = new();
    private readonly TrayServices services;
    private readonly SemaphoreSlim serial = new(1);
    private readonly CancellationTokenSource closing = new();
    private readonly NotifyIcon tray;
    private readonly Icon icon;
    private readonly Icon grayIcon;
    private readonly StatusForm form;
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 3000 };
    private readonly TrayMenu menu;
    private bool changing;
    private bool exitRequested;
    private string progress = "";
    private bool resourcesDisposed;
    private ControlReply? last;
    private JobsState? jobs;

    internal TrayContext(bool show)
    {
        services = new(controller);
        using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Tlachihuani.XT.ico")!;
        icon = new Icon(resource);
        grayIcon = TrayIcons.Grayscale(icon);
        form = new StatusForm(icon);
        form.Requested += operation => _ = RunAsync(operation);
        form.ExitRequested += RequestExit;
        menu = new TrayMenu(ShowPanel, RunAsync, RequestExit);
        tray = new NotifyIcon { Icon = grayIcon, Text = "Tlachihuani — Checking services", ContextMenuStrip = menu, Visible = true };
        // WinForms NotifyIcon handles Explorer's TaskbarCreated message and adds the icon again.
        tray.DoubleClick += (_, _) => ShowPanel();
        timer.Tick += (_, _) => _ = RunAsync("status"); timer.Start();
        if (show) ShowPanel();
        _ = RunAsync("status");
    }

    private void ShowPanel() { form.Show(); form.Activate(); }

    private void RequestExit()
    {
        // Finish an accepted Stop Services even if Exit is selected while Jobs is draining.
        if (changing) exitRequested = true;
        else ExitThread();
    }

    private async Task RunAsync(string operation)
    {
        if (changing || closing.IsCancellationRequested) return;
        var token = closing.Token;
        bool mutation = operation != "status";
        if (!mutation && !serial.Wait(0)) return;
        if (mutation)
        {
            changing = true;
            progress = operation switch
            {
                "start-services" => "Starting services", "stop-services" => "Stopping services", _ => "Updating service"
            };
            Render();
            // A click during a periodic observation must run after it rather than disappear.
            try { await serial.WaitAsync(token); }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { return; }
        }
        string? error = null;
        try
        {
            if (mutation)
            {
                try
                {
                    if (operation == "start-services") await Task.Run(() => services.StartAsync(token), token);
                    else if (operation == "stop-services") await Task.Run(() => services.StopAsync(token), token);
                    else
                    {
                        var result = await Task.Run(() => controller.ExecuteAsync(operation, token), token);
                        if (!result.Ok) error = result.Error?.Message ?? "The service operation failed.";
                    }
                }
                catch (Exception ex) when (!token.IsCancellationRequested && ex is not OutOfMemoryException) { error = ex.Message; }
            }
            last = await Task.Run(() => controller.ExecuteAsync("status", token), token);
            jobs = await Task.Run(() => services.ObserveJobsAsync(token), token);
            if (operation == "start-services" && !Ready) error ??= "The services have not reached API readiness. Check the Services panel and retry.";
            if (operation == "stop-services" && !Stopped) error ??= "Service shutdown could not be confirmed. Check the Services panel and retry.";
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            jobs = null;
            if (mutation) error ??= ex.Message;
        }
        finally
        {
            if (mutation) changing = false;
            serial.Release();
            if (!token.IsCancellationRequested) Render();
        }
        if (error is not null && !token.IsCancellationRequested)
            ServiceDialogs.Notice(form, "Service action failed", error);
        if (mutation && exitRequested && !token.IsCancellationRequested) ExitThread();
    }

    private bool Ready => last is { Service.ScmState: "running", Capabilities: not null }
        && last.Error?.Code is not ("identity_changed" or "incompatible_protocol") && jobs?.ApiReady == true;
    private bool Stopped => (last?.Service?.ScmState is "stopped" or "not_installed") && (jobs?.State is "stopped" or "not_installed");

    private void Render()
    {
        menu.UpdateActions(last, Ready, Stopped, changing);
        if (last is not null) form.Render(last, jobs, changing);
        menu.SetState(StatusForm.Pretty(last?.Service?.ScmState ?? "unavailable"));
        tray.Icon = !changing && Ready ? icon : grayIcon;
        var text = changing ? progress : Ready ? "Services running · Torrenter API ready"
            : Stopped ? "Services stopped" : jobs is null || last is null ? "Service status unavailable"
            : last.Service?.ScmState != "running" ? "Main service " + StatusForm.Pretty(last.Service?.ScmState ?? "unavailable")
            : jobs.State != "running" ? "Jobs " + StatusForm.Pretty(jobs.State) : "Torrenter API unavailable";
        tray.Text = "Tlachihuani — " + text;
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
            closing.Cancel(); timer.Dispose(); tray.Dispose(); menu.Dispose(); form.Dispose(); grayIcon.Dispose(); icon.Dispose(); closing.Dispose();
        }
        base.Dispose(disposing);
    }
}
