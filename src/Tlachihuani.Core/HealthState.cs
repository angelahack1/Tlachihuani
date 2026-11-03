// Tlachihuani — Angela López Mendoza · XAIHT
using System.Diagnostics;
using Tlachihuani.Contracts;

namespace Tlachihuani.Core;

public sealed class HealthState
{
    private static readonly string ProductVersion = typeof(HealthState).Assembly.GetName().Version!.ToString(3);
    private readonly object gate = new();
    private readonly Queue<ServiceEvent> events = new();
    private readonly Stopwatch uptime = Stopwatch.StartNew();
    private readonly Guid instanceId = Guid.NewGuid();
    private readonly DateTimeOffset started = DateTimeOffset.UtcNow;
    private DateTimeOffset heartbeat = DateTimeOffset.UtcNow;
    private long heartbeatSequence;
    private long eventSequence;
    private string health = "initializing";
    private const int Capacity = 256;

    public void Pulse()
    {
        lock (gate)
        {
            heartbeat = DateTimeOffset.UtcNow;
            heartbeatSequence++;
            health = "healthy";
        }
    }

    public void Stopping()
    {
        lock (gate) health = "stopping";
        AddEvent("stopping", "Graceful service shutdown requested.");
    }

    public ServiceEvent AddEvent(string kind, string message)
    {
        lock (gate)
        {
            var value = new ServiceEvent(++eventSequence, DateTimeOffset.UtcNow,
                kind[..Math.Min(kind.Length, 40)], message[..Math.Min(message.Length, 240)]);
            events.Enqueue(value);
            while (events.Count > Capacity) events.Dequeue();
            return value;
        }
    }

    public Reply Answer(Request request, Guid installationId)
    {
        Protocol.Validate(request);
        lock (gate)
        {
            var snapshot = new HealthSnapshot(instanceId, Environment.ProcessId, ProductVersion, health,
                started, heartbeat, Math.Round(uptime.Elapsed.TotalSeconds, 2), heartbeatSequence);
            var selected = request.Operation == "events"
                ? events.Where(e => e.Sequence > request.Cursor).Take(request.Limit).ToArray() : null;
            long? cursor = selected is null ? null : selected.LastOrDefault()?.Sequence ?? request.Cursor;
            bool expired = request.Cursor > 0 && events.Count > 0 && request.Cursor < events.Peek().Sequence - 1;
            return new Reply(Protocol.Major, Protocol.Minor, request.RequestId, true,
                DateTimeOffset.UtcNow, installationId, snapshot, selected, cursor, expired);
        }
    }
}
