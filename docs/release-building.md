# Build the Windows release ZIP

Open a visible Command Prompt in the Tlachihuani repository root and run:

```bat
Build-Release.cmd
```

Keep the console visible until it reports **READY**. From PowerShell use
`.\Build-Release.cmd`. Administrator permission is not needed to build.

## Build-machine prerequisites

Use Windows x64 with Git, Python 3.10 or later on PATH, the .NET SDK pinned in
`global.json`, and the Windows .NET Framework 4.x compiler. Dependency restore,
the pinned WiX tool and private CPython/libtorrent downloads need network access
on their first use. Caches and scratch space stay inside `artifacts`; client
machines need none of these development tools.

## Version and source

Each invocation reads local Git tags again. The highest numeric stable tag in
`vX.Y.Z` or `X.Y.Z` form supplies the version; creation dates and lexical sorting
do not determine it. Prerelease tags are ignored. There must be a stable tag,
its commit must be an ancestor of HEAD, and its version must fit MSI's
255.255.65535 limits. Keep your local tags current before building; the command
does not fetch, create or move them.

The current working tree supplies the code, including local edits. The builder
updates `Directory.Build.props` and internal Tlachihuani project dependency
ranges in lockfiles to that version. External package pins and hashes stay
unchanged. No Git commit, push or upload is performed. A local `source.json`
records the tag, checkout commit and whether local edits were present.

## What the command does

1. Acquires a build lock and creates fresh staging under `artifacts/release-builds`.
2. Tests numeric tag selection and version stamping, then stamps the product.
3. Restores locked dependencies, builds and runs the lifecycle checks.
4. Publishes Service, Control, Tray and Jobs for Windows x64 with private runtimes.
5. Adds hash-pinned CPython and libtorrent, regenerates setup and the offline guide.
6. Checks every MSI cabinet file against the published bytes, the startup-choice
   condition, shortcuts, service startup types and Windows registration metadata.
7. Checks the six-file ZIP allowlist, CRC, manifest, file sizes and SHA-256 hashes.
8. Copies the verified ZIP and checksum into `dist`. Failed builds leave previous
   release files intact. Each successful rebuild replaces the same version's ZIP;
   other versions remain. Logs and staging are retained for inspection.

Upload `dist/Tlachihuani-<version>-windows-x64.zip` and its `.zip.sha256` to the
GitHub Release you create. Do not upload the checkout or `artifacts` directory.

## New-user experience

The user extracts the ZIP and opens Installer.exe from their normal Windows
session. Setup asks whether XT should appear at Windows sign-in. That optional
common Startup shortcut applies to all Windows users on the PC. Start menu and
Desktop shortcuts are always installed. The review page shows the exact choice.
UAC is requested only for installation/removal; the original Windows operator
remains the delegated service operator when another administrator approves it.

After successful setup, the original unelevated wizard launches XT once. It is
gray, with both services stopped. If the entire wizard was run elevated, the
result directs the user to the normal Desktop shortcut instead of launching an
elevated tray. Login startup never starts services. Both services are Manual and
stay stopped after reboot until the operator chooses **Start Services**.
Signing out/in while services are already running does not stop them; use
**Stop Services** for that. **Exit tray** only closes XT.

Windows Installed apps and Control Panel offer native removal. Uninstall removes
package-owned shortcuts, registry entries, services and binaries, while keeping
downloads, protected identities and job history. See the [setup guide](../packaging/setup/README.md).

## Release acceptance

Package verification is automatic. On a visible clean Windows QA machine, also
test installation with startup checked and unchecked, ordinary-user XT launch,
Desktop/Start reopening, a real reboot, service start/stop, and Control Panel
removal. The [visible setup harness](../scripts/Test-Setup.ps1) supports isolated
SCM tests and Windows Sandbox. An isolated fixture does not certify the real
Torrenter engine. The package is unsigned until the publisher supplies a signing
certificate; checksums are integrity checks, not publisher authentication.
