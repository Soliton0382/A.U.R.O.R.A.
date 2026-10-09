#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# A.U.R.O.R.A. installer: from a fresh `git clone` to a running Aurora sized for this machine.
#
#   ./install.sh                     # asks a few questions (defaults in brackets)
#   ./install.sh --yes               # takes every default
#   options: --no-services (stop before systemd/HTTPS: for a second copy on a machine that already runs Aurora)
#   unattended: each answer from AURORA_INSTALL_<NAME> (NAME, ASSISTANT, PERSONALITY 1-4, VOICE f/m, LANG, DOMAIN, PORT,
#            REACH 1-3 (this computer, also the home network, a name of yours), EXEMPT y/n, MODE single/multi,
#            REASONER 1-2 or BACKEND local/cloud, CLOUD y/n, PROVIDER 1-8, CLOUD_URL (provider 8), MODEL), e.g.
#            AURORA_INSTALL_MODE=multi ./install.sh --yes; the cloud key from AURORA_INSTALL_CLOUD_KEY (never asked twice)
#   without an NVIDIA GPU of 16 GB (or AURORA_INSTALL_BACKEND=cloud): a cloud reasoner (Anthropic, OpenAI, Gemini,
#            Mistral, OpenRouter, xAI or Claude Code), every call masked; the encoder and re-ranker on the CPU
#            --no-optional-models (only the required models; add others later with sys_models_fetch.py)
#            --with-video (also the video model under --yes, 34 GB)   --reset-venv   --skip-build
#
# Steps: system check → packages → NVIDIA (driver present, CUDA toolkit 13) or cloud → your answers → venv → cloud
# key and model checked → hardware profile → .env → models from Hugging Face → llama.cpp for your GPUs (not in the
# cloud) → tests → code of conduct key → systemd units + HTTPS → health check → the address to open.
# Every step can be run again: what is done is not done twice.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
YES=0; SERVICES=1; OPTIONAL=1; RESET_VENV=0; BUILD=1; VIDEO=0
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --no-services) SERVICES=0 ;;
    --no-optional-models) OPTIONAL=0 ;;
    --with-video) VIDEO=1 ;;
    --reset-venv) RESET_VENV=1 ;;
    --skip-build) BUILD=0 ;;
    -h|--help) sed -n '4,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done
exec > >(tee -a "$ROOT/install.log") 2>&1
IT=0; case "${LANG:-}" in it*) IT=1 ;; esac
t() { if [ "$IT" = 1 ]; then echo "$1"; else echo "$2"; fi; }
step() { echo; echo -e "\e[1;36m━━ $* ━━\e[0m"; }
ok() { echo -e "  \e[32m✓\e[0m $*"; }
warn() { echo -e "  \e[33m!\e[0m $*"; }
die() { echo -e "\n\e[31m✗ $*\e[0m"; echo "$(t 'Dettagli in' 'Details in') $ROOT/install.log"; exit 1; }
ask() {  # ask "question" default [NAME] -> echo answer; AURORA_INSTALL_<NAME> answers without asking
  local q="$1" d="$2" a v="AURORA_INSTALL_${3:-}"
  if [ -n "${3:-}" ] && [ -n "${!v:-}" ]; then echo "${!v}"; return; fi
  if [ "$YES" = 1 ]; then echo "$d"; return; fi
  drain
  read -r -p "  $q [$d]: " a </dev/tty
  echo "${a:-$d}"
}
drain() {  # what was typed before a question is not its answer (owner's colleague, 9 Oct: «Where will you use Aurora
  # from» and the provider were skipped — an Enter arriving twice, as some terminals send CR+LF, answered the next one)
  while read -r -t 0 </dev/tty 2>/dev/null; do read -r -t 1 _ </dev/tty || break; done
}
yesno() {  # yesno "question" y|n [NAME] -> exit status
  local a; a=$(ask "$1 (y/n)" "$2" "${3:-}")
  case "$a" in y|Y|s|S|si|sì|yes) return 0 ;; *) return 1 ;; esac
}
echo -e "\e[1mA.U.R.O.R.A.\e[0m — $(t 'installazione' 'installation') $(date '+%Y-%m-%d %H:%M')  ($ROOT)"

# ---------------------------------------------------------------------------------------------------
step "1. $(t 'Controllo del sistema' 'System check')"
# an Aurora already installed here (its .env): an update — every choice kept, nothing asked again (owner, 9 Oct:
# «allineiamo l'installer Linux», as install.ps1 does; C234)
UPDATE=0
if [ -f .env ]; then
  UPDATE=1; OPTIONAL=0; EXEMPT=0                    # EXEMPT=0: setup leaves an existing exemption as it is
  PORT=$(sed -n 's/^AURORA_HTTPS_PORT=//p' .env | tail -1); UMODE=$(sed -n 's/^AURORA_USER_MODE=//p' .env | tail -1)
  ok "$(t 'Aurora è già installata qui: aggiorno codice, ambiente e servizi; le tue scelte restano quelle del .env' 'Aurora is already installed here: code, environment and services are updated; your choices stay as in .env')"
fi
[ "$(id -u)" != 0 ] || die "$(t 'Lancialo come utente normale: sudo verrà chiesto quando serve.' 'Run it as a normal user: sudo is asked when needed.')"
. /etc/os-release
ok "$PRETTY_NAME, kernel $(uname -r)"
case "$ID:$VERSION_ID" in ubuntu:26.04*) ;; ubuntu:24.04*) warn "$(t 'Ubuntu 24.04: non misurato (consigliato 26.04)' 'Ubuntu 24.04: not measured (26.04 recommended)')" ;;
  *) warn "$(t 'sistema non provato: gli script usano apt e i driver di Ubuntu' 'untested system: the scripts use apt and Ubuntu drivers')" ;; esac
command -v sudo >/dev/null || die "sudo"
FREE=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc 0-9)
ok "$(t 'spazio libero' 'free space'): ${FREE} GB"
# measured on the reference machine: .venv 6.1 GB, encoder + re-ranker 3.4 GB (cloud); + reasoner 21.5 GB and build (local)
[ "$UPDATE" = 1 ] || [ "$FREE" -ge 15 ] || die "$(t 'servono almeno 15 GB liberi (45 con il ragionatore locale)' 'at least 15 GB free needed (45 with the local reasoner)')"

# ---------------------------------------------------------------------------------------------------
step "2. $(t 'Pacchetti di sistema' 'System packages')"
# bubblewrap: the plugins' cage — without it no plugin runs (C226); it was missing here (C237, the Install run, 9 Oct)
PKGS="python3-venv python3-dev build-essential cmake git curl ffmpeg poppler-utils caddy libnss3-tools openssl bubblewrap"
MISSING=$(for p in $PKGS; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done | tr '\n' ' ')
if [ -n "${MISSING// /}" ]; then
  echo "  $(t 'da installare' 'to install'): $MISSING"
  sudo apt-get update -q && sudo apt-get install -y -q $MISSING
fi
ok "$PKGS"
# a systemd unit started by the package would hold ports 80/443: Aurora runs its own Caddy (aurora-https)
if systemctl is-enabled --quiet caddy 2>/dev/null; then sudo systemctl disable --now caddy; ok "$(t 'caddy di sistema disattivato' 'system caddy disabled') (aurora-https)"; fi
BROWSER=$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)
[ -n "$BROWSER" ] && ok "$(t 'browser per i PDF' 'browser for PDFs'): $BROWSER" || warn "$(t 'nessun Chrome/Chromium: i PDF non saranno disponibili' 'no Chrome/Chromium: PDFs will not be available')"

# ---------------------------------------------------------------------------------------------------
step "3. $(t 'GPU o cloud' 'GPU or cloud')"
BACKEND="${AURORA_INSTALL_BACKEND:-}"
[ "$UPDATE" = 1 ] && [ -z "$BACKEND" ] && BACKEND=$(sed -n 's/^AURORA_LLM_BACKEND=//p' .env | tail -1)
# a cloud reasoner needs the exemption (rule 9) — an installation that stopped before step 11 never got it (the owner's
# colleague, 9 Oct: «no local reasoner and no exemption from level B»); signed again here, as a new one would be
[ "$UPDATE" = 1 ] && [ "$BACKEND" = cloud ] && EXEMPT=1
VRAM=0
if nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | sed 's/^/  /'
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | sort -n | tail -1 | tr -dc 0-9)
fi
if [ -z "$BACKEND" ] && [ "${VRAM:-0}" -ge 15000 ]; then
  echo "  $(t 'Dove ragiona Aurora?' 'Where does Aurora reason?')"
  echo "    1) $(t 'sulla tua GPU: niente esce dal computer (consigliato)' 'on your GPU: nothing leaves the computer (advised)')"
  echo "    2) $(t 'con un modello cloud a tua scelta: ogni testo mascherato, la GPU resta libera' 'with a cloud model of your choice: every text masked, the GPU stays free')"
  case "$(ask "$(t 'Scegli 1-2' 'Choose 1-2')" "1" REASONER)" in 2) BACKEND=cloud ;; *) BACKEND=local ;; esac
fi
if [ -z "$BACKEND" ]; then
  if [ "${VRAM:-0}" = 0 ]; then warn "$(t 'nessuna GPU NVIDIA attiva' 'no NVIDIA GPU running')"
  else warn "$(t 'GPU troppo piccola per il ragionatore locale (servono 16 GB)' 'GPU too small for the local reasoner (16 GB needed)')"; fi
  echo "  $(t 'Aurora può funzionare senza GPU: ragiona con un modello cloud a tua scelta; ricerca, memoria e documenti restano su questo computer.' 'Aurora can run without a GPU: she reasons with a cloud model of your choice; search, memory and documents stay on this computer.')"
  if lspci 2>/dev/null | grep -qi 'vga.*nvidia\|3d.*nvidia' && [ "${VRAM:-0}" = 0 ]; then
    echo "  $(t 'C è una scheda NVIDIA senza driver: per usarla installa il driver, riavvia e rilancia ./install.sh:' 'There is an NVIDIA card without a driver: to use it install the driver, reboot and run ./install.sh again:')"
    echo "    sys/core/script/sys_nvidia.sh driver --driver \$(ubuntu-drivers devices 2>/dev/null | awk '/recommended/{print \$3}' | sed 's/nvidia-driver-//')"
  fi
  yesno "$(t 'Installare Aurora con il ragionatore cloud?' 'Install Aurora with the cloud reasoner?')" y CLOUD || die "$(t 'serve una GPU NVIDIA da 16 GB o il cloud' 'an NVIDIA GPU of 16 GB or the cloud is needed')"
  BACKEND=cloud
fi
case "$BACKEND" in local|cloud) ;; *) die "AURORA_INSTALL_BACKEND: local o cloud" ;; esac
if [ "$BACKEND" = cloud ]; then
  ok "$(t 'ragionatore cloud: niente CUDA, niente llama.cpp' 'cloud reasoner: no CUDA, no llama.cpp')"
else
[ "${VRAM:-0}" -gt 0 ] || die "$(t 'il ragionatore locale richiede una GPU NVIDIA con il driver attivo' 'the local reasoner needs an NVIDIA GPU with its driver running')"
[ "$UPDATE" = 1 ] || [ "$FREE" -ge 45 ] || die "$(t 'servono almeno 45 GB liberi (modelli obbligatori 24,7 GB + ambiente e build)' 'at least 45 GB free needed (required models 24.7 GB + environment and build)')"
NVCC_OK=0
if [ -x /usr/local/cuda/bin/nvcc ]; then
  v=$(/usr/local/cuda/bin/nvcc --version | grep -o 'release [0-9.]*' | cut -d' ' -f2)
  [ "$(printf '%s\n12.8\n' "$v" | sort -V | head -1)" = "12.8" ] && NVCC_OK=1 && ok "nvcc $v"
fi
if [ "$NVCC_OK" = 0 ]; then
  echo "  $(t 'serve il CUDA toolkit ≥ 12.8 (solo il toolkit: il driver resta quello di Ubuntu)' 'the CUDA toolkit ≥ 12.8 is needed (toolkit only: the driver stays Ubuntu'"'"'s)')"
  sudo sys/core/script/sys_nvidia.sh toolkit --yes
  [ -x /usr/local/cuda/bin/nvcc ] || die "CUDA toolkit"
fi
fi

# ---------------------------------------------------------------------------------------------------
step "4. $(t 'Le tue scelte' 'Your choices')"
TLS=""; TRUST=""
if [ "$UPDATE" = 1 ]; then
  ok "$(t 'scelte del .env tenute' 'choices of .env kept')"
  # Caddy's local authority trusted again (an installation that stopped early never was: the colleague's «HTTP 000»)
  TRUST=$(sed -n 's/^AURORA_TLS_MODE=//p' .env | tail -1)
else
DEF_NAME="$(getent passwd "$USER" | cut -d: -f5 | cut -d, -f1)"; DEF_NAME="${DEF_NAME:-$USER}"
OWNER=$(ask "$(t 'Il tuo nome (come ti chiamerà Aurora)' 'Your name (what Aurora will call you)')" "$DEF_NAME" NAME)
# who the assistant is (each user changes it later in their settings): her name, her character, her voice
ANAME=$(ask "$(t 'Il nome della tua assistente' 'Your assistant'"'"'s name')" "Aurora" ASSISTANT)
echo "  $(t 'Personalità:' 'Personality:') 1) $(t 'Aurora, scienziata poliedrica' 'Aurora, the many-souled scientist')  2) $(t 'Filosofa' 'Philosopher')  3) $(t 'Empatica' 'Empathic')  4) $(t 'Pratica' 'Practical')"
case "$(ask "$(t 'Scegli 1-4' 'Choose 1-4')" "1" PERSONALITY)" in
  2) PERSONA=philosopher ;; 3) PERSONA=empathic ;; 4) PERSONA=practical ;; *) PERSONA=aurora ;;
esac
case "$(ask "$(t 'Voce femminile o maschile (f/m)' 'Female or male voice (f/m)')" "f" VOICE)" in
  m|M) AGENDER=male ;; *) AGENDER=female ;;
esac
LANGDEF=$([ "$IT" = 1 ] && echo it_IT || echo en_US)
ULANG=$(ask "$(t 'Lingua (it_IT / en_US)' 'Language (it_IT / en_US)')" "$LANGDEF" LANG)
# where Aurora is used from: the phone needs an address it can reach (this computer's on the home network)
LANIP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}')
ALIASES=""; REACH=1
if [ -n "${AURORA_INSTALL_DOMAIN:-}" ]; then
  DOMAIN="$AURORA_INSTALL_DOMAIN"; REACH=3
else
  echo "  $(t 'Da dove userai Aurora?' 'Where will you use Aurora from?')"
  echo "    1) $(t 'solo da questo computer' 'this computer only') (https://localhost)"
  [ -n "$LANIP" ] && echo "    2) $(t 'anche dal telefono e dagli altri dispositivi di casa' 'also from the phone and the other devices at home') (https://$LANIP)"
  echo "    3) $(t 'da un mio nome di dominio' 'from a domain name of mine') ($(t 'con il mio certificato, o con il tunnel Cloudflare dopo' 'with my certificate, or with the Cloudflare tunnel later'))"
  REACH=$(ask "$(t 'Scegli 1-3' 'Choose 1-3')" "1" REACH)
  case "$REACH" in
    2) [ -n "$LANIP" ] || die "$(t 'nessun indirizzo di rete trovato' 'no network address found')"
       DOMAIN="$LANIP"; ALIASES="$(hostname -s 2>/dev/null || hostname).local,localhost" ;;
    3) DOMAIN=$(ask "$(t 'Il tuo nome (es. aurora.example.com)' 'Your name (e.g. aurora.example.com)')" "" DOMAIN_NAME)
       [ -n "$DOMAIN" ] || die "$(t 'nome vuoto' 'empty name')" ;;
    *) REACH=1; DOMAIN=localhost ;;
  esac
  ok "$(t 'Aurora sarà su' 'Aurora will be at') https://$DOMAIN"
fi
TLS=internal; CERT=""; KEY=""
if [ "$REACH" = 3 ] && [ "$DOMAIN" != localhost ] && yesno "$(t 'Hai un tuo certificato per' 'Do you have your own certificate for') $DOMAIN?" n; then
  CERT=$(ask "$(t 'file del certificato (fullchain)' 'certificate file (fullchain)')" "")
  KEY=$(ask "$(t 'file della chiave privata' 'private key file')" "")
  [ -r "$CERT" ] && [ -r "$KEY" ] || die "$(t 'certificato o chiave non leggibili' 'certificate or key not readable')"
  TLS=files
fi
PORT=$(ask "$(t 'Porta HTTPS' 'HTTPS port')" "443" PORT)
# the HTTP port: the phones' certificate and the redirect to HTTPS; another web server on 443 likely has 80 too
HPORT=$(ask "$(t 'Porta HTTP (certificato per i telefoni, rimando all HTTPS)' 'HTTP port (the phones'"'"' certificate, redirect to HTTPS)')" "$([ "$PORT" = 443 ] && echo 80 || echo 8080)" HTTP_PORT)
[ "$HPORT" != "$PORT" ] || die "$(t 'le due porte devono essere diverse' 'the two ports must differ')"
EXEMPT=0
PROVIDER=""; CKEYNAME=""; CMODEL=""
if [ "$BACKEND" = cloud ]; then
  echo
  echo "  $(t 'Ragionatore cloud. Cosa esce da questo computer: le domande, i passaggi dei documenti che servono alla risposta, la conversazione recente.' 'Cloud reasoner. What leaves this computer: the questions, the passages of the documents an answer needs, the recent conversation.')"
  echo "  $(t 'Prima di uscire ogni testo è mascherato: email, telefoni, IBAN, carte, codice fiscale, partita IVA, targhe, indirizzi, IP, chiavi e password, il tuo nome e le parole che indicherai sono sostituiti da segnaposto e rimessi nella risposta.' 'Before leaving every text is masked: e-mails, phones, IBANs, cards, tax codes, VAT numbers, plates, addresses, IPs, keys and passwords, your name and the words you list are replaced by placeholders and put back in the answer.')"
  echo "  $(t 'NON si maschera il contenuto in sé (di cosa parla un documento) né le foto. Il provider lo tratta secondo i suoi termini.' 'NOT masked: the content itself (what a document is about) and photos. The provider handles it under its own terms.')"
  echo "  $(t 'Per questo serve l esenzione dal livello B del codice di condotta (regola 9), che firmi alla fine con sudo.' 'This is why the exemption from level B of the code of conduct (rule 9) is needed: you sign it at the end with sudo.')"
  yesno "$(t 'Va bene così?' 'Is that all right?')" y CLOUD_OK || die "$(t 'senza il cloud serve una GPU NVIDIA da 16 GB' 'without the cloud an NVIDIA GPU of 16 GB is needed')"
  EXEMPT=1
  echo "  $(t 'Provider:' 'Provider:') 1) Anthropic (Claude)  2) OpenAI  3) Google Gemini  4) Mistral  5) OpenRouter  6) xAI Grok  7) Claude Code ($(t 'abbonamento' 'subscription'))"
  echo "            8) $(t 'altro servizio compatibile OpenAI (server aziendale, vLLM, LM Studio, Ollama...)' 'another OpenAI-compatible service (company server, vLLM, LM Studio, Ollama...)')"
  CURL_BASE=""
  case "$(ask "$(t 'Scegli 1-8' 'Choose 1-8')" "1" PROVIDER)" in
    2) PROVIDER=openai; CKEYNAME=AURORA_OPENAI_API_KEY ;;
    3) PROVIDER=google; CKEYNAME=AURORA_GOOGLE_API_KEY ;;
    4) PROVIDER=mistral; CKEYNAME=AURORA_MISTRAL_API_KEY ;;
    5) PROVIDER=openrouter; CKEYNAME=AURORA_OPENROUTER_API_KEY ;;
    6) PROVIDER=xai; CKEYNAME=AURORA_XAI_API_KEY ;;
    7) PROVIDER=claude_code ;;
    8) PROVIDER=custom; CKEYNAME=AURORA_CUSTOM_API_KEY
       CURL_BASE=$(ask "$(t 'Indirizzo del servizio (finisce con /v1)' 'The service'"'"'s address (ending in /v1)')" "" CLOUD_URL)
       case "$CURL_BASE" in http://*|https://*) ;; *) die "$(t 'indirizzo non valido' 'invalid address'): $CURL_BASE" ;; esac ;;
    *) PROVIDER=anthropic; CKEYNAME=AURORA_ANTHROPIC_API_KEY ;;
  esac
  ok "Provider: $PROVIDER"
  CKEY="${AURORA_INSTALL_CLOUD_KEY:-}"
  if [ "$PROVIDER" = claude_code ]; then
    CLAUDE_BIN=$(command -v claude || true)
    [ -n "$CLAUDE_BIN" ] || die "$(t 'Claude Code non trovato: installalo, collega il tuo account (comando claude) e rilancia ./install.sh' 'Claude Code not found: install it, sign in (the claude command) and run ./install.sh again')"
    ok "Claude Code: $CLAUDE_BIN"
  elif [ -z "$CKEY" ] && [ "$PROVIDER" = custom ]; then          # a service of one's own may ask no key
    if [ "$YES" = 0 ]; then
      drain; read -r -s -p "  $(t 'Chiave API del servizio' 'API key of the service') $CURL_BASE ($(t 'non viene mostrata; vuota se non la chiede' 'not shown; empty if it asks none')): " CKEY </dev/tty; echo
    fi
  elif [ -z "$CKEY" ]; then
    [ "$YES" = 1 ] && die "AURORA_INSTALL_CLOUD_KEY"
    drain; read -r -s -p "  $(t 'Chiave API di' 'API key of') $PROVIDER ($(t 'non viene mostrata' 'not shown')): " CKEY </dev/tty; echo
    [ -n "$CKEY" ] || die "$(t 'chiave vuota' 'empty key')"
  fi
else
echo "  $(t 'Livello B del codice di condotta: conferma delle azioni esterne, approvazione delle modifiche al codice, dichiarazione IA.' 'Level B of the code of conduct: confirmation of external actions, approval of code changes, AI disclosure.')"
yesno "$(t 'Esentare questa installazione dal livello B? (sconsigliato all inizio)' 'Exempt this installation from level B? (not advised at first)')" n EXEMPT && EXEMPT=1
fi
# a new Aurora starts with an empty vault: the harvester fills it (owner, 2026-10-09: on unless the owner says no)
echo "  $(t 'Aurora parte con il vault vuoto: la raccolta lo riempie con articoli e voci aperte (arXiv, Wikipedia, Europe PMC…); si cambia nella pagina Harvester.' 'Aurora starts with an empty vault: harvesting fills it with open papers and articles (arXiv, Wikipedia, Europe PMC…); changed on the Harvester page.')"
HARVEST=0
yesno "$(t 'Accendere la raccolta automatica di conoscenza?' 'Switch automatic knowledge harvesting on?')" y HARVEST && HARVEST=1
# the areas: what the harvest collects and the seed's answers (shadows) this installation starts with (owner, 9 Oct)
echo "  $(t 'Argomenti che ti interessano: la raccolta parte da questi e Aurora arriva già con le risposte pronte (ombre) su questi temi, nella tua lingua. Si cambia nella pagina Conoscenza.' 'Topics you care about: harvesting starts from these and Aurora comes with ready answers (shadows) on them, in your language. Changed on the Knowledge page.')"
python3 -I sys/core/script/sys_domains.py --list "$(t it en)"
while :; do
  DOMAINS=$(ask "$(t 'Numeri separati da virgola, oppure tutte' 'Numbers separated by commas, or all')" "$(t tutte all)" DOMAINS)
  python3 -I sys/core/script/sys_domains.py --check "$DOMAINS" && break
  [ "$YES" = 1 ] && die "AURORA_INSTALL_DOMAINS=$DOMAINS"
done
echo "  $(t 'Tipo di installazione:' 'Installation type:')"
echo "    single — $(t 'una persona: tu, amministratore' 'one person: you, the admin')"
echo "    multi  — $(t 'più persone: ognuna con la sua cartella usr/<nome>, le sue impostazioni e la sua memoria privata; accesso con password e codice Authenticator' 'several people: each with their folder usr/<name>, their settings and private memory; login with password and Authenticator code')"
echo "  $(t 'È reversibile dalle Impostazioni → Utenti: da single a multi non si sposta nulla; da multi a single gli altri utenti vengono eliminati, dopo un elenco e una conferma. I tuoi dati non vengono mai toccati.' 'Reversible from Settings → Users: from single to multi nothing moves; from multi to single the other users are deleted, after a list and a confirmation. Your data is never touched.')"
UMODE=$(ask "$(t 'single o multi' 'single or multi')" "single" MODE)
case "$UMODE" in
  single) ;;
  multi) echo "  $(t 'Multi-utente: alla fine entra con la chiave che ti mostro, poi in 👥 Utenti imposta la tua password e collega l app Authenticator, e crea gli utenti.' 'Multi-user: at the end log in with the key shown, then in 👥 Users set your password, link the Authenticator app and create the users.')" ;;
  *) UMODE=single ;;
esac
fi

# ---------------------------------------------------------------------------------------------------
step "5. Python (venv)"
if [ "$RESET_VENV" = 1 ] && [ -d .venv ]; then mv .venv ".venv.old-$(date +%s)"; fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
# every package byte for byte as tested: versions and SHA-256 pinned in requirements.lock
.venv/bin/pip install -q --require-hashes -r requirements.lock || die "pip install --require-hashes -r requirements.lock"
ok "$(.venv/bin/python --version), torch $(.venv/bin/python -c 'import torch; print(torch.__version__, "cuda", torch.cuda.is_available())')"

if [ "$BACKEND" = cloud ] && [ "$UPDATE" = 0 ]; then
  step "5b. $(t 'Modello cloud' 'Cloud model')"
  # the key goes by the environment, never on a command line (visible to every user of this computer)
  export AURORA_INSTALL_CLOUD_URL="$CURL_BASE"            # provider 8 only; not secret
  LIST=$(AURORA_INSTALL_CLOUD_KEY="$CKEY" .venv/bin/python sys/core/script/sys_cloud_setup.py models "$PROVIDER") \
    || die "$(t 'il provider rifiuta la chiave' 'the provider refuses the key'): $(echo "$LIST" | tail -1)"
  echo "$LIST" | head -12 | nl -w4 -s') '
  CDEF=$(echo "$LIST" | head -1)
  CMODEL=$(ask "$(t 'Modello (numero o nome; il primo è consigliato)' 'Model (number or name; the first is advised)')" "$CDEF" MODEL)
  case "$CMODEL" in *[!0-9]*|"") ;; *) CMODEL=$(echo "$LIST" | sed -n "${CMODEL}p") ;; esac
  [ -n "$CMODEL" ] || die "$(t 'modello non valido' 'invalid model')"
  out=$(AURORA_INSTALL_CLOUD_KEY="$CKEY" timeout 300 .venv/bin/python sys/core/script/sys_cloud_setup.py try "$PROVIDER" "$CMODEL") \
    || die "$PROVIDER $CMODEL: $(echo "$out" | tail -1)"
  ok "$PROVIDER $CMODEL $(t 'risponde' 'answers')"
fi

# ---------------------------------------------------------------------------------------------------
step "6. $(t 'Profilo hardware' 'Hardware profile')"
PFLAG=$([ "$BACKEND" = cloud ] && echo --cloud || true)
PROFILE=$(.venv/bin/python sys/core/script/sys_profile.py --json $PFLAG) || { .venv/bin/python sys/core/script/sys_profile.py || true; die "$(t 'hardware non supportato' 'hardware not supported')"; }
.venv/bin/python sys/core/script/sys_profile.py $PFLAG | sed 's/^/  /' || true

# ---------------------------------------------------------------------------------------------------
step "6b. $(t 'Funzioni facoltative (modelli da scaricare)' 'Optional features (models to download)')"
# one question per group; a group this machine cannot run (measured VRAM / RAM) is not offered
PICK=""; MODELS=""; EXTRA=0
PROFILE_FILE=$(mktemp)
echo "$PROFILE" > "$PROFILE_FILE"
while IFS='|' read -r g size fits def why lit len mods todo; do
  label=$(t "$lit" "$len")
  if [ "$OPTIONAL" = 0 ]; then continue; fi
  if [ "$fits" != 1 ]; then warn "$label: $(t 'non adatta a questa macchina' 'not for this machine') ($why)"; continue; fi
  d=$([ "$def" = 1 ] && echo y || echo n); [ "$g" = video ] && [ "$VIDEO" = 1 ] && d=y
  if yesno "$label (+${size} GB)?" "$d"; then
    PICK="$PICK,$g"; MODELS="$MODELS,$mods"; EXTRA=$(.venv/bin/python -c "print(round($EXTRA + $todo, 1))")   # only what is missing
  fi
done < <(.venv/bin/python sys/core/script/sys_doctor.py --groups "$PROFILE_FILE")
PICK="${PICK#,}"; MODELS="${MODELS#,}"
NEED=$(.venv/bin/python -c "print(int($([ "$BACKEND" = cloud ] && echo 15 || echo 45) + $EXTRA + 0.999))")
[ "$UPDATE" = 1 ] || [ "$FREE" -ge "$NEED" ] || die "$(t "servono ${NEED} GB liberi per le scelte fatte, ce ne sono ${FREE}" "${NEED} GB free needed for these choices, ${FREE} available")"
ok "$(t 'scelte' 'chosen'): ${PICK:-$(t 'nessuna' 'none')} ($(t 'da scaricare' 'to download'): ${EXTRA} GB)"

# ---------------------------------------------------------------------------------------------------
step "7. $(t 'Configurazione (.env)' 'Configuration (.env)')"
if [ -f .env ]; then
  ok "$(t '.env esistente: lo tengo (le chiavi nuove prendono il valore consigliato)' 'existing .env kept (new keys take their recommended value)')"
  .venv/bin/python sys/core/script/sys_env_sync.py >/dev/null && mv .env.proposed .env
else
  FRESH_ENV=1
  SETS=(--set "AURORA_OWNER_NAME=$OWNER" --set "AURORA_ASSISTANT_NAME=$ANAME" --set "AURORA_PERSONALITY=$PERSONA"
        --set "AURORA_ASSISTANT_GENDER=$AGENDER" --set "AURORA_LANG_DEFAULT=$ULANG" --set "AURORA_DOMAIN=$DOMAIN"
        --set "AURORA_HTTPS_PORT=$PORT" --set "AURORA_HTTP_PORT=$HPORT" --set "AURORA_TLS_MODE=$TLS" --set "AURORA_UPDATE_MODE=notify"
        --set "AURORA_SERVICE_USER=$USER" --set "AURORA_USER_MODE=$UMODE" --set "AURORA_DOMAIN_ALIASES=$ALIASES" --set "AURORA_HARVEST_ENABLED=$HARVEST")
  [ -n "$BROWSER" ] && SETS+=(--set "AURORA_CHROME_BIN=$BROWSER")
  if [ "$BACKEND" = cloud ]; then
    SETS+=(--set "AURORA_CLOUD_PROVIDER=$PROVIDER" --set "AURORA_CLOUD_MODEL=$CMODEL")
    [ "$PROVIDER" = claude_code ] && SETS+=(--set "AURORA_CLAUDE_CODE_BIN=$CLAUDE_BIN" --set "AURORA_CLAUDE_CODE_MODEL=$CMODEL")
    [ "$PROVIDER" = custom ] && SETS+=(--set "AURORA_CUSTOM_BASE_URL=$CURL_BASE")
    if [ -n "$CKEYNAME" ]; then export "$CKEYNAME=$CKEY"; SETS+=(--set-env "$CKEYNAME"); fi
  fi
  while IFS='=' read -r k v; do [ -n "$k" ] && SETS+=(--set "$k=$v"); done < <(echo "$PROFILE" | .venv/bin/python -c 'import json,sys; [print(f"{k}={v}") for k, v in json.load(sys.stdin)["env"].items()]')
  case ",$PICK," in *,dreams,*) ;; *) SETS+=(--set "AURORA_IMAGE_ENABLED=0") ;; esac   # no dream model, no dream painting
  case ",$PICK," in *,voice,*) ;; *) SETS+=(--set "AURORA_TTS=0") ;; esac              # no Piper, no voice switched on
  .venv/bin/python sys/core/script/sys_env_sync.py "${SETS[@]}" | grep -E '^\s+[=*]' || true
  mv .env.proposed .env
  [ -n "$CKEYNAME" ] && unset "$CKEYNAME"
fi
chmod 600 .env
if [ "$TLS" = files ]; then mkdir -p sys/https/cert && install -m 600 "$CERT" sys/https/cert/fullchain.pem && install -m 600 "$KEY" sys/https/cert/privkey.pem; fi
.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; sys_config.get()' || die ".env"
ok "$(t '.env valido (permessi 600)' '.env valid (mode 600)')"
# the per-user layout (usr/<you>/, your own .env, your memory): a new installation starts on it, nothing to move
if [ ! -f "$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get().path("AURORA_STATUS_DIR"))')/users_layout.json" ]; then
  if .venv/bin/python sys/core/script/sys_users_migrate.py migrate --yes --fresh >/dev/null; then
    ok "$(t 'struttura per utente: usr/'"$USER"'/ e le tue impostazioni personali in usr/'"$USER"'/.env' 'per-user layout: usr/'"$USER"'/ and your personal settings in usr/'"$USER"'/.env')"
  else
    warn "$(t 'ci sono già dati: la struttura per utente si crea con la migrazione, dopo un backup:' 'there is data already: the per-user layout comes with the migration, after a backup:')"
    echo "    .venv/bin/python sys/core/script/sys_users_migrate.py plan"
  fi
fi

# the areas only on a new installation: run again on an Aurora in use, the Knowledge page's choices stay
if [ "${FRESH_ENV:-0}" = 1 ]; then
  .venv/bin/python sys/core/script/sys_domains.py --set "$DOMAINS" | sed 's/^/  ✓ /' || die "sys_domains.py --set $DOMAINS"
fi

# ---------------------------------------------------------------------------------------------------
step "8. $(t 'Modelli (Hugging Face, revisioni fissate, SHA-256 verificati)' 'Models (Hugging Face, pinned revisions, SHA-256 checked)')"
if [ "$BACKEND" = cloud ]; then                # the reasoner is the provider's: encoder and re-ranker only
  .venv/bin/python sys/core/script/sys_models_fetch.py --models embedder,reranker --yes || die "$(t 'download dei modelli' 'model download')"
else
  .venv/bin/python sys/core/script/sys_models_fetch.py --required --yes || die "$(t 'download dei modelli' 'model download')"
fi
if [ "$BACKEND" = cloud ] && [ "$UPDATE" = 0 ]; then          # how many passages this CPU re-ranks in 15 s (C229: 30 fixed took minutes on 2 cores)
  CAL=$(.venv/bin/python sys/core/script/sys_calibrate.py --write --say "$(t it en)" 2>/dev/null | tail -1) \
    && ok "$(t 'audit della macchina' 'machine audit'): $CAL" || warn "$(t 'audit della macchina non riuscito: restano i valori del profilo cloud' 'machine audit failed: the cloud profile values stay')"
fi
if [ -n "$MODELS" ]; then
  .venv/bin/python sys/core/script/sys_models_fetch.py --models "$MODELS" --yes || die "$(t 'download dei modelli facoltativi' 'optional model download')"
  case ",$PICK," in *,voice,*) bash sys/core/script/sys_tts_install.sh || warn "$(t 'voce di Aurora non installata' "Aurora's voice not installed")" ;; esac
fi

# ---------------------------------------------------------------------------------------------------
step "9. $(t 'Programmi' 'Programs')"
if [ "$BACKEND" = local ]; then
  if [ "$BUILD" = 1 ] || [ ! -x sys/runtime/llama.cpp/bin/llama-server ]; then
    sys/core/script/sys_nvidia.sh llama --yes | tail -3 || die "llama.cpp"
  fi
  ok "$(sys/runtime/llama.cpp/bin/llama-server --version 2>&1 | head -1)"
fi
# the GitHub plugin's own program (pinned, SHA-256 checked): nothing installed it before 8 Oct 2026
if out="$(bash sys/core/script/sys_github_mcp_install.sh 2>&1)"; then ok "GitHub MCP: $(echo "$out" | tail -1)"
else warn "$(t 'programma del plugin GitHub non installato' 'the GitHub plugin program not installed'): $(echo "$out" | tail -1)"; fi

# ---------------------------------------------------------------------------------------------------
step "10. Test"
# the failed tests by name, not only the count (the Install run, 9 Oct: «1 failed, 632 passed» and nothing to go on)
(cd sys/core && ../../.venv/bin/python -m pytest -p no:cacheprovider -rfE tests --ignore=tests/test_models_gpu.py 2>&1 \
  | grep -E '^(FAILED|ERROR) |passed|failed' | tail -12) || die "test"

# ---------------------------------------------------------------------------------------------------
step "11. $(t 'Codice di condotta: la chiave di questa installazione' 'Code of conduct: this installation'"'"'s key')"
SIGN="sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup"
[ "$EXEMPT" = 1 ] && SIGN="$SIGN --exempt"           # a false test before && does not stop set -e
SUDO_LATER=0
if sudo -n true 2>/dev/null || (exec </dev/tty) 2>/dev/null; then
  $SIGN
  .venv/bin/python sys/core/script/sys_ethics_sign.py check || die "ethics"
else                                   # no terminal to type the sudo password in (a script, a remote run)
  SUDO_LATER=1
  warn "$(t 'nessun terminale per sudo: la firma e i servizi vanno completati a mano, da questa cartella:' 'no terminal for sudo: signature and services must be completed by hand, from this folder:')"
  echo "    $SIGN"
  [ "$SERVICES" = 1 ] && echo "    .venv/bin/python sys/core/script/sys_install_services.py && sudo bash sys/deploy/systemd/install.sh"
fi

# ---------------------------------------------------------------------------------------------------
if [ "$SERVICES" = 0 ] || [ "$SUDO_LATER" = 1 ]; then
  step "$(t 'Servizi non installati' 'Services not installed') ($([ "$SERVICES" = 0 ] && echo --no-services || echo sudo))"
  echo "  .venv/bin/python sys/core/script/sys_install_services.py && sudo bash sys/deploy/systemd/install.sh"
  .venv/bin/python sys/core/script/sys_doctor.py || true          # what works already, and what is left to do
  echo
  .venv/bin/python sys/core/script/sys_ready.py --pending          # where to open it, and the key: always said
  exit 0
fi
step "12. $(t 'Servizi (systemd) e HTTPS' 'Services (systemd) and HTTPS')"
.venv/bin/python sys/core/script/sys_install_services.py | tail -3
sudo bash sys/deploy/systemd/install.sh || die "$(t 'servizi' 'services')"
if [ "$TLS" = internal ] || [ "$TRUST" = internal ]; then
  ADMIN=$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get()["AURORA_CADDY_ADMIN"])')
  sudo caddy trust --address "$ADMIN" && ok "$(t 'certificato locale di Caddy riconosciuto da questo computer' 'Caddy local certificate trusted on this computer')"
fi
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  HTTPP=$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get()["AURORA_HTTP_PORT"])')
  warn "$(t 'firewall attivo: per usare Aurora da altri dispositivi' 'firewall active: to use Aurora from other devices'): sudo ufw allow $PORT/tcp && sudo ufw allow $HTTPP/tcp"
fi

# ---------------------------------------------------------------------------------------------------
step "13. $(t 'Pronta' 'Ready')"
.venv/bin/python sys/core/script/sys_ready.py
[ "$UMODE" = multi ] && echo "  $(t 'Multi-utente: al primo accesso entra con la chiave API, poi crea la tua password e collega Google Authenticator; da lì entrerai con nome, password e codice.' 'Multi-user: at the first login enter with the API key, then create your password and link Google Authenticator; from then on you enter with name, password and code.')"
echo
.venv/bin/python sys/core/script/sys_doctor.py || warn "$(t 'qualcosa di obbligatorio non va: vedi sopra' 'something required is wrong: see above')"
echo "  $(t 'Funzioni non scelte: si aggiungono quando vuoi con' 'Features not chosen: add them any time with'): .venv/bin/python sys/core/script/sys_models_fetch.py --models <$(t 'nome' 'name')> --yes"
echo "  $(t 'Log dell installazione' 'Installation log'): $ROOT/install.log"
