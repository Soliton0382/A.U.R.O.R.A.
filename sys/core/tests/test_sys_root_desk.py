# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 D10: `aurora-root install desk` then `uninstall desk` leave no file behind (in a folder of its own), the
launcher runs root's copy with an environment written out, and the personal library is never touched."""
import os
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))

import sys_root_desk as D  # noqa: E402


def _write(path: Path, data: bytes, mode: int, owner=None) -> None:
    path.write_bytes(data)
    os.chmod(path, mode)


def _files(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink())


def test_install_then_uninstall_leaves_nothing(tmp_path):
    lib = tmp_path / "home" / ".local" / "state" / "aurora-desk" / "library" / "bozze" / "x.json"
    lib.parent.mkdir(parents=True)
    lib.write_text("{}")                                 # the owner's personal library: never touched
    written = D.install(_write, prefix=tmp_path, run=lambda *a, **k: None)
    assert len(written) == 6 and all(Path(p).is_file() for p in written)
    modes = {k: stat.S_IMODE(os.stat(tmp_path / f).st_mode) for k, f in D.FILES.items()}
    assert modes == {"launcher": 0o755, "unit": 0o644, "desktop": 0o644, "icon": 0o644, "autostart": 0o644,
                     "web_desktop": 0o644}
    gone = D.uninstall(prefix=tmp_path, run=lambda *a, **k: None)
    assert sorted(gone) == sorted(written)
    assert _files(tmp_path) == ["home/.local/state/aurora-desk/library/bozze/x.json"]


def test_a_link_in_place_is_left_alone(tmp_path):
    D.install(_write, prefix=tmp_path, run=lambda *a, **k: None)
    target = tmp_path / "someone-elses"
    target.write_text("x")
    icon = tmp_path / D.FILES["icon"]
    icon.unlink()
    icon.symlink_to(target)
    D.uninstall(prefix=tmp_path, run=lambda *a, **k: None)
    assert icon.is_symlink() and target.read_text() == "x"


def test_the_launcher_runs_roots_copy_with_a_written_environment():
    t = D.LAUNCHER
    assert "/usr/bin/env -i " in t and "PATH=/usr/bin:/bin" in t
    assert "/usr/bin/python3 -I -B -X pycache_prefix=/nonexistent/aurora-desk" in t     # C737: -I ignores PYTHON*
    assert "/usr/local/lib/aurora/sys/core/desk/app/aurora_desk.py" in t                # C738: root's copy
    assert '--unit="aurora-desk-$id"' in t                                               # R1: no owner's drop-in
    assert "LimitCORE=0" in t and "RestrictAddressFamilies=AF_UNIX" in t and "ExecStopPost=" in t
    assert "SystemCallErrorNumber=EPERM" in t        # D9: a forbidden call answers an error; the default kills (SIGSYS)
    r = subprocess.run(["/bin/sh", "-n"], input=t, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr


def test_the_login_unit_puts_accessibility_back():
    assert "a11y_fix.py" in D.UNIT_TEXT and "Type=oneshot" in D.UNIT_TEXT and "WantedBy=default.target" in D.UNIT_TEXT
    assert "/usr/local/lib/aurora/" in D.UNIT_TEXT


def test_the_tray_at_login_and_the_launcher_takes_only_tray_or_web():
    assert "Exec=/usr/local/bin/aurora-desk --tray" in D.AUTOSTART and "NoDisplay=true" in D.AUTOSTART
    assert 'case "$*" in "" | --tray | --web) ;;' in D.LAUNCHER and "aurora_desk.py $*" in D.LAUNCHER


def test_the_web_window_has_its_own_unit_with_network_and_only_aurora_s_address():
    t = D.LAUNCHER
    web = t[t.index('if [ "$*" = "--web" ]'):t.index("\nfi\n")]
    assert '--unit="aurora-web-$id"' in web and "LimitCORE=0" in web and "/usr/bin/env -i " in web
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK" in web
    assert "DESK_WEB_URL=http://127.0.0.1:9700/" in web and web.rstrip().endswith("desk/app/web.py")
    assert "aurora_desk.py" not in web                       # the learning app keeps AF_UNIX only
    assert "__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json" in web     # never the RTX cards
    assert "__GLX_VENDOR_LIBRARY_NAME=mesa" in web and "CUDA_VISIBLE_DEVICES= " in web
    assert "Exec=/usr/local/bin/aurora-desk --web" in D.WEB_DESKTOP and D.FILES["web_desktop"].endswith("aurora.desktop")


def test_the_menu_entry_and_icon():
    assert "Exec=/usr/local/bin/aurora-desk" in D.DESKTOP and "Icon=aurora-desk" in D.DESKTOP
    assert D.FILES["desktop"].endswith("aurora-desk.desktop")        # = the app's Wayland id (setDesktopFileName)
    assert D._icon_svg().lstrip().startswith("<svg")


def test_sys_root_carries_desk_into_roots_copy():
    src = (Path(__file__).resolve().parents[1] / "script" / "sys_root.py").read_text()
    assert '"sys_root_desk.py"' in src and 'rel.startswith("sys/core/desk/") and rel.endswith(".py")' in src
    assert 'if action == "uninstall":' in src
