# Visible desktop checks

Real XT tray presence/menu, Explorer restart, per-session behavior, DPI, keyboard operation and host consent. Every harness must be visible, monitored and retain truthful evidence; no headless mode. See [the execution policy](../../docs/development-execution.md).

For the installer and uninstaller UI, use [the setup acceptance commands](../../packaging/setup/README.md#reproduce-a-build).

From a verified foreground PowerShell console, build the solution in Release, then run the native dialog audit at the desktop DPI and the Windows 96-DPI baseline. Both runs display the production forms, measure their controls at default and minimum size, and save screenshots. Credential and erasure views use fixtures.

```powershell
$checks = '.\tests\Tlachihuani.Checks\bin\Release\net10.0-windows\Tlachihuani.Checks.exe'
& $checks --tray-layout '.\artifacts\verification\dialogs' desktop
& $checks --tray-layout '.\artifacts\verification\dialogs' 96dpi
```
