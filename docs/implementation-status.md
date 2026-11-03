# Windows setup — 2026-11-03

The versioned setup output under `artifacts/setup/<version>/windows-x64/` contains the graphical installer and matching uninstaller. Workstation UI automation has exercised both version labels, Review and Cancel. Visible isolated acceptance installed the QA package, started both SCM services, removed it, reinstalled it with the same protected Jobs identity and removed it again. The test uses inert service binaries and separate product and service IDs. Full production-payload acceptance requires a clean machine or Windows Sandbox. Build, maintenance and test commands are in the [Windows setup guide](../packaging/setup/README.md).

On 3 November the operator also completed installation of the production 0.1.0 package on the workstation after preserving the legacy folders. Launching the tray executable with `--show` opened the panel. **Start Services** changed XT from gray to green, the Jobs health endpoint returned `engine: ready`, and the workspace displayed the signed-in Tlamatini account. This was a manual workstation check. See [v0.2.0](releases/v0.2.0.md) for the release scope.

## Jobs and Torrenter — 2026-10-31

On ANGYSLAP, Jobs was installed and upgraded under its virtual service account. The delegated operator verified the named pipe and restarted Jobs from standard Windows PowerShell, while the original Tlachihuani service stayed stopped. The installed XT panel approved an actual headed Chrome session on port 12064. A private swarm exercised transfer, publication, recovery, isolation and deletion. See [the operating guide and verification scope](torrenter.md).

The installed XT menu was exercised on ANGYSLAP with both services set to Manual. **Start Services** brought up both hosts and the REST endpoint. Tlamatini's enrolled Torrenter agent listed the completed download. The original icon appeared in color when the API was ready and turned gray when the provider was disabled. **Start Services** also recovered that partially running configuration.

After **Stop Services**, both SCM PIDs were zero, the captured service and child processes had exited, port 12064 had no listener, and the same XT process displayed the gray icon. An isolated Jobs host also shut down with its torrent worker deliberately suspended. A local-pipe regression check disconnects a client mid-request and verifies that the primary host keeps serving other clients.

The following entries are the historical October 11 foundation record.

## Lifecycle foundation — 2026-10-11

This page distinguishes working code from the broader design. No SCM service, registry startup entry, local Git repository or GitHub repository was created. Tlamatini remains a separate, read-only checkout at `C:\Development\XAIHT\Tlamatini`, https://github.com/XAIHT/Tlamatini.

## Implemented

| Component | Current behavior |
|---|---|
| Contracts | Snake-case JSON; four-byte little-endian length; 64 KiB maximum; depth 16; version, operation, request ID, cursor and limit validation |
| Core | Independent health/SCM states; heartbeat every two seconds; boot instance ID; last 256 events; idempotent Start/Stop and ordered Restart with deadlines |
| Windows | Fixed-name own-process SCM adapter; quoted image-path validation; live pipe PID/image/held-process identity; restricted global mutation mutex |
| Service | Microsoft Windows-service lifetime; 16 reusable local-only pipe instances; three-second exchanges; ready event; bounded cancellation; console mode must be explicit |
| Client/Control | Synchronous status/events/start/stop/restart; one JSON envelope; documented exit codes; missing service reported honestly; no implicit install/elevation |
| Tray | Original XT icon; one companion per Windows session; slate/teal status window; nonblocking polling and lifecycle actions; independent Close/Exit; configurable loopback Tlamatini URL |
| Packaging | Framework-dependent publish; explicit first-install, registration removal and per-user logon scripts; scripts require verified foreground development console |

The pipe's DACL grants the selected operator data read/write rights without permission to create another pipe instance. SYSTEM, administrators and the service identity can administer the endpoint. The kernel rejects remote clients. Client SQOS is identification-only. Pipe observations verify the live server process before accepting data; installed mode additionally checks SCM. The separate development endpoint is never reported as an installed/running SCM service.

Protocol clarification from live testing: after reading a complete framed reply, a client sends byte `0x06`. The server waits within the same three-second deadline before disconnecting. Without this acknowledgement, Windows can discard unread reply bytes when an instance is reused. No second request is dispatched on that connection. Semantically invalid requests receive a correlated error; malformed/oversized frames are disconnected. The CLI forwards `next_cursor` and `cursor_expired` for events.

Start/Stop/Restart operate entirely through SCM and do not wait for pipe health. Their 30-second deadline returns failure/timeout rather than guessing success or killing a process. Mutations serialize across processes through a Windows mutex restricted to the configured operator, administrators and SYSTEM. Synchronous results use `request_id`; persistent `operation_id` receipts and automatic retries are not part of this foundation. Do not retry Restart blindly after a controller disconnect.

## Verification

See [the dated verification record](verification/2026-10-11-foundation.md) for exact checks, results, initial defects and limitations. Tests execute visibly, including the temporary real service-host process. That process shuts itself down after 12 seconds and is never registered with SCM. The tray's native status window was inspected on the real desktop; shell notification-area positioning remains Windows-controlled.

NuGet is the sole package source. `Microsoft.Extensions.Hosting.WindowsServices` is pinned to `10.0.12`, SDK to `10.0.401` (latest patch roll-forward), and transitive dependencies are locked. NuGet audit is enabled. No Snyk scan, hook, skill or package is used. Microsoft references: [Worker services on Windows](https://learn.microsoft.com/en-us/dotnet/core/extensions/windows-service), [named-pipe ACLs](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights), [package metadata](https://www.nuget.org/packages/Microsoft.Extensions.Hosting.WindowsServices/10.0.12).

## Not implemented or not accepted yet

- Actual installed-service acceptance, cross-account/remote-pipe tests, reboot/sign-out tests and Explorer restart verification. Current token is unelevated; native installation was not performed.
- Force termination, UAC/host consent, elevated helper, durable receipts and restart request deduplication. `force_stop` is explicitly false.
- Signed release installer, update/repair/rollback and automatic file cleanup on uninstall. Scripts are a reviewable first-install foundation, not a certified release installer.
- Persistent service-specific log files and the proposed local-log menu. Installed hosting diagnostics use the Windows Application log (`.NET Runtime` source); the activity ring is ephemeral.
- The proposed tray consent IPC and full Tlamatini panel. Double-click currently opens the native status window; the optional menu link opens an existing Tlamatini URL, without assuming its port or adding a panel route.
- Functional business workload. The service only demonstrates lifecycle, readiness and heartbeat.

These limitations must remain visible in future handoffs; source/console tests do not certify a Windows installation.
