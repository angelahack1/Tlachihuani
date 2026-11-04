"""Verify every MSI cabinet byte and registration metadata (Windows Python 3)."""
from pathlib import Path
import ctypes
from ctypes import wintypes as w
import subprocess
import sys

package, scratch, publish = map(Path, sys.argv[1:4])
api = ctypes.WinDLL("msi")
H = w.UINT
api.MsiOpenDatabaseW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.POINTER(H)]
api.MsiDatabaseOpenViewW.argtypes = [H, w.LPCWSTR, ctypes.POINTER(H)]
api.MsiViewExecute.argtypes = [H, H]
api.MsiViewFetch.argtypes = [H, ctypes.POINTER(H)]
api.MsiRecordGetStringW.argtypes = [H, w.UINT, w.LPWSTR, ctypes.POINTER(w.DWORD)]
api.MsiRecordReadStream.argtypes = [H, w.UINT, ctypes.c_void_p, ctypes.POINTER(w.DWORD)]

def checked(rc):
    if rc: raise OSError(rc, "Windows Installer database operation failed")

def opened(fn, *args):
    h = H()
    checked(fn(*args, ctypes.byref(h)))
    return h

def string(rec, field):
    size = w.DWORD(0)
    rc = api.MsiRecordGetStringW(rec, field, None, ctypes.byref(size))
    if rc not in (0, 234): checked(rc)
    buf = ctypes.create_unicode_buffer(size.value + 1)
    size.value += 1
    checked(api.MsiRecordGetStringW(rec, field, buf, ctypes.byref(size)))
    return buf.value

db = opened(api.MsiOpenDatabaseW, str(package.resolve()), None)
def rows(sql, count):
    view = opened(api.MsiDatabaseOpenViewW, db, sql)
    try:
        checked(api.MsiViewExecute(view, 0))
        while True:
            rec = H()
            rc = api.MsiViewFetch(view, ctypes.byref(rec))
            if rc == 259: break
            checked(rc)
            try: yield tuple(string(rec, i) for i in range(1, count + 1))
            finally: api.MsiCloseHandle(rec)
    finally: api.MsiCloseHandle(view)

try:
    props = dict(rows("SELECT `Property`,`Value` FROM `Property`", 2))
    assert props["ARPNOMODIFY"] == props["ARPNOREPAIR"] == "1"
    assert props["Manufacturer"] == "XAIHT" and props["ARPPRODUCTICON"] == "XT.ico"
    assert props["ARPHELPLINK"].startswith("https://github.com/angelahack1/Tlachihuani")
    assert "ARPNOREMOVE" not in props and "ARPSYSTEMCOMPONENT" not in props
    assert props["TLTRAYSTARTUP"] == "0", "Silent installs must not opt into login startup"
    assert "TLTRAYSTARTUP" in props["SecureCustomProperties"].split(";")
    components = {c: (d, condition) for c, d, condition in rows("SELECT `Component`,`Directory_`,`Condition` FROM `Component`", 3)}
    shortcuts = list(rows("SELECT `Shortcut`,`Component_`,`Arguments` FROM `Shortcut`", 3))
    for folder in ("ProgramMenuFolder", "DesktopFolder", "StartupFolder"):
        match = [(c, a) for s, c, a in shortcuts if s == "Link" + folder]
        assert len(match) == 1, folder
        component, args = match[0]
        assert components[component][0] == folder
        assert args == ("" if folder == "StartupFolder" else "--show")
        assert components[component][1] == ('TLTRAYSTARTUP = "1"' if folder == "StartupFolder" else "")
    services = list(rows("SELECT `Name`,`StartType`,`StartName` FROM `ServiceInstall`", 3))
    assert len(services) == 2
    for name, start, account in services:
        assert start == "3" and account == "NT SERVICE\\" + name, (name, start, account)
    for name, event in rows("SELECT `Name`,`Event` FROM `ServiceControl`", 2):
        assert int(event) & (1 | 16) == 0, "MSI must never start a service: " + name
    print("PASS optional login startup, Start/Desktop shortcuts and Manual services with no automatic start.", flush=True)
    dirs = {d: (parent, name.split("|")[-1]) for d, parent, name in rows("SELECT `Directory`,`Directory_Parent`,`DefaultDir` FROM `Directory`", 3)}
    def rel(d):
        if d == "appRoot": return Path()
        parent, name = dirs[d]
        return rel(parent) / name
    folders = dict(rows("SELECT `Component`,`Directory_` FROM `Component`", 2))
    cabinets = list(rows("SELECT `Cabinet` FROM `Media`", 1))
    assert cabinets and all(c[0].startswith("#") for c in cabinets)
    extracted = scratch / "expanded"
    extracted.mkdir(parents=True)
    for n, (cabinet,) in enumerate(cabinets):
        name = cabinet[1:]
        cab = scratch / (str(n) + ".cab")
        view = opened(api.MsiDatabaseOpenViewW, db, "SELECT `Data` FROM `_Streams` WHERE `Name` = '" + name.replace("'", "''") + "'")
        try:
            checked(api.MsiViewExecute(view, 0))
            rec = opened(api.MsiViewFetch, view)
            try:
                buf = ctypes.create_string_buffer(65536)
                with cab.open("xb") as out:
                    while True:
                        count = w.DWORD(len(buf))
                        checked(api.MsiRecordReadStream(rec, 1, buf, ctypes.byref(count)))
                        out.write(buf.raw[:count.value])
                        if count.value < len(buf): break
            finally: api.MsiCloseHandle(rec)
        finally: api.MsiCloseHandle(view)
        print("Checking cabinet", n + 1, "of", len(cabinets), flush=True)
        subprocess.run(["expand.exe", "-F:*", str(cab), str(extracted)], check=True, stdout=subprocess.DEVNULL)
    expected = {p.relative_to(publish) for part in ("Service", "Jobs", "Control", "Tray") for p in (publish/part).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pdb")}
    setup_sources = {Path("Setup/SetupIdentity.exe"): "SetupIdentity.exe", Path("Uninstaller.exe"): "Uninstaller.exe", Path("Setup/START-HERE.html"): "START-HERE.html"}
    actual, setup_actual = set(), set()
    for fid, cid, filename in rows("SELECT `File`,`Component_`,`FileName` FROM `File`", 3):
        path = rel(folders[cid]) / filename.split("|")[-1]
        data = (extracted / fid).read_bytes()
        if path in setup_sources:
            assert data == (package.parent / setup_sources[path]).read_bytes(), str(path)
            setup_actual.add(path)
        else:
            assert data == (publish / path).read_bytes(), str(path)
            actual.add(path)
    assert actual == expected, sorted(actual ^ expected)
    assert setup_actual == set(setup_sources)
    print("PASS:", len(actual), "runtime files and all maintenance files verified byte-for-byte; MSI registration properties verified.")
finally:
    api.MsiCloseHandle(db)
