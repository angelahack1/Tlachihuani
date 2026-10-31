# Visible development scripts

`Build.ps1 -Mode Build|Check|Publish` restores locked packages, builds Release and optionally verifies or publishes the three executables. `Check` includes a temporary real console-mode service host and gracefully stops it. `Assert-Visible.ps1` refuses a missing, minimized, hidden or non-foreground console. Run in one visible classic PowerShell console with `-NoExit`; keep its output open and monitor long checks every 5–15 seconds.

These checks apply to developer execution, not extra end-user service consoles. See [development policy](../docs/development-execution.md).
