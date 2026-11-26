#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# Aurora on a computer where Aurora is not installed (owner, 27 Nov: «se non viene installata sulla stessa macchina
# allora utilizza il medesimo form dell'app android»): the WebUI's window only — the address asked once (the Android
# app's form), the login once, Aurora's notifications on this desktop. Downloaded from Aurora (📱 App → 🖥️ Computer).
# For this user only, nothing as root: ~/.local/share/aurora-desk-client (its own Python), ~/.local/bin/aurora,
# the menu's entry. Linux with a desktop (Wayland or X11), Python 3.10 or newer.
#     sh install.sh            install or update
#     sh install.sh --remove   take it away (the login kept in ~/.local/state/aurora-desk goes too)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/aurora-desk-client"
BIN="$HOME/.local/bin/aurora"
MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications/aurora-desk-client.desktop"

if [ "${1:-}" = "--remove" ]; then
  rm -rf "$DEST" "${XDG_STATE_HOME:-$HOME/.local/state}/aurora-desk"
  rm -f "$BIN" "$MENU"
  echo "Aurora tolta da questo computer."
  exit 0
fi

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "Serve Python 3 (python3)." >&2; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Serve Python 3.10 o più recente." >&2; exit 1; }
"$PY" -c 'import venv' 2>/dev/null || { echo "Serve il modulo venv di Python (python3-venv)." >&2; exit 1; }

mkdir -p "$DEST" "$HOME/.local/bin" "$(dirname "$MENU")"
[ -x "$DEST/venv/bin/python" ] || "$PY" -m venv "$DEST/venv"
"$DEST/venv/bin/python" -m pip install -q --disable-pip-version-check -r "$HERE/requirements.txt"
rm -rf "$DEST/desk"
cp -R "$HERE/desk" "$DEST/desk"

cat > "$BIN" <<EOF
#!/bin/sh
# Aurora's window (written by Aurora's desktop installer)
exec "$DEST/venv/bin/python" -I -B "$DEST/desk/app/web.py" "\$@"
EOF
chmod 755 "$BIN"
cat > "$MENU" <<EOF
[Desktop Entry]
Type=Application
Name=Aurora
Comment=Aurora, la tua assistente
Exec=$BIN
Icon=aurora-desk
Terminal=false
Categories=Network;Office;
EOF
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
mkdir -p "$ICONS"
"$DEST/venv/bin/python" -I -B -c "import sys; sys.path.insert(0, '$DEST'); from desk.app import icon; print(icon.SVG)" \
  > "$ICONS/aurora-desk.svg" 2>/dev/null || true
echo "Aurora installata: cercala nel menu, oppure lancia «aurora». La prima volta ti chiede l'indirizzo della tua Aurora."
