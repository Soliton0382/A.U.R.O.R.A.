# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C229 (the Windows VM, 9 Oct): a client without streaming waited for the memory's indexing after the answer
(60-69 s behind the harvest). The OpenAI-compatible endpoint answers at answer.final."""
import asyncio
import json
import threading


def test_the_answer_goes_out_before_the_run_ends(cfg, monkeypatch):
    import importlib
    import sys
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)               # the API reads the settings at import: a clone has no .env
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    oai = importlib.import_module("aurora.api.oai")
    run = {"id": "r1", "cond": threading.Condition(), "done": False, "answer": None,
           "events": [{"event": "route", "payload": {"mode": "knowledge"}},
                      {"event": "answer.final", "payload": {"text": "Un solitone è un'onda [1].",
                                                            "sources": [{"n": 1, "title": "Solitone", "source": "wikipedia:Solitone",
                                                                         "domain": "web"}]}}]}
    monkeypatch.setattr(oai, "start_run", lambda q, origin, job: run)            # the memory is still being written

    class Req:
        async def json(self):
            return {"messages": [{"role": "user", "content": "Che cos'è un solitone?"}]}
    out = asyncio.run(asyncio.wait_for(oai.chat_completions(Req()), 10))
    text = json.loads(out.body)["choices"][0]["message"]["content"]
    assert text.startswith("Un solitone") and "[1] Solitone (web)" in text and not run["done"]
