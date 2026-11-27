# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C746 (owner, 27 Nov: «chiuso con attesa»): a text the local model could not look at for personal data never goes to
a cloud model — the look tried again for a while, then refused; behind Fallback the local model answers. A name no
fixed rule sees never leaves while the local model is down."""
import pytest

from aurora import mdl_router as R
from aurora import sec_mask_spot


class Cloud:
    name, model = "cloudy", "big"

    def __init__(self):
        self.sent = []

    def complete(self, system, user, max_tokens, think=False):
        self.sent.append(user)
        return R.Completion("ok", "", 1, 0.1, False)


class Local:
    name, model = "local", "small"

    def complete(self, system, user, max_tokens, think=False):
        return R.Completion("the local answer", "", 1, 0.1, False)


@pytest.fixture
def quick(monkeypatch, cfg):
    monkeypatch.setattr(R, "MASK_WAIT_S", 0.05)
    monkeypatch.setattr(R, "MASK_STEP_S", 0.01)
    cfg.values["AURORA_CLOUD_MASK_DYNAMIC"] = True
    return cfg


def test_the_local_model_down_nothing_leaves(quick, monkeypatch):
    monkeypatch.setattr(sec_mask_spot, "_ask", lambda cfg, chunk: None)          # down: it never answers
    cloud = Cloud()
    with pytest.raises(R.MaskUnseen):
        R.MaskedLLM(cloud, "reasoner", quick).complete("sys", "Ho parlato con Gianfranco Zappalà ieri", 100)
    assert cloud.sent == []                                                     # the name never left
    out = R.Fallback(R.MaskedLLM(cloud, "reasoner", quick), Local(), "reasoner", None).complete("sys", "Gianfranco Zappalà", 100)
    assert out.answer == "the local answer" and cloud.sent == []


def test_it_waits_and_sends_once_the_local_model_looked(quick, monkeypatch):
    calls = []

    def ask(cfg, chunk):
        calls.append(1)
        return None if len(calls) == 1 else ["Gianfranco Zappalà"]               # busy first, then it answers
    monkeypatch.setattr(sec_mask_spot, "_ask", ask)
    monkeypatch.setattr(sec_mask_spot, "_learn", lambda cfg, told: None)
    sec_mask_spot._seen.clear()
    monkeypatch.setattr(R, "MASK_WAIT_S", 1.0)
    cloud = Cloud()
    R.MaskedLLM(cloud, "reasoner", quick).complete("sys", "Ho parlato con Gianfranco Zappalà ieri", 100)
    assert cloud.sent and "Zappalà" not in cloud.sent[0] and "[PRIVATE_" in cloud.sent[0]


def test_the_owner_s_choice_without_the_dynamic_look_is_kept(quick, monkeypatch):
    quick.values["AURORA_CLOUD_MASK_DYNAMIC"] = False                            # off: the fixed rules alone, as set
    monkeypatch.setattr(sec_mask_spot, "_ask", lambda cfg, chunk: None)
    cloud = Cloud()
    R.MaskedLLM(cloud, "reasoner", quick).complete("sys", "una frase qualsiasi", 100)
    assert cloud.sent == ["una frase qualsiasi"]


def test_a_machine_without_a_local_model_masks_by_the_fixed_rules_and_answers(quick, monkeypatch):
    """C761 (the Mac install's CI, 27 Nov): AURORA_LLM_BACKEND=cloud has no local model to look, ever — every cloud
    question waited a minute and was refused. There the fixed rules mask, as before C746, and the answer comes."""
    quick.values["AURORA_LLM_BACKEND"] = "cloud"
    monkeypatch.setattr(sec_mask_spot, "_ask", lambda cfg, chunk: pytest.fail("no local model to ask"))
    cloud = Cloud()
    out = R.MaskedLLM(cloud, "reasoner", quick).complete("sys", "scrivi a mario.rossi@example.com", 100)
    assert out.answer == "ok" and cloud.sent and "mario.rossi@example.com" not in cloud.sent[0]
