using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;

namespace Tlachihuani.Jobs;

// Exactly one outstanding request. If a response is lost, discard the stream so
// the next caller can never consume the previous caller's reply.
internal sealed class WorkerChannel : IDisposable
{
    private Process? process;
    private readonly SemaphoreSlim gate = new(1, 1);
    public bool Running
    {
        get { var current = process; try { return current is { HasExited: false }; } catch (InvalidOperationException) { return false; } }
    }
    internal static Process Spawn(string executable, IEnumerable<string> arguments)
    {
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = new UTF8Encoding(false),
            CreateNoWindow = true,
            WorkingDirectory = AppContext.BaseDirectory
        };
        foreach (string arg in arguments) start.ArgumentList.Add(arg);
        var child = Process.Start(start) ?? throw new IOException("Could not start provider process.");
        try
        {
            OwnedProcesses.Attach(child);
            child.StandardInput.WriteLine("START"); child.StandardInput.Flush();
            return child;
        }
        catch
        {
            try { if (!child.HasExited) child.Kill(true); } finally { child.Dispose(); }
            throw;
        }
    }
    public void Start(JobsSettings settings)
    {
        gate.Wait();
        try
        {
            CloseProcess();
            process = Spawn(Path.Combine(AppContext.BaseDirectory, "runtime", "python.exe"),
                ["-I", "-B", "-X", "utf8", "-u", Path.Combine(AppContext.BaseDirectory, "worker", "worker.py"), settings.State, settings.Development ? "development" : "installed"]);
            using var startup = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            if (process.StandardOutput.ReadLineAsync(startup.Token).AsTask().GetAwaiter().GetResult() != "READY")
                throw new IOException("Torrent engine failed its startup check.");
        }
        catch { CloseProcess(); throw; }
        finally { gate.Release(); }
    }
    public async Task<JsonObject> Request(JsonObject command, CancellationToken token)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(15));
        await gate.WaitAsync(deadline.Token);
        try
        {
            var proc = process;
            if (proc is null || proc.HasExited) throw new IOException("Torrent engine unavailable.");
            try
            {
                await proc.StandardInput.WriteLineAsync(command.ToJsonString().AsMemory(), deadline.Token);
                var line = await proc.StandardOutput.ReadLineAsync(deadline.Token);
                return JsonNode.Parse(line ?? throw new EndOfStreamException())!.AsObject();
            }
            catch { CloseProcess(); throw; }
        }
        finally { gate.Release(); }
    }
    public void Dispose()
    {
        gate.Wait();
        try { CloseProcess(); } finally { gate.Release(); }
    }
    private void CloseProcess()
    {
        if (process is null) return;
        var proc = process; process = null;
        try { proc.StandardInput.Close(); if (!proc.WaitForExit(3000)) { proc.Kill(true); proc.WaitForExit(3000); } }
        catch (InvalidOperationException) { }
        finally { proc.Dispose(); }
    }
}
