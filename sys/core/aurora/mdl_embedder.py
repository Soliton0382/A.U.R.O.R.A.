# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The encoder: turns solitons and questions into vectors.

Solitons are encoded as they are; questions get AURORA_EMBEDDER_QUERY_PROMPT
in front (the official instruction of the model: a custom one cost 21 points
of rank-1, M18). Vectors are L2-normalized, so a dot product is a cosine.

Loading takes a few seconds and ~1.2 GB of GPU memory in fp16; the object is
meant to stay resident. Today it runs inside the process that uses it; the
same interface will be served by aurora-models.
"""
from __future__ import annotations

import time
from typing import Sequence

import numpy as np

from . import sys_config, sys_log


class Embedder:
    def __init__(self, cfg: sys_config.Config | None = None):
        import torch
        from sentence_transformers import SentenceTransformer

        self.cfg = cfg or sys_config.get()
        self.log = sys_log.get_logger("models")
        path = self.cfg.path("AURORA_EMBEDDER_DIR")
        t0 = time.time()
        self.model = SentenceTransformer(
            str(path), device=self.cfg["AURORA_EMBEDDER_DEVICE"],
            model_kwargs={"torch_dtype": getattr(torch, self.cfg["AURORA_EMBEDDER_DTYPE"])},
            processor_kwargs={"padding_side": "left"}, local_files_only=True)
        self.model.max_seq_length = self.cfg["AURORA_EMBEDDER_MAX_TOKENS"]
        self.dim = self.model.get_embedding_dimension()
        if self.dim != self.cfg["AURORA_EMBEDDER_DIM"]:
            raise ValueError(f"{path.name} produces {self.dim}-d vectors, AURORA_EMBEDDER_DIM says "
                             f"{self.cfg['AURORA_EMBEDDER_DIM']}")
        self.name = path.name
        self.prompt = self.cfg["AURORA_EMBEDDER_QUERY_PROMPT"]
        self.batch = self.cfg["AURORA_EMBEDDER_BATCH"]
        self.log.info("embedder %s loaded on %s in %.1f s (%d-d)", self.name,
                      self.cfg["AURORA_EMBEDDER_DEVICE"], time.time() - t0, self.dim)

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float16)
        v = self.model.encode(list(texts), batch_size=self.batch, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)
        return v.astype(np.float16)

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        t0 = time.time()
        v = self._encode(texts)
        if texts:
            self.log.debug("encoded %d documents in %.2f s", len(texts), time.time() - t0)
        return v

    def encode_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode([self.prompt + t for t in texts])
