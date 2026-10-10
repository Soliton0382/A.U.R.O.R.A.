# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One exchange of the conversation forgotten for good (10 Oct: probe questions had landed in the owner's memory, and
only the session memories could be forgotten)."""
import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def activity(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):
        importlib.import_module(f"aurora.api.{name}")
    return importlib.import_module("aurora.api.activity")


def test_an_exchange_is_forgotten_with_its_index_rows(activity, monkeypatch):
    calls = []
    writer = SimpleNamespace(remove_source=lambda d, s: calls.append(("remove", d, s)) or (["a", "b"] if s == "run:x" else []))
    indexer = SimpleNamespace(drop=lambda d, sids: calls.append(("drop", d, sids)))
    monkeypatch.setattr(activity, "pipeline", lambda: SimpleNamespace(writer=writer, indexer=indexer))
    assert activity.forget_exchange("run:x") == {"forgotten": 2}
    assert calls == [("remove", "conversation", "run:x"), ("drop", "conversation", ["a", "b"])]
    with pytest.raises(HTTPException) as e:
        activity.forget_exchange("run:none")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        activity.forget_exchange("doc:something")                      # only a conversation's run
    assert e.value.status_code == 422
