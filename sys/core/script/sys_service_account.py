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
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
# root runs this from its own signed copy (sudo aurora-root account, C556): Aurora's folder then comes from the
# launcher (INSTALL_ROOT), the package from beside this file — never imported from the folder the services write
LIB = Path("/usr/local/lib/aurora")
ROOT = Path(os.environ["INSTALL_ROOT"]) if HERE.is_relative_to(LIB) and os.environ.get("INSTALL_ROOT") else HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
from aurora import sys_rootcmd  # noqa: E402 — stdlib only, the lists of C556
SHIM = sys_rootcmd.SHIM
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


def _dirfd(path: Path) -> int:
    """A folder opened by root through no symbolic link, from / down. The caller closes it."""
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


def copy_owner_key(src: Path, keys: Path, who: str, account: str = ACCOUNT, name: str = "firewall_key") -> None:
    """Audit F1, 12 Nov: the path comes from .env, which the services' account writes — root copied any file it named
    (the owner's signing key, /etc/shadow) to a file of the account's, through links. Now only a regular file of the
    owner's own (never a link, at most 64 KiB) is copied, written as a new file through the folder's descriptor."""
    fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != pwd.getpwnam(who).pw_uid or st.st_size > 65536:
            raise PermissionError(f"{src}: not a regular file of {who}'s: not copied")
        data = os.read(fd, 65537)
    finally:
        os.close(fd)
    top = _dirfd(keys.parent)
    try:
        try:
            os.mkdir(keys.name, 0o700, dir_fd=top)
        except FileExistsError:
            pass
        d = os.open(keys.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=top)
    finally:
        os.close(top)
    try:
        try:
            os.unlink(name, dir_fd=d)
        except FileNotFoundError:
            pass
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=d)
        try:
            os.write(out, data)
            a = pwd.getpwnam(account)
            os.fchown(out, a.pw_uid, a.pw_gid)
        finally:
            os.close(out)
    finally:
        os.close(d)


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
        step(f"its home {home}", make_home, home)
    for g in GPU_GROUPS:
        if exists_group(g) and (DRY or ACCOUNT not in grp.getgrnam(g).gr_mem):
            step(f"{ACCOUNT} in {g} (the GPU)", run, "usermod", "-aG", g, ACCOUNT)
    if DRY or not exists_group(ACCOUNT) or who not in grp.getgrnam(ACCOUNT).gr_mem:
        step(f"{who} in the group {ACCOUNT} (to read and write the installation as before)", run, "usermod", "-aG", ACCOUNT, who)


def make_home(home: Path, account: str = ACCOUNT) -> None:
    """C592 (audit F7): the home is in a folder the account writes — made, owned and its mode set on the open folder,
    reached through no link (chown and chmod by path followed one planted there)."""
    home.parent.mkdir(parents=True, exist_ok=True)
    top = _dirfd(home.parent)
    try:
        try:
            os.mkdir(home.name, 0o750, dir_fd=top)
        except FileExistsError:
            pass
        fd = os.open(home.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=top)
        try:
            a = pwd.getpwnam(account)
            os.fchown(fd, a.pw_uid, a.pw_gid)
            os.fchmod(fd, 0o750)
        finally:
            os.close(fd)
    finally:
        os.close(top)


def _entry(dfd: int, name: str, change) -> bool:
    """C592 (audit F7): one entry of a folder root holds open, changed on the entry itself — opened O_PATH and never
    through a link, then owner and mode set on that very file. By path, after an «is it a link?», the services'
    account had the time to swap it for a link to a file of root's. False for a link: left as it is."""
    fd = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=dfd)
    try:
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode):
            return False
        if change:
            change(f"/proc/self/fd/{fd}", st)
        return True
    finally:
        os.close(fd)


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
        own = None if DRY else (lambda target, st: os.chown(target, uid, -1))
        if not os.path.lexists(top):
            continue
        if not top.is_dir() or top.is_symlink():          # a file (.env): through its folder's descriptor
            d = os.open(top.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                n += _entry(d, top.name, own)
            finally:
                os.close(d)
            continue
        # C592: fwalk holds each folder open and never enters a link; every change goes through those descriptors
        for here, dirs, files, dfd in os.fwalk(top, follow_symlinks=False):
            dirs[:] = [d for d in dirs if not papers(Path(here) / d)]     # papers: never the account's, even read
            n += 1
            if own:
                own(dfd, None)
            for f in files:
                n += _entry(dfd, f, own)
    step(f"the data ({', '.join(DATA)}): {n} files and folders owned by {ACCOUNT}; the code stays the owner's")


def tree_mode(p: Path, mode: int, is_dir: bool) -> int:
    """The mode a file or folder of the installation gets, from the one it has."""
    if in_papers(p):                                     # --with-papers: the group may read, nothing else; the
        return mode | (0o050 if is_dir else 0o040)       # files stay the owner's, none written
    rel = p.relative_to(ROOT).as_posix()
    if sys_rootcmd.owner_only(rel):                      # C556: the group reads and runs it, never writes it
        add = 0o050 | stat.S_ISGID if is_dir else 0o040 | (0o010 if mode & 0o100 else 0)
        return (mode | add) & ~0o020
    if is_dir:
        return mode | 0o070 | stat.S_ISGID | (stat.S_ISVTX if rel in sys_rootcmd.STICKY else 0)
    if p.name == ".env":
        return 0o660
    return mode | 0o060 | (0o010 if mode & 0o100 else 0)


def tree() -> None:
    gid = grp.getgrnam(ACCOUNT).gr_gid if exists_group(ACCOUNT) else -1
    n = skipped = 0
    def change(p: Path):
        def fn(target, st):
            st = st or os.stat(target)
            os.chown(target, -1, gid)
            os.chmod(target, tree_mode(p, stat.S_IMODE(st.st_mode), stat.S_ISDIR(st.st_mode)))
        return None if DRY else fn
    # C592 (audit F7): fwalk holds each folder open and never enters a link; group and mode are set on the open
    # folder and, for a file, on the entry itself (_entry) — never by a path the account can swap after the check
    for top, dirs, files, dfd in os.fwalk(ROOT, follow_symlinks=False):
        here = Path(top)
        keep = []
        for d in dirs:
            if papers(here / d) and not WITH_PAPERS:
                skipped += 1
                continue
            keep.append(d)
        dirs[:] = keep
        n += 1
        if not DRY:
            change(here)(dfd, None)
        for name in files:
            n += _entry(dfd, name, change(here / name))
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
        if rel.endswith("backup.key") and d.with_name("backup.key.sealed").exists():
            continue                                    # sealed for the services (C461): never a plain copy again
        if s.exists() and not d.exists():
            def copy(s=s, d=d):
                # C592: root copies into a folder of its own and hands it over; the account itself puts it in its
                # home — a link it planted there leads only where it could write anyway, never a write of root's
                work = Path(tempfile.mkdtemp(prefix="aurora-home-"))
                try:
                    (shutil.copytree if s.is_dir() else shutil.copy2)(s, work / s.name)
                    run("chown", "-R", f"{ACCOUNT}:{ACCOUNT}", str(work))
                    run("runuser", "-u", ACCOUNT, "--", "mkdir", "-p", str(d.parent))
                    run("runuser", "-u", ACCOUNT, "--", "cp", "-a", str(work / s.name), str(d))
                finally:
                    shutil.rmtree(work, ignore_errors=True)
            step(f"{rel} copied to the account's home", copy)


def settings(who: str) -> None:
    py = ROOT / ".venv" / "bin" / "python"
    sets = [f"AURORA_SERVICE_USER={ACCOUNT}"]
    try:
        from aurora import sys_config                  # the package beside this file (C556)
        cfg = sys_config.load()
        key = str(cfg["AURORA_FIREWALL_SSH_KEY"] or "")
        if key.startswith("~"):                          # the owner's home, not root's (this runs with sudo)
            key = str(Path(pwd.getpwnam(who).pw_dir) / key[1:].lstrip("/"))
        if key and Path(key).is_file() and not Path(key).resolve().is_relative_to(ROOT):
            dst = cfg.path("AURORA_STATUS_DIR") / "keys" / "firewall_key"
            def move_key(src=Path(key), dst=dst):
                copy_owner_key(src, dst.parent, who)
            step(f"the firewall's SSH key copied into {dst.parent} (the setting follows)", move_key)
            sets.append(f"AURORA_FIREWALL_SSH_KEY={dst}")
    except Exception as e:                               # noqa: BLE001 — no .env yet (a fresh install): only the account
        print(f"  (settings not read: {type(e).__name__})")
    # written in place, as the owner (sys_config.write_env keeps the file's group: the services' own); sys_env_sync's
    # --set only proposes (.env.proposed), the first VM trial left the old account in place
    code = ("import sys; sys.path.insert(0, %r); from aurora import sys_config as c; "
            "c.write_env(c.env_file_path(), dict(a.split('=', 1) for a in sys.argv[1:]))" % str(ROOT / "sys" / "core"))
    step("settings " + ", ".join(s.split("=")[0] for s in sets), run, "runuser", "-u", who, "--", str(py), "-c", code, *sets)


def root_launcher() -> Path:
    """C592 (audit F2): aurora-root as root runs it — root's own signed copy beside this file when this is root's
    copy, never the one in Aurora's folder, which the services' account can write (it ran as root before any check)."""
    return (HERE.parent if HERE.is_relative_to(LIB) else ROOT / "sys" / "core" / "script") / "sys_root.py"


def services(who: str) -> None:
    py = ROOT / ".venv" / "bin" / "python"
    step("the units and the polkit rule written for the account", run, "runuser", "-u", who, "--", str(py),
         str(ROOT / "sys" / "core" / "script" / "sys_install_services.py"))
    # root installs through aurora-root (sys_root.py, 9 Nov): only what the owner signed, from root's own copy
    launcher = ["/usr/bin/python3", "-I", str(root_launcher()), "install"]
    step("the units installed", run, *launcher, "systemd")
    nft = ROOT / "sys" / "deploy" / "nft" / "install.sh"
    if Path("/usr/local/sbin/aurora-nft").exists() and nft.exists():
        step("the firewall helper's socket for the account", lambda: subprocess.run(
            [*launcher, "nft"], env={**os.environ, "SVC_ACCOUNT": ACCOUNT}, check=True))
    tunnel = ROOT / "sys" / "deploy" / "cloudflared" / "install.sh"
    if Path("/etc/systemd/system/aurora-tunnel.service").exists() and tunnel.exists():
        # the tunnel reads its token from the services' data: it runs on their account too, or the way in from
        # outside would be lost at the next start
        step("the Cloudflare tunnel on the account", lambda: subprocess.run(
            [*launcher, "tunnel"], env={**os.environ, "SVC_ACCOUNT": ACCOUNT}, check=True))
    step("the services restarted", run, "systemctl", "restart", "aurora.target")


def main() -> int:
    if os.geteuid() != 0:
        print("run with sudo")
        return 1
    if SHIM.exists() and not HERE.is_relative_to(LIB):   # C592 (audit F2): root never runs the writable folder's copy
        print("use: sudo aurora-root account — this copy is in the folder the services can write")
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
