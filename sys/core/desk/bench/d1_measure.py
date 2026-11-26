# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1, test D1 (+D5) on the virtual bench (design bozza 8 §8, §10 (a)): a demonstration with real keys,
recorded by a recorder process without libatspi (desk/app/recorder.py), turned into a draft (desk/app/draft.py),
checked as a personal procedure (library_check, ns per), then run again on the bench with real keys and NEW values:
the metric is the outcome (the file's text, the result read), not the anchors.

Variants: kate-menu (type, Alt+F, s), kate-shortcut (type, Ctrl+S), kcalc (type, Enter).
    python3 -I -B d1_measure.py --scratch DIR [--trials 10]          results in DIR/run-*/d1_results.json"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1]
sys.path.insert(0, str(CORE))

from desk import library_check  # noqa: E402
from desk.app import draft, recorder  # noqa: E402
from desk.bench import a11y, bench as benchmod, ei_input, lib_run  # noqa: E402
from desk.bench.p4_measure import approve  # noqa: E402
from desk.bench.p_measure import bus_names_by_pid  # noqa: E402

TEXTS = ["Lista: mele e pane", "Nota del giorno 3", "Prova (uno) e due", "a, b; c.", "Tre parole qui",
         "Riga numero 6", "Fine? Forse!", "MAIUSCOLE e minuscole", "x = 7 + 8", "Ultima riga 10"]
TEXTS2 = ["Altro testo 1", "Seconda prova", "Cento e uno", "Nuova nota", "Ancora una",
          "Sei di sei", "Sette volte", "Otto righe", "Nove (9)", "Dieci finale"]
EXPRS = [("12+30", "42"), ("7*8", "56"), ("100-58", "42"), ("81/9", "9"), ("(2+3)*4", "20"),
         ("9-4", "5"), ("6*7", "42"), ("50/2", "25"), ("11+11", "22"), ("3*3*3", "27")]
EXPRS2 = [("2+2", "4"), ("10*10", "100"), ("90-45", "45"), ("64/8", "8"), ("(1+1)*5", "10"),
          ("8-3", "5"), ("4*5", "20"), ("30/3", "10"), ("13+7", "20"), ("2*2*2", "8")]
FOLDERS = ["Ricette", "Foto estate", "Lavoro 2026", "Bollette", "Musica", "Documenti vari", "Viaggi",
           "Scuola", "Progetti", "Archivio"]
FOLDERS2 = ["Note", "Contratti", "Fatture", "Video", "Libri", "Disegni", "Salute", "Casa", "Auto", "Varie"]
ENV_IT = {"LANG": "it_IT.UTF-8", "LC_ALL": "it_IT.UTF-8", "LANGUAGE": "it", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1"}


def frame_of(addr: str, bus: str) -> str:
    app = recorder.App(recorder.connect(addr), bus)
    for p in app.children("/org/a11y/atspi/accessible/root"):
        if app.info(p).get("role") == "frame":
            return p
    return ""


def demonstrate(b, kb_holder, name: str, argv: list, actions: list, app_names: tuple = (), wait_s: float = 5.0) -> dict:
    """The «person»: real keys only. Returns the recorder's output (from its own process). app_names: the names the
    program gives itself on the accessibility bus when not its file's (LibreOffice); wait_s: how long it may take."""
    before = {a11y.app_pid(x) for x in a11y.apps()}
    p = b.procs.start(f"d1-{name}", argv, b.wenv(**ENV_IT), stdout=b.out("d1"), stderr=-2)
    time.sleep(5.0)
    names = {os.path.basename(argv[0]), *app_names}
    t_end = time.monotonic() + max(0.0, wait_s - 5.0)
    while time.monotonic() < t_end and not any(a11y.app_pid(x) not in before and x.get_name() in names
                                               for x in a11y.apps()):
        time.sleep(0.5)
    if "kb" not in kb_holder:
        pt = ei_input.Portal()
        kb = ei_input.Keyboard(pt.connect(approve, timeout=20))
        kb.ready(10)
        kb_holder.update(pt=pt, kb=kb)
    app = next((x for x in a11y.apps() if a11y.app_pid(x) not in before and x.get_name() in names), None)
    if app is None:
        raise RuntimeError(f"no window of {sorted(names)}; new apps seen: "
                           f"{sorted(x.get_name() for x in a11y.apps() if a11y.app_pid(x) not in before)}")
    prog = app.get_name()
    addr = recorder.a11y_address()
    bus = bus_names_by_pid(addr)[a11y.app_pid(app)]
    frame = frame_of(addr, bus)
    tmp = Path(tempfile.mkdtemp(dir=b.base))
    out, stop = tmp / "rec.json", tmp / "stop"
    rp = subprocess.Popen(["/usr/bin/python3", "-I", "-B", str(CORE / "desk/app/recorder.py"), "--addr", addr,
                           "--app-bus", bus, "--frame", frame, "--out", str(out), "--stop", str(stop)],
                          env=dict(b.env), stdout=subprocess.DEVNULL, stderr=b.out("d1rec"))
    t0 = time.monotonic()
    while not Path(str(out) + ".ready").exists() and time.monotonic() - t0 < 10:
        time.sleep(0.05)
    time.sleep(0.4)
    kb = kb_holder["kb"]
    for act in actions:
        if act[0] == "type":
            kb.type(act[1])
        else:
            kb.tap(*act[1:])
        time.sleep(0.6)
    time.sleep(1.5)
    stop.write_text("stop")
    rp.wait(20)
    rec = json.loads(out.read_text()) if out.exists() else {"events": [], "counters": {}}
    for pid in {a11y.app_pid(x) for x in a11y.apps() if x.get_name() == prog} - before:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
    b.procs.stop_one(p)
    time.sleep(1.0)
    return rec


def trial(b, kb_holder, variant: str, i: int, home: Path) -> dict:
    r = {"variant": variant, "i": i}
    if variant.startswith("kate"):
        f_demo = home / f"d1-{variant}-{i}-demo.txt"
        acts = [("type", TEXTS[i])] + ([("tap", "Alt", "f"), ("tap", "s")] if variant == "kate-menu"
                                       else [("tap", "Ctrl", "s")])
        rec = demonstrate(b, kb_holder, f"{variant}-{i}", ["/usr/bin/kate", str(f_demo)], acts)
        prog = {"name": "kate", "package": "kate", "exe": "/usr/bin/kate", "version": "4:25.12",
                "args": [str(f_demo)]}
        r["demo_file_ok"] = f_demo.exists() and f_demo.read_text().rstrip("\n") == TEXTS[i]
    elif variant == "dolphin":
        lav = home / f"d1-dolphin-{i}-demo"
        lav.mkdir(exist_ok=True)
        rec = demonstrate(b, kb_holder, f"dolphin-{i}", ["/usr/bin/dolphin", "--new-window", str(lav)],
                          [("tap", "F10"), ("tap", "Down"), ("tap", "Right"), ("tap", "Enter"),
                           ("type", FOLDERS[i]), ("tap", "Enter")])
        prog = {"name": "dolphin", "package": "dolphin", "exe": "/usr/bin/dolphin", "version": "4:25.12",
                "args": ["--new-window", str(lav)]}
        r["demo_file_ok"] = (lav / FOLDERS[i]).is_dir()
    else:
        e, _ = EXPRS[i]
        rec = demonstrate(b, kb_holder, f"kcalc-{i}", ["/usr/bin/kcalc"], [("type", e), ("tap", "Enter")])
        prog = {"name": "kcalc", "package": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12", "args": []}
    r["counters"] = rec.get("counters")
    d = draft.build(rec.get("events", []), prog, loc="it", network=False)
    proc = d["procedure"]
    proc["id"] = f"per:linux/{prog['name']}/d1-{variant}-{i}"
    r["steps"] = [(s["do"], s.get("keys") or s.get("target", {}).get("id_end", "")[-30:]) for s in proc["steps"]]
    r["flags"] = d["flags"]
    r["examples"] = d["examples"]
    root = b.base / "per"
    pf = root / "linux" / prog["name"] / f"d1-{variant}-{i}.json"
    pf.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(proc, ensure_ascii=False)
    pf.write_text(raw)
    r["check"] = library_check.check(pf, root, ns="per")
    # the outcome with NEW values
    work = home / "lavoro"
    work.mkdir(exist_ok=True)
    params = {}
    texts = [k for k in proc["params"] if proc["params"][k]["kind"] == "text"]
    if variant == "dolphin":
        new_dir = work / f"d1-dolphin-{i}-replay"
        new_dir.mkdir(exist_ok=True)
        params = {"f1": str(new_dir)}
        if texts:
            params[texts[0]] = FOLDERS2[i]
        want = FOLDERS2[i]
    elif variant.startswith("kate"):
        new_file = work / f"d1-{variant}-{i}-replay.txt"
        params = {"f1": str(new_file)}
        if texts:
            params[texts[0]] = TEXTS2[i]
        want = TEXTS2[i]
    else:
        if texts:
            params[texts[0]] = EXPRS2[i][0]
        want = EXPRS2[i][1]
    lib_run.KEYS.update(kb=kb_holder["kb"])
    rr = lib_run.run_one(b, proc, params, "it", work)
    r["replay_ok"] = rr.get("ok")
    r["replay_error"] = rr.get("error")
    r["replay_steps"] = [(x["n"], x["do"], x.get("ok"), x.get("via"), x.get("error", "")) for x in rr["steps"]]
    bad = next((x for x in rr["steps"] if not x.get("ok")), None)
    if bad:
        r["replay_dump"] = [d for d in (bad.get("dump") or []) if "menu" in d or "dialog" in d or "button" in d][:60]
    if variant == "dolphin":
        made = sorted(x.name for x in new_dir.iterdir() if x.is_dir())
        got = made[0] if len(made) == 1 else made
    elif variant.startswith("kate"):
        got = new_file.read_text().rstrip("\n") if new_file.exists() else None
    else:
        got = next((s.get("read") for s in rr["steps"] if s["do"] == "read"), None)
    r["got"], r["want"] = got, want
    r["outcome_ok"] = got == want
    return r


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    res = {"trials": []}
    out = b.base / "d1_results.json"
    home = Path(b.desc["home"])
    kb_holder = {}
    try:
        b.up()
        a11y.init()
        from gi.repository import Atspi
        Atspi.set_timeout(2000, 15000)
        for variant in (a.variants or "kate-menu,kate-shortcut,kcalc").split(","):
            for i in range(a.trials):
                try:
                    res["trials"].append(trial(b, kb_holder, variant, i, home))
                except Exception as e:                  # noqa: BLE001
                    import traceback
                    res["trials"].append({"variant": variant, "i": i, "fatal": traceback.format_exc()[-800:]})
                out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    except Exception:                                   # noqa: BLE001
        import traceback
        res["fatal"] = traceback.format_exc()
    finally:
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        if kb_holder.get("kb"):
            kb_holder["kb"].close()
            kb_holder["pt"].close()
        b.down()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(benchmod.default_scratch()))
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--variants", default="")
    ap.add_argument("--inside", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    desc = benchmod.prepare(Path(a.scratch))
    rc = benchmod.reexec_inside(desc, ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside",
                                       "--trials", str(a.trials), "--variants", a.variants])
    print(f"results: {desc['base']}/d1_results.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
