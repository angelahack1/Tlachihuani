// Tlachihuani — Angela López Mendoza · XAIHT
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Tlachihuani.Core;

namespace Tlachihuani.Windows;

public static class LifecycleGate
{
    // Mutex ownership is thread-affine. Keep acquisition, the entire async lifecycle and release on this dedicated task thread.
    public static Task<NativeStatus> RunAsync(Installation installation, string action, CancellationToken token) => Task.Run(() =>
    {
        using var security = new NativeSecurity($"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;0x100001;;;{installation.OperatorSid})");
        var attributes = security.Attributes;
        using var mutex = CreateMutexEx(ref attributes, $"Global\\XAIHT.Tlachihuani.{installation.InstallationId:N}.Lifecycle", 0, 0x100001);
        if (mutex.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        var wait = WaitForSingleObject(mutex, 0);
        if (wait == 258) throw new LifecycleException("busy", "Another service lifecycle action is in progress.");
        if (wait is not (0 or 0x80)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            token.ThrowIfCancellationRequested();
            var backend = new ScmBackend();
            backend.ValidateInstallation(installation);
            // Querying anew also reconciles an abandoned mutex after a controller crash.
            return new Lifecycle(backend).ExecuteAsync(action, TimeSpan.FromSeconds(30), token).GetAwaiter().GetResult();
        }
        finally { ReleaseMutex(mutex); }
    }, token);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeWaitHandle CreateMutexEx(ref SecurityAttributes security, string name, uint flags, uint access);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern uint WaitForSingleObject(SafeWaitHandle handle, uint timeout);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool ReleaseMutex(SafeWaitHandle handle);
}
