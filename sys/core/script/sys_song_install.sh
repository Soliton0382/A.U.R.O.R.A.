#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# The music model that sings Aurora's songs (aud_song): ACE-Step 1.5 (MIT) in an environment of its own, everything
# inside Aurora's folder (owner, 2026-10-27: «vorrei che tutto stia dentro la cartella di installazione di aurora e
# non in giro per il sistema»):
#   sys/runtime/uv/            uv itself (pinned, SHA-256 checked), its package cache and the Python it installs
#   sys/runtime/ace-step/      ACE-Step's code at a pinned commit, its .venv, its caches
#   sys/models/music/ace-step  the weights (config/models.json "music": pinned revision, SHA-256 checked)
# Nothing in ~/.cache, ~/.local or the system's Python. Run again: what is there is kept, what is missing is added.
#
#   bash sys/core/script/sys_song_install.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
ROOT=$PWD
RT=$ROOT/sys/runtime
UV_VERSION=0.11.16
ACE_REPO=https://github.com/ACE-Step/ACE-Step-1.5.git
ACE_COMMIT=ca1e85fe9430179831e6bc6be790c332190a3866
case "$(uname -m)" in
  x86_64)  UV_ARCH=x86_64-unknown-linux-gnu;  UV_SHA=74947fe2c03315cf07e82ab3acc703eddef01aba4d5232a98e4c6825ec116131 ;;
  aarch64) UV_ARCH=aarch64-unknown-linux-gnu; UV_SHA=8c9d0f0ee98166ae6ab198747519ba6f25db29d185bd2ae5960ecebc91a5c22a ;;
  *) echo "❌ songs: no uv build for $(uname -m)"; exit 1 ;;
esac
# every cache and every Python of uv and of ACE-Step inside Aurora (aud_song.inside gives the service the same)
eval "$("$ROOT/.venv/bin/python" -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import aud_song
for k, v in aud_song.inside('$ROOT').items(): print(f'export {k}={v!r}')")"

if [ ! -x "$RT/uv/bin/uv" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/uv.tgz" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$UV_ARCH.tar.gz"
  echo "$UV_SHA  $tmp/uv.tgz" | sha256sum -c --quiet - || { echo "❌ uv: SHA-256 does not match"; exit 1; }
  mkdir -p "$RT/uv/bin"
  tar -xzf "$tmp/uv.tgz" -C "$tmp"
  install -m 0755 "$tmp/uv-$UV_ARCH/uv" "$RT/uv/bin/uv"
  find "$tmp" -delete
fi
UV="$RT/uv/bin/uv"

if [ ! -d "$RT/ace-step/.git" ]; then
  git clone -q "$ACE_REPO" "$RT/ace-step"
fi
git -C "$RT/ace-step" fetch -q origin "$ACE_COMMIT" 2>/dev/null || true
git -C "$RT/ace-step" checkout -q "$ACE_COMMIT"
# a .venv on a Python outside Aurora (a first install made by hand) is made again on uv's own, inside
if [ -e "$RT/ace-step/.venv/bin/python" ] && [[ "$(readlink -f "$RT/ace-step/.venv/bin/python")" != "$RT"/* ]]; then
  "$UV" venv --clear --python 3.12 "$RT/ace-step/.venv" >/dev/null
fi
(cd "$RT/ace-step" && "$UV" sync --frozen --python 3.12)

"$ROOT/.venv/bin/python" sys/core/script/sys_models_fetch.py --models music --yes
echo "✅ songs ready: the DJ page's «🎤 Canzone da un'idea»"
