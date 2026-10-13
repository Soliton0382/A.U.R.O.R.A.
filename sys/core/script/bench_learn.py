#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora learns from a benchmark's mistakes (kno_lessons): each wrong answer of the result files given becomes one
lesson of method — never its answer — kept in <STATUS>/lessons.jsonl and read by the answers to come.

    python script/bench_learn.py <result.json> [...]     # a bench_public.py or a bench_agi.py result
    python script/bench_learn.py --list                    # the lessons she has
    python script/bench_learn.py --calibrate <result.json> # the cosine of each lesson's question vs the others (MIN_COS)

The lessons are written by the model of the «rem» role (her autonomic cycle: her own reflections). Measure them with
bench_public.py: the same set with (--lessons) and without, and another sample (--seed) for whether they generalise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))          # bench_public, to read a set again

from aurora import kno_lessons, mdl_router, sys_config  # noqa: E402
from aurora.mdl_llm import LLM  # noqa: E402
from aurora.mdl_remote import RemoteEmbedder  # noqa: E402


def rows_of(path: Path) -> tuple[list[dict], str]:
    """Graded rows [{question, expected, answer, right, why}] of a result file, and its origin."""
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    if "sets" in d:                                       # bench_public.py
        for s, v in d["sets"].items():
            asked = {}
            if any(not r.get("question") for r in v.get("rows", [])):   # a file of before the question was kept
                import bench_public as P
                try:
                    asked = {it["id"]: it["prompt"] for it in P.questions(s, d.get("n", 10), d.get("seed", 7))}
                except Exception as e:                    # noqa: BLE001 — a set that cannot be read again: its rows wait
                    print(f"  {s}: questions not read again ({e})", flush=True)
            for r in v.get("rows", []):
                out.append({"question": r.get("question") or asked.get(r["id"], ""), "expected": r.get("expected", ""),
                            "answer": r.get("answer", ""), "right": r.get("right"), "why": r.get("got", "")})
        return out, f"bench:{d.get('target', 'public')}:{path.stem}"
    for s, v in d.get("sections", {}).items():           # bench_agi.py
        for r in v.get("rows", []):
            q = r.get("q", "")
            if r.get("quote"):
                q = f"(replying to «{r['quote']}») {q}"
            out.append({"question": q, "expected": r.get("expected", ""), "answer": r.get("answer", ""),
                        "right": r.get("right"), "why": r.get("why", "")})
    return out, f"agi:{path.stem}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    a = ap.parse_args()
    cfg = sys_config.get()
    if a.list:
        for x in kno_lessons.load(cfg):
            print(f"[{x['id']}] ×{x.get('seen', 1)} · {x.get('kind', '')}\n  quando {x['when']}\n  → {x['do']}")
        return
    emb = RemoteEmbedder(cfg)
    if a.calibrate:
        qs = [r["question"] for f in a.files for r in rows_of(Path(f))[0] if r["question"]]
        import numpy as np
        les = kno_lessons.load(cfg)
        if not les or not qs:
            print("no lessons or no questions")
            return
        L = kno_lessons._unit(emb.encode_documents([x["when"] for x in les]))
        Q = kno_lessons._unit(emb.encode_queries(qs))
        best = (Q @ L.T).max(axis=1)
        print(f"{len(qs)} questions × {len(les)} lessons: best cosine per question p10 {np.percentile(best, 10):.3f} "
              f"p50 {np.median(best):.3f} p90 {np.percentile(best, 90):.3f} max {best.max():.3f}; "
              f"questions over MIN_COS {kno_lessons.MIN_COS}: {(best >= kno_lessons.MIN_COS).sum()}")
        return
    llm = mdl_router.model_for("rem", LLM(cfg), cfg)
    for f in a.files:
        rows, origin = rows_of(Path(f))
        print(f, json.dumps(kno_lessons.learn(cfg, llm, emb, rows, origin)), flush=True)


if __name__ == "__main__":
    main()
