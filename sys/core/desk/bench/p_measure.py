# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 v1, preliminary measures P1-P3 on the virtual bench (design bozza 8 §10). P1 uses the real dconf backend
inside the bench HOME (never the owner's). Results in DIR/run-*/p_results.json.

    python3 -I -B p_measure.py --scratch DIR [--trials 10]"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from desk.bench import a11y, bench as benchmod  # noqa: E402

KEY = ["org.gnome.desktop.interface", "toolkit-accessibility"]


def gget(env: dict) -> str:
    r = subprocess.run(["/usr/bin/gsettings", "get", *KEY], env=env, capture_output=True, text=True, timeout=20)
    return (r.stdout or r.stderr).strip()


def is_enabled() -> bool:
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    r = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Get",
                      GLib.Variant("(ss)", ("org.a11y.Status", "IsEnabled")), None, Gio.DBusCallFlags.NONE, 3000, None)
    return bool(r.unpack()[0])


def a11y_addr() -> str:
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    r = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None,
                      GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 3000, None)
    return r.unpack()[0]


def bus_names_by_pid(addr: str) -> dict:
    """Applications registered on the AT-SPI bus: pid -> unique bus name (D-Bus only)."""
    from gi.repository import Gio, GLib
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    c = Gio.DBusConnection.new_for_address_sync(addr, flags, None, None)
    r = c.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root", "org.a11y.atspi.Accessible",
                    "GetChildren", None, None, Gio.DBusCallFlags.NONE, 3000, None)
    out = {}
    for name, _path in r.unpack()[0]:
        try:
            p = c.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                            "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)), None,
                            Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            out[p] = name
        except GLib.Error:
            continue
    c.close_sync(None)
    return out


def app_by_name(name: str):
    for a in a11y.apps():
        try:
            if a.get_name() == name:
                return a
        except Exception:                               # noqa: BLE001
            continue
    return None


def tree_size(app) -> int:
    return 0 if app is None else sum(1 for _ in a11y.walk(app, limit=5000))


def kate_text(app):
    for _, n in a11y.walk(app, limit=20000):
        try:
            if n.get_role_name() == "text" and (n.get_accessible_id() or "").endswith("KateViewInternal"):
                return n
        except Exception:                               # noqa: BLE001
            continue
    return None


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    res = {"P1": {}, "P2": {}, "P3": {"test": [], "control": []}}
    out = b.base / "p_results.json"
    home = Path(b.desc["home"])
    try:
        res["P1"]["before_up"] = gget(dict(b.env))
        b.up()                                          # sets IsEnabled = true (bench.set_a11y)
        a11y.init()
        res["P1"]["after_set_true"] = gget(dict(b.env))
        res["P1"]["isenabled_after_up"] = is_enabled()

        # P2: Qt at run time
        b.set_a11y(False)
        time.sleep(1.0)
        res["P2"]["isenabled_off"] = is_enabled()
        doc = home / "p2.txt"
        env = b.wenv(LANG="it_IT.UTF-8", LC_ALL="it_IT.UTF-8", LANGUAGE="it")
        env.pop("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", None)
        before = {a11y.app_pid(x) for x in a11y.apps()}
        kate = b.procs.start("p2-kate", ["/usr/bin/kate", str(doc)], env, stdout=b.out("p"), stderr=-2)
        time.sleep(8.0)
        k = app_by_name("kate")
        res["P2"]["tree_while_off"] = tree_size(k)
        b.set_a11y(True)
        t0 = time.monotonic()
        size = 0
        while time.monotonic() - t0 < 10:
            k = app_by_name("kate")
            size = tree_size(k)
            if size > 5:
                break
            time.sleep(0.5)
        res["P2"]["tree_after_on"] = size
        res["P2"]["seconds_to_tree"] = round(time.monotonic() - t0, 2) if size > 5 else None

        # P3: a recorder without libatspi, filtered by RegisterEvent app_bus_name and sender=
        kc = b.procs.start("p3-kcalc", ["/usr/bin/kcalc"], b.wenv(QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1"),
                           stdout=b.out("p"), stderr=-2)
        time.sleep(4.0)
        k = app_by_name("kate")
        if k is None or tree_size(k) <= 5:              # P2 said no: restart Kate with the tree forced on
            b.procs.stop_one(kate)
            kate = b.procs.start("p3-kate", ["/usr/bin/kate", str(doc)],
                                 b.wenv(QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1"), stdout=b.out("p"), stderr=-2)
            time.sleep(5.0)
            res["P3"]["kate_restarted_forced"] = True
        addr = a11y_addr()
        names = bus_names_by_pid(addr)
        pk = a11y.app_pid(app_by_name("kate"))
        pc = a11y.app_pid(app_by_name("kcalc"))
        kate_bus, kcalc_bus = names.get(pk), names.get(pc)
        res["P3"]["bus"] = {"kate": kate_bus, "kcalc": kcalc_bus}
        text = kate_text(app_by_name("kate"))
        res["P3"]["kate_text_found"] = text is not None
        for kind in ("test", "control"):
            for i in range(a.trials):
                canary = f"CANARINO{secrets.token_hex(6).upper()}"
                o = b.base / f"p3-{kind}-{i}.json"
                st = b.base / f"p3-{kind}-{i}.strace"
                args = ["--addr", addr, "--seconds", "4", "--out", str(o)]
                if kind == "test":
                    args += ["--app-bus", kcalc_bus, "--sender", kcalc_bus]
                else:
                    args += ["--app-bus", kate_bus]
                p = subprocess.Popen(["/usr/bin/strace", "-f", "-qq", "-s", "100000", "-e",
                                      "trace=read,recvmsg,recvfrom,readv", "-o", str(st),
                                      "/usr/bin/python3", "-I", "-B", str(HERE / "rec_probe.py"), *args],
                                     env=dict(b.env), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                t1 = time.monotonic()
                while not Path(str(o) + ".ready").exists() and time.monotonic() - t1 < 10:
                    time.sleep(0.05)
                time.sleep(0.5)
                from gi.repository import Atspi
                ok = Atspi.EditableText.set_text_contents(text, f"riga di prova {canary}") if text else False
                p.wait(20)
                rep = json.loads(o.read_text()) if o.exists() else {}
                trace = st.read_text(errors="replace") if st.exists() else ""
                res["P3"][kind].append({"written": bool(ok), "in_trace": canary in trace,
                                        "in_bodies": any(canary in x for x in rep.get("bodies", [])),
                                        "event_signals": rep.get("event_signals"), "register": rep.get("register"),
                                        "senders": rep.get("senders"), "errors": rep.get("register_errors")})
                for f in (o, st, Path(str(o) + ".ready")):
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass

        # P1 (end): a new bus launcher reads the stored value
        b.procs.stop_one(b.started["atspi"])
        time.sleep(1.0)
        res["P1"]["dconf_after_launcher_stop"] = gget(dict(b.env))
        b._start("atspi2", [benchmod.ATSPI_LAUNCHER, "--launch-immediately"], dict(b.env))
        b.wait_name("org.a11y.Bus")
        time.sleep(1.0)
        res["P1"]["isenabled_new_launcher"] = is_enabled()
    except Exception as e:                              # noqa: BLE001
        res["fatal"] = repr(e)
    finally:
        out.write_text(json.dumps(res, indent=1))
        b.down()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(benchmod.default_scratch()))
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--inside", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    desc = benchmod.prepare(Path(a.scratch))
    desc["env"]["GSETTINGS_BACKEND"] = "dconf"          # P1: the real backend, inside the bench HOME only
    argv = ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside", "--trials", str(a.trials)]
    rc = benchmod.reexec_inside(desc, argv)
    print(f"results: {desc['base']}/p_results.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
