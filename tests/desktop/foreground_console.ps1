$ErrorActionPreference='Stop'
. "$PSScriptRoot\..\..\scripts\Assert-Visible.ps1"
Assert-VisibleDevelopmentConsole -TimeoutSeconds 5
Write-Output 'PASS: actual foreground console accepted.'
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;
public class VisibleFocusFixture {
  public static readonly ManualResetEvent shown = new ManualResetEvent(false);
  [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  public static bool InFront;
  public static void Show() {
    IntPtr console=GetConsoleWindow();
    var thread=new Thread(delegate() {
      using (var form=new Form()) using (var timer=new System.Windows.Forms.Timer()) {
        form.Text="Torrenter visible test: checking foreground recovery";
        form.Width=530;form.Height=130;form.StartPosition=FormStartPosition.CenterScreen;
        form.Controls.Add(new Label { Text="This test window closes in four seconds. The updater must wait.",Dock=DockStyle.Fill,TextAlign=System.Drawing.ContentAlignment.MiddleCenter });
        form.Shown += delegate { form.Activate();SetForegroundWindow(form.Handle);InFront=GetForegroundWindow()==form.Handle;shown.Set();timer.Interval=4000;timer.Start(); };
        timer.Tick += delegate { timer.Stop();bool ours=GetForegroundWindow()==form.Handle;form.Close();if(ours)SetForegroundWindow(console); };
        Application.Run(form);
      }
    });
    thread.SetApartmentState(ApartmentState.STA);thread.Start();
  }
}
'@
[VisibleFocusFixture]::Show()
if(![VisibleFocusFixture]::shown.WaitOne(6000) -or ![VisibleFocusFixture]::InFront){throw 'The visible focus fixture did not become foreground.'}
$rejected=$false
try { Assert-VisibleDevelopmentConsole -TimeoutSeconds 1 }
catch { if($_.Exception.Message -like 'No verified foreground console.*'){$rejected=$true}else{throw} }
if (!$rejected){throw 'The guard accepted a different active window.'}
Write-Output 'PASS: another visible window in front did not authorize the workload.'
$wait=[Diagnostics.Stopwatch]::StartNew()
Assert-VisibleDevelopmentConsole -TimeoutSeconds 15
if($wait.ElapsedMilliseconds -lt 1000){throw 'The console was not gated through the focus transition.'}
Write-Output ("PASS: original console recovered automatically after "+$wait.ElapsedMilliseconds+" ms; no blind success or extra shell.")
