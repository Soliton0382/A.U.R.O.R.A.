# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C208: the clients of aurora-models ask it at their first use, not when made — a page that only reads (the chat's
history) worked only while aurora-models was up (found by the suite on a real Mac, where no aurora-models runs)."""
import pytest

from aurora import mdl_remote


def test_making_the_clients_asks_nothing_the_first_use_asks(cfg, monkeypatch):
    asked = []

    class Health:
        def json(self):
            return {"status": "ok", "encoder": "enc-x", "dim": 8}

    def get(url, timeout):
        asked.append(url)
        return Health()
    monkeypatch.setattr(mdl_remote.httpx, "get", get)
    e, r = mdl_remote.RemoteEmbedder(cfg), mdl_remote.RemoteReranker(cfg)
    assert asked == []                                              # made: nothing asked
    assert (e.name, e.dim) == ("enc-x", 8) and len(asked) == 1     # the first use asks once
    assert e.dim == 8 and len(asked) == 1
    assert r.info["status"] == "ok" and len(asked) == 2


def test_a_service_not_ready_is_said_at_the_first_use(cfg, monkeypatch):
    class NotReady:
        def json(self):
            return {"status": "loading"}
    monkeypatch.setattr(mdl_remote.httpx, "get", lambda url, timeout: NotReady())
    e = mdl_remote.RemoteEmbedder(cfg)
    with pytest.raises(RuntimeError, match="not ready"):
        e.dim


def test_documents_go_in_parts_and_come_back_in_order(cfg, monkeypatch):
    """C219: one request of 256 passages ran past the 600 s timeout on a 2-core Windows; parts of DOC_PART, in order."""
    import numpy as np
    sizes = []

    class Answer:
        def __init__(self, texts):
            self.texts = texts

        def raise_for_status(self):
            return self

        def json(self):
            return {"vectors": [[float(t), 0.0] for t in self.texts]}

    def post(url, json, timeout):
        sizes.append(len(json["texts"]))
        return Answer(json["texts"])
    monkeypatch.setattr(mdl_remote.httpx, "post", post)
    e = mdl_remote.RemoteEmbedder(cfg)
    v = e.encode_documents([str(i) for i in range(70)])
    assert sizes == [32, 32, 6] and v.shape == (70, 2) and list(v[:, 0]) == list(np.arange(70, dtype=np.float16))
    assert e.encode_queries(["1"] * 40).shape == (40, 2) and sizes[-1] == 40      # a question: one request
