param([switch]$WindowsSandbox,[switch]$Isolated)
$ErrorActionPreference='Stop'
function Get-SetupDigest([string]$Path){
 $hash=[Security.Cryptography.SHA256]::Create()
 $stream=[IO.File]::OpenRead($Path)
 try{[BitConverter]::ToString($hash.ComputeHash($stream))}finally{$stream.Dispose();$hash.Dispose()}
}
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$root=Split-Path $PSScriptRoot
$version=([xml](Get-Content -LiteralPath "$root\Directory.Build.props" -Raw)).Project.PropertyGroup.Version
$bundle=Join-Path $root "artifacts\setup\$version\windows-x64"
if(!(Test-Path "$bundle\Installer.exe") -or !(Test-Path "$bundle\Uninstaller.exe")){throw 'Build the setup package first.'}
$work=Join-Path $root ('artifacts\verification\setup-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($work)
$env:TEMP=$env:TMP=$work
if($Isolated){
 if($WindowsSandbox){throw 'Choose one test target.'}
 if(!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Use an elevated foreground console for the isolated SCM test.'}
 Push-Location $root
 try{
   python -B packaging/setup/build.py --isolated-acceptance
   if($LASTEXITCODE){throw 'Isolated package build failed'}
   $base=Join-Path $root 'artifacts\verification\setup-package-qa'
   $gen=Get-Content -LiteralPath "$base\current.txt" -Raw
   if($gen -notmatch '^[a-f0-9]{12}$'){throw 'Unexpected QA generation'}
   & "$root\tests\desktop\SetupWizard.ps1" -Bundle (Join-Path $base $gen) -Isolated -Report "$work\isolated.log"
 }finally{Pop-Location}
 return
}
if(!$WindowsSandbox){
 & "$root\tests\desktop\SetupWizard.ps1" -Bundle $bundle -Report "$work\host.log"
 return
}
$tools=Join-Path $work 'tools'
$guestBundle=Join-Path $work 'bundle'
[void][IO.Directory]::CreateDirectory($guestBundle)
foreach($name in 'Installer.exe','Uninstaller.exe'){
    Copy-Item -LiteralPath (Join-Path $bundle $name) -Destination $guestBundle
    if((Get-SetupDigest (Join-Path $bundle $name)) -ne (Get-SetupDigest (Join-Path $guestBundle $name))){throw "Sandbox bundle copy differs: $name"}
}
$results=Join-Path $work 'results'
[void][IO.Directory]::CreateDirectory($tools)
[void][IO.Directory]::CreateDirectory($results)
Copy-Item -LiteralPath "$PSScriptRoot\Assert-Visible.ps1","$root\tests\desktop\SetupWizard.ps1" -Destination $tools
@'
$ErrorActionPreference='Stop'
[void][IO.Directory]::CreateDirectory('C:\SetupScratch')
$env:TEMP=$env:TMP='C:\SetupScratch'
[IO.File]::WriteAllText('C:\SetupResults\guest-started','Windows Sandbox logon command started')
. C:\SetupTools\Assert-Visible.ps1
try{
 Assert-VisibleDevelopmentConsole
 & C:\SetupTools\SetupWizard.ps1 -Bundle C:\SetupBundle -Sandbox -Report C:\SetupResults\test.log
 [IO.File]::WriteAllText('C:\SetupResults\result','PASS')
}catch{[IO.File]::WriteAllText('C:\SetupResults\result',$_.ToString());throw}
'@ | Set-Content -Encoding UTF8 "$tools\test.ps1"
function Map-Folder($hostPath,$guestPath,$readOnly){
 "<MappedFolder><HostFolder>$([Security.SecurityElement]::Escape($hostPath))</HostFolder><SandboxFolder>$guestPath</SandboxFolder><ReadOnly>$readOnly</ReadOnly></MappedFolder>"
}
$maps=@((Map-Folder $guestBundle 'C:\SetupBundle' 'true'),(Map-Folder $tools 'C:\SetupTools' 'true'),(Map-Folder $results 'C:\SetupResults' 'false')) -join ''
$config="<Configuration><MappedFolders>$maps</MappedFolders><LogonCommand><Command>C:\Windows\System32\conhost.exe powershell.exe -NoProfile -NoExit -ExecutionPolicy RemoteSigned -File C:\SetupTools\test.ps1</Command></LogonCommand></Configuration>"
$target="$work\setup.wsb"
$config|Set-Content -LiteralPath $target -Encoding UTF8
Write-Host "Visible Windows Sandbox acceptance: $results"
Start-Process -FilePath $target -WindowStyle Normal
$end=(Get-Date).AddMinutes(6)
while(!(Test-Path "$results\result") -and (Get-Date) -lt $end){Start-Sleep -Seconds 2}
if(!(Test-Path "$results\result")){throw "Sandbox did not return a test result: $results"}
if((Get-Content "$results\result" -Raw) -ne 'PASS'){throw (Get-Content "$results\result" -Raw)}
Write-Host 'Windows Sandbox setup acceptance passed. The sandbox remains open for inspection.'
