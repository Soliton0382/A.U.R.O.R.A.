# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Mount the NAS folders Aurora uses — the backup's (AURORA_BACKUP_DIR = smb://host/share/folder, read and write) and
the astrophotographer's frames (AURORA_ASTRO_FRAMES_DIR = smb://…, read only: Aurora never touches a light) and the
folder the certificates are copied to (AURORA_CERTS_COPY_DIR = smb://…, read and write: a media server's, often with a
NAS user of its own, AURORA_CERTS_NAS_USER, else the backup's) — run as root by aurora-mount. The others with the same
NAS user (AURORA_NAS_USER).

    systemctl start aurora-mount.service        # what the backup plugin's Save does (polkit: aurora units only)

The owner's consent to root is the one `sudo aurora-root install systemd` that installed this unit: after that
Saving the plugin is enough. What root does, and nothing else:
  - the address and the share are checked strictly (an IPv4 or a host name; letters, digits, . _ - $ /): nothing can
    be injected into /etc/fstab;
  - the NAS user and password go to /etc/aurora/nas.cred (root, 0600), never into fstab;
  - /mnt/aurora-nas (and /mnt/aurora-astro, /mnt/aurora-certs) is made; with AURORA_NAS_FSTAB one line each, marked "# aurora-nas"
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
CERTS = Path("/mnt/aurora-certs")                  # the certificates' copy (net_certs.copy), its own user if set
CERTS_MARK = "# aurora-certs"
CERTS_CRED = Path("/etc/aurora/certs.cred")
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
               ro: bool = False, cred: Path = CRED) -> str:
    opts = (("ro," if ro else "") + f"credentials={cred},uid={uid},gid={gid},file_mode=0600,dir_mode=0700,iocharset=utf8,"
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


def _dirfd(path: Path) -> int:
    """A folder of the services opened by root through no symbolic link at all, from / down (audit, 9 Nov: a link
    planted in sys/status/backup made root write and chown a file of its own code). The caller closes it."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(os.path.abspath(path)).parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except OSError:
        os.close(fd)
        raise


def taken(status: Path) -> dict:
    """The passwords the API handed over for this mount, read once and removed (never through a link)."""
    try:
        d = _dirfd(status)
    except OSError:
        return {}
    try:
        fd = os.open("nas_pass.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=d)
        with os.fdopen(fd, "rb") as h:
            out = json.loads(h.read(65536) or b"{}")
        os.unlink("nas_pass.json", dir_fd=d)
        return out if isinstance(out, dict) else {}
    except (OSError, ValueError):
        return {}
    finally:
        os.close(d)


def mount_one(cfg, url: str, mount: Path, mark: str, ro: bool, user, cred_file: Path = CRED,
              login: tuple[str, str] = ("AURORA_NAS_USER", "AURORA_NAS_PASSWORD"), handed: dict | None = None) -> dict:
    """One share mounted on `mount` for the service user; the folder checked as that user (written to, or listed).
    `login`: the settings of its NAS user and password, kept in `cred_file`."""
    host, share, sub = parse(url)
    from aurora import sys_backup                   # C125: a NAS asleep said as such, not "File exists"
    if not sys_backup.nas_reachable(url):
        raise RuntimeError(f"the NAS {host} does not answer (off or asleep): mount it again when it is on")
    # 🔐 a password sealed in the .env (N69): given once by the API when it changes, else the credentials kept here
    password = (handed or {}).get(login[1]) or str(cfg[login[1]] or "")
    if not password and cfg.locked and cred_file.is_file():
        cred = cred_file.read_text()
        if f"username={cfg[login[0]]}\n" not in cred:
            raise ValueError(f"{login[0]} changed but its password is sealed: save the password again")
    else:
        cred = credentials(str(cfg[login[0]] or ""), password)
    line = fstab_line(host, share, user.pw_uid, user.pw_gid, mount, mark, ro, cred_file)
    dest = mount / sub if sub else mount
    try:
        same = cred_file.read_text() == cred and line in FSTAB.read_text().splitlines() and sys_backup.mounted(mount)
    except OSError:
        same = False
    if same and cfg["AURORA_NAS_FSTAB"]:            # already so: never pulled away from a backup that is running
        check(dest, ro, user)
        return {"ok": True, "dest": str(dest), "fstab": True, "share": f"//{host}/{share}", "unchanged": True}
    cred_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(cred_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
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


def admin_name(cfg) -> str:
    """The admin's name, read from the users' store without ever writing it: this runs as root on a file the service
    owns (opened read only and «immutable»: no journal replayed, nothing created). "" when there is none."""
    import sqlite3
    from urllib.parse import quote
    f = cfg.path("AURORA_STATUS_DIR") / "users.db"
    if f.is_symlink() or not f.is_file():
        return ""
    try:
        con = sqlite3.connect(f"file:{quote(str(f))}?mode=ro&immutable=1", uri=True, timeout=5)
        try:
            r = con.execute("SELECT name FROM users WHERE role='admin' ORDER BY created LIMIT 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return ""
    name = str(r[0]) if r else ""
    return name if re.fullmatch(r"[\w.-]{1,40}", name) and name not in (".", "..") else ""


def astro_url(cfg) -> str:
    """The NAS frames folder: the machine's AURORA_ASTRO_FRAMES_DIR, else the admin's own (usr/<admin>/.env). Never
    another person's (C595: every person's smb://… was looked at and the first one mounted — by root, with the
    house's NAS login: a user chose which share of which server that login was sent to)."""
    from aurora import sys_user_config as U
    urls = [str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip()]
    admin = admin_name(cfg)
    if admin:
        try:
            urls.append(str(U._own(cfg, admin).get("AURORA_ASTRO_FRAMES_DIR", "")).strip())
        except (OSError, ValueError):
            pass
    return next((u for u in urls if u.startswith("smb://")), "")


def certs_login(cfg) -> tuple[str, str]:
    """The certificates' share: its own NAS user when one is set, else the backup's."""
    if str(cfg["AURORA_CERTS_NAS_USER"] or "").strip():
        return "AURORA_CERTS_NAS_USER", "AURORA_CERTS_NAS_PASSWORD"
    return "AURORA_NAS_USER", "AURORA_NAS_PASSWORD"


def report(out: dict, status: Path, user) -> None:
    print(json.dumps(out), flush=True)                          # in the journal first: never lost again
    try:                                                        # audit, 9 Nov: never through a link, chown on the open file
        d = _dirfd(status.parent)
        try:
            tmp = f".{status.name}.tmp"
            try:
                os.unlink(tmp, dir_fd=d)
            except FileNotFoundError:
                pass
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=d)
            with os.fdopen(fd, "w") as h:
                h.write(json.dumps(out))
                os.fchown(h.fileno(), user.pw_uid, user.pw_gid)
            os.rename(tmp, status.name, src_dir_fd=d, dst_dir_fd=d)   # a link at the name is replaced, not followed
        finally:
            os.close(d)
    except OSError as e:
        print(f"status not written ({e}): the card cannot show it", file=sys.stderr)


def main() -> int:
    from aurora import sys_config
    cfg = sys_config.get()
    # C592 (audit F11): the folder as the setting writes it under the installation, not resolved — cfg.path() follows
    # a link put at the status folder, and _dirfd then walked the place it points to as if it were Aurora's
    status = cfg.root / str(cfg["AURORA_STATUS_DIR"]) / "backup"
    try:                                                        # made inside its parent opened through no link
        d = _dirfd(status.parent)
        try:
            os.mkdir(status.name, 0o2770, dir_fd=d)
        except FileExistsError:
            pass
        finally:
            os.close(d)
    except OSError as e:
        print(f"status folder: {e}", file=sys.stderr)
    user = pwd.getpwnam(sys_config.service_user(cfg))
    astro = astro_url(cfg)
    jobs = [("AURORA_BACKUP_DIR", MOUNT, MARK, False, "nas.json")]
    if astro:                                                   # the frames on the NAS too (read only)
        jobs.append(("AURORA_ASTRO_FRAMES_DIR", ASTRO, ASTRO_MARK, True, "astro.json"))
    if str(cfg["AURORA_CERTS_COPY_DIR"] or "").strip().startswith("smb://"):   # the certificates' copy (read and write)
        jobs.append(("AURORA_CERTS_COPY_DIR", CERTS, CERTS_MARK, False, "certs.json"))
    ok, handed = True, taken(status)
    for key, mount, mark, ro, name in jobs:
        out = {"at": time.time(), "ok": False, "mount": str(mount)}
        try:
            if os.geteuid() != 0:
                raise PermissionError("run as root (systemctl start aurora-mount.service)")
            url = astro if key == "AURORA_ASTRO_FRAMES_DIR" else str(cfg[key] or "").strip()
            if not url.startswith("smb://"):
                raise ValueError(f"{key} is not smb://…: nothing to mount")
            if key == "AURORA_CERTS_COPY_DIR":
                out.update(mount_one(cfg, url, mount, mark, ro, user, CERTS_CRED, certs_login(cfg), handed))
            else:
                out.update(mount_one(cfg, url, mount, mark, ro, user, handed=handed))
        except Exception as e:                              # said in the card, never silent
            out["error"] = f"{type(e).__name__}: {e}"[:400]
        ok = ok and (out["ok"] or (key == "AURORA_BACKUP_DIR" and len(jobs) > 1 and "nothing to mount" in out.get("error", "")))
        report(out, status / name, user)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
