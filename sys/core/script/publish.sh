#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# One command to publish (owner, 2026-10-08: «con un comando solo si firma e si pubblica»): the code of conduct signed
# when the code changed (sudo asks the password once), the mirror checked and committed (dev_publish.sh: paths,
# secrets, personal data, tests, the ports built), pushed; with --release also a version: CHANGELOG.md and
# pyproject.toml, a signed tag pushed — GitHub makes the release from it (.github/workflows/release.yml) and runs the
# ports on a real Mac and Windows (ports.yml).
#
#   bash sys/core/script/publish.sh "message"                     # sign + publish + push
#   bash sys/core/script/publish.sh "message" --release 0.2.0     # + version 0.2.0, tag v0.2.0, the GitHub release
#   bash sys/core/script/publish.sh "message" --no-push           # commit in the mirror only
#   bash sys/core/script/publish.sh --check                        # copy and checks, nothing signed or committed
#
# Run it as yourself, not with sudo: the mirror and its git keys are yours; only the signature needs root.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
MIRROR="${AURORA_PUBLISH_MIRROR:-$(dirname "$SRC")/Aurora_git}"
PY="$SRC/.venv/bin/python"
# C556: the folder's bytecode is the services' to write: the owner's Python keeps its own, never loads theirs
export PYTHONPYCACHEPREFIX="${XDG_CACHE_HOME:-$HOME/.cache}/aurora-pycache"
ROOTCMD=/usr/local/sbin/aurora-root
MSG=""; RELEASE=""; PUSH=1; CHECK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --release) RELEASE="${2#v}"; shift ;;
    --no-push) PUSH=0 ;;
    --check) CHECK=1 ;;
    --mirror) MIRROR="$2"; shift ;;
    -*) echo "unknown option $1"; exit 2 ;;
    *) MSG="$1" ;;
  esac
  shift
done
say() { echo -e "\e[1m$*\e[0m"; }
[ "$(id -u)" != 0 ] || { echo "run it as yourself, not with sudo (sudo is asked only for the signature)"; exit 2; }
[ -d "$MIRROR/.git" ] || { echo "no mirror at $MIRROR (AURORA_PUBLISH_MIRROR or --mirror)"; exit 2; }
if [ "$CHECK" = 1 ]; then                # C556: the checks run the folder's code as the owner: only as signed
  if [ -x "$ROOTCMD" ] && ! "$ROOTCMD" verify; then echo "sign first (sudo aurora-root sign), then --check"; exit 2; fi
  exec bash "$SRC/sys/core/script/dev_publish.sh" "$MIRROR"
fi
[ -n "$MSG" ] || { echo 'a message: publish.sh "what changed"'; exit 2; }

# The commit, the tag and the two pushes all use the git SSH key: its passphrase asked once here (kept in the agent
# for an hour), not four times (owner, 2026-10-14: «almeno 4/5 volte quando lancio il comando»).
KEY="$(git -C "$MIRROR" config user.signingkey || true)"
KEY="${KEY%.pub}"
if [ -n "$KEY" ] && [ -f "$KEY" ]; then
  if [ -z "${SSH_AUTH_SOCK:-}" ]; then eval "$(ssh-agent -s)" >/dev/null; trap 'ssh-agent -k >/dev/null' EXIT; fi
  ssh-add -l >/dev/null 2>&1 || ssh-add -t 3600 "$KEY" || { echo "the SSH key was not unlocked"; exit 2; }
fi

say "== the code of conduct"
# C556: asked to root's copy with the system's Python (no sudo), never to the folder's own code: until the owner has
# seen the list and signed, nothing of the folder runs as him
if [ -x "$ROOTCMD" ]; then
  if STATE="$("$ROOTCMD" verify)"; then echo "  nothing changed since the last signature"
  else
    echo "$STATE" | sed 's/^/  /'
    sudo "$ROOTCMD" sign                 # root signs (sys_root.py, 9 Nov): the list of what changed, then «s»
    "$ROOTCMD" verify >/dev/null || { echo "  the code is not as signed: nothing published"; exit 2; }
  fi
else                                     # the first time: the setup, from Aurora's folder
  sudo /usr/bin/python3 -I "$SRC/sys/core/script/sys_root.py" setup
fi

KEEP=""
restore() {
  [ -n "$KEEP" ] || return 0
  cp "$KEEP/pyproject.toml" "$SRC/"
  if [ -f "$KEEP/CHANGELOG.md" ]; then cp "$KEEP/CHANGELOG.md" "$SRC/"; else rm -f -- "$SRC/CHANGELOG.md"; fi
  echo "pyproject.toml and CHANGELOG.md put back: the same command can be run again"
}
if [ -n "$RELEASE" ]; then
  say "== version $RELEASE"
  KEEP="$(mktemp -d)"
  cp "$SRC/pyproject.toml" "$KEEP/"
  [ ! -f "$SRC/CHANGELOG.md" ] || cp "$SRC/CHANGELOG.md" "$KEEP/"
  trap restore ERR                       # a failure before the commit leaves no version half made
  "$PY" "$SRC/sys/core/script/dev_changelog.py" "$MIRROR" "$RELEASE" "$MSG"
fi

say "== publish"
# one time for the commit and the tag: the last 19:00 not in the future, never the hour of work (owner, 2026-10-14)
if [ "$(date +%H)" -ge 19 ]; then AT="$(date +%Y-%m-%d)"; else AT="$(date -d yesterday +%Y-%m-%d)"; fi
export GIT_AUTHOR_DATE="${AT}T19:00:00" GIT_COMMITTER_DATE="${AT}T19:00:00"
ARGS=(--commit "$MSG")
[ "$PUSH" = 0 ] || ARGS+=(--push)
bash "$SRC/sys/core/script/dev_publish.sh" "$MIRROR" "${ARGS[@]}"
trap - ERR
KEEP=""

if [ -n "$RELEASE" ]; then
  say "== tag v$RELEASE (signed)"
  git -C "$MIRROR" tag -s "v$RELEASE" -m "Aurora v$RELEASE"
  git -C "$MIRROR" -c gpg.ssh.allowedSignersFile="$MIRROR/sys/core/config/allowed_signers" verify-tag "v$RELEASE"
  if [ "$PUSH" = 1 ]; then
    git -C "$MIRROR" push origin "v$RELEASE"
    echo "GitHub makes the release now (Actions → Release); the ports run on a real Mac and Windows (Actions → Ports)"
  fi
fi
say "== done"
