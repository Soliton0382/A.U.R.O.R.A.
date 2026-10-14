#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora against the same model bare, question by question (owner, 2026-10-14: «grafici con test… che confermano che
aurora migliora i modelli nudi e crudi»). Reads two runs of bench_public on the same questions and says, per set and in
all: right answers of each, the questions only one of them got right, and McNemar's exact test on those (the paired
test: the same questions, so what counts is where they differ, not two totals and their noise).

    python sys/core/script/bench_compare.py <aurora run.json>[,<more of the same target>] <bare run.json>[,…]
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path


def rows(paths: str) -> dict[tuple[str, str], bool]:
    out = {}
    for p in paths.split(","):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        for name, s in d["sets"].items():
            for r in s.get("rows", []):
                out[(name, str(r.get("id") or r.get("question", "")[:80]))] = bool(r.get("right"))
    return out


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided p of b against c discordant pairs (binomial, p = ½)."""
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def compare(a: dict, b: dict) -> dict:
    keys = sorted(set(a) & set(b))
    sets: dict[str, dict] = {}
    for k in keys:
        s = sets.setdefault(k[0], {"n": 0, "a": 0, "b": 0, "only_a": 0, "only_b": 0})
        s["n"] += 1
        s["a"] += a[k]
        s["b"] += b[k]
        s["only_a"] += a[k] and not b[k]
        s["only_b"] += b[k] and not a[k]
    total = {f: sum(s[f] for s in sets.values()) for f in ("n", "a", "b", "only_a", "only_b")}
    for s in [*sets.values(), total]:
        s["p"] = round(mcnemar(s["only_a"], s["only_b"]), 4)
    return {"sets": sets, "total": total}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    out = compare(rows(sys.argv[1]), rows(sys.argv[2]))
    print(f"{'set':14} {'n':>4} {'Aurora':>7} {'bare':>5} {'only A':>7} {'only bare':>9} {'p':>7}")
    for name, s in [*out["sets"].items(), ("TOTAL", out["total"])]:
        print(f"{name:14} {s['n']:>4} {s['a']:>7} {s['b']:>5} {s['only_a']:>7} {s['only_b']:>9} {s['p']:>7}")
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
