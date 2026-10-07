# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How much to think (kno_think): each question goes the way of its kind; the vault mode stays as before."""
from types import SimpleNamespace

import pytest

from aurora import kno_think as T

READ = {"text": "ok [1]", "sources": [{"n": 1, "url": "https://x"}], "dropped": []}


def _same(r):
    return r is not None and {k: r[k] for k in READ} == READ


@pytest.fixture
def run(monkeypatch):
    def go(mode, kind, web=None, vault=None, memory=None, deep=None):
        calls, events = [], []
        monkeypatch.setattr(T.kno_read, "kind", lambda p, q: kind)
        monkeypatch.setattr(T.kno_read, "from_web", lambda p, q, ev, size="fact", open_pages=True, translation=None:
                            calls.append(f"web({size},{'pages' if open_pages else 'snippets'})") or web)
        monkeypatch.setattr(T.kno_read, "from_vault", lambda p, q, hits, size="explain": calls.append(f"vault({size})") or vault)
        monkeypatch.setattr(T.kno_read, "from_memory", lambda p, q, ev: calls.append("memory") or memory)

        def retrieve(recall):
            calls.append("search")
            return ["h"], []

        def classic(h, s):
            calls.append("deep")
            return deep
        out = T.answer(SimpleNamespace(cfg={}), "q", None, mode, retrieve, classic,
                       lambda e, pl: events.append(pl) if e == "think" else None)
        return out, calls, events[-1]
    return go


def test_vault_is_the_pipeline_of_before(run):
    (r, a, _, _), calls, ev = run("vault", "fact", deep=("x", [], []))
    assert r is None and a == ("x", [], []) and calls == ["search", "deep"] and ev["used"] == "vault"


def test_a_fact_goes_to_the_web_without_searching_the_vault(run):
    (r, a, _, _), calls, ev = run("auto", "fact", web=READ)
    assert _same(r) and calls == ["web(fact,pages)"] and ev["why"] == "un fatto da cercare → web"


def test_light_reads_only_the_snippets(run):
    _, calls, _ = run("light", "fact", web=READ)
    assert calls == ["web(fact,snippets)"]


def test_an_explanation_reads_the_vault_then_the_web(run):
    (r, _, _, _), calls, ev = run("auto", "explain", vault=None, web=READ)
    assert _same(r) and calls == ["search", "vault(explain)", "web(explain,pages)"] and ev["why"].endswith("→ web")


def test_a_case_goes_deep_in_auto_but_not_in_medium(run):
    (_, a, _, _), calls, ev = run("auto", "case", deep=("profonda", [], []))
    assert a == ("profonda", [], []) and calls == ["search", "deep"] and ev["why"] == "un caso → deep"
    _, calls, _ = run("medium", "case", vault=READ)
    assert "deep" not in calls and calls[-1] == "vault(explain)"


def test_no_source_then_memory_marked_never_silence(run):
    (r, a, _, _), calls, ev = run("auto", "fact", memory=READ)
    assert _same(r) and calls == ["web(fact,pages)", "search", "vault(fact)", "memory"] and ev["why"].endswith("→ memory")
    (r, a, _, _), _, ev = run("auto", "fact")
    assert r is None and a is None and ev["why"].endswith("nessuna fonte")


def test_an_unknown_mode_is_the_vault():
    assert T.mode_of({"AURORA_ANSWER_MODE": "turbo"}, None) == "vault" and T.mode_of({"AURORA_ANSWER_MODE": "vault"}, "AUTO") == "auto"


def test_a_source_that_breaks_does_not_break_the_answer(run, monkeypatch):
    def boom(*a, **k):
        raise TypeError("a bug in a source")
    monkeypatch.setattr(T.kno_read, "from_web", boom)
    monkeypatch.setattr(T.kno_read, "kind", lambda p, q: "fact")
    events = []
    out = T.answer(SimpleNamespace(cfg={}), "q", None, "auto", lambda r: (["h"], []), lambda h, s: None,
                   lambda e, pl: events.append(e))
    assert "read.failed" in events and events[-1] == "think"            # it went on: the vault, then memory


def test_an_explanation_the_vault_lacked_is_studied_at_night_a_fact_is_not(run):
    (r, _, _, _), _, _ = run("auto", "explain", vault=None, web=READ)
    assert r["came_from"] == "web" and r["learn"] is True
    (r, _, _, _), _, _ = run("auto", "fact", web=READ)
    assert r["came_from"] == "web" and r["learn"] is False            # a fact: the cache is enough
    (r, _, _, _), _, _ = run("auto", "explain", vault=READ)
    assert r["came_from"] == "vault" and r["learn"] is False
