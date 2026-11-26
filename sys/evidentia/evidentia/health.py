# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What the pages of Aurora's 🕵️ Evidentia menu show (owner, 10 Nov: «manca tutta la gestione dei menu… poco
navigabile»): the collections of the archive with their numbers (🗄️ Archivi) and the server's health (🩺 Server).
Read-only, fixed queries; the counts over the four million passages are kept a few minutes (one scan, not one a click)."""
from __future__ import annotations

import os
import time
from pathlib import Path

STARTED = time.time()
KEEP = 300                                   # seconds a scan of the archive is reused
_cache: dict[str, tuple[float, dict]] = {}


def _kept(name: str, make) -> dict:
    hit = _cache.get(name)
    if hit and time.time() - hit[0] < KEEP:
        return hit[1]
    out = make()
    _cache[name] = (time.time(), out)
    return out


def collections(corpus, vectors: Path) -> dict:
    """Each collection: documents, pages, kinds, failures, passages; and the vectors made for the whole archive."""
    def make() -> dict:
        rows = {}
        for r in corpus.execute("SELECT collection, COUNT(*) AS docs, COALESCE(SUM(pages), 0) AS pages, "
                                "SUM(kind = 'text') AS text, SUM(kind = 'scan') AS scan, SUM(kind = 'mixed') AS mixed, "
                                "SUM(kind = 'image') AS image, SUM(status = 'failed') AS failed "
                                "FROM documents GROUP BY collection ORDER BY docs DESC"):
            rows[r["collection"]] = {**dict(r), "passages": 0}
        for r in corpus.execute("SELECT substr(doc, 1, instr(doc, ':') - 1) AS c, COUNT(*) AS n FROM passages GROUP BY c"):
            if r["c"] in rows:
                rows[r["c"]]["passages"] = r["n"]
        total = sum(c["passages"] for c in rows.values())
        return {"collections": list(rows.values()), "passages": total, "vectors": _vectors(vectors, total), "at": time.time()}
    return _kept("collections", make)


def _vectors(folder: Path, passages: int) -> dict:
    """The embedding blocks on disk (100,000 passages each, the last one shorter): their number and size."""
    blocks = sorted(folder.glob("*/block-*.npz")) if folder.is_dir() else []
    models = sorted({b.parent.name for b in blocks})
    return {"models": models, "blocks": len(blocks), "bytes": sum(b.stat().st_size for b in blocks),
            "expected": -(-passages // 100_000) if passages else 0}


def health(data: Path, sources: Path | None, corpus_ok: bool, leads: dict, agents: tuple[int, int]) -> dict:
    files = {n: (data / n).stat().st_size for n in ("corpus.db", "findings.db", "cases.db") if (data / n).exists()}
    return {"up_since": STARTED, "pid": os.getpid(), "archive": corpus_ok, "files": files,
            "sources": {"path": str(sources or ""), "reachable": bool(sources) and sources.is_dir(), "set": bool(sources)},
            "leads": leads, "agents": {"active": agents[0], "proposed": agents[1]}, "at": time.time()}
