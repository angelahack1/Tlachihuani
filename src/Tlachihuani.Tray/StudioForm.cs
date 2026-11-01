// Tlachihuani — Angela López Mendoza · XAIHT
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace Tlachihuani.Tray;

// Native counterparts of Tlamatini's ui_tokens.css and dialog_theme.css.
internal static class Studio
{
    private static Color Ink(string hex, Color system) => SystemInformation.HighContrast ? system : ColorTranslator.FromHtml(hex);
    internal static Color Surface => Ink("#242c38", SystemColors.Window);
    internal static Color Chrome => Ink("#202733", SystemColors.Control);
    internal static Color Pane => Ink("#1a222e", SystemColors.Window);
    internal static Color Raised => Ink("#2c3745", SystemColors.Control);
    internal static Color Hover => Ink("#3a4b5b", SystemColors.ControlLight);
    internal static Color Text => Ink("#edf2f7", SystemColors.WindowText);
    internal static Color Body => Ink("#ced7e2", SystemColors.WindowText);
    internal static Color Muted => Ink("#aab8c9", SystemColors.GrayText);
    internal static Color Line => Ink("#445164", SystemColors.WindowFrame);
    internal static Color Hairline => Ink("#354152", SystemColors.WindowFrame);
    internal static Color Accent => Ink("#55bbaa", SystemColors.Highlight);
    internal static Color AccentHover => Ink("#79d8c7", SystemColors.Highlight);
    internal static Color AccentInk => Ink("#102f2b", SystemColors.HighlightText);
    internal static Color Focus => Ink("#8ee6d5", SystemColors.Highlight);
    internal static Color Danger => Ink("#ff9da9", SystemColors.WindowText);

    private static string PreferredFont(string name, string fallback)
    {
        using var sample = new Font(name, 9);
        return sample.Name.Equals(name, StringComparison.OrdinalIgnoreCase) ? name : fallback;
    }
    private static readonly string Sans = PreferredFont("Nunito", "Segoe UI");
    internal static readonly Font Regular = new(Sans, 9.5f);
    internal static readonly Font Small = new(Sans, 9);
    internal static readonly Font Caption = new(Sans, 8.5f, FontStyle.Bold);
    internal static readonly Font Strong = new(Sans, 10, FontStyle.Bold);
    internal static readonly Font Heading = new(Sans, 17, FontStyle.Bold);
    internal static readonly Font Metric = new(PreferredFont("Cascadia Code", "Consolas"), 12, FontStyle.Bold);

    internal static Label Label(string text, Font? font = null, Color? color = null) => new()
    {
        Text = text, Font = font ?? Regular, ForeColor = color ?? Body, Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft, AutoEllipsis = true, Margin = Padding.Empty, UseMnemonic = false
    };

    // Negative measurements are proportional weights; positive ones are design pixels at 96 DPI.
    internal static TableLayoutPanel Grid(float[] columns, float[] rows)
    {
        var grid = new TableLayoutPanel { Dock = DockStyle.Fill, Margin = Padding.Empty, ColumnCount = columns.Length, RowCount = rows.Length };
        foreach (float column in columns) grid.ColumnStyles.Add(new ColumnStyle(column < 0 ? SizeType.Percent : SizeType.Absolute, Math.Abs(column)));
        foreach (float row in rows) grid.RowStyles.Add(new RowStyle(row < 0 ? SizeType.Percent : SizeType.Absolute, Math.Abs(row)));
        return grid;
    }

    internal static FlowLayoutPanel Actions(params Control[] controls)
    {
        var row = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, AutoScroll = false, Margin = Padding.Empty };
        row.Controls.AddRange(controls);
        return row;
    }

    internal static Panel Card(Control content, Padding padding)
    {
        var card = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty, BackColor = Pane, Padding = padding };
        card.Paint += (_, e) => ControlPaint.DrawBorder(e.Graphics, card.ClientRectangle, Hairline, ButtonBorderStyle.Solid);
        card.Controls.Add(content);
        return card;
    }

    internal static Panel Field(TextBox input, string accessibleName)
    {
        input.AccessibleName = accessibleName;
        input.BorderStyle = BorderStyle.None; input.BackColor = Pane; input.ForeColor = Text;
        input.Font = Regular; input.Dock = DockStyle.Fill;
        var frame = new Panel { Dock = DockStyle.Fill, BackColor = Pane, Padding = new Padding(9, 7, 9, 3), Margin = Padding.Empty };
        frame.Controls.Add(input);
        frame.Paint += (_, e) => ControlPaint.DrawBorder(e.Graphics, frame.ClientRectangle, input.Focused ? Focus : Line, ButtonBorderStyle.Solid);
        input.GotFocus += (_, _) => frame.Invalidate(); input.LostFocus += (_, _) => frame.Invalidate();
        return frame;
    }
}

internal enum ButtonTone { Secondary, Primary, Danger, Tab }

internal sealed class StudioButton : Button
{
    private readonly ButtonTone tone;
    private bool hover, pressed;
    internal bool Selected { get; private set; }
    internal void SelectTab(bool selected) { Selected = selected; Invalidate(); }

    internal StudioButton(string text, ButtonTone tone = ButtonTone.Secondary)
    {
        this.tone = tone; Text = text; Font = Studio.Caption; FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0;
        UseVisualStyleBackColor = false; BackColor = Studio.Raised; ForeColor = Studio.Text;
        using var sample = new Bitmap(1, 1);
        sample.SetResolution(96, 96);
        using var graphics = Graphics.FromImage(sample);
        Margin = new Padding(0, 0, 8, 0);
        Size = new Size(Math.Max(76, (int)Math.Ceiling(graphics.MeasureString(text, Font).Width) + 26), 34);
        Cursor = Cursors.Hand; SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
    }
    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = pressed = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnMouseDown(MouseEventArgs e) { pressed = true; Invalidate(); base.OnMouseDown(e); }
    protected override void OnMouseUp(MouseEventArgs e) { pressed = false; Invalidate(); base.OnMouseUp(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.Clear(Parent?.BackColor ?? Studio.Surface);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        bool primary = Enabled && tone == ButtonTone.Primary;
        bool tab = tone == ButtonTone.Tab;
        var fill = primary ? (hover || pressed ? Studio.AccentHover : Studio.Accent)
            : tab ? (Selected || hover ? Studio.Raised : Parent?.BackColor ?? Studio.Surface)
            : hover && Enabled ? Studio.Hover : Enabled ? Studio.Raised : Studio.Surface;
        var ink = !Enabled ? Studio.Muted : primary ? Studio.AccentInk : tone == ButtonTone.Danger ? Studio.Danger : tab && Selected ? Studio.AccentHover : Studio.Text;
        var bounds = new RectangleF(0.5f, 0.5f, Width - 1, Height - 1);
        using var shape = new GraphicsPath();
        float radius = 6f * DeviceDpi / 96;
        shape.AddRoundedRectangle(bounds, new SizeF(radius, radius));
        using var background = new SolidBrush(fill);
        using var border = new Pen(Focused && ShowFocusCues ? Studio.Focus : primary ? fill : tab ? fill : Enabled ? Studio.Line : Studio.Hairline,
            Focused && ShowFocusCues ? 2 : 1);
        g.FillPath(background, shape); g.DrawPath(border, shape);
        if (tab && Selected)
        {
            using var marker = new SolidBrush(Studio.Accent);
            int inset = LogicalToDeviceUnits(10);
            g.FillRectangle(marker, inset, Height - LogicalToDeviceUnits(3), Width - 2 * inset, LogicalToDeviceUnits(2));
        }
        TextRenderer.DrawText(g, Text, Font, ClientRectangle, ink,
            TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine);
    }
}

internal class StudioForm : Form
{
    protected Panel BodyArea { get; }
    protected FlowLayoutPanel Commands { get; }
    protected FlowLayoutPanel HeaderCommands { get; }
    protected Label FooterNote { get; }

    protected StudioForm(Icon? icon, string caption, string section, string title, Size size, Size minimum)
    {
        SuspendLayout();
        if (icon == null)
        {
            using var stream = typeof(StudioForm).Assembly.GetManifestResourceStream("Tlachihuani.XT.ico")!;
            ownedIcon = new Icon(stream); icon = ownedIcon;
        }
        Icon = icon; Text = caption; Font = Studio.Regular; ForeColor = Studio.Text; BackColor = Studio.Surface;
        // Derived dialogs add their body and footer actions after this constructor.
        // Scale the complete control tree together on first display.
        AutoScaleMode = AutoScaleMode.None;
        StartPosition = FormStartPosition.CenterParent; MinimizeBox = false; ShowInTaskbar = false;
        ClientSize = size; MinimumSize = SizeFromClientSize(minimum);
        var shell = Studio.Grid([-1], [78, -1, 58]);
        var header = Studio.Grid([48, -1, 0], [-1]);
        header.ColumnStyles[2].SizeType = SizeType.AutoSize;
        header.Padding = new Padding(20, 10, 12, 9); header.BackColor = Studio.Chrome;
        var mark = new PictureBox { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, Margin = new Padding(0, 9, 12, 9) };
        if (icon != null) { var image = icon.ToBitmap(); mark.Image = image; mark.Disposed += (_, _) => image.Dispose(); }
        header.Controls.Add(mark, 0, 0);
        var titles = Studio.Grid([-1], [21, -1]);
        titles.Controls.Add(Studio.Label(section.ToUpperInvariant(), Studio.Caption, Studio.AccentHover), 0, 0);
        titles.Controls.Add(Studio.Label(title, Studio.Heading, Studio.Text), 0, 1);
        header.Controls.Add(titles, 1, 0);
        HeaderCommands = Studio.Actions(); HeaderCommands.AutoSize = true; HeaderCommands.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        HeaderCommands.FlowDirection = FlowDirection.RightToLeft; HeaderCommands.Padding = new Padding(0, 13, 0, 0);
        HeaderCommands.Visible = false;
        HeaderCommands.ControlAdded += (_, _) => HeaderCommands.Visible = true;
        header.Controls.Add(HeaderCommands, 2, 0);
        header.Paint += (_, e) => ControlPaint.DrawBorder(e.Graphics, header.ClientRectangle, Color.Empty, 0, ButtonBorderStyle.None, Color.Empty, 0, ButtonBorderStyle.None, Color.Empty, 0, ButtonBorderStyle.None, Studio.Hairline, 1, ButtonBorderStyle.Solid);
        BodyArea = new Panel { Dock = DockStyle.Fill, Padding = new Padding(20, 12, 20, 12), Margin = Padding.Empty };
        var footer = Studio.Grid([-1, -3], [-1]);
        footer.Padding = new Padding(20, 12, 12, 10); footer.BackColor = Studio.Chrome;
        footer.Paint += (_, e) => { using var pen = new Pen(Studio.Hairline); e.Graphics.DrawLine(pen, 0, 0, footer.Width, 0); };
        FooterNote = Studio.Label("", Studio.Small, Studio.Muted); footer.Controls.Add(FooterNote, 0, 0);
        Commands = Studio.Actions(); Commands.FlowDirection = FlowDirection.RightToLeft; footer.Controls.Add(Commands, 1, 0);
        shell.Controls.Add(header, 0, 0); shell.Controls.Add(BodyArea, 0, 1); shell.Controls.Add(footer, 0, 2);
        Controls.Add(shell);
        ResumeLayout(false);
    }

    protected override void OnLoad(EventArgs e)
    {
        SuspendLayout();
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96, 96);
        ResumeLayout(true);
        PerformAutoScale();
        var area = Screen.FromControl(Owner ?? this).WorkingArea;
        if (MinimumSize.Width > area.Width || MinimumSize.Height > area.Height)
        {
            // Only a display smaller than the usable design needs a scrollable body.
            BodyArea.AutoScrollMinSize = new Size(Math.Max(0, BodyArea.Width - (Width - MinimumSize.Width)),
                Math.Max(0, BodyArea.Height - (Height - MinimumSize.Height)));
            BodyArea.AutoScroll = true;
            MinimumSize = new Size(Math.Min(MinimumSize.Width, area.Width), Math.Min(MinimumSize.Height, area.Height));
        }
        Size = new Size(Math.Min(Width, area.Width), Math.Min(Height, area.Height));
        var ownerBounds = Owner?.Bounds ?? area;
        Location = new Point(Math.Clamp(ownerBounds.Left + (ownerBounds.Width - Width) / 2, area.Left, area.Right - Width),
            Math.Clamp(ownerBounds.Top + (ownerBounds.Height - Height) / 2, area.Top, area.Bottom - Height));
        base.OnLoad(e);
    }

    protected StudioButton Command(string text, Action action, ButtonTone tone = ButtonTone.Secondary)
    {
        var button = new StudioButton(text, tone); button.Click += (_, _) => action(); return button;
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        if (SystemInformation.HighContrast || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 17763)) return;
        int dark = 1;
        DwmSetWindowAttribute(Handle, 20, ref dark, sizeof(int));
        var c = Studio.Chrome; int caption = c.R | c.G << 8 | c.B << 16;
        DwmSetWindowAttribute(Handle, 35, ref caption, sizeof(int));
    }
    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
    private readonly Icon? ownedIcon;
    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (disposing) ownedIcon?.Dispose();
    }
}
