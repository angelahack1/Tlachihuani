// Tlachihuani — Angela López Mendoza · XAIHT
using System.Diagnostics;
using System.Text.Json.Nodes;
using Tlachihuani.Core;
using Tlachihuani.Windows;

namespace Tlachihuani.Tray;

internal sealed class ServicesForm : Form
{
    private readonly Label status = new() { AutoSize = true };
    private readonly TextBox pair = new() { Width = 115, MaxLength = 8, PlaceholderText = "8-digit code" };
    private readonly FlowLayoutPanel actions = Row();
    private readonly FlowLayoutPanel machine = Row();
    private readonly CancellationTokenSource closing = new();
    private readonly System.Windows.Forms.Timer timer = new() { Interval = 4000 };
    private bool busy;
    private string impact = "";
    private readonly Dictionary<string, Button> buttons = new();

    public ServicesForm(Icon icon)
    {
        Icon = icon; Text = "Tlachihuani · Services"; Font = new Font("Segoe UI", 10);
        BackColor = Color.FromArgb(31,49,58); ForeColor = Color.WhiteSmoke;
        ClientSize = new Size(730, 475); MinimumSize = new Size(620, 490); StartPosition = FormStartPosition.CenterParent;
        var body = new FlowLayoutPanel { Dock=DockStyle.Fill, FlowDirection=FlowDirection.TopDown, WrapContents=false, AutoScroll=true, Padding=new Padding(18) };
        body.Controls.Add(Heading("Services")); body.Controls.Add(status);
        Button(machine,"Start Jobs",()=>HostAction("start")); Button(machine,"Stop Jobs",()=>HostAction("stop"));
        body.Controls.Add(machine); body.Controls.Add(Heading("Torrenter"));
        Button(actions,"Start provider",()=>Provider("start")); Button(actions,"Stop provider",()=>Provider("stop"));
        Button(actions,"Restart provider",()=>Provider("restart")); Button(actions,"Restart web",()=>Call(new(){["op"]="restart-web"})); Button(actions,"Open workspace",OpenWorkspace);
        body.Controls.Add(actions);
        body.Controls.Add(new Label { Text="Browser pairing · enter the code shown by your local transfer workspace", AutoSize=true });
        var pairing=Row(); pairing.Controls.Add(pair);
        var profile=new TextBox{Width=190,PlaceholderText="Account (optional)"};pairing.Controls.Add(profile); Button(pairing,"Approve code",async()=>{
            var code=pair.Text.Trim();
            if(code.Length!=8 || !code.All(char.IsAsciiDigit)) throw new ArgumentException("Enter the eight digits shown in the browser.");
            await Call(new(){["op"]="approve",["code"]=code,["profile"]=profile.Text.Trim()}); pair.Clear(); MessageBox.Show(this,"The matching browser may now redeem its session.","Pairing approved");
        }); body.Controls.Add(pairing);
        var credentials=Row();
        Button(credentials,"Review erasure",ReviewDeletion); Button(credentials,"Issue API credential",Issue);
        Button(credentials,"Revoke access",async()=>{if(Confirm("Revoke all REST sessions and enrolled gateways for your Windows account?"))await Call(new(){["op"]="revoke"});});
        body.Controls.Add(credentials);
        var bottom=Row(); Button(bottom,"Refresh",()=>Task.CompletedTask);
        var close=new Button {Text="Close",AutoSize=true};close.Click+=(_,_)=>Close();bottom.Controls.Add(close); body.Controls.Add(bottom);
        Controls.Add(body);
        timer.Tick+=async (_,_)=>await Run(()=>Task.CompletedTask);
        Shown+=async (_,_)=>{await Run(()=>Task.CompletedTask);timer.Start();};
        FormClosed+=(_,_)=>{timer.Stop();closing.Cancel();};
    }
    private static FlowLayoutPanel Row()=>new(){AutoSize=true,WrapContents=true,MaximumSize=new Size(680,0),Margin=new Padding(0,6,0,9)};
    private static Label Heading(string text)=>new(){Text=text,Font=new Font("Segoe UI",16,FontStyle.Bold),AutoSize=true};
    private void Button(FlowLayoutPanel row,string caption,Func<Task> action)
    {
        var button=new Button{Text=caption,AutoSize=true,FlatStyle=FlatStyle.Flat,ForeColor=Color.WhiteSmoke,BackColor=Color.FromArgb(48,75,79)};
        button.Click+=async (_,_)=>await Run(action);
        row.Controls.Add(button);buttons.Add(caption,button);
    }
    private bool Confirm(string text)=>MessageBox.Show(this,text,"Tlachihuani · Confirm",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)==DialogResult.Yes;
    private async Task Run(Func<Task> action)
    {
        if(busy || closing.IsCancellationRequested)return;
        busy=true;
        try { await action(); if(!closing.IsCancellationRequested)await RefreshState(); }
        catch(Exception ex) when(ex is not OutOfMemoryException){if(!closing.IsCancellationRequested)status.Text=ex.Message;}
        finally{busy=false;}
    }
    private async Task<JsonObject> Call(JsonObject request)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(closing.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(8));
        var result=await Task.Run(async ()=>{
            var install=JobsInstallation.Load();var scm=ScmBackend.ForJobs();scm.ValidateJobsInstallation();
            return await JobsEndpoint.CallAsync(JobsEndpoint.Pipe(install),scm.Query().Pid,JobsInstallation.Image,request,timeout.Token);
        },timeout.Token);
        if(result["code"] is JsonValue code && code.GetValue<int>()>=400) throw new InvalidOperationException((string?)result["body"]?["error"]);
        return result["body"]?.AsObject() ?? result;
    }
    private async Task RefreshState()
    {
        var state=await Task.Run(()=>ScmBackend.ForJobs().Query(),closing.Token);
        if(closing.IsCancellationRequested)return;
        bool running=state.State=="running";
        buttons["Start Jobs"].Enabled=state.State=="stopped";buttons["Stop Jobs"].Enabled=running;
        foreach(var key in new[]{"Start provider","Stop provider","Restart provider","Restart web","Open workspace","Approve code","Review erasure","Issue API credential","Revoke access"})buttons[key].Enabled=false;
        status.Text=state.State=="not_installed"?"Jobs is not installed. Use the Windows Jobs installer.":"Windows Jobs host · "+state.State;
        if(!running)return;
        var catalog=await Call(new(){["op"]="catalog"});if(closing.IsCancellationRequested)return;
        var result=catalog["providers"]!.AsArray().First(item=>(string?)item?["provider"]=="torrenter")!;
        impact=result["impact"] is JsonObject counts ? $" {counts["active"]} active transfers across {counts["records"]} records." : "";
        bool enabled=(bool?)result["enabled"]==true, engine=(bool?)result["engine"]==true, web=(bool?)result["web"]==true;
        status.Text=$"Windows Jobs host · running     Torrenter · {(enabled?"enabled":"stopped")}     Engine · {(engine?"ready":"offline")}     Web · {(web?"ready":"offline")}{Environment.NewLine}{impact.Trim()}";
        buttons["Start provider"].Enabled=!enabled;buttons["Stop provider"].Enabled=enabled;buttons["Restart provider"].Enabled=enabled;
        buttons["Restart web"].Enabled=enabled;buttons["Open workspace"].Enabled=web;buttons["Approve code"].Enabled=web;
        foreach(var key in new[]{"Review erasure","Issue API credential","Revoke access"})buttons[key].Enabled=engine;
    }
    private async Task HostAction(string op)
    {
        if(op=="stop"&&!Confirm("Stop the Jobs host and checkpoint all its providers?"+impact))return;
        await Task.Run(async()=>{var scm=ScmBackend.ForJobs();scm.ValidateJobsInstallation();await new Lifecycle(scm).ExecuteAsync(op,TimeSpan.FromSeconds(30),closing.Token);});
    }
    private async Task Provider(string op)
    {
        if(op!="start"&&!Confirm(op+" Torrenter and checkpoint its active transfers?"+impact))return;
        await Call(new(){["op"]=op});
    }
    private async Task OpenWorkspace()
    {
        var current=await Call(new(){["op"]="status"});
        if((bool?)current["web"]!=true)throw new InvalidOperationException("The workspace is offline.");
        Process.Start(new ProcessStartInfo("http://127.0.0.1:12064/"){UseShellExecute=true});
    }
    private async Task Issue()
    {
        using var dialog=new Form{Text="Torrenter · API access",Size=new Size(480,240),StartPosition=FormStartPosition.CenterParent};
        var panel=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,Padding=new Padding(12)};
        var profile=new TextBox{Width=350,PlaceholderText="Optional application account (blank = your Windows profile)"};
        var scope=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=350};
        scope.Items.AddRange(["read","read submit control","read submit control remove erase"]);scope.SelectedIndex=0;
        var okay=new Button{Text="Issue token",AutoSize=true,DialogResult=DialogResult.OK};
        panel.Controls.AddRange([new Label{Text="Account and permissions · expires in one hour",AutoSize=true},profile,scope,okay]);dialog.Controls.Add(panel);
        if(dialog.ShowDialog(this)!=DialogResult.OK)return;
        var result=await Call(new(){["op"]="issue",["profile"]=profile.Text.Trim(),["scope"]=scope.Text});
        using var secret=new Form{Text="Torrenter · Copy credential",Size=new Size(540,145),StartPosition=FormStartPosition.CenterParent};
        var field=new TextBox{Text=(string?)result["access_token"],ReadOnly=true,Dock=DockStyle.Top};secret.Controls.Add(field);secret.ShowDialog(this);
    }
    private async Task ReviewDeletion()
    {
        var pending=await Call(new(){["op"]="pending-deletions"});
        var items=pending["items"]!.AsArray();
        if(items.Count==0){MessageBox.Show(this,"There are no pending file-erasure requests.","Torrenter");return;}
        foreach(var item in items){
            var preview=await Call(new(){["op"]="deletion-details",["preview_id"]=(string?)item!["preview_id"]});
            using var dialog=new Form{Text="Review exact files for erasure",Size=new Size(660,440),StartPosition=FormStartPosition.CenterParent};
            var review=new TextBox{Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Both,WordWrap=false,
                Text="Job "+(string?)preview["job_id"]+Environment.NewLine+string.Join(Environment.NewLine,preview["files"]!.AsArray().Select(x=>$"{x!["bytes"]} bytes   {x["path"]}"))};
            var approve=new Button{Text="Authorize erasure of these files",Dock=DockStyle.Bottom,DialogResult=DialogResult.Yes};
            var decline=new Button{Text="Close without approval",Dock=DockStyle.Bottom,DialogResult=DialogResult.Cancel};
            dialog.Controls.AddRange([review,approve,decline]);dialog.CancelButton=decline;
            if(dialog.ShowDialog(this)==DialogResult.Yes)await Call(new(){["op"]="approve-delete",["preview_id"]=(string?)item["preview_id"],["manifest_digest"]=(string?)preview["manifest_digest"]});
        }
    }
    protected override void Dispose(bool disposing){if(disposing){timer.Dispose();closing.Dispose();}base.Dispose(disposing);}
}
