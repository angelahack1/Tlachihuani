using Microsoft.Win32.SafeHandles;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Tlachihuani.Jobs;

// Unnamed, non-inheritable handle. Windows terminates the entire provider tree
// when the SCM host dies, including native code that cannot observe stdin EOF.
internal static class OwnedProcesses
{
    private static readonly Lazy<SafeFileHandle> Job = new(Create);
    internal static void Attach(Process process)
    {
        if (!AssignProcessToJobObject(Job.Value, process.SafeHandle))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    private static SafeFileHandle Create()
    {
        var job = CreateJobObject(IntPtr.Zero, null);
        if (job.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        var limits = new Limits { Basic = new BasicLimits { Flags = 0x2000 } };
        if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Limits>()))
        { int error = Marshal.GetLastWin32Error(); job.Dispose(); throw new Win32Exception(error); }
        return job;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimits
    {
        public long PerProcess, PerJob; public uint Flags; public nuint MinWorkingSet, MaxWorkingSet;
        public uint Active; public nuint Affinity; public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] private struct IoCounters { public ulong Reads, Writes, Others, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)]
    private struct Limits
    { public BasicLimits Basic; public IoCounters Io; public nuint ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory; }
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeFileHandle CreateJobObject(IntPtr security, string? name);
    [DllImport("kernel32", SetLastError = true)] private static extern bool SetInformationJobObject(SafeFileHandle job, int info, ref Limits limits, uint size);
    [DllImport("kernel32", SetLastError = true)] private static extern bool AssignProcessToJobObject(SafeFileHandle job, SafeProcessHandle process);
}
