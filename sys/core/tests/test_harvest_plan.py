# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What is left to harvest and the room it takes (kno_harvest_plan): totals asked of the sources, the weight of a
document measured in the vault, a source without a total said «not measured», never guessed."""
from types import SimpleNamespace

from aurora import kno_harvest_plan as P, kno_sources


def test_left_times_the_measured_weight_and_the_unknown_said(cfg, monkeypatch):
    monkeypatch.setattr(kno_sources, "modes", lambda c: {"ai": "round", "law": "round", "off_one": "off"})
    monkeypatch.setattr(kno_sources, "specs", lambda c, d: [("0", {"source": "arxiv", "categories": ["cs.AI", "cs.LG"]})]
                        if d == "ai" else [("0", {"source": "normattiva"})])
    monkeypatch.setattr(kno_sources, "progress", lambda c, d: {"taken": 100 if d == "ai" else 50, "done": False})
    monkeypatch.setattr(P, "_weight", lambda c, d: {"docs": 10, "chunks": 200, "bytes": 1_000_000, "per_doc": 100_000})
    xml = {"cs.AI": 1000, "cs.LG": 500}

    def fetch(url, **p):
        q = p.get("search_query", "")
        if "sortBy" in p:                                         # the newest of each archive
            return SimpleNamespace(text="<entry><id>http://arxiv.org/abs/2610.13948v1</id></entry>")
        return SimpleNamespace(text=f"<opensearch:totalResults>{xml[q[4:]]}</opensearch:totalResults>")
    plan = P.build(fetch, cfg)
    ai, law = plan["domains"]
    assert ai["available"] == 1500 and ai["left"] == 1400 and ai["projected_bytes"] == 140_000_000
    assert law["available"] is None and law["unknown"] == ["normattiva"] and law["projected_bytes"] is None
    assert plan["arxiv_newest"] == "2610.13948"
    assert [d["domain"] for d in plan["domains"]] == ["ai", "law"]                  # «off» is not planned
