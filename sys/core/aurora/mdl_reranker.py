# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The re-ranker: reads a question and a passage together and scores how well
the passage answers the question.

Cross-encoder bge-reranker-v2-m3, input truncated to AURORA_RERANKER_MAX_TOKENS
(1,024 halves the cost of 2,048 for about one point, M15). Scores are in 0..1.
Meant to stay resident next to the encoder.
"""
from __future__ import annotations

import time
from typing import Sequence

import numpy as np

from . import sys_config, sys_log


class Reranker:
    def __init__(self, cfg: sys_config.Config | None = None):
        import torch
        from sentence_transformers import CrossEncoder

        self.cfg = cfg or sys_config.get()
        self.log = sys_log.get_logger("models")
        path = self.cfg.path("AURORA_RERANKER_DIR")
        t0 = time.time()
        self.model = CrossEncoder(str(path), device=self.cfg["AURORA_RERANKER_DEVICE"],
                                  max_length=self.cfg["AURORA_RERANKER_MAX_TOKENS"],
                                  model_kwargs={"torch_dtype": torch.float16}, local_files_only=True)
        self.batch = self.cfg["AURORA_RERANKER_BATCH"]
        self.name = path.name
        self.log.info("reranker %s loaded on %s in %.1f s", self.name,
                      self.cfg["AURORA_RERANKER_DEVICE"], time.time() - t0)

    def score(self, pairs: Sequence[tuple[str, str]]) -> np.ndarray:
        if not pairs:
            return np.zeros(0, dtype=np.float32)
        return np.asarray(self.model.predict(list(pairs), batch_size=self.batch,
                                             show_progress_bar=False), dtype=np.float32)
