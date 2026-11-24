// N152 Windows phase 0: read-only probes (windows, UI Automation, capture, integrity, injected input).
// C# 5 (PowerShell 5.1 Add-Type): no string interpolation, no out var.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Automation;
using System.Windows.Forms;

public class Win {
    public long H { get; set; }
    public int Pid { get; set; }
    public string Title { get; set; }
    public string Cls { get; set; }
}

public class El {
    public string Type { get; set; }
    public string Name { get; set; }
    public string Aid { get; set; }
    public string Cls { get; set; }
    public int Depth { get; set; }
    public bool Pw { get; set; }
    public bool Enabled { get; set; }
    public bool Offscreen { get; set; }
}

public static class W0 {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, string l, uint flags, uint timeout, out IntPtr res);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(uint a, bool inh, int pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool ReadProcessMemory(IntPtr p, IntPtr addr, byte[] buf, int n, out IntPtr read);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);

    delegate IntPtr LLProc(int n, IntPtr w, IntPtr l);
    [DllImport("user32.dll", SetLastError = true)] static extern IntPtr SetWindowsHookEx(int id, LLProc fn, IntPtr mod, uint tid);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h, int n, IntPtr w, IntPtr l);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr GetModuleHandle(string n);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [StructLayout(LayoutKind.Sequential)] struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam, lParam; public uint time; public int x, y; }
    [DllImport("user32.dll")] static extern int GetMessage(out MSG m, IntPtr h, uint a, uint b);
    [DllImport("user32.dll")] static extern bool PostThreadMessage(uint tid, uint m, IntPtr w, IntPtr l);
    [StructLayout(LayoutKind.Sequential)] struct KBDLL { public uint vk, scan, flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint data, flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Explicit)] struct INPUT {
        [FieldOffset(0)] public uint type;
        [FieldOffset(8)] public KEYBDINPUT ki;
        [FieldOffset(8)] public MOUSEINPUT mi;
    }
    [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] i, int size);
    [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cb; public uint t; }
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO l);

    public static void DpiAware() { SetProcessDPIAware(); }

    public static List<Win> Top() {
        List<Win> r = new List<Win>();
        EnumWindows(delegate(IntPtr h, IntPtr l) {
            if (!IsWindowVisible(h)) return true;
            StringBuilder sb = new StringBuilder(512); GetWindowText(h, sb, 512);
            StringBuilder cb = new StringBuilder(256); GetClassName(h, cb, 256);
            uint pid; GetWindowThreadProcessId(h, out pid);
            Win w = new Win(); w.H = h.ToInt64(); w.Pid = (int)pid; w.Title = sb.ToString(); w.Cls = cb.ToString();
            r.Add(w);
            return true;
        }, IntPtr.Zero);
        return r;
    }

    public static Win Find(string pat) {
        Regex re = new Regex(pat);
        foreach (Win w in Top()) if (re.IsMatch(w.Title)) return w;
        return null;
    }

    public static void Close(long h) { PostMessage(new IntPtr(h), 0x0010, IntPtr.Zero, IntPtr.Zero); }

    public static List<El> Walk(long h, int max, int maxDepth) {
        List<El> res = new List<El>();
        AutomationElement root = AutomationElement.FromHandle(new IntPtr(h));
        TreeWalker w = TreeWalker.ControlViewWalker;
        Stack<KeyValuePair<AutomationElement, int>> st = new Stack<KeyValuePair<AutomationElement, int>>();
        st.Push(new KeyValuePair<AutomationElement, int>(root, 0));
        while (st.Count > 0 && res.Count < max) {
            KeyValuePair<AutomationElement, int> p = st.Pop();
            AutomationElement e = p.Key;
            try {
                AutomationElement.AutomationElementInformation c = e.Current;
                El d = new El();
                d.Type = c.ControlType.ProgrammaticName.Replace("ControlType.", "");
                d.Name = c.Name; d.Aid = c.AutomationId; d.Cls = c.ClassName; d.Depth = p.Value;
                d.Pw = c.IsPassword; d.Enabled = c.IsEnabled; d.Offscreen = c.IsOffscreen;
                res.Add(d);
            } catch (Exception) { continue; }
            if (p.Value >= maxDepth) continue;
            List<AutomationElement> kids = new List<AutomationElement>();
            try {
                AutomationElement k = w.GetFirstChild(e);
                while (k != null) { kids.Add(k); k = w.GetNextSibling(k); }
            } catch (Exception) { }
            for (int i = kids.Count - 1; i >= 0; i--) st.Push(new KeyValuePair<AutomationElement, int>(kids[i], p.Value + 1));
        }
        return res;
    }

    public static string UiaSet(long h, string aid, string val) {
        try {
            AutomationElement root = AutomationElement.FromHandle(new IntPtr(h));
            AutomationElement e = root.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.AutomationIdProperty, aid));
            if (e == null) return "notfound";
            object p;
            if (!e.TryGetCurrentPattern(ValuePattern.Pattern, out p)) return "nopattern";
            ((ValuePattern)p).SetValue(val);
            return "ok";
        } catch (Exception x) { return "exc:" + x.GetType().Name + ":" + x.Message; }
    }

    public static string MsgSet(long h, string val) {
        IntPtr target = IntPtr.Zero;
        EnumChildWindows(new IntPtr(h), delegate(IntPtr c, IntPtr l) {
            StringBuilder cb = new StringBuilder(256); GetClassName(c, cb, 256);
            if (cb.ToString().ToUpper().Contains("EDIT")) { target = c; return false; }
            return true;
        }, IntPtr.Zero);
        if (target == IntPtr.Zero) return "noedit";
        IntPtr res;
        IntPtr r = SendMessageTimeout(target, 0x000C, IntPtr.Zero, val, 0x2, 2000, out res);
        return string.Format("ret={0} err={1} res={2}", r, Marshal.GetLastWin32Error(), res);
    }

    public static string ReadMZ(int pid) {
        IntPtr p = OpenProcess(0x0410, false, pid);
        if (p == IntPtr.Zero) return "open_fail " + Marshal.GetLastWin32Error();
        try {
            IntPtr b = Process.GetProcessById(pid).MainModule.BaseAddress;
            byte[] buf = new byte[2]; IntPtr n;
            bool ok = ReadProcessMemory(p, b, buf, 2, out n);
            return ok ? ("read " + (char)buf[0] + (char)buf[1]) : ("read_fail " + Marshal.GetLastWin32Error());
        } catch (Exception x) { return "exc " + x.Message; }
        finally { CloseHandle(p); }
    }

    static double Mag(Bitmap bmp, long h, Rectangle b) {
        RECT r; GetWindowRect(new IntPtr(h), out r);
        long m = 0, t = 0;
        for (int y = r.T + 5; y < r.B - 5; y += 2)
            for (int x = r.L + 5; x < r.R - 5; x += 2) {
                int px = x - b.X, py = y - b.Y;
                if (px < 0 || py < 0 || px >= b.Width || py >= b.Height) continue;
                Color c = bmp.GetPixel(px, py); t++;
                if (c.R > 240 && c.G < 15 && c.B > 240) m++;
            }
        return t == 0 ? -1 : (double)m / t;
    }

    public static double[] Capture(long hEx, long hIn) {
        Rectangle b = Screen.PrimaryScreen.Bounds;
        using (Bitmap bmp = new Bitmap(b.Width, b.Height)) {
            using (Graphics g = Graphics.FromImage(bmp)) g.CopyFromScreen(b.X, b.Y, 0, 0, b.Size);
            long nb = 0, tot = 0;
            for (int y = 0; y < b.Height; y += 4)
                for (int x = 0; x < b.Width; x += 4) {
                    Color c = bmp.GetPixel(x, y); tot++;
                    if (c.R + c.G + c.B > 30) nb++;
                }
            return new double[] { (double)nb / tot, Mag(bmp, hEx, b), Mag(bmp, hIn, b), b.Width, b.Height };
        }
    }

    static int s_down, s_inj, s_up;
    static LLProc s_keep;
    static IntPtr Proc(int n, IntPtr w, IntPtr l) {
        if (n >= 0) {
            KBDLL k = (KBDLL)Marshal.PtrToStructure(l, typeof(KBDLL));
            if (k.vk == 0x87) {  // VK_F24: no app binds it
                if (w.ToInt64() == 0x100) { s_down++; if ((k.flags & 0x10) != 0) s_inj++; }
                else s_up++;
            }
        }
        return CallNextHookEx(IntPtr.Zero, n, w, l);
    }

    public static long[] W8(int count) {
        s_down = 0; s_inj = 0; s_up = 0;
        uint tid = 0; IntPtr hk = IntPtr.Zero;
        ManualResetEvent ready = new ManualResetEvent(false);
        Thread th = new Thread(delegate() {
            tid = GetCurrentThreadId();
            s_keep = Proc;
            hk = SetWindowsHookEx(13, s_keep, GetModuleHandle(null), 0);
            ready.Set();
            MSG m;
            while (GetMessage(out m, IntPtr.Zero, 0, 0) > 0) { }
            if (hk != IntPtr.Zero) UnhookWindowsHookEx(hk);
        });
        th.IsBackground = true; th.Start(); ready.WaitOne(); Thread.Sleep(300);
        LASTINPUTINFO li = new LASTINPUTINFO(); li.cb = 8;
        GetLastInputInfo(ref li); uint t0 = li.t;
        int sz = Marshal.SizeOf(typeof(INPUT)); uint sent = 0;
        for (int i = 0; i < count; i++) {
            INPUT[] a = new INPUT[2];
            a[0].type = 1; a[0].ki.vk = 0x87;
            a[1].type = 1; a[1].ki.vk = 0x87; a[1].ki.flags = 2;
            sent += SendInput(2, a, sz);
            Thread.Sleep(10);
        }
        Thread.Sleep(800);
        GetLastInputInfo(ref li); uint t1 = li.t;
        PostThreadMessage(tid, 0x12, IntPtr.Zero, IntPtr.Zero); th.Join(2000);
        return new long[] { hk == IntPtr.Zero ? 0 : 1, sent, s_down, s_inj, s_up, (long)(t1 - t0), sz };
    }
}
