# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The questions people really ask, with their right answers (owner, 2026-10-07: «un repo delle domande più comuni che
un utente fa… come batteria di prova e per creare le ombre»).

MKQA (Apple, CC BY-SA 3.0): 10,000 real queries to Google (from Natural Questions), each translated by people into
25 languages, Italian included, with answers independent of any passage. Only the questions whose answer can be checked
by a program are used (an entity, a date, a number, a short phrase, yes/no — not «long answer», not «unanswerable»).

Each question goes through the answer pipeline (no API, no memory: nothing is remembered) in each mode asked, and is
scored: RIGHT when the answer contains the expected text or one of its aliases (numbers and dates normalised), WRONG
when it answers something else, ABSTAINED when Aurora says she does not know. The time and the sentences confirmed by a
source are kept. The answers are from 2018: a few (who holds a title today) may have changed — the misses are listed.

    python sys/core/script/bench_common.py --n 40 --modes vault,verify          # ~1 h on the GPU shared with the chat
    python sys/core/script/bench_common.py --n 5 --modes verify
The file: <AURORA_STATUS_DIR>/bench/mkqa/mkqa.jsonl.gz (https://github.com/apple/ml-mkqa/raw/main/dataset/mkqa.jsonl.gz).
Results: <AURORA_STATUS_DIR>/bench/common-<time>.json.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402

CHECKABLE = ("entity", "date", "number", "number_with_unit", "short_phrase", "binary")
YES = {"sì", "si", "yes"}
NO = {"no"}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(\d)\.0\b", r"\1", t)                   # «11.0 anno» → «11 anno»
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


NUMBER_WORDS = {"uno": "1", "una": "1", "due": "2", "tre": "3", "quattro": "4", "cinque": "5", "sei": "6", "sette": "7",
                "otto": "8", "nove": "9", "dieci": "10", "undici": "11", "dodici": "12"}


def right(answer: str, gold: list[dict]) -> bool:
    """Exact text or alias; a person's name by its first and last word («Iain Stirling» for «Iain Andrew Stirling»);
    a number also written as a word («due» for 2) — the same rules for every mode (M130)."""
    a = " " + " ".join(NUMBER_WORDS.get(w, w) for w in norm(answer).split()) + " "
    if _strict(a, gold):
        return True
    for g in gold:
        if g["type"] == "entity":
            for t in [g.get("text") or ""] + list(g.get("aliases") or []):
                w = norm(t).split()
                if len(w) >= 3 and f" {w[0]} " in a and f" {w[-1]} " in a:
                    return True
    return False


def _strict(answer: str, gold: list[dict]) -> bool:
    """The answer holds an expected text: whole words for names, the number or the year for numbers and dates."""
    a = f" {norm(answer)} "
    for g in gold:
        kind = g["type"]
        texts = [g.get("text") or ""] + list(g.get("aliases") or [])
        if kind == "binary":
            want = norm(texts[0])
            words = set(a.split())
            if (want in YES and words & YES) or (want in NO and " non " in a or want in NO and words & NO):
                return True
            continue
        for t in texts:
            t = norm(t)
            if not t:
                continue
            if kind in ("number", "number_with_unit"):
                num = re.findall(r"\d+(?:\s\d{3})*", t)
                if num and f" {num[0]} " in a:
                    return True
            elif kind == "date":
                year = re.findall(r"\b\d{4}\b", t)
                if (year and f" {year[0]} " in a) or f" {t} " in a:
                    return True
            elif f" {t} " in a:
                return True
    return False


def sample(path: Path, n: int, seed: int) -> list[dict]:
    rows = [json.loads(l) for l in gzip.open(path, "rt", encoding="utf-8")]
    ok = [r for r in rows if r["answers"]["it"] and r["answers"]["it"][0]["type"] in CHECKABLE and r["queries"].get("it")
          and "other unit" not in (r["answers"]["it"][0].get("text") or "")]      # «19.79 other unit»: not checkable
    rng = random.Random(seed)
    rng.shuffle(ok)
    return ok[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--modes", default="vault,verify")
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()
    cfg = sys_config.get()
    path = cfg.path("AURORA_STATUS_DIR") / "bench" / "mkqa" / "mkqa.jsonl.gz"
    qs = sample(path, args.n, args.seed)
    from aurora.kno_answer import Pipeline
    from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
    p = Pipeline(RemoteEmbedder(cfg), RemoteReranker(cfg), cfg)
    rows = []
    for q in qs:
        question, gold = q["queries"]["it"], q["answers"]["it"]
        for mode in args.modes.split(","):
            cfg.values["AURORA_ANSWER_MODE"] = mode
            seen = {}
            a = p.run(question, emit=lambda e, pl: seen.__setitem__(e, pl) if e in ("think", "read.web", "read.pages",
                                                                                  "read.memory") else None, remember=False)
            score = "abstained" if a.abstained else "right" if right(a.text, gold) else "wrong"
            rows.append({"id": q["example_id"], "question": question, "type": gold[0]["type"], "gold": gold[0]["text"],
                         "mode": mode, "score": score, "seconds": round(a.seconds, 1), "answer": a.text[:600],
                         "sources": len(a.sources), "way": (seen.get("think") or {}).get("why", ""),
                         "web_query": (seen.get("read.web") or {}).get("query"), "pages": "read.pages" in seen,
                         "memory": "read.memory" in seen})
            print(json.dumps({k: rows[-1][k] for k in ("mode", "score", "seconds", "way", "gold", "question")},
                             ensure_ascii=False)[:240], flush=True)
    summary = {}
    for mode in args.modes.split(","):
        rs = [r for r in rows if r["mode"] == mode]
        summary[mode] = {"n": len(rs), **{s: sum(r["score"] == s for r in rs) for s in ("right", "wrong", "abstained")},
                         "seconds_mean": round(sum(r["seconds"] for r in rs) / max(1, len(rs)), 1),
                         "seconds_max": max((r["seconds"] for r in rs), default=0)}
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / f"common-{time.strftime('%Y%m%d-%H%M')}.json"
    out.write_text(json.dumps({"seed": args.seed, "n": args.n, "summary": summary, "rows": rows,
                               "source": "MKQA (Apple), CC BY-SA 3.0, from Natural Questions"}, ensure_ascii=False, indent=1))
    print()
    for mode, s in summary.items():
        print(f"{mode:7} right {s['right']}/{s['n']}  wrong {s['wrong']}  abstained {s['abstained']}  "
              f"time {s['seconds_mean']} s (max {s['seconds_max']})")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
