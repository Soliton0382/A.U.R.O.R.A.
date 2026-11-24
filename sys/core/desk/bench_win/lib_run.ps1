# N152 bench (Windows): runs one general-library procedure through UI Automation patterns and checks every step's
# expected state. Bench only: aurora-desk acts by input, not by patterns; this proves the anchors and the flow.
# Usage (in the lab user's session): lib_run.ps1 -Job <job.json>, job = {"proc": file, "params": {...}, "out": file}
param([string]$Job)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type -Namespace W32 -Name Msg -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
[StructLayout(LayoutKind.Sequential)] public struct PT { public int x, y; }
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(PT p);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
'@
[void][W32.Msg]::SetProcessDPIAware()
# A window that is not the task's (a system notice always on top, another program) in front, or under the point to
# be clicked = STOP (design §8.3). Seen on the VM: a Windows Update notice took the keys meant for a save dialog.
function Mine([IntPtr]$h) {
  if ($h -eq [IntPtr]::Zero) { return $false }
  $root = [W32.Msg]::GetAncestor($h, 3)
  $ours = @(NewWindows | ForEach-Object { [IntPtr]$_.Current.NativeWindowHandle })
  return ($ours -contains $root) -or ($ours -contains $h)
}
function Title([IntPtr]$h) { $sb = New-Object System.Text.StringBuilder 256; [void][W32.Msg]::GetWindowText($h, $sb, 256); return $sb.ToString() }
function Guard([object]$pt) {
  $fg = [W32.Msg]::GetForegroundWindow()
  if (-not (Mine $fg)) { throw ("STOP: foreign window in front: '{0}'" -f (Title ([W32.Msg]::GetAncestor($fg, 3)))) }
  if ($pt) {
    $p = New-Object W32.Msg+PT; $p.x = $pt[0]; $p.y = $pt[1]
    $hw = [W32.Msg]::WindowFromPoint($p)
    if (-not (Mine $hw)) { throw ("STOP: foreign window under the point: '{0}'" -f (Title ([W32.Msg]::GetAncestor($hw, 3)))) }
  }
}
# Bench input, as aurora-desk will act: a click at the element's centre, then real keys.
function Click($e) {
  $b = $e.Current.BoundingRectangle
  Guard @([int]($b.X + $b.Width / 2), [int]($b.Y + $b.Height / 2))
  [void][W32.Msg]::SetCursorPos([int]($b.X + $b.Width / 2), [int]($b.Y + $b.Height / 2))
  Start-Sleep -Milliseconds 80
  [W32.Msg]::mouse_event(0x2, 0, 0, 0, [IntPtr]::Zero); [W32.Msg]::mouse_event(0x4, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 150
}
function Esc([string]$t) { return ($t -replace '([+^%~(){}\[\]])', '{$1}') }
$AE = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$loc = (Get-Culture).TwoLetterISOLanguageName
$jb = Get-Content $Job -Raw -Encoding UTF8 | ConvertFrom-Json
$Out = $jb.out
$Pr = Get-Content $jb.proc -Raw -Encoding UTF8 | ConvertFrom-Json
$par = $jb.params
$res = [ordered]@{ id = $Pr.id; locale = $loc; steps = @(); ok = $false }

function Sub([string]$s) {
  foreach ($p in $par.PSObject.Properties) { $s = $s.Replace('{' + $p.Name + '}', [string]$p.Value) }
  return $s
}
function TopHandles { @($AE::RootElement.FindAll($TS::Children, [System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.NativeWindowHandle }) }
$before = TopHandles
function NewWindows { @($AE::RootElement.FindAll($TS::Children, [System.Windows.Automation.Condition]::TrueCondition) | Where-Object { $before -notcontains $_.Current.NativeWindowHandle }) }

# The managed UIA client has no proxies for classic Win32 controls: they come back as Pane. The role is then taken
# from the window class (Button, Edit, ComboBox), as the native client would report it.
function Role($e) {
  $r = $e.Current.ControlType.ProgrammaticName.Replace('ControlType.', '')
  if ($r -eq 'Pane') { switch -regex ($e.Current.ClassName) { '^Button$' { return 'Button' } '^Edit$' { return 'Edit' } '^ComboBox' { return 'ComboBox' } } }
  return $r
}
function Cond($t) {
  if ($t.id) { return New-Object System.Windows.Automation.PropertyCondition($AE::AutomationIdProperty, [string]$t.id) }
  if ($t.name -and $t.name.$loc) { return New-Object System.Windows.Automation.PropertyCondition($AE::NameProperty, (Sub ([string]$t.name.$loc))) }
  return [System.Windows.Automation.Condition]::TrueCondition
}
function Matches($e, $t) {
  if ((Role $e) -ne $t.role) { return $false }
  if ($t.id -and $t.name -and $t.name.$loc -and $e.Current.Name -ne (Sub ([string]$t.name.$loc))) { return $false }
  if ($t.name_re -and $t.name_re.$loc) { return $e.Current.Name -match (Sub ([string]$t.name_re.$loc)) }
  return $true
}
function FindT($t) {
  $cond = Cond $t
  foreach ($w in NewWindows) {
    foreach ($e in $w.FindAll($TS::Subtree, $cond)) { if (Matches $e $t) { if (-not $e.Current.IsOffscreen -or $t.offscreen_ok) { return $e } } }
  }
  return $null
}
function WaitT($t, $sec) {
  $end = [DateTime]::Now.AddSeconds($sec)
  do { $e = FindT $t; if ($e) { return $e }; Start-Sleep -Milliseconds 200 } while ([DateTime]::Now -lt $end)
  return $null
}
function Keys([string]$k) {
  $m = ''; $parts = $k.Split('+'); $key = $parts[-1]
  foreach ($q in $parts[0..($parts.Count - 2)]) { if ($parts.Count -gt 1) { switch ($q) { 'Ctrl' { $m += '^' } 'Shift' { $m += '+' } 'Alt' { $m += '%' } } } }
  $map = @{ Enter = '{ENTER}'; Esc = '{ESC}'; Tab = '{TAB}'; F2 = '{F2}'; F4 = '{F4}'; Del = '{DEL}' }
  if ($map.ContainsKey($key)) { $key = $map[$key] } else { $key = $key.ToLower() }
  return $m + $key
}
function Pat($e, $p) { $o = $null; if ($e.TryGetCurrentPattern($p, [ref]$o)) { return $o }; return $null }
function Dump {
  $l = @()
  foreach ($w in NewWindows) {
    foreach ($e in $w.FindAll($TS::Subtree, [System.Windows.Automation.Condition]::TrueCondition)) {
      $c = $e.Current
      if ($c.Name -or $c.AutomationId) { $l += ('{0}|{1}|{2}|{3}|off={4}' -f (Role $e), $c.Name, $c.AutomationId, $c.ClassName, $c.IsOffscreen) }
      if ($l.Count -ge 400) { return $l }
    }
  }
  return $l
}

try {
  $la = @($Pr.program.launch.args | Where-Object { $_ } | ForEach-Object { Sub $_ })
  if ($la.Count) { Start-Process $Pr.program.launch.exe -ArgumentList $la } else { Start-Process $Pr.program.launch.exe }
  $vars = @{}
  foreach ($s in $Pr.steps) {
    $r = [ordered]@{ n = $s.n; do = $s.do; class = $s.class }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
      $tmo = $(if ($s.timeout_s) { [int]$s.timeout_s } else { 10 })
      $e = $null
      if ($s.target) { $e = WaitT $s.target $tmo; if (-not $e) { throw "target not found" } }
      switch ($s.do) {
        'wait' { }
        'open_menu' { (Pat $e ([System.Windows.Automation.ExpandCollapsePattern]::Pattern)).Expand() }
        'press' {
          $iv = Pat $e ([System.Windows.Automation.InvokePattern]::Pattern)
          if ($iv) { $iv.Invoke() } else {
            $si = Pat $e ([System.Windows.Automation.SelectionItemPattern]::Pattern)
            if ($si) { $si.Select() } else {
              $tg = Pat $e ([System.Windows.Automation.TogglePattern]::Pattern)
              if ($tg) { $tg.Toggle() }
              else { Click $e; $r.via = 'click' }
            }
          }
        }
        'type' {
          $v = Pat $e ([System.Windows.Automation.ValuePattern]::Pattern)
          $txt = Sub ([string]$s.text)
          if ($v) { $v.SetValue($txt) }
          else { Click $e; Guard $null; [System.Windows.Forms.SendKeys]::SendWait('^a'); Guard $null; [System.Windows.Forms.SendKeys]::SendWait((Esc $txt)); $r.via = 'click+keys' }
        }
        'key' { if ($e) { try { $e.SetFocus() } catch { Click $e } }; Start-Sleep -Milliseconds 150; Guard $null; [System.Windows.Forms.SendKeys]::SendWait((Keys $s.keys)) }
        'read' {
          $v = Pat $e ([System.Windows.Automation.ValuePattern]::Pattern)
          $vars[$s.into] = $(if ($v) { $v.Current.Value } else { $e.Current.Name })
          $r.read = $vars[$s.into]
        }
        default { throw "unknown step $($s.do)" }
      }
      if ($s.expect) {
        if ($s.expect.present) { if (-not (WaitT $s.expect.present $tmo)) { throw 'expected element missing' } }
        if ($s.expect.gone) {
          $end = [DateTime]::Now.AddSeconds($tmo)
          while ((FindT $s.expect.gone) -and [DateTime]::Now -lt $end) { Start-Sleep -Milliseconds 200 }
          if (FindT $s.expect.gone) { throw 'expected element still there' }
        }
      }
      $r.ok = $true
    } catch {
      $r.ok = $false; $r.error = "$_"; $r.dump = Dump
      $r.ms = $sw.ElapsedMilliseconds; $res.steps += $r
      throw "step $($s.n): $_"
    }
    $r.ms = $sw.ElapsedMilliseconds; $res.steps += $r
  }
  $res.ok = $true; $res.vars = $vars
} catch { $res.error = "$_" }
finally {
  foreach ($w in NewWindows) { try { $h = $w.Current.NativeWindowHandle; if ($h) { [void](Pat $w ([System.Windows.Automation.WindowPattern]::Pattern)).Close() } } catch { } }
  ($res | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 $Out
}
