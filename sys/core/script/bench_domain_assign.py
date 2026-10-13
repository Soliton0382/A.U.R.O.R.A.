#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which way of choosing a document's domain is right (owner, 2026-10-13: «documenti in domini sbagliati… quella cosa si
allena e si sceglie un solo metodo… harvester deve essere una roccia»). The Wikipedia harvester puts an article in the
domain of the LIST it came from («Philosophy and religion» → religion: «Philosophy of science» in religion).

A stratified sample of the vault's documents (read only: title and first passage) is labelled by a reference model
(Claude, the cloud: one short call each), then each method is scored against it:
    list      the domain the document is in today (the list it came from)
    centroid  the nearest domain by meaning: each domain's centroid of its documents' first passages (the encoder)
    local     the local model reading the title and the start, choosing among the domains (the route role's model)

    python script/bench_domain_assign.py [--per-domain 25] [--domains general,history,...] [--judge sonnet]
Results: <STATUS>/bench/domain_assign-<time>.json and a table.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from aurora import mdl_router, sol_vault, sys_config  # noqa: E402
from aurora.mdl_llm import LLM  # noqa: E402
from aurora.mdl_remote import RemoteEmbedder  # noqa: E402
from aurora.sol_schema import load_taxonomy  # noqa: E402

SYS = ("You assign a document to ONE domain of a library, the one it is mainly about. DOMAINS (id: name): {domains}. "
       "«general» only when no other domain fits. Reply with the domain id only.")


ACCEPT = ("Domains: {domains}. A document was put in CHOSEN; you chose YOURS. Is CHOSEN also a defensible place for "
          "it (a document between two domains), or a mistake? Reply YES or NO.")


def first_passages(cfg, domain: str, n: int, seed: int = 7) -> list[dict]:
    """n documents of a domain (title, first passage), drawn with a fixed seed: read only."""
    layout = sol_vault.Layout.from_config(cfg, None)
    docs = []
    for shard in layout.shards("knowledge", domain):
        with sol_vault.db(shard, readonly=True) as con:
            docs += [{"source_id": r[0], "title": r[1], "text": r[2][:900], "domain": domain} for r in con.execute(
                "SELECT source_id, title, text FROM solitons WHERE chunk_index = 0 AND title != ''")]
    random.Random(seed).shuffle(docs)
    return docs[:n]


def pick(llm, doc: dict, ids: list[str], names: str) -> str:
    out = llm.complete(SYS.format(domains=names), f"TITLE: {doc['title']}\n\nSTART: {doc['text']}", 12).answer.strip().lower()
    m = re.search(r"[a-z_]+", out)
    return m.group(0) if m and m.group(0) in ids else "?"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-domain", type=int, default=25)
    ap.add_argument("--domains", default="general,history,philosophy,religion,literature,society")
    ap.add_argument("--judge", default="sonnet", help="Claude Code's model that labels the reference")
    ap.add_argument("--centroid-docs", type=int, default=60, help="documents per domain for its centroid")
    a = ap.parse_args()
    cfg = sys_config.get()
    tax = {k: v for k, v in load_taxonomy().items() if not v.get("memory")}
    ids = sorted(tax)
    names = "; ".join(f"{k} ({tax[k]['en']}: {tax[k].get('about', '')})" for k in ids)
    from aurora.mdl_cloud import ClaudeCodeLLM
    judge = ClaudeCodeLLM(cfg, a.judge)
    local = mdl_router.model_for("route", LLM(cfg), cfg)
    emb = RemoteEmbedder(cfg)
    t0 = time.time()
    # the centroids: the first passages of every knowledge domain (a fixed seed), from today's assignments
    cents = {}
    for d in ids:
        docs = first_passages(cfg, d, a.centroid_docs, seed=11)
        if docs:
            v = np.asarray(emb.encode_documents([x["text"] for x in docs]), dtype=np.float32)
            c = v.mean(axis=0)
            cents[d] = c / (np.linalg.norm(c) + 1e-9)
    cid = list(cents)
    C = np.stack([cents[d] for d in cid])
    rows = []
    for d in a.domains.split(","):
        for doc in first_passages(cfg, d, a.per_domain):
            ref = pick(judge, doc, ids, names)
            q = np.asarray(emb.encode_queries([f"{doc['title']}. {doc['text']}"])[0], dtype=np.float32)
            q = q / (np.linalg.norm(q) + 1e-9)
            row = {"title": doc["title"], "source_id": doc["source_id"], "ref": ref, "list": d,
                   "centroid": cid[int(np.argmax(C @ q))], "local": pick(local, doc, ids, names)}
            rows.append(row)
            print(f"{d:12} ref {ref:22} list {'✓' if d == ref else '✗'} centroid {row['centroid'][:14]:14} "
                  f"{'✓' if row['centroid'] == ref else '✗'} local {row['local'][:14]:14} {'✓' if row['local'] == ref else '✗'} "
                  f"{doc['title'][:40]}", flush=True)
    # a disagreement may be a document between two domains: the reference says whether the other choice is defensible
    for r in rows:
        for m in ("list", "local"):
            if r[m] != r["ref"]:
                said = judge.complete(ACCEPT.format(domains=names), f"TITLE: {r['title']}\nCHOSEN: {r[m]}\nYOURS: {r['ref']}",
                                      4).answer.strip().upper()
                r[f"{m}_acceptable"] = said.startswith("YES")
    ok = {m: sum(r[m] == r["ref"] for r in rows) for m in ("list", "centroid", "local")}
    ok_or_fine = {m: sum(r[m] == r["ref"] or r.get(f"{m}_acceptable", False) for r in rows) for m in ("list", "local")}
    summary = {"documents": len(rows), "right": ok, "accuracy": {m: round(v / len(rows), 3) for m, v in ok.items()},
               "right_or_defensible": {m: round(v / len(rows), 3) for m, v in ok_or_fine.items()},
               "list_wrong_pairs": Counter(f"{r['list']} → {r['ref']}" for r in rows if r["list"] != r["ref"]).most_common(12),
               "minutes": round((time.time() - t0) / 60, 1)}
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / f"domain_assign-{datetime.now():%Y%m%d-%H%M}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("→", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
