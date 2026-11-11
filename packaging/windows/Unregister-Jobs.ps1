# Remove only this SCM registration. Installed content and the job journal are retained.
$ErrorActionPreference='Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
. "$PSScriptRoot\JobsPayload.ps1"
Assert-VisibleDevelopmentConsole
$name='Tlachihuani.Jobs'
$expected='"'+(Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani\Jobs\Tlachihuani.Jobs.exe')+'"'
function Assert-Registration {
    $entry=Get-CimInstance Win32_Service -Filter "Name='Tlachihuani.Jobs'"
    if(!$entry){throw 'Jobs is not registered.'}
    if($entry.PathName -ne $expected -or $entry.StartName -ne 'NT SERVICE\Tlachihuani.Jobs'){throw 'Jobs registration identity mismatch.'}
    return $entry
}
[void](Assert-Registration)
Stop-Service -Name $name
if((Assert-Registration).State -ne 'Stopped'){throw 'Jobs is still active.'}
& sc.exe delete $name
if($LASTEXITCODE){throw "SCM deletion failed: $LASTEXITCODE"}
Remove-JobsPeerFirewallRule
Write-Host 'Jobs registration and its peer firewall rules removed. State, credentials and downloaded files were retained.'
