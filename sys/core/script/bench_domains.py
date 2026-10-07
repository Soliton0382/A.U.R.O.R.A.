# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Retrieval by domain, on the real vault (owner, 2026-10-07: «le norme di legge sono incasinate, fisica e matematica
sono lineari, filosofia e psicologia sono fumose… test per i diversi domini»).

For each domain, passages are drawn at random (a fixed seed) from the vault itself — read only, nothing written to it.
For each passage the local model writes two questions in Italian that it answers: a DIRECT one (a precise question,
never copying the passage's sentences) and a STORY (2-4 sentences of everyday life whose answer needs the passage,
without its technical terms — like the owner's real case, C183). Each question is searched as production does:
  whole   the message whole (sol_search, as for every question today)
  split   the message's problems as short questions (kno_split), merged
  cites   the provisions the model names, fetched by number (kno_cites; law only), first, then split
and the rank of the passage (or of any passage of its document) is measured: in 1st place, top 5, top 12.
The model writes the questions from the passage it read: a bias towards the passage's words is possible (said in the
results); the STORY questions are asked to avoid them.

    python sys/core/script/bench_domains.py --per-domain 8                       # ~30 min, the GPU shared with the chat
    python sys/core/script/bench_domains.py --domains law_it,philosophy --per-domain 3
Results: <AURORA_STATUS_DIR>/bench/domains-<time>.json, and a table on stdout.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import kno_cites, kno_split, sys_config  # noqa: E402

DOMAINS = ["law_it", "physics", "mathematics", "philosophy", "society", "medicine", "history", "computer_science"]
SYS_DIRECT = ("Write ONE question in Italian that this passage answers precisely. Do not copy its sentences; name the "
              "subject. Output only the question.")
SYS_DRAFT = ("Answer briefly (3-6 sentences) from what you know, in the question's language, naming the precise "
             "subject: the law and article, the theorem, the author and work, the event and date. If you do not know, "
             "say so in one sentence.")
SYS_STORY = ("Write, in Italian, a short message (2-4 sentences) from a person in an everyday situation whose answer "
             "needs this passage — the way someone tells a problem to a friend, in plain words, WITHOUT the passage's "
             "technical terms, names or numbers. Output only the message.")


def sample(reader, domain: str, n: int, rng: random.Random) -> list[str]:
    """`n` sids of the domain's passages of 400+ characters, drawn with the seed (read-only connections)."""
    out = []
    for shard in reader.layout.shards("knowledge", domain):
        con = sqlite3.connect(f"file:{shard}?mode=ro", uri=True)
        hi = con.execute("SELECT max(rowid) FROM solitons").fetchone()[0] or 0
        tries = 0
        while len(out) < n and tries < n * 40:
            tries += 1
            r = con.execute("SELECT sid FROM solitons WHERE rowid = ? AND length(text) >= 400", (rng.randint(1, hi),)).fetchone()
            if r and r[0] not in out:
                out.append(r[0])
        con.close()
        if len(out) >= n:
            break
    return out


def rank(hits: list, sid: str, source: str) -> tuple[int | None, int | None]:
    chunk = next((i for i, h in enumerate(hits, 1) if h.sid == sid), None)
    doc = next((i for i, h in enumerate(hits, 1) if h.soliton.source_id == source), None)
    return chunk, doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default=",".join(DOMAINS))
    ap.add_argument("--per-domain", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--only", default="whole,split,cites,draft", help="strategies to run (draft: the model's answer recalls)")
    args = ap.parse_args()
    cfg = sys_config.get()
    from aurora.kno_answer import Pipeline
    from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
    p = Pipeline(RemoteEmbedder(cfg), RemoteReranker(cfg), cfg)
    llm = p.llm
    rng = random.Random(args.seed)
    rows = []
    noop = lambda *a, **k: None                                 # noqa: E731
    for domain in args.domains.split(","):
        sids = sample(p.reader, domain, args.per_domain, rng)
        for sid in sids:
            s = p.reader.get(sid)
            passage = s.text[:3000]
            for kind, system in (("direct", SYS_DIRECT), ("story", SYS_STORY)):
                q = llm.complete(system, passage, 220).answer.strip().strip('"«»')
                tr = llm.complete(kno_split.SYS_TRANSLATE, q, 200).answer
                row = {"domain": domain, "sid": sid, "source": s.source_id, "kind": kind, "question": q}
                only = set(args.only.split(","))
                t = time.time()
                hits = p.search.search(q, tr)
                row["whole"], row["whole_s"] = rank(hits, sid, s.source_id), round(time.time() - t, 1)
                if "draft" in only:                     # the owner's idea: what the model knows finds the passage
                    t = time.time()
                    draft = llm.complete(SYS_DRAFT, q, 400).answer
                    dh = p.search.search(q, tr, recall=[draft])
                    row["draft"], row["draft_s"] = rank(dh, sid, s.source_id), round(time.time() - t, 1)
                if kind == "story" and only & {"split", "cites"}:
                    t = time.time()
                    subs = kno_split.split(llm, q)
                    found = [p.search.search(x, llm.complete(kno_split.SYS_TRANSLATE, x, 120).answer, candidates=80)
                             for x in subs]
                    merged = kno_split.merge([], found, int(cfg["AURORA_SEARCH_TOPK"])) if found else hits
                    row["split"], row["split_s"], row["subs"] = rank(merged, sid, s.source_id), round(time.time() - t, 1), subs
                    if domain == "law_it":
                        t = time.time()
                        cited = kno_cites.hits(p, q, noop)
                        both = cited[:6] + [h for h in merged if h.sid not in {c.sid for c in cited[:6]}]
                        row["cites"], row["cites_s"] = rank(both, sid, s.source_id), round(time.time() - t, 1)
                rows.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "subs"}, ensure_ascii=False)[:300], flush=True)

    def rate(vals, k, i):
        vals = [v for v in vals if v is not None]
        return round(100 * sum(1 for v in vals if v[i] is not None and v[i] <= k) / len(vals)) if vals else None

    table = []
    for domain in args.domains.split(","):
        for kind in ("direct", "story"):
            rs = [r for r in rows if r["domain"] == domain and r["kind"] == kind]
            if not rs:
                continue
            line = {"domain": domain, "kind": kind, "n": len(rs)}
            for strat in ("whole", "draft", "split", "cites"):
                vals = [r.get(strat) for r in rs if strat in r]
                if vals:
                    line[strat] = {"chunk@1": rate(vals, 1, 0), "chunk@5": rate(vals, 5, 0), "chunk@12": rate(vals, 12, 0),
                                   "doc@5": rate(vals, 5, 1), "s": round(statistics.mean(r[f"{strat}_s"] for r in rs if strat in r), 1)}
            table.append(line)
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / f"domains-{time.strftime('%Y%m%d-%H%M')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.seed, "per_domain": args.per_domain, "table": table, "rows": rows},
                              ensure_ascii=False, indent=1))
    print(f"\n{'domain':18} {'kind':7} {'n':>3}  " + "  ".join(f"{s:>28}" for s in ("whole @1/@5/@12 doc@5 s", "draft", "split", "cites")))
    for t in table:
        cell = lambda s: (f"{t[s]['chunk@1']}/{t[s]['chunk@5']}/{t[s]['chunk@12']} {t[s]['doc@5']} {t[s]['s']}s"
                          if s in t else "—")       # noqa: E731
        print(f"{t['domain']:18} {t['kind']:7} {t['n']:>3}  " + "  ".join(f"{cell(s):>28}" for s in ("whole", "draft", "split", "cites")))
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
