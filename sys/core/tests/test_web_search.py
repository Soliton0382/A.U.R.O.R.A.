# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The web search, one for the answers and the agent's tool (kno_web.search, C368): Brave Search first when the
machine has its key, else — and when Brave fails or finds nothing — ddgs with no key; nothing found said to the agent
with the way out (fetch_url on the known sources)."""
import importlib.util
from pathlib import Path

import httpx
import pytest

from aurora import kno_web

SERVER = Path(__file__).resolve().parents[2] / "plugins" / "web" / "server.py"
FREE = [{"title": "Nebulosa Pellicano", "href": "https://it.wikipedia.org/wiki/x", "body": "IC 5070"}]


@pytest.fixture
def web():
    spec = importlib.util.spec_from_file_location("web_server", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def engines(monkeypatch):
    """ddgs and Brave answering as told; what each was asked."""
    seen = {"ddgs": 0, "brave": 0}
    state = {"free": FREE, "brave": 200}

    class DDGS:
        def text(self, q, region, max_results, backend):
            seen["ddgs"] += 1
            return list(state["free"])

    def get(url, params=None, headers=None, timeout=None):
        seen["brave"] += 1
        return httpx.Response(state["brave"], request=httpx.Request("GET", url),
                              json={"web": {"results": [{"title": "B", "url": "https://b.example", "description": "d"}]}})
    import ddgs
    monkeypatch.setattr(ddgs, "DDGS", DDGS)
    monkeypatch.setattr(kno_web.httpx, "get", get)
    monkeypatch.setattr(kno_web.time, "sleep", lambda s: None)
    return seen, state


def test_without_a_key_the_keyless_engines_search(engines, monkeypatch, web):
    seen, state = engines
    monkeypatch.setattr(kno_web, "brave_key", lambda: "")
    assert web.search("nebulosa").startswith("Nebulosa Pellicano\nhttps://it.wikipedia.org") and seen["brave"] == 0
    state["free"] = []
    with pytest.raises(Exception, match="no results.*fetch_url"):
        web.search("nebulosa")


def test_with_its_key_brave_answers_for_everyone_and_ddgs_when_it_fails(engines, monkeypatch, web):
    seen, state = engines
    monkeypatch.setattr(kno_web, "brave_key", lambda: "b" * 30)
    assert kno_web.search("nebulosa")[0]["url"] == "https://b.example" and seen["ddgs"] == 0     # the answers
    assert web.search("nebulosa").startswith("B\nhttps://b.example")                             # the agent's tool
    state["brave"] = 429                                                                         # over its quota
    assert kno_web.search("nebulosa")[0]["url"] == "https://it.wikipedia.org/wiki/x" and seen["ddgs"] == 1


def test_the_key_from_the_plugin_s_own_environment(monkeypatch):
    monkeypatch.setenv("AURORA_BRAVE_SEARCH_KEY", "k" * 30)
    assert kno_web.brave_key() == "k" * 30
