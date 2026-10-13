#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Before a large benchmark (owner, 2026-10-13: «30 domande sono tante, quindi prima di avviarle dobbiamo avere
computer scarico, codice allineato e accesso cloud resettato… una volta raggiunto il limite bisogna aspettare il reset
settimanale»). Each condition measured, and a GO only when all hold:

    machine idle    the GPUs under 10% and no run under way in aurora-api, no other benchmark running
    code aligned    the code as the owner signed it (sys_ethics.code_drift): nothing changed since the signature
    cloud fresh     Claude Code's tokens of the last 7 days (the trace, measured) — the weekly window of the
                    subscription is not readable from here: the owner says when it was reset (--cloud-reset-on DATE),
                    and the tokens counted since then are shown

    python script/bench_preflight.py [--cloud-reset-on 2026-10-14]
Exit 0 = GO, 1 = not yet (each reason said).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora import mdl_router, sys_config, sys_ethics  # noqa: E402


def gpus_idle(limit: int = 10) -> tuple[bool, str]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True, "no NVIDIA GPU read (nvidia-smi missing): not a reason to wait"
    loads = [int(x.split(",")[1]) for x in out.strip().splitlines() if "," in x]
    return all(v < limit for v in loads), "GPU " + ", ".join(f"{i}: {v}%" for i, v in enumerate(loads))


def runs_idle(cfg) -> tuple[bool, str]:
    import httpx
    try:
        r = httpx.get(f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/v1/aurora/runs",
                      headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}, timeout=10)
        open_runs = [x["question"][:50] for x in r.json() if not x["done"]]
    except Exception as e:                                # noqa: BLE001
        return False, f"aurora-api not read ({e})"
    return not open_runs, f"{len(open_runs)} runs under way" + (f": {open_runs[:3]}" if open_runs else "")


def benches_idle() -> tuple[bool, str]:
    mine = os.getpid()
    others = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) == mine:
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "script/bench_" in cmd and "bench_preflight" not in cmd:
            others.append(cmd.split("script/")[-1][:60])
    return not others, f"{len(others)} benchmarks running" + (f": {others}" if others else "")


def code_aligned() -> tuple[bool, str]:
    d = sys_ethics.code_drift()
    s = sys_ethics.drift_summary(d)
    return not s, s or "the code as the owner signed it"


def cloud_since(cfg, reset_on: str | None) -> tuple[bool, str]:
    days = 7.0
    if reset_on:
        days = max(0.01, (dt.datetime.now() - dt.datetime.fromisoformat(reset_on)).total_seconds() / 86400)
    st = mdl_router.stats(cfg, days=days)
    cc = {k: v for k, v in st.get("calls", {}).items() if k.startswith("claude_code")} if isinstance(st.get("calls"), dict) else {}
    tokens = sum(v.get("in", 0) + v.get("out", 0) + v.get("cached", 0) for v in cc.values())
    calls = sum(v.get("calls", 0) for v in cc.values())
    since = f"since {reset_on}" if reset_on else "in the last 7 days"
    if not reset_on:
        return False, (f"Claude Code {since}: {calls} calls, {tokens:,} tokens — the weekly reset is not readable "
                       "here: give its date with --cloud-reset-on")
    return True, f"Claude Code {since}: {calls} calls, {tokens:,} tokens"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cloud-reset-on", help="the date (YYYY-MM-DD) Claude Code's weekly window was reset")
    a = ap.parse_args()
    cfg = sys_config.get()
    checks = [("machine idle", gpus_idle()), ("no run under way", runs_idle(cfg)), ("no other benchmark", benches_idle()),
              ("code aligned", code_aligned()), ("cloud fresh", cloud_since(cfg, a.cloud_reset_on))]
    for name, (ok, why) in checks:
        print(f"{'✅' if ok else '⛔'} {name}: {why}")
    go = all(ok for _, (ok, _) in checks)
    print("GO" if go else "NOT YET")
    return 0 if go else 1


if __name__ == "__main__":
    sys.exit(main())
