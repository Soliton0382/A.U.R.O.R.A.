# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Mount the NAS folder of the backup (AURORA_BACKUP_DIR = smb://host/share/folder) — run as root by aurora-mount.

    systemctl start aurora-mount.service        # what the backup plugin's Save does (polkit: aurora units only)

The owner's consent to root is the one `sudo bash sys/deploy/systemd/install.sh` that installed this unit: after that
Saving the plugin is enough. What root does, and nothing else:
  - the address and the share are checked strictly (an IPv4 or a host name; letters, digits, . _ - $ /): nothing can
    be injected into /etc/fstab;
  - the NAS user and password go to /etc/aurora/nas.cred (root, 0600), never into fstab;
  - /mnt/aurora-nas is made; with AURORA_NAS_FSTAB one line, marked "# aurora-nas", is added to /etc/fstab or
    replaces the previous one (a copy /etc/fstab.aurora-<time> is kept first), with nofail and automount: a NAS
    switched off never stops the computer from starting;
  - the share is mounted for the service user (uid/gid), files 0600 and folders 0700.
The result goes to <AURORA_STATUS_DIR>/backup/nas.json for the plugin card and the Status page.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MOUNT = Path("/mnt/aurora-nas")
CRED = Path("/etc/aurora/nas.cred")
FSTAB = Path("/etc/fstab")
MARK = "# aurora-nas"
IPV4 = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$")
NAME = re.compile(r"^(?=.*[a-zA-Z])[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")   # a host name has a letter
PART = re.compile(r"^[A-Za-z0-9._$-]{1,80}$")


def parse(url: str) -> tuple[str, str, str]:
    """smb://host/share/sub/folder → (host, share, "sub/folder"); ValueError for anything else."""
    m = re.fullmatch(r"smb://([^/\s]+)/([^/\s]+)(/[^\s]*)?", url.strip())
    if not m:
        raise ValueError("expected smb://address/share/folder")
    host, share, rest = m.group(1), m.group(2), (m.group(3) or "").strip("/")
    if not (IPV4.match(host) or NAME.match(host)):
        raise ValueError(f"not an address or a host name: {host!r}")
    if not PART.match(share):
        raise ValueError(f"not a share name: {share!r}")
    parts = [p for p in rest.split("/") if p]
    if any(not PART.match(p) or p in (".", "..") for p in parts):
        raise ValueError(f"not a folder path: {rest!r}")
    return host, share, "/".join(parts)


def fstab_line(host: str, share: str, uid: int, gid: int) -> str:
    opts = (f"credentials={CRED},uid={uid},gid={gid},file_mode=0600,dir_mode=0700,iocharset=utf8,noserverino,"
            "_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30,x-systemd.idle-timeout=0")
    return f"//{host}/{share} {MOUNT} cifs {opts} 0 0 {MARK}"


def updated_fstab(text: str, line: str | None) -> str:
    """fstab with our one line put in place of the previous one (or removed when `line` is None)."""
    kept = [l for l in text.splitlines() if not l.rstrip().endswith(MARK)]
    if line:
        kept.append(line)
    return "\n".join(kept) + "\n"


def credentials(user: str, password: str) -> str:
    if "\n" in user or "\n" in password or not user:
        raise ValueError("the NAS user is missing, or user/password contain a line break")
    return f"username={user}\npassword={password}\n"


def main() -> int:
    from aurora import sys_config
    cfg = sys_config.get()
    status = cfg.path("AURORA_STATUS_DIR") / "backup" / "nas.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    user = pwd.getpwnam(sys_config.service_user(cfg))
    out = {"at": time.time(), "ok": False, "mount": str(MOUNT)}
    try:
        if os.geteuid() != 0:
            raise PermissionError("run as root (systemctl start aurora-mount.service)")
        url = str(cfg["AURORA_BACKUP_DIR"] or "")
        if not url.startswith("smb://"):
            raise ValueError("AURORA_BACKUP_DIR is not smb://…: nothing to mount")
        host, share, sub = parse(url)
        CRED.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(CRED, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(credentials(str(cfg["AURORA_NAS_USER"] or ""), str(cfg["AURORA_NAS_PASSWORD"] or "")))
        MOUNT.mkdir(parents=True, exist_ok=True)
        line = fstab_line(host, share, user.pw_uid, user.pw_gid)
        if cfg["AURORA_NAS_FSTAB"]:
            shutil.copy2(FSTAB, FSTAB.with_name(f"fstab.aurora-{time.strftime('%Y%m%d-%H%M%S')}"))
            new = updated_fstab(FSTAB.read_text(), line)
            tmp = FSTAB.with_name("fstab.aurora-tmp")
            tmp.write_text(new)
            os.chmod(tmp, 0o644)
            os.replace(tmp, FSTAB)
            subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=60)
        # systemd mounts it, in the namespace of the whole system: a mount made by this unit itself would stay in the
        # unit's private namespace and vanish with it (C90)
        unit = subprocess.run(["systemd-escape", "-p", "--suffix=mount", str(MOUNT)], capture_output=True, text=True,
                              check=True, timeout=30).stdout.strip()
        if cfg["AURORA_NAS_FSTAB"]:
            for u in (unit.replace(".mount", ".automount"), unit):
                subprocess.run(["systemctl", "stop", u], capture_output=True, timeout=60)
            r = subprocess.run(["systemctl", "start", unit], capture_output=True, text=True, timeout=120)
            subprocess.run(["systemctl", "start", unit.replace(".mount", ".automount")], capture_output=True, timeout=60)
        else:
            subprocess.run(["systemd-umount", str(MOUNT)], capture_output=True, timeout=60)
            opts = ",".join(o for o in line.split()[3].split(",") if not o.startswith(("x-systemd", "_netdev", "nofail")))
            r = subprocess.run(["systemd-mount", "-t", "cifs", "-o", opts, f"//{host}/{share}", str(MOUNT)],
                               capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            log = subprocess.run(["journalctl", "-u", unit, "-n", "5", "--no-pager"], capture_output=True, text=True).stdout
            raise RuntimeError(f"mount failed: {(r.stderr or r.stdout).strip()[-200:]} {log.strip()[-300:]}")
        dest = MOUNT / sub if sub else MOUNT
        dest.mkdir(parents=True, exist_ok=True)                  # owned by the service user: the mount's uid/gid
        probe = dest / ".aurora-write-test"
        subprocess.run(["runuser", "-u", user.pw_name, "--", "touch", str(probe)], check=True, timeout=30)
        probe.unlink()
        out.update(ok=True, dest=str(dest), fstab=bool(cfg["AURORA_NAS_FSTAB"]), share=f"//{host}/{share}")
    except Exception as e:                              # said in the card, never silent
        out["error"] = f"{type(e).__name__}: {e}"[:400]
    print(json.dumps(out), flush=True)                          # in the journal first: never lost again
    try:
        status.write_text(json.dumps(out))
        os.chown(status, user.pw_uid, user.pw_gid)
    except OSError as e:
        print(f"status not written ({e}): the card cannot show it", file=sys.stderr)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
