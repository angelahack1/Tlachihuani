# Verification plan

Actual foundation results are in [the 2026-10-11 record](verification/2026-10-11-foundation.md). The cases below remain acceptance requirements, not claims of completion.

This is a future acceptance matrix. Every runtime case is **NOT_RUN** in the design scaffold. Documentation integrity and the source inventory are separate checks, recorded in [source-review.md](source-review.md).

Run every command/test from a verified visible foreground console; use browser automation with explicit `headless: false` / `headless=False`. Keep the console open after completion, monitor long runs every 5–15 seconds and retain exit code plus observed application result. A background Windows service is verified from that visible console and the actual tray/UI; it does not need a product console.

| ID | Case | Required evidence |
|---|---|---|
| S01 | Real SCM registration/start/stop | Correct service type/account/path; pending→running/stopped states; process handle and health |
| S02 | Duplicate Start/Stop from two controllers | Serialized/idempotent outcome, no duplicate service |
| S03 | Stop blocked by a hung workload | Deadline, honest timeout, no silent force escalation |
| S04 | Force kill of that hung service | Local consent, verified identity, exact process exit, SCM stopped, no automatic restart |
| S05 | PID reused, binary substituted, instance changed | Refusal; unrelated process remains alive |
| S06 | Tlamatini/browser/tray exits | Service remains independent; no reaper/updater ownership |
| S07 | Service crash, logoff, reboot, sleep/resume | State/freshness correct; documented delayed automatic boot start |
| P01 | Pipe denied/network client, malformed/oversized/truncated frame | Bounded refusal without crash, hang or secret leak |
| P02 | Spoofed pipe server or wrong protocol major | Refusal and actionable incompatible/unavailable state |
| P03 | Empty JSON, process exit 0, stale replies | No false success; correct timeout/staleness handling |
| T01 | Actual XT tray icon at 100/150/200% DPI | Visible icon or Windows overflow; legible tooltip and keyboard menu |
| T02 | Explorer restarts; tray launched twice | Icon re-registers; one instance per session |
| T03 | Multiple Windows sessions | Session-specific tray status/consent; shared service state |
| T04 | Exit tray / UAC denied / no interactive session | Service continues or operation cancels honestly; no invisible elevation |
| W01 | Future menu and modal while chat answers | Panels stays available; chat unaffected; correct shared theme |
| W02 | Escape/X/outside click/Tab/zoom/reduced motion | Shared dismissal policy, focus trap/return, readable content and reachable footer |
| W03 | Unauthorized account, CSRF, GET mutation, account switch | Backend refuses mutation/leak; stale account response discarded |
| W04 | Two tabs, modal close/reopen, remote host browser | Coalesced polling, operation reconciliation, host scope explicit |
| W05 | Service absent, stopped, unresponsive, wrong version | Accurate separate SCM/health/UI states, no blocked chat startup |
| I01 | Real compiled clean install and uninstall | Owned registrations/startup/data behavior, actual compiled-client checks |
| I02 | Upgrade while running/stopped and failed upgrade | Correct desired state, rollback evidence, retained configuration |
| I03 | Tlamatini source versus frozen installed integration | Separate verdicts, correct controller discovery and asset carriage |

Every result records artifact/version/hash, Windows/session, action, expected and observed state, timestamp, status (PASS/FAIL/BLOCKED/NOT_RUN), evidence path, and cleanup. Do not claim installation success from a helper-only or mocked test. Do not test force kill on the user's unrelated processes. Installation/destructive lifecycle verification uses an explicitly authorized test target.
