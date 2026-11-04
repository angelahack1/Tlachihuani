# Tlachihuani handoff · 4 November 2026 · v0.2.1 packaging

Work in `C:\Development\XAIHT\Tlachihuani`. The separate Tlamatini reference checkout is `C:\Development\XAIHT\Tlamatini`. Read AGENTS.md, CLAUDE.md, [the Torrenter operating guide](docs/torrenter.md) and [implementation status](docs/implementation-status.md). The design baseline is Revision 05 of `TlachihuaniKickoffDesign.html` on Angela’s Desktop.

## Latest release and installation evidence

**Latest released version: v0.2.1.** It includes the offline ZIP package, private runtimes and Windows uninstall registration. For fresh deployments, use the [graphical Windows setup guide](packaging/setup/README.md) and [release notes](docs/releases/v0.2.1.md). Read the [verification status](docs/implementation-status.md) for the actual test scope. The last recorded workstation installation was the 0.1.0 wizard installation on 3 November 2026; the operator confirmed the green XT icon, a ready Jobs API and the signed-in workspace. That dated installation evidence does not change the latest released version.

* On ANGYSLAP both services are set to Manual. The delegated operator is `ANGYSLAP\angel`. XT starts independently at user sign-in. **Start Services** brings up the services and Torrenter on port 12064. **Stop Services** leaves only XT running. Jobs has a separate manifest from the original service.
* XT is gray until both services are running and Torrenter's API responds. The context menu also offers **Show panel** and **Exit tray**. The exit label reads **Exit tray (service keeps running)** until XT confirms both services are stopped or absent and any pending change finishes. The optional historical commands are preserved in `src/Tlachihuani.Tray/TrayMenu.cs`.
* `scripts/Build.ps1 -Mode Check` covers the original lifecycle. Publish, then run `scripts/Test-Jobs.ps1` for a real private swarm and crash/recovery checks. Supply a Playwright-capable Python and an installed Chrome for the explicitly headed workflow. Follow [the visible-execution policy](docs/development-execution.md).
* The installed XT/Chrome run on 31 October exercised the native code approval, upload, all detail tabs, stop, filter and record removal. The delegated account exercised actual SCM stop and start. The original Tlachihuani registration remained stopped. Installation and update retained the independent Jobs identity.

## Next work

The root release command is now `Build-Release.cmd`; read [release building](docs/release-building.md). It rebuilds the current checkout at the latest numeric local Git-tag version and emits a checked ZIP/checksum in `dist`. Setup now asks for the optional common login shortcut and always creates Start/Desktop shortcuts. Services remain Manual/stopped after installation and reboot. The normal unelevated installer opens XT once after success; an elevated launch directs the operator to the normal Desktop shortcut.

1. Complete the release acceptance gates with a sign-out/Explorer restart, reboot, power interruption, multi-day transfer, a second real Windows login and packaged signing/rollback qualification. Keep the original service’s force-stop consent helper on its own backlog.
2. Extend tracker error telemetry and rate-history visualization, and qualify large queues, network failures and disk exhaustion. The current REST and UI surfaces are listed in the [Torrenter guide](docs/torrenter.md).
3. Keep the existing Tlamatini wrapped Torrenter client compatible with the scoped REST contract. The future Tlamatini Panels integration and agent catalog belong to that checkout. Preserve its protected database mechanics.

Tlachihuani upstream is [angelahack1/Tlachihuani](https://github.com/angelahack1/Tlachihuani). Tlamatini upstream is [XAIHT/Tlamatini](https://github.com/XAIHT/Tlamatini). Keep the implementation uncommitted until Angela requests otherwise. Snyk remains disabled.
