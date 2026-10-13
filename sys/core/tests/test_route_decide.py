# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The router's choice read from one token's probabilities (M197, M199): the same decisions, half the time."""
import math

from aurora import mdl_llm


class R:
    def __init__(self, top):
        self.top = top

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": [
            {"token": t, "logprob": math.log(p)} for t, p in self.top]}]}}]}


def _llm(cfg, monkeypatch, top):
    sent = {}
    monkeypatch.setattr(mdl_llm.httpx, "post", lambda url, **kw: sent.update(kw["json"]) or R(top))
    llm = mdl_llm.LLM(cfg)
    monkeypatch.setattr(mdl_llm.LLM, "fmt", property(lambda self: type("F", (), {"template": "chatml"})()))
    return llm, sent


def test_the_first_token_of_an_option_counts_for_it(cfg, monkeypatch):
    llm, sent = _llm(cfg, monkeypatch, [("SELF", 0.6), ("KN", 0.3), ("KNOWN", 0.05), ("The", 0.05)])
    out = llm.decide("sys", "LAST MESSAGE: x", ["SELF", "KNOWLEDGE"])
    assert sent["max_tokens"] == 1 and sent["logprobs"] and sent["chat_template_kwargs"] == {"enable_thinking": False}
    assert round(out["SELF"], 3) == round(0.6 / 0.9, 3)          # «KNOWN» is not KNOWLEDGE's start and round(sum(out.values()), 6) == 1


def test_an_answer_that_is_no_option_asks_in_words(cfg, monkeypatch):
    llm, _ = _llm(cfg, monkeypatch, [("Here", 0.7), ("The", 0.3)])
    assert llm.decide("sys", "u", ["SELF", "KNOWLEDGE"]) is None


def test_a_model_without_it_is_asked_in_words():
    from aurora.mdl_budget import Metered
    assert Metered(object(), "route").decide("s", "u", ["TOOLS", "NO"]) is None
