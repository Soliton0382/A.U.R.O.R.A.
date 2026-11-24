# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1, tests D2 (protected fields), D3 (the filter) and D4 (the accessibility switch put back) on the
virtual bench with real keys and the real dconf backend inside the bench HOME (never the owner's).

D2: Qt (password echo, and a plain field named «Codice OTP») and GTK 3 (visibility off); a canary typed in each, and a
    control canary in a plain field. Looked for in the recorder's output, in the draft, in all the traffic the
    recorder process read (strace) and in its memory (/proc/<pid>/mem) just before it stops.
D3: (a) a canary typed in another program; (b) a canary typed in a second window of the same program.
D4: the switch on, then the app killed (SIGKILL); the owner's own «on» before; a change meanwhile; the bus launcher
    restarted (a logout or a reboot) — then a new process puts it back.
    python3 -I -B d234_measure.py --scratch DIR [--trials 25] [--d4 20]       results in DIR/run-*/d234_results.json"""
import argparse
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1]
sys.path.insert(0, str(CORE))

from desk.app import draft, recorder  # noqa: E402
from desk.bench import a11y, bench as benchmod, ei_input  # noqa: E402
from desk.bench.p4_measure import approve  # noqa: E402
from desk.bench.p_measure import a11y_addr, bus_names_by_pid, gget, is_enabled  # noqa: E402

PY = ["/usr/bin/python3", "-I", "-B"]
ENV_APP = {"LANG": "it_IT.UTF-8", "LC_ALL": "it_IT.UTF-8", "LANGUAGE": "it", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1"}


def start_app(b, mode: str, tag: str):
    ready = b.base / f"ready-{tag}"
    p = b.procs.start(f"d2-{tag}", PY + [str(HERE / "d2_apps.py"), mode, "--ready", str(ready)], b.wenv(**ENV_APP),
                      stdout=b.out("d2"), stderr=-2)
    t0 = time.monotonic()
    while not ready.exists() and time.monotonic() - t0 < 20:
        time.sleep(0.1)
    time.sleep(2.0)
    return p


def app_of(pid: int):
    for _ in range(50):
        for x in a11y.apps():
            if a11y.app_pid(x) == pid and x.get_child_count():
                return x
        time.sleep(0.2)
    return None


def frame_path(addr: str, bus: str, title: str) -> str:
    app = recorder.App(recorder.connect(addr), bus)
    for p in app.children("/org/a11y/atspi/accessible/root"):
        i = app.info(p)
        if i.get("name") == title:                       # a plain Qt window is a «filler», not a «frame»
            return p
    return ""


def field(app, name: str):
    for _, n in a11y.walk(app, limit=5000):
        try:
            if n.get_name() == name and n.get_role_name() in ("text", "password text", "entry"):
                return n
        except Exception:                               # noqa: BLE001
            continue
    return None


def start_rec(b, addr: str, bus: str, frame: str, tag: str) -> dict:
    out, stop, st = b.base / f"rec-{tag}.json", b.base / f"stop-{tag}", b.base / f"rec-{tag}.strace"
    p = subprocess.Popen(["/usr/bin/strace", "-f", "-qq", "-s", "200000", "-e", "trace=read,recvmsg,recvfrom,readv",
                          "-o", str(st)] + PY + [str(CORE / "desk/app/recorder.py"), "--addr", addr, "--app-bus",
                                                 bus, "--frame", frame, "--out", str(out), "--stop", str(stop)],
                         env=dict(b.env), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.monotonic()
    while not Path(str(out) + ".ready").exists() and time.monotonic() - t0 < 15:
        time.sleep(0.05)
    time.sleep(0.4)
    return {"p": p, "out": out, "stop": stop, "strace": st}


def child_pid(strace_pid: int) -> int:
    for t in Path(f"/proc/{strace_pid}/task").iterdir():
        kids = (t / "children").read_text().split()
        if kids:
            return int(kids[0])
    return -1


def in_memory(pid: int, needles: list) -> dict:
    found = {n: False for n in needles}
    try:
        maps = Path(f"/proc/{pid}/maps").read_text().splitlines()
        with open(f"/proc/{pid}/mem", "rb", 0) as mem:
            for line in maps:
                m = re.match(r"([0-9a-f]+)-([0-9a-f]+) (r[w-])", line)
                if not m:
                    continue
                a, z = int(m.group(1), 16), int(m.group(2), 16)
                if z - a > 512 * 1024 * 1024:
                    continue
                try:
                    mem.seek(a)
                    chunk = mem.read(z - a)
                except OSError:
                    continue
                for n in needles:
                    if not found[n] and (n.encode() in chunk or n.encode("utf-16-le") in chunk):
                        found[n] = True
    except OSError as e:
        return {"error": str(e)}
    return found


def stop_rec(r: dict, needles: list) -> dict:
    pid = child_pid(r["p"].pid)
    mem = in_memory(pid, needles) if pid > 0 else {"error": "no child"}
    r["stop"].write_text("stop")
    r["p"].wait(30)
    out = r["out"].read_text() if r["out"].exists() else ""
    trace = r["strace"].read_text(errors="replace") if r["strace"].exists() else ""
    rec = json.loads(out) if out else {"events": [], "counters": {}}
    for f in (r["out"], r["stop"], r["strace"], Path(str(r["out"]) + ".ready")):
        if f.exists():
            f.unlink()
    return {"rec": rec, "out_text": out, "trace": trace, "mem": mem}


def canary(prefix: str) -> str:
    return prefix + secrets.token_hex(5).upper()


def d2_trial(b, kb, mode: str, i: int, addr: str, app, bus: str) -> dict:
    title = "Prova D2 Qt" if mode == "qt" else "Prova D2 GTK"
    fr = frame_path(addr, bus, title)
    fields = {"Nome": canary("NOMEC")}
    fields["Password"] = canary("PWDS")
    if mode == "qt":
        fields["Codice OTP"] = str(secrets.randbelow(9 * 10 ** 8) + 10 ** 8)
    r = start_rec(b, addr, bus, fr, f"d2-{mode}-{i}")
    from gi.repository import Atspi
    for name, val in fields.items():
        node = field(app, name)
        if node is None:
            raise RuntimeError(f"field {name} not found")
        Atspi.Component.grab_focus(node)
        time.sleep(0.25)
        kb.tap("Ctrl", "a")
        kb.type(val)
        time.sleep(0.3)
    time.sleep(0.8)
    got = stop_rec(r, list(fields.values()))
    d = draft.build(got["rec"].get("events", []), {"name": "d2", "exe": "/usr/bin/python3", "version": "1"},
                    network=False)
    dtext = json.dumps(d, ensure_ascii=False)
    res = {"mode": mode, "i": i, "counters": got["rec"].get("counters"),
           "marks": sum(1 for e in got["rec"].get("events", []) if e["kind"] == "Suppressed")}
    for name, val in fields.items():
        res[name] = {"output": val in got["out_text"], "draft": val in dtext,
                     "memory": got["mem"].get(val) if isinstance(got["mem"], dict) else None}
    return res


def d3_trial(b, kb, case: str, i: int, addr: str, ctx: dict) -> dict:
    from gi.repository import Atspi
    val = canary("ALTROC")
    if case == "other":                                  # record the Qt window; type in another program
        r = start_rec(b, addr, ctx["qt_bus"], frame_path(addr, ctx["qt_bus"], "Prova D2 Qt"), f"d3o-{i}")
        node = field(ctx["other_app"], "Testo")
    else:                                                # record window A; type in window B of the same program
        r = start_rec(b, addr, ctx["qt2_bus"], frame_path(addr, ctx["qt2_bus"], "Finestra A"), f"d3w-{i}")
        node = field(ctx["qt2_app"], "Testo B")
    Atspi.Component.grab_focus(node)
    time.sleep(0.25)
    kb.tap("Ctrl", "a")
    kb.type(val)
    time.sleep(1.0)
    try:
        landed = val in Atspi.Text.get_text(node, 0, Atspi.Text.get_character_count(node))
    except Exception:                                   # noqa: BLE001
        landed = None
    got = stop_rec(r, [val])
    d = draft.build(got["rec"].get("events", []), {"name": "d3", "exe": "/usr/bin/python3", "version": "1"},
                    network=False)
    return {"case": case, "i": i, "landed": landed, "output": val in got["out_text"], "draft": val in json.dumps(d), "memory": got["mem"].get(val) if isinstance(got["mem"], dict) else None,
            "counters": got["rec"].get("counters")}


def d4(b, n: int) -> dict:
    """Each case in fresh processes, as the app would be: store.a11y_on in one, store.a11y_restore in the next."""
    env = dict(b.env)
    pre = f"import sys; sys.path.insert(0, {str(CORE)!r}); from desk.app import store; "

    def run(code: str) -> str:
        r = subprocess.run(PY + ["-c", pre + code], env=env, capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()

    out = {"crash": [], "owner_on_before": [], "changed_meanwhile": [], "launcher_restart": []}
    for _ in range(n):
        b.set_a11y(False)
        run("store.a11y_on(); import os, signal; os.kill(os.getpid(), signal.SIGKILL)")
        mid = is_enabled()
        msg = run("print(store.a11y_restore())")
        out["crash"].append({"on_while": mid, "after": is_enabled(), "dconf": gget(env), "msg": msg})
        b.set_a11y(True)                                 # the owner's own «on» (a screen reader)
        run("store.a11y_on()")
        msg = run("print(store.a11y_restore())")
        out["owner_on_before"].append({"after": is_enabled(), "msg": msg})
        b.set_a11y(False)
        run("store.a11y_on()")
        b.set_a11y(False)                                # someone turned it off meanwhile
        msg = run("print(store.a11y_restore())")
        out["changed_meanwhile"].append({"after": is_enabled(), "msg": msg})
    for _ in range(n):
        b.set_a11y(False)
        run("store.a11y_on()")
        b.procs.stop_one(b.started["atspi"])             # the bus launcher goes (logout, reboot) and comes back
        time.sleep(0.5)
        b._start("atspi", [benchmod.ATSPI_LAUNCHER, "--launch-immediately"], dict(b.env))
        b.wait_name("org.a11y.Bus")
        time.sleep(0.5)
        came_back_on = is_enabled()
        msg = run("print(store.a11y_restore())")
        out["launcher_restart"].append({"came_back_on": came_back_on, "after": is_enabled(), "dconf": gget(env),
                                        "msg": msg})
    return out


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    res = {"D2": [], "D3": [], "D4": None}
    out = b.base / "d234_results.json"
    pt = kb = None
    try:
        b.up()
        a11y.init()
        from gi.repository import Atspi
        Atspi.set_timeout(2000, 15000)
        addr = a11y_addr()
        ctx = {}

        def up_app(mode):                                # one program at a time: it is the active window
            p = start_app(b, mode, f"{mode}-{len(ctx)}")
            ctx[mode + "_p"], ctx[mode + "_app"] = p, app_of(p.pid)
            ctx[mode + "_bus"] = bus_names_by_pid(addr).get(p.pid)
            return p

        def keyboard():
            nonlocal pt, kb
            if kb is None:
                pt = ei_input.Portal()
                kb = ei_input.Keyboard(pt.connect(approve, timeout=20))
                res["keyboard_ready"] = kb.ready(10)
            return kb

        for mode in ("qt", "gtk"):
            p = up_app(mode)
            k = keyboard()
            for i in range(a.trials):
                try:
                    res["D2"].append(d2_trial(b, k, mode, i, addr, ctx[mode + "_app"], ctx[mode + "_bus"]))
                except Exception as e:                  # noqa: BLE001
                    res["D2"].append({"mode": mode, "i": i, "fatal": repr(e)})
            b.procs.stop_one(p)
            time.sleep(1.0)
        up_app("qt")                                     # recorded window
        up_app("other")                                  # opened last: the active one, where the canary goes
        for i in range(a.trials):
            try:
                res["D3"].append(d3_trial(b, kb, "other", i, addr, ctx))
            except Exception as e:                      # noqa: BLE001
                res["D3"].append({"case": "other", "i": i, "fatal": repr(e)})
        b.procs.stop_one(ctx["other_p"])
        b.procs.stop_one(ctx["qt_p"])
        time.sleep(1.0)
        up_app("qt2")                                    # window B shown last: the active one
        for i in range(a.trials):
            try:
                res["D3"].append(d3_trial(b, kb, "window", i, addr, ctx))
            except Exception as e:                      # noqa: BLE001
                res["D3"].append({"case": "window", "i": i, "fatal": repr(e)})
        b.procs.stop_one(ctx["qt2_p"])
        res["buses"] = {k: v for k, v in ctx.items() if k.endswith("_bus")}
        out.write_text(json.dumps(res, indent=1))
        res["D4"] = d4(b, a.d4)
    except Exception:                                   # noqa: BLE001
        import traceback
        res["fatal"] = traceback.format_exc()
    finally:
        out.write_text(json.dumps(res, indent=1))
        if kb is not None:
            kb.close()
        if pt is not None:
            pt.close()
        b.down()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(benchmod.default_scratch()))
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--d4", type=int, default=20)
    ap.add_argument("--inside", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    desc = benchmod.prepare(Path(a.scratch))
    desc["env"]["GSETTINGS_BACKEND"] = "dconf"          # D4: the real backend, inside the bench HOME only
    rc = benchmod.reexec_inside(desc, PY + [str(Path(__file__).resolve()), "--inside", "--trials", str(a.trials),
                                            "--d4", str(a.d4)])
    print(f"results: {desc['base']}/d234_results.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
