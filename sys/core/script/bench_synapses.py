# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Do the synapses make the answers' passages better? (owner, 2026-10-27: «verifichiamo anche la parte delle sinapsi…
sono curioso se stanno crescendo bene… pianifica un confronto»).

Real questions of the last DAYS (the search traces), each searched twice on the real vault with the production
Searcher and the running models: with the synapses (AURORA_SYNAPSE_EXPAND as set) and without (0). Nothing is
written: the synapses' use and growth are switched off for the run, the search traces too. For every question that
the synapses changed, the local reasoner judges each passage they brought in and each one they pushed out (0 not
relevant, 1 partly, 2 relevant to the question); the synapses help when what they bring is judged better than what it
displaces. Results: <STATUS>/bench/synapses-<time>.json and a line in synapses_history.jsonl; told as a notification.

    python sys/core/script/bench_synapses.py [--days 14] [--max 120]
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import gzip
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import kno_synapse, sys_config, sys_log  # noqa: E402

JUDGE = ("You judge whether a passage helps to answer a question. Reply with one digit only: 2 if the passage is "
         "relevant and useful to answer it, 1 if it is related but not much use, 0 if it is not relevant.")


def questions(cfg, days: int, most: int) -> list[str]:
    """Distinct questions of the last `days` from the search traces, the ones the synapses touched first."""
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    touched, other = {}, {}
    for f in sorted(glob.glob(str(cfg.path("AURORA_LOG_DIR") / "trace" / "search*"))):
        op = gzip.open if f.endswith(".gz") else open
        with op(f, "rt", errors="replace") as fh:
            for line in fh:
                if '"retrieval.hits"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                q = str(e["payload"].get("question") or "").strip()
                if e["ts"][:10] < since or len(q) < 12:
                    continue
                (touched if (e["payload"].get("synapses") or {}).get("added") else other)[q] = 1
    pick = list(touched)[-most:]
    rest = [q for q in other if q not in touched]
    random.Random(7).shuffle(rest)
    return pick + rest[:max(0, most // 3)]


def judge(llm, question: str, text: str) -> int:
    out = llm.complete(JUDGE, f"QUESTION: {question}\n\nPASSAGE:\n{text[:1500]}", 4).text
    m = re.search(r"[012]", out)
    return int(m.group(0)) if m else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="the synapses with and without, on real questions")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--max", type=int, default=120)
    args = ap.parse_args()
    cfg = sys_config.get()
    log = sys_log.get_logger("bench")
    from aurora import sol_search
    from aurora.mdl_llm import LLM
    from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
    # nothing of the run is kept: no use counted, no growth, no search trace
    kno_synapse.used = lambda *a, **k: None
    kno_synapse.grow_for = lambda *a, **k: 0
    sol_search.Searcher._grow_where_used = lambda self, sids: None
    real_trace = sys_log.trace
    sys_log.trace = lambda component, *a, **k: None if component == "search" else real_trace(component, *a, **k)
    expand = int(cfg["AURORA_SYNAPSE_EXPAND"])
    off = dataclasses.replace(cfg, values={**cfg.values, "AURORA_SYNAPSE_EXPAND": 0})
    embedder, reranker = RemoteEmbedder(cfg), RemoteReranker(cfg)
    with_s = sol_search.Searcher(embedder, reranker, cfg)
    without = sol_search.Searcher(embedder, reranker, off, reader=with_s.reader, index=with_s.index)
    llm = LLM(cfg)
    qs = questions(cfg, args.days, args.max)
    log.info("bench synapses: %d questions, expand %d", len(qs), expand)
    rows, t0 = [], time.time()
    for q in qs:
        a = with_s.search(q)
        b = without.search(q)
        sa, sb = {h.sid: h for h in a}, {h.sid: h for h in b}
        brought = [h for h in a if h.sid not in sb]
        pushed = [h for h in b if h.sid not in sa]
        row = {"question": q, "changed": bool(brought), "brought": [], "pushed": []}
        for key, hs in (("brought", brought), ("pushed", pushed)):
            for h in hs:
                row[key].append({"sid": h.sid, "domain": h.soliton.domain, "rerank": round(h.rerank, 4),
                                 "judge": judge(llm, q, h.soliton.text)})
        rows.append(row)
    changed = [r for r in rows if r["changed"]]
    gain = [statistics.mean(x["judge"] for x in r["brought"]) - statistics.mean(x["judge"] for x in r["pushed"])
            for r in changed if r["brought"] and r["pushed"]]
    flat = lambda k: [x["judge"] for r in changed for x in r[k]]  # noqa: E731
    summary = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "questions": len(rows), "changed": len(changed),
               "brought": len(flat("brought")), "brought_relevance": round(statistics.mean(flat("brought")), 3) if flat("brought") else None,
               "pushed_relevance": round(statistics.mean(flat("pushed")), 3) if flat("pushed") else None,
               "better": sum(1 for g in gain if g > 0), "worse": sum(1 for g in gain if g < 0), "same": sum(1 for g in gain if g == 0),
               "links": kno_synapse.stats(cfg)["links"], "expand": expand, "minutes": round((time.time() - t0) / 60, 1)}
    out = cfg.path("AURORA_STATUS_DIR") / "bench"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"synapses-{time.strftime('%Y%m%d-%H%M')}.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "synapses_history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")
    log.info("bench synapses: %s", summary)
    print(json.dumps(summary, ensure_ascii=False))
    try:                                                   # told to the owner, like a night's work
        from aurora import sys_push
        msg = {"title": "🧠 Confronto delle sinapsi pronto", "view": "synapses", "tag": "aurora-bench",
               "body": f"{summary['changed']} domande su {summary['questions']} cambiate dalle sinapsi; pertinenza di "
                       f"ciò che portano {summary['brought_relevance']} contro {summary['pushed_relevance']} di ciò "
                       "che scalzano (0–2)."}
        sys_push.send(msg, cfg)
        sys_push.remember(msg, "bench.synapses", ["push"], cfg)
    except Exception as e:                                 # noqa: BLE001 — the results are on disk anyway
        log.warning("bench synapses: not told: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
