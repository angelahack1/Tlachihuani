// Tlachihuani — Angela López Mendoza · XAIHT
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Tlachihuani.Tray;

internal sealed class ServiceDialogs : StudioForm
{
    private ServiceDialogs(Form? owner, string caption, string section, string title, Size size)
        : base(owner?.Icon, caption, section, title, size, size)
    {
        MaximizeBox = false;
        if (owner?.Visible != true) { StartPosition = FormStartPosition.CenterScreen; ShowInTaskbar = true; }
    }

    private StudioButton Choice(string caption, DialogResult result, ButtonTone tone = ButtonTone.Secondary)
    {
        var button = new StudioButton(caption, tone) { DialogResult = result };
        Commands.Controls.Add(button); return button;
    }

    private DialogResult Open(Form? owner) => owner?.Visible == true ? ShowDialog(owner) : ShowDialog();

    internal static void Notice(Form? owner, string title, string message)
    {
        using var dialog = new ServiceDialogs(owner, title, "Tlachihuani   /   Service notice", title, new(530, 236));
        dialog.BodyArea.Controls.Add(ReadText(message, "Message"));
        var ok = dialog.Choice("OK", DialogResult.OK, ButtonTone.Primary);
        dialog.AcceptButton = dialog.CancelButton = ok; dialog.Open(owner);
    }

    internal static bool Confirm(Form owner, string title, string message, string action)
    {
        using var dialog = new ServiceDialogs(owner, "Tlachihuani · Confirm", "Tlachihuani   /   Confirmation", title, new(540, 240));
        dialog.BodyArea.Controls.Add(ReadText(message.Trim(), "Confirmation details"));
        dialog.Choice(action, DialogResult.Yes, ButtonTone.Danger);
        var cancel = dialog.Choice("Cancel", DialogResult.Cancel);
        dialog.AcceptButton = dialog.CancelButton = cancel; dialog.ActiveControl = cancel;
        return dialog.Open(owner) == DialogResult.Yes;
    }

    private static RichTextBox ReadText(string text, string name) => new()
    {
        Text = text, AccessibleName = name, ReadOnly = true, DetectUrls = false, WordWrap = true,
        ScrollBars = RichTextBoxScrollBars.Vertical, BorderStyle = BorderStyle.None,
        BackColor = Studio.Surface, ForeColor = Studio.Body, Font = Studio.Regular, Dock = DockStyle.Fill, Margin = Padding.Empty
    };

    internal static (string Account, string Scope)? RequestCredential(Form owner)
    {
        using var dialog = new ServiceDialogs(owner, "Torrenter · API access", "Torrenter   /   Access", "Issue API credential", new(560, 386));
        var form = Studio.Grid([-1], [23, 34, 9, 23, 102, -1]);
        var account = new TextBox { PlaceholderText = "Use my Windows profile" };
        var choices = Studio.Grid([-1], [-1, -1, -1]);
        choices.AccessibleName = "Permissions";
        var permissions = new[] { ("Read only", "read"), ("Read, submit and control transfers", "read submit control"),
            ("Read, submit, control, remove and erase", "read submit control remove erase") };
        var options = permissions.Select(p => new RadioButton { Text = p.Item1, Tag = p.Item2, Dock = DockStyle.Fill,
            FlatStyle = FlatStyle.Flat, ForeColor = Studio.Body, Margin = Padding.Empty }).ToArray();
        for (int i = 0; i < options.Length; i++) choices.Controls.Add(options[i], 0, i);
        options[0].Checked = true;
        form.Controls.Add(Studio.Label("Application account", Studio.Small), 0, 0); form.Controls.Add(Studio.Field(account, "Application account"), 0, 1);
        form.Controls.Add(Studio.Label("Permissions", Studio.Small), 0, 3);
        form.Controls.Add(Studio.Card(choices, new Padding(10, 3, 10, 3)), 0, 4);
        form.Controls.Add(Studio.Label("The credential expires in one hour.", Studio.Small, Studio.Muted), 0, 5);
        dialog.BodyArea.Controls.Add(form);
        var issue = dialog.Choice("Issue token", DialogResult.OK, ButtonTone.Primary);
        dialog.AcceptButton = issue; dialog.CancelButton = dialog.Choice("Cancel", DialogResult.Cancel);
        dialog.ActiveControl = account;
        return dialog.Open(owner) == DialogResult.OK ? (account.Text.Trim(), (string)options.Single(o => o.Checked).Tag!) : null;
    }

    internal static void ShowCredential(Form owner, string token)
    {
        using var dialog = new ServiceDialogs(owner, "Torrenter · Copy credential", "Torrenter   /   Access", "API credential", new(566, 257));
        var form = Studio.Grid([-1], [24, 34, -1]);
        var field = new TextBox { Text = token, ReadOnly = true, UseSystemPasswordChar = true };
        form.Controls.Add(Studio.Label("Access token", Studio.Small), 0, 0); form.Controls.Add(Studio.Field(field, "Issued access token"), 0, 1);
        form.Controls.Add(Studio.Label("Copy this token before closing the window.", Studio.Small, Studio.Muted), 0, 2);
        dialog.BodyArea.Controls.Add(form);
        var copy = dialog.Command("Copy token", () =>
        {
            try { Clipboard.SetText(token); dialog.FooterNote.Text = "Copied"; }
            catch (ExternalException) { dialog.FooterNote.Text = "Clipboard busy"; }
        }, ButtonTone.Primary);
        var reveal = new StudioButton("Show token");
        reveal.Click += (_, _) => { field.UseSystemPasswordChar = !field.UseSystemPasswordChar; reveal.Text = field.UseSystemPasswordChar ? "Show token" : "Hide token"; };
        dialog.Commands.Controls.AddRange([copy, reveal]); dialog.AcceptButton = copy; dialog.CancelButton = dialog.Choice("Close", DialogResult.Cancel);
        dialog.Open(owner);
    }

    internal static bool ReviewFiles(Form owner, JsonObject preview)
    {
        var files = preview["files"]!.AsArray();
        using var dialog = new ServiceDialogs(owner, "Review exact files for erasure", "Torrenter   /   File erasure", "Review files for erasure", new(686, 392));
        var layout = Studio.Grid([-1], [26, 35, 10, -1]);
        layout.Controls.Add(Studio.Label($"{files.Count} {(files.Count == 1 ? "file" : "files")} in this request", Studio.Strong, Studio.Text), 0, 0);
        var job = new TextBox { Text = (string?)preview["job_id"], ReadOnly = true };
        var identity = Studio.Grid([55, -1], [-1]);
        identity.Controls.Add(Studio.Label("Job ID", Studio.Small, Studio.Muted), 0, 0);
        identity.Controls.Add(Studio.Field(job, "Job ID"), 1, 0); layout.Controls.Add(identity, 0, 1);
        var list = ReadText(string.Join(Environment.NewLine + Environment.NewLine,
            files.Select(f => $"{f!["bytes"]} bytes   ·   {f["path"]}")), "Exact files and sizes");
        list.BackColor = Studio.Pane; list.Font = Studio.Small;
        layout.Controls.Add(Studio.Card(list, new Padding(10)), 0, 3); dialog.BodyArea.Controls.Add(layout);
        dialog.Choice("Authorize erasure", DialogResult.Yes, ButtonTone.Danger);
        var cancel = dialog.Choice("Cancel", DialogResult.Cancel);
        dialog.AcceptButton = dialog.CancelButton = cancel; dialog.ActiveControl = cancel;
        return dialog.Open(owner) == DialogResult.Yes;
    }
}
