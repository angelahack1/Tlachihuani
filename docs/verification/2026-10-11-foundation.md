# Foundation verification — 2026-10-11

Environment: Windows 11 x64 (10.0.26200), .NET SDK 10.0.401, .NET/WindowsDesktop runtime 10.0.12, unelevated Windows account. Development ran through one visible classic PowerShell console with Win32 foreground/visible/nonminimized verification before each job. Product test output was streamed into that console; local transcripts were inspected during the work. No service or startup registration was created.

## Completed checks

| Check | Result | Evidence |
|---|---|---|
| Locked restore and Release build | PASS, zero warnings/errors | `Temp/implementation-20261011/final-checks.txt` |
| Ten executable checks | PASS | Same file; real host PID 34484 exited gracefully at 11:43:12 local time |
| Frame bounds and malformed/truncated input | PASS | Zero/oversized/negative lengths, truncated body, malformed UTF-8 |
| Protocol validation and event retention | PASS | Unknown operations/versions, request IDs, event bounds, 256-event ring, cursor expiry, distinct boot IDs |
| Core lifecycle semantics | PASS | Idempotent Start/Stop, ordered Restart, missing service, hung-stop timeout without termination, failed-start reconciliation during Stop |
| Native local pipe / process identity | PASS | Read-only development status and wrong-image refusal |
| Real console host | PASS | 32 concurrent clients, advancing heartbeat, ready event/cursor, correlated incompatible-version error, read-only development mode, graceful 12-second shutdown, unreachable afterward |
| Three executable publishes | PASS | `Temp/implementation-20261011/final-publish.txt`; outputs in `artifacts/publish/` |
| Published CLI envelopes and exit codes | PASS | Status 0 / not_installed; Start, Stop, Restart 3; arbitrary command 2; `job-09-final-build.ps1.log` |
| NuGet dependency audit | PASS, no known vulnerable packages reported by configured source | `nuget-audit.txt`; includes transitive dependencies; not a guarantee against undisclosed vulnerabilities |
| Five PowerShell scripts | PASS syntax parsing | Install, Unregister, Set-TrayStartup, Build, Assert-Visible; `job-08-release.ps1.log` |
| Original XT identity | PASS | SHA256 `71de562b49020a30d3ea0d2e5813ce11611fed09250e9340c46f5444237d34be` |
| Native tray status window | PASS visual/accessibility inspection | Published executable, original XT in title/header, slate/teal styling, honest Not installed state, disabled lifecycle actions, Refresh/Close/Exit controls |
| Per-session tray singleton | PASS observed | Second preview process exited while original preview remained; only one status window |
| Published tray Exit action | PASS after repair, exit 0 | `job-17-clean-exit.ps1.log`; visible Exit link exercised, no remaining test process or window |
| Tlamatini preservation | PASS | Clean working tree before and after; no local Git metadata initialized here |
| Snyk disabled at user request | PASS configuration validation | Global Codex MCP `enabled=false`, three hook registrations commented, both local Snyk skills disabled; TOML parsed successfully |

## Defects found and corrected

1. WinForms serialization analyzer required an explicit nonserialized policy for the internal close-state property. Fixed; subsequent builds were clean.
2. Immediate pipe disconnect discarded unread responses under concurrent load. Added a three-second bounded client receipt acknowledgement; the real 32-client run then passed.
3. Stop waiting on a pending startup originally treated a failed startup as a failed Stop. It now recognizes the resulting Stopped state; a regression case passes.
4. The first temporary preview cleanup lost its process object across script scopes. The old preview was subsequently identified by its held handle, exact path and creation time, then stopped before inspecting the published tray. This affected the development harness, not product service ownership.
5. A final audit script attempted unavailable `Get-FileHash`; build, publish and CLI checks had already passed. Repeated only the audit with .NET SHA256, verified the expected XT hash and clean Tlamatini status. The initial audit failure is retained in its transcript.
6. Real tray Exit exposed double disposal of the application's cancellation source. Windows Application log identified `ObjectDisposedException` in `TrayContext.Dispose`. Made resource cleanup idempotent and captured the cancellation token before dispatching background reads. Republished the tray and repeated its visible Exit action: process exit **0**, no test processes/windows remained. The earlier harness labeled process completion as PASS despite a nonzero code; that label is superseded by the strict exit-code assertion in `job-17-clean-exit.ps1.log`.

At 11:50:28 local time the development queue stopped, Tlamatini's working tree was still clean, and all Tlachihuani test processes had exited. The single development console was left open and idle for inspection. No Snyk MCP/hook process appeared in the targeted process inventory. Global Codex settings may require an app restart to reload completely.

## NOT_RUN / future acceptance

- SCM install/start/stop/restart under the virtual service account; operator versus outsider ACLs; restricted global mutex contention across real installed clients.
- Remote named-pipe denial from another machine, crash/boot recovery, service/tray sign-out separation and Explorer restart.
- Direct visual inspection of the Windows notification-area XT icon/overflow. The desktop tool exposed the status window but did not expose the shell notification area as a target. The original icon and NotifyIcon creation are implemented; do not equate this with shell-level acceptance.
- Registered tray logon startup, installed Application log writes, update/repair/uninstall and signing.
- Force-stop/UAC/host consent/durable operation receipts; these are not implemented.
- Tlamatini browser panel, source/frozen integration and any business workload; all remain deferred.

These are foundation results, not release or installed-service certification. Historical preparation/source-review records remain separate in `docs/reference/`.
