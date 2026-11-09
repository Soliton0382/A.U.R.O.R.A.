# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The night's training answers alone (audit, 10 Nov): its shadows («train») serve the other users, so the owner's
recent turns never shape the question nor become its sources."""
from types import SimpleNamespace

from aurora import kno_shadow, kno_train


def test_the_training_asks_without_the_owners_turns(cfg, monkeypatch):
    doc = SimpleNamespace(title="Decoherence", text="x" * 500, domain="physics")
    monkeypatch.setattr(kno_train, "documents", lambda reader, n, rng: [doc])
    monkeypatch.setattr(kno_shadow, "find", lambda *a, **k: None)
    monkeypatch.setattr(kno_shadow, "add", lambda *a, **k: None)
    seen = {}

    def run(q, **kw):
        seen.update(kw)
        return SimpleNamespace(abstained=True, mode="knowledge", sources=[], text="", suggestions=[])
    llm = SimpleNamespace(complete=lambda *a: SimpleNamespace(answer="What is quantum decoherence?"))
    pipeline = SimpleNamespace(reader=None, llm=llm, run=run, search=SimpleNamespace(embedder=None, reranker=None))
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    kno_train.train(pipeline, cfg, lambda *a: None, 1, seed=1)
    assert seen.get("alone") is True and seen.get("remember") is False
