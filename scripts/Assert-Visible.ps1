# Development policy: call from an actual, foreground classic console (conhost).
function Assert-VisibleDevelopmentConsole {
    if (-not ('TlachihuaniDevelopmentWindow' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TlachihuaniDevelopmentWindow {
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
    }
    $window = [TlachihuaniDevelopmentWindow]::GetConsoleWindow()
    if ($window -eq [IntPtr]::Zero -or -not [TlachihuaniDevelopmentWindow]::IsWindowVisible($window) -or [TlachihuaniDevelopmentWindow]::IsIconic($window) -or [TlachihuaniDevelopmentWindow]::GetForegroundWindow() -ne $window) {
        throw 'Development workload refused: run this script in a visible foreground conhost PowerShell window. Keep it open afterward (-NoExit).'
    }
}
