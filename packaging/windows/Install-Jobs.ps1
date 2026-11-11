# Install the independently bootable Jobs service. Never change the original SCM registration.
param([Parameter(Mandatory=$true)][string]$OperatorAccount,[switch]$UpdateTray)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$user=[Security.Principal.WindowsIdentity]::GetCurrent()
if (!([Security.Principal.WindowsPrincipal]$user).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Use an elevated visible PowerShell console.' }
$sid=([Security.Principal.NTAccount]::new($OperatorAccount)).Translate([Security.Principal.SecurityIdentifier]).Value
$package=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\artifacts\publish'))
$program=Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani'
$data=Join-Path $env:ProgramData 'XAIHT\Tlachihuani.Jobs'
$jobs=Join-Path $program 'Jobs'
$image=Join-Path $jobs 'Tlachihuani.Jobs.exe'
$tray=Join-Path $program 'Tray'
foreach ($leaf in @('Jobs\Tlachihuani.Jobs.exe','Jobs\runtime\python.exe','Jobs\worker\worker.py','Jobs\wwwroot\index.html','Tray\Tlachihuani.Tray.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $package $leaf) -PathType Leaf)) { throw "Missing $leaf. Run scripts\Build.ps1 -Mode Publish first." }
}
. "$PSScriptRoot\JobsPayload.ps1"
Assert-PlainPath $program
Assert-PlainPath $data
Assert-PlainPath $jobs
Assert-PlainPath $tray
if ((Get-Service 'Tlachihuani.Jobs' -ErrorAction SilentlyContinue) -or [IO.Directory]::Exists($jobs) -or [IO.Directory]::Exists($data)) {
    throw "Jobs registration, binaries or state already exist. First install refuses replacement. Preserve the existing state for repair."
}
if ($UpdateTray -and (Get-Process -Name Tlachihuani.Tray -ErrorAction SilentlyContinue | Where-Object Path -eq (Join-Path $tray 'Tlachihuani.Tray.exe'))) {
    throw 'Choose Exit tray in XT, then run the installer again. Existing downloads can continue.'
}
function ProtectFolder([string]$Path,[hashtable]$Rights) {
    $acl=[Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true,$false)
    $map=@{'S-1-5-18'='FullControl';'S-1-5-32-544'='FullControl'}
    foreach($id in $Rights.Keys){ if(!$map.ContainsKey($id)){$map[$id]=$Rights[$id]} }
    foreach($id in $map.Keys) {
        $rule=[Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($id),$map[$id],'ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
$created=$false
try {
    [void][IO.Directory]::CreateDirectory($program)
    Copy-JobsPayload $package $jobs
    [void](New-Service -Name 'Tlachihuani.Jobs' -DisplayName 'Tlachihuani Jobs' -BinaryPathName ('"{0}"' -f $image) -StartupType Manual)
    $created=$true
    & sc.exe config Tlachihuani.Jobs obj= 'NT SERVICE\Tlachihuani.Jobs' start= demand
    if($LASTEXITCODE){throw "Virtual account setup failed: $LASTEXITCODE"}
    & sc.exe sidtype Tlachihuani.Jobs unrestricted
    if($LASTEXITCODE){throw "Service SID setup failed: $LASTEXITCODE"}
    $svc=([Security.Principal.NTAccount]::new('NT SERVICE\Tlachihuani.Jobs')).Translate([Security.Principal.SecurityIdentifier]).Value
    [void][IO.Directory]::CreateDirectory($data)
    ProtectFolder $data @{$sid='ReadAndExecute';$svc='ReadAndExecute'}
    $state=Join-Path $data 'state'
    [void][IO.Directory]::CreateDirectory($state)
    ProtectFolder $state @{$svc='Modify'}
    $downloads=Join-Path $state 'downloads'
    [void][IO.Directory]::CreateDirectory($downloads)
    # Give the native Windows profile access to its own published bytes only.
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$ownerHash=[BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($sid))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    $ownerFiles=Join-Path $downloads $ownerHash
    [void][IO.Directory]::CreateDirectory($ownerFiles)
    ProtectFolder $ownerFiles @{$svc='Modify';$sid='ReadAndExecute'}
    $manifest=@{installation_id=[guid]::NewGuid().ToString();operator_sid=$sid}
    [IO.File]::WriteAllText((Join-Path $data 'installation.json'),($manifest|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    & sc.exe sdset Tlachihuani.Jobs "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;CCLCRPWPLORC;;;$sid)"
    if($LASTEXITCODE){throw "Operator delegation failed: $LASTEXITCODE"}
    if($UpdateTray) {
        $stage=Join-Path $program ('Tray.new.'+[guid]::NewGuid().ToString('N'))
        $backup=Join-Path $program ('Tray.previous.'+[guid]::NewGuid().ToString('N'))
        Copy-Item -LiteralPath (Join-Path $package 'Tray') -Destination $stage -Recurse
        if([IO.Directory]::Exists($tray)){[IO.Directory]::Move($tray,$backup)}
        try{[IO.Directory]::Move($stage,$tray)}
        catch{if([IO.Directory]::Exists($backup) -and ![IO.Directory]::Exists($tray)){[IO.Directory]::Move($backup,$tray)};throw}
    }
    & sc.exe config Tlachihuani.Jobs start= delayed-auto
    if($LASTEXITCODE){throw 'Boot configuration failed.'}
    & sc.exe failure Tlachihuani.Jobs reset= 86400 actions= restart/5000/restart/30000/restart/60000
    if($LASTEXITCODE){throw 'SCM recovery setup failed.'}
    Set-JobsPeerFirewallRule $jobs
    Start-Service Tlachihuani.Jobs
    Write-Host 'Jobs installed. Open XT -> Show panel -> Services -> Open workspace.'
} catch {
    if($created){ & sc.exe config Tlachihuani.Jobs start= disabled }
    try { Remove-JobsPeerFirewallRule } catch { Write-Warning "Firewall rule cleanup failed: $_" }
    throw
}
