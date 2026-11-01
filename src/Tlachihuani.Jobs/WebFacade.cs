using System.Net;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace Tlachihuani.Jobs;

internal static class WebFacade
{
    internal const int MaxMetainfo = 1024 * 1024;
    public static async Task RunAsync(int port)
    {
        var builder = WebApplication.CreateSlimBuilder(new WebApplicationOptions
        {
            Args = [],
            ContentRootPath = AppContext.BaseDirectory,
            WebRootPath = "wwwroot"
        });
        builder.Configuration.Sources.Clear();
        builder.Logging.ClearProviders(); // stdout is the private inherited transport.
        builder.WebHost.ConfigureKestrel(k =>
        {
            k.AddServerHeader = false; k.Limits.MaxRequestBodySize = 2 * MaxMetainfo;
            k.Limits.MaxConcurrentConnections = 48; k.Listen(IPAddress.Loopback, port);
        });
        var app = builder.Build();
        var exchange = new SemaphoreSlim(1);
        var replies = Channel.CreateBounded<string>(1);
        async Task<JsonObject> Exchange(JsonObject request, CancellationToken client)
        {
            await exchange.WaitAsync(client);
            try
            {
                await Console.Out.WriteLineAsync(request.ToJsonString());
                await Console.Out.FlushAsync();
                // Finish this exchange even when the initiating HTTP request is aborted.
                return JsonNode.Parse(await replies.Reader.ReadAsync(app.Lifetime.ApplicationStopping))!.AsObject();
            }
            finally { exchange.Release(); }
        }
        app.Use(async (ctx, next) =>
        {
            var request = ctx.Request;
            if (request.Host.Value != $"127.0.0.1:{port}" ||
                request.Headers.TryGetValue("Origin", out var origin) && origin != $"http://127.0.0.1:{port}" ||
                request.Headers["Sec-Fetch-Site"] == "cross-site")
            {
                ctx.Response.StatusCode = 403; return;
            }
            ctx.Response.Headers.CacheControl = "no-store";
            ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
            ctx.Response.Headers["Referrer-Policy"] = "no-referrer";
            ctx.Response.Headers["Content-Security-Policy"] = "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";
            await next();
        });
        app.UseDefaultFiles(); app.UseStaticFiles();
        app.MapGet("/controllers", WorkspaceControllers.Available);
        app.MapMethods("/api/v1/{**route}", ["GET", "POST", "PATCH", "DELETE"], async (HttpContext ctx, string? route) =>
        {
            var req = ctx.Request;
            try
            {
                JsonNode? body = null;
                if (req.Method is "POST" or "PATCH" || req.Method == "DELETE" && req.HasJsonContentType() && req.ContentLength > 0)
                {
                    if (route == "inspections" && req.HasFormContentType)
                    {
                        var form = await req.ReadFormAsync(ctx.RequestAborted);
                        var file = form.Files.GetFile("file");
                        if (file is null || file.Length is <= 0 or > MaxMetainfo) return Results.BadRequest(new { error = "Invalid torrent upload." });
                        using var bytes = new MemoryStream();
                        await file.CopyToAsync(bytes, ctx.RequestAborted);
                        body = new JsonObject { ["metainfo"] = Convert.ToBase64String(bytes.ToArray()) };
                    }
                    else if (req.HasJsonContentType())
                    {
                        body = await JsonNode.ParseAsync(req.Body, cancellationToken: ctx.RequestAborted);
                        if (body is not JsonObject) return Results.BadRequest(new { error = "Expected a JSON object." });
                    }
                    else return Results.StatusCode(415);
                }
                var request = new JsonObject
                {
                    ["method"] = req.Method,
                    ["path"] = route?.TrimEnd('/'),
                    ["body"] = body,
                    ["authorization"] = req.Headers.Authorization.ToString(),
                    ["key"] = req.Headers["Idempotency-Key"].ToString(),
                    ["revision"] = req.Headers.IfMatch.ToString(),
                    ["query"] = JsonSerializer.SerializeToNode(req.Query.ToDictionary(k => k.Key, k => k.Value.ToString()))
                };
                var result = await Exchange(request, ctx.RequestAborted);
                var value = result["body"];
                int status = (int?)result["code"] ?? 500;
                if (route == "events" && req.Method == "GET" && req.Headers.Accept.ToString().Contains("text/event-stream", StringComparison.Ordinal) && status == 200)
                {
                    ctx.Response.ContentType = "text/event-stream";
                    while (!ctx.RequestAborted.IsCancellationRequested)
                    {
                        var events = result["body"]!["events"]!.AsArray();
                        if (events.Count == 0) await ctx.Response.WriteAsync(": heartbeat\n\n", ctx.RequestAborted);
                        foreach (var entry in events)
                            await ctx.Response.WriteAsync($"id: {entry!["cursor"]}\nevent: job\ndata: {entry.ToJsonString()}\n\n", ctx.RequestAborted);
                        await ctx.Response.Body.FlushAsync(ctx.RequestAborted);
                        request["query"]!["after"] = result["body"]!["next_cursor"]!.ToString();
                        await Task.Delay(1500, ctx.RequestAborted);
                        result = await Exchange(request, ctx.RequestAborted);
                        if ((int?)result["code"] != 200) break;
                    }
                    return Results.Empty;
                }
                if (value?["revision"] is JsonValue rev) ctx.Response.Headers.ETag = $"\"{rev}\"";
                if (status == 202 && value?["operation_id"] is JsonValue id) ctx.Response.Headers.Location = "/api/v1/operations/" + id;
                if (status >= 400 && value is JsonObject problem)
                {
                    problem["status"] = status;
                    problem["request_id"] = ctx.TraceIdentifier;
                    problem["retryable"] = status is 429 or 503;
                }
                return Results.Json(value, statusCode: status);
            }
            catch (JsonException) { return Results.BadRequest(new { error = "Invalid JSON." }); }
            catch (InvalidDataException) { return Results.BadRequest(new { error = "Invalid request body." }); }
        });
        await app.StartAsync();
        await Console.Out.WriteLineAsync("READY");
        await Console.Out.FlushAsync();
        // No separate orphaned listener if the owning Windows service exits unexpectedly.
        try
        {
            while (await Console.In.ReadLineAsync(app.Lifetime.ApplicationStopping) is string line)
                await replies.Writer.WriteAsync(line, app.Lifetime.ApplicationStopping);
        }
        catch (OperationCanceledException) { }
        finally { replies.Writer.TryComplete(); await app.StopAsync(); }
    }
}
