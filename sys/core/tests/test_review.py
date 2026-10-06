# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Thinking again about past answers (owner, 2026-10-06): drives counted, not simulated; a message only for a better
answer with new sources; a daily limit; a pause when it is not worth it."""
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aurora import kno_review

NOW = datetime.now(timezone.utc)


def turn(role, text, rid, hours_ago=30, sid=None, **extra):
    return SimpleNamespace(text=text, sid=sid or f"{rid}-{role}", created_at=(NOW - timedelta(hours=hours_ago)).isoformat(),
                           extra={"role": role, "run_id": rid, **extra})


def answer(rid, hours_ago=30, dropped=0, sources=2, **extra):
    trace = [["answer.final", {"dropped": ["x"] * dropped}]]
    return turn("assistant", f"risposta {rid}", rid, hours_ago, mode="knowledge", abstained=False, trace=trace,
                source_list=[{"sid": f"s{i}", "title": f"T{i}"} for i in range(sources)], **extra)


class P:
    def __init__(self, turns, new=None, verdict="NEW_INFO\nAggiunge il meccanismo."):
        self.reader = SimpleNamespace(recent=lambda n, domain="conversation": turns if domain == "conversation" else [],
                                      layout=SimpleNamespace(shards=lambda *a: []))
        self.new, self.asked = new, []
        self.llm = SimpleNamespace(complete=lambda s, u, n: SimpleNamespace(answer=verdict))
        self.search = SimpleNamespace(embedder=None)

    def run(self, question, emit, run_id, remember=True):
        assert remember is False                      # a review never writes a conversation turn
        self.asked.append(question)
        return self.new


def test_the_weakest_past_answers_come_first(cfg):
    turns = [turn("user", "Cos'è un laser?", "r1"), answer("r1"),
             turn("user", "Come funziona la fusione?", "r2"), answer("r2", dropped=2),
             turn("user", "Cos'è un buco nero?", "r3", hours_ago=2), answer("r3", hours_ago=2),           # too recent
             turn("user", "Che ore sono?", "r4"), turn("assistant", "Le 10", "r4", mode="self"),          # not knowledge
             turn("user", "Spiegami la decoerenza", "r5"), turn("assistant", "Non so", "r5", abstained=True, mode="knowledge"),
             turn("user", "Cos'è l'entropia?", "r6", hours_ago=24 * 20), answer("r6", hours_ago=24 * 20)]    # too old
    got = kno_review.candidates(P(turns), cfg)
    assert [g["run_id"] for g in got] == ["r2", "r1"]
    assert got[0]["drive"] == "dissatisfaction" and got[1]["drive"] == "novelty"
    d = kno_review.drives(P(turns), cfg, idle_min=90)
    assert (d["curiosity"], d["dissatisfaction"], d["novelty"], d["social_h"]) == (1, 1, 1, 1.5)


def test_a_follow_up_is_reviewed_as_it_was_searched(cfg):
    a = answer("r1")
    a.extra["trace"].insert(0, ["question.standalone", {"question": "Come funziona la fissione nucleare?"}])
    got = kno_review.candidates(P([turn("user", "e la fissione?", "r1"), a]), cfg)
    assert got[0]["question"] == "Come funziona la fissione nucleare?"


def test_only_a_better_answer_with_new_sources_is_told(cfg, monkeypatch):
    written, shadowed = [], []
    monkeypatch.setattr("aurora.kno_rem.Rem._write", lambda self, text, typ, src, extra, emit:
                        written.append((typ, text)) or SimpleNamespace(sid="w1"))
    monkeypatch.setattr("aurora.kno_shadow.add", lambda *a, **k: shadowed.append(a[2]))
    cfg.values.update({"AURORA_REVIEW_MESSAGES": 1})
    turns = [turn("user", "Cos'è un laser?", "r1"), answer("r1"), turn("user", "Come funziona la fusione?", "r2"), answer("r2")]
    new = SimpleNamespace(text="nuova [1]", abstained=False, mode="knowledge", sources=[{"sid": "s9", "title": "Nuovo"}],
                          suggestions=[])
    out = kno_review.review(P(turns, new), cfg, lambda *a: None, 2)
    assert (out["reviewed"], out["better"], out["told"]) == (2, 2, 1)            # one message a day, both in the shadow
    assert written[0][0] == "review" and "Ripensando alla tua domanda" in written[0][1] and "Nuovo" in written[0][1]
    assert len(shadowed) == 2
    assert kno_review.candidates(P(turns), cfg) == []                           # each answer reviewed once


def test_same_sources_or_same_content_is_not_news(cfg, monkeypatch):
    monkeypatch.setattr("aurora.kno_rem.Rem._write", lambda *a, **k: (_ for _ in ()).throw(AssertionError("told")))
    turns = [turn("user", "Cos'è un laser?", "r1"), answer("r1")]
    old_sources = SimpleNamespace(text="x", abstained=False, mode="knowledge", sources=[{"sid": "s0"}], suggestions=[])
    assert kno_review.review(P(turns, old_sources), cfg, lambda *a: None, 1)["better"] == 0
    f = kno_review._state_file(cfg); f.unlink()
    new = SimpleNamespace(text="x", abstained=False, mode="knowledge", sources=[{"sid": "s9"}], suggestions=[])
    assert kno_review.review(P(turns, new, verdict="SAME"), cfg, lambda *a: None, 1)["better"] == 0


def test_the_judge_reads_one_word():
    llm = lambda out: SimpleNamespace(complete=lambda s, u, n: SimpleNamespace(answer=out))
    assert kno_review.judge(llm("**CORRECTION**\nLa massa era sbagliata."), "q", "a", "b") == ("CORRECTION", "La massa era sbagliata.")
    assert kno_review.judge(llm("new info\nx"), "q", "a", "b")[0] == "NEW_INFO"
    assert kno_review.judge(llm("boh"), "q", "a", "b")[0] == "SAME"           # unreadable: never news


def test_hours_limit_and_pause(cfg):
    cfg.values.update({"AURORA_REVIEW_HOURS": "9-22", "AURORA_REVIEW_PER_DAY": 3})
    assert kno_review.in_hours(cfg, 9) and kno_review.in_hours(cfg, 21) and not kno_review.in_hours(cfg, 22)
    cfg.values["AURORA_REVIEW_HOURS"] = "22-2"
    assert kno_review.in_hours(cfg, 23) and kno_review.in_hours(cfg, 1) and not kno_review.in_hours(cfg, 12)
    for i in range(kno_review.PAUSE_AFTER - 1):
        kno_review._mark(cfg, f"r{i}", {"verdict": "SAME", "at": time.time() - 86400 * 2 + i})
    assert not kno_review.paused(cfg)
    kno_review._mark(cfg, "last", {"verdict": "WORSE", "at": time.time() - 86400})
    assert kno_review.paused(cfg)                                               # 12 in a row with nothing better
    kno_review._mark(cfg, "good", {"verdict": "NEW_INFO", "at": time.time()})
    assert not kno_review.paused(cfg) and kno_review.reviewed_today(cfg) == 1
