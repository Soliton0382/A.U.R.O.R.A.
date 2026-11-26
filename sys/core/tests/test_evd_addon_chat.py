# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
# Evidentia's chat answered by an agent — its context, its tools, what it saves.
import importlib
from types import SimpleNamespace

import pytest

from aurora import sys_addons

C = None


@pytest.fixture(autouse=True)
def _addon(cfg, monkeypatch):
    """The add-on's modules, loaded as Aurora loads them, on the test's configuration (api.core reads it at import)."""
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    sys_addons.module("evidentia")
    global C
    C = importlib.import_module("aurora_addon_evidentia.evd_chat")


def test_the_chat_agent_has_evidentias_tools_only_and_saves_into_the_case(cfg, monkeypatch):
    import aurora.agt_loop as L
    import sys
    import aurora.api.core  # noqa: F401
    core = sys.modules["aurora.api.core"]          # the module the code imports from (a test may have reloaded it)
    saved, made = [], {}

    def ask(method, path, body=None):
        if path.startswith("/cases/") and path.endswith("/steps"):
            saved.append(body)
            return {"step": 1}
        if path == "/docids":                          # the collections Evidentia is configured with (docids.json)
            return {"collections": [{"name": "EFTA", "pattern": "^(EFTA\\d{8})(?:_dup_\\d+)?$", "upper": True}]}
        if path.startswith("/leads"):
            return {"leads": [{"id": 4, "agent": "sniper", "status": "done", "what": "who owned it", "summary": "JEGE Inc."}]}
        return {"id": "abcdef123456", "title": "Flotta", "diary": [{"kind": "search", "content": {"q": "N908JE"}}]}

    class FakeAgent:
        def __init__(self, *a, **k):
            made["agent"] = self
            self.ledger = []

        def run(self, goal, emit, run_id, context=""):
            made["goal"] = goal
            return SimpleNamespace(text="JEGE Inc. held it (EFTA00087596 p. 2).")
    monkeypatch.setattr(C, "_ask", ask)
    monkeypatch.setattr(C, "_RULES", None)            # read again from this test's /docids
    monkeypatch.setattr(L, "Agent", FakeAgent)
    monkeypatch.setattr(core, "pipeline", lambda: None)
    monkeypatch.setattr(core, "plugin_host", lambda: None)
    monkeypatch.setattr(C.__dict__.get("sys_config", None) or __import__("aurora.sys_config", fromlist=["x"]), "get", lambda: cfg)
    C.job("abcdef123456", "Chi possedeva l'aereo?")("q", lambda *a: None, "run1")
    assert made["agent"].allow == {C.PLUGIN} and made["agent"].max_steps == C.STEPS
    a = made["agent"]                                  # audit A1–A4, 11 Nov
    assert a.loop_tools == set() and a.local_only and a.between is not None and a.cancelled() is False
    assert "lead #4" in made["goal"] and "Chi possedeva" in made["goal"] and "victims" in made["goal"]
    fence = made["goal"].split("<<<DATA\n", 1)[1].split("\nDATA>>>", 1)
    assert "JEGE Inc." in fence[0] and C.AFTER in fence[1]          # the leads' words as data, the rules after (B35)
    assert saved[0] == {"kind": "question", "text": "Chi possedeva l'aereo?"}
    assert saved[1]["kind"] == "answer" and saved[1]["docs"] == ["EFTA:EFTA00087596"]


def test_the_report_is_written_in_the_readers_language():
    """Owner, 10 Nov: «in base alla lingua selezionata dall'utente»: the report in it_IT is Italian, quotes kept."""
    assert "ITALIAN" in C.language("it_IT") and "quote them" in C.language("it_IT")
    assert "ENGLISH" in C.language("en_US") and "ITALIAN" in C.language("xx")


def test_the_page_reaches_the_reopen_of_a_lead_and_never_its_report():
    """B20 of Evidentia: the owner's page reopens a cold lead; the report (a worker's, with its token) stays out."""
    ALLOWED = importlib.import_module("aurora_addon_evidentia.api_evidentia").ALLOWED
    assert ALLOWED.fullmatch("leads/12/reopen") and ALLOWED.fullmatch("leads/12") and ALLOWED.fullmatch("leads")
    assert not ALLOWED.fullmatch("leads/12/report") and not ALLOWED.fullmatch("leads/claim")
