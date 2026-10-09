#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora for macOS (Apple Silicon or Intel): the installer — install.sh's steps and questions, the Mac's way. Phase 3
# of the port: the reasoner in the cloud (llama.cpp on Metal comes later); search, memory and documents stay here.
#
#   In the Terminal, in the folder of the downloaded Aurora:
#   bash Aurora_mac/install.sh            # questions on screen
#   bash Aurora_mac/install.sh --yes      # every default (the cloud key from AURORA_INSTALL_CLOUD_KEY)
#   ... --root ~/Aurora   --no-optional-models   --no-services
# Every answer can come from AURORA_INSTALL_<NAME>, as on Linux and Windows. Run again to update: the code is copied
# over the old one; .env, the vault, the models and the users' data stay. Written for the bash every Mac has (3.2).
set -eu -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"            # Aurora_mac
REPO="$(dirname "$HERE")"                         # the Linux code it is built from
ROOT="$HOME/Aurora"; YES=0; SERVICES=1; OPTIONAL=1
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --root) shift; ROOT="$1" ;;
    --no-services) SERVICES=0 ;;
    --no-optional-models) OPTIONAL=0 ;;
    -h|--help) sed -n '4,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done
LOG="$REPO/install-mac.log"
exec > >(tee -a "$LOG") 2>&1
IT=0; case "${LANG:-}" in it*) IT=1 ;; esac
t() { if [ "$IT" = 1 ]; then echo "$1"; else echo "$2"; fi; }
step() { echo; printf '\033[1;36m━━ %s ━━\033[0m\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '\n\033[31m✗ %s\033[0m\n' "$*"; echo "$(t 'Dettagli in' 'Details in') $LOG"; exit 1; }
drain() {  # what was typed before a question is not its answer (C217: a terminal sending CR+LF answered the next one)
  /usr/bin/python3 -c 'import sys, termios; f = open("/dev/tty"); termios.tcflush(f, termios.TCIFLUSH)' 2>/dev/null || true
}
ask() {  # ask "question" default [NAME] -> echo answer; AURORA_INSTALL_<NAME> answers without asking
  local q="$1" d="$2" v="AURORA_INSTALL_${3:-}" a=""
  if [ -n "${3:-}" ] && [ -n "$(eval echo "\${$v:-}")" ]; then eval echo "\${$v}"; return; fi
  if [ "$YES" = 1 ]; then echo "$d"; return; fi
  drain
  read -r -p "  $q [$d]: " a </dev/tty
  echo "${a:-$d}"
}
yesno() { local a; a=$(ask "$1 (y/n)" "$2" "${3:-}"); case "$a" in y|Y|s|S|si|sì|yes) return 0 ;; *) return 1 ;; esac; }
printf '\033[1mA.U.R.O.R.A.\033[0m — %s %s  (%s)\n' "$(t 'installazione Mac' 'Mac installation')" "$(date '+%Y-%m-%d %H:%M')" "$ROOT"

# ---------------------------------------------------------------------------------------------------
step "1. $(t 'Controllo del sistema' 'System check')"
[ "$(id -u)" != 0 ] || die "$(t 'Lancialo come utente normale: sudo verrà chiesto quando serve.' 'Run it as a normal user: sudo is asked when needed.')"
[ "$(uname -s)" = Darwin ] || die "$(t 'questo è l installer per il Mac' 'this is the Mac installer')"
OSV=$(sw_vers -productVersion); MAJOR=${OSV%%.*}
[ "$MAJOR" -ge 13 ] || die "macOS 13+ ($OSV)"
ok "macOS $OSV, $(uname -m)"
[ -f "$HERE/build.py" ] || die "$(t 'lancia install.sh dalla cartella Aurora_mac del download' 'run install.sh from the Aurora_mac folder of the download')"
mkdir -p "$ROOT"
# the Mac's disk does not tell ~/aurora from ~/Aurora: the download and the installation must be two folders
[ "$(cd "$ROOT" && pwd -P | tr 'A-Z' 'a-z')" != "$(cd "$REPO" && pwd -P | tr 'A-Z' 'a-z')" ] \
  || die "$(t 'il download è già in' 'the download is already in') $ROOT: $(t 'spostalo (es. ~/Downloads/A.U.R.O.R.A) o usa --root' 'move it (e.g. ~/Downloads/A.U.R.O.R.A) or use --root')"
FREE=$(df -g "$ROOT" | awk 'NR==2 {print $4}')
ok "$(t 'spazio libero' 'free space'): $FREE GB"
[ "$FREE" -ge 15 ] || die "$(t 'servono almeno 15 GB liberi' 'at least 15 GB free needed')"

# ---------------------------------------------------------------------------------------------------
step "2. $(t 'Programmi (Homebrew)' 'Programs (Homebrew)')"
BREW=$(command -v brew || ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1 || true)
[ -n "$BREW" ] || die "$(t 'serve Homebrew: installalo da https://brew.sh (un comando nel Terminale) e rilancia' 'Homebrew is needed: install it from https://brew.sh (one command in the Terminal) and run again')"
eval "$("$BREW" shellenv)"
for f in python@3.14 caddy ffmpeg-full poppler; do
  if "$BREW" list --formula "$f" >/dev/null 2>&1; then ok "$f"
  else "$BREW" install --quiet "$f" >/dev/null || die "brew install $f"; ok "$f ($(t 'installato' 'installed'))"; fi
done
PY314="$("$BREW" --prefix python@3.14)/bin/python3.14"
[ -x "$PY314" ] || die "python3.14: $PY314"
CADDY="$("$BREW" --prefix)/bin/caddy"; PDFTOTEXT="$("$BREW" --prefix)/bin/pdftotext"
BROWSER=""
for b in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
  [ -x "$b" ] && BROWSER="$b" && break
done
if [ -n "$BROWSER" ]; then ok "$(t 'browser per i PDF' 'browser for PDFs'): $BROWSER"
else warn "$(t 'nessun Chrome/Edge: i PDF delle pagine non saranno disponibili' 'no Chrome/Edge: page PDFs will not be available')"; fi

# ---------------------------------------------------------------------------------------------------
step "3. $(t 'GPU o cloud' 'GPU or cloud')"
warn "$(t 'sul Mac il ragionatore locale (llama.cpp su Metal) non c è ancora: Aurora ragiona con un modello cloud; ricerca, memoria e documenti restano su questo computer.' 'on the Mac the local reasoner (llama.cpp on Metal) is not there yet: Aurora reasons with a cloud model; search, memory and documents stay on this computer.')"
yesno "$(t 'Installare Aurora con il ragionatore cloud?' 'Install Aurora with the cloud reasoner?')" y CLOUD || die "$(t 'sul Mac, per ora, serve il cloud' 'on the Mac, for now, the cloud is needed')"

# ---------------------------------------------------------------------------------------------------
step "4. $(t 'Le tue scelte' 'Your choices')"
FRESH=1; [ -f "$ROOT/.env" ] && FRESH=0
if [ "$FRESH" = 0 ]; then
  ok "$(t '.env esistente: aggiorno il codice, le scelte restano quelle di prima' 'existing .env: the code is updated, the choices stay as they were')"
else
  DEF_NAME="$(id -F 2>/dev/null || echo "$USER")"
  OWNER=$(ask "$(t 'Il tuo nome (come ti chiamerà Aurora)' 'Your name (what Aurora will call you)')" "$DEF_NAME" NAME)
  ANAME=$(ask "$(t 'Il nome della tua assistente' 'Your assistant'"'"'s name')" "Aurora" ASSISTANT)
  echo "  $(t 'Personalità:' 'Personality:') 1) $(t 'Aurora, scienziata poliedrica' 'Aurora, the many-souled scientist')  2) $(t 'Filosofa' 'Philosopher')  3) $(t 'Empatica' 'Empathic')  4) $(t 'Pratica' 'Practical')"
  case "$(ask "$(t 'Scegli 1-4' 'Choose 1-4')" "1" PERSONALITY)" in
    2) PERSONA=philosopher ;; 3) PERSONA=empathic ;; 4) PERSONA=practical ;; *) PERSONA=aurora ;;
  esac
  case "$(ask "$(t 'Voce femminile o maschile (f/m)' 'Female or male voice (f/m)')" "f" VOICE)" in m|M) AGENDER=male ;; *) AGENDER=female ;; esac
  ULANG=$(ask "$(t 'Lingua (it_IT / en_US)' 'Language (it_IT / en_US)')" "$([ "$IT" = 1 ] && echo it_IT || echo en_US)" LANG)
  LANIP=$(ipconfig getifaddr "$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}')" 2>/dev/null || true)
  echo "  $(t 'Da dove userai Aurora?' 'Where will you use Aurora from?')"
  echo "    1) $(t 'solo da questo computer' 'this computer only') (https://localhost)"
  [ -n "$LANIP" ] && echo "    2) $(t 'anche dal telefono e dagli altri dispositivi di casa' 'also from the phone and the other devices at home') (https://$LANIP)"
  echo "    3) $(t 'da un mio nome di dominio' 'from a domain name of mine')"
  REACH=$(ask "$(t 'Scegli 1-3' 'Choose 1-3')" "1" REACH); ALIASES=""
  case "$REACH" in
    2) [ -n "$LANIP" ] || die "$(t 'nessun indirizzo di rete trovato' 'no network address found')"
       DOMAIN="$LANIP"; ALIASES="$(scutil --get LocalHostName 2>/dev/null | tr 'A-Z' 'a-z').local,localhost" ;;
    3) DOMAIN=$(ask "$(t 'Il tuo nome (es. aurora.example.com)' 'Your name (e.g. aurora.example.com)')" "" DOMAIN_NAME)
       [ -n "$DOMAIN" ] || die "$(t 'nome vuoto' 'empty name')" ;;
    *) REACH=1; DOMAIN=localhost ;;
  esac
  ok "$(t 'Aurora sarà su' 'Aurora will be at') https://$DOMAIN"
  TLS=internal; CERT=""; KEY=""
  if [ "$REACH" = 3 ] && yesno "$(t 'Hai un tuo certificato per' 'Do you have your own certificate for') $DOMAIN?" n; then
    CERT=$(ask "$(t 'file del certificato (fullchain)' 'certificate file (fullchain)')" "")
    KEY=$(ask "$(t 'file della chiave privata' 'private key file')" "")
    [ -r "$CERT" ] && [ -r "$KEY" ] || die "$(t 'certificato o chiave non leggibili' 'certificate or key not readable')"
    TLS=files
  fi
  PORT=$(ask "$(t 'Porta HTTPS' 'HTTPS port')" "443" PORT)
  HPORT=$(ask "$(t 'Porta HTTP (certificato per i telefoni, rimando all HTTPS)' 'HTTP port (the phones'"'"' certificate, redirect to HTTPS)')" "$([ "$PORT" = 443 ] && echo 80 || echo 8080)" HTTP_PORT)
  [ "$HPORT" != "$PORT" ] || die "$(t 'le due porte devono essere diverse' 'the two ports must differ')"
  echo
  echo "  $(t 'Ragionatore cloud. Cosa esce da questo computer: le domande, i passaggi dei documenti che servono alla risposta, la conversazione recente.' 'Cloud reasoner. What leaves this computer: the questions, the passages of the documents an answer needs, the recent conversation.')"
  echo "  $(t 'Prima di uscire ogni testo è mascherato: email, telefoni, IBAN, carte, codice fiscale, partita IVA, targhe, indirizzi, IP, chiavi e password, il tuo nome e le parole che indicherai sono sostituiti da segnaposto e rimessi nella risposta.' 'Before leaving every text is masked: e-mails, phones, IBANs, cards, tax codes, VAT numbers, plates, addresses, IPs, keys and passwords, your name and the words you list are replaced by placeholders and put back in the answer.')"
  echo "  $(t 'NON si maschera il contenuto in sé (di cosa parla un documento) né le foto. Il provider lo tratta secondo i suoi termini.' 'NOT masked: the content itself (what a document is about) and photos. The provider handles it under its own terms.')"
  echo "  $(t 'Per questo serve l esenzione dal livello B del codice di condotta (regola 9), che firmi alla fine con sudo.' 'This is why the exemption from level B of the code of conduct (rule 9) is needed: you sign it at the end with sudo.')"
  yesno "$(t 'Va bene così?' 'Is that all right?')" y CLOUD_OK || die "$(t 'sul Mac, per ora, serve il cloud' 'on the Mac, for now, the cloud is needed')"
  echo "  Provider: 1) Anthropic (Claude)  2) OpenAI  3) Google Gemini  4) Mistral  5) OpenRouter  6) xAI Grok  7) Claude Code ($(t 'abbonamento' 'subscription'))"
  echo "            8) $(t 'altro servizio compatibile OpenAI (server aziendale, vLLM, LM Studio, Ollama...)' 'another OpenAI-compatible service (company server, vLLM, LM Studio, Ollama...)')"
  CURL_BASE=""; CKEYNAME=""
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
  CKEY="${AURORA_INSTALL_CLOUD_KEY:-}"; CLAUDE_BIN=""
  if [ "$PROVIDER" = claude_code ]; then
    CLAUDE_BIN=$(command -v claude || true)
    [ -n "$CLAUDE_BIN" ] || die "$(t 'Claude Code non trovato: installalo, collega il tuo account (comando claude) e rilancia' 'Claude Code not found: install it, sign in (the claude command) and run again')"
    ok "Claude Code: $CLAUDE_BIN"
  elif [ -z "$CKEY" ] && [ "$PROVIDER" = custom ]; then
    if [ "$YES" = 0 ]; then drain; read -r -s -p "  $(t 'Chiave API del servizio' 'API key of the service') $CURL_BASE ($(t 'non viene mostrata; vuota se non la chiede' 'not shown; empty if it asks none')): " CKEY </dev/tty; echo; fi
  elif [ -z "$CKEY" ]; then
    [ "$YES" = 1 ] && die "AURORA_INSTALL_CLOUD_KEY"
    drain; read -r -s -p "  $(t 'Chiave API di' 'API key of') $PROVIDER ($(t 'non viene mostrata' 'not shown')): " CKEY </dev/tty; echo
    [ -n "$CKEY" ] || die "$(t 'chiave vuota' 'empty key')"
  fi
  echo "  $(t 'Aurora parte con il vault vuoto: la raccolta lo riempie con articoli e voci aperte (arXiv, Wikipedia, Europe PMC…); si cambia nella pagina Harvester.' 'Aurora starts with an empty vault: harvesting fills it with open papers and articles (arXiv, Wikipedia, Europe PMC…); changed on the Harvester page.')"
  HARVEST=0; yesno "$(t 'Accendere la raccolta automatica di conoscenza?' 'Switch automatic knowledge harvesting on?')" y HARVEST && HARVEST=1
  # the areas: what the harvest collects and the seed's answers (shadows) this installation starts with (owner, 9 Oct)
  echo "  $(t 'Argomenti che ti interessano: la raccolta parte da questi e Aurora arriva già con le risposte pronte (ombre) su questi temi, nella tua lingua. Si cambia nella pagina Conoscenza.' 'Topics you care about: harvesting starts from these and Aurora comes with ready answers (shadows) on them, in your language. Changed on the Knowledge page.')"
  "$PY314" -I "$REPO/sys/core/script/sys_domains.py" --list "$(t it en)"
  while :; do
    DOMAINS=$(ask "$(t 'Numeri separati da virgola, oppure tutte' 'Numbers separated by commas, or all')" "$(t tutte all)" DOMAINS)
    "$PY314" -I "$REPO/sys/core/script/sys_domains.py" --check "$DOMAINS" && break
    [ "$YES" = 1 ] && die "AURORA_INSTALL_DOMAINS=$DOMAINS"
  done
  echo "  $(t 'Tipo di installazione: single (una persona: tu) o multi (più persone, ognuna con la sua cartella e la sua memoria privata)' 'Installation type: single (one person: you) or multi (several people, each with their folder and private memory)')"
  UMODE=$(ask "$(t 'single o multi' 'single or multi')" "single" MODE); [ "$UMODE" = multi ] || UMODE=single
fi

# ---------------------------------------------------------------------------------------------------
step "5. $(t 'Codice e Python (venv)' 'Code and Python (venv)')"
# built from the Linux code next to this folder, then copied over Aurora's folder: only code moves (rsync without
# --delete): .env and the data are never touched
STAGE="${TMPDIR:-/tmp}/aurora-build-mac"
"$PY314" "$HERE/build.py" --out "$STAGE" | tail -1 | sed 's/^/  /' || die "build.py"
rsync -a "$STAGE/" "$ROOT/" || die "rsync"
ok "$(t 'codice in' 'code in') $ROOT"
cd "$ROOT"
[ -x .venv/bin/python ] || "$PY314" -m venv .venv || die "venv"
.venv/bin/pip install -q --upgrade pip >/dev/null
# the Linux lock pins Linux wheels: the Mac takes requirements.txt's versions from PyPI (torch with Metal: mps)
.venv/bin/pip install -q -r requirements.txt || die "pip install -r requirements.txt"
ok "$(.venv/bin/python --version), torch $(.venv/bin/python -c 'import torch; print(torch.__version__, "mps", torch.backends.mps.is_available())')"
if [ "$FRESH" = 1 ]; then
  step "5b. $(t 'Modello cloud' 'Cloud model')"
  export AURORA_INSTALL_CLOUD_URL="$CURL_BASE"
  LIST=$(AURORA_INSTALL_CLOUD_KEY="$CKEY" .venv/bin/python sys/core/script/sys_cloud_setup.py models "$PROVIDER") \
    || die "$(t 'il provider rifiuta la chiave' 'the provider refuses the key'): $(echo "$LIST" | tail -1)"
  echo "$LIST" | head -12 | nl -w4 -s') '
  CDEF=$(echo "$LIST" | head -1)
  CMODEL=$(ask "$(t 'Modello (numero o nome; il primo è consigliato)' 'Model (number or name; the first is advised)')" "$CDEF" MODEL)
  case "$CMODEL" in *[!0-9]*|"") ;; *) CMODEL=$(echo "$LIST" | sed -n "${CMODEL}p") ;; esac
  [ -n "$CMODEL" ] || die "$(t 'modello non valido' 'invalid model')"
  out=$(AURORA_INSTALL_CLOUD_KEY="$CKEY" .venv/bin/python sys/core/script/sys_cloud_setup.py try "$PROVIDER" "$CMODEL") \
    || die "$PROVIDER $CMODEL: $(echo "$out" | tail -1)"
  ok "$PROVIDER $CMODEL $(t 'risponde' 'answers')"
fi

# ---------------------------------------------------------------------------------------------------
step "6. $(t 'Profilo hardware e funzioni facoltative' 'Hardware profile and optional features')"
PROFILE=$(.venv/bin/python sys/core/script/sys_profile.py --json --cloud) || die "$(t 'hardware non supportato' 'hardware not supported')"
PROFILE_FILE="${TMPDIR:-/tmp}/aurora-profile.json"; echo "$PROFILE" > "$PROFILE_FILE"
PICK=""; MODELS=""
if [ "$FRESH" = 1 ] && [ "$OPTIONAL" = 1 ]; then
  while IFS='|' read -r g size fits def why lit len mods todo; do
    label=$(t "$lit" "$len")
    if [ "$g" = voice ]; then warn "$label: $(t 'sul Mac non ancora (Piper)' 'not on the Mac yet (Piper)')"; continue; fi
    if [ "$fits" != 1 ]; then warn "$label: $(t 'non adatta a questa macchina' 'not for this machine') ($why)"; continue; fi
    d=$([ "$def" = 1 ] && echo y || echo n)
    if yesno "$label (+${size} GB)?" "$d"; then PICK="$PICK,$g"; MODELS="$MODELS,$mods"; fi
  done < <(.venv/bin/python sys/core/script/sys_doctor.py --groups "$PROFILE_FILE")
fi
PICK="${PICK#,}"; MODELS="${MODELS#,}"
ok "$(t 'scelte' 'chosen'): ${PICK:-$(t 'nessuna' 'none')}"

# ---------------------------------------------------------------------------------------------------
step "7. $(t 'Configurazione (.env)' 'Configuration (.env)')"
if [ "$FRESH" = 0 ]; then
  .venv/bin/python sys/core/script/sys_env_sync.py >/dev/null && mv .env.proposed .env
else
  SETS=(--set "AURORA_ROOT=$ROOT" --set "AURORA_OWNER_NAME=$OWNER" --set "AURORA_ASSISTANT_NAME=$ANAME"
        --set "AURORA_PERSONALITY=$PERSONA" --set "AURORA_ASSISTANT_GENDER=$AGENDER" --set "AURORA_LANG_DEFAULT=$ULANG"
        --set "AURORA_DOMAIN=$DOMAIN" --set "AURORA_HTTPS_PORT=$PORT" --set "AURORA_HTTP_PORT=$HPORT"
        --set "AURORA_TLS_MODE=$TLS" --set "AURORA_UPDATE_MODE=notify" --set "AURORA_SERVICE_USER=$USER"
        --set "AURORA_USER_MODE=$UMODE" --set "AURORA_DOMAIN_ALIASES=$ALIASES" --set "AURORA_HARVEST_ENABLED=$HARVEST"
        --set "AURORA_LLM_BACKEND=cloud" --set "AURORA_CLOUD_PROVIDER=$PROVIDER" --set "AURORA_CLOUD_MODEL=$CMODEL"
        --set "AURORA_CADDY_BIN=$CADDY" --set "AURORA_PDFTOTEXT_BIN=$PDFTOTEXT" --set "AURORA_TTS=0")
  [ -n "$BROWSER" ] && SETS+=(--set "AURORA_CHROME_BIN=$BROWSER")
  [ "$PROVIDER" = claude_code ] && SETS+=(--set "AURORA_CLAUDE_CODE_BIN=$CLAUDE_BIN" --set "AURORA_CLAUDE_CODE_MODEL=$CMODEL")
  [ "$PROVIDER" = custom ] && SETS+=(--set "AURORA_CUSTOM_BASE_URL=$CURL_BASE")
  if [ -n "$CKEYNAME" ]; then export "$CKEYNAME=$CKEY"; SETS+=(--set-env "$CKEYNAME"); fi
  while IFS='=' read -r k v; do
    [ -n "$k" ] && [ "$k" != AURORA_LLM_BACKEND ] && SETS+=(--set "$k=$v")
  done < <(echo "$PROFILE" | .venv/bin/python -c 'import json,sys; [print(f"{k}={v}") for k, v in json.load(sys.stdin)["env"].items()]')
  case ",$PICK," in *,dreams,*) ;; *) SETS+=(--set "AURORA_IMAGE_ENABLED=0") ;; esac
  .venv/bin/python sys/core/script/sys_env_sync.py "${SETS[@]}" >/dev/null
  mv .env.proposed .env
  [ -n "$CKEYNAME" ] && unset "$CKEYNAME"
fi
chmod 600 .env
if [ "${TLS:-internal}" = files ]; then mkdir -p sys/https/cert && install -m 600 "$CERT" sys/https/cert/fullchain.pem && install -m 600 "$KEY" sys/https/cert/privkey.pem; fi
.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; sys_config.get()' || die ".env"
chmod 700 "$ROOT"
ok "$(t '.env valido; la cartella è leggibile solo da te' '.env valid; the folder is readable by you only')"
STATUS=$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get().path("AURORA_STATUS_DIR"))')
if [ ! -f "$STATUS/users_layout.json" ]; then
  .venv/bin/python sys/core/script/sys_users_migrate.py migrate --yes --fresh >/dev/null && ok "$(t 'struttura per utente' 'per-user layout'): usr/$USER/" \
    || warn "$(t 'struttura per utente non creata' 'per-user layout not made'): sys_users_migrate.py plan"
fi
[ -n "${DOMAINS:-}" ] && { .venv/bin/python sys/core/script/sys_domains.py --set "$DOMAINS" | sed 's/^/  ✓ /' || die "sys_domains.py --set $DOMAINS"; }

# ---------------------------------------------------------------------------------------------------
step "8. $(t 'Modelli (Hugging Face, revisioni fissate, SHA-256 verificati)' 'Models (Hugging Face, pinned revisions, SHA-256 checked)')"
.venv/bin/python sys/core/script/sys_models_fetch.py --models embedder,reranker --yes | tail -1 | sed 's/^/  /' || die "$(t 'download dei modelli' 'model download')"
[ -n "$MODELS" ] && { .venv/bin/python sys/core/script/sys_models_fetch.py --models "$MODELS" --yes | tail -1 | sed 's/^/  /' || die "$(t 'download dei modelli facoltativi' 'optional model download')"; }
# how many passages this CPU re-ranks in 15 s (C229: the fixed 30 took minutes on 2 cores)
CAL=$(.venv/bin/python sys/core/script/sys_calibrate.py --write 2>/dev/null | tail -1) \
  && ok "$(t 'ricerca tarata su questa CPU' 'search tuned to this CPU'): $CAL" || warn "$(t 'taratura della ricerca non riuscita: restano 30 candidati' 'search not tuned: 30 candidates kept')"

# ---------------------------------------------------------------------------------------------------
step "9. $(t 'Codice di condotta: la chiave di questa installazione' 'Code of conduct: this installation'"'"'s key')"
echo "  $(t 'La chiave sta in /Library/Application Support/Aurora/keys, di root: sudo ti chiede la password.' 'The key lives in /Library/Application Support/Aurora/keys, root'"'"'s: sudo asks your password.')"
sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup --exempt | sed 's/^/  /' || die "ethics"
.venv/bin/python sys/core/script/sys_ethics_sign.py check | sed 's/^/  /' || die "ethics"

# ---------------------------------------------------------------------------------------------------
if [ "$SERVICES" = 0 ]; then
  step "$(t 'Servizi non installati' 'Services not installed') (--no-services)"
  echo "  .venv/bin/python sys/core/script/sys_install_agents.py"
  .venv/bin/python sys/core/script/sys_ready.py --pending
  exit 0
fi
step "10. $(t 'Servizi (launchd) e HTTPS' 'Services (launchd) and HTTPS')"
.venv/bin/python sys/core/script/sys_install_agents.py | sed 's/^/  /' || die "$(t 'servizi' 'services')"
if [ "${TLS:-internal}" = internal ] || [ "$FRESH" = 0 ]; then
  ADMIN=$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get()["AURORA_CADDY_ADMIN"])')
  # the System keychain: the root certificate trusted by Safari and Chrome on this Mac
  sudo "$CADDY" trust --address "$ADMIN" >/dev/null 2>&1 && ok "$(t 'certificato locale di Caddy riconosciuto da questo Mac' 'Caddy local certificate trusted on this Mac')" \
    || warn "$(t 'certificato di Caddy non registrato: il browser chiederà un eccezione' 'Caddy'"'"'s certificate not registered: the browser will ask for an exception')"
fi
echo "  $(t 'I servizi girano mentre sei collegato al Mac (agenti launchd): per un Mac sempre acceso usa l accesso automatico (Impostazioni → Utenti).' 'The services run while you are logged in (launchd agents): for a Mac always on use automatic login (Settings → Users).')"

# ---------------------------------------------------------------------------------------------------
step "11. $(t 'Pronta' 'Ready')"
.venv/bin/python sys/core/script/sys_ready.py
.venv/bin/python sys/core/script/sys_doctor.py || warn "$(t 'qualcosa di obbligatorio non va: vedi sopra' 'something required is wrong: see above')"
echo "  $(t 'Log dell installazione' 'Installation log'): $LOG"
