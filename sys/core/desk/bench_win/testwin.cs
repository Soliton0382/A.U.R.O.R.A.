// N152 Windows phase 0: a test window with a known title (and, by mode, a password box, a capture-excluded
// magenta surface, or a text box whose content it reports to a file).
using System;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Windows.Forms;

public static class TestWin {
    [DllImport("user32.dll", SetLastError = true)] static extern bool SetWindowDisplayAffinity(IntPtr h, uint a);

    [STAThread]
    public static void Main(string[] a) {
        string mode = a.Length > 0 ? a[0] : "plain";
        string title = a.Length > 1 ? a[1] : "W0";
        Form f = new Form();
        f.Text = title;
        f.StartPosition = FormStartPosition.Manual;
        f.Width = 300; f.Height = 200;
        f.Left = a.Length > 2 ? int.Parse(a[2]) : 100;
        f.Top = a.Length > 3 ? int.Parse(a[3]) : 100;
        string report = a.Length > 4 ? a[4] : null;
        if (mode == "pw") {
            TextBox t = new TextBox(); t.Name = "pwbox"; t.UseSystemPasswordChar = true; t.Left = 10; t.Top = 10; t.Width = 200;
            TextBox u = new TextBox(); u.Name = "plainbox"; u.Left = 10; u.Top = 50; u.Width = 200;
            f.Controls.Add(t); f.Controls.Add(u);
        }
        if (mode == "excl" || mode == "incl") {
            f.BackColor = Color.FromArgb(255, 0, 255);
            f.FormBorderStyle = FormBorderStyle.None;
            f.TopMost = true;
            f.Shown += delegate(object s, EventArgs e) {
                if (mode == "excl") {
                    bool ok = SetWindowDisplayAffinity(f.Handle, 0x11);
                    File.WriteAllText(report, ok ? "ok" : ("fail " + Marshal.GetLastWin32Error()));
                }
            };
        }
        if (mode == "cover") {
            // a foreign surface always on top over the whole screen (like a system notice): counts what reaches it
            f.FormBorderStyle = FormBorderStyle.None;
            f.TopMost = true;
            f.ShowInTaskbar = false;
            f.BackColor = Color.FromArgb(40, 40, 40);
            f.Bounds = Screen.PrimaryScreen.Bounds;
            f.KeyPreview = true;
            int clicks = 0, keys = 0;
            f.MouseDown += delegate(object s, MouseEventArgs e) { clicks++; File.WriteAllText(report, clicks + "|" + keys); };
            f.KeyDown += delegate(object s, KeyEventArgs e) { keys++; File.WriteAllText(report, clicks + "|" + keys); };
            f.Shown += delegate(object s, EventArgs e) { File.WriteAllText(report, "0|0"); };
        }
        if (mode == "elev") {
            TextBox t = new TextBox(); t.Name = "elevbox"; t.Text = "orig"; t.Left = 10; t.Top = 10; t.Width = 200;
            f.Controls.Add(t);
            bool adm = new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);
            Timer tm = new Timer(); tm.Interval = 300;
            tm.Tick += delegate(object s, EventArgs e) {
                try { File.WriteAllText(report, (adm ? "admin" : "noadmin") + "|" + t.Text); } catch (Exception) { }
            };
            tm.Start();
        }
        Application.Run(f);
    }
}
