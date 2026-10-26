# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📚 The publications plugin (owner, 26 Oct): the works found by ORCID, one reading kept a day, the change since
yesterday and a week ago told; and Oggi's greeting with the person's name and a sign of the day."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2] / "plugins" / "publications" / "server.py"


def load(cfg, monkeypatch, tmp_path, orcid="0000-0002-1825-0097"):
    from aurora import sys_config
    cfg.values.update(AURORA_PUBLICATIONS_ORCID=orcid, AURORA_PUBLICATIONS_DIR=str(tmp_path / "pub"))
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    spec = importlib.util.spec_from_file_location("publications_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def work(i, views, downloads):
    return {"id": f"zenodo:{i}", "source": "zenodo", "title": f"Un lavoro inventato {i}", "kind": "Preprint",
            "published": "2026-01-01", "url": f"https://doi.org/10.0/{i}", "views": views, "downloads": downloads}


def test_the_change_since_yesterday_and_a_week_ago_is_told(cfg, monkeypatch, tmp_path):
    P = load(cfg, monkeypatch, tmp_path)
    day0, counts = date(2026, 3, 1), {"1": (10, 2), "2": (5, 0)}
    monkeypatch.setattr(P, "_zenodo", lambda orcid: [work(k, *v) for k, v in counts.items()])

    def on(d):
        P._cache["works"] = None
        return {w["id"]: w for w in P.works(d)}
    first = on(day0)
    assert first["zenodo:1"]["day"] is None and "Prima lettura" in P.report(list(first.values()))
    counts.update({"1": (14, 3)})
    on(day0)                                                   # read again the same day: one row, the last wins
    counts.update({"1": (20, 4)})
    nxt = on(day0 + timedelta(days=1))
    assert nxt["zenodo:1"]["day"] == {"views": 6, "downloads": 1} and nxt["zenodo:2"]["day"] == {"views": 0, "downloads": 0}
    assert len(P._history()) == 2
    text = P.report(list(nxt.values()))
    assert "25 visite (+6 da ieri), 4 download (+1)" in text and "da ieri +6 visite, +1 download" in text
    counts.update({"1": (30, 4)})
    week = on(day0 + timedelta(days=7))
    assert week["zenodo:1"]["week"] == {"views": 16, "downloads": 1}    # against day 0, seven days before
    assert week["zenodo:1"]["day"] == {"views": 10, "downloads": 0}     # against day 1, the last one kept


def test_without_an_orcid_or_with_a_wrong_one_it_says_what_to_set(cfg, monkeypatch, tmp_path):
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="AURORA_PUBLICATIONS_ORCID"):
        load(cfg, monkeypatch, tmp_path, orcid="").works()
    with pytest.raises(ToolError, match="looks like"):
        load(cfg, monkeypatch, tmp_path, orcid="12345").works()


def test_the_greeting_s_sign_follows_the_weather_then_the_hour():
    from aurora.sns_weather import sign_of_day
    assert sign_of_day({"condition": "rain", "clouds_pct": 90}, 12)[0] == "🌧️"
    assert sign_of_day({"condition": "neutral", "clouds_pct": 80}, 23)[0] == "☁️"
    assert sign_of_day({"condition": "clear_mild", "clouds_pct": 5}, 23)[0] == "🌙"
    assert sign_of_day({"condition": "neutral", "clouds_pct": 40}, 10)[0] == "⛅"
    assert sign_of_day({"condition": "clear_mild", "clouds_pct": 5}, 10)[0] == "☀️"
    assert sign_of_day(None, 10)[0] == "👋" and sign_of_day(None, 22)[0] == "🌙"


def test_the_papers_tab_gets_each_work_day_by_day_and_its_versions(cfg, monkeypatch, tmp_path):
    import json
    P = load(cfg, monkeypatch, tmp_path)
    day0, counts = date(2026, 3, 1), {"1": (10, 2)}
    monkeypatch.setattr(P, "_zenodo", lambda orcid: [work(k, *v) for k, v in counts.items()])
    for i, v in enumerate((10, 12, 15)):
        counts["1"] = (v, 2)
        P._cache["works"] = None
        P.works(day0 + timedelta(days=i))
    monkeypatch.setattr(P, "date", type("D", (date,), {"today": staticmethod(lambda: day0 + timedelta(days=2))}))
    got = json.loads(P.publications_list(history_days=2))[0]
    assert [h["day"] for h in got["history"]] == ["2026-03-02", "2026-03-03"] and got["history"][-1]["views"] == 15
    assert "history" not in json.loads(P.publications_list())[0]          # the agent's list stays short
    assert len(json.loads(P.publications_list(history_days=9999))[0]["history"]) == 3   # at most a year: all three
    assert P._versions({"relations": {"version": [{"index": 1, "is_last": True}]}}) == 2
    assert P._versions({}) == 1
