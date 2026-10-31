# Upgrade the registered Jobs service without changing its operator or durable state.
param([switch]$UpdateTray)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
. "$PSScriptRoot\JobsPayload.ps1"
Assert-VisibleDevelopmentConsole
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Use an elevated foreground PowerShell console.'
}
$program = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani'
$jobs = Join-Path $program 'Jobs'
$tray = Join-Path $program 'Tray'
$data = Join-Path $env:ProgramData 'XAIHT\Tlachihuani.Jobs'
$package = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\artifacts\publish'))
$expected = '"' + (Join-Path $jobs 'Tlachihuani.Jobs.exe') + '"'
function Get-VerifiedRegistration {
    $service = Get-CimInstance Win32_Service -Filter "Name='Tlachihuani.Jobs'"
    if (!$service -or $service.PathName -ne $expected -or $service.StartName -ne 'NT SERVICE\Tlachihuani.Jobs') {
        throw 'Installed Jobs identity mismatch.'
    }
    return $service
}
foreach ($path in @($program,$jobs,$tray,$data)) { Assert-PlainPath $path }
$manifest = Get-Content -Raw -LiteralPath (Join-Path $data 'installation.json') | ConvertFrom-Json
if ([guid]$manifest.installation_id -eq [guid]::Empty) { throw 'Invalid Jobs identity.' }
$null = [Security.Principal.SecurityIdentifier]::new($manifest.operator_sid)
$initial = Get-VerifiedRegistration
if ($initial.State -notin @('Running','Stopped')) { throw 'Wait for Jobs to finish changing state.' }
if ($UpdateTray -and (Get-Process -Name Tlachihuani.Tray -ErrorAction SilentlyContinue | Where-Object Path -eq (Join-Path $tray 'Tlachihuani.Tray.exe'))) {
    throw 'Exit the installed XT tray before upgrading it.'
}
foreach ($leaf in @('Jobs\Tlachihuani.Jobs.exe','Jobs\runtime\python.exe','Jobs\worker\worker.py','Jobs\wwwroot\index.html','Tray\Tlachihuani.Tray.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $package $leaf) -PathType Leaf)) { throw "Missing published $leaf." }
}
# All paths below are new direct siblings under the verified Program Files directory.
$generation = [guid]::NewGuid().ToString('N')
$parts = @('Jobs')
if ($UpdateTray) { $parts += 'Tray' }
foreach ($part in $parts) {
    $stage = Join-Path $program "$part.new.$generation"
    if ($part -eq 'Jobs') { Copy-JobsPayload $package $stage }
    else { Copy-Item -LiteralPath (Join-Path $package $part) -Destination $stage -Recurse }
}
$swapped = @()
try {
    if ((Get-VerifiedRegistration).State -eq 'Running') { Stop-Service Tlachihuani.Jobs }
    if ((Get-VerifiedRegistration).State -ne 'Stopped') { throw 'Jobs is still running.' }
    foreach ($part in $parts) {
        $target = Join-Path $program $part
        $previous = Join-Path $program "$part.previous.$generation"
        [IO.Directory]::Move($target,$previous)
        $swapped += $part
        [IO.Directory]::Move((Join-Path $program "$part.new.$generation"),$target)
    }
    if ($initial.State -eq 'Running') {
        Start-Service Tlachihuani.Jobs
        $image = Join-Path $jobs 'Tlachihuani.Jobs.exe'
        $ready = $false
        for ($attempt=0; $attempt -lt 12; $attempt++) {
            if ((Get-VerifiedRegistration).State -ne 'Running') { break }
            $reply = '{"op":"status"}' | & $image --control
            if ($LASTEXITCODE -eq 0 -and ($reply | ConvertFrom-Json).provider -eq 'torrenter') { $ready=$true; break }
            Start-Sleep -Seconds 1
        }
        if (!$ready) { throw 'Updated host did not answer its authenticated status check.' }
    }
    Write-Host "Jobs updated. Previous program files retained under generation $generation."
} catch {
    if ((Get-VerifiedRegistration).State -eq 'Running') { Stop-Service Tlachihuani.Jobs }
    [array]::Reverse($swapped)
    foreach ($part in $swapped) {
        $target = Join-Path $program $part
        if ([IO.Directory]::Exists($target)) { [IO.Directory]::Move($target,(Join-Path $program "$part.failed.$generation")) }
        [IO.Directory]::Move((Join-Path $program "$part.previous.$generation"),$target)
    }
    if ($initial.State -eq 'Running') { Start-Service Tlachihuani.Jobs }
    throw
}
