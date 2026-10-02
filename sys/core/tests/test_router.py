# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import pytest

from aurora import mdl_router as R
from aurora.mdl_llm import Completion


class Fake:
    name, model = "fake", "m"

    def __init__(self, fail=False):
        self.fail, self.seen = fail, []

    def complete(self, system, user, max_tokens, think=False):
        if self.fail:
            raise RuntimeError("provider down")
        self.seen.append(system + "\n" + user)
        return Completion(f"risposta su {user.split()[-1]}", "", 3, 0.1, False)


def test_without_a_choice_the_old_two_settings_decide(cfg):
    cfg.values.update(AURORA_REASONER_PROVIDER="claude_code", AURORA_CLOUD_ROLES="synthesis,agent")
    a = R.assignments(cfg)
    assert a["synthesis"]["provider"] == "claude_code" and a["agent"]["provider"] == "claude_code"
    assert a["route"]["provider"] == "local" and a["vision"]["provider"] == "local"
    a = R.set_assignments(cfg, {"forge_judge": {"provider": "xai", "model": "grok-x"}})
    assert R.assignments(cfg)["forge_judge"] == {"provider": "xai", "model": "grok-x"}
    with pytest.raises(ValueError):
        R.set_assignments(cfg, {"synthesis": {"provider": "acme"}})


def test_rule_9_keeps_everything_local_without_the_exemption(cfg, monkeypatch):
    R.set_assignments(cfg, {"synthesis": {"provider": "openai", "model": "gpt-x"}})
    local = object()
    monkeypatch.setattr(R.sys_ethics, "exempt", lambda c: False)
    assert R.model_for("synthesis", local, cfg) is local
    monkeypatch.setattr(R.sys_ethics, "exempt", lambda c: True)
    m = R.model_for("synthesis", local, cfg)
    assert isinstance(m, R.Fallback) and isinstance(m.primary, R.MaskedLLM) and m.primary.name == "openai"
    assert R.model_for("route", local, cfg) is local


def test_the_cloud_sees_masked_text_and_aurora_gets_the_real_one_back(cfg):
    inner = Fake()
    m = R.MaskedLLM(inner, "synthesis", cfg)
    out = m.complete("sys", "il server 192.168.1.20", 50)
    assert "192.168" not in inner.seen[0] and "[IP_1]" in inner.seen[0]
    assert out.answer == "risposta su 192.168.1.20"


def test_a_provider_down_falls_back_to_the_local_model(cfg):
    local = Fake()
    m = R.Fallback(R.MaskedLLM(Fake(fail=True), "gate", cfg), local, "gate")
    assert m.complete("s", "domanda pippo", 10).answer == "risposta su pippo" and local.seen
