#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Remove Aurora from this computer (owner, 2026-10-06), guided:
#   1) keep your data, settings and projects — services, environment, programs (and, if you say so, the models) go;
#      a reinstall in this folder starts again where you were (install.sh keeps the .env, the vault, usr/);
#   2) remove everything — after a double confirmation; first make a backup (the NAS copy is never touched).
# Never touched: the backups on the NAS, the NVIDIA driver, CUDA, the apt packages (listed at the end).
#
#   bash uninstall.sh                # asks
#   bash uninstall.sh --dry-run [1|2] # shows what a choice would do, changes nothing
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
IT=1; case "${LANG:-}" in it*|"") IT=1 ;; *) IT=0 ;; esac
t() { if [ "$IT" = 1 ]; then echo "$1"; else echo "$2"; fi; }
step() { echo; echo -e "\e[1;36m━━ $* ━━\e[0m"; }
ok() { echo -e "  \e[32m✓\e[0m $*"; }
warn() { echo -e "  \e[33m!\e[0m $*"; }
run() { if [ "$DRY" = 1 ]; then echo "    [dry-run] $*"; else "$@"; fi; }
[ "$(id -u)" != 0 ] || { echo "$(t 'Lancialo come utente normale: sudo verrà chiesto quando serve.' 'Run it as a normal user: sudo is asked when needed.')"; exit 1; }

# only the units this installation put there (sys/deploy/systemd), with their drop-in and .wants folders — never
# other files with a similar name (an older installation's copies stay the owner's)
UNITS=""
for f in sys/deploy/systemd/*.service sys/deploy/systemd/*.timer sys/deploy/systemd/*.target; do
  [ -e "$f" ] || continue
  u=$(basename "$f")
  for x in "$u" "$u.d" "$u.wants"; do [ -e "/etc/systemd/system/$x" ] && UNITS="$UNITS $x"; done
done
step "$(t 'Rimozione di Aurora' 'Removing Aurora') — $ROOT"
echo "  $(t 'Servizi installati' 'Installed services'): ${UNITS:-—}"
echo "  1) $(t 'Togli Aurora, TIENI dati, impostazioni e progetti (vault, usr/, .env, plugin, stato): una reinstallazione qui riparte da dove eri' 'Remove Aurora, KEEP data, settings and projects (vault, usr/, .env, plugins, state): a reinstall here starts where you were')"
echo "  2) $(t 'Rimuovi TUTTO: anche i dati, le chiavi in ~/.config/aurora e /etc/aurora, la cartella' 'Remove EVERYTHING: the data too, the keys in ~/.config/aurora and /etc/aurora, the folder')"
echo "  0) $(t 'Annulla' 'Cancel')"
if [ "$DRY" = 1 ]; then CHOICE=${2:-1}; echo "  > $CHOICE"; else read -r -p "  > " CHOICE; fi
case "$CHOICE" in 1|2) ;; *) echo "$(t 'Annullato.' 'Cancelled.')"; exit 0 ;; esac

if [ "$CHOICE" = 2 ] && [ "$DRY" = 0 ]; then
  warn "$(t 'Prima di tutto un backup: 🧩 Plugin → backup → 💾 Esegui ora, e conserva il codice di recupero della chiave.' 'A backup first: 🧩 Plugins → backup → 💾 Run now, and keep the key recovery code.')"
  read -r -p "  $(t 'Per rimuovere TUTTO scrivi' 'To remove EVERYTHING type') RIMUOVI AURORA: " C1
  [ "$C1" = "RIMUOVI AURORA" ] || { echo "$(t 'Annullato.' 'Cancelled.')"; exit 0; }
  read -r -p "  $(t 'Sicuro? Senza un backup i dati non si recuperano. Scrivi' 'Sure? Without a backup the data cannot be recovered. Type') SI: " C2
  [ "$C2" = "SI" ] || [ "$C2" = "YES" ] || { echo "$(t 'Annullato.' 'Cancelled.')"; exit 0; }
fi

step "$(t 'Servizi' 'Services')"
if [ -n "$UNITS" ]; then
  run sudo systemctl disable --now aurora.target aurora-backup.timer
  for u in $UNITS; do case "$u" in *.d|*.wants) ;; *) run sudo systemctl disable --now "$u" ;; esac; done
  if mountpoint -q /mnt/aurora-nas 2>/dev/null; then run sudo umount /mnt/aurora-nas; fi
  for u in $UNITS; do run sudo rm -rf "/etc/systemd/system/$u"; done
  run sudo systemctl daemon-reload
  ok "$(t 'servizi fermati e tolti' 'services stopped and removed')"
fi
if [ -f /etc/polkit-1/rules.d/50-aurora.rules ]; then run sudo rm -f /etc/polkit-1/rules.d/50-aurora.rules; ok "polkit"; fi
if command -v caddy >/dev/null && [ -d "$HOME/.local/share/caddy/pki" ]; then
  run caddy untrust; ok "$(t 'certificato locale di Caddy non più fidato' 'Caddy local certificate no longer trusted')"
fi

step "$(t 'Programmi' 'Programs')"
for d in .venv sys/runtime; do if [ -e "$d" ]; then run rm -rf "$ROOT/$d"; ok "$d"; fi; done
if [ -d sys/models ]; then
  SIZE=$(du -sh sys/models 2>/dev/null | cut -f1)
  DROP=n
  if [ "$CHOICE" = 2 ]; then DROP=y
  elif [ "$DRY" = 0 ]; then
    read -r -p "  $(t "Togliere anche i modelli ($SIZE)? Reinstallando si riscaricano. [s/N]" "Remove the models too ($SIZE)? A reinstall downloads them again. [y/N]") " M
    case "$M" in s|S|y|Y) DROP=y ;; esac
  fi
  if [ "$DROP" = y ]; then run rm -rf "$ROOT/sys/models"; ok "sys/models ($SIZE)"
  else ok "$(t 'modelli tenuti' 'models kept'): sys/models ($SIZE)"; fi
fi

if [ "$CHOICE" = 1 ]; then
  step "$(t 'Tenuti' 'Kept')"
  for d in .env sys/vault sys/status sys/plugins usr; do [ -e "$d" ] && ok "$d"; done
  echo "  $(t 'Per tornare: bash install.sh in questa cartella — è un aggiornamento: nessuna domanda, le scelte del .env restano.' 'To come back: bash install.sh in this folder — an update: no question asked, the choices in .env stay.')"
else
  step "$(t 'Dati e chiavi' 'Data and keys')"
  if [ -d /etc/aurora ]; then run sudo rm -rf /etc/aurora; ok "/etc/aurora"; fi
  if [ -d "$HOME/.config/aurora" ]; then run rm -rf "$HOME/.config/aurora"; ok "~/.config/aurora"; fi
  # usr/ holds the people's own documents (papers, projects, health): kept outside unless asked a third time
  if [ -d usr ]; then
    KEEPUSR="$HOME/Aurora-documenti-$(date +%Y%m%d-%H%M%S)"
    ANS=""
    [ "$DRY" = 0 ] && read -r -p "  $(t "usr/ (i vostri documenti, papers, progetti, salute) va in $KEEPUSR. Per cancellare anche quelli scrivi" "usr/ (your documents, papers, projects, health) goes to $KEEPUSR. To delete those too type") CANCELLA ANCHE I DOCUMENTI: " ANS
    if [ "$ANS" = "CANCELLA ANCHE I DOCUMENTI" ]; then warn "$(t 'anche usr/ verrà cancellata' 'usr/ will be deleted too')"
    else run mv "$ROOT/usr" "$KEEPUSR"; ok "$(t 'documenti messi al sicuro in' 'documents kept in') $KEEPUSR"; fi
  fi
  cd /
  run rm -rf "$ROOT"; ok "$ROOT"
  # the folder was the git clone: a clean installation starts from a new one (the owner's colleague, 9 Oct)
  echo "  $(t 'Per una installazione pulita:' 'For a clean installation:') git clone https://github.com/Soliton0382/A.U.R.O.R.A..git aurora && cd aurora && bash install.sh"
fi

step "$(t 'Lasciati al loro posto' 'Left in place')"
echo "  $(t 'i backup sul NAS; il driver NVIDIA e CUDA; i pacchetti apt installati per Aurora (ffmpeg, poppler-utils, caddy…): togli quelli che non usi con' 'the backups on the NAS; the NVIDIA driver and CUDA; the apt packages installed for Aurora (ffmpeg, poppler-utils, caddy…): remove those you do not use with') sudo apt remove …"
# the browsers keep the old key and the old WebUI (its service worker): after a new installation they must forget
# them (the owner's colleague, 9 Oct: only the background and the stars)
echo "  $(t 'nei browser e sul telefono: la vecchia chiave e la WebUI in cache. Dopo una nuova installazione, nel browser: impostazioni del sito → Cancella dati (o Ctrl+Shift+R), poi la nuova chiave API; sul telefono togli e rimetti l app.' 'in the browsers and on the phone: the old key and the cached WebUI. After a new installation, in the browser: site settings → Clear data (or Ctrl+Shift+R), then the new API key; on the phone remove and add the app again.')"
if [ "$DRY" = 1 ]; then echo; warn "$(t 'dry-run: niente è stato cambiato' 'dry-run: nothing was changed')"; fi
exit 0
