param([Parameter(Mandatory)][string]$Bundle,[switch]$Sandbox,[switch]$Isolated,[string]$Report)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
if(!('TlachihuaniWizardTestInputV2' -as [type])){Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
public static class TlachihuaniWizardTestInputV2 {
 [DllImport("msi.dll",CharSet=CharSet.Unicode)] public static extern uint MsiGetProductInfo(string product,string property,System.Text.StringBuilder value,ref uint size);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern void keybd_event(byte k,byte s,uint f,UIntPtr e);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint x,uint y,uint data,UIntPtr extra);
}
'@
}
function Say($s){Write-Host $s;if($Report){[IO.File]::AppendAllText($Report,$s+[Environment]::NewLine)}}
function Wait-For($description,[scriptblock]$predicate,[int]$seconds=35){
 $end=(Get-Date).AddSeconds($seconds)
 do{$value=& $predicate;if($value){return $value};Start-Sleep -Milliseconds 200}while((Get-Date) -lt $end)
 throw "Timed out waiting for $description"
}
function Button($name){
 $c=[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty,$name)
 $win.FindFirst([Windows.Automation.TreeScope]::Descendants,$c)
}
function Open-Wizard($name){
 $image=Join-Path $Bundle "$name.exe"
 $script:proc=Start-Process -FilePath $image -WindowStyle Normal -PassThru
 $hw=Wait-For 'setup window' {$proc.Refresh();if($proc.MainWindowHandle -ne [IntPtr]::Zero){$proc.MainWindowHandle}}
 [TlachihuaniWizardTestInputV2]::keybd_event(18,0,0,[UIntPtr]::Zero);[TlachihuaniWizardTestInputV2]::keybd_event(18,0,2,[UIntPtr]::Zero)
 [void][TlachihuaniWizardTestInputV2]::SetForegroundWindow($hw)
 [void](Wait-For 'visible foreground wizard' {([TlachihuaniWizardTestInputV2]::IsWindowVisible($hw)) -and !([TlachihuaniWizardTestInputV2]::IsIconic($hw)) -and ([TlachihuaniWizardTestInputV2]::GetForegroundWindow() -eq $hw)})
 $script:win=[Windows.Automation.AutomationElement]::FromHandle($hw)
 $ver=[Diagnostics.FileVersionInfo]::GetVersionInfo($image)
 $version="$($ver.FileMajorPart).$($ver.FileMinorPart).$($ver.FileBuildPart)"
 if(!$win.Current.Name.Contains($version)){throw 'Window version does not match executable'}
 Say "PASS visible $name $version"
 Start-Sleep -Milliseconds 850
}
function Click($name){
 $b=Wait-For $name {Button $name}
 if(!$b.Current.IsEnabled -or $b.Current.IsOffscreen){throw "$name is unavailable"}
 $hw=$proc.MainWindowHandle
 [TlachihuaniWizardTestInputV2]::keybd_event(18,0,0,[UIntPtr]::Zero)
 [TlachihuaniWizardTestInputV2]::keybd_event(18,0,2,[UIntPtr]::Zero)
 [void][TlachihuaniWizardTestInputV2]::SetForegroundWindow($hw)
 [void](Wait-For 'foreground after UAC' {([TlachihuaniWizardTestInputV2]::GetForegroundWindow() -eq $hw)})
 $r=$b.Current.BoundingRectangle
 [void][TlachihuaniWizardTestInputV2]::SetCursorPos([int]($r.Left+$r.Width/2),[int]($r.Top+$r.Height/2))
 [TlachihuaniWizardTestInputV2]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
 [TlachihuaniWizardTestInputV2]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
 Start-Sleep -Milliseconds 650
}
function Close-Check(){if(!$proc.WaitForExit(10000)){throw 'Wizard did not close'}}
function Apply-Wizard($name,$action,$success){
 Open-Wizard $name
 Click Review
 Click $action
 [void](Wait-For $success {if(Button 'Setup did not finish'){Click Finish;Close-Check;throw 'Wizard reported failure. Inspect the Windows Installer log.'};Button $success} 180)
 Say "PASS $success"
 Click Finish
 Close-Check
}
function Check-Registration {
 $script:registration=@(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object DisplayName -eq $product)
 if($registration.Count -ne 1){throw 'Expected exactly one Windows application entry'}
 $script:registration=$registration[0]
 $v=[Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $Bundle 'Installer.exe'))
 $version="$($v.FileMajorPart).$($v.FileMinorPart).$($v.FileBuildPart)"
 $installed="$env:ProgramFiles\XAIHT\$product"
 if($registration.DisplayVersion -ne $version -or $registration.Publisher -ne 'XAIHT' -or $registration.InstallLocation.TrimEnd('\') -ne $installed -or $registration.NoModify -ne 1 -or $registration.NoRepair -ne 1 -or !$registration.EstimatedSize -or $registration.WindowsInstaller -ne 1){throw 'Incomplete Windows application registration'}
 # MSI products expose ProductIcon through Windows Installer, not necessarily
 # DisplayIcon in the uninstall key (which standalone EXE installers create).
 $icon=[Text.StringBuilder]::new(4096);[uint32]$size=4096
 if([TlachihuaniWizardTestInputV2]::MsiGetProductInfo($registration.PSChildName,'ProductIcon',$icon,[ref]$size) -ne 0 -or !(Test-Path -LiteralPath $icon.ToString())){throw 'Windows Installer product icon is missing'}
 $app=Get-ItemProperty "HKLM:\SOFTWARE\XAIHT\$product"
 if($app.Version -ne $version -or !$app.OperatorSID -or $app.InstallLocation.TrimEnd('\') -ne $installed){throw 'Application discovery values differ'}
 foreach($f in 'Uninstaller.exe','Setup\START-HERE.html'){if(!(Test-Path -LiteralPath (Join-Path $installed $f))){throw "Installed maintenance file missing: $f"}}
 $shell=New-Object -ComObject WScript.Shell
 $start=[Environment]::GetFolderPath('CommonPrograms')
 $auto=[Environment]::GetFolderPath('CommonStartup')
 if($shell.CreateShortcut((Join-Path $start "$product XT.lnk")).Arguments -ne '--show' -or $shell.CreateShortcut((Join-Path $auto "$product XT.lnk")).Arguments){throw 'Start/login shortcut behavior differs'}
 if(!(Test-Path -LiteralPath (Join-Path $start "Uninstall $product.lnk"))){throw 'Uninstall shortcut missing'}
 Say "PASS Windows registration, version $version, publisher, icon, size, location and shortcuts"
}
function Remove-RegisteredProduct {
 # Exercise the command Windows Programs and Features owns, with its visible
 # native progress UI. Never use Win32_Product (which triggers MSI repair).
 $command=$registration.UninstallString
 if($command -notmatch '(?i)^MsiExec\.exe\s+/X(?<code>\{[0-9A-F-]{36}\})$'){throw "Unexpected registered uninstall command: $command"}
 $code=$Matches.code
 Start-Process -FilePath control.exe -ArgumentList 'appwiz.cpl' -WindowStyle Normal
 $desktop=[Windows.Automation.AutomationElement]::RootElement
 $window=Wait-For 'Programs and Features window' {
   $c=[Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::NameProperty,'Programs and Features')
   $desktop.FindFirst([Windows.Automation.TreeScope]::Children,$c)
 }
 [void][TlachihuaniWizardTestInputV2]::SetForegroundWindow([IntPtr]$window.Current.NativeWindowHandle)
 # Explorer's virtualized/legacy list is not reliably exposed by managed UIA.
 # The product row is a separate visual checkpoint; registry + MSI API checks
 # above are the automated contract. Never pretend a missing UIA row passed.
 $panelHandle=[IntPtr]$window.Current.NativeWindowHandle
 if(![TlachihuaniWizardTestInputV2]::IsWindowVisible($panelHandle) -or [TlachihuaniWizardTestInputV2]::IsIconic($panelHandle)){throw 'Programs and Features is not visible'}
 Say 'Programs and Features opened for visual inspection; registered metadata was verified above.'
 $msiLog=Join-Path (Split-Path $Report) 'registered-uninstall.log'
 $uninstall=Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -WindowStyle Normal -ArgumentList "/x $code /passive /norestart /L*v `"$msiLog`"" -PassThru
 if(!$uninstall.WaitForExit(120000)){throw 'Registered uninstall timed out'}
 if($uninstall.ExitCode -notin 0,3010){throw "Registered uninstall failed: $($uninstall.ExitCode); $msiLog"}
 if(Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$code"){throw 'Windows entry survived uninstall'}
 if(Get-ItemProperty "HKLM:\SOFTWARE\XAIHT\$product" -Name InstallLocation -ErrorAction SilentlyContinue){throw 'Discovery value survived uninstall'}
 Say 'PASS removal through registered Windows uninstall command with services running'
}
try{
 $product=if($Isolated){'Tlachihuani.SetupAcceptance'}else{'Tlachihuani'}
 foreach($n in 'Installer','Uninstaller'){
    if([Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $Bundle "$n.exe")).ProductName -ne $product){throw "Unexpected test package identity: $n"}
 }
 foreach($name in 'Installer','Uninstaller'){
    Open-Wizard $name
    Click Review
    if(!(Button 'Cancel')){throw 'Cancel missing from review'}
    Click Cancel
    Close-Check
    Say "PASS $name review and cancel"
 }
 if($Sandbox -or $Isolated){
    if(($Sandbox -and $env:USERNAME -ne 'WDAGUtilityAccount') -or (Get-Service -Name $product,"$product.Jobs" -ErrorAction SilentlyContinue)){throw 'Test target is not clean'}
    Apply-Wizard Installer Install 'Installation complete'
    Check-Registration
    $idPath="$env:ProgramData\XAIHT\$product.Jobs\installation.json"
    $identity=(Get-FileHash $idPath).Hash
    foreach($name in $product,"$product.Jobs"){
        $svc=Get-CimInstance Win32_Service -Filter "Name='$name'"
        if($svc.State -ne 'Stopped' -or $svc.StartMode -ne 'Manual' -or $svc.StartName -ne "NT SERVICE\$name"){throw "Unexpected service configuration: $name"}
        Start-Service $name
    }
    if($Sandbox){[void](Wait-For 'Jobs REST API' {try{(Invoke-RestMethod -TimeoutSec 2 'http://127.0.0.1:12064/api/v1/health').engine -eq 'ready'}catch{$false}} 65);Say 'PASS Jobs API ready'}
    Say "PASS both SCM services started: $product"
    Remove-RegisteredProduct
    if((Get-Service -Name $product,"$product.Jobs" -ErrorAction SilentlyContinue) -or (Test-Path "$env:ProgramFiles\XAIHT\$product\Service\Tlachihuani.Service.exe") -or (Get-FileHash $idPath).Hash -ne $identity){throw 'Removal ownership or preservation check failed'}
    Apply-Wizard Installer Install 'Installation complete'
    if((Get-FileHash $idPath).Hash -ne $identity){throw 'Identity changed on reinstall'}
    Apply-Wizard Uninstaller Uninstall 'Removal complete'
    Say 'PASS uninstall, retained identity and reinstall'
 }
 Say 'PASS all requested wizard checks'
}catch{Say ("FAILED: "+$_.Exception.Message);throw}
