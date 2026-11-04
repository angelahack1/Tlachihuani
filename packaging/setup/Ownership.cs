using System;
using System.IO;
using System.Linq;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using Microsoft.Win32;
using System.Diagnostics;

internal static class Ownership {
    internal static readonly string Program = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "XAIHT", Product.Name);
    internal static readonly string Common = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "XAIHT");
    internal static string Image(bool jobs) { return Path.Combine(Program, jobs ? "Jobs" : "Service", jobs ? "Tlachihuani.Jobs.exe" : "Tlachihuani.Service.exe"); }
    internal static string Name(bool jobs) { return Product.Name + (jobs ? ".Jobs" : ""); }
    static void Plain(string path) {
        for (var d = new DirectoryInfo(path); d != null; d = d.Parent) {
            try { if ((File.GetAttributes(d.FullName) & FileAttributes.ReparsePoint) != 0) throw new InvalidOperationException("A redirected path cannot be used: " + d.FullName); }
            catch (DirectoryNotFoundException) {} catch (FileNotFoundException) {}
        }
    }
    internal static void Inspect(bool remove, bool managed, string operatorSid) {
        Plain(Program); Plain(Common);
        string tray=Path.Combine(Program,"Tray","Tlachihuani.Tray.exe");
        if(!remove) foreach(var candidate in Process.GetProcessesByName("Tlachihuani.Tray")) using(candidate){
            try{
                if(!remove && String.Equals(candidate.MainModule.FileName,tray,StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Choose Exit tray in XT before continuing.");
            }catch(System.ComponentModel.Win32Exception){throw new InvalidOperationException("Could not verify the running XT tray. Close XT in other signed-in sessions and retry.");}
        }
        if (!remove && !managed && Directory.Exists(Program)) throw new InvalidOperationException("This program folder already exists. Use the existing installation's maintenance tools. Setup will not overwrite it.");
        foreach (bool jobs in new[]{false,true}) {
            string name=Name(jobs);
            using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+name)) {
                if(k!=null) {
                    if(!managed || !String.Equals((string)k.GetValue("ImagePath"),"\""+Image(jobs)+"\"",StringComparison.OrdinalIgnoreCase) ||
                       !String.Equals((string)k.GetValue("ObjectName"),@"NT SERVICE\"+name,StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("The existing "+name+" registration belongs to a different installation. Use its original maintenance tools.");
                    using(var svc=new ServiceController(name)) if(!remove && svc.Status!=ServiceControllerStatus.Stopped)
                        throw new InvalidOperationException("Choose XT → Stop Services, then Exit tray before continuing.");
                }
            }
            string data=Path.Combine(Common,name);
            Plain(data);
            if(!remove && Directory.Exists(data)) CheckExisting(data,jobs,operatorSid);
            if(remove && managed && Directory.Exists(data)) CheckExisting(data,jobs,null);
        }
        // Self-contained published payloads are verified by the package builder.
        // MSI ServiceControl stops the services during removal; Restart Manager
        // handles locked applications. Do not reject a normal Control Panel /x
        // because the services are still running before StopServices executes.
    }
    static DirectorySecurity Permissions(string service,string op,bool state) {
        var acl=new DirectorySecurity();
        string rights=state ? "(A;OICI;0x1301bf;;;"+service+")" : "(A;OICI;GRGX;;;"+service+")(A;OICI;GRGX;;;"+op+")";
        acl.SetSecurityDescriptorSddlForm("O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"+rights);
        return acl;
    }
    static void Trusted(string path,bool sharedParent=false) {
        Plain(path);
        var acl=Directory.GetAccessControl(path);
        var owner=acl.GetOwner(typeof(SecurityIdentifier)).Value;
        if(owner!="S-1-5-18" && owner!="S-1-5-32-544") throw new InvalidOperationException("Unexpected owner of "+path);
        foreach(FileSystemAccessRule r in acl.GetAccessRules(true,true,typeof(SecurityIdentifier))) {
            if(r.AccessControlType!=AccessControlType.Allow || (r.PropagationFlags & PropagationFlags.InheritOnly)!=0)continue;
            string id=r.IdentityReference.Value;
            // ProgramData's shared vendor directory may grant create-child rights.
            // It must not grant replacement of an existing protected child.
            var unsafeRights=FileSystemRights.Delete|FileSystemRights.DeleteSubdirectoriesAndFiles|FileSystemRights.ChangePermissions|FileSystemRights.TakeOwnership;
            if(!sharedParent)unsafeRights|=FileSystemRights.Write;
            if(id!="S-1-5-18" && id!="S-1-5-32-544" && (r.FileSystemRights & unsafeRights)!=0)
                throw new InvalidOperationException("Untrusted write access on "+path);
        }
    }
    static void CheckExisting(string data,bool jobs,string op) {
        Trusted(data);
        var marker=Path.Combine(data,"setup-owner.txt"); var manifest=Path.Combine(data,"installation.json");
        Plain(marker);Plain(manifest);
        if(!File.Exists(marker)||File.ReadAllText(marker)!=Product.Family || !File.Exists(manifest))
            throw new InvalidOperationException("Unmanaged or incomplete installation state at "+data+". Preserve it for recovery.");
        var doc=new JavaScriptSerializer().Deserialize<Dictionary<string,string>>(File.ReadAllText(manifest));
        Guid id;
        if(!Guid.TryParse(doc["installation_id"],out id)||id==Guid.Empty||(op!=null && doc["operator_sid"]!=op) ||
           (!jobs&&!String.Equals(doc["service_path"],Image(false),StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("Retained state belongs to a different operator or installation.");
    }
    internal static void Provision(string op) {
        var sid=new SecurityIdentifier(op);
        if(!sid.IsAccountSid())throw new InvalidOperationException("A Windows operator account is required.");
        Plain(Common);
        if(!Directory.Exists(Common)) Directory.CreateDirectory(Common,Permissions("S-1-5-32-545",op,false));
        Trusted(Common,true);
        foreach(bool jobs in new[]{false,true}) {
            string name=Name(jobs), data=Path.Combine(Common,name);
            ServiceIdentity.Configure(name,op);
            string svc=((SecurityIdentifier)new NTAccount(@"NT SERVICE\"+name).Translate(typeof(SecurityIdentifier))).Value;
            Plain(data);
            if(Directory.Exists(data)) CheckExisting(data,jobs,op);
            else {
                string stage=Path.Combine(Common,".setup-"+Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(stage,Permissions(svc,op,false));
                var doc=new Dictionary<string,string>{{"installation_id",Guid.NewGuid().ToString()},{"operator_sid",op}};
                if(!jobs)doc["service_path"]=Image(false);
                File.WriteAllText(Path.Combine(stage,"installation.json"),new JavaScriptSerializer().Serialize(doc));
                File.WriteAllText(Path.Combine(stage,"setup-owner.txt"),Product.Family);
                if(jobs)Directory.CreateDirectory(Path.Combine(stage,"state"),Permissions(svc,op,true));
                Directory.Move(stage,data);
            }
        }
    }
}
