# Removes only the fixed, verified SCM registration. Keeps binaries and data for manual inspection/removal.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An elevated console is required.' }
$installRoot = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani'
$expected = '"' + (Join-Path $installRoot 'Service\Tlachihuani.Service.exe') + '"'
$service = Get-CimInstance Win32_Service -Filter "Name='Tlachihuani'"
if (-not $service) { Write-Host 'Tlachihuani is already unregistered.'; return }
if ($service.PathName -ne $expected) { throw 'Service ownership check failed. Nothing removed.' }
$control = Join-Path $installRoot 'Control\Tlachihuani.Control.exe'
& $control stop
if ($LASTEXITCODE -ne 0) { throw 'Graceful stop failed; service registration was preserved.' }
$service = Get-CimInstance Win32_Service -Filter "Name='Tlachihuani'"
if ($service.State -ne 'Stopped' -or $service.PathName -ne $expected) { throw 'Service state or identity changed. Nothing removed.' }
& sc.exe delete Tlachihuani
if ($LASTEXITCODE -ne 0) { throw "SCM deletion failed: $LASTEXITCODE" }
Write-Host 'SCM registration removed. Binaries, installation manifest and per-user tray settings remain. Exit any tray instances separately.'
