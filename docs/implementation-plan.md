# Implementation sequence

The first implementation covers the code foundation of phases 1–3 and initial packaging scripts. See [current implementation status](implementation-status.md) for actual evidence and unfinished acceptance gates; the phase table below remains the full roadmap. Use the [visible execution policy](development-execution.md) throughout.

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 1. Contracts and solution | Actual .NET solution/projects, reviewed package versions, JSON validation, state/operation model | Contracts serialize/validate with meaningful malformed/version/deadline cases; no external Tlamatini dependency |
| 2. Service foundation | Worker host, visible developer console mode, cancellation, heartbeat, bounded logs, native SCM adapter | Console lifecycle is observed; a real service installation is tested only in an explicitly authorized location/account |
| 3. Control and tray | Shared pipe client, JSON controller, fixed-service SCM controls, original XT icon | Start/status/stop from controller and tray; tray survives service stop and Explorer restart; denied access is clear |
| 4. Force-stop and isolation | Local-consent/elevation helper, operation serialization, request receipts, identity checks | Hung own-service termination succeeds; PID reuse, path substitution, unrelated process, canceled UAC, parallel controls remain safe |
| 5. Packaging | Independent installer/uninstaller, discovery, logon registration, release manifest | Actual installed binaries pass lifecycle/tray tests; clean removal respects retained data and Tlamatini |
| 6. Tlamatini panel — deferred | Menu, themed modal, Django adapter/API, packaging/cache integration | Only after Angela authorizes editing Tlamatini; visible source and installed/frozen integration checks |
| 7. Workload | Specific useful background capability selected by Angela | Separate requirements, cancellation/resource/privilege design and end-to-end acceptance |

Begin with a small genuine vertical slice: service state + health + tray display + Start/Stop. Do not write mock code that reports running before SCM and health observations exist. Keep force-stop unavailable until ownership/consent is implemented.

No GitHub automation or release publishing belongs in these phases unless Angela later requests it. She will create the repository personally. No `dotnet new`, package restore, build, installation or test command is claimed to have run during the design-only preparation.
