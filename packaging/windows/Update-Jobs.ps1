# Upgrade the registered Jobs service without changing its operator or durable state.
param([switch]$UpdateTray, [switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
. "$PSScriptRoot\JobsPayload.ps1"
Assert-VisibleDevelopmentConsole
if ($VerifyOnly -and $UpdateTray) { throw 'VerifyOnly checks the installed Jobs payload; omit UpdateTray.' }
if (!$VerifyOnly -and !([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
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
$required = @('Tlachihuani.Jobs.exe','Tlachihuani.Jobs.dll','Tlachihuani.Windows.dll',
    'runtime\python.exe','worker\worker.py','worker\api.py','worker\engine.py',
    'worker\storage.py','worker\delivery.py','wwwroot\index.html')
function Get-PayloadDigest([string]$file) {
    $stream = [IO.File]::OpenRead($file)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
$digests = @{}
foreach ($leaf in $required) {
    $file = Join-Path (Join-Path $package 'Jobs') $leaf
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing published Jobs\$leaf." }
    $digests[$leaf] = Get-PayloadDigest $file
}
if ($UpdateTray -and !(Test-Path -LiteralPath (Join-Path $package 'Tray\Tlachihuani.Tray.exe') -PathType Leaf)) {
    throw 'Missing published Tray\Tlachihuani.Tray.exe.'
}
function Assert-InstalledJobsPayload {
    foreach ($leaf in $required) {
        $targetFile = Join-Path $jobs $leaf
        if (!(Test-Path -LiteralPath $targetFile -PathType Leaf) -or
            (Get-PayloadDigest $targetFile) -ne $digests[$leaf]) {
            throw "Verification failed: $targetFile is missing or differs from the published file."
        }
    }
}
if ($VerifyOnly) {
    Assert-InstalledJobsPayload
    Write-Host ("Verified installed Jobs at " + $jobs + "; Downloads worker SHA-256: " + $digests['worker\delivery.py'])
    return
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
    # A status response alone can also come from an older healthy build. Verify
    # the registered program directory inside the rollback boundary while Jobs
    # is stopped. Do not print a success receipt for a stale or partial payload.
    Assert-InstalledJobsPayload
    # Installations made before peers could connect inbound have no rule yet.
    Set-JobsPeerFirewallRule $jobs
    if ($initial.State -eq 'Running') {
        Start-Service Tlachihuani.Jobs
        $image = Join-Path $jobs 'Tlachihuani.Jobs.exe'
        $ready = $false
        for ($attempt=0; $attempt -lt 12; $attempt++) {
            if ((Get-VerifiedRegistration).State -ne 'Running') { break }
            # Jobs is a Windows-subsystem executable so older windowless callers
            # cannot flash a console. A downstream command makes PowerShell 5.1
            # redirect stdout and wait for the native process before checking it.
            $reply = '{"op":"status"}' | & $image --control | Out-String
            if ($LASTEXITCODE -eq 0 -and ($reply | ConvertFrom-Json).provider -eq 'torrenter') { $ready=$true; break }
            Start-Sleep -Seconds 1
        }
        if (!$ready) { throw 'Updated host did not answer its authenticated status check.' }
    }
    Write-Host "Jobs updated and verified in $jobs. Update ID: $generation"
    Write-Host ("Downloads worker SHA-256: " + $digests['worker\delivery.py'])
    Write-Host "Previous program files retained under generation $generation."
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
