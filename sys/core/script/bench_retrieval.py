# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Permanent retrieval benchmark: runs the production search on a fixed suite.

A suite is a folder under <AURORA_STATUS_DIR>/bench/<suite>/ with
  corpus.jsonl     {"text", "domain", "lang", "source_id", "title"} per line
  questions.jsonl  {"question", "translation", "source_id", "source_text"} per line
Questions are paraphrases in the owner's language, never excerpts of the source.

The suite is loaded into its own vault and index (<suite>/work-<hash>), never
into the real vault; the work folder is reused while the corpus and the encoder
do not change. Each question goes through sol_search.Searcher exactly as in
production, and the rank of the source is measured:
  chunk rank  — the exact source soliton;
  doc rank    — any soliton of the source document (source_id).
Results: <suite>/results/<timestamp>.json, one summary line in <suite>/history.jsonl.

    python sys/core/script/bench_retrieval.py --suite retrieval_pool108
    python sys/core/script/bench_retrieval.py --suite retrieval_pool108 --no-translation --min-doc-r1 70
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sol_schema, sys_config, sys_log  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rate(ranks: list[int | None], k: int) -> float:
    return round(100 * sum(1 for r in ranks if r is not None and r <= k) / len(ranks), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="permanent retrieval benchmark")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--remote", action="store_true",
                    help="the encoder and re-ranker of the running models service (no second copy on the GPU)")
    ap.add_argument("--no-translation", action="store_true", help="search with the original question only")
    ap.add_argument("--candidates", type=int, default=None, help="default: AURORA_SEARCH_CANDIDATES")
    ap.add_argument("--min-doc-r1", type=float, default=None, help="exit 1 if document rank-1 falls below this")
    args = ap.parse_args()

    cfg = sys_config.get()
    log = sys_log.get_logger("bench")
    suite = cfg.path("AURORA_STATUS_DIR") / "bench" / args.suite
    corpus, questions = load_jsonl(suite / "corpus.jsonl"), load_jsonl(suite / "questions.jsonl")
    enc_name = cfg.path("AURORA_EMBEDDER_DIR").name
    digest = hashlib.blake2b((suite / "corpus.jsonl").read_bytes() + enc_name.encode(), digest_size=6).hexdigest()
    work = suite / f"work-{digest}"
    cfg.values["AURORA_VAULT_DIR"] = os.path.relpath(work / "vault", cfg.root)   # isolate from the real vault
    cfg.values["AURORA_INDEX_DIR"] = os.path.relpath(work / "index", cfg.root)

    from aurora.mdl_embedder import Embedder
    from aurora.mdl_reranker import Reranker
    from aurora.sol_index import Indexer
    from aurora.sol_search import Searcher
    from aurora.sol_writer import VaultWriter

    t0 = time.time()
    if args.remote:                                     # the production models, already loaded: no GPU memory of its own
        from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
        embedder, reranker = RemoteEmbedder(cfg), RemoteReranker(cfg)
    else:
        embedder, reranker = Embedder(cfg), Reranker(cfg)
    t_models = time.time() - t0
    if not (work / "ready").exists():
        sols = [sol_schema.Soliton.new(r["text"], r["domain"], "knowledge", r["lang"], r["source_id"], title=r["title"])
                for r in corpus]
        rep = VaultWriter(cfg, component="bench").add_many(sols)
        log.info("suite %s: %d solitons written, %d duplicates, %d rejected", args.suite, len(rep.written),
                 len(rep.duplicates), len(rep.rejected))
    t1 = time.time()
    Indexer(embedder, cfg, component="bench").update_all()
    (work / "ready").write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    t_index = time.time() - t1

    candidates = args.candidates or cfg["AURORA_SEARCH_CANDIDATES"]
    searcher = Searcher(embedder, reranker, cfg)
    rows, lat = [], []
    for q in questions:
        source_sid = sol_schema.make_sid("knowledge", sol_schema.normalize(q["source_text"]))
        t = time.time()
        hits = searcher.search(q["question"], None if args.no_translation else q["translation"],
                               candidates=candidates, top_k=candidates)
        lat.append(time.time() - t)
        chunk = next((i for i, h in enumerate(hits, 1) if h.sid == source_sid), None)
        doc = next((i for i, h in enumerate(hits, 1) if h.soliton.source_id == q["source_id"]), None)
        rows.append({"question": q["question"], "chunk_rank": chunk, "doc_rank": doc,
                     "top1": hits[0].soliton.source_id if hits else None})
    ch, dc = [r["chunk_rank"] for r in rows], [r["doc_rank"] for r in rows]
    summary = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "suite": args.suite, "questions": len(rows),
        "corpus": len(corpus), "encoder": enc_name, "reranker": cfg.path("AURORA_RERANKER_DIR").name,
        "translation": not args.no_translation, "candidates": candidates,
        "doc": {f"r@{k}": rate(dc, k) for k in (1, 5, 10, 12)},
        "chunk": {f"r@{k}": rate(ch, k) for k in (1, 5, 10, 12)},
        "source_in_candidates": {"doc": rate(dc, candidates), "chunk": rate(ch, candidates)},
        "seconds": {"models": round(t_models, 1), "index": round(t_index, 1),
                    "per_question_median": round(statistics.median(lat), 2),
                    "per_question_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 2)},
    }
    (suite / "results").mkdir(exist_ok=True)
    out = suite / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(suite / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    log.info("bench %s: doc r@1 %.1f r@10 %.1f | chunk r@1 %.1f | %s", args.suite, summary["doc"]["r@1"],
             summary["doc"]["r@10"], summary["chunk"]["r@1"], out.name)
    sys_log.trace("bench", "bench.retrieval", summary)
    print(json.dumps(summary, indent=1))
    if args.min_doc_r1 is not None and summary["doc"]["r@1"] < args.min_doc_r1:
        print(f"BELOW THRESHOLD: doc r@1 {summary['doc']['r@1']} < {args.min_doc_r1}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
