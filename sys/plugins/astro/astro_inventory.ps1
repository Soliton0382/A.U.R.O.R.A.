# Aurora - inventory of an astrophotography PC (read only: nothing is changed, nothing is sent anywhere).
# Run in PowerShell, in the folder of this file:  powershell -ExecutionPolicy Bypass -File .\astro_inventory.ps1
# Writes astro_inventory.txt next to this script: upload it in Aurora's Astro page.
# Private data: the site's coordinates are rounded to 0.1 degrees (about 10 km); passwords, keys and tokens are never
# copied. Version 2 (ROADMAP 79): the darks are also looked for in N.I.N.A.'s image folders, PHD2's profile by its
# name and its guide logs where PHD2 writes them. Version 3: run it with the programs open - the servers they offer
# (PHD2's event server, N.I.N.A.'s Advanced API, ASCOM Remote / Alpaca) are listed and tried from this PC, read only.
$ErrorActionPreference = "SilentlyContinue"
$out = Join-Path $PSScriptRoot "astro_inventory.txt"
function W($s) { Add-Content -Path $out -Value $s -Encoding UTF8 }
Set-Content -Path $out -Value "# astro inventory $(Get-Date -Format 'yyyy-MM-dd HH:mm') (script 3)" -Encoding UTF8

W "`n== system"
$os = Get-CimInstance Win32_OperatingSystem; $cpu = Get-CimInstance Win32_Processor
W "$($os.Caption) $($os.Version); CPU $($cpu.Name) ($($cpu.NumberOfLogicalProcessors) threads); RAM $([math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB"
W "time zone: $((Get-TimeZone).Id); clock source: $((w32tm /query /status | Select-String 'Source').Line)"
Get-CimInstance Win32_LogicalDisk | ForEach-Object { W "disk $($_.DeviceID) $([math]::Round($_.FreeSpace/1GB)) GB free of $([math]::Round($_.Size/1GB)) GB ($($_.ProviderName))" }

W "`n== astronomy software installed"
$keys = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
Get-ItemProperty $keys | Where-Object { $_.DisplayName -match "N\.?I\.?N\.?A|PHD|ASTAP|ASCOM|Stellarium|SharpCap|ZWO|QHY|Pegasus|EQMOD|GSServer|iOptron|Celestron|SkyWatcher|PlateSolve|Siril|PixInsight|Cartes|Gemini|Optec|Moonlite|Starlight|OnStep|Alpaca" } |
  Sort-Object DisplayName -Unique | ForEach-Object { W "$($_.DisplayName) | $($_.DisplayVersion) | $($_.InstallLocation)" }

W "`n== ASCOM: platform and drivers"
$ascom = "HKLM:\SOFTWARE\WOW6432Node\ASCOM"
W "platform: $((Get-ItemProperty "$ascom\Platform").'Platform Version')"
foreach ($kind in "Telescope", "Camera", "Focuser", "FilterWheel", "Rotator", "Dome", "SafetyMonitor", "ObservingConditions", "Switch", "CoverCalibrator") {
  Get-ChildItem "$ascom\$kind Drivers" | ForEach-Object { W "$kind : $($_.PSChildName) | $((Get-ItemProperty $_.PSPath).'(default)')" }
}

W "`n== devices (USB / serial)"
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match "COM\d|ZWO|\bASI\d|QHY|Pegasus|FTDI|Prolific|CH340|Silicon Labs|Celestron|Sky-Watcher|iOptron|Focus|Filter|Canon|Nikon|Sony" } |
  ForEach-Object { W "$($_.Name) | $($_.Status)" }

W "`n== N.I.N.A. profiles"
$nina = Join-Path $env:LOCALAPPDATA "NINA"
$images = @()
Get-ChildItem (Join-Path $nina "Profiles") -Filter *.profile | Sort-Object LastWriteTime -Descending | ForEach-Object {
  [xml]$x = Get-Content $_.FullName
  $pname = $x.SelectSingleNode("//*[local-name()='Name' and parent::*[local-name()='Profile']]").InnerText
  W "-- $($_.Name) name=$pname ($($_.LastWriteTime))"
  $t = $x.SelectSingleNode("//*[local-name()='AstrometrySettings']")
  if ($t) { W "  site: lat $([math]::Round([double]$t.Latitude,1)) lon $([math]::Round([double]$t.Longitude,1)) elevation $($t.Elevation) m (rounded)" }
  foreach ($n in "CameraSettings", "TelescopeSettings", "FocuserSettings", "FilterWheelSettings", "GuiderSettings", "PlateSolveSettings", "ImageFileSettings", "MeridianFlipSettings", "AutoFocusSettings", "RotatorSettings") {
    $node = $x.SelectSingleNode("//*[local-name()='$n']")
    if ($node) {
      $vals = $node.ChildNodes | Where-Object { $_.Name -notmatch "(?i)password|key|token|secret|user" -and $_.InnerText.Length -lt 120 -and $_.InnerText -ne "" } |
        ForEach-Object { "$($_.LocalName)=$($_.InnerText)" }
      W "  $n : $($vals -join '; ')"
    }
  }
  $fp = $x.SelectSingleNode("//*[local-name()='ImageFileSettings']/*[local-name()='FilePath']").InnerText
  if ($fp) { $images += $fp.TrimEnd('\') + '\' }
  $filters = $x.SelectNodes("//*[local-name()='FilterInfo']/*[local-name()='_name' or local-name()='Name']") | ForEach-Object { $_.InnerText }
  if ($filters) { W "  filters: $(($filters | Select-Object -Unique) -join ', ')" }
}
W "N.I.N.A. plugins: $((Get-ChildItem (Join-Path $nina 'Plugins') -Directory -Recurse -Depth 1 | Where-Object { $_.Name -notmatch '^\d+(\.\d+)+$' } | ForEach-Object Name) -join ', ')"
$docs = [Environment]::GetFolderPath("MyDocuments")
W "N.I.N.A. sequences: $((Get-ChildItem $docs -Recurse -Depth 3 -Filter *.json | Where-Object { $_.FullName -match 'N\.?I\.?N\.?A' } | Select-Object -First 25 | ForEach-Object Name) -join ', ')"
W "N.I.N.A. last log, errors and warnings:"
Get-ChildItem (Join-Path $nina "Logs") -Filter *.log | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object {
  W "  log: $($_.Name) ($($_.LastWriteTime))"
  Select-String -Path $_.FullName -Pattern "\|ERROR\||\|WARNING\|" | Select-Object -Last 15 | ForEach-Object { W "  $($_.Line.Substring(0, [Math]::Min(220, $_.Line.Length)))" } }

W "`n== PHD2: the current profile, its settings and the guide logs"
$phd = "HKCU:\Software\StarkLabs\PHDGuidingV2"
$root = Get-ItemProperty $phd
$cur = ($root.PSObject.Properties | Where-Object { $_.Name -match "currentProfile" } | Select-Object -First 1).Value
Get-ChildItem "$phd\profile" | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath
  W "profile $($_.PSChildName): $($p.name)$(if ("$($_.PSChildName)" -eq "$cur") { ' (current)' })"
}
if ($cur) {
  W "settings of the current profile:"
  Get-ChildItem "$phd\profile\$cur" -Recurse | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath
    $p.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS|(?i)password|key" } | ForEach-Object { W "  $($_.Name)=$($_.Value)" } }
}
$logdir = ($root.PSObject.Properties | Where-Object { $_.Name -match "LogDir" } | Select-Object -First 1).Value
if (-not $logdir) { $logdir = Join-Path $docs "PHD2" }
W "guide logs in: $logdir"
$logs = Get-ChildItem $logdir -Filter "PHD2_GuideLog*.txt" | Sort-Object LastWriteTime
W "guide logs: $($logs.Count); the latest: $(($logs | Select-Object -Last 5 | ForEach-Object { "$($_.Name) ($([math]::Round($_.Length/1KB)) KB)" }) -join ', ')"
$logs | Select-Object -Last 1 | ForEach-Object {
  Get-Content $_.FullName -TotalCount 80 | Where-Object { $_ -match "Pixel scale|Exposure|RA =|Dec =|Mount|Camera|Calibration|Guiding Begins|aggressiveness|Hysteresis|MinMove|algorithm|Focal length" } | ForEach-Object { W "  $_" }
  W "  sessions in it: $((Select-String -Path $_.FullName -Pattern 'Guiding Begins').Count); stars lost: $((Select-String -Path $_.FullName -Pattern 'Star lost|STAR_LOST').Count)" }

W "`n== ASTAP"
$astap = Get-ChildItem "C:\Program Files\astap", "C:\Program Files (x86)\astap" -Filter astap.exe -Recurse | Select-Object -First 1
W "program: $($astap.FullName)"
if ($astap) { W "star databases: $((Get-ChildItem (Split-Path $astap.FullName) -Recurse -Include *.1476,*.290,*.001 | ForEach-Object { $_.Name.Split('_')[0] } | Sort-Object -Unique) -join ' ')" }

W "`n== connections (the programs' own servers: run this with N.I.N.A., PHD2 and the drivers open)"
# what Aurora can reach to follow a night: which programs run, the ports they listen on and to whom (only this PC, or
# the network), the Windows firewall's rules for them, and a read-only look at each server from this PC itself
foreach ($a in Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' }) {
  W "address: $($a.IPAddress)/$($a.PrefixLength) on $($a.InterfaceAlias)" }
Get-NetConnectionProfile | ForEach-Object { W "network profile: $($_.InterfaceAlias) = $($_.NetworkCategory)" }
$names = "NINA", "phd2", "ASCOM.RemoteServer", "ASCOM.Remote", "RemoteServer", "SharpCap", "astap", "stellarium", "OnStep", "ASCOM.DeviceHub", "GSServer", "EQMOD", "APCC", "TheSkyX", "Cartes", "SkyChart"
$procs = Get-Process | Where-Object { $n = $_.ProcessName; $names | Where-Object { $n -like "*$_*" } }
foreach ($p in $procs) { W "running: $($p.ProcessName) (pid $($p.Id))" }
$ids = @($procs | ForEach-Object Id)
Get-NetTCPConnection -State Listen | Where-Object { $ids -contains $_.OwningProcess -or @(4400, 4401, 1888, 11111, 8090, 9999, 7624) -contains $_.LocalPort } |
  Sort-Object LocalPort -Unique | ForEach-Object {
    $pn = (Get-Process -Id $_.OwningProcess).ProcessName
    W "listening: tcp $($_.LocalPort) $pn on $($_.LocalAddress)$(if ($_.LocalAddress -in '127.0.0.1', '::1') { ' (this PC only)' } else { ' (the network)' })" }
Get-NetUDPEndpoint | Where-Object { $_.LocalPort -eq 32227 } | ForEach-Object { W "listening: udp 32227 $((Get-Process -Id $_.OwningProcess).ProcessName) on $($_.LocalAddress) (Alpaca discovery)" }
Get-NetFirewallRule -Enabled True -Direction Inbound | Where-Object { $_.DisplayName -match "N\.?I\.?N\.?A|PHD|ASCOM|Alpaca|Stellarium|SharpCap|OnStep" } | ForEach-Object {
  $port = ($_ | Get-NetFirewallPortFilter).LocalPort; $app = ($_ | Get-NetFirewallApplicationFilter).Program
  W "firewall: $($_.DisplayName) | $($_.Action) | profiles $($_.Profile) | port $port | $app" }
function Probe($label, $url) {                    # one GET on this PC, its first words; nothing is changed
  try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 $url; W "server: $label answers $($r.StatusCode): $($r.Content.Substring(0, [Math]::Min(160, $r.Content.Length)) -replace '\s+', ' ')" }
  catch { W "server: $label does not answer at $url" } }
Probe "N.I.N.A. Advanced API" "http://localhost:1888/v2/api/version"
Probe "ASCOM Remote / Alpaca" "http://localhost:11111/management/apiversions"
Probe "Stellarium remote control" "http://localhost:8090/api/main/status"
try {                                              # PHD2's event server says who it is as soon as one connects
  $c = New-Object System.Net.Sockets.TcpClient; $c.ReceiveTimeout = 3000; $c.Connect("127.0.0.1", 4400)
  $line = (New-Object System.IO.StreamReader($c.GetStream())).ReadLine(); $c.Close()
  W "server: PHD2 event server answers: $($line.Substring(0, [Math]::Min(160, $line.Length)))" }
catch { W "server: PHD2 event server does not answer on port 4400 (PHD2 closed, or Tools > Enable Server off)" }
W "N.I.N.A. Advanced API plugin: $(if (Get-ChildItem (Join-Path $nina 'Plugins') -Recurse -Depth 2 -Filter '*Advanced*API*') { 'installed' } else { 'not found' })"

W "`n== darks (folders with 'dark' in the name: count and an example file name, which usually holds exposure, gain, temperature)"
$places = @($images) + @($docs, "D:\", "E:\") | Select-Object -Unique
W "looked in: $($places -join ', ')"
foreach ($d in $places) {
  Get-ChildItem $d -Recurse -Depth 5 -Include *.fits,*.fit,*.fts,*.xisf | Where-Object { $_.FullName -match "(?i)dark" } |
    Group-Object { $_.Directory.FullName } | Select-Object -First 30 | ForEach-Object { W "$($_.Name): $($_.Count) files, e.g. $($_.Group[0].Name)" } }
W "`n# end"
Write-Host "written: $out"
