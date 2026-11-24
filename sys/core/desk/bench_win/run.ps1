# N152 Windows phase 0 runner: runs in aurora-lab's console session (scheduled task /IT, LIMITED).
# Writes only under C:\Aurora\desk_w0\out.
$ErrorActionPreference = 'Continue'
$base = 'C:\Aurora\desk_w0'; $out = Join-Path $base 'out'
New-Item -ItemType Directory -Force $out | Out-Null
function Save($name, $obj) { $obj | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $out $name) }
function Log($m) { Add-Content -Encoding UTF8 (Join-Path $out 'log.txt') ("{0} {1}" -f [DateTime]::Now.ToString('s'), $m) }
$R = [ordered]@{}
try {
  Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase, System.Windows.Forms, System.Drawing
  $want = 'UIAutomationClient', 'UIAutomationTypes', 'WindowsBase', 'System.Windows.Forms', 'System.Drawing'
  $refs = @([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $want -contains $_.GetName().Name } | ForEach-Object { $_.Location } | Select-Object -Unique)
  Add-Type -Path (Join-Path $base 'W0.cs') -ReferencedAssemblies $refs
  [W0]::DpiAware()
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $R.runner_admin_role = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  $R.runner_label = @(whoami /groups | Select-String 'S-1-16-' | ForEach-Object { $_.Line.Trim() -replace '\s+', ' ' })
  $R.session = (Get-Process -Id $PID).SessionId
  $tw = Join-Path $base 'testwin.exe'
  function WaitFind($pat, $sec) {
    $t = [DateTime]::Now.AddSeconds($sec)
    while ([DateTime]::Now -lt $t) { $w = [W0]::Find($pat); if ($w) { return $w }; Start-Sleep -Milliseconds 300 }
    return $null
  }

  # W1: window -> process
  Log 'W1'
  $p1 = @{}
  for ($i = 0; $i -lt 50; $i++) {
    $x = 20 + ($i % 10) * 70; $y = 20 + [math]::Floor($i / 10) * 70
    $p = Start-Process $tw -ArgumentList @('plain', "W1-$i", $x, $y) -PassThru; $p1[$i] = $p.Id
  }
  $t = [DateTime]::Now.AddSeconds(40)
  do { Start-Sleep 1; $wins = [W0]::Top(); $seen = @($wins | Where-Object { $_.Title -like 'W1-*' }).Count } while ($seen -lt 50 -and [DateTime]::Now -lt $t)
  $ok = 0; $bad = @()
  for ($i = 0; $i -lt 50; $i++) {
    $m = @($wins | Where-Object { $_.Title -eq "W1-$i" })
    if ($m.Count -eq 1 -and $m[0].Pid -eq $p1[$i]) { $ok++ } else { $bad += "$i found=$($m.Count) want=$($p1[$i])" }
  }
  $sw = [Diagnostics.Stopwatch]::StartNew(); for ($k = 0; $k -lt 20; $k++) { [void][W0]::Top() }
  $R.W1 = [ordered]@{ ok = $ok; of = 50; seen = $seen; bad = $bad; enum_ms_mean = [math]::Round($sw.Elapsed.TotalMilliseconds / 20, 2) }
  # W7: same-user memory read
  Log 'W7'
  $R.W7 = [W0]::ReadMZ($p1[0])
  foreach ($k in $p1.Keys) { Stop-Process -Id $p1[$k] -Force -ErrorAction SilentlyContinue }

  # W2 (+ W3 Edge): UI Automation names
  $act = 'Button', 'MenuItem', 'Edit', 'ListItem', 'TabItem', 'CheckBox', 'Hyperlink', 'ComboBox', 'RadioButton', 'SplitButton'
  $apps = @(
    @{ k = 'notepad';  f = { Start-Process notepad.exe }; pat = 'Blocco note|Notepad' },
    @{ k = 'explorer'; f = { Start-Process explorer.exe -ArgumentList $base }; pat = '^desk_w0' },
    @{ k = 'settings'; f = { Start-Process 'ms-settings:' }; pat = '^Impostazioni$|^Settings$' },
    @{ k = 'calc';     f = { Start-Process calc.exe }; pat = '^Calcolatrice$|^Calculator$' },
    @{ k = 'paint';    f = { Start-Process mspaint.exe }; pat = 'Paint$' },
    @{ k = 'edge';     f = { Start-Process msedge.exe -ArgumentList 'file:///C:/Aurora/desk_w0/pagina.html' }; pat = 'W0 pagina di prova' }
  )
  $R.W2 = [ordered]@{}
  foreach ($a in $apps) {
    Log "W2 $($a.k)"
    try {
      & $a.f
      $w = WaitFind $a.pat 25
      if (-not $w) { $R.W2[$a.k] = @{ error = 'window not found' }; continue }
      Start-Sleep 3
      $sw = [Diagnostics.Stopwatch]::StartNew(); $els = [W0]::Walk($w.H, 5000, 40); $ms1 = $sw.Elapsed.TotalMilliseconds
      Start-Sleep 2
      $sw.Restart(); $els = [W0]::Walk($w.H, 5000, 40); $ms2 = $sw.Elapsed.TotalMilliseconds
      $Az = @($els | Where-Object { $act -contains $_.Type }); $Nam = @($Az | Where-Object { $_.Name -and $_.Name.Trim() })
      $R.W2[$a.k] = [ordered]@{
        title = $w.Title; pid = $w.Pid; total = $els.Count; actionable = $Az.Count; named = $Nam.Count
        frac = $(if ($Az.Count) { [math]::Round($Nam.Count / $Az.Count, 4) } else { $null })
        walk_ms_first = [math]::Round($ms1); walk_ms = [math]::Round($ms2)
        password_fields = @($els | Where-Object { $_.Pw }).Count
      }
      if ($a.k -eq 'edge') {
        $di = -1
        for ($j = 0; $j -lt $els.Count; $j++) { if ($els[$j].Type -eq 'Document' -and $els[$j].Name -match 'W0 pagina') { $di = $j; break } }
        if ($di -ge 0) {
          $dd = $els[$di].Depth; $sub = @()
          for ($j = $di + 1; $j -lt $els.Count -and $els[$j].Depth -gt $dd; $j++) { $sub += $els[$j] }
          $As = @($sub | Where-Object { $act -contains $_.Type }); $Ns = @($As | Where-Object { $_.Name -and $_.Name.Trim() })
          $R.W2.edge_page = [ordered]@{ actionable = $As.Count; named = $Ns.Count; unnamed = @($As | Where-Object { -not ($_.Name -and $_.Name.Trim()) } | ForEach-Object { "$($_.Type) $($_.Aid)" }) }
        }
        $R.W3_edge = [ordered]@{
          pw1 = @($els | Where-Object { $_.Aid -eq 'pw1' } | ForEach-Object { $_.Pw })
          u1 = @($els | Where-Object { $_.Aid -eq 'u1' } | ForEach-Object { $_.Pw })
          pw_edits = @($els | Where-Object { $_.Type -eq 'Edit' -and $_.Pw }).Count
        }
      }
      Save "uia_$($a.k).json" $els
      if ($a.k -ne 'edge') { [W0]::Close($w.H) }
    } catch { $R.W2[$a.k] = @{ error = "$_" } }
  }

  # W3: password box in a WinForms window
  Log 'W3'
  $p3 = Start-Process $tw -ArgumentList @('pw', 'W3-pw', 600, 300) -PassThru
  $w = WaitFind '^W3-pw$' 15
  $els = [W0]::Walk($w.H, 200, 10)
  $R.W3_form = [ordered]@{
    pwbox = @($els | Where-Object { $_.Aid -eq 'pwbox' } | ForEach-Object { $_.Pw })
    plainbox = @($els | Where-Object { $_.Aid -eq 'plainbox' } | ForEach-Object { $_.Pw })
  }
  Stop-Process -Id $p3.Id -Force

  # W8: injected input is flagged
  Log 'W8'
  $r8 = [W0]::W8(100)
  $R.W8 = [ordered]@{ hook = $r8[0]; sent_events = $r8[1]; down_seen = $r8[2]; down_injected = $r8[3]; up_seen = $r8[4]; lastinput_delta_ms = $r8[5]; input_size = $r8[6] }

  # W4/W5: capture without consent; capture exclusion
  Log 'W4'
  $flag = Join-Path $out 'w5_affinity.txt'
  $pe = Start-Process $tw -ArgumentList @('excl', 'W5-excl', 100, 100, $flag) -PassThru
  $pc = Start-Process $tw -ArgumentList @('incl', 'W5-incl', 500, 100, 'none') -PassThru
  $we = WaitFind '^W5-excl$' 15; $wc = WaitFind '^W5-incl$' 15; Start-Sleep 2
  $c = [W0]::Capture($we.H, $wc.H)
  $R.W4 = [ordered]@{ nonblack_frac = [math]::Round($c[0], 4); width = $c[3]; height = $c[4] }
  $R.W5 = [ordered]@{ affinity_call = $(if (Test-Path $flag) { ([string](Get-Content $flag -Raw)) } else { 'no report' }); magenta_in_excluded = [math]::Round($c[1], 4); magenta_in_control = [math]::Round($c[2], 4) }
  Stop-Process -Id $pe.Id, $pc.Id -Force

  # W6: UIPI. Control first (a medium window), then the elevated one started by the host.
  Log 'W6'
  $sf = Join-Path $out 'w6_medium.txt'
  $pm = Start-Process $tw -ArgumentList @('elev', 'W6-medium', 100, 400, $sf) -PassThru
  $wm = WaitFind '^W6-medium$' 15; Start-Sleep 1
  $s0 = [string](Get-Content $sf -Raw)
  $cu = [W0]::UiaSet($wm.H, 'elevbox', 'cambiato-uia'); Start-Sleep 1; $s1 = [string](Get-Content $sf -Raw)
  $cm = [W0]::MsgSet($wm.H, 'cambiato-msg'); Start-Sleep 1; $s2 = [string](Get-Content $sf -Raw)
  $R.W6_control = [ordered]@{ before = $s0; uia = $cu; after_uia = $s1; msg = $cm; after_msg = $s2 }
  Stop-Process -Id $pm.Id -Force
  Set-Content (Join-Path $out 'need_w6.txt') 'go'
  $ef = Join-Path $out 'w6.txt'
  $t = [DateTime]::Now.AddSeconds(120); while (-not (Test-Path $ef) -and [DateTime]::Now -lt $t) { Start-Sleep 1 }
  $we6 = WaitFind '^W6-elev$' 20; Start-Sleep 1
  if ($we6) {
    $s0 = [string](Get-Content $ef -Raw)
    $eu = [W0]::UiaSet($we6.H, 'elevbox', 'cambiato-uia'); Start-Sleep 1; $s1 = [string](Get-Content $ef -Raw)
    $em = [W0]::MsgSet($we6.H, 'cambiato-msg'); Start-Sleep 1; $s2 = [string](Get-Content $ef -Raw)
    $R.W6 = [ordered]@{ before = $s0; uia = $eu; after_uia = $s1; msg = $em; after_msg = $s2 }
  } else { $R.W6 = @{ error = 'elevated window not found' } }
} catch {
  $R.fatal = "$_ | $($_.InvocationInfo.PositionMessage)"
} finally {
  Save 'result.json' $R
  Set-Content (Join-Path $out 'done.txt') 'done'
  Log 'done'
}
