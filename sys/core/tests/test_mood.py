# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💗 Emotions from measurements (roadmap 52): each a number from what is measured now, with its causes; nothing said
when nothing was measured. And the Security fixes of the same morning (C174): a block closes its incident, the
owner's blocks are counted among her proposals."""
import json
import time

import pytest

from aurora import kno_mood, sec_defence, sys_autonomy, sys_logread
from aurora.sec_incidents import Incidents

QUIET = {"answers": 0, "by_outcome": {}, "errors": 0}


@pytest.fixture
def machine(cfg, monkeypatch):
    state = {"gpus": [{"index": 0, "util": 0, "temp_c": 35, "margin_c": 52}], "hour": QUIET, "day": QUIET}
    monkeypatch.setattr(kno_mood, "gpus", lambda: state["gpus"])
    monkeypatch.setattr(sys_logread, "answer_stats", lambda h, cfg=None: state["hour" if h <= 1 else "day"])
    cfg.values.update(AURORA_MOOD=True, AURORA_LLM_PARALLEL=2, AURORA_STUDY_PER_NIGHT=5, AURORA_REVIEW_PER_DAY=3,
                      AURORA_REM_BORED_MIN=120)
    return state


def test_a_resting_machine_is_not_stressed_and_says_why(cfg, machine):
    m = kno_mood.measure(cfg, {}, 0)
    assert m["emotions"]["stress"]["value"] == 0.0 and "riposo" in m["emotions"]["stress"]["causes"][0]
    assert m["emotions"]["satisfaction"]["value"] is None             # no question: not said
    assert m["emotions"]["tiredness"]["value"] is None                # no samples yet: not said
    assert m["dominant"] == "serenity"


def test_stress_is_the_largest_cause_heat_load_or_errors(cfg, machine):
    machine["gpus"] = [{"index": 0, "util": 30, "temp_c": 70, "margin_c": 17},
                       {"index": 1, "util": 92, "temp_c": 80, "margin_c": 4}]
    m = kno_mood.measure(cfg, {}, 1)
    s = m["emotions"]["stress"]
    assert s["value"] == 0.92 and s["causes"][0] == "GPU1 al 92%"
    assert "4 °C dal limite" in s["causes"][1]                       # 15/(15+4) = 0.79, second
    machine["gpus"] = [{"index": 0, "util": 0, "temp_c": 35, "margin_c": 52}]
    machine["hour"] = {"answers": 2, "by_outcome": {}, "errors": 4}
    assert kno_mood.measure(cfg, {}, 0)["emotions"]["stress"]["value"] == 0.8   # 4 errors: 4/(4+1)


def test_each_count_is_half_at_its_own_threshold(cfg, machine):
    machine["day"] = {"answers": 10, "by_outcome": {"knowledge": 8, "abstained": 2}, "errors": 0}
    st = {"idle_min": 120, "to_study": 4, "drives": {"novelty": 4}, "weather": {"clouds_pct": 100, "rain_mm": 1.0}}
    e = kno_mood.measure(cfg, st, 0)["emotions"]
    assert e["satisfaction"]["value"] == 0.8 and "8 domande su 10" in e["satisfaction"]["causes"][0]
    assert e["longing"]["value"] == 0.5                                # silent as long as the boredom threshold
    assert e["curiosity"]["value"] == 0.5                              # as much as one night can take (5 + 3)
    assert e["melancholy"]["value"] == 0.5 and "1.0 mm" in e["melancholy"]["causes"][0]


def test_worry_comes_from_grave_incidents_and_health_only_for_the_admin(cfg, machine):
    Incidents(cfg).add({"kind": "ips_alert", "source": "45.33.32.156", "severity": "high", "count": 1})
    st = {"health_problems": ["aurora-https: HTTPS non risponde"]}
    assert kno_mood.measure(cfg, st, 0, admin=True)["emotions"]["worry"]["value"] == pytest.approx(2 / 3, abs=0.01)
    assert kno_mood.measure(cfg, {}, 0, admin=False)["emotions"]["worry"]["value"] == 0.0


def test_tiredness_is_the_busy_share_of_the_last_hours(cfg, machine):
    now = time.time()
    rows = [{"at": now - 60 * (40 - i), "gpu": 90 if i < 10 else 0, "busy": False} for i in range(40)]
    kno_mood._file(cfg).parent.mkdir(parents=True, exist_ok=True)
    kno_mood._file(cfg).write_text(json.dumps(rows))
    assert kno_mood.tiredness(cfg)["value"] == 0.25
    kno_mood.record(cfg, True, [{"util": 0}])                            # a minute after the last one: kept
    kno_mood.record(cfg, True, [{"util": 0}])                            # again at once: not a second sample
    assert len(kno_mood._samples(cfg)) == 41


def test_her_words_and_the_good_morning_say_the_cause(cfg, machine):
    m = kno_mood.measure(cfg, {"idle_min": 720}, 0)
    assert m["dominant"] == "longing"
    assert kno_mood.feeling(m) == "Stamattina prevale la nostalgia: nessun messaggio da 12.0 ore."
    assert "nostalgia 0.9 (nessun messaggio da 12.0 ore)" in kno_mood.words(m)
    kno_mood.save(cfg, m)
    assert kno_mood.compact(kno_mood.last(cfg))["dominant"] == "longing"
    cfg.values["AURORA_MOOD"] = False
    assert kno_mood.last(cfg) is None and kno_mood.measure(cfg, {}, 0)["emotions"] == {}


def test_an_old_mood_is_not_said_as_todays(cfg, machine):
    m = kno_mood.measure(cfg, {}, 0)
    kno_mood.save(cfg, {**m, "at": time.time() - 3600})
    assert kno_mood.last(cfg) is None


# ---- Security, C174 -------------------------------------------------------------------------------------------------
def test_a_second_click_on_a_blocked_address_adds_no_row(cfg):
    sec_defence.record_manual(cfg, "45.33.32.156", "ips_alert i1", "i1")
    sec_defence.record_manual(cfg, "45.33.32.156", "ips_alert i1", "i1")
    assert len(sec_defence._load(cfg)) == 1 and sec_defence.blocked(cfg, "45.33.32.156")


def test_the_owners_blocks_count_among_her_security_proposals(cfg):
    inc = Incidents(cfg)
    a = inc.add({"kind": "ips_alert", "source": "45.33.32.156", "severity": "high", "count": 1})
    b = inc.add({"kind": "rule:scan", "source": "45.33.32.157", "severity": "medium", "count": 3})
    inc.add({"kind": "rule:scan", "source": "10.0.0.7", "severity": "low", "count": 50, "internal": True})
    inc.update(b["id"], status="closed")                               # closed without a block: refused
    sec_defence.record_manual(cfg, "45.33.32.156", "ips_alert", a["id"])
    sec = sys_autonomy.statistics(cfg, [], set())["security"]
    assert (sec["proposed"], sec["approved"], sec["refused"], sec["rate"]) == (2, 1, 1, 0.5)   # home: never a proposal


def test_what_she_did_alone_is_counted_from_her_ledger(cfg):
    sys_autonomy.log(cfg, "knowledge", "searched the sources by herself: x")
    sys_autonomy.log(cfg, "forge", "plugin logs built")
    sys_autonomy.log(cfg, "social", "facebook.publish_post: y")         # social: counted from the approvals instead
    st = sys_autonomy.statistics(cfg, [], set())
    assert (st["knowledge"]["alone"], st["forge"]["alone"], st["social"]["alone"]) == (1, 1, 0)
