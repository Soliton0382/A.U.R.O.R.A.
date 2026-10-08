# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aurora.kno_rem import Rem
from aurora.sol_index import Indexer
from aurora.sol_reader import VaultReader
from aurora.sol_schema import Soliton
from aurora.sol_writer import VaultWriter
from test_sol_index import FakeEncoder


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def complete(self, system, user, max_tokens, think=False):
        self.prompts.append(user)
        return SimpleNamespace(answer="Il 30 settembre il proprietario mi ha chiesto del Transformer.")


def turn(role, text, minutes_ago, run="r1", **extra):
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="milliseconds")
    return Soliton.new(text, "conversation", "conversation", "it", f"run:{run}", created_at=at,
                       extra={"role": role, "run_id": run, **extra})


def pipeline(cfg):
    llm = FakeLLM()
    return SimpleNamespace(writer=VaultWriter(cfg), reader=VaultReader(cfg), indexer=Indexer(FakeEncoder(), cfg),
                           llm=llm, _for=lambda role: llm)


def test_closed_sessions_become_memories_and_turns_go_long_term(cfg):
    p = pipeline(cfg)
    p.writer.add_many([turn("user", "Quante teste usa il Transformer?", 200),
                       turn("assistant", "Otto teste [1].", 199),
                       turn("user", "E il dropout?", 190, "r2"),
                       turn("assistant", "Non ho trovato nulla.", 189, "r2", abstained=True),
                       turn("user", "Ciao Aurora", 5, "r3")])                  # open session: too recent
    events = []
    out = Rem(p, cfg).consolidate(lambda e, x: events.append((e, x)))
    assert len(out["sessions"]) == 1 and out["sessions"][0]["turns"] == 4 and out["sessions"][0]["moved_to_ltm"] == 4
    prompt = p.llm.prompts[0]
    assert "Otto teste" in prompt and "Non ho trovato nulla" not in prompt and "(non ha trovato nulla nel vault)" in prompt
    mem = p.reader.recent(5, domain="reflection")
    assert len(mem) == 1 and mem[0].kind == "reflection" and mem[0].extra["type"] == "session_memory"
    assert mem[0].consolidated and len(mem[0].extra["turns"]) == 4
    assert [t.consolidated for t in p.reader.recent(5)] == [True, True, True, True, False]
    assert Rem(p, cfg).consolidate(lambda e, x: None) == {"sessions": []}   # nothing twice
    assert events[0][0] == "rem.session_memory"


def test_trail_keeps_steps_and_reasoning_not_the_streamed_answer():
    from aurora.kno_answer import Trail
    t = Trail()
    t.add("route", {"mode": "knowledge"})
    t.add("synthesis.delta", {"kind": "thought", "text": "penso "})
    t.add("synthesis.delta", {"kind": "answer", "text": "bozza"})
    t.add("synthesis.delta", {"kind": "thought", "text": "ancora"})
    t.add("verify.drop", {"sentence": "x" * 5000, "reason": "no citation"})
    out = t.export()
    assert [s[0] for s in out["trace"]] == ["route", "verify.drop"]
    assert out["thought"] == "penso ancora" and "bozza" not in str(out["trace"])
    assert len(out["trace"][1][1]["sentence"]) == Trail.MAX_TEXT + 1                # cut, with an ellipsis


def dreaming(cfg, monkeypatch, paint):
    p = pipeline(cfg)
    p.writer.add_many([turn("user", "Parlami dei solitoni", 30), turn("assistant", "Onde che non si disperdono.", 29)])
    p.llm.complete = lambda system, user, max_tokens, think=False: SimpleNamespace(
        answer="Sogno onde di luce.\nIMAGE: a luminous soliton wave")
    monkeypatch.setattr("aurora.kno_rem.mdl_image.paint", paint)
    monkeypatch.setattr("aurora.kno_rem.sys_features.ok", lambda cfg, name: True)   # the models, as on a full install
    monkeypatch.setattr(Rem, "_random_knowledge", lambda self, n: [])
    out = Rem(p, cfg).dream(lambda e, x: None)
    return out, [s for s in p.reader.recent(5, domain="reflection") if s.extra.get("type") == "dream"][-1]


def test_a_dream_is_painted(cfg, monkeypatch):
    seen = {}
    def paint(prompt, name, cfg, emit, title=""):
        seen["prompt"] = prompt
        return {"file": f"{name}.png", "seconds": 1.0, "swap": True}
    out, dream = dreaming(cfg, monkeypatch, paint)
    assert seen["prompt"] == "a luminous soliton wave"
    assert dream.text == "Sogno onde di luce." and dream.extra["image"].startswith("dream-") and not dream.extra["painting_problem"]


def test_a_dream_survives_a_failed_painting(cfg, monkeypatch):
    def paint(*a, **k):
        raise RuntimeError("GPU 0: 0.7 GB free")
    out, dream = dreaming(cfg, monkeypatch, paint)
    assert dream.extra["image"] is None and "GPU 0" in dream.extra["painting_problem"] and out["sid"] == dream.sid


def test_without_the_dream_models_the_dream_is_written_and_says_why_it_is_not_painted(cfg, monkeypatch):
    def paint(*a, **k):
        raise AssertionError("no model, no painting job")
    p = pipeline(cfg)
    p.writer.add_many([turn("user", "Parlami dei solitoni", 30), turn("assistant", "Onde che non si disperdono.", 29)])
    p.llm.complete = lambda system, user, max_tokens, think=False: SimpleNamespace(
        answer="Sogno onde di luce.\nIMAGE: a luminous soliton wave")
    monkeypatch.setattr("aurora.kno_rem.mdl_image.paint", paint)
    monkeypatch.setattr(Rem, "_random_knowledge", lambda self, n: [])
    monkeypatch.setattr("aurora.kno_rem.sys_features.ok", lambda cfg, name: False)
    monkeypatch.setattr("aurora.kno_rem.sys_features.check", lambda cfg, name: {"missing": ["image_base (18 file)"]})
    cfg.values["AURORA_IMAGE_ENABLED"] = True
    out = Rem(p, cfg).dream(lambda e, x: None)
    assert out["image"] is None and out["painting_problem"] == "image_base (18 file)"


def test_dates_are_labelled_relative_to_today(cfg):
    from aurora import sns_clock
    now = sns_clock.now(cfg)
    assert sns_clock.when(now.isoformat(), cfg).endswith("(oggi)")
    assert sns_clock.when((now - timedelta(days=1)).isoformat(), cfg).endswith("(ieri)")
    assert sns_clock.when((now - timedelta(days=5)).isoformat(), cfg).endswith("(5 giorni fa)")
    assert sns_clock.DAYS_IT[(now - timedelta(days=1)).weekday()] in sns_clock.when((now - timedelta(days=1)).isoformat(), cfg)


def test_the_dream_s_painting_is_the_scene_the_dream_tells():
    """C196: the dream was abstract sentences and its painting one object picked from them; now the dream is told as
    scenes and the painting is its central scene, with the dream's own place, things, colours and light."""
    from aurora.kno_rem import SYS_DREAM
    assert "SEEN" in SYS_DREAM and "central" in SYS_DREAM
    assert "exactly that central scene" in SYS_DREAM and "nothing it does not tell" in SYS_DREAM
    assert "no names of people" in SYS_DREAM
