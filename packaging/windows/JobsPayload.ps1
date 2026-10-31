function Assert-PlainPath([string]$Path) {
    $item=[IO.DirectoryInfo]::new($Path)
    while($null -ne $item) {
        if($item.Exists -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing reparse point $($item.FullName)" }
        $item=$item.Parent
    }
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
