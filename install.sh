#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# A.U.R.O.R.A. installer: from a fresh `git clone` to a running Aurora sized for this machine.
#
#   ./install.sh                     # asks a few questions (defaults in brackets)
#   ./install.sh --yes               # takes every default
#   options: --no-services (stop before systemd/HTTPS: for a second copy on a machine that already runs Aurora)
#            --no-optional-models (only the required models; add others later with sys_models_fetch.py)
#            --with-video (also the video model under --yes, 34 GB)   --reset-venv   --skip-build
#
# Steps: system check → packages → NVIDIA (driver present, CUDA toolkit 13) → your answers → venv → hardware
# profile → .env → models from Hugging Face → llama.cpp for your GPUs → tests → code of conduct key → systemd
# units + HTTPS → health check. Every step can be run again: what is done is not done twice.
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
ask() {  # ask "question" default -> echo answer
  local q="$1" d="$2" a
  if [ "$YES" = 1 ]; then echo "$d"; return; fi
  read -r -p "  $q [$d]: " a </dev/tty
  echo "${a:-$d}"
}
yesno() {  # yesno "question" y|n -> exit status
  local a; a=$(ask "$1 (y/n)" "$2")
  case "$a" in y|Y|s|S|si|sì|yes) return 0 ;; *) return 1 ;; esac
}
echo -e "\e[1mA.U.R.O.R.A.\e[0m — $(t 'installazione' 'installation') $(date '+%Y-%m-%d %H:%M')  ($ROOT)"

# ---------------------------------------------------------------------------------------------------
step "1. $(t 'Controllo del sistema' 'System check')"
[ "$(id -u)" != 0 ] || die "$(t 'Lancialo come utente normale: sudo verrà chiesto quando serve.' 'Run it as a normal user: sudo is asked when needed.')"
. /etc/os-release
ok "$PRETTY_NAME, kernel $(uname -r)"
case "$ID:$VERSION_ID" in ubuntu:26.04*) ;; ubuntu:24.04*) warn "$(t 'Ubuntu 24.04: non misurato (consigliato 26.04)' 'Ubuntu 24.04: not measured (26.04 recommended)')" ;;
  *) warn "$(t 'sistema non provato: gli script usano apt e i driver di Ubuntu' 'untested system: the scripts use apt and Ubuntu drivers')" ;; esac
command -v sudo >/dev/null || die "sudo"
FREE=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc 0-9)
ok "$(t 'spazio libero' 'free space'): ${FREE} GB"
[ "$FREE" -ge 45 ] || die "$(t 'servono almeno 45 GB liberi (modelli obbligatori 24,7 GB + ambiente e build)' 'at least 45 GB free needed (required models 24.7 GB + environment and build)')"

# ---------------------------------------------------------------------------------------------------
step "2. $(t 'Pacchetti di sistema' 'System packages')"
PKGS="python3-venv python3-dev build-essential cmake git curl ffmpeg poppler-utils caddy libnss3-tools openssl"
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
step "3. NVIDIA"
if ! nvidia-smi >/dev/null 2>&1; then
  warn "$(t 'nessun driver NVIDIA attivo.' 'no NVIDIA driver running.')"
  echo "  $(t 'Installa il driver consigliato da Ubuntu, riavvia e rilancia ./install.sh:' 'Install Ubuntu'"'"'s recommended driver, reboot and run ./install.sh again:')"
  echo "    sys/core/script/sys_nvidia.sh driver --driver \$(ubuntu-drivers devices 2>/dev/null | awk '/recommended/{print \$3}' | sed 's/nvidia-driver-//')"
  die "$(t 'driver mancante' 'driver missing')"
fi
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader | sed 's/^/  /'
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

# ---------------------------------------------------------------------------------------------------
step "4. $(t 'Le tue scelte' 'Your choices')"
DEF_NAME="$(getent passwd "$USER" | cut -d: -f5 | cut -d, -f1)"; DEF_NAME="${DEF_NAME:-$USER}"
OWNER=$(ask "$(t 'Il tuo nome (come ti chiamerà Aurora)' 'Your name (what Aurora will call you)')" "$DEF_NAME")
LANGDEF=$([ "$IT" = 1 ] && echo it_IT || echo en_US)
ULANG=$(ask "$(t 'Lingua (it_IT / en_US)' 'Language (it_IT / en_US)')" "$LANGDEF")
DOMAIN=$(ask "$(t 'Nome per la WebUI (localhost = solo questo computer)' 'Name for the WebUI (localhost = this computer only)')" "localhost")
TLS=internal; CERT=""; KEY=""
if [ "$DOMAIN" != localhost ] && yesno "$(t 'Hai un tuo certificato per' 'Do you have your own certificate for') $DOMAIN?" n; then
  CERT=$(ask "$(t 'file del certificato (fullchain)' 'certificate file (fullchain)')" "")
  KEY=$(ask "$(t 'file della chiave privata' 'private key file')" "")
  [ -r "$CERT" ] && [ -r "$KEY" ] || die "$(t 'certificato o chiave non leggibili' 'certificate or key not readable')"
  TLS=files
fi
PORT=$(ask "$(t 'Porta HTTPS' 'HTTPS port')" "443")
EXEMPT=0
echo "  $(t 'Livello B del codice di condotta: conferma delle azioni esterne, approvazione delle modifiche al codice, dichiarazione IA.' 'Level B of the code of conduct: confirmation of external actions, approval of code changes, AI disclosure.')"
yesno "$(t 'Esentare questa installazione dal livello B? (sconsigliato all inizio)' 'Exempt this installation from level B? (not advised at first)')" n && EXEMPT=1
echo "  $(t 'Tipo di installazione:' 'Installation type:')"
echo "    single — $(t 'una persona: tu, amministratore' 'one person: you, the admin')"
echo "    multi  — $(t 'più persone: ognuna con la sua cartella usr/<nome>, le sue impostazioni e la sua memoria privata; accesso con password e codice Authenticator' 'several people: each with their folder usr/<name>, their settings and private memory; login with password and Authenticator code')"
echo "  $(t 'È reversibile dalle Impostazioni → Utenti: da single a multi non si sposta nulla; da multi a single gli altri utenti vengono eliminati, dopo un elenco e una conferma. I tuoi dati non vengono mai toccati.' 'Reversible from Settings → Users: from single to multi nothing moves; from multi to single the other users are deleted, after a list and a confirmation. Your data is never touched.')"
UMODE=$(ask "$(t 'single o multi' 'single or multi')" "single")
case "$UMODE" in
  single) ;;
  multi) echo "  $(t 'Multi-utente: alla fine entra con la chiave che ti mostro, poi in 👥 Utenti imposta la tua password e collega l app Authenticator, e crea gli utenti.' 'Multi-user: at the end log in with the key shown, then in 👥 Users set your password, link the Authenticator app and create the users.')" ;;
  *) UMODE=single ;;
esac

# ---------------------------------------------------------------------------------------------------
step "5. Python (venv)"
if [ "$RESET_VENV" = 1 ] && [ -d .venv ]; then mv .venv ".venv.old-$(date +%s)"; fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
# every package byte for byte as tested: versions and SHA-256 pinned in requirements.lock
.venv/bin/pip install -q --require-hashes -r requirements.lock || die "pip install --require-hashes -r requirements.lock"
ok "$(.venv/bin/python --version), torch $(.venv/bin/python -c 'import torch; print(torch.__version__, "cuda", torch.cuda.is_available())')"

# ---------------------------------------------------------------------------------------------------
step "6. $(t 'Profilo hardware' 'Hardware profile')"
PROFILE=$(.venv/bin/python sys/core/script/sys_profile.py --json) || { .venv/bin/python sys/core/script/sys_profile.py || true; die "$(t 'hardware non supportato' 'hardware not supported')"; }
.venv/bin/python sys/core/script/sys_profile.py | sed 's/^/  /' || true

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
NEED=$(.venv/bin/python -c "print(int(45 + $EXTRA + 0.999))")
[ "$FREE" -ge "$NEED" ] || die "$(t "servono ${NEED} GB liberi per le scelte fatte, ce ne sono ${FREE}" "${NEED} GB free needed for these choices, ${FREE} available")"
ok "$(t 'scelte' 'chosen'): ${PICK:-$(t 'nessuna' 'none')} ($(t 'da scaricare' 'to download'): ${EXTRA} GB)"

# ---------------------------------------------------------------------------------------------------
step "7. $(t 'Configurazione (.env)' 'Configuration (.env)')"
if [ -f .env ]; then
  ok "$(t '.env esistente: lo tengo (le chiavi nuove prendono il valore consigliato)' 'existing .env kept (new keys take their recommended value)')"
  .venv/bin/python sys/core/script/sys_env_sync.py >/dev/null && mv .env.proposed .env
else
  SETS=(--set "AURORA_OWNER_NAME=$OWNER" --set "AURORA_LANG_DEFAULT=$ULANG" --set "AURORA_DOMAIN=$DOMAIN"
        --set "AURORA_HTTPS_PORT=$PORT" --set "AURORA_TLS_MODE=$TLS" --set "AURORA_UPDATE_MODE=notify"
        --set "AURORA_SERVICE_USER=$USER" --set "AURORA_USER_MODE=$UMODE")
  [ -n "$BROWSER" ] && SETS+=(--set "AURORA_CHROME_BIN=$BROWSER")
  while IFS='=' read -r k v; do [ -n "$k" ] && SETS+=(--set "$k=$v"); done < <(echo "$PROFILE" | .venv/bin/python -c 'import json,sys; [print(f"{k}={v}") for k, v in json.load(sys.stdin)["env"].items()]')
  case ",$PICK," in *,dreams,*) ;; *) SETS+=(--set "AURORA_IMAGE_ENABLED=0") ;; esac   # no dream model, no dream painting
  .venv/bin/python sys/core/script/sys_env_sync.py "${SETS[@]}" | grep -E '^\s+[=*]' || true
  mv .env.proposed .env
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

# ---------------------------------------------------------------------------------------------------
step "8. $(t 'Modelli (Hugging Face, revisioni fissate, SHA-256 verificati)' 'Models (Hugging Face, pinned revisions, SHA-256 checked)')"
.venv/bin/python sys/core/script/sys_models_fetch.py --required --yes || die "$(t 'download dei modelli' 'model download')"
if [ -n "$MODELS" ]; then
  .venv/bin/python sys/core/script/sys_models_fetch.py --models "$MODELS" --yes || die "$(t 'download dei modelli facoltativi' 'optional model download')"
fi

# ---------------------------------------------------------------------------------------------------
step "9. llama.cpp $(t 'per le tue GPU' 'for your GPUs')"
if [ "$BUILD" = 1 ] || [ ! -x sys/runtime/llama.cpp/bin/llama-server ]; then
  sys/core/script/sys_nvidia.sh llama --yes | tail -3 || die "llama.cpp"
fi
ok "$(sys/runtime/llama.cpp/bin/llama-server --version 2>&1 | head -1)"

# ---------------------------------------------------------------------------------------------------
step "10. Test"
(cd sys/core && ../../.venv/bin/python -m pytest -p no:cacheprovider tests --ignore=tests/test_models_gpu.py 2>&1 | tail -1) || die "test"

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
  exit 0
fi
step "12. $(t 'Servizi (systemd) e HTTPS' 'Services (systemd) and HTTPS')"
.venv/bin/python sys/core/script/sys_install_services.py | tail -3
sudo bash sys/deploy/systemd/install.sh || die "$(t 'servizi' 'services')"
if [ "$TLS" = internal ]; then
  ADMIN=$(.venv/bin/python -c 'import sys; sys.path.insert(0, "sys/core"); from aurora import sys_config; print(sys_config.get()["AURORA_CADDY_ADMIN"])')
  sudo caddy trust --address "$ADMIN" && ok "$(t 'certificato locale di Caddy riconosciuto da questo computer' 'Caddy local certificate trusted on this computer')"
  echo "  $(t 'Per altri dispositivi importa' 'For other devices import'): ~/.local/share/caddy/pki/authorities/local/root.crt"
fi
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  warn "$(t 'firewall attivo: per usare Aurora da altri dispositivi' 'firewall active: to use Aurora from other devices'): sudo ufw allow $PORT/tcp"
fi

# ---------------------------------------------------------------------------------------------------
step "13. $(t 'Pronta' 'Ready')"
.venv/bin/python - <<'EOF'
import sys
sys.path.insert(0, "sys/core")
from aurora import sys_config as C
c = C.get()
port = "" if c["AURORA_HTTPS_PORT"] == 443 else f":{c['AURORA_HTTPS_PORT']}"
print(f"  WebUI:   https://{c['AURORA_DOMAIN']}{port}/")
print(f"  API key: {c['AURORA_API_KEY']}   (once, to register each browser or app)")
EOF
echo
.venv/bin/python sys/core/script/sys_doctor.py || warn "$(t 'qualcosa di obbligatorio non va: vedi sopra' 'something required is wrong: see above')"
echo "  $(t 'Funzioni non scelte: si aggiungono quando vuoi con' 'Features not chosen: add them any time with'): .venv/bin/python sys/core/script/sys_models_fetch.py --models <$(t 'nome' 'name')> --yes"
echo "  $(t 'Log dell installazione' 'Installation log'): $ROOT/install.log"
