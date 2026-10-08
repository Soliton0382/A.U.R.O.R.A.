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
if [ "$CHECK" = 1 ]; then exec bash "$SRC/sys/core/script/dev_publish.sh" "$MIRROR"; fi
[ -n "$MSG" ] || { echo 'a message: publish.sh "what changed"'; exit 2; }

say "== the code of conduct"
STATE="$("$PY" "$SRC/sys/core/script/sys_ethics_sign.py" check 2>/dev/null || true)"
echo "$STATE" | sed 's/^/  /'
if echo "$STATE" | grep -q "^OK: " && echo "$STATE" | grep -q "every file as signed"; then
  echo "  nothing changed since the last signature"
else
  sudo "$PY" "$SRC/sys/core/script/sys_ethics_sign.py" sign
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
