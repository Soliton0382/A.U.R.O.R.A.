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
