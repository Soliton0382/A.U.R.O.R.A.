# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C516: the conductor answers in the language the user wrote in, not the installation's default."""
import asyncio
import importlib
import sys

from aurora import sys_config


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def _api(cfg, monkeypatch):
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "projects_conduct"):
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import projects_conduct as P
    return P


def test_the_talk_follows_the_words_language(cfg, monkeypatch):
    P = _api(cfg, monkeypatch)
    from aurora import prj_talk
    seen = []
    monkeypatch.setattr(P, "_check", lambda name: None)
    monkeypatch.setattr(P, "pipeline", lambda: None)
    monkeypatch.setattr(prj_talk, "say", lambda cfg, name, words, pipe, lang: seen.append(lang) or {"backend": "local"})

    async def direct(fn, *a):
        return fn(*a)
    monkeypatch.setattr(P, "in_thread", direct)
    asyncio.run(P.talk_say("p", _Req({"text": "Please design a resonator and tell me how you will test it."})))
    asyncio.run(P.talk_say("p", _Req({"text": "Progetta un risuonatore e dimmi come lo verificherai, per favore."})))
    assert seen == ["en", "it"]
