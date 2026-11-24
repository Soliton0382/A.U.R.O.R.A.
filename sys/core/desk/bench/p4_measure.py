# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 v1, preliminary measure P4 on the virtual bench: real keys (RemoteDesktop portal + libei, ei_input.py) into
Kate, then Ctrl+S, while a recorder without libatspi (rec_probe.py), filtered on Kate's bus name, listens.
Results in DIR/run-*/p4_results.json.

    python3 -I -B p4_measure.py --scratch DIR [--trials 10]"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from desk.bench import a11y, bench as benchmod, ei_input  # noqa: E402
from desk.bench.p_measure import a11y_addr, app_by_name, bus_names_by_pid  # noqa: E402

TEXTS = ["Hello world 123", "Lista: mele, pane", "Prova numero 2 (ok)", "a+b=c; x/y", "Due parole",
         "Riga con punto.", "SIMBOLI # @ & * !", "minuscole e MAIUSCOLE", "1234567890", "Fine della prova?"]
EVENTS = ["object:text-changed", "object:property-change", "object:state-changed", "window:", "focus:"]


def approve() -> bool:
    """The bench's consent: «Approve» on the portal's «Remote Control» dialog; the restore box is never touched."""
    for app in a11y.apps():
        if (app.get_name() or "") != "xdg-desktop-portal-kde":
            continue
        for j in range(app.get_child_count()):
            w = app.get_child_at_index(j)
            if (w.get_name() or "") != "Remote Control":
                continue
            for _, n in a11y.walk(w):
                if n.get_role_name() == "button" and n.get_name() == "Approve":
                    return bool(a11y.do_action(n, ("Press",)))
    return False


def analyse(rep: dict, typed: str) -> dict:
    ev = rep.get("events", [])
    inserted = "".join(e["v"] for e in ev if e["m"] == "TextChanged" and str(e["detail"]).startswith("insert"))
    names = [e["v"] for e in ev if e["m"] == "PropertyChange" and e["detail"] == "accessible-name"
             and "Kate" in e["v"]]
    saved = any("*" in a and "*" not in b for a, b in zip(names, names[1:]))
    return {"inserted_equals": inserted == typed, "inserted": inserted[:120], "keyboard_events":
            sum(1 for e in ev if e["i"] == "Keyboard"), "name_changes": names[-4:], "saved_seen": saved,
            "n_events": len(ev), "members": sorted({f"{e['i']}:{e['m']}:{e['detail']}" for e in ev})[:30]}


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    res = {"trials": []}
    out = b.base / "p4_results.json"
    home = Path(b.desc["home"])
    portal = kb = None
    try:
        b.up()
        a11y.init()
        addr = a11y_addr()
        for i in range(a.trials):
            doc = home / f"p4-{i}.txt"
            before = {a11y.app_pid(x) for x in a11y.apps()}
            k = b.procs.start(f"p4-kate-{i}", ["/usr/bin/kate", str(doc)],
                              b.wenv(QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1"), stdout=b.out("p4"), stderr=-2)
            time.sleep(5.0)
            kate = app_by_name("kate")
            kpid = a11y.app_pid(kate) if kate is not None else -1
            if portal is None:                          # one portal session for all trials
                portal = ei_input.Portal()
                fd = portal.connect(approve, timeout=20)
                kb = ei_input.Keyboard(fd)
                res["keyboard_ready"] = kb.ready(10)
                res["portal"] = portal.events
            kbus = bus_names_by_pid(addr).get(kpid)
            o = b.base / f"p4-{i}.json"
            args = ["--addr", addr, "--seconds", "9", "--out", str(o), "--app-bus", kbus or "", "--sender",
                    kbus or ""]
            for e in EVENTS:
                args += ["--event", e]
            rp = subprocess.Popen(["/usr/bin/python3", "-I", "-B", str(HERE / "rec_probe.py"), *args],
                                  env=dict(b.env), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            t1 = time.monotonic()
            while not Path(str(o) + ".ready").exists() and time.monotonic() - t1 < 10:
                time.sleep(0.05)
            time.sleep(0.5)
            text = TEXTS[i % len(TEXTS)]
            kb.type(text)
            time.sleep(0.5)
            kb.tap("Ctrl", "s")
            rp.wait(30)
            rep = json.loads(o.read_text()) if o.exists() else {}
            got = doc.read_text().rstrip("\n") if doc.exists() else None
            r = {"i": i, "typed": text, "file_equals": got == text, "file": got, "kate_bus": kbus}
            r.update(analyse(rep, text))
            res["trials"].append(r)
            for pid in {a11y.app_pid(x) for x in a11y.apps() if (x.get_name() or "") == "kate"} - before:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
            b.procs.stop_one(k)
            time.sleep(1.0)
    except Exception as e:                              # noqa: BLE001
        import traceback
        res["fatal"] = traceback.format_exc()
    finally:
        if kb is not None:
            kb.close()
        if portal is not None:
            portal.close()
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
    rc = benchmod.reexec_inside(desc, ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside",
                                       "--trials", str(a.trials)])
    print(f"results: {desc['base']}/p4_results.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
