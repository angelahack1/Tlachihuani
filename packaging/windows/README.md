# Windows packaging foundation

For a new graphical installation use the [Windows setup wizards](../setup/README.md). The scripts below maintain script-managed installations and use different ownership records.

Run `scripts/Build.ps1 -Mode Publish` from a verified visible foreground PowerShell console. Published binaries are framework-dependent Windows x64 builds and require the .NET 10 Desktop Runtime. They are not signed release artifacts.

**Independent Jobs workload.** See [the Torrenter operating guide](../../docs/torrenter.md) for first installation, update, runtime requirements, delegated controls and verification. `Install-Jobs.ps1`, `Update-Jobs.ps1` and `Unregister-Jobs.ps1` target the separate Jobs registration. The remaining instructions describe the original service packaging. Agree on a test target/operator, then review these scripts before running them in one visible elevated console. Leave the console open afterward. None launches hidden development commands or automatically elevates.

- `Install.ps1 -OperatorAccount 'MACHINE\SelectedUserOrGroup'`: first install only; refuses an existing service/directory. Copies the three components to `%ProgramFiles%\XAIHT\Tlachihuani`; creates a protected manifest at `%ProgramData%\XAIHT\Tlachihuani\installation.json`; configures the fixed own-process service under `NT SERVICE\Tlachihuani`, delayed automatic startup and explicit operator ACLs. A new service has no crash-restart actions. It remains stopped after installation. On a configuration failure the newly created service is disabled and files are retained for inspection.
- `Unregister.ps1`: validates the fixed installed image, requests graceful Stop through the controller, observes Stopped and removes only the SCM registration. It does **not** erase files, data or per-user startup entries. This is not yet a complete release uninstaller.
- `Set-TrayStartup.ps1` / `-Disable`: run as the intended interactive Windows user, in a visible console. Adds/removes only the owned `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value `XAIHT.Tlachihuani`; refuses a conflicting value. Does not launch the tray or start the service.

After installation, run the published `Control\Tlachihuani.Control.exe status`, `start`, `stop` or `restart` from the visible console. Start never installs anything. The independent `Tray\Tlachihuani.Tray.exe --show` opens the status window and XT icon; exiting it does not stop the service.

The Tlamatini link is omitted from the current XT menu. If re-enabled in [TrayMenu.cs](../../src/Tlachihuani.Tray/TrayMenu.cs), it reads the optional per-user `%LOCALAPPDATA%\XAIHT\Tlachihuani\tray.json`: `{"tlamatini_url":"http://localhost:YOUR_ACTUAL_PORT/"}` with the actual port substituted. Only HTTP(S) loopback URLs without embedded credentials are accepted; with no valid URL, the restored entry is disabled. No Tlamatini source or configuration is changed by these scripts.

Next acceptance must cover virtual-account startup, operator/outsider rights, protected installation files, remote pipe rejection, Start/Stop/Restart from the tray and CLI, logon/sign-out, Explorer restart, boot behavior, partial-install recovery and registration removal. PowerShell syntax checks alone do not certify those behaviors.
