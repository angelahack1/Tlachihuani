# Next session: native Windows installation acceptance

Updated 2026-10-31. Work in `C:\Development\XAIHT\Tlachihuani`; keep `C:\Development\XAIHT\Tlamatini` read-only. Tlachihuani upstream is https://github.com/angelahack1/Tlachihuani (`https://github.com/angelahack1/Tlachihuani.git`). Tlamatini upstream is https://github.com/XAIHT/Tlamatini.

Read AGENTS.md, CLAUDE.md and [implementation status](docs/implementation-status.md), including its evidence and known gaps, before continuing. The older design documents contain planned features beyond the current implementation.

## Available now

- Eight buildable .NET projects in `Tlachihuani.slnx`; pinned SDK/package and NuGet lock files.
- Windows Service host, explicit console development mode, heartbeat, 256-event in-memory history and a 16-client local-only pipe with explicit Windows ACLs.
- Controller `status`, `events [--cursor N]`, `start`, `stop`, `restart`; SCM state remains separate from pipe health. Fixed service identity, process-image checks, 30-second lifecycle deadlines and a restricted cross-process mutex.
- WinForms XT tray, native panel, per-session singleton and independent tray exit. As of 2026-10-31 the icon menu shows only **Show panel** and **Exit tray (service keeps running)**. Six optional rows are retained in `src/Tlachihuani.Tray/TrayMenu.cs`; lifecycle controls and refresh remain in the panel. See [the tray contract](docs/panel-and-tray.md#tray).
- Visible build/check/publish scripts, first-install/unregister and per-user tray-startup scripts. Packaging scripts have not been run against SCM/registry.
- `artifacts/publish/Service`, `/Control`, `/Tray` contain framework-dependent Windows x64 binaries. Use .NET 10 Desktop Runtime.

## Next work

1. Agree on the actual test installation/account before registering a service. The initial script uses `%ProgramFiles%\XAIHT\Tlachihuani`, `%ProgramData%\XAIHT\Tlachihuani`, `NT SERVICE\Tlachihuani`, and a required operator account/group. The implementation session was unelevated and did not install anything.
2. From a verified visible elevated development console, review and exercise `packaging/windows/Install.ps1` on that authorized target. Verify service-account startup, operator versus outsider permissions, pipe remote denial, protected manifest/files, Start/Stop/Restart, account sign-out, tray independence, Explorer restart, delayed boot start and crash-restart disabled. Parse-only script validation is not installed acceptance.
3. Harden packaging recovery/repair/update, real cleanup/uninstall and signing. `Unregister.ps1` removes only verified SCM registration and preserves all files/data. The first-install script refuses existing directories and disables any newly created service if configuration fails.
4. Implement explicit host-consent force-stop with held process identity and a narrowly scoped elevated helper. Add durable operation receipts/restart deduplication before any asynchronous web integration. Current commands are synchronous; `force_stop` capability is false.
5. Only after separate authorization, add the Tlamatini Panels entry and Django adapter. The future panel must control this service without involving Tlamatini's agent process reaper.

No business workload has been selected. Do not invent agents, model calls, microphone access, or arbitrary execution.

Run development commands only in a verified visible foreground console and leave it open after checks. Use one console, not repeated launchers. Snyk is disabled at Angela's request; do not use it. A fresh Codex session may be needed to reload that global setting.
