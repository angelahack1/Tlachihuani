// Tlachihuani — Angela López Mendoza · XAIHT
using System.IO.Pipes;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Tlachihuani.Contracts;
using Tlachihuani.Core;
using Tlachihuani.Windows;

namespace Tlachihuani.Service;

public sealed record PipeSettings(string Name, string OperatorSid, Guid InstallationId);

public sealed class ServiceWorker(HealthState health, PipeSettings settings, ILogger<ServiceWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Keep the first instance alive until all listeners stop, preventing replacement/squatting between clients.
        var listeners = new List<NamedPipeServerStream>();
        using var workersStopped = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        try
        {
            for (var i = 0; i < 16; i++) listeners.Add(LocalPipe.CreateServer(settings.Name, settings.OperatorSid, first: i == 0));
            health.Pulse();
            health.AddEvent("ready", "Local status channel is ready.");
            logger.LogInformation("Tlachihuani ready. PID {Pid}; pipe {Pipe}. No business workload is configured.", Environment.ProcessId, settings.Name);
            var workers = listeners.Select(pipe => ServeAsync(pipe, workersStopped.Token)).Append(PulseAsync(workersStopped.Token)).ToArray();
            await Task.WhenAny(workers);
            workersStopped.Cancel();
            // Observe every worker before disposing pipes. WhenAll propagates a fault ahead of sibling cancellation.
            await Task.WhenAll(workers);
        }
        catch (OperationCanceledException) when (workersStopped.IsCancellationRequested) { }
        finally
        {
            health.Stopping();
            foreach (var pipe in listeners) pipe.Dispose();
            logger.LogInformation("Tlachihuani stopped; all local clients released.");
        }
    }

    private async Task PulseAsync(CancellationToken token)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(2));
        while (await timer.WaitForNextTickAsync(token)) health.Pulse();
    }

    private async Task ServeAsync(NamedPipeServerStream pipe, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            await pipe.WaitForConnectionAsync(token);
            try
            {
                using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
                deadline.CancelAfter(TimeSpan.FromSeconds(3));
                // The kernel authenticates each connection against the explicit DACL. All three operations are read-only.
                var request = await Protocol.ReadAsync<Request>(pipe, deadline.Token);
                Reply answer;
                try { answer = health.Answer(request, settings.InstallationId); }
                catch (ProtocolException ex)
                {
                    answer = new(Protocol.Major, Protocol.Minor, request.RequestId, false, DateTimeOffset.UtcNow, settings.InstallationId, null, Error: new(ex.Code, ex.Message));
                }
                await Protocol.WriteAsync(pipe, answer, deadline.Token);
                // Bounded receipt acknowledgement prevents DisconnectNamedPipe from discarding a reply
                // before its client has consumed it. This never dispatches a second operation.
                var receipt = new byte[1];
                await pipe.ReadExactlyAsync(receipt, deadline.Token);
                if (receipt[0] != 0x06) throw new ProtocolException("invalid_request", "Invalid receipt acknowledgement.");
            }
            catch (Exception ex) when (ex is IOException or ProtocolException or OperationCanceledException)
            {
                // Do not log attacker-controlled payloads or flood the journal with rejected connections.
                logger.LogDebug("Local client ended before a valid exchange: {ErrorType}", ex.GetType().Name);
            }
            // A broken connection also needs Disconnect before the next accept.
            finally { pipe.Disconnect(); }
        }
    }
}
