# Windows setup

The two x64 Windows wizards use Tlamatini's dark setup palette, Segoe UI and the original XT icon. Their title and version label use the compiled assembly version sourced from the project's `Directory.Build.props`. Installer.exe contains a compressed Windows Installer package. Uninstaller.exe targets the corresponding registered product. Neither needs the source tree at runtime.

## Install and operate

Use Windows 11 x64. Extract `Tlachihuani-0.2.1-windows-x64.zip` with **Extract All** and read `START-HERE.html`. This package carries private .NET 10 and CPython/libtorrent runtimes; clients do not need to install a runtime or SDK. Sign in as the intended operator. Open **Installer.exe**, choose **Review**, confirm the operator, destination and version, and select **Install**. Approve UAC. If a different administrator supplies credentials, the operator shown in the original review remains the delegated operator.

Before Review, choose **Show XT at Windows sign-in (all users of this PC)** or leave it unchecked. Review displays that choice. After **Installation complete**, the original unelevated wizard opens the gray tray icon once; both services remain stopped. **Start menu and Desktop shortcuts** always reopen XT. If the entire wizard was launched as administrator, use either shortcut from your normal Desktop session. Choose **Start Services** in XT when needed.

The optional per-machine Startup shortcut displays only XT at sign-in. With the option unchecked, no login shortcut is installed. The services use Manual startup under separate virtual accounts and stay stopped after reboot. Signing out/in does not stop services already started by the operator. Windows enforces service permissions separately.

## Remove and reinstall

Stop both services from XT. Exit the tray in every active Windows session. Start the version-matched **Uninstaller.exe**, choose **Review**, then **Uninstall**. Review can be cancelled before applying changes. During Apply, leave the wizard open. The Finish page reports Windows Installer's result and any required reboot.

Windows Installer removes registered services, its own shortcuts and packaged files. Downloads, application-generated exports, job state and account manifests are retained. Reinstall as the original operator. Windows Installed apps also provides removal if the standalone uninstaller is lost. A different-version installation or a script-managed deployment must be maintained using the tools for that installation. An in-place upgrade is not offered by these wizards.

### Moving from 0.1.0 / 0.2.0 to 0.2.1

Stop Services, exit XT, remove the old wizard installation through Windows or its original uninstaller and run the 0.2.1 installer as the same operator. Its build output is `artifacts/setup/0.2.1/windows-x64/`. The previously published 0.2.0 tag is unchanged.

For a legacy PowerShell installation, use its [unregister scripts](../windows/README.md) first. Disable its per-user XT startup entry. Preserve the legacy program directory and both ProgramData directories under separate backup names before a fresh wizard install. A journal in a renamed legacy folder is a backup, not an imported queue. Leave it intact.

## Failures and recovery

Each wizard transaction writes a unique verbose log under `%SystemRoot%\Logs\Tlachihuani-<id>.log`. The result page gives its path. Cancelling UAC before the transaction starts produces no MSI log. Windows Installer rolls back transactional changes on failure. Identity and job data are retained separately. Never delete a job journal to retry setup.

If Review reports an existing service, unexpected image, different operator, or unmanaged state, preserve it and investigate its original installation. If Windows reports another installation in progress, finish it and retry. Stop Services and exit XT before removal. Reboot when Windows reports pending file replacement or removal.

## Reproduce a build

For the complete release, run **`Build-Release.cmd`** from a visible Command Prompt at the repository root (or `.\Build-Release.cmd` in PowerShell). It reads the latest numeric local release tag, stamps product versions, rebuilds into fresh staging, checks the payload and writes the ZIP plus SHA-256 into **`dist/`**. It performs no Git writes or publication. See [the full command guide](../../docs/release-building.md).

For lower-level component development:

From a verified visible foreground PowerShell console in the repository, keep the console open and run:

```powershell
.\scripts\Build.ps1 -Mode Publish
.\scripts\Build-Setup.ps1
.\scripts\Test-Setup.ps1
```

Building setup requires Windows PowerShell, 64-bit Windows, Python 3, the .NET SDK and the Windows .NET Framework 4.x compiler. The build installs WiX 4.0.6 under `artifacts/setup-tools` on first use. Distribute `artifacts/setup/<version>/Tlachihuani-<version>-windows-x64.zip` and its `.sha256`. The archive contains an allowlist of six public files; it never archives the checkout, credentials or application state. The local build is unsigned. Authenticode signing and verification with the publisher's own certificate are release steps.

`tests/integration/check_setup_zip.py <zip> <fresh-app-owned-folder>` checks ZIP CRC, exact contents, extracted file hashes, sizes and version. `check_setup_payload.py` verifies cabinet bytes against published runtimes. Run both from the visible console.

The default test opens the shipping executables visibly, checks their version labels and exercises Review and Cancel.

For an automated test of both login-startup choices, run
`tests\integration\Test-SetupStartup.ps1 -PublishDirectory <fresh-publish-directory>`
from a visible administrator PowerShell console. It uses separate QA service and
product names, installs with startup off and on through real MSI transactions,
checks Start/Desktop/login shortcuts and stopped Manual services, then removes
each installation through its Windows product registration. It preserves QA
identity state and does not touch the production installation or downloads.

* **Isolated SCM test on a developer workstation.** Run `.\scripts\Test-Setup.ps1 -Isolated` in an elevated, verified foreground PowerShell console. It builds a separately named QA package with inert test services, independent product and service IDs, paths and shortcuts. The real Windows Installer engine installs and removes that package twice. The test checks startup policy, virtual accounts, ARP fields, application discovery values and shortcuts. It opens Programs and Features for a separate visual row check, then runs the registered MSI uninstall command with services still running. It verifies removal and retained identity before reinstalling. Its protected QA state remains for inspection.
* **Full product acceptance in a disposable guest.** Run `.\scripts\Test-Setup.ps1 -WindowsSandbox` in a verified foreground console with Windows Sandbox enabled. The guest receives read-only mappings of the bundle and harness and a dedicated writable results folder. Keep the guest visible. The test installs the shipping binaries, starts both services, checks the Jobs API, removes the software and reinstalls it with the retained identity. Results are under `artifacts/verification` in a separate directory for each run.

A successful workstation review or isolated SCM test does not certify production Jobs startup. Use the guest test or a clean Windows QA machine for that release gate.

## Native Windows registration

Windows Installer owns exactly one x64 per-machine entry at `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\{ProductCode}`. It supplies DisplayName, DisplayVersion, Publisher, a cached XT product icon, EstimatedSize and the native `/x` UninstallString. Setup adds InstallLocation, HelpLink, URLInfoAbout and contact information through MSI properties. Modify and Repair are disabled; Uninstall remains available. The setup does not overwrite the system-owned uninstall command or create a duplicate entry.

`HKLM\Software\XAIHT\Tlachihuani` contains InstallLocation, Version, OperatorSID and TrayAtLogin. Those values and setup-owned shortcut markers are MSI components and disappear on removal. Protected ProgramData identities/history are separate and preserved. Start provides XT (with `--show`), the setup guide and native Uninstall. The public Desktop always provides XT with `--show`. Common Startup opens XT only when setup receives `TLTRAYSTARTUP=1`; silent MSI installation defaults to `0`. No setup or login action starts a service.

The installed directory includes the matching Uninstaller.exe and offline guide. Native Control Panel removal uses cached MSI metadata and works even if the original ZIP has been deleted. Windows Installer stops the services and manages files in use; close XT before removing for an orderly shutdown. A restart may be required if a file remains locked.

References: [Windows uninstall registration](https://learn.microsoft.com/en-us/windows/win32/msi/uninstall-registry-key), [native uninstall command](https://learn.microsoft.com/en-us/windows/win32/msi/arpnomodify), [self-contained .NET deployment](https://learn.microsoft.com/en-us/dotnet/core/deploying/).
