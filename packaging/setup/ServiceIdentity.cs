using System;
using System.ComponentModel;
using System.Security.AccessControl;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

// Configure and read back SERVICE_CONFIG_SERVICE_SID_INFO before any service may start.
internal static class ServiceIdentity {
    private sealed class ScHandle : SafeHandleZeroOrMinusOneIsInvalid {
        private ScHandle() : base(true) {}
        protected override bool ReleaseHandle(){return CloseServiceHandle(handle);}
    }
    [DllImport("advapi32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern ScHandle OpenSCManager(string machine,string database,uint access);
    [DllImport("advapi32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern ScHandle OpenService(ScHandle manager,string name,uint access);
    [DllImport("advapi32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool ChangeServiceConfig2(ScHandle service,uint level,ref uint value);
    [DllImport("advapi32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool QueryServiceConfig2(ScHandle service,uint level,out uint value,uint size,out uint needed);
    [DllImport("advapi32.dll")] static extern bool CloseServiceHandle(IntPtr handle);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetServiceObjectSecurity(ScHandle service,uint info,byte[] descriptor);
    internal static void Configure(string name,string operatorSid){
        using(var manager=OpenSCManager(null,null,1)){
            if(manager.IsInvalid)throw new Win32Exception();
            using(var service=OpenService(manager,name,0x40003)){
                if(service.IsInvalid)throw new Win32Exception();
                uint value=1,needed;
                if(!ChangeServiceConfig2(service,5,ref value)||!QueryServiceConfig2(service,5,out value,4,out needed))throw new Win32Exception();
                if(value!=1)throw new InvalidOperationException("Service SID configuration was not applied.");
                var acl=new RawSecurityDescriptor("D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;CCLCRPWPLORC;;;"+operatorSid+")");
                var bytes=new byte[acl.BinaryLength];
                acl.GetBinaryForm(bytes,0);
                if(!SetServiceObjectSecurity(service,4,bytes))throw new Win32Exception();
            }
        }
    }
}
