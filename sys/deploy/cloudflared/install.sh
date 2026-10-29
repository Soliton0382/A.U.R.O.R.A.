#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# Aurora reachable everywhere through Cloudflare One (WARP private network, roadmap 56) — run ONCE, with sudo:
# installs cloudflared from Cloudflare's own repository and the service aurora-tunnel (it runs as Aurora's user and
# reads the tunnel's token from a 0600 file). Nothing to paste here: the cloudflare plugin's «Salva» creates the
# tunnel, fetches its token and starts the service by itself (polkit lets Aurora start and stop aurora-* units).
#   sudo bash sys/deploy/cloudflared/install.sh            install
#   sudo bash sys/deploy/cloudflared/install.sh status     the service and its last lines
#   sudo bash sys/deploy/cloudflared/install.sh remove     stop and remove the service (cloudflared stays)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# the services' account (U6: sys_service_account.py passes «aurora»), else the owner of Aurora's folder
USER_NAME="${SVC_ACCOUNT:-$(stat -c %U "$ROOT")}"
UNIT=/etc/systemd/system/aurora-tunnel.service

case "${1:-install}" in
status) systemctl --no-pager status aurora-tunnel || true; exit 0 ;;
remove) systemctl disable --now aurora-tunnel 2>/dev/null || true; unlink "$UNIT" 2>/dev/null || true
        systemctl daemon-reload; echo "aurora-tunnel removed"; exit 0 ;;
install) ;;
*) echo "usage: $0 [install|status|remove]"; exit 2 ;;
esac

# Cloudflare's current signing key (cloudflare-public-v2): the list of a first version of this script is replaced
install -m 0755 -d /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg -o /usr/share/keyrings/cloudflare-public-v2.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  > /etc/apt/sources.list.d/cloudflared.list
if ! command -v cloudflared >/dev/null; then
  echo "== installing cloudflared"
  apt-get update -qq && apt-get install -y -qq cloudflared
fi
cloudflared --version

STATUS="$(sudo -u "$USER_NAME" "$ROOT/.venv/bin/python" -c "import sys; sys.path.insert(0, '$ROOT/sys/core'); \
from aurora import sys_config; print(sys_config.get().path('AURORA_STATUS_DIR'))" 2>/dev/null | tail -1)"
[ -n "$STATUS" ] || STATUS="$ROOT/sys/status"
TOKEN="$STATUS/cloudflare/tunnel.token"
install -d -m 0700 -o "$USER_NAME" "$STATUS/cloudflare"

cat > "$UNIT" <<UNIT_EOF
# Installed by sys/deploy/cloudflared/install.sh — the token is written by the cloudflare plugin's «Salva»
[Unit]
Description=Aurora — Cloudflare tunnel (WARP private network, no port opened)
After=network-online.target
Wants=network-online.target
ConditionPathExists=$TOKEN

[Service]
Type=simple
User=$USER_NAME
ExecStart=$(command -v cloudflared) tunnel --no-autoupdate run --token-file $TOKEN
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes
CapabilityBoundingSet=
RestrictSUIDSGID=yes
LockPersonality=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
# the tunnel's token never written to a swap file on the disk, which may be plain (C462)
MemorySwapMax=0
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK

[Install]
WantedBy=multi-user.target
UNIT_EOF
systemctl daemon-reload
systemctl enable aurora-tunnel >/dev/null 2>&1
if systemctl is-active --quiet cloudflared 2>/dev/null; then
  echo "note: a 'cloudflared' service from a manual install is running too (sudo cloudflared service uninstall)"
fi
if [ -s "$TOKEN" ]; then systemctl restart aurora-tunnel && echo "✅ aurora-tunnel started"
else echo "✅ installed. Now in Aurora: Plugins → cloudflare → account ID and API token → Salva: the rest is automatic."; fi
