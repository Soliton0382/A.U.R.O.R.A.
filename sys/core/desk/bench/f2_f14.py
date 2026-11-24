# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F2 (consent dialog at every persist_mode = 0 session; Registry name) and F14 (dumpable 0 and capture; sibling
attacks on a dumpable 1 client). Sessions are probe_capture.py processes; dialogs come from consent.py's log, matched
by time to the session's Start call: a Start answered with success and no dialog in its window = a session without
consent (the stop condition of F2 a)."""
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ID = "org.aurora.desk"
APP_NAME = "Aurora Desk Banco"                          # Name= of the bench's .desktop file for APP_ID


def consent_events(log: Path) -> list:
    try:
        return [json.loads(x) for x in log.read_text().splitlines() if '"dialog"' in x]
    except OSError:
        return []


def one(bench, tag: str, consent_log: Path, dumpable: str = "1", register: str = "", attack: bool = False) -> dict:
    wd = bench.base / "portal"
    wd.mkdir(exist_ok=True)
    out = wd / f"{tag}.json"
    argv = ["/usr/bin/python3", "-I", "-B", str(HERE / "probe_capture.py"), "--out", str(out), "--dumpable",
            dumpable, "--timeout", "20", "--hold", "1.0" if attack else "0"]
    if register:
        argv += ["--register", register]
    p = bench.procs.start(f"probe-{tag}", argv, bench.wenv(), stdout=bench.out("probe"), stderr=subprocess.STDOUT)
    atk = None
    if attack:
        time.sleep(0.4)                                # the target is alive (portal calls, then 1 s of hold)
        if p.poll() is None:
            a = subprocess.run(["/usr/bin/python3", "-I", "-B", str(HERE / "attack.py"), str(p.pid)],
                               env=bench.wenv(), capture_output=True, text=True, timeout=30)
            try:
                atk = json.loads(a.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                atk = {"error": a.stderr[-300:]}
            try:
                st = Path(f"/proc/{p.pid}/status").read_text()
                atk["target_tracer"] = next((ln.split()[1] for ln in st.splitlines()
                                             if ln.startswith("TracerPid:")), "?")
            except OSError:
                atk["target_tracer"] = "gone"
        else:
            atk = {"error": "target already gone"}
    try:
        p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        bench.procs.stop_one(p)
    try:
        r = json.loads(out.read_text())
    except (OSError, ValueError):
        r = {"error": "no result file"}
    st = r.get("start") or {}
    t0, t1 = r.get("t_start_call"), st.get("t_answer")
    dialogs = []
    if t0 and t1:
        dialogs = [e for e in consent_events(consent_log) if t0 - 0.05 <= e["t"] <= t1 + 0.05]
    return {"tag": tag, "pid": r.get("pid"), "dumpable": r.get("dumpable"), "register": r.get("register"),
            "create": (r.get("create") or {}).get("code"), "select": (r.get("select") or {}).get("code"),
            "start": st.get("code"), "start_s": st.get("s"), "restore_token": st.get("restore_token"),
            "frames": (r.get("capture") or {}).get("frames", 0), "error": r.get("error"),
            "dialogs": len(dialogs), "titles": [d["title"] for d in dialogs],
            "restore_box": [d.get("restore") for d in dialogs], "attack": atk}


def run_f2(bench, consent_log: Path, n_a: int, n_b: int, log) -> dict:
    a, b = [], []
    for i in range(n_a):
        r = one(bench, f"f2a-{i}", consent_log)
        a.append(r)
        log(f"F2a {i} start={r['start']} dialogs={r['dialogs']} token={r['restore_token']}")
    for i in range(n_b):
        r = one(bench, f"f2b-{i}", consent_log, register=APP_ID)
        r["name_shown"] = any(APP_NAME in t for t in r["titles"])
        b.append(r)
        log(f"F2b {i} register={r['register']} titles={r['titles']}")
    return {"a": a, "b": b, "app_id": APP_ID, "app_name": APP_NAME}


def run_f14(bench, consent_log: Path, n: int, log) -> dict:
    d0, d1 = [], []
    for i in range(n):
        r = one(bench, f"f14d0-{i}", consent_log, dumpable="0")
        d0.append(r)
        log(f"F14 d0 {i} dumpable={r['dumpable']} start={r['start']} frames={r['frames']} err={r['error']}")
    for i in range(n):
        r = one(bench, f"f14d1-{i}", consent_log, dumpable="1", attack=True)
        d1.append(r)
        log(f"F14 d1 {i} frames={r['frames']} attack={json.dumps(r['attack'])[:160]}")
    ctrl = []
    for i in range(10):
        a = subprocess.run(["/usr/bin/python3", "-I", "-B", str(HERE / "attack.py"), "--self-test"],
                           env=bench.wenv(), capture_output=True, text=True, timeout=30)
        try:
            ctrl.append(json.loads(a.stdout.strip().splitlines()[-1]))
        except (ValueError, IndexError):
            ctrl.append({"error": a.stderr[-300:]})
    return {"dumpable0": d0, "dumpable1": d1, "ancestor_control": ctrl}
