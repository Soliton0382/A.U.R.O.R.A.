# Aurora - a camera of this PC sent to Aurora (the collimator's, a guide camera...), for the live collimation page.
# Run in PowerShell, in the folder of this file, with the command Aurora's page gives (it holds your camera key):
#   powershell -ExecutionPolicy Bypass -File .\astro_camera.ps1 -Url https://your-aurora:8443 -Key aurcam_...
# What it does: tells Aurora the cameras this PC sees, asks which one you chose in the page, and sends only that one,
# as JPEG frames, with ffmpeg. Nothing is listened to on this PC (no port opened): it only sends. The camera key can
# only send frames: it reads nothing of Aurora. Ctrl+C stops it. Close the camera's own program first (it holds the
# camera). ffmpeg: if it is not installed,  winget install --id Gyan.FFmpeg -e  (or -Ffmpeg C:\path\to\ffmpeg.exe).
# -Insecure: accept a certificate this PC does not trust (Aurora reached by its LAN address).
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [Parameter(Mandatory = $true)][string]$Key,
  [string]$Ffmpeg = "",
  [int]$Fps = 10,
  [int]$Width = 1280,
  [switch]$Insecure
)
$ErrorActionPreference = "Stop"
$Url = $Url.TrimEnd("/")
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if ($Insecure) { [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } }

function Find-Ffmpeg {
  if ($Ffmpeg -and (Test-Path $Ffmpeg)) { return $Ffmpeg }
  $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  $w = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\ffmpeg.exe"
  if (Test-Path $w) { return $w }
  return $null
}

function Get-Cameras($ff) {
  # ffmpeg lists DirectShow devices on stderr: '"Name" (video)' (newer) or a "DirectShow video devices" section (older)
  $lines = & $ff -hide_banner -list_devices true -f dshow -i dummy 2>&1 | ForEach-Object { "$_" }
  $names = @(); $inVideo = $false
  foreach ($l in $lines) {
    if ($l -match "DirectShow video devices") { $inVideo = $true; continue }
    if ($l -match "DirectShow audio devices") { $inVideo = $false; continue }
    if ($l -match "Alternative name") { continue }
    if ($l -match '"([^"]+)"\s+\(video\)') { $names += $Matches[1]; continue }
    if ($inVideo -and $l -match '"([^"]+)"') { $names += $Matches[1] }
  }
  return @($names | Select-Object -Unique)
}

function Ask($cams) {
  $body = @{ devices = @($cams) } | ConvertTo-Json -Compress
  $r = Invoke-RestMethod -Method Post -Uri "$Url/v1/aurora/astro/camera/pc" -Headers @{ "X-Aurora-Camera" = $Key } `
    -ContentType "application/json" -Body $body -TimeoutSec 10
  return [string]$r.wanted
}

$ff = Find-Ffmpeg
if (-not $ff) {
  Write-Host "ffmpeg not found. Install it with:  winget install --id Gyan.FFmpeg -e   (then open a new PowerShell)"
  exit 1
}
Write-Host "ffmpeg: $ff"
$cams = Get-Cameras $ff
Write-Host "cameras: $($cams -join ', ')"
if (-not $cams.Count) { Write-Host "no camera seen by DirectShow: is it plugged in?" }

$proc = $null; $current = ""; $listed = Get-Date
try {
  while ($true) {
    try { $wanted = Ask $cams } catch { Write-Host "Aurora does not answer: $($_.Exception.Message)"; Start-Sleep 5; continue }
    if ($proc -and $proc.HasExited) { $proc = $null }
    if ($wanted -ne $current -or ($wanted -and -not $proc)) {
      if ($proc) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; $proc = $null }
      $current = $wanted
      if ($wanted) {
        Write-Host "sending: $wanted"
        $ffArgs = @("-hide_banner", "-loglevel", "error", "-f", "dshow", "-rtbufsize", "64M", "-i", "video=`"$wanted`"",
          "-vf", "`"scale='min($Width,iw)':-2`"", "-r", "$Fps", "-f", "mpjpeg", "-q:v", "5",
          "-method", "POST", "-chunked_post", "1", "-headers", "`"X-Aurora-Camera: $Key`"",
          "$Url/v1/aurora/astro/camera/push")
        $proc = Start-Process -FilePath $ff -ArgumentList $ffArgs -NoNewWindow -PassThru
      } else { Write-Host "no camera chosen: waiting" }
    }
    if (-not $proc -and ((Get-Date) - $listed).TotalSeconds -gt 30) { $cams = Get-Cameras $ff; $listed = Get-Date }
    Start-Sleep 2
  }
} finally {
  if ($proc) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}
