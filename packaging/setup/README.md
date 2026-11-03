# Windows setup

The two x64 Windows wizards use Tlamatini's dark setup palette, Segoe UI and the original XT icon. Their title and version label use the compiled assembly version sourced from the project's `Directory.Build.props`. Installer.exe contains a compressed Windows Installer package. Uninstaller.exe targets the corresponding registered product. Neither needs the source tree at runtime.

## Install and operate

Use a Windows x64 machine with the standard x64 .NET 10 Windows Desktop and ASP.NET Core shared runtimes. Sign in as the intended operator. Open **Installer.exe**, choose **Review**, confirm the operator, destination and version, and select **Install**. Approve UAC. If a different administrator supplies credentials, the operator shown in the original review remains the delegated operator.

Wait for **Installation complete**, then choose **Finish**. Start **Tlachihuani XT** from Start and use **Start Services**. The per-machine Startup shortcut displays the tray at sign-in. Windows enforces service permissions separately. The two services run under their own virtual accounts and use Manual startup.

## Remove and reinstall

Stop both services from XT. Exit the tray in every active Windows session. Start the version-matched **Uninstaller.exe**, choose **Review**, then **Uninstall**. Review can be cancelled before applying changes. During Apply, leave the wizard open. The Finish page reports Windows Installer's result and any required reboot.

Windows Installer removes registered services, its own shortcuts and packaged files. Downloads, application-generated exports, job state and account manifests are retained. Reinstall as the original operator. Windows Installed apps also provides removal if the standalone uninstaller is lost. A different-version installation or a script-managed deployment must be maintained using the tools for that installation. An in-place upgrade is not offered by these wizards.

### Moving from 0.1.0 to 0.2.0

Keep the uninstaller that came with 0.1.0. Stop Services, exit XT, remove the old wizard installation and run the 0.2.0 installer as the same operator. Its build output is `artifacts/setup/0.2.0/windows-x64/`.

For a legacy PowerShell installation, use its [unregister scripts](../windows/README.md) first. Disable its per-user XT startup entry. Preserve the legacy program directory and both ProgramData directories under separate backup names before a fresh wizard install. A journal in a renamed legacy folder is a backup, not an imported queue. Leave it intact.

## Failures and recovery

Each wizard transaction writes a unique verbose log under `%SystemRoot%\Logs\Tlachihuani-<id>.log`. The result page gives its path. Cancelling UAC before the transaction starts produces no MSI log. Windows Installer rolls back transactional changes on failure. Identity and job data are retained separately. Never delete a job journal to retry setup.

If Review reports an existing service, unexpected image, different operator, or unmanaged state, preserve it and investigate its original installation. If Windows reports another installation in progress, finish it and retry. Stop Services and exit XT before removal. Reboot when Windows reports pending file replacement or removal.

## Reproduce a build

From a verified visible foreground PowerShell console in the repository, keep the console open and run:

```powershell
.\scripts\Build.ps1 -Mode Publish
.\scripts\Build-Setup.ps1
.\scripts\Test-Setup.ps1
```

Building setup requires Windows PowerShell, 64-bit Windows, Python 3, the .NET SDK and the Windows .NET Framework 4.x compiler. The build installs WiX 4.0.6 under `artifacts/setup-tools` on first use. Distribute the matching executables from `artifacts/setup/<version>/windows-x64/`. The local build is unsigned. Authenticode signing and verification with the publisher's own certificate are release steps.

The default test opens the shipping executables visibly, checks their version labels and exercises Review and Cancel.

* **Isolated SCM test on a developer workstation.** Run `.\scripts\Test-Setup.ps1 -Isolated` in an elevated, verified foreground PowerShell console. It builds a separately named QA package with inert test services, independent product and service IDs, paths and shortcuts. The real Windows Installer engine installs and removes that package twice. The test checks startup policy, virtual accounts and retained identity. Its protected QA state remains for inspection.
* **Full product acceptance in a disposable guest.** Run `.\scripts\Test-Setup.ps1 -WindowsSandbox` in a verified foreground console with Windows Sandbox enabled. The guest receives read-only mappings of the bundle, harness and .NET runtimes and a dedicated writable results folder. Keep the guest visible. The test installs the shipping binaries, starts both services, checks the Jobs API, removes the software and reinstalls it with the retained identity. Results are under `artifacts/verification` in a separate directory for each run.

A successful workstation review or isolated SCM test does not certify production Jobs startup. Use the guest test or a clean Windows QA machine for that release gate.
