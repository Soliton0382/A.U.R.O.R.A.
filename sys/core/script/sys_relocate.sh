#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Move or rename the installation. The current folder is read from AURORA_ROOT in .env; the new one is
# asked (or given as the first argument). Run it from a normal terminal, outside the installation folder
# and outside any program working in it, as the owner; sudo is asked for the units and the exemption.
#
#   bash /path/to/aurora/sys/core/script/sys_relocate.sh [/new/path]
#
# Steps (the procedure used on 2026-10-01 to rename the installation folder):
#   1. services stop;  2. AURORA_ROOT in .env becomes the new folder (Aurora refuses to start on a mismatch);
#   3. the folder moves;  4. the venv is created again from requirements.txt (a venv holds absolute paths),
#      the old one kept as .venv.old and put back if pip fails;  5. units and Caddyfile generated again and
#      installed;  6. the level-B exemption, bound to the folder, signed again if it existed;  7. start + checks.
# The installation's key in /etc/aurora and the signed manifest do not depend on the folder.
# Claude Code keeps its history per folder: open it in the new folder (claude --continue starts fresh there).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/../../.." && pwd)"
OLD=$(cd "$HERE" && python3 -c "
import sys; sys.path.insert(0, 'sys/core')
from aurora import sys_config as C
f = C.env_file_path(); print(C.parse_env(f.read_text(encoding='utf-8'), str(f))['AURORA_ROOT'])")
[ "$OLD" = "$HERE" ] || { echo "AURORA_ROOT=$OLD but the script runs from $HERE: fix that first"; exit 1; }

NEW="${1:-}"
if [ -z "$NEW" ]; then
  read -r -p "Current folder: $OLD
New folder [$OLD]: " NEW
  NEW="${NEW:-$OLD}"
fi
NEW="$(realpath -m "$NEW")"
[ "$NEW" != "$OLD" ] || { echo "same folder: nothing to do"; exit 0; }
[ ! -e "$NEW" ] || { echo "$NEW already exists: stop"; exit 1; }
[ -d "$(dirname "$NEW")" ] || { echo "$(dirname "$NEW") does not exist"; exit 1; }
case "$PWD" in "$OLD"*) echo "run it from another folder (cd ~)"; exit 1 ;; esac

UNITS="aurora-harvester aurora-rem aurora-sentinel aurora-api aurora-https aurora-llm aurora-models"
EXEMPT=$(cd "$OLD" && .venv/bin/python -c "
import sys; sys.path.insert(0, 'sys/core')
from aurora import sys_ethics; print(1 if sys_ethics.exempt() else 0)" 2>/dev/null || echo 0)

echo "Move: $OLD -> $NEW   (level-B exemption: $([ "$EXEMPT" = 1 ] && echo 'signed again' || echo 'none'))"
read -r -p "Proceed? [y/N] " ok; [ "$ok" = y ] || [ "$ok" = s ] || exit 0

echo "== 1. stop";        sudo systemctl stop $UNITS
echo "== 2. AURORA_ROOT"
python3 - "$OLD/.env" "$NEW" <<'EOF'
import os, sys
path, root = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines()
assert sum(l.startswith("AURORA_ROOT=") for l in lines) == 1
lines = [f"AURORA_ROOT={root}" if l.startswith("AURORA_ROOT=") else l for l in lines]
fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
os.replace(path + ".tmp", path)
EOF
echo "== 3. move";        mv "$OLD" "$NEW"; cd "$NEW"
echo "== 4. venv"
mv .venv .venv.old
if python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; then
  echo "venv ok (the old one is .venv.old: delete it when you are happy)"
else
  echo "pip failed: the old venv goes back, its paths rewritten"
  mv .venv .venv.failed; mv .venv.old .venv
  sed -i "s#$OLD#$NEW#g" .venv/pyvenv.cfg
  grep -rl "$OLD" .venv/bin | xargs -r sed -i "s#$OLD#$NEW#g"
fi
echo "== 5. units";       .venv/bin/python sys/core/script/sys_install_services.py; sudo bash sys/deploy/systemd/install.sh
echo "== 6. ethics"
[ "$EXEMPT" = 1 ] && sudo .venv/bin/python sys/core/script/sys_ethics_sign.py exempt
.venv/bin/python sys/core/script/sys_ethics_sign.py check
echo "== 7. start";       sudo systemctl start aurora.target; sleep 20
for u in $UNITS; do printf '%-18s %s\n' "$u" "$(systemctl is-active $u)"; done
echo "Done: $NEW"
