# Visible development execution

Angela's visibility requirement applies to this project as well as Tlamatini. Authoritative reference: `C:\Development\XAIHT\Tlamatini\TestsVisiblesAndVisibleExecutionFromClaude2Codex.md` and its `AGENTS.md`.

Every development command, diagnostic, script, test, build and automated browser must run in a visible, forked foreground window on Angela's real interactive desktop. Verify visibility before releasing the workload. A PID, accepted launch or focus request is insufficient. If the tooling cannot observe the window, obtain explicit user confirmation or stop the dependent execution. Do not repeatedly open duplicate windows because a desktop inventory omits consoles.

Use PowerShell `-NoExit` or CMD `/k` so output remains readable. The normal PowerShell launch pattern is `Start-Process -WindowStyle Normal` with `-NoProfile -NoExit -File` arguments pointing to a prepared script. A launcher should initially gate its workload until visibility is established. Explicit conhost is an option when Windows Terminal delegation obscures ownership. Discover a window by title, not only the process owning the command.

`scripts/Assert-Visible.ps1` waits up to 90 seconds for its own console to
become foreground after launch or elevation. Click inside the same window if it
is waiting. Classic consoles are verified by their window handle. For a
[pseudoconsole](https://learn.microsoft.com/en-us/windows/console/getconsolewindow),
the guard briefly sets a unique [shell title](https://learn.microsoft.com/en-us/windows/terminal/tutorials/tab-title)
and checks the foreground terminal for it; the previous title is restored.
If a custom tab title prevents verification, use a classic conhost console.
A timeout does not start the workload. Run
`tests/desktop/foreground_console.ps1` from a visible PowerShell console to
exercise acceptance, refusal while another window is in front, and recovery.

Keep launchers ASCII or UTF-8 with BOM for Windows PowerShell 5.1. Configure console/output encoding for UTF-8. Print progress/results and preserve a transcript. During a long run read it every 5–15 seconds, report meaningful changes at least once a minute, inspect the first error and relevant application log, and record the real exit code.

Browser harnesses must explicitly set `headless: false` or `headless=False`, use a visible browser and retain it for inspection. No invisible CI substitutes, hidden developer consoles, detached jobs, minimized workloads, or compatibility flags that enable headless execution. Use Tlamatini's Shoter for whole-desktop verification evidence where available; never report unobserved output as watched.

The rule governs development and verification. The product service remains in Session 0, and the tray/helper processes do not open extra consoles or steal focus. Status belongs in the tray/panel and logs. Observe that product behavior from a visible development console.
