#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F4: every passage of the archive as a vector (EmbeddingGemma, bf16, the model's «document» prompt), one process per
GPU, in blocks of 100,000 passages written as soon as they are done — a block already on disk is skipped, so a stop
costs at most one block. Run only with the GPUs free (Aurora at rest: law 6).

    .venv/bin/python sys/evidentia/script/evd_embed.py            # every GPU in EVD_GPUS
    .venv/bin/python sys/evidentia/script/evd_embed.py --check    # bf16 against float32 on 300 passages, then stop

Measured (I2, 10 Nov): bf16 at 512 tokens 111 passages/s per RTX 5060 Ti, float32 42/s; 90 % of the passages ≤ 420 tokens.
Output: sys/data/vectors/<model>/block-<n>.npz with ids (int64) and vectors (float16, normalised)."""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sys" / "evidentia"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_model  # noqa: E402 — the same folder: the model's pin (B30)
from evidentia import config  # noqa: E402

BLOCK = 100_000
CFG = config.load()
MAX_TOKENS = 512


def _db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{CFG.path('EVD_DATA_DIR') / 'corpus.db'}?mode=ro", uri=True)


def _model(name: str, gpu: int, dtype: str = "bf16"):
    import torch
    from sentence_transformers import SentenceTransformer
    kw = {"torch_dtype": torch.bfloat16} if dtype == "bf16" else {}
    folder = fetch_model.check(name, CFG.path('EVD_MODELS_DIR'))     # B30: the pinned files, or ModelMismatch — never loaded
    m = SentenceTransformer(str(folder), device=f"cuda:{gpu}", model_kwargs=kw)
    m.max_seq_length = MAX_TOKENS
    return m


def _texts(db, lo: int, hi: int) -> tuple[list[int], list[str]]:
    rows = db.execute("SELECT id, text FROM passages WHERE id >= ? AND id < ? ORDER BY id", (lo, hi)).fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]


def check(name: str, gpu: int) -> int:
    """bf16 and float32 vectors of the same 300 passages: their cosine (the same within ~0.99 or bf16 is refused)."""
    import numpy as np
    db = _db()
    top = db.execute("SELECT max(id) FROM passages").fetchone()[0]
    ids, texts = [], []
    for start in range(1, top, top // 300):
        i, t = _texts(db, start, start + 1)
        ids += i
        texts += t
    a = _model(name, gpu, "bf16").encode_document(texts, batch_size=64, normalize_embeddings=True)
    b = _model(name, gpu, "fp32").encode_document(texts, batch_size=64, normalize_embeddings=True)
    cos = (np.asarray(a, dtype=np.float32) * np.asarray(b, dtype=np.float32)).sum(1)
    out = {"passages": len(texts), "cos_min": round(float(cos.min()), 4), "cos_p01": round(float(np.quantile(cos, 0.01)), 4),
           "cos_mean": round(float(cos.mean()), 4)}
    print(json.dumps(out))
    return 0 if out["cos_p01"] >= 0.99 else 1


def complete(db, out: Path, n: int) -> bool:
    """A block on disk with as many passages as the archive holds in its range (a collection added later,
    10 Nov — appends passages to the last block: it is done again)."""
    import numpy as np
    f = out / f"block-{n:04d}.npz"
    if not f.exists():
        return False
    have = len(np.load(f)["ids"])
    return have == db.execute("SELECT count(*) FROM passages WHERE id >= ? AND id < ?", (n * BLOCK, (n + 1) * BLOCK)).fetchone()[0]


def worker(name: str, gpu: int, blocks: list[int], out: Path) -> None:
    import numpy as np
    m = _model(name, gpu)
    db = _db()
    for n in blocks:
        f = out / f"block-{n:04d}.npz"
        if complete(db, out, n):
            continue
        t0 = time.time()
        ids, texts = _texts(db, n * BLOCK, (n + 1) * BLOCK)
        if ids:
            v = m.encode_document(texts, batch_size=128, normalize_embeddings=True, convert_to_numpy=True)
            tmp = out / f".block-{n:04d}.{gpu}.npz"
            np.savez(tmp, ids=np.asarray(ids, dtype=np.int64), vectors=np.asarray(v, dtype=np.float16))
            os.replace(tmp, f)                                   # whole or nothing: a stop never leaves half a block
        rate = len(ids) / max(time.time() - t0, 1e-6)
        print(f"gpu{gpu} block {n}: {len(ids)} passages in {time.time() - t0:.0f} s ({rate:.0f}/s)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=CFG["EVD_EMBED_MODEL"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    gpus = [int(g) for g in str(CFG["EVD_GPUS"]).split(",") if g.strip()]
    if a.check:
        return check(a.model, gpus[0])
    top = _db().execute("SELECT max(id) FROM passages").fetchone()[0]
    out = CFG.path("EVD_DATA_DIR") / "vectors" / a.model
    out.mkdir(parents=True, exist_ok=True)
    blocks = list(range(top // BLOCK + 1))
    db = _db()
    todo = [n for n in blocks if not complete(db, out, n)]
    print(f"{len(blocks)} blocks of {BLOCK}, {len(todo)} to do, on GPUs {gpus}", flush=True)
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=worker, args=(a.model, g, todo[i::len(gpus)], out)) for i, g in enumerate(gpus)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    return max(p.exitcode or 0 for p in procs)


if __name__ == "__main__":
    raise SystemExit(main())
