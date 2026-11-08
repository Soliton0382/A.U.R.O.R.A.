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
# run by aurora-root only (sys_root.py, 9 Nov): this folder is a copy root checked against the owner's signature
if [ -z "${AURORA_DEPLOY:-}" ]; then
  if [ -x /usr/local/sbin/aurora-root ]; then echo "usa: sudo aurora-root install tunnel"
  else echo "la prima volta, dalla cartella di Aurora: sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup"; fi
  exit 1
fi
ROOT="${INSTALL_ROOT:?}"                              # Aurora's folder (its code run only as the services' account)
# the services' account (U6: sys_service_account.py passes «aurora»), else the owner of Aurora's folder
# C520: the services' own account (U6) when it exists — run by hand without SVC_ACCOUNT, the folder's owner took the
# tunnel and its folder away from the API
if [ -z "${SVC_ACCOUNT:-}" ] && id -u aurora >/dev/null 2>&1; then SVC_ACCOUNT=aurora; fi
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
# the folder is the service account's: a symlink in its place (or above it) is refused, never followed by root
for p in "$STATUS" "$STATUS/cloudflare"; do
  if [ -L "$p" ]; then echo "✗ $p is a symbolic link: refused" >&2; exit 1; fi
done
install -d -m 0700 -o "$USER_NAME" "$STATUS/cloudflare"
# C520: files left by a run on another account given back to this one (-h: a link itself, never what it points to;
# a hard link to someone else's file cannot be made with fs.protected_hardlinks, the default)
find "$STATUS/cloudflare" -maxdepth 1 -type f ! -user "$USER_NAME" -exec chown -h "$USER_NAME" {} +
as_service() { sudo -u "$USER_NAME" -- "$@"; }        # every step on the folder's files: as its owner, not as root
for f in "$TOKEN" "$TOKEN.new" "$TOKEN.cred" "$TOKEN.cred.tmp" "$TOKEN.sha256"; do   # and no link among them at all
  if [ -L "$f" ]; then echo "✗ $f is a symbolic link: refused (remove it and run again)" >&2; exit 1; fi
done

# 🔐 the token sealed (C463, ROADMAP N69 g): a systemd credential bound to this machine (its TPM when it has one), opened by
# systemd for cloudflared alone at each start, in a folder of its own; the file in clear removed, its SHA-256 left for
# Aurora to know the same token again. A new token Aurora fetched (tunnel.token.new) is sealed here the same way.
CRED="$TOKEN.cred"
SOURCE_ARGS="--token-file $TOKEN"
CREDENTIAL=""
SYSTEMD_V="$(systemctl --version | sed -n '1s/^systemd \([0-9]*\).*/\1/p')"
if command -v systemd-creds >/dev/null && [ "${SYSTEMD_V:-0}" -ge 254 ]; then     # %d: the credentials' folder
  NEW="$TOKEN.new"
  if as_service test -s "$NEW"; then PLAIN="$NEW"; elif as_service test -s "$TOKEN"; then PLAIN="$TOKEN"; else PLAIN=""; fi
  if [ -n "$PLAIN" ]; then
    # audit, 9 Nov: root read, wrote, chowned and shredded these paths itself, so a symlink planted by the service
    # account (tunnel.token.sha256 -> /etc/shadow) made root write there. Now: read as the account into root's own
    # folder, sealed there, and every file put back or removed as the account.
    WORK="$(mktemp -d)"
    as_service cat -- "$PLAIN" > "$WORK/plain"
    systemd-creds encrypt --name=tunnel.token "$WORK/plain" "$WORK/cred"
    as_service sh -c 'umask 077; cat > "$1.tmp" && mv -f -- "$1.tmp" "$1"' _ "$CRED" < "$WORK/cred"
    sha256sum "$WORK/plain" | cut -d" " -f1 | as_service sh -c 'umask 077; cat > "$1"' _ "$TOKEN.sha256"
    shred -u "$WORK/plain" "$WORK/cred"
    rmdir "$WORK"
    as_service shred -u -- "$PLAIN"
    if as_service test -e "$TOKEN"; then as_service shred -u -- "$TOKEN"; fi
    echo "🔐 tunnel token sealed: $CRED (the file in clear removed)"
  fi
  if [ -s "$CRED" ]; then
    SOURCE_ARGS="--token-file %d/tunnel.token"
    CREDENTIAL="LoadCredentialEncrypted=tunnel.token:$CRED"
    TOKEN="$CRED"                                  # the unit's condition: the sealed file
  fi
fi

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
$CREDENTIAL
ExecStart=$(command -v cloudflared) tunnel --no-autoupdate run $SOURCE_ARGS
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
