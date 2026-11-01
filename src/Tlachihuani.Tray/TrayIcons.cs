// Tlachihuani — Angela López Mendoza · XAIHT
using System.Runtime.InteropServices;

namespace Tlachihuani.Tray;

internal static class TrayIcons
{
    internal static Icon Grayscale(Icon original)
    {
        using var sized = new Icon(original, SystemInformation.SmallIconSize);
        using var pixels = sized.ToBitmap();
        for (int y = 0; y < pixels.Height; y++)
        for (int x = 0; x < pixels.Width; x++)
        {
            var c = pixels.GetPixel(x, y);
            int gray = (299 * c.R + 587 * c.G + 114 * c.B) / 1000;
            pixels.SetPixel(x, y, Color.FromArgb(c.A, gray, gray, gray));
        }
        var handle = pixels.GetHicon();
        try { using var borrowed = Icon.FromHandle(handle); return (Icon)borrowed.Clone(); }
        finally { DestroyIcon(handle); }
    }

    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr icon);
}
