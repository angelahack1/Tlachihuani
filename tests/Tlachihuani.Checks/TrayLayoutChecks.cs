// Tlachihuani — Angela López Mendoza · XAIHT
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Tlachihuani.Contracts;
using Tlachihuani.Tray;

internal static class TrayLayoutChecks
{
    internal static int Run(string directory, string mode)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try { Exercise(Path.GetFullPath(directory), mode); }
            catch (Exception ex) { failure = ex; }
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join();
        if (failure == null) return 0;
        Console.Error.WriteLine(failure); return 1;
    }

    private static void Exercise(string directory, string mode)
    {
        Application.SetHighDpiMode(mode switch
        {
            "desktop" => HighDpiMode.PerMonitorV2, "96dpi" => HighDpiMode.DpiUnaware,
            _ => throw new ArgumentException("Choose desktop or 96dpi.")
        });
        Application.EnableVisualStyles(); Directory.CreateDirectory(directory);
        using var resource = typeof(StatusForm).Assembly.GetManifestResourceStream("Tlachihuani.XT.ico")!;
        using var icon = new Icon(resource);
        using var owner = new StatusForm(icon);
        owner.Show();
        void Render(string scm, string health, ErrorInfo? error = null)
        {
            bool online = scm == "running";
            var service = new ServiceStatus("Tlachihuani", scm, health, online ? 12345 : null, null, online ? "0.1.0" : null,
                online ? 1234567 : null, null);
            owner.Render(new(1, Guid.NewGuid(), true, "status", "succeeded", DateTimeOffset.UtcNow, "test", null, service,
                new(true, true, true, false, null), error), new JobsState(online ? "running" : "stopped", online), false);
        }
        void Snap(Form dialog, string name)
        {
            dialog.Activate(); Application.DoEvents(); Pump(180);
            if (GetForegroundWindow() != dialog.Handle || !dialog.Visible) throw new Exception($"Window is not foreground: {name}");
            int count = Audit(dialog, name);
            if (!Screen.FromControl(dialog).WorkingArea.Contains(dialog.Bounds)) throw new Exception($"{name}: window exceeds the working area.");
            var rectangle = dialog.RectangleToScreen(dialog.ClientRectangle);
            using var screenshot = new Bitmap(rectangle.Width, rectangle.Height);
            using (var graphics = Graphics.FromImage(screenshot))
                graphics.CopyFromScreen(rectangle.Location, Point.Empty, rectangle.Size);
            screenshot.Save(Path.Combine(directory, $"{name}-{dialog.DeviceDpi}.png"));
            Console.WriteLine($"PASS {name}: {count} visible controls, {dialog.DeviceDpi} DPI, client {dialog.ClientSize}.");
        }

        Render("stopped", "unknown"); Snap(owner, "overview-stopped");
        owner.Size = owner.MinimumSize;
        foreach (var scm in new[] { "stopped", "start_pending", "running", "stop_pending", "paused", "not_installed", "unknown" })
        {
            Render(scm, scm == "running" ? "healthy" : "unknown"); Snap(owner, "overview-min-" + scm);
        }
        Render("stop_pending", "unknown", new("timeout", "The service did not reach the requested state before the deadline. Refresh its status; no force termination was attempted."));
        Snap(owner, "overview-min-timeout");
        using (var services = new ServicesForm(icon))
        {
            services.Show(owner); Pump(420);
            var size = services.Size;
            foreach (bool minimum in new[] { false, true })
            {
                services.Size = minimum ? services.MinimumSize : size;
                foreach (string view in new[] { "Runtime", "Access" })
                {
                    All(services).OfType<Button>().Single(b => b.Text == view).PerformClick();
                    Snap(services, "services-" + view.ToLowerInvariant() + (minimum ? "-min" : ""));
                }
            }
            services.Close();
        }

        void Modal(string name, Action open)
        {
            Exception? error = null;
            using var timer = new System.Windows.Forms.Timer { Interval = 200 };
            timer.Tick += (_, _) =>
            {
                if (Form.ActiveForm is not StudioForm dialog || dialog == owner) return;
                timer.Stop();
                try
                {
                    Snap(dialog, name);
                    if (name == "credential-result")
                    {
                        var reveal = All(dialog).OfType<Button>().Single(b => b.Text == "Show token");
                        reveal.PerformClick(); Snap(dialog, "credential-result-revealed");
                        reveal.PerformClick();
                    }
                }
                catch (Exception ex) { error = ex; }
                finally { dialog.DialogResult = DialogResult.Cancel; dialog.Close(); }
            };
            timer.Start(); open(); if (error != null) throw error;
        }

        Modal("credential-issue", () => ServiceDialogs.RequestCredential(owner));
        Modal("credential-result", () => ServiceDialogs.ShowCredential(owner, "sample-token-for-layout-verification-only"));
        foreach (var (title, button) in new[] { ("Stop the Jobs host?", "Stop Jobs"), ("Stop Torrenter?", "Stop provider"),
            ("Restart Torrenter?", "Restart provider"), ("Revoke account access?", "Revoke access") })
            Modal("confirm-" + button.Replace(' ', '-'), () => ServiceDialogs.Confirm(owner, title, button == "Revoke access"
                ? "This revokes all REST sessions and enrolled gateways for your Windows account."
                : "Active transfers will be checkpointed. 10 active transfers across 250 records.", button));
        Modal("service-ready", () => ServiceDialogs.Notice(owner, "Services ready", "Open your downloads from the signed-in Tlamatini account."));
        Modal("no-files", () => ServiceDialogs.Notice(owner, "File erasure", "There are no pending file-erasure requests."));
        Modal("operation-error", () => ServiceDialogs.Notice(owner, "Service action failed", "Windows could not complete this operation. Check the service status and try again."));
        Modal("link-error", () => ServiceDialogs.Notice(null, "Open Tlamatini", "Windows could not open the configured Tlamatini link."));
        Modal("tray-help", () => ServiceDialogs.Notice(null, "Open the XT tray", "Run Tlachihuani.Tray.exe to show the tray icon. Add --show to open the service overview."));
        JsonObject Preview(int count) => new()
        {
            ["job_id"] = new string('b', 32),
            ["files"] = new JsonArray(Enumerable.Range(1, count).Select(n => (JsonNode)new JsonObject
                { ["path"] = $"fixture/volume-{n:D2}/a-long-test-filename-for-review-only.epub", ["bytes"] = 192003 }).ToArray())
        };
        Modal("erasure-review", () => ServiceDialogs.ReviewFiles(owner, Preview(2)));
        Modal("erasure-review-many", () => ServiceDialogs.ReviewFiles(owner, Preview(32)));
        owner.AllowExit = true; owner.Close();
    }

    private static void Pump(int milliseconds)
    {
        var clock = Stopwatch.StartNew();
        while (clock.ElapsedMilliseconds < milliseconds) { Application.DoEvents(); Thread.Sleep(10); }
    }
    private static IEnumerable<Control> All(Control parent)
    {
        foreach (Control child in parent.Controls)
        {
            yield return child;
            foreach (var nested in All(child)) yield return nested;
        }
    }
    private static int Audit(Control parent, string view)
    {
        var children = parent.Controls.Cast<Control>().Where(c => c.Visible).ToArray();
        int count = 0;
        if (parent is ScrollableControl panel && (panel.VerticalScroll.Visible || panel.HorizontalScroll.Visible))
            throw new Exception($"{view}: unexpected scrolling in {parent.GetType().Name}.");
        foreach (var child in children)
        {
            string id = $"{view}: {child.GetType().Name} {child.Text}";
            if (!parent.ClientRectangle.Contains(child.Bounds) || child.Width <= 0 || child.Height <= 0)
                throw new Exception($"{id}: {child.Bounds} outside {parent.ClientRectangle}.");
            foreach (var sibling in children.Where(other => other != child))
                if (Rectangle.Intersect(child.Bounds, sibling.Bounds) is { Width: > 0, Height: > 0 })
                    throw new Exception($"{id} overlaps {sibling.GetType().Name} {sibling.Text}.");
            using var graphics = child.CreateGraphics();
            var flags = TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine;
            var available = child.ClientSize;
            if (child is Label or ButtonBase)
            {
                int width = available.Width - (child is RadioButton ? child.LogicalToDeviceUnits(22) : 0);
                var needed = TextRenderer.MeasureText(graphics, child.Text, child.Font, Size.Empty, flags);
                if (child is Label && needed.Width > width)
                    needed = TextRenderer.MeasureText(graphics, child.Text, child.Font, new(width, 10000), TextFormatFlags.NoPrefix | TextFormatFlags.WordBreak);
                if (needed.Width > width || needed.Height > available.Height)
                    throw new Exception($"{id}: requires {needed}, available {width}x{available.Height}.");
            }
            if (child is PictureBox picture && (picture.Image == null || picture.SizeMode != PictureBoxSizeMode.Zoom))
                throw new Exception($"{id}: brand image missing or cropped.");
            if (child is TextBox field)
            {
                if (field.Height < field.PreferredHeight) throw new Exception($"{id}: input height {field.Height} < {field.PreferredHeight}.");
                var placeholder = TextRenderer.MeasureText(graphics, field.PlaceholderText, field.Font, Size.Empty, flags);
                if (placeholder.Width > available.Width) throw new Exception($"{id}: placeholder requires {placeholder.Width}px.");
            }
            if (child is RichTextBox rich && rich.TextLength > 0)
            {
                if (view == "erasure-review-many")
                {
                    rich.Select(rich.TextLength, 0);
                    rich.ScrollToCaret();
                }
                var end = rich.GetPositionFromCharIndex(rich.TextLength - 1);
                if (end.X < 0 || end.Y < 0 || end.X >= rich.ClientSize.Width || end.Y + rich.Font.Height > rich.ClientSize.Height)
                    throw new Exception($"{id}: last line outside the text viewport.");
                if (view == "erasure-review-many") { rich.Select(0, 0); rich.ScrollToCaret(); }
            }
            count += 1 + Audit(child, view);
        }
        return count;
    }

    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
}
