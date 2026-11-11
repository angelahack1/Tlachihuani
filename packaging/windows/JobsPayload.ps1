function Assert-PlainPath([string]$Path) {
    $item=[IO.DirectoryInfo]::new($Path)
    while($null -ne $item) {
        if($item.Exists -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing reparse point $($item.FullName)" }
        $item=$item.Parent
    }
}

$JobsFirewallGroup = 'Tlachihuani Jobs'

# Torrent peers connect inbound to the worker interpreter: TCP for peers,
# UDP for uTP peers and DHT. One rule per protocol, scoped to that program.
function Set-JobsPeerFirewallRule([string]$jobs) {
    $python = Join-Path $jobs 'runtime\python.exe'
    Remove-JobsPeerFirewallRule
    foreach ($protocol in @('TCP','UDP')) {
        [void](New-NetFirewallRule -Name "Tlachihuani.Jobs.Peers.$protocol" `
            -DisplayName "Tlachihuani Jobs torrent peers ($protocol)" -Group $JobsFirewallGroup `
            -Direction Inbound -Action Allow -Program $python -Protocol $protocol -Profile Any -Enabled True)
    }
}

function Remove-JobsPeerFirewallRule {
    Get-NetFirewallRule -Group $JobsFirewallGroup -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}

function Copy-JobsPayload([string]$package,[string]$jobs) {
    [void][IO.Directory]::CreateDirectory($jobs)
    foreach ($entry in Get-ChildItem -LiteralPath (Join-Path $package 'Jobs')) {
        if ($entry.Name -eq 'worker') {
            $code = [IO.Directory]::CreateDirectory((Join-Path $jobs 'worker'))
            Get-ChildItem -LiteralPath $entry.FullName -Filter '*.py' -File | Copy-Item -Destination $code.FullName
        } else { Copy-Item -LiteralPath $entry.FullName -Destination $jobs -Recurse }
    }
}
