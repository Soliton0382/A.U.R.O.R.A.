#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where the vault's points are lost (roadmap T2; owner, 2026-10-13: «la questione è anche capire se il vault da davvero
un valore aggiunto… fare un test corretto, stabilire dove intervenire»). On the REAL vault — every passage competing,
not a suite's own small vault (bench_retrieval.py) — for each question of a pool with its gold source:

    1. present   is the gold source in the vault at all
    2. found     its rank among the passages the production search returns (top_k as in the chat, and up to `deep`
                 to tell a ranking problem from a search problem)
    3. read      given the chat's passages, does the reading (kno_read.from_vault, the owner's roles: local) answer
                 and cite the gold source — or answer from others, or find nothing
    4. way       the question's kind (kno_read.kind) and so the way «auto» takes: a FACT goes to the web first

Local models only: no cloud quota. Results: <STATUS>/bench/vault_diag/<time>.json and a summary on screen.

    python script/bench_vault_diag.py [--suite retrieval_pool108] [--n 0] [--deep 30] [--no-read]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora import kno_read, sys_config  # noqa: E402


def rank_of(hits, gold: set[str]) -> int | None:
    return next((i for i, h in enumerate(hits, 1) if h.soliton.source_id in gold), None)


def legacy_title(source_id: str, title: str) -> str:
    """The plain title of a v1 source: «legacy:wiki_Cold_War_txt_done» → «Cold War» (chats and reflections: none)."""
    m = re.match(r"legacy:(wiki|arxiv)_(.+?)(?:_txt_done|_pdf_done|_done)?$", source_id)
    if m:
        return m.group(2).replace("_", " ").strip()
    return "" if source_id.startswith("legacy:") else title.strip()


def same_title(cfg, titles: set[str]) -> dict[str, set[str]]:
    """{title: the source ids that carry it in the vault} — a v1 source harvested again by v2 has a new id
    (legacy:wiki_Buddhism_txt_done → doc:449151…, title «Buddhism»): the same document (13 Oct: 7 of 11 «missing»)."""
    from aurora import sol_vault
    layout = sol_vault.Layout.from_config(cfg, None)
    out: dict[str, set[str]] = {t: set() for t in titles if t}
    for section in sol_vault.SECTIONS:
        for dom in layout.domains(section):
            for shard in layout.shards(section, dom):
                with sol_vault.db(shard, readonly=True) as con:
                    for t in out:                    # the same title; a long one may be the start (v1 cut them at
                        long = len(t) >= 40             # ~50 characters); a short one only exact: «Islam» is not «Islamic art»
                        out[t] |= {r[0] for r in con.execute(
                            "SELECT DISTINCT source_id FROM solitons WHERE lower(title) = ? OR (? AND lower(title) LIKE ?)",
                            (t.lower(), long, t.lower() + "%"))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="retrieval_pool108")
    ap.add_argument("--n", type=int, default=0, help="the first N questions (0 = all)")
    ap.add_argument("--deep", type=int, default=30, help="how far down to look for the gold source")
    ap.add_argument("--no-read", action="store_true", help="the search only (no model)")
    ap.add_argument("--with-memory", action="store_true",
                    help="keep the pool's questions on v1 chats and reflections (memory, not knowledge: left out by default)")
    a = ap.parse_args()
    cfg = sys_config.get()
    base = cfg.path("AURORA_STATUS_DIR") / "bench" / a.suite
    qs = [json.loads(x) for x in (base / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if not a.with_memory:                              # the owner's conversations and Aurora's reflections are memory:
        qs = [q for q in qs if not q["source_id"].startswith(("legacy:chat_", "legacy:json_"))]   # not the vault's test
    qs = qs[:a.n] if a.n else qs
    domain_of, title_of = {}, {}
    for line in (base / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            domain_of.setdefault(d["source_id"], d["domain"])
            title_of.setdefault(d["source_id"], legacy_title(d["source_id"], d.get("title") or ""))
    by_title = same_title(cfg, {title_of.get(q["source_id"], "") for q in qs})
    from aurora.kno_answer import Pipeline
    from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
    p = Pipeline(RemoteEmbedder(cfg), RemoteReranker(cfg), cfg)
    top_k = int(cfg["AURORA_SEARCH_TOPK"])
    knowledge = [d for d, v in p.reader.layout.taxonomy.items() if not v.get("memory")]
    rows, t0 = [], time.time()
    for i, q in enumerate(qs, 1):
        gold, question, tr = q["source_id"], q["question"], q.get("translation") or None
        # the pool's domain may not be the one the source lives in now: looked for in every knowledge domain
        doms = [domain_of.get(gold, "")] + [d for d in knowledge if d != domain_of.get(gold)]
        dom = next((d for d in doms if d and p.reader.by_source(d, gold, limit=1)), "")
        golds = {gold} | by_title.get(title_of.get(gold, ""), set())
        present = bool(dom) or len(golds) > 1
        chat = p.search.search(question, tr)                                  # what the chat reads
        deep = p.search.search(question, tr, candidates=max(a.deep * 3, 90), top_k=a.deep)
        r_chat, r_deep = rank_of(chat, golds), rank_of(deep, golds)
        row = {"i": i, "question": question, "gold": gold, "same_title": sorted(golds - {gold}), "domain": dom, "present": present,
               "rank_chat": r_chat, "rank_deep": r_deep, "top_k": len(chat),
               "chat_domains": sorted({h.soliton.domain for h in chat})}
        if not a.no_read:
            row["kind"] = kno_read.kind(p, question)
            out = kno_read.from_vault(p, question, chat, "explain")
            cited = [s.get("source") for s in (out or {}).get("sources", [])]
            row["read"] = "nothing" if not out else "gold" if golds & set(cited) else "others"
            row["answer"] = (out or {}).get("text", "")[:600]
        rows.append(row)
        print(f"{i:3}/{len(qs)} {'P' if present else '-'} chat {r_chat or '—':>2} deep {r_deep or '—':>2} "
              f"{row.get('kind', ''):8} {row.get('read', ''):7} {question[:60]}", flush=True)
    n = len(rows)
    pres = [r for r in rows if r["present"]]
    summary = {
        "questions": n, "present": len(pres),
        "found_r1": sum(1 for r in pres if r["rank_chat"] == 1),
        "found_chat": sum(1 for r in pres if r["rank_chat"]),
        "found_deep_only": sum(1 for r in pres if not r["rank_chat"] and r["rank_deep"]),
        "not_found": sum(1 for r in pres if not r["rank_deep"]),
        "top_k": top_k, "deep": a.deep, "seconds": round(time.time() - t0)}
    if not a.no_read:
        inchat = [r for r in pres if r["rank_chat"]]
        summary.update({
            "kinds": dict(Counter(r["kind"] for r in rows)),
            "read_when_found": dict(Counter(r["read"] for r in inchat)),
            "read_when_not_found": dict(Counter(r["read"] for r in pres if not r["rank_chat"]))})
    out = base.parent / "vault_diag"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{datetime.now():%Y%m%d-%H%M}-{a.suite}.json"
    f.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("→", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
