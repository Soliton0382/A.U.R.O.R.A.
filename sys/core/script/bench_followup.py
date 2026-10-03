# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Follow-up benchmark: does a vague follow-up find its source once rewritten with the conversation (C104, M71)?

For N questions of retrieval_pool108 the local model writes a general first question that names the subject and the
original question as a follow-up that hides it ("e quale condizione serve sulla sua misura di base?"). Two synthetic
turns (the first question, the source's opening as the answer) are the conversation; nothing is written to the vault.
The rank of the source document is measured for the original question (ceiling), the bare follow-up and the rewritten
one. N more questions, complete, with turns about another topic, are the control: they should not change.
Generated follow-ups that copy the original or the prompt's example are dropped and counted.

    python sys/core/script/bench_followup.py [--n 20]
Results: <STATUS>/bench/followup_<date>.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sns_clock, sys_config  # noqa: E402
from aurora.kno_answer import SYS_TRANSLATE, Pipeline  # noqa: E402
from aurora.mdl_remote import RemoteEmbedder, RemoteReranker  # noqa: E402
from aurora.sol_schema import Soliton  # noqa: E402

EXAMPLE = "misura di base"
SPLIT = ("You get a precise question. Write JSON {\"first\": ..., \"follow\": ...} in the same language: 'first' is a "
         "short general question that names the subject (e.g. 'Cos'è il processo di Dirichlet?'); 'follow' is the "
         "original question asked AFTER 'first', where the subject is replaced by a pronoun or a vague reference "
         f"('e quale condizione serve sulla sua {EXAMPLE}…'), so that alone it cannot be understood. Output only JSON.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    cfg = sys_config.get()
    p = Pipeline(RemoteEmbedder(cfg), RemoteReranker(cfg), cfg)
    bench = cfg.path("AURORA_STATUS_DIR") / "bench"
    rows = [json.loads(x) for x in (bench / "retrieval_pool108" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]
    random.Random(11).shuffle(rows)
    llm = p._for("translate")
    tr = lambda q: llm.complete(SYS_TRANSLATE, q, 200).answer  # noqa: E731

    def doc(source_id: str) -> str:            # the suite's ids carry an older prefix than the vault's
        return source_id.split(":", 1)[-1]

    def rank(q: str, src: str) -> int | None:
        return next((i for i, h in enumerate(p.search.search(q, tr(q)), 1) if doc(h.soliton.source_id) == doc(src)), None)

    def turns(first: str, answer: str) -> list[Soliton]:
        now = sns_clock.now(cfg)
        return [Soliton.new(text, "memory", "conversation", "it", "bench", extra={"role": role},
                            created_at=(now - timedelta(minutes=3 - i)).isoformat())
                for i, (role, text) in enumerate((("user", first), ("assistant", answer)))]

    out, mute = [], lambda *_: None
    for r in rows[:a.n]:
        m = re.search(r"\{.*\}", llm.complete(SPLIT, r["question"], 400).answer, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            d = {}
        f = str(d.get("follow", "")).strip()
        valid = bool(f) and f != r["question"].strip() and not (EXAMPLE in f and EXAMPLE not in r["question"])
        row = {"kind": "follow", "valid": valid, "original": r["question"], "first": d.get("first"), "follow": f}
        if valid:
            std = p._standalone(f, turns(d["first"], r["source_text"][:400]), mute)
            row.update(rewritten=std, rank_original=rank(r["question"], r["source_id"]), rank_follow=rank(f, r["source_id"]),
                       rank_rewritten=rank(std, r["source_id"]) if std != f else None)
            if std == f:
                row["rank_rewritten"] = row["rank_follow"]
        out.append(row)
        print(json.dumps(row, ensure_ascii=False)[:200], flush=True)
    for r, other in zip(rows[a.n:2 * a.n], rows[:a.n]):
        std = p._standalone(r["question"], turns(other["question"], other["source_text"][:400]), mute)
        out.append({"kind": "control", "original": r["question"], "rewritten": std, "changed": std != r["question"],
                    "rank_original": rank(r["question"], r["source_id"]),
                    "rank_rewritten": rank(std, r["source_id"]) if std != r["question"] else None})
    v = [x for x in out if x["kind"] == "follow" and x["valid"]]
    top3 = lambda k: sum(1 for x in v if x[k] is not None and x[k] <= 3)  # noqa: E731
    summary = {"valid": len(v), "of": a.n, "top3_original": top3("rank_original"), "top3_follow": top3("rank_follow"),
               "top3_rewritten": top3("rank_rewritten"),
               "worse": sum(1 for x in v if (x["rank_rewritten"] or 99) > (x["rank_follow"] or 99)),
               "control_changed": sum(1 for x in out if x["kind"] == "control" and x["changed"])}
    print(json.dumps(summary))
    (bench / f"followup_{datetime.now():%Y%m%d-%H%M}.json").write_text(
        json.dumps({"summary": summary, "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
