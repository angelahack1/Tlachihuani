"""Compare every distributed runtime byte with the source of the MSI cabinet (Windows Python 3.12)."""
from pathlib import Path
import ctypes
import subprocess
import sys
import msilib

package, scratch, publish = map(Path, sys.argv[1:4])
db = msilib.OpenDatabase(str(package), msilib.MSIDBOPEN_READONLY)
def rows(sql, count):
    view=db.OpenView(sql)
    view.Execute(None)
    while rec:=view.Fetch():
        yield tuple(rec.GetString(i) for i in range(1,count+1))
dirs={d:(parent,name.split("|")[-1]) for d,parent,name in rows("SELECT `Directory`,`Directory_Parent`,`DefaultDir` FROM `Directory`",3)}
def rel(d):
    if d=="appRoot":return Path()
    parent,name=dirs[d]
    return rel(parent)/name
folders=dict(rows("SELECT `Component`,`Directory_` FROM `Component`",2))
cabinets=list(rows("SELECT `Cabinet` FROM `Media`",1))
assert len(cabinets)==1 and cabinets[0][0].startswith("#")
name=cabinets[0][0][1:]
cab=scratch/"payload.cab"
api=ctypes.WinDLL("msi")
def checked(result):
    if result:raise OSError(result,"Windows Installer stream read failed")
handles=[]
def handle(func,*args):
    value=ctypes.c_uint()
    checked(func(*args,ctypes.byref(value)))
    handles.append(value)
    return value
try:
    native=handle(api.MsiOpenDatabaseW,str(package),None)
    view=handle(api.MsiDatabaseOpenViewW,native,"SELECT `Data` FROM `_Streams` WHERE `Name` = '"+name+"'")
    checked(api.MsiViewExecute(view,0))
    rec=handle(api.MsiViewFetch,view)
    buf=ctypes.create_string_buffer(65536)
    with cab.open("xb") as out:
        while True:
            count=ctypes.c_uint(len(buf))
            checked(api.MsiRecordReadStream(rec,1,buf,ctypes.byref(count)))
            out.write(buf.raw[:count.value])
            if count.value<len(buf):break
finally:
    for h in reversed(handles):api.MsiCloseHandle(h)
extracted=scratch/"expanded"
extracted.mkdir()
subprocess.run(["expand.exe","-F:*",str(cab),str(extracted)],check=True,stdout=subprocess.DEVNULL)
expected={p.relative_to(publish) for part in ("Service","Jobs","Control","Tray") for p in (publish/part).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc",".pdb")}
actual=set()
for fid,cid,filename in rows("SELECT `File`,`Component_`,`FileName` FROM `File`",3):
    path=rel(folders[cid])/filename.split("|")[-1]
    data=(extracted/fid).read_bytes()
    if path==Path("Setup/SetupIdentity.exe"):continue
    assert data==(publish/path).read_bytes(),str(path)
    actual.add(path)
assert actual==expected, sorted(actual ^ expected)
print("PASS: all",len(actual),"published runtime files verified byte-for-byte inside the shipping installer.")
