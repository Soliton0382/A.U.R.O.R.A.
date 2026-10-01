# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Clients of aurora-models with the same interface as the local encoder and re-ranker,
so that sol_index and sol_search work unchanged against the service."""
from __future__ import annotations

from typing import Sequence

import httpx
import numpy as np

from . import sys_config


class _Client:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.url = f"http://{self.cfg['AURORA_MODELS_HOST']}:{self.cfg['AURORA_MODELS_PORT']}"
        info = httpx.get(self.url + "/health", timeout=10).json()
        if info.get("status") != "ok":
            raise RuntimeError(f"aurora-models is not ready: {info}")
        self.info = info


class RemoteEmbedder(_Client):
    def __init__(self, cfg: sys_config.Config | None = None):
        super().__init__(cfg)
        self.name, self.dim = self.info["encoder"], self.info["dim"]

    def _embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float16)
        r = httpx.post(self.url + "/embed", json={"texts": list(texts), "kind": kind}, timeout=600)
        r.raise_for_status()
        return np.asarray(r.json()["vectors"], dtype=np.float16)

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "documents")

    def encode_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "queries")


class RemoteReranker(_Client):
    def score(self, pairs: Sequence[tuple[str, str]]) -> np.ndarray:
        if not pairs:
            return np.zeros(0, dtype=np.float32)
        r = httpx.post(self.url + "/rerank", json={"pairs": [list(p) for p in pairs]}, timeout=600)
        r.raise_for_status()
        return np.asarray(r.json()["scores"], dtype=np.float32)
