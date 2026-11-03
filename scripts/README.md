# Visible development scripts

`Build.ps1 -Mode Build|Check|Publish` restores locked packages, builds Release and optionally verifies or publishes the Service, Control, Tray and Jobs components. `Check` includes a temporary real console-mode service host and gracefully stops it. `Assert-Visible.ps1` refuses a missing, minimized, hidden or non-foreground console. Run in one visible classic PowerShell console with `-NoExit`; keep its output open and monitor long checks every 5–15 seconds.

After publishing, use `Build-Setup.ps1` to build the matching versioned installer and uninstaller. `Test-Setup.ps1` opens the production wizards for a visible Review and Cancel check. The [setup guide](../packaging/setup/README.md) describes the isolated SCM and Windows Sandbox tests.

These checks apply to developer execution, not extra end-user service consoles. See [development policy](../docs/development-execution.md).
