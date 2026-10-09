# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora for Windows 10/11 (x64): the installer — install.sh's steps and questions, this system's way. Phase 3 of the
# port: the reasoner in the cloud (the local llama.cpp comes later); search, memory and documents stay on this computer.
#
#   PowerShell as administrator, in the folder of the downloaded Aurora:
#   powershell -ExecutionPolicy Bypass -File Aurora_windows\install.ps1            # questions on screen
#   ... -Yes                    every default (the cloud key from AURORA_INSTALL_CLOUD_KEY, never on a command line)
#   ... -Root D:\Aurora         where Aurora lives (default C:\Aurora)
#   ... -NoOptionalModels       no optional feature    -NoServices   no scheduled tasks
# Every answer can come from AURORA_INSTALL_<NAME> as in install.sh (NAME, PROVIDER, MODEL, REACH, HARVEST...).
# Run again to update: the code is copied over the old one; .env, the vault, the models and the users' data stay.
[CmdletBinding()]
param([switch]$Yes, [string]$Root = "C:\Aurora", [switch]$NoOptionalModels, [switch]$NoServices)

# Continue: in Windows PowerShell 5.1 a native program's line on stderr (pip, Hugging Face warnings) becomes an error
# record and «Stop» would end the installer there; every step checks its exit code instead
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path          # Aurora_windows
$Repo = Split-Path -Parent $Here                                 # the Linux code it is built from
$Log = Join-Path $Repo "install-windows.log"
$IT = (Get-Culture).Name -like "it*"
try { Start-Transcript -Path $Log -Append | Out-Null } catch { }

function T([string]$it, [string]$en) { if ($IT) { $it } else { $en } }
function Step([string]$s) { Write-Host ""; Write-Host "━━ $s ━━" -ForegroundColor Cyan }
function Ok([string]$s) { Write-Host "  ✓ $s" -ForegroundColor Green }
function Warn([string]$s) { Write-Host "  ! $s" -ForegroundColor Yellow }
function Die([string]$s) {
    Write-Host ""; Write-Host "✗ $s" -ForegroundColor Red
    Write-Host "$(T 'Dettagli in' 'Details in') $Log"
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
function Ask([string]$q, [string]$d, [string]$name = "") {
    if ($name) { $v = [Environment]::GetEnvironmentVariable("AURORA_INSTALL_$name"); if ($v) { return $v } }
    if ($Yes) { return $d }
    $a = Read-Host "  $q [$d]"
    if ($a) { return $a.Trim() } else { return $d }
}
function YesNo([string]$q, [string]$d, [string]$name = "") { return (Ask "$q (y/n)" $d $name) -match '^(y|s|si|sì|yes)$' }
function Secret([string]$q) {
    $s = Read-Host "  $q" -AsSecureString
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
function Refresh-Path {
    # what winget just added, before this session's own (a program the owner put on the path for this window stays)
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
}
# Aurora's Python, always in UTF-8 (Windows would read her texts as cp1252)
function Py { & $script:VPy -X utf8 @args; if ($LASTEXITCODE -ne 0) { throw "python $($args -join ' '): exit $LASTEXITCODE" } }
function PyOut { $o = & $script:VPy -X utf8 @args; if ($LASTEXITCODE -ne 0) { throw "python $($args -join ' '): exit $LASTEXITCODE" }; return $o }

Write-Host "A.U.R.O.R.A. — $(T 'installazione Windows' 'Windows installation') $(Get-Date -Format 'yyyy-MM-dd HH:mm')  ($Root)" -ForegroundColor White

# ---------------------------------------------------------------------------------------------------
Step "1. $(T 'Controllo del sistema' 'System check')"
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($me)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Die (T "Apri PowerShell come amministratore (tasto destro → Esegui come amministratore) e rilancia." "Open PowerShell as administrator (right click → Run as administrator) and run it again.")
}
$OwnerAccount = $me.Name                                          # COMPUTER\name: the services run as this user
$os = Get-CimInstance Win32_OperatingSystem
if (-not [Environment]::Is64BitOperatingSystem -or [int]$os.BuildNumber -lt 19041) { Die "Windows 10 2004+ / 11 x64" }
Ok "$($os.Caption) $($os.Version)"
if (-not (Test-Path (Join-Path $Here "build.py"))) { Die (T "lancia install.ps1 dalla cartella Aurora_windows del download" "run install.ps1 from the Aurora_windows folder of the download") }
# Windows does not tell C:\aurora from C:\Aurora: the download and the installation must be two folders
if ([IO.Path]::GetFullPath($Root).TrimEnd('\') -ieq [IO.Path]::GetFullPath($Repo).TrimEnd('\')) {
    Die "$(T 'il download è già in' 'the download is already in') ${Root}: $(T 'spostalo (es. in Download) o usa -Root' 'move it (e.g. to Downloads) or use -Root')"
}
$drive = Get-PSDrive ($Root.Substring(0, 1))
$Free = [int][math]::Floor($drive.Free / 1GB)
Ok "$(T 'spazio libero' 'free space'): $Free GB"
if ($Free -lt 15) { Die (T "servono almeno 15 GB liberi su $($drive.Name):" "at least 15 GB free needed on $($drive.Name):") }

# ---------------------------------------------------------------------------------------------------
Step "2. $(T 'Programmi (winget)' 'Programs (winget)')"
# winget for a user who never signed in on the desktop (a remote session): registered, and its catalogue added
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    try { Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe -ErrorAction Stop } catch { }
    $env:Path += ";$env:LOCALAPPDATA\Microsoft\WindowsApps"
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Die (T "winget non trovato: installa «Programma di installazione app» dal Microsoft Store" "winget not found: install «App Installer» from the Microsoft Store") }
winget search --id Python.Python.3.14 --exact --source winget --accept-source-agreements *> $null
if ($LASTEXITCODE -ne 0) {
    $msix = Join-Path $env:TEMP "winget-source2.msix"
    try { Invoke-WebRequest https://cdn.winget.microsoft.com/cache/source2.msix -OutFile $msix -UseBasicParsing -ErrorAction Stop
          Add-AppxPackage $msix -ErrorAction Stop } catch { Die "winget source: $_" }
    winget search --id Python.Python.3.14 --exact --source winget --accept-source-agreements *> $null
    if ($LASTEXITCODE -ne 0) { Die (T "il catalogo di winget non risponde" "winget's catalogue does not answer") }
}
function Get-Package([string]$id, [string]$label, [bool]$machine = $true) {
    winget list --id $id --exact --accept-source-agreements *> $null
    if ($LASTEXITCODE -eq 0) { Ok "$label"; return }
    $scope = @(); if ($machine) { $scope = @("--scope", "machine") }
    winget install --id $id --exact @scope --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "winget install $id ($LASTEXITCODE)" }
    Ok "$label ($(T 'installato' 'installed'))"
}
Get-Package "Python.Python.3.14" "Python 3.14"
Get-Package "Microsoft.VCRedist.2015+.x64" "Visual C++ Redistributable" $false   # torch's DLLs (WinError 1114 without it)
Get-Package "Gyan.FFmpeg" "FFmpeg"
Get-Package "oschwartz10612.Poppler" "Poppler (PDF)"
Get-Package "CaddyServer.Caddy" "Caddy (HTTPS)"
Refresh-Path
$SysPy = "$env:ProgramFiles\Python314\python.exe"
if (-not (Test-Path $SysPy)) { Die "Python 3.14: $SysPy" }
$Caddy = (Get-Command caddy -ErrorAction SilentlyContinue).Source
$PdfToText = (Get-Command pdftotext -ErrorAction SilentlyContinue).Source
if (-not $Caddy) { Die "caddy.exe" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Warn (T "ffmpeg non trovato nel PATH: niente video e audio" "ffmpeg not in PATH: no video nor audio") }
$Browser = ""
foreach ($b in @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")) {
    if (Test-Path $b) { $Browser = $b; break }
}
if ($Browser) { Ok "$(T 'browser per i PDF' 'browser for PDFs'): $Browser" } else { Warn (T "nessun Chrome/Edge: i PDF delle pagine non saranno disponibili" "no Chrome/Edge: page PDFs will not be available") }

# ---------------------------------------------------------------------------------------------------
Step "3. $(T 'GPU o cloud' 'GPU or cloud')"
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) { & nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | ForEach-Object { "  $_" } }
Warn (T "su Windows il ragionatore locale (llama.cpp) non c'è ancora: Aurora ragiona con un modello cloud; ricerca, memoria e documenti restano su questo computer." "on Windows the local reasoner (llama.cpp) is not there yet: Aurora reasons with a cloud model; search, memory and documents stay on this computer.")
if (-not (YesNo (T "Installare Aurora con il ragionatore cloud?" "Install Aurora with the cloud reasoner?") "y" "CLOUD")) { Die (T "su Windows, per ora, serve il cloud" "on Windows, for now, the cloud is needed") }

# ---------------------------------------------------------------------------------------------------
Step "4. $(T 'Le tue scelte' 'Your choices')"
$Fresh = -not (Test-Path (Join-Path $Root ".env"))
if (-not $Fresh) { Ok (T ".env esistente: aggiorno il codice, le scelte restano quelle di prima" "existing .env: the code is updated, the choices stay as they were") }
else {
    $full = ""; try { $full = (Get-LocalUser -Name $env:USERNAME -ErrorAction Stop).FullName } catch { }
    if (-not $full) { $full = $env:USERNAME }
    $OwnerName = Ask (T "Il tuo nome (come ti chiamerà Aurora)" "Your name (what Aurora will call you)") $full "NAME"
    $AName = Ask (T "Il nome della tua assistente" "Your assistant's name") "Aurora" "ASSISTANT"
    Write-Host "  $(T 'Personalità:' 'Personality:') 1) $(T 'Aurora, scienziata poliedrica' 'Aurora, the many-souled scientist')  2) $(T 'Filosofa' 'Philosopher')  3) $(T 'Empatica' 'Empathic')  4) $(T 'Pratica' 'Practical')"
    $Persona = @{ "2" = "philosopher"; "3" = "empathic"; "4" = "practical" }[(Ask (T "Scegli 1-4" "Choose 1-4") "1" "PERSONALITY")]
    if (-not $Persona) { $Persona = "aurora" }
    $AGender = "female"; if ((Ask (T "Voce femminile o maschile (f/m)" "Female or male voice (f/m)") "f" "VOICE") -match '^[mM]') { $AGender = "male" }
    $ULang = Ask (T "Lingua (it_IT / en_US)" "Language (it_IT / en_US)") $(if ($IT) { "it_IT" } else { "en_US" }) "LANG"
    # where Aurora is used from: the phone needs an address it can reach (this computer's on the home network)
    $LanIp = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1).IPv4Address.IPAddress
    Write-Host "  $(T 'Da dove userai Aurora?' 'Where will you use Aurora from?')"
    Write-Host "    1) $(T 'solo da questo computer' 'this computer only') (https://localhost)"
    if ($LanIp) { Write-Host "    2) $(T 'anche dal telefono e dagli altri dispositivi di casa' 'also from the phone and the other devices at home') (https://$LanIp)" }
    Write-Host "    3) $(T 'da un mio nome di dominio' 'from a domain name of mine')"
    $Reach = Ask (T "Scegli 1-3" "Choose 1-3") "1" "REACH"
    $Domain = "localhost"; $Aliases = ""
    switch ($Reach) {
        "2" { if (-not $LanIp) { Die (T "nessun indirizzo di rete trovato" "no network address found") }
              $Domain = $LanIp; $Aliases = "$($env:COMPUTERNAME.ToLower()).local,localhost" }
        "3" { $Domain = Ask (T "Il tuo nome (es. aurora.example.com)" "Your name (e.g. aurora.example.com)") "" "DOMAIN_NAME"
              if (-not $Domain) { Die (T "nome vuoto" "empty name") } }
        default { $Reach = "1" }
    }
    $CertFile = ""; $KeyFile = ""
    if ($Reach -eq "3" -and (YesNo "$(T 'Hai un tuo certificato per' 'Do you have your own certificate for') ${Domain}?" "n")) {
        $CertFile = Ask (T "file del certificato (fullchain)" "certificate file (fullchain)") ""
        $KeyFile = Ask (T "file della chiave privata" "private key file") ""
        if (-not (Test-Path $CertFile) -or -not (Test-Path $KeyFile)) { Die (T "certificato o chiave non leggibili" "certificate or key not readable") }
    }
    $Port = Ask (T "Porta HTTPS" "HTTPS port") "443" "PORT"
    # the HTTP port: the phones' certificate and the redirect to HTTPS; another web server on 443 likely has 80 too
    $HPort = Ask (T "Porta HTTP (certificato per i telefoni, rimando all'HTTPS)" "HTTP port (the phones' certificate, redirect to HTTPS)") $(if ($Port -eq "443") { "80" } else { "8080" }) "HTTP_PORT"
    if ($HPort -eq $Port) { Die (T "le due porte devono essere diverse" "the two ports must differ") }
    Write-Host ""
    Write-Host "  $(T 'Ragionatore cloud. Cosa esce da questo computer: le domande, i passaggi dei documenti che servono alla risposta, la conversazione recente.' 'Cloud reasoner. What leaves this computer: the questions, the passages of the documents an answer needs, the recent conversation.')"
    Write-Host "  $(T 'Prima di uscire ogni testo è mascherato: email, telefoni, IBAN, carte, codice fiscale, partita IVA, targhe, indirizzi, IP, chiavi e password, il tuo nome e le parole che indicherai sono sostituiti da segnaposto e rimessi nella risposta.' 'Before leaving every text is masked: e-mails, phones, IBANs, cards, tax codes, VAT numbers, plates, addresses, IPs, keys and passwords, your name and the words you list are replaced by placeholders and put back in the answer.')"
    Write-Host "  $(T 'NON si maschera il contenuto in sé (di cosa parla un documento) né le foto. Il provider lo tratta secondo i suoi termini.' 'NOT masked: the content itself (what a document is about) and photos. The provider handles it under its own terms.')"
    Write-Host "  $(T "Per questo serve l'esenzione dal livello B del codice di condotta (regola 9), firmata alla fine con la chiave di questa installazione." 'This is why the exemption from level B of the code of conduct (rule 9) is needed, signed at the end with this installation''s key.')"
    if (-not (YesNo (T "Va bene così?" "Is that all right?") "y" "CLOUD_OK")) { Die (T "su Windows, per ora, serve il cloud" "on Windows, for now, the cloud is needed") }
    Write-Host "  Provider: 1) Anthropic (Claude)  2) OpenAI  3) Google Gemini  4) Mistral  5) OpenRouter  6) xAI Grok  7) Claude Code ($(T 'abbonamento' 'subscription'))"
    Write-Host "            8) $(T 'altro servizio compatibile OpenAI (server aziendale, vLLM, LM Studio, Ollama...)' 'another OpenAI-compatible service (company server, vLLM, LM Studio, Ollama...)')"
    $CUrlBase = ""; $CKeyName = ""
    switch (Ask (T "Scegli 1-8" "Choose 1-8") "1" "PROVIDER") {
        "2" { $Provider = "openai"; $CKeyName = "AURORA_OPENAI_API_KEY" }
        "3" { $Provider = "google"; $CKeyName = "AURORA_GOOGLE_API_KEY" }
        "4" { $Provider = "mistral"; $CKeyName = "AURORA_MISTRAL_API_KEY" }
        "5" { $Provider = "openrouter"; $CKeyName = "AURORA_OPENROUTER_API_KEY" }
        "6" { $Provider = "xai"; $CKeyName = "AURORA_XAI_API_KEY" }
        "7" { $Provider = "claude_code" }
        "8" { $Provider = "custom"; $CKeyName = "AURORA_CUSTOM_API_KEY"
              $CUrlBase = Ask (T "Indirizzo del servizio (finisce con /v1)" "The service's address (ending in /v1)") "" "CLOUD_URL"
              if ($CUrlBase -notmatch '^https?://') { Die "$(T 'indirizzo non valido' 'invalid address'): $CUrlBase" } }
        default { $Provider = "anthropic"; $CKeyName = "AURORA_ANTHROPIC_API_KEY" }
    }
    $CKey = $env:AURORA_INSTALL_CLOUD_KEY
    $ClaudeBin = ""
    if ($Provider -eq "claude_code") {
        $ClaudeBin = (Get-Command claude -ErrorAction SilentlyContinue).Source
        if (-not $ClaudeBin) { Die (T "Claude Code non trovato: installalo, collega il tuo account (comando claude) e rilancia" "Claude Code not found: install it, sign in (the claude command) and run again") }
        Ok "Claude Code: $ClaudeBin"
    } elseif (-not $CKey -and $Provider -eq "custom") {
        if (-not $Yes) { $CKey = Secret (T "Chiave API (non viene mostrata; vuota se il servizio non la chiede)" "API key (not shown; empty if the service asks none)") }
    } elseif (-not $CKey) {
        if ($Yes) { Die "AURORA_INSTALL_CLOUD_KEY" }
        $CKey = Secret (T "Chiave API (non viene mostrata)" "API key (not shown)")
        if (-not $CKey) { Die (T "chiave vuota" "empty key") }
    }
    # a new Aurora starts with an empty vault: the harvester fills it (owner, 2026-10-09: on unless the owner says no)
    Write-Host "  $(T 'Aurora parte con il vault vuoto: la raccolta lo riempie con articoli e voci aperte (arXiv, Wikipedia, Europe PMC…); si cambia nella pagina Harvester.' 'Aurora starts with an empty vault: harvesting fills it with open papers and articles (arXiv, Wikipedia, Europe PMC…); changed on the Harvester page.')"
    $Harvest = 0; if (YesNo (T "Accendere la raccolta automatica di conoscenza?" "Switch automatic knowledge harvesting on?") "y" "HARVEST") { $Harvest = 1 }
    # the areas: what the harvest collects and the seed's answers (shadows) this installation starts with (owner, 9 Oct)
    Write-Host "  $(T 'Argomenti che ti interessano: la raccolta parte da questi e Aurora arriva già con le risposte pronte (ombre) su questi temi, nella tua lingua. Si cambia nella pagina Conoscenza.' 'Topics you care about: harvesting starts from these and Aurora comes with ready answers (shadows) on them, in your language. Changed on the Knowledge page.')"
    $DomainsPy = Join-Path $Repo "sys\core\script\sys_domains.py"
    & $SysPy -X utf8 -I $DomainsPy --list (T "it" "en")
    while ($true) {
        $Domains = Ask (T "Numeri separati da virgola, oppure tutte" "Numbers separated by commas, or all") (T "tutte" "all") "DOMAINS"
        & $SysPy -X utf8 -I $DomainsPy --check $Domains
        if ($LASTEXITCODE -eq 0) { break }
        if ($Yes) { Die "AURORA_INSTALL_DOMAINS=$Domains" }
    }
    Write-Host "  $(T 'Tipo di installazione: single (una persona: tu) o multi (più persone, ognuna con la sua cartella e la sua memoria privata)' 'Installation type: single (one person: you) or multi (several people, each with their folder and private memory)')"
    $UMode = Ask (T "single o multi" "single or multi") "single" "MODE"
    if ($UMode -ne "multi") { $UMode = "single" }
}

# ---------------------------------------------------------------------------------------------------
Step "5. $(T 'Codice e Python (venv)' 'Code and Python (venv)')"
# built from the Linux code next to this folder (build.py: the port's files and rewrites), then copied over Aurora's
# folder: only code moves, .env and the data are never touched (robocopy without /PURGE deletes nothing)
$Stage = Join-Path $env:TEMP "aurora-build-windows"
& $SysPy -X utf8 (Join-Path $Here "build.py") --out $Stage | Select-Object -Last 2 | ForEach-Object { "  $_" }
if ($LASTEXITCODE -ne 0) { Die "build.py" }
New-Item -ItemType Directory -Force -Path $Root | Out-Null
robocopy $Stage $Root /E /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
if ($LASTEXITCODE -ge 8) { Die "robocopy $Stage → $Root ($LASTEXITCODE)" }
Ok "$(T 'codice in' 'code in') $Root"
Set-Location $Root
$script:VPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VPy)) { & $SysPy -m venv (Join-Path $Root ".venv"); if ($LASTEXITCODE -ne 0) { Die "venv" } }
& $VPy -m pip install -q --upgrade pip | Out-Null
# the Linux lock pins Linux wheels (CUDA among them): Windows takes requirements.txt's versions from PyPI
& $VPy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Die "pip install -r requirements.txt" }
Ok "$(& $VPy --version), torch $(PyOut -c 'import torch; print(torch.__version__)')"

if ($Fresh) {
    Step "5b. $(T 'Modello cloud' 'Cloud model')"
    # the key goes by the environment, never on a command line (visible to every user of this computer)
    $env:AURORA_INSTALL_CLOUD_URL = $CUrlBase
    $env:AURORA_INSTALL_CLOUD_KEY = $CKey
    $List = @(& $VPy -X utf8 sys\core\script\sys_cloud_setup.py models $Provider)
    if ($LASTEXITCODE -ne 0) { Die "$(T 'il provider rifiuta la chiave' 'the provider refuses the key'): $($List | Select-Object -Last 1)" }
    $i = 0; $List | Select-Object -First 12 | ForEach-Object { $i++; Write-Host ("  {0,3}) {1}" -f $i, $_) }
    $CModel = Ask (T "Modello (numero o nome; il primo è consigliato)" "Model (number or name; the first is advised)") $List[0] "MODEL"
    if ($CModel -match '^\d+$') { $CModel = $List[[int]$CModel - 1] }
    if (-not $CModel) { Die (T "modello non valido" "invalid model") }
    $out = & $VPy -X utf8 sys\core\script\sys_cloud_setup.py try $Provider $CModel
    if ($LASTEXITCODE -ne 0) { Die "$Provider ${CModel}: $($out | Select-Object -Last 1)" }
    Remove-Item Env:\AURORA_INSTALL_CLOUD_KEY -ErrorAction SilentlyContinue
    Ok "$Provider $CModel $(T 'risponde' 'answers')"
}

# ---------------------------------------------------------------------------------------------------
Step "6. $(T 'Profilo hardware e funzioni facoltative' 'Hardware profile and optional features')"
$ProfileJson = (PyOut sys\core\script\sys_profile.py --json --cloud) -join "`n"
$ProfileFile = Join-Path $env:TEMP "aurora-profile.json"
[IO.File]::WriteAllText($ProfileFile, $ProfileJson, (New-Object System.Text.UTF8Encoding($false)))
$Pick = @(); $Models = @()
if ($Fresh -and -not $NoOptionalModels) {
    foreach ($row in (PyOut sys\core\script\sys_doctor.py --groups $ProfileFile)) {
        $g, $size, $fits, $def, $why, $lit, $len, $mods, $todo = $row -split '\|'
        $label = T $lit $len
        if ($g -eq "voice") { Warn "$label`: $(T 'su Windows non ancora (Piper)' 'not on Windows yet (Piper)')"; continue }
        if ($fits -ne "1") { Warn "$label`: $(T 'non adatta a questa macchina' 'not for this machine') ($why)"; continue }
        $d = if ($def -eq "1") { "y" } else { "n" }
        if (YesNo "$label (+$size GB)?" $d) { $Pick += $g; $Models += $mods }
    }
}
Ok "$(T 'scelte' 'chosen'): $(if ($Pick) { $Pick -join ', ' } else { T 'nessuna' 'none' })"

# ---------------------------------------------------------------------------------------------------
Step "7. $(T 'Configurazione (.env)' 'Configuration (.env)')"
if (-not $Fresh) {
    Py sys\core\script\sys_env_sync.py | Out-Null
} else {
    $svcUser = ($env:USERNAME.ToLower() -replace '[^a-z0-9._-]', '-').Trim('.')        # a folder name: usr\<name>
    $sets = @("AURORA_ROOT=$($Root -replace '\\', '/')", "AURORA_OWNER_NAME=$OwnerName", "AURORA_ASSISTANT_NAME=$AName",
              "AURORA_PERSONALITY=$Persona", "AURORA_ASSISTANT_GENDER=$AGender", "AURORA_LANG_DEFAULT=$ULang",
              "AURORA_DOMAIN=$Domain", "AURORA_HTTPS_PORT=$Port", "AURORA_HTTP_PORT=$HPort", "AURORA_TLS_MODE=internal", "AURORA_UPDATE_MODE=notify",
              "AURORA_SERVICE_USER=$svcUser", "AURORA_USER_MODE=$UMode", "AURORA_DOMAIN_ALIASES=$Aliases",
              "AURORA_HARVEST_ENABLED=$Harvest", "AURORA_LLM_BACKEND=cloud", "AURORA_CLOUD_PROVIDER=$Provider",
              "AURORA_CLOUD_MODEL=$CModel", "AURORA_CADDY_BIN=$($Caddy -replace '\\', '/')", "AURORA_TTS=0")
    if ($PdfToText) { $sets += "AURORA_PDFTOTEXT_BIN=$($PdfToText -replace '\\', '/')" }
    if ($Browser) { $sets += "AURORA_CHROME_BIN=$($Browser -replace '\\', '/')" }
    if ($Provider -eq "claude_code") { $sets += "AURORA_CLAUDE_CODE_BIN=$($ClaudeBin -replace '\\', '/')"; $sets += "AURORA_CLAUDE_CODE_MODEL=$CModel" }
    if ($Provider -eq "custom") { $sets += "AURORA_CUSTOM_BASE_URL=$CUrlBase" }
    foreach ($kv in (($ProfileJson | ConvertFrom-Json).env.PSObject.Properties)) {
        if ($kv.Name -ne "AURORA_LLM_BACKEND") { $sets += "$($kv.Name)=$($kv.Value)" }
    }
    if ($Pick -notcontains "dreams") { $sets += "AURORA_IMAGE_ENABLED=0" }
    $argv = @(); foreach ($s in $sets) { $argv += @("--set", $s) }
    if ($CKeyName -and $CKey) { [Environment]::SetEnvironmentVariable($CKeyName, $CKey, "Process"); $argv += @("--set-env", $CKeyName) }
    Py sys\core\script\sys_env_sync.py @argv | Out-Null
    if ($CKeyName) { Remove-Item "Env:\$CKeyName" -ErrorAction SilentlyContinue }
}
Move-Item -Force (Join-Path $Root ".env.proposed") (Join-Path $Root ".env")
Py -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; sys_config.get()"
# Aurora's folder: its owner, SYSTEM and the Administrators only (C:\ lets every user read by default)
Py -c "import sys; sys.path.insert(0, 'sys/core'); from pathlib import Path; from aurora import sys_platform; sys_platform.current().make_private(Path(r'$Root'))"
Ok (T ".env valido; la cartella è leggibile solo da te e dagli amministratori" ".env valid; the folder is readable by you and the administrators only")
if ($Fresh -and $CertFile) {
    $env:AURORA_INSTALL_CERT = $CertFile; $env:AURORA_INSTALL_KEY = $KeyFile
    Py -c "import os, sys; sys.path.insert(0, 'sys/core'); from pathlib import Path; from aurora import net_https, sys_config; c = sys_config.get(); info = net_https.check_pair(Path(os.environ['AURORA_INSTALL_CERT']).read_bytes(), Path(os.environ['AURORA_INSTALL_KEY']).read_bytes(), str(c['AURORA_DOMAIN'])); [net_https._write_private(c.path(k), Path(os.environ[e]).read_bytes()) for k, e in (('AURORA_TLS_CERT', 'AURORA_INSTALL_CERT'), ('AURORA_TLS_KEY', 'AURORA_INSTALL_KEY'))]; sys_config.write_env(c.env_file, {'AURORA_TLS_MODE': 'files'}); print(info['names'])"
    Ok (T "il tuo certificato è in uso" "your certificate is in use")
}
$status = (PyOut -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; print(sys_config.get().path('AURORA_STATUS_DIR'))") | Select-Object -Last 1
if (-not (Test-Path (Join-Path $status "users_layout.json"))) {
    & $VPy -X utf8 sys\core\script\sys_users_migrate.py migrate --yes --fresh | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok (T "struttura per utente: usr\$svcUser\" "per-user layout: usr\$svcUser\") }
    else { Warn (T "struttura per utente non creata: sys_users_migrate.py plan" "per-user layout not made: sys_users_migrate.py plan") }
}
if ($Domains) {                                   # asked on a new installation only: the Knowledge page's choices stay
    & $VPy -X utf8 sys\core\script\sys_domains.py --set $Domains | ForEach-Object { Ok $_ }
    if ($LASTEXITCODE -ne 0) { Die "sys_domains.py --set $Domains" }
}

# ---------------------------------------------------------------------------------------------------
Step "8. $(T 'Modelli (Hugging Face, revisioni fissate, SHA-256 verificati)' 'Models (Hugging Face, pinned revisions, SHA-256 checked)')"
Py sys\core\script\sys_models_fetch.py --models "embedder,reranker" --yes        # quoted: a bare a,b is an array here | Select-Object -Last 1 | ForEach-Object { "  $_" }
if ($Models) { Py sys\core\script\sys_models_fetch.py --models ($Models -join ",") --yes | Select-Object -Last 1 | ForEach-Object { "  $_" } }
# how many passages this CPU re-ranks in 15 s (C229: the fixed 30 took minutes on 2 cores)
$cal = & $VPy -X utf8 sys\core\script\sys_calibrate.py --write --say (T "it" "en") 2>$null | Select-Object -Last 1
if ($LASTEXITCODE -eq 0) { Ok "$(T 'audit della macchina' 'machine audit'): $cal" } else { Warn (T "audit della macchina non riuscito: restano i valori del profilo cloud" "machine audit failed: the cloud profile values stay") }

# ---------------------------------------------------------------------------------------------------
Step "9. $(T 'Codice di condotta: la chiave di questa installazione' "Code of conduct: this installation's key")"
Py sys\core\script\sys_ethics_sign.py setup --exempt | ForEach-Object { "  $_" }
Py sys\core\script\sys_ethics_sign.py check | ForEach-Object { "  $_" }

# ---------------------------------------------------------------------------------------------------
if ($NoServices) {
    Step "$(T 'Servizi non installati' 'Services not installed') (-NoServices)"
    Write-Host "  .venv\Scripts\python.exe -X utf8 sys\core\script\sys_install_tasks.py --user $OwnerAccount"
} else {
    Step "10. $(T 'Servizi (Utilità di pianificazione) e HTTPS' 'Services (Task Scheduler) and HTTPS')"
    & $VPy -X utf8 sys\core\script\sys_install_tasks.py --user $OwnerAccount | ForEach-Object { "  $_" }
    if ($LASTEXITCODE -ne 0) { Die (T "servizi" "services") }
    $admin = (PyOut -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; print(sys_config.get()['AURORA_CADDY_ADMIN'])") | Select-Object -Last 1
    # Caddy's root into the computer's store (LocalMachine\Root, as the administrator, no dialog): «caddy trust» writes the
    # user's store, which asks for a confirmation in a window and fails without one (a remote session, 9 Oct)
    $trusted = $false
    for ($i = 0; $i -lt 20 -and -not $trusted; $i++) {
        try {
            $pem = (Invoke-RestMethod "http://$admin/pki/ca/local" -TimeoutSec 5).root_certificate
            $crt = Join-Path $env:TEMP "aurora-caddy-root.crt"
            [IO.File]::WriteAllText($crt, $pem)
            Import-Certificate -FilePath $crt -CertStoreLocation Cert:\LocalMachine\Root -ErrorAction Stop | Out-Null
            $trusted = $true
        } catch { Start-Sleep -Seconds 3 }
    }
    if ($trusted) { Ok (T "certificato locale di Caddy riconosciuto da questo computer" "Caddy local certificate trusted on this computer") }
    else { Warn (T "certificato di Caddy non registrato: il browser chiederà un'eccezione" "Caddy's certificate not registered: the browser will ask for an exception") }
    $cfgDomain = (PyOut -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; c = sys_config.get(); print(c['AURORA_DOMAIN'], c['AURORA_HTTPS_PORT'], c['AURORA_HTTP_PORT'])") | Select-Object -Last 1
    $d, $hp, $pp = $cfgDomain -split ' '
    Get-NetFirewallRule -DisplayName "Aurora HTTPS" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($d -ne "localhost") {
        # the phone and the devices at home: this network only, never from outside it
        New-NetFirewallRule -DisplayName "Aurora HTTPS" -Direction Inbound -Protocol TCP -LocalPort @([int]$hp, [int]$pp) -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
        Ok "$(T 'firewall di Windows: porte' 'Windows Firewall: ports') $hp, $pp $(T 'aperte alla rete di casa' 'open to the home network')"
    }
}

# ---------------------------------------------------------------------------------------------------
Step "11. $(T 'Pronta' 'Ready')"
if ($NoServices) { & $VPy -X utf8 sys\core\script\sys_ready.py --pending } else { & $VPy -X utf8 sys\core\script\sys_ready.py }
& $VPy -X utf8 sys\core\script\sys_doctor.py
Write-Host "  $(T "Log dell'installazione" 'Installation log'): $Log"
try { Stop-Transcript | Out-Null } catch { }
