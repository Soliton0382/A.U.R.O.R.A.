# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The top bar's new figures (owner, 2026-10-13): the cloud calls under way and of the last minute, and the network's
traffic as bytes a second and a share of the link."""
from types import SimpleNamespace

from aurora import mdl_router, sys_metrics


def test_a_cloud_call_is_counted_while_it_runs_and_in_the_last_minute(cfg):
    seen = {}

    class Inner:
        name, model = "claude_code", "sonnet"

        def complete(self, system, user, max_tokens, think=False):
            seen["during"] = mdl_router.cloud_live()["active"]
            return SimpleNamespace(answer="ok, done", thought="", tokens=3, seconds=0.1, truncated=False)

    before = mdl_router.cloud_live()
    mdl_router.MaskedLLM(Inner(), "synthesis", cfg).complete("system", "a question", 50)
    after = mdl_router.cloud_live()
    assert seen["during"] == before["active"] + 1 and after["active"] == before["active"]
    assert after["calls"] == before["calls"] + 1 and "claude_code" in after["providers"]
    assert after["received"] - before["received"] == len("ok, done") and after["sent"] > before["sent"]


def test_the_network_is_a_rate_between_two_samples(monkeypatch):
    counts = iter([(1_000, 500, 1000), (1_000 + 250_000, 500 + 50_000, 1000)])
    monkeypatch.setattr(sys_metrics, "_net_bytes", lambda: next(counts))
    monkeypatch.setitem(sys_metrics._state, "net", None)
    first = sys_metrics._net(100.0)
    assert first["rx_bps"] is None                                   # one sample: no rate yet
    n = sys_metrics._net(102.0)
    assert n == {"rx_bps": 125_000, "tx_bps": 25_000, "link_mbps": 1000, "pct": 0.1}


def test_who_uses_the_gpus_comes_from_pmons_own_columns(monkeypatch):
    monkeypatch.setattr(sys_metrics, "_service_of", lambda pid: {"7": "llm", "8": "models"}.get(pid, "other"))
    got = sys_metrics._gpu_by_service("""# gpu pid type sm mem enc dec jpg ofa fb ccpm command
# Idx # C/G % % % % % % MB MB name
    0 7 C 55 28 - - - - 15158 0 llama
    1 7 C 38 21 - - - - 8932 0 llama
    1 8 C 2 0 - - - - 2424 0 python
    1 - - - - - - - - - - -""")
    assert got["0"] == [{"who": "llm", "util_pct": 55, "used_mib": 15158}]
    assert [r["who"] for r in got["1"]] == ["llm", "models"]


def test_who_says_only_the_services_names_and_lives_without_cgroups(cfg, monkeypatch):
    monkeypatch.setattr(sys_metrics, "_cpu_by_service", lambda: {})
    monkeypatch.setattr(sys_metrics, "_gpu_by_service", lambda: {})
    got = sys_metrics.who(cfg, runs_open=2, window=0.01)
    assert got["cpu"] == [] and got["gpus"] == {} and got["doing"][0] == {"what": "runs", "n": 2}
