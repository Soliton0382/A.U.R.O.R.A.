#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The judge's own drift (ROADMAP D2, N4 b; owner, 15 Oct: «un giudice che non vari»): the answers of saved runs of
bench_public judged again by the same model, twice, nothing asked again.

Only the answers a model judged (HLE's exact answers, MATH's not identical, SimpleQA, her edge's source and judge
items with a fixed truth); the ones scored by code cannot drift. A saved answer keeps its last 1500 characters, so
two numbers: today against the run's own verdict (drift between days, the cut included) and today against today
(the judge alone on the same text).

    python sys/core/script/bench_rejudge.py 20261015-1420-aurora-mixed.json 20261015-1449-aurora-mixed-s8.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_public import OUT, grade, questions  # noqa: E402
from bench_quality import cfg  # noqa: E402

from aurora.mdl_cloud import ClaudeCodeLLM  # noqa: E402

JUDGED = ("exact", "math", "simpleqa", "source", "judge")


def judged_rows(report: dict):
    """(set, row, item) for every answer a model judged, with its item rebuilt from the same seed."""
    seed, n = report.get("seed", 7), report.get("n", 10)
    for s, entry in report["sets"].items():
        if "rows" not in entry:
            continue
        items = {it["id"]: it for it in questions(s, n, seed)}
        for row in entry["rows"]:
            it = items.get(row["id"])
            if it is None or it["kind"] not in JUDGED or callable(it.get("truth")):
                continue
            if it["kind"] == "math" and not row.get("judged"):     # identical to the gold: no judge was asked
                continue
            yield s, row, it


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="result files in status/bench/public")
    ap.add_argument("--judge", default="sonnet")
    ap.add_argument("--only", default="", help="set or set/id-prefix, e.g. aurora_edge/vault")
    a = ap.parse_args()
    judge = ClaudeCodeLLM(cfg, a.judge)
    out = {"at": datetime.now().isoformat(timespec="seconds"), "judge": a.judge, "files": a.files, "rows": []}
    for f in a.files:
        report = json.loads((OUT / f).read_text(encoding="utf-8"))
        for s, row, it in judged_rows(report):
            if a.only and not f"{s}/{row['id']}".startswith(a.only):
                continue
            first = grade(dict(it), row["answer"], judge)["right"]
            second = grade(dict(it), row["answer"], judge)["right"]
            out["rows"].append({"file": f, "set": s, "id": row["id"], "then": bool(row["right"]), "now": first,
                                "again": second, "cut": len(row["answer"]) >= 1500})
            print(f"{s} {row['id']}: then {row['right']} now {first} again {second}", flush=True)
    rows = out["rows"]
    flips = lambda x, y: sum(r[x] != r[y] for r in rows)                          # noqa: E731
    out["summary"] = {"judged": len(rows), "then_vs_now": flips("then", "now"), "now_vs_again": flips("now", "again"),
                      "then_right": sum(r["then"] for r in rows), "now_right": sum(r["now"] for r in rows),
                      "again_right": sum(r["again"] for r in rows), "cut": sum(r["cut"] for r in rows),
                      "then_vs_now_uncut": sum(r["then"] != r["now"] for r in rows if not r["cut"])}
    path = OUT / f"{datetime.now():%Y%m%d-%H%M}-rejudge.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"]), "→", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
