# Build from the published payload; see packaging/setup/README.md.
$ErrorActionPreference='Stop'
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$root=Split-Path $PSScriptRoot
Push-Location -LiteralPath $root
try {
    $cache=Join-Path $root 'artifacts\setup-build'
    [void][IO.Directory]::CreateDirectory($cache)
    $env:TEMP=$env:TMP=$cache
    $env:DOTNET_CLI_HOME=Join-Path $cache 'dotnet'
    $env:NUGET_PACKAGES=Join-Path $cache 'packages'
    $version=([xml](Get-Content -LiteralPath 'Directory.Build.props' -Raw)).Project.PropertyGroup.Version
    foreach($component in 'Service','Control','Tray','Jobs'){
        $image=(Resolve-Path "artifacts\publish\$component\Tlachihuani.$component.exe").Path
        $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($image)
        if("$($v.FileMajorPart).$($v.FileMinorPart).$($v.FileBuildPart)" -ne $version){throw "Publish $component at version $version before packaging."}
    }
    if(!(Test-Path -LiteralPath 'artifacts\setup-tools\wix.exe')){
        dotnet tool install wix --version 4.0.6 --tool-path artifacts/setup-tools --configfile NuGet.Config
        if($LASTEXITCODE){throw 'Could not install WiX 4.0.6.'}
    }
    python -B packaging/setup/build.py
    if($LASTEXITCODE){throw 'Setup package build failed.'}
} finally {Pop-Location}
