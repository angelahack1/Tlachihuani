param(
    [string]$BrowserPython,
    [switch]$Installed,
    [int]$TrayProcessId
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$project = Split-Path $PSScriptRoot
Push-Location -LiteralPath $project
try {
    if ($Installed) {
        if (!$BrowserPython) { throw 'Installed browser acceptance requires -BrowserPython.' }
        $image = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani\Jobs\Tlachihuani.Jobs.exe'
        $switches = @('--installed')
        if ($TrayProcessId) {
            $actual = Get-Process -Id $TrayProcessId
            $expected = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani\Tray\Tlachihuani.Tray.exe'
            if ($actual.Path -ne $expected -or $actual.SessionId -ne (Get-Process -Id $PID).SessionId) { throw 'Unexpected tray identity.' }
            $switches += @('--tray-pid',[string]$TrayProcessId)
        }
    } else {
        $image = '.\artifacts\publish\Jobs\Tlachihuani.Jobs.exe'
        $runtime = '.\artifacts\publish\Jobs\runtime\python.exe'
        if (!(Test-Path -LiteralPath $runtime)) { throw 'Publish Jobs and its private runtime first.' }
        & $runtime -B -u '.\tests\integration\jobs_swarm.py' $image
        if ($LASTEXITCODE) { throw "Private swarm check failed ($LASTEXITCODE)." }
        $switches = @()
    }
    if ($BrowserPython) {
        Assert-VisibleDevelopmentConsole
        & $BrowserPython -B -u '.\tests\desktop\torrenter_workspace.py' $image @switches
        if ($LASTEXITCODE) { throw "Headed Chrome acceptance failed ($LASTEXITCODE)." }
    }
} finally { Pop-Location }
