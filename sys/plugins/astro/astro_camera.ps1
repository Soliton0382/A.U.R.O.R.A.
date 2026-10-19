# Aurora - a camera of this PC sent to Aurora (the collimator's, a guide camera...), for the live collimation page.
# Run in PowerShell, in the folder of this file, with the command Aurora's collimation page gives (it holds your key):
#   powershell -ExecutionPolicy Bypass -File .\astro_camera.ps1 -Url https://your-aurora:8443 -Key aurcam_...
# The first time it installs what it needs, for this user only: Python (with winget, if missing), then in a folder of
# its own next to this file (.aurora-camera) OpenCV - the same engine the collimator's program uses - and pygrabber
# (the cameras' names). Then it starts astro_camera.py: it tells Aurora the cameras this PC sees, sends the one you
# choose in the page, and sets on it what you ask there (gain, exposure, focus, zoom, resolution). Nothing listens on
# this PC: it only sends. Close the collimator's own program first (it holds the camera). Ctrl+C stops it.
# -Insecure: accept a certificate this PC does not trust (Aurora reached by its LAN address). -List: only the cameras.
param(
  [string]$Url = "",
  [string]$Key = "",
  [switch]$Insecure,
  [switch]$List
)
# "Continue", not "Stop": Windows PowerShell 5.1 turns any line a program writes on stderr into an error, and with
# "Stop" the expected failure of the first check (OpenCV not installed yet) ended the script (owner's PC, 20 Oct)
$ErrorActionPreference = "Continue"
$here = $PSScriptRoot
$venv = Join-Path $here ".aurora-camera"
$vpy = Join-Path $venv "Scripts\python.exe"

function Find-Python {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $exe = (& py -3 -c "import sys; print(sys.executable)" 2>&1 | Where-Object { $_ -is [string] } | Select-Object -Last 1)
    if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
  }
  $p = Get-Command python -ErrorAction SilentlyContinue
  if ($p -and $p.Source -notmatch "WindowsApps") { return $p.Source }        # not the Store's stub
  foreach ($v in "313", "312", "311", "310") {
    $c = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
    if (Test-Path $c) { return $c }
  }
  return $null
}

if (-not (Test-Path $vpy)) {
  $python = Find-Python
  if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
      Write-Host "Python is missing and winget is not on this PC: install Python 3 from python.org, then run this again."
      exit 1
    }
    Write-Host "Installing Python (once, for this user)..."
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $python = Find-Python
    if (-not $python) { Write-Host "Python installed but not found: open a new PowerShell and run this again."; exit 1 }
  }
  Write-Host "Preparing the folder .aurora-camera with $python ..."
  & $python -m venv $venv
  if ($LASTEXITCODE -ne 0) { Write-Host "the folder could not be made"; exit 1 }
}

# a check that writes nothing on stderr: 0 when both are installed
& $vpy -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('cv2') and u.find_spec('pygrabber') else 1)"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing OpenCV and pygrabber (once)..."
  & $vpy -m pip install --disable-pip-version-check --quiet opencv-python pygrabber
  if ($LASTEXITCODE -ne 0) { Write-Host "the installation did not succeed: is the PC on the internet?"; exit 1 }
}

$agent = Join-Path $here "astro_camera.py"
if ($List) { & $vpy $agent --list; exit 0 }
if (-not $Url -or -not $Key) { Write-Host "Give -Url and -Key: the command is in Aurora's collimation page."; exit 1 }
$a = @($agent, "--url", $Url, "--key", $Key)
if ($Insecure) { $a += "--insecure" }
& $vpy @a
