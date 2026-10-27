# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The reasoner stopped on purpose for a GPU job is never a red light (C157, C409: the owner saw red while a song was
sung — the reasoner stopping, and starting again and loading, were not «inactive»)."""
import pytest

from aurora import sys_health


@pytest.mark.parametrize("state", ["deactivating", "inactive", "activating", "active"])
def test_every_state_of_the_swap_is_a_planned_pause(cfg, monkeypatch, state):
    monkeypatch.setattr(sys_health, "_unit", lambda u: state if u == "aurora-llm" else "active")
    monkeypatch.setattr(sys_health, "_http", lambda url: (False, "refused") if str(cfg["AURORA_LLM_PORT"]) in url else (True, "HTTP 200"))
    monkeypatch.setattr(sys_health, "_https", lambda d, p: (True, "HTTP 200"))
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "song luce-eterna since 22:21:00")
    llm = next(i for i in sys_health.check(cfg)["items"] if i["name"] == "aurora-llm")
    assert llm["level"] == "ok" and "lavoro sulla GPU" in llm["text"]


def test_without_a_gpu_job_a_silent_reasoner_is_down(cfg, monkeypatch):
    monkeypatch.setattr(sys_health, "_unit", lambda u: "inactive" if u == "aurora-llm" else "active")
    monkeypatch.setattr(sys_health, "_http", lambda url: (False, "refused") if str(cfg["AURORA_LLM_PORT"]) in url else (True, "HTTP 200"))
    monkeypatch.setattr(sys_health, "_https", lambda d, p: (True, "HTTP 200"))
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "")
    llm = next(i for i in sys_health.check(cfg)["items"] if i["name"] == "aurora-llm")
    assert llm["level"] == "down"
