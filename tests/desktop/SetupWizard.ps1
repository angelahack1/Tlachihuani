param([Parameter(Mandatory)][string]$Bundle,[switch]$Sandbox,[switch]$Isolated,[string]$Report)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
if(!('TlachihuaniWizardTestInput' -as [type])){Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
public static class TlachihuaniWizardTestInput {
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
 [TlachihuaniWizardTestInput]::keybd_event(18,0,0,[UIntPtr]::Zero);[TlachihuaniWizardTestInput]::keybd_event(18,0,2,[UIntPtr]::Zero)
 [void][TlachihuaniWizardTestInput]::SetForegroundWindow($hw)
 [void](Wait-For 'visible foreground wizard' {([TlachihuaniWizardTestInput]::IsWindowVisible($hw)) -and !([TlachihuaniWizardTestInput]::IsIconic($hw)) -and ([TlachihuaniWizardTestInput]::GetForegroundWindow() -eq $hw)})
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
 [TlachihuaniWizardTestInput]::keybd_event(18,0,0,[UIntPtr]::Zero)
 [TlachihuaniWizardTestInput]::keybd_event(18,0,2,[UIntPtr]::Zero)
 [void][TlachihuaniWizardTestInput]::SetForegroundWindow($hw)
 [void](Wait-For 'foreground after UAC' {([TlachihuaniWizardTestInput]::GetForegroundWindow() -eq $hw)})
 $r=$b.Current.BoundingRectangle
 [void][TlachihuaniWizardTestInput]::SetCursorPos([int]($r.Left+$r.Width/2),[int]($r.Top+$r.Height/2))
 [TlachihuaniWizardTestInput]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
 [TlachihuaniWizardTestInput]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
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
    $idPath="$env:ProgramData\XAIHT\$product.Jobs\installation.json"
    $identity=(Get-FileHash $idPath).Hash
    foreach($name in $product,"$product.Jobs"){
        $svc=Get-CimInstance Win32_Service -Filter "Name='$name'"
        if($svc.State -ne 'Stopped' -or $svc.StartMode -ne 'Manual' -or $svc.StartName -ne "NT SERVICE\$name"){throw "Unexpected service configuration: $name"}
        Start-Service $name
    }
    if($Sandbox){[void](Wait-For 'Jobs REST API' {try{(Invoke-RestMethod -TimeoutSec 2 'http://127.0.0.1:12064/api/v1/health').engine -eq 'ready'}catch{$false}} 65);Say 'PASS Jobs API ready'}
    Say "PASS both SCM services started: $product"
    Stop-Service -Name "$product.Jobs",$product
    Apply-Wizard Uninstaller Uninstall 'Removal complete'
    if((Get-Service -Name $product,"$product.Jobs" -ErrorAction SilentlyContinue) -or (Test-Path "$env:ProgramFiles\XAIHT\$product\Service\Tlachihuani.Service.exe") -or (Get-FileHash $idPath).Hash -ne $identity){throw 'Removal ownership or preservation check failed'}
    Apply-Wizard Installer Install 'Installation complete'
    if((Get-FileHash $idPath).Hash -ne $identity){throw 'Identity changed on reinstall'}
    Apply-Wizard Uninstaller Uninstall 'Removal complete'
    Say 'PASS uninstall, retained identity and reinstall'
 }
 Say 'PASS all requested wizard checks'
}catch{Say ("FAILED: "+$_.Exception.Message);throw}
