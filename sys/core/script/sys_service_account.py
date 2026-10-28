# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's services under an account of their own, «aurora» (ROADMAP U6; owner, 28 Oct: «facciamo U6… l'aggiornamento
dovrà prevedere la migrazione di ambiente già configurato senza che si vedano casini»). Run with sudo, once; again is
harmless (each step checks first). --dry-run says what it would do and does nothing.

Why: the services ran as the owner's own login account, on a desktop one in groups that are root in all but name
(docker, libvirt, sudo), whose home holds the owner's SSH keys and logins (security review, 28 Oct).

What it does:
  1. the group and the account «aurora»: a system account, no login, its home in the installation's state
     (sys/status/home); in the GPU's groups (video, render) and in no other; the owner in the group «aurora»;
  2. the folders above the installation: the account may pass through them (an ACL «x» only: it cannot list them);
  3. the installation: group «aurora», readable and writable by the group, new folders keep the group (setgid);
     the owner stays the files' owner. Left as they are, untouched: any «papers» folder of a user (the owner's
     documents), unless --with-papers (read only for the group);
  4. what the services kept in the owner's home, copied to the account's: Caddy's certificates, the SSH known hosts;
     the firewall's SSH key into the installation's keys (the setting follows);
  5. AURORA_SERVICE_USER=aurora; the units, the polkit rule and the firewall helper written again for it; the
     services restarted.
The Claude CLI's login is not copied: the owner logs in again from ☁️ Accounts (the account's own).
"""
from __future__ import annotations

import grp
import os
import pwd
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ACCOUNT = "aurora"
GPU_GROUPS = ("video", "render")
DRY = "--dry-run" in sys.argv
WITH_PAPERS = "--with-papers" in sys.argv
said: list[str] = []


def step(text: str, fn=None, *args) -> None:
    said.append(text)
    print(("  would: " if DRY else "  ") + text)
    if fn and not DRY:
        fn(*args)


def run(*cmd: str) -> None:
    subprocess.run(list(cmd), check=True)


def owner() -> str:
    return os.environ.get("SUDO_USER") or pwd.getpwuid(ROOT.stat().st_uid).pw_name


def exists_user(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def exists_group(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def account(who: str) -> None:
    home = ROOT / "sys" / "status" / "home"
    if not exists_group(ACCOUNT):
        step(f"group {ACCOUNT}", run, "groupadd", "--system", ACCOUNT)
    if not exists_user(ACCOUNT):
        step(f"account {ACCOUNT} (no login, home {home})", run, "useradd", "--system", "--gid", ACCOUNT, "--home-dir",
             str(home), "--no-create-home", "--shell", "/usr/sbin/nologin", ACCOUNT)
    if not home.is_dir() or DRY:
        step(f"its home {home}", lambda: (home.mkdir(parents=True, exist_ok=True), shutil.chown(home, ACCOUNT, ACCOUNT),
                                          home.chmod(0o750)))
    for g in GPU_GROUPS:
        if exists_group(g) and (DRY or ACCOUNT not in grp.getgrnam(g).gr_mem):
            step(f"{ACCOUNT} in {g} (the GPU)", run, "usermod", "-aG", g, ACCOUNT)
    if DRY or not exists_group(ACCOUNT) or who not in grp.getgrnam(ACCOUNT).gr_mem:
        step(f"{who} in the group {ACCOUNT} (to read and write the installation as before)", run, "usermod", "-aG", ACCOUNT, who)


def traverse() -> None:
    if not shutil.which("setfacl"):
        step("the package acl (setfacl)", run, "apt-get", "install", "-y", "-q", "acl")
    for p in reversed(ROOT.parents):
        if p == Path("/"):
            continue
        if p.stat().st_mode & stat.S_IXOTH:
            continue
        acl = subprocess.run(["getfacl", "-p", str(p)], capture_output=True, text=True).stdout if shutil.which("getfacl") else ""
        if f"user:{ACCOUNT}:" not in acl:
            step(f"{ACCOUNT} may pass through {p} (ACL x: no listing)", run, "setfacl", "-m", f"u:{ACCOUNT}:x", str(p))


def papers(path: Path) -> bool:
    """A user's «papers» folder: the owner's own documents, never changed unless asked."""
    return path.name == "papers" and "usr" in path.parts


def in_papers(path: Path) -> bool:
    """Inside a user's papers folder (the folder itself included)."""
    rel = path.relative_to(ROOT).parts if path.is_relative_to(ROOT) else path.parts
    return "usr" in rel and "papers" in rel[rel.index("usr"):]


# what the services write and keep: their account owns it (they may set its modes); the owner reads and writes it
# through the group. The code (sys/core, the plugins, .venv, docs) stays the owner's
DATA = ("sys/status", "sys/logs", "sys/vault", "sys/sandbox", "sys/https", "sys/runtime", "usr", ".env")


def data_owner() -> None:
    uid = pwd.getpwnam(ACCOUNT).pw_uid if exists_user(ACCOUNT) else -1
    n = 0
    for rel in DATA:
        top = ROOT / rel
        if not top.exists():
            continue
        walk = [(top, [], [])] if top.is_file() else os.walk(top, followlinks=False)
        for here, dirs, files in walk:
            here = Path(here)
            dirs[:] = [d for d in dirs if not papers(here / d)]     # papers: never the account's, even read
            for p in [here, *(here / f for f in files)]:
                if p.is_symlink():
                    continue
                n += 1
                if not DRY:
                    os.lchown(p, uid, -1)
    step(f"the data ({', '.join(DATA)}): {n} files and folders owned by {ACCOUNT}; the code stays the owner's")


def tree() -> None:
    gid = grp.getgrnam(ACCOUNT).gr_gid if exists_group(ACCOUNT) else -1
    n = skipped = 0
    for top, dirs, files in os.walk(ROOT, followlinks=False):
        here = Path(top)
        keep = []
        for d in dirs:
            if papers(here / d) and not WITH_PAPERS:
                skipped += 1
                continue
            keep.append(d)
        dirs[:] = keep
        for name in [None, *files]:
            p = here if name is None else here / name
            if p.is_symlink():
                continue
            n += 1
            if DRY:
                continue
            st = p.lstat()
            os.lchown(p, -1, gid)
            mode = stat.S_IMODE(st.st_mode)
            if in_papers(p):                             # --with-papers: the group may read, nothing else; the
                os.chmod(p, mode | (0o050 if p.is_dir() else 0o040))   # files stay the owner's, none written
                continue
            if p.is_dir():
                os.chmod(p, mode | 0o070 | stat.S_ISGID)
            elif name == ".env":
                os.chmod(p, 0o660)
            else:
                os.chmod(p, mode | 0o060 | (0o010 if mode & 0o100 else 0))
    step(f"the installation: {n} files and folders to the group {ACCOUNT}, read and write for the group"
         + (f"; {skipped} papers folder(s) left as they are" if skipped else ""))
    if WITH_PAPERS:
        step("papers: read only for the group (no file moved or changed)")


def from_home(who: str) -> None:
    src_home = Path(pwd.getpwnam(who).pw_dir)
    dst_home = ROOT / "sys" / "status" / "home"
    # the backup's encryption key too (AURORA_BACKUP_KEY_FILE «~/.config/aurora/backup.key»: «~» is now the account's
    # home — the first migration of the owner's machine left it behind and the backup lost its key, 28 Oct)
    for rel in (".local/share/caddy", ".config/caddy", ".ssh/known_hosts", ".config/aurora/backup.key"):
        s, d = src_home / rel, dst_home / rel
        if s.exists() and not d.exists():
            def copy(s=s, d=d):
                d.parent.mkdir(parents=True, exist_ok=True)
                (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
                subprocess.run(["chown", "-R", f"{ACCOUNT}:{ACCOUNT}", str(dst_home)], check=True)
            step(f"{rel} copied to the account's home", copy)


def settings(who: str) -> None:
    py = ROOT / ".venv" / "bin" / "python"
    sets = [f"AURORA_SERVICE_USER={ACCOUNT}"]
    sys.path.insert(0, str(ROOT / "sys" / "core"))
    try:
        from aurora import sys_config
        cfg = sys_config.load()
        key = str(cfg["AURORA_FIREWALL_SSH_KEY"] or "")
        if key.startswith("~"):                          # the owner's home, not root's (this runs with sudo)
            key = str(Path(pwd.getpwnam(who).pw_dir) / key[1:].lstrip("/"))
        if key and Path(key).is_file() and not Path(key).resolve().is_relative_to(ROOT):
            dst = cfg.path("AURORA_STATUS_DIR") / "keys" / "firewall_key"
            def move_key(src=Path(key), dst=dst):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                shutil.chown(dst, ACCOUNT, ACCOUNT)
                dst.chmod(0o600)
            step(f"the firewall's SSH key copied into {dst.parent} (the setting follows)", move_key)
            sets.append(f"AURORA_FIREWALL_SSH_KEY={dst}")
    except Exception as e:                               # noqa: BLE001 — no .env yet (a fresh install): only the account
        print(f"  (settings not read: {type(e).__name__})")
    # written in place, as the owner (sys_config.write_env keeps the file's group: the services' own); sys_env_sync's
    # --set only proposes (.env.proposed), the first VM trial left the old account in place
    code = ("import sys; sys.path.insert(0, %r); from aurora import sys_config as c; "
            "c.write_env(c.env_file_path(), dict(a.split('=', 1) for a in sys.argv[1:]))" % str(ROOT / "sys" / "core"))
    step("settings " + ", ".join(s.split("=")[0] for s in sets), run, "runuser", "-u", who, "--", str(py), "-c", code, *sets)


def services(who: str) -> None:
    py = ROOT / ".venv" / "bin" / "python"
    step("the units and the polkit rule written for the account", run, "runuser", "-u", who, "--", str(py),
         str(ROOT / "sys" / "core" / "script" / "sys_install_services.py"))
    step("the units installed", run, "bash", str(ROOT / "sys" / "deploy" / "systemd" / "install.sh"))
    nft = ROOT / "sys" / "deploy" / "nft" / "install.sh"
    if Path("/usr/local/sbin/aurora-nft").exists() and nft.exists():
        step("the firewall helper's socket for the account", lambda: subprocess.run(
            ["bash", str(nft)], env={**os.environ, "SVC_ACCOUNT": ACCOUNT}, check=True))
    tunnel = ROOT / "sys" / "deploy" / "cloudflared" / "install.sh"
    if Path("/etc/systemd/system/aurora-tunnel.service").exists() and tunnel.exists():
        # the tunnel reads its token from the services' data: it runs on their account too, or the way in from
        # outside would be lost at the next start
        step("the Cloudflare tunnel on the account", lambda: subprocess.run(
            ["bash", str(tunnel)], env={**os.environ, "SVC_ACCOUNT": ACCOUNT}, check=True))
    step("the services restarted", run, "systemctl", "restart", "aurora.target")


def main() -> int:
    if os.geteuid() != 0:
        print("run with sudo")
        return 1
    who = owner()
    print(f"Aurora in {ROOT}, owner {who}: the services move to the account «{ACCOUNT}»" + (" (dry run)" if DRY else ""))
    account(who)
    traverse()
    tree()
    data_owner()
    from_home(who)
    if "--account-only" not in sys.argv:
        settings(who)
        services(who)
    print("done." + ("" if DRY else " Claude CLI: log in again from ☁️ Accounts (the account's own login). "
                     f"{who} is in the group {ACCOUNT} from the next login: log out and in (or restart) once."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
