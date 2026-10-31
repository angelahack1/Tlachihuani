param([ValidateSet('Build', 'Check', 'Publish')][string]$Mode = 'Check')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    dotnet restore Tlachihuani.slnx --locked-mode
    if ($LASTEXITCODE -ne 0) { throw "Restore failed: $LASTEXITCODE" }
    dotnet build Tlachihuani.slnx --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $LASTEXITCODE" }
    if ($Mode -eq 'Check') {
        & '.\tests\Tlachihuani.Checks\bin\Release\net10.0-windows\Tlachihuani.Checks.exe' --service-exe '.\src\Tlachihuani.Service\bin\Release\net10.0-windows\Tlachihuani.Service.exe'
        if ($LASTEXITCODE -ne 0) { throw "Checks failed: $LASTEXITCODE" }
    }
    if ($Mode -eq 'Publish') {
        foreach ($component in @('Service', 'Control', 'Tray', 'Jobs')) {
            dotnet publish "src/Tlachihuani.$component/Tlachihuani.$component.csproj" --configuration Release --no-restore --output "artifacts/publish/$component"
            if ($LASTEXITCODE -ne 0) { throw "$component publish failed: $LASTEXITCODE" }
        }
    }
    if ($Mode -eq 'Publish') { & "$PSScriptRoot\Prepare-JobsRuntime.ps1" -Destination (Join-Path $projectRoot 'artifacts\publish\Jobs\runtime') }
    Write-Host "$Mode completed successfully." -ForegroundColor Green
} finally { Pop-Location }
