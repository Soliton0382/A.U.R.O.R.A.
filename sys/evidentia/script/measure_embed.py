#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Measure I2: an embedding model on this machine's GPU — passages a second, memory, the vector's size — on real text
of a random sample of the PDFs (never printed). Run only with the GPU free (Aurora at rest: law 6).

    .venv/bin/python sys/evidentia/script/measure_embed.py embeddinggemma-300m 2000
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidentia import config  # noqa: E402

SOURCES = Path(os.environ.get("EVD_SOURCES_DIR") or config.load().path("EVD_SOURCES_DIR"))   # the .env's (B23)


def passages(n: int, size: int = 1200) -> list[str]:
    """~n passages of about `size` characters from random PDFs (the text itself is never printed)."""
    random.seed(11)
    names = [x for x in os.listdir(SOURCES) if x.lower().endswith(".pdf")]
    out: list[str] = []
    for name in random.sample(names, min(len(names), n)):
        txt = subprocess.run(["pdftotext", "-layout", str(SOURCES / name), "-"], capture_output=True, timeout=60).stdout
        t = " ".join(txt.decode("utf-8", "replace").split())
        out += [t[i:i + size] for i in range(0, len(t), size) if len(t[i:i + size]) > 200]
        if len(out) >= n:
            break
    return out[:n]


def main(model: str, n: int) -> int:
    import torch
    from sentence_transformers import SentenceTransformer
    busy = subprocess.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], capture_output=True,
                          text=True).stdout.strip()
    if busy:
        print("the GPU is in use (law 6): put Aurora to rest first")
        return 1
    texts = passages(n)
    import fetch_model                                    # the same folder: a model changed is never measured (B30)
    folder = fetch_model.check(model, ROOT / "sys" / "models")
    m = SentenceTransformer(str(folder), device="cuda")
    torch.cuda.reset_peak_memory_stats()
    m.encode(texts[:32], batch_size=32)                     # warm-up
    t0 = time.time()
    v = m.encode(texts, batch_size=64, normalize_embeddings=True)
    secs = time.time() - t0
    print(json.dumps({"model": model, "passages": len(texts), "seconds": round(secs, 1),
                      "passages_per_s": round(len(texts) / secs, 1), "dim": int(v.shape[1]),
                      "gpu_peak_mib": round(torch.cuda.max_memory_allocated() / 2 ** 20)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "embeddinggemma-300m",
                          int(sys.argv[2]) if len(sys.argv) > 2 else 2000))
