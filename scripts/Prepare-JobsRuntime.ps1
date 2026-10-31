# Prepare a private CPython/libtorrent runtime, without installing into a system Python.
param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole
$cache = Join-Path (Split-Path $PSScriptRoot) 'artifacts\jobs-runtime-cache'
[void][IO.Directory]::CreateDirectory($cache)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$client = [Net.WebClient]::new()
function Fetch([string]$Name,[string]$Url,[string]$Digest) {
    $path = Join-Path $cache $Name
    if (-not [IO.File]::Exists($path)) { $client.DownloadFile($Url, $path) }
    $stream = [IO.File]::OpenRead($path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $hash.Dispose() }
    if ($actual -ne $Digest) { throw "Integrity mismatch for $Name. Check the cached download at $path." }
    return $path
}
$python = Fetch 'python-3.12.10-embed-amd64.zip' 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
$name = 'libtorrent-2.1.1-cp312-cp312-win_amd64.whl'
$wheelPath = Join-Path $cache $name
$url = ''
if (-not [IO.File]::Exists($wheelPath)) {
    $meta = $client.DownloadString('https://pypi.org/pypi/libtorrent/2.1.1/json') | ConvertFrom-Json
    $url = ($meta.urls | Where-Object filename -eq $name).url
    if (([uri]$url).Host -ne 'files.pythonhosted.org') { throw 'Unexpected wheel origin.' }
}
$wheel = Fetch $name $url '493954405d15f14b9d9f9b1762ae78e7fecc5a44699f74cb433a9800fa3a7b45'
$dest = [IO.Path]::GetFullPath($Destination)
[void][IO.Directory]::CreateDirectory($dest)
# Repeated builds replace only members of these verified archives.
foreach($archive in @($python,$wheel)) {
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach($item in $zip.Entries) {
            if (!$item.Name) { continue }
            $file = [IO.Path]::GetFullPath((Join-Path $dest $item.FullName))
            if (!$file.StartsWith(($dest.TrimEnd('\')+'\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Archive traversal.' }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($item,$file,$true)
        }
    } finally { $zip.Dispose() }
}
[IO.File]::WriteAllLines((Join-Path $dest 'python312._pth'), @('python312.zip','.','../worker'), [Text.Encoding]::ASCII)
Write-Host "Verified private runtime staged in $dest"
