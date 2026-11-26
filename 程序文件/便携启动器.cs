using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using System.Reflection;
[assembly:AssemblyTitle("施工方案 AI 审查")]
[assembly:AssemblyProduct("施工方案 AI 审查客户端")]
class Launcher {
 [STAThread] static int Main() {
  try {
   AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
   AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
   string root=AppDomain.CurrentDomain.BaseDirectory;
   string app=Path.Combine(root,"程序文件");
   var start=new ProcessStartInfo(Path.Combine(app,@"运行库\pythonw.exe"),"-B -X utf8 "+(char)34+Path.Combine(app,"桌面客户端_v4.py")+(char)34);
   start.WorkingDirectory=root; start.UseShellExecute=false; start.CreateNoWindow=true;
   using(var process=Process.Start(start)){process.WaitForExit();return process.ExitCode;}
  } catch(Exception){MessageBox.Show("客户端启动失败，请完整解压后从程序目录启动。","施工方案 AI 审查");return 1;}
 }
}
