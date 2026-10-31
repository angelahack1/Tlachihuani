// Tlachihuani — Angela López Mendoza · XAIHT
using System.Buffers.Binary;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Tlachihuani.Contracts;

public static class Protocol
{
    public const int Major = 1;
    public const int Minor = 0;
    public const int MaxFrameBytes = 65_536;
    public const string ServiceName = "Tlachihuani";
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = false,
        MaxDepth = 16,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    public static void Validate(Request request)
    {
        if (request.ProtocolMajor != Major)
            throw new ProtocolException("incompatible_protocol", "This client uses an unsupported protocol version.");
        if (request.ProtocolMinor < 0 || request.RequestId == Guid.Empty)
            throw new ProtocolException("invalid_request", "A valid protocol version and request ID are required.");
        if (request.Operation is not ("hello" or "status" or "events"))
            throw new ProtocolException("invalid_request", "The service accepts hello, status and events only.");
        if (request.Cursor < 0 || request.Limit is < 1 or > 100)
            throw new ProtocolException("invalid_request", "Event cursor or limit is outside its allowed range.");
    }

    public static async Task<T> ReadAsync<T>(Stream stream, CancellationToken cancellationToken)
    {
        byte[] header = new byte[4];
        await stream.ReadExactlyAsync(header, cancellationToken);
        int length = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (length is < 1 or > MaxFrameBytes)
            throw new ProtocolException("invalid_request", "Message length is outside the protocol limit.");
        byte[] body = new byte[length];
        await stream.ReadExactlyAsync(body, cancellationToken);
        try
        {
            return JsonSerializer.Deserialize<T>(body, Json)
                ?? throw new ProtocolException("invalid_request", "A JSON object is required.");
        }
        catch (JsonException)
        {
            throw new ProtocolException("invalid_request", "The message is not valid protocol JSON.");
        }
    }

    public static async Task WriteAsync<T>(Stream stream, T value, CancellationToken cancellationToken)
    {
        byte[] body = JsonSerializer.SerializeToUtf8Bytes(value, Json);
        if (body.Length > MaxFrameBytes)
            throw new ProtocolException("invalid_request", "The response exceeds the protocol limit.");
        byte[] header = new byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(header, body.Length);
        await stream.WriteAsync(header, cancellationToken);
        await stream.WriteAsync(body, cancellationToken);
        await stream.FlushAsync(cancellationToken);
    }
}

public sealed record Request(int ProtocolMajor, int ProtocolMinor, Guid RequestId, string Operation,
    long Cursor = 0, int Limit = 50);
public sealed record ErrorInfo(string Code, string Message, int? NativeCode = null);
public sealed record ServiceEvent(long Sequence, DateTimeOffset TimestampUtc, string Kind, string Message);
public sealed record HealthSnapshot(Guid InstanceId, int Pid, string Version, string Health,
    DateTimeOffset StartedAtUtc, DateTimeOffset LastHeartbeatUtc, double UptimeSeconds, long HeartbeatSequence);
public sealed record Reply(int ProtocolMajor, int ProtocolMinor, Guid RequestId, bool Ok,
    DateTimeOffset ObservedAtUtc, Guid InstallationId, HealthSnapshot? Service,
    IReadOnlyList<ServiceEvent>? Events = null, long? NextCursor = null, bool CursorExpired = false,
    ErrorInfo? Error = null);
public sealed class ProtocolException(string code, string message) : Exception(message)
{
    public string Code { get; } = code;
}

public sealed record ServiceStatus(string Name, string ScmState, string Health, int? Pid,
    Guid? InstanceId, string? Version, double? UptimeSeconds, DateTimeOffset? LastHeartbeatUtc);
public sealed record Capabilities(bool Start, bool Stop, bool Restart, bool ForceStop, string? Reason);
public sealed record ControlReply(int ProtocolMajor, Guid RequestId, bool Ok, string Operation,
    string Phase, DateTimeOffset ObservedAtUtc, string Mode, Guid? InstallationId,
    ServiceStatus? Service, Capabilities? Capabilities = null, ErrorInfo? Error = null,
    IReadOnlyList<ServiceEvent>? Events = null, long? NextCursor = null, bool CursorExpired = false);
