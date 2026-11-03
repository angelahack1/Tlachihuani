<!-- Tlachihuani — Created for Angela López Mendoza · XAIHT · @angelahack1 -->

<p align="center">
  <img src="assets/branding/readme-hero.svg" alt="Tlachihuani connects the XT tray, Windows services, Torrenter and the local REST API." width="1280" />
</p>

<h1 align="center">Tlachihuani</h1>

<p align="center">
  <b>Start your Windows services from the XT tray. Follow your downloads in Tlamatini.</b><br />
  Tlachihuani runs background jobs independently of your browser and chat windows.
  Torrenter is its first provider.
</p>

<p align="center">
  <a href="#installation"><img src="assets/branding/badge-windows.svg" alt="Windows x64 installation" /></a>
  <a href="#build-from-source"><img src="assets/branding/badge-dotnet.svg" alt="Build with .NET 10" /></a>
  <a href="docs/torrenter.md"><img src="assets/branding/badge-rest.svg" alt="REST API v1 guide" /></a>
</p>

<p align="center">
  <a href="#first-download">First download</a> ·
  <a href="#tray-controls">Tray controls</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#documentation">Documentation</a>
</p>

> [!TIP]
> **Already installed?** Right-click **XT → Start Services**. When the icon turns color, open **Panels → Torrenter Workspace** in Tlamatini to see the downloads for your signed-in account.

## First download

1. **Open your workspace.** Use the Tlamatini menu above, or choose **Open workspace** in XT. If both Tlamatini editions are available, choose the account you want to use.
2. **Pick what to download.** Select **Add torrent**, paste a magnet or open a `.torrent` file, then choose **Inspect metadata**. Jobs can look up four magnets at once. Additional magnets wait in order, and their peer timeout starts when a slot opens.
3. **Start the transfer.** Choose the files you want and select **Download selected files**. You can close the browser or Tlamatini while the Jobs service continues downloading.
4. **Find your files.** Select the completed transfer and open **Verified output** for its saved directory and each file’s SHA-256. The usual destination is **Downloads → Torrenter**. If Windows refuses delivery there, check Verified output for the application’s `content_generated` fallback.

## Tray controls

| What you want to do | Where to go | What happens |
| :--- | :--- | :--- |
| Bring Torrenter online | **XT → Start Services** | The icon turns color when the services and API are ready. |
| Check a slow download | **XT → Show panel → Services…** | Inspect Jobs, engine and web readiness. Open the workspace for the transfer’s progress, trackers and peers. |
| Stop background work | **XT → Stop Services** | The services and their workers stop. The gray XT icon stays available to start them again. |
| Close only the tray | **XT → Exit tray** | The icon disappears. If a service is running, the menu reads **Exit tray (service keeps running)**. |

> [!NOTE]
> **Remove record** keeps the downloaded files. To delete the files themselves, choose **Erase files…**, review the exact files and approve the operation in XT.

## Installation

Use **Windows x64** with the **.NET 10 Desktop** and **ASP.NET Core 10** shared runtimes. Windows runs two independent services. `Tlachihuani` reports lifecycle and health. `Tlachihuani.Jobs` hosts Torrenter. The XT tray runs in the signed-in Windows session.

| Step | Guide |
| :--- | :--- |
| 1 · Install the primary service, controller and XT tray for your Windows operator | [Windows packaging and permissions](packaging/windows/README.md) |
| 2 · Register Jobs on first installation, or update an existing installation | [Torrenter installation and update](docs/torrenter.md#windows-installation) |
| 3 · Show XT at sign-in | Run `packaging\windows\Set-TrayStartup.ps1` as the intended Windows user. This registers the tray for the next sign-in independently of service startup. |

### Build from source

<details>
<summary><b>Show PowerShell commands and runtime requirements</b></summary>

Use the SDK pinned in [global.json](global.json). Open a visible foreground PowerShell console and keep it open for the results. From the source checkout on this machine, run:

```powershell
Set-Location -LiteralPath 'C:\Development\XAIHT\Tlachihuani'
.\scripts\Build.ps1 -Mode Check
.\scripts\Build.ps1 -Mode Publish
.\artifacts\publish\Control\Tlachihuani.Control.exe status
.\artifacts\publish\Tray\Tlachihuani.Tray.exe --show
```

**Check** exercises the boundaries and a temporary console service host. **Publish** produces the Service, Control, Tray and Jobs components under `artifacts/publish/`. Windows service registration is a separate installation step.

</details>

## Documentation

| For operators | For developers |
| :--- | :--- |
| [Torrenter workspace and REST API](docs/torrenter.md) | [Architecture and process responsibilities](docs/architecture.md) |
| [Service lifecycle](docs/lifecycle.md) | [Controller commands and JSON replies](docs/control-protocol.md) |
| [Panel and tray](docs/panel-and-tray.md) | [Tlamatini integration design](docs/tlamatini-integration.md) |
| [Windows privileges and local IPC](docs/security-and-installation.md) | [Implementation status and verification evidence](docs/implementation-status.md) |

<details>
<summary><b>Under the hood · API, repositories and contributor references</b></summary>

The browser workspace and Tlamatini’s wrapped Torrenter agent use the same account-scoped Jobs API. With Jobs running, [open local API discovery](http://127.0.0.1:12064/api/v1). The native controller handles `status`, `events [--cursor N]`, `start`, `stop` and `restart` for the primary service. The separate **Panels → Tlachihuani** lifecycle panel is a design target. **Panels → Torrenter Workspace** is the implemented download interface.

| Reference | Location |
|---|---|
| This independent project | `C:\Development\XAIHT\Tlachihuani` |
| Tlachihuani on GitHub | [github.com/angelahack1/Tlachihuani](https://github.com/angelahack1/Tlachihuani) |
| Tlachihuani Git origin | `https://github.com/angelahack1/Tlachihuani.git` |
| Tlamatini source checkout | `C:\Development\XAIHT\Tlamatini` |
| Tlamatini Django application | `C:\Development\XAIHT\Tlamatini\Tlamatini` |
| Tlamatini on GitHub | [github.com/XAIHT/Tlamatini](https://github.com/XAIHT/Tlamatini) |
| Verified origin | `https://github.com/XAIHT/Tlamatini.git` |
| Design reference revision | `c18d50815cfe8b1681f805fd4e76c66fbaeabaf6` (`v1.78.0-4-gc18d5081`) |

For the next development session, read [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) and the [session handoff](NEXT_SESSION.md). The [roadmap](docs/implementation-plan.md), [verification plan](docs/verification-plan.md), [project tree](docs/project-tree.md), [source review](docs/source-review.md) and [skill inventory](docs/skill-inventory.md) cover the rest of the checkout. Changes to either repository and publication require their own authorization.

</details>

<p align="center">
  <a href="assets/branding/README.md"><img src="assets/branding/xt-preview.png" alt="Original XAIHT XT emblem" width="64" height="64" /></a><br />
  <b>Created by Angela López Mendoza · XAIHT</b><br />
  <a href="https://github.com/angelahack1/Tlachihuani">Tlachihuani</a> · <a href="https://github.com/XAIHT/Tlamatini">Tlamatini</a>
</p>
