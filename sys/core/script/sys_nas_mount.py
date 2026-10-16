# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Mount the NAS folders Aurora uses — the backup's (AURORA_BACKUP_DIR = smb://host/share/folder, read and write) and
the astrophotographer's frames (AURORA_ASTRO_FRAMES_DIR = smb://…, read only: Aurora never touches a light) — run as
root by aurora-mount. Both with the same NAS user (AURORA_NAS_USER).

    systemctl start aurora-mount.service        # what the backup plugin's Save does (polkit: aurora units only)

The owner's consent to root is the one `sudo bash sys/deploy/systemd/install.sh` that installed this unit: after that
Saving the plugin is enough. What root does, and nothing else:
  - the address and the share are checked strictly (an IPv4 or a host name; letters, digits, . _ - $ /): nothing can
    be injected into /etc/fstab;
  - the NAS user and password go to /etc/aurora/nas.cred (root, 0600), never into fstab;
  - /mnt/aurora-nas (and /mnt/aurora-astro) is made; with AURORA_NAS_FSTAB one line each, marked "# aurora-nas"
    ("# aurora-astro"), is added to /etc/fstab or
    replaces the previous one (a copy /etc/fstab.aurora-<time> is kept first), with nofail and automount: a NAS
    switched off never stops the computer from starting;
  - the share is mounted for the service user (uid/gid), files 0600 and folders 0700.
The result goes to <AURORA_STATUS_DIR>/backup/nas.json (astro.json for the frames) for the cards and the Status page.
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
ASTRO = Path("/mnt/aurora-astro")                  # the frames' share, read only (ROADMAP N29)
ASTRO_MARK = "# aurora-astro"
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


def fstab_line(host: str, share: str, uid: int, gid: int, mount: Path = MOUNT, mark: str = MARK,
               ro: bool = False) -> str:
    opts = (("ro," if ro else "") + f"credentials={CRED},uid={uid},gid={gid},file_mode=0600,dir_mode=0700,iocharset=utf8,"
            "noserverino,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30,x-systemd.idle-timeout=0")
    return f"//{host}/{share} {mount} cifs {opts} 0 0 {mark}"


def updated_fstab(text: str, line: str | None, mark: str = MARK) -> str:
    """fstab with our one line put in place of the previous one (or removed when `line` is None)."""
    kept = [l for l in text.splitlines() if not l.rstrip().endswith(mark)]
    if line:
        kept.append(line)
    return "\n".join(kept) + "\n"


def credentials(user: str, password: str) -> str:
    if "\n" in user or "\n" in password or not user:
        raise ValueError("the NAS user is missing, or user/password contain a line break")
    return f"username={user}\npassword={password}\n"


def mount_one(cfg, url: str, mount: Path, mark: str, ro: bool, user) -> dict:
    """One share mounted on `mount` for the service user; the folder checked as that user (written to, or listed)."""
    host, share, sub = parse(url)
    from aurora import sys_backup                   # C125: a NAS asleep said as such, not "File exists"
    if not sys_backup.nas_reachable(url):
        raise RuntimeError(f"the NAS {host} does not answer (off or asleep): mount it again when it is on")
    cred = credentials(str(cfg["AURORA_NAS_USER"] or ""), str(cfg["AURORA_NAS_PASSWORD"] or ""))
    line = fstab_line(host, share, user.pw_uid, user.pw_gid, mount, mark, ro)
    dest = mount / sub if sub else mount
    try:
        same = CRED.read_text() == cred and line in FSTAB.read_text().splitlines() and sys_backup.mounted(mount)
    except OSError:
        same = False
    if same and cfg["AURORA_NAS_FSTAB"]:            # already so: never pulled away from a backup that is running
        check(dest, ro, user)
        return {"ok": True, "dest": str(dest), "fstab": True, "share": f"//{host}/{share}", "unchanged": True}
    CRED.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(CRED, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(cred)
    mount.mkdir(parents=True, exist_ok=True)
    if cfg["AURORA_NAS_FSTAB"]:
        shutil.copy2(FSTAB, FSTAB.with_name(f"fstab.aurora-{time.strftime('%Y%m%d-%H%M%S')}"))
        new = updated_fstab(FSTAB.read_text(), line, mark)
        tmp = FSTAB.with_name("fstab.aurora-tmp")
        tmp.write_text(new)
        os.chmod(tmp, 0o644)
        os.replace(tmp, FSTAB)
        subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=60)
    # systemd mounts it, in the namespace of the whole system: a mount made by this unit itself would stay in the
    # unit's private namespace and vanish with it (C90)
    unit = subprocess.run(["systemd-escape", "-p", "--suffix=mount", str(mount)], capture_output=True, text=True,
                          check=True, timeout=30).stdout.strip()
    if cfg["AURORA_NAS_FSTAB"]:
        for u in (unit.replace(".mount", ".automount"), unit):
            subprocess.run(["systemctl", "stop", u], capture_output=True, timeout=60)
        r = subprocess.run(["systemctl", "start", unit], capture_output=True, text=True, timeout=120)
        subprocess.run(["systemctl", "start", unit.replace(".mount", ".automount")], capture_output=True, timeout=60)
    else:
        subprocess.run(["systemd-umount", str(mount)], capture_output=True, timeout=60)
        opts = ",".join(o for o in line.split()[3].split(",") if not o.startswith(("x-systemd", "_netdev", "nofail")))
        r = subprocess.run(["systemd-mount", "-t", "cifs", "-o", opts, f"//{host}/{share}", str(mount)],
                           capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        log = subprocess.run(["journalctl", "-u", unit, "-n", "5", "--no-pager"], capture_output=True, text=True).stdout
        raise RuntimeError(f"mount failed: {(r.stderr or r.stdout).strip()[-200:]} {log.strip()[-300:]}")
    check(dest, ro, user)
    return {"ok": True, "dest": str(dest), "fstab": bool(cfg["AURORA_NAS_FSTAB"]), "share": f"//{host}/{share}"}


def check(dest: Path, ro: bool, user) -> None:
    """The folder works for the service user: listed (the frames: only looked at, never written) or written to."""
    if ro:
        subprocess.run(["runuser", "-u", user.pw_name, "--", "ls", str(dest)], check=True, timeout=30,
                       capture_output=True)
        return
    dest.mkdir(parents=True, exist_ok=True)                     # owned by the service user: the mount's uid/gid
    probe = dest / ".aurora-write-test"
    subprocess.run(["runuser", "-u", user.pw_name, "--", "touch", str(probe)], check=True, timeout=30)
    probe.unlink()


def astro_url(cfg) -> str:
    """The NAS frames folder: AURORA_ASTRO_FRAMES_DIR is each person's own (usr/<name>/.env), one share per machine —
    the first person's smb://… is mounted."""
    from aurora import sys_user_config as U, sys_users_layout as L
    urls = [str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip()]
    try:
        homes = sorted(d.name for d in L.usr(cfg).iterdir() if (d / U.ENV).is_file())
    except OSError:
        homes = []
    for name in homes:
        try:
            urls.append(str(U._own(cfg, name).get("AURORA_ASTRO_FRAMES_DIR", "")).strip())
        except (OSError, ValueError):
            continue
    return next((u for u in urls if u.startswith("smb://")), "")


def report(out: dict, status: Path, user) -> None:
    print(json.dumps(out), flush=True)                          # in the journal first: never lost again
    try:
        status.write_text(json.dumps(out))
        os.chown(status, user.pw_uid, user.pw_gid)
    except OSError as e:
        print(f"status not written ({e}): the card cannot show it", file=sys.stderr)


def main() -> int:
    from aurora import sys_config
    cfg = sys_config.get()
    status = cfg.path("AURORA_STATUS_DIR") / "backup"
    status.mkdir(parents=True, exist_ok=True)
    user = pwd.getpwnam(sys_config.service_user(cfg))
    astro = astro_url(cfg)
    jobs = [("AURORA_BACKUP_DIR", MOUNT, MARK, False, "nas.json")]
    if astro:                                                   # the frames on the NAS too (read only)
        jobs.append(("AURORA_ASTRO_FRAMES_DIR", ASTRO, ASTRO_MARK, True, "astro.json"))
    ok = True
    for key, mount, mark, ro, name in jobs:
        out = {"at": time.time(), "ok": False, "mount": str(mount)}
        try:
            if os.geteuid() != 0:
                raise PermissionError("run as root (systemctl start aurora-mount.service)")
            url = astro if key == "AURORA_ASTRO_FRAMES_DIR" else str(cfg[key] or "").strip()
            if not url.startswith("smb://"):
                raise ValueError(f"{key} is not smb://…: nothing to mount")
            out.update(mount_one(cfg, url, mount, mark, ro, user))
        except Exception as e:                              # said in the card, never silent
            out["error"] = f"{type(e).__name__}: {e}"[:400]
        ok = ok and (out["ok"] or (key == "AURORA_BACKUP_DIR" and len(jobs) > 1 and "nothing to mount" in out.get("error", "")))
        report(out, status / name, user)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
