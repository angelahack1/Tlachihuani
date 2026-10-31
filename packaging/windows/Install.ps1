# Tlachihuani — Angela López Mendoza · XAIHT
# First-install script. Run explicitly in an elevated, visible foreground console.
param([Parameter(Mandatory = $true)][string]$OperatorAccount)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'An elevated console is required to install the Windows service.' }
$operatorSid = ([Security.Principal.NTAccount]::new($OperatorAccount)).Translate([Security.Principal.SecurityIdentifier]).Value
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$publishRoot = Join-Path $projectRoot 'artifacts\publish'
$installRoot = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani'
$dataRoot = Join-Path $env:ProgramData 'XAIHT\Tlachihuani'
if ((Get-Service -Name 'Tlachihuani' -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath $installRoot) -or (Test-Path -LiteralPath $dataRoot)) { throw 'An existing service or installation directory exists. First-install refuses to overwrite it.' }
foreach ($component in @('Service', 'Control', 'Tray')) {
    if (-not (Test-Path -LiteralPath (Join-Path $publishRoot "$component\Tlachihuani.$component.exe") -PathType Leaf)) { throw "Publish $component before installing." }
}
function Set-ProtectedDirectoryAcl([string]$Path, [string[]]$Readers) {
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($sid), 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    foreach ($sid in $Readers) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($sid), 'ReadAndExecute', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

# New-Service preserves the quoted image path on Windows PowerShell 5.1; do not pass it through native argument re-quoting.
# No service is started until its virtual account and complete ACL/manifest have been configured.
$created = $false
try {
    [void](New-Item -ItemType Directory -Path $installRoot)
    Set-ProtectedDirectoryAcl $installRoot @('S-1-5-32-545')
    foreach ($component in @('Service', 'Control', 'Tray')) { Copy-Item -LiteralPath (Join-Path $publishRoot $component) -Destination $installRoot -Recurse }
    $image = Join-Path $installRoot 'Service\Tlachihuani.Service.exe'
    [void](New-Service -Name 'Tlachihuani' -DisplayName 'Tlachihuani' -BinaryPathName ('"{0}"' -f $image) -StartupType Manual -Description 'XAIHT Tlachihuani lifecycle service; controlled by Tlamatini and the XT tray companion.')
    $created = $true
    & sc.exe config Tlachihuani obj= 'NT SERVICE\Tlachihuani' start= delayed-auto
    if ($LASTEXITCODE -ne 0) { throw "Service account configuration failed: $LASTEXITCODE" }
    & sc.exe sidtype Tlachihuani unrestricted
    if ($LASTEXITCODE -ne 0) { throw "Service SID configuration failed: $LASTEXITCODE" }
    $serviceSid = ([Security.Principal.NTAccount]::new('NT SERVICE\Tlachihuani')).Translate([Security.Principal.SecurityIdentifier]).Value
    [void](New-Item -ItemType Directory -Path $dataRoot)
    Set-ProtectedDirectoryAcl $dataRoot @($serviceSid, $operatorSid)
    $manifest = [ordered]@{ installation_id = [guid]::NewGuid().ToString(); service_path = $image; operator_sid = $operatorSid }
    [IO.File]::WriteAllText((Join-Path $dataRoot 'installation.json'), ($manifest | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    # Query-config, query-status, Start, Stop, interrogate and read-control; no config changes, deletion or DACL writes.
    $serviceAcl = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;CCLCRPWPLORC;;;$operatorSid)"
    & sc.exe sdset Tlachihuani $serviceAcl
    if ($LASTEXITCODE -ne 0) { throw "Service ACL configuration failed: $LASTEXITCODE" }
    # A new service has no failure actions; do not add automatic crash restarts.
    & (Join-Path $installRoot 'Control\Tlachihuani.Control.exe') status
    if ($LASTEXITCODE -ne 0) { throw 'Post-install identity check failed.' }
    Write-Host "Installed at $installRoot. Operator: $OperatorAccount ($operatorSid). Service is stopped; use Control.exe start when ready." -ForegroundColor Green
    Write-Host 'Tray logon registration is a separate per-user action. No tray or browser was started.'
} catch {
    # Never leave a partially configured new service eligible to start at the next boot.
    if ($created) { & sc.exe config Tlachihuani start= disabled }
    Write-Warning 'Installation did not finish. Files are preserved for inspection; any newly created service was disabled. No recursive cleanup or overwrite was attempted.'
    throw
}
