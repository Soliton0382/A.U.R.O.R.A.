# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: the list of windows for «Mostrami», in a short-lived process of its own (bozza 8 §10 R4): it
reads the AT-SPI registry over D-Bus (no libatspi), prints one JSON list and exits before any recording starts.
Only what the owner needs to choose: program name, window title, PID, bus name, window path.

    python3 -I -B windows.py [--exclude-pid N]"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recorder import App, a11y_address, connect  # noqa: E402

from gi.repository import Gio, GLib  # noqa: E402

SKIP = {"xdg-desktop-portal-kde", "xdg-desktop-portal-gtk", "ksecretd", "kwalletd", "kded6", "kiod6", "kwin",
        "ksmserver", "gmenudbusmenuproxy", "xembedsniproxy", "kaccess", "plasmashell", "polkit-kde-authentication-"
        "agent-1", "org_kde_powerdevil", "kdeconnect.daemon", "ActivityManager", "kupdaemon", "discover.notifier"}


def list_windows(exclude_pid: int = -1) -> list:
    addr = a11y_address()
    c = connect(addr)
    reg = c.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root", "org.a11y.atspi.Accessible",
                      "GetChildren", None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
    out = []
    for bus, path in reg:
        try:
            pid = c.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "GetConnectionUnixProcessID", GLib.Variant("(s)", (bus,)), None,
                              Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        except GLib.Error:
            continue
        if pid == exclude_pid or pid == os.getpid():
            continue
        app = App(c, bus)
        name = app.info(path).get("name") or ""
        if name in SKIP:
            continue
        for k in app.children(path):
            i = app.info(k)
            if i.get("name") and i.get("role") not in ("application", "tool tip", "popup menu", "menu"):
                out.append({"app": name, "title": i["name"], "pid": pid, "bus": bus, "frame": k,
                            "role": i["role"]})
    c.close_sync(None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-pid", type=int, default=-1)
    a = ap.parse_args()
    print(json.dumps({"addr": a11y_address(), "windows": list_windows(a.exclude_pid)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
