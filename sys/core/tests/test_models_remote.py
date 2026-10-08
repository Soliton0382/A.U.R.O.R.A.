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
