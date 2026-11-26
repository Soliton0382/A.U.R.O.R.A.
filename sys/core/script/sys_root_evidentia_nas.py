# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's sources on the NAS (owner, 27 Nov: «la cartella NAS per evidentia… utente e password sono le medesime
per il backup»; R22) — root's, from `aurora-root install evidentia --nas smb://host/share/folder`.

Only that folder of the share, never the whole share; read only; for the account evidentia and its group (the owner is
in it), files 0440 and folders 0550 — Aurora's account is not in the group and does not read it. The NAS user and
password are the backup's: /etc/aurora/nas.cred (written by aurora-mount) copied to /etc/aurora/evidentia-nas.cred
(root, 0600), never into fstab. One fstab line marked «# evidentia-nas» (a copy of fstab kept first), with nofail and
automount: a NAS asleep never stops the computer from starting nor Evidentia from running. The address stays in
/etc/aurora/evidentia.env (EVD_NAS_SOURCES), never in the code."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

MOUNT = Path("/mnt/evidentia-nas")
CRED = Path("/etc/aurora/evidentia-nas.cred")
BACKUP_NAS_CRED = Path("/etc/aurora/nas.cred")
FSTAB = Path("/etc/fstab")
MARK = "# evidentia-nas"


def parse(url: str) -> tuple[str, str, str]:
    """smb://host/share/folder → (host, share, folder), checked as aurora-mount checks its own (nothing reaches fstab
    that is not an address, a share and a folder of plain names); the folder is required."""
    from sys_nas_mount import parse as p
    host, share, sub = p(url)
    if not sub:
        raise ValueError("Evidentia mounts a folder of the share, not the whole share: smb://address/share/folder")
    return host, share, sub


def fstab_line(host: str, share: str, sub: str, uid: int, gid: int) -> str:
    opts = (f"ro,credentials={CRED},uid={uid},gid={gid},file_mode=0440,dir_mode=0550,iocharset=utf8,noserverino,"
            "_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30,x-systemd.idle-timeout=0")
    return f"//{host}/{share}/{sub} {MOUNT} cifs {opts} 0 0 {MARK}"


def _fstab(line: str | None) -> None:
    from sys_nas_mount import updated_fstab
    text = FSTAB.read_text()
    new = updated_fstab(text, line, MARK)
    if new.strip() == text.strip():                    # already so: fstab not rewritten
        return
    shutil.copy2(FSTAB, FSTAB.with_name(f"fstab.evidentia-{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = FSTAB.with_name("fstab.evidentia-tmp")
    tmp.write_text(new)
    os.chmod(tmp, 0o644)
    os.replace(tmp, FSTAB)


def _units(run) -> tuple[str, str]:
    m = run(["systemd-escape", "-p", "--suffix=mount", str(MOUNT)], capture_output=True, text=True, check=True,
            timeout=30).stdout.strip()
    return m, m.replace(".mount", ".automount")


def mount(url: str, uid: int, gid: int, user: str, run=subprocess.run) -> dict:
    host, share, sub = parse(url)
    if not BACKUP_NAS_CRED.is_file():
        raise SystemExit("evidentia: the NAS's user and password are the backup's (/etc/aurora/nas.cred): set the NAS in "
                         "the backup plugin first (it mounts it), then install Evidentia again")
    fd = os.open(CRED, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(BACKUP_NAS_CRED.read_bytes())
    os.chmod(CRED, 0o600)
    MOUNT.mkdir(mode=0o755, exist_ok=True)
    _fstab(fstab_line(host, share, sub, uid, gid))
    run(["systemctl", "daemon-reload"], check=True, timeout=60)
    mnt, auto = _units(run)
    for u in (auto, mnt):
        run(["systemctl", "stop", u], capture_output=True, timeout=60)
    r = run(["systemctl", "start", mnt], capture_output=True, text=True, timeout=120)
    run(["systemctl", "start", auto], capture_output=True, timeout=60)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout or "").strip()[-300:], "mount": str(MOUNT)}
    seen = run(["runuser", "-u", user, "--", "ls", str(MOUNT)], capture_output=True, text=True, timeout=60)
    return {"ok": seen.returncode == 0, "mount": str(MOUNT), "folders": len((seen.stdout or "").split("\n")) - 1,
            "error": (seen.stderr or "").strip()[-200:]}


def unmount(run=subprocess.run) -> list[str]:
    """The line, the mount and the credentials gone; the NAS's files untouched (they are only read)."""
    gone = []
    if FSTAB.is_file() and any(l.rstrip().endswith(MARK) for l in FSTAB.read_text().splitlines()):
        mnt, auto = _units(run)
        for u in (auto, mnt):
            run(["systemctl", "stop", u], capture_output=True, timeout=60)
        _fstab(None)
        run(["systemctl", "daemon-reload"], check=False, timeout=60)
        gone.append(f"{FSTAB} ({MARK})")
    if CRED.is_file() and not CRED.is_symlink():
        CRED.unlink()
        gone.append(str(CRED))
    return gone


# ---- N168: each user's own NAS folder (owner, 27 Nov: «è importante che ognuno possa collegare il percorso che vuole»)
# A user asks from the WebUI (Evidentia → Archivi → «Collega una tua cartella del NAS»): Aurora writes one request
# into her status folder (evidentia/nas-<user>.json, 0600: the address, the NAS user, the password) and starts
# aurora-evidentia-nas (root). Root reads it as data, strictly, once (the file goes as soon as it is read), and mounts
# that folder read only at /mnt/evidentia-nas-<user> for Evidentia's account — only that user's requests see it
# (evidentia/sources). The password goes to /etc/aurora/evidentia-nas-<user>.cred (root, 0600), never into fstab.
import json as _json
import re as _re
import stat as _stat

USER_NAME = _re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
RESULTS = Path("/var/lib/evidentia-api")                 # nas-<user>.json: what happened, readable by Aurora's account


def user_mount(user: str) -> Path:
    return Path(f"/mnt/evidentia-nas-{user}")


def user_cred(user: str) -> Path:
    return Path(f"/etc/aurora/evidentia-nas-{user}.cred")


def user_line(host: str, share: str, sub: str, uid: int, gid: int, user: str) -> str:
    return fstab_line(host, share, sub, uid, gid).replace(str(MOUNT), str(user_mount(user)), 1) \
        .replace(str(CRED), str(user_cred(user)), 1).replace(MARK, f"{MARK}-{user}")


def read_requests(folder: Path, owner_uid: int, max_age: float = 600) -> list[dict]:
    """Every request in Aurora's folder, checked and removed: a regular file of her own, not a link, ≤ 4 KB, not
    writable by others, ≤ 10 minutes old; the user, the address, the NAS user and the password as plain text."""
    out = []
    try:
        names = sorted(n for n in os.listdir(folder) if _re.fullmatch(r"nas-[a-z0-9][a-z0-9_-]{0,31}\.json", n))
    except OSError:
        return out
    for n in names:
        f = folder / n
        try:
            fd = os.open(f, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            continue
        try:
            st = os.fstat(fd)
            ok = _stat.S_ISREG(st.st_mode) and st.st_size <= 4096 and st.st_uid == owner_uid and not st.st_mode & 0o022
            raw = os.read(fd, 4097) if ok else b""
        finally:
            os.close(fd)
            f.unlink(missing_ok=True)                   # once
        try:
            r = _json.loads(raw)
        except ValueError:
            continue
        user = n[4:-5]
        if not isinstance(r.get("at"), (int, float)) or not 0 <= time.time() - r["at"] <= max_age:
            out.append({"user": user, "error": "the request is older than 10 minutes: ask again"})
            continue
        out.append({"user": user, "remove": bool(r.get("remove")), "url": str(r.get("url", "")),
                    "nas_user": str(r.get("nas_user", "")), "password": str(r.get("password", ""))})
    return out


def mount_user(req: dict, uid: int, gid: int, service_user: str, run=subprocess.run) -> dict:
    user = req["user"]
    if not USER_NAME.match(user):
        raise ValueError("a user's name")
    if req.get("remove"):
        return {"ok": True, "removed": unmount_user(user, run)}
    host, share, sub = parse(req["url"])
    from sys_nas_mount import credentials
    cred = credentials(req["nas_user"], req["password"])  # no line break in either: nothing reaches fstab
    fd = os.open(user_cred(user), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(cred)
    user_mount(user).mkdir(mode=0o755, exist_ok=True)
    from sys_nas_mount import updated_fstab
    text = FSTAB.read_text()
    new = updated_fstab(text, user_line(host, share, sub, uid, gid, user), f"{MARK}-{user}")
    if new.strip() != text.strip():
        shutil.copy2(FSTAB, FSTAB.with_name(f"fstab.evidentia-{time.strftime('%Y%m%d-%H%M%S')}"))
        tmp = FSTAB.with_name("fstab.evidentia-tmp")
        tmp.write_text(new)
        os.chmod(tmp, 0o644)
        os.replace(tmp, FSTAB)
    run(["systemctl", "daemon-reload"], check=True, timeout=60)
    m = run(["systemd-escape", "-p", "--suffix=mount", str(user_mount(user))], capture_output=True, text=True,
            check=True, timeout=30).stdout.strip()
    for u in (m.replace(".mount", ".automount"), m):
        run(["systemctl", "stop", u], capture_output=True, timeout=60)
    r = run(["systemctl", "start", m], capture_output=True, text=True, timeout=120)
    run(["systemctl", "start", m.replace(".mount", ".automount")], capture_output=True, timeout=60)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout or "").strip()[-300:]}
    seen = run(["runuser", "-u", service_user, "--", "ls", str(user_mount(user))], capture_output=True, text=True, timeout=60)
    return {"ok": seen.returncode == 0, "folders": max(0, len((seen.stdout or "").split("\n")) - 1),
            "error": (seen.stderr or "").strip()[-200:]}


def unmount_user(user: str, run=subprocess.run) -> list[str]:
    gone, mark = [], f"{MARK}-{user}"
    if FSTAB.is_file() and any(l.rstrip().endswith(mark) for l in FSTAB.read_text().splitlines()):
        m = run(["systemd-escape", "-p", "--suffix=mount", str(user_mount(user))], capture_output=True, text=True,
                check=True, timeout=30).stdout.strip()
        for u in (m.replace(".mount", ".automount"), m):
            run(["systemctl", "stop", u], capture_output=True, timeout=60)
        from sys_nas_mount import updated_fstab
        tmp = FSTAB.with_name("fstab.evidentia-tmp")
        tmp.write_text(updated_fstab(FSTAB.read_text(), None, mark))
        os.chmod(tmp, 0o644)
        os.replace(tmp, FSTAB)
        run(["systemctl", "daemon-reload"], check=False, timeout=60)
        gone.append(mark)
    c = user_cred(user)
    if c.is_file() and not c.is_symlink():
        c.unlink()
        gone.append(str(c))
    return gone


def _result(user: str, out: dict) -> None:
    import grp
    f = RESULTS / f"nas-{user}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(_json.dumps({**out, "at": time.time()}))
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, 0, grp.getgrnam("evidentia-api").gr_gid)
    except KeyError:
        pass
    tmp.replace(f)


def from_request() -> int:
    """aurora-evidentia-nas: every request waiting, each said in /var/lib/evidentia-api/nas-<user>.json."""
    import pwd
    import grp
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from aurora import sys_config
    cfg = sys_config.get()
    folder = cfg.root / str(cfg["AURORA_STATUS_DIR"]) / "evidentia"
    try:
        owner_uid = folder.stat().st_uid
    except OSError:
        return 0
    svc = pwd.getpwnam("evidentia")
    rc = 0
    for req in read_requests(folder, owner_uid):
        try:
            out = {"ok": False, **{k: req[k] for k in ("error",) if k in req}} if "error" in req else \
                mount_user(req, svc.pw_uid, grp.getgrnam("evidentia").gr_gid, "evidentia")
        except (ValueError, OSError, subprocess.SubprocessError) as e:
            out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
        rc = rc or (0 if out.get("ok") else 1)
        _result(req["user"], out)
    return rc


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(from_request() if "--from-request" in _sys.argv else 2)
