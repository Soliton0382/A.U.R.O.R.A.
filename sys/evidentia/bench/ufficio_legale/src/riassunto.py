#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The scores of a run file (risultati/llm_runs*.jsonl) as one JSON: per task kind, citations, leaks, time."""
import json
import sys
from pathlib import Path

f = Path(sys.argv[1])
rows = [json.loads(l)["score"] for l in f.read_text().splitlines()]
by = {}
for s in rows:
    by.setdefault(s["kind"], []).append(s)
out = {"tasks": len(rows)}
for kind, ss in by.items():
    d = {"n": len(ss), "answered": sum(s["answered"] for s in ss)}
    if kind in ("lookup", "classify"):
        d["correct"] = sum(bool(s.get("correct")) for s in ss)
    if kind == "lookup":
        d["gold_cited"] = sum(bool(s.get("gold_cited")) for s in ss)
    if "share" in ss[0]:
        d["share_mean"] = round(sum(s["share"] for s in ss) / len(ss), 3)
        d["per_matter"] = {s["matter"]: round(s["share"], 2) for s in ss}
    out[kind] = d
c = [s["cites"] for s in rows]
out["citations"] = {"total": sum(x["n"] for x in c), "held_on_page": sum(x["kept"] for x in c),
                    "fake_or_wrong_page": sum(x["fake"] for x in c), "format_refused": sum(x["format"] for x in c),
                    "held_from_other_matter": sum(x["other_matter"] for x in c)}
out["seconds_total"] = round(sum(s["seconds"] for s in rows), 1)
out["seconds_max"] = max(s["seconds"] for s in rows)
print(json.dumps(out, indent=1, ensure_ascii=False))
