# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 v1, measure P3: a recorder without libatspi (Gio only, design bozza 8 §10 R4). It connects to the AT-SPI bus,
registers one event for one application (RegisterEvent with app_bus_name) and adds a match rule, optionally with
sender=, then counts what arrives. Bench only.

    python3 -I -B rec_probe.py --addr A --event object:text-changed [--app-bus :1.x] [--sender :1.x] --seconds S --out F"""
import argparse
import json

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", required=True)
    ap.add_argument("--event", action="append", default=None)
    ap.add_argument("--app-bus", default="")
    ap.add_argument("--sender", default="")
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    a.event = a.event or ["object:text-changed"]
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    conn = Gio.DBusConnection.new_for_address_sync(a.addr, flags, None, None)
    rep = {"register": None, "rule": None, "messages": 0, "event_signals": 0, "senders": {}, "bodies": [],
           "events": []}
    for ev in a.event:
        for sig, args in (("(sass)", (ev, [], a.app_bus)), ("(sas)", (ev, [])), ("(s)", (ev,))):
            try:
                conn.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/registry", "org.a11y.atspi.Registry",
                               "RegisterEvent", GLib.Variant(sig, args), None, Gio.DBusCallFlags.NONE, 3000, None)
                rep["register"] = sig
                break
            except GLib.Error as e:
                rep.setdefault("register_errors", []).append(f"{sig}: {e.message}")
    rules = []
    for iface in ("Object", "Window", "Focus", "Keyboard"):
        rule = f"type='signal',interface='org.a11y.atspi.Event.{iface}'"
        if a.sender:
            rule += f",sender='{a.sender}'"
        conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch",
                       GLib.Variant("(s)", (rule,)), None, Gio.DBusCallFlags.NONE, 3000, None)
        rules.append(rule)
    rep["rule"] = rules

    def filt(c, msg, incoming):
        if incoming:
            rep["messages"] += 1
            if msg.get_message_type() == Gio.DBusMessageType.SIGNAL and \
                    (msg.get_interface() or "").startswith("org.a11y.atspi.Event"):
                rep["event_signals"] += 1
                s = msg.get_sender() or "?"
                rep["senders"][s] = rep["senders"].get(s, 0) + 1
                b = msg.get_body()
                if b is not None and len(rep["bodies"]) < 50:
                    rep["bodies"].append(str(b.unpack())[:300])
                if len(rep["events"]) < 2000:
                    u = b.unpack() if b is not None else ()
                    rep["events"].append({"i": msg.get_interface().rsplit(".", 1)[-1], "m": msg.get_member(),
                                          "path": msg.get_path(), "detail": u[0] if u else "",
                                          "d1": u[1] if len(u) > 1 else None, "d2": u[2] if len(u) > 2 else None,
                                          "v": str(u[3])[:200] if len(u) > 3 else ""})
        return msg

    conn.add_filter(filt)
    loop = GLib.MainLoop()
    GLib.timeout_add(int(a.seconds * 1000), loop.quit)
    with open(a.out + ".ready", "w") as f:
        f.write("ready")
    loop.run()
    with open(a.out, "w") as f:
        json.dump(rep, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
