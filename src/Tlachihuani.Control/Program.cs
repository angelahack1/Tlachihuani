// Tlachihuani — Angela López Mendoza · XAIHT
using System.Text.Json;
using Tlachihuani.Client;
using Tlachihuani.Contracts;

ControlReply result;
var operation = args.FirstOrDefault() ?? "status";
long cursor = 0;
var validArguments = args.Length <= 1 || (args.Length == 3 && operation == "events" && args[1] == "--cursor" && long.TryParse(args[2], out cursor) && cursor >= 0);
if (!validArguments)
{
    result = new(Protocol.Major, Guid.NewGuid(), false, operation, "failed", DateTimeOffset.UtcNow, "installed", null, null,
        Error: new("invalid_request", "Usage: Tlachihuani.Control.exe [status|events [--cursor N]|start|stop|restart]. No arbitrary names, paths, PIDs or shell commands are accepted."));
}
else
{
    using var cancel = new CancellationTokenSource();
    Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancel.Cancel(); };
    try { result = await new Controller().ExecuteAsync(operation, cancel.Token, cursor); }
    catch (Exception ex) when (ex is not OutOfMemoryException)
    {
        result = new(Protocol.Major, Guid.NewGuid(), false, operation, "failed", DateTimeOffset.UtcNow, "installed", null, null,
            Error: new("internal_error", "The control operation failed unexpectedly. Refresh status before trying again."));
    }
}
Console.WriteLine(JsonSerializer.Serialize(result, Protocol.Json));
return result.Ok ? 0 : result.Error?.Code switch
{
    "invalid_request" => 2, "not_installed" => 3, "access_denied" => 4,
    "busy" or "identity_changed" => 5, "timeout" => 6, "incompatible_protocol" => 7, _ => 8
};
