#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora's own firewall on this machine, installed once by the owner:
#   sudo bash sys/deploy/nft/install.sh            (to take it away: sudo bash sys/deploy/nft/install.sh --remove)
# What it puts in the system: /usr/local/sbin/aurora-nft (the only root command Aurora may run), /etc/aurora/aurora.nft
# (its own table), aurora-nft.service (loads the table at boot), aurora-nftd.socket + aurora-nftd@.service (how Aurora's
# hardened services reach it: they cannot use sudo, C194), /etc/sudoers.d/aurora-nft (for the shell, checked with visudo).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
# the services' account (U6: «aurora», sys_service_account.py passes it), else whoever runs sudo
USER_SVC="${SVC_ACCOUNT:-${SUDO_USER:-$(stat -c %U "$HERE/../../..")}}"   # else the owner of Aurora's folder
if [ "${1:-}" = "--remove" ]; then
  systemctl disable --now aurora-nftd.socket 2>/dev/null || true
  systemctl disable --now aurora-nft.service 2>/dev/null || true
  for f in /etc/systemd/system/aurora-nftd.socket /etc/systemd/system/aurora-nftd@.service \
           /etc/systemd/system/aurora-nft.service /usr/local/sbin/aurora-nft /etc/sudoers.d/aurora-nft /etc/aurora/aurora.nft; do
    [ -e "$f" ] && unlink "$f"
  done
  systemctl daemon-reload
  echo "taken away"
  exit 0
fi
command -v nft >/dev/null || apt-get install -y -q nftables
install -m 0755 -o root -g root "$HERE/aurora-nft" /usr/local/sbin/aurora-nft
install -d -m 0755 /etc/aurora
install -m 0644 -o root -g root "$HERE/aurora.nft" /etc/aurora/aurora.nft
# the addresses never blocked, root's own list beside the helper (sys_root_sync.py)
"$HERE/../../../.venv/bin/python" "$HERE/../../core/script/sys_root_sync.py" || echo "  (never-blocked list not written: run sys_root_sync.py)"
install -m 0644 "$HERE/aurora-nft.service" /etc/systemd/system/aurora-nft.service
GROUP_SVC="$(id -gn "$USER_SVC")"
sed "s/@GROUP@/$GROUP_SVC/" "$HERE/aurora-nftd.socket" > /etc/systemd/system/aurora-nftd.socket
chmod 0644 /etc/systemd/system/aurora-nftd.socket
install -m 0644 "$HERE/aurora-nftd@.service" /etc/systemd/system/aurora-nftd@.service
TMP=$(mktemp)
echo "$USER_SVC ALL=(root) NOPASSWD: /usr/local/sbin/aurora-nft" > "$TMP"
visudo -cf "$TMP" >/dev/null && install -m 0440 -o root -g root "$TMP" /etc/sudoers.d/aurora-nft
unlink "$TMP"
systemctl daemon-reload
systemctl enable --now aurora-nft.service
systemctl enable aurora-nftd.socket
# made again, not only enabled: a socket already there keeps its old group (U6, 28 Oct: still the
# owner's after the services moved to their own account, and Aurora could not reach the helper)
systemctl restart aurora-nftd.socket
echo "✅ Aurora's firewall ready (table inet aurora)"
if printf 'list\n' | sudo -u "$USER_SVC" python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect("/run/aurora-nftd.sock"); s.sendall(sys.stdin.buffer.read()); s.shutdown(1); print(s.makefile().read())' | grep -q "#rc 0"; then
  echo "✅ Aurora's services may use it (socket /run/aurora-nftd.sock)"
else
  echo "❌ the socket does not answer: journalctl -u 'aurora-nftd@*'"
fi
sudo -u "$USER_SVC" sudo -n /usr/local/sbin/aurora-nft list >/dev/null && echo "✅ $USER_SVC may use it (sudo -n)"
