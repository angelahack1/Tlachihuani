# One visible, fail-closed path from the latest local release tag to dist.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$savedEnvironment=@{}
foreach($name in 'TEMP','TMP','DOTNET_CLI_HOME','NUGET_PACKAGES','DOTNET_CLI_TELEMETRY_OPTOUT','DOTNET_GENERATE_ASPNET_CERTIFICATE','PYTHONDONTWRITEBYTECODE','TL_PUBLISH_DIR','TL_SETUP_WORK','TL_SETUP_OUTPUT'){
    $savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process')
}
$lock=$null
$transcribing=$false
Push-Location -LiteralPath $root
try {
    $cache=Join-Path $root 'artifacts\release-cache'
    [void][IO.Directory]::CreateDirectory($cache)
    # Set scratch BEFORE the visibility probe compiles its native declarations.
    $env:TEMP=$env:TMP=$cache
    $env:DOTNET_CLI_HOME=Join-Path $cache 'dotnet'
    $env:NUGET_PACKAGES=Join-Path $cache 'packages'
    $env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
    $env:DOTNET_GENERATE_ASPNET_CERTIFICATE='false'
    $env:PYTHONDONTWRITEBYTECODE='1'
    . "$PSScriptRoot\Assert-Visible.ps1"
    Assert-VisibleDevelopmentConsole
    try{$lock=[IO.File]::Open((Join-Path $cache 'release.lock'),'OpenOrCreate','ReadWrite','None')}
    catch{throw 'Another release build holds the release lock. Let it finish first.'}
    foreach($tool in 'git','python','dotnet'){if(!(Get-Command $tool -ErrorAction SilentlyContinue)){throw "Required build tool is missing: $tool"}}
    $run=Join-Path $root ('artifacts\release-builds\'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    [void][IO.Directory]::CreateDirectory($run)
    Start-Transcript -LiteralPath (Join-Path $run 'build.log') | Out-Null
    $transcribing=$true
    Write-Host 'TLACHIHUANI / RELEASE BUILDER' -ForegroundColor Cyan
    python -B -m unittest discover -s tests/integration -p test_release_version.py -v
    if($LASTEXITCODE){throw 'Release version regression checks failed.'}
    $record=python -B scripts/release_version.py --stamp
    if($LASTEXITCODE){throw 'Release tag selection or version stamping failed.'}
    $release=$record | ConvertFrom-Json
    $version=$release.version
    Write-Host "Release $version from tag $($release.tag); building the current checkout ($($release.commit))." -ForegroundColor Cyan
    if($release.working_tree_modified){Write-Host 'Local edits are included. Nothing will be committed or uploaded.' -ForegroundColor Yellow}
    $record | Set-Content -LiteralPath (Join-Path $run 'source.json') -Encoding UTF8
    $publish=Join-Path $run 'publish'
    & "$PSScriptRoot\Build.ps1" -Mode Check
    & "$PSScriptRoot\Build.ps1" -Mode Publish -PublishDirectory $publish
    $setupWork=Join-Path $run 'setup-work'
    $setupOutput=Join-Path $run 'setup'
    & "$PSScriptRoot\Build-Setup.ps1" -PublishDirectory $publish -WorkDirectory $setupWork -OutputDirectory $setupOutput
    $archive=Join-Path $setupOutput "$version\Tlachihuani-$version-windows-x64.zip"
    python -B tests/integration/check_setup_payload.py (Join-Path $setupWork 'Tlachihuani.msi') (Join-Path $run 'payload-check') $publish
    if($LASTEXITCODE){throw 'MSI payload verification failed.'}
    python -B tests/integration/check_setup_zip.py $archive (Join-Path $run 'zip-check')
    if($LASTEXITCODE){throw 'ZIP verification failed.'}
    # dist receives bytes only after ALL checks succeed. Older versions are kept.
    $dist=Join-Path $root 'dist'
    [void][IO.Directory]::CreateDirectory($dist)
    $copies=@()
    foreach($source in $archive,($archive+'.sha256')){
        $target=Join-Path $dist ([IO.Path]::GetFileName($source))
        $stage=$target+'.new'
        Copy-Item -LiteralPath $source -Destination $stage -Force
        if((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $stage).Hash){throw 'Distribution copy hash mismatch.'}
        $copies+=@{Target=$target; Stage=$stage; Backup=$target+'.previous'; Existed=(Test-Path -LiteralPath $target); Done=$false}
    }
    try{
        foreach($copy in $copies){
            if($copy.Existed){[IO.File]::Replace($copy.Stage,$copy.Target,$copy.Backup)}else{[IO.File]::Move($copy.Stage,$copy.Target)}
            $copy.Done=$true
        }
    }catch{
        foreach($copy in $copies){
            if($copy.Done){
                if($copy.Existed){[IO.File]::Replace($copy.Backup,$copy.Target,$null)}else{[IO.File]::Delete($copy.Target)}
            }
        }
        throw
    }
    foreach($copy in $copies){if(Test-Path -LiteralPath $copy.Backup){Remove-Item -LiteralPath $copy.Backup -Force}}
    Write-Host "READY: $(Join-Path $dist ([IO.Path]::GetFileName($archive)))" -ForegroundColor Green
    Write-Host "Upload the ZIP and its .sha256 to your GitHub Release. Build log: $run\build.log"
    Write-Host 'Package checks passed. Clean-Windows installation and reboot acceptance remain separate release checks.'
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if($transcribing){Stop-Transcript | Out-Null}
    if($lock){$lock.Dispose()}
    foreach($name in $savedEnvironment.Keys){[Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process')}
    Pop-Location
}
