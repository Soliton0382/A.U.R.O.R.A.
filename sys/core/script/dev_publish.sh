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
#   - every Python file compiles; the test suite passes on the mirror's code.
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

say "== files to publish (what .gitignore lets through)"
# a throw-away git directory reads .gitignore: the installation itself needs no repository
git init -q --bare "$GITTMP"
git --git-dir="$GITTMP" --work-tree="$SRC" ls-files --others --exclude-standard | sort -u > "$LIST"
echo "$(wc -l < "$LIST") files"

say "== forbidden paths"
if grep -nE '^(sys/(vault|status|logs|models|runtime|sandbox|https|deploy|tmp)/|usr/|tmp/|\.claude/|CLAUDE\.md$|\.venv|.*\.env$|.*\.sig$|.*MANIFEST\.json$|.*id_(ed25519|rsa|ecdsa).*)' "$LIST"; then
  fail "forbidden paths above: fix .gitignore"
fi

say "== copy to $DST"
rsync -a --files-from="$LIST" "$SRC/" "$DST/"
(cd "$DST" && find . -type f -not -path './.git/*' | sed 's#^\./##' | sort) | comm -23 - "$LIST" | while read -r gone; do
  echo "  removed from the mirror: $gone"; rm -f -- "$DST/$gone"
done
find "$DST" -type d -empty -not -path "$DST/.git*" -delete

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

say "== code"
PY="$SRC/.venv/bin/python"
(cd "$DST" && "$PY" -m compileall -q sys/core sys/plugins >/dev/null) || fail "Python files that do not compile"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$DST/sys/core" && PYTHONDONTWRITEBYTECODE=1 timeout 1800 "$PY" -m pytest -q -p no:cacheprovider tests --ignore=tests/test_models_gpu.py) | tail -2 \
  || fail "tests failed on the mirror"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +

cd "$DST"
[ -d .git ] || { git init -q -b main; say "== new repository in $DST"; }
git add -A
say "== changes"
git status --short | head -40; echo "$(git status --short | wc -l) changed"
if [ -n "$MSG" ]; then
  git diff --cached --quiet && { echo "nothing to commit"; exit 0; }
  git commit -q -m "$MSG" && git log --oneline -1
  if [ "$PUSH" = 1 ]; then git push -u origin main; fi
else
  echo "(no commit: add --commit \"message\")"
fi
