# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F9: aurora-desk's window out of AT-SPI (way A), while the libatspi reader still reads other programs.

Per launch: aurora-desk's test window (f9_apps desk) with way A, and the 50-node test program (f9_apps tree).
Per attempt: (1) every AT-SPI object found for the desk window's PID, and every action invoked on them; the window's
own event file says whether anything happened; (2) the tree program read again: the 50 named nodes, with roles.
Positive control: the same desk window without way A must be seen and its «Sì» pressed through AT-SPI (the reader
and the oracle are not blind).
"""
import json
import subprocess
import time
from pathlib import Path

from gi.repository import Atspi

from . import a11y

HERE = Path(__file__).resolve().parent
ROLE = {"label": {Atspi.Role.LABEL}, "button": {Atspi.Role.PUSH_BUTTON, Atspi.Role.BUTTON},
        "check": {Atspi.Role.CHECK_BOX}}


def _events(path: Path) -> list:
    try:
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    except OSError:
        return []


def desk_objects(pid: int, press: bool) -> dict:
    """Every AT-SPI node of the app with this PID; with press, every action on every node is invoked."""
    nodes = actions_ok = actions_tried = 0
    apps = [a for a in a11y.apps() if a11y.app_pid(a) == pid]
    for app in apps:
        for depth, n in a11y.walk(app):
            if depth == 0 and not app.get_child_count():
                continue                               # the bare application node, without children
            nodes += 1
            if not press:
                continue
            ai = n.get_action_iface()
            if ai is None:
                continue
            for i in range(ai.get_n_actions()):
                actions_tried += 1
                try:
                    if ai.do_action(i):
                        actions_ok += 1
                except Exception:                       # noqa: BLE001
                    pass
    return {"apps": len(apps), "nodes": nodes, "actions_tried": actions_tried, "actions_ok": actions_ok}


def read_tree(pid: int, spec: list) -> dict:
    want = {s["name"]: s["kind"] for s in spec}
    got = {}
    total = 0
    for app in [a for a in a11y.apps() if a11y.app_pid(a) == pid]:
        for _, n in a11y.walk(app):
            total += 1
            try:
                nm, role = n.get_name(), n.get_role()
            except Exception:                           # noqa: BLE001
                continue
            if nm in want:
                got[nm] = role
    right = sum(1 for nm, kind in want.items() if nm in got and got[nm] in ROLE[kind])
    return {"named_found": len(got), "right": right, "of": len(want), "all_nodes": total}


def press_yes(pid: int) -> bool:
    for app in [a for a in a11y.apps() if a11y.app_pid(a) == pid]:
        for _, n in a11y.walk(app):
            try:
                if n.get_name() == "Sì" and n.get_role() in ROLE["button"]:
                    return bool(a11y.do_action(n, ("Press", "press", "click")))
            except Exception:                           # noqa: BLE001
                continue
    return False


def _wait_app(pid: int, timeout: float = 15.0, need_children: bool = True) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        for a in a11y.apps():
            if a11y.app_pid(a) == pid and (a.get_child_count() or not need_children):
                return True
        time.sleep(0.1)
    return False


def launch(bench, i: int, way_a: bool):
    wd = bench.base / "f9"
    wd.mkdir(exist_ok=True)
    ev = wd / f"desk-{i}-{int(way_a)}.jsonl"
    ready = wd / f"tree-{i}.json"
    extra = {"AT_SPI_BUS_ADDRESS": f"unix:path={bench.rt}/no-a11y-bus"} if way_a else {}
    d = bench.procs.start(f"f9desk-{i}", ["/usr/bin/python3", "-I", "-B", str(HERE / "f9_apps.py"), "desk",
                                          "--events", str(ev)], bench.wenv(**extra),
                          stdout=bench.out("f9"), stderr=subprocess.STDOUT)
    t = bench.procs.start(f"f9tree-{i}", ["/usr/bin/python3", "-I", "-B", str(HERE / "f9_apps.py"), "tree",
                                          "--ready", str(ready)], bench.wenv(),
                          stdout=bench.out("f9"), stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 20 and not (ready.exists() and any(e["kind"] == "ready" for e in _events(ev))):
        time.sleep(0.05)
    return d, t, ev, ready


def run(bench, launches: int, attempts: int, controls: int, log) -> dict:
    a11y.init()
    rows, ctrl = [], []
    for i in range(launches):
        d, t, ev, ready = launch(bench, i, way_a=True)
        try:
            spec = json.loads(ready.read_text())["spec"]
            seen_tree = _wait_app(t.pid)
            time.sleep(1.0)                            # the desk window gets the same time to (not) appear
            for k in range(attempts):
                before = len(_events(ev))
                o = desk_objects(d.pid, press=True)
                time.sleep(0.05)
                happened = [e for e in _events(ev)[before:] if e["kind"] != "ready"]
                r = read_tree(t.pid, spec)
                rows.append({"launch": i, "attempt": k, "desk": o, "desk_events": len(happened), "tree": r,
                             "tree_app_seen": seen_tree})
            log(f"F9 launch={i} desk_nodes={rows[-1]['desk']['nodes']} tree={rows[-1]['tree']['right']}")
        finally:
            bench.procs.stop_one(d)
            bench.procs.stop_one(t)
    for i in range(controls):
        d, t, ev, ready = launch(bench, 1000 + i, way_a=False)
        try:
            seen = _wait_app(d.pid)
            before = len(_events(ev))
            o = desk_objects(d.pid, press=False)
            pressed = press_yes(d.pid)
            time.sleep(0.3)
            happened = [e for e in _events(ev)[before:] if e["kind"] == "press"]
            ctrl.append({"control": i, "seen": seen, "desk": o, "press_action": pressed,
                         "press_events": len(happened)})
            log(f"F9 control={i} nodes={o['nodes']} press_events={len(happened)}")
        finally:
            bench.procs.stop_one(d)
            bench.procs.stop_one(t)
    return {"rows": rows, "controls": ctrl, "way_a": "AT_SPI_BUS_ADDRESS=unix:path=<bench rt>/no-a11y-bus"}
