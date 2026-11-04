# Build from the published payload; see packaging/setup/README.md.
param([string]$PublishDirectory, [string]$WorkDirectory, [string]$OutputDirectory)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$root=Split-Path $PSScriptRoot
$savedPaths=@{}
foreach($name in 'TL_PUBLISH_DIR','TL_SETUP_WORK','TL_SETUP_OUTPUT'){$savedPaths[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
Push-Location -LiteralPath $root
try {
    $cache=if($WorkDirectory){$WorkDirectory}else{Join-Path $root 'artifacts\setup-build'}
    if(!$PublishDirectory){$PublishDirectory=Join-Path $root 'artifacts\publish'}
    [void][IO.Directory]::CreateDirectory($cache)
    $env:TEMP=$env:TMP=$cache
    if(!$env:DOTNET_CLI_HOME){$env:DOTNET_CLI_HOME=Join-Path $cache 'dotnet'}
    if(!$env:NUGET_PACKAGES){$env:NUGET_PACKAGES=Join-Path $cache 'packages'}
    $version=([xml](Get-Content -LiteralPath 'Directory.Build.props' -Raw)).Project.PropertyGroup.Version
    foreach($component in 'Service','Control','Tray','Jobs'){
        $image=(Resolve-Path (Join-Path $PublishDirectory "$component\Tlachihuani.$component.exe")).Path
        $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($image)
        if("$($v.FileMajorPart).$($v.FileMinorPart).$($v.FileBuildPart)" -ne $version){throw "Publish $component at version $version before packaging."}
    }
    if(!(Test-Path -LiteralPath 'artifacts\setup-tools\wix.exe')){
        dotnet tool install wix --version 4.0.6 --tool-path artifacts/setup-tools --configfile NuGet.Config
        if($LASTEXITCODE){throw 'Could not install WiX 4.0.6.'}
    }
    $env:TL_PUBLISH_DIR=$PublishDirectory
    $env:TL_SETUP_WORK=$cache
    $env:TL_SETUP_OUTPUT=if($OutputDirectory){$OutputDirectory}else{Join-Path $root 'artifacts\setup'}
    python -B packaging/setup/build.py
    if($LASTEXITCODE){throw 'Setup package build failed.'}
} finally {
    foreach($name in $savedPaths.Keys){[Environment]::SetEnvironmentVariable($name,$savedPaths[$name],'Process')}
    Pop-Location
}
