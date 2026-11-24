# N152 Windows phase 0, second (declared) measure of W3/W2 on Edge web content.
$ErrorActionPreference = 'Continue'
$base = 'C:\Aurora\desk_w0'; $out = Join-Path $base 'out_w3b'
New-Item -ItemType Directory -Force $out | Out-Null
$R = [ordered]@{}
try {
  Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase, System.Windows.Forms, System.Drawing
  $want = 'UIAutomationClient', 'UIAutomationTypes', 'WindowsBase', 'System.Windows.Forms', 'System.Drawing'
  $refs = @([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $want -contains $_.GetName().Name } | ForEach-Object { $_.Location } | Select-Object -Unique)
  Add-Type -Path (Join-Path $base 'W0.cs') -ReferencedAssemblies $refs
  $act = 'Button', 'MenuItem', 'Edit', 'ListItem', 'TabItem', 'CheckBox', 'Hyperlink', 'ComboBox', 'RadioButton', 'SplitButton'
  function Stat($tag) {
    $w = $null; $t = [DateTime]::Now.AddSeconds(30)
    while (-not $w -and [DateTime]::Now -lt $t) { $w = [W0]::Find('W0 pagina di prova'); Start-Sleep -Milliseconds 500 }
    if (-not $w) { return @{ error = 'window not found' } }
    $res = @()
    foreach ($wait in 2, 10) {
      Start-Sleep $wait
      $els = [W0]::Walk($w.H, 5000, 60)
      $doc = @($els | Where-Object { $_.Type -eq 'Document' })
      $Az = @($els | Where-Object { $act -contains $_.Type }); $Nm = @($Az | Where-Object { $_.Name -and $_.Name.Trim() })
      $res += [ordered]@{
        after_s = $wait; total = $els.Count; documents = $doc.Count; actionable = $Az.Count; named = $Nm.Count
        pw1 = @($els | Where-Object { $_.Aid -eq 'pw1' } | ForEach-Object { [string]$_.Pw }) -join ','
        u1 = @($els | Where-Object { $_.Aid -eq 'u1' } | ForEach-Object { [string]$_.Pw }) -join ','
        pw_edits = @($els | Where-Object { $_.Pw }).Count
        unnamed = @($Az | Where-Object { -not ($_.Name -and $_.Name.Trim()) } | ForEach-Object { "$($_.Type)/$($_.Aid)/$($_.Cls)" }) -join '; '
      }
      ($els | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 (Join-Path $out "uia_edge_$tag.json")
    }
    return $res
  }
  $R.plain = Stat 'plain'
  Set-Content (Join-Path $out 'need_restart.txt') 'go'
  $t = [DateTime]::Now.AddSeconds(90); while (-not (Test-Path (Join-Path $out 'restarted.txt')) -and [DateTime]::Now -lt $t) { Start-Sleep 1 }
  Start-Process msedge.exe -ArgumentList '--force-renderer-accessibility', 'file:///C:/Aurora/desk_w0/pagina.html'
  $R.forced = Stat 'forced'
} catch { $R.fatal = "$_ | $($_.InvocationInfo.PositionMessage)" }
finally {
  ($R | ConvertTo-Json -Depth 5) | Set-Content -Encoding UTF8 (Join-Path $out 'result.json')
  Set-Content (Join-Path $out 'done.txt') 'done'
}
