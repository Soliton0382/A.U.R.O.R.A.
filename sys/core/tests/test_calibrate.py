# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C229: the candidates a CPU re-ranks for one question, from its measured speed (law 2: the ceiling first)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import sys_calibrate as C  # noqa: E402


def test_the_candidates_fit_the_budget_between_the_floor_and_the_profile(cfg, monkeypatch):
    import aurora.mdl_reranker as R
    speed = {"s": 0.0}

    class Fake:
        def __init__(self, cfg):
            pass

        def score(self, pairs):
            time.sleep(speed["s"] * len(pairs))
    monkeypatch.setattr(R, "Reranker", Fake)
    monkeypatch.setattr(C, "BUDGET_S", 0.4)                  # the rule, at a test's scale
    low = C.floor(cfg)
    assert low == cfg.specs["AURORA_SEARCH_CANDIDATES"]["min"]          # the settings' own floor: always loadable
    speed["s"] = 0.4 / (low + 2)                                     # low + 2 fit in 0.4 s
    assert low <= C.measure(cfg)["candidates"] <= low + 2
    speed["s"] = 0.02                                          # 20 fit
    assert 17 <= C.measure(cfg)["candidates"] <= 20
    speed["s"] = 0.2                                           # 2 would fit: never under the floor
    assert C.measure(cfg)["candidates"] == low
    speed["s"] = 0.0                                           # a fast CPU: never over the profile's 30
    assert C.measure(cfg)["candidates"] == C.CEILING


def test_the_tiers_follow_cores_and_memory():
    assert C.tier(4, 32) == "light" and C.tier(16, 8) == "light"          # the colleague's 4 cores; a small memory
    assert C.tier(10, 16) == "standard" and C.tier(16, 64) == "strong"


def test_the_harvest_fits_its_share_of_the_cpu(cfg, monkeypatch):
    """A round's indexing within HARVEST_SHARE of the interval, never over the recommended 10 a source."""
    monkeypatch.setattr(C, "active_share", lambda c: 1.0)
    cfg.values["AURORA_HARVEST_INTERVAL_H"] = 6
    room = C.HARVEST_SHARE["light"] * 6 * 3600
    slow = 3.0                                                          # s a passage: 2 cores of the test VM, C229
    got = C.per_category(cfg, slow, "light")
    assert got == int(room / (C.DOCS_PER_UNIT * C.PASSAGES_PER_DOC * slow)) and 1 <= got < C.PER_CATEGORY_MAX
    assert C.per_category(cfg, 0.05, "strong") == C.PER_CATEGORY_MAX     # a fast CPU: the recommended value
    assert C.per_category(cfg, 1000.0, "light") == 1                     # never 0: the harvest still moves
    monkeypatch.setattr(C, "active_share", lambda c: 0.1)               # fewer areas chosen: more each
    assert C.per_category(cfg, slow, "light") > got


def test_the_audit_writes_what_it_measured(cfg, monkeypatch):
    import sys_profile
    monkeypatch.setattr(C, "measure", lambda c: {"seconds_per_passage": 1.48, "candidates": 10})
    monkeypatch.setattr(C, "measure_encoder", lambda c: 3.0)
    monkeypatch.setattr(C, "active_share", lambda c: 1.0)
    monkeypatch.setattr(sys_profile, "ram_gb", lambda: 16.0)
    monkeypatch.setattr(C.os, "cpu_count", lambda: 2)
    out = C.audit(cfg)
    assert out["tier"] == "light" and out["env"]["AURORA_SEARCH_CANDIDATES"] == "10"
    assert out["env"]["AURORA_EMBEDDER_BATCH"] == "4" and int(out["env"]["AURORA_HARVEST_PER_CATEGORY"]) < 10


def test_the_installers_line_says_the_tier_and_the_numbers():
    out = {"tier": "light", "cores": 2, "ram_gb": 16.0, "rerank_s_per_passage": 1.48, "encode_s_per_passage": 3.0,
           "env": {"AURORA_SEARCH_CANDIDATES": "10", "AURORA_HARVEST_PER_CATEGORY": "6", "AURORA_EMBEDDER_BATCH": "4"}}
    assert C.summary(out, "it") == ("profilo leggero: 2 core, 16.0 GB; ricerca 10 candidati (1.48 s/passaggio), "
                                    "raccolta 6 per fonte a giro (3.0 s/passaggio), batch 4")
