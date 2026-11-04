"""Verify the public download independently of the bundle builder."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

archive, output = map(Path, sys.argv[1:])
expected = {"Installer.exe", "Uninstaller.exe", "START-HERE.html",
            "READ-ME-FIRST.txt", "manifest.json", "SHA256SUMS.txt"}
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
assert Path(str(archive) + ".sha256").read_text().split()[0] == digest
assert not output.exists(), "Use a fresh application-owned extraction folder"
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    names = z.namelist()
    assert len(names) == len(expected)
    prefix = names[0].split("/")[0]
    assert {n.removeprefix(prefix + "/") for n in names} == expected
    assert all(n.startswith(prefix + "/") and ".." not in Path(n).parts for n in names)
    z.extractall(output)
bundle = output / prefix
manifest = json.loads((bundle / "manifest.json").read_text())
assert prefix == "Tlachihuani-" + manifest["version"]
assert manifest["architecture"] == "x64" and manifest["self_contained"] is True
for line in (bundle / "SHA256SUMS.txt").read_text().splitlines():
    sha, name = line.split("  ", 1)
    assert name in expected
    assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == sha, name
for name, entry in manifest["files"].items():
    content = (bundle / name).read_bytes()
    assert len(content) == entry["size"]
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
guide = (bundle / "START-HERE.html").read_text(encoding="utf-8")
assert "{{VERSION}}" not in guide and manifest["version"] in guide
assert "<script" not in guide and '<link ' not in guide
print("PASS: ZIP CRC, exact public contents, extraction, versions, sizes and SHA-256 hashes")
print("Extracted customer package:", bundle)
