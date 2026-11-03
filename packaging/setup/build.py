"""Build the two Windows wizards and the transactional MSI from published bytes."""
import hashlib
import os
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
if sys.argv[1:] not in ([], ["--isolated-acceptance"]):
    raise SystemExit("Expected no arguments or --isolated-acceptance")
isolated = bool(sys.argv[1:])
WORK = ROOT / ("artifacts/setup-build-qa" if isolated else "artifacts/setup-build")
OUT = ROOT / ("artifacts/verification/setup-package-qa" if isolated else "artifacts/setup")
PUB = ROOT / "artifacts/publish"
NAME = "Tlachihuani.SetupAcceptance" if isolated else "Tlachihuani"
FAMILY = uuid.UUID("1b626a92-29ac-4c9b-bdad-a82914f47e04")
if isolated:
    FAMILY = uuid.uuid5(FAMILY, "isolated-test-only")
VERSION = ET.parse(ROOT / "Directory.Build.props").findtext(".//Version")
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", VERSION):
    raise ValueError("Setup requires a three-part numeric product version")
if not isolated:
    OUT = OUT / VERSION / "windows-x64"
else:
    generation = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(SRC.glob("*.cs"))) + Path(__file__).read_bytes()).hexdigest()[:12]
    OUT = OUT / generation
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
os.environ.update(TMP=str(WORK), TEMP=str(WORK), DOTNET_ROLL_FORWARD="Major")
CODE = "{" + str(uuid.uuid5(FAMILY, VERSION)).upper() + "}"
CSC = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
ICON = ROOT / "assets/branding/XT.ico"
config = WORK / "Product.cs"
config.write_text(f'[assembly:System.Reflection.AssemblyProduct("{NAME}")]\n'
                  f'[assembly:System.Reflection.AssemblyVersion("{VERSION}.0")]\n'
                  f'[assembly:System.Reflection.AssemblyFileVersion("{VERSION}.0")]\n'
                  f'internal static class Product {{ public const string Code="{CODE}", Name="{NAME}", Family="{FAMILY}"; }}\n')

def compile_tool(name, source, *extra):
    target = WORK / name
    args = [str(CSC), "/nologo", "/platform:x64", "/target:winexe", "/optimize+",
            "/win32icon:" + str(ICON), "/out:" + str(target),
            "/reference:System.ServiceProcess.dll,System.Windows.Forms.dll,System.Drawing.dll,System.Web.Extensions.dll",
            *extra, str(config), str(SRC / "Ownership.cs"), str(SRC / "ServiceIdentity.cs"), str(SRC / source)]
    subprocess.run(args, check=True)
    return target

guard = compile_tool("SetupIdentity.exe", "Guard.cs")
remove = compile_tool("Uninstaller.exe", "Wizard.cs", "/define:REMOVE")
def child(parent, tag, **attrs):
    return ET.SubElement(parent, tag, attrs)
def ident(prefix, key):
    return prefix + hashlib.sha256(key.encode()).hexdigest()[:26]

xml = ET.Element("Wix", xmlns="http://wixtoolset.org/schemas/v4/wxs")
pkg = child(xml, "Package", Name=NAME, Manufacturer="XAIHT", Version=VERSION, ProductCode=CODE,
            UpgradeCode=str(FAMILY), Scope="perMachine", InstallerVersion="500", Language="1033")
child(pkg,"MediaTemplate",EmbedCab="yes")
child(pkg,"Icon",Id="XTIcon",SourceFile=str(ICON))
child(pkg,"Property",Id="ARPPRODUCTICON",Value="XTIcon")
child(pkg,"Property",Id="TLOPERATOR",Secure="yes")
child(pkg,"SetProperty",Id="TLOPERATOR",Value="[UserSID]",Before="CostFinalize",Sequence="execute",Condition="NOT TLOPERATOR")
files=child(child(child(pkg,"StandardDirectory",Id="ProgramFiles64Folder"),"Directory",Id="vendor",Name="XAIHT"),"Directory",Id="appRoot",Name=NAME)
feature=child(pkg,"Feature",Id="Complete",Title=NAME,Level="1")
dirs={"":files}
def directory(rel):
    if rel not in dirs:
        parent,_,name=rel.rpartition("/")
        dirs[rel]=child(directory(parent),"Directory",Id=ident("D",rel),Name=name)
    return dirs[rel]
def component(folder,key):
    cid=ident("C",key)
    child(feature,"ComponentRef",Id=cid)
    return child(folder,"Component",Id=cid,Guid=str(uuid.uuid5(FAMILY,key)),Bitness="always64")
for rel in ["Service/Tlachihuani.Service.exe","Control/Tlachihuani.Control.exe","Tray/Tlachihuani.Tray.exe","Jobs/Tlachihuani.Jobs.exe","Jobs/runtime/python.exe","Jobs/worker/worker.py","Jobs/wwwroot/index.html"]:
    if not (PUB/rel).is_file():raise RuntimeError("Missing published component: "+rel)
payload=[(p.relative_to(PUB).as_posix(),p) for part in ["Service","Control","Tray","Jobs"] for p in sorted((PUB/part).rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc",".pdb")]
if isolated:
    # These services cannot access the production pipe, manifests or downloads.
    # Keep the same directory layout, MSI actions, security and wizard code.
    fixture=compile_tool("Fixture.exe","Fixture.cs")
    payload=[(rel,fixture) for rel,_ in payload if rel in (
        "Service/Tlachihuani.Service.exe","Control/Tlachihuani.Control.exe",
        "Tray/Tlachihuani.Tray.exe","Jobs/Tlachihuani.Jobs.exe")]
for rel,p in payload+[("Setup/SetupIdentity.exe",guard)]:
    comp=component(directory(rel.rpartition("/")[0]),rel)
    fid=ident("F",rel)
    child(comp,"File",Id=fid,Name=rel.rpartition("/")[2],Source=str(p),KeyPath="yes")
    if rel in ("Service/Tlachihuani.Service.exe","Jobs/Tlachihuani.Jobs.exe"):
        name=NAME+(".Jobs" if rel.startswith("Jobs") else "")
        svc=child(comp,"ServiceInstall",Name=name,DisplayName=name,Type="ownProcess",Start="demand",ErrorControl="normal",Account="NT SERVICE\\"+name)
        child(comp,"ServiceControl",Name=name,Stop="uninstall",Remove="uninstall",Wait="yes")
tray="[#" + ident("F","Tray/Tlachihuani.Tray.exe")+"]"
for sd,label in [("ProgramMenuFolder",NAME+" XT"),("StartupFolder",NAME+" XT")]:
    c=component(child(pkg,"StandardDirectory",Id=sd),sd)
    child(c,"Shortcut",Id="Link"+sd,Name=label,Target=tray,WorkingDirectory=ident("D","Tray"),Icon="XTIcon")
    child(c,"RegistryValue",Root="HKLM",Key="Software\\XAIHT\\"+NAME+"\\Setup",Name=sd,Type="integer",Value="1",KeyPath="yes")
child(pkg,"Binary",Id="Guard",SourceFile=str(guard))
seq=child(pkg,"InstallExecuteSequence")
for name,mode,condition in [("InspectInstall","install","NOT Installed"),("InspectRepair","repair",'Installed AND NOT (REMOVE~="ALL")'),("InspectRemove","remove",'Installed AND REMOVE~="ALL"')]:
    child(pkg,"CustomAction",Id=name,BinaryRef="Guard",ExeCommand=mode+' [TLOPERATOR] "[appRoot]."',Execute="deferred",Impersonate="no",Return="check")
    child(seq,"Custom",Action=name,Before="StopServices",Condition=condition)
child(pkg,"CustomAction",Id="CreateIdentity",FileRef=ident("F","Setup/SetupIdentity.exe"),ExeCommand="state [TLOPERATOR]",Execute="deferred",Impersonate="no",Return="check")
child(seq,"Custom",Action="CreateIdentity",After="InstallServices",Condition='NOT (REMOVE~="ALL")')
wxs=WORK/"Package.wxs"
ET.ElementTree(xml).write(wxs,encoding="utf-8",xml_declaration=True)
msi=WORK/(NAME+".msi")
subprocess.run([str(ROOT/"artifacts/setup-tools/wix.exe"),"build","-arch","x64","-intermediatefolder",str(WORK/"obj"),"-o",str(msi),str(wxs)],check=True)
setup=compile_tool("Installer.exe","Wizard.cs","/resource:"+str(msi)+",package.msi")
import shutil
for p in (setup,remove):
    stage=OUT/(p.name+".new")
    shutil.copyfile(p,stage)
    stage.replace(OUT/p.name)
print(f"Built {NAME} {VERSION} for Windows x64 in {OUT}")
if isolated:
    (OUT.parent / "current.txt").write_text(OUT.name, encoding="ascii")
