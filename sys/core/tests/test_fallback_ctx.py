# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C331, found by Aurora's own self-repair: a cloud agent call that fails hands 34,204 tokens to a local slot of 32,768
(400 from llama-server). Her tests from the sandbox fallback-ctx-10c9d2, and the budget path and whole steps."""
from aurora import mdl_fit
from aurora import mdl_router as R

CFG = {"AURORA_LLM_CTX": 32768, "AURORA_LLM_PARALLEL": 1}


def long_run(steps=10):
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "GOAL"}]
    for i in range(steps):
        msgs.append({"role": "assistant", "content": "call %d" % i})
        msgs.append({"role": "tool", "content": "x" * 10000})
    return msgs


def test_a_long_run_is_shortened_for_the_local_window():
    msgs = long_run()
    assert mdl_fit.used(msgs) > 32768
    out, max_tokens = mdl_fit.fit(msgs, 1500, mdl_fit.window(CFG))
    assert max_tokens == 1500 and mdl_fit.used(out) + 1500 + 256 <= 32768
    assert out[:2] == msgs[:2] and out[-4:] == msgs[-4:]
    assert msgs[3]["content"] == "x" * 10000                 # the caller's list is not touched


def test_a_short_run_is_left_alone():
    msgs = long_run(1)
    assert mdl_fit.fit(msgs, 1500, 32768) == (msgs, 1500)


def test_a_dropped_step_takes_its_results_and_the_slots_share_the_window():
    msgs = long_run(30)
    out, _ = mdl_fit.fit(msgs, 1500, mdl_fit.window({**CFG, "AURORA_LLM_PARALLEL": 2}))
    assert mdl_fit.used(out) + 1500 + 256 <= 16384
    assert out[2]["role"] == "assistant"


class Local:
    def complete_turns(self, messages, max_tokens, think=False):
        self.got = (messages, max_tokens)
        return "local"


class Cloud:
    name = "cloud"

    def complete_turns(self, *a, **k):
        raise RuntimeError("a tool call it cannot parse")


def test_both_ways_to_the_local_model_fit_it(monkeypatch):
    from aurora import mdl_budget
    for over in (False, True):                                # the cloud failing, today's budget spent
        monkeypatch.setattr(mdl_budget, "over", lambda cfg, provider, o=over: o)
        local = Local()
        fb = R.Fallback(Cloud(), local, "agent", CFG)
        assert fb.complete_turns(long_run(), 1500, think=True) == "local"
        assert mdl_fit.used(local.got[0]) + local.got[1] + 256 <= 32768


def test_without_settings_nothing_changes():
    msgs = long_run()
    assert mdl_fit.fit(msgs, 1500, mdl_fit.window({})) == (msgs, 1500)


def test_the_last_turns_too_long_are_shortened_as_well():
    # C380: four long file reads at the end and a long prompt: 42,540 tokens to a slot of 32,768 after a cloud limit
    msgs = [{"role": "system", "content": "s" * 30000}, {"role": "user", "content": "GOAL"}]
    for i in range(3):
        msgs += [{"role": "assistant", "content": "read %d" % i}, {"role": "tool", "content": "y" * 20000}]
    out, max_tokens = mdl_fit.fit(msgs, 1500, 32768)
    assert mdl_fit.used(out) + max_tokens + 256 <= 32768
    assert out[0] == msgs[0] and out[-1]["content"].startswith("y" * 2000)


class TooLong:
    """A local server whose slot refuses the prompt (llama-server's 400)."""

    def complete_turns(self, messages, max_tokens, think=False):
        import httpx
        req = httpx.Request("POST", "http://local/v1/chat/completions")
        raise httpx.HTTPStatusError("400", request=req, response=httpx.Response(
            400, request=req, text='{"error":"request (42540 tokens) exceeds the available context size (32768 tokens)"}'))


def test_a_run_that_cannot_fit_stops_as_cloud_out(monkeypatch):
    # C385: the cloud ends mid-run; a run too long for the local slot, even shortened, stops with a clear word
    import pytest
    from aurora import mdl_budget
    monkeypatch.setattr(mdl_budget, "over", lambda cfg, provider: False)
    huge = [{"role": "system", "content": "s" * 100000}, {"role": "user", "content": "GOAL"}]
    with pytest.raises(mdl_fit.CloudOut):
        R.Fallback(Cloud(), Local(), "agent", CFG).complete_turns(huge, 1500, think=True)
    with pytest.raises(mdl_fit.CloudOut):                      # the local server's own refusal is renamed too
        R.Fallback(Cloud(), TooLong(), "agent", CFG).complete_turns(long_run(1), 1500, think=True)


def test_the_agent_stops_the_phase_with_cloud_out(cfg):
    from types import SimpleNamespace
    from aurora.agt_loop import Agent

    class Out:
        def complete_turns(self, *a, **k):
            raise mdl_fit.CloudOut("cloud esaurito: the run does not fit the local model's window")

    llm = Out()
    agent = Agent(SimpleNamespace(llm=llm, _for=lambda role: llm), cfg)
    agent.host = SimpleNamespace(plugins=lambda: [], get=lambda p: None)
    events = []
    ans = agent.run("lavora al progetto", lambda e, p: events.append(e), "r1")
    assert ans.text.startswith("☁️ Cloud esaurito") and "agent.cloud_out" in events and "agent.finish" in events
