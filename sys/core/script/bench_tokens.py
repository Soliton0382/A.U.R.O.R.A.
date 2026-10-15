#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The cloud's tokens of each configuration (ROADMAP D2, N4 a), read back from the trace of runs already made.

A run of bench_public lasts from its file's «at» to the file's last write. In that window every cloud call is in the
trace (`cloud.call`, with its usage); Aurora's own are made by the API's process, each one after a `cloud.mask` naming
its step, and the judge's by the benchmark's process (for bare-claude, the answers too). An agent run whose goal is one
of the run's questions is the benchmark's (her edge's live questions go to the agent); the other agents of the window
(routines, repairs) are kept apart as «agent (background)» and left out of the answers' total.

    python sys/core/script/bench_tokens.py 20261015-1420-aurora-mixed.json 20261015-1519-aurora-classifiers-cloud.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402


def zero() -> dict:
    return {"calls": 0, "in": 0, "cache_read": 0, "out": 0, "cost_usd": 0.0}


def events(trace: Path, start: str, end: str):
    for f in sorted(trace.glob("llm_client*")):
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", errors="replace") as h:
            for line in h:
                if '"cloud.' in line:
                    e = json.loads(line)
                    if start <= e["ts"] <= end:
                        yield e


def agent_runs(trace: Path, start: str, stop: str) -> list[tuple[str, str, int, str]]:
    """(start, end, pid, goal) of every agent run begun in the window."""
    runs: dict = {}
    for f in sorted(trace.glob("agent*")):
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", errors="replace") as h:
            for line in h:
                if '"agent.start"' in line or '"agent.finish"' in line:
                    e = json.loads(line)
                    r = runs.setdefault(e["run_id"], {"pid": e["pid"], "end": "9"})
                    if e["event"] == "agent.start":
                        r.update(start=e["ts"], goal=" ".join(str(e["payload"].get("goal", "")).split()))
                    else:
                        r["end"] = e["ts"]
    return [(r["start"], r["end"], r["pid"], r["goal"]) for r in runs.values() if start <= r.get("start", "") <= stop]


def tokens(trace: Path, report: dict, end: float) -> dict:
    """{"aurora": {step: usage}, "bench": usage} of one run; an agent's calls are the benchmark's when its goal is
    one of the run's questions (her edge's live questions go to the agent), «agent (background)» otherwise."""
    start = datetime.fromtimestamp(report["at"]).astimezone().isoformat()
    stop = datetime.fromtimestamp(end).astimezone().isoformat()
    evs = sorted(events(trace, start, stop), key=lambda e: e["ts"])
    asked = {" ".join(r["question"].split())[:80] for s in report["sets"].values() for r in s.get("rows", [])}
    agents = agent_runs(trace, start, stop)

    def agent_of(e) -> str:
        for a0, a1, pid, goal in agents:
            if pid == e["pid"] and a0 <= e["ts"] <= a1:
                return "agent" if goal[:80] in asked else "agent (background)"
        return "agent (background)"
    masked = {e["pid"] for e in evs if e["event"] == "cloud.mask"}             # the API: it masks before a call
    step, aurora, bench = {}, defaultdict(zero), zero()
    for e in evs:
        p = e.get("payload") or {}
        if e["event"] == "cloud.mask":
            step[e["pid"]] = p.get("role", "?")
        elif e["event"] == "cloud.call":
            u = p.get("usage") or {}
            role = step.pop(e["pid"], "?")
            c = aurora[agent_of(e) if role == "agent" else role] if e["pid"] in masked else bench
            c["calls"] += 1
            c["in"] += int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
            c["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
            c["out"] += int(u.get("output_tokens") or 0)
            c["cost_usd"] += float(p.get("cost_usd") or 0)
    return {"aurora": dict(aurora), "bench": bench}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="result files in status/bench/public")
    a = ap.parse_args()
    cfg = sys_config.get()
    out_dir = cfg.path("AURORA_STATUS_DIR") / "bench" / "public"
    trace = cfg.path("AURORA_LOG_DIR") / "trace"
    out = {}
    for f in a.files:
        path = out_dir / f
        report = json.loads(path.read_text(encoding="utf-8"))
        answers = sum(len(s.get("rows", [])) for s in report["sets"].values())
        t = tokens(trace, report, os.path.getmtime(path))
        total = zero()
        for role, c in t["aurora"].items():
            if role in ("agent (background)", "self", "?"):      # not the benchmark's answers
                continue
            for k in total:
                total[k] += c[k]
        out[f] = {"answers": answers, **t, "aurora_total": total}
        bg = t["aurora"].get("agent (background)", zero())
        print(f"{f}: {answers} answers; background agents {bg['calls']} calls {bg['cost_usd']:.2f} USD; the answers' cloud calls {total['calls']}, in {total['in']:,}, cached "
              f"{total['cache_read']:,}, out {total['out']:,}, {total['cost_usd']:.2f} USD; the benchmark's "
              f"(judge{', answers' if 'bare' in f else ''}) {t['bench']['calls']} calls, {t['bench']['cost_usd']:.2f} USD")
    dest = out_dir / f"{datetime.now():%Y%m%d-%H%M}-tokens.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
