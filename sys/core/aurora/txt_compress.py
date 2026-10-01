# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Token compression for cloud reasoners: the owner's Soliton-Salience compressor (SSCC).

Port of AGI_old/Papers/Presentation_Hybrid-Offload-Engine/sscc_api_client.py, applied to sentences:

    score = cos(query, sentence) * (1 + ALPHA * Amp) * (GAMMA + (1 - GAMMA) * Vel)

cos is TF-IDF similarity (numpy only), Amp the unique-token ratio normalised to the densest sentence,
Vel the position (later = fresher). The best `keep_pct` percent of the sentences survive, in their
original order; sentences carrying a citation [n] are always kept, so the verification still works.
Every call returns its measured saving (characters and estimated tokens), which the caller logs.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

ALPHA = 0.35
GAMMA = 0.70
MIN_KEEP = 3

_TOKEN = re.compile(r"\w+", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")
_CITATION = re.compile(r"\[\d+\]")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class _Tfidf:
    def __init__(self, corpus: list[str]):
        df = Counter(w for d in corpus for w in set(_tokens(d)))
        self.vocab = {w: i for i, w in enumerate(df)}
        n = max(1, len(corpus))
        self.idf = np.array([math.log((1 + n) / (1 + df[w])) + 1.0 for w in self.vocab], dtype=np.float32)

    def embed(self, text: str) -> np.ndarray:
        v = np.zeros(len(self.vocab), dtype=np.float32)
        toks = _tokens(text)
        for w, c in Counter(toks).items():
            j = self.vocab.get(w)
            if j is not None:
                v[j] = c / len(toks) * self.idf[j]
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v


def score(query: str, chunks: list[str], alpha: float = ALPHA, gamma: float = GAMMA) -> np.ndarray:
    emb = _Tfidf(chunks + [query])
    q = emb.embed(query)
    amps = np.array([len(set(_tokens(c))) / max(1, len(_tokens(c))) for c in chunks], dtype=np.float32)
    amps = amps / (amps.max() + 1e-8)
    n = len(chunks)
    return np.array([float(np.dot(q, emb.embed(c))) * (1 + alpha * amps[i]) * (gamma + (1 - gamma) * (i + 1) / n)
                     for i, c in enumerate(chunks)], dtype=np.float32)


def compress(query: str, text: str, keep_pct: int) -> tuple[str, dict]:
    """(compressed text, {"chars_in", "chars_out", "sentences_in", "sentences_out"})."""
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    stats = {"chars_in": len(text), "sentences_in": len(sentences)}
    k = min(len(sentences), max(MIN_KEEP, round(len(sentences) * keep_pct / 100)))
    if k >= len(sentences):
        return text, {**stats, "chars_out": len(text), "sentences_out": len(sentences)}
    s = score(query, sentences)
    keep = set(np.argsort(-s)[:k].tolist()) | {i for i, x in enumerate(sentences) if _CITATION.search(x)}
    out = " ".join(sentences[i] for i in sorted(keep))
    return out, {**stats, "chars_out": len(out), "sentences_out": len(keep)}
