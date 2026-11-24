# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F1: what the KWin reader script reports against an oracle that does not use it.

Oracle: (1) every test program reports its own PID and its windows' titles, colours and declared parents;
(2) a ScreenCast frame of the virtual screen: the picture predicted from the reader's geometry and stacking order
(topmost window containing each pixel gives its colour) must equal the frame, pixel by pixel. «Keep above» is checked
against the director's plan and the frame (a keep-above window must not be covered by a normal one).
"""
import json
import os
import random
import signal
import subprocess
import time
from pathlib import Path

from .kwin_scripts import KWinScripts

HERE = Path(__file__).resolve().parent
READS_PER_SCENARIO = 5
SETTLE = 0.6                                           # seconds after the director before reading the frame


def palette(n: int, rng: random.Random) -> list:
    """n colours far apart (each channel a multiple of 51, never black: the empty screen is black)."""
    allc = [(r, g, b) for r in range(0, 256, 51) for g in range(0, 256, 51) for b in range(0, 256, 51)
            if (r, g, b) != (0, 0, 0)]
    return rng.sample(allc, n)


def make_scenario(k: int, rng: random.Random, W: int, H: int) -> dict:
    progs = []
    nprog = rng.randint(2, 6)
    counts = [rng.randint(1, 3) for _ in range(nprog)]
    cols = palette(sum(counts), rng)
    ci = 0
    plan = []
    for p in range(nprog):
        wins = []
        for j in range(counts[p]):
            title = f"n152-{k}-{p}-{j}"
            parent = 0 if (j > 0 and rng.random() < 0.5) else None
            wins.append({"title": title, "rgb": list(cols[ci]), "parent": parent})
            ci += 1
            w, h = rng.randint(120, 520), rng.randint(90, 380)
            plan.append({"title": title, "x": rng.randint(0, W - w), "y": rng.randint(0, H - h), "w": w, "h": h,
                         "above": rng.random() < 0.2})
        progs.append({"windows": wins})
    rng.shuffle(plan)                                  # the raise order
    return {"k": k, "programs": progs, "plan": plan}


def compare_frame(frame: bytes, W: int, H: int, ours: list, colour: dict) -> dict:
    """Paint the prediction (bottom to top) and count pixels that differ from the frame.

    Inside a reported window: the pixel must be that window's colour. Outside every reported window: the pixel must
    not be any of our colours. visible[i] = pixels where window i is seen, as predicted."""
    import numpy as np
    img = np.frombuffer(frame, dtype=np.uint8)[: W * H * 4].reshape(H, W, 4)[:, :, :3].astype(np.int32)
    code = img[:, :, 0] * 65536 + img[:, :, 1] * 256 + img[:, :, 2]
    pred = np.zeros((H, W), dtype=np.int32)            # 0 = none of ours; i+1 = index into ours
    for i, w in enumerate(ours):                       # stacking order: bottom first
        x, y, ww, hh = (int(round(v)) for v in w["frame"])
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + ww), min(H, y + hh)
        if x1 > x0 and y1 > y0:
            pred[y0:y1, x0:x1] = i + 1
    want = np.full(len(ours) + 1, -1, dtype=np.int32)
    for i, w in enumerate(ours):
        r, g, b = colour[w["caption"]]
        want[i + 1] = r * 65536 + g * 256 + b
    inside = pred > 0
    bad_in = int(np.count_nonzero(inside & (code != want[pred])))
    ourcodes = np.array(sorted({r * 65536 + g * 256 + b for r, g, b in colour.values()}), dtype=np.int32)
    bad_out = int(np.count_nonzero(~inside & np.isin(code, ourcodes)))
    visible = [int(np.count_nonzero((pred == i + 1) & (code == want[i + 1]))) for i in range(len(ours))]
    return {"bad_pixels": bad_in + bad_out, "bad_inside": bad_in, "bad_outside": bad_out,
            "covered": int(np.count_nonzero(inside)), "visible": visible,
            "hidden_windows": sum(1 for v in visible if v == 0)}


def start_programs(bench, sc: dict, wd: Path) -> list:
    out = []
    for i, prog in enumerate(sc["programs"]):
        ready = wd / f"ready-{sc['k']}-{i}.json"
        p = bench.procs.start(f"testwin-{sc['k']}-{i}",
                              ["/usr/bin/python3", "-I", "-B", str(HERE / "testwin.py"), "--spec", json.dumps(prog),
                               "--ready", str(ready)],
                              bench.wenv(), stdout=bench.out("testwin"), stderr=subprocess.STDOUT)
        out.append((p, ready))
    t0 = time.monotonic()
    while time.monotonic() - t0 < 20 and not all(r.exists() for _, r in out):
        time.sleep(0.05)
    return out


def stop_programs(bench, progs: list) -> None:
    for p, _ in progs:
        bench.procs.stop_one(p)
    bench.procs.items = [(n, q) for n, q in bench.procs.items if all(q is not p for p, _ in progs)]


def grab(serve_pid: int, path: Path, timeout: float = 5.0) -> bytes:
    meta = Path(str(path) + ".json")
    old = meta.stat().st_mtime_ns if meta.exists() else 0
    os.kill(serve_pid, signal.SIGUSR1)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if meta.exists() and meta.stat().st_mtime_ns != old:
            return path.read_bytes()
        time.sleep(0.02)
    return b""


def check_scenario(sc: dict, progs_ready: list, reads: list, frame: bytes, W: int, H: int) -> dict:
    truth = {}                                         # caption -> (pid, rgb, parent caption)
    for p, ready in progs_ready:
        try:
            r = json.loads(ready.read_text())
        except (OSError, ValueError):
            continue
        for w in r["windows"]:
            par = r["windows"][w["parent"]]["title"] if w.get("parent") is not None else None
            truth[w["title"]] = (r["pid"], w["rgb"], par)
    plan = {p["title"]: p for p in sc["plan"]}
    res = {"k": sc["k"], "n_windows": len(plan), "n_programs": len(sc["programs"]), "errors": []}
    first = reads[0]
    if first is None:
        res["errors"].append("no reader answer")
        return res
    ours = [w for w in first["windows"] if w["caption"] in plan]
    ids = {w["id"]: w["caption"] for w in first["windows"]}
    if {w["caption"] for w in ours} != set(plan):
        res["errors"].append(f"windows missing in reader: {sorted(set(plan) - {w['caption'] for w in ours})}")
    pid_bad = trans_bad = above_bad = 0
    for w in ours:
        pid, rgb, par = truth.get(w["caption"], (None, None, None))
        if w["pid"] != pid:
            pid_bad += 1
        reported_par = ids.get(w["transientFor"]) if w["transientFor"] else None
        if bool(w["transient"]) != (par is not None) or reported_par != par:
            trans_bad += 1
        if bool(w["keepAbove"]) != bool(plan[w["caption"]]["above"]):
            above_bad += 1
    # stability: the same answer in every read of the scenario (nobody moved anything between reads)
    sig = [json.dumps([(w["id"], w["frame"], w["keepAbove"]) for w in r["windows"]]) if r else None for r in reads]
    cursor = [tuple(r["cursor"].values()) if r else None for r in reads]
    colour = {c: truth[c][1] for c in truth}
    cmp = compare_frame(frame, W, H, ours, colour) if frame else {"bad_pixels": None}
    # the oracle is not blind: the same windows in reverse order must disagree with the frame where they overlap
    rev = compare_frame(frame, W, H, list(reversed(ours)), colour)["bad_pixels"] if frame else None
    res["reversed_bad_pixels"] = rev
    res["n_transient"] = sum(1 for c in truth.values() if c[2] is not None)
    res["n_above"] = sum(1 for p in sc["plan"] if p["above"])
    # keep above: no normal window above a keep-above one in the reported order, among ours
    order_ok = True
    seen_above = False
    for w in ours:
        if w["keepAbove"]:
            seen_above = True
        elif seen_above:
            order_ok = False
    res.update({"pid_bad": pid_bad, "transient_bad": trans_bad, "above_bad": above_bad,
                "stack_layers_ok": order_ok, "stable_reads": len(set(sig)) == 1, "cursor": cursor[0],
                "pixels": cmp, "geometry_vs_plan": sum(1 for w in ours if [round(v) for v in w["frame"]] !=
                                                      [plan[w["caption"]][k] for k in ("x", "y", "w", "h")])})
    return res


def run(bench, n: int, seed: int, log, serve_pid: int, frame_path: Path) -> dict:
    rng = random.Random(seed)
    W, H = bench.desc["width"], bench.desc["height"]
    wd = bench.base / "f1"
    ks = KWinScripts(wd / "scripts")
    results, lat = [], []
    for k in range(n):
        sc = make_scenario(k, rng, W, H)
        progs = start_programs(bench, sc, wd)
        try:
            d, _ = ks.direct(sc["plan"])
            if d and d.get("missing"):                 # a window still mapping: one more try
                time.sleep(0.5)
                d, _ = ks.direct(sc["plan"])
            time.sleep(SETTLE)
            reads = []
            for _ in range(READS_PER_SCENARIO):
                r, dt = ks.read()
                reads.append(r)
                if dt is not None:
                    lat.append(dt)
            frame = grab(serve_pid, frame_path)
            res = check_scenario(sc, progs, reads, frame, W, H)
            res["director_missing"] = d.get("missing") if d else "no answer"
            results.append(res)
            log(f"F1 k={k} {json.dumps({x: res.get(x) for x in ('pid_bad', 'transient_bad', 'above_bad', 'stack_layers_ok')})} px={res.get('pixels', {}).get('bad_pixels')}")
        finally:
            stop_programs(bench, progs)
            time.sleep(0.2)
    return {"scenarios": results, "latency_s": lat, "seed": seed}
