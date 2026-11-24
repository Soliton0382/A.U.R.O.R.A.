# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""`aurora-root install desk` / `uninstall desk` (N152, Aurora Desktop version 1; design bozza 8 §1, §2, §10 R1/R9).

Run by root's copy of sys_root.py after the signature and root's copy (sync_lib, which carries sys/core/desk/) are
done. It writes, all owned by root:
  /usr/local/bin/aurora-desk                     the launcher: a transient user unit with a random name (no drop-in of
                                                 the owner's applies), an environment written out (env -i), the
                                                 system's Python -I -B from root's copy, no core dumps, no network
                                                 sockets, accessibility put back when the unit stops (ExecStopPost)
  /etc/systemd/user/aurora-desk-a11y-fix.service accessibility put back at login after an interrupted demonstration
                                                 (enabled with --global; disabled and removed by uninstall)
  /usr/local/share/applications/aurora-desk.desktop  the menu entry (its name = the app's Wayland id)
  /usr/local/share/icons/hicolor/scalable/apps/aurora-desk.svg  the icon (from desk/app/icon.py, signed)
Uninstall puts accessibility back as the owner first, then removes exactly these files. The owner's personal library
(~/.local/state/aurora-desk) is never touched by either. Every path sits under `prefix` (default /) so a test can
install and uninstall in a folder of its own (D10)."""
import os
import subprocess
import sys
from pathlib import Path

LIB = "/usr/local/lib/aurora"
PY = "/usr/bin/python3 -I -B -X pycache_prefix=/nonexistent/aurora-desk"
APP = f"{LIB}/sys/core/desk/app"
UNIT = "aurora-desk-a11y-fix.service"
FILES = {
    "launcher": "usr/local/bin/aurora-desk",
    "unit": f"etc/systemd/user/{UNIT}",
    "desktop": "usr/local/share/applications/aurora-desk.desktop",
    "icon": "usr/local/share/icons/hicolor/scalable/apps/aurora-desk.svg",
}

LAUNCHER = f"""#!/bin/sh
# Aurora Desktop (N152): written by `aurora-root install desk`. Root's signed copy, never the repository's; an
# environment written out (env -i: nothing inherited from the session's manager but what is listed); a transient user
# unit with a random name, so no drop-in under ~/.config/systemd/user applies; accessibility put back when it stops.
case "$XDG_RUNTIME_DIR" in /run/user/[0-9]*) ;; *) echo "aurora-desk: no session" >&2; exit 1 ;; esac
case "$WAYLAND_DISPLAY" in wayland-[0-9]*) ;; *) echo "aurora-desk: Wayland only" >&2; exit 1 ;; esac
id=$(od -An -N4 -tx4 /dev/urandom | tr -d ' ')
exec /usr/bin/systemd-run --user --quiet --collect --unit="aurora-desk-$id" \\
  -p LimitCORE=0 -p NoNewPrivileges=yes -p RestrictAddressFamilies=AF_UNIX -p SystemCallArchitectures=native \\
  -p "SystemCallFilter=~io_uring_setup io_uring_enter io_uring_register" -p SystemCallErrorNumber=EPERM \\
  -p "ExecStopPost={PY} {APP}/a11y_fix.py" \\
  /usr/bin/env -i PATH=/usr/bin:/bin HOME="$HOME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \\
    WAYLAND_DISPLAY="$WAYLAND_DISPLAY" DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \\
    LANG="${{LANG:-C.UTF-8}}" LANGUAGE="${{LANGUAGE:-}}" QT_QPA_PLATFORM=wayland \\
    {PY} {APP}/aurora_desk.py
"""

UNIT_TEXT = f"""[Unit]
Description=Aurora Desktop: accessibility put back after an interrupted demonstration
After=dbus.socket
Before=plasma-workspace.target graphical-session.target

[Service]
Type=oneshot
ExecStart={PY} {APP}/a11y_fix.py

[Install]
WantedBy=default.target
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=Aurora Desktop
GenericName=Aurora impara dal desktop
Comment=Aurora impara da una tua dimostrazione; non agisce sul desktop (versione 1)
Exec=/usr/local/bin/aurora-desk
Icon=aurora-desk
Terminal=false
Categories=Utility;
StartupNotify=true
"""


def _icon_svg() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from desk.app import icon
    return icon.SVG


def _put(write, prefix: Path, key: str, text: str, mode: int) -> None:
    path = prefix / FILES[key]
    for d in reversed([path.parent, *path.parent.parents]):
        if d == prefix or prefix not in [d, *d.parents]:
            continue
        if not d.exists():
            d.mkdir(mode=0o755)
    write(path, text.encode(), mode, (0, 0))


def install(write, prefix: Path = Path("/"), run=subprocess.run) -> list:
    """Write the four files with `write` (sys_root._write: no link on the way, root-owned, atomic); enable the login
    unit for every user (only when prefix is /). Returns what was written."""
    _put(write, prefix, "launcher", LAUNCHER, 0o755)
    _put(write, prefix, "unit", UNIT_TEXT, 0o644)
    _put(write, prefix, "desktop", DESKTOP, 0o644)
    _put(write, prefix, "icon", _icon_svg(), 0o644)
    if prefix == Path("/"):
        run(["/usr/bin/systemctl", "--global", "enable", UNIT], check=False)
    return [str(prefix / f) for f in FILES.values()]


def owner_restore(run=subprocess.run) -> str:
    """Accessibility put back as the owner (the one who ran sudo), on his session bus, before anything is removed."""
    uid = os.environ.get("SUDO_UID")
    if not uid or not uid.isdigit():
        return "no owner session (not run through sudo): the login unit is gone, put it back by hand if needed"
    bus = f"/run/user/{uid}/bus"
    if not os.path.exists(bus):
        return "the owner has no session now"
    r = run(["/usr/sbin/runuser", "-u", os.environ.get("SUDO_USER", ""), "--", "/usr/bin/env", "-i",
             f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}", f"XDG_RUNTIME_DIR=/run/user/{uid}",
             f"HOME={Path('~' + os.environ.get('SUDO_USER', '')).expanduser()}", "PATH=/usr/bin:/bin",
             *PY.split(), f"{APP}/a11y_fix.py"], capture_output=True, text=True, check=False)
    return (r.stdout or r.stderr).strip()


def uninstall(prefix: Path = Path("/"), run=subprocess.run) -> list:
    """Put accessibility back (owner), disable the login unit, remove exactly the installed files. Returns removed."""
    if prefix == Path("/"):
        print(f"  accessibilità: {owner_restore(run)}")
        run(["/usr/bin/systemctl", "--global", "disable", UNIT], check=False)
    gone = []
    for rel in FILES.values():
        p = prefix / rel
        if p.is_symlink():
            print(f"  {p}: a link, left alone (not ours)")
            continue
        if p.exists():
            p.unlink()
            gone.append(str(p))
    return gone


def main(action: str, write, yes: bool) -> int:
    if action == "install":
        for p in install(write):
            print(f"  scritto {p}")
        print("  Aurora Desktop nel menu delle applicazioni (se non compare subito: esci e rientra, o kbuildsycoca6). "
              "La tua libreria personale resta in ~/.local/state/aurora-desk.")
        return 0
    if action == "uninstall":
        for p in uninstall():
            print(f"  tolto {p}")
        print("  La tua libreria personale (~/.local/state/aurora-desk) non l'ho toccata: è tua.")
        return 0
    print("desk: install or uninstall", file=sys.stderr)
    return 1
