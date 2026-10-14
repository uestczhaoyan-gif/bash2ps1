"""Windows native stderr merging through one OS pipe, without cmd/Bash wrappers."""
NATIVE_RUNTIME = r'''
function Initialize-B2PSMergedNative {
    if ('B2PS.NativeMerged' -as [type]) { return }
    $source=@'
using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using System.ComponentModel;
using Microsoft.Win32.SafeHandles;
namespace B2PS {
 public static class NativeMerged {
  [StructLayout(LayoutKind.Sequential)] struct SA { public int Length; public IntPtr Descriptor; [MarshalAs(UnmanagedType.Bool)] public bool Inherit; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct SI {
   public int cb; public string Reserved; public string Desktop; public string Title;
   public int X,Y,XSize,YSize,XCount,YCount,Fill,Flags; public short Show,ReservedSize;
   public IntPtr ReservedPointer,Input,Output,Error;
  }
  [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr Process,Thread; public int ProcessId,ThreadId; }
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SA security,int size);
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool SetHandleInformation(IntPtr handle,int mask,int flags);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CreateProcess(string application,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,int flags,IntPtr environment,string directory,ref SI startup,out PI process);
  [DllImport("kernel32.dll")] static extern int WaitForSingleObject(IntPtr handle,int milliseconds);
  [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool GetExitCodeProcess(IntPtr handle,out int code);
  [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int number);
  [DllImport("kernel32.dll")] [return:MarshalAs(UnmanagedType.Bool)] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool SetEnvironmentVariable(string name,string value);
  public static void RemoveEnvironment(string name) { if(!SetEnvironmentVariable(name,null))throw new Win32Exception(); }
  public static void SetEnvironment(string name,string value) { if(!SetEnvironmentVariable(name,value))throw new Win32Exception(); }
  static void Close(ref IntPtr h) { if(h!=IntPtr.Zero && h!=new IntPtr(-1)){CloseHandle(h);h=IntPtr.Zero;} }
  public static int Run(string file,string arguments,string directory,Stream input,Stream output) {
   IntPtr read=IntPtr.Zero,write=IntPtr.Zero,inputRead=IntPtr.Zero,inputWrite=IntPtr.Zero;
   PI pi=new PI(); FileStream reader=null,writer=null;
   try {
    SA sa=new SA { Length=Marshal.SizeOf(typeof(SA)), Inherit=true };
    if(!CreatePipe(out read,out write,ref sa,0))throw new Win32Exception();
    if(!SetHandleInformation(read,1,0))throw new Win32Exception();
    IntPtr childInput=GetStdHandle(-10);
    if(input!=null || childInput==IntPtr.Zero || childInput==new IntPtr(-1)) {
     if(!CreatePipe(out inputRead,out inputWrite,ref sa,0))throw new Win32Exception();
     if(!SetHandleInformation(inputWrite,1,0))throw new Win32Exception();
     childInput=inputRead;
    }
    SI si=new SI { cb=Marshal.SizeOf(typeof(SI)), Flags=0x100, Input=childInput, Output=write, Error=write };
    StringBuilder command=new StringBuilder("\""+file+"\" "+arguments);
    if(!CreateProcess(file,command,IntPtr.Zero,IntPtr.Zero,true,0x08000000,IntPtr.Zero,directory,ref si,out pi))throw new Win32Exception();
    Close(ref write);Close(ref inputRead);Close(ref pi.Thread);
    reader=new FileStream(new SafeFileHandle(read,true),FileAccess.Read);read=IntPtr.Zero;
    FileStream readStream=reader;
    Task drain=Task.Run(()=>readStream.CopyTo(output));
    Task feed=null;
    if(inputWrite!=IntPtr.Zero) {
     writer=new FileStream(new SafeFileHandle(inputWrite,true),FileAccess.Write);inputWrite=IntPtr.Zero;
     FileStream writeStream=writer;
     feed=Task.Run(()=>{try{if(input!=null)input.CopyTo(writeStream);}catch(IOException){}finally{writeStream.Dispose();}});
    }
    WaitForSingleObject(pi.Process,-1);
    drain.GetAwaiter().GetResult();if(feed!=null)feed.GetAwaiter().GetResult();output.Flush();
    int code;if(!GetExitCodeProcess(pi.Process,out code))throw new Win32Exception();return code;
   } finally {
    if(reader!=null)reader.Dispose();if(writer!=null)writer.Dispose();
    Close(ref read);Close(ref write);Close(ref inputRead);Close(ref inputWrite);Close(ref pi.Thread);Close(ref pi.Process);
   }
  }
 }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}
'''
