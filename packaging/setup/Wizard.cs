using System;
using System.Drawing;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class Wizard : Form {
    [DllImport("msi.dll",CharSet=CharSet.Unicode)] static extern int MsiQueryProductState(string product);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h,int attr,ref int value,int size);
    static readonly Color Bg=ColorTranslator.FromHtml("#0e111a"),Card=ColorTranslator.FromHtml("#1c2535"),Ink=ColorTranslator.FromHtml("#edf2fa"),Muted=ColorTranslator.FromHtml("#a6b4c9"),Teal=ColorTranslator.FromHtml("#79dfce"),Amber=ColorTranslator.FromHtml("#ffc08c");
    static readonly string Version=typeof(Wizard).Assembly.GetName().Version.ToString(3);
#if REMOVE
    static readonly bool Removing=true;
#else
    static readonly bool Removing=false;
#endif
    static string Verb { get {return Removing?"Uninstall":"Install";} }
    readonly Label stage=new Label(),heading=new Label(),detail=new Label(),notice=new Label();
    readonly Button next=new Button(),back=new Button();
    readonly ProgressBar progress=new ProgressBar();
    readonly CheckBox startup=new CheckBox();
    readonly string op=WindowsIdentity.GetCurrent().User.Value;
    int page;
    bool busy;
    bool installedSuccessfully;
    static bool Managed {get{return MsiQueryProductState(Product.Code)==5;}}
    static void Preflight(bool remove,string sid){
        if(remove && !Managed)throw new InvalidOperationException("This version was not installed by this setup package. For a script installation, follow the Windows packaging guide.");
        if(!remove && Managed)throw new InvalidOperationException("This version is already installed. Use Windows Installed apps for maintenance.");
        Ownership.Inspect(remove,Managed,sid);
    }
    static void LabelStyle(Label label,float size,Color color,bool bold){
        label.Font=new Font("Segoe UI",size,bold?FontStyle.Bold:FontStyle.Regular);
        label.ForeColor=color;label.AutoSize=true;label.Dock=DockStyle.Fill;label.Anchor=AnchorStyles.Left;
    }
    public Wizard(){
        Text=Product.Name+" "+Verb+" · "+Version; Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        BackColor=Bg;ForeColor=Ink;Font=new Font("Segoe UI",10);AutoScaleMode=AutoScaleMode.Dpi;
        StartPosition=FormStartPosition.CenterScreen;ClientSize=new Size(760,570);MinimumSize=new Size(740,605);
        var grid=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=8,Padding=new Padding(30,22,30,18)};
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        for(int i=0;i<8;i++)grid.RowStyles.Add(new RowStyle(i==3?SizeType.Percent:SizeType.AutoSize,i==3?100:0));
        Controls.Add(grid);
        var brand=new Label{Text="XAIHT    /    TLACHIHUANI     •     VERSION "+Version};LabelStyle(brand,10,Teal,true);grid.Controls.Add(brand,0,0);
        LabelStyle(stage,9,Muted,true);stage.Margin=new Padding(3,20,3,4);grid.Controls.Add(stage,0,1);
        LabelStyle(heading,21,Ink,true);grid.Controls.Add(heading,0,2);
        LabelStyle(detail,11,Ink,false);detail.BackColor=Card;detail.Padding=new Padding(16);detail.Anchor=AnchorStyles.None;detail.Dock=DockStyle.Fill;detail.Margin=new Padding(0,15,0,10);grid.Controls.Add(detail,0,3);
        startup.Text="Show XT at Windows sign-in (all users of this PC)";
        startup.AccessibleName=startup.Text;startup.Checked=true;startup.AutoSize=true;startup.Dock=DockStyle.Fill;
        startup.Margin=new Padding(3,4,3,14);startup.Visible=!Removing;grid.Controls.Add(startup,0,4);
        LabelStyle(notice,10,Muted,false);grid.Controls.Add(notice,0,5);
        progress.Dock=DockStyle.Top;progress.Height=5;progress.Margin=new Padding(0,12,0,10);grid.Controls.Add(progress,0,6);
        var buttons=new FlowLayoutPanel{AutoSize=true,Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft,WrapContents=false};grid.Controls.Add(buttons,0,7);
        foreach(var b in new[]{next,back}){b.AutoSize=true;b.Padding=new Padding(15,5,15,5);b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderSize=0;buttons.Controls.Add(b);}
        next.BackColor=Removing?Amber:Teal;next.ForeColor=Bg;back.BackColor=Card;back.ForeColor=Ink;
        AcceptButton=next;CancelButton=back;next.Click+=async delegate {await Advance();};
        back.Click+=delegate{
            if(busy)return;
            if(installedSuccessfully){
                try{
                    OpenTray();
                }catch(Exception ex){MessageBox.Show(this,ex.Message,"Open XT",MessageBoxButtons.OK,MessageBoxIcon.Error);return;}
            }
            Close();
        };
        FormClosing+=delegate(object sender,FormClosingEventArgs e){if(busy)e.Cancel=true;};
        Shown+=delegate{int on=1;DwmSetWindowAttribute(Handle,20,ref on,4);};
        stage.Text="01   /   OVERVIEW";heading.Text=Removing?"Remove the Windows services":"Set up your Windows services";
        detail.Text=Removing?"Remove the primary service, Jobs host, XT shortcuts and packaged program files.\n\nDownloaded files, installation identities and the Jobs journal stay on this PC.":"Install the primary service, Torrenter Jobs and the XT tray companion.\n\nServices stay stopped after installation and every reboot. Choose Start Services in XT when you need them.\n\nStart menu and Desktop shortcuts are always included.";
        notice.Text=Removing?"Windows x64    •    Per-machine installation":"Only the tray icon starts at sign-in. Services and downloads do not.";next.Text="Review";back.Text="Cancel";
    }
    static void OpenTray(){
        // Launch only from the original unelevated wizard, never its UAC helper.
        // No lifecycle command is sent: TrayContext starts with status polling.
        Process.Start(new ProcessStartInfo(Path.Combine(Ownership.Program,"Tray","Tlachihuani.Tray.exe")){UseShellExecute=true});
    }
    async Task Advance(){
        if(busy)return;
        if(page==2){Close();return;}
        if(page==0){
            page=1;stage.Text="02   /   REVIEW";heading.Text=Removing?"Review removal":"Review installation";
            startup.Visible=false;
            detail.Text="Location\n"+Ownership.Program+"\n\nWindows operator\n"+WindowsIdentity.GetCurrent().Name;
            if(!Removing)detail.Text+="\n\nXT at sign-in: "+(startup.Checked?"Yes, for all users":"No")+"\nStart menu and Desktop shortcuts: Yes\nServices after setup / reboot: Stopped (Manual)";
            try{Preflight(Removing,op);notice.Text="Windows will request administrator access when you continue.";next.Text=Verb;}
            catch(Exception ex){stage.Text="02   /   ACTION REQUIRED";notice.Text=ex.Message;next.Text="Close";page=2;}
            return;
        }
        busy=true;next.Enabled=back.Enabled=false;progress.Style=ProgressBarStyle.Marquee;stage.Text="03   /   APPLY";heading.Text=Removing?"Removing components…":"Installing components…";
        string log=null;
        try{
            string stamp=Guid.NewGuid().ToString("N");
            log=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"Logs","Tlachihuani-"+stamp+".log");
            var start=new ProcessStartInfo(Application.ExecutablePath,"--apply "+op+" "+stamp+" "+(startup.Checked?"1":"0")){UseShellExecute=true,Verb="runas"};
            int rc=await Task.Run(delegate{using(var child=Process.Start(start)){child.WaitForExit();return child.ExitCode;}});
            if(rc!=0 && rc!=3010)throw new InvalidOperationException("Windows setup returned "+rc+".");
            if(Managed==Removing)throw new InvalidOperationException("Windows did not confirm the requested installation state.");
            heading.Text=Removing?"Removal complete":"Installation complete";
            installedSuccessfully=!Removing && rc==0;
            detail.Text=Removing?"The services and packaged files have been removed. Your downloads and job history were preserved.":"Both services are stopped. Right-click the gray XT icon and choose Start Services when you need them.\n\nReopen XT any time from Start or your Desktop.\n\n"+(startup.Checked?"XT will appear at Windows sign-in; services remain stopped after reboot.":"Automatic XT startup is off. Open XT yourself after signing in.");
            notice.Text=rc==3010?"Restart Windows to finish.":"Installation log: "+log;
            if(installedSuccessfully){
                bool elevated=new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);
                if(!elevated){
                    try{OpenTray();}
                    catch(Exception ex){detail.Text+="\n\nXT could not open: "+ex.Message+" Use the Desktop shortcut to retry.";}
                }else detail.Text+="\n\nThis wizard is elevated. Open XT from your normal Desktop session.";
            }
        }catch(Exception ex){heading.Text="Setup did not finish";detail.Text=ex.Message;notice.Text=log==null?"Close and retry when ready.":"If installation began, see "+log;}
        finally{
            busy=false;page=2;stage.Text="04   /   RESULT";progress.Style=ProgressBarStyle.Blocks;progress.Value=100;
            // Keep XT in the original, unelevated operator session. If someone
            // started the whole wizard as administrator, direct them to Start.
            bool elevated=new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);
            back.Visible=installedSuccessfully && !elevated;back.Enabled=back.Visible;back.Text="Open XT";
            next.Enabled=true;next.Text="Finish";
        }
    }
    static int Apply(string sid,string stamp,string trayStartup){
        new SecurityIdentifier(sid); Guid.ParseExact(stamp,"N");
        if(trayStartup!="0" && trayStartup!="1")return 87;
        if(!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator))return 5;
        Preflight(Removing,sid);
        string log=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"Logs","Tlachihuani-"+stamp+".log");
        string scratch=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"Installer","Tlachihuani-"+stamp);
        var permissions=new System.Security.AccessControl.DirectorySecurity();
        permissions.SetSecurityDescriptorSddlForm("O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)");
        Directory.CreateDirectory(scratch,permissions);
        Environment.SetEnvironmentVariable("TEMP",scratch);
        Environment.SetEnvironmentVariable("TMP",scratch);
        string pkg=Path.Combine(scratch,"payload.msi");
        try{
            string args="/x "+Product.Code;
            if(!Removing){
                using(var payload=typeof(Wizard).Assembly.GetManifestResourceStream("package.msi"))
                using(var file=new FileStream(pkg,FileMode.CreateNew,FileAccess.Write,FileShare.None))payload.CopyTo(file);
                args="/i \""+pkg+"\" TLOPERATOR="+sid+" TLTRAYSTARTUP="+trayStartup;
            }
            using(var proc=Process.Start(new ProcessStartInfo(Path.Combine(Environment.SystemDirectory,"msiexec.exe"),args+" /qn /norestart /L*v \""+log+"\""){UseShellExecute=false})){proc.WaitForExit();return proc.ExitCode;}
        }finally{
            // Preserve the real MSI result if Windows still holds a staging file.
            try{if(File.Exists(pkg))File.Delete(pkg);Directory.Delete(scratch,false);}
            catch(IOException){}catch(UnauthorizedAccessException){}
        }
    }
    [STAThread] static int Main(string[] args){
        try{
            if(args.Length==4 && args[0]=="--apply")return Apply(args[1],args[2],args[3]);
            if(args.Length!=0)return 87;
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Wizard());return 0;
        }catch(Exception e){MessageBox.Show(e.Message,Product.Name+" setup",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1603;}
    }
}
