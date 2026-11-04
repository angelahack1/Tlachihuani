<!-- Tlachihuani — Created for Angela López Mendoza · XAIHT · @angelahack1 -->
# Tlachihuani implementation contract

This is the onboarding document for Claude, Codex, and every coding agent working on Tlachihuani.

For v0.2.1 ZIP packaging, migration and verification, read the [packaging notes](docs/releases/v0.2.1.md) and the [Windows setup guide](packaging/setup/README.md). Change the product version in `Directory.Build.props` and refresh internal project lock references together.

`Build-Release.cmd` is the root release entry point. It chooses the highest stable local Git tag numerically, stamps product/internal project versions, rebuilds into fresh staging and verifies before copying the install ZIP to `dist`. It never commits, tags or pushes. See [release building](docs/release-building.md). Setup asks whether XT should appear at sign-in, always installs Start/Desktop shortcuts, and leaves both services stopped/Manual. Startup shortcuts must never start services. Preserve the distinction between the original unelevated wizard and its privileged MSI helper.

## Project identity and controller

**Project root:** `C:\Development\XAIHT\Tlachihuani`.
Its GitHub repository is **https://github.com/angelahack1/Tlachihuani**; the verified Git origin is **https://github.com/angelahack1/Tlachihuani.git**.

**Tlamatini reference checkout:** `C:\Development\XAIHT\Tlamatini`.
Its Django source root is `C:\Development\XAIHT\Tlamatini\Tlamatini`.
Its GitHub repository is **https://github.com/XAIHT/Tlamatini**; the verified Git origin is **https://github.com/XAIHT/Tlamatini.git**.

Tlachihuani is a completely separate Windows application/service. **Tlamatini will control it** through a new themed dialog named **Tlachihuani**, under Tlamatini's **Panels** menu. That dialog will raise/start, monitor, gracefully stop, and explicitly force-terminate this service. The panel is planned only; Angela expressly deferred all Tlamatini modifications during this design session.

The 2026-10-11 review used Tlamatini HEAD `c18d50815cfe8b1681f805fd4e76c66fbaeabaf6`, not just the older v1.78.0 tag. Recheck source before integration because this is a dated design reference.

## Read order

1. [AGENTS.md](AGENTS.md), [NEXT_SESSION.md](NEXT_SESSION.md), [architecture](docs/architecture.md).
2. [Lifecycle](docs/lifecycle.md), [control protocol](docs/control-protocol.md), [security and installation](docs/security-and-installation.md).
3. [Panel/tray specification](docs/panel-and-tray.md) and [Tlamatini integration](docs/tlamatini-integration.md).
4. [Implementation plan](docs/implementation-plan.md), [verification plan](docs/verification-plan.md), [source review](docs/source-review.md).
5. Before editing Tlamatini in a later authorized session, read its `AGENTS.md`, `CLAUDE.md`, `TestsVisiblesAndVisibleExecutionFromClaude2Codex.md`, and `docs/claude/INDEX.md` at the full checkout path above. Relevant skill paths and applicability are indexed in [skill-inventory.md](docs/skill-inventory.md).

## Torrenter and the Jobs host

Read [the operating and REST contract](docs/torrenter.md). The independent `Tlachihuani.Jobs` SCM service owns the provider registry and child-process lifetime. A protected worker journal owns transfer state, permissions and durable receipts. XT manages providers on the Jobs v2 pipe. The web facade at `127.0.0.1:12064` exposes the transfer API to paired browsers and enrolled automation clients. SCM installation, delegated control and headed XT pairing were tested on 2026-10-31.

## Original service design decisions

- SCM service name and display name: `Tlachihuani`; own-process Windows service.
- Resident binaries implemented: `Tlachihuani.Service.exe` (SCM/Session 0 or explicit development console) and `Tlachihuani.Tray.exe` (signed-in user's session).
- `Tlachihuani.Control.exe` implements synchronous JSON/SCM bridging. `Tlachihuani.Elevated.exe`, force-stop, durable operation receipts and host consent are still future work.
- C#/.NET 10 Worker Service + WinForms tray; solution `Tlachihuani.slnx`, SDK `10.0.401`, WindowsServices package `10.0.12`, lock files saved in each project. See [implementation status](docs/implementation-status.md).
- Reuse the existing XT icon copied from `C:\Development\XAIHT\Tlamatini\Tlamatini.ico`, with provenance in `assets/branding/`. Do not generate a replacement logo.
- Local-only named-pipe IPC, explicit Windows ACLs, bounded/versioned messages. Tlamatini exposes authenticated same-origin web endpoints; the browser never talks directly to the service.
- No dependency on Tlamatini's Django database, Python imports, RAG/model loop, agent pool, or process reaper.
- Install, update, uninstall, and application data are owned by Tlachihuani. Do not reuse Tlamatini's installer or database handling.
- Stop/kill are different actions. A killed process must remain stopped for the current boot, and success must be observed through SCM and process exit. First-release SCM crash-restart actions are off.
- The tray remains available to show a stopped or unavailable service. Exiting the tray does not stop the service. Closing the panel does neither.

## Development conduct

Follow [development-execution.md](docs/development-execution.md): verified visible foreground development console; explicitly headed browser automation; no invisible test or diagnostic; monitor live and retain exit codes. This is not a requirement for extra end-user service consoles.

Work only within the new project unless the user broadens scope. Do not create a GitHub repository, invent its URL, initialize a remote, commit, publish, or push without instructions. Angela will create the repository personally. Preserve authorship and never rewrite history.

Angela explicitly rejected Snyk on 2026-10-11. Do not use its skills, hooks or tools. Its global Codex server/hooks/skills were disabled at her request. NuGet audit remains enabled for this solution.

Tlamatini's protected SQLite backup/restore mechanics are out of scope. Its `build.py` erases its development database and dist tree; do not run it for this project. No source changes there, database migrations, installations, registry writes, or service registrations were performed for this scaffold.

## Completion standards

Use separate evidence for design review, unit checks, native SCM/service checks, tray UI, future Tlamatini browser integration, and installed release acceptance. A JSON fixture, mockup, or exit code alone cannot prove a running service or a visible tray icon.

Torrenter is the first Jobs provider. Add later providers through the Jobs registry, and keep torrent-specific operations in its adapter. Consult the dated verification records before claiming installed acceptance.
