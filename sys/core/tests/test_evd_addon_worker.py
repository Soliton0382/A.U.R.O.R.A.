# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# Evidentia's lead worker — one lead at a time, the owner's only, twice then dropped.
import importlib
import json

import pytest

from aurora import sys_addons

W = None


@pytest.fixture(autouse=True)
def _addon(cfg, monkeypatch):
    """The add-on's modules, loaded as Aurora loads them, on the test's configuration (api.core reads it at import)."""
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    global W
    sys_addons.module("evidentia")
    W = importlib.import_module("aurora_addon_evidentia.evd_worker")


def test_the_worker_takes_one_lead_and_drops_one_it_cannot_close(cfg, monkeypatch):
    import sys
    import aurora.api.core  # noqa: F401
    core = sys.modules["aurora.api.core"]          # the module the code imports from (a test may have reloaded it)
    monkeypatch.setattr(W.sys_config, "get", lambda: cfg)
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    asked, started = [], []

    def ask(method, path, body=None):
        asked.append((method, path))
        if path == "/leads/claim":
            return {"lead": {"id": 7, "what": "who signed it", "token": "tok"}, "prompt": "You are the sniper."}
        return {"status": "dropped"}
    monkeypatch.setattr(W, "_ask", ask)
    monkeypatch.setattr(core, "_admin", lambda: "owner")
    monkeypatch.setattr(core, "_runs", {})
    monkeypatch.setattr(core, "start_run", lambda q, origin, job: started.append((q, origin)) or {"id": "r"})
    W.tick("owner")
    assert started == [] and asked == []                          # off by default
    W.save({**W.state(cfg), "on": True}, cfg)
    W.tick("someone else")
    assert started == []                                           # the owner's only
    W.tick("owner")
    assert started and started[0][1] == "evidentia" and W.state(cfg)["tries"] == {"7": 1}
    W.tick("owner")
    assert len(started) == 1                                       # not before ten minutes
    st = W.state(cfg); st["started_at"] = 0; st["tries"]["7"] = W.TRIES; W.save(st, cfg)
    W.tick("owner")
    assert ("DELETE", "/leads/7") in asked and W.state(cfg)["last"][0]["result"] == "dropped"


def test_a_lead_run_is_kept_to_evidentia_local_and_stops_when_the_worker_is_switched_off(cfg, monkeypatch):
    """Audit A1–A4, 11 Nov: no built-in tools, the local model, the owner first, 🛑 and «off» stop the running lead."""
    from types import SimpleNamespace
    import aurora.agt_loop as L
    import sys
    import aurora.api.core  # noqa: F401
    core = sys.modules["aurora.api.core"]          # the module the code imports from (a test may have reloaded it)
    monkeypatch.setattr(W.sys_config, "get", lambda: cfg)
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    W.save({"on": True, "tries": {}, "last": []}, cfg)
    made = {}

    class FakeAgent:
        def __init__(self, *a, **k):
            made["agent"], self.ledger = self, []

        def run(self, goal, emit, run_id, context=""):
            made["on"] = self.cancelled()
            W.save({**W.state(cfg), "on": False}, cfg)            # the owner switches it off mid-run
            made["off"] = self.cancelled()
            return SimpleNamespace(text="done")
    monkeypatch.setattr(L, "Agent", FakeAgent)
    monkeypatch.setattr(core, "pipeline", lambda: None)
    monkeypatch.setattr(core, "plugin_host", lambda: None)
    monkeypatch.setattr(core, "_runs", {})
    monkeypatch.setattr(W, "_ask", lambda *a, **k: {"status": "done"})
    W._job({"id": 3, "what": "x", "token": "t"}, "You are the sniper.")("q", lambda *a: None, "r9")
    a = made["agent"]
    assert a.loop_tools == set() and a.local_only and a.between is not None
    assert made["on"] is False and made["off"] is True
