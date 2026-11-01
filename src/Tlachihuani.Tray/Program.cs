// Tlachihuani — Angela López Mendoza · XAIHT
namespace Tlachihuani.Tray;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        if (args.Length > 1 || (args.Length == 1 && args[0] != "--show"))
        {
            ServiceDialogs.Notice(null, "Open the XT tray", "Run Tlachihuani.Tray.exe to show the tray icon. Add --show to open the service overview.");
            return;
        }
        using var singleton = new Mutex(true, @"Local\XAIHT.Tlachihuani.Tray.v1", out var first);
        if (!first) return;
        using var context = new TrayContext(args.Contains("--show"));
        Application.Run(context);
        singleton.ReleaseMutex();
    }
}
