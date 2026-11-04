# Real MSI transactions with separately named inert QA services. No production
# installation, queue, pipe or downloaded file is changed. Keep this console open.
param([Parameter(Mandatory)][string]$PublishDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot)
$run=Join-Path $root ('artifacts\verification\startup-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($run)
$env:TEMP=$env:TMP=$run
. "$root\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
if(!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Open this test in a visible administrator PowerShell window.'
}
$product='Tlachihuani.SetupAcceptance'
if(Get-Service -Name $product,"$product.Jobs" -ErrorAction SilentlyContinue){throw 'The QA services already exist; preserve them and inspect their previous test.'}
$transcribing=$false
$savedPaths=@{}
foreach($name in 'TL_PUBLISH_DIR','TL_SETUP_WORK','TL_SETUP_OUTPUT'){$savedPaths[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
Push-Location -LiteralPath $root
try{
    Start-Transcript -LiteralPath (Join-Path $run 'test.log') | Out-Null
    $transcribing=$true
    $env:TL_PUBLISH_DIR=(Resolve-Path -LiteralPath $PublishDirectory).Path
    $env:TL_SETUP_WORK=Join-Path $run 'setup-work'
    $env:TL_SETUP_OUTPUT=Join-Path $run 'bundle'
    python -B packaging/setup/build.py --isolated-acceptance
    if($LASTEXITCODE){throw 'QA package build failed.'}
    [xml]$definition=Get-Content -LiteralPath (Join-Path $env:TL_SETUP_WORK 'Package.wxs') -Raw
    $code=$definition.Wix.Package.ProductCode
    $msi=Join-Path $env:TL_SETUP_WORK "$product.msi"
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $startup=Join-Path ([Environment]::GetFolderPath('CommonStartup')) "$product XT.lnk"
    $start=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) "$product XT.lnk"
    $desktop=Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) "$product XT.lnk"
    $identity=$null
    foreach($choice in 0,1){
        Write-Host "REAL MSI INSTALL: login startup=$choice" -ForegroundColor Cyan
        $installLog=Join-Path $run "install-$choice.log"
        $process=Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -WindowStyle Normal -ArgumentList "/i `"$msi`" TLOPERATOR=$sid TLTRAYSTARTUP=$choice /passive /norestart /L*v `"$installLog`"" -PassThru -Wait
        if($process.ExitCode -ne 0){throw "MSI install exit $($process.ExitCode): $installLog"}
        foreach($name in $product,"$product.Jobs"){
            $service=Get-CimInstance Win32_Service -Filter "Name='$name'"
            if(!$service -or $service.StartMode -ne 'Manual' -or $service.State -ne 'Stopped' -or $service.StartName -ne "NT SERVICE\$name"){throw "Service startup policy failed: $name"}
        }
        $app=Get-ItemProperty "HKLM:\SOFTWARE\XAIHT\$product"
        if($app.TrayAtLogin -ne $choice -or $app.OperatorSID -ne $sid){throw 'Registry choice/operator differ from installer input.'}
        if((Test-Path -LiteralPath $startup) -ne [bool]$choice){throw 'Startup shortcut does not honor the choice.'}
        $shell=New-Object -ComObject WScript.Shell
        foreach($shortcut in $start,$desktop){
            if(!(Test-Path -LiteralPath $shortcut)){throw "Missing shortcut: $shortcut"}
            $link=$shell.CreateShortcut($shortcut)
            if($link.TargetPath -ne "$env:ProgramFiles\XAIHT\$product\Tray\Tlachihuani.Tray.exe" -or $link.Arguments -ne '--show'){throw "Wrong shortcut target: $shortcut"}
        }
        if($choice -and $shell.CreateShortcut($startup).Arguments){throw 'Login shortcut must not request a panel or service action.'}
        $arp=Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$code"
        if($arp.DisplayName -ne $product -or $arp.DisplayVersion -ne $definition.Wix.Package.Version -or !$arp.UninstallString){throw 'Windows application registration failed.'}
        $idPath="$env:ProgramData\XAIHT\$product.Jobs\installation.json"
        $hash=(Get-FileHash -LiteralPath $idPath).Hash
        if($identity -and $identity -ne $hash){throw 'Reinstall replaced the retained identity.'}
        $identity=$hash
        Write-Host "PASS startup=$choice; both services Stopped/Manual; Start + Desktop; registry + Windows uninstall entry." -ForegroundColor Green
        $removeLog=Join-Path $run "remove-$choice.log"
        $process=Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -WindowStyle Normal -ArgumentList "/x $code /passive /norestart /L*v `"$removeLog`"" -PassThru -Wait
        if($process.ExitCode -ne 0){throw "MSI removal exit $($process.ExitCode): $removeLog"}
        if(Get-Service -Name $product,"$product.Jobs" -ErrorAction SilentlyContinue){throw 'QA service survived removal.'}
        foreach($shortcut in $start,$desktop,$startup){if(Test-Path -LiteralPath $shortcut){throw "Shortcut survived removal: $shortcut"}}
        if(Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$code"){throw 'Uninstall entry survived removal.'}
        if((Get-FileHash -LiteralPath $idPath).Hash -ne $identity){throw 'Removal changed retained state.'}
        Write-Host "PASS removal startup=$choice; owned shortcuts and services gone; identity retained." -ForegroundColor Green
    }
    git diff --check
    if($LASTEXITCODE){throw 'Git whitespace check failed.'}
    Write-Host "PASS all real MSI startup-choice tests. Evidence: $run" -ForegroundColor Green
} finally {
    if($transcribing){Stop-Transcript | Out-Null}
    foreach($name in $savedPaths.Keys){[Environment]::SetEnvironmentVariable($name,$savedPaths[$name],'Process')}
    Pop-Location
}
