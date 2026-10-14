#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The honeypot measured (ROADMAP 104): every content of bench_honeypot_data handed to the decoy (sec_detonate.explode)
with the local model, the decoy Aurora uses (C317) — no network, no VM, nothing executed: the decoy only writes text. Counts traps
caught (and the «zero_day» ones, with none of the cheap cues), harmless contents flagged (false alarms), the cues'
own hits for comparison, and the seconds per content. Results: <STATUS>/bench/honeypot.json.

    python sys/core/script/bench_honeypot.py               # the local model: the decoy in use
    python sys/core/script/bench_honeypot.py --agent       # the agent's model instead (Claude: it falls for nothing)
    python sys/core/script/bench_honeypot.py --repeat 3    # each content 3 times (the decoy's answers vary)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench_honeypot_data import HARMLESS, TRAPS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", action="store_true", help="the agent's model (the Models page), not the local decoy")
    ap.add_argument("--repeat", type=int, default=1, help="tries per content")
    a = ap.parse_args()
    from aurora import mdl_router, sec_detonate, sys_config
    cfg = sys_config.get()
    local = mdl_router.base(cfg)
    model = mdl_router.model_for("agent", local, cfg) if a.agent else local
    rows = []
    for kind, items in (("trap", [(n, z, t) for n, z, t in TRAPS]), ("harmless", [(n, False, t) for n, t in HARMLESS])):
        for name, zero_day, text in items:
            for k in range(a.repeat):
                t0 = time.time()
                boom, why = sec_detonate.explode(model, text)
                rows.append({"kind": kind, "name": name, "zero_day": zero_day, "try": k, "exploded": boom,
                             "why": why[:300], "cues": sec_detonate.cues(text), "seconds": round(time.time() - t0, 1)})
                mark = ("✅" if boom else "❌") if kind == "trap" else ("⚠️" if boom else "✅")
                print(f"{mark} {kind:8} {name:16} {rows[-1]['seconds']:>5} s  {why[:90]}", flush=True)
    traps = [r for r in rows if r["kind"] == "trap"]
    zd = [r for r in traps if r["zero_day"]]
    harm = [r for r in rows if r["kind"] == "harmless"]
    out = {"at": time.strftime("%Y-%m-%d %H:%M"), "model": "agent" if a.agent else "local", "repeat": a.repeat,
           "caught": sum(r["exploded"] for r in traps), "traps": len(traps),
           "zero_day_caught": sum(r["exploded"] for r in zd), "zero_day": len(zd),
           "cues_on_traps": sum(bool(r["cues"]) for r in traps), "cues_on_harmless": sum(bool(r["cues"]) for r in harm),
           "false_alarms": sum(r["exploded"] for r in harm), "harmless": len(harm),
           "median_s": sorted(r["seconds"] for r in rows)[len(rows) // 2], "rows": rows}
    path = cfg.path("AURORA_STATUS_DIR") / "bench" / "honeypot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\ncaught {out['caught']}/{out['traps']} (zero-day {out['zero_day_caught']}/{out['zero_day']}), "
          f"false alarms {out['false_alarms']}/{out['harmless']}; the cues alone: {out['cues_on_traps']}/{out['traps']} "
          f"traps, {out['cues_on_harmless']}/{out['harmless']} harmless; median {out['median_s']} s → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
