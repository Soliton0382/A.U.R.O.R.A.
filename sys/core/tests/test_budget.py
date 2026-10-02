# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json

from aurora import mdl_budget as B
from aurora import mdl_router as R
from aurora.mdl_llm import Completion


class Cloud:
    name, model = "google", "gemini-x"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user, max_tokens, think=False):
        self.calls += 1
        return Completion("cloud", "", 10, 0.1, False)


class Local:
    name, model = "local", "qwen"

    def complete(self, system, user, max_tokens, think=False):
        return Completion("local", "", 7, 0.1, False)

    def stream(self, system, user, max_tokens, think=False):
        yield "answer", "ciao "
        yield "answer", "mondo"


def test_a_paid_provider_stops_at_the_daily_ceiling_and_the_local_model_answers(cfg):
    cfg.values["AURORA_CLOUD_DAILY_TOKENS"] = 1000
    cloud, local = Cloud(), Local()
    f = R.Fallback(cloud, local, "synthesis", cfg, "google")
    assert f.complete("s", "u", 10).answer == "cloud"
    assert B.record(cfg, "google", {"prompt_tokens": 600, "completion_tokens": 300}) == 900
    assert f.complete("s", "u", 10).answer == "cloud"                  # 900 < 1000
    B.record(cfg, "google", {"prompt_tokens": 100, "completion_tokens": 0})
    assert f.complete("s", "u", 10).answer == "local" and cloud.calls == 2   # ceiling reached: not called again today
    day = B.today(cfg)
    assert day["tokens"]["google"] == 1000 and day["stopped"] == ["google"] and day["calls"]["google"] == 2
    B.record(cfg, "claude_code", {"input_tokens": 10**9})
    assert not B.over(cfg, "claude_code")                               # the subscription has no ceiling
    cfg.values["AURORA_CLOUD_DAILY_TOKENS"] = 0
    assert not B.over(cfg, "google")                                    # 0 = no ceiling


def test_every_local_call_is_traced_with_its_step(cfg):
    m = B.Metered(Local(), "verify")
    assert m.complete("sys", "user", 5).answer == "local" and m.name == "local"     # the model as it is
    assert "".join(p for _, p in m.stream("s", "u", 5)) == "ciao mondo"
    trace = (cfg.path("AURORA_LOG_DIR") / "trace" / "llm_client.jsonl").read_text().splitlines()
    calls = [json.loads(l)["payload"] for l in trace if '"local.call"' in l]
    assert [c["role"] for c in calls] == ["verify", "verify"] and calls[0]["tokens_out"] == 7
    assert calls[0]["chars_in"] == len("sys") + len("user")
    assert B.tokens_of({"input_tokens": 5, "cache_creation_input_tokens": 2, "output_tokens": 3}) == 10
