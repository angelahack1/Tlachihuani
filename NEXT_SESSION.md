# Tlachihuani handoff · 31 October 2026

Work in `C:\Development\XAIHT\Tlachihuani`. The separate Tlamatini reference checkout is `C:\Development\XAIHT\Tlamatini`. Read AGENTS.md, CLAUDE.md, [the Torrenter operating guide](docs/torrenter.md) and [implementation status](docs/implementation-status.md). The design baseline is Revision 05 of `TlachihuaniKickoffDesign.html` on Angela’s Desktop.

## Installed now

* On ANGYSLAP the independent `Tlachihuani.Jobs` service is registered for delayed automatic startup under its own virtual account. The delegated operator is `ANGYSLAP\angel`. XT → Show panel → Services… manages Torrenter and opens its loopback workspace on port 12064. Jobs has a separate manifest from the original service.
* The solution carries the original SCM service, native controls and tray, plus the Jobs host, its enrolled providers, web assets and private torrent runtime. The tray context menu still has two entries. The optional historical commands are preserved in `src/Tlachihuani.Tray/TrayMenu.cs`.
* `scripts/Build.ps1 -Mode Check` covers the original lifecycle. Publish, then run `scripts/Test-Jobs.ps1` for a real private swarm and crash/recovery checks. Supply a Playwright-capable Python and an installed Chrome for the explicitly headed workflow. Follow [the visible-execution policy](docs/development-execution.md).
* The installed XT/Chrome run on 31 October exercised the native code approval, upload, all detail tabs, stop, filter and record removal. The delegated account exercised actual SCM stop and start. The original Tlachihuani registration remained stopped. Installation and update retained the independent Jobs identity.

## Next work

1. Complete the release acceptance gates with a sign-out/Explorer restart, reboot, power interruption, multi-day transfer, a second real Windows login and packaged signing/rollback qualification. Keep the original service’s force-stop consent helper on its own backlog.
2. Extend tracker error telemetry and rate-history visualization, and qualify large queues, network failures and disk exhaustion. The current REST and UI surfaces are listed in the [Torrenter guide](docs/torrenter.md).
3. When separately authorized, implement Tlamatini’s wrapped Torrenter client, using the scoped REST contract and trusted-account enrollment. The future Tlamatini Panels integration and agent catalog belong to that checkout. Preserve its protected database mechanics.

Tlachihuani upstream is [angelahack1/Tlachihuani](https://github.com/angelahack1/Tlachihuani). Tlamatini upstream is [XAIHT/Tlamatini](https://github.com/XAIHT/Tlamatini). Keep the implementation uncommitted until Angela requests otherwise. Snyk remains disabled.
