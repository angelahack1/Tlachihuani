using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Diagnostics;
internal static class Guard {
    [DllImport("msi.dll",CharSet=CharSet.Unicode)] static extern int MsiQueryProductState(string product);
    static int Main(string[] args){
        try{
            if(args.Length==2 && args[0]=="state") Ownership.Provision(args[1]);
            else if(args.Length==3 && (args[0]=="install"||args[0]=="repair"||args[0]=="remove")){
                if(!String.Equals(Ownership.Program,Path.GetFullPath(args[2]).TrimEnd('\\'),StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Unexpected install root.");
                // Windows Installer selects the action from its own Installed/REMOVE
                // state. A deferred LocalSystem process cannot infer that transaction
                // state by querying its own interactive user's product registration.
                Ownership.Inspect(args[0]=="remove",args[0]!="install",args[1]);
            }else return 87;
            return 0;
        }catch(Exception ex){
            string message=Product.Name+" setup: "+ex.Message;
            try{File.WriteAllText(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"Logs",
                Product.Name+"-identity-"+Guid.NewGuid().ToString("N")+".log"),message);}
            catch(IOException){}catch(UnauthorizedAccessException){}
            Console.Error.WriteLine(message);return 1;
        }
    }
}
