# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""😠 Anger measured (kno_anger; owner, 17 Oct: «ma si può anche arrabbiare?… sempre uno stato basato su
misurazioni»): insults counted by words, fading in half an hour, ended by an apology; two in a few minutes and she asks
for a moment — never for what is urgent, never longer than COOL_S. Made-up messages."""
import pytest

from aurora import kno_anger as A, kno_mood


@pytest.mark.parametrize("text,kind", [
    ("Sei proprio un'idiota", "offence"), ("stai zitta", "offence"), ("vaffanculo", "offence"),
    ("you're so useless", "offence"), ("Sei davvero inutile oggi", "offence"),
    ("Che errore stupido ho fatto nel codice", ""), ("è inutile provare stasera, piove", ""),
    ("Scusa, mi dici che ore sono?", "apology"), ("Mi dispiace per prima", "apology"), ("Che tempo fa?", ""),
])
def test_an_insult_is_told_from_a_word_that_only_sounds_rude(text, kind):
    assert A.heard(text) == kind


def test_one_offence_is_half_two_close_ones_more_and_each_fades_in_half_an_hour():
    now = 10_000.0
    one = [{"at": now, "kind": "offence", "words": "x"}]
    assert A.value(one, now)[0] == 0.5
    two = one + [{"at": now + 60, "kind": "offence", "words": "y"}]
    assert 0.6 < A.value(two, now + 60)[0] < 0.7
    assert A.value(one, now + A.FADE_S)[0] == 0.0
    assert A.value(two + [{"at": now + 120, "kind": "apology"}], now + 121)[0] == 0.0


def test_she_answers_after_one_asks_for_a_moment_after_two_and_an_apology_ends_it(cfg):
    t = 50_000.0
    r = A.react(cfg, "sei una cretina, dimmi il meteo", now=t)
    assert r["kind"] == "offence" and r["prefix"].startswith("😠") and not r["cool"]
    r = A.react(cfg, "stai zitta", now=t + 30)
    assert r["cool"] and "calmarmi" in r["cool"]
    assert A.react(cfg, "che ore sono?", now=t + 60)["cool"]                    # still cooling
    assert not A.react(cfg, "c'è un allarme in casa, aiuto", now=t + 70)["cool"]  # urgent: answered at once
    assert not A.react(cfg, "che ore sono?", now=t + 30 + A.COOL_S + 1)["cool"]   # never longer than COOL_S
    r = A.react(cfg, "scusami, ho esagerato", now=t + 400)
    assert r["prefix"].startswith("🙂") and A.level(cfg, now=t + 401)["value"] == 0.0


def test_anger_is_one_of_her_emotions_and_prevails_when_it_is_the_highest(cfg, monkeypatch):
    monkeypatch.setattr(kno_mood, "gpus", lambda: [])
    import time
    A.react(cfg, "sei un'idiota", now=time.time())
    A.react(cfg, "fai schifo", now=time.time())
    m = kno_mood.measure(cfg, {})
    assert m["emotions"]["anger"]["value"] > 0.6 and m["dominant"] == "anger"
    assert "offese" in m["emotions"]["anger"]["causes"][0]
    assert kno_mood.LABELS["it"]["anger"] == "rabbia"


def test_off_means_no_anger(cfg, monkeypatch):
    monkeypatch.setitem(cfg.raw, "AURORA_MOOD", "false") if hasattr(cfg, "raw") else None
    off = type("C", (), {"__getitem__": lambda s, k: False if k == "AURORA_MOOD" else cfg[k], "user": None, "base": None})()
    assert A.react(off, "sei un'idiota") == {"kind": "", "value": 0.0, "cool": "", "prefix": ""}
