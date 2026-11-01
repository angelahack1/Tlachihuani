param(
    [string]$BrowserPython,
    [switch]$Installed,
    [string]$Username,
    [string]$Controller = "http://127.0.0.1:8000"
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
        if (!$Username) { throw 'Supply a signed-in development account with -Username.' }
        $switches = @('--installed','--controller',$Controller,'--username',$Username)
    } else {
        $image = '.\artifacts\publish\Jobs\Tlachihuani.Jobs.exe'
        $runtime = '.\artifacts\publish\Jobs\runtime\python.exe'
        if (!(Test-Path -LiteralPath $runtime)) { throw 'Publish Jobs and its private runtime first.' }
        & $runtime -I -B -u '.\tests\integration\test_magnet_queue.py'
        if ($LASTEXITCODE) { throw "Magnet queue and recovery check failed ($LASTEXITCODE)." }
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
