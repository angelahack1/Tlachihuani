// Tlachihuani — Angela López Mendoza · XAIHT
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Tlachihuani.Contracts;
using Tlachihuani.Core;

namespace Tlachihuani.Windows;

// This adapter has no caller-selected service name, image, command line, or PID.
public sealed class ScmBackend : IServiceBackend
{
    private readonly bool jobs;
    public ScmBackend() { }
    private ScmBackend(bool jobs) => this.jobs = jobs;
    public static ScmBackend ForJobs() => new(true);
    private string ServiceName => jobs ? JobsEndpoint.ServiceName : Protocol.ServiceName;

    public NativeStatus Query()
    {
        using var manager = OpenSCManager(null, null, 1);
        Check(manager);
        using var service = OpenService(manager, ServiceName, 4);
        if (service.IsInvalid && Marshal.GetLastWin32Error() == 1060) return new("not_installed");
        Check(service);
        if (!QueryServiceStatusEx(service, 0, out var status, Marshal.SizeOf<Status>(), out _)) Fail();
        if (status.Type != 0x10) throw new LifecycleException("identity_changed", "Tlachihuani must be an own-process Windows service.");
        return new(status.State switch
        {
            1 => "stopped", 2 => "start_pending", 3 => "stop_pending", 4 => "running",
            5 => "continue_pending", 6 => "pause_pending", 7 => "paused", _ => "unknown"
        }, checked((int)status.Pid), checked((int)status.Win32ExitCode));
    }

    public void ValidateInstallation(Installation installation) => ValidateImage(installation.ServicePath);
    public void ValidateJobsInstallation()
    {
        if (!jobs) throw new InvalidOperationException("Expected the Jobs service.");
        ValidateImage(JobsInstallation.Image);
    }
    private void ValidateImage(string expected)
    {
        using var manager = OpenSCManager(null, null, 1);
        Check(manager);
        using var service = OpenService(manager, ServiceName, 1);
        Check(service);
        QueryServiceConfig(service, IntPtr.Zero, 0, out var needed);
        if (needed is 0 or > 65536) Fail();
        var buffer = Marshal.AllocHGlobal((int)needed);
        try
        {
            if (!QueryServiceConfig(service, buffer, needed, out _)) Fail();
            var config = Marshal.PtrToStructure<ServiceConfig>(buffer);
            var binary = Marshal.PtrToStringUni(config.BinaryPath);
            if (jobs && !string.Equals(Marshal.PtrToStringUni(config.StartName), @"NT SERVICE\Tlachihuani.Jobs", StringComparison.OrdinalIgnoreCase))
                throw new LifecycleException("identity_changed", "Unexpected Jobs service account.");
            if (config.Type != 0x10 || !string.Equals(binary, $"\"{expected}\"", StringComparison.OrdinalIgnoreCase))
                throw new LifecycleException("identity_changed", "The registered service executable does not match this installation.");
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    public void Start()
    {
        using var service = OpenFor(0x10);
        if (!StartService(service, 0, IntPtr.Zero) && Marshal.GetLastWin32Error() != 1056) Fail();
    }

    public void Stop()
    {
        using var service = OpenFor(0x20);
        if (!ControlService(service, 1, out _) && Marshal.GetLastWin32Error() != 1062) Fail();
    }

    public bool CanControl()
    {
        try { using var service = OpenFor(0x10 | 0x20); return true; }
        catch (Win32Exception ex) when (ex.NativeErrorCode is 5 or 1060) { return false; }
    }

    private ScHandle OpenFor(uint access)
    {
        using var manager = OpenSCManager(null, null, 1);
        Check(manager);
        var service = OpenService(manager, ServiceName, access);
        if (service.IsInvalid) { var error = Marshal.GetLastWin32Error(); service.Dispose(); throw new Win32Exception(error); }
        return service;
    }
    private static void Check(ScHandle handle) { if (handle.IsInvalid) Fail(); }
    private static void Fail() => throw new Win32Exception(Marshal.GetLastWin32Error());

    [StructLayout(LayoutKind.Sequential)] private struct Status
    {
        public uint Type, State, ControlsAccepted, Win32ExitCode, ServiceExitCode, Checkpoint, WaitHint, Pid, Flags;
    }
    [StructLayout(LayoutKind.Sequential)] private struct ServiceConfig
    {
        public uint Type, StartType, ErrorControl;
        public IntPtr BinaryPath, LoadOrderGroup;
        public uint TagId;
        public IntPtr Dependencies, StartName, DisplayName;
    }
    private sealed class ScHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public ScHandle() : base(true) { }
        protected override bool ReleaseHandle() => CloseServiceHandle(handle);
    }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern ScHandle OpenSCManager(string? machine, string? database, uint access);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern ScHandle OpenService(ScHandle manager, string name, uint access);
    [DllImport("advapi32.dll", SetLastError = true)] private static extern bool QueryServiceStatusEx(ScHandle service, int level, out Status status, int size, out int needed);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool QueryServiceConfig(ScHandle service, IntPtr config, uint size, out uint needed);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool StartService(ScHandle service, int count, IntPtr arguments);
    [DllImport("advapi32.dll", SetLastError = true)] private static extern bool ControlService(ScHandle service, uint control, out Status status);
    [DllImport("advapi32.dll")] private static extern bool CloseServiceHandle(IntPtr handle);
}
