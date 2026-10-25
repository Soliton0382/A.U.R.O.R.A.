#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Publish this installation's code to a separate clean folder that holds the git repository, so that the
# owner's working installation (vault, chats, keys, plugin settings, models) never meets git.
#
#   bash sys/core/script/dev_publish.sh /path/to/mirror                       # copy + checks, nothing committed
#   bash sys/core/script/dev_publish.sh /path/to/mirror --commit "message"    # + commit in the mirror
#   bash sys/core/script/dev_publish.sh /path/to/mirror --commit "message" --push
#
# What is copied: exactly the files git would publish from here (tracked + untracked not ignored by
# .gitignore). Files gone from here are removed from the mirror (its .git stays).
# Checks before any commit, each one stops the script:
#   - no forbidden path (vault, user files, status, logs, models, runtime, .env, keys, signatures, .claude);
#   - no file over 5 MB;
#   - no secret-looking string (private keys, API tokens);
#   - none of the owner's personal patterns, listed one regex per line in ~/.config/aurora/publish_deny.txt
#     (kept outside the repository on purpose: the list itself is personal);
#   - every Python file compiles; the test suite passes on the mirror's code;
#   - each port (Aurora_mac, Aurora_windows: they live in the mirror only) builds from this code, its anchors found
#     once, and its platform tests pass (a moved line of the Linux code is caught here, not on a user's Mac).
set -euo pipefail
export LC_ALL=C                       # one byte order for sort and comm

SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
DST="${1:?mirror folder}"; shift
MSG=""; PUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --commit) MSG="$2"; shift ;;
    --push) PUSH=1 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done
DST="$(realpath -m "$DST")"
[ "$DST" != "$SRC" ] || { echo "the mirror must be another folder"; exit 1; }
mkdir -p "$DST"
DENY="${AURORA_PUBLISH_DENY:-$HOME/.config/aurora/publish_deny.txt}"
LIST="$(mktemp)"; GITTMP="$(mktemp -d)"; trap 'rm -rf "$LIST" "$GITTMP"' EXIT

say() { echo -e "\e[1m$*\e[0m"; }
fail() { echo -e "\e[31mSTOP: $*\e[0m"; exit 1; }

say "== .env.example from the schema (never behind the settings)"
"$SRC/.venv/bin/python" "$SRC/sys/core/script/sys_env_sync.py" --example

say "== dependencies: lock and known vulnerabilities"
[ "$SRC/requirements.lock" -nt "$SRC/requirements.txt" ] || fail "requirements.txt changed: regenerate requirements.lock (pip-compile --generate-hashes)"
if command -v pip-audit >/dev/null; then
  pip-audit --disable-pip --require-hashes -r "$SRC/requirements.lock" || fail "known vulnerabilities above"
else
  echo "  pip-audit not installed: vulnerability scan skipped (pipx install pip-audit)"
fi

say "== files to publish (what .gitignore lets through)"
# a throw-away git directory reads .gitignore: the installation itself needs no repository
git init -q --bare "$GITTMP"
git --git-dir="$GITTMP" --work-tree="$SRC" ls-files --others --exclude-standard | sort -u > "$LIST"
echo "$(wc -l < "$LIST") files"

say "== forbidden paths"
if grep -nE '^(sys/(vault|status|logs|models|runtime|sandbox|https|deploy|tmp)/|usr/|tmp/|\.claude/|CLAUDE\.md$|\.venv|.*\.env$|.*\.sig$|.*MANIFEST\.json$|.*id_(ed25519|rsa|ecdsa).*)' "$LIST"; then
  fail "forbidden paths above: fix .gitignore"
fi

say "== the root holds only what belongs there"
# a stray file at the top (C306: «0.2.7», a command's error output, public for 4 days) stops the publish
stray=$(grep -v '/' "$LIST" | grep -vxE '\.dockerignore|\.env\.example|\.gitignore|CHANGELOG\.md|CITATION\.cff|LICENSE|NOTICE|README(\.en)?\.md|SECURITY\.md|install\.sh|uninstall\.sh|pyproject\.toml|requirements\.(txt|lock)' || true)
[ -z "$stray" ] || fail "unexpected files at the root (take them away or add them to this list): $stray"

say "== copy to $DST"
rsync -a --files-from="$LIST" "$SRC/" "$DST/"
# the ports (Aurora_mac, Aurora_windows) are made in the mirror only: never removed from it here
(cd "$DST" && find . -type f -not -path './.git/*' -not -path './Aurora_mac/*' -not -path './Aurora_windows/*' | sed 's#^\./##' | sort) | comm -23 - "$LIST" | while read -r gone; do
  echo "  removed from the mirror: $gone"; rm -f -- "$DST/$gone"
done
find "$DST" -type d -empty -not -path "$DST/.git*" -not -path "$DST/Aurora_mac*" -not -path "$DST/Aurora_windows*" -delete

say "== size"
big=$(cd "$DST" && find . -type f -not -path './.git/*' -size +5M)
[ -z "$big" ] || fail "files over 5 MB: $big"

say "== secrets"
if (cd "$DST" && grep -rnI -E 'BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}|sk-ant-[A-Za-z0-9-]{10}|sk-[A-Za-z0-9]{32}|xox[bp]-[A-Za-z0-9-]{10}|AKIA[0-9A-Z]{16}|[0-9]{8,10}:AA[A-Za-z0-9_-]{30}' --exclude-dir=.git .); then
  fail "secret-looking strings above"
fi

say "== personal data ($DENY)"
if [ -s "$DENY" ]; then
  if (cd "$DST" && grep -rnI -i -E -f "$DENY" --exclude-dir=.git .); then fail "personal data above"; fi
  echo "none of $(grep -c . "$DENY") patterns found"
else
  echo "  no deny list: create $DENY (one regex per line: your name, e-mail, domain, home address, LAN addresses...)"
  [ -z "$MSG" ] || fail "a commit needs the personal-data check"
fi

say "== private data Aurora knows (masker terms, firewall devices)"
"$SRC/.venv/bin/python" "$SRC/sys/core/script/dev_privacy_scan.py" "$DST" || fail "private data above (file:line, kind)"

say "== times of day in the documents (owner, 2026-10-14: «non ci sono orari nei documenti vero?»)"
"$SRC/.venv/bin/python" "$DST/sys/core/script/doc_times.py" --check || fail "times of day above: doc_times.py --fix, or <!-- schedule --> for a time Aurora is set to"
"$SRC/.venv/bin/python" "$DST/sys/core/script/doc_callmap.py" --check || fail "the call map above: python sys/core/script/doc_callmap.py, and every new file in docs/MODULE_MAP.md"

say "== code"
PY="$SRC/.venv/bin/python"
(cd "$DST" && "$PY" -m compileall -q sys/core sys/plugins >/dev/null) || fail "Python files that do not compile"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$DST/sys/core" && PYTHONDONTWRITEBYTECODE=1 timeout 1800 "$PY" -m pytest -q -p no:cacheprovider tests --ignore=tests/test_models_gpu.py) | tail -2 \
  || fail "tests failed on the mirror"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +

say "== ports (built from this code, platform tests)"
PORTS="$(mktemp -d)"
for port in Aurora_mac Aurora_windows; do
  [ -f "$DST/$port/build.py" ] || { echo "  $port: not in the mirror"; continue; }
  (cd "$DST" && PYTHONDONTWRITEBYTECODE=1 "$PY" "$port/build.py" --test --out "$PORTS/$port" > "$PORTS/$port.log" 2>&1) \
    || { tail -20 "$PORTS/$port.log"; fail "$port does not build or its platform tests fail (log above)"; }
  echo "  $port: $(grep -o '^== rewrites ([0-9]*)' "$PORTS/$port.log" | tr -cd '0-9') rewrites applied," \
       "$(grep -E '^[.sF]+ +\[' "$PORTS/$port.log" | tr -cd '.' | wc -c) platform tests passed"
done
rm -r -- "$PORTS"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +

cd "$DST"
[ -d .git ] || { git init -q -b main; say "== new repository in $DST"; }
git add -A
say "== changes"
git status --short | head -40; echo "$(git status --short | wc -l) changed"
if [ -n "$MSG" ]; then
  git diff --cached --quiet && { echo "nothing to commit"; exit 0; }
  # «a && b» does not stop a «set -e» script: a refused commit (its signature) went on to push nothing and tag the
  # commit before (v0.2.18 on 13 Oct) — now it stops here
  # the commit's time is not the hour it was made (owner, 2026-10-14): the last 19:00 that is not in the future,
  # for the author and the committer (and the tag, made with the same variables by publish.sh)
  if [ -z "${GIT_COMMITTER_DATE:-}" ]; then
    if [ "$(date +%H)" -ge 19 ]; then AT="$(date +%Y-%m-%d)"; else AT="$(date -d yesterday +%Y-%m-%d)"; fi
    export GIT_AUTHOR_DATE="${AT}T19:00:00" GIT_COMMITTER_DATE="${AT}T19:00:00"
  fi
  git commit -q -m "$MSG" || fail "the commit was refused (its signature? the output above): nothing pushed, no tag"
  git log --oneline -1
  if [ "$PUSH" = 1 ]; then git push -u origin main; fi
else
  echo "(no commit: add --commit \"message\")"
fi
