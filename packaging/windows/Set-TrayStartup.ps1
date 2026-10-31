param([switch]$Disable)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$trayPath = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani\Tray\Tlachihuani.Tray.exe'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$value = '"' + $trayPath + '"'
$existing = (Get-ItemProperty -LiteralPath $runKey -Name 'XAIHT.Tlachihuani' -ErrorAction SilentlyContinue).'XAIHT.Tlachihuani'
if ($existing -and $existing -ne $value) { throw 'An unrelated startup value uses this name. Nothing changed.' }
if ($Disable) {
    if ($existing) { Remove-ItemProperty -LiteralPath $runKey -Name 'XAIHT.Tlachihuani' }
    Write-Host 'Tlachihuani tray startup disabled for this Windows user.'
} else {
    if (-not (Test-Path -LiteralPath $trayPath -PathType Leaf)) { throw 'Install the published tray first.' }
    if (-not (Test-Path -LiteralPath $runKey)) { [void](New-Item -Path $runKey -Force) }
    Set-ItemProperty -LiteralPath $runKey -Name 'XAIHT.Tlachihuani' -Value $value -Type String
    Write-Host 'Tlachihuani tray startup enabled for this Windows user. It will not implicitly start the service.'
}
