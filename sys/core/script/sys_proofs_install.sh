#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Formal proofs (N143 proof_check in the projects, N144 «/lean …» in the chat): Lean 4 and Mathlib into
# AURORA_LEAN_HOME (default sys/runtime/lean). Optional: without it proof_check and the chat's prover say
# «Lean non installato» and nothing else changes. install.sh runs it with --with-lean (or when the answer is yes);
# run it by hand to add or repair it later. Network needed; about 11 GB on disk (measured on the owner's machine).
#
#   bash sys/core/script/sys_proofs_install.sh             # install or repair into sys/runtime/lean
#   bash sys/core/script/sys_proofs_install.sh --dry-run   # says what it would do, changes nothing
#   bash sys/core/script/sys_proofs_install.sh /some/dir   # another folder: then set AURORA_LEAN_HOME to it in Settings
#
# What comes from where (each pinned):
#   elan (the toolchain manager)  github.com/leanprover/elan, release v4.4.0, SHA-256 checked
#   the Lean toolchain            github.com/leanprover/lean4, release v4.36.0, SHA-256 checked
#   Mathlib and its dependencies  the git revisions of sys/deploy/lean/lake-manifest.json (lake clones them), and
#                                 Mathlib's compiled library downloaded from Mathlib's cache server over TLS (lake exe
#                                 cache get): lake picks the files by the hashes of their sources, but their content is
#                                 NOT pinned here — it is trusted as Mathlib's own build (C657)
# Nothing is installed outside the folder: no PATH change, no shell profile edited (elan-init --no-modify-path).
# A folder this script created carries .installed-by-aurora: uninstall.sh removes only such a folder when it lives
# outside Aurora's folder and holds nothing else (sys/runtime itself goes with the programs).
#   --update  a workspace this script made, whose package revisions differ from sys/deploy/lean's, is brought to them
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DRY=0; UPDATE=0; HOME_DIR=""
for a in "$@"; do                                     # C657: the options in any order (a «dir --dry-run» installed)
  case "$a" in
    --dry-run) DRY=1 ;;
    --update) UPDATE=1 ;;
    -*) echo "formal proofs: unknown option $a (--dry-run, --update)"; exit 2 ;;
    *) [ -z "$HOME_DIR" ] || { echo "formal proofs: one folder only"; exit 2; }; HOME_DIR="$a" ;;
  esac
done
HOME_DIR="${HOME_DIR:-$ROOT/sys/runtime/lean}"
HOME_DIR="$(realpath -m -- "$HOME_DIR")"              # C668: a relative folder broke after «cd workspace»
# C657: never a folder that holds something else (a «sys_proofs_install.sh ~» made the home folder readable to all)
if [ -d "$HOME_DIR" ] && [ "$HOME_DIR" != "$ROOT/sys/runtime/lean" ] && [ ! -f "$HOME_DIR/.installed-by-aurora" ] \
   && [ -n "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  echo "formal proofs: $HOME_DIR exists, is not empty and was not made by this script: choose a new folder"; exit 1
fi
revs() { grep -o '"rev": *"[0-9a-f]*"' "$1" 2>/dev/null | sort | sha256sum | cut -c1-16; }
ELAN_VERSION="4.4.0"
LEAN_TAG="v4.36.0"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    EA="elan-x86_64-unknown-linux-gnu.tar.gz"; ESHA="0e8250aa2be86c7af929ade68db617af9edc8b9ccf6eaf5ece228250d0d032e2"
    LA="lean-4.36.0-linux.tar.zst"; LSHA="2b7ab1ed8b92d2e6abfaf41344823b510064dbc9c0260cac73eb496ab2dea6eb" ;;
  Linux-aarch64)
    EA="elan-aarch64-unknown-linux-gnu.tar.gz"; ESHA="45cde3006f82f98804c94cf2ca4949d117060a5f3cc8afa62f523759947ee21f"
    LA="lean-4.36.0-linux_aarch64.tar.zst"; LSHA="35471998152191ef809418ce5bf61f8fc5f209e5e3be05b48bdc4949fdb3e726" ;;
  *) echo "formal proofs: no pinned Lean release for $(uname -s) $(uname -m) here"; exit 1 ;;
esac
export ELAN_HOME="$HOME_DIR/elan"
TCDIR="$ELAN_HOME/toolchains/leanprover--lean4---$LEAN_TAG"
WS="$HOME_DIR/workspace"
MATHLIB="$WS/.lake/packages/mathlib/.lake/build/lib/lean"

PINNED="$(revs "$ROOT/sys/deploy/lean/lake-manifest.json")"
if [ -x "$ELAN_HOME/bin/elan" ] && [ -x "$TCDIR/bin/lean" ] && [ -d "$MATHLIB" ]; then
  if [ "$(revs "$WS/lake-manifest.json")" = "$PINNED" ]; then
    echo "Lean $LEAN_TAG and Mathlib already installed in $HOME_DIR"; exit 0
  fi
  # C657: installed, but the workspace's package revisions are not sys/deploy/lean's (an update of the manifest)
  if [ "$UPDATE" != 1 ] || [ ! -f "$WS/.from-aurora-template" ]; then
    echo "Lean $LEAN_TAG and Mathlib installed in $HOME_DIR, but its package revisions differ from sys/deploy/lean's"
    [ -f "$WS/.from-aurora-template" ] && echo "  run again with --update to bring them in line" \
      || echo "  its workspace was not made by this script: left as it is (your own lakefile is not overwritten)"
    exit 0
  fi
  [ "$DRY" = 1 ] && { echo "[dry-run] workspace revisions brought to sys/deploy/lean's, then lake exe cache get"; exit 0; }
  cp "$ROOT/sys/deploy/lean/lakefile.toml" "$ROOT/sys/deploy/lean/lean-toolchain" "$ROOT/sys/deploy/lean/lake-manifest.json" "$WS/"
fi
if [ "$DRY" = 1 ]; then
  [ -x "$ELAN_HOME/bin/elan" ] || echo "[dry-run] elan $ELAN_VERSION ($EA, SHA-256 $ESHA) into $ELAN_HOME"
  [ -x "$TCDIR/bin/lean" ] || echo "[dry-run] Lean $LEAN_TAG ($LA, SHA-256 $LSHA) into $TCDIR"
  [ -f "$WS/lean-toolchain" ] || echo "[dry-run] workspace from sys/deploy/lean into $WS"
  [ -d "$MATHLIB" ] || echo "[dry-run] Mathlib (manifest revisions) and its compiled cache into $WS/.lake"
  echo "[dry-run] chmod -R a+rX $ELAN_HOME $WS (the services' account reads them)"; exit 0
fi
for p in curl tar zstd git sha256sum; do
  command -v "$p" >/dev/null || { echo "formal proofs: «$p» is missing (sudo apt-get install $p)"; exit 1; }
done
PARENT="$(dirname "$HOME_DIR")"; mkdir -p "$PARENT"
FREE=$(df -BG --output=avail "$PARENT" | tail -1 | tr -dc '0-9')
[ "$FREE" -ge 14 ] || { echo "formal proofs: 14 GB free needed in $PARENT, ${FREE} GB available"; exit 1; }
if [ ! -e "$HOME_DIR" ] || [ -z "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  mkdir -p "$HOME_DIR"; date -u +%F > "$HOME_DIR/.installed-by-aurora"
fi
DL="$HOME_DIR/.download"; mkdir -p "$DL"; trap 'rm -r -- "$DL"' EXIT   # on disk: /tmp may live in RAM

if [ ! -x "$ELAN_HOME/bin/elan" ]; then
  curl -fsSL -o "$DL/$EA" "https://github.com/leanprover/elan/releases/download/v$ELAN_VERSION/$EA"
  echo "$ESHA  $DL/$EA" | sha256sum -c --quiet - || { echo "formal proofs: elan SHA-256 differs, not installed"; exit 1; }
  tar -xzf "$DL/$EA" -C "$DL"
  "$DL/elan-init" -y --no-modify-path --default-toolchain none >/dev/null
fi
echo "elan $("$ELAN_HOME/bin/elan" --version | cut -d' ' -f2)"

if [ ! -x "$TCDIR/bin/lean" ]; then
  curl -fsSL -o "$DL/$LA" "https://github.com/leanprover/lean4/releases/download/$LEAN_TAG/$LA"
  echo "$LSHA  $DL/$LA" | sha256sum -c --quiet - || { echo "formal proofs: Lean SHA-256 differs, not installed"; exit 1; }
  mkdir -p "$TCDIR"
  tar --zstd -xf "$DL/$LA" -C "$TCDIR" --strip-components=1
fi
"$TCDIR/bin/lean" --version

if [ ! -f "$WS/lean-toolchain" ]; then
  mkdir -p "$WS"
  cp "$ROOT/sys/deploy/lean/lakefile.toml" "$ROOT/sys/deploy/lean/lean-toolchain" "$ROOT/sys/deploy/lean/lake-manifest.json" "$WS/"
  date -u +%F > "$WS/.from-aurora-template"
fi
# the toolchain's own lake, never one found on PATH; the manifest's revisions, then Mathlib's compiled library
(cd "$WS" && PATH="$TCDIR/bin:$PATH" lake exe cache get)
[ -d "$MATHLIB" ] || { echo "formal proofs: Mathlib not built in $WS"; exit 1; }
# the check proof_check itself relies on: a theorem using Mathlib compiles with the workspace's paths
printf 'import Mathlib.Data.Nat.Basic\nexample (n : Nat) : n + 0 = n := by simp\n' > "$DL/Check.lean"
(cd "$WS" && PATH="$TCDIR/bin:$PATH" lake env lean "$DL/Check.lean") || { echo "formal proofs: the check did not compile"; exit 1; }
chmod a+rX "$HOME_DIR"; chmod -R a+rX "$ELAN_HOME" "$WS"   # C657: only what this script made
echo "Lean $LEAN_TAG and Mathlib ready in $HOME_DIR ($(du -sh "$HOME_DIR" | cut -f1))"
if [ "$HOME_DIR" != "$ROOT/sys/runtime/lean" ]; then
  echo "set AURORA_LEAN_HOME = $HOME_DIR in Settings (Projects), then restart Aurora"
fi
