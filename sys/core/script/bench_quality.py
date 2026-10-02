# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Answer quality of Aurora as she is now: the real API answers, a blind judge scores them against the passages.

    python sys/core/script/bench_quality.py                 # questions of <STATUS>/bench/quality_questions.json
    python sys/core/script/bench_quality.py --judge sonnet  # another Claude model as the judge
    python sys/core/script/bench_quality.py --pool 30       # 30 questions of retrieval_pool108 (fixed sample, seed 7)

For each question: POST /v1/aurora/ask (remember: false — nothing goes into her memory), the run's events followed to
the answer; the passages she retrieved are read from the vault by their ids; the judge (Claude Code, opus by default)
gets the question, the passages and the answer, and scores 0-10: correct against the passages, complete, no sentence
the passages do not support. An abstention scores 0 unless the passages really do not hold the answer (then 10).
Results: <STATUS>/bench/quality_<date>.json with every answer and score, and the mean (M40: local 5.25, noise ±0.75).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402

cfg = sys_config.get()
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
HEAD = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
JUDGE = ("You are a strict, impartial examiner. You get a QUESTION, the PASSAGES of a knowledge base and an ANSWER "
         "that cites passages as [n]. Score the answer from 0 to 10: 10 = correct according to the passages, complete "
         "for what the question asks, every sentence supported by them; subtract for every error, every missing key "
         "fact the passages hold, every claim they do not support. If the answer declines to answer: 10 if the "
         "passages really do not hold the answer, 0 if they do. Reply ONLY with JSON: {\"score\": n, \"why\": \"one "
         "sentence\"}.")


def questions(path: Path) -> list[str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["questions"]
    old = path.with_name("quality_ab.json")             # the 8 questions of M40, kept as the reference set
    qs = [r["q"] for r in json.loads(old.read_text(encoding="utf-8"))["rows"]]
    path.write_text(json.dumps({"about": "M40's 8 questions (retrieval_pool108, document in the top 3)",
                                "questions": qs}, ensure_ascii=False, indent=1), encoding="utf-8")
    return qs


def pool(n: int) -> list[str]:
    import random
    f = cfg.path("AURORA_STATUS_DIR") / "bench" / "retrieval_pool108" / "questions.jsonl"
    qs = [json.loads(line)["question"] for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    return random.Random(7).sample(qs, min(n, len(qs)))


def stage(events: list[dict]) -> str:
    """Where an abstention happened: the gate closed, every extraction empty, verification dropped everything, or the
    synthesis said it had nothing."""
    gate = next((e for e in events if e["event"] == "gate"), None)
    if gate and not gate["payload"].get("open"):
        return "gate"
    doms = [e for e in events if e["event"] == "synthesis.domain"]
    if doms and not any(e["payload"].get("kept") for e in doms):
        return "extraction"
    if any(e["event"] == "verify.drop" for e in events) and not any(e["event"] == "verify.keep" for e in events):
        return "verification"
    return "synthesis"


def ask(q: str) -> dict:
    run = httpx.post(f"{BASE}/v1/aurora/ask", headers=HEAD, json={"question": q, "remember": False}, timeout=60).json()["run_id"]
    t0, hits, final, events = time.time(), [], None, []
    with httpx.stream("GET", f"{BASE}/v1/aurora/runs/{run}/events", headers=HEAD, timeout=900) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            e = json.loads(line[6:])
            events.append(e)
            if e["event"] == "retrieval.hits":
                hits = [h["sid"] for h in e["payload"]["hits"]]
            elif e["event"] == "answer.final":
                final = e["payload"]
            elif e["event"] in ("run.end", "error") and final is not None or e["event"] == "error":
                break
    abstained = bool((final or {}).get("abstained"))
    return {"run": run, "hits": hits, "answer": (final or {}).get("text", ""), "abstained": abstained,
            "stage": stage(events) if abstained else None, "seconds": round(time.time() - t0, 1)}


def passages(sids: list[str]) -> str:
    from aurora.sol_reader import VaultReader
    found = VaultReader(cfg).get_many(sids)
    return "\n\n".join(f"[{n}] {found[s].title or ''}\n{found[s].text}" for n, s in enumerate(sids, 1) if s in found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--judge", default="opus")
    ap.add_argument("--pool", type=int, default=0, help="N questions of retrieval_pool108 instead of the 8 of M40")
    ap.add_argument("--only", default="", help="only these positions of the pool sample, e.g. 4,6,12")
    ap.add_argument("--tag", default="", help="a word in the result's file name (before, after…)")
    a = ap.parse_args()
    from aurora.mdl_cloud import ClaudeCodeLLM
    judge = ClaudeCodeLLM(cfg, a.judge)
    bench = cfg.path("AURORA_STATUS_DIR") / "bench"
    rows = []
    qs = pool(a.pool) if a.pool else questions(bench / "quality_questions.json")
    keep = {int(x) for x in a.only.split(",") if x.strip().isdigit()}
    for i, q in enumerate(qs, 1):
        if keep and i not in keep:
            continue
        res = ask(q)
        ctx = passages(res["hits"])
        out = judge.complete(JUDGE, f"QUESTION: {q}\n\nPASSAGES:\n{ctx}\n\nANSWER:\n{res['answer']}", 400).answer
        m = re.search(r"\{.*\}", out, re.S)
        try:
            verdict = json.loads(m.group(0)) if m else {}
        except ValueError:
            verdict = {}
        score = verdict.get("score")
        rows.append({**res, "q": q, "score": score, "why": verdict.get("why", out[:300])})
        print(f"{i}. {score}/10 in {res['seconds']} s{' [abstained: ' + res['stage'] + ']' if res['abstained'] else ''} — "
              f"{q[:60]}… | {str(verdict.get('why', ''))[:110]}", flush=True)
    scored = [r["score"] for r in rows if isinstance(r["score"], (int, float))]
    mean = round(sum(scored) / len(scored), 2) if scored else None
    from collections import Counter
    wrong = Counter(r["stage"] for r in rows if r["abstained"] and (r["score"] or 0) < 5)
    print(f"MEAN {mean} on {len(scored)} questions (M40: local 5.25, local+SSCC 6.00, Claude 5.38; noise ±0.75); "
          f"answered {sum(not r['abstained'] for r in rows)}, wrong abstentions by stage {dict(wrong)}")
    (bench / f"quality_{datetime.now():%Y%m%d-%H%M}{'_' + a.tag if a.tag else ''}.json").write_text(
        json.dumps({"at": datetime.now().isoformat(), "judge": a.judge, "mean": mean, "rows": rows}, ensure_ascii=False,
                   indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
