# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 phase 0 on the bench (§13.1, §14.1): F1, F2, F7, F9, F13, F14, all as the calling user, no root, no input
but the bench's AT-SPI consent, never the real session.

    /usr/bin/python3 -I -B sys/core/desk/bench/run_phase0.py --scratch DIR [--only F1,F7] [--quick] [--seed N]

Writes DIR/run-*/results.json; prints one line per test. Refuses to start next to the owner's session (guard.py).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # sys/core

from desk.bench import bench as benchmod  # noqa: E402
from desk.bench import guard  # noqa: E402

HERE = Path(__file__).resolve().parent
FULL = {"F1": 200, "F2a": 100, "F2b": 20, "F7": (300, 100, 300, 100), "F9": (30, 10, 3), "F13": (100, 10),
        "F14": 50}
QUICK = {"F1": 3, "F2a": 3, "F2b": 2, "F7": (10, 5, 10, 3), "F9": (2, 3, 1), "F13": (2, 1), "F14": 2}


def gpu_mem() -> list:
    try:
        out = subprocess.run(["/usr/bin/nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20, env={"PATH": "/usr/bin:/bin"}).stdout
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        return ["nvidia-smi not available"]


def outer(a) -> int:
    missing = benchmod.which_missing()
    hard = [m for m in missing if m != "qrencode"]
    print(f"missing: {missing or 'none'}")
    if hard:
        print("the bench cannot start without these; nothing done")
        return 2
    real_before = guard.real_sockets()
    gpu_before = gpu_mem()
    desc = benchmod.prepare(Path(a.scratch))
    (Path(desc["base"]) / "outer.json").write_text(json.dumps({"real_before": real_before, "gpu_before": gpu_before,
                                                               "missing": missing}))
    argv = ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside", "--seed", str(a.seed)]
    if a.only:
        argv += ["--only", a.only]
    if a.quick:
        argv += ["--quick"]
    rc = benchmod.reexec_inside(desc, argv)
    real_after = guard.real_sockets()
    o = json.loads((Path(desc["base"]) / "outer.json").read_text())
    o.update({"real_after": real_after, "real_same": guard.same_real(real_before, real_after),
              "gpu_after": gpu_mem(), "inner_rc": rc})
    (Path(desc["base"]) / "outer.json").write_text(json.dumps(o))
    print(f"results: {desc['base']}/results.json  real wayland sockets unchanged: {o['real_same']}")
    return rc


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    n = QUICK if a.quick else FULL
    only = set(a.only.split(",")) if a.only else {"F1", "F2", "F7", "F9", "F13", "F14"}
    res = {"n": n, "seed": a.seed, "started": time.time(), "tests": {}}
    out = b.base / "results.json"

    def log(msg):
        b.log(msg)
        print(msg, flush=True)

    def save():
        out.write_text(json.dumps(res))

    consent = b.base / "consent.jsonl"
    try:
        res["bench_up"] = b.up()
        res["bench_alive"] = b.alive()
        b.procs.start("consent", ["/usr/bin/python3", "-I", "-B", str(HERE / "consent.py"), "--log", str(consent)],
                      b.wenv(), stdout=b.out("consent"), stderr=subprocess.STDOUT)
        time.sleep(1.0)
        if "F7" in only:
            res["tests"]["F7"] = run_f7(b, *n["F7"])
            save()
        if "F9" in only:
            from desk.bench import f9
            res["tests"]["F9"] = f9.run(b, *n["F9"], log)
            save()
        if "F1" in only:
            res["tests"]["F1"] = run_f1(b, n["F1"], a.seed, log)
            save()
        if "F2" in only:
            from desk.bench import f2_f14
            res["tests"]["F2"] = f2_f14.run_f2(b, consent, n["F2a"], n["F2b"], log)
            save()
        if "F14" in only:
            from desk.bench import f2_f14
            res["tests"]["F14"] = f2_f14.run_f14(b, consent, n["F14"], log)
            save()
        if "F13" in only:
            from desk.bench import f13
            res["tests"]["F13"] = f13.run(b, *n["F13"], log)
            save()
        b.check_real()
        res["unreadable_fd_pids"] = sorted(set(b.unreadable))
    except guard.BenchRefused as e:
        res["refused"] = str(e)
        log(f"REFUSED: {e}")
    finally:
        res["consent_events"] = sum(1 for x in consent.read_text().splitlines() if '"dialog"' in x) \
            if consent.exists() else 0
        res["down"] = b.down()
        res["finished"] = time.time()
        save()
    return 0 if "refused" not in res else 3


def run_f7(b, n_child: int, n_grand: int, n_stranger: int, cycles: int) -> dict:
    sock = b.rt / "f7.sock"
    out = b.base / "f7.json"
    ready = b.base / "f7.ready"
    f7 = str(HERE / "f7.py")
    srv = b.procs.start("f7-server", ["/usr/bin/python3", "-I", "-B", f7, "server", str(sock), str(out),
                                      str(n_child), str(n_grand), str(n_stranger), str(cycles), str(ready)],
                        b.wenv(), stdout=b.out("f7"), stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while not ready.exists() and time.monotonic() - t0 < 20:
        time.sleep(0.02)
    st = b.procs.start("f7-stranger", ["/usr/bin/python3", "-I", "-B", f7, "stranger", str(sock), str(n_stranger)],
                       b.wenv(), stdout=b.out("f7"), stderr=subprocess.STDOUT)
    st.wait(timeout=300)
    srv.wait(timeout=900)
    return json.loads(out.read_text())


def run_f1(b, n: int, seed: int, log) -> dict:
    from desk.bench import f1
    ready, fp = b.base / "serve.ready", b.base / "frame.raw"
    srv = b.procs.start("f1-serve", ["/usr/bin/python3", "-I", "-B", str(HERE / "probe_capture.py"), "--out",
                                     str(b.base / "serve.json"), "--serve", str(ready), "--save-frame", str(fp)],
                        b.wenv(), stdout=b.out("serve"), stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    while not ready.exists() and time.monotonic() - t0 < 30:
        time.sleep(0.1)
    if not ready.exists():
        return {"error": "no ScreenCast stream for the oracle", "serve": (b.base / "serve.json").read_text()
                if (b.base / "serve.json").exists() else None}
    r = f1.run(b, n, seed, log, srv.pid, fp)
    b.procs.stop_one(srv)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed", type=int, default=20261124)
    ap.add_argument("--inside", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    if not a.scratch:
        ap.error("--scratch DIR is required (temporary files of the bench)")
    return outer(a)


if __name__ == "__main__":
    sys.exit(main())
