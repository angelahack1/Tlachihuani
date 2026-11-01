# Gate development work on THIS console, including the selected Windows Terminal
# tab. A newly elevated console can exist before Windows switches the foreground.
function Assert-VisibleDevelopmentConsole {
    param([ValidateRange(1,300)][int]$TimeoutSeconds = 90)
    if (-not ('Tlachihuani.ForegroundConsoleProbe' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace Tlachihuani {
public static class ForegroundConsoleProbe {
    [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h, uint kind);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    public static bool IsForeground(string marker) {
        var console = GetConsoleWindow();
        var front = GetForegroundWindow();
        if (console == IntPtr.Zero || front == IntPtr.Zero || !IsWindowVisible(front) || IsIconic(front)) return false;
        if (IsWindowVisible(console) && GetAncestor(console, 2) == front) return true;
        // ConPTY's GetConsoleWindow is a hidden message window. An arbitrary
        // Terminal in front is not evidence: require the nonce written by this tab.
        if (String.IsNullOrEmpty(marker)) return false;
        var cls = new StringBuilder(128);
        GetClassName(front, cls, cls.Capacity);
        if (cls.ToString() != "CASCADIA_HOSTING_WINDOW_CLASS" && cls.ToString() != "ConsoleWindowClass") return false;
        var title = new StringBuilder(2048);
        GetWindowText(front, title, title.Capacity);
        return title.ToString().IndexOf(marker, StringComparison.Ordinal) >= 0;
    }
}
}
'@
    }
    if ([Tlachihuani.ForegroundConsoleProbe]::IsForeground($null)) { return }
    $marker = 'Tlachihuani verification ' + [guid]::NewGuid().ToString('N')
    $oldTitle = $Host.UI.RawUI.WindowTitle
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $Host.UI.RawUI.WindowTitle = $marker
        Write-Host "Waiting for this PowerShell window to be in front. Click inside it to continue (up to $TimeoutSeconds seconds)."
        do {
            if ([Tlachihuani.ForegroundConsoleProbe]::IsForeground($marker)) { return }
            Start-Sleep -Milliseconds 150
        } while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds)
        throw 'No verified foreground console. Click inside this window and rerun the command here. No workload was started.'
    } finally {
        $Host.UI.RawUI.WindowTitle = $oldTitle
    }
}
