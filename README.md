<!-- Tlachihuani — Created for Angela López Mendoza · XAIHT · @angelahack1 -->
# Tlachihuani

A standalone Windows service with an XAIHT XT system-tray companion, designed to be raised, monitored, stopped, and force-terminated from **Tlamatini → Panels → Tlachihuani**.

**Status on 31 October 2026.** The independent Jobs service and its first provider, Torrenter, are implemented and installed on the authorized Windows test machine. Open **XT → Show panel → Services… → Open workspace** for downloads. The versioned REST API serves browser and application clients. [Operator and REST guide](docs/torrenter.md) · [Verification record](docs/implementation-status.md).

## Relationship to Tlamatini

| Reference | Location |
|---|---|
| This independent project | `C:\Development\XAIHT\Tlachihuani` |
| Tlachihuani on GitHub | [github.com/angelahack1/Tlachihuani](https://github.com/angelahack1/Tlachihuani) |
| Tlachihuani Git origin | `https://github.com/angelahack1/Tlachihuani.git` |
| Tlamatini source checkout | `C:\Development\XAIHT\Tlamatini` |
| Tlamatini Django application | `C:\Development\XAIHT\Tlamatini\Tlamatini` |
| Tlamatini on GitHub | [github.com/XAIHT/Tlamatini](https://github.com/XAIHT/Tlamatini) |
| Verified origin | `https://github.com/XAIHT/Tlamatini.git` |
| Design reference revision | `c18d50815cfe8b1681f805fd4e76c66fbaeabaf6` (`v1.78.0-4-gc18d5081`) |

Tlamatini is the future control interface. Tlachihuani owns its service, tray process, local control protocol, installation, state, and logs. It is not a Tlamatini workflow agent or an ACPX/MCP plugin. Tlamatini closing, updating, or uninstalling must not implicitly terminate or remove Tlachihuani.

Windows services cannot host the interactive tray UI directly. The original design uses two resident processes: a service managed by Windows Service Control Manager (SCM), and a tray companion in each participating signed-in Windows session. A small on-demand controller bridges Tlamatini's Python backend to native Windows APIs. See [architecture](docs/architecture.md).

## Start here next session

Open this folder as the workspace. Read [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), then [NEXT_SESSION.md](NEXT_SESSION.md). The implementation sequence and acceptance gates are in [the roadmap](docs/implementation-plan.md) and [verification plan](docs/verification-plan.md).

The stack is C# / .NET 10 with a Worker Service, WinForms `NotifyIcon`, shared native Windows library, and JSON CLI. SDK `10.0.401` and Microsoft WindowsServices `10.0.12` are pinned, with NuGet lock files. No Snyk integration is used.

## Build and run

Open one visible foreground classic PowerShell console (`conhost.exe powershell.exe -NoProfile -NoExit`) and keep it open. The build scripts verify foreground visibility before running. In that console:

```powershell
Set-Location -LiteralPath 'C:\Development\XAIHT\Tlachihuani'
.\scripts\Build.ps1 -Mode Check
.\scripts\Build.ps1 -Mode Publish
.\artifacts\publish\Control\Tlachihuani.Control.exe status
.\artifacts\publish\Tray\Tlachihuani.Tray.exe --show
```

The framework-dependent binaries require Windows x64 and the .NET 10 Desktop Runtime and, for Jobs, the ASP.NET Core 10 shared runtime. `Check` runs boundary checks and a real, temporary console service host; it does not install a Windows service. `Publish` creates `Service`, `Control`, `Tray`, and `Jobs` directories under `artifacts/publish/`.

The controller accepts `status`, `events [--cursor N]`, `start`, `stop`, and `restart`, and emits one JSON reply. Start never installs anything. The tray remains available while stopped; Close hides its status window, and Exit tray leaves the service alone. For actual registration, read [Windows packaging](packaging/windows/README.md) first.

## Design contents

- [Architecture and process responsibilities](docs/architecture.md)
- [Service lifecycle, start/stop/kill semantics](docs/lifecycle.md)
- [Future Tlamatini integration map](docs/tlamatini-integration.md)
- [Panel and tray experience](docs/panel-and-tray.md)
- [Control protocol and error contract](docs/control-protocol.md)
- [Privileges, identities, and local IPC](docs/security-and-installation.md)
- [Whole-repository review and its limits](docs/source-review.md)
- [All repository skills and applicability](docs/skill-inventory.md)
- [Actual scaffold tree](docs/project-tree.md)
- [Original XT icon provenance](assets/branding/README.md)

## Scope boundary

The original service provides lifecycle control and health reporting. The independent Jobs host runs Torrenter, the first implemented workload. The Tlamatini wrapped agent will consume the same owner-scoped API as the browser.

**Do not edit Tlamatini or add its menu entry until Angela explicitly authorizes that integration. Do not create a GitHub repository, publish, or push this project on her behalf.**
