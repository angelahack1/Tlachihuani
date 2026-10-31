// Tlachihuani — Angela López Mendoza · XAIHT
namespace Tlachihuani.Tray;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Length > 1 || (args.Length == 1 && args[0] != "--show"))
        {
            MessageBox.Show("Usage: Tlachihuani.Tray.exe [--show]", "Tlachihuani", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        using var singleton = new Mutex(true, @"Local\XAIHT.Tlachihuani.Tray.v1", out var first);
        if (!first) return;
        ApplicationConfiguration.Initialize();
        using var context = new TrayContext(args.Contains("--show"));
        Application.Run(context);
        singleton.ReleaseMutex();
    }
}
