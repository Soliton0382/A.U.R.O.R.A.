#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# The GitHub plugin's own program: GitHub's MCP server (github/github-mcp-server, MIT), a pinned release checked
# against its SHA-256, into sys/runtime/github-mcp-server. Found on 8 Oct 2026: nothing installed it — a fresh
# installation had the plugin broken («cannot list tools»). install.sh runs it; run it by hand to repair.
#
#   bash sys/core/script/sys_github_mcp_install.sh            # install or repair (nothing done when already right)
#
# The assets of the other systems (the ports' installers): github-mcp-server_Darwin_arm64.tar.gz
# 7e6c5aec43f26b82d3580e77a4ee26872bcd34b48c9a08d0eaef48b5d0563904, github-mcp-server_Windows_x86_64.zip
# c08872e69f700d4219e7b4ab9607d56d7993171519ee32b62fccb8fba0cab673 (the release's checksums.txt).
set -euo pipefail
VERSION="1.12.2"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DIR="$ROOT/sys/runtime/github-mcp-server"
case "$(uname -m)" in
  x86_64) ASSET="github-mcp-server_Linux_x86_64.tar.gz"; SHA="95843162759da2c31dde082dd145be35db82164594796c294414b69790c2290e" ;;
  aarch64|arm64) ASSET="github-mcp-server_Linux_arm64.tar.gz"; SHA="2b30f9fcc061b57456cbe38ddc0f13c88863bad49557508a9196f2d1c4cb17a5" ;;
  *) echo "github-mcp-server: no release for $(uname -m)"; exit 1 ;;
esac
if [ -x "$DIR/github-mcp-server" ] && "$DIR/github-mcp-server" --version 2>/dev/null | grep -q "Version: $VERSION$"; then
  echo "github-mcp-server $VERSION already installed"; exit 0
fi
mkdir -p "$DIR"
TMP="$(mktemp -d)"; trap 'rm -r -- "$TMP"' EXIT
curl -fsSL -o "$TMP/$ASSET" "https://github.com/github/github-mcp-server/releases/download/v$VERSION/$ASSET"
echo "$SHA  $TMP/$ASSET" | sha256sum -c --quiet - || { echo "github-mcp-server: SHA-256 differs, not installed"; exit 1; }
tar -xzf "$TMP/$ASSET" -C "$TMP" github-mcp-server LICENSE README.md
install -m 0755 "$TMP/github-mcp-server" "$DIR/github-mcp-server"
install -m 0644 "$TMP/LICENSE" "$TMP/README.md" "$DIR/"
"$DIR/github-mcp-server" --version | grep "Version"
